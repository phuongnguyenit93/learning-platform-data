# Di chuyển dữ liệu, đối chiếu kết quả và kiểm soát giai đoạn song song

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Chuyển đổi kiến trúc.  
> **Mục tiêu:** thiết kế migration dữ liệu từ hệ thống cũ sang microservices có thể kiểm chứng và phục hồi; hiểu backfill, CDC, dual-run, dual-write, reconciliation, cutover và rollback; giữ đúng dữ liệu nghiệp vụ trong suốt giai đoạn hai hệ thống cùng tồn tại.

## 1. Bài toán: chuyển ứng dụng dễ hơn chuyển dữ liệu

Một doanh nghiệp có monolith thương mại điện tử. Customer, Order, Payment, Inventory và Shipping cùng nằm trong một relational database. Doanh nghiệp muốn tách thành các microservices có database riêng.

API mới có thể được triển khai dần, nhưng dữ liệu cũ không tự chuyển sang service mới. Trong giai đoạn chuyển đổi, monolith vẫn nhận đơn hàng, một số request đã được route sang service mới, còn batch jobs và webhook vẫn chạy theo đường cũ. Nếu không có cơ chế đồng bộ và đối chiếu, hệ thống mới có thể thiếu record, đọc trạng thái cũ, tạo giao dịch trùng hoặc tính tổng khác hệ thống cũ.

Ví dụ:

- Backfill đã copy bảng Orders nhưng một đơn mới được tạo ngay sau khi worker đọc đến cuối bảng.
- CDC phát lại event khi consumer restart; projection mới đếm doanh thu hai lần.
- Monolith cập nhật địa chỉ Customer trong khi Customer Service cũng ghi phiên bản mới.
- Dual-write ghi thành công database cũ nhưng thất bại database mới.
- Hai hệ thống dùng quy tắc rounding khác nhau nên tổng tiền lệch.
- Cutover chuyển 100% traffic nhưng webhook, batch job và reporting vẫn đọc nguồn cũ.
- Rollback ứng dụng về monolith nhưng schema mới đã nhận dữ liệu mà schema cũ không thể biểu diễn.

**Di chuyển dữ liệu là thay đổi về quyền sở hữu, hợp đồng, consistency và vận hành**, không chỉ là copy rows từ database này sang database khác.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Mục đích |
| --- | --- | --- |
| **Backfill** | Đọc dữ liệu lịch sử và nạp vào đích | Đưa dữ liệu hiện có sang hệ thống mới |
| **CDC** | Ghi nhận thay đổi phát sinh sau một mốc log/transaction | Bắt kịp source trong lúc backfill |
| **Initial snapshot** | Ảnh chụp dữ liệu tại thời điểm nhất quán | Tạo baseline có thể đối chiếu |
| **Dual-run** | Chạy hai implementation trong cùng giai đoạn | So sánh behavior trước cutover |
| **Shadow traffic** | Sao chép request sang hệ mới nhưng không dùng response mới cho user | Quan sát hệ mới an toàn |
| **Dual-write** | Một logical operation ghi vào hai nơi | Giữ hai store nhận thay đổi, nhưng có partial failure |
| **Dual-read** | Đọc hai nguồn để so sánh hoặc fallback | Phát hiện sai khác/chuyển nguồn đọc |
| **Reconciliation** | Đối chiếu trạng thái theo quy tắc nghiệp vụ | Phát hiện và phân loại sai khác |
| **Cutover** | Chuyển quyền phục vụ hoặc ghi sang hệ thống mới | Hoàn tất một giai đoạn migration |
| **Rollback** | Quay lại phiên bản/nguồn phục vụ trước | Phục hồi khi thay đổi không đạt điều kiện |
| **Roll-forward** | Sửa hệ thống mới và tiếp tục tiến lên | Tránh rollback khi dữ liệu mới không thể biểu diễn ở hệ cũ |
| **Source of truth** | Nguồn có thẩm quyền cho một dữ liệu/nghiệp vụ | Tránh nhiều nơi cùng tự quyết định |
| **Watermark/checkpoint** | Vị trí đã đọc/xử lý an toàn trong stream hoặc log | Resume mà không bỏ sót |

Không dùng các thuật ngữ này thay thế nhau. **Dual-run không đồng nghĩa dual-write**: có thể chạy implementation mới để so sánh nhưng chỉ một nơi có quyền ghi. Đây thường là cách giảm rủi ro hơn.

## 3. Xác định ownership và bất biến nghiệp vụ

Trước khi chọn công cụ, cần xác định domain nào thuộc service nào.

| Data domain | Owner sau chuyển đổi | Ví dụ dữ liệu | Ai được quyền ghi |
| --- | --- | --- | --- |
| Customer | Customer Service | Profile, address, contact preference | Customer Service |
| Order | Order Service | Order, line items, order state | Order Service |
| Payment | Payment Service | Payment attempt, capture, refund, ledger reference | Payment Service |
| Inventory | Inventory Service | Stock balance, reservation, movement | Inventory Service |
| Shipping | Shipping Service | Shipment, label, tracking state | Shipping Service |

Bảng là ví dụ; hệ thống thật có thể chia nhỏ ownership theo aggregate hoặc subdomain.

### 3.1. Source of truth thay đổi theo giai đoạn

- **Trước migration:** monolith/database cũ là nguồn có thẩm quyền.
- **Backfill:** database cũ vẫn là nguồn chính; đích nhận bản sao.
- **Shadow/dual-run:** nguồn cũ quyết định response; hệ mới chỉ tính kết quả đối chiếu.
- **Write cutover:** service mới nhận quyền ghi cho domain đã chuyển.
- **Post-cutover:** service mới là authority; nguồn cũ chỉ còn read/archive theo policy.
- **Retirement:** loại bỏ đường ghi cũ sau khi hết phụ thuộc và retention.

Không để một domain có hai authority không được điều phối. Nếu tạm thời dual-write, phải có giao thức xác định commit, retry, deduplication và xử lý partial failure.

### 3.2. Ghi rõ business invariants

Ví dụ:

- Một orderId xác định một đơn hàng duy nhất.
- Tổng tiền order bằng tổng line items, discount, tax và shipping theo quy tắc được công bố.
- Một payment capture không được ghi nhận hai lần cho cùng logical operation.
- Available stock không âm nếu nghiệp vụ không cho phép oversell.
- Reservation chỉ được release một lần.
- Shipment không chuyển sang trạng thái lùi bất hợp lệ.
- Customer thuộc đúng tenant và không rò sang tenant khác.

Reconciliation phải kiểm tra **invariants**, không chỉ so sánh số lượng rows.

## 4. Lựa chọn chiến lược migration

### 4.1. Big-bang migration

Dừng writes ở hệ cũ, copy dữ liệu, xác minh rồi mở hệ mới.

Ưu điểm là consistency dễ hiểu hơn vì có cửa sổ freeze writes. Nhược điểm là downtime có thể dài; cần dữ liệu, index, sequence và external dependencies sẵn sàng; rollback khó nếu hệ mới đã nhận writes.

Phù hợp khi dataset nhỏ, downtime chấp nhận được và quy trình freeze/restore đã được diễn tập.

### 4.2. Trickle migration

Chuyển từng nhóm dữ liệu, tenant hoặc partition trong khi hệ thống vẫn hoạt động.

Ưu điểm là blast radius nhỏ, có thể học từ từng đợt. Nhược điểm là cần ownership/routing rõ, duy trì hai đường dữ liệu lâu và reconciliation phức tạp.

Phù hợp khi có ranh giới partition/tenant tương đối độc lập.

### 4.3. Strangler pattern

Từng capability được chuyển khỏi monolith. Gateway hoặc routing layer gửi request đến service mới khi capability sẵn sàng; phần còn lại tiếp tục ở monolith.

Ưu điểm là thay đổi dần, không cần thay toàn bộ ứng dụng một lần. Nhược điểm là giai đoạn trung gian có nhiều route, adapter, dữ liệu trùng và coupling.

Cần định nghĩa request nào thuộc service mới, request nào còn ở monolith và dữ liệu được ghi ở đâu.

### 4.4. Expand–migrate–contract

Thích hợp cho schema và contract:

1. **Expand:** thêm cột/table/field mới nhưng giữ đường cũ.
2. **Migrate:** backfill và cập nhật consumer để hiểu cả định dạng cũ/mới.
3. **Contract:** ngừng dùng cấu trúc cũ rồi mới xóa sau support window.

Cách này giảm nguy cơ một deploy làm app cũ không đọc được schema mới.

### 4.5. Chuyển theo domain hoặc tenant

Có thể chuyển Customer trước, sau đó Order, rồi Payment/Inventory khi dependency sẵn sàng. Một nhóm tenant có thể được route sang service mới qua feature flag.

Tránh chuyển một phần aggregate trong khi monolith vẫn ghi phần còn lại theo quy tắc cũ. Chọn partition sao cho giao dịch xuyên ranh giới có thể xử lý được.

## 5. Snapshot và CDC phải có mốc liên hệ

Một chiến lược phổ biến là snapshot kết hợp CDC:

~~~text
1. Chọn snapshot hoặc consistent point S.
2. Bắt đầu giữ CDC từ log position L0 tương ứng.
3. Backfill dữ liệu lịch sử tại S sang target.
4. Đọc CDC từ L0 và apply thay đổi sau snapshot.
5. Theo dõi lag đến khi target bắt kịp source.
6. Reconcile theo key, range và domain.
7. Chỉ cutover khi các điều kiện chấp nhận đạt.
~~~

Thứ tự khởi tạo snapshot và CDC phụ thuộc công cụ. Nếu bắt CDC quá muộn, thay đổi trong khoảng giữa có thể bị mất. Nếu bắt CDC trước snapshot nhưng không có transaction boundary rõ, event cũ có thể được áp dụng sai thứ tự.

Cần ghi lại:

- Snapshot identifier hoặc transaction boundary.
- CDC start position: LSN, binlog position, offset hoặc tương đương.
- Backfill range/checkpoint.
- Consumer checkpoint đã commit.
- Transform version.
- Target schema version.
- Số bản ghi đọc, ghi, bỏ qua và lỗi.
- Thời điểm dữ liệu đạt consistency condition.

Không chỉ ghi timestamp bắt đầu migration. Phải có mốc nối snapshot với stream changes theo semantics của database/CDC tool.

## 6. Backfill theo batch có thể resume

Với bảng lớn, không đọc toàn bảng vào memory. Dùng batch theo key ổn định:

~~~sql
SELECT id, customer_id, status, total_minor, updated_at
FROM legacy_orders
WHERE id > :last_seen_id
ORDER BY id
LIMIT :batch_size;
~~~

Đây là ví dụ cho primary key tăng dần. Không dùng offset pagination trên bảng lớn nếu offset ngày càng tốn kém hoặc rows thay đổi làm page bị lệch.

### 6.1. Chọn cursor

Cursor tốt nên có thứ tự ổn định và duy nhất, không thay đổi trong lúc scan, có index, ghi được checkpoint và không bỏ qua record khi insert/update.

Nếu key không tăng đơn điệu hoặc dùng composite key, dùng tuple cursor như (created_at, id) với điều kiện so sánh tương ứng. Không chỉ dùng updated_at nếu timestamp có thể trùng và thiếu tie-breaker.

### 6.2. Checkpoint đúng thứ tự

Sau mỗi batch:

1. Đọc range.
2. Transform và validate.
3. Upsert vào target theo idempotent key.
4. Xác minh đầu ra batch theo policy.
5. Chỉ sau khi target commit thành công mới lưu checkpoint tiến lên.

Nếu checkpoint commit trước target data, process crash có thể làm mất batch. Nếu target commit xong nhưng checkpoint chưa ghi, batch chạy lại; vì vậy upsert phải idempotent.

### 6.3. Batch size và throughput

Batch lớn tăng throughput nhưng có thể gây transaction dài, lock lâu, memory pressure, WAL backlog, throttling database nguồn và retry tốn kém. Batch nhỏ giảm blast radius nhưng tăng round trips.

Chọn bằng load test và giới hạn nguồn; theo dõi latency/lag. Không lấy batch size từ ví dụ làm chuẩn production.

## 7. CDC bắt thay đổi trong lúc backfill

CDC có thể đọc transaction log hoặc cơ chế capture tương đương để phát insert/update/delete. So với polling theo timestamp, log-based CDC thường giữ được nhiều metadata transaction và delete hơn, tùy công nghệ.

Các nguồn CDC có thể gồm:

- PostgreSQL logical decoding/WAL.
- MySQL binlog.
- SQL Server Change Data Capture.
- Debezium hoặc connector tương đương.
- Database provider change stream.
- Outbox table do ứng dụng chủ động ghi.

Mỗi nguồn có semantics riêng về transaction boundary, ordering, snapshot mode, tombstone, schema evolution, retention và delivery guarantee.

CDC không tự tạo ra một bản sao đúng. Phải xác định:

- Event đại diện row change hay business event?
- Thứ tự được bảo đảm trong phạm vi nào?
- Delete được biểu diễn ra sao?
- Snapshot event phân biệt với live event thế nào?
- Consumer restart có replay event không?
- Schema thay đổi trong lúc capture xử lý thế nào?
- Log retention đủ cho thời gian backfill/recovery không?
- Connector mất vị trí có thể resume hay phải snapshot lại?

CDC row-level phản ánh thay đổi database; nó không tự có ý nghĩa nghiệp vụ đầy đủ.

## 8. Tránh snapshot cũ ghi đè CDC mới

Ví dụ:

1. Snapshot đọc Order O1 ở version 10.
2. Source cập nhật O1 lên version 11.
3. CDC phát version 11.
4. Backfill chậm hơn và ghi snapshot version 10 sau CDC.
5. Target quay về trạng thái cũ.

Cần snapshot watermark và record version:

- Snapshot có mốc transaction/LSN nhất quán.
- CDC bắt đầu từ vị trí gắn với snapshot.
- Target apply thay đổi theo version/sequence.
- Nếu snapshot và CDC chạy song song, conditional upsert ngăn dữ liệu cũ ghi đè mới.
- Có thể stage snapshot rồi merge theo thứ tự đã xác định.

Không dùng updated_at đơn thuần làm version nếu timestamp lệch, trùng hoặc không đơn điệu. Tốt hơn dùng transaction sequence/row version có semantics rõ.

## 9. Idempotency: giả định event có thể được xử lý lại

CDC hoặc broker có thể replay event. Consumer cần chịu được duplicate:

~~~text
Event E-100 arrives -> apply
Consumer crashes before checkpoint
Event E-100 arrives again -> apply safely
~~~

Các cách:

- Event có ID duy nhất.
- Lưu processed-event ID hoặc inbox record.
- Upsert theo source primary key và version.
- Conditional update chỉ áp dụng version mới hơn.
- Business operation có idempotency key.
- Transaction gộp inbox/checkpoint và target mutation khi công nghệ hỗ trợ.

Ví dụ khái niệm PostgreSQL:

~~~sql
INSERT INTO target_orders(id, status, source_version)
VALUES (:id, :status, :version)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    source_version = EXCLUDED.source_version
WHERE target_orders.source_version < EXCLUDED.source_version;
~~~

Cần định nghĩa tie-breaker nếu nhiều event cùng version và bảo đảm version phản ánh thứ tự authoritative. Idempotent upsert không giải quyết event sai thứ tự nếu version không đáng tin.

## 10. Delete, tombstone và retention

Backfill thường chỉ đọc rows còn tồn tại trong source. Nếu record bị xóa sau snapshot, CDC phải truyền delete hoặc tombstone; nếu không target giữ record cũ mãi mãi.

Phân biệt:

- **Hard delete:** record biến mất khỏi source.
- **Soft delete:** cờ deleted/status được cập nhật.
- **Tombstone:** event biểu diễn key không còn tồn tại.
- **Retention delete:** xóa theo policy lưu trữ, có thể cần archive/audit.
- **Business cancellation:** trạng thái nghiệp vụ vẫn cần giữ lịch sử.

Không biến mọi loại delete thành hard delete ở target nếu service mới cần audit hoặc legal retention. Transform phải giữ semantics của dữ liệu.

## 11. Schema mapping và transform

Giữa hệ cũ và service mới, schema thường khác nhau:

- Monolith lưu customer_name trong Order row; service mới tham chiếu customer_id.
- Cột status cũ có 12 giá trị, service mới dùng state machine khác.
- Tiền cũ lưu decimal, service mới lưu integer minor units.
- Timestamp cũ không có timezone rõ.
- Một bảng cũ chứa cả địa chỉ giao hàng và địa chỉ hiện tại.
- Nullable fields được hiểu khác nhau.

Mỗi transform cần mô tả:

1. Source field và type.
2. Target field và type.
3. Mapping enum/status.
4. Default/null semantics.
5. Rounding/timezone/encoding.
6. Validation constraints.
7. Transform version.
8. Xử lý record lỗi.
9. Reversibility và dữ liệu không thể biểu diễn ngược.

| Source | Target | Quy tắc |
| --- | --- | --- |
| legacy_order_id | order_id | Giữ stable ID hoặc mapping table |
| total_decimal | total_minor | Convert theo currency scale và rounding policy |
| status = P | PAYMENT_PENDING | Mapping enum có version |
| deleted_at | deleted_at/tombstone | Không làm mất audit |
| created_local | UTC timestamp | Chỉ chuyển khi timezone nguồn xác định |

Không suy diễn timezone từ vị trí máy chủ hoặc locale hiện tại nếu dữ liệu lịch sử không ghi timezone.

## 12. Ownership và database-per-service

Khi tách monolith, có thể có giai đoạn service mới đọc database cũ. Đây có thể là bước chuyển tiếp, nhưng cần kế hoạch chấm dứt phụ thuộc.

1. Xác định bảng/aggregate thuộc domain nào.
2. Xác định write owner trong từng giai đoạn.
3. Tạo API hoặc event contract cho consumer.
4. Backfill domain data sang store mới.
5. Đồng bộ changes bằng CDC/outbox.
6. Chuyển reads theo cohort.
7. Chuyển writes sang service owner.
8. Ngăn monolith ghi trực tiếp vào dữ liệu đã chuyển.
9. Giữ compatibility adapter trong thời gian cần.
10. Gỡ quyền/đường truy cập cũ sau khi xác nhận không còn consumer.

Không để microservices cùng dùng chung một database schema lâu dài rồi gọi đó là database-per-service. Có thể dùng chung database server, nhưng **ownership và quyền thao tác dữ liệu** phải rõ.

## 13. Dual-run và shadow traffic

Shadow traffic sao chép request sang hệ thống mới nhưng không dùng response mới cho user và không cho phép side effects:

~~~text
Client -> Gateway -> Legacy implementation -> User response
                  \
                   -> New implementation -> Shadow result
                                              |
                                        Compare/log metrics
~~~

Ưu điểm: kiểm tra production-like traffic, serializer, query, latency và error mapping mà chưa chuyển quyền phục vụ.

Rủi ro:

- Shadow request tiêu thụ CPU/database/network.
- Nếu không chặn side effects, có thể gửi email, charge tiền hoặc ghi event hai lần.
- Dữ liệu nhạy cảm có thể bị copy sang vùng chưa được cấp quyền.
- Replay request không tái tạo đúng state tại thời điểm gốc.
- So sánh có thể sai nếu hai implementation đọc snapshot khác nhau.

Shadow phải read-only hoặc dùng side-effect sandbox. Không gửi lặp request production tới payment provider chỉ để so sánh response.

Có thể chọn sample theo tỷ lệ request, tenant nội bộ, SKU, operation ít rủi ro hoặc chỉ GET/read trước. Giữ correlation ID để đối chiếu nhưng không đưa PII/secret vào log.

## 14. Dual-write: hai lệnh ghi không phải một transaction

Ví dụ code ngây thơ:

~~~java
legacyRepository.save(order);
newOrderRepository.save(order);
~~~

Nếu lần đầu commit thành công nhưng lần hai timeout, hai nguồn lệch. Nếu retry toàn method, lần đầu có thể bị ghi lại hoặc side effect trùng. Hai database độc lập không có transaction ACID chung chỉ vì hai lệnh nằm trong cùng method Java.

Failure modes:

1. Legacy commit, target fail.
2. Target commit, legacy fail.
3. Cả hai commit nhưng caller mất response.
4. Một bên timeout nhưng thực tế đã commit.
5. Retry tạo side effect lần nữa.
6. Hai nơi có validation/default khác nhau.
7. Một bên rollback local nhưng bên kia đã commit.

**Dual-write không tự atomic.**

### 14.1. Transactional outbox

Nếu ứng dụng sở hữu database nguồn, có thể ghi business mutation và outbox record trong cùng transaction:

~~~sql
BEGIN;

UPDATE legacy_orders
SET status = 'CONFIRMED'
WHERE id = :order_id;

INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :order_id, 'OrderConfirmed', :payload);

COMMIT;
~~~

Publisher đọc outbox và gửi message. Nếu publisher crash sau publish nhưng trước khi đánh dấu sent, event có thể được gửi lại; consumer phải deduplicate.

Outbox bảo đảm **business mutation và ý định phát event** cùng commit trong database nguồn. Nó không tự làm broker, target DB và external side effects cùng commit một transaction.

### 14.2. Khi nào chọn CDC, outbox hay application dual-write?

| Cách | Phù hợp | Hạn chế |
| --- | --- | --- |
| Log-based CDC | Copy changes từ DB cũ, ít sửa application | Row-level semantics, connector/retention/schema dependency |
| Transactional outbox | Phát domain events từ application owner | Cần thay đổi app và vận hành publisher |
| Application dual-write | Một số migration nhỏ có kiểm soát | Partial commit, retry và ordering phức tạp |
| Polling updated_at | Hệ cũ đơn giản, volume thấp | Miss delete, timestamp/ordering, polling load |
| Database replication | Chuyển cả database hoặc read replica | Không tự giải quyết domain ownership |
| Batch export/import | Dataset nhỏ hoặc downtime cho phép | Không bắt changes sau export nếu không có cơ chế bổ sung |

Ưu tiên single write owner kết hợp outbox/CDC khi phù hợp. Chỉ dual-write trực tiếp khi consistency protocol, reconciliation và rollback plan được kiểm chứng.

## 15. Reconciliation: đối chiếu theo nhiều lớp

Reconciliation có thể chạy sau mỗi batch, liên tục trong CDC, trước cutover, trong canary, sau cutover hoặc sau incident.

Các lớp đối chiếu:

1. **Count:** tổng số record theo table/domain/partition.
2. **Key coverage:** key có ở source thì target có không.
3. **Field comparison:** trường quan trọng có cùng giá trị sau transform không.
4. **Aggregate:** tổng tiền, số lượng trạng thái, stock totals.
5. **Business invariants:** order total, payment capture uniqueness, inventory non-negative.
6. **Referential integrity:** liên kết giữa domain có tồn tại không.
7. **Event consistency:** outbox/event IDs đã được apply chưa.
8. **Freshness:** target theo kịp đến watermark nào.
9. **Security/tenant:** dữ liệu thuộc đúng tenant và access boundary.
10. **Behavioral comparison:** response legacy và new khác nhau ở đâu.

**Count khớp không chứng minh dữ liệu đúng.** Hai hệ thống có thể cùng một triệu rows nhưng một số rows sai key hoặc amount.

## 16. Hash và đối chiếu theo partition

Với bảng lớn, chia dữ liệu thành partition theo key/range rồi tạo digest:

~~~text
Partition 0000-0999:
  source count
  target count
  source checksum
  target checksum

Partition 1000-1999:
  source count
  target count
  source checksum
  target checksum
~~~

Hash chỉ hữu ích nếu canonicalization nhất quán:

- Chuẩn hóa field order.
- Phân biệt null và empty.
- Quy định encoding.
- Chuẩn hóa decimal/rounding.
- Chuẩn hóa timestamp/timezone.
- Loại field volatile chỉ khi policy cho phép.
- Không hash secret/plaintext credential.
- Version hóa thuật toán và field set.

Hash partition lệch cho biết có khác biệt; cần drill down theo key để tìm record. Không dùng checksum tổng nếu không thể khoanh vùng lỗi.

Một bản ghi Order có thể chuẩn hóa thành JSON gồm orderId, customerId, currency, totalMinor, status và lineItems. Thứ tự line items chỉ được sort nếu thứ tự không mang ý nghĩa nghiệp vụ.

## 17. Đối chiếu tiền và trạng thái

Tiền là nguồn sai lệch phổ biến:

- Legacy dùng decimal scale 2.
- Target dùng integer minor units.
- Currency có số chữ số thập phân khác nhau.
- Discount được làm tròn theo line hay order?
- Tax tính trước hay sau discount?
- Shipping fee có nằm trong total?
- Null amount là 0 hay unknown?

Không luôn nhân 100 để đổi sang minor units. Phải xác định currency scale, rounding, overflow và thứ tự tính toán; báo cáo chênh lệch theo từng currency.

Legacy status cũng có thể khác target state machine. Ví dụ status P có thể map thành PAYMENT_PENDING, nhưng cần xét lịch sử chuyển trạng thái và các giao dịch liên quan. Order CANCELLED nhưng Payment đã CAPTURED chưa refund không thể được coi là một mapping đơn giản.

Reconciliation nên đối chiếu **cross-domain state**, ví dụ Order–Payment–Inventory, không chỉ status từng bảng.

## 18. Phân loại discrepancy và xử lý

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Expected transform | Legacy enum P thành PAYMENT_PENDING | Đánh dấu mapping hợp lệ |
| Missing target record | Source có order, target không có | Replay/backfill theo key |
| Stale target | Target có version cũ | Apply CDC mới hơn |
| Duplicate target | Hai records cùng logical ID | Deduplicate theo rule và lineage |
| Unexpected target only | Target có record không có source | Xác minh nguồn phát sinh, không tự xóa |
| Semantic mismatch | Total/status khác | Điều tra business rule/transform |
| Referential gap | Order trỏ customer không tồn tại | Sửa dependency hoặc quarantine |
| Unauthorized data | Record thuộc tenant sai | Cô lập và xử lý như incident bảo mật |
| Legacy ambiguity | Không xác định timezone/status cũ | Manual review/business decision |

Mỗi discrepancy nên có stable key, source/target version, field khác biệt, severity, owner, action/reason, retry count, checkpoint và audit trail.

Không dùng job copy source đè target cho mọi trường hợp. Sau cutover, source cũ thường không còn là authority; copy mù có thể ghi đè write hợp lệ ở target.

## 19. CDC lag, watermark và cutover readiness

Theo dõi:

- Source log position.
- Position đã đọc.
- Position đã apply vào target.
- Tuổi event cũ nhất chưa xử lý.
- Queue depth/backlog.
- Retry, dead-letter và poison records.
- Schema version và transform version.
- Connector restart/rebalance.
- Log retention còn lại ở source.

Lag theo giây có thể gây hiểu nhầm nếu traffic không đều; bổ sung log position và age of oldest unapplied event.

Trước cutover có thể yêu cầu:

- Backfill hoàn tất mọi partition.
- CDC apply tới watermark đã xác định.
- Không còn poison event chưa phân loại trong phạm vi bắt buộc.
- Reconciliation không còn discrepancy nghiêm trọng.
- Target đạt freshness threshold.
- Soak window không phát sinh sai lệch mới.

Watermark phải có nghĩa kỹ thuật và tái tạo được. Đừng chỉ nói CDC gần realtime mà không đo lag.

## 20. Dual-read và fallback

Có ba kiểu:

1. **Compare-only:** trả kết quả source chính, đọc target nền để so sánh.
2. **Canary read:** một cohort nhận response từ target.
3. **Fallback read:** target lỗi thì đọc source cũ nếu dữ liệu và semantics cho phép.

Rủi ro gồm tăng tải, snapshot khác nhau, stale fallback sau khi target nhận write mới, cache freshness khác và authorization khác.

Khi so sánh, nên dùng cùng source version/watermark hoặc chỉ đánh giá record ổn định trước mốc. Nếu không, mismatch rate có thể phản ánh replication lag hợp lệ thay vì lỗi transform.

Fallback phải nói rõ response là stale hay unavailable. Không dùng legacy read để xác nhận payment chưa diễn ra nếu legacy không còn là authority.

## 21. Dual-write có kiểm soát

Nếu bắt buộc ghi cả hai hệ thống trong giai đoạn chuyển tiếp:

- Chỉ định một primary write owner.
- Ghi mutation và outbox trong cùng transaction tại owner.
- Replicate sang target bằng event có ID/version.
- Consumer idempotent.
- Reconciliation liên tục.
- Không để target tự phát side effect lần hai.
- Có retry/dead-letter và replay runbook.
- Theo dõi partial success.
- Xác định thời điểm ngừng ghi source cũ.

Vận hành có thể theo dõi trạng thái:

- **COMMITTED_AT_SOURCE:** source transaction đã commit.
- **PENDING_REPLICATION:** event chưa được target apply.
- **APPLIED_AT_TARGET:** target đã apply event/version.
- **RECONCILIATION_REQUIRED:** hai nơi khác nhau ngoài policy.
- **FAILED_PERMANENT:** cần can thiệp.

Đây là trạng thái nội bộ để quan sát, không nhất thiết là business API contract.

## 22. Cutover: chuyển quyền đọc và ghi theo điều kiện

Cutover nên là một state machine có điều kiện:

1. **Pre-check:** backfill hoàn tất, CDC lag trong ngưỡng, target đủ capacity.
2. **Freeze risky changes:** hạn chế schema/behavior changes trong cửa sổ cutover.
3. **Drain:** xử lý request/transaction đang chạy ở source theo policy.
4. **Final sync:** chờ CDC tới watermark cuối.
5. **Reconcile:** kiểm tra key coverage, aggregates, invariants và discrepancy quan trọng.
6. **Switch reads:** chuyển cohort đọc sang target.
7. **Observe:** theo dõi latency, errors, mismatch và business metrics.
8. **Switch writes:** chuyển owner ghi theo giao thức; không để hai authority.
9. **Stop old writers:** thu hồi quyền ghi cũ và xác minh.
10. **Post-cutover reconcile:** tiếp tục đối chiếu trong soak window.
11. **Retire old path:** chỉ sau khi hết consumer, retention và rollback dependencies.

Có thể chuyển read theo 1%, 5%, 10%, 25%, 50%, rồi 100%. Nhưng **write canary khó hơn read canary**: không được ngẫu nhiên gửi cùng aggregate đến hai writer. Cần partition ownership hoặc một authority rõ ràng.

## 23. Rollback và roll-forward

Rollback ứng dụng không nhất thiết rollback dữ liệu. Trước khi quay lại, cần biết:

- Schema mới có field/table mà code cũ không hiểu?
- Target đã nhận writes chưa?
- Những writes đó có được đồng bộ ngược source?
- Source còn quyền ghi không?
- Event consumers đã tạo external side effects chưa?
- Có thể map target state về source mà không mất semantics?
- Có migration destructive hoặc một chiều không?

### 23.1. Trước write cutover

Nếu hệ mới chỉ chạy shadow/read compare và chưa nhận authoritative writes, có thể tắt shadow, giữ source làm chính và sửa lỗi tương đối đơn giản.

### 23.2. Sau write cutover

Có thể cần:

- Replicate/translate target writes về source trong compatibility window.
- Dừng writes, export và reconcile trước khi đưa source trở lại.
- Giữ target làm source of truth nhưng rollback application version tương thích target.
- Roll-forward sửa lỗi thay vì chuyển dữ liệu ngược.
- Restore backup/PITR nếu dữ liệu hỏng rồi reconcile external side effects.

**Không tự động đổi route về legacy khi target đã có dữ liệu mới mà legacy không có.** Điều đó có thể làm mất đơn hoặc lặp thanh toán.

### 23.3. Roll-forward

Roll-forward thường an toàn hơn khi schema/data format đã thay đổi không đảo ngược. Có thể deploy bản sửa, repair dữ liệu có checkpoint và giữ authority tại target. Quyết định rollback/roll-forward phải có runbook trước cutover.

## 24. Expand–migrate–contract khi hai phiên bản cùng chạy

~~~text
Expand:
  Thêm field/table mới, giữ field cũ.
  Application cũ vẫn chạy.

Migrate:
  Backfill sang cấu trúc mới.
  Consumer mới hiểu old + new.
  Đồng bộ thay đổi bằng CDC/outbox.

Contract:
  Chuyển hết consumer.
  Ngừng ghi field cũ.
  Xác minh không còn read path cũ.
  Sau support window mới xóa field/table.
~~~

Không thêm NOT NULL column không có default rồi deploy khi code cũ chưa cung cấp giá trị. Không drop/rename cột trước khi mọi consumer cũ đã rời khỏi.

Compatibility window cần xét app version, event/schema cũ còn trong queue, CDC backlog, backup restore và khả năng rollback image đọc data mới.

## 25. Transaction boundaries và thứ tự dependency

Một transaction legacy có thể cập nhật nhiều bảng. CDC row-level có thể phát các thay đổi riêng; nếu target xử lý một phần trước phần còn lại, có thể thấy trạng thái trung gian.

Cần xem connector có giữ transaction metadata và ordering không. Nếu domain cần atomic aggregate, có thể:

- Gộp thay đổi theo transaction boundary.
- Dùng outbox domain event trong cùng transaction.
- Stage rồi apply nguyên lô.
- Chỉ expose target record khi aggregate đủ dữ liệu.
- Có trạng thái migration-incomplete và không phục vụ read sớm.

Thứ tự backfill theo dependency graph có thể là Customer/reference data, Inventory baseline, Order, Payment references, Shipping rồi read models. Đây là ví dụ; một số domain cần snapshot đồng bộ tại cùng mốc.

Nếu có cyclic references, cân nhắc staged import, placeholder có kiểm soát hoặc tách aggregate reference; không bỏ integrity checks vĩnh viễn.

## 26. Identity mapping và khóa dữ liệu

Nếu source và target dùng key khác nhau, cần mapping ổn định:

- Legacy numeric ID sang UUID mới.
- Customer ID cũ sang service-owned ID.
- Composite key sang stable external key.
- Tenant namespace.
- Foreign key sang reference qua API/event.

Mapping table nên có legacy key, target key, domain, batch, status và audit. Cần uniqueness constraint, backup và cơ chế resume.

Không tái sử dụng ID theo cách có thể nhầm record mới với record cũ. Nếu giữ nguyên ID, vẫn cần kiểm tra namespace, tenant và collision khi service mới tạo record trong lúc backfill.

## 27. Performance và bảo vệ database nguồn

Backfill có thể làm source database quá tải:

- Full table scans cạnh tranh với OLTP.
- CDC đọc WAL/binlog tăng I/O.
- Target writes tạo network/CPU pressure.
- Reconciliation hash đọc lại dữ liệu.
- Index build làm tăng disk usage.
- Retry batch lặp lại load.

Biện pháp:

- Giới hạn QPS/concurrency theo nguồn.
- Chia batch và pause/resume.
- Ưu tiên workload production.
- Dùng read replica nếu semantics snapshot phù hợp.
- Theo dõi CPU, IOPS, locks, replication lag và WAL retention.
- Chạy reconciliation ngoài peak hoặc theo partition.
- Có kill switch cho migration worker.
- Không để backlog vượt log retention CDC.

Worker nhanh nhưng làm latency production tăng gấp ba không phải migration thành công.

## 28. Observability và dashboard migration

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Backfill | Rows scanned/applied/failed | Tiến độ và lỗi |
| Checkpoint | Last key/partition completed | Resume và coverage |
| CDC | Source position, applied position, lag | Độ bắt kịp |
| Errors | Retry, poison records, dead-letter | Thay đổi chưa xử lý |
| Reconciliation | Match/mismatch by type/severity | Tính đúng đắn |
| Target | Write latency, DB CPU, index growth | Khả năng tiếp nhận |
| Source | Query latency, locks, WAL/binlog retention | Ảnh hưởng hệ cũ |
| Cutover | Traffic share, read/write owner | Trạng thái chuyển |
| Business | Orders, captures, stock, refunds | Kết quả nghiệp vụ |
| Security | Tenant violations, unexpected access | Bảo vệ dữ liệu |

Dashboard không chỉ báo số rows migrated. Cần coverage theo domain, severity, aggregate và business invariants. 99,9% rows migrated vẫn có thể bỏ sót một payment quan trọng.

Tránh raw customerId/orderId hoặc secret trong high-cardinality metrics labels. Dùng trace/audit có kiểm soát để điều tra record cụ thể.

## 29. Data quality và quarantine

Record lỗi transform không nên âm thầm bị skip. Quarantine record nên lưu:

- Source key và source version.
- Batch/event ID.
- Transform version.
- Error category.
- Diagnostic đã loại PII/secret không cần thiết.
- Retryability.
- Owner và status.
- Timestamp và audit.
- Quyết định sửa dữ liệu hoặc chấp nhận ngoại lệ.

Phân biệt lỗi tạm thời với lỗi dữ liệu:

- **Transient:** timeout, rate limit, network reset; retry bounded.
- **Permanent mapping:** enum chưa có mapping; cần sửa transform hoặc quyết định nghiệp vụ.
- **Constraint violation:** duplicate key, missing parent; điều tra source/ordering.
- **Security violation:** tenant mismatch; dừng và raise incident.
- **Schema mismatch:** producer version không tương thích; cập nhật consumer/contract.

Không retry vô hạn permanent errors; nó tạo backlog và che lỗi gốc.

## 30. Security và privacy trong migration

Dữ liệu migration thường có PII, payment references và thông tin nhạy cảm. Cần:

- Xác định data classification và allowed destination.
- Encryption in transit và at rest.
- Least privilege cho source reader, target writer và operator.
- Tách credential migration khỏi credential runtime.
- Mask/tokenize dữ liệu trong môi trường test.
- Không copy secret, password hash hoặc payment data nếu không cần.
- Audit ai đọc, export, transform, restore và xóa.
- Retention của export files, staging tables và quarantine.
- Data residency và tenant boundaries.
- Secure deletion sau khi nguồn cũ hết retention và có phê duyệt.

Shadow traffic và CDC có thể sao chép dữ liệu sang nhiều nơi hơn dự kiến. Kiểm tra privacy/access policy trước khi bật.

## 31. Kiểm thử migration trước production

Một bài test có ý nghĩa cần dataset và failure modes đại diện:

1. Functional mapping: enum, null, timezone, money, IDs.
2. Volume test: kích thước gần production.
3. Backfill resume: kill worker giữa batch rồi resume.
4. CDC replay: duplicate, out-of-order, restart, schema change.
5. Delete handling: hard delete, soft delete, tombstone.
6. Concurrent updates: source thay đổi trong lúc backfill.
7. Dual-run compare: cùng input và snapshot/version.
8. Reconciliation: count, hash, totals và invariants.
9. Cutover drill: switch reads/writes trong môi trường gần thật.
10. Rollback drill sau khi target đã có writes.
11. Performance: ảnh hưởng source, target và CDC lag.
12. Security: tenant isolation, access, logs và secret handling.

Không chỉ test happy path với vài chục rows. Cần thử process crash, timeout sau commit, duplicate event và target unavailable.

## 32. Runbook theo giai đoạn

### A. Discovery và thiết kế

- Kiểm kê bảng, volume, indexes, constraints và consumers.
- Chọn domain ownership.
- Định nghĩa source of truth từng phase.
- Ghi schema mapping và business invariants.
- Xác định snapshot/CDC semantics.
- Chốt freshness, rollback và cutover conditions.
- Định danh owner/escalation.

### B. Prepare target

- Tạo schema/indexes và access policy.
- Tạo mapping tables/checkpoints.
- Thiết lập CDC/outbox connector.
- Test target capacity, permissions và encryption.
- Deploy consumer idempotent và quarantine.
- Đặt dashboards/alerts và kill switch.

### C. Snapshot/backfill

- Chọn consistent snapshot và CDC start position.
- Chạy batch theo key/partition.
- Upsert idempotent, checkpoint sau target commit.
- Track rows/errors/lag.
- Pause khi source bị ảnh hưởng.
- Re-run failed batches có kiểm soát.

### D. Catch-up/reconciliation

- Apply CDC liên tục.
- Theo dõi watermark và log retention.
- Reconcile theo partition/key/aggregate.
- Điều tra mismatch và repair có audit.
- So sánh behavior shadow với cùng input.
- Chờ soak window đạt điều kiện.

### E. Cutover

- Freeze risky schema/behavior changes.
- Drain source writes theo policy.
- Chờ final CDC watermark.
- Xác minh reconciliation và invariants.
- Chuyển reads rồi writes theo state machine.
- Thu hồi old write path.
- Theo dõi business/technical metrics.

### F. Stabilize/retire

- Tiếp tục reconciliation.
- Theo dõi error, latency, duplicate và stale read.
- Xử lý consumer còn đọc nguồn cũ.
- Archive/retain nguồn cũ theo chính sách.
- Chỉ xóa dữ liệu cũ khi có approval và restore evidence.
- Cập nhật runbook và ownership.

## 33. Cutover gates

| Gate | Điều kiện minh họa | Bằng chứng |
| --- | --- | --- |
| Backfill | Tất cả partitions hoàn tất | Checkpoint và batch manifest |
| CDC | Lag dưới ngưỡng trong soak window | Source/target positions |
| Data coverage | Key coverage đạt yêu cầu | Reconciliation report |
| Critical invariants | Không còn mismatch nghiêm trọng | Business validation |
| Performance | Target đáp ứng SLO | Load/canary metrics |
| Security | Quyền và tenant isolation đã test | Audit/security checks |
| Rollback | Đường rollback/roll-forward đã diễn tập | Drill record |
| Ownership | Một writer owner được xác định | Authority/config/audit |
| Dependencies | Consumer, webhook, jobs đã route đúng | Inventory và telemetry |
| Operations | On-call/runbook/alerts sẵn sàng | Readiness sign-off |

Ngưỡng số phải do owner xác định. Không đặt “99,99% rows match” mà bỏ qua payment mismatch nghiêm trọng.

## 34. Xử lý discrepancy sau cutover

Nếu phát hiện sai khác sau khi target đã là source of truth:

1. Xác định key/domain và source version.
2. Kiểm tra target đã nhận writes mới chưa.
3. Không tự copy source cũ đè target.
4. Phân loại discrepancy và đánh giá ảnh hưởng.
5. Xác định authoritative record theo owner hiện tại.
6. Tạo correction command/event có idempotency.
7. Chạy repair có checkpoint và audit.
8. Đối chiếu lại invariant.
9. Ghi nguyên nhân và thêm test ngăn tái diễn.

Sau cutover, legacy data thường là snapshot hoặc record lịch sử, không còn là authority. Reconciliation phải biết hướng sửa dựa trên owner hiện tại.

## 35. Ví dụ Java: consumer CDC idempotent theo version

~~~java
public record OrderChange(
    String eventId,
    String orderId,
    long sourceVersion,
    String status
) {}

public interface ProcessedEventStore {
    boolean alreadyProcessed(String eventId);
    void markProcessed(String eventId);
}

public interface OrderTargetStore {
    void upsertIfNewer(
        String orderId,
        long sourceVersion,
        String status
    );
}

public final class OrderChangeHandler {
    private final ProcessedEventStore events;
    private final OrderTargetStore target;

    public OrderChangeHandler(
            ProcessedEventStore events,
            OrderTargetStore target
    ) {
        this.events = events;
        this.target = target;
    }

    public void handle(OrderChange change) {
        if (events.alreadyProcessed(change.eventId())) {
            return;
        }

        target.upsertIfNewer(
            change.orderId(),
            change.sourceVersion(),
            change.status()
        );

        events.markProcessed(change.eventId());
    }
}
~~~

Đây là skeleton minh họa, chưa bảo đảm atomicity giữa target upsert và processed-event record. Nếu process crash sau upsert nhưng trước markProcessed, event replay. Upsert theo version có thể an toàn trong điều kiện version đúng; nếu mutation tạo side effect khác, cần transaction/inbox/outbox thích hợp.

Trong production:

- Gộp dedup và target mutation trong cùng transaction nếu cùng database.
- Nếu khác store, dùng inbox/outbox, idempotent state transition và reconciliation.
- Duplicate event ID với payload khác là lỗi dữ liệu, không bỏ qua mù.
- Kiểm soát ordering và sourceVersion.
- Quarantine poison messages.
- Chỉ commit offset/checkpoint khi durable processing theo contract.

## 36. Ví dụ đối chiếu tổng tiền

Giả sử có 100.000 orders. Báo cáo theo currency:

| Currency | Source count | Target count | Source total | Target total | Chênh lệch |
| --- | ---: | ---: | ---: | ---: | ---: |
| VND | 80.000 | 80.000 | 120.000.000.000 | 120.000.000.000 | 0 |
| USD | 15.000 | 15.000 | 2.500.000 | 2.499.950 | -50 |
| JPY | 5.000 | 5.000 | 40.000.000 | 40.000.000 | 0 |

Số liệu minh họa. Count khớp nhưng USD total lệch 50 đơn vị; cần drill down theo order/line, kiểm tra rounding, discount, currency scale và refund/cancel. Không bù chênh lệch bằng update tổng chung; cần tìm record và quy tắc gây ra.

Báo cáo nên có count by status/tenant/currency/date, distinct keys, null/invalid fields, duplicate IDs, orphan references, CDC watermark, lag, severity và owner.

## 37. Những anti-pattern thường gặp

1. Copy toàn bộ bảng một lần trong giờ cao điểm.
2. Backfill xong mới bật CDC, làm mất khoảng thay đổi giữa hai bước.
3. Dùng updated_at không có tie-breaker để poll.
4. Commit checkpoint trước khi target ghi bền.
5. CDC consumer không idempotent.
6. Không xử lý delete/tombstone.
7. Snapshot cũ ghi đè CDC mới.
8. Không version hóa transform.
9. Mapping enum bằng default chung làm sai state.
10. Đổi decimal sang minor units bằng cách luôn nhân 100.
11. Dual-write hai repository tuần tự và giả định atomic.
12. Shadow traffic vẫn gọi external side effects.
13. So sánh source/target ở hai snapshot khác nhau.
14. Chỉ đối chiếu row count.
15. Chỉ báo match rate, không phân loại severity.
16. Sửa discrepancy bằng cách copy source đè target sau cutover.
17. Cutover khi CDC lag vẫn tăng.
18. Chuyển reads/writes mà không xác định owner.
19. Rollback app nhưng quên target đã nhận dữ liệu mới.
20. Giữ monolith quyền ghi sau khi service mới nhận quyền.
21. Quên jobs, webhooks, reports và partner consumers.
22. Không đo ảnh hưởng backfill đến database nguồn.
23. Retry poison record vô hạn.
24. Ghi PII/secret vào quarantine/log.
25. Xóa database cũ trước retention/restore window.
26. Không diễn tập cutover/rollback trên dữ liệu đại diện.

## 38. Checklist triển khai

### Thiết kế và ownership

- [ ] Có owner cho từng domain/table/aggregate.
- [ ] Có source of truth theo từng migration phase.
- [ ] Có business invariants và mapping rules.
- [ ] Có stable keys/ID mapping và tenant boundaries.
- [ ] Schema/transform được version hóa.
- [ ] Có compatibility window và deprecation plan.

### Backfill và CDC

- [ ] Snapshot và CDC start position có liên hệ rõ.
- [ ] Backfill dùng keyset pagination/batch.
- [ ] Checkpoint chỉ tiến sau target commit.
- [ ] Consumer idempotent và xử lý out-of-order.
- [ ] Delete/tombstone và schema changes được xử lý.
- [ ] Lag, backlog, log retention và poison events có dashboard.
- [ ] Có pause/resume/kill switch và quarantine.

### Dual-run và reconciliation

- [ ] Shadow requests không tạo side effects.
- [ ] So sánh cùng input/snapshot/watermark.
- [ ] Có count, key, field, aggregate và invariant checks.
- [ ] Sai khác có severity/owner/action.
- [ ] Không chỉ dựa vào row count/hash tổng.
- [ ] Có cross-domain reconciliation cho Order/Payment/Inventory.

### Cutover và recovery

- [ ] Có cutover gates và soak window.
- [ ] Có một write owner rõ ràng.
- [ ] Old write path được thu hồi và xác minh.
- [ ] Rollback/roll-forward đã diễn tập sau khi target có writes.
- [ ] Không xóa nguồn cũ trước retention/restore sign-off.
- [ ] Có audit, on-call và runbook cho discrepancy.

## 39. Câu hỏi tự kiểm tra

**1. Backfill và CDC khác nhau thế nào?**  
Backfill chuyển dữ liệu lịch sử; CDC bắt thay đổi phát sinh sau mốc log/transaction để target bắt kịp source.

**2. Vì sao phải liên kết snapshot với CDC starting position?**  
Để không bỏ sót changes giữa snapshot và lúc capture bắt đầu, cũng không áp dụng event cũ sai thứ tự.

**3. Vì sao backfill cần idempotent upsert?**  
Batch có thể chạy lại sau crash; upsert an toàn giúp không tạo duplicates hoặc lùi dữ liệu.

**4. Dual-run có bắt buộc dual-write không?**  
Không. Có thể shadow implementation mới và chỉ dùng một write owner.

**5. Vì sao dual-write hai database không atomic?**  
Một commit có thể thành công còn commit kia thất bại/timeout; không có transaction chung tự động.

**6. Outbox giải quyết vấn đề gì?**  
Ghi business mutation và ý định phát event trong cùng transaction nguồn; publisher retry và consumer deduplicate.

**7. Count khớp có chứng minh migration đúng?**  
Không. Field values, keys, aggregates, relationships và business invariants vẫn có thể sai.

**8. Vì sao phải xử lý delete/tombstone?**  
Nếu chỉ insert/update, target giữ record đã bị xóa ở source.

**9. Vì sao updated_at đơn thuần có thể không đủ làm cursor?**  
Timestamp có thể trùng, lệch hoặc không đơn điệu; cần tie-breaker/version/transaction position đáng tin.

**10. Khi nào rollback về monolith nguy hiểm?**  
Khi target đã nhận writes hoặc schema/state mới mà legacy không thể biểu diễn hoặc chưa được đồng bộ ngược.

**11. Vì sao shadow traffic cần chặn side effects?**  
Request lặp có thể charge tiền, gửi email hoặc tạo order lần thứ hai.

**12. Reconciliation sau cutover nên sửa theo hướng nào?**  
Theo source of truth hiện tại của domain, có phân loại, idempotency, checkpoint và audit.

**13. Vì sao phải đối chiếu tiền theo currency?**  
Currency có scale và rounding khác nhau; cộng chung hoặc luôn nhân 100 có thể sai.

**14. CDC lag bằng 0 trong metric có đủ để cutover?**  
Chưa; cần watermark thực, backlog/poison events, snapshot coverage và business invariants.

**15. Khi nào có thể retire database cũ?**  
Khi không còn consumer/write path cần nó, retention/backup/legal requirements được đáp ứng và rollback/recovery window được phê duyệt.

## 40. Tài liệu tham khảo

- Martin Fowler — Strangler Fig Application: https://martinfowler.com/bliki/StranglerFigApplication.html
- Martin Fowler — Parallel Change: https://martinfowler.com/bliki/ParallelChange.html
- Debezium Documentation: https://debezium.io/documentation/
- Debezium — Outbox Event Router: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- PostgreSQL — Logical Decoding: https://www.postgresql.org/docs/current/logicaldecoding.html
- PostgreSQL — WAL: https://www.postgresql.org/docs/current/wal.html
- AWS Prescriptive Guidance — Database migration strategies: https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-databases/welcome.html
- AWS Prescriptive Guidance — CDC migration pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/migrate-data-by-using-change-data-capture.html
- Google Cloud — Database migration concepts: https://cloud.google.com/architecture/database-migration-concepts-principles
- Microsoft — Data architecture guide: https://learn.microsoft.com/en-us/azure/architecture/data-guide/
- Apache Kafka — Documentation: https://kafka.apache.org/documentation/
- OpenTelemetry — Observability concepts: https://opentelemetry.io/docs/concepts/

**Ghi nhớ:** Migration dữ liệu an toàn cần một **nguồn có thẩm quyền rõ theo từng giai đoạn**, snapshot và CDC có watermark, backfill idempotent, dual-run không tạo side effect, reconciliation theo cả dữ liệu lẫn bất biến nghiệp vụ, và cutover/rollback được diễn tập. Chỉ khi target đã bắt kịp, sai khác quan trọng được xử lý và quyền ghi cũ được kiểm soát thì mới nên coi việc chuyển đổi là hoàn tất.
