# Đánh giá chi phí ghi nhiều bảng và đối soát tính nhất quán

## Mục tiêu bài học

Khi thiết kế dữ liệu theo truy vấn trong Apache Cassandra, cùng một thực thể nghiệp vụ có thể được lưu vào nhiều bảng để phục vụ nhiều đường đọc: tìm theo ID, liệt kê theo khách hàng, lọc theo trạng thái hoặc đọc theo thời gian. Cách **denormalization** này thường giảm số partition phải đọc, nhưng mỗi lần tạo, sửa hoặc xóa dữ liệu sẽ phát sinh **nhiều mutation**, nhiều lần truyền dữ liệu và nguy cơ các bảng không cập nhật đồng thời.

Bài học thuộc chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung tập trung vào **đánh giá chi phí ghi nhiều bảng và đối soát tính nhất quán** trong Cassandra: từ hợp đồng truy vấn, CQL, replication và consistency level đến lỗi mạng, tombstone, compaction, repair và cách ứng dụng Java duy trì các bảng biểu diễn dữ liệu.

Sau bài học, bạn có thể:

- Ước tính số **mutation logic**, lượng byte ghi, số partition đích và tác động của replication khi một nghiệp vụ có nhiều projection.
- Phân tích lợi ích giảm **read fan-out** so với chi phí tăng **write amplification**, lưu trữ và vận hành.
- Phân biệt nhất quán **giữa replica của một partition** và nhất quán **giữa các bảng nghiệp vụ**; không nhầm `LOCAL_QUORUM`, logged batch, LWT hoặc repair với giao dịch SQL xuyên bảng.
- Thiết kế **nguồn sự thật**, revision/event ID, quy tắc cập nhật projection và cách xử lý ghi lặp, đến sai thứ tự hoặc thất bại từng phần.
- Xây dựng phép **đối soát (reconciliation)** với invariant rõ ràng, đầu vào có thể duyệt, cơ chế sửa an toàn và metric phát hiện lệch.
- Viết CQL và mã Java minh họa, đồng thời xây bộ kiểm thử lỗi và tiêu chí vận hành.

## 1. Vấn đề: đọc đơn giản hơn, ghi phức tạp hơn

Một ứng dụng bán hàng nhiều tenant có ba yêu cầu:

| ID | Hành vi đọc | Đầu vào mà caller luôn có | Đường truy cập mong muốn |
| --- | --- | --- | --- |
| Q01 | Tra cứu một đơn | `tenant_id`, `order_id` | Một partition theo ID |
| Q02 | Danh sách đơn của một khách trong tháng UTC | `tenant_id`, `customer_id`, `month_bucket` | Một partition, mới nhất trước |
| Q03 | Danh sách đơn đang `PENDING` được tạo trong ngày | `tenant_id`, `status`, `created_day` | Một partition theo trạng thái/ngày |

Giả sử Q02 và Q03 đều là màn hình quan trọng, đòi độ trễ thấp. Nếu chỉ có bảng theo ID, một lần đọc danh sách có thể cần biết trước rất nhiều order ID. Nếu chỉ có bảng theo khách hàng, Q03 không biết khách hàng nào có đơn đang chờ và phải thăm dò nhiều partition.

Ta có thể tạo **ba bảng theo ba query shape**. Đường đọc được đơn giản hóa, nhưng một đơn mới cần ghi ba nơi. Khi đơn đổi trạng thái từ `PENDING` sang `PAID`, một hàng phải biến mất khỏi partition trạng thái cũ và xuất hiện ở partition trạng thái mới. Nếu mất kết nối giữa các thao tác, người dùng có thể thấy dữ liệu không khớp.

Đó là đánh đổi cần lượng hóa:

```text
Ít bảng, ít mutation hơn
    -> có thể cần đọc nhiều partition, lọc/merge ở dịch vụ

Nhiều projection theo truy vấn
    -> đọc ít partition hơn
    -> tăng mutation, lưu trữ, độ phức tạp cập nhật và đối soát
```

**Nguyên tắc:** một bảng projection chỉ đáng thêm nếu lợi ích của **đường đọc xác định, có giới hạn** lớn hơn chi phí **ghi và duy trì tính đúng nghiệp vụ** ở tải thực tế.

## 2. CQL: ba biểu diễn của cùng một đơn

Các schema sau dùng `tenant_id` là chuỗi, `order_id/customer_id` là UUID và bucket theo **thời điểm tạo đơn UTC**. Chúng là ví dụ độc lập để tính chi phí và đối soát.

### 2.1. Bảng nguồn tra cứu theo ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    updated_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, current_status,
       total_amount, updated_at, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Trong ví dụ, ứng dụng coi `orders_by_id` là **hàng trạng thái nguồn để quyết định bản hiện tại**. `revision` là phiên bản nghiệp vụ do ứng dụng/luồng sự kiện cấp; Cassandra **không tự tăng** trường này. Cơ chế ghi phải bảo đảm sự kiện phiên bản cũ không được phép cập nhật lùi trạng thái nguồn.

### 2.2. Projection danh sách theo khách/tháng

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    current_status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, current_status, total_amount, revision
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` theo dạng `YYYY-MM` từ `created_at` ở UTC; ví dụ `2026-11`. Trong bảng này, `current_status` là cột dữ liệu thường, có thể được cập nhật trên cùng hàng khi trạng thái đổi.

### 2.3. Projection hàng đợi theo trạng thái/ngày tạo

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    current_status text,
    created_day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, current_status, created_day),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount, revision
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = 'PENDING'
  AND created_day = ?
LIMIT 50;
```

Ở đây `created_day` có nghĩa **ngày tạo đơn UTC**, không phải ngày đơn chuyển sang `PENDING`. Vì `current_status` nằm trong partition key, đổi trạng thái không thể thực hiện như cập nhật một regular column trong cùng hàng: cần **xóa hàng ở khóa trạng thái cũ và ghi hàng ở khóa mới**.

Ba bảng trên đều cho phép một truy vấn quan trọng đọc đúng **một partition logic** nếu caller có đầy đủ khóa. Tuy nhiên, bảng status/day có thể quá lớn hoặc nóng khi tenant có rất nhiều đơn trong một trạng thái. Tính phù hợp về CQL **chưa phải** xác nhận về SLA.

## 3. Đếm mutation trên đường ghi

Trước khi tối ưu, cần phân biệt ba đại lượng:

- **Mutation logic:** thao tác ghi/xóa mà ứng dụng yêu cầu ở một bảng/partition, ví dụ một `INSERT` hoặc `DELETE`.
- **Replica application:** Cassandra phân phối mỗi mutation tới các replica theo keyspace strategy/replication factor; không nên đồng nhất một mutation logic với một lần ghi vật lý trên đĩa.
- **I/O thực tế:** commit log, memtable, SSTable, compaction, retry, tombstone, network và các bước nội bộ khác. Đây là chi phí phải đo, không thể suy chính xác chỉ từ số câu CQL.

### 3.1. Tạo một đơn mới

Với ba bảng ở phần 2:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    current_status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, current_status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

**Ít nhất ba mutation logic** cho một sự kiện tạo đơn nếu chỉ xét ba projection này. Nếu còn có durable event log, bảng audit, bảng theo mã ngoài hoặc index khác, số thao tác và lưu trữ tiếp tục tăng.

### 3.2. Chuyển trạng thái một đơn

Giả sử đơn tạo ngày 21/11 đang `PENDING`, sau đó được chấp nhận chuyển thành `PAID`. Mô hình đơn giản dùng:

1. Cập nhật `orders_by_id` với `current_status = PAID` và revision mới.
2. Cập nhật `orders_by_customer_month` với trạng thái/revision mới.
3. `DELETE` hàng cũ trong `orders_by_status_day` theo `PENDING`.
4. `INSERT` hàng mới trong `orders_by_status_day` theo `PAID`.

```sql
-- 1. Đơn đã được hệ thống nghiệp vụ chấp nhận chuyển trạng thái.
UPDATE orders_by_id
SET current_status = ?, updated_at = ?, revision = ?
WHERE tenant_id = ? AND order_id = ?;

-- 2. Cập nhật regular columns ở bảng khách/tháng.
UPDATE orders_by_customer_month
SET current_status = ?, revision = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;

-- 3. Xóa hàng ở partition trạng thái cũ.
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;

-- 4. Thêm hàng vào partition trạng thái mới.
INSERT INTO orders_by_status_day (
    tenant_id, current_status, created_day, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

**Bốn mutation logic** là phép đếm của **kịch bản minh họa này**, chưa bao gồm bản ghi sự kiện, xác nhận idempotency, retry, thao tác điều kiện hoặc bảng bổ sung.

Câu `UPDATE orders_by_id` phía trên **không tự kiểm soát cạnh tranh phiên bản**. Nó chỉ minh họa một mutation sau khi hệ thống đã xác nhận revision mới hợp lệ; nếu nhiều writer có thể xử lý đồng thời, phải có cơ chế CAS/LWT hoặc nguồn xử lý tuần tự phù hợp (trình bày ở phần sau).

### 3.3. Mô hình ước tính đơn giản

Đặt:

```text
C = số đơn mới mỗi giây
U = số sự kiện đổi trạng thái mỗi giây
Pcreate = số mutation logic khi tạo đơn
Pupdate = số mutation logic khi đổi trạng thái

logical_mutations_per_second ≈ C × Pcreate + U × Pupdate
```

Giả sử **800 đơn mới/giây** và **200 lượt đổi trạng thái/giây**:

```text
Pcreate = 3
Pupdate = 4
logical mutations/s = 800 × 3 + 200 × 4
                    = 2.400 + 800
                    = 3.200
```

Với keyspace có replication factor `RF = 3` và giả định mọi mutation được áp dụng tới ba replica, có thể ước lượng cấp cao **3.200 × 3 = 9.600 lượt áp dụng mutation ở replica mỗi giây**. Đây là phép nhân **minh họa tải đích**, **không phải** số I/O, gói tin hoặc ghi đĩa thực tế: replica placement, consistency, retry, batchlog, topology và compaction làm chi phí khác đi.

Nếu `Pcreate` từ 3 tăng lên 6 vì có thêm ba projection, phần tăng tối thiểu là `800 × 3 = 2.400 mutation logic/giây` ở tải tạo đơn nói trên, trước cả khi tính cập nhật. Bởi vậy, mỗi projection mới cần có **lý do đường đọc** và kết quả đo.

### 3.4. Ước lượng dung lượng và write amplification

Giả sử ba biểu diễn của một đơn có kích thước dữ liệu thô trung bình:

| Biểu diễn | Dữ liệu thô/đơn (giả định) | Vai trò |
| --- | ---: | --- |
| `orders_by_id` | 500 B | Chi tiết/tóm tắt |
| `orders_by_customer_month` | 180 B | Danh sách khách |
| `orders_by_status_day` | 160 B | Hàng đợi trạng thái |
| **Tổng** | **840 B** | Chưa tính replication/overhead |

So với chỉ 500 B ở một bảng, dữ liệu thô của ba biểu diễn tăng khoảng `840 / 500 = 1,68` lần. **Đây không phải hệ số dung lượng đĩa thật**: kích thước primary key, metadata, compression, tombstone, memtable/SSTable, chỉ mục partition và replication đều phải được đo.

Với hàng đổi trạng thái, `DELETE` thường tạo tombstone và `INSERT` tạo hàng mới; cập nhật `status` thường xuyên có thể làm **số byte ghi thực và dữ liệu lưu tạm thời** tăng mạnh hơn dự báo chỉ dựa trên kích thước hàng đang sống.

## 4. Đọc được lợi gì khi chấp nhận nhiều bảng?

Không nên chỉ đếm mutation mà quên **read amplification** của phương án không có projection.

| Tiêu chí | Chỉ một bảng theo khách/tháng | Thêm bảng theo trạng thái/ngày |
| --- | --- | --- |
| Q02: khách/tháng | Trực tiếp một partition | Vẫn trực tiếp ở bảng khách/tháng |
| Q03: toàn tenant, status/ngày | Không biết khách hàng nào có dữ liệu; nguy cơ thăm dò nhiều partition | Biết partition key `(tenant,status,day)` |
| Lọc `PENDING` | Có thể phải lọc dữ liệu ở ứng dụng | `PENDING` là thành phần khóa phân vùng |
| Sắp xếp danh sách | Ghép/sắp xếp nhiều luồng | Clustering theo `created_at DESC` trong partition |
| Tải ghi | Ít mutation hơn | Thêm mutation và tombstone khi chuyển trạng thái |
| Nguy cơ khác | Độ trễ fan-out cao, khó dự đoán | Partition trạng thái có thể quá nóng |

Ví dụ tenant có **50.000 khách hàng**. Nếu truy vấn hàng đợi cần thăm dò một phần lớn số khách, áp lực đọc sẽ khác rất nhiều so với một truy vấn trực tiếp vào partition trạng thái. Tuy nhiên, nếu status/day chứa hàng triệu hàng hoặc được ghi/xóa cực nhanh, projection vẫn có thể trở thành điểm nóng.

Khi một partition theo `(tenant_id, current_status, created_day)` quá nóng, có thể thêm `shard_id` vào partition key theo quy tắc hash ổn định của `order_id`. Đọc hàng đợi sẽ thành fan-out tới **N shard đã biết**, rồi hợp nhất kết quả. Đây là đổi từ **fan-out không có phạm vi nhỏ xác định** sang **fan-out hữu hạn**, nhưng tăng độ phức tạp phân trang và cần quản lý version của quy tắc shard.

Quyết định tạo thêm projection hoặc shard phải dựa trên **QPS, p95/p99, dữ liệu lệch tải, bytes/partition, số lần chuyển trạng thái, tombstone, chi phí lưu trữ và mức nhất quán mong muốn**, không chỉ vì câu CQL chạy được.

## 5. Ba lớp nhất quán không được nhầm lẫn

### 5.1. Nhất quán giữa replica của cùng một partition

Cassandra phân phối dữ liệu của partition tới các replica theo cấu hình keyspace. Consistency level của thao tác (ví dụ `ONE`, `LOCAL_QUORUM` trong topology phù hợp) xác định mức xác nhận từ replica khi đọc/ghi.

Chọn consistency level đúng có thể hỗ trợ một số yêu cầu đọc sau ghi trên **cùng dữ liệu** với replication factor thích hợp. Nhưng nó không làm một mutation **chưa từng được gửi** tới bảng projection xuất hiện ở bảng đó.

### 5.2. Nhất quán nghiệp vụ giữa các bảng projection

Nếu `orders_by_id` đã là `PAID` nhưng consumer chưa cập nhật `orders_by_status_day`, một truy vấn vào bảng status có thể vẫn thấy hàng `PENDING` hoặc chưa thấy hàng `PAID`. Đây là **projection lag hoặc lỗi bỏ sót mutation**, không phải vấn đề chọn `LOCAL_QUORUM` ở truy vấn status.

Một yêu cầu sản phẩm phải nói rõ:

- Cần **read-your-writes** từ bảng nào và ngay sau lệnh nào?
- Cho phép các danh sách phụ chậm hơn nguồn bao lâu?
- Có chấp nhận đơn xuất hiện tạm thời ở cả hai hàng đợi hay không?
- API phải xử lý thế nào khi nguồn đã cập nhật nhưng projection chưa hội tụ?

Không được tuyên bố “eventual consistency” là giải pháp hoàn chỉnh nếu không có **phát sự kiện bền vững, retry và đối soát**: nếu mutation mất vĩnh viễn, hệ thống không tự hội tụ chỉ nhờ chờ đợi.

### 5.3. Nhất quán khi đọc nhiều partition hoặc nhiều bảng

Ngay cả khi từng truy vấn dùng consistency level mạnh hơn, hai `SELECT` tại hai thời điểm trên hai partition không mặc nhiên là **một snapshot giao dịch chung**. Dữ liệu có thể thay đổi giữa hai lần đọc. Pagination nhiều bucket cũng không tự đảm bảo một snapshot bất biến nếu có ghi/xóa song song.

Vì vậy nên phân biệt các mục tiêu:

| Mục tiêu | Cách tiếp cận cần cân nhắc |
| --- | --- |
| Đọc trạng thái chuẩn của một order | Đọc `orders_by_id` theo hợp đồng consistency |
| Danh sách có thể chậm vài giây | Projection bất đồng bộ + SLO độ trễ và giám sát |
| Tránh nhận hai lần một transition | Idempotency key/sequence và kiểm soát thay đổi ở nguồn |
| Kiểm toán sự kiện không được mất | Durable event log và quy trình khôi phục được kiểm thử |
| Trạng thái ở nhiều bảng phải khớp khi đã hội tụ | Invariant, reconciliation và khả năng replay/rebuild |

## 6. Logged batch, LWT và timestamp giải quyết đến đâu?

### 6.1. CQL BATCH không phải SQL transaction xuyên bảng

`BEGIN BATCH ... APPLY BATCH` có thể nhóm nhiều mutation. **Logged batch** hỗ trợ tính nguyên tử theo nghĩa các mutation đã được chấp nhận có thể được phục hồi để cuối cùng cùng được áp dụng trong trường hợp lỗi, nhưng **không cung cấp cách ly giao dịch xuyên partition như SQL**: độc giả có thể quan sát dữ liệu đã cập nhật ở một số nơi trong khi nơi khác chưa.

Không dùng batch nhiều partition như mẹo mặc định để tăng throughput. Khi số partition lớn, batchlog và coordinator có thể chịu tải cao. Batch cũng **không** kiểm tra “revision 11 có được ghi đè revision 12 hay không”.

### 6.2. LWT/CAS kiểm soát điều kiện trên trạng thái nguồn

Khi nghiệp vụ cần bảo đảm mỗi đơn chỉ chuyển trạng thái từ một revision đã biết, có thể thiết kế **lightweight transaction** trên hàng `orders_by_id`:

```sql
-- Giả định hàng nguồn đã tồn tại và expectedRevision được caller biết.
UPDATE orders_by_id
SET current_status = ?,
    updated_at = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

Ứng dụng phải kiểm tra kết quả `[applied]`, xử lý tranh chấp và xác minh `nextRevision` là phiên bản nghiệp vụ hợp lệ. Cassandra không tự suy từ việc gán `revision = 13` rằng số này là bước tiếp theo sau 12. LWT thêm round-trip/chi phí điều phối, nên chỉ chọn nếu hợp đồng nhất quán cần.

**LWT ở một hàng nguồn không tự biến các mutation của bảng khách/tháng và bảng trạng thái/ngày thành một transaction có cách ly xuyên partition.** Chỉ những transition **đã được chấp nhận** mới được đưa vào đường đồng bộ projection.

### 6.3. Không xem timestamp ghi là revision nghiệp vụ

Cassandra giải quyết xung đột cell thông thường dựa trên timestamp ghi; một sự kiện nghiệp vụ xảy ra sớm hơn vẫn có thể tới server muộn hơn và vô tình ghi đè dữ liệu mới nếu pipeline cập nhật vô điều kiện.

Không dùng đồng hồ máy client/server làm sequence nghiệp vụ nếu không có thiết kế kiểm soát. `USING TIMESTAMP` cũng không tự cung cấp giao dịch, deduplication hoặc quy tắc chuyển trạng thái; kết hợp với `DELETE`/tombstone cần được đánh giá đặc biệt cẩn thận.

## 7. Ma trận lỗi: vì sao các projection có thể lệch?

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Nguồn cập nhật thành công, bảng khách/tháng thất bại | Chi tiết đơn mới hơn danh sách khách | Retry/replay mutation dựa trên revision đã chấp nhận |
| Nguồn `PAID`, xóa `PENDING` thất bại | Đơn vẫn có trong hàng đợi PENDING | Retry xóa bằng **khóa cũ**, đối soát hàng thừa |
| Đã xóa `PENDING`, ghi `PAID` thất bại | Đơn tạm thời không ở hàng đợi nào | Retry ghi hàng mới, đối soát hàng thiếu |
| Timeout nhưng Cassandra đã áp dụng ghi | Caller không biết thao tác thành công hay thất bại | Dùng ID/revision ổn định, retry an toàn và kiểm tra lại |
| Event được gửi hai lần | Projection có thể xử lý lặp hoặc TTL bị làm mới | Dedupe/sequence, idempotent mutation và định nghĩa retention |
| Revision 12 đến trước revision 11 | Trạng thái có nguy cơ bị ghi lùi | Kiểm soát thứ tự theo order, kiểm tra revision ở nguồn |
| Consumer chết sau khi ghi một projection | Một bảng mới, bảng khác cũ | Durable log, checkpoint đúng thời điểm, replay |
| Đổi `customer_id` hoặc `created_at` | Hàng cũ vẫn ở partition/bucket cũ | Biết khóa cũ/mới, xóa/ghi theo quy trình migration |
| Projection có TTL ngắn hơn nguồn | Hàng danh sách biến mất trước chi tiết đơn | Quy định retention riêng hoặc đồng bộ policy |
| Node/replica tạm mất liên lạc | Replica có thể cần repair | Kiểm soát replication/CL và repair, **không nhầm** với sửa logic projection |

Một retry “ghi lại tất cả bảng bất cứ lúc nào” không luôn an toàn. Ví dụ nếu revision 11 thất bại, revision 12 đã hoàn tất, sau đó retry revision 11 có thể **tái tạo hàng PENDING cũ** nếu không chặn thay đổi lỗi thời. Cần kết hợp **thứ tự xử lý, idempotency và đối soát**, không chỉ “at least once”.

## 8. Xác định nguồn sự thật và invariant trước khi đối soát

**Reconciliation** là quy trình so sánh các projection với trạng thái được tin cậy, tìm dữ liệu thiếu/thừa/lỗi thời và sửa chúng theo quy tắc an toàn. Không thể xây đối soát đúng nếu chưa trả lời “cái gì là sự thật?”.

Trong ví dụ này, chọn:

- `orders_by_id` chứa trạng thái cuối cùng đã được **chấp nhận có revision**.
- Một **nguồn sự kiện bền vững** ghi các thay đổi đã chấp nhận, gồm `event_id`, `revision`, `old_status`, `new_status`, tenant/order ID, customer, `created_at` và thời gian xử lý. Nguồn này giúp phục hồi các transition và biết khóa cũ cần xóa. Nguồn có thể là event stream/durable log được thiết kế riêng; bài không giả định chỉ một công nghệ.
- Hai bảng danh sách là **projection** có thể xây dựng lại theo thông tin nguồn đã được xác minh.

### 8.1. Invariant minh họa

Với một order có trạng thái nguồn `PAID`, revision 12, `customer_id = C` và `created_at = T`:

| Mã | Invariant sau khi projection đã hội tụ |
| --- | --- |
| I1 | Hàng `orders_by_id` phản ánh status `PAID` và revision 12 đã được chấp nhận |
| I2 | Hàng có khóa `(tenant,C,month(T),T,orderId)` trong `orders_by_customer_month` tồn tại và có status/revision khớp nguồn |
| I3 | Hàng có khóa `(tenant,PAID,day(T),T,orderId)` trong `orders_by_status_day` tồn tại và có revision khớp nguồn |
| I4 | Các hàng status/day cũ của cùng order ở **những status đã đi qua** không còn tồn tại sau khi hội tụ |
| I5 | Những projection còn trong chính sách retention có thể truy vấn được; các bản đã hết hạn xử lý theo hợp đồng lưu trữ |

I4 không có nghĩa Cassandra có một phép tra cứu rẻ “tìm order ID trong mọi partition status/day”. Để biết các khóa cũ cần kiểm, hệ thống dùng **event log, manifest thay đổi hoặc tập trạng thái đã biết theo nghiệp vụ**. Tránh toàn bảng scan cho mỗi đơn.

### 8.2. Đối soát không được phá dữ liệu mới hơn

Ví dụ job đối soát đọc nguồn ở revision 12, chuẩn bị sửa projection. Trong lúc đó nguồn chuyển thành revision 13. Nếu job chậm và ghi lại dữ liệu revision 12 sau mutation revision 13, chính **job sửa lỗi** có thể làm bảng sai.

Cần có ít nhất một trong các cơ chế kiểm soát:

- Xử lý tuần tự/khóa logic theo `(tenant_id, order_id)` cho cả mutation projection và repair.
- Dựa trên snapshot/version watermark đáng tin cậy, rồi kiểm tra lại trạng thái nguồn trước khi áp dụng khi có tranh chấp.
- Dùng mô hình mutation/so sánh revision đủ mạnh để **bỏ qua sửa lỗi thời**; không suy rằng chỉ lưu trường revision trong row sẽ tự chặn cập nhật cũ.

Không có bước này, reconciliation có thể làm tình trạng nhất quán tệ hơn.

## 9. Quy trình đối soát có thể vận hành

Một quy trình thực tế có thể chia thành **đối soát gần thời gian thực** và **đối soát định kỳ theo lô**.

### 9.1. Phát hiện đối tượng cần kiểm

Không nên khởi đầu bằng `SELECT * FROM orders_by_id` để quét toàn Cassandra trên đường request. Cassandra tối ưu đường đọc theo partition key, không phải cơ chế scan trực tuyến vô hạn.

Có thể tạo **danh sách ID cần đối soát** từ:

1. Các sự kiện đã được chấp nhận trong durable log theo khoảng thời gian.
2. Các mutation lỗi hoặc timeout nằm trong retry/dead-letter queue.
3. Các ID phát hiện sai lệch bởi kiểm tra nghiệp vụ hoặc phản hồi người dùng.
4. Các lô ID được lưu có chủ đích trong manifest/đầu vào của job bảo trì.

Đặt giới hạn batch size, QPS, thời gian chạy và có checkpoint tiến độ; không để job đối soát tranh tài nguyên không kiểm soát với truy vấn sản xuất.

### 9.2. So sánh theo khóa đầy đủ

Với từng `(tenant_id, order_id)`:

1. Đọc hàng nguồn `orders_by_id` và revision hiện tại.
2. Tính `month_bucket` và `created_day` theo **`created_at` UTC** từ nguồn.
3. Đọc hàng customer/month bằng **đầy đủ partition và clustering key**.
4. Đọc hàng status/day tương ứng **trạng thái hiện tại**.
5. Từ event log/manifest, xác định các trạng thái/bucket **cũ đã dùng**, kiểm tra hàng mồ côi cần xóa.
6. So sánh ID, trạng thái, revision và các thuộc tính projection được quy định đồng bộ.

Ví dụ câu CQL kiểm tra một hàng cụ thể trong bảng khách/tháng:

```sql
SELECT current_status, total_amount, revision
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
```

Và một hàng trạng thái:

```sql
SELECT revision, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND current_status = ?
  AND created_day = ?
  AND created_at = ?
  AND order_id = ?;
```

Điều quan trọng là **biết đầy đủ khóa cần kiểm**, không thêm `ALLOW FILTERING` để tìm order ID trong mọi partition.

### 9.3. Phân loại sai lệch

| Loại | Ví dụ | Hành động mong muốn |
| --- | --- | --- |
| `MISSING` | Nguồn `PAID` nhưng thiếu hàng PAID trong status/day | Tạo lại hàng tại khóa đúng |
| `STALE` | Customer/month vẫn `PENDING` revision 11, nguồn `PAID` revision 12 | Cập nhật các cột projection theo revision hợp lệ |
| `ORPHAN` | Hàng PENDING cũ còn tồn tại sau chuyển PAID | Xóa hàng ở khóa cũ đã được xác nhận |
| `MISMATCH` | Total amount ở projection khác nguồn | Xác định nguồn chuẩn và sửa cột được phép |
| `EXPIRED_EXPECTED` | Projection hết TTL theo chính sách | Không tự tạo lại dữ liệu đã hết hạn |
| `IN_FLIGHT` | Mutation mới vừa được nhận, chưa hết SLO lag | Theo dõi, chờ trong cửa sổ trễ cho phép trước khi báo lỗi |

Phân biệt `IN_FLIGHT` với lỗi thật giúp job không liên tục “sửa” những projection đang cập nhật bình thường. Tuy nhiên, việc đợi quá lâu cũng có thể che lỗi; định nghĩa SLO cho lag và phân loại theo độ tuổi sự kiện.

### 9.4. Sửa lỗi có kiểm soát

Thuật toán khái niệm:

```text
for each orderKey in boundedManifest:
    source = readOrdersById(orderKey)
    if source absent:
        apply deletion/retention policy; do not assume every absence is error
        continue

    expectedCustomerKey = keyFrom(source.customerId, source.createdAt)
    expectedStatusKey = keyFrom(source.status, source.createdAt)
    oldStatusKeys = lookupKnownHistoricalKeysFromDurableEvents(orderKey)

    observed = readExpectedProjectionRowsAndKnownOldKeys(...)
    discrepancies = compare(source.revision, source.fields, observed)

    if discrepancies:
        verify source is still current / acquire per-order sequencing
        repair missing/stale expected rows
        remove known orphan rows using exact old primary keys
        verify or enqueue a new bounded verification pass

    record outcome and advance checkpoint only after safe handling
```

Nếu lỗi xảy ra giữa chừng, job phải có thể tiếp tục mà không tạo dữ liệu sai. Không xóa hàng cũ khi chưa xác minh trạng thái nguồn hoặc chưa biết khóa cũ có còn hợp lệ. Không ép mọi projection thành cùng TTL nếu chúng có vòng đời được thiết kế khác nhau.

### 9.5. Metric đối soát và cảnh báo

Theo dõi ít nhất:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `projection_lag_seconds` theo bảng | Tuổi của thay đổi nguồn chưa phản ánh ở projection |
| Số mutation retry/dead-letter | Dấu hiệu lỗi đẩy dữ liệu hoặc lỗi không thể tự phục hồi |
| `missing/stale/orphan/mismatch` theo thời gian | Phân loại lỗi để tìm nguyên nhân |
| Số đối tượng đã kiểm và checkpoint | Job có đang tiến bộ và bao phủ đủ dữ liệu không? |
| Tỷ lệ sửa thành công và số lần thử lại | Đo hiệu quả và tác động của reconcile |
| p95/p99 read/write latency | Theo dõi cái giá của denormalization |
| Partition lớn nhất, tombstone scanned | Phát hiện bảng trạng thái hoặc bảng lịch sử xuống cấp |
| Backlog tuổi lớn nhất | Phát hiện những sự kiện chưa hội tụ vượt giới hạn cam kết |

Ngưỡng cảnh báo phải được chốt theo SLA sản phẩm và đo thật; không có một ngưỡng lag/partition size phổ quát cho mọi cụm Cassandra.

## 10. Java: gọi đúng projection và xử lý cập nhật

Ví dụ dùng **DataStax Java Driver 4.x** cho một consumer nhận **transition đã được chấp nhận**. Giả định hệ thống upstream đã đảm bảo xử lý theo thứ tự revision cho từng order và đã có durable event để retry/reconcile; nếu thiếu các bảo đảm đó, đoạn mã **không an toàn** trước sự kiện đến sai thứ tự.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.UUID;

public final class OrderProjectionWriter {
    private final CqlSession session;
    private final PreparedStatement updateCustomer;
    private final PreparedStatement deleteOldStatus;
    private final PreparedStatement insertNewStatus;

    public OrderProjectionWriter(CqlSession session) {
        this.session = session;
        this.updateCustomer = session.prepare(
            "UPDATE orders_by_customer_month " +
            "SET current_status = ?, revision = ? " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "AND created_at = ? AND order_id = ?"
        );
        this.deleteOldStatus = session.prepare(
            "DELETE FROM orders_by_status_day " +
            "WHERE tenant_id = ? AND current_status = ? AND created_day = ? " +
            "AND created_at = ? AND order_id = ?"
        );
        this.insertNewStatus = session.prepare(
            "INSERT INTO orders_by_status_day (" +
            "tenant_id, current_status, created_day, created_at, " +
            "order_id, customer_id, total_amount, revision) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );
    }

    // Chỉ gọi với transition nguồn đã chấp nhận và được xử lý đúng thứ tự.
    // Nếu một lệnh lỗi, durable event cần được giữ để retry/reconcile.
    public void projectStatusChange(
        String tenantId, UUID orderId, UUID customerId,
        Instant createdAt, String oldStatus, String newStatus,
        BigDecimal totalAmount, long revision
    ) {
        String month = YearMonth.from(
            createdAt.atZone(ZoneOffset.UTC)
        ).toString();
        LocalDate day = createdAt.atZone(ZoneOffset.UTC).toLocalDate();

        session.execute(updateCustomer.bind(
            newStatus, revision, tenantId, customerId, month,
            createdAt, orderId
        ));
        session.execute(deleteOldStatus.bind(
            tenantId, oldStatus, day, createdAt, orderId
        ));
        session.execute(insertNewStatus.bind(
            tenantId, newStatus, day, createdAt, orderId,
            customerId, totalAmount, revision
        ));
    }
}
```

Mã chỉ trình bày **các mutation projection**; thao tác chấp nhận trạng thái mới ở `orders_by_id` và durable log đã xảy ra ở tầng khác. Các câu `session.execute` không tạo transaction xuyên bảng: nếu câu thứ hai thành công nhưng câu thứ ba lỗi, trạng thái projection bị thiếu tạm thời.

Để vận hành, cần thêm:

1. **Checkpoint sau khi hoàn tất an toàn:** không đánh dấu event đã xử lý vĩnh viễn nếu một projection còn thiếu.
2. **Thứ tự theo order ID:** không để retry revision 11 áp lại sau revision 12; nếu không đảm bảo thứ tự, cần cơ chế kiểm tra revision/source và sửa phù hợp.
3. **Timeout không rõ kết quả:** có thể Cassandra đã nhận ghi nhưng client mất ACK; retry phải an toàn và không tạo row khác khóa.
4. **Consistency level:** chọn theo topology và SLA; không giả định CL của một mutation bảo đảm các bảng đồng bộ.
5. **Kiểm tra tenant:** partition key có tenant không tự cấp quyền truy cập, API vẫn phải phân quyền.
6. **Giám sát:** có metric cho mỗi bước mutation và đưa event lỗi sang hàng đợi có thể xử lý lại.

`CqlSession` nên được tạo/quản lý theo vòng đời ứng dụng, không tạo lại trên từng lần cập nhật. Kiểu `Instant` ánh xạ CQL `timestamp`, `LocalDate` ánh xạ `date`, `UUID` ánh xạ `uuid` và `BigDecimal` ánh xạ `decimal`. Bucket phải dùng UTC thống nhất giữa đường ghi, đường đọc và đối soát.

### 10.1. Vì sao không chỉ thêm `BATCH` vào mã Java?

Một logged batch có thể hỗ trợ việc áp dụng tất cả mutation sau sự cố theo ngữ nghĩa batch, nhưng không giải quyết **sai thứ tự revision**, không cung cấp snapshot xuyên partition và không thay thế event log/reconciliation. Nếu cập nhật thường xuyên tới nhiều partition, batch còn có thể làm tăng áp lực coordinator/batchlog; cần so sánh bằng phép đo.

Khi một projection được xây bằng consumer bất đồng bộ, luồng đúng thường là: **transition được chấp nhận → sự kiện bền vững → cập nhật projection → kiểm tra/ghi nhận tiến độ → retry/đối soát khi cần**, chứ không phải “ghi bất kỳ ba bảng nào rồi hy vọng chúng sẽ luôn bằng nhau”.

## 11. Tombstone, TTL, compaction và repair

### 11.1. Chi phí ẩn khi trạng thái là một phần của khóa

Mỗi lần `PENDING → PAID` sinh ít nhất một tombstone cho hàng trạng thái cũ, trước khi dữ liệu cũ được dọn trong quá trình compaction khi đủ điều kiện. Hàng đợi có nhiều chuyển trạng thái có thể đọc nhiều tombstone ngay cả khi `LIMIT 50` chỉ trả 50 hàng đang sống.

Theo dõi tombstone scanned, SSTables-per-read, write latency và độ nóng của partition; đừng cho rằng bảng trạng thái luôn rẻ chỉ vì query nhắm vào một partition.

### 11.2. TTL khác nhau giữa các projection

Bảng ID có thể cần giữ trạng thái trong suốt vòng đời đơn, trong khi bảng danh sách có chính sách lưu trữ ngắn hơn. Nếu projection hết TTL trước khi đối soát, job không nên tự tạo lại mọi hàng cũ mà không kiểm tra **retention policy**. Ngược lại, nếu xóa nguồn nhưng bảng phụ không được dọn, thông tin có thể còn xuất hiện ở danh sách theo trạng thái.

TTL áp dụng cho các giá trị được ghi, có thể tạo tombstone; việc replay/update có thể tác động thời hạn sống của ô. Chốt thời hạn lưu, hành vi xóa và xử lý GDPR/quy định tương ứng ở lớp nghiệp vụ nếu hệ thống có yêu cầu.

### 11.3. Compaction và repair không chữa lỗi logic projection

Compaction quản lý tổ chức SSTable và dọn dữ liệu cũ/tombstone khi đủ điều kiện, không tạo một hàng `PAID` chưa từng được ứng dụng ghi. Repair đồng bộ các replica theo cơ chế Cassandra, không biết một đơn còn nằm sai hàng đợi `PENDING` do consumer quên `DELETE`.

Đừng giảm `gc_grace_seconds` tùy ý để dọn tombstone nhanh hơn; an toàn xóa phụ thuộc tình trạng replica, lịch repair và chính sách vận hành. Với bảng projection có TTL và xóa nhiều, cần giám sát cả **tải tombstone** lẫn **tính đúng khi dữ liệu hết hạn**.

## 12. Kiểm thử lỗi và checklist quyết định

### 12.1. Bộ tình huống kiểm thử tối thiểu

| Tình huống | Bất biến cần quan sát sau khi hội tụ |
| --- | --- |
| Tạo đơn bình thường | Có hàng nguồn, hàng customer/month, hàng status/day |
| Đổi `PENDING → PAID` | Hàng nguồn/customer cùng revision; có PAID, không còn PENDING |
| Câu lệnh xóa trạng thái cũ bị timeout | Có retry/đối soát hàng cũ, không để orphan kéo dài |
| Câu lệnh ghi trạng thái mới thất bại | Có bổ sung hàng thiếu sau retry |
| Đổi trạng thái liên tiếp revision 11/12/13 | Kết quả cuối đúng phiên bản mới, không bị replay cũ ghi lùi |
| Consumer restart giữa các mutation | Không mất sự kiện, có checkpoint đúng và phục hồi |
| Một tenant có phân vùng PENDING cực lớn | Thỏa p95/p99 mục tiêu hoặc xác định cần shard |
| Projection hết TTL trước nguồn | Kết quả tuân retention, đối soát không tái tạo trái chính sách |
| Node/replica tạm mất | Dữ liệu được xử lý theo CL/repair, không nhầm với lỗi sync nghiệp vụ |
| Job đối soát chạy đồng thời với chuyển trạng thái | Job không ghi dữ liệu lỗi thời sau transition mới |

### 12.2. Checklist thiết kế

| Câu hỏi | Tiêu chí chấp nhận |
| --- | --- |
| Projection phục vụ query shape nào? | Có ID truy vấn, input, partition key, sort và SLA |
| Đã đếm mutation chưa? | Có đường tạo/sửa/xóa, bao gồm delete+insert khi đổi key |
| Đã dự báo chi phí chưa? | QPS read/write, bytes, RF/topology, tombstone, peak partition |
| Nguồn sự thật là gì? | Một nơi/quy trình quyết định revision và trạng thái đã chấp nhận |
| Có event log bền vững không? | Có thể replay sau lỗi mà không mất transition |
| Mutation retry có an toàn không? | ID ổn định, kiểm soát thứ tự và idempotency được kiểm thử |
| Có xác định độ trễ đồng bộ cho phép không? | SLO projection lag và hành vi đọc khi stale rõ ràng |
| Có đầu vào để đối soát không? | Durable log, manifest hoặc danh sách key có thể duyệt với giới hạn |
| Có invariant và sửa lỗi an toàn không? | Phát hiện missing/stale/orphan; chặn repair revision cũ |
| Đã phân biệt replica repair với reconciliation chưa? | Có quy trình riêng cho lỗi node và lỗi nghiệp vụ |
| Đã đo trên dữ liệu lớn nhất chưa? | Có p95/p99, hàng/byte partition lớn, tombstone và write throughput |

## 13. Bài tập áp dụng

Một hệ thống Java quản lý ticket hỗ trợ và muốn trả ba API:

```text
R1. Tra cứu ticket theo (tenant_id, ticket_id).
R2. Liệt kê 20 ticket gần nhất của requester trong tháng.
R3. Liệt kê ticket OPEN được tạo trong ngày của tenant, mới nhất trước.
```

Mỗi ticket có `ticket_id`, `requester_id`, `created_at`, `status`, `priority` và `revision`. Nguồn trạng thái là bảng theo ID; hai bảng còn lại là projection.

**Yêu cầu:**

1. Đề xuất partition key và clustering key cho ba bảng; giải thích tại sao R3 không nên đọc xuyên mọi requester/month.
2. Tính số mutation logic tối thiểu nếu một ticket mới cần ghi cả ba bảng, và một lần `OPEN → RESOLVED` cần cập nhật hai bảng, xóa hàng OPEN và ghi hàng RESOLVED.
3. Giả sử tải là **300 ticket mới/giây** và **100 lần chuyển trạng thái/giây**. Tính mutation logic mỗi giây với `Pcreate = 3`, `Pupdate = 4`, chưa tính event log và retry.
4. Nếu `RF = 3`, tính ước lượng lượt áp dụng mutation tới replica theo phép nhân đơn giản; giải thích vì sao nó chưa phải số I/O đĩa thực.
5. Nêu ba sai lệch có thể xảy ra nếu lỗi sau thao tác xóa OPEN nhưng trước thao tác thêm RESOLVED; đề xuất cách phát hiện/sửa.
6. Một job đối soát đang đọc revision 8 thì nguồn chuyển sang revision 9. Job cần điều kiện gì trước khi sửa projection để không tái tạo dữ liệu phiên bản 8?
7. Giải thích vì sao `LOCAL_QUORUM` hoặc logged batch không thay thế việc quản lý thứ tự sự kiện và đối soát nghiệp vụ.

**Gợi ý đối chiếu:** R1 theo `(tenant_id, ticket_id)`; R2 theo `(tenant_id, requester_id, month_bucket)` với clustering `created_at DESC, ticket_id DESC`; R3 theo `(tenant_id, status, created_day)` với clustering tương tự. Phép tính ở câu 3: `300 × 3 + 100 × 4 = 1.300 mutation logic/giây`; với `RF = 3`, ước lượng cấp cao là `3.900 replica-level applications/giây`. Cần đếm thêm nếu có bảng log/dedupe hoặc retry. Sau xóa OPEN nhưng chưa thêm RESOLVED, nguồn và bảng requester có thể đã đổi trong khi danh sách status thiếu hàng; đối soát theo revision và khóa đầy đủ cần khôi phục RESOLVED, không tái tạo OPEN lỗi thời. Job reconciliation phải kiểm tra revision mới hoặc xử lý trong cơ chế tuần tự theo ticket trước khi ghi.

## Kết luận

Thêm bảng projection trong Cassandra là một quyết định **đổi chi phí ghi lấy đường đọc hiệu quả**. Đánh giá không chỉ dừng ở số câu `INSERT` hay số byte lưu lặp: cần tính cả chuyển khóa, tombstone, retry, replication, độ trễ đồng bộ và chi phí duy trì đúng trạng thái. Consistency level, LWT, batch, compaction và repair giải quyết những vấn đề khác nhau; chúng không tự biến các projection thành một giao dịch xuyên bảng. Muốn denormalization đáng tin cậy, hãy xác định **nguồn sự thật, revision, event bền vững, invariant, cơ chế đối soát và phép đo tải** trước khi cam kết SLA cho các đường đọc.
