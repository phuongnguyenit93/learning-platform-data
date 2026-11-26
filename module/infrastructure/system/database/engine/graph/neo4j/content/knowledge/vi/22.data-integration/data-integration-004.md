# Tính lũy đẳng, thứ tự sự kiện và xử lý sự kiện trùng

## 1. Bài toán tích hợp sự kiện với Neo4j

Một hệ thống quản lý bán hàng đẩy sự kiện sang dịch vụ cập nhật đồ thị Neo4j. Mỗi khi sản phẩm được bán, dịch vụ cần cập nhật bộ đếm trên node `Product`; khi đơn hàng đổi trạng thái, dịch vụ cần đồng bộ thuộc tính trên node `Order`; khi khách hàng được gán vai trò, dịch vụ có thể tạo hoặc sửa relationship.

Trong thực tế, một sự kiện có thể được gửi lại do timeout, consumer khởi động lại, broker phân phối lại hoặc ứng dụng chủ động retry. Đồng thời, các sự kiện của **cùng một thực thể** có thể đến sai thứ tự vì nhiều producer/worker, mạng hoặc quá trình replay.

Giả sử ba sự kiện của đơn `O100`:

| Sự kiện | Phiên bản đơn | Nội dung | Thời điểm tới consumer |
|---|---:|---|---|
| E-21 | 21 | `status = CREATED` | 09:00:03 |
| E-23 | 23 | `status = SHIPPED` | 09:00:04 |
| E-22 | 22 | `status = PAID` | 09:00:08 |

Nếu consumer cập nhật `Order.status` theo **thứ tự nhận** và không kiểm tra phiên bản, trạng thái cuối có thể thành **PAID** dù nguồn đã chuyển tới **SHIPPED**. Nếu broker gửi lại `E-22`, sự kiện trùng có thể tiếp tục làm hỏng projection.

Đối với sự kiện kiểu **cộng dồn**, nguy cơ còn rõ hơn: cùng sự kiện `OrderLineAdded` chứa `quantity = 2` được xử lý hai lần sẽ làm bộ đếm `soldUnits` tăng **4** thay vì **2**.

Ba vấn đề cần phân biệt:

- **Tính lũy đẳng (idempotency):** xử lý lại **cùng một thao tác logic** không nhân đôi tác dụng nghiệp vụ.
- **Thứ tự sự kiện (ordering):** một thực thể được cập nhật theo quy tắc phụ thuộc trước–sau của các phiên bản/sự kiện.
- **Sự kiện trùng (duplicate delivery):** một bản tin đã nhận và có thể đã commit được phân phối lại, hoặc cùng hành động được xuất bản nhiều lần.

Bài học thuộc chương **Tích hợp dữ liệu** trong Neo4j: trọng tâm là giữ đúng node, relationship, property và trạng thái projection khi đồng bộ từ message broker, CDC hoặc các dịch vụ Java. Những nguyên tắc này áp dụng cho Java Driver và Spring Data Neo4j; cách triển khai cụ thể còn phụ thuộc broker và phiên bản driver.

## 2. At-most-once, at-least-once và hiệu ứng xử lý đúng một lần

### 2.1. Vì sao sự kiện có thể đến nhiều lần?

Ví dụ một consumer nhận event, ghi thành công vào Neo4j, nhưng **crash trước khi xác nhận đã xử lý (ack)** với broker:

~~~text
Producer        Broker             Consumer             Neo4j
   |               |                   |                    |
   |--- E-100 ---->|                   |                    |
   |               |--- E-100 -------> |                    |
   |               |                   |--- commit -------> |
   |               |                   | <--- thành công ---|
   |               |                   X crash               |
   |               |                   |                    |
   |               |--- E-100 lại ---> |                    |
~~~

Broker không nhận ack nên có thể gửi lại E-100. Một transaction Neo4j thành công **không đồng nghĩa** broker đã biết điều đó.

| Cơ chế phân phối | Đặc tính chung | Trách nhiệm của consumer |
|---|---|---|
| At-most-once | Có thể mất sự kiện, nhưng hạn chế gửi lại | Chỉ phù hợp khi chấp nhận mất dữ liệu |
| At-least-once | Sự kiện thường không bị mất nếu có retry, nhưng có thể nhận lại | Xử lý lũy đẳng và ghi nhận tiến độ |
| Exactly-once trong một phạm vi cụ thể | Một nền tảng có thể bảo đảm theo giao dịch nội bộ của chính nó | Kiểm tra giới hạn phạm vi; không suy ra tác dụng phụ Neo4j tự đúng một lần |

Ngay cả khi broker hỗ trợ tính năng mang tên **exactly-once**, giao dịch của broker và transaction ghi Neo4j không tự nhiên trở thành **một giao dịch phân tán duy nhất**. Mục tiêu thực tế là **exactly-once effect** cho một thao tác có khóa định danh ổn định: mỗi event logic chỉ làm thay đổi graph **một lần**, dù consumer nhận lại nhiều lần.

### 2.2. Phải nói rõ “lũy đẳng” trên đối tượng nào

Hai cách xử lý có ý nghĩa khác nhau:

~~~cypher
// Gán một trạng thái tuyệt đối
MATCH (o:Order {orderId: $orderId})
SET o.status = 'PAID';
~~~

~~~cypher
// Cộng dồn một giá trị
MATCH (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

Nếu chạy **lặp lại ngay cùng trạng thái cơ sở dữ liệu**, phép gán `status = 'PAID'` thường không làm giá trị thay đổi thêm; phép cộng `soldUnits` thì làm thay đổi mỗi lần chạy.

Tuy nhiên, phép gán trạng thái **không an toàn trước sự kiện cũ tới muộn**: khi trạng thái đã là SHIPPED, xử lý lại sự kiện PAID sẽ đưa nó lùi về PAID. Vì thế, **lũy đẳng của một phép gán và tính đúng của chuỗi sự kiện là hai yêu cầu khác nhau**.

## 3. Thiết kế hợp đồng sự kiện có định danh và phiên bản

Ví dụ payload được phát hành từ dịch vụ đơn hàng:

~~~json
{
  "eventId": "orders-service:E-000123",
  "eventType": "OrderStatusChanged",
  "source": "orders-service",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "occurredAt": "2026-11-25T09:00:00Z",
  "payload": {
    "status": "SHIPPED"
  }
}
~~~

| Trường | Mục đích | Nguyên tắc |
|---|---|---|
| `eventId` | Nhận diện **một sự kiện logic** qua retry/replay | Ổn định giữa các lần gửi lại |
| `eventType` | Chọn cách ánh xạ vào graph | Có schema và validation cho từng loại |
| `source` | Xác định namespace và nguồn tin cậy | Dùng khi sự kiện đến từ nhiều hệ thống |
| `schemaVersion` | Chọn bộ giải mã payload | Không đánh đồng với version của Order |
| `aggregateId` | Xác định node/luồng thứ tự cần bảo vệ | Không lấy ID nội bộ Neo4j làm khóa ngoại |
| `aggregateVersion` | Xác định thứ tự thay đổi **của một aggregate** | Tăng theo quy tắc của producer |
| `occurredAt` | Thông tin thời gian sự kiện | Không thay thế version để phân xử thứ tự |
| `payload` | Dữ liệu nghiệp vụ được áp dụng | Phân biệt snapshot với delta |

**Hai kiểu version không nên nhầm lẫn:** `schemaVersion` nói về **định dạng bản tin**, còn `aggregateVersion` nói về **thứ tự thay đổi của thực thể**.

### 3.1. Event ID ổn định qua retry

Nếu producer tạo một UUID **mới mỗi lần gửi lại cùng thao tác**, consumer sẽ coi các bản tin đó là **những event khác nhau**. Mọi kỹ thuật chống trùng dựa vào eventId đều mất tác dụng.

Cần chọn ID ngay lúc tạo sự kiện logic, lưu nó bền vững, rồi giữ nguyên khi retry. Với mô hình outbox, cùng một hàng outbox nên mang cùng eventId trong mọi lần được publisher gửi lại.

### 3.2. ID chỉ duy nhất trong phạm vi nào?

Hai hệ thống độc lập có thể cùng tạo eventId là `123`. Có thể dùng khóa đầy đủ:

~~~text
eventKey = source + ":" + eventId
~~~

Ví dụ `crm:123` và `orders:123` là hai sự kiện khác nhau.

Nếu hệ thống nhiều tenant, namespace còn có thể cần `tenantId`. **Phạm vi duy nhất của eventKey phải khớp đúng hợp đồng tạo ID**; không mặc định một mã ngắn là duy nhất toàn cầu.

### 3.3. Payload hash phát hiện xung đột ID

Cùng một `eventKey` nhưng nội dung khác nhau có thể là lỗi producer, hỏng dữ liệu hoặc thay đổi semantics của event. Lưu thêm một **payloadHash** được tính từ biểu diễn payload chuẩn hóa phù hợp giúp phân biệt:

- **Cùng eventKey, cùng payloadHash:** thường là bản tin gửi lại.
- **Cùng eventKey, payloadHash khác:** xung đột cần cảnh báo và điều tra, không tự coi là duplicate an toàn.

Cần thống nhất cách canonicalize: thứ tự key JSON, kiểu số, mã hóa và phiên bản schema đều có thể ảnh hưởng digest. Trong hệ thống nghiêm ngặt, so sánh trực tiếp các trường nghiệp vụ quan trọng cũng có thể cần thiết.

## 4. Thiết kế mô hình graph và sổ ghi sự kiện đã áp dụng

Có hai nhóm node phục vụ mục đích khác nhau:

~~~text
(:Product {sku, soldUnits})
(:AppliedEvent {eventKey, source, eventId, payloadHash, appliedAt})
~~~

Có thể thêm relationship để truy vết:

~~~text
(:AppliedEvent)-[:APPLIED_TO]->(:Product)
~~~

Node `Product` lưu trạng thái nghiệp vụ; `AppliedEvent` là **receipt/ledger** ghi rằng một event đã tạo tác dụng đối với projection Neo4j. Sổ ghi này có thể ở cùng database Neo4j hoặc trong một hệ thống có cơ chế giao dịch phù hợp; ví dụ bài dùng **cùng transaction Neo4j**.

Thiết lập uniqueness constraint cho khóa nghiệp vụ và eventKey:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT applied_event_key_unique IF NOT EXISTS
FOR (e:AppliedEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

Hai constraint có nhiệm vụ khác nhau:

- `Product.sku` ngăn tạo hai node Product cùng SKU.
- `AppliedEvent.eventKey` ngăn **hai transaction cùng commit hai receipt cho một eventKey**.

Tạo schema trước khi xử lý sự kiện đồng thời. Nếu dữ liệu đã trùng khóa, tạo constraint có thể thất bại và cần xử lý dữ liệu trước. Uniqueness constraint không tự đảm bảo property khóa luôn hiện diện, nên input phải được kiểm tra.

### 4.1. Nhược điểm của việc chỉ dùng MERGE

~~~cypher
MERGE (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

Câu trên có thể tránh tạo Product trùng **khi có constraint phù hợp**, nhưng không ngăn **cùng event tăng soldUnits lần thứ hai**. MERGE tìm hoặc tạo **node Product**, không ghi nhận event nào đã cộng số lượng.

Tương tự, chỉ thêm:

~~~cypher
MERGE (e:AppliedEvent {eventKey: $eventKey})
WITH e
MATCH (p:Product {sku: $sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity;
~~~

vẫn sai: dù MERGE tìm thấy receipt cũ, pipeline vẫn thực hiện SET. **MERGE receipt không tự đồng nghĩa “chỉ chạy các bước sau ON CREATE”.**

## 5. Mẫu xử lý delta bằng receipt và constraint trong một transaction

Giả sử event `ProductUnitsSold` chứa `sku` và `quantity` nguyên dương. Node Product đã tồn tại; mỗi event phải tăng `soldUnits` đúng một lần.

~~~cypher
MATCH (p:Product {sku: $sku})
CREATE (e:AppliedEvent {
    eventKey: $eventKey,
    source: $source,
    eventId: $eventId,
    payloadHash: $payloadHash,
    appliedAt: datetime()
})
SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity
CREATE (e)-[:APPLIED_TO]->(p)
RETURN p.sku AS sku, p.soldUnits AS soldUnits;
~~~

Câu truy vấn có ba đặc tính quan trọng:

1. **MATCH Product** trước; nếu không tìm được SKU, không có hàng để đi tiếp đến CREATE receipt. Ứng dụng phải phát hiện kết quả 0 hàng và xử lý dữ liệu thiếu.
2. **CREATE AppliedEvent** cố tạo receipt mới, được bảo vệ bởi uniqueness constraint `AppliedEvent.eventKey`. Receipt, relationship truy vết và thay đổi `soldUnits` nằm trong **cùng một transaction**.
3. Với một eventKey đã commit, lần CREATE tiếp theo vi phạm uniqueness constraint. Transaction thất bại và **không commit thêm lần cộng**. Ứng dụng kiểm tra receipt hiện có rồi phân loại thành duplicate hay xung đột.

**Phạm vi bảo đảm:** mẫu trên phù hợp nếu mọi worker ghi `soldUnits` theo sự kiện đều đi qua cùng cơ chế receipt/constraint và dùng eventKey ổn định. Không có bảo đảm cho worker khác bỏ qua quy tắc rồi tự cộng lại.

### 5.1. Vì sao dùng CREATE receipt thay vì MERGE trong ví dụ?

`CREATE` buộc transaction phải chứng minh eventKey **chưa được dùng** bằng uniqueness constraint. Nếu khóa đã tồn tại, câu ghi gặp lỗi và rollback. Đây là cách tạo **cổng chống trùng** rõ ràng.

Nếu chọn `MERGE` receipt thay vì CREATE, cần một cách xác định chắc chắn receipt vừa được tạo trong transaction này để **chỉ thực hiện tác dụng nghiệp vụ ở nhánh tạo**. Không được đơn giản đặt SET cộng dồn sau MERGE rồi cho rằng tự lũy đẳng.

### 5.2. Hai worker cùng nhận một event

~~~text
Consumer A              Neo4j                Consumer B
    |                       |                      |
    |-- CREATE E-100 ------>|<------ CREATE E-100--|
    |                       |                      |
    |     một transaction commit                   |
    |     transaction còn lại không thể commit    |
    |     receipt trùng eventKey                   |
~~~

Tùy timing và cơ chế giao dịch, một worker có thể phải chờ hoặc nhận lỗi liên quan đến constraint/transaction. **Bất biến** quan trọng là constraint không cho phép **hai receipt cùng eventKey được commit**. Khi receipt và cập nhật business nằm trong cùng transaction, event trùng không thể được áp dụng hai lần bởi mẫu xử lý này.

Nếu đã nhận lỗi, **không mặc định mọi lỗi constraint đều là duplicate**. Constraint khác có thể bị vi phạm. Cần xác minh mã lỗi, eventKey và payload của receipt đã commit.

### 5.3. Xử lý kết quả transaction

| Kết quả | Ý nghĩa và xử lý |
|---|---|
| Có một hàng RETURN, transaction commit thành công | Event đã được áp dụng; có thể ack broker |
| Không tìm thấy Product | Không có hàng để xử lý; báo lỗi dữ liệu hoặc chờ thực thể xuất hiện theo quy tắc |
| EventKey vi phạm uniqueness và receipt có cùng payloadHash | Event đã áp dụng trước đó; không cộng lại, có thể coi lần giao nhận này đã hoàn tất |
| EventKey trùng nhưng payloadHash khác | Xung đột producer/dữ liệu; cảnh báo, không ack như thành công bình thường nếu chưa giải quyết |
| Lỗi transient/deadlock | Retry **toàn bộ transaction** theo giới hạn, có backoff |
| Trạng thái commit không chắc do mất kết nối | Đọc lại receipt qua phiên/giao dịch mới trước khi quyết định chạy lại |

Cần phân biệt **“DB commit thành công”** với **“client có nhận được phản hồi thành công”**. Mất kết nối sau commit có thể làm client không biết kết quả; receipt chính là bằng chứng để tra lại.

## 6. Các cách xử lý idempotent khác

Mẫu receipt là giải pháp tổng quát cho event delta cần giữ chính xác số lần áp dụng. Tùy loại dữ liệu, có những kỹ thuật bổ sung.

| Cách | Tình huống thích hợp | Giới hạn |
|---|---|---|
| `MERGE` node theo khóa ổn định | Tạo/cập nhật thực thể có định danh | Không tự chống cộng delta hai lần |
| `MERGE` relationship giữa hai node đã định danh | Tạo liên kết tồn tại theo nghiệp vụ | Cần xét cạnh tranh và bất biến duy nhất relationship |
| Receipt với eventKey và uniqueness constraint | Mỗi event phải tác động đúng một lần | Tốn lưu trữ, cần chính sách retention |
| Gán snapshot tuyệt đối có kiểm tra version | Đồng bộ trạng thái mới nhất | Không xử lý được thứ tự sai chỉ bằng SET |
| Idempotency key theo **lệnh nghiệp vụ** | Producer có thể tạo nhiều event khác ID cho cùng một hành động | Cần hợp đồng operationId rõ ràng |
| Serialization theo khóa aggregate | Ngăn hai worker cùng xử lý lịch sử một thực thể | Cần quản lý phân phối lại, timeout, replay |

### 6.1. Trùng bản tin và trùng thao tác nghiệp vụ không giống nhau

Giả sử một lệnh “tạo đơn hàng” được client gửi hai lần vì timeout. Producer có thể tạo **hai eventId khác nhau** dù đây chỉ là **một yêu cầu người dùng**. Receipt theo eventId sẽ coi đó là hai sự kiện hợp lệ.

Nếu nghiệp vụ muốn tạo đúng một đơn cho một lần bấm “Đặt hàng”, API/producer còn cần **operationId** hoặc **requestId** ổn định qua các lần retry của yêu cầu. ID này có thể trở thành khóa duy nhất của thực thể hoặc một ledger ở tầng producer. Consumer chống duplicate delivery không thể tự suy ra hai eventId khác nhau là cùng một hành động.

## 7. Thứ tự sự kiện: event đến muộn và phiên bản aggregate

### 7.1. Dùng version theo một thực thể, không dùng thời điểm nhận

Ví dụ Order O100 có chuỗi:

~~~text
version=21  CREATED
version=22  PAID
version=23  SHIPPED
~~~

Trạng thái hiện tại của projection có thể lưu:

~~~text
(:Order {
  orderId: 'O100',
  status: 'SHIPPED',
  lastAppliedVersion: 23
})
~~~

Consumer nhận lại event **version=22** không nên thay trạng thái từ SHIPPED về PAID. Cần kiểm tra phiên bản tại lúc áp dụng.

Một bản tin có `occurredAt` muộn hơn bản khác **không luôn có nghĩa** là phiên bản logic mới hơn: đồng hồ máy chủ có thể lệch, network delay và producer khác nhau. `aggregateVersion` hoặc sequence do nguồn có thẩm quyền cấp thường đáng tin hơn để xác định thứ tự **trong phạm vi aggregate**.

### 7.2. Hai loại sự kiện, hai chính sách thứ tự

**Sự kiện snapshot/trạng thái đầy đủ:**

~~~json
{
  "eventId": "E-23",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "payload": {
    "status": "SHIPPED",
    "totalInCents": 360000,
    "currency": "VND"
  }
}
~~~

Snapshot đầy đủ có thể cho phép **lấy phiên bản cao hơn** và bỏ các snapshot cũ, nếu producer bảo đảm snapshot phiên bản N chứa đủ toàn bộ trạng thái cần thiết và không cần thực hiện những side effect của các phiên bản bị bỏ qua.

**Sự kiện delta:**

~~~json
{
  "eventId": "E-23",
  "aggregateId": "O100",
  "aggregateVersion": 23,
  "payload": {
    "addedAmountInCents": 120000
  }
}
~~~

Delta chỉ mô tả **một thay đổi**. Nếu bỏ version=22 rồi áp dụng version=23, projection có thể thiếu một phần tổng. Với delta yêu cầu xử lý đủ thứ tự, không thể đơn giản giữ phiên bản lớn nhất.

**Quy tắc quan trọng:** “version mới hơn” không đủ để quyết định có thể bỏ qua các bản tin giữa chừng. Quyết định phải dựa trên semantics **snapshot đầy đủ** hay **delta phụ thuộc lịch sử**.

### 7.3. Bảng quyết định theo version

Giả sử projection của một aggregate có `lastAppliedVersion = 21` và producer cấp version **liên tiếp** cho mọi sự kiện mà projection cần.

| Event mới | Tình trạng | Xử lý cho delta tuần tự |
|---|---|---|
| `version = 22` | Đúng kế tiếp | Kiểm tra receipt, áp dụng và tăng checkpoint đến 22 |
| `version = 21` | Cũ hoặc gửi lại | Không áp dụng delta; kiểm tra eventId/payload |
| `version = 20` | Rất cũ | Bỏ qua có kiểm soát hoặc đối chiếu lịch sử |
| `version = 23` | Hở version 22 | Giữ pending, tìm/replay version 22; không cộng trước |
| `version = 22` nhưng eventId khác bản ghi đã có | Xung đột phiên bản | Điều tra, không áp dụng tùy tiện |

Bảng trên **chỉ đúng** khi sequence của nguồn liên tiếp cho loại dữ liệu projection đang tiêu thụ. Nếu producer có những loại event khác nhau cùng chia một bộ đếm nhưng consumer chỉ quan tâm một phần event, cần một chính sách checkpoint khác; không giả định cứ thiếu một số nguyên là mất bản tin.

### 7.4. Thứ tự trong broker không tự bảo đảm thứ tự commit vào Neo4j

Nếu broker có partition theo aggregate key, các bản tin của một key có thể được phát trong cùng partition theo thứ tự. Nhưng:

- Consumer có thể xử lý song song nhiều record trong cùng partition.
- Một record thất bại và bị retry muộn, record sau lại được commit trước.
- Rebalance hoặc nhiều pipeline cùng ghi có thể tạo các lịch xen kẽ khác nhau.
- Dữ liệu nhập bù/replay có thể bỏ qua luồng broker thông thường.

Vì vậy, **khóa aggregate để phân phối** là một biện pháp giảm khả năng sai thứ tự, còn việc kiểm tra version và giao dịch ghi ở đích vẫn cần được thiết kế.

## 8. Giữ trạng thái xử lý theo aggregate

Một cách biểu diễn checkpoint:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
MATCH (o:Order {orderId: $orderId})
RETURN o.lastAppliedVersion AS lastAppliedVersion,
       o.status AS currentStatus;
~~~

Khi tiếp nhận một sự kiện, handler cần quyết định liệu nó có thể áp dụng. Về mặt logic:

~~~text
nhận event E
  |
  v
kiểm tra schema, khóa, version, payload
  |
  +-- eventKey đã áp dụng --> so payload --> duplicate hoặc conflict
  |
  +-- version < phiên bản hiện tại --> stale --> bỏ qua có kiểm soát
  |
  +-- version = kế tiếp --> áp dụng + receipt + checkpoint cùng giao dịch
  |
  +-- version vượt kế tiếp --> pending/replay khoảng thiếu
~~~

**Lưu ý concurrency:** đọc `lastAppliedVersion`, so sánh trong Java, rồi chạy một câu SET khác **không tự tạo phép compare-and-swap nguyên tử**. Hai worker có thể cùng đọc version cũ và cùng cho rằng event của mình hợp lệ.

Đối với pipeline bắt buộc version tuần tự, cần kết hợp **serialization theo aggregate** và cơ chế khóa/điều phối trong Neo4j, hoặc một quy trình cập nhật có điều kiện đã kiểm chứng dưới cạnh tranh. Việc chỉ viết `MATCH ... WHERE o.lastAppliedVersion = $expectedVersion SET ...` không nên mặc nhiên được coi là đủ bảo đảm trong mọi lịch đồng thời: điều kiện có thể được đánh giá trước khi transaction thu được khóa ghi cần thiết.

Khi triển khai điều phối bằng khóa ghi, cần đảm bảo **đọc lại trạng thái sau khi khóa được lấy**, rồi đưa cập nhật trạng thái, receipt và checkpoint vào **cùng transaction**. Chi tiết khóa tự động và hành vi câu Cypher phụ thuộc phiên bản Neo4j, vì vậy cần kiểm thử concurrency thực tế cho phiên bản đang vận hành.

### 8.1. Đừng để checkpoint đi trước dữ liệu

Một thiết kế lỗi:

~~~text
1. ghi lastAppliedVersion = 23
2. commit
3. cập nhật Order.status = SHIPPED
4. commit
~~~

Nếu chương trình crash giữa bước 2 và 3, lần retry thấy checkpoint 23 và có thể bỏ qua event, trong khi trạng thái chưa cập nhật.

Cần commit **receipt + cập nhật nghiệp vụ + lastAppliedVersion** như một **đơn vị giao dịch nguyên tử**. Nếu cùng một giao dịch rollback, không phần nào trong ba thao tác đó được coi là đã áp dụng.

### 8.2. Một event cập nhật nhiều node và relationship

Ví dụ `OrderConfirmed` cần cập nhật node Order và tạo relationship `(Customer)-[:PLACED]->(Order)`. Nếu event yêu cầu bất biến tất cả hoặc không có gì:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
CREATE (e:AppliedEvent {
    eventKey: $eventKey,
    payloadHash: $payloadHash,
    appliedAt: datetime()
})
SET o.status = 'CONFIRMED'
MERGE (c)-[:PLACED]->(o)
CREATE (e)-[:APPLIED_TO]->(o)
RETURN o.orderId AS orderId;
~~~

Constraint trên `AppliedEvent.eventKey` giúp chặn xử lý lặp event; các thay đổi graph nằm cùng transaction. Ví dụ giả định các node đầu mút đã tồn tại và pipeline có chính sách version phù hợp. **MERGE** relationship mô tả liên kết, nhưng uniqueness constraint trên Customer/Order **không tự đảm bảo bất biến một relationship duy nhất cho một cặp đầu mút** trong mọi kịch bản ghi đồng thời không phối hợp.

## 9. Xử lý sự kiện sai thứ tự theo nghiệp vụ

### 9.1. Chờ bản tin còn thiếu (reorder buffer)

Với delta liên tiếp, khi đang ở version 21 nhưng nhận version 23:

1. Lưu event 23 vào **pending inbox** hoặc nơi lưu bền vững phù hợp.
2. Tìm event 22 từ broker/replay/source.
3. Áp dụng event 22 và 23 theo thứ tự.
4. Xóa dấu pending khi trạng thái đích và checkpoint đã được xác nhận.

Không nên chỉ giữ event 23 trong RAM nếu crash sẽ khiến mất khả năng xử lý tiếp. Pending cần có cơ chế retention, retry và cảnh báo khi khoảng thiếu kéo dài.

### 9.2. Snapshot mới nhất có thể phục hồi khoảng thiếu

Nếu sự kiện là **full snapshot** chứa toàn bộ trạng thái, projection có thể cập nhật từ version 21 lên version 23 mà không áp dụng version 22, khi các yêu cầu sau đều đúng:

- Source xác nhận snapshot 23 là trạng thái hợp lệ đầy đủ.
- Không có tác dụng phụ cần được thực hiện riêng từ version 22.
- Cập nhật version được điều phối để event 22 không ghi đè sau đó.
- Quy trình audit/reconciliation cho phép bỏ qua thay đổi trung gian.

Cách này không áp dụng tùy tiện cho tiền, tồn kho dạng delta, đếm event hoặc các quá trình cần lưu toàn bộ lịch sử.

### 9.3. Nhiều nguồn có xung đột

Nếu CRM và hệ thống bán hàng cùng cập nhật `Customer.name`, mỗi nguồn có thể đánh version riêng. Không thể so trực tiếp `CRM version 12` với `Sales version 40` rồi coi 40 mới hơn về nghiệp vụ.

Cần quy định:

- Nguồn nào có **quyền sở hữu** từng property?
- Có phải tách `crmName` và `displayName` để giữ hai góc nhìn?
- Chỉ source có thẩm quyền mới được sửa trạng thái chung?
- Khi cần hợp nhất, dùng ưu tiên nguồn, vector/version theo nguồn hoặc logic nghiệp vụ cụ thể?

`occurredAt` cũng không tự giải quyết tranh chấp đa nguồn. Chọn nguồn có thẩm quyền thường dễ kiểm chứng hơn quy tắc “timestamp lớn nhất thắng” khi đồng hồ phân tán.

## 10. Sự kiện trùng trong LOAD CSV, JSON và CDC

### 10.1. Nhập theo lô bằng UNWIND

Một batch JSON có thể chứa nhiều bản tin, trong đó một `eventKey` xuất hiện lặp lại. Câu lệnh:

~~~cypher
UNWIND $events AS ev
MATCH (p:Product {sku: ev.sku})
SET p.soldUnits = coalesce(p.soldUnits, 0) + ev.quantity;
~~~

**không lũy đẳng**. Nếu một event xuất hiện hai lần trong mảng hoặc cả batch được retry, số lượng bị cộng lại.

Mỗi event phải được kiểm tra định danh và receipt; có thể xử lý từng event trong transaction riêng hoặc thiết kế lô có cổng chống trùng rõ ràng. Nếu dùng `CREATE AppliedEvent` với uniqueness constraint trong **một transaction chứa nhiều event**, chỉ một event trùng có thể làm **rollback cả lô**. Đây là trade-off cần lựa chọn dựa trên mục tiêu thông lượng và mức cô lập lỗi.

### 10.2. CDC và thứ tự từ nguồn quan hệ

Trong Change Data Capture (CDC), metadata có thể gồm:

- ID của record thay đổi hoặc vị trí log nguồn.
- Tên bảng và khóa hàng.
- Thao tác INSERT/UPDATE/DELETE.
- Offset, LSN hoặc tọa độ log tương ứng với hệ thống nguồn.
- Thời điểm thay đổi và dữ liệu trước/sau.

Một **offset** hoặc vị trí log có thể giúp resume/replay; **eventKey** có thể được xây từ khóa bản ghi CDC ổn định và namespace phù hợp. Không mặc định chỉ offset số học là duy nhất trên mọi partition, mọi database hoặc mọi thời gian; phải dựa trên hợp đồng connector.

Đối với thay đổi trạng thái, payload `after` có thể đóng vai trò snapshot của một hàng. Nhưng ghép trạng thái từ nhiều bảng/aggregate vẫn có thể cần nhiều event và ràng buộc thứ tự; snapshot của **một hàng SQL** không nhất thiết là snapshot đầy đủ của **toàn graph projection**.

### 10.3. Import theo lịch có thể phát lại bản ghi

Với CSV snapshot được nạp mỗi đêm, `MERGE` node theo khóa giúp tránh tạo lại node, nhưng các quan hệ hoặc số liệu cộng dồn phải được xử lý có chủ đích. Chẳng hạn, tổng doanh thu nên được **tính lại từ các bản ghi nguồn được định danh**, hoặc ghi bằng snapshot có version; không cộng toàn bộ tổng trong CSV vào cùng node mỗi đêm nếu đó là bản tổng lặp lại.

Một nguồn quan hệ hoặc CSV không có event ID cần thiết kế **idempotency key** theo thao tác hợp lý (ví dụ mã dòng giao dịch + loại sự kiện + phiên bản), đồng thời xác định “một lần phát lại dữ liệu” có phải cùng sự kiện logic hay không.

## 11. Java Driver: đặt receipt và cập nhật trong managed transaction

Ví dụ Java dưới đây thực thi sự kiện cộng `quantity` vào Product bằng **một câu Cypher trong managed write transaction**. Nó giả định schema có hai uniqueness constraint từ mục 4 và input đã được kiểm tra.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ProductEventWriter {
    private final Driver driver;

    public ProductEventWriter(Driver driver) {
        this.driver = driver;
    }

    public long applySoldUnits(
            String eventKey, String source, String eventId,
            String payloadHash, String sku, long quantity) {

        if (eventKey == null || eventKey.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid event input");
        }

        String cypher = """
            MATCH (p:Product {sku: $sku})
            CREATE (e:AppliedEvent {
                eventKey: $eventKey,
                source: $source,
                eventId: $eventId,
                payloadHash: $payloadHash,
                appliedAt: datetime()
            })
            SET p.soldUnits = coalesce(p.soldUnits, 0) + $quantity
            RETURN p.soldUnits AS soldUnits
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var result = tx.run(cypher, Map.of(
                    "eventKey", eventKey,
                    "source", source,
                    "eventId", eventId,
                    "payloadHash", payloadHash,
                    "sku", sku,
                    "quantity", quantity
                ));
                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Product was not found: " + sku
                    );
                }
                return result.single().get("soldUnits").asLong();
            });
        }
    }
}
~~~

Đoạn code chỉ minh họa **nhánh áp dụng mới**. Khi event đã được xử lý trước đó, uniqueness constraint có thể gây lỗi ghi; tầng gọi cần bắt **đúng loại lỗi phù hợp**, mở transaction/read session mới để tìm receipt và so `payloadHash`. Nếu cùng khóa/cùng payload, trả kết quả “đã xử lý” cho broker mà không tăng `soldUnits` lần nữa. Nếu cùng khóa khác payload, báo xung đột.

Không được bắt mọi exception rồi coi là duplicate: lỗi mạng, timeout, khóa, schema hoặc dữ liệu sai đều đòi hỏi xử lý khác nhau. Mã lỗi exception và nhóm lỗi được driver tự retry cần được kiểm tra theo phiên bản Neo4j/Java Driver đang dùng.

### 11.1. Vì sao callback cần an toàn khi retry?

`session.executeWrite(...)` có thể chạy lại callback khi gặp lỗi transient được driver xác định có thể retry. Nếu callback chỉ chạy các câu ghi Neo4j có tính lũy đẳng phù hợp, việc retry dễ kiểm soát hơn.

**Không gửi email, gọi thanh toán hoặc publish thêm event có tác dụng phụ bên ngoài Neo4j trong callback** nếu chưa có idempotency/outbox. Callback có thể bị gọi lại; transaction Neo4j rollback không hoàn tác thao tác HTTP đã gửi thành công.

### 11.2. Ack broker sau khi đã biết kết quả database

Luồng xử lý an toàn về ý nghĩa:

~~~text
Nhận event từ broker
    |
Kiểm tra schema, ID, version
    |
Bắt đầu managed transaction Neo4j
    |
Tạo receipt / cập nhật graph / checkpoint
    |
Commit thành công?
    |-- Có --> ack/commit vị trí broker
    |
    |-- Chưa rõ --> tra receipt; có thể retry
    |
    |-- Lỗi rõ ràng --> phân loại retry / pending / conflict / DLQ
~~~

Nếu ack **trước khi commit Neo4j**, consumer có thể crash sau ack và mất tác dụng cập nhật. Nếu commit Neo4j trước ack rồi crash, broker có thể gửi lại, nhưng receipt giúp nhận diện và không áp dụng lần hai.

Đây là cơ chế phối hợp ở cấp ứng dụng; không tự biến Neo4j và broker thành một transaction phân tán.

### 11.3. Với Spring Data Neo4j

Trong ứng dụng Spring, một service có thể dùng `@Transactional` để gom cập nhật graph và receipt trong cùng transaction Neo4j theo cách cấu hình transaction manager phù hợp. Repository `save(...)` hoặc `Neo4jClient` không tự chống event trùng nếu thiếu event ID/receipt và constraint.

Khi dùng cả SQL, broker và Neo4j, cần phân biệt rõ transaction manager nào quản lý tài nguyên nào. Không mặc định một annotation `@Transactional` duy nhất bảo đảm atomic commit xuyên qua nhiều hệ thống độc lập.

## 12. Retry, sự kiện độc và dead-letter queue

Hãy phân loại trước khi quyết định có retry hay không.

| Nhóm | Ví dụ | Xử lý gợi ý |
|---|---|---|
| Retryable/transient | Khóa tranh chấp, deadlock, service tạm thời quá tải | Retry có giới hạn, backoff, theo dõi số lần |
| Duplicate đã xác nhận | Receipt cùng eventKey và payloadHash | Ack mà không áp dụng lại |
| Xung đột dữ liệu | EventKey trùng nhưng payload khác, version xung đột | Cách ly, cảnh báo, điều tra |
| Sai schema/thiếu khóa | Không có aggregateId, quantity không hợp lệ | Quarantine/DLQ, không retry vô hạn |
| Thiếu phụ thuộc | Relationship tham chiếu Product chưa được tạo | Pending theo chính sách hoặc truy vấn nguồn để phục hồi |
| Hở version | Nhận event 23 trước 22 | Buffer/replay 22 theo thời hạn |
| Mất xác nhận commit | Timeout sau khi DB có thể đã commit | Đọc receipt rồi quyết định |
| Lỗi nghiệp vụ bền vững | Sự kiện trái quy tắc chuyển trạng thái | Báo lỗi dữ liệu, không retry mù |

**Retry có giới hạn** giúp tránh một bản tin lỗi chiếm toàn bộ worker. Khi đưa sự kiện vào DLQ, cần lưu đủ metadata để phân tích và replay an toàn: eventKey, aggregateId, version, thông tin nguồn, loại lỗi, số lần thử và payload theo quy định bảo mật.

Không nên xử lý DLQ bằng cách xóa receipt hoặc reset version tùy tiện. Việc replay phải tuân thủ cùng khóa, constraint và quy tắc thứ tự như luồng bình thường.

## 13. Retention của receipt và chi phí lưu trữ

Mỗi event được áp dụng tạo một node `AppliedEvent` có thể khiến số lượng node tăng nhanh. Cần quyết định **giữ receipt bao lâu**, dựa trên khoảng thời gian broker có thể replay và yêu cầu kiểm toán.

Ví dụ, xóa receipt sau 7 ngày nhưng một job backfill gửi lại event của 30 ngày trước sẽ khiến hệ thống không còn bằng chứng event đã áp dụng. Nếu event là delta, nó có thể được áp dụng lần thứ hai.

Có thể chọn:

- Giữ receipt đủ dài cho **toàn bộ khoảng replay hợp lệ**, có tính cả backfill.
- Dùng checkpoint/version được bảo vệ cùng logic nghiệp vụ khi có thể ngăn replay cũ.
- Lưu receipt dài hạn ở lớp dữ liệu khác nhưng có khả năng tra cứu nhất quán theo eventKey.
- Dùng quy tắc import/rebuild projection từ đầu với namespace hoặc database riêng, không lẫn với trạng thái đã ứng dụng.

Không tự động xóa sổ receipt chỉ vì dữ liệu cũ ít được truy cập. Chi phí node, index và relationship cần được đưa vào thiết kế tải và retention.

## 14. Quan sát và truy vấn kiểm chứng trong Neo4j

### 14.1. Kiểm tra receipt đã được lưu

~~~cypher
MATCH (e:AppliedEvent {eventKey: $eventKey})
RETURN e.eventKey AS eventKey,
       e.eventId AS eventId,
       e.source AS source,
       e.payloadHash AS payloadHash,
       e.appliedAt AS appliedAt;
~~~

Dữ liệu trả về giúp phân biệt event trùng với lỗi xung đột ID. Ứng dụng nên dùng tham số thay vì ghép chuỗi từ event đầu vào.

### 14.2. Đếm receipt theo ID

~~~cypher
MATCH (e:AppliedEvent {eventKey: $eventKey})
RETURN count(e) AS receiptCount;
~~~

Khi constraint đúng và receipt tồn tại, `receiptCount = 1`; bằng 0 nghĩa là chưa có receipt cho key đó trong database đang kiểm tra. Nếu không có constraint, nhiều receipt trùng có thể xuất hiện và làm cơ chế chống lặp mất hiệu lực.

### 14.3. Tìm một số node Order chưa có checkpoint

~~~cypher
MATCH (o:Order)
WHERE o.lastAppliedVersion IS NULL
RETURN o.orderId AS orderId,
       o.status AS status
LIMIT 50;
~~~

Đây là kiểm tra hỗ trợ migration/giám sát. Sự vắng mặt của version có thể hợp lệ với Order chưa từng được đồng bộ qua event; cần hiểu cách projection được khởi tạo trước khi gắn nhãn dữ liệu lỗi.

### 14.4. Truy ngược node đã nhận event

Nếu lưu `APPLIED_TO`:

~~~cypher
MATCH (e:AppliedEvent)-[:APPLIED_TO]->(p:Product {sku: $sku})
RETURN e.eventKey AS eventKey,
       e.appliedAt AS appliedAt
ORDER BY appliedAt DESC
LIMIT 20;
~~~

Truy vấn này phù hợp với audit khi mô hình lưu relationship. Trong pipeline tốc độ rất cao, relationship audit cũng tăng write load; cân nhắc ích lợi truy vết so với dung lượng và chi phí cập nhật graph.

### 14.5. Các chỉ số vận hành nên theo dõi

| Chỉ số | Giúp phát hiện |
|---|---|
| Số event nhận và số event áp dụng mới | Chênh lệch bất thường hoặc nhiều lỗi |
| Duplicate rate theo source/aggregate | Producer retry nhiều, broker redelivery |
| Conflicting eventKey rate | Nguồn phát ID không ổn định hoặc dữ liệu lỗi |
| Out-of-order/gap count | Pipeline không giữ thứ tự, thiếu bản tin |
| Tuổi pending event lâu nhất | Một aggregate bị kẹt vì thiếu version |
| Retry, deadlock, transaction timeout | Tranh chấp ghi và tải Neo4j |
| Consumer lag, DLQ depth | Tồn đọng sự kiện chưa xử lý |
| Số receipt và kích thước index | Chi phí retention/sổ ghi sự kiện |
| Chênh lệch projection so với source | Lỗi logic không thể phát hiện chỉ bằng số retry |

Theo dõi cả **độ đúng** và **thông lượng**. Một pipeline trả lời nhanh nhưng bỏ qua version thiếu có thể gây sai dữ liệu lâu dài.

## 15. Thử nghiệm đồng thời và khôi phục sau lỗi

Nên chạy các tình huống sau trên **database thử nghiệm có dữ liệu cô lập**, dùng cùng schema/constraint như môi trường vận hành.

| Kịch bản | Tác động thử nghiệm | Kỳ vọng |
|---|---|---|
| Gửi một event một lần | E100 tăng 2 đơn vị | `soldUnits` tăng 2, có 1 receipt |
| Gửi lại cùng eventKey/payload | E100 gửi lần thứ hai | Không tăng thêm; phân loại duplicate |
| Hai worker cùng xử lý E100 | Cạnh tranh tạo cùng receipt | Chỉ một lần tác động commit |
| Cùng key nhưng payload đổi | E100 tăng 3 thay vì 2 | Phát hiện conflict, không cộng 3 |
| Mất kết nối ngay sau commit | Client không nhận phản hồi | Tra receipt để biết event đã áp dụng |
| Event snapshot v23 trước v22 | SHIPPED đến trước PAID | Không để v22 ghi đè trạng thái mới |
| Event delta v23 trước v22 | Thiếu delta v22 | Đưa v23 pending hoặc replay v22 |
| Crash sau DB commit, trước broker ack | Broker redeliver | Receipt chặn xử lý lại |
| Crash trước DB commit | Transaction rollback | Retry có thể áp dụng đúng một lần |
| Thiếu node đầu mút | Event tham chiếu SKU lạ | Không ghi receipt áp dụng giả; xử lý thiếu phụ thuộc |
| Replay sau khi hết hạn receipt | Bản tin cũ quay lại | Tuân thủ retention/version policy; không nhân đôi tác dụng |
| Hai nguồn khác nhau cùng sửa property | CRM/Sales có version khác nhau | Quy tắc quyền sở hữu nguồn được áp dụng |

### 15.1. Thử với bộ đếm có thể đối chiếu

Trên dữ liệu thử, chuẩn bị Product có `soldUnits = 0` và một tập gồm 100 event khác nhau, mỗi event tăng 1. Trộn ngẫu nhiên nhiều lần gửi, chia cho nhiều worker, mô phỏng retry và crash.

Nếu **100 event hợp lệ khác nhau đều được commit đúng một lần**, số cuối kỳ vọng là **100**, dù tổng số lần broker giao có thể lớn hơn 100. Đếm receipt theo tập eventKey phải tương ứng 100.

Để xác nhận tính đúng, không chỉ kiểm tra tổng: **hai lỗi cộng thừa và bỏ sót có thể triệt tiêu nhau**. Cần đối chiếu từng eventKey, số lần áp dụng và bất biến phiên bản.

### 15.2. Tránh đụng dữ liệu vận hành khi thử

Các ví dụ tạo constraint, receipt và cập nhật dữ liệu trong bài là **thao tác ghi thật**. Hãy thực hiện trong database thử nghiệm được cấp phép, với khóa event và SKU minh họa riêng, rồi dọn dữ liệu thử theo quy trình. Không chạy lệnh sửa dữ liệu trên production chỉ để quan sát giải thích.

## 16. Những ngộ nhận thường gặp

**“MERGE là đủ để xử lý event trùng.”** MERGE node theo khóa tránh tạo node trùng, nhưng một SET cộng dồn chạy sau MERGE vẫn cộng thêm mỗi lần nhận.

**“Exactly-once của broker tự áp dụng cho Neo4j.”** Bảo đảm của broker có phạm vi cụ thể; ghi Neo4j là một tác dụng phụ riêng cần receipt hoặc cơ chế tương đương.

**“Bất cứ sự kiện nào có version cao hơn cũng có thể bỏ qua những version giữa chừng.”** Chỉ có thể trong một số mô hình snapshot đầy đủ. Delta cộng dồn thường cần đủ lịch sử.

**“Cứ dựa vào occurredAt để sắp xếp.”** Đồng hồ phân tán, độ trễ mạng và nhiều nguồn phát có thể làm timestamp không phản ánh thứ tự nghiệp vụ.

**“Hai transaction cùng kiểm tra version ở WHERE rồi SET chắc chắn là compare-and-swap.”** Không thể kết luận nếu chưa hiểu khóa và thời điểm kiểm tra; cần thiết kế bảo vệ concurrency và kiểm chứng.

**“Một lỗi uniqueness luôn có nghĩa event đã xử lý.”** Có thể vi phạm constraint khác, hoặc cùng eventKey mang payload khác. Phải kiểm tra receipt và dữ liệu liên quan.

**“Checkpoint có thể commit trước rồi cập nhật graph sau.”** Crash giữa hai bước sẽ tạo trạng thái bị đánh dấu đã xử lý nhưng chưa áp dụng.

**“Ack ngay khi nhận event giúp pipeline nhanh hơn mà vẫn an toàn.”** Ack trước commit có thể làm mất event khi consumer crash.

**“Có thể xóa receipt khi đủ 24 giờ, bất kể replay.”** Nếu có thể nhận lại event cũ hơn khoảng lưu receipt, hệ thống có thể áp dụng lặp.

**“Mọi duplicate đều phải bị ném lỗi liên tục.”** Duplicate thật đã xác nhận là tình huống bình thường của at-least-once. Consumer nên trả kết quả đã xử lý, tránh kẹt hàng đợi.

## 17. Bài tập vận dụng

### Bài 1 — Chống cộng lặp

Một event `StockReceived` có eventKey `inventory:E8` và `quantity = 5`. Broker gửi event hai lần. Ứng dụng viết:

~~~cypher
MERGE (p:Product {sku: 'P7'})
SET p.stock = coalesce(p.stock, 0) + 5;
~~~

**Câu hỏi:** Vì sao stock có thể tăng 10 và cần bổ sung gì?

**Đáp án:** MERGE chỉ xử lý node Product; hai lần SET vẫn cộng 5 hai lần. Cần eventKey ổn định, receipt có constraint duy nhất và cập nhật stock cùng transaction, kèm xử lý duplicate.

### Bài 2 — Xung đột cùng ID

Hai bản tin dùng `eventKey = orders:E9` nhưng payload lần đầu `status = PAID`, lần sau `status = CANCELLED`.

**Câu hỏi:** Có nên coi lần thứ hai là duplicate thành công?

**Đáp án:** Không nếu payload khác nhau ngoài quy tắc chuẩn hóa đã thống nhất. Cần so hash/trường nghiệp vụ và điều tra xung đột ID.

### Bài 3 — Gap version

Projection có `lastAppliedVersion = 41`, nhận delta version 43.

**Câu hỏi:** Có nên áp dụng ngay vì 43 mới hơn?

**Đáp án:** Không nếu mỗi delta phụ thuộc vào việc version 42 đã được áp dụng. Đưa event 43 vào pending và tìm/replay version 42; chỉ cho phép nhảy version khi semantics và chính sách nguồn xác định rõ.

### Bài 4 — Snapshot cũ đến muộn

Projection Order có version 50 và status SHIPPED. Consumer nhận snapshot version 49, status PAID.

**Câu hỏi:** Cập nhật thế nào?

**Đáp án:** Không để snapshot cũ ghi đè version 50. Xác minh event theo quy tắc version của cùng nguồn/aggregate rồi phân loại stale hoặc duplicate.

### Bài 5 — Crash sau commit

Consumer đã commit Neo4j nhưng crash trước khi ack Kafka. Kafka gửi lại cùng eventKey.

**Câu hỏi:** Consumer cần làm gì?

**Đáp án:** Dựa vào receipt/constraint, xác nhận eventKey và payload đã được áp dụng; ack bản tin gửi lại mà không áp dụng delta lần nữa.

### Bài 6 — Hai loại phiên bản

Một event có `schemaVersion = 3` và `aggregateVersion = 17`.

**Câu hỏi:** Số nào dùng để chọn decoder JSON, số nào dùng để kiểm tra thứ tự thay đổi node?

**Đáp án:** schemaVersion chọn decoder; aggregateVersion thể hiện thứ tự logic của aggregate theo hợp đồng nguồn.

### Bài 7 — Receipt retention

Broker giữ 7 ngày, nhưng mỗi quý có job backfill sự kiện 90 ngày cũ. Receipt chỉ giữ 14 ngày.

**Câu hỏi:** Có nguy cơ gì?

**Đáp án:** Backfill có thể làm gửi lại delta đã áp dụng nhưng receipt bị xóa. Phải mở rộng retention hoặc sử dụng cơ chế checkpoint/rebuild an toàn tương đương cho khoảng backfill đó.

## 18. Ghi nhớ

Trong tích hợp sự kiện với Neo4j, **tính lũy đẳng** cần gắn với **một event hoặc thao tác nghiệp vụ được định danh ổn định**; `MERGE` node không tự chống cập nhật cộng dồn hai lần. Một giải pháp thực tiễn là lưu **receipt có uniqueness constraint**, rồi tạo receipt và cập nhật node/relationship/property **trong cùng transaction**. Nếu transaction commit nhưng broker chưa nhận ack, bản tin được phát lại vẫn có thể được xác minh mà không nhân đôi tác dụng.

**Thứ tự sự kiện** cần được giải quyết bằng version/sequence trong phạm vi aggregate và bằng semantics của **snapshot** hay **delta**. Sự kiện đến muộn, gap version, producer khác nhau, retry và replay đều phải có chính sách rõ ràng. Kết hợp khóa, constraint, Java Driver managed transaction, ack sau commit, pending/DLQ, retention và đối soát nguồn giúp graph phản ánh đúng nghiệp vụ ngay cả khi hệ thống phân tán gửi sự kiện **trùng, chậm hoặc sai thứ tự**.
