# Lập báo cáo tối ưu gồm tính đúng đắn, số liệu trước sau và đánh đổi

Một thay đổi tối ưu cơ sở dữ liệu chỉ có thể được đánh giá đầy đủ khi báo cáo chứng minh được ba điều: kết quả nghiệp vụ vẫn đúng, hiệu năng thay đổi như thế nào trong điều kiện đo có thể so sánh, và hệ thống phải trả chi phí gì để đạt được cải thiện đó. Một câu kết luận như “query nhanh hơn 40%” chưa đủ để quyết định triển khai nếu chưa biết dữ liệu trả về có tương đương, workload ghi có chậm đi, storage tăng bao nhiêu hoặc p99 của các request khác có bị ảnh hưởng.

Trong module DATABASE_PERFORMANCE, việc tối ưu dựa trên đo tải, execution plan, statistics và cơ chế truy cập dữ liệu. Báo cáo tối ưu cần kết nối các bằng chứng này thành một câu chuyện kỹ thuật có thể kiểm tra: vấn đề ban đầu, giả thuyết, thay đổi, phương pháp xác minh correctness, số liệu trước/sau, nguyên nhân của kết quả, đánh đổi, giới hạn và quyết định tiếp theo.

Bài học này hướng dẫn cách lập báo cáo cho một thay đổi SQL hoặc index, mở rộng sang các thay đổi cấu hình và workload, tổ chức phép đo trước/sau, kiểm tra tính đúng đắn của dữ liệu, diễn giải metric, ghi nhận trade-off và đưa ra quyết định phát hành. Các số liệu trong ví dụ là dữ liệu minh họa để thực hành cách phân tích, không phải kết quả của một hệ thống thực.

## 1. Mục tiêu của báo cáo tối ưu

Báo cáo tối ưu là hồ sơ kỹ thuật mô tả một thay đổi đã được kiểm chứng. Báo cáo phải giúp người đọc trả lời:

1. Vấn đề nào cần giải quyết và nó ảnh hưởng workload nào?
2. Giả thuyết tối ưu dựa trên bằng chứng nào?
3. Thay đổi cụ thể là gì và phạm vi tác động ở đâu?
4. Kết quả dữ liệu trước/sau có tương đương theo quy tắc nghiệp vụ không?
5. Latency, throughput, lỗi và tài nguyên thay đổi ra sao?
6. Execution plan, cardinality estimate, statistics hoặc đường truy cập dữ liệu thay đổi thế nào?
7. Hệ thống phải trả thêm chi phí gì về ghi, bộ nhớ, I/O, storage, log hoặc replication?
8. Kết quả áp dụng trong điều kiện nào và còn giới hạn gì?
9. Có nên triển khai, triển khai có điều kiện, thử tiếp hay hoàn tác?

Một báo cáo tốt không cố chứng minh mọi thay đổi đều thành công. Nếu hiệu năng không cải thiện, kết quả đo không ổn định hoặc correctness không đạt, báo cáo phải ghi nhận điều đó và giải thích bằng chứng còn thiếu.

### Ba lớp bằng chứng

| Lớp | Câu hỏi | Bằng chứng điển hình |
|---|---|---|
| Tính đúng đắn | Hành vi và dữ liệu có giữ đúng yêu cầu? | So sánh kết quả, invariant, constraint, transaction behavior |
| Hiệu năng | Workload chạy nhanh và ổn định hơn không? | p50/p95/p99, throughput, error rate, queue |
| Chi phí/đánh đổi | Cải thiện đạt được bằng tài nguyên hoặc rủi ro nào? | CPU, memory, I/O, lock, log, storage, replication, write latency |

Không được dùng một lớp để thay thế lớp khác. Query nhanh hơn nhưng trả thiếu hàng là thất bại. Query nhanh hơn nhưng làm ghi vượt SLO cũng có thể là thất bại. Index tăng storage nhưng giúp workload quan trọng đạt SLO có thể là lựa chọn hợp lý nếu chi phí được chấp nhận.

## 2. Chọn một vấn đề có thể kiểm chứng

Hãy bắt đầu từ workload hoặc query fingerprint đã được quan sát. Tránh chọn một câu SQL chỉ vì nó trông phức tạp.

Các nguồn bằng chứng có thể gồm:

- Tổng DB time hoặc CPU time theo query fingerprint.
- p95/p99 latency theo endpoint, transaction hoặc câu SQL.
- Logical reads, physical reads và số hàng được đọc/trả về.
- Execution plan với scan lớn, join không phù hợp hoặc sort/hash spill.
- Estimated rows khác xa actual rows.
- Lock wait, deadlock, transaction duration hoặc hot key.
- Connection pool wait và số lần round-trip.
- I/O latency, queue depth, log flush và replication lag.

### Định nghĩa phạm vi

Ghi rõ đối tượng cần tối ưu:

- Một query hay một nhóm query cùng fingerprint.
- Một transaction có nhiều statement.
- Một API end-to-end gồm application, pool, network và DB.
- Một workload đọc, ghi hoặc hỗn hợp.
- Một bảng, partition, tenant hoặc toàn database.

Nếu đo SQL trực tiếp, không gọi đó là latency API. Nếu đo API, cần nêu latency có bao gồm queue, connection acquisition, network và serialization hay không.

### Xác định mức độ quan trọng

Không xếp hạng chỉ bằng latency trung bình. Một truy vấn chậm 2 giây nhưng chạy một lần mỗi ngày có thể ít ảnh hưởng hơn truy vấn 80 ms chạy hàng nghìn lần mỗi giây.

Có thể xem xét đồng thời:

- Tổng thời gian tiêu thụ: calls × mean duration.
- p95/p99 và số request vượt SLO.
- Tần suất gọi và mức độ quan trọng nghiệp vụ.
- CPU/IO time và số hàng đọc.
- Ảnh hưởng lên các workload khác.

## 3. Viết giả thuyết tối ưu trước khi sửa

Giả thuyết mô tả cơ chế dự kiến làm hiệu năng thay đổi. Nó phải gắn với execution plan, statistics hoặc cách truy cập dữ liệu.

Ví dụ:

“Query lịch sử đơn hàng lọc theo tenant bằng equality và theo thời gian bằng range, nhưng plan hiện tại đọc nhiều hàng rồi lọc và sort. Index ghép (tenant_id, created_at) có thể giảm logical reads và sort work. Chi phí dự kiến là storage tăng và INSERT/UPDATE phải duy trì thêm index.”

Giả thuyết này có thể được kiểm chứng bằng:

- Số hàng và page được đọc trước/sau.
- Access path trước/sau.
- Sort operator và spill.
- p95/p99 latency ở cùng workload.
- Insert/update latency và kích thước index.

### Ví dụ các giả thuyết khác

| Quan sát | Giả thuyết | Số liệu cần kiểm tra |
|---|---|---|
| Estimated rows thấp hơn actual rows rất nhiều | Statistics/histogram không phản ánh phân bố | Estimate error, plan, statistics freshness |
| N+1 query tạo nhiều round-trip | Gom truy vấn sẽ giảm số lần gọi DB | Calls/request, total DB time, payload size |
| Lock wait tập trung ở một khóa nóng | Giảm thời gian giữ transaction hoặc phân tán ghi sẽ giảm contention | Lock wait, blocker duration, throughput |
| Sort/hash spill ra disk | Cardinality hoặc memory grant chưa phù hợp | Spill bytes, memory, actual rows |
| Batch ghi quá lớn làm replica lag | Điều tiết batch/concurrency sẽ giảm burst log | Rows/s, log rate, commit time, apply lag |
| Pool wait cao trong khi DB còn headroom | Pool hoặc thời gian giữ connection đang giới hạn | Pool wait, active session, connection hold time |

Đặt cả metric kỳ vọng cải thiện và metric có thể xấu đi. Nếu chỉ nêu lợi ích, báo cáo sẽ không đủ cơ sở để đánh giá trade-off.

## 4. Ghi lại baseline trước thay đổi

Baseline là trạng thái tham chiếu trước khi tối ưu. Không có baseline đáng tin cậy thì rất khó kết luận candidate tốt hơn.

### Thông tin cần lưu

| Nhóm | Nội dung |
|---|---|
| DBMS | Sản phẩm, phiên bản, edition, patch |
| Hạ tầng | CPU, RAM, storage, IOPS, network |
| Topology | Primary/replica, cluster, shard, proxy |
| Schema | DDL, constraint, partition, trigger |
| Index | Định nghĩa, kích thước, usage nếu có |
| Statistics | Thời điểm cập nhật, histogram/sampling quan trọng |
| Dữ liệu | Số hàng, dung lượng, skew, tenant distribution |
| Cấu hình | Memory, parallelism, isolation, connection, durability |
| Ứng dụng | Version, driver, ORM, pool settings |
| Workload | Read/write mix, concurrency, arrival rate, parameter mix |
| Cache | Cold/warm, buffer/cache hit ratio, plan cache |
| Thời gian | Ngày giờ, cửa sổ đo, tác vụ nền |

Không nhất thiết đưa mọi tham số vào phần tóm tắt. Tuy nhiên, phải lưu những thông tin có thể làm thay đổi execution plan, memory, I/O, lock hoặc kết quả.

### Metric baseline

Tối thiểu nên có:

- p50, p95, p99 latency.
- Throughput thành công.
- Error/timeout/retry rate.
- Số request và số mẫu.
- CPU và memory.
- Logical/physical reads, write bytes và I/O latency.
- Lock wait/deadlock nếu có.
- Connection/pool wait.
- Log generation/flush và replication lag nếu workload ghi.

Ghi rõ ranh giới đo, đơn vị và nguồn dữ liệu. p95 của SQL server execution không tương đương p95 của API.

### Giữ điều kiện đo tương đương

Trước/sau cần giữ ổn định:

- Dataset snapshot và phân bố tham số.
- DBMS version và cấu hình.
- Workload mix, concurrency và arrival model.
- Warm-up và cache state.
- Thời lượng steady-state.
- Tải nền và topology.
- Metric definition và công cụ đo.

Nếu không thể giữ một điều kiện, ghi rõ khác biệt và xem kết quả là so sánh có điều kiện. Không nhân tuyến tính số liệu từ môi trường khác cấu hình để suy ra kết quả production.

## 5. Kiểm chứng tính đúng đắn trước khi so hiệu năng

Đây là bước bắt buộc khi viết lại SQL, thay đổi join, predicate, pagination, index có điều kiện, partition hoặc cấu trúc dữ liệu.

### Xác định hợp đồng kết quả

Trước khi so sánh, xác định:

- Những hàng nào phải xuất hiện.
- Những hàng nào không được xuất hiện.
- Số lượng và thứ tự có ý nghĩa hay không.
- Giá trị NULL, duplicate và giá trị mặc định được xử lý thế nào.
- Biên thời gian, timezone và collation.
- Quyền truy cập theo tenant/user.
- Isolation level và snapshot semantics.
- Hành vi khi dữ liệu thay đổi đồng thời.

Nếu thứ tự kết quả là một phần hợp đồng API, ORDER BY phải có tie-breaker ổn định. Sắp xếp chỉ theo timestamp có thể không xác định thứ tự giữa các hàng cùng thời điểm.

### So sánh trên cùng snapshot

Khi có thể, chạy query cũ và mới trên cùng một snapshot dữ liệu hoặc bản sao nhất quán. Nếu dữ liệu thay đổi giữa hai lần chạy, chênh lệch kết quả có thể do insert/update thực tế chứ không phải do câu SQL.

Đối với query chỉ đọc, có thể:

1. Lấy tập khóa chính từ query cũ.
2. Lấy tập khóa chính từ query mới.
3. So sánh số lượng và tập khóa theo hai chiều.
4. So sánh giá trị cột quan trọng theo khóa.
5. Kiểm tra thứ tự nếu thứ tự là yêu cầu.

Không chỉ so sánh COUNT(*). Hai tập kết quả khác nhau vẫn có thể có cùng số hàng.

### So sánh hai chiều

Về mặt logic, cần tìm:

- Hàng có trong kết quả cũ nhưng thiếu trong kết quả mới.
- Hàng mới xuất hiện trong kết quả mới nhưng không có ở kết quả cũ.
- Hàng có cùng khóa nhưng giá trị cột khác nhau.

Một số DBMS hỗ trợ toán tử tập hợp như EXCEPT/MINUS; cú pháp, cách xử lý NULL và hỗ trợ nhiều cột phụ thuộc DBMS. Có thể dùng full outer join theo khóa hoặc công cụ đối chiếu riêng. Khi so sánh giá trị nullable, phải dùng phép so sánh null-safe phù hợp.

Ví dụ khái niệm:

```text
missing = old_result MINUS new_result
extra   = new_result MINUS old_result
changed = same_key_but_different_values
```

Kết quả đúng khi cả ba tập sai khác đều rỗng, trong phạm vi dữ liệu và điều kiện được kiểm tra.

### Kiểm tra invariant nghiệp vụ

Ngoài so sánh query output, kiểm tra các bất biến:

- Tổng tiền theo đơn hàng/khách hàng.
- Số lượng chi tiết phải khớp số lượng header.
- Không có khóa trùng ngoài quy tắc cho phép.
- Foreign key và quan hệ tham chiếu còn hợp lệ.
- Không có bản ghi thuộc tenant khác.
- Tổng số hàng theo trạng thái không thay đổi ngoài dự kiến.
- Giá trị aggregate và checksum theo nhóm.

Ví dụ, query mới trả đúng 100 order ID nhưng total_amount bị tính sai do JOIN nhân bản detail row thì chỉ so sánh ID là chưa đủ.

### Kiểm tra DML và transaction

Với INSERT/UPDATE/DELETE hoặc batch:

- Kiểm tra số hàng bị tác động.
- Kiểm tra giá trị trước/sau theo khóa.
- Kiểm tra trigger, cascade, audit và outbox.
- Xác minh commit/rollback.
- Kiểm tra retry có gây ghi lặp không.
- Xác minh idempotency và unique constraint.
- Đánh giá isolation và lost update.

Không chạy lại DML trên production chỉ để so sánh nếu có side effect. Dùng bản sao dữ liệu, transaction rollback đã kiểm chứng hoặc quy trình test có kiểm soát.

### Đồng thời và isolation

Hai câu SQL cho cùng kết quả khi chạy đơn lẻ chưa chắc tương đương dưới concurrency. Thay đổi transaction boundary, thứ tự đọc/ghi hoặc số statement có thể thay đổi:

- Snapshot được quan sát.
- Khả năng lost update.
- Deadlock order.
- Thời gian giữ lock.
- Retry do serialization failure.
- Thứ tự phát sinh event/outbox.

Nếu tối ưu thay đổi transaction, cần test với nhiều transaction đồng thời và kiểm tra invariant sau khi hoàn tất.

## 6. Ví dụ capstone: tối ưu truy vấn lịch sử đơn hàng

### Bối cảnh nghiệp vụ

Một ứng dụng thương mại điện tử cung cấp API lịch sử đơn hàng theo tenant. Người dùng chọn khoảng thời gian và nhận tối đa 100 đơn gần nhất. Khi số đơn tăng, endpoint chậm rõ rệt ở tenant lớn.

Truy vấn hiện tại:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 100;
```

Cú pháp LIMIT ở đây minh họa cho PostgreSQL/MySQL. SQL Server và Oracle dùng cú pháp giới hạn hàng riêng; báo cáo thực tế phải lưu câu SQL đúng dialect.

### Phạm vi

- Chỉ tối ưu endpoint lịch sử đơn hàng.
- Truy vấn chỉ đọc, không thay đổi transaction ghi đơn.
- Dữ liệu gồm nhiều tenant với quy mô không đồng đều.
- Workload có cả đọc lịch sử và cập nhật trạng thái đơn.
- Mục tiêu là giảm latency đọc trong khi write latency vẫn nằm trong SLO.

### Baseline minh họa

Giả sử phép đo baseline cho kết quả:

| Metric | Baseline |
|---|---:|
| p50 query latency | 72 ms |
| p95 query latency | 310 ms |
| p99 query latency | 780 ms |
| Throughput thành công | 190 request/s |
| Logical reads/query | 31.500 |
| Physical reads/query trung bình | 420 |
| DB CPU | 69% |
| Error rate | 0,04% |
| p95 update order latency | 48 ms |
| Index storage trên orders | 6,2 GB |

Đây là số liệu giả định để minh họa cách viết báo cáo. Khi làm thực tế, thay bằng dữ liệu thu thập được và lưu số mẫu, thời lượng, workload mix, cache state.

### Phân tích execution plan

Plan baseline cho thấy:

- Database đọc một vùng dữ liệu lớn từ index hiện có hoặc table scan.
- Predicate tenant/time loại bỏ phần lớn hàng sau khi đọc.
- Sort xử lý nhiều hàng trước khi lấy 100 hàng đầu.
- Số hàng actual cao hơn đáng kể so với số hàng cần trả về.

Giả thuyết: index ghép (tenant_id, created_at DESC) giúp định vị phạm vi tenant trước, sau đó duyệt theo khoảng thời gian và thứ tự cần thiết. Cần xác minh plan thật vì optimizer có thể chọn access path khác tùy selectivity và thống kê.

### Candidate change

Tạo index phù hợp:

```sql
CREATE INDEX ix_orders_tenant_created
ON orders (tenant_id, created_at DESC);
```

Đây là DDL khái niệm; cú pháp online/concurrent và khả năng hỗ trợ phụ thuộc DBMS/version. Trong production phải chọn phương pháp tạo index phù hợp và ghi rõ lock, I/O, log, dung lượng dự kiến.

Không đưa total_amount và status vào index một cách tự động chỉ để tạo covering index. Include column có thể giảm table lookup nhưng làm index lớn hơn và tăng write amplification. Chỉ cân nhắc sau khi đo số lookup còn lại và chi phí lưu trữ/ghi.

### Xác minh correctness

Trước khi so latency:

1. Chọn cùng snapshot dữ liệu.
2. Chạy query cũ và query mới với tenant nhỏ, tenant lớn và tenant có phân bố lệch.
3. So sánh tập order_id hai chiều.
4. So sánh status, total_amount, created_at theo từng order_id.
5. Kiểm tra các timestamp nằm đúng tại from_time và to_time.
6. Xác minh tenant predicate không bị bỏ sót.
7. Kiểm tra thứ tự khi nhiều đơn có cùng created_at.

Nếu API yêu cầu thứ tự xác định, bổ sung tie-breaker như order_id vào ORDER BY và cân nhắc cấu trúc index tương ứng. Đây là thay đổi hợp đồng kết quả cần được đánh giá rõ ràng; không tự thêm hoặc bỏ thứ tự trong báo cáo mà không nêu.

### Đo candidate

Chạy cùng workload mix, concurrency, arrival rate, dataset và cache state. Lưu plan mới, actual rows, logical reads, physical reads, sort và metric hệ thống.

Kết quả minh họa:

| Metric | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| p50 query latency | 72 ms | 34 ms | -52,8% |
| p95 query latency | 310 ms | 118 ms | -61,9% |
| p99 query latency | 780 ms | 420 ms | -46,2% |
| Throughput thành công | 190 request/s | 255 request/s | +34,2% |
| Logical reads/query | 31.500 | 4.600 | -85,4% |
| Physical reads/query trung bình | 420 | 85 | -79,8% |
| DB CPU | 69% | 73% | +4 điểm % |
| Error rate | 0,04% | 0,04% | Không đổi |
| p95 update order latency | 48 ms | 55 ms | +14,6% |
| Index storage trên orders | 6,2 GB | 8,0 GB | +1,8 GB |

Các số liệu trên hoàn toàn minh họa. Phần trăm thay đổi được tính từ hai giá trị cùng đơn vị và cùng phương pháp đo. Với CPU, cần phân biệt tăng 4 điểm phần trăm với tăng 4% tương đối.

### Phân tích plan sau thay đổi

Plan candidate có thể cho thấy:

- Index range scan/seek theo tenant và thời gian.
- Ít hàng được đọc hơn trước.
- Sort được loại bỏ hoặc xử lý trên tập nhỏ hơn nếu index order phù hợp.
- Logical reads giảm mạnh.
- Table lookup vẫn còn nếu index không bao phủ cột trả về.

Nếu optimizer vẫn chọn scan, hãy kiểm tra selectivity và kích thước bảng. Scan có thể hợp lý khi query lấy phần lớn dữ liệu. Không kết luận index thất bại chỉ vì plan không dùng index trong một parameter class.

## 7. Phân tích số liệu trước và sau

### Latency

Luôn báo p50, p95 và p99 khi có đủ mẫu. p50 thể hiện request điển hình; p95/p99 giúp nhìn tail latency. Một thay đổi có thể giảm p50 nhưng p99 tăng do lock hoặc queue.

Ví dụ trong capstone:

- p50 giảm từ 72 ms xuống 34 ms.
- p95 giảm từ 310 ms xuống 118 ms.
- p99 giảm từ 780 ms xuống 420 ms.

Đây là dấu hiệu cải thiện cả phần lớn request và tail latency. Tuy nhiên, p99 vẫn còn 420 ms; nếu SLO yêu cầu dưới 300 ms thì candidate chưa đạt hoàn toàn.

### Throughput

Throughput phải là số request/transaction thành công theo định nghĩa rõ ràng. Ghi cả failed request, retry và timeout. Không xem số request được nhận vào generator là số request DB xử lý thành công.

Khi throughput tăng, kiểm tra latency có giữ trong ngưỡng không. Hệ thống có thể đạt throughput cao hơn bằng cách xếp hàng request lâu hơn; đó không phải cải thiện nếu SLO latency bị vi phạm.

### Error rate và correctness

Error rate không thay thế kiểm tra correctness. Một query có thể trả thiếu hàng mà không phát sinh SQL error. Báo cáo phải ghi riêng:

- Lỗi kỹ thuật.
- Timeout/retry.
- Sai khác kết quả.
- Vi phạm invariant.
- Sai quyền truy cập hoặc dữ liệu tenant.

Nếu có sai khác correctness ngoài dự kiến, không đánh dấu PASS dù latency tốt.

### Logical reads và physical reads

Logical reads phản ánh page được truy cập trong buffer/cache của DBMS. Physical reads phản ánh dữ liệu phải đọc từ storage theo định nghĩa của DBMS và công cụ. Giảm logical reads thường cho thấy ít công việc truy cập page hơn; physical reads còn phụ thuộc cache state và tải nền.

Không so sánh physical reads giữa một lượt cold-cache và một lượt warm-cache như thể chỉ có index thay đổi. Ghi rõ cache state và cách warm-up.

### CPU

CPU có thể tăng nhẹ trong khi latency giảm vì throughput tăng. Điều cần quan tâm là CPU trên mỗi request thành công, headroom còn lại và khả năng giữ SLO khi tải cao điểm. Có thể báo cả CPU utilization và CPU time/query hoặc CPU/request nếu thu thập được.

### Đọc và ghi

Index thường làm đọc nhanh hơn nhưng tăng chi phí ghi:

- Insert thêm entry.
- Update cột index có thể sửa B-tree.
- Delete phải xóa hoặc đánh dấu entry.
- Page split, WAL/redo và cache pressure có thể tăng.

Do đó cần đo write latency, write throughput, log generation và replication. Nếu chỉ đo SELECT, báo cáo chưa phản ánh chi phí của index trong workload hỗn hợp.

## 8. Ghi nhận đánh đổi một cách minh bạch

Trade-off là chi phí hệ thống chấp nhận để đạt lợi ích. Báo cáo phải lượng hóa khi có thể và nêu ảnh hưởng vận hành.

### Các loại đánh đổi phổ biến

| Lợi ích | Chi phí có thể phát sinh | Metric cần theo dõi |
|---|---|---|
| SELECT nhanh hơn nhờ index | Write amplification, storage | Insert/update latency, index size |
| Ít round-trip hơn nhờ batch query | Payload lớn, memory ở app/DB | Rows/response, memory, p99 |
| Batch ghi lớn tăng rows/s | Transaction dài, log burst, replica lag | Commit duration, log rate, lag |
| Tăng memory giảm spill | Memory pressure khi concurrency cao | Peak memory, swap, spill, grant wait |
| Parallel query giảm thời gian một query | CPU/worker contention | CPU, worker queue, latency workload khác |
| Connection limit lớn hơn | Nhiều session và contention | Active sessions, pool wait, lock wait |
| Timeout ngắn giải phóng tài nguyên | Tăng lỗi/retry | Timeout rate, retry amplification |
| Cache tăng hit ratio | Stale data, invalidation complexity | Freshness, hit ratio, invalidation lag |

### Đánh đổi trong capstone

Candidate giảm logical reads 85,4% và p95 đọc 61,9%, nhưng:

- Index storage tăng 1,8 GB.
- p95 update tăng 7 ms, tương đương 14,6%.
- CPU tăng 4 điểm phần trăm do throughput cao hơn và duy trì index.

Để quyết định, cần so các chi phí này với SLO ghi, storage headroom, backup duration và replication. Nếu p95 update vẫn thấp hơn ngưỡng nghiệp vụ và còn đủ dung lượng, trade-off có thể chấp nhận. Nếu hệ thống gần hết disk hoặc workload ghi đã sát SLO, cần cân nhắc index hẹp hơn, covering có chọn lọc, partition hoặc cách tối ưu query khác.

### Chi phí tuyệt đối và tương đối

Nên báo cả:

- Tăng tuyệt đối: index thêm 1,8 GB.
- Tăng tương đối: storage index tăng khoảng 29% so với baseline 6,2 GB.
- Tác động trên mỗi thao tác: write p95 tăng 7 ms.
- Tác động tổng: throughput ghi hoặc DB time thay đổi bao nhiêu.

Tỷ lệ phần trăm lớn trên một giá trị nhỏ có thể ít quan trọng; chi phí tuyệt đối lớn có thể tạo rủi ro capacity dù phần trăm thấp.

### Chi phí dài hạn

Một phép thử ngắn có thể bỏ sót:

- Index/table bloat.
- Vacuum/purge hoặc maintenance tăng thời gian.
- Backup và restore chậm hơn.
- Cache residency giảm vì index lớn.
- Replication apply chậm dần khi write volume tăng.
- Statistics thay đổi theo phân bố dữ liệu.
- Query plan regression sau khi data volume tăng.

Nếu thay đổi có ảnh hưởng dài hạn, cần theo dõi sau triển khai và ghi rõ thời gian quan sát ban đầu.

## 9. Phân biệt cải thiện thực và nhiễu đo

### Số lần lặp

Không chọn lượt chạy tốt nhất. Chạy nhiều lượt trong điều kiện tương đương, báo median và range hoặc phân bố giữa các run. Nếu kết quả có outlier, điều tra checkpoint, backup, failover, cache miss, lock hoặc bottleneck ở load generator.

### Warm-up và cache

Ghi rõ:

- Warm-up kéo dài bao lâu.
- Điều kiện dừng warm-up.
- Cache có được reset giữa các lượt không.
- Plan cache có được giữ không.
- Candidate có được chạy sau baseline khiến cache nóng hơn không.

Có thể dùng thứ tự xen kẽ baseline/candidate để giảm thiên lệch thứ tự, hoặc khôi phục snapshot/cache state giữa các lượt nếu môi trường cho phép.

### Sample size và percentile

Ghi số request thành công và thất bại. p99 từ ít mẫu có thể dao động mạnh. Không loại request timeout khỏi latency mà không báo; làm vậy có thể khiến phần đuôi xấu nhất biến mất khỏi báo cáo.

Nếu dùng histogram, ghi bucket width và cách tổng hợp. Không lấy trung bình p95 của các batch nhỏ để thay cho p95 của toàn bộ tập mẫu.

### Load generator

Xác nhận generator đạt arrival rate yêu cầu. Theo dõi CPU, network, worker, dropped request và queue của generator. Nếu generator bị nghẽn, throughput quan sát được không phản ánh giới hạn của DB.

## 10. Liên kết kết quả với execution plan và statistics

Bảng số liệu cho biết điều gì đã thay đổi; execution plan giúp giải thích tại sao.

Báo cáo nên lưu:

- SQL text đã chuẩn hóa và query fingerprint.
- Parameter class hoặc phân bố giá trị thử.
- Execution plan trước/sau ở định dạng gốc của DBMS.
- Access path và join strategy.
- Estimated rows và actual rows.
- Loops, rows removed/filter và rows returned.
- Logical/physical reads.
- Sort/hash memory và spill.
- Parallel worker/degree of parallelism.
- Statistics/histogram và thời điểm cập nhật.

### Estimated rows và actual rows

Nếu estimate sai lớn, optimizer có thể chọn join order, index hoặc memory grant không phù hợp. Báo cáo cần chỉ rõ node nào sai lệch, mức độ và ảnh hưởng đến các node phía trên.

Ví dụ minh họa:

| Node | Estimated rows | Actual rows | Ý nghĩa |
|---|---:|---:|---|
| Index scan | 500 | 45.000 | Ước lượng thấp 90 lần |
| Join output | 1.000 | 38.000 | Sai lệch lan lên join |
| Sort input | 1.200 | 37.500 | Có thể tăng sort cost/spill |

Không kết luận statistics là nguyên nhân chỉ vì estimate sai. Cần kiểm tra skew, correlation giữa cột, histogram, sampling và parameter value.

### Statistics trước/sau

Nếu candidate bao gồm cập nhật statistics, hãy ghi đó là một phần của thay đổi. Không gộp “thêm index + cập nhật statistics + đổi SQL + tăng memory” rồi quy toàn bộ cải thiện cho index.

Nếu mục tiêu là đánh giá nhân quả, thay một yếu tố chính mỗi lượt hoặc thiết kế ma trận thử nghiệm có kiểm soát. Nếu thay đổi phải đi cùng nhau, báo cáo cần ghi rõ nhóm thay đổi và không tách đóng góp khi chưa có bằng chứng.

### Không chỉ lưu ảnh plan

Lưu plan text/JSON/XML theo DBMS, thời điểm, parameter class, query fingerprint và phiên bản. Một ảnh chụp không chứng minh mọi lần thực thi đều dùng cùng plan.

Nếu dùng công cụ thực thi query để lấy actual plan, đánh giá side effect và chi phí đo. Không chạy DML có thể thay đổi dữ liệu chỉ để lấy execution statistics trên production.

## 11. Báo cáo cho thay đổi SQL

Khi viết lại SQL, cần báo ba nhóm kết quả:

### Semantics

- Kết quả có tương đương không?
- Có thay đổi NULL, duplicate, ordering, collation hoặc timezone không?
- Có thay đổi isolation hoặc transaction boundary không?
- Predicate bảo mật/tenant có được giữ không?

### Plan và chi phí

- Calls và DB time.
- Rows read/returned.
- Logical/physical reads.
- CPU và elapsed time.
- Join/sort/hash operators.
- Memory spill.
- Round-trip và payload.

### Workload rộng hơn

- Query khác dùng chung bảng/index có bị ảnh hưởng không?
- Ghi có tăng latency không?
- Connection pool và concurrency có thay đổi không?
- p99 API có ổn định không?

### Ví dụ: loại bỏ N+1 query

Trước tối ưu, ứng dụng lấy danh sách 50 đơn rồi gọi thêm một query để lấy chi tiết cho từng đơn. Tổng cộng khoảng 51 round-trip.

Sau tối ưu, ứng dụng gom ID và truy vấn detail theo danh sách. Báo cáo cần so sánh:

- Số query/request giảm từ khoảng 51 xuống 2.
- Tổng DB time và end-to-end latency.
- Kích thước payload và số hàng trả về.
- Memory ở application và database.
- Kết quả chi tiết có giữ thứ tự và không nhân bản không.
- Hành vi với danh sách rỗng/lớn và ID không tồn tại.

Một câu IN với hàng nghìn ID có thể có giới hạn bind parameter hoặc plan kém. Batch size và cách truyền danh sách cần được đo theo DBMS/driver.

## 12. Báo cáo cho thay đổi index

Với index, báo cáo cần nêu:

- DDL và loại index.
- Thứ tự cột, include columns, filter/predicate.
- Kích thước trước/sau.
- Thời gian và phương thức build.
- Lock mode và tác động trong lúc build.
- Plan và access path trước/sau.
- Logical/physical reads.
- Write latency và write throughput.
- WAL/redo/log generation.
- Cache pressure và replication.

### Index có được dùng không?

Kiểm tra plan với các parameter class đại diện. Optimizer có thể không dùng index nếu:

- Query trả về phần lớn bảng.
- Statistics cho thấy scan rẻ hơn.
- Predicate không phù hợp thứ tự cột.
- Predicate không SARGable.
- Kiểu dữ liệu/conversion làm mất khả năng seek.
- Query cần sort khác thứ tự index.

Index tồn tại không có nghĩa nó luôn được sử dụng. Không ép plan chỉ để tạo ra một kết quả đẹp trong báo cáo.

### Đánh giá index ít dùng

Không kết luận index dư thừa chỉ từ usage counter trong một cửa sổ ngắn. Counter có thể reset sau restart hoặc không bao phủ workload theo tháng/quý. Kiểm tra constraint, unique key, foreign key, batch và báo cáo định kỳ trước khi đề xuất drop.

## 13. Báo cáo cho thay đổi transaction và write path

Khi tối ưu ghi, cần đo:

- Transactions/s và rows/s.
- Commit latency và transaction duration.
- Lock wait, deadlock và retry.
- Log bytes/s, flush latency và log queue.
- Replica send/receive/apply lag.
- Batch size và concurrency.
- Error và idempotency behavior.

### Ví dụ batch size

Một job import thử batch 200, 1.000 và 5.000 hàng:

| Batch size | Rows/s | p95 transaction | Peak replica lag |
|---:|---:|---:|---:|
| 200 | 18.000 | 90 ms | 1,2 s |
| 1.000 | 27.000 | 310 ms | 4,8 s |
| 5.000 | 29.000 | 1.650 ms | 22 s |

Số liệu minh họa cho thấy batch 5.000 tăng throughput chỉ khoảng 7,4% so với batch 1.000 nhưng transaction p95 và replica lag tăng mạnh. Nếu SLO replica lag dưới 5 giây, batch 5.000 không đạt dù rows/s cao nhất.

Báo cáo cần ghi thêm:

- Có giữ nguyên thứ tự và tính nguyên tử của nghiệp vụ không?
- Nếu batch giữa chừng thất bại, checkpoint ở đâu?
- Retry có thể ghi trùng không?
- Transaction log có đủ dung lượng không?
- Workload trực tuyến có bị lock hoặc I/O contention không?

## 14. Báo cáo cho thay đổi cấu hình

Với memory, parallelism, connection, timeout hoặc durability, cần ghi:

- Tham số và giá trị cũ/mới.
- Scope: session, database, instance hoặc cluster.
- Runtime/persistent behavior.
- Có cần reload/restart không.
- Workload và parameter class được thử.
- Metric mục tiêu và guardrail.
- Ảnh hưởng tới các workload khác.

### Memory

Tăng memory cho sort/hash có thể giảm spill nhưng nhiều query đồng thời có thể dùng memory cùng lúc. Ghi peak memory, swap, spill, memory grant wait và concurrency. Đừng đánh giá bằng một query chạy đơn lẻ.

### Parallelism

Ghi thời gian query nặng, CPU, worker queue và p99 của request nhỏ. Query đơn lẻ nhanh hơn có thể làm throughput toàn hệ thống giảm.

### Connection limit

Ghi pool wait, active sessions, memory, context switching, lock wait và throughput. Nhiều connection hơn không đồng nghĩa database có thể xử lý nhiều query hữu ích hơn.

### Durability

Nếu thay đổi flush policy hoặc synchronous commit, phải ghi rõ tác động tới RPO và khả năng mất dữ liệu khi crash. Không xem latency giảm là thành công nếu yêu cầu durability bị vi phạm.

## 15. Phân tích nguyên nhân và không phóng đại kết luận

Một báo cáo phải phân biệt:

- **Quan sát:** p95 giảm từ 310 ms xuống 118 ms.
- **Bằng chứng cơ chế:** logical reads giảm, plan chuyển sang index range scan.
- **Giải thích:** index giúp định vị tenant và khoảng thời gian trực tiếp hơn.
- **Giới hạn:** mới thử với các tenant và dữ liệu trong snapshot hiện tại.
- **Giả thuyết chưa xác nhận:** write overhead dài hạn có thể tăng thêm khi dữ liệu tăng.

Không viết “index chắc chắn là nguyên nhân duy nhất” nếu cùng lúc cập nhật statistics hoặc thay đổi cache state.

### Phân tích theo workload class

Gộp tất cả request có thể che giấu regression của một nhóm nhỏ. Tách theo:

- Tenant lớn/nhỏ.
- Parameter selectivity.
- Read/write/report/batch.
- Cold/warm cache.
- Peak/off-peak.
- Query plan/fingerprint.

Nếu tenant lớn cải thiện nhưng tenant nhỏ chậm hơn, báo cáo cần nêu rõ và đánh giá tỷ trọng traffic của mỗi nhóm.

### Phân biệt tương quan và nguyên nhân

CPU giảm đồng thời với latency giảm không chứng minh CPU là nguyên nhân duy nhất. Cần liên hệ plan, reads, waits và thời gian đo. Khi nhiều biến thay đổi cùng lúc, chỉ kết luận ở cấp nhóm thay đổi.

## 16. Cấu trúc báo cáo tối ưu

Một báo cáo thực tế có thể dùng cấu trúc sau:

### 16.1. Thông tin chung

- Tên thay đổi và Change ID.
- Module/database/service.
- Người thực hiện và người review.
- Ngày giờ, múi giờ và cửa sổ đo.
- DBMS/version, application commit và schema version.
- Trạng thái: PASS, FAIL, INCONCLUSIVE hoặc PASS WITH CONDITIONS.

### 16.2. Tóm tắt

Trong vài đoạn, nêu:

- Vấn đề và mức ảnh hưởng.
- Thay đổi đã thực hiện.
- Kết quả correctness.
- Hai hoặc ba metric hiệu năng quan trọng.
- Trade-off chính.
- Quyết định và điều kiện triển khai.

### 16.3. Baseline và giả thuyết

- Bằng chứng vấn đề.
- Query fingerprint/workload.
- Execution plan và statistics.
- Mục tiêu/SLO.
- Giả thuyết và rủi ro dự kiến.

### 16.4. Thay đổi

- SQL/DDL/config trước và sau.
- Phạm vi đối tượng.
- Phụ thuộc.
- Cách triển khai và thời gian.
- Cấu hình hoặc dữ liệu đã thay đổi.

### 16.5. Xác minh correctness

- Dataset/snapshot.
- Cách so sánh.
- Số hàng, khóa và giá trị khác biệt.
- Invariant và constraint.
- Transaction/concurrency behavior.
- Kết quả và ngoại lệ.

### 16.6. Phương pháp đo

- Workload mix.
- Arrival rate và concurrency.
- Warm-up và steady-state.
- Thời lượng, số lần lặp, số mẫu.
- Tool/version và metric source.
- Ranh giới latency.
- Tiêu chí loại lượt/outlier.

### 16.7. Kết quả trước/sau

Bảng metric có baseline, candidate, delta, đơn vị và ngưỡng. Kèm plan, resource, error và trade-off.

### 16.8. Phân tích

Giải thích vì sao plan/metric thay đổi. Tách quan sát khỏi giả thuyết. Nêu workload class được cải thiện hoặc suy giảm.

### 16.9. Đánh đổi và giới hạn

Ghi storage, write overhead, CPU, memory, I/O, lock, log, replication, backup/maintenance và điều kiện chưa thử.

### 16.10. Quyết định

Nêu PASS/FAIL/INCONCLUSIVE, rollout scope, rollback trigger, monitoring sau triển khai và phép đo tiếp theo.

### 16.11. Phụ lục

Lưu query fingerprint, execution plan, DDL, cấu hình, script workload, raw metrics, dashboard và commit. Loại bỏ password, token, connection secret và dữ liệu cá nhân không cần thiết.

## 17. Mẫu báo cáo có thể tái sử dụng

Sao chép khung sau và điền số liệu thực:

```markdown
# Báo cáo tối ưu database: <tên thay đổi>

## Trạng thái
- Kết luận: PASS / FAIL / INCONCLUSIVE / PASS WITH CONDITIONS
- Change ID:
- Ngày giờ:
- Người thực hiện/reviewer:
- DBMS/version:
- Application commit/schema version:

## 1. Vấn đề và phạm vi
- Workload/query fingerprint:
- Mức ảnh hưởng:
- Baseline/SLO:
- Phạm vi được thử:

## 2. Giả thuyết
- Bằng chứng:
- Cơ chế dự kiến:
- Metric kỳ vọng cải thiện:
- Trade-off dự kiến:

## 3. Điều kiện đo
- Hạ tầng/topology:
- Dataset và phân bố:
- Statistics:
- Workload mix:
- Arrival rate/concurrency:
- Cache state/warm-up:
- Duration/số lần lặp/số mẫu:
- Công cụ và ranh giới đo:

## 4. Thay đổi
- SQL/DDL/config trước:
- SQL/DDL/config sau:
- Phạm vi:
- Thời gian triển khai:
- Phụ thuộc:

## 5. Xác minh correctness
- Snapshot/dataset:
- So sánh tập khóa hai chiều:
- So sánh giá trị:
- Invariant/constraint:
- Concurrency/transaction:
- Sai khác và cách xử lý:
- Kết quả: PASS / FAIL

## 6. Kết quả hiệu năng
| Metric | Baseline | Candidate | Delta | SLO/Guardrail |
|---|---:|---:|---:|---:|
| p50 latency | | | | |
| p95 latency | | | | |
| p99 latency | | | | |
| Throughput | | | | |
| Error rate | | | | |
| CPU | | | | |
| Memory | | | | |
| Logical reads | | | | |
| Physical reads/I/O | | | | |
| Lock wait | | | | |
| Write latency | | | | |
| Log/replica lag | | | | |
| Storage | | | | |

## 7. Execution plan/statistics
- Plan trước:
- Plan sau:
- Estimated/actual rows:
- Access path/join/sort:
- Spill/buffer/I/O:
- Statistics thay đổi:

## 8. Đánh đổi
- Lợi ích:
- Chi phí tăng:
- Workload bị ảnh hưởng:
- Capacity/maintenance:
- Rủi ro còn lại:

## 9. Giới hạn
- Workload chưa mô phỏng:
- Parameter class chưa thử:
- Môi trường khác production:
- Thời gian quan sát:
- Metric còn thiếu:

## 10. Quyết định và kế hoạch
- Kết luận:
- Rollout scope:
- Rollback trigger:
- Theo dõi sau triển khai:
- Người chịu trách nhiệm:
- Phép đo tiếp theo:

## Phụ lục
- Query fingerprint/plan:
- DDL/config:
- Script workload:
- Raw result/dashboard:
- Commit/artifact:
```

## 18. Cách tính và trình bày mức thay đổi

### Phần trăm giảm latency

Với metric mà giá trị thấp hơn là tốt hơn:

Mức giảm (%) = (Baseline - Candidate) / Baseline × 100

Ví dụ p95 giảm từ 310 ms xuống 118 ms:

(310 - 118) / 310 × 100 ≈ 61,9%

### Phần trăm tăng throughput

Với metric mà giá trị cao hơn là tốt hơn:

Mức tăng (%) = (Candidate - Baseline) / Baseline × 100

Ví dụ throughput tăng từ 190 lên 255 request/s:

(255 - 190) / 190 × 100 ≈ 34,2%

### Điểm phần trăm và phần trăm tương đối

CPU tăng từ 69% lên 73% là tăng 4 điểm phần trăm. Mức tăng tương đối là khoảng 5,8%. Báo cáo nên dùng đúng cách diễn đạt để người đọc không hiểu nhầm.

### Đơn vị và định nghĩa

Ghi rõ:

- ms hay seconds.
- Request/s, transaction/s hay rows/s.
- Bytes, MiB hay GiB.
- Average, median hay percentile.
- Per request, per transaction hay tổng trong cửa sổ.

Không đặt tên “TPS” nếu chưa định nghĩa transaction. Không gọi logical reads là physical I/O.

## 19. Quyết định PASS, FAIL và INCONCLUSIVE

### PASS

Chỉ kết luận PASS khi:

- Correctness đạt.
- Metric mục tiêu đạt ngưỡng.
- Error rate và các guardrail bắt buộc đạt.
- Không có regression vượt giới hạn ở workload liên quan.
- Trade-off được chấp nhận.
- Điều kiện đo đủ tin cậy.

### PASS WITH CONDITIONS

Dùng khi kết quả đạt trong phạm vi nhất định, nhưng cần giới hạn rollout hoặc theo dõi thêm. Ví dụ:

- Chỉ đạt với tenant có quy mô đến một ngưỡng.
- p95 đạt nhưng p99 cần quan sát thêm.
- Write overhead chấp nhận được khi storage headroom còn đủ.
- Cần canary trước khi mở rộng toàn bộ traffic.

Ghi rõ điều kiện, thời hạn và người chịu trách nhiệm.

### FAIL

Dùng khi:

- Correctness sai.
- Metric bắt buộc không đạt.
- Error/lock/replication vượt guardrail.
- Trade-off làm workload quan trọng vi phạm SLO.
- Rollback hoặc vận hành không an toàn.

### INCONCLUSIVE

Dùng khi:

- Số mẫu quá ít.
- Workload generator không đạt arrival rate.
- Baseline và candidate khác cache state hoặc tải nền.
- Có thay đổi khác xảy ra cùng lúc.
- Thiếu execution plan hoặc metric cần thiết.
- Kết quả giữa các lượt biến động chưa giải thích.

INCONCLUSIVE không đồng nghĩa candidate tốt hay xấu. Cần nêu phép đo bổ sung để có thể kết luận.

## 20. Kế hoạch rollout và theo dõi sau tối ưu

Kết quả benchmark trên staging không bảo đảm production sẽ giống hệt. Traffic thực có skew, cache state, background job và contention khác.

Một rollout có thể:

1. Triển khai trên staging với dataset/workload gần production.
2. Canary trên shard, tenant hoặc tỷ lệ request phù hợp.
3. So sánh canary với control cohort.
4. Mở rộng theo các bước khi đủ mẫu và đạt guardrail.
5. Theo dõi qua chu kỳ nghiệp vụ.
6. Xác minh plan, correctness và replication.
7. Đóng change record sau khi kết quả ổn định.

### Rollback trigger

Định nghĩa trước:

- p95/p99 vượt SLO trong cửa sổ đánh giá.
- Error/timeout/retry vượt ngưỡng.
- Write latency hoặc throughput ghi không đạt.
- Lock wait/deadlock tăng bất thường.
- CPU/memory/I/O vượt capacity budget.
- Replica lag tăng liên tục.
- Sai khác dữ liệu hoặc invariant bị vi phạm.

Trigger correctness phải được xử lý ngay. Không chờ hết thời gian quan sát latency nếu phát hiện sai dữ liệu hoặc vi phạm tenant isolation.

### Sau rollout

Kiểm tra:

- Plan mới vẫn ổn định với parameter class thực tế.
- Statistics được duy trì.
- Index size và usage hợp lý.
- Write overhead không tăng theo thời gian vượt dự kiến.
- Backup/restore và maintenance vẫn nằm trong cửa sổ.
- Replica apply không tích lũy backlog.
- p99 và error rate ổn định qua peak traffic.

## 21. Giới hạn của báo cáo và cách nêu trung thực

Một phép đo luôn có phạm vi. Nêu giới hạn giúp tránh áp dụng kết luận quá rộng.

### Dataset không đại diện

Dữ liệu tổng hợp đều có thể không mô phỏng tenant lớn, hot key hoặc phân bố thời gian. Ghi cách tạo dataset và khác biệt so với production.

### Workload không đầy đủ

Thiếu batch, report, backup, replication hoặc tác vụ nền có thể làm candidate trông tốt hơn thực tế. Ghi nhóm workload chưa thử.

### Cache state khác nhau

Warm-cache và cold-cache trả lời hai câu hỏi khác nhau. Báo cáo nên tách kết quả thay vì gộp.

### Thời gian thử quá ngắn

Test ngắn có thể bỏ qua bloat, memory leak, vacuum/purge, checkpoint, log retention và replica backlog. Nêu rõ thời gian quan sát và đề xuất soak test nếu cần.

### Khác biệt DBMS/version

Online DDL, optimizer, statistics, index và configuration semantics phụ thuộc DBMS/version. Không áp dụng cú pháp hoặc kết luận của một engine cho engine khác.

### Instrumentation overhead

Query logging, tracing, plan capture và metric polling có thể thêm overhead. Ghi mức instrumentation và cách giảm tác động.

### Suy rộng capacity

Không giả định tăng CPU gấp đôi sẽ tăng throughput gấp đôi. Lock, I/O, log, memory bandwidth và coordination có thể trở thành bottleneck mới.

## 22. Những lỗi thường gặp khi lập báo cáo

- **Chỉ ghi latency trung bình:** bỏ qua p95/p99 và số mẫu.
- **Chỉ so COUNT(*):** hai tập kết quả khác nhau vẫn có thể cùng số hàng.
- **Không kiểm tra dữ liệu:** query nhanh hơn nhưng trả thiếu hoặc trùng hàng.
- **Bỏ qua tenant predicate:** có nguy cơ lộ dữ liệu chéo tenant.
- **Không dùng cùng snapshot:** chênh lệch có thể do dữ liệu thay đổi.
- **Chỉ đo query đọc:** không thấy write amplification của index.
- **Chỉ nhìn CPU:** bỏ qua lock, I/O, memory, log và replication.
- **Gộp nhiều thay đổi:** không xác định được yếu tố tạo ra cải thiện.
- **Chọn lượt benchmark tốt nhất:** che giấu biến động.
- **Bỏ request timeout khỏi thống kê:** làm tail latency đẹp giả tạo.
- **Không lưu plan:** không giải thích được nguyên nhân.
- **Không ghi parameter class:** bỏ sót plan regression do skew.
- **Không ghi storage/backup cost:** bỏ qua chi phí dài hạn.
- **Tuyên bố PASS khi correctness chưa xác minh:** biến hiệu năng thành tiêu chí duy nhất.
- **Không nêu giới hạn:** khiến người đọc áp dụng kết quả vượt phạm vi thử.
- **Không có rollback trigger:** không biết khi nào phải dừng rollout.

## 23. Checklist review báo cáo tối ưu

| Hạng mục | Câu hỏi review |
|---|---|
| Vấn đề | Có query/workload và mức ảnh hưởng cụ thể? |
| Giả thuyết | Có cơ chế liên quan plan, statistics hoặc data access? |
| Baseline | Có môi trường, dataset, workload, cache và metric? |
| Tương đương | Điều kiện trước/sau có đủ giống nhau? |
| Correctness | Có so sánh tập khóa, giá trị và invariant? |
| Concurrency | Có kiểm tra transaction/isolation khi thay đổi liên quan? |
| Latency | Có p50/p95/p99, đơn vị và số mẫu? |
| Throughput | Có định nghĩa request/transaction/rows thành công? |
| Error | Có timeout, retry và sai khác dữ liệu? |
| Plan | Có plan trước/sau, actual rows và query fingerprint? |
| Resource | Có CPU, memory, I/O, lock và log? |
| Trade-off | Có write overhead, storage, replication và maintenance? |
| Thống kê | Có số lần lặp, outlier và cache state? |
| Kết luận | PASS/FAIL/INCONCLUSIVE dựa trên mọi ngưỡng? |
| Rollout | Có canary, monitoring và rollback trigger? |
| Artifact | Có raw data, script, config và commit? |

## 24. Bài thực hành tổng hợp

Thực hiện một bài tối ưu trên môi trường thử nghiệm hoặc bản sao dữ liệu:

**Tình huống:** truy vấn lịch sử đơn hàng chậm ở tenant lớn. Nhóm đề xuất thêm index ghép theo tenant và thời gian.

**Nhiệm vụ:**

1. Xác định query fingerprint và ghi baseline.
2. Lưu execution plan, estimated/actual rows và logical reads.
3. Nêu giả thuyết và trade-off trước khi thay đổi.
4. Tạo dataset có tenant lớn/nhỏ và khoảng thời gian ngắn/dài.
5. Chạy query cũ và candidate trên cùng snapshot.
6. So sánh tập khóa hai chiều, giá trị cột và thứ tự.
7. Tạo index trong điều kiện phù hợp với DBMS.
8. Đo p50/p95/p99, throughput, errors, CPU, I/O và write latency.
9. Ghi kích thước index, log và replication lag.
10. Phân tích plan trước/sau và giải thích cơ chế cải thiện.
11. Lập bảng lợi ích/chi phí và kết luận PASS/FAIL/INCONCLUSIVE.
12. Đề xuất canary, rollback trigger và metric cần theo dõi sau triển khai.

### Tiêu chí hoàn thành

- Không có sai khác kết quả ngoài quy tắc đã công bố.
- Số liệu có đơn vị, số mẫu và điều kiện đo.
- Baseline/candidate có thể so sánh.
- Kết luận liên hệ với execution plan/statistics.
- Trade-off được lượng hóa hoặc ghi rõ chưa đo.
- Quyết định triển khai có guardrail và rollback trigger.

Nếu không đủ bằng chứng để kết luận, ghi INCONCLUSIVE và chỉ rõ phép đo cần bổ sung. Đây là kết quả hợp lệ của một bài thực hành nếu người học nhận diện đúng giới hạn.

## 25. Nguyên tắc lập báo cáo tối ưu có thể tin cậy

Báo cáo tối ưu cơ sở dữ liệu phải bắt đầu từ vấn đề có bằng chứng, nêu giả thuyết có thể kiểm chứng và lưu baseline trước thay đổi. Trước khi so hiệu năng, xác minh kết quả nghiệp vụ trên cùng snapshot bằng tập khóa, giá trị và invariant; với thay đổi transaction, kiểm tra thêm hành vi concurrency và isolation.

Số liệu trước/sau phải có cùng định nghĩa, đơn vị, workload và điều kiện đo. Hãy báo latency percentiles, throughput, error rate và tài nguyên; liên kết chúng với execution plan, cardinality estimate, statistics, index và cơ chế đọc/ghi. Đồng thời lượng hóa chi phí tăng về storage, write amplification, CPU, memory, I/O, log, lock, replication và maintenance.

Kết luận cần phản ánh cả lợi ích lẫn giới hạn. Chỉ PASS khi correctness, metric mục tiêu và guardrail đều đạt; dùng PASS WITH CONDITIONS khi cần rollout giới hạn; dùng FAIL khi vi phạm yêu cầu; và dùng INCONCLUSIVE khi phép đo chưa đủ tin cậy. Một báo cáo có thể tái lập, trung thực về trade-off và gắn với kế hoạch rollout/rollback sẽ giúp nhóm tối ưu hiệu năng có quyết định rõ ràng và kiểm chứng được sau triển khai.
