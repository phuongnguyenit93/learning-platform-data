# Phân trang bằng offset, token hoặc khóa tiếp nối

## 1. Vì sao phân trang là một phần của thiết kế truy vấn NoSQL?

Một ứng dụng có thể lưu hàng triệu đơn hàng, bài đăng, sự kiện hoặc tài liệu. Người dùng hiếm khi cần nhận toàn bộ dữ liệu trong một response. Thay vào đó, ứng dụng trả một nhóm nhỏ:

- 20 đơn hàng mới nhất của một khách hàng;
- 50 sự kiện gần nhất của thiết bị;
- 10 sản phẩm tìm kiếm phù hợp nhất;
- 100 tài liệu để worker xử lý theo lô;
- 30 bài đăng tiếp theo khi người dùng cuộn màn hình.

**Phân trang (pagination)** là cách chia một tập kết quả lớn thành những phần có kích thước giới hạn để truy xuất lần lượt. Nó liên quan trực tiếp tới **CRUD và truy vấn** vì cách viết điều kiện lọc, lựa chọn index, khóa phân vùng và thứ tự sắp xếp quyết định việc sang trang tiếp theo có nhanh và đúng hay không.

Có ba cách tiếp cận thường gặp:

1. **Offset pagination:** bỏ qua một số lượng bản ghi đầu rồi lấy một trang.
2. **Continuation token / paging token:** để database hoặc ứng dụng trả một token đại diện cho vị trí tiếp tục; client dùng token này trong lần truy vấn sau.
3. **Keyset / seek pagination:** dùng giá trị khóa sắp xếp của hàng cuối cùng đã hiển thị để tìm các hàng đứng sau nó.

Ba cách **không hoàn toàn loại trừ nhau**. Ví dụ một API có thể trả token opaque mà bên trong chứa chính khóa tiếp nối của keyset. Một database khác trả token trạng thái thực thi đặc thù của engine, không thể quy nó thành một ID đơn giản.

### 1.1. Ví dụ xuyên suốt

Giả sử hệ thống lưu sự kiện theo tenant, mỗi event có:

```json
{
  "eventId": "E105",
  "tenantId": "T1",
  "occurredAt": "2026-11-14T08:05:00Z",
  "type": "LOGIN",
  "severity": "INFO",
  "message": "Đăng nhập thành công"
}
```

Màn hình hiển thị sự kiện mới nhất trước:

| Vị trí | eventId | occurredAt (UTC) |
|---:|---|---|
| 1 | E105 | 08:05 |
| 2 | E104 | 08:04 |
| 3 | E103 | 08:03 |
| 4 | E102 | 08:02 |
| 5 | E101 | 08:01 |
| 6 | E100 | 08:00 |

Với `pageSize = 2`:

```text
Trang 1: E105, E104
Trang 2: E103, E102
Trang 3: E101, E100
```

Đây chỉ là một ảnh chụp dữ liệu lúc bắt đầu. Trong hệ thống thực, event mới có thể được ghi vào bất cứ lúc nào. Chính điều đó làm các kiểu phân trang có hành vi khác nhau.

## 2. Trước khi chọn cách phân trang: xác định hợp đồng kết quả

Một API phân trang cần trả lời rõ những câu hỏi:

- **Phạm vi:** dữ liệu của tenant, user hoặc partition nào?
- **Filter:** trạng thái, loại event, khoảng thời gian nào?
- **Order:** sắp xếp theo trường nào, tăng hay giảm?
- **Kích thước trang:** một lần trả tối đa bao nhiêu record?
- **Tiếp tục:** client cung cấp số trang, offset, token hay khóa?
- **Dữ liệu thay đổi:** có phải nhìn đúng một snapshot cố định hay chấp nhận danh sách động?
- **Kết thúc:** xác định hết dữ liệu bằng cách nào?
- **Tổng số:** có bắt buộc biết chính xác bao nhiêu kết quả hay không?
- **Bảo mật:** client có được thay token để đọc dữ liệu tenant khác không?

Một quyết định quan trọng là **thứ tự phải có tính xác định**.

### 2.1. Chỉ ORDER BY thời gian thường chưa đủ

Giả sử hai event cùng có `occurredAt = 08:04:00Z`:

```text
E104A 08:04:00
E104B 08:04:00
```

Nếu chỉ sắp xếp theo `occurredAt DESC`, thứ tự tương đối giữa E104A và E104B có thể không ổn định. Khi phân trang, một event có thể xuất hiện ở hai trang hoặc bị bỏ sót, tùy engine và dữ liệu.

Một thứ tự xác định nên dùng **khóa phụ duy nhất**:

```text
ORDER BY occurredAt DESC, eventId DESC
```

Nếu `eventId` thực sự duy nhất trong tập cần truy vấn, mỗi cặp `(occurredAt, eventId)` có một vị trí xác định. Không nhất thiết phải dùng ID mang ý nghĩa thời gian; nó chỉ cần so sánh ổn định và đủ để phân biệt hàng cùng timestamp.

### 2.2. Bộ lọc và thứ tự là một phần của “danh sách”

Hai truy vấn khác nhau:

```text
tenant=T1, severity=ERROR, sort=occurredAt DESC
tenant=T1, severity=INFO,  sort=occurredAt DESC
```

không dùng chung vị trí tiếp tục. Một token tạo cho bộ lọc `ERROR` không được tự động dùng để đọc tiếp bộ lọc `INFO`.

Tương tự, thay `DESC` thành `ASC` hoặc đổi search query có thể khiến vị trí cũ không còn ý nghĩa.

### 2.3. Giới hạn trang để bảo vệ hệ thống

Nếu client có thể yêu cầu `pageSize=1000000`, chỉ thêm phân trang chưa đủ tránh trả quá nhiều dữ liệu. Nên đặt:

```text
defaultPageSize = 20
maximumPageSize = 100
```

Các con số chỉ minh họa. Server cần giới hạn tại tầng API và hiểu các giới hạn riêng của database, ví dụ page response tối đa theo byte, timeout hay RU.

## 3. Offset pagination: bỏ qua N bản ghi đầu

### 3.1. Ý tưởng

Offset pagination dùng hai tham số:

- `offset`: số record đứng trước trang cần đọc;
- `limit`: số record tối đa muốn lấy.

Với trang đánh số từ 1:

\[
offset = (pageNumber - 1) \times pageSize
\]

Giả sử `pageSize = 2`:

| Trang | offset | limit | Kết quả lúc dữ liệu đứng yên |
|---:|---:|---:|---|
| 1 | 0 | 2 | E105, E104 |
| 2 | 2 | 2 | E103, E102 |
| 3 | 4 | 2 | E101, E100 |

Ví dụ SQL để hình dung:

```sql
SELECT event_id, occurred_at, message
FROM events
WHERE tenant_id = 'T1'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2 OFFSET 2;
```

Truy vấn trên lấy trang thứ hai với dữ liệu theo thứ tự đã định.

### 3.2. Ví dụ MongoDB với skip và limit

MongoDB hỗ trợ `skip()`, `limit()` và `sort()`:

```javascript
const pageNumber = 3;
const pageSize = 20;
const offset = (pageNumber - 1) * pageSize;

const events = db.events.find({
  tenantId: "T1",
  severity: "ERROR"
})
.sort({ occurredAt: -1, _id: -1 })
.skip(offset)
.limit(pageSize)
.toArray();
```

Ở đây `_id` được dùng làm khóa phụ duy nhất. Để sắp xếp theo thời gian đáng tin cậy, các document cần lưu `occurredAt` với kiểu dữ liệu thống nhất, ví dụ BSON Date.

### 3.3. Vì sao offset lớn thường đắt?

Giả sử người dùng muốn trang 10.000, mỗi trang 20 bản ghi:

\[
offset = (10000 - 1) \times 20 = 199980
\]

Hệ quản trị có thể phải duyệt và bỏ qua một đoạn rất dài trước khi trả 20 bản ghi cần thiết. Dù truy vấn có index hỗ trợ sắp xếp, việc **di chuyển qua gần 200.000 vị trí** vẫn có thể tốn công.

Một ước lượng tư duy:

\[
work \propto offset + limit
\]

Đây không phải định luật độ phức tạp chính xác cho mọi engine, nhưng minh họa vì sao **deep pagination** bằng offset thường ngày càng chậm. Chi phí thực còn phụ thuộc index, độ chọn lọc, plan, phân vùng, bộ nhớ và cách database xử lý `skip`.

### 3.4. Offset có những ưu điểm gì?

- Dễ hiểu đối với người dùng: trang 1, 2, 3.
- Dễ xây UI có số trang khi tập kết quả nhỏ hoặc khá ổn định.
- Có thể nhảy thẳng tới trang 10 nếu database hỗ trợ.
- Đơn giản để kiểm thử khi dữ liệu cố định.
- Hữu ích cho trang quản trị có tập kết quả giới hạn và index phù hợp.

Không nên xem offset là “sai” trong mọi hoàn cảnh. Nó là lựa chọn hợp lý khi chi phí bỏ qua được kiểm soát và UI thật sự cần điều hướng ngẫu nhiên theo số trang.

### 3.5. Nhưng nhiều NoSQL không có OFFSET tổng quát

Cassandra Query Language (CQL) không cung cấp một phép `OFFSET` tổng quát tương đương SQL cho các truy vấn thông thường. DynamoDB Query cũng không có tham số offset để bỏ qua N item đã khớp. Những hệ này thường dùng **paging state / continuation key**.

Nếu ứng dụng tự gọi database nhiều trang rồi bỏ dữ liệu cho đến vị trí mong muốn, nó vẫn phải trả chi phí đọc và truyền qua những trang trước đó, thậm chí còn đắt hơn offset được hỗ trợ trực tiếp.

## 4. Dữ liệu thay đổi làm offset bị trùng hoặc bỏ sót thế nào?

Offset đếm **vị trí hiện tại**, không ghi nhớ một bản ghi cụ thể.

### 4.1. Chèn bản ghi mới trước đầu danh sách

Ban đầu:

```text
[E105, E104, E103, E102, E101, E100]
```

Client đọc trang 1 với `offset=0, limit=2`:

```text
Trang 1 -> [E105, E104]
```

Ngay sau đó có E106 mới, danh sách thành:

```text
[E106, E105, E104, E103, E102, E101, E100]
```

Client tiếp tục trang 2 bằng `offset=2, limit=2`:

```text
Trang 2 -> [E104, E103]
```

**E104 bị lặp** vì nó dịch từ vị trí 2 xuống vị trí 3. Client không thay đổi offset sai; tập kết quả đã thay đổi.

### 4.2. Xóa bản ghi phía trước

Ban đầu client đọc:

```text
Trang 1 -> [E105, E104]
```

Sau đó E105 bị xóa:

```text
[E104, E103, E102, E101, E100]
```

Trang 2 với `offset=2`:

```text
Trang 2 -> [E102, E101]
```

**E103 bị bỏ sót** vì xóa ở đầu danh sách làm các vị trí dịch lên.

### 4.3. Kết luận về tính nhất quán

Offset pagination **không cố định tập kết quả theo thời điểm đầu**. Nếu mục tiêu là một ảnh chụp ổn định, cần cơ chế snapshot/PIT hoặc một chiến lược nhất quán khác phù hợp với database.

Đổi sang keyset giúp tránh một số lỗi dịch vị trí nhưng **không tự bảo đảm snapshot hoàn hảo** nếu dữ liệu có thể thay đổi sort key hoặc bị xóa.

## 5. Keyset/seek pagination: dùng khóa của hàng cuối cùng

### 5.1. Ý tưởng

Thay vì yêu cầu “bỏ qua 20 hàng”, client nói:

> “Tôi đã xem đến E104, có thời điểm 08:04. Hãy lấy những hàng đứng sau khóa `(08:04, E104)` theo đúng thứ tự.”

Nếu sắp xếp giảm dần theo `occurredAt` và `eventId`, hàng đứng sau phải có:

\[
occurredAt < lastOccurredAt
\]

hoặc khi trùng thời điểm:

\[
occurredAt = lastOccurredAt \land eventId < lastEventId
\]

Gộp lại:

\[
(occurredAt < t)\ \lor\
(occurredAt=t \land eventId < id)
\]

Đây là so sánh **từ điển (lexicographic comparison)** theo đúng thứ tự sắp xếp giảm dần.

### 5.2. Ví dụ trang thứ hai

Trang 1:

```text
E105 08:05
E104 08:04
```

Khóa tiếp nối là:

```json
{
  "lastOccurredAt": "2026-11-14T08:04:00Z",
  "lastEventId": "E104"
}
```

Truy vấn kế tiếp chọn những bản ghi có khóa đứng sau E104:

```text
E103 08:03
E102 08:02
```

Nếu E106 vừa được thêm vào đầu danh sách, nó **không làm E104 dịch vị trí trong biểu thức so sánh**. Truy vấn vẫn bắt đầu sau `(08:04, E104)`.

### 5.3. Vì sao phải có tie-breaker duy nhất?

Nếu chỉ dùng:

```text
WHERE occurredAt < lastOccurredAt
```

và có nhiều event cùng thời điểm cuối trang, các event cùng timestamp còn lại sẽ bị bỏ sót.

Ví dụ:

```text
E105 08:05
E104 08:04
E103 08:04
E102 08:03
```

Trang 1 trả E105 và E104. Nếu trang 2 chỉ lọc `occurredAt < 08:04`, E103 biến mất. Có `eventId` trong điều kiện, trang 2 vẫn có thể bắt đầu bằng E103.

Một khóa tiếp nối phải phản ánh **toàn bộ trường làm nên thứ tự xác định**.

## 6. Keyset bằng MongoDB: truy vấn và index

Giả sử collection `events` có:

- `tenantId`;
- `severity`;
- `occurredAt` kiểu BSON Date;
- `_id` duy nhất.

Truy vấn UI cần 20 event ERROR mới nhất của tenant T1.

### 6.1. Index phù hợp

```javascript
db.events.createIndex({
  tenantId: 1,
  severity: 1,
  occurredAt: -1,
  _id: -1
});
```

Các trường bằng nhau (`tenantId`, `severity`) đứng trước hai trường dùng để sắp xếp. Đây là một thiết kế index **đáng xem xét** cho mẫu truy vấn này; hiệu quả thực tế cần kiểm tra bằng `explain()` và phân phối dữ liệu thật.

### 6.2. Truy vấn trang đầu

```javascript
const pageSize = 20;

const firstPage = db.events.find({
  tenantId: "T1",
  severity: "ERROR"
})
.sort({ occurredAt: -1, _id: -1 })
.limit(pageSize + 1)
.toArray();
```

Lấy `pageSize + 1` là một cách thường dùng để biết có khả năng còn dữ liệu phía sau mà không cần truy vấn `COUNT`. Nếu lấy 21 record, hiển thị 20 và dùng record thứ 21 chỉ để xác định `hasMore = true`.

**Token phải lấy từ record thứ 20 (hàng cuối đã hiển thị), không lấy record thứ 21.** Nếu lấy khóa của record peek-ahead, lần đọc tiếp có thể bỏ qua chính record đó.

### 6.3. Truy vấn trang kế tiếp

Giả sử trang trước kết thúc ở:

```javascript
const lastOccurredAt = ISODate("2026-11-14T08:04:00Z");
const lastId = ObjectId("691829000000000000000004");
```

Nếu collection dùng `_id` kiểu ObjectId, các giá trị so sánh cũng phải được giải mã đúng thành ObjectId; không so bằng chuỗi tùy tiện.

```javascript
const nextPage = db.events.find({
  tenantId: "T1",
  severity: "ERROR",
  $or: [
    { occurredAt: { $lt: lastOccurredAt } },
    {
      occurredAt: lastOccurredAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ occurredAt: -1, _id: -1 })
.limit(pageSize + 1)
.toArray();
```

Các điều kiện trên đúng với sort `occurredAt DESC, _id DESC`. Nếu sort tăng dần, hướng so sánh thay đổi; nếu một trường ASC và một trường DESC, công thức cũng phải được xây lại theo thứ tự hỗn hợp.

### 6.4. Không phụ thuộc vào thứ tự mặc định của database

`find()` không có `sort()` không phải hợp đồng thứ tự ổn định cho phân trang. Thứ tự lưu trữ/natural order có thể thay đổi và không đủ ý nghĩa nghiệp vụ.

Ngay cả khi `_id` có vẻ tăng theo thời gian, không nên suy rằng mọi `ObjectId` luôn phản ánh thứ tự commit toàn cục giữa nhiều máy. Khi muốn sắp xếp theo thời điểm nghiệp vụ, hãy lưu và index thời điểm đó, cùng khóa tie-break.

### 6.5. Null và dữ liệu thiếu trường

Nếu một số document thiếu `occurredAt`, biểu thức so sánh theo Date có thể không bao phủ chúng như mong muốn. Trước khi dùng keyset:

- Bảo đảm trường sort có mặt hoặc xác định cách sắp xếp null/missing;
- Chuẩn hóa kiểu dữ liệu;
- Xác định collation cho chuỗi;
- Đảm bảo khóa phụ duy nhất trong phạm vi truy vấn.

Một khóa tiếp nối chỉ đúng khi **ngữ nghĩa sắp xếp và so sánh giữa các trang không thay đổi**.

## 7. Offset và keyset khác nhau ra sao về chi phí?

Giả sử số record phù hợp là 10 triệu, `pageSize = 20`.

| Tiêu chí | Offset | Keyset |
|---|---|---|
| Trang đầu | Đơn giản | Đơn giản |
| Trang sâu | Có thể phải bỏ qua rất nhiều record | Có thể seek từ khóa neo nhờ index |
| Nhảy trực tiếp đến trang N | Thuận tiện nếu API hỗ trợ | Không tự nhiên nếu chưa có khóa neo |
| Thêm bản ghi trước danh sách | Có thể lặp bản ghi | Không làm dịch vị trí của khóa đã xem |
| Xóa bản ghi trước danh sách | Có thể bỏ sót bản ghi | Không phụ thuộc số lượng bản ghi trước anchor |
| Đổi sort key của một record | Có thể gây trùng/bỏ sót | Vẫn có thể gây trùng/bỏ sót |
| Yêu cầu thứ tự xác định | Có | Đặc biệt quan trọng |
| Hỗ trợ NoSQL | Không đồng nhất | Tùy khả năng so sánh/index và khóa |
| Cách hiển thị UI | Trang 1, 2, 3 | “Tải thêm” / infinite scroll |
| Tổng số trang | Có thể cần count | Không nhất thiết có count |

Keyset thường đặc biệt phù hợp cho **timeline/feed, lịch sử sự kiện, danh sách mới nhất trước** khi đã có index theo khóa sort. Không có nghĩa keyset luôn nhanh: nếu truy vấn xuyên hàng nghìn partition hoặc không có index, chi phí vẫn có thể cao.

## 8. Continuation token: trạng thái tiếp nối do hệ quản trị hoặc ứng dụng cấp

### 8.1. Token không nhất thiết là offset hoặc một ID

Một continuation token thường là một chuỗi opaque:

```json
{
  "items": [
    {"eventId": "E105"},
    {"eventId": "E104"}
  ],
  "nextToken": "eyJ2IjoxLCJjdXJzb3IiOiIuLi4ifQ..."
}
```

Client **không cần hiểu nội dung token**. Nó chỉ lưu token và gửi lại:

```text
GET /events?tenantId=T1&pageSize=20
       |
       v
200 OK + nextToken="abc..."

GET /events?tenantId=T1&pageSize=20&pageToken=abc...
       |
       v
200 OK + nextToken="def..."
~~~

Token có thể chứa:

- Khóa cuối cùng đã đọc;
- Vị trí trong một index hoặc partition;
- Paging state của query executor;
- Offset hoặc continuation metadata nội bộ;
- ID một snapshot/PIT;
- Thông tin về những partition đã duyệt;
- Một con trỏ do server lưu trạng thái ở nơi khác.

**Không được giả định token của mọi database có cùng định dạng hoặc có thể tự tạo bằng Base64(ID).**

### 8.2. Token của database và token API khác nhau

Có thể có hai lớp:

```text
Client
  |
  | pageToken của ứng dụng
  v
Backend API
  |
  | paging state / LastEvaluatedKey / search_after
  v
Database
~~~

Backend có thể đóng gói token của database cùng phiên bản API, filter và thông tin bảo mật để tạo một **public token** cho client.

Không nên phơi bày trực tiếp token nội bộ của database nếu nó chứa thông tin nhạy cảm hoặc không an toàn để cho client tùy ý sửa. Với một số hệ, paging state còn được xem như input không đáng tin cậy cần kiểm soát chống tampering.

### 8.3. Không có nextToken nghĩa là gì?

Thông thường khi API trả `nextToken = null` hoặc không có trường này, ứng dụng coi đó là kết thúc. Nhưng chi tiết của từng database khác nhau:

- Token tồn tại có thể chỉ cho biết **có khả năng cần tiếp tục**, không chắc trang sau có record trả về.
- Một trang có thể **rỗng nhưng vẫn có token** do filtering được áp dụng sau giai đoạn đọc.
- Các service có giới hạn theo dung lượng/chi phí nên một trang có thể trả ít hơn `pageSize`.

Do đó, ở API chuyển tiếp token từ một database, đừng suy `items.length < pageSize` là chắc chắn hết dữ liệu.

## 9. DynamoDB: LastEvaluatedKey và ExclusiveStartKey

DynamoDB Query và Scan thường phân trang bằng **`LastEvaluatedKey`** và **`ExclusiveStartKey`**.

### 9.1. Ví dụ bảng lịch sử theo user

Giả sử bảng `OrdersByCustomer`:

```text
Partition key : customerId
Sort key      : createdAtOrderId
Attributes    : status, totalCents, ...
~~~

`createdAtOrderId` là khóa sort được thiết kế có thứ tự ổn định và tránh trùng, ví dụ chuỗi timestamp UTC định dạng cố định cộng ID phân biệt.

Đường truy vấn:

```text
Query:
  customerId = "U42"
  ScanIndexForward = false
  Limit = 20
~~~

Nếu câu trả lời chứa `LastEvaluatedKey`, client có thể tiếp tục Query với chính giá trị đó trong `ExclusiveStartKey`.

### 9.2. Request minh họa dạng JSON

Trang đầu:

```json
{
  "TableName": "OrdersByCustomer",
  "KeyConditionExpression": "customerId = :customer",
  "ExpressionAttributeValues": {
    ":customer": {"S": "U42"}
  },
  "ScanIndexForward": false,
  "Limit": 20
}
```

Nếu response có:

```json
{
  "Items": [
    {"customerId": {"S": "U42"}, "createdAtOrderId": {"S": "2026-11-14T08:05:00Z#O105"}}
  ],
  "LastEvaluatedKey": {
    "customerId": {"S": "U42"},
    "createdAtOrderId": {"S": "2026-11-14T07:40:00Z#O085"}
  }
}
```

thì lần tiếp theo gửi:

```json
{
  "TableName": "OrdersByCustomer",
  "KeyConditionExpression": "customerId = :customer",
  "ExpressionAttributeValues": {
    ":customer": {"S": "U42"}
  },
  "ScanIndexForward": false,
  "Limit": 20,
  "ExclusiveStartKey": {
    "customerId": {"S": "U42"},
    "createdAtOrderId": {"S": "2026-11-14T07:40:00Z#O085"}
  }
}
```

Các item trong response được rút gọn để minh họa. Trong API thật, `LastEvaluatedKey` phải được lấy nguyên vẹn từ response của lần truy vấn trước theo đúng kiểu DynamoDB `AttributeValue`, không tự suy từ một trường hiển thị.

### 9.3. Giới hạn kích thước response

DynamoDB Query đọc tối đa một lượng dữ liệu theo giới hạn service, thường có ngưỡng **1 MB cho một lần Query** trước khi phải tiếp tục. Vì vậy số item trả về có thể ít hơn `Limit` do giới hạn theo byte.

Ngoài ra, `Limit` của Query giới hạn số item được đánh giá trong lần thực thi, không nhất thiết bằng số item còn lại sau `FilterExpression`.

### 9.4. Trang rỗng nhưng chưa phải kết thúc

Ví dụ 20 item đầu đều bị `FilterExpression` loại bỏ:

```text
DynamoDB đọc/đánh giá 20 item
    |
    v
FilterExpression loại hết
    |
    v
Items = []
LastEvaluatedKey = {...}
~~~

Nếu ứng dụng dừng khi `Items.length == 0`, nó có thể bỏ sót dữ liệu khớp ở phía sau.

Quy tắc ứng dụng: **tiếp tục theo `LastEvaluatedKey` cho đến khi không còn token**, hoặc đến giới hạn công việc phù hợp; khi trả API ra ngoài cần kiểm soát số vòng/trang rỗng để tránh một request backend quét quá nhiều dữ liệu.

### 9.5. Consistency và GSI

DynamoDB Query trên bảng/index có các lựa chọn nhất quán khác nhau. Đặc biệt, **Global Secondary Index (GSI)** có cơ chế cập nhật bất đồng bộ và không hỗ trợ strong consistent reads như bảng cơ sở trong những ngữ cảnh tương ứng.

Dù có strong read cho từng lần Query nơi được hỗ trợ, nhiều lần phân trang vẫn **không tự tạo một snapshot transaction duy nhất** của toàn danh sách.

### 9.6. Chi phí đọc không chỉ là số Items trả về

FilterExpression áp dụng sau giai đoạn đọc cho Query/Scan, nên một trang trả 5 item vẫn có thể tiêu tốn tài nguyên đọc nhiều item hơn. Thiết kế **partition key, sort key và KeyConditionExpression** phù hợp quan trọng hơn việc thêm filter rồi chờ phân trang tự tối ưu.

## 10. Cassandra: paging state của driver, không có OFFSET tổng quát

Trong Cassandra, dữ liệu thường được thiết kế theo query-first:

```sql
CREATE TABLE events_by_user_day (
    user_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((user_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Một truy vấn thuận lợi biết partition key:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_user_day
WHERE user_id = ?
  AND event_day = ?;
```

### 10.1. Page size ở driver và LIMIT trong CQL

**CQL `LIMIT`** giới hạn tổng số hàng của truy vấn trong ngữ cảnh tương ứng.

**Driver page size/fetch size** điều khiển số hàng driver cố lấy trong mỗi trang kết quả trên đường truyền.

Hai khái niệm không giống nhau. Nếu truy vấn được giới hạn tổng cộng 100 hàng và page size là 20, driver có thể tải nhiều trang để nhận tối đa 100 hàng, tùy dữ liệu và điều kiện.

### 10.2. Paging state

Driver Cassandra có thể trả **paging state** sau một phần kết quả. Client tiếp tục bằng paging state trong yêu cầu tương thích.

Giả mã:

```text
statement = queryByUserDay(userId, day)
statement.pageSize = 20

if pageToken exists:
    statement.pagingState = restoreOpaquePagingState(pageToken)

resultPage = execute(statement)

items = resultPage.currentPage
nextToken = encodePagingState(resultPage.nextPagingState)
~~~

Đây là giả mã không ràng buộc một phiên bản driver Java cụ thể. API thực tế khác nhau giữa driver và chế độ đồng bộ/bất đồng bộ.

### 10.3. Không ghép paging state thủ công

Paging state là trạng thái kỹ thuật của driver/database. Không nên:

- Đoán nó chứa row ID nào;
- Tự sửa byte;
- Tái sử dụng cho một câu truy vấn khác;
- Dùng token cũ sau khi đổi partition key/filter/sort;
- Cho rằng nó đại diện một snapshot cố định.

Khi đưa paging state ra API công khai, nên dùng cơ chế an toàn do driver/ứng dụng hỗ trợ. Trạng thái phân trang không được xem như nguồn dữ liệu đáng tin cậy chỉ vì do client gửi lại.

### 10.4. Chuyển sang ngày khác

Nếu partition key là `(user_id, event_day)`, paging state của ngày D không tự động tiếp tục sang partition ngày D−1 như một timeline vô hạn.

Muốn hiện “100 sự kiện mới nhất qua nhiều ngày”, backend có thể:

1. Truy vấn ngày gần nhất.
2. Tiếp tục paging state trong partition đó.
3. Khi hết, chuyển sang ngày trước.
4. Trả một token API chứa thông tin ngày hiện tại và paging state tương ứng.

Nếu truy vấn song song nhiều ngày để gộp, token phải quản lý trạng thái từng partition và thứ tự merge, không chỉ một page number.

### 10.5. Dữ liệu thay đổi giữa các trang

Cassandra paging state không tự đảm bảo snapshot isolation xuyên nhiều lần gọi. Insert/update/delete, TTL và compaction có thể làm dữ liệu giữa các trang thay đổi. Nếu nghiệp vụ cần đọc một tập nhất quán cố định, phải đánh giá kiến trúc snapshot/export hoặc cơ chế khác, không chỉ lưu paging state.

## 11. Azure Cosmos DB for NoSQL: continuation token theo query

Azure Cosmos DB for NoSQL hỗ trợ phân trang truy vấn qua **continuation token** được SDK/query engine cung cấp.

Một truy vấn khái niệm:

```sql
SELECT c.id, c.createdAt, c.status
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
```

Backend đọc một page bằng SDK rồi lấy continuation token tương ứng, sau đó dùng lại để đọc tiếp **cùng truy vấn và các lựa chọn phù hợp**.

### 11.1. Không lấy “số items” làm điều kiện kết thúc

Số item trong page có thể chịu giới hạn thực thi, tài nguyên, response, partition và cấu hình `MaxItemCount`. Một page nhỏ hơn số dự kiến không tự chứng minh hết dữ liệu; cần dựa vào token/trạng thái SDK.

### 11.2. Token thường gắn với ngữ cảnh truy vấn

Nếu client đổi `tenantId` hoặc thay `ORDER BY`, token cũ không được sử dụng như vị trí của truy vấn mới. Backend cần kiểm tra/bind token với định nghĩa truy vấn đã phát hành.

### 11.3. Chi phí RU và cross-partition

Một truy vấn theo partition key rõ ràng thường có hướng truy cập khác với truy vấn xuyên nhiều partition. Continuation token giúp tiếp tục tiến độ nhưng **không tự giảm chi phí quét/sắp xếp cross-partition**.

Khi truy vấn nhiều partition và sort toàn cục, query engine có thể phải quản lý trạng thái tiếp tục phức tạp hơn một khóa đơn. Vì vậy không nên parse token để suy luận nó tương đương `lastId`.

### 11.4. Snapshot không đến từ token một cách mặc định

Dữ liệu Cosmos DB có thể thay đổi giữa các lần gọi. Continuation token giúp tiếp tục query theo cơ chế engine, không mặc định cố định một ảnh chụp toàn bộ kết quả trong thời gian dài. Nếu cần consistency cao hơn, phải xét mô hình dữ liệu và bảo đảm cụ thể của dịch vụ.

## 12. Cloud Firestore: startAfter và document cursor

Firestore cho phép phân trang query bằng cursor như `startAfter()` hoặc `startAt()`.

Giả sử collection `events` và truy vấn theo tenant:

```javascript
const baseQuery = db.collection("events")
  .where("tenantId", "==", "T1")
  .orderBy("occurredAt", "desc")
  .limit(20);

const snapshot = await baseQuery.get();
const docs = snapshot.docs;
```

Ví dụ dùng Firestore Node.js SDK ở môi trường đã thiết lập `db`. Index yêu cầu có thể khác tùy filter/order và database có thể hướng dẫn tạo composite index.

### 12.1. Lấy trang tiếp bằng DocumentSnapshot

```javascript
const lastDoc = docs[docs.length - 1];

const nextSnapshot = await db.collection("events")
  .where("tenantId", "==", "T1")
  .orderBy("occurredAt", "desc")
  .startAfter(lastDoc)
  .limit(20)
  .get();
```

`startAfter(lastDoc)` dùng document snapshot làm cursor, giúp tránh một số trường hợp mơ hồ so với chỉ truyền timestamp khi có nhiều document cùng giá trị. Cần sử dụng cùng bộ lọc và thứ tự.

### 12.2. Cursor dựa trên giá trị sắp xếp

Firestore cũng có dạng `startAfter(value1, value2, ...)` phù hợp với các `orderBy` đã khai báo.

Nếu chỉ truyền `lastOccurredAt` mà nhiều document cùng thời điểm, vị trí có thể không đủ phân biệt. Nên thêm thứ tự bằng khóa tài liệu hoặc dùng document snapshot theo khả năng SDK.

### 12.3. Hạn chế cần nhớ

- `orderBy("occurredAt")` có những ngữ nghĩa đối với document thiếu trường đó; dữ liệu thiếu sort field có thể không được truy vấn như kỳ vọng.
- Query có thể yêu cầu composite index phù hợp.
- Các thay đổi dữ liệu giữa những lần `get()` không mặc định tạo snapshot xuyên toàn bộ phiên phân trang.
- Có thể xảy ra duplicate/missing nếu trường sắp xếp thay đổi trong khi client cuộn.
- Nếu lưu cursor của document snapshot để tiếp tục nhiều giờ sau, cần xét việc document có thể bị xóa; API public nên có chiến lược token dựa trên giá trị và hợp đồng rõ ràng khi cần.

## 13. Elasticsearch/OpenSearch: from/size và search_after

Search engine có hai tình huống đáng phân biệt:

1. Trang kết quả nông với `from`/`size`.
2. Phân trang sâu/duyệt nhiều kết quả bằng `search_after` hoặc cơ chế chuyên dụng.

### 13.1. from/size

Ví dụ Elasticsearch:

```json
{
  "from": 20,
  "size": 10,
  "query": {
    "term": { "tenantId": "T1" }
  },
  "sort": [
    { "createdAt": "desc" },
    { "eventId.keyword": "desc" }
  ]
}
```

Ý tưởng tương tự offset: bỏ qua 20 kết quả đứng đầu, lấy 10.

Elasticsearch có giới hạn độ sâu `from + size` thông qua `index.max_result_window`, **mặc định thường là 10.000**. Tăng giới hạn tùy ý có thể khiến truy vấn tốn tài nguyên, nhất là khi nhiều shard cần giữ nhiều kết quả trung gian.

### 13.2. search_after

Cơ chế `search_after` dùng bộ giá trị sort của **hit cuối trang trước**.

Trang đầu:

```json
{
  "size": 2,
  "query": {
    "term": { "tenantId": "T1" }
  },
  "sort": [
    { "createdAt": "desc" },
    { "eventId.keyword": "desc" }
  ]
}
```

Giả sử hit cuối có:

```json
{
  "_source": { "eventId": "E104" },
  "sort": [
    "2026-11-14T08:04:00.000Z",
    "E104"
  ]
}
```

Trang kế:

```json
{
  "size": 2,
  "query": {
    "term": { "tenantId": "T1" }
  },
  "sort": [
    { "createdAt": "desc" },
    { "eventId.keyword": "desc" }
  ],
  "search_after": [
    "2026-11-14T08:04:00.000Z",
    "E104"
  ]
}
```

**Giá trị trong `search_after` phải khớp đúng bộ giá trị sort do engine trả về**, bao gồm đúng thứ tự, kiểu và mọi tie-breaker. Không suy lại bằng cách format tùy tiện từ tài liệu nguồn.

### 13.3. Point in Time (PIT)

Khi search index được cập nhật trong lúc client duyệt nhiều trang, thứ tự và tập kết quả có thể thay đổi. Elasticsearch hỗ trợ **Point in Time (PIT)** để cố định ngữ cảnh tìm kiếm trong một khoảng thời gian được cấp phép.

Một quy trình:

```text
Open PIT
   |
   v
Search first page (PIT + sort)
   |
   v
Take last hit.sort values
   |
   v
Search next page (same query + PIT + search_after)
   |
   v
Close PIT when finished
```

Khi dùng PIT, cần theo đúng hướng dẫn của phiên bản engine về `pit.id`, `keep_alive`, sort tie-breaker (như `_shard_doc` được hỗ trợ trong ngữ cảnh PIT) và việc ID PIT có thể đổi sau các response.

Không nên dùng PIT như một snapshot vĩnh viễn: nó có thời hạn và chi phí tài nguyên. Một token API có thể chứa hoặc tham chiếu PIT trong thời gian giới hạn, và cần phản hồi rõ khi PIT đã hết hạn.

### 13.4. Search relevance thay đổi

Nếu sắp xếp theo `_score`, kết quả có thể thay đổi khi index được cập nhật hoặc truy vấn khác đi. `search_after` không tự cố định scoring. Với các tác vụ cần duyệt ổn định nhiều trang, cần kiểm soát query, sort tie-break và PIT phù hợp.

### 13.5. Scroll khác với phân trang UI

Các API scroll của search engine thường phù hợp hơn cho một số tác vụ duyệt/lấy dữ liệu hàng loạt theo tài liệu sản phẩm, không nên mặc định chọn cho UI người dùng tương tác. Với deep pagination hiện đại, `search_after` + PIT thường là phương án đáng cân nhắc cho Elasticsearch; cách chọn cụ thể tùy phiên bản và workload.

## 14. Graph database và bảng wide-column: pagination phải đi theo access pattern

### 14.1. Neo4j/Cypher

Một truy vấn có thể dùng `SKIP` và `LIMIT`:

```cypher
MATCH (a:Account {accountId: $accountId})-[:MADE_ORDER]->(o:Order)
RETURN o.orderId AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
SKIP $offset
LIMIT $pageSize;
```

Với đồ thị lớn, `SKIP` sâu có thể tốn chi phí, nhất là khi đã mở rộng nhiều cạnh và sắp xếp rồi mới bỏ kết quả.

Keyset có thể dùng điều kiện trên khóa sort của `o`:

```cypher
MATCH (a:Account {accountId: $accountId})-[:MADE_ORDER]->(o:Order)
WHERE o.createdAt < $lastCreatedAt
   OR (
     o.createdAt = $lastCreatedAt
     AND o.orderId < $lastOrderId
   )
RETURN o.orderId AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
LIMIT $pageSize;
```

Đây là mô hình ý tưởng. Query planner, index, degree của Account và đường expand quyết định chi phí thật. Nếu một account có hàng triệu quan hệ, thêm cursor chưa chắc ngăn việc duyệt một lượng lớn cạnh; có thể cần read model theo thời gian dành riêng cho danh sách.

### 14.2. Wide-column và thứ tự trong partition

Với Cassandra, clustering key quyết định thứ tự trong một partition. Nếu phải hiển thị dòng sự kiện theo thời gian, khóa:

```sql
PRIMARY KEY ((user_id, event_day), occurred_at, event_id)
```

giúp đọc một partition đã được tổ chức theo clustering order. Nhưng để tạo timeline **xuyên tháng/ngày**, backend phải chuyển partition và có thể merge nhiều tập kết quả.

Một token duy nhất cho toàn UI có thể phải chứa:

- Bucket/ngày hiện tại;
- Paging state của partition đang đọc;
- Vị trí cuối đã hiển thị;
- Trạng thái những partition khác nếu merge song song.

Đây là lý do keyset đơn giản theo timestamp không tự giải quyết mọi bài toán NoSQL phân tán.

## 15. Phân trang xuyên nhiều partition hoặc shard

Giả sử sự kiện được chia vào ba partition:

```text
Partition A:  E105(08:05), E102(08:02), E098(07:58)
Partition B:  E104(08:04), E101(08:01), E097(07:57)
Partition C:  E103(08:03), E100(08:00), E096(07:56)
```

Muốn trả 4 event mới nhất toàn hệ:

```text
[E105, E104, E103, E102]
```

Backend có thể lấy các phần tử đầu của mỗi partition, dùng **merge có thứ tự** (ví dụ priority queue) rồi chọn top 4.

### 15.1. Tiếp tục lần sau khó hơn một khóa

Nếu mỗi partition đã đọc thêm record trước khi chọn top 4, backend phải biết những record đã lấy nhưng **chưa hiển thị**. Nếu chỉ lưu vị trí driver hiện tại, có thể bỏ sót những record bị fetch-ahead.

Các cách giải quyết:

- Lưu continuation riêng cho từng partition và buffer chưa trả;
- Thiết kế thuật toán merge có khả năng phục hồi từ last global sort key, với các query theo khóa thích hợp;
- Duy trì một read model/timeline tổng hợp phục vụ truy vấn toàn cục;
- Dùng search engine hoặc hệ có query engine hợp nhất nhiều shard.

Token cross-partition vì vậy có thể chứa trạng thái phức tạp hoặc tham chiếu đến trạng thái lưu ở server, không phải đơn giản `offset=40`.

### 15.2. Truy vấn cross-partition có chi phí riêng

Một token giúp tiếp tục nhưng không nhất thiết giảm:

- Số partition phải đọc;
- Chi phí mạng và merge;
- Hot partition;
- Fan-out;
- Bộ nhớ giữ buffer;
- Số request đến backend.

Phải tối ưu access pattern trước, thay vì coi việc chuyển từ offset sang token là giải pháp duy nhất.

## 16. Dữ liệu đang thay đổi: keyset giải quyết được gì và không giải quyết được gì?

### 16.1. Insert mới nằm trước anchor

Nếu event mới E106 có timestamp lớn hơn anchor E104, truy vấn keyset “đứng sau E104” không trả E106 ở trang kế. Điều này thường **đúng với trải nghiệm infinite scroll**: những item mới xuất hiện khi người dùng làm mới danh sách.

### 16.2. Insert mới nằm sau anchor

Nếu một event có timestamp cũ hơn anchor được import muộn, nó có thể xuất hiện ở trang kế dù không tồn tại ở lúc đọc trang đầu. Keyset không phải snapshot.

Nếu cần cố định tập dữ liệu lúc bắt đầu, phải chọn snapshot/PIT hoặc một cơ chế giới hạn theo mốc với bảo đảm phù hợp. Chỉ thêm `createdAt <= firstPageTime` không đủ với dữ liệu backfill có thời điểm nghiệp vụ cũ hơn.

### 16.3. Update sort key

Giả sử E103 đổi `occurredAt` từ 08:03 sang 08:06 sau khi client đọc trang đầu. Nó có thể chuyển **lên trước anchor**, nên những trang tiếp theo không thấy E103.

Nếu một item đã đọc đổi sort key từ mới sang cũ, nó có thể xuất hiện lại ở trang sau.

**Keyset giảm vấn đề dịch vị trí do thêm/xóa trước anchor, nhưng không bảo đảm exactly-once khi sort key có thể thay đổi.**

Một hướng giảm rủi ro là chọn sort key **bất biến**, ví dụ `createdAt` được gán khi tạo và không sửa, kết hợp ID duy nhất.

### 16.4. Delete

Nếu item chưa đọc bị xóa, các trang tiếp theo đương nhiên không chứa nó trong danh sách hiện tại. Nếu cần xử lý từng bản ghi đã tồn tại tại một mốc, phải có snapshot hoặc một danh sách ID cố định để bảo đảm không bỏ sót.

### 16.5. Pagination và công việc xử lý nền

Không nên dựa vào phân trang UI như cơ chế chính để bảo đảm worker xử lý **chính xác một lần** mọi record đang thay đổi.

Worker nền thường cần thêm:

- Work queue hoặc stream có checkpoint;
- Trạng thái đã xử lý;
- Idempotency;
- Lease/claim an toàn;
- Retry và DLQ;
- Snapshot hoặc high-water mark nếu cần.

Pagination chỉ giải quyết việc **lấy dữ liệu theo phần**, không tự đảm bảo hoàn thành một workflow phân tán.

## 17. Snapshot consistency và khái niệm “một lần duyệt ổn định”

### 17.1. Ba hợp đồng có thể chọn

**Danh sách động:** mỗi lần tải trang phản ánh dữ liệu hiện tại. Không hứa trang 1–N cùng một snapshot. Phù hợp feed thông thường.

**Giới hạn bằng watermark:** client duyệt dữ liệu có timestamp/sequence dưới một mốc cố định. Giảm việc mới xuất hiện vào tập, nhưng chưa chống được cập nhật sort key hoặc backfill theo thời gian cũ nếu không có quy tắc khác.

**Snapshot thật:** các trang truy cập cùng một ảnh chụp của dữ liệu tại một mốc theo bảo đảm sản phẩm, ví dụ PIT của search engine hoặc cơ chế snapshot đọc phù hợp. Tốn tài nguyên và thường có hạn thời gian.

### 17.2. Mỗi database có phạm vi snapshot khác nhau

- Một transaction snapshot trong cơ sở dữ liệu có hỗ trợ có thể phù hợp cho một tác vụ ngắn, nhưng không nhất thiết phù hợp phiên cuộn kéo dài hàng giờ.
- PIT có thời hạn và tài nguyên giới hạn.
- DynamoDB/Cassandra paging state không mặc định tạo snapshot xuyên mọi lần đọc.
- Một export theo mốc CDC có thể phù hợp batch hơn UI.

Trước khi hứa “không trùng, không sót trong mọi hoàn cảnh”, phải xác định liệu database và chiến lược phân trang có **bảo đảm đủ mạnh cho yêu cầu đó** hay không.

## 18. Thiết kế API REST phân trang

### 18.1. Offset API

Request:

```http
GET /api/events?tenantId=T1&page=3&pageSize=20
```

Response:

```json
{
  "items": [
    {
      "eventId": "E065",
      "occurredAt": "2026-11-14T07:05:00Z"
    }
  ],
  "page": 3,
  "pageSize": 20,
  "hasMore": true
}
```

Nếu cần total:

```json
{
  "totalItems": 5380,
  "totalPages": 269
}
```

Các số chỉ minh họa và có thể bị thay đổi trong lúc client duyệt. Nếu total cần chính xác theo snapshot, query count phải tương ứng cùng phạm vi/trạng thái, không tự lấy từ một lần đếm riêng rồi coi luôn đồng nhất.

### 18.2. Token API

Request đầu:

```http
GET /api/events?tenantId=T1&severity=ERROR&pageSize=20
```

Response:

```json
{
  "items": [
    {
      "eventId": "E105",
      "occurredAt": "2026-11-14T08:05:00Z"
    },
    {
      "eventId": "E104",
      "occurredAt": "2026-11-14T08:04:00Z"
    }
  ],
  "nextToken": "opaque-page-token",
  "hasMore": true
}
```

Request tiếp:

```http
GET /api/events?tenantId=T1&severity=ERROR&pageSize=20&pageToken=opaque-page-token
```

Response cuối có thể:

```json
{
  "items": [
    {
      "eventId": "E001",
      "occurredAt": "2026-11-10T11:10:00Z"
    }
  ],
  "nextToken": null,
  "hasMore": false
}
```

Ví dụ rút gọn items để làm rõ hợp đồng. Một số backend không biết chắc `hasMore` nếu chưa đọc thêm và có thể chỉ phát trường `nextToken`. Hãy chọn một cách biểu diễn nhất quán.

### 18.3. Đổi filter phải bắt đầu lại

Nếu client thay `severity=ERROR` thành `INFO`, hoặc đổi tenant, thứ tự hay kích thước trang trong những thiết kế yêu cầu token cố định, hãy:

1. Bỏ token cũ;
2. Gửi truy vấn mới không có token;
3. Hiển thị danh sách mới từ đầu.

Backend không nên âm thầm cho token của truy vấn khác tiếp tục, vì kết quả có thể không đúng hoặc vi phạm kiểm soát truy cập.

### 18.4. Khi token hết hạn

Một token có TTL/snapshot hết hạn cần có phản hồi rõ ràng, ví dụ HTTP 400/410 theo hợp đồng API cùng mã lỗi:

```json
{
  "code": "PAGE_TOKEN_EXPIRED",
  "message": "Vị trí phân trang đã hết hạn. Vui lòng tải lại từ đầu."
}
```

Không nên trả ngẫu nhiên trang đầu mà vẫn báo đó là “trang tiếp theo”; client có thể hiển thị bản ghi trùng và không biết chuyện gì xảy ra.

## 19. Thiết kế token an toàn: opaque, ký xác thực và ràng buộc ngữ cảnh

### 19.1. Token tự tạo cho keyset có thể chứa gì?

Ví dụ payload **trước khi bảo vệ**:

```json
{
  "v": 1,
  "tenantId": "T1",
  "queryFingerprint": "sha256-of-canonical-query",
  "sort": "occurredAt:desc,eventId:desc",
  "lastOccurredAt": "2026-11-14T08:04:00Z",
  "lastEventId": "E104",
  "pageSize": 20,
  "issuedAt": 1794643200,
  "expiresAt": 1794646800
}
```

Các timestamp số chỉ minh họa cấu trúc. Khi triển khai, cần tính chúng từ thời gian thật và xác định rõ đơn vị.

Ứng dụng encode payload thành một token, rồi xác thực nó mỗi lần client gửi lại. `queryFingerprint` có thể được tính từ một bản chuẩn hóa của filter, sort, phạm vi tenant và phiên bản schema.

### 19.2. Base64 không phải bảo mật

Một token:

```text
Base64(JSON)
```

chỉ là cách biểu diễn byte. Client có thể decode, đọc và sửa nội dung. Nếu server tin `tenantId` hoặc `lastEventId` trong token chưa kiểm tra, người dùng có thể thử truy cập vị trí/dữ liệu ngoài quyền.

Các lựa chọn:

- **HMAC/signature:** đảm bảo token không bị chỉnh mà không bị phát hiện; không che giấu nội dung.
- **Authenticated encryption:** vừa xác thực vừa mã hóa nếu payload chứa thông tin không được để lộ.
- **Server-side state:** token chỉ là ID ngẫu nhiên tham chiếu trạng thái được lưu ở server với TTL và ACL.

Không đưa bí mật hoặc dữ liệu cá nhân vào token chỉ vì nó được Base64 encode.

### 19.3. Quy trình xác thực token

Một backend nên:

1. Kiểm tra cú pháp và giới hạn kích thước token.
2. Xác thực chữ ký/MAC hoặc giải mã có xác thực.
3. Kiểm tra `version` và `expiresAt`.
4. Xác nhận token thuộc **endpoint, tenant, người dùng/phạm vi quyền và query** đang yêu cầu.
5. Kiểm tra sort, filter, pageSize và schema compatibility.
6. Đánh giá quyền truy cập **ở lần gọi hiện tại**, không chỉ dựa vào quyền lúc tạo token.
7. Áp dụng giới hạn tài nguyên và định mức đọc.
8. Nếu token sai hoặc hết hạn, trả lỗi rõ ràng, không đoán cursor.

### 19.4. Không tin token thô của database

Một số token database chứa paging state nội bộ, có thể phơi bày chi tiết thực thi. Nếu tài liệu sản phẩm cảnh báo paging state bị chỉnh có thể gây rủi ro, backend cần bảo vệ trước khi cho client lưu.

Ngay cả khi SDK trả token opaque, đó không có nghĩa token là **bằng chứng xác thực người dùng**. Authorization phải độc lập.

### 19.5. Versioning và key rotation

Khi đổi thuật toán sort hoặc payload token:

- Có trường `v` để biết version định dạng.
- Có chính sách token cũ còn được hỗ trợ trong bao lâu.
- Token ngắn hạn giảm chi phí tương thích.
- Khi thay khóa HMAC/mã hóa, có thể dùng key identifier và quá trình rotate an toàn.
- Khi token trỏ đến PIT/snapshot, thời hạn token không được vượt thời hạn tài nguyên đó nếu không có cơ chế gia hạn hợp lệ.

## 20. Tối ưu index cho keyset

### 20.1. Filter + sort + cursor là một truy vấn thống nhất

Giả sử:

```text
WHERE tenantId = T1
  AND severity = ERROR
ORDER BY occurredAt DESC, eventId DESC
LIMIT 20
~~~

Một index dự kiến:

```text
(tenantId, severity, occurredAt DESC, eventId DESC)
~~~

Hướng thiết kế là đưa các điều kiện equality vào tiền tố, sau đó các trường sắp xếp và khóa phân biệt.

Nhưng còn phụ thuộc:

- Database có hỗ trợ compound index theo quy tắc nào?
- Condition theo range dùng như thế nào?
- Có partition/shard key bắt buộc?
- Sort kết hợp ASC/DESC có được index hỗ trợ?
- Truy vấn có cần lọc sau khi đọc không?
- Data type và collation có nhất quán?

Không phải chỉ thêm một index có tên phù hợp là bảo đảm query seek hiệu quả. Hãy dùng `explain`, query plan và benchmark trên workload đại diện.

### 20.2. Tránh sort không có thứ tự toàn phần

Một query:

```text
ORDER BY status
~~~

có thể có hàng triệu record cùng `status=ACTIVE`. Nếu muốn keyset, cần thêm trường phân biệt:

```text
ORDER BY status ASC, createdAt DESC, eventId DESC
~~~

Điều kiện tiếp nối phải được xây tương ứng với thứ tự **hỗn hợp**. Không được dùng `eventId < lastId` cho mọi trường hợp mà bỏ qua status/createdAt.

### 20.3. Trường được cập nhật thường xuyên

Nếu sort theo `updatedAt DESC`, mỗi update làm record nhảy vị trí. Với UI feed mới cập nhật, điều đó có thể là chủ đích; nhưng keyset có thể lặp hoặc bỏ sót record trong lúc cuộn.

Nếu nghiệp vụ cần duyệt ổn định, cân nhắc:

- Sort theo `createdAt` bất biến;
- Snapshot/PIT;
- Chốt một high-water mark;
- Duyệt theo ID/sequence bất biến;
- Giữ danh sách ID tại thời điểm bắt đầu tác vụ.

### 20.4. Pagination rất sâu nhưng index không phù hợp

Keyset chỉ tránh việc bỏ qua một prefix dài **khi cơ sở dữ liệu có đường seek hợp lý**. Nếu query cần filter không index được hoặc fan-out nhiều partition, truy vấn vẫn có thể quét rộng để tìm đủ 20 record tiếp theo.

Vì vậy cần xem **chi phí mỗi trang**, không chỉ so số dòng kết quả.

## 21. Phân trang lùi (previous page) với keyset

Keyset tự nhiên cho “Next”. Nếu UI cần “Previous”, có thể:

- Lưu lịch sử cursor ở client và dùng lại khi quay về trang đã đọc;
- Hoặc thực hiện một query ngược từ **khóa đầu tiên của trang hiện tại**, rồi đảo thứ tự kết quả cho UI;
- Hoặc giữ snapshot/trạng thái server khi cần điều hướng phức tạp.

### 21.1. Ví dụ truy vấn ngược

Sort hiển thị chính:

```text
occurredAt DESC, eventId DESC
~~~

Trang hiện tại bắt đầu ở `(tFirst, idFirst)`. Muốn lấy các record **đứng trước** khóa đầu trang:

\[
(occurredAt > tFirst)
\lor
(occurredAt=tFirst \land eventId > idFirst)
\]

Để lấy những record gần nhất trước trang hiện tại, query có thể tạm sắp xếp **tăng dần** và giới hạn `pageSize`, sau đó đảo danh sách trả về.

Không nên đơn thuần lấy `LIMIT pageSize` với sort giảm dần của toàn bộ những record đứng trước, vì có thể nhận **trang đầu tiên của toàn bộ danh sách**, không phải trang ngay trước.

### 21.2. Không nên hứa previous page tuyệt đối với dữ liệu động

Nếu trong lúc người dùng đọc, record thay đổi sort key hoặc bị xóa, trang “quay lại” có thể khác trang đã thấy trước đó. Nếu UI cần hiển thị lại chính xác, cache các trang đã tải hoặc dùng snapshot phù hợp.

## 22. “Có còn trang sau không?” và việc dùng limit + 1

Một cách thường dùng trong keyset:

1. Query tối đa `pageSize + 1` record.
2. Nếu kết quả có nhiều hơn `pageSize`, đặt `hasMore = true`.
3. Trả tối đa `pageSize`.
4. Tạo token từ **record cuối đã trả**.
5. Không đưa record peek-ahead vào token như anchor mới.

Ví dụ `pageSize=3`, database trả:

```text
[E105, E104, E103, E102]
~~~

API:

```text
items       = [E105, E104, E103]
hasMore     = true
nextCursor  = key(E103)
~~~

Lần kế tiếp bắt đầu **sau E103** và có thể trả E102.

Tuy nhiên, với engine như DynamoDB, một page bị giới hạn theo `1 MB` và filter sau đọc, `items.length` không phải tín hiệu chắc chắn của việc kết thúc. Với paging token của engine, nên tuân theo **trạng thái continuation chính thức** thay vì áp dụng máy móc `limit + 1`.

## 23. Tổng số bản ghi và tổng số trang

UI có số trang thường muốn:

```text
Tổng 5.380 bản ghi
269 trang, 20 bản ghi/trang
~~~

Công thức:

\[
totalPages = \left\lceil \frac{totalItems}{pageSize} \right\rceil
\]

Nhưng `COUNT` trên tập lớn hoặc truy vấn xuyên partition có thể đắt, và kết quả count có thể thay đổi trong lúc duyệt.

Các lựa chọn:

- Trả **không có total** cho infinite scroll;
- Trả số lượng ước lượng khi phù hợp và ghi rõ đó là estimate;
- Dùng counter/tổng đã tính sẵn, hiểu độ trễ;
- Đếm theo nhu cầu riêng với giới hạn nguồn lực;
- Chỉ hiện `hasMore` và số record vừa tải.

Trong Cassandra hoặc DynamoDB, đừng mặc định có một `COUNT(*)` rẻ và chính xác cho mọi bộ lọc. Nếu báo cáo cần total chính xác tại một mốc, nên dùng kiến trúc đo đếm/phân tích tương ứng.

## 24. Java: xây trang keyset từ MongoDB Sync Driver

Ví dụ sau minh họa việc chuyển các giá trị cursor thành truy vấn, lấy thêm một record để xác định trang sau và tạo kết quả. Giả sử collection:

- `tenantId` dạng string;
- `severity` dạng string;
- `occurredAt` dạng BSON Date;
- `_id` dạng ObjectId.

Code Java tập trung vào **phần truy vấn**. Lớp API còn cần giải mã/xác thực token theo mục 19.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class EventPager {

    public record Cursor(Date lastOccurredAt, ObjectId lastId) {}

    public record Page(List<Document> items, Cursor nextCursor) {}

    private final MongoCollection<Document> events;

    public EventPager(MongoCollection<Document> events) {
        this.events = events;
    }

    public Page getPage(
            String tenantId,
            String severity,
            Cursor cursor,
            int pageSize) {

        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                    "pageSize must be between 1 and 100");
        }

        Bson scope = Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.eq("severity", severity)
        );

        Bson filter = scope;

        if (cursor != null) {
            Bson after = Filters.or(
                    Filters.lt("occurredAt", cursor.lastOccurredAt()),
                    Filters.and(
                            Filters.eq("occurredAt", cursor.lastOccurredAt()),
                            Filters.lt("_id", cursor.lastId())
                    )
            );
            filter = Filters.and(scope, after);
        }

        List<Document> fetched = events.find(filter)
                .sort(Sorts.orderBy(
                        Sorts.descending("occurredAt"),
                        Sorts.descending("_id")
                ))
                .limit(pageSize + 1)
                .into(new ArrayList<>());

        boolean hasMore = fetched.size() > pageSize;
        List<Document> visible = new ArrayList<>(
                fetched.subList(0, Math.min(pageSize, fetched.size()))
        );

        Cursor next = null;

        if (hasMore && !visible.isEmpty()) {
            Document last = visible.get(visible.size() - 1);
            next = new Cursor(
                    last.getDate("occurredAt"),
                    last.getObjectId("_id")
            );
        }

        return new Page(visible, next);
    }
}
```

### 24.1. Lưu ý về đoạn Java

- Query filter luôn chứa `tenantId` và `severity` từ context đã được xác thực.
- Cursor dùng **cả timestamp và _id**.
- `pageSize` được giới hạn.
- Token tiếp theo lấy từ **record cuối đã trả**, không từ item thứ `pageSize + 1`.
- Nếu không có thêm record, `nextCursor=null`.
- `Cursor` ở đây là object **nội bộ**; API công khai phải ký/mã hóa/bind với query/tenant trước khi gửi cho client.
- Không nên để client tự gửi `tenantId` tùy ý mà bỏ qua authorization.
- Nếu `_id` không phải ObjectId hoặc `occurredAt` không phải BSON Date, cần đổi kiểu và codec cho đúng.
- Trường hợp sort key thay đổi giữa các trang vẫn chưa được bảo đảm snapshot.
- Index phù hợp và `explain()` vẫn cần được xem xét ở bước tối ưu thực tế.

Đoạn code này minh họa một đường keyset cho **một collection/query cụ thể**, không phải lớp trừu tượng áp dụng nguyên xi cho mọi loại NoSQL.

## 25. Kiến trúc token API cho cả offset, keyset và paging state

Một backend lớn có thể dùng một contract chung:

```text
GET /resources?pageSize=20&pageToken=...
~~~

nhưng triển khai backend theo loại nguồn.

```text
            Pagination API
                   |
         Validate auth/filter
                   |
          Decode page token
                   |
       +-----------+------------+
       |           |            |
       v           v            v
     MongoDB    DynamoDB     Cassandra
     keyset     LEK          paging state
       |           |            |
       +-----------+------------+
                   |
          Encode safe token
                   |
                   v
         items + nextToken
~~~

Một token có thể chứa trường `strategy` để biết nó dùng:

- `KEYSET_V1`;
- `DYNAMODB_LEK_V1`;
- `CASSANDRA_STATE_V1`;
- `SEARCH_AFTER_PIT_V1`.

Nhưng không nên cố chuẩn hóa bằng cách **tự đọc cấu trúc bên trong của paging state do database tạo**. Backend chỉ nên encode/decode như một blob theo contract của SDK, kèm validation ngữ cảnh.

### 25.1. Stateless và stateful token

**Stateless:** token mang đầy đủ trạng thái tiếp nối, được bảo vệ bằng chữ ký/mã hóa. Server không cần lưu state cho mỗi người dùng. Đổi lại, token có thể lớn, phức tạp và khó thu hồi trước hạn.

**Stateful:** token là ID ngẫu nhiên tham chiếu tới bản ghi lưu ở server:

```text
token: "p_91c8..."
server state:
    user/tenant
    query fingerprint
    database continuation
    issuedAt/expiresAt
~~~

Ưu điểm là dễ thu hồi/giới hạn kích thước token; nhược điểm là cần storage, TTL, cleanup và khả năng mở rộng cho state.

Chọn theo yêu cầu bảo mật, số người dùng đồng thời, kích thước continuation và thời hạn duyệt.

## 26. Kiểm thử phân trang: các trường hợp không nên bỏ qua

### 26.1. Dữ liệu cố định

Tạo tập:

```text
E105 08:05
E104 08:04
E103 08:03
E102 08:02
E101 08:01
E100 08:00
~~~

Với `pageSize=2`, kiểm tra:

- Trang đầu có E105, E104.
- Trang hai có E103, E102.
- Trang ba có E101, E100.
- Sau trang ba không có next token.
- Tổng hợp các trang chứa đúng những event mong đợi và không trùng.

### 26.2. Trùng sort key

Tạo:

```text
E105 08:05
E104 08:04
E103 08:04
E102 08:04
E101 08:03
~~~

Với keyset sort `occurredAt DESC, eventId DESC` và pageSize=2, mọi event phải xuất hiện đúng một lần khi dữ liệu đứng yên. Đây là test quan trọng để bắt lỗi chỉ dùng timestamp làm cursor.

### 26.3. Chèn dữ liệu ở đầu

- Đọc trang đầu.
- Chèn event mới có timestamp lớn hơn.
- Đọc trang tiếp.
- Quan sát offset có thể trùng; keyset thường không bị dịch do insert trước anchor.

Mục tiêu là kiểm tra **hợp đồng đã chọn**, không mặc định keyset phải hiển thị ngay event mới trên trang sau.

### 26.4. Xóa trước anchor

- Đọc trang đầu.
- Xóa item đầu danh sách.
- Đọc trang tiếp.
- Xác nhận hành vi đúng với offset/keyset đã thiết kế.

### 26.5. Update sort key

- Đọc trang đầu.
- Chuyển timestamp của một record chưa đọc lên trước anchor.
- Đọc tiếp.
- Xác nhận hệ thống biết hoặc chấp nhận giới hạn của danh sách động; nếu yêu cầu snapshot, kiểm tra cơ chế snapshot thật.

### 26.6. Token sai hoặc bị sửa

Thử:

- Sửa một byte token;
- Token của tenant khác;
- Token của query/filter khác;
- Token từ endpoint khác;
- Token hết hạn;
- Token định dạng cũ sau nâng cấp;
- Token quá lớn;
- Token bị replay sau khi quyền truy cập thay đổi.

Backend phải từ chối hoặc xử lý theo hợp đồng, không được bỏ qua authorization hay rơi vào truy vấn rộng không giới hạn.

### 26.7. Trang rỗng có continuation

Đặc biệt với DynamoDB khi dùng `FilterExpression`, hãy kiểm tra một page có `Items=[]` nhưng `LastEvaluatedKey` vẫn tồn tại. Ứng dụng phải có chiến lược tiếp tục, không nhầm rằng đã hết dữ liệu.

### 26.8. Giới hạn hệ thống

- Page size âm, 0 hoặc quá lớn;
- Không có index hỗ trợ sort;
- Số partition tăng mạnh;
- PIT/snapshot hết hạn;
- Timeout khi tải trang sâu;
- Cursor của ngày/partition cũ;
- Client bấm tải thêm nhiều lần cùng lúc;
- Request trước trả về sau request sau.

UI nên kiểm soát loading state, thứ tự response và dedup hiển thị nếu danh sách có thể thay đổi.

## 27. Đánh giá hiệu năng bằng số liệu thay vì chỉ nhìn mã

Một bộ kịch bản benchmark minh họa:

| Kịch bản | Offset | Keyset/token | Điều cần đo |
|---|---|---|---|
| Trang đầu 20 item | offset 0 | first page | p95/p99, số docs/keys đọc |
| Trang 100 | offset 1980 | cursor thứ 99 | Chi phí tăng theo độ sâu |
| Trang 10.000 | offset 199980 | seek từ anchor | CPU, network, memory |
| Dữ liệu thêm liên tục | Có thể lặp/bỏ sót | Hành vi theo anchor | Độ ổn định UX |
| Cross-partition | Có thể quét rộng | Token nhiều partition | Số partition và fan-out |
| Filter ít chọn lọc | Quét nhiều | Token có thể trả ít items | Read capacity/RU/DB hits |
| Sort key thay đổi | Có thể lỗi vị trí | Vẫn có thể lỗi vị trí | Tỷ lệ duplicate/missing |
| Snapshot/PIT | Cần context tương ứng | Cần context tương ứng | Chi phí giữ snapshot và expiry |

Các metric nên theo dõi:

- `p50/p95/p99` latency mỗi trang;
- Số item/byte được đọc ở backend so với số item trả;
- Read capacity units / request units / DB hits;
- Số partition/shard truy cập;
- Token size và lỗi token;
- Cache hit/miss;
- Tỷ lệ timeout/retry;
- Tỷ lệ client dừng trước khi hết danh sách;
- CPU/I/O/heap khi deep pagination;
- Dữ liệu biến động làm trùng hoặc thiếu theo hợp đồng UI.

Nếu keyset query vẫn quét một triệu document để lấy 20 kết quả, vấn đề nằm ở **access path và index**, không phải cú pháp cursor.

## 28. Mẫu lựa chọn chiến lược theo bài toán

### 28.1. Trang quản trị có vài trăm kết quả, cần chọn số trang

Offset có thể phù hợp nếu danh sách khá ổn định, có sort xác định và chi phí đọc nhỏ. Có thể hiển thị totalPages hoặc số trang giới hạn.

### 28.2. News feed/cuộn vô hạn theo thời gian

Keyset theo `createdAt DESC, id DESC` thường phù hợp. Trả opaque next token, không cần total chính xác. Event mới xuất hiện khi refresh đầu danh sách.

### 28.3. Lịch sử đơn theo customer trong DynamoDB

Query trên partition customer với sort key thời gian, tiếp tục bằng `LastEvaluatedKey`. Không tự mô phỏng offset bằng cách đọc và bỏ đi hàng nghìn item.

### 28.4. Sự kiện một ngày trong Cassandra

Đọc partition `(userId, day)` bằng driver paging state. Nếu sang ngày khác, backend quản lý chuyển partition và token API bao gồm trạng thái ngày hiện tại.

### 28.5. Tìm kiếm toàn văn hàng chục nghìn kết quả

Cho trang đầu: `from/size` có thể đủ. Nếu duyệt sâu và cần ổn định, đánh giá `search_after + PIT` theo phiên bản engine; không tăng `max_result_window` vô hạn.

### 28.6. Báo cáo cần xuất toàn bộ bản ghi đúng một lần

Đừng dựa duy nhất vào UI page token trên tập đang thay đổi. Cần xem snapshot/export/stream có checkpoint và xử lý idempotent, tùy nghiệp vụ và database.

### 28.7. Nhiều partition, một timeline toàn cục

Ưu tiên đường truy cập theo truy vấn: read model tổng hợp, search index hoặc cơ chế merge với token per-partition. Không kỳ vọng chỉ thay một số offset bằng lastId sẽ tự giải quyết fan-out.

## 29. Những sai lầm thường gặp

**“Dùng LIMIT là đã phân trang.”** LIMIT chỉ giới hạn một lần đọc. Cần cơ chế tiếp tục và thứ tự xác định để đi qua nhiều trang.

**“Query không ORDER BY vẫn có thứ tự ổn định.”** Không nên dựa vào thứ tự mặc định; có thể thay đổi theo plan, storage và dữ liệu.

**“Timestamp đủ làm cursor.”** Không khi có nhiều record cùng timestamp. Cần tie-breaker duy nhất.

**“Offset chỉ tốn đúng pageSize.”** Sai ở trang sâu; engine có thể phải di chuyển qua rất nhiều record trước đó.

**“Keyset có thể nhảy ngay đến trang 100 mà không biết các trang trước.”** Không tự nhiên, trừ khi có anchor hoặc cấu trúc bổ trợ.

**“Keyset luôn bảo đảm không trùng và không sót.”** Không khi sort key thay đổi hoặc cần snapshot cố định.

**“Continuation token của database chỉ là last ID.”** Không nhất thiết; có thể chứa paging state, partition progress hoặc ngữ cảnh thực thi.

**“Trang trả ít hơn Limit nghĩa là đã hết.”** Không với nhiều dịch vụ có giới hạn theo byte/filter, đặc biệt DynamoDB.

**“Trang rỗng nghĩa là đã hết.”** Không nếu còn continuation key/token hợp lệ.

**“Base64(JSON) là token bảo mật.”** Không. Cần xác thực/mã hóa và kiểm tra ngữ cảnh, quyền truy cập.

**“Token của tenant T1 có thể dùng cho T2 vì truy vấn giống nhau.”** Không. Token phải ràng buộc phạm vi và được kiểm tra authorization mỗi lần.

**“Paging token giữ một snapshot.”** Không mặc định. Cần bảo đảm snapshot/PIT cụ thể nếu muốn điều đó.

**“COUNT tổng thể luôn rẻ và chính xác.”** Không trên mọi NoSQL, nhất là truy vấn phân tán.

**“Search_after không cần sort tie-break.”** Sai khi nhiều hit có cùng giá trị sort; cần thứ tự xác định hoặc cơ chế tie-break được engine hỗ trợ.

**“Cassandra LIMIT là page size của driver.”** Không. Đây là hai tầng giới hạn khác nhau.

**“FilterExpression DynamoDB làm Query chỉ đọc item phù hợp.”** Không; filter thường áp dụng sau đọc, ảnh hưởng số item trả về chứ không xóa hết chi phí đánh giá.

## 30. Bài tập thực hành

### Bài tập 1: tính offset

Có 250 đơn hàng, mỗi trang 25 đơn, đánh số trang từ 1.

**Câu hỏi:** Trang 7 có offset bao nhiêu? Tổng số trang là bao nhiêu?

**Gợi ý:**

\[
offset=(7-1)\times25=150
\]

\[
totalPages=\lceil250/25\rceil=10
\]

### Bài tập 2: tìm lỗi trùng do insert

Danh sách ban đầu:

```text
[A, B, C, D, E, F]
```

Client đọc trang 1 (A, B). Một item X được chèn đầu, rồi client đọc `offset=2, limit=2`.

**Câu hỏi:** Trang hai có thể chứa gì? Điều gì bị trùng?

**Gợi ý:** Danh sách trở thành `[X,A,B,C,D,E,F]`; trang hai là `[B,C]`. B bị lặp.

### Bài tập 3: cursor với timestamp trùng

Danh sách giảm dần:

```text
E5 (10:05)
E4 (10:04)
E3 (10:04)
E2 (10:03)
```

Trang đầu size=2 kết thúc ở E4.

**Câu hỏi:** Vì sao `createdAt < 10:04` sai? Viết điều kiện đúng với sort `createdAt DESC, eventId DESC`.

**Gợi ý:**

```text
createdAt < 10:04
OR (createdAt = 10:04 AND eventId < E4)
```

Nhờ vậy E3 vẫn nằm ở trang tiếp.

### Bài tập 4: peek-ahead

Database trả 4 record cho `pageSize=3`:

```text
[E9, E8, E7, E6]
```

**Câu hỏi:** API hiển thị mấy record, lấy cursor từ record nào?

**Gợi ý:** Hiển thị E9,E8,E7; `hasMore=true`; cursor là khóa E7, không phải E6.

### Bài tập 5: DynamoDB page rỗng

`Query` có `Limit=20`, `FilterExpression` chỉ giữ status=PAID. Response:

```json
{
  "Items": [],
  "LastEvaluatedKey": {
    "PK": {"S": "USER#U1"},
    "SK": {"S": "ORDER#2026-11-14#O20"}
  }
}
```

**Câu hỏi:** Có được kết luận hết dữ liệu không?

**Gợi ý:** Không. Tiếp tục bằng `ExclusiveStartKey` hoặc trả nextToken phù hợp; những item sau có thể khớp filter.

### Bài tập 6: Cassandra theo ngày

Bảng có partition key `(userId, eventDay)`. API muốn “50 sự kiện mới nhất của user qua 7 ngày”.

**Câu hỏi:** Vì sao paging state trong một ngày chưa đủ?

**Gợi ý:** Mỗi ngày là một partition. Backend cần chuyển ngày hoặc merge nhiều partition, lưu trạng thái tiến độ theo ngày/partition.

### Bài tập 7: token bị sửa

Một API mã hóa token bằng Base64 JSON có `tenantId=T1`, `lastId=E10` mà không ký. Client tự sửa tenantId thành T2.

**Câu hỏi:** Rủi ro gì và cách khắc phục?

**Gợi ý:** Token có thể bị giả mạo để thay đổi phạm vi truy vấn. Dùng chữ ký/MAC hoặc authenticated encryption, bind với query/tenant/user và kiểm tra authorization ở mỗi request.

### Bài tập 8: sort key thay đổi

Client đọc các item mới nhất theo `updatedAt DESC`. E3 chưa được xem, sau đó được cập nhật lên đầu danh sách.

**Câu hỏi:** Keyset có bảo đảm E3 được đọc ở trang sau không?

**Gợi ý:** Không. E3 có thể chuyển lên trước anchor và không còn ở phạm vi trang tiếp. Muốn snapshot chính xác cần cơ chế khác hoặc chọn sort key bất biến.

### Bài tập 9: trang trước

UI hiển thị theo `occurredAt DESC, eventId DESC` và muốn quay lại trang đứng ngay trước.

**Câu hỏi:** Điều kiện nào xác định record ở phía trước khóa đầu trang?

**Gợi ý:**

```text
occurredAt > firstOccurredAt
OR (
  occurredAt = firstOccurredAt
  AND eventId > firstEventId
)
```

Sau đó dùng sort ngược để lấy nhóm gần nhất trước trang hiện tại, rồi đảo kết quả hiển thị.

### Bài tập 10: phân trang search sâu

Người dùng muốn duyệt 100.000 kết quả tìm kiếm trong Elasticsearch.

**Câu hỏi:** Vì sao không nên chỉ tăng `from` đến 100.000?

**Gợi ý:** Chi phí giữ/bỏ kết quả trung gian và giới hạn `max_result_window`. Cần xem `search_after`, PIT và mục tiêu nghiệp vụ; nếu xuất dữ liệu hàng loạt, cân nhắc API/cơ chế thích hợp hơn UI.

### Bài tập 11: count chính xác

DynamoDB lưu 20 triệu đơn hàng, API infinite scroll theo từng khách và UI không cần số trang.

**Câu hỏi:** Có cần tính chính xác `totalItems` ở mỗi lần tải trang không?

**Gợi ý:** Không bắt buộc. Có thể chỉ trả items + nextToken, tránh chi phí count không cần thiết. Nếu sản phẩm yêu cầu total, thiết kế cơ chế đo đếm riêng.

### Bài tập 12: kiểm thử dữ liệu thay đổi

Viết bộ test cho API keyset `createdAt DESC, id DESC`.

**Yêu cầu:** Đề xuất ít nhất 5 trường hợp kiểm thử.

**Gợi ý:** Có record cùng timestamp, thêm record mới đầu danh sách, xóa record trước anchor, thay đổi sort key, token sai filter/tenant, token hết hạn, page cuối, pageSize không hợp lệ và kết quả rỗng nhưng còn continuation từ database.

### Bài tập 13: nhiều partition

Có 4 partition chứa sự kiện xen kẽ theo thời gian. API lấy top 20 toàn hệ và prefetch mỗi partition 20 record.

**Câu hỏi:** Vì sao token chỉ chứa “đã đọc 20 record ở mỗi partition” có thể làm mất dữ liệu?

**Gợi ý:** Nhiều record prefetch chưa được trả cho client. Token phải bảo lưu những item đã lấy nhưng chưa hiển thị hoặc xây lại tiến độ theo khóa toàn cục một cách chính xác.

### Bài tập 14: chọn chiến lược

Đánh giá ba yêu cầu:

1. Trang quản trị có dưới 100 bản ghi và cần số trang.
2. Feed người dùng có hàng triệu bài, thêm mới liên tục.
3. Xuất dữ liệu phân tích cần một tập nhất quán tại thời điểm chốt.

**Gợi ý:** (1) Offset có thể phù hợp; (2) keyset/opaque token với sort bất biến; (3) snapshot/export/checkpoint chuyên dụng, không chỉ một cursor của UI.

## 31. Kết luận

**Phân trang là lựa chọn về đường truy cập và tính nhất quán, không chỉ là cách chia response thành 20 record.** Offset dùng vị trí số học, đơn giản cho tập nhỏ và số trang; nhưng trang sâu có thể tốn công, và thêm/xóa record trước vị trí đọc có thể gây lặp hoặc bỏ sót.

**Keyset/seek** dựa trên giá trị sort của record cuối đã hiển thị. Khi có index thích hợp và **thứ tự xác định với tie-breaker duy nhất**, nó thường phù hợp hơn cho feed, lịch sử sự kiện và truy vấn tuần tự nhiều trang. Tuy vậy, keyset không tự cố định snapshot nếu sort key thay đổi hoặc có dữ liệu được thêm/xóa giữa các lần gọi.

**Continuation token** là một giao diện tổng quát hơn: token có thể chứa khóa keyset, paging state của Cassandra, `LastEvaluatedKey` của DynamoDB, continuation của Cosmos DB hoặc `search_after`/PIT của search engine. Token nên được xem là dữ liệu opaque, gắn với query và quyền truy cập, có kiểm soát phiên bản và thời hạn.

Khi thiết kế một API NoSQL phân trang, hãy bắt đầu từ **partition/filter/sort, khóa tie-break, giới hạn page size, yêu cầu snapshot và khả năng index của database**. Sau đó mới chọn offset, keyset hay token. Cuối cùng, hãy kiểm thử trên dữ liệu đang thay đổi và đo **chi phí đọc thực tế mỗi trang**, bởi một API trả ít record chưa chắc là một truy vấn rẻ hoặc một danh sách nhất quán.

