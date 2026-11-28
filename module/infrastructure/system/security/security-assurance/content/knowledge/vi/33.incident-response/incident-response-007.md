# Evidence preservation: Bảo toàn chứng cứ trong ứng phó sự cố

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **evidence preservation** là gì và vai trò của nó trong **incident response** và **security assurance**.
2. Phân biệt dữ liệu nguồn, bản sao thu thập, bản làm việc, kết quả phân tích, giả thuyết và kết luận điều tra.
3. Lựa chọn thời điểm, thứ tự và phương pháp thu thập phù hợp với mức độ biến động của chứng cứ, nhu cầu containment và các giới hạn quyền hạn.
4. Thiết lập **chain of custody**, ghi nhận provenance, bảo vệ tính toàn vẹn và kiểm tra bằng chứng qua các lần chuyển giao.
5. Áp dụng nguyên tắc bảo toàn cho endpoint, server, IAM, cloud, Kubernetes, ứng dụng, mạng và dịch vụ bên thứ ba.
6. Thiết kế phép thử và bằng chứng audit chứng minh quy trình bảo toàn hoạt động liên tục, đồng thời ghi rõ khoảng trống và rủi ro tồn dư.

## 1. Evidence preservation và vấn đề cần giải quyết

**Evidence preservation** là quá trình nhận diện, thu thập, ghi nhận, lưu giữ và bảo vệ dữ liệu có thể liên quan tới một sự cố sao cho người điều tra có thể kiểm chứng **nguồn gốc, tính toàn vẹn, thời gian, phạm vi và lịch sử xử lý** của dữ liệu đó.

Trong một sự cố, dữ liệu rất dễ bị thay đổi hoặc biến mất: tiến trình kết thúc, RAM bị ghi đè, container được tạo lại, log rotation xảy ra, tài khoản bị thu hồi, máy ảo bị hủy hoặc retention của dịch vụ SaaS hết hạn. Nếu không bảo toàn kịp thời, đội ứng phó có thể khôi phục dịch vụ nhưng không còn đủ dữ liệu để giải thích điều gì đã xảy ra và những tài sản nào bị ảnh hưởng.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, evidence preservation hỗ trợ cách đánh giá bảo mật có bằng chứng, từ phân tích rủi ro, security controls đến kiểm thử, audit, phản ứng và khắc phục. Một tuyên bố như “không thấy truy xuất dữ liệu trái phép” chỉ đáng tin khi phạm vi log, cách thu thập, thời điểm, độ đầy đủ và những điểm mù đã được ghi rõ.

### 1.1. Chứng cứ phục vụ ba mục tiêu

- **Điều tra kỹ thuật:** tái dựng chuỗi sự kiện, xác định actor, quyền, hành động, tài sản và tác động.
- **Điều hành ứng phó:** lựa chọn containment, eradication, recovery và kiểm tra sau khắc phục bằng thông tin đủ tin cậy.
- **Assurance và audit:** để reviewer độc lập đánh giá kết luận, hiệu lực của controls, điểm yếu quy trình và việc xử lý findings.

Quy tắc bảo toàn chứng cứ cho mục đích pháp lý có thể khác giữa các khu vực pháp lý và thủ tục. Khi vụ việc liên quan tố tụng, nghĩa vụ thông báo hoặc yêu cầu của cơ quan chức năng, cần phối hợp với người phụ trách pháp lý và chuyên gia pháp chứng có thẩm quyền.

### 1.2. Khái niệm quan trọng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Nguồn/original** | Vật hoặc hệ thống nơi dữ liệu đang tồn tại hoặc được phát sinh. | Đĩa vật lý, API audit, node, dịch vụ lưu log. |
| **Potential evidence** | Dữ liệu có thể liên quan nhưng chưa xác định được giá trị điều tra. | Raw event về một lần thay đổi IAM. |
| **Acquired copy** | Bản sao được thu bằng phương pháp có ghi nhận. | Disk image, export JSONL, memory dump. |
| **Working copy** | Bản dùng để phân tích, lọc, giải nén, normalize hoặc redaction. | Timeline đã tương quan từ nhiều file log. |
| **Provenance** | Thông tin cho biết dữ liệu bắt nguồn từ đâu và qua những bước nào. | Account, cluster, collector, API export, phiên bản parser. |
| **Chain of custody** | Hồ sơ lưu dấu ai giữ, truy cập, chuyển giao hoặc thay đổi cách bảo quản chứng cứ. | Sổ bàn giao và audit truy cập kho lưu. |
| **Integrity verification** | Kiểm tra bytes chứng cứ được lưu giữ không đổi ngoài các biến đổi có ghi nhận. | Hash SHA-256 trước và sau chuyển giao. |
| **Finding** | Nhận định có căn cứ từ các hiện vật. | Principal P tạo role binding B lúc 10:03 UTC. |
| **Hypothesis** | Lời giải thích cần thêm chứng cứ xác nhận hoặc bác bỏ. | Principal P có thể bị chiếm quyền. |

**Không đồng nhất sự kiện, chứng cứ và kết luận.** Một audit record “principal P đọc object X” chưa chứng minh người sở hữu P trực tiếp thực hiện; một flow log “có kết nối egress” chưa xác nhận những bytes nào đã bị chuyển ra ngoài.

## 2. Nguyên tắc bảo toàn chứng cứ

| Nguyên tắc | Câu hỏi assurance | Cách bảo đảm |
|---|---|---|
| **Authenticity/provenance** | Hiện vật đến từ hệ thống nào, bằng phương pháp và danh tính nào? | Nguồn, asset ID, người thu, API/export, thời gian, tool/version. |
| **Integrity** | Nội dung có bị thay đổi sau acquisition không? | Hash, kiểm soát ghi, versioning/immutable storage khi phù hợp, kiểm tra lại. |
| **Completeness** | Phạm vi thời gian, tài sản và dữ liệu bắt buộc có đầy đủ không? | Collection manifest, kiểm tra record count, pagination, lỗi và gap report. |
| **Traceability** | Ai đã làm gì với chứng cứ, lúc nào và vì sao? | Custody record, command log, audit truy cập, change/ticket. |
| **Confidentiality** | Dữ liệu cá nhân, credentials và thông tin nhạy cảm có bị lộ không? | RBAC, mã hóa, hạn chế export, bản báo cáo đã loại dữ liệu không cần. |
| **Availability** | Chứng cứ có thể truy xuất và khôi phục khi cần không? | Retention, backup, diễn tập restore, kiểm tra khóa mã hóa. |
| **Reproducibility** | Người khác có thể đánh giá lại phân tích không? | Bản raw, hash, phiên bản công cụ, query, rules và timeline. |

Không phải hiện vật nào cũng có thể được thu theo cách không thay đổi nguồn. **Live acquisition** (thu thập khi hệ thống đang chạy) có thể làm thay đổi RAM, atime, cache, process state hoặc log. Mục tiêu là giảm tác động và **ghi lại tác động đã biết**, thay vì tuyên bố không có tác động.

### 2.1. Hash có tác dụng gì và không có tác dụng gì?

Hash mật mã như **SHA-256** giúp so sánh nội dung bytes của các bản sao. Nếu hai bản có cùng digest, có bằng chứng mạnh rằng nội dung của chúng giống nhau theo thuật toán được dùng.

Tuy nhiên, hash **không tự chứng minh** dữ liệu đã đúng từ nguồn: attacker có thể sửa log trước khi bạn thu; collector có thể loại mất record; export có thể thiếu trang dữ liệu; người có đặc quyền có thể thay cả file lẫn manifest hash trong cùng một kho. Vì vậy, hash phải đi cùng nguồn đáng tin, mô tả phương pháp, record count, quyền truy cập, audit và chain of custody.

Ví dụ trên Linux, với bản sao đã lưu trong kho được ủy quyền:

~~~bash
sha256sum acquired-audit.jsonl > acquired-audit.jsonl.sha256
sha256sum -c acquired-audit.jsonl.sha256
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
Get-FileHash -LiteralPath '.\acquired-audit.jsonl' -Algorithm SHA256
~~~

Ghi thêm thời điểm, tên file, kích thước, nơi lưu, danh tính người thực hiện và kết quả. Nếu giải nén, đổi encoding, sửa newline hoặc normalize JSON thì bytes sẽ khác; artifact dẫn xuất phải có **hash riêng** và liên kết về bản gốc. Không dùng ETag của cloud object như SHA-256 mặc định: ETag có thể có cách tính khác, nhất là khi tải lên nhiều phần.

## 3. Ưu tiên theo độ biến động và mức rủi ro

**Order of volatility** là nguyên tắc ưu tiên dữ liệu dễ mất, nhưng không phải thứ tự cứng áp dụng cho mọi sự cố. Containment khẩn cấp có thể cần được thực hiện trước khi thu đủ RAM nếu tiếp tục chờ khiến dữ liệu khách hàng bị lấy cắp hoặc hệ thống bị phá hủy.

| Chứng cứ | Rủi ro mất | Hướng xử lý |
|---|---|---|
| RAM, process tree, kết nối đang mở, session/runtime state. | Rất cao khi shutdown, restart, terminate process. | Cân nhắc thu sớm bằng công cụ có thẩm quyền nếu an toàn và khả thi. |
| Trạng thái pod/container, ephemeral storage, stdout/stderr chưa chuyển đi. | Cao khi pod thay thế, node restart hoặc log rotate. | Snapshot trạng thái và lấy từ collector tập trung sớm. |
| Kubernetes Events, DNS cache, bảng kết nối và metadata ngắn hạn. | Cao theo TTL, retention hoặc hoạt động runtime. | Xác định nguồn, thời điểm, khả năng export. |
| OS/application logs tại host. | Có thể mất do rotation, overwrite, malware. | Sao chép/raw export theo phương pháp được chấp thuận. |
| Disk image, filesystem, database snapshot. | Có thể bị ghi/sửa; consistency khác nhau. | Snapshot/image, ghi phương pháp, độ nhất quán, hash và restore check. |
| Cloud/IAM/SaaS audit tập trung. | Phụ thuộc cấu hình retention, account, region và API. | Đặt preservation/hold nếu cần, export raw và kiểm tra pagination. |
| CI/CD, config, IAM/RBAC hiện tại. | State thay đổi nhanh; trạng thái hiện tại có thể che lịch sử. | Ghi snapshot hiện tại cùng audit thay đổi và version/digest. |

### 3.1. Quyết định giữa containment và thu thập

~~~mermaid
flowchart TD
    A["Phát hiện nghi vấn sự cố"] --> B["Xác định mức tác động đang diễn ra"]
    B --> C{"Có cần ngăn thiệt hại ngay?"}
    C -->|Có| D["Containment theo thẩm quyền"]
    C -->|Chưa| E["Thu chứng cứ volatile ưu tiên"]
    D --> F["Ghi lại chứng cứ có thể mất và dữ liệu còn lại"]
    E --> G["Containment có kiểm soát"]
    G --> F
    F --> H["Kiểm tra integrity, lưu custody và điều tra"]
~~~

Các lựa chọn containment có mức tác động khác nhau. Chặn một kết nối egress có thể giữ máy chạy nhưng thay đổi traffic; thu hồi key làm mất khả năng tiếp tục quan sát phiên dùng key; tắt VM có thể làm mất RAM và ephemeral disk; xóa pod có thể xóa trạng thái runtime cùng log cục bộ.

Một **decision record** tối thiểu gồm: sự cố, nguy cơ đang diễn ra, mục đích hành động, các lựa chọn, người quyết định, thời gian UTC, hệ thống bị ảnh hưởng, chứng cứ dự kiến mất và nguồn thay thế.

Không trì hoãn biện pháp bảo vệ khẩn cấp vô hạn chỉ để có một bản sao pháp chứng hoàn hảo. Ngược lại, tránh những thao tác sửa chữa, reboot, cleanup hoặc xóa tài nguyên tùy tiện nếu có thể thu chứng cứ quan trọng mà không làm tăng rủi ro đáng kể.

## 4. Chuẩn bị năng lực preservation trước sự cố

Trong incident response, chuẩn bị tốt quyết định khả năng có bằng chứng sau sự cố. Một chương trình tối thiểu cần:

1. **Inventory:** asset, owner, môi trường, cloud account, tenant, cluster, nguồn logging và vị trí lưu.
2. **Evidence source map:** event nào được tạo, độ đầy đủ, retention, quyền export, cách snapshot, nguồn dự phòng.
3. **Playbook theo loại sự cố:** identity compromise, malware, data leakage, ransomware, cloud privilege escalation, container compromise.
4. **Quyền và phê duyệt:** ai được thu, xem, chuyển, bảo toàn lâu dài, xóa, yêu cầu vendor và đặt hold.
5. **Công cụ được xác minh:** phiên bản collector, disk/memory acquisition, công cụ hash, nơi ghi log thao tác.
6. **Kho bảo toàn:** phân quyền, mã hóa, retention, audit, backup, khả năng chống xóa/sửa khi cần.
7. **Mẫu hồ sơ:** evidence register, chain of custody, acquisition checklist, timeline và findings.
8. **Diễn tập và đánh giá:** trích xuất chứng cứ trước khi hết retention, kiểm tra hash, chuyển giao, restore và bàn giao giữa ca.

### 4.1. Ai chịu trách nhiệm?

| Vai trò | Trách nhiệm |
|---|---|
| **Incident commander / IR lead** | Quyết định mục tiêu điều tra, ưu tiên, containment và điều phối nguồn lực. |
| **Forensic collector / responder** | Thu thập theo quy trình; ghi thời gian, công cụ, trạng thái, lỗi và hash. |
| **Evidence custodian** | Giữ kho, custody record, quyền truy cập, retention và kiểm tra toàn vẹn. |
| **Platform/cloud/asset owner** | Hỗ trợ truy xuất nguồn, snapshot và bối cảnh cấu hình với quyền phù hợp. |
| **Security analyst** | Phân tích bản sao làm việc, nêu finding và độ tin cậy. |
| **Legal/privacy/compliance** | Xác định nghĩa vụ bảo toàn, giới hạn xử lý dữ liệu, legal hold và kết thúc lưu. |
| **Security assurance/audit** | Đánh giá tính truy vết, độ đầy đủ, tính độc lập và hiệu lực quy trình. |

Ở tổ chức nhỏ, một người có thể kiêm nhiệm nhiều vai trò, nhưng vẫn phải có bằng chứng về quyền thực hiện và phê duyệt các hành động quan trọng.

## 5. Quy trình thu thập và bảo toàn từ đầu đến cuối

~~~mermaid
flowchart LR
    I["Identify"] --> S["Scope & prioritize"]
    S --> C["Collect / Acquire"]
    C --> V["Validate & hash"]
    V --> P["Preserve & custody"]
    P --> A["Analyze working copy"]
    A --> R["Report & limitations"]
    R --> L["Retain / release / improve"]
~~~

### Bước 1 — Xác lập scope và câu hỏi điều tra

Lập mã sự cố, mô tả vấn đề, câu hỏi điều tra, khoảng thời gian, asset liên quan, owner, thẩm quyền thu thập và các nguồn cần lấy. Ví dụ: “kiểm tra liệu service account billing-prod có đọc object ngoài phạm vi trong 09:00–11:00 UTC hay không”.

Không giả định mọi nguồn đã được thu; danh sách phải ghi **bắt buộc / ưu tiên / không thể lấy**.

### Bước 2 — Ưu tiên nguồn

Phân loại theo thời hạn tồn tại, giá trị điều tra, rủi ro tiếp tục tấn công, khả năng thu an toàn, chi phí và quyền truy cập. Quyết định lấy memory trước disk hoặc audit log trước network packet cần lý do phù hợp sự cố.

### Bước 3 — Acquisition có kiểm soát

Mỗi acquisition phải có:

- Evidence ID và incident ID.
- Source/asset/tenant/cluster/account, người hoặc service principal thực hiện.
- Loại thu thập: raw export, logical copy, physical image, snapshot, memory acquisition, metadata collection.
- Thời gian bắt đầu/kết thúc; timezone; phạm vi truy vấn chính xác.
- Công cụ/phiên bản, lệnh hoặc API request, filter, pagination, kết quả, error và retry.
- Dung lượng, record count, consistency và các phần bị thiếu.
- Mọi thay đổi lên nguồn do thao tác thu thập gây ra.

**Raw export** cần giữ như đã nhận từ nguồn khi khả thi. Phân tích, lọc trường, redaction, chuyển timezone hoặc normalize phải thực hiện ở bản dẫn xuất.

### Bước 4 — Kiểm tra và bảo toàn

Kiểm tra dữ liệu thu có thể đọc; đúng phạm vi; có record count/manifest; ghi lỗi. Tính hash trên acquired copy, lưu manifest có bảo vệ và chuyển artifact vào kho có quyền tối thiểu. Cân nhắc write-once/immutable storage theo nền tảng và nghĩa vụ retention.

Việc có hash không bảo đảm đầy đủ dữ liệu. Nếu export chỉ lấy trang đầu vì API phân trang, thì hash vẫn đúng cho **bản export thiếu**. Phải kiểm tra completeness riêng.

### Bước 5 — Chain of custody

Ghi nhận mọi lần chuyển giao, truy cập phân tích đáng kể, thay đổi nơi lưu hoặc xử lý bản sao, với thời gian, người giao/nhận, mục đích, hình thức và kết quả integrity check. Sử dụng audit của kho và hệ thống quản lý chứng cứ để tăng khả năng kiểm chứng.

### Bước 6 — Phân tích và báo cáo

Tạo bản làm việc có liên kết đến acquired copy, ghi parser/tool/version, query, filter, phương pháp correlation và mọi artifact dẫn xuất. Trong báo cáo, tách **sự kiện quan sát**, **suy luận**, **giả thuyết chưa xác minh** và **điểm mù dữ liệu**.

### Bước 7 — Lưu giữ, khắc phục và kết thúc

Chốt retention, owner, legal hold nếu có, quyền truy cập và ngày rà soát. Khi kết thúc nhu cầu giữ, áp dụng quy trình release/delete được phê duyệt và lưu audit. Không tự xóa chứng cứ ngay khi hệ thống đã phục hồi.

## 6. Chain of custody và evidence manifest

Một bản ghi custody cần trả lời: **ai đã quản lý artifact nào, khi nào, ở đâu, vì mục đích gì và tình trạng artifact lúc chuyển giao ra sao?**

### 6.1. Manifest minh họa

~~~json
{
  "incident_id": "INC-2026-042",
  "evidence_id": "EV-0007",
  "source": {
    "system": "cloud-audit",
    "account": "production-example",
    "region": "region-1",
    "time_range_utc": "[2026-11-28T09:00:00Z,2026-11-28T11:30:00Z)"
  },
  "acquisition": {
    "method": "approved-api-export",
    "collector_id": "responder-01",
    "tool_version": "exporter-example-v1",
    "started_at": "2026-11-28T11:41:00Z",
    "completed_at": "2026-11-28T11:44:00Z",
    "record_count": 1842,
    "errors": []
  },
  "artifact": {
    "filename": "EV-0007-raw-audit.jsonl",
    "size_bytes": 542381,
    "hash_algorithm": "SHA-256",
    "digest": "<sha256-duoc-tinh-khi-thu-thap>",
    "storage_reference": "evidence-vault/INC-2026-042/EV-0007"
  },
  "custody_events": [
    {
      "at": "2026-11-28T11:45:00Z",
      "from": "responder-01",
      "to": "evidence-custodian",
      "purpose": "secure-preservation",
      "integrity_result": "matched"
    }
  ]
}
~~~

Các định danh và kích thước ở đây là ví dụ. **Digest phải được tính từ artifact thực**, không dùng giá trị trong mẫu. Với manifest có dữ liệu bí mật hoặc định danh người dùng, lưu theo phân loại dữ liệu tương ứng.

### 6.2. Các tình huống cần ghi bổ sung

- **Tệp nén hoặc chuyển định dạng:** lưu hash của bản gốc và bản dẫn xuất, công cụ, tham số, người thực hiện.
- **Đổi môi trường lưu:** lưu nơi cũ/mới, người chuyển, thời gian và kiểm tra integrity trước/sau.
- **Khôi phục backup:** lưu nguồn backup, phiên bản, thời gian restore, hash so khớp và lỗi nếu có.
- **Tiếp nhận từ nhà cung cấp:** giữ ticket, danh tính bên cung cấp, cách chuyển, mô tả phạm vi, định dạng và giới hạn xác nhận của bên cung cấp.
- **Dữ liệu không thể thu:** ghi lý do, thời điểm thất bại, nguyên nhân dự kiến và ảnh hưởng lên kết luận.
- **Làm việc nhiều người:** mọi phân tích dùng bản working copy có ID, không sửa trực tiếp acquired copy.

## 7. Timestamp, timezone và chất lượng timeline

Chứng cứ thường đến từ các đồng hồ khác nhau. Cần giữ giá trị gốc, offset hoặc timezone và ghi mức không chắc chắn nếu đồng hồ nguồn lệch.

| Thời điểm | Nghĩa | Không nên hiểu nhầm |
|---|---|---|
| **event_time** | Khi nguồn ghi nhận hoạt động. | Không đồng nghĩa thời gian ingest hoặc export. |
| **ingested_at** | Khi hệ thống tập trung nhận sự kiện. | Có thể trễ do queue, network, retry. |
| **collected_at** | Khi điều tra viên xuất dữ liệu. | Không thể dùng thay thời điểm xảy ra hành vi. |
| **snapshot_created_at** | Khi nền tảng đánh dấu tạo snapshot. | Không tự bảo đảm tính nhất quán ứng dụng. |
| **file modified/accessed** | Timestamp do filesystem ghi. | Có thể đổi do thao tác đọc/copy, malware hoặc restore. |
| **analysis_time** | Lúc công cụ phân tích xử lý dữ liệu. | Không phải thời điểm tấn công. |

Ví dụ:

~~~text
10:00:00 UTC  Storage audit ghi nhận GetObject
10:03:15 UTC  SIEM nhận audit event
10:04:05 UTC  Rule tạo security alert
10:15:40 UTC  Responder xuất raw audit
~~~

Trong ví dụ, **ingestion latency = 195 giây**, **detection latency = 245 giây** nếu cùng một chuẩn thời gian đáng tin. Thời điểm 10:15:40 là thời gian xuất chứng cứ, không được dùng như thời gian truy cập object. Nếu đồng hồ nguồn sai hoặc chỉ có timestamp client cung cấp, phải ghi **clock skew và độ tin cậy**, tránh sửa mất giá trị gốc.

Khi timeline có khoảng trống, cần xác định log bị tắt, retention hết hạn, collector mất kết nối, parser loại record, nguồn không bao phủ asset hoặc có event bị lọc. Không diễn giải “không có log” thành “không có hành động”.

## 8. Bảo toàn chứng cứ theo từng môi trường

### 8.1. Endpoint và máy chủ

Các nhóm dữ liệu liên quan có thể gồm:

- **Volatile:** RAM, process list/tree, loaded module, socket, session, DNS cache, service/process state.
- **Host logs:** event log, auth log, system journal, EDR telemetry, audit và công cụ giám sát.
- **Filesystem:** disk image, changed files, scheduled tasks, registry/autoruns, systemd/cron, file metadata.
- **Identity/context:** user và group, privilege, logon session, remote administration, credential handling metadata.

Ví dụ lệnh quan sát trên Linux, **chỉ khi có quyền và trong phạm vi được duyệt**:

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ'
uname -a
ps -eo pid,ppid,user,lstart,args
ss -tunap
findmnt
~~~

Trên Windows PowerShell:

~~~powershell
Get-Date -Format o
Get-Process | Select-Object Id,ProcessName,Path,StartTime
Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess
Get-Service | Select-Object Name,Status,StartType
~~~

Những lệnh này cung cấp **trạng thái quan sát tại thời điểm chạy**, không phải bộ bằng chứng forensic đầy đủ. Chúng có thể không hiển thị hết vì thiếu quyền, version OS khác hoặc tiến trình đã kết thúc. Ghi stdout/stderr, thời điểm, quyền chạy và lỗi. **Không chạy công cụ một cách tùy tiện trên máy đang nghi bị xâm nhập** khi việc chạy làm tăng nguy cơ hoặc phá trạng thái cần thu.

Memory dump có thể chứa mật khẩu, token và PII; chỉ thu theo playbook và phân loại dữ liệu nhạy cảm. Disk image/snapshot cần ghi **physical hay logical**, phạm vi ổ/partition, consistency, encryption, công cụ acquisition, write blocker nếu có, hash và kết quả đọc lại. Chụp snapshot không đồng nghĩa thu được RAM.

### 8.2. Cloud và IAM

| Nguồn | Thông tin cần giữ | Bẫy thường gặp |
|---|---|---|
| **Control-plane audit** | Actor, action, target, outcome, request ID, account/project, region và raw event. | Chỉ lấy một region hoặc một account; pagination thiếu. |
| **IAM/SSO** | Đăng nhập, MFA, session, token issuance/revocation metadata, role/policy changes. | Nhầm tên hiển thị với principal ID bất biến. |
| **VM/instance** | Instance ID, image, metadata, disk/snapshot, IAM role, network settings, runtime state khi có thể. | Stop/terminate làm mất RAM/ephemeral storage. |
| **Object storage** | Object/key/version, access audit, bucket policy, ACL, retention/lifecycle. | Chỉ lấy bản hiện tại mà bỏ object version hoặc delete marker. |
| **Cloud network** | Flow logs, firewall, DNS, NAT/proxy, route changes. | Aggregation, sampling, ingest delay; flow log không phải packet capture. |
| **Managed DB** | Query/audit, snapshot, role changes, backup/transaction logs. | Snapshot không tự bảo đảm trạng thái ứng dụng nhất quán. |
| **SaaS** | Admin activities, file sharing/export, sign-in, audit policy, connector health. | Provider có retention ngắn hoặc API giới hạn, cần yêu cầu giữ sớm. |

Khi chụp disk/cloud snapshot, ghi ID, account/region, thời điểm, mã hóa/KMS, principal có quyền truy cập, trạng thái nhất quán, object liên quan và cách restore. Nếu tài nguyên có nhiều volume hoặc DB đang ghi, đánh giá application-consistency; nhiều snapshot tạo gần nhau không mặc nhiên có cùng mốc trạng thái giao dịch.

**Nhà cung cấp cloud lưu một số dữ liệu dưới mô hình shared responsibility.** Tổ chức phải biết audit log nào cần bật, retention nào đang dùng, quyền xóa thuộc principal nào và có đủ phạm vi account/region cho câu hỏi điều tra không.

### 8.3. Kubernetes và container

Container/pod có thể tồn tại ngắn, trong khi desired-state manifest thay đổi liên tục. Cần liên kết **cluster, namespace, pod UID, container ID, node, image digest, service account, RBAC, volume, deployment history**.

Những nguồn cần cân nhắc:

- Kubernetes API audit và admission events.
- PodSpec hiện tại và historical manifest/commit.
- Container stdout/stderr (hiện hành và trước đó nếu còn), log tập trung.
- Node/container runtime, process/network state và metrics theo phạm vi cho phép.
- Kubernetes Events, config changes, RoleBinding/ClusterRoleBinding, ephemeral container và lệnh exec.
- Cloud/network flow, namespace labels, NetworkPolicy, CI/CD artifact và deployment logs.

Ví dụ xuất dữ liệu quan sát theo quyền được ủy quyền:

~~~bash
kubectl --context <context> -n <namespace> get pod <pod> -o json > pod-snapshot.json
kubectl --context <context> -n <namespace> get events -o json > namespace-events.json
kubectl --context <context> -n <namespace> logs <pod> -c <container> --timestamps > container-current.log
kubectl --context <context> -n <namespace> logs <pod> -c <container> --previous --timestamps > container-previous.log
~~~

Các tên trong ngoặc nhọn phải được thay bằng giá trị hợp lệ. Đây là **lệnh minh họa**, chưa phải quy trình pháp chứng hoàn chỉnh. Ghi timestamp, cluster context, danh tính RBAC, kubectl/client/server version và thông báo lỗi. Tùy thời điểm, log trước đó có thể không còn, Kubernetes Events có thể đã hết TTL và pod cũ đã bị xóa. Khi lệnh lấy log trước đó không thành công, ghi **không thu được**, không kết luận container trước đó không hề chạy.

Dữ liệu hiện tại của PodSpec không tự chứng minh cấu hình của pod đã bị xóa trong quá khứ. Cần đối chiếu admission audit, deployment history, image digest, commit và log ở nguồn độc lập.

Hạn chế dùng **kubectl exec** trực tiếp trong container nghi vấn nếu chưa có kế hoạch: nó có thể làm thay đổi trạng thái, kích hoạt xử lý của attacker hoặc khiến log điều tra lẫn với hành vi ban đầu.

### 8.4. Mạng

Nguồn gồm DNS, VPN, proxy, WAF, firewall, IDS/NDR, flow logs và packet capture. Một số điểm cần thận trọng:

- Địa chỉ IP qua NAT/proxy không xác định chắc duy nhất người dùng.
- TLS có thể che payload; một packet capture chỉ có metadata không đủ để kết luận nội dung file đã truyền.
- Flow log thường tổng hợp, có delay hoặc sampling; không dùng sự vắng mặt event làm bằng chứng tuyệt đối không có lưu lượng.
- Packet capture có thể lưu mật khẩu, session hoặc thông tin cá nhân; phải giới hạn thu thập, truy cập và retention.
- Khi correlate với IdP, endpoint và cloud, cần đánh giá clock skew, NAT mapping, request ID và tính liên tục của phiên.

### 8.5. Database và ứng dụng

Thu các event nghiệp vụ cần thiết để trả lời câu hỏi, ví dụ actor nào xuất báo cáo, object nào được đọc, role nào thay đổi, truy vấn nào thành công, dữ liệu nào được cập nhật. Các nguồn hỗ trợ gồm API gateway, application audit, DB audit, backup, change data capture, transaction logs, CI/CD và feature flags.

Phân biệt **request** với **outcome**. HTTP 200 ở gateway không chắc chứa toàn bộ dữ liệu mong đợi; query SELECT chưa chứng minh có exfiltration qua mạng. Cần kết hợp response, lượng dữ liệu, event nghiệp vụ, authorization và network context. Nếu log dùng account pooling, tìm cách liên kết principal thực với connection hoặc request ID.

## 9. Bảo vệ dữ liệu nhạy cảm trong quá trình forensic

Evidence có thể chứa dữ liệu cá nhân, customer data, mã nguồn, nội dung thư, token, secret và dữ liệu tài chính. Mục tiêu bảo toàn không cho phép mở rộng quyền xem vô hạn.

Thiết kế ba khu vực:

1. **Acquisition vault:** giữ raw evidence với quyền hạn chế, mã hóa, retention, audit và quy trình chain of custody.
2. **Analysis workspace:** bản working copy theo quyền tối thiểu, theo dõi tool, query, transformation và liên kết acquisition ID.
3. **Reporting package:** trích dẫn bằng chứng, timeline, kết luận và dữ liệu đã redacted theo nguyên tắc cần biết.

Nếu phát hiện credential trong raw artifact: hạn chế người xem, báo đúng kênh, rotate/revoke theo quy trình containment, ghi timestamp và ảnh hưởng lên hoạt động điều tra; không dán secret vào ticket/chat có quyền rộng.

**Redaction thực hiện trên bản dẫn xuất** trong phạm vi được phép, kèm mô tả trường đã che và rule sử dụng. Không chỉnh trực tiếp acquired copy để “làm sạch” bằng chứng rồi đánh dấu là original.

Legal hold, retention và việc xóa sau vụ việc cần có **thẩm quyền, phạm vi, owner, ngày rà soát và audit**. Khi có yêu cầu bảo toàn hợp lệ, phối hợp pháp lý và quyền riêng tư để xử lý xung đột với lịch xóa dữ liệu thường lệ. Không mặc định cứ có sự cố thì phải giữ mọi dữ liệu mãi mãi.

## 10. Tình huống thực tế: lạm dụng access key trên cloud

**Bối cảnh:** SIEM cảnh báo một access key vừa được tạo cho principal có quyền đọc object storage của hệ thống hóa đơn. Sau đó có nhiều event GetObject. Đội IR chuẩn bị thu hồi key và dừng máy ảo nghi có liên quan.

### 10.1. Câu hỏi cần trả lời

- Ai đã tạo key, theo session nào, quyền hiệu lực ra sao?
- Key được dùng để gọi API nào, đối với object/version nào, có thành công không?
- Dữ liệu có thực sự được truyền khỏi hệ thống không? Nếu có, bằng nguồn nào chứng minh?
- Máy ảo có process đang dùng key không, và thao tác stop sẽ làm mất dữ liệu volatile nào?
- Có dấu hiệu sửa/tắt logging hoặc xóa dấu vết không?

### 10.2. Ưu tiên nguồn và lý do

| Evidence ID | Nguồn | Điều cần lưu | Nguy cơ nếu chậm |
|---|---|---|---|
| EV-01 | IAM/IdP audit | Principal, session, MFA, tạo access key, role policy, request ID. | Retention và thay đổi state. |
| EV-02 | Object access log | Thời điểm, object/version, outcome, actor, request ID, bytes nếu khả dụng. | Delay, hết retention, lọc sai. |
| EV-03 | Runtime VM | RAM/process/socket, metadata key usage theo playbook. | Stop/restart làm mất volatile data. |
| EV-04 | Disk snapshot | Image, config và artifacts liên quan. | Dữ liệu bị sửa/xóa hoặc không nhất quán. |
| EV-05 | Network/proxy | Egress, DNS, NAT context, destination. | Rotation, sampling hoặc thiếu liên kết. |
| EV-06 | SIEM/IR case | Alert raw, rule version, investigation/containment timeline. | Ticket chỉnh sửa, thiếu audit. |
| EV-07 | CI/CD và secret manager | Thay đổi pipeline, deploy, secret access, phiên bản. | Artifact/log retention. |

Nếu truy cập dữ liệu đang tiếp tục, thu hồi key khẩn cấp có thể cần ưu tiên; ghi quyết định và thu các nguồn còn lại. Không giữ credential đang bị lạm dụng chỉ vì chờ hoàn tất forensic.

### 10.3. Timeline có dẫn nguồn

~~~text
09:57:12 UTC  IdP: một session của principal P được tạo    [EV-01]
10:01:06 UTC  IAM: access key K được tạo thành công         [EV-01]
10:02:18 UTC  Storage: GetObject đến object X              [EV-02]
10:02:21 UTC  Egress flow: kết nối từ host H                [EV-05]
10:06:45 UTC  SIEM tạo alert                               [EV-06]
10:11:30 UTC  Responder revoke key K                        [EV-06]
10:14:03 UTC  Snapshot disk host H hoàn tất                 [EV-04]
~~~

**Quan sát trực tiếp:** các event được ghi nhận tại nguồn tương ứng trong thời gian đã kiểm tra.

**Suy luận có điều kiện:** một chuỗi hoạt động đáng nghi xảy ra gần nhau, có thể liên quan cùng credential/host.

**Chưa thể kết luận:** người sở hữu P trực tiếp thực hiện, bytes nào chắc chắn bị đưa ra ngoài, mọi object đã bị đọc hay không, hoặc có hành động ngoài cửa sổ đã thu. Cần đối chiếu request ID, response status, object version, IAM session, NAT/egress, quality/coverage và clock skew.

### 10.4. Cấu trúc evidence package

~~~text
incidents/INC-2026-042/
  scope-and-authority.md
  evidence-register.csv
  timeline-with-sources.md
  acquisition/
    EV-01-idp-iam-audit-raw.jsonl
    EV-02-storage-access-raw.jsonl
    EV-03-runtime-acquisition-metadata.json
    EV-04-snapshot-reference.json
    EV-05-network-flows-raw.jsonl
    EV-06-alert-and-actions.jsonl
    EV-07-cicd-secret-audit.jsonl
  integrity/
    sha256-manifest.txt
    verification-history.csv
  custody/
    transfer-history.csv
    access-audit-references.md
  analysis/
    working-timeline.csv
    queries-and-tools.md
    findings-and-limitations.md
  decisions/
    containment-approval.md
    retention-hold-status.md
    remediation-and-retest.md
~~~

Snapshot có thể là tài nguyên cloud có ID và chính sách riêng chứ không phải file tải xuống; metadata phải liên kết tới snapshot thực và cách truy xuất. Raw artifacts cần nằm trong kho có quyền phù hợp; đây chỉ là sơ đồ tổ chức minh họa.

## 11. Security assurance cho quy trình bảo toàn chứng cứ

Quy trình evidence preservation phải được **thử nghiệm**, có tiêu chí và bằng chứng, thay vì chỉ có chính sách được phê duyệt.

### 11.1. Ma trận claim → test → evidence

| Claim | Phép thử/tiêu chí chấp nhận | Bằng chứng |
|---|---|---|
| **C1: Nguồn chứng cứ trọng yếu được nhận diện.** | Đối chiếu inventory với hệ thống đang vận hành, owner, retention, phương pháp export. | Source coverage report, gap register. |
| **C2: Có thể thu trước khi dữ liệu biến mất.** | Diễn tập thu trong cửa sổ retention thực, kiểm tra lỗi API/pagination/time range. | Export log, record count, timeline, error report. |
| **C3: Bản sao giữ nguyên qua chuyển giao.** | Hash acquisition và hash sau chuyển kho/restore khớp. | SHA-256 manifest, verification record và custody. |
| **C4: Quyền truy cập và xóa được hạn chế.** | Tài khoản không được phép bị từ chối; truy cập hợp lệ có audit. | Policy, access-control test, audit truy cập. |
| **C5: Reviewer tái dựng được cách thu.** | Từ evidence ID tìm được source, tool/version, người, thời gian, command/API, query và giới hạn. | Acquisition manifest, custody log, reviewer signoff. |
| **C6: Có thể khôi phục dữ liệu cần thiết.** | Restore artifact mẫu, đối chiếu hash và khả năng đọc/diễn giải. | Restore log, hash check, retention/backup config. |
| **C7: Quyết định containment có truy vết.** | Diễn tập một tình huống không thể thu hết volatile data; có decision record, gap và hành động tiếp theo. | Incident exercise report, decision log. |
| **C8: Retention/hold được quản trị.** | Diễn tập đặt và gỡ hold trên dữ liệu thử, kiểm tra quyền và audit. | Hold record, approval, release log. |

Kết quả test phải đánh dấu **PASS / FAIL / INCONCLUSIVE / NOT RUN**. Không đánh dấu PASS nếu API export thiếu một trang, hash không khớp, người nhận không thể truy xuất artifact hoặc không có chứng cứ cho thao tác chuyển giao.

### 11.2. Các chỉ số hữu ích

| Chỉ số | Phương pháp | Giới hạn |
|---|---|---|
| **Source coverage** | Nguồn trọng yếu có playbook acquisition đã được thử / tổng nguồn trọng yếu. | Không tự chứng minh thực thi lúc sự cố thật. |
| **Collection success rate** | Số lần acquisition đáp ứng yêu cầu / số lần thử hợp lệ. | Cần nêu rõ “đáp ứng” về scope, time range và errors. |
| **Time to preservation** | Từ trigger/phê duyệt đến khi chứng cứ được đặt vào kho bảo toàn. | Cần tách thời gian phát hiện chậm khỏi acquisition. |
| **Integrity pass rate** | Số artifact kiểm tra hash khớp / tổng artifact được kiểm tra. | Không đo tính xác thực nguồn hoặc completeness. |
| **Custody completeness** | Artifact có đầy đủ trường bắt buộc / số artifact được audit. | Phụ thuộc tiêu chí và tính đại diện mẫu. |
| **Restore success rate** | Bài thử restore qua kiểm tra hash và đọc dữ liệu / tổng bài thử hợp lệ. | Tùy loại artifact, khóa và công cụ đọc. |
| **Unresolved evidence gaps** | Khoảng trống còn mở theo severity, owner và tuổi. | Ít gap được báo không chứng minh hệ thống không có điểm mù. |

Một dashboard “100% artifact có SHA-256” chỉ hỗ trợ kiểm soát integrity ở một giai đoạn; không tự chứng minh tất cả chứng cứ đã đầy đủ và đáng tin.

### 11.3. Diễn tập kiểm chứng end-to-end

Giả lập một pod Kubernetes có kết nối outbound trái baseline và dự kiến bị rolling update trong 15 phút. Đội IR phải:

1. Xác định đúng cluster, namespace, pod UID, container ID, node và source telemetry.
2. Thu PodSpec, log hiện hành, audit liên quan và metadata runtime khả dụng.
3. Ghi lệnh, giờ UTC, người, lỗi và nguồn nào volatile.
4. Hash acquired artifacts, lưu kho, thực hiện chuyển giao và kiểm tra lại hash.
5. Tạo timeline từ log có nguồn và giới hạn rõ.
6. Lập decision record containment và cleanup trong sandbox.
7. Để reviewer khác truy vết evidence ID tới nguồn và phương pháp.

Nếu container đã biến mất và log không còn, phải ghi nhận gap cùng ảnh hưởng đến kết luận; không tự tạo kết quả PASS.

## 12. Sai lầm phổ biến

1. **“Copy được file log là xong.”** Chưa chắc đúng nguồn, phạm vi, thời gian, completeness và custody.
2. **“Hash khớp nghĩa là log hoàn toàn thật.”** Hash chứng minh tính nhất quán bytes sau acquisition, không chứng minh nguồn không bị sửa trước đó.
3. **“SIEM có mọi chứng cứ.”** Có thể thiếu RAM, process, file, network hoặc log bị drop trước ingestion.
4. **“Luôn phải lấy RAM trước containment.”** Cần cân bằng với thiệt hại đang tiếp diễn, safety và quyền quyết định.
5. **“Cloud snapshot chứa toàn bộ trạng thái.”** RAM, ephemeral state, multi-volume consistency và các dịch vụ ngoài snapshot có thể thiếu.
6. **“Thời gian export bằng thời gian tấn công.”** Phải phân biệt event, ingest, collection và analysis time.
7. **“Không thấy log chứng minh không có hành vi.”** Có thể nguồn bị tắt, hết retention, parser lỗi hoặc không bao phủ toàn hệ thống.
8. **“Có thể sửa bản raw để che PII rồi gọi là original.”** Redaction cần tạo bản dẫn xuất và giữ provenance phù hợp.
9. **“Tất cả nhân viên bảo mật nên được đọc mọi evidence.”** Quyền rộng có thể làm rò rỉ secret và giảm độ tin cậy của custody.
10. **“Đã recovery thì xóa chứng cứ ngay.”** Retention/hold và hậu kiểm có thể còn hiệu lực.
11. **“Cloud provider lưu mọi audit mãi mãi.”** Retention, khu vực, quyền export và cấu hình audit khác nhau theo dịch vụ.
12. **“GetObject và egress flow chứng minh toàn bộ dữ liệu bị lấy cắp.”** Cần nối chính xác actor, response, lượng bytes, object, destination và nguồn xác nhận.

## 13. Checklist triển khai Evidence preservation

- [ ] Incident ID, câu hỏi điều tra, scope, thời gian và thẩm quyền thu thập được xác định.
- [ ] Nguồn chứng cứ được lập danh mục kèm retention, owner, mức nhạy cảm và phương pháp thu.
- [ ] Tính biến động và rủi ro containment đã được đánh giá; các quyết định có audit.
- [ ] Acquisition có evidence ID, thời điểm UTC, danh tính, tool/version, command/API, kết quả và lỗi.
- [ ] Lưu acquisition copy và làm việc trên bản dẫn xuất có provenance.
- [ ] Có kiểm tra kích thước, record count, time range, pagination và completeness.
- [ ] Artifact được hash; hash manifest được bảo vệ và kiểm tra sau chuyển giao/restore.
- [ ] Chain of custody liên tục cho các lần chuyển giao/xử lý cần ghi nhận.
- [ ] Kho evidence có RBAC, mã hóa, audit, retention và phương án khôi phục.
- [ ] Timestamp gốc, timezone, clock skew, ingestion lag và giới hạn tương quan được giữ.
- [ ] Có playbook phù hợp cho endpoint, cloud, Kubernetes, network, SaaS và ứng dụng.
- [ ] Secrets và dữ liệu riêng tư được bảo vệ; reporting dùng dữ liệu tối thiểu cần thiết.
- [ ] Kết luận phân biệt sự kiện quan sát, suy luận, giả thuyết và khoảng trống.
- [ ] Findings có owner, hạn khắc phục và cơ chế xác minh lại.
- [ ] Retention/hold, release và xóa hợp lệ có phê duyệt và audit.
- [ ] Quy trình được diễn tập và có kết quả PASS/FAIL/INCONCLUSIVE kiểm chứng được.

## 14. Câu hỏi tự đánh giá

1. Tại sao SHA-256 đúng chưa đủ chứng minh file log xuất phát từ một nguồn đáng tin và đầy đủ?
2. Một VM nghi bị xâm nhập đang truyền dữ liệu ra ngoài. Khi nào cần containment trước khi thu RAM, và cần ghi gì trong decision record?
3. Nếu một pod cũ đã bị xóa, desired-state Deployment YAML có đủ để chứng minh quyền thực tế của container đó không? Cần nguồn bổ sung nào?
4. Vì sao cần giữ event_time, ingested_at và collected_at riêng biệt?
5. Nếu cloud audit export báo lỗi pagination nhưng những file đã tải đều có hash đúng, kết quả completeness cần đánh giá thế nào?
6. Khi analyst tạo normalized CSV từ raw JSONL, hồ sơ provenance và custody cần bổ sung những thông tin gì?
7. Những nguồn bổ sung nào giúp phân biệt một yêu cầu đọc object với dữ liệu chắc chắn đã truyền ra ngoài?
8. Làm sao thử khả năng khôi phục và kiểm tra tính toàn vẹn của một cloud snapshot đã lưu?
9. Vì sao immutable storage không giải quyết được việc thu sai nguồn hoặc bỏ sót log?
10. Hãy thiết kế một bài diễn tập bảo toàn log SaaS có thời hạn retention ngắn, với tiêu chí PASS và bằng chứng cần giữ.

**Điểm cốt lõi:** Evidence preservation bảo vệ khả năng hiểu đúng và kiểm chứng một sự cố sau khi các hệ thống, phiên truy cập và dữ liệu volatile đã thay đổi. Chất lượng chứng cứ phụ thuộc vào **nguồn, phạm vi, thời điểm, phương pháp thu thập, integrity, custody, quyền truy cập và những giới hạn được ghi rõ**. Trong security assurance, các năng lực này phải được chuẩn bị, diễn tập và kiểm tra thường xuyên để kết luận điều tra và khắc phục dựa trên bằng chứng đáng tin.
