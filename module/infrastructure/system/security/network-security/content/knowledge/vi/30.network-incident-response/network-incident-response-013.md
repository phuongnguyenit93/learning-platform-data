# Diễn tập network incident response

## 1. Diễn tập để kiểm chứng khả năng ứng phó sự cố mạng

**Diễn tập network incident response** là hoạt động tạo ra một tình huống sự cố có kiểm soát để kiểm chứng con người, quy trình và công cụ có phối hợp hiệu quả từ lúc xuất hiện dấu hiệu bất thường đến khi dịch vụ an toàn trở lại hay không. Mục tiêu không chỉ là tìm đúng địa chỉ IP đáng ngờ: đội ứng phó cần xác định mức độ ảnh hưởng, thu thập chứng cứ có thể kiểm tra, ra quyết định cô lập phù hợp, phối hợp truyền thông và chứng minh biện pháp khắc phục thực sự có hiệu lực.

Đối với module **SECURITY_NETWORK_SECURITY**, bài học kết nối kiến thức phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, bảo vệ mạng không dây và hạ tầng đám mây với hoạt động ứng phó thực tế. Việc giám sát lưu lượng, mô hình hóa mối đe dọa, phân tích cảnh báo và khôi phục dịch vụ đều phải được kiểm chứng trong điều kiện có áp lực thời gian và có nhiều nhóm cùng tham gia.

Sau bài học, người học có thể:

- Phân biệt diễn tập thảo luận (tabletop), diễn tập thao tác trên hệ thống giả lập (functional exercise) và diễn tập kỹ thuật trong lab.
- Viết kế hoạch diễn tập với phạm vi, mục tiêu, giả định, quyền hạn, điều kiện dừng và tiêu chí đánh giá rõ ràng.
- Phối hợp SOC, NOC, quản trị mạng, vận hành hệ thống, IR/DFIR, quản lý sự cố và các bên liên quan.
- Điều tra tín hiệu từ DNS, NetFlow/IPFIX, firewall, IDS/IPS, DHCP, VPN, IAM, EDR và gói tin PCAP; kiểm tra giả thuyết thay vì suy đoán từ một cảnh báo.
- Thực hành quy trình phát hiện → phân loại → khoanh vùng → ngăn chặn → loại bỏ nguyên nhân → khôi phục → rút kinh nghiệm.
- Đo tiến độ bằng mốc thời gian, chất lượng quyết định, tính toàn vẹn chứng cứ và kết quả khôi phục.

### 1.1. Chọn loại diễn tập

| Hình thức | Cách thực hiện | Phù hợp để kiểm tra | Giới hạn |
|---|---|---|---|
| **Tabletop** | Điều phối viên phát thông tin tình huống, thành viên thảo luận quyết định | Vai trò, kênh liên lạc, quyền phê duyệt, quy trình leo thang | Chưa chứng minh được thao tác kỹ thuật thực tế |
| **Functional** | Thành viên xử lý alert, truy vấn dữ liệu mẫu, mở ticket và thực hiện thay đổi giả lập | Chuyển giao giữa nhóm, tốc độ xử lý, cách ghi nhận quyết định | Một số kết quả kỹ thuật được mô phỏng |
| **Technical lab** | Dùng VM, mạng ảo, log, PCAP và công cụ phòng thủ trong môi trường cô lập | Chất lượng phát hiện, điều tra, thay đổi firewall, xác minh phục hồi | Cần chuẩn bị hạ tầng và dữ liệu thực hành |
| **Diễn tập phối hợp đa nhóm** | Kết hợp tabletop, functional và các bước lab được cho phép | Xử lý áp lực vận hành, truyền thông, ưu tiên dịch vụ | Khó tổ chức hơn; cần người điều phối và giám sát độc lập |

Có thể bắt đầu bằng tabletop 60–90 phút, sau đó chuyển các bước nhiều lỗi thành bài kỹ thuật trong lab. Mọi kịch bản phải phân biệt rõ **hành động thực tế**, **hành động được mô phỏng** và **kết quả do điều phối viên cung cấp**.

## 2. Khung tổ chức và quy tắc an toàn

### 2.1. Mục tiêu, phạm vi và điều kiện dừng

Ví dụ mục tiêu đo được cho một phiên 120 phút:

1. SOC xác nhận, phân loại và thông báo cảnh báo DNS bất thường trong **15 phút từ khi nhận alert**.
2. Nhóm điều tra nối được IP, thiết bị, người hoặc dịch vụ liên quan với bằng chứng từ ít nhất **hai nguồn độc lập**.
3. Incident Commander phê duyệt biện pháp cô lập có phương án hoàn tác; kỹ thuật viên xác minh lưu lượng rủi ro đã dừng.
4. NOC và nhóm ứng dụng chứng minh dịch vụ thiết yếu vẫn hoạt động hoặc đưa ra quyết định chấp nhận gián đoạn có ghi nhận.
5. Nhóm hoàn thành timeline, nhật ký quyết định, báo cáo tình huống và danh sách hành động cải tiến có người phụ trách.

Các thời hạn trên là **SLO minh họa của buổi diễn tập**, không phải ngưỡng bắt buộc cho mọi tổ chức. Phải điều chỉnh theo mức độ nghiêm trọng, độ phủ giám sát, mức quan trọng của dịch vụ và nguồn lực.

Bản kế hoạch (EX-PLAN) cần ghi cụ thể:

| Thành phần | Cần định nghĩa |
|---|---|
| Phạm vi tài sản | Subnet, VLAN, workload, tài khoản và dịch vụ được đưa vào giả lập; ranh giới với production |
| Thời gian | Ngày, múi giờ, thời lượng, mốc phát tình huống, thời điểm tổng kết |
| Dữ liệu | Log, alert, PCAP, sơ đồ và tài khoản thử nghiệm; chính sách lưu trữ và xử lý dữ liệu |
| Quyền thay đổi | Ai được xem log, thay đổi ACL/firewall, cô lập endpoint, chuyển hướng DNS, khôi phục |
| Phụ thuộc | Ứng dụng quan trọng, DNS, DHCP, VPN, NAT, proxy, cloud, nhà cung cấp và đầu mối liên lạc |
| Quy tắc đánh dấu | Ticket, cảnh báo và thông báo đều có tiền tố **[EXERCISE]** |
| Điều kiện dừng | Có ảnh hưởng ngoài phạm vi, phát hiện sự cố thật, sai lệch dữ liệu, mất khả năng hoàn tác |
| Phục hồi lab | Snapshot/cấu hình trước diễn tập, người chịu trách nhiệm khôi phục, kiểm tra sau khi dừng |

**Không triển khai payload gây hại, đánh sập dịch vụ, khai thác lỗ hổng hoặc truyền dữ liệu nhạy cảm ra ngoài.** Nếu buổi diễn tập liên quan hệ thống sản xuất, chỉ thao tác trong phạm vi đã được vận hành phê duyệt và dùng dữ liệu/alert mô phỏng khi có thể. Có một lệnh dừng rõ ràng, chẳng hạn **EXERCISE STOP**, và một kênh riêng cho sự cố thật. Người điều phối dừng ngay các hoạt động giả lập nếu xuất hiện dấu hiệu sự cố thật.

### 2.2. Ai làm gì?

| Vai trò | Trách nhiệm trong diễn tập | Sản phẩm/bằng chứng |
|---|---|---|
| **Exercise Director / Controller** | Thiết kế kịch bản, phát tình huống theo lịch, giữ phạm vi và điều kiện dừng | EX-PLAN, các thẻ tình huống (inject), nhật ký điều phối |
| **Incident Commander (IC)** | Ra quyết định ưu tiên, xác nhận mức độ, phê duyệt cô lập và khôi phục, quyết định leo thang | Decision log, các lần phê duyệt, SITREP |
| **SOC / Detection Analyst** | Tiếp nhận cảnh báo, truy vấn telemetry, xây dựng timeline và mức độ tin cậy | Alert/ticket, kết quả truy vấn, giả thuyết điều tra |
| **NOC / Network Security** | Xác thực đường đi lưu lượng, NAT/DHCP/VLAN, triển khai và kiểm tra rule mạng | Flow, firewall change, xác minh trước/sau |
| **System / Cloud / Endpoint Owner** | Xác định chủ tài sản, kiểm tra host/EDR/IAM, xử lý nguyên nhân và phục hồi dịch vụ | Log host, hành động xử lý, kết quả health check |
| **DFIR / Evidence Custodian** | Thu chứng cứ, xác minh hash, quản lý chuỗi bàn giao và phạm vi truy cập | Evidence manifest, biên bản bàn giao |
| **Service Owner / Comms / Legal** | Đánh giá tác động nghiệp vụ, cập nhật bên liên quan, xem xét yêu cầu thông báo khi cần | Đánh giá ảnh hưởng, bản cập nhật, đầu việc tuân thủ |
| **Evaluator / Observer** | Ghi thời điểm, quan sát phối hợp, đối chiếu tiêu chí mà không gợi đáp án | Bảng điểm và nhận xét độc lập |

Ở đội nhỏ, một người có thể kiêm nhiều vai trò, nhưng nên tách **người ra quyết định thay đổi** khỏi **người đánh giá kết quả**. Người điều phối không được tự ý giải đáp bài điều tra trừ khi đó là inject đã định trước.

### 2.3. Vòng đời ứng phó dùng trong diễn tập

~~~mermaid
flowchart LR
    A["Chuẩn bị<br/>Phạm vi, con người, log"] --> B["Phát hiện & phân tích<br/>Alert, kiểm chứng, phân loại"]
    B --> C["Ngăn chặn<br/>Khoanh vùng, cô lập có kiểm soát"]
    C --> D["Xử lý nguyên nhân<br/>Tài khoản, cấu hình, endpoint"]
    D --> E["Khôi phục & giám sát<br/>Kiểm tra dịch vụ, theo dõi tái diễn"]
    E --> F["Đánh giá sau sự cố<br/>Bài học, người phụ trách, hạn xử lý"]
    F --> A
~~~

Thực tế các pha có thể chồng lấp: phải bảo toàn chứng cứ trong khi ngăn chặn, tiếp tục phân tích khi khôi phục, và cập nhật các bên liên quan trong suốt quá trình. Thời điểm bước ngoặt và lý do quyết định quan trọng hơn việc “đánh dấu đã làm” theo thứ tự cứng nhắc.

## 3. Chuẩn bị kịch bản diễn tập có thể chạy lại

Một kịch bản tốt phải mô tả **trạng thái bình thường**, **sự lệch chuẩn**, **điều người chơi biết ở từng thời điểm** và **cách xác minh thành công**.

### 3.1. Bảy bước chuẩn bị

1. **Chọn rủi ro:** ví dụ một máy trong VLAN người dùng phát sinh truy vấn DNS không bình thường và kết nối đến máy chủ ngoài danh sách cho phép.
2. **Xác định tài sản trọng yếu:** thông tin thiết bị, dịch vụ được phép gián đoạn, đường truy cập, chủ sở hữu và hệ thống phụ thuộc.
3. **Vẽ luồng mạng cơ sở:** nguồn, đích, resolver, proxy, firewall, VPN, gateway, NAT và vị trí cảm biến.
4. **Tạo telemetry tổng hợp:** alert có thời điểm, DHCP mapping, DNS log, NetFlow, firewall decision và sự kiện endpoint; thêm một tín hiệu dễ nhầm lẫn để người học phải đối chiếu.
5. **Đặt nhánh quyết định:** cách xác minh false positive, phạm vi cô lập, tình huống chủ dịch vụ phản đối và quyết định khôi phục.
6. **Định nghĩa bằng chứng và đáp án kiểm tra:** mỗi inject có mục đích, hành vi kỳ vọng, điều kiện đạt, tiêu chí an toàn; kết quả ẩn với người chơi.
7. **Chạy thử:** kiểm tra dữ liệu dùng được, tài khoản có quyền đọc cần thiết, đồng bộ thời gian UTC, phương án hoàn tác và điều kiện dừng.

### 3.2. Kiểm tra khả năng quan sát trước buổi diễn tập

| Nguồn | Câu hỏi có thể trả lời | Lưu ý thường bị bỏ qua |
|---|---|---|
| Firewall / NGFW / cloud flow | Lưu lượng được cho phép hay chặn, theo rule nào, ở thời điểm nào? | NAT có thể che giấu IP nội bộ; log bị sampling hoặc thiếu bytes |
| NetFlow/IPFIX | Nguồn/đích/cổng/giao thức/bytes/packets và mức lệch baseline? | Đây là metadata, không chứng minh nội dung truyền đi |
| DNS resolver | Thiết bị nào hỏi tên miền nào, NXDOMAIN và tần suất ra sao? | DNS mã hóa hoặc resolver bên ngoài làm giảm độ nhìn thấy |
| DHCP / IPAM / NAC | IP vào thời điểm đó được cấp cho MAC/port/thiết bị nào? | IP có thể đổi chủ; cần đối chiếu **lease time** |
| VPN / IAM | Danh tính, thời gian xác thực, thiết bị và địa điểm truy cập? | IP tại gateway không luôn xác định duy nhất người dùng |
| IDS/IPS / NDR | Cảnh báo nào xuất hiện, độ tin cậy, signature/behavior nào? | Một signature là tín hiệu điều tra, không phải kết luận |
| EDR / OS / Proxy | Tiến trình, người dùng, đường dẫn, tài khoản và hành động trên host? | Endpoint có thể mất log hoặc không được cài agent |
| NTP / time service | Log giữa các nguồn có cùng chuẩn thời gian? | Lệch đồng hồ có thể đảo thứ tự sự kiện |

Nếu thiếu nguồn dữ liệu, ghi **khoảng trống quan sát** vào báo cáo; không tự điền giả định bằng “bằng chứng” chưa thấy.

## 4. Kịch bản chính: DNS bất thường và lưu lượng đi ra ngoài

### 4.1. Bối cảnh và kiến trúc lab

Tất cả địa chỉ và dữ liệu dưới đây là **giả lập**, dùng cho học tập. Dải 198.51.100.0/24 và 203.0.113.0/24 dành cho tài liệu ví dụ; tên miền có đuôi .example cũng là tên miền minh họa.

- **Client-45:** 10.20.30.45, nằm trong VLAN 30.
- **DNS nội bộ được cho phép:** 10.20.0.53.
- **Resolver bên ngoài giả lập:** 198.51.100.53.
- **Điểm cuối TLS bên ngoài giả lập:** 203.0.113.80:443.
- **Dịch vụ nghiệp vụ:** ứng dụng nội bộ truy cập qua gateway; chủ dịch vụ yêu cầu tránh ngắt toàn VLAN.
- **Dữ liệu thực hành:** bản ghi tổng hợp đã gỡ thông tin cá nhân và PCAP tạo trong lab; không có dữ liệu thật cần trích xuất.

~~~mermaid
flowchart LR
    U["Client-45<br/>10.20.30.45<br/>VLAN 30"] --> SW["Switch / NAC"]
    SW --> FW["Firewall egress<br/>Flow + rule logs"]
    SW --> DNS["DNS nội bộ<br/>10.20.0.53"]
    FW --> EX1["Resolver giả lập<br/>198.51.100.53:53"]
    FW --> EX2["Endpoint giả lập<br/>203.0.113.80:443"]
    SW -. "DHCP / IPAM" .-> SIEM["SIEM / Ticket"]
    FW -. "Flow / firewall logs" .-> SIEM
    DNS -. "DNS logs" .-> SIEM
    U -. "EDR telemetry" .-> SIEM
~~~

**Baseline:** Client-45 chủ yếu hỏi DNS nội bộ, dùng ứng dụng nghiệp vụ qua các đích được cho phép. Bất thường là nhiều truy vấn tên miền dài, lượng NXDOMAIN tăng, có kết nối UDP/53 tới resolver bên ngoài và một phiên TCP/443 có chiều gửi lớn hơn baseline. Các đặc điểm này **không tự động chứng minh đã có DNS tunneling hoặc rò rỉ dữ liệu**. Nhiệm vụ của đội là kiểm tra giả thuyết, xác định mức độ tin cậy và ra quyết định tương xứng.

### 4.2. Bộ dữ liệu giả lập cho người chơi

Mốc giờ dùng **UTC ngày 15-01-2026**. Chuỗi log rút gọn sau đây là dữ liệu diễn tập, không phải dữ liệu từ thiết bị thật.

~~~text
2026-01-15T08:58:40Z DHCP    lease_ip=10.20.30.45 mac=02:00:00:00:30:45 vlan=30 asset=Client-45
2026-01-15T09:00:12Z DNS     src=10.20.30.45 dst=10.20.0.53 qname=portal.lab.example result=NOERROR
2026-01-15T09:03:04Z NDR     src=10.20.30.45 indicator=long_qname_spike nxdomain_ratio=0.78
2026-01-15T09:04:21Z FLOW    src=10.20.30.45 dst=198.51.100.53 proto=UDP dport=53 flows=135 decision=ALLOW
2026-01-15T09:06:11Z FLOW    src=10.20.30.45 dst=203.0.113.80 proto=TCP dport=443 bytes_out=1843200 bytes_in=15781
2026-01-15T09:07:00Z SIEM    alert=EXERCISE-NET-013 severity=HIGH asset=Client-45
2026-01-15T09:11:32Z EDR     asset=Client-45 event=unusual_process_network_activity confidence=medium
~~~

Giá trị nxdomain_ratio và số flow chỉ mang tính minh họa; phải so với baseline và cửa sổ thời gian cụ thể. Dòng EDR chưa chỉ ra tiến trình nào gây ra lưu lượng. Trong quá trình diễn tập, evaluator chỉ cấp chi tiết bổ sung khi người chơi hỏi đúng nguồn hoặc thực hiện bước điều tra tương ứng.

### 4.3. Giả thuyết cần phân biệt

| Giả thuyết | Dữ liệu ủng hộ | Dữ liệu cần kiểm tra trước khi kết luận |
|---|---|---|
| Ứng dụng lỗi hoặc cấu hình resolver sai | DNS truy vấn lỗi nhiều, sử dụng DNS ngoài | Thay đổi cấu hình gần đây, chủ ứng dụng, log thay đổi, mẫu truy vấn |
| Endpoint bị chiếm quyền và gửi dữ liệu ra ngoài | DNS bất thường + kết nối ngoài với bytes_out tăng | Tiến trình/EDR, nội dung được phép quan sát, baseline, đích và định danh asset |
| Dịch vụ hợp lệ sinh truy vấn ngẫu nhiên | Tên miền dài, lượng truy vấn cao | Danh sách dịch vụ đã phê duyệt, chứng cứ từ proxy/app, tính lặp lại |
| Sai lệch telemetry hoặc ánh xạ IP | Log mâu thuẫn hoặc không đủ | Đồng hồ, NAT, DHCP lease, VLAN, packet loss, sampling |

Ghi rõ trong ticket mức độ: **fact** (đã thấy), **hypothesis** (giả thuyết), **unknown** (chưa xác định), **decision** (đã phê duyệt), **next check** (bước kiểm tra tiếp). Không đánh đồng “khả nghi” với “đã xâm nhập”.

## 5. Runbook thực hành trong buổi diễn tập

### Bước 1 — Nhận cảnh báo, lập hồ sơ và xác nhận thời gian

SOC ghi vào ticket: ID, người xử lý, thời điểm nhận UTC, nguồn cảnh báo, chỉ báo, phạm vi nghi ngờ, mức ưu tiên ban đầu và lý do. Kiểm tra cảnh báo có nằm trong chương trình **[EXERCISE]** hay không. Nếu phát hiện sự cố thật, chuyển đúng quy trình sự cố thật và dừng kịch bản giả lập liên quan.

Bước kiểm tra đầu tiên:

1. Xác nhận hệ thống phát cảnh báo và khoảng thời gian log.
2. Đối chiếu DHCP lease tại thời điểm xuất hiện sự kiện; kiểm tra NAT nếu có.
3. Xác nhận asset owner, mức quan trọng của host, dịch vụ đang chạy.
4. Tìm các cảnh báo cùng IP, MAC, user, VLAN, destination hoặc khoảng thời gian.
5. Phân biệt lưu lượng bị **ALLOW** và **DENY**; một rule chặn thành công vẫn tạo log cảnh báo.

Ví dụ câu truy vấn **SQL giả định** cho dữ liệu đã chuẩn hóa, cần điều chỉnh schema theo SIEM thực tế:

~~~sql
SELECT event_time_utc, src_ip, dst_ip, dst_port, protocol,
       action, bytes_out, bytes_in
FROM network_flows
WHERE src_ip = '10.20.30.45'
  AND event_time_utc >= '2026-01-15T08:50:00Z'
  AND event_time_utc <  '2026-01-15T09:20:00Z'
ORDER BY event_time_utc;
~~~

Không lấy một kết quả truy vấn trống làm bằng chứng không có sự cố khi pipeline thu thập log, retention, múi giờ hoặc mapping trường chưa được kiểm tra.

### Bước 2 — Phân tích lưu lượng và xác định mức ảnh hưởng

Điều tra viên lập danh sách IP đích, cổng, protocol, số phiên, lưu lượng ra/vào, kết quả DNS và baseline. Tách câu hỏi “có liên lạc” khỏi “đã chuyển dữ liệu gì”. Dữ liệu NetFlow/IPFIX chỉ cho biết đặc tính kết nối, không cho biết nội dung HTTPS hay DNS đã mã hóa.

Trong **lab được phép**, có thể xác nhận địa chỉ, route và socket từ máy thí nghiệm:

~~~bash
ip -br addr
ip route
ss -tunap
~~~

Để bắt gói tin khi thực sự cần và đã được phép thu thập, dùng filter hẹp, thời gian ngắn, tệp lưu được bảo vệ:

~~~bash
sudo tcpdump -i <IFACE> -n -s 128 -c 500 \
  -w /var/tmp/exercise-net-013.pcap \
  'host 10.20.30.45 and (port 53 or port 443)'
~~~

Ở ví dụ này, **-s 128** giới hạn độ dài gói được lưu nhằm giảm dữ liệu tải; nó cũng có thể khiến thiếu thông tin ứng dụng. Nếu mục tiêu điều tra buộc phải thu đủ gói, cần phê duyệt riêng và đánh giá dữ liệu nhạy cảm. Trong hạ tầng thật, ưu tiên telemetry có sẵn trước khi tạo thêm PCAP. Lọc và phân tích PCAP trong lab bằng công cụ quen thuộc:

~~~bash
tshark -r /var/tmp/exercise-net-013.pcap \
  -Y 'dns && ip.src == 10.20.30.45' \
  -T fields -e frame.time_utc -e ip.src -e dns.qry.name

tshark -r /var/tmp/exercise-net-013.pcap \
  -Y 'ip.addr == 10.20.30.45 && tcp.port == 443' \
  -q -z conv,tcp
~~~

Nếu bản build TShark không có trường hoặc tùy chọn giống ví dụ, tra danh sách trường/lệnh trợ giúp của đúng phiên bản đang dùng. PCAP cần kèm ghi chú điểm capture, span/VLAN, filter và khoảng thời gian; không thu được gói tại một sensor chưa chứng minh host không hề truyền.

Gợi ý đối chiếu khác: DNS query/response, NXDOMAIN ratio, chiều dài QNAME theo thời gian; firewall rule ID và NAT mapping; sự kiện EDR và tiến trình tạo kết nối; phiên VPN hoặc danh tính người dùng; thay đổi cấu hình thiết bị trước khi có tín hiệu bất thường.

### Bước 3 — Phân loại, leo thang và quyết định ngăn chặn

Incident Commander đánh giá ba yếu tố: **độ tin cậy của dấu hiệu**, **mức quan trọng của tài sản/dữ liệu** và **mức ảnh hưởng đang tiếp diễn**. Có thể dùng thang nội bộ như sau, nhưng phải ánh xạ vào chính sách tổ chức:

| Mức minh họa | Tình huống | Cách xử lý |
|---|---|---|
| P1 | Bằng chứng tin cậy về ảnh hưởng tới dịch vụ trọng yếu hoặc dữ liệu nhạy cảm đang bị tác động | Kích hoạt điều phối sự cố, ưu tiên kiểm soát tác động và thông báo đầu mối |
| P2 | Tín hiệu đáng tin cậy trên một host, ảnh hưởng chưa rõ hoặc chưa lan rộng | Điều tra ưu tiên cao, chuẩn bị cô lập hẹp, tăng giám sát |
| P3 | Alert đơn lẻ, độ tin cậy thấp, chưa có tác động đã xác minh | Xác thực thêm, theo dõi và đóng với lý do rõ ràng nếu là false positive |

Trong kịch bản, lựa chọn có thể là chặn DNS trực tiếp đến resolver không được phê duyệt, tạm giới hạn egress của Client-45, hoặc cô lập endpoint bằng EDR/NAC trong lab. Mỗi phương án phải trả lời:

- **Chặn cái gì?** Nguồn, đích, cổng, chiều, rule/ACL, phạm vi VLAN, TTL nếu có.
- **Vì sao cần chặn?** Chỉ báo nào đủ tin cậy; rủi ro nếu chờ thêm bằng chứng.
- **Ảnh hưởng phụ?** DNS của ứng dụng, thiết bị dùng chung, luồng quản trị và đường truy cập ứng cứu.
- **Ai phê duyệt và ai thực hiện?** Thời điểm, ticket thay đổi và người xác minh độc lập.
- **Hoàn tác thế nào?** Cấu hình trước thay đổi, điều kiện rollback và đầu mối thực hiện.

Không nên mặc định chặn toàn VLAN vì một endpoint khả nghi. Cô lập mạng có thể làm mất kênh EDR/thu chứng cứ hoặc cắt dịch vụ nghiệp vụ. Nếu cần cô lập gấp, ghi nhận nguyên nhân ưu tiên và tiến hành bước bảo toàn khả thi song song.

### Bước 4 — Bảo quản chứng cứ

Với mỗi hiện vật, ghi:

| Trường trong evidence manifest | Ví dụ |
|---|---|
| Evidence ID | EX-NET-013-E03 |
| Nguồn | Firewall egress của VLAN 30 |
| Khoảng thời gian (UTC) | 2026-01-15 08:50–09:40 |
| Người thu / thời điểm thu | Nhân sự được phân quyền / 09:42 UTC |
| Dữ liệu | Trích xuất flow dạng CSV đã giới hạn phạm vi |
| SHA-256 | Hash của tệp sau khi xuất |
| Nơi lưu | Kho chứng cứ có kiểm soát truy cập và retention |
| Chuỗi bàn giao | Ai nhận, khi nào, mục đích, quyền truy cập |

Ví dụ kiểm tra hash của file lab:

~~~bash
sha256sum /var/tmp/exercise-net-013.pcap
~~~

Hash giúp kiểm tra **tính toàn vẹn byte** từ thời điểm tạo hash; nó không tự chứng minh nguồn gốc, tính đầy đủ hoặc khả năng chấp nhận theo thủ tục pháp lý. Giữ tệp gốc, hạn chế sửa trực tiếp, phân quyền, ghi mọi lần chuyển giao và tuân thủ chính sách lưu trữ.

### Bước 5 — Xử lý nguyên nhân và khôi phục có kiểm chứng

Sau khi kiểm soát lưu lượng nghi ngờ, người phụ trách endpoint và network phối hợp tìm nguyên nhân: ứng dụng hợp lệ bị cấu hình sai, tác vụ không được phép, tài khoản bị lộ, DNS egress policy yếu, hoặc lỗi telemetry. **Cách xử lý phụ thuộc kết luận điều tra**: sửa cấu hình, thu hồi thông tin xác thực, dọn tác vụ, cập nhật endpoint, bổ sung rule hoặc nâng chất lượng phát hiện. Không kết luận đã xử lý tận gốc chỉ vì luồng mạng tạm dừng.

Điều kiện phục hồi gợi ý:

1. Người phụ trách xác nhận nguyên nhân hoặc mức rủi ro còn lại đã được chấp nhận bởi đúng thẩm quyền.
2. Có cấu hình trước/sau, kế hoạch khôi phục, giám sát tăng cường và người thực hiện.
3. DNS tới resolver nội bộ hoạt động; egress chỉ đi qua đường được phê duyệt.
4. Ứng dụng nghiệp vụ vượt qua health check và các kiểm thử kết nối thiết yếu.
5. Trong cửa sổ quan sát thỏa thuận, không xuất hiện lại cùng chỉ báo hoặc có giải thích rõ về nhiễu hợp lệ.
6. IC và service owner ghi quyết định kết thúc, điều kiện mở lại sự cố nếu có tái diễn.

Nếu khôi phục có ràng buộc RTO/RPO, hãy đo theo **định nghĩa RTO/RPO của chính dịch vụ**. Không đồng nhất “rule đã xóa” với “dịch vụ đã phục hồi”, cũng không lấy việc “không có alert mới” làm tiêu chí duy nhất.

## 6. Danh sách inject cho người điều phối

**Inject** là thông tin mới được phát vào một thời điểm định trước để buộc đội ứng phó lựa chọn, phối hợp hoặc kiểm chứng. Bảng sau dùng cho buổi diễn tập 120 phút; T+ tính từ lúc bắt đầu. Chỉ controller/evaluator được xem trước cột “Điều cần quan sát”.

| Mốc | Inject gửi người chơi | Hành động mong đợi | Điều cần quan sát |
|---|---|---|---|
| T+00 | “Đang trực ca; cảnh báo chưa xuất hiện.” | Kiểm tra ca trực, kênh liên lạc, dashboard và chủ dịch vụ | Có người nhận vai trò, biết đường leo thang |
| T+10 | SIEM gửi **EXERCISE-NET-013**: DNS anomaly từ 10.20.30.45 | Mở ticket, xác thực IP/timestamp, phân công điều tra | Ghi mốc nhận và giả thuyết ban đầu |
| T+20 | Flow cho thấy DNS ngoài và TCP/443 có bytes_out cao | So sánh baseline, kiểm tra firewall/NAT/DHCP | Không tự kết luận exfiltration chỉ từ flow |
| T+30 | “Đơn vị nghiệp vụ xác nhận Client-45 chạy một ứng dụng quan trọng.” | Đánh giá blast radius và biện pháp ít ảnh hưởng | Có thảo luận về rủi ro gián đoạn |
| T+40 | EDR có cảnh báo tiến trình mạng bất thường, chưa đủ chi tiết | Phối hợp endpoint, đề nghị thu chứng cứ theo thẩm quyền | Không suy đoán danh tính tiến trình |
| T+50 | Chủ dịch vụ yêu cầu “đừng chặn cả VLAN”; hoạt động đáng ngờ vẫn tiếp diễn | IC chọn biện pháp hẹp, ghi phê duyệt, kiểm tra rollback | Quyết định có điều kiện và người chịu trách nhiệm |
| T+65 | Log firewall cho biết rule hẹp đã chặn DNS ra ngoài; DNS nội bộ vẫn hoạt động | Xác minh hiệu lực chặn trên **nhiều nguồn** | Phân biệt action DENY với alert cũ |
| T+80 | Nhóm endpoint tìm thấy cấu hình DNS không được phê duyệt trong image lab | Đề xuất xử lý nguyên nhân và thử nghiệm | Ghi kết luận phù hợp với chứng cứ |
| T+95 | Health check nghiệp vụ đạt, chưa thấy lưu lượng tương tự trong cửa sổ quan sát | Đề xuất khôi phục và thời gian tăng giám sát | IC/service owner quyết định theo tiêu chí |
| T+110 | Quản lý yêu cầu cập nhật trạng thái trong 2 phút | Gửi SITREP ngắn, phân biệt fact/unknown/next step | Thông tin chính xác, không suy diễn rò rỉ |
| T+120 | Điều phối viên công bố kết thúc diễn tập | Lưu chứng cứ, tổng hợp timeline, họp debrief | Có kết luận, điểm yếu, owner và hạn khắc phục |

Controller có thể thay đổi inject dựa trên quyết định người chơi, nhưng phải ghi thay đổi để evaluator không so sánh sai giữa các đội. Nếu người chơi phát hiện false positive hợp lý, cho phép nhánh xử lý đó; chấm **chất lượng chứng minh** thay vì ép họ đi tới kết luận cố định.

### 6.1. Ba nhánh mở rộng

**Nhánh A — Mất telemetry:** Một sensor NetFlow ngừng gửi 10 phút. Đội phải nhận diện khoảng trống, lấy nguồn bù (firewall/EDR/DNS), phản ánh mức độ tự tin giảm và đề xuất khắc phục pipeline.

**Nhánh B — Quy tắc firewall ảnh hưởng dịch vụ:** Thao tác mô phỏng chặn nhầm DNS nội bộ. Đội phải phát hiện suy giảm qua health check, đưa ra rollback đã chuẩn bị, đồng thời giữ kiểm soát với đích đáng ngờ.

**Nhánh C — Cảnh báo trên hạ tầng đám mây:** Cùng IOC xuất hiện tại workload cloud. Đội phải kiểm tra VPC/VNet flow, security group/NSG, NAT gateway, DNS logging, chủ tài khoản và phạm vi IAM; không giả định biện pháp tại firewall on-premise có hiệu lực với mọi đường egress.

## 7. Nhật ký và mẫu báo cáo sử dụng trong diễn tập

### 7.1. Timeline sự kiện và quyết định

Một timeline cần tách **thời gian sự kiện** khỏi **thời gian đội biết về sự kiện**. Ví dụ:

| Event time (UTC) | Observed time (UTC) | Ghi nhận | Mức tin cậy / nguồn |
|---|---|---|---|
| 09:03 | 09:07 | DNS anomaly xuất hiện và SIEM phát alert | High về việc có cảnh báo; chưa kết luận nguyên nhân |
| 09:06 | 09:13 | Flow TCP/443 ra ngoài được phát hiện khi điều tra | High về metadata; unknown về payload |
| 09:19 | 09:19 | IC nâng mức ưu tiên và giao phương án cô lập | Decision log |
| 09:37 | 09:39 | Rule mô phỏng có hiệu lực; kiểm chứng qua log và probe | Firewall + validation record |
| 10:55 | 10:55 | Service owner xác nhận điều kiện khôi phục | Health check + phê duyệt |

Ở diễn tập khác, evaluator có thể thay đổi toàn bộ thời điểm này; chúng **không** được tự động suy từ mốc T+ ở bảng inject bên trên. Timeline riêng này là ví dụ độc lập để thực hành tính thời lượng.

### 7.2. Mẫu SITREP ngắn

~~~text
[EXERCISE] SITREP 02 — 2026-01-15 09:40 UTC
Incident ID: EXERCISE-NET-013
Điều phối: IC / người trực chịu trách nhiệm
Trạng thái: Đang kiểm soát, chưa kết thúc điều tra

Đã xác minh:
- Client-45 (10.20.30.45 tại thời điểm log) có DNS egress ngoài chính sách.
- Firewall ghi nhận rule cô lập hẹp có hiệu lực.
- DNS nội bộ đang đáp ứng truy vấn kiểm tra.

Chưa xác minh:
- Có hay không truy xuất dữ liệu nhạy cảm.
- Nguyên nhân gốc và các host khác có liên quan.

Ảnh hưởng nghiệp vụ:
- Chưa thấy lỗi ở health check của dịch vụ được đưa vào lab.

Việc tiếp theo:
- Endpoint owner phân tích nguyên nhân trước 10:00 UTC.
- NOC tiếp tục giám sát flow và chuẩn bị rollback khi cần.
- IC cập nhật SITREP tiếp theo lúc 10:10 UTC.
~~~

Cập nhật nên ghi rõ người nhận, thời điểm và kênh đã dùng. Với người dùng cuối, truyền thông theo chính sách tổ chức; không nói “đã rò rỉ” khi mới có traffic volume bất thường.

### 7.3. Mẫu decision log và action tracker

| Thời điểm UTC | Người quyết định | Quyết định và căn cứ | Phạm vi / rủi ro / rollback | Kết quả xác minh |
|---|---|---|---|---|
| 09:19 | IC | Ưu tiên P2; tiếp tục kiểm tra endpoint | Chưa thay đổi mạng; đánh giá lại trong 10 phút | Ticket được cập nhật |
| 09:30 | IC + service owner | Phê duyệt rule egress chỉ cho Client-45 và đích DNS ngoài | Snapshot ACL; rollback do NOC thực hiện | Hiệu lực lúc 09:37 |
| 10:55 | IC + service owner | Đóng pha khôi phục theo health check và giám sát | Duy trì cảnh báo tăng cường | Ghi người theo dõi 24 giờ mô phỏng |

| Hành động cải tiến | Owner | Mức ưu tiên | Hạn / tiêu chí hoàn thành |
|---|---|---|---|
| Bổ sung tương quan DHCP lease và firewall NAT trong SIEM | SOC engineer | High | Có test log đổi IP, tự động tra đúng asset |
| Tạo playbook cô lập host với bước rollback | Network security | High | Chạy lại trong lab, được service owner phê duyệt |
| Đo độ trễ ingest DNS/EDR và cảnh báo mất telemetry | Observability | Medium | Có dashboard và cảnh báo kiểm thử được |
| Bổ sung ngưỡng DNS anomaly theo baseline ứng dụng | Detection engineer | Medium | Tỷ lệ false positive được báo cáo trên dữ liệu lab |

### 7.4. After Action Review (AAR)

Ngay sau phiên, controller tổ chức debrief khoảng 15–30 phút. AAR cần trả lời:

1. Mục tiêu nào đạt, mục tiêu nào chưa đạt, dựa trên evidence ID hoặc quan sát nào?
2. Quyết định nào làm giảm ảnh hưởng? Quyết định nào tạo rủi ro gián đoạn không cần thiết?
3. Những bước nào chậm do thiếu quyền, log, quy trình hay đầu mối liên hệ?
4. Có giả định ban đầu nào bị bác bỏ khi dữ liệu mới xuất hiện?
5. Bài học nào biến thành thay đổi cụ thể, có owner, hạn và cách thử lại?

Một phát hiện tốt viết theo cấu trúc **quan sát → hệ quả → đề xuất → người chịu trách nhiệm → kiểm chứng**, chẳng hạn: “Không truy xuất được lease lịch sử trong 8 phút → chậm xác nhận asset → tạo truy vấn IPAM theo timestamp → nhóm SOC → chạy lại inject đổi IP để xác minh”.

## 8. Đo lường hiệu quả và chấm điểm

### 8.1. Phân biệt các mốc đo

Ghi timestamp theo UTC và thống nhất quy ước trước buổi diễn tập:

- **Thời gian phát hiện:** từ sự kiện đầu tiên nằm trong phạm vi diễn tập đến lúc tín hiệu được hệ thống/đội phát hiện; nêu rõ đang đo alert tự động hay con người.
- **Thời gian tiếp nhận:** từ khi alert đến khi analyst xác nhận và nhận phụ trách.
- **Thời gian phân loại:** từ tiếp nhận đến quyết định mức ưu tiên có căn cứ.
- **Thời gian ngăn chặn:** từ quyết định cô lập đến lúc chứng minh biện pháp đã có hiệu lực.
- **Thời gian khôi phục:** từ thời điểm biện pháp ngăn chặn có hiệu lực đến lúc đáp ứng tiêu chí phục hồi.
- **Thời gian toàn trình:** từ sự kiện đầu tiên đến mốc kết thúc đã được phê duyệt.

Với timeline minh họa 09:03 (sự kiện), 09:07 (alert), 09:10 (tiếp nhận), 09:19 (phân loại), 09:37 (ngăn chặn có hiệu lực), 10:55 (khôi phục):

| Chỉ số của **một tình huống** | Phép tính | Kết quả |
|---|---|---|
| Thời gian phát hiện | 09:07 − 09:03 | 4 phút |
| Thời gian tiếp nhận | 09:10 − 09:07 | 3 phút |
| Thời gian phân loại sau tiếp nhận | 09:19 − 09:10 | 9 phút |
| Thời gian ngăn chặn sau quyết định | 09:37 − 09:19 | 18 phút |
| Thời gian từ ngăn chặn đến phục hồi | 10:55 − 09:37 | 78 phút |
| Thời gian toàn trình | 10:55 − 09:03 | 112 phút |

Các con số trên là **duration** của một lượt diễn tập. Chỉ dùng tên MTTD/MTTC/MTTR khi đã định nghĩa chính xác điểm đầu/cuối và có tập đủ nhiều sự cố để lấy trung bình; MTTR có nhiều cách định nghĩa giữa các tổ chức.

### 8.2. Rubric đánh giá 100 điểm

| Nhóm năng lực | Điểm tối đa | Tiêu chí có thể kiểm chứng |
|---|---:|---|
| Phát hiện và tiếp nhận | 15 | Ticket đúng phạm vi, timestamp và người phụ trách |
| Phân tích và định phạm vi | 20 | Đối chiếu nhiều nguồn; tách fact/hypothesis; tìm asset và mức ảnh hưởng |
| Ra quyết định / cô lập | 20 | Chọn phạm vi phù hợp, có phê duyệt, rollback và xác nhận hiệu lực |
| Quản lý chứng cứ | 15 | Manifest, hash, nguồn, timezone và chuỗi bàn giao |
| Phối hợp và truyền thông | 10 | Rõ vai trò, SITREP đúng sự thật và cập nhật đúng lịch |
| Khôi phục và theo dõi | 15 | Root cause hoặc rủi ro còn lại, health check, phê duyệt, giám sát tái diễn |
| AAR và cải tiến | 5 | Có ít nhất một hành động cụ thể với owner và test lại |
| **Tổng** | **100** | Không cộng điểm từ kết quả chỉ do controller “nói rằng đã xong” |

Evaluator nên ghi bằng chứng theo mục tiêu, ví dụ ticket ID, thời điểm rule có hiệu lực, link dashboard hoặc evidence ID. **Chấm chất lượng quyết định và khả năng giải thích**, không chỉ số phút. Một đội có thể chậm hơn vì kiểm tra tác động nghiệp vụ đúng quy trình.

## 9. Kế hoạch thời gian cho một buổi diễn tập

| Khoảng | Hoạt động | Đầu ra |
|---|---|---|
| Trước buổi diễn tập | Xác nhận EX-PLAN, ROE, quyền, người trực, dữ liệu và backup/snapshot | Điều kiện bắt đầu đã đạt |
| 00–10 phút | Briefing nhanh, phân vai, kênh liên lạc | Danh sách vai trò và tình trạng sẵn sàng |
| 10–35 phút | Alert + truy vấn DNS/Flow/DHCP/EDR | Ticket, timeline, giả thuyết và scope |
| 35–65 phút | Tranh luận rủi ro, phê duyệt cô lập và xác minh | Decision log, rule change, kết quả kiểm chứng |
| 65–95 phút | Xử lý nguyên nhân và khôi phục dịch vụ giả lập | Health check, trạng thái dịch vụ, residual risk |
| 95–120 phút | SITREP, review nhanh và thu sản phẩm | Sơ bộ AAR và danh sách đầu việc |
| Sau buổi diễn tập | AAR đầy đủ, cải tiến, giao deadline, thử lại | Báo cáo chấm điểm và kế hoạch khắc phục |

Tùy mục tiêu, có thể tách debrief 15–30 phút thành phiên riêng để không làm thiếu thời gian điều tra. Mục tiêu diễn tập **không phải cố kết thúc mọi nhánh trong 120 phút**; một đội biết dừng và giao tiếp rủi ro chưa giải quyết cũng có thể đạt kết quả tốt.

## 10. Các lỗi thường gặp và cách phát hiện

| Sai sót | Dấu hiệu | Cách cải thiện |
|---|---|---|
| Kết luận xâm nhập từ một rule hoặc một alert | Báo cáo ghi “đã rò rỉ” nhưng không có nguồn xác minh | Tách fact/hypothesis/unknown; buộc nêu dữ liệu cần kiểm chứng |
| Đồng nhất IP với người dùng | Tra IP hiện tại, bỏ qua lease lịch sử/NAT/VPN | Tương quan theo timestamp, asset, MAC, user và đường NAT |
| Chặn quá rộng | Cô lập toàn VLAN, dịch vụ khác mất DNS | Đánh giá phạm vi hẹp, phụ thuộc và kế hoạch hoàn tác |
| Để mất chứng cứ | Chỉ lưu ảnh màn hình; không có file gốc/hash/timestamp | Evidence manifest, chính sách truy cập và bàn giao |
| Không xác minh hiệu quả cô lập | Firewall đã thêm rule nhưng flow vẫn đi qua đường khác | Kiểm tra action, telemetry bổ sung, đường đi thay thế và test ứng dụng |
| Bỏ sót cloud/VPN | Chỉ kiểm tra firewall trong văn phòng | Vẽ luồng dữ liệu từ endpoint tới VPC/VNet, VPN, proxy và SaaS |
| Không đồng bộ giờ | DNS/EDR/firewall thể hiện timeline trái nhau | Chuẩn UTC, kiểm tra clock skew và thời điểm ingest |
| Không thông báo theo lịch | Ticket có log nhưng người ra quyết định không có SITREP | Cố định chu kỳ SITREP và đầu mối chịu trách nhiệm |
| Khôi phục vội | Thấy alert ngừng rồi xóa rule ngay | Cần chứng cứ xử lý nguyên nhân, health check và giám sát |
| AAR thiếu hành động | “Cần phối hợp tốt hơn” không có người phụ trách | Chuyển thành ticket cải tiến đo được, deadline và bài thử lại |

## 11. Bài tập thực hành và câu hỏi tự đánh giá

### Bài tập 1 — Xử lý false positive có căn cứ

Controller chỉ cung cấp: “Client-45 có 135 flow UDP/53 tới 198.51.100.53 trong 5 phút”. Hãy ghi **ba giả thuyết**, **ba nguồn dữ liệu cần kiểm tra** và **một quyết định tạm thời**.

**Gợi ý đối chiếu:** ứng dụng đổi resolver, lưu lượng bất thường do phần mềm, sai mapping IP; tra DHCP lease + cấu hình DNS/EDR + firewall/NDR; có thể tăng giám sát hoặc chặn egress hẹp sau khi đánh giá ảnh hưởng. Không mặc định số flow nói lên rò rỉ dữ liệu.

### Bài tập 2 — Cô lập với ràng buộc nghiệp vụ

Host bị nghi ngờ đang phục vụ một tác vụ quan trọng, còn cách kiểm tra tiến trình. Viết một decision log ngắn gồm: mức ưu tiên, nguồn bằng chứng, phương án cô lập hẹp nhất còn hiệu quả, tác động có thể có, người phê duyệt, điều kiện rollback và cách xác nhận kết quả.

**Tiêu chí đạt:** người học chứng minh cân nhắc mức độ đe dọa và tính liên tục dịch vụ, không chọn phương án chỉ vì thao tác nhanh.

### Bài tập 3 — Chứng minh phục hồi

Rule firewall đã hoạt động và SIEM không có cảnh báo mới trong 10 phút. Có đủ cơ sở đóng sự cố chưa? Liệt kê ít nhất bốn kiểm tra cần hoàn thành.

**Gợi ý đối chiếu:** xác minh telemetry đang hoạt động; kiểm tra luồng DNS/egress trên nguồn độc lập; xác nhận xử lý nguyên nhân hoặc residual risk đã được chấp thuận; chạy health check; ghi phê duyệt, cửa sổ theo dõi và cơ chế mở lại.

### Bài tập 4 — Nhánh telemetry thiếu

Một trạm NetFlow mất dữ liệu nhưng DNS và firewall vẫn còn log. Hãy mô tả cách báo cáo khoảng trống chứng cứ, dữ liệu thay thế, mức độ tự tin của kết luận và một cải tiến sau diễn tập.

**Tiêu chí đạt:** không coi sự im lặng của sensor là “không còn lưu lượng”; đưa ra cách xác thực pipeline và trách nhiệm khắc phục.

### Bài tập 5 — Viết AAR có thể thực thi

Cho tình huống: “Lúc 09:07 có cảnh báo; tới 09:19 mới định được chủ thiết bị vì thiếu truy vấn lịch sử DHCP”. Viết một mục AAR theo mẫu quan sát → hệ quả → đề xuất → owner → kiểm chứng.

**Ví dụ đáp án:** “Mất 12 phút xác nhận asset do tìm lease thủ công → trì hoãn phân loại → bổ sung truy vấn tương quan DHCP theo event_time từ SIEM → SOC platform owner → dùng inject IP đổi chủ để kiểm tra trước kỳ diễn tập tiếp theo”.

## 12. Checklist bàn giao kết quả

- [ ] EX-PLAN, phạm vi, quyền thao tác, điều kiện dừng và người chịu trách nhiệm đã rõ.
- [ ] Cảnh báo và log có nguồn, mốc UTC, thông tin asset và giả thuyết được phân biệt.
- [ ] Điều tra có đối chiếu nguồn độc lập, ghi lại những vùng không đủ dữ liệu.
- [ ] Quyết định ngăn chặn có lý do, phê duyệt, phạm vi, phương án rollback và xác minh hiệu lực.
- [ ] Chứng cứ được lưu có kiểm soát, mã định danh, hash (khi có file) và biên bản bàn giao.
- [ ] Hệ thống được kiểm tra khả năng phục hồi; service owner xác nhận điều kiện khôi phục.
- [ ] Có SITREP phù hợp và phân biệt điều đã biết với phần chưa được chứng minh.
- [ ] Evaluator ghi mốc thời gian, bằng chứng, chất lượng ra quyết định và tác động phụ.
- [ ] AAR nêu rõ phát hiện, hành động khắc phục, owner, hạn và cách xác minh ở lần diễn tập sau.

Một buổi diễn tập network incident response có giá trị khi đội ngũ **chứng minh được** khả năng phối hợp, giải thích quyết định bằng dữ liệu, hạn chế phạm vi ảnh hưởng và chuyển bài học thành cải tiến kiểm tra lại được. Việc hoàn thành thao tác kỹ thuật chỉ là một phần của kết quả; hồ sơ quyết định, trạng thái dịch vụ và chất lượng chứng cứ mới cho biết tổ chức có sẵn sàng đối phó với sự cố thật hay chưa.

