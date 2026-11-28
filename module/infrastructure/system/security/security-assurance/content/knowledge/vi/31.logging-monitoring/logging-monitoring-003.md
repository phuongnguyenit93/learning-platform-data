# Log integrity: bảo đảm tính toàn vẹn của nhật ký và bằng chứng bảo mật

Trong hệ thống hiện đại, log là dữ liệu thiết yếu để phát hiện tấn công, điều tra sự cố, kiểm toán hành động quản trị, tái dựng chuỗi sự kiện và chứng minh một security control có hiệu lực. Tuy nhiên, việc nhìn thấy bản ghi trong dashboard chưa đủ để kết luận dữ liệu đó đáng tin. Log có thể bị sửa, giả mạo, xóa, cắt cụt, ghi sai thời gian hoặc thất lạc giữa nguồn và hệ thống lưu trữ.

**Log integrity** là khả năng bảo vệ hoặc phát hiện những thay đổi trái phép đối với nội dung nhật ký trong phạm vi đã xác định, cùng với bằng chứng cho phép kiểm chứng tuyên bố đó. Để log phục vụ điều tra đáng tin cậy, còn phải xem xét nguồn gốc, độ đầy đủ, thứ tự, thời gian, khả năng truy cập và quyền bảo vệ chứng cứ.

Bài học thuộc chương **Logging và monitoring** của module **SECURITY_SECURITY_ASSURANCE**. Module hướng tới đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu, security controls đến kiểm thử, audit và khắc phục phát hiện, trong một chương trình security assurance liên tục. Vì vậy, mỗi cơ chế bảo vệ log trong bài đều cần được chuyển thành tiêu chí, phép kiểm và bằng chứng đánh giá cụ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt integrity, authenticity, completeness, ordering, timeliness, availability và confidentiality của log.
2. Mô hình hóa các rủi ro sửa, xóa, giả mạo, mất, trùng và trì hoãn sự kiện.
3. Thiết kế chuỗi thu thập, truyền, xử lý, lưu giữ và xác minh nhật ký nhiều lớp.
4. Giải thích đúng vai trò và giới hạn của hash, HMAC, chữ ký số, hash chain, Merkle tree và immutable storage.
5. Thiết lập bộ control, tiêu chí đạt, bằng chứng và phép thử âm để kiểm tra log integrity.
6. Xây dựng quy trình chain of custody, xử lý finding và retest sau khắc phục.

## 2. Log integrity và các thuộc tính liên quan

### 2.1. Log có thể được sử dụng làm bằng chứng khi nào?

Một bản ghi bảo mật thường cần các trường:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| event_id, source_id | Xác định sự kiện và nguồn sinh | evt-184, payments-api/prod |
| event_time | Thời điểm nguồn ghi nhận sự kiện | 2026-11-28T07:15:20Z |
| receive_time, ingest_time | Thời điểm agent/collector nhận và hệ thống lưu | 2026-11-28T07:15:21Z |
| actor_id, action, outcome | Ai đã làm gì, kết quả gì | principal-219, permission.update, DENY |
| resource_id, request_id | Đối tượng và tương quan giữa hệ thống | merchant-708, req-44b7 |
| sequence, epoch | Trình tự trong một nguồn/partition | 184, instance-3 |
| schema_version, integrity_ref | Định dạng và điểm tham chiếu xác minh | v2, batch-07 |

Những giá trị này chỉ là ví dụ. Không phải mọi sự kiện phải có tất cả các trường, nhưng mỗi **nhóm sự kiện trọng yếu** cần định nghĩa schema và mức chính xác của dữ liệu. Không đưa password, private key, bearer token hoặc dữ liệu cá nhân không cần thiết vào log vì mục đích kiểm toán.

### 2.2. Các thuộc tính không đồng nhất

| Thuộc tính | Câu hỏi | Ví dụ sai lệch |
|---|---|---|
| **Integrity — toàn vẹn** | Nội dung có bị sửa trái phép so với bản gốc/điểm cam kết đáng tin không? | Event DENY bị đổi thành ALLOW |
| **Authenticity — xác thực nguồn gốc** | Có bằng chứng về nguồn hoặc hệ thống ký đã khai báo không? | Collector giả gửi event dưới tên app khác |
| **Completeness — đầy đủ** | Tất cả sự kiện thuộc phạm vi bắt buộc đã được ghi/thu đủ chưa? | Mất 10 phút log khi queue đầy |
| **Ordering — trình tự** | Có thể xác định trật tự cần thiết giữa các sự kiện không? | Batch đến muộn hoặc bị phát lại |
| **Timeliness — kịp thời** | Log đến hệ thống giám sát trong thời hạn cho phép không? | Sự kiện nghiêm trọng bị trễ nhiều giờ |
| **Availability — sẵn có** | Bằng chứng có thể truy cập khi cần điều tra không? | Kho log không truy vấn được sau sự cố |
| **Confidentiality — bí mật** | Ai được xem dữ liệu log và metadata nhạy cảm? | Log vô tình chứa khóa truy cập |

Hash của một file có thể hoàn toàn khớp nhưng file vẫn **thiếu sự kiện** do lỗi thu thập. Chữ ký hợp lệ có thể được tạo trên bản ghi sai sự thật bởi nguồn đã bị xâm phạm. Vì vậy, không dùng integrity để thay cho completeness hoặc authenticity.

### 2.3. Không đồng nhất integrity với mã hóa

- **TLS** bảo vệ tính bí mật và tính toàn vẹn trên một kết nối theo cơ chế xác thực đã cấu hình; sau khi giải mã ở endpoint, log vẫn có thể bị sửa.
- **Encryption at rest** giúp bảo mật nội dung trong lưu trữ theo mô hình khóa/quyền; riêng việc bật nó không chứng minh không ai có thể xóa hoặc thay file.
- **Checksum/hash** đối chiếu byte với một giá trị tham chiếu; nếu tham chiếu bị sửa cùng file, việc xác minh có thể bị đánh lừa.
- **HMAC/chữ ký số** cung cấp cơ chế kiểm chứng dựa trên khóa và mô hình tin cậy; chúng không chứng minh nguồn đã ghi mọi sự kiện.
- **WORM/immutable retention** bảo vệ đối tượng đã ghi trong kỳ lưu giữ theo tính năng và quyền thực tế của nền tảng; nó không ngăn mất log trước khi ghi.

Một đánh giá đúng phải nói rõ **đối tượng nào được bảo vệ, từ thời điểm nào, trước tác nhân đe dọa nào và trong kỳ nào**.

## 3. Mô hình đe dọa đối với log integrity

Các tài sản quan trọng gồm log nguồn, dữ liệu đang nằm trong buffer, segment/batch, log đã chuẩn hóa, manifest, hash/checkpoint, khóa signing, policy retention, tài khoản quản trị kho, audit của chính pipeline và hồ sơ điều tra.

### 3.1. Kịch bản rủi ro

| Điểm tấn công/lỗi | Kịch bản | Hậu quả |
|---|---|---|
| Ứng dụng bị chiếm quyền | Attacker vô hiệu hóa logging hoặc ghi sự kiện giả | Mất sự thật ngay tại nguồn |
| Log injection | Input chứa ký tự xuống dòng hoặc cấu trúc phá parser | Giả mạo hoặc đổi nghĩa sự kiện |
| Agent/collector | Agent crash, disk đầy, buffer overflow, cấu hình drop | Mất hoặc trễ event |
| Kênh truyền | Endpoint giả, thay đổi dữ liệu, retry/replay sai | Sai nguồn, trùng hoặc thiếu batch |
| Parser/normalizer | Bỏ trường quan trọng, bỏ event không đúng schema | Bằng chứng downstream không phản ánh nguồn |
| Kho log | Sửa, xóa, cắt cụt hoặc làm mất bản cũ | Mất lịch sử và dấu vết điều tra |
| Quyền đặc biệt | Admin có quyền cả ứng dụng, log, checkpoint và key | Có khả năng thay bằng chứng đồng thời |
| Khóa ký | Khóa bị lộ hoặc không quản lý rotation | Attacker tạo dấu xác thực giả |
| Thời gian | Clock drift, reset, sửa event_time | Tái dựng timeline sai |
| Xuất/chuyển chứng cứ | Sửa bản sao, mất metadata, không ghi bàn giao | Chain of custody không rõ |

Không nên chỉ xây threat model cho hacker bên ngoài. Insider có quyền cao, sai sót cấu hình, sự cố lưu trữ và nâng cấp pipeline cũng tạo ra rủi ro integrity.

### 3.2. Các ranh giới tin cậy

~~~mermaid
flowchart LR
    APP["Ứng dụng / OS / DB / Cloud audit"] --> AG["Agent + local buffer"]
    AG --> BROKER["Collector / broker"]
    BROKER --> NORMAL["Parser / normalizer"]
    NORMAL --> SEARCH["SIEM / Search"]
    NORMAL --> VAULT["Kho bằng chứng"]
    BROKER --> CHECK["Signer + checkpoint"]
    CHECK --> ROOT["Kho checkpoint độc lập"]
    VAULT --> VER["Verifier / Auditor"]
    ROOT --> VER
~~~

Ở từng chặng, cần trả lời: ai tạo, ai sửa được, ai xóa được, ai xác thực và ai giám sát mất mát. **Vị trí đặt trust anchor** rất quan trọng. Nếu hash chỉ được tính ở collector, nó chứng minh dữ liệu sau thời điểm collector cam kết không đổi; không chứng minh nguồn trước đó chưa bị sửa. Với log quan trọng, nên thu từ nguồn kiểm toán độc lập nếu có: hệ thống identity, API gateway, DB audit hoặc cloud control plane.

### 3.3. Mục tiêu bảo mật mẫu

Giả sử một dịch vụ thanh toán phải theo dõi mọi thay đổi quyền tại production:

1. Mọi thao tác thay đổi quyền thành công hoặc thất bại đều được ghi theo schema thống nhất.
2. Log được chuyển từ node ứng dụng sang kho trung tâm trong độ trễ đã phê duyệt, có cảnh báo gián đoạn.
3. Người quản trị ứng dụng không thể sửa hoặc xóa dữ liệu đã đưa vào kho chứng cứ.
4. Mọi sửa đổi trái phép đối với byte của segment đã cam kết đều làm verification thất bại.
5. Thiếu event, segment hoặc checkpoint được phát hiện sau cửa sổ chờ sự kiện đến muộn đã định.
6. Có thể xuất bằng chứng, xác minh khóa, digest, thời điểm, phạm vi và lịch sử bàn giao.

Các tiêu chí trên cần gắn với risk assessment, owner, mức rủi ro và pháp lý, không sử dụng một ngưỡng thời gian lưu giữ áp cho mọi loại log.

## 4. Pipeline thu thập và lưu log đáng tin cậy

### 4.1. Ghi log có cấu trúc

Log tự do dễ bị injection, không nhất quán timestamp và khó tìm kiếm. Một event có cấu trúc minh họa:

~~~json
{
  "schema_version": "1.0",
  "event_id": "evt-000184",
  "source_id": "payments-api/prod",
  "instance_epoch": "pod-7d9a",
  "sequence": 184,
  "event_time": "2026-11-28T07:15:20.130Z",
  "action": "permission.change",
  "actor_id": "principal-219",
  "resource_id": "merchant-708",
  "outcome": "DENY",
  "request_id": "req-44b7"
}
~~~

Schema cần quy định bắt buộc/tùy chọn, kiểu dữ liệu, escaping, độ dài và giá trị hợp lệ. Parser phải xử lý an toàn input lạ: newline, Unicode, duplicate JSON keys, timestamp không hợp lệ và payload quá lớn. Không ghép trực tiếp input người dùng vào dòng log cho phép làm giả prefix/severity/event.

### 4.2. Phân biệt các timestamp

- **event_time:** nguồn cho biết sự kiện xảy ra khi nào.
- **receive_time:** agent/collector tiếp nhận khi nào.
- **ingest_time:** hệ thống lưu hoặc index sự kiện khi nào.

Lưu các mốc này theo UTC và ghi rõ timezone, đồng thời giám sát đồng hồ của nguồn. Event có event_time cũ chưa chắc là tấn công: có thể do clock drift hoặc backfill. Nhận biết điều đó giúp tránh phát hiện sai và phân biệt độ trễ pipeline với thời gian thực của hành vi.

### 4.3. Chuyển giao có khả năng kiểm soát thất thoát

Thiết kế agent/broker nên xác định:

- **Acknowledgement:** xác nhận khi bên nhận đã nhận bền vững theo hợp đồng, tránh hiểu việc gọi API thành công là đã lưu lâu dài.
- **Buffer/queue:** giữ tạm khi mạng hoặc broker lỗi; kiểm soát full disk và chính sách quá tải.
- **Retry/backoff:** có giới hạn phù hợp; theo dõi lỗi kéo dài.
- **Event ID và idempotency:** xử lý duplicate khi sử dụng at-least-once delivery.
- **Sequence:** phát hiện gap trong phạm vi một nguồn/partition.
- **Dead-letter:** lưu event lỗi parse để điều tra thay vì âm thầm loại.
- **Metrics:** dropped_events, queue_lag, ingest_delay, retry_errors, bytes_sent và agent_health.
- **Heartbeat:** phát hiện nguồn hoặc checkpoint ngừng gửi, kể cả khi không có event nghiệp vụ.

Không khẳng định "không mất log" khi chưa thử các điều kiện lỗi nằm trong phạm vi cam kết. Pipeline không thể bảo vệ event chưa từng được ứng dụng tạo ra.

### 4.4. Bản gốc và dữ liệu chuẩn hóa

Normalizer có thể ẩn thông tin cá nhân, đổi tên trường, chuyển kiểu timestamp hoặc bổ sung metadata. Việc này có thể hợp lệ nhưng cần phân biệt:

- **Raw event:** bản ghi trước biến đổi, nếu chính sách cho phép giữ.
- **Normalized event:** sự kiện sau khi áp quy tắc xử lý.
- **Transformation record:** parser version, thời gian, rule và mapping.
- **Integrity reference:** hash/signature/batch của đối tượng được cam kết.
- **Linkage:** cách truy lại cùng một event qua các hệ thống.

Không dùng hash của raw event để yêu cầu nó phải bằng hash của normalized event. Assurance cần kiểm chứng cả **byte-level integrity** và **processing/semantic integrity** ở những chặng có chuyển đổi.

## 5. Hash, HMAC và chữ ký số

### 5.1. Hash và trust anchor

Hàm SHA-256 tính giá trị băm cho byte:

~~~text
digest = SHA-256(exact_bytes_of_log_segment)
~~~

Nếu nội dung thay đổi, digest mới gần như chắc chắn khác digest cũ. Tuy nhiên, nếu attacker có thể thay **cả log lẫn digest tham chiếu**, kiểm tra vẫn có thể PASS.

~~~bash
sha256sum events.ndjson
sha256sum --check evidence.sha256
~~~

Lệnh thứ hai giả định manifest evidence.sha256 đã được xác thực và quản lý độc lập. Chỉ có tệp checksum đặt cạnh log với cùng quyền ghi không đủ làm bằng chứng chống sửa.

### 5.2. HMAC

HMAC dùng secret key và dữ liệu cần xác thực:

~~~text
tag = HMAC-SHA-256(key, canonical(segment))
verify(key, segment, tag) -> PASS or FAIL
~~~

HMAC bảo vệ trước người không biết khóa. **Mọi bên có khóa đều có khả năng tạo HMAC mới**, nên dùng khóa chung cho nhiều đội không tạo bằng chứng độc lập về bên nào thực sự đã ký. Cần kiểm soát quyền dùng key, rotation, lộ khóa, key ID và giới hạn thời hạn.

### 5.3. Chữ ký số

Một hệ thống ký manifest hoặc segment bằng private key và verifier dùng public key tin cậy. Để kết luận verification đạt, cần xét:

1. Thuật toán được phê duyệt, tham số, định dạng chữ ký và dữ liệu được ký.
2. Định danh signer, public key/certificate và trust policy.
3. Hiệu lực, rotation, sự kiện lộ hoặc thu hồi khóa theo thời điểm.
4. Thời điểm ký, phạm vi segment và khả năng chứng minh mốc thời gian.
5. Chính sách bảo vệ private key, giới hạn quyền và audit khi ký.

**Chữ ký hợp lệ không chứng minh nguồn trung thực** nếu attacker đã kiểm soát nguồn trước lúc ký. Chữ ký cũng không tự chứng minh những segment bị thiếu.

### 5.4. Chuẩn hóa để ký (canonicalization)

Hai đối tượng JSON dưới đây có nội dung trường tương đương nhưng byte khác nhau:

~~~json
{"action":"login","outcome":"DENY"}
~~~

~~~json
{"outcome":"DENY","action":"login"}
~~~

Hash trên byte trực tiếp khác nhau. Nếu hệ thống yêu cầu chữ ký của cấu trúc ngữ nghĩa, cần định nghĩa canonicalization gồm thứ tự trường, UTF-8, Unicode, số, timestamp, escaping, duplicate keys, schema version và trường không có. Thay đổi cách serialize phải tạo version mới; giữ version lịch sử để verify lại dữ liệu cũ.

## 6. Hash chain và checkpoint độc lập

### 6.1. Nguyên lý chuỗi băm

Có thể nối các event trong từng luồng:

~~~text
h_0 = trusted_genesis_hash
h_i = SHA-256(
  encode(h_(i-1), source_id, epoch, sequence_i, canonical(event_i))
)
~~~

Hàm encode phải phân định kiểu và độ dài để không nhập nhằng dữ liệu. Nếu sửa event ở giữa chuỗi, kết quả của event đó và tất cả event tiếp theo sẽ thay đổi khi đối chiếu với hash/commitment tin cậy.

**Giới hạn:** attacker có thể viết lại toàn bộ chuỗi nếu cũng thay được giá trị tham chiếu; việc xóa phần đuôi khó bị phát hiện nếu không có mốc kỳ vọng. Cần **checkpoint định kỳ**, tốt hơn khi được ký và lưu ở nơi có quyền quản trị độc lập, kèm kỳ vọng số lượng event hoặc heartbeat.

### 6.2. Merkle tree

Merkle tree tạo các hash lá từ event/batch và ghép thành root hash. Bằng chứng Merkle inclusion cho phép kiểm tra một record nằm trong batch đã commit mà không cần truyền toàn bộ batch.

Merkle root chỉ ràng buộc **tập dữ liệu đã đưa vào cây**. Nếu event bị bỏ trước bước xây cây, một root hợp lệ vẫn có thể đại diện cho một batch thiếu. Phải kiểm tra nguồn, sequence, count và mốc checkpoint.

### 6.3. Checkpoint tham khảo

~~~yaml
checkpoint_id: "payments-2026-11-28T07:20Z"
source_id: "payments-api/prod"
epoch: "pod-7d9a"
sequence_from: 150001
sequence_to: 150487
event_count: 487
period_start: "2026-11-28T07:15:00Z"
period_end: "2026-11-28T07:20:00Z"
canonicalization_version: "v2"
hash_algorithm: "SHA-256"
root_hash: "EXAMPLE_ROOT_HASH"
signer_key_id: "signer-v4"
signature_ref: "signatures/checkpoint-0720.sig"
~~~

Giá trị hoàn toàn giả định. Không được coi có trường signature_ref là đủ: phải có chữ ký thật và bước xác minh bằng khóa tin cậy. Checkpoint nên được gửi đến kho độc lập, ghi thời gian nhận, theo dõi missing checkpoint và bảo vệ qua retention.

### 6.4. Độ trễ, sequence gap và cắt phần đuôi

Trong hệ thống phân tán, event có thể đến muộn hoặc đến sai thứ tự. Kiểm tra cần định nghĩa:

- Late-arrival window và điều kiện đóng kỳ.
- Cách xử lý retry, duplicate, backfill và restart sequence.
- Định danh epoch khi một instance khởi động lại.
- Ngưỡng cảnh báo thiếu checkpoint và mất nguồn log.
- Mốc cuối được kỳ vọng từ nguồn độc lập; không chỉ nhìn các file còn tồn tại.

Một khoảng sequence trống trước khi đóng kỳ có thể chỉ là dữ liệu đến muộn. Nhưng sau ngưỡng chờ đã định, vẫn phải tạo trạng thái nghi vấn và finding nếu không đối soát được.

## 7. Immutable storage và phân tách quyền

### 7.1. WORM và retention lock

Write Once Read Many (WORM) cùng các tính năng immutable retention nhằm ngăn hoặc giới hạn sửa/xóa đối tượng đã ghi trong kỳ lưu giữ. Những khả năng có thể cân nhắc theo dịch vụ:

- **AWS S3 Object Lock:** retention và legal hold theo cấu hình, cần hiểu versioning và các chế độ governance/compliance.
- **Azure Blob immutable storage:** chính sách time-based retention và legal hold khi phù hợp.
- **Google Cloud Storage Bucket Lock:** retention policy được khóa theo cơ chế nền tảng.

Những dịch vụ này có semantics, quyền và giới hạn khác nhau. Không nên tuyên bố "đã bật logging nên log bất biến". Cũng cần phân biệt giai đoạn **trước khi commit vào kho** với giai đoạn kho đã áp chính sách.

### 7.2. Tách quyền theo chức năng

| Vai trò | Quyền cần thiết | Hạn chế cần xác minh |
|---|---|---|
| Ứng dụng/producer | Tạo sự kiện và gửi đến endpoint cho phép | Không thể xóa lịch sử hoặc thay checkpoint |
| Agent/collector | Chuyển, bổ sung batch mới và xem metrics | Không được xóa bản cũ hoặc đổi retention |
| Đội vận hành dịch vụ | Quan sát logs thuộc scope và xử lý lỗi | Không có quyền xóa bằng chứng về hành vi của chính mình |
| Đội giám sát/SOC | Đọc, tìm kiếm, tạo alert, quản lý case | Không tự sửa dữ liệu gốc đã cam kết |
| Quản trị lưu trữ | Quản lý nền tảng theo quy trình | Quyền đặc biệt phải có phê duyệt/audit và kiểm soát độc lập |
| Đội audit | Đọc bản chứng cứ, checkpoint và chạy verify | Không làm biến đổi bản gốc trong khi phân tích |
| Quản trị khóa | Quản lý/rotation/revocation theo chính sách | Không tự ý sửa log và chứng cứ liên quan |

Assurance phải kiểm tra **effective permissions** gồm các quyền kế thừa từ organization/tenant, IAM role, nhóm quản trị, khóa mã hóa, backup và quyền cấp cao, thay vì chỉ xem ACL một bucket.

### 7.3. Tách kho tìm kiếm và kho bằng chứng

SIEM thường ưu tiên search, enrich, index, tối ưu retention và hiệu năng. Kho chứng cứ ưu tiên bảo vệ raw segment/manifest/checkpoint đủ thời gian kiểm toán.

~~~mermaid
flowchart LR
    SOURCE["Log source"] --> AG["Agent/collector"]
    AG --> SIEM["Search/SIEM"]
    AG --> EVIDENCE["Evidence store có retention"]
    AG --> SIGN["Signer/checkpoint"]
    SIGN --> INDEPENDENT["Independent checkpoint store"]
    EVIDENCE --> VERIFY["Verifier"]
    INDEPENDENT --> VERIFY
~~~

Nếu collector bị chiếm trước lúc gửi vào evidence store, bản WORM có thể vẫn chứa dữ liệu giả. Đó là lý do cần identity, source audit và đối soát độc lập.

### 7.4. Retention và dữ liệu cá nhân

Log có thể chứa thông tin khách hàng hoặc tài sản trí tuệ. Giữ bất biến lâu hơn thời gian cần thiết có thể mâu thuẫn với chính sách dữ liệu hoặc quy định pháp luật áp dụng. Cần phân loại, tối thiểu hóa trường thu thập, masking tại điểm thích hợp, giới hạn quyền đọc và đặt retention đúng theo loại log. Việc khóa chính sách không thể hoàn tác ở một số chế độ cần được cân nhắc trước khi áp dụng, đặc biệt với dữ liệu nhạy cảm.

## 8. Đồng bộ thời gian và đối soát tính đầy đủ

### 8.1. Đồng hồ và timestamp

Khi điều tra đa hệ thống, timeline từ application, IdP, database, mạng và cloud control plane có thể lệch. Cần giám sát đồng bộ thời gian, ghi nhận reset/clock drift và không mặc định event_time tăng dần biểu diễn đúng trình tự nhân quả.

Một timestamp do máy bị xâm nhập tạo ra không tự chứng minh thời điểm tuyệt đối. Với yêu cầu cao, có thể cần checkpoint độc lập có dấu thời gian đáng tin và đối chiếu nhiều nguồn.

### 8.2. Heartbeat và kiểm tra gián đoạn

Heartbeat từ nguồn cho thấy đường phát tín hiệu đang hoạt động, không khẳng định mọi security event đã được tạo. Để kiểm tra completeness:

- So sánh số event/sequence phát sinh và đã tiếp nhận.
- Tìm gap, duplicate, batch bị trễ và dropped count.
- Đối chiếu với nguồn độc lập như API gateway, IdP audit hoặc database audit.
- Phân biệt nguồn im lặng hợp lệ và nguồn ngừng ghi log.
- Đặt cửa sổ chờ event muộn trước khi kết luận FAIL.
- Kiểm tra cả log của hệ thống thu log để phát hiện thay đổi hoặc tắt cơ chế giám sát.

Không có cơ chế phổ quát nào chứng minh đầy đủ mọi sự kiện khi nguồn đã bị chiếm toàn quyền. Báo cáo phải nêu rõ giả định và giới hạn đó.

## 9. Baseline control và bằng chứng assurance

| ID | Control | Điều kiện đánh giá | Bằng chứng/phép kiểm |
|---|---|---|---|
| **LI-01** | Kiểm kê nguồn | Mọi nguồn log bắt buộc có ID, owner, môi trường và phân loại | So khớp inventory dịch vụ với nguồn thực tế |
| **LI-02** | Ghi nhận event | Sự kiện trọng yếu có schema và trường cần thiết; thay đổi logging có audit | Sinh sự kiện thử, kiểm tra cấu hình và log |
| **LI-03** | Xác thực nguồn | Producer và collector xác thực, nguồn không được phép bị chặn | Cấu hình TLS/mTLS/identity và test deny |
| **LI-04** | Vận chuyển bền vững | Buffer, ack, retry và monitoring theo failure model | Test ngắt kết nối/collector crash, đối soát count |
| **LI-05** | Phát hiện mất/trùng | Có sequence, event ID hoặc bộ đếm; nhận diện gap, replay, duplicate | Thử mất batch, replay và kiểm tra alert |
| **LI-06** | Integrity mật mã | Log/segment có hash/MAC/chữ ký và trust anchor | Verify mẫu nguyên vẹn và mẫu sửa byte |
| **LI-07** | Checkpoint | Mốc cam kết được giữ độc lập và có alert khi thiếu | Danh sách checkpoint, test cắt đuôi |
| **LI-08** | Immutable storage | Kho chứng cứ hạn chế sửa/xóa theo kỳ retention | Policy hiệu lực, test delete/overwrite bị từ chối |
| **LI-09** | Phân tách quyền | Đội vận hành nguồn không tự sửa log, key, checkpoint | IAM/RBAC effective permission và test deny |
| **LI-10** | Thời gian | Có event/receive/ingest time và clock drift monitoring | Cấu hình sync, telemetry, timeline test |
| **LI-11** | Phát hiện tamper | Thay logging config, retention, key và collector gây cảnh báo | Change audit, alert và tamper test |
| **LI-12** | Retention và privacy | Lưu đúng kỳ hạn, kiểm soát dữ liệu nhạy cảm | Policy, masking sample, retention audit |
| **LI-13** | Chain of custody | Xuất, chuyển và verify log có lịch sử chứng cứ | Export manifest, digest, audit access |
| **LI-14** | Restore và continuity | Restore bản chứng cứ và verify được trong phạm vi cam kết | Restore drill, checksum/signature result |
| **LI-15** | Continuous assurance | Finding có owner, thời hạn, sửa và retest | Dashboard có mẫu số, ticket và retest result |

Một control quan trọng thường cần **bằng chứng cấu hình** cộng **kiểm thử hiệu lực**. Ví dụ LI-08 không thể chỉ dựa vào ảnh "retention enabled": phải kiểm tra đúng object/version, quyền xóa hiệu lực, thời gian áp dụng, alert thay chính sách và kết quả test deny với identity phù hợp.

## 10. Kiểm thử thực tế trên gói log

### 10.1. Gói bằng chứng tham khảo

~~~text
evidence/
  2026-11-28T07/
    events.ndjson
    manifest.json
    manifest.sig
    signer-chain.pem
    verify-result.json
~~~

Ý nghĩa:

- **events.ndjson:** các event thuộc một segment theo schema.
- **manifest.json:** source_id, time range, sequence range, record count, digest của file.
- **manifest.sig:** chữ ký trên representation chuẩn của manifest.
- **signer-chain.pem:** thông tin public key/certificate và chuỗi tin cậy, nếu dùng PKI.
- **verify-result.json:** kết quả kiểm chứng độc lập.

~~~json
{
  "manifest_version": "1",
  "source_id": "payments-api/prod",
  "segment_id": "2026-11-28T07",
  "from_sequence": 150001,
  "to_sequence": 150487,
  "event_count": 487,
  "payload_encoding": "UTF-8 NDJSON",
  "digest_algorithm": "SHA-256",
  "payload_digest": "EXAMPLE_HEX_DIGEST",
  "signer_key_id": "signer-prod-v4",
  "signature_algorithm": "EXAMPLE_APPROVED_ALGORITHM",
  "checkpoint_ref": "checkpoints/2026-11-28T07.json"
}
~~~

Các giá trị digest và algorithm giả định chưa phải chữ ký hợp lệ. Manifest trong hệ thống thực phải dùng giá trị và thuật toán được phê duyệt.

### 10.2. Trình tự kiểm chứng

1. **Xác định scope:** source, segment ID, kỳ, thời gian, schema và định danh collector.
2. **Xác minh chữ ký manifest:** xác minh khóa, trust chain, thuật toán, dữ liệu ký và chính sách key rotation/revocation.
3. **Tính digest file log:** so sánh byte đúng với digest nằm trong manifest đã xác thực.
4. **Kiểm tra record count/sequence:** xác minh range, duplicate/gap và xử lý late arrival.
5. **Đối chiếu checkpoint độc lập:** mốc cam kết đã nhận đúng kỳ; cảnh báo nếu checkpoint bị thiếu.
6. **Đối soát dữ liệu nguồn độc lập:** kiểm tra khả năng mất event trước khi segment được tạo.
7. **Lưu kết quả:** tool/version, assessor, timestamp, kiểm tra PASS/FAIL/INCONCLUSIVE và mọi giới hạn.

Lệnh minh họa tính hash cho file tại máy:

~~~bash
sha256sum events.ndjson
~~~

Lệnh chỉ tính hash của file hiện tại. Không dùng nó như bằng chứng integrity nếu thiếu manifest đã xác thực hoặc chứng cứ checkpoint.

### 10.3. Phép kiểm âm: sửa một byte

Trên một **bản sao trong môi trường test**:

1. Sửa một byte của events.ndjson, giữ nguyên manifest/signature.
2. Chạy lại verifier.
3. Kỳ vọng integrity verification **FAIL**, nêu rõ segment và sai lệch.
4. Kiểm tra alert được gửi đến đội vận hành assurance và finding được tạo.

Nếu chỉnh cả events và manifest không ký vẫn có thể PASS thì thiết kế thiếu mốc tin cậy độc lập.

### 10.4. Phép kiểm âm: xóa segment hoặc cắt đuôi

- Bỏ một segment đã cam kết hoặc mô phỏng mất checkpoint của kỳ cuối.
- Xác minh missing sequence/missing checkpoint alert sau cửa sổ trễ cho phép.
- Nếu tất cả file còn lại có hash đúng nhưng hệ thống không phát hiện segment biến mất, **completeness control chưa đạt**.

### 10.5. Phép kiểm quyền truy cập

Dùng identity của operator/collector đã được phê duyệt trong tài nguyên test:

- Thử xóa/ghi đè object đang có retention lock.
- Thử sửa policy hoặc checkpoint vượt quyền.
- Kiểm chứng deny, ghi audit, thời gian và context.
- Rà soát effective permission của quyền cấp cao, không chỉ identity test.

Kết quả PASS cần mô tả chính xác vai trò và hành động đã thử, tránh kết luận mọi principal đều bị giới hạn khi chưa kiểm tra phạm vi đó.

## 11. Kiểm chứng log integrity trên cloud và Kubernetes

### 11.1. Cloud audit log

Ở các môi trường cloud, nguồn log và nơi lưu giữ có thể do các dịch vụ khác nhau quản lý, với mức bảo vệ và trách nhiệm riêng.

**AWS:** có thể sử dụng CloudTrail cho một phần hoạt động quản trị và audit. Khi tính năng **CloudTrail log file integrity validation** được bật và cấu hình phù hợp, hệ thống cung cấp digest file để hỗ trợ xác minh log file đã giao có bị thay đổi/xóa theo mô hình của tính năng. Assurance vẫn phải kiểm tra trail được áp đúng account, region, sự kiện cần thiết và đường giao log. Digest hợp lệ không có nghĩa ứng dụng đã tạo đủ audit event hoặc mọi data event đều được bật.

**Microsoft Azure:** cần xác định đúng Azure Activity Log, diagnostic settings, đích xuất log và phạm vi subscription/resource được thu. Nếu dùng Azure Blob immutable storage để giữ bằng chứng, cần xác minh chính sách time-based retention/legal hold ở đúng tài nguyên, kiểm tra quyền sửa diagnostic setting và việc export thực sự hoạt động.

**Google Cloud:** đánh giá Cloud Audit Logs, cấu hình log sink/log bucket hoặc đích Cloud Storage, loại sự kiện thuộc yêu cầu, các filter/exclusion và quyền đổi sink. Nếu dùng retention lock ở đích, cần xác định thời điểm và phạm vi khóa, cùng khả năng sửa/xóa của các danh tính cấp tổ chức.

Trong mọi trường hợp, cần phân biệt:
- **Nhật ký do nhà cung cấp tạo** với log ứng dụng tự sinh.
- **Bật thu thập** với **đã chuyển tới kho chứng cứ**.
- **Có chính sách retention** với **không thể sửa/xóa theo threat model**.
- **Hash/chữ ký hợp lệ** với **độ đầy đủ của sự kiện**.

### 11.2. Container và Kubernetes

Ứng dụng thường ghi log ra stdout/stderr, agent trên node hoặc nền tảng quản lý log sẽ thu thập. Những rủi ro riêng gồm: container bị xóa trước khi gửi hết buffer, log rotation quá nhanh, node mất, quyền truy cập file log trên host, agent crash và nhiều container chung một pod.

Một phép đánh giá có thể thực hiện trong namespace thử được phép:

1. Tạo một event có request_id duy nhất và ghi lại timestamp tại nguồn.
2. Xác minh agent nhận event, collector tiếp nhận và kho bằng chứng commit segment.
3. So khớp source_id, pod/container identity, epoch, request_id và hash/checkpoint của batch.
4. Mô phỏng mất kết nối hoặc pod restart để thử buffer, retry, duplicate và detection.
5. Kiểm tra những quyền có thể tắt log agent, sửa config collector hoặc xóa log đã lưu.
6. Xác minh event được truy vấn tại SIEM và bản chứng cứ riêng, công bố sự khác biệt do parsing/masking.

Đối với log **Kubernetes audit** hoặc control plane, cần hiểu chính sách audit của API server, đích nhận, retention và giới hạn log được cấu hình. Log pod của ứng dụng không thể thay thế audit cấp control plane.

### 11.3. Thử thay đổi cấu hình logging

Một hệ thống có thể ghi log đúng hôm nay nhưng bị vô hiệu hóa sau deployment. Vì vậy cần theo dõi:
- Thay đổi logging level, loại audit event, sink/filter/exclusion.
- Sửa cấu hình pipeline, parser, agent hoặc destination.
- Đổi IAM/RBAC trên kho log, checkpoint store và signing key.
- Thay retention, lifecycle, legal hold hoặc policy immutable.
- Tắt cảnh báo hoặc thay ngưỡng monitoring.

Cần giữ change record (người thực hiện, thời gian, chính sách cũ/mới, phê duyệt nếu cần) và tạo alert khi có hành vi trái quy trình. Một thay đổi được phê duyệt vẫn cần kiểm tra tác động đến chất lượng bằng chứng.

## 12. Chain of custody: quản lý chứng cứ khi điều tra

**Chain of custody** là lịch sử các thao tác thu thập, sao chép, bàn giao, phân tích, chuyển đổi, truy cập hoặc lưu giữ bằng chứng. Nó không thay thế kiểm chứng mật mã nhưng giúp giải thích tính đáng tin và trách nhiệm của từng hành động.

### 12.1. Trình tự quản lý chứng cứ

1. **Nhận diện:** ghi incident ID, nguồn, khoảng thời gian, segment ID, đường dẫn và dữ liệu liên quan.
2. **Thu thập:** dùng công cụ và danh tính được cho phép; giữ nguyên dữ liệu gốc và ghi nhận thời điểm thu.
3. **Tính/kiểm hash, chữ ký:** dùng dữ liệu gốc, manifest, signer policy và checkpoint theo quy trình.
4. **Bảo quản:** chuyển bản gốc hoặc bản sao pháp chứng vào nơi bảo vệ, phân quyền và retention.
5. **Làm việc trên bản sao:** khi lọc, masking, normalize hoặc export, giữ liên kết đến bản gốc và metadata chuyển đổi.
6. **Ghi bàn giao:** ai chuyển cho ai, khi nào, vì sao, dữ liệu nào, có digest trước/sau ra sao.
7. **Kiểm chứng độc lập:** chạy lại verify trước khi dùng kết quả cho kết luận kiểm toán hoặc điều tra.

Một ví dụ hồ sơ:

~~~yaml
evidence_id: "INC-2026-118/log-segment-07"
incident_id: "INC-2026-118"
source_id: "payments-api/prod"
collected_at: "2026-11-28T08:42:00Z"
collector_identity: "incident-response-service"
original_reference: "evidence-store/segment-07"
byte_count: 148320
digest_algorithm: "SHA-256"
digest_value: "EXAMPLE_DIGEST"
custody:
  - action: "copy-for-analysis"
    actor: "ir-analyst-01"
    timestamp: "2026-11-28T08:47:00Z"
    destination: "forensic-workspace/copy-07"
verify_result: "PASS_WITH_SCOPE"
limitations:
  - "Hash chỉ đối chiếu bản sao với digest tin cậy tại thời điểm thu"
~~~

Các giá trị trên là giả định. Trường hợp có yêu cầu pháp lý đặc biệt, quy trình có thể cần người chứng kiến, ký xác nhận, niêm phong hoặc cách lưu giữ do tổ chức quy định.

### 12.2. Những giới hạn cần nêu rõ

- Hash đúng chứng minh **bản đang kiểm tra khớp với mốc tham chiếu**, không chứng minh nguồn đã luôn trung thực.
- Chữ ký của hệ thống export chỉ xác nhận dữ liệu tại lúc export, không tự xác nhận đường thu thập trước đó.
- Bản sao SIEM và bản gốc có thể khác byte do normalize hoặc masking; cần lưu mô tả transformation.
- Nếu hệ thống nguồn đã bị xâm phạm, cần kiểm chứng thông tin bằng nguồn độc lập.
- Không đưa credential, token hoặc dữ liệu bí mật chưa cần thiết vào báo cáo phân tích để rồi tạo thêm rủi ro lộ dữ liệu.

## 13. Case study: thiếu 12 phút log thay đổi quyền

Một tổ chức có dịch vụ thanh toán ghi audit log tại ứng dụng, đồng thời có audit từ identity provider và database. Yêu cầu bảo mật quy định mọi hành động thay đổi quyền ở production phải được ghi và truy vấn được trong 180 ngày.

**Phát hiện:** sau sự cố nghi chiếm quyền, đội điều tra thấy kho trung tâm thiếu application log từ **09:12 đến 09:24 UTC**. Các tệp trước và sau khoảng này đều có SHA-256 hợp lệ so với manifest.

Kết luận "log nguyên vẹn toàn bộ" lúc này là sai vì cần tách **tính toàn vẹn file đang có** khỏi **độ đầy đủ của dòng sự kiện**.

### 13.1. Phân tích theo lớp

**Tại nguồn:** kiểm tra phiên bản ứng dụng, deployment, logging config, event counter, sequence, health và các event thay đổi quyền từ IdP/DB. Cần trả lời log chưa được tạo hay đã tạo nhưng không chuyển thành công.

**Tại agent và broker:** kiểm tra restart, local buffer, disk usage, queue lag, retry, dropped_events, dead-letter và acknowledgement.

**Tại kho lưu:** đối chiếu danh sách segment với manifest/checkpoint, audit sửa/xóa object, retention và các quyền đặc biệt.

**Tại timeline:** so sánh event_time, receive_time và ingest_time, theo dõi clock drift, tránh nhầm sự kiện đến muộn là sự kiện bị mất.

Giả định evidence cho thấy collector restart lúc 09:12, buffer node đầy, thiếu sequence 31001–31126 và không có checkpoint kỳ 09:15. Cảnh báo missing checkpoint đã được phát nhưng chưa được xử lý.

### 13.2. Đánh giá control

| Control | Kết quả minh họa | Lý do |
|---|---|---|
| LI-06 — Integrity từng file | **PASS trong các file đã thử** | Hash/chữ ký các file còn lại hợp lệ |
| LI-05 — Phát hiện mất/trùng | **PASS trong phạm vi test** | Gap và missing checkpoint đã được phát hiện |
| LI-04 — Chuyển log bền vững | **FAIL** | Buffer đầy gây thất thoát trước khi lưu |
| LI-07 — Checkpoint | **FAIL hoặc INCONCLUSIVE tùy assertion** | Checkpoint bị thiếu, cần xác định cơ chế cảnh báo và kỳ cam kết |
| LI-15 — Xử lý finding | **FAIL nếu vi phạm SLA** | Alert đã phát nhưng không xử lý đúng kỳ hạn |
| Timeline thay đổi quyền | **INCONCLUSIVE cho khoảng thiếu** | Không đủ bằng chứng từ application; cần đối chiếu IdP/DB |

Tùy câu hỏi kiểm toán, một control có thể PASS trong phạm vi hẹp nhưng mục tiêu tổng thể vẫn chưa đạt. Báo cáo nên trình bày thẳng giới hạn này.

### 13.3. Khắc phục và retest

1. Ghi finding với nguồn, event class, time window, gap, tác động, owner và deadline.
2. Điều chỉnh buffer/queue, retry, ghi bền vững và giới hạn tài nguyên theo failure model đã phê duyệt.
3. Cấu hình cảnh báo về dropped events, missing checkpoint và ingest lag; có người nhận và escalations.
4. Kiểm thử mất kết nối và collector restart trong môi trường test, xác nhận event đến đủ hoặc có cơ chế nhận diện tổn thất đúng tiêu chí.
5. Chạy lại phép verify segment, checkpoint, đối soát count/sequence và thử phản ứng alert.
6. Đóng finding sau khi có **bằng chứng retest**, đồng thời ghi rõ rủi ro còn lại nếu chưa thể ngăn toàn bộ dạng mất log.

Nếu một kiến trúc không thể bảo đảm zero loss trước mọi dạng sự cố, assurance phải giới hạn kết luận theo failure model và cung cấp cơ chế phát hiện cùng khắc phục tương ứng.

## 14. Continuous assurance và giám sát drift

Một pipeline được đánh giá đạt vào đầu quý có thể không đạt sau khi thay quyền, nâng cấp collector, đổi filter hoặc policy retention. Vì vậy, kiểm tra integrity cần diễn ra **liên tục** theo các lần thay đổi và chu kỳ rủi ro.

~~~mermaid
flowchart LR
    R["Rủi ro và yêu cầu"] --> D["Thiết kế control"]
    D --> I["Triển khai pipeline + policy"]
    I --> V["Kiểm chứng bằng chứng"]
    V --> P{"Đạt tiêu chí?"}
    P -- "Có" --> M["Monitor drift và checkpoint"]
    P -- "Không" --> F["Finding + owner + hạn"]
    M --> T["Change / alert / audit"]
    T --> V
    F --> X["Khắc phục và retest"]
    X --> V
~~~

### 14.1. Điểm đo theo vòng đời

| Thời điểm | Hoạt động assurance | Bằng chứng giữ lại |
|---|---|---|
| Thiết kế hệ thống | Threat model, phân loại nguồn, yêu cầu retention, identity | Tài liệu được phê duyệt, control mapping |
| Thay mã nguồn | Kiểm tra event bắt buộc, schema, tránh secret/log injection | Test result, code review, event sample |
| Thay cấu hình | Policy-as-code cho collector, sink, storage, IAM | Pull request, diff, approval, policy validation |
| Vận hành | Heartbeat, sequence, checkpoint, drop metrics, audit quyền | Metrics, alarm và snapshot |
| Audit định kỳ | Xác minh mẫu segment, signature, retention và restore | Báo cáo độc lập, scope, tool version |
| Sau sự cố | Chain of custody, xác định khoảng mất, nguồn độc lập | Incident report, forensic export, retest |

### 14.2. KPI cần hiểu mẫu số và giới hạn

| KPI | Cách tính/quan sát | Giới hạn |
|---|---|---|
| **Source coverage** | Nguồn bắt buộc có owner và telemetry / tổng nguồn bắt buộc được phát hiện | Inventory thiếu làm tỷ lệ cao giả |
| **Integrity verification coverage** | Segment verify PASS / tổng segment kỳ vọng trong phạm vi | Không chỉ tính file vẫn còn tồn tại |
| **Missing checkpoint rate** | Checkpoint thiếu/trễ / checkpoint kỳ vọng | Phải xét cửa sổ late arrival |
| **Delivery gap rate** | Kỳ hoặc sequence chưa đối soát / tổng kỳ được đo | Không thể đo đúng nếu nguồn không phát counter |
| **Detection latency** | Từ sai lệch đến lúc alert có thể hành động | Phân biệt event/ingest/alert timestamp |
| **Immutable coverage** | Log chứng cứ giữ đúng retention / tổng log cần bảo vệ | Kiểm tra policy hiệu lực và quyền cao |
| **Privileged access review** | Principal đặc quyền đã rà soát / tất cả principal đặc quyền | Xét group, role và cấp tổ chức |
| **Time to remediate** | Từ phát hiện đến khi retest PASS | Ticket chuyển Done không đủ |
| **Overdue exceptions** | Ngoại lệ hết hạn chưa được xử lý / tổng ngoại lệ hết hạn | Cần owner và thời hạn rõ |

Ví dụ KPI 100% "checksum verified" có thể chỉ nói **những file đang còn** đều khớp, trong khi log đã bị xóa không có ai phát hiện. Muốn KPI phản ánh assurance tốt phải xác định mẫu số qua inventory, sequence và checkpoint ngoài kho đang được kiểm.

### 14.3. Ngoại lệ có kiểm soát

Một số hệ thống cũ chưa hỗ trợ ký log gần nguồn hoặc retention lock. Ngoại lệ cần ghi:

- Control nào chưa đạt và tài nguyên nào chịu ảnh hưởng.
- Lý do kỹ thuật, rủi ro, owner và thời hạn.
- Biện pháp bù trừ như audit nguồn độc lập, giảm quyền, immutable backup, đối soát tăng cường.
- Người phê duyệt, điều kiện thu hồi ngoại lệ và lịch retest.

Ngoại lệ được chấp thuận là **rủi ro được chấp nhận có điều kiện**, không phải PASS kỹ thuật. Kết luận cần phản ánh đúng trạng thái đó.

## 15. Mẫu hồ sơ đánh giá assurance

~~~yaml
assessment_id: "LI-ASSESS-2026-11-028"
control_id: "LI-06"
control_name: "Cryptographic integrity of log segments"
assessed_at: "2026-11-28T10:00:00Z"
scope:
  environment: "production"
  source_id: "payments-api/prod"
  segment_range: "2026-11-28T07:00Z/2026-11-28T08:00Z"
  expected_segments: 12
baseline_version: "log-integrity-baseline-v2"
method:
  - "Verify manifest signature using trusted public key"
  - "Compare SHA-256 digests of segments"
  - "Check independent checkpoints and sequence coverage"
evidence:
  - type: "export"
    reference: "evidence/LI-06/segments-manifest.json"
  - type: "signature-verification"
    reference: "evidence/LI-06/verify-signature.json"
  - type: "sequence-check"
    reference: "evidence/LI-06/sequence-report.json"
result: "PASS_WITH_SCOPE"
limitations:
  - "Chỉ đánh giá nguồn payments-api/prod trong kỳ được nêu"
  - "Không chứng minh tính trung thực của nguồn ở thời điểm tạo log"
assessor: "security-assurance-team"
~~~

Mọi giá trị là dữ liệu giả định. **PASS_WITH_SCOPE** là nhãn minh họa; một hệ thống thực cần định nghĩa thống nhất PASS, FAIL, NOT_APPLICABLE, INCONCLUSIVE và tình trạng ngoại lệ. Bản ghi finding nên có finding ID, nguồn, control, evidence, mức rủi ro, owner, deadline, biện pháp sửa và bằng chứng **retest**. Không đóng finding chỉ dựa trên việc ticket được đổi trạng thái.

## 16. Nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| "Đã dùng HTTPS thì log không thể bị sửa." | TLS chỉ bảo vệ chặng truyền; endpoint, collector hoặc kho vẫn có thể bị can thiệp. |
| "Checksum khớp chứng minh log đầy đủ." | Hash kiểm tra tập hiện có; sequence/checkpoint mới hỗ trợ phát hiện phần thiếu. |
| "Checksum đặt cạnh log đủ để chống sửa." | Bên có quyền ghi cả hai có thể tạo lại checksum. |
| "Đã ký log nghĩa là event chắc chắn đúng." | Chữ ký gắn với bên ký, nguồn có thể đã bị kiểm soát trước đó. |
| "Encryption at rest tương đương WORM." | Mã hóa và quyền sửa/xóa là hai vấn đề khác nhau. |
| "Retention đã bật thì tất cả log được bảo vệ." | Cần xác minh đúng object, thời điểm áp policy, quyền cao và đường thu thập. |
| "Timestamp tăng dần nghĩa là thứ tự chính xác." | Clock drift và hệ phân tán có thể làm sai thứ tự. |
| "SIEM đang nhận event nghĩa là không mất dữ liệu." | Cần giám sát buffer, drop, gap, heartbeat và checkpoint. |
| "Log được normalize nên hash bắt buộc phải giống raw." | Byte representation có thể thay đổi hợp lệ; phải định nghĩa đối tượng được ký. |
| "Khôi phục từ backup nghĩa là nguyên vẹn." | Phải đối chiếu hash/signature/checkpoint với mốc tin cậy. |
| "Finding đóng do đã sửa cấu hình." | Cần thực hiện retest trên trạng thái thực và giữ bằng chứng. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** File audit.log và file checksum.sha256 nằm cùng thư mục, cùng một admin có thể sửa. Hash khớp có đủ chứng minh không ai đã sửa log?

**Gợi ý:** Không. Admin có thể thay cả file và checksum. Cần manifest được ký hoặc mốc hash được bảo vệ độc lập.

**Câu 2.** Một batch log đã có chữ ký số hợp lệ nhưng ứng dụng bị chiếm trước lúc ký. Có thể khẳng định sự kiện đúng thực tế không?

**Gợi ý:** Không. Chữ ký gắn với khóa/hệ thống ký trong mô hình tin cậy, chưa chứng minh sự kiện phát sinh trung thực. Cần nguồn audit độc lập.

**Câu 3.** Vì sao hash chain cần checkpoint độc lập theo kỳ?

**Gợi ý:** Nếu tất cả log/hash đều do cùng người sửa được, attacker có thể tái tính chuỗi hoặc cắt phần đuôi. Checkpoint độc lập và heartbeat giúp phát hiện thay đổi lịch sử hoặc mốc bị thiếu.

**Câu 4.** Kho WORM chứa đầy đủ những file đã nhận, nhưng collector làm rơi 200 event trước đó. Control nào chưa đạt?

**Gợi ý:** Retention có thể PASS trong phạm vi file đã lưu, nhưng delivery/completeness không đạt. Cần tìm dropped counter, sequence gap và các nguồn đối soát.

**Câu 5.** Vì sao event_id quan trọng trong mô hình at-least-once?

**Gợi ý:** Retry có thể giao trùng event. Event ID hỗ trợ phát hiện/deduplicate và ngăn nhầm một sự kiện thành nhiều thao tác thật.

**Câu 6.** Một hệ thống đặt log có dữ liệu cá nhân trong retention lock 10 năm. Cần kiểm tra thêm yếu tố gì?

**Gợi ý:** Pháp lý và chính sách dữ liệu áp dụng, mục đích thu thập, tối thiểu hóa trường, quyền đọc, xử lý dữ liệu nhạy cảm, cách hết hạn/xóa hợp lệ và hậu quả của khóa khó đảo ngược.

## 18. Checklist triển khai log integrity assurance

- [ ] Có inventory đầy đủ nguồn log, owner, phân loại và nhóm sự kiện bắt buộc.
- [ ] Có schema event, ID, source, timestamp, correlation ID và tránh log injection.
- [ ] Producer/agent/collector có xác thực, đường truyền bảo vệ và quyền tối thiểu.
- [ ] Có buffer, acknowledgement, retry và metrics thất thoát với cảnh báo có người nhận.
- [ ] Có sequence/event ID, kiểm soát duplicate, replay, gap và missing heartbeat.
- [ ] Có hash/HMAC/chữ ký trên đối tượng xác định rõ, canonicalization và quản lý khóa.
- [ ] Có checkpoint độc lập, phát hiện cắt đuôi và mất kỳ.
- [ ] Có immutable evidence store/retention với chính sách dữ liệu phù hợp.
- [ ] Tách quyền của application operator, collector, auditor, storage admin và key admin.
- [ ] Có đồng bộ thời gian, event/receive/ingest time và giám sát clock drift.
- [ ] Có test âm cho sửa byte, xóa segment, mất checkpoint và quyền xóa trái phép.
- [ ] Có đối soát từ nguồn độc lập để phát hiện dữ liệu không được ghi hoặc chuyển.
- [ ] Có chain of custody, record xuất bằng chứng và khả năng xác minh sau restore.
- [ ] Có finding owner, hạn xử lý, ngoại lệ có thời hạn và chứng cứ retest.
- [ ] Báo cáo thể hiện đúng phạm vi, độ bao phủ, trust assumption và giới hạn kết luận.

## Kết luận

Log integrity là khả năng phát hiện hoặc ngăn thay đổi trái phép đối với dữ liệu nhật ký trong một mô hình tin cậy đã định. Nhưng để log đáng tin cho monitoring, điều tra và audit, còn cần bảo vệ **tính đầy đủ, xác thực nguồn, thời gian, thứ tự, quyền truy cập và chuỗi quản lý chứng cứ**. Hash, chữ ký, checkpoint, immutable storage, phân tách quyền và đối soát độc lập giải quyết các mắt xích khác nhau, không thay thế lẫn nhau.

Trong chương trình **SECURITY_SECURITY_ASSURANCE**, kết luận "log đáng tin cậy" chỉ có giá trị khi gắn với **nguồn cụ thể, loại sự kiện, khoảng thời gian, control, phép kiểm, bằng chứng và giới hạn rõ ràng**. Khi việc xác minh được đưa vào vận hành liên tục và mỗi finding được khắc phục, retest, tổ chức mới có khả năng sử dụng log như nền tảng bằng chứng đáng tin cho quyết định bảo mật.

