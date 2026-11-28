# Backup cấu hình và bảo vệ bản sao

## 1. Vai trò của sao lưu trong hardening thiết bị và dịch vụ mạng

**Backup cấu hình** là quá trình lưu lại trạng thái cấu hình có thể dùng để đối chiếu, khôi phục hoặc tái dựng thiết bị và dịch vụ mạng sau lỗi thao tác, cập nhật thất bại, sự cố phần cứng, xâm nhập hoặc mất hạ tầng quản lý. Trong chương **Hardening thiết bị và dịch vụ mạng** của mô-đun **SECURITY_NETWORK_SECURITY**, backup là một lớp phòng vệ giúp duy trì và khôi phục chính sách phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây và môi trường cloud.

Ví dụ: một thay đổi ACL trên firewall khiến các VLAN ứng dụng không liên lạc được với DNS nội bộ. Nếu có bản cấu hình trước thay đổi, metadata phiên bản và quy trình kiểm tra khôi phục, nhóm vận hành có thể xác định phần thay đổi gây lỗi và khôi phục chính sách phù hợp. Ngược lại, tệp cấu hình bị bỏ trong thư mục chia sẻ không kiểm soát có thể chứa thông tin xác thực, khóa dùng chung VPN, hostname, IP nội bộ và sơ đồ mạng. Chính bản backup khi đó trở thành một mục tiêu có giá trị với kẻ tấn công.

Hai mục tiêu phải được đáp ứng đồng thời:

1. **Khả năng khôi phục:** có phiên bản đầy đủ, đúng thời điểm, tương thích nền tảng và đã kiểm chứng rằng có thể sử dụng.
2. **Bảo vệ bản sao:** giữ bí mật, tính toàn vẹn và khả năng sẵn sàng của dữ liệu backup, đặc biệt trước lỗi vận hành hoặc tài khoản quản trị bị xâm nhập.

Backup không thay thế cấu hình chuẩn, quản lý thay đổi, giám sát drift, phân quyền hay kế hoạch khôi phục thảm họa. Nó là một phần của hệ thống phòng vệ và ứng phó sự cố.

Sau bài học, người học cần biết xác định dữ liệu phải sao lưu, thiết kế vòng đời bản sao, lựa chọn kỹ thuật lưu an toàn, kiểm tra integrity, khôi phục thử và đánh giá các rủi ro khi sao lưu cấu hình của thiết bị mạng.

## 2. Phân biệt cấu hình hiện hành, cấu hình lưu và dữ liệu phụ trợ

Trên thiết bị mạng, các thuật ngữ **running configuration**, **startup configuration**, **candidate configuration**, **committed configuration** hoặc **configuration database** có thể mang nghĩa khác nhau tùy nhà cung cấp.

| Loại dữ liệu | Nội dung | Vì sao cần chú ý |
| --- | --- | --- |
| **Running/active config** | Cấu hình thực sự đang có hiệu lực tại thời điểm lấy | Có thể chứa thay đổi chưa được lưu để khởi động lại |
| **Startup/saved config** | Cấu hình thiết bị nạp khi khởi động, tùy nền tảng | Có thể khác active config và làm lỗi tái xuất hiện sau reboot |
| **Candidate config** | Thay đổi đang chuẩn bị, chưa commit | Có thể dùng để xem thay đổi sắp áp dụng |
| **Committed version** | Phiên bản thiết bị đã xác nhận/applied | Thuận lợi cho rollback nếu nền tảng hỗ trợ |
| **Configuration as Code / IaC** | Cấu hình mong muốn trong Git, template hoặc công cụ quản lý | Chưa chứng minh cấu hình thực tế đang khớp mong muốn |
| **Secret/PKI dependencies** | Chứng chỉ, private key, PSK, tài khoản dịch vụ, secret reference | Có thể được lưu riêng hoặc bị loại khỏi export |
| **Software và trạng thái hệ thống** | Firmware, OS image, license, module, plugin, package | Có thể là điều kiện bắt buộc để restore hoạt động |
| **Runtime/session state** | NAT session, ARP, route động, VPN SA, trạng thái HA | Thường không thể khôi phục chỉ từ file cấu hình |

Không giả định lệnh xuất cấu hình của mọi thiết bị thu được tất cả thành phần. Một thiết bị có thể lưu local users trong database khác, giữ chứng chỉ/private key trong kho riêng hoặc không xuất các bí mật ở dạng có thể nhập lại. Cần ghi rõ **những gì thực sự có trong tệp**, **những gì phụ thuộc vào dịch vụ ngoài** và **những gì phải tái tạo khi khôi phục**.

### 2.1. Phạm vi thiết bị và dịch vụ cần sao lưu

| Hệ thống | Đối tượng quan trọng | Rủi ro nếu thiếu |
| --- | --- | --- |
| Router / switch | VLAN, VRF, route, routing policy, ACL, interface, SNMP/AAA settings | Mất phân đoạn, mất kết nối hoặc giảm khả năng quan sát |
| Firewall / NGFW | Zone, object, rule, NAT, IPS profile, URL filtering, identity integration | Chính sách phòng vệ bị mất hoặc bị khôi phục sai |
| VPN gateway | Tunnel, peers, proposal, route, certificate references, identity policy | Chi nhánh hoặc người dùng không kết nối được |
| DNS / DHCP | Zone, forwarders, resolver policy, lease/config, DNSSEC dependencies | Phân giải tên hoặc cấp địa chỉ sai |
| WAF / load balancer | Listener, TLS profile, VIP, backend, health check, WAF rules | Dịch vụ không còn được định tuyến hoặc bảo vệ đúng |
| IDS/IPS / NDR | Sensor settings, rule set, tuning, exception, forwarding configuration | Mất khả năng phát hiện hoặc phát sinh cảnh báo sai |
| Wi-Fi controller / NAC | SSID, VLAN mapping, RADIUS, 802.1X, certificate và policy | Thiết bị không thể xác thực hoặc truy cập sai zone |
| Cloud network | Route table, security group/NSG, NACL, gateway, LB, policy/IaC | Mất kiến trúc bảo vệ và đường đi liên vùng |
| Kubernetes / service mesh | NetworkPolicy, ingress, Gateway API, CNI config, mesh auth policy | Giao tiếp giữa workload sai phạm vi |
| Hệ thống quản trị | Inventory, AAA, automation template, backup tool config, CA/PKI metadata | Không thể quản trị hoặc tái dựng nhất quán |

**Không nên lưu mọi secret vào một file cấu hình chung cho tiện khôi phục.** Hãy xác định secret nào có thể được tái cấp hoặc nạp lại từ kho bí mật riêng, loại nào bắt buộc bảo toàn để phục hồi dữ liệu hoặc danh tính, rồi áp dụng chính sách bảo vệ tương ứng.

## 3. Mô hình đe dọa đối với bản sao cấu hình

Một bản backup cấu hình có thể bị **đọc trộm, sửa, xóa, thay thế hoặc làm không thể phục hồi**. Những đường tấn công và sự cố thường gặp:

| Rủi ro | Tác động | Biện pháp chủ đạo |
| --- | --- | --- |
| Lộ tài khoản backup, token hoặc SSH key | Đọc cấu hình toàn hệ thống, có thể truy cập thiết bị | Least privilege, MFA cho quản trị, secret manager, rotation |
| Rò rỉ nội dung backup | Lộ sơ đồ mạng, ACL, private key hoặc credential | Mã hóa, kiểm soát truy cập, giảm thiểu secret |
| Xóa/sửa backup từ tài khoản quản trị bị chiếm | Mất điểm khôi phục hoặc đưa cấu hình độc hại vào | Immutable/offline copy, tách quyền ghi và xóa, audit |
| Backup chứa thay đổi sai hoặc bị cài cắm | Restore lặp lại sự cố/xâm nhập | Quản lý phiên bản, review diff, chọn mốc sạch |
| Chỉ lưu trên thiết bị nguồn | Mất cùng thiết bị khi lỗi phần cứng | Bản sao độc lập ngoài thiết bị |
| Backup quá cũ | Khôi phục làm mất thay đổi chính sách hợp lệ | Backup theo lịch và sau thay đổi quan trọng |
| Tệp export thiếu chứng chỉ hoặc license | Có file nhưng dịch vụ không thể khởi chạy | Dependency inventory và test restore |
| Không giải mã được khi cần | Khóa nằm cùng hệ thống bị mất hoặc bị thu hồi | KMS/escrow và diễn tập giải mã |
| Tài khoản backup truy cập quá rộng | Một lỗi làm lộ nhiều zone | Chia vùng repository và vai trò theo mức nhạy cảm |
| Log hoặc Git vô tình ghi secret | Lộ thông tin ngay cả khi backup mã hóa | Redaction, secret scanning, cấm commit file thô |

Các mục tiêu **confidentiality, integrity, availability** phải được xem xét riêng. Mã hóa bảo vệ tính bí mật khi khóa còn an toàn, nhưng không tự chống xóa. Hash có thể phát hiện thay đổi byte khi so sánh với giá trị tin cậy, nhưng không tự chống giả mạo nếu kẻ tấn công sửa được cả tệp lẫn hash.

## 4. Chính sách sao lưu: thời điểm, tần suất và mục tiêu khôi phục

### 4.1. Backup theo lịch và theo sự kiện

Kết hợp hai cơ chế:

- **Định kỳ:** ví dụ mỗi ngày cho thiết bị đổi cấu hình thường xuyên, mỗi tuần cho thiết bị ổn định; lựa chọn phụ thuộc mức rủi ro và nhu cầu phục hồi.
- **Theo thay đổi:** lưu bản **trước và sau** mỗi thay đổi quan trọng đã được cho phép; gắn change ticket và người thực hiện.
- **Theo vòng đời:** sau triển khai mới, nâng firmware, chuyển platform, đổi PKI/AAA, thay topology, failover hoặc trước diễn tập phục hồi.
- **Theo sự cố:** bảo toàn snapshot cấu hình và log hiện tại khi điều tra, nhưng không coi bản snapshot nghi bị xâm nhập là mốc khôi phục sạch.

Lấy bản active/saved config đúng với cách nhà cung cấp quản lý commit. Nếu một thay đổi chỉ áp dụng vào running config mà chưa được save, cần ghi rõ sự khác biệt. Có thể cần chụp cả hai trạng thái.

### 4.2. RPO và RTO của cấu hình

**RPO (Recovery Point Objective)** là lượng thay đổi cấu hình chấp nhận mất tính đến mốc khôi phục. **RTO (Recovery Time Objective)** là thời gian mục tiêu để dịch vụ trở lại hoạt động ở mức đã xác định.

Ví dụ: nếu firewall thay policy nhiều lần mỗi ngày và RPO yêu cầu không mất thay đổi đã được phê duyệt, backup theo lịch mỗi đêm là chưa đủ; cần export sau mỗi lần commit thành công. Nếu RTO cho VPN gateway là 30 phút nhưng việc tìm khóa giải mã và certificate mất nhiều giờ, kế hoạch chưa đáp ứng mục tiêu.

RPO/RTO phải được thỏa thuận theo **dịch vụ nghiệp vụ** và phụ thuộc của nó, thay vì lấy cùng một giá trị cho mọi switch, firewall và DNS server.

### 4.3. Retention và phiên bản

Một chính sách cần chỉ rõ thời gian giữ bản gần, bản hàng tuần/tháng, bản trước thay đổi lớn và bản liên quan điều tra sự cố. Phân biệt **retention vận hành** với **legal hold/điều tra** khi áp dụng. Các phiên bản phải có timestamp UTC, asset ID và loại trạng thái, tránh đặt tên mơ hồ như latest-config.txt rồi ghi đè liên tục.

Một tệp backup mới chưa tự chứng minh phiên bản cũ đã có thể xóa: cần giữ đủ điểm khôi phục để quay lại mốc trước một thay đổi sai được phát hiện muộn.

## 5. Kiến trúc lưu bản sao có sức chống chịu

Quy tắc tham khảo **3-2-1**: ba bản sao dữ liệu (bao gồm bản vận hành), lưu trên hai loại phương tiện hoặc miền lỗi độc lập, ít nhất một bản tại vị trí tách biệt. Biến thể **3-2-1-1-0** nhấn mạnh thêm một bản immutable/offline và mục tiêu không còn lỗi chưa xử lý trong các lần kiểm tra backup/restore. Các con số là khung thiết kế, **không tự bảo đảm** an toàn hoặc thành công khi phục hồi.

~~~mermaid
flowchart LR
    D[Thiết bị mạng / API cấu hình] -->|Kênh quản trị được xác thực| C[Collector ít quyền]
    C -->|Ghi bản tạm có kiểm soát| S[Kho staging hạn chế]
    S -->|Đã kiểm tra và mã hóa| R[Kho backup chính]
    R -->|Replication + kiểm tra| O[Kho offsite / miền tin cậy khác]
    R -->|Phiên bản giữ khóa, WORM hoặc offline| I[Bản immutable / offline]
    M[Kho khóa KMS / HSM] -. Quản lý khóa độc lập .-> R
    M -. Chính sách khôi phục khóa .-> O
    A[Audit và giám sát] -.-> C
    A -.-> R
    A -.-> O
~~~

Một bản sao ở thư mục khác nhưng nằm **cùng ổ đĩa, cùng account quyền xóa và cùng hệ thống bị xâm nhập** không tạo miền lỗi độc lập đáng kể. Với hệ thống bảo mật quan trọng, nên tách repository, account quản trị, khóa mã hóa hoặc ít nhất quyền quản lý/xóa giữa môi trường production và backup.

### 5.1. Immutable, offline và offsite khác nhau

| Cách lưu | Mục đích | Giới hạn |
| --- | --- | --- |
| Offsite | Chống sự cố tại site chính | Nếu cùng credential bị chiếm, bản sao vẫn có thể bị xóa |
| Immutable / WORM | Chống sửa/xóa trong thời hạn retention khóa | Phải kiểm tra cơ chế lock và quyền quản trị, không bảo vệ khỏi mọi lỗi cấu hình |
| Offline/air-gapped | Hạn chế đường truy cập trực tuyến của kẻ tấn công | Cần quy trình đưa dữ liệu vào/ra và kiểm thử phục hồi |
| Versioned repository | Quay lại mốc cấu hình trước đó | Versioning không thay thế chống xóa hàng loạt hoặc backup độc lập |

Kiểm tra cụ thể hành vi của nền tảng: retention lock có thể cấu hình sai, tài khoản quản trị cấp cao có thể có ngoại lệ, hoặc replication có thể sao chép cả hành động xóa. Cần diễn tập tình huống **credential backup bị chiếm** và **production bị mất hoàn toàn**.

## 6. Mã hóa, đường truyền và bảo vệ khóa

### 6.1. Truyền cấu hình qua kênh bảo mật

Ưu tiên **SSH/SFTP, SCP, API qua TLS đã xác thực và các cơ chế backup native bảo mật** của nhà cung cấp. Bật kiểm tra danh tính máy đích: SSH host keys hoặc TLS certificates đúng chuẩn, tránh bỏ xác minh host/certificate chỉ để script chạy nhanh.

**TFTP, FTP, Telnet và HTTP plaintext** có thể làm lộ nội dung hoặc credentials khi di chuyển qua mạng không đáng tin. Nếu một thiết bị cũ chỉ hỗ trợ cơ chế không mã hóa, cần phân đoạn management network riêng, hạn chế đường đi, có kế hoạch nâng cấp và tuyệt đối không mặc định dữ liệu được bảo vệ trên đường truyền.

Đường quản trị nên tách khỏi đường người dùng, giới hạn bằng ACL/security group, và cho phép kết nối từ collector đến **đúng địa chỉ/port**. Không mở inbound Internet vào giao diện quản trị để tiện sao lưu.

### 6.2. Mã hóa khi lưu và vòng đời khóa

Mã hóa backup khi lưu bằng cơ chế đã kiểm định của tổ chức, dùng khóa hoặc envelope encryption do KMS/HSM/secret management quản trị. Cần xác định:

- Ai có quyền **mã hóa**, **giải mã**, **đổi khóa**, **vô hiệu hóa**, **xóa bản sao**?
- Backup key có bị lưu cùng file và cùng quyền đọc không?
- Có thể khôi phục trong môi trường cô lập nếu KMS ở site chính không hoạt động không?
- Khi rotate/revoke khóa, những phiên bản cũ có còn giải mã được trong thời hạn retention không?
- Mọi lần giải mã và thay đổi key policy có audit và cảnh báo không?

**Không đưa mật khẩu hoặc private key vào shell argument, console output, ticket hoặc source repository.** Nếu cấu hình chứa PSK, password hash, API token hoặc certificate private key, hãy coi file gốc là dữ liệu nhạy cảm dù có một phần ký tự bị che.

### 6.3. Quản lý secrets phục vụ phục hồi

Nhiều thiết bị xuất **tham chiếu** đến secret, certificate hoặc đối tượng PKI, chứ không xuất được private key có thể tái nhập. Runbook phải mô tả nguồn phục hồi hợp lệ: secret manager, CA, backup PKI riêng, cơ chế cấp lại chứng chỉ, và những trường hợp phải **rotate credentials sau sự cố**.

Một hệ thống có thể phục hồi rule firewall nhưng không dựng được VPN nếu thiếu trust chain hoặc PSK; cần kiểm tra dependencies trước khi khẳng định backup hoàn chỉnh.

## 7. Kiểm soát quyền, tách vai trò và audit

Áp dụng **least privilege** theo các vai trò:

| Vai trò | Quyền tối thiểu | Hạn chế quan trọng |
| --- | --- | --- |
| Collector service | Đọc/export đúng cấu hình thiết bị; ghi vào staging | Không tự ý thay cấu hình, không xóa bản immutable |
| Backup operator | Giám sát job, xem metadata, xử lý thất bại | Không mặc định có quyền đọc plaintext/giải mã toàn bộ |
| Security reviewer | Xem diff đã xử lý hoặc báo cáo tuân thủ | Không cần tải bản có secret |
| Restore operator | Được phê duyệt để giải mã/khôi phục trong sự cố | Restore vào production theo change/incident process |
| Key administrator | Quản trị khóa hoặc chính sách KMS | Không đồng thời có toàn quyền xóa và đọc bản sao |
| Backup repository administrator | Cấu hình lưu trữ và retention | Hạn chế quyền thay đổi khóa hoặc nội dung plaintext |
| Auditor | Xem log truy cập, thay đổi và kết quả kiểm thử | Quyền chỉ đọc |

Phân quyền cụ thể phụ thuộc nền tảng, nhưng mục tiêu là không để **một tài khoản tự thu, sửa, xóa, giải mã mọi backup và xóa audit log**. Dùng MFA cho truy cập quản trị tương tác; service identities nên có cơ chế cấp chứng thực tự động, giới hạn phạm vi và rotation. Những khóa SSH/API token dùng cho job cần được quản trị, không chôn trong script hoặc file cấu hình công khai.

Theo dõi các sự kiện: backup thất bại, truy cập plaintext, giải mã bất thường, xóa phiên bản, thay đổi retention, thay đổi chính sách KMS, tắt audit và mất liên lạc với collector.

## 8. Toàn vẹn, nguồn gốc và khả năng kiểm chứng

Một bản sao dùng được phải có **nội dung đầy đủ**, **metadata nguồn**, **tính toàn vẹn** và **khả năng giải thích đây là cấu hình nào**. Kiểm tra nhiều lớp:

1. Export trả mã thành công, file không rỗng và có cấu trúc mong đợi của nền tảng.
2. Ghi asset ID, hostname, hardware/model, OS/firmware version, loại cấu hình, thời điểm UTC, collector/version, phương pháp và change ID.
3. Tính hash sau khi nhận file, chuyển hash và metadata tới kho có quyền ghi/sửa tách biệt.
4. Nếu cần chống giả mạo có chủ đích, dùng **chữ ký số/MAC hoặc manifest được ký** với khóa được bảo vệ và xác thực signer; hash lưu cùng tệp và cùng quyền ghi không đủ.
5. Sau replication, xác minh byte, metadata, khả năng mở/giải mã của bản sao và trạng thái retention.
6. Định kỳ làm **restore test**. Bản hash hợp lệ chưa chứng minh thiết bị có thể boot hoặc áp dụng cấu hình.

Ví dụ manifest mô tả backup của một firewall:

~~~yaml
backup_id: NET-EXAMPLE-20261128-001
asset_id: fw-edge-01
device_role: segmentation-firewall
configuration_type: active
captured_at_utc: "2026-11-28T05:00:00Z"
collected_by: network-backup-collector
collection_method: authenticated-management-api
platform: example-vendor
firmware_version: "example-10.2"
change_id: CHG-EXAMPLE-042
content_file: "fw-edge-01-20261128T050000Z.enc"
content_sha256: "<dien ma hash cua file thuc>"
encryption_key_reference: "kms/backup/network/example-key"
retention_class: network-critical
restore_test_reference: "TEST-EXAMPLE-019"
notes:
  - "Can khoi phuc certificate tu PKI rieng"
  - "Khong chua runtime session hoac NAT table"
~~~

Manifest chỉ là **minh họa**, không phải schema bắt buộc. Khi ghi hash, phải xác định hash áp dụng cho **plaintext**, **ciphertext** hay cả hai; khi đổi lớp mã hóa, hash ciphertext sẽ đổi dù nội dung cấu hình tương đương.

### 8.1. Dùng hash đúng mục đích

~~~bash
# Tính SHA-256 cho tệp đã thu trong thư mục giới hạn quyền:
sha256sum fw-edge-01-backup.enc

# Kiểm tra bằng danh sách hash đã được bảo quản đáng tin cậy:
sha256sum -c fw-edge-01-backup.enc.sha256
~~~

Kết quả khớp xác nhận byte file được so khớp với hash tham chiếu; nó không tự chứng minh file đã được thu đúng thiết bị, không chứa thay đổi độc hại hoặc có thể restore. **Hash và manifest cần được bảo vệ trước việc bị thay đổi đồng thời.**

## 9. Quy trình tự động hóa backup an toàn

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A[Inventory tài sản và phiên bản] --> B[Chọn kênh quản trị và identity ít quyền]
    B --> C[Đọc active/saved/candidate theo nền tảng]
    C --> D{Thu thành công và kiểm tra cấu trúc?}
    D -->|Không| E[Đánh dấu thất bại, báo động, giữ phiên bản trước]
    D -->|Có| F[Ghi metadata, hash và phiên bản]
    F --> G[Mã hóa và chuyển sang kho backup]
    G --> H[Replication ra miền độc lập, retention/immutable]
    H --> I[Kiểm tra integrity và điều kiện truy xuất]
    I --> J[Giám sát, so diff và diễn tập restore]
~~~

### 9.1. Ví dụ thu cấu hình qua SSH vào staging

Đoạn shell sau **chỉ minh họa bước export cục bộ** trên một máy collector Linux có thư mục staging được bảo vệ. Lệnh **show running-config** mang tính ví dụ cho một số hệ điều hành mạng; cú pháp, quyền read-only và khả năng chạy non-interactive phải được xác minh với đúng nhà cung cấp. Nhiều thiết bị cần API/export riêng.

~~~bash
#!/usr/bin/env bash
set -euo pipefail
umask 077

device=fw-edge-01.example.internal
backup_dir=./restricted-network-backup-staging
stamp=$(date -u +%Y%m%dT%H%M%SZ)

mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
tmp=$(mktemp "$backup_dir/.capture.XXXXXX")
trap 'rm -f "$tmp"' EXIT

# Cấu hình SSH key/host key phải được thiết lập an toàn từ trước.
# Tài khoản backup chỉ được đọc/xuất cấu hình được cho phép.
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=10 \
    "backup@$device" 'show running-config' > "$tmp"

# Kiểm tra cơ bản; triển khai thực tế cần parse/validate theo vendor.
test -s "$tmp"
final="$backup_dir/$device-$stamp.cfg"
test ! -e "$final"
mv "$tmp" "$final"
chmod 600 "$final"
sha256sum "$final" > "$final.sha256"
~~~

Ví dụ trên chưa mã hóa, chưa gửi ra kho immutable/offsite, chưa ký manifest và **không phải một backup pipeline production hoàn chỉnh**. Staging phải nằm trên hệ thống có phân quyền và mã hóa lưu trữ phù hợp, tránh lưu plaintext lâu hơn cần thiết. Tệp cấu hình có thể chứa secret; cần sớm chuyển qua cơ chế mã hóa đã phê duyệt, xác nhận bản sao đích, sau đó xử lý tệp staging theo chính sách. Không đưa plaintext vào Git, log pipeline hoặc ticket.

Không tự ý tắt StrictHostKeyChecking để xử lý lỗi xác thực; thay vào đó phải cập nhật trust inventory/host key qua quy trình quản trị. Nếu SSH export thất bại hoặc file rỗng, job **phải báo thất bại**, không ghi đè bản backup tốt gần nhất bằng dữ liệu không hợp lệ.

### 9.2. Tổ chức tên bản sao

Tên file nên chứa **asset ID + thời điểm UTC + loại config hoặc version**, nhưng không chứa password/token. Nếu nhiều collector chạy song song, sử dụng ID phiên thu thập duy nhất để tránh đụng tên và ghi đè.

Ví dụ:

~~~text
network-backups/
  asset=fw-edge-01/
    2026-11-28T05-00-00Z-active.enc
    2026-11-28T05-00-00Z-active.manifest.json
    2026-11-28T05-00-00Z-active.signature
  asset=core-sw-02/
    2026-11-28T05-05-00Z-saved.enc
    2026-11-28T05-05-00Z-saved.manifest.json
~~~

Đây là cách đặt tên minh họa; không suy ra việc có extension .enc nghĩa là file thực sự đã được mã hóa đúng chuẩn. Cần xác minh metadata mã hóa và khả năng giải mã.

## 10. Quản lý phiên bản, diff và configuration drift

**Backup** giữ trạng thái cấu hình tại một thời điểm. **Source of truth/IaC** lưu ý định cấu hình mong muốn. **Drift detection** so chúng để tìm thay đổi bất thường hoặc thay đổi chưa đi qua quy trình quản trị.

Một quy trình so sánh an toàn:

1. Lấy bản cấu hình mới và phiên bản trước, giữ nguyên bản gốc.
2. Chuẩn hóa các trường thay đổi tự động mà nhà cung cấp tạo ra **chỉ trong bản sao phục vụ diff**, không sửa backup nguyên trạng.
3. Ẩn/redact secret khi tạo báo cáo cho người không có quyền.
4. Liên hệ thay đổi với change ticket, deployment, audit config và người quản trị.
5. Kiểm tra sự khác biệt liên quan firewall allow/deny, NAT, VPN peers, AAA, DNS, route, syslog, IDS/IPS profile.
6. Khi có thay đổi không được phê duyệt, điều tra nguồn gốc và ảnh hưởng trước khi lựa chọn rollback.

Những thay đổi cần được cảnh báo ưu tiên: tắt logging/IDS/IPS, mở rộng rule quá mức, tạo tài khoản quản trị mới, thay trusted CA, đổi DNS/route/egress bất thường hoặc sửa backup destination.

**Không dùng text diff chưa xử lý như bằng chứng đầy đủ** nếu cấu hình có thứ tự rule quan trọng, object references, cấu trúc nhị phân hoặc chính sách sinh tự động; cần đối chiếu semantics bằng công cụ/vendor API.

## 11. Khôi phục: phụ thuộc và thứ tự thực hiện

Restore có thể tác động trực tiếp đến định tuyến, mạng quản trị, ACL, identity hoặc kết nối production. Trước khi áp dụng cần xác định **mục tiêu phục hồi**, **ảnh hưởng dự kiến**, **cửa sổ thay đổi** và **cơ chế quay lại khi thất bại**.

### 11.1. Không phải mọi cấu hình đều khôi phục được ngay

| Phụ thuộc | Điều phải xác minh |
| --- | --- |
| Model và phần cứng | Số cổng, module, tốc độ, interface name có phù hợp không? |
| OS/firmware | Phiên bản config syntax và các tính năng có tương thích không? |
| License/subscription | Tính năng VPN, IPS, WAF, HA có còn license cần thiết không? |
| PKI và secrets | Private key, certificate, trust chain, PSK và secret reference có nạp được không? |
| AAA và quản trị | Có quyền truy cập recovery nếu RADIUS/SSO chưa hoạt động không? |
| Routing/HA | VRF, BGP/OSPF neighbor, HA pair, cluster ID, node-specific settings |
| Firewall/WAF objects | Network objects, address groups, profiles, order của rule |
| External dependencies | DNS, NTP, syslog, KMS, upstream API và monitoring |
| Device-specific identity | Serial, MAC binding, hostname, cloud resource ID và IP management |

Không lấy một bản cấu hình của node A và nạp nguyên vào node B nếu chứa identity, port mapping, HA peer hoặc certificate ràng buộc phần cứng. Một số thành phần phải được tái cấp hoặc tạo theo mẫu của thiết bị đích.

### 11.2. Thứ tự khôi phục phụ thuộc topology

Không có thứ tự cố định cho mọi hệ thống. Có thể cần phục hồi **management access và identity/PKI**, rồi các lớp **underlay connectivity, route/VLAN/VRF**, sau đó **firewall policy, VPN, load balancing, DNS và dịch vụ ứng dụng**. Nếu hệ thống có out-of-band management, hãy dùng nó để tránh mất đường quản trị khi đổi route hoặc ACL.

Trước khi restore vào production, lưu cấu hình hiện tại và bằng chứng sự cố theo quyền hạn. Khi nghi bị xâm nhập, chọn mốc backup đã được kiểm chứng sạch và rà soát thay đổi để tránh phục hồi lại tài khoản/ACL độc hại; rotation credentials có thể cần thiết.

## 12. Kiểm thử restore và đo RPO/RTO thực tế

Một **backup thành công** về mặt kỹ thuật chưa phải **phục hồi thành công**. Cần diễn tập với thiết bị lab, VM hoặc môi trường staging có mạng cô lập, tương thích firmware và đủ phụ thuộc để kiểm tra cấu hình thực sự áp dụng.

| Bước | Cách kiểm chứng | Bằng chứng cần lưu |
| --- | --- | --- |
| Chọn bản | Phiên bản, asset, timestamp, change ID, hash/signature hợp lệ | Backup ID và manifest |
| Truy cập | Có thể truy xuất từ offsite/offline khi giả lập site chính mất | Log truy xuất, người thực hiện |
| Giải mã | KMS/escrow và quyền giải mã hoạt động | Kết quả không lộ khóa vào log |
| Import/parse | Cấu hình được hệ điều hành/firmware đích chấp nhận | Validation output đã lọc secret |
| Khôi phục phụ thuộc | PKI, license, AAA, interface, HA và object mapping đúng | Checklist dependency |
| Kiểm tra mạng | Route, ARP/ND, phân đoạn, DNS, VPN, health-check hoạt động | Output thử nghiệm và thời gian |
| Kiểm tra bảo mật | ACL deny/allow, IDS/IPS, WAF, syslog/audit, MFA đúng | Kịch bản positive và negative |
| Đo kết quả | Mốc khôi phục đáp RPO; thời gian dịch vụ đạt RTO | Timeline sự cố giả định |
| Đóng diễn tập | Những bước thủ công và lỗi được ghi vào runbook | Báo cáo, owner, hạn sửa |

Chẳng hạn, một firewall restore thành công nhưng vô tình mở rule **any-to-any** hoặc tắt audit logging **không đạt yêu cầu khôi phục an toàn**. Test phải bao gồm cả luồng hợp lệ được cho phép và luồng cần chặn.

### 12.1. Tần suất kiểm thử

Chọn lịch diễn tập theo mức quan trọng của thiết bị và sau các thay đổi đáng kể như firmware, PKI, storage, KMS, model phần cứng hoặc automation. Kiểm thử chỉ mở được file mỗi đêm không thay thế bài kiểm thử restore thực tế định kỳ.

## 13. Kịch bản sự cố: firewall bị sửa cấu hình và bản backup bị nhắm tới

Giả sử lúc 09:10 UTC, SIEM cảnh báo xuất hiện một rule firewall cho phép truy cập quản trị từ subnet không được phê duyệt. Cùng lúc job backup thất bại và có yêu cầu xóa nhiều phiên bản trong repository.

### 13.1. Bằng chứng cần ưu tiên

| Nguồn | Câu hỏi |
| --- | --- |
| Firewall config audit | Ai đã sửa rule, lúc nào, qua phiên quản trị nào? |
| AAA/identity logs | Có đăng nhập khác thường, MFA bất thường hoặc credential bị dùng sai? |
| Backup job logs | Export thất bại ở bước nào, có bản trước/sau thay đổi? |
| Repository audit | Ai yêu cầu xóa, thay retention hoặc đọc plaintext? |
| KMS logs | Có yêu cầu decrypt/rotate/disable key bất thường không? |
| Network telemetry | Có kết nối quản trị hoặc egress đáng nghi từ thiết bị/collector? |
| Signed manifest/offline copy | Còn bản sạch được kiểm tra toàn vẹn từ thời điểm nào? |

### 13.2. Phục hồi có kiểm soát

1. Kích hoạt quy trình ứng phó và bảo toàn audit, cấu hình hiện tại, phiên bản trước, key usage và dấu vết thay đổi.
2. Cô lập hoặc thu hồi credential bị nghi xâm nhập theo quyết định của nhóm chỉ huy sự cố; bảo vệ kho immutable/offline.
3. Xác định **phiên bản cuối đáng tin**, kiểm tra lịch sử thay đổi và tính phù hợp của firmware/PKI.
4. Trong môi trường staging, diff và kiểm thử rule, route, NAT, VPN cùng khả năng truy cập quản trị.
5. Áp dụng phương án phục hồi theo change/incident procedure; giám sát cả allowed và denied flows.
6. Rotate keys/tokens/certificates theo mức độ nghi lộ; không phục hồi mật khẩu đã bị đánh cắp rồi coi là an toàn.
7. Xác nhận log/audit/IDS/IPS hoạt động trở lại và kiểm tra replication/immutable retention.
8. Ghi timeline, tác động nghiệp vụ, root cause đã kiểm chứng và các hành động giảm tái diễn.

Nếu bản backup được tạo **sau** khi cấu hình bị cài cắm, restore bản mới nhất có thể đưa hành vi độc hại quay lại. Phải dựa vào mốc tin cậy và kiểm tra nội dung, không chọn chỉ vì file có timestamp gần nhất.

## 14. Giám sát chất lượng backup

Cần quan sát cả mức độ **hoàn thành** và mức độ **phục hồi thực tế**:

| Chỉ số / cảnh báo | Ý nghĩa |
| --- | --- |
| Tỷ lệ job thành công theo asset | Có đang bỏ sót một nhóm thiết bị hay không |
| **Age of last verified backup** | Bao lâu chưa có bản được kiểm tra hợp lệ |
| Asset coverage | Bao nhiêu tài sản quan trọng không có job hoặc không có phiên bản gần |
| Versioning và retention | Có giữ đủ mốc trước các thay đổi quan trọng |
| Export size/schema anomalies | File quá nhỏ, thay đổi đột ngột hoặc sai cấu trúc |
| Replication lag | Bản offsite/immutable có bị chậm |
| Restore test pass rate | Độ tin cậy thực tế của đường phục hồi |
| RPO/RTO đạt được | Khả năng đáp ứng mục tiêu phục hồi đã thống nhất |
| Privileged actions | Decrypt, xóa version, thay policy KMS/retention, tắt audit |
| Drift/change mismatch | Cấu hình thực tế không trùng approved change hoặc baseline |

Một file backup có hash khớp nhưng **không có khóa giải mã, thiếu certificate hoặc chưa từng kiểm thử restore** vẫn là rủi ro lớn. Chỉ số "job success" nên đi kèm **verified restore** và **coverage by criticality**.

Không dùng asset ID hoặc backup ID có cardinality rất cao làm metric label bừa bãi nếu hệ thống monitoring không phù hợp; có thể lưu chi tiết trong inventory/log và tổng hợp dashboard theo zone, nhóm thiết bị và trạng thái.

## 15. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Lưu mỗi bản trên chính router/firewall | Mất cùng thiết bị hoặc tài khoản bị chiếm | Kho riêng, replication/offsite |
| Coi export config là đầy đủ | Thiếu PKI, license, secret, firmware | Dependency inventory và restore test |
| Chỉ lấy startup config | Bỏ qua thay đổi chạy nhưng chưa lưu | Xác định cơ chế active/saved/candidate |
| Ghi đè bản cũ bằng latest | Mất mốc sạch trước thay đổi sai | Versioning, retention, immutable |
| Đưa plaintext vào Git hoặc ticket | Lộ secret và topology | Encryption, restricted repository, redacted diff |
| Đặt khóa giải mã cùng backup và chung quyền | Mã hóa mất tác dụng khi quyền bị chiếm | Tách quyền, KMS/escrow, MFA và audit |
| Chỉ tạo hash cạnh file | Attacker có thể thay cả file và hash | Signed/trusted manifest ở miền độc lập |
| Tin vào job exit code đơn lẻ | File rỗng, lỗi parse hoặc export thiếu dữ liệu | Content validation và test restore |
| Dùng FTP/TFTP trên mạng không tin cậy | Bị đọc hoặc chỉnh sửa nội dung | SSH/SFTP/TLS và management segmentation |
| Tắt host key/TLS certificate checking | Nguy cơ kết nối nhầm endpoint | Trust inventory, pin/verify identity |
| Không kiểm tra quyền xóa repository | Attacker xóa mọi bản sao | Tách quyền, immutable/offline copy |
| Khôi phục bản mới nhất sau xâm nhập | Đưa cấu hình độc hại quay lại | Chọn clean point, review change history |
| Không thử nghiệm trên nền tảng tương thích | Chỉ phát hiện thiếu dependency khi sự cố | Lab restore và firmware/PKI mapping |
| Không ghi owner hoặc UTC metadata | Không biết file thuộc thiết bị và mốc nào | Asset inventory, manifest và audit |
| Không đo RPO/RTO | Có backup nhưng khôi phục không kịp | Diễn tập theo mục tiêu nghiệp vụ |

## 16. Bài tập thiết kế: backup cho ba lớp mạng

**Bối cảnh:** hệ thống gồm router biên, firewall phân đoạn và VPN gateway. Các thay đổi firewall diễn ra hàng ngày; routing thay đổi theo đợt triển khai; VPN dùng chứng chỉ của PKI nội bộ. Doanh nghiệp muốn có điểm khôi phục trước/sau mọi thay đổi được phê duyệt, phục hồi cả khi site chính mất và giới hạn nguy cơ lộ cấu hình.

Hãy điền bảng kế hoạch:

| Tài sản | Khi nào lưu | Dữ liệu và dependency | Kho dự phòng | Kiểm chứng |
| --- | --- | --- | --- | --- |
| Router biên | Định kỳ + trước/sau thay đổi route | Active/saved config, VRF, route policy, OS version | Offsite/immutable | Lab routing test, reachability, rollback |
| Firewall phân đoạn | Định kỳ + sau mỗi policy commit | Rules, NAT, zones, objects, profiles, license | Offsite/immutable | Allow/deny matrix, logging, diff |
| VPN gateway | Định kỳ + khi đổi peer/cert/crypto policy | Tunnel, route, certificate refs, PKI recovery plan | Offsite + secret vault riêng | Peer/auth test, tunnel recovery |

**Kết quả mong đợi:** có danh mục asset, lịch và trigger, vai trò thu/giải mã/restore, cách quản trị secret, versioning, retention, replication, kiểm tra integrity và bài thử restore. Nếu PKI chỉ tồn tại ở site chính, phải bổ sung phương án khôi phục PKI hoặc cấp lại chứng chỉ; sao lưu file VPN config một mình chưa đủ.

## 17. Checklist áp dụng trong vận hành

- [ ] Đã xác định các thiết bị, dịch vụ mạng và owner cần backup.
- [ ] Đã phân biệt active/running, saved/startup, committed và IaC desired state.
- [ ] Đã biết thành phần nào export được, thành phần nào phải phục hồi từ PKI/secret manager/license.
- [ ] Đã thiết lập RPO/RTO theo mức độ quan trọng của dịch vụ.
- [ ] Có backup định kỳ, trước/sau thay đổi và sau commit quan trọng.
- [ ] Có phiên bản, timestamp UTC, asset ID, firmware và change reference.
- [ ] Đường truyền được xác thực và mã hóa; không dùng kênh plaintext trên mạng không tin cậy.
- [ ] Bản sao lưu được mã hóa, khóa và quyền giải mã quản lý độc lập, có phương án khôi phục khóa.
- [ ] Có ít nhất một bản trong miền lỗi độc lập, kèm immutable/offline theo mức rủi ro.
- [ ] Quyền đọc, ghi, xóa, restore, decrypt và audit được phân tách.
- [ ] Export được kiểm tra nội dung, hash/manifest và độ đầy đủ; replication được xác minh.
- [ ] Diff được review khi có thay đổi cấu hình ngoài dự kiến; không lộ secret trong báo cáo.
- [ ] Đã kiểm thử restore trong môi trường tương thích, kiểm tra cả kết nối hợp lệ và các luồng bị chặn.
- [ ] Có cảnh báo backup quá hạn, job lỗi, mất replication, thay retention/KMS hoặc yêu cầu decrypt bất thường.
- [ ] Có runbook phục hồi khi production, site chính hoặc backup account bị xâm nhập.

**Một bản sao cấu hình chỉ có giá trị phòng vệ khi có thể truy xuất, kiểm tra và khôi phục an toàn đúng lúc.** Thiết kế backup cho thiết bị mạng phải cân bằng giữa tính đầy đủ của cấu hình, bảo vệ các secrets, tách quyền, khả năng chống xóa/sửa và diễn tập restore trên nền tảng thực. Khi thực hiện đồng bộ những bước này, tổ chức có thể khôi phục nhanh lớp firewall, VPN, DNS, routing và các dịch vụ mạng mà không biến kho backup thành điểm yếu bảo mật mới.
