# Đặt ngưỡng chấp nhận chức năng, hiệu năng và vận hành trong CI

## 1. Vì sao cần ngưỡng chấp nhận khi nâng Java?

Trong **Java Advance Compatibility Migration**, một bản build biên dịch thành công trên JDK mới chưa chứng minh sản phẩm sẵn sàng phát hành. Migration có thể giữ đúng kiểu dữ liệu và API công khai nhưng làm thay đổi hành vi serialization, cách xử lý timezone, thứ tự thực thi đồng thời, latency khi tải cao, mức dùng native memory hoặc tốc độ khởi động container.

Để phát hành có kiểm soát, nhóm cần chuyển câu hỏi mơ hồ **“JDK mới có ổn không?”** thành những điều kiện xác định:

- **Chức năng (functional correctness):** hành vi nào bắt buộc giữ nguyên, hành vi nào được phép thay đổi theo hợp đồng đã công bố?
- **Hiệu năng (performance):** throughput, latency, allocation, CPU, GC và startup được phép chênh lệch đến mức nào so với baseline?
- **Vận hành (operational readiness):** ứng dụng có khởi động, duy trì sức khỏe, tôn trọng resource limits, xử lý sự cố, shutdown và quan sát được trên hạ tầng mục tiêu hay không?
- **Độ tin cậy của bằng chứng:** dữ liệu CI có đủ điều kiện môi trường, số mẫu, độ ổn định và tính tái lập để kết luận không?
- **Quyết định phát hành:** vi phạm nào chặn merge/release, vi phạm nào cảnh báo, và khi nào phải điều tra hoặc phê duyệt ngoại lệ?

**Ngưỡng chấp nhận** (acceptance threshold) là ranh giới được định nghĩa *trước khi đánh giá kết quả* để quyết định PASS, FAIL, INCONCLUSIVE hoặc cần phê duyệt. Nó khác với việc chạy test rồi chọn một con số sao cho kết quả hiện tại vừa đủ qua.

Trong bài này, **CI gate** là bước tự động kiểm tra một hay nhiều điều kiện. Không phải mọi loại tiêu chí đều có thể được đo tốt bằng một job ngắn trong CI: ví dụ memory leak cần soak test, còn hành vi canary dưới traffic thật cần theo dõi sau deployment. Vì vậy, thiết kế tốt chia gate theo giai đoạn, nhưng vẫn có tiêu chí, owner và bằng chứng rõ ràng.

Mục tiêu học tập:

1. Thiết lập tiêu chí pass/fail cho ba nhóm chức năng, hiệu năng và vận hành.
2. Chọn baseline đúng để so sánh trước/sau migration JDK.
3. Viết ngưỡng theo đơn vị, chiều đo, dữ liệu và quy tắc xử lý nhiễu.
4. Tránh kết luận giả từ benchmark không tương đương môi trường.
5. Tổ chức pipeline gồm correctness gates, performance gates, runtime smoke tests và kiểm chứng triển khai.
6. Xử lý flaky tests, thiếu dữ liệu, variance, kết quả sát ngưỡng và ngoại lệ.
7. Ghi evidence để quyết định phát hành, canary hoặc rollback có thể giải thích và kiểm toán.

## 2. Phân biệt test assertion, quality gate, SLO và error budget

Những khái niệm sau thường bị trộn lẫn:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Test assertion** | Một test case có cho kết quả đúng không? | API trả HTTP 400 cho payload sai. |
| **Functional acceptance criterion** | Tập hợp hợp đồng nào bắt buộc giữ nguyên? | Không mất dữ liệu, không có breaking change ngoài phạm vi. |
| **Quality gate** | Pipeline có được chuyển bước hoặc cho phát hành không? | 100% critical contract tests phải PASS. |
| **Performance regression budget** | Chênh lệch với baseline bao nhiêu là chấp nhận được? | p95 latency không tăng quá mức đã duyệt dưới tải cố định. |
| **Absolute performance limit** | Kết quả có vượt mức tối đa/tối thiểu bất kể baseline không? | p99 dưới trần latency yêu cầu. |
| **Operational readiness criterion** | Artifact có vận hành an toàn trên runtime đích không? | Không OOMKilled trong bài test đã định nghĩa; SIGTERM được xử lý. |
| **SLO** | Mức chất lượng dịch vụ mục tiêu trong cửa sổ vận hành? | 99,9% request hợp lệ thành công trong 30 ngày, theo định nghĩa SLI. |
| **Error budget** | Có bao nhiêu phần chất lượng được phép tiêu thụ trong cửa sổ SLO? | Mức downtime/error còn lại theo SLO. |

CI quality gate có thể sử dụng một số ngưỡng lấy từ SLO, nhưng **benchmark 5 phút không chứng minh SLO 30 ngày**. Ngược lại, ứng dụng vượt regression budget so với baseline vẫn có thể đang dưới trần SLO; cần chính sách quyết định rõ có cho phép regression hay không.

### 2.1. Ba kiểu điều kiện nên xuất hiện cùng nhau

Với một metric hiệu năng, thường cần:

1. **Giới hạn tuyệt đối (absolute guardrail):** không vượt trần hoặc xuống dưới sàn.
2. **Ngân sách hồi quy (relative/absolute delta):** không kém baseline quá mức cho phép.
3. **Điều kiện bằng chứng (evidence validity):** số mẫu, môi trường, test duration, variance và độ bao phủ hợp lệ.

Ví dụ latency của phiên bản mới bằng 180 ms so với 100 ms là regression 80%. Dù SLO cho phép dưới 500 ms, nhóm có thể vẫn quyết định **FAIL** vì regression quá lớn. Ngược lại, baseline đã ở 480 ms và candidate lên 490 ms dù delta nhỏ, vẫn có thể vượt ngưỡng an toàn được định nghĩa cho khả năng tăng tải.

### 2.2. Chính sách phải phân biệt trạng thái

Một gate không nên chỉ trả boolean từ mọi tình huống. Trạng thái khuyến nghị:

~~~text
PASS         Đủ bằng chứng và tất cả điều kiện bắt buộc thỏa.
FAIL         Có vi phạm đã xác định hoặc lỗi thực sự.
INCONCLUSIVE Chưa đủ bằng chứng/độ ổn định để kết luận.
WAIVED       Có ngoại lệ được phê duyệt đúng phạm vi và thời hạn.
~~~

Trong một pipeline bắt buộc, FAIL và INCONCLUSIVE thường đều **không được tự động phát hành**. Nhưng ghi hai trạng thái khác nhau giúp tránh nhầm test infrastructure gặp sự cố với một regression của ứng dụng.

## 3. Đặt baseline trước khi chọn ngưỡng

**Baseline** là kết quả tham chiếu có nguồn gốc rõ ràng để đánh giá candidate. Một baseline không đáng tin cậy làm mọi phép so sánh phía sau kém giá trị.

### 3.1. Baseline có thể là gì?

- Bản phát hành đang vận hành ổn định trên JDK cũ.
- Cùng source commit được build và chạy trên hai JDK khác nhau để tách ảnh hưởng JDK.
- Benchmark kết quả được duyệt từ nhánh release.
- Tập golden outputs và contract fixtures cho chức năng.
- Ngưỡng độc lập lấy từ SLO/product requirements khi không có phiên bản trước.

Không nên tự dùng “kết quả run cuối cùng trên CI” làm baseline động nếu run đó có thể đã chứa regression. Một baseline được duyệt nên có version, ngày tạo, người/chính sách phê duyệt và mô tả môi trường.

### 3.2. Hai phép so sánh khác nhau

Trong migration, cần phân biệt:

**So sánh JDK thuần:**

~~~text
Cùng source code và dependency đã khóa
    ├── Run trên JDK baseline
    └── Run trên JDK mục tiêu
~~~

Phép đo giúp thấy khác biệt runtime/JIT/GC/implementation nếu harness và môi trường giữ tương đương.

**So sánh thay đổi sản phẩm:**

~~~text
Release baseline: source + JDK cũ + dependency cũ
Release candidate: source mới + JDK mới + dependency mới
~~~

Phép đo này phản ánh tác động tổng thể với consumer nhưng **không thể quy toàn bộ thay đổi cho JDK**.

Nếu cần phân tích root cause, có thể thiết kế ma trận 2 × 2 khi build/runtime compatibility cho phép:

| Source / runtime | JDK cũ | JDK mới |
|---|---|---|
| Code baseline | A | B |
| Code candidate | C | D |

A→B gợi ý ảnh hưởng JDK với code baseline; A→C gợi ý thay đổi code trên JDK cũ; B→D gợi ý thay đổi code khi đã trên JDK mới; A→D là tác động tổng hợp. Không phải mọi tổ hợp đều biên dịch/chạy được, đặc biệt khi dependency đã nâng Java minimum; khi đó phải ghi giới hạn thay vì suy diễn.

### 3.3. Metadata phải đi cùng baseline

Một baseline hiệu năng tối thiểu nên mô tả:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Artifact | Commit, dependency lock/BOM, checksum hoặc image digest. |
| JDK | Vendor, major, update/build, JVM implementation và flags. |
| OS/hardware | CPU model/architecture, vCPU, memory, kernel, container image. |
| Runtime constraints | CPU quota/cpuset, memory limit, cgroups mode. |
| Benchmark tool | Tool/version, scenario, harness, warmup và measurement. |
| Workload | Dataset size, request mix, concurrency, throughput target. |
| External dependencies | DB/cache versions, network conditions, isolation strategy. |
| Results | Raw sample data, summary metrics, variance và logs. |
| Ownership | Owner, ngày duyệt, expiry/re-baseline policy. |

Một p95 đo trên laptop và một p95 đo trên shared cloud runner không phải hai điểm có thể so sánh chính xác chỉ vì tên test giống nhau.

## 4. Xác định phạm vi chức năng cần bảo vệ

Functional gate phải bắt đầu từ **hợp đồng sản phẩm**, không bắt đầu từ tỷ lệ test coverage.

Các nhóm hợp đồng quan trọng khi nâng JDK:

- Public Java API và binary compatibility cho thư viện.
- HTTP/gRPC/message wire contract: field names, status codes, schemas.
- Persistence: dữ liệu, transaction, isolation, migration schema và rollback.
- Serialization: JSON, XML, Java serialization, protobuf, date/time và charset.
- Authorization/security: không làm mất các kiểm tra bắt buộc.
- Concurrency: ordering, atomicity, race conditions và deadlocks.
- TLS/crypto: certificate validation, provider và thuật toán được hỗ trợ.
- Timezone/locale/Unicode và số học có quy tắc làm tròn.
- Startup/configuration, plugin discovery, reflection và modularity khi ứng dụng dựa vào chúng.
- API/CLI của consumer khi library/module được cập nhật.

Chỉ chọn các tiêu chí thật sự thuộc contract của sản phẩm. Một migration có thể chủ động thay hành vi cũ vì lý do bảo mật hoặc thay public API trong major release; những khác biệt được duyệt phải được mô tả và test theo hợp đồng **mới**, không bị lén xem như “regression được phép” không tài liệu.

### 4.1. Mẫu tiêu chí chức năng

| ID | Hợp đồng | Ngưỡng | Mức |
|---|---|---|---|
| F-01 | Critical business journeys | 100% cases bắt buộc PASS trên JDK mục tiêu. | Blocker |
| F-02 | Public API/ABI không phá hợp đồng đã cam kết | 0 breaking changes không được phê duyệt. | Blocker |
| F-03 | Authorization và dữ liệu giữa tenant | 0 kết quả vi phạm trong tập test bảo mật bắt buộc. | Blocker |
| F-04 | Database transaction rollback | 100% failure-path assertions PASS. | Blocker |
| F-05 | Serialization/wire golden fixtures | Kết quả theo tolerance/normalization đã định nghĩa. | Blocker hoặc có versioning |
| F-06 | Secondary UI rendering | Không có regression severity đã định nghĩa; một số cosmetic changes có thể chấp thuận. | Theo severity |

Đây là ngưỡng minh họa cho một hệ thống, không phải tiêu chuẩn chung bắt mọi dự án áp dụng. Khi viết F-01, phải có danh sách test ID, expected behavior, JDK matrix, dữ liệu và điều kiện PASS cụ thể.

### 4.2. Tại sao “100% test pass” vẫn chưa đủ?

Nếu một nhóm nghiệp vụ không có test, 100% của những test hiện có vẫn có thể bỏ sót. Do đó functional gate nên kiểm tra:

1. Test suites bắt buộc đã thực thi.
2. Số test bị skip/disabled có nằm trong policy?
3. Test discovery có tìm đủ các test được yêu cầu?
4. Kết quả không bị che bởi retry hoặc ignoreFailures.
5. Contract fixtures, consumer tests hoặc end-to-end flows trọng yếu có mặt.
6. Test chạy trên **JDK/runtime thực** được công bố, không chỉ Java compiler toolchain.

Coverage có thể là tín hiệu hỗ trợ nhưng không phải bằng chứng duy nhất rằng toàn bộ hợp đồng được kiểm thử.

## 5. Functional gates theo mức độ rủi ro

Một mô hình hữu ích là chia severity:

| Mức | Ví dụ | Gate đề xuất |
|---|---|---|
| Critical | Mất dữ liệu, lộ quyền, sai tiền, bypass authentication. | FAIL ngay; không tự waive thông thường. |
| High | Breaking public API không được công bố, transaction sai, crash trên runtime hỗ trợ. | FAIL merge/release. |
| Medium | Hành vi phụ trợ khác, có workaround và phạm vi ảnh hưởng giới hạn. | FAIL hoặc yêu cầu phê duyệt có thời hạn theo policy. |
| Low | Cosmetic differences, log order không thuộc contract. | Warning/triage; không tự thay golden output để bỏ qua. |

Severity phải do product/engineering/security owners thống nhất, không được developer tự hạ mức sau khi thấy test fail.

### 5.1. Contract tests và golden files

Ví dụ API nhận JSON:

~~~json
{
  "customerId": "c-102",
  "balance": "128.50",
  "createdAt": "2026-01-15T09:30:00Z"
}
~~~

Nếu contract quy định balance là decimal string có đúng hai chữ số thập phân và createdAt là UTC ISO-8601, test cần kiểm tra những đặc điểm đó. Không nên so sánh toàn bộ JSON như chuỗi raw khi thứ tự object fields không thuộc hợp đồng; làm vậy dễ tạo false failure.

Ngược lại, nếu API thật sự yêu cầu key ordering hoặc byte-for-byte signature, normalization làm mất thông tin sẽ che regression.

Một nguyên tắc:

> Chuẩn hóa những khác biệt không có ý nghĩa theo contract, nhưng tuyệt đối không chuẩn hóa đi chính nội dung mà hợp đồng bảo vệ.

### 5.2. Kiểm thử sai số số học

Không phải mọi kết quả floating point có thể yêu cầu bitwise equality trên các thư viện/JDK/thuật toán đã thay đổi. Tùy miền nghiệp vụ:

- Tiền tệ dùng decimal và rounding policy rõ ràng.
- Số đo có tolerance tuyệt đối/tương đối hợp lý.
- Invariants phải luôn đúng ngay cả khi giá trị vi mô dao động.
- NaN, Infinity, signed zero và overflow cần policy riêng nếu ảnh hưởng contract.

Tolerance phải được xác định trước từ đặc tính miền dữ liệu; không tăng epsilon chỉ để giúp một regression “qua” CI.

## 6. Chọn chỉ số hiệu năng đúng cho workload

Hiệu năng là đa chiều. Chỉ dùng throughput hoặc chỉ dùng thời gian test tổng có thể đánh lừa.

| Metric | Đơn vị ví dụ | Chiều mong muốn | Cần phân tích thêm |
|---|---|---|---|
| Throughput | requests/s, jobs/min | Càng cao càng tốt | Load mix, concurrency, lỗi. |
| p50 latency | ms | Càng thấp càng tốt | Median trải nghiệm, không phản ánh tail. |
| p95 latency | ms | Càng thấp càng tốt | Tail latency đủ mẫu. |
| p99 latency | ms | Càng thấp càng tốt | Nhạy với nhiễu/số mẫu, cần volume. |
| Startup time | s | Càng thấp càng tốt | Cold/warm start, image pull, readiness. |
| Allocation rate | MiB/s hoặc bytes/op | Tùy policy; thường thấp hơn tốt hơn | Workload, GC, escaping objects. |
| GC pause p99 | ms | Càng thấp càng tốt | Collector, số pauses, CPU quota. |
| GC CPU overhead | % CPU/time | Thường thấp hơn tốt hơn | Throughput trade-off. |
| Process/container memory | MiB | Cần nằm trong budget | RSS, cgroup usage, native memory. |
| CPU utilization | core-seconds/req | Không luôn “càng thấp càng tốt” | Giữ cùng throughput/latency. |
| Error/timeout rate | % | Càng thấp càng tốt | Không cho phép đổi nhanh hơn nhưng sai. |

**CPU usage 100% không tự là regression** nếu workload cố ý bão hòa CPU để đo throughput; CPU usage 20% cũng không chứng minh tốt nếu thread bị blocked và throughput thấp. Cần diễn giải metric theo loại test.

### 6.1. Phân loại workload

Nên có các kịch bản riêng:

1. **Microbenchmark:** một thuật toán hoặc API nội bộ được đo bằng công cụ phù hợp như JMH.
2. **Component benchmark:** database mapper, JSON serializer, HTTP client, crypto/compression.
3. **Service load test:** endpoints và real dependency mix dưới concurrency xác định.
4. **End-to-end:** luồng nghiệp vụ đi qua nhiều service.
5. **Startup/cold start:** thời gian từ process start đến trạng thái phục vụ.
6. **Soak/stress:** memory growth, concurrency, GC và ổn định theo thời gian.

Không dùng microbenchmark để kết luận toàn bộ service đã đạt SLO. Ngược lại, service p99 ổn không bảo đảm một hàm compute quan trọng không chậm hơn nhiều nếu traffic hiện tại không kích hoạt nó.

## 7. Thiết kế performance budget định lượng

Có hai loại ranh giới:

**Absolute guardrail**, ví dụ:

~~~text
p95 latency <= 250 ms
error_rate <= 0.1%
startup_time <= 40 s
~~~

**Regression budget**, ví dụ:

~~~text
p95 latency candidate không tăng quá 10% so với baseline
throughput candidate không giảm quá 8% so với baseline
~~~

Các con số trong bài là **dữ liệu minh họa** để giải thích cách thiết kế gate; không phải thresholds được áp dụng sẵn cho một sản phẩm.

### 7.1. Công thức delta tương đối

Với metric “càng thấp càng tốt”:

~~~text
regression_pct = (candidate - baseline) / baseline × 100%
~~~

Với metric “càng cao càng tốt”:

~~~text
regression_pct = (baseline - candidate) / baseline × 100%
~~~

Trong cả hai công thức, giá trị dương biểu diễn xấu đi. Cần baseline dương và cách xử lý trường hợp baseline bằng 0 hoặc gần 0.

Ví dụ p95 latency:

~~~text
baseline  = 100 ms
candidate = 112 ms
regression_pct = (112 - 100) / 100 × 100% = 12%
~~~

Nếu policy cho phép tối đa 10% regression thì FAIL.

Ví dụ throughput:

~~~text
baseline  = 2,000 requests/s
candidate = 1,860 requests/s
regression_pct = (2000 - 1860) / 2000 × 100% = 7%
~~~

Nếu budget tối đa 8% và các guardrails khác PASS, metric này có thể PASS.

### 7.2. Kết hợp ngưỡng tương đối và tuyệt đối nhỏ

Nếu baseline của một metric chỉ 0,2 ms, một chênh lệch 0,05 ms đã là 25% và có thể chỉ là nhiễu của harness. Một chiến lược có thể là:

~~~text
allowed_worsening = max(relative_budget × baseline,
                        absolute_noise_allowance)
~~~

Ví dụ với p95:

~~~text
relative_budget       = 10%
absolute_noise_allowance = 5 ms
baseline              = 100 ms
allowed_worsening     = max(10 ms, 5 ms) = 10 ms
regression boundary   = 110 ms
~~~

Chính sách này cho phép vượt một trong hai ngưỡng tùy cách xác định, nên phải được phê duyệt trước. Với những metric có yêu cầu rất chặt, có thể muốn dùng phép AND hoặc một hard ceiling riêng; không chọn toán tử tùy tiện sau khi xem kết quả.

Ví dụ:

~~~text
PASS if:
  candidate <= baseline + allowed_worsening
  AND candidate <= absolute_ceiling
  AND measurement_quality == VALID
~~~

Đây là quy tắc rõ nghĩa cho metric “lower is better”; với throughput phải đảo chiều.

### 7.3. Trường hợp baseline bằng 0

Với error count baseline = 0, phép tính phần trăm regression không có nghĩa. Hãy dùng absolute criteria:

- Critical security violation count = 0.
- Unhandled error count = 0 trong tập scenario bắt buộc, theo policy.
- Error rate <= trần phù hợp với volume mẫu.
- Restart/OOMKilled count = 0 trong test ổn định có xác định duration.

Một kết quả “0 errors trên 10 requests” không chứng minh error rate production cực nhỏ; cần cửa sổ đo và volume phù hợp.

## 8. Ví dụ bộ tiêu chí hiệu năng cho một API

Giả sử một service xử lý thanh toán nội bộ với bộ tải cố định, số đo minh họa:

| Metric | Baseline | Candidate | Gate minh họa | Kết quả |
|---|---:|---:|---|---|
| p95 latency | 180 ms | 189 ms | Tăng tối đa 10%; trần 250 ms | PASS |
| p99 latency | 310 ms | 365 ms | Tăng tối đa 12%; trần 400 ms | FAIL theo delta |
| Throughput | 2.000 req/s | 1.940 req/s | Giảm tối đa 8%; sàn 1.700 req/s | PASS |
| Error rate | 0,02% | 0,03% | Trần 0,10% và đủ mẫu | PASS |
| Startup to ready | 24 s | 27 s | Tăng tối đa 20%; trần 35 s | PASS |
| Peak container memory | 1.200 MiB | 1.500 MiB | Trần 1.600 MiB; regression budget tùy policy | Cần kiểm tra delta |

Kết luận cho bộ tiêu chí này là **không đủ điều kiện PASS toàn bộ performance gate** vì p99 tăng hơn mức cho phép, dù vẫn dưới trần tuyệt đối 400 ms. Không được lờ p99 chỉ vì throughput vẫn tốt.

### 8.1. Một metric không tự đại diện toàn bộ chất lượng

Ví dụ candidate có throughput tăng 20% nhưng tỷ lệ lỗi tăng từ 0% lên 2%, đó không phải cải thiện có thể chấp nhận nếu chất lượng response bị giảm.

Hoặc latency giảm nhưng CPU core-seconds/request tăng gấp đôi, có thể gây tăng chi phí và throttling khi triển khai trên cùng resource limit. Nên tách hiệu năng người dùng và hiệu quả tài nguyên.

## 9. Nhiễu đo lường và sự ổn định của baseline

Chạy benchmark một lần rồi lấy chênh lệch 2% làm kết luận thường không đáng tin cậy. Những nguồn nhiễu gồm:

- CPU frequency scaling, turbo boost và nhiệt độ.
- Shared CI runners bị contention.
- CPU quota/cpuset thay đổi.
- JIT warmup, tiered compilation và profile-guided behavior của JVM.
- GC cycles, classloading, code cache và thread scheduling.
- Disk/page cache, network jitter và DNS.
- Database cache, index, background maintenance.
- Số lượng request không đủ cho p99.
- Dataset khác giữa baseline và candidate.
- JDK vendor/update, GC, OS kernel hoặc container image khác.
- Test ordering, randomized seeds và concurrent jobs chạy cùng máy.

**Một regression nhỏ hơn mức nhiễu của hệ đo không nên được tuyên bố chắc chắn là regression thật.** Ngược lại, một biến động lớn nhưng environment thay đổi vẫn cần phân biệt nguyên nhân.

### 9.1. Tách warmup khỏi measurement

Đối với JIT-based JVM:

~~~text
Process start
    │
    ▼
Classloading / JIT warmup / cache settling
    │
    ▼
Measurement window
    │
    ▼
Aggregate + variance + evidence validity
~~~

Warmup duration hoặc điều kiện chuyển pha phải được định nghĩa trước; không loại bỏ tùy ý những mẫu chậm của candidate vì “chắc chưa warm”.

Riêng **startup-time benchmark** cần đo cold start thực sự, không loại warmup đi rồi báo đó là startup latency. Hai test trả lời hai câu hỏi khác nhau.

### 9.2. Lặp lại nhiều process runs

Ví dụ thực hiện 5–10 lượt đo độc lập trên cùng môi trường phù hợp, mỗi lượt có warmup và measurement đã định nghĩa. Đây chỉ là số lượng minh họa; số lượt cần thiết phải dựa trên variance, chi phí và độ nhạy gate.

Không xem 10.000 samples trong cùng một JVM process là tương đương 10.000 independent runs khi mọi sample cùng bị ảnh hưởng bởi một GC state hoặc runner condition.

### 9.3. Baseline distribution thay vì một con số

Ví dụ p95 latency theo từng independent run:

~~~text
Baseline:  101, 99, 103, 100, 98 ms
Candidate: 110, 112, 108, 111, 109 ms
~~~

So sánh median theo run có thể hữu ích. Nhưng nếu:

~~~text
Baseline: 100, 120, 98, 140, 102 ms
Candidate: 108, 111, 105, 122, 110 ms
~~~

thì baseline biến động mạnh hơn; gate nên xem xét measurement quality, các outliers do hạ tầng và kế hoạch rerun, thay vì tự chọn một baseline run có lợi.

Các thống kê như median, interquartile range, median absolute deviation hoặc bootstrap confidence interval có thể hỗ trợ nhưng phải được sử dụng đúng giả định về tính độc lập của samples. Không tạo một p-value từ hàng triệu request samples cùng một process rồi xem như có hàng triệu thí nghiệm độc lập.

## 10. Chọn chính sách với kết quả sát ngưỡng

Một gate mạnh cần định nghĩa **vùng không chắc chắn**:

~~~text
Điều kiện đủ rõ để PASS
      │
      ▼
Vùng gần ngưỡng / variance cao → INCONCLUSIVE hoặc rerun
      │
      ▼
Vi phạm vượt ngưỡng rõ ràng → FAIL
~~~

Ví dụ chính sách minh họa:

1. Nếu dữ liệu thiếu hoặc môi trường không tương đương: INCONCLUSIVE.
2. Nếu candidate vi phạm hard ceiling hoặc correctness rule: FAIL.
3. Nếu regression vượt budget và repeated runs cho cùng xu hướng: FAIL.
4. Nếu regression gần budget, nằm trong dải nhiễu đã được lượng hóa: chạy lại theo rerun policy giới hạn trước.
5. Nếu sau rerun vẫn không thể kết luận: INCONCLUSIVE, chuyển đến người sở hữu benchmark.
6. Nếu PASS và bằng chứng hợp lệ: cho pipeline tiếp tục.

Không dùng chiến lược “rerun mãi cho đến khi có một lần PASS”. Rerun không kiểm soát sẽ làm giảm giá trị của quality gate và khuyến khích chọn kết quả may mắn.

### 10.1. Phải có chính sách khi runner quá nhiễu

Nếu shared runner tạo variance cao, một giải pháp tốt hơn có thể là:

- Dedicated benchmark worker có tài nguyên cố định.
- Pin CPU affinity/CPU limits và kiểm tra noise floor.
- Sử dụng tải nội bộ để tránh network biến động khi đo microbenchmark.
- Giảm số background tasks.
- So sánh baseline và candidate theo lượt gần nhau trên cùng worker khi phù hợp.

Không tăng regression budget lên mức rất lớn chỉ vì môi trường đo kém ổn định. Điều đó làm gate mất khả năng phát hiện regression thật.

## 11. Thử nghiệm thống kê: ý nghĩa thực tiễn và giới hạn

Một kết quả thống kê có thể “significant” nhưng chênh lệch chỉ 0,1% và không đáng kể với sản phẩm; hoặc chênh lệch 10% nguy hiểm nhưng test quá ít samples nên chưa đủ sức kết luận thống kê.

Do đó, quyết định nên cân nhắc đồng thời:

1. **Effect size:** độ lớn chênh lệch thực tế.
2. **Measurement uncertainty:** độ tin cậy và biến động.
3. **Product budget:** mức chấp nhận được của workload.
4. **Hard operational limits:** giới hạn tuyệt đối cần bảo đảm.

Chọn confidence interval, paired comparison hoặc phương pháp robust tùy thiết kế đo. Không áp dụng một t-test đơn giản nếu samples có autocorrelation, phân phối rất lệch hoặc baseline/candidate không độc lập như giả định.

### 11.1. Percentiles cần đủ dữ liệu

p99 là tail metric. Với 100 requests, p99 chủ yếu phụ thuộc 1 request ở cực trị và rất dễ dao động. Với một workload có hàng nghìn requests, p99 vẫn phải được diễn giải theo sampling window và hình dạng phân phối.

Khi báo cáo p95/p99, nên lưu:

- Số requests thành công và thất bại.
- Cách tính percentile (raw samples hay histogram approximation).
- Độ phân giải histogram và sampling policy.
- Thời gian warmup/measurement.
- Load shape/concurrency.
- Có loại timeout hoặc failed requests khỏi latency metric không.

Nếu các failed requests bị loại khỏi latency một cách tùy tiện, candidate có thể trông “nhanh” vì những request chậm nhất đã timeout và bị bỏ khỏi mẫu. Cần gate riêng cho error rate và quy định rõ latency population.

## 12. JMH và benchmark Java có kiểm soát

Với microbenchmark trong Java, **JMH** là công cụ phù hợp vì có cơ chế warmup, measurement, fork và xử lý nhiều cạm bẫy JIT. Tuy nhiên, JMH không tự loại bỏ mọi nhiễu phần cứng hoặc biến một microbenchmark thành kết luận production SLO.

Ví dụ đơn giản dùng JMH annotations:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringParsingBenchmark {
    private final String input = "12345678";

    @Benchmark
    @BenchmarkMode(Mode.AverageTime)
    @OutputTimeUnit(TimeUnit.NANOSECONDS)
    public int parse() {
        return Integer.parseInt(input);
    }
}
~~~

Đoạn trên chỉ minh họa cách khai báo benchmark và cần JMH dependencies/harness phù hợp. Không tự chạy class như một application main thông thường rồi kết luận đó là benchmark đáng tin cậy.

### 12.1. Các nguyên tắc JMH

- Định nghĩa warmup, measurement iterations và forks.
- Không viết benchmark để compiler loại bỏ toàn bộ phép tính không có hiệu ứng quan sát.
- Đảm bảo input/state đại diện tình huống cần kiểm tra.
- Phân biệt AverageTime, Throughput và SampleTime; không so ngược đơn vị.
- Nếu benchmark chạy trên nhiều JDK, ghi JDK flags, collector, CPU và JMH version.
- Xem hiệu quả sau tối ưu và workload thực, không chỉ một micro-operation.

Với function rất nhỏ, sai lệch do constant folding hoặc dead-code elimination có thể lớn hơn nhiều so với JDK regression mà nhóm muốn đo.

### 12.2. Service load tests cần harness khác

Khi đo REST API, dùng load generator và metric pipeline thích hợp; không lấy một JMH benchmark của serializer làm đại diện cho p99 của API có database và network.

Đối với end-to-end, phải chốt workload mix (ví dụ 70% read, 20% update, 10% create), dataset, concurrency, warmup, error handling và duration.

## 13. Các ngưỡng vận hành trên JVM mới

Vận hành không chỉ là “Pod Running” hay “systemd active”. Một service có thể sống nhưng không ready, bị throttling nặng, không flush dữ liệu khi shutdown hoặc thiếu logs để điều tra sự cố.

Các tiêu chí vận hành thường gồm:

| ID | Chỉ số/hành vi | Ngưỡng minh họa | Cách xác minh |
|---|---|---|---|
| O-01 | Startup thành công trên JDK mục tiêu | 100% bắt buộc, không dùng unsupported flags | Smoke startup và JVM log. |
| O-02 | Readiness sau startup | Sẵn sàng trước timeout theo policy | Probe/health test. |
| O-03 | OOMKilled | 0 trong bài load/soak đã định nghĩa | Pod status, memory.events, logs. |
| O-04 | Crash/Unexpected restarts | 0 trong stability window, trừ test chủ động kill | Container/systemd events. |
| O-05 | Memory peak | Dưới container limit với headroom được duyệt | Cgroup/RSS/native/heap metrics. |
| O-06 | CPU throttling | Không vượt budget dưới tải cố định | Cgroup cpu.stat/metrics. |
| O-07 | Graceful shutdown | Drain/stop trong grace period, không mất dữ liệu | SIGTERM + integration test. |
| O-08 | Diagnostics | GC/application logs và metrics có mặt, không rò secret | Collector/smoke checks. |
| O-09 | TLS/truststore | Kết nối tới endpoints hợp lệ, không bỏ verify | TLS integration tests. |
| O-10 | Agent/instrumentation | Agent bắt buộc load đúng 1 lần và hỗ trợ JDK | Startup instrumentation check. |

Các giá trị “0” áp dụng trong **cửa sổ test được định nghĩa**; chúng không thể suy ra xác suất sự cố bằng 0 trong production vô hạn.

### 13.1. Cần phân biệt hard limit và headroom

Container memory limit 2 GiB không có nghĩa “peak 1,99 GiB = PASS tốt”. Nếu workload có burst, thêm connections, thay traffic mix hoặc GC native overhead, headroom còn quá ít.

Một policy minh họa:

~~~text
memory_limit        = 2048 MiB
max_allowed_peak    = 1740 MiB
required_headroom   ≈ 308 MiB
~~~

Đây chỉ là mức ví dụ, không phải tỷ lệ chuẩn. Headroom cần dựa trên memory variance, native buffers, cache và mục tiêu availability.

### 13.2. CPU throttling không có một ngưỡng chung

nr_throttled/nr_periods, throttled_usec và CPU quota giúp nhận diện contention, nhưng không có một tỷ lệ “an toàn” chung cho mọi workload. Một batch job có thể chấp nhận throttling đáng kể nếu hoàn thành trước deadline, trong khi low-latency API nhạy với tail latency.

Ngưỡng cần gắn với:

- CPU limits và cgroups version.
- Workload type và traffic.
- Latency/throughput requirements.
- GC/concurrency behavior.
- Cost và capacity policy.

Không kết luận chỉ từ một counter, hãy đối chiếu throttled time và application latency theo cùng timeline.

## 14. Startup time, readiness và shutdown có ngưỡng riêng

### 14.1. Định nghĩa thời điểm bắt đầu/kết thúc

“Startup time” có thể có nhiều nghĩa:

- Thời gian từ chạy java process đến main method.
- Từ JVM start đến application context initialized.
- Từ container start đến startup probe thành công.
- Từ Pod scheduled đến Ready.
- Từ deployment tạo Pod đến instance sẵn sàng nhận traffic.

Các định nghĩa này **không tương đương**. Khi so sánh JDK, nếu mục tiêu là JVM/application startup, không nên trộn image pull, scheduling và node provisioning vào metric rồi quy lỗi cho JDK.

Ví dụ tiêu chí:

~~~text
Metric: application_start_to_ready_seconds
Start: process start timestamp
End: readiness endpoint đạt đúng điều kiện
Load: no external warmup traffic
Budget: median <= baseline × 1.15
Absolute ceiling: <= 35 seconds
Samples: ít nhất 5 independent process launches
~~~

Các con số là minh họa. Một ứng dụng cần cache warming hoặc migration DB trong startup có thể phải dùng chính sách và metrics khác.

### 14.2. Graceful shutdown

Trong Kubernetes, Pod có terminationGracePeriodSeconds; systemd có TimeoutStopSec. Gate có thể chủ động gửi SIGTERM trong test, xác nhận:

1. Process nhận signal.
2. Readiness bị hạ theo contract.
3. Không nhận request mới trái policy.
4. In-flight work và transaction kết thúc hoặc rollback an toàn.
5. Consumer background jobs dừng đúng.
6. Process exit trong grace period đã định nghĩa.

Không dùng một test chỉ kiểm tra exit code 0 để chứng minh không mất dữ liệu, vì ứng dụng có thể thoát sạch nhưng bỏ dở một nghiệp vụ quan trọng.

## 15. GC, heap và native memory trong acceptance gates

Khi đổi JDK, GC ergonomics hoặc hỗ trợ container/cgroups có thể đổi. Thường cần đo cả:

- Heap used/committed/max.
- GC pause distribution và total pause time.
- GC throughput/CPU overhead.
- Allocation rate và promotion behavior.
- Metaspace/class count, code cache.
- Direct/off-heap/native memory, thread stacks.
- Process RSS và cgroup memory.current/peak.
- OOM events và JVM crash logs.

### 15.1. Đừng dùng heap usage làm đại diện cho container memory

Ví dụ:

~~~text
Java heap used peak       800 MiB
Java heap max            1200 MiB
Container memory peak    1900 MiB
Container limit          2048 MiB
~~~

Heap chỉ là một phần bộ nhớ. Dù heap mới dùng 800 MiB, container có thể gần hard limit do native buffers, metaspace, stacks, mmap hoặc page cache.

### 15.2. Native Memory Tracking có phạm vi riêng

Với HotSpot JDK phù hợp, Native Memory Tracking (NMT) giúp phân loại một số native allocations của JVM. Nhưng NMT không bao phủ mọi cấp phát từ native libraries/third-party code, và có overhead.

Do đó, nếu đặt gate về native memory, phải ghi nguồn đo: NMT category, process RSS, cgroup memory hay công cụ profiling khác. Không so số NMT total với cgroup memory.current như thể hai giá trị đại diện cùng một lượng.

### 15.3. Định nghĩa cửa sổ đo bộ nhớ

Memory peak phụ thuộc test duration, warmup, cache growth, GC và dữ liệu. Nên phân biệt:

- Startup peak.
- Steady-state peak.
- Soak peak hoặc growth slope.
- Peak under stress.

Soak test 2 giờ không thể so trực tiếp với benchmark 5 phút rồi kết luận candidate có memory leak chỉ từ peak khác nhau.

## 16. Thiết kế CI pipeline đa tầng

Một pipeline thực tế có thể tổ chức:

~~~text
Commit / pull request
       │
       ▼
Build & static compatibility checks
       │
       ▼
Unit + API/contract tests
       │
       ▼
Integration tests on supported JDK matrix
       │
       ▼
Service startup/container smoke tests
       │
       ▼
Performance benchmark on controlled runners
       │
       ▼
Operational/stability tests
       │
       ▼
Aggregate evidence and quality gates
       │
       ├─ FAIL / INCONCLUSIVE → Block and triage
       │
       └─ PASS → Candidate eligible for staging/canary
                                  │
                                  ▼
                           Rollout gates
~~~

Không phải mọi job phải chạy trên mỗi pull request nếu chi phí cao. Có thể phân loại:

| Giai đoạn | Thường chạy | Ví dụ |
|---|---|---|
| Per-commit/PR | Nhanh, determinism cao | Compile, unit, contract, dependency/bytecode, smoke. |
| Protected branch/pre-release | Trung bình, môi trường ổn định | JDK matrix, integration, service load test. |
| Nightly | Tốn thời gian | Soak, memory growth, rộng OS/GC matrix. |
| Release candidate | Đầy đủ theo policy | Functional/perf/operational evidence, packaging. |
| Staging/canary | Môi trường gần thật | Health, real traffic/error rate, shutdown, rollback. |

Điều quan trọng là release gate phải biết những job nào bắt buộc. Không để một candidate tự động được phát hành chỉ vì per-PR tests PASS nhưng nightly/regression job đang FAIL hoặc chưa có dữ liệu hợp lệ.

## 17. Java runtime matrix: compile JDK khác test JDK

Gradle Java Toolchains có thể dùng JDK mới cho compiler nhưng biên dịch với options.release cho mức Java tối thiểu; Test task có thể cần launcher khác compiler.

Ví dụ Kotlin DSL cho một Java library có minimum Java 17 nhưng build bằng JDK 21:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

val testJdk = providers.gradleProperty("testJdk")
    .orElse("17").map(String::toInt)

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(
            JavaLanguageVersion.of(testJdk.get())
        )
    })
}
~~~

Đây là ví dụ về việc chọn runtime cho Gradle Test tasks, không phải bảo đảm mọi custom JavaExec hoặc plugin test sẽ tự nhận cấu hình này. Cần kiểm tra mức API Gradle và source project thực tế.

Trong CI:

~~~bash
./gradlew clean test -PtestJdk=17
./gradlew clean test -PtestJdk=21
~~~

Các lượt chạy có thể được thực hiện ở jobs riêng. Khi chạy song song, cần cô lập build directories/caches nếu chúng có thể gây tranh chấp. Ngoài unit tests, phải kiểm tra artifact được đóng gói cùng runtime dependencies trên JDK tối thiểu.

### 17.1. Vì sao phải chạy thật trên JDK tối thiểu?

Biên dịch bằng javac --release 17 không tự đổi bytecode của thư viện phụ thuộc. Một dependency bắc cầu có class version Java 21 có thể bị nạp trên Java 17 rồi gặp UnsupportedClassVersionError.

Vì vậy, nếu sản phẩm công bố Java 17 và Java 21:

- Functional tests bắt buộc có trên Java 17.
- Compatibility smoke tests với artifact trên Java 17.
- Một tập tests thích hợp trên Java 21.
- Nếu còn hỗ trợ OS/architectures khác, matrix mở rộng theo cam kết sản phẩm.

Số lượng tổ hợp không cần là tích Descartes vô hạn; thiết kế theo rủi ro nhưng không bỏ runtime tối thiểu đã công bố.

## 18. Tách “gate engine” khỏi dữ liệu đo

Một thiết kế tốt có ba thành phần:

1. **Test/benchmark runner** tạo dữ liệu kết quả chuẩn hóa.
2. **Policy file** mô tả ngưỡng, điều kiện valid và severity.
3. **Gate evaluator** đọc dữ liệu và quyết định PASS/FAIL/INCONCLUSIVE, sinh báo cáo.

Ví dụ policy ở định dạng YAML:

~~~yaml
policyVersion: 1
suite: java-compatibility
minimumIndependentRuns: 5

functional:
  mandatorySuites:
    - api-contract
    - security-boundary
    - persistence-rollback
  requiredPassRate: 1.0
  allowSkippedCriticalTests: false

performance:
  scenario: checkout-read-write
  latencyP95:
    direction: lower
    maxRegressionPercent: 10
    absoluteCeilingMs: 250
  throughput:
    direction: higher
    maxRegressionPercent: 8
    absoluteFloorRps: 1700

operational:
  unexpectedRestartCountMax: 0
  oomKillCountMax: 0
  requireReady: true
  requireGracefulStop: true
~~~

Đây là **policy minh họa**, không phải schema của một công cụ chuẩn đang được tự động cài đặt. Để chạy thực tế cần evaluator hiểu đúng field names, đơn vị và quy tắc.

### 18.1. Metadata điều kiện valid không được bỏ qua

Ngoài policy trên, evaluator nên xác nhận:

- Baseline và candidate chạy trên hardware/OS/runtime constraints đủ tương đương.
- Workload/scenario và test data có cùng định nghĩa.
- Measurement unit và histogram configuration khớp.
- Số independent runs đủ.
- Không có run bị lỗi hạ tầng hoặc timeouts chưa được phân loại.
- Các test suite bắt buộc có report.
- Candidate artifact, dependency graph và JDK metadata đúng mục tiêu.
- Không có unknown/missing metrics bị âm thầm coi là 0.

Nếu missing p99 data mà evaluator mặc định 0 ms rồi PASS, gate đang khuyến khích thiếu quan sát chứ không kiểm soát hồi quy.

## 19. Ví dụ công thức gate dễ tự động hóa

Với metric có giá trị baseline và candidate dương:

~~~text
For "lower is better":
    absolute_ok = candidate <= ceiling (nếu có)
    regression_ok = candidate <= baseline × (1 + budget)

For "higher is better":
    absolute_ok = candidate >= floor (nếu có)
    regression_ok = candidate >= baseline × (1 - budget)

pass = valid_evidence AND absolute_ok AND regression_ok
~~~

Một cách triển khai đơn giản bằng Python 3 cho dữ liệu đã được tổng hợp:

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    direction: str              # "lower" hoặc "higher"
    max_regression_pct: float    # ví dụ 10.0
    hard_bound: float            # ceiling nếu lower, floor nếu higher


def evaluate_metric(baseline: float,
                    candidate: float,
                    gate: Gate) -> tuple[bool, str]:
    if baseline <= 0:
        return False, "INCONCLUSIVE: baseline must be > 0"

    if gate.direction == "lower":
        regression_boundary = baseline * (
            1.0 + gate.max_regression_pct / 100.0
        )
        okay = (candidate <= regression_boundary
                and candidate <= gate.hard_bound)
    elif gate.direction == "higher":
        regression_boundary = baseline * (
            1.0 - gate.max_regression_pct / 100.0
        )
        okay = (candidate >= regression_boundary
                and candidate >= gate.hard_bound)
    else:
        return False, "INCONCLUSIVE: unknown metric direction"

    return okay, "PASS" if okay else "FAIL"


latency = Gate("lower", 10.0, 250.0)
print(evaluate_metric(180.0, 189.0, latency))

throughput = Gate("higher", 8.0, 1700.0)
print(evaluate_metric(2000.0, 1940.0, throughput))
~~~

Ví dụ chỉ minh họa logic ngưỡng **sau khi số liệu đã được xác thực**. Nó không xử lý dữ liệu thiếu, NaN/Infinity, confidence interval, environment comparability hoặc sample-count validity, nên **không phải một CI gate production hoàn chỉnh**. Trong triển khai thật, các điều kiện đó phải được kiểm tra trước và kết quả INCONCLUSIVE được xử lý như trạng thái riêng.

### 19.1. Không chôn thresholds trong code không kiểm soát

Tốt hơn là policy được review/version cùng repository, nhưng có quyền sở hữu rõ và không để người tạo candidate tự nới ngưỡng trong cùng change mà không review bổ sung.

Cần lưu policy revision trong mỗi báo cáo để biết tại sao cùng số liệu tuần trước PASS còn tuần này FAIL khi threshold thay đổi.

## 20. Quy tắc exit code và tổng hợp CI

Một gate step nên xuất kết quả có cấu trúc và exit status phù hợp:

~~~text
PASS         exit 0
FAIL         exit non-zero
INCONCLUSIVE exit non-zero trong required job
~~~

Đây là gợi ý vận hành; tùy CI engine có thể phân biệt error code hoặc structured status riêng. Quan trọng là **không làm missing evidence mặc định trở thành PASS**.

Ví dụ lược đồ aggregator:

~~~text
Functional gate    PASS
Performance gate   FAIL (p99 +17.7% > +12% budget)
Operational gate   PASS
Evidence quality   PASS
---------------------------------
Overall            FAIL
~~~

Những trị số là ví dụ. Không cộng các điểm thành một average score để một critical functional failure được “bù” bởi throughput tốt.

### 20.1. Hard-fail, soft-fail và warning

Chọn mức theo rủi ro:

- **Hard-fail:** correctness critical, security, data integrity, ABI contract, OOM/crash hoặc hard performance ceilings quan trọng.
- **Soft-fail có owner:** benchmark vừa được thêm, dữ liệu variance cao nhưng chưa chứng minh regression, metric quan sát phụ.
- **Warning:** thay đổi log format không thuộc contract, trend xa mức nguy hiểm nhưng cần theo dõi.

Nếu soft-fail vẫn cho merge, phải quy định điều kiện phát hành: một warning trong PR có thể trở thành blocker ở release candidate. Đừng để warning tồn tại vĩnh viễn không owner.

## 21. Flaky tests và retry policy

Flaky test là test cho kết quả khác nhau khi code/điều kiện kiểm thử đáng lẽ tương đương. Nó có thể do race, time dependency, shared state, môi trường hoặc test design.

Trong migration JDK, một test trước đây “thỉnh thoảng đỏ” có thể đỏ nhiều hơn vì JIT/scheduler/GC timing thay đổi; việc đó không nên bị bỏ qua như “do CI”.

### 21.1. Phân loại nguyên nhân

| Triệu chứng | Khả năng | Hướng xử lý |
|---|---|---|
| Test race fail ngẫu nhiên | Shared mutable state, scheduling. | Sửa concurrency/test isolation. |
| Test timeout chỉ trên shared runner | Resource contention hoặc timeout quá thấp. | So sánh runner resources, profile và budget. |
| Database test lệch dữ liệu | Fixture state không reset. | Isolation/rollback/testcontainers phù hợp. |
| Test chỉ fail trên JDK mới | Behavior/API/runtime change. | Reproduce, debug JDK-specific difference. |
| Test pass sau retry nhiều lần | Flaky hoặc transient issue, chưa chứng minh correctness. | Ghi retry count; điều tra, không chỉ lấy kết quả cuối. |

### 21.2. Retry không được xóa bằng chứng thất bại

Một chính sách có thể cho retry 1–2 lần vì lỗi infrastructure đã phân loại, nhưng phải lưu:

- First failure.
- Nguyên nhân dự kiến.
- Retry count.
- Kết quả từng lần.
- Final status và owner.

Với critical security/data-integrity tests, việc chỉ giữ lần PASS sau retry có thể che regression không ổn định. Các hệ thống thường nên chặn cho đến khi tìm được nguyên nhân hoặc có ngoại lệ được phê duyệt rõ.

### 21.3. Quarantine có thời hạn

Nếu một test flaky bị đưa vào quarantine:

1. Chỉ định owner.
2. Ghi lý do và issue.
3. Đặt deadline khắc phục.
4. Đánh giá có thuộc critical coverage hay không.
5. Nếu critical, phải có kiểm soát thay thế trước khi tạm bỏ gate.

Không quarantine một test chỉ vì nó làm candidate mới FAIL rồi tuyên bố chức năng đã đủ điều kiện.

## 22. Baseline drift và cập nhật ngưỡng

Sau vài tuần, hardware, dependency hoặc workload có thể thay đổi khiến baseline cũ không còn đại diện.

**Re-baselining** là quy trình tạo baseline mới có phê duyệt, không phải thao tác ghi đè tự động mỗi khi pipeline chạy.

### 22.1. Khi nào cần re-baseline?

- Thay đổi hardware/CPU architecture hoặc container resources có chủ đích.
- Framework/algorithm được thay theo major release.
- Workload/test dataset thay đổi theo phiên bản.
- Product SLO hoặc traffic mix được công bố lại.
- Benchmark harness/công cụ đo được nâng cấp.
- JDK migration hoàn tất, version mới đã được xác nhận trở thành baseline vận hành.

### 22.2. Các bước cập nhật

1. Lưu baseline cũ và lý do không còn phù hợp.
2. Chạy tập tests trong môi trường chuẩn với candidate đã được chấp thuận.
3. Có nhiều measurements, dữ liệu variance và metadata.
4. So sánh với SLO/absolute guardrails trước khi duyệt baseline mới.
5. Được owner/nhóm có trách nhiệm phê duyệt.
6. Version baseline + policy, ghi hiệu lực và ngày rà soát.
7. Không xóa evidence lịch sử vì đó là nguồn để tìm regression dài hạn.

Nếu metric ngày càng chậm, tự động cập nhật baseline mỗi ngày có thể khiến mỗi lần chỉ chậm hơn một chút và cuối cùng suy giảm rất lớn mà vẫn PASS. Cần tránh “ratcheting regression” như vậy.

## 23. Waiver và exception handling

Không phải mọi tiêu chí đều luôn tuyệt đối. Một migration có thể chấp nhận performance trade-off vì sửa lỗ hổng bảo mật hoặc yêu cầu product mới. Nhưng ngoại lệ phải là **quyết định có chủ đích**, không phải đổi thresholds lén lút.

Một waiver tối thiểu nên có:

| Trường | Yêu cầu |
|---|---|
| Gate/metric ID | Tiêu chí nào được miễn? |
| Artifact/version | Chỉ áp dụng cho candidate nào? |
| Observed deviation | Chênh lệch và evidence cụ thể. |
| Business/security rationale | Vì sao vẫn chấp thuận? |
| Compensating controls | Giảm rủi ro bằng cách nào? |
| Owner/approver | Ai chịu trách nhiệm và ai duyệt? |
| Expiration | Hết hạn khi nào hoặc điều kiện gỡ bỏ? |
| Follow-up issue | Kế hoạch khắc phục và đo lại. |

Ví dụ một startup benchmark tăng 8 giây do bổ sung certificate verification bắt buộc có thể được đánh giá trong bối cảnh rủi ro và điều chỉnh SLO/timeout có phê duyệt. Nhưng không nên dùng waiver để bỏ qua lỗi authorization hoặc mất dữ liệu nghiêm trọng.

### 23.1. Không biến WAIVED thành PASS

Trong báo cáo, ghi rõ:

~~~text
Gate O-Startup: WAIVED until version X, approver Y
Gate F-Authorization: PASS
Gate P-Latency: PASS
Overall release: CONDITIONAL APPROVAL
~~~

Trạng thái conditional approval cần được nhìn thấy ở release notes/decision record nội bộ. Khi waiver hết hạn, pipeline phải quay về enforcement policy.

## 24. Từ CI sang staging/canary

CI đo chức năng và hiệu năng trong điều kiện đã thiết kế; production traffic thường phức tạp hơn và chứa long-tail workloads. Vì vậy một migration có rủi ro cao nên có rollout gates.

Một trình tự:

~~~text
CI quality gates PASS
        │
        ▼
Staging on target JDK/image
        │
        ▼
Synthetic + integration + load checks
        │
        ▼
Canary rollout (small share)
        │
        ▼
Compare SLI/error/latency/memory against controls
        │
   ┌────┴─────┐
   ▼          ▼
PASS         FAIL
   │          │
Expand       Rollback and triage
   │
   ▼
Full rollout + monitoring
~~~

### 24.1. Canary metrics

Các chỉ số thường có giá trị:

- Error rate theo endpoint/status, không chỉ tổng 5xx.
- Tail latency và throughput theo nhóm traffic.
- JVM crash, OOMKilled, restart và health failures.
- CPU throttling, heap/native memory, GC pause/overhead.
- Database connection pool saturation, queue depth và timeout.
- TLS, message retry/dead-letter hoặc dữ liệu bất thường.
- Business correctness signals quan trọng (ví dụ số giao dịch lỗi).

Đối chiếu canary với control cohort ở điều kiện traffic đủ tương đương. Nếu canary chỉ nhận request nhẹ nhưng control nhận request nặng, so latency trực tiếp sẽ không phản ánh ảnh hưởng của JDK.

### 24.2. Rollback gate

Định nghĩa rõ:

- Metric nào vi phạm thì tự động rollback.
- Cửa sổ quan sát và số mẫu tối thiểu.
- Hành vi khi metrics pipeline mất dữ liệu.
- Thời gian tối đa trước khi rollback.
- Phương án rollback image/JDK/config và DB changes.
- Owner nhận cảnh báo và điều tra.

Rollback một Java binary có thể không đủ nếu cùng đợt migration đã thay database schema, serialized state hoặc message format theo cách không tương thích ngược.

## 25. Phân tích nguyên nhân khi gate FAIL sau nâng JDK

Khi gate đỏ, trước tiên xác định **bằng chứng nói gì**, không vội sửa threshold.

### 25.1. Functional failure

Nếu unit/contract test FAIL:

1. Xem failing assertion, JDK runtime/version và stack trace.
2. Xác định có thay API, exception type, serialization, timezone hoặc charset không.
3. So sánh dependency graph và test data.
4. Kiểm tra thread scheduling/race nếu fail không ổn định.
5. Dùng testcase nhỏ nhất tái hiện.
6. Nếu behavior mới là thay đổi có chủ đích, cập nhật contract/test có review.

### 25.2. Performance regression

Nếu p95 tăng hoặc throughput giảm:

1. Kiểm tra measurement comparability và sample count.
2. Xem CPU quota/cpuset, throttling, memory limit.
3. So sánh JDK flags, GC, active processors và compiler/JIT behavior.
4. Xác định workload nào bị ảnh hưởng, không dựa một số tổng.
5. Đo allocation, GC pause, cache hit/miss, DB I/O và network.
6. Kiểm tra dependency/framework thay đổi cùng JDK.
7. Rerun trong policy có giới hạn để phân biệt noise.
8. Sửa nguyên nhân hoặc đưa ra decision record khi trade-off được chấp thuận.

### 25.3. Operational failure

Nếu OOMKilled, crash hoặc không Ready:

1. Phân biệt Java OutOfMemoryError với kernel/container OOM kill.
2. Xem cgroup memory.events, container status, JVM heap/native metrics.
3. Kiểm tra startup script/systemd/Kubernetes command/args.
4. Xác định removed JVM flags và agent compatibility.
5. Kiểm tra truststore, TLS, filesystem permissions và native libraries.
6. Test lại trên runtime/OS/architecture thực sự được triển khai.

Không quy mọi lỗi sau migration cho JDK core. Thay base image, container runtime, build plugin, framework hoặc dependency cũng có thể là nguyên nhân.

## 26. Ví dụ ma trận acceptance cho Java 17 → Java 21

Giả sử một service hiện chạy Java 17, mục tiêu Java 21 và business contract chưa đổi. Một matrix minh họa:

| Gate | Java 17 baseline | Java 21 candidate | Ngưỡng | Kết quả cần báo |
|---|---|---|---|---|
| API contract | Golden fixtures hiện hành | Chạy fixtures giống nhau | 0 breaking differences không duyệt | PASS/FAIL |
| Auth/data isolation | Test security bắt buộc | Chạy cùng fixtures | 0 violations | PASS/FAIL |
| Transaction rollback | Failure-path suite | Chạy trên JDK 21 | 100% required cases PASS | PASS/FAIL |
| CPU-bound component throughput | 15.000 op/s | Ví dụ 14.250 op/s | Giảm tối đa 8% | PASS |
| Service p95 | 120 ms | Ví dụ 135 ms | Tăng tối đa 10%; trần 180 ms | FAIL |
| Service error rate | 0,01% | Ví dụ 0,01% | Trần 0,10% và đủ mẫu | PASS |
| Startup-to-ready | 20 s | Ví dụ 23 s | Tăng tối đa 20%; trần 30 s | PASS |
| Peak memory | 950 MiB | Ví dụ 1.050 MiB | Dưới budget đã duyệt | Theo policy |
| OOMKilled/restarts | 0 | 0 | 0 trong stability window | PASS |
| Graceful shutdown | Thành công | Thành công | Dừng trong grace period | PASS |

Với p95 từ 120 ms lên 135 ms, regression là 12,5%, vượt budget 10%. Trong ví dụ này, tổng gate **FAIL** cho đến khi xử lý regression hoặc có waiver được duyệt. Không thể kết luận “ứng dụng đạt” chỉ vì mọi functional tests PASS.

### 26.1. Lưu ý về thay đổi GC

Nếu JDK mới mặc định một collector/setting khác, việc đo baseline và candidate với flags mặc định có thể phản ánh cả **policy default** và runtime improvements. Điều đó có giá trị nếu sản phẩm dự định dùng defaults mới.

Nếu muốn cô lập ảnh hưởng JDK core, có thể chạy thêm một benchmark với GC/flags được kiểm soát, miễn collector/flags được hỗ trợ ở cả hai versions. Không ép dùng GC không được hỗ trợ chỉ để giữ environment “giống nhau” một cách giả tạo.

## 27. Kiến trúc báo cáo CI có thể truy xuất

Một quality report nên có:

~~~text
Release candidate:
  commit:
  artifact/image checksum:
  dependency lock/BOM:
  JDK vendor/version/update:
  build tool:

Baseline:
  source/version:
  JDK and flags:
  hardware/OS/container:
  policy version:

Functional:
  required suites:
  executed/passed/failed/skipped:
  failing contract IDs:

Performance:
  scenario and dataset:
  run count/warmup/measurement:
  raw result locations:
  baseline/candidate summaries:
  variation/uncertainty:
  per-metric budget and outcome:

Operational:
  startup/readiness:
  memory/CPU/cgroup limits:
  heap/GC/native metrics:
  OOM/crashes/restarts:
  TLS/agent/shutdown:

Decision:
  PASS / FAIL / INCONCLUSIVE / WAIVED:
  blockers:
  waived metrics + approvals:
  next action and owner:
~~~

Không thay metrics bằng một dòng “Performance OK”. Cần có baseline, candidate, units, threshold, variance và scenario ID để người khác tái kiểm tra.

### 27.1. Raw data và summaries

Raw measurements nên được giữ theo retention policy để điều tra sự khác nhau; summaries giúp người phê duyệt đọc nhanh. Các metrics phải gắn cùng artifact commit/JDK/hardware/test profile để tránh so nhầm kết quả của hai pipeline khác nhau.

Không lưu private production payload, token hoặc secrets trong benchmark artifacts. Nếu test dùng dữ liệu production-like, phải có quy trình ẩn danh hoặc dữ liệu tổng hợp an toàn.

### 27.2. Không ghi đè lịch sử PASS/FAIL

Khi một gate được rerun, giữ history hoặc ít nhất reference đến first attempt và lý do. Nếu chỉ lưu kết quả PASS cuối cùng, nhóm mất khả năng phát hiện sự bất ổn của CI và đo xu hướng dài hạn.

## 28. Checklist trước khi đưa quality gate thành required check

### 28.1. Functional

- [ ] Có danh mục critical user journeys và contract IDs.
- [ ] Required suites được discover và executed trên JDK mục tiêu.
- [ ] Không có critical tests bị skipped/quarantined không kiểm soát.
- [ ] API/binary compatibility có policy cho public libraries.
- [ ] Serialization, persistence, time/locale, security và concurrency có test thích hợp.
- [ ] Thay đổi có chủ đích được version hóa và review.

### 28.2. Performance

- [ ] Baseline được duyệt và có metadata đầy đủ.
- [ ] Runner/hardware/JDK/resources/workload tương đương.
- [ ] Warmup, measurement và independent runs được định nghĩa.
- [ ] Chỉ số có đơn vị và chiều đo rõ.
- [ ] Có hard ceiling/floor và regression budget khi cần.
- [ ] Có chính sách cho baseline 0, missing data và variance.
- [ ] Không tự pass bằng cách lấy lần rerun may mắn.
- [ ] p95/p99 có đủ sample volume và thống nhất cách tính.

### 28.3. Operational

- [ ] Startup/container/JDK/version và agents đúng runtime.
- [ ] Resource limits, Xmx/native headroom và GC được đo.
- [ ] OOMKilled, crashes, restarts, throttling và probes có evidence.
- [ ] SIGTERM/graceful shutdown đã thử trên topology phù hợp.
- [ ] Logs, metrics, alerts có mặt và không lộ secrets.
- [ ] TLS/truststore/native dependencies có integration tests.

### 28.4. Policy và vận hành CI

- [ ] Policy file có version và owner.
- [ ] FAIL/INCONCLUSIVE không tự được diễn giải PASS.
- [ ] Required jobs và release gating rõ ràng.
- [ ] Rebaseline/waiver có approval, expiry và audit trail.
- [ ] Metrics artifacts có checksum, JDK và environment metadata.
- [ ] Có staging/canary/rollback criteria cho release rủi ro cao.

Checklist hướng dẫn thiết kế CI trong sản phẩm thật; việc đánh dấu một mục cần có bằng chứng, không tự cho rằng đã kiểm chứng chỉ vì cấu hình tồn tại trong repository.

## 29. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| “Build xanh là migration thành công.” | Không phát hiện lỗi runtime/hiệu năng. | Có functional, performance và operational gates. |
| Đặt thresholds sau khi nhìn candidate | Điều chỉnh kết quả theo mong muốn. | Định nghĩa policy trước, version và review. |
| Baseline lấy từ một run bất kỳ | Dễ bị nhiễu hoặc chứa regression. | Baseline approved, repeated và metadata đầy đủ. |
| So benchmark khác CPU/hardware | False regression/improvement. | Dùng runner và workload tương đương. |
| Chỉ so average latency | Bỏ sót tail/timeout. | Đo p95/p99, error rate và đủ samples. |
| Chỉ so % mà không có absolute bound | Có thể PASS dù vượt SLO. | Kết hợp hard ceiling/floor và regression budget. |
| Chỉ có absolute SLO bound | Cho phép regression lớn dưới trần. | Bổ sung relative regression budget. |
| Thiếu metric thì mặc định 0 | Gate PASS giả. | Fail closed hoặc INCONCLUSIVE. |
| Retry đến khi PASS | Che flaky regression. | Rerun policy giới hạn, giữ lịch sử. |
| Tự update baseline mỗi ngày | Suy giảm tăng dần không bị phát hiện. | Rebaseline có approval. |
| Test pass trên JDK build, không chạy JDK tối thiểu | Có thể lỗi dependency runtime. | Chạy Test JVM/artifact thực ở supported JDKs. |
| Xmx dưới limit nên chắc không OOM | Native/off-heap vẫn tiêu thụ memory. | Đo cgroup peak và headroom. |
| CPU throttle được coi là metric phụ vô hại | Có thể làm tail latency tăng mạnh. | Gắn metric với workload/SLO. |
| Đánh giá p99 từ rất ít requests | Percentile không đáng tin cậy. | Đủ sample volume và measurement window. |
| Benchmark đạt vì failed requests bị loại | Candidate trông nhanh nhưng lỗi nhiều. | Gate error rate và định nghĩa latency population. |
| Tổng hợp điểm trung bình cho mọi gate | Lỗi bảo mật bị “bù” bằng throughput. | Critical hard-fail độc lập. |
| Waiver không expiry/owner | Nợ chất lượng kéo dài vô hạn. | Waiver giới hạn và audit. |
| Pod Running được coi là Ready/Healthy | Không phát hiện probe/traffic failure. | Runtime readiness và integration checks. |
| Chỉ có CI, không có rollout gate | Bỏ sót production behavior. | Canary/SLO checks và rollback plan. |

## 30. Quy trình triển khai acceptance thresholds từng bước

**Bước 1 — Xác định support contract.** Ghi JDK tối thiểu/đích, OS, architecture, API compatibility và behavior bắt buộc giữ nguyên. Chỉ rõ business-critical journeys và security/data invariants.

**Bước 2 — Chốt baseline.** Chọn release/artifact/JDK/workload đại diện; lưu checksum, dependency lock, hardware/container metadata và raw measurements.

**Bước 3 — Phân loại metrics.** Chia functional, performance, operational; xác định đơn vị, chiều đo, time window, source of truth và owner cho từng metric.

**Bước 4 — Định nghĩa ngưỡng trước.** Dùng hard ceiling/floor, regression budget và evidence quality rules. Với functional critical yêu cầu 0 vi phạm trong tập tests đã định nghĩa.

**Bước 5 — Thiết lập controlled runners.** Khóa resource limits, dataset, tool versions, warmup, samples và test harness; tránh noisy neighbors khi đo hiệu năng nhạy.

**Bước 6 — Chạy JDK matrix.** Test trên JDK mới và các runtime vẫn được công bố hỗ trợ. Tách kết quả build JDK khỏi runtime JVM. Kiểm tra dependency artifacts và class-file levels.

**Bước 7 — Tích hợp gate engine.** Đọc structured results và policy đã version hóa; phân biệt PASS/FAIL/INCONCLUSIVE. Các dữ liệu thiếu không được mặc định PASS.

**Bước 8 — Chẩn đoán thất bại.** Phân loại correctness, noise, runtime resource, GC/JIT, dependency hoặc deployment. Tái hiện, không chỉ thay thresholds.

**Bước 9 — Ghi decision record.** Lưu per-metric result, raw data, JDK/runtime metadata, waivers và người phê duyệt.

**Bước 10 — Triển khai có guardrails.** Sau CI PASS, tiếp tục staging/canary theo policy. Theo dõi error, tail latency, memory, OOM, restarts và rollback khi vi phạm.

**Bước 11 — Bảo trì thresholds.** Đánh giá noise, sản phẩm thay đổi và rebaseline theo quy trình được duyệt. Không tự động trôi baseline theo kết quả mới nhất.

## 31. Kết luận

**Ngưỡng chấp nhận chức năng, hiệu năng và vận hành trong CI** là cơ chế biến Java compatibility migration từ một hoạt động “chạy test xem có xanh không” thành **quyết định phát hành có tiêu chí và bằng chứng**. Functional gate bảo vệ hợp đồng API/dữ liệu/bảo mật; performance gate đo chênh lệch với baseline và hard limits trong môi trường có kiểm soát; operational gate xác nhận JDK, container resources, startup, readiness, logs, GC/memory, shutdown và khả năng khôi phục.

Không có một tỷ lệ latency regression hoặc một mức MaxRAMPercentage đúng cho mọi sản phẩm. Threshold phải được chọn dựa trên user experience, SLO, workload, độ nhiễu của hệ đo và mức rủi ro nghiệp vụ. Baseline cần có nguồn gốc, phép đo phải tái lập được, dữ liệu thiếu phải được phân loại rõ và waiver phải có owner/thời hạn.

Mục tiêu cuối cùng không phải **làm cho mọi ô CI xanh bằng mọi giá**, mà là **biết chính xác điều gì đã được kiểm chứng, điều gì chưa, mức suy giảm nào được phép và khi nào cần chặn hoặc rollback**. Khi những quy tắc đó được quản lý cùng artifact, JDK/runtime matrix và rollout policy, nhóm có thể nâng Java một cách minh bạch, bảo vệ hợp đồng hiện có và phát hiện regression đủ sớm trước khi gây ảnh hưởng người dùng.
