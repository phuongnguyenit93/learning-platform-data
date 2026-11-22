# Quét toàn bộ dữ liệu và các tình huống cần kiểm soát phạm vi

## 1. Đặt vấn đề: một truy vấn trả ít kết quả vẫn có thể đọc rất nhiều dữ liệu

Trong ứng dụng sử dụng NoSQL, nhiều câu truy vấn trông đơn giản:

- “Tìm 20 đơn hàng đang có trạng thái `FAILED`”.
- “Liệt kê 100 sự kiện mới nhất của thiết bị”.
- “Tìm tất cả tài khoản chưa hoạt động trong 180 ngày”.
- “Xuất dữ liệu trong tháng trước để kiểm toán”.
- “Tính lại chỉ số từ toàn bộ lịch sử sự kiện”.

Điểm khó không nằm ở cú pháp `find()`, `SELECT` hay `Scan` mà nằm ở **phạm vi dữ liệu DBMS phải đọc hoặc xem xét** để tạo ra kết quả.

Một ví dụ:

~~~text
Toàn bộ collection: 50 triệu sự kiện
Sự kiện mức ERROR: 0,01%
API yêu cầu: 20 sự kiện ERROR mới nhất
~~~

Nếu không có đường truy cập phù hợp, một truy vấn có thể phải đi qua nhiều bản ghi rồi lọc và sắp xếp mới trả 20 hàng. Kể cả khi API có `LIMIT 20`, DBMS vẫn có thể làm công việc rất lớn ở phía trước giới hạn.

Ngược lại, nếu dữ liệu có **khóa phân vùng hoặc chỉ mục phù hợp với điều kiện lọc và thứ tự**, truy vấn có thể định vị một phạm vi nhỏ hơn nhiều.

Bài học này tập trung vào:

1. Phân biệt các kiểu quét và nguyên nhân phát sinh full scan.
2. Xác định **khi nào quét toàn bộ dữ liệu là hợp lý**.
3. Thiết kế ranh giới truy vấn theo tenant, partition, ID, thời gian, độ sâu và dung lượng.
4. Kiểm soát truy vấn quét lớn bằng phân trang, checkpoint, timeout, rate limit và giám sát.
5. Nhận diện khác biệt giữa MongoDB, DynamoDB, Cassandra, Redis và mô hình đồ thị.
6. Thực hành chuyển một truy vấn không giới hạn thành đường đọc phù hợp với workload.

## 2. “Scan” có thể mang nhiều nghĩa khác nhau

Trong NoSQL, từ *scan* thường chỉ hoạt động **duyệt một tập các mục dữ liệu**, nhưng cần xác định tập đó rộng đến đâu.

| Loại truy cập | Cách diễn giải | Ví dụ |
|---|---|---|
| **Point lookup** | Đọc một item theo khóa xác định | Lấy Order bằng `orderId` |
| **Partition/key-range read** | Đọc các hàng trong một partition hoặc khoảng khóa | 50 event của `(deviceId, day)` |
| **Index seek/range scan** | Dùng chỉ mục để tìm hoặc duyệt một dải index | Đơn của khách trong một khoảng ngày |
| **Full index scan** | Duyệt phần lớn hoặc toàn bộ index | Tính thống kê từ mọi khóa có trong index |
| **Full table/collection scan** | Duyệt lượng lớn hoặc toàn bộ dữ liệu trong tập | Đọc mọi document vì không có filter/index phù hợp |
| **Distributed/parallel scan** | Chia việc quét nhiều phần dữ liệu cho worker | Export hoặc backfill nhiều phân đoạn |
| **Keyspace scan** | Duyệt khóa trong kho key-value | Redis `SCAN` |
| **Graph traversal** | Đi theo quan hệ từ node nguồn; phạm vi có thể bùng nổ | Duyệt mọi liên kết ở độ sâu lớn |

**Không phải mọi index scan đều là full collection scan**, và một scan có thể là lựa chọn tối ưu khi ứng dụng thực sự cần đọc phần lớn dữ liệu. Điều quan trọng là **đã có giới hạn phạm vi có ý nghĩa chưa, và chi phí có phù hợp với mục tiêu của truy vấn không**.

### 2.1. Hình dung hai đường truy cập

~~~mermaid
flowchart TD
  A["API: 20 đơn PAID mới nhất của khách X"] --> B{"Có khóa/index đúng mẫu?"}
  B -->|"Có"| C["Tìm nhóm customer=X và status=PAID"]
  C --> D["Đọc theo createdAt DESC"]
  D --> E["Dừng sau đủ 20 kết quả"]
  B -->|"Không"| F["Duyệt lượng lớn đơn"]
  F --> G["Lọc customer/status"]
  G --> H["Sắp xếp các ứng viên"]
  H --> E
~~~

Sơ đồ minh họa luồng logic, không áp đặt một execution plan vật lý cụ thể. Engine có thể tối ưu sort, song vẫn phải xem xét nhiều ứng viên nếu thiếu đường truy cập phù hợp.

### 2.2. Full scan không luôn là lỗi

Một job cần tính checksum của **toàn bộ 100 triệu record** thực sự phải xem xét toàn bộ dữ liệu hoặc dùng một cấu trúc thống kê/bản sao có bảo đảm đủ cho mục tiêu. Khi đó scan là hoạt động nghiệp vụ hợp lệ.

Ngược lại, một API khách hàng chỉ cần 20 bản ghi gần nhất nhưng lại đọc mọi record để tìm 20 kết quả là một dấu hiệu phải xem lại thiết kế.

**Câu hỏi đúng không phải “có scan hay không?”, mà là “có phải đọc nhiều đến thế để trả lời câu hỏi này không?”**

---

## 3. Chi phí quét phụ thuộc số mục được xem xét, không chỉ số mục trả về

Xét các đại lượng:

- \(N\): tổng số mục trong tập dữ liệu có thể bị quét.
- \(n\): số mục thực sự được xem xét bởi query.
- \(k\): số kết quả trả về.
- \(s\): kích thước trung bình của mục được đọc.
- \(q\): số lần truy vấn trong một khoảng thời gian.

Một phép ước tính thô cho byte phải xem xét:

\[
B_{\text{scan}} \approx n \times s.
\]

Nếu một truy vấn không index phải xem xét 20 triệu document với trung bình 1 KiB/document:

\[
B_{\text{scan}} \approx 20\,000\,000 \times 1\,024
\approx 20.48\ \text{GB}.
\]

Đây là **ước tính dữ liệu logic**; lượng I/O thực tế khác do compression, storage layout, cache, cột/projection và tối ưu engine.

Nếu API gọi 10 lần/giây, chi phí tích lũy có thể rất lớn dù mỗi response chỉ khoảng vài chục KB.

### 3.1. Selectivity

**Độ chọn lọc (selectivity)** phản ánh tỷ lệ dữ liệu đáp ứng bộ lọc.

Ví dụ:

~~~text
Collection: 10 triệu bản ghi
Filter status = ERROR: 10.000 bản ghi
Tỷ lệ phù hợp: 10.000 / 10.000.000 = 0,1%
~~~

Bộ lọc rất chọn lọc nhưng **không có index** vẫn có thể buộc engine đọc rất nhiều document để phát hiện những record phù hợp. Một index hợp lý có thể làm giảm tập dữ liệu phải xét.

Tuy nhiên, một index trên `status` với chỉ ba giá trị `ACTIVE`, `PAUSED`, `DELETED` có thể không hữu ích cho mọi query nếu mỗi giá trị chiếm hàng triệu record và query cần lọc thêm nhiều trường khác.

### 3.2. Những chi phí phải tính cùng nhau

| Chi phí | Vì sao quan trọng |
|---|---|
| I/O và bytes read | Scan đọc dữ liệu từ bộ nhớ hoặc đĩa |
| CPU filter | So sánh điều kiện với nhiều item |
| Sort/aggregation | Có thể cần giữ và sắp xếp nhiều ứng viên |
| Network | Quét phân tán hoặc trả dữ liệu lớn giữa các node |
| Read capacity | Một số managed DB tính đơn vị đọc theo lượng dữ liệu đã đánh giá |
| Cache pressure | Scan có thể đẩy dữ liệu nóng khỏi cache |
| Latency p95/p99 | Truy vấn lớn ảnh hưởng cả các request khác |
| Replica/shard load | Quét cùng lúc trên nhiều node gây cạnh tranh tài nguyên |
| Thời gian vận hành | Cần phân đoạn, retry, checkpoint và giám sát |

Khi đánh giá hiệu năng, không nên chỉ ghi “query chạy 2 giây” mà không ghi số bản ghi đọc, phân bố dữ liệu và mức tải cùng thời điểm.

## 4. `LIMIT` không thay thế điều kiện lọc hiệu quả

Ví dụ MongoDB:

~~~javascript
db.orders.find({ status: "PAID" }).limit(20);
~~~

Nếu query planner không có đường truy cập phù hợp, nó có thể duyệt collection cho tới khi đủ 20 kết quả. Nếu `PAID` hiếm, số document phải đọc có thể rất nhiều; nếu phải sort, việc giới hạn số kết quả còn có thể diễn ra **sau khi engine đã xem xét các ứng viên**.

Truy vấn:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

đòi thêm thứ tự mới nhất. Index chỉ trên `status` có thể không đủ tối ưu thứ tự; cần đánh giá index ghép theo filter và sort.

Một hợp đồng API tốt phải định nghĩa đồng thời:

~~~text
WHERE: tenantId = ? AND customerId = ? AND status = ?
ORDER BY: createdAt DESC, uniqueId DESC
LIMIT: 20, tối đa 100
CURSOR: vị trí cuối trang theo đúng khóa ORDER BY
~~~

**Một query trả ít hàng không chứng minh chi phí đọc thấp.**

## 5. Xác định phạm vi trước khi chạy truy vấn

Có nhiều chiều giới hạn phạm vi:

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| **Tenant** | Người gọi được phép xem tenant nào? | `tenantId = callerTenant` |
| **Khóa chính** | Có biết ID chính xác không? | `orderId = "order-1001"` |
| **Partition** | Có thể định vị một nhóm khóa không? | `(deviceId, eventDay)` |
| **Thời gian** | Cần dữ liệu trong bao lâu? | `eventAt >= from AND eventAt < to` |
| **Trạng thái/loại** | Bộ lọc nào xuất hiện thường xuyên? | `status = FAILED` |
| **Projection** | API cần những trường nào? | Chỉ ID, thời gian, trạng thái |
| **Số bản ghi** | Một trang trả tối đa bao nhiêu? | `pageSize <= 100` |
| **Số nhóm truy cập** | Có thể chạm bao nhiêu shard/bucket? | Tối đa vài bucket trong một request |
| **Thời gian thực thi** | Query có ngân sách timeout không? | Theo SLO API |
| **Độ sâu quan hệ** | Truy vấn graph đi mấy cạnh? | 1–2 hops, không duyệt vô hạn |

Một yêu cầu “tìm tất cả dữ liệu của mọi tenant trong cả năm” cần được phân biệt với API thông thường. Nó có thể là **job export/batch được phân quyền riêng**, không nên lộ ra như một endpoint public không giới hạn.

### 5.1. Giới hạn theo tenant là yêu cầu bảo mật

Không được tin mù quáng `tenantId` do client gửi. Backend phải lấy tenant được phép từ ngữ cảnh đã xác thực hoặc kiểm tra quyền đối với tenant được yêu cầu.

Một query có index rất nhanh nhưng thiếu ràng buộc tenant vẫn có thể gây **rò rỉ dữ liệu**. Bảo mật và phạm vi truy vấn là một phần của tính đúng đắn, không phải chỉ là tối ưu hiệu năng.

### 5.2. Giới hạn theo thời gian

Thay vì:

~~~text
Lấy mọi event của thiết bị X
~~~

hãy xác định:

~~~text
deviceId = X
eventAt >= 2026-11-01T00:00:00Z
eventAt <  2026-12-01T00:00:00Z
limit = 100
~~~

Khoảng thời gian dạng **nửa mở** `[from, to)` dễ nối các kỳ liên tiếp mà không trùng ranh giới. Nếu hệ dùng time bucket, API cũng cần định tuyến tới đúng bucket tháng/ngày.

### 5.3. Giới hạn không gian dữ liệu cần xét

Nếu một partition có hàng trăm triệu hàng, chỉ có partition key chưa chắc đã đủ. Có thể cần thêm sort key/range, clustering key, page size và tối đa thời gian truy vấn.

Trong hệ đa shard, một filter chỉ có `status` nhưng không có shard key có thể trở thành query fan-out qua nhiều shard. Điều này có thể hợp lý cho báo cáo, nhưng cần cân nhắc với API có SLO thấp.

---

## 6. Khi nào quét toàn bộ dữ liệu là lựa chọn hợp lý?

### 6.1. Kiểm toán và đối soát

Ví dụ muốn xác minh không có đơn bị mất sau một đợt migration. Một job cần duyệt toàn bộ các ID hoặc checksum để so sánh nguồn–đích.

Đây là scan có mục đích rõ. Nên thực hiện theo batch, có snapshot/watermark phù hợp, checkpoint, giới hạn tốc độ và báo cáo sai lệch.

### 6.2. Export hoặc backup logic

Một yêu cầu xuất toàn bộ dữ liệu của một tenant có thể cần đọc mọi bản ghi được phép. Nhưng export logic không đồng nghĩa backup nhất quán khi hệ có ghi liên tục.

Nếu cần một ảnh chụp chính xác theo thời điểm, nên dùng snapshot/export/backup mechanism của DBMS hoặc giải pháp có thể ghi nhận thay đổi phát sinh trong lúc export.

### 6.3. Backfill index hoặc read model

Khi thêm một bảng đọc mới, hệ có thể phải đi qua dữ liệu hiện hữu để tạo bản chiếu. Sau đó dùng change stream/outbox/CDC để bắt các thay đổi phát sinh.

Đây là job tạm thời, không nên để mỗi request người dùng tự thực hiện backfill.

### 6.4. Migration và chuyển schema

Khi một trường được đổi cấu trúc hoặc một kho mới cần dữ liệu, việc scan từng record có thể bắt buộc. Cần tính đầy đủ dữ liệu, khả năng chạy lại và điều kiện cutover.

### 6.5. Tác vụ phân tích

Một số tổng hợp toàn bộ tập dữ liệu cần đọc nhiều hàng. Nhưng nếu nhu cầu lặp thường xuyên, nên cân nhắc:

- Incremental aggregation.
- Bảng tổng hợp theo ngày/tháng.
- Data warehouse hoặc analytical store.
- Stream processing giữ chỉ số khi dữ liệu mới được ghi.
- Index hoặc materialized view cho các chiều lọc phổ biến.

Không nên mặc định scan OLTP store là cách tốt nhất để chạy báo cáo lớn theo lịch.

### 6.6. Dataset nhỏ hoặc truy vấn hiếm

Với vài nghìn item và tần suất rất thấp, full scan có thể hợp lý hơn việc duy trì index phức tạp. Quyết định phải dựa trên kích thước, tải và chi phí ghi/index, không coi mọi COLLSCAN là lỗi nghiêm trọng.

## 7. MongoDB: nhận diện `COLLSCAN` và `IXSCAN`

Giả sử collection `orders` chứa:

~~~json
{
  "_id": "order-1001",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "status": "PAID",
  "createdAt": "2026-11-14T08:15:27.123Z",
  "totalVnd": 1050000
}
~~~

Trong MongoDB, nếu cần so sánh thời gian, `createdAt` nên được lưu bằng **BSON Date**, không chỉ chuỗi JSON. Ví dụ hiển thị ở trên dùng chuỗi cho dễ đọc.

### 7.1. Query dễ gây quét rộng

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Nếu chưa có index phù hợp, kế hoạch có thể dùng `COLLSCAN` và/hoặc sort tốn kém.

Để xem execution plan:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Những dấu hiệu cần quan sát:

- `COLLSCAN`: quét collection.
- `IXSCAN`: quét index; cần xem index nào và phạm vi.
- `totalKeysExamined`: số khóa index được xem xét.
- `totalDocsExamined`: số document được xem xét.
- Số record trả về.
- Sort stage, thời gian thực thi và tài nguyên dùng.

**IXSCAN không mặc nhiên rẻ**: full index scan trên một index rất lớn vẫn có thể tốn kém. Ngược lại, COLLSCAN có thể là lựa chọn hợp lý khi truy vấn cần phần lớn document hoặc tập dữ liệu quá nhỏ để index mang lại lợi ích.

### 7.2. Thu hẹp từ hợp đồng API

Giả sử yêu cầu thật là “20 đơn PAID mới nhất của một khách trong tenant”.

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    status: "PAID"
  },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Một compound index có thể cân nhắc:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Các điều kiện bằng đứng trước các trường sắp xếp, giúp một mẫu truy vấn được phục vụ theo một dải index nếu kế hoạch phù hợp.

Đây là **ứng viên index**, không phải cam kết performance. Cần đo execution plan trên dữ liệu đại diện. Nếu API bỏ `status` mà vẫn muốn sort theo `createdAt`, index có `status` trước thời gian chưa chắc là index tốt nhất cho biến thể đó.

### 7.3. Khi filter không đủ chọn lọc

Giả sử 99% đơn là `PAID`. Một index chỉ trên `status` có thể không giảm nhiều công việc so với quét collection khi query phải trả một lượng lớn dữ liệu.

Thiết kế cần xét **tổ hợp filter, thứ tự, projection và tỷ lệ truy vấn**, thay vì tạo index cho từng trường một cách tự động.

### 7.4. Quét có chủ đích cho batch job

Khi thật sự cần duyệt toàn bộ một tập:

~~~javascript
const cursor = db.orders.find(
  { tenantId: "tenant-7" },
  {
    _id: 1,
    tenantId: 1,
    updatedAt: 1
  }
)
.sort({ _id: 1 })
.batchSize(500);
~~~

Đây là thao tác minh họa cho job batch. `batchSize` quản lý số document nhận mỗi batch theo cursor; **không phải tổng số document** và không tự giới hạn tài nguyên của cả job.

Nếu chỉ một tenant, cần index theo `(tenantId, _id)` để hỗ trợ đường đọc có lọc và thứ tự phù hợp. Đối với tenant rất lớn, còn cần rate limit, checkpoint và giới hạn thời gian xử lý.

### 7.5. `maxTimeMS` và projection

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42"
  },
  {
    _id: 1,
    createdAt: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(50)
.maxTimeMS(2000);
~~~

`maxTimeMS` giúp đặt một ngân sách thời gian cho thao tác theo ngữ nghĩa MongoDB, nhưng **không phải mức trần số byte, CPU hoặc số item đã đọc**. Timeout cũng cần được xử lý ở driver/API và hạ tầng.

Projection giúp tránh tải dữ liệu không cần thiết. Một document có mảng `items` rất lớn không nên bị trả toàn bộ nếu màn hình danh sách chỉ cần ID, thời gian và tổng tiền.

---

## 8. MongoDB: phân trang bằng cursor thay vì `skip` lớn

Một endpoint dùng:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42"
})
.sort({ createdAt: -1, _id: -1 })
.skip(100000)
.limit(20);
~~~

Dù có index, offset lớn có thể khiến engine phải đi qua nhiều mục trước khi trả trang. Khi có insert mới giữa hai lần đọc, offset có thể làm trùng hoặc bỏ sót bản ghi.

### 8.1. Keyset pagination

Dùng sort:

~~~text
createdAt DESC, _id DESC
~~~

Bản ghi cuối trang trước:

~~~json
{
  "createdAt": "2026-11-14T08:15:27.123Z",
  "id": "order-1001"
}
~~~

Trang sau chỉ nhận các item đứng sau cặp khóa cuối:

~~~javascript
const cursorTime = new Date("2026-11-14T08:15:27.123Z");
const cursorId = "order-1001";

db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  },
  {
    _id: 1,
    createdAt: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Giả định `_id` có kiểu chuỗi, so sánh nhất quán với cursor. Nếu `_id` là ObjectId thật, cursor phải dùng cùng kiểu BSON ObjectId.

Tie-breaker duy nhất giúp không bỏ sót các item có timestamp bằng nhau. Nhưng cursor **không tự tạo snapshot**: bản ghi được cập nhật hoặc đổi `createdAt` trong lúc duyệt có thể đổi vị trí. Nếu export cần ảnh chụp nhất quán, phải dùng cách khác phù hợp DBMS.

### 8.2. Phân trang ổn định khi dữ liệu đang ghi

Một batch quét để đối soát có thể cố định một **high-water mark** hoặc snapshot trước khi bắt đầu. Ví dụ chỉ xử lý item có `createdAt < cutoff`, tránh liên tục kéo thêm record mới vào tập quét.

Tuy nhiên, một item được ghi muộn với `createdAt` cũ vẫn có thể lọt vào khoảng đã quét. Vì vậy, nếu cần **không thiếu bất kỳ bản ghi nào**, phải kết hợp snapshot/change stream/CDC hoặc một giao thức tương đương, không chỉ một mốc thời gian.

## 9. DynamoDB: `Scan` khác `Query`

DynamoDB có hai kiểu đọc quan trọng:

- **`GetItem`**: lấy một item qua khóa chính.
- **`Query`**: đọc item thuộc một partition key xác định và có thể giới hạn theo sort key.
- **`Scan`**: đọc tuần tự/phân đoạn item trong table hoặc index, tùy tham số.

### 9.1. Một Scan có filter vẫn phải đánh giá item trước

Ví dụ AWS SDK for JavaScript v3 ở dạng minh họa:

~~~javascript
import {
  DynamoDBClient
} from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  ScanCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({})
);

const page = await client.send(new ScanCommand({
  TableName: "Orders",
  FilterExpression: "#s = :paid",
  ExpressionAttributeNames: {
    "#s": "status"
  },
  ExpressionAttributeValues: {
    ":paid": "PAID"
  },
  ProjectionExpression: "orderId, #s, createdAt",
  Limit: 20
}));

console.log(page.Items);
console.log(page.LastEvaluatedKey);
~~~

**Ngữ nghĩa quan trọng:** `FilterExpression` của DynamoDB `Scan` được áp dụng **sau khi dịch vụ đọc/đánh giá các item trong phạm vi lượt quét**. Vì vậy:

- `Limit: 20` giới hạn số item được đánh giá trong lượt đó, không đảm bảo trả 20 item phù hợp.
- Một page có thể trả 0 item nhưng `LastEvaluatedKey` vẫn tồn tại.
- Một lượt `Scan` cũng chịu giới hạn dữ liệu đọc cho một trang theo cơ chế dịch vụ, thường tối đa **1 MB trước filter**.
- Filter/projection không khiến những item không phù hợp được bỏ qua miễn phí khi tính chi phí đọc.
- Phân trang chỉ kết thúc khi không còn `LastEvaluatedKey`.

Ví dụ nếu chỉ 1% item là `PAID`, một page đánh giá 20 item có thể trả 0 hoặc 1 item. Không được kết luận “không có đơn PAID” khi response đầu không có `Items`.

### 9.2. Query theo partition và sort key

Thiết kế bảng:

~~~text
PK = CUSTOMER#customer-42
SK = ORDER#2026-11-14T08:15:27.123Z#order-1001
~~~

Truy vấn theo đúng partition:

~~~javascript
import {
  QueryCommand
} from "@aws-sdk/lib-dynamodb";

const page = await client.send(new QueryCommand({
  TableName: "OrdersByCustomer",
  KeyConditionExpression: "PK = :pk",
  ExpressionAttributeValues: {
    ":pk": "CUSTOMER#customer-42"
  },
  ScanIndexForward: false,
  Limit: 20,
  ProjectionExpression: "PK, SK, totalVnd"
}));

console.log(page.Items);
~~~

`Query` giúp giới hạn phạm vi bằng partition key và có thể thêm điều kiện sort key nếu cần. Nếu `SK` chứa timestamp chuẩn hóa UTC với định dạng có thứ tự từ điển, `ScanIndexForward: false` cho phép lấy dữ liệu theo sort key giảm dần trong partition.

Nếu danh sách cần lọc theo `status`, chỉ có `FilterExpression` sau `Query` vẫn có thể phải đọc nhiều item rồi lọc. Có thể cân nhắc khóa khác hoặc GSI theo mẫu truy cập, với chi phí ghi/lưu trữ và mức nhất quán phù hợp.

### 9.3. Phân trang `Scan` tới hết

~~~javascript
let lastEvaluatedKey = undefined;

do {
  const response = await client.send(new ScanCommand({
    TableName: "Orders",
    ProjectionExpression: "orderId, updatedAt",
    Limit: 250,
    ExclusiveStartKey: lastEvaluatedKey
  }));

  for (const item of response.Items ?? []) {
    // Xử lý idempotent, tránh giữ toàn bộ dữ liệu trong RAM.
    await processOneItem(item);
  }

  lastEvaluatedKey = response.LastEvaluatedKey;
} while (lastEvaluatedKey);
~~~

Đây là logic job batch minh họa, không phải endpoint public và chưa có retry/backoff/checkpoint bền vững. Trong production cần:

- Kiểm tra quyền trên table và dữ liệu.
- Đặt ngân sách read capacity hoặc concurrency.
- Xử lý throttling bằng retry/backoff có giới hạn.
- Lưu checkpoint sau khi các item của page đã được xử lý thành công.
- Xử lý sự kiện được đọc lại, item biến mất hoặc cập nhật trong lúc scan.
- Có cơ chế dừng/tạm dừng và metric tiến độ.

### 9.4. `Parallel Scan`

DynamoDB hỗ trợ chia scan qua các segment với `TotalSegments` và `Segment`. Ví dụ bốn worker được chỉ định bốn segment khác nhau.

Parallel Scan có thể tăng throughput khi cần backfill lớn, nhưng cũng:

- Tăng áp lực read capacity và khả năng throttling.
- Đòi checkpoint theo **từng segment**, không chỉ một cursor chung.
- Không tạo thứ tự toàn cục.
- Không tự tạo snapshot nhất quán toàn bảng.

Tùy mức nhất quán đọc và thời điểm cập nhật item, scan trên bảng đang thay đổi có thể cho kết quả không tương ứng một ảnh chụp duy nhất. Nếu cần export chính xác theo thời điểm, nên đánh giá export/backup/PITR và cách bắt thay đổi sau snapshot thay vì dựa thuần vào `Scan`.

## 10. Cassandra: tránh truy vấn không có partition key phù hợp

Trong Cassandra, thiết kế primary key quyết định đường truy cập.

Ví dụ:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id text,
    event_day date,
    event_at timestamp,
    event_id text,
    severity text,
    payload text,
    PRIMARY KEY (
      (tenant_id, device_id, event_day),
      event_at,
      event_id
    )
) WITH CLUSTERING ORDER BY (
    event_at DESC,
    event_id DESC
);
~~~

### 10.1. Truy vấn đúng partition

~~~sql
SELECT event_id, event_at, severity
FROM events_by_device_day
WHERE tenant_id = 'tenant-7'
  AND device_id = 'sensor-01'
  AND event_day = '2026-11-14'
LIMIT 100;
~~~

Truy vấn có đầy đủ partition key, cho phép DBMS định vị một partition và đọc theo clustering key. Nếu cần một khoảng thời gian:

~~~sql
SELECT event_id, event_at, severity
FROM events_by_device_day
WHERE tenant_id = 'tenant-7'
  AND device_id = 'sensor-01'
  AND event_day = '2026-11-14'
  AND event_at >= '2026-11-14T08:00:00Z'
  AND event_at < '2026-11-14T09:00:00Z'
LIMIT 100;
~~~

Đường đọc có phạm vi rõ, nhưng nếu một partition quá lớn hoặc nóng thì vẫn có thể tốn tài nguyên.

### 10.2. Vì sao `ALLOW FILTERING` cần thận trọng?

Một truy vấn như:

~~~sql
SELECT event_id, event_at
FROM events_by_device_day
WHERE severity = 'ERROR'
ALLOW FILTERING;
~~~

có thể buộc Cassandra phải đọc/kiểm tra nhiều dữ liệu vì `severity` không nằm trong khóa chính của bảng mẫu và chưa có index thích hợp. Cú pháp `ALLOW FILTERING` có thể cho phép Cassandra thực hiện cách lọc không được hỗ trợ hiệu quả bởi khóa, **không biến bộ lọc này thành đường truy cập rẻ**.

Điều này đặc biệt nguy hiểm trong endpoint cần p95 ổn định hoặc khi bảng có hàng tỷ event. Không nên dùng `ALLOW FILTERING` như cách sửa mặc định cho truy vấn production.

### 10.3. Thiết kế một bảng đọc theo truy vấn

Nếu nghiệp vụ thường cần “100 event ERROR mới nhất của một tenant trong ngày”, có thể thiết kế bảng khác:

~~~sql
CREATE TABLE error_events_by_tenant_day (
    tenant_id text,
    event_day date,
    event_at timestamp,
    event_id text,
    device_id text,
    payload text,
    PRIMARY KEY (
      (tenant_id, event_day),
      event_at,
      event_id
    )
) WITH CLUSTERING ORDER BY (
    event_at DESC,
    event_id DESC
);
~~~

Khi ghi một event `ERROR`, ứng dụng thêm bản ghi vào bảng đọc này theo đường đồng bộ phù hợp. Query:

~~~sql
SELECT event_id, event_at, device_id
FROM error_events_by_tenant_day
WHERE tenant_id = 'tenant-7'
  AND event_day = '2026-11-14'
LIMIT 100;
~~~

Bảng đọc giúp truy vấn theo mẫu xác định, nhưng tạo **write amplification, lặp dữ liệu và trách nhiệm đồng bộ**. Nếu tenant có số event ERROR rất lớn, partition theo tenant-ngày có thể cần chia thêm bucket.

### 10.4. Scan toàn bảng cho job có chủ đích

Backfill hoặc export một bảng Cassandra lớn có thể cần duyệt theo token range hoặc dùng công cụ/connector phân tán phù hợp. Một câu `SELECT *` không giới hạn qua một client thông thường không phải chiến lược tốt cho hàng tỷ row.

Cần:

- Chia công việc theo token range/partition/key range phù hợp.
- Dùng paging theo driver và giới hạn concurrency.
- Tránh làm quá tải node đang phục vụ ứng dụng.
- Theo dõi retry, tombstone, timeout và topology thay đổi.
- Có snapshot/CDC nếu yêu cầu export nhất quán trong lúc dữ liệu được ghi.

Cassandra không biến một scan rộng thành truy vấn rẻ chỉ vì hệ được phân tán trên nhiều node.

---

## 11. Redis: `SCAN` khác `KEYS`

Trong một kho key-value như Redis, đôi khi ứng dụng cần liệt kê khóa để bảo trì hoặc dọn dữ liệu.

### 11.1. `KEYS` có thể gây rủi ro

~~~text
KEYS session:*
~~~

`KEYS` duyệt toàn keyspace và có thể gây hoạt động chặn/tốn tài nguyên, đặc biệt khi số khóa lớn. Không nên dùng như thao tác lặp lại trong đường request production.

### 11.2. `SCAN` là phép duyệt tăng dần

Ví dụ:

~~~text
SCAN 0 MATCH session:* COUNT 1000
~~~

Kết quả của một lượt `SCAN` gồm:

- Cursor mới.
- Một danh sách khóa được tìm thấy trong lượt đó.

Client tiếp tục dùng cursor trả về cho tới khi cursor trở lại `0`.

`COUNT` là **gợi ý về lượng công việc**, không phải cam kết mỗi lượt trả đúng 1.000 khóa. `MATCH` giúp chọn khóa trả về theo pattern, nhưng không đồng nghĩa Redis chỉ xem xét những khóa khớp pattern.

### 11.3. SCAN không phải ảnh chụp bất biến

Trong một vòng lặp `SCAN` đầy đủ:

- Một khóa có thể xuất hiện nhiều lần.
- Khóa được thêm/xóa trong lúc duyệt có semantics riêng và không phải một snapshot toàn keyspace.
- Client phải xử lý duplicate an toàn.
- Kết quả một page rỗng không có nghĩa đã hết; phải xét cursor.

Ví dụ pseudocode:

~~~javascript
let cursor = "0";

do {
  const result = await redis.scan(cursor, {
    MATCH: "session:*",
    COUNT: 1000
  });

  cursor = result.cursor;

  for (const key of result.keys) {
    await processKeyIdempotently(key);
  }
} while (cursor !== "0");
~~~

Đây là cách biểu diễn logic; API thực tế của thư viện Redis có thể khác. Trong Redis Cluster, quét toàn bộ keyspace có thể cần thực hiện trên các node liên quan theo cách client hỗ trợ, không mặc định một lệnh `SCAN` trên một node đã bao phủ cả cluster.

### 11.4. Tránh phụ thuộc quét keyspace vào luồng chính

Nếu cần liệt kê session theo user hoặc tenant thường xuyên, có thể thiết kế index dữ liệu riêng như set/sorted set, TTL và chiến lược cleanup phù hợp. Nhưng index tự quản lý cũng cần cập nhật nhất quán khi key hết hạn hoặc được xóa.

**SCAN phù hợp cho một số tác vụ quản trị theo batch, không phải lựa chọn mặc định cho mọi truy vấn nghiệp vụ.**

## 12. Graph database: giới hạn điểm xuất phát và độ sâu traversal

Một phép duyệt graph có thể bắt đầu từ một node hoặc từ mọi node.

~~~cypher
MATCH (u:User)
RETURN u.userId
LIMIT 50;
~~~

Truy vấn này không có điều kiện chọn node cụ thể; nó có thể phải scan các node mang nhãn `User` để tạo kết quả. `LIMIT 50` giúp giới hạn số hàng trả về và có thể cho phép dừng sớm trong một số kế hoạch, nhưng không bảo đảm một order ổn định nếu không chỉ định sort.

Truy vấn nên bắt đầu từ định danh:

~~~cypher
MATCH (me:User {userId: $viewerId})
      -[:FOLLOWS]->(followed:User)
RETURN followed.userId AS userId
ORDER BY userId
LIMIT 50;
~~~

Nếu `userId` có unique constraint/index phù hợp, DBMS có thể định vị node nguồn rồi đi theo những cạnh liên quan.

### 12.1. Duyệt nhiều bước

~~~cypher
MATCH (me:User {userId: $viewerId})
      -[:FOLLOWS*1..2]->(candidate:User)
WHERE candidate <> me
RETURN DISTINCT candidate.userId AS candidateId
LIMIT 50;
~~~

Hai bước traversal có thể khám phá rất nhiều đường nếu node nguồn theo dõi nhiều tài khoản và các tài khoản đó có bậc ra rất lớn. `LIMIT 50` ở cuối **không chắc giới hạn số đường trung gian cần mở rộng và khử trùng**.

Giới hạn phạm vi bằng:

- Node bắt đầu xác định qua khóa.
- Relationship type cụ thể.
- Hướng cạnh rõ ràng.
- Độ sâu tối đa.
- Bộ lọc trên node/cạnh khi phù hợp.
- Ngân sách thời gian/query và profiling.

Graph traversal là một dạng đọc theo quan hệ, không nhất thiết là full scan tất cả node. Nhưng nếu không có điểm xuất phát hoặc giới hạn độ sâu, nó có thể tạo khối lượng công việc rất lớn.

---

## 13. Quét lớn phải dùng phân trang, checkpoint và giới hạn tài nguyên

Khi full scan là việc cần làm, không nên thực hiện như một request đồng bộ duy nhất.

### 13.1. Chia nhỏ công việc

Một job phù hợp có thể:

1. Xác định phạm vi: tenant, khoảng ngày, tập khóa, snapshot hoặc watermark.
2. Chia phạm vi thành những segment/bucket ổn định.
3. Xử lý từng batch nhỏ.
4. Ghi checkpoint sau khi batch đã được xử lý thành công.
5. Có retry/backoff và giới hạn số worker.
6. Có khả năng tạm dừng và tiếp tục.
7. Đo số item đã xử lý, lỗi, throughput, lag và chi phí.
8. Đối soát kết quả cuối.

### 13.2. Checkpoint không đơn thuần là offset

Ví dụ:

~~~json
{
  "jobId": "backfill-orders-20261114",
  "tenantId": "tenant-7",
  "segmentId": "segment-03",
  "lastProcessedId": "order-103900",
  "processedCount": 3900,
  "failedCount": 2,
  "snapshotWatermark": "source-version-8112"
}
~~~

Checkpoint cần trả lời:

- Khoảng nào đã xử lý **bền vững**?
- Nếu retry page vừa xử lý, có tạo side effect trùng không?
- Điều gì xảy ra nếu dữ liệu được thêm/xóa trong lúc quét?
- Làm sao phục hồi nếu worker khác tiếp quản?
- Nếu dùng parallel scan, checkpoint có được giữ theo từng segment không?

### 13.3. Idempotency của xử lý từng item

Một backfill chỉ ghi đè theo ID/version có thể dễ chạy lại. Một job “tăng counter” trên mỗi record có thể tăng hai lần khi retry nếu thiếu deduplication.

Phân biệt:

~~~text
Đặt giá trị theo ID và version    -> có thể thiết kế idempotent
Cộng doanh thu theo mỗi record    -> phải chống đếm trùng
Gửi email cho mỗi record          -> side effect cần kiểm soát riêng
Xóa từng record                   -> cần bảo đảm không xóa nhầm dữ liệu mới
~~~

### 13.4. Throttle và backpressure

Một job scan không nên lấy toàn bộ khả năng đọc của DBMS khiến API khách hàng bị timeout. Có thể dùng:

- Rate limit theo item/byte/read capacity.
- Giới hạn concurrency/segment.
- Exponential backoff với jitter khi bị throttle.
- Theo dõi p95/p99 của workload online.
- Tạm dừng job khi áp lực quá lớn.
- Chạy trong khoảng vận hành phù hợp nếu SLO cho phép.

Backpressure không chỉ là giảm `batchSize`. Một batch nhỏ nhưng hàng nghìn worker chạy đồng thời vẫn có thể tạo tải rất lớn.

## 14. Dữ liệu thay đổi trong lúc quét: có cần snapshot?

Một full scan có thể mất nhiều giờ. Trong thời gian đó:

- Một item mới được tạo.
- Một item bị xóa.
- Trường trạng thái của item thay đổi.
- Khóa phân vùng hoặc sort key thay đổi.
- Dữ liệu được chuyển sang shard/bucket khác.

Kết quả quét không tự tương ứng “toàn bộ dữ liệu ở đúng một thời điểm”.

### 14.1. Ba mục tiêu khác nhau

| Mục tiêu | Chiến lược cần cân nhắc |
|---|---|
| Xử lý tất cả item đang tồn tại tại thời điểm bắt đầu | Snapshot/export nhất quán hoặc cơ chế đọc có mốc |
| Xử lý item hiện có và cả thay đổi trong lúc quét | Snapshot/backfill kết hợp CDC/change stream |
| Làm mới dần read model, cho phép eventual consistency | Scan idempotent và đối soát định kỳ |

Nếu job đòi “không thiếu một thay đổi nào”, chỉ sử dụng cursor tăng dần theo ID có thể chưa đủ, nhất là khi item được tạo muộn nhưng có ID nhỏ hơn cursor hoặc bị chuyển khóa.

### 14.2. High-water mark

Một cách hữu ích cho một số workload là cố định cutoff:

~~~text
Chỉ xử lý createdAt < 2026-11-14T08:00:00Z
~~~

Điều này giảm nguy cơ job liên tục thấy record mới, nhưng **không tự chống item đến muộn với createdAt cũ**. Cần dữ liệu phát sinh sau mốc snapshot được thu thập riêng nếu mục tiêu đòi tính đầy đủ.

### 14.3. Đọc mạnh không tự có snapshot toàn tập

Một số DBMS hỗ trợ strong consistent read trên từng item. Điều đó không nhất thiết tạo một snapshot nhất quán của **toàn bộ scan kéo dài**. Phải phân biệt phạm vi bảo đảm của mỗi request/item/page với bảo đảm “toàn bộ tập như ở thời điểm T”.

## 15. Kiểm soát phạm vi trong API production

Một endpoint nhận các tham số tùy ý dễ trở thành “full scan as a service” nếu không thiết kế giới hạn.

### 15.1. Một hợp đồng API

~~~http
GET /tenants/tenant-7/events?deviceId=sensor-01&from=2026-11-01T00:00:00Z&to=2026-11-02T00:00:00Z&limit=100
~~~

Backend cần:

1. Xác thực người gọi và tenant được phép.
2. Yêu cầu `deviceId` hoặc một khóa định vị phù hợp với index.
3. Giới hạn khoảng thời gian tối đa theo loại endpoint.
4. Giới hạn `limit`, số byte response và timeout.
5. Áp đúng sort và tie-breaker.
6. Trả cursor opaque gắn với filter/sort và tenant.
7. Từ chối hoặc chuyển sang job export khi người dùng đòi phạm vi quá lớn.

### 15.2. Đừng dùng filter sau khi lấy page

Sai về ngữ nghĩa:

~~~text
1. Đọc 100 item mới nhất của tenant.
2. Lọc ra những item thuộc deviceId = sensor-01.
3. Trả tối đa 20 item.
~~~

Nếu 100 item đầu không chứa dữ liệu của thiết bị này nhưng 20 item phù hợp nằm phía sau, API trả thiếu dù còn dữ liệu.

Đúng hơn là **lọc theo deviceId trong tập ứng viên rồi lấy 20 kết quả phù hợp** bằng đường truy cập có index/key phù hợp.

Với một số DBMS có FilterExpression sau bước đọc giới hạn, backend phải tiếp tục phân trang theo semantics của sản phẩm để đủ kết quả hoặc kết luận đã hết.

### 15.3. Chặn truy vấn không có ranh giới

Các tình huống cần cân nhắc từ chối trực tiếp ở API:

- `from` và `to` đều trống khi không có khóa lọc chặt.
- Yêu cầu toàn bộ tenant mà tenant có hàng trăm triệu item.
- `limit` quá lớn hoặc không được cung cấp giá trị tối đa.
- Truy vấn sort theo thuộc tính chưa có đường truy cập phù hợp.
- Truy vấn graph không giới hạn số hops.
- Quét cùng lúc mọi shard qua endpoint dành cho người dùng cuối.

Khi yêu cầu lớn là hợp lệ, hãy cung cấp **job bất đồng bộ có trạng thái và kết quả xuất**, không biến một HTTP request thành công việc kéo dài hàng giờ.

## 16. Bảo mật khi triển khai scan

Scan rộng làm tăng rủi ro lộ dữ liệu vì chạm tới nhiều item hơn bình thường.

### 16.1. Tenant isolation

Ngay cả khi một job chỉ xuất dữ liệu của một tenant, filter theo tenant phải được thực thi **trước khi dữ liệu rời khỏi phạm vi được phép**, không chỉ tải mọi tenant vào ứng dụng rồi bỏ bớt.

Một lỗi quên điều kiện tenant trong `Scan` hoặc `find` có thể làm log/export chứa dữ liệu không được phép truy cập.

### 16.2. Least privilege

- Tách quyền chạy batch/export khỏi quyền của endpoint thông thường.
- Giới hạn collection/table và trường nhạy cảm có thể đọc.
- Không log toàn bộ payload của record đã quét.
- Mã hóa file xuất và thiết lập thời hạn lưu.
- Ghi audit ai chạy scan, phạm vi nào và kết quả đi đâu.
- Kiểm soát số lượng job song song theo tenant.

### 16.3. Scan và dữ liệu đã hết hạn

Nếu item đã qua `expiresAt` nhưng cleanup TTL chưa xóa vật lý, job export có thể vẫn thấy nó. Phải áp dụng retention/authorization khi xuất, không coi “còn trong DB” đồng nghĩa “được phép xuất”.

### 16.4. Nguy cơ làm nghẽn hệ

Endpoint cho người dùng gửi truy vấn scan tùy ý có thể trở thành vector làm cạn tài nguyên. Cần quota, rate limit, timeout, giới hạn đồng thời, xác thực và từ chối phạm vi quá rộng.

Đây là kiểm soát an toàn vận hành, không chỉ tối ưu hiệu năng.

---

## 17. Quy trình quyết định: đọc theo khóa, scan một phần hay full scan?

~~~mermaid
flowchart TD
  A["Xác định câu hỏi nghiệp vụ"] --> B{"Cần toàn bộ dữ liệu?"}
  B -->|"Không"| C["Xác định tenant, ID, time range, sort"]
  C --> D{"Có key/index phục vụ?"}
  D -->|"Có"| E["Query trong partition/index range"]
  D -->|"Không"| F["Thiết kế index/read model hoặc điều chỉnh API"]
  B -->|"Có"| G{"Có phải công việc online?"}
  G -->|"Không"| H["Batch/export có checkpoint và throttle"]
  G -->|"Có"| I["Xem xét aggregate/index/cache, đặt ngân sách"]
  E --> J["Đo rows/bytes scanned và p95/p99"]
  F --> J
  H --> K["Đối soát, theo dõi tiến độ và rủi ro stale"]
  I --> J
~~~

Nên hỏi theo thứ tự:

1. Tập kết quả cần trả thực sự gồm bao nhiêu phần trăm dữ liệu?
2. Có thể lọc bằng tenant, ID hoặc partition key không?
3. Có thể giới hạn khoảng thời gian hoặc các nhóm vật lý liên quan không?
4. Có index nào hỗ trợ cả filter lẫn sort không?
5. API cần dữ liệu tức thời hay có thể dùng aggregate/read model?
6. Nếu bắt buộc scan, job có được phép chạy ngoài đường request không?
7. Có cách retry/checkpoint/đối soát không?
8. Có ngân sách tài nguyên và quyền dữ liệu phù hợp không?

## 18. Thực hành tổng hợp: hệ thống nhật ký IoT

Giả sử có dữ liệu:

~~~json
{
  "eventId": "evt-9001",
  "tenantId": "tenant-7",
  "deviceId": "sensor-01",
  "severity": "ERROR",
  "eventAt": "2026-11-14T08:15:27.123Z",
  "ingestedAt": "2026-11-14T08:15:30.000Z",
  "payload": "..."
}
~~~

Nhu cầu:

| ID | Câu hỏi | Đặc tính |
|---|---|---|
| Q1 | Lấy một event theo ID | Point lookup |
| Q2 | Lấy 100 event mới nhất của thiết bị trong một ngày | Partition/range read |
| Q3 | Lấy 100 ERROR mới nhất của tenant trong 24 giờ | Truy vấn theo trạng thái + thời gian |
| Q4 | Xuất mọi event tháng trước của tenant | Scan lớn có chủ đích |
| Q5 | Xây lại bảng tổng hợp theo giờ | Backfill/aggregation |
| Q6 | Tìm mọi event có payload chứa chuỗi tùy ý | Có thể cần search index/chức năng chuyên biệt |

### 18.1. Chọn cấu trúc cho Q2

Ví dụ wide-column:

~~~text
Partition key = (tenantId, deviceId, eventDay)
Clustering    = (eventAt DESC, eventId DESC)
~~~

Truy vấn Q2 chỉ cần đọc partition và dải thời gian phù hợp. Với Q3, một bảng/chỉ mục theo `(tenantId, severity, eventDay)` và clustering theo thời gian có thể cần thiết nếu Q3 quan trọng. Không nên dùng full scan raw events cho mọi request Q3.

### 18.2. Xử lý Q4 thành batch

Q4 yêu cầu toàn bộ event tháng trước: scan là hợp lý. Nhưng cần:

- Xác định tenant và khoảng thời gian bằng nguồn được phép.
- Dùng snapshot hoặc watermark/CDC nếu export cần đầy đủ.
- Chia theo ngày/partition hoặc segment.
- Rate limit và giới hạn worker.
- Lưu checkpoint sau từng batch.
- Mã hóa file xuất, ghi manifest và kiểm tra checksum.
- Không tải toàn bộ kết quả vào bộ nhớ của một API server.

### 18.3. Chọn công cụ cho Q6

Nếu `payload` chứa văn bản và người dùng thường xuyên tìm nội dung tùy ý, full scan mọi document mỗi lần tìm kiếm sẽ tốn kém. Có thể cân nhắc full-text/search index hoặc hệ tìm kiếm riêng theo quyền và freshness được định nghĩa rõ.

Nhưng nếu Q6 chỉ chạy hiếm trong một tập nhỏ của một thiết bị/ngày, scan trên phạm vi đã giới hạn có thể chấp nhận. **Không cần thêm một hệ thống mới chỉ vì một truy vấn hiếm chưa được đo.**

## 19. Bài tập tự luyện

### Bài 1: Phân biệt chi phí quét

Collection có 100 triệu document. API yêu cầu 10 document cuối của `customerId = C42`.

Giải thích:

1. Vì sao `limit(10)` không tự bảo đảm đọc ít?
2. Query cần filter và sort nào?
3. Compound index nào có thể phù hợp?
4. Cần xem metric nào trong `explain("executionStats")`?
5. Nếu C42 có 20 triệu document, cần thêm ranh giới nào?

*Gợi ý:* dùng `customerId` cùng `createdAt DESC, _id DESC`; cân nhắc phân vùng thời gian và keyset pagination theo workload.

### Bài 2: DynamoDB Scan có page rỗng

Một `Scan` dùng `Limit = 100` và `FilterExpression` theo trạng thái `FAILED`. Response có `Items = []` nhưng `LastEvaluatedKey` khác rỗng.

Hãy giải thích vì sao không thể kết luận không có item FAILED, và viết logic tiếp tục trang kế tiếp.

### Bài 3: Cassandra và `ALLOW FILTERING`

Bảng được khóa theo `(tenantId, deviceId, eventDay)`. Người dùng thường tra cứu tất cả event ERROR của tenant mà không biết deviceId.

Hãy nêu:

1. Vì sao bảng gốc không phục vụ trực tiếp mẫu này một cách hiệu quả?
2. Tại sao `ALLOW FILTERING` không phải giải pháp tối ưu mặc định?
3. Một bảng đọc hoặc index theo mẫu nào có thể phù hợp?
4. Nếu tenant có tải cực lớn, partition theo tenant-ngày có thể gặp vấn đề gì?

### Bài 4: Redis SCAN và retry

Một job dùng `SCAN` để xử lý mọi khóa `session:*`. Trong lúc scan, khóa được tạo và xóa. Hãy giải thích vì sao phải xử lý duplicate, vì sao không coi một vòng scan là snapshot và khi nào cần dùng một nguồn index hoặc snapshot khác.

### Bài 5: Xuất dữ liệu cho kiểm toán

Một job phải xuất 500 triệu record trong lúc hệ thống tiếp tục ghi.

Thiết kế:

- Cách chia segment.
- Cách tạo mốc snapshot hoặc ghi nhận thay đổi.
- Cấu trúc checkpoint.
- Giới hạn read throughput.
- Quy tắc retry idempotent.
- Cách phát hiện thiếu/nhân đôi record.
- Cách bảo vệ dữ liệu xuất và xác minh kết quả cuối.

### Bài 6: Tính chi phí

Giả sử mỗi full scan đọc logic khoảng 25 GiB và chạy 12 lần/ngày.

Tổng khối lượng logic được xem xét:

\[
25 \times 12 = 300\ \text{GiB/ngày}.
\]

Đây không phải số byte đĩa thực tế; cache, compression, index và engine có thể làm thay đổi. Hãy so sánh với phương án index giúp query chỉ xem xét 50 MiB mỗi lượt, đồng thời tính chi phí lưu trữ và duy trì index khi ghi.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi `LIMIT` là giới hạn công việc quét | Truy vấn vẫn đọc rất nhiều dữ liệu | Thiết kế filter/index và đo examined rows/keys |
| Lọc tenant ở application sau khi lấy dữ liệu | Có thể rò rỉ dữ liệu và tốn tài nguyên | Kiểm tra quyền, lọc từ nguồn |
| Scan trên endpoint người dùng cuối | Timeout, nghẽn DBMS | Giới hạn phạm vi hoặc chuyển sang batch/export |
| Thêm index riêng cho mọi trường | Tăng chi phí ghi/lưu trữ | Ưu tiên access pattern và đo usage |
| Coi IXSCAN luôn nhanh | Full index scan vẫn có thể lớn | Quan sát phạm vi và keys examined |
| Dùng `ALLOW FILTERING` để chữa schema Cassandra | Quét phân tán khó dự đoán | Thiết kế lại partition/read model |
| Hiểu `Scan Limit` của DynamoDB là số kết quả sau filter | Trang rỗng hoặc thiếu item dù còn dữ liệu | Theo dõi `LastEvaluatedKey` và tiếp tục đúng |
| Dùng Redis `KEYS` thường xuyên trên keyspace lớn | Có thể gây nghẽn | Dùng `SCAN` cho batch, hoặc index riêng |
| Kết thúc vòng scan khi một page rỗng | Bỏ sót dữ liệu | Dùng cursor/continuation token chính xác |
| Không có checkpoint | Job thất bại phải chạy lại từ đầu | Lưu tiến độ theo segment |
| Retry không idempotent | Đếm trùng hoặc side effect lặp | Dedupe/version/conditional write |
| Không xác định snapshot semantics | Export thiếu hoặc không nhất quán | Snapshot/CDC và đối soát |
| Chạy quá nhiều scan song song | Throttling và suy giảm API chính | Concurrency budget/backpressure |
| Không giới hạn traversal graph | Bùng nổ số đường quan hệ | Node nguồn, loại cạnh, số hops, timeout |
| Bỏ qua TTL khi export | Xuất dữ liệu quá hạn | Áp retention tại đường xuất |
| Chỉ đo latency trung bình | Che khuất p99, cache pressure và hotspot | Đo examined bytes/keys, p95/p99, throughput |

## 21. Kết luận

**Quét toàn bộ dữ liệu không tự sai**, nhưng cần được xem là một quyết định có chủ đích với phạm vi, mục tiêu và ngân sách rõ ràng.

Đối với truy vấn online:

- Định vị dữ liệu bằng **tenant, ID, partition key và time range** khi có thể.
- Chọn index/read model phù hợp cả **điều kiện lọc và thứ tự sắp xếp**.
- Giới hạn page size, projection, timeout và số partition phải chạm.
- Không coi `LIMIT` hoặc filter sau khi đọc là bảo đảm đọc ít.
- Đo execution plan, số record/keys examined và p95/p99 thay vì chỉ nhìn số kết quả.

Đối với công việc thật sự cần scan toàn bộ:

- Tách khỏi request path.
- Phân đoạn, phân trang, checkpoint và retry idempotent.
- Giới hạn throughput/concurrency để không ảnh hưởng workload chính.
- Xác định mức nhất quán mong muốn khi dữ liệu đang thay đổi.
- Đối soát kết quả, bảo vệ dữ liệu và ghi audit.

**Thiết kế CRUD và truy vấn NoSQL tốt không chỉ biết lấy dữ liệu đúng; nó còn biết chính xác phải đi qua bao nhiêu dữ liệu, vì sao cần đi qua chừng đó và làm thế nào để giới hạn tác động lên toàn hệ thống.**
