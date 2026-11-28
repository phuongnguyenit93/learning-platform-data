# Bảo toàn log và chain of custody trong điều tra số trên mạng

## 1. Mục tiêu và bối cảnh

Trong một sự cố an ninh mạng, dấu vết có thể xuất hiện đồng thời ở firewall, VPN, DNS, IDS/IPS, load balancer, thiết bị mạng, máy chủ, cloud audit, SIEM và file PCAP. Chúng giúp xác định máy nào liên lạc với đích đáng ngờ, chính sách nào cho phép hoặc chặn kết nối, thời điểm phát hiện và diễn biến của cuộc tấn công. Nhưng nếu log bị ghi đè, dữ liệu được xuất thiếu, timestamp bị diễn giải sai hoặc nhiều người cùng sửa file, kết luận điều tra có thể không kiểm chứng được.

**Bảo toàn log (log preservation)** là tập hợp phương pháp nhận diện, thu thập, kiểm tra, lưu giữ và bảo vệ bản ghi cùng ngữ cảnh cần thiết, sao cho dữ liệu vẫn có thể được kiểm chứng trong suốt vòng đời vụ việc.

**Chain of custody (chuỗi quản lý, bàn giao chứng cứ)** là hồ sơ theo dõi người hoặc hệ thống nắm quyền quản lý chứng cứ: ai thu, ai nhận, vào lúc nào, ở đâu, để làm gì, bằng cách nào, có tác động gì và kết quả kiểm tra tính toàn vẹn ra sao.

Đây là kiến thức nền tảng của chương **Điều tra số trên mạng** thuộc module **SECURITY_NETWORK_SECURITY**. Nó bổ trợ cho phân đoạn mạng, firewall, VPN, IDS/IPS, giám sát xâm nhập, bảo vệ DNS, mạng không dây và cloud security; một capture hay cảnh báo chỉ thực sự có ích khi hiểu nguồn quan sát và giới hạn của nó.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu nguồn, bản thu thập gốc, bản làm việc và dữ liệu dẫn xuất.
- Xác định log dễ mất và thu thập theo độ khẩn cấp, phạm vi cho phép.
- Ghi hash, metadata, manifest và các bản ghi bàn giao có khả năng kiểm toán.
- Phân tích vấn đề timestamp, thiếu log, sampling, NAT, đa vùng và pipeline SIEM.
- Tổ chức kho chứng cứ với quyền truy cập, mã hóa, retention và legal hold phù hợp.
- Giải thích kết luận dựa trên bằng chứng, nêu rõ mức tin cậy và phần chưa xác minh.

> **Nguyên tắc:** Thu đúng phạm vi; giữ bản gốc và metadata; dùng bản làm việc để phân tích; ghi mọi thay đổi/bàn giao quan trọng; đưa ra kết luận có thể kiểm chứng độc lập.

## 2. Bảy thuộc tính quan trọng của chứng cứ số

| Thuộc tính | Câu hỏi | Cách kiểm tra hỗ trợ |
|---|---|---|
| **Nguồn gốc (provenance)** | Log phát sinh ở thiết bị, hệ thống, tài khoản, sensor nào? | Asset ID, collector ID, export job, cấu hình và nhật ký nguồn |
| **Toàn vẹn (integrity)** | Byte của bản đang lưu có bị thay đổi không? | Hash, object version, write protection, định kỳ kiểm tra |
| **Xác thực (authenticity)** | Có căn cứ tin dữ liệu thực sự đến từ nguồn đã khai báo không? | Xác thực nguồn, bảo vệ đường truyền, chữ ký khi có, đối chiếu độc lập |
| **Đầy đủ (completeness)** | Có mất record, mất packet hoặc thiếu một khoảng thời gian? | Log rotation, cursor/offset, sequence, packet drop, ingest counters |
| **Liên quan (relevance)** | Bản ghi có hỗ trợ giả thuyết điều tra cụ thể? | Incident scope, time range, device mapping, correlation ID |
| **Truy vết (accountability)** | Ai truy cập, tạo bản sao hoặc chuyển dữ liệu? | Chain of custody, audit trail, phê duyệt |
| **Tái lập (reproducibility)** | Người khác có thể chạy lại thao tác phân tích? | Raw data, tool/version, query/filter, đầu vào/đầu ra, hash |

Cần tránh đồng nhất các thuộc tính:

1. **Hash khớp không chứng minh log đúng sự thật.** Hash SHA-256 chứng minh byte chưa thay đổi so với giá trị hash tin cậy, nhưng attacker có thể tạo một log giả và tính hash chính xác cho nó.
2. **Mã hóa không đồng nghĩa bất biến.** Mã hóa bảo vệ tính bí mật; người được cấp quyền có thể giải mã và tạo phiên bản mới nếu quyền không được hạn chế.
3. **Lưu bất biến không sửa được dữ liệu sai đã ghi.** WORM hoặc object lock chỉ hạn chế thay đổi sau khi ghi; pipeline vẫn có thể thu thiếu hoặc parse sai.
4. **Chain of custody không thay thế phân tích kỹ thuật.** Có hồ sơ bàn giao đầy đủ không đảm bảo mọi sensor đều quan sát đúng đường đi của gói tin.
5. **Không thấy sự kiện không có nghĩa là sự kiện không xảy ra.** Log có thể bị cắt, bị lấy mẫu, collector lỗi, lệch đồng hồ hoặc không bật trước thời điểm cần điều tra.

## 3. Phân biệt bản nguồn, bản thu và bản làm việc

Một hệ thống đang chạy liên tục tạo log mới. Không thể luôn “đóng băng” nguồn; điều tra cần mô tả chính xác loại vật chứng:

- **Nguồn đang hoạt động:** firewall/session table, DNS resolver, syslog, event log, buffer packet capture hoặc một cơ sở dữ liệu log đang thay đổi.
- **Bản thu thập (acquisition artifact):** file đầu tiên export/snapshot từ nguồn với phạm vi và phương pháp đã ghi rõ. Đây có thể là bản xuất đầu tiên, chứ không phải bản gốc bất biến đã tồn tại trong hệ thống.
- **Bản bảo quản (preserved copy):** bản đã kiểm tra tính toàn vẹn, phân loại và lưu vào kho có quyền hạn chế, có manifest và custodian.
- **Bản làm việc (working copy):** bản sao để lọc, tìm kiếm, decode, dựng timeline; mỗi phép biến đổi cần ghi rõ.
- **Bản dẫn xuất (derived artifact):** CSV, báo cáo, đồ thị, tập PCAP đã lọc, dữ liệu chuẩn hóa hoặc bản redact. Có hash và ID riêng, liên kết nguồn.
- **Báo cáo kết luận:** nêu bằng chứng hỗ trợ, thời điểm, độ tin cậy và giới hạn; không tự động trở thành bằng chứng gốc.

Không sửa, sắp xếp hoặc xóa trường ngay trên bản bảo quản. Công cụ mở file có thể tạo metadata hoặc cache, còn việc copy bằng lệnh thông thường không bảo toàn mọi ACL, extended attributes, journal hoặc metadata của filesystem. Nếu cần forensic disk image hay bộ nhớ, dùng quy trình/công cụ chuyên dụng đúng phạm vi.

## 4. Vòng đời quản lý và luồng bàn giao

~~~mermaid
flowchart TD
    A["Incident và quyền thu thập"] --> B["Xác định nguồn, ưu tiên dữ liệu dễ mất"]
    B --> C["Acquisition có ghi phương pháp, UTC và phạm vi"]
    C --> D["Chốt snapshot/export, hash và manifest"]
    D --> E["Kho mã hóa, phân quyền, audit và retention"]
    E --> F["Tạo bản làm việc; phân tích và lưu query"]
    F --> G["Kết quả có tham chiếu evidence ID"]
    G --> H{"Cần giữ hoặc chuyển giao?"}
    H -->|"Bàn giao"| I["Người nhận xác thực và đối chiếu hash"]
    I --> E
    H -->|"Legal hold hợp lệ"| J["Khóa xóa đúng phạm vi, định kỳ rà soát"]
    J --> E
    H -->|"Hết hạn được phép"| K["Xóa bản sao/phiên bản và lưu biên bản"]
~~~

Mỗi đối tượng cần `incident_id` (vụ việc) và `evidence_id` (vật chứng). Tránh thư mục chứa nhiều PCAP tên `final2.pcap` hoặc log không rõ nguồn và thời hạn.

### 4.1. Kế hoạch trước khi thu

Ghi rõ các quyết định:

1. **Mục đích:** phát hiện truy cập trái phép, truy vết DNS tunneling, đối chiếu bất thường VPN hay điều tra kết nối?
2. **Phạm vi:** hệ thống, segment, IP, user/session, thời gian, cổng/giao thức, tài khoản cloud và tenant được phép.
3. **Thẩm quyền:** ai phê duyệt, ai thực hiện, ai là evidence custodian, có yêu cầu phối hợp pháp chế/bảo vệ dữ liệu hay không?
4. **Mức độ dễ mất:** buffer có bị overwrite, container có bị thay thế, thiết bị có log rotation, index SIEM có hết hạn?
5. **Tác động thao tác:** export API có giới hạn, snapshot có làm tải tăng, có cần dừng/restart dịch vụ hay không?
6. **Bảo vệ:** nơi lưu đã mã hóa, IAM, MFA, audit, retention, pháp lý và yêu cầu xử lý secret.

Khi phải xử lý nguy cơ tức thời, an toàn và containment có thể được ưu tiên hơn bảo toàn tuyệt đối hiện trường. Ghi lại hành động đã làm và tác động đã biết; không cố trì hoãn ứng cứu chỉ để có bộ log hoàn hảo.

## 5. Bản đồ các nguồn log cần bảo toàn

| Nguồn | Thông tin hữu ích | Giới hạn và rủi ro mất |
|---|---|---|
| Firewall/NGFW/IDS/IPS | Rule ID/version, allow/deny, signature, NAT, session | Rotation, policy change, sampling, session timeout |
| Router, switch, SD-WAN | Interface errors/drop, flow records, routing/BGP event | Reset counters, export delay, packet/flow sampling |
| DNS | Query/response, rcode, client, resolver, TTL | Cache, DoH/DoT, retention ngắn, domain nhạy cảm |
| VPN/ZTNA/IAM | Login, session ID, assigned IP, user/device, tunnel | IP lease tái dùng, NAT, xác thực và tunnel events khác thời điểm |
| Proxy, WAF, LB, CDN | Request ID, status, upstream latency, security decision | Proxy chấm dứt TCP/TLS, log chưa bật đủ, khác múi giờ |
| SIEM/NDR/EDR | Alert, nguồn event, normalized fields, analyst action | Parser đổi cấu trúc, index thiếu, ingest delay |
| PCAP/PCAPNG | Packet bytes, timestamp, capture point, snaplen | Packet drop, SPAN oversubscription, capture một chiều, offload |
| Host Linux/Windows | Auth log, system log, Event Log, process/network events | Buffer, rotation, log cleared, host compromised |
| Cloud/Kubernetes | Control-plane audit, flow logs, pod/container lifecycle | Ephemeral resources, region, API pagination, log bật theo cấu hình |
| Application/database | Request ID, trace, exception, connection pool, query | Sampling, PII trong payload, log không đồng bộ |

**Các nguồn thường khác nhau về mức độ tin cậy.** Firewall ghi `allow` chỉ phản ánh quyết định tại điểm firewall, không chứng minh application đã nhận request. IDS cảnh báo là dấu hiệu cần triage, chưa tự chứng minh compromise. PCAP là tập các gói sensor đã ghi nhận, chưa chắc là mọi gói trên đường.

Với NAT, proxy và VPN, cần giữ mapping theo thời gian: IP nội bộ, IP/port đã dịch, session ID, 5-tuple, thiết bị, source zone và sensor location. Không dùng một địa chỉ IP đơn lẻ để gán danh tính một người nếu địa chỉ có thể tái cấp phát.

## 6. Dữ liệu dễ mất và thứ tự thu thập

| Loại dữ liệu | Vì sao dễ mất | Gợi ý bảo toàn |
|---|---|---|
| Session table/NAT mapping | Timeout, eviction, restart | Snapshot và ghi mốc UTC, thiết bị, lệnh/API |
| PCAP ring buffer | File cũ bị ghi đè | Chốt hoặc xuất đúng cửa sổ cần thiết, lưu capture stats |
| Syslog/Windows Event Log | Size limit, log rotation, clearing | Export tập file/bản ghi liên quan, bảo toàn metadata |
| RAM/process/cache | Reboot, process exit | Phương pháp live forensics có thẩm quyền, ghi tác động |
| Pod/container logs | Auto scaling, pod replacement | Lưu UID/container ID và export kịp thời |
| SIEM/flow indexes | Retention, pagination, quota | Export có kiểm tra đủ page/offset và timestamp |
| DNS caches/TTL | Entry tự hết hạn | Ghi hiện trạng kèm nguồn, thời điểm và hạn chế |

Không có thứ tự cứng đúng cho mọi tình huống. Ưu tiên theo **giá trị điều tra × tính dễ mất × độ rủi ro thao tác**, phối hợp với incident commander. Lệnh đọc hoặc snapshot trên hệ thống live có thể tạo audit event hoặc làm đổi trạng thái; cần ghi nhận điều đó.

### 6.1. Mẫu kế hoạch thu thập

~~~yaml
incident_id: INC-2026-031
purpose: "Kiểm tra lưu lượng DNS bất thường qua VPN"
scope:
  start_utc: "2026-11-28T02:00:00Z"
  end_utc: "2026-11-28T04:00:00Z"
  sources: ["resolver-a", "vpn-gateway-a", "ngfw-a"]
approver_role: incident-commander
collector_role: security-forensics
classification: restricted
priority:
  - "DNS raw log trước khi rotation"
  - "NAT/session mapping trước timeout"
  - "SIEM raw export để đối chiếu"
storage: encrypted-evidence-vault
retention_review_utc: "2026-12-05T00:00:00Z"
legal_hold: false
~~~

Đây là **metadata minh họa**, không phải cấu hình đang áp dụng. Phạm vi, thời hạn và quyền cần theo chính sách tổ chức. Khi cần mở rộng từ log sang full-packet capture hoặc decrypt TLS, phải xét riêng thẩm quyền và dữ liệu nhạy cảm.

## 7. Thu thập và niêm phong log

### 7.1. Ghi ngữ cảnh acquisition

Trước hoặc trong khi export, ghi:

- Nguồn: hostname, asset ID, tenant/account/region, interface, loại log và nơi quan sát trong topology.
- Thiết lập: phiên bản phần mềm, logging config, timezone, đồng bộ NTP, filter, sampling, rotation/retention.
- Acquisition: người thực hiện, thời gian bắt đầu/kết thúc UTC, công cụ/phiên bản, API/lệnh, quyền truy cập, mục đích.
- Output: file/export job ID, time range, số record, số trang/chunk, byte count, query/filters, cảnh báo/lỗi.
- Giới hạn: dropped packets, missing files, log gaps, collector down, clock offset, data redaction hoặc parser transformation.

Nếu nguồn đang ghi liên tục, **không hash một file đang thay đổi rồi coi đó là snapshot cố định**. Sử dụng export/snapshot nhất quán theo khả năng công cụ; khi nguồn không thể đóng băng, ghi rõ phương pháp lấy và tính đầy đủ chưa thể xác nhận.

### 7.2. Ví dụ bảo quản bản export trên Linux

Giả sử đã được phép export một log DNS ổn định, với môi trường GNU/Linux và kho mã hóa đã triển khai:

~~~bash
# Chỉ dùng trong môi trường điều tra có thẩm quyền.
umask 077
mkdir -p -- /secure-evidence/INC-2026-031/raw

# Copy từ file export đã chốt, không phải log đang ghi.
cp -- /staging-export/dns-20261128.jsonl \
   /secure-evidence/INC-2026-031/raw/dns-20261128.jsonl

# Kiểm tra số byte, mốc giờ file và SHA-256.
stat -c '%n | bytes=%s | mtime=%y' \
  /secure-evidence/INC-2026-031/raw/dns-20261128.jsonl
sha256sum -- /secure-evidence/INC-2026-031/raw/dns-20261128.jsonl
date -u '+%Y-%m-%dT%H:%M:%SZ'
~~~

Cách copy đơn giản này **không phải forensic imaging** và không bảo toàn mọi ACL, ownership, extended attribute, alternate data stream hoặc filesystem metadata. Khi những thuộc tính đó cần thiết, dùng giải pháp acquisition phù hợp và so sánh metadata. Nguồn `staging-export` cũng phải được bảo vệ, kiểm soát thời hạn xóa và tránh để plaintext trên ổ không mã hóa.

### 7.3. Thu log qua stream/API

Với syslog, Kafka, cloud streaming, SIEM hoặc audit API:

- Ghi stream/topic, partition, offset/cursor, query, page size, limit và job ID.
- Ghi các batch thất bại, retry, timestamp của nguồn và collector, số record dự kiến/nhận được nếu có.
- Lưu original message bytes khi có thể. Nếu normalized/enriched, giữ bản đó riêng và ghi phép biến đổi.
- Chốt từng chunk, tính hash sau khi đóng, lưu index/sequence để phát hiện thiếu hoặc trùng.
- Kiểm tra semantics: at-least-once có thể có duplicate, best-effort có thể mất, ingest lag có thể làm event đến sau khi export.
- Không khẳng định “đã thu toàn bộ” nếu không có cơ chế xác nhận completeness.

## 8. Chuẩn hóa timestamp mà vẫn giữ nguyên bản

Trong điều tra mạng cần phân biệt:

| Trường | Ý nghĩa |
|---|---|
| `event_time` | Thời điểm thiết bị/app ghi sự kiện, tùy đồng hồ nguồn |
| `receive_time` | Thời điểm collector nhận message |
| `ingest_time` | Thời điểm dữ liệu được index, có thể chậm hơn nhiều |
| `collection_time` | Thời điểm analyst export snapshot/file |
| `normalized_utc` | Bản chuẩn hóa ở dữ liệu làm việc, có ghi cách chuyển |
| `clock_uncertainty` | Sai số đồng hồ ước lượng hoặc chưa biết |

Ví dụ:

~~~text
original_event_time   = "2026-11-28 09:31:15 +0700"
normalized_event_time = "2026-11-28T02:31:15Z"
receive_time          = "2026-11-28T02:31:18Z"
collection_time       = "2026-11-28T05:10:00Z"
source                = "vpn-gateway-a"
clock_uncertainty     = "+/- 2 seconds"
~~~

Không ghi đè timestamp gốc. Thu thông tin về timezone, NTP/PTP status, độ phân giải (giây/ms/µs/ns), thay đổi múi giờ, daylight saving và cấu hình hệ thống. Syslog truyền thống có thể thiếu năm, timezone; suy luận dựa trên ngữ cảnh phải được ghi rõ.

Khi hai nguồn sai khác 3 giây nhưng độ bất định đồng hồ mỗi nguồn là ±5 giây, không thể khẳng định sự kiện A chắc chắn trước B chỉ bằng thứ tự timestamp. Dùng thêm sequence, packet capture, request ID, collector time và nguồn độc lập.

## 9. Hash, manifest và kiểm tra tính toàn vẹn

### 9.1. SHA-256 trả lời câu hỏi gì?

SHA-256 tạo digest đại diện cho byte đầu vào. Khi hash hai bản trùng nhau và giá trị chuẩn ban đầu được bảo vệ, ta có cơ sở rất mạnh cho thấy byte không đổi. Nếu hash khác nhau, không tự kết luận có kẻ tấn công: có thể copy thiếu, file đổi trong lúc đọc, chuyển đổi encoding/line ending hoặc lấy sai object version. Cần bảo toàn cả hai bản và điều tra sai khác.

Quy trình:

1. Chốt bản export hoặc snapshot ở trạng thái ổn định.
2. Ghi kích thước, digest SHA-256, thời điểm, người, công cụ và evidence ID.
3. Lưu digest vào manifest **có quyền và audit độc lập** với quyền sửa dữ liệu.
4. Sau khi truyền, copy, bàn giao hoặc restore, người nhận tính lại và so sánh.
5. Ghi kết quả xác minh, ngày, người thực hiện, công cụ và xử lý nếu không khớp.

~~~bash
cd /secure-evidence/INC-2026-031/raw

# Sau khi đã chốt acquisition artifact.
sha256sum -- dns-20261128.jsonl > ../checksums.sha256

# Người nhận kiểm tra lại từ manifest tin cậy.
sha256sum -c -- ../checksums.sha256
~~~

Manifest lưu cạnh dữ liệu **không tự động đáng tin** nếu cùng một tài khoản có thể sửa cả file lẫn hash. Cần phân tách quyền, lưu bất biến, audit và khi phù hợp ký số manifest với khóa do tổ chức quản lý. Chữ ký số chứng minh byte được ký bởi khóa phù hợp, vẫn không tự chứng minh sự kiện trong log là đúng.

### 9.2. Manifest mẫu

~~~yaml
incident_id: INC-2026-031
evidence_set_id: ES-031-01
classification: restricted
collected_at_utc: "2026-11-28T05:10:00Z"
source: "resolver-a"
acquisition_method: "approved-export-api"
export_job_id: "export-193"
query: "resolver-a, 02:00Z..04:00Z"
record_count: 18420
completeness: "partial; chưa xác minh toàn bộ nguồn"
files:
  - evidence_id: EV-031-001
    name: dns-20261128.jsonl
    size_bytes: 15426812
    sha256: "<digest thực tế sau khi thu>"
    derived: false
  - evidence_id: EV-031-001-D01
    name: dns-summary.csv
    sha256: "<digest thực tế của output>"
    derived_from: EV-031-001
retention_policy_ref: "organization-evidence-policy"
legal_hold: false
custodian_role: security-forensics
~~~

Mọi giá trị là ví dụ; `sha256` phải được điền bằng giá trị đo được, không tự tạo. Đảm bảo bản manifest được bảo vệ và có revision history nếu cập nhật.

## 10. Chain of custody: ai giữ, ai giao, ai nhận?

Một hồ sơ chain of custody nên ghi tối thiểu:

| Trường | Nội dung |
|---|---|
| Incident/evidence ID | Định danh duy nhất, tên file/nhóm đối tượng |
| Nguồn và phạm vi | Device/tenant/sensor, time range, query, định dạng |
| Người thu | ID người thực hiện, ngày giờ UTC, phương thức thu |
| Fingerprint | Size, SHA-256 và metadata kỹ thuật |
| Nơi lưu | Bucket/volume và object version/đường dẫn đủ để truy vết |
| Quyền | Classification, custodian, nhóm/role được truy cập |
| Chuyển giao | Người gửi, người nhận, thời điểm, lý do, xác nhận |
| Kiểm tra | Hash tại điểm nhận, trạng thái, ngoại lệ và cách giải quyết |
| Bản dẫn xuất | Ai tạo, từ file nào, filter/tool/version, hash output |
| Vòng đời | Retention review, legal hold, gia hạn, xóa có biên bản |

### 10.1. Ví dụ nhật ký bàn giao

~~~text
Incident: INC-2026-031
Evidence: EV-031-001 (DNS export)
Source: resolver-a, range 02:00Z - 04:00Z
Hash: <SHA-256 đã được xác minh>
Classification: RESTRICTED

05:10Z  ACQUIRED
Actor: analyst-17
Method: resolver export API, job export-193
Action: export đã chốt, ghi size/hash, tạo manifest
Storage: encrypted-staging/INC-2026-031
Result: success; giới hạn completeness đã ghi

05:20Z  HANDOFF
From: analyst-17
To: evidence-custodian-2
Reason: chuyển vào kho chứng cứ theo case
Action: người nhận tự tính SHA-256, so với manifest
Result: MATCH, nhận quyền custodian
Storage: evidence-vault/INC-2026-031/EV-031-001

06:00Z  WORKING_COPY
Actor: investigator-3
Input: EV-031-001, đã xác minh hash
Output: EV-031-001-W01
Purpose: đối chiếu DNS query với VPN session
Permission: time-bound theo incident
Result: success, bản gốc không thay đổi
~~~

Ghi cả truy cập đọc, tải, giải mã, tạo bản sao, thay quyền, xuất báo cáo, chuyển vùng lưu, restore từ backup và hành vi break-glass. Khi có hai người bàn giao, người nhận nên xác nhận định danh đối tượng, số byte, hash và nơi lưu mới.

**Nhật ký hệ thống không luôn thay thế biên bản chain of custody:** một audit event “object downloaded” có thể không biết mục đích, bản copy đi đâu, ai chính thức nhận trách nhiệm quản lý. Kết hợp audit tự động với biểu mẫu/case workflow.

### 10.2. Nếu hash không khớp sau bàn giao

1. Không ghi “verified” hoặc thay giá trị hash chuẩn để hợp thức hóa.
2. Cách ly bản có sai khác và giữ lại bản gốc/manifest tin cậy.
3. So sánh file size, hash, object version, đường truyền, định dạng, encoding và trạng thái lúc tính hash.
4. Kiểm tra audit access, thao tác tools, sự cố storage và người đã thực hiện.
5. Ghi sự kiện vào chain record; xác định bản nào được chấp nhận dùng tiếp theo quy trình.
6. Nếu có bằng chứng bị xâm phạm, chuyển nhóm ứng cứu thích hợp và bảo toàn thêm logs liên quan.

Không xóa dữ liệu sai khác trước khi kết thúc đánh giá vì chính sai khác có thể là chứng cứ của sự cố.

## 11. Kho lưu trữ và kiểm soát truy cập

Thiết kế kho chứng cứ theo lớp:

- **At rest:** mã hóa volume/object, quản lý khóa riêng phù hợp KMS/HSM và quyền giải mã giới hạn.
- **In transit:** truyền bằng giao thức bảo mật có xác thực hai đầu khi áp dụng; không chuyển raw PCAP qua link công khai.
- **IAM/RBAC:** quyền theo case, nguyên tắc ít quyền nhất, MFA, cấp quyền có hạn và phê duyệt khi xuất dữ liệu.
- **Role separation:** analyst phân tích working copy; custodian quản lý bản gốc và vòng đời; auditor kiểm tra lịch sử không nhất thiết được đọc payload.
- **Tamper resistance:** immutable storage hoặc versioning đúng phạm vi, retention lock, audit log ở trust boundary khác nếu có thể.
- **Monitoring:** cảnh báo download bất thường, thay retention, xóa, thay quyền, truy cập từ vùng lạ hoặc export hàng loạt.
- **Periodic checks:** kiểm tra hash, object count, orphan files, trạng thái replica, tính đúng của lịch hết hạn.
- **Disaster recovery:** backup phải bảo vệ tương đương, và retention/hold được duy trì khi restore.

Mã hóa ổ đĩa không ngăn người được cấp quyền đọc plaintext. WORM không ngăn dữ liệu giả được đưa vào từ đầu. Cần kiểm soát cả nguồn, collector, kho và danh tính người truy cập.

## 12. Phân tích từ bản làm việc và tái lập kết quả

Một báo cáo điều tra tốt cho biết **điều gì đã được làm với dữ liệu nào**. Mẫu provenance của phép phân tích:

~~~text
Input: EV-031-001, sha256=<hash đã xác minh>
Working copy: EV-031-001-W01
Tool: parser-name/version
Scope: 2026-11-28T02:00:00Z..04:00:00Z
Method:
  - đọc JSONL, giữ raw timestamp
  - tạo normalized UTC trong bản làm việc
  - join với VPN lease theo session ID và khoảng thời gian hợp lệ
  - nhóm DNS query theo source device và domain
Output: EV-031-001-D01 / summary.csv
Output SHA-256: <digest thực tế>
Limits: DNS cache/DoH không hiển thị; clock skew chưa đo đủ
~~~

Nếu giải nén, redact IP, chuyển format, giải mã hoặc lọc gói, byte đầu ra khác byte đầu vào nên hash khác là bình thường. Phải tạo evidence/derived ID mới và ghi bản gốc đã được dùng, điều kiện biến đổi và phiên bản công cụ.

### 12.1. Đặc thù của PCAP

- Ghi capture point/interface, BPF filter, snaplen, link-layer type, start/end UTC và tool/version.
- Giữ counters captured/received/dropped khi có; packet loss tại sensor khác packet loss trên dây.
- Ghi tình trạng SPAN/TAP, tunnel, VLAN, NAT, proxy, checksum/segmentation offload, lưu lượng bất đối xứng.
- PCAPNG có thể chứa interface names, comments, name-resolution blocks, cần bảo vệ metadata đó.
- Display filter Wireshark chỉ thay phần hiển thị, không xóa byte khỏi file gốc.
- Phân tích trên file copy, ghi filter, stream ID và hash bản exported packets.

~~~bash
# Đọc bản làm việc khi được phép; không sửa bản gốc.
tcpdump -nn -r /secure-evidence/INC-2026-031/working/sample.pcap \
  'host 192.0.2.10 and port 443'

# Kiểm tra metadata file capture bằng công cụ tương ứng nếu có.
capinfos /secure-evidence/INC-2026-031/working/sample.pcap
~~~

`192.0.2.10` là địa chỉ tài liệu TEST-NET. Một bản PCAP không thấy gói có thể do sensor đặt sai, capture filter bỏ qua, traffic đi đường khác hoặc gói bị rơi ở sensor. Không tự kết luận gói không tồn tại.

### 12.2. Đặc thù của SIEM/cloud query

Khi xuất kết quả từ SIEM, lưu query text, index/dataset, tenant/account/region, timezone, time field được tìm, query time, page/cursor, limit, record count, parser/enrichment version nếu biết. Một screenshot không thay thế raw export.

Với cloud log, ghi rõ logging đã bật trước sự kiện hay chưa, nguồn control-plane/data-plane, region, API pagination, ingest lag, export job, object generation/version và thời gian giữ. Một số cloud services ghi logs theo chế độ tùy chọn; không được giả định nhà cung cấp đã lưu mọi event cần điều tra.

## 13. Phát hiện log gap, sai lệch thời gian và nguồn bị xâm phạm

| Dấu hiệu | Các khả năng | Cần đối chiếu |
|---|---|---|
| Mất nhiều phút log | Collector down, rotation, filter, attacker tắt logging | Collector health, syslog sender, audit config, nguồn khác |
| Timestamp nhảy/đảo | NTP step, timezone sai, buffer/retry, chỉnh đồng hồ | NTP log, ingest time, event ID/sequence |
| Record count giảm bất thường | Sampling, lỗi export, ingestion drop | Counters, flow volume, API pages, system logs |
| Hash thay đổi | Khác phiên bản, sửa dữ liệu, copy thiếu, hỏng file | Object version, audit, manifest tin cậy |
| Duplicate events | Retry, at-least-once delivery, replay | Message ID, partition/offset, collector logs |
| NAT mapping không khớp | IP/port tái sử dụng, thiếu thời gian, tunnel khác | Session ID, lease, full 5-tuple, clock uncertainty |
| SIEM thiếu một field quan trọng | Parser/schema version hoặc raw event không có | Raw message, pipeline config, mapping |

Khi nghi ngờ nguồn bị thao túng, bảo toàn dữ liệu hiện có và log về thay đổi quyền/cấu hình, đối chiếu nguồn độc lập. Không xóa bản bị nghi giả để “làm sạch”; bản này có thể là bằng chứng của việc che giấu hành vi. Kết luận phải ghi rõ “không phát hiện trong phạm vi đã kiểm tra” khi chưa thể chứng minh toàn bộ hệ thống không có sự kiện.

## 14. Dữ liệu nhạy cảm, retention và legal hold

Log mạng có thể chứa IP cá nhân, username, tên thiết bị, domain, URL, cookie, API token, mật khẩu truyền rõ, dữ liệu kinh doanh hoặc payload được giải mã. Khóa TLS/SSLKEYLOGFILE và memory dump có thể còn nhạy cảm hơn log thông thường.

Thực hành bảo vệ:

- Chỉ thu theo mục đích, hạn chế time range, source/segment, volume; không tự động bật full capture toàn mạng.
- Gắn classification phù hợp cho file gốc, metadata, bản dẫn xuất, screenshot và phụ lục báo cáo.
- Quản lý quyền đọc/tải, mã hóa, khóa giải mã, audit và các bản sao lưu.
- Redact trên bản làm việc/xuất báo cáo khi có căn cứ; giữ bản gốc trong kho được kiểm soát nếu cần phục vụ điều tra.
- Xác định thời hạn retention theo chính sách, pháp luật/hợp đồng và mục đích hợp lệ, không tự đặt “giữ mãi”.
- Nếu có **legal hold**, ghi căn cứ, phạm vi, owner, thời điểm review và cơ chế giải phóng khi không còn hiệu lực.
- Khi hết hạn và không có nghĩa vụ giữ lại, xóa theo quy trình đối với object version, replica, cache, snapshot, working copy và backup; ghi biên bản và xác minh.

Xóa object chính chưa đảm bảo đã xóa bản sao hoặc phiên bản cũ. Crypto-erasure chỉ có ý nghĩa khi tất cả bản cần xóa thực sự phụ thuộc khóa đã bị hủy và không có plaintext copy độc lập.

## 15. Tình huống thực tế: nghi vấn DNS tunneling qua VPN

Giả sử IDS cảnh báo DNS query có nhãn dài, tần suất cao từ một IP VPN tới domain đáng ngờ. Mục tiêu điều tra là xác định phiên VPN, thiết bị liên quan, luồng bị firewall xử lý như thế nào và khả năng dữ liệu thoát ra ngoài.

**Bằng chứng cần giữ:** IDS alert và rule version; DNS resolver query/raw response; VPN auth, session/assigned IP; NGFW NAT/allow/deny; SIEM raw events và trạng thái parser; PCAP vòng đệm tại sensor nếu còn và thuộc phạm vi được phép.

**Thứ tự thao tác:** chốt case và quyền, ưu tiên DNS log/PCAP ring buffer/NAT table sắp mất, export các nguồn khác, ghi source time/config, tính hash sau khi export ổn định, lập manifest, chuyển kho, tạo working copy và tương quan bằng session ID + IP/port + khoảng thời gian hiệu lực.

### 15.1. Timeline minh họa

| UTC | Nguồn | Sự kiện | Giới hạn |
|---|---|---|---|
| 02:24:30 | VPN | Máy D nhận IP 10.20.1.5 | Phải kiểm tra session và lease validity |
| 02:31:13 | DNS | Query tên miền đáng ngờ | Chưa biết clock offset resolver |
| 02:31:15 | IDS | Alert nghi vấn DNS tunneling | Signature có thể false positive |
| 02:31:16 | Firewall | NAT mapping của flow tương ứng | Cần full 5-tuple và thời gian |
| 02:35:00 | SIEM | Analyst nhận cảnh báo | Đây là mốc nhận, không phải mốc bắt đầu |
| 05:10:00 | Custodian | Export log, chốt SHA-256 | Mốc thu thập, khác event time |

**Điều có thể nói:** trong phạm vi logs đã thu, những query và flow liên quan xuất hiện theo mốc trên; nếu VPN session mapping đủ, có thể quy về thiết bị/phiên tương ứng. **Điều chưa được chứng minh:** exfiltration đã thành công, toàn bộ DNS traffic đã được quan sát, chính người sở hữu tài khoản là người thao tác, hoặc payload đã ra khỏi mạng. Cần thêm bằng chứng phù hợp trước khi kết luận.

Khi chuyển dữ liệu cho nhóm khác, không gửi toàn bộ PCAP qua email nhóm. Cấp quyền theo case, ghi nhận người nhận, mục đích, thời điểm, hash tại hai đầu và nơi lưu mới; báo cáo phổ biến chỉ đưa dữ kiện đã rà soát và tham chiếu tới evidence ID.

## 16. Runbook thực hành từ đầu đến cuối

~~~text
1. TRIAGE:
   incident_id, phạm vi, người phê duyệt, người thu, custodian.

2. INVENTORY:
   nguồn dữ liệu, thiết bị, lưu lượng quan sát được,
   retention/rotation, log gaps, dữ liệu dễ mất.

3. ACQUIRE:
   export/snapshot theo quyền và phương pháp đã duyệt;
   ghi UTC, command/API, query/filter, tool, version, lỗi.

4. SEAL:
   chốt file, kiểm tra size/record/page/offset,
   tính SHA-256, tạo evidence_id và manifest.

5. STORE:
   kho mã hóa, IAM ít quyền, audit truy cập,
   retention/hold, ghi bàn giao và hash người nhận.

6. ANALYZE:
   tạo working copy, ghi tool/query/transform,
   so nguồn độc lập, chuẩn hóa timestamp có giới hạn.

7. REPORT:
   timeline, phát hiện, chứng cứ, độ tin cậy,
   unknowns, kết luận và đề xuất tiếp theo.

8. CLOSE:
   xử lý legal hold, retention, các bản copy/backup,
   biên bản xóa hoặc gia hạn có phê duyệt.
~~~

### 16.1. Điều kiện có thể đánh dấu việc bảo toàn là hoàn thành

- Tệp và đối tượng trong manifest tồn tại, số byte/hash được ghi trên bản export ổn định.
- Source, time range, method, query/filter và công cụ được lưu đủ để hiểu phép thu.
- Đã kiểm tra hoặc ghi rõ giới hạn pagination, record count, packet drop, sampling và log gap.
- Timestamp gốc được giữ, timezone/clock uncertainty được đánh giá; không tự ý đổi mốc trên bản nguồn.
- Custodian và các lần bàn giao có record, quyền đọc/ghi phù hợp.
- Dữ liệu gốc, bản làm việc và derived artifacts có thể phân biệt và truy vết.
- Retention/hold, bản sao và yêu cầu xóa được xác định theo chính sách.

Nếu chưa đáp ứng một điều kiện, ghi chính xác phần chưa xác minh; không tự gắn nhãn “đầy đủ” cho chứng cứ.

## 17. Các sai lầm thường gặp

1. Chỉ chụp dashboard SIEM, không lưu raw export, query, limit và pagination.
2. Dùng trình soạn thảo sửa timestamp, lọc hoặc xóa field trong bản gốc.
3. Hash file log còn đang ghi, rồi coi giá trị là bằng chứng ổn định.
4. Cho phép cùng một admin sửa file chứng cứ lẫn manifest và audit log.
5. Đồng nhất clock time của thiết bị với event time chính xác, không xét NTP offset.
6. Lấy IP VPN/NAT làm danh tính cố định, không xét lease và session.
7. Giả định chỉ số `allow` ở firewall chứng minh ứng dụng đã nhận request.
8. Giả định thiếu IDS alert tức là chắc chắn không có xâm nhập.
9. Cho rằng PCAP đầy đủ, bỏ qua dropped packets, offload, snaplen và sensor location.
10. Quên ghi tool version, SIEM parser, filter, ngày xuất hoặc output hash.
11. Chuyển dữ liệu qua email/link rộng quyền mà không ghi người nhận và bản sao.
12. Xóa log cần giữ hoặc giữ dữ liệu nhạy cảm vô thời hạn vì không rõ retention.
13. Nhầm integrity, authenticity và completeness là cùng một thuộc tính.
14. Chỉ ghi “bản đã kiểm tra” nhưng không có bằng chứng checksum, actor và thời điểm.

## 18. Checklist triển khai

### Trước khi thu

- [ ] Có incident ID, scope, mục tiêu và quyền thu thập hợp lệ.
- [ ] Có inventory log, điểm đặt sensor, NAT/LB/proxy mapping và retention.
- [ ] Đã ưu tiên session table, ring buffer, ephemeral logs và nguồn dễ mất.
- [ ] Đã xác định dữ liệu nhạy cảm, kho mã hóa, custodian, quyền và thời hạn giữ.

### Trong lúc thu và bàn giao

- [ ] Ghi source, UTC, tool/version, command/API, query, filter, người thực hiện.
- [ ] Ghi số record, pagination/offset, export errors, packet drops và clock offset.
- [ ] Chốt export, ghi size, SHA-256, manifest và giá trị hash được bảo vệ.
- [ ] Người nhận kiểm tra size/hash và xác nhận chain of custody.
- [ ] Không thay đổi bản gốc; working copy và output có định danh/hạn lưu riêng.

### Trong lúc phân tích và đóng vụ việc

- [ ] Lưu query/transform/parser version, input/output hash và đánh giá tính đầy đủ.
- [ ] Phân biệt event time, ingest time, collection time và sai số đồng hồ.
- [ ] Tương quan nhiều nguồn và nêu giới hạn chứng cứ trong kết luận.
- [ ] Chỉ chia sẻ dữ liệu giảm nhạy cảm theo phạm vi; kiểm soát quyền và audit.
- [ ] Kiểm tra legal hold, retention, object versions, bản sao và biên bản xóa.

## 19. Câu hỏi tự kiểm tra

**1. Tính SHA-256 cho bản log DNS đã đủ chứng minh dữ liệu đó là thật và đầy đủ chưa?**

Chưa. Hash xác minh byte so với chuẩn tin cậy, không khẳng định nguồn gốc hoặc đầy đủ. Phải xem cách thu, cấu hình logging, số record, gap, clock và các nguồn độc lập.

**2. Một PCAP được gửi qua email, người nhận tính hash khớp. Chain of custody đã đủ chưa?**

Chưa chắc. Cần ghi danh tính, lúc gửi/nhận, mục đích, nơi lưu, xác nhận bàn giao, các bản sao email và chính sách xử lý chúng. Hash không thay thế lịch sử truy cập.

**3. Firewall ghi allow nhưng server không có log request. Có thể khẳng định server nhận gói không?**

Không. Kiểm tra đường đi, NAT, proxy, PCAP tại các điểm quan sát và server logs. Allow chỉ phản ánh một quyết định tại firewall.

**4. Một log có mốc 09:00 +0700 và log khác là 09:00Z. Có đồng thời không?**

Không. Mốc 09:00 +0700 tương ứng 02:00Z; chuẩn hóa UTC trong bản làm việc và xét clock skew.

**5. SIEM export trả đúng hash nhưng chỉ lấy tối đa 10.000 event. Dữ liệu đã bảo toàn đầy đủ chưa?**

Chưa. Cần biết tổng record, pagination/cursor, bộ lọc, sampling, ingestion delay và các trang/chunk còn thiếu.

**6. WORM storage có làm cho chain of custody trở nên không cần thiết?**

Không. WORM giảm nguy cơ sửa sau khi ghi, nhưng nguồn có thể không đáng tin và vẫn phải ghi người đọc, bàn giao, tạo bản sao, giải mã, phân tích, retention và xử lý hold.

**7. Khi legal hold kết thúc có thể xóa ngay mọi log không?**

Chỉ khi không còn nghĩa vụ giữ hợp lệ khác và chính sách cho phép. Cần rà soát bản chính, version, backup, snapshot và ghi biên bản xử lý.

---

**Ghi nhớ:** Chất lượng điều tra mạng phụ thuộc vào **nguồn và ngữ cảnh log**, **tính toàn vẹn của byte và metadata**, **chuỗi trách nhiệm khi thu/bàn giao**, và **khả năng tái lập phân tích**. Giữ bản gốc, bảo vệ manifest, kiểm tra giới hạn dữ liệu và ghi chain of custody từ acquisition đến khi kết thúc vòng đời.
