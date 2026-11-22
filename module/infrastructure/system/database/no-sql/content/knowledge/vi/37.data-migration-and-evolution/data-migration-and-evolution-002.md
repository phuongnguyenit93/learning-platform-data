# Chuyển mô hình quan hệ sang khóa–giá trị, tài liệu, cột rộng hoặc đồ thị

Một ứng dụng đặt chỗ được xây bằng Java và cơ sở dữ liệu quan hệ có các bảng **customers**, **properties**, **bookings**, **booking_items**, **payments** và **property_tags**. Các khóa ngoại và câu lệnh JOIN giúp nhóm phát triển đi từ customer đến booking rồi đến property và payment. Khi tải tăng, ứng dụng muốn đưa một số chức năng sang NoSQL để phục vụ tra cứu độ trễ thấp, hiển thị booking timeline, xử lý lượng ghi lớn hoặc truy vấn mạng quan hệ.

Câu hỏi không phải: “Đổi sáu bảng SQL thành sáu collection NoSQL như thế nào?”. Câu hỏi đúng hơn là:

- Người dùng thực sự đọc/ghi dữ liệu theo những đường nào?
- Các truy vấn nào cần trả trong 20 ms và truy vấn nào được xử lý bất đồng bộ?
- Bất biến nào trước đây do FOREIGN KEY, UNIQUE, CHECK và transaction bảo vệ?
- Những bản sao dữ liệu nghiệp vụ nào phải cập nhật đồng bộ, bản sao nào được phép trễ?
- Nếu một booking thay đổi hoặc bị xóa, bao nhiêu mô hình đọc và chỉ mục phải cập nhật?
- Có thể di chuyển từng đường truy cập mà vẫn bảo toàn dữ liệu và rollback không?

Bài thuộc **Database No SQL → Di chuyển và thay đổi**, giải thích cách chuyển mô hình quan hệ sang bốn họ mô hình thường gặp:

1. **Khóa–giá trị (key–value):** tối ưu các phép truy cập theo khóa xác định; các truy vấn khác cần chỉ mục/bảng dẫn xuất hoặc dữ liệu bổ sung.
2. **Tài liệu (document):** nhóm dữ liệu được đọc và cập nhật cùng nhau thành document, với lựa chọn nhúng hay tham chiếu có chủ đích.
3. **Cột rộng (wide-column):** thiết kế partition key, clustering columns và các bảng theo đường truy vấn; đặc biệt chú ý phân phối tải và truy vấn theo phạm vi.
4. **Đồ thị (graph):** mô hình thực thể cùng quan hệ/cạnh khi traversal là truy vấn chủ đạo, đồng thời kiểm soát độ sâu và fan-out.

Bài cũng xây dựng quy trình **backfill, CDC, so sánh song song, cutover, rollback**, các ví dụ Java 21, bảng đánh đổi, những tình huống cần giữ SQL và kế hoạch kiểm thử.

> **Nguyên tắc:** Chuyển sang NoSQL là **thiết kế lại mô hình dữ liệu theo access patterns và hợp đồng nhất quán**, không chỉ đổi cú pháp SQL thành API của driver. Mỗi ràng buộc và JOIN bỏ đi phải có một phương án rõ: **đọc bằng key, tiền tính toán, materialized view, transaction/conditional write, reconciliation hoặc chấp nhận eventual consistency với giới hạn được công bố**.

> **Phạm vi:** NoSQL không phải một engine thống nhất. Redis thường được dùng cho key–value và cache; DynamoDB kết hợp key–value/document với partition/sort key và secondary indexes; MongoDB đại diện document; Cassandra và HBase là các ví dụ wide-column với semantics khác nhau; Neo4j là ví dụ graph. Phải kiểm tra khả năng transaction, index, partition, TTL, giới hạn kích thước và mức nhất quán của đúng phiên bản/nhà cung cấp trước khi triển khai.

## 1. Bắt đầu từ mô hình quan hệ đang có

Một schema minh họa:

~~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    email VARCHAR(256) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    UNIQUE (tenant_id, email)
);

CREATE TABLE properties (
    property_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    host_customer_id VARCHAR(64) NOT NULL,
    title VARCHAR(256) NOT NULL,
    city VARCHAR(128) NOT NULL,
    FOREIGN KEY (host_customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE bookings (
    booking_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    property_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_minor BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL,
    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id),
    FOREIGN KEY (property_id)
        REFERENCES properties(property_id)
);

CREATE TABLE booking_items (
    booking_id VARCHAR(64) NOT NULL,
    item_no INTEGER NOT NULL,
    description VARCHAR(256) NOT NULL,
    amount_minor BIGINT NOT NULL,
    PRIMARY KEY (booking_id, item_no),
    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
);

CREATE TABLE payments (
    payment_id VARCHAR(64) PRIMARY KEY,
    booking_id VARCHAR(64) NOT NULL,
    amount_minor BIGINT NOT NULL,
    state VARCHAR(32) NOT NULL,
    provider_operation_id VARCHAR(128),
    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
);
~~~~

Đây chỉ là schema minh họa, chưa bao gồm mọi ràng buộc cho tenancy, unique booking slot, tài chính và định dạng thời gian. Trong thực tế, các foreign keys chỉ an toàn theo phạm vi schema/engine và ứng dụng vẫn phải bảo đảm identity/tenant authorization.

### 1.1. Một query thường thấy

~~~~sql
SELECT b.booking_id,
       b.status,
       b.total_minor,
       c.display_name,
       p.title,
       p.city
FROM bookings b
JOIN customers c ON c.customer_id = b.customer_id
JOIN properties p ON p.property_id = b.property_id
WHERE b.tenant_id = ?
  AND b.customer_id = ?
ORDER BY b.created_at DESC, b.booking_id DESC
LIMIT 30;
~~~~

Nếu ứng dụng luôn cần màn hình danh sách booking cho một customer, có thể đặt một **read model** chứa các trường cần hiển thị vào một document/bảng theo customer. Nhưng nếu lưu trùng customer displayName và property title, cần quy tắc cập nhật khi customer đổi tên hoặc property đổi tiêu đề.

### 1.2. Các bất biến SQL đang cung cấp

- Primary key: không có hai rows cùng booking_id.
- Unique constraint: một email không trùng trong tenant theo policy.
- Foreign key: booking tham chiếu customer/property hợp lệ.
- Transaction: nhóm cập nhật có thể commit/rollback cùng nhau theo engine/isolation.
- Check constraint: giá trị miền hợp lệ nếu khai báo.
- Query optimizer: JOIN và nhiều access paths dựa trên index.
- Consistency: read/write và isolation theo cấu hình SQL.

Khi chuyển sang NoSQL, **không được mặc định những bảo đảm này tồn tại ở cùng phạm vi**.

## 2. Inventory đường truy cập thay vì chuyển bảng một–một

Lập bảng từ telemetry và nhu cầu thực:

| Đường truy cập | Ví dụ | Truy cập chủ đạo | Mục tiêu |
| --- | --- | --- | --- |
| Booking theo ID | GET /bookings/B-91 | Point read | p99 thấp |
| Booking của customer | GET /customers/C-2/bookings | Theo tenant/customer, sorted recent | Cursor pagination |
| Booking theo property/day | Lịch phòng hôm nay | Partition/range | Nhiều reads |
| Tạo booking | POST /bookings | Conditional write và inventory invariant | Không double-book |
| Cập nhật trạng thái | Confirm/cancel | Versioned mutation | Không lost update |
| Payment state | Reconcile webhook | Operation ID/idempotency | Không double charge |
| Search properties | City/amenities/text | Text + filters | Eventual freshness cho phép |
| Gợi ý liên quan | Customer–property–tag graph | Traversal | Fan-out có giới hạn |
| Báo cáo tài chính | Tổng kết nhiều bảng | Aggregation/analytical | Có thể batch |
| Xóa dữ liệu | Customer privacy erasure | Đa nguồn và mọi bản sao | Không resurrect |

### 2.1. Mỗi truy vấn có thêm thông số vận hành

Ghi:
- Tần suất: RPS giờ thường/đỉnh.
- Read/write mix.
- p50/p95/p99 và deadline.
- Số items trả về.
- Partition/tenant skew.
- Kích thước record/document.
- Sort/filter/index bắt buộc.
- Độ mới chấp nhận: ngay lập tức, sau vài giây hay eventual.
- Auth/tenant scope.
- Transaction và idempotency cần thiết.
- Retention/TTL/deletion.
- Chi phí một request và tổng capacity.

Không biết distribution mà chọn partition key là một rủi ro lớn.

### 2.2. Phân loại access pattern

Có bốn câu hỏi điển hình:
- **Biết key cụ thể?** Key–value thường phù hợp.
- **Thường đọc một cụm thuộc tính cùng nhau?** Document có thể phù hợp.
- **Cần nhiều rows theo partition + trật tự/range?** Wide-column có thể phù hợp.
- **Cần khám phá nhiều quan hệ và traversal?** Graph có thể phù hợp.

Không nhất thiết đưa toàn bộ ứng dụng vào một mô hình. Một hệ có thể giữ SQL làm authoritative source và tạo NoSQL read models cho từng đường đọc.

## 3. Phân biệt relational migration với cache hoặc projection

Ba quyết định khác nhau:

1. **Thay source of truth:** ứng dụng ghi trực tiếp NoSQL và dựa vào nó để bảo vệ invariants.
2. **Thêm read projection:** SQL vẫn authoritative; NoSQL nhận snapshot/CDC để tăng tốc reads.
3. **Thêm cache:** NoSQL/key–value giữ dữ liệu dẫn xuất có thể hết hạn và tái tạo được.

### 3.1. Read model thường là bước chuyển an toàn

Ví dụ:
- Booking creation/inventory/payment vẫn ở SQL.
- MongoDB lưu booking summary cho màn hình chi tiết.
- Cassandra lưu booking_by_customer_day.
- Search index phục vụ text search.
- Redis cache booking detail vài phút.
- Graph store dùng recommendation snapshot.

Có thể triển khai từng phần, đo consistency lag và rollback reads về SQL nếu NoSQL projection lỗi. Đây là migration theo **Strangler pattern** ở phạm vi đường truy cập, không phải SQL→NoSQL big bang.

### 3.2. Source migration có độ rủi ro cao hơn

Khi đưa writes sang NoSQL, phải chuyển nơi bảo đảm:
- Unique booking/slot.
- Atomic inventory decrement.
- Payment idempotency.
- Foreign-reference validity.
- Write ownership và recovery.
- Auditing.
- Tenant authorization.

Đây là thay đổi hợp đồng giao dịch, không chỉ thay repository implementation.

## 4. Bảng tổng quan bốn mô hình

| Đặc tính | Khóa–giá trị | Tài liệu | Cột rộng | Đồ thị |
| --- | --- | --- | --- | --- |
| Truy cập tốt nhất | Theo key | Theo document/index | Theo partition + clustering/range | Theo node/edge/traversal |
| Cách nhóm dữ liệu | Một value theo key | Document với embedded fields | Row/partition và clustering order | Nodes, properties, relationships |
| JOIN truyền thống | Thường không | Có giới hạn và tùy engine; không nên giả định như SQL | Thường thiết kế bảng theo query | Traversal thay cách JOIN |
| Denormalization | Thường rất rõ | Embedded/snapshot | Thường nhiều bảng theo truy vấn | Quan hệ tường minh; vẫn có duplication |
| Fan-out risk | Multi-key reads | Reference lookups/large arrays | Cross-partition queries | High-degree traversal |
| Atomic boundary | Tùy engine/key/transaction | Thường từng document mạnh; multi-document tùy engine | Partition/statement/conditional semantics tùy engine | Transaction semantics theo DB |
| Secondary indexes | Có thể ít/không | Thường có | Không giống SQL, phụ thuộc engine | Index để tìm start nodes |
| Data migration risk | Key naming, index maintenance | Huge document, embed decisions | Hot partition, fan-out, tombstones | Supernodes, relationship direction |
| Thích hợp điển hình | Session/cache/point lookup | Aggregate object/API | Time-ordered event/history per key | Recommendation/relationship exploration |

### 4.1. Họ NoSQL không phải các hộp độc lập tuyệt đối

DynamoDB có items dạng document và key-value access. Redis có hashes, sets, sorted sets và streams. MongoDB có aggregation; HBase/Cassandra cùng gọi wide-column nhưng data layout, timestamp và consistency khác nhau. Chọn theo **khả năng cụ thể của engine và truy vấn**, không theo nhãn marketing.

## 5. Chuyển sang khóa–giá trị: từ khóa chính tới access keys

Một key–value model đơn giản:

~~~~text
booking:{tenantId}:{bookingId}
    -> serialized booking summary

customer:{tenantId}:{customerId}
    -> serialized customer profile

property:{tenantId}:{propertyId}
    -> serialized property summary
~~~~

Ví dụ value:

~~~~json
{
  "bookingId":"B-91",
  "tenantId":"T-7",
  "customerId":"C-2",
  "propertyId":"P-15",
  "status":"CONFIRMED",
  "totalMinor":1850000,
  "version":14,
  "updatedAt":"2026-11-14T09:30:00Z"
}
~~~~

Điểm mạnh: đọc theo key rất rõ. Nhưng câu hỏi “lấy 30 booking mới nhất của C-2” không còn tự giải quyết bằng một GET.

### 5.1. Tạo index dẫn xuất theo customer

Có thể dùng:
- Một key chứa danh sách booking IDs giới hạn.
- Redis sorted set có score là createdAt và member là bookingId.
- Một bảng/collection riêng ánh xạ customer→bookings.
- Một search service nếu truy vấn phức tạp.

Mô hình:

~~~~text
booking:T-7:B-91 -> booking payload
customerBookings:T-7:C-2 -> ordered [B-91, B-90, ...]
~~~~

Hai keys có quan hệ logic. Tạo booking mới cần cập nhật cả record và index, đồng nghĩa có vấn đề **atomicity và consistency giữa các bản sao**.

### 5.2. Phân biệt value và materialized index

Nếu read model không phải source authority:
- Có thể rebuild index từ source.
- Cần version/watermark.
- Có thể eventual.
- Phải xử lý delete/cancel/TTL.

Nếu key–value store là source authority:
- Cần transaction/conditional semantics theo engine.
- Nếu không có multi-key atomicity, cần workflow/outbox/ledger.
- Không được hứa strong read invariant nếu chỉ ghi hai keys độc lập.

### 5.3. Thiết kế key

Một key tốt thường:
- Có namespace/module.
- Có tenant scope rõ.
- Có immutable identity.
- Có version format.
- Có encoding cho separator.
- Không làm lộ PII trong raw key nếu không cần.

Không dùng email, số điện thoại hay secrets trực tiếp làm key nếu có thể dùng opaque IDs.

### 5.4. Redis Cluster hash slot

Trong Redis Cluster, nhiều key operations/scripts/transactions có các hạn chế khi keys nằm ở khác hash slots. Hash tags có thể giúp đặt keys liên quan vào cùng slot khi thật sự cần, nhưng đặt quá nhiều keys của một tenant lớn vào một slot cũng tạo **hot shard**.

Không dùng một hash tag cho toàn bộ tenant lớn chỉ để dễ multi-key atomicity mà bỏ qua capacity.

### 5.5. Cache-aside khác migration source

Nếu SQL vẫn là source:
1. Read cache.
2. Miss → read SQL.
3. Populate cache có TTL/version.
4. On write → invalidate hoặc cập nhật theo policy.

Cache entry stale không phải source corruption. Migration key–value source cần bảo đảm durability, recoverability và write invariants cao hơn cache-aside.

## 6. Khóa tự nhiên, UUID và sharding

Một bookingId có thể được tạo từ:
- ID tuần tự.
- UUID random.
- Time-ordered ID.
- Tenant + business key.

Tác động:
- Range locality.
- Index fragmentation.
- Hot partition nếu monotonic key định tuyến theo range.
- Partition distribution nếu hash.
- Query theo tenant/day.
- Debuggability và uniqueness.

### 6.1. Không chọn key từ mỗi tiêu chí uniqueness

Một key duy nhất không nhất thiết:
- Phân bố đều.
- Giúp query theo thời gian.
- Giúp đọc theo customer.
- Tránh hot tenant.

Với read models, có thể phải **một source identity + nhiều materialized keys theo access pattern**.

### 6.2. Key encoding

Nếu key format là:

~~~~text
tenant|customer|booking
~~~~

cần định nghĩa escaping/canonicalization để separator trong IDs không gây ambiguity. Tránh tự nối chuỗi mà không có test với Unicode, empty strings và unusual values.

### 6.3. Hot keys

Nếu một booking/status được đọc 100.000 lần/giây:
- Single key có thể thành bottleneck.
- Cache replicas/sharding/read fan-out có thể cần.
- Write invalidation và freshness phải được thiết kế.

Khóa phân bố theo hash không giúp phân tán **một hot key duy nhất** nếu một logical key vẫn ở một partition/owner.

## 7. DynamoDB như một lựa chọn key–value/document

Ví dụ một table:

~~~~text
PK                         SK                    Attributes
TENANT#T7#BOOKING#B91       META                  status, total, version
TENANT#T7#CUSTOMER#C2      BOOKING#20261114#B91   status, propertyTitle, ...
~~~~

Đây là một cách minh họa single-table design, không phải quy tắc bắt buộc. Nó đặt items phục vụ các access patterns cạnh nhau nhưng phải cân nhắc:
- Capacity/hot partition.
- Item size.
- Transaction scope.
- Access pattern bằng PK/SK.
- GSI cho đường truy cập khác.
- TTL và Streams.
- Strong vs eventual reads.

### 7.1. GSI không đồng nhất với source key

DynamoDB GSI cập nhật bất đồng bộ và không hỗ trợ strongly consistent reads theo cùng cách base table có thể hỗ trợ trong region. Nếu user vừa tạo booking rồi tìm qua GSI ngay, query có thể chưa thấy item. Đừng mô tả source write failed chỉ vì GSI chậm.

### 7.2. Conditional writes

Để cập nhật version:
- Dùng condition expectedVersion.
- Nếu conflict, không ghi đè mù.
- Với invariant nhiều items, cân nhắc transaction API trong giới hạn documented.
- Idempotency keys cho timeout-after-commit.

### 7.3. Scans không thay SQL WHERE

Một API Query dựa vào PK và optional sort key không tương đương arbitrary SQL filter. FilterExpression có thể loại kết quả sau khi đã đọc items, vì vậy model phải thiết kế key đúng với query trước.

## 8. Chuyển sang tài liệu: aggregate boundaries

Document model có thể gộp booking và các dòng chi tiết:

~~~~json
{
  "_id":"T-7#B-91",
  "tenantId":"T-7",
  "bookingId":"B-91",
  "customerId":"C-2",
  "propertyId":"P-15",
  "status":"CONFIRMED",
  "totalMinor":1850000,
  "currency":"VND",
  "version":14,
  "createdAt":"2026-11-14T09:10:00Z",
  "items":[
    {"itemNo":1,"kind":"NIGHT","amountMinor":1600000},
    {"itemNo":2,"kind":"FEE","amountMinor":250000}
  ],
  "displaySnapshot":{
    "propertyTitle":"Căn hộ mẫu",
    "city":"Đà Nẵng"
  }
}
~~~~

Ở đây **booking + items** là một aggregate nếu:
- Items được tạo/cập nhật theo lifecycle của booking.
- Số items có giới hạn.
- Thường đọc cùng booking.
- Cần atomic update trong một document theo semantics engine.

### 8.1. Nhúng (embed) khi nào?

Nhúng có lợi khi:
- Quan hệ một–ít.
- Cùng lifecycle.
- Thường đọc cùng.
- Số lượng bounded.
- Ít thay đổi độc lập.

Ví dụ booking line items có tối đa 20 items.

### 8.2. Tham chiếu (reference) khi nào?

Giữ customerId và propertyId nếu:
- Customer/property được chia sẻ cho hàng triệu bookings.
- Thực thể có lifecycle độc lập.
- Dữ liệu lớn hoặc thay đổi thường xuyên.
- Không muốn update fan-out khi customer đổi tên.
- Cần giữ một source authoritative cho properties.

Không embed toàn bộ profile customer với PII vào mọi booking.

### 8.3. Snapshot fields có semantics riêng

displaySnapshot.propertyTitle là **tên tại thời điểm đặt chỗ** hoặc tên dẫn xuất hiện tại? Hai lựa chọn khác nhau:
- Historical snapshot: bất biến, cần bảo tồn khi property đổi tên.
- Current projection: phải update khi property đổi tên.

Đặt tên rõ để tránh “dữ liệu trùng” bị sửa nhầm.

### 8.4. Không nhúng arrays không giới hạn

Ví dụ customer có hàng triệu bookings. Embed toàn bộ vào một customer document sẽ gây:
- Document growth và size limits.
- Write contention.
- Large read amplification.
- Pagination khó.
- Hot document.
- Khó delete từng item hiệu quả.

Dùng collection/bookings riêng, index theo tenantId/customerId/createdAt hoặc read projection theo page/bucket.

## 9. Document collections thường thiết kế theo aggregate, không theo từng bảng

Một cách ánh xạ:

| SQL entities | Document model có thể | Lý do |
| --- | --- | --- |
| bookings + booking_items | bookings document + embedded items | Cùng vòng đời và atomic boundary |
| customers | customers collection | Reusable, profile thay đổi độc lập |
| properties | properties collection | Số bookings lớn, thay đổi độc lập |
| payments | payments collection/ledger | Audit, trạng thái độc lập, idempotency |
| property_tags | Embedded bounded tags hoặc join-like relation | Tùy cardinality và update frequency |
| booking search summary | bookings index hoặc projection riêng | Phục vụ access path |
| customer booking timeline | Query bookings bằng compound index | Không embed unbounded list |

### 9.1. Sơ đồ

~~~~mermaid
flowchart LR
    Customer["customers document"] -->|customerId reference| Booking["bookings aggregate"]
    Property["properties document"] -->|propertyId reference| Booking
    Booking --> Items["embedded items"]
    Booking --> Payment["payments ledger by bookingId"]
    Booking --> Summary["optional read projection"]
~~~~

### 9.2. Atomicity của single-document update

MongoDB cung cấp atomicity cho thao tác cập nhật một document. Nếu items và tổng tiền thuộc cùng document, có thể cập nhật có điều kiện cùng version mà không cần distributed transaction. Nhưng transaction xuyên bookings + payments + inventory là bài toán khác.

### 9.3. MongoDB multi-document transactions

MongoDB hỗ trợ multi-document transactions trong các cấu hình phù hợp. Tuy nhiên:
- Có giới hạn/overhead.
- Không thay business idempotency.
- Không bắc cầu atomic qua payment provider hay search index.
- Không nên dùng transaction để che mô hình dữ liệu gây quá nhiều cross-document writes.

Tùy endpoint, giữ SQL source hoặc dùng transactional/conditional pattern sẽ hợp lý hơn chuyển tất cả sang MongoDB.

## 10. Chỉ mục cho document model

Ví dụ những query cần:

~~~~javascript
db.bookings.find(
  {tenantId:"T-7", customerId:"C-2"},
  {bookingId:1, status:1, createdAt:1, totalMinor:1}
)
.sort({createdAt:-1, bookingId:-1})
.limit(30)
~~~~

Index phù hợp có thể là:

~~~~javascript
db.bookings.createIndex({
  tenantId:1,
  customerId:1,
  createdAt:-1,
  bookingId:-1
})
~~~~

### 10.1. Index theo filter và sort

Không tự giả định mọi query sử dụng index tối ưu. Xem:
- Equality prefix.
- Range/sort.
- Index size/write amplification.
- Selectivity.
- Collection growth.
- Actual explain plans.
- Tenant distribution.

### 10.2. Một SQL index không dịch cơ học

Chỉ mục quan hệ trên customer_id và created_at có thể gợi ý compound index, nhưng cần kiểm tra lại:
- Embedded field paths.
- Multikey array behavior.
- Collation.
- Cursor pagination.
- Query projections.
- Sharding key.
- Consistency/replica read preference.

### 10.3. Secondary index cost

Càng nhiều indexes:
- Writes chậm hơn.
- Storage nhiều hơn.
- Backfill/index build lâu hơn.
- Migration cutover phức tạp hơn.

Chỉ tạo indexes cho những access paths được đo là cần thiết.

## 11. Wide-column: thiết kế bảng theo truy vấn

Cassandra/HBase thường dẫn đến cách nghĩ khác SQL. Với Cassandra, truy vấn hiệu quả dựa vào **partition key** và **clustering order**, không phải tùy ý JOIN bảng.

Đặt các mục tiêu:
- Đọc booking theo ID.
- Đọc booking timeline theo customer trong 30 ngày.
- Đọc booking của property theo ngày.

Có thể cần ba bảng/dạng dữ liệu:

~~~~text
booking_by_id
    key: tenant_id + booking_id
    values: canonical booking fields

booking_by_customer_day
    partition: tenant_id + customer_id + bucket_day
    clustering: created_at DESC, booking_id
    values: timeline summary

booking_by_property_day
    partition: tenant_id + property_id + bucket_day
    clustering: start_time, booking_id
    values: calendar summary
~~~~

**Một booking xuất hiện nhiều lần có chủ đích.** Đó là denormalization theo query path, không phải lỗi chuẩn hóa.

### 11.1. CQL minh họa

~~~~sql
CREATE TABLE booking_by_id (
    tenant_id text,
    booking_id text,
    customer_id text,
    property_id text,
    status text,
    total_minor bigint,
    created_at timestamp,
    version bigint,
    PRIMARY KEY ((tenant_id, booking_id))
);

CREATE TABLE booking_by_customer_day (
    tenant_id text,
    customer_id text,
    bucket_day date,
    created_at timestamp,
    booking_id text,
    property_id text,
    status text,
    total_minor bigint,
    version bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, bucket_day),
        created_at,
        booking_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    booking_id ASC
);

CREATE TABLE booking_by_property_day (
    tenant_id text,
    property_id text,
    bucket_day date,
    start_time timestamp,
    booking_id text,
    customer_id text,
    status text,
    version bigint,
    PRIMARY KEY (
        (tenant_id, property_id, bucket_day),
        start_time,
        booking_id
    )
) WITH CLUSTERING ORDER BY (
    start_time ASC,
    booking_id ASC
);
~~~~

Đây là ví dụ CQL định hướng, chưa bao gồm index/repair/TTL/compaction, table options, schema version và business authorization. Primary keys/time bucket phải được chọn theo distribution và workload thật.

### 11.2. Query timeline

~~~~sql
SELECT booking_id, property_id, status,
       total_minor, created_at
FROM booking_by_customer_day
WHERE tenant_id = ?
  AND customer_id = ?
  AND bucket_day = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 30;
~~~~

Query chủ động chọn **một bucket_day**, vì một trang timeline nhiều ngày cần xử lý:
- Nhiều partitions/days.
- Cursor per bucket hoặc merge order.
- Query budget và fan-out.
- Dữ liệu có thể đến muộn.
- Stable ordering.

Không coi một bảng với partition key theo ngày tự giải quyết “top 30 mọi thời điểm” bằng một câu query đơn.

## 12. Wide-column: partition key, clustering key, bucketing

### 12.1. Partition key

Partition key quyết định dữ liệu được phân phối/định vị theo semantics engine. Cần:
- Cardinality đủ.
- Không quá skew.
- Có mặt trong query.
- Không quá rộng.
- Dễ xác định từ input.
- Giữ tenant isolation.

### 12.2. Clustering key

Clustering key giúp sắp xếp rows trong partition và hỗ trợ một số range queries. Nó không tương đương một SQL secondary index toàn cục. Phải hiểu thứ tự columns và điều kiện query được phép.

### 12.3. Time bucketing

Nếu một customer có hàng triệu bookings, partition theo customerId đơn thuần có thể quá lớn. Thêm bucket_day/month hoặc fixed-size bucket giúp quản lý partition size nhưng:
- Query nhiều ngày phải fan-out.
- Backfill cần tính bucket từ lịch sử.
- Late-arriving events có thể vào bucket cũ.
- Không phải mọi tenant có cùng volume.
- Một ngày vẫn có thể hot.

Chọn bucket bằng phép đo, không chỉ bởi lịch.

### 12.4. Hot tenant và salting

Nếu một tenant tạo phần lớn traffic:
- tenantId một mình có thể là hot partition.
- Có thể chia theo entity/day/hashed bucket.
- Phải biết cách query gộp kết quả.
- Ràng buộc uniqueness và update ordering trở nên khó hơn.

Salting tăng phân phối writes nhưng tăng số reads cần hợp nhất; chỉ dùng nếu workload đo xác nhận cần.

### 12.5. Tombstones/TTL

Trong Cassandra/HBase, deletes/TTL và compaction/repair ảnh hưởng đến hiệu năng và consistency. Một migration full reload không được:
- Bỏ qua tombstones.
- Recreate TTL không đúng thời gian.
- Ghi dữ liệu cũ với timestamp ưu tiên cao hơn delete hợp lệ.
- Tự hồi sinh records bị xóa.

Cần deletion ledger và versioned apply.

## 13. Wide-column khác nhau giữa Cassandra và HBase

| Chủ đề | Cassandra | HBase |
| --- | --- | --- |
| Truy cập chính | Partition key + clustering columns | Row key + column family/qualifier |
| Phân tán | Token/ring và replica placement theo cluster | Region partitioning và region servers |
| Thứ tự | Clustering order trong partition | Lexicographic row-key order, cells theo version/timestamp |
| Cấu trúc | CQL tables/rows | Column families và cells |
| Consistency | Read/write consistency levels, repair | Row operations và distributed coordination theo stack |
| TTL/deletes | Tombstones/compaction/repair | TTL/cell versions/delete markers/compaction |
| Query path | Thiết kế theo partition | Thiết kế row-key prefix/range |
| Migration risk | Wide/hot partitions, repair/tombstones | Hot row-key prefixes, region skew, version semantics |

Không lấy một thiết kế Cassandra partition + clustering key rồi tuyên bố HBase có cùng semantics.

### 13.1. HBase row key minh họa

~~~~text
tenantId#customerId#reverseTimestamp#bookingId
~~~~

Nếu thiết kế scan theo customer/time:
- Prefix mang tenant/customer.
- Time component có thứ tự phù hợp.
- BookingId làm tie-breaker.
- Có thể cần hash/salt trước prefix để tránh hotspot.
- Nhưng hash/salt phá scan locality nếu không có fan-out strategy.

### 13.2. Column family theo access pattern

Không tạo mỗi SQL column thành một HBase column family. Column families có overhead và storage/compaction semantics; nên nhóm các cột theo lifecycle/access pattern phù hợp.

### 13.3. Versions khác app version

Cell timestamp/version của HBase không tự là optimistic version của booking trong domain. Cần phân biệt:
- Storage cell version.
- Business entity version.
- Event sequence.
- Snapshot boundary.

## 14. Graph: khi quan hệ là đường truy cập chính

Một mô hình quan hệ nhiều–nhiều:

~~~~text
Customer --made--> Booking --for--> Property
Customer --follows--> Host
Property --hasTag--> Tag
Property --locatedIn--> City
Customer --interestedIn--> Tag
~~~~

Trong SQL, một truy vấn “những properties được khách hàng có sở thích tương tự yêu thích, ở cùng city, loại bỏ đã book” có thể cần nhiều JOINs. Nếu traversal đa bước là core workload, graph store có thể thuận tiện hơn.

### 14.1. Nodes, labels, properties, relationships

Ví dụ graph data:

~~~~cypher
CREATE (c:Customer {
    tenantId: 'T-7',
    customerId: 'C-2'
})
CREATE (p:Property {
    tenantId: 'T-7',
    propertyId: 'P-15',
    city: 'Da Nang'
})
CREATE (c)-[:VIEWED {at: datetime()}]->(p)
~~~~

Đây là dữ liệu thử nghiệm, chưa có indexes/constraints, authorization hoặc uniqueness. Không chạy trực tiếp với IDs thật/PII trong môi trường chung.

### 14.2. Relationships cần danh tính và semantics rõ

Một cạnh VIEWED khác BOOKED:
- VIEWED có thể có hàng triệu events.
- BOOKED cần authoritative booking identity.
- FOLLOWS có thể có uniqueness theo cặp.
- OWNS thuộc quyền nội bộ.

Không cho một user tự tạo cạnh OWNS/ADMIN_OF thông qua một endpoint graph generic.

### 14.3. Truy vấn traversal minh họa

~~~~cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
MATCH (c)-[:INTERESTED_IN]->(tag:Tag)
MATCH (p:Property)-[:HAS_TAG]->(tag)
WHERE p.tenantId = $tenantId
RETURN DISTINCT p.propertyId, p.city
LIMIT 20
~~~~

Khi triển khai:
- TenantId phải lấy từ trusted principal.
- Xác minh mỗi node/edge trong traversal thuộc authorized graph scope.
- Có indexes/constraints để tìm start node.
- Đặt depth/fan-out/query timeout.
- Tránh tham chiếu trực tiếp tới dữ liệu cá nhân trong edges nếu không cần.

### 14.4. Graph không thay relational transactions miễn phí

Graph database có transaction/constraint capabilities tùy engine. Nhưng nếu inventory/payment authoritative vẫn ở SQL, graph chỉ nên là read projection, hoặc phải có distributed consistency design cho cross-store workflows.

## 15. Graph: supernode và unbounded traversal

Một City hoặc Tag phổ biến có thể nối tới hàng triệu Properties. Truy vấn bắt đầu từ supernode và duyệt toàn bộ có thể rất đắt.

Phải kiểm soát:
- Start node selection.
- Direction/relationship type.
- Depth.
- Fan-out/cardinality.
- Index.
- Result limit.
- Time/CPU budget.
- Graph degree distribution.

### 15.1. Đừng biến mọi foreign key thành edge

Nếu chỉ có GET booking by ID, một graph với Customer–Booking–Property edges có thể phức tạp hơn document/point-read. Graph có lợi khi traversal đa bước mang giá trị thật.

### 15.2. Denormalization trong graph

Graph vẫn có thể có snapshot properties trên nodes/edges để tránh traversal phụ. Khi một property đổi tên:
- Ai cập nhật snapshots?
- Có version/watermark không?
- Bản nào là authority?
- Eventual lag cho phép bao lâu?

Graph cũng không thoát khỏi consistency tradeoffs.

### 15.3. Dữ liệu quan hệ nhạy cảm

Một cạnh có thể tiết lộ:
- Một khách hàng từng ở đâu.
- Ai theo dõi ai.
- Quan hệ business.
- Sở thích cá nhân.

Authorization theo nodes/edges và kết quả traversal phải được thiết kế rõ. Không xem graph traversal là quyền đọc mặc định mọi quan hệ.

## 16. Từ bảng JOIN sang các chiến lược NoSQL

Một JOIN có thể được thay bởi:

| Đường thay | Cách làm | Đánh đổi |
| --- | --- | --- |
| Embed | Nhúng fields liên quan trong document | Write fan-out hoặc snapshot semantics |
| Reference fetch | Đọc booking rồi đọc customer/property | Network round trips và consistency |
| Materialized view | Tiền tính booking summary | Storage và CDC lag |
| Multiple query tables | Ghi booking_by_id, booking_by_customer | Duplication/reconciliation |
| Graph traversal | Đi theo quan hệ | Supernode/fan-out/query budget |
| Application join | Batch GET nhiều keys rồi merge | N+1 và partial failures |
| Giữ SQL | Tiếp tục JOIN trong source/analytical DB | Không đạt mọi mục tiêu latency/scaling |

### 16.1. Tránh N+1

Nếu timeline 30 bookings, mỗi booking lại GET customer + property, có thể tạo 60+ requests. Khắc phục:
- Batch fetching.
- Embed bounded display snapshot.
- Materialized read model.
- Caching với freshness policy.
- Giữ SQL JOIN nếu rẻ và phù hợp hơn.

### 16.2. Không denormalize tất cả

Một customer displayName thay đổi một lần/ngày nhưng có 10 triệu bookings:
- Fan-out update 10 triệu records chỉ để hiển thị tên hiện tại có thể rất đắt.
- Có thể fetch customer profile riêng hoặc dùng snapshot semantics.

Đánh giá **read amplification vs write amplification vs storage vs freshness**.

## 17. Chuyển các ràng buộc dữ liệu

| Bảo đảm ở SQL | Câu hỏi khi chuyển NoSQL | Cách triển khai khả thi |
| --- | --- | --- |
| PRIMARY KEY | Entity ID unique ở phạm vi nào? | Key design + conditional insert |
| UNIQUE tenant,email | Global/tenant uniqueness được bảo đảm thế nào? | Unique-claim item/table, transaction/condition |
| FOREIGN KEY | Không có orphan references? | App validation + atomic workflow/reconciliation |
| CHECK | Giá trị business hợp lệ? | Domain validation + DB schema/condition |
| Atomic transaction | Những writes nào phải cùng commit? | Engine transaction trong scope hoặc workflow design |
| SERIALIZABLE isolation | Concurrency invariant là gì? | Version compare-and-set, transaction/lock/escrow |
| ON DELETE CASCADE | Xóa bản sao ra sao? | Event/outbox, tombstone, idempotent cleanup |
| Referential query JOIN | Read paths thay thế? | Embed, reference, materialized view, graph |
| Audit trail | Có dữ liệu lịch sử/truy xuất? | Immutable event/operation ledger |

### 17.1. Unique email

Trong SQL, UNIQUE(tenant_id,email) có thể trực tiếp. NoSQL migration nếu chỉ:
1. Query email chưa tồn tại.
2. Insert new customer.

thì hai requests đồng thời có thể vượt qua check. Cần:
- Conditional unique claim theo tenant+normalizedEmail.
- Transaction/consistent insert nếu engine hỗ trợ.
- Conflict response.
- Race tests.
- Rename/delete/release semantics.

Không dùng eventual secondary index để tự khẳng định uniqueness nếu consistency không bảo đảm.

### 17.2. Booking inventory

Nếu một property chỉ còn một chỗ và hai khách cùng book:
- Một index theo property không tự ngăn double-book.
- Cần authoritative inventory reservation/conditional decrement hoặc transaction theo thiết kế.
- Idempotency operation IDs.
- Timeout-after-commit reconciliation.
- Multi-region conflict policy.

Đây có thể là lý do giữ booking write source ở SQL dù chuyển read models sang NoSQL.

## 18. Nhất quán: chấp nhận lệch ở đâu?

Một bản sao summary có thể chậm vài giây nhưng payment ledger thì không.

| Dữ liệu | Gợi ý contract | Lý do |
| --- | --- | --- |
| Booking creation authority | Không double-book; durable ACK | Business invariant |
| Booking status trên detail API | Có thể yêu cầu read-your-writes | User vừa confirm/cancel |
| Timeline projection | Eventual với lag bound | Có thể chấp nhận vài giây |
| Search index | Eventual | Query discovery |
| Recommendation graph | Eventual và batch rebuild | Không critical transaction |
| Financial ledger | Idempotent, authoritative | Không double charge |
| Redis cache | Stale bounded hoặc invalidate | Derived data |

### 18.1. Staleness phải định lượng

Không chỉ ghi “eventually consistent”. Cần:
- Max/target freshness lag.
- Source version trong projection.
- Checkpoint/watermark.
- Fallback khi stale quá ngưỡng.
- SLO, metrics và on-call runbook.

### 18.2. Causal session

Nếu user vừa cập nhật rồi đọc qua read projection, có thể dùng:
- Session minVersion.
- Read-from-authority fallback.
- Wait-until-version-visible với timeout.
- Sticky read policy theo engine.

Không đơn giản giả định read replica/GSI/search đã bắt kịp ngay.

## 19. Phân hoạch và tenant isolation

Một schema SQL có thể query theo tenantId với indexes. NoSQL partition strategy phải xử lý:
- Tenant lớn hơn nhiều tenant khác.
- Hot booking/day.
- Skew read/write.
- Data locality.
- Multi-region placement.
- Authorization.
- Operations liên quan một tenant.
- Retention/erasure.

### 19.1. Key chỉ tenantId có thể gây hotspot

Nếu một tenant tạo hàng chục nghìn writes/s, toàn bộ trong một partition/slot có thể nóng. Một cách chia:
- tenant + customerId.
- tenant + propertyId + day.
- tenant + bucket.
- Hash(key) theo access pattern.

Nhưng chia càng nhiều thì query “toàn tenant” càng fan-out. Chọn qua benchmark và phân phối thật.

### 19.2. Cross-tenant leakage

Materialized views cần gắn tenant trong:
- Storage key.
- Query filter.
- Cache namespace.
- Cursor.
- CDC routing.
- Graph node/edge scope.
- Authorization tests.

Một read model được tạo từ SQL JOIN có tenant filter đúng chưa đủ nếu NoSQL projection key bỏ tenantId và reuse ID giữa tenants.

## 20. Thiết kế ID, version và schema evolution

Một entity có thể có:

~~~~json
{
  "tenantId":"T-7",
  "bookingId":"B-91",
  "schemaVersion":3,
  "sourceVersion":14,
  "sourceCommitTime":"2026-11-14T09:30:00Z",
  "projectionVersion":2
}
~~~~

Ý nghĩa:
- **bookingId:** identity nghiệp vụ.
- **schemaVersion:** định dạng payload.
- **sourceVersion:** phiên bản nghiệp vụ/nguồn dùng ordering.
- **projectionVersion:** version của transformer/read model.
- **sourceCommitTime:** timestamp tham khảo, không tự thay total ordering.

### 20.1. Không dùng updatedAt đơn độc để chọn winner

Clock skew và nhiều writes trong cùng millisecond có thể làm updatedAt không đủ để định thứ tự. Dùng version/sequence/commit token có guarantee phù hợp.

### 20.2. Schema v1/v2/v3

Trong migration, có thể có:
- SQL row cũ không có property snapshot.
- Document v2 có totalMinor là string.
- Document v3 có totalMinor dạng integer.
- Cassandra read model cũ thiếu currency.

Cần:
- Versioned mappers.
- Typed conversions.
- Backward/forward compatibility.
- Safe defaults theo domain.
- Migration/reindex.
- Contract tests.

### 20.3. Không bắt tất cả old records viết lại ngay

Lazy migration có thể giảm write spike, nhưng phải:
- Reader hiểu old schema.
- Writer nâng schema có điều kiện.
- Index/query vẫn đúng.
- Không làm lost update.
- Có monitoring tỷ lệ old versions.

## 21. Quy trình di chuyển an toàn: expand–backfill–catch-up–cutover–contract

Một lộ trình:

~~~~mermaid
flowchart TD
    INV["Inventory access patterns + invariants"] --> MODEL["Design NoSQL projections/models"]
    MODEL --> EXPAND["Deploy additive schema and events"]
    EXPAND --> SNAP["Consistent snapshot / backfill"]
    SNAP --> CDC["CDC catch-up with versions/tombstones"]
    CDC --> SHADOW["Shadow reads + reconciliation"]
    SHADOW --> GATE{"Correctness, performance, lag pass?"}
    GATE -->|No| FIX["Repair mapping / replay / backfill"]
    FIX --> SHADOW
    GATE -->|Yes| CANARY["Route small read traffic"]
    CANARY --> CUT["Expand traffic, monitor"]
    CUT --> CONTRACT["Retire old read path only after rollback window"]
~~~~

### 21.1. Expand

Trước tiên thêm:
- Source version.
- Stable entity IDs.
- Outbox/event IDs nếu chưa có.
- Read model schema/keys.
- CDC connector.
- Metrics và health checks.
- Backfill writer.

Không gỡ SQL columns/tables ngay.

### 21.2. Backfill

Chụp consistent snapshot hoặc đọc nguồn theo boundary documented:
- Partition/batch scan.
- Không tạo scan quá tải.
- Giữ datatype/schema/TTL.
- Ghi progress/checkpoints.
- Idempotent writes.
- Chống overwrite từ events mới.

### 21.3. Catch-up

Replay changes từ mốc phù hợp:
- Có event ordering/sequence per key.
- Dedupe.
- Apply deletes.
- Version guards.
- Quarantine malformed events.
- Track consumer lag.
- Không bỏ missing segments.

### 21.4. Shadow/read compare

Ứng dụng vẫn trả SQL results. Song song:
- Đọc NoSQL projection trên traffic chọn lọc.
- So canonical business fields.
- Đo query latency/cost.
- Ghi mismatches không lộ PII.
- Không gây side effects.

### 21.5. Canary và cutover

- Route nhỏ traffic reads sang NoSQL.
- Giữ fallback có budget và cảnh báo.
- Theo dõi p99/errors/freshness.
- Nâng dần.
- Chỉ sau khi ổn định mới retire old read path theo kế hoạch.

### 21.6. Source-of-truth cutover

Nếu chuyển writes hẳn sang NoSQL, cần thêm:
- Single-writer authority/fencing.
- Idempotency.
- Cutover epoch/lease.
- Transaction/invariant tests.
- Dual-write/backout semantics.
- Handling of unknown writes.
- Reconciliation cả hai phía.
- Failback plan khi new source đã có writes.

## 22. Snapshot + CDC: tránh khe hở và ghi đè dữ liệu mới

Một thảm họa migration phổ biến:

~~~~text
T1 backfill đọc booking v10
T2 source commit booking v11
T3 CDC apply v11 vào NoSQL
T4 backfill viết v10 vào NoSQL
=> projection bị lùi về v10
~~~~

### 22.1. Quy tắc version-aware apply

Một phép apply phải xét:
- Entity key.
- SourceVersion.
- Delete/tombstone flag.
- Event ID.
- Projection/schema version.
- Conditional update.

Nếu target đã có v11, backfill v10 không được ghi đè.

### 22.2. Cửa sổ snapshot/CDC

Có thể:
1. Xác định snapshot boundary H.
2. Bắt CDC từ một vị trí đủ sớm không bỏ events.
3. Chạy backfill consistent tới H.
4. Apply CDC idempotently sau H.
5. Verify catch-up tới watermark W.
6. Cutover khi lag và drift trong budget.

Chi tiết phụ thuộc DB/CDC connector: không phải mọi SELECT pagination là snapshot consistent, và không phải mọi CDC token có thể replay từ H.

### 22.3. Không rely solely on event arrival order

Events qua nhiều partitions/shards có thể tới target khác thứ tự:
- Version-aware compare.
- Per-key ordering.
- Partition/epoch semantics.
- Causal/dependency handling khi cần.
- Idempotent processing.
- Dead-letter queue có replay policy.

Không tự cộng offsets của các partitions thành một global order.

### 22.4. Deletes là first-class events

Một backfill cũ có thể hồi sinh record đã DELETE. Cần tombstone/watermark đủ lâu và apply logic ngăn stale UPSERT.

## 23. Dual-write: vì sao nguy hiểm?

Một API cố ghi cả SQL và NoSQL:

~~~~text
write SQL success
write NoSQL timeout
HTTP response?
~~~~

Hoặc ngược lại:
- NoSQL success.
- SQL rollback.
- Retry dẫn tới duplicates.

Không có distributed transaction đáng tin giữa hai stores, dual-write trực tiếp có thể tạo drift.

### 23.1. Transactional outbox

Một hướng:
- Trong SQL transaction, update source + ghi outbox event.
- Worker phát event từ outbox/CDC.
- NoSQL consumer apply idempotent.
- Eventual read model, giám sát lag.

Ưu điểm: khi SQL transaction commit, record và intent phát event cùng tồn tại. Hạn chế: delivery có thể at-least-once, cần dedupe/version, không có instant consistency.

### 23.2. Khi phải dual-write thật

Nếu business yêu cầu chuyển write authority:
- Có migration state machine và single-writer rule.
- Ghi operationId.
- Preflight compare.
- Throttle.
- Shadow validation.
- Unknown commit reconciliation.
- Rollback policy.
- Không mở đồng thời hai writers tự do mà thiếu conflict resolution.

### 23.3. Không gọi exactly-once một cách dễ dãi

At-least-once CDC + idempotent writes có thể đạt **effectively-once business outcome** trong điều kiện ledger/transaction đúng, nhưng network retries, external side effects và retention không tự được giải quyết.

## 24. Java 21: định nghĩa domain độc lập storage

Tách domain khỏi DTO SQL và DTO NoSQL giúp migration dễ kiểm tra.

~~~~java
import java.time.Instant;
import java.util.List;

public record BookingId(String tenantId, String bookingId) {
    public BookingId {
        if (tenantId == null || tenantId.isBlank()
                || bookingId == null || bookingId.isBlank()) {
            throw new IllegalArgumentException("missing identity");
        }
    }
}

public enum BookingStatus {
    PENDING, CONFIRMED, CANCELLED
}

public record BookingItem(
        int itemNo,
        String description,
        long amountMinor
) {}

public record BookingAggregate(
        BookingId id,
        String customerId,
        String propertyId,
        BookingStatus status,
        long totalMinor,
        long version,
        Instant createdAt,
        List<BookingItem> items
) {
    public BookingAggregate {
        if (id == null || status == null ||
                createdAt == null || version < 0 ||
                totalMinor < 0 || items == null) {
            throw new IllegalArgumentException("invalid booking");
        }
        items = List.copyOf(items);
    }
}
~~~~

### 24.1. Không nhầm domain model với persistence entity

Có thể có:
- SqlBookingRow.
- MongoBookingDocument.
- CassandraBookingByCustomerRow.
- RedisBookingValue.
- GraphBookingNode.
- BookingAggregate domain object.

Mapper giữa chúng phải:
- Bảo tồn ID/tenant.
- Bảo tồn số tiền theo integer minor units.
- Bảo tồn UTC instants.
- Giữ version.
- Phân biệt null/missing.
- Validate enum/schema.
- Ghi rõ trường snapshot vs current.

### 24.2. Một mapping có thể cố tình làm mất thông tin

Read summary chỉ cần status/propertyTitle/createdAt, không cần toàn bộ payment PII. Đó là **projection có chủ đích** chứ không phải lỗi. Nhưng response equivalence phải so đúng những business fields mà API hứa, không đòi raw JSON giống hệt SQL.

## 25. Java 21: mapper sang document và KV value

Dạng ánh xạ typed:

~~~~java
import java.time.Instant;
import java.util.List;

public record BookingDocumentV3(
        String tenantId,
        String bookingId,
        String customerId,
        String propertyId,
        String status,
        long totalMinor,
        long sourceVersion,
        Instant createdAt,
        List<BookingItem> items
) {}

public final class BookingMappings {
    private BookingMappings() {}

    public static BookingDocumentV3 document(
            BookingAggregate source
    ) {
        return new BookingDocumentV3(
                source.id().tenantId(),
                source.id().bookingId(),
                source.customerId(),
                source.propertyId(),
                source.status().name(),
                source.totalMinor(),
                source.version(),
                source.createdAt(),
                source.items()
        );
    }

    public static String bookingKey(BookingId id) {
        // Example only: production must encode delimiters,
        // validate identifiers, and avoid raw sensitive values.
        return "booking:" + id.tenantId() +
                ":" + id.bookingId();
    }
}
~~~~

Không dùng generic BeanUtils copy giữa SQL entity và NoSQL document nếu fields có ý nghĩa khác nhau, ví dụ passwordHash, deletedAt, internalScore hoặc version.

### 25.1. Tests cho mapper

- Round-trip quantity/decimal.
- ISO timestamp/timezone.
- Legacy nullable fields.
- Enum unknown.
- UTF-8/Unicode identifiers.
- Arrays/items size.
- Transaction metadata.
- Delete/tombstone.
- Snapshot vs current property title.

### 25.2. Serialization versioning

Khi đổi schema:
- Sử dụng schemaVersion.
- Có reader cho old versions trong migration window.
- Không tự coi tất cả fields mới optional nếu invariant đòi có.
- Không chuyển long tiền sang double.
- Cân nhắc rolling upgrade theo pod/worker.

## 26. Java: idempotent version-aware projection apply

Một interface khái niệm:

~~~~java
public record BookingChanged(
        String eventId,
        BookingId id,
        long sourceVersion,
        boolean deleted,
        BookingDocumentV3 document
) {}

public enum ApplyResult {
    APPLIED,
    ALREADY_CURRENT,
    SKIPPED_STALE,
    RETRYABLE_FAILURE,
    QUARANTINED
}

public interface BookingProjectionRepository {
    // Must atomically compare sourceVersion and update/tombstone
    // using guarantees of the chosen storage engine.
    ApplyResult applyIfNewer(BookingChanged event);
}
~~~~

Consumer:

~~~~java
public final class BookingProjectionConsumer {
    private final BookingProjectionRepository repository;

    public BookingProjectionConsumer(
            BookingProjectionRepository repository
    ) {
        this.repository = repository;
    }

    public ApplyResult onEvent(BookingChanged event) {
        if (event == null || event.id() == null
                || event.sourceVersion() < 0
                || event.eventId() == null) {
            return ApplyResult.QUARANTINED;
        }

        if (!event.deleted() && event.document() == null) {
            return ApplyResult.QUARANTINED;
        }

        return repository.applyIfNewer(event);
    }
}
~~~~

### 26.1. Điểm khó nằm ở adapter cụ thể

Từng engine có:
- Atomic conditional update khác nhau.
- Transaction boundary khác nhau.
- Secondary index/GSI lag.
- Retry/timeout semantics.
- TTL/deletion behavior.
- Conflict errors.

Interface không tự tạo atomicity. Adapter phải thật sự implement version guard bằng phương tiện engine hỗ trợ, hoặc dùng event/ledger ownership rõ.

### 26.2. Không cập nhật checkpoint trước durable apply

Một consumer chỉ checkpoint/ACK sự kiện khi target đã apply bền vững theo contract. Nếu checkpoint trước, crash có thể mất event. Nếu crash sau commit nhưng trước ACK, event có thể được phát lại; apply phải idempotent.

### 26.3. Delete tombstone

Một delete event v15 phải ngăn UPSERT v14 đến muộn. Nếu remove record vật lý và không lưu watermark, projection có thể bị hồi sinh bởi backfill/replay cũ.

## 27. Chuyển dữ liệu có điều kiện khi còn ghi liên tục

Một backfill lớn thường cần:
- Consistent read boundary hoặc streaming snapshot.
- Chunking theo key/range/token.
- Max concurrency và source query budget.
- Retry/backoff.
- Resumable checkpoint.
- Version guard.
- Dead-letter/quarantine.
- Per-bucket reconciliation.
- Per-tenant quotas.
- Data retention controls.
- Operation-specific metrics.

### 27.1. Pagination bằng offset có thể sai

Quét SQL bằng OFFSET trong khi rows được thêm/xóa có thể:
- Skip rows.
- Read duplicates.
- Chi phí cao.

Keyset pagination hoặc snapshot-consistent scanning phù hợp hơn, nhưng phải thiết kế theo unique stable sort key và database isolation semantics.

### 27.2. CDC không thay snapshot

CDC thường ghi changes từ một mốc; nó không tạo sẵn mọi records trước mốc đó. Cần backfill, trừ khi log chứa đủ full history và replay được theo contract.

### 27.3. Snapshot không thay CDC

Backfill xong sau nhiều giờ có thể stale ngay nếu source tiếp tục ghi. Cần CDC tail hoặc maintenance freeze/cutover được quản lý.

### 27.4. Source load protection

Không dùng backfill scan tốc độ tối đa khiến SQL production p99 vượt SLO. Cần adaptive throughput, rate caps, partition scheduling và off-peak policy.

## 28. Đối soát hai mô hình: đúng trạng thái, không chỉ bằng số bản ghi

Một migration đáng tin phải chứng minh:
- **Membership:** mọi entity cần có đều có.
- **Value:** business fields đúng.
- **Version:** target không lùi.
- **Delete/TTL:** records bị xóa không hồi sinh.
- **Type:** integer/decimal/date/null/enum đúng.
- **Reference:** các ID/tenant mappings hợp lệ.
- **Query result:** pages, sort, filters theo contract.
- **Invariants:** không double-book, payment duplicate.
- **Access control:** không cross-tenant leak.
- **Freshness:** lag trong bound cho phép.

### 28.1. Bảng đối soát

| Key | SQL sourceVersion | NoSQL version | Kết luận |
| --- | ---: | ---: | --- |
| B-91 | 14 | 14 | Cần so thêm canonical fields |
| B-92 | 8 | 7 | Target lag hoặc missing event |
| B-93 | Deleted v12 | 11 visible | Có nguy cơ resurrection |
| B-94 | 5 | Absent | Missing target |
| B-95 | 6 | 7 | Có thể là bất thường; xem lineage |

Không tự kết luận v7 đúng hơn v6 chỉ vì lớn hơn; target version có thể bị sinh từ một luồng không cùng lineage.

### 28.2. Canonicalization trước khi hash

Nếu tính content digest:
- Sắp xếp fields/arrays có quy tắc.
- Giữ null vs missing.
- Numeric type/scale.
- UTC timestamps.
- Unicode normalization theo contract.
- Exclude metadata không thuộc business equivalence.
- Include schema/projection version khi cần.

Hash raw JSON của SQL DTO và MongoDB BSON có thể khác chỉ vì serialization order/type tags. Cần canonical business representation.

### 28.3. Bucketed checksums

Với tập dữ liệu lớn, chia theo tenant/hash bucket:
- Đếm keys.
- Hash tập keys.
- Hash canonical values.
- Đối soát mismatch buckets.
- Khoanh vùng keys để repair.

Không so counts rồi coi dữ liệu đã đúng.

### 28.4. So cùng boundary

Nếu SQL source đã v15 nhưng target vừa đọc v14, đó có thể là eventual lag hợp lệ. Cần query theo snapshot/watermark hoặc cho freshness grace window, không báo lỗi từ hai reads ở thời điểm khác nhau.

## 29. Shadow reads và equivalence theo hợp đồng

Một request đọc booking:
1. Trả kết quả từ SQL authority.
2. Gọi NoSQL shadow read bất đồng bộ có budget.
3. So các trường mà endpoint hứa.
4. Ghi mismatch type/category.
5. Không thay đổi response user.
6. Không làm latency production tăng ngoài giới hạn.

### 29.1. Không so raw JSON byte-to-byte

SQL có thể trả displayName từ customers hiện tại; NoSQL summary lưu displayName snapshot. Hai kết quả khác nhau **có thể đúng** nếu contract đã định nghĩa khác. Trước khi shadow compare, thống nhất response semantics.

### 29.2. Các loại mismatch

- MISSING_TARGET.
- PHANTOM_TARGET.
- STALE_VERSION.
- WRONG_VALUE.
- WRONG_TYPE.
- WRONG_TENANT.
- SORT_ORDER_DIFF.
- PAGINATION_DIFF.
- DELETED_RESURRECTION.
- AUTHORIZATION_DIFF.
- EXPECTED_EVENTUAL_LAG.

### 29.3. Sampling

Khi traffic lớn:
- Shadow một tỷ lệ có kiểm soát.
- Bao gồm hot tenants/edge cases.
- Không chỉ sample successful reads.
- Tách timeout/error.
- Không làm source hoặc new projection quá tải.

## 30. Chiến lược cutover theo đường truy cập

Một cutover an toàn có thể tiến theo thứ tự:
1. Cấu hình feature flag cho read model.
2. Internal/testing tenants.
3. 1% reads.
4. 5%.
5. 25%.
6. 50%.
7. 100%.
8. Retain SQL fallback trong thời hạn quy định.
9. Contract/remove old path sau khi rollback không còn cần.

Các tỷ lệ chỉ minh họa. Stop/go gates phải dựa trên metrics và business invariants.

### 30.1. Gate có thể gồm

- Backfill complete theo snapshot H.
- CDC lag p99 trong ngưỡng.
- No unresolved critical mismatches.
- No cross-tenant leakage.
- Query p99/deadline pass.
- Database cost trong budget.
- Replication/backup/restore tested.
- On-call runbook sẵn sàng.

### 30.2. Rollback reads

Nếu NoSQL read model sai:
- Chuyển đọc về SQL nếu SQL còn authoritative và capacity đủ.
- Tiếp tục hoặc tạm dừng CDC theo incident policy.
- Quarantine bad projection.
- Repair/rebuild và shadow compare lại.

### 30.3. Rollback writes khó hơn

Sau khi NoSQL thành authoritative và nhận new writes, SQL source cũ có thể stale. “Tắt flag về SQL” có thể làm mất dữ liệu. Cần reverse-CDC/reconciliation, single-writer fencing, conflict-resolution và failback plan.

## 31. Công thức chi phí denormalization

Giả sử một booking được lưu trong k=3 read models. Mỗi source write tạo thêm updates cho ba models.

Không nhất thiết 1 source write → 3 physical writes đúng tuyệt đối vì batching/indexing/retries, nhưng write amplification tối thiểu thường tăng theo số projections.

Một cách ước tính:

\[
W_{\mathrm{total}}\approx W_{\mathrm{source}}+
\sum_{i=1}^{k} W_{\mathrm{projection},i}+
W_{\mathrm{index}}+W_{\mathrm{retry}}
\]

Cần tính:
- Storage bytes và index bytes.
- Read amplification.
- Write amplification.
- Replica cost.
- CDC broker retention.
- Backfill/repair cost.
- Recovery and monitoring cost.
- Data deletion cost.

### 31.1. Một snapshot field đắt thế nào?

Nếu property title được lặp trong 10 triệu booking summaries, một lần đổi title có hai semantics:
- Snapshot-at-booking: không update (ít write nhưng không là current title).
- Current title: update millions or read separate property.

Hãy nêu rõ business semantics trước khi chọn.

### 31.2. Data transfer cost

Nếu app cần 30 bookings và mỗi item có 100 KB embedded data, một page có thể chuyển 3 MB dù UI chỉ dùng 1 KB/booking. Projection hẹp hoặc document split phù hợp hơn.

### 31.3. Không tối ưu chỉ theo latency đơn lẻ

Một read p99=10 ms nhưng backfill/reconciliation/repair mất 20 giờ và write correctness yếu không phải tradeoff tối ưu cho mọi hệ.

## 32. Capacity planning theo mô hình

### 32.1. Key–value

- Key size và value size.
- Hot keys.
- Cache hit ratio.
- Eviction/TTL.
- Connection throughput.
- Memory overhead/replication.
- Multi-key index updates.

### 32.2. Document

- Document growth.
- Index count/selectivity.
- Read/write amplification.
- Shard key distribution.
- Large arrays.
- Query planner and aggregation.
- Replica read lag.

### 32.3. Wide-column

- Partition width.
- Clustering range size.
- Hot partitions.
- Compaction/tombstones.
- Read repair.
- SSTable IO.
- Cross-bucket fan-out.
- TTL churn.

### 32.4. Graph

- Node/edge counts.
- Degree distribution.
- Supernodes.
- Traversal depth.
- Path cardinality.
- Index for start nodes.
- Memory/page cache.
- Multi-hop p99.

Không lấy một benchmark point-GET 100k RPS để chứng minh một graph traversal hoặc wide-column range scan sẽ đạt cùng mức.

## 33. Tải Java trong migration: đo cả generator

Một thử nghiệm cần:
- Planned vs sent vs completed requests.
- Per-operation p99.
- Error/timeouts.
- Read-after-write freshness.
- Projection lag.
- Connection-pool waits.
- Driver retries.
- GC/CPU.
- Hot key/partition distribution.
- Generator scheduler lag.

Nếu load generator bị chậm khi source quá tải, một benchmark closed-loop có thể tự giảm offered RPS và tạo số p99 lạc quan. Muốn kiểm tra fixed-arrival capacity cần đo scheduled arrivals và dropped/missed attempts, không chỉ completed successes.

### 33.1. Mô phỏng query mix thật

Ví dụ:
- 50% booking point reads.
- 20% customer timeline reads.
- 10% property calendar reads.
- 10% new booking writes.
- 5% cancel/confirm.
- 5% search/graph.

Các tỷ lệ chỉ là workload minh họa. Phải dựa vào telemetry và peak distribution thực tế.

### 33.2. Hot tenants

Nếu 5% tenants sinh 90% traffic, benchmark uniform random tenant IDs sẽ che hot partition. Phải đo theo các distribution như Zipfian/skew và realistic entity sizes.

### 33.3. Latency riêng cho từng đường

Không báo một p99 chung cho tất cả operations rồi tuyên bố đã chuyển thành công. Cần p99 theo endpoint, tenant tier, key size, query shape và consistency mode.

## 34. Retry, timeout và unknown commit

Chuyển write authority sang NoSQL có thể thay lỗi/retry semantics:
- Driver timeout không khẳng định write chưa commit.
- Conditional conflict khác transient network error.
- Một physical request có thể được gửi nhiều lần.
- Event consumer có thể replay cùng event.
- Multi-region failover có thể đổi write owner.

### 34.1. Idempotency key

Mỗi business operation có:
- Logical operationId.
- Auth tenant/resource ID.
- Expected version.
- Payload fingerprint.
- Canonical result.
- Commit state/ledger.

Không tự tạo operationId mới cho mỗi retry nếu muốn tránh duplicate bookings/payments.

### 34.2. Không retry khi condition thất bại

Version conflict có thể là user khác vừa cập nhật; cần reread/reconcile, không bỏ guard rồi ghi đè.

### 34.3. Cross-store side effects

Một SQL transaction không thể atomic cùng:
- MongoDB write.
- Cassandra materialized table update.
- Redis cache.
- Search index.
- Payment provider.

Cần saga/outbox/compensation tùy tác vụ. Không gọi đó là distributed transaction nếu không có coordinator/guarantees.

## 35. Deletes, privacy và data retention

Một delete SQL có thể cần:
- Xóa document source.
- Xóa KV index.
- Xóa wide-column views.
- Xóa graph nodes/edges theo policy.
- Invalidate cache.
- Xóa search index.
- Lưu tombstone/watermark để không replay stale event.
- Thực hiện privacy erasure.
- Áp backup retention/deletion workflow.

### 35.1. Không chỉ emit DELETE rồi xong

Nếu consumer A offline quá retention:
- Có thể miss delete event.
- Một backfill cũ đưa record trở lại.
- Target còn PII.

Cần reconciliation từ current source state và erasure ledger phù hợp.

### 35.2. TTL có thể khác nhau

Source record TTL=30 ngày nhưng Redis key TTL=5 phút và Cassandra column TTL=7 ngày có semantics khác. Không được coi TTL là dữ liệu được sao chép 1:1; định nghĩa absolute expiry và retention chính sách.

### 35.3. Graph deletes

Xóa một customer khỏi graph có thể ảnh hưởng edges với property/tag; cần:
- Quy tắc detach/delete.
- Ranh giới những edges thuộc customer.
- Không xóa shared nodes vô ý.
- Audit/erasure compliance.

## 36. Bảo mật migration

Một pipeline backfill/CDC thường có quyền đọc rất rộng:
- SQL production data.
- NoSQL destination.
- PII.
- Cross-tenant data.
- Credentials.
- Backup.

Cần:
- Least-privilege service accounts.
- IAM/ACL theo namespace/tenant nếu khả thi.
- Encryption.
- Secrets trong vault, không trong logs.
- Bounded access.
- Audited exports.
- Retention của staging data.
- Redaction khi shadow compare.
- Không public raw CDC payload.

### 36.1. Multi-tenant key isolation

Khi thiết kế Redis keys, MongoDB filters, Cassandra partitions và graph traversals, luôn đưa tenant scope từ **trusted principal/context**, không chỉ từ untrusted request body.

### 36.2. Sensitive fields

Không đưa customer email/payment token vào mọi read projection nếu UI không cần. Data minimization giảm blast radius khi một projection lỗi/bị truy cập trái phép.

### 36.3. Search/graph inference

Ngay cả khi không trả private fields, sort, count và traversal có thể tiết lộ thông tin về người khác. Query field/edge authorization là một phần thiết kế.

## 37. Vì sao nhiều migrations thất bại?

1. Chuyển mỗi SQL table thành một collection mà không đo access patterns.
2. Bỏ JOIN nhưng tạo N+1 network reads.
3. Nhúng unbounded arrays trong document.
4. Lưu trùng dữ liệu mà không có owner/version.
5. Chọn partition key chỉ theo uniqueness.
6. Không đo hot tenants.
7. Xem GSI/search index như source strongly consistent.
8. Bỏ unique constraint mà không tạo conditional claim.
9. Ghi nhiều NoSQL tables mà giả định atomic như SQL transaction.
10. Dual-write trực tiếp không có outbox/ledger.
11. Backfill ghi đè event mới.
12. Không replay DELETE.
13. Không giữ sourceVersion.
14. Chỉ so row counts.
15. Không so datatype/decimal precision.
16. Không kiểm tra null vs missing.
17. Không test cross-tenant authorization.
18. Dùng TTL không đúng retention.
19. Không kiểm soát query cost.
20. Rollback reads thì dễ nhưng rollback writes không có kế hoạch.
21. Tính RPO/RTO theo replication thay vì backup.
22. Không có DR restore drill.
23. Đưa mọi use case vào một NoSQL model.
24. Đánh giá graph chỉ bằng số JOIN SQL.
25. Bỏ SQL dù workload transaction/analytic vẫn phù hợp SQL.

## 38. Runbook migration theo từng giai đoạn

### Bước 1 — Khảo sát dữ liệu và workload

- ERD/DDL.
- FK/unique/check/transaction invariants.
- Query inventory.
- RPS/p99.
- Tenant skew.
- Cardinality/document size.
- TTL/retention.
- Data ownership.
- Security/privacy.

### Bước 2 — Chọn mô hình cho từng access pattern

- KV point GET/cache.
- Document aggregates.
- Wide-column time-series/timeline.
- Graph relationships.
- Giữ SQL cho workflows chưa có cách bảo vệ invariants.

Ghi ADR và tradeoffs.

### Bước 3 — Thiết kế keys, schema, indexes, edges

- Tenant scope.
- Key naming.
- Partition/clustering.
- Document boundaries.
- Graph degree/traversal.
- SchemaVersion/sourceVersion.
- Tombstones.
- Index and query budgets.

### Bước 4 — Thiết kế consistency và write ownership

- Authority per entity.
- Source commit semantics.
- Outbox/CDC.
- Conditional writes.
- Idempotency.
- Retry/UNKNOWN.
- Reconciliation.
- Multi-region conflict policy.

### Bước 5 — Build pipeline

- Capture snapshot H.
- Backfill chunks.
- CDC from safe boundary.
- Version-aware apply.
- Checkpoints after durable apply.
- DLQ/repair.
- Metrics.
- Source load limits.

### Bước 6 — Kiểm chứng dữ liệu

- Membership.
- Typed canonical digests.
- Versions.
- Deletes.
- Auth/tenant.
- Business invariants.
- Pagination/sort.
- Read freshness.
- Performance and cost.

### Bước 7 — Shadow/canary

- Compare SQL vs NoSQL.
- Explain expected eventual lag.
- 1%→100% reads theo gates.
- Rollback flag.
- On-call monitoring.

### Bước 8 — Chuyển source writes nếu cần

- Single-writer authority.
- Fencing.
- Idempotency ledger.
- Transaction/conditional policy.
- Reverse sync/failback.
- DR backup restore.

### Bước 9 — Contract và hậu kiểm

- Loại old code/DB access chỉ sau khi đủ rollback window.
- Cập nhật diagrams/runbooks.
- Quyết định retention/staging deletion.
- So chi phí và SLO thực.
- Postmortem các mismatches và fixes.

## 39. Test matrix cần có

| Tình huống | Kiểm tra |
| --- | --- |
| Booking point read | Key/doc/row đúng với source |
| Customer timeline | Sort/cursor không thiếu hoặc lặp |
| Property calendar | Range theo bucket đúng |
| Booking + items | Aggregate boundaries đúng |
| Customer rename | Snapshot vs current semantics rõ |
| Concurrent bookings | Không double-book |
| Duplicate create requests | Idempotency |
| Timeout-after-commit | UNKNOWN reconcile |
| Read-after-write | Đáp ứng freshness contract |
| Secondary index lag | Không ngộ nhận missing source |
| CDC duplicate event | Apply một logical effect |
| CDC out-of-order | Version guard không rollback |
| Backfill races | Không ghi v10 đè v11 |
| Delete events | Không resurrection |
| Expired TTL | Không hồi sinh dữ liệu |
| Legacy schema | V1/V2/V3 compatible |
| Large customer | Không unbounded document/partition |
| Hot tenant | NoSQL p99 và throttles trong budget |
| Graph supernode | Traversal bounded |
| Cross-tenant query | Không dữ liệu ngoài scope |
| Failover | Fencing và checkpoint |
| Backup/restore | RPO/RTO được đo |
| Partial projection loss | Rebuild/reconcile |
| Slow generator | Offered vs sent đo đúng |
| Old SQL rollback path | Không mất writes sau source cutover |

### 39.1. Fault injection

- Kill CDC consumer giữa apply và checkpoint.
- Mất log segments sau retention.
- NoSQL write timeout.
- Network partition.
- GSI lag.
- Redis eviction.
- Cassandra compaction spike.
- Hot shard.
- Graph high-degree expansion.
- Schema version mismatch.
- Database failover.
- Duplicate event after restart.

Mỗi fault phải có:
- Expected behavior.
- Invariant.
- Logs/metrics.
- Quarantine policy.
- Recovery test.
- Pass/fail criteria.

## 40. Bài tập: chọn mô hình cho hệ đặt chỗ

Một nền tảng có:
- 3 triệu customers.
- 80.000 properties.
- 120 triệu bookings.
- Một tenant chiếm 35% traffic.
- 80% reads là booking detail/timeline.
- 10% writes là booking create/cancel.
- 10% là search và recommendations.
- Deadline booking detail p99 dưới 100 ms.
- Search có thể stale tối đa 10 giây.
- Payment không được double-charge.
- Có booking-items trung bình 3, tối đa 20.
- User có thể xem danh sách bookings trong 5 năm.
- Có yêu cầu xóa dữ liệu cá nhân.
- SQL là source ban đầu.

### A. Chọn mô hình

1. Booking detail dùng KV hay document?
2. Timeline 5 năm nên embed vào customer không?
3. Wide-column bucket thế nào cho customer lớn?
4. Graph phù hợp truy vấn nào?
5. Có nên chuyển payment authority khỏi SQL ngay không?

### B. Aggregate và index

Dùng bookings + booking_items:
1. Khi nào embed?
2. Khi nào reference?
3. Cần compound index filter/sort nào?
4. Vì sao customer profile không nên nhúng toàn bộ?
5. Snapshot property title có ý nghĩa gì?

### C. Partition và hot tenant

1. Vì sao tenantId một mình có thể hot?
2. Partition bằng tenant+customer+month có tradeoff gì?
3. Một customer có 5 triệu bookings xử lý thế nào?
4. Làm sao query across buckets?
5. Cần đo phân phối nào trước chọn key?

### D. Ràng buộc nghiệp vụ

1. Chuyển UNIQUE tenant,email thế nào?
2. Ngăn double booking bằng cách nào?
3. Payment retry cần operationId ra sao?
4. Delete cascade phải thay bằng workflow nào?
5. Thế nào là outbox khác dual-write trực tiếp?

### E. Backfill/CDC

Tình huống:
- Backfill đọc B-91 v10.
- CDC apply B-91 v11.
- Backfill đến muộn.

1. Nếu overwrite mù, điều gì xảy ra?
2. Thiết kế version guard.
3. CDC checkpoint nên ghi lúc nào?
4. Một delete v12 tới trước upsert v11 xử lý thế nào?
5. Khi retention CDC hết trước catch-up, phải làm gì?

### F. Kiểm chứng

1. Row counts bằng nhau có chứng minh không thiếu key?
2. Cần canonical digest gồm gì?
3. Null/missing có xử lý giống nhau không?
4. Nếu SQL v15, NoSQL v14 nhưng lag cho phép 10 giây, báo ra sao?
5. Cross-tenant leakage kiểm tra thế nào?

### G. Cutover

1. Chọn canary phases.
2. Các stop/go gates.
3. Read rollback cần gì?
4. Write rollback khác gì?
5. Fencing old writer khi đổi authority như thế nào?

### H. Graph

Một Tag:POPULAR liên kết 50 triệu properties/views:
1. Vì sao thành supernode?
2. Traversal nên giới hạn thế nào?
3. Dùng index để tìm start nodes ra sao?
4. Có nên lưu mỗi VIEWED event thành edge mãi mãi?
5. Phải bảo vệ quan hệ nhạy cảm thế nào?

### I. Ước tính chi phí

Booking source ghi 2.000 lần/s, có ba projections:
1. Write amplification?
2. CDC broker/consumer throughput?
3. Một property đổi title gây fan-out gì?
4. RPO/RTO nếu source hỏng?
5. Vì sao query p99 thấp chưa chứng minh migration thành công?

### J. Thiết kế test

Lập ít nhất 15 tests:
- Point reads.
- Customer timeline pagination.
- Wrong tenant key.
- Concurrent writes.
- Conditional version conflict.
- Duplicate operationId.
- Backfill race.
- CDC duplicate/out-of-order.
- Tombstone.
- TTL expiry.
- Large customer.
- Hot partition.
- Graph supernode.
- Schema v1/v3.
- GSI lag.
- Retry timeout.
- Multi-region failover.
- Restore projection.
- SQL fallback.
- Authorization.

### K. ADR

Viết Architecture Decision Record gồm:
- Context/workload.
- Chọn mô hình nào cho query nào.
- Vì sao không thay mọi bảng.
- Data owner/invariants.
- Consistency SLO.
- Partition and index design.
- Migration stages.
- Rollback/failback.
- Operational cost/risk.
- Success criteria.

### L. Phản biện

Một đồng nghiệp nói:

> “NoSQL linh hoạt hơn SQL nên cứ tạo collection cho từng bảng. JOIN thì gọi nhiều GET. Dữ liệu trùng cứ update sau, không cần sourceVersion. Chuyển cả payment và booking trong một lần cho đỡ phức tạp. Backfill xong là bật 100% traffic, nếu lỗi tắt flag về SQL. Vì Redis/DynamoDB/MongoDB đều NoSQL nên cùng một consistency model.”

Hãy phản biện dựa trên:
- Access pattern.
- N+1.
- Denormalization/CDC.
- Source authority.
- Transaction/invariants.
- Version guards/deletes.
- GSI/index freshness.
- Source write failback.
- Cutover stages.
- Engine-specific semantics.

### Hướng giải

Một phương án hợp lý:
1. Giữ SQL authoritative ban đầu cho booking/payment.
2. Tạo document booking summary có embedded bounded items.
3. Dùng key–value cache cho point reads theo tenant+bookingId.
4. Dùng wide-column timeline theo tenant+customer+bucket, đo hot tenants.
5. Dùng graph read projection cho recommendation traversal cần thiết.
6. Dùng snapshot+CDC/outbox với sourceVersion, tombstone và idempotent apply.
7. Đối soát theo key/value/type/version, không chỉ count.
8. Shadow reads và canary trước khi chuyển reads.
9. Xác định rõ search/graph eventual freshness.
10. Chỉ di chuyển source writes khi unique/transaction/idempotency/DR đã được thiết kế và kiểm chứng.

## 41. Checklist trước khi công bố di chuyển thành công

1. **Đã lập inventory SQL schema, FK/unique/check/transactions?**
2. **Đã đo workload theo access pattern, p99 và distribution?**
3. **Đã xác định source authority cho từng entity/field?**
4. **Có quyết định giữ SQL ở các workflows phù hợp?**
5. **KV keys có tenant namespace và immutable IDs?**
6. **Có kế hoạch multi-key index consistency nếu dùng KV?**
7. **Document aggregate boundaries theo lifecycle?**
8. **Không nhúng unbounded arrays hoặc PII không cần thiết?**
9. **Có index cho document filter/sort?**
10. **Wide-column partition key đo theo distribution?**
11. **Bucketing và cross-bucket pagination có thiết kế?**
12. **Tombstone/TTL/compaction được hiểu theo engine?**
13. **Graph start-node index và traversal bounds có?**
14. **Supernode và sensitive relationships được xử lý?**
15. **Có mapping cho SQL unique/FK/check constraints?**
16. **Có phương án bảo vệ inventory/payment invariants?**
17. **Có idempotency và UNKNOWN commit handling?**
18. **Có schemaVersion/sourceVersion?**
19. **Có source snapshot/CDC boundary nhất quán?**
20. **Backfill apply không ghi đè versions mới?**
21. **Deletes/tombstones ngăn resurrection?**
22. **CDC checkpoint chỉ sau durable target apply?**
23. **CDC retention và gap recovery được diễn tập?**
24. **Có outbox hoặc write strategy rõ, tránh dual-write mù?**
25. **Có typed mappers Java, không copy field tùy tiện?**
26. **Có canonical hash và membership reconciliation?**
27. **Có shadow compare với đúng business semantics?**
28. **Có test pagination/sort/filter/query authorization?**
29. **Có hot tenant/skew load test?**
30. **Có query timeout, source protection và rate budgets?**
31. **Có freshness lag SLO cho projections?**
32. **Có canary routing và rollback reads?**
33. **Có source write cutover/fencing/failback nếu cần?**
34. **Có backup/restore và RPO/RTO cho NoSQL?**
35. **Có xử lý privacy erasure ở mọi projections?**
36. **Không gửi lại external side effects khi replay?**
37. **Có multi-region conflict/placement policy?**
38. **Có observability cho drift, lag, p99 và source cost?**
39. **Có runbook để repair/rebuild từng read model?**
40. **Chỉ retire SQL path sau khi invariants và rollback window đạt?**

**Kết luận:** Chuyển mô hình quan hệ sang NoSQL không có công thức “một bảng thành một collection”. Với **khóa–giá trị**, hãy thiết kế keys và các chỉ mục dẫn xuất quanh point reads, đồng thời hiểu chi phí đa key. Với **tài liệu**, hãy gom những thuộc tính cùng vòng đời thành bounded aggregates, phân biệt embedded snapshot với reference cần cập nhật. Với **cột rộng**, hãy thiết kế partition/clustering/bucket từ các truy vấn cụ thể và phân phối tải thực, thay JOIN bằng những read models được đối soát. Với **đồ thị**, hãy mô hình hóa quan hệ khi traversal thật sự là nhu cầu chính, và kiểm soát degree, depth cùng quyền truy cập. Trong mọi mô hình, phải **chuyển hoặc bảo toàn các bất biến giao dịch và phân quyền mà SQL từng giữ**; dùng snapshot + CDC/outbox, version-aware apply, deletes/tombstones, shadow compare, canary và rollback/failback có kế hoạch. Một migration chỉ thành công khi **dữ liệu đúng, ứng dụng giữ được hợp đồng nghiệp vụ, hiệu năng/chi phí đạt mục tiêu và hệ thống phục hồi được khi gặp lỗi**.
