# Đánh giá kết quả và đề xuất cải tiến

## 1. Mục tiêu của bước đánh giá sau dự án thực hành

Hoàn thành một phòng lab bảo mật mạng không chỉ là triển khai được firewall, VPN, IDS/IPS hoặc phân đoạn VLAN. Một bài lab có giá trị khi người học có thể **chứng minh các lớp kiểm soát thực hiện đúng mục tiêu**, chỉ ra điểm chưa đạt, giải thích rủi ro còn tồn tại và đưa ra kế hoạch cải tiến **có thể triển khai, đo lường và kiểm thử lại**.

Ví dụ, máy người dùng truy cập ứng dụng HTTPS thành công là một tín hiệu tích cực, nhưng chưa đủ kết luận mạng được phân đoạn tốt. Cần kiểm tra thêm máy đó **không** truy cập trực tiếp database, máy ở Wi-Fi guest **không** vào mạng quản trị, và log chặn có được thu thập để phục vụ điều tra. Một cấu hình trông đúng trên màn hình quản trị có thể không đồng nhất với chính sách thực tế sau NAT, định tuyến, failover hoặc thay đổi trên đám mây.

Bài thuộc chương **Dự án thực hành bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Phạm vi đánh giá bao gồm các kỹ năng của module: phân đoạn mạng, firewall, VPN và xác thực kết nối, IDS/IPS và giám sát, DNS, Wi-Fi, quản trị thiết bị, các kiểm soát cloud/hybrid, phân tích lưu lượng và mô hình hóa đe dọa.

**Sau bài học, người học có thể:**

1. Xác định mục tiêu, tiêu chí nghiệm thu và phạm vi đánh giá của một lab.
2. Thu thập bằng chứng từ test, cấu hình đang chạy, log, flow/PCAP và hệ thống giám sát.
3. Phân biệt **PASS**, **FAIL**, **INCONCLUSIVE**, **NOT_TESTED** và trường hợp kết quả chỉ đạt một phần.
4. Tính các chỉ số có mẫu số rõ ràng mà không giấu kết quả thất bại hoặc thiếu dữ liệu.
5. Phân tích nguyên nhân gốc, lượng hóa và ưu tiên rủi ro thay vì chỉ liệt kê lỗi kỹ thuật.
6. Viết đề xuất cải tiến gồm owner, biện pháp, phụ thuộc, điều kiện nghiệm thu, rollback và retest.
7. Trình bày báo cáo cuối lab có thể được người khác kiểm chứng và tái sử dụng.

> **Phân biệt quan trọng:** “Đã cấu hình” là một trạng thái triển khai; “đã kiểm thử” là trạng thái xác minh; “được chấp nhận” là quyết định dựa trên kết quả và rủi ro. Ba trạng thái này không đồng nghĩa.

## 2. Định nghĩa môi trường và giới hạn đánh giá

Trước khi chấm điểm, ghi rõ **cái gì đã được thử và cái gì chưa**. Không được suy rộng từ một topology lab nhỏ thành mức an toàn của mạng sản xuất.

### 2.1. Topology lab tham chiếu

Giả sử phòng lab được xây trong môi trường cô lập, dùng thiết bị ảo hoặc máy chủ/thiết bị do người thực hành được phép quản lý:

- **USER:** máy trạm người dùng nội bộ.
- **APP:** máy chủ ứng dụng HTTPS.
- **DATA:** dịch vụ database chỉ dành cho backend đã phê duyệt.
- **MGMT:** giao diện quản trị của switch, router và firewall, truy cập từ bastion.
- **GUEST:** Wi-Fi dành cho khách, không được vào vùng nội bộ hoặc quản trị.
- **VPN:** người dùng từ xa được cấp quyền theo ứng dụng/danh tính.
- **CLOUD:** workload cloud trong một vùng tách biệt, được bảo vệ bằng security group/cloud firewall.
- **SECURITY:** resolver DNS, IDS/IPS/NDR sensor và bộ thu log/SIEM thử nghiệm.

~~~mermaid
flowchart LR
    User["USER"] -->|"HTTPS được duyệt"| FW["Firewall / phân đoạn"]
    VPN["VPN + Identity"] --> FW
    Guest["GUEST Wi-Fi"] -.->|"Default deny"| MGMT["MGMT / thiết bị mạng"]
    FW --> APP["APP / HTTPS"]
    APP -->|"DB port hợp lệ"| DATA["DATA / Database"]
    User -.->|"Default deny"| DATA
    B["Bastion"] -->|"SSH/HTTPS đã cấp quyền"| MGMT
    APP -->|"Kết nối đã duyệt"| CLOUD["CLOUD workloads"]
    DNS["Resolver DNS nội bộ"] --- FW
    FW -->|"Flow / audit logs"| SIEM["Collector / SIEM"]
    IDS["IDS/IPS/NDR"] -->|"Telemetry"| SIEM
~~~

Sơ đồ minh họa **ý định bảo mật**, không mặc định mọi gói đều đi qua cùng firewall. Luồng thực có thể chịu nhiều lớp kiểm soát: router ACL, host firewall, NAT, Wi-Fi client isolation, ZTNA policy, security group hoặc container NetworkPolicy. Bản đánh giá phải ghi **điểm thực thi** và đường đi thực tế, không chỉ dựa vào mũi tên trên sơ đồ.

### 2.2. Giới hạn và điều kiện an toàn

Chỉ thực hiện kiểm thử trên tài sản **được ủy quyền**, trong phạm vi IP/tên miền, tài khoản, thời gian và kỹ thuật đã thống nhất. Dùng dữ liệu giả, endpoint thử nghiệm, tác vụ đọc trạng thái và lưu lượng có giới hạn. Không thu thập mật khẩu thật, không trích xuất dữ liệu nghiệp vụ và không tạo lưu lượng làm mất dịch vụ để “chứng minh” điểm yếu.

Những thông tin cần có trong *lab charter*:

| Trường | Nội dung phải xác định |
| --- | --- |
| Lab ID, phiên bản | Mã bài thực hành, bản sơ đồ, phiên bản chính sách và thời điểm chạy |
| Scope | Các máy, vùng, giao diện, cloud account/namespace, tài khoản và dịch vụ được phép |
| Out of scope | Tài sản sản xuất, hệ thống bên thứ ba, dữ liệu thật và hành vi không được ủy quyền |
| Người chịu trách nhiệm | Lab owner, người thực hành, người review và đầu mối dừng khẩn |
| Tiêu chí thành công | Các luồng cần được phép/chặn, chất lượng log và hiệu năng tối thiểu |
| Công cụ và giới hạn | Công cụ probe, collector, thời gian timeout, hạn mức lưu lượng và quyền tài khoản |
| Điều kiện dừng | Tác động ngoài phạm vi, mất quan sát, sai mục tiêu hoặc lỗi hạ tầng |
| Rollback | Snapshot cấu hình, đường console/OOB và cách trở lại trạng thái an toàn |

Một thay đổi cấu hình được gửi đi nhưng chưa commit hoặc chưa đồng bộ tới node dự phòng **không được tính là triển khai thành công**.

## 3. Xây dựng tiêu chí nghiệm thu từ threat model

Một báo cáo đánh giá tốt bắt đầu với **mục tiêu cần bảo vệ**, sau đó mới lựa chọn chỉ số.

### 3.1. Từ tài sản đến kiểm thử

| Tài sản/mục tiêu | Kịch bản rủi ro | Kiểm soát kỳ vọng | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| DATA | Người dùng/guest truy cập database trái quyền | Firewall/host/cloud policy default deny | Test âm từ nguồn không được phép, rule/flow evidence |
| APP | Người dùng hợp lệ không thể sử dụng ứng dụng | Allow đúng cổng, DNS, VPN/identity, TLS | Test dương end-to-end tới ứng dụng |
| MGMT | Người không được cấp quyền kết nối dịch vụ quản trị | Management isolation, bastion, AAA, ACL | Test nguồn cho phép và nguồn không cho phép |
| VPN | Tài khoản hoặc thiết bị không hợp lệ vào ứng dụng | Xác thực, MFA/posture theo thiết kế, phân quyền | Log IdP/VPN và thử quyền hợp lệ/không hợp lệ |
| DNS | Client dùng đường phân giải không được quản lý | Resolver policy và egress control | Kiểm thử resolver được duyệt và đường ngoài chính sách |
| IDS/IPS | Hành vi thử hợp lệ không được ghi nhận | Sensor coverage, event pipeline, rule/correlation | Log event time, ingest time, alert/case và bằng chứng thử |
| GUEST Wi-Fi | Khách tiếp cận mạng nội bộ | Guest isolation, ACL, policy route | Test âm từ máy guest được ủy quyền |
| CLOUD | Workload ngoài nhóm được phép vào dịch vụ nhạy cảm | Security group/cloud firewall/network policy | Test từ workload hợp lệ và workload bị từ chối |

Để liên kết với threat model, có thể mô tả **tài sản → trust boundary → kịch bản rủi ro → kiểm soát → test → evidence → kết luận**. Không cần mô phỏng tấn công gây hại; một kết nối TCP được kiểm soát và log tại nơi chặn đã đủ cho nhiều bài test phân đoạn.

### 3.2. Ba tiêu chí cần đánh giá cùng nhau

1. **Functionality:** kết nối và dịch vụ hợp lệ có hoạt động đúng không?
2. **Security effectiveness:** đường không hợp lệ có thực sự bị chặn và quyền có đủ tối thiểu không?
3. **Observability & response:** có đủ tín hiệu để phát hiện, giải thích và xử lý sai lệch không?

Đo chức năng mà không đo hiệu lực bảo mật có thể thưởng nhầm cho cấu hình `allow any any`. Đo số lượng gói bị chặn mà không thử giao dịch hợp lệ có thể tưởng một firewall cấu hình quá chặt là tốt. Đo alert mà không kiểm tra chất lượng log và quy trình xử lý cũng chưa chứng minh khả năng phản ứng.

## 4. Thu thập và bảo quản bằng chứng

### 4.1. Các nguồn dữ liệu phù hợp

| Nguồn | Có thể chứng minh | Không tự chứng minh |
| --- | --- | --- |
| **Running configuration / runtime policy** | Rule và giao diện hiện đang áp dụng trên thiết bị cụ thể | Lưu lượng đi qua đường đó và ứng dụng hoạt động |
| **Firewall rule hit / flow log** | Action, source/destination, zone, rule ID, thời điểm ở điểm thực thi | Mức độ ảnh hưởng tới toàn bộ hệ thống nếu path chưa được xác nhận |
| **Packet capture trong lab** | Gói, handshake, response và một phần đường đi | Chính sách của tất cả thiết bị trên mạng |
| **Synthetic application probe** | Giao dịch người dùng thử có thành công không | Những nguồn khác có bị chặn đúng không |
| **VPN / IdP / AAA logs** | Xác thực, cấp quyền, session và sự kiện quản trị | Toàn bộ traffic ứng dụng sau khi xác thực |
| **DNS logs** | Truy vấn/response tới resolver được quan sát | Mọi đường DNS ngoài resolver hoặc khả năng truy cập cuối |
| **IDS/IPS/NDR và SIEM** | Sensor nhìn thấy và gửi được sự kiện; có thể có alert/case | Firewall có chặn hay không khi sensor chạy passive |
| **Cloud audit / policy readback** | Thay đổi và trạng thái security group/network policy | Toàn bộ traffic đa cloud nếu không kiểm tra đường cụ thể |
| **Ticket / change / risk record** | Yêu cầu và người phê duyệt | Thay đổi đã có hiệu lực trên thiết bị thực |

Luôn phân biệt **event time**, **collector receive time** và **analyst observation time**. Đồng bộ thời gian hoặc ghi timezone và độ lệch ước lượng. Khi nguồn log mất dữ liệu, ghi **không quan sát được**; không điền “không có sự kiện” nếu thực tế chưa có khả năng nhìn thấy.

### 4.2. Traceability của một test

~~~mermaid
flowchart TD
    OBJ["Yêu cầu / threat scenario"] --> T["Test case có ID"]
    T --> P["Nguồn và điều kiện thử"]
    P --> O["Kết quả quan sát"]
    O --> E["Evidence ID + thời gian + policy version"]
    E --> C["PASS / FAIL / INCONCLUSIVE"]
    C --> R["Finding / cải tiến"]
    R --> RT["Retest và đóng finding"]
~~~

Ví dụ bản ghi kiểm thử:

~~~yaml
lab_id: NETSEC-LAB-014
test_id: N02
objective: "Guest không truy cập được dịch vụ quản trị"
owner: network-security-lab
scope:
  source_zone: GUEST
  source_host: "192.0.2.21"
  destination_zone: MGMT
  destination_host: "198.51.100.10"
  protocol: tcp
  destination_port: 22
expected: deny_new_connection
observed: tcp_handshake_completed
result: FAIL
time_utc: "2026-11-28T03:15:00Z"
policy_version: "lab-policy-v1"
evidence_ids:
  - "FLOW-N02-001"
  - "HOST-N02-001"
notes: "Chỉ kiểm tra kết nối TCP; không đăng nhập hay thử lấy quyền"
~~~

Đây là **bản ghi ví dụ giả lập**, không phải kết quả từ một hệ thống thật. Các địa chỉ `192.0.2.0/24` và `198.51.100.0/24` là dải dành cho tài liệu; thay bằng thông tin của mạng lab đã được duyệt nếu triển khai thực hành.

### 4.3. Chất lượng và tính toàn vẹn chứng cứ

Mỗi evidence ID nên liên kết tới nguồn, thời gian, môi trường, quyền thực hiện, bộ lọc, phiên bản cấu hình và người thu thập. Không đưa token, secret, khóa riêng hoặc nội dung dữ liệu cá nhân vào báo cáo. Nếu cần lưu PCAP/log chứa dữ liệu nhạy cảm, giới hạn truy cập và thời hạn giữ theo quy định.

Ảnh chụp màn hình GUI đơn lẻ có thể thiếu ngữ cảnh: rule chưa deploy, ảnh chỉ hiển thị config candidate hoặc dashboard đang lấy dữ liệu cũ. Nên kèm readback của **trạng thái đang chạy** và bằng chứng lưu lượng.

## 5. Quy tắc kết luận kết quả kiểm thử

### 5.1. Phân loại theo mức chắc chắn

| Trạng thái | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **PASS** | Đúng kết quả mong đợi và có chứng cứ đủ theo tiêu chí nghiệm thu | Kết nối sai nguồn bị chặn đúng rule, flow log thể hiện deny |
| **FAIL** | Có chứng cứ đáng tin cho thấy hành vi trái kỳ vọng | Guest hoàn tất kết nối TCP đến cổng quản trị lẽ ra phải bị chặn |
| **PARTIAL** | Chỉ một phần tiêu chí đạt; cần nêu từng phần | SSH giới hạn nguồn đúng nhưng audit login thiếu |
| **INCONCLUSIVE** | Đã thử nhưng thiếu bằng chứng hoặc điều kiện đo không hợp lệ, không thể kết luận | Không thấy alert do collector không gửi log, chưa biết sensor có nhận gói không |
| **NOT_TESTED** | Chưa thực hiện thử nghiệm có thể quan sát | Chưa kiểm tra đường dự phòng sau HA failover |

Không được đổi **INCONCLUSIVE** thành PASS chỉ vì không xuất hiện hành vi bất thường. Nếu không có alert từ IDS/IPS, nguyên nhân có thể là sensor không nhìn thấy traffic, signature không phù hợp, pipeline trễ hoặc test không chạy đúng; cần kiểm tra từng chặng trước khi kết luận.

**PARTIAL** nên có kết luận **cho từng tiêu chí con**. Nếu một điều kiện bảo mật bắt buộc thất bại, trạng thái tổng thể phải phản ánh **không đủ điều kiện nghiệm thu**, không được hòa vào các tiêu chí nhỏ đã đạt.

### 5.2. Tính hợp lệ của negative test

Kết quả “timeout” hoặc “connection refused” từ host thử **không tự động là PASS**:

- **Timeout:** có thể do firewall drop, route lỗi, host tắt hoặc mất phản hồi.
- **Connection refused:** đích hoặc thiết bị trung gian trả RST, chưa chắc do firewall deny.
- **DNS resolution error:** thất bại phân giải tên, chưa chứng minh network ACL chặn kết nối.
- **Không nhận alert:** chưa chứng minh IDS đã bỏ sót nếu không biết sensor có nhận sự kiện.

Với test âm, xác minh **nguồn đúng**, **đường đi đúng**, **đích/port đúng**, **phiên mới**, **nơi thực thi policy** và **bằng chứng chặn**. Với test dương, kiểm chứng cả chức năng ứng dụng và quyền truy cập, không chỉ TCP handshake.

## 6. Ma trận kiểm thử cuối lab

Ma trận dưới đây là một **bộ dữ liệu giả lập nhất quán**, dùng để luyện cách phân tích kết quả. Đây không phải log từ file khác, không phải kết quả của hệ thống người học và không phải tuyên bố sản phẩm đã an toàn.

| Test ID | Mục tiêu / hành vi được kiểm tra | Kỳ vọng | Quan sát giả lập | Kết quả |
| --- | --- | --- | --- | --- |
| **P01** | USER → APP qua TCP/443 | Allow đúng ứng dụng/TLS | Giao dịch HTTPS hợp lệ thành công | **PASS** |
| **N01** | USER → DATA qua TCP/5432 | Deny | Firewall ghi nhận deny tại zone DATA | **PASS** |
| **P02** | APP backend → DATA qua TCP/5432 | Allow đúng backend | Giao dịch database thử thành công | **PASS** |
| **N02** | GUEST Wi-Fi → MGMT qua TCP/22 | Deny | TCP handshake hoàn tất ngoài kỳ vọng | **FAIL** |
| **P03** | Bastion → MGMT qua SSH | Allow + audit | SSH dùng tài khoản test hợp lệ, audit đầy đủ | **PASS** |
| **P04** | VPN user được cấp quyền → APP qua HTTPS | Allow theo identity | MFA/ủy quyền đạt, ứng dụng phản hồi đúng | **PASS** |
| **N03** | VPN user không có quyền → APP | Deny ở lớp identity | ZTNA/VPN policy từ chối, có log | **PASS** |
| **P05** | Client → DNS resolver được duyệt | Allow và phân giải đúng | Truy vấn tên miền test thành công | **PASS** |
| **N04** | Client → DNS resolver ngoài chính sách qua UDP/53 | Deny theo egress policy | Truy vấn ngoài resolver vẫn nhận phản hồi | **FAIL** |
| **P06** | Cloud APP → API được duyệt | Allow theo policy | Truy vấn API test thành công | **PASS** |
| **N05** | Cloud workload không được duyệt → DATA | Deny | Security group/flow log ghi nhận chặn | **PASS** |
| **T01** | Mô phỏng sự kiện benign để kiểm tra IDS/NDR → SIEM | Có telemetry/cảnh báo test theo tiêu chí | Không thấy alert; chưa xác minh đường sensor → collector | **INCONCLUSIVE** |

**Phép thử có giới hạn:** thử N02 ở mức kiểm tra kết nối tới đúng cổng, **không thử đăng nhập trái quyền**. N04 chỉ thử DNS resolver nằm trong môi trường được tổ chức cho phép kiểm tra, không quét hoặc gửi truy vấn hàng loạt. T01 chỉ dùng sự kiện test lành tính và cơ chế test được thiết kế cho sensor.

### 6.1. Kết luận trực tiếp từ ma trận

- **9 PASS**: các luồng được phép quan trọng và một số đường cấm đã được xác nhận.
- **2 FAIL**: ranh giới GUEST → MGMT và chính sách DNS egress chưa đạt yêu cầu.
- **1 INCONCLUSIVE**: chưa đủ bằng chứng để đánh giá chuỗi quan sát IDS/NDR → SIEM.
- Kết quả **không đủ để nghiệm thu kiến trúc bảo mật** nếu N02 là điều kiện bắt buộc, dù phần lớn bài test đã đạt.
- Các luồng/tài sản **không nằm trong ma trận** (ví dụ đường HA, IPv6 hoặc workload khác) chưa được chứng minh bởi tập test này.

Một bài đánh giá không nên chỉ kết thúc bằng “9/12 đã đạt”. Cần nêu rõ **2 thất bại ảnh hưởng gì**, **1 trường hợp chưa biết ảnh hưởng mức tin cậy ra sao** và những việc phải làm trước khi nghiệm thu.

## 7. Chọn chỉ số có mẫu số rõ ràng

### 7.1. Những tỷ lệ không được đánh đồng

Đặt:

- \(P\): số test PASS.
- \(F\): số test FAIL.
- \(I\): số test INCONCLUSIVE.
- \(N\): số test NOT_TESTED.
- \(R\): số test PARTIAL (nếu có), cần xử lý theo tiêu chí con trước khi chấm điểm.

Với tập **không có PARTIAL** như ví dụ:

\[
PlannedTests = P+F+I+N.
\]

\[
ConclusiveRate = \frac{P+F}{PlannedTests}\times100\%.
\]

\[
PassRateOnConclusive = \frac{P}{P+F}\times100\%.
\]

Khi mẫu số bằng 0, phải hiển thị **N/A**, không tự đặt tỷ lệ thành 100%.

Từ ma trận:

\[
PlannedTests=9+2+1+0=12.
\]

\[
ConclusiveRate=\frac{11}{12}\times100\%\approx91{,}67\%.
\]

\[
PassRateOnConclusive=\frac{9}{11}\times100\%\approx81{,}82\%.
\]

Hai tỷ lệ có ý nghĩa khác nhau. **91,67%** là tỷ lệ test có thể kết luận; **81,82%** là tỷ lệ đạt trong những test đã kết luận. Không dùng **9/12 = 75%** rồi gọi chung là “pass rate” nếu chưa nêu cách xử lý test INCONCLUSIVE. Để quản trị rủi ro, phải hiển thị **cả số FAIL và INCONCLUSIVE**, không để một chỉ số tổng che mất lỗi nghiêm trọng.

### 7.2. Chỉ số theo nhóm kiểm soát

| Nhóm | Chỉ số gợi ý | Điều kiện diễn giải |
| --- | --- | --- |
| **Network policy** | Tỷ lệ test allow/deny đúng | Đánh giá riêng test dương và âm; cần chứng cứ nơi thực thi |
| **Identity/VPN** | Tỷ lệ user đúng quyền vào được và sai quyền bị từ chối | Kiểm tra MFA/posture/role theo khả năng hệ thống |
| **Telemetry** | Test case có event tới collector và đủ trường / test case đủ điều kiện | “Có log” chưa có nghĩa alert hoặc triage đúng |
| **IDS/IPS** | Test phát hiện có điều kiện đầu vào hợp lệ / test mục tiêu | Phân biệt sensor thấy sự kiện, rule chạy, alert được triage |
| **DNS** | Resolver được duyệt hoạt động; đường bypass bị chặn | Xét UDP/TCP 53, DoH/DoT nếu chính sách áp dụng |
| **Cloud** | Policy deploy/readback + test dương/âm theo workload | Kiểm tra tag, account/region, route và security group |
| **Operations** | Thay đổi có kiểm thử sau triển khai / thay đổi cần kiểm thử | Review rollback, logging, HA và drift |
| **Coverage** | Phần ranh giới/tài sản quan trọng được thử / tổng ranh giới cần thử | Phải dựa trên inventory đáng tin, không dựa trên số host đã mở |

Các mục tiêu như “mọi luồng từ GUEST tới MGMT phải bị chặn” có thể là **điều kiện bắt buộc**, không nên chuyển thành một mức phần trăm cho phép sai sót. Tỷ lệ tổng hợp chỉ hỗ trợ quản trị, không thay thế kết luận về các yêu cầu cốt lõi.

### 7.3. Thời gian và hiệu năng

Nếu đo độ trễ VPN, DNS hoặc phản hồi ứng dụng, cần đặt baseline trước khi thay policy và đo lại dưới tải tương đương. Có thể dùng p50/p95/p99, tỷ lệ lỗi, packet loss và số kết nối đồng thời theo phạm vi thích hợp. Đừng kết luận “firewall mới làm ứng dụng chậm” nếu chưa tách DNS delay, TLS, database, route, host CPU và tải thử nghiệm.

Giới hạn và ngưỡng chấp nhận phải đến từ **mục tiêu lab đã thống nhất** hoặc SLO của dịch vụ. Nếu không có baseline, ghi **PENDING BASELINE**; không sáng tạo một ngưỡng như “phải dưới 10 ms” rồi chấm đạt/rớt tùy ý.

## 8. Phân tích phát hiện và nguyên nhân gốc

Không nên nhảy từ kết quả test sang việc thêm một rule mới mà chưa biết nguyên nhân. Với mỗi phát hiện, tách bốn lớp: **quan sát → điều kiện thực thi → giả thuyết nguyên nhân → phép kiểm chứng giả thuyết**.

### 8.1. Finding F-01: GUEST kết nối được tới MGMT

| Mục | Nội dung cần điều tra |
| --- | --- |
| Quan sát | N02 thấy TCP handshake tới TCP/22 của IP quản trị thành công |
| Rủi ro | Mở đường mạng tới management plane từ vùng ít tin cậy; không đồng nghĩa đã chiếm quyền quản trị |
| Giả thuyết | Sai ACL trên VLAN guest, route khác đường dự kiến, rule NAT/any, IPv6 hoặc interface quản trị lắng nghe quá rộng |
| Chứng cứ cần có | IP nguồn thực tế, zone/interface, route, NAT, rule hit, SSH listening interfaces, policy đang chạy, log |
| Hành động tức thời trong lab | Dừng sử dụng đường không phù hợp, cô lập đúng vùng và xác định nơi lọc thực tế |
| Chứng minh đã sửa | Guest không mở được phiên TCP tới MGMT, có deny evidence; bastion vẫn SSH và audit đúng |

Không tự tuyên bố **SSH bị bẻ khóa** khi bằng chứng mới chỉ là TCP handshake. Phải mô tả đúng mức ảnh hưởng đã chứng minh: **mở bề mặt quản trị trái yêu cầu phân đoạn**.

### 8.2. Finding F-02: DNS có đường ra ngoài chính sách

| Mục | Nội dung cần điều tra |
| --- | --- |
| Quan sát | N04 nhận phản hồi DNS từ resolver không được cho phép |
| Rủi ro | Client có thể bỏ qua DNS policy hoặc làm mất telemetry nếu truy vấn không qua resolver quản lý |
| Giả thuyết | Egress filter thiếu rule, cloud security group mở rộng, NAT path bypass, rule chỉ xét TCP hoặc chưa xét UDP |
| Kiểm chứng | Đường tới resolver, UDP/TCP 53, rule/flow log, chính sách DoH/DoT nếu thiết kế yêu cầu |
| Hành động | Định nghĩa resolver cho phép, thu hẹp egress, xác nhận ứng dụng hợp lệ vẫn phân giải tên được |
| Retest | Client dùng resolver nội bộ đạt; đường tới resolver ngoài policy bị chặn với bằng chứng |

Không tự động chặn mọi HTTPS chỉ để ngăn DNS-over-HTTPS. Chính sách cần xét khả năng quản lý endpoint, proxy, domain/application control và các phụ thuộc hợp lệ trước khi triển khai.

### 8.3. Finding F-03: Thiếu bằng chứng IDS/NDR → SIEM

| Mục | Nội dung cần điều tra |
| --- | --- |
| Quan sát | T01 không tạo alert quan sát được, chưa xác minh sensor có nhận gói |
| Tình trạng | **INCONCLUSIVE**, không thể kết luận IDS hoàn toàn không phát hiện |
| Giả thuyết | SPAN/TAP sai đường, cảm biến ở passive mode, rule chưa bật, dữ liệu bị lọc, pipeline ingest trễ hoặc dashboard/query sai |
| Chứng cứ cần có | Packet/sensor receive counter, event time, collector ingest, rule ID, alert/case |
| Hành động | Kiểm tra từng chặng sensor → event → collector → detection → case |
| Retest | Test event được tạo trong phạm vi, đến collector đủ field và có kết quả theo tiêu chí đã định |

Nếu sau điều tra xác minh **bắt buộc phải có log nhưng nguồn không gửi**, cần mở **finding riêng về telemetry health** với mức ưu tiên phù hợp. Không che rủi ro thiếu khả năng quan sát bằng cách giữ mã T01 ở trạng thái INCONCLUSIVE mãi mãi.

### 8.4. Kỹ thuật tìm nguyên nhân

Một công cụ đơn giản là **5 Whys**: tại sao phép thử sai? Vì sao cấu hình khác ý định? Vì sao quy trình review/deploy không phát hiện? Vì sao test âm không có trong checklist? Vì sao owner hoặc nguồn sự thật không rõ?

Kết quả nên phân loại:

- **Thiết kế:** trust boundary/luồng được phép chưa rõ hoặc mô hình không bao phủ.
- **Cấu hình:** rule, object, interface, route, NAT hoặc identity mapping sai.
- **Triển khai:** policy chưa commit, không đồng bộ HA, controller/cloud chưa apply.
- **Quan sát:** không có log, log mất field, sensor không đi đúng đường, chênh thời gian.
- **Quy trình:** thiếu change review, test âm, owner, expiry hoặc retest.

Không được khẳng định nguyên nhân gốc từ một kết quả probe duy nhất. Mỗi giả thuyết cần **bằng chứng xác nhận hoặc bác bỏ**.

## 9. Ưu tiên phát hiện theo rủi ro, không theo số lượng

Một điểm yếu ở management plane có thể nghiêm trọng hơn nhiều lỗi về trình bày dashboard dù số lượng điểm yếu chỉ là một. Chọn tiêu chí ưu tiên dựa trên:

- **Khả năng bị tiếp cận:** từ Internet, guest, VPN user thông thường, workload ít tin cậy hay chỉ từ bastion.
- **Tác động tiềm năng:** dữ liệu, kiểm soát thiết bị, khả năng lan rộng, tính sẵn sàng và khả năng phát hiện.
- **Biện pháp bảo vệ hiện có:** AAA/MFA, ACL bổ sung, logging, host firewall, network segmentation.
- **Tài sản và phụ thuộc:** giá trị nghiệp vụ, phạm vi người dùng, môi trường sản xuất hay lab cô lập.
- **Độ tin cậy:** đã xác minh, có bằng chứng giới hạn hay còn thiếu dữ liệu.
- **Khả năng khắc phục:** có phương án an toàn, owner, cách test lại và rollback hay chưa.

### 9.1. Ma trận rủi ro minh họa

Nếu muốn dùng thang 1–5 cho xác suất/khả năng và tác động:

\[
RiskScore = Likelihood \times Impact.
\]

Đây là **công cụ sắp ưu tiên tương đối**, không phải mô hình định lượng xác suất tấn công hay giá trị rủi ro tiền tệ. Các mức và ngưỡng phải được tổ chức thống nhất trước khi sử dụng.

| Finding | Likelihood (giả lập) | Impact (giả lập) | Score | Quyết định xử lý |
| --- | ---: | ---: | ---: | --- |
| **F-01: GUEST → MGMT ngoài policy** | 4 | 5 | **20/25** | **Ưu tiên cao nhất**, không nghiệm thu ranh giới quản trị |
| **F-02: DNS egress bypass** | 3 | 4 | **12/25** | **Ưu tiên cao**, làm rõ đường đi và kiểm soát egress |
| **F-03: IDS/NDR test inconclusive** | Chưa đủ dữ liệu | Chưa đủ dữ liệu | **N/A** | Điều tra độ phủ và mở finding telemetry nếu xác nhận lỗi |

Không chấm F-03 bằng 0 vì “chưa chứng minh được lỗi”. **Unknown không đồng nghĩa rủi ro thấp**. Nếu môi trường có dữ liệu nhạy cảm hoặc yêu cầu giám sát nghiêm ngặt, việc thiếu telemetry có thể là vấn đề cần ưu tiên ngay cả trước khi biết nguyên nhân.

### 9.2. Điều kiện chặn nghiệm thu

Từ trước khi chạy test, cần quy định **mandatory gates**. Với ví dụ:

- Không có đường từ **GUEST/USER tới MGMT** ngoài chính sách.
- Luồng bị cấm từ **USER tới DATA** bị chặn ở mọi đường trong phạm vi.
- Truy cập hợp lệ tới APP, DNS, VPN, backend/database không bị làm hỏng.
- Những nguồn log/sensor bắt buộc phải có bằng chứng được thu thập và kiểm tra.
- Có đường cứu hộ/rollback khi thay đổi firewall hoặc management ACL.

Nếu gate F-01 thất bại, quyết định là **NOT ACCEPTED / FIX REQUIRED**, bất kể tỷ lệ tổng hợp đạt bao nhiêu. Với F-03, có thể là **PENDING EVIDENCE**, chưa được xác nhận là đạt yêu cầu giám sát.

## 10. Viết đề xuất cải tiến có thể thực thi

Một khuyến nghị hữu ích không dừng ở “nâng cao bảo mật”, “siết firewall” hoặc “tăng monitoring”. Phải mô tả **thay đổi cụ thể, phạm vi, owner, bằng chứng kết thúc và ảnh hưởng vận hành**.

### 10.1. Mẫu một hành động cải tiến

| Trường | Nội dung |
| --- | --- |
| **Action ID** | Mã để liên kết finding, ticket, change và retest |
| **Finding / risk** | Kết quả quan sát, mức ảnh hưởng, tài sản và điều kiện |
| **Proposed change** | Cấu hình, thiết kế hoặc quy trình cần thay đổi |
| **Owner / approver** | Vai trò thực hiện, người đánh giá rủi ro và người nghiệm thu |
| **Priority / due** | Mức ưu tiên và ngày cam kết sau khi được phê duyệt |
| **Dependencies** | Inventory, owner ứng dụng, route/NAT, platform/cloud, AAA, collector |
| **Acceptance criteria** | Kết quả dương/âm và bằng chứng phải có sau sửa |
| **Risk / rollback** | Rủi ro chặn nhầm, điều kiện dừng và cách khôi phục an toàn |
| **Evidence** | Policy version, runtime readback, flow logs, test ID, người xác nhận |

### 10.2. Backlog cải tiến gợi ý từ ví dụ

| Action | Ưu tiên | Thay đổi đề xuất | Owner theo vai trò | Bằng chứng đóng việc |
| --- | --- | --- | --- | --- |
| **A-01** | P0 trong lab nếu MGMT phải cô lập tuyệt đối | Xác định path GUEST → MGMT; sửa ACL/guest isolation hoặc management binding ở đúng điểm | Network Security / NetOps | N02 **PASS** với deny evidence; P03 vẫn PASS |
| **A-02** | P1 | Thu hẹp egress DNS tới resolver được phê duyệt, kiểm soát cả đường dự phòng phù hợp | Firewall / DNS Operations | N04 **PASS**, P05 vẫn PASS |
| **A-03** | P1 để có thể đánh giá kết quả | Khôi phục hoặc xác minh sensor → collector → SIEM, làm rõ detection rule và event fields | SOC / Detection Engineering | T01 có kết luận bằng log/sensor/case hợp lệ |
| **A-04** | P1/P2 theo scope | Bổ sung các đường chưa được thử: IPv6, HA, cloud region/namespace, VPN split tunnel | Test Owner + Platform Owners | Coverage matrix cập nhật, các gate bắt buộc được test |
| **A-05** | P2 | Gắn test âm vào quy trình sau change và định nghĩa owner của rule ngoại lệ | Network Security Architecture | Mỗi thay đổi trọng yếu có test case, evidence và kết quả lưu được |

P0/P1/P2 ở đây là **nhãn ưu tiên minh họa**, chưa phải SLA thực tế. Ngày triển khai cần được chủ sở hữu và người phê duyệt đặt sau khi xét mức độ nghiêm trọng, phạm vi hệ thống và khối lượng công việc.

### 10.3. Chọn biện pháp tốt hơn thay vì “mở hoặc chặn tất cả”

**Với F-01**, cần chọn đúng lớp xử lý: sửa VLAN guest isolation, ACL trên SVI, route/firewall zone, chặn quản trị từ nguồn không tin cậy hoặc chỉ bind SSH trên management interface. Kiểm tra IPv6 và đường OOB riêng. Đừng chặn toàn mạng guest tới Internet nếu mục tiêu chỉ là ngăn vào MGMT.

**Với F-02**, xem xét resolver policy, firewall egress, endpoint DNS settings, DoH/DoT và đường cloud/proxy. Đừng chặn TCP/443 đại trà chỉ vì lo DoH nếu việc đó làm hỏng ứng dụng hợp lệ và không chứng minh đã kiểm soát DNS.

**Với F-03**, kiểm tra sensor nhận packet, event được tạo, log transport, collector parsing, correlation rule và đường thông báo. Không chỉ “tăng độ nhạy IDS” khi nguyên nhân có thể là mirror port chưa đưa đúng traffic tới sensor.

## 11. Lộ trình cải tiến theo vòng lặp

### 11.1. Các giai đoạn

~~~mermaid
flowchart TD
    A["Đánh giá kết quả / phân loại finding"] --> B["Ưu tiên theo rủi ro + điều kiện gate"]
    B --> C["Phân tích nguyên nhân và chọn phương án"]
    C --> D["Owner + change approval + rollback"]
    D --> E["Triển khai từng phạm vi"]
    E --> F["Positive, negative và telemetry retest"]
    F --> G{"Đạt tiêu chí?"}
    G -->|"Chưa"| H["Dừng / điều chỉnh / rollback an toàn"]
    H --> C
    G -->|"Đạt"| I["Ghi evidence, cập nhật baseline, đóng finding"]
    I --> J["Regression testing và theo dõi drift"]
~~~

Trình tự đề xuất:

1. **Ổn định bằng chứng:** chốt topology, nguồn test, tài khoản, time window, snapshot runtime và các trường hợp chưa rõ.
2. **Xử lý gate thất bại:** ưu tiên các đường vào MGMT/DATA trái quyền, giữ đường quản trị cứu hộ và đảm bảo test dương sau khi siết policy.
3. **Khôi phục khả năng quan sát:** không để thời gian dài mà không biết IDS/NDR có thực sự nhìn thấy luồng quan trọng.
4. **Giảm nợ thiết kế:** bổ sung source of truth cho flow matrix, object group, IAM, ngoại lệ, rule ownership và TTL/review.
5. **Tăng độ phủ:** IPv6, node HA, cloud segmentation, VPN split tunnel, Wi-Fi và các luồng egress đặc biệt.
6. **Tự động hóa retest có kiểm soát:** ưu tiên probes giới hạn và policy-as-code, có log/rollback, không tác động hệ thống khác.
7. **Bàn giao vận hành:** dashboard, checklist, runbook, owner, tiêu chí alert và lịch review theo thay đổi.

### 11.2. Quy tắc quản lý tiến độ

Không đóng action chỉ vì ticket chuyển sang “Done” hoặc rule được push từ controller. Điều kiện đóng là **runtime thay đổi đúng, test trước–sau đạt, rủi ro tồn dư được quyết định và evidence có thể truy xuất**.

Một finding có thể ở các trạng thái:

~~~text
OPEN
  -> TRIAGED
  -> ROOT_CAUSE_VERIFIED
  -> CHANGE_APPROVED
  -> IMPLEMENTED
  -> RETESTED_PASS
  -> CLOSED

Nếu không đạt:
  IMPLEMENTED -> RETEST_FAILED -> REWORK_OR_ROLLBACK

Nếu chưa đủ chứng cứ:
  TRIAGED -> PENDING_EVIDENCE -> REASSESS
~~~

Lộ trình trên là ví dụ workflow, không phải ràng buộc mọi hệ thống ticketing. Khi có risk acceptance, phải ghi **người phê duyệt, lý do, biện pháp bù trừ và ngày tái đánh giá**, không đổi tên FAIL thành PASS.

## 12. Thiết kế retest và kiểm thử hồi quy

### 12.1. Retest một thay đổi phải kiểm tra cả chức năng và bảo mật

Với **A-01** (GUEST → MGMT):

1. Xác minh policy version và nơi thay đổi được áp dụng ở runtime.
2. Từ nguồn guest đã phê duyệt, tạo một kết nối TCP mới tới cổng quản trị thử nghiệm; kỳ vọng bị deny tại điểm thực thi.
3. Từ bastion, xác minh SSH hợp lệ vẫn kết nối được, AAA/audit hoạt động.
4. Kiểm tra cùng nhóm nguồn khác trong guest segment, IPv6 và đường HA nếu thuộc phạm vi.
5. Đối chiếu flow log với test ID, timestamp và rule ID.
6. Nếu kết quả không đạt hoặc làm gián đoạn đường quản trị hợp lệ, dừng và rollback theo change.

Với **A-02** (DNS egress):

1. Client vẫn phân giải tên hợp lệ qua resolver được phê duyệt.
2. Client không truy vấn trực tiếp qua UDP/TCP 53 tới resolver không được duyệt.
3. Xem xét DoH/DoT trong phạm vi đã được quy định; không khẳng định chặn mọi cách vượt DNS chỉ từ một test UDP/53.
4. DNS logs có source/query context cần thiết theo chính sách, không lộ dữ liệu ngoài mục tiêu kiểm thử.

Với **A-03** (IDS/NDR telemetry):

1. Sensor có nhìn thấy event thử được ủy quyền không?
2. Event có được chuyển đến collector với timestamp, sensor ID, test ID và trường cần thiết không?
3. Detection rule có kích hoạt nếu test case yêu cầu alert không?
4. Case/alert có đến người trực hoặc pipeline phản ứng đúng cách không?
5. Có phân biệt *event generated*, *event ingested*, *alert fired*, *triaged correctly* không?

### 12.2. Regression test

Sau khi sửa một finding, các bài test **không liên quan trực tiếp** vẫn có thể bị ảnh hưởng. Ví dụ siết guest ACL làm lỗi DNS/DHCP captive portal, hoặc chặn DNS egress làm cloud workload không resolve được API. Tập hồi quy tối thiểu nên gồm:

| Nhóm hồi quy | Điều cần chứng minh |
| --- | --- |
| Luồng hợp lệ | APP, VPN và DB workflow còn chạy sau thay đổi |
| Default deny | Luồng bị cấm vẫn bị chặn, không phát sinh allow rộng khác |
| Quản trị/cứu hộ | Bastion, OOB, AAA và log còn hoạt động |
| DNS/NTP/PKI | Dịch vụ nền tảng không bị chặn nhầm |
| Telemetry | Log, event, alert không bị mất do đổi route/rule |
| HA/cloud | Hai node hoặc các điểm thực thi dự phòng có cấu hình đồng nhất |
| Hiệu năng | Độ trễ, tỷ lệ lỗi, tải CPU/packet drop không vượt ngưỡng đã thống nhất |

Với firewall stateful, thay đổi rule có thể **không ngắt các phiên đã thiết lập**. Nếu yêu cầu là “không khởi tạo được kết nối mới”, phải thử phiên mới; nếu yêu cầu là “không còn quyền truy cập đang tồn tại”, cần kế hoạch xử lý session state có kiểm soát theo thiết bị.

### 12.3. Điều kiện nghiệm thu cuối

Ví dụ điều kiện chốt lab:

- Mọi **mandatory gate** đã được thử và đạt, hoặc có quyết định chấp nhận rủi ro có thẩm quyền nêu rõ phạm vi và giới hạn.
- Không còn FAIL chưa có owner, phương án xử lý và mức rủi ro được đánh giá.
- Không đánh dấu INCONCLUSIVE thành PASS; có bằng chứng khắc phục hoặc kế hoạch giải quyết khoảng trống quan sát.
- Các test dương và hồi quy nghiệp vụ trọng yếu vẫn đạt.
- Những điểm thực thi đang chạy, các đường dự phòng và log có bằng chứng phù hợp với phạm vi công bố.
- Tài liệu mô tả **giới hạn đánh giá** trung thực; không nói “toàn mạng an toàn tuyệt đối”.

## 13. Mẫu báo cáo tổng kết phòng lab

Một báo cáo tốt nên được đọc theo hai lớp: **tóm tắt quyết định cho người phụ trách** và **phụ lục chứng cứ cho kỹ sư kiểm tra**.

### 13.1. Cấu trúc đề xuất

~~~markdown
# Báo cáo đánh giá Network Security Lab

## Thông tin chung
- Lab ID / Phiên bản topology / Thời điểm:
- Người thực hiện / Reviewer:
- Phạm vi, hệ thống ngoài phạm vi và giới hạn kỹ thuật:
- Các yêu cầu bắt buộc (mandatory gates):

## Tóm tắt kết quả
- Kết luận: ACCEPTED / NOT_ACCEPTED / PENDING_EVIDENCE
- Tổng test: PASS, FAIL, PARTIAL, INCONCLUSIVE, NOT_TESTED
- Tỷ lệ test kết luận được; tỷ lệ đạt trên test có kết luận
- Các rủi ro chưa được xử lý và ảnh hưởng nghiệp vụ

## Evidence và traceability
- Flow matrix / Threat model / Chính sách dự kiến:
- Rule IDs / Config versions / Test IDs:
- Log, PCAP, SIEM events, screenshots có bối cảnh:
- Ghi chú thời gian, phương pháp đo và thiếu dữ liệu:

## Findings
- Finding ID, độ tin cậy, quan sát
- Tài sản, trust boundary, ảnh hưởng
- Nguyên nhân đã chứng minh / giả thuyết còn mở
- Khuyến nghị, owner, priority, điều kiện nghiệm thu

## Kế hoạch cải tiến
- Change ID, trình tự triển khai, phụ thuộc
- Hạn được phê duyệt, tiêu chí dừng, rollback
- Positive/negative/regression retest và evidence

## Kết luận và bàn giao
- Quyết định nghiệm thu và người phê duyệt
- Rủi ro tồn dư và thời điểm xem lại
- Bài học rút ra và thay đổi quy trình cần thực hiện
~~~

### 13.2. Ví dụ executive summary

> **Tóm tắt giả lập:** Phòng lab đã thực hiện 12 test case, có 9 PASS, 2 FAIL và 1 INCONCLUSIVE. Tỷ lệ có thể kết luận là 91,67%; tỷ lệ đạt trong các test đã kết luận là 81,82%. Chưa thể nghiệm thu vì luồng GUEST tới MGMT vẫn reachable trái yêu cầu, và DNS egress có đường bypass. Chuỗi IDS/NDR đến SIEM chưa đủ bằng chứng để kết luận. Ưu tiên tiếp theo là xác minh/sửa đường GUEST–MGMT, thu hẹp DNS egress và làm rõ trạng thái telemetry; sau mỗi thay đổi cần retest và kiểm tra các luồng hợp lệ.

Phần tóm tắt nên ngắn, nhưng không được giấu **phát hiện nghiêm trọng** sau một tỷ lệ phần trăm đẹp. Nếu quyết định cuối là chưa chấp thuận, phải nêu **điều kiện cụ thể để đổi trạng thái**.

### 13.3. Bảng bàn giao findings

| ID | Hiện trạng | Rủi ro | Owner vai trò | Bước tiếp theo | Retest cần đạt |
| --- | --- | --- | --- | --- | --- |
| F-01 | FAIL | Đường guest tới management | NetOps/Network Security | Xác định path, siết ACL/isolation | N02 PASS và P03 vẫn PASS |
| F-02 | FAIL | DNS bypass ngoài chính sách | Firewall/DNS Ops | Thiết kế kiểm soát egress | N04 PASS và P05 vẫn PASS |
| F-03 | INCONCLUSIVE | Không đủ bằng chứng IDS/NDR | SOC/Detection Eng. | Kiểm tra sensor và log pipeline | T01 có kết luận có chứng cứ |
| COV-01 | NOT_TESTED | Chưa biết về IPv6/HA nếu thuộc scope | Lab Owner | Bổ sung ca kiểm thử | Có coverage matrix và test được duyệt |

Không ghi **ngày đến hạn cụ thể** thay cho người có thẩm quyền khi chưa được thống nhất. Có thể ghi “pending scheduling” và xác định rõ người sẽ ra quyết định về hạn.

## 14. Phụ lục: mẫu dữ liệu và kiểm tra kết quả chỉ đọc

### 14.1. CSV test result minh họa

~~~csv
test_id,category,result,evidence_id
P01,functional,PASS,EV-P01
N01,segmentation,PASS,EV-N01
P02,functional,PASS,EV-P02
N02,segmentation,FAIL,EV-N02
P03,management,PASS,EV-P03
P04,identity,PASS,EV-P04
N03,identity,PASS,EV-N03
P05,dns,PASS,EV-P05
N04,dns,FAIL,EV-N04
P06,cloud,PASS,EV-P06
N05,cloud,PASS,EV-N05
T01,telemetry,INCONCLUSIVE,EV-T01
~~~

Trong hệ thống thực, mỗi hàng cần thêm metadata của phép thử, nguồn/đích, chính sách, time window, người thực hiện và đường dẫn tới **evidence đã được kiểm tra**. Một chuỗi `EV-P01` trong CSV chỉ là ID, không tự chứng minh file log tồn tại.

### 14.2. Ví dụ Python tổng hợp kết quả từ CSV

Đoạn mã sau **chỉ đọc file CSV** để tính số lượng và hai tỷ lệ. Không tạo traffic, không chạy scanner, không kết nối thiết bị mạng và không tự động chấm nghiệm thu:

~~~python
import csv
from collections import Counter

VALID = {"PASS", "FAIL", "PARTIAL", "INCONCLUSIVE", "NOT_TESTED"}

def summarize(path):
    counts = Counter()
    test_ids = set()

    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"test_id", "category", "result", "evidence_id"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Missing required CSV columns")

        for row in reader:
            test_id = (row["test_id"] or "").strip()
            result = (row["result"] or "").strip().upper()
            evidence = (row["evidence_id"] or "").strip()

            if not test_id or test_id in test_ids:
                raise ValueError("Missing or duplicate test ID")
            test_ids.add(test_id)

            if result not in VALID:
                raise ValueError(f"Unsupported result for {test_id}: {result}")
            if result in {"PASS", "FAIL"} and not evidence:
                raise ValueError(f"Conclusive test has no evidence ID: {test_id}")
            counts[result] += 1

    total = sum(counts.values())
    conclusive = counts["PASS"] + counts["FAIL"]
    conclusive_rate = 100 * conclusive / total if total else None
    pass_rate = 100 * counts["PASS"] / conclusive if conclusive else None

    print("Total tests:", total)
    for status in sorted(VALID):
        print(status, counts[status])

    if counts["PARTIAL"]:
        print("WARNING: PARTIAL results need per-criterion adjudication")
    print("Conclusive rate:", f"{conclusive_rate:.2f}%" if total else "N/A")
    print("Pass rate on conclusive:", f"{pass_rate:.2f}%" if conclusive else "N/A")
    return counts

summarize("network_lab_results.csv")
~~~

Với CSV minh họa, chương trình trả về tổng **12**, **9 PASS**, **2 FAIL**, **1 INCONCLUSIVE**, *conclusive rate* xấp xỉ **91,67%** và *pass rate on conclusive* xấp xỉ **81,82%**. Hàm **không** xác thực nội dung evidence, không so khớp mandatory gates và không thay thế reviewer; việc chọn **ACCEPTED/NOT ACCEPTED/PENDING EVIDENCE** vẫn phải dựa trên rủi ro và tiêu chí đã xác định.

## 15. Những sai lầm phổ biến khi tổng kết lab

1. **Chấm theo số dịch vụ bật thành công:** có VPN/firewall/IDS nhưng không kiểm tra hiệu lực hoặc đường bypass.
2. **Chỉ thử luồng được phép:** một rule `allow any any` có thể làm mọi test chức năng đạt nhưng phá default deny.
3. **Lấy timeout làm bằng chứng đã chặn:** bỏ qua route, DNS, host firewall và trạng thái dịch vụ.
4. **Không có log nhưng ghi PASS:** mất telemetry không đồng nghĩa không xảy ra sự kiện.
5. **Dùng một tỷ lệ tổng che lỗ hổng quan trọng:** 90% bài test đạt không bù được một đường guest vào management plane.
6. **Phóng đại ảnh hưởng:** có TCP handshake không chứng minh đã đăng nhập hoặc chiếm quyền quản trị.
7. **Trộn kết quả nhiều phiên bản policy:** phải gắn test với config version và time window cụ thể.
8. **Không thử IPv6, cloud hoặc HA nhưng kết luận toàn mạng an toàn:** phải nói rõ phạm vi chưa được chứng minh.
9. **Khuyến nghị mơ hồ:** “cập nhật firewall”, “tăng bảo mật” không có owner, thay đổi, tiêu chí đóng và rollback.
10. **Sửa một lỗi làm hỏng luồng hợp lệ:** không có positive/regression retest.
11. **Đo test case nhưng không kiểm tra bằng chứng:** ID log, ảnh chụp cũ, policy chưa commit hoặc collector chậm có thể dẫn tới kết luận sai.
12. **Đóng ticket trước khi kiểm thử lại:** trạng thái “triển khai xong” khác “khắc phục có hiệu lực”.
13. **Chấm rủi ro unknown thành thấp:** vấn đề thiếu dữ liệu cần được điều tra, không được tự coi là an toàn.
14. **Không xem xét tác động vận hành:** thay đổi bảo mật có thể ảnh hưởng DNS, NTP, AAA, VPN, ứng dụng hoặc truy cập cứu hộ.
15. **Không rút bài học quy trình:** nếu ngoại lệ không owner, thiếu test âm hoặc mất log lặp lại, cần sửa cách quản lý chứ không chỉ một rule.

## 16. Checklist nghiệm thu và câu hỏi tự kiểm tra

| Hạng mục | Đạt / Chưa / Không áp dụng |
| --- | --- |
| Lab charter xác định phạm vi, quyền thực hiện, người phụ trách và giới hạn an toàn? | |
| Mỗi yêu cầu có test ID và tiêu chí PASS/FAIL từ trước khi thử? | |
| Có cả **positive tests và negative tests** cho các ranh giới trọng yếu? | |
| Test gắn đúng nguồn, đích, zone, identity, port, cấu hình và thời điểm? | |
| Có evidence thực tế (log/counter/flow/readback) thay vì chỉ đoán từ timeout? | |
| Tách rõ PASS, FAIL, PARTIAL, INCONCLUSIVE và NOT_TESTED? | |
| Các tỷ lệ có mẫu số, thời gian đo và cách xử lý dữ liệu thiếu minh bạch? | |
| Mandatory gates được đánh giá riêng, không bị hòa tan trong điểm tổng? | |
| Mỗi finding có tài sản, rủi ro, giả thuyết nguyên nhân và bằng chứng cần bổ sung? | |
| Đề xuất cải tiến nêu owner, phạm vi, mức ưu tiên, phụ thuộc, retest và rollback? | |
| Đã chạy kiểm thử hồi quy cho luồng hợp lệ sau thay đổi? | |
| Đã ghi nhận giới hạn của IPv6, HA, cloud, VPN, Wi-Fi và telemetry khi chưa thử? | |
| Đã lưu kết luận, người đánh giá, rủi ro tồn dư và việc phải làm trước khi nghiệm thu? | |
| Đã tạo kế hoạch theo dõi drift, ngoại lệ và regression test sau lab? | |

### Câu hỏi ôn tập

1. Vì sao cấu hình firewall đã được áp dụng chưa đủ chứng minh chính sách phân đoạn đạt yêu cầu?
2. Tập test có 9 PASS, 2 FAIL và 1 INCONCLUSIVE. Tỷ lệ có kết luận và tỷ lệ đạt trên test có kết luận là bao nhiêu?
3. Một máy guest mở được TCP/22 tới interface quản trị. Có thể kết luận điều gì, và **chưa** thể kết luận điều gì?
4. Nếu IDS không sinh alert, cần xem những chặng nào trước khi kết luận tính năng phát hiện thất bại?
5. Vì sao cần thử luồng hợp lệ sau khi sửa lỗi GUEST → MGMT?
6. Hai phát hiện có cùng số điểm tổng, nhưng một phát hiện ảnh hưởng đến tài sản DATA, một phát hiện chỉ thiếu metadata báo cáo. Có nên ưu tiên như nhau không?
7. Tại sao kết quả từ chính sách IPv4 không đủ để bảo đảm IPv6 đã được kiểm soát?
8. Nêu khác biệt giữa một action “IMPLEMENTED” và “RETESTED_PASS”.
9. Trong báo cáo cuối lab, làm sao biểu diễn một yêu cầu chưa thử và một yêu cầu đã thử nhưng không đủ bằng chứng?
10. Những trường nào làm cho một đề xuất “cải tiến bảo mật” trở thành một hành động có thể giao và nghiệm thu?

**Gợi ý trả lời:** (1) Cần kiểm thử luồng trên đường thực và chứng cứ runtime, không chỉ cấu hình dự kiến. (2) 11/12 ≈ 91,67%; 9/11 ≈ 81,82%. (3) Có đường kết nối TCP ngoài chính sách; chưa chứng minh đăng nhập hoặc chiếm quyền. (4) Sensor nhận gói, event generation, log transport, ingest, detection và case/triage. (5) Tránh khóa đường bastion/quản trị hợp lệ, bảo đảm availability và bảo mật cùng đạt. (6) Không, xét tài sản, độ phơi lộ, tác động và bằng chứng. (7) Policy, route và điểm thực thi IPv6 có thể khác IPv4. (8) Implemented là triển khai, retested pass có bằng chứng kiểm chứng. (9) NOT_TESTED và INCONCLUSIVE, không đổi cả hai thành PASS. (10) Finding ID, thay đổi cụ thể, owner/approver, ưu tiên/hạn, phụ thuộc, điều kiện nghiệm thu, rollback và evidence.

### Bài tập tổng kết

Dựa trên ma trận 12 test giả lập trong mục 6, hãy lập một báo cáo ngắn gồm **(a)** bảng đếm theo trạng thái, **(b)** ba finding/unknown cần xử lý, **(c)** thứ tự ưu tiên có giải thích, **(d)** các phép retest cho từng action và **(e)** kết luận nghiệm thu. Chỉ được ghi **ACCEPTED** nếu mọi mandatory gate đã đạt và không còn rủi ro chưa được quyết định theo quy trình.

**Ghi nhớ:** Đánh giá một lab network security là **chuyển quan sát thành quyết định có chứng cứ**. Bản tổng kết tốt chứng minh được cả **kết nối hợp lệ hoạt động** và **đường không hợp lệ bị chặn**, chỉ rõ **mức quan sát và độ chắc chắn**, sau đó chuyển những điểm chưa đạt thành **cải tiến cụ thể, có owner, điều kiện nghiệm thu và retest**. Mục tiêu cuối cùng không phải một điểm số đẹp mà là hệ thống bảo vệ mạng **dễ kiểm chứng, dễ vận hành và liên tục được cải thiện**.
