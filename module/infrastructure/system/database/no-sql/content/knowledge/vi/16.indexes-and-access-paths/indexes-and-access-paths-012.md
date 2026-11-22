# Đọc kế hoạch, thống kê truy vấn hoặc công cụ giải thích theo từng hệ NoSQL

## 1. Vì sao phải nhìn cách truy vấn được thực thi?

Giả sử một ứng dụng bán hàng có 5 triệu đơn hàng. Màn hình quản trị cần lấy **20 đơn thanh toán gần đây nhất của khách C007 thuộc tenant T01**:

```text
tenantId = T01
customerId = C007
status = PAID
sort = createdAt DESC, orderId DESC
limit = 20
```

Một truy vấn có thể trả đúng 20 đơn nhưng phải đọc hàng triệu document, nhiều partition hoặc hàng chục nghìn cạnh graph. Trên dữ liệu thử nghiệm chỉ có vài dòng, hiện tượng này hầu như không nhìn thấy. Khi tăng dữ liệu và số người dùng đồng thời, hệ thống có thể đột ngột tăng độ trễ, chi phí đọc và tải CPU/đĩa.

Để hiểu vấn đề, cần phân biệt ba nhóm công cụ:

1. **Execution plan / explain:** cho biết hệ quản trị dự định hoặc thực tế sử dụng những bước nào để thực hiện truy vấn: tìm qua index, quét dữ liệu, lọc, sắp xếp, mở rộng quan hệ, lấy document gốc…
2. **Query statistics / metrics:** cho biết số mục chỉ mục, bản ghi hoặc phần tử được đọc; số kết quả trả về; thời gian, bộ nhớ, I/O và tài nguyên bị tiêu tốn.
3. **Tracing / profiling / monitoring:** cho biết thao tác diễn ra ở node nào, bao lâu, có chờ mạng/đĩa hay không, và hành vi dưới tải thật theo thời gian.

**Không phải hệ NoSQL nào cũng có lệnh `EXPLAIN` như SQL.** MongoDB cung cấp `explain()` với thống kê thực thi; Neo4j có `EXPLAIN`/`PROFILE`; Cassandra thường sử dụng tracing và chỉ số của cluster; DynamoDB cung cấp thống kê item đọc/capacity; Redis core chủ yếu quan sát lệnh, độ trễ và cấu trúc key; Elasticsearch/OpenSearch có Search Profile API.

Mục tiêu của bài học là biết **cần mở công cụ nào, đọc tín hiệu nào và quyết định chỉnh sửa gì**, thay vì mặc định thấy một truy vấn chậm thì thêm một index.

## 2. Chỉ mục và đường truy cập liên quan thế nào?

Một hệ dữ liệu phải chọn **cách tìm các phần tử phù hợp** trước khi trả kết quả.

Ví dụ khái niệm:

```text
Truy vấn: tenant=T01 AND status=PAID, mới nhất trước, lấy 20
                                    |
               +--------------------+-------------------+
               |                                        |
               v                                        v
       Không có index phù hợp                    Có index phù hợp
               |                                        |
       Quét nhiều bản ghi                          Đi vào dải key
               |                                        |
       Lọc tenant/status                          Quét dải index
               |                                        |
          Sắp xếp nhiều                         Đã có thứ tự cần thiết?
               |                                        |
           Lấy top 20                                 Lấy top 20
```

Đây là hai khả năng minh họa, **không phải mọi optimizer đều có đúng hai lựa chọn**. Truy vấn có index vẫn có thể phải đọc nhiều document; hệ quản trị có thể chọn quét vì tập dữ liệu nhỏ, độ chọn lọc thấp hoặc chi phí dự đoán. Các hệ NoSQL có thể cố định đường truy cập theo khóa phân vùng thay vì chọn plan linh hoạt.

### Những khái niệm nên nhận diện

| Thuật ngữ | Ý nghĩa | Câu hỏi khi đọc kế hoạch |
|---|---|---|
| **Point lookup** | Tìm theo khóa xác định | Có đọc đúng key/partition cần thiết không? |
| **Index scan / seek** | Tìm trong cấu trúc chỉ mục | Index nào được dùng, số mục được xét? |
| **Full scan** | Xem nhiều/toàn bộ dữ liệu trong phạm vi | Scan là hợp lý hay dấu hiệu thiếu đường truy cập? |
| **Fetch / document read** | Lấy bản ghi gốc sau khi qua index | Có phải đọc document cho từng ứng viên không? |
| **Filter** | Loại bản ghi không thỏa điều kiện | Filter có chạy sau khi đọc quá nhiều dữ liệu? |
| **Sort** | Sắp xếp kết quả | Có tận dụng thứ tự index không, có tốn bộ nhớ/đĩa? |
| **Aggregation** | Gom nhóm/tính toán | Có phải giữ khối lượng trung gian lớn? |
| **Graph expand** | Duyệt cạnh từ node | Fan-out và số hop có tăng quá rộng? |
| **Partition read** | Đọc tập dữ liệu theo khóa phân vùng | Có đụng quá nhiều partition/nút không? |
| **Covered query** | Dùng dữ liệu từ index đủ trả kết quả | Có tránh fetch document gốc không? |

Một plan hiệu quả phải được đánh giá theo **truy vấn cụ thể, tập dữ liệu thực và mục tiêu độ trễ**, không phải theo tên stage nghe có vẻ tốt.

## 3. Đọc ba số liệu nền tảng: đã xét bao nhiêu, trả bao nhiêu, tốn bao lâu?

Giả sử hệ thống đọc 100.000 ứng viên, lọc còn 20 kết quả. Ta có thể xem tỷ lệ:

\[
\text{Read amplification} =
\frac{\text{số đơn vị dữ liệu đã xét}}{\max(1,\text{số kết quả trả về})}
\]

Nếu đọc 100.000 document để trả 20, tỷ lệ theo document là 5.000:1. **Đây là tín hiệu đáng điều tra, không phải một ngưỡng lỗi tuyệt đối.** Với truy vấn tổng hợp cần đọc tất cả sự kiện, việc đọc nhiều bản ghi có thể là đúng; với point lookup thì không hợp lý.

Một chỉ số khác là độ chọn lọc (*selectivity*):

\[
\text{Selectivity} =
\frac{\text{số bản ghi thỏa điều kiện}}{\text{số bản ghi trong phạm vi xét}}
\]

Điều kiện lọc giữ 1% dữ liệu có độ chọn lọc cao hơn điều kiện giữ 90%. Trong thực tế, **thứ tự index, tương quan giữa các trường, sự phân bố tenant và các điều kiện sắp xếp** quyết định index có mang lại lợi ích không.

### Không đánh đồng các loại số đếm

- **Index entries/keys examined:** bao nhiêu mục chỉ mục đã được duyệt; có thể nhiều hơn số document vì multikey, các nhánh OR hoặc cách index tổ chức.
- **Documents/records examined:** bao nhiêu bản ghi gốc được đọc/kiểm tra.
- **Items scanned:** bao nhiêu item được xem xét ở datastore; không nhất thiết trùng với số item trả về.
- **Rows/operators in plan:** số record trung gian đi qua một stage, không nhất thiết là số record cuối.
- **Result count:** kết quả trả về sau filter, sort, limit.
- **Elapsed time:** chịu ảnh hưởng CPU, cache, I/O, mạng, tải đồng thời, serialization, scheduling và client.

Một plan có `nReturned=0` nhưng vẫn đọc hàng triệu document có thể là vấn đề lớn. Vì vậy **đừng chia tỷ lệ và kết luận từ số kết quả bằng 0 mà bỏ qua tổng lượng đọc**.

## 4. Ví dụ truy vấn xuyên suốt

Giả sử collection MongoDB `orders` có schema:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T01",
  customerId: "C007",
  status: "PAID",
  createdAt: ISODate("2026-11-10T08:30:00Z"),
  totalVnd: 520000,
  shipping: { city: "Hà Nội" },
  items: [
    { sku: "P10", quantity: 2 },
    { sku: "P20", quantity: 1 }
  ]
}
```

Mẫu truy vấn mục tiêu:

```javascript
db.orders.find(
  {
    tenantId: "T01",
    customerId: "C007",
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
```

Khi đọc công cụ giải thích ở các hệ, nên đặt cùng một nhóm câu hỏi:

1. Có **lọc tenant và khóa khách hàng trước** khi phải đọc lượng lớn dữ liệu không?
2. Điều kiện `status` được áp dụng ở đâu?
3. Thứ tự `createdAt DESC, _id DESC` có được hỗ trợ bởi index/khóa sắp xếp không?
4. Hệ quản trị phải đọc bao nhiêu ứng viên để trả 20?
5. Có phải đưa dữ liệu trung gian sang bộ nhớ hoặc đĩa để sort/group không?
6. Độ trễ dưới tải thật và khi dữ liệu thay đổi có ổn định không?

Các hệ NoSQL trả lời những câu hỏi này bằng **những công cụ khác nhau**.

## 5. MongoDB: `explain()` và các stage quan trọng

MongoDB hỗ trợ giải thích cách một query được thực thi. Với `mongosh`:

```javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C007",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
```

Các mức verbosity thường gặp:

| Mức | Ý nghĩa chính | Khi nào nên dùng |
|---|---|---|
| `queryPlanner` | Thông tin kế hoạch được chọn và ứng viên | Nhìn đường truy cập cơ bản |
| `executionStats` | Kế hoạch được chọn kèm số liệu của lần thực thi giải thích | Điều tra số mục/bản ghi đã xét |
| `allPlansExecution` | Bổ sung thống kê giai đoạn lựa chọn kế hoạch cho các candidate plans | Điều tra vì sao optimizer chọn plan |

**Lưu ý:** `explain()` dùng cơ chế thực thi/thu thập của lệnh giải thích, không mặc nhiên phản ánh toàn bộ độ trễ người dùng thật hoặc hành vi plan cache của request thông thường. Ở các phiên bản MongoDB và execution engine khác nhau, cấu trúc output có thể thay đổi. Không viết code phụ thuộc cứng vào một vị trí JSON của mọi stage trong mọi phiên bản.

### 5.1. Những trường đọc đầu tiên

Trong output `executionStats`, các trường thường hữu ích:

```text
queryPlanner.winningPlan    -> kế hoạch được chọn
executionStats.nReturned   -> số document trả về
executionStats.totalKeysExamined
                            -> số mục index đã xét
executionStats.totalDocsExamined
                            -> số document đã xét
executionStats.executionTimeMillis
                            -> thời gian thực thi được đo trong explain
executionStats.executionStages
                            -> các bước chi tiết của quá trình thực thi
```

Ví dụ **giả định**:

```json
{
  "executionStats": {
    "nReturned": 20,
    "executionTimeMillis": 190,
    "totalKeysExamined": 0,
    "totalDocsExamined": 750000
  }
}
```

Nếu plan cho thấy một `COLLSCAN` hoặc đường quét rộng để tìm 20 đơn, cần điều tra index và điều kiện query. Nhưng không được coi số minh họa này là benchmark thực của MongoDB.

### 5.2. Nhận biết `COLLSCAN`, `IXSCAN` và `FETCH`

Một dạng plan theo mô hình stage phổ biến:

```text
LIMIT
  |
  SORT
   |
  COLLSCAN
```

`COLLSCAN` cho biết quét collection. Với 5 triệu document, việc quét có thể đắt, nhất là khi chỉ cần 20 kết quả.

Nếu có index phù hợp, có thể xuất hiện:

```text
LIMIT
  |
 FETCH
  |
IXSCAN
```

- `IXSCAN`: duyệt mục của index.
- `FETCH`: lấy document gốc khi cần thêm field/kiểm tra điều kiện.
- `LIMIT`: dừng sau một số kết quả, nếu các bước trước cho phép.

Stage **SORT** không xuất hiện trong một plan có thể là dấu hiệu thứ tự index đã đáp ứng sort, nhưng phải xem kế hoạch thực tế. Tương tự, `IXSCAN` không có nghĩa truy vấn hiệu quả nếu nó duyệt vài triệu index entries để trả một nhóm nhỏ kết quả.

**Chú ý phiên bản:** trong MongoDB có nhiều execution engine, chẳng hạn classic và slot-based execution (SBE). Một số bản explain trình bày `queryPlan`, `slotBasedPlan` hoặc cấu trúc stage khác. Hãy đọc ý nghĩa các thao tác và số liệu tổng hợp, không mặc định mọi kết quả đều là một cây `IXSCAN → FETCH` theo đúng hình thức trên.

### 5.3. Tạo index theo mẫu truy vấn

Với filter bằng nhau theo `tenantId`, `customerId`, `status` rồi sort giảm dần theo `createdAt` và `_id`:

```javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Sau khi tạo index, chạy lại **cùng filter, sort, projection, limit** với `explain("executionStats")`. Các câu hỏi:

- `totalDocsExamined` có giảm rõ rệt?
- `totalKeysExamined` có hợp lý so với số kết quả?
- Có tránh được sort tốn nhiều tài nguyên không?
- Hệ quản trị chọn index mong đợi hay chọn index khác?
- Chi phí ghi và dung lượng index có chấp nhận được?

Lý do index này đáng xem xét: các trường equality đặt trước các trường dùng để duyệt theo thứ tự. Tuy nhiên, **không có thứ tự index đúng cho mọi truy vấn**. Nếu query thêm điều kiện range theo `totalVnd`, phải xem lại vị trí của trường range so với sort và các truy vấn chủ đạo.

### 5.4. `hint()` chỉ để chẩn đoán, không phải cách chữa đầu tiên

Có thể thử ép một index nhằm so sánh:

```javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C007",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.hint({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
.explain("executionStats");
```

`hint` giúp phân tích một đường truy cập cụ thể. Nhưng ép index lâu dài có thể trở nên kém khi phân bố dữ liệu, schema hoặc phiên bản optimizer thay đổi. Nên dùng hint có chủ đích, được benchmark và có kế hoạch bảo trì, không coi là mặc định tối ưu.

### 5.5. Index scan vẫn có thể đắt

Giả sử index là:

```javascript
db.orders.createIndex({ status: 1 });
```

Nếu 95% đơn đều `PAID`, index chỉ theo status có thể không giúp nhiều. Truy vấn tenant T01, khách C007 vẫn cần xét lượng lớn đơn PAID của nhiều tenant và khách khác.

Một plan dùng `IXSCAN` nhưng có:

```text
totalKeysExamined = 800000
totalDocsExamined = 500000
nReturned = 20
```

vẫn có nguy cơ chậm. **Tên stage không quan trọng bằng lượng công việc và access pattern.**

### 5.6. Covered query và projection

Nếu mọi trường cần lọc và trả về nằm trong index theo điều kiện của database, có thể có một **covered query** không cần fetch document gốc. Điều này giúp giảm I/O trong một số truy vấn.

Ví dụ:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find(
  { tenantId: "T01", status: "PAID" },
  { _id: 1, status: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
```

Tìm xem `totalDocsExamined` có thể bằng 0 và plan có bước projection từ index hay không. **Không mặc định cứ có projection là covered**: nếu query cần field chưa có trong index, hoặc index/mảng/collation có giới hạn, vẫn cần fetch.

### 5.7. Multikey, `$elemMatch` và các điều kiện mảng

Với mảng `items`:

```javascript
db.orders.find({
  tenantId: "T01",
  items: {
    $elemMatch: {
      sku: "P10",
      quantity: { $gte: 2 }
    }
  }
});
```

`$elemMatch` bảo đảm hai điều kiện khớp **cùng một item**, khác với hai điều kiện dot notation tách biệt có thể khớp hai phần tử khác nhau. Một index multikey hỗ trợ đường dẫn mảng có khả năng tăng số mục index so với số document. Khi đọc explain, cần nhớ **một document có thể tạo nhiều index entries**.

Không vội kết luận `totalKeysExamined > totalDocsExamined` nghĩa là hệ có bug; đó có thể là kết quả bình thường của multikey hoặc range scan.

### 5.8. Aggregation và thao tác cần bộ nhớ

MongoDB cũng hỗ trợ explain cho aggregation pipeline:

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "T01",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalPaidVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { totalPaidVnd: -1 } },
  { $limit: 10 }
]);
```

Quan sát liệu `$match` có thể được đẩy vào đường truy cập index, các bước `$group`/`$sort` có tốn bộ nhớ hoặc phải xử lý nhiều group không, và các bước thực thi được hiển thị ra sao theo phiên bản. **Đẩy `$limit` lên trước `$group` để chạy nhanh có thể làm sai kết quả**: phải giữ đúng ngữ nghĩa trước khi tối ưu.

### 5.9. Quan sát truy vấn thật ngoài explain

Một lần explain không đủ thay monitoring. MongoDB còn có các cơ chế như **profiler, diagnostic logs, current operations và công cụ theo dõi query shape** tùy phiên bản/triển khai. Dùng chúng để phát hiện truy vấn chậm thực tế, mức tải đồng thời, plan thay đổi và tác động của cache.

Profiler có thể ghi dữ liệu truy vấn nhạy cảm và tạo overhead. Chỉ bật ở mức độ/phạm vi phù hợp, có retention và quyền đọc. Không bật full profiling không giới hạn trên production chỉ để xem một truy vấn.

## 6. Redis: không có optimizer plan tổng quát cho lệnh key–value

Redis core chủ yếu nhận **command** như `GET`, `HGET`, `ZRANGE`, `SMEMBERS` hoặc `SCAN`. Với key-value, nhiều thao tác có đường truy cập cố định theo key và cấu trúc dữ liệu; không có `EXPLAIN GET key` tương đương MongoDB `explain`.

Ví dụ:

```redis
HSET order:T01:ORD-1001 status PAID totalVnd 520000
HGET order:T01:ORD-1001 status
HGETALL order:T01:ORD-1001
```

Hai lệnh đọc trên có chi phí khác nhau về **khối lượng dữ liệu trả về**. `HGET` đọc một field; `HGETALL` đọc mọi field của hash. Với hash rất lớn, dù lookup theo key chính xác, `HGETALL` vẫn có thể tốn CPU, truyền mạng và bộ nhớ client.

### 6.1. SLOWLOG: lệnh nào tốn thời gian xử lý ở server?

```redis
SLOWLOG GET 10
SLOWLOG LEN
```

`SLOWLOG` ghi lại những lệnh có thời gian thực thi vượt ngưỡng cấu hình. Nó hữu ích để nhận diện các lệnh chậm.

**Giới hạn quan trọng:** thời gian trong Redis SLOWLOG chủ yếu đo **thời gian xử lý lệnh ở server**, không phải end-to-end latency từ phía ứng dụng bao gồm truyền mạng và thời gian gửi kết quả cho client. Vì thế SLOWLOG thấp không chứng minh người dùng không gặp chậm mạng, pooling hoặc xử lý response.

Đừng tùy tiện thay cấu hình `slowlog-log-slower-than` hay `slowlog-max-len` trên hệ sản xuất; làm vậy cần cân nhắc overhead, khả năng lộ tham số lệnh trong log và chính sách vận hành.

### 6.2. INFO commandstats: lệnh nào chiếm tải?

```redis
INFO commandstats
```

Nhóm thống kê theo command có thể cho biết số lần gọi, thời gian xử lý tích lũy, thời gian trung bình và các counter khác tùy phiên bản. Ví dụ, nếu `HGETALL` xuất hiện hàng triệu lần và chiếm nhiều CPU hơn dự kiến, có thể đổi access pattern sang `HMGET` cho các field cần đọc.

**Số liệu tích lũy không cho biết mỗi request người dùng đã làm gì** nếu thiếu metric ứng dụng và tracing. Cần so sánh chênh lệch counter theo thời gian, không chỉ đọc một snapshot bất kỳ.

### 6.3. LATENCY và thông số sức khỏe

```redis
LATENCY LATEST
LATENCY DOCTOR
INFO stats
INFO memory
```

Tùy cấu hình và phiên bản, các công cụ latency có thể giúp phát hiện spike do event nội bộ, I/O, fork hoặc công việc nặng. `INFO memory` cho biết bộ nhớ và áp lực liên quan; không phải execution plan của một `GET`.

### 6.4. `KEYS`, `SCAN` và tìm theo thuộc tính

Không nên dùng:

```redis
KEYS order:*
```

trong một endpoint công khai để tìm đơn, vì `KEYS` có thể quét không gian key và gây ảnh hưởng lớn khi nhiều key.

```redis
SCAN 0 MATCH order:T01:* COUNT 100
```

`SCAN` hỗ trợ duyệt tăng dần thay vì một lệnh quét trả toàn bộ kết quả, nhưng:

- `COUNT` là **gợi ý lượng công việc**, không bảo đảm mỗi lượt trả đúng 100 key.
- Cần tiếp tục bằng cursor trả về cho đến khi trở về cursor kết thúc.
- Trong lúc tập key thay đổi, có thể thấy phần tử lặp hoặc hành vi không giống snapshot bất biến.
- `SCAN` vẫn là một dạng duyệt key, **không thay thế secondary index cho endpoint tra cứu thường xuyên**.

Nếu thường tìm theo status, category hoặc giá, cần index nghiệp vụ phù hợp, công cụ search bổ sung hoặc datastore khác; đồng thời theo dõi chi phí đồng bộ giữa index và dữ liệu gốc.

### 6.5. Tìm “big key” và giới hạn số phần tử trả về

Với set lớn, `SMEMBERS` trả tất cả phần tử; với sorted set lớn, `ZRANGE` nên được dùng cùng phạm vi/lượng kết quả phù hợp. Chỉ thấy thời gian server thấp không đủ nếu response hàng chục MB làm client chậm.

Đọc số lượng phần tử theo kiểu dữ liệu:

```redis
HLEN order:T01:ORD-1001
SCARD orders:by-status:T01:PAID
ZCARD orders:by-time:T01
MEMORY USAGE order:T01:ORD-1001
```

Các lệnh thống kê cũng có chi phí và cần quyền tương ứng. Với hệ lớn, thu thập theo mẫu, tránh quét/tính toán nặng ở giờ cao điểm.

**Cách đọc Redis:** hỏi “lệnh nào, trên kiểu dữ liệu gì, kích thước key/phần tử bao nhiêu, mất bao lâu ở server, bao lâu ở client và có gọi quá thường xuyên không?”.

## 7. DynamoDB: Query/Scan và `ConsumedCapacity`

DynamoDB khác MongoDB ở chỗ bảng có **partition key**, có thể có sort key và secondary indexes. Đường truy vấn hiệu quả thường là **GetItem hoặc Query với khóa phù hợp**, không phải filter tự do trên mọi attribute.

Giả sử bảng có:

```text
PK = "TENANT#T01#CUSTOMER#C007"
SK = "ORDER#2026-11-10T08:30:00Z#ORD-1001"
status = "PAID"
totalVnd = 520000
```

### 7.1. Đọc kết quả Query theo khóa

Một request Query API kiểu low-level:

```json
{
  "TableName": "Orders",
  "KeyConditionExpression": "#pk = :pk AND begins_with(#sk, :prefix)",
  "ExpressionAttributeNames": {
    "#pk": "PK",
    "#sk": "SK"
  },
  "ExpressionAttributeValues": {
    ":pk": { "S": "TENANT#T01#CUSTOMER#C007" },
    ":prefix": { "S": "ORDER#" }
  },
  "Limit": 20,
  "ReturnConsumedCapacity": "TOTAL"
}
```

Yêu cầu dùng `PK` đã biết để giới hạn một partition key và prefix trên sort key. `ReturnConsumedCapacity` giúp quan sát lượng capacity tiêu thụ của request (ở mức được yêu cầu).

### 7.2. Thống kê quan trọng ở response

Những field nên hiểu:

| Field | Diễn giải |
|---|---|
| `Count` | Số item được trả trong response sau filter |
| `ScannedCount` | Số item được đánh giá trước khi áp `FilterExpression` trong request |
| `ConsumedCapacity` | Capacity tiêu thụ do thao tác, theo chế độ báo cáo được yêu cầu |
| `LastEvaluatedKey` | Dấu hiệu còn một phần kết quả để đọc ở trang tiếp theo |
| `Items` | Các item trả về |

**Giới hạn:** `ScannedCount` không phải “tổng số item trong table”, và `ConsumedCapacity` không thể suy trực tiếp từ `Count`. Số liệu trên response chỉ mô tả một request hoặc trang, không nhất thiết toàn bộ truy vấn nếu ứng dụng tự phân trang qua nhiều lần gọi.

### 7.3. Vì sao FilterExpression không thay thế đường truy cập theo khóa?

Giả sử thêm:

```json
{
  "FilterExpression": "#status = :paid",
  "ExpressionAttributeNames": {
    "#status": "status"
  },
  "ExpressionAttributeValues": {
    ":paid": { "S": "PAID" }
  }
}
```

Đây là các thành phần bổ sung vào request Query, không phải request JSON hoàn chỉnh.

`FilterExpression` được áp dụng **sau khi DynamoDB đã đọc item phù hợp KeyConditionExpression trong trang đó**. Vì vậy nó không làm giảm lượng đọc/capacity tiêu thụ chỉ nhờ loại bớt item trả về.

Ví dụ:

```text
KeyCondition đọc/evaluate 100 items
FilterExpression giữ 4 items

ScannedCount = 100
Count        = 4
```

Đây là ví dụ minh họa, không phải số liệu thực của một request. Nếu pattern chủ đạo là “đơn PAID theo tenant và thời gian” nhưng bảng chỉ có khóa theo customer, cần xem **GSI hoặc cấu trúc item/index khác** để đưa status vào đường truy cập, thay vì chỉ thêm filter.

### 7.4. `Limit` và phân trang

Trong DynamoDB, `Limit` giới hạn số item được đánh giá ở một request `Query` (cùng với giới hạn trang do hệ thống), không bảo đảm response có đúng `Limit` item sau filter.

Vì vậy:

```text
Count = 0
LastEvaluatedKey = có giá trị
```

**không có nghĩa đã hết dữ liệu**. Client cần tiếp tục với `ExclusiveStartKey` đến khi không còn `LastEvaluatedKey` hoặc đạt ngân sách/trang theo hợp đồng API.

### 7.5. Query khác Scan

- `GetItem`: lấy item khi biết đầy đủ primary key.
- `Query`: lấy phạm vi theo partition key và điều kiện sort key được hỗ trợ, trên table hoặc index.
- `Scan`: xem item trong table hoặc index theo cơ chế quét, thường tốn nhiều tài nguyên khi phạm vi lớn.

Không kết luận `Scan` lúc nào cũng sai: nó có thể hợp lý cho export, quản trị theo batch hoặc phân tích không thường xuyên. Nhưng dùng Scan cho endpoint cần 20 đơn của một khách trong tập hàng triệu item thường là dấu hiệu **thiết kế key/index chưa khớp access pattern**.

### 7.6. Giám sát và giới hạn DynamoDB

Ngoài thống kê response, cần quan sát **CloudWatch** và công cụ vận hành phù hợp, chẳng hạn:

- Consumed read/write capacity và mức giới hạn/throttle.
- Latency của các thao tác thành công.
- Request bị throttling hoặc lỗi.
- Ảnh hưởng của phân bố key nóng (*hot partition*).
- Mức sử dụng capacity của table và GSI.

Không có một `EXPLAIN` kiểu MongoDB cho mọi DynamoDB Query. **Thiết kế khóa và số item đọc/capacity** chính là những thông tin chính để đánh giá đường truy cập. GSI có tính nhất quán và chi phí riêng; không nên chỉ nhìn một Query nhanh rồi bỏ qua chi phí ghi vào nhiều index.

## 8. Cassandra: CQL tracing, khóa phân vùng và thống kê cluster

Cassandra ưu tiên truy vấn theo **partition key** và **clustering columns**. Nó không hoạt động như một optimizer có thể tùy ý chọn nhiều kế hoạch tương đương cho mọi câu lệnh CQL.

Giả sử bảng:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Đường truy cập được thiết kế cho đơn của **một khách trong một tenant**.

### 8.1. Query đúng với partition key

```sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer
WHERE tenant_id = 'T01'
  AND customer_id = 'C007'
  AND created_at >= '2026-11-01T00:00:00Z'
  AND created_at < '2026-12-01T00:00:00Z'
LIMIT 20;
```

Vì có đủ `tenant_id` và `customer_id`, hệ thống xác định được partition key. Điều kiện trên clustering column giới hạn phạm vi theo thứ tự lưu của partition. Cú pháp/ràng buộc chính xác của range theo clustering column cần đối chiếu phiên bản CQL và cấu hình bảng.

### 8.2. CQL tracing với `cqlsh`

```sql
TRACING ON;

SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer
WHERE tenant_id = 'T01'
  AND customer_id = 'C007'
LIMIT 20;

TRACING OFF;
```

Khi tracing được bật và có quyền/cấu hình thích hợp, `cqlsh` có thể hiển thị session trace gồm những bước server thực hiện, chẳng hạn gửi yêu cầu tới replica, đọc dữ liệu và thời gian của từng hoạt động.

Không phải mỗi trace có cùng chuỗi event. Nội dung phụ thuộc phiên bản Cassandra, topology, cache, truy vấn, consistency level và trạng thái cluster. Tracing có overhead; **không bật cho toàn bộ lưu lượng production để đo hiệu năng thường xuyên**.

### 8.3. Cần nhìn gì trong trace?

- Coordinator nào nhận query?
- Có liên hệ tới bao nhiêu replica/partition?
- Phải chờ replica, disk I/O hoặc công việc compaction/tombstone không?
- Có dấu hiệu đọc nhiều dữ liệu so với kết quả không?
- Độ trễ trong trace so với latency phía ứng dụng thế nào?
- Query đang đọc một partition rất lớn hay nhiều partition?

Với truy vấn theo partition key rõ ràng, thường có cơ hội giới hạn phạm vi đọc tốt hơn truy vấn đòi quét trên non-key column.

### 8.4. `ALLOW FILTERING` không tương đương index phù hợp

Ví dụ không phù hợp với bảng theo khách:

```sql
SELECT *
FROM orders_by_customer
WHERE status = 'PAID';
```

`status` không phải partition/clustering key của bảng trên. Trong nhiều tình huống CQL sẽ từ chối hoặc yêu cầu `ALLOW FILTERING`, tùy schema/index. Cố thêm `ALLOW FILTERING` có thể cho phép truy vấn phải đọc và loại rất nhiều dữ liệu; **đó không phải bằng chứng truy vấn được tối ưu**.

Nếu cần thường xuyên tìm đơn PAID theo tenant và tháng, có thể thiết kế bảng đọc chuyên biệt:

```sql
CREATE TABLE orders_by_status_month (
    tenant_id text,
    status text,
    month_bucket text,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, status, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Chi phí là phải đồng bộ bản biểu diễn mới khi đơn đổi status hoặc bị xóa. Với tenant rất lớn, bucket theo tháng có thể vẫn tạo partition lớn; cần xác định kích thước dữ liệu và phân bố thực.

### 8.5. Thống kê vận hành

Ngoài tracing, Cassandra có các công cụ và chỉ số cluster như:

```text
nodetool tablestats
nodetool tablehistograms <keyspace> <table>
```

Tùy phiên bản, chúng có thể giúp nhìn thống kê bảng, latency và phân bố hoạt động liên quan tới sstable/partition/tombstone. Cũng cần quan sát client-side latency, read/write timeout, compaction backlog, GC, disk I/O và số partition/row được đọc.

Đặc biệt với LSM-tree, **tombstone nhiều hoặc partition quá lớn** có thể gây chậm dù truy vấn đã biết partition key. Tối ưu Cassandra không chỉ là “đã có WHERE partition key”.

## 9. Neo4j: `EXPLAIN` khác `PROFILE`

Trong Neo4j, Cypher là ngôn ngữ mô tả mẫu graph. Công cụ:

- **`EXPLAIN`:** tạo kế hoạch dự kiến **không thực thi query**.
- **`PROFILE`:** thực thi query và thu thập số liệu từng operator.

Ví dụ graph:

```text
(Customer {tenantId:T01, customerId:C007})
             |
          [:PLACED]
             |
             v
       (Order {status:PAID})
             |
          [:HAS_LINE]
             |
             v
          (OrderLine)
```

### 9.1. Xem plan mà không thực thi

```cypher
EXPLAIN
MATCH (c:Customer {tenantId: 'T01', customerId: 'C007'})
      -[:PLACED]->(o:Order)
WHERE o.tenantId = 'T01'
  AND o.status = 'PAID'
RETURN o.orderId AS orderId
ORDER BY orderId
LIMIT 20;
```

Plan có thể hiển thị những operator như:

- `NodeIndexSeek`: tìm node qua index.
- `NodeByLabelScan`: quét node thuộc một nhãn.
- `Expand(All)` hoặc biến thể expand: đi theo relationship.
- `Filter`: kiểm tra điều kiện property.
- `Sort`: sắp xếp kết quả.
- `Limit`: giới hạn số row.
- `CartesianProduct`: ghép hai nhánh không có điều kiện liên kết thích hợp.

**Tên operator và cách trình bày có thể thay đổi** theo version planner/runtime. Quan trọng là hỏi plan bắt đầu từ node nào, mở rộng bao nhiêu cạnh và số row trung gian tăng ra sao.

### 9.2. PROFILE để xem công việc thực

```cypher
PROFILE
MATCH (c:Customer {tenantId: 'T01', customerId: 'C007'})
      -[:PLACED]->(o:Order)
WHERE o.tenantId = 'T01'
  AND o.status = 'PAID'
RETURN o.orderId AS orderId
ORDER BY orderId
LIMIT 20;
```

Tùy phiên bản và runtime, profile có thể hiển thị:

| Chỉ số/operator | Ý nghĩa |
|---|---|
| `Rows` | Số hàng qua từng operator |
| `DbHits` | Lượt truy cập dữ liệu theo cách Neo4j đo |
| `Estimated Rows` | Ước lượng của planner để so với quan sát |
| Page cache hits/misses | Dữ liệu được phục vụ từ cache hay phải đọc thêm |
| `Expand` | Công việc duyệt cạnh từ các node |
| `Sort`/`Eager` | Có khả năng dùng bộ nhớ cho trung gian |
| `CartesianProduct` | Có thể tạo số kết hợp lớn nếu không cố ý |

**Cảnh báo:** `PROFILE` **thực thi truy vấn**. Nếu đặt trước một truy vấn `CREATE`/`MERGE`/`SET`/`DELETE`, nó có thể thực hiện thay đổi thật. Chỉ profile lệnh ghi khi đã chủ động kiểm soát môi trường, transaction và tác động. `EXPLAIN` thích hợp để kiểm tra kế hoạch trước khi thực thi.

### 9.3. Index cho node bắt đầu

Nếu truy vấn thường xuyên tìm Customer theo tenant và ID:

```cypher
CREATE INDEX customer_lookup IF NOT EXISTS
FOR (c:Customer)
ON (c.tenantId, c.customerId);
```

Sau khi index được tạo và trở nên sẵn sàng, xem lại `EXPLAIN`/`PROFILE` để xác định hệ có chọn index seek hay không. Query graph có thể vẫn chậm nếu node C007 có **vài triệu cạnh `PLACED`**: index giúp tìm node đầu, nhưng không làm biến mất chi phí duyệt toàn bộ các cạnh liên quan.

### 9.4. Cảnh báo fan-out và truy vấn nhiều hop

Một truy vấn duyệt sâu:

```cypher
MATCH p = (s:Service {serviceId: 'API'})
          -[:DEPENDS_ON*1..4]->(target:Service)
RETURN target.serviceId, length(p) AS hops
LIMIT 100;
```

Giới hạn output 100 dòng **không bảo đảm chỉ duyệt 100 path**. Nếu graph dày đặc hoặc có chu trình, số đường đi trung gian có thể tăng nhanh. Xem các operator mở rộng, `Rows`, `DbHits` và điều kiện thu hẹp ở từng bước. Giới hạn hop, relationship type, node bắt đầu, query timeout và kiểu uniqueness của path theo đúng nghiệp vụ.

### 9.5. Nhận diện Cartesian product không mong muốn

```cypher
MATCH (c:Customer {tenantId: 'T01'}),
      (p:Product {tenantId: 'T01'})
RETURN c.customerId, p.sku;
```

Nếu có 10.000 Customer và 10.000 Product, biểu thức hai tập không liên kết có thể tạo **100 triệu cặp**. Một operator `CartesianProduct` trong plan là tín hiệu cần hỏi “có thật sự cần ghép mọi khách với mọi sản phẩm không?”. Nếu mục tiêu là sản phẩm mà khách đã mua, nên truy vấn theo **mẫu relationship** thay vì nối hai tập độc lập.

## 10. Elasticsearch/OpenSearch: Search Profile API và search statistics

Elasticsearch/OpenSearch thường được dùng làm search/read model cạnh database nguồn. Đường truy cập dựa trên index, shard và cấu trúc inverted index, khác với point lookup của Redis hay partition key của DynamoDB.

Ví dụ tìm đơn theo trường keyword, số và sort:

```http
POST /orders_search/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "T01" } },
        { "term": { "status": "PAID" } },
        { "range": { "totalVnd": { "gte": 200000 } } }
      ]
    }
  },
  "sort": [
    { "createdAt": { "order": "desc" } },
    { "orderId": { "order": "desc" } }
  ],
  "size": 20
}
```

Ví dụ giả định mapping của `tenantId`, `status` và `orderId` cho phép truy vấn chính xác và sort (chẳng hạn các field keyword), `totalVnd` là numeric, `createdAt` là date. Nếu một field là analyzed text, `term` query và sort có thể không mang ngữ nghĩa mong muốn; cần xem mapping thật.

### 10.1. Bật profiling có chủ đích

```http
POST /orders_search/_search
Content-Type: application/json

{
  "profile": true,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "T01" } },
        { "term": { "status": "PAID" } }
      ]
    }
  },
  "size": 20
}
```

Với profiling, response có thể chứa dữ liệu theo shard về:

- Những thành phần query được thực thi.
- Chi phí thời gian tương đối ở các bước query.
- Breakdown ở các collector hoặc truy vấn con.
- Cách hệ thống xử lý các nhánh truy vấn.

**Giới hạn quan trọng:** profiling bổ sung overhead, và các số thời gian chi tiết thường **không bằng toàn bộ độ trễ end-to-end** (còn scheduling, queue, mạng, fetch/serialization hoặc các công việc không được profile đầy đủ tùy phiên bản). Không bật `"profile": true` cho mọi request production.

### 10.2. Đọc các field thống kê của Search API

Thông tin response thường bao gồm:

```text
took                 -> thời gian phía search engine báo cho request
timed_out            -> query có chạm timeout được báo không
_shards.total        -> số shard liên quan
_shards.failed       -> có shard nào lỗi không
hits.total           -> tổng hit (theo chính sách track_total_hits)
hits.hits            -> những kết quả thuộc trang đang trả
profile              -> thông tin profiling nếu được yêu cầu
```

Không nên nhầm **`hits.total` với số document đã được duyệt**. Nếu cấu hình hạn chế việc đếm total hits, trường total còn có thể mang nghĩa quan hệ “ít nhất” thay vì số chính xác. Hãy đọc `relation` và chính sách `track_total_hits` khi cần số lượng chính xác.

### 10.3. `_explain` khác Search Profile

Một số search engine có API kiểu `_explain` để giải thích **vì sao một document cụ thể khớp và được tính điểm như thế nào**. Nó không tương đương một execution plan của toàn bộ truy vấn.

- **Explain theo document:** trả lời “document này được chấm điểm/khớp vì sao?”.
- **Search Profile:** trả lời “các thành phần search đã tiêu thụ thời gian ở đâu?”.
- **Search metrics/slow logs:** trả lời “truy vấn thực dưới tải có chậm không, shard nào có vấn đề?”.

Chọn đúng công cụ cho câu hỏi, thay vì thấy chữ “explain” rồi kỳ vọng nó trả `COLLSCAN/IXSCAN` như MongoDB.

### 10.4. Shard, mapping và sort

Một truy vấn phải chạy qua nhiều shard có thể cần gom kết quả từ các shard rồi sắp xếp/merge để trả trang cuối. Độ trễ chịu ảnh hưởng số shard, bộ lọc, cardinality, cấu hình cache, từ điển index, tài nguyên node và sort.

Với filter nhiều lần lặp, một số cache có thể mang lại lợi ích; với dữ liệu thay đổi liên tục, cache hit và chi phí duy trì index cũng quan trọng. Không nên kỳ vọng một query nhanh trên index vừa dựng với ít shard sẽ có cùng chi phí khi dữ liệu và số shard tăng mạnh.

## 11. Couchbase: ví dụ hệ NoSQL có `EXPLAIN` riêng

Couchbase hỗ trợ truy vấn theo ngôn ngữ SQL++ (trước đây thường gọi N1QL), qua dịch vụ Query và các loại index thích hợp. Đây là ví dụ hữu ích vì **cùng là NoSQL nhưng có EXPLAIN dạng planner gần với SQL**.

Ví dụ khái niệm:

```sql
EXPLAIN
SELECT o.orderId, o.status, o.createdAt
FROM orders AS o
WHERE o.tenantId = "T01"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Trên triển khai thật, `orders` phải trỏ đúng keyspace/collection theo cấu trúc bucket/scope/collection; query chỉ mang tính minh họa cú pháp phổ biến.

Plan có thể chứa các operator như **IndexScan, Fetch, Filter, Order, Limit** hoặc những biến thể theo phiên bản. Cần xem:

- Có dùng secondary index hay phải scan rộng?
- Có bước `Fetch` đọc document gốc không?
- Có sort sau khi lấy nhiều bản ghi không?
- Các điều kiện được push xuống index scan tới mức nào?

Ngoài `EXPLAIN`, khả năng profiling và query metrics của dịch vụ Query có thể giúp đo thời gian và số thao tác thực. Cách bật profiling, schema output và phạm vi metric phải đối chiếu với phiên bản Couchbase đang dùng.

**Bài học chung:** một engine document khác có thể cung cấp `EXPLAIN` nhưng tên operator và cơ chế index không trùng MongoDB; hãy hiểu mô hình engine thay vì chỉ đối chiếu chữ trong plan.

## 12. So sánh nhanh công cụ theo từng hệ

| Hệ | Công cụ/cách quan sát chính | Tín hiệu đường truy cập | Điểm dễ đọc sai |
|---|---|---|---|
| MongoDB | `explain("executionStats")`, profiler/metrics | `IXSCAN`, `COLLSCAN`, `FETCH`, keys/docs examined | Có `IXSCAN` không đồng nghĩa ít việc; explain không phải latency người dùng |
| Redis | `SLOWLOG`, `INFO commandstats`, `LATENCY`, key cardinality | Loại command, độ lớn key, thời gian xử lý | SLOWLOG không bao gồm toàn bộ network/client latency |
| DynamoDB | `Count`, `ScannedCount`, `ConsumedCapacity`, CloudWatch | GetItem/Query theo key hay Scan; filter sau đọc | FilterExpression không làm giảm item đọc bằng cách tự tạo index |
| Cassandra | `TRACING ON`, metrics/node tools | Partition/clustering key, replica/partition read, tombstones | Tracing không phải general SQL-style optimizer plan |
| Neo4j | `EXPLAIN`, `PROFILE` | Index seek, node scan, expand, rows/DbHits | PROFILE thực thi cả truy vấn ghi |
| Elasticsearch/OpenSearch | `profile: true`, Search API stats, slow logs | Shards, query/collector work, search/fetch | Profile timing không bằng mọi thành phần end-to-end |
| Couchbase | SQL++ `EXPLAIN`, Query metrics/profile | Index scan, fetch, filter, order | Plan format/version riêng, index không tự đảm bảo covered |

Lựa chọn công cụ phải xuất phát từ **kiến trúc truy vấn của chính hệ đó**. Không có một chỉ số duy nhất để so sánh công bằng chi phí giữa Redis command, DynamoDB capacity unit và Neo4j DbHits.

## 13. Một quy trình điều tra truy vấn chậm có thể lặp lại

Giả sử API `GET /orders?status=PAID` có p95 latency cao. Đừng bắt đầu bằng việc tạo index tùy ý. Một quy trình:

### Bước 1 — Xác nhận câu hỏi và bất biến

Ghi cụ thể:

```text
Query name: ListPaidOrdersForCustomer
Principal: tenant từ authentication
Filter: tenantId = ?, customerId = ?, status = PAID
Sort: createdAt DESC, _id DESC
Limit: 20
SLA: p95 <= ngưỡng do sản phẩm xác định
Consistency: có thể dùng read model eventual hay phải đọc source?
```

Tránh tối ưu bằng cách bỏ điều kiện quyền hoặc cắt logic lọc bắt buộc.

### Bước 2 — Thu thập baseline có ngữ cảnh

Đo:

- p50/p95/p99 latency tại API và tại database.
- Kích thước dữ liệu, số tenant, tỉ lệ đơn PAID.
- QPS và concurrency ở thời điểm đo.
- Cache hit ratio, CPU, memory, disk I/O, network và throttling.
- Số kết quả và số dữ liệu đã đọc theo công cụ từng hệ.

**Không so một lần chạy cold-cache trên môi trường A với một lần warm-cache trên môi trường B rồi kết luận index mới nhanh hơn.**

### Bước 3 — Dùng đúng công cụ để thấy đường đọc

```text
MongoDB    -> explain executionStats
Redis      -> SLOWLOG + INFO + size/cardinality + app latency
DynamoDB   -> ReturnConsumedCapacity + Count/ScannedCount
Cassandra  -> cqlsh TRACING + cluster metrics
Neo4j      -> EXPLAIN, sau đó PROFILE cho SELECT/MATCH
Elasticsearch -> search profile + took/shard stats/slow logs
Couchbase  -> EXPLAIN + query metrics
```

Không bắt buộc tất cả công cụ xuất ra một cây execution plan. Mục tiêu là biết **đường truy cập và công việc thực**.

### Bước 4 — Xác định điểm gây chi phí

Các khả năng thường thấy:

1. **Đọc quá rộng:** full scan, thiếu partition key hoặc range quá rộng.
2. **Index chưa phù hợp:** có index nhưng lọc/sort không tận dụng được.
3. **Selectivity thấp:** status phổ biến, index đơn trường không thu hẹp đủ.
4. **Sort/group nặng:** cần đọc và sắp hàng triệu ứng viên.
5. **Hot key/partition:** một tenant/customer có quá nhiều dữ liệu hoặc lưu lượng.
6. **Fan-out graph:** một node có nhiều cạnh, traversal quá nhiều hop.
7. **Tombstone/compaction:** dữ liệu chết làm tăng công việc trên storage engine.
8. **Nghẽn ngoài query:** network, connection pool, throttling, GC, serialization hoặc downstream.

Không phải mọi độ trễ cao đều do thiếu index.

### Bước 5 — Đề xuất thay đổi nhỏ, đo lại

Một số hướng:

- Compound index khớp equality + sort/range trong MongoDB.
- Thay `Scan` bằng `Query` theo PK/GSI trong DynamoDB.
- Thiết kế thêm bảng theo access pattern trong Cassandra.
- Đổi truy vấn graph bắt đầu từ node được index, giới hạn hop/relationship.
- Tránh `KEYS` và `HGETALL` trên dữ liệu lớn, thay cách truy cập Redis.
- Chuyển regex/wildcard quá rộng thành truy vấn search phù hợp và hạn chế input.

Mỗi thay đổi phải được kiểm chứng với **cùng query semantics**. Một truy vấn nhanh hơn vì trả thiếu tenant hoặc bỏ qua một nhánh OR là sai, không phải tối ưu.

### Bước 6 — Kiểm tra chi phí phía ghi và vận hành

Thêm index có thể giúp đọc nhưng đồng thời:

- Tăng dung lượng lưu trữ.
- Tốn thêm ghi/index maintenance.
- Tác động tới bulk import và cập nhật.
- Làm tăng chi phí replication/backup.
- Tạo hot partition hoặc nâng cao complexity của đồng bộ read model.

Đánh giá **tổng chi phí và SLO**, không chỉ một lần query.

### Bước 7 — Quan sát sau triển khai

Đặt metric theo query name/shape, p95/p99, lượng đọc, lỗi timeout/throttle và độ trễ read model. So sánh trước–sau trong cùng điều kiện hoặc thiết kế canary. Có rollback khi truy vấn khác bị ảnh hưởng.

## 14. Tình huống thực hành: vì sao có index vẫn quét rất nhiều?

Giả sử MongoDB có:

```javascript
db.orders.createIndex({ status: 1 });
```

API thực hiện:

```javascript
db.orders.find({
  tenantId: "T01",
  customerId: "C007",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Khi `status = PAID` rất phổ biến, index `{status:1}` có thể phải xem nhiều index entries rồi lọc tenant/customer sau đó, đồng thời sort. Khi ấy:

```text
nReturned: ít
totalKeysExamined: rất nhiều
totalDocsExamined: đáng kể
winningPlan: có thể dùng IXSCAN nhưng vẫn tốn việc
```

Một index theo access pattern:

```javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

có cơ hội thu hẹp theo ba điều kiện equality và duyệt theo `createdAt`. Nếu cần thứ tự xác định khi trùng timestamp, thêm `_id` vào sort/index và đánh giá lại.

### Điều không được suy luận từ ví dụ

- Không thể kết luận index mới chắc chắn được optimizer chọn trên mọi bộ dữ liệu.
- Không thể suy ra tốc độ cải thiện bao nhiêu lần nếu chưa đo.
- Không thể nói index `{status:1}` luôn vô dụng; có workload khác có thể hưởng lợi.
- Không thể giả định cùng index tối ưu cả query theo khách, query theo ngày, query theo SKU trong array và query tổng hợp.

**Công việc của explain và benchmark là làm rõ những điều chưa biết này.**

## 15. Dữ liệu mẫu, độ chọn lọc và tính đại diện

Một plan tốt trên 100 record thử nghiệm có thể kém trên 5 triệu record thực vì:

- Tỉ lệ status khác nhau (5% PAID vs 95% PAID).
- Một vài tenant lớn hơn hẳn phần còn lại.
- Trường `customerId` có độ phân bố rất lệch.
- Một số document chứa mảng `items` cực dài.
- Ngày tạo có nhiều giá trị trùng, ảnh hưởng sort/pagination.
- Dữ liệu vừa xóa tạo tombstone/fragmentation.
- Độ phân mảnh và cache thay đổi theo thời gian.
- Truy vấn chạy cùng nhiều request khác và write load.

Nên benchmark ít nhất các nhóm:

| Nhóm kiểm thử | Tại sao cần? |
|---|---|
| Tenant nhỏ và tenant lớn | Phát hiện lệch tải |
| Status phổ biến và hiếm | Xem index selectivity |
| Có kết quả và không có kết quả | Phát hiện scan vô ích |
| Trang đầu và trang sâu | Kiểm tra pagination |
| Document nhỏ và lớn | Đo fetch/serialization |
| Dữ liệu cache nóng và lạnh | Đo I/O thực |
| Lúc tải thấp và tải cao | Đo contention/throttle |
| Query theo range rộng/hẹp | Xem index bound và sort |

Không nên chỉ ghi một số “truy vấn 5 ms” mà không có kích thước dữ liệu, query shape và điều kiện đo.

## 16. Bảo mật khi dùng công cụ giải thích và giám sát

Execution plan, slow query log và trace có thể chứa:

- Tên collection/table/index và cấu trúc dữ liệu nội bộ.
- Điều kiện lọc, ID khách hàng, tenant ID và giá trị truy vấn.
- Địa chỉ node/cluster hoặc dấu vết kết nối.
- Tên field có tính nhạy cảm.
- Query text hoặc payload lẽ ra không được phát tán.

Vì vậy:

1. Chỉ người vận hành được phép truy cập công cụ chẩn đoán.
2. Không có endpoint công khai `/explain?query=...` nhận raw query từ client.
3. Hạn chế profiler/tracing trên production theo chính sách; không bật toàn bộ nếu không cần.
4. Redact dữ liệu cá nhân trong log, dùng query shape thay cho raw values khi có thể.
5. Gắn thời hạn retention và quyền xem cho logs/traces.
6. Khi chạy `PROFILE` trên Neo4j hoặc query analytics có khả năng ghi, xác định rõ tác động trước khi thực hiện.
7. Chỉ dùng thống kê aggregate để so sánh chi phí; không làm lộ danh tính từng user bằng metric labels có cardinality cao.

Kết quả explain phục vụ chẩn đoán kỹ thuật, **không thay thế authorization của query trong sản phẩm**.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao chưa chính xác? | Cách nhìn đúng |
|---|---|---|
| “Có index là query chắc chắn nhanh” | Index có thể kém chọn lọc hoặc không hỗ trợ sort | Xem lượng index/document đọc và plan thật |
| “Thấy `IXSCAN` thì ổn” | Có thể quét hàng triệu key | So keys/docs examined với kết quả |
| “`COLLSCAN` là bug” | Với vài document hoặc yêu cầu đọc toàn bộ, quét có thể hợp lý | Đánh giá theo kích thước và mục tiêu |
| “`nReturned=0` nghĩa là không tốn tài nguyên” | Có thể đọc toàn collection để xác nhận không khớp | Xem work done, không chỉ kết quả |
| “`EXPLAIN` luôn chạy query” | Tùy hệ/cấp công cụ; Neo4j EXPLAIN không chạy | Phân biệt explain, profile, execution stats |
| “`PROFILE` chỉ quan sát, không thay đổi gì” | Neo4j PROFILE thực thi query, kể cả ghi | Chỉ dùng có kiểm soát |
| “DynamoDB FilterExpression tiết kiệm số item đọc” | Filter áp sau bước đọc trong trang | Dùng key/GSI theo access pattern |
| “Redis có thể explain mọi GET/HGET như SQL” | Redis core không có general optimizer plan kiểu đó | Dùng commandstats, SLOWLOG, latency, key size |
| “`SCAN` là index truy vấn theo field” | Nó duyệt key, không tự index metadata | Dùng data access structure phù hợp |
| “Cassandra biết partition key là đủ” | Partition quá lớn, tombstone, replica và I/O vẫn gây chậm | Tracing và bảng/partition metrics |
| “Graph có index node đầu thì mọi traversal nhanh” | Fan-out/hop có thể bùng nổ | PROFILE Expand/Rows/DbHits |
| “Search profile bằng tổng response time” | Có overhead và phạm vi đo riêng | Dùng thêm took, slow logs, client latency |
| “Thêm index không tốn chi phí” | Tăng ghi, RAM, disk và vận hành | Đo workload đọc/ghi tổng thể |
| “Một lần chạy nhanh là bằng chứng tối ưu” | Cache, tải và dữ liệu có thể khác | Benchmark lặp và theo dõi p95/p99 |
| “Để client tự chạy explain cho tiện” | Lộ schema/query hoặc tạo tải | Quyền vận hành và template an toàn |

## 18. Bài tập thực hành

### Bài 1 — Đọc explain MongoDB

Một lần explain giả định trả:

```json
{
  "executionStats": {
    "nReturned": 20,
    "totalKeysExamined": 0,
    "totalDocsExamined": 1200000,
    "executionTimeMillis": 360
  }
}
```

Truy vấn tìm 20 đơn PAID của một khách trong một tenant. Hãy nêu các dấu hiệu cần điều tra; đề xuất index theo tenant, customer, status và createdAt; giải thích vì sao chưa thể khẳng định cải thiện bao nhiêu nếu chưa chạy lại trên dữ liệu thực.

### Bài 2 — Có `IXSCAN` nhưng vẫn chậm

Một MongoDB query có `nReturned=20`, `totalKeysExamined=850000`, `totalDocsExamined=450000`. Có phải chỉ cần nhìn thấy `IXSCAN` là query đã tối ưu? Điều kiện `status=PAID` xuất hiện ở 95% đơn ảnh hưởng ra sao?

### Bài 3 — Query DynamoDB bị lọc nhiều

Response Query có `ScannedCount=1000`, `Count=10`, `LastEvaluatedKey` khác null. Vì sao chỉ nhận 10 item không chứng minh đọc rẻ? Có nên dừng phân trang không? Khi nào GSI theo status hoặc mô hình key khác hữu ích?

### Bài 4 — Tracing Cassandra

Một query Cassandra bỏ partition key, chỉ lọc `status`. Hãy giải thích vì sao nó không khớp bảng `orders_by_customer`. Đề xuất bảng theo `(tenant_id,status,month_bucket)`, đồng thời nêu ít nhất hai chỉ số cần theo dõi trong tracing/cluster khi partition lớn.

### Bài 5 — Neo4j EXPLAIN và PROFILE

Một query bắt đầu ở Customer rồi duyệt qua `PLACED` và `HAS_LINE`. Kế hoạch hiển thị `NodeByLabelScan`, `Expand(All)` và số `Rows` tăng rất nhanh. Hãy xác định cách tìm node đầu bằng ID/index và cách hạn chế fan-out. Vì sao chỉ dùng `LIMIT 20` chưa chắc đủ giảm toàn bộ công việc?

### Bài 6 — Redis SLOWLOG

API chậm 300 ms nhưng SLOWLOG cho biết `HGET` chỉ tốn 0,1 ms ở server. Hãy đề xuất những nơi khác cần đo: network, connection pool, serialization, số lệnh nối tiếp, big key và thời gian xử lý ứng dụng. Vì sao không thể dùng SLOWLOG như latency toàn request?

### Bài 7 — Elasticsearch Profile

Một Search API trả `took` cao trên nhiều shard. Hãy mô tả khác biệt giữa `"profile":true`, `hits.total`, `took` và API explain theo document. Vì sao `hits.total` không cho biết số document được hệ thống thực sự kiểm tra?

### Bài 8 — Thực nghiệm trước–sau

Hãy lập kế hoạch đo trước khi thêm index: baseline query shape, dữ liệu đại diện, độ trễ p95, keys/docs examined hoặc capacity, tỉ lệ cache hit, write load. Sau thêm index, cần kiểm tra những điều kiện nào để bảo đảm kết quả vẫn đúng và chi phí tổng thể không tăng quá mức?

### Bài 9 — Truy vấn đọc được 0 kết quả

Một API tìm đơn với ID không tồn tại có p99 latency cao. Tại sao `resultCount=0` vẫn đáng điều tra? Với MongoDB, cần xem chỉ số nào? Với DynamoDB, cần xem key lookup hay Scan? Với Redis, cần phân biệt key không tồn tại và scan theo pattern như thế nào?

### Bài 10 — Quyền vận hành

Một developer muốn tạo endpoint công khai nhận raw MongoDB filter/Cypher query rồi trả explain. Hãy phân tích những rủi ro về bảo mật, quyền truy cập, truy vấn tốn tài nguyên và lộ schema; đề xuất một công cụ vận hành giới hạn query template và quyền người sử dụng.

## 19. Checklist thực dụng trước khi kết luận một truy vấn đã tốt

Một câu hỏi nhanh để tự kiểm tra khi điều tra:

1. **Có đo đúng query shape không?** Filter, sort, projection, limit, consistency level và quyền có giống sản phẩm?
2. **Có biết dữ liệu đại diện không?** Số lượng, phân bố tenant, độ chọn lọc, kích thước bản ghi, cache và tải?
3. **Có biết đường truy cập không?** Index/partition/graph expansion/command/key?
4. **Có biết lượng công việc thực không?** Keys/docs/items/rows đã xét, DbHits, capacity, số shard/partition?
5. **Có biết vấn đề nằm ở database hay ngoài database không?** Network, pool, application, serialization, retry và contention?
6. **Có giữ nguyên tính đúng và quyền không?** Không bỏ filter tenant, điều kiện nghiệp vụ, sort ổn định và giới hạn truy cập?
7. **Có biết chi phí của giải pháp không?** Index mới, write amplification, backup, migration và đồng bộ?
8. **Có kết quả sau đo lại không?** p95/p99, regression, query plan mới và monitoring?

Checklist này giúp tổ chức việc điều tra; **nó không phải một công thức tự động cho mọi hệ NoSQL**.

## 20. Kết luận

**Đọc kế hoạch, thống kê truy vấn và công cụ giải thích** là bước kết nối giữa **thiết kế chỉ mục/đường truy cập** với **hành vi thực tế của NoSQL**.

- **MongoDB:** dùng `explain("executionStats")` để xem index/collection scan, fetch, sort và số key/document đã xét; phối hợp profiler/metrics cho tải thực.
- **Redis:** quan sát loại lệnh, thời gian server, kích thước key, số phần tử và độ trễ end-to-end; đừng tìm một cây execution plan SQL không tồn tại cho lệnh key–value cốt lõi.
- **DynamoDB:** hiểu GetItem/Query/Scan, `Count`, `ScannedCount`, `ConsumedCapacity`, `LastEvaluatedKey` và giới hạn của FilterExpression.
- **Cassandra:** kiểm tra partition/clustering access pattern, tracing và số liệu cluster; lưu ý partition lớn, replica và tombstone.
- **Neo4j:** dùng `EXPLAIN` để xem kế hoạch chưa chạy và `PROFILE` để đo operator thực, nhất là `Expand`, `Rows`, `DbHits` và `CartesianProduct`.
- **Elasticsearch/OpenSearch:** dùng Search Profile và thống kê shard/search đúng mục đích; không nhầm explain điểm số theo document với execution plan toàn hệ.
- **Couchbase:** đọc SQL++ `EXPLAIN` và query metrics theo những operator của riêng engine.

Điểm cốt lõi không phải “query nào cũng phải dùng index”, mà là **biết hệ đang đọc bao nhiêu dữ liệu, vì sao đọc như vậy, tốc độ dưới tải thực ra sao và thay đổi nào cải thiện được mà vẫn giữ đúng nghiệp vụ**. Khi làm được điều đó, việc thêm index, đổi khóa phân vùng, chia lại read model hoặc sửa mẫu truy vấn trở thành quyết định dựa trên bằng chứng thay vì phỏng đoán.
