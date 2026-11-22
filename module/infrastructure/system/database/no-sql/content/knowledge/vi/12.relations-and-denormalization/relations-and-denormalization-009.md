# Sự kiện thay đổi, đối soát định kỳ và chiến lược sửa sai

## 1. Vì sao lặp dữ liệu cần cơ chế tự phục hồi?

Trong hệ NoSQL, một thực thể thường được lưu ở nhiều vị trí để phục vụ những đường đọc khác nhau. Một đơn hàng có thể xuất hiện trong bảng tra cứu theo ID, bảng lịch sử của khách hàng và bảng hàng chờ của người bán. Một sản phẩm có thể xuất hiện trong document database, chỉ mục tìm kiếm và cache.

Ví dụ:

~~~text
                      Đơn O100
                   status = PAID
                         |
             Đổi thành status = SHIPPED
                         |
              +----------+------------+
              |          |            |
              v          v            v
         orders_by_id  orders_by_user  orders_by_seller
           SHIPPED       SHIPPED         SHIPPED
~~~

Đó là trạng thái mong muốn. Nhưng một lần cập nhật bị timeout có thể để lại:

~~~text
Nguồn chính:             SHIPPED
Danh sách của khách:     SHIPPED
Hàng chờ của người bán:  PAID       <-- Sai lệch
~~~

Đồng bộ dữ liệu không chỉ là gọi các lệnh ghi sau mỗi lần thay đổi. Muốn vận hành tin cậy cần trả lời:

1. Bản ghi nào quyết định **trạng thái đúng**?
2. Làm sao chuyển thay đổi từ nguồn sang mọi bản sao?
3. Nếu event mất, trùng hoặc đến sai thứ tự thì sao?
4. Sai lệch tồn tại âm thầm được phát hiện thế nào?
5. Khi phát hiện lỗi, sửa ra sao mà không ghi đè dữ liệu mới?
6. Làm sao chứng minh hệ thống đã hội tụ về trạng thái đúng?

Ba thành phần cần phối hợp:

- **Sự kiện thay đổi (change event):** giúp các bản sao cập nhật liên tục hoặc gần thời gian thực.
- **Đối soát định kỳ (reconciliation):** so sánh dữ liệu dẫn xuất với nguồn chuẩn để tìm thiếu, thừa hoặc sai.
- **Sửa sai (repair):** đưa bản sao về trạng thái hợp lệ bằng retry, replay, sửa theo ID, backfill hoặc rebuild.

Ba cơ chế này bổ trợ nhau. Event stream mang lại độ mới; đối soát giúp phát hiện lỗi đã bị bỏ qua; repair giúp phục hồi trạng thái đúng.

## 2. Trước khi đồng bộ: xác định nguồn sự thật

**Source of truth** là nơi có quyền quyết định trạng thái nghiệp vụ của một trường hoặc thực thể. Những bản sao tối ưu truy vấn được gọi là **read model**, **projection** hoặc bảng phi chuẩn hóa.

| Vị trí dữ liệu | Vai trò | Ví dụ |
|---|---|---|
| Nguồn nghiệp vụ | Quyết định dữ liệu hiện tại và các bất biến | `orders_by_id` |
| Bảng dẫn xuất | Truy vấn nhanh theo khóa khác | `orders_by_customer` |
| Chỉ mục tìm kiếm | Tìm từ khóa, lọc và xếp hạng | `products_search` |
| Cache | Giảm thời gian đọc lặp | `product:P100` |
| Kho phân tích | Lưu facts, dimension, tổng hợp | `daily_sales` |
| Replica nội bộ DB | Phục vụ chịu lỗi/nhất quán hạ tầng | Các replica cùng partition |

**Replication hạ tầng không đồng nghĩa lặp dữ liệu theo đường truy cập.** Database có thể tự quản lý nhiều replica cho cùng một partition; nhưng hai bảng theo `orderId` và `customerId` là hai cấu trúc logic khác nhau. Việc một replica đã nhận ghi không chứng minh mọi read model khác đã cập nhật.

### 2.1. Một document có thể ghép nhiều nguồn chuẩn

Ví dụ tài liệu tìm kiếm:

~~~json
{
  "productId": "P100",
  "name": "Tai nghe không dây",
  "priceCents": 149900,
  "available": true,
  "categoryName": "Âm thanh"
}
~~~

Các trường có thể đến từ nhiều hệ:

- `name` do Product Service quản lý.
- `priceCents` do Pricing Service quản lý.
- `available` do Inventory Service quản lý.
- `categoryName` do Category Service quản lý.

Reconciler muốn sửa giá phải hỏi Pricing, không thể tin một bản sao khác có thể cũng bị trễ. Khi một projection gồm nhiều nguồn, phải lưu **quy tắc sở hữu từng trường** và phiên bản của từng thành phần nếu cần.

### 2.2. Giá trị khác nhau không phải lúc nào cũng sai

Ví dụ `priceAtPurchase` trong đơn hàng là snapshot giá tại lúc mua. Giá sản phẩm hiện tại tăng từ 100 lên 120 không có nghĩa phải cập nhật đơn hàng cũ thành 120.

Một trường dẫn xuất có thể mang các ý nghĩa:

- **Current state:** phản ánh giá trị hiện tại của nguồn.
- **Historical snapshot:** giá trị đúng tại thời điểm phát sinh nghiệp vụ.
- **Calculated value:** tổng, tỷ lệ, số lượng đã tính theo quy tắc.
- **Cached value:** có thể chậm trong khoảng được cho phép.

Đối soát phải so **đúng ngữ nghĩa**. Nếu lấy giá trị mới nhất ghi đè mọi bản chụp lịch sử, công cụ sửa sai lại trở thành nguyên nhân sai dữ liệu.

## 3. Sự kiện thay đổi mang thông tin gì?

Một change event mô tả sự thay đổi đã diễn ra. Nó có thể là **sự kiện nghiệp vụ** như `OrderShipped`, hoặc **sự kiện thay đổi dữ liệu** như thao tác UPDATE từ CDC.

Ví dụ:

~~~json
{
  "eventId": "2fd58b6e-0710-4a2a-b74d-8c6f4a6c0e61",
  "eventType": "OrderStatusChanged",
  "schemaVersion": 1,
  "aggregateId": "O100",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-14T08:30:00Z",
  "data": {
    "orderId": "O100",
    "customerId": "U42",
    "sellerId": "S9",
    "oldStatus": "PAID",
    "newStatus": "SHIPPED",
    "createdAt": "2026-11-13T10:00:00Z",
    "totalCents": 25990
  }
}
~~~

Từng consumer áp dụng khác nhau:

~~~text
                   OrderStatusChanged v8
                             |
                 +-----------+-----------+
                 |                       |
                 v                       v
        Customer-order view      Seller-status view
        SET status=SHIPPED       DELETE key status=PAID
                                 INSERT key status=SHIPPED
~~~

Một event không nhất thiết tương ứng một lệnh ghi. Nếu trường thay đổi là một phần **partition key**, read model có thể phải xóa hàng theo khóa cũ và thêm hàng với khóa mới.

### 3.1. Những trường nên cân nhắc

| Trường | Công dụng |
|---|---|
| `eventId` | Nhận diện event cụ thể để theo dõi/deduplicate |
| `aggregateId` | Xác định thực thể được thay đổi |
| `aggregateVersion` | So sánh cập nhật cũ và mới trong cùng thực thể |
| `eventType` | Diễn tả hành động hoặc dạng thay đổi |
| `schemaVersion` | Giải mã payload theo hợp đồng |
| `occurredAt` | Thời gian theo quy ước nguồn |
| `oldValue` | Xác định khóa cũ cần xóa khi cần |
| `newValue` | Dựng trạng thái mới |
| `sourcePosition` | Vị trí log/CDC phục vụ resume và audit |

Không phải event nào cũng cần đủ các trường. Nhưng nếu một bảng dùng `status` làm khóa mà event chỉ chứa `newStatus`, consumer cần cách khác xác định `oldStatus` để xóa hàng cũ.

### 3.2. Full-state event và delta event

**Full-state event** mang trạng thái cần cho projection:

~~~json
{
  "aggregateId": "O100",
  "aggregateVersion": 8,
  "operation": "UPSERT",
  "state": {
    "orderId": "O100",
    "customerId": "U42",
    "sellerId": "S9",
    "status": "SHIPPED",
    "totalCents": 25990
  }
}
~~~

Dễ dùng để dựng bản sao hiện tại, nhưng có thể không có khóa cũ. **Delta event** chỉ chứa những trường được sửa:

~~~json
{
  "aggregateId": "O100",
  "aggregateVersion": 8,
  "operation": "PATCH",
  "changes": {
    "status": {
      "before": "PAID",
      "after": "SHIPPED"
    }
  }
}
~~~

Delta gọn hơn nhưng đòi hỏi các event có thứ tự, không bị mất và consumer đã có trạng thái trước đó. Full-state dễ hồi phục hơn cho current-state view, nhưng có chi phí payload cao và vẫn cần quy tắc xóa/di chuyển khóa.

## 4. Thu nhận thay đổi mà không làm mất sự kiện

### 4.1. Vấn đề dual write

Cách viết đơn giản:

~~~text
1. Ghi database nguồn.
2. Gửi event đến broker.
~~~

Nếu bước một thành công rồi tiến trình crash trước bước hai, nguồn mới mà read model không biết. Đảo thứ tự cũng có lỗi: phát event thành công nhưng transaction nguồn rollback.

Hai hệ riêng lẻ không tự tạo thành một giao dịch chỉ vì code gọi chúng liên tiếp.

### 4.2. Transactional outbox

Khi nguồn hỗ trợ giao dịch phù hợp, ghi cả thay đổi nghiệp vụ và bản ghi outbox trong **cùng transaction**:

~~~text
               Một transaction
        +---------------------------+
        | UPDATE orders             |
        | INSERT outbox_event       |
        | COMMIT                    |
        +---------------------------+
                    |
                    v
               Outbox relay
                    |
                    v
                 Broker
                    |
                    v
                Consumers
~~~

Ví dụ SQL minh họa:

~~~sql
BEGIN;

UPDATE orders
SET status = 'SHIPPED',
    version = version + 1
WHERE order_id = :order_id
RETURNING order_id, version, status;

-- Ứng dụng lấy version mới từ RETURNING và bind payload.
INSERT INTO outbox_events (
    event_id, aggregate_id, aggregate_version,
    event_type, payload
)
VALUES (
    :event_id, :order_id, :new_version,
    'OrderStatusChanged', :payload_json
);

COMMIT;
~~~

Các placeholder phải được cung cấp bởi ứng dụng; đoạn này minh họa thứ tự và ranh giới transaction, không phải script độc lập.

Relay phát outbox ra broker. Nếu relay crash sau khi broker nhận nhưng trước khi đánh dấu đã gửi, event có thể được phát lại. Outbox giải quyết nguy cơ **mất sự kiện giữa ghi nguồn và ghi outbox**, nhưng không tự bảo đảm exactly-once trên mọi sink.

### 4.3. Change Data Capture (CDC)

CDC đọc thay đổi đã commit từ cơ chế nguồn hỗ trợ như transaction log, change stream hoặc event feed:

~~~text
Ứng dụng
   |
   v
Database nguồn
   |
   v
Change log/CDC connector
   |
   v
Broker hoặc consumer
   |
   v
Read model
~~~

Tùy database, event CDC có thể chứa document đầy đủ, dữ liệu trước/sau hoặc chỉ những trường thay đổi. Delete có thể chỉ mang khóa. Cần tìm hiểu:

- Có thu nhận mọi thay đổi đã commit không?
- Log được giữ bao lâu khi consumer ngừng chạy?
- Resume token/offset hoạt động thế nào?
- Thứ tự được bảo đảm trong phạm vi nào?
- Một event có đủ thông tin để xóa projection key cũ không?
- Thay đổi schema nguồn ảnh hưởng consumer thế nào?

Ví dụ với MongoDB Node.js driver, cú pháp minh họa:

~~~javascript
const changeStream = db.collection("orders").watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);

for await (const change of changeStream) {
  console.log(change.operationType, change.documentKey);
  // Chuyển đổi và ghi sink, lưu resume token/checkpoint
  // chỉ sau khi đã xử lý thành công hoặc nhận trách nhiệm retry bền vững.
}
~~~

Cần kết nối, quyền truy cập, topology và xử lý lỗi/resume phù hợp với phiên bản sản phẩm. Không phải mọi NoSQL đều có cùng API hoặc khả năng CDC.

### 4.4. Dùng nguồn event bền vững

Nếu event log chỉ giữ bảy ngày và consumer ngừng 10 ngày, không thể mặc định resume từ vị trí cũ. Cần khả năng **snapshot/backfill từ nguồn**, cùng cơ chế chuyển tiếp qua những thay đổi mới.

Nếu sự kiện có ý nghĩa nghiệp vụ rất quan trọng, cân nhắc chính sách lưu trữ dài hạn hoặc log chuyên dụng phù hợp với yêu cầu tái dựng lịch sử.

## 5. Thứ tự, phiên bản và xử lý lặp

### 5.1. Event ID khác phiên bản thực thể

Giả sử:

~~~text
E8: O100 v8 status=SHIPPED
E9: O100 v9 status=DELIVERED
~~~

Nếu E9 đến trước E8, deduplicate dựa trên `eventId` không giúp vì đây là hai event khác nhau. Cần so **aggregateVersion** hoặc một sequence có bảo đảm phù hợp.

Một sink đang ở version 9 không được áp dụng event version 8 để ghi lùi về `SHIPPED`.

### 5.2. Sắp thứ tự theo khóa trong broker chưa đủ

Một broker có thể giữ thứ tự trong partition khi các event dùng cùng một key. Nhưng sau khi nhận, nhiều tác vụ bất đồng bộ có thể hoàn thành không cùng thứ tự:

~~~text
E8 -> worker A -> gọi database chậm
E9 -> worker B -> ghi database nhanh
E9 đã ghi; E8 hoàn thành sau
~~~

Phải bảo vệ ở **nơi cam kết ghi bản sao**, chẳng hạn conditional write/CAS theo version, hoặc đảm bảo một tác vụ cùng khóa được thực thi tuần tự và không có writer khác phá trật tự.

### 5.3. Consumer idempotent

Với at-least-once delivery, event có thể được xử lý nhiều lần. Một consumer idempotent hướng đến:

- **Khóa projection ổn định** từ ID nguồn, không sinh ID ngẫu nhiên mỗi retry.
- Upsert cùng event không tạo thêm hàng.
- Version cũ hoặc event trùng được bỏ qua an toàn.
- Delete không làm bản ghi mới hơn biến mất.
- Tác động cộng dồn có cơ chế dedup theo event/business key.

Giả mã:

~~~text
function apply(event):
    key = projectionKey(event.aggregateId)
    currentVersion = sink.getVersion(key)

    if currentVersion >= event.aggregateVersion:
        return ACK_OLD_OR_DUPLICATE

    projected = transform(event)

    sink.atomicWriteIfNewer(
        key,
        projected,
        event.aggregateVersion
    )

    return ACK
~~~

**Lưu ý:** `getVersion` rồi `write` rời nhau vẫn có race giữa các worker. Phép kiểm tra version và ghi phải là một thao tác được bảo vệ nguyên tử hoặc có giao thức tuần tự tương đương. Đây là giả mã mô tả yêu cầu, không phải API sẵn có cho mọi database.

### 5.4. Sự kiện tính tổng cần đặc biệt cẩn trọng

Nếu consumer nhận `OrderPaid(O100)` và thực hiện:

~~~text
dailyRevenue = dailyRevenue + 25990
~~~

thì replay hai lần sẽ cộng hai lần. Thường cần một fact có định danh ổn định như `paid_order_facts[orderId]`, hoặc một transaction có dedup phù hợp rồi mới tổng hợp.

Không nên coi mọi event là an toàn để “chạy lại” nếu thao tác sink là cộng/trừ không idempotent.

## 6. Quan hệ và lặp dữ liệu làm sai lệch phức tạp ra sao?

### 6.1. Bảng có khóa theo trạng thái

Thiết kế wide-column:

~~~text
orders_by_id:
    PK = orderId

orders_by_customer_month:
    PK = (customerId, month)
    clustering = (createdAt, orderId)

orders_by_seller_status_month:
    PK = (sellerId, status, month)
    clustering = (createdAt, orderId)
~~~

Khi O100 chuyển `PAID -> SHIPPED`:

1. Ghi `status=SHIPPED` ở bảng chính.
2. Cập nhật cột trạng thái trong bảng lịch sử khách.
3. Xóa hàng với khóa `sellerId, PAID, month, createdAt, orderId`.
4. Thêm hàng với khóa `sellerId, SHIPPED, month, createdAt, orderId`.

Nếu bước 3 lỗi, cùng một đơn có thể xuất hiện ở cả hai hàng chờ:

~~~text
seller=S9/status=PAID       -> O100 (sai)
seller=S9/status=SHIPPED    -> O100 (đúng)
~~~

Đây là **sai lệch giữa những bản sao logic**, không phải lỗi replication nội bộ.

### 6.2. Quan hệ hai chiều

Một membership giữa tài khoản U1 và thiết bị D7 có thể lưu:

~~~text
devices_by_user:  (U1, D7)
users_by_device:  (D7, U1)
~~~

Nếu xóa quan hệ ở một hướng mà quên hướng còn lại, hai câu hỏi trả lời khác nhau:

- “U1 dùng thiết bị nào?”
- “D7 được ai sử dụng?”

Reconciliation cần so sánh **tập cạnh quan hệ** theo nguồn chuẩn của membership, không chỉ kiểm tra từng document đơn lẻ.

### 6.3. Đổi trường nằm trong khóa cần dọn khóa cũ

Đổi `customerId` hoặc `status` thường làm vị trí logic của bản ghi trong read model thay đổi. Nếu chỉ thêm vị trí mới, vị trí cũ trở thành **orphan**.

Để sửa, phải biết khóa cũ. Cách tổ chức có thể gồm:

- Event mang `oldStatus`, `oldCustomerId`;
- Lưu manifest `orderId -> các projection keys đang tồn tại`;
- Lưu lịch sử thay đổi khóa để replay;
- Dựng lại theo partition/bucket khi không thể tìm theo ID;
- Thiết kế một index ngược chỉ phục vụ repair nếu chi phí xứng đáng.

Không nên mặc định Cassandra có truy vấn hiệu quả theo `orderId` trên bảng mà `orderId` chỉ là clustering column phía sau những trường partition key không biết.

## 7. Tại sao cần đối soát định kỳ dù đã có event?

Một đường đồng bộ có thể mất chính xác vì:

- Dual write lỗi giữa hai bước.
- CDC log hết hạn khi connector tạm ngừng.
- Consumer ACK trước khi sink ghi thành công.
- Mapping hoặc transform có bug nhưng không phát exception.
- Event mới bị event cũ ghi đè.
- Thao tác xóa khóa cũ bị bỏ sót.
- Cập nhật schema nhưng không backfill dữ liệu cũ.
- Quá trình import/backfill đưa dữ liệu cũ vào sau dữ liệu mới.
- Event bị đưa vào DLQ mà không ai replay.
- Một tác vụ quản trị ghi/xóa trực tiếp trên sink.

Nếu chỉ dùng event, các sai lệch **âm thầm** có thể tồn tại rất lâu. Đối soát tạo một cơ chế kiểm chứng độc lập:

~~~text
              Nguồn sự thật
                   |
           +-------+-------+
           |               |
           v               v
       Event pipeline   Reconciliation job
           |               |
           v               v
       Read model     Compare expected/actual
           ^               |
           |               v
           +----------- Repair
~~~

Reconciliation **không thay thế** pipeline liên tục; nó đảm nhận việc phát hiện và phục hồi khi pipeline không đạt kết quả đúng.

## 8. So sánh những gì khi đối soát?

Đối soát là quá trình tính ra **trạng thái mong đợi của projection** từ nguồn chuẩn rồi so với trạng thái thực tế.

~~~text
expected = project(authoritativeRecord, projectionSchema)
actual   = loadProjection(authoritativeRecord.id)
compare(expected, actual)
~~~

### 8.1. Các mức kiểm tra

| Mức | Phương pháp | Nhìn thấy được | Hạn chế |
|---|---|---|---|
| Số lượng | So count theo phạm vi | Lệch nhiều bản ghi | Không chỉ ra ID cụ thể |
| Tập khóa | So source IDs và sink IDs | Bản ghi thiếu/thừa | Không phát hiện giá trị sai |
| Phiên bản | So sourceVersion | Bản sao cũ hoặc đến sau | Cùng version vẫn có thể sai nội dung |
| Nội dung | So các trường sau chuẩn hóa | Transform lỗi, trường sai | Cần định nghĩa projection chính xác |
| Quan hệ | So tập cạnh/khóa đảo chiều | Cạnh dư hoặc thiếu | Có thể cần nguồn edge authoritative |
| Tổng hợp | Đối chiếu facts và tổng theo quy tắc | Báo cáo cộng thiếu/trùng | Phải biết thời điểm và cách tính |

Ví dụ:

| ID | Nguồn chuẩn | View khách | View người bán | Kết quả |
|---|---|---|---|---|
| O100 | SHIPPED/v8 | SHIPPED/v8 | SHIPPED/v8 | Khớp |
| O101 | PAID/v6 | CREATED/v5 | PAID/v6 | View khách chậm |
| O102 | CANCELLED/v9 | CANCELLED/v9 | còn hàng PAID/v8 | Khóa cũ chưa xóa |
| O103 | DELETED/v12 | còn O103/v10 | không có | View khách còn bản sao |
| O104 | PAID/v3, total=200 | PAID/v3, total=100 | PAID/v3 | Nội dung sai dù version khớp |

**Bằng count không chứng minh hai hệ có cùng bản ghi.** Ví dụ nguồn có ID A, B, C; view có A, B, D: hai bên đều có ba bản ghi nhưng C thiếu và D thừa.

### 8.2. Cùng phiên bản chưa chắc cùng nội dung

Nếu bug của projector đã tính `totalCents` sai nhưng vẫn lưu `sourceVersion = 3`, kiểm tra version sẽ cho kết quả bình thường. Vì vậy, những projection quan trọng có thể cần so trường hoặc hash của **giá trị chuẩn hóa được kỳ vọng**.

### 8.3. Hàm project phải biết ngữ nghĩa

Nếu một đơn chỉ lưu snapshot giá mua, không thể so với giá sản phẩm hôm nay. Nếu view chỉ lưu tổng và trạng thái, không nên báo thiếu vì nó không có đầy đủ thông tin giống nguồn.

Hợp đồng projection cần quy định:

- Trường nào được sao chép;
- Trường nào được tính hoặc tổng hợp;
- Trường nào là snapshot lịch sử;
- Quy tắc số thập phân và làm tròn;
- Null so với trường không tồn tại;
- Ngữ nghĩa thứ tự array;
- Quy tắc trạng thái đã xóa;
- Phiên bản schema projection.

Đối soát không có hợp đồng này dễ sửa đúng thành sai.

## 9. Thời điểm so sánh: tránh báo sai khi dữ liệu vẫn thay đổi

Ví dụ:

~~~text
T1: Reconciler đọc nguồn O100 = PAID/v7
T2: Nguồn commit SHIPPED/v8
T3: Event cập nhật view SHIPPED/v8
T4: Reconciler đọc view SHIPPED/v8
~~~

Nếu reconciler lấy snapshot nguồn v7 để ghi đè view v8, nó gây sai lệch. Cần xác định **mốc so sánh và điều kiện ghi an toàn**.

### 9.1. Version-aware reconciliation

Khi phát hiện view v7, nguồn v8:

1. Xác định đây có thể là độ trễ trong ngưỡng cho phép.
2. Nếu quá ngưỡng, đọc lại trạng thái nguồn và view.
3. Chỉ áp dụng phiên bản mới hơn bằng điều kiện nguyên tử.
4. Kiểm tra kết quả sau sửa.

Nếu view v9 nhưng nguồn vừa đọc ra v8, không nên ép view về v8. Có thể nguồn được đọc qua replica trễ hoặc snapshot cũ. Cần điều tra rồi đọc lại từ nơi authoritative phù hợp.

### 9.2. Watermark và offset

Nếu đồng bộ qua CDC/broker, có thể ghi lại vị trí đã xử lý. Nhiều broker chỉ bảo đảm thứ tự **trong partition**, nên watermark có thể là một tập offset:

~~~text
partition-0: applied through 1200
partition-1: applied through  850
partition-2: applied through 2100
~~~

Không được lấy offset 2100 rồi cho rằng toàn pipeline đã đồng bộ mọi event từ mọi partition đến vị trí đó.

Đối soát theo mốc cần có định nghĩa rõ **event nào chắc chắn đã được áp dụng** và projection đã truy vấn thấy hay chưa.

### 9.3. Grace period

Nếu SLO cho phép bản sao chậm tối đa 30 giây, view kém một phiên bản trong 2 giây có thể là điều bình thường.

Một cách phân loại:

- **Expected lag:** lệch trong ngưỡng hội tụ.
- **Stale beyond SLO:** view vẫn cũ sau ngưỡng.
- **Missing:** bản ghi đáng có nhưng không có.
- **Orphan:** bản ghi ở view không còn thuộc dữ liệu nguồn.
- **Corrupt:** nội dung không khớp ngay cả khi version bằng.
- **Conflict:** nhiều nguồn/trạng thái có vẻ cùng authoritative.

Cần tính thời gian sai lệch theo mốc phù hợp, không dựa vào đồng hồ ngẫu nhiên của từng worker khi nguồn có sequence/version rõ hơn.

## 10. Đối soát định kỳ ở quy mô lớn

Với 100 triệu document, không thể tùy tiện quét toàn bộ nguồn và sink mỗi phút mà không tính tải.

### 10.1. Chia phạm vi

Các chiến lược phổ biến:

- Theo tenant;
- Theo ngày/tháng phát sinh;
- Theo shard hoặc partition;
- Theo hash bucket của ID;
- Theo nhóm nghiệp vụ quan trọng;
- Theo tập ID có sự kiện lỗi;
- Theo khoảng version hoặc CDC position.

~~~text
Reconciliation scheduler
      |
      +--> bucket 00, tenant T1
      +--> bucket 01, tenant T1
      +--> bucket 00, tenant T2
      +--> recent changed IDs
      +--> failed/retry IDs
~~~

Mỗi job có checkpoint/cursor để tiếp tục sau khi crash.

### 10.2. Incremental và full scan

**Incremental scan** xem bản ghi mới thay đổi hoặc ID bị nghi ngờ. Nó tiết kiệm tài nguyên và giúp sửa nhanh, nhưng có thể bỏ sót lỗi lịch sử nếu danh sách “đã thay đổi” không đầy đủ.

**Full scan** kiểm tra toàn bộ phạm vi, phát hiện cả những sai lệch lâu ngày. Nó tốn nhiều I/O, nên thường chạy luân phiên theo bucket, trong lịch vận hành thích hợp.

Một chiến lược kết hợp:

1. Liên tục đối soát những ID có lỗi/retry.
2. Thường xuyên kiểm tra các bản ghi vừa thay đổi.
3. Hằng ngày quét các bucket theo lượt.
4. Định kỳ bao phủ toàn bộ tập dữ liệu.
5. Khi pipeline có sự cố, quét ưu tiên phạm vi sự kiện bị ảnh hưởng.

### 10.3. Phân trang ổn định

Quét dữ liệu đang thay đổi bằng offset pagination có thể bị lặp hoặc bỏ sót khi bản ghi thêm/xóa làm dịch vị trí. Nên dùng cursor/keyset hoặc cơ chế snapshot của database khi có thể.

Nếu dùng `updatedAt` làm watermark, cần xử lý nhiều bản ghi có cùng timestamp và transaction commit trễ; không nên cập nhật `lastSyncTime = now()` mà chưa đảm bảo tất cả thay đổi trước mốc đã được xử lý.

### 10.4. Giới hạn tải

Reconciler không được làm nghẽn giao dịch đang phục vụ người dùng. Cần giới hạn:

- Số partition hoặc ID đang quét đồng thời;
- Kích thước batch;
- Request/giây đến nguồn và sink;
- Băng thông, CPU, I/O;
- Thời gian chạy và mức ưu tiên;
- Retry khi hệ đang quá tải.

Nếu phát hiện sai lệch nghiêm trọng, có thể ưu tiên một số ID trước, thay vì chạy full scan không kiểm soát.

## 11. Hash và checksum để thu hẹp sai lệch

Khi so nhiều trường tốn băng thông, có thể tính hash của projection **sau chuẩn hóa**.

~~~text
Source record
     |
     v
projectForCustomerView(source)
     |
     v
canonical serialization
     |
     v
SHA-256 expectedHash
~~~

Sink dùng cùng quy tắc để tính `actualHash`. Hash khác là dấu hiệu cần kiểm tra sâu.

### 11.1. Canonicalization là điều bắt buộc

Hai object JSON:

~~~json
{"a": 1, "b": 2}
~~~

và:

~~~json
{"b": 2, "a": 1}
~~~

có thể biểu thị cùng nội dung nhưng khi hash chuỗi văn bản nguyên gốc sẽ khác nhau. Cần xác định:

- Thứ tự tên trường;
- Biểu diễn số như `1` và `1.0`;
- Chuẩn hóa Unicode;
- Ngày giờ và múi giờ;
- Null so với missing;
- Thứ tự mảng có ý nghĩa không;
- Trường kỹ thuật nào được bỏ qua;
- Projection schema version.

Hash phải phản ánh **cùng tập trường và cùng ý nghĩa dữ liệu**. Hash của schema v1 không nên so trực tiếp với hash của schema v2.

### 11.2. Hash theo bucket hoặc Merkle tree

Một chiến lược:

~~~text
Tổng 64 bucket
   |
   +--> bucket 00: hash nguồn vs hash view
   +--> bucket 01: hash nguồn vs hash view
   ...
   +--> bucket 63: hash nguồn vs hash view
~~~

Chỉ đi sâu vào những bucket khác nhau, sau đó so ID và trường. Các cấu trúc hash phân cấp như Merkle tree có thể giúp tìm vùng lệch ở tập dữ liệu lớn.

Tuy nhiên, nguồn và sink vẫn thay đổi liên tục. Nếu hai bên được hash ở những thời điểm không tương đương, chênh lệch có thể chỉ do lag hợp lệ. Cần mốc snapshot hoặc watermark thích hợp.

## 12. Phân loại sai lệch và cách sửa phù hợp

| Loại lỗi | Biểu hiện | Hướng sửa |
|---|---|---|
| Missing projection | Nguồn có, view không có | Dựng projection từ nguồn |
| Stale projection | View version thấp hơn nguồn | Replay hoặc conditional upsert bản mới |
| Orphan | View có nhưng nguồn đã xóa/chuyển | Xóa/ẩn bản thừa với version guard |
| Sai khóa | Hàng nằm trong partition/status cũ | Xóa khóa cũ, thêm khóa đúng |
| Sai trường | Version khớp nhưng nội dung khác | Tính lại transform |
| Trùng bản ghi | Một ID xuất hiện nhiều hàng không mong muốn | Ổn định khóa, xóa hàng dư |
| Sai quan hệ | Cạnh tồn tại ở một hướng nhưng không ở hướng khác | Đối soát nguồn membership, cập nhật cả hai view |
| Thiếu lịch sử | Bảng tổng hợp thiếu fact cũ | Replay log/fact authoritative nếu còn |
| Không hiểu schema | Consumer không hỗ trợ event mới | Sửa mapping, backfill/reindex |
| Xung đột nguồn | Hai hệ đều tuyên bố là chủ sở hữu cùng trường | Quyết định quyền sở hữu và cách hòa giải |

**Không phải mọi sai lệch đều khôi phục được từ current state.** Nếu projection lịch sử cần event đã bị xóa khỏi cả log và nguồn, không thể tự tạo ra dữ liệu chính xác chỉ từ trạng thái mới nhất.

## 13. Các chiến lược sửa sai

### 13.1. Retry một event

Phù hợp khi lỗi mạng tạm thời, sink rate limit hoặc timeout, và thao tác cập nhật là idempotent.

Cần backoff, jitter, giới hạn retry và quan sát. Retry vô hạn một event sai schema chỉ làm nghẽn luồng.

### 13.2. Replay từ log

Phù hợp khi biết một consumer lỗi trong khoảng offset/time nhất định và broker còn dữ liệu.

Điều kiện:

- Tái áp dụng không tạo tác động phụ trùng;
- Event cũ không ghi đè view mới;
- Có checkpoint và cách kiểm chứng hoàn tất;
- Có đủ thông tin để dựng lại projection cần thiết.

### 13.3. Read-repair theo ID

Khi lệch vài bản ghi:

~~~text
Mismatch O100
     |
     v
Read authoritative O100
     |
     v
Transform expected projection
     |
     v
Conditional upsert / delete
     |
     v
Verify actual view
~~~

Ưu điểm: không cần replay lịch sử nếu view chỉ biểu diễn trạng thái hiện tại. Nhưng nếu view là bảng tổng hợp lịch sử hoặc cần biết khóa cũ, có thể cần thêm log/manifest.

### 13.4. Backfill theo lô

Nếu hàng nghìn hoặc hàng triệu bản ghi thiếu do pipeline dừng:

1. Chia phạm vi theo tenant/partition/date/bucket.
2. Đọc nguồn theo cursor có checkpoint.
3. Tính projection với schema hiện hành.
4. Ghi bằng version guard.
5. Tiếp tục áp dụng event mới trong lúc backfill.
6. Đối soát lại phạm vi đã sửa.

Cần tránh snapshot v7 ghi đè event v8 vừa được consumer áp dụng.

### 13.5. Rebuild toàn bộ read model

Khi mapping sai hàng loạt hoặc cần đổi schema/index, có thể xây view mới song song:

~~~text
Source + events
     |
     +----> view_v1 (đang phục vụ)
     |
     +----> view_v2 (snapshot + catch-up)
                        |
                        v
                   Reconciliation
                        |
                        v
                    Cutover
~~~

Chỉ chuyển traffic sau khi view mới đủ dữ liệu, đạt freshness SLO và các phép đối soát cần thiết. Nên có rollback/alias hoặc cách chuyển tương đương của sản phẩm.

### 13.6. Sửa thủ công

Một số trường hợp cần xác nhận nghiệp vụ: hai tài khoản bị gộp nhầm, lịch sử thanh toán tranh chấp hoặc thiếu nguồn gốc dữ liệu. Repair thủ công cần audit trail, quyền thực thi, bằng chứng và kiểm tra sau sửa. Không nên dùng “lấy timestamp mới nhất” như quy tắc chung khi hai nguồn xung đột.

## 14. Repair cần idempotent và version-aware

Một repair job tốt phải tránh tạo lỗi mới khi chạy đồng thời với event pipeline.

### 14.1. Race giữa repair và cập nhật mới

~~~text
T0: Reconciler đọc source O100 version 8
T1: Consumer ghi view version 9
T2: Reconciler muốn ghi view version 8
~~~

Nếu repair ghi vô điều kiện, trạng thái bị lùi. **Phép kiểm tra phiên bản ở sink phải nguyên tử** hoặc có giao thức bảo đảm một writer cho cùng khóa.

### 14.2. Giả mã

~~~text
function reconcile(orderId):
    source = authoritativeStore.read(orderId)
    actual = projection.lookupBySourceId(orderId)

    if source is deleted:
        removeAllProjectionKeysSafely(orderId, source.deleteVersion)
        verifyDelete(orderId)
        return

    expected = project(source)

    if actual is missing:
        conditionalUpsertIfNewer(expected, source.version)
        verify(orderId)
        return

    if actual.sourceVersion < source.version:
        conditionalUpsertIfNewer(expected, source.version)
        verify(orderId)
        return

    if actual.sourceVersion == source.version:
        if canonicalHash(actual) != canonicalHash(expected):
            repairSameVersionWithConcurrencyGuard(expected)
            verify(orderId)
        return

    if actual.sourceVersion > source.version:
        investigateOrRetryWithFreshSourceRead(orderId)
~~~

Đây là **giả mã**, chưa gồm cách xác định khóa cũ hoặc transaction của một hệ cụ thể. Đặc biệt, sửa khi **version bằng nhau nhưng nội dung sai** cần có quy tắc bảo vệ để không tranh chấp với một writer khác đang chuyển sang version tiếp theo.

### 14.3. Những tính chất mong muốn

- **Idempotent:** chạy hai lần cho kết quả tương đương chạy một lần.
- **Version-safe:** không ghi đè dữ liệu mới bằng snapshot cũ.
- **Scoped:** chỉ sửa ID/phạm vi xác định.
- **Rate-limited:** không gây quá tải nguồn và sink.
- **Observable:** có log, metric và dấu vết thay đổi.
- **Verifiable:** đọc lại và kiểm chứng hội tụ.
- **Resumable:** worker crash có thể tiếp tục từ checkpoint.
- **Auditable:** biết vì sao hệ đã sửa dữ liệu đó.

## 15. Manifest để tìm những hàng phải xóa

Một khó khăn của wide-column là read model chỉ truy vấn tốt theo partition key đã thiết kế. Nếu `orderId` không phải partition key, tìm mọi hàng phụ của đơn đó có thể tốn chi phí.

Có thể lưu **projection manifest**:

~~~json
{
  "orderId": "O100",
  "sourceVersion": 8,
  "keys": {
    "customerView": ["U42/2026-11/O100"],
    "sellerStatusView": ["S9/SHIPPED/2026-11/O100"]
  }
}
~~~

Khi trạng thái đổi, worker so khóa mới với khóa hiện có để xóa phần cũ và thêm phần mới.

Tuy nhiên, manifest **cũng là dữ liệu phải duy trì đúng**. Nếu ghi manifest thành công nhưng ghi view lỗi (hoặc ngược lại), đối soát cần phát hiện. Vì vậy có thể kết hợp manifest với log sự kiện, một cơ chế write-step checkpoint hoặc quét định kỳ ở phạm vi hạn chế.

Nếu hệ không cần nhiều view đảo chiều, chi phí manifest có thể không đáng. Thiết kế cần dựa vào lượng quan hệ và yêu cầu phục hồi.

## 16. Xóa dữ liệu và chống “hồi sinh” bản ghi

### 16.1. Event DELETE

Nếu nguồn xóa O100 mà consumer chỉ xử lý insert/update, bản sao có thể tồn tại vô thời hạn.

~~~json
{
  "eventId": "e4185032-f025-4649-b81a-1ac82bfd975f",
  "eventType": "OrderDeleted",
  "aggregateId": "O100",
  "aggregateVersion": 12,
  "operation": "DELETE"
}
~~~

Consumer cần xóa/ẩn các projection thuộc phạm vi, bao gồm những hàng theo khóa cũ. Có thể cần old key, manifest hoặc lịch sử để tìm chúng.

### 16.2. Tombstone và version marker

Giả sử:

~~~text
T1: DELETE O100 version 12
T2: Snapshot cũ UPSERT O100 version 10 đến muộn
~~~

Nếu sink đã xóa sạch cả dữ liệu và dấu version, snapshot v10 có thể tạo lại O100. Cần cơ chế **tombstone/version guard**, hoặc một quy trình snapshot/replay đảm bảo không áp dụng dữ liệu cũ sau delete.

Thời gian giữ tombstone phải xét tuổi tối đa của event/snapshot có thể replay. TTL ngắn không tự bảo vệ được mọi trường hợp worker cũ đến muộn.

### 16.3. Delete có ý nghĩa nghiệp vụ khác nhau

- **Soft delete:** trạng thái nguồn chuyển sang INACTIVE/DELETED, projection có thể ẩn.
- **Hard delete:** nguồn bỏ hẳn bản ghi, cần event xóa hoặc phát hiện thay đổi từ log.
- **Retention:** dữ liệu lịch sử có thể được giữ dưới dạng đã tổng hợp/ẩn danh tùy chính sách.
- **Quyền được xóa:** cần xem cả bản sao, cache, index, vector, báo cáo và bản xuất liên quan.

Không thể khẳng định đã xử lý xong xóa dữ liệu chỉ vì document nguồn không còn đọc được.

## 17. Đối soát nhiều nguồn và dữ liệu tổng hợp

### 17.1. Mỗi nguồn có version riêng

Một tài liệu search có thể kết hợp Product v18, Price v46 và Inventory v207:

~~~json
{
  "productId": "P100",
  "versions": {
    "product": 18,
    "price": 46,
    "inventory": 207
  }
}
~~~

Một trường `sourceVersion=18` không đủ thể hiện thay đổi giá v46. Phải biết **component version** hoặc một snapshot có quy tắc nhất quán.

Không được so các số version thuộc **những hệ khác nhau** như thể chúng nằm trên cùng một trục thời gian.

### 17.2. Bảng tổng hợp và late events

Một đơn có thể được ghi nhận doanh thu lúc thanh toán, rồi sau đó hoàn tiền. Nếu pipeline cộng mỗi event vào `dailyRevenue` mà không có fact idempotent hoặc cách điều chỉnh, số liệu sẽ sai.

Ngoài ra, event của ngày hôm qua có thể đến hôm nay. Một pipeline OLAP cần định nghĩa theo **event time** hay **processing time**, watermark, cách xử lý late-arriving events và backfill khoảng ngày bị ảnh hưởng.

Reconciliation cho aggregate nên đối chiếu từ **facts chuẩn hóa hoặc nguồn lịch sử**, không chỉ so với trạng thái hiện tại của từng đơn nếu đã mất thông tin giao dịch.

### 17.3. Bản ghi liên quan thay đổi độc lập

Nếu seller đổi tên, hàng trăm nghìn document tìm kiếm sản phẩm có `sellerName` sao chép có thể trở nên cũ. Cần chọn:

- Phát sự kiện SellerChanged và fan-out cập nhật;
- Giữ reference thay vì sao chép một số trường;
- Dùng read model đã join theo event;
- Chấp nhận tên cũ có giới hạn nếu nghiệp vụ cho phép.

Tăng denormalization giúp đọc nhanh hơn nhưng làm chi phí propagation/reconciliation lớn hơn.

## 18. Retry, DLQ và xử lý lỗi không phục hồi

### 18.1. Phân biệt lỗi

- **Tạm thời:** timeout, rate limit, mạng chập chờn.
- **Dữ liệu:** payload sai schema, thiếu trường, kiểu không hợp lệ.
- **Phụ thuộc:** event liên quan đến bản ghi chưa được tạo tại sink.
- **Ngữ nghĩa:** event cũ, trạng thái không thể áp dụng, nguồn đã xóa.
- **Hạ tầng:** sink không khả dụng hoặc đổi mapping.

Lỗi tạm thời có thể retry với backoff và jitter. Event sai schema thường cần sửa consumer/data rồi replay; retry vô điều kiện chỉ gây tắc nghẽn.

### 18.2. Dead Letter Queue

~~~text
Event -> Consumer -> Sink
              |
              +--> OK: ACK
              |
              +--> Retryable: backoff + retry
              |
              +--> Permanent: DLQ + alert
                                   |
                                   v
                                Fix cause
                                   |
                                   v
                                 Replay
                                   |
                                   v
                             Reconciliation
~~~

DLQ nên giữ event ID, aggregate ID/version, nguồn, consumer, lỗi, số lần thử và thời điểm. Với dữ liệu nhạy cảm, có thể giữ tham chiếu payload được bảo vệ thay vì sao chép nội dung rộng rãi.

**Đưa event vào DLQ không có nghĩa bản sao đã đúng.** Cần giám sát số event tồn đọng, thời gian tồn đọng và xử lý/replay có kiểm chứng.

### 18.3. ACK phải gắn với trách nhiệm bền vững

Một consumer chỉ nên ACK khi:

- Ghi sink đã thành công theo bảo đảm yêu cầu; hoặc
- Đã chuyển trách nhiệm xử lý sang hàng đợi retry bền vững; hoặc
- Xác định event cũ/trùng một cách đúng đắn.

Ghi sink rồi crash trước ACK có thể gây xử lý lặp. ACK trước khi ghi có thể gây mất thay đổi. Thiết kế phải chấp nhận và giải quyết cả hai.

## 19. Đo độ mới và tính đúng của bản sao

Một pipeline gồm:

~~~text
T0 nguồn commit
   |
T1 event vào broker
   |
T2 consumer nhận
   |
T3 sink xác nhận ghi
   |
T4 ứng dụng truy vấn thấy dữ liệu mới
~~~

**Freshness end-to-end = T4 - T0**, không chỉ là consumer lag.

### 19.1. Các metric quan trọng

| Nhóm | Metric | Mục đích |
|---|---|---|
| Thu nhận | CDC/outbox backlog, capture lag | Phát hiện event chưa rời nguồn |
| Broker | Oldest event age, lag theo partition | Phát hiện hàng đợi tồn đọng |
| Consumer | Success/s, retry/s, schema failure/s | Theo dõi tiến độ xử lý |
| Sink | Write errors, version conflicts, visibility lag | Kiểm tra trạng thái đã đọc thấy |
| Reconciler | Scanned IDs, mismatch rate, mismatch age | Đánh giá sai lệch thật |
| Repair | Repaired IDs, retry, verify failures | Biết khả năng tự phục hồi |
| DLQ | Count, oldest age, nguyên nhân | Phát hiện lỗi chưa giải quyết |
| Delete | Pending deletes, overdue deletes | Theo dõi nghĩa vụ xóa |
| Tài nguyên | CPU, I/O, băng thông, storage | Kiểm soát chi phí chạy nền |

Theo dõi theo tenant, loại thực thể, sink và projection version khi phù hợp. Một trung bình toàn hệ có thể che khuất một partition/tenant đang gặp sự cố.

### 19.2. SLO về độ mới

Ví dụ:

> Trong 30 ngày, 99,9% thay đổi trạng thái đơn hàng đã commit phải được nhìn thấy đúng trong danh sách của khách hàng trong 15 giây.

Để đo, phải kiểm tra **phiên bản và kết quả truy vấn thật ở sink**, không chỉ event đã ACK.

Một SLO khác:

> Sai lệch kéo dài quá 10 phút phải được phát hiện; các sai lệch có thể tự sửa phải được xử lý trong 30 phút.

Đây là ví dụ, không phải ngưỡng chung cho mọi hệ. SLO phải xác định đối tượng, lỗi được tính, cửa sổ và phương pháp đo.

### 19.3. Freshness và correctness khác nhau

Một consumer cập nhật sai giá **rất nhanh** có freshness tốt nhưng correctness kém. Một view cập nhật đúng giá sau 45 giây có correctness tốt nhưng freshness có thể không đạt SLO. Cần đo **cả hai**.

## 20. Quy trình vận hành từ phát hiện đến phục hồi

Một quy trình có thể gồm:

1. **Phát hiện:** alert, mismatch từ reconciler hoặc người dùng báo.
2. **Khoanh vùng:** loại thực thể, tenant, thời gian, partition, consumer bị lỗi.
3. **Bảo vệ nghiệp vụ:** nếu view sai ảnh hưởng quyền, tiền hoặc xác nhận đơn, chuyển sang nguồn authoritative hoặc chặn thao tác không an toàn.
4. **Xác định nguồn đúng:** trường/quan hệ nào có chủ sở hữu authoritative?
5. **Chọn chiến lược repair:** replay, per-ID, batch backfill hay rebuild.
6. **Giới hạn tải và quyền:** tránh gây quá tải và sửa sai phạm vi.
7. **Thực hiện có version guard:** chặn dữ liệu cũ ghi lùi.
8. **Verify:** đối soát sau sửa, xác nhận SLO.
9. **Tìm nguyên nhân gốc:** sửa luồng thiếu ACK, bug transform, xóa khóa cũ...
10. **Đề phòng tái diễn:** thêm metric, cảnh báo, kiểm thử lỗi và quy trình backfill.

### 20.1. Chọn mức độ ưu tiên

| Sai lệch | Ưu tiên minh họa | Hành động |
|---|---|---|
| Tên hiển thị chậm vài giây | Thấp | Theo dõi hội tụ |
| Search sản phẩm cũ vài phút | Trung bình | Retry/backfill, cảnh báo |
| Đơn đã hủy còn trong hàng xử lý | Cao | Xác minh nguồn khi hành động, repair ưu tiên |
| Quyền truy cập đã thu hồi nhưng view còn quyền | Rất cao | Không dựa vào view trễ, sửa khẩn |
| Hàng triệu tài liệu sai do mapping | Sự cố diện rộng | Dừng writer lỗi, rebuild/backfill |
| Dữ liệu phải xóa vẫn ở cache/index | Theo chính sách bảo mật | Lan truyền xóa và xác minh |

## 21. Ví dụ xuyên suốt: một đơn hàng sai ở bảng người bán

### 21.1. Trạng thái ban đầu

~~~text
Nguồn orders_by_id:
    O100 / status=SHIPPED / version=8

Customer view:
    U42/O100 / status=SHIPPED / version=8

Seller-status view:
    S9/PAID/O100     <-- sai
    S9/SHIPPED/O100  <-- đúng
~~~

Consumer đã thêm hàng SHIPPED nhưng xóa hàng PAID không thành công.

### 21.2. Reconciler phát hiện

Job đọc trạng thái authoritative O100 v8 và xác định bộ khóa expected:

~~~text
Expected:
    seller-status-key = S9/SHIPPED/O100

Actual:
    S9/PAID/O100
    S9/SHIPPED/O100
~~~

Để lấy các khóa actual của O100, hệ có thể dùng manifest, một index/ngược phù hợp hoặc quét phạm vi theo cách được thiết kế. Không được giả định mọi bảng wide-column tìm theo order ID hiệu quả khi thiếu partition key.

### 21.3. Repair thực hiện

1. Đọc lại O100 từ nguồn.
2. Xác minh nó vẫn ở v8 hoặc đã có v9 mới hơn.
3. Tính tập khóa expected theo trạng thái hiện tại.
4. Xóa khóa cũ bằng thao tác an toàn theo version/owner.
5. Upsert khóa đúng nếu thiếu.
6. Kiểm tra lại bộ khóa và nội dung.
7. Ghi nhận kết quả sửa.

Nếu trong quá trình đó O100 chuyển `DELIVERED v9`, repair từ snapshot SHIPPED v8 phải bị chặn hoặc đọc lại để tính trạng thái mới.

### 21.4. Sửa nguyên nhân

Sửa hàng cũ là bước phục hồi, chưa phải giải pháp cuối. Cần kiểm tra:

- Consumer có ACK trước khi xóa thành công không?
- Event có chứa đủ oldStatus không?
- Retry delete có được lưu bền vững không?
- Có version guard cho thao tác di chuyển key không?
- Có test cho failure giữa DELETE và INSERT không?

Nếu không khắc phục, cùng loại sai lệch sẽ xuất hiện trở lại.

## 22. Các sai lầm thường gặp

**“Có event stream thì dữ liệu chắc chắn đúng.”** Không. Event có thể bị bỏ sót, xử lý sai hoặc ACK sớm.

**“Consumer lag bằng 0 nghĩa là sink đã đồng bộ chính xác.”** Không. Sink có thể viết sai trường hoặc chưa hiển thị dữ liệu mới.

**“Chỉ cần cùng số bản ghi.”** Không. Hai tập có thể có ID khác nhau nhưng count bằng.

**“Version bằng nhau là nội dung giống nhau.”** Không nếu projector có bug, hoặc projection ghép nhiều nguồn phiên bản khác nhau.

**“Replay là cứ chạy lại mọi event.”** Không nếu thao tác không idempotent hoặc event cũ ghi đè dữ liệu mới.

**“Repair copy trạng thái nguồn mới nhất lên mọi trường.”** Không với snapshot lịch sử và bảng aggregate có quy tắc riêng.

**“Bảng theo status chỉ cần thêm hàng ở trạng thái mới.”** Không. Phải dọn khóa cũ nếu không muốn cùng ID xuất hiện trong nhiều partition.

**“Đối soát full scan càng thường xuyên càng tốt.”** Không nếu chi phí quét làm nghẽn nguồn. Cần chia bucket và giới hạn tải.

**“Xóa nguồn là đã xóa mọi bản sao.”** Không. Cache, index, bảng phi chuẩn hóa và kho khác có thể còn dữ liệu.

**“DLQ là nơi kết thúc xử lý lỗi.”** Không. Event trong DLQ vẫn phải được sửa/replay và đối soát.

**“Repair có thể ghi vô điều kiện vì đã đọc nguồn chuẩn.”** Không. Nguồn và view có thể đổi trong lúc repair; cần version guard.

## 23. Bài tập tự vận dụng

### Bài tập 1: vì sao dual write không đủ?

API ghi `Order.status=SHIPPED` thành công rồi crash trước khi phát event. View người bán vẫn có `PAID`.

**Câu hỏi:** Cơ chế nào giảm nguy cơ mất event? Đối soát có vai trò gì?

**Gợi ý:** Outbox trong transaction hoặc CDC từ thay đổi đã commit có thể giúp thu nhận đáng tin cậy. Đối soát phát hiện view vẫn cũ nếu pipeline bỏ sót.

### Bài tập 2: event sai thứ tự

Consumer nhận `O100 v9 DELIVERED` rồi `O100 v8 SHIPPED`.

**Câu hỏi:** Chỉ dedup bằng eventId có đủ không?

**Gợi ý:** Không, đây là hai event khác nhau. Cần version/ordering và conditional update tại sink.

### Bài tập 3: count bằng nhau

Nguồn có `A, B, C`; view có `A, B, D`. Hai bên đều có count=3.

**Câu hỏi:** So sánh gì tiếp theo?

**Gợi ý:** So tập ID để thấy C thiếu, D thừa; sau đó so version và nội dung.

### Bài tập 4: snapshot lịch sử

Đơn hàng lưu `priceAtPurchase=100`. Giá sản phẩm hiện tại là 120.

**Câu hỏi:** Reconciler có nên sửa giá trên đơn thành 120?

**Gợi ý:** Không nếu trường là snapshot khi mua. Phải so với chứng từ/lịch sử mua tại thời điểm đó.

### Bài tập 5: hàng cũ của status

Bảng người bán có cả `S9/PAID/O100` và `S9/SHIPPED/O100`, nhưng nguồn chỉ có `SHIPPED`.

**Câu hỏi:** Repair cần biết gì?

**Gợi ý:** Bộ khóa expected, bộ khóa thực tế hoặc manifest/oldStatus, version và quy tắc dọn khóa cũ.

### Bài tập 6: repair bị đua tranh

Repair đọc v8; consumer cập nhật v9; repair ghi v8.

**Câu hỏi:** Cơ chế nào ngăn trạng thái bị lùi?

**Gợi ý:** Conditional write theo sourceVersion hoặc xử lý tuần tự có bảo đảm tương đương.

### Bài tập 7: full scan gây quá tải

Nguồn có 50 triệu bản ghi. Mỗi lần đối soát toàn bộ làm I/O tăng mạnh.

**Câu hỏi:** Tổ chức lại job thế nào?

**Gợi ý:** Chia theo hash bucket/tenant/ngày, giới hạn concurrency, ưu tiên ID lỗi/mới thay đổi, full scan luân phiên theo lịch và lưu checkpoint.

### Bài tập 8: lỗi trong DLQ

Consumer không hiểu schemaVersion=3 và gửi 3.000 event vào DLQ, rồi tiếp tục xử lý event khác.

**Câu hỏi:** Hệ thống đã hoàn tất đồng bộ chưa?

**Gợi ý:** Chưa. Phải sửa consumer, replay có idempotency/version guard, rồi đối soát những ID bị ảnh hưởng.

### Bài tập 9: tính độ trễ toàn tuyến

Nguồn commit lúc 10:00:00; broker nhận lúc 10:00:02; consumer ACK lúc 10:00:05; search đọc thấy lúc 10:00:11.

**Câu hỏi:** End-to-end freshness là bao nhiêu? Vì sao không dùng thời gian ACK?

**Gợi ý:** 11 giây. ACK chưa bao gồm toàn bộ thời gian nguồn–broker và visibility ở đích.

### Bài tập 10: quan hệ đảo chiều

Nguồn chuẩn nói U1 không còn dùng D7. `devices_by_user` đã xóa cạnh, nhưng `users_by_device` vẫn chứa U1–D7.

**Câu hỏi:** Cần đối soát những gì?

**Gợi ý:** Tập quan hệ theo nguồn chuẩn, hai bảng đảo chiều, version và bước xóa còn thiếu. Không chỉ so số node.

## 24. Kết luận

Trong kiến trúc NoSQL có **quan hệ và dữ liệu lặp**, mỗi đường đọc tối ưu hóa cho một truy vấn nhưng phải duy trì đúng ý nghĩa của dữ liệu gốc. **Change event** giúp bản sao theo kịp thay đổi, **đối soát định kỳ** phát hiện các sai lệch còn tồn tại, còn **repair** giúp tự phục hồi khi event bị mất, trùng, đến muộn hoặc có lỗi biến đổi.

Một hệ thống đáng tin cậy cần biết **nguồn sự thật của từng trường, hợp đồng projection, khóa và phiên bản ổn định, idempotency, thứ tự cập nhật, tombstone, cách kiểm tra theo mốc, checkpoint, DLQ và chiến lược rebuild**. Đặc biệt, trong bảng có khóa theo quan hệ/trạng thái, sửa đúng đôi khi nghĩa là **xóa hàng ở khóa cũ rồi thêm hàng ở khóa mới**, chứ không chỉ đổi một giá trị.

Khả năng **phát hiện, giải thích và sửa sai lệch** nên được thiết kế ngay khi quyết định lặp dữ liệu. Nhờ vậy, kiến trúc nhiều read model có thể đạt hiệu năng tốt mà vẫn giữ khả năng vận hành, đối soát và phục hồi sau sự cố.

