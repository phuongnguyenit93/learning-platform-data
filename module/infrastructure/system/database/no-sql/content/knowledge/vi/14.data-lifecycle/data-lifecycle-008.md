# Độ trễ đồng bộ dữ liệu đã xóa sang chỉ mục hoặc kho dẫn xuất

## 1. Bài toán: nguồn đã xóa nhưng kết quả tìm kiếm vẫn còn

Một nền tảng xuất bản lưu bài viết trong document database, còn các thành phần khác giữ bản sao để đọc nhanh:

- **Database nguồn** quản lý nội dung, chủ sở hữu và trạng thái.
- **Search index** cho phép tìm theo từ khóa.
- **Cache** lưu nội dung chi tiết hoặc kết quả truy vấn.
- **Recommendation store** lưu danh sách bài liên quan.
- **Kho phân tích** giữ dữ liệu phục vụ báo cáo.

Lúc 10:00, tác giả xóa bài **A123**. Nguồn ghi nhận thành công và API trả “Đã xóa”, nhưng lúc 10:00:02, kết quả tìm kiếm vẫn hiện tiêu đề bài; đường xem chi tiết thậm chí có thể trả nội dung cũ từ cache.

~~~text
10:00:00.000  API nhận yêu cầu xóa A123
10:00:00.050  Database nguồn ghi DELETED thành công
10:00:00.100  API xác nhận
10:00:01.100  Search vẫn trả A123
10:00:02.000  Consumer nhận sự kiện delete
10:00:02.250  Search engine ACK thao tác xóa
10:00:03.000  Search query không còn trả A123
10:00:05.000  Cache chi tiết được vô hiệu hóa
~~~

Khoảng từ **source commit** đến khi một **đường đọc dẫn xuất không còn trả dữ liệu đã xóa** được gọi ở đây là **độ trễ lan truyền xóa** (*deletion propagation lag*). Nếu hệ có nhiều đường đọc, chúng có thể hội tụ ở những thời điểm khác nhau.

Với bài viết công khai, việc kết quả tìm kiếm chậm cập nhật vài giây có thể chỉ gây trải nghiệm không tốt. Với tài liệu mật, thông tin cá nhân hoặc thu hồi quyền, một lần trả nội dung cũ cũng có thể là vi phạm nghiêm trọng. Vì vậy, thao tác xóa cần được thiết kế theo **rủi ro nghiệp vụ**, không chỉ theo khả năng của queue hay chỉ mục.

## 2. “Đã xóa” có thể mang bốn ý nghĩa

| Mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Xóa logic ở nguồn** | Nguồn giữ trạng thái không còn hoạt động | status = DELETED, deletedAt có giá trị |
| **Không còn hiển thị/truy cập** | Các API và bản chiếu không trả nội dung trong phạm vi cần bảo vệ | Search loại A123, GET chi tiết trả 404/403 phù hợp |
| **Xóa vật lý khỏi hệ lưu đang hoạt động** | Dữ liệu hoặc segment được thu hồi bởi engine | Database loại document; index compaction/merge |
| **Xử lý bản lưu trữ dài hạn** | Log, backup, archive tuân chính sách lưu giữ và khôi phục | Backup hết retention hoặc được xử lý theo quy trình riêng |

Các mức này **không xảy ra đồng thời**. Search engine có thể không còn trả kết quả sau refresh dù những segment cũ chưa được merge. Database có thể tạo **tombstone** chứ chưa lập tức thu hồi mọi byte. CDN và browser có thể giữ response đã cache; backup tạo trước thời điểm xóa vẫn có thể chứa bản ghi.

Do đó, cam kết “xóa xong” phải trả lời: **xóa khỏi đâu, ai không còn truy cập được, tính từ thời điểm nào và bằng chứng kiểm chứng là gì?**

### 2.1. Logical delete và hard delete

Một logical delete:

~~~json
{
  "tenantId": "T01",
  "documentId": "A123",
  "status": "DELETED",
  "deletedAt": "2026-11-14T03:00:00Z",
  "revision": 17
}
~~~

Giữ trạng thái tối thiểu có thể giúp consumer biết bản ghi đã bị xóa, tránh sự kiện update cũ hồi sinh nó, phục vụ hoàn tác có kiểm soát hoặc đối soát.

**Hard delete** xóa document khỏi truy cập thông thường ở nguồn, nhưng vẫn cần xem log, backup, tombstone và các bản sao dẫn xuất. Không nên giữ toàn bộ dữ liệu nhạy cảm vô thời hạn chỉ để tiện xử lý sự kiện; nếu cần tombstone, ưu tiên **định danh và revision tối thiểu** theo chính sách lưu giữ.

### 2.2. Thu hồi quyền không đồng nghĩa xóa nội dung

Trong trường hợp thu hồi quyền:

~~~text
Document A123 vẫn tồn tại.
User U07 không còn quyền xem.
~~~

Nội dung có thể vẫn hợp lệ với người dùng khác; điều cần bảo vệ là **đường phân quyền và trả nội dung**. Ngược lại, yêu cầu loại bỏ hoàn toàn một tài liệu có thể bao gồm nhiều lớp lưu trữ hơn chỉ thay ACL.

## 3. Dữ liệu dẫn xuất tồn tại ở đâu?

~~~mermaid
flowchart TD
    S[("Source DB: A123")] --> E["Outbox / CDC"]
    E --> I["Search indexer"]
    E --> V["Vector / recommendation updater"]
    E --> W["Warehouse loader"]
    S --> C["Redis / application cache"]
    C --> CDN["CDN / edge cache"]
    I --> SI[("Full-text index")]
    V --> VI[("Embedding / recommendation store")]
    W --> DW[("Analytical tables")]
~~~

Mỗi nơi có một cơ chế xóa khác nhau:

| Nơi | Dữ liệu có thể còn | Việc cần xử lý |
| --- | --- | --- |
| Full-text index | Title, snippet, searchable document | Delete đúng ID, refresh/visibility |
| Vector index | Embedding của nhiều đoạn, metadata | Xóa mọi chunk/vector và kiểm tra filter |
| Recommendation | Candidate, danh sách bài liên quan | Bỏ ID khỏi tập gợi ý và bản precompute |
| Redis/application cache | Object hoặc cached query result | Invalidate key, phiên bản cache, TTL |
| CDN | HTML, thumbnail, file tĩnh | Purge/invalidation và cache-control phù hợp |
| Materialized view | Bản chiếu theo owner/tag/status | Xóa từ tất cả đường truy cập dẫn xuất |
| Warehouse | Snapshot, fact, aggregate, raw events | Chính sách delete/recompute và lineage |
| Event log | Payload các event cũ | Retention và hạn chế dữ liệu nhạy cảm |
| Backup/archive | Snapshot trước khi delete | Chính sách lưu giữ, restore, chống hồi sinh |

Không phải hệ nào cũng có đầy đủ các thành phần này. Bước đầu tiên là **lập sơ đồ dòng dữ liệu**, gồm những nơi chỉ lưu tiêu đề, ảnh đại diện, excerpt hoặc embedding chứ không giữ nguyên document.

## 4. Eventual consistency đối với thao tác delete

Khi nguồn ghi trước, downstream nhận thay đổi sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Source DB
    participant O as Outbox/CDC
    participant W as Worker
    participant I as Search
    C->>S: Delete A123
    S->>O: Lưu thay đổi delete
    S-->>C: Source commit thành công
    Note over C,I: Search có thể còn A123
    W->>O: Nhận DocumentDeleted
    W->>I: Delete A123
    I-->>W: Đã chấp nhận thay đổi
    Note over C,I: Sau refresh, query mới không trả A123
~~~

**Eventual consistency** chỉ cho phép các bản sao tạm thời chưa giống nguồn dưới một số điều kiện. Nó không tự bảo đảm:

- Event sẽ không bao giờ mất.
- Consumer không bao giờ xử lý sai thứ tự.
- Target đã xóa thật chỉ vì API trả ACK.
- Dữ liệu sẽ hội tụ dù pipeline lỗi vĩnh viễn.
- Những bản sao cũ không thể bị reindex/restore đưa trở lại.

Một lần delete có thể chỉ trễ vài giây trong điều kiện khỏe; nhưng khi consumer bị dừng hoặc event mất, độ trễ có thể kéo dài hàng giờ hoặc **không kết thúc**. Do đó cần cả cơ chế truyền thay đổi đáng tin, xử lý trùng, giám sát và đối soát.

## 5. Phân rã độ trễ từ nguồn tới người đọc

Ký hiệu các mốc:

~~~text
t0  source commit delete
t1  event khả dụng trong stream
t2  consumer nhận event
t3  target index xác nhận thao tác delete
t4  query target không còn trả document
t5  mọi read path liên quan đạt trạng thái yêu cầu
~~~

Với từng nhánh:

~~~text
Publish lag        = t1 - t0
Queue/consumer lag = t2 - t1
Process/write lag  = t3 - t2
Visibility lag     = t4 - t3
End-to-end lag     = t5 - t0
~~~

Một biểu thức trực giác:

\[
L_{\mathrm{delete-visible}} =
L_{\mathrm{publish}} +
L_{\mathrm{queue}} +
L_{\mathrm{process}} +
L_{\mathrm{visibility}}
\]

Biểu thức áp dụng cho **một chuỗi bước**. Nếu search, cache và warehouse cập nhật song song, thời gian hoàn thành ở **tất cả nhánh** phụ thuộc nhánh chậm nhất, chứ không phải cộng tất cả thời gian nhánh.

### 5.1. Xác nhận xóa không đồng nghĩa khả kiến ngay

Một công cụ search near-real-time có thể xác nhận delete trước khi dữ liệu không còn xuất hiện ở các truy vấn. Trong engine dựa trên segment, việc **không còn hiển thị** cũng khác với việc **dữ liệu vật lý đã được thu hồi hoàn toàn**.

Vì vậy cần định nghĩa đúng mốc đo:

- **ACK**: target xác nhận nhận/xử lý yêu cầu theo hợp đồng API.
- **VISIBLE**: query thực tế ở phạm vi đã nêu không còn trả document.
- **PHYSICAL CLEANUP**: dữ liệu được thu dọn khỏi các lớp lưu tương ứng theo chính sách engine.

Nếu SLO là “không còn xuất hiện trong search”, không nên chỉ đo thời gian tới ACK.

### 5.2. Đồng hồ và bằng chứng đo

t0 có thể do máy A ghi, t4 do máy B ghi. Nếu đồng hồ lệch, lấy hiệu timestamp có thể sai. Có thể dùng trace, đồng bộ thời gian, sequence/watermark, revision và kết quả truy vấn xác minh. Thời gian do client gửi không phải lúc nào cũng là nguồn tin cậy để tính SLA/SLO xóa.

## 6. Khi nào có thể chấp nhận độ trễ xóa?

| Tình huống | Rủi ro của bản sao cũ | Mức bảo vệ nên đánh giá |
| --- | --- | --- |
| Xóa bài nháp của tác giả | Danh sách riêng có thể hiện thêm vài giây | Xóa bất đồng bộ, phản hồi UX rõ |
| Xóa bài công khai | Search trả kết quả lỗi hoặc không còn nội dung | Event delete, lọc trạng thái và retry |
| Gỡ nội dung vi phạm | Người khác có thể tiếp tục thấy nội dung không được phép | Chặn trả nội dung qua đường có thẩm quyền |
| Thu hồi quyền tài liệu mật | Lộ thông tin trong khoảng lag | Authorization không phụ thuộc bản chiếu cũ |
| Xóa dữ liệu cá nhân theo yêu cầu | Các kho dẫn xuất hoặc bản lưu có thể giữ nội dung | Quy trình xóa đa hệ, retention và kiểm chứng |
| Xóa dữ liệu thống kê | Báo cáo có thể tạm sai | SLO hội tụ/đối soát tùy nghiệp vụ |
| Ngừng bán sản phẩm không an toàn | Search hoặc recommendation còn đề xuất | Chặn hành động ở nguồn và ưu tiên xóa bản chiếu |

**Chấp nhận eventual consistency ở search không đồng nghĩa chấp nhận truy cập trái phép.** Nếu người đã mất quyền vẫn có thể đọc nội dung bằng URL hoặc snippet, phải bảo vệ **đường thực thi quyền** chứ không chỉ đợi index cập nhật.

### 6.1. Mẫu SLO xóa có thể đo được

Ví dụ giả định:

> Trong điều kiện vận hành bình thường, 99,9% thao tác xóa bài công khai sẽ không còn xuất hiện ở kết quả tìm kiếm trong vòng 10 giây tính từ source commit. Khi quá ngưỡng, hệ phát cảnh báo và API xem chi tiết vẫn chặn tài liệu đã xóa.

**99,9% và 10 giây chỉ là số minh họa**, không phải thông số của một sản phẩm cụ thể. SLO cần làm rõ phạm vi:

- Bắt đầu từ lúc nhận request hay lúc nguồn commit?
- Kết thúc lúc target ACK hay khi query không còn trả nội dung?
- Gồm những region, tenant và read paths nào?
- Các trường hợp pending vượt deadline được tính ra sao?
- Dữ liệu có mức độ nhạy cảm khác nhau có cùng SLO không?

## 7. Làm sao bảo đảm event delete không bị bỏ lỡ?

Một lỗi phổ biến:

~~~text
1. Xóa A123 trong database -> thành công
2. Publish DocumentDeleted -> lỗi mạng
3. API đã trả success
4. Search không bao giờ nhận delete
~~~

Nếu ghi nguồn và phát event là hai thao tác độc lập, lỗi giữa chúng có thể tạo dữ liệu dẫn xuất **không bao giờ hội tụ**.

### 7.1. Transactional outbox

Khi nguồn hỗ trợ transaction trong ranh giới cần thiết, ứng dụng có thể cập nhật trạng thái và ghi outbox cùng commit:

~~~sql
BEGIN;

UPDATE documents
SET status = 'DELETED',
    revision = revision + 1,
    deleted_at = CURRENT_TIMESTAMP
WHERE document_id = 'A123'
  AND status <> 'DELETED';

-- Phát outbox gắn với revision của thao tác thực sự thành công.
INSERT INTO outbox (
    event_id, aggregate_id, event_type, aggregate_revision, payload
) VALUES (
    'EVT-DELETE-017',
    'A123',
    'DocumentDeleted',
    17,
    '{"documentId":"A123","revision":17}'
);

COMMIT;
~~~

Đây là **minh họa SQL**, không phải lệnh chung cho NoSQL; trong triển khai thật phải bảo đảm chỉ tạo outbox khi update thành công và revision đúng. Một worker đọc outbox rồi gửi event hoặc trực tiếp cập nhật target.

Outbox giảm nguy cơ mất sự kiện giữa nguồn và publisher nhưng **không tự cung cấp exactly-once** cho toàn pipeline. Nếu worker áp dụng delete thành công rồi crash trước checkpoint, event có thể được nhận lại. Consumer phải xử lý lặp an toàn.

### 7.2. Change Data Capture (CDC)

Một lựa chọn khác:

~~~text
Source commit delete
    -> CDC log/stream
    -> connector/broker
    -> search/cache/warehouse consumers
~~~

Cần xác minh theo sản phẩm:

- Event delete có chứa ID/partition key cần thiết không?
- Có pre-image/document cũ hay chỉ có document key?
- Checkpoint/resume token được bảo vệ thế nào?
- Stream retention có đủ cho outage không?
- Nếu event mất vì quá retention, có rebuild/reconciliation không?
- Thứ tự giữa update và delete được bảo đảm theo khóa nào?

Không nên giả định CDC của mọi database có hình dạng hoặc bảo đảm giống nhau.

### 7.3. Xóa vì TTL không nhất thiết qua API

Nếu nguồn tự hết hạn bản ghi bằng TTL, controller **DeleteDocument** có thể không bao giờ được gọi. Nếu event chỉ được phát từ controller, downstream có thể giữ bản ghi đã hết hạn.

Tùy hệ có thể dùng CDC quan sát xóa TTL, job hết hạn, field expiresAt trên bản chiếu và logic kiểm tra lúc đọc, hoặc reconciliation định kỳ. Cần kiểm tra khả năng cụ thể của database; **TTL hết hạn** và **dữ liệu bị xóa vật lý ngay** không phải luôn là một thời điểm.

## 8. Định dạng sự kiện xóa và ánh xạ ID

Một event tối thiểu:

~~~json
{
  "eventId": "EVT-DELETE-017",
  "eventType": "DocumentDeleted",
  "eventSchemaVersion": 1,
  "tenantId": "T01",
  "aggregateId": "A123",
  "aggregateRevision": 17,
  "occurredAt": "2026-11-14T03:00:00Z",
  "payload": {
    "documentId": "A123",
    "deletionKind": "USER_REQUEST"
  }
}
~~~

| Trường | Vai trò |
| --- | --- |
| eventId | Định danh thông điệp, chống xử lý trùng |
| tenantId | Giới hạn phạm vi và tránh đụng ID giữa tenant |
| aggregateId | Chỉ định record nguồn |
| aggregateRevision | Chống sự kiện cũ ghi đè delete |
| eventSchemaVersion | Consumer đọc được nhiều phiên bản payload |
| occurredAt | Thời gian nghiệp vụ, không thay revision |
| deletionKind | Phân biệt loại xóa nếu cần chính sách khác nhau |

Delete event không nên chở lại **toàn bộ nội dung nhạy cảm** của record sắp xóa; nếu không broker/log/DLQ lại trở thành bản sao mới. Nếu downstream cần biết khóa dẫn xuất cũ (ví dụ tag, owner), chỉ truyền metadata tối thiểu hoặc giữ mapping có thời hạn.

### 8.1. Canonical ID không nhất thiết trùng target ID

~~~text
Source documentId   = A123
Search document ID  = T01:A123
Vector chunk IDs    = T01:A123:chunk:1 ... chunk:30
Cache key           = article-detail:T01:A123
CDN asset path      = /T01/A123/thumbnail.jpg
~~~

Consumer phải biết quy tắc biến đổi ID và phiên bản index/collection. Nếu gửi delete ID=A123 vào index thực dùng ID=T01:A123, target có thể trả **not found** dù bản sao vẫn tồn tại.

Không nên coi “not found” là bằng chứng toàn hệ đã xóa nếu chưa kiểm chứng đúng index, routing, namespace và ID.

## 9. Chống dữ liệu đã xóa bị hồi sinh

Xét lịch sử:

~~~text
revision 15: PUBLISHED
revision 16: UPDATED
revision 17: DELETED
~~~

Consumer có thể nhận:

~~~text
17 (delete)
16 (update đến muộn)
17 (delete lặp)
~~~

Nếu xóa ở revision 17 rồi upsert bản revision 16 mà không kiểm tra version, record sẽ **xuất hiện trở lại**, có thể tồn tại mãi cho tới thay đổi tiếp theo.

### 9.1. Version guard

Với event mang **toàn bộ state mới**, một quy tắc là:

~~~text
incomingRevision < lastAppliedRevision
    -> ignore stale event

incomingRevision == lastAppliedRevision
    -> xử lý như duplicate đã ghi nhận

incomingRevision > lastAppliedRevision
    -> áp dụng state/delete và lưu revision mới
~~~

Quy tắc phải được thực hiện bằng **thao tác điều kiện/atomic ở nơi lưu revision**, hoặc một cơ chế đồng bộ thực sự, không chỉ đọc revision trong RAM rồi ghi mù.

Nếu event là **delta** như “tăng bộ đếm thêm 1”, không thể tùy tiện bỏ phiên bản trung gian; phải phát hiện gap/replay hoặc dùng phép gộp có semantics phù hợp.

### 9.2. Tombstone tối thiểu

~~~json
{
  "tenantId": "T01",
  "documentId": "A123",
  "lastRevision": 17,
  "deleted": true
}
~~~

Tombstone giữ bằng chứng record đã bị xóa ở revision 17, giúp từ chối update revision 16 dù nội dung thực đã được loại khỏi index. Không cần giữ nguyên payload cũ.

Tombstone cũng phải có chính sách retention. Nếu xóa tombstone quá sớm trong khi event cũ còn được replay, document có thể hồi sinh. Nhưng giữ tombstone chứa định danh hoặc dữ liệu cá nhân vô thời hạn cũng có thể không phù hợp chính sách xóa. Cần cân bằng bằng metadata tối thiểu, TTL có cơ sở, watermark replay và khả năng kiểm tra authoritative state.

### 9.3. Xóa rồi tạo lại cùng ID

Nếu nghiệp vụ cho phép tái sử dụng A123, phải phân biệt **đời record**:

~~~text
aggregateId = A123
generation  = 2
revision    = 1
~~~

hoặc dùng revision đơn điệu xuyên các đời record. Với nội dung nhạy cảm, tránh tái sử dụng ID thường đơn giản hơn. Nếu không, một delete cũ có thể xóa nhầm record mới, hoặc một create cũ hồi sinh record đã xóa.

## 10. Xóa khỏi search index: ACK, visibility và cleanup

Đối với search engine, cần phân biệt:

1. **Delete accepted:** target xác nhận thao tác theo write API.
2. **Search visibility updated:** các truy vấn ở phạm vi cần kiểm chứng không trả document.
3. **Physical cleanup:** dữ liệu lưu trong segment/file được dọn theo cơ chế engine.

Một request dạng REST minh họa theo phong cách Elasticsearch/OpenSearch:

~~~http
DELETE /articles_v2/_doc/T01%3AA123
~~~

Cú pháp, URL encoding, routing, version conflict, alias và refresh cần tra đúng tài liệu phiên bản triển khai; đây không phải API phổ quát cho mọi hệ search.

### 10.1. Refresh và replica

Search engine near-real-time có thể có **refresh interval**, vì vậy ACK từ delete API chưa nhất thiết là lúc mọi query thấy trạng thái mới. Làm refresh cưỡng bức sau mỗi delete có thể tốn tài nguyên, đặc biệt khi tải cao. Nếu cần ngăn nội dung nhạy cảm xuất hiện lập tức, hãy thêm **chốt ở đường đọc/authorization** thay vì chỉ dựa vào lịch refresh.

### 10.2. Delete-by-ID và delete-by-query

Nếu biết danh sách ID chính xác, xóa theo ID thường dễ kiểm soát **idempotency, tiến độ và kết quả**.

Delete-by-query có thể phù hợp khi xóa một tập lớn theo điều kiện, nhưng cần xem:

- Truy vấn có đúng tenant/phạm vi không?
- Có record mới được tạo trong lúc job chạy không?
- Khi job kết thúc, những shard/replica nào đã cập nhật?
- Có cần kiểm tra lại sau refresh không?
- Bản ghi ở index cũ/mới có bị bỏ sót không?

Một lệnh bulk có thể xóa nhiều dữ liệu hơn dự kiến nếu filter sai; phải có guardrail và quy trình vận hành phù hợp.

### 10.3. Reindex là đường tái xuất hiện dữ liệu

~~~text
10:00  Bắt đầu dựng articles_v3 từ snapshot cũ
10:01  A123 bị xóa tại nguồn
10:02  Delete event áp dụng lên articles_v2
10:03  Snapshot cũ đưa A123 vào articles_v3
10:04  Alias chuyển từ articles_v2 sang articles_v3
~~~

Kết quả: A123 xuất hiện lại sau cutover.

Quy trình reindex an toàn hơn cần:

1. Mốc snapshot/watermark rõ ràng.
2. Replay thay đổi sau snapshot, **bao gồm delete**.
3. Áp dụng theo revision và quy tắc tombstone.
4. Xác minh tài liệu đã xóa không có ở index mới.
5. Chuyển alias/traffic sau khi đạt tiêu chí.
6. Quản lý index cũ theo retention và yêu cầu xóa dữ liệu.

Đừng chỉ đếm số document gần đúng để chứng minh không còn bản ghi bị xóa.

## 11. Cache và CDN: không còn ở search vẫn có thể đọc qua URL

Giả sử:

~~~text
cache key = article-detail:T01:A123
value     = nội dung bài trước khi xóa
TTL       = 30 phút
~~~

Nếu API đọc cache rồi trả ngay mà không kiểm tra trạng thái, người có URL trực tiếp vẫn đọc được nội dung dù search đã gỡ.

### 11.1. Các tầng cache cần xem

- In-process cache ở API node.
- Redis/Memcached shared cache.
- Cached query result trong GraphQL hoặc search API.
- CDN/edge cache giữ HTML, image, thumbnail.
- Browser cache/service worker và cache ứng dụng mobile.
- Autocomplete, recommendation hoặc pre-rendered feed.

Không phải mọi bản đã được tải về thiết bị người dùng đều có thể thu hồi tức thì. Hợp đồng xóa cần phân biệt **ngừng cung cấp nội dung từ hạ tầng** với việc xóa mọi bản sao đã được người dùng lưu.

### 11.2. Invalidation không thay authorization

Một đường xử lý có thể gửi lệnh:

~~~text
Delete source
    -> invalidate detail cache
    -> invalidate query caches
    -> purge CDN asset
    -> delete search/vector/recommendation
~~~

Nếu cache invalidation thất bại, đường phục vụ nội dung nhạy cảm vẫn phải **kiểm tra trạng thái/quyền authoritative**, dùng version/revocation token tin cậy hoặc từ chối truy cập khi không xác minh được.

Không được đưa payload nhạy cảm ra frontend trước rồi mới cho frontend tự ẩn; lúc đó dữ liệu đã bị tiết lộ.

### 11.3. Key có version

~~~text
article:T01:A123:revision16
article:T01:A123:revision17
~~~

Versioned cache key có thể giảm nguy cơ dùng nhầm nội dung cũ nếu API lấy revision có thẩm quyền trước khi đọc. Nhưng key cũ vẫn có thể nằm trong bộ nhớ đến khi hết hạn; kỹ thuật này không chứng minh đã xóa vật lý.

## 12. Materialized view, analytics và vector store

### 12.1. Bản chiếu theo các khóa khác nhau

Nguồn A123 có:

~~~text
owner = U07
tag   = NoSQL
status= PUBLISHED
~~~

Các read models:

~~~text
articles_by_owner[U07] -> A123
articles_by_tag[NoSQL] -> A123
recent_articles[T01]  -> A123
~~~

Để gỡ A123, consumer phải biết các **khóa dẫn xuất** mà nó đã từng xuất hiện. Nếu nguồn đã hard-delete và event chỉ có documentId, consumer có thể không biết A123 thuộc tag nào.

Giải pháp gồm: payload sự kiện chứa khóa dẫn xuất tối thiểu, pre-image trong CDC nếu hỗ trợ, mapping ID -> projection keys, hoặc một tombstone/metadata có thời hạn. Không cần tái phát toàn bộ nội dung chỉ để xác định tag.

### 12.2. Analytics/warehouse

Một bản ghi có thể xuất hiện trong:

~~~text
raw_events
article_snapshot
daily_article_counts
owner_activity
~~~

Xóa khỏi snapshot không tự xóa payload lịch sử trong raw_events hoặc sửa mọi bảng tổng hợp. Cần **data lineage** và chính sách dữ liệu cụ thể: bảng nào phải xử lý record, bảng nào cần tính lại, aggregate nào có thể được giữ, retention nào đang áp dụng.

Không thể mặc định dữ liệu đã aggregate là vô hại; cũng không thể suy mọi aggregate đều bắt buộc xóa trong mọi trường hợp. Điều này phải dựa trên hợp đồng nghiệp vụ và yêu cầu áp dụng.

### 12.3. Vector index và chunk

Một bài A123 có thể được chia thành 30 chunk để tạo 30 vector:

~~~text
T01:A123:chunk:01
T01:A123:chunk:02
...
T01:A123:chunk:30
~~~

Nếu chỉ xóa một vector đại diện, 29 chunk còn lại có thể tiếp tục xuất hiện trong retrieval. Cần duy trì mapping bài -> chunk IDs, xóa đủ và kiểm tra metadata/similarity search không còn trả nội dung cũ.

Khi rebuild embeddings từ snapshot cũ, lại có nguy cơ hồi sinh chunk; cần replay trạng thái xóa như với full-text index.

## 13. Những điểm lỗi dọc đường đồng bộ

| Sự cố | Hệ quả | Biện pháp |
| --- | --- | --- |
| Source commit nhưng publish event lỗi | Target không nhận delete | Outbox hoặc CDC có khả năng phục hồi |
| Connector ngừng hoạt động | Backlog tăng | Retry, giám sát lag/age |
| Stream hết retention | Không replay được event | Rebuild/reconciliation từ nguồn |
| Consumer crash sau khi delete | Event được giao lại | Idempotent delete |
| Checkpoint trước khi target ghi xong | Mất tiến độ và bỏ lỡ delete | Chỉ ACK theo quy trình an toàn |
| Update cũ đến sau delete | Bản ghi hồi sinh | Revision guard/tombstone |
| Sai tenant/index/document ID | Target trả not found dù dữ liệu còn | Canonical ID + mapping và kiểm tra |
| Event schema đổi phá tương thích | Consumer parse lỗi | Schema version/compatibility |
| Target quá tải | Delete kéo dài | Bounded queue, backpressure, retry |
| Reindex từ snapshot cũ | Document xuất hiện lại | Replay delete và kiểm tra cutover |
| Cache invalidation lỗi | GET chi tiết vẫn trả bản cũ | Authoritative read gate + retry |

**Dead-letter queue (DLQ)** chỉ giữ thông điệp chưa xử lý, không tự sửa sự cố. Cần owner, alert, runbook, cơ chế sửa payload và replay. Một event xóa mắc trong DLQ từ hôm qua có thể nghiêm trọng hơn hàng nghìn event mới tới.

### 13.1. At-least-once delivery

Một consumer có thể nhận:

~~~text
DocumentDeleted A123 rev17
DocumentDeleted A123 rev17
DocumentDeleted A123 rev17
~~~

Kết quả cần giữ A123 bị xóa, revision không giảm, không tạo tác dụng phụ sai. Delete-by-ID thường dễ idempotent, nhưng cần bảo vệ trường hợp ID được tái sử dụng hoặc target khác chưa hoàn tất.

### 13.2. Thứ tự event không phải lúc nào cũng toàn cục

Một broker có thể bảo đảm thứ tự **trong cùng partition** nhưng không giữa các partition. Chọn event partition key theo aggregate ID giúp giảm đảo thứ tự cho một document, nhưng không thay thế revision guard khi có replay, parallelism, failover hoặc nhiều writer.

## 14. Workflow xóa đa hệ cần theo dõi tiến độ

Không thể giả định xóa source + search + Redis + CDN + warehouse là một transaction ACID duy nhất.

Pseudocode consumer:

~~~text
on DocumentDeleted(event):
    validate schema and tenant
    resolve canonical target IDs
    check revision with an atomic/conditional mechanism
    record deletion version/tombstone
    enqueue or apply delete per downstream target
    retry failed targets idempotently
    record target completion and verification status
    acknowledge event under safe checkpoint policy
~~~

Đây là luồng logic. **Kiểm tra version và ghi tombstone phải có bảo đảm cạnh tranh thích hợp**, còn các thao tác sang nhiều dịch vụ phải có trạng thái/retry; không thể gói tất cả chúng vào một câu lệnh atomic giả định.

### 14.1. Progress record

~~~json
{
  "requestId": "DEL-1001",
  "tenantId": "T01",
  "documentId": "A123",
  "revision": 17,
  "sourceState": "DELETED",
  "targets": {
    "search": "VERIFIED",
    "detailCache": "VERIFIED",
    "recommendations": "PENDING",
    "warehouse": "QUEUED"
  },
  "requestedAt": "2026-11-14T03:00:00Z"
}
~~~

Quy ước trạng thái:

- **QUEUED:** nhiệm vụ đã được ghi nhận.
- **APPLIED/ACKED:** target xác nhận thao tác theo API.
- **VISIBLE/VERIFIED:** kiểm tra ở đường đọc cho thấy đạt điều kiện mong muốn.
- **PENDING:** còn bước phải làm.
- **FAILED:** vượt số lần thử/điều kiện xử lý thông thường.

Không nên báo “đã xóa khỏi mọi nơi” khi search thành công nhưng warehouse còn pending. Với hệ không hỗ trợ GET/verification trực tiếp, cần định nghĩa bằng chứng phù hợp như watermark/job completion/reconciliation; tránh khẳng định quá khả năng quan sát.

## 15. Bảo vệ người dùng trong thời gian bản chiếu chưa hội tụ

Với dữ liệu không được phép lộ, đường đọc không nên chỉ tin vào bản search index có thể cũ:

~~~text
User -> Search API
      -> Search trả A123 (stale)
      -> API kiểm tra trạng thái/quyền authoritative
      -> Source báo A123 DELETED
      -> API loại A123 trước khi trả payload
~~~

Điều quan trọng là loại dữ liệu **trước** khi title, snippet, highlight hoặc metadata nhạy cảm được chuyển cho client.

Nếu kiểm tra từng hit quá tốn kém, có thể dùng batch authorization, revocation lookup có bảo đảm phù hợp, filter authoritative hoặc thiết kế read model khác. Khi không thể xác minh quyền cho dữ liệu nhạy cảm, **fail closed** (không trả nội dung) thường an toàn hơn trả cache cũ.

Đường GET chi tiết cũng phải kiểm tra, vì biết URL trực tiếp không cần đi qua search. Autocomplete, facet counts, ảnh CDN và recommendation cards cũng là các đường có thể tiết lộ nội dung/tồn tại của record đã xóa.

## 16. Reconciliation khi event đã thất bại hoặc bị bỏ sót

Một job **đối soát** giúp tìm những bản chiếu không còn tương ứng với nguồn:

~~~text
1. Chọn tenant, khoảng ID hoặc các thay đổi từ watermark.
2. Đọc tập nguồn active và revision.
3. Đọc tập record trong index/read model.
4. Phát hiện:
   - nguồn đã xóa, target vẫn còn
   - nguồn còn nhưng target thiếu
   - target mang revision cũ
   - record nằm sai tenant/index
5. Tạo thao tác sửa idempotent.
6. Ghi watermark, kết quả và lỗi cần xử lý.
~~~

Khi nguồn **hard-delete** và không giữ danh sách ID/tombstone, việc biết chính xác “những record nào vừa bị xóa” khó hơn. Có thể so sánh tập ID theo snapshot, giữ deletion ledger tối thiểu có thời hạn hoặc khôi phục từ stream/log trong phạm vi retention.

### 16.1. Reconciliation cũng có thể tạo dữ liệu cũ

~~~text
T0: reconciler chụp trạng thái A123 rev15
T1: user xóa A123 rev17
T2: reconciler upsert A123 rev15 vào search
~~~

Nếu không có revision guard, job sửa dữ liệu thiếu lại **hồi sinh** record. Vì vậy reconciliation phải kiểm tra trạng thái nguồn mới nhất phù hợp hoặc dùng conditional update có version, không được ghi đè mù.

### 16.2. Full rebuild

Khi index hỏng, event stream quá retention hoặc mapping sai hàng loạt:

1. Lấy snapshot nguồn có mốc nhất quán.
2. Lập chỉ mục các record hợp lệ.
3. Replay các thay đổi sau snapshot, đặc biệt là **delete**.
4. Xác minh nhóm record đã xóa trước cutover.
5. Chuyển traffic sang index mới có kiểm soát.

Restore search index cũ từ backup có thể đưa record đã xóa trở lại nếu không replay những thay đổi xóa sau mốc backup.

## 17. Đo SLO: nhìn vào tail lag, không chỉ trung bình

Giả sử một ngày có **10.000** delete; mục tiêu minh họa là **99,9%** biến mất khỏi search trong **10 giây** tính từ source commit.

Nếu chỉ **9.985** thao tác đạt ngưỡng:

\[
\frac{9{,}985}{10{,}000}\times100\% = 99{,}85\%
\]

Mục tiêu **99,9% chưa đạt** dù thời gian trung bình có thể rất thấp.

### 17.1. Metric nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| deletion_visibility_lag | Độ trễ từ commit đến khi target không trả record |
| deletion_publish_lag | Độ trễ đưa delete vào stream |
| deletion_consumer_lag | Event chờ consumer bao lâu |
| oldest_pending_delete_age | Tuổi event delete lâu nhất chưa hoàn thành |
| pending_deletions_by_target | Số việc còn chờ cho search/cache/vector/warehouse |
| deletion_retry_count | Số lần retry |
| deletion_dlq_count | Số delete chưa xử lý thành công trong DLQ |
| stale_deleted_document_count | Số record nguồn đã xóa nhưng target còn |
| delete_resurrection_count | Bản ghi bị update/reindex cũ tạo lại |
| reconciliation_repairs | Số sai lệch được sửa |
| deletion_slo_compliance | Tỷ lệ delete đạt deadline theo loại dữ liệu |

**Đừng chỉ thống kê những delete đã hoàn thành.** Các delete pending quá hạn phải được tính là vi phạm, nếu không dashboard có thể trông tốt hơn thực tế.

### 17.2. Age quan trọng hơn chỉ đếm backlog

Queue chứa 1.000 event mới tạo có thể là tải bình thường. Queue chứa 1 event delete nhạy cảm kẹt 24 giờ có thể nghiêm trọng hơn. Nên theo dõi **tuổi nhiệm vụ cũ nhất** và phân nhóm sự kiện theo mức độ rủi ro.

### 17.3. Xác minh trạng thái target

Nếu SLO nói về search visibility, cách đo phải kiểm chứng **search query không còn trả document** trong phạm vi yêu cầu. Nếu target không hỗ trợ kiểm tra trực tiếp theo ID, cần dùng completion marker, watermark, batch verification hoặc phương pháp chứng cứ khác với giới hạn rõ ràng.

## 18. Xóa hàng loạt: tải và chi phí cũng ảnh hưởng lag

Một yêu cầu xóa toàn tenant, hết hạn retention hoặc gỡ một nhóm nội dung có thể tạo hàng trăm nghìn đến hàng triệu delete.

~~~text
Source delete events
  -> bounded queue
  -> batch workers
  -> target delete API
  -> retry lỗi tạm thời với backoff
  -> checkpoint an toàn
~~~

Các yếu tố cần kiểm soát:

- Concurrency và batch size phù hợp với từng target.
- Backpressure khi search/index đang quá tải.
- Retry với exponential backoff và jitter để tránh retry storm.
- Tách độ ưu tiên cho delete nhạy cảm và delete analytics.
- Giới hạn tài nguyên để không phá khả dụng của đường đọc/ghi khác.
- Watermark và progress để biết phạm vi công việc đã hoàn thành.

Delete-by-query có thể hiệu quả cho tập lớn nhưng cần định nghĩa **snapshot/phạm vi**, xử lý record được thêm trong lúc job chạy và kiểm tra cuối. Nếu filter tenant sai, hậu quả có thể nghiêm trọng hơn cả độ trễ đồng bộ.

## 19. Restore và backup có thể hồi sinh dữ liệu

~~~text
09:00  Backup nguồn còn A123
10:00  User xóa A123
10:05  Search/cache đã xóa theo
11:00  Sự cố khiến hệ restore backup 09:00
11:10  Reindex từ nguồn restored lại thấy A123
~~~

Nếu không phát lại deletion log/tombstone sau mốc backup, A123 có thể xuất hiện trở lại.

Một quy trình restore đúng cần:

1. Xác định mốc backup và những thay đổi sau mốc.
2. Replay các update/delete bắt buộc theo thứ tự/phiên bản phù hợp.
3. Áp dụng lại danh sách xóa quan trọng trước khi mở đường phục vụ.
4. Rebuild các bản chiếu từ nguồn đã được khôi phục đúng.
5. Xác minh những record đã xóa không tái xuất.

Backup và archive có retention theo chính sách riêng. Nếu hạ tầng dùng immutable backup, có thể không khả thi để xóa byte ngay trong mọi snapshot; cần diễn đạt rõ chính sách lưu giữ, thời hạn, kiểm soát truy cập và tránh tái xuất khi restore, thay vì hứa điều hệ thống không thực hiện được.

## 20. Quy trình thiết kế tính năng Delete Article

### Bước 1 — Định nghĩa hợp đồng

~~~text
API: DELETE /articles/{articleId}
Quyền: xác thực owner/tenant
Source completion: nguồn commit trạng thái DELETED
Read authorization: từ thời điểm phù hợp, không còn trả nội dung trái quyền
Search: hội tụ theo SLO đã đo
Analytics/backup: xử lý theo retention và chính sách riêng
Response: phân biệt xóa ở nguồn với các downstream đang xử lý
~~~

### Bước 2 — Ghi nguồn và event đáng tin cậy

~~~text
transaction/atomic scope:
    verify ownership and current state
    update status=DELETED, revision++
    append outbox DocumentDeleted(articleId, revision, tenantId)
commit
~~~

Nếu DELETE được retry, phải có semantics idempotent. Không cần tạo vô hạn revision/event mới chỉ vì client gửi lại cùng yêu cầu do timeout.

### Bước 3 — Bảo vệ đường đọc quan trọng

API chi tiết xác minh trạng thái authoritative. Search API có thể lọc record đã xóa tại server trước khi trả title/excerpt. Không coi TTL cache là ranh giới bảo mật.

### Bước 4 — Consumer cập nhật từng kho

~~~text
Search: delete article + chunks, xử lý revision/refresh
Redis: invalidate các key detail/query
Vector: xóa toàn bộ embedding chunks
Recommendations: bỏ article khỏi candidate list
Warehouse: apply retention/delete policy
~~~

Các consumer hoạt động độc lập, có retry và trạng thái. Một target ACK không đồng nghĩa tất cả target đã hoàn thành.

### Bước 5 — Theo dõi và đối soát

Ghi source commit, event age, target ACK và target visibility. Cảnh báo delete vượt deadline, duy trì DLQ, reconciliation và playbook sửa sai lệch.

### Bước 6 — Kiểm soát reindex/restore

Mọi quá trình rebuild từ snapshot phải phát lại trạng thái delete và kiểm tra trước khi chuyển traffic.

## 21. Kiểm thử các ca lỗi điển hình

### 21.1. Consumer tạm dừng

Xóa A123 tại nguồn, dừng consumer trong môi trường test. Kiểm tra API chi tiết không tiết lộ nội dung trái quyền dù search còn stale. Khởi động consumer và xác nhận search hội tụ.

### 21.2. Event đảo thứ tự

~~~text
DocumentDeleted A123 revision17
DocumentUpdated A123 revision16
~~~

Kết quả mong muốn: A123 **không hồi sinh**. Cần cơ chế revision/tombstone có bảo đảm cạnh tranh thực tế.

### 21.3. Event lặp

~~~text
DocumentDeleted A123 revision17
DocumentDeleted A123 revision17
~~~

Consumer vẫn idempotent, không lỗi vô hạn. Cần kiểm tra đúng ID/namespace trước khi coi not found là trạng thái hợp lệ.

### 21.4. Crash trước checkpoint

Consumer xóa target thành công rồi crash trước khi xác nhận event. Khi nhận lại event, kết quả vẫn đúng.

### 21.5. TTL tự xóa

Để một record hết hạn ở nguồn không qua controller. Xác minh downstream nhận thay đổi qua cơ chế đã chọn hoặc đường đọc tự loại bản hết hạn.

### 21.6. Reindex từ snapshot cũ

Dựng index mới từ snapshot có A123, sau đó phát lại delete và kiểm tra trước cutover rằng không còn A123.

### 21.7. Restore trước mốc delete

Restore backup trước khi A123 bị xóa, áp dụng lại deletion log và kiểm tra mọi projection trước khi mở traffic.

### 21.8. Một target lỗi kéo dài

Search đã xác minh sạch nhưng vector store không kết nối được. Workflow phải giữ trạng thái pending, retry và không báo “mọi nơi đã xóa hoàn tất”.

## 22. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| DELETE trả 200 là mọi bản sao đã xóa | Chỉ đúng trong phạm vi hợp đồng ACK |
| Search không thấy record là dữ liệu vật lý đã mất | Visibility khác cleanup, compaction và backup |
| TTL là sự kiện delete phát ngay | Hành vi TTL/event tùy database |
| Eventual nghĩa là tự hội tụ dù mất event | Cần đường truyền, replay và reconciliation |
| Event delete gửi trùng là lỗi không thể xử lý | Consumer nên idempotent |
| Update cũ không ảnh hưởng sau delete | Có thể hồi sinh document nếu thiếu version guard |
| Xóa search chính là đủ | Cache, CDN, vector, recommendation và analytics cũng có dữ liệu |
| Delete-by-ID not found nghĩa là sạch mọi index | Có thể sai ID/routing/index hoặc còn bản khác |
| Reindex từ snapshot cũ luôn an toàn | Cần replay delete sau snapshot |
| Backup chỉ dùng để cứu dữ liệu | Restore backup cũ có thể tái tạo dữ liệu đã xóa |
| Có DLQ là lỗi được giải quyết | DLQ cần owner, cảnh báo và replay |
| Độ trễ trung bình thấp là đủ | Tail latency và delete không bao giờ hoàn thành rất quan trọng |
| Client tự lọc kết quả là đủ cho bảo mật | Dữ liệu phải được chặn trước khi tới client |

## 23. Bài tập thực hành

### Bài 1: Tính lag

~~~text
source commit = 10:00:00.000
event publish = 10:00:00.100
consumer read = 10:00:01.500
index ACK     = 10:00:01.800
query clean   = 10:00:02.400
~~~

**Câu hỏi:** End-to-end search visibility lag và visibility lag sau ACK là bao nhiêu?

**Gợi ý:** Lần lượt **2,4 giây** và **0,6 giây**, nếu đồng hồ/mốc đo thống nhất.

### Bài 2: Update đến muộn

~~~text
v8 DocumentUpdated
v9 DocumentDeleted
~~~

Consumer nhận v9 trước v8. Nếu xóa v9 rồi upsert v8, điều gì xảy ra?

**Gợi ý:** Dữ liệu bị hồi sinh. Cần tombstone/version guard có bảo đảm atomic hoặc quy trình tương đương.

### Bài 3: Cache cũ

Search gỡ bài A123 sau 2 giây, nhưng detail cache vẫn trả nội dung trong 30 phút.

**Câu hỏi:** Hệ đã bảo đảm “không thể xem bài sau khi xóa” chưa?

**Gợi ý:** Chưa. Cần invalidate cache và kiểm tra authoritative state/quyền trên đường chi tiết.

### Bài 4: Xóa do TTL

Session tự hết hạn trong database, consumer chỉ nghe event do DeleteController phát.

**Câu hỏi:** Có thể tồn tại stale data ở đâu? Chọn phương án sửa.

**Gợi ý:** Các bản chiếu không biết TTL đã xóa nguồn. Dùng CDC nếu hỗ trợ, expiresAt ở đường đọc, expiration job hoặc reconciliation.

### Bài 5: Bản chiếu theo tag

Document A123 có tag NoSQL, nhưng nguồn hard-delete và event chỉ còn documentId.

**Câu hỏi:** Làm sao consumer biết cần bỏ A123 khỏi danh sách NoSQL?

**Gợi ý:** Lưu pre-image metadata tối thiểu, mapping ID -> projection keys hoặc một tombstone có hạn; không cần phát lại toàn bộ nội dung.

### Bài 6: Tính SLO

Có 20.000 thao tác delete, 19.970 thao tác hoàn thành trong 10 giây. Mục tiêu 99,9%.

**Gợi ý:** \(19.970/20.000 = 99,85\%\), nên **không đạt**.

### Bài 7: Reindex hồi sinh

Index v2 đã xóa A123; index v3 được dựng từ snapshot cũ chưa có delete, rồi alias chuyển sang v3.

**Gợi ý:** Replay delete sau snapshot và xác minh trạng thái xóa ở v3 trước khi cutover.

### Bài 8: Restore backup

Backup 09:00 chứa A123; A123 bị xóa lúc 10:00; lúc 11:00 phải restore backup 09:00.

**Gợi ý:** Áp dụng lại delete từ log/tombstone sau mốc backup, rebuild projection và xác minh A123 không tái xuất trước khi mở traffic.

### Bài 9: Xóa hàng loạt

Một job xóa dữ liệu tenant T01 đang chạy, có bản ghi mới xuất hiện và một phần delete-by-query thất bại.

**Gợi ý:** Xác định scope/time boundary, giám sát tiến độ, retry phần lỗi, phối hợp writer nếu cần và đối soát kết quả; không dựa duy nhất vào số lượng deleted do job trả.

### Bài 10: Trạng thái hoàn tất

~~~text
Source: DELETED
Search: VERIFIED
Cache: VERIFIED
Vector: PENDING
Warehouse: QUEUED
~~~

**Câu hỏi:** Có thể công bố “đã xóa hoàn toàn” không?

**Gợi ý:** Chưa. Chỉ có thể xác nhận những lớp đã được kiểm chứng trong phạm vi tương ứng; vector/warehouse vẫn đang xử lý.

## 24. Kết luận

Trong NoSQL nhiều bản chiếu, **xóa ở nguồn là điểm bắt đầu của vòng đời xóa**, không phải lúc mọi nơi đồng thời sạch dữ liệu. Search index, cache, CDN, vector store, recommendation, analytics và backup có cơ chế lưu giữ, cập nhật và quan sát khác nhau.

Độ trễ xóa nên được đo từ **source commit tới lúc đường đọc thật không còn trả dữ liệu trong phạm vi cam kết**, thay vì chỉ đo tới thời điểm event được gửi hoặc target ACK. Những nội dung nhạy cảm cần được bảo vệ **ngay tại authorization và đường phục vụ**, không được chờ tất cả bản chiếu eventual hội tụ mới ngăn truy cập trái phép.

Một thiết kế đáng tin cậy cần **outbox/CDC, định danh và revision ổn định, idempotency, tombstone chống hồi sinh, retry, đo lag theo target, reconciliation và quy trình reindex/restore** có xử lý delete. Chỉ khi phân biệt rõ **xóa logic, không còn hiển thị, xóa vật lý và xử lý bản lưu trữ dài hạn**, hệ thống mới có thể đưa ra lời cam kết xóa chính xác, có thể kiểm chứng và phù hợp rủi ro nghiệp vụ.
