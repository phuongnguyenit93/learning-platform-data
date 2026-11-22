# Truy vấn chậm do kế hoạch đổi sau tăng trưởng dữ liệu

Một truy vấn có thể chạy ổn định trong nhiều tháng rồi đột ngột chậm sau khi bảng tăng từ vài trăm nghìn lên hàng chục triệu hàng. Một nguyên nhân thường gặp là optimizer chọn execution plan khác vì thống kê, phân bố dữ liệu hoặc ước lượng cardinality đã thay đổi. Kế hoạch cũ có thể từng phù hợp với dữ liệu nhỏ; khi dữ liệu tăng, cùng cách truy cập có thể đọc quá nhiều trang, join sai thứ tự, chọn nested loop cho tập lớn hoặc tạo sort/hash spill xuống storage.

Trong module **DATABASE_PERFORMANCE**, việc tối ưu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Chẩn đoán sự cố** tập trung vào cách tìm nguyên nhân của suy giảm hiệu năng trong môi trường đang vận hành. Bài học này hướng dẫn điều tra trường hợp truy vấn chậm do execution plan thay đổi sau tăng trưởng dữ liệu: xác nhận plan regression, so sánh estimated và actual rows, kiểm tra statistics và data skew, đánh giá access path/join/memory, rồi thử điều chỉnh có kiểm soát và xác minh dưới tải đại diện.

Sau bài học, người học có thể:

- Phân biệt truy vấn chậm do plan regression với truy vấn chậm vì lượng công việc tăng nhưng plan không đổi.
- Thu thập SQL, bind parameters, execution plan, runtime metrics và thời điểm plan thay đổi.
- So sánh estimated rows với actual rows tại từng operator.
- Giải thích tác động của statistics, histograms, data skew, correlation và parameter sensitivity.
- Nhận diện các thay đổi về index scan, table scan, join order, join algorithm, sort, hash và parallelism.
- Đánh giá memory grant, work area và spill khi cardinality hoặc row width bị ước lượng sai.
- Chọn cách xử lý phù hợp: cập nhật statistics, bổ sung thống kê đa cột, sửa index/query hoặc quản lý plan.
- Áp dụng quy trình điều tra an toàn, giữ baseline và rollback được.
- Đo kết quả trước/sau bằng latency, CPU, I/O, logical reads, waits và concurrency.
- Ngăn tái diễn bằng Query Store/plan history, cảnh báo và kiểm soát tăng trưởng dữ liệu.

## 1. Nhận diện vấn đề: dữ liệu tăng và truy vấn đột nhiên chậm

### 1.1. Triệu chứng điển hình

Một plan regression thường biểu hiện qua một hoặc nhiều dấu hiệu:

- p95 hoặc p99 của một query fingerprint tăng mạnh dù ứng dụng không thay đổi.
- Cùng một SQL có nhiều plan khác nhau trong một khoảng thời gian.
- Logical reads, physical reads hoặc CPU tăng bất thường.
- Số hàng trung gian tăng vượt dự kiến.
- Query chuyển từ index seek/range scan sang scan rộng, hoặc ngược lại chọn index không phù hợp.
- Join order hoặc join algorithm thay đổi.
- Sort/hash operation bắt đầu spill xuống temporary storage.
- Một số giá trị bind chạy nhanh, giá trị khác rất chậm.
- Query Store, plan history hoặc performance schema cho thấy thời điểm plan mới xuất hiện trùng với thời điểm latency tăng.

Không phải cứ thấy table scan là có lỗi. Khi bảng nhỏ hoặc predicate trả về phần lớn dữ liệu, scan có thể rẻ hơn hàng triệu lần lookup qua index. Cần so sánh chi phí thực tế và số hàng trả về.

### 1.2. Phân biệt ba tình huống

**Tình huống A: Plan thay đổi và plan mới kém hơn.**  
SQL và dữ liệu đầu vào tương tự, nhưng execution plan có operator hoặc thứ tự join khác; runtime tăng rõ. Đây là plan regression theo nghĩa trực tiếp.

**Tình huống B: Plan gần như không đổi nhưng lượng công việc tăng.**  
Số hàng phù hợp tăng theo dữ liệu, thời gian tăng tương ứng. Plan có thể vẫn hợp lý; cần xem lại yêu cầu, partitioning, index hoặc giới hạn kết quả.

**Tình huống C: Plan thay đổi nhưng không phải nguyên nhân chính.**  
Latency tăng do storage chậm, lock wait, network, CPU contention hoặc concurrency; plan mới chỉ xuất hiện cùng thời điểm. Cần phân tách elapsed time với CPU time, wait time và thời gian fetch.

Một chẩn đoán đúng phải chứng minh mối liên hệ giữa thay đổi plan và chi phí thực thi. Chỉ dựa vào thời điểm trùng nhau chưa đủ.

### 1.3. Ví dụ về tác động của tăng trưởng

Giả sử bảng orders tăng từ 500 nghìn lên 80 triệu hàng. Query lấy đơn hàng của một tenant trong 24 giờ gần nhất:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
  AND status = 'PAID';
~~~

Khi dữ liệu nhỏ, optimizer có thể chọn index phù hợp và đọc vài nghìn hàng. Sau tăng trưởng:

- Một số tenant có số đơn lớn hơn nhiều tenant khác.
- Tỷ lệ PAID thay đổi.
- Dữ liệu mới tập trung trong một khoảng ngày.
- Statistics chưa phản ánh phân bố mới.
- Một index hiện tại không bao phủ đủ cột cần thiết.
- Optimizer ước lượng thấp số hàng rồi chọn nested loop với hàng triệu lần lookup.

Kết quả có thể là số logical reads, CPU và elapsed time tăng rất mạnh. Cần xem plan thực tế và cardinality ở từng bước để biết nguyên nhân nào đang xảy ra.

### 1.4. Bắt đầu từ bằng chứng có thể so sánh

Trước khi thay đổi cấu hình, hãy lưu:

- SQL text và query fingerprint.
- Bind values đại diện, bao gồm giá trị phổ biến và giá trị cực trị.
- Plan hiện tại và plan trước đó nếu có.
- Estimated rows và actual rows.
- Elapsed time, CPU time, logical reads, physical reads.
- Wait events hoặc wait statistics.
- Số lần thực thi và concurrency.
- Thời điểm deploy, statistics refresh, index maintenance hoặc thay đổi cấu hình.
- Kích thước bảng/index và phân bố dữ liệu liên quan.

Không lưu dữ liệu cá nhân hoặc bí mật trong log chẩn đoán không được bảo vệ. Với bind values nhạy cảm, dùng mẫu đã ẩn danh nhưng vẫn giữ đặc tính phân bố cần thiết.

## 2. Execution plan thay đổi như thế nào?

### 2.1. Optimizer lựa chọn kế hoạch dựa trên ước lượng

Optimizer thường không thử chạy mọi kế hoạch để chọn kế hoạch nhanh nhất. Nó tạo các phương án và ước lượng chi phí dựa trên:

- Số hàng dự kiến (cardinality).
- Phân bố giá trị và độ chọn lọc predicate.
- Số trang/khối dữ liệu và index.
- Chi phí CPU và I/O.
- Khả năng sort/hash trong bộ nhớ.
- Chi phí truyền hàng giữa các operator.
- Parallelism và các giới hạn tài nguyên.
- Tham số bind hoặc thông tin về kiểu dữ liệu.

Statistics là một phần đầu vào quan trọng. Khi bảng tăng trưởng hoặc phân bố thay đổi, statistics cũ có thể khiến optimizer ước lượng sai và chọn plan không còn phù hợp.

### 2.2. Cardinality là số hàng optimizer dự đoán

Cardinality estimate là số hàng mà optimizer dự đoán một operator sẽ nhận hoặc phát ra. Sai số ở một operator có thể lan truyền sang các operator phía trên.

Ví dụ:

~~~text
Actual rows:      2,400,000
Estimated rows:      1,200
Estimation error:    2,000x
~~~

Nếu optimizer nghĩ một đầu vào chỉ có 1.200 hàng, nó có thể chọn nested loop và lookup theo từng hàng. Khi thực tế có 2,4 triệu hàng, chi phí lookup lặp lại trở nên rất lớn.

Không phải mọi sai số cardinality đều gây chậm. Cần xem operator chịu ảnh hưởng, vị trí sai số xuất hiện đầu tiên và plan alternative mà optimizer đã chọn.

### 2.3. Estimated rows và actual rows

Khi có execution plan thực tế, so sánh số hàng ước lượng với số hàng thật tại từng node. Một cách tính sai số tương đối:

\[
ErrorFactor =
\frac{\max(EstimatedRows, ActualRows)}
{\max(\min(EstimatedRows, ActualRows), 1)}
\]

Ví dụ, estimated 10.000 và actual 500.000 tạo sai số 50 lần. Hệ số này chỉ là chỉ báo; với parallel plan hoặc operator được gọi nhiều lần, cần hiểu cách engine báo actual rows (mỗi loop hay tổng toàn bộ).

Hãy tìm **điểm sai lệch đầu tiên** trong plan từ dưới lên. Nếu node scan đã ước lượng sai lớn, các join phía trên có thể chỉ là hậu quả. Sửa node gốc thường hiệu quả hơn ép operator phía trên.

### 2.4. Đọc plan theo luồng dữ liệu

Khi đọc plan, lần theo:

1. Nguồn hàng: table scan, index scan/seek, partition scan.
2. Filter: predicate được áp dụng ở đâu, có được pushdown không?
3. Join: thứ tự join và thuật toán nào được dùng?
4. Sort/aggregate: có cần materialize nhiều hàng không?
5. Memory: hash/sort có spill không?
6. Output: số hàng cuối, số cột và kích thước kết quả.

Cần chú ý cardinality ở từng ranh giới. Một plan có index seek vẫn có thể chậm nếu seek trả về quá nhiều hàng hoặc lặp lại hàng triệu lần bên trong nested loop.

### 2.5. Plan cost không phải thời gian thực tế

Cost của optimizer là đơn vị nội bộ để so sánh phương án, không phải milliseconds. Không kết luận plan có cost 10.000 chắc chắn chậm gấp đôi plan cost 5.000.

So sánh runtime trên cùng dữ liệu, bind parameters, cache state và mức concurrency. Cost hữu ích để hiểu optimizer đánh đổi I/O/CPU như thế nào; runtime metrics mới cho biết người dùng thực sự chịu chi phí gì.

## 3. Vì sao tăng trưởng dữ liệu làm plan thay đổi?

### 3.1. Thay đổi quy mô và ngưỡng chọn access path

Với bảng nhỏ, table scan có thể đọc ít page hơn so với index lookup. Khi bảng lớn hơn, index có thể trở nên có lợi nếu predicate chọn lọc cao. Nhưng nếu predicate trả về phần lớn bảng, scan tuần tự vẫn có thể rẻ hơn.

Optimizer có thể chuyển giữa:

- Table scan và index scan.
- Index seek/range scan và scan rộng.
- Index-only/covering access và lookup về bảng.
- Partition pruning và quét nhiều partition.
- Serial và parallel plan.

Sự thay đổi này có thể hợp lý hoặc không, tùy độ chọn lọc, row width, clustering/locality và chi phí I/O.

### 3.2. Statistics không theo kịp dữ liệu

Statistics có thể được tạo khi bảng còn nhỏ hoặc trước khi một đợt bulk load diễn ra. Nếu số hàng, số distinct values hoặc phân bố thay đổi nhưng statistics chưa cập nhật, optimizer tiếp tục dùng mô hình cũ.

Một số engine tự động cập nhật statistics theo ngưỡng; ngưỡng và hành vi phụ thuộc phiên bản, loại statistics, partition và cấu hình. Bulk load, ETL, delete lớn hoặc dữ liệu tăng nhanh có thể khiến thống kê không còn đại diện dù auto update đang bật.

### 3.3. Data skew: phân bố lệch

Data skew xảy ra khi một số giá trị chiếm tỷ trọng rất lớn. Ví dụ:

- Tenant A có 40% tổng số đơn.
- Một status chiếm 95% hàng.
- Một vùng địa lý chứa phần lớn khách hàng.
- Một ngày chiến dịch có lượng giao dịch cao gấp nhiều lần ngày thường.

Statistics chỉ lưu thông tin tóm tắt; nếu histogram hoặc sampling không mô tả đủ giá trị lệch, optimizer có thể ước lượng sai cho các giá trị cụ thể.

Một query với tenant nhỏ có thể chạy tốt bằng index seek; cùng query với tenant lớn có thể cần scan hoặc hash join. Một plan duy nhất có thể không tối ưu cho mọi bind value.

### 3.4. Correlation giữa các cột

Giả sử country_code và region_code có quan hệ phụ thuộc. Nếu optimizer giả định hai predicate độc lập, nó có thể nhân selectivity riêng lẻ và ước lượng số hàng thấp hơn nhiều so với thực tế.

Ví dụ:

~~~sql
SELECT *
FROM customers
WHERE country_code = 'VN'
  AND region_code = 'HCM';
~~~

Nếu gần như mọi khách hàng ở HCM đều có country_code = VN, hai predicate có correlation mạnh. Statistics một cột có thể không đủ để mô tả mối quan hệ này.

Tùy engine, có thể dùng extended/multicolumn statistics, column group statistics hoặc histogram thích hợp. Cần tạo đúng nhóm cột có quan hệ và xác nhận optimizer thực sự sử dụng chúng.

### 3.5. Row width thay đổi

Tăng trưởng không chỉ là số hàng. Giá trị trong cột có thể dài hơn, JSON/LOB tăng kích thước hoặc schema thay đổi làm row width trung bình tăng.

Điều này ảnh hưởng:

- Số page phải đọc.
- Số hàng mỗi page.
- Memory grant/work area cần thiết.
- Kích thước sort/hash.
- Network transfer.
- Số batch cần truyền đến client.

Nếu plan giữ nguyên nhưng row width tăng, query vẫn có thể chậm. Đây là lý do phải đo payload và page reads cùng với cardinality.

### 3.6. Index và partition thay đổi theo thời gian

Index có thể không còn phù hợp với workload mới. Một index từng hỗ trợ predicate chọn lọc cao có thể không còn hữu ích khi phân bố thay đổi. Index fragmentation, bloat hoặc page density thấp cũng có thể tăng chi phí đọc, tùy engine.

Partitioning có thể giúp giới hạn phạm vi scan khi predicate khớp partition key. Nhưng nếu predicate không có partition key hoặc partition pruning không xảy ra, query vẫn có thể quét nhiều partition. Tăng số partition không tự động làm truy vấn nhanh hơn.

### 3.7. Bind parameter sensitivity

Một số optimizer lập kế hoạch dựa trên bind parameter hoặc giá trị đầu tiên được sniff/peek. Nếu giá trị đầu tiên thuộc tenant nhỏ, plan có thể tối ưu cho tập nhỏ. Sau đó cùng plan được tái sử dụng cho tenant lớn và trở nên rất chậm.

Hiện tượng này được gọi theo tên khác nhau tùy engine như parameter sniffing, bind peeking hoặc parameter-sensitive plan. Cần kiểm tra plan cache và runtime theo nhóm bind value trước khi kết luận.

### 3.8. Plan cache và invalidation

Plan có thể thay đổi sau:

- Statistics refresh.
- Index create/drop/rebuild.
- Schema change.
- Engine upgrade hoặc compatibility level change.
- Plan cache eviction/recompile.
- Bind value khác làm optimizer tạo plan khác.
- Thay đổi optimizer settings hoặc session settings.

Ghi lại các sự kiện này theo thời gian giúp tìm được mốc plan thay đổi. Không xóa toàn bộ plan cache như bước chẩn đoán đầu tiên vì hành động đó có thể gây compile storm và làm thay đổi hành vi của nhiều query khác.

## 4. Đọc execution plan để tìm nguyên nhân gốc

### 4.1. Thu thập actual execution plan

Estimated plan cho biết optimizer dự đoán gì. Actual plan bổ sung số hàng và runtime information sau khi chạy. Tùy engine, actual plan có thể gồm số lần operator được gọi, thời gian, logical reads, memory grant, spill và wait.

Khi lấy actual plan:

- Dùng đúng SQL và kiểu bind như request gặp lỗi.
- Ghi lại bind value đại diện, không chỉ một giá trị thuận lợi.
- Không chạy query cực nặng trên production chỉ để lấy plan nếu có thể gây quá tải.
- Ưu tiên Query Store, monitoring hoặc plan capture sẵn có.
- Nếu phải chạy lại, chọn thời điểm và giới hạn an toàn; dùng read-only transaction khi phù hợp.
- Ghi nhận cache state vì cold cache và warm cache có thể tạo thời gian khác nhau.

Một actual plan được lấy với bind value khác có thể không tái hiện vấn đề. Đối với query nhạy tham số, cần so sánh nhiều nhóm giá trị.

### 4.2. Tìm điểm sai lệch đầu tiên

Đọc plan từ các leaf operator lên phía trên. Tại mỗi node, so sánh:

- Estimated rows và actual rows.
- Số lần thực thi (loops/executions).
- Rows per execution và tổng rows.
- Logical reads hoặc buffer accesses.
- Thời gian CPU và elapsed.
- Rows bị loại bởi filter.
- Số hàng được đưa sang operator kế tiếp.

Ví dụ:

| Operator | Estimated rows | Actual rows | Nhận xét |
|---|---:|---:|---|
| Index range scan | 2.000 | 1.800.000 | Sai lệch đầu tiên rất lớn |
| Nested loop input | 2.000 | 1.800.000 | Sai lệch được truyền lên |
| Lookup table | 1 | 1 mỗi loop | Bị lặp hàng triệu lần |
| Final output | 1.500 | 1.620.000 | Plan đánh giá thấp toàn bộ công việc |

Trong ví dụ này, nested loop có thể không phải nguyên nhân gốc. Nó trở nên đắt vì input thực tế lớn hơn 900 lần ước lượng. Hãy điều tra vì sao index range scan ước lượng thấp trước khi ép đổi join algorithm.

### 4.3. Đừng nhầm actual rows với rows per loop

Một số engine hiển thị actual rows trung bình mỗi lần operator chạy, cùng số loops. Một operator có actual rows 1 nhưng loops 2 triệu có thể đã phát ra tổng cộng 2 triệu hàng.

Khi đọc plan, cần biết công cụ đang hiển thị:

- Hàng mỗi lần gọi.
- Tổng hàng qua mọi lần gọi.
- Thời gian trung bình mỗi lần.
- Tổng thời gian tích lũy.
- Thời gian operator có bao gồm thời gian của child hay không.

Không cộng thời gian của mọi node một cách máy móc vì nhiều plan báo thời gian lồng nhau hoặc operator chạy pipeline đồng thời.

### 4.4. Nhận diện access path không phù hợp

Một số dấu hiệu cần điều tra:

- Index seek/range scan trả về phần lớn bảng.
- Index lookup/key lookup được gọi rất nhiều lần.
- Table scan đọc bảng lớn dù predicate chọn lọc cao.
- Index condition không được pushdown, filter được áp dụng muộn.
- Partition pruning không xảy ra.
- Function hoặc implicit conversion trên cột làm mất khả năng dùng index.
- Index order không phù hợp với predicate và ORDER BY.
- Index-only scan không thể dùng vì thiếu cột hoặc visibility condition.

Ví dụ predicate:

~~~sql
WHERE CAST(created_at AS DATE) = :order_day
~~~

Có thể khiến optimizer khó dùng index range trên created_at tùy engine. Viết khoảng nửa mở thường thuận lợi hơn:

~~~sql
WHERE created_at >= :day_start
  AND created_at < :next_day_start
~~~

Cần xác minh kiểu timezone, precision và semantics của ngày để không thay đổi kết quả.

### 4.5. Nhận diện join order và join algorithm

Nested loop thường phù hợp khi một đầu vào nhỏ và đầu vào kia có index lookup hiệu quả. Nếu outer input thực tế lớn, số lần lookup tăng theo số hàng.

Hash join thường phù hợp với tập lớn khi có thể xây hash table trong ngân sách bộ nhớ. Nếu estimate sai hoặc memory grant thấp, hash join có thể spill.

Merge join có thể hiệu quả khi hai đầu vào đã được sắp xếp hoặc có thể đọc theo thứ tự phù hợp; nếu cần sort lớn, chi phí sort cần được tính vào.

Không có thuật toán join nào luôn nhanh nhất. Cần so sánh cardinality, số lần lookup, memory, sort và I/O của từng plan.

### 4.6. Sort, hash và memory spill

Khi sort hoặc hash không vừa bộ nhớ được cấp, engine có thể ghi các run/partition trung gian xuống temporary storage rồi đọc lại. Spill làm tăng I/O và latency, đặc biệt với query lớn hoặc nhiều query đồng thời.

Dấu hiệu:

- Plan ghi nhận spill hoặc disk-based sort/hash.
- Tempdb/temp tablespace usage tăng.
- Physical reads/writes tăng.
- Query runtime tăng khi concurrency cao.
- Memory grant hoặc work area khác biệt giữa plan cũ và mới.

Spill có thể do row count estimate thấp, row width tăng, memory grant cap, cạnh tranh memory hoặc cấu hình work area. Không tăng memory toàn cục ngay khi thấy spill; trước hết xác định operator, query và tổng nhu cầu dưới concurrency.

### 4.7. Parallelism và chi phí phân phối

Khi bảng tăng, optimizer có thể chuyển sang parallel plan. Điều này có thể giảm elapsed time nhưng tăng tổng CPU, memory và I/O. Parallel plan cũng có thể bị chậm do:

- Worker imbalance vì data skew.
- Exchange/repartition overhead.
- Worker chờ nhau.
- Resource semaphore hoặc giới hạn worker.
- Một số partition/nhóm key nặng hơn phần còn lại.

Đo cả elapsed time và total CPU. Một query nhanh hơn một chút nhưng tiêu thụ CPU gấp nhiều lần có thể làm workload tổng thể xấu đi.

## 5. Statistics: kiểm tra chất lượng và cập nhật đúng cách

### 5.1. Statistics thường chứa thông tin gì?

Tùy DBMS, statistics có thể bao gồm:

- Tổng số hàng và số page/block.
- Number of distinct values.
- Null fraction.
- Minimum/maximum value.
- Histogram hoặc frequency distribution.
- Average column width.
- Correlation hoặc thông tin đa cột.
- Sampling metadata và thời điểm cập nhật.

Optimizer dùng các số liệu này để ước lượng selectivity và cardinality. Statistics không phải bản sao đầy đủ của dữ liệu; nó là mô hình tóm tắt.

### 5.2. Kiểm tra statistics có cũ hay không

Xem:

- Thời điểm cập nhật gần nhất.
- Số hàng thay đổi kể từ lần cập nhật.
- Auto statistics có bật và chạy thành công không.
- Bulk load hoặc ETL có bỏ qua refresh không.
- Statistics của partition và global table có đồng bộ không.
- Histogram có phản ánh giá trị phổ biến và giá trị hiếm không.
- Sampling rate có đủ cho phân bố lệch không.

Không kết luận statistics cũ chỉ dựa vào timestamp. Nếu dữ liệu ít thay đổi hoặc phân bố ổn định, statistics cũ vẫn có thể đủ tốt. Ngược lại, một đợt load nhỏ nhưng thêm một giá trị cực kỳ phổ biến có thể làm phân bố thay đổi đáng kể.

### 5.3. Cập nhật statistics có kiểm soát

Quy trình:

1. Lưu plan và runtime baseline.
2. Xác định bảng/cột có estimate sai.
3. Kiểm tra statistics hiện tại và mức thay đổi dữ liệu.
4. Chạy cập nhật statistics cho đối tượng liên quan bằng cơ chế của engine.
5. Để optimizer tạo plan mới hoặc recompile query phù hợp.
6. Chạy cùng bộ bind parameters và workload đại diện.
7. So sánh plan, logical reads, CPU, elapsed, spill và concurrency.
8. Giữ hoặc rollback theo kết quả.

Statistics refresh có thể làm plan thay đổi cho nhiều query khác cùng sử dụng bảng. Cần đánh giá phạm vi ảnh hưởng, đặc biệt trên bảng dùng chung.

### 5.4. Histogram và sampling

Histogram giúp mô tả phân bố không đều. Nếu histogram quá thưa hoặc sampling bỏ qua một giá trị hiếm nhưng quan trọng, estimate có thể sai.

Tăng sample size hoặc histogram buckets có thể cải thiện estimate trong một số trường hợp, nhưng làm tăng thời gian cập nhật và metadata. Cần xem hỗ trợ của DBMS và workload query thực tế; không đặt mức cao nhất cho mọi cột.

### 5.5. Multicolumn/extended statistics

Khi các predicate trên nhiều cột có tương quan, statistics đơn cột có thể không đủ. Một nhóm statistics đa cột có thể giúp optimizer hiểu quan hệ giữa các cột hoặc distinct combination.

Ví dụ query lọc tenant_id, status và region_id. Nếu status phân bố khác nhau theo tenant, ước lượng độc lập từng cột có thể sai. Hãy xác định nhóm cột có correlation và tạo extended statistics theo engine.

Không tạo statistics group cho mọi tổ hợp cột. Chọn theo query có tần suất cao và sai số cardinality được chứng minh.

### 5.6. Partition statistics

Với partitioned table, một số engine duy trì statistics ở cấp partition và cấp toàn bảng. Một partition mới có thể chứa dữ liệu rất khác các partition cũ. Global statistics có thể che giấu skew theo partition; local statistics có thể không đủ khi query đọc nhiều partition.

Kiểm tra partition pruning, local/global statistics, incremental statistics và hành vi optimizer ở đúng phiên bản engine. Sau khi attach/load partition, xác minh statistics được cập nhật hoặc được kế thừa theo cách dự kiến.

## 6. Parameter sensitivity và nhiều nhóm dữ liệu

### 6.1. Vì sao cùng một SQL có thể cần nhiều plan?

Một query lọc theo tenant có thể trả 10 hàng với tenant nhỏ và 10 triệu hàng với tenant lớn. Một plan dùng nested loop và index lookup có thể rất tốt cho tenant nhỏ nhưng tệ cho tenant lớn. Plan dùng hash join hoặc scan có thể phù hợp với tenant lớn nhưng lãng phí cho tenant nhỏ.

Nếu engine tái sử dụng một plan cho mọi bind value, query có thể có hiệu năng không ổn định dù statistics tổng thể tương đối chính xác.

### 6.2. Lấy mẫu bind value có chủ đích

Phân nhóm bind value theo selectivity hoặc phân bố thực tế:

- Nhóm hiếm: trả rất ít hàng.
- Nhóm trung bình: trả lượng hàng điển hình.
- Nhóm phổ biến: trả nhiều hàng.
- Giá trị biên: ngày cao điểm, tenant lớn, trạng thái chiếm tỷ lệ cao.

Với từng nhóm, ghi lại plan, estimated/actual rows, CPU, logical reads, elapsed và p95/p99. Không chỉ kiểm thử một bind value đầu tiên hoặc giá trị trung bình.

### 6.3. Các cách xử lý parameter sensitivity

Tùy engine, có thể cân nhắc:

- Cho optimizer tạo nhiều plan phù hợp với nhóm parameter.
- Dùng cơ chế parameter-sensitive plan hoặc adaptive cursor sharing nếu được hỗ trợ.
- Tách query path cho nhóm dữ liệu có selectivity khác biệt rõ.
- Recompile có chọn lọc khi chi phí compile thấp hơn thiệt hại do plan sai.
- Dùng option tối ưu theo giá trị trung bình chỉ khi workload thực sự phù hợp.
- Dùng hint/plan guide như biện pháp có kiểm soát, có thời hạn và có baseline.

Không dùng local variable hoặc biến trung gian để che bind value một cách máy móc. Việc làm optimizer mất thông tin có thể khiến estimate tệ hơn và tạo plan trung bình không tốt cho nhóm nào.

### 6.4. Chia query path theo workload

Nếu hai nhóm tham số có đặc tính rất khác nhau, có thể tách thành hai câu query hoặc hai procedure path có cùng semantics:

- Query A dành cho tenant nhỏ, có thể dùng index seek và nested loop.
- Query B dành cho tenant lớn, có thể dùng scan/parallel/hash join.

Điều kiện tách phải ổn định, dựa trên dữ liệu hoặc thống kê đã đo. Cần tránh hard-code một ngưỡng số hàng không có cơ chế cập nhật khi workload thay đổi.

### 6.5. Bind type và implicit conversion

Kiểu dữ liệu của bind parameter phải tương thích với kiểu cột. Nếu cột là bigint nhưng ứng dụng bind chuỗi, hoặc cột có collation/charset khác, DBMS có thể thực hiện implicit conversion trên cột hoặc chọn estimate khác.

Kiểm tra:

- Kiểu bind trong driver.
- Precision/scale của decimal.
- Độ dài và charset của string.
- Timezone và precision của timestamp.
- Collation và case sensitivity.
- Plan có CONVERT/CAST trên cột hay không.

Dùng đúng kiểu bind giúp predicate có thể dùng index và optimizer có thông tin phù hợp.

## 7. Dấu hiệu theo DBMS và công cụ quan sát

Tên view, cú pháp và hành vi thay đổi theo phiên bản. Luôn dùng tài liệu tương ứng với engine đang chạy và quyền truy cập hiện có.

### 7.1. PostgreSQL

Các điểm cần kiểm tra:

- EXPLAIN (ANALYZE, BUFFERS) để so sánh estimated rows, actual rows, loops và buffer activity.
- pg_stat_statements để tìm query có total time, mean time hoặc calls tăng.
- pg_stats để xem n_distinct, most_common_vals, histogram_bounds và correlation.
- Statistics target của cột có phân bố lệch.
- Extended statistics cho dependencies, ndistinct hoặc multivariate MCV khi predicate có tương quan.
- Autoanalyze có chạy sau bulk load và dữ liệu tăng nhanh không.
- Generic plan và custom plan khi prepared statement có parameter sensitivity.

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at < TIMESTAMP '2026-11-02 00:00:00'
  AND status = 'PAID';
~~~

EXPLAIN ANALYZE thực thi query. Với query ghi hoặc query nặng, phải cân nhắc tác động và dùng transaction rollback hoặc môi trường phù hợp. BUFFERS giúp quan sát buffer hits/reads; actual time và rows giúp đối chiếu estimate.

Có thể cập nhật statistics có chọn lọc bằng ANALYZE trên bảng hoặc cột. Trước khi tăng statistics target, xác định cột và query có sai số; mức cao hơn tăng chi phí thu thập và lưu statistics.

### 7.2. SQL Server

Các điểm cần kiểm tra:

- Actual execution plan với actual rows, estimated rows, executions và warning.
- Query Store để xem plan history, runtime statistics và thời điểm regression.
- sys.dm_exec_query_stats, sys.dm_exec_query_plan và các DMV liên quan để xem thống kê runtime/cache.
- Statistics properties, last updated, rows sampled và modification counter.
- Histograms qua DBCC SHOW_STATISTICS.
- Auto update statistics, async update và threshold behavior theo compatibility/version.
- Parameter sniffing và parameter-sensitive plan optimization ở các phiên bản hỗ trợ.
- Memory grant, spill warning, tempdb và wait statistics.

Query Store có thể giúp xác định plan nào bắt đầu chậm và so sánh runtime theo thời gian. Plan forcing có thể là biện pháp giảm thiểu tạm thời nếu plan tốt cũ còn phù hợp, nhưng cần theo dõi vì dữ liệu tiếp tục tăng có thể khiến plan đó trở nên tệ.

Cập nhật statistics có thể dùng UPDATE STATISTICS hoặc sp_updatestats theo phạm vi phù hợp. Tránh cập nhật toàn bộ database không có kế hoạch vì có thể tạo nhiều compile/recompile và thay đổi plan của workload khác.

### 7.3. MySQL

Các điểm cần kiểm tra:

- EXPLAIN FORMAT=JSON hoặc EXPLAIN ANALYZE trên phiên bản hỗ trợ.
- estimated rows, actual rows, filtered và chosen key.
- Performance Schema và sys schema để xác định digest có latency/calls cao.
- ANALYZE TABLE và histogram khi phù hợp.
- InnoDB table/index statistics, persistent statistics và sampling configuration.
- Optimizer trace khi cần hiểu vì sao một access path bị loại.
- Index cardinality và phân bố dữ liệu thực tế.

EXPLAIN ANALYZE thực thi statement để thu actual timing; kiểm tra hỗ trợ và tác động theo phiên bản. ANALYZE TABLE cập nhật statistics nhưng plan sau đó có thể thay đổi cho nhiều query. Chạy trên thời điểm thích hợp và so sánh trước/sau.

### 7.4. Oracle Database

Các điểm cần kiểm tra:

- Actual plan và row-source statistics qua DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST khi statistics được thu thập.
- V$SQL và AWR/ASH nếu được cấp phép để xem plan hash, executions, elapsed time, buffer gets và wait profile.
- DBA_TAB_STATISTICS/DBA_TAB_COL_STATISTICS và histogram.
- Pending statistics để thử đánh giá trước khi publish trong môi trường hỗ trợ.
- Column group statistics cho predicate có correlation.
- Bind peeking, adaptive cursor sharing và child cursor.
- SQL Plan Management/baseline để quản lý plan theo quy trình.

Không giả định mọi môi trường có license hoặc quyền dùng AWR/ASH. Dùng công cụ được cấp phép và quyền truy cập hợp lệ. DBMS_XPLAN cần actual row-source statistics phù hợp; estimated plan đơn thuần không thay thế số liệu runtime.

### 7.5. So sánh nhanh công cụ

| Mục tiêu | PostgreSQL | SQL Server | MySQL | Oracle |
|---|---|---|---|---|
| Plan thực tế | EXPLAIN ANALYZE | Actual execution plan | EXPLAIN ANALYZE nếu hỗ trợ | DISPLAY_CURSOR với row-source stats |
| Query history | pg_stat_statements | Query Store/DMV | Performance Schema | V$SQL, AWR/ASH nếu có quyền/license |
| Statistics | pg_stats, ANALYZE | Statistics/UPDATE STATISTICS | Persistent stats, ANALYZE TABLE | Dictionary statistics, DBMS_STATS |
| Correlation | Extended statistics | Multi-column statistics | Histogram/cost model tùy version | Column group statistics |
| Plan control | Plan management tùy extension/quy trình | Query Store forcing/guide | Hint tùy version | SQL Plan Management |

## 8. Các biện pháp khắc phục theo nguyên nhân

### 8.1. Statistics stale hoặc thiếu đại diện

Khi actual rows lệch mạnh và dữ liệu đã thay đổi:

1. Xác định bảng/cột gây sai số đầu tiên.
2. Xác minh statistics age, sampling và modification.
3. Cập nhật statistics có mục tiêu.
4. Với skew, kiểm tra histogram và statistics target.
5. Với correlation, cân nhắc extended/multicolumn statistics.
6. Re-run query với cùng bind value và đo lại.
7. Theo dõi các query khác dùng chung statistics.

Không refresh statistics vô điều kiện mỗi khi query chậm. Nếu estimate đã sát actual rows, nguyên nhân có thể nằm ở access path, I/O, lock hoặc memory pressure.

### 8.2. Index không còn phù hợp

Tăng trưởng có thể khiến index cũ không còn phục vụ predicate và order tốt. Xem lại:

- Cột equality predicate đứng trước cột range/order theo quy tắc phù hợp engine.
- Selectivity và data distribution.
- Có cần INCLUDE/covering columns không.
- Lookup về bảng có bị lặp quá nhiều không.
- Index có dư thừa hoặc write overhead quá lớn không.
- Partition key có được sử dụng để pruning không.

Ví dụ một index ghép có thể được cân nhắc:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Đây chỉ là ví dụ để phân tích, không phải khuyến nghị tạo index ngay. Cần kiểm tra workload đọc/ghi, kích thước index, selectivity, column order và execution plan. Index mới làm tăng storage, write amplification và chi phí bảo trì.

### 8.3. Query predicate làm mất khả năng dùng index

Tránh biến đổi cột được index nếu engine không thể dùng expression index phù hợp:

~~~sql
-- Có thể hạn chế range access trên created_at
WHERE DATE(created_at) = :day
~~~

Có thể viết:

~~~sql
WHERE created_at >= :day_start
  AND created_at < :next_day_start
~~~

Nếu nghiệp vụ cần biểu thức, cân nhắc generated/computed column hoặc expression index khi engine hỗ trợ. Kiểm tra semantics NULL, timezone, collation và precision.

### 8.4. Join algorithm không phù hợp

Nếu nested loop bị đắt vì outer input lớn, trước tiên sửa cardinality estimate. Sau đó đánh giá:

- Index lookup có thật sự cần thiết?
- Hash join có phù hợp và đủ memory không?
- Join order có giảm intermediate rows không?
- Có thể filter sớm hơn mà giữ nguyên semantics?
- Statistics đa cột có cải thiện estimate không?

Ép join hint có thể hữu ích trong một tình huống đã được chứng minh, nhưng dễ trở thành nợ kỹ thuật khi dữ liệu tiếp tục tăng.

### 8.5. Spill và memory grant

Nếu spill xuất hiện sau khi dữ liệu tăng:

- Kiểm tra estimate và row width.
- Xác định operator và số byte spill.
- Xem query concurrency và memory grant queue.
- Kiểm tra sort/hash có thể giảm input bằng filter/projection không.
- Đánh giá cấu hình memory/work area ở phạm vi query hoặc workload.
- Đo tổng memory khi nhiều query cùng chạy.

Tăng memory grant cho một query có thể khiến query khác chờ memory. Ưu tiên sửa estimate và giảm intermediate rows trước khi tăng giới hạn toàn cục.

### 8.6. Partition pruning và phạm vi truy vấn

Với bảng rất lớn, partition theo thời gian hoặc tenant có thể giảm phạm vi dữ liệu phải đọc nếu predicate khớp partition key. Kiểm tra plan có chỉ truy cập partition cần thiết không. Nếu query bọc partition key trong function hoặc chuyển kiểu, pruning có thể bị hạn chế.

Partitioning không thay thế index và không làm mọi query nhanh hơn. Nó tăng độ phức tạp vận hành, index maintenance, statistics và lifecycle dữ liệu. Chỉ chọn khi workload và retention thực sự hưởng lợi.

## 9. Plan baseline, forcing và biện pháp giảm thiểu

### 9.1. Khi nào nên giữ plan tốt đã biết?

Nếu production đang bị ảnh hưởng nghiêm trọng và có một plan cũ đã được đo là tốt trên workload tương tự, có thể cần khôi phục plan để giảm tác động trong khi tiếp tục điều tra.

Các cơ chế khác nhau theo engine:

- SQL Server Query Store có thể force một plan đã ghi nhận.
- Oracle SQL Plan Management có thể dùng SQL plan baseline.
- PostgreSQL core không có cơ chế plan forcing tổng quát tương đương; thường cần sửa statistics/query/index hoặc dùng công cụ/extension được đánh giá kỹ.
- MySQL có optimizer hints và một số cơ chế điều khiển plan theo phiên bản; cần xác nhận hỗ trợ và tác động.

Plan forcing là biện pháp kiểm soát, không phải sửa nguyên nhân. Plan cũ có thể không còn phù hợp khi dữ liệu tiếp tục tăng, bind value thay đổi hoặc index bị thay đổi.

### 9.2. Quy tắc khi force plan

Trước khi force:

1. Có plan cũ và runtime evidence chứng minh nó tốt.
2. So sánh plan đó trên các nhóm bind value quan trọng.
3. Kiểm tra index và statistics mà plan phụ thuộc vẫn tồn tại.
4. Đo CPU, reads, elapsed, memory và waits dưới concurrency đại diện.
5. Đặt owner, thời hạn review và tiêu chí gỡ forcing.
6. Ghi lại cách rollback nếu plan gây tác dụng phụ.

Sau khi force, tiếp tục theo dõi. Nếu optimizer không thể dùng plan đó hoặc forcing tạo lỗi, cần có đường quay lại ngay.

### 9.3. Không xóa plan cache hàng loạt

Xóa toàn bộ plan cache có thể làm mọi query phải compile lại, tăng CPU và gây compile storm. Nó cũng phá hủy bằng chứng về plan trước đó.

Nếu cần recompile, hãy chọn đúng query hoặc object bằng cơ chế của engine, lưu plan history trước và thực hiện trong cửa sổ phù hợp. Đôi khi cập nhật statistics hoặc thay đổi schema tự gây recompile; cần hiểu tác động đó trước khi triển khai.

### 9.4. Plan management cần có lịch sử

Lưu lại:

- Query fingerprint.
- Plan identifier/hash.
- Thời điểm plan xuất hiện và kết thúc.
- Runtime metrics theo plan.
- Bind value group hoặc selectivity class.
- Statistics version/time.
- Index/schema version.
- Engine version và optimizer settings.
- Hành động đã áp dụng và kết quả.

Lịch sử này giúp phân biệt regression do data growth, deploy, statistics refresh hay thay đổi cấu hình.

## 10. Quy trình điều tra có kiểm soát

Có thể dùng quy trình sau cho một query chậm sau tăng trưởng dữ liệu.

### Bước 1: Xác nhận phạm vi và mức ảnh hưởng

- Query nào chậm: fingerprint, endpoint hoặc job?
- Bắt đầu từ thời điểm nào?
- p50, p95, p99 thay đổi bao nhiêu?
- Ảnh hưởng một tenant, một bind value hay mọi request?
- Tần suất thực thi và concurrency hiện tại?
- Các query khác trên cùng bảng có bị ảnh hưởng không?

### Bước 2: Thu thập baseline và plan history

- Lưu SQL, bind type và các nhóm bind value.
- Lấy plan hiện tại và plan tốt trước đó nếu có.
- Ghi actual rows, estimated rows, loops và operator warnings.
- Lưu elapsed, CPU, reads, writes, waits, memory và spill.
- Ghi nhận thời điểm deploy, DDL, statistics refresh và engine upgrade.

### Bước 3: Xác định điểm sai lệch đầu tiên

- Đọc plan từ leaf lên root.
- Tìm node có estimated/actual rows lệch lớn đầu tiên.
- Xác định skew, correlation hoặc row width.
- Kiểm tra số lần operator chạy và tổng hàng thực tế.
- Xác định join/access path nào bị ảnh hưởng.

### Bước 4: Kiểm tra statistics và dữ liệu

- Số hàng và số distinct values có thay đổi?
- Statistics có stale hoặc sample không đại diện?
- Histogram có mô tả giá trị phổ biến?
- Predicate trên nhiều cột có correlation?
- Partition mới đã có statistics phù hợp?
- Bind values có selectivity rất khác nhau?

### Bước 5: Kiểm tra tài nguyên và waits

- CPU time tăng hay elapsed tăng do wait?
- Physical reads hay logical reads chi phối?
- Có lock/blocking hoặc latch contention?
- Sort/hash có spill không?
- Memory grant queue hoặc temp storage có nghẽn?
- Network/fetch time có phải phần lớn thời gian?

### Bước 6: Đưa ra giả thuyết có thể bác bỏ

Ví dụ:

- Statistics stale khiến estimate thấp 100 lần.
- Tenant lớn làm plan nested loop không còn phù hợp.
- Predicate function làm index range scan không được dùng.
- Hash join spill do row width và memory grant.
- Lock wait tăng do query chạy lâu hơn, không phải do plan trực tiếp.

Mỗi giả thuyết phải chỉ ra metric hoặc plan evidence sẽ xác nhận/bác bỏ nó.

### Bước 7: Thử một thay đổi nhỏ

Chọn thay đổi phù hợp nguyên nhân đã xác định: refresh statistics mục tiêu, bổ sung extended statistics, điều chỉnh index, sửa predicate, tách query path hoặc áp dụng plan control tạm thời.

Không đồng thời thay statistics, index, SQL và memory settings nếu không cần. Thay nhiều yếu tố cùng lúc làm mất khả năng xác định yếu tố tạo cải thiện hoặc gây regression.

### Bước 8: Đo lại cùng điều kiện

Chạy cùng query, bind group và concurrency. So sánh:

- Plan shape.
- Estimated/actual rows.
- Elapsed và CPU.
- Logical/physical reads.
- Temp spill và memory.
- Waits.
- Throughput và p95/p99 của workload tổng thể.

Đừng chỉ đo một lần chạy ấm cache. Cần hiểu cả cold/warm behavior và tác động của các query cạnh tranh.

### Bước 9: Triển khai theo phạm vi nhỏ

Dùng canary, tenant subset hoặc workload window nếu hệ thống cho phép. Theo dõi query mục tiêu và các query dùng chung bảng/index/statistics. Có rollback rõ ràng cho DDL, configuration và plan forcing.

### Bước 10: Ghi nhận nguyên nhân và phòng ngừa

Cập nhật runbook, cảnh báo theo query fingerprint, plan history, statistics maintenance và capacity model. Theo dõi tăng trưởng hàng/ngày, data skew và query latency để phát hiện sớm lần regression tiếp theo.

## 11. Tình huống thực tế: query đơn hàng chậm sau khi bảng tăng trưởng

### 11.1. Hiện tượng

Một dịch vụ báo cáo lọc đơn hàng theo tenant, trạng thái và khoảng ngày. Khi bảng orders có 4 triệu hàng, p95 của query khoảng 180 ms. Sau 9 tháng, bảng tăng lên 90 triệu hàng; p95 tăng lên 8,4 giây và CPU DBMS tăng cao vào giờ báo cáo.

Query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC;
~~~

### 11.2. Bằng chứng thu thập

Plan history cho thấy plan cũ dùng index range scan theo tenant/status/time rồi đọc các hàng phù hợp. Sau một đợt bulk load, statistics được cập nhật và plan mới dùng nested loop với lookup lặp lại. Với tenant lớn, actual rows ở node đầu vào cao hơn estimate hơn 300 lần.

Đồng thời phát hiện:

- Tenant lớn chiếm tỷ trọng đơn hàng tăng nhanh.
- Status phân bố lệch theo tenant.
- Statistics đơn cột không mô tả đủ correlation tenant/status.
- Lookup về bảng thực hiện hàng triệu lần.
- Logical reads và CPU tăng mạnh; physical I/O chỉ chiếm một phần.
- Tenant nhỏ vẫn chạy nhanh với plan mới.

Những bằng chứng này cho thấy một plan được chọn theo phân bố trung bình không phù hợp với tenant lớn.

### 11.3. Các giả thuyết được thử

1. Refresh statistics với sample/target phù hợp cho cột có skew.
2. Tạo statistics đa cột cho tenant_id và status nếu engine hỗ trợ.
3. Đánh giá index ghép tenant_id, status, created_at và khả năng bao phủ cột output.
4. Kiểm tra plan cho tenant nhỏ, tenant trung bình và tenant lớn.
5. So sánh nested loop với phương án hash/scan khi số hàng lớn.
6. Đánh giá sort và memory khi ORDER BY created_at DESC.

### 11.4. Kết quả minh họa

| Chỉ số | Trước điều chỉnh | Sau thử nghiệm |
|---|---:|---:|
| p95 tenant lớn | 8.400 ms | 620 ms |
| CPU time/query | 5.900 ms | 410 ms |
| Logical reads/query | 1.850.000 | 92.000 |
| Sai số cardinality tại node đầu | 300x | 1,8x |
| Spill | Có ở một số lần chạy | Không thấy trong workload thử nghiệm |
| p95 tenant nhỏ | 150 ms | 165 ms |

Số liệu minh họa cho thấy cải thiện mạnh với tenant lớn, nhưng tenant nhỏ chậm hơn nhẹ do plan/index mới có trade-off. Cần xác định SLO cho từng nhóm tenant và cân nhắc nhiều plan hoặc query path nếu chênh lệch selectivity lớn.

### 11.5. Điều kiện để chấp nhận

- Kết quả trả về giống nhau với mọi nhóm bind value.
- Không bỏ sót hoặc nhân đôi hàng.
- p95/p99 của tenant lớn đạt mục tiêu.
- Tenant nhỏ không vượt SLO.
- CPU và logical reads tổng thể giảm.
- Write overhead và kích thước index nằm trong ngân sách.
- Các query khác trên orders không bị regression.
- Có phương án rollback và theo dõi sau deploy.

## 12. Những sai lầm thường gặp

**Chỉ nhìn operator cuối cùng.**  
Sai số cardinality đầu tiên thường xuất hiện ở leaf hoặc filter node; join phía trên chỉ chịu hậu quả.

**Cho rằng table scan luôn xấu.**  
Scan có thể hợp lý nếu predicate trả nhiều hàng hoặc bảng nhỏ.

**Refresh toàn bộ statistics ngay lập tức.**  
Có thể thay đổi plan của nhiều query và tạo compile/recompile load.

**Ép join hint trước khi sửa estimate.**  
Hint có thể che nguyên nhân và trở nên sai khi dữ liệu tiếp tục tăng.

**Chỉ kiểm tra một bind value.**  
Tenant nhỏ và tenant lớn có thể cần plan khác nhau.

**Xóa toàn bộ plan cache.**  
Có thể tạo compile storm và mất bằng chứng plan cũ.

**Tăng memory toàn cục khi thấy spill.**  
Có thể làm các query đồng thời tranh chấp memory nghiêm trọng hơn.

**Tạo index theo một query mà không xét workload ghi.**  
Index mới tăng storage, write amplification, maintenance và có thể làm insert/update chậm hơn.

**So sánh runtime trong điều kiện khác nhau.**  
Cache state, bind value, concurrency và dữ liệu khác nhau làm kết quả không đáng tin.

**Kết luận plan regression chỉ vì latency tăng.**  
Lock wait, storage, network hoặc ứng dụng có thể là nguyên nhân chính.

**Force plan cũ vô thời hạn.**  
Plan tốt trước đây có thể mất hiệu quả khi phân bố dữ liệu tiếp tục đổi.

## 13. Phòng ngừa regression khi dữ liệu tiếp tục tăng

### 13.1. Theo dõi tăng trưởng và phân bố

Không chỉ theo dõi tổng row count. Theo dõi thêm:

- Rows theo tenant, trạng thái và khoảng thời gian.
- Distinct values và tỷ lệ giá trị phổ biến.
- Row width và payload size.
- Số partition và dữ liệu mỗi partition.
- Index size, bloat/fragmentation và page density.
- Tỷ lệ insert/update/delete.
- Số query có cardinality estimate sai lớn.

Các metric theo nhóm giúp phát hiện skew trước khi nó làm plan thay đổi.

### 13.2. Theo dõi plan và runtime theo query fingerprint

Cảnh báo khi:

- p95/p99 tăng vượt baseline.
- Logical reads hoặc CPU/query tăng đột biến.
- Plan identifier thay đổi đồng thời với regression.
- Estimated/actual rows lệch quá ngưỡng đã định.
- Spill hoặc temp usage tăng.
- Một nhóm bind value có latency cao bất thường.

Plan change không luôn là lỗi. Cảnh báo cần kết hợp plan change với runtime regression để tránh noise.

### 13.3. Statistics maintenance theo đặc tính dữ liệu

- Xác định bảng tăng nhanh hoặc skew cao.
- Chạy analyze/update statistics sau bulk load lớn khi cần.
- Kiểm tra incremental/partition statistics.
- Chọn histogram hoặc sample cho cột có ảnh hưởng.
- Dùng extended statistics khi predicate có correlation.
- Theo dõi auto statistics job và lỗi của nó.
- Kiểm thử plan sau refresh trên các query trọng yếu.

### 13.4. Capacity và query design

- Đặt giới hạn thời gian và số hàng cho report.
- Dùng keyset/pagination khi không cần tải toàn bộ dữ liệu.
- Thiết kế index theo predicate và order thực tế.
- Cân nhắc partition theo retention/access pattern.
- Đưa query phân tích nặng sang replica hoặc workload group phù hợp nếu kiến trúc cho phép.
- Tách workload có selectivity khác biệt rõ.
- Benchmark với dữ liệu và skew gần production.

### 13.5. Runbook và rollback

Mỗi query trọng yếu nên có:

- Query fingerprint và owner.
- SLO và baseline.
- Cách lấy actual plan.
- Bind groups cần kiểm tra.
- Statistics/index liên quan.
- Plan history và biện pháp rollback.
- Metric cần theo dõi sau thay đổi.
- Điều kiện gỡ plan forcing hoặc hint tạm thời.

## 14. Kết luận

Tăng trưởng dữ liệu làm thay đổi số hàng, phân bố giá trị, row width, số page và mức độ chọn lọc của predicate. Optimizer dựa trên statistics và ước lượng cardinality để chọn access path, join order, memory và parallelism. Khi mô hình ước lượng không còn phản ánh dữ liệu thật, plan có thể chuyển sang phương án đắt hơn; một plan mới cũng có thể hợp lý cho nhóm bind này nhưng kém cho nhóm khác.

Điều tra cần bắt đầu bằng bằng chứng: plan history, actual rows, estimated rows, loops, reads, CPU, waits và bind values. Tìm sai lệch đầu tiên, kiểm tra statistics/skew/correlation, rồi xác định access path, join, spill hoặc parameter sensitivity. Thử một thay đổi có kiểm soát, đo lại cùng workload và chỉ giữ khi cả query mục tiêu lẫn hệ thống tổng thể đều tốt hơn.

Không có một hint, index hay statistics setting nào bảo đảm plan luôn tối ưu khi dữ liệu tiếp tục thay đổi. Theo dõi plan và runtime theo query fingerprint, kiểm soát statistics sau bulk load, kiểm thử các nhóm bind value và duy trì rollback giúp giảm thời gian phát hiện cũng như khôi phục khi regression xuất hiện.

## Câu hỏi tự kiểm tra

1. Làm thế nào phân biệt plan regression với tình huống plan không đổi nhưng số hàng xử lý tăng?
2. Vì sao cardinality estimate sai ở node thấp có thể làm join phía trên trở nên rất đắt?
3. Cần hiểu gì về loops và actual rows khi đọc execution plan?
4. Data skew và correlation giữa các cột ảnh hưởng optimizer như thế nào?
5. Vì sao cùng một SQL có thể cần plan khác nhau cho tenant nhỏ và tenant lớn?
6. Statistics refresh có thể làm thay đổi những query nào ngoài query đang điều tra?
7. Khi nào table scan có thể tốt hơn index seek?
8. Vì sao nested loop với outer input lớn có thể tạo hàng triệu lookup?
9. Spill của sort/hash có thể do những nguyên nhân nào ngoài memory cấu hình thấp?
10. Các công cụ nào giúp theo dõi plan history trên PostgreSQL, SQL Server, MySQL và Oracle?
11. Khi nào plan forcing có thể là biện pháp giảm thiểu hợp lý, và cần điều kiện gỡ bỏ nào?
12. Vì sao không nên xóa toàn bộ plan cache như bước chẩn đoán đầu tiên?
13. Hãy thiết kế một benchmark có tenant nhỏ, trung bình và lớn để kiểm tra query theo cùng khoảng thời gian.
14. Những metric nào cần theo dõi để chứng minh thay đổi đã giảm tải DBMS mà không làm workload khác chậm hơn?
15. Hãy lập runbook cho trường hợp query p95 tăng sau bulk load và statistics refresh.

Khi một truy vấn chậm sau tăng trưởng dữ liệu, hãy lần theo câu hỏi: plan đã đổi ở đâu, optimizer dự đoán bao nhiêu hàng, thực tế có bao nhiêu hàng, phân bố nào đã thay đổi và operator nào đang trả giá cho sai lệch đó. Bằng chứng ở từng bước giúp chọn đúng biện pháp và tránh biến một sự cố query thành regression của toàn hệ thống.
