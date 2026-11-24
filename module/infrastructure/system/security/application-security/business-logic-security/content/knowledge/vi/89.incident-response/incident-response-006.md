# Bảo toàn chứng cứ khi ứng phó sự cố nghiệp vụ (Evidence preservation)

Một đơn hàng bị sửa giá, một bước phê duyệt bị bỏ qua hoặc hai khoản thu xuất hiện cho cùng nghĩa vụ thanh toán thường để lại dấu vết ở nhiều nơi: audit nghiệp vụ, database, hệ thống quyền, idempotency store, outbox và bên thanh toán. Nếu đội vận hành sửa ngay trạng thái đơn, xóa request trùng hoặc chạy lại worker mà không ghi nhận, các dấu vết cần để giải thích sự cố có thể mất hoặc bị trộn với hành động khắc phục.

Trong chương **Incident Response** của module Business Logic Security, evidence preservation là bảo toàn **nội dung, ngữ cảnh, tính toàn vẹn và nguồn gốc** của dữ liệu liên quan đến sự cố. Mục tiêu là xác định quy tắc nghiệp vụ nào bị vi phạm, ảnh hưởng đến đối tượng nào và điều gì đã thực sự xảy ra trước khi quyết định khôi phục, bù hoặc sửa hệ thống.

## 1. Bảo toàn chứng cứ phải giúp trả lời câu hỏi nghiệp vụ

Một gói log lớn chưa chắc đủ để điều tra. Với thao tác xác nhận đơn, cần trả lời được:

- Ai hoặc service nào yêu cầu hành động, thuộc tenant nào và tác động lên đối tượng nào?
- Quyền nào được đánh giá tại thời điểm đó, dựa trên policy và dữ liệu nào?
- Phiên bản nội dung nào đã được duyệt, ai duyệt và giá có hiệu lực là bao nhiêu?
- Chuyển trạng thái nào được yêu cầu, chuyển nào đã commit và chuyển nào chỉ mới được ghi trong log?
- Những request khác nhau có cùng một ý định hay là những nghĩa vụ khác nhau?
- Khoản thu hoặc refund nào thực sự có hiệu lực bên ngoài database?
- Những thay đổi nào do người ứng phó thực hiện sau khi phát hiện sự cố?

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong bài | Ví dụ |
|---|---|---|
| Artifact | Một đơn vị dữ liệu được thu nhận và định danh | File export audit, snapshot các hàng liên quan, phản hồi tra cứu provider |
| Provenance | Nguồn gốc và cách dữ liệu được tạo, thu nhận, xử lý | Export từ cluster nào, bằng tài khoản nào, truy vấn gì, lúc nào |
| Integrity | Khả năng phát hiện dữ liệu đã thay đổi so với mốc được tin cậy | So sánh SHA-256 khi thu nhận và khi bàn giao |
| Chain of custody | Nhật ký kiểm soát, chuyển giao và truy cập chứng cứ | Người thu nhận bàn giao EV-004 cho người phân tích, có xác minh digest |
| Working copy | Bản dùng để tìm kiếm, giải mã hợp lệ, phân tích hoặc dựng timeline | Bản log đã parse thành bảng, có liên kết về artifact nguồn |
| Retention | Chính sách thời gian lưu và điều kiện được xóa | Giữ gói sự cố theo quyết định đã ghi nhận, thay vì để TTL thông thường xóa mất |

Mức thủ tục bàn giao tùy loại sự cố và chính sách tổ chức. Không phải mọi sự cố đều cần quy trình thu chứng cứ hình thức như nhau, nhưng dữ liệu và hành động điều tra vẫn cần được bảo vệ về tính toàn vẹn, nguồn gốc và quyền truy cập. Đây cũng là nội dung của RS.AN-06 và RS.AN-07 trong [NIST SP 800-61 Rev. 3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf).

### 1.2. Chứng cứ có giới hạn

Hash đúng không chứng minh sự kiện trong file là sự thật. Một file giả cũng có hash hợp lệ. Một export nguyên vẹn vẫn có thể thiếu trang, thiếu tenant hoặc lấy từ replica chưa cập nhật.

Do đó phải tách ba nhận định:

```text
File này không đổi kể từ mốc thu nhận đã xác minh.
File này đến từ nguồn được xác định bằng quy trình đã ghi nhận.
Nội dung file đủ và đáng tin đến mức nào để hỗ trợ một kết luận cụ thể.
```

Không biến một trong ba nhận định thành bằng chứng thay cho hai nhận định còn lại.

## 2. Tình huống xuyên suốt và bản đồ chứng cứ

Giả sử đội vận hành nhận phản ánh về đơn ORD-742 của tenant T1:

- Nội dung được cho là đã duyệt có version 7 và tổng tiền 195.000 VND.
- Có request xác nhận gửi giá 19.500 VND từ client.
- Client bị timeout rồi gửi thêm request với idempotency key khác.
- Người dùng phản ánh có hai khoản thu.
- Trạng thái hiện tại của đơn là PAID, nhưng chưa rõ lần chuyển nào tạo ra nó.

Đây là **tình huống giả định để học**. Phản ánh, request body và trạng thái hiện tại là đầu mối; chưa đủ để kết luận đã có hành vi gian lận hoặc đã thu tiền hai lần.

Các invariant cần kiểm chứng trong mô hình:

```text
I1: Số tiền được thu phải khớp nội dung có hiệu lực đã được server chấp nhận.
I2: Nội dung được xác nhận phải có phê duyệt hợp lệ cho đúng phiên bản.
I3: Caller phải có quyền thực hiện hành động trên đúng order và tenant.
I4: Một nghĩa vụ thanh toán trong luồng mẫu có tối đa một khoản thu hợp lệ.
I5: Chuyển PAID phải có bằng chứng thanh toán hợp lệ theo state machine.
```

Nếu có quy trình điều chỉnh giá, duyệt lại hoặc thanh toán nhiều đợt, phải đưa các quy tắc đó vào mô hình trước khi so sánh. Không mặc định mọi chênh lệch là vi phạm.

| Câu hỏi điều tra | Nguồn cần bảo toàn | Ngữ cảnh không được bỏ mất |
|---|---|---|
| Giá nào được duyệt? | Phiên bản order/quote, approval record, lịch sử chỉnh sửa | Amount, currency, đơn vị tiền, version, thời hạn và quy tắc điều chỉnh |
| Caller có quyền không? | Quyết định authorization, membership/role/policy history | Principal, tenant, object, action, policy version, quyền ủy quyền nếu có |
| Request đã được chấp nhận thế nào? | Gateway log và audit ứng dụng | Request ID, dữ liệu đã chuẩn hóa, giá server, outcome, app version |
| Có bỏ qua bước không? | Transition audit, order history, operation | Trạng thái trước/sau, version, điều kiện guard, thời điểm commit có thể xác minh |
| Retry có tạo ý định mới không? | Idempotency mapping, fingerprint, operation và retry metadata | Scope key, TTL, operation ID, conflict/replay decision, external key reference |
| Sự kiện nào đã được phát? | Outbox, inbox, broker metadata, consumer audit | Event ID, payload/version, publish/ACK/redelivery, worker attempt |
| Có bao nhiêu khoản thu thực tế? | Provider transaction/ledger, callback và kết quả tra cứu | Provider account, effect ID, amount, currency, trạng thái capture/void/refund |
| Dữ liệu đã thay đổi sau khi phát hiện chưa? | Nhật ký ứng phó, DB/admin audit, deployment/config history | Người thao tác, thời điểm, lý do, command/query, trước và sau thay đổi |

Trạng thái hiện tại của bảng order không thay thế lịch sử. Quyền hiện tại của người dùng cũng không chứng minh quyền của họ tại thời điểm request được xử lý.

## 3. Hành động ban đầu: giữ dấu vết trong khi ngăn thiệt hại

### 3.1. Ghi nhận điểm bắt đầu và phạm vi

Tạo case ID và ghi thời điểm phát hiện theo UTC, nguồn cảnh báo, đối tượng nghi vấn, người phụ trách và mức khẩn cấp. Phân biệt thời điểm phát hiện với thời điểm sự kiện có thể đã bắt đầu.

Phạm vi ban đầu nên có tenant, object/operation ID, khoảng thời gian và thành phần liên quan. Bắt đầu từ ORD-742 không có nghĩa chắc chắn chỉ một đơn bị ảnh hưởng; mở rộng theo chứng cứ và invariant, đồng thời ghi phiên bản phạm vi truy vấn.

### 3.2. Phối hợp containment với preservation

Containment có thể cần khóa chức năng xác nhận đơn bị lỗi, giới hạn endpoint, chặn thao tác mới của principal hoặc dừng một worker cụ thể. Ghi rõ ai quyết định, thay đổi nào được thực hiện và tác động lên dữ liệu/tiến trình.

Nếu cần ngăn thiệt hại đang diễn ra, không chờ thu nhận hoàn hảo mọi artifact mới hành động. Khi có thể, thực hiện song song việc giữ dấu vết và containment; nếu phải ưu tiên một hành động khẩn cấp, ghi dữ liệu có thể mất và lý do lựa chọn.

Không dừng toàn bộ callback/reconciliation mà bỏ quên nghĩa vụ thanh toán chưa rõ kết quả. Chặn tạo nghĩa vụ mới và tiếp tục đối soát nghĩa vụ đã tồn tại có thể là hai quyết định vận hành khác nhau.

### 3.3. Ưu tiên theo nguy cơ mất dữ liệu

| Dấu vết | Nguy cơ | Hành động bảo toàn phù hợp |
|---|---|---|
| Request/trace có thời gian lưu ngắn | Sampling, rotation, agent restart | Export hoặc giữ lại partition/object liên quan; ghi rõ mức sampling và khả năng thiếu |
| Idempotency/cache/lease | TTL, eviction, worker cập nhật | Thu nhận value liên quan, scope, TTL còn lại và thời điểm đọc |
| Outbox/inbox/queue | Cleanup, ACK, retry thay đổi metadata | Giữ bản ghi liên quan và metadata trước khi cleanup; tránh thao tác consume có tác dụng phụ |
| Dữ liệu nghiệp vụ | Tiếp tục được user/worker cập nhật | Snapshot nhất quán hoặc export có mốc phiên bản rõ ràng |
| Audit quyền, feature flag, deployment | Cấu hình bị thay bởi containment/hotfix | Lưu phiên bản và lịch sử liên quan trước hoặc đồng thời với thay đổi |
| Dữ liệu provider | Cửa sổ truy vấn/export, trạng thái cập nhật về sau | Thu nhận các effect liên quan và ghi thời điểm quan sát; bổ sung các lần đối soát sau |
| Dữ liệu volatile trong tiến trình | Mất khi restart hoặc scale down | Cân nhắc người có chuyên môn thu nhận đúng phạm vi khi cần; ghi tác động của thao tác |

Không có thứ tự cố định phù hợp mọi kiến trúc. Dựa vào độ biến động, giá trị điều tra, tác động vận hành và khả năng thu nhận an toàn. Không mặc định dump toàn bộ bộ nhớ hoặc database cho mọi lỗi nghiệp vụ.

### 3.4. Ghi mọi hành động làm thay đổi hiện trường

Trước khi sửa trạng thái, chạy refund, replay outbox hoặc triển khai hotfix, ghi các artifact đã có và trạng thái liên quan. Sau hành động, ghi kết quả và định danh hiệu lực mới.

```text
03:14:10Z: xác nhận giữ lại audit partition liên quan.
03:14:22Z: ngăn tạo confirmation mới cho luồng bị ảnh hưởng.
03:15:08Z: thu nhận snapshot operation và reservation.
03:18:40Z: khởi động lại worker để đối soát operation đã có.
03:20:12Z: nhận kết quả tra cứu provider; lưu thành artifact mới.
```

Các thời điểm trên chỉ minh họa cách ghi, không phải lịch bắt buộc. Không sửa lại timestamp trong log gốc để làm nó khớp với biên bản.

## 4. Giữ đủ ngữ cảnh của quyết định nghiệp vụ

### 4.1. Định danh để nối các nguồn

Request ID thường định danh một lần gọi; operation ID định danh ý định nghiệp vụ có thể sống qua nhiều request. Event ID định danh sự kiện logic; provider effect ID định danh khoản thu/hoàn thực tế. Các định danh này không hoán đổi cho nhau.

Một chuỗi liên kết mong muốn:

```text
tenant + order/version + approval
    -> request ID + authorization decision
    -> operation ID + idempotency scope/fingerprint
    -> outbox event ID + worker attempt
    -> provider account + payment/capture effect ID
    -> callback event ID + local transition
```

Một request có thể tạo nhiều event và một operation có thể được gọi lại nhiều lần. Nhiều log có cùng operation ID không tự chứng minh thu trùng; cần đếm hiệu lực theo semantics nghiệp vụ.

### 4.2. Ví dụ event quyết định đã chấp nhận

Ví dụ JSON sau mô tả cấu trúc audit mong muốn với dữ liệu giả. Đây là event của một lần chấp nhận hợp lệ để minh họa các trường cần có, không phải kết luận về ORD-742 trong tình huống nghi vấn.

```json
{
  "schema_version": 1,
  "event_id": "AUD-901",
  "event_type": "order.confirmation.accepted",
  "event_time": "2026-11-23T03:00:01.230Z",
  "ingested_at": "2026-11-23T03:00:01.900Z",
  "service": "order-service",
  "deployment_id": "release-42",
  "request_id": "REQ-81",
  "tenant_id": "T1",
  "actor": {
    "principal_id": "USER-A",
    "kind": "user"
  },
  "target": {
    "order_id": "ORD-EXAMPLE",
    "version_before": 7,
    "version_after": 8
  },
  "authorization": {
    "action": "order.confirm",
    "decision": "ALLOW",
    "policy_version": "policy-12",
    "decision_id": "AUTHZ-31"
  },
  "business_context": {
    "approval_id": "APR-70",
    "approved_version": 7,
    "requested_amount": 195000,
    "authoritative_amount": 195000,
    "currency": "VND",
    "amount_unit": "VND_integer"
  },
  "operation_id": "OP-63",
  "idempotency": {
    "scope_id": "T1:USER-A:order.confirm",
    "key_ref": "KEYREF-14",
    "fingerprint_ref": "FPREF-20",
    "decision": "CREATED"
  },
  "transition": {
    "from": "APPROVED",
    "to": "PAYMENT_PENDING",
    "commit_outcome": "CONFIRMED"
  }
}
```

Trong thiết kế này, event “accepted” chỉ được công bố từ dữ liệu đã commit, chẳng hạn qua audit/outbox ghi cùng transaction. Nếu log được ghi trước commit, phải gọi đúng nghĩa là attempted hoặc pending và có bằng chứng riêng về outcome. Dòng log “success” do code chạy tới cuối hàm chưa chắc chứng minh database đã commit.

`key_ref` và `fingerprint_ref` là tham chiếu minh họa tới dữ liệu được kiểm soát. Nếu dùng giá trị băm/HMAC để liên kết, cần ghi scheme, scope và phiên bản khóa phù hợp; không biến một tham chiếu không thể tra cứu thành “bằng chứng chống trùng”.

### 4.3. Chứng cứ quyền phải có chiều thời gian

Đối với thao tác phê duyệt hoặc hoàn tiền, bảo toàn principal đã xác thực, service đại diện nếu có, tenant, target, action và quyết định authorization. Thu nhận policy/rule version và các thuộc tính quan trọng thực sự đã được dùng để quyết định.

Một role name trong log không đủ nếu role đã bị đổi quyền hoặc caller còn có điều kiện theo đối tượng. Cần phân biệt quyền tổng quát `refund:create` với điều kiện chỉ được refund đơn thuộc tenant và hạn mức được giao.

Log ghi actor USER-A chỉ chứng minh hệ thống đã gắn thao tác với định danh đó trong ngữ cảnh được thu nhận. Việc quy kết một con người cụ thể còn cần chứng cứ khác; IP hoặc tên tài khoản không tự giải quyết khả năng chiếm phiên, ủy quyền hoặc tài khoản dùng chung.

## 5. Thu nhận dữ liệu mà không tạo lịch sử giả

### 5.1. Ghi phương pháp trước khi export

Mỗi lượt thu nhận cần ghi nguồn, tài khoản/quyền dùng để đọc, thời điểm bắt đầu/kết thúc, công cụ/phiên bản, query/filter, tham số, timezone, pagination và giới hạn kết quả. Không đặt credential vào query text hoặc manifest.

Phân biệt rõ:

- Bản export từ nguồn tại thời điểm thu nhận.
- Bản snapshot/backup với mốc phục hồi xác định.
- Kết quả truy vấn đã lọc.
- Bản dữ liệu được parse, chuẩn hóa, khử định danh hoặc tổng hợp.

Mỗi loại hỗ trợ một mức kết luận khác nhau. Export đã lọc không phải ảnh đầy đủ của hệ thống, kể cả khi bản export được giữ nguyên byte.

### 5.2. Database: snapshot nhất quán và phạm vi liên quan

Khi cần so sánh order, approval, operation, reservation và outbox, ưu tiên cơ chế đọc nhất quán hoặc snapshot do hệ thống hỗ trợ. Ghi cluster/database, nguồn primary hay replica, mốc snapshot/backup và độ trễ đã biết.

Mã giả cho một lượt export:

```text
mở phiên đọc nhất quán theo cơ chế của database
ghi nhận mốc snapshot và thời gian quan sát

export order của tenant T1, id ORD-742
export các version/approval liên quan tới order đó
export operation và idempotency mapping liên quan
export reservation, payment record, outbox/inbox liên quan
export audit quyền và transition trong phạm vi đã định nghĩa

ghi số hàng, khóa liên kết và hạn chế truy vấn
kết thúc phiên đọc
```

Không giả định `READ ONLY` tự tạo ra cùng một snapshot cho mọi câu truy vấn; điều đó còn tùy isolation và hệ quản trị. Tránh giữ transaction đọc dài tùy tiện vì có thể ảnh hưởng tài nguyên vận hành.

Một snapshot database không tạo snapshot nguyên tử với broker hoặc provider. Ghi riêng thời điểm thu nhận từng nguồn và trạng thái có thể đang thay đổi. Nếu cần đối chiếu ở mốc lịch sử, dùng lịch sử/audit hoặc bản phục hồi được quản lý, không lấy trạng thái hiện tại rồi gán cho quá khứ.

### 5.3. Logs và message: kiểm tra phần bị bỏ sót

Một truy vấn theo khoảng thời gian nên ghi rõ biên đóng/mở, ví dụ `[03:00:00Z, 03:30:00Z)`, trường thời gian được lọc và query version. Nếu sự kiện được gửi trễ, lọc chỉ theo ingestion time có thể khác với lọc theo event time.

Khi export qua API có pagination:

1. Ghi điều kiện truy vấn và giới hạn kích thước mỗi trang.
2. Thu nhận đủ trang theo cơ chế của nguồn, ghi token/mốc phân trang cần thiết trong vùng kiểm soát.
3. Ghi số trang, số record, lỗi/timeout và dấu hiệu truncation.
4. Xác định nguồn có bảo đảm snapshot ổn định trong quá trình phân trang hay không.
5. Nếu phải đọc chồng lấn để tránh mất record, giữ ID và quy tắc dedup ở bản phân tích; không xóa âm thầm record nguồn.

Mở rộng từ ID liên quan, không chỉ từ timestamp: approval có thể nằm trước cửa sổ, callback hoặc refund nằm sau cửa sổ. Ghi artifact bổ sung và lý do mở rộng, thay vì trộn vào file cũ rồi giữ nguyên tên/hash.

Không gọi API dequeue/ACK/replay chỉ để “xem message” nếu thao tác đó làm thay đổi hàng đợi hoặc tạo hiệu lực. Chọn khả năng đọc/export phù hợp; nếu không thể tránh tác động, ghi rõ trạng thái trước và sau cùng giới hạn của việc thu nhận.

### 5.4. Provider: phân biệt dấu vết gửi và hiệu lực thực tế

Giữ request/operation reference, provider account, effect ID, amount, currency, trạng thái và thời điểm tra cứu. Nếu dữ liệu được trả qua nhiều lượt hoặc có độ trễ quan sát, ghi lại hạn chế đó.

Callback được nhận hai lần có thể là cùng một event được giao lại. Hai effect ID khác nhau cần được kiểm tra semantics: authorization, capture, void và refund không phải cùng một loại hiệu lực. Hai notification cũng không đồng nghĩa hai lần thu.

Một request trả timeout không chứng minh chưa thu tiền. Không tạo request thanh toán mới để “thử xem hệ thống có hoạt động không” trên đơn đang điều tra; hành động đó có thể thay đổi chính đối tượng cần xác minh.

Nếu cần bảo toàn chữ ký webhook, giữ dữ liệu cần thiết cho việc xác minh theo đúng giao thức: representation của payload, header chữ ký, thời điểm/phiên bản cấu hình xác minh và kết quả đã quan sát. Không lưu signing secret trong gói chứng cứ. Bản JSON được parse rồi serialize lại có thể không còn là byte sequence ban đầu được ký.

## 6. Giữ tính toàn vẹn và nguồn gốc sau thu nhận

### 6.1. Tách bản thu nhận và bản làm việc

Sau thu nhận, lưu artifact trong vùng kiểm soát truy cập phù hợp. Tính digest cho đúng byte sequence đã lưu, xác minh sau khi chuyển vào kho, ghi manifest và giữ bản baseline của manifest ở nơi được bảo vệ độc lập với quyền sửa artifact.

Một tổ chức thư mục minh họa:

```text
IR-2026-017/
    acquired/       các artifact thu nhận, không sửa tại chỗ
    manifests/     phiên bản manifest và thông tin xác thực đi kèm
    custody/       nhật ký bàn giao, truy cập, thay đổi quyền
    working/       bản parse, kết quả truy vấn phân tích
    reports/       timeline, kết luận, giới hạn và tham chiếu artifact
```

Đây là mô hình tổ chức dữ liệu, không phải bảo đảm bảo mật từ tên folder. Phải có kiểm soát truy cập, mã hóa khi phù hợp, audit và chính sách lưu/xóa thực tế.

Nếu dùng object storage hỗ trợ versioning hoặc retention/immutability, ghi object version và cấu hình liên quan. Versioning riêng lẻ không bảo đảm không ai xóa được mọi phiên bản; cờ read-only của file cũng không ngăn người có quyền quản trị sửa dữ liệu.

### 6.2. Hash đúng byte sequence

Ví dụ PowerShell sau chỉ minh họa tính SHA-256 cho một artifact đã thu nhận:

```powershell
Get-FileHash -LiteralPath 'D:\IncidentEvidence\IR-2026-017\acquired\EV-004-provider-export.json' -Algorithm SHA256
```

Ghi thuật toán, digest, kích thước byte và artifact ID trong manifest. Thực hiện lại phép tính trên phía nhận hoặc trên bản sao để đối chiếu với baseline được tin cậy.

Đổi encoding, newline, thứ tự field JSON hoặc cách nén làm thay đổi byte sequence và digest. Nếu cần biến đổi để phân tích, tạo artifact dẫn xuất có ID/hash mới và liên kết về nguồn, không cập nhật hash cũ để làm như chưa có thay đổi.

Hash không có khóa có thể phát hiện khác biệt khi có baseline đáng tin. Nếu người tấn công sửa được cả file lẫn manifest và baseline, việc “hash khớp” không còn đủ. Chữ ký số, mốc thời gian tin cậy hoặc cơ chế ghi độc lập có thể tăng khả năng kiểm chứng, tùy threat model và cách bảo vệ khóa/quyền.

### 6.3. Giữ cả công cụ đọc và bối cảnh giải thích

Một file còn nguyên nhưng không biết schema hoặc đơn vị tiền vẫn khó dùng. Bảo toàn schema version, mô tả trường, app/deployment version, policy/config liên quan, timezone và phiên bản công cụ cần để đọc dữ liệu.

Không phải artifact nào cũng là bit-for-bit image của nguồn. Với dữ liệu cloud/API, cần mô tả đúng đây là export/response được thu nhận bằng phương pháp nào. [NIST SP 800-86](https://nvlpubs.nist.gov/nistpubs/legacy/sp/nistspecialpublication800-86.pdf) phân biệt thu thập, examination, analysis và reporting; việc tạo bản phân tích cần giữ liên kết và tính toàn vẹn của dữ liệu đã thu nhận.

## 7. Manifest và nhật ký bàn giao

### 7.1. Manifest mô tả chính xác thứ đã được thu nhận

Manifest không chỉ là danh sách file. Nó phải giúp người khác kiểm tra nguồn, cách lấy, phạm vi, byte sequence, giới hạn và quan hệ giữa các artifact.

Ví dụ dưới là template với dữ liệu giả. Các giá trị trong dấu `<...>` là chỗ phải điền sau thu nhận thực tế, không phải digest hay định danh đã được xác minh.

```json
{
  "manifest_version": 1,
  "case_id": "IR-2026-017",
  "artifact_id": "EV-004",
  "description": "Provider export for payment effects related to ORD-742",
  "source": {
    "system": "payment-provider",
    "environment": "production",
    "account_ref": "PROVIDER-ACCOUNT-1",
    "source_reference": "<export-job-or-query-reference>"
  },
  "collection": {
    "collector_id": "RESPONDER-02",
    "started_at": "2026-11-23T03:20:00Z",
    "completed_at": "2026-11-23T03:20:09Z",
    "method": "read-only provider export",
    "tool_version": "<collector-and-version>",
    "query_reference": "QUERY-004",
    "scope": {
      "tenant_id": "T1",
      "order_id": "ORD-742",
      "operation_ids": ["OP-63", "OP-64"],
      "filter_time_field": "provider_created_at",
      "window_start_inclusive": "2026-11-23T02:50:00Z",
      "window_end_exclusive": "2026-11-23T03:30:00Z"
    },
    "page_count": 1,
    "record_count": 2,
    "truncation_observed": false
  },
  "stored_artifact": {
    "file_name": "EV-004-provider-export.json",
    "media_type": "application/json",
    "byte_length": 18432,
    "digest_algorithm": "SHA-256",
    "digest": "<64-hex-characters-computed-from-stored-bytes>",
    "storage_version_ref": "<protected-object-version>"
  },
  "limitations": [
    "Export is provider data as observed during collection, not a cross-system snapshot",
    "An empty result outside the query scope has not been established"
  ]
}
```

`record_count` và `byte_length` trong ví dụ là số minh họa. Khi triển khai, lấy từ dữ liệu thực; không điền số mong đợi để làm manifest trông hoàn chỉnh.

Query/filter chi tiết có thể nằm trong artifact riêng với quyền truy cập tương ứng, rồi được tham chiếu từ manifest. Nếu query chứa dữ liệu nhạy cảm, bảo vệ nó như dữ liệu sự cố; không bỏ tham số đến mức không thể hiểu phạm vi đã thu nhận.

### 7.2. Không tạo vòng lặp hash

Danh sách digest trong manifest áp dụng cho artifact được liệt kê. Không yêu cầu manifest chứa hash của chính byte sequence đầy đủ của nó, vì thêm digest sẽ lại thay đổi byte sequence đó.

Một phương án là chốt manifest rồi lưu digest/chữ ký của manifest trong record riêng ở hệ thống được bảo vệ. Mỗi lần bổ sung artifact, tạo manifest version mới và liên kết phiên bản trước. Không sửa manifest cũ và giả như nó đã mô tả dữ liệu mới từ đầu.

### 7.3. Nhật ký chuyển giao và truy cập

Tùy chính sách, nhật ký có thể do hệ thống quản lý chứng cứ hoặc cơ chế audit phù hợp tạo ra. Các trường hữu ích gồm:

| Trường | Nội dung cần ghi |
|---|---|
| Case/artifact ID | Định danh ổn định của dữ liệu được thao tác |
| Thời điểm | Thời điểm UTC và nguồn thời gian khi có ý nghĩa |
| Người/service thực hiện | Định danh có thể truy vết, vai trò liên quan |
| Hành động | Thu nhận, sao chép, chuyển giao, xác minh, đọc, tạo bản dẫn xuất |
| Nguồn và đích | Vị trí/object version được kiểm soát, không phải URL chứa secret |
| Mục đích và phạm vi | Vì sao cần thao tác, artifact nào được cấp quyền |
| Kết quả xác minh | Digest/size đối chiếu với baseline nào, PASS hay sai khác |
| Quan hệ dẫn xuất | Parent artifact, công cụ, phép biến đổi, output ID/hash |
| Ngoại lệ | Lỗi truyền, thiếu dữ liệu, truy cập khẩn cấp, hành động chưa xác minh được |

Nếu digest sai khi nhận, ghi sự cố, cách ly bản sai khác và bảo toàn các record liên quan để kiểm tra. Không ghi đè baseline hoặc âm thầm thay file rồi đánh dấu bàn giao thành công. Việc thu lại từ nguồn phải tạo lượt thu nhận/artifact mới có lịch sử riêng.

## 8. Dựng timeline có thể kiểm chứng

### 8.1. Phân biệt ba loại thời gian

- **Event time:** nguồn ghi sự kiện cho rằng hành động xảy ra lúc nào.
- **Ingestion/observation time:** collector hoặc hệ thống nhận quan sát được dữ liệu lúc nào.
- **Collection time:** người ứng phó thu artifact vào gói chứng cứ lúc nào.

Giữ nguyên timestamp nguồn, timezone/offset và độ phân giải; thêm cột chuẩn hóa UTC trong bản phân tích. `2026-11-23T03:00:00Z` và `2026-11-23T10:00:00+07:00` biểu diễn cùng thời điểm, nhưng không được bỏ offset rồi coi hai giá trị giờ địa phương là có thứ tự khác nhau.

Nếu một node lệch đồng hồ hoặc timestamp chỉ chính xác tới giây, ghi độ lệch/độ bất định đã biết. Không sắp xếp toàn bộ event theo timestamp rồi tuyên bố đó là thứ tự nhân quả chính xác.

### 8.2. Dùng liên kết và phiên bản để kiểm tra thứ tự

Order version, transition sequence, event ID/cause reference, outbox sequence, provider effect reference và transaction metadata có thể giúp xác định quan hệ. Phải hiểu phạm vi của từng trường: một số thứ tự chỉ có ý nghĩa trong một object, partition hoặc database.

Trace ID do client gửi có thể bị lặp hoặc giả mạo nếu hệ thống không kiểm soát. Giữ thông tin nguồn và dùng định danh server/provider có scope rõ ràng để đối chiếu; không tin mọi field chỉ vì nó xuất hiện trong log.

### 8.3. Ví dụ timeline của tình huống giả định

Giả sử sau thu nhận, các artifact riêng đã cung cấp những dữ liệu sau. Đây là phần tiếp diễn minh họa, không phải kết quả của một cuộc điều tra thực tế.

| Event time UTC theo nguồn | Artifact | Dữ liệu quan sát được | Điều hỗ trợ hoặc còn thiếu |
|---|---|---|---|
| 02:59:40 | EV-001 | Approval APR-70 gắn ORD-742 version 7, amount 195000 VND | Xác định nội dung được duyệt; cần kiểm tra thẩm quyền người duyệt và có điều chỉnh hợp lệ không |
| 03:00:01 | EV-002 | REQ-81 gửi amount 19500; audit tạo OP-63, guard ghi version 7 | Chênh lệch giữa request và nội dung duyệt; cần xác minh amount server thực sự dùng |
| 03:00:02 | EV-003 | OP-63 và PaymentRequested EVT-1 đã commit, amount 19500 | Bằng chứng cục bộ về ý định thanh toán sai khác trong mô hình chưa có điều chỉnh |
| 03:00:03 | EV-004 | Provider ghi capture CAP-1 cho OP-63, amount 19500 VND | Có một khoản thu thực tế theo trạng thái provider đã thu nhận |
| 03:00:04 | EV-002 | Gateway ghi timeout cho REQ-81 | Client có thể không biết kết quả; timeout không phủ định CAP-1 |
| 03:00:05 | EV-002, EV-003 | REQ-82 dùng key khác, tạo OP-64 cho cùng nghĩa vụ | Nghi nhánh chống trùng theo đối tượng không chặn; cần kiểm tra policy luồng và version |
| 03:00:06 | EV-004 | Provider ghi capture CAP-2 cho OP-64, cùng order/nghĩa vụ | Hai khoản thu nếu CAP-1 và CAP-2 thực sự là hai capture có hiệu lực theo hợp đồng |
| 03:14:22 | EV-005 | Đội ứng phó chặn tạo confirmation mới | Mốc hành động khắc phục; không trộn với hành vi trước phát hiện |

Cần đối chiếu các record theo ID và ngữ cảnh, không chỉ theo thời gian. Từ timeline này có thể xây dựng giả thuyết lỗi giá và tạo operation trùng; để kết luận, phải loại trừ điều chỉnh giá được phép, nghĩa vụ thanh toán khác và cách provider biểu diễn hiệu lực.

### 8.4. Phân tách fact, hypothesis và unknown

Một báo cáo nên thể hiện rõ:

```text
FACT:
    EV-004 chứa hai capture effect ID khác nhau đã có hiệu lực,
    được provider trả cho hai operation liên kết với ORD-742.

HYPOTHESIS:
    Nhánh retry với key mới đã bỏ qua ràng buộc theo nghĩa vụ thanh toán.

UNKNOWN:
    Chưa có snapshot policy/decision inputs tại thời điểm REQ-82;
    chưa xác nhận nguyên nhân chuyển quyền hoặc principal thực sự điều khiển phiên.
```

Ví dụ FACT chỉ được dùng khi semantics và liên kết của EV-004 đã được xác minh như mô tả. Nếu chưa có dữ liệu đó, ghi “người dùng phản ánh hai khoản thu” hoặc “export hiển thị hai record cần đối soát”, không nâng mức chắc chắn bằng cách đổi câu chữ.

Không tìm thấy log phê duyệt không tự chứng minh chưa từng có phê duyệt. Kiểm tra thời gian lưu, sampling, nguồn audit, sự cố pipeline và phạm vi truy vấn trước khi dùng sự vắng mặt làm bằng chứng.

## 9. Bảo vệ dữ liệu nhạy cảm trong quá trình bảo toàn

### 9.1. Thu đủ để điều tra, giới hạn người được xem

Định danh đối tượng, amount, currency, role/policy và fingerprint có thể đủ cho nhiều câu hỏi; password, access token, session cookie, signing secret hoặc toàn bộ dữ liệu thẻ thường không cần xuất hiện trong log nghiệp vụ.

Nếu artifact đã chứa dữ liệu nhạy cảm, kiểm soát truy cập và tạo bản dẫn xuất phù hợp để chia sẻ. Việc xử lý bản thu nhận gốc theo chính sách sự cố phải được ghi lại; không tự ý xóa/che đè lên bản đã chốt rồi vẫn dùng digest cũ.

Theo [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), log cần đủ ngữ cảnh sự kiện và liên kết tương tác, đồng thời xử lý dữ liệu nhạy cảm, đầu vào không tin cậy và rủi ro log injection. Trong bài này, điều đó có nghĩa cần thiết kế sẵn dữ liệu nghiệp vụ có cấu trúc, thay vì bật ghi toàn bộ request body khi sự cố xảy ra.

### 9.2. Redaction là phép biến đổi có lịch sử

Ví dụ tạo bản chia sẻ:

```text
Parent: EV-002, bản export ứng dụng đã được bảo toàn
Method: bỏ trường Authorization/Cookie; thay email bằng pseudonym ổn định
Tool/config: phiên bản bộ lọc và quy tắc được ghi nhận
Output: EV-002-R1, digest riêng, phạm vi người nhận riêng
Limitations: không dùng EV-002-R1 để xác minh chữ ký trên byte payload gốc
```

Nếu cần nối pseudonym giữa các nguồn, dùng quy tắc có scope được kiểm soát và bảo vệ mapping/khóa. Hash trực tiếp một tập giá trị dễ đoán như email hoặc mã nhân viên có thể bị dò; không mặc định “đã hash” nghĩa là đã ẩn danh.

### 9.3. Tránh làm chứng cứ thành nguồn tấn công mới

Dữ liệu thu nhận có thể chứa ký tự điều khiển, công thức bảng tính, URL hoặc nội dung thực thi. Công cụ xem/phân tích cần xử lý chúng như dữ liệu không tin cậy: encode khi hiển thị, kiểm soát việc render và không mở/chạy payload chỉ vì nó nằm trong file log.

Không sửa bản gốc để làm đầu vào “an toàn hơn” rồi mất dấu byte ban đầu. Tạo working copy đã được xử lý và ghi phương pháp, nhất là khi chuẩn hóa newline, parse JSON hoặc xuất CSV.

## 10. Kiểm thử khả năng bảo toàn trước khi có sự cố thật

Các bài kiểm tra sau nên dùng fixture và tài khoản thử nghiệm, với dữ liệu/hiệu lực được kiểm soát. Mục tiêu là chứng minh đường thu nhận và bàn giao hoạt động, không chỉ chứng minh ứng dụng có in log.

| Bài kiểm tra | Cách mô phỏng | Kỳ vọng |
|---|---|---|
| Sửa artifact sau thu nhận | Thay một byte trong working copy dùng cho phép thử xác minh | So sánh với baseline tin cậy phát hiện sai khác, không tự cập nhật digest |
| Thiếu trang export | Cho API trả nhiều trang rồi làm lỗi một trang | Gói được đánh dấu thiếu; manifest không báo thu nhận đầy đủ |
| TTL và cleanup | Tạo idempotency mapping/outbox rồi cho cleanup tới hạn | Cơ chế giữ dữ liệu sự cố hoạt động đúng scope hoặc báo rõ phần không giữ được |
| Crash sau commit | Commit operation rồi dừng tiến trình trước response | Liên kết operation/event còn truy vết được từ dữ liệu durable |
| Callback trùng | Giao lại cùng provider event ID | Timeline phân biệt redelivery với khoản thu mới |
| Thu tiền rồi timeout | Stub ghi capture trước khi cắt response | Artifact từ stub/provider và ứng dụng cho phép nhận biết kết quả cục bộ chưa rõ |
| Đồng hồ lệch | Cho một node lệch và ghi ingestion trễ | Báo cáo giữ độ bất định, không tự dựng thứ tự nhân quả sai |
| Thay quyền sau sự kiện | Thu hồi role sau thao tác thử nghiệm | Vẫn có bằng chứng policy/quyết định tại thời điểm thao tác hoặc báo thiếu |
| Truy cập sai quyền | Người không thuộc nhóm sự cố đọc/export artifact tenant khác | Bị chặn và có audit phù hợp; đường redacted export vẫn tôn trọng scope |
| Log injection | Field thử nghiệm có CR/LF và delimiter | Không tạo record giả; dữ liệu bất thường có thể phân tích an toàn |
| Hành động khắc phục | Chạy refund/recovery bằng operation riêng | Dấu vết mới phân biệt được với hiệu lực gây sự cố ban đầu |
| Bàn giao rồi đọc lại | Chuyển gói sang kho/nhóm nhận | Người nhận xác minh được digest, provenance, scope và mở được định dạng |

### 10.1. Tiêu chí đạt cho một gói chứng cứ

Gói sẵn sàng bàn giao khi người nhận có quyền có thể:

1. Xác định mỗi artifact đến từ đâu, ai thu, khi nào và bằng cách nào.
2. Kiểm tra byte sequence với baseline được bảo vệ và phát hiện sai khác.
3. Hiểu query scope, pagination, sampling, retention, khoảng trống và độ bất định thời gian.
4. Liên kết actor, target/version, approval, operation, event và hiệu lực ngoài cho các invariant đang điều tra.
5. Tái hiện các bước phân tích từ working copy mà không sửa artifact thu nhận.
6. Phân biệt fact, hypothesis, unknown và các hành động ứng phó đã làm thay đổi hệ thống.
7. Truy cập/chia sẻ theo đúng phạm vi và biết thời điểm cần rà soát retention.

Một gói có thể được bàn giao với phần thiếu nếu phần thiếu đã ghi rõ và được người phụ trách đánh giá. Không đổi “chưa thu được” thành “không có sự kiện” để vượt tiêu chí.

### 10.2. Tiêu chí chưa đạt

- Chỉ có ảnh dashboard, không có record ID/query/filter và mốc quan sát.
- Chỉ giữ log HTTP, không có phiên bản nội dung duyệt hoặc liên kết tới hiệu lực thanh toán.
- Digest khớp nhưng manifest và artifact cùng có thể bị sửa bởi tài khoản ứng dụng nghi bị xâm phạm.
- Không biết export từ primary hay replica, hoặc các trang có bị cắt không.
- File đã được che dữ liệu/chuyển encoding nhưng vẫn nhận là bản thu nhận ban đầu.
- Dữ liệu hiện tại được dùng để suy quyền hay trạng thái trong quá khứ mà không có căn cứ lịch sử.
- Replay/refund làm thay đổi dữ liệu nhưng không có nhật ký và định danh hiệu lực mới.
- Bản bàn giao không mở được hoặc không xác định được đơn vị tiền/schema.

## 11. Runbook tối thiểu cho sự cố logic nghiệp vụ

Runbook dưới đây là điểm bắt đầu để điều chỉnh cho hệ thống cụ thể, không ấn định thời hạn lưu dữ liệu hoặc thời gian xử lý chung cho mọi tổ chức.

1. **Mở case:** ghi phát hiện, phạm vi ban đầu, người phụ trách, invariant nghi vi phạm và nguồn cảnh báo.
2. **Đánh giá mất dấu vết:** xác định TTL, rotation, cleanup, trạng thái worker và nguồn nào có dữ liệu ngắn hạn.
3. **Containment có ghi nhận:** ngăn tạo thiệt hại mới, ghi thay đổi và tiếp tục xử lý nghĩa vụ pending theo quyết định đã xác định.
4. **Giữ dữ liệu liên quan:** áp dụng retention/hold theo thẩm quyền và chính sách; kiểm tra có hiệu lực thay vì chỉ ghi yêu cầu.
5. **Thu nhận có ngữ cảnh:** logs, snapshot nghiệp vụ, approval/quyền, idempotency, outbox/inbox, provider và deployment/config liên quan.
6. **Chốt artifact:** ghi byte size/digest, kiểm tra sau chuyển, lập manifest version và bảo vệ baseline cùng quyền truy cập.
7. **Phân tích trên bản sao:** dựng timeline có timezone/độ bất định; kiểm tra invariant và ghi fact/hypothesis/unknown.
8. **Ghi khắc phục:** lưu liên kết tới hotfix, recovery, refund và kết quả đối soát bằng artifact mới.
9. **Bàn giao và rà soát:** người nhận kiểm tra integrity/provenance; quyết định phạm vi bổ sung, thời điểm rà soát retention và điều kiện đóng case.

Khi hết nhu cầu giữ và đủ điều kiện theo chính sách, việc giải phóng hold/xóa dữ liệu cũng cần có quyết định và audit phù hợp. “Bảo toàn” không có nghĩa sao chép toàn bộ dữ liệu nhạy cảm rồi giữ vô thời hạn.

## 12. Bài tập áp dụng

### 12.1. Thiết kế gói chứng cứ cho ORD-742

Với tình huống ở mục 2, lập danh sách artifact cần thu cho từng invariant I1–I5. Với mỗi artifact, ghi nguồn, định danh liên kết, phương pháp thu nhận, nguy cơ mất dữ liệu và điều còn không chứng minh được từ nguồn đó.

Yêu cầu lời giải có cả dữ liệu chứng minh và dữ liệu có thể bác bỏ giả thuyết. Ví dụ, lịch sử điều chỉnh giá được duyệt lại có thể giải thích chênh lệch; callback trùng có thể giải thích nhiều notification mà không có hai khoản thu.

### 12.2. Xử lý ba biến cố khi đang điều tra

1. Idempotency mapping đã hết TTL trước khi được thu nhận. Bạn dùng nguồn nào để khôi phục liên kết, và ghi giới hạn nào nếu không thể khôi phục?
2. Người vận hành đã refund trước khi mở case. Làm sao phân biệt khoản thu ban đầu, refund khắc phục và các lần retry của refund?
3. Một artifact có digest khác baseline khi bàn giao. Bạn bảo toàn sai khác, thu lại và ghi lịch sử thế nào mà không sửa dấu vết ban đầu?

### 12.3. Đọc và đánh giá một kết luận

Nhận định sau chưa đủ căn cứ:

> Log không có APPROVED, HTTP trả 500 và hash của file log khớp, nên chắc chắn người dùng đã bỏ qua phê duyệt nhưng chưa bị thu tiền.

Hãy chỉ ra phần nào là quan sát được, phần nào là suy diễn và cần thêm nguồn nào để đánh giá. Một lời giải tốt phải nêu được giới hạn của sự vắng mặt trong log, của lỗi HTTP và của việc xác minh hash; sau đó nối chúng với approval/version, commit outcome và ledger thanh toán.
