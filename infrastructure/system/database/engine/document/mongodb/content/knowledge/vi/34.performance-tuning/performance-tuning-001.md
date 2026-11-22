# Xây dựng tải thử đại diện và tiêu chí đo p50, p95, p99 trong MongoDB

## 1. Vì sao một truy vấn chạy nhanh chưa chứng minh database đủ nhanh?

Một ứng dụng cho thuê nhà dùng MongoDB để quản lý tin đăng, người dùng, lịch hẹn và hoạt động giao dịch. Developer mở mongosh rồi chạy:

~~~javascript
db.listings.find({ status: "active" }).limit(20);
~~~

Truy vấn trả kết quả sau vài mili giây. Nhóm kết luận MongoDB đã tối ưu. Nhưng vào giờ cao điểm, người dùng thấy trang tìm kiếm mất vài giây, một số request timeout và CPU database tăng cao.

Sự khác biệt đến từ **tải thử không đại diện**:

- Production có **hàng triệu documents**, không phải vài trăm bản ghi mẫu.
- Có nhiều kiểu truy vấn: tìm tin theo thành phố/giá, xem chi tiết, thống kê, cập nhật trạng thái.
- Nhiều người dùng thực hiện request **đồng thời**.
- Một số tenant/thành phố được truy cập nhiều hơn hẳn các nhóm còn lại.
- Cache nóng/lạnh thay đổi tỷ lệ cache hit và disk I/O.
- Index tạo lợi thế cho read nhưng làm tăng chi phí ghi.
- Network, TLS, connection pool, replication và write concern đều có thể làm tăng latency.
- Những request chậm ở phần đuôi phân phối có thể không ảnh hưởng nhiều đến trung bình nhưng ảnh hưởng nghiêm trọng đến trải nghiệm người dùng.

Do đó, câu hỏi đúng không phải:

> “MongoDB chạy một truy vấn này mất bao nhiêu mili giây?”

Mà là:

> “Ở dữ liệu, tỷ lệ read/write, phân bố truy vấn, concurrency và tốc độ request giống production, MongoDB có đáp ứng **SLO về latency, throughput và lỗi**, kể cả p95/p99, trong khoảng thời gian cần thiết không?”

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **workload profile** từ traffic và truy vấn thực tế.
2. Thiết kế dataset kiểm thử gần đúng về **dung lượng, cardinality, phân bố, độ chọn lọc và kích thước document**.
3. Phân biệt **offered load, achieved throughput, concurrency, utilization, service time, queueing time và response time**.
4. Phân biệt **closed-loop** và **open-loop load generation**; hiểu hiện tượng **coordinated omission**.
5. Tính và diễn giải **p50, p95, p99** bằng phương pháp percentile đã công bố.
6. Định nghĩa **SLI/SLO** theo từng loại truy vấn và toàn bộ hệ thống.
7. Chạy một lab MongoDB với dữ liệu cố định, query shapes và index có chủ đích.
8. Đọc **explain("executionStats")**, các chỉ số driver, server và hạ tầng để phân tích bottleneck.
9. Dựng benchmark Node.js ở mức cơ bản, phân tách warmup/measurement và ghi nhận lỗi, timeout.
10. Đưa ra quyết định tối ưu **dựa trên phân phối latency và tính đại diện**, không chỉ dựa trên một thời gian chạy tốt nhất.

> **Phạm vi:** Bài thuộc **Database Engine Document MongoDB → Tối ưu hiệu năng**. Toàn bộ lệnh seed chỉ dùng database **mongo_perf_lab_362** với IDs riêng có prefix **b362-**. Benchmark mặc định là **read-only** và giới hạn concurrency; chế độ ghi chỉ dùng trên bộ counters của lab khi bật chủ động. **Không tạo tải thử trực tiếp lên production** nếu chưa có kế hoạch, giới hạn, phê duyệt và rollback.

## 2. Những đại lượng cần đo

### 2.1. Response time và latency

Từ góc nhìn người dùng, thời gian phản hồi của API có thể gồm:

~~~text
Request tới API
    |
    +--> Xếp hàng ở load balancer/server
    +--> Xác thực và xử lý logic
    +--> Chờ connection từ driver pool
    +--> DNS/TLS/network tới MongoDB
    +--> Chờ/queue ở database
    +--> Thực thi query/index scan
    +--> Network trả documents
    +--> Serialize response
    |
    v
Response tới client
~~~

Trong khi đó, **executionTimeMillis** của explain chỉ phản ánh một phần thời gian thực thi phía database theo cơ chế explain. Nó **không tương đương** thời gian API mà client thấy.

Khi báo cáo latency, luôn ghi rõ **đo ở đâu**:

- **End-to-end API latency:** từ client gửi request tới lúc nhận toàn bộ response.
- **Driver operation latency:** từ ứng dụng bắt đầu gọi driver tới khi Promise hoàn tất, thường gồm pool wait/network/server/deserialization.
- **MongoDB command duration:** đo bằng driver command monitoring, phạm vi đo tùy event/driver.
- **Server query execution:** các thông số của explain/profiler, không gồm toàn bộ thời gian ngoài server.

Không so p99 của API với p99 của explain rồi gọi chúng là cùng một SLI.

### 2.2. Throughput

**Throughput** là số thao tác hoàn thành mỗi đơn vị thời gian:

\[
\text{Throughput} = \frac{\text{Số thao tác thành công hoàn tất}}{\text{Thời gian quan sát}}
\]

Ví dụ: 12.000 thao tác hoàn tất thành công trong 60 giây tương ứng **200 successful operations/second**.

Nếu 13.000 request được gửi, 12.000 thành công và 1.000 lỗi, báo cáo cần cả:

- **Offered load:** số request hệ thống nhận/được đề nghị.
- **Successful throughput:** số request thành công.
- **Error/timeout rate:** tỷ lệ không thành công.

Không tuyên bố hệ thống đạt 216 RPS tốt chỉ vì đã **gửi** 13.000 request trong 60 giây.

### 2.3. Offered load và achieved load

~~~text
Load generator định gửi 500 request/s
       |
       v
Server chỉ hoàn tất 300 request/s
       |
       +--> Hàng đợi tăng
       +--> Timeout bắt đầu xuất hiện
       +--> p95/p99 tăng
~~~

Trong trường hợp này:

- **Offered rate:** 500 RPS.
- **Achieved success rate:** khoảng 300 RPS.
- **Chênh lệch:** có thể là queue backlog, errors, throttling hoặc giới hạn generator.

Đo cả hai mới phân biệt được **database không đáp ứng tải** và **load generator không tạo đủ tải**.

### 2.4. Concurrency

Concurrency là số tác vụ đang hoạt động/đang chờ hoàn tất cùng lúc. Nó **không đồng nghĩa** với throughput.

Ví dụ một closed-loop client có 10 workers, mỗi worker gửi request mới ngay khi request trước hoàn tất:

- Latency trung bình 50 ms: lý tưởng khoảng 200 requests/s (bỏ qua overhead).
- Latency trung bình 200 ms: chỉ còn khoảng 50 requests/s nếu vẫn 10 workers.

Khi server chậm đi, **closed-loop tự giảm offered throughput**, có thể che giấu khủng hoảng ở giờ cao điểm.

### 2.5. Little's Law

Trong điều kiện hệ thống ổn định phù hợp, quan hệ xấp xỉ:

\[
L = \lambda W
\]

Trong đó:

- **L:** số request trung bình đang có trong hệ thống.
- **λ:** throughput/arrival rate trung bình.
- **W:** thời gian request trung bình trong hệ thống.

Ví dụ **200 req/s × 0,1 s = 20 requests** đang tồn tại trung bình. Đây là công cụ suy luận capacity và queueing, không phải giấy phép suy ra p99 từ latency trung bình.

### 2.6. Utilization và saturation

CPU 60% không nhất thiết nghĩa là MongoDB còn dư 40% năng lực hữu ích. Bottleneck có thể nằm ở:

- Một CPU core hoặc một stage tuần tự.
- Disk latency / IOPS / throughput.
- WiredTiger cache pressure.
- Network bandwidth.
- Connection pool wait.
- Locks/tickets/admission control.
- Replica set majority/journal wait.
- Hot shard hoặc tenant hot spot.

**Saturation** là trạng thái tải tăng thêm gây queueing/latency hoặc error rate tăng nhanh, dù offered traffic tăng mà successful throughput không tăng tương ứng.

## 3. p50, p95, p99 là gì?

### 3.1. Khái niệm percentile

Với N quan sát latency:

- **p50:** khoảng 50% thao tác có latency không vượt ngưỡng này theo phương pháp percentile.
- **p95:** khoảng 95% thao tác có latency không vượt ngưỡng; phần đuôi còn lại khoảng 5%.
- **p99:** khoảng 99% thao tác không vượt ngưỡng; phần đuôi còn lại khoảng 1%.

**p99 không phải latency lớn nhất.** Còn có những request nằm trên p99, đôi khi rất chậm. Percentile là một ngưỡng thuộc phân phối quan sát được, không phải lời hứa cho từng request.

### 3.2. Ví dụ trực giác

Giả sử 100 thao tác, được sắp tăng dần theo latency. Khi dùng **nearest-rank**:

- p50 là quan sát thứ **50**.
- p95 là quan sát thứ **95**.
- p99 là quan sát thứ **99**.

Nếu 95 thao tác hoàn thành không quá 80 ms, bốn thao tác tiếp theo mất 300–500 ms và thao tác cuối mất 2.000 ms, **p95 có thể vẫn là 80 ms**, nhưng p99 sẽ phản ánh phần đuôi chậm hơn.

### 3.3. Vì sao average có thể đánh lừa?

Giả sử:

~~~text
99 requests: 20 ms
 1 request:  2.000 ms
~~~

Mean:

\[
\frac{99\times20+2000}{100}=39{,}8\text{ ms}
\]

Mean khoảng **39,8 ms** nghe có vẻ tốt, nhưng một người dùng đã chờ **2 giây**. Với ứng dụng có nhiều request mỗi phiên, những đuôi chậm có thể xuất hiện thường xuyên ở trải nghiệm tổng thể.

Vì vậy, theo dõi ít nhất **p50, p95, p99, throughput và error rate**; trong tình huống đặc biệt cũng cần max/p99.9 hoặc tail timeouts.

### 3.4. Percentile có nhiều định nghĩa thống kê

Không có một công thức nội suy percentile duy nhất được mọi thư viện sử dụng. Hai hệ đo khác nhau có thể trả giá trị hơi khác với cùng danh sách, đặc biệt khi ít mẫu.

Trong lab này sử dụng **nearest-rank**:

1. Sắp xếp N latency tăng dần.
2. Chọn hạng **ceil(p × N)** với p từ 0 đến 1.
3. Lấy phần tử ở vị trí đó, tính từ 1.

\[
P_p=x_{(\lceil pN\rceil)}
\]

Với N=20: p50 là quan sát thứ 10, p95 là thứ 19 và p99 là thứ 20. Như vậy **p99 chính là max khi chỉ có 20 mẫu**. Điều này cho thấy p99 ở tập quá nhỏ rất thiếu ổn định.

### 3.5. Hàm percentile trong JavaScript

~~~javascript
function percentileNearestRank(values, p) {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }
  if (p < 0 || p > 1) {
    throw new Error("p phải nằm trong [0, 1]");
  }
  if (!values.every(v => Number.isFinite(v) && v >= 0)) {
    throw new Error("Latency phải là số hữu hạn không âm");
  }

  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil(p * sorted.length));
  return sorted[rank - 1];
}

const latenciesMs = [
  18, 23, 21, 20, 19, 24, 22, 26, 27, 25,
  29, 31, 28, 30, 32, 35, 34, 40, 120, 600
];

printjson({
  p50: percentileNearestRank(latenciesMs, 0.50),
  p95: percentileNearestRank(latenciesMs, 0.95),
  p99: percentileNearestRank(latenciesMs, 0.99)
});
~~~

Kết quả theo nearest-rank:

~~~text
p50 = 27 ms
p95 = 120 ms
p99 = 600 ms
~~~

Ở đây chỉ có **20 mẫu**. Không dùng p99 từ 20 requests để hứa SLO production.

### 3.6. Tại sao cần nhiều mẫu?

Với nearest-rank:

| Số mẫu | p99 lấy hạng | Nhận xét |
| ---: | ---: | --- |
| 20 | 20 | Bằng max, quá nhiễu |
| 50 | 50 | Vẫn bằng max |
| 100 | 99 | Chỉ một vài quan sát phần đuôi |
| 1.000 | 990 | Có khoảng 10 mẫu trên p99 |
| 10.000 | 9.900 | 100 mẫu trên p99 |
| 100.000 | 99.000 | 1.000 mẫu trên p99 |

Những con số chỉ diễn giải vị trí percentile, **không bảo đảm confidence interval**. Latency thường có tính tương quan theo thời gian, request bursts, GC và incidents; 10.000 mẫu liên tiếp chưa chắc tương đương 10.000 quan sát độc lập.

### 3.7. Đừng lấy trung bình của các p99

Giả sử hai phút:

~~~text
Phút A: 10.000 requests, p99 = 100 ms
Phút B:    100 requests, p99 = 1.000 ms
~~~

Không tính p99 của cả 10.100 requests bằng:

~~~text
(100 + 1000) / 2 = 550 ms   // SAI
~~~

Cũng không thể lấy weighted average của hai p99 để thu được p99 tổng chính xác. Cần **gộp raw observations hoặc các histogram/summary mergeable có độ chính xác phù hợp**, rồi tính percentile của phân phối gộp.

### 3.8. Percentile theo từng loại operation

Một read theo _id có thể mất 2–10 ms, còn báo cáo aggregation 300–600 ms. Nếu gộp:

~~~text
95% requests là point lookup nhanh
 5% requests là aggregation chậm
~~~

p95 tổng thể có thể **che khuất hoàn toàn** latency của aggregation. Vì vậy:

- Đo p50/p95/p99 **theo operation/endpoint/query shape**.
- Thêm p50/p95/p99 tổng thể để theo dõi trải nghiệm tổng.
- Luôn báo số mẫu và tỷ trọng traffic của từng nhóm.

## 4. Định nghĩa SLI, SLO và tiêu chí PASS/FAIL

### 4.1. SLI

**Service Level Indicator** là chỉ số đo được, ví dụ:

- p95 latency của API tìm kiếm.
- p99 latency của point lookup.
- Successful throughput.
- Error rate (including timeouts).
- Tỷ lệ yêu cầu hoàn tất trong ngân sách thời gian.

### 4.2. SLO

**Service Level Objective** là mục tiêu đã chọn cho SLI trong khoảng thời gian rõ ràng.

Ví dụ giả định cho lab/hệ thống minh họa:

| Workload | Tốc độ đưa tải | p50 | p95 | p99 | Error rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Search feed** | 140 req/s | ≤ 40 ms | ≤ 150 ms | ≤ 300 ms | ≤ 0,2% |
| **Point lookup** | 40 req/s | ≤ 15 ms | ≤ 60 ms | ≤ 120 ms | ≤ 0,2% |
| **Aggregation summary** | 20 req/s | ≤ 100 ms | ≤ 400 ms | ≤ 800 ms | ≤ 0,5% |
| **Bounded update** | 10 req/s | ≤ 40 ms | ≤ 180 ms | ≤ 400 ms | ≤ 0,2% |

Các con số trong bảng là **mục tiêu tự đặt để minh họa**, không phải chuẩn MongoDB hoặc yêu cầu bắt buộc cho mọi sản phẩm. Chúng phải được hiệu chỉnh từ business SLO, network location, data size, hardware và chi phí.

### 4.3. Ghi điều kiện đo kèm tiêu chí

Một phát biểu có thể kiểm chứng:

> Trong 30 phút steady-state trên môi trường staging có dataset và index tương đương production, khi load generator đưa 200 req/s theo đúng tỷ lệ workload, Search Feed phải đạt p95 ≤ 150 ms, p99 ≤ 300 ms, error rate ≤ 0,2% và achieved successful throughput tối thiểu 139 req/s cho riêng workload này.

Phải ghi thêm:

- Vị trí client và database.
- Số instance/size cluster.
- Driver version, pool settings.
- Warmup time.
- Write concern/read preference/read concern.
- Cache/dataset state.
- Chính sách retries, timeouts.
- Định nghĩa “success” và sampling.

### 4.4. Không đánh giá một SLO riêng lẻ

Hệ thống có thể đạt p95 vì đã **từ chối 30% requests** hoặc generator tạo được nửa tải dự định. Do đó, tiêu chí PASS phải gồm:

1. **Offered load đạt yêu cầu** và đúng request mix.
2. **Successful throughput** đáp ứng tối thiểu.
3. **Latency percentile** theo mỗi loại operation đạt ngưỡng.
4. **Error/timeout rate** không vượt ngưỡng.
5. Không có queue backlog tăng không kiểm soát.
6. Không bị bất thường nghiêm trọng về replication, storage hoặc resource.
7. Kết quả đủ mẫu và lặp lại được.

### 4.5. Percentile và tỷ lệ trong ngưỡng

Hai cách mô tả:

~~~text
p95 response time <= 150 ms
95% requests hoàn tất <= 150 ms
~~~

có quan hệ gần nhau về ý tưởng, nhưng phải thống nhất cách xử lý **failed requests, timeouts, late completions, sampling và phương pháp percentile**. SLO “95% requests dưới 150 ms” thường thuận tiện cho tính toán **good events/total events**, còn p95 là một thống kê tóm tắt. Trong vận hành, cả hai nên có định nghĩa rõ.

## 5. Xây dựng workload đại diện từ production

### 5.1. Workload không chỉ là tỷ lệ read/write

Hai hệ thống đều “80% read, 20% write” nhưng có thể khác nhau hoàn toàn:

~~~text
System A:
  80% read theo _id đã index
  20% insert nhỏ

System B:
  80% aggregation nhiều stage và sort lớn
  20% update một document chứa array rất dài
~~~

Chi phí CPU, I/O, locks, cache và index maintenance rất khác nhau.

Vì vậy, profile phải có **query shapes**, độ chọn lọc, kích thước payload và tần suất thực tế.

### 5.2. Thu thập query shape

Từ logs, APM/profiler có quyền, application metrics hoặc workload discovery:

- Tên endpoint/operation.
- MongoDB command và query shape.
- Filter fields và operators.
- Sort, projection, limit, skip.
- Index được dùng và plan.
- Tần suất và thời gian trong ngày.
- Kích thước response.
- Tỷ lệ lỗi, timeout, retry.
- Tenant/city/product phân bố ra sao.

Không đưa nguyên raw query chứa PII hay passwords vào tập benchmark nếu không có chính sách xử lý dữ liệu.

### 5.3. Ma trận workload ví dụ

Một hỗn hợp giả định:

| Operation | Tỷ lệ | MongoDB pattern | Dữ liệu/chi phí quan trọng |
| --- | ---: | --- | --- |
| **SearchFeed** | 70% | find tenant/city/status/price + sort + limit | Range/selectivity, sort/index |
| **GetListing** | 15% | findOne theo _id | Point lookup, cache |
| **CitySummary** | 10% | aggregate match/group | Docs scanned, CPU |
| **UpdateCounter** | 5% | updateOne counter có ID cố định | Write lock/journal/contention |

Tỷ lệ tổng = **100%**. Đo riêng mỗi operation và đo đồng thời đúng tỷ trọng để thấy read/write ảnh hưởng lẫn nhau.

**Cảnh báo:** workload 70/15/10/5 chỉ là ví dụ. Với một hệ thống ghi nhiều sự kiện thời gian thực, tỷ lệ write có thể cao hơn rất nhiều.

### 5.4. Phân bố tenant không đồng đều

Production thường có skew:

~~~text
Tenant lớn t001: 60% traffic
Các tenant nhỏ: 40% traffic
~~~

Dataset và query generator cần phản ánh điều này. Nếu benchmark phân phối query đồng đều trên 100 tenants, nó có thể bỏ sót:

- Hot partitions/chunks.
- Các index ranges truy cập liên tục.
- Cache locality.
- Lock/contention trên một số documents.

### 5.5. Hot và cold data

Thông thường, các tin mới đăng hoặc tin phổ biến được đọc nhiều hơn tin cũ. Query mix nên có:

- **Hot reads**: nhiều lần trên tập nhỏ.
- **Warm reads**: tập trung vừa phải.
- **Cold reads**: quét/đọc dữ liệu ít có trong cache.

Chỉ query cùng một document theo _id một triệu lần có thể tạo benchmark “quá đẹp” do mọi thứ nằm sẵn trong cache.

### 5.6. Kích thước document và Array

Ảnh hưởng hiệu năng có thể tới từ:

- Một document nhỏ 1 KiB vs 100 KiB.
- Arrays vài phần tử vs hàng nghìn phần tử.
- Embedded documents sâu.
- Số fields được projection.
- Cardinality của index.
- Multikey index entries.
- Tỷ lệ update tăng kích thước document.

Một dataset gồm toàn documents nhỏ đồng nhất không đại diện cho ứng dụng có nhiều arrays/metadata lớn.

### 5.7. Thời gian và mùa vụ

Hệ thống có thể có:

- Buổi sáng nhiều search reads.
- Giờ trưa burst 3×.
- Cuối ngày job tổng hợp.
- Cuối tháng đối soát thanh toán.
- Đợt import dữ liệu lớn.

Vì thế có thể cần nhiều kịch bản **steady, peak, batch overlap, recovery catch-up** thay vì chỉ một bài test cố định.

## 6. Dữ liệu thử phải có đặc tính giống production

### 6.1. Kích thước không phải yếu tố duy nhất

Muốn mô phỏng collection 100 triệu documents, không nhất thiết lab nhỏ có thể tạo đúng 100 triệu. Nhưng cần biết nếu chỉ có 5.000 documents và toàn bộ vừa WiredTiger cache, kết luận về I/O không thể khái quát sang production.

Khi thu nhỏ dataset, ghi rõ khác biệt:

- Tổng documents/bytes.
- Số tenants và tỷ lệ tenant hot.
- Cardinality city/status/category.
- Phân bố price, createdAt.
- Tỷ lệ documents lớn và số array entries.
- Working set so với RAM/WiredTiger cache.
- Độ chọn lọc của mỗi filter.

### 6.2. Dữ liệu tổng hợp có chủ đích

Không nhất thiết cần sao chép PII thật. Có thể tạo synthetic data nhưng giữ những thống kê quan trọng: phân bố giá, số bản ghi theo thành phố, độ dài metadata, số tin theo tenant, độ tập trung thời gian.

Đừng chỉ dùng các giá trị random đều:

~~~text
tenantId random đều 1..1000
city random đều 1..100
price random đều 1..100
~~~

nếu production có 65% tin ở một thành phố, rất nhiều tin giá vừa phải và chỉ vài tenants lớn.

### 6.3. Lưu data provenance

Một benchmark cần ghi dataset version:

~~~text
datasetName: listings-synthetic-v1
documents: 12000
tenantDistribution: skewed
cityDistribution: synthetic
embedding: none
payloadSize: bounded
seed: deterministic
indexes: captured separately
~~~

Khi kết quả cải thiện sau tối ưu, phải biết liệu dữ liệu/index có thay đổi ngoài dự tính hay không.

## 7. Lab mongosh: tạo dataset tải thử có thể tái lập

### 7.1. Phạm vi lab

Database:

~~~text
mongo_perf_lab_362
  lab_listings
  lab_counters
~~~

Kế hoạch:

- Seed **12.000 listings** với ID cố định.
- Dùng phân bố tenant có một nhóm hot.
- Có city, status, category, price, createdAt và mảng amenities.
- Tạo những indexes được chọn rõ ràng.
- Seed **16 counters** dành riêng cho thử ghi, không đụng nghiệp vụ thật.
- Không drop database/collection.
- Không tạo tải lớn trong quá trình seed ngoài batch có giới hạn.

### 7.2. Script seed idempotent

Chạy trong mongosh trên **local/staging cô lập** với quyền ghi/createIndex:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_perf_lab_362");
  const listings = lab.getCollection("lab_listings");
  const counters = lab.getCollection("lab_counters");
  const tag = "mongo-perf-362-v1";
  const total = 12000;
  const batchSize = 400;
  let ops = [];

  function writeBatch() {
    if (ops.length === 0) return;
    listings.bulkWrite(ops, { ordered: false });
    ops = [];
  }

  for (let i = 0; i < total; i++) {
    const tenantId = i % 10 < 6
      ? "t001"
      : "t" + String((i % 24) + 2).padStart(3, "0");
    const city = ["HCM", "HN", "DN"][i % 3];
    const category = ["studio", "apartment", "house"][i % 3];
    const id = "b362-listing-" + String(i).padStart(6, "0");

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      city,
      category,
      status: i % 10 === 0 ? "inactive" : "active",
      rentMillion: 6 + (i % 35),
      createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
      title: "Synthetic listing " + i,
      amenities: i % 4 === 0
        ? ["desk", "wifi", "parking", "balcony"]
        : ["wifi"],
      description: "Lab-only document for query-shape testing."
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });

    if (ops.length >= batchSize) {
      writeBatch();
    }
  }
  writeBatch();

  for (let id = 0; id < 16; id++) {
    counters.updateOne(
      {
        _id: "b362-counter-" + id,
        labTag: tag
      },
      {
        $setOnInsert: {
          labTag: tag,
          increments: 0,
          updatedAt: new Date(0)
        }
      },
      { upsert: true }
    );
  }

  listings.createIndex(
    {
      tenantId: 1,
      city: 1,
      status: 1,
      createdAt: -1,
      _id: -1
    },
    { name: "ix_b362_tenant_city_status_recent" }
  );

  listings.createIndex(
    {
      tenantId: 1,
      status: 1,
      city: 1
    },
    { name: "ix_b362_tenant_status_city" }
  );

  printjson({
    labListings: listings.countDocuments({ labTag: tag }),
    labCounters: counters.countDocuments({ labTag: tag }),
    indexNames: listings.getIndexes().map(x => x.name)
  });
})();
~~~

Kết quả dự kiến:

~~~text
labListings = 12000
labCounters = 16
~~~

**Chỉ chạy trên database lab được phép ghi.** Script cố ý không xóa collection; lần chạy sau sẽ thay những listings của lab có cùng _id và giữ counters đã tạo. Nếu _id trùng document ngoài bài, điều kiện có **labTag** sẽ tránh overwrite nhưng upsert có thể báo duplicate key; hãy dừng điều tra, không xóa dữ liệu không thuộc bài.

### 7.3. Đọc mô tả dataset

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");

printjson(
  listings.aggregate([
    { $match: { labTag: "mongo-perf-362-v1" } },
    {
      $group: {
        _id: {
          tenantId: "$tenantId",
          city: "$city",
          status: "$status"
        },
        n: { $sum: 1 }
      }
    },
    { $sort: { n: -1 } },
    { $limit: 20 }
  ]).toArray()
);
~~~

Mục đích là kiểm tra phân bố, không phải đo latency performance bằng một lần aggregation.

### 7.4. Query A — search feed

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");

const feedQuery = {
  labTag: "mongo-perf-362-v1",
  tenantId: "t001",
  city: "HCM",
  status: "active",
  rentMillion: { $lte: 20 }
};

printjson(
  listings.find(
    feedQuery,
    {
      _id: 1,
      title: 1,
      rentMillion: 1,
      createdAt: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray()
);
~~~

Query A kết hợp **tenant + city + status + price range + sort + limit**. Đây là ví dụ có thể gặp trong ứng dụng tìm tin.

Với index **ix_b362_tenant_city_status_recent**, các trường equality và sort có thể có lợi; **rentMillion** chưa nằm trong index này nên MongoDB có thể vẫn cần lọc thêm. Không kết luận kế hoạch tối ưu nếu chưa xem explain.

### 7.5. Query B — point lookup

~~~javascript
printjson(
  listings.findOne(
    { _id: "b362-listing-004200" },
    {
      projection: {
        _id: 1,
        tenantId: 1,
        title: 1,
        city: 1
      }
    }
  )
);
~~~

Lookup theo **_id** thường có đường truy cập rất khác với range+sort trên nhiều documents. Không dùng p99 của Query B để suy ra p99 của Query A.

### 7.6. Query C — aggregation summary

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        labTag: "mongo-perf-362-v1",
        tenantId: "t001",
        status: "active"
      }
    },
    {
      $group: {
        _id: "$city",
        count: { $sum: 1 },
        avgRentMillion: { $avg: "$rentMillion" }
      }
    },
    { $sort: { count: -1 } }
  ]).toArray()
);
~~~

Aggregation này xét nhiều documents hơn point lookup và có thể dùng CPU/đọc index nhiều hơn. Đưa nó vào workload mix để thấy ảnh hưởng thực khi chạy đồng thời với search.

### 7.7. Query D — counter update (chỉ lab)

~~~javascript
const counters = lab.getCollection("lab_counters");

printjson(
  counters.updateOne(
    {
      _id: "b362-counter-0",
      labTag: "mongo-perf-362-v1"
    },
    {
      $inc: { increments: 1 },
      $set: { updatedAt: new Date() }
    }
  )
);
~~~

Đây là một write **có side effect**, chỉ chạy khi muốn thử. Counter được giới hạn vào collection riêng của lab. Vì document là một hot key, hành vi contention có thể khác workload ghi của ứng dụng thật; nếu production ghi phân tán, thay Query D bằng một mẫu đại diện hơn.

### 7.8. Dataset lab khác production ở đâu?

12.000 documents nhỏ chưa đại diện cho:

- Vài triệu documents chiếm hàng trăm GiB.
- Dataset không vừa WiredTiger cache.
- Replication cross-region.
- Chuỗi giao dịch nhiều collections.
- Search indexes/vector/geospatial workloads.
- Sharded cluster và hot shard.

**Không sử dụng số latency lab như lời hứa production**. Lab giúp học kỹ thuật đo, không chứng minh capacity.

## 8. Index và explain: chuẩn bị trước khi bắn tải

### 8.1. Xem index thực tế

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");
printjson(listings.getIndexes());
~~~

Xác nhận các indexes dự kiến. Nếu index build còn đang diễn ra, load test có thể đo chi phí build thay vì workload ổn định.

### 8.2. Explain Query A

~~~javascript
const q = {
  labTag: "mongo-perf-362-v1",
  tenantId: "t001",
  city: "HCM",
  status: "active",
  rentMillion: { $lte: 20 }
};

const plan = listings
  .find(
    q,
    { _id: 1, title: 1, createdAt: 1, rentMillion: 1 }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(plan);
~~~

Tập trung vào:

- **winningPlan**.
- **totalKeysExamined**.
- **totalDocsExamined**.
- **nReturned**.
- **executionTimeMillis**.
- Những stage như **IXSCAN, FETCH, SORT, COLLSCAN** khi xuất hiện.

Tên stage và cấu trúc output có thể thay đổi theo **MongoDB version/query engine**; không viết test cứng rằng mọi index scan đều phải xuất hiện dưới đúng một path JSON.

### 8.3. Tỷ lệ examined/returned

Giả sử:

~~~text
totalDocsExamined = 50.000
nReturned = 20
~~~

Đây là tín hiệu query đang xem rất nhiều document để trả ít kết quả. Nó **không đủ** để kết luận chính xác cần tạo index nào, nhưng cho thấy có thể cần xem selectivity/sort, filter fields, index prefix và dữ liệu.

Nếu totalDocsExamined=20 nhưng latency vẫn cao, hãy xét network, disk/cache, document size, pool queue và workload đồng thời.

### 8.4. Explain không phải benchmark throughput

**Explain** giúp hiểu query plan, không phải nguồn duy nhất để đo latency người dùng. Kế hoạch explain có overhead và có thể khác chạy tự nhiên trong một số tình huống; một phép explain đơn lẻ không cho biết distribution p95/p99.

Sử dụng:

~~~text
explain -> tìm đường thực thi và chi phí server
load test -> đo hành vi dưới tải đồng thời
monitoring -> xác định nút nghẽn hệ thống
~~~

### 8.5. Không tạo index ngay giữa phép so sánh mà quên đánh dấu phiên bản

Nếu thử trước/sau tối ưu:

1. Ghi nhận index definitions và dataset version ban đầu.
2. Chạy baseline nhiều lượt.
3. Thêm index được phê duyệt.
4. Chờ index build hoàn tất và hệ thống ổn định.
5. Chạy lại cùng workload/điều kiện.
6. So cả read latency, write latency, storage và cache.

Đừng so một lượt baseline cold cache với một lượt after warm cache rồi kết luận index mới giảm latency 80%.

## 9. Open-loop và closed-loop load generators

### 9.1. Closed-loop

Mỗi worker gửi request mới khi request trước hoàn tất:

~~~text
Worker 1: req -> wait -> req -> wait -> ...
Worker 2: req -> wait -> req -> wait -> ...
Worker 3: req -> wait -> req -> wait -> ...
~~~

Ưu điểm:

- Dễ lập trình.
- Giữ giới hạn concurrency.
- Phù hợp mô phỏng số clients cố định với hành vi request-response.

Nhược điểm:

- Khi server chậm, worker tạo request mới chậm theo.
- Offered load có thể tự giảm đúng khi hệ thống đang suy yếu.
- Khó chứng minh hệ thống chịu được arrival rate cố định giờ cao điểm.

### 9.2. Open-loop

Generator lên lịch request theo một arrival rate độc lập tương đối với thời gian hoàn tất các request cũ:

~~~text
Timeline: 0 ms, 10 ms, 20 ms, 30 ms, ...
           |      |      |      |
           +--> Requests được lập lịch

Các request có thể chờ thành hàng đợi nếu
server không theo kịp.
~~~

Open-loop phù hợp khi muốn hỏi:

> “Nếu người dùng thực sự tới với tốc độ 200 req/s trong 5 phút, hệ thống sẽ làm gì?”

Nhưng phải **giới hạn số in-flight requests**, có cơ chế backpressure/abort và bảo đảm load generator không tự trở thành bottleneck. Nếu bắn request vô hạn mà không có guard, benchmark có thể gây outage ngoài mục tiêu.

### 9.3. Coordinated omission

**Coordinated omission** xảy ra khi hệ đo vô tình bỏ sót thời gian chờ mà người dùng thực sự sẽ trải qua vì thời điểm phát request được điều chỉnh theo độ chậm của hệ thống.

Ví dụ:

~~~text
Ý định: gửi 1 request mỗi 10 ms.

Server bị stall 1.000 ms.

Closed-loop:
  chỉ gửi 1 request, đo latency 1.000 ms,
  rồi gửi request kế tiếp.

Open-loop theo lịch:
  có tới khoảng 100 arrival slots trong
  1.000 ms; queueing của nhiều requests
  phải được phản ánh hoặc báo dropped/late.
~~~

Với closed-loop, nhiều request đáng ra tới trong stall **không được phát**, nên histogram có thể không phản ánh tail latency của offered arrival process thực.

### 9.4. Tránh “sửa” coordinated omission bằng số liệu bịa

Không tự thêm 99 request giả với latency đoán trước rồi gọi đó là thực tế. Cần:

- Dùng load generator hỗ trợ **constant arrival rate** và latency histogram theo lịch.
- Ghi **scheduled time**, **actual start time**, **completion time**.
- Theo dõi **queue wait, in-flight count và dropped/rejected requests**.
- Áp chính sách khi generator quá tải.
- Công bố mô hình load để người đọc hiểu ngữ nghĩa percentile.

### 9.5. Mối quan hệ với user behavior

Không phải mọi ứng dụng đều cần open-loop thuần. Người dùng thực có **think time**, thao tác phụ thuộc response và một số request cần hoàn thành trước khi gửi request khác. Một workload đại diện có thể mô phỏng:

- Sessions với think time (closed-loop có pacing).
- Traffic API/automation theo arrival rate (open-loop).
- Burst theo giờ cao điểm.

Quan trọng là chọn mô hình khớp **hành vi cần đánh giá** và ghi rõ phương pháp.

## 10. Kế hoạch thí nghiệm có warmup và các giai đoạn

### 10.1. Warmup

Khi test vừa khởi động:

- Connections mới được mở.
- TLS handshake diễn ra.
- Pool tăng tới steady-state.
- Cache bắt đầu nóng lên.
- Query planner và các thành phần runtime đang ổn định.

Nếu production thường chạy lâu, nên có **warmup** trước giai đoạn đo. Nếu cold start là điều cần đánh giá, hãy chạy **bài test cold riêng**; đừng loại nó rồi tuyên bố cold performance tốt.

### 10.2. Baseline

Chạy một tải nhỏ để kiểm tra:

- Script đúng query shapes.
- Credentials không lỗi.
- Index đã sẵn sàng.
- Server không có tình trạng bất thường trước test.
- Load generator còn dư CPU/memory/network.

Nếu baseline đã timeout, không cần vội tăng tới tải cực đại.

### 10.3. Ramp-up

Ví dụ:

~~~text
0-5 phút:   50 RPS
5-10 phút: 100 RPS
10-15 phút:150 RPS
15-20 phút:200 RPS
~~~

Theo dõi p95/p99, queueing, throughput, errors và resource tại từng mức. Tránh tăng quá nhanh khiến các giai đoạn chồng lấn và khó xác định điểm saturation.

### 10.4. Steady-state

Giữ một tải ổn định đủ lâu, ví dụ 20–30 phút, để thu được nhiều mẫu và thấy:

- Cache ổn định.
- Batching/journaling/replication effects.
- Background jobs định kỳ.
- Kiểu lỗi lặp lại dưới tải.

Thời gian hợp lý phụ thuộc loại workload và yêu cầu thống kê; 30 phút chỉ là ví dụ.

### 10.5. Spike

Ví dụ tăng từ 200 lên 500 RPS trong 30 giây. Đo:

- Hệ thống phản ứng ra sao.
- Queue có tích tụ không.
- Lỗi/timeout và recovery time.
- Có giảm offered load hay load shedding không.

Spike test cần phạm vi an toàn, không nên dùng trên production một cách tùy tiện.

### 10.6. Soak

Chạy nhiều giờ để phát hiện:

- Memory leak/client connection leak.
- Cache churn.
- Disk/journal pressure.
- Oplog lag.
- Slow operations tích lũy.
- Những job định kỳ chồng tải.

Soak test có mục tiêu khác với “tìm RPS cao nhất trong 60 giây”.

### 10.7. Các kịch bản nên tách riêng

| Kịch bản | Mục tiêu |
| --- | --- |
| Cold-start | Độ trễ ban đầu/cache rỗng |
| Warm steady | SLO bình thường |
| Peak | Khả năng chịu giờ cao điểm |
| Spike | Hành vi khi arrival rate tăng đột ngột |
| Soak | Tính ổn định trong thời gian dài |
| Batch overlap | Ảnh hưởng import/reporting chạy đồng thời |
| Replica lag stress | Write concern/read preference khi replication chậm |
| Recovery scenario | Khôi phục sau failover, khi đã có môi trường chaos test riêng |

Không ép tất cả câu hỏi vào cùng một kịch bản để rồi không biết nguyên nhân của kết quả.

## 11. Node.js benchmark cơ bản: closed-loop, giới hạn concurrency

### 11.1. Vì sao sử dụng Node.js driver?

MongoDB driver cho phép đo **end-to-end thời gian thực hiện thao tác từ ứng dụng** (gồm thời gian chờ driver/network/server theo cách sử dụng Promise). Đây là một điểm quan sát gần nhu cầu backend hơn một phép explain đơn lẻ.

Tuy nhiên, script dưới đây là **demo closed-loop**, không thể thay thế một distributed load generator chuyên nghiệp có hỗ trợ constant arrival rate và coordinated-omission correction.

### 11.2. Chuẩn bị

Trong một thư mục lab do bạn quản lý (không phải project file được Worker tạo), có thể cài:

~~~bash
npm init -y
npm install mongodb
~~~

Chuẩn bị Node.js phiên bản được MongoDB Node.js driver tương ứng hỗ trợ và biến môi trường **MONGODB_URI** trỏ tới lab được phép thử.

Script ví dụ dùng cú pháp ES modules, lưu thành **bench362.mjs** ở môi trường học của bạn. Những command này là hướng dẫn trong tài liệu, **không được Worker chạy**.

### 11.3. Script benchmark

~~~javascript
// bench362.mjs
import { MongoClient } from "mongodb";
import { performance } from "node:perf_hooks";

const uri = process.env.MONGODB_URI;
if (!uri) {
  throw new Error("Thiếu MONGODB_URI");
}

const concurrency = 8;
const warmupSeconds = 10;
const measureSeconds = 30;
const allowWrites = process.env.BENCH362_ALLOW_WRITES === "true";
const tag = "mongo-perf-362-v1";

const client = new MongoClient(uri, {
  maxPoolSize: 16,
  serverSelectionTimeoutMS: 5000,
  socketTimeoutMS: 10000,
  retryWrites: false
});

function percentile(values, p) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.max(1, Math.ceil(p * sorted.length)) - 1;
  return sorted[index];
}

function summarize(name, values, errors, elapsedSeconds) {
  return {
    operation: name,
    completedSuccess: values.length,
    errors,
    successfulOpsPerSecond:
      Number((values.length / elapsedSeconds).toFixed(2)),
    p50Ms: percentile(values, 0.50),
    p95Ms: percentile(values, 0.95),
    p99Ms: percentile(values, 0.99),
    maxMs: values.length
      ? values.reduce((max, value) => Math.max(max, value), -Infinity)
      : null
  };
}

await client.connect();

try {
  const lab = client.db("mongo_perf_lab_362");
  const listings = lab.collection("lab_listings");
  const counters = lab.collection("lab_counters");

  const exists = await listings.countDocuments({
    labTag: tag
  }, { limit: 1 });
  if (exists === 0) {
    throw new Error(
      "Chưa seed dữ liệu lab. Hãy chạy mục 7 trước."
    );
  }

  const operations = allowWrites
    ? [
        ...Array(14).fill("feed"),
        ...Array(3).fill("point"),
        ...Array(2).fill("summary"),
        "counter"
      ]
    : [
        ...Array(14).fill("feed"),
        ...Array(4).fill("point"),
        ...Array(2).fill("summary")
      ];

  const measures = Object.fromEntries(
    [...new Set(operations)].map(name => [
      name, { latencies: [], errors: 0 }
    ])
  );

  async function perform(name, workerId, iteration) {
    if (name === "feed") {
      return listings.find({
        labTag: tag,
        tenantId: "t001",
        city: "HCM",
        status: "active",
        rentMillion: { $lte: 20 }
      }, {
        projection: {
          _id: 1,
          title: 1,
          rentMillion: 1,
          createdAt: 1
        },
        maxTimeMS: 3000
      })
      .sort({ createdAt: -1, _id: -1 })
      .limit(20)
      .toArray();
    }

    if (name === "point") {
      const idNumber = (workerId * 997 + iteration * 47) % 12000;
      const id = "b362-listing-" +
        String(idNumber).padStart(6, "0");

      return listings.findOne(
        { _id: id, labTag: tag },
        {
          projection: { _id: 1, title: 1, tenantId: 1 },
          maxTimeMS: 3000
        }
      );
    }

    if (name === "summary") {
      return listings.aggregate([
        {
          $match: {
            labTag: tag,
            tenantId: "t001",
            status: "active"
          }
        },
        {
          $group: {
            _id: "$city",
            count: { $sum: 1 }
          }
        }
      ], { maxTimeMS: 3000 }).toArray();
    }

    if (name === "counter" && allowWrites) {
      return counters.updateOne(
        {
          _id: "b362-counter-" + (workerId % 16),
          labTag: tag
        },
        { $inc: { increments: 1 } },
        { upsert: false, writeConcern: { w: "majority" } }
      );
    }

    throw new Error("Tên operation không hợp lệ: " + name);
  }

  const testStart = performance.now();
  const measureStart = testStart + warmupSeconds * 1000;
  const measureEnd = measureStart + measureSeconds * 1000;

  async function worker(workerId) {
    let iteration = workerId;
    while (performance.now() < measureEnd) {
      const name = operations[iteration % operations.length];
      const started = performance.now();
      let error = null;

      try {
        await perform(name, workerId, iteration);
      } catch (e) {
        error = e;
      }

      const ended = performance.now();
      const inMeasurementWindow =
        started >= measureStart &&
        ended <= measureEnd;

      if (inMeasurementWindow) {
        if (error) {
          measures[name].errors++;
        } else {
          measures[name].latencies.push(
            Number((ended - started).toFixed(3))
          );
        }
      }

      // Nếu không ghi nhận lỗi, script vẫn tiếp tục để đo
      // error rate. Không retry thủ công nhằm tránh giấu lỗi.
      iteration++;
    }
  }

  await Promise.all(
    Array.from({ length: concurrency },
      (_, id) => worker(id))
  );

  const report = Object.entries(measures).map(
    ([name, data]) => {
      const row = summarize(
        name, data.latencies, data.errors, measureSeconds
      );
      const total = data.latencies.length + data.errors;
      return {
        ...row,
        errorRatePct: total
          ? Number((100 * data.errors / total).toFixed(3))
          : null
      };
    }
  );

  console.log(JSON.stringify({
    mode: "closed-loop",
    concurrency,
    warmupSeconds,
    measureSeconds,
    allowWrites,
    report
  }, null, 2));
} finally {
  await client.close();
}
~~~

### 11.4. Cách chạy read-only

Thiết lập biến môi trường MONGODB_URI theo hệ điều hành và secret policy, rồi chạy:

~~~bash
node bench362.mjs
~~~

Chế độ mặc định **không gọi counter update**. Workload có 70% feed, 20% point và 10% summary theo số lượt được lập lịch bởi từng worker.

### 11.5. Bật ghi chỉ trong lab

Khi đã xác nhận collection **mongo_perf_lab_362.lab_counters** là dữ liệu lab:

~~~bash
# Với shell bash trên máy lab:
BENCH362_ALLOW_WRITES=true node bench362.mjs
~~~

Workload chuyển thành **70% feed, 15% point, 10% summary, 5% counter update**. Do các operations có thời gian khác nhau và generator là closed-loop, **tỷ lệ hoàn tất trong một cửa sổ thời gian có thể lệch** một chút so với tỷ lệ lượt đã lập lịch.

Nếu không muốn phát sinh bất kỳ write nào, **không bật biến BENCH362_ALLOW_WRITES**.

### 11.6. Script này đo được gì?

Với mỗi operation:

- Số requests thành công đã hoàn tất **trong measurement window**.
- Số thao tác lỗi.
- p50/p95/p99 từ **những thao tác thành công**.
- Successful operations per second theo cửa sổ đo.

**Quan trọng:** errors và timeouts được báo riêng, **không đưa vào latency percentile** trong script đơn giản này. Nếu cần SLO end-to-end cho tất cả requests, phải báo tỷ lệ good events/total events và xử lý timeout theo policy. Đừng che một tỷ lệ timeout lớn bằng percentile chỉ tính trên những request thành công.

### 11.7. Hạn chế kỹ thuật của demo

Đây là script học tập; không phải load test production:

- **Closed-loop**: không cam kết offered arrival rate.
- Chỉ một process; CPU của generator có thể là bottleneck.
- Ghi samples vào Array; không phù hợp hàng chục triệu observations.
- Không xuất histogram mergeable hoặc confidence intervals.
- Không đo queue-wait riêng của driver pool.
- Không có warm/cold isolation nâng cao.
- Không theo dõi failed requests hoàn tất sau measurement window.
- Không capture raw server metrics hoặc index statistics trong cùng report.
- Dùng một query feed rất nóng, không mô phỏng đầy đủ đa dạng query parameters.
- Tỷ lệ requests theo iteration không bảo đảm traffic phân phối hệt production.

Để benchmark nghiêm ngặt nên dùng công cụ tạo tải có hỗ trợ **arrival-rate control, histogram, labels, distributed load generation và metrics integration**, hoặc phát triển harness có các tính năng đó.

### 11.8. Một lỗi đo dễ bỏ qua: warmup phải có cùng mix

Warmup chỉ chạy point lookup rồi steady-state chạy aggregation và write có thể tạo trạng thái cache/pool khác mục tiêu. Trong demo, cùng các operations được chạy xuyên suốt warmup và measurement, giúp giảm sự khác biệt không cần thiết.

## 12. Tính p50/p95/p99 khi có lỗi và timeout

### 12.1. Thành công và thất bại

Giả sử ở mức tải 200 req/s:

~~~text
Requests đã hoàn tất: 10.000
Success:               9.700
Timeout/error:            300
~~~

Error rate:

\[
\frac{300}{10.000}\times100\%=3\%
\]

Nếu chỉ đưa 9.700 latency thành công vào p99, có thể thu p99 đẹp dù 3% khách hàng nhận lỗi. Do đó báo **p99 thành công + error/timeout rate**, hoặc dùng thêm SLI “tỷ lệ tất cả requests hoàn thành thành công dưới 300 ms”.

### 12.2. Request còn in-flight tại cuối cửa sổ

Benchmark chạy 60 giây rồi dừng nhận mẫu. Những request gửi trong cửa sổ nhưng hoàn tất sau giây thứ 60 sẽ bị mất khỏi report nếu không có chính sách rõ.

Các lựa chọn:

- Đếm theo **completion timestamp** trong cửa sổ ổn định.
- Đếm theo **arrival timestamp** rồi chờ in-flight kết thúc với deadline.
- Theo dõi **in-flight/drained count** và báo riêng những request bị cắt.

Phải công bố phương pháp; nếu không p99 có thể bị **survivorship bias** do những request chậm nhất chưa hoàn tất.

### 12.3. Histogram

Thay vì giữ từng sample không giới hạn, các hệ thống thực tế dùng **histogram**:

~~~text
Latency buckets:
  <= 10 ms
  <= 25 ms
  <= 50 ms
  <= 100 ms
  <= 250 ms
  <= 500 ms
  <= 1.000 ms
  > 1.000 ms
~~~

Histogram cần **bucket boundaries phù hợp SLO**. Nếu p99 mục tiêu 300 ms nhưng buckets chỉ có 100/1.000 ms, p99 ước lượng sẽ quá thô để quyết định pass/fail sát 300 ms.

### 12.4. HdrHistogram và fixed buckets

Các công cụ chuyên dụng có thể dùng HdrHistogram hoặc dạng histogram có thể merge theo nguyên tắc riêng. Quan trọng:

- Histogram phải giữ thông tin đuôi đủ chính xác.
- Các workers dùng compatible bucket scheme.
- Gộp **counts theo buckets** trước khi tính percentile.
- Không gộp p99 số học của từng worker.
- Ghi đơn vị (**microseconds** hay **milliseconds**) rõ ràng.

### 12.5. Sample count và low-traffic endpoints

Một endpoint chỉ có 30 requests trong 30 phút không có đủ quan sát để suy ra p99 đáng tin. Nên:

- Báo sample count cùng percentile.
- Dùng cửa sổ dài hơn hoặc synthetic load riêng.
- Xem max và từng slow trace.
- Cân nhắc confidence interval/bootstrapping khi so hai phiên bản.
- Không tự tăng tần suất một endpoint từ 0,01 RPS lên 100 RPS mà vẫn coi là “representative” nếu mục tiêu đang đo tổng tải bình thường.

### 12.6. Outlier không mặc nhiên là lỗi đo

Một request mất 5 giây có thể là:

- GC pause ở client.
- Network stall.
- TLS reconnect.
- Connection pool timeout.
- Disk I/O spike.
- Server failover.

Đừng tự loại tất cả outliers để p99 đẹp hơn. Nếu loại một sample vì lỗi đo rõ ràng, cần tiêu chí trước thí nghiệm và giữ audit trail.

## 13. Khi nào generator là bottleneck?

### 13.1. Dấu hiệu

- CPU load generator gần 100%.
- Generator không gửi đủ offered RPS.
- Event loop lag lớn.
- Memory tăng do lưu quá nhiều samples.
- Network interface client đạt throughput giới hạn.
- Connection pool thiết lập sai hoặc chỉ có ít connections.
- TLS/DNS/serialization tiêu tốn phần lớn thời gian phía client.

Nếu generator giới hạn ở 150 RPS, không thể kết luận MongoDB capacity tối đa cũng là 150 RPS.

### 13.2. Tách load generators khỏi database

Một test chuyên nghiệp có thể dùng:

~~~text
Load Generator A ----+
Load Generator B ----+----> App / MongoDB
Load Generator C ----+
~~~

Và thu thập:

- Offered RPS của từng generator.
- Achieved RPS.
- CPU/network client.
- Latency histogram có thể merge.
- Tỷ lệ connection errors.
- Clock synchronization và timestamp conventions.

### 13.3. Không đo từ cùng host khi muốn thấy network thực

Mongosh trên cùng host mongod có thể giảm đáng kể network/TLS latency. Nếu production chạy app trong AZ/region khác, benchmark phải mô phỏng network placement tương đương.

Ngược lại, không đặt generator ở nơi có network xa bất thường rồi quy toàn bộ tăng latency cho MongoDB.

## 14. Chỉ số phía MongoDB để giải thích p99

### 14.1. Client metrics và server metrics phải đi cùng nhau

Một bảng điều tra:

| Triệu chứng client | Dữ liệu cần xem từ MongoDB/hạ tầng |
| --- | --- |
| p99 tăng nhưng p50 ổn | GC, pool waits, disk spikes, slow queries, failover |
| Throughput phẳng khi offered tăng | CPU, admission queues, disk throughput, lock contention |
| Update p99 cao | Journal/durability, lock/write conflicts, majority replication |
| Query có nReturned ít mà chậm | Keys/docs examined, disk misses, sort, network |
| Khi chạy aggregation thì feed chậm | CPU/cache/IO contention, spill, concurrent requests |
| Lỗi timeout tăng | Pool size, server selection, network, maxTimeMS, overload |

### 14.2. serverStatus

Với account có quyền đọc metrics phù hợp:

~~~javascript
const admin = db.getSiblingDB("admin");
const status = admin.runCommand({ serverStatus: 1 });

printjson({
  uptime: status.uptime,
  connections: status.connections,
  opcounters: status.opcounters,
  wiredTiger: {
    cache: status.wiredTiger?.cache
  }
});
~~~

Output có thể lớn và field names phụ thuộc server version/topology. **Counters như opcounters thường là tích lũy**, nên cần lấy **delta giữa hai thời điểm**, không coi số tuyệt đối là ops/second.

### 14.3. WiredTiger cache

Theo dõi các tín hiệu phù hợp như:

- Cache used/dirty bytes.
- Pages read into cache.
- Pages written/evicted.
- Eviction activity.
- Disk read/write latency.
- Tỷ lệ working set vượt khả năng cache.

Một benchmark với dataset vừa RAM có thể có p99 tốt, nhưng khi working set lớn hơn cache, read latency và disk I/O tăng khác hẳn.

### 14.4. Connections và pool

MongoDB server có thống kê connections; driver có **connection pool** riêng.

Nếu app có:

~~~text
maxPoolSize = 10
200 requests in flight
~~~

nhiều requests phải đợi một socket sẵn sàng. Client latency p99 có thể tăng do pool queue dù server query execution vẫn nhanh.

Đo driver pool checkout wait cùng server metrics để xác định cần tăng pool, giảm concurrency hoặc sửa vấn đề query chậm giữ connection quá lâu.

### 14.5. Slow operations / profiler

MongoDB có database profiler và các cơ chế slow query logs/APM, tùy phiên bản/cấu hình.

Trên lab có quyền quản trị, có thể xem profiling level:

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
printjson(lab.getProfilingStatus());
~~~

Việc bật profiler có thể tạo overhead, lưu nội dung truy vấn/metadata nhạy cảm và khác hành vi trên một số Atlas deployment. **Không bật profiling level 2 trên production chỉ để lấy thêm số liệu benchmark** nếu chưa đánh giá chi phí/retention.

### 14.6. currentOp

Khi có thao tác chậm kéo dài, công cụ currentOp/monitoring phù hợp có thể giúp quan sát lệnh đang chạy, thời gian và trạng thái chờ trong phạm vi quyền được cấp. Không lạm dụng killOp hoặc thay hệ thống đang chạy nếu chưa đánh giá side effects.

### 14.7. Replication và write concern

Với replica set, ghi **w:"majority"** có thể liên quan đến replication/durability; write latency không chỉ là thời gian cập nhật document trên primary.

Theo dõi:

- Secondary replication lag.
- Primary/secondary health.
- Oplog window.
- Write concern timeouts.
- Elections/failovers trong test.

Không so write p99 giữa hai thí nghiệm nếu một bên dùng w:1 còn bên kia dùng w:"majority" nhưng báo cả hai là cùng workload.

### 14.8. Atlas metrics

Trên MongoDB Atlas, có thể xem những biểu đồ/metrics tương ứng như CPU, memory, operation execution, connections, cache, disk, replication và slow queries tùy cluster/tier. Ghi lại time window khớp benchmark.

Chọn metrics thuộc cluster thực sự được thử; không nhìn một biểu đồ trung bình 24 giờ để giải thích spike 30 giây.

## 15. Tối ưu dựa trên bottleneck, không tối ưu theo trực giác

### 15.1. Nếu p99 tăng vì COLLSCAN

Phương án:

1. Xem query shape và selectivity.
2. Kiểm tra hiện có index phù hợp chưa.
3. Đo keys/docs examined.
4. Cân nhắc index/compound index phù hợp sort/filter.
5. Đánh giá trade-off ghi/index size.
6. Chạy lại cùng dataset/workload.

Không tạo một index mới cho mọi field chỉ vì query có nhiều điều kiện.

### 15.2. Nếu p99 tăng vì SORT

Một sort không được index hỗ trợ có thể cần thêm memory và có thể spill (tùy operation/cấu hình). Cần xem:

- Equality prefix và sort order.
- Cardinality, limit, query projection.
- Index phù hợp.
- Số lượng documents phải xét trước khi sort.

Không kết luận “thiếu RAM” trước khi xem kế hoạch.

### 15.3. Nếu p99 tăng vì pool queue

Một số bước:

- Đo checkout wait/checked-out connection counts.
- Kiểm tra query có giữ socket quá lâu không.
- Kiểm tra số app instances và số connections server.
- Điều chỉnh concurrency/pool với thử nghiệm có kiểm soát.

Tăng maxPoolSize tùy tiện có thể tạo thêm áp lực lên server. Một pool lớn không sửa được query đang block disk I/O.

### 15.4. Nếu p99 tăng vì disk

Cần kiểm tra:

- Working set so với WiredTiger cache.
- Disk latency/IOPS/throughput.
- Compaction, backup, index build hoặc batch job đang chạy.
- Read preference, tier, storage performance.

Một index giúp giảm docs examined có thể làm disk reads ít hơn; nhưng nếu workload cần đọc nhiều dữ liệu thật, phải thiết kế pagination/read model hoặc hạ tầng phù hợp.

### 15.5. Nếu update p99 cao

Điều tra:

- Hot document contention.
- Số index phải cập nhật khi write.
- Array growth hoặc document updates.
- Write conflicts/retries.
- Journal/storage latency.
- Write concern majority và secondary lag.

Nếu chỉ thử một hot counter nhưng production ghi phân tán, có thể kết luận sai rằng mọi write đều cần sharding.

### 15.6. Nếu app logic là bottleneck

Khi database query nhanh nhưng API p99 cao:

- Kiểm tra serialization/decompression.
- Logic service và external API calls.
- Connection pool wait.
- Large response payload.
- Thread pool/event loop.
- GC pauses.

**Không tối ưu MongoDB index để sửa một vấn đề xảy ra hoàn toàn trước hoặc sau query.**

## 16. So sánh trước/sau tối ưu cho công bằng

### 16.1. Giữ nguyên điều kiện

Ví dụ báo cáo:

~~~text
Baseline:
  dataset: synthetic-v1
  indexes: ixA
  cluster: staging-M
  load: 200 RPS, 70/15/10/5
  duration: 30 min

Change:
  thêm ixB

After:
  dataset: synthetic-v1
  indexes: ixA + ixB
  cluster: staging-M
  load: 200 RPS, 70/15/10/5
  duration: 30 min
~~~

Kết quả có giá trị khi **điều kiện chỉ thay đổi ở yếu tố đang thử**, ngoại trừ những biến động được ghi nhận và đánh giá.

### 16.2. Lặp nhiều lượt

Một lượt:

~~~text
Before p99 = 290 ms
After p99  = 260 ms
~~~

chưa đủ để chứng minh cải thiện ổn định. Chạy nhiều lượt theo thứ tự phù hợp, ghi các yếu tố noise như cache, GC, background maintenance và traffic từ hệ thống khác.

Nếu biến động 30–50 ms tự nhiên giữa những lần thử, chênh 30 ms có thể không đáng tin nếu không có đủ mẫu/lặp lại.

### 16.3. Báo cả hiệu năng và chi phí

Một index có thể:

- Giảm feed p95 từ 180 xuống 95 ms.
- Tăng insert p99 từ 120 lên 190 ms.
- Tăng storage index 25%.

Không nên chỉ báo feed tốt hơn rồi triển khai nếu write SLO trở nên không đạt.

### 16.4. Percentile difference

Khi before/after:

~~~text
p99 before: 300 ms
p99 after:  240 ms
~~~

Giảm tuyệt đối **60 ms**, giảm tương đối **20%**. Nhưng cần kiểm tra **confidence**, sample count, workload đạt mục tiêu và error rate. Nếu after có nhiều timeouts hơn, p99 của successful requests giảm không nhất thiết là cải thiện.

### 16.5. Lưu artifacts của benchmark

Ít nhất ghi:

- Timestamp, owner, commit/version.
- MongoDB version và FCV nếu liên quan.
- Driver/runtime version.
- Topology/cluster size/network.
- Dataset version và số lượng documents.
- Index definitions.
- Query shapes/mix.
- Load model, offered rate, concurrency, warmup, duration.
- SLI/SLO pass/fail.
- Per-operation samples, percentiles, throughput, errors.
- Client, server, resource charts.
- Known limitations.

Không chỉ lưu một ảnh dashboard không có thông tin môi trường.

## 17. Phân tích từng cửa sổ thời gian

### 17.1. Aggregated p99 che giấu sự cố

Một bài test 30 phút có thể gồm:

~~~text
25 phút ổn định: p99 80 ms
 5 phút disk spike: p99 2.000 ms
~~~

Percentile gộp cả 30 phút có thể có ý nghĩa nhưng không cho biết **khi nào** spike diễn ra. Cần time series buckets, ví dụ mỗi 1 phút, kèm histogram gộp cho cả giai đoạn.

### 17.2. Không trung bình các percentiles theo phút

Mỗi phút có số requests khác nhau. Nếu báo “p99 toàn bài” thì tính trên phân phối gộp. Nếu muốn tìm **p99 tệ nhất theo phút**, đó là một chỉ số khác:

~~~text
max( p99_of_minute_1, ..., p99_of_minute_30 )
~~~

Không gọi max của các p99 phút là p99 chung và cũng không gọi average của chúng là percentile tổng.

### 17.3. Cửa sổ trượt

Một dashboard có thể dùng rolling 5-minute/30-minute histograms. Điều quan trọng là:

- Mỗi cửa sổ có đủ mẫu không?
- Histogram merge có đúng không?
- Time buckets có cùng đơn vị/semantics không?
- Lỗi/timeout có bị loại sai không?

Nếu sample count thấp, hiển thị thông báo **low sample size** thay vì một con số p99 quá tự tin.

## 18. Phân tích workload read/write hỗn hợp

### 18.1. Chạy riêng từng nhóm không đủ

Nếu benchmark:

~~~text
SearchFeed alone: p99 100 ms
Update alone:     p99 50 ms
~~~

không có nghĩa khi chạy đồng thời:

~~~text
SearchFeed 140 RPS + Update 10 RPS
~~~

cả hai vẫn giữ p99 như trên. Chúng có thể cạnh tranh CPU, disk, WiredTiger cache, write tickets hoặc locks.

### 18.2. Thiết kế kịch bản hỗn hợp

Một kịch bản:

~~~text
SearchFeed:    70%
GetListing:    15%
CitySummary:   10%
UpdateCounter:  5%
~~~

Nên giữ tỷ lệ theo thời gian, theo dõi thực tế đạt được và báo p50/p95/p99 của **từng operation**.

### 18.3. Hot write skew

Nếu 10 workers cùng update một document, sẽ có contention. Nếu production ghi mỗi request vào document khác nhau, benchmark một hot key đang cố tình đo **worst-case contention**, không đại diện cho throughput viết chung.

Tốt nhất có cả:

- Write workload phân tán.
- Hot-spot workload với tỷ lệ giống thực tế.
- Một stress test contention riêng.

### 18.4. Index trade-off

Thêm compound index phục vụ read có thể làm mỗi insert/update phải cập nhật thêm index entries. Đo **read và write SLO cùng lúc** để tránh tối ưu cục bộ.

## 19. Query pagination và response payload

### 19.1. Phân trang theo offset

~~~javascript
db.listings.find({ status: "active" })
  .sort({ createdAt: -1 })
  .skip(100000)
  .limit(20);
~~~

Với skip rất lớn, database có thể phải duyệt/bỏ qua nhiều entries. Nếu production có deep pagination, benchmark chỉ page 1 sẽ bỏ sót chi phí thực tế.

### 19.2. Keyset pagination

Một hướng thường phù hợp hơn với feed có thứ tự ổn định:

~~~javascript
db.listings.find({
  tenantId: "t001",
  status: "active",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Biến **lastCreatedAt/lastId** lấy từ trang trước; code chỉ minh họa shape. Query phải có đúng index và xử lý pagination token/tenant authorization. Khi so sánh skip và keyset, cần cùng page depth, dữ liệu và response size.

### 19.3. Projection

Nếu API chỉ trả title/price, đừng để benchmark lấy cả description dài, embedded images metadata và nested arrays rồi so với một API thật chỉ project vài fields. Ngược lại, nếu API thật gửi payload lớn, benchmark projection quá hẹp sẽ làm đẹp network latency giả tạo.

### 19.4. Cursor và batching

Một find chỉ đo tới khi cursor được tạo mà không đọc toàn bộ documents **không tương đương** với đo tới khi API đã consume kết quả. Trong Node.js benchmark, **toArray()** khiến quá trình retrieval/transfer/deserialization của tập kết quả được tính vào Promise latency.

Với result set rất lớn, dùng streaming/pagination thay vì toArray() trong production; và đo latency theo user-visible chunks hoặc complete response đúng nhu cầu.

## 20. Một mẫu báo cáo benchmark có thể đánh giá

### 20.1. Thông tin môi trường

~~~yaml
benchmarkId: "mongo-perf-362-example"
environment: "staging-isolated"
dataset: "synthetic-v1"
mongoVersion: "CAPTURE_FROM_DEPLOYMENT"
driverVersion: "CAPTURE_FROM_PACKAGE"
topology: "replica-set"
loadModel: "open-loop-constant-arrival"
warmupMinutes: 5
steadyMinutes: 30
offeredRps: 200
mix:
  searchFeed: 0.70
  getListing: 0.15
  citySummary: 0.10
  updateCounter: 0.05
~~~

Đây là mẫu metadata do nhóm tự định nghĩa, không phải cấu hình MongoDB bắt buộc.

### 20.2. Bảng kết quả minh họa

| Operation | Count thành công | p50 | p95 | p99 | Lỗi/timeout | SLO |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| SearchFeed | 251.000 | 38 ms | 141 ms | 280 ms | 0,1% | PASS |
| GetListing | 53.800 | 9 ms | 44 ms | 107 ms | 0,1% | PASS |
| CitySummary | 35.900 | 86 ms | 390 ms | 870 ms | 0,3% | FAIL p99 |
| UpdateCounter | 17.700 | 45 ms | 175 ms | 420 ms | 0,1% | FAIL p99 |

**Tất cả số trong bảng là số minh họa**, không được đo từ lab này. Đánh giá PASS/FAIL giả định SLO ở mục 4 và môi trường đáp ứng tải đề ra.

### 20.3. Cách đọc báo cáo

- SearchFeed đạt mục tiêu p99 300 ms và error rate.
- GetListing đạt mục tiêu p99 120 ms.
- CitySummary vượt p99 800 ms; cần xem aggregation plan/CPU/cache.
- UpdateCounter vượt p99 400 ms; cần xem hot document, write concern và storage.

Điều chưa được kết luận:

- Liệu generator thật sự gửi đủ 200 RPS không? Cần offered/achieved.
- Liệu một phút cuối có p99 5 giây không? Cần time series/histogram.
- Có background index build không? Cần environment log.
- Mức tự tin của chênh lệch trước/sau? Cần số lần lặp và sai số.

### 20.4. Quyết định tối ưu

Một báo cáo tốt kết thúc bằng **hành động kiểm chứng được**:

~~~text
Issue:
  CitySummary p99 vượt 800 ms ở offered 200 RPS.

Hypothesis:
  Aggregation đọc quá nhiều documents và cache misses.

Evidence needed:
  explain executionStats, WiredTiger cache,
  disk latency, operator-level time series.

Change:
  thử index/summary precomputation phù hợp.

Verification:
  chạy lại cùng workload và kiểm tra
  cả SearchFeed, UpdateCounter, storage cost.
~~~

Không kết thúc chỉ bằng câu “tăng CPU thêm” nếu chưa xác định điểm nghẽn.

## 21. Các bẫy đo lường phổ biến

| Sai lầm | Kết quả gây hiểu nhầm | Cách khắc phục |
| --- | --- | --- |
| Chạy query một lần | Không có phân phối p95/p99 | Thu thập nhiều observations |
| Benchmark trên 100 documents | Cache/index quá dễ | Dataset tương đương về working set/selectivity |
| Chỉ đo mean | Không thấy tail latency | p50/p95/p99 + errors |
| Chỉ đo p99 | Không thấy throughput và error rate | Báo nhiều SLIs |
| p99 từ 20 samples | p99 gần hoặc bằng max | Ghi sample count, tăng giai đoạn đo |
| Trung bình p99 nhiều phút | Không phải p99 gộp | Merge histogram/raw data |
| Gộp mọi operation | Slow operation bị traffic nhanh che | Tách endpoint/query shape |
| Loại timeout khỏi báo cáo | Percentile trông đẹp hơn | Báo error/timeout và good-event rate |
| Dừng test khi có request đang chạy | Bỏ mất tail chậm | Chính sách in-flight/drain rõ |
| Generator closed-loop ở peak | Offered load tự giảm khi server chậm | Open-loop arrival-rate benchmark |
| Không đo generator CPU | Nhầm giới hạn generator thành DB | Client resource telemetry |
| Chỉ test hot cache | Cold I/O bị che | Kịch bản cold riêng |
| Chỉ test page 1 | Không thấy deep pagination | Trộn page depths thực tế |
| Chỉ test _id lookup | Bỏ qua aggregation/sort | Query mix đại diện |
| Thiếu write workload | Không thấy index maintenance/contention | Chạy read+write mix |
| Seed data random đều | Bỏ qua hot tenants/data skew | Phân bố phản ánh production |
| Trộn w:1 và w:majority | Write latency không so được | Cố định write concern |
| Client gần DB khác production | Network latency sai | Network placement tương đương |
| Dùng explain làm latency SLI | Không phải client response time | Đo từ driver/API |
| Tạo index giữa test | Workload thay đổi trong lúc đo | Tách baseline/after |
| Test chỉ một lượt | Noise có thể là “cải thiện” | Lặp thí nghiệm |
| Chỉ nhìn CPU average | Bỏ qua disk/pool/queue | Resource metrics đa chiều |
| Driver auto-retry không được báo | Error/rate/latency bị đổi | Ghi retry policy/attempts |
| Dữ liệu thay đổi khi so hai bản | Không so được nguyên nhân | Dataset/version ổn định |
| Query kết quả khác giữa hai lần | Không cùng workload logic | Verify counts/semantic correctness |
| Chạy tải trên production vô kiểm soát | Có thể outage | Môi trường riêng, guardrails |

## 22. Checklist từ yêu cầu đến quyết định

### 22.1. Trước khi benchmark

1. Ghi SLO cần đạt và khoảng thời gian đo.
2. Phân biệt p50/p95/p99 theo **operation**.
3. Thu thập query shapes và traffic mix từ nguồn phù hợp.
4. Ghi data size/cardinality/selectivity/hot keys.
5. Ghi index definitions.
6. Xác định load model và offered RPS/concurrency.
7. Chọn client location, driver, TLS, pool settings.
8. Chuẩn bị backup/rollback và môi trường được phép.

### 22.2. Khi chạy

1. Xác minh seed/index/cluster health.
2. Warmup phù hợp mục tiêu.
3. Ghi sample counts, offered, achieved throughput.
4. Đo success/failure/timeouts riêng.
5. Ghi latency histograms theo operation.
6. Theo dõi database CPU, cache, disk, connections, replication.
7. Theo dõi resource của load generator.
8. Dừng/hạ tải theo safety limits nếu có nguy cơ gián đoạn.

### 22.3. Khi phân tích

1. Kiểm tra dữ liệu có đủ mẫu cho p99.
2. Không lấy trung bình các percentiles.
3. So per-operation SLO và overall UX.
4. Xác nhận offered load và actual throughput.
5. Phân tích time series để nhận diện spikes.
6. Xem explain/slow query/profiler theo quyền.
7. Phân biệt server bottleneck, network và pool queue.
8. Ghi các yếu tố biến thiên/những giới hạn phép đo.

### 22.4. Khi tối ưu và thử lại

1. Nêu **một giả thuyết** cụ thể.
2. Đổi một nhóm yếu tố có chủ đích.
3. Giữ dataset, workload và môi trường gần như không đổi.
4. Lặp test đủ lần.
5. So read/write p50/p95/p99, errors và throughput.
6. Đo storage/CPU/IO trade-off.
7. Cập nhật runbook/dashboard và quyết định deploy.

## 23. Bài tập thực hành

### Bài 1 — Đọc percentile

Giải thích p50, p95, p99 trên 100 requests. p99 có phải thời gian chậm nhất không?

### Bài 2 — Nearest-rank

Với 20 latency: 18, 23, 21, 20, 19, 24, 22, 26, 27, 25, 29, 31, 28, 30, 32, 35, 34, 40, 120, 600 ms, tính p50/p95/p99 bằng nearest-rank.

### Bài 3 — Mean và tail

99 requests mất 20 ms, một request mất 2.000 ms. Tính mean. Vì sao chỉ dùng mean có thể khiến nhóm đánh giá sai trải nghiệm?

### Bài 4 — p99 ở ít mẫu

Với 20 samples, p99 gần bằng thống kê nào? Tại sao một endpoint 30 requests/ngày cần cách báo SLO khác endpoint 100.000 requests/phút?

### Bài 5 — Percentiles không cộng gộp

Hai workers có p99 lần lượt 80 và 500 ms, count lần lượt 10.000 và 100. Có thể tính p99 chung bằng trung bình thường hoặc trung bình có trọng số không? Cần dữ liệu gì?

### Bài 6 — Workload mix

Một hệ thống có 70% feed, 15% detail, 10% summary, 5% write. Với offered 200 RPS, mỗi operation được đề nghị bao nhiêu RPS?

### Bài 7 — Offered vs achieved

Generator cố gửi 500 RPS nhưng chỉ hoàn tất thành công 300 RPS và có 10% errors. Bạn cần những thống kê gì để xác định server saturation hay generator bottleneck?

### Bài 8 — Concurrency

Closed-loop có 20 workers, latency trung bình tăng từ 50 lên 200 ms. Throughput xấp xỉ thay đổi thế nào nếu không có think time và overhead đáng kể?

### Bài 9 — Coordinated omission

Giả sử arrival dự kiến mỗi 10 ms, server dừng 1 giây, nhưng closed-loop chỉ có một request đang chờ. Vì sao histogram có thể bỏ sót trải nghiệm của những arrival slots khác?

### Bài 10 — Dataset skew

Production có tenant t001 chiếm 60% traffic, test dataset phân phối đều trên 200 tenants. Benchmark có thể bỏ sót hot spots nào?

### Bài 11 — Seed lab

Chạy seed mục 7 trên MongoDB lab, kiểm tra 12.000 listings và 16 counters. Giải thích cơ chế upsert và tại sao filter có labTag.

### Bài 12 — Kiểm tra phân bố

Chạy aggregation group theo tenantId/city/status. Tỷ lệ active và mức tập trung tenant có giống giả định ban đầu không?

### Bài 13 — Explain Feed

Chạy explain("executionStats") của Query A. Ghi winningPlan, keys examined, docs examined và nReturned. Khi nào nên thử compound index mới?

### Bài 14 — Sort

So feed sort theo createdAt và sort theo rentMillion. Với indexes hiện có, có thể xuất hiện khác biệt nào về sort stage và latency?

### Bài 15 — Point lookup

Chạy Query B với nhiều IDs. Vì sao điểm lookup thường khác chi phí so với Query A, và vì sao p99 lookup không thể thay SLO feed?

### Bài 16 — Aggregation

Chạy Query C và giải thích phần $match/$group. Nếu latency tăng khi chạy đồng thời với feed, cần xem CPU/cache/IO metrics nào?

### Bài 17 — Write concern

So hai write workloads giống nhau nhưng một bên dùng w:1, bên kia w:"majority". Vì sao không thể gán mọi chênh lệch cho index?

### Bài 18 — Benchmark Node.js

Chạy script closed-loop read-only trong lab. Ghi số mẫu theo operation, p50/p95/p99, errors và throughput. Vì sao các số này không là kết quả production?

### Bài 19 — Mixed read/write

Trên lab, bật BENCH362_ALLOW_WRITES=true và so với read-only. Những khác biệt nào về contention, journaling và write rate có thể xuất hiện?

### Bài 20 — Warmup

So lần chạy đầu với cache lạnh và lần chạy sau khi warmup. Tại sao không được so một baseline cold với một after-change warm để kết luận tối ưu?

### Bài 21 — Timeout

Một workload có 10.000 requests, 9.700 success và 300 timeout. Tính error rate. Nếu p99 thành công là 100 ms, có được tuyên bố hệ thống hoàn toàn đạt SLO không?

### Bài 22 — In-flight requests

Đến cuối measurement window còn 50 requests chưa hoàn tất, nhiều request bị treo lâu. Bạn sẽ định nghĩa sample window/drain policy như thế nào để không giấu tail latency?

### Bài 23 — Pool queue

Server query execution khoảng 5 ms nhưng client p99 là 500 ms. Hãy đề xuất cách đo connection pool checkout wait, network và service time.

### Bài 24 — Generator capacity

Load generator CPU 100%, không gửi đủ offered RPS, trong khi MongoDB CPU 35%. Có thể kết luận database còn chịu được tải cao hơn không? Cần thay thí nghiệm thế nào?

### Bài 25 — Deep pagination

So offset skip(100000) với keyset pagination có cùng sort và page size. Những chỉ số nào chứng minh cải thiện? Phải giữ những điều kiện gì như nhau?

### Bài 26 — Read/write trade-off

Một index mới giảm feed p99 từ 300 xuống 220 ms nhưng tăng update p99 từ 180 lên 260 ms. Dựa vào SLO nào để quyết định giữ index?

### Bài 27 — Tính RPS

30 phút steady-state có 360.000 successful operations. Tính throughput thành công trung bình. Nếu load generator dự định 250 RPS, đã đạt offered target chưa?

### Bài 28 — Thống kê theo cửa sổ

Một bài test có 25 phút bình thường và 5 phút disk spike. Tại sao cần cả p99 gộp và time-series p99 mỗi phút? Có được lấy trung bình p99 theo phút làm p99 tổng không?

### Bài 29 — Dashboard

Thiết kế dashboard với offered RPS, success RPS, error rate, p50/p95/p99 theo operation, pool wait, WiredTiger cache, disk latency, CPU và replication lag.

### Bài 30 — SLO pass/fail

Thiết kế tiêu chí PASS cho SearchFeed ở offered 140 RPS, p95 ≤ 150 ms, p99 ≤ 300 ms, error ≤ 0,2%, có warmup và steady-state. Khi nào kết quả phải là INCONCLUSIVE thay vì PASS?

### Bài 31 — Điều tra p99

Ở tải 200 RPS, p50 không đổi nhưng p99 tăng từ 90 lên 800 ms. Hãy sắp xếp các bước kiểm tra: client, pool, slow queries, disk, GC, background jobs, failover.

### Bài 32 — Kế hoạch peak

Production thường 200 RPS nhưng 5 phút cao điểm đạt 650 RPS. Thiết kế ramp/peak/spike test với guardrails để xác định saturation và thời gian hệ thống hồi phục.

### Bài 33 — Báo cáo before/after

Soạn một benchmark report ghi database/driver versions, dataset, indexes, mix, concurrency/arrival rate, warmup, duration, sample counts, histograms, p50/p95/p99, errors, throughput và kết luận có căn cứ.

### Bài 34 — Tổng hợp

Một sản phẩm có 10 triệu listings, nhiều tenants, SearchFeed 65%, Detail 20%, Summary 10%, Write 5%, mục tiêu p99 feed 250 ms ở 500 RPS. Thiết kế toàn bộ quá trình: dữ liệu tổng hợp đại diện, query shapes, indexes, generator open-loop, warmup, scenarios, SLI/SLO, metrics, safe test environment, và cách đưa ra quyết định tối ưu.

## 24. Tài liệu tham khảo

- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/).
- MongoDB Manual — [Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/).
- MongoDB Manual — [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/).
- MongoDB Manual — [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/).
- MongoDB Manual — [currentOp](https://www.mongodb.com/docs/manual/reference/command/currentOp/).
- MongoDB Manual — [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/).
- MongoDB Node.js Driver — [Monitor Commands](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/monitoring/).
- MongoDB Node.js Driver — [Connection Pools](https://www.mongodb.com/docs/drivers/node/current/connect/connection-options/connection-pools/).
- MongoDB Atlas — [Monitor Database Deployment Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/).
- Brendan Gregg — [USE Method: Utilization, Saturation, Errors](https://www.brendangregg.com/usemethod.html).
- Gil Tene — [How NOT to Measure Latency](https://www.youtube.com/watch?v=lJ8ydIuPFeU) (thảo luận về coordinated omission và tail latency).

**Kết luận:** Một bài tối ưu MongoDB chỉ đáng tin nếu **tải thử đại diện cho hành vi production** về dữ liệu, query shape, tỷ lệ read/write, concurrency, phân bố hot/cold và mức arrival rate. **p50** mô tả trải nghiệm điển hình, **p95** cho biết phần đuôi thường xuyên hơn, còn **p99** giúp phát hiện những yêu cầu chậm nhất trong khoảng 1% cuối; nhưng tất cả đều phải đi kèm **sample count, phương pháp percentile, thời gian đo, throughput và error rate**. Dùng **explain** để hiểu truy vấn, **driver/API metrics** để đo trải nghiệm, **server/cache/disk/replication metrics** để tìm bottleneck; tránh **coordinated omission**, việc lấy trung bình các percentiles và những phép so trước/sau không công bằng. Đích đến không phải một biểu đồ đẹp, mà là chứng minh hệ thống **đạt SLO p50/p95/p99 ở đúng offered load, với lỗi được kiểm soát và có khả năng tái lập**.
