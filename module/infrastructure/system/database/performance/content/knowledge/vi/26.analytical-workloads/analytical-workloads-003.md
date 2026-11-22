# Nén dữ liệu, xử lý theo lô và thực thi vector hóa

## Mục tiêu bài học

Tải phân tích thường đọc một lượng dữ liệu lớn, quét nhiều cột, lọc và tổng hợp hàng triệu dòng. Nếu mỗi byte đều phải đọc từ storage, mỗi dòng đều phải giải mã riêng và mỗi thao tác đều đi qua nhiều lớp xử lý nhỏ, chi phí I/O và CPU có thể trở thành nút thắt. Nén dữ liệu giảm số byte phải lưu và truyền; xử lý theo lô giảm chi phí cố định của từng lần gọi hoặc từng transaction; thực thi vector hóa xử lý nhiều giá trị trong một lần thay vì lặp từng dòng.

Trong chương **Tải phân tích** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách ba kỹ thuật phối hợp để cải thiện hiệu năng truy vấn và nạp dữ liệu. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, không thể chọn codec, kích thước batch hoặc chế độ thực thi chỉ dựa trên tỷ lệ nén hay benchmark đơn lẻ; cần đo cả CPU, memory, I/O, độ trễ, throughput và chi phí ghi.

Sau bài học, bạn có thể:

- Giải thích cách nén theo cột và các kiểu encoding thường dùng trong hệ phân tích.
- Đánh giá đánh đổi giữa dung lượng, tốc độ đọc, tốc độ ghi và chi phí giải nén.
- Chọn batch size phù hợp cho ingestion, cập nhật và truy vấn theo lô.
- Phân biệt batching ở tầng ứng dụng với vectorized execution bên trong query engine.
- Giải thích vectorized operator, selection vector, SIMD và late materialization.
- Nhận diện trường hợp nén hoặc vector hóa không đem lại lợi ích.
- Thiết kế benchmark có đối chứng và kiểm tra kết quả bằng kế hoạch thực thi cùng số liệu tài nguyên.

## 1. Đặc điểm của tải phân tích

Tải phân tích (analytical workload) thường khác tải giao dịch ngắn (OLTP):

| Đặc điểm | Tải giao dịch | Tải phân tích |
|---|---|---|
| Truy cập | Một vài dòng theo khóa | Nhiều dòng, thường quét một phần lớn bảng |
| Phép xử lý | Đọc/ghi nhỏ, kiểm tra trạng thái | Filter, join, group, aggregate, sort |
| Kết quả | Ít dòng | Có thể là tập kết quả lớn hoặc một số ít giá trị tổng hợp |
| Mục tiêu | Độ trễ từng giao dịch, tính nhất quán | Throughput scan, thời gian truy vấn, chi phí trên mỗi GB |
| Tài nguyên nổi bật | Lock, round trip, index lookup | I/O tuần tự, CPU, memory bandwidth, cache và temp storage |

Một báo cáo doanh thu theo tháng có thể đọc hàng chục triệu dòng đơn hàng, lọc theo ngày và trạng thái, nối với dòng hàng rồi tổng hợp theo khu vực. Trong trường hợp này, giảm số byte đọc, xử lý nhiều giá trị cùng lúc và tránh round trip lặp lại có thể đem lại lợi ích lớn.

Ba kỹ thuật trong bài học tác động ở các tầng khác nhau:

- **Nén dữ liệu:** thay đổi cách biểu diễn và lưu trữ dữ liệu để giảm số byte.
- **Xử lý theo lô (batching):** gom nhiều bản ghi hoặc công việc thành một đơn vị xử lý để giảm chi phí cố định.
- **Thực thi vector hóa (vectorized execution):** query engine áp dụng một toán tử lên một nhóm giá trị cùng lúc, thường theo vector hoặc batch cột.

Chúng bổ trợ nhau nhưng không đồng nghĩa. Một ứng dụng có thể gửi một batch lớn tới database nhưng engine vẫn xử lý từng tuple. Một engine có thể vector hóa scan và aggregate dù dữ liệu không được nạp từ ứng dụng theo batch.

## 2. Nén dữ liệu trong hệ phân tích

Nén dữ liệu biểu diễn cùng một thông tin bằng ít byte hơn. Khi truy vấn bị giới hạn bởi storage bandwidth, đọc ít byte hơn có thể giảm thời gian scan. Tuy nhiên, dữ liệu phải được giải mã trước hoặc trong quá trình xử lý, nên nén cũng tiêu thụ CPU và có thể làm tăng chi phí ghi.

### 2.1. Row store và column store

Trong row store, các thuộc tính của một dòng thường được lưu gần nhau. Cấu trúc này phù hợp với việc đọc hoặc cập nhật một dòng theo khóa.

```text
Row store:
  [id, date, region, status, amount]
  [id, date, region, status, amount]
  [id, date, region, status, amount]
```

Trong column store, giá trị của cùng một cột được lưu thành vùng liên tục hoặc các segment riêng:

```text
Column store:
  id:      [ ... ][ ... ][ ... ]
  date:    [ ... ][ ... ][ ... ]
  region:  [ ... ][ ... ][ ... ]
  status:  [ ... ][ ... ][ ... ]
  amount:  [ ... ][ ... ][ ... ]
```

Nếu truy vấn chỉ cần `date`, `region` và `amount`, column store có thể chỉ đọc các cột đó thay vì tải toàn bộ thuộc tính của mỗi dòng. Các giá trị cùng cột thường có kiểu và phân bố tương tự, giúp áp dụng encoding hiệu quả hơn.

Columnar layout đặc biệt hữu ích cho scan, filter và aggregate trên tập dữ liệu lớn. Row store thường phù hợp hơn với cập nhật một vài dòng, transaction ngắn và truy vấn cần hầu hết cột của một bản ghi. Nhiều hệ thống kết hợp hai kiểu lưu trữ hoặc dùng row store cho dữ liệu mới rồi chuyển sang columnar storage khi dữ liệu ổn định.

### 2.2. Tỷ lệ nén và chi phí giải nén

Tỷ lệ nén có thể biểu diễn theo hai cách phổ biến:

\[
CompressionRatio = \frac{OriginalSize}{CompressedSize}
\]

\[
SpaceSaving = 1 - \frac{CompressedSize}{OriginalSize}
\]

Ví dụ, 100 GB dữ liệu được nén còn 25 GB có compression ratio 4:1 và tiết kiệm 75% dung lượng. Đây chỉ là tỷ lệ dung lượng; nó chưa nói truy vấn nhanh hơn bao nhiêu.

Để đánh giá hiệu năng, cần xem:

- Byte đọc từ storage trước và sau nén.
- Throughput giải nén và mức sử dụng CPU.
- Số dòng được giải mã để trả một kết quả.
- Khả năng giải nén theo từng block hoặc từng cột mà không cần giải nén toàn bộ dataset.
- Chi phí nén khi ingest và chi phí cập nhật dữ liệu đã nén.
- Dung lượng cache sau nén và mức tái sử dụng cache.

Nếu workload bị giới hạn bởi I/O, nén thường có lợi vì giảm byte đọc. Nếu workload đã bị giới hạn bởi CPU và codec giải nén tốn nhiều chu kỳ, mức nén cao có thể làm truy vấn chậm hơn. Cần đo trên storage và CPU thực tế.

## 3. Các kiểu encoding và compression thường gặp

Trong hệ columnar, dữ liệu thường được biến đổi bằng encoding phù hợp với kiểu và phân bố giá trị trước khi áp dụng một thuật toán nén tổng quát. Encoding khai thác cấu trúc dữ liệu; compression codec tiếp tục giảm byte trên biểu diễn đó.

### 3.1. Dictionary encoding

Dictionary encoding thay các giá trị lặp lại bằng mã số nhỏ. Ví dụ cột `status` chỉ có một số giá trị:

```text
Giá trị gốc:  PAID, NEW, PAID, CANCELLED, NEW, PAID

Dictionary:
  0 = PAID
  1 = NEW
  2 = CANCELLED

Encoded:      0, 1, 0, 2, 1, 0
```

Kỹ thuật này phù hợp với cột có cardinality thấp như trạng thái, loại sự kiện, mã khu vực hoặc nhóm sản phẩm. Nó cũng có thể giúp filter bằng cách so sánh mã dictionary thay vì chuỗi dài.

Nếu mỗi giá trị gần như duy nhất, dictionary có thể lớn và ít tiết kiệm. Với dữ liệu thay đổi liên tục, dictionary cần được cập nhật hoặc chia theo block để tránh chi phí quản lý lớn.

### 3.2. Run-Length Encoding (RLE)

RLE lưu một giá trị cùng số lần lặp liên tiếp thay vì ghi lại giá trị ở mọi vị trí:

```text
Giá trị:  A, A, A, A, B, B, C, C, C
RLE:      (A, 4), (B, 2), (C, 3)
```

RLE hiệu quả khi dữ liệu có nhiều đoạn giá trị lặp liên tiếp. Sắp xếp dữ liệu theo cột phù hợp có thể tăng cơ hội tạo run dài, nhưng việc sắp xếp lại dữ liệu có chi phí ghi và có thể làm truy vấn khác kém thuận lợi.

### 3.3. Delta encoding

Delta encoding lưu chênh lệch giữa các giá trị liên tiếp. Ví dụ timestamp hoặc số thứ tự tăng đều:

```text
Giá trị:  1000, 1005, 1010, 1015, 1020
Delta:    1000, 5, 5, 5, 5
```

Các delta nhỏ hơn giá trị tuyệt đối, có thể được mã hóa bằng ít bit hơn. Kỹ thuật này phù hợp với timestamp, sequence hoặc số đo có xu hướng gần nhau khi dữ liệu được sắp theo một thứ tự thích hợp.

### 3.4. Bit packing và frame of reference

Nếu các số nguyên trong một block nằm trong một khoảng nhỏ, hệ thống có thể dùng số bit vừa đủ để lưu mỗi giá trị. Ví dụ các mã vùng nằm trong khoảng 0–15 chỉ cần 4 bit mỗi giá trị thay vì 32 bit.

Frame of reference lưu một giá trị cơ sở rồi mã hóa phần chênh lệch so với cơ sở. Nó hữu ích khi các số trong block tập trung quanh một vùng hẹp.

Các kỹ thuật này thường được kết hợp với delta hoặc dictionary encoding. Khi có giá trị ngoại lệ rất lớn, block có thể cần fallback hoặc chia thành các nhóm nhỏ để tránh làm mọi giá trị dùng số bit quá lớn.

### 3.5. Compression codec tổng quát

Sau encoding, engine có thể áp dụng codec như LZ4, Zstandard hoặc các thuật toán khác tùy nền tảng. Các codec có đánh đổi:

| Nhóm codec | Đặc điểm thường gặp | Khi cân nhắc |
|---|---|---|
| Ưu tiên tốc độ | Nén/giải nén nhanh, tỷ lệ nén vừa phải | Workload cần giải nén thường xuyên, CPU hạn chế |
| Cân bằng | Tỷ lệ nén và tốc độ ở mức trung gian | Workload hỗn hợp, lưu trữ lâu dài |
| Ưu tiên tỷ lệ nén | Dung lượng nhỏ hơn nhưng CPU nén/giải nén có thể cao hơn | Dữ liệu ít thay đổi, lưu trữ dài hạn hoặc storage đắt |

Không có codec tốt nhất cho mọi cột. Cột số có thể phù hợp với delta/bit packing; cột chuỗi ít giá trị có thể phù hợp với dictionary; payload văn bản hoặc JSON có thể hưởng lợi từ codec tổng quát. Hãy thử trên dữ liệu thật, gồm cả phân bố và mức entropy.

### 3.6. Nén theo block và khả năng đọc chọn lọc

Columnar engine thường chia dữ liệu thành block, stripe hoặc row group. Mỗi block có metadata như min/max, số dòng, dictionary hoặc thống kê cột. Khi truy vấn có predicate, engine có thể bỏ qua block không thể chứa giá trị phù hợp (data skipping/zone map) trước khi giải nén.

Ví dụ, nếu truy vấn lọc `event_date` trong một khoảng thời gian, block có min/max ngày nằm hoàn toàn ngoài khoảng đó có thể bị bỏ qua. Hiệu quả phụ thuộc cách dữ liệu được sắp hoặc phân cụm, kích thước block và độ chọn lọc của predicate.

Nén tốt nhưng block quá lớn có thể buộc engine giải nén nhiều dữ liệu không cần thiết. Block quá nhỏ làm tăng metadata, số lần gọi I/O và chi phí điều phối. Kích thước block cần được lựa chọn theo engine và workload.

## 4. Chọn dữ liệu và thứ tự để nén hiệu quả

### 4.1. Cardinality và phân bố giá trị

Cardinality là số lượng giá trị khác nhau trong một cột. Cột có cardinality thấp thường nén tốt bằng dictionary hoặc RLE. Cột có cardinality cao nhưng giá trị gần nhau có thể nén tốt bằng delta hoặc frame of reference. Dữ liệu ngẫu nhiên, mã hóa hoặc có entropy cao thường khó nén.

Đừng dùng cardinality đơn lẻ để chọn codec. Hãy xem phân bố theo từng block, độ lặp liên tiếp, tương quan với cột khác và cách dữ liệu được sắp.

### 4.2. Sắp xếp và clustering

Sắp xếp dữ liệu theo ngày, tenant hoặc một chiều truy vấn phổ biến có thể:

- Tăng khả năng bỏ qua block nhờ min/max.
- Tạo các run dài hơn cho RLE.
- Làm delta giữa các timestamp hoặc khóa gần nhau hơn.
- Giảm số block cần đọc cho truy vấn range.

Nhưng một thứ tự vật lý chỉ tối ưu một số mẫu truy vấn. Nếu workload thường lọc theo nhiều chiều khác nhau, một thứ tự duy nhất có thể không phục vụ tốt tất cả. Recluster hoặc rewrite dữ liệu cũng tốn I/O, CPU và dung lượng tạm.

### 4.3. Nén và kiểu dữ liệu

Chọn kiểu dữ liệu phù hợp trước khi nén:

- Dùng integer có độ rộng phù hợp với miền giá trị.
- Dùng `date`/`timestamp` thay cho chuỗi ngày tháng nếu cần thao tác thời gian.
- Tránh lưu cùng một mã số dưới dạng chuỗi dài nếu không có lý do nghiệp vụ.
- Tách thuộc tính lặp thành dimension/dictionary khi mô hình phân tích phù hợp.
- Không giảm độ chính xác số học chỉ để tiết kiệm byte nếu nghiệp vụ cần độ chính xác đó.

Nén không sửa được mô hình dữ liệu sai hoặc kiểu dữ liệu quá rộng. Tối ưu biểu diễn logic thường giúp cả lưu trữ, so sánh và truyền dữ liệu.

## 5. Xử lý theo lô (batch processing)

Batching gom nhiều thao tác nhỏ thành một đơn vị lớn hơn. Mục tiêu là giảm chi phí cố định như round trip mạng, parse/prepare lặp lại, commit, gọi hàm và điều phối transaction.

Batching có thể áp dụng ở nhiều tầng:

- Ứng dụng gom nhiều bản ghi trước khi gửi tới database.
- Database nhận dữ liệu qua bulk load hoặc `COPY`.
- Một câu SQL xử lý nhiều dòng thay vì gọi một câu cho từng dòng.
- Pipeline phân tích chia dữ liệu thành các micro-batch.
- Query engine xử lý block/vector nội bộ.

Các tầng này có thể cùng tồn tại nhưng phải được đo riêng. Batch ở tầng ứng dụng không tự biến query engine thành vectorized engine.

### 5.1. Vì sao batch nhanh hơn từng dòng?

Giả sử ứng dụng cần nạp 100.000 dòng. Nếu gửi một request/transaction cho mỗi dòng, hệ thống có thể chịu:

- 100.000 round trip hoặc lần gọi driver.
- 100.000 lần parse/execute nếu statement không được tái sử dụng hiệu quả.
- 100.000 commit nếu mỗi dòng nằm trong transaction riêng.
- Chi phí xác thực, log, lock và điều phối lặp lại.

Gom nhiều dòng vào một batch giúp chia sẻ chi phí cố định. Tuy nhiên, batch quá lớn làm transaction kéo dài, tăng bộ nhớ, WAL, lock duration và chi phí rollback khi lỗi.

### 5.2. Batch size là một đánh đổi

| Batch nhỏ | Batch lớn |
|---|---|
| Latency mỗi batch thấp | Amortize overhead tốt hơn |
| Dễ retry và rollback phạm vi nhỏ | Ít commit và round trip hơn |
| Nhiều lần điều phối/commit | Có thể tăng throughput tới một điểm |
| Dễ tạo quá nhiều transaction | Transaction dài, nhiều WAL và lock lâu hơn |
| Ít memory mỗi batch | Có thể giữ nhiều dữ liệu trong memory và tạo temp lớn |

Không có batch size chuẩn. Hãy thử tăng dần theo các mức phù hợp với kích thước dòng, latency mạng, khả năng WAL/storage và giới hạn transaction. Theo dõi cả throughput lẫn p95/p99 và thời gian hoàn tất batch.

### 5.3. Bulk load trong PostgreSQL với COPY

Với dữ liệu nhập số lượng lớn, PostgreSQL hỗ trợ `COPY` để chuyển nhiều dòng hiệu quả hơn so với một câu `INSERT` riêng cho mỗi dòng.

```sql
COPY staging_events (event_id, event_time, tenant_id, event_type, amount)
FROM STDIN WITH (FORMAT csv, HEADER true);
```

`COPY FROM STDIN` thường được dùng qua driver để truyền dữ liệu từ ứng dụng. `COPY FROM '/path/file'` đọc file từ filesystem mà server có quyền truy cập và yêu cầu quyền phù hợp; không nhầm quyền filesystem của client với server.

Một quy trình nạp thường gặp:

1. Nạp vào staging table có cấu trúc và ràng buộc phù hợp.
2. Kiểm tra số dòng, dữ liệu sai định dạng và khóa trùng.
3. Chuyển dữ liệu hợp lệ sang bảng đích bằng `INSERT ... SELECT` hoặc thao tác merge phù hợp.
4. Cập nhật thống kê bằng `ANALYZE` khi cần.
5. Theo dõi WAL, replication lag, index maintenance và dung lượng trong lúc nạp.

Ví dụ chuyển dữ liệu đã kiểm tra:

```sql
INSERT INTO fact_events
    (event_id, event_time, tenant_id, event_type, amount)
SELECT
    event_id, event_time, tenant_id, event_type, amount
FROM staging_events
WHERE is_valid = true;
```

Nếu cần chống nạp trùng, dùng khóa duy nhất và chiến lược `ON CONFLICT` hoặc staging/dedup phù hợp. Không bỏ ràng buộc dữ liệu mà không có bước xác minh tương đương.

### 5.4. Chia batch theo transaction

Một batch có thể chứa nhiều dòng trong cùng transaction, nhưng không nhất thiết toàn bộ file phải nằm trong một transaction duy nhất. Chia thành micro-batch có thể:

- Giới hạn thời gian giữ lock và snapshot.
- Giới hạn lượng WAL cần xử lý trong một lần lỗi.
- Giúp replication và autovacuum có cơ hội theo kịp.
- Cho phép retry một phần dữ liệu nếu có idempotency.

Đổi lại, dữ liệu có thể được commit từng phần. Nếu nghiệp vụ yêu cầu tất cả hoặc không có gì, cần giữ một transaction nguyên tử hoặc thiết kế staging và bước publish nguyên tử. Hãy xác định rõ tính nhất quán trước khi chia batch.

### 5.5. Batch update và delete

Không nên gửi hàng nghìn câu update đơn lẻ nếu có thể diễn đạt bằng một thao tác set-based. Ví dụ:

```sql
UPDATE orders
SET archived = true
WHERE created_at < DATE '2025-01-01'
  AND archived = false;
```

Với tập dữ liệu rất lớn, một câu lệnh duy nhất có thể tạo transaction dài và lượng WAL lớn. Có thể chia thành batch theo khóa ổn định, commit giữa các batch và theo dõi lock/WAL. Khi dùng nhiều worker, cần thiết kế cách phân vùng công việc để tránh cùng xử lý một dòng.

### 5.6. Micro-batching và streaming

Streaming xử lý từng sự kiện khi đến; micro-batching gom sự kiện trong một cửa sổ ngắn rồi xử lý cùng lúc. Micro-batching giảm overhead và tận dụng bulk operation nhưng thêm độ trễ chờ gom batch.

Ví dụ, hệ thống có thể gom sự kiện trong 500 ms hoặc tới khi đạt 5.000 bản ghi, tùy điều kiện nào đến trước. Cửa sổ thời gian và kích thước tối đa phải phù hợp với SLA và tốc độ đầu vào.

Để vận hành an toàn, micro-batch cần:

- Checkpoint offset hoặc watermark để biết dữ liệu đã xử lý tới đâu.
- Idempotency hoặc deduplication khi batch được phát lại.
- Retry có giới hạn và dead-letter cho dữ liệu lỗi.
- Backpressure khi tốc độ đầu vào vượt năng lực xử lý.
- Metric về batch size, batch duration, lag và số lần retry.

## 6. Thực thi vector hóa

Trong mô hình thực thi row-at-a-time, engine gọi operator cho từng tuple. Mỗi lần gọi có thể có chi phí kiểm tra kiểu, điều kiện, con trỏ, nhánh điều khiển và chuyển dữ liệu giữa các operator.

**Vectorized execution** xử lý một nhóm giá trị cùng lúc. Engine đọc một batch cột hoặc vector, áp dụng phép so sánh, biểu thức hoặc aggregate lên nhiều phần tử rồi chuyển kết quả sang operator tiếp theo.

### 6.1. Row-at-a-time và vectorized

```text
Row-at-a-time:
  row 1 -> filter -> project -> aggregate
  row 2 -> filter -> project -> aggregate
  row 3 -> filter -> project -> aggregate
  ...

Vectorized:
  batch [row 1 ... row N]
        |
        v
      filter vector
        |
        v
      project vector
        |
        v
      aggregate vector
```

Vectorization giảm số lần gọi operator và có thể tận dụng SIMD (Single Instruction, Multiple Data) để áp dụng cùng một phép toán lên nhiều giá trị. Nó cũng giúp tăng locality và tận dụng memory bandwidth tốt hơn khi dữ liệu được bố trí phù hợp.

### 6.2. Vector và selection vector

Một vector có thể chứa các giá trị của một cột, ví dụ 1.024 timestamp hoặc 1.024 số tiền. Operator filter đánh giá predicate trên vector và tạo selection vector/mask cho biết phần tử nào thỏa điều kiện.

Ví dụ logic:

```text
amount:       [10, 80, 25, 120, 45]
predicate:    amount >= 50
selection:    [1, 3]
result:       [80, 120]
```

Selection vector cho phép operator tiếp theo xử lý chỉ các vị trí được chọn, giảm việc sao chép dữ liệu. Một số engine dùng bit mask, selection array hoặc bitmap tùy kiến trúc.

### 6.3. SIMD

SIMD cho phép một lệnh CPU thao tác trên nhiều phần tử dữ liệu trong một vector register. Ví dụ so sánh nhiều số nguyên với cùng một ngưỡng có thể được thực hiện song song trong một số instruction.

SIMD hữu ích với phép toán đơn giản và dữ liệu có kiểu đồng nhất như số nguyên, số thực hoặc timestamp được biểu diễn phù hợp. Nó ít hiệu quả hơn với logic phức tạp, chuỗi có độ dài biến thiên, nhánh điều kiện khó dự đoán hoặc dữ liệu cần giải mã nhiều bước.

Không phải mọi query engine đều vector hóa mọi operator. Một truy vấn có thể dùng vectorized scan nhưng chuyển sang operator row-based cho một hàm hoặc kiểu dữ liệu đặc biệt.

### 6.4. Pipeline execution

Trong pipeline execution, các operator truyền batch kết quả trực tiếp sang operator tiếp theo thay vì materialize toàn bộ kết quả trung gian ra bộ nhớ hoặc đĩa. Ví dụ scan → filter → project → aggregate có thể chạy theo từng batch.

Pipeline giảm việc ghi/đọc intermediate data và tăng locality. Tuy nhiên, một số operator cần state lớn hoặc phải chờ toàn bộ đầu vào, như sort toàn cục, hash build hoặc một số window operation. Những operator này có thể tạo ranh giới pipeline và cần memory hoặc temp storage.

### 6.5. Late materialization

Late materialization trì hoãn việc lấy các cột rộng hoặc payload lớn cho tới khi đã lọc được tập dòng cần thiết. Ví dụ, truy vấn chỉ cần `event_time` và `tenant_id` để lọc hàng triệu dòng; chỉ sau khi chọn được 1% dòng, engine mới lấy `payload` cho các dòng còn lại.

Kỹ thuật này đặc biệt hữu ích trong columnar storage vì có thể tránh đọc hoặc giải mã cột không cần thiết. Nếu truy vấn cần hầu hết cột ngay từ đầu, lợi ích sẽ nhỏ hơn.

## 7. Nén và vector hóa phối hợp như thế nào?

Columnar storage thường nén từng cột hoặc block. Vectorized engine giải mã block thành vector rồi áp dụng filter/aggregate lên nhiều phần tử. Một số engine có thể thực hiện predicate trực tiếp trên encoded representation để tránh giải mã toàn bộ dữ liệu.

Một pipeline phân tích có thể gồm:

```text
Đọc metadata block (min/max, row count)
        |
        v
Bỏ qua block không thỏa predicate
        |
        v
Đọc compressed column segment
        |
        v
Giải mã thành vector hoặc lọc trực tiếp trên encoding
        |
        v
Áp dụng selection mask
        |
        v
Project các cột cần thiết
        |
        v
Aggregate theo batch
        |
        v
Merge kết quả các batch
```

Lợi ích cộng hưởng có thể đến từ:

- Ít byte đọc nhờ nén.
- Ít block phải đọc nhờ min/max và data skipping.
- Ít overhead operator nhờ xử lý vector.
- Ít dữ liệu trung gian nhờ pipeline và late materialization.
- Ít memory footprint nếu batch được giới hạn phù hợp.

Nhưng có thể xuất hiện chi phí bổ sung:

- Giải mã codec tốn CPU.
- Batch quá lớn tạo memory pressure hoặc spill.
- Dictionary không phù hợp với cardinality.
- Dữ liệu không được sắp/clustering khiến data skipping kém.
- Một operator không hỗ trợ vector hóa làm pipeline chuyển chế độ hoặc materialize dữ liệu.

## 8. Ví dụ truy vấn phân tích

Giả sử bảng sự kiện có các cột `event_time`, `tenant_id`, `event_type`, `amount` và `payload`. Báo cáo chỉ cần doanh thu theo tenant và loại sự kiện trong một tháng:

```sql
SELECT
    tenant_id,
    event_type,
    SUM(amount) AS total_amount,
    COUNT(*) AS event_count
FROM fact_events
WHERE event_time >= TIMESTAMP '2026-10-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY tenant_id, event_type;
```

Các điểm cần lưu ý:

- `payload` không xuất hiện trong truy vấn, nên columnar engine có thể không đọc cột này.
- Filter thời gian có thể hỗ trợ partition pruning hoặc data skipping nếu dữ liệu được phân vùng/clustering phù hợp.
- `event_type` có thể có cardinality thấp và phù hợp với dictionary encoding.
- `event_time` có thể phù hợp với delta encoding nếu dữ liệu theo thứ tự gần thời gian.
- `SUM` và `COUNT` có thể được thực hiện theo batch rồi merge kết quả partial aggregate.

SQL chỉ mô tả kết quả logic. Việc engine có dùng columnar scan, compression, vectorized aggregation hoặc SIMD hay không phụ thuộc hệ quản trị, phiên bản, kiểu dữ liệu và execution plan.

### 8.1. Đọc kế hoạch và xác nhận engine thực sự dùng kỹ thuật

Trong PostgreSQL, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    tenant_id,
    event_type,
    SUM(amount) AS total_amount,
    COUNT(*) AS event_count
FROM fact_events
WHERE event_time >= TIMESTAMP '2026-10-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY tenant_id, event_type;
```

Quan sát scan type, partition pruning, số dòng trước/sau filter, hash/sort aggregate, memory, temp spill, buffers và thời gian từng node. PostgreSQL core sử dụng executor theo tuple cho các kế hoạch thông thường; không nên kết luận rằng truy vấn PostgreSQL đã dùng SIMD/vectorized execution chỉ vì nó quét theo batch ở tầng storage hoặc có aggregate.

Các data warehouse hoặc engine columnar có thể cung cấp thông tin riêng về vectorized operator, row group/segment pruning, compressed bytes, decoded bytes và SIMD. Hãy dùng explain/profile công cụ của đúng engine để xác nhận.

## 9. Batch size, memory và spill

Batch size ảnh hưởng cả throughput lẫn footprint bộ nhớ. Nếu một batch có N dòng, mỗi dòng mang nhiều cột và payload rộng, lượng memory cần giữ có thể lớn hơn nhiều so với kích thước file nén.

### 9.1. Batch quá nhỏ

- Tăng số lần gọi driver, commit hoặc chuyển batch.
- Tăng overhead điều phối và metadata.
- Có thể không tận dụng tốt bulk write hoặc vector operator.
- Tạo nhiều transaction nhỏ nếu mỗi batch commit riêng.

### 9.2. Batch quá lớn

- Tăng memory footprint và nguy cơ spill ra disk.
- Transaction kéo dài, giữ lock/snapshot lâu hơn.
- Tăng lượng WAL và phạm vi rollback khi lỗi.
- Làm tăng latency của bản ghi đầu tiên nếu phải chờ gom đủ batch.
- Có thể làm replication lag hoặc autovacuum khó theo kịp.

### 9.3. Chọn batch size theo phép đo

Thử một dải kích thước tăng dần, ví dụ 256, 1.024, 4.096 hoặc 16.384 dòng tùy kích thước record và engine. Đây là các mốc thử nghiệm minh họa, không phải giá trị mặc định. Với vectorized engine, batch nội bộ thường do engine quản lý; không nên ép batch SQL của ứng dụng bằng đúng kích thước vector nội bộ.

Ghi nhận:

- Rows/second và bytes/second.
- Thời gian mỗi batch và p95/p99.
- Peak memory và memory bandwidth.
- Temp bytes/files và số lần spill.
- WAL bytes, commit latency và lock duration.
- CPU utilization và storage latency.
- Queue depth, consumer lag và replication lag.

Chọn batch size nằm trong vùng throughput tốt mà không làm latency, memory hoặc I/O vượt giới hạn vận hành.

## 10. Các giới hạn và trường hợp kỹ thuật không hiệu quả

### 10.1. Dữ liệu khó nén

Ảnh, video, ciphertext, dữ liệu đã nén hoặc chuỗi ngẫu nhiên thường có entropy cao và ít lặp. Nén thêm có thể chỉ tiết kiệm ít byte nhưng vẫn tốn CPU. Với dữ liệu nhị phân đã nén, có thể lưu nguyên dạng hoặc dùng codec nhẹ tùy yêu cầu.

### 10.2. Workload cần cập nhật từng dòng liên tục

Columnar storage và block compression phù hợp với dữ liệu ít thay đổi hoặc ingest theo lô. Cập nhật một giá trị nhỏ trong block nén có thể cần giải mã, sửa và ghi lại block hoặc tạo delta structure tùy engine. Với workload OLTP cập nhật từng dòng thường xuyên, row store có thể phù hợp hơn.

### 10.3. Truy vấn cần hầu hết cột

Column store có lợi khi chỉ đọc một phần cột. Nếu truy vấn cần tất cả cột cho từng dòng, engine phải đọc nhiều segment và có thể chịu thêm chi phí tái dựng dòng. Row store có thể hiệu quả hơn tùy hệ thống.

### 10.4. Batch gây áp lực transaction

Một transaction ingest quá lớn có thể giữ snapshot lâu, tạo nhiều WAL, làm rollback tốn thời gian và gây replication lag. Chia batch có thể cải thiện khả năng kiểm soát, nhưng phải giữ idempotency và quy tắc publish dữ liệu.

### 10.5. Vectorization không giúp mọi operator

Các phép toán số học, so sánh và aggregate trên kiểu dữ liệu đồng nhất thường vector hóa tốt. UDF phức tạp, xử lý chuỗi biến thiên, logic nhiều nhánh hoặc operator không hỗ trợ vector có thể làm giảm lợi ích. Chi phí chuyển đổi giữa vector và row representation cũng có thể đáng kể.

## 11. Khác biệt giữa PostgreSQL row store và engine columnar

PostgreSQL core chủ yếu lưu bảng theo row-oriented heap. Nó có cơ chế nén cho một số giá trị lớn thông qua TOAST; tùy phiên bản và cấu hình có thể dùng các phương thức nén như PGLZ hoặc LZ4. Cơ chế TOAST không biến bảng heap thành column store và không đồng nghĩa query executor PostgreSQL core thực thi vector hóa toàn diện.

Để phục vụ phân tích lớn, hệ thống có thể dùng:

- Partitioning và pruning trong PostgreSQL để giới hạn vùng dữ liệu cần đọc.
- Materialized view hoặc bảng tổng hợp để giảm scan lặp lại.
- Extension hoặc giải pháp lưu trữ columnar tương thích với PostgreSQL.
- ETL/ELT sang data warehouse hoặc query engine columnar.
- Object storage với định dạng cột như Parquet và engine đọc trực tiếp.

Với PostgreSQL row store, tối ưu có thể tập trung vào index, partition pruning, parallel query, aggregate, `COPY`, statistics và memory/temp. Với columnar engine, cần thêm đánh giá encoding, compression, row group, vectorized execution và data skipping.

Không áp dụng tham số của một columnar engine cho PostgreSQL core nếu chúng không tồn tại. Hãy kiểm tra tính năng và phiên bản cụ thể trước khi cấu hình.

## 12. Quy trình tối ưu một pipeline phân tích

**Bước 1 — Mô tả workload.** Xác định dữ liệu đầu vào, số dòng/ngày, độ rộng record, tỷ lệ đọc/ghi, truy vấn chính, SLA và mức đồng thời.

**Bước 2 — Lưu baseline.** Đo thời gian ingest, query latency, throughput, CPU, memory, I/O, WAL, temp spill và dung lượng lưu trữ.

**Bước 3 — Chọn layout và kiểu dữ liệu.** Xem row/column store, partition, clustering, kiểu số/ngày giờ và cột cần đọc. Tránh lưu payload rộng trong đường scan nếu không cần.

**Bước 4 — Thử encoding/compression.** Chọn một tập dữ liệu đại diện, thử codec/encoding theo cardinality và phân bố; đo tỷ lệ nén, giải nén, CPU và bytes đọc.

**Bước 5 — Tối ưu ingestion theo batch.** Thử bulk load hoặc `COPY`, batch size khác nhau, staging và commit theo lô. Kiểm tra duplicate, retry, WAL, lock và replication lag.

**Bước 6 — Xem kế hoạch truy vấn.** Xác nhận filter pushdown, partition/data skipping, số cột được đọc, aggregate, sort, join và temp spill.

**Bước 7 — Kiểm tra vectorization.** Dùng profile/explain của engine để xác nhận operator nào chạy theo vector, có fallback hay chuyển đổi representation không.

**Bước 8 — Tối ưu memory.** Giới hạn batch, concurrency và memory theo operator; kiểm tra spill và tổng footprint khi nhiều query đồng thời.

**Bước 9 — Benchmark hỗn hợp.** Chạy ingest và truy vấn phân tích đồng thời, với cache nóng/lạnh và dữ liệu có phân bố đại diện.

**Bước 10 — Xác nhận tính đúng.** Đối chiếu số dòng, checksum hoặc aggregate giữa nguồn và đích; kiểm tra timezone, NULL, precision, duplicate và thứ tự xử lý sự kiện.

**Bước 11 — Đánh giá toàn hệ thống.** So sánh throughput, p95/p99, CPU, memory, I/O, WAL, temp, replication lag, dung lượng và chi phí vận hành.

**Bước 12 — Triển khai có thể rollback.** Lưu cấu hình cũ, thử trên một partition hoặc workload nhỏ, theo dõi và mở rộng dần khi đạt mục tiêu.

## 13. Thiết kế benchmark có đối chứng

Một benchmark đáng tin cậy cần giữ các yếu tố so sánh giống nhau:

- Cùng dữ liệu hoặc cùng snapshot dữ liệu.
- Cùng truy vấn và điều kiện lọc.
- Cùng page cache/storage cache state hoặc ghi rõ cache nóng/lạnh.
- Cùng số worker và concurrency.
- Cùng cấu hình CPU, memory và storage.
- Đo nhiều lần, loại bỏ thời gian warm-up khi phù hợp và báo cáo phân vị.

Không chỉ so sánh thời gian chạy trung bình. Một cấu hình có throughput cao hơn nhưng p99 tăng mạnh có thể không phù hợp với workload chia sẻ tài nguyên. Một codec tiết kiệm 70% dung lượng nhưng tăng CPU gấp đôi có thể tốt cho kho dữ liệu lưu trữ lâu dài nhưng không tốt cho truy vấn tương tác.

### 13.1. Ma trận benchmark mẫu

| Thử nghiệm | Thay đổi | Chỉ số chính |
|---|---|---|
| Baseline | Không nén, batch hiện tại, execution mặc định | Thời gian, throughput, CPU, I/O, memory |
| Compression | Thử encoding/codec khác | Compressed bytes, decode throughput, CPU, query latency |
| Batch size | Tăng/giảm kích thước batch | Rows/s, batch duration, memory, WAL, lock time |
| Vectorized path | Bật/tắt hoặc so sánh engine/operator nếu hỗ trợ | CPU cycles/row, vector batches, throughput, spill |
| Mixed workload | Ingest đồng thời với dashboard | p95/p99 đọc/ghi, throughput tổng, resource saturation |

### 13.2. Kiểm tra tính đúng đắn

Nén và xử lý theo lô không được làm thay đổi dữ liệu logic. Đặc biệt chú ý:

- Decimal và số thực: tránh sai số do đổi kiểu hoặc phép tính khác thứ tự.
- Timestamp: giữ timezone và độ chính xác phần lẻ giây.
- NULL: không biến NULL thành 0 hoặc chuỗi rỗng khi encode.
- Duplicate: batch retry không được nhân đôi sự kiện.
- Ordering: nếu pipeline phụ thuộc thứ tự, phải dùng sequence/version thay vì giả định thứ tự batch.
- Late-arriving data: dữ liệu đến trễ cần cập nhật đúng partition hoặc aggregate.
- Partial failure: batch commit một phần phải có checkpoint để tiếp tục an toàn.

## 14. Những nhầm lẫn thường gặp

- **“Nén càng mạnh càng nhanh.”** Nén giảm I/O nhưng tăng CPU giải mã; cần xác định bottleneck trước.
- **“Tỷ lệ nén cao chứng minh truy vấn nhanh.”** Cần đo bytes đọc, decode cost, CPU và latency thực tế.
- **“Column store luôn tốt hơn row store.”** Column store phù hợp scan/aggregate; row store thường phù hợp cập nhật và lookup theo dòng.
- **“Dictionary encoding phù hợp với mọi cột.”** Cột cardinality cao hoặc thay đổi liên tục có thể làm dictionary tốn kém.
- **“RLE không phụ thuộc thứ tự dữ liệu.”** RLE hiệu quả khi giá trị giống nhau nằm liên tiếp; clustering có thể làm run dài hơn.
- **“Batch càng lớn càng tốt.”** Batch quá lớn tăng memory, WAL, lock duration, rollback và latency.
- **“Batching ở ứng dụng đồng nghĩa vectorized execution.”** Batching gom thao tác; vectorization là cách query engine thực thi operator.
- **“SIMD tự động được dùng cho mọi truy vấn.”** Chỉ operator và kiểu dữ liệu được hỗ trợ mới tận dụng SIMD.
- **“Vectorized execution không cần memory limit.”** Batch lớn và operator state vẫn có thể gây memory pressure hoặc spill.
- **“PostgreSQL core là columnar engine.”** Heap mặc định là row-oriented; TOAST compression không biến heap thành column store.
- **“Thêm partition tự động làm scan nhanh.”** Cần predicate cho phép pruning và partition layout phù hợp.
- **“Benchmark một truy vấn là đủ.”** Phải đo tải đọc/ghi đồng thời, cache state và concurrency đại diện.
- **“Có thể bỏ ràng buộc để nạp nhanh.”** Bulk load cần quy trình xác minh dữ liệu và bảo đảm tính toàn vẹn tương đương.

## 15. Checklist nén, batching và vectorization

- [ ] Đã xác định workload thiên về scan/aggregate hay lookup/update theo dòng.
- [ ] Đã chọn row store, column store hoặc mô hình kết hợp theo mẫu truy vấn.
- [ ] Đã phân tích cardinality, entropy và phân bố dữ liệu theo block.
- [ ] Đã thử encoding phù hợp như dictionary, RLE, delta hoặc bit packing.
- [ ] Đã đo compressed size, decode throughput, CPU và bytes đọc.
- [ ] Đã xem data skipping, partition pruning và số block thực sự được đọc.
- [ ] Đã chọn batch size bằng benchmark, có giới hạn memory và transaction duration.
- [ ] Đã cân nhắc `COPY`/bulk load, staging, deduplication và idempotency.
- [ ] Đã phân biệt batching ở ứng dụng với vectorized execution trong engine.
- [ ] Đã xác nhận operator nào thực sự vectorized/SIMD bằng công cụ của engine.
- [ ] Đã kiểm tra pipeline boundary, late materialization và temp spill.
- [ ] Đã benchmark tải hỗn hợp với p95/p99, throughput, CPU, memory, I/O và WAL.
- [ ] Đã đối chiếu tính đúng của dữ liệu sau nén, batch và retry.
- [ ] Đã có phương án rollback và theo dõi sau triển khai.

## Kết luận

Nén dữ liệu giảm byte lưu trữ và I/O nhưng cần CPU để giải mã. Columnar layout kết hợp dictionary, RLE, delta, bit packing và codec có thể đặc biệt hiệu quả với dữ liệu phân tích có cấu trúc và phân bố phù hợp. Batching giảm round trip và chi phí cố định khi nạp hoặc xử lý dữ liệu, nhưng batch quá lớn làm tăng memory, WAL, lock duration và phạm vi rollback. Vectorized execution xử lý nhiều giá trị cùng lúc, giảm overhead operator và có thể tận dụng SIMD, nhưng hiệu quả phụ thuộc engine, kiểu dữ liệu và operator.

Hãy chọn kỹ thuật dựa trên nút thắt đo được. Đo tỷ lệ nén cùng decode cost, thử batch size theo throughput và latency, xác nhận vectorized path bằng execution profile, rồi benchmark tải đọc/ghi hỗn hợp. Một thay đổi chỉ có ích khi cải thiện hiệu năng tổng thể mà vẫn giữ nguyên tính đúng đắn, khả năng phục hồi và giới hạn tài nguyên của hệ thống.
