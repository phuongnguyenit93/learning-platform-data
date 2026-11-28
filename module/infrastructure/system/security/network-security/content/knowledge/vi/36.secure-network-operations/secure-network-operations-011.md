# SLA và chỉ số của Network Security Operation

## 1. Tại sao vận hành bảo mật mạng cần SLA và chỉ số đo lường?

Một hệ thống firewall có thể hiển thị trạng thái **UP** nhưng lại áp dụng sai quy tắc phân đoạn; VPN có thể nhận đăng nhập nhưng nhân viên không vào được ứng dụng; SIEM có thể chạy ổn định trong khi log từ một thiết bị mạng quan trọng đã ngừng gửi. Vì vậy, chỉ đo uptime của thiết bị không đủ để chứng minh **dịch vụ bảo mật mạng đang được cung cấp đúng và hiệu quả**.

Trong chương **Quản trị vận hành mạng an toàn**, việc quản lý **Service Level Agreement (SLA)** và các chỉ số liên quan giúp biến lời hứa “hệ thống mạng an toàn và được giám sát liên tục” thành những kỳ vọng **có chủ sở hữu, ranh giới, cách đo, thời hạn và bằng chứng**. Đây là công cụ điều hành, kiểm soát rủi ro, ưu tiên nguồn lực và cải tiến dịch vụ; không phải chỉ là bảng điểm đẹp cho lãnh đạo.

Bài học thuộc module **SECURITY_NETWORK_SECURITY**, áp dụng cho vận hành phân đoạn và firewall, VPN/ZTNA, IDS/IPS/NDR, DNS, Wi-Fi, xác thực kết nối, thiết bị mạng, kết nối cloud và các hệ thống điều phối. Nhóm Network Security Operation (NetSecOps) phải vừa giữ **khả năng kết nối hợp lệ**, vừa bảo đảm **luồng trái chính sách bị chặn, sự cố có thể quan sát và phản ứng đúng lúc**.

Sau bài học, người học có thể:

1. Phân biệt SLA, SLO, SLI, OLA, hợp đồng hỗ trợ và các mục tiêu phục hồi.
2. Xác định đối tượng dịch vụ, ranh giới trách nhiệm, cửa sổ thời gian, mẫu số và nguồn dữ liệu đo.
3. Thiết kế chỉ số cho tính sẵn sàng, hiệu lực kiểm soát, độ phủ log, chất lượng cảnh báo, xử lý sự cố, lỗ hổng và thay đổi cấu hình.
4. Tính service availability, error budget, thời gian phát hiện và phản ứng mà không nhầm mốc bắt đầu/kết thúc.
5. Xây dashboard, quy trình báo cáo, escalation và đánh giá vi phạm SLA có chứng cứ.
6. Nhận diện trường hợp chỉ số “đạt” nhưng dịch vụ bảo mật thực tế vẫn có rủi ro.

> **Ý chính:** SLA có giá trị khi đo **dịch vụ theo trải nghiệm và rủi ro thật**, trong khi các chỉ số nội bộ cho biết **vì sao dịch vụ đạt hoặc không đạt**, và cần hành động gì tiếp theo.

## 2. Phân biệt SLA, SLO, SLI, OLA, RTO và RPO

| Khái niệm | Định nghĩa thực dụng | Ví dụ trong network security |
| --- | --- | --- |
| **SLI – Service Level Indicator** | Đại lượng quan sát được, có công thức và phương pháp đo | Tỷ lệ probe VPN → ứng dụng hoàn thành thành công trong cửa sổ 30 ngày |
| **SLO – Service Level Objective** | Mục tiêu mong muốn cho một SLI trong phạm vi và kỳ đo | Ít nhất 99,95% phút đủ điều kiện dịch vụ truy cập từ xa sẵn sàng |
| **SLA – Service Level Agreement** | Cam kết/thỏa thuận chính thức giữa bên cung cấp và bên nhận dịch vụ, có cách đo và cơ chế xử lý vi phạm | Thời gian cung cấp dịch vụ, tỷ lệ sẵn sàng, cách thông báo và trách nhiệm khi không đạt |
| **OLA – Operational Level Agreement** | Thỏa thuận phối hợp **nội bộ** giữa các nhóm để hỗ trợ SLA/SLO | NetOps cung cấp đường OOB, IAM duy trì IdP, SOC tiếp nhận cảnh báo theo quy trình |
| **Supporting contract / underpinning agreement** | Cam kết của nhà cung cấp hoặc đối tác hỗ trợ dịch vụ | Hợp đồng bảo trì firewall, hỗ trợ kỹ thuật, thay thiết bị |
| **RTO – Recovery Time Objective** | Mục tiêu thời gian phục hồi sau gián đoạn thuộc phạm vi liên tục kinh doanh/khôi phục | Khôi phục năng lực truy cập ứng dụng qua VPN sau một sự cố nghiêm trọng trong mục tiêu được phê duyệt |
| **RPO – Recovery Point Objective** | Mức mất dữ liệu tối đa có thể chấp nhận theo thời gian, chủ yếu với dữ liệu/trạng thái cần khôi phục | Mức mất bản sao cấu hình hoặc dữ liệu nhật ký được chấp nhận khi phục hồi hệ quản lý |

SLO **không tự động** là điều khoản hợp đồng; SLA thường chứa nhiều điều kiện ngoài một ngưỡng kỹ thuật, chẳng hạn phạm vi khách hàng, giờ hỗ trợ, loại trừ được thỏa thuận, chế độ escalation và cách giải quyết vi phạm. Một tổ chức cũng có thể đặt **SLO nội bộ chặt hơn SLA** để có vùng dự phòng vận hành.

**RTO không phải MTTR:** RTO là *mục tiêu* phục hồi trong một kịch bản xác định, còn MTTR là chỉ số *đo thực tế* với định nghĩa riêng của tổ chức. **RPO không phải uptime:** RPO đo chấp nhận mất dữ liệu/trạng thái khi phục hồi và có thể không phải chỉ số phù hợp cho mọi dịch vụ chuyển tiếp gói tin.

### 2.1. SLA có thể là cam kết gì?

Một SLA vận hành bảo mật mạng có thể bao gồm các nhóm nghĩa vụ khác nhau:

- **Khả năng truy cập dịch vụ được bảo vệ:** VPN, DNS resolver, secure web gateway hoặc đường ứng dụng qua firewall sẵn sàng theo giới hạn được định nghĩa.
- **Thời gian tiếp nhận và cập nhật sự cố:** đội trực nhận ticket, xác nhận mức ưu tiên và cung cấp cập nhật theo lịch.
- **Thời gian thực hiện yêu cầu tiêu chuẩn:** ví dụ phê duyệt và triển khai một firewall rule đã cung cấp đủ thông tin.
- **Độ sẵn sàng của hoạt động giám sát:** hệ thống logging/telemetry có nguồn dữ liệu đầy đủ trong giới hạn đã cam kết.
- **Yêu cầu kiểm soát:** chính sách default deny, ghi log quản trị và kiểm thử định kỳ; thường thích hợp dưới dạng tiêu chí kiểm soát hoặc OLO/SLO nội bộ hơn là một con số “an toàn 100%”.

Không tuyên bố cam kết “ngăn chặn mọi cuộc tấn công”, vì không thể xác minh đầy đủ và không phản ánh giới hạn thực tế của hệ thống phòng vệ.

## 3. Định nghĩa dịch vụ trước khi đo

**Đơn vị được đo là dịch vụ**, không nhất thiết là một thiết bị đơn lẻ. Để thiết kế SLA, phải trả lời người dùng/ứng dụng đang nhận được năng lực nào và phần nào thuộc trách nhiệm NetSecOps.

| Dịch vụ | Trải nghiệm hoặc năng lực cần bảo đảm | Thành phần phụ thuộc |
| --- | --- | --- |
| Truy cập từ xa an toàn | Người dùng hợp lệ xác thực và truy cập **đúng ứng dụng được phép** | VPN/ZTNA gateway, IdP/MFA, DNS, policy, tuyến mạng |
| Firewall phân đoạn | Luồng hợp lệ đi qua; luồng ngoài policy bị chặn | HA, rulebase, route/NAT, collector log, host/cloud policy |
| Bảo vệ truy cập Internet | Ứng dụng được phép truy cập theo policy; rủi ro bị kiểm soát | Egress firewall, proxy, DNS, certificate, ISP |
| DNS bảo mật | Phân giải đúng, kịp thời, theo chính sách, có thể truy vết | Resolver, forwarder, DNSSEC/policy theo thiết kế, upstream, log |
| IDS/IPS/NDR | Có tín hiệu quan sát và xử lý các tình huống đã được chọn | Sensor, mirror/TAP/inline path, signature, telemetry, SIEM |
| Mạng Wi-Fi doanh nghiệp | Thiết bị hợp lệ kết nối, xác thực và đến tài nguyên được phép | AP/controller, RADIUS/IdP, RF, VLAN, firewall |
| Quản trị thiết bị mạng | Người được cấp phép truy cập quản trị an toàn và có audit | Bastion/OOB, AAA, SSH/HTTPS/SNMPv3, thiết bị |
| Kết nối mạng cloud/hybrid | Workload được phép kết nối qua zone/region đúng chính sách | Security group, cloud firewall, routing, VPN/interconnect |

Chẳng hạn, việc **một firewall node trong HA bị lỗi** có thể không làm gián đoạn dịch vụ nếu node còn lại tiếp tục phục vụ; tuy vậy đó là suy giảm **mức dự phòng**, cần cảnh báo riêng. Ngược lại, cả hai node “healthy” nhưng một policy bị áp sai vẫn có thể gây vi phạm kiểm soát. Vì vậy nên duy trì đồng thời **chỉ số trải nghiệm dịch vụ**, **chỉ số rủi ro/kiểm soát** và **chỉ số sức khỏe thành phần**.

### 3.1. Service catalog tối thiểu

Một bản ghi danh mục dịch vụ nên có:

- **Service ID, tên, mô tả, người sử dụng và mức criticality**.
- **Owner chịu trách nhiệm cuối cùng** và các nhóm vận hành/phụ thuộc.
- **Phạm vi mạng và tài sản**: site, khu vực, VPC/VNet, tenant, IP/URL/FQDN, nhóm người dùng và trường hợp không thuộc phạm vi.
- **Giờ cung cấp và kỳ đo**: 24×7 hay theo giờ kinh doanh; timezone; lịch bảo trì được xử lý thế nào.
- **SLI, SLO, SLA áp dụng**, phương pháp kiểm chứng, thời hạn lưu chứng cứ và đầu mối escalation.
- **Kênh thông báo, change freeze và hỗ trợ cứu hộ**, nhất là khi mất cả quản trị từ xa.

Đừng lấy tổng số thiết bị trong CMDB làm mẫu số của “SLA kết nối” nếu điều khách hàng cần là **một luồng nghiệp vụ end-to-end**. Mô hình đo phải nhất quán với mục tiêu sử dụng.

## 4. Xây dựng bộ chỉ số theo lớp

Nên tổ chức các chỉ số theo ba lớp:

~~~mermaid
flowchart TD
    A["Lớp 1: Kết quả dịch vụ và rủi ro"] --> B["Sẵn sàng, truy cập đúng quyền, đáp ứng sự cố"]
    C["Lớp 2: Hiệu quả kiểm soát an ninh"] --> D["Phân đoạn, detection, telemetry, khắc phục"]
    E["Lớp 3: Chỉ số chẩn đoán vận hành"] --> F["HA, CPU, drops, collector lag, config drift"]
    F --> D
    D --> B
    B --> G["SLA / SLO và quyết định ưu tiên"]
~~~

Một dashboard tốt trình bày **kết quả trước, nguyên nhân sau**. Chỉ số thành phần như CPU firewall, session table, lỗi interface hoặc lượng log gửi về giúp điều tra, nhưng không nên sử dụng chúng như đại diện duy nhất cho tính bảo mật.

### 4.1. Ma trận chỉ số gợi ý

| Nhóm | SLI/KPI | Ý nghĩa | Rủi ro khi diễn giải |
| --- | --- | --- | --- |
| **Khả dụng** | Service availability, tỷ lệ probe end-to-end thành công | Dịch vụ đến được từ nơi người dùng sử dụng | Uptime thiết bị có thể cao trong khi ứng dụng bị chặn sai |
| **Độ trễ/chất lượng** | p95/p99 DNS response, VPN connect duration, packet loss trên tuyến được duyệt | Trải nghiệm và hiệu năng | Không dùng trung bình che sự cố theo site/nhóm user |
| **Chính sách** | Tỷ lệ positive/negative policy test đạt | Luồng hợp lệ chạy được, luồng trái policy bị chặn | Timeout không có log chưa đủ chứng minh deny đúng |
| **Phủ giám sát** | Tỷ lệ nguồn telemetry trọng yếu gửi log đúng chuẩn và đúng hạn | Mức độ quan sát được môi trường | Có log không có nghĩa detection hoạt động |
| **Phát hiện** | Detection test coverage, alert precision trên tập đã phân loại | Chất lượng phát hiện trong các tình huống có thể kiểm chứng | Không suy thành recall toàn bộ các cuộc tấn công thực |
| **Sự cố** | TTD, thời gian acknowledge, triage/contain, escalation compliance | Tốc độ vận hành theo mức ưu tiên | Những sự cố chưa phát hiện không có trong mẫu đo |
| **Lỗ hổng** | Tỷ lệ tài sản trong phạm vi được kiểm kê, tỷ lệ xử lý quá hạn | Mức độ kiểm soát exposure | “Đã tạo ticket” không bằng “đã khắc phục và xác minh” |
| **Thay đổi** | Change success rate, rollback rate, unauthorized change count | Độ ổn định và kiểm soát cấu hình | Không khuyến khích bỏ qua thay đổi có ích để giữ KPI |
| **Ngoại lệ** | Số ngoại lệ quá hạn, tỷ lệ ngoại lệ đủ owner/review/expiry | Mức kỷ luật quản trị policy | Rule 0 hits chưa chắc vô dụng, cần đối chiếu nghiệp vụ |
| **Khả năng phục hồi** | HA failover test pass, restore config test pass | Dịch vụ tiếp tục hoặc khôi phục đúng mục tiêu | Một lần failover thành công không bảo đảm mọi kịch bản |

Không cần đặt SLA hợp đồng cho **tất cả** chỉ số. Một số phù hợp là SLI/SLO dịch vụ; số khác là **Key Risk Indicator (KRI)**, chỉ số kỹ thuật nội bộ hoặc mục kiểm toán. Hãy chỉ định rõ loại chỉ số để tránh dùng tỷ lệ hoàn thành công việc thay cho kết quả bảo mật.

## 5. Đo tính sẵn sàng dịch vụ và error budget

### 5.1. Availability đo cái gì?

Với cách đo theo số phút đủ điều kiện:

\[
Availability = \frac{EligibleMinutes - UnavailableMinutes}
{EligibleMinutes} \times 100\%.
\]

Trong đó:

- **EligibleMinutes:** tổng phút thuộc kỳ SLA đã cam kết, sau khi áp dụng **đúng các điều khoản loại trừ được phê duyệt trước**.
- **UnavailableMinutes:** phút thuộc phạm vi được đo mà dịch vụ không đáp ứng điều kiện khả dụng đã định.
- **Kỳ đo:** lịch tháng, 30 ngày liên tiếp hay cửa sổ rolling; phải chọn trước, không đổi hậu kiểm để cải thiện kết quả.

Một dịch vụ có nhiều site/người dùng có thể bị lỗi cục bộ. Cần định nghĩa **thế nào là “dịch vụ không khả dụng”**: tất cả site lỗi, một tỷ lệ người dùng bị ảnh hưởng, một endpoint trọng yếu lỗi hay mỗi site có SLI riêng. Không cộng số phút gián đoạn của nhiều site và gọi là phút downtime toàn dịch vụ nếu đã định nghĩa khác.

### 5.2. Error budget

Nếu mục tiêu availability là \(SLO\) (biểu diễn từ 0 đến 1) trong kỳ có \(T\) phút đủ điều kiện:

\[
ErrorBudgetMinutes = T \times (1-SLO).
\]

**Ví dụ giả lập**: dịch vụ VPN/ZTNA có mục tiêu **99,95%** trong **30 ngày**, đo 24×7, không có phút loại trừ. Kỳ đo có:

\[
T = 30 \times 24 \times 60 = 43\,200\text{ phút}.
\]

Error budget cho phép:

\[
43\,200 \times (1 - 0{,}9995) = 21{,}6\text{ phút}.
\]

Nếu xác minh được **18 phút không khả dụng**:

\[
Availability = \frac{43\,200-18}{43\,200}\times100\%
\approx 99{,}9583\%.
\]

Kết quả **đạt** SLO 99,95% theo định nghĩa ví dụ, nhưng đã dùng \(18 / 21{,}6 \approx 83{,}33\%\) error budget, chỉ còn **3,6 phút**. Không nên chỉ ghi “SLO đạt” mà bỏ tín hiệu rằng dư địa chịu lỗi đã gần hết.

Lưu ý: cách làm tròn và quy tắc đo theo phút/phần trăm cần được thống nhất trong SLA. **Khoảng không có dữ liệu đo không được mặc định là thời gian hoạt động tốt**: nên đánh dấu **unknown**, truy nguồn đo khác và áp dụng quy tắc xử lý thiếu dữ liệu đã được công bố.

### 5.3. Đo bằng probe nào?

Thiết kế **synthetic transaction** có thể phản ánh trải nghiệm người dùng:

~~~text
SLO dịch vụ truy cập ứng dụng qua VPN:
  1. Từ probe tại vùng client đại diện, thiết lập đường VPN/ZTNA.
  2. Xác thực bằng tài khoản synthetic được phép, bảo vệ bí mật.
  3. Phân giải tên ứng dụng theo DNS đúng.
  4. Kết nối HTTPS và kiểm tra phản hồi ở tầng ứng dụng.
  5. Kiểm tra certificate hợp lệ và không được phép mở sai phạm vi.
  6. Ghi event time, site, kết quả từng chặng, HTTP/application result.

Thành công end-to-end:
  Mọi điều kiện cần thiết của giao dịch tổng hợp đều đạt.
Phân loại lỗi:
  VPN, IdP, DNS, route, firewall, TLS, ứng dụng, probe hoặc unknown.
~~~

Probe phải có quyền tối thiểu, dữ liệu không nhạy cảm và không gây tải đáng kể. Nếu tài khoản synthetic bị khóa hoặc bản thân probe hỏng, cần đánh dấu **measurement fault** để điều tra, không tùy tiện chuyển toàn bộ phút lỗi thành lỗi VPN hoặc thành thời gian hoạt động tốt.

**Phân biệt hai loại SLI:** availability end-to-end là kết quả người dùng, còn firewall appliance availability là chỉ số thành phần. Có thể đo cả hai, nhưng không trộn chung mẫu số.

## 6. SLA xử lý sự cố và cách đo thời gian

### 6.1. Mốc thời gian phải có ngữ nghĩa

~~~mermaid
flowchart LR
    A["t0: Sự kiện bắt đầu"] --> B["t1: Phát sinh tín hiệu / ingest"]
    B --> C["t2: Phát hiện có thể hành động"]
    C --> D["t3: Acknowledge"]
    D --> E["t4: Triage / xác minh"]
    E --> F["t5: Containment"]
    F --> G["t6: Service recovery"]
    G --> H["t7: Root cause / closure"]
~~~

Một số chỉ số:

\[
\begin{aligned}
TTD &= t_2-t_0,\\
TTA &= t_3-t_2,\\
TTC &= t_5-t_0,\\
TTR_{service} &= t_6-t_0.
\end{aligned}
\]

- **TTD (Time to Detect):** từ thời điểm hành vi/sự cố bắt đầu tới lúc phát hiện theo định nghĩa rõ.
- **TTA (Time to Acknowledge):** thời gian từ alert/case được phát sinh đến lúc người trực nhận trách nhiệm; một số tổ chức dùng MTTA là giá trị trung bình của nhiều TTA.
- **Triage time:** thời gian để nhận định loại sự kiện, mức ưu tiên và hướng xử lý.
- **TTC (Time to Contain):** thời gian đến khi kiểm soát ảnh hưởng theo tiêu chí containment đã định.
- **Time to Restore / Recover:** thời gian tới khi **dịch vụ** hoạt động trở lại theo kiểm tra nghiệp vụ.
- **MTTR:** thuật ngữ không nhất quán giữa các tổ chức (mean time to repair/recover/resolve/respond). Mọi dashboard phải ghi rõ nó là *mean time to điều gì, bắt đầu ở đâu, kết thúc ở đâu*.

**Ví dụ giả lập:** sự kiện bắt đầu 10:00; ingest log lúc 10:02; cảnh báo được SOC xác nhận đủ ngữ cảnh lúc 10:04; analyst acknowledge 10:09; containment hoàn tất 10:35; dịch vụ được xác minh phục hồi 10:50.

| Chỉ số | Kết quả | Giải thích |
| --- | ---: | --- |
| Telemetry delay | 2 phút | 10:00 → 10:02 |
| TTD | 4 phút | 10:00 → 10:04 |
| TTA | 5 phút | 10:04 → 10:09 |
| TTC | 35 phút | 10:00 → 10:35 |
| Time to restore | 50 phút | 10:00 → 10:50 |

Không được báo TTC là **26 phút** chỉ vì tính từ lúc acknowledge nếu hợp đồng đã định nghĩa tính từ thời điểm bắt đầu. Mốc nào chưa biết chính xác cần đánh dấu **ước lượng và nguồn suy đoán**, không tự cho độ chính xác tới từng giây.

### 6.2. Phân cấp ưu tiên và nghĩa vụ phản ứng

Một bảng mục tiêu **nội bộ minh họa, không phải chuẩn chung**:

| Mức | Ví dụ điều kiện | Tiếp nhận/acknowledge mục tiêu | Xử lý tiếp theo |
| --- | --- | --- | --- |
| **P1 / Critical** | Hệ thống bảo vệ trọng yếu mất chức năng; sự cố ảnh hưởng lớn và đang diễn ra | Trong 15 phút theo trực 24×7 | Kích hoạt incident commander, SOC/NetOps/owner, cập nhật theo quy trình khẩn |
| **P2 / High** | Suy giảm đáng kể hoặc rủi ro cao trong một vùng | Trong 30 phút theo giờ trực áp dụng | Điều tra ưu tiên, có kế hoạch containment và thông báo |
| **P3 / Medium** | Lỗi cục bộ, có đường dự phòng hoặc workaround được phê duyệt | Trong 4 giờ làm việc | Xử lý theo hàng đợi và owner đã chỉ định |
| **P4 / Low** | Yêu cầu chuẩn hóa, cải tiến hoặc cảnh báo ít ảnh hưởng | Trong 1 ngày làm việc | Lập ticket, xem xét trong lịch vận hành |

Ngưỡng trên chỉ minh họa cách xây chính sách. Trong vận hành thật, phải định nghĩa **ai đánh giá severity**, **có chuyển cấp không**, **đồng hồ SLA tính giờ làm việc hay 24×7**, **cách đo khi đổi mức**, và **điều kiện tạm dừng đồng hồ** nếu tổ chức có cơ chế đó. Không tự động “pause” SLA mỗi khi chờ nhà cung cấp, trừ khi điều khoản đã cho phép.

### 6.3. Nguồn chứng cứ cho từng mốc

| Mốc | Nguồn chính | Lỗi thường gặp |
| --- | --- | --- |
| Sự kiện bắt đầu | Network telemetry, host logs, flow/PCAP được phép, báo người dùng | Xác định bắt đầu quá muộn vì chỉ dựa trên ticket |
| Ingest | Collector receive time, log pipeline | Nhầm thời gian ingest với event time |
| Detection | SIEM/NDR alert có đủ tín hiệu, SOC case | Dùng timestamp của rule chạy batch trễ làm mốc bắt đầu |
| Acknowledge | On-call system, ticket event, case assignment | Ticket tự động nhận là analyst đã tiếp nhận |
| Containment | Firewall policy, account/session revoke, endpoint isolation kèm xác nhận | Chỉ ghi “đã ra lệnh”, chưa chứng minh tác động thực |
| Recovery | Synthetic transaction, ứng dụng, người dùng hoặc owner xác nhận | Thiết bị “UP” nhưng dịch vụ không dùng được |
| Closure | Post-incident review, owner approval và action items | Đóng ticket trước khi rủi ro được giao người xử lý |

Phải đồng bộ NTP, timezone và lưu **event time**, **collection time**, **action time** ở mức phù hợp. Nếu nguồn log bị mất, báo rõ độ bất định của thời điểm thay vì ép đủ các mốc cho KPI.

## 7. Chỉ số hiệu lực kiểm soát và chất lượng phát hiện

Đây là nhóm quan trọng nhất để tránh tình huống uptime cao nhưng bảo mật sai.

### 7.1. Kiểm chứng phân đoạn/firewall

Hai chỉ số tương hỗ:

\[
PositivePassRate =
\frac{AllowTestsPassed}{ValidAllowTests}\times100\%.
\]

\[
NegativePassRate =
\frac{DenyTestsWithEvidence}{ValidDenyTests}\times100\%.
\]

**Positive test** chứng minh luồng hợp lệ chạy qua policy và hoàn thành điều kiện ứng dụng. **Negative test** chứng minh luồng **không được phê duyệt** bị chặn ở đúng điểm kiểm soát, có log/counter/trace phù hợp. Nếu một test timeout vì database không lắng nghe, nó không tự chứng minh firewall đã deny.

**Ví dụ:** chạy 20 phép thử được phép, 19 đạt; chạy 30 phép thử bị cấm, 28 có bằng chứng bị chặn; một phép thử thiếu log và một phép thử cho phép trái policy. Khi đó:

- Positive pass rate = **95%**.
- Negative pass rate = **93,33%**.
- Trong hai negative test chưa đạt, cần phân biệt **thực sự vi phạm** với **không đủ bằng chứng**; không mặc định cả hai có cùng nguyên nhân.

Không nên gộp hai tỷ lệ vào một số duy nhất khi yêu cầu bảo mật là bắt buộc. Một hệ thống cho tất cả traffic đi qua có thể đạt positive pass rate 100% nhưng thất bại hoàn toàn ở negative test.

### 7.2. Telemetry health và coverage

**Log source coverage** có thể định nghĩa:

\[
Coverage =
\frac{\text{Nguồn bắt buộc gửi đủ dữ liệu trong kỳ}}
{\text{Tổng nguồn bắt buộc trong phạm vi}}\times100\%.
\]

Nhưng một thiết bị gửi **một log duy nhất** không có nghĩa nó đã gửi **đầy đủ các sự kiện cần thiết**. Nên tách:

- **Source enrollment:** đã đăng ký đúng nguồn và owner hay chưa.
- **Source freshness:** còn phát sinh log trong ngưỡng phù hợp với hoạt động của nguồn hay không.
- **Field completeness:** có timestamp, src/dst, action, rule ID, asset/user/context cần thiết hay không.
- **Pipeline latency:** event time tới thời điểm log được ingest/searchable.
- **Sensor/path coverage:** IDS/IPS/NDR có thực sự nhìn thấy luồng trọng yếu, hay chỉ có agent chạy?
- **Retention và truy vấn được:** dữ liệu có thể truy xuất khi điều tra trong thời hạn đã phê duyệt không?

Nguồn chỉ phát log theo sự kiện cần thêm **heartbeat hoặc active test**; không có log mới không tự chứng minh hệ thống lỗi, cũng không chứng minh nó còn hoạt động.

### 7.3. Detection coverage, precision và chất lượng triage

Trong một tập **test case đã biết** (purple team/attack simulation được phép):

\[
TestDetectionCoverage =
\frac{\text{Case thử hợp lệ tạo phát hiện đúng}}
{\text{Tổng case thử hợp lệ có yêu cầu phát hiện}}\times100\%.
\]

Chỉ số này **không phải true recall trên mọi cuộc tấn công ngoài đời**, vì mẫu kiểm thử chưa bao phủ tất cả hành vi. Đồng thời phải ghi số case được chạy, phạm vi TTP, phiên bản rule, môi trường và các nguồn telemetry.

Đối với cảnh báo đã được triage và gắn nhãn:

\[
AlertPrecision =
\frac{\text{Cảnh báo xác nhận đúng}}
{\text{Tất cả cảnh báo đã phân loại được}}\times100\%.
\]

Định nghĩa **đúng** phải dựa trên tiêu chí nội bộ (cảnh báo chính xác một hành vi cần chú ý, không nhất thiết đã là sự cố nghiêm trọng). Một loạt cảnh báo chưa triage không được tự coi là false positive hoặc true positive; cần báo **tỷ lệ chưa phân loại** song song.

Quan sát bổ sung: tỷ lệ alert trùng, tỷ lệ alert có đủ ngữ cảnh, độ trễ triage, số case quá tải trên mỗi analyst và mức độ hữu ích của các rule. Chỉ đo “số lượng cảnh báo càng nhiều càng tốt” dễ dẫn đến nhiễu và làm giảm khả năng xử lý.

### 7.4. Đo kết quả chặn và ngăn ngừa

Không nên dùng trực tiếp **số kết nối bị firewall chặn** hoặc **số lượng IDS alerts** làm KPI “đã ngăn được bao nhiêu cuộc tấn công”. Một deny có thể đến từ nhầm cấu hình hoặc ứng dụng lỗi; một IDS alert có thể chỉ là quan sát, không chặn. Chỉ kết luận hiệu lực khi có bằng chứng theo **test có kiểm soát, incident investigation hoặc review policy**.

## 8. Chỉ số quản trị lỗ hổng, firmware, ngoại lệ và thay đổi

### 8.1. Lỗ hổng và phiên bản thiết bị

Chỉ số có thể gồm:

- **Inventory coverage:** tỷ lệ thiết bị mạng thuộc phạm vi được xác minh tồn tại và có owner.
- **Firmware evidence freshness:** tỷ lệ thiết bị có running version được thu thập trong kỳ yêu cầu.
- **Exposure validation:** tỷ lệ advisory áp dụng đã được đánh giá theo vendor/model/version/feature, không chỉ match CVE theo tên.
- **Remediation within target:** tỷ lệ hạng mục lỗ hổng xử lý đúng hạn trên tập hạng mục đủ điều kiện và **đã kiểm chứng khắc phục**.
- **Overdue high-risk exposure:** số hoặc tỷ lệ điểm phơi lộ nghiêm trọng quá hạn, có chủ sở hữu và biện pháp bù trừ.
- **Unsupported assets:** số thiết bị hết hỗ trợ bảo mật, cần phân biệt nguồn lifecycle và tình trạng đã xác minh.

Không tính “đã lên lịch nâng cấp” hoặc “đã tải image” là đã sửa. Với firewall HA/stack, cần xác minh **phiên bản đang chạy của từng node/member** sau thay đổi.

### 8.2. Quản lý ngoại lệ firewall

Một ngoại lệ tốt cần ID, lý do, owner, source/destination, port/protocol, zone, phê duyệt, thời điểm có hiệu lực, expiry/review và test. Các KPI hữu ích:

- **Exception completeness:** ngoại lệ có đủ metadata bắt buộc / toàn bộ ngoại lệ đang hiệu lực.
- **Expired active exceptions:** số ngoại lệ đã quá hạn nhưng rule còn hiệu lực; số này nên được ưu tiên đưa về **0**, cùng cơ chế escalations.
- **Exception recertification:** tỷ lệ ngoại lệ được chủ dịch vụ xác nhận còn cần và kiểm thử lại đúng hạn.
- **Overly broad rule review:** số rule có *any/any*, service rộng hoặc đối tượng không rõ được rà soát và có quyết định.

Rule có **0 hit** chưa chắc có thể xóa ngay vì có thể chỉ phục vụ kỳ backup hiếm gặp; cần xác minh chu kỳ nghiệp vụ, thời gian reset counter và kế hoạch rollback.

### 8.3. Chỉ số thay đổi cấu hình

| Chỉ số | Định nghĩa gợi ý | Cách dùng |
| --- | --- | --- |
| Change success rate | Thay đổi hoàn thành tiêu chí nghiệp vụ và bảo mật, không phải rollback ngoài kế hoạch / thay đổi đã triển khai | Theo dõi chất lượng review, triển khai và test |
| Failed change rate | Thay đổi gây sự cố/vi phạm tiêu chí nghiệm thu / thay đổi có thể đo | Tìm nhóm thay đổi rủi ro, không đổ lỗi cá nhân |
| Emergency change share | Thay đổi khẩn / tổng thay đổi trong kỳ | Phát hiện thiếu dự báo, rủi ro hoặc backlog |
| Unauthorized change count | Thay đổi trên runtime không khớp nguồn phê duyệt và không có ngoại lệ hợp lệ | Ưu tiên xác minh và xử lý config drift |
| Post-change verification rate | Thay đổi có readback runtime và test dương/âm phù hợp / thay đổi cần xác minh | Chống trạng thái “deploy xong” nhưng control chưa có hiệu lực |
| Rollback readiness | Các loại thay đổi quan trọng có phương án và thực hành rollback hợp lệ | Đánh giá khả năng phục hồi, không chỉ có tài liệu |

Không nên biến KPI thành động lực **né nâng cấp bảo mật** để giảm số lần failed change. Cần nhìn cùng tốc độ giảm exposure, error budget và kết quả kiểm thử.

## 9. Thiết kế SLI đúng: nguồn, mẫu số và chất lượng đo

Một SLI rõ ràng nên là **specification** có phiên bản, gồm:

| Trường | Ý nghĩa |
| --- | --- |
| **metric_id / name** | Mã và tên không mơ hồ |
| **service_id / scope** | Dịch vụ, site, region, user class và điểm thực thi thuộc phạm vi |
| **intent** | Câu hỏi chỉ số muốn trả lời |
| **numerator / denominator** | Điều kiện nào được tính; trường hợp nào loại khỏi mẫu |
| **unit / aggregation** | Phút, %, seconds, p95, số lượng; tính theo site hay toàn dịch vụ |
| **measurement method** | Synthetic probe, log, metrics, test case, audit, người xác minh |
| **source of truth** | Hệ thống dữ liệu chính và nguồn bổ sung để đối chiếu |
| **sampling & freshness** | Tần suất đo, độ trễ mong đợi và quy tắc dữ liệu thiếu |
| **threshold & window** | Ngưỡng, khoảng thời gian, timezone, business-hours/24×7 |
| **owner & escalation** | Người chịu trách nhiệm khi vi phạm, liên hệ và mức ưu tiên |
| **exclusions** | Các điều kiện loại trừ đã phê duyệt từ trước, có chứng cứ |
| **evidence / version** | Query/dashboard version, ticket, quyền truy cập, thời hạn lưu |

### 9.1. Metric registry mẫu

Đây là dữ liệu **minh họa**, không phải hợp đồng SLA thật hay cấu hình hoàn chỉnh cho công cụ monitoring:

~~~yaml
metric_id: NETSEC-SLI-REMOTE-ACCESS-001
service_id: remote-access-critical-app
owner_team: network-security-operations
metric_type: SLI
description: "Tỷ lệ phút dịch vụ truy cập từ xa khả dụng"
scope:
  sites: ["site-a", "site-b"]
  user_class: "synthetic-authorized-user"
  application: "critical-app"
  measurement_timezone: "UTC"
  service_hours: "24x7"
measurement:
  method: synthetic_end_to_end_transaction
  required_steps:
    - vpn_or_ztna_connect
    - permitted_identity_authentication
    - dns_resolution
    - tls_and_application_healthcheck
  aggregation: "eligible minutes per site; publish each site separately"
  missing_data_policy: "mark unknown; investigate measurement fault"
  probe_interval_seconds: 60
objective:
  target_availability_percent: 99.95
  window: "rolling 30 days"
  allowed_exclusions: "only preapproved, evidence-backed SLA exclusions"
response:
  alert_before_error_budget_exhausted: true
  escalation_owner: netsec-oncall
evidence:
  source_system: approved-monitoring-platform
  query_version: "v1"
  retention_policy: org-approved
~~~

Ví dụ này chọn **xuất SLI riêng cho từng site**, chưa quyết định cách tổng hợp thành một SLA duy nhất. Nếu hợp đồng yêu cầu tổng hợp, phải quy định rõ trọng số, đối tượng khách hàng và cách xử lý sự cố đồng thời giữa các site. Không đơn giản lấy trung bình phần trăm của hai site có quy mô khác nhau mà không có lý do.

### 9.2. Ví dụ tính toán ngắn bằng Python

Đoạn code thuần thư viện chuẩn minh họa **phép tính số học**, không tự động xác định downtime từ log thực:

~~~python
from decimal import Decimal

eligible_minutes = Decimal("43200")
unavailable_minutes = Decimal("18")
slo_percent = Decimal("99.95")

assert eligible_minutes > 0
assert Decimal("0") <= unavailable_minutes <= eligible_minutes
assert Decimal("0") < slo_percent <= Decimal("100")

availability = (
    (eligible_minutes - unavailable_minutes)
    / eligible_minutes
    * Decimal("100")
)
error_budget = eligible_minutes * (
    Decimal("1") - slo_percent / Decimal("100")
)
budget_used_percent = unavailable_minutes / error_budget * Decimal("100")

print(f"Availability: {availability:.4f}%")
print(f"Error budget: {error_budget} phút")
print(f"Budget đã dùng: {budget_used_percent:.2f}%")
print("SLO đạt:", availability >= slo_percent)
~~~

Với số liệu trên, mã cho kết quả xấp xỉ **99,9583%**, error budget **21,60000 phút**, đã dùng **83,33%** và SLO đạt. Trong hệ thống thật, việc xác định phút lỗi, phút chưa biết, các lần probe lặp và điều kiện loại trừ thường phức tạp hơn công thức này.

### 9.3. Những trường hợp làm sai số liệu

- **Mẫu số không rõ:** tổng số alert có bao gồm alert chưa triage? Tổng tài sản có bao gồm node HA đang ngủ và thiết bị unmanaged?
- **Dữ liệu thiếu thành dữ liệu tốt:** log collector lỗi và dashboard lại hiển thị “0 incident”.
- **Trộn nguồn không tương đương:** byte/flow của exporter khác nhau, timestamp khác timezone, trạng thái allow khác định nghĩa.
- **Mất context:** giá trị uptime thiết bị không cho thấy default deny đang được enforce.
- **Nghiệp vụ theo lịch:** downtime trong giờ hệ thống không phục vụ có thể cần quy tắc riêng đã phê duyệt.
- **Thiết bị có nhiều service:** một lỗi có thể ảnh hưởng nhiều dịch vụ hoặc không làm hỏng dịch vụ nào nhờ HA.
- **Phiên và hành động không đối chiếu:** ticket đã “resolved” nhưng synthetic test chưa phục hồi, hoặc containment command chưa có hiệu lực.
- **Phân bố bị che:** trung bình TTD đẹp nhưng một số case critical bị phát hiện quá trễ.

Nên phân lớp dữ liệu thành **raw events → normalized events → metric calculations → dashboard/report** và giữ khả năng truy ngược đến event ID, nguồn và phiên bản quy tắc.

## 10. Dashboard vận hành: đi từ dịch vụ tới nguyên nhân

Một dashboard lãnh đạo và dashboard on-call có thể dùng **cùng nguồn đo**, nhưng mục đích khác:

| Tầng báo cáo | Người dùng | Nội dung trọng tâm |
| --- | --- | --- |
| **Executive / Service review** | Owner dịch vụ, lãnh đạo, risk/compliance | SLO/SLA đạt hay không, tác động người dùng, risk exceptions, xu hướng, quyết định cần hỗ trợ |
| **Operational health** | NetSecOps, NetOps, CloudOps | Availability theo site, error budget, VPN/DNS health, HA, queue, config drift, thay đổi gần nhất |
| **Security effectiveness** | SOC, Detection Engineering, Architecture | Detection tests, nguồn telemetry mất, negative test failures, false positive, xử lý exposure |
| **Incident workspace** | On-call/Incident commander | Timeline, asset/service phụ thuộc, log, owner, next action, status và escalation |

### 10.1. Thiết kế dashboard không tạo hiểu nhầm

- Hiển thị **giá trị quan sát + mục tiêu + khoảng đo + phạm vi** cùng một chỗ.
- Đặt **unknown / data gap** thành trạng thái riêng, không đổi thành xanh hoặc đỏ tùy tiện.
- Có drill-down từ SLI dịch vụ tới site, giờ, thành phần, thay đổi gần nhất và raw evidence.
- Hiển thị cả **số tuyệt đối và tỷ lệ**: 100% pass trên 2 test khác 99% pass trên 10.000 test.
- Phân biệt **sự kiện và cảnh báo**, **đã phát hiện và đã phản ứng**, **đã triển khai và đã verify**.
- Kèm chú thích phiên bản định nghĩa metric khi thay đổi cách đo để người đọc không so sai hai giai đoạn.
- Đánh dấu **rủi ro cao còn tồn tại** ngay cả khi uptime/SLO đạt, ví dụ sai phân đoạn hoặc mất logging của vùng quan trọng.

### 10.2. Nhịp vận hành đề xuất

~~~mermaid
flowchart TD
    A["Telemetry và synthetic tests liên tục"] --> B["On-call phát hiện sai lệch và xử lý"]
    B --> C["Daily: kiểm tra health, data gaps, exceptions"]
    C --> D["Weekly: review incident, detection, changes, backlog"]
    D --> E["Monthly: SLO/SLA và rủi ro, kế hoạch cải tiến"]
    E --> F["Quarterly hoặc khi thay đổi lớn: xem lại metric và kiến trúc"]
    F --> A
~~~

Tần suất trên là gợi ý. Vùng mạng trọng yếu có thể cần review thường xuyên hơn; môi trường nhỏ có thể hợp nhất các buổi. Không thay đổi SLA/SLI ngay giữa kỳ chỉ để làm giảm một vi phạm đã phát sinh.

## 11. Khi SLA hoặc SLO có nguy cơ không đạt

### 11.1. Error budget là tín hiệu điều hành

Khi error budget giảm nhanh, nhóm vận hành cần xét:

1. **Đây có phải lỗi đo không?** Probe, collector, DNS test hoặc định nghĩa availability có thay đổi?
2. **Lỗi tập trung ở đâu?** Một site, một nhóm user, một firewall HA member, một IdP hoặc đường cloud interconnect?
3. **Có thay đổi nào gần đây?** Policy, route, DNS, certificate, firmware, IdP, controller, HA?
4. **Rủi ro bảo mật có tăng không?** Có cần đóng một đường không hợp lệ dù ảnh hưởng một phần truy cập?
5. **Hành động ưu tiên là gì?** Khôi phục, rollback, tạm dừng rollout, tăng quan sát, thông báo khách hàng hoặc kích hoạt incident management?

Không nên dùng error budget làm lý do **bỏ qua bản vá bảo mật bắt buộc** hoặc duy trì rule quá rộng. Quyết định phải kết hợp **security risk, reliability, tác động khách hàng và tính cấp thiết**, được người có thẩm quyền ghi nhận.

### 11.2. Quy trình xử lý vi phạm SLA

~~~text
1. Phát hiện SLI vượt ngưỡng hoặc dự báo sẽ vượt trong kỳ.
2. Xác minh chất lượng dữ liệu, scope và điều kiện tính theo SLA.
3. Liên kết incident ID, thời gian, dịch vụ và nhóm bị ảnh hưởng.
4. Kích hoạt escalation theo severity và giờ hỗ trợ đã cam kết.
5. Khôi phục dịch vụ/kiểm soát, bảo toàn log và kiểm thử sau thay đổi.
6. Tính kết quả chính thức theo định nghĩa metric có version.
7. Thông báo cho chủ dịch vụ; thực hiện nghĩa vụ SLA tương ứng.
8. Post-incident review: nguyên nhân, gaps phát hiện, biện pháp sửa.
9. Giao action item, owner, hạn và test lại để chứng minh cải thiện.
~~~

Trong một sự cố nghiêm trọng, **khôi phục kết nối nhanh nhất** không đồng nghĩa mở lại toàn bộ firewall hoặc tắt IDS/IPS một cách không kiểm soát. Phương án tạm phải bảo toàn ranh giới an toàn tối thiểu và được phê duyệt theo quy trình ứng phó.

## 12. Ca thực hành: VPN đạt uptime nhưng monitoring mất log

**Bối cảnh giả lập.** Doanh nghiệp có dịch vụ truy cập ứng dụng qua VPN/ZTNA với SLO availability 99,95% trong 30 ngày, đo end-to-end. Firewall biên hoạt động HA. IDS/NDR và SIEM nhận log từ VPN gateway, IdP và firewall. Trong kỳ:

- Synthetic probe xác minh 18 phút dịch vụ không khả dụng.
- Một collector ngừng nhận firewall deny logs của vùng DATA trong 4 giờ, nhưng cảnh báo mất log không hoạt động.
- SOC phát hiện một sự kiện truy cập trái policy sau 35 phút dựa trên log từ nguồn khác.
- Một thay đổi rule firewall đã được deploy nhưng chưa có negative test từ VLAN người dùng.

### 12.1. Đánh giá theo các lớp

| Mục | Quan sát | Kết luận phù hợp |
| --- | --- | --- |
| Service availability | 18 / 43.200 phút không khả dụng | **Đạt** mục tiêu 99,95% của ví dụ, đã tiêu thụ ~83,33% error budget |
| Telemetry freshness | Một nguồn bắt buộc mất deny logs trong 4 giờ | **Không đạt yêu cầu quan sát** nếu ngưỡng cho phép ngắn hơn; cần đo cụ thể |
| Detection latency | Một sự kiện được phát hiện sau 35 phút | Cần so ngưỡng theo severity và độ tin cậy event time; không đủ dữ liệu để gọi MTTR |
| Policy verification | Rule đã triển khai nhưng thiếu negative test | **Chưa xác nhận hiệu lực kiểm soát**; trạng thái cần là pending verification |
| Chất lượng sự cố | SOC dựa vào nguồn log khác mới phát hiện | Có khả năng dự phòng tín hiệu, đồng thời lộ khoảng trống telemetry |

**Không kết luận “NetSecOps đạt toàn bộ SLA nên mạng an toàn”**. Đạt availability chỉ mô tả một khía cạnh dịch vụ; mất log và thiếu kiểm thử âm là rủi ro khác có thể đòi hỏi escalation ngay dù SLA uptime chưa vi phạm.

### 12.2. Kế hoạch khắc phục

1. Kiểm tra nguyên nhân synthetic probe ghi nhận 18 phút không khả dụng; xác định lỗi dịch vụ, probe hay hệ thống phụ thuộc.
2. Khôi phục log forwarding của firewall và thử các sự kiện được phê duyệt để xác minh event time, field, rule ID và pipeline latency.
3. Thiết lập **log source heartbeat/coverage** phù hợp cho nguồn ít phát sinh event, kèm cảnh báo mất tín hiệu.
4. Chạy positive/negative tests từ đúng nguồn/vùng để chứng minh rule firewall đang thực thi; kiểm tra IPv6, NAT và HA nếu áp dụng.
5. Rà soát TTD/TTA/containment của incident, phân biệt mốc đo và cải tiến correlation/enrichment nếu thiếu.
6. Cập nhật SLI registry và dashboard để hiển thị **service availability, telemetry health và policy verification** cạnh nhau, không gộp sai.
7. Giao owner, hạn hoàn tất và kế hoạch test lại; báo cáo risk exception nếu phải chấp nhận tạm thời thiếu telemetry.

### 12.3. Bảng báo cáo mẫu

~~~text
Reporting period: 30-day example window, UTC
Service: remote-access-critical-app
Owner: Network Security Operations
Target: availability >= 99.95%
Eligible minutes: 43200
Verified unavailable minutes: 18
Observed availability: 99.9583% (PASS)
Error budget: 21.6 minutes; consumed: 18 minutes
Evidence: synthetic transaction records + incident timeline

Telemetry risk:
  - source: DATA-zone firewall deny log
  - gap: 4 hours; root cause under investigation
  - control result: gap detected late, corrective action opened

Policy assurance:
  - post-change negative test: NOT PERFORMED
  - status: PENDING_VERIFICATION (not PASS)

Incident performance:
  - one observed TTD: 35 minutes
  - threshold/incident sample: validate before SLA judgment

Actions:
  - restore log pipeline and prove field completeness
  - run authorized firewall negative tests
  - add missing-signal alarm and retest
  - assign owners, due dates and review evidence
~~~

## 13. Sai lầm thường gặp và cách tránh

1. **SLA = uptime của thiết bị:** thiết bị khỏe vẫn có thể chặn sai hoặc cho traffic trái policy. Đo theo luồng và giao dịch của dịch vụ.
2. **SLO là điều khoản bắt buộc với khách hàng:** nhiều SLO chỉ là mục tiêu nội bộ. Phân biệt rõ hợp đồng SLA và target vận hành.
3. **Không có alert tức không có sự cố:** có thể đang mất nguồn log, rule không kích hoạt, sensor không nhìn thấy traffic. Đo telemetry health độc lập.
4. **Tính trung bình các tỷ lệ không cùng mẫu số:** gây sai số khi site có lượng người dùng/traffic khác nhau. Xác định trọng số và cách tổng hợp.
5. **Tự loại downtime bảo trì sau khi kỳ đo kết thúc:** làm mất tính tin cậy. Quy tắc loại trừ phải được định nghĩa và phê duyệt trước.
6. **Chỉ thống kê sự cố đã được phát hiện:** đánh giá thấp thời gian phát hiện thực khi có sự cố bị bỏ sót. Dùng purple-team/test và đối chiếu nhiều nguồn để thấy khoảng trống.
7. **MTTR không có định nghĩa:** mean repair, recover, resolve hoặc respond có mốc khác nhau. Ghi rõ tên, bắt đầu/kết thúc và phạm vi.
8. **Tỷ lệ false positive tính trên alert chưa triage:** dẫn tới kết luận sai. Báo riêng backlog chưa phân loại và tập có nhãn.
9. **Đếm số deny như số cuộc tấn công bị chặn:** không xác định ý định hoặc chất lượng policy. Kiểm chứng bằng case/test có chứng cứ.
10. **“Đã deploy” bằng “đã kiểm chứng”:** control có thể không có hiệu lực ở node HA hoặc đường IPv6. Cần readback và positive/negative testing.
11. **Chỉ dùng chỉ số trung bình:** che p95/p99 và các sự cố nghiêm trọng. Hiển thị cả phân bố, cỡ mẫu và dữ liệu thiếu.
12. **KPI phạt nhân sự khi số sự cố tăng:** tạo động lực giảm ghi nhận. Đo chất lượng phát hiện, cải tiến và hành động, không khuyến khích che giấu.
13. **Thay đổi định nghĩa âm thầm:** hai tháng không còn so sánh được. Version metric, lưu lịch sử và chú thích thay đổi.
14. **Thiếu owner và hành động sau báo cáo:** chỉ số đỏ lặp lại nhưng không ai xử lý. Mỗi gap có trách nhiệm, hạn, bằng chứng retest.

## 14. Checklist triển khai và tự kiểm tra

| Câu hỏi | Có / Chưa / Không áp dụng |
| --- | --- |
| Đã lập service catalog với owner, scope, criticality, giờ hỗ trợ và người dùng? | |
| Đã phân biệt SLA, SLO, SLI, OLA, RTO và RPO theo nghĩa tổ chức sử dụng? | |
| Mỗi SLI có tử số, mẫu số, kỳ đo, nguồn dữ liệu, quy tắc thiếu dữ liệu và version? | |
| Availability được đo end-to-end ở site/nhóm người dùng đại diện, không chỉ node uptime? | |
| Có cả positive và negative tests cho các chính sách phân đoạn quan trọng? | |
| Có đo độ phủ và độ mới telemetry, tình trạng sensor và chất lượng field? | |
| Có phân biệt event, alert, analyst acknowledgement, containment, recovery và closure? | |
| Detection metrics có cỡ mẫu, phạm vi TTP và tỷ lệ chưa phân loại rõ ràng? | |
| Inventory, firmware, ngoại lệ và change verification có KPI gắn với risk không? | |
| Dashboard hiển thị unknown/data gap và không tự tính khoảng thiếu là healthy? | |
| SLA vi phạm có escalation, thông báo, evidence, PIR và chủ action item? | |
| Có review và điều chỉnh SLI/SLO khi kiến trúc, công nghệ hoặc nhu cầu thay đổi? | |

### Câu hỏi luyện tập

1. SLA khác SLO và SLI như thế nào? Vì sao một hệ thống có thể đạt uptime nhưng chưa đạt yêu cầu bảo mật?
2. Với mục tiêu 99,95% trong 30 ngày 24×7, error budget bao nhiêu phút? Nếu downtime 18 phút, đã sử dụng bao nhiêu phần trăm?
3. Tại sao không nên tính khoảng **mất telemetry** là phút dịch vụ hoạt động bình thường?
4. Một collector nhận một dòng log mới mỗi ngày; vì sao chưa đủ để nói telemetry coverage đạt?
5. Nếu SIEM tạo alert lúc 10:04 và analyst acknowledge 10:09 nhưng sự kiện bắt đầu 10:00, TTD và TTA bằng bao nhiêu theo định nghĩa bài?
6. Khi một policy firewall được triển khai nhưng chưa có negative test, trạng thái kiểm soát nên được báo cáo như thế nào?
7. Detection coverage trên 20 test case đã chọn có đồng nghĩa recall của mọi cuộc tấn công trong sản xuất không?
8. Vì sao tỷ lệ xử lý lỗ hổng phải dựa trên **đã xác minh khắc phục** thay vì số ticket đóng?
9. SLA uptime vẫn đạt trong khi một vùng mất IDS/IPS telemetry và xuất hiện ngoại lệ quá hạn; báo cáo lãnh đạo nên tách thông tin gì?
10. Nêu ba biện pháp tránh “gaming metrics” trong vận hành network security.

**Gợi ý trả lời:** (1) SLA là thỏa thuận, SLO là mục tiêu, SLI là phép đo; uptime không chứng minh hiệu lực policy. (2) 21,6 phút và khoảng 83,33%. (3) Thiếu quan sát chưa chứng minh healthy; cần trạng thái unknown và nguồn đối chiếu. (4) Có thể thiếu loại event và field trọng yếu; cần heartbeat/active test và đánh giá chất lượng. (5) TTD 4 phút, TTA 5 phút. (6) Pending verification, có owner và hạn kiểm chứng. (7) Không, đó chỉ là độ phủ trên tập kiểm thử. (8) Ticket đóng không đảm bảo phiên bản đang chạy/rule đã thay đổi đúng. (9) Tách availability, telemetry/detection gaps và exception risk. (10) Cố định định nghĩa, đối chiếu bằng chứng độc lập, báo đủ unknown và phân bố, kết hợp chỉ số kết quả với chất lượng kiểm soát.

**Ghi nhớ:** Một chương trình **Network Security Operation** trưởng thành không chỉ hỏi *“dịch vụ có chạy không?”* mà còn hỏi *“đúng người có vào được không, người không có quyền có bị chặn không, chúng ta có nhìn thấy rủi ro không và phản ứng có hiệu quả không?”*. SLA/SLO và chỉ số kỹ thuật chỉ đáng tin khi được định nghĩa rõ phạm vi, thu từ nguồn chứng cứ chất lượng, phân biệt trạng thái chưa biết và dẫn tới hành động cải tiến thực tế.
