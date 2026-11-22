# Khác biệt truy cập theo hàng và theo cột trong truy vấn phân tích

Một truy vấn phân tích thường đọc rất nhiều hàng nhưng chỉ cần một phần nhỏ các cột để lọc, nhóm và tính tổng. Ngược lại, một giao dịch OLTP thường tìm một vài hàng theo khóa rồi đọc hoặc cập nhật nhiều thuộc tính của những hàng đó. Hai kiểu truy cập này có đặc điểm rất khác nhau. **Row-oriented storage** đặt các cột của cùng một hàng gần nhau; **column-oriented storage** đặt các giá trị của cùng một cột hoặc nhóm giá trị cùng cột gần nhau. Cách tổ chức dữ liệu ảnh hưởng đến lượng I/O, khả năng nén, CPU giải mã, bộ nhớ, tính song song và chi phí ghi.

Bài học thuộc chương **Tải phân tích** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Khi tối ưu truy vấn phân tích, cần hiểu dữ liệu được lưu theo hàng hay theo cột, engine thực sự đọc bao nhiêu cột/hàng, và liệu layout hiện tại có phù hợp với query mix hay không.

## 1. Hai cách tổ chức dữ liệu

Giả sử có bảng `sales` gồm các cột:

```text
sale_id, sale_time, customer_id, region_id,
product_id, quantity, unit_price, status, note
```

Một hệ thống OLTP thường tra cứu một giao dịch theo `sale_id` và cần nhiều thuộc tính của đúng một hàng. Một báo cáo doanh thu có thể quét hàng chục triệu giao dịch nhưng chỉ cần `region_id`, `sale_time` và `quantity * unit_price`.

### 1.1. Row-oriented storage

Trong row store, các giá trị của một hàng được lưu gần nhau theo định dạng hàng. Một cách hình dung đơn giản:

```text
Row 1: [sale_id | sale_time | customer_id | region_id | product_id | ...]
Row 2: [sale_id | sale_time | customer_id | region_id | product_id | ...]
Row 3: [sale_id | sale_time | customer_id | region_id | product_id | ...]
```

Khi tìm một hàng theo primary key, engine có thể định vị page chứa hàng rồi đọc nhiều cột của hàng đó trong một số lần truy cập bộ nhớ/storage tương đối ít. Đây là lý do row store thường phù hợp với point lookup, insert/update từng hàng và transaction cần nhiều thuộc tính của một số ít hàng.

### 1.2. Column-oriented storage

Trong column store, các giá trị của cùng một cột được lưu gần nhau, thường theo column segment hoặc column chunk:

```text
sale_id:     [101 | 102 | 103 | ...]
sale_time:   [t1  | t2  | t3  | ...]
region_id:   [7   | 3   | 7   | ...]
quantity:    [2   | 1   | 5   | ...]
unit_price:  [10  | 25  | 12  | ...]
status:      [OK  | OK  | VOID| ...]
```

Nếu truy vấn chỉ cần `region_id`, `quantity` và `unit_price`, columnar engine có thể đọc các column chunks tương ứng và bỏ qua các cột còn lại. Các giá trị cùng cột thường có kiểu và phân bố gần nhau, tạo cơ hội nén hiệu quả và xử lý theo vector.

Đây là mô hình khái niệm. Hệ thống thực tế có thể chia dữ liệu thành row group, stripe, segment, micro-partition hoặc block; có metadata, dictionary, encoding, compression và index riêng. Column store không nhất thiết lưu từng cột thành một file độc lập.

## 2. Vì sao truy vấn phân tích thường thích truy cập theo cột?

Truy vấn phân tích thường có ba đặc điểm:

- Đọc nhiều hàng để tính toán trên một tập dữ liệu lớn.
- Chỉ dùng một phần các cột trong bảng.
- Thực hiện các phép scan, filter, aggregate, sort và join với số lượng hàng lớn.

Ví dụ báo cáo doanh thu theo khu vực:

```sql
SELECT region_id, SUM(quantity * unit_price) AS revenue
FROM sales
WHERE sale_time >= TIMESTAMP '2026-10-01 00:00:00'
  AND sale_time <  TIMESTAMP '2026-11-01 00:00:00'
  AND status = 'OK'
GROUP BY region_id;
```

Truy vấn cần `sale_time` và `status` để lọc, `region_id` để nhóm, `quantity` và `unit_price` để tính tổng. Các cột như `customer_id`, `note` hoặc `product_id` không cần thiết cho kết quả này.

Trong row store, các cột không dùng có thể vẫn nằm trên page được đọc khi scan hàng, tùy định dạng hàng và cách lưu cột lớn/off-row. Trong column store, engine thường có thể bỏ hẳn column chunks không được tham chiếu. Vì vậy, khi bảng rộng và truy vấn chỉ dùng ít cột, columnar scan có thể giảm đáng kể bytes đọc và dữ liệu cần giải mã.

### 2.1. Lợi ích của projection pruning

Projection pruning là việc loại bỏ cột không cần thiết khỏi đường đọc và các toán tử. Nó có thể giảm:

- Số byte phải đọc từ storage.
- Số byte phải giải nén hoặc decode.
- Lượng dữ liệu đưa vào filter, join và aggregate.
- Memory footprint của vector/buffer trung gian.
- Dữ liệu truyền qua network exchange trong hệ thống phân tán.
- Lượng dữ liệu serialize và trả về client.

Lợi ích rõ nhất khi các cột bị bỏ chiếm tỷ trọng lớn và storage engine thực sự có thể đọc riêng cột. Với row store, bỏ cột vẫn giảm output/network và có thể giúp covering index, nhưng không nhất thiết giảm tỷ lệ page scan tương ứng với số cột bị bỏ.

### 2.2. Lợi ích của compression

Columnar layout thường tạo locality theo kiểu dữ liệu và giá trị. Ví dụ một cột `status` có rất ít giá trị khác nhau; một cột `sale_date` có thể có nhiều giá trị lặp hoặc tăng theo thời gian. Engine có thể dùng dictionary encoding, run-length encoding, bit packing, delta encoding hoặc compression codec phù hợp.

Khi dữ liệu nén tốt, hệ thống có thể đọc ít byte từ storage hơn. Nếu CPU giải nén nhanh và dữ liệu có locality tốt, chi phí giải mã có thể thấp hơn chi phí I/O tiết kiệm được. Tuy nhiên, compression không miễn phí: dữ liệu cần được encode/decode, và mức nén phụ thuộc phân bố dữ liệu, row group size và codec.

## 3. Vì sao OLTP thường thích truy cập theo hàng?

Một giao dịch như cập nhật trạng thái đơn hàng thường cần tìm một hàng rồi đọc hoặc sửa một số thuộc tính:

```sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE order_id = :order_id;

UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = :order_id;
```

Row store có thể truy cập page chứa hàng và thao tác với các cột liên quan trong cùng vùng lưu trữ. Nó thường phù hợp với:

- Point lookup theo primary key hoặc unique key.
- Insert từng hàng.
- Update một số hàng.
- Delete theo khóa.
- Transaction cần nhiều cột của cùng một hàng.
- Workload có yêu cầu đồng thời và cập nhật thường xuyên.

Column store vẫn có thể hỗ trợ một số kiểu cập nhật, nhưng việc thay đổi một giá trị có thể liên quan đến encoding, compression unit, delta store, delete bitmap hoặc merge/rewrite segment tùy kiến trúc. Một số columnar database được thiết kế để xử lý ingestion và mutation hiệu quả, nhưng không nên mặc định chúng có cùng đặc tính với row-oriented OLTP engine.

## 4. So sánh row store và column store

| Tiêu chí | Row-oriented | Column-oriented |
|---|---|---|
| Đơn vị locality chính | Các cột của một hàng | Các giá trị của cùng cột/column chunk |
| Point lookup | Thường hiệu quả khi có index phù hợp | Có thể cần cấu trúc index/metadata riêng hoặc đọc segment |
| Scan nhiều hàng, ít cột | Có thể đọc dữ liệu thừa của hàng | Thường đọc riêng các cột được chọn |
| Đọc nhiều cột của ít hàng | Thường thuận lợi | Có thể cần ghép nhiều column streams |
| Aggregate trên cột | Có thể cần scan page chứa hàng | Thường phù hợp với vectorized column scan |
| Compression | Có thể nén theo page/row | Thường tận dụng locality cùng cột tốt hơn |
| Insert/update nhỏ | Thường thuận lợi | Có thể cần delta store, delete bitmap hoặc merge |
| Workload điển hình | OLTP, transaction | OLAP, warehouse, scan và aggregate |
| Chi phí cần chú ý | Random I/O, index maintenance, row width | Ingestion/merge, delete/update, metadata và segment management |

Đây là xu hướng chung, không phải quy luật tuyệt đối. Một row store có covering index tốt có thể trả lời một số truy vấn phân tích rất nhanh. Một column store có thể hỗ trợ workload tương tác hoặc truy vấn gần thời gian thực nếu thiết kế phù hợp.

## 5. Cách một row store thực hiện truy vấn phân tích

Giả sử bảng `sales` là row-oriented và có 500 triệu hàng. Truy vấn cần lọc một khoảng thời gian, nhóm theo khu vực và tính doanh thu.

Nếu không có access path hữu ích, engine có thể thực hiện full table scan:

```text
Table Scan: sales
    |
    v
Filter sale_time/status
    |
    v
Compute quantity * unit_price
    |
    v
Hash Aggregate by region_id
    |
    v
Sort by revenue
```

Trong row store, scan có thể phải đọc các page chứa hàng. Nếu hàng rộng hoặc có payload lớn, lượng dữ liệu vật lý đọc có thể lớn dù truy vấn chỉ dùng ít cột. Engine có thể giảm tác động bằng covering index, index-only access, partitioning, compression hoặc row-store-specific optimizations.

### 5.1. Covering index

Một covering index chứa đủ các cột cần cho predicate và output để engine có thể trả kết quả mà không phải quay lại đọc base table cho từng hàng. Ví dụ:

```sql
SELECT sale_time, region_id, quantity, unit_price
FROM sales
WHERE region_id = :region_id
  AND sale_time >= :from_time
  AND sale_time < :to_time;
```

Một index có key `(region_id, sale_time)` và include các cột `quantity`, `unit_price` nếu DBMS hỗ trợ có thể giảm lookup về bảng chính.

Covering index có trade-off:

- Tăng kích thước index và storage.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Tăng công việc vacuum/maintenance hoặc page split tùy engine.
- Có thể cải thiện một query nhưng không phù hợp với mọi query mix.

Không tạo index chứa mọi cột chỉ để biến row store thành column store. Index chỉ có ích khi query pattern và selectivity phù hợp.

### 5.2. Index-only scan không phải lúc nào cũng chỉ đọc index

Một số DBMS cần xác nhận visibility hoặc kiểm tra dữ liệu trong heap/base table trước khi coi kết quả là index-only. Ví dụ PostgreSQL có thể dùng visibility map để tránh heap fetch cho page phù hợp; nếu visibility information chưa đủ, vẫn có heap fetch. Hãy xem actual plan và số heap fetch thay vì chỉ nhìn tên operator.

### 5.3. Partition pruning và scan theo phạm vi

Nếu bảng row store partition theo thời gian, predicate trên partition key có thể loại các partition ngoài khoảng cần đọc. Điều này giảm lượng page scan ở mức partition. Kết hợp partition pruning với index hoặc scan trong partition có thể hiệu quả hơn đọc toàn bộ bảng.

## 6. Cách column store thực hiện truy vấn phân tích

Trong columnar engine, dữ liệu có thể được chia thành row group/segment. Mỗi nhóm chứa column chunk và metadata. Với truy vấn ví dụ, engine có thể:

1. Đọc metadata để xác định schema và phạm vi dữ liệu.
2. Chọn các cột `sale_time`, `status`, `region_id`, `quantity`, `unit_price`.
3. Bỏ qua partition, file hoặc row group không thể chứa ngày cần tìm.
4. Đọc và giải nén column chunks cần thiết.
5. Áp dụng filter trên vector giá trị.
6. Tính biểu thức và aggregate theo batch/vector.
7. Trả kết quả đã nhóm.

```text
Metadata / partition pruning
            |
            v
Chọn các cột cần thiết (projection)
            |
            v
Đọc column chunks / row groups
            |
            v
Decode + vectorized filter
            |
            v
Vectorized expression evaluation
            |
            v
Partial aggregate per worker
            |
            v
Merge/final aggregate
            |
            v
Kết quả
```

Các bước có thể được pipeline và chạy song song. Engine có thể push filter xuống reader để tránh giải mã toàn bộ giá trị hoặc dùng metadata để bỏ row group trước khi đọc. Hiệu quả phụ thuộc format, layout, statistics và connector.

### 6.1. Vectorized execution

Thay vì xử lý từng hàng qua một vòng lặp object-oriented, vectorized engine xử lý một batch giá trị của cùng cột hoặc một batch hàng. Cách này có thể:

- Giảm overhead gọi hàm và quản lý object cho từng hàng.
- Tận dụng cache CPU và SIMD/vector instructions.
- Áp dụng predicate cho nhiều giá trị cùng lúc.
- Tối ưu biểu thức số học và aggregate theo batch.
- Giảm chi phí chuyển đổi qua lại giữa representation.

Vectorized execution không tự động làm mọi truy vấn nhanh. Nếu dữ liệu bị skew, memory không đủ hoặc phải shuffle nhiều, network và spill vẫn có thể chi phối. Hàm UDF hoặc kiểu dữ liệu không được vector hóa cũng có thể làm pipeline quay về xử lý chậm hơn.

### 6.2. Late materialization

Late materialization là kỹ thuật trì hoãn việc ghép hoặc dựng đầy đủ hàng cho đến khi thật sự cần. Engine có thể lọc trên các vector cột trước, giữ row identifier/selection vector cho các hàng còn lại, rồi mới lấy thêm cột hoặc tạo output.

Ví dụ, truy vấn lọc 1 tỷ hàng còn 0,5% bằng `status` và `sale_time`. Engine có thể chỉ đọc hai cột filter trước, tạo danh sách row position còn phù hợp, sau đó mới đọc `region_id` và `amount` cho số hàng còn lại. Cách này tránh đọc/giải mã cột output cho những hàng bị loại.

Late materialization hữu ích khi filter có selectivity cao và dữ liệu được tổ chức cho phép truy cập cột theo row position. Nếu filter giữ gần như toàn bộ hàng hoặc việc truy cập cột sau đó không tuần tự, lợi ích có thể nhỏ.

## 7. Compression và encoding trong column store

Columnar storage thường có cơ hội nén tốt vì các giá trị liên tiếp có cùng kiểu và có thể lặp lại hoặc có delta nhỏ.

### 7.1. Dictionary encoding

Thay vì lưu chuỗi lặp lại nhiều lần, engine lưu dictionary các giá trị duy nhất và mã số đại diện cho từng giá trị.

Ví dụ:

```text
Giá trị:  VN, VN, SG, VN, JP, SG
Dictionary: 0=VN, 1=SG, 2=JP
Mã:       0,  0,  1,  0,  2,  1
```

Điều này có thể giảm dung lượng và giúp filter equality nhanh hơn khi engine có thể so sánh mã. Nếu cardinality rất cao hoặc dictionary lớn, lợi ích giảm và metadata có thể tăng.

### 7.2. Run-length encoding

Run-length encoding lưu một giá trị cùng số lần lặp liên tiếp. Ví dụ `A,A,A,A,B,B,C` có thể được biểu diễn thành `(A,4),(B,2),(C,1)`. Kỹ thuật này hiệu quả khi dữ liệu được sắp xếp hoặc có các đoạn giá trị lặp dài.

### 7.3. Delta encoding và bit packing

Với dữ liệu số tăng đều hoặc có chênh lệch nhỏ, delta encoding lưu chênh lệch giữa các giá trị thay vì toàn bộ số. Bit packing dùng số bit vừa đủ để biểu diễn các giá trị trong block. Các kỹ thuật này có thể giảm bytes đọc và cải thiện cache locality.

### 7.4. Compression codec

Codec như Snappy, Zstandard, LZ4 hoặc các codec khác có trade-off giữa tốc độ nén/giải nén và tỷ lệ nén. Chọn codec cần dựa trên storage bandwidth, CPU, query pattern và khả năng của engine. Codec nén mạnh có thể giảm I/O nhưng tăng CPU decode; codec nhanh có thể dùng nhiều storage hơn nhưng cải thiện thời gian truy vấn trong môi trường CPU-bound.

## 8. Row group, segment và kích thước đơn vị lưu trữ

Column store thường gom nhiều hàng thành row group hoặc segment. Kích thước đơn vị này ảnh hưởng đến:

- Compression ratio.
- Hiệu quả min/max pruning và dictionary.
- Mức song song khi scan.
- Số lượng metadata và file/segment cần quản lý.
- Chi phí mở file và lập task.
- Khả năng đọc ngẫu nhiên hoặc cập nhật một phần.

Row group quá nhỏ có thể tạo metadata overhead, compression kém và nhiều task nhỏ. Row group quá lớn có thể làm tăng memory cần thiết, giảm độ mịn của pruning và tạo ít đơn vị song song hơn. Không có kích thước tối ưu chung; hãy dùng khuyến nghị của engine rồi đo với phân bố dữ liệu thực tế.

### 8.1. Min/max pruning

Mỗi row group có thể lưu min/max cho một cột. Nếu truy vấn lọc tháng 10 nhưng row group chỉ chứa ngày tháng 2, engine có thể bỏ qua nhóm đó. Dữ liệu được sắp xếp hoặc clustering theo cột lọc thường giúp min/max hẹp và hữu ích hơn.

### 8.2. Small files và compaction

Trong data lake, quá nhiều file nhỏ làm tăng chi phí liệt kê metadata, mở file và lập task. Compaction có thể gộp file để giảm overhead. Tuy nhiên, compaction cũng tiêu thụ CPU/I/O và có thể ảnh hưởng ingestion; file quá lớn có thể giảm parallelism hoặc làm pruning kém. Cần đo file count, average size, row group count và bytes scanned.

## 9. Row store có thể tối ưu cho phân tích bằng cách nào?

Không phải mọi workload phân tích đều cần chuyển sang column store. Row store có thể đáp ứng tốt khi:

- Bảng không quá rộng hoặc query dùng phần lớn cột.
- Dataset vừa cache hoặc truy vấn chọn lọc cao.
- Có index/covering index phù hợp.
- Partition pruning giới hạn phạm vi scan.
- Query chỉ cần một nhóm hàng nhỏ.
- Hệ thống cần cập nhật liên tục và freshness thấp.

Các kỹ thuật hỗ trợ:

1. Projection tường minh, tránh `SELECT *`.
2. Predicate sargable trên partition/index key.
3. Covering index cho query pattern ổn định.
4. Partitioning theo thời gian/tenant khi phù hợp.
5. Statistics/histogram để optimizer ước lượng cardinality.
6. Materialized view hoặc summary table cho aggregate lặp lại.
7. Read replica hoặc reporting database để cách ly tải phân tích.

### 9.1. Materialized view và summary table

Nếu cùng một aggregate được tính thường xuyên, có thể lưu trước kết quả theo ngày/khu vực/sản phẩm. Truy vấn báo cáo sẽ đọc ít hàng hơn thay vì quét fact table mỗi lần. Đổi lại, hệ thống phải cập nhật hoặc refresh summary, xử lý late-arriving data và xác định độ trễ chấp nhận được.

### 9.2. Columnstore index trên row-oriented database

Một số hệ quản trị hỗ trợ columnstore index hoặc columnar access path bên cạnh row store. Ví dụ SQL Server có columnstore index; một số nền tảng khác cung cấp extension hoặc analytic engine riêng. Điều này cho phép giữ bảng row-oriented cho OLTP nhưng dùng cấu trúc cột cho scan/aggregate.

Columnstore index có chi phí build, memory, compression, delta rowgroup hoặc maintenance. Khả năng update và concurrency khác nhau theo engine/phiên bản. Hãy xác nhận query optimizer chọn columnstore path cho truy vấn mục tiêu và đo ảnh hưởng lên workload ghi.

## 10. Column store có thể hỗ trợ ghi và truy vấn point như thế nào?

Column store không nhất thiết phải ghi trực tiếp vào segment nén chính mỗi khi có INSERT/UPDATE. Một số engine dùng:

- Delta store hoặc write buffer để nhận ghi mới.
- Delete bitmap/tombstone để đánh dấu hàng đã xóa.
- Background merge/compaction để hợp nhất dữ liệu.
- Micro-batch ingestion để gom nhiều thay đổi.
- Metadata/index phụ để tìm segment hoặc key.

Kiến trúc này giúp tăng throughput ingestion, nhưng có thể tạo độ trễ giữa dữ liệu mới và segment tối ưu, đồng thời phát sinh background merge. Truy vấn có thể phải đọc cả dữ liệu trong delta store lẫn segment nén.

Point lookup trên column store phụ thuộc index, clustering, metadata và khả năng tìm key. Một số analytic database có index phụ hoặc search optimization; một số hệ thống không tối ưu cho point lookup như row-oriented OLTP engine. Cần benchmark đúng kiểu truy cập thay vì suy ra từ nhãn “columnar”.

## 11. Hybrid architecture: kết hợp row và column

Trong hệ thống thực tế, một kiến trúc có thể dùng nhiều layout:

```text
Ứng dụng giao dịch
       |
       v
Row-oriented OLTP database
       |
       +---- CDC / replication / ETL ---->
                                         |
                                         v
                                Columnar warehouse
                                         |
                                         v
                                  Báo cáo / OLAP
```

Row store phục vụ transaction và cập nhật chi tiết; dữ liệu được chuyển qua CDC, replication hoặc ETL sang columnar warehouse để scan/aggregate. Kiến trúc này cách ly tải phân tích và cho phép tối ưu từng hệ thống theo workload.

Trade-off:

- Có độ trễ đồng bộ giữa OLTP và warehouse.
- Cần quản lý CDC lag, schema evolution, replay và duplicate events.
- Dữ liệu có thể không đồng nhất trong một khoảng thời gian.
- Phải vận hành thêm pipeline, storage và monitoring.
- Truy vấn cần dữ liệu mới nhất có thể vẫn phải đọc từ OLTP hoặc dùng đường truy vấn khác.

Không nên đưa mọi truy vấn sang warehouse nếu nghiệp vụ yêu cầu read-after-write tức thời. Hãy xác định freshness SLO và cách xử lý dữ liệu chưa được replicate.

## 12. Chọn layout theo query pattern

Hãy phân loại truy vấn trước khi chọn row hay column:

| Query pattern | Layout thường phù hợp | Lý do |
|---|---|---|
| Tìm một hàng theo primary key, đọc nhiều thuộc tính | Row store | Các cột của hàng ở gần nhau, index lookup phù hợp |
| Cập nhật trạng thái một số hàng | Row store | Mutation theo hàng và transaction thường xuyên |
| Quét hàng triệu hàng nhưng chỉ đọc 3/40 cột | Column store | Projection pruning giảm bytes đọc |
| Aggregate trên cột số với nhiều hàng | Column store | Scan cột, compression và vectorized aggregation |
| Báo cáo trên dữ liệu lịch sử ít thay đổi | Column store/warehouse | Tối ưu scan, compression và phân tích song song |
| Truy vấn hỗn hợp, vừa point lookup vừa scan lớn | Hybrid hoặc workload isolation | Mỗi đường truy cập dùng cấu trúc phù hợp |
| Query chọn lọc cao trên row store có covering index | Row store có thể đủ tốt | Index có thể đọc ít page và không cần full scan |

### 12.1. Tỷ lệ cột được chọn

Nếu bảng có 50 cột nhưng query chỉ dùng 2 cột, column store có cơ hội giảm lượng dữ liệu đọc. Nếu query dùng 45/50 cột, lợi ích projection giảm; row store có thể cạnh tranh tốt hơn tùy layout, compression và engine.

Không dùng số cột đơn thuần để quyết định. Một cột JSON 2 MB có thể chiếm nhiều bytes hơn 20 cột số nhỏ. Hãy so sánh compressed bytes, uncompressed bytes, row width và số cột thực tế được đọc.

### 12.2. Selectivity và locality

Query lọc còn 0,01% hàng có thể phù hợp với index lookup hoặc partition pruning, kể cả trên row store. Query lọc còn 70% hàng có thể phù hợp với scan tuần tự/columnar scan. Selectivity chỉ là một yếu tố; locality, clustering, index depth và cost model cũng quan trọng.

## 13. Đọc execution plan để nhận biết kiểu truy cập

Khi phân tích plan, tìm các thông tin:

- Table scan, index scan/seek hoặc columnar scan.
- Các cột thực sự được đọc (read schema/projection).
- Predicate được push xuống scan hay còn residual filter.
- Số partition, segment, file hoặc row group được đọc/bỏ qua.
- Rows read so với rows output.
- Logical/physical reads hoặc bytes scanned.
- Compression/decompression và CPU time nếu engine cung cấp.
- Vectorized/batch mode hay row mode.
- Join strategy, exchange/shuffle và aggregate stage.
- Memory grant, spill và temporary I/O.

Tên operator tùy hệ quản trị. SQL Server có thể hiển thị Columnstore Index Scan và batch mode; PostgreSQL thường hiển thị Seq Scan, Index Scan, Bitmap Heap Scan và các node khác; analytic engines có thể hiển thị columnar scan, file scan, row group pruning hoặc vectorized operator. Không thể suy ra toàn bộ physical layout chỉ từ một tên operator.

### 13.1. Estimated rows và actual rows

Optimizer cần ước lượng số hàng đi qua từng operator để chọn scan, join và aggregate. Nếu estimate sai lớn, nó có thể chọn nested loop thay vì hash join, cấp memory không đủ hoặc chọn sai access path. So sánh estimated rows với actual rows và xem statistics, histogram, data skew.

### 13.2. Đo bytes đọc thay vì chỉ thời gian

Thời gian có thể thay đổi vì cache nóng, CPU contention hoặc background workload. Bytes/pages read và rows scanned giúp hiểu lượng công việc thực tế. Hãy lấy metrics theo cùng measurement window và phân biệt logical reads với physical device I/O.

## 14. Ví dụ so sánh hai kiểu truy vấn

### 14.1. Point lookup

```sql
SELECT sale_id, customer_id, sale_time, status, quantity, unit_price
FROM sales
WHERE sale_id = 90000123;
```

Truy vấn tìm một hàng và cần nhiều cột. Row store với primary-key index thường là lựa chọn tự nhiên. Column store có thể cần tra metadata/index rồi đọc nhiều column streams hoặc segment; khả năng này phụ thuộc engine.

### 14.2. Analytical scan

```sql
SELECT region_id, SUM(quantity * unit_price) AS revenue
FROM sales
WHERE sale_time >= TIMESTAMP '2026-10-01 00:00:00'
  AND sale_time <  TIMESTAMP '2026-11-01 00:00:00'
  AND status = 'OK'
GROUP BY region_id;
```

Truy vấn đọc nhiều hàng nhưng ít cột và aggregate theo nhóm. Columnar scan có thể chỉ đọc năm cột cần thiết, dùng min/max hoặc partition pruning, nén dữ liệu và vectorize phép tính. Row store vẫn có thể chạy tốt nếu partition/index/summary phù hợp hoặc dữ liệu cần đọc nhỏ.

## 15. Benchmark row store và column store công bằng

Không thể so sánh hai layout bằng cách chạy một query duy nhất trên dataset khác nhau. Thiết kế benchmark cần kiểm soát:

- Cùng dữ liệu logic, số hàng và phân bố giá trị.
- Cùng query semantics, filter, join và aggregate.
- Cùng freshness requirement và transaction mix.
- Cấu hình hardware, CPU, RAM, storage và network tương đương hoặc được ghi rõ.
- Warm/cold cache state và số lần lặp tương đương.
- Statistics, partitioning, index và compression được ghi nhận.
- Concurrency và query mix gần cùng mục tiêu.
- Kết quả được xác minh giống nhau, kể cả NULL, duplicate và boundary.

### 15.1. Tách benchmark đọc và ghi

Row store và column store có trade-off khác nhau. Cần đo riêng:

- Point lookup p50/p95/p99.
- Range scan và analytical scan latency.
- Bytes read và rows scanned.
- Aggregate throughput.
- Insert throughput và ingestion lag.
- Update/delete latency và background merge/compaction.
- Storage footprint và compression ratio.
- CPU, memory, spill và I/O.

Nếu chỉ đo analytical scan, column store có thể thắng rõ nhưng chưa cho biết hệ thống có phù hợp với transaction ghi nhỏ hay không. Nếu chỉ đo point update, row store có thể thắng nhưng chưa phản ánh workload warehouse.

### 15.2. Warm cache và cold cache

Warm-cache benchmark cho biết hiệu năng khi dữ liệu nóng đã được nạp; cold-cache benchmark cho biết chi phí lần đọc đầu trong điều kiện cache được kiểm soát. Columnar compression có thể làm giảm storage bytes ngay cả khi cache nóng; row store có thể có lợi thế locality cho point lookup.

Restart database không bảo đảm xóa OS page cache hoặc storage cache. Ghi rõ cách chuẩn bị cache và không xóa cache hệ thống production tùy tiện.

### 15.3. Không so sánh chỉ theo bytes lưu trữ

Column store có thể nén tốt hơn nhưng query latency còn phụ thuộc decode CPU, pruning, parallelism và network. Row store có thể lớn hơn nhưng point lookup nhanh. Đo cả storage footprint, bytes scanned, CPU time và latency theo query pattern.

## 16. Quy trình tối ưu workload phân tích

1. **Phân loại query:** point lookup, range scan, full scan, aggregate, join hay báo cáo hỗn hợp.
2. **Xác định dữ liệu cần:** cột output, predicate, join key, group key và kích thước payload.
3. **Đo layout hiện tại:** row/column, partition, index, compression, clustering và working set.
4. **Đọc execution plan:** scan type, projection, pushed filter, rows/bytes read và operator mode.
5. **Xác định chi phí:** storage I/O, CPU decode, memory, shuffle, spill hay network.
6. **Thử tối ưu query:** projection tường minh, predicate sargable, partition pruning và giảm dữ liệu trước join.
7. **Đánh giá cấu trúc:** covering index, columnstore index, materialized view, summary table hoặc analytic replica.
8. **Đo cả đọc và ghi:** xác định write amplification, ingestion lag, update/delete cost và maintenance.
9. **Kiểm chứng kết quả:** đối chiếu output và transaction semantics.
10. **So sánh lặp lại:** giữ cùng dataset, query mix, concurrency, cache state và measurement window.

## 17. Những sai lầm thường gặp

- **Cho rằng column store luôn nhanh hơn:** point lookup và cập nhật nhỏ có thể phù hợp row store hơn.
- **Cho rằng row store luôn phải đọc toàn bộ cột:** covering index, partitioning và engine optimization có thể giảm lượng dữ liệu đọc.
- **Đếm số cột để dự đoán bytes tiết kiệm:** kích thước và compression của từng cột khác nhau.
- **Dùng `SELECT *` trong truy vấn phân tích:** làm mất cơ hội projection pruning.
- **Bỏ qua filter pushdown:** vẫn đọc nhiều row group/partition trước khi lọc.
- **Cho rằng columnar storage không thể cập nhật:** nhiều engine có delta store, delete bitmap hoặc merge, nhưng chi phí khác row store.
- **Bỏ qua ingestion và compaction:** background merge có thể cạnh tranh tài nguyên với query.
- **Chỉ đo query đọc:** không thấy write amplification và chi phí duy trì layout.
- **So sánh hai hệ thống với cache state khác nhau:** kết quả latency thiếu công bằng.
- **Chỉ nhìn thời gian tổng:** không biết bytes scanned, CPU decode, spill hay network là nguyên nhân.
- **Cho rằng columnar index giống base table column store:** index, segment và execution mode có semantics khác nhau theo DBMS.
- **Chuyển toàn bộ OLTP sang warehouse:** có thể vi phạm freshness, transaction hoặc consistency requirement.

## 18. Bài tập tự kiểm tra

### Bài tập 1: Chọn layout cho point lookup

Một API tìm đơn hàng theo primary key, đọc 12 cột và đôi khi cập nhật trạng thái. Bảng có 80 triệu hàng.

**Câu hỏi:** row store hay column store thường phù hợp hơn? Vì sao?

**Gợi ý trả lời:** row store thường phù hợp vì truy vấn tìm ít hàng nhưng cần nhiều thuộc tính và có cập nhật theo hàng. Cần index phù hợp và đo concurrency/lock; column store chỉ nên chọn nếu engine có cơ chế point access phù hợp và workload chứng minh lợi ích.

### Bài tập 2: Chọn layout cho báo cáo

Một báo cáo quét 300 triệu giao dịch nhưng chỉ dùng 4 cột trong bảng 45 cột, sau đó tính tổng theo ngày.

**Câu hỏi:** column store có thể cải thiện ở đâu?

**Gợi ý trả lời:** projection pruning giảm column chunks phải đọc; compression giảm storage bytes; vectorized execution tăng hiệu quả filter và aggregate. Cần kiểm tra partition/row-group pruning, bytes scanned, CPU decode và query latency.

### Bài tập 3: Column store chậm sau ingestion

Sau một đợt nạp dữ liệu lớn, truy vấn phân tích chậm dù số hàng không tăng quá nhiều.

**Câu hỏi:** ngoài CPU và storage, cần kiểm tra gì?

**Gợi ý trả lời:** delta store, delete bitmap, segment merge/compaction, small files, statistics và background maintenance. Dữ liệu mới có thể nằm ở layout chưa tối ưu hoặc khiến reader phải kết hợp nhiều vùng.

### Bài tập 4: Covering index

Row store có truy vấn lọc theo `region_id`, khoảng `sale_time` và output `quantity`, `unit_price`. Một index ghép cùng include columns được đề xuất.

**Câu hỏi:** lợi ích và chi phí cần đo là gì?

**Gợi ý trả lời:** có thể giảm lookup về base table và logical reads. Cần đo kích thước index, write amplification, insert/update latency, maintenance và xem actual plan có dùng covering path hay không.

### Bài tập 5: Row group pruning

Một file columnar có row group A với ngày tháng 1–2, row group B với ngày tháng 10. Truy vấn chỉ đọc tháng 10.

**Câu hỏi:** metadata min/max giúp gì?

**Gợi ý trả lời:** engine có thể bỏ row group A vì min/max không giao với khoảng tháng 10, chỉ đọc B. Hiệu quả phụ thuộc statistics tồn tại và predicate được reader hỗ trợ.

### Bài tập 6: Hybrid architecture

Ứng dụng cần cập nhật đơn hàng tức thời nhưng báo cáo lịch sử có thể trễ 30 giây.

**Câu hỏi:** có thể dùng row store và columnar warehouse cùng lúc không? Cần kiểm soát điều gì?

**Gợi ý trả lời:** có thể giữ OLTP trên row store và replicate/CDC sang warehouse columnar. Cần theo dõi lag, replay, duplicate, schema evolution và định nghĩa freshness; truy vấn yêu cầu read-after-write phải đọc từ nguồn có dữ liệu mới nhất.

### Checklist chọn cách truy cập theo hàng hay theo cột

- [ ] Đã phân loại workload là point lookup, transaction, range scan hay analytical scan.
- [ ] Đã xác định số hàng và số cột thực sự cần.
- [ ] Đã hiểu row-oriented và column-oriented physical locality.
- [ ] Đã kiểm tra projection pruning và predicate pushdown.
- [ ] Đã xem partition/segment/row-group pruning và metadata statistics.
- [ ] Đã đánh giá compression, encoding và CPU decode.
- [ ] Đã kiểm tra vectorized execution, late materialization và spill.
- [ ] Đã xem index, covering index hoặc columnstore index nếu DBMS hỗ trợ.
- [ ] Đã đo cả point lookup, scan, aggregate, insert, update và delete theo workload.
- [ ] Đã đánh giá ingestion lag, delta store, merge/compaction và write amplification.
- [ ] Đã xem xét hybrid OLTP/OLAP và yêu cầu freshness/consistency.
- [ ] Đã so sánh bytes read, rows scanned, CPU, memory, I/O và p95/p99.
- [ ] Đã kiểm chứng kết quả và giữ cùng điều kiện benchmark.

Row store đặt các cột của một hàng gần nhau nên thường thuận lợi cho transaction và point lookup; column store đặt các giá trị cùng cột gần nhau nên thường thuận lợi cho scan nhiều hàng nhưng chỉ dùng ít cột, compression và vectorized analytics. Hiệu năng thực tế còn phụ thuộc projection, predicate, partitioning, index, data ordering, cache và chi phí ghi. Hãy chọn layout theo query mix, đọc execution plan, đo bytes/rows thực tế cùng cả workload đọc lẫn ghi, rồi kiểm chứng freshness và tính đúng đắn trước khi thay đổi kiến trúc.
