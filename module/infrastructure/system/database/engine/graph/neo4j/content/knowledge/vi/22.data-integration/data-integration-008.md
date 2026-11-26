# Đối soát, xử lý sai lệch và khôi phục luồng đồng bộ sau sự cố

Khi Neo4j nhận dữ liệu từ một hệ thống khác, việc luồng đồng bộ báo “đã chạy xong” chưa đủ để chứng minh đồ thị đúng. Một sự kiện có thể bị gửi lặp, đến sai thứ tự, thiếu node đầu mối hoặc được ghi vào Neo4j thành công nhưng consumer mất kết nối trước khi xác nhận offset. Sự cố kéo dài còn có thể khiến dữ liệu nguồn tiếp tục thay đổi trong khi đồ thị dừng ở phiên bản cũ.

Bài học thuộc chương **Tích hợp dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j lưu dữ liệu liên kết theo mô hình **property graph**, dùng Cypher để cập nhật node/relationship, index và constraint để bảo vệ khóa, và thường được tích hợp bằng Java Driver hoặc Spring Data Neo4j. Trọng tâm bài là cách **đối soát dữ liệu giữa nguồn và Neo4j, phân loại và sửa sai lệch, sau đó khôi phục một luồng đồng bộ có thể phát lại an toàn**.

Sau khi học, bạn có thể:

- Định nghĩa nguồn dữ liệu chuẩn (*source of truth*), đơn vị đồng bộ, khóa định danh, phiên bản nguồn và điểm cắt đối soát.
- Đối chiếu số lượng, thuộc tính, phiên bản, quan hệ và trường hợp bị xóa bằng Cypher kết hợp dữ liệu nguồn.
- Phân biệt sự kiện trùng, mất, sai thứ tự, lỗi chuyển đổi, thiếu dependency và lỗi ghi một phần.
- Thiết kế cách ghi idempotent, quản lý checkpoint/offset và khôi phục sau sự cố mà không áp dụng lại một thay đổi nghiệp vụ hai lần.
- Lập runbook xử lý sự cố, kiểm thử phát lại và đo chất lượng đồng bộ bằng các chỉ số vận hành.

## 1. Nhìn toàn bộ luồng trước khi sửa một bản ghi

Giả sử hệ thống giao dịch lưu khách hàng và đơn hàng trong một cơ sở dữ liệu nguồn. Neo4j cung cấp truy vấn quan hệ giữa khách, đơn hàng và những thực thể liên quan:

~~~text
      HỆ THỐNG NGUỒN
    (Customer, Order)
             |
   Snapshot / CDC / Event
             |
             v
       Broker / Queue
             |
             v
  Consumer + chuẩn hóa dữ liệu
             |
      Giao dịch Neo4j
             |
             v
(:SyncDemoCustomer)-[:DEMO_PLACED]->(:SyncDemoOrder)
             |
             v
  Đối soát + cảnh báo + sửa chữa
~~~

Luồng trên có thể dùng Kafka, CDC hoặc hệ thống hàng đợi khác; bài không phụ thuộc một sản phẩm cụ thể. Mỗi thành phần có một trách nhiệm:

| Thành phần | Vai trò | Vấn đề cần kiểm soát |
| --- | --- | --- |
| Database nguồn | Giữ trạng thái nghiệp vụ gốc khi thiết kế chọn nguồn này làm chuẩn. | Đọc snapshot nhất quán, nhận biết thay đổi/xóa. |
| CDC/event producer | Chuyển sự thay đổi thành sự kiện. | Định danh, schema, thứ tự, tính đầy đủ của log. |
| Broker/queue | Lưu, chuyển giao và có thể phát lại sự kiện. | Offset, retention, retry, mất kết nối, phân vùng. |
| Consumer | Chuyển dữ liệu nguồn thành node/relationship. | Chuẩn hóa khóa, xử lý sự kiện cũ, ghi nguyên tử. |
| Neo4j | Lưu hình chiếu đồ thị phục vụ truy vấn. | Constraint, đúng endpoint, đúng trạng thái và phiên bản. |
| Reconciler | So sánh nguồn với trạng thái đích tại điểm cắt xác định. | Báo sai lệch thật, tránh báo nhầm do độ trễ. |

Trong kiến trúc này, **nguồn giao dịch là chuẩn** cho các thuộc tính được đồng bộ. Nếu một số thuộc tính được cập nhật trực tiếp trong Neo4j, cần làm rõ quyền sở hữu **theo từng trường**: bộ đối soát không được tùy tiện ghi đè dữ liệu do Neo4j làm nguồn chuẩn.

### 1.1. Đồng bộ không đồng nghĩa sao chép mọi cột

Ví dụ ánh xạ dữ liệu:

| Bản ghi nguồn | Biểu diễn trong Neo4j | Quy tắc |
| --- | --- | --- |
| Customer(tenant_id, customer_id, full_name, version) | `(:SyncDemoCustomer {tenantId, customerId, name, sourceVersion})` | Khóa khách gồm tenant và customer ID. |
| Order(tenant_id, order_id, customer_id, total_minor, status, version) | `(:SyncDemoOrder {tenantId, orderId, customerId, amountMinor, status, sourceVersion})` | Số tiền ở đơn vị nhỏ nhất, không làm tròn tùy ý. |
| Order.customer_id | `(:SyncDemoCustomer)-[:DEMO_PLACED]->(:SyncDemoOrder)` | Một đơn phải thuộc đúng một khách theo mô hình ví dụ. |
| Event(event_id, aggregate_key, version, payload) | `(:SyncDemoAppliedEvent {eventId, aggregateKey, sourceVersion})` | Dấu vết sự kiện đã áp dụng trong Neo4j. |

Tên label/type có tiền tố `SyncDemo` dùng cho ví dụ học tập. Hệ thống thật có thể chọn tên khác nhưng nên giữ **hợp đồng dữ liệu** rõ ràng giữa nguồn và đồ thị.

## 2. Những bất biến cần đối soát

Đối soát có ý nghĩa khi biết điều gì phải đúng. Với mô hình ví dụ:

| Mã | Bất biến | Phép kiểm tra |
| --- | --- | --- |
| R1 | Không có hai node `SyncDemoOrder` cùng cặp `(tenantId, orderId)`. | Constraint duy nhất theo cặp thuộc tính. |
| R2 | Thuộc tính đơn phản ánh trạng thái nguồn được chấp nhận mới nhất. | Đối chiếu `sourceVersion`, `status`, `amountMinor`, `customerId`. |
| R3 | Một đơn đang hoạt động có đúng một relationship `DEMO_PLACED` từ khách phù hợp. | Đếm cạnh, kiểm tra khóa khách và tenant của endpoint. |
| R4 | Bản ghi đã bị xóa ở nguồn được xử lý theo chính sách xóa đã chọn. | Kiểm tra tombstone, trạng thái ẩn hoặc xóa khỏi Neo4j. |
| R5 | Không có một sự kiện nghiệp vụ được áp dụng hai lần. | Dấu vết `eventId` duy nhất, xử lý phát lại idempotent. |
| R6 | Một điểm checkpoint chỉ được công bố sau khi phần ghi tương ứng an toàn. | Đối chiếu trạng thái commit và vị trí đọc sự kiện. |

**Bất biến phải có phạm vi:** tenant, loại thực thể, phiên bản schema và khoảng thời gian. “Neo4j có ít hơn nguồn 100 đơn” chưa đủ kết luận mất dữ liệu nếu nguồn đã bao gồm các đơn mới mà consumer chưa tới hoặc nếu Neo4j cố tình chỉ lưu đơn chưa bị xóa.

### 2.1. Khóa định danh và phiên bản nguồn

Mỗi sự kiện nên mang ít nhất:

~~~json
{
  "eventId": "orders/partition-2/offset-1042",
  "aggregateKey": "tenant-a/order-100",
  "entityType": "Order",
  "operation": "UPSERT",
  "sourceVersion": 12,
  "schemaVersion": 2,
  "payload": {
    "tenantId": "tenant-a",
    "orderId": "order-100",
    "customerId": "customer-7",
    "amountMinor": 125000,
    "status": "PAID"
  }
}
~~~

Đây là **hợp đồng minh họa**, không phải định dạng bắt buộc của mọi hệ thống CDC. `eventId` phải xác định ổn định cùng một sự kiện khi broker gửi lại; `aggregateKey` xác định thực thể cần giữ thứ tự; `sourceVersion` là phiên bản tăng đơn điệu **theo thực thể** nếu nguồn hỗ trợ. Một timestamp do nhiều máy tạo không mặc nhiên thay thế được phiên bản có thứ tự.

Nếu producer gửi **sự kiện chứa trạng thái đầy đủ** (*upsert snapshot*), bản mới hơn có thể thay thế trạng thái cũ; nếu producer gửi **delta** như “tăng số dư 200”, phải kiểm soát từng sự kiện chính xác và không được đơn giản bỏ qua các phiên bản trung gian. Chính sách phục hồi phụ thuộc loại sự kiện.

## 3. Phân loại sai lệch trước khi ra lệnh sửa

| Loại sai lệch | Ví dụ | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| **MISSING** | Nguồn có đơn O3, Neo4j không có. | Mất event, lỗi import, dependency chưa tới. | Xác nhận điểm cắt, phát lại/upsert đơn từ nguồn. |
| **EXTRA** | Neo4j còn O4 nhưng snapshot nguồn đầy đủ không còn. | Bỏ sót delete, lọc nguồn/đích không thống nhất. | Xác nhận chính sách xóa và phạm vi snapshot trước khi sửa. |
| **STALE** | Nguồn ở version 8, Neo4j mới version 6. | Consumer chậm, DLQ, offset bị nhảy. | Khôi phục/replay theo khóa hoặc chụp lại trạng thái mới nhất. |
| **VALUE_MISMATCH** | Cùng version nhưng `amountMinor` khác. | Bug chuyển đổi, lỗi làm tròn, mapping sai. | Quarantine; sửa mapper, rồi đồng bộ lại từ nguồn chuẩn. |
| **LINK_MISMATCH** | Đơn có hai `DEMO_PLACED` hoặc nối sai tenant. | Replay tạo cạnh trùng, xử lý đổi chủ sở hữu chưa đủ. | Sửa trong transaction dựa vào khóa nguồn, kiểm tra lại. |
| **DUPLICATE_EVENT** | Cùng `eventId` được nhận nhiều lần. | Broker giao ít nhất một lần, retry sau timeout. | Kiểm tra dấu vết xử lý, không áp dụng side effect lần nữa. |
| **OUT_OF_ORDER** | Event version 10 tới trước version 9. | Trộn phân vùng, xử lý song song, retry. | Giữ thứ tự theo aggregate hoặc áp dụng rule phiên bản phù hợp. |
| **SCHEMA_DRIFT** | `total_minor` đổi tên hoặc đổi kiểu. | Nâng phiên bản producer, consumer cũ. | Tạm dừng loại event không tương thích, cập nhật contract. |
| **UNKNOWN_OUTCOME** | Neo4j đã commit nhưng consumer mất phản hồi. | Lỗi kết nối ngay lúc commit. | Tra dấu vết giao dịch trước khi quyết định phát lại. |

Không coi mọi sai lệch là lý do xóa và nạp lại toàn bộ đồ thị. Ví dụ, thấy Neo4j “thừa” một đơn có thể là do snapshot nguồn thiếu một phân vùng; xóa ngay sẽ tạo lỗi thật từ một báo cáo sai.

## 4. Chuẩn bị schema tối thiểu để giảm lỗi đồng bộ

Những lệnh dưới đây chỉ nên dùng trong **database học tập hoặc môi trường đã được cấp quyền thay đổi schema**. Các label được đặt riêng cho bài thực hành.

~~~cypher
CREATE CONSTRAINT sync_demo_customer_unique IF NOT EXISTS
FOR (c:SyncDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT sync_demo_order_unique IF NOT EXISTS
FOR (o:SyncDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT sync_demo_event_unique IF NOT EXISTS
FOR (e:SyncDemoAppliedEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

Các uniqueness constraint này ngăn **giá trị khóa trùng khi các thuộc tính khóa hiện diện**; chúng không tự buộc mọi thành phần khóa luôn có mặt. Dịch vụ nhập liệu vẫn phải từ chối sự kiện thiếu `tenantId`, `orderId`, `customerId` hoặc `eventId`. Nếu yêu cầu cả tính hiện diện và duy nhất, đánh giá key/existence constraint theo phiên bản và edition Neo4j thực tế.

Một `MERGE` thiếu khóa chuẩn, ví dụ `MERGE (o:SyncDemoOrder {orderId: $orderId})` trong môi trường đa tenant, có thể ghép nhầm đơn giữa hai tenant. Constraint theo cặp không sửa được lỗi vì consumer đã dùng sai khóa. **Khóa trong `MERGE` phải khớp hợp đồng định danh.**

## 5. Đối soát chính xác cần một điểm cắt chung

Giả sử tại thời điểm T, nguồn có 10.000 đơn, nhưng Neo4j mới nhận đến offset 9.900. Nếu so trực tiếp hai số lượng của hệ thống đang ghi liên tục, 100 đơn khác nhau có thể là **độ trễ bình thường**, không phải mất dữ liệu.

Một quy trình đáng tin cậy:

1. Lấy snapshot nguồn nhất quán, đồng thời ghi nhận **watermark/LSN/offset tương ứng** theo cơ chế của nguồn.
2. Xác định phân vùng và tập khóa mà snapshot bao phủ, kể cả quy tắc biểu diễn bản ghi đã xóa.
3. Đợi consumer áp dụng tất cả thay đổi cần thiết đến watermark đó, hoặc dựng một hình chiếu Neo4j tương ứng tại cùng điểm cắt.
4. Ổn định phạm vi đối chiếu: nếu Neo4j tiếp tục nhận thay đổi **sau** điểm cắt, phải có cơ chế đọc trạng thái theo phiên bản hoặc cô lập phạm vi, nếu không bản mới hơn có thể bị báo sai khác giả.
5. So sánh bản ghi và relationship theo khóa, lưu kết quả theo `batchId` và phân loại sai lệch.

**Lưu ý:** “đã đọc đến offset N” không đủ nếu batch trước N còn lỗi hoặc ghi vào Neo4j chưa commit. Một watermark hợp lệ phải thể hiện **phần liên tục đã xử lý thành công** theo từng partition/source stream, có xét các event được đưa vào hàng đợi xử lý lỗi bền vững. Khi đánh dấu một event đã “bỏ qua”, cần lưu quyết định và tác động tới completeness.

### 5.1. Đối soát ở nhiều tầng

| Tầng kiểm tra | Chi phí | Khả năng phát hiện |
| --- | --- | --- |
| Tổng số bản ghi theo tenant/trạng thái/phân vùng | Thường thấp hơn so sánh toàn bộ. | Phát hiện mất/thừa số lượng nhưng không phát hiện hai lỗi triệt tiêu nhau. |
| Version/updatedAt theo khóa | Trung bình. | Phát hiện bản ghi cũ, khác phiên bản; không chứng minh payload đúng nếu mapper sai. |
| So sánh trường chuẩn hóa theo khóa | Cao hơn. | Tìm khác biệt giá trị thực sự. |
| Kiểm tra cạnh và endpoint | Phụ thuộc mức độ kết nối. | Phát hiện node đúng nhưng quan hệ thiếu, sai, thừa. |
| Checksum theo partition/canonical record | Có thể hỗ trợ so sánh lượng lớn. | Định vị phân vùng khác nhau; khi lệch vẫn cần drill-down theo khóa. |

Checksum phải được tính từ **cùng các trường, cùng chuẩn hóa giá trị, sắp xếp ổn định và cùng điểm cắt** ở hai phía. Một checksum “tổng cộng” thiếu chuẩn hóa không đủ chứng minh dữ liệu bằng nhau; hash còn có xác suất va chạm.

## 6. Ví dụ đối soát dữ liệu bằng Cypher

Phần này minh họa cách **nạp một snapshot chuẩn nhỏ** vào các node `SyncDemoExpectedOrder` để truy vấn đối chiếu ngay trong Neo4j. Trong thực tế, dữ liệu chuẩn thường được đối chiếu **ở công cụ bên ngoài** hoặc nạp vào một vùng staging có kiểm soát; không nên đưa toàn bộ snapshot nguồn vào đồ thị production nếu chỉ cần một đợt đối soát.

### 6.1. Tạo fixture có chủ đích sai lệch

Trên database thử nghiệm, tạo một khách và ba đơn ở trạng thái Neo4j:

~~~cypher
MERGE (c:SyncDemoCustomer {
  tenantId: 'tenant-demo', customerId: 'C1'
})
SET c.name = 'An', c.sourceVersion = 4
MERGE (o1:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O1'
})
SET o1.customerId = 'C1', o1.amountMinor = 1000,
    o1.status = 'PAID', o1.sourceVersion = 3
MERGE (o2:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O2'
})
SET o2.customerId = 'C1', o2.amountMinor = 700,
    o2.status = 'PENDING', o2.sourceVersion = 1
MERGE (o4:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O4'
})
SET o4.customerId = 'C1', o4.amountMinor = 400,
    o4.status = 'PAID', o4.sourceVersion = 1
MERGE (c)-[:DEMO_PLACED]->(o1)
MERGE (c)-[:DEMO_PLACED]->(o2)
MERGE (c)-[:DEMO_PLACED]->(o4);
~~~

Đối với bài tập, coi snapshot nguồn đã được chụp nhất quán gồm các đơn O1, O2 và O3. O2 ở nguồn có version và số tiền mới hơn; O3 chưa tới Neo4j; O4 không còn trong snapshot:

~~~cypher
UNWIND [
  {orderId: 'O1', customerId: 'C1', amountMinor: 1000,
   status: 'PAID', sourceVersion: 3},
  {orderId: 'O2', customerId: 'C1', amountMinor: 900,
   status: 'PAID', sourceVersion: 2},
  {orderId: 'O3', customerId: 'C1', amountMinor: 600,
   status: 'PENDING', sourceVersion: 1}
] AS src
MERGE (x:SyncDemoExpectedOrder {
  batchId: 'reconcile-demo-001',
  tenantId: 'tenant-demo',
  orderId: src.orderId
})
SET x.customerId = src.customerId,
    x.amountMinor = src.amountMinor,
    x.status = src.status,
    x.sourceVersion = src.sourceVersion;
~~~

Fixture không xóa những dữ liệu cũ có thể trùng khóa trong môi trường dùng chung. Hãy chọn database học tập riêng và xác nhận không có các node demo từ lượt chạy trước nếu cần kết quả đúng như bảng minh họa.

### 6.2. Tìm bản ghi nguồn thiếu hoặc khác nội dung ở đích

Giả sử ứng dụng truyền `$batchId = 'reconcile-demo-001'` và `$tenantId = 'tenant-demo'`:

~~~cypher
MATCH (x:SyncDemoExpectedOrder {
  batchId: $batchId, tenantId: $tenantId
})
OPTIONAL MATCH (o:SyncDemoOrder {
  tenantId: x.tenantId, orderId: x.orderId
})
WITH x, o,
     CASE
       WHEN o IS NULL THEN 'MISSING'
       WHEN o.sourceVersion IS NULL
         OR o.sourceVersion <> x.sourceVersion
         OR o.customerId IS NULL
         OR o.customerId <> x.customerId
         OR o.amountMinor IS NULL
         OR o.amountMinor <> x.amountMinor
         OR o.status IS NULL
         OR o.status <> x.status
       THEN 'DIFFERENT'
       ELSE 'OK'
     END AS result
WHERE result <> 'OK'
RETURN x.orderId AS orderId,
       result, x.sourceVersion AS sourceVersion,
       o.sourceVersion AS neo4jVersion,
       x.amountMinor AS sourceAmount,
       o.amountMinor AS neo4jAmount
ORDER BY orderId;
~~~

Kỳ vọng: **O2 = DIFFERENT**, **O3 = MISSING**. Truy vấn so sánh rõ các thuộc tính cần thiết và kiểm tra trường null; khi ứng dụng có nhiều trường hơn, phải phát biểu đầy đủ phép chuẩn hóa và so sánh theo hợp đồng dữ liệu.

### 6.3. Tìm bản ghi đích không có trong snapshot nguồn

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
WHERE NOT EXISTS {
  MATCH (x:SyncDemoExpectedOrder {
    batchId: $batchId,
    tenantId: o.tenantId,
    orderId: o.orderId
  })
}
RETURN o.orderId AS extraOrderId,
       o.status AS status, o.sourceVersion AS sourceVersion
ORDER BY extraOrderId;
~~~

Kỳ vọng: **O4**. Chỉ được kết luận O4 cần xóa nếu snapshot có **độ bao phủ đầy đủ** và quy tắc nguồn nói rằng O4 thực sự bị xóa. Snapshot chỉ lấy “đơn đã thanh toán” sẽ không thể dùng để kết luận mọi đơn không có trong snapshot phải bị xóa.

### 6.4. Phát hiện sai lệch quan hệ và endpoint

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
OPTIONAL MATCH (c:SyncDemoCustomer)-[r:DEMO_PLACED]->(o)
WITH o,
     count(r) AS totalLinks,
     sum(
       CASE
         WHEN c IS NULL
           OR c.tenantId <> o.tenantId
           OR c.customerId <> o.customerId
         THEN 1 ELSE 0
       END
     ) AS wrongLinks
WHERE totalLinks <> 1 OR wrongLinks > 0
RETURN o.orderId AS orderId, totalLinks, wrongLinks
ORDER BY orderId;
~~~

Trong mô hình ví dụ, mỗi đơn phải có đúng một cạnh tới khách cùng tenant và ID khớp thuộc tính `customerId` của đơn. Truy vấn trả những đơn thiếu cạnh, thừa cạnh hoặc nối sai. Neo4j không có relationship “mồ côi” không có endpoint; dạng lỗi thường gặp là **endpoint nghiệp vụ sai**, không phải cạnh trỏ tới node đã bị xóa khỏi cơ sở dữ liệu.

### 6.5. Phân biệt số lượng đúng với dữ liệu đúng

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
RETURN count(o) AS targetOrders,
       count(DISTINCT o.customerId) AS distinctCustomerIds;
~~~

Count và `DISTINCT` giúp kiểm tra nhanh quy mô, nhưng không đủ chứng minh tính đúng đắn. Trong fixture trên, Neo4j có ba đơn O1, O2, O4 và snapshot nguồn cũng có ba đơn O1, O2, O3; **số lượng bằng nhau nhưng vẫn có hai loại sai lệch**. Muốn kết luận đồng bộ đúng, cần so sánh khóa, nội dung, phiên bản và quan hệ.

## 7. Xử lý sai lệch dựa trên nguyên nhân, không sửa “mù”

Một bản ghi khác nhau có thể do quá trình đồng bộ còn chạy, do producer sai, mapper lỗi hoặc do người quản trị sửa trực tiếp trên Neo4j. Hướng sửa phụ thuộc nguyên nhân:

1. **Đánh dấu phạm vi sự cố:** tenant, entity type, partition, khoảng offset/version, thời điểm bắt đầu và kết thúc.
2. **Lưu bằng chứng trước khi sửa:** snapshot/mẫu khóa, query diff, log ingest, event ID, phiên bản code và các checkpoint.
3. **Cách ly đường ghi lỗi:** tạm dừng consumer/partition ảnh hưởng nếu tiếp tục ghi có thể làm sai thêm; tránh dừng toàn hệ thống khi chỉ một phân vùng lỗi và có thể cô lập.
4. **Xác nhận nguồn chuẩn:** nếu nguồn không nhất quán, sửa tại nguồn trước; tránh “sửa đúng” Neo4j dựa trên dữ liệu nguồn chưa được xác minh.
5. **Chọn sửa chính xác:** replay event, re-upsert một aggregate, xây dựng lại một partition, hoặc bổ sung/xóa relationship theo chính sách.
6. **Đọc lại và đối soát:** kiểm chứng bất biến R1–R6 trên phạm vi đã sửa, sau đó mới mở luồng và cập nhật trạng thái sự cố.

### 7.1. MISSING và STALE

Nếu nguồn cung cấp sự kiện **trạng thái đầy đủ**, có thể nạp lại bản mới nhất theo khóa với `sourceVersion` để tránh ghi đè bản mới bằng bản cũ. Nếu nguồn chỉ cấp **delta**, phải khôi phục đầy đủ chuỗi sự kiện theo thứ tự hoặc tái tạo lại từ một snapshot chuẩn rồi replay các delta sau điểm cắt.

Khi cần tạo relationship tới `Customer` mà node khách chưa có, không nên tự tạo khách với các trường ngẫu nhiên để “cho chạy qua”. Hãy xử lý thứ tự dependency, tải khách trước hoặc đưa sự kiện đơn hàng vào hàng đợi chờ có giới hạn và có cảnh báo.

### 7.2. VALUE_MISMATCH cùng phiên bản

Cùng `sourceVersion` mà giá trị khác nhau thường đáng điều tra hơn chậm trễ bình thường. Kiểm tra quy tắc:

- Mã tiền tệ, đơn vị tiền nhỏ nhất, làm tròn và kiểu số.
- Chuẩn hóa `null`, chuỗi rỗng, mã trạng thái và timezone.
- Chuẩn hóa ký tự Unicode/chữ hoa chữ thường của khóa.
- Phiên bản schema và logic mapping giữa producer và consumer.
- Bản ghi có thể đã bị sửa trực tiếp trên Neo4j hay không.

Nếu mapper đang sai, phát lại cùng sự kiện bằng code cũ chỉ tái tạo sai lệch. Sửa mapper, thử dữ liệu mẫu, sau đó backfill/replay với dấu vết kết quả.

### 7.3. EXTRA và DELETE

CDC có thể biểu diễn xóa bằng **tombstone** hoặc sự kiện `DELETE`. Hệ thống cần chọn rõ:

- **Physical delete:** bỏ node/relationship tương ứng; phải xem có dữ liệu liên kết khác còn cần không.
- **Soft delete:** giữ node với `deleted=true` / `deletedAt` để truy vấn nghiệp vụ chủ động bỏ qua.
- **Archive:** chuyển lịch sử sang vùng lưu trữ phù hợp thay vì giữ mãi trong luồng truy vấn nóng.

Không tự dùng `DETACH DELETE` hàng loạt trên dữ liệu thật chỉ vì thấy bản ghi “thừa”: lệnh này xóa mọi relationship nối vào node. Một event xóa **đến muộn** cũng không được xóa phiên bản mới hơn; luôn gắn chính sách delete với version/sequence của thực thể.

### 7.4. LINK_MISMATCH

Khi một đơn đổi khách sở hữu theo nghiệp vụ, lệnh chỉ `MERGE (newCustomer)-[:DEMO_PLACED]->(order)` có thể **để lại relationship cũ**. Phải xử lý cả liên kết trước đó và liên kết mới **trong một transaction**, sau khi xác minh người nhận mới, phiên bản sự kiện và quyền thay đổi. Nếu nghiệp vụ không cho phép đổi khách sở hữu, hãy coi event đó là lỗi nguồn thay vì âm thầm sửa đồ thị.

## 8. Ghi idempotent và checkpoint theo đúng ranh giới transaction

Trong một luồng được broker phát lại, cách triển khai thực tế thường là **at-least-once delivery**. Consumer có thể nhận cùng một sự kiện nhiều lần; điều cần bảo vệ là **cùng một thay đổi nghiệp vụ không được áp dụng nhiều lần**.

### 8.1. Ghi event marker và cập nhật đồ thị trong cùng transaction

Ý tưởng:

~~~text
Nhận sự kiện
   |
   v
Kiểm tra schema + khóa + version
   |
   v
BEGIN TRANSACTION Neo4j
   |
   +-- CREATE marker cho eventId (unique constraint)
   |
   +-- Kiểm tra dependency và cập nhật node/relationship
   |
   +-- COMMIT thành công cả marker lẫn dữ liệu
   |
   v
Xác nhận offset với broker
~~~

Nếu update thất bại, marker cũng phải rollback. Nếu DB commit rồi client mất kết nối trước khi ack broker, lần nhận lại sẽ gặp marker đã tồn tại; consumer phải kiểm chứng marker tương ứng **đúng sự kiện/payload** và coi đây là replay, thay vì cập nhật đồ thị lần nữa.

Chỉ `MERGE (o:SyncDemoOrder {tenantId, orderId})` chưa đủ đảm bảo idempotency cho mọi trường hợp: một câu `SET total = total + $delta` bị gọi hai lần vẫn áp dụng delta hai lần. Ngược lại, một sự kiện chứa **trạng thái đầy đủ** có thể an toàn khi upsert có kiểm soát version, nhưng vẫn phải bảo vệ các thay đổi liên quan như quan hệ và hiệu ứng bên ngoài.

### 8.2. Ví dụ Java Driver cho sự kiện upsert đơn hàng

Ví dụ sau minh họa giao dịch ghi nguyên tử bằng Neo4j Java Driver. Các event được giả định chứa **trạng thái đơn đầy đủ** và được consumer đưa vào xử lý **tuần tự theo khóa aggregate**. Khách hàng đích phải có trước; chính sách thiếu dependency sẽ được xử lý ở tầng điều phối.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderSyncWriter {
    public static boolean applyUpsert(Driver driver, Map<String, Object> p) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                // Marker này và tất cả cập nhật bên dưới cùng một transaction.
                tx.run("""
                    CREATE (:SyncDemoAppliedEvent {
                      eventId: $eventId,
                      aggregateKey: $aggregateKey,
                      sourceVersion: $sourceVersion,
                      processedAt: datetime()
                    })
                    """, p).consume();

                long customerCount = tx.run("""
                    MATCH (c:SyncDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })
                    RETURN count(c) AS n
                    """, p).single().get("n").asLong();

                if (customerCount != 1L) {
                    throw new IllegalStateException(
                        "MISSING_CUSTOMER_DEPENDENCY");
                }

                return tx.run("""
                    MATCH (c:SyncDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })
                    MERGE (o:SyncDemoOrder {
                      tenantId: $tenantId, orderId: $orderId
                    })
                    ON CREATE SET o.sourceVersion = -1
                    WITH c, o
                    WHERE o.sourceVersion < $sourceVersion
                    SET o.customerId = $customerId,
                        o.amountMinor = $amountMinor,
                        o.status = $status,
                        o.sourceVersion = $sourceVersion,
                        o.syncedAt = datetime()
                    MERGE (c)-[:DEMO_PLACED]->(o)
                    RETURN count(o) AS applied
                    """, p).single().get("applied").asLong() == 1L;
            });
        }
    }
}
~~~

**Điều kiện của ví dụ:**

- Các constraint ở mục 4 đã có và `eventId` là duy nhất toàn luồng. `p` chứa các khóa `eventId, aggregateKey, tenantId, orderId, customerId, amountMinor, status, sourceVersion` với kiểu hợp lệ.
- Consumer dùng **một luồng xử lý tuần tự trên mỗi aggregate**, hoặc cơ chế khóa tương đương. Chỉ kiểm tra `o.sourceVersion < $sourceVersion` mà không kiểm soát cạnh tranh ghi không đủ để chứng minh an toàn với mọi lịch thực thi song song.
- Quy tắc minh họa giả định **khách sở hữu đơn không thay đổi**. Nếu `customerId` có thể thay, phải xóa/cập nhật quan hệ cũ trong cùng giao dịch; không được dùng nguyên mẫu này.
- Khi source version đến muộn và thấp hơn version đã lưu, truy vấn cập nhật trả 0, trong khi marker sự kiện vẫn được commit như một sự kiện đã phân loại là cũ. Với event dạng delta cần chính sách khác.
- Unique constraint có thể từ chối lần replay `eventId` đã ghi. Đoạn code **chưa xử lý nhánh lỗi duplicate**; adapter phía ngoài phải phân biệt đúng lỗi uniqueness của marker, đọc lại marker/payload fingerprint để xác nhận replay thật và không bỏ qua những lỗi database khác.
- `executeWrite` có thể retry callback khi gặp một số lỗi transient. Không gọi API, gửi email hoặc ack broker **bên trong callback**; các side effect ngoài Neo4j không tự được rollback theo transaction.

Trong sản phẩm thực tế nên bổ sung hash payload hoặc metadata nguồn để phát hiện cùng `eventId` nhưng nội dung khác, kiểm tra khả năng tồn tại của endpoint, giới hạn thời gian, quan sát tracing và phân loại lỗi. Ví dụ tập trung vào nguyên tắc **marker và cập nhật đồ thị cùng commit**.

### 8.3. Offset broker không thuộc transaction Neo4j

Không có transaction ACID tự động bao trùm cả Neo4j và broker chỉ vì ứng dụng gọi hai API liên tiếp. Hãy xét hai thứ tự:

| Thứ tự | Rủi ro |
| --- | --- |
| Ack/commit offset **trước** khi commit Neo4j | Worker chết sau ack có thể khiến sự kiện mất khỏi phạm vi replay dù dữ liệu chưa ghi. |
| Commit Neo4j **trước**, ack offset sau | Worker chết giữa hai bước gây replay; marker và idempotency giúp nhận biết sự kiện đã áp dụng. |

Vì vậy, với delivery ít nhất một lần, thông thường chọn **commit Neo4j trước rồi xác nhận offset**, kết hợp event marker và khả năng phát lại. Nếu event được đưa vào DLQ/hàng đợi chờ, chỉ ack bản gốc khi đã **ghi bền vững quyết định chuyển hướng** theo quy tắc bảo đảm không mất dữ liệu; với broker theo partition, checkpoint phải phản ánh cả các offset trước đó.

Không hứa “exactly once end-to-end” nếu chưa chứng minh ranh giới transaction và cơ chế idempotency giữa toàn bộ hệ thống.

## 9. Phục hồi luồng đồng bộ sau sự cố

Một sự cố thường có ba lớp cần khôi phục: **dịch vụ chạy trở lại**, **mọi sự kiện cần thiết được xử lý**, và **Neo4j trở về trạng thái đúng theo nguồn**. Chỉ khởi động lại consumer mới đáp ứng lớp đầu.

### 9.1. Runbook theo trình tự

| Bước | Hành động | Điều kiện chuyển tiếp |
| --- | --- | --- |
| 1. Khoanh vùng | Ghi nhận thời gian lỗi, topic/partition, tenant, code/schema version, các event ID và offset liên quan. | Xác định phạm vi ảnh hưởng có bằng chứng. |
| 2. Chặn lỗi lan rộng | Tạm dừng consumer hoặc partition lỗi; giữ nguyên log, DLQ và checkpoint. | Không tiếp tục ghi dữ liệu sai trên phạm vi đó. |
| 3. Bảo vệ dữ liệu nguồn | Xác nhận source còn snapshot/log cần replay; kiểm tra retention, sao lưu và quyền truy cập. | Có điểm khôi phục đủ tin cậy. |
| 4. Chẩn đoán | Xem lỗi schema, converter, constraint, node dependency, deadlock, timeout hay lỗi mạng. | Biết cách xử lý lỗi có thể tái diễn. |
| 5. Sửa và thử | Sửa mã/ánh xạ/config, thử trên fixture và mẫu event bị lỗi. | Ghi đúng, idempotent, rollback và phân loại lỗi đạt. |
| 6. Chọn điểm phát lại | Dựa trên checkpoint **đã commit**, watermark nguồn và event marker; không chỉ dựa vào offset cuối log. | Có danh sách partition/offset hoặc khóa cần chạy lại. |
| 7. Replay có kiểm soát | Chạy đúng thứ tự theo aggregate; giới hạn throughput để không quá tải Neo4j. | Lag giảm, DLQ và lỗi mới được theo dõi. |
| 8. Đối soát lại | So sánh theo cùng điểm cắt, kiểm node, property, relationship, delete và version. | Sai lệch thuộc phạm vi sự cố về 0 hoặc có ngoại lệ được phê duyệt. |
| 9. Mở luồng bình thường | Bỏ pause theo từng partition, tăng tải dần và theo dõi tiếp. | Checkpoint ổn định, không tái diễn sai lệch. |
| 10. Hậu kiểm | Lưu timeline, nguyên nhân gốc, tác động và biện pháp ngăn tái diễn. | Có bằng chứng khôi phục và hành động theo dõi. |

Nếu lỗi gây ghi sai vào Neo4j, **đừng chỉ replay thêm event mới** vì dữ liệu sai cũ có thể vẫn tồn tại. Cần phục hồi điểm đúng từ snapshot nguồn, phát lại hoặc sửa có kiểm chứng theo từng aggregate, rồi đối soát.

### 9.2. Mốc khôi phục minh họa

~~~text
Nguồn:       ... 1040  1041  1042  1043  1044  1045 ...
Consumer:          OK    OK   lỗi    ?     chưa  chưa
Neo4j marker:      có   có    chưa  kiểm tra  -   -
Checkpoint:              1041
                             |
                    Khởi động lại từ vị trí
                    phù hợp sau 1041
~~~

Khi event 1042 không được commit, không được đánh dấu checkpoint 1044 chỉ vì event 1043 đã xử lý thành công ở một worker song song. Nếu event 1043 đã commit nhưng không được ack, replay của nó phải được nhận diện bởi marker. Trong Kafka và các hệ thống theo partition, việc quản lý **offset liên tục đã hoàn tất** là tối quan trọng.

### 9.3. Chọn replay hay tái dựng lại

| Hoàn cảnh | Phương án |
| --- | --- |
| Lỗi ngắn, log đầy đủ, dữ liệu đích trước lỗi đúng. | Replay từ điểm đã được xác nhận an toàn, sử dụng dedup/idempotency. |
| Một nhóm entity sai do mapper mới. | Sửa mapper, re-upsert hoặc backfill **phạm vi khóa ảnh hưởng** từ nguồn chuẩn, rồi chạy CDC nối tiếp. |
| Log quá thời gian retention, thiếu một đoạn thay đổi. | Dựng lại từ snapshot nguồn nhất quán và CDC bắt đầu tại watermark của snapshot. |
| Dữ liệu đích sai trên diện rộng và không tin cậy được. | Tạo lại hình chiếu đồ thị trong vùng cô lập, chạy backfill + CDC catch-up, đối soát rồi chuyển luồng đọc. |
| Event nguồn bị thiếu và không có snapshot khả dụng. | Không thể khẳng định đã phục hồi đầy đủ; phải điều tra/khôi phục dữ liệu nguồn hoặc sao lưu khác. |

Đối với cơ chế **snapshot + CDC**, điểm bắt đầu CDC phải khớp watermark của snapshot để không để khoảng hở hoặc bỏ qua thay đổi. Nếu có vùng trùng khi chuyển tiếp, phải dựa vào idempotency để phát lại an toàn. Thứ tự thao tác xóa và cập nhật ở thời điểm chuyển tiếp cũng cần được kiểm chứng.

## 10. Dữ liệu đến sai thứ tự, retry và DLQ

### 10.1. Hai loại sự kiện dẫn đến hai chính sách khác nhau

**Upsert trạng thái đầy đủ:**

~~~text
Order O2, version 6: amountMinor = 900
Order O2, version 5: amountMinor = 700 (đến muộn)
~~~

Nếu version 6 đã được áp dụng, event version 5 không được ghi đè lại. Có thể đánh dấu event cũ đã được xử lý/bỏ qua theo chính sách và giữ state version 6.

**Delta:**

~~~text
Account A, version 5: +200
Account A, version 6: -50
~~~

Nếu chưa áp dụng version 5 mà nhận version 6, không thể bỏ version 5 rồi cho rằng trạng thái cuối đúng. Phải xử lý đầy đủ chuỗi delta theo thứ tự, hoặc nạp một snapshot đã bao gồm các thay đổi tương ứng.

### 10.2. Thiếu node endpoint

Giả sử event Order tới trước event Customer:

~~~text
UPSERT Order O3 -> tham chiếu Customer C1
UPSERT Customer C1 -> đến sau
~~~

Có thể dùng một trong các cơ chế tùy nghiệp vụ:

- Chuyển event đơn hàng vào **hàng đợi chờ dependency** bền vững, có timeout và cảnh báo; xử lý lại khi Customer xuất hiện.
- Tách hai pha: nạp các node trước, sau đó ghép relationship dựa trên khóa nguồn.
- Thiết kế producer/broker giữ thứ tự phù hợp giữa các thực thể có phụ thuộc, nếu nguồn cho phép.

Tạo “customer rỗng” làm placeholder chỉ là lựa chọn hợp lệ nếu hệ thống định nghĩa rõ quy tắc và kiểm soát việc hoàn thiện; nếu không, placeholder có thể che giấu dữ liệu thiếu. Không để event chờ vô hạn mà không có metric và cơ chế can thiệp.

### 10.3. DLQ không đồng nghĩa sửa xong

Dead-letter queue (DLQ) giữ các event chưa xử lý được sau chính sách retry. Cần ghi lại:

- Event ID, partition/offset, aggregate key và source version.
- Nguyên nhân, mã lỗi, số lần retry, thời điểm đầu tiên/cuối cùng thất bại.
- Schema version và vị trí payload nguồn để có thể phát lại an toàn.
- Trạng thái: đang chờ, đã sửa nguyên nhân, đã replay, đã đối soát, hoặc chấp nhận ngoại lệ có phê duyệt.

Một số event lỗi do dữ liệu không hợp lệ (*poison message*) nên dừng retry mù để không chặn mãi luồng; nhưng việc chuyển sang DLQ cần bảo toàn khả năng khôi phục và không làm checkpoint báo “đã đồng bộ đủ” khi chưa giải quyết. Event sau phụ thuộc event trong DLQ có thể phải tạm dừng theo aggregate.

## 11. Kiểm thử sự cố và chứng minh khôi phục

Một hệ thống tích hợp cần kiểm thử các trường hợp thất bại, không chỉ đường đi thành công. Dùng môi trường cô lập có source và Neo4j fixture riêng.

| Test | Cách tạo tình huống | Kỳ vọng |
| --- | --- | --- |
| S01 — Event lặp | Giao cùng `eventId` hai lần. | Một lần áp dụng nghiệp vụ; marker phù hợp; replay không gây cạnh trùng. |
| S02 — Ghi DB thất bại | Tạo lỗi sau marker nhưng trước cập nhật order. | Cả marker và cập nhật rollback; offset chưa bị ack sai. |
| S03 — Mất phản hồi commit | Giả lập mất kết nối ngay sau khi DB có thể đã commit. | Consumer tra marker/phân loại outcome, không cập nhật hai lần. |
| S04 — Sai thứ tự | Phát version 6 rồi version 5 của cùng order snapshot. | Đích giữ version 6; xử lý event cũ có ghi nhận. |
| S05 — Mất một event delta | Bỏ version giữa chuỗi tăng/giảm. | Detect gap và không tự coi dòng delta đã đủ. |
| S06 — Thiếu Customer | Order đến trước node Customer. | Không commit quan hệ sai; đưa vào retry/dependency queue. |
| S07 — Tombstone | Xóa order ở nguồn. | Đích xóa/đánh dấu xóa đúng chính sách và version. |
| S08 — Sai kiểu dữ liệu | `amountMinor` là chuỗi thay vì số nguyên. | Reject/quarantine, không ghi giá trị sai âm thầm. |
| S09 — Đứt luồng lâu | Tạm dừng consumer rồi vượt qua thời gian retry. | Phục hồi từ checkpoint/log hoặc snapshot phù hợp; đối soát đạt. |
| S10 — Thừa quan hệ | Bơm thêm một `DEMO_PLACED` sai endpoint trong fixture. | Query đối soát phát hiện và quy trình sửa giữ đúng một cạnh. |
| S11 — Cùng count khác khóa | Giữ số đơn bằng nhau nhưng thay O3 bằng O4. | So sánh theo khóa phát hiện MISSING và EXTRA. |
| S12 — Replay đồng thời | Nhiều worker nhận cùng aggregate/event. | Constraint và chính sách serialize/retry không làm sai state. |

### 11.1. Bài test có oracle rõ ràng

Với fixture ở mục 6, một test đối soát trước sửa cần nhận:

| Bản ghi | Phát hiện |
| --- | --- |
| O1 | OK |
| O2 | DIFFERENT — version và nội dung cũ |
| O3 | MISSING |
| O4 | EXTRA — chỉ kết luận cần xóa nếu snapshot đầy đủ |

Sau khi khôi phục từ nguồn chuẩn, chạy lại truy vấn theo cùng phạm vi. Bài test đạt khi không còn sai lệch **và** kiểm tra relationship hợp lệ. Đừng chỉ đếm số đơn hoặc chỉ kiểm `sourceVersion`: một mapper sai có thể ghi sai payload ngay cả khi version đã tăng.

### 11.2. Kiểm thử hiệu năng của replay

Ngoài độ đúng, cần đo:

| Chỉ số | Mục đích |
| --- | --- |
| Consumer lag theo partition và tuổi event cũ nhất chưa xử lý | Biết thời gian bắt kịp nguồn sau khi khởi động lại. |
| Số event áp dụng, bỏ qua do cũ, trùng và chuyển DLQ | Nhận diện replay bất thường hoặc mất tiến độ. |
| Thời gian commit Neo4j p95/p99 và tỷ lệ lỗi | Phát hiện quá tải, cạnh tranh lock, cấu hình batch không phù hợp. |
| Số sai lệch đối soát theo loại/tenant và tuổi sai lệch | Biết chất lượng dữ liệu sau catch-up. |
| Số event đang đợi dependency và tuổi già nhất | Phát hiện chuỗi sự kiện bị kẹt. |
| Khoảng còn lại của log retention | Biết liệu log còn đủ thời gian cho replay nếu phải dừng. |

Tăng concurrency không luôn giúp replay nhanh hơn: nhiều worker cùng cập nhật một aggregate có thể gây lock contention, deadlock hoặc phá thứ tự. Tùy quy mô, cân nhắc chia theo tenant/aggregate, batch có giới hạn và điều tiết throughput; đo cả write latency lẫn nhu cầu đọc trực tuyến.

## 12. Vận hành an toàn với batch và migration

Neo4j có thể xử lý import/batch bằng Cypher, Java Driver hoặc các công cụ phù hợp. Khi một job chia nhiều giao dịch nhỏ, **một batch thất bại không làm rollback các batch đã commit trước đó**. Do đó:

1. Gán ID phiên chạy và trạng thái mỗi partition/chunk để biết phần đã hoàn thành.
2. Thiết kế mỗi chunk có thể replay an toàn; dùng khóa chuẩn và kiểm tra source version.
3. Không dùng một transaction cực lớn nếu vượt khả năng bộ nhớ hoặc thời gian khóa; nhưng cũng không tách những cập nhật cần atomicity của **một thực thể** sang nhiều transaction không có cơ chế bù trừ.
4. Chỉ đánh dấu watermark hoàn tất khi mọi chunk cần thiết đã commit, cùng các lỗi được phân loại và giữ lại để xử lý.
5. Đối soát lại sau chuyển schema hoặc thay mapping, kể cả khi lệnh import không báo lỗi.

Các câu lệnh có `CALL { ... } IN TRANSACTIONS` thường chia công việc thành nhiều giao dịch. Nếu batch số 1–5 đã commit rồi batch số 6 lỗi, toàn bộ job **không có tính nguyên tử trên sáu batch**. Cần checkpoint riêng và cơ chế chạy tiếp, đặc biệt với các lần nhập ban đầu hoặc nạp lại dữ liệu sau sự cố.

Đừng tạo các constraint hay index mới trực tiếp giữa lúc luồng đang quá tải nếu chưa kiểm tra trạng thái schema và kế hoạch vận hành. Đặt tên nhất quán, giám sát trạng thái index, và kiểm tra phiên bản/edition khi dùng tính năng mới.

## 13. Quy tắc bảo mật và truy vết thay đổi

Đối soát thường xử lý bản ghi có PII hoặc thông tin giao dịch. Báo cáo diff nên lưu **khóa, loại sai lệch, version và hash cần thiết** thay vì sao chép toàn bộ payload nhạy cảm. Giới hạn quyền truy cập snapshot nguồn, topic/DLQ, tài khoản ghi Neo4j và công cụ sửa dữ liệu.

Mọi hành động sửa nên có audit gồm:

- Ai hoặc job nào thực hiện; lý do, ticket sự cố và thời điểm.
- Phiên bản mapper, nguồn chuẩn, batch/watermark và danh sách khóa ảnh hưởng.
- Hành động: replay, upsert lại, xóa theo tombstone hoặc sửa relationship.
- Kết quả trước/sau, số bản ghi xử lý, số lỗi còn lại và bằng chứng đối soát.

Nếu dữ liệu phân biệt tenant, mọi truy vấn kiểm tra và sửa phải ràng buộc đúng `tenantId`. Không “sửa” bản ghi từ tenant khác vì chỉ khớp `orderId`. Truyền tham số vào Cypher qua driver; tránh xây query bằng nối trực tiếp chuỗi từ event bên ngoài.

## 14. Bài tập áp dụng

**Bài 1 — Đối soát trên fixture:** Chạy phần 6 trên database học tập, thực thi truy vấn so sánh hai chiều và truy vấn quan hệ. Giải thích vì sao cùng có ba đơn không chứng minh hai bên đồng nhất. Hãy mô tả quy trình sửa O2, O3, O4 với điều kiện snapshot nguồn đầy đủ.

**Bài 2 — Thiết kế marker idempotent:** Một consumer nhận lại event 1042 sau khi Neo4j commit nhưng trước khi broker nhận ack. Hãy mô tả cách tra marker, xác minh event ID/payload và quyết định ack hay điều tra. Chỉ ra vì sao `SET balance = balance + 200` không an toàn nếu replay mà không có bảo vệ riêng.

**Bài 3 — Đổi người đặt đơn:** Nguồn phát event thay `customerId` của O5 từ C1 sang C2. Hãy viết luồng Cypher chạy trong **một transaction** để kiểm tra version, bỏ cạnh sở hữu cũ và tạo cạnh mới. Đề xuất hai assert sau commit để bảo đảm không có hai cạnh hoặc cạnh sai tenant.

**Bài 4 — Khoảng hở CDC:** Snapshot nguồn được chụp ở watermark W, nhưng CDC consumer khởi động từ W+100. Nêu những dữ liệu nào có thể bị thiếu, vì sao một lần đếm hiện tại không đủ, và cách xây lại hình chiếu/nguồn log nhằm không bỏ sót đoạn W+1 đến W+99.

**Bài 5 — Runbook sự cố:** Consumer dừng 8 giờ, một số event đã vào DLQ và broker sắp hết thời gian giữ log. Xếp thứ tự các bước: cô lập luồng lỗi, bảo vệ log/snapshot, xác định checkpoint đáng tin, sửa mapper, replay/catch-up, đối soát, và mở lại tải. Giải thích phép đo nào chứng minh thực sự phục hồi.

**Bài 6 — Phân biệt snapshot và delta:** Với event trạng thái đầy đủ đến thứ tự version 8 rồi 7, bạn xử lý như thế nào? Nếu event là “+5” và “-3” nhưng một event thiếu, điều gì thay đổi trong chiến lược phục hồi?

## 15. Checklist hoàn thành một lần khôi phục

Một sự cố đồng bộ chỉ nên được kết luận đã khôi phục khi có bằng chứng rằng:

1. Nguồn chuẩn, phạm vi tenant/entity, schema version và điểm cắt đã được xác định.
2. Mọi offset/event cần thiết đã commit, hoặc đang ở hàng đợi xử lý lỗi bền vững có chủ sở hữu và kế hoạch rõ ràng.
3. Không có dấu hiệu ghi trùng side effect khi replay; lỗi outcome chưa xác định đã được hòa giải.
4. Node, thuộc tính, source version, delete và relationship khớp theo hợp đồng nghiệp vụ.
5. Kết quả đối soát tại điểm cắt là đạt hoặc có ngoại lệ được ghi nhận đầy đủ, không phải do dữ liệu hai bên đang ở hai thời điểm khác nhau.
6. Lag, DLQ, lỗi ghi và thời gian xử lý đã trở về ngưỡng vận hành; consumer tiếp tục tiến về các offset mới.
7. Có báo cáo nguyên nhân gốc, bằng chứng kiểm thử và phương án tránh tái diễn.

**Điểm cốt lõi:** khôi phục luồng đồng bộ không kết thúc khi consumer chạy lại. Với Neo4j, phải chứng minh **các node và quan hệ tạo thành một property graph đúng với nguồn tại một điểm cắt rõ ràng**, và mọi phần ghi có thể phát lại mà không nhân đôi hiệu ứng nghiệp vụ. Thiết kế checkpoint cùng ranh giới transaction, đối soát theo khóa/phiên bản/quan hệ, và xử lý sai lệch dựa trên nguyên nhân là ba nền tảng giúp hệ thống duy trì độ tin cậy khi có sự cố.
