# Kết thúc vòng đời lưu trữ bằng chứng trong điều tra số trên mạng

Trong chương **Điều tra số trên mạng** thuộc module **SECURITY_NETWORK_SECURITY**, bằng chứng không kết thúc vòng đời khi điều tra viên viết xong báo cáo hoặc đội SOC đóng một incident ticket. Các bản **PCAP, NetFlow/IPFIX, DNS, DHCP, NAT, firewall, VPN, IDS/IPS, TLS metadata, endpoint/network logs, cloud audit, timeline và artifacts được trích xuất** có thể tiếp tục được lưu giữ phục vụ kiểm toán, yêu cầu pháp lý, rà soát sự cố hoặc đối chiếu các cuộc điều tra khác. Đồng thời, chúng có thể chứa **dữ liệu cá nhân, topology, session identifiers, nội dung truyền qua mạng hoặc secrets**; giữ quá lâu hoặc xóa sai thời điểm đều tạo rủi ro.

**Kết thúc vòng đời lưu trữ bằng chứng** là quy trình có kiểm soát để xác nhận một tập bằng chứng đã hoàn thành mục đích lưu giữ hợp lệ, không còn nghĩa vụ bảo toàn đang có hiệu lực, được quyết định **chuyển lưu trữ, bàn giao, hủy hoặc tiếp tục giữ theo ngoại lệ**, và có đủ hồ sơ chứng minh mọi thao tác. Đây là vấn đề kết hợp **network forensics, incident response, bảo toàn chain of custody, quản trị dữ liệu, an toàn lưu trữ và phân quyền quyết định**.

Nguyên tắc trọng tâm:

> **Không xóa vì ticket đã đóng; không giữ mãi vì “biết đâu sau này cần”.** Mỗi artifact phải có căn cứ lưu giữ, owner, thời hạn, trạng thái hold, quyết định disposition và bằng chứng hoàn tất.

**Sau bài học, người học có thể:**

- Phân biệt **đóng điều tra, đóng case, hết hạn lưu giữ, chuyển archive, release legal hold và hủy bằng chứng**.
- Lập **evidence inventory** với source/provenance, hash, phiên bản, vị trí lưu, độ nhạy, retention rule, case links, hold scope và bản sao.
- Thiết kế **retention schedule** theo chính sách áp dụng mà không tự bịa thời hạn pháp lý.
- Giữ và xác minh **chain of custody**, audit trail, integrity checks, restore test và quyền truy cập khi bàn giao/archive.
- Xử lý **legal hold, pending litigation, regulatory request, data subject request, multi-case references, vendor/cloud storage và backups** trước khi hủy.
- So sánh **logical deletion, sanitization, cryptographic erase, backup expiry, immutable/WORM retention** và các giới hạn xác minh.
- Thực hiện quy trình **approval → pre-disposition review → execution → verification → certificate/closure**, có rollback hoặc ngoại lệ thích hợp.
- Dùng **lab với metadata giả** để kiểm tra quyết định retention/hold/disposition mà **không hủy dữ liệu thật**.

**Phạm vi và giới hạn:** Nội dung mô tả nguyên tắc kỹ thuật/quản trị tổng quát, không thay thế quyết định của pháp chế, quy định lưu trữ, hợp đồng hoặc chính sách của tổ chức. Tất cả domain **.example**, IP từ dải tài liệu, case ID và thời điểm trong ví dụ đều giả định. Không thực hiện lệnh xóa, thay quyền hoặc thay cấu hình production ngoài quy trình được phê duyệt.

## 1. “Kết thúc” một vòng đời bằng chứng nghĩa là gì?

Một artifact có thể đã hết giá trị cho điều tra hiện tại nhưng **vẫn phải lưu** vì hold, kiểm toán, điều tra liên quan hoặc quy định. Ngược lại, một case vẫn mở có thể không cần giữ tất cả bản sao tạm nếu bản gốc được bảo toàn và quy trình cho phép loại bỏ bản dẫn xuất không cần thiết.

### 1.1. Các trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Hành động mặc định |
| --- | --- | --- |
| **Active collection** | Bằng chứng đang được thu phục vụ IR/forensics | Thu trong scope, ghi provenance |
| **Preserved** | Raw artifact được bảo quản để giữ nguyên tính toàn vẹn | Giới hạn ghi/sửa, kiểm tra hash |
| **Analysis/working** | Tạo bản làm việc, decoded flows, extracts, annotations | Kiểm soát bản sao/PII, theo dõi lineage |
| **Case closed** | Điều tra có quyết định kết thúc phần phân tích hiện tại | Review retention/hold; **không tự xóa** |
| **Archived** | Chuyển sang tầng lưu trữ bảo toàn dài hạn/ít truy cập | Kiểm tra manifest, khả năng truy xuất, restore test |
| **Legal/administrative hold** | Phải tạm ngừng disposition theo phạm vi hold | Giữ đúng scope, khóa deletion jobs |
| **Disposition approved** | Có quyết định đúng thẩm quyền cho hành động cuối | Kiểm tra điều kiện ngay trước thi hành |
| **Disposed/transfer completed** | Đã hủy hoặc bàn giao đúng quy trình, có xác nhận | Giữ hồ sơ tối thiểu về quyết định/thao tác |
| **Exception pending** | Có blocker về quyền, cloud copy, backup, thiết bị không truy cập được | Chưa tuyên bố hoàn tất |

**Case closure không đồng nghĩa evidence destruction** và **archival không đồng nghĩa disposal**. Một quyết định disposition có thể là **retain**, **transfer**, **archive**, **anonymize** hoặc **securely dispose**, tùy loại đối tượng, chính sách và nghĩa vụ.

### 1.2. Mô hình vòng đời

~~~mermaid
flowchart TD
    A["Evidence acquired / registered"] --> B["Preserve raw + hash + custody"]
    B --> C["Analyze / derive artifacts / correlate cases"]
    C --> D["Case review / retention schedule"]
    D --> E{"Active legal/admin hold or other obligation?"}
    E -->|Có| F["Freeze disposition in scoped stores"]
    F --> G["Periodic hold review + evidence integrity"]
    G --> E
    E -->|Không| H{"Disposition decision approved?"}
    H -->|Chưa| I["Retain with owner and review date"]
    I --> D
    H -->|Có| J{"Disposition type"}
    J -->|Archive/transfer| K["Transfer + validate manifest/restore"]
    J -->|Secure disposal| L["Sanitize authorized copies/keys/media"]
    K --> M["Receipt + audit record"]
    L --> N["Verify disposal and residual copies"]
    N --> M
    M --> O["Close custody/disposition record"]
~~~

Vòng lặp **review hold/retention** là phần bắt buộc; sự cố kết thúc về mặt vận hành không tự chấm dứt nghĩa vụ lưu giữ.

## 2. Những loại bằng chứng mạng và lý do nhạy cảm

### 2.1. Nhận diện dữ liệu theo lớp

| Artifact | Nội dung có thể chứa | Rủi ro chính khi lưu giữ |
| --- | --- | --- |
| **Full PCAP/PCAPNG** | Packet headers, payload plaintext nếu có, DNS/TLS metadata | Lộ nội dung, secrets, endpoint topology |
| **TLS/session-key diagnostics** | Traffic trace và session secrets được thu có quyền | Có thể giải mã traffic trong phạm vi tương ứng |
| **NetFlow/IPFIX/sFlow** | Flows, IP/port, bytes, timing, interface | Tiết lộ patterns/metadata, sampling limits |
| **Firewall/NAT logs** | Quyết định policy, translated IP/port, zones | Sơ đồ network và mapping người dùng |
| **VPN/ZTNA/IdP logs** | User/session, auth/MFA, device posture | PII, security context, identity trail |
| **DNS/DHCP logs** | Queries, IP leases, device identifiers | Hoạt động truy cập, user/device attribution |
| **IDS/IPS/NDR events** | Alerts, packet snippets, signatures | False-positive risk, payload snippets nhạy cảm |
| **Proxy/WAF/app logs** | Host/path/status, headers và đôi khi body | URI có token/PII, customer/business data |
| **Endpoint/EDR exports** | Process, connections, memory/host artifacts | Personal data, credential exposure |
| **Cloud/Kubernetes audit** | Policy changes, service IDs, workload state | Access topology, identity, tenant metadata |
| **Analysis artifacts** | Timeline, extracted files, screenshots, IOC, notes | Kế thừa nhạy cảm và lỗi diễn giải từ raw |
| **Reports/custody records** | Kết luận, people/case references, hashes | Confidential investigation information |

**Không coi network metadata là không nhạy cảm.** Một IP, domain và timestamp khi được ghép với VPN/IdP có thể tiết lộ hoạt động của một cá nhân. Ngược lại, không phải mọi PCAP đều có plaintext: TLS/QUIC có thể mã hóa application content, nhưng vẫn có metadata nhạy cảm.

### 2.2. Raw, working copy, derivative và published report

- **Raw source:** dữ liệu đầu vào được thu theo phương pháp được phê duyệt, giữ nguyên bytes.
- **Forensic/working copy:** bản dùng phân tích và triage, có thể tạm thời.
- **Derivative:** reassembled TCP streams, filtered PCAP, decoded file, timeline CSV, SIEM export, graph, screenshot, trích IOC.
- **Report:** diễn giải/số liệu đã review; có thể được gửi cho người không có quyền xem raw.
- **Disposition record:** minh chứng quá trình lưu giữ, chuyển giao hoặc hủy; thường phải giữ theo lịch riêng.

Không tự gán **thời hạn derivative = raw** nếu chính sách có phân loại; đồng thời không để một bản screenshot/CSV giữ secret đã có trong PCAP sau khi bản raw được xử lý.

### 2.3. Theo dõi quan hệ nguồn–dẫn xuất

~~~text
EVID-001 raw capture (restricted)
  +-- EVID-001-A filtered pcap (working copy)
  +-- EVID-001-B extracted HTTP headers (redacted)
  +-- EVID-001-C flow summary
  +-- EVID-001-D analyst timeline visualization
  +-- CASE-2026-17 technical report

Each descendant has:
  parent reference, creation time, creator, storage location,
  sensitivity, retention/hold applicability, disposition owner.
~~~

Khi kết thúc lưu trữ, **lineage graph** giúp kiểm tra **cả bản gốc và các dẫn xuất**, không chỉ file có tên “evidence.pcap”.

## 3. Điều kiện trước khi được xem xét disposition

Một artifact chỉ nên vào quy trình ra quyết định cuối khi thỏa hoặc được xử lý rõ các điều kiện sau:

1. **Ownership xác định:** có case owner/evidence custodian và đúng tài sản thuộc phạm vi.
2. **Inventory đầy đủ trong mức hợp lý:** đã biết các bản lưu chính, bản sao, exports, snapshots, backups và vendor copies liên quan.
3. **Mục đích lưu giữ rõ:** incident response, audit, litigation, operational support, regulatory hoặc hợp đồng.
4. **Retention rule có căn cứ:** bắt đầu đếm từ mốc nào và thời điểm review/expiry nào.
5. **Hold status được kiểm tra:** legal hold, dispute, regulator request, security investigation liên quan.
6. **Cross-case dependency:** không có case đang mở sử dụng artifact, hoặc quyết định hold/retain đã xử lý.
7. **Integrity/provenance:** manifest, hashes và chain-of-custody history đáng tin.
8. **Disposal method phù hợp:** media/cloud encryption/immutable storage/backup có phương án khả thi.
9. **Approval đúng cấp:** legal/privacy/compliance/security/records và business owner khi quy định.
10. **Verification plan:** biết cách xác minh hành động hoàn tất và cách ghi exceptions.

### 3.1. Ma trận điều kiện “được phép hủy?”

| Tình trạng | Quyết định kỹ thuật an toàn |
| --- | --- |
| Retention chưa hết | Chưa hủy; giữ và đặt kỳ review |
| Active legal hold | **Không hủy** phần nằm trong scope hold |
| Có case khác đang giữ dependency | Thẩm định với case owner và legal/records |
| Không rõ có hold không | **Tạm dừng disposition**, hỏi owner có thẩm quyền |
| Storage bất biến chưa tới expiry | Không cố phá retention lock; xử lý theo cơ chế hợp lệ |
| Hết hạn, không hold, đầy đủ approval | Được chuyển sang **execution** theo SOP |
| Đã xóa bản chính nhưng backup còn | Chưa tuyên bố tất cả copies đã được hủy |
| Vendor chưa xác nhận thực thi | Theo dõi pending; không đánh dấu fully verified |
| Bằng chứng cần tiếp tục dùng cho audit | Retain/archive có owner và lịch riêng |

### 3.2. Không đồng nhất tài liệu kỹ thuật với thẩm quyền pháp lý

Đội Forensics có thể đánh giá **evidence còn được tham chiếu hay không và tác dụng kỹ thuật của cách hủy**, nhưng **không tự quyết định nghĩa vụ pháp lý đã hết**. Khi có tranh chấp, rủi ro khiếu kiện, kiểm toán hoặc yêu cầu cơ quan quản lý, cần Legal/Records/Compliance theo quy trình. Bài không đặt một số năm lưu giữ áp dụng cho mọi tổ chức hay quốc gia.

## 4. Retention schedule: giữ bao lâu và bắt đầu tính từ đâu?

**Retention schedule** là bảng chính sách chỉ ra loại hồ sơ, mục đích, sự kiện kích hoạt (trigger), thời gian giữ, cơ chế hold override, địa điểm lưu, owner và phương án disposition.

### 4.1. Một retention rule phải định nghĩa đầy đủ

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Record category** | PCAP, firewall log, audit case, incident report hay custody record? |
| **Purpose/legal basis** | Vì sao được hoặc phải giữ? |
| **Trigger event** | Bắt đầu tính từ **collection, case closure, fiscal period end, contract end** hay sự kiện khác? |
| **Duration** | Bao lâu theo **chính sách/luật/hợp đồng** được áp dụng? |
| **Hold precedence** | Hold làm tạm dừng gì và được release bằng cách nào? |
| **Storage controls** | Encryption, RBAC, immutability, location, restore expectation |
| **Review cadence** | Khi nào xem lại và ai nhận nhắc việc? |
| **Disposition route** | Archive/transfer/destruction/anonymization, với điều kiện nào? |
| **Exceptions** | Ai được duyệt, scope, lý do, expiry, compensating controls? |
| **Proof** | Cần receipt/hash/log/audit/certificate nào? |

### 4.2. Trigger có thể khác nhau theo loại hồ sơ

Giả sử một PCAP được thu ngày 01/05, case đóng ngày 10/06. Nếu policy tính từ **collection date** và policy khác tính từ **case closure date**, hai ngày expiry khác nhau. Không tự lấy ngày cuối cùng được copy vào archive làm trigger trừ khi policy nói thế.

Thêm nữa, **retention duration là ví dụ chính sách chứ không phải tiêu chuẩn chung**. Mọi giá trị minh họa về ngày/giờ ở bài này đều không phải yêu cầu pháp luật.

### 4.3. Nhiều rules đồng thời

Một artifact có thể thuộc:

- Network forensic incident record.
- Personal data record.
- Contractual audit evidence.
- Active dispute/litigation hold.
- Regulated-sector record.

Không dùng một TTL kỹ thuật ngắn để bỏ qua một nghĩa vụ giữ còn hiệu lực; ngược lại, không giữ vô hạn nếu hết các căn cứ giữ hợp lệ. **Records/Legal** cần xác định precedence theo quy định/chính sách.

### 4.4. Retention clock và timezone

Lưu các mốc quan trọng ở **UTC có timezone/offset và source provenance**. Khi policy tính theo **ngày lịch** thay vì 24 giờ chính xác, phải tuân quy tắc lịch/timezone của policy; không tự làm tròn bằng cách cộng tùy tiện một số giây nếu có daylight saving hoặc trigger là “cuối năm tài chính”.

## 5. Legal hold và nghĩa vụ bảo toàn vượt lịch xóa

**Legal hold** (hoặc preservation hold có thẩm quyền tương tự) là yêu cầu bảo toàn hồ sơ trong phạm vi xác định bất chấp lịch disposition thông thường. Đây không đơn thuần là cờ “keep forever”; cần **scope, issuer, reason/reference, effective time, custodians, covered systems, review cadence và release procedure**.

### 5.1. Trạng thái hold

| Trạng thái | Ý nghĩa | Disposal? |
| --- | --- | --- |
| **None confirmed** | Đã kiểm tra nguồn hold có thẩm quyền trong thời điểm review | Tiếp tục các điều kiện khác |
| **Pending review** | Đang đánh giá khả năng hold hoặc yêu cầu mới | **Tạm dừng** |
| **Active hold** | Có chỉ thị có hiệu lực trong scope | **Không** với artifact thuộc scope |
| **Partially scoped** | Hold chỉ áp một tập files/cases/people/time | Phân loại đúng từng artifact; không suy toàn bộ |
| **Release authorized** | Người có thẩm quyền ký giải tỏa | Review retention và holds khác trước khi disposition |
| **Disputed/unknown** | Có xung đột về phạm vi/hiệu lực | Tạm dừng và escalation |

### 5.2. Một hold có thể phủ cả dẫn xuất và hệ thống bên ngoài

Ví dụ hold cho incident liên quan egress ngày 01–07/06 có thể áp lên **raw PCAP, filtered PCAP, NetFlow exports, proxy transaction records, EDR process traces, timeline, audit report và vendor-hosted copy**, tùy wording của lệnh. Đội kỹ thuật cần **mapping data locations + lineage** để triển khai hold đúng, không tự cắt phạm vi.

### 5.3. Quy trình khi hold được kích hoạt

1. Nhận chỉ thị qua **kênh có thẩm quyền**, lưu issuer/reference/effective scope.
2. Xác định **case/evidence IDs, custodians, storage buckets, backups, vendors** liên quan.
3. Dừng **scheduled deletion/lifecycle policies** đối với phần trong scope bằng phương thức hợp lệ.
4. Xác minh thay đổi đã áp dụng tại **tầng dữ liệu**, không chỉ email xác nhận.
5. Gửi preservation notice và instructions tới custodians/vendor đúng phạm vi.
6. Lưu **hold acknowledgment, applied time, coverage gaps**.
7. Review định kỳ và theo dõi **hold modifications**.
8. Chỉ release theo **đúng chủ thể có thẩm quyền**; sau release chạy lại **retention/disposition review**, không auto-delete ngay.

### 5.4. Lưu ý khi hệ thống đã auto-expire dữ liệu

Nếu một bản log đã bị hệ thống xóa trước khi hold tới, không được khẳng định có thể phục hồi. Cần **ghi loss window, retention policy, backup availability, lịch sử thông báo và nguyên nhân** cho legal/incident team. Không dựng lại “bản gốc” từ summary rồi tuyên bố là bit-for-bit identical.

## 6. Thẩm quyền và phân tách trách nhiệm

Không nên để một cá nhân **định nghĩa thời hạn, tự phê duyệt và xóa bản gốc** không có kiểm tra. Quy trình cần phân tách hợp lý theo độ nhạy/rủi ro.

### 6.1. RACI minh họa

| Công việc | Responsible | Accountable | Consulted |
| --- | --- | --- | --- |
| Evidence inventory/lineage | Forensics custodian | IR/Forensics lead | Network/SOC |
| Retention rule mapping | Records/Data governance | Records authority | Legal/Compliance/Security |
| Hold scope và release | Legal hold coordinator | Legal/authorized office | Custodians, Records |
| Archive architecture | Storage/Platform | Data owner | Security, IR, Privacy |
| Integrity verification | Forensic analyst | Evidence custodian | Security assurance |
| Disposition approval | Records/Legal process owner | Authorized approver | IR, case owner |
| Destruction execution | Storage operations | Data/evidence owner | Security/Cloud/Vendor |
| Destruction verification | Independent reviewer khi yêu cầu | Records/Compliance | Storage/Custodian |
| Closure record & audit | Evidence custodian | Case/Records owner | Legal, Security |

**RACI chỉ là ví dụ**, quyền cụ thể phải căn cứ vào chính sách tổ chức. Đối với artifacts có tranh chấp hay yêu cầu bảo toàn, cần workflow phê duyệt chặt hơn dữ liệu vận hành thông thường.

### 6.2. Người phê duyệt khác người thực thi

- **Case owner:** xác nhận tình trạng điều tra/các điều tra liên quan.
- **Records/Legal:** xác định nghĩa vụ và permission cho disposition.
- **Custodian:** chịu trách nhiệm inventory và chain of custody.
- **Storage/cloud owner:** kiểm tra thao tác archive/delete/retention locks.
- **Verifier:** kiểm tra outcome, pending copies/backup và đóng hồ sơ.

Trong môi trường nhỏ một người có thể mang nhiều vai trò, nhưng vẫn cần **audit trail và approval kiểm tra độc lập theo mức rủi ro**.

## 7. Evidence inventory: danh sách phải đủ trước khi đóng lưu giữ

Một evidence manifest chuẩn có thể có:

~~~yaml
evidence_id: "EVID-LAB-012"
case_ids: ["INC-LAB-012", "AUDIT-LAB-02"]
artifact_type: "network-pcap"
source_system: "lab-network-sensor"
capture_scope: "owned-loopback-test-traffic"
collection_time_utc: "2026-11-28T08:10:00Z"
custodian: "forensics-custodian"
original_name: "capture-test.pcapng"
size_bytes: 4096
hash_algorithm: "SHA-256"
hash_value: "<TO_BE_MEASURED_FROM_REAL_ARTIFACT>"
sensitivity: "restricted"
primary_location_ref: "evidence-vault/object/demo-012"
derivatives: ["EVID-LAB-012-A", "EVID-LAB-012-B"]
other_copies: ["working-lab-copy", "backup-reference"]
retention_policy_ref: "POLICY-EXAMPLE-ONLY"
retention_trigger: "case_closure"
retention_start_utc: null
hold_state: "review_required"
disposition_state: "not_approved"
last_integrity_verification_utc: null
~~~

Đây là **schema học tập**, không được coi là policy thực hay hash thật. Các trường trống/null cho thấy **chưa đủ dữ kiện** để hủy, không phải cho phép bỏ qua.

### 7.1. Inventory phải bao phủ nhiều nơi

Ngoài evidence vault chính, kiểm tra khả năng có:

- Local workstation analyst downloads, temp folders, forensic workstation images.
- SIEM exports, search snapshots, case attachments, SOC tickets.
- EDR/NDR consoles và vendor-managed investigations.
- Object storage, cloud regions/replicas, immutable buckets.
- Backups, snapshots, DR copies, tape/offline media.
- Remote endpoint caches và files chuyển cho đối tác có quyền.
- Data warehouses và dashboard/report exports.
- Email/chat đã chia sẻ artifacts, nếu việc thu hồi thuộc quyền/chính sách.
- Build/test artifacts có vô tình chứa PCAP/log snippets hay không.

Không phải lúc nào mọi bản sao đều tìm được tuyệt đối; cần ghi **search scope, uncertainty, owners và residual risk**, không tự tuyên bố “đã xóa tất cả” khi chưa kiểm chứng.

### 7.2. Một artifact có thể thuộc nhiều case

Nếu PCAP EVID-012 thuộc case A đã đóng nhưng case B đang điều tra, disposition phải xét **tất cả case references**, kể cả legal holds riêng. Không dựa vào một ticket đã closed để xóa file đang làm bằng chứng cho ticket khác.

## 8. Disposition review: quyết định đúng trạng thái cuối

**Disposition** không đồng nghĩa duy nhất “delete”. Nó là quyết định xử lý hồ sơ khi tới mốc review/expiry. Với từng evidence ID, có thể chọn **tiếp tục giữ, archive, transfer, minimize/anonymize có điều kiện hoặc destroy**, tùy chính sách và tình trạng pháp lý.

### 8.1. Ma trận quyết định

| Mục đích/nhiệm vụ còn tồn tại | Trạng thái hold | Lựa chọn phù hợp | Điều kiện |
| --- | --- | --- | --- |
| Điều tra vẫn mở | Bất kỳ | **Preserve/retain** | Không làm mất evidence đang phục vụ điều tra |
| Case đóng, retention chưa hết | Không | **Retain hoặc archive** | Có vault owner, integrity, access và review date |
| Case đóng, retention hết | Active | **Preserve under hold** | Xác nhận hold scope và không xóa |
| Case đóng, retention hết | Không có, đã xác minh | **Disposition approval review** | Xác nhận copies, case links, legal/records approval |
| Data còn được yêu cầu bởi case khác | Tùy | **Retain/transfer ownership** | Có custody transfer và phạm vi mới |
| Hết hạn nhưng backup immutable còn | Không | **Schedule expiry/exception** | Không tuyên bố destruction toàn bộ |
| Được yêu cầu bàn giao sang archive khác | Tùy | **Controlled transfer** | Hash/manifest, receipt và continuity of custody |
| Không còn căn cứ lưu bản chi tiết, aggregate còn hợp lệ | Không | **Minimize/anonymize theo policy** | Xác minh tính không thể tái nhận diện trong bối cảnh phù hợp |
| Hết nghĩa vụ, đủ approval và phương pháp | Không | **Secure disposal** | Execution + verification + certificate |

### 8.2. Tách quyết định và thực thi

Một quyết định phải có:

~~~text
Disposition proposal ID:
Evidence IDs and exact scope:
Case status and last review:
Retention policy version and trigger:
All active/pending hold checks:
Cross-case dependencies:
Storage locations/known copies:
Sensitivity and privacy assessment:
Proposed action + technical method:
Approver(s), approval time, expiry of approval:
Execution change ticket and planned window:
Verification criteria and residual risk:
~~~

**Approval cũng có thể hết hiệu lực:** nếu legal hold xuất hiện giữa lúc phê duyệt và lúc thực thi, phải **dừng và review lại**, không dùng approval cũ để xóa.

## 9. Archive là một trạng thái lưu giữ có kiểm soát

Một số evidence không cần truy cập hàng ngày nhưng vẫn phải lưu. **Archiving** có thể giảm rủi ro thao tác nhầm và chi phí, song phải bảo đảm dữ liệu **có thể truy xuất, hiểu, xác thực và bàn giao** khi cần.

### 9.1. Kiến trúc lưu trữ minh họa

~~~mermaid
flowchart LR
    A["Active forensic workspace"] --> B["Evidence staging"]
    B --> C["Hash/manifest + owner/retention check"]
    C --> D["Encrypted archive vault"]
    D --> E["Immutable/audit-controlled metadata"]
    D --> F["Authorized restore area"]
    F --> G["Restore verification and logging"]
    C --> H["Evidence ledger + custody record"]
    G --> H
~~~

### 9.2. Chuẩn đầu vào archive

- **Artifact manifest:** evidence IDs, file paths/object keys, sizes, file formats, hash algorithms/values.
- **Metadata:** capture vantage, sensor/parser version, network time source, case/owner, sensitivity, collection method.
- **Chain of custody:** source custodian, destination custodian, transfer details, approvals.
- **Data integrity:** pre-transfer checksum, post-transfer check ở object đích và manifest.
- **Encryption/access:** encryption at rest/in transit, KMS/HSM/key escrow theo chính sách, role restrictions.
- **Retention/hold:** tags và controls được gắn đúng cho object/derivatives.
- **Retrievability:** restore/access test theo risk tier, không chỉ kiểm tra danh sách file.
- **Format longevity:** biết cách đọc PCAPNG/JSON/proprietary evidence, parser/tool versions, schema docs.

### 9.3. Transfer receipt

~~~text
Transfer ID: TRANSFER-LAB-012
Source custodian: forensic-team
Destination custodian: archive-operations
Evidence scope: EVID-LAB-012 and scoped derivatives
Manifest reference: MANIFEST-LAB-012
Approved destination: vault-class-restricted
Transport encryption: per approved standard
Source hash verified: YES (actual record required)
Destination hash verified: YES (actual record required)
Archive retention/hold policy applied: review evidence required
Restore sample test: pass/fail with test ID
Transfer time UTC and two-party acknowledgment
~~~

Không điền **YES** khi thao tác thực chưa được kiểm chứng. Receipt là kết quả của quy trình, không phải template được điền để hợp thức hóa.

### 9.4. Archive format và khả năng đọc về sau

Một PCAP/PCAPNG giữ nguyên bytes nhưng sau nhiều năm có thể:

- Thiếu **capture metadata** (interface, snaplen, timezone, packet-loss counters).
- Dùng encapsulation/vendor format mà công cụ hiện tại không đọc.
- Mất **application decoder/plugin/version** dùng cho derived analysis.
- Có chứng thư/chữ ký cần kiểm tra bằng trust anchors lịch sử.

Nên lưu **format version, minimal decoder specification và hash manifest**, kiểm thử restore+read ở chu kỳ phù hợp. **Chuyển đổi định dạng** nên tạo một derivative mới, giữ raw artifact theo retention/hold, không âm thầm ghi đè file gốc.

## 10. Tính toàn vẹn: hash, chữ ký, metadata và kiểm tra định kỳ

### 10.1. Hash có và không chứng minh điều gì?

Cryptographic hash như SHA-256 giúp xác định file bytes **có thay đổi** so với digest đã ghi và bảo vệ đúng cách. Hash **không tự chứng minh**:

- Sensor ban đầu không bị tampering.
- Host clock và timestamps chính xác.
- PCAP chứa tất cả packets.
- Người bị nghi là actor thực.
- Archive owner có quyền pháp lý giữ file.

Tính toàn vẹn kỹ thuật cần kết hợp **provenance, authenticated source, collection log, access controls và chain of custody**.

### 10.2. Integrity verification ở từng bước

| Bước | Kiểm tra |
| --- | --- |
| Thu thập | Digest + kích thước + source/source-time + capture tool |
| Đưa lên evidence vault | Verify upload complete, digest sau transfer |
| Tạo derivative | Parent ID, method/tool/version, digest derivative |
| Di chuyển archive | Manifest, pre/post digests, metadata consistency |
| Restore từ archive | Bytes restored so với hash đã lưu, parsing smoke test |
| Trước disposition | Evidence ID/size/hash, owner/hold/locations đúng |
| Sau disposal | Kiểm tra object không còn truy xuất theo phương pháp; ghi receipt |

### 10.3. Integrity scan và bit rot

Storage có thể gặp **bit rot, media failure, lỗi replication hoặc silent corruption**. Archive policy nên đặt kỳ kiểm tra integrity theo **độ quan trọng và khả năng phục hồi**. Nếu hash mismatch:

1. Không “sửa hash mới” thành đúng mà không điều tra.
2. Cô lập bản bị nghi lỗi và giữ log kiểm tra.
3. So với source/raw digest đã ký/trusted ledger.
4. Kiểm tra replicas/backups còn nguyên vẹn.
5. Khôi phục từ bản tin cậy theo change/custody process.
6. Ghi incident về evidence integrity và tác động pháp lý/điều tra.

### 10.4. Digital signatures và audit logs

Chữ ký điện tử phù hợp có thể xác thực người/phần mềm **ký một manifest** và giúp kiểm tra việc sửa đổi. Nó không thay kiểm tra xem manifest có **đúng tập evidence** hay không. Audit trail cần bảo vệ khỏi người có quyền thay chính evidence đồng thời xóa lịch sử truy cập; tổ chức có thể dùng **segregated append-only records** theo kiến trúc.

### 10.5. Vòng đời hash/reference sau khi hủy

Sau disposal, có thể cần giữ **hash, evidence ID, loại artifact, receipt và quyết định** làm chứng từ kiểm toán theo policy riêng. Nhưng hash/metadata đôi khi có thể là dữ liệu nhạy cảm hoặc định danh gián tiếp; không mặc định giữ vĩnh viễn. **Retention của destruction certificate** là một loại hồ sơ riêng.

## 11. Mã hóa và quản trị khóa trong evidence vault

Archive encryption bảo vệ confidentiality nhưng không thay retention/hold và không tự bảo đảm integrity.

### 11.1. Những kiểm soát cần có

- **Encryption at rest** và encryption khi chuyển giao.
- Quản trị **master keys/data encryption keys** theo vai trò, rotation và recovery policy.
- Tách quyền **xem evidence** khỏi quyền **quản lý khóa/xóa evidence** khi khả thi.
- **Audit** khi decrypt/download/restore/export.
- Kiểm tra **backup/escrow** các khóa cần thiết để phục hồi archive.
- Đảm bảo retention của **encrypted artifacts và keys** nhất quán với legal hold.
- Khóa không còn cần giữ được xử lý theo **cryptographic lifecycle** được duyệt.

### 11.2. Lỗi khi chỉ giữ ciphertext

Nếu archive vẫn còn nhưng khóa giải mã bị hủy trước retention expiry, bằng chứng có thể **không thể truy cập** dù files tồn tại. Ngược lại, nếu keys còn trên backup hoặc được dùng chung cho nhiều objects, một thao tác “crypto erase” trên một key copy có thể **không làm mất khả năng giải mã**.

### 11.3. Backup keys và legal hold

Khi có hold, phải xét cả **KMS key deletion schedule, BYOK/HYOK dependencies, backups/escrow, HSM recovery**, vì sự cố mất key cũng có thể vi phạm nghĩa vụ bảo toàn. Không đưa khóa bí mật vào evidence manifest; chỉ dùng **key reference** và policy controls.

## 12. Quản lý access và kết thúc quyền của đội điều tra

Khi case chuyển sang archive hoặc đóng, việc giữ nguyên quyền đọc rộng của analysts là **rủi ro** ngay cả khi chưa xóa file.

### 12.1. Review quyền theo trạng thái

| Trạng thái | Quyền truy cập hợp lý |
| --- | --- |
| Active incident | Nhóm IR được chỉ định, access logging |
| Working analysis | Người phân tích theo nhiệm vụ, quyền với raw/derivative tách biệt |
| Case closed, retention active | Chỉ custodians/authorized reviewers và request-based access |
| Legal hold | Preservation controls, truy cập theo hold scope và need-to-know |
| Long-term archive | Roles hạn chế, break-glass có audit/approval |
| Disposition execution | Approver, executor và verifier theo phân tách trách nhiệm |
| Post-disposition | Chỉ metadata/receipt còn được phép giữ |

### 12.2. Quy trình revoke access

1. Xuất danh sách **users, groups, roles, service accounts, token grants và external shares**.
2. Xác định ai vẫn cần phục vụ audit/hold và owner cho future requests.
3. Gỡ **case-specific temporary grants** theo approval.
4. Thu hồi **sharing links, API tokens, temporary export credentials** khi không cần.
5. Kiểm tra **effective permissions** thay vì chỉ policy config (kể cả inherited roles).
6. Kiểm toán event **access revoke** và thử rằng unauthorized principal không còn đọc được.
7. Giữ kênh truy xuất hợp lệ cho **custodians hoặc legal hold users**.

**Revoke analyst access** khác **delete evidence** và có thể được thực hiện khi retention vẫn còn.

### 12.3. Authorized restore không được làm mất chain of custody

Khi archive được restore phục vụ case mới, ghi **requestor, authorization, source manifest, restore destination, checksum, purpose, new copy ID và retention linkage**. Không để các bản restore tồn tại vô thời hạn ở workstation không có inventory.

## 13. Bản sao ở cloud, SIEM, tickets và bên thứ ba

Một artifact có thể được sao chép tự động hoặc thủ công qua nhiều systems, mỗi nơi có mô hình retention và deletion semantics khác nhau.

### 13.1. Bản đồ dữ liệu theo nơi

~~~mermaid
flowchart TD
    E["Raw evidence vault"] --> W["Analyst workstation copies"]
    E --> S["SIEM/NDR case exports"]
    E --> C["Cloud object storage replicas"]
    E --> T["Ticket attachments / reports"]
    E --> B["Backup / DR snapshots"]
    E --> V["Approved vendor/partner transfer"]
    W --> I["Disposition inventory and owners"]
    S --> I
    C --> I
    T --> I
    B --> I
    V --> I
~~~

### 13.2. Mỗi destination cần metadata riêng

| Trường | Ví dụ lý do cần |
| --- | --- |
| **Copy/replica ID** | Không nhầm original và derivative |
| **Destination owner** | Ai có quyền thực hiện disposition |
| **Storage service/region** | Data residency và replication boundaries |
| **Retention/hold controls** | Có policy/hold theo object/case không? |
| **Access class** | Raw PCAP nhạy cảm không giống report summary |
| **Disposal support** | Delete object, lifecycle expiry, media sanitize hoặc vendor request |
| **Verification method** | Audit response, object inventory, receipt, deletion attestation |
| **Backup dependencies** | Bản sao có xuất hiện trong snapshots/DR không? |

### 13.3. Cloud deletion khác toàn bộ physical erasure

Xóa object qua API có thể khiến object không còn truy xuất theo quyền bình thường nhưng dữ liệu vật lý có thể được nhà cung cấp xử lý theo **replication, retention, versioning và backend lifecycle**. Không tuyên bố “mọi byte đã bị ghi đè trên thiết bị” khi chỉ có **DeleteObject API success**. Dùng **provider commitments/attestations**, cơ chế mã hóa hoặc chính sách sanitize được duyệt và ghi rõ mức xác minh.

### 13.4. Versioning và delete markers

Trong một object store có **versioning**, thao tác delete có thể chỉ thêm **delete marker** trong khi các **previous versions** vẫn tồn tại. Cần biết retention/hold và version policy, kiểm tra **all versions/replicas** trong scope trước khi chứng nhận disposition. Không chạy script purge phiên bản trên production khi chưa có thẩm quyền.

### 13.5. Ticket và chat attachments

Một sanitized summary trong ticket khác về độ nhạy với raw PCAP được upload. Inventory cần ghi **report recipients, attachment owners, external sharing và chính sách xóa của hệ thống**, không cố “xóa hoàn toàn email đã gửi” nếu sản phẩm/giới hạn pháp lý không cho phép; ghi rõ phần không thể thu hồi.

## 14. Backups, snapshots, DR và immutable/WORM storage

### 14.1. Vì sao backup là điểm khó?

Backup thường tối ưu **khôi phục dữ liệu**, không phải xóa một file đơn lẻ ngay lập tức. Một artifact đã hết hạn ở primary store có thể còn trong **encrypted snapshots, incremental backups, offline tape hoặc DR region**.

### 14.2. Các tình huống

| Tình huống | Điều cần làm |
| --- | --- |
| Backup cho phép granular delete an toàn | Theo quy trình đã duyệt, không phá khả năng restore dữ liệu khác |
| Backup chỉ hết hạn theo vòng đời | Ghi **scheduled expiry và coverage**, theo dõi tới khi hết |
| Immutable/WORM lock chưa hết | Giữ nguyên, ghi blocker/expiry, không bypass |
| Legal hold bảo toàn cả backups | Suspend expiry theo scope hợp lệ |
| Backup chứa nhiều case/dữ liệu chung | Không destroy toàn backup chỉ vì một artifact hết hạn |
| DR copy trên region khác | Kiểm tra owner, residency, policy và verification |
| Backup thiếu khả năng chứng minh từng object đã purge | Nêu limitation; không cấp false attestation |

### 14.3. WORM là bảo vệ, cũng tạo ràng buộc

**Write Once Read Many (WORM)** hoặc object retention lock giúp giảm nguy cơ evidence bị sửa/xóa, nhưng có thể khiến hủy trước thời hạn **không khả thi**, kể cả khi bản chính hết mục đích. Phải thiết kế retention policy đúng **trước khi bật khóa bất biến** và có quy trình exception/legal review.

### 14.4. Backup lifecycle và hold release

Sau release hold, **không tự động xóa mọi backups ngay lập tức**: kiểm tra các retention rules khác, khả năng restore, dependencies và approval. Một backup đang hết hạn theo chính sách có thể được giữ tới lần lifecycle purge hợp lệ. Trong disposition report, ghi **“primary removed; backup retained until scheduled expiry”** nếu thực tế như vậy.

### 14.5. Kiểm thử restore trước khi long-term archive

Một archive có hash đúng nhưng không thể giải mã/đọc file hoặc thiếu metadata vẫn có thể thất bại mục đích lưu giữ. Phải thử **restore + verification + parser/readability** phù hợp với risk tier; test bản sao, không làm thay đổi raw artifact.

## 15. Pre-disposition review: kiểm tra lần cuối trước thao tác không thể đảo ngược

Thời điểm một yêu cầu được ký và thời điểm triển khai có thể cách nhau nhiều ngày. Trong thời gian đó có thể xuất hiện **legal hold mới, incident liên quan, storage migration hoặc copy mới**. Vì vậy cần **pre-execution gate** ngay trước thao tác.

### 15.1. Bảy câu hỏi tối thiểu

1. Evidence ID/object version chính xác và **hash/inventory** có khớp manifest không?
2. Retention expiry đã thực sự tới theo **đúng trigger/timezone/policy version** chưa?
3. Có **active/pending/disputed hold** nào mới không?
4. Có **cross-case references hoặc pending appeals/requests** chưa xử lý không?
5. Approval còn hiệu lực cho **đúng scope, phương pháp và địa điểm** không?
6. Mọi **primary, replicas, derivatives, snapshots, vendor copies, backups** đã được phân loại với trạng thái rõ không?
7. Có **verification plan, designated executor, independent reviewer và rollback/exception approach** phù hợp không?

Nếu bất kỳ điều kiện quan trọng nào là **unknown**, dừng, xác minh, hoặc tạo exception với approver; không coi unknown là “không có rủi ro”.

### 15.2. Khóa thao tác trên đúng tập object

Không dùng filename prefix mơ hồ như **case-\*** để chọn hàng nghìn objects. Dùng **immutable evidence IDs, exact object/version references hoặc approved manifest**, kiểm tra dry-run listing và số lượng/size trước khi có change approval.

**Số lượng đối tượng chọn để hủy** phải khớp scope đã ký. Nếu phát sinh object ngoài manifest, dừng và investigate; không “mở rộng” lệnh vì tiện.

### 15.3. Hai cấp phê duyệt theo rủi ro

Với raw PCAP liên quan pháp lý hoặc hồ sơ có dữ liệu cá nhân nhạy cảm, tổ chức có thể yêu cầu:

- **Records/Legal approval** cho điều kiện được disposition.
- **Technical execution authorization** cho chính xác phương pháp, địa điểm, thời gian và người kiểm chứng.

Hệ thống nên kiểm tra quyền bằng **policy-as-code/approval workflow** nếu phù hợp, nhưng không bỏ human escalation cho tình huống hold hoặc ownership bất định.

## 16. Các phương án hủy an toàn và giới hạn xác minh

**Secure disposal** là lựa chọn kỹ thuật phù hợp để làm dữ liệu không thể truy xuất theo mức rủi ro/chính sách. Không nên đồng nhất **nhấn Delete, dọn Recycle Bin, ghi đè file một lần, cryptographic erase và hủy vật lý media**: chúng có tiền đề và mức assurance khác nhau.

### 16.1. Phân loại phương pháp

| Phương pháp | Ý tưởng | Giới hạn cần biết |
| --- | --- | --- |
| **Logical deletion** | Xóa tham chiếu/object hoặc quyền truy cập thông thường | Snapshots, versions, recovery areas, backups có thể còn |
| **Application/API deletion** | Dùng workflow chính thức của storage/SaaS | Phụ thuộc provider retention/replication semantics |
| **Media sanitization** | Làm dữ liệu trên phương tiện không còn phục hồi theo mức kiểm soát | Phải phù hợp media technology và chính sách, có verification |
| **Cryptographic erase** | Làm key material cần thiết để giải mã không còn sử dụng được | Chỉ đáng tin khi encryption/key scope và key destruction đáp ứng tiền đề |
| **Physical media destruction** | Loại bỏ/tiêu hủy vật lý theo quy trình | Không áp dụng tùy tiện với shared cloud storage; có chi phí/chain of custody |
| **Scheduled backup expiry** | Để backup hết hạn theo lifecycle có kiểm soát | Không chứng minh đã biến mất trước expiry; phải ghi pending |
| **Anonymization/minimization** | Giữ phần dữ liệu không còn nhận dạng theo tiêu chí phù hợp | Có nguy cơ tái nhận diện; không mặc định tương đương hủy |

### 16.2. Clear, purge, destroy là các mức mục tiêu chứ không phải một lệnh

Trong quy trình sanitization, các khái niệm **clear/purge/destroy** thường chỉ các mức loại bỏ khả năng khôi phục khác nhau. Lựa chọn phụ thuộc **độ nhạy, threat model, loại phương tiện và yêu cầu quản trị**. Không gán một thuật toán ghi đè duy nhất phù hợp mọi HDD, SSD, tape, cloud object hoặc thiết bị chuyên dụng.

### 16.3. Lựa chọn phương pháp theo kiểm soát thực tế

~~~mermaid
flowchart TD
    A["Disposition approved + no active hold"] --> B{"Media/storage ownership"}
    B -->|Physical media under control| C["Approved sanitization/destruction SOP"]
    B -->|Cloud object/SaaS| D["Provider lifecycle, versions, replicas, attestations"]
    B -->|Immutable backup| E["Scheduled expiry or approved exception"]
    C --> F["Execution log + independent verification"]
    D --> F
    E --> G["Pending until eligible completion"]
    F --> H{"Verification complete for scoped copies?"}
    H -->|Có| I["Issue precise disposition certificate"]
    H -->|Chưa| G
~~~

### 16.4. Vì sao bài không đưa lệnh xóa production?

Một lệnh xóa theo đường dẫn hoặc bucket prefix có thể làm mất **bằng chứng thuộc case khác, backup hoặc dữ liệu không thuộc scope**. Quy trình triển khai phải dựa trên **manifest chính xác, approvals, quyền hạn, công cụ vendor và môi trường**; bài chỉ cung cấp các kiểm tra, mô hình ra quyết định và lab không phá dữ liệu.

## 17. Hủy theo loại phương tiện: HDD, SSD, USB, tape và VM disks

### 17.1. HDD truyền thống

Với ổ đĩa từ tính do tổ chức sở hữu, phương pháp sanitization phải được chọn theo **media/vendor capabilities, tình trạng thiết bị, data classification và quy trình đã duyệt**. Một file-level overwrite không chứng minh mọi bản sao, filesystem journal, snapshots hoặc spare regions đã xử lý.

### 17.2. SSD, NVMe, flash và wear leveling

**Wear leveling, overprovisioning, remapped blocks và controller behavior** có thể khiến ghi đè logical file không bảo đảm toàn bộ flash cells cũ bị ghi. Cần sử dụng **supported sanitize/secure erase mechanisms** và đánh giá cryptographic erase nếu encryption architecture đáp ứng. Đừng đoán mức assurance dựa trên “đã ghi số 0 vào file”.

### 17.3. USB/SD/removable media

Removable media có thể thất lạc, hỏng hoặc không hỗ trợ sanitize đáng tin. Khi hết vòng đời:

- Có inventory **serial/asset ID** nếu khả dụng.
- Xác nhận owner và evidence scope.
- Chọn phương pháp theo media class.
- Ghi custody transfer tới bộ phận xử lý.
- Nhận **certificate/receipt và reconciliation** của thiết bị.

Không tuyên bố đã hủy nếu USB được gửi cho vendor nhưng chưa có bằng chứng vendor nhận/xử lý theo thỏa thuận.

### 17.4. Tape/offline backups

Tape có thể chứa nhiều case/đối tượng. Việc hủy một cuộn tape vì một PCAP hết hạn có thể làm mất hồ sơ khác vẫn có nghĩa vụ lưu. Phải quản lý **media catalog, expiration, hold và chain of custody** ở mức tape set và các record bên trong.

### 17.5. VM disk images và snapshots

Xóa một file trong máy ảo không nhất thiết xóa bytes ở **base disk, checkpoints, snapshots, replication images hoặc cloud volume backups**. Nếu evidence được chứa trong VM image, inventory phải liên kết **disk versions/snapshots/backups và encryption keys**, không chỉ filesystem path hiện tại.

### 17.6. Thiết bị lỗi và media không đọc được

Một ổ hỏng không thể verify từng byte không nên được coi là “đã an toàn vì không mount được”. Cần **quy trình destruction/sanitization cho failed media**, ghi serial, custody và verification phù hợp. Nếu nhà cung cấp chỉ trả “device retired” mà không có attestation cần thiết, phải ghi limitation.

## 18. Cryptographic erase: mạnh khi tiền đề đúng, nguy hiểm nếu hiểu sai

**Cryptographic erase (CE)** dựa trên việc dữ liệu được mã hóa đủ tốt và việc làm không còn khả năng dùng **key material** khiến ciphertext không thể giải mã theo threat model. CE có thể phù hợp với cloud/SSD/encrypted vault nhưng cần đánh giá kỹ trước khi coi đã disposal.

### 18.1. Các điều kiện phải kiểm tra

1. Dữ liệu luôn được **mã hóa thích hợp trước khi ghi lên media** trong phạm vi cần hủy.
2. Thuật toán/key management đáp ứng mức an toàn và threat model.
3. Key nằm trong **đúng scope**, không dùng chung với dữ liệu vẫn phải giữ.
4. Không có **plaintext copies, unencrypted caches, temp files hoặc extracted derivatives** ngoài phạm vi.
5. Mọi **key copies, backup/escrow, recovery material và wrapped-key versions** được xử lý theo policy.
6. Không có **active legal hold** yêu cầu giữ khả năng giải mã.
7. Key deletion/revocation thực sự có hiệu lực theo **provider/HSM semantics**, không chỉ request accepted.
8. Có kiểm chứng và **audit record** đáp ứng yêu cầu disposition.

### 18.2. Ví dụ key hierarchy

~~~text
Evidence object ciphertext
   └── DEK-EVID-012  (data-encryption key)
         └── wrapped by KEK-ARCHIVE-01
               └── protected by KMS/HSM root

Question:
  Is DEK exclusive to this evidence object?
  Does another wrapped copy/backup exist?
  Is plaintext present in another store?
  Does the active hold require key preservation?
~~~

Nếu chỉ xóa một bản wrapped DEK nhưng còn bản recoverable ở nơi khác, không được chứng nhận đã CE hoàn tất. Nếu xóa **KEK dùng chung**, có thể làm mất khả năng đọc những evidence khác chưa hết hạn, gây hậu quả nghiêm trọng.

### 18.3. Rotation khác destruction

**Key rotation** có thể tạo key mới và giữ khả năng giải mã dữ liệu cũ bằng key trước hoặc rewrap; vì vậy **rotation không mặc định là cryptographic erasure**. Muốn khẳng định CE, phải kiểm tra thực tế **khả năng phục hồi từ tất cả key paths có quyền**.

### 18.4. Encryption key không chứng minh toàn bộ copies đã xóa

Nếu có **PCAP được trích thành CSV plaintext** ở analyst workstation hoặc được dán vào ticket, CE ở evidence vault không ảnh hưởng các bản sao đó. Cần **lineage và copy inventory**.

### 18.5. Không dùng CE để giải quyết hold conflict

Khi retention hoặc legal hold đang có hiệu lực, việc hủy key cần để đọc evidence có thể tương đương làm mất bằng chứng. Quy trình phê duyệt phải đối chiếu **records/hold policy** trước mọi key lifecycle action có tác động không thể đảo ngược.

## 19. Bên thứ ba, SaaS và xác nhận disposition

Khi evidence đã được chia sẻ cho **cloud provider, MSSP, forensic consultancy, external counsel hoặc vendor support**, tổ chức cần hiểu **ai sở hữu data, ai xử lý deletion/retention và ai có thể chứng nhận kết quả**.

### 19.1. Điều cần có trong yêu cầu gửi vendor

- Evidence/copy IDs hoặc exact data scope.
- Contractual **retention/disposal obligation** và thẩm quyền yêu cầu.
- Xác nhận không có **hold/other obligation** ngăn hủy.
- Loại dữ liệu (raw PCAP, log export, report, derived files).
- Địa điểm/region/tenancy khi có.
- Cách vendor xử lý **replicas, backups, subprocessors và immutable storage**.
- Thời điểm dự kiến và giới hạn thực tế của deletion.
- Cách vendor cung cấp **attestation/receipt, exception hoặc residual retention**.

### 19.2. Đọc vendor attestation chính xác

| Vendor nói | Có thể kết luận | Không nên kết luận |
| --- | --- | --- |
| “Deleted from active service” | Không còn phục vụ trong active scope vendor xác nhận | Mọi backup/physical media đã purge |
| “Scheduled to expire from backups” | Có kế hoạch expiry được khai báo | Backup đã được hủy ngay |
| “Encryption key disabled” | Khóa bị disable theo service semantics | Không có key copies hoặc plaintext khác |
| “All contract-defined copies disposed” | Vendor attest scope theo hợp đồng | Những nơi ngoài hợp đồng do người dùng tự tạo |
| “Ticket closed” | Support workflow kết thúc | Data disposition được chứng minh hoàn toàn |

### 19.3. Khi vendor từ chối hoặc không thể hủy ngay

Ghi **exception ID, lý do, contractual/technical limitation, copy scopes, owner, residual risk, review date và compensating controls**. Chỉ ghi hoàn tất khi **mức hoàn tất thực sự** được chứng minh. Không dùng tuyên bố chung chung “vendor đã xử lý” thay cho attestation trong đúng phạm vi.

### 19.4. Mỗi tổ chức có bản sao riêng

Nếu báo cáo được gửi cho external counsel hoặc cơ quan có thẩm quyền theo quy trình, bên nhận có thể có **nghĩa vụ bảo quản độc lập**. Không tự yêu cầu xóa trái thẩm quyền hoặc giả định tổ chức có quyền xóa data trong hệ thống bên nhận. Điều này cần được Legal/Records giải quyết.

## 20. Verification sau disposition: điều gì thực sự được xác minh?

### 20.1. Xác nhận xóa logic và xóa thực tế khác nhau

Một API trả trạng thái thành công chỉ chứng minh **hệ thống chấp nhận thao tác theo semantics đã định**. Cần kiểm tra:

1. **Đúng evidence IDs/version IDs** đã xử lý.
2. Object không còn **truy xuất trong active scope** theo yêu cầu.
3. **Previous versions/replicas** đã được xử lý hoặc còn với exception rõ.
4. **Backup/DR copies** ở trạng thái đã xử lý hoặc chờ expiry có owner.
5. Vendor attestation phù hợp với thỏa thuận.
6. **Hold/retention audit** không ghi sai hoặc mâu thuẫn.
7. **Disposition evidence** được lưu vào đúng ledger và phê duyệt closure.

### 20.2. Verification matrix

| Scope | Kỹ thuật xác minh minh họa | Mức khẳng định |
| --- | --- | --- |
| Primary object | Inventory/read attempt theo quyền và service API | Không còn truy xuất ở primary scope |
| Versioned object | Object version list/lifecycle audit theo service | Các versions trong scope đã xử lý |
| Storage media | Vendor sanitize result, serial/custody receipt | Media xử lý theo SOP/attestation |
| Cryptographic erase | Key lifecycle audit, thiết kế key scope, validation | Key path trong scope không còn khả dụng |
| Local working copies | Approved endpoint inventory/removal attestation | Các copies được kiểm tra không còn |
| Backups | Backup catalog/expiry job report | Backup đã hết hoặc còn theo lịch nêu rõ |
| External vendor | Contractual completion confirmation | Vendor attest trong phạm vi xác định |
| Case/ticket copies | Attachment inventory và access revocation log | Những attachments trong scope đã được xử lý |

### 20.3. Không “kiểm thử” bằng cách khôi phục secret ngoài thẩm quyền

Một phép xác minh không nên đòi analyst tìm cách **tái tạo credential, giải mã trái phép traffic hoặc truy cập vùng storage ngoài quyền**. Dùng các control-plane/service-supported verification methods phù hợp, với test accounts và scope được phê duyệt.

### 20.4. Verification fail

Nếu một phần không xử lý được:

- **Không ký “fully disposed”**.
- Ghi precisely **scope completed, scope pending/blocked, reason**.
- Tạm giữ metadata/approval/custody và mở follow-up.
- Không tiếp tục xóa lan rộng ngoài manifest để “đạt 100%”.
- Gắn owner, review date và ngưỡng escalation.

## 21. Chứng nhận hủy và hồ sơ kết thúc (certificate/closure record)

**Certificate of destruction/disposition** là hồ sơ xác nhận một thao tác theo phương pháp, thời gian và phạm vi đã thực hiện. Nó **không tự chứng minh** đã xử lý những bản sao nằm ngoài những gì ghi trong chứng nhận.

### 21.1. Những trường nên có

~~~yaml
certificate_id: "CERT-LAB-012"
evidence_ids: ["EVID-LAB-012"]
disposition_type: "secure_disposal"
approved_scope_ref: "APPROVAL-LAB-012"
policy_ref: "POLICY-EXAMPLE-ONLY"
hold_check_ref: "HOLD-REVIEW-LAB-012"
execution_time_utc: null
executor: null
verifier: null
method: "TO_BE_SELECTED_BY_APPROVED_SOP"
storage_locations_completed: []
copies_verified: []
copies_pending: ["backup-lifecycle-review"]
vendor_attestation_refs: []
verification_result: "PENDING"
limitations: ["No execution has occurred in this example"]
chain_of_custody_ref: "CUSTODY-LAB-012"
certificate_retention_class: "SEPARATE_POLICY_REQUIRED"
~~~

Đây là **bản mẫu chưa thực thi**. Không chuyển trạng thái sang PASS nếu vẫn có backup pending hoặc phương pháp chưa được áp theo policy.

### 21.2. Câu chữ xác nhận nên chính xác

Không nên:

> “Toàn bộ bằng chứng đã bị xóa vĩnh viễn khỏi mọi hệ thống.”

Khi thực tế chỉ biết primary object đã xóa và backup còn theo vòng đời, viết:

> “Bản active trong evidence vault đã được disposition theo approval X và được xác minh không còn truy xuất tại scope Y. Backup copy Z đang chờ scheduled expiry theo policy P; hồ sơ vẫn mở ở trạng thái partial completion.”

### 21.3. Closure record không được gây hồi sinh secrets

Không dán raw PCAP, tokens hoặc full content vào certificate. Dùng **evidence IDs, hash values nếu policy cho phép, method, scope, storage class, approvals và links tới restricted ledger**.

### 21.4. Retention của chứng nhận

Hồ sơ về việc hủy có thể phải **giữ dài hơn hoặc khác** bằng chứng đã hủy, tùy quy định. Giữ đúng những metadata cần cho accountability, có phân loại và lịch review riêng, không dùng “đã xóa PCAP” làm lý do tự động xóa dấu vết quyết định.

## 22. Exception, partial completion và tranh chấp

Quy trình disposition thực tế thường không kết thúc gọn bằng một nút Delete. Cần mô hình quản lý trường hợp ngoại lệ.

### 22.1. Các trường hợp cần mở exception

| Trường hợp | Trạng thái đúng | Hành động |
| --- | --- | --- |
| Vendor không gửi deletion attestation | **Vendor verification pending** | Theo dõi contract/SLA/escalation |
| Immutable backup chưa hết TTL | **Retained until scheduled expiry** | Ghi backup ID, due date, owner |
| Object version còn do hold khác | **Hold retained** | Kiểm tra và giải quyết scope theo thẩm quyền |
| Không rõ nơi copy một PCAP đã chia sẻ | **Inventory incomplete** | Điều tra scope, hạn chế quyền, ghi residual risk |
| Integrity mismatch trước archive | **Quarantined for review** | Điều tra corruption/tampering, không hủy nguồn |
| KMS key shared với evidence khác | **Crypto erase not eligible** | Chọn phương pháp khác, review key hierarchy |
| Requester không có thẩm quyền disposition | **Approval rejected** | Escalate tới Records/Legal/owner |
| Case khác vừa reopen | **Disposition suspended** | Review dependencies và hold |

### 22.2. Exception không được ẩn khỏi dashboard

Một dashboard có thể báo:

~~~text
Cases reviewed for disposition:      30
Fully completed:                    20
Archived/transferred with receipt:   5
Legal hold / retained:               3
Pending vendor/backup verification:   2

All values are illustrative.
~~~

Không báo **“30 cases destroyed”** khi 10 case có trạng thái khác. Thước đo nên phân biệt **approved, executed, verified, partial và held**.

### 22.3. Không làm giảm khả năng điều tra còn mở

Trong trường hợp một incident được reopen sau khi dữ liệu đã disposition hợp lệ, đội điều tra chỉ dùng **những artifacts thực sự còn tồn tại và các record được phép giữ**. Không bịa reconstruction để thay raw evidence đã mất. Nếu retention policy dẫn đến mất dữ liệu cần thiết cho recurring incidents, ghi **lesson learned** và review policy, không tự đổ lỗi cho người làm đúng quy trình.

### 22.4. Trường hợp yêu cầu xóa dữ liệu cá nhân

Yêu cầu của chủ thể dữ liệu có thể tương tác với **nghĩa vụ lưu giữ bằng chứng, legal hold và regulatory obligations**. Không hứa xóa ngay mọi evidence nếu có yêu cầu bảo toàn hợp lệ; cũng không viện dẫn “security” để giữ vô hạn. Quyết định cần từ **Privacy/Legal/Records**, và hồ sơ phải phản ánh **phạm vi được xóa, phạm vi phải giữ, lý do và thời điểm xem lại**.

## 23. Runbook từ case closure đến evidence storage closure

Runbook nên có thể **thực hiện lặp lại, kiểm toán được và dừng an toàn** khi xuất hiện dữ liệu mới. Các bước không thay thế legal approval của tổ chức.

### Giai đoạn A — Đóng phần điều tra và chuyển giao

1. Incident commander/case owner xác nhận **phạm vi phân tích đã kết thúc hoặc được bàn giao**.
2. Kiểm tra **case report, timeline, findings, corrective actions, pending technical investigation** và yêu cầu lưu dữ liệu.
3. Xuất danh sách **raw evidence và derivatives**, liên kết từng file với evidence ID.
4. So sánh **custody ledger, forensic workstation, incident ticket, SIEM exports, cloud store và shared copies**.
5. Khóa/ghi trạng thái final **analysis outputs**, không chỉnh sửa raw evidence.
6. Chuyển quyền lưu giữ sang **evidence custodian/records owner** nếu cần.

### Giai đoạn B — Retention và holds

1. Xác định **policy/version và retention trigger** cho từng artifact class.
2. Review **all active/pending/disputed legal holds**, litigation/audit/regulatory requests.
3. Xác định **cross-case dependencies** và người chịu trách nhiệm.
4. Ghi **expiry/review date** theo timezone và luật/chính sách áp dụng.
5. Nếu có hold, **freeze disposition trong scope** và lập kỳ review.
6. Nếu chưa hết retention, chọn **retain/archive** thay vì hủy.

### Giai đoạn C — Archival/transfer khi cần

1. Xác định archive class, encryption keys, immutable/hold settings và access model.
2. Lập **manifest** và hash/integrity baseline của raw/derivatives trong scope.
3. Chuyển giao qua kênh được phê duyệt, ghi **source/destination custodian**.
4. So pre/post digests, file counts, sizes, metadata và case references.
5. Thử **authorized restore/readability** đúng loại artifact.
6. Revoke working grants/temporary copies theo approval và scope.
7. Ghi **transfer receipt, archive owner, next review**.

### Giai đoạn D — Disposition approval khi hết điều kiện giữ

1. Chạy **pre-disposition gate** ngay trước dự kiến thực thi.
2. Chuẩn bị exact **evidence/version/copy manifest** và method phù hợp media.
3. Review **backup, snapshots, replicas, shared keys, vendors, external copies**.
4. Lấy approvals với **scope/method/expiry** rõ; không mở rộng theo prefix tùy ý.
5. Chỉ định **executor, verifier, rollback/exception route**, change window.
6. Tách dữ liệu chưa đủ điều kiện (hold/pending/unknown) khỏi tập được phép xử lý.

### Giai đoạn E — Thực hiện và xác minh

1. Thực hiện theo **SOP và công cụ vendor** được duyệt, không chạy lệnh ad hoc từ tài liệu này.
2. Ghi execution audit: **time, actor, service/API, object versions/media IDs, result codes**.
3. Verify đúng scope qua **control-plane inventory, supported media attestations, key audit, vendor receipts**.
4. Kiểm tra **secondary copies và backup status**; phân loại fully vs partial.
5. Nếu fail/partial, **dừng, isolate pending records, mở exception**.
6. Đối chiếu kết quả với manifest/approval và ký xác nhận theo thẩm quyền.

### Giai đoạn F — Đóng hồ sơ lưu giữ

1. Phát hành **disposition/transfer certificate** có scope chính xác.
2. Cập nhật evidence ledger: archived, held, disposed, partially complete hoặc exception.
3. Bảo vệ **minimal audit metadata**, giữ theo lịch retention riêng.
4. Thu hồi **temporary accesses, links, service credentials và testing artifacts**.
5. Ghi những **known residual copies, expiry dates, vendor pending items**.
6. Bàn giao dashboard/report cho Records/Legal/Security assurance.
7. Rà soát lessons learned về **capture scope, data minimization, backups và key management**.

## 24. Workflow trạng thái và các điểm dừng bắt buộc

### 24.1. State machine

~~~mermaid
stateDiagram-v2
    [*] --> Registered
    Registered --> Preserved
    Preserved --> InAnalysis
    InAnalysis --> RetentionReview
    RetentionReview --> Held: valid hold
    Held --> RetentionReview: authorized release/review
    RetentionReview --> Archived: retain/archive
    Archived --> RetentionReview: next review
    RetentionReview --> DispositionPending: eligible + proposed
    DispositionPending --> RetentionReview: approval denied/expired
    DispositionPending --> Executing: approved + precheck pass
    Executing --> PartiallyComplete: exceptions or pending copies
    Executing --> VerifiedComplete: all scoped checks pass
    PartiallyComplete --> Executing: authorized remediation
    PartiallyComplete --> RetentionReview: new hold/changed scope
    VerifiedComplete --> ClosedRecord: certificate and audit
    ClosedRecord --> [*]
~~~

**State machine không cho phép** nhảy thẳng từ **case closed** sang **VerifiedComplete**. Phải qua retention/hold review, approval, execution và verification.

### 24.2. Invariants

Một số quy tắc không được vi phạm:

- **Held ⇒ no destructive disposition trong scope**.
- **Unknown hold ⇒ chưa eligible**.
- **Approval scope ⇒ execution scope phải là tập con hoặc bằng**, không vượt.
- **Execution success ≠ verification success**.
- **Unresolved copies ⇒ không fully complete**.
- **Archive transfer ⇒ phải có receipt và integrity check**.
- **Raw evidence đã disposed ⇒ không còn được dùng như artifact đang lưu**, chỉ tham chiếu metadata theo policy.
- **Case reopen ⇒ kiểm tra retention/dependencies**, không tự tái tạo dữ liệu.

### 24.3. Concurrency và race condition

Hai automation có thể cạnh tranh: một job tự xóa object lúc hết TTL và một investigator tạo legal hold cùng thời điểm. Giải pháp thiết kế là **central hold/retention authority, atomic/transactional policy gate nếu nền tảng hỗ trợ, lock/lease ở disposition workflow và audit log**. Không dựa vào email thông báo đơn lẻ để bảo đảm job tự động không chạy.

### 24.4. Điều kiện automation thất bại

Nếu retention engine không truy cập được hold registry, hoặc registry trả lỗi/timeouts, workflow cần **fail safely** theo chính sách bảo toàn: tạm dừng destructive action và escalation. Không diễn giải response rỗng thành “không có hold”.

## 25. Automation và policy-as-code: chỉ tự động hóa sau khi có quyết định

Automation có ích khi evidence nhiều, nhưng destructive operations phải có **clear authority, narrow scope, idempotence và verification**. Chỉ nên tự động hóa những bước kiểm tra/chuẩn hóa có rủi ro thấp trước; hủy cuối cùng theo quy định.

### 25.1. Pseudocode kiểm tra eligibility (không phải lệnh xóa)

~~~text
function evaluateDisposition(evidence, policy, holdRegistry):
    require evidence.id and evidence.manifestRef
    require evidence.custodian and evidence.storageLocations

    if holdRegistry.status != "available_and_verified":
        return BLOCK("HOLD_REGISTRY_UNAVAILABLE")
    if evidence.hasActiveOrPendingHold:
        return BLOCK("ACTIVE_OR_PENDING_HOLD")
    if evidence.crossCaseDependenciesNotResolved:
        return BLOCK("CROSS_CASE_DEPENDENCY")
    if not policy.retentionExpiredFor(evidence, timezoneRules):
        return RETAIN("RETENTION_NOT_EXPIRED")
    if not evidence.copyInventoryCompleteEnoughForApproval:
        return BLOCK("COPY_INVENTORY_INCOMPLETE")
    if not evidence.approvalValidForExactManifest:
        return BLOCK("APPROVAL_MISSING_OR_SCOPE_MISMATCH")
    if not evidence.dispositionMethodSupportedForStorage:
        return BLOCK("METHOD_NOT_SUPPORTED")
    return ELIGIBLE_FOR_EXECUTION_REVIEW

No deletion is performed by this function.
~~~

### 25.2. Workflow phải ghi phiên bản policy

Ví dụ một decision:

~~~json
{
  "decision_id": "DISP-REVIEW-LAB-012",
  "evidence_id": "EVID-LAB-012",
  "reviewed_at_utc": "2026-11-28T12:00:00Z",
  "retention_policy_version": "demo-policy-v2",
  "hold_registry_check": "verified",
  "hold_result": "no_active_hold_in_reviewed_scope",
  "case_dependency_check": "pending_review",
  "copy_inventory_state": "partial",
  "decision": "BLOCKED",
  "reasons": [
    "CROSS_CASE_DEPENDENCY_REVIEW_REQUIRED",
    "COPY_INVENTORY_INCOMPLETE"
  ],
  "destructive_action_executed": false
}
~~~

Đây là **fixture mô phỏng**, không phải quyết định thực tế cho case ngoài lab.

### 25.3. Kiểm soát jobs tự xóa theo TTL

Một job auto-delete nên:

- Có **policy owner, source of truth và current hold registry**.
- Chỉ thao tác với object **đã được phép**, dùng manifest chính xác.
- Có **dry-run mode** và log candidate count/total bytes.
- Có **approver/checkpoint** theo mức risk.
- Kiểm tra again ngay trước execution.
- Báo **execution result + failed objects + pending backups**.
- Không ghi nhãn full completion nếu verification chưa đạt.

### 25.4. Thay đổi retention policy

Nếu policy mới kéo dài hoặc rút ngắn thời hạn:

1. Review ảnh hưởng với Legal/Records/Privacy.
2. Không thay silent trên dữ liệu có active hold.
3. Lưu **policy version/effective date và affected evidence IDs**.
4. Có migration/exception plan cho storage lock không điều chỉnh được.
5. Test **retention trigger và timezone calculations** bằng fixtures.
6. Ghi thông tin nào đã disposed hợp lệ dưới policy cũ nếu có; không bịa dữ liệu đã mất.

## 26. Các chỉ số vận hành cho kết thúc vòng đời

Một dashboard tốt giúp giảm **quá hạn retention, tồn đọng hold và thất thoát bằng chứng** mà không tạo động cơ hủy nhanh bằng mọi giá.

### 26.1. Các KPI/SLI có ý nghĩa

| Chỉ số | Cách diễn giải | Cạm bẫy |
| --- | --- | --- |
| **Evidence inventory completeness** | % artifacts có owner, location và class rõ | “Unknown copies” bị bỏ khỏi denominator |
| **Retention classification coverage** | % evidence có policy/trigger/version hợp lệ | Assign default TTL vô căn cứ |
| **Hold compliance** | % hold-scoped artifacts được preserve/acknowledged | Chỉ đếm email đã gửi |
| **Archive integrity verification pass rate** | % archives trong test scope khớp manifest và đọc được | Chỉ hash mà không restore |
| **Access recertification completion** | % cases đã review privileged/shared access | Config revoke nhưng effective role vẫn mở |
| **Eligible disposition backlog** | Số artifacts đủ điều kiện nhưng chưa được xử lý | Không phân biệt held và pending approval |
| **Disposition execution success** | % actions thực hiện theo approved scope | API success không chứng minh all copies |
| **Verified completion rate** | % requests xác minh đủ phạm vi đã duyệt | Gộp partial/pending vào complete |
| **Pending copy/backup expiry age** | Tuổi của residual copies có owner và due date | Gọi scheduled expiry là destroyed |
| **Vendor attestation latency** | Thời gian nhận xác nhận từ vendor | SLA quá nhanh khuyến khích xác nhận thiếu scope |
| **Integrity exceptions** | Số hash/restore mismatches theo risk | Tự sửa manifest che lỗi |
| **PII minimization incidents** | Lỗi tạo thêm bản sao/dữ liệu nhạy cảm ngoài scope | Không phát hiện uploads vào ticket/chat |

### 26.2. Định nghĩa tỷ lệ hoàn tất

\[
\text{Verified disposition rate} =
\frac{\text{requests with all approved scoped checks verified}}
{\text{eligible disposition requests reviewed}} \times 100\%
\]

Khi reporting, tách **held, ineligible, approved, executed, partially verified, fully verified**. Một artifact có immutable backup còn 6 tháng không nên được gán là “fully destroyed” chỉ vì active object đã xóa.

### 26.3. Dashboard ví dụ (dữ liệu giả)

| Tình trạng | Số requests | Hành động |
| --- | ---: | --- |
| Retain/archive còn hạn | 48 | Integrity và access review định kỳ |
| Active/pending hold | 7 | Preservation controls và hold review |
| Eligible, chờ approval | 9 | Records/Legal review |
| Approved, chưa execution | 4 | Kiểm tra copy manifest và scheduling |
| Executed, pending backup/vendor | 5 | Theo dõi partial completion |
| Fully verified + certificate | 22 | Đóng record theo retention riêng |

Các số là **minh họa**, không cộng gộp thành “đã hủy 95 case”; mỗi hàng phản ánh trạng thái khác nhau.

### 26.4. Không tối ưu KPI bằng cách hủy bừa

Một chỉ số **deletion throughput** cao không có nghĩa chương trình an toàn hơn. Chất lượng phụ thuộc việc **không xóa khi hold, không giữ quá hạn vô căn cứ, không làm mất chain of custody, không tạo copies nhạy cảm và không phát hành chứng nhận sai**.

## 27. Privacy, data subject rights và nguyên tắc tối thiểu

Forensic evidence có thể chứa dữ liệu nhạy cảm liên quan nhân viên, khách hàng hoặc đối tác. Quản trị vòng đời cần cân bằng **nghĩa vụ bảo toàn** và **data minimization**, không giữ vô hạn mặc định.

### 27.1. Tối thiểu hóa ngay từ khâu thu thập

Một full PCAP chứa payload HTTP plaintext có thể giữ nhiều thông tin hơn mục tiêu incident yêu cầu. Trong điều tra có quyền, nên xác định:

- Có cần **full packet bytes** hay chỉ flow metadata/pcap filter?
- Có thể ghi **request ID, route template, status, byte counts** thay raw body không?
- Khi nào được tạo derivatives đã redacted/anonymized?
- Raw evidence nào cần preserve nguyên trạng để bảo toàn integrity, và quyền xem nó là gì?
- Có cách chuyển các báo cáo sang aggregated forms sau case không?

**Không sửa raw evidence đã có** để “che PII”; tạo bản sanitized derivative với lineage, giữ/disposing bản gốc đúng policy.

### 27.2. Confidentiality của custody/disposition ledger

Evidence ID kết hợp **ngày, site, username, IP, DNS domain và ticket title** có thể làm lộ thông tin điều tra. Bảng metadata cần **access class, retention và audit** riêng; không phải cứ không có PCAP bytes là có thể public.

### 27.3. Anonymization không đơn giản là bỏ username

Một mạng nội bộ với IP/port/time chính xác có thể được re-identify bằng NAT/IdP logs khác. **Pseudonymization** và **irreversible anonymization** là hai mục tiêu khác nhau; khi đánh giá còn dữ liệu cá nhân hay không, cần xem khả năng liên kết lại **theo bối cảnh và nguồn phụ trợ**.

### 27.4. Giữ có mục đích và review định kỳ

Với data còn được giữ theo hold/retention:

- Giới hạn **purpose và access**.
- Rà **retention deadline và hold validity**.
- Ghi **secondary use** nếu được phép.
- Dùng de-identified summaries khi cung cấp cho nhóm không cần raw.
- Thực hiện data subject requests theo **Privacy/Legal process**, có lý do quyết định trong từng scope.

### 27.5. Không lấy “security” làm lý do giữ mọi log vĩnh viễn

Một hệ thống lưu tất cả PCAP, logs và session identifiers không hạn định tạo **khối dữ liệu nhạy cảm lớn**, làm tăng tác động nếu vault bị compromise. Cần phân biệt **dữ liệu phục vụ incident cụ thể** với **telemetry vận hành định kỳ**, áp retention purpose/category rõ ràng và tiêu hủy có kiểm chứng.

## 28. Công cụ và bước kiểm tra read-only trên evidence được phép

Khi cần review một artifact thật, ưu tiên **read-only inventory và integrity checks**, không thực thi hủy. Các lệnh sau dành cho **Windows PowerShell** hoặc file lab thuộc quyền quản trị; chúng **không thực hiện delete, overwrite, change ACL hay thay retention policy**.

### 28.1. Xem metadata cơ bản

~~~powershell
# Trên file lab bạn sở hữu; chỉ đọc metadata.
$path = '.\evidence-lab.pcapng'
Get-Item -LiteralPath $path |
  Select-Object Name, Length, CreationTimeUtc, LastWriteTimeUtc
~~~

**Lưu ý:** filesystem CreationTime/LastWriteTime có thể thay khi copy/move và không chứng minh thời điểm packet được capture. Chúng chỉ là **metadata của file ở vị trí hiện tại**.

### 28.2. Tính SHA-256 để đối chiếu manifest

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\evidence-lab.pcapng'
~~~

Chạy trên **artifact có quyền đọc**, không đọc file ngoài scope. Digest phải được so với **trusted manifest được lập từ thời điểm thu hoặc transfer có kiểm chứng**; một digest mới tự nó không xác nhận file là bản gốc.

### 28.3. Đối chiếu từ hai vị trí mà không thay file

~~~powershell
$original = Get-FileHash -Algorithm SHA256 -LiteralPath '.\evidence-lab.pcapng'
$archiveCopy = Get-FileHash -Algorithm SHA256 -LiteralPath '.\archive-copy-lab.pcapng'

[PSCustomObject]@{
  SourceHash = $original.Hash
  ArchiveHash = $archiveCopy.Hash
  HashesMatch = ($original.Hash -eq $archiveCopy.Hash)
}
~~~

Nếu hash khác, không tự kết luận ai đã sửa trái phép: có thể **file corruption, encoding/format transformation, sai source path hoặc copy không đầy đủ**. Giữ cả hai và điều tra lineage.

### 28.4. Kiểm tra metadata có timestamp UTC/retention trigger

~~~powershell
# Các ngày là ví dụ; không tính thời hạn pháp lý từ dữ liệu dưới đây.
$exampleTrigger = [DateTimeOffset]::Parse(
  '2026-11-28T09:00:00+07:00',
  [System.Globalization.CultureInfo]::InvariantCulture
)
$exampleTrigger.ToUniversalTime().ToString('o')
~~~

Timezone/trigger từ policy phải được xác minh trước khi tính expiry. **Một mốc ngày đã parse đúng không đồng nghĩa artifact đủ điều kiện hủy**.

### 28.5. Kiểm tra archive metadata qua control plane

Với cloud/object storage, chỉ sử dụng **read-only inventory/list versions/retention/hold** theo quyền; câu lệnh và API khác nhau theo provider. Ghi **bucket/object/version IDs**, tránh xuất object URLs chứa signed tokens ra ticket. Không đưa ví dụ delete/purge/force-unlock vào bài vì dễ gây mất evidence.

### 28.6. Xem custody log và dấu vết truy cập

Kiểm tra:

- Có ai download/restore evidence kể từ lần review cuối?
- Có **new copy/export** nào chưa được đưa vào inventory?
- KMS/key policy có thay đổi ảnh hưởng khả năng restore?
- Hold registry có thay đổi sau khi retention candidate được tạo?
- Vendor/backup lifecycle có thực sự báo hoàn thành hay chỉ scheduled?

Một file hash khớp vẫn có thể có **quyền truy cập quá rộng** hoặc đang được lưu tại sai region. Integrity là một phần của review, không phải review toàn bộ.

## 29. Case study 1 — Incident đóng, legal hold tới trước lịch xóa

### 29.1. Bối cảnh giả định

Incident **INC-LAB-A** đã đóng ngày 01/08. Một tập PCAP được đặt lịch disposition ngày 01/12 theo quy định nội bộ minh họa. Ngày 25/11, bộ phận Legal gửi thông báo preservation hold cho một tranh chấp có liên quan đến cùng host/network interval.

### 29.2. Timeline

| Ngày giả định | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| 01/08 | Case investigation closed | Không có nghĩa được hủy |
| 10/11 | Retention job tạo candidate disposition | Chưa được thực thi |
| 25/11 | Authorized legal hold nhận và xác nhận scope | Cần ngừng deletion với artifacts thuộc hold |
| 26/11 | Vault/backup policy review | Kiểm tra thực tế hold đã được áp |
| 01/12 | Candidate disposal date cũ | **Không hủy** phần đang hold |
| Khi Legal release về sau | Hold release có thẩm quyền | Chạy lại retention/disposition review |

### 29.3. Phương án đúng

1. Gắn **hold ID, issuer, scope, effective date** với PCAP và derivatives liên quan.
2. Dừng **scheduled deletion job** cho đúng object versions và backed copies theo khả năng service.
3. Xác nhận **retention lock/hold effective**, không chỉ sửa trường trong Excel/ticket.
4. Ghi acknowledgment của custodians và vendors trong scope.
5. Duy trì **integrity và access review** trong suốt hold.
6. Sau release, kiểm tra cả **other holds/retention rules** trước khi disposition.

### 29.4. Anti-pattern

“Ticket đóng và auto-delete lịch 01/12 vẫn cứ chạy, vì hold đến muộn.” Sai: một chỉ thị bảo toàn có thẩm quyền đến **trước thao tác** có thể ngăn disposition. Không giả định rule cũ tiếp tục hợp lệ.

**Bài học:** trạng thái case và lịch TTL không thay thế **hold authority + pre-execution gate**.

## 30. Case study 2 — Xóa file gốc nhưng cloud versioning và backup còn

### 30.1. Bối cảnh

Một tổ chức giữ **network-forensics.pcapng** trong object storage có versioning và có backup cross-region. Đội Storage được phép xóa bản active sau retention review. API trả success; dashboard đánh dấu “hủy sạch 100%”.

### 30.2. Bằng chứng sau thao tác

| Nơi | Kết quả | Trạng thái đúng |
| --- | --- | --- |
| Primary active object | Không còn truy xuất qua key thông thường | **Active copy removed** |
| Previous object version | Vẫn tồn tại theo versioning | **Not disposed** nếu nằm trong scope |
| Cross-region replica | Đang chờ lifecycle/sync | **Pending verification** |
| Immutable backup | Hết hạn sau một chu kỳ đã biết | **Retained until scheduled expiry** |
| Analyst CSV extract | Có trong ticket, chưa inventory | **Discovery/action required** |

### 30.3. Cách khắc phục

1. Dừng tuyên bố **fully destroyed**.
2. Đối chiếu approval với **object version IDs**, không chỉ filename.
3. Review cloud versioning, replica và backup policies.
4. Tìm **derived exports** trong forensic tickets/working areas thuộc scope.
5. Không tự phá immutable backup; lập **exception/pending expiry** theo policy.
6. Ghi **partial certificate** hoặc execution record đúng thực tế.
7. Cập nhật verified completion khi toàn bộ phạm vi đủ điều kiện đã được xác nhận.

### 30.4. Bài học

**Delete API success ≠ all copies destroyed**. Cơ chế cloud replication/versioning và backup phải nằm trong evidence copy inventory.

## 31. Case study 3 — Cryptographic erase làm mất cả evidence chưa hết hạn

### 31.1. Bối cảnh

Archive có một **key-encryption key** dùng chung để bảo vệ các data keys của nhiều case. Một nhóm muốn CE một PCAP hết hạn bằng cách hủy shared key; trong cùng hệ còn nhiều artifacts đang theo legal hold.

### 31.2. Sai lầm nguy hiểm

~~~text
KEK-ARCHIVE-SHARED
  +-- DEK for EVID-A (eligible for disposition)
  +-- DEK for EVID-B (active legal hold)
  +-- DEK for EVID-C (retention active)

Destroying the shared KEK may make B and C inaccessible.
~~~

### 31.3. Phương án an toàn

1. Xây **key dependency graph** cho evidence objects.
2. Xác định có **per-object exclusive DEK** hay không.
3. Kiểm tra **wrapped copies, backups, key escrow, plaintext exports**.
4. Đánh giá CE eligibility với **KMS/security owner và Legal/Records**.
5. Nếu key scope không phù hợp, chọn **supported alternative disposal process**.
6. Test phương pháp bằng **synthetic evidence objects** trước khi áp thật.
7. Không tự chứng nhận crypto erase dựa trên thao tác rotate/disable key.

### 31.4. Bài học

**CE chỉ có ý nghĩa khi key scope và toàn bộ đường khôi phục đã được hiểu**. Hủy nhầm shared key có thể phá cả bằng chứng phải lưu giữ.

## 32. Case study 4 — Archive đủ hash nhưng không thể restore phân tích

### 32.1. Bối cảnh giả định

Forensics team chuyển một raw packet capture và file analysis derivative vào archive. Hash so đúng. Sau hai năm, một case được reopen; restore file thành công nhưng công cụ phân tích không giải mã được một vendor-specific capture encapsulation, plugin/metadata đã không được lưu.

### 32.2. Vì sao hash PASS chưa đủ?

- Hash chứng minh **bytes của file được giữ**, không chứng minh tooling còn đọc được.
- Có thể thiếu **sensor interface mapping, capture metadata hoặc parser version**.
- Vendor plugin/license/tool có thể không còn khả dụng.
- Derived reports có thể tham chiếu external object IDs đã hết hạn.
- Encryption keys có thể đã mất dù archive ciphertext còn nguyên.

### 32.3. Biện pháp

1. Xác minh raw hash và custody, không sửa file để “làm cho parser hiểu”.
2. Kiểm tra **format header, tool/version, decoder/plugin requirements** đã được inventory chưa.
3. Liên hệ platform/forensic tool owner theo quyền để tìm supported reader.
4. Nếu được phép, tạo **converted derivative mới** từ raw, giữ raw/hash và transformation log.
5. Rà lại chương trình archive để có **scheduled restore+readability tests**.
6. Ghi limitation cho case mới nếu không thể phân tích artifact.

### 32.4. Bài học

**Archival quality = bit integrity + custody + retrievability + interpretability**. Hash khớp mới là một phần.

## 33. Case study 5 — Vendor đã đóng ticket nhưng chưa xác nhận bản sao

### 33.1. Tình huống

Một MSSP nhận raw IDS export và PCAP theo hợp đồng để hỗ trợ điều tra. Sau khi case đóng, nội bộ yêu cầu xóa các bản copy đã giao. MSSP trả “support ticket closed” nhưng không trả lời về backup/subprocessor copies.

### 33.2. Điều cần yêu cầu

- **Evidence IDs và exact scope** MSSP đã nhận.
- Confirmation active copies **đã xóa theo phương pháp gì**.
- Trạng thái **backup/DR/replicas** theo hợp đồng.
- Chính sách của **subprocessors** liên quan nếu có.
- Hold và retention obligations của vendor.
- Attestation time, signatory/authorized account và exceptions.

### 33.3. Kết quả đúng

Nếu chỉ ticket closed:

~~~text
Vendor support case: CLOSED
Active copy deletion attestation: MISSING
Backup expiry attestation: MISSING
Evidence disposition status: PENDING VENDOR VERIFICATION
Owner: vendor-management + evidence-custodian
Next action: contractual evidence and escalation
~~~

Không tuyên bố full completion hoặc tự yêu cầu xóa bằng mọi cách ngoài hợp đồng.

### 33.4. Bài học

**Support case closure khác evidence disposition closure**. Cần vendor attestation có phạm vi, giới hạn và trách nhiệm.

## 34. Case study 6 — Một PCAP được tham chiếu bởi hai vụ điều tra

### 34.1. Bối cảnh

Raw **EVID-2026-120** ghi lưu lượng từ vùng mạng VPN và đã được dùng trong incident **A**, vừa kết thúc. Trong quá trình review disposition, analyst phát hiện cùng capture được đăng ký làm source cho incident **B** liên quan tới một thiết bị chưa xử lý xong.

### 34.2. Bẫy

Nếu đánh dấu “A closed → EVID-2026-120 delete”, incident B có thể mất chứng cứ gốc, dẫn đến analysis không thể tái lập. Nếu team copy raw sang B mà không ghi custody/lineage, lại xuất hiện bản sao có retention/hold không rõ.

### 34.3. Quy trình đúng

1. Ghi **multi-case reference** trên inventory.
2. Kiểm tra B có **active hold, open investigation, independent retention trigger** không.
3. Xác định custodian chịu trách nhiệm **sở hữu chính** và quyền truy cập của B.
4. Nếu cần copy, tạo **authorized derivative/replica có hash + custody**, không phân phối tùy tiện.
5. Đánh dấu disposition của A **blocked by B dependency** nếu cần, hoặc chuyển ownership có receipt.
6. Khi B đóng, chạy lại toàn bộ retention/hold review.

### 34.4. Bài học

**Evidence lifecycle thường kéo dài hơn một incident**. Có thể đóng case A mà không được đóng vòng đời dữ liệu của artifact dùng chung.

## 35. Những nhầm lẫn thường gặp về kết thúc lưu giữ bằng chứng

1. **“Đóng incident ticket nghĩa có thể xóa PCAP.”** Case closure khác retention expiry và legal hold review.
2. **“Một người trong SOC có quyền xóa file nên cũng có thẩm quyền hủy.”** Khả năng kỹ thuật không thay approval.
3. **“Legal hold không áp cho derivatives.”** Phạm vi hold có thể bao gồm reports, exports và bản sao dẫn xuất.
4. **“Legal hold cứ tồn tại mãi, không cần review.”** Hold cần owner, scope và release/review process.
5. **“Hold release nghĩa được xóa ngay.”** Cần review các retention rules và holds khác.
6. **“Có ticket yêu cầu xóa nghĩa tất cả điều kiện đã đủ.”** Phải xác minh retention/hold/case dependencies.
7. **“Một retention TTL áp cho mọi evidence.”** Loại record, mục đích và luật/hợp đồng khác nhau.
8. **“Retention đếm từ ngày thu thập ở mọi nơi.”** Trigger có thể là case closure hoặc mốc khác theo policy.
9. **“Giữ càng lâu càng an toàn.”** Retention quá mức làm tăng diện dữ liệu nhạy cảm có thể bị lộ.
10. **“Xóa càng sớm càng tốt dù còn tranh chấp.”** Hủy khi có preservation obligation có thể gây mất chứng cứ.
11. **“PCAP mã hóa TLS hoàn toàn không nhạy cảm.”** IP/port/timing/DNS/TLS metadata và nội dung plaintext khác vẫn có thể nhạy cảm.
12. **“Không cần inventory derivatives.”** CSV, screenshots, extracted files có thể giữ lại dữ liệu gốc.
13. **“Một file chỉ thuộc một case.”** Cross-case dependencies có thể yêu cầu giữ tiếp.
14. **“Gửi cho vendor xong không cần theo dõi copy đó.”** Phải quản lý contract/copies/disposition attestations.
15. **“Cloud DeleteObject thành công = mọi physical bytes biến mất.”** Replicas, versions, snapshots và lifecycle khác nhau.
16. **“Delete marker đồng nghĩa previous object versions đã hủy.”** Versioned store có thể giữ dữ liệu cũ.
17. **“Backup có thể hủy ngay một file riêng trong mọi sản phẩm.”** Granularity/immutability có thể không cho phép.
18. **“Immutable/WORM không bao giờ ảnh hưởng kế hoạch xóa.”** Retention lock có thể là blocker hợp lệ.
19. **“Một backup chưa tới expiry vẫn được báo là fully destroyed.”** Phải ghi pending/scheduled expiry.
20. **“Ghi đè một file trên SSD đảm bảo mọi cell cũ bị xóa.”** Wear leveling/overprovisioning làm giả định thiếu chắc chắn.
21. **“Ổ đĩa không mount được chắc dữ liệu đã bị hủy.”** Failed media vẫn cần sanitization/destruction theo SOP.
22. **“Crypto erase = rotate key.”** Rotation không nhất thiết làm key cũ không dùng được.
23. **“Xóa shared KMS key là cách hủy một file.”** Có thể làm mất evidence khác cần giữ.
24. **“Xóa wrapped key ở một vị trí đủ chứng minh CE.”** Có thể còn recovery/backup key.
25. **“CE vault cũng xóa được CSV đã xuất plaintext.”** Các bản sao ngoài scope phải xử lý riêng.
26. **“Hash SHA-256 chứng minh người dùng đã làm hành vi trong PCAP.”** Hash chỉ kiểm tra bytes/integrity.
27. **“Hash khớp chứng minh archive đọc được.”** Thiếu decoder/keys/metadata vẫn có thể không restore usable.
28. **“Tạo hash mới sau lỗi có thể giải quyết mismatch.”** Cần điều tra nguyên nhân, giữ baseline gốc.
29. **“Một restore thành công là mọi archive luôn đọc được.”** Test coverage và chu kỳ phù hợp.
30. **“Revoke role analyst nghĩa evidence đã disposal.”** Access control khác storage lifecycle.
31. **“Từ chối quyền đọc là verification hủy dữ liệu.”** Access denied có thể do ACL, object vẫn còn.
32. **“Approval tuần trước luôn hợp lệ hôm nay.”** Hold/copy/retention có thể đổi.
33. **“Có thể chạy wildcard delete rộng rồi kiểm tra lại.”** Phải chọn exact approved scope trước.
34. **“Automation không đọc được hold registry thì cứ coi không có hold.”** Phải fail safely.
35. **“Execution success đồng nghĩa verification success.”** Phải xác minh copies, versions và attestations.
36. **“Vendor nói ticket closed nghĩa dữ liệu đã hủy.”** Support workflow khác destruction attestation.
37. **“Certificate nói all copies mà không liệt kê scope là đủ.”** Cần phạm vi, phương pháp, kết quả và limitations.
38. **“Destruction certificate không cần retention riêng.”** Nó cũng là record cần policy.
39. **“Sau hủy không còn cần lưu audit metadata nào.”** Có thể phải giữ receipt/approval tối thiểu.
40. **“Hồ sơ kết thúc phải chứa nguyên raw secrets cho đầy đủ.”** Reference IDs và hạn chế dữ liệu là lựa chọn an toàn hơn.
41. **“Object copy trong chat/email luôn có thể thu hồi tuyệt đối.”** Nền tảng và bên nhận có thể có giới hạn.
42. **“Xóa file khỏi laptop analyst là đủ.”** Còn exports, backups, snapshots, cloud và ticket attachments.
43. **“Một IP hoặc domain metadata không phải dữ liệu cá nhân.”** Có thể liên kết tới người dùng khi ghép sources.
44. **“Pseudonymization giống anonymization.”** Dữ liệu có thể bị re-identify bằng auxiliary records.
45. **“Không biết copy ở đâu có thể ghi ‘đã hủy hết’.”** Phải ghi inventory gap và residual risk.
46. **“Case reopen có thể khôi phục raw evidence đã xóa hợp lệ.”** Không thể bảo đảm phục hồi dữ liệu đã mất.
47. **“Mọi hồ sơ archive giữ nguyên file là đủ.”** Cần format readability, metadata, keys và custody.
48. **“Một số KPI xóa cao chứng minh data governance tốt.”** Phải đo compliance, verification và privacy.
49. **“Storage administrator phải có toàn quyền quyết định.”** Phải có Records/Legal/evidence ownership.
50. **“Một external disclosure là quyền xóa dữ liệu bên nhận.”** Bên nhận có thể có retention obligations riêng.

## 36. Lab offline: quyết định retention/hold mà không xóa gì

Lab sử dụng **các records giả**. Người học chỉ đọc dữ liệu và ra quyết định; **không chạy bất kỳ destructive command nào**, không cần kết nối cloud hoặc hệ thống thật.

### 36.1. Bảng evidence giả

Ngày đánh giá giả định: **2026-11-28 UTC**.

| Evidence ID | Case | Retention rule giả định | Hold | Dependencies/copies | Kết luận sơ bộ |
| --- | --- | --- | --- | --- | --- |
| **LAB-A** | Case A đã đóng | Review due 2026-11-20 | Active hold H-1 | PCAP raw + archive | **Giữ** vì hold |
| **LAB-B** | Case B đã đóng | Review due 2026-11-20 | None confirmed | Active object + immutable backup tới 2027 | **Chưa fully disposed**; backup review |
| **LAB-C** | Case C đã đóng | Review due 2026-11-25 | None confirmed | Khóa mã hóa dùng chung D | **Chưa đủ điều kiện CE bằng shared key** |
| **LAB-D** | Case D đang mở | Review due 2026-11-28 | None confirmed | Raw + two extracts | **Giữ** vì investigation open |
| **LAB-E** | Case E đã đóng | Review due 2026-11-10 | Hold unknown | Vendor copy không có confirmation | **Dừng** vì hold/copy unknown |
| **LAB-F** | Case F đã đóng | Review due 2026-11-01 | None confirmed | Exact copy inventory, approval pending | **Chờ approval**, không tự execution |

**Quan trọng:** “Review due” không có nghĩa retention đã hết, trừ khi chính sách đã xác nhận eligibility. Bảng cố ý chứa điều kiện còn thiếu.

### 36.2. Bước 1 — Đặt decision state

Với mỗi row, ghi:

~~~text
Evidence ID:
Case status:
Retention policy and trigger verified?  YES/NO/UNKNOWN
Retention expired?                     YES/NO/UNKNOWN
Hold status:                           NONE/ACTIVE/PENDING/UNKNOWN
Other case references:                 ...
Known primary/derivative/backup copies:
Method eligible for all relevant stores?
Approval state:
Disposition status:
Blocked reason:
Next reviewer/owner/time:
~~~

### 36.3. Bước 2 — Giải thích từng blocker

- **LAB-A:** Active hold có hiệu lực; review scope và bảo toàn, không xóa.
- **LAB-B:** Active copy có thể được disposition nếu đủ điều kiện, nhưng backup còn immutable tới kỳ expiry; không báo full completion.
- **LAB-C:** Shared key có thể liên quan D; không tự xóa key để CE riêng C.
- **LAB-D:** Case còn mở; retention candidate không vượt điều kiện điều tra.
- **LAB-E:** Không có kết quả hold rõ và vendor chưa attest; **fail closed** với destructive action.
- **LAB-F:** Policy due chưa đủ; cần xác minh policy eligibility và nhận approval.

### 36.4. Bước 3 — Tạo manifest/receipt giả

~~~json
{
  "exercise_id": "LAB-DISPOSITION-012",
  "review_time_utc": "2026-11-28T12:00:00Z",
  "evidence_id": "LAB-B",
  "decision": "PARTIAL_COMPLETION_NOT_YET_PERMITTED",
  "primary_copy": "eligible_only_after_approval",
  "backup_copy": {
    "status": "immutable_until_expiry",
    "expiry_window": "2027 - verify actual policy"
  },
  "legal_hold": "none_confirmed_for_current_review",
  "approved_destructive_action": false,
  "disposition_executed": false,
  "attestation": "NOT_APPLICABLE_YET",
  "next_action": "records_review_and_backup_owner_confirmation"
}
~~~

Không được đổi các trường **disposition_executed** và **attestation** sang true khi lab chỉ đánh giá điều kiện.

### 36.5. Bước 4 — Kiểm tra tính toàn vẹn của dữ liệu demo

Tự tạo hai **file văn bản giả vô hại** trong thư mục lab riêng của người học (không dùng log thật). Chạy **Get-FileHash** ở mục 28 để so digest khi copy. Sau đó trả lời:

1. Hash khớp có chứng minh file nguồn là bằng chứng hợp lệ không?
2. Có cần giữ **source/tool/collection metadata** khi archive không?
3. Nếu file được chuyển định dạng, hash của derivative có cần giống raw không?
4. Nếu backup còn và bản active không còn, có được cấp full disposal certificate không?

**Gợi ý:** hash khớp chứng minh **bytes được sao chép tương ứng**; format conversion tạo artifact khác cần **lineage và hash riêng**; backup pending không được ghi full destruction.

### 36.6. Điều kiện đạt lab

Người học:

- Không đề xuất xóa khi **active/pending/unknown hold**.
- Không đồng nhất **review due với authorized deletion**.
- Ghi đúng **raw, derivative, backup và vendor copies**.
- Xác định được shared key risk.
- Viết **partial/pending status** khi chưa có full verification.
- Giữ evidence refs và không dùng credential/PCAP thật.

## 37. Ma trận kiểm thử kiểm soát retention, archive và disposition

Ma trận dùng **fixtures, mock storage hoặc môi trường staging được cấp phép**, không hủy dữ liệu thật. Một bài kiểm thử đạt khi có **input, chính sách mong đợi, observed decision, evidence và người review**.

| Test ID | Điều kiện kiểm thử | Kết quả bắt buộc |
| --- | --- | --- |
| **T01 – Case closed, retention active** | Case đóng nhưng chưa hết hạn | **RETAIN**, không disposition |
| **T02 – Active legal hold** | Hợp lệ và nằm trong scope | Destructive action **blocked** |
| **T03 – Pending hold** | Registry chưa xác nhận | **BLOCK**, không suy “none” |
| **T04 – Hold registry timeout** | Không gọi được source of truth | **Fail safely** và escalation |
| **T05 – Hold release** | Có release được ủy quyền | Chạy lại retention/other-holds review |
| **T06 – Hold scope partial** | Một số files bị hold | Chỉ phân loại đúng scope, không hủy nhầm |
| **T07 – Cross-case reference** | Artifact dùng trong case đang mở | Retain/transfer ownership theo policy |
| **T08 – Retention trigger ambiguity** | Collection và closure dates khác | Không tự chọn trigger để tính expiry |
| **T09 – Timezone/DST** | Trigger ở vùng có DST | Tính theo rules của policy, không dùng offset tùy ý |
| **T10 – Approval missing** | Hết hạn nhưng chưa có approver | Chưa execution |
| **T11 – Approval expired** | Hold/copy state đổi sau ký | Revalidate/reapprove |
| **T12 – Manifest mismatch** | Planned objects khác approved set | Dừng, không mở rộng xóa |
| **T13 – Raw/derivative lineage** | Có filtered PCAP và CSV extract | Tất cả trong inventory |
| **T14 – Working copy xuất hiện** | Analyst download mới | Trạng thái copy được cập nhật và xử lý |
| **T15 – Hash mismatch khi archive** | Source/destination digest khác | Quarantine/investigate, không update trusted baseline bừa |
| **T16 – Archive restore** | Bytes hash đúng nhưng không decode | Not fully archival-ready; format remediation |
| **T17 – Missing decryption key** | Encrypted archive không đọc được | Preservation/restore exception |
| **T18 – Shared KMS key** | Key dùng cho evidence held | CE của một item không được phá key shared |
| **T19 – Key backup exists** | DEK có bản recoverable | CE chưa verified |
| **T20 – Cloud object versioning** | Delete marker, old version còn | Partial/not complete |
| **T21 – Cross-region replica** | Replica còn chờ sync/expiry | Pending verification |
| **T22 – Immutable backup** | Lock chưa hết | Không force-unlock; exception/scheduled expiry |
| **T23 – Backup expiry** | Catalog báo expired và job completed | Xác minh theo supported audit process |
| **T24 – Vendor ticket closed** | Không có deletion attestation | Pending vendor verification |
| **T25 – Vendor attestation limited** | Chỉ active copy, không backup | Báo partial scope |
| **T26 – Physical media transfer** | USB gửi nhà cung cấp xử lý | Custody receipt + media inventory + destruction certificate |
| **T27 – Failed SSD** | Media không đọc được | Không tự gọi sanitized; dùng approved failed-media process |
| **T28 – Unauthorized requestor** | Người yêu cầu không có quyền | Reject/escalate, không thực thi |
| **T29 – Access revoke** | Analyst mất quyền, object vẫn tồn tại | Đánh dấu access closure, **không** destruction |
| **T30 – Post-disposal archive record** | Destruction certificate cần retention riêng | Giữ metadata tối thiểu theo policy |
| **T31 – Privacy request vs hold** | Data subject yêu cầu xóa, hold active | Escalate Privacy/Legal, không hủy trái hold |
| **T32 – Case reopened** | Incident mới cần artifact đã archived | Restore có approval, tạo copy ID và custody |
| **T33 – Case reopened after lawful disposal** | Chỉ còn destruction receipt | Không bịa raw evidence, ghi limitation |
| **T34 – Scheduled deletion and concurrent hold** | Hold tới ngay trước execution | Pre-execution check dừng deletion |
| **T35 – Verification failure** | API success nhưng object version còn | Không ký fully disposed |
| **T36 – Certificate overclaim** | “All copies destroyed” nhưng backup còn | Review rejects certificate wording |
| **T37 – External copy undiscovered** | Ticket attachment chứa raw PCAP | Inventory gap surfaced, incident/data handling follow-up |
| **T38 – Key rotation** | Rotate encryption key | Không tự gán CE completed |
| **T39 – Sanitized derivative** | Mask PII trong report | Raw/source retention xử lý riêng, không coi raw đã xóa |
| **T40 – Dashboard calculation** | 5 partial + 20 fully verified | Verified count = **20**, không phải 25 |

### 37.1. Mẫu ghi kết quả kiểm thử

~~~text
Test ID:
Fixture / non-production environment:
Policy version / effective date:
Expected gate outcome:
Actual gate outcome:
Hold/retention/cross-case conditions:
Evidence/copy scope:
Executed destructive action? NO (for this learning lab)
Observed verification / simulated receipt:
Pass/fail:
Known limitations and reviewer:
~~~

### 37.2. Positive và negative control

**Positive control:** Một artifact giả đã đủ eligibility và approval phù hợp nên được workflow mô phỏng đánh dấu **eligible for execution review**, không bị block sai vì policy parser lỗi.

**Negative controls:** hold active, shared key, unknown vendor copy hoặc manifest mismatch phải **block**. Nếu hệ thống chỉ biết block mọi thứ, nó không chứng minh đúng quản trị disposition; ngược lại, nếu cho phép tất cả, nó không bảo vệ bằng chứng.

### 37.3. Test không chứng minh đã hủy ngoài lab

Một dry-run report hoặc kết quả 40/40 tests không chứng minh production objects đã được xử lý. Real-world completion vẫn cần **approval, exact scope, execution audit, verification và certificate**.

## 38. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Case đóng có được xóa ngay?

Incident ngày 10/01 đã đóng, PCAP còn trong vault. Một kỹ sư muốn giải phóng storage và nói “ticket đã resolved”.

**Gợi ý:** không đủ. Kiểm tra **retention policy/trigger, case references, holds, backups, approval và copy inventory** trước khi disposition.

### Bài 2 — Hai retention triggers

PCAP được thu ngày 01/04, case đóng ngày 01/06; policy của hai loại hồ sơ khác nhau dùng **collection date** và **case closure date**. Có thể dùng cùng một ngày expiry không?

**Gợi ý:** không mặc định. Mỗi loại evidence phải dùng **policy/trigger đúng**, time zone/calendar rules và hold precedence.

### Bài 3 — Hold đến sau approval

Disposition được phê duyệt hôm thứ Hai. Thứ Ba Legal ban hành hold có hiệu lực trước giờ chạy job thứ Tư. Kỹ sư có thể chạy theo approval cũ không?

**Gợi ý:** không. **Pre-execution hold check** phải dừng destructive action và review lại scope/approval.

### Bài 4 — Hủy object trong versioned cloud storage

API delete object trả 204/success, nhưng có ba previous versions còn trong object list.

**Gợi ý:** chỉ có thể xác nhận **logical active deletion** theo service semantics. Previous versions vẫn cần retention/hold/disposition review và verification.

### Bài 5 — Backup immutable

PCAP hết hạn theo policy sau case, nhưng snapshot immutable vẫn còn tới chu kỳ năm sau.

**Gợi ý:** không cố force-delete trái lock. Ghi **backup retained until scheduled expiry**, owner, date và exception/risk; không ký fully destroyed.

### Bài 6 — Hash trước và sau archive

Hash raw PCAP trước chuyển và hash file lấy về từ archive khớp, nhưng decoder không đọc được một dạng metadata proprietary.

**Gợi ý:** bit integrity đạt, **usability/readability chưa đạt**. Giữ raw, điều tra format/tool/plugin, tạo derivative với lineage nếu được phép.

### Bài 7 — CE trên shared key

Một KMS KEK dùng cho 50 evidence objects, trong đó 10 đang có hold. Để xóa một PCAP hết hạn, một kỹ sư đề xuất destroy KEK.

**Gợi ý:** sai: có thể làm 49 artifacts khác không còn đọc được. Phải kiểm tra **key hierarchy, DEK scope, backup/escrow** và dùng phương pháp phù hợp.

### Bài 8 — Copy ngoài hệ thống

Evidence vault đã xóa file đúng quy trình. Một analyst còn export CSV chứa identifiers trên workstation và share trong ticket.

**Gợi ý:** full disposition chưa được chứng minh. Bổ sung **derivative/copied artifacts inventory**, quyền owner và phương án xử lý/attestation theo chính sách.

### Bài 9 — Case B còn mở

Một PCAP là parent artifact cho reports của case A và B. A đã hết retention; B vẫn đang điều tra.

**Gợi ý:** không tự hủy PCAP. Kiểm tra **multi-case linkage**, retain/transfer custodian, bảo toàn integrity và review lại khi B kết thúc.

### Bài 10 — Vendor ticket

MSSP báo support request đã đóng nhưng không có báo cáo về backup/subprocessors. Có đủ để cấp chứng nhận không?

**Gợi ý:** chưa. Cần **scoped attestation** về phần đã disposition, pending/retained copies và limitation.

### Bài 11 — Revoke access nhưng chưa hủy

Một analyst đã bị gỡ quyền read vào archive, song object còn tồn tại hợp lệ trong legal hold.

**Gợi ý:** đây là **access closure**, không phải data disposal. Preservation vẫn đúng nếu hold/owner và audit controls được giữ.

### Bài 12 — Yêu cầu xóa PII

Một người yêu cầu xóa log VPN chứa thông tin của họ; log đang là evidence trong cuộc điều tra có hold hợp lệ.

**Gợi ý:** phối hợp **Privacy/Legal/Records** để đánh giá quyền/nghĩa vụ và scope, hạn chế truy cập, lưu hồ sơ quyết định; không tự hứa xóa ngay hay giữ vĩnh viễn.

### Bài 13 — Xác nhận phương pháp trên SSD

Kỹ sư ghi đè file một lần rồi gọi đó là “irrecoverable physical erase” trên SSD.

**Gợi ý:** không đủ do **wear leveling, snapshots và controller behavior**. Cần supported sanitize/CE/destruction SOP phù hợp media và evidence.

### Bài 14 — Partial certificate

Primary object và working copy đã xóa theo approval, vendor copy và DR backup chưa confirmed. Hãy viết kết luận.

**Gợi ý:** “**Primary/working copies completed within scope; vendor/DR pending verification**”, có owner/due date. Không dùng “all evidence permanently destroyed”.

### Bài 15 — Đánh giá dashboard

Từ 40 yêu cầu eligible, 25 hoàn tất đầy đủ, 10 bị hold, 5 pending vendor. Phát biểu “100% disposition completed” có chính xác không?

**Gợi ý:** không. Cần làm rõ 10 bị hold có còn trong denominator “eligible” hay không; nếu đã gọi eligible nhưng lại held thì **định nghĩa population có vấn đề**. Trong dữ liệu nêu, chỉ **25 fully verified**; phần khác phải phân loại lại theo trạng thái chính xác.

### Bài 16 — Thiết kế quy trình cho tổ chức nhiều vùng mạng

Tổ chức có PCAP tại sensor on-prem, flow logs cloud, EDR exports, SIEM alerts, sandbox extracts, ticket attachments, vendor copies và DR backups. Thiết kế workflow kết thúc vòng đời:

1. Chuẩn hóa **evidence IDs, owner, source/time/provenance và hashes**.
2. Xây **raw/derivative/copy lineage**.
3. Map **retention triggers và legal holds** theo đúng source.
4. Thiết lập **pre-execution gate và approval separation**.
5. Có **archive/restore/integrity tests**.
6. Chọn method theo **physical/cloud/encrypted/versioned storage**.
7. Xử lý **backup/immutable/vendored copies** riêng.
8. Cấp **partial/full attestation** chỉ khi phù hợp evidence.
9. Thu hồi **access/shared links** và bảo vệ hồ sơ disposition.
10. Gắn **exceptions, owners, reviews và data-minimization controls**.

**Gợi ý:** dùng evidence lifecycle state machine ở mục 24, không xây workflow chỉ bằng một trường \`status=deleted\`.

## 39. Checklist đóng vòng đời lưu trữ bằng chứng

Checklist dùng để review **đúng từng evidence set/case** trước khi ký; một ô “không áp dụng” phải có lý do và owner, không dùng để bỏ kiểm tra.

### 39.1. Ownership, mục đích và căn cứ

| Câu hỏi | Evidence cần có |
| --- | --- |
| Evidence set có **case ID, evidence ID và custodian**? | Register/manifest |
| Case thật sự đã đóng phần điều tra và findings chính? | Case owner sign-off |
| Có case khác còn dùng raw/derivative artifact? | Cross-case reference search |
| Có phân loại **raw, copies, derivatives, reports**? | Lineage inventory |
| Có mục đích và căn cứ lưu giữ cho từng record class? | Retention policy mapping |
| Retention trigger đã xác định và đúng timezone? | Policy version/trigger evidence |
| Hết hạn retention theo rule áp dụng? | Expiry calculation/reviewer |
| Đã kiểm tra active/pending/disputed holds? | Authorized hold registry check |
| Legal hold release được ký đúng thẩm quyền nếu có? | Release reference |
| Có yêu cầu privacy/regulator/contract đang mở? | Records/Legal/Privacy review |

### 39.2. Storage, archive và copy inventory

| Câu hỏi | Evidence cần có |
| --- | --- |
| Biết primary vault và all known physical/cloud locations? | Storage/copy manifest |
| Có workstation/download/temporary extracts? | Endpoint/case workspace inventory |
| Có SIEM/EDR/NDR/sandbox exports? | Console export ledger |
| Có ticket/chat/email attachments hoặc external shares? | Sharing/copy inventory |
| Có cloud object versions/replicas/cross-region copies? | Storage inventory và policy |
| Có immutable/WORM retention lock? | Storage retention metadata |
| Có backups/snapshots/tape/DR copies? | Backup catalog và expiry |
| Có vendor/subprocessor copies? | Contract/copy acknowledgment |
| Có encryption key dependencies hoặc plaintext cache? | KMS/architecture review |
| Nếu archive, metadata và decoder có đầy đủ? | Format manifest, parsing/restore test |
| Hash/integrity đã đối chiếu ở các transfer points? | Trusted digest ledger |
| Custody transfer có bên gửi/nhận và thời gian UTC? | Transfer receipt |

### 39.3. Approval và execution

| Câu hỏi | Evidence cần có |
| --- | --- |
| Decision là retain, archive, transfer hay dispose? | Approved decision |
| Method phù hợp với HDD/SSD/cloud/SaaS/backup? | SOP/media assessment |
| Object/version IDs đúng và không vượt scope? | Exact approved manifest |
| Approval còn hiệu lực ngay trước execution? | Pre-execution gate |
| Có người thực thi và reviewer đúng quyền? | Roles/change ticket |
| Hold registry sẵn sàng và không phát sinh blocker? | Real-time verified check |
| Có phương án cho immutable backup/vendor pending? | Exception/expiry plan |
| Không có destructive action outside approval? | Execution audit |
| Restore/integrity checks của archive/transfer đã đạt? | Verification report |
| Nếu dùng CE, key scope và backups đã kiểm tra? | KMS/crypto erase assessment |

### 39.4. Verification và closure

| Câu hỏi | Evidence cần có |
| --- | --- |
| Execution result đã đối chiếu approved manifest? | Result per evidence/version |
| Primary objects đã được verify trong exact scope? | Control-plane/storage evidence |
| Backups/versions/replicas đã xử lý hoặc ghi pending? | Copy state reconciliation |
| Vendor attestation đúng phạm vi đã nhận? | Signed/authorized response |
| Có unresolved exception/partial completion? | Exception register |
| Destruction/transfer certificate ghi giới hạn chính xác? | Reviewed certificate |
| Có owner/due date cho every pending residual copy? | Follow-up tickets |
| Analyst/temp grants/shared links đã revoke thích hợp? | Effective access audit |
| Disposition metadata không chứa raw secrets/PII ngoài mục đích? | Redaction review |
| Custody/change/access logs đủ cho audit? | Final ledger |
| Certificate có retention class riêng? | Records schedule |
| Evidence record cuối đã được versioned/approved? | Closure sign-off |

### 39.5. Điều kiện bàn giao cho prime/case owner trong workflow thật

Một bản **closure report** tối thiểu phải phân biệt:

~~~text
Case ID / disposition request ID:
Evidence inventory version:
Case closure confirmation:
Retain/hold/release review refs:
Policy version and retention trigger:
Approved disposition scope and method:
Archive transfers and integrity/restore results:
Secure disposal execution references:
Vendor/backups/immutable copy statuses:
Verification conclusion: FULL / PARTIAL / BLOCKED / RETAINED
Open exceptions + owners + next review:
Certificate/ledger references and approvers:
Personal-data treatment and authorized distribution:
~~~

Không cần điền raw credentials, session cookies, file contents hoặc sensitive packet payload vào biểu mẫu này. Các artifacts thô chỉ được mở qua **evidence vault/authorization**.

## 40. Tổng kết

**Kết thúc vòng đời lưu trữ bằng chứng** không phải là thao tác xóa một file PCAP sau khi đội SOC đóng ticket. Đó là **quy trình kiểm soát toàn bộ trạng thái của dữ liệu điều tra số**, từ thu thập/đăng ký, bảo toàn bản gốc, phân tích và tạo dẫn xuất, xác định **retention và legal hold**, chuyển **archive/transfer** khi cần, cho tới **disposition được phê duyệt, thực thi, xác minh và lưu hồ sơ chứng nhận**.

Trong hệ thống **SECURITY_NETWORK_SECURITY**, bằng chứng có thể trải rộng từ **packet captures, TLS/DNS metadata, NetFlow/IPFIX, firewall/NAT/VPN/IDS/IPS logs, SIEM exports, endpoint/cloud audit, timeline và báo cáo ứng phó sự cố**. Vì có thể chứa topology, user identifiers, session data, secrets hoặc dữ liệu ứng dụng, cần **đăng ký nguồn gốc, SHA-256/integrity checks, chain of custody, phân quyền, mã hóa, data minimization, copy inventory và retention schedule**. Bản raw và các derivatives/bản sao phải được theo dõi xuyên suốt nhiều môi trường.

Trước một thao tác hủy, phải xác nhận **đã hết nghĩa vụ lưu giữ, không còn hold hoặc case dependency, approval còn hiệu lực, method phù hợp với môi trường lưu trữ và phạm vi bản sao đã rõ**. **Delete API success, key rotation, hủy một bản DEK, đóng vendor ticket hoặc gỡ quyền đọc** không tự tương đương hủy mọi bản sao. Đặc biệt, **cloud versioning, immutable backups, replicas, shared encryption keys, snapshot và vendor copies** có thể khiến một yêu cầu chỉ đạt **partial completion** và phải tiếp tục theo dõi.

Một cuộc điều tra có trách nhiệm phải kết thúc với **bằng chứng về quyết định**, không chỉ tuyên bố. Chuẩn cuối cùng là một **evidence ledger + retention/hold review + approved disposition manifest + execution and verification records + certificate có giới hạn chính xác**, cùng owner cho mọi ngoại lệ. Nhờ vậy tổ chức vừa **không làm mất bằng chứng còn nghĩa vụ bảo toàn**, vừa **không giữ dữ liệu nhạy cảm quá lâu không có căn cứ**, và có thể giải thích đầy đủ cho người kiểm toán, chủ hệ thống và các bên có thẩm quyền về trạng thái thực tế của từng artifact.
