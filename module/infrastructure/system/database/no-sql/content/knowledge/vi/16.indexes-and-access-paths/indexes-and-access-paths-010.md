# Chi phí ghi, lưu trữ và tái xây dựng chỉ mục

## 1. Vì sao chỉ mục giúp đọc nhanh nhưng không miễn phí?

Một hệ thống NoSQL có thể phục vụ truy vấn bằng khóa chính rất hiệu quả. Nhưng khi sản phẩm thêm yêu cầu đọc theo trạng thái, ngày tạo, tên, nhãn hoặc các thuộc tính khác, người phát triển thường tạo thêm **chỉ mục (index)** để tránh đọc quá nhiều bản ghi.

Ví dụ ứng dụng bán hàng có truy vấn:

> Lấy 20 đơn hàng `PAID` mới nhất của khách hàng C42 trong tenant T7.

Nếu không có đường truy cập phù hợp, hệ có thể phải xem xét một tập đơn hàng rất lớn rồi lọc và sắp xếp. Một compound index hoặc bảng đọc theo mẫu truy vấn có thể đưa việc đọc về một dải khóa nhỏ. Nhưng đổi lại, khi đơn mới được tạo, trạng thái đổi hoặc dữ liệu bị xóa, hệ thống phải **cập nhật cả dữ liệu chính và cấu trúc chỉ mục liên quan**.

Một chỉ mục cũng chiếm dung lượng. Nếu phải khôi phục sau sự cố, thêm một index trên dữ liệu đã có, đổi schema hoặc sửa một index không còn phù hợp, hệ có thể phải **quét lại nhiều triệu bản ghi để xây dựng chỉ mục**. Công việc này tranh CPU, I/O, RAM và throughput với các request đang hoạt động.

Vì vậy, câu hỏi thiết kế không chỉ là:

- “Index nào giúp query nhanh nhất?”

Mà phải là:

- “Mỗi lệnh ghi phải duy trì những index nào?”
- “Index tiêu thụ bao nhiêu byte, I/O, bộ nhớ và năng lực ghi?”
- “Khi dữ liệu tăng gấp 10 lần, index còn phù hợp không?”
- “Tạo hoặc xây lại index trên hệ đang chạy sẽ ảnh hưởng ra sao?”
- “Nếu quá trình xây bị lỗi hoặc kết quả không khớp nguồn, làm sao khôi phục?”
- “Khi muốn bỏ một index, có chắc không còn đường đọc nào cần nó?”

Bài học đặt chỉ mục trong toàn bộ vòng đời **CRUD, vận hành và thay đổi schema**, không xem nó chỉ là một công cụ tối ưu riêng cho `SELECT` hoặc `find()`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **chi phí duy trì index khi ghi**, **dung lượng lưu index** và **chi phí xây/tái xây dựng**.
2. Giải thích write amplification ở tầng ứng dụng và storage engine.
3. So sánh index khóa ghép, partial, multikey, secondary index, GSI, SAI, inverted index và read model theo truy vấn.
4. Đọc một số dấu hiệu từ MongoDB, DynamoDB và Cassandra để đánh giá lợi ích và chi phí index.
5. Xây dựng kế hoạch tạo/thay index có giai đoạn backfill, kiểm chứng, cutover và rollback.
6. Xác định các bất biến liên quan đến uniqueness, dữ liệu thay đổi đồng thời, quyền truy cập và consistency.
7. Lập ma trận đo lường, ước lượng dung lượng và thực hành ra quyết định giữ/bỏ index.

---

## 2. Hình dung chỉ mục: một đường truy cập phụ đến dữ liệu

Giả sử collection `orders` lưu:

~~~json
{
  "_id": "order-1001",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "status": "PAID",
  "createdAt": "2026-11-14T08:15:27Z",
  "totalVnd": 1050000
}
~~~

Để truy vấn theo `customerId` và thời gian, một index logic có thể hình dung:

~~~text
Index key                               Pointer / reference
------------------------------------------------------------------
(tenant-7, customer-42, 2026-11-14) -> order-1001
(tenant-7, customer-42, 2026-11-13) -> order-0999
(tenant-7, customer-88, 2026-11-12) -> order-0990
...
~~~

DBMS có thể tìm một dải index rồi đọc những document phù hợp, thay vì duyệt toàn bộ collection.

Tuy nhiên, **index là cấu trúc phải được duy trì**, không phải bảng tra miễn phí xuất hiện từ hư không:

~~~mermaid
flowchart LR
    App["Ứng dụng ghi Order"] --> Source["Dữ liệu nguồn"]
    App --> I1["Index customer + date"]
    App --> I2["Index status + date"]
    App --> I3["Index search / tags"]
    Source --> Storage["Dữ liệu, log, replica"]
    I1 --> Cost["CPU, I/O, RAM, storage"]
    I2 --> Cost
    I3 --> Cost
~~~

Sơ đồ trên biểu diễn tác động logic. Trong nhiều DBMS, ứng dụng chỉ gửi **một** lệnh ghi và engine tự cập nhật index bên trong, thay vì ứng dụng thực hiện ba lệnh riêng.

### 2.1. Khóa chính và đường truy cập phụ

Cần phân biệt:

- **Primary key / định danh nguồn:** thường dùng để lấy bản ghi trực tiếp.
- **Secondary index:** đường đọc khác được xây từ một hay nhiều thuộc tính.
- **Composite/compound index:** một chỉ mục có thứ tự trên nhiều trường.
- **Materialized view hoặc read model:** một bản sao có cấu trúc riêng, đôi khi có index và cơ chế đồng bộ của chính nó.
- **Search/inverted index:** cấu trúc cho tìm văn bản hoặc các truy vấn đảo từ giá trị về tập document.

Không phải DBMS nào cũng tổ chức primary key và secondary index giống nhau. Một số hệ gắn secondary index với node lưu dữ liệu; một số khác phân phối global secondary index thành cấu trúc độc lập. Vì thế **chi phí của hai index cùng tên gọi có thể rất khác nhau**.

### 2.2. Index không làm dữ liệu gốc tự thay đổi ngữ nghĩa

Một index `(tenantId, customerId, createdAt)` không:

- Thay thế kiểm tra quyền truy cập tenant.
- Tự làm cho dữ liệu trở nên nhất quán giữa nhiều collection.
- Bảo đảm một bản ghi tồn tại nếu nguồn đã bị xóa.
- Cam kết truy vấn phải sử dụng index đó.
- Giải quyết mọi biến thể lọc, sort hoặc phân trang.

Index giúp tạo một **đường truy cập**, còn tính đúng đắn nghiệp vụ vẫn phải được thiết kế riêng.

## 3. Ba nhóm chi phí của một chỉ mục

| Nhóm chi phí | Điều gì phát sinh? | Đo bằng gì? |
|---|---|---|
| **Ghi thường xuyên** | Insert, update, delete phải duy trì index entry | Write latency p95/p99, throughput, write capacity, compaction |
| **Lưu trữ lâu dài** | Key, pointer, metadata, replica, backup và log liên quan | Index bytes, disk utilization, storage growth |
| **Tạo/tái xây dựng** | Quét nguồn, sort/build, backfill, bắt thay đổi và xác minh | Build duration, scan bytes, CPU/I/O, lag, errors |

Các chi phí còn kéo theo **độ phức tạp vận hành**: theo dõi index không được dùng, migration schema, xử lý uniqueness, phục hồi khi index không khớp nguồn và quyết định khi nào có thể xóa index cũ.

### 3.1. Lợi ích đọc cũng phải được ghi thành số liệu

Một index chỉ đáng giữ nếu giúp các truy vấn quan trọng đủ nhiều hoặc đáp ứng ràng buộc bắt buộc.

Nên ghi:

~~~text
Q2: Danh sách 20 đơn mới nhất của khách
Filter: tenantId, customerId, status
Sort: createdAt DESC, _id DESC
Tỷ lệ request: 35% traffic đọc
Mục tiêu: p95 dưới 120 ms
Kết quả trước/sau index: phải đo
~~~

Đừng chỉ viết “index tăng hiệu năng đọc”: lợi ích của một index trên 100.000 record và trên 100 triệu record có thể khác nhau, cũng như phân bố khách hàng phổ biến và khách ít hoạt động.

---

## 4. Chi phí ghi: insert, update và delete có tác động khác nhau

### 4.1. Insert

Giả sử một collection có ba secondary index. Khi thêm Order:

~~~text
1. Ghi document Order.
2. Duy trì index A theo customerId + createdAt.
3. Duy trì index B theo tenantId + status.
4. Duy trì index C theo một thuộc tính phục vụ tìm kiếm.
5. Thực hiện log/replication/compaction theo engine.
~~~

Đây là mô hình công việc, không phải số lệnh gọi ứng dụng. Một index có thể không nhận entry nếu điều kiện partial index không khớp hoặc tài liệu thiếu thuộc tính được index theo ngữ nghĩa hệ cụ thể.

### 4.2. Update trường không nằm trong index

Ví dụ chỉ cập nhật ghi chú nội bộ `internalNote`, không có index nào dùng trường này. Engine vẫn phải cập nhật document và cơ chế lưu trữ liên quan, nhưng **có thể không cần đổi khóa index phụ** nếu các giá trị index không đổi.

Tuy nhiên, không nên hứa chi phí bằng không: cập nhật document, write-ahead log, versioning hoặc cấu trúc lưu trữ vẫn có thể phát sinh I/O.

### 4.3. Update trường nằm trong index

Đổi:

~~~text
status: PENDING -> PAID
~~~

Nếu `status` nằm trong một compound index, index entry cũ có thể phải được loại hoặc đánh dấu hết hiệu lực, và entry mới được tạo/cập nhật theo engine. Nếu index là bản chiếu theo status, một document còn có thể cần được chuyển giữa hai nhóm khóa.

Với hệ LSM-tree, thao tác thường dẫn tới dữ liệu/tombstone mới rồi được xử lý trong compaction về sau. Với các cấu trúc dạng B-tree, engine có thể phải thay đổi các trang/cây chỉ mục. Chi tiết vật lý tùy sản phẩm.

### 4.4. Delete

Khi xóa một document, các secondary index không nên tiếp tục trả document đó như dữ liệu còn sống. Hệ phải duy trì trạng thái xóa hoặc xóa entry tương ứng.

Một lệnh xóa hàng loạt có thể tạo:

- Nhiều thay đổi index.
- Nhiều tombstone hoặc công việc dọn dẹp về sau.
- Áp lực replication và log.
- I/O tranh chấp với traffic đọc/ghi chính.
- Chi phí tìm bản ghi thỏa điều kiện xóa.

**Không phải tạo index giúp DELETE lúc nào cũng nhanh hơn**: index có thể giúp tìm record cần xóa, nhưng cũng làm mỗi record bị xóa đòi bảo trì nhiều cấu trúc hơn.

### 4.5. Update không đổi khóa nhưng đổi field được projection

Một global secondary index hoặc read model có thể lưu `totalVnd` như một trường được project để tránh đọc nguồn. Dù khóa index không đổi, cập nhật `totalVnd` vẫn có thể cần cập nhật bản chiếu.

Cần phân biệt:

- **Key attributes:** quyết định vị trí/sort trong index.
- **Projected/included attributes:** được lưu kèm để query không phải truy cập nguồn.
- **Unindexed attributes:** không xuất hiện trong index đang xét.

Việc chọn projection ảnh hưởng chi phí ghi và dung lượng, không chỉ payload trả về.

---

## 5. Write amplification: công việc tăng thêm trên một thay đổi nghiệp vụ

**Write amplification** có hai lớp cần phân biệt.

### 5.1. Khuếch đại ghi ở tầng mô hình dữ liệu

Một yêu cầu “tạo đơn” có thể gây:

~~~text
1 document nguồn
1 item ở orders_by_customer
1 item ở orders_by_status
1 bản ghi audit
1 event/outbox
~~~

Đó là nhiều **ghi logic** do ứng dụng hoặc hệ quản lý các projection tạo ra.

Nếu cập nhật một Order làm đổi trạng thái, có thể cần:

~~~text
Đổi nguồn
Xóa item khỏi trạng thái cũ
Thêm item vào trạng thái mới
Đổi bản chiếu của khách hàng
Ghi event
~~~

Chi phí này tồn tại dù từng bảng không có secondary index.

### 5.2. Khuếch đại ghi ở storage engine

Một lệnh ghi logic bên trong DBMS có thể dẫn tới:

- Write-ahead/commit log.
- Bảo trì primary/secondary index.
- Replication.
- Flush memtable thành SSTable.
- Compaction hoặc hợp nhất page/index.
- Snapshot/backup theo chu kỳ.

Không thể lấy “có 3 index nên chính xác gấp 4 lượng I/O” làm định luật. Mỗi index khác kích thước, cách lưu, compression, key cardinality và mức update; engine cũng có cách tối ưu và compaction khác nhau.

### 5.3. Công thức ước lượng tầng ứng dụng

Đặt:

- \(N_i\): số insert nghiệp vụ trong kỳ.
- \(N_u\): số update.
- \(N_d\): số delete.
- \(a_i, a_u, a_d\): số ghi logic trung bình phát sinh tương ứng, bao gồm read model nếu có.

Một mô hình sơ bộ:

\[
W_{\mathrm{logical}}
= N_i a_i + N_u a_u + N_d a_d.
\]

Ví dụ giả định:

~~~text
Mỗi ngày:
  100.000 insert
   50.000 update status
   10.000 delete

Trung bình:
  insert -> 3 ghi logic
  update -> 4 ghi logic
  delete -> 3 ghi logic
~~~

Tổng:

\[
100000\times 3 + 50000\times 4 + 10000\times 3
= 530000\ \text{ghi logic/ngày}.
\]

Đây không phải số write capacity unit hay byte I/O hóa đơn. Nó giúp nhận biết **chi phí đồng bộ do mô hình dữ liệu**, sau đó phải đo trên DBMS thật.

### 5.4. Độ trễ tail quan trọng hơn trung bình

Một index có thể tăng thời gian insert trung bình rất ít, nhưng ở tải cao tạo ra:

- p99 write latency tăng.
- Timeout do disk pressure.
- Throttling vì GSI không đủ năng lực ghi.
- Replication hoặc compaction lag.
- Tranh chấp một hot key/index partition.

Vì vậy, nên so sánh p95/p99 của read **và** write trong cùng workload, cùng phân bố dữ liệu, cùng cấu hình.

---

## 6. Chi phí lưu trữ: index không chỉ bằng độ dài trường

Một index có thể chứa:

- Giá trị khóa đã mã hóa hoặc sắp xếp.
- Định danh/pointer đến document nguồn.
- Metadata của cây, posting list, SSTable hoặc cấu trúc index.
- Nhiều bản sao theo replication.
- Dữ liệu trung gian khi build/compaction.
- Thông tin version hoặc tombstone.
- Một số trường được projection/included.
- Bản sao trong snapshot/backup và vùng lưu trữ tạm.

Vì thế, kích thước index **không luôn là tổng độ dài chuỗi của trường đã index**.

### 6.1. Công thức sơ bộ

Với:

- \(N\): số document được index.
- \(e\): số entry trung bình trên một document.
- \(s_e\): số byte logic trung bình của một entry (key + pointer + metadata ước tính).
- \(r\): hệ số bản sao logic để ước lượng sơ bộ.

\[
S_{\text{index, logical}} \approx N \times e \times s_e.
\]

\[
S_{\text{copies, rough}} \approx r \times S_{\text{index, logical}}.
\]

Đây chỉ là phép ước tính ban đầu. Storage engine có thể nén khác nhau; index có cấu trúc trang/SSTable khác nhau; backup, cache và compaction không được phản ánh đầy đủ.

### 6.2. Ví dụ định lượng

Giả sử:

~~~text
20 triệu đơn hàng.
Mỗi index entry giả định chiếm trung bình 90 byte logic.
Mỗi document đóng góp một entry cho mỗi index.
Có 2 secondary index.
~~~

Tổng dung lượng index logic trước overhead thực tế:

\[
20\,000\,000 \times 90 \times 2
= 3\,600\,000\,000\ \text{byte}
\approx 3.6\ \text{GB}.
\]

Nếu hệ giữ ba bản sao logic có kích thước tương đương, phép nhân sơ bộ cho kết quả khoảng **10,8 GB** trước các yếu tố khác.

**Không được sử dụng kết quả này như hóa đơn lưu trữ dự báo chính xác**. Một index thực tế có thể dùng nhiều hoặc ít byte hơn vì compression, key encoding, số entry và cấu trúc engine.

### 6.3. Mảng và multikey index làm tăng số entry

Ví dụ document:

~~~json
{
  "_id": "product-8",
  "tags": ["wireless", "mouse", "electronics", "sale"]
}
~~~

Một index trên `tags` có thể tạo nhiều khóa index ứng với các giá trị trong mảng theo ngữ nghĩa multikey của MongoDB. Document có 40 thẻ có thể làm index tốn tài nguyên hơn document có 2 thẻ.

Không thể giả định luôn đúng “một document = một index entry”. Với index mảng, text/inverted index hoặc tập nested attribute, số entry có thể lớn hơn đáng kể.

### 6.4. Project nhiều trường làm index “nặng”

Trong các hệ hỗ trợ covering/projection, có thể lưu thêm những trường phục vụ query để tránh lấy document nguồn. Cách này giảm một số lần đọc, nhưng làm:

- Entry lớn hơn.
- Index cần thêm dung lượng và bộ nhớ cache.
- Những update của trường được project có thể trở thành index write.
- Backfill cần đọc/ghi thêm dữ liệu.

Một “covering index” giúp read nhanh chưa chắc tối ưu tổng thể khi 90% traffic là ghi.

### 6.5. Chi phí không tỷ lệ tuyến tính tuyệt đối

Khi index vượt bộ nhớ hữu dụng, tỷ lệ cache miss có thể tăng, khiến độ trễ không tăng tuyến tính theo dung lượng. Khi workload chạm giới hạn throughput của thiết bị/managed service, chỉ thêm ít index cũng có thể làm tail latency tăng mạnh.

Nên đo tại nhiều quy mô và mức tải, không nội suy đơn giản từ một dataset rất nhỏ.

---

## 7. Chi phí theo loại chỉ mục

| Loại index | Lợi ích đọc chính | Chi phí và rủi ro đặc trưng |
|---|---|---|
| **Primary key** | Point lookup theo ID | Chi phí duy trì định danh/khóa nền tảng |
| **Compound index** | Filter + sort theo mẫu truy vấn cụ thể | Key dài, nhiều cấu trúc tương tự nếu API có nhiều biến thể |
| **Partial/sparse index** | Chỉ index tập có điều kiện | Nhỏ hơn, nhưng điều kiện query phải tương thích; cập nhật có thể thêm/xóa entry khi đổi trạng thái |
| **Unique index** | Hỗ trợ ràng buộc không trùng | Build thất bại nếu dữ liệu vi phạm; ghi phải kiểm tra xung đột |
| **Multikey/array index** | Tra cứu phần tử trong mảng | Có thể tạo nhiều entries/doc và tăng chi phí update mảng |
| **TTL index** | Dọn dữ liệu theo thời hạn | Lượng delete lớn và cleanup không tức thời |
| **Global secondary index** | Truy vấn theo khóa khác, có thể phân tán riêng | Backfill, eventual consistency, write capacity và projected storage |
| **Storage-attached secondary index** | Lọc trên trường ngoài primary key theo khả năng engine | Index maintenance, compaction, giới hạn truy vấn và selectivity |
| **Inverted/text/search index** | Tìm theo token/term, văn bản, thuộc tính tìm kiếm | Posting list lớn, mapping/analyzer, đồng bộ với nguồn |
| **Read model riêng** | Tối ưu sâu theo access pattern | Write amplification, lag, backfill và vận hành pipeline |

**Cùng gọi là secondary index nhưng bảo đảm, cách phân phối và phạm vi transaction khác nhau theo DBMS.** Không nên dùng một bảng này để kết luận sản phẩm nào “luôn nhanh hơn”.

## 8. MongoDB: compound index ảnh hưởng cả đọc lẫn ghi

Giả sử collection `orders` lưu trường thời gian dưới dạng BSON Date.

Truy vấn ứng dụng:

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

Một index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "orders_tenant_customer_status_recent"
  }
);
~~~

### 8.1. Index giúp đọc như thế nào?

Điều kiện bằng `tenantId`, `customerId`, `status` giúp tìm một dải tương đối hẹp; phần `createdAt DESC, _id DESC` phục vụ thứ tự. Nếu planner chọn index này và dữ liệu phân bố phù hợp, query có thể ít quét và giảm công việc sort.

Điều này không cam kết query sẽ luôn nhanh hoặc planner luôn dùng index: phải đo trên tập dữ liệu đại diện.

### 8.2. Ghi phải trả giá ra sao?

Khi tạo Order mới, engine cần duy trì compound index. Khi Order đổi `status` từ `PENDING` sang `PAID`, khóa index chứa `status` thay đổi. Khi xóa Order, entry liên quan cũng phải được loại hoặc đánh dấu theo engine.

Ngược lại, cập nhật một trường không xuất hiện trong index như `internalComment` có thể không đòi thay giá trị entry của index này, dù document nguồn và log vẫn có chi phí ghi.

### 8.3. Một index không phục vụ mọi biến thể

Truy vấn thứ hai:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Vì index ở trên có `status` nằm trước `createdAt`, việc bỏ bộ lọc status có thể khiến dải index không thuận tiện cho thứ tự thời gian tổng thể. Có thể phải tạo index khác, nhưng chỉ sau khi đánh giá tần suất query và chi phí bổ sung:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "orders_tenant_customer_recent"
  }
);
~~~

Nếu cả hai index được giữ, insert phải duy trì cả hai. **Mỗi biến thể query được thêm vào sản phẩm không mặc nhiên xứng đáng có một index riêng.**

### 8.4. Dùng `explain` để đo lợi ích

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    status: "PAID"
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Cần xem:

- `COLLSCAN` hay `IXSCAN`.
- Index nào được dùng trong winning plan.
- `totalKeysExamined` và `totalDocsExamined`.
- Số item trả về.
- Có sort tốn tài nguyên hoặc fetch document lớn không.
- Độ trễ và tác động khi thử với phân bố khách hàng “nóng”.

Một `IXSCAN` đọc hàng triệu key vẫn có thể không phù hợp; chỉ nhìn thấy tên index trong plan chưa đủ.

### 8.5. Kiểm tra kích thước và mức sử dụng

Ví dụ `mongosh`:

~~~javascript
db.orders.getIndexes();
db.orders.totalIndexSize();

db.orders.aggregate([
  { $indexStats: {} }
]);
~~~

`getIndexes()` cho biết index đã khai báo; `totalIndexSize()` cho kích thước index theo thông tin engine; `$indexStats` giúp quan sát một số thống kê về index usage.

Lưu ý:

- Thống kê usage có phạm vi và vòng đời riêng, có thể bị reset do restart hoặc thay đổi topology.
- “Chưa thấy index được dùng” trong một cửa sổ ngắn không chứng minh index vô dụng: có thể phục vụ job cuối tháng, migration hoặc bảo đảm uniqueness.
- Giá trị kích thước phải được diễn giải cùng compression, replica, backup và phiên bản hệ.

---

## 9. MongoDB: giảm chi phí bằng partial index và thiết kế mảng cẩn thận

### 9.1. Partial index cho tập dữ liệu được đọc nhiều

Giả sử API thường đọc các đơn `OPEN` gần đây, trong khi phần lớn đơn đã `CLOSED`.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "open_orders_recent",
    partialFilterExpression: { status: "OPEN" }
  }
);
~~~

Một truy vấn phù hợp:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  status: "OPEN"
})
.sort({ createdAt: -1, _id: -1 })
.limit(50);
~~~

Index chỉ chứa những document thỏa điều kiện partial, giúp giảm số entry so với index bao phủ mọi Order nếu OPEN chiếm tỷ lệ nhỏ.

Nhưng cần nhớ:

- Query phải có điều kiện bảo đảm đúng tập được index để planner sử dụng an toàn.
- Đổi trạng thái `OPEN -> CLOSED` khiến document rời tập index.
- Đổi `CLOSED -> OPEN` khiến document được thêm vào index.
- Nếu tỷ lệ OPEN tăng mạnh, kích thước index cũng tăng.
- Một partial index không tự phục vụ query tìm tất cả trạng thái.

**Tiết kiệm lưu trữ có thể đổi thành chi phí ghi lớn ở lúc document đi vào/ra tập được index.**

### 9.2. Unique index và dữ liệu trùng

Ví dụ một tài khoản có email chuẩn hóa duy nhất **trong một tenant**:

~~~javascript
db.users.createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  {
    unique: true,
    name: "uniq_email_per_tenant"
  }
);
~~~

Index này kiểm soát trùng cặp khóa trong phạm vi collection theo ngữ nghĩa MongoDB. Nó không kiểm tra email có thật hay người dùng được quyền truy cập tenant.

Nếu dữ liệu hiện có đã có hai document cùng `tenantId, normalizedEmail`, xây unique index có thể thất bại. Cần **phân tích và xử lý duplicate trước khi build**, không mặc định DBMS sẽ tự chọn bản đúng.

Với trường có thể thiếu hoặc `null`, phải xem rõ cách unique index xử lý missing/null và có cần partial unique index. Một index `unique` sai phạm vi có thể vừa chặn các ghi hợp lệ vừa không thể hiện đúng nghiệp vụ.

### 9.3. Multikey index khi document có mảng

~~~json
{
  "_id": "product-8",
  "tags": ["wireless", "mouse", "sale"]
}
~~~

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

Khi mảng có nhiều phần tử, một document có thể đóng góp nhiều khóa vào multikey index. Update mảng lớn hoặc thêm/xóa tags hàng loạt có thể tăng chi phí index maintenance.

MongoDB còn có quy tắc đối với compound multikey index, đặc biệt khi nhiều trường mảng nằm trong cùng document. Không nên tạo index ghép cho hai mảng tùy ý mà không kiểm tra các ràng buộc của phiên bản đang dùng.

### 9.4. TTL index cũng tạo khối lượng delete

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

TTL giúp session hết hạn được dọn, nhưng xóa diễn ra bất đồng bộ. Nếu 20 triệu session cùng hết hạn sau một chiến dịch, công việc delete và index maintenance có thể tạo tải cao.

TTL không phải phép thay thế đầy đủ cho một chính sách xóa dữ liệu cá nhân hoặc backup. Khi tạo TTL index trên một collection đã có nhiều dữ liệu quá hạn, phải dự tính là lượng bản ghi đủ điều kiện dọn có thể rất lớn.

---

## 10. DynamoDB: GSI làm chi phí ghi/lưu trữ trở nên rõ rệt

Trong DynamoDB, bảng có primary key phục vụ một cách định vị dữ liệu. **Global secondary index (GSI)** cho phép query bằng khóa khác.

Giả sử bảng `Orders` có primary key `orderId`. API lại thường đọc đơn theo tenant, trạng thái và thời gian.

Có thể tạo thuộc tính:

~~~json
{
  "orderId": "order-1001",
  "tenantStatus": "tenant-7#PAID",
  "createdAtOrder": "2026-11-14T08:15:27Z#order-1001",
  "totalVnd": 1050000
}
~~~

Và GSI logic:

~~~text
GSI_TenantStatusCreatedAt

Partition key: tenantStatus
Sort key:      createdAtOrder
Projection:    những thuộc tính API thực sự cần
~~~

### 10.1. Truy vấn GSI

Ví dụ AWS SDK for JavaScript v3:

~~~javascript
import { QueryCommand } from "@aws-sdk/lib-dynamodb";

const page = await client.send(new QueryCommand({
  TableName: "Orders",
  IndexName: "GSI_TenantStatusCreatedAt",
  KeyConditionExpression: "tenantStatus = :key",
  ExpressionAttributeValues: {
    ":key": "tenant-7#PAID"
  },
  ScanIndexForward: false,
  Limit: 20
}));

console.log(page.Items);
~~~

Đoạn mã giả định `client` là DynamoDBDocumentClient đã cấu hình, GSI đã ACTIVE và projection chứa những trường cần trả. Nếu một trường không được project lên GSI, không thể mặc định query GSI sẽ tự đọc thêm trường đó từ bảng nguồn.

### 10.2. Write cost của GSI

Khi Order được insert, các entry GSI tương ứng phải được duy trì. Khi trạng thái đổi:

~~~text
tenant-7#PENDING -> tenant-7#PAID
~~~

khóa partition của GSI thay đổi. Việc đồng bộ GSI có thể bao gồm xóa entry cũ và tạo entry mới theo dịch vụ.

Điều cần đo:

- Base-table write traffic.
- GSI write capacity/consumption.
- Kích thước item được project lên GSI.
- Số thao tác update trên trường khóa hoặc projected attributes.
- Throttling của bảng và GSI.
- Độ trễ query sau một update.

**Write pressure từ GSI có thể ảnh hưởng khả năng ghi của bảng nguồn** nếu tài nguyên GSI không đáp ứng nhịp cập nhật, tùy cơ chế capacity của cấu hình dịch vụ.

### 10.3. GSI có tính nhất quán đọc riêng

GSI của DynamoDB chỉ hỗ trợ **eventually consistent reads**, không cung cấp strong consistent read giống một số kiểu đọc trên bảng nguồn. Sau khi đổi trạng thái, query trên GSI có thể chưa thấy Order ở nhóm mới ngay lập tức.

Với một màn hình vừa cập nhật Order và cần read-your-writes, có thể đọc nguồn bằng `orderId` hoặc thiết kế UX chấp nhận trễ của GSI.

Đây là một **chi phí tính đúng đắn và trải nghiệm**, không chỉ thêm vài mili giây.

### 10.4. Projection và kích thước index

Nếu GSI chỉ cần hiển thị:

~~~text
orderId
createdAtOrder
status
totalVnd
~~~

không nhất thiết project toàn bộ địa chỉ giao hàng, danh sách item và metadata lớn. Project rộng giúp một số query khỏi cần tra nguồn, nhưng làm GSI tốn lưu trữ và phải duy trì nhiều thuộc tính hơn.

Nếu ứng dụng đổi một trường chỉ có trên nguồn và không được project, tác động tới GSI có thể khác với đổi trường khóa GSI. Cần xem thống kê thực tế và ngữ nghĩa của dịch vụ.

### 10.5. Sparse GSI

Trong DynamoDB, item không có đủ key attributes của GSI sẽ không xuất hiện trong GSI. Có thể tận dụng điều này để chỉ index những item cần hiển thị trong một read model nhất định.

Tuy nhiên, việc thêm/xóa thuộc tính khóa để item vào/ra GSI tạo chi phí cập nhật. Sparse GSI có ích khi tập cần index nhỏ, không phải cách miễn phí để lọc mọi điều kiện.

### 10.6. GSI và LSI không giống nhau

**Local secondary index (LSI)** dùng cùng partition key với bảng và chọn sort key khác, có những giới hạn riêng và phải được xác định lúc tạo bảng theo hợp đồng DynamoDB. Không thể xử lý việc thêm LSI muộn giống thêm GSI.

GSI có thể tạo trên bảng đã tồn tại, nhưng quá trình tạo cần **backfill dữ liệu hiện có** và tiêu thụ tài nguyên. Khi thiết kế schema từ đầu, cần cân nhắc các truy vấn đòi LSI và giới hạn item collection tương ứng.

Không nên gộp “secondary index” thành một tùy chọn có thể thay đổi tùy ý sau khi bảng đã lên production.

---

## 11. Cassandra: primary key, secondary index và chi phí LSM/compaction

Cassandra được thiết kế để đọc hiệu quả theo **partition key** và thứ tự trong partition. Đặt đúng primary key cho access pattern thường quan trọng hơn thêm một index để chữa mọi truy vấn không có khóa.

Bảng mẫu:

~~~sql
CREATE TABLE orders_by_tenant_month (
  tenant_id text,
  order_month text,
  order_id timeuuid,
  status text,
  total_vnd bigint,
  PRIMARY KEY ((tenant_id, order_month), order_id)
);
~~~

Một query thuận lợi:

~~~sql
SELECT order_id, status, total_vnd
FROM orders_by_tenant_month
WHERE tenant_id = 'tenant-7'
  AND order_month = '2026-11'
LIMIT 50;
~~~

Nếu cần lọc thêm `status` thường xuyên, có thể cân nhắc secondary indexing theo khả năng phiên bản Cassandra hoặc một bảng đọc riêng.

### 11.1. Secondary index không thay thế partition design

Một truy vấn tìm tất cả đơn `PAID` trên toàn cụm, không có tenant/time scope, có thể rất tốn kém ngay cả khi có một số cấu trúc index phù hợp với field `status`. Độ chọn lọc thấp, tập kết quả lớn hoặc yêu cầu truy vấn phân tán đều là yếu tố cần xét.

Các truy vấn theo trạng thái thường xuyên có thể phù hợp với read model:

~~~sql
CREATE TABLE orders_by_tenant_status_month (
  tenant_id text,
  status text,
  order_month text,
  created_at timestamp,
  order_id timeuuid,
  total_vnd bigint,
  PRIMARY KEY (
    (tenant_id, status, order_month),
    created_at,
    order_id
  )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Bảng này đánh đổi read nhanh theo khóa lấy việc **nhân bản dữ liệu và duy trì thêm một bảng** khi Order được tạo/đổi trạng thái.

### 11.2. Storage-Attached Index (SAI)

Trong những phiên bản/phân phối Cassandra hỗ trợ SAI, có thể tạo index trên một trường ngoài primary key. Ví dụ cú pháp minh họa theo dạng hỗ trợ SAI:

~~~sql
CREATE CUSTOM INDEX IF NOT EXISTS
ON orders_by_tenant_month (status)
USING 'StorageAttachedIndex';
~~~

Cú pháp/khả năng của SAI cần được kiểm tra với phiên bản và bản phân phối Cassandra đang dùng; không phải mọi cluster Cassandra đều hỗ trợ như nhau.

SAI có thể giúp truy vấn một số điều kiện mà không cần tạo bảng đọc thủ công cho mọi trường. Tuy nhiên:

- Index vẫn tiêu tốn dung lượng.
- Write path và compaction có công việc duy trì index.
- Hiệu quả phụ thuộc selectivity, phân vùng và loại truy vấn.
- Không tự thay thế thiết kế partition key cho workload lớn.
- Xây index trên tập dữ liệu hiện có có chi phí backfill/build.

Một câu truy vấn được cho phép chạy không đồng nghĩa nó hiệu quả trong mọi phân bố dữ liệu.

### 11.3. Chi phí do LSM-tree và tombstone

Cassandra ghi vào các cấu trúc in-memory/on-disk theo cách của engine, rồi compaction xử lý các SSTable. Dữ liệu cũ và tombstone có thể được giữ trong một khoảng trước khi dọn vật lý.

Secondary index trên hệ này có thể gắn với công việc flush/compaction và cách sắp xếp dữ liệu; không nên đánh giá chỉ bằng số lệnh CQL do ứng dụng gửi.

Nếu một thuộc tính được cập nhật liên tục, giá trị index cũ và mới có thể gây áp lực lưu trữ/compaction. Với bảng có TTL và nhiều xóa, phải đo thêm tombstone và latency.

### 11.4. Bảng đọc theo truy vấn có giá riêng

Nếu dùng `orders_by_tenant_status_month`, mỗi lần đổi status từ `PENDING` sang `PAID` có thể phải:

1. Cập nhật trạng thái ở nguồn có thẩm quyền.
2. Xóa hàng khỏi nhóm PENDING trong bảng đọc.
3. Ghi hàng vào nhóm PAID.
4. Xử lý retry/đối soát nếu một bước thất bại.

Đừng giả định batch CQL giữa nhiều partition là transaction SQL có cô lập mạnh. **Lợi ích đọc được đổi bằng write amplification và bài toán nhất quán**.

---

## 12. Inverted index và công cụ tìm kiếm: số từ khóa cũng là chi phí

Một search index thường ánh xạ **token/term → danh sách document**.

Ví dụ:

~~~text
Term "nosql"       -> doc-1, doc-4, doc-9
Term "database"    -> doc-1, doc-2
Term "distributed" -> doc-2, doc-9
~~~

Khi tài liệu dài hoặc chứa nhiều trường được đánh index, một document có thể sinh ra nhiều posting. Index cho full-text search có thể lớn và chi phí update khác với một compound index B-tree thông thường.

### 12.1. Khi document thay đổi

Nếu một bài viết đổi tiêu đề hoặc nội dung:

- Nội dung mới cần được phân tích thành token theo analyzer.
- Posting list cũ phải được cập nhật/loại bỏ theo engine.
- Các segment có thể cần refresh/merge.
- Tài liệu có thể chưa xuất hiện ngay trong kết quả search nếu index có chu kỳ refresh hoặc đồng bộ bất đồng bộ.

Cần hiểu search index có là **nguồn sự thật** hay chỉ là read model từ document DBMS.

### 12.2. Mở rộng mapping cũng là một quyết định storage

Index tất cả trường dưới dạng search có thể tăng:

- Dung lượng posting/index.
- CPU phân tích dữ liệu.
- Chi phí refresh/merge.
- Thời gian rebuild.
- Số field và độ phức tạp mapping.

Nên phân loại trường được tìm full-text, lọc chính xác, sort, aggregate hoặc chỉ trả về. Không phải field nào cũng cần được index cùng kiểu.

### 12.3. Đồng bộ DBMS nguồn và search

Nếu Order đã bị xóa khỏi nguồn nhưng search vẫn trả document cũ, phải xác định:

- Có được phép trả kết quả stale không?
- Search hit có cần kiểm tra quyền/trạng thái ở nguồn trước khi trả không?
- Event xóa được retry và xử lý đúng thứ tự thế nào?
- Khi rebuild, lấy toàn bộ dữ liệu nguồn ở snapshot nào?
- Có cơ chế phát hiện index thiếu/thừa document không?

Đó là chi phí vận hành và tính đúng đắn của **index ngoài hệ nguồn**, không chỉ chi phí lưu thêm dữ liệu.

## 13. Chỉ mục tự quản lý trong key-value: nhanh khi đọc, thêm trách nhiệm khi ghi

Một kho key-value đơn giản có thể lưu Order bằng ID:

~~~text
order:order-1001 -> {customerId, status, totalVnd, ...}
~~~

Nếu muốn lấy ID theo status, ứng dụng có thể tự duy trì tập khóa:

~~~text
idx:orders:status:PAID -> {order-1001, order-1009, ...}
~~~

Trong Redis, một cách minh họa:

~~~text
HSET order:order-1001 status PAID customerId customer-42
SADD idx:orders:status:PAID order-1001
~~~

Nếu status đổi sang `REFUNDED`:

~~~text
HSET order:order-1001 status REFUNDED
SREM idx:orders:status:PAID order-1001
SADD idx:orders:status:REFUNDED order-1001
~~~

Đây chỉ là các lệnh minh họa; ứng dụng cần xác định transaction/script hoặc giao thức phù hợp, đặc biệt nếu key nằm trên các node khác nhau trong cluster.

Các rủi ro:

- Lỗi giữa hai thao tác khiến index sai.
- Retry có thể tạo side effect lặp nếu dùng counter không idempotent.
- Xóa hoặc TTL của Order không tự đảm bảo các set index được dọn.
- Tập index của một trạng thái phổ biến có thể rất lớn.
- Truy vấn theo nhiều thuộc tính phải giao hoặc kết hợp nhiều tập ID.
- Cần backfill và đối soát khi thêm index mới.

**Chỉ mục thủ công là một read model do ứng dụng chịu trách nhiệm**, khác với secondary index được DBMS duy trì bên trong phạm vi bảo đảm của engine.

---

## 14. Đánh đổi giữa nhiều index và một read model chuyên dụng

Giả sử API thường đọc:

~~~text
Q1: Order theo orderId
Q2: 20 Order mới nhất của customerId
Q3: 20 Order PAID mới nhất của customerId
Q4: Tổng doanh thu theo tháng của tenant
~~~

Các lựa chọn:

- Giữ collection nguồn với compound index phục vụ Q2/Q3.
- Tạo bảng/collection `orders_by_customer` hoặc `orders_by_customer_status`.
- Tạo bảng `monthly_revenue` tổng hợp cho Q4.
- Scan toàn bộ Order mỗi lần làm Q4, nếu dữ liệu nhỏ/tần suất thấp.

### 14.1. Một index ghép thường hiệu quả hơn nhiều index đơn lẻ

Nếu Q3 lọc theo customer, status và sort theo thời gian, ba index độc lập trên từng trường không mặc nhiên tương đương một index ghép phục vụ đúng thứ tự.

Mặt khác, index ghép được tối ưu cho một mẫu có thể không dùng tốt cho query thiếu các trường tiền tố. Phải so sánh **toàn bộ access pattern**, không chỉ một query.

### 14.2. Read model không luôn tốt hơn index

Read model theo Q3 có thể giúp đọc cực nhanh, nhưng thêm:

- Data duplication.
- Write amplification khi Order đổi status.
- Event pipeline, retry, đối soát.
- Eventual consistency nếu cập nhật bất đồng bộ.
- Backfill/rebuild khi schema thay đổi.

Nếu compound index trên nguồn đáp ứng SLO với chi phí chấp nhận được, chưa chắc read model riêng có lợi.

### 14.3. Báo cáo tổng hợp khác với index lọc

Đối với Q4, index có thể giúp giới hạn khoảng thời gian, nhưng nếu API liên tục phải tính tổng trên hàng triệu đơn, một bảng tổng hợp theo tháng có thể hợp lý hơn:

~~~json
{
  "tenantId": "tenant-7",
  "month": "2026-11",
  "paidOrderCount": 120344,
  "paidRevenueVnd": 93877120000,
  "sourceVersion": 5182
}
~~~

Đây là read model tổng hợp, cần quy tắc xử lý đổi trạng thái, refund, event trùng và backfill. Index không tự biến aggregate lớn thành phép đọc O(1).

---

## 15. Khi nào phải tạo hoặc tái xây dựng chỉ mục?

Các tình huống phổ biến:

1. **Tạo index mới** cho một API vừa xuất hiện trên dữ liệu đã có.
2. **Thay đổi thứ tự trường hoặc hướng sort** của index ghép.
3. **Thay điều kiện partial/sparse** khi workload thay đổi.
4. **Tạo unique constraint** để ràng buộc dữ liệu đang tồn tại.
5. **Đổi schema hoặc loại dữ liệu** ảnh hưởng cách tạo index key.
6. **Khôi phục index sau hỏng/lỗi** theo cơ chế sản phẩm.
7. **Chuyển DBMS hoặc tách shard/partition**, cần xây đường đọc ở nơi mới.
8. **Tạo lại read model/search index** từ nguồn sau khi pipeline sai.
9. **Đổi tokenizer/analyzer** của full-text index.
10. **Loại chỉ mục cũ** và thay bằng chỉ mục tối ưu hơn.

Cần phân biệt:

- **Index build nội bộ của DBMS:** engine tự quét nguồn và xây cấu trúc index theo hợp đồng của nó.
- **Backfill read model do ứng dụng quản lý:** worker đọc dữ liệu nguồn, ghi vào một collection/bảng/index khác và phải xử lý cả thay đổi trong lúc chạy.

Hai quá trình có thể được gọi chung “rebuild index”, nhưng độ tin cậy và giao thức khác nhau.

## 16. Vòng đời một index đang phục vụ production

Một quy trình chuyển từ index A sang index B nên có các pha rõ ràng:

~~~mermaid
flowchart TD
    A["Đề xuất index B"] --> B["Đo query và write baseline"]
    B --> C["Kiểm tra schema, uniqueness, dữ liệu nguồn"]
    C --> D["Tạo index B / bắt đầu backfill"]
    D --> E["Xây dựng và bắt kịp thay đổi"]
    E --> F["Xác minh index B đã sẵn sàng"]
    F --> G["Cho query dùng B, theo dõi canary"]
    G --> H{"Đáp ứng SLO và tính đúng?"}
    H -->|"Có"| I["Giữ B; xác minh A không còn cần"]
    I --> J["Loại A theo kế hoạch"]
    H -->|"Không"| K["Rollback đường đọc và điều tra"]
~~~

Không phải DBMS nào cũng có trạng thái “catching up” hoặc khả năng chuyển index explicit giống nhau. Sơ đồ là **quy trình vận hành** để tránh tạo index rồi xóa index cũ ngay mà chưa kiểm tra.

### 16.1. Pha chuẩn bị

Ghi lại:

- Tên index và trường/điều kiện.
- Access pattern muốn phục vụ.
- Dataset size và tốc độ tăng.
- Tần suất insert/update/delete, đặc biệt update các trường index.
- Dung lượng và tài nguyên dự phòng.
- Những ràng buộc uniqueness/collation/kiểu dữ liệu.
- SLO đọc và ghi trước thay đổi.
- Kế hoạch rollback nếu query planner hoặc application không hoạt động như dự kiến.

### 16.2. Pha xây

Một index mới trên collection lớn có thể cần:

- Đọc dữ liệu hiện hữu.
- Tạo/ghi index entries.
- Sort hoặc tổ chức dữ liệu theo engine.
- Theo dõi và tích hợp những thay đổi phát sinh trong lúc build.
- Đồng bộ metadata/index state qua node hoặc replica.
- Kiểm tra tính hợp lệ, đặc biệt với unique index.

Không nên tự suy luận rằng index build “online” nghĩa là **không ảnh hưởng latency**. Một số công việc có thể diễn ra đồng thời với traffic, nhưng vẫn chiếm CPU, RAM, I/O và có những pha khóa/ngăn thao tác tùy engine.

### 16.3. Pha kiểm chứng

- Trạng thái index đã sẵn sàng theo DBMS.
- Query dùng đúng index hay kế hoạch hợp lý.
- Độ trễ p95/p99 của query dưới tải đại diện.
- Write latency và capacity vẫn trong ngân sách.
- Index size và headroom ổn.
- Unique/partial rules đúng với dữ liệu thật.
- Nếu là read model ngoài DBMS nguồn, dữ liệu đã backfill và bắt kịp thay đổi.
- Không có lỗ hổng phân quyền hoặc stale state không chấp nhận được.

### 16.4. Pha chuyển và dọn

Chỉ loại index cũ khi đã xác minh:

- Những truy vấn phụ thuộc đã chuyển sang đường đọc mới hoặc không còn được gọi.
- Job định kỳ hiếm cũng đã được kiểm kê.
- Ràng buộc uniqueness không mất.
- Có khả năng quay lại nếu phát sinh query plan xấu.
- Cửa sổ giám sát sau rollout đủ đại diện cho traffic.

**Xóa index cũ quá sớm có thể làm API khác đột ngột chuyển sang full scan.**

---

## 17. Index build trên dữ liệu lớn: tính trước tài nguyên và thời gian

Giả sử có **200 triệu document** cần xây một index. Một thử nghiệm nhỏ cho thấy tốc độ xử lý khoảng **10.000 document/giây** trong điều kiện cụ thể.

Ước tính tối thiểu theo tốc độ này:

\[
T_{\mathrm{estimate}}
= \frac{200\,000\,000}{10\,000}
= 20\,000\ \text{giây}
\approx 5.56\ \text{giờ}.
\]

Con số **không phải dự báo chính xác**. Trong production, tốc độ có thể thay đổi do:

- Cache nóng/lạnh.
- Dung lượng và loại index.
- Số shard, phân phối key và replication.
- Write traffic đồng thời.
- Khả năng giữ dữ liệu trung gian trong RAM.
- I/O saturation, compaction hoặc network.
- Pha commit/validation cuối build.
- Giới hạn tài nguyên của managed service.

Ngoài ra, nếu dataset tăng trong lúc build, engine hoặc pipeline phải xử lý cả các thay đổi mới.

### 17.1. Dự trù dung lượng tạm

Giả sử index mới dự kiến chiếm 30 GB logic. Trong quá trình chuyển có thể cần:

~~~text
Index cũ vẫn tồn tại.
Index mới đang được xây.
Có dữ liệu sort/build tạm.
Có replication và backup theo cấu hình.
Có tăng trưởng dữ liệu mới trong thời gian build.
~~~

Không nên chỉ kiểm tra còn 30 GB đĩa trống rồi bắt đầu. Cần headroom phù hợp với engine, cluster và phương án rollback.

### 17.2. Giới hạn concurrency

Chạy nhiều index build cùng lúc có thể làm quá tải disk và CPU. Trước khi triển khai, cân nhắc:

- Lập lịch theo thời gian ít tải.
- Giới hạn số index được build đồng thời.
- Theo dõi read/write p95/p99 và replication lag.
- Có ngưỡng dừng/cancel hoặc rollback phù hợp sản phẩm.
- Tránh vừa tạo index lớn vừa thực hiện migration/compaction nặng nếu capacity không đủ.
- Phân chia từng shard/collection khi kiến trúc và công cụ hỗ trợ.

**Thời điểm build quan trọng gần bằng định nghĩa index** đối với hệ thống phục vụ traffic 24/7.

---

## 18. Backfill read model: khác với DBMS tự xây secondary index

Giả sử ứng dụng tạo collection `orders_by_customer` để thay thế một đường đọc cũ.

Nếu chỉ quét 50 triệu Order hiện có rồi ghi sang collection mới, các Order được thêm hoặc sửa **trong lúc backfill** có thể bị bỏ sót hoặc bị bản cũ ghi đè.

### 18.1. Quy trình có nguồn sự thật

Một chiến lược:

~~~mermaid
sequenceDiagram
    participant Source as Orders nguồn
    participant Change as CDC / Outbox
    participant Worker as Backfill worker
    participant View as Read model

    Source->>Change: Ghi nhận thay đổi từ mốc xác định
    Worker->>Source: Đọc snapshot hoặc các batch dữ liệu gốc
    Source-->>Worker: Order và version
    Worker->>View: Upsert theo ID/version
    Change-->>Worker: Các thay đổi phát sinh
    Worker->>View: Áp dụng theo version, bỏ qua bản cũ
    Worker->>View: Đối soát nguồn và bản chiếu
~~~

Cần định nghĩa:

1. Mốc nguồn được coi là snapshot.
2. Cách lấy change log cho những ghi xảy ra trong lúc quét.
3. Identity của mỗi bản ghi trong index/read model.
4. Thứ tự/version để không cho event cũ ghi đè event mới.
5. Cách xử lý delete/tombstone.
6. Khi nào xác nhận projection đã **bắt kịp**.
7. Cách đối soát trước khi chuyển traffic.

### 18.2. Idempotency

Một upsert theo khóa ổn định và version có thể được thiết kế an toàn khi worker retry. Nhưng các thao tác như:

~~~text
monthlyRevenue += order.total
activeOrderCount += 1
~~~

không idempotent nếu event bị xử lý hai lần. Phải có deduplication, conditional update, ledger hoặc khả năng tính lại aggregate theo nguồn.

### 18.3. Checkpoint

Ví dụ:

~~~json
{
  "jobId": "rebuild-orders-by-customer-20261114",
  "segment": "tenant-7",
  "lastProcessedOrderId": "order-250000",
  "processedCount": 250000,
  "failedCount": 3,
  "sourceWatermark": "version-5182"
}
~~~

Checkpoint chỉ an toàn nếu cách quét có thứ tự và phạm vi được định nghĩa rõ. Nếu một Order mới có ID nằm trước cursor, quét theo ID mà không có snapshot/change capture có thể bỏ sót.

### 18.4. Xử lý lỗi và khôi phục

Nếu worker chết sau khi ghi view nhưng trước khi lưu checkpoint, batch có thể bị chạy lại. Do đó **ghi view phải idempotent**. Nếu nguồn thay đổi trong lúc worker chạy, các update về sau phải áp dụng theo version có thẩm quyền.

Nếu cần phục hồi sau mất toàn bộ read model, nên có tài liệu chỉ rõ:

- Nguồn để xây lại.
- Thời lượng dự kiến và capacity cần thiết.
- Kế hoạch bắt kịp thay đổi.
- Tiêu chí sẵn sàng để trả traffic.
- Cách xử lý khi view không còn đồng bộ.

---

## 19. Unique index: rủi ro ở giai đoạn build và rollout

Unique index vừa là đường truy cập vừa là **ràng buộc tính đúng đắn**.

### 19.1. Dữ liệu trước đó có thể không sạch

Giả sử có hai User trùng `(tenantId, normalizedEmail)` do các lần nhập dữ liệu cũ.

Tạo unique index có thể thất bại. Không nên xử lý bằng cách “xóa một trong hai cho build thành công” nếu chưa hiểu:

- User nào là bản có thẩm quyền.
- Các quan hệ/order tham chiếu tới từng User.
- Quyền truy cập và lịch sử cần giữ.
- Có được phép gộp tài khoản hay không.
- Có cần chỉnh luồng đăng ký để không tạo duplicate mới trong lúc dọn dữ liệu.

### 19.2. Dọn duplicate và chặn ghi mới phải được phối hợp

Một quy trình:

1. Xác định phạm vi uniqueness.
2. Rà soát dữ liệu trùng hiện có.
3. Sửa nguyên nhân tạo trùng trong đường ghi.
4. Dọn duplicate theo quy tắc nghiệp vụ.
5. Tạo unique index/constraint theo DBMS.
6. Kiểm thử ghi cạnh tranh và retry.
7. Theo dõi duplicate-key errors sau triển khai.

Nếu dọn dữ liệu trước nhưng không chặn việc tạo duplicate mới, quá trình build vẫn có thể thất bại vì một request đến giữa chừng.

### 19.3. Unique index không thay thế mọi ràng buộc

Unique trên `(tenantId, normalizedEmail)` không đảm bảo:

- Email thực sự thuộc về user.
- Tenant tham chiếu tồn tại.
- Mỗi user có profile nếu đó là quy tắc bắt buộc.
- Quyền ghi và đọc đúng.
- Những người dùng có email null/missing được xử lý theo cách nghiệp vụ mong muốn.

Đó là lý do không xem index build là thao tác thuần hiệu năng trong những trường hợp dùng để bảo đảm uniqueness.

---

## 20. Tính nhất quán khi rebuild: DB-managed index và external view

| Đặc tính | Index do DBMS duy trì | Read model/search index ngoài nguồn |
|---|---|---|
| Nơi định nghĩa | Schema/config/index của engine | Collection, bảng hoặc dịch vụ riêng |
| Đồng bộ | Theo bảo đảm của DBMS, có thể khác giữa loại index | Do app/CDC/stream phụ trách |
| Cách rebuild | Lệnh/cơ chế build của DBMS | Backfill nguồn, bắt sự kiện, đối soát |
| Trạng thái phục vụ | Theo lifecycle của engine | Cần định nghĩa readiness và lag |
| Xử lý ghi phát sinh | Engine tích hợp theo hợp đồng | Cần thiết kế version, idempotency |
| Recovery | Công cụ/replica của DBMS | Worker, checkpoint, replay và source |
| Chi phí vận hành | Resource pressure, index lifecycle | Thêm pipeline và người chịu trách nhiệm |

**Đừng gán tính nhất quán nguyên tử của một index nội bộ MongoDB cho GSI DynamoDB hoặc read model bất đồng bộ do ứng dụng xây.** Mỗi sản phẩm có hợp đồng riêng.

### 20.1. Cần tách ba loại “xong”

- **Build completed:** quá trình xây đã báo hoàn tất.
- **Ready for query:** index đã ở trạng thái có thể phục vụ truy vấn theo hệ thống.
- **Verified for workload:** query chạy đúng, đủ nhanh và không làm write path vi phạm ngân sách.

Có những trường hợp index đã tạo xong nhưng query planner không dùng, dùng kém hiệu quả hoặc lợi ích đọc không bù được write cost.

### 20.2. Eventual consistency và đọc ngay sau ghi

Nếu một GSI/search index/read model có thể trễ, API vừa tạo Order rồi lập tức query bằng index đó có thể chưa thấy Order.

Các lựa chọn:

- Trả dữ liệu từ nguồn của thao tác vừa ghi.
- Hiển thị trạng thái “đang cập nhật” trong UX.
- Dùng đường đọc có consistency mạnh hơn trong phạm vi hỗ trợ.
- Chờ view bắt kịp version, có timeout và fallback.
- Thiết kế API cho phép dữ liệu trễ với hợp đồng rõ.

Không được chỉ ghi “index đã tồn tại” rồi suy ra mọi đường đọc nhất quán tức thời.

---

## 21. Tạo index mới mà không làm gián đoạn API

Một cách rollout theo pha:

### Pha A — Baseline

Ghi:

~~~text
Q2 p50/p95/p99
Insert p50/p95/p99
Update-status p95/p99
Throughput đọc/ghi
CPU, RAM, disk I/O, disk free
Index size hiện tại
Keys/docs examined hoặc chỉ số đọc tương ứng
Hot tenant / hot partition
~~~

### Pha B — Kiểm tra dữ liệu

Xác minh kiểu trường, tỷ lệ missing/null, mảng quá lớn, giá trị trùng nếu unique, trường thời gian và collation. Lỗi dữ liệu có thể chỉ lộ ra khi build index trên tập lớn.

### Pha C — Tạo index

Theo cơ chế DBMS phù hợp, giám sát:

- Tốc độ build.
- CPU/I/O tăng.
- Độ trễ request chính.
- Replication/compaction.
- Dung lượng dùng tạm.
- Error hoặc tiến trình bị dừng.

### Pha D — Canary query

Cho một phần request hoặc bộ benchmark đại diện sử dụng đường truy vấn mới. Đối chiếu kết quả, latency và tác động lên write workload.

### Pha E — Cutover

Chuyển traffic đọc dần khi index đã được xác minh. Nếu có read model ngoài nguồn, phải đợi backfill và catch-up xong trước khi dùng làm nguồn đọc chính.

### Pha F — Quan sát và dọn

Chỉ drop index cũ sau khi không còn query bắt buộc dùng nó và có đường rollback phù hợp.

**Không nên xóa index cũ đồng thời với việc tạo index mới trong một thay đổi không thể quay lại**, trừ khi kế hoạch và mức rủi ro cho phép rõ ràng.

## 22. Khi nào nên bỏ một index?

Dấu hiệu:

- Query tương ứng đã bị xóa khỏi sản phẩm.
- Query chuyển sang một index ghép khác phục vụ tốt hơn.
- Index cực lớn nhưng gần như không được dùng trong khoảng quan sát đủ đại diện.
- Index làm đường ghi bị nghẽn, trong khi lợi ích đọc nhỏ.
- Trường được index không còn dùng hoặc schema đã thay.
- Index có điều kiện quá rộng so với partial index có thể thay thế.

Nhưng một index có ít reads có thể vẫn có vai trò **unique constraint** hoặc phục vụ job hiếm theo kỳ. Trước khi drop, cần kiểm kê cả API, batch, báo cáo, migration và ràng buộc nghiệp vụ.

### 22.1. Dừng tạo index mới không đồng nghĩa xóa index cũ

Khi sản phẩm ngừng ghi một thuộc tính, index cũ có thể còn cần cho dữ liệu lịch sử hoặc công cụ truy xuất. Phải xét retention và các truy vấn dữ liệu cũ.

### 22.2. Không dùng một ngày thống kê để kết luận

Một index chỉ được gọi trong kỳ đối soát cuối tháng có thể không xuất hiện trong thống kê một tuần. Nên kết hợp query logs, code path và lịch vận hành trước khi loại bỏ.

### 22.3. Thao tác drop cũng cần kế hoạch

Drop index có thể thay đổi query plan đột ngột và có chi phí tài nguyên/metadata theo engine. Nếu sau drop cần tạo lại trên hàng trăm triệu document, việc “rollback” không phải lúc nào cũng tức thời: có thể phải **rebuild tốn nhiều giờ**.

---

## 23. Bảo mật và khả năng xóa dữ liệu liên quan đến index

Một index có thể chứa dữ liệu hoặc bản sao đủ để suy ra thông tin nhạy cảm.

Ví dụ search index chứa email, địa chỉ hoặc mô tả có thông tin cá nhân. Xóa document nguồn mà không dọn search index có thể khiến kết quả tìm kiếm vẫn lộ dữ liệu.

Cần thiết kế:

- Phạm vi tenant trong index key và query.
- Quyền truy cập chỉ mục/read model.
- Mã hóa khi lưu/truyền theo hệ thống.
- Dữ liệu nào được project vào index.
- Xóa và đồng bộ trạng thái delete.
- Backup/snapshot chứa index hoặc dữ liệu cần tái tạo index.
- Khả năng rebuild từ nguồn không tái đưa record đã xóa vào view.

### 23.1. Index không phải lớp kiểm soát quyền

Một compound index bắt đầu bằng `tenantId` giúp query định vị dữ liệu, nhưng backend vẫn phải kiểm tra tenant người gọi được phép truy cập.

Với GSI hoặc read model bất đồng bộ, quyền thay đổi có thể được cập nhật trễ. Nếu hệ dùng index stale để trả dữ liệu xuyên ranh giới quyền, đó là lỗi tính đúng đắn nghiêm trọng. Các API nhạy cảm cần kiểm tra nguồn có thẩm quyền hoặc một cơ chế phù hợp bảo đảm quyền.

### 23.2. Rebuild từ backup cũ

Nếu nguồn khôi phục từ một backup cũ, rebuild index có thể đưa trở lại dữ liệu đã bị xóa theo yêu cầu trong thời gian sau backup. Cần áp dụng lại deletion requests/tombstones và chính sách retention theo quy trình phục hồi trước khi phục vụ dữ liệu.

Index rebuild không được xem là cách bỏ qua lịch sử xóa.

---

## 24. Đo gì để quyết định giữ, thêm hoặc bỏ index?

| Mục tiêu | Chỉ số | Câu hỏi |
|---|---|---|
| Lợi ích đọc | p50/p95/p99, timeout | Query có đáp ứng SLO ở tải cao điểm? |
| Hiệu quả đọc | keys/docs examined, rows/bytes read | Có quét quá nhiều so với số kết quả? |
| Chi phí ghi | insert/update/delete p95/p99 | Index mới có làm write path chậm? |
| Write capacity | Units/ops, throttling, queue depth | Có đủ tài nguyên duy trì index? |
| Dung lượng | Index bytes, data bytes, replica | Index chiếm tỷ lệ bao nhiêu và tăng nhanh không? |
| Cache | Cache hit/miss, memory pressure | Index mới có đẩy dữ liệu nóng khỏi cache? |
| Build | Duration, processed records, failure | Có thể xây lại trong thời gian vận hành cho phép? |
| Backfill | Lag, backlog, version gap | Read model đã bắt kịp nguồn chưa? |
| Độ đúng | Mismatch/missing/duplicate | Có kết quả sai hoặc view stale quá mức? |
| Vận hành | Retry, compaction, replication lag | Có ảnh hưởng sang workload khác? |
| Bảo mật | Unauthorized results, stale entitlements | Index có thể trả dữ liệu sai quyền không? |

### 24.1. So sánh trong cùng điều kiện

Một phép thử hợp lệ nên ghi:

- DBMS và phiên bản.
- Schema, index definitions và dataset size.
- Tỷ lệ read/write/delete.
- Phân bố tenant và trạng thái; có hot keys.
- Số node, replica, storage class, cache warm/cold.
- Concurrency, thời gian warm-up và thời lượng đo.
- Kết quả nhiều lần chạy nếu có.
- Độ tin cậy của số liệu so với production.

Tránh so sánh query có index trên cache ấm với query không index trên cache lạnh rồi kết luận chỉ số latency khác biệt hoàn toàn do index.

### 24.2. Ví dụ số liệu giả định

| Metric | Trước index | Sau index | Diễn giải |
|---|---:|---:|---|
| Q2 p95 | 420 ms | 32 ms | Đọc được cải thiện trong phép thử |
| Q2 p99 | 900 ms | 75 ms | Tail latency tốt hơn |
| Insert p95 | 15 ms | 23 ms | Ghi chịu chi phí bổ sung |
| Update-status p95 | 19 ms | 31 ms | Trường indexed đổi thường xuyên |
| Index storage mới | 0 GB | 2,4 GB | Dung lượng bổ sung cần budget |
| Write throughput trước throttle | 6.000/s | 4.900/s | Có thể là nút thắt mới |

**Tất cả số liệu trong bảng là ví dụ giả định**, không phải kết quả benchmark của một sản phẩm cụ thể. Không được khẳng định index “giảm 90%” trong production khi chưa có phép đo tương ứng.

## 25. Ma trận quyết định theo workload

Một hệ đơn hàng có ba hướng:

- **A:** Không thêm index, chấp nhận scan/filter trong một số query.
- **B:** Thêm compound index theo customer, status và thời gian.
- **C:** Duy trì read model riêng `orders_by_customer_status`.

| Tiêu chí | A — Không thêm | B — Compound index | C — Read model riêng |
|---|---|---|---|
| Q2 đọc 20 đơn gần nhất | Có thể chậm khi dữ liệu lớn | Có khả năng nhanh nếu index phù hợp | Có thể tối ưu sâu theo query |
| Insert | Ít index phụ hơn | Phải duy trì index | Ghi nguồn và cập nhật view |
| Update status | Ít công việc phụ hơn | Thay index entry | Có thể chuyển record giữa nhóm view |
| Dung lượng | Thấp hơn ở phần index đang xét | Tăng theo index entries | Tăng do dữ liệu nhân bản/index |
| Tính nhất quán | Nguồn trực tiếp | Theo bảo đảm index nội bộ | Có thể stale nếu view bất đồng bộ |
| Xây/tái xây | Ít công việc index phụ | Build index từ nguồn | Backfill + CDC + đối soát |
| Vận hành | Query scan có thể làm nghẽn | Theo dõi planner/index lifecycle | Pipeline và replay/recovery |
| Thích hợp khi | Dataset nhỏ, query hiếm | Query đọc lặp nhiều và có filter/sort rõ | Nhiều đường đọc đặc thù hoặc tổng hợp |

### 25.1. Quyết định không chỉ bằng tốc độ đọc

Giả sử Q2 chiếm 40% traffic và đang vi phạm SLO, B có thể là bước đầu phù hợp nếu thỏa write budget. Nếu Q2 chỉ là job báo cáo chạy một lần/tháng, A hoặc job phân tích riêng có thể hợp lý hơn.

C có thể đáng chọn khi B không đáp ứng hiệu năng hoặc mô hình truy vấn phức tạp, nhưng phải chấp nhận quản lý consistency và backfill.

### 25.2. Các ràng buộc bắt buộc

Trước khi chấm điểm phương án, hãy loại những lựa chọn vi phạm:

- Phân quyền tenant.
- Tính duy nhất nghiệp vụ.
- Read-your-writes nếu bắt buộc.
- Ngân sách write throughput tối thiểu.
- Khả năng phục hồi index/read model trong thời gian chấp nhận.
- Quy định retention và xóa dữ liệu.

Một phương án đọc nhanh nhưng làm lộ dữ liệu hoặc phá uniqueness **không thể được chọn** chỉ vì p95 đẹp.

---

## 26. Tình huống thường gặp và cách xử lý

### 26.1. Index quá nhiều, insert ngày càng chậm

Dấu hiệu: insert p99 tăng dần theo số lượng index; index size lớn; nhiều index ít được dùng.

Hướng xử lý:

1. Kiểm kê index và access pattern.
2. Đo usage trên cửa sổ đủ đại diện.
3. Tìm index trùng lặp/được thay thế bởi index khác, kiểm tra prefix/sort.
4. Xác nhận unique/TTL constraints trước khi bỏ.
5. Thử bỏ từng index không cần thiết theo quy trình an toàn.
6. Đo lại write latency, read plan và disk footprint.

### 26.2. Một index hiệu quả khi ít dữ liệu, nay query vẫn chậm

Có thể do:

- Dataset lớn và phân bố key lệch.
- Hot tenant có hàng triệu document.
- Bộ lọc trở nên ít chọn lọc.
- Query thay đổi sort hoặc projection.
- Cache không đủ.
- Một index được chọn nhưng vẫn đọc nhiều docs.
- Index/read model chưa bắt kịp dữ liệu mới.

Cần xem plan/metrics; không mặc định “tạo thêm một index nữa” là cách giải quyết.

### 26.3. Tạo unique index thất bại

Cần xác định duplicate và nguyên nhân đường ghi tạo trùng, dọn theo nghiệp vụ, khóa race hợp lý rồi build lại. Không tự xóa record tùy tiện.

### 26.4. GSI build kéo dài

Kiểm tra trạng thái build/backfill, năng lực bảng và index, throttling, dung lượng, tốc độ ghi mới và giới hạn dịch vụ. Không chuyển query sang GSI trước khi nó sẵn sàng.

### 26.5. Read model mới thiếu dữ liệu

Kiểm tra snapshot watermark, checkpoint, event ordering, delete events, worker retries và khả năng áp version. Chỉ đếm số record bằng nhau chưa chứng minh hai tập ID và trạng thái khớp nhau.

### 26.6. Index build làm production chậm

Giảm khối lượng công việc đồng thời theo khả năng engine, thay đổi lịch build, mở capacity nếu phù hợp, theo dõi SLO chính và dừng/rollback theo runbook. **Đừng tiếp tục một build chỉ vì đã chạy được 90%** khi nó khiến API quan trọng bị gián đoạn.

---

## 27. Thực hành tổng hợp: thiết kế chỉ mục cho hệ đơn hàng

### 27.1. Bối cảnh

Một dịch vụ NoSQL có:

~~~text
20 triệu đơn hiện có.
100.000 đơn mới/ngày.
50.000 lần đổi status/ngày.
Mỗi đơn có tenantId, customerId, status, createdAt, totalVnd.
85% traffic là đọc, 15% là ghi.
Khách hàng lớn nhất tạo 20% traffic.
API danh sách chỉ trả tối đa 50 đơn/trang.
~~~

Các yêu cầu:

| ID | Truy vấn | Mục tiêu |
|---|---|---|
| Q1 | Lấy Order theo `orderId` | Point lookup |
| Q2 | 20 đơn mới nhất của customer trong tenant | p95 dưới 120 ms |
| Q3 | 20 đơn PAID mới nhất của customer | p95 dưới 120 ms |
| Q4 | Báo cáo tổng doanh thu tenant theo tháng | Có thể bất đồng bộ |
| W1 | Tạo đơn | p95 dưới 50 ms |
| W2 | Đổi status | Không cập nhật sai Order/tenant |

### 27.2. Phương án thử

**Phương án A — Index nguồn:**

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "orders_by_customer_recent" }
);
~~~

Phục vụ Q2. Q3 có thể cần index theo `status` nếu tần suất cao và index A không đủ.

**Phương án B — Thêm index cho Q3:**

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "paid_and_other_status_by_customer" }
);
~~~

Phục vụ bộ lọc status nếu kế hoạch phù hợp, nhưng tăng chi phí duy trì index khi Order đổi trạng thái.

**Phương án C — Read model riêng cho Q3:**

~~~text
orders_by_customer_status
  PK = tenantId#customerId#status
  SK = createdAt#orderId
~~~

Phải backfill 20 triệu Order và đồng bộ thay đổi W1/W2, gồm xóa khỏi nhóm trạng thái cũ và thêm vào nhóm mới.

### 27.3. Yêu cầu bài làm

1. Chỉ ra index nào phục vụ Q2 và Q3, và tại sao trường `status` ảnh hưởng thứ tự sort.
2. Nêu các bước ghi thêm khi W1 tạo Order.
3. Nêu các bước index maintenance khi W2 đổi `PENDING -> PAID`.
4. Nếu muốn chỉ index đơn đang `OPEN`, đề xuất partial index và điều kiện query cần đi kèm.
5. Ước tính dung lượng logic của hai index nếu mỗi index entry trung bình 90 byte/document.
6. Lập kế hoạch xây index trên 20 triệu Order mà vẫn có request ghi.
7. Xác định mức read/write latency và số keys/docs examined cần đo trước/sau.
8. Nếu chọn read model, thiết kế checkpoint và version để tránh event cũ ghi đè.
9. Khi muốn drop index A, cần kiểm tra query/job nào còn phụ thuộc?
10. Viết một ADR ngắn lý giải lựa chọn cho giai đoạn hiện tại và điều kiện phải xem xét lại.

### 27.4. Gợi ý tính dung lượng

Giả sử mỗi index có một entry/document với 90 byte logic:

\[
20\,000\,000 \times 90 = 1.8\ \text{GB/index}.
\]

Hai index xấp xỉ:

\[
2 \times 1.8 = 3.6\ \text{GB logic}.
\]

Đây chỉ là **phép tính sơ bộ**, chưa bao gồm index metadata, cấu trúc lưu trữ, replica, compression, WAL, snapshot, backup hoặc overhead build.

### 27.5. Gợi ý quyết định

Có thể bắt đầu từ index A nếu Q2 là truy vấn phổ biến, đo Q3 với workload thật, sau đó cân nhắc index B hoặc read model C khi cần. Không tạo đồng thời mọi cấu trúc chỉ vì chúng đều làm một truy vấn nhanh hơn.

Khi thêm index B, phải có thử nghiệm **W2 đổi status**, vì đây là thao tác trực tiếp tác động trường index. Nếu W2 đang gần giới hạn write capacity, lợi ích của Q3 cần được so với chi phí update.

### 27.6. Một ADR ngắn

~~~markdown
# ADR: Index danh sách đơn hàng theo khách

## Bối cảnh
- Q2 và Q3 yêu cầu phân trang theo thời gian.
- 20 triệu Order, dữ liệu tiếp tục tăng.
- W1/W2 thường xuyên.
- Read SLO: p95 < 120 ms.
- Write SLO: p95 < 50 ms.

## Phương án
A. Một index tenant/customer/time.
B. Thêm index tenant/customer/status/time.
C. Read model theo customer/status.

## Số liệu
- Q2/Q3 p95/p99 trước và sau.
- Insert/update p95/p99.
- Index bytes và tốc độ tăng.
- Keys/docs examined.
- Build duration và replication/compaction impact.

## Quyết định
Chọn ... vì ... (số liệu).
Chấp nhận ... (chi phí).
Không chọn ... vì ... (rủi ro/chưa cần).

## Rollout và rollback
- Kiểm tra dữ liệu hiện có.
- Build index có giám sát.
- Canary query và đo lại write workload.
- Không drop index cũ trước khi xác minh.
- Có đường quay lại nếu p99 hoặc lỗi tăng.

## Xem xét lại khi
- Query đổi filter/sort.
- Index storage vượt ngân sách.
- W2 write p99 vi phạm SLO.
- Dataset tăng gấp nhiều lần.
- Một hot tenant gây nghẽn.
~~~

## 28. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Index chỉ tăng tốc đọc, không ảnh hưởng ghi.” | Insert/update/delete có thể phải duy trì index. |
| “Mỗi index thêm đúng một lần ghi vật lý.” | Write amplification phụ thuộc engine, key và cấu trúc lưu trữ. |
| “Index có kích thước bằng đúng tổng byte của field.” | Còn pointer, metadata, compression, replica và các entry bổ sung. |
| “Một document chỉ có một entry trong mọi index.” | Mảng, token và cấu trúc index khác có thể sinh nhiều entry. |
| “Index trên status luôn tốt.” | Nếu status ít giá trị và query không đủ chọn lọc, lợi ích có thể hạn chế. |
| “Có index đơn lẻ trên từng trường là đủ thay compound index.” | Filter + sort có thể cần một cấu trúc ghép phù hợp. |
| “Covering index không tốn chi phí.” | Trường được project làm index lớn hơn và có thể tăng chi phí update. |
| “Partial index miễn phí khi ghi.” | Item đi vào/ra tập được index cần cập nhật. |
| “Unique index chỉ là tối ưu.” | Nó còn có vai trò ràng buộc; build có thể thất bại vì duplicate. |
| “Index build online không gây tải.” | Vẫn tiêu CPU/I/O/RAM, có thể ảnh hưởng p99. |
| “Tạo index xong là mọi query sẽ dùng nó.” | Planner và access pattern quyết định đường thực thi. |
| “Xóa index cũ có thể khôi phục tức thì.” | Tạo lại trên dữ liệu lớn có thể mất nhiều giờ. |
| “GSI luôn đọc trạng thái mới nhất.” | GSI DynamoDB hỗ trợ đọc eventual consistent. |
| “GSI query tự lấy mọi trường từ table.” | Phải xét projection và thuộc tính sẵn có trên index. |
| “SAI thay thế mọi thiết kế partition key Cassandra.” | Cần chọn primary key và phạm vi query phù hợp. |
| “Read model tự đúng vì có CDC.” | Cần version, idempotency, backfill và đối soát. |
| “Index không chứa thông tin nhạy cảm.” | Key/projected data có thể làm lộ dữ liệu và phải được bảo vệ. |
| “Chỉ nhìn read latency là đủ.” | Phải đo ghi, storage, build/recovery và tính đúng đắn. |
| “Index không được dùng trong một ngày thì có thể xóa.” | Có thể phục vụ job hiếm hoặc unique constraint. |
| “Chạy lại backfill là sẽ hết sai.” | Nếu không có snapshot/version hoặc xử lý delete đúng, có thể tái tạo lỗi. |

## 29. Tổng kết

Chỉ mục tạo ra **đường truy cập phụ** giúp ứng dụng định vị dữ liệu mà không phải quét mọi bản ghi, nhưng lợi ích đọc luôn đi kèm một số chi phí:

- **Chi phí ghi:** engine hoặc ứng dụng phải duy trì index khi insert, update indexed fields, delete và xử lý các bản chiếu.
- **Chi phí lưu trữ:** index entries, key/pointer, projected attributes, metadata, replication, backup và dung lượng tạm khi build.
- **Chi phí tái xây dựng:** quét dữ liệu nguồn, tổ chức lại cấu trúc, bắt thay đổi mới, dùng tài nguyên production và kiểm chứng kết quả.
- **Chi phí độ phức tạp:** rollout, rollback, unique constraint, eventual consistency, monitoring, recovery và bảo mật.

Khi quyết định tạo index, cần làm rõ **query nào được tối ưu, mức lợi ích đã đo, tác động lên đường ghi, dung lượng dài hạn và khả năng tái xây dựng**.

Một quy trình tốt là:

1. Bắt đầu từ access pattern và SLO.
2. Chọn loại index phù hợp, tránh tạo index cho mọi trường.
3. Đo read/write và ước lượng storage trên dữ liệu đại diện.
4. Lập kế hoạch build/backfill có headroom và giám sát.
5. Xác minh index mới trước khi chuyển traffic.
6. Đối soát và kiểm tra consistency nếu dùng read model ngoài nguồn.
7. Chỉ loại index cũ khi không còn query/ràng buộc phụ thuộc.
8. Ghi điều kiện xem xét lại khi workload, data size hoặc chi phí thay đổi.

**Một chỉ mục tốt không phải chỉ mục khiến một truy vấn nhanh nhất bằng mọi giá; đó là chỉ mục đem lại lợi ích đọc có thể chứng minh, với chi phí ghi, lưu trữ và tái xây dựng mà toàn hệ thống có thể chấp nhận và vận hành an toàn.**
