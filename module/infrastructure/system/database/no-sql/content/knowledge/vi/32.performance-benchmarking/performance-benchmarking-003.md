# Thiết kế dữ liệu đại diện về kích thước, phân bố và tỷ lệ đọc/ghi

## 1. Một phép đo tải đúng kỹ thuật vẫn có thể dẫn đến quyết định sai

Một nhóm phát triển ứng dụng Java dùng NoSQL cho hệ thống đơn hàng. Họ thử hiệu năng trên 1 triệu documents; mỗi document dài 1 KB, key được chọn ngẫu nhiên đều và workload gồm 90% GET theo ID, 10% INSERT. Kết quả trên môi trường test đạt 20.000 thao tác/giây, p99 là 12 ms.

Khi triển khai thật:

- 1% khách hàng lớn tạo ra 60% lưu lượng.
- Documents có size từ vài trăm byte tới hàng trăm KB vì mảng line items và metadata.
- 25% thao tác là UPDATE trên những records đang nóng; một số UPDATE làm tăng kích thước document.
- Truy vấn tìm đơn theo customer và khoảng thời gian không phải GET theo primary key.
- Dữ liệu tồn tại nhiều tháng và phần lớn không nằm trong RAM.
- Các writes tạo secondary indexes, replication traffic, flush/compaction và TTL cleanup.
- Traffic tập trung vào giờ cao điểm, có bursts do campaign và batch ingestion.

Kết quả production không giống benchmark. Điều này chưa chắc là database kém; **bài test đã tạo một thế giới khác hẳn thế giới thực**.

Trọng tâm bài thuộc module **Database No SQL**, chương **Hiệu năng và đo tải**, là thiết kế **bộ dữ liệu và chuỗi thao tác đủ đại diện** để kết quả benchmark có ý nghĩa cho quyết định kiến trúc.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa workload từ hành vi nghiệp vụ thay vì chỉ từ phần trăm CRUD tổng quát.
2. Thiết kế phân bố kích thước record: median, p95/p99, long tail, nested arrays, compressed/on-disk size.
3. Tạo phân bố key, tenant, document age, field cardinality và mức độ skew/hotspot thực tế.
4. Xác định tỷ lệ đọc/ghi theo operation, cửa sổ thời gian, mức tải và điểm nóng.
5. Tính dữ liệu logic, working set, tăng trưởng, index/replica overhead và headroom.
6. Tách bulk load, warm-up, steady-state, burst, recovery và long-running tests.
7. Chọn open-loop/closed-loop load generation, concurrency và tiêu chí chống coordinated omission.
8. Viết generator với seed cố định, phân bố có chủ đích và ràng buộc tham chiếu.
9. Vận dụng các đặc điểm MongoDB, DynamoDB, Cassandra/ScyllaDB và Redis.
10. Đo throughput, latency, tail latency, errors, resource consumption và độ đúng của dữ liệu sau test.

## 2. Dữ liệu đại diện không nhất thiết là dữ liệu thật

**Representative dataset** là tập dữ liệu có các đặc điểm đủ gần với production đối với những yếu tố ảnh hưởng kết quả đo của một câu hỏi cụ thể.

Nó không nhất thiết là bản sao của dữ liệu người dùng:

- Có thể là dữ liệu tổng hợp (synthetic).
- Có thể là replay đã ẩn danh, được cho phép và đã loại thông tin nhạy cảm.
- Có thể là tổ hợp snapshot giả lập với phân bố đo được từ telemetry.
- Có thể có nhiều kịch bản: bình thường, cao điểm, dữ liệu cực đoan và tương lai.

### 2.1. Không có một bộ dữ liệu “đại diện mọi bài toán”

Nếu muốn đánh giá point lookup, điều quan trọng là key popularity, cache hit/miss, document size và read consistency.

Nếu muốn đánh giá aggregation, điều quan trọng có thể là number of groups, index selectivity, filter predicates, scan width và skew.

Nếu muốn đo write-heavy LSM, size của value, compaction, tombstones và tuổi đời data có thể quan trọng hơn response payload của GET.

### 2.2. Câu hỏi benchmark quyết định cách thiết kế data

Ví dụ:

> “Với 30 triệu order records, 2.000 create/sec và 10.000 reads/sec vào giờ cao điểm, cụm có giữ p99 GET dưới 80 ms và p99 write dưới 120 ms trong 6 giờ khi index, replication và compaction hoạt động bình thường không?”

Câu hỏi này yêu cầu một dataset khác phép thử “truy cập một triệu key đều nhau trong 60 giây”.

### 2.3. Nên có cả baseline và stress scenario

- **Baseline:** Phản ánh workload được quan sát hiện tại.
- **Forecast:** Dự kiến khi số tenant/data tăng trong 6–12 tháng.
- **Stress:** Thử skew, burst, oversized records, TTL sweep hoặc node failure.
- **Counterfactual:** Thử một thay đổi riêng như index mới hoặc cache lớn hơn.

Không gọi stress scenario là “production trung bình”; báo cáo rõ nó là điều kiện thiết kế để khám phá giới hạn.

## 3. Ba trục cốt lõi: kích thước, phân bố và tỷ lệ đọc/ghi

### 3.1. Kích thước

Record bao nhiêu bytes? Có field lồng nhau, binary blob, metadata dài, array lớn? Storage overhead/serialization/compression/index thay đổi ra sao?

### 3.2. Phân bố

Những IDs nào được truy cập? Có keys được hỏi hàng nghìn lần so với key khác? Tenant, thời gian, partition và query fields lệch như thế nào?

### 3.3. Tỷ lệ đọc/ghi

Trong một cửa sổ đo, có bao nhiêu GET, query, INSERT, UPDATE, DELETE, scan, batch write? Operations nào có payload lớn? Chúng tương tác trên cùng một key hay phân tán?

### 3.4. Ba trục không độc lập

Một số tenant lớn có record to hơn, update nhiều hơn và xuất hiện trong p99. Hot keys có thể là những records vừa tạo, trong khi cold keys thường lớn và nằm ở disk.

Nếu generator bốc kích thước, tuổi record, tenant và key popularity **độc lập hoàn toàn**, nó có thể bỏ lỡ tương quan thực tế.

### 3.5. Bổ sung ràng buộc nhất quán và thời gian

Một phép thử có thể cần mô tả thêm:

- Consistency level/read preference.
- Transaction/conditional write.
- Replica placement và replication factor.
- SLO durability và write acknowledgment.
- Traffic profile theo giờ.
- Cache warm/cold.
- TTL và background maintenance.

Không bỏ những yếu tố này khi chúng làm thay đổi ý nghĩa latency và throughput.

## 4. Từ user journey đến workload matrix

Đừng khởi đầu bằng “80% read, 20% write” nếu chưa biết read/write đó là gì. Hãy lập bảng:

| Hành vi | Database operation | Key/query pattern | Tần suất mẫu | Payload | Business requirement |
|---|---|---|---:|---|---|
| Xem chi tiết đơn | GET by (tenantId,orderId) | Point lookup | 35% | Trả một document | Read-your-writes sau tạo |
| Liệt kê đơn của user | Query by customer/time | Partition/range | 25% | 20–50 rows/page | Sort descending |
| Xem trạng thái checkout | GET operationId | Hot recent keys | 15% | Nhỏ | Status chính xác |
| Tạo đơn | INSERT/conditional | New key | 10% | Trung bình | Không tạo trùng |
| Cập nhật trạng thái | UPDATE/CAS | Recent order | 10% | Partial update | Expected version |
| Tìm kiếm | Search/filter | Secondary index | 3% | Nhiều rows | Eventual freshness |
| Hủy/xóa | DELETE/tombstone | Existing order | 2% | Nhỏ | Propagation/retention |

Tỷ lệ là ví dụ, không phải số đo chuẩn của một ứng dụng. Tính tổng đúng 100% theo định nghĩa **một logical operation**.

### 4.1. Một user request có thể tạo nhiều database operations

Ví dụ “checkout” có thể phát sinh:

~~~text
1 HTTP POST /checkout
  -> 1 idempotency lookup
  -> 1 stock conditional update
  -> 1 order insert
  -> 1 outbox insert
  -> optional 1 status query
~~~

Nếu benchmark chỉ đếm một INSERT, sẽ đánh giá thấp database load và contention.

### 4.2. Tách traffic frontend và internal

CDC consumers, scheduled jobs, repair, analytics exports và TTL cleanup có thể chạy cùng cụm. Chúng không nằm trong bảng request từ web, nhưng vẫn tiêu thụ I/O, CPU và network.

### 4.3. Tách physical attempts và logical operations

Một read có retry hoặc speculative execution có thể phát ra nhiều attempts. Benchmark nên đo:

~~~text
logical GET rate
physical DB request rate
attempt amplification
~~~

Nếu tính retries thành những business operations mới, throughput báo cáo có thể lạc quan hoặc khó đối soát.

## 5. Thống kê dữ liệu trước khi sinh

Nếu có telemetry hợp lệ, lấy thống kê aggregate của production:

- Document count và bytes theo collection/table/tenant.
- Histogram kích thước record trước/sau serialization.
- p50/p90/p95/p99/max của số phần tử array.
- Tỷ lệ field null/missing/optional.
- Distinct values (NDV) của các trường filter/sort.
- Mối quan hệ tenant size, request rate và document size.
- Tuổi bản ghi và tốc độ tăng trưởng.
- Key popularity/rank-frequency.
- Query templates và số lần thực thi.
- Ratio GET vs range query vs update vs insert.
- Các peaks theo giờ/ngày và background jobs.

### 5.1. Đừng chỉ lấy trung bình

Ví dụ average document size là 4 KB nhưng:

~~~text
90% records = 1 KB
9% records  = 8 KB
1% records  = 220 KB
~~~

Trung bình logic:

\[
E[S] = 0.90\times 1 + 0.09\times 8 + 0.01\times 220
     = 3.82\text{ KB}.
\]

Một test toàn 3,82 KB có cùng mean nhưng **không có records 220 KB**; nó bỏ qua phân mảnh, network buffers, max document/item size và p99 response size.

### 5.2. Histogram thực dụng

| Bucket document size | Tỷ lệ mẫu | Tác động có thể có |
|---|---:|---|
| Dưới 1 KB | 45% | Cache hiệu quả, nhiều keys |
| 1–4 KB | 35% | Workload phổ biến |
| 4–16 KB | 15% | Tốn memory/network hơn |
| 16–64 KB | 4% | Tail payload và index work |
| 64–256 KB | 0,9% | Oversized objects |
| Trên 256 KB | 0,1% | Stress limits/driver buffers |

Các bucket/tỷ lệ phải được gán từ quan sát hoặc giả định có ghi nguồn; số ở đây chỉ minh họa.

### 5.3. Phân biệt population distribution với access-weighted distribution

Một bộ dữ liệu có 1% records lớn nhưng nếu 30% reads rơi vào nhóm lớn, **phân bố kích thước response mà client trải nghiệm** khác phân bố toàn tập.

Nên đo cả:

~~~text
P(record size | record tồn tại trong dataset)
P(record size | record được đọc)
P(payload size | API operation)
~~~

### 5.4. Dữ liệu không được thu thập tùy tiện

Không sao chép raw production PII/credentials/payment data sang môi trường load test. Ưu tiên aggregate histograms và generator tổng hợp. Nếu được phép replay, cần xử lý consent, ẩn danh hóa, access controls và retention.

## 6. Logical size khác on-disk size và resident size

Một document JSON dài 5 KB không có nghĩa hệ NoSQL dùng đúng 5 KB trên SSD.

### 6.1. Những thành phần dung lượng

~~~text
Logical values
  + serialization/BSON/row metadata
  + primary index
  + secondary indexes
  + internal storage structures
  + compaction/fragmentation overhead
  + snapshots/backups
  + replication copies
  + temporary rebuild/repair space
~~~

Compression có thể giảm on-disk bytes, nhưng việc giải nén, index và cache memory vẫn có chi phí.

### 6.2. Đừng dùng một multiplier chung cho mọi engine

Index-heavy MongoDB, Cassandra LSM, DynamoDB service storage, Redis memory và search inverted index có overhead khác nhau. Một công thức “data size × 3” có thể là ước lượng sơ bộ nhưng phải đo để quyết định capacity.

### 6.3. Kích thước request/response khác kích thước document

Một query trả 50 orders nhưng chỉ projection:

~~~text
orderId, status, total
~~~

sẽ có network payload khác GET 50 full documents có nested line items. Phải sinh đúng projection/query shape.

### 6.4. Giới hạn mỗi item/document

Benchmark cần có record-size edge cases gần giới hạn phù hợp với engine, nhưng không tạo records vượt hard limit rồi cho đó là lỗi hiệu năng. Ví dụ một số hệ có giới hạn item/document riêng; kiểm tra cụ thể phiên bản và API deployment trước khi stress.

## 7. Phân bố kích thước: đuôi dài làm thay đổi p99

Một lựa chọn sinh size là hỗn hợp:

\[
P(S) =
\begin{cases}
0.80 & S\text{ thuộc nhóm nhỏ}\\
0.17 & S\text{ thuộc nhóm vừa}\\
0.03 & S\text{ thuộc nhóm lớn}
\end{cases}
\]

Ở đây ký hiệu diễn tả xác suất nhóm, không phải mật độ xác suất liên tục chính xác. Trong từng nhóm có thể chọn một log-normal/truncated distribution để tránh mọi record bằng nhau.

### 7.1. Không chỉ tạo bytes rác

Hai documents cùng 8 KB có thể tạo performance khác nhau:

- Một String body dài và compressible.
- Nhiều fields ngắn cần index.
- Một array 100 nested items.
- Random binary payload không nén được.

Data generator cần mô phỏng **cấu trúc** và entropy chứ không chỉ tổng byte count.

### 7.2. Tỷ lệ entropy tác động compression

Nếu dùng chuỗi "AAAAAAAA..." để đệm tới 100 KB, compression có thể nén cực tốt, khiến disk/I/O workload không giống dữ liệu thật.

Ngược lại, toàn random bytes có thể quá khó nén so với JSON lặp field names/values. Kết hợp patterns theo domain, đo compression ratio của dữ liệu sinh.

### 7.3. Nested array size cũng là một phân bố

Ví dụ:

~~~text
0 items:       1%
1–3 items:    70%
4–10 items:   24%
11–50 items:   4%
51–500 items:  1%
~~~

Nếu mỗi order luôn 3 items, benchmark sẽ không thể hiện việc update array lớn, serialize nặng và pagination/response tail.

### 7.4. Gắn size với query pattern

Đối với API details, reads có thể tải full document. Đối với API list, chỉ lấy một số fields. Kết quả đo phải gồm cả việc **truy xuất/serialization** phù hợp request, không đánh đồng mọi reads thành cùng lượng bytes.

## 8. Cardinality và phân bố giá trị của field

**Cardinality/NDV** là số giá trị phân biệt trong một field.

Ví dụ một triệu orders:

~~~text
status:       6 distinct values
country:     20 distinct values
customerId:  200,000 distinct values
orderId:     1,000,000 distinct values
~~~

### 8.1. Vì sao NDV quan trọng?

Một query:

~~~text
WHERE status = 'PENDING'
~~~

có thể match 60% records nếu PENDING chiếm phần lớn, trong khi:

~~~text
WHERE orderId = 'O101'
~~~

chỉ match một record khi orderId unique.

Index selectivity, pages scanned, returned rows, read amplification và plan sẽ khác nhau.

### 8.2. Đồng đều không giống thực tế

Sáu trạng thái không nhất thiết mỗi trạng thái 16,7%. Ví dụ:

~~~text
CONFIRMED   62%
DELIVERED   20%
PENDING     10%
CANCELLED    5%
REFUNDED     2%
FAILED       1%
~~~

Một benchmark sinh status đều sẽ đánh giá sai filter selectivity và grouping.

### 8.3. Phân bố kết hợp, không chỉ marginals

Country và paymentMethod có thể tương quan; tenant lớn có tỷ lệ orders PENDING cao. Nếu sinh từng field độc lập, query kết hợp có thể ước tính/select khác production.

### 8.4. Null/missing

Một tỷ lệ documents legacy có shippingAddress missing, một số có null, một số có object. Những kiểu này ảnh hưởng partial indexes, query semantics và response serialization.

## 9. Key popularity: uniform, hotspot và Zipf

### 9.1. Uniform

Với N keys, mỗi key có xác suất:

\[
P(i)=\frac{1}{N}.
\]

Uniform giúp tạo baseline dễ hiểu và có ích khi keys thực sự phân tán gần đều. Nhưng nhiều hệ thực tế có **một số IDs nóng**.

### 9.2. Hotspot distribution

Ví dụ:

~~~text
20% hot keys nhận 80% GET traffic.
80% cold keys nhận 20% traffic.
~~~

Không phải mọi workload đều có tỷ lệ 80/20; cần đo. Nhưng mô hình nóng/lạnh này đã bộc lộ cache locality và contention mà uniform bỏ lỡ.

### 9.3. Zipfian distribution

Một mô hình theo hạng phổ biến:

\[
P(i)=\frac{i^{-s}}{\displaystyle\sum_{j=1}^{N}j^{-s}},
\qquad i=1,\ldots,N.
\]

Trong đó i=1 là key phổ biến nhất, s điều chỉnh mức skew:

- s=0: đồng đều.
- s tăng: traffic tập trung hơn vào các key top rank.
- s gần 1 là một trường hợp phổ biến để thử workload lệch, **không phải giá trị chuẩn cho mọi hệ**.

### 9.4. Zipfian không thay dữ liệu nghiệp vụ

Chọn keys theo Zipf là bước chọn **key nào bị truy cập**. Còn record size, tenant, age và query shape cần mô hình hóa riêng hoặc có điều kiện. Không dùng Zipf trên key index rồi giả định database load thực đã được tái hiện đầy đủ.

### 9.5. Hotset có thể dịch chuyển

~~~text
09:00 hot keys = newest orders.
12:00 hot keys = active campaigns.
20:00 hot keys = evening region customers.
~~~

Một phân bố Zipf cố định suốt 6 giờ có thể không phản ánh warm-cache churn. Hãy thử moving hotset/recency distribution.

### 9.6. Hot records và hot partitions khác nhau

1.000 hot keys cùng partition có thể tạo hot shard, dù mỗi key không cực nóng. Ngược lại 1.000 hot keys được phân đều nhiều partitions có thể chịu tải tốt hơn.

Benchmark cần biết cách partition key được tính, không chỉ mức skew của full document ID.

## 10. Multi-tenant skew: ít tenant có thể chiếm phần lớn tải

Một SaaS có 10.000 tenants. Số lượng tenant không nói rõ request share hoặc storage share.

Ví dụ:

| Nhóm tenant | Tỷ lệ số tenants | Tỷ lệ stored records | Tỷ lệ traffic |
|---|---:|---:|---:|
| Enterprise | 1% | 45% | 60% |
| Growth | 9% | 35% | 25% |
| Small | 90% | 20% | 15% |

Nếu generator chia đều 1 triệu records và 100.000 requests cho mỗi nhóm tenant, test sẽ không có hot tenants.

### 10.1. Storage size và traffic share khác nhau

Một tenant rất cũ có nhiều dữ liệu nhưng QPS thấp; một tenant mới có ít data nhưng burst traffic cao. Hãy mô hình riêng:

~~~text
P(tenant in stored data)
P(tenant chosen by read)
P(tenant chosen by write)
P(record age | tenant)
~~~

### 10.2. Tenant-specific schema

Enterprise tenant có thể dùng metadata rộng và nhiều indexes; small tenant có document nhỏ. Sinh một schema size cho mọi tenant sẽ không tái hiện network/memory pressure đúng.

### 10.3. Tenant-aware cache

Một tenant phát 60% traffic có thể chiếm phần lớn cache working set, làm tenants khác bị eviction. Đo latency theo tenant tier, không chỉ p99 toàn cụm.

### 10.4. Tenant ID là partition key?

Nếu DynamoDB PK chỉ là TENANT#id cho mọi orders của một tenant lớn, có thể tạo hotspot. Benchmark phải phản ánh item collection, sort key, access distribution và giới hạn thực tế của partitioning.

### 10.5. Fairness

Khi enterprise tenant spike, small tenants có bị ảnh hưởng? SLI nên có latency/error theo nhóm tenant và workload class để không che starvation dưới trung bình.

## 11. Phân bố theo thời gian: mới, cũ, theo mùa

Nhiều hệ có read distribution theo **độ tuổi**:

~~~text
Orders mới trong 24 giờ: 50% reads.
Orders 1–30 ngày:      30% reads.
Orders 1–12 tháng:    15% reads.
Orders cũ hơn:         5% reads.
~~~

Các tỷ lệ minh họa cần được thay bằng số đo nếu có.

### 11.1. Recency và cache

Nếu 80% reads nhắm records tạo trong 48 giờ, warm cache có thể chứa gần hết working set nóng. Uniform read trên 12 tháng dữ liệu khiến hit rate thấp giả tạo.

### 11.2. Recency và storage layout

Wide-column/LSM stores có SSTables mới và cũ; time-series data thường theo buckets. Workload ghi vào partition hiện hành khác với update dữ liệu năm ngoái, xét compaction và read amplification.

### 11.3. Seasonal bursts

Black Friday/campaigns, lịch thanh toán cuối tháng và đầu giờ làm việc có thể tạo peaks. Một Poisson rate cố định không phản ánh tất cả bursts.

### 11.4. Late arrivals và backfill

Sự kiện ghi hôm nay nhưng eventTime thuộc tháng trước có thể cập nhật partitions cũ và query windows khác. Nếu generator luôn dùng eventTime=now, không đánh giá được late writes/tombstones/compaction.

### 11.5. Chọn mô hình tuổi

Có thể phối hợp:

- Uniform creation trong mỗi bucket lịch sử.
- Piecewise rate theo ngày/giờ.
- Exponential recency-decay.
- Burst creation trong campaign.

Mục tiêu là tái hiện access pattern, không phải khớp một phân bố lý thuyết bằng mọi giá.

## 12. Working set: phần dữ liệu được đọc lặp lại

**Working set** là nhóm dữ liệu được truy cập trong một cửa sổ thời gian, có thể khác nhiều so với tổng volume.

Ví dụ:

~~~text
Total canonical documents: 100 million.
Last-day active documents: 2 million.
Most GET traffic targets the active set.
~~~

### 12.1. Working set nhỏ và lớn tạo kết quả khác

Nếu warm working set vừa RAM/cache, p99 đọc có thể thấp. Khi working set vượt RAM, disk I/O, compaction interference và eviction tăng.

### 12.2. Định nghĩa theo thời gian

Working set trong 5 phút có thể là 200.000 keys, trong một ngày là 6 triệu keys. Hãy ghi rõ window thay vì chỉ nói “working set=2 triệu”.

### 12.3. Byte-weighted working set

Không chỉ đếm keys; 100.000 documents 100 KB khác 100.000 documents 1 KB.

~~~text
Working-set keys = 1 million
Average touched bytes per key = 5 KB
Approx. logical touched bytes = 5 GB
~~~

Trong thực tế caching còn index pages, decompressed blocks, overhead/headers và eviction policy, nên 5 GB không đồng nghĩa cache RAM cần đúng 5 GB.

### 12.4. Warmup cần cả dữ liệu lẫn access distribution

Nếu prewarm bằng uniform GET nhưng measured phase đọc Zipf hotset, cache state khác production. Warmup traffic nên phản ánh query mix và popularity trước khi ghi nhận latency.

## 13. Thiết kế phân bố theo quan hệ giữa các trường

Synthetic data có thể đúng histogram riêng của từng field nhưng sai quan hệ.

Ví dụ:

~~~text
Enterprise customers thường tạo orders nhiều items.
Campaign X thường bán products size lớn.
EU tenants có thời gian hoạt động khác APAC.
Pending orders thường là records rất mới.
~~~

### 13.1. Conditional sampling

Thay vì:

~~~text
tenant = randomTenant()
items = randomItemCount()
age = randomAge()
status = randomStatus()
~~~

hãy dùng:

~~~text
tenantTier = sampleTenantTier()
tenant = sampleTenant(tenantTier)
age = sampleAge(tenantTier)
status = sampleStatus(age, tenantTier)
items = sampleItemCount(tenantTier, status)
~~~

### 13.2. Correlation làm thay đổi p99

Nếu records có size lớn lại được GET ở giờ cao điểm, latency tail sẽ chịu ảnh hưởng lớn hơn so với dataset có size lớn nhưng chỉ nằm trong nhóm cold.

### 13.3. Không trộn khái niệm correlation và causation

Telemetry có thể cho thấy tenant lớn thường có size records lớn, nhưng chưa chứng minh tenant size **gây** ra size. Với benchmark, chỉ cần tái hiện phân bố chung khi nó ảnh hưởng kết quả; không khẳng định quan hệ nhân quả.

### 13.4. Tương quan với partition key

Nếu tất cả updates của một tenant vào partition hiện hành trong thời gian ngắn, backend behavior khác việc chọn random partition đều nhau. Sinh đúng key shape và routing.

## 14. Tỷ lệ đọc/ghi: một số phần trăm không đủ

Một workload “80% reads, 20% writes” còn mơ hồ:

- Read là GET 1 item hay scan 10.000 rows?
- Write là INSERT, partial UPDATE, increment, append vào array hay DELETE?
- Một UPDATE làm tăng size document bao nhiêu?
- Write có transaction, conditional guard, index updates hay outbox?
- Read có bypass cache hay trả từ Redis?
- Có background ingestion không?

### 14.1. Phân loại operations

Một bảng:

| Operation | Tỷ lệ | Target | Dung lượng logic | Truy vấn/điều kiện |
|---|---:|---|---:|---|
| Point GET | 45% | Hot/cold key mix | 1 doc | Primary key |
| Range/list GET | 20% | Tenant+time | 20 docs/page | Indexed range |
| Filter query | 5% | Status+region | 10–200 docs | Secondary index |
| INSERT | 10% | New key | 0,5–80 KB | Optional conditional |
| Partial UPDATE | 15% | Recent keys | Vài fields | CAS/version |
| DELETE/expire | 5% | Old keys | Tombstone | Retention |

Các tỷ lệ có tổng 100% theo một định nghĩa logical database operation.

### 14.2. Read mix theo chính sách cache

Nếu 45% GET được phục vụ 70% từ cache, backend GET rate khác 45% total user requests. Cần:

~~~text
Client-level mix
Cache-level hit/miss
Backend physical operation mix
~~~

### 14.3. Writes có thể tạo reads ẩn

Một conditional insert có thể yêu cầu kiểm tra trạng thái hoặc quorum coordination. Đếm chỉ một write ở client không có nghĩa backend chỉ thực hiện một I/O.

### 14.4. DELETE có thể là write

Trong LSM systems, DELETE có thể tạo tombstone, rồi compaction mới dọn vật lý. Trong MongoDB, delete index keys và replication log cũng có chi phí. Không bỏ qua DELETE vì “xóa làm dữ liệu nhỏ đi”.

## 15. Tỷ lệ theo thời gian khác tỷ lệ tổng cả ngày

Ví dụ:

| Cửa sổ | RPS tổng | Reads | Writes | Bối cảnh |
|---|---:|---:|---:|---|
| 02:00–03:00 | 2.000 | 50% | 50% | Batch import |
| 09:00–12:00 | 8.000 | 80% | 20% | Giờ làm việc |
| 19:00–20:00 | 15.000 | 90% | 10% | Campaign |
| 23:00–00:00 | 3.000 | 70% | 30% | Sync/maintenance |

Đây là dữ liệu minh họa, không phải SLA.

### 15.1. Daily-average có thể che peak

Một hệ trung bình 5.000 ops/sec trong ngày nhưng peak 15.000 ops/sec phải được test ở peak nếu mục tiêu là bảo đảm SLO.

### 15.2. Peak read và peak write có thể không trùng

Ngày quảng cáo tạo read peak; lúc đồng bộ cuối ngày tạo write peak. Hai kịch bản riêng đều cần thiết, có thể thêm kịch bản tệ nhất khi chúng chồng nhau theo thực tế.

### 15.3. Cửa sổ ngắn và bursts

Peak 1 phút và peak 1 giây có thể cao hơn trung bình 1 giờ rất nhiều. Sampling telemetry theo phút có thể không nhìn thấy microbursts làm queueing/latency tăng.

### 15.4. Mô hình traffic thay đổi có kế hoạch

~~~text
Phase A: baseline for 10 minutes.
Phase B: ramp 3,000 -> 10,000 ops/sec.
Phase C: sustained peak for 30 minutes.
Phase D: sudden 2x burst for 60 seconds.
Phase E: recovery under normal traffic.
~~~

Các mốc thời gian/rates chỉ minh họa; test thực tế chọn theo SLO, khả năng tạo tải và production profile.

## 16. Update pattern quan trọng không kém write ratio

Hai workloads đều có 20% writes nhưng rất khác:

~~~text
A: 20% INSERT immutable new records.
B: 20% UPDATE same 100 hot records.
~~~

### 16.1. Contention

UPDATE/CAS lên hot key có thể gây conflicts, retries và serialization. INSERT random keys tạo profile I/O khác.

### 16.2. Update-in-place vs append

Một system thay field status nhỏ có chi phí khác việc append thêm 1 KB vào array dài 300 KB. NoSQL engine và data model quyết định write amplification.

### 16.3. Partial update vs full replacement

~~~text
PATCH status only
PUT whole 100 KB document
~~~

Nếu production dùng full replacement nhưng benchmark chỉ update field nhỏ, network, concurrency và write costs sẽ bị đánh giá thấp.

### 16.4. Tombstones, TTL và churn

Một workload gồm 20% inserts và 20% deletes có thể giữ logical count ổn định nhưng vẫn sinh nhiều writes/compactions/tombstones. Đừng kết luận dataset ổn định nên storage overhead không thay đổi.

### 16.5. State transitions phải hợp lệ

Đối với Order:

~~~text
DRAFT -> CONFIRMED -> SHIPPED -> DELIVERED
        \-> CANCELLED
~~~

Generator nên tạo các transitions hợp lệ, vì invalid operations có thể bị reject nhanh mà không gây cùng storage load như writes thành công.

## 17. Tính dung lượng dataset và tăng trưởng

Một ước lượng logic cơ bản:

\[
V_{\text{logical}}
=\sum_{i=1}^{N}S_i
\approx N\times E[S].
\]

Nếu 20 triệu documents với mean serialized logical size 3 KB:

\[
V_{\text{logical}}\approx 20{,}000{,}000\times 3\text{ KB}
=60\text{ GB}
\]

theo quy ước KB thập phân trong ví dụ. Đây **chưa phải** disk allocation.

### 17.1. Dung lượng mỗi loại record

Một ứng dụng có:

~~~text
Orders:        20 million records × 3 KB
Order events: 100 million records × 0.5 KB
Customers:     2 million records × 1.5 KB
~~~

Logical values khoảng:

~~~text
Orders:       60 GB
Order events: 50 GB
Customers:     3 GB
Total:       113 GB
~~~

Đó mới là ước lượng payload, chưa có indexes, replication, compression, tombstones, temp files và backups.

### 17.2. Tính index storage riêng

Nếu index thứ cấp giữ tenantId/status/createdAt, storage per indexed entry thay đổi theo engine và value cardinality. Đừng giả định index size bằng 0 hoặc một tỷ lệ cố định không được đo.

### 17.3. Replication factor

Nếu database lưu RF=3, có ba replicas của nhiều phần dữ liệu trong cluster, nhưng không thể đơn giản nhân mọi con số (cache, object metadata, compression, index) đúng 3 mà bỏ qua placement và engine. Dùng RF để ước lượng sơ bộ, sau đó lấy measured per-node disk usage.

### 17.4. Headroom và compaction temporary space

LSM engines có thể cần thêm disk để flush/compaction/repair và giữ snapshots. Bài test chạy ở disk usage 10% không phản ánh rủi ro khi cluster đã 75% đầy.

### 17.5. Đơn vị phải nhất quán

MB/GB có thể được hiểu theo decimal (10^6/10^9) hoặc binary (MiB/GiB). Trong báo cáo ghi rõ đơn vị; việc nhầm GB và GiB có thể tạo sai số đáng kể khi sizing nhiều TB.

## 18. Dung lượng không chỉ là hiện tại: retention và thời gian tồn tại

Giả sử có 2.000 inserts/giây, mỗi record trung bình 1 KB.

Một ngày có:

\[
2{,}000\times 86{,}400=172{,}800{,}000\text{ inserts/ngày}.
\]

Logical ingest khoảng 172,8 GB/ngày với đơn vị KB thập phân và bỏ qua metadata.

### 18.1. Retention làm thay đổi size toàn hệ

Nếu giữ 30 ngày với dòng dữ liệu tương đối ổn định, chỉ tính payload mới có thể khoảng:

\[
172.8\times 30 = 5{,}184\text{ GB}.
\]

Đây không phải dung lượng tối thiểu cần cấp cho cụm khi có replication/index/compaction.

### 18.2. TTL không có nghĩa xóa vật lý đúng hạn

Một số NoSQL xử lý TTL/tombstones và cleanup bất đồng bộ. Dataset ở steady state sau nhiều ngày không nhất thiết có on-disk bytes giống tính toán “inserts/day × TTL days”.

### 18.3. Data lifecycle

~~~text
CREATED -> ACTIVE -> ARCHIVED -> EXPIRED -> PHYSICALLY_REMOVED
~~~

Benchmark cần có records ở từng trạng thái và background jobs tác động tương ứng.

### 18.4. Tỷ lệ overwrite vs append

Nếu 20% writes là update thay giá trị cũ, logical document count không tăng tương ứng write ops. Nhưng disk/memory bandwidth vẫn bị tiêu thụ.

### 18.5. Dataset mới tinh không phản ánh dữ liệu già

Một cụm vừa được bulk insert chưa trải qua hàng tuần compaction, tombstones, index churn và backups. Nếu mục tiêu steady state, cần tạo tuổi đời/độ phân mảnh phù hợp hoặc chạy đủ các maintenance cycles trong điều kiện cho phép.

## 19. Data model quyết định chi phí đo tải

Hãy sinh dữ liệu theo **schema dự kiến chạy thật**, không chỉ bảng key/value đơn giản.

### 19.1. Document NoSQL

~~~json
{
  "tenantId": "T17",
  "orderId": "O101",
  "customerId": "U801",
  "status": "CONFIRMED",
  "totalMinor": 150000,
  "createdAt": "2026-11-14T08:00:00Z",
  "items": [
    {"sku": "SKU-01", "quantity": 2, "unitPriceMinor": 75000}
  ],
  "shipping": {"country": "VN", "city": "Hồ Chí Minh"},
  "attributes": {"source": "mobile"}
}
~~~

Đây là JSON minh họa, không có nghĩa các trường trong storage luôn là BSON String. Khi dùng MongoDB, việc chọn BSON DateTime/Decimal128/Int64 có thể ảnh hưởng serialization, query và index.

### 19.2. Access-pattern table

Trong Cassandra:

~~~text
orders_by_customer((tenantId,customerId),createdAt,orderId)
~~~

Các rows phải được sinh đúng phân bố partition width. 1 triệu rows trải đều 1 triệu partitions khác 1 triệu rows của một customer partition.

### 19.3. Composite key trong DynamoDB

~~~text
PK = TENANT#T17#CUSTOMER#U801
SK = ORDER#2026-11-14T08:00:00Z#O101
~~~

Nếu một hot customer ghi 5.000 orders/giây lên cùng partition key, kết quả khác nhiều keys rải đều.

### 19.4. Redis cache

Không chỉ sinh một key Redis cho mỗi document. Mô hình hóa:

~~~text
cache order summary
cache product details
negative cache keys
session keys
rate-limit counters
~~~

Mỗi loại có TTL, size, hit rate và update pattern riêng.

### 19.5. Dữ liệu hợp lệ cho query

Nếu benchmark hỏi orders_by_customer nhưng generator tạo customerId không nhất quán với orders_by_id, query có thể trả rỗng, làm p99 rất đẹp vì engine không đọc dữ liệu.

## 20. Referential consistency trong dữ liệu tổng hợp

NoSQL thường không enforce foreign key như relational database, nhưng application có các quan hệ logic.

### 20.1. Tạo entity theo thứ tự

~~~text
1. Generate tenants.
2. Generate customers within tenants.
3. Generate products.
4. Generate orders referencing valid customers/products.
5. Generate order events and payments referencing orders.
~~~

### 20.2. Các quan hệ phải phản ánh tỷ lệ thực tế

Một customer có 1 order hay 50.000 orders ảnh hưởng partition width, read query và update hotspot. Không chọn ngẫu nhiên đều customerId cho mỗi order nếu sản phẩm thực có power users.

### 20.3. Tỷ lệ orphan hoặc missing có chủ đích

Nếu production có 0,2% events mất parent do lịch sử/migration, có thể tạo scenario riêng để xem error path. Đừng để 80% dữ liệu vô tình orphan rồi gọi đó là representative.

### 20.4. Business constraints

Đơn hàng total có thể được tính từ line items, currency phù hợp, quantity dương và status hợp lệ. Một benchmark tạo nhiều invalid writes sẽ đo tốc độ validation rejection thay vì write throughput.

### 20.5. Duplicate IDs

Chỉ sinh duplicate key khi kiểm tra conflict handling/conditional write. Nếu load test bulk insert vô tình trùng IDs, tỷ lệ lỗi và kích thước dataset sau seed sẽ khác dự kiến.

## 21. Phân bố kết quả trả về và negative queries

Một workload read có thể bao gồm:

~~~text
85% GET existing key
10% GET previously deleted key
 5% GET never-existing key
~~~

### 21.1. Positive cache hit

Reads tới existing hot keys thường được cache; source QPS thấp hơn API QPS.

### 21.2. Negative cache hit

Reads tới missing hot keys có thể được negative-cache. Nếu tất cả benchmark reads đều existing, không đo được cache penetration/error-path.

### 21.3. 404 khác timeout

Source NOT_FOUND hợp lệ có chi phí khác timeout/retry; không biến errors thành missing records chỉ để giữ tỷ lệ kết quả thành công.

### 21.4. Search zero hits

Một query filter có thể trả 0/1/1000 rows. Cần phân bố result cardinality phù hợp, không chỉ sinh query luôn match đúng một record.

### 21.5. Empty page và deep pagination

Page đầu có 50 records thường nhanh hơn page 10.000 với offset/skip sâu ở một số access patterns. Benchmark phải bao gồm paging depth thực tế hoặc thiết kế cursor.

## 22. Read/write byte ratio khác read/write operation ratio

Ví dụ:

~~~text
90% GET operations, mỗi GET trả 1 KB.
10% INSERT operations, mỗi INSERT ghi 100 KB.
~~~

Trên 100 operations:

~~~text
Read logical payload: 90 × 1 KB = 90 KB.
Write logical payload: 10 × 100 KB = 1,000 KB.
~~~

Mặc dù “90% reads”, **logical payload bytes của writes lớn gấp khoảng 11,1 lần reads** trong ví dụ. Backend write amplification/replication còn có thể làm write I/O cao hơn.

### 22.1. Mô hình thêm bytes/sec

Đối với từng operation class c:

\[
\text{LogicalBytesPerSecond}
=\sum_c \lambda_c E[B_c].
\]

Trong đó \(\lambda_c\) là operations/sec và \(E[B_c]\) là bytes trung bình của payload liên quan class đó.

### 22.2. Tách network vs storage I/O

Một GET trả 1 KB có thể khiến backend đọc nhiều index/data blocks. Một UPDATE 100-byte field có thể ghi nhiều blocks/index entries. Logical bytes không là số physical I/O.

### 22.3. Tính tail size

Mean bytes/sec chưa phản ánh việc một số requests trả 10 MB. Hãy đo histogram request/response bytes và gắn latency với payload bucket.

## 23. Index và query selectivity phải được tái hiện

Giả sử MongoDB có index theo:

~~~text
(tenantId, status, createdAt)
~~~

Một query:

~~~text
tenantId=T17
status=PENDING
createdAt in last 7 days
limit=50
~~~

có hiệu năng phụ thuộc:

- Số records của tenant T17.
- Tỷ lệ PENDING của tenant đó.
- Phân bố createdAt.
- Sort/pagination.
- Records được index cover hay phải fetch full document.

### 23.1. Query luôn unique là bài test khác

Nếu generator biến status thành một giá trị gần unique để mọi query match 1 row, index selectivity sẽ đẹp hơn thực tế.

### 23.2. Composite predicates và tương quan

Điều kiện tenantId/status có thể tương quan. Dùng chỉ NDV riêng từng field để sinh data có thể tạo result counts rất khác production.

### 23.3. Covering/index-only paths

Một API list chỉ lấy fields trong index có thể nhanh hơn full document fetch. Không dùng projected query cho mọi reads nếu production trả nested object.

### 23.4. Index build timing

Benchmark insert khi chưa tạo secondary indexes không phản ánh write overhead sau khi index tồn tại. Cần tách:

~~~text
Bulk load without secondary indexes (setup)
Build indexes (maintenance phase)
Measure writes with indexes active (steady state)
~~~

### 23.5. Query plan may change with data volume

Ở 10.000 records, scan có thể đủ nhanh; ở 100 triệu records, plan/index và memory pressure khác. Dataset nhỏ hơn production có thể làm optimization quyết định sai.

## 24. Hotspot ở partition và shard

Các hệ NoSQL thường phân phối dữ liệu theo partition/shard keys.

### 24.1. Partition key kém

~~~text
PK = day="2026-11-14"
~~~

Nếu mọi writes hôm nay vào cùng logical partition, partition rộng/hot dù cluster có nhiều nodes.

### 24.2. Phân vùng theo bucket

~~~text
PK = (day, bucket=hash(userId)%32)
~~~

có thể phân tán traffic nhưng tăng fan-out queries và complexity. Benchmark phải đo cả writes lẫn queries sau thay đổi data model.

### 24.3. Hot item

Một counter item được update 10.000 lần/giây có thể bị contention/throttle, dù 1 triệu items khác hầu như idle.

### 24.4. Skew theo key range

Nếu database có range sharding hoặc sort-key locality, một dải timestamp tăng dần có thể tập trung writes. Không giả định random UUID distribution phản ánh sequential key workload.

### 24.5. Metrics per shard/partition

Toàn cụm CPU 40% không nói không có vấn đề: một shard có thể CPU 100% hoặc network/IO saturated. Đo per-node, per-partition/top-key metrics nếu engine cung cấp.

## 25. TTL, tombstone và dọn dữ liệu ảnh hưởng benchmark

Một dataset vừa seed không có nhiều tombstones. Production có thể có:

~~~text
20% records bị xóa/expire theo vòng đời.
15% keys được overwrite nhiều lần.
Background compaction/cleanup vẫn chạy.
~~~

### 25.1. TTL expiration không nhất thiết xóa vật lý ngay

Logical reads có thể coi data expired trước khi storage disk được thu hồi. Cần hiểu semantics engine và retention.

### 25.2. Tombstones ảnh hưởng reads

Trong một số LSM paths, nhiều tombstones/versions có thể tăng read amplification hoặc scan cost. Dataset sạch có thể làm đánh giá thấp tail latency.

### 25.3. Compaction write amplification

LSM merges tạo I/O nền; test chạy 1 phút sau ingest có thể chưa phản ánh compaction backlog. Để đánh giá sustained ingest, phải theo dõi throughput và backlog đủ lâu.

### 25.4. Temporary disk headroom

Compaction/rebuild cần dung lượng trống. Benchmark không nên chỉ kiểm tra disk consumption lúc bắt đầu mà bỏ qua peak storage demand.

### 25.5. Khi cần test maintenance scenario riêng

Chạy TTL sweep, index rebuild, backup snapshot hoặc repair trong môi trường test được kiểm soát để xem read/write latency khi tác vụ nền chồng tải.

## 26. Generator cần mô tả distribution, không chỉ random

Một dữ liệu sinh đại diện cần có **bản mô tả cấu hình độc lập**:

~~~yaml
seed: 20261114
dataset:
  tenants: 10000
  orderCount: 20000000
  orderSizeModel:
    smallProbability: 0.80
    mediumProbability: 0.17
    largeProbability: 0.03
  orderAge:
    pastDays: 365
traffic:
  keyPopularity: zipf
  zipfExponent: 0.9
  readHotsetDays: 7
  readRatio: 0.70
  writeRatio: 0.30
~~~

Đây là YAML mô tả ý định, **không phải cấu hình của một benchmark tool cụ thể**. Khi hiện thực, nên tách details như key distribution, operation weights và phasing thành schema được validate.

### 26.1. Seed cố định

Chọn random seed cố định để có thể tái tạo cùng dataset khi so sánh hai phiên bản schema hoặc database.

### 26.2. Không chỉ lưu seed

Một seed không đủ nếu:

- Generator code đã đổi.
- Số threads/chunk order đã đổi.
- Random draws phụ thuộc thứ tự scheduling.
- Time.now được gọi ở các thời điểm khác nhau.

Ghi cả generator version, config hash, snapshot cutoff, ordering và execution environment.

### 26.3. Stable per-record generation

Một lựa chọn reproducible:

~~~text
recordSeed = mix(globalSeed, tenantId, recordOrdinal)
~~~

Mỗi record sinh từ seed xác định bởi identity, không phụ thuộc worker nào tạo trước. Điều này hữu ích khi seed song song nhiều partitions.

### 26.4. Phân phối lỗi có chủ đích

Nên có tỷ lệ invalid operations, duplicate IDs hoặc unavailable reads **riêng** khi đo error handling. Không trộn 30% invalid writes vào throughput baseline mà không biết.

### 26.5. Lưu histogram mục tiêu và số sinh ra

Generator được giao “1% documents >64 KB” nhưng có thể phát sinh chỉ 0,1% do bug/rounding. Báo cáo nên nêu cả target distribution và observed distribution sau generation.

## 27. Java: sinh kích thước record theo mixture

Một ví dụ đơn giản dùng JDK, nhằm minh họa **cách chọn bucket**:

~~~java
import java.util.SplittableRandom;

public final class SizeSampler {
    private final SplittableRandom random;

    public SizeSampler(long seed) {
        this.random = new SplittableRandom(seed);
    }

    public int nextPayloadSizeBytes() {
        double p = random.nextDouble();
        if (p < 0.80) {
            return random.nextInt(512, 4097);         // Small
        }
        if (p < 0.97) {
            return random.nextInt(4096, 32769);       // Medium
        }
        return random.nextInt(32768, 262145);         // Large
    }
}
~~~

### 27.1. Đây là bucket-uniform, không phải measured size distribution

Trong mỗi bucket, ví dụ chọn đều trong một khoảng bytes. Nếu production có log-normal hoặc heavy tail **bên trong** bucket, cần samplers khác.

### 27.2. Payload target và serialized size

Nếu generator trả targetBytes=4.096, chưa có nghĩa BSON/JSON document sau serialization đúng 4.096 bytes. Field names, nested documents và metadata tạo overhead; cần đo serialized bytes thực tế.

### 27.3. Tránh đệm một String lặp

Không cứ tạo body bằng 4.096 ký tự 'A'. Thay vào đó sinh fields/nested lists và text có entropy đại diện, rồi điều chỉnh mức độ dài theo mục tiêu.

### 27.4. Kiểm tra giới hạn record

Nếu target size vượt item limit của engine, không cố insert rồi đo failure như throughput. Hoặc đặt scenario riêng cho boundary validation.

## 28. Java: chọn hot/cold keys có kiểm soát

Một sampler theo kiểu 80/20:

~~~java
import java.util.SplittableRandom;

public final class KeySampler {
    private final SplittableRandom random;
    private final long hotKeyCount;
    private final long totalKeys;

    public KeySampler(
            long seed,
            long totalKeys,
            double hotFraction
    ) {
        if (totalKeys < 2 || hotFraction <= 0 || hotFraction >= 1) {
            throw new IllegalArgumentException("invalid key configuration");
        }
        this.random = new SplittableRandom(seed);
        this.totalKeys = totalKeys;
        this.hotKeyCount = Math.max(1, Math.min(
                totalKeys - 1,
                (long) Math.floor(totalKeys * hotFraction)
        ));
    }

    public long nextKey() {
        if (random.nextDouble() < 0.80) {
            return random.nextLong(hotKeyCount);
        }
        return hotKeyCount
                + random.nextLong(totalKeys - hotKeyCount);
    }
}
~~~

Đoạn này có **hotFraction keys nhận 80% attempts**; chỉ khi hotFraction=0.20 mới đúng ví dụ 80/20. Với các tỷ lệ khác, đây là mô hình hot/cold tổng quát.

### 28.1. Không phải Zipf

Trong hot subset, các keys được chọn đều nhau. Zipf theo rank tạo đường cong liên tục và có thể tập trung cực mạnh vào top 1.

### 28.2. Key age/tenant cần được nối

Nếu hotKeyCount luôn là phần đầu key range, keys nóng có thể chính là keys cũ nhất. Production có thể nóng ở records mới nhất; khi đó cần ánh xạ hot key ranks sang IDs theo age.

### 28.3. Mối quan hệ key và partition

Hãy tính partition key của mỗi selected key và kiểm tra request share theo partition, không chỉ theo entityId.

### 28.4. Hotset moving

Một workload dài có thể đổi mapping hot keys mỗi 10 phút để mô phỏng trends/campaigns. Không thay ngẫu nhiên quá nhanh nếu production hotset giữ ổn định vài giờ.

## 29. Java: chọn operation theo tỷ lệ

Ví dụ phân loại:

~~~java
import java.util.SplittableRandom;

public enum Operation {
    POINT_READ,
    RANGE_READ,
    INSERT,
    UPDATE,
    DELETE
}

public final class OperationSampler {
    private final SplittableRandom random;

    public OperationSampler(long seed) {
        this.random = new SplittableRandom(seed);
    }

    public Operation next() {
        double p = random.nextDouble();
        if (p < 0.45) return Operation.POINT_READ;
        if (p < 0.70) return Operation.RANGE_READ;
        if (p < 0.80) return Operation.INSERT;
        if (p < 0.95) return Operation.UPDATE;
        return Operation.DELETE;
    }
}
~~~

### 29.1. Chỉ là bước đầu

Sampler chưa quyết định:

- Read positive hay missing?
- Point read chọn key theo Zipf/recency?
- Range read chọn tenant nào và page size?
- UPDATE chọn field nào, tăng kích thước ra sao?
- DELETE có tombstone, retention, cleanup policy gì?

### 29.2. Logical operation phải tạo ra request thật

Benchmark không nên đếm một no-op validation rejection như một successful write. Trong output, tách attempted, accepted, committed và rejected operations.

### 29.3. Phân bố thay đổi theo phase

Một sampler cố định 45/25/10/15/5 có thể dùng cho baseline, nhưng peak import phase cần weights khác. Lưu phase config riêng và record timestamps để giải thích kết quả.

## 30. Sinh JSON/BSON có cấu trúc thay vì “value bytes”

Một generator Order có thể dùng:

~~~text
tenantId sampled from tenant population.
customerId sampled within tenant.
createdAt sampled from tenant age distribution.
status sampled conditional on age.
itemCount sampled conditional on tenant tier.
itemPrices sampled from currency-specific price distribution.
totalMinor computed from item prices/quantities/discounts.
metadata fields selected by schema version.
~~~

### 30.1. Tổng tiền phải khớp line items

Nếu totalMinor được random độc lập với lineItem prices, business invariant có thể reject many writes hoặc mọi records trở nên vô nghĩa đối với API.

### 30.2. Trường thời gian

Nguồn thời gian phải nhất quán:

~~~text
createdAt <= updatedAt
paidAt >= createdAt when status=PAID
deletedAt present only if deleted
~~~

### 30.3. Nested arrays ảnh hưởng size/tần suất update

Nếu production thường append lineItem hoặc thêm metadata, generator cần thực hiện cùng update shape chứ không chỉ tạo document lúc đầu.

### 30.4. Định danh cần ổn định

Nếu INSERT request có retry, operationId phải giữ nguyên giữa attempts khi test idempotency. Nếu mỗi retry sinh ID mới, benchmark thay đổi semantics business.

### 30.5. Format output theo engine

Với MongoDB, ghi BSON với đúng numeric/date types; với DynamoDB, Number/String/Map/List đúng schema; với Cassandra, CQL type binding; với Redis, đúng serialization/TTL.

## 31. Vì sao phải seed dữ liệu trước khi đo

Một dataset trống có nhiều đặc điểm khác production:

- Indexes nhỏ và gần như hoàn toàn trong memory.
- Không có aged records hoặc fragmentation.
- Không có tombstones/expired data.
- Cache không có lịch sử truy cập.
- Không có phân bố tenants/hot keys ổn định.

### 31.1. Bulk-load phase

~~~text
Step 1: create schema and indexes according to test plan.
Step 2: generate base population.
Step 3: ingest/verify record count, type distribution.
Step 4: run maintenance and wait for stable baseline as appropriate.
Step 5: warm workload, then measure.
~~~

### 31.2. Index timing phải được báo cáo

Đo “ingest 10 triệu docs không indexes rồi build index sau” là bài toán khác “sustained inserts với 5 secondary indexes online”.

### 31.3. Preload và data placement

Trong distributed database, seed nhanh vào ít partitions hoặc một node có thể làm data placement không đại diện. Sau seeding, quan sát disk, shard/replica distribution, compaction/rebalance.

### 31.4. Dataset không được biến mất giữa các runs

Nếu run A bắt đầu với data 10 triệu docs nhưng run B bắt đầu 15 triệu do writes chưa được reset, so sánh p99 sẽ không công bằng. Cần reset từ snapshot hoặc lập kế hoạch sequence với recorded state.

### 31.5. Warmup không được tính chung nếu mục tiêu steady state

Nếu báo cáo steady-state p99, giai đoạn cache warm/index initialization/JIT warming phải được gắn nhãn riêng. Đồng thời cold-start performance có thể là một bài test độc lập cần thiết.

## 32. Cold-cache, warm-cache và mixed-cache

### 32.1. Cold-cache

Cache chưa có working set; nhiều reads xuống database. Dùng khi đánh giá restart/recovery, cold deployment hoặc cache outage.

### 32.2. Warm-cache

Cache chứa những keys được đọc thường xuyên theo đúng popularity distribution. Hữu ích cho trạng thái hoạt động bình thường.

### 32.3. Mixed-cache

Một phần keys đã warm, một phần là data mới, random misses và moving hotset. Đây có thể là kịch bản phản ánh production hơn hoàn toàn cold/warm.

### 32.4. Không làm cold-cache giả tạo sai mục tiêu

Không FLUSHALL Redis của một môi trường dùng chung chỉ để có cold-cache. Dùng test cache riêng hoặc dựng môi trường có kiểm soát; bảo đảm có quyền và kế hoạch khôi phục.

### 32.5. Cache size ratio

Thay vì ghi “Redis RAM 16 GB”, hãy báo:

~~~text
Working-set logical bytes = 24 GB.
Cache effective capacity estimate = 12 GB.
Key popularity Zipf s=0.9.
Observed cache hit rate = 72%.
~~~

Các số minh họa; actual memory overhead, serialization và eviction policy cần được đo.

## 33. Open-loop và closed-loop load generation

### 33.1. Closed-loop

Một client gửi request, chờ phản hồi, rồi mới gửi request kế tiếp:

~~~text
send -> wait -> send -> wait -> ...
~~~

Khi server chậm, client tự giảm rate. Điều này có thể làm throughput quan sát trông ổn định dù hệ không đáp ứng được **arrival rate** người dùng mong muốn.

### 33.2. Open-loop

Generator cố gắng phát requests theo lịch đến:

~~~text
scheduled arrivals at target rate
-> requests may overlap
-> queue and latency expose saturation
~~~

Open-loop phù hợp khi mục tiêu là xem hệ chịu arrival rate cố định/biến thiên như thế nào.

### 33.3. Open-loop không có nghĩa gửi vô hạn

Load generator vẫn cần bounded queue, max outstanding, deadline và ghi nhận dropped/late requests. Nếu generator tự quá tải, kết quả không thể quy cho database.

### 33.4. Little's Law

Ở điều kiện ổn định:

\[
L=\lambda W.
\]

Trong đó L là số công việc đồng thời trung bình, \(\lambda\) là throughput hoàn tất hoặc arrival rate trong steady state ổn định, W là thời gian trung bình trong hệ.

Ví dụ ở 5.000 ops/sec và mean latency 20 ms:

\[
L = 5{,}000\times 0.020 = 100.
\]

Khoảng 100 in-flight operations trung bình trong mô hình ổn định. Khi backlog tăng không giới hạn, điều kiện ổn định không còn nên không dùng công thức đơn giản này để biện minh hệ đã đạt SLO.

### 33.5. Chọn theo câu hỏi

Closed-loop có ích khi muốn mô hình số clients hữu hạn và think time; open-loop tốt cho arrival-rate SLO. Có thể dùng cả hai như hai bài test khác nhau, ghi rõ semantics.

## 34. Coordinated omission: latency bị đo thấp khi hệ chậm

**Coordinated omission** xảy ra khi generator chỉ ghi nhận những request đã được gửi, nhưng vì nó chờ hệ trả lời nên bỏ qua những arrivals lẽ ra đã xảy ra trong khoảng hệ chậm.

Ví dụ:

~~~text
Target: 1 request mỗi 10 ms.
Server treo 1 giây.
Closed-loop client đợi, không gửi 100 requests dự kiến.
Metric chỉ thấy một request mất 1 giây.
~~~

### 34.1. Vì sao sai?

Người dùng/arrival stream thật có thể tiếp tục tới, tạo queue. Việc không gửi các requests dự kiến khiến latency histogram bỏ qua tác động đến những arrivals đó.

### 34.2. Ghi scheduled start time

Một open-loop generator có thể ghi:

~~~text
scheduledAt
actualSentAt
completedAt
~~~

và phân biệt scheduling delay với service duration/end-to-end latency.

### 34.3. Các bộ đo có cơ chế correction

Một số load/latency tools có chế độ correction theo expected interval. Nhưng correction không thay việc hiểu generator có thực sự phát đủ tải hay không. Luôn báo requested, attempted, completed, timed out và dropped rates.

### 34.4. Tail latency

Đo p50/p95/p99/p99.9, maximum có ý nghĩa theo sample size và confidence. Một test 100 requests không đủ đại diện p99.9; tăng sample size và giữ thời gian đo thích hợp.

### 34.5. Timeout là một kết quả, không được loại khỏi histogram

Nếu 5% requests timeout, báo p99 chỉ trên 95% successes sẽ che vi phạm SLO. Tách successful latency distribution và failure/timeout rates, tính service-level SLO theo định nghĩa.

## 35. Kiểm soát load generator là một phần của thực nghiệm

### 35.1. Đừng để generator là bottleneck

Nếu Java load client CPU 100%, networking exhausted hoặc GC pause, backend throughput thấp có thể do generator, không phải NoSQL.

### 35.2. Nơi đặt generator

Client trong cùng machine với database khác client đi qua network thật. Đo riêng network latency, TLS, serialization, connection pools và cross-AZ/Region paths theo deployment thực.

### 35.3. Connection pooling

Một benchmark mỗi request mở TCP connection mới sẽ không giống Java service dùng driver pool. Ngược lại pool chỉ có 2 connections cũng có thể làm bottleneck giả.

### 35.4. Async và blocking clients

Async driver có thể duy trì nhiều in-flight operations với ít threads, nhưng không làm queries miễn phí. Đo queue depth, outstanding futures và timeout policy.

### 35.5. Tránh test request payload đã bị thay

Một generator dùng Gson/Jackson serializer khác application thật có thể tạo BSON/JSON types, nesting và bytes khác. Khi benchmark end-to-end, dùng đường API/driver thực hoặc chứng minh serialization equivalence.

### 35.6. Báo actual arrival rate

Nếu target 20.000 ops/sec nhưng generator chỉ gửi 12.000 ops/sec, không được báo database “đạt SLO ở 20.000” dù cấu hình target ghi như vậy.

## 36. MongoDB: document size, arrays, indexes và query shape

MongoDB phù hợp nhiều document workloads, nhưng một benchmark chỉ INSERT những documents phẳng 1 KB sẽ không thể hiện:

- Embedded arrays dài và variable-length fields.
- Một collection có nhiều secondary indexes.
- Query theo tenant/status/date và sort.
- Partial update vs full document replacement.
- Read preference/read concern/write concern.
- Shard key distribution và jumbo/hot ranges.
- TTL indexes và background cleanup.

### 36.1. Dataset minh họa

~~~json
{
  "tenantId": "T17",
  "orderId": "O101",
  "customerId": "U801",
  "status": "CONFIRMED",
  "createdAt": {"$date": "2026-11-14T08:00:00Z"},
  "totalMinor": {"$numberLong": "150000"},
  "items": [
    {"sku": "SKU-01", "quantity": 2, "unitPriceMinor": 75000}
  ]
}
~~~

Đây là Extended JSON minh họa types, không phải mặc định mọi JSON file sẽ được insert giữ nguyên BSON type nếu loader không parse Extended JSON.

### 36.2. Query classes

~~~javascript
db.orders.findOne({tenantId: "T17", orderId: "O101"});

db.orders.find({
  tenantId: "T17",
  status: "PENDING",
  createdAt: {$gte: startDate, $lt: endDate}
}).sort({createdAt: -1}).limit(50);
~~~

Generator cần tạo distribution cho tenantId, status, createdAt sao cho query thực có selectivity đại diện.

### 36.3. Multikey index

Index trên fields trong array có semantics và storage cost khác scalar index. Nếu 1% orders có 500 items, index fan-out có thể ảnh hưởng đáng kể; không bỏ tail.

### 36.4. Sharding

Nếu shard key chỉ tenantId, tập trung tenants lớn; nếu hashed key, range query có thể cần fan-out. Benchmark phải chạy đúng shard key/indexes và query routing.

### 36.5. Đọc từ replica

Read preference/concern có thể thay đổi latency và freshness. Không dùng secondary reads để báo p99 low latency rồi bỏ qua tỷ lệ stale/missing nếu API cần read-your-writes.

### 36.6. Document growth

Partial updates làm document lớn dần có thể có chi phí khác updates trạng thái kích thước cố định. Sinh tuổi đời và growth distribution.

## 37. DynamoDB: key access, item size và hot partition

DynamoDB vận hành theo key/item/access pattern; một benchmark cần làm rõ:

- Partition key/sort key design.
- Point GetItem vs Query vs Scan.
- Item size theo distribution.
- Read/write consistency.
- Conditional writes, transactions, TTL.
- Secondary indexes và write amplification.
- Provisioned/on-demand capacity, throttling và account/table limits của deployment.

### 37.1. Ví dụ key shape

~~~text
PK = TENANT#T17#CUSTOMER#U801
SK = ORDER#2026-11-14T08:00:00Z#O101
~~~

Nếu 60% requests vào T17 nhưng còn được rải qua hàng nghìn customer keys, kết quả khác 60% requests dồn vào một PK duy nhất.

### 37.2. Item size và capacity

DynamoDB có cơ chế tính capacity theo kích thước item/consistency/API. Một item vài trăm bytes khác item vài trăm KB, dù cả hai là một PutItem.

Không dự đoán capacity chỉ từ 10.000 operations/sec mà bỏ item-size histogram. Với giao dịch và GSI, chi phí có thể khác non-transactional base table writes.

### 37.3. Query result pages

Một Query có pagination và size limits theo API; đọc 1.000 items có thể cần nhiều requests vật lý, không phải một read operation chỉ vì business API trả một danh sách.

### 37.4. GSI selectivity

Queries qua GSI có projection và consistency khác base table. Tạo dữ liệu đúng value distribution ở index key; không dùng empty results làm benchmark thay cho query thật.

### 37.5. Hot key và adaptive behavior

Phân bố key skew có thể gây throttling/latency. Hệ có cơ chế partitioning/adaptive behavior riêng nhưng không nên giả định nó hấp thụ mọi hot key. Cần đo actual throttles, consumed capacity, retries và p99.

### 37.6. Reserved capacity và costs

Nếu so sánh schema A/B trên DynamoDB, cần ghi capacity mode, GSI count, transactional vs standard APIs và request costs. Tốc độ cao ở cấu hình cost gấp nhiều lần không phải một cải thiện miễn phí.

## 38. Cassandra/ScyllaDB: partition width, LSM và consistency

Một bảng wide-column:

~~~sql
CREATE TABLE orders_by_customer (
  tenant_id text,
  customer_id text,
  created_at timestamp,
  order_id text,
  status text,
  total_minor bigint,
  PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC);
~~~

### 38.1. Partition width distribution

Nếu 80% customers có 1–5 orders, 19% có 6–100 và 1% có nhiều nghìn orders, cần mô hình hóa phân bố này. Uniform rows/partition che large partition read/compaction.

### 38.2. Read pattern

~~~sql
SELECT created_at, order_id, status
FROM orders_by_customer
WHERE tenant_id = ?
  AND customer_id = ?
LIMIT 50;
~~~

khác với:

~~~sql
SELECT * FROM orders_by_customer
WHERE tenant_id = ? AND customer_id = ?;
~~~

Truy vấn full partition cho power user tạo network/heap pressure khác pagination.

### 38.3. LSM steady state

Bulk ingest ban đầu tạo SSTables, rồi writes/update/delete tạo nhiều versions/tombstones; compaction strategy ảnh hưởng disk/network I/O. Long-run test cần quan sát compaction backlog, read/write amplification và write stalls.

### 38.4. TTL/time-window data

Nếu TTL 7 ngày và dữ liệu được ghi theo time buckets, need include expired data/late writes, không chỉ new live rows.

### 38.5. Consistency and replication

Đo với CL và replication factor của ứng dụng. Một ONE read và QUORUM read có latency/availability/freshness khác nhau; không so trực tiếp mà bỏ qua correctness contract.

### 38.6. Batch/LWT

Nếu production có LWT/conditional claims hoặc logged batches, benchmark write thường không thay được. Đo riêng conflicts, retry rate, coordinator load và cross-partition effects.

## 39. Redis: key distribution, TTL, cache churn và memory

Redis có thể là cache, queue, rate-limit store hoặc giữ operational state tùy architecture. Workload phải tương ứng mục đích.

### 39.1. Giá trị Redis không đồng nhất

~~~text
product:detail      -> JSON String 2–20 KB
order:summary       -> Hash 100 B–2 KB
user:session        -> String 0.5–5 KB
notfound:product    -> Small negative sentinel, TTL seconds
rank:products       -> Sorted Set
~~~

### 39.2. Key popularity và eviction

Zipf distribution cùng cache capacity quyết định hit rate/churn. Uniform keys có thể làm hit rate thấp giả so với hot catalog; ngược lại workload toàn một hot key làm cache kết quả quá đẹp.

### 39.3. TTL distribution

Không set mọi cache key TTL 300 giây nếu production dùng:

~~~text
session 30 min
product 5 min
negative 5 sec
temporary rate-limit bucket 1 min
~~~

Số keys expiring mỗi giây ảnh hưởng expiration/eviction and cache misses.

### 39.4. Memory footprint

Redis key/value overhead có thể lớn so với payload rất nhỏ. 10 triệu negative sentinels một byte không chỉ tốn 10 MB RAM.

### 39.5. Benchmark hit rate phải xuất phát từ workload

Ép “cache hit rate = 95%” bằng cách gửi cùng key liên tục có thể không phản ánh production. Sinh key popularity, working-set size và TTL hợp lý rồi **quan sát hit rate**; nếu dùng fixed hit target, cần ghi đó là scenario riêng.

### 39.6. Multi-level cache

Ứng dụng Java có local Caffeine trước Redis. Một GET local cache hit không xuất hiện trong Redis metrics. Phải đo request rates ở từng tầng nếu đang sizing cluster Redis/NoSQL.

## 40. Search/analytics workloads không phải point reads

Một hệ OpenSearch/Elasticsearch hoặc analytics projection có:

~~~text
Full-text query
Filters + sort
Aggregations
Top-k search
Deep pagination/scroll
Index refresh
Bulk indexing
~~~

### 40.1. Corpus vocabulary distribution

Tạo 1 triệu documents có cùng content “test document” không mô phỏng term frequency, field length, analyzers và inverted index của corpus thật.

### 40.2. Query term popularity

User search keywords cũng có hot terms, long-tail rare terms và misspellings. Query always-unique chỉ đo rare-term path, không đại diện toàn hệ.

### 40.3. Facet cardinality

Một aggregation theo country (20 groups) khác theo customerId (1 triệu groups). Sinh distinct values và group skew đúng.

### 40.4. Query result size

Từ khóa thường gặp có thể match 30% documents, từ khóa hiếm match 5; top-k, sort và aggregation cost khác nhau.

### 40.5. Ingest + search overlap

Index refresh/segment merges trong lúc bulk ingest làm search latency thay đổi. Đừng chỉ test query trên index hoàn toàn tĩnh nếu production có indexing liên tục.

## 41. YCSB và các benchmark frameworks: dùng làm công cụ, không làm định nghĩa production

YCSB (Yahoo! Cloud Serving Benchmark) cung cấp workload abstractions phổ biến để đánh giá key-value/database serving với operation mix và key selection distributions.

### 41.1. Giá trị

- Có phương pháp chung để lặp lại và so sánh.
- Có cấu hình operation proportions.
- Có các distributions cho key selection.
- Có các bindings cho một số stores.
- Có telemetry throughput/latency cơ bản.

### 41.2. Giới hạn

Các workload mẫu như read-heavy, update-heavy hoặc scan-heavy là **điểm khởi đầu**, không tự là profile của hệ thống thực.

Nếu production queries vào secondary index với nested documents, một benchmark chỉ GET/UPDATE primary key có thể kết luận sai.

### 41.3. Binding/driver semantics

Khi chọn benchmark binding, kiểm tra:

- Driver/SDK version.
- Read/write concern.
- Batch behavior.
- Retry and timeouts.
- Data serialization types.
- Connection pool.
- Record field count/length.

### 41.4. Workload mix và byte sizes

Ngay cả khi “95% read” giống sản phẩm, record size và key popularity vẫn có thể khác, nên cần custom workload/dataset hoặc ứng dụng-specific load tests.

### 41.5. Microbenchmark và end-to-end test

Một benchmark driver-to-DB giúp đánh giá storage path. End-to-end API load test còn đo Java JSON serialization, auth, caches, network và downstream calls. Cả hai hữu ích nhưng trả lời câu hỏi khác nhau.

## 42. Công cụ đo cần có ở mọi tầng

### 42.1. Client/generator

~~~text
target ops/sec
actual sent ops/sec
completed ops/sec
in-flight requests
generator CPU/GC/network
timeout/cancelled/dropped
latency distribution by operation class
~~~

### 42.2. Java service

~~~text
HTTP throughput and status
thread/connection pool utilization
queue wait time
GC pauses and heap allocation
cache hit/miss/negative hit
downstream retries
serialization CPU/bytes
~~~

### 42.3. Database

~~~text
CPU and memory
read/write IOPS and throughput
disk queue and utilization
per-node/per-shard load
cache/page hit rate
replication lag/quorum failures
compaction/flush/checkpoint
index usage
locks/conflicts/throttles
data size over time
~~~

### 42.4. Network

~~~text
latency between client/service/database
packets/bytes/sec
connection resets
TLS overhead
cross-AZ/Region traffic
~~~

### 42.5. Business correctness

~~~text
duplicate order count
incorrect inventory reservations
stale-read incidents
lost updates
idempotency conflicts
data checksum mismatches
~~~

Benchmark tăng throughput nhưng tạo wrong business outcome không được coi là thành công.

## 43. Latency histograms phải gắn với phân bố đầu vào

Nếu một p99 tổng gộp đủ loại operations, nó có thể giấu query chậm:

~~~text
GET by ID:           p99=15 ms
Recent order list:   p99=70 ms
Old order list:      p99=900 ms
Bulk update:         p99=1200 ms
~~~

### 43.1. Breakdown theo operation class

Báo p50/p95/p99 cho GET, range, filter, INSERT, UPDATE, DELETE riêng.

### 43.2. Breakdown theo item size

~~~text
GET <4 KB
GET 4–64 KB
GET >=64 KB
~~~

### 43.3. Breakdown theo tenant tier

Enterprise vs small tenants có thể có rất khác p99 do hot partitions và larger documents.

### 43.4. Breakdown theo key temperature

Hot-cache vs cold-disk reads. Một p99 chung có thể giảm sau tuning vì hot keys tăng, trong khi cold-read p99 không cải thiện.

### 43.5. Histograms không mất dữ liệu vì rounding

Nên dùng công cụ đo latency có dải precision thích hợp; tránh gom mọi requests từ 0–1000 ms vào một bucket quá rộng nếu SLO 80 ms.

### 43.6. Sample size

Để ước lượng p99.9 có ý nghĩa, cần đủ samples ở tail và thời gian đại diện. Không công bố một số p99.9 duy nhất sau 1.000 requests mà không ghi uncertainty.

## 44. Lập test plan theo trạng thái dữ liệu

Một plan có thể tách rõ:

| Phase | Trạng thái dataset | Workload | Mục tiêu |
|---|---|---|---|
| Preparation | Schema/indexes có sẵn | Seed generator | Tạo population |
| Settling | Dữ liệu vừa seed | Maintenance/idle hợp lý | Ổn định background |
| Warm-up | Cold hoặc partially warm cache | Representative mix | Khởi tạo cache/JIT |
| Baseline | Data và working set ổn định | Normal day | Đo steady state |
| Peak | Same distribution, higher rate | Peak 30–60 min | SLO tại giờ cao điểm |
| Burst | Current data + hot keys | Spike 2x ngắn | Queue/throttle/recovery |
| Aging | Data tăng/TTL phát huy | Long-running writes | Compaction/retention |
| Failure | Replica/node/consumer có lỗi | Same workload | Graceful degradation |
| Recovery | Phục hồi sau lỗi | Workload tiếp tục | Catch-up/backlog |

Thời lượng trong bảng là minh họa; chọn đủ lâu để chạm các chu kỳ nền cần đo.

### 44.1. Phase transitions cần được log

Ghi timestamps khi load generator tăng rate, khi backup bắt đầu, khi node down, khi compaction tăng và lúc traffic trở lại bình thường.

### 44.2. Không gộp các phases vào một p99 vô nghĩa

Nếu 10 phút warm-up chậm và 50 phút steady state nhanh, một p99 chung không nói rõ hệ khỏe khi vận hành bình thường hay chậm khi restart. Báo tách pha.

### 44.3. Data drift trong một run

INSERT/DELETE làm dataset đổi. Nếu benchmark kéo dài 24 giờ, key population và working set có thể thay đổi. Generator cần hỗ trợ chọn keys mới được tạo, xóa và tránh queries không hợp lệ không có chủ đích.

### 44.4. Recovery không có nghĩa throughput tức thời phục hồi

Sau failover, pending writes, repair/compaction, cache cold hoặc streaming backlog có thể gây p99 cao trong vài phút. Ghi recovery time và backlog drain rate.

## 45. A/B benchmark phải kiểm soát biến

Giả sử muốn so sánh:

~~~text
A: MongoDB indexes {tenantId, createdAt}
B: MongoDB indexes {tenantId, status, createdAt}
~~~

### 45.1. Giữ dataset tương đương

Hai runs phải dùng cùng seed/schema versions, population, key popularity, size distribution và workload phase, nếu mục đích chỉ so index.

### 45.2. Giữ infrastructure tương đương

Giống node size, disk class, network, replica/shard topology và client location; nếu không, hiệu năng khác có thể đến từ phần cứng.

### 45.3. Giữ consistency contract

Không so A read primary strong với B eventual GSI rồi tuyên bố B nhanh hơn nếu yêu cầu business cần strong read.

### 45.4. Randomize order/carryover

Nếu luôn chạy A trước, B sau, B có thể lợi vì OS cache/JIT warm hoặc hại vì disk fragmentation. Dùng run order đảo, reset state hoặc nhiều repeats tùy chi phí.

### 45.5. Nhiều lần đo

Một lần chạy có thể bị noise do GC, background compaction hay hàng xóm cloud. Ghi nhiều runs với variation/ranges, không chỉ chọn số nhanh nhất.

### 45.6. Không dùng benchmark để chứng minh nhân quả vượt dữ liệu

Nếu B cải thiện p99 ở dataset synthetic, kết luận hợp lệ là **B cải thiện trên cấu hình/workload đó**; production có thể khác, nên cần shadow/canary khi áp dụng thật.

## 46. Tải ngoài chuẩn: stress đúng một chiều mỗi lần

Để biết hệ nhạy với yếu tố nào, tạo các scenarios có kiểm soát:

### 46.1. Size stress

Tăng tỷ lệ records >64 KB từ 1% lên 5% mà giữ key popularity và operation mix.

### 46.2. Skew stress

Giữ total requests/sec, đổi uniform → Zipf s=0.8 → s=1.1 để xem hot partition/cache/lock contention.

### 46.3. Working-set stress

Giữ QPS và document size, mở working set từ 4 GB lên 40 GB để xem cache eviction và disk I/O.

### 46.4. Write mix stress

Giữ QPS, tăng writes 10% → 30% → 50% và quan sát write stalls, replication lag, compaction.

### 46.5. TTL/deletion stress

Giữ live document count gần nhau nhưng tăng overwrite/delete rate, xem tombstone backlog và reads.

### 46.6. Tenant hotspot stress

Giữ overall QPS, tăng share của top tenant từ 20% lên 60%, đo fairness và per-partition throttle.

### 46.7. Burst and failure stress

Giữ profile bình thường, tạo spike rồi fail một replica/nút trong môi trường được phép; xem throughput, p99 và recovery.

### 46.8. Đừng trộn mọi cực đoan rồi gọi là baseline

Nếu tăng size, skew, writes và retries cùng lúc, kết quả có ích để xem breaking point tổng hợp nhưng khó xác định yếu tố gây vấn đề. Nên có cả single-factor tests và combined worst-case.

## 47. Kiểm tra đúng đắn sau khi đo

Một database có thể trả rất nhanh vì writes bị reject, queries luôn empty hoặc generator không kiểm tra kết quả.

### 47.1. Count reconciliation

Với:

~~~text
Initial records: 1,000,000
Committed unique inserts: 100,000
Committed deletes: 20,000
No duplicate IDs or TTL expiry within scope
~~~

Expected final count:

\[
1{,}000{,}000+100{,}000-20{,}000=1{,}080{,}000.
\]

Điều kiện “unique committed” quan trọng: retries/idempotency và TTL có thể làm count thay đổi nếu không được kiểm soát.

### 47.2. Sampled value checks

Đọc lại một mẫu records sau writes, đối chiếu expected status, version, amount và array length. Nếu production consistency eventual, chờ watermark hoặc read source phù hợp trước khi kết luận mismatch.

### 47.3. Lost updates

Với concurrent updates, kiểm tra version/conditional results và business invariants. Nếu cả hai writers “success” nhưng một update mất, throughput cao không đáng tin.

### 47.4. Duplicate effects

Với retry tạo order, kiểm tra một operationId không sinh hai orders hoặc hai payment captures. Đếm cả attempts và logical results.

### 47.5. Time and TTL checks

Kiểm tra dữ liệu đã expire theo contract đọc, dữ liệu chưa đến hạn còn được trả, và không có stale replication gây kết luận sai trong use case cần strong read.

### 47.6. Query result cardinality

Nếu workload range GET kỳ vọng median 20 rows nhưng observed median 0, benchmark đang đo empty-query path. Đây là vấn đề dữ liệu test, không phải thành tích latency.

## 48. Một performance report tái hiện được cần gì?

Một mẫu report:

~~~yaml
experimentId: orders-peak-2026-11-14
dataset:
  generatorVersion: 3
  configHash: sha256-example
  seed: 20261114
  orderCount: 20000000
  logicalBytes: 60000000000
  schemaVersion: 2
  sizeBuckets: [small, medium, large]
  tenantSkewModel: tiered
  keyPopularity: zipf_s_0_9
workload:
  pointReadPercent: 45
  rangeReadPercent: 25
  insertPercent: 10
  updatePercent: 15
  deletePercent: 5
  offeredRateOpsPerSecond: 12000
  loadModel: open_loop
environment:
  cacheState: warm
  topology: example-replicated-cluster
  consistency: application-contract
results:
  actualSentOpsPerSecond: null
  completedOpsPerSecond: null
  p99ByOperation: {}
  errorRate: null
  physicalAttemptAmplification: null
~~~

Đây là một cấu trúc report minh họa, không phải kết quả đo thực hoặc cấu hình của sản phẩm cụ thể. Các trường null cần điền từ telemetry.

### 48.1. Environment metadata

Ghi engine/version, driver/version, node count, disk/network, replication/consistency, indexes, cache capacity và settings ảnh hưởng performance.

### 48.2. Time window metadata

Ghi phase intervals, thời gian warmup, giờ bắt đầu/kết thúc, dataset changes và background maintenance.

### 48.3. Throughput không được thiếu errors

Một phép đo 50.000 requests/sec với 20% timeouts không nên được so tốt hơn 40.000 requests/sec với 0,1% errors chỉ bằng throughput offered.

### 48.4. Chi phí và độ bền

Nếu một schema tăng throughput 20% nhưng disk usage/gateway costs gấp đôi hoặc giảm durability/consistency, báo các đánh đổi rõ ràng.

## 49. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng hơn |
|---|---|---|
| Mọi record có size 1 KB | Mất long tail | Sinh histogram size/nesting |
| Chỉ đo mean document size | Che oversized records | p50/p95/p99/max và access-weighted |
| Body toàn ký tự A | Compression giả tốt | Sinh entropy/schema phù hợp |
| Chọn keys uniform khi production skew | Không thấy hot partition | Zipf/hotset theo telemetry |
| Sinh tenants đều nhau | Che enterprise hotspot | Tiered tenant size/traffic |
| Sinh fields độc lập | Query selectivity sai | Conditional/correlated sampling |
| 90% GET không ghi query shape | Thiếu range/scan costs | Operation templates |
| Read/write mix chỉ đếm API methods | Thiếu downstream writes/reads | Logical + physical attempts |
| Không pre-seed data | Index/disk quá nhỏ | Base population đúng scale |
| Benchmark data volume chỉ 1% production | Cache dễ chứa tất cả | Scale theo mục tiêu |
| Không bật secondary indexes | Write costs quá thấp | Tạo indexes như production |
| Bỏ TTL/delete/backfill | Không có tombstone/compaction | Lifecycle realistic |
| Update random cold keys khi thực tế update hot | Không thấy contention | Hot update distribution |
| Chỉ test average RPS | Không thấy bursts | Time-varying rate |
| Generator closed-loop rồi báo target RPS | Coordinated omission | Scheduled arrivals và actual rate |
| Bỏ timeouts khỏi p99 | Che failures | Báo errors/timeouts riêng |
| Cache luôn warm 100% | Đọc quá nhanh | Cold/warm/mixed scenarios |
| Không reset dataset giữa A/B | Kết quả không so sánh được | Snapshot/config/seed |
| Coi GSI empty là fast GET | Query path không giống nguồn | Đúng consistency/query semantics |
| Query luôn trả 0 rows | p99 đẹp giả | Result cardinality distribution |
| Chỉ báo cluster average CPU | Che shard 100% | Per-node/per-partition metrics |
| Chạy 2 phút, kết luận LSM steady-state | Chưa có compaction backlog | Long-running aging test |
| Random test chứa PII thật | Rủi ro bảo mật | Synthetic/approved anonymization |
| Ghi mỗi seed, không ghi generator version | Không tái tạo được | Seed+config+code+snapshot |
| Đếm failed writes là successful throughput | Thành tích sai | Accepted/committed/error breakdown |
| Bỏ tính fairness | Tenant nhỏ bị ảnh hưởng | p99 theo tenant tier |
| Không kiểm tra record count cuối test | Có thể mất/nhân dữ liệu | Reconciliation |

## 50. Checklist thiết kế dataset đại diện

### 50.1. Dữ liệu

- Có histogram kích thước BSON/JSON/item, không chỉ một mean?
- Nested arrays, optional fields, string entropy và schema versions hợp lý?
- Tenant cardinality, tiers và record counts đúng phân bố?
- Có tương quan giữa tenant, age, status và record size?
- Có dữ liệu lịch sử, TTL, expired/deleted và late-arriving records?
- Có đầy đủ indexes/replicas/partition keys theo deployment?

### 50.2. Traffic

- Mỗi business user journey biến thành bao nhiêu DB requests?
- Point GET, range, filter, scan, update, insert, delete ratios thế nào?
- Read targets hot keys/cold keys theo phân bố nào?
- Thời gian/peak/bursts/batch jobs có được tái hiện?
- Có retry/speculative attempts và consistency levels đúng không?
- Query result size/page depth/positive vs missing tỷ lệ thế nào?

### 50.3. Thực nghiệm

- Có base population đủ quy mô và warmup phù hợp?
- Open-loop/closed-loop rõ ràng?
- Có actual sent vs target offered rate?
- Generator CPU/GC/network có đủ headroom?
- Có chạy đủ lâu để compaction/TTL/maintenance phản ánh steady state?
- A/B giữ dataset/schema/infrastructure đồng nhất?

### 50.4. Đo lường

- p50/p95/p99 theo operation, size, tenant, hot/cold?
- Throughput completed, errors, throttles, timeouts?
- CPU, I/O, memory, compaction, replication, per-partition metrics?
- Có count/checksum/business invariant checks sau test?
- Có lưu config/seed/generator version và data profile thực tế?

## 51. Bài tập 1 — vì sao cùng average size chưa đại diện?

Hai datasets có cùng số records:

~~~text
Dataset A:
  100% documents = 4 KB

Dataset B:
  90% documents = 1 KB
   9% documents = 8 KB
   1% documents = 220 KB
~~~

Yêu cầu:

1. Tính mean record size của B.
2. Vì sao B có mean gần A nhưng p99 response size có thể rất khác?
3. Nếu chỉ 1% records lớn nhưng 25% GETs vào nhóm đó, access-weighted mean thay đổi thế nào?
4. Nêu tác động tới serialization, compression, network và max item size.
5. Thiết kế histogram thay cho một fixed-size generator.

## 52. Bài tập 2 — ước lượng dung lượng logic

Một hệ gồm:

~~~text
Orders:        20,000,000 × 3 KB
Order events: 100,000,000 × 0.5 KB
Customers:     2,000,000 × 1.5 KB
~~~

1. Tính logical GB theo đơn vị thập phân.
2. Nếu replication factor=3, vì sao logical GB ×3 chỉ là ước lượng sơ bộ?
3. Những overhead nào còn thiếu?
4. Nếu mỗi order có 3 secondary indexes, cần đo thêm gì?
5. Cần bao nhiêu headroom cho compaction/index rebuild theo đặc điểm engine?

## 53. Bài tập 3 — ước lượng tăng trưởng và retention

Một hệ ghi 2.000 events/sec, kích thước trung bình 1 KB, retention 30 ngày.

1. Tính events/ngày.
2. Tính logical ingest GB/ngày.
3. Tính logical bytes của 30 ngày trong steady state lý tưởng.
4. Nếu 10% records expired nhưng tombstones chưa được dọn, disk usage khác logical count thế nào?
5. Nếu traffic ban đêm cao gấp đôi, phép tính daily-average có còn đúng không?
6. Vẽ một kịch bản dài ngày có TTL sweep và compaction.

## 54. Bài tập 4 — chọn key distribution

Hệ có 1 triệu keys. Telemetry cho biết top 5% keys nhận 70% GETs.

1. Uniform key selection phản ánh hệ này không?
2. Thiết kế một two-tier sampler theo tỷ lệ 70/30.
3. So sánh two-tier sampler với Zipf.
4. Nếu hot keys dịch chuyển hằng giờ, cần đổi generator thế nào?
5. Nếu hot keys cùng một partition, throughput bị ảnh hưởng ra sao?

## 55. Bài tập 5 — mô hình tenant skew

Một SaaS:

~~~text
10,000 tenants total.
100 enterprise tenants produce 60% requests.
900 growth tenants produce 25%.
9,000 small tenants produce 15%.
~~~

1. Tính average traffic share per tenant trong mỗi tier.
2. Nếu records/tenant cũng khác, cần hai distributions riêng nào?
3. Sinh tenantId theo request share mà không làm mọi enterprise tenant có traffic bằng nhau.
4. Nếu top enterprise tenant tăng gấp 10 lần trong 1 phút, metric nào chỉ ra hot partition?
5. Đề xuất fairness SLO cho small tenants.

## 56. Bài tập 6 — thiết kế tỷ lệ read/write có ngữ nghĩa

Một dashboard thấy:

~~~text
GET by ID 45%
GET list 25%
INSERT 10%
UPDATE 15%
DELETE 5%
~~~

1. Tính tổng read/write tỷ lệ theo operations.
2. Vì sao read ratio 70% chưa đủ?
3. Nếu GET list trả 50 rows và GET by ID trả 1, hãy so sánh response bytes khi row size như nhau.
4. Nếu UPDATE là conditional write vào hot keys, tác động tới contention là gì?
5. Đề xuất phân bố page size, key popularity, update-field shape và error paths.

## 57. Bài tập 7 — operation ratio khác byte ratio

Workload có 90% GET 1 KB và 10% INSERT 100 KB.

1. Trên 100 operations, tính logical read bytes.
2. Tính logical write bytes.
3. Mặc dù reads nhiều hơn, loại nào có logical payload lớn hơn?
4. Replication và index có thể làm write I/O tăng như thế nào?
5. Đề xuất đo IOPS và bytes/sec thực trên database thay vì chỉ tính payload.

## 58. Bài tập 8 — phân bố cardinality và selectivity

Một triệu Orders có:

~~~text
status:
  CONFIRMED  62%
  DELIVERED  20%
  PENDING    10%
  CANCELLED   5%
  REFUNDED    2%
  FAILED      1%
~~~

1. Một filter status=PENDING trả khoảng bao nhiêu records nếu không có điều kiện khác?
2. Nếu generator sinh status uniform, kết quả dự kiến lệch bao nhiêu?
3. Chọn hai query templates để phân biệt low/high selectivity.
4. Nếu status phụ thuộc tenant tier và record age, nên sinh như thế nào?
5. Những metrics nào cho biết query scan/return ratio?

## 59. Bài tập 9 — working set so với dataset

~~~text
Total records: 100 million.
Hot records trong một ngày: 2 million.
Mean logical size của hot record: 5 KB.
Redis cache estimated effective capacity: 6 GB.
~~~

1. Tính logical hot working-set bytes.
2. Vì sao không suy cache hit rate chỉ từ phép chia 6 GB/10 GB?
3. Zipf và record-size correlation ảnh hưởng cache efficiency thế nào?
4. Đề xuất một warm-cache và một cold-cache test.
5. Nêu cách đo working set theo 5 phút và 24 giờ.

## 60. Bài tập 10 — index build và steady state

Bạn muốn đo INSERT với 5 indexes trong MongoDB.

1. Nếu seed 20 triệu records khi tắt indexes rồi đo writes mà vẫn chưa tạo indexes, kết quả đại diện production không?
2. Phân biệt bulk-load performance và steady-state insert throughput.
3. Nếu index build chạy giữa test, nên báo như phase riêng hay gộp?
4. Query by tenant/status/createdAt phụ thuộc NDV và correlation thế nào?
5. Nếu 1% documents có array 500 items, multikey index khác ra sao?

## 61. Bài tập 11 — Cassandra partition width

Một bảng orders_by_customer có phân bố:

~~~text
80% customers: 1–5 orders.
19% customers: 6–100 orders.
 1% customers: 1,000–20,000 orders.
~~~

1. Vì sao test 10 orders/customer đều nhau dễ đánh giá sai?
2. Query LIMIT 50 khác full partition scan thế nào?
3. Những ảnh hưởng tới network, memory và compaction là gì?
4. Nếu data đã trải qua nhiều DELETE/TTL, generator cần dựng thêm gì?
5. Đề xuất metrics cho wide/hot partitions và read amplification.

## 62. Bài tập 12 — DynamoDB hot partition

Schema:

~~~text
PK = TENANT#T17
SK = ORDER#<timestamp>#<orderId>
~~~

Tenant T17 chiếm 65% writes và có hàng triệu orders.

1. Vì sao một PK có thể là nút thắt dù dịch vụ có khả năng scale?
2. Đề xuất bucketed PK theo customer hoặc hash.
3. Fan-out reads thay đổi ra sao sau bucketing?
4. Nếu items có sizes từ 1–200 KB, consumed capacity chỉ phụ thuộc ops/sec không?
5. Nêu các metrics throttle, latency và consumed capacity cần thu thập.

## 63. Bài tập 13 — Redis TTL và cache churn

Redis có:

~~~text
product details: 5 min TTL
session:        30 min TTL
negative keys:   5 sec TTL
rate limit:      1 min TTL
~~~

1. Nếu generator dùng TTL 5 phút cho mọi key, sai lệch gì?
2. Khi 100.000 negative entries expire cùng lúc, điều gì có thể xảy ra?
3. Jitter và single-flight giúp theo hai hướng nào?
4. Vì sao working set và Zipf quyết định cache hit rate?
5. Nếu Caffeine ở trước Redis, làm sao biết bao nhiêu API GET thực sự tới Redis?

## 64. Bài tập 14 — open-loop và coordinated omission

Một generator closed-loop có 100 users, mỗi user chỉ gửi request mới khi request cũ hoàn tất. Khi server bị treo 2 giây, throughput generator tự giảm mạnh.

1. Vì sao đây có thể che mức backlog của traffic thực?
2. Thiết kế open-loop target 5.000 ops/sec với bounded outstanding requests.
3. Phân biệt scheduledAt, actualSentAt và completedAt.
4. Nếu generator chỉ gửi 3.000 ops/sec vì CPU đầy, có được nói hệ chịu 5.000 ops/sec không?
5. Nếu 10% requests timeout, tại sao chỉ báo p99 successes là thiếu?

## 65. Bài tập 15 — Little's Law

Một hệ ổn định xử lý 8.000 requests/sec với mean total latency 25 ms.

1. Ước lượng mean concurrent requests theo Little's Law.
2. Nếu throughput 8.000 nhưng mean latency tăng thành 200 ms, concurrency ước lượng thay đổi thế nào?
3. Nếu offered rate 15.000 nhưng throughput chỉ 8.000 và queue tăng liên tục, có còn hệ ổn định không?
4. Vì sao tăng số client threads không tự tăng backend capacity?
5. Chọn maximum outstanding/rejection metrics cho generator.

## 66. Bài tập 16 — kiểm thử dài hạn LSM

Cassandra ghi 10.000 updates/sec trong 1 giờ đầu với p99 thấp. Sau 8 giờ, p99 tăng và disk usage cao.

1. Những background processes có thể gây ra hiện tượng này?
2. Cần đo compaction backlog, write stalls, tombstones và disk headroom thế nào?
3. Vì sao benchmark 10 phút sau clean bulk load không đủ?
4. Nếu TTL mỗi record 7 ngày, một test 4 giờ có tái hiện đầy đủ lifecycle không?
5. Thiết kế ageing dataset hoặc test dài hơn theo khả năng môi trường.

## 67. Bài tập 17 — synthetic data không giữ quan hệ

Generator tạo:

~~~text
Order.customerId chosen uniformly among all customers.
Order.total chosen randomly unrelated to line items.
Order.status chosen uniformly across all ages.
~~~

1. Nêu ba sai lệch với business data thường gặp.
2. Tại sao invalid totals có thể tạo benchmark đo rejection path?
3. Thiết kế sampling conditional on tenantTier, orderAge và customerActivity.
4. Tạo ràng buộc createdAt <= paidAt <= shippedAt khi các mốc tồn tại.
5. Đề xuất các phép đo histogram/aggregate để xác nhận generator tạo dữ liệu mong muốn.

## 68. Bài tập 18 — so sánh hai indexes

Bạn so MongoDB:

~~~text
Config A index: (tenantId, createdAt)
Config B index: (tenantId, status, createdAt)
~~~

1. Liệt kê những biến cần giữ giống nhau giữa A/B.
2. Nếu B chạy sau và dữ liệu đã warm, vì sao so sánh thiếu công bằng?
3. Những query templates nào có lợi cho B và khi nào?
4. Có cần đo write cost và index storage ngoài read p99 không?
5. Đề xuất nhiều runs và phân tích variance.
6. Khi nào nên shadow/canary trong production thay vì kết luận trực tiếp?

## 69. Bài tập 19 — thiết kế báo cáo đo tải

Một benchmark có:

~~~text
Offered:   20,000 ops/sec
Sent:      17,000 ops/sec
Completed: 15,000 ops/sec
Timeout:    2,000 ops/sec
Generator CPU: 98%
DB CPU:        42%
~~~

1. Có thể kết luận DB max capacity là 15.000 ops/sec không?
2. Dấu hiệu nào cho thấy generator bottleneck?
3. Thông số nào cần bổ sung: in-flight, queue, network, per-node CPU?
4. Báo p99 theo operation/error group như thế nào?
5. Những cảnh báo nào về actual vs target rate phải viết trong report?
6. Thiết kế lại load client hoặc phân tán generator ra sao?

## 70. Bài tập 20 — xây workload matrix hoàn chỉnh

Một nền tảng đặt hàng có:

~~~text
1 million customers
20 million orders
10 thousand tenants
Read-heavy normal day
Write-heavy import phase
Some power users have thousands of orders
Orders retain 12 months
~~~

Yêu cầu thiết kế:

1. Histogram order size và lineItemCount.
2. Tenant tier distribution (storage vs traffic).
3. Status distribution conditional on age.
4. Read key distribution Zipf hoặc moving hotset.
5. Point/range/filter query templates.
6. Write mix gồm insert, status update, delete.
7. TTL/retention/backfill scenarios.
8. Base dataset seed/rebuild plan.
9. Warm-up, normal, peak, burst, failure phases.
10. SLI p95/p99/error/compaction/cache hit/correctness.
11. Cấu hình benchmark để có thể tái tạo từ seed và generator version.

## 71. Tổng kết: dữ liệu đại diện mới tạo ra phép đo có ý nghĩa

Một benchmark không sai chỉ vì SQL/CQL/NoSQL operations được gửi thành công và biểu đồ p99 đẹp. Nó chỉ hữu ích khi mô tả đủ trung thực **những gì hệ thống sẽ thực sự phải xử lý**.

Các nguyên tắc cần nhớ:

1. **Bắt đầu từ user journeys và câu hỏi đo tải.** Một tỷ lệ đọc/ghi chung không mô tả query shape, kết quả trả về, điều kiện nhất quán hay backend operations.
2. **Sinh đúng phân bố kích thước.** Mean giống production nhưng thiếu p95/p99 và nested arrays lớn có thể làm sai network, I/O, compression và tail latency.
3. **Sinh đúng phân bố truy cập.** Uniform, Zipf, 80/20 hotset và moving hotset tạo các kiểu cache/partition contention khác nhau.
4. **Tenant skew và correlation phải được giữ.** Một số tenant lớn, nhiều requests mới, hot updates và oversized records có thể cùng xuất hiện.
5. **Read/write ratio phải có nghĩa.** Phân biệt point GET, range, filter, INSERT, partial UPDATE, DELETE, retries và business transactions.
6. **Tính cả bytes, không chỉ operations.** 90% GET nhỏ có thể tiêu thụ logical payload ít hơn 10% writes lớn.
7. **Data model đúng như production.** Document nesting, indexes, partition keys, sort keys, UDT, GSI, Redis TTL và query shapes quyết định chi phí.
8. **Tạo dataset đủ quy mô và tuổi đời.** Warm-cache một triệu records không tương đương hệ trăm triệu records có tombstones, compaction, index churn và retention.
9. **Quan sát working set và cache state.** Cold, warm, mixed cùng key popularity thực tế giúp hiểu p99 và throughput ở từng điều kiện.
10. **Open-loop/closed-loop phải được ghi rõ.** Không để client chờ server làm giảm offered load rồi báo hệ chịu được peak; đề phòng coordinated omission.
11. **Đo actual offered/sent/completed rates và failures.** Một target 20.000 ops/sec không có nghĩa generator đã thực sự gửi hoặc database đã commit từng ấy operations.
12. **Đo nhiều chiều.** p99 theo operation, size, tenant, hot/cold; CPU, disk, compaction, replication, throttling và network theo node/partition.
13. **Đối soát tính đúng đắn.** Record count, business invariants, duplicate writes, lost updates và query result cardinality là một phần của báo cáo hiệu năng.
14. **Thực nghiệm phải tái tạo được.** Lưu seed, generator version, config hash, dataset snapshots, engine/driver versions, indexes và phase timings.
15. **So sánh có kiểm soát.** Chỉ thay một biến khi muốn hiểu tác động của biến đó; chạy stress tổng hợp riêng để tìm breaking point.
16. **Không dùng dữ liệu nhạy cảm bừa bãi.** Dữ liệu tổng hợp giữ histogram/correlation là lựa chọn tốt hơn raw production dump trong nhiều hoàn cảnh.

Để tự kiểm tra trước khi chạy benchmark, hãy hỏi:

> **“Nếu dữ liệu thật có kích thước đuôi dài, vài tenants rất nóng, reads chủ yếu vào records mới và writes làm thay đổi cùng partitions suốt nhiều giờ, bộ dữ liệu và chuỗi thao tác này có tạo ra đúng những áp lực đó không — hay đang đo hiệu năng của một thế giới giả quá dễ?”**








