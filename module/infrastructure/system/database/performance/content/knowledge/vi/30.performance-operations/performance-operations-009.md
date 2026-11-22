# Hồ sơ điều tra sự cố và thư viện thí nghiệm có thể tái lập

## Vì sao cần lưu hồ sơ điều tra và thí nghiệm có thể chạy lại?

Tối ưu hiệu năng cơ sở dữ liệu thường bắt đầu từ một sự cố cụ thể: API tăng p99, transaction chờ khóa, truy vấn báo cáo spill ra vùng lưu trữ tạm, replica bị lag hoặc storage latency tăng đột biến. Nhóm vận hành thu thập số liệu, xem execution plan, thay đổi tham số rồi quan sát kết quả. Nếu thông tin chỉ nằm trong chat, terminal, dashboard tạm hoặc trí nhớ của người trực, lần điều tra sau có thể phải làm lại từ đầu và dễ lặp lại giả thuyết sai.

Một hồ sơ điều tra sự cố (incident investigation dossier) ghi lại điều gì đã xảy ra, ảnh hưởng đến ai, dữ liệu nào được quan sát, giả thuyết nào đã được kiểm tra, thay đổi nào được thực hiện và bằng chứng nào cho thấy hệ thống đã phục hồi. Hồ sơ tốt giúp người khác hiểu quyết định tại thời điểm đó, phân biệt sự kiện với suy luận và tiếp tục điều tra mà không phải đoán.

Một thư viện thí nghiệm hiệu năng (performance experiment library) lưu các phép thử đã được chuẩn hóa để có thể dựng lại trong môi trường kiểm soát. Mỗi thí nghiệm mô tả phiên bản database, schema, index, dữ liệu, thống kê, cấu hình, workload, công cụ tạo tải, điều kiện chạy, metric và kết quả. Khi các thành phần này được ghi rõ, nhóm có thể so sánh trước/sau, kiểm chứng hồi quy sau nâng cấp và xác định liệu một tối ưu có còn hiệu quả khi dữ liệu hoặc workload thay đổi.

Hai thực hành bổ trợ cho nhau:
- Hồ sơ sự cố trả lời: hệ thống đã gặp vấn đề gì, bằng chứng nào hỗ trợ kết luận và vì sao nhóm chọn cách xử lý đó?
- Thư viện thí nghiệm trả lời: làm thế nào tái tạo điều kiện đã quan sát, kiểm tra giả thuyết và xác nhận thay đổi bằng phép đo lặp lại?

Trong tối ưu hiệu năng cơ sở dữ liệu, hồ sơ và thí nghiệm cần liên kết với query fingerprint, execution plan, thống kê, wait events, workload, transaction behavior, I/O, memory và cấu hình engine. Bài học này hướng dẫn cách thiết kế hồ sơ, lưu bằng chứng có thể kiểm tra, tạo manifest thí nghiệm, quản lý dữ liệu và môi trường, so sánh kết quả công bằng, bảo vệ thông tin nhạy cảm và duy trì tri thức sau sự cố.

## Phân biệt sự kiện, giả thuyết, kết luận và hành động

Một hồ sơ đáng tin phải thể hiện rõ mức độ chắc chắn của từng thông tin. Không ghi một suy đoán thành sự kiện chỉ vì nó phù hợp với hướng xử lý đã chọn.

| Loại thông tin | Ý nghĩa | Ví dụ |
|---|---|---|
| Sự kiện (fact) | Được quan sát trực tiếp hoặc xác nhận bằng nguồn cụ thể | p99 tăng từ 120 ms lên 900 ms trong 10 phút |
| Giả thuyết (hypothesis) | Cách giải thích cần kiểm chứng | Một truy vấn mới gây tăng logical reads |
| Bằng chứng (evidence) | Dữ liệu hỗ trợ hoặc bác bỏ giả thuyết | Query fingerprint X tăng calls và shared reads |
| Kết luận (finding) | Diễn giải dựa trên các bằng chứng đã xem | Truy vấn X đóng góp phần lớn lượng đọc tăng |
| Hành động (action) | Thay đổi đã thực hiện hoặc được giao | Khôi phục index và chạy lại workload |
| Kết quả (outcome) | Điều đo được sau hành động | p99 giảm, reads/call giảm, write latency gần như không đổi |

Một câu như “database chậm do thiếu index” là kết luận quá sớm nếu chưa có plan, actual rows, logical reads và so sánh workload. Hãy ghi giả thuyết “truy vấn có thể đang đọc quá nhiều trang vì thiếu access path phù hợp”, rồi chỉ chuyển thành finding khi có bằng chứng.

Cũng cần ghi giả thuyết bị bác bỏ. Ví dụ, nhóm nghi storage chậm nhưng đo được storage latency ổn định trong khi lock wait tăng. Việc lưu giả thuyết đã bác bỏ giúp người sau tránh điều tra lại cùng hướng mà không có lý do mới.

## Cấu trúc hồ sơ điều tra sự cố

### 1. Thông tin nhận diện

Mỗi hồ sơ cần một mã duy nhất và thông tin đủ để tìm lại:
- Incident ID và tiêu đề ngắn.
- Dịch vụ, module, database/cluster và môi trường.
- Mức độ ảnh hưởng hoặc severity theo quy ước của tổ chức.
- Thời điểm bắt đầu, phát hiện, giảm tác động và kết thúc.
- Người điều phối, nhóm tham gia và người chịu trách nhiệm cập nhật.
- Liên kết đến ticket, deployment, change request hoặc dashboard liên quan.
- Trạng thái hồ sơ: đang điều tra, đã giảm tác động, đã đóng hoặc cần theo dõi.

Không dùng tên người hoặc tên khách hàng làm ID nếu không cần thiết. Mã sự cố nên ổn định, không chứa bí mật và có thể dùng trong metric, log hoặc tài liệu liên quan.

### 2. Tóm tắt ảnh hưởng

Tóm tắt phải giúp người đọc hiểu nhanh phạm vi và mức độ ảnh hưởng:
- API, job hoặc nhóm truy vấn nào bị ảnh hưởng.
- Số lượng request, tenant hoặc người dùng bị tác động nếu đo được.
- p50/p95/p99 trước và trong sự cố.
- Throughput, error rate, timeout và queue depth.
- Ảnh hưởng đến read/write, replication, backup hoặc tác vụ nền.
- Có mất dữ liệu, sai dữ liệu hay chỉ tăng latency.
- SLO/SLA nào bị vi phạm và trong khoảng thời gian nào.

Nếu không có số liệu, ghi rõ “chưa đo được” hoặc “ước lượng” cùng nguồn và phương pháp. Không biến một ước lượng từ người dùng thành con số chính xác.

### 3. Mô tả hệ thống và thay đổi gần thời điểm sự cố

Ghi những thành phần có thể ảnh hưởng đến hiệu năng:
- Database engine, phiên bản, edition và topology.
- Primary/replica, shard, partition hoặc availability group.
- CPU, RAM, storage tier, IOPS/throughput limit và network.
- Connection pool, số session và cấu hình timeout.
- Schema, index, partition, extension và migration gần nhất.
- Ứng dụng, driver, ORM và phiên bản được triển khai.
- Query, batch, ETL, backup, maintenance hoặc tác vụ nền.
- Thay đổi cấu hình, deploy, data growth hoặc traffic pattern.

Phân biệt “đã thay đổi ngay trước sự cố” với “được cho là có liên quan”. Thời điểm gần nhau không chứng minh quan hệ nhân quả. Ghi deployment ID, config revision hoặc migration ID nếu có thể.

### 4. Timeline

Timeline là chuỗi sự kiện theo thời gian, dùng một múi giờ thống nhất, tốt nhất ghi rõ UTC offset. Mỗi dòng nên có timestamp, sự kiện, nguồn và mức độ tin cậy.

| Thời điểm | Sự kiện | Nguồn | Ý nghĩa |
|---|---|---|---|
| 09:02:10 | p99 API bắt đầu tăng | APM dashboard | Dấu hiệu đầu tiên |
| 09:04:30 | Alert timeout vượt ngưỡng | Alert manager | Sự cố được phát hiện |
| 09:07:00 | Query fingerprint Q17 tăng calls | Query statistics | Hướng điều tra |
| 09:12:20 | Lock wait tăng trên bảng orders | DB monitoring | Bằng chứng tranh chấp |
| 09:18:00 | Giảm concurrency batch | Change log | Hành động giảm tác động |
| 09:25:00 | p99 giảm dưới ngưỡng cảnh báo | APM dashboard | Xác nhận tạm thời |

Ví dụ chỉ minh họa định dạng. Trong hồ sơ thật, không ghi thời gian giả định như dữ kiện. Nếu đồng hồ giữa ứng dụng và database lệch nhau, ghi độ lệch đã biết và nguồn timestamp. Không trộn thời gian local và UTC mà không chú thích.

### 5. Bằng chứng và nguồn

Mỗi bằng chứng nên có:
- Evidence ID.
- Thời điểm và khoảng thời gian được thu thập.
- Nguồn: APM, database view, log, execution plan, OS metrics, network telemetry hoặc benchmark.
- Câu hỏi mà bằng chứng dùng để trả lời.
- Phạm vi và giới hạn của dữ liệu.
- Liên kết hoặc vị trí lưu artifact.
- Hash/checksum nếu cần xác nhận file không bị thay đổi.
- Người hoặc hệ thống thu thập.

Ví dụ:
- E01: histogram latency theo endpoint trong 15 phút.
- E02: query statistics delta của fingerprint Q17.
- E03: actual execution plan của truy vấn Q17 trên dataset thử nghiệm.
- E04: wait statistics cho cùng khoảng thời gian.
- E05: CPU và storage latency từ host database.
- E06: deployment/config revision trước và sau thay đổi.

Một ảnh chụp dashboard không thay thế dữ liệu nguồn nếu cần phân tích sâu. Lưu export CSV/JSON hoặc kết quả truy vấn có timestamp và metadata khi chính sách cho phép. Nếu chỉ có screenshot, ghi rõ đó là bằng chứng trực quan và những dữ liệu không thể khôi phục từ ảnh.

## Quy trình điều tra dựa trên giả thuyết

### Bước 1: xác định triệu chứng và phạm vi

Viết triệu chứng theo dạng đo được. Ví dụ:
- p99 của endpoint /orders tăng từ 150 ms lên 1.2 s.
- Write throughput giảm 30%.
- Log flush wait tăng gấp ba.
- Replica replay queue tăng đều.
- Một query fingerprint tăng logical reads/call.
- Connection acquisition p95 vượt 500 ms.

Xác định sự cố ảnh hưởng một query, một workload class, một node hay toàn cluster. Không bắt đầu bằng việc thay đổi index hoặc memory trước khi biết triệu chứng nằm ở đâu.

### Bước 2: thiết lập baseline

Chọn khoảng thời gian trước sự cố có workload tương tự và ghi:
- Query mix và calls/sec.
- Rows/call, logical reads/call, physical reads và bytes.
- CPU time, elapsed time và wait events.
- p50/p95/p99, throughput và error rate.
- Active sessions, pool wait và transaction duration.
- Cache/buffer behavior, memory grant và spill.
- I/O latency, queue depth và log flush.
- Replication lag nếu có.

Baseline phải có ngữ cảnh. Một khoảng ban đêm ít tải không phải baseline phù hợp để so với giờ cao điểm.

### Bước 3: lập giả thuyết có thể kiểm chứng

Mỗi giả thuyết nên nêu:
- Cơ chế gây ra triệu chứng.
- Dấu hiệu dự kiến nếu giả thuyết đúng.
- Dữ liệu cần thu thập.
- Kết quả nào sẽ bác bỏ giả thuyết.
- Thử nghiệm nhỏ nhất có thể phân biệt các khả năng.

| Giả thuyết | Dấu hiệu dự kiến | Bằng chứng cần có |
|---|---|---|
| Query plan regression | Rows/reads hoặc elapsed tăng sau deploy | Plan trước/sau, query stats |
| Lock contention | Lock wait tăng, CPU có thể không cao | Blocking chain, transaction age |
| Storage bottleneck | I/O latency và queue tăng | OS/storage metrics, DB I/O waits |
| Buffer churn | Reads tăng khi workload scan chạy | Buffer stats, query fingerprint |
| Pool exhaustion | Acquisition wait và pending borrowers tăng | Pool metrics, connection usage |
| Replica apply lag | Receive/replay queue tăng | Replication status và node metrics |

Không cần kiểm tra mọi giả thuyết cùng lúc. Ưu tiên giả thuyết giải thích nhiều triệu chứng và có phép đo phân biệt rõ.

### Bước 4: thu thập plan và thống kê đúng cách

Với truy vấn quan trọng, lưu:
- SQL đã normalize hoặc query fingerprint.
- Tham số đại diện và phân bố tham số.
- Estimated execution plan.
- Actual execution plan trong môi trường an toàn.
- Estimated rows và actual rows.
- Logical reads, physical reads, CPU và elapsed.
- Sort/hash spill, memory grant và temp I/O.
- Wait events và blocking liên quan.
- Phiên bản engine, schema/index và statistics timestamp.

Actual plan có thể chứa giá trị tham số hoặc thông tin dữ liệu nhạy cảm. Cần xử lý theo chính sách bảo mật. Với DML, không chạy EXPLAIN ANALYZE hoặc công cụ thực thi tương đương trên production nếu chưa đánh giá side effect.

### Bước 5: thay đổi từng yếu tố

Mỗi lần thử nên thay đổi một yếu tố có thể cô lập:
- Sửa SQL hoặc parameter binding.
- Thêm/bỏ một index trong môi trường thử nghiệm.
- Cập nhật statistics.
- Thay đổi batch size.
- Giới hạn concurrency.
- Điều chỉnh memory grant/workload group.
- Thay đổi pool size hoặc timeout.
- Tách workload báo cáo khỏi OLTP.

Nếu thay nhiều thứ cùng lúc, kết quả có thể tốt hơn nhưng không biết yếu tố nào tạo ra cải thiện hoặc gây tác dụng phụ.

### Bước 6: xác minh sau thay đổi

So sánh trên cùng workload và điều kiện:
- Kết quả nghiệp vụ có chính xác không?
- Throughput có tăng không?
- p95/p99 có giảm không?
- CPU, I/O, memory và temp usage thay đổi thế nào?
- Write latency hoặc workload khác có bị ảnh hưởng không?
- Error, timeout, retry và replication lag có tăng không?
- Kết quả có lặp lại qua nhiều lần chạy không?

Một truy vấn nhanh hơn nhưng làm write latency tăng mạnh do index mới có thể là đánh đổi không chấp nhận được. Hồ sơ cần ghi cả lợi ích và chi phí phụ.

### Bước 7: kết luận và theo dõi

Phân loại kết quả:
- **Confirmed:** bằng chứng trực tiếp hỗ trợ cơ chế và thay đổi đã cải thiện chỉ số mục tiêu.
- **Likely:** bằng chứng phù hợp nhưng còn giới hạn chưa loại trừ.
- **Rejected:** dữ liệu không hỗ trợ giả thuyết.
- **Inconclusive:** phép đo hoặc môi trường chưa đủ để kết luận.

Ghi điều kiện theo dõi sau triển khai, ngưỡng rollback và người chịu trách nhiệm. Đừng tuyên bố root cause confirmed nếu chỉ có tương quan thời gian.

## Thiết kế thư viện thí nghiệm hiệu năng

### Mỗi thí nghiệm phải có mục tiêu và giả thuyết

Một experiment record nên trả lời:
- Câu hỏi cần kiểm tra là gì?
- Giả thuyết và cơ chế dự kiến là gì?
- Biến độc lập nào được thay đổi?
- Những biến nào phải giữ cố định?
- Metric nào quyết định thành công?
- Điều kiện dừng hoặc rollback là gì?
- Ai sở hữu và ai đã xem xét kết quả?

Ví dụ:
- Câu hỏi: composite index có giảm reads cho truy vấn lọc tenant và khoảng thời gian không?
- Giả thuyết: index bắt đầu bằng tenant_id, created_at giúp giảm scan trên workload có selectivity cao.
- Biến độc lập: index có/không.
- Biến kiểm soát: engine version, dataset, statistics, query parameters, concurrency, cache state.
- Metric chính: logical reads/call và p95 latency.
- Guardrail: write throughput, insert latency, index size và CPU.

### Phân biệt experiment, run và artifact

- **Experiment:** định nghĩa câu hỏi, giả thuyết, biến và tiêu chí đánh giá.
- **Run:** một lần thực thi experiment với một cấu hình cụ thể.
- **Artifact:** dữ liệu đầu ra của run như plan, logs, histogram, metrics, result summary.
- **Finding:** kết luận rút ra từ một hoặc nhiều run.
- **Decision:** quyết định áp dụng, không áp dụng hoặc thử tiếp.

Một experiment có thể có nhiều run. Không ghi đè kết quả run cũ khi chạy lại; mỗi run cần ID và timestamp riêng.

### Manifest mô tả môi trường

Manifest giúp tái tạo điều kiện. Có thể lưu YAML với các trường như sau:

~~~yaml
experiment_id: dbperf-index-orders-001
title: Composite index for tenant order history
owner_team: database-performance
created_at: "2026-11-19T09:00:00+07:00"

target:
  engine: PostgreSQL
  engine_version: "16.4"
  topology: single-primary
  driver: "PostgreSQL JDBC"
  driver_version: "42.x"

schema:
  migration_revision: "2026.11.12.3"
  schema_fingerprint: "sha256:..."
  index_state: "baseline-without-candidate-index"

dataset:
  generator_revision: "git:abc1234"
  seed: 84127
  row_counts:
    orders: 20000000
  distribution_profile: "tenant-skew-v2"
  data_fingerprint: "sha256:..."

workload:
  script_revision: "git:def5678"
  query_fingerprint: "orders-by-tenant-date"
  concurrency: 32
  duration_seconds: 900
  warmup_seconds: 180
  model: closed
  parameter_profile: "tenant-size-mix-v3"

measurement:
  metrics:
    - throughput
    - latency_p50
    - latency_p95
    - latency_p99
    - logical_reads
    - cpu_time
    - write_latency
  repetitions: 5

change:
  candidate_index: "orders(tenant_id, created_at DESC)"
  expected_effect: "reduce rows and pages read"

result:
  status: pending
  artifacts_path: "runs/run-2026-11-19-001/"
~~~

Đây là cấu trúc tham khảo. Các trường version, schema fingerprint, dataset generator và workload revision phải phản ánh công cụ thật của dự án. Không điền giá trị giả để làm manifest trông đầy đủ; trường chưa biết cần được đánh dấu unknown hoặc pending.

### Fingerprint của schema và dữ liệu

Chỉ ghi migration revision có thể chưa đủ nếu schema bị thay đổi thủ công. Có thể tạo fingerprint từ metadata schema đã chuẩn hóa: table, column, type, nullability, constraint, index, partition và extension. Cần chuẩn hóa thứ tự trước khi hash để fingerprint ổn định.

Dataset fingerprint có thể dựa trên:
- Generator version và seed.
- Row count theo bảng/partition.
- Phân bố cardinality, skew và NULL.
- Min/max của cột thời gian hoặc khóa.
- Checksum theo chunk hoặc một mẫu có kiểm soát.

Không nhất thiết hash toàn bộ dữ liệu lớn trong mọi run. Có thể lưu fingerprint theo partition/chunk và metadata thống kê. Mục tiêu là phát hiện dataset khác nhau đủ để ảnh hưởng kết quả, không phải tạo chi phí đo lớn hơn thí nghiệm.

## Tái lập dữ liệu và workload

### Dùng generator xác định

Generator dữ liệu nên có version, seed và tham số phân bố. Cùng seed và cùng version phải tạo dữ liệu giống nhau trong phạm vi đã định nghĩa. Nếu generator thay đổi thuật toán, tăng version dù seed giữ nguyên.

Cần mô tả:
- Row count và kích thước dữ liệu.
- Cardinality từng khóa.
- Tỷ lệ NULL và duplicate.
- Phân bố tenant, trạng thái, thời gian và hot key.
- Quan hệ giữa các bảng.
- Data skew và các giá trị ngoại lệ.
- Tỷ lệ insert/update/delete nếu thí nghiệm có ghi.

Dataset đồng đều hoàn toàn có thể làm optimizer chọn plan khác production. Với query theo tenant, cần có tenant nhỏ, trung bình và rất lớn. Với dữ liệu thời gian, cần có vùng nóng và lạnh. Với index, cần phân bố selectivity thực tế.

### Tách fixture correctness và dataset performance

Fixture nhỏ giúp test logic nhanh và xác định kết quả mong đợi. Dataset lớn giúp kiểm tra cardinality, memory, spill, I/O và plan. Không nên dùng một fixture nhỏ để khẳng định hiệu năng ở quy mô production.

Có thể duy trì:
- Bộ fixture nhỏ, deterministic cho correctness.
- Bộ dataset trung bình cho plan regression.
- Bộ dataset lớn hoặc synthetic production-like cho capacity test.
- Bộ dữ liệu anonymized nếu được phép và đã xử lý rủi ro riêng tư.

Mỗi bộ phải có mô tả mục đích, kích thước, phân bố và hạn chế.

### Mô tả workload có thể tái chạy

Workload manifest cần ghi:
- Query mix và tỷ lệ từng query fingerprint.
- Tần suất/arrival rate hoặc concurrency.
- Closed/open model và think time.
- Transaction size và số statement mỗi transaction.
- Connection pool size và timeout.
- Parameter distribution và random seed.
- Fetch size, response size và cách tiêu thụ kết quả.
- Warm-up, ramp-up, steady-state và cooldown.
- Retry policy và request deadline.

Một script chỉ ghi “chạy 100 user trong 10 phút” chưa đủ để tái lập. Cần biết mỗi user làm gì, với dữ liệu nào, khoảng nghỉ bao lâu và công cụ đo latency ở điểm nào.

## Kiểm soát điều kiện đo

### Cache state

Cold-cache và warm-cache là hai điều kiện khác nhau. Ghi rõ:
- Database vừa restart hay đang chạy lâu.
- Buffer pool/shared buffers có được làm nóng không.
- OS page cache có bị xóa hay không.
- Storage cache có được kiểm soát không.
- Warm-up bao lâu và dựa trên tiêu chí nào.

Không xóa cache production để làm benchmark. Nếu cần cold-cache test, dùng môi trường thử nghiệm riêng và ghi cách tạo trạng thái lạnh. Một restart database không nhất thiết xóa OS hoặc storage cache.

### Statistics và plan cache

Optimizer dựa vào statistics, histogram, cardinality và plan cache. Ghi:
- Thời điểm cập nhật statistics.
- Cấu hình sampling hoặc analyze nếu có.
- Parameter sniffing/parameter-sensitive behavior liên quan.
- Prepared statement và plan cache state.
- Plan ID hoặc plan hash nếu engine cung cấp.
- Các cấu hình optimizer quan trọng.

Không chạy một lần sau khi cập nhật statistics rồi so với một lần trước đó mà không ghi sự thay đổi này. Nếu mục tiêu chính là đánh giá index, statistics phải được kiểm soát để tránh nhầm tác động của hai yếu tố.

### Tài nguyên và môi trường

Ghi các yếu tố:
- CPU model, core/vCPU và quota.
- RAM và memory limit của container/VM.
- Storage loại gì, IOPS/throughput limit và latency.
- Filesystem, volume và vị trí log/data/temp.
- Network bandwidth và RTT giữa generator, app và DB.
- OS/kernel hoặc image/container revision.
- Database config và workload/resource group.
- Các workload khác chạy cùng host hoặc cùng storage.

Nếu dùng cloud instance, ghi instance type và storage class thay vì chỉ ghi “máy 8 CPU”. Giới hạn burst credit hoặc throttling có thể làm kết quả thay đổi theo thời gian.

### Tính ổn định của phép đo

Thực hiện warm-up, ramp-up, steady-state và cooldown theo kịch bản. Lặp lại nhiều lần nếu metric biến động. Ghi:
- Thời lượng mỗi phase.
- Số lần lặp.
- Median hoặc phân bố kết quả giữa các run.
- Outlier và lý do loại nếu có.
- Sự kiện nền như backup, checkpoint, vacuum, compaction hoặc deployment.

Không xóa outlier chỉ vì nó làm kết quả xấu. Nếu có lý do loại một run, ghi điều kiện và giữ artifact của run đó để người khác xem lại.

## So sánh trước và sau một thay đổi

### Giữ điều kiện tương đương

Khi so sánh baseline và candidate, cần giữ cố định các yếu tố không phải biến thử nghiệm:
- Cùng engine/version và topology.
- Cùng schema trừ thay đổi đang thử.
- Cùng dataset và seed.
- Cùng statistics state hoặc quy trình cập nhật.
- Cùng query mix, parameters và arrival/concurrency.
- Cùng cache condition.
- Cùng generator capacity và network path.
- Cùng duration và warm-up.

Nếu phải thay đổi nhiều điều kiện, đánh dấu run là không tương đương và không diễn giải chênh lệch như tác động riêng của một thay đổi.

### Chọn metric chính và guardrail

Không chỉ chọn metric giúp candidate trông tốt. Ví dụ với index mới:
- Metric chính: p95 query latency, logical reads/call.
- Guardrail: insert/update latency, write throughput, index size, storage I/O, replication lag.

Với thay đổi connection pool:
- Metric chính: acquisition p95, throughput.
- Guardrail: database sessions, CPU, lock waits, memory và query latency.

Với thay đổi memory:
- Metric chính: spill bytes và elapsed.
- Guardrail: memory pressure, concurrency, temp I/O và latency của workload khác.

### So sánh percentile đúng cách

Không lấy trung bình p95 của các run hoặc các generator để tạo p95 tổng. Hãy gộp histogram hoặc dữ liệu mẫu theo phương pháp hỗ trợ merge rồi tính percentile. Ghi số mẫu và khoảng thời gian.

Khi so sánh nhiều lần chạy, báo cáo median của metric theo run và độ phân tán giữa các run. Với latency tail, cần đủ mẫu để p99 có ý nghĩa. Nếu chỉ có 100 request, p99 gần như phụ thuộc vào một vài mẫu cuối và rất thiếu ổn định.

### Xem cả chi phí phụ

Một index có thể giảm read latency nhưng tăng write amplification. Một materialized view có thể làm dashboard nhanh nhưng tăng chi phí refresh. Tăng parallelism có thể giảm thời gian một truy vấn nhưng làm các truy vấn khác chậm do tranh CPU và memory.

Báo cáo phải thể hiện:
- Lợi ích ở workload mục tiêu.
- Tác động đến workload đọc/ghi khác.
- Chi phí bộ nhớ, lưu trữ và log.
- Độ phức tạp vận hành.
- Tác động đến recovery, replication và backup.
- Điều kiện mà lợi ích không còn đúng.

## Quản lý artifact và khả năng truy xuất

### Cấu trúc thư mục tham khảo

Có thể tổ chức theo incident hoặc experiment:

~~~text
performance-knowledge/
  incidents/
    INC-2026-0142/
      README.md
      timeline.csv
      hypotheses.md
      findings.md
      decisions.md
      evidence/
        E01-latency-histogram.json
        E02-query-stats.csv
        E03-execution-plan.json
      actions/
        change-001.md
  experiments/
    dbperf-index-orders-001/
      experiment.md
      manifest.yaml
      runs/
        run-2026-11-19-001/
          environment.json
          metrics/
          plans/
          logs/
          result.md
        run-2026-11-20-001/
          environment.json
          metrics/
          plans/
          logs/
          result.md
~~~

Đây là cách tổ chức gợi ý. Chọn vị trí lưu phù hợp với repository, hệ thống ticket, object storage hoặc knowledge base của tổ chức. Không sao chép dữ liệu nhạy cảm vào Git chỉ vì muốn tiện quản lý.

### Metadata cho artifact

Mỗi artifact nên có:
- Artifact ID và loại file.
- Incident/experiment/run liên quan.
- Timestamp và timezone.
- Nguồn thu thập và công cụ/version.
- Query fingerprint hoặc plan ID liên quan.
- Khoảng thời gian và đơn vị metric.
- Checksum nếu cần kiểm tra toàn vẹn.
- Mức phân loại dữ liệu và thời hạn lưu.
- Ghi chú về biến đổi hoặc redaction đã áp dụng.

Tên file nên ổn định và dễ tìm. Không dùng tên như final2-new-latest nếu không có version hoặc run ID.

### Version control

Đưa manifest, script workload, SQL, migration fixture và tài liệu vào version control nếu phù hợp. Mỗi run cần trỏ đến commit hoặc revision chính xác. Artifact lớn như database dump, trace hoặc raw metrics có thể lưu ngoài Git, nhưng manifest phải giữ URI/object ID và checksum để truy xuất.

Không ghi đè run cũ. Nếu chạy lại cùng experiment, tạo run ID mới. Nếu sửa script hoặc dataset generator, revision thay đổi và run mới phải tham chiếu revision mới.

### Bảo vệ dữ liệu và bí mật

Execution plan, query text, bind parameters, logs và dump có thể chứa:
- Email, số điện thoại, địa chỉ hoặc dữ liệu khách hàng.
- Token, password hoặc connection string.
- Business identifiers và thông tin giao dịch.
- Schema nội bộ hoặc dữ liệu có thể nhận diện tổ chức.

Trước khi lưu hoặc chia sẻ:
- Loại bỏ secret và credential.
- Redact hoặc tokenize dữ liệu nhạy cảm.
- Chỉ giữ bind values khi thực sự cần và đã được phê duyệt.
- Giới hạn quyền truy cập theo nhóm và mục đích.
- Mã hóa khi truyền và khi lưu nếu chính sách yêu cầu.
- Đặt retention period và quy trình xóa.
- Không đưa production dump vào môi trường cá nhân hoặc repo công khai.
- Ghi rõ dữ liệu đã được anonymize hay synthetic.

Anonymization cần được đánh giá theo khả năng tái nhận diện; thay tên cột hoặc xóa một vài trường chưa chắc đã loại bỏ rủi ro.

## Mẫu hồ sơ điều tra sự cố

Có thể dùng mẫu sau để bắt đầu:

~~~markdown
# Incident: INC-YYYY-NNNN - <short title>

## 1. Summary
- Service/database:
- Environment/topology:
- Severity:
- Start/detected/mitigated/resolved:
- Customer or workload impact:
- SLO affected:

## 2. Symptoms and baseline
- p50/p95/p99:
- Throughput:
- Error/timeout rate:
- CPU / memory / I/O:
- Active sessions / pool wait:
- Replication lag:

## 3. Timeline
| Time with timezone | Event | Source | Confidence |

## 4. Recent changes
- Application/deployment:
- Schema/migration/index:
- Database configuration:
- Workload/data changes:

## 5. Hypotheses
| ID | Hypothesis | Expected evidence | Status |

## 6. Evidence
| ID | Artifact | Time window | Source | Limitation |

## 7. Findings
- Confirmed:
- Likely:
- Rejected:
- Inconclusive:

## 8. Actions
| Action | Owner | Change ID | Risk/rollback | Result |

## 9. Verification
- Workload used:
- Before/after metrics:
- Guardrails:
- Observation window:

## 10. Follow-up
- Prevention:
- Monitoring:
- Runbook:
- Owner and due date:
~~~

Mẫu này cần được điều chỉnh theo quy trình incident của tổ chức. Không điền các mục không áp dụng bằng suy đoán; ghi N/A hoặc chưa xác định và giải thích khi cần.

## Mẫu báo cáo một thí nghiệm

Một result record nên có:
- Experiment ID và Run ID.
- Câu hỏi, giả thuyết và biến được thay đổi.
- Commit/revision của script, schema và generator.
- Engine/version, driver, topology và config fingerprint.
- Dataset fingerprint, row count và distribution.
- Workload model, query mix, parameters và concurrency.
- Warm-up/steady-state duration và repetitions.
- Metric chính, guardrail và lỗi.
- Artifact links/checksums.
- Kết luận, giới hạn và quyết định tiếp theo.

Ví dụ bảng kết quả:

| Metric | Baseline median | Candidate median | Thay đổi | Guardrail |
|---|---:|---:|---:|---|
| Query p95 | 420 ms | 180 ms | -57,1% | Đạt |
| Logical reads/call | 18.000 | 4.200 | -76,7% | Đạt |
| Insert p95 | 12 ms | 17 ms | +41,7% | Cần đánh giá |
| Index size | 0 GB | 6,4 GB | Tăng | Trong giới hạn |

Số liệu chỉ minh họa cách trình bày, không phải kết quả của một phép đo thực tế. Nếu insert p95 tăng, không thể chỉ kết luận candidate tốt vì query p95 giảm. Cần đánh giá trade-off theo SLO và tỷ lệ đọc/ghi.

## Biến thí nghiệm thành tri thức dùng lại

### Tạo thư viện theo vấn đề và cơ chế

Có thể phân loại thí nghiệm theo nhóm:
- Access path và index design.
- SQL rewrite và cardinality estimation.
- Join, sort và aggregation.
- Pagination và query search.
- Transaction, lock và concurrency.
- Write path, WAL và group commit.
- Buffer/cache và memory grant.
- I/O, checkpoint và storage.
- Connection pool, network và driver.
- Replication lag và read routing.
- Load generator và workload model.

Mỗi thí nghiệm nên có tags cho engine, version, workload type, data scale, symptom và mechanism. Tag giúp tìm các phép thử tương tự nhưng không thay thế manifest chi tiết.

### Tái sử dụng có kiểm soát

Khi áp dụng một thí nghiệm cũ cho môi trường mới, kiểm tra:
- Engine/version có giống không?
- Schema và index có tương đương không?
- Data distribution và cardinality có tương tự không?
- Workload mix và concurrency có giống không?
- Storage, memory và topology có thay đổi không?
- Metric và tiêu chí thành công có còn phù hợp không?

Một kết quả cũ là bằng chứng trong điều kiện cũ, không phải định luật cho mọi hệ thống. Nếu khác điều kiện quan trọng, chạy lại experiment thay vì sao chép kết luận.

### Đánh giá độ tin cậy của tri thức

Mỗi finding nên có mức độ:
- **High confidence:** phép đo lặp lại, điều kiện được kiểm soát, nhiều nguồn bằng chứng nhất quán.
- **Medium confidence:** kết quả phù hợp nhưng còn một số biến chưa kiểm soát.
- **Low confidence:** dữ liệu ít, chỉ một lần chạy hoặc có yếu tố gây nhiễu đáng kể.

Ghi ngày xác minh gần nhất và engine version. Kết luận về optimizer hoặc một tham số cấu hình có thể hết hiệu lực sau nâng cấp. Thư viện cần cơ chế review hoặc đánh dấu stale khi môi trường thay đổi.

## Ví dụ: điều tra query regression và lưu thành experiment

Một endpoint tìm lịch sử đơn hàng tăng p95 từ 180 ms lên 700 ms sau một lần phát hành. Hồ sơ điều tra ghi:
- Query fingerprint không đổi nhưng số calls tăng nhẹ.
- Logical reads/call tăng từ 3.000 lên 22.000.
- Actual plan đổi từ index seek/range scan sang scan rộng.
- Estimated rows thấp hơn actual rows nhiều lần.
- Statistics trên cột trạng thái đã cũ.
- CPU database tăng, storage latency không thay đổi rõ.

Giả thuyết là sai lệch cardinality khiến optimizer chọn access path kém. Nhóm dựng lại schema và dataset có phân bố trạng thái tương tự trong container/instance thử nghiệm, chạy migration và tạo statistics theo cùng quy trình. Sau đó nhóm thực hiện các run:
1. Baseline với statistics hiện tại.
2. Candidate sau khi cập nhật statistics.
3. Candidate với index thay đổi nếu plan vẫn không phù hợp.
4. Lặp lại từng run với cùng query mix và tham số.

Kết quả cho thấy cập nhật statistics làm plan ổn định và logical reads giảm. Index mới chỉ cải thiện thêm một phần nhưng làm insert p95 tăng. Nhóm quyết định giữ thay đổi statistics, chưa áp dụng index mới và đặt alert cho cardinality/reads regression.

Hồ sơ sự cố lưu timeline, query plan, query stats, deployment ID và quyết định. Thư viện experiment lưu manifest, dataset generator revision, script workload, các run và artifacts. Khi engine được nâng cấp, nhóm có thể chạy lại experiment để xem optimizer có còn chọn plan phù hợp hay không.

Ví dụ này minh họa cách nối điều tra với thí nghiệm. Kết quả phải dựa trên số liệu thật của hệ thống; không sao chép kết luận hoặc ngưỡng từ ví dụ.

## Những sai lầm thường gặp

- **Chỉ ghi kết luận, không lưu bằng chứng:** người sau không thể kiểm tra vì sao nhóm tin vào kết luận.
- **Gộp sự kiện và giả thuyết:** suy luận ban đầu có thể bị coi nhầm là nguyên nhân đã xác nhận.
- **Không lưu giả thuyết bị bác bỏ:** nhóm khác dễ lặp lại cùng phép thử.
- **Thiếu timeline và timezone:** khó ghép application log, database metric và deployment.
- **Không lưu query fingerprint hoặc plan:** khó xác định truy vấn nào thay đổi.
- **Chỉ ghi database version:** bỏ qua driver, schema, index, statistics và config.
- **Dùng dataset không có skew:** benchmark có thể chọn plan khác production.
- **Không ghi cache state:** so sánh cold-cache với warm-cache gây kết luận sai.
- **Thay nhiều biến cùng lúc:** không biết thay đổi nào tạo ra hiệu quả.
- **Chỉ đo metric mục tiêu:** bỏ qua write latency, storage, memory hoặc workload khác.
- **Lấy trung bình các percentile:** p95 của nhiều run/generator không thể gộp bằng phép trung bình đơn giản.
- **Ghi đè artifact cũ:** mất khả năng truy vết lịch sử.
- **Không version hóa workload script:** không thể biết chính xác request mix đã chạy.
- **Đưa dữ liệu production nhạy cảm vào thư viện:** tạo rủi ro riêng tư và bảo mật.
- **Coi kết quả cũ luôn đúng:** engine, schema và workload có thể đã thay đổi.
- **Đóng incident khi chỉ số chính giảm:** cần xác minh guardrail, workload khác và cửa sổ ổn định.

## Checklist hồ sơ sự cố và thư viện thí nghiệm

- [ ] Có Incident ID/Experiment ID/Run ID duy nhất.
- [ ] Ghi service, database, engine/version, topology và thời gian có timezone.
- [ ] Ghi impact, SLO, p50/p95/p99, throughput và error/timeout.
- [ ] Có timeline gắn với nguồn và mức độ tin cậy.
- [ ] Phân biệt facts, hypotheses, evidence, findings và actions.
- [ ] Lưu query fingerprint, plan, statistics và wait metrics liên quan.
- [ ] Ghi deployment, migration, config và workload changes.
- [ ] Manifest có engine, driver, schema, dataset, workload và tool versions.
- [ ] Dataset có seed, generator revision, row count và distribution profile.
- [ ] Ghi cache state, statistics state, warm-up và repetitions.
- [ ] Mỗi run có artifacts riêng và không bị ghi đè.
- [ ] So sánh baseline/candidate trên điều kiện tương đương.
- [ ] Có metric chính và guardrail cho workload khác.
- [ ] Gộp histogram/percentile đúng cách và lưu số mẫu.
- [ ] Ghi giới hạn, mức độ tin cậy và ngày xác minh.
- [ ] Redact secret, bảo vệ dữ liệu nhạy cảm và đặt retention.
- [ ] Có owner, follow-up, rollback condition và lịch review.

## Kết luận

Hồ sơ điều tra sự cố giúp biến một lần xử lý khẩn cấp thành tri thức có thể kiểm tra; thư viện thí nghiệm giúp biến giả thuyết tối ưu thành phép đo có thể chạy lại. Khi ghi rõ timeline, facts, hypotheses, evidence, query fingerprint, execution plan, cấu hình, dữ liệu và workload, nhóm có thể phân biệt nguyên nhân thật với tương quan và tái tạo điều kiện đã tạo ra kết quả.

Hãy version hóa manifest, script, schema fixture và generator; giữ artifact theo từng run; kiểm soát cache, statistics, concurrency và tài nguyên; so sánh metric chính cùng guardrail; đồng thời bảo vệ dữ liệu nhạy cảm. Một kết luận chỉ nên được tái sử dụng khi điều kiện hiện tại còn tương đương và mức độ tin cậy được ghi rõ. Nhờ đó, mỗi sự cố và thí nghiệm góp phần làm cho quyết định tối ưu cơ sở dữ liệu nhanh hơn, có căn cứ hơn và dễ kiểm chứng hơn trong những lần vận hành tiếp theo.
