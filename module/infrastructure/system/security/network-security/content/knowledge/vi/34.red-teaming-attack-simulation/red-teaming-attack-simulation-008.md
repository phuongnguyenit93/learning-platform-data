# Đo khả năng phát hiện của SOC

## 1. Bối cảnh và mục tiêu

Trong chương **Red team và mô phỏng tấn công mạng** của học phần **SECURITY_NETWORK_SECURITY**, bài học này tập trung vào câu hỏi: *khi một hành vi đe dọa xảy ra trong phạm vi mạng được bảo vệ, Security Operations Center (SOC) có quan sát được, phát cảnh báo đúng, hiểu được mức độ nguy hiểm và phản ứng đủ nhanh hay không?*

An ninh mạng có nhiều lớp phòng vệ: phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, mạng đám mây, hệ thống thu thập lưu lượng và giám sát xâm nhập. Mỗi lớp tạo ra những dấu vết khác nhau. Một bài kiểm thử phát hiện cần đo toàn bộ đường đi của dấu vết, từ hành vi mô phỏng đến người phân tích, thay vì chỉ xem quy tắc SIEM có được bật hay không.

Sau bài này, người học có thể:

- Xác định phạm vi và giả thuyết phát hiện cho một tình huống red team hoặc purple team được cấp phép.
- Lập bộ **ground truth** (sự thật đối chứng) và ma trận kiểm thử gắn với kỹ thuật tấn công, nguồn telemetry và kết quả SOC mong đợi.
- Phân biệt **khả năng quan sát**, **khả năng phát hiện**, **chất lượng cảnh báo**, **khả năng phân tích** và **khả năng phản ứng**.
- Tính và giải thích detection coverage, precision, recall, false positive rate, MTTD, MTTA và các chỉ số hỗ trợ.
- Phân tích nguyên nhân bỏ sót, đề xuất cải tiến, rồi kiểm thử hồi quy mà không gây ảnh hưởng cho hệ thống sản xuất.

**Phạm vi kiểm thử:** chỉ sử dụng môi trường, tài khoản, dữ liệu và kịch bản đã được tổ chức chấp thuận. Các ví dụ dưới đây dùng bản ghi tổng hợp hoặc hoạt động vô hại trong lab; mục tiêu là đánh giá năng lực phòng thủ, không khai thác hệ thống.

## 2. SOC phát hiện được nghĩa là gì?

SOC là chức năng con người, quy trình và công nghệ dùng để thu thập sự kiện, phân tích dấu hiệu đe dọa, điều tra và điều phối ứng phó. Một hệ thống có nhiều log chưa chắc phát hiện tốt; một hệ thống tạo nhiều alert cũng chưa chắc giúp analyst ra quyết định.

Chuỗi xử lý điển hình:

~~~mermaid
flowchart LR
    A["Hành vi mô phỏng\n(có ground truth)"] --> B["Thiết bị và cảm biến\nFW / DNS / VPN / IDS / Cloud"]
    B --> C["Thu thập và chuẩn hóa\ntelemetry"]
    C --> D["Tương quan / luật / phân tích\nSIEM - NDR - EDR"]
    D --> E["Cảnh báo có ngữ cảnh"]
    E --> F["SOC triage và xác nhận"]
    F --> G["Điều tra / chuyển xử lý\n/ phản ứng"]
    A -. "Đối chiếu thực nghiệm" .-> H["Bảng đo và bằng chứng"]
    B -.-> H
    D -.-> H
    F -.-> H
    G -.-> H
~~~

Nên đánh giá các tầng riêng biệt:

| Tầng | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Prevention** – ngăn chặn | Firewall, segmentation hay IPS có chặn hành động không? | Quyết định allow/deny, policy ID, sự kiện chặn |
| **Visibility** – quan sát | Hành vi có tạo telemetry tại điểm cần đo không? | Event gốc, PCAP được phép thu, trường nguồn/đích |
| **Detection** – phát hiện | Công cụ có đưa ra tín hiệu hoặc alert đúng giả thuyết không? | Alert ID, rule ID, thời điểm alert, thực thể liên quan |
| **Triage** – phân tích ban đầu | Analyst có nhận ra cảnh báo đáng chú ý và phân loại đúng không? | Case, phân loại, mức độ ưu tiên, biên bản phân tích |
| **Response** – ứng phó | SOC có thực hiện/escalate đúng runbook và thời hạn không? | Acknowledgement, ticket, hành động được phê duyệt |

**Ví dụ:** Một kết nối trái phép bị firewall chặn. Điều này chứng minh kiểm soát ngăn chặn hoạt động. Nếu bản ghi chặn không đến SOC hoặc không tạo tín hiệu mong đợi, chưa thể kết luận SOC đã phát hiện. Ngược lại, một alert được sinh nhưng không ai nhận và xử lý cũng chưa chứng minh khả năng vận hành SOC tốt.

### 2.1. Nguồn dữ liệu thường dùng trong network security

| Lớp mạng | Telemetry điển hình | Giới hạn thường gặp |
| --- | --- | --- |
| Firewall, ACL, phân đoạn | Source/destination IP, port, action, rule, zone | Thiếu lưu lượng east–west, chỉ log deny, NAT làm mất liên kết danh tính |
| IDS/IPS và NDR | Chữ ký, flow, protocol, anomaly, session | Điểm đặt sensor không thấy lưu lượng; mã hóa làm giảm nội dung quan sát |
| DNS | Query, response, resolver, client, thời gian | DNS-over-HTTPS/DoT ngoài resolver quản lý; cache; thiếu client identity |
| VPN/ZTNA, NAC, xác thực | Login, thiết bị, user, risk, kết quả cấp quyền | Mapping người dùng–IP thay đổi; session tồn tại qua nhiều địa chỉ |
| Proxy, API gateway, load balancer | HTTP metadata, domain, URI, status, request ID | Thiếu request ID xuyên các tầng; tải log không đều |
| Wi-Fi và switch | Association, 802.1X, AP, VLAN, port | Thiếu lịch sử roaming, đồng hồ không đồng bộ |
| Cloud VPC/VNet, Kubernetes | Flow log, audit trail, security-group change, workload ID | Log bị bật chọn lọc; tài nguyên ngắn hạn; độ trễ export |
| Endpoint và identity | Process, host, account, device posture | Không phủ hết thiết bị mạng/IoT; cần tương quan với log mạng |

Không phải hệ thống nào cũng có tất cả các nguồn. Ma trận kiểm thử phải dựa trên **kiến trúc và độ phủ thực tế**, nêu rõ chỗ chỉ có metadata hoặc chưa có sensor.

## 3. Thiết kế phép thử: bắt đầu bằng giả thuyết có thể kiểm chứng

Một yêu cầu mơ hồ như “kiểm tra xem SOC có thấy hành vi bất thường” khó đo lường. Cần viết giả thuyết gồm điều kiện kích hoạt, nơi quan sát, logic nhận diện, đầu ra mong đợi và giới hạn thời gian.

**Mẫu giả thuyết:**

> Khi xuất hiện nhiều kết nối bị từ chối từ cùng một thiết bị nguồn tới các cổng dịch vụ khác nhau trên một đích trong khoảng 5 phút ở vùng lab, firewall gửi log đầy đủ về nền tảng giám sát và SOC nhận được cảnh báo “nghi vấn dò dịch vụ” có source IP, destination IP, dải thời gian và rule ID trong vòng 10 phút.

Đây là *giả thuyết*, chưa phải kết quả. Chỉ sau khi có sự kiện kiểm thử, log, alert và dấu thời gian mới kết luận được.

### 3.1. Bộ dữ liệu ground truth

**Ground truth** do nhóm kiểm thử giữ độc lập với bộ máy cảnh báo. Tối thiểu phải có:

- **scenario_id, execution_id:** định danh kịch bản và lần chạy, tránh gộp nhầm các lần chạy.
- **Technique / tactic:** mục đích và hành vi được mô phỏng; có thể tham chiếu MITRE ATT&CK khi phù hợp.
- **Phạm vi được phép:** môi trường, nguồn/đích, cửa sổ thời gian, người phụ trách, mức độ tác động và điều kiện dừng.
- **Thời điểm:** bắt đầu/kết thúc theo UTC; trạng thái đồng bộ đồng hồ; loại dấu thời gian của từng hệ thống.
- **Dấu vết mong đợi:** log, sensor, trường dữ liệu, quy tắc/analytics và ngưỡng; có thể có nhiều tín hiệu cho một kịch bản.
- **Tiêu chí thành công:** điều kiện chính xác để tính detected, triaged và responded; ví dụ alert phải có đủ định danh tài sản.
- **Dữ liệu âm tính (negative control):** các hoạt động lành tính tương tự, để đánh giá mức báo nhầm.
- **Bằng chứng thực tế:** event ID, PCAP hash nếu có, alert ID, case/ticket ID, thời điểm phản ứng, người kiểm chứng.

Nếu thử nghiệm không diễn ra đúng kịch bản hoặc dữ liệu ground truth không đáng tin, đánh dấu **INVALID_TEST** và chạy lại. Không biến lỗi phép thử thành kết quả thất bại của SOC.

### 3.2. Ma trận kịch bản mẫu

Bảng dưới đây minh họa các giả thuyết phòng thủ. Mọi hoạt động đều được mô phỏng có kiểm soát trong lab, hoặc phát lại các bản ghi tổng hợp.

| ID | Tình huống mô phỏng | Nguồn quan sát | Phát hiện mong đợi |
| --- | --- | --- | --- |
| RT08-01 | Lưu lượng dò nhiều cổng trong segment thử nghiệm (ATT&CK T1046) | Firewall deny, NDR/IDS, NetFlow | Cảnh báo quét dịch vụ với nguồn, đích và số cổng |
| RT08-02 | Truy vấn DNS đến tên miền dành riêng cho kiểm thử theo nhịp đều | DNS resolver, NDR | Tín hiệu chu kỳ DNS, có giải thích và ngữ cảnh loại trừ |
| RT08-03 | Đăng nhập VPN thử nghiệm trong điều kiện rủi ro đã định nghĩa | VPN, IdP, ZTNA | Cảnh báo bất thường gắn với user và device |
| RT08-04 | Kết nối east–west tới vùng phân đoạn bị policy từ chối | Firewall nội bộ, switch flow | Log chặn đúng policy; alert nếu kịch bản đặt yêu cầu alert |
| RT08-05 | Metadata HTTP được gắn nhãn mô phỏng với chu kỳ đều | Proxy, NDR | Tín hiệu kết nối lặp lại khi đạt ngưỡng, không dựa riêng vào nhãn test |
| RT08-06 | Thay đổi security group trên tài nguyên cloud lab | Cloud audit log, SIEM | Cảnh báo thay đổi cấu hình quan trọng với actor và resource ID |

Tín hiệu **ứng viên** (nhiều cổng, truy vấn định kỳ, đăng nhập khác thường) chưa tự chứng minh có tấn công. Một quy tắc tốt phải thêm ngữ cảnh tài sản, baseline, allowlist đã xét duyệt và bằng chứng tương quan để tránh báo động từ việc quét bảo trì, dịch vụ kiểm tra sức khỏe hay tác vụ quản trị hợp lệ.

### 3.3. Điều kiện an toàn và tính công bằng của phép đo

Trước khi chạy, xác nhận phạm vi ủy quyền, cửa sổ thử nghiệm, mức tải tối đa, đầu mối liên lạc và cơ chế dừng. Dùng tài khoản, dải mạng, tên miền, thiết bị thử nghiệm chuyên dụng; **không** dùng dữ liệu thật của khách hàng để tạo sự kiện nhạy cảm. Với tình huống khó thực hiện an toàn, dùng log/PCAP tổng hợp hoặc cơ chế mô phỏng của công cụ bảo mật.

Hai chế độ đo đều có giá trị nhưng phải tách bạch:

1. **Informed exercise:** SOC biết trước một đợt mô phỏng sẽ diễn ra, phù hợp kiểm tra kỹ thuật, chỉnh rule và quy trình.
2. **Blind exercise:** chỉ nhóm điều phối được ủy quyền biết kịch bản; phù hợp đánh giá quy trình nhận biết và phản ứng trong điều kiện thực tế.

Ghi rõ chế độ khi báo cáo. Một đội SOC được báo trước sẽ có thời gian phản ứng khác với ca trực thường ngày; không nên so sánh trực tiếp hai đợt như thể điều kiện giống nhau.

## 4. Quy trình đo từ đầu đến cuối

### Bước 1. Đóng băng phạm vi, mục tiêu và baseline

Ghi lại phiên bản rule, cấu hình thu thập log, các connector, khả năng retention, cấu hình phân đoạn, timezone và thời gian hoạt động của sensor. Xác định mức hiệu năng của môi trường trước kiểm thử: lưu lượng nền, số alert thông thường, backlog, số analyst trực ca. Điều này giúp phân biệt tín hiệu mô phỏng với thay đổi hệ thống tình cờ.

Đặt thời hạn cho từng kết quả: chẳng hạn **alert trong 10 phút**, **acknowledge trong 15 phút kể từ alert**, **escalate trong 30 phút nếu mức độ cao**. Đây chỉ là ví dụ: ngưỡng thực phải theo SLA và mức độ rủi ro của tổ chức.

### Bước 2. Kiểm tra ống dẫn telemetry trước khi đánh giá rule

Kiểm tra đồng bộ NTP, thời gian sự kiện, thời gian ingest, định dạng IP/port, hostname, user ID, workload ID, NAT mapping và trường zone. Chạy một sự kiện lab dễ nhận biết; đối chiếu event ID từ sensor đến kho log/SIEM. Nếu log không tới, ghi nhận lỗi visibility và thực hiện phép thử sau khi hiểu nguyên nhân. Không coi sự hiện diện của dữ liệu trong sensor là bằng chứng SIEM đã thu được.

Mỗi vị trí log nên lưu các mốc:

- **t0:** hành vi mô phỏng bắt đầu theo ground truth.
- **t1:** sensor tạo sự kiện.
- **t2:** SIEM/NDR nhận và có thể tìm kiếm sự kiện.
- **t3:** alert đầu tiên thỏa tiêu chí phát hiện được tạo.
- **t4:** analyst xác nhận/acknowledge.
- **t5:** analyst phân loại đúng hoặc chuyển cho bên phản ứng.
- **t6:** hành động ứng phó được phép thực hiện và xác nhận.

Khi cần phân tích thời gian, dùng timestamp từ cùng chuẩn UTC. Nếu chỉ biết thời gian giao diện hiển thị, phải nói rõ độ chính xác thấp hơn log timestamp.

### Bước 3. Chạy positive test và negative control

**Positive test** chủ động tạo sự kiện được kỳ vọng phát hiện. Đối với mỗi lần chạy, lưu execution_id, đầu vào và chứng cứ sự kiện thật sự đã xảy ra. **Negative control** là hoạt động lành tính có đặc điểm gần tương tự nhưng không cần báo động mức nguy hiểm, chẳng hạn quét bảo trì từ nguồn đã đăng ký trong khung giờ được duyệt hoặc chu kỳ DNS của ứng dụng nội bộ.

Không nên gắn cờ “simulation=true” làm điều kiện chính để quy tắc phát hiện phát alert: như vậy chỉ chứng minh hệ thống nhận nhãn, không chứng minh phân tích hành vi. Nhãn mô phỏng dùng để đối chiếu và làm sạch dữ liệu bài kiểm thử sau khi kết thúc.

### Bước 4. Thu thập bằng chứng ở từng tầng

Đối với **mọi** lần chạy, xác nhận:

1. Hành vi có được tạo thành công không? Có chứng cứ độc lập không?
2. Sensor nào thấy, sensor nào không thấy, và vì sao?
3. Log có vào kho đích đúng thời điểm, đủ trường nhận diện không?
4. Rule hoặc analytic nào chạy, có alert đúng kịch bản và đủ ngữ cảnh không?
5. SOC có tiếp nhận, xác nhận, phân loại và mở case đúng yêu cầu không?
6. Nếu có phản ứng, đã được phê duyệt, thực thi và xác nhận chưa?

Khi một kịch bản sinh 20 alert trùng nội dung, không tính thành 20 lần phát hiện thành công. Dùng một đơn vị đánh giá đã định nghĩa trước (thường là **một lần thực thi kịch bản**) và đo riêng mức trùng lặp cảnh báo.

### Bước 5. Đối chiếu và phân loại kết quả

| Trạng thái | Diễn giải |
| --- | --- |
| **DETECTED** | Có ít nhất một alert đủ tiêu chí, liên hệ được đúng execution_id và trong thời hạn đặt ra |
| **DETECTED_LATE** | Có alert đúng nhưng sau thời hạn; cần hiển thị riêng khi đánh giá SLA |
| **NOT_DETECTED** | Hành vi thực sự xảy ra, nhưng không có alert thỏa tiêu chí trước thời hạn |
| **UNOBSERVABLE** | Hành vi xảy ra nhưng đường thu thập telemetry thiếu/đứt; là một loại nguyên nhân bỏ sót end-to-end |
| **INVALID_TEST** | Kịch bản không chạy đúng hoặc ground truth không xác định được; loại khỏi mẫu và chạy lại |
| **NOT_RUN** | Chưa thử; không được báo thành công hay thất bại |

**UNOBSERVABLE** phải được tính là thất bại khi đo khả năng phát hiện end-to-end trong hệ thống đang vận hành. Tuy nhiên, nếu mục tiêu nghiên cứu chỉ là chất lượng một rule trên các log sẵn có thì ghi riêng mẫu bị thiếu telemetry và công khai việc loại mẫu. Không được loại các trường hợp khó khỏi mẫu số mà không giải thích.

## 5. Các chỉ số và cách tính

### 5.1. Bốn ô kết quả: TP, FP, FN, TN

Với từng đơn vị đánh giá và bộ tiêu chí cố định:

- **TP (true positive):** hành vi mục tiêu đã xảy ra và hệ thống báo đúng.
- **FN (false negative):** hành vi mục tiêu đã xảy ra nhưng không được phát hiện đạt tiêu chí.
- **FP (false positive):** hệ thống cảnh báo hành vi mục tiêu trong một đơn vị đối chứng không có hành vi đó.
- **TN (true negative):** đơn vị đối chứng không có hành vi mục tiêu và hệ thống không cảnh báo.

**Lưu ý về mẫu số:** cần dùng đơn vị thống nhất, ví dụ *cửa sổ–tài sản* được gắn nhãn, hoặc *lần thực thi kịch bản*. Không ghép số lần mô phỏng cho TP/FN với số raw alert cho FP. TN đặc biệt dễ bị phóng đại nếu tự đếm mọi phút không có alert là một mẫu âm tính; phải xác định cửa sổ đối chứng từ trước.

| | Thực tế có hành vi mục tiêu | Thực tế không có hành vi mục tiêu |
| --- | ---: | ---: |
| Hệ thống báo có | TP | FP |
| Hệ thống báo không | FN | TN |

Các chỉ số:

\[
\text{Recall (Detection Rate)}=\frac{TP}{TP+FN}
\]

\[
\text{Precision}=\frac{TP}{TP+FP}
\]

\[
\text{False Positive Rate}=\frac{FP}{FP+TN}
\]

\[
F_1=2\times\frac{\text{Precision}\times\text{Recall}}{\text{Precision}+\text{Recall}}
\]

Nếu mẫu số bằng 0, báo **N/A**; không tự gán bằng 0 hoặc 100%. Khi số mẫu nhỏ, luôn công bố cả tử số/mẫu số. Precision cao nhờ chỉ phát hiện 1 ca rất rõ ràng nhưng bỏ sót phần còn lại vẫn là hệ thống kém bao phủ; vì vậy cần xem Precision *cùng* Recall.

### 5.2. Coverage cần tách theo tầng

**Scenario detection coverage** = số kịch bản hợp lệ có detection đạt tiêu chí / tổng số kịch bản hợp lệ nằm trong phạm vi đã chốt.

**Telemetry coverage** = số kịch bản hợp lệ có dữ liệu quan sát cần thiết / tổng số kịch bản hợp lệ yêu cầu dữ liệu đó.

**Technique coverage** = số kỹ thuật trong danh mục đã chọn có ít nhất một kịch bản được kiểm thử và đạt tiêu chí / số kỹ thuật trong danh mục đã chọn. Công bố danh mục và tiêu chuẩn “đạt”; một kỹ thuật có 1 cảnh báo không đồng nghĩa mọi biến thể của kỹ thuật đó đều được phát hiện.

**Response SLA compliance** = số case cần phản ứng có xử lý trong thời hạn / số case đủ điều kiện cần phản ứng. Không tính các case chưa được mở thành kết quả phản ứng tốt; báo kèm số ca không được phát hiện để tránh thiên lệch.

Coverage cần đi kèm độ tin cậy tín hiệu: alert có đủ thông tin nguồn, đích, user, tài sản, sơ đồ liên kết và hướng dẫn điều tra hay không.

### 5.3. Thời gian phát hiện và xử lý

Với một lần chạy có cảnh báo đúng:

\[
TTD_i=t3_i-t0_i
\]

\[
TTA_i=t4_i-t3_i
\]

\[
TTE_i=t5_i-t3_i
\]

Trong đó **TTD** (time to detect) là thời gian từ bắt đầu hành vi đến alert đạt tiêu chí; **TTA** (time to acknowledge) là thời gian từ alert đến khi được nhận; **TTE** ở đây là thời gian từ alert đến khi phân loại hoặc chuyển tuyến đúng. Cần thống nhất định nghĩa này trong báo cáo vì tên viết tắt có thể khác giữa các tổ chức.

**MTTD** là trung bình TTD của các lần được phát hiện, nên phải báo kèm **tỷ lệ phát hiện và tỷ lệ trễ SLA**. Một SOC chỉ phát hiện 1/100 tình huống trong 1 phút có MTTD rất thấp nhưng năng lực tổng thể không tốt.

Có thể báo thêm median và P95 TTD vì phân phối thường lệch. Với mẫu nhỏ, ghi rõ phương pháp phân vị (ví dụ nearest-rank). Thời gian nhận log là **t2 − t1**, độ trễ phát hiện sau ingest là **t3 − t2**. Phân rã này giúp xác định nút thắt ở sensor, pipeline hay rule.

Các tình huống không có alert là dữ liệu **chưa phát hiện trong cửa sổ quan sát**. Không gán TTD = 0, và không tùy ý gán thời gian vô cực khi tính trung bình; đưa vào FN/coverage và thống kê riêng kết quả censored.

### 5.4. Chi phí và sức khỏe vận hành

Các chỉ số hữu ích khác:

- **Alert volume:** số alert theo ngày, ca, loại rule và mức nghiêm trọng.
- **Duplicate alert rate:** tỷ lệ alert bị gộp trùng theo khóa kịch bản/tài sản; giúp tránh alert storm.
- **Actionable alert rate:** tỷ lệ alert có đủ thông tin và có hành động tiếp theo phù hợp.
- **Case accuracy:** tỷ lệ phân loại đúng so với ground truth được người kiểm chứng phê duyệt.
- **Telemetry freshness và completeness:** độ trễ đưa log vào hệ thống, tỷ lệ sự kiện mất trường bắt buộc.
- **Analyst workload:** số case/ca trực, thời gian triage và backlog.

Không nên đặt KPI kiểu “càng nhiều alert càng tốt”. Sự cân bằng giữa độ bao phủ, độ chính xác và công sức analyst mới phản ánh năng lực phát hiện.

## 6. Ví dụ tính toán hoàn chỉnh

Một đợt thử nghiệm trong lab đã xác định trước **8 cửa sổ có hành vi mục tiêu** và **10 cửa sổ đối chứng âm tính** cùng đơn vị quan sát, với **cửa sổ đánh giá phát hiện là 20 phút**. Trong 8 positive test, 6 trường hợp có alert đúng trong cửa sổ 20 phút, 2 không được phát hiện. Trong 10 negative control, 2 bị báo nhầm và 8 không có cảnh báo.

| Kết quả | Số lượng | Ghi chú |
| --- | ---: | --- |
| TP | 6 | Có alert đúng trong cửa sổ quan sát 20 phút |
| FN | 2 | Một trường hợp không có telemetry, một có log nhưng rule không kích hoạt |
| FP | 2 | Hai cửa sổ hoạt động lành tính phát cảnh báo nhầm |
| TN | 8 | Tám cửa sổ đối chứng không phát alert |

Từ đó:

\[
\text{Recall}=\frac{6}{8}=75\%,\quad
\text{Precision}=\frac{6}{8}=75\%
\]

\[
\text{FPR}=\frac{2}{10}=20\%,\quad
F_1=0.75
\]

TTD của **sáu TP**, tính bằng phút, lần lượt là 3, 5, 4, 10, 7, 13.

\[
MTTD=\frac{3+5+4+10+7+13}{6}=7\text{ phút}
\]

Dãy sắp xếp là 3, 4, 5, 7, 10, 13; median = (5 + 7)/2 = **6 phút**, P95 nearest-rank = **13 phút**. Nếu SLA phát hiện là **10 phút tính cả mốc bằng 10**, chỉ **5/6 alert** đạt SLA; ca có TTD 13 phút thuộc loại **DETECTED_LATE** dù vẫn là TP trong cửa sổ 20 phút. Khi đo *recall đúng SLA*, số lần phát hiện đúng hạn chỉ là 5/8 = **62,5%**, trong khi recall theo cửa sổ quan sát là 6/8 = **75%**. Phải công bố rõ hai tiêu chí và bảo đảm các negative control cũng dùng cửa sổ đánh giá nhất quán.

Ví dụ phân tích một ca (các thời điểm UTC):

| Mốc | Thời điểm | Diễn giải |
| --- | --- | --- |
| t0 | 10:00 | Mô phỏng bắt đầu |
| t1 | 10:01 | Firewall tạo log |
| t2 | 10:02 | SIEM nhận log |
| t3 | 10:04 | SIEM tạo cảnh báo đúng |
| t4 | 10:10 | Analyst acknowledge |
| t5 | 10:19 | Analyst phân loại và chuyển tuyến |

Từ bảng: **TTD = 4 phút**, **TTA = 6 phút**, **TTE = 15 phút**. Độ trễ ingest sau khi sensor tạo log là 1 phút; từ ingest tới alert là 2 phút. Đây là các số đo quan sát, chưa phải bằng chứng đã ngăn chặn hay khôi phục hệ thống.

## 7. Thực hành phân biệt tín hiệu và alert bằng dữ liệu tổng hợp

Ví dụ một sự kiện DNS tổng hợp trong lab (dùng địa chỉ tài liệu và tên miền không thể phân giải ra Internet):

~~~json
{
  "event_id": "evt-rt08-002-001",
  "execution_id": "run-20261128-a",
  "scenario_id": "RT08-02",
  "event_time": "2026-11-28T03:00:00Z",
  "ingest_time": "2026-11-28T03:00:07Z",
  "event_type": "dns_query",
  "sensor": "dns-resolver-lab",
  "src_ip": "192.0.2.15",
  "query": "check.simulation.invalid",
  "rcode": "NXDOMAIN",
  "simulation": true
}
~~~

Bản ghi chứng minh cảm biến ghi nhận một truy vấn DNS. **Chưa đủ** để khẳng định có beaconing, nhiễm mã độc hay SOC phát hiện. Phát hiện hành vi nhịp đều cần chuỗi thời gian đủ dài, thống kê khoảng cách giữa các lần truy vấn, so sánh baseline và loại trừ tác vụ bảo trì/health check; sau đó phải có alert gắn đúng nguồn và thời điểm kiểm thử.

Một ví dụ quy tắc phân tích *dạng giả mã* cho RT08-01:

~~~text
INPUT: firewall_logs đã chuẩn hóa (timestamp, src_ip, dst_ip,
       dst_port, action, sensor_id, policy_id)

FOR EACH (src_ip, dst_ip) IN sliding_window(5 minutes):
    denied_ports = distinct(dst_port WHERE action == "deny")
    IF count(denied_ports) >= threshold_for_segment
       AND src_ip NOT IN approved_scanners_for_this_window:
        EMIT alert(
            rule_id="NET-SERVICE-ENUMERATION-CANDIDATE",
            src_ip, dst_ip, port_count,
            first_seen, last_seen, sample_event_ids
        )
~~~

**Ngưỡng** phải được chọn từ baseline và hiệu chỉnh theo môi trường; giả mã này chỉ là một phép phát hiện ứng viên. Không nên gắn nhãn “tấn công chắc chắn” nếu không có kiểm chứng thêm. Nhóm kiểm thử đánh giá ba điểm riêng: log có xuất hiện, rule có phát tín hiệu và tín hiệu có đủ ngữ cảnh để analyst quyết định.

Kiểm tra một alert mẫu:

~~~json
{
  "alert_id": "soc-lab-404",
  "rule_id": "NET-SERVICE-ENUMERATION-CANDIDATE",
  "created_time": "2026-11-28T03:04:00Z",
  "src_ip": "192.0.2.15",
  "dst_ip": "198.51.100.20",
  "first_seen": "2026-11-28T03:00:00Z",
  "last_seen": "2026-11-28T03:03:20Z",
  "port_count": 18,
  "related_event_ids": ["evt-rt08-001-001", "evt-rt08-001-018"],
  "severity": "medium",
  "reason": "Nhiều kết nối bị từ chối tới các cổng khác nhau"
}
~~~

Đối chiếu **execution_id** qua dữ liệu ground truth, asset/IP mapping và **related_event_ids**; không kết luận chỉ dựa vào thời gian gần nhau. Tránh để thông tin gắn nhãn thử nghiệm trở thành điều kiện bắt buộc trong rule production.

## 8. Khi SOC bỏ sót: chẩn đoán đúng lớp lỗi

Dùng chứng cứ để đi từ gốc đến ngọn, thay vì kết luận chung chung rằng SOC yếu.

~~~mermaid
flowchart TD
    A["Ground truth: hành vi đã xảy ra?"] -->|Không| X["INVALID_TEST: sửa phép thử"]
    A -->|Có| B{"Sensor thấy sự kiện?"}
    B -->|Không| C["Blind spot: vị trí sensor,\npolicy log, lưu lượng mã hóa"]
    B -->|Có| D{"Log vào kho phân tích?"}
    D -->|Không| E["Pipeline: parser, drop,\nquota, connector, clock"]
    D -->|Có| F{"Rule tạo alert đúng?"}
    F -->|Không| G["Detection: filter, ngưỡng,\ncorrelation, field mapping"]
    F -->|Có| H{"SOC xử lý đạt yêu cầu?"}
    H -->|Không| I["Operations: routing, ca trực,\nrunbook, backlog, escalation"]
    H -->|Có| J["PASS: lưu bằng chứng\nvà kiểm thử hồi quy"]
~~~

| Điểm nghẽn | Dấu hiệu | Cải tiến có thể đo lại |
| --- | --- | --- |
| Blind spot | Không có sự kiện ở chặng mạng đang thử | Bổ sung sensor / flow log, điều chỉnh điểm đặt hoặc giới hạn kết luận phạm vi |
| Data pipeline | Sensor có log, SIEM thiếu hoặc trễ | Sửa ingest, parser, field mapping, retention, cảnh báo mất nguồn log |
| Detection logic | Log có đủ nhưng rule im lặng | Sửa rule, threshold, join key; thử với dữ liệu positive và negative |
| Alert quality | Có alert nhưng thiếu nguồn, tài sản hoặc bằng chứng | Enrichment user/asset/zone, correlation ID, đường dẫn truy vết |
| Triage workflow | Alert đúng nhưng bị đóng hoặc phân loại sai | Cập nhật playbook, hướng dẫn analyst, escalation, SLA |
| Response workflow | Case được xác định nhưng phản ứng chậm | Xem phê duyệt, owner, quyền thực thi, kênh điều phối và diễn tập |
| Measurement | Không có timestamp chuẩn hay không gắn được execution_id | Hoàn thiện ground truth, đồng bộ đồng hồ, tiêu chí matching |

Mỗi phát hiện nên đi cùng **owner, mức độ ưu tiên, kế hoạch sửa và kịch bản retest**. Tối ưu một rule có thể làm tăng recall nhưng cũng tăng FP; vì vậy phải chạy lại negative controls trước khi triển khai rộng.

## 9. Sai lầm phổ biến khi công bố “SOC phát hiện tốt”

1. **Lấy số rule làm coverage:** Một rule có thể chỉ bắt được một biến thể hành vi; cần phép thử với dữ liệu đối chứng và danh mục kỹ thuật rõ ràng.
2. **Đếm số alert thành công:** Một kịch bản có hàng trăm alert lặp không chứng minh phát hiện một trăm tình huống; cần de-duplicate theo đơn vị đo.
3. **Chỉ thử positive:** Phát hiện tất cả bản ghi tổng hợp bằng một rule quá rộng có thể gây FP nghiêm trọng khi áp dụng thực tế.
4. **Trộn prevention với detection:** Tường lửa chặn lưu lượng là tín hiệu prevention; phải chứng minh log hoặc alert được SOC nhận nếu mục tiêu kiểm tra SOC.
5. **Không đo data loss:** Thiếu sensor hoặc sai parser khiến cảnh báo không xuất hiện; sửa rule đơn thuần không giải quyết nguyên nhân.
6. **Không khóa phạm vi và cửa sổ:** Có thể lấy alert từ một đợt kiểm thử trước hoặc từ hoạt động quản trị thật để ghép nhầm.
7. **Chỉ báo MTTD của TP:** Bỏ qua FN làm hệ thống có vẻ nhanh nhưng không bao phủ.
8. **Tự loại “unobservable” khỏi mẫu:** Kết quả tốt giả tạo do loại bỏ các vùng không có telemetry.
9. **Thiếu điều kiện an toàn/đồng thuận:** Bài thử có thể gây gián đoạn hoặc khiến analyst phản ứng lên tài sản ngoài phạm vi.
10. **Không đánh giá lại sau khi sửa:** Thay đổi parser, network topology, IP mapping, dịch vụ cloud và rule có thể làm một phát hiện từng tốt trở nên lỗi thời.

## 10. Mẫu báo cáo cho một đợt kiểm thử

Một báo cáo kỹ thuật đủ để nhóm red team, blue team, SOC manager và kỹ sư nền tảng cùng kiểm chứng nên có:

| Trường | Nội dung minh họa |
| --- | --- |
| Mục tiêu | Xác minh khả năng cảnh báo dò dịch vụ trên phân đoạn lab |
| Phạm vi | Segment LAB-A tới LAB-B, ngày/giờ UTC, danh sách tài sản được phép |
| Chế độ | Purple team có thông báo trước |
| Kỹ thuật | ATT&CK T1046 (nếu phù hợp với kịch bản) |
| Ground truth | execution_id, t0, kết quả tạo sự kiện, file chứng cứ/hash |
| Expected | Firewall ghi deny; SIEM phát alert có source/destination trong 10 phút |
| Observed | Sensor log ID, ingest t2, alert ID t3, case ID t4/t5 |
| Kết quả | DETECTED / DETECTED_LATE / NOT_DETECTED / UNOBSERVABLE / INVALID_TEST |
| KPI | TP, FP, FN, TN, recall, precision, FPR, coverage, TTD, TTA, tỷ lệ SLA |
| Nguyên nhân | Ví dụ không map được src_ip sau NAT hoặc chưa thu log east–west |
| Hành động | Owner sửa collector/rule/runbook, ngày retest và tiêu chí nghiệm thu |

Nên lưu bảng tổng hợp:

~~~text
test_run,scenario_id,execution_id,expected_signal,telemetry_present,
alert_id,t0_utc,t2_utc,t3_utc,t4_utc,triage_outcome,
detection_result,ttd_seconds,owner,evidence_reference
~~~

Không công khai IP thực, dữ liệu định danh, token, log nhạy cảm hoặc phương thức mô phỏng có thể ảnh hưởng đến hệ thống. Phân quyền báo cáo và giới hạn thời gian giữ chứng cứ theo chính sách của tổ chức.

Một kết quả có thể hành động được cần nói rõ:

- **Đã kiểm thử điều gì:** phạm vi, số lần chạy, tầng cảm biến và điều kiện kích hoạt.
- **Đã quan sát điều gì:** bằng chứng và kết quả phân loại, bao gồm thất bại và các phép thử không hợp lệ.
- **Tác động đến vận hành:** tình huống nào có thể bị bỏ sót, độ trễ nào gây rủi ro và mức độ báo nhầm.
- **Sẽ sửa và kiểm tra lại thế nào:** người phụ trách, thời điểm, định nghĩa đạt và negative control đi kèm.

## 11. Bài tập thực hành trong lab

**Bài toán:** Một SOC đang giám sát phân đoạn mạng thử nghiệm. Kỹ sư muốn đánh giá tính đầy đủ của log và độ chính xác của cảnh báo từ sự kiện firewall deny, DNS và VPN.

**Chuẩn bị:** Dùng hai máy ảo hoặc các bản ghi tổng hợp; đồng hồ UTC đồng bộ, collector/SIEM lab, quy tắc phát hiện ứng viên và danh sách tài sản đã duyệt. Xác định ba positive scenario cùng ít nhất ba negative control từ các hoạt động bình thường. Đặt cửa sổ quan sát và SLA trước khi chạy.

**Thực hiện:**

1. Viết giả thuyết, đặt scenario_id và execution_id cho từng trường hợp.
2. Tạo hoặc phát lại bản ghi vô hại; ghi t0 và bảo toàn event ID.
3. Truy từ sensor qua collector đến alert, ghi t1, t2, t3; kiểm tra độ đầy đủ trường dữ liệu.
4. Nếu có analyst thực hành, ghi t4 và t5, kiểm tra phân loại theo runbook.
5. Chấm kết quả với ground truth, lập confusion matrix ở một đơn vị đo duy nhất và tính các chỉ số đủ mẫu số.
6. Chọn một FN hoặc FP, xác định nguyên nhân, sửa cấu hình/rule trong lab và chạy lại cả positive lẫn negative control.

**Tiêu chí nghiệm thu:** Có bảng dữ liệu đối chứng, liên kết được từ execution_id tới bằng chứng, phân biệt được visibility/detection/triage, công bố tỷ lệ thành công *và* bỏ sót, giải thích được độ trễ, chỉ ra một cải tiến và một phép retest xác nhận cải tiến không làm báo nhầm tăng vô lý.

## 12. Tự kiểm tra

**Câu 1.** Một IPS chặn kết nối đáng ngờ nhưng SOC không nhận alert. Có nên ghi TP cho SOC không?

**Đáp án:** Không, nếu tiêu chí yêu cầu cảnh báo đến SOC. Ghi nhận **prevention success** riêng, sau đó phân tích sensor/pipeline/rule để biết vì sao không có detection đúng tiêu chí.

**Câu 2.** Trong 20 positive test hợp lệ, có 12 alert đúng, 5 không có log và 3 có log nhưng không tạo alert. Detection recall end-to-end là bao nhiêu?

**Đáp án:** TP = 12; FN = 5 + 3 = 8; recall = 12/20 = **60%**. Năm trường hợp thiếu log là blind spot, vẫn thuộc thất bại end-to-end.

**Câu 3.** MTTD của các ca được phát hiện giảm từ 8 xuống 3 phút sau khi đổi rule, nhưng recall giảm từ 80% xuống 30%. Có thể kết luận SOC tốt hơn không?

**Đáp án:** Chưa. Alert đến nhanh hơn trên tập được phát hiện nhưng nhiều ca hơn bị bỏ sót. Cần so sánh recall, precision, FN, FP, tỷ lệ đạt SLA và chi phí vận hành trên cùng bộ kiểm thử.

**Câu 4.** Một hành vi bị mô phỏng đúng nhưng không có log vì sensor chỉ đặt tại Internet gateway, trong khi lưu lượng đi east–west. Đâu là thay đổi ưu tiên?

**Đáp án:** Xử lý **visibility**: bổ sung nguồn quan sát phù hợp cho east–west, kiểm tra phạm vi thu log và định tuyến telemetry; sau đó mới đánh giá lại rule.

**Câu 5.** Vì sao cần negative control khi thử quy tắc phát hiện truy vấn DNS đều đặn?

**Đáp án:** Nhiều ứng dụng hợp lệ truy vấn định kỳ. Không có đối chứng sẽ khó biết quy tắc đang phát hiện hoạt động nguy hiểm hay chỉ báo động nhầm trước các heartbeat bình thường.

---

**Điểm cốt lõi:** Năng lực phát hiện của SOC là kết quả đo được qua một chuỗi bằng chứng: **hành vi có ground truth → telemetry → alert đủ ngữ cảnh → triage đúng → phản ứng đạt yêu cầu**. Mỗi lần kiểm thử phải công bố rõ mẫu số, điều kiện tính đạt, độ trễ, trường hợp bỏ sót và kế hoạch cải tiến để kết luận có giá trị kỹ thuật và vận hành.
