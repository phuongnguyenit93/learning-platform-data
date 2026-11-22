# 2.2 Lập mốc so sánh ở trạng thái bình thường và ghi lại điều kiện đo

Một con số như “CPU 70%”, “p95 = 180 ms” hoặc “heap dùng 600 MiB” **chưa đủ** để kết luận ứng dụng Java có bất thường. Cần biết số đó được đo trên bản build nào, tại tải bao nhiêu, JVM đã warm-up chưa, trong khoảng thời gian nào, giới hạn CPU/RAM thực tế ra sao và trước đó hệ thống thường vận hành như thế nào.

**Baseline** (mốc so sánh) là tập số liệu cùng bối cảnh, được thu thập bằng phương pháp đủ nhất quán để so sánh với một lần đo khác. Lập baseline không đơn giản là chụp một ảnh dashboard: phải định nghĩa thế nào là “bình thường”, chọn đại lượng, cố định hoặc ghi lại điều kiện đo, thu thập đủ mẫu và lưu bằng chứng có thể kiểm tra lại.

Bài này tập trung vào **phương pháp đo** trong Java runtime diagnostics: xây dựng baseline đáng tin, ghi điều kiện đo, tránh sai lệch do warm-up/JIT/GC/tải/container, và dùng baseline để đánh giá biến động thay vì vội quy kết nguyên nhân.

## 1. Hiểu đúng baseline, trạng thái bình thường và ngưỡng chất lượng

### 1.1 Baseline chứa cả số liệu lẫn điều kiện đo

Một bản ghi baseline tối thiểu trả lời được bốn nhóm câu hỏi:

1. **Đo cái gì?** Ví dụ: latency p50/p95/p99 của một endpoint, throughput, tỷ lệ lỗi, CPU, GC pause, heap used, queue depth.
2. **Đo ở đâu và bằng gì?** JVM/process/container/host nào, công cụ và phiên bản nào, metric có đơn vị và cách tính gì.
3. **Đo dưới điều kiện nào?** Bản build, JDK/JVM/flags, GC, tài nguyên cấp phép, dữ liệu, loại request, tốc độ đến, concurrency, dependency, warm-up, thời gian đo.
4. **Dữ liệu có đáng tin để so sánh không?** Có bao nhiêu yêu cầu/mẫu, mất mẫu không, clock/window có đồng bộ không, đã lặp lại chưa, hệ thống có sự cố ngoài dự kiến không.

Vì vậy, một baseline có thể được mô tả khái quát là:

```text
Baseline = điều kiện / kịch bản đo
         + chuỗi số liệu có đơn vị và mốc thời gian
         + cách thu thập / xử lý số liệu
         + kiểm tra chất lượng và mức dao động giữa các lần đo
```

Nếu mất phần điều kiện, số liệu không đủ ngữ cảnh để so sánh; nếu mất số liệu gốc và phương pháp, kết luận khó tái hiện.

### 1.2 “Bình thường” không có nghĩa là “đạt yêu cầu”

Cần tách ba khái niệm:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Baseline** | Ở điều kiện xác định, hệ thống thường có kết quả nào và dao động bao nhiêu? | Trong kịch bản cố định, p95 dao động khoảng 85–95 ms qua nhiều lần đo |
| **SLO / tiêu chí chấp nhận** | Hệ thống *phải* đạt mức chất lượng nào? | Ít nhất 99,9% request thành công trong cửa sổ đã quy định |
| **Ngưỡng cảnh báo** | Khi nào cần điều tra biến động hoặc vi phạm chất lượng? | Cảnh báo khi p95 tăng bền vững so với mốc và số request đủ lớn |

Baseline được lấy từ một hệ thống vốn đã chậm có thể tái hiện rất ổn định sự chậm đó. Nó vẫn là baseline mô tả hiện trạng, nhưng **không tự chứng minh** hệ thống đạt SLO. Ngược lại, một ứng dụng có p95 thấp hơn baseline vẫn có thể vi phạm SLO ở lỗi 5xx hay khả dụng.

Không tồn tại một ngưỡng tăng 10%, 20% hoặc 30% đúng cho mọi hệ thống. Mức biến động bình thường, mức tác động tới người dùng và mức bất định đo được mới quyết định khi nào cần chú ý.

### 1.3 Bình thường là một *tập điều kiện* được mô tả rõ

Với dịch vụ Java, thường cần phân biệt ít nhất các bối cảnh sau nếu chúng có ý nghĩa thực tế:

- **Cold start:** khởi động ứng dụng, load class, thiết lập pool, cache chưa ấm; thời gian/CPU/IO có thể khác giai đoạn ổn định.
- **Warm-up:** JIT biên dịch các đường thực thi nóng, cache và connection pool dần đạt trạng thái vận hành; không mặc nhiên đã ổn định sau một thời gian cố định.
- **Steady state:** tải và những đại lượng mục tiêu tương đối ổn định trong cửa sổ quan sát; vẫn có GC, request chậm và dao động hợp lệ.
- **Peak bình thường:** cao điểm dự kiến theo giờ hoặc workload; nên có baseline riêng, tránh so tải thấp với tải cao.
- **Batch/maintenance:** job nền, compaction, backup hoặc tác vụ theo lịch có thể thay đổi profile; ghi rõ có/không diễn ra.

Không gom mọi trạng thái vào một số “bình thường” duy nhất rồi dùng để giải thích mọi tình huống. Khi môi trường production có nhiều nhóm tải, dùng các baseline theo từng nhóm hoặc theo biến điều kiện phù hợp.

## 2. Chọn kịch bản có thể lặp lại trước khi bấm đo

Một baseline có ích phải gắn với câu hỏi chẩn đoán cụ thể. Ví dụ: “Tại lưu lượng ghi 50 request/giây, endpoint tạo đơn trên phiên bản này có p95 bao nhiêu và dùng bao nhiêu CPU?” khác hẳn “Ứng dụng tiêu tốn bao nhiêu CPU khi không có người dùng?”.

### 2.1 Định nghĩa workload như một hợp đồng đo

Ghi rõ:

- **Đường đi:** endpoint/loại message/batch job, tỷ lệ các loại thao tác đọc-ghi, payload, kích thước dữ liệu và kiểu response.
- **Tải đầu vào:** số request/s thực sự *được gửi* (offered rate), số request/s hoàn thành (throughput), concurrency/in-flight, thời gian nghỉ (think time), thời gian giữ kết nối và retry.
- **Dữ liệu:** độ lớn bảng/collection, phân bố khóa, cache hit, thứ tự dữ liệu, phiên bản schema, dữ liệu mới so với đã có.
- **Phụ thuộc:** DB, cache, broker, DNS, dịch vụ thứ ba; độ trễ, giới hạn pool và topology. Một DB “chậm hôm nay” làm baseline ứng dụng thay đổi dù code không đổi.
- **Phân bố:** tải tăng đều, burst, steady, chu kỳ; tỷ lệ request lỗi và timeout cũng là đặc trưng workload, không được bỏ qua.
- **Điều kiện thành công:** tiêu chí cho phép nhận bộ dữ liệu là baseline bình thường, chẳng hạn không deploy giữa phép đo, không có lỗi hạ tầng ngoài dự kiến, đủ traffic, log không báo bất thường.

**Offered load không đồng nghĩa throughput.** Nếu client chỉ gửi request tiếp theo sau khi request trước hoàn thành (mô hình closed-loop), dịch vụ chậm có thể làm *giảm chính tốc độ gửi*, khiến số liệu trông “nhẹ tải” hơn. Với bài kiểm tra theo arrival rate, đo cả lịch phát sinh request và yêu cầu đã hoàn thành; dùng load generator nhận biết nguy cơ **coordinated omission** (bỏ sót thời gian chờ do bộ tạo tải không phát lệnh đúng lịch khi hệ thống bị nghẽn).

### 2.2 Cố định những biến cần cố định, ghi lại những biến không kiểm soát được

Để so hai lần đo A/B, không cần khẳng định toàn bộ môi trường tuyệt đối giống nhau; cần **biết điều gì giống, điều gì thay đổi và ảnh hưởng tiềm tàng của khác biệt**.

| Nhóm điều kiện | Điều tối thiểu cần lưu | Vì sao có thể làm lệch baseline? |
| --- | --- | --- |
| Mã và cấu hình | Commit/build ID, image digest, feature flags, cấu hình pool/cache, log level | Cùng tên phiên bản vẫn có thể chạy artifact hoặc flag khác |
| Java runtime | Java vendor/version/build, JVM implementation, `-Xms`/`-Xmx`, GC, JVM flags, `JAVA_TOOL_OPTIONS` nếu dùng | JIT, GC, ergonomics, sizing thay đổi giữa runtime hoặc flags |
| Tài nguyên | CPU cores/quota, affinity, memory limit, host/VM type, container requests/limits, số replica | CPU throttling và memory pressure làm tăng latency |
| Workload | Script/version, arrival rate, concurrency, payload, tỷ lệ endpoint, dữ liệu và seed | Thay đổi lượng và loại công việc làm mất tính so sánh |
| Dependencies | DB/broker/cache versions, topology, pool limits, latency ngoài ứng dụng | Nút nghẽn có thể ở hệ thống khác |
| Đo đạc | Instrumentation/profiler, sampling, scrape interval, histogram buckets, exporter version | Công cụ làm phát sinh overhead hoặc đổi cách tính |
| Thời gian | Bắt đầu/kết thúc UTC, timezone hiển thị, warm-up, số lần chạy, sự kiện deploy/GC/backup | Chọn sai cửa sổ làm trộn cold start với steady state |

Không lưu mật khẩu, token, chuỗi kết nối chứa bí mật hay dữ liệu cá nhân trong manifest baseline. Với flag/env nhạy cảm, ghi phiên bản cấu hình hoặc giá trị đã loại bỏ bí mật nhưng vẫn đủ chứng minh điều kiện đo.

## 3. Chọn số đo ở các lớp ứng dụng, JVM và hệ điều hành

Đo đầy đủ không có nghĩa thu mọi metric đang tồn tại. Bắt đầu từ giả thuyết cần phân biệt, rồi chọn tập số liệu bổ trợ nhau.

### 3.1 Tầng ứng dụng và kết quả người dùng

Một tập có ích cho HTTP/service:

| Metric | Đơn vị / cách đọc | Điểm cần thận trọng |
| --- | --- | --- |
| Request count | số request trong cửa sổ | Định nghĩa có tính retry và timeout hay không |
| Offered request rate | request/giây từ phía client/generator | Phân biệt request được gửi với request hệ thống xử lý xong |
| Throughput | request hoàn thành/giây | Không suy ra latency chỉ từ throughput |
| p50/p95/p99 latency | ms theo phân bố request cùng loại/cùng cửa sổ | p99 rất nhạy với số mẫu; tránh lấy trung bình các percentile |
| Error rate | lỗi / tổng request hợp lệ, % | Ghi loại lỗi: 4xx/5xx/timeout/transport/application |
| In-flight, queue length, pool utilization | số lượng hoặc % | Làm rõ định nghĩa metric và giới hạn của pool |
| Dependency latency | ms theo DB/cache/broker/call | Chỉ đo end-to-end có thể không định vị được lớp gây trễ |

Một request mất 500 ms có thể dành 450 ms để đợi database, 30 ms xử lý ứng dụng và 20 ms phần còn lại. Muốn biết Java runtime có vấn đề, cần đo được các pha hoặc có trace đủ chi tiết; chỉ nhìn tổng latency là chưa đủ.

### 3.2 JVM: đo hành vi runtime cùng cửa sổ

- **GC:** số lần, tổng pause time, phân bố pause, allocation rate, heap occupancy trước/sau GC. Một lần pause dài ở ngoài cửa sổ latency không thể mặc định giải thích mọi request chậm trong cửa sổ.
- **Memory:** used/committed/max heap, metaspace, code cache, direct/native memory khi có nguồn đo; nên so với RSS và memory limit. `-Xmx` không phải tổng RAM tiến trình.
- **Threads và contention:** số live platform threads, deadlock/blocked/waiting, executor queue, lock wait; virtual threads (Java 21+) không tương ứng 1:1 với native OS threads.
- **Compilation/class loading:** warm-up JIT, class loading và compilation có thể làm số đo giai đoạn khởi động khác với steady-state.
- **JFR / MXBeans / GC logs:** các nguồn bổ trợ giúp liên hệ runtime events với vấn đề quan sát ở application metrics. Ghi rõ loại recording và overhead nếu áp dụng.

Tránh so CPU của JVM trong khi một lần chạy đang bật profiler nặng và lần kia không bật; bản thân quan sát cũng có thể thay đổi hệ thống. Ghi rõ instrumentation có mặt trong tất cả lần đo hay chỉ trong một phiên điều tra.

### 3.3 OS, container và host: tài nguyên thực tế JVM được dùng

- CPU theo **process và thread**, mức sử dụng so với số CPU được phép, CPU throttling và runnable queue khi có.
- RSS và mức sử dụng container/cgroup, memory limit, OOM events; page cache và native memory tùy cơ chế hạch toán.
- Disk latency/IOPS/throughput, network errors/RTT, open file descriptors/socket state.
- CPU steal của VM, mức tranh chấp host hoặc noisy neighbor khi công cụ có thể quan sát.

Ví dụ, host sử dụng CPU trung bình 20% không phủ nhận khả năng container bị CPU throttling vì quota thấp. Ngược lại, heap used giảm không đồng nghĩa RSS giảm ngay. Khi chụp baseline phải ghi **scope của metric**: host-wide, container, process hay từng thread.

### 3.4 Ưu tiên tập metric gọn nhưng đủ đối chiếu

Một lần đo service ổn định thường bắt đầu bằng bốn nhóm:

1. **Kết quả:** throughput, latency distribution, error rate.
2. **Áp lực:** concurrency, queue/in-flight, mức sử dụng pool.
3. **JVM:** heap trend, GC pauses/frequency, thread count và runtime events phù hợp.
4. **Hệ thống:** process CPU, quota/throttling, RSS/limit, disk/network khi là nghi vấn.

Sau khi nhìn thấy khác biệt, mới tăng độ chi tiết, chẳng hạn JFR recording hoặc thread dump tại thời điểm bất thường. Thu hết mọi profile trên mỗi baseline vừa tốn chi phí vừa dễ làm điều kiện đo thay đổi.

## 4. Chọn cửa sổ, cadence và cách tính để số liệu có ý nghĩa

### 4.1 Một lần đo nên có các pha rõ ràng

Ví dụ cho phép thử tải cố định:

```text
Chuẩn bị dữ liệu / hệ thống
      |
      v
Khởi động JVM và dependency
      |
      v
Warm-up: phát tải đại diện, chờ ổn định
      |
      v
Steady-state đo chính thức: ghi thời gian bắt đầu/kết thúc
      |
      v
Cooldown / dừng tải
      |
      v
Lưu metrics, raw samples, JFR/log và manifest cùng run ID
```

**Không tính warm-up vào baseline steady-state** nếu mục tiêu là steady-state; vẫn có thể lưu nó như một bộ dữ liệu riêng. Đừng giả định warm-up luôn hoàn tất sau đúng 30 giây: phụ thuộc ứng dụng, JIT, cache, connection setup, GC và tải. Quan sát throughput, latency, compilation/GC và cache đến khi tương đối ổn định trong điều kiện mục tiêu.

Một run có thể gồm nhiều khoảng đo nhưng cần ghi rõ đoạn nào chính thức. Nếu đo cả startup, hãy tách startup time và first-request latency thay vì hòa vào p95 của giai đoạn ổn định.

### 4.2 Thời gian thực, thời gian đơn điệu và đồng bộ cửa sổ

- Dùng **UTC wall-clock** để gắn mốc giữa nhiều máy, log và dashboard; lưu cả timezone nếu UI hiển thị địa phương.
- Dùng đồng hồ đơn điệu như `System.nanoTime()` để đo **elapsed duration trong cùng JVM**; không chuyển giá trị `nanoTime()` thành thời điểm lịch. Không dùng `System.currentTimeMillis()` làm nguồn chính cho đoạn đo ngắn vì wall-clock có thể điều chỉnh.
- Khi so sự kiện giữa JVM, container, DB và load generator, bảo đảm đồng bộ clock đủ tốt hoặc ghi sai lệch; kiểm tra time range và timezone.
- Ghi **scrape interval**, bước query, khoảng aggregation và cách xử lý missing samples. Không lấy điểm metric 5 phút so trực tiếp với histogram latency 10 giây rồi tuyên bố quan hệ nhân quả.

Ví dụ, GC pause lúc 10:02:15Z chỉ có giá trị giải thích spike p99 nếu cửa sổ latency và request tương ứng bao phủ khoảng ấy, không bị lệch timestamp và có nguồn đo đủ chi tiết.

### 4.3 Counter, gauge, histogram: tránh dùng sai mẫu số

**Counter** tích lũy sự kiện: tính rate cho một cửa sổ bằng độ tăng counter / số giây; chú ý reset khi tiến trình restart. **Gauge** là số đo tại thời điểm hoặc trạng thái (heap used, queue depth): có thể lấy min/max/avg theo thời gian nếu giữ nguyên định nghĩa. **Histogram/timer** biểu diễn phân bố quan sát: dùng để suy ra percentile khi có đủ mẫu.

Ví dụ: từ 12:00:00 đến 12:01:00 UTC, counter hoàn thành tăng 12.000 thì throughput trung bình trong cửa sổ là `12.000 / 60 = 200 request/giây`. Nếu có 24 lỗi trong 12.000 lần hoàn thành, tỷ lệ lỗi là `24 / 12.000 × 100 = 0,2%`. Hai phép tính chỉ đúng nếu numerator/denominator định nghĩa cùng đối tượng và cùng cửa sổ.

Percentile cần giữ **phân bố hoặc histogram gộp được**:

- p95 = giá trị mà khoảng 95% quan sát có latency không vượt quá, tùy phương pháp nội suy/ước lượng. Với các hệ đo khác nhau, cách tính percentile có thể khác.
- **Không lấy trung bình số p95 của từng phút để nhận p95 toàn khoảng.** Hai phút có số request khác nhau, phân bố khác nhau; “trung bình p95” không tương đương percentile của dữ liệu gộp.
- Khi gộp endpoint/instance, phải biết histogram được gộp như thế nào, bucket resolution và nhãn để không trộn request khác bản chất.
- Phân biệt metric của **successful requests** với tất cả completed requests; bỏ qua timeout có thể làm p99 trông đẹp giả tạo.
- Khi ít mẫu, p99 thường gần cực đại và dao động mạnh. Luôn lưu `count` cùng mọi percentile.

### 4.4 Lặp lại và mô tả dao động

Một lần chạy đẹp chưa chắc là baseline. Thu nhiều run độc lập ở điều kiện tương đương (ví dụ tối thiểu ba run như điểm bắt đầu thực hành, **không phải quy tắc thống kê phổ quát**). Giữa các run, có thể đổi thời điểm hoặc reset dữ liệu nếu kịch bản yêu cầu; phải ghi chính xác cách làm.

Đối với từng metric, lưu:

- Dữ liệu mỗi run và số mẫu, không chỉ một con số chung.
- Trung vị/độ trải giữa các run, phạm vi min-max hoặc khoảng phân vị thích hợp; giữ raw data để phân tích lại.
- Dấu hiệu trend và khả năng lệch do hot cache, JIT, tải nền, GC, CPU throttling.
- Cửa sổ loại trừ và **lý do được định nghĩa trước**; không loại run chỉ vì kết quả “xấu”.

Nếu hệ thống có biến động theo giờ, baseline theo giờ cao điểm và giờ thấp điểm hợp lý hơn tính một giá trị trung bình đánh mất các chu kỳ. Baseline phải được cập nhật có chủ đích khi công nghệ, tải hoặc kiến trúc thay đổi, kèm lịch sử và tiêu chí cập nhật.

## 5. Ghi điều kiện đo bằng manifest có thể đối chiếu lại

Tạo một bản ghi điều kiện riêng cho **mỗi run**, gắn run ID tới dữ liệu/recording/log. Dưới đây là **ví dụ minh họa giả định**, không phải cấu hình hay kết quả của một hệ thống đang tồn tại:

```yaml
baseline:
  baseline_id: "order-api-steady-50rps-v1"
  run_id: "order-api-steady-50rps-r03"
  status: "accepted"
  purpose: "So p95, throughput, CPU và GC giữa hai build"
  run_window_utc:
    warmup_start: "2026-10-28T09:00:00Z"
    measurement_start: "2026-10-28T09:10:00Z"
    measurement_end: "2026-10-28T09:20:00Z"
    sampling_interval_seconds: 10
  application:
    artifact: "order-api"
    commit: "a7b8c9d"
    image_digest: "sha256:example-digest-for-documentation"
    feature_flags_profile: "profile-A-v2"
    replica_count: 1
  runtime:
    java_vendor: "Example JDK distribution"
    java_version: "21"
    gc: "G1"
    heap_initial_mib: 512
    heap_max_mib: 512
    jvm_flags_profile: "jvm-flags-v3"
  infrastructure:
    environment: "isolated-load-test"
    container_cpu_limit_cores: 2
    container_memory_limit_mib: 1536
    host_type: "documented-test-vm"
  workload:
    script_version: "create-order-v4"
    model: "constant-arrival-rate"
    offered_rps_target: 50
    payload_profile: "small-order-v2"
    dataset_version: "seed-order-100k-v3"
    dependencies_profile: "db-and-cache-test-v2"
  collection:
    latency_scope: "end-to-end client observed, all completed"
    histogram_scheme: "latency-hist-v2"
    metrics_collector_version: "collector-v3"
    tracing_sample_probability: 0.1
    jfr_enabled: false
  quality_gate:
    requests_completed: 30000
    unexpected_infrastructure_incidents: 0
    collection_gap_seconds: 0
    notes: "Không deploy trong cửa sổ đo"
  artifacts:
    request_histogram: "run-r03-latency.hist"
    timeseries: "run-r03-metrics.json"
    environment_snapshot: "run-r03-environment.json"
```

**Cách sử dụng manifest:** giá trị như `commit`, `image_digest`, `jvm_flags_profile` và đường dẫn artifact phải được thay bằng dữ liệu thực của chính run; chuỗi `example-digest-for-documentation` trong ví dụ chỉ minh họa cấu trúc, không phải digest hợp lệ để triển khai. Khi triển khai thật, lưu hash/digest hợp lệ, dữ liệu gốc và quyền truy cập tương ứng. Nếu không đo được một trường, ghi rõ “không quan sát được” cùng tác động lên khả năng so sánh; đừng lặng lẽ coi nó là bằng nhau.

Ví dụ trên có cửa sổ đo 600 giây và mục tiêu 50 request/giây, nên **30.000 request hoàn thành** là con số chỉ hợp lý nếu thực tế throughput đạt mục tiêu, không có request còn tồn đọng hay lỗi đếm. Không dùng phép nhân này để “điền số đẹp”; `requests_completed` phải đến từ số liệu đo.

Bản ghi điều kiện cũng nên tham chiếu quyền truy cập JFR/GC log/tracing và thời hạn lưu. Với production, cần chú ý dữ liệu nhạy cảm trong log, request payload, JFR stack trace hoặc heap dump. Manifest có thể không lưu raw payload mà dùng tên profile và checksum dataset không chứa bí mật.

## 6. Thu bằng chứng trong JVM và môi trường chạy

Công cụ được chọn theo mục tiêu đo. Các lệnh dưới đây minh họa loại thông tin cần thu, không phải một script tự động áp dụng cho mọi máy.

### 6.1 Xác định Java runtime/flags đúng tiến trình

```bash
java -version
jcmd -l
```

`java -version` phản ánh lệnh `java` trong terminal đang chạy; nếu service dùng Java executable khác, kết quả đó **chưa đủ**. Từ danh sách process, xác định đúng PID rồi truy vấn, ví dụ với PID giả định `4242`:

```bash
jcmd 4242 VM.command_line
jcmd 4242 VM.flags
jcmd 4242 GC.heap_info
```

Công cụ `jcmd` thường sẵn trong JDK/HotSpot, nhưng container runtime tối giản có thể không cài; attach có thể bị cấm bởi quyền, PID namespace hoặc cấu hình JVM. `jcmd 4242 GC.heap_info` chỉ cho tình trạng ở thời điểm đọc, không thay thế chuỗi GC metrics. Khi so baseline A/B, đọc cả startup flags và **effective flags** nếu có; cùng `-Xmx` không đảm bảo cùng GC hay processor count.

### 6.2 Đối chiếu giới hạn từ OS/container

Trên Linux, chọn PID và cgroup của đúng tiến trình. Trong một môi trường cgroup v2 có đường dẫn được mount theo thông lệ, có thể tham khảo:

```bash
cat /proc/4242/status
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
```

Đây là lệnh ví dụ cho PID `4242` và cgroup tương ứng; nếu chạy từ host, container hoặc namespace khác, đường dẫn `/sys/fs/cgroup` không nhất thiết trỏ tới cgroup của service. Trên cgroup v1 và hệ điều hành khác, giao diện khác. Với `cpu.max`, hai giá trị quota/period biểu diễn giới hạn CPU, hoặc `max` nghĩa là không áp đặt quota ở cấp đó. Cũng nên lấy CPU throttling counters khi cần chứng minh thiếu CPU; chỉ nhìn CPU utilization chưa đủ.

Trước/sau benchmark, giữ ảnh chụp process/container resource limits để phát hiện một lần chạy vô tình bị đổi quota, số replica hay host. Metrics phải ghi đơn vị rõ ràng: bytes vs MiB, cores vs phần trăm một lõi, ms vs seconds.

### 6.3 Thu theo thứ tự giảm mức can thiệp

Tùy câu hỏi, có thể bắt đầu với application metrics, JMX/MXBeans, exporter và GC log vốn đã bật; tiếp tục bằng JFR với cấu hình kiểm soát; cuối cùng mới thu profiling hoặc dump nặng ở môi trường phù hợp.

Ví dụ, heap dump có thể lớn, chứa dữ liệu nhạy cảm và gây chi phí đáng kể; không nên mặc định chụp heap dump trong mọi phép đo baseline. NMT cần bật từ lúc JVM khởi động mới có số liệu tương ứng, đồng thời có overhead riêng. Nếu bật/tắt công cụ giữa các run, ghi rõ thay đổi này trong manifest và đánh giá liệu kết quả còn so được không.

## 7. Thực hành Java 17+: tính metric cho một cửa sổ mẫu

Ví dụ sau **tính số thống kê từ dữ liệu cố định**, không giả vờ đo được CPU hay độ trễ của production. Nó giúp thấy percentile phụ thuộc mẫu dữ liệu và phải đi kèm `count`, khoảng đo. Java 17+ có thể biên dịch/chạy trực tiếp.

Lưu thành tệp `BaselineWindowDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;

public class BaselineWindowDemo {
    static long percentileNearestRank(long[] sorted, int percentile) {
        if (sorted.length == 0 || percentile < 1 || percentile > 100) {
            throw new IllegalArgumentException("invalid percentile or empty data");
        }
        int rank = (int) Math.ceil(percentile / 100.0 * sorted.length);
        return sorted[rank - 1];
    }

    public static void main(String[] args) {
        long[] latencyMs = {8, 11, 11, 13, 17, 20, 26, 45, 90, 120};
        Arrays.sort(latencyMs);

        long completed = latencyMs.length;
        long errors = 0;
        double measurementSeconds = 2.0;

        System.out.println("count=" + completed);
        System.out.println("p50_ms=" + percentileNearestRank(latencyMs, 50));
        System.out.println("p95_ms=" + percentileNearestRank(latencyMs, 95));
        System.out.println("p99_ms=" + percentileNearestRank(latencyMs, 99));
        System.out.printf(Locale.ROOT, "throughput_rps=%.1f%n",
                completed / measurementSeconds);
        System.out.printf(Locale.ROOT, "error_rate_pct=%.2f%n",
                errors * 100.0 / completed);
    }
}
```

Biên dịch và chạy:

```bash
javac BaselineWindowDemo.java
java BaselineWindowDemo
```

Stdout **chính xác** với dữ liệu đã định:

```text
count=10
p50_ms=17
p95_ms=120
p99_ms=120
throughput_rps=5.0
error_rate_pct=0.00
```

**Giải thích:**

- Đây là phương pháp **nearest-rank**: sắp xếp tăng dần, vị trí của p95 là `ceil(0,95 × 10) = 10` nên giá trị là 120 ms. Một hệ thống khác có thể nội suy percentile hoặc dùng histogram xấp xỉ và cho kết quả khác.
- Chỉ có 10 quan sát nên p95 và p99 đều bằng giá trị lớn nhất. **Không dùng mười điểm này làm baseline p99 production**. Để so tail latency cần nhiều quan sát hơn, đủ thời lượng và phương pháp thống nhất.
- Throughput 5 request/giây tính trên **2 giây** là dữ liệu giả định minh họa. Việc đặt `measurementSeconds = 2.0` không khiến chương trình tự phát hay đo request trong 2 giây.
- Mã không thu thập thời gian bằng `System.nanoTime()`, không tách timeout khỏi successful request, không thu error từ hệ thống thật. Khi xây collector production, các sự kiện phải được ghi nhận và phân nhóm đúng, sau đó mới áp dụng thống kê.

Nếu cần đo duration cho một thao tác thật **trong cùng JVM**, có thể lấy hai mốc `System.nanoTime()` quanh phần việc đang quan sát rồi lấy hiệu. Tuy nhiên, một microbenchmark thủ công rất dễ sai vì JIT, dead-code elimination, GC, warm-up và nhiễu OS; với performance benchmark cấp phương thức, ưu tiên **JMH** và xây kịch bản có cách kiểm soát rõ. Baseline chẩn đoán service nên đo luồng request thực tế hoặc workload đại diện thay vì suy diễn từ một vòng lặp in ra console.

## 8. Đọc baseline nhiều lần và so sánh trước–sau

Giả sử ba lần đo ổn định, cùng profile tải, cho bộ số liệu **giả định** sau:

| Run | Completed requests | Throughput (req/s) | p95 latency (ms) | Error (%) | CPU process (cores trung bình) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 | 30.006 | 50,01 | 90 | 0,10 | 0,74 |
| A2 | 29.994 | 49,99 | 93 | 0,10 | 0,77 |
| A3 | 30.000 | 50,00 | 88 | 0,10 | 0,75 |

Số liệu trên được đặt ra để luyện cách đọc, **không phải dữ liệu thu từ Sheet hay máy nào**. Chỉ có thể xem ba run tương đương khi điều kiện và phương pháp đo thật sự giống nhau. Cửa sổ giả định mỗi run là 600 giây; throughput = completed/600. CPU “0,75 cores” khác cách diễn đạt “75% CPU” trên host nhiều lõi.

Trong ví dụ, median của **ba số p95 theo run** là 90 ms; đây là “trung vị các p95 của từng run”, **không phải p95 gộp của 90.000 request**. Nếu có histogram gốc, mới có thể tính p95 phân bố kết hợp theo đúng thuật toán. Nên giữ từng run để đọc biến động và tránh giấu khác biệt.

Một build B được đo dưới cùng điều kiện cho p95 117 ms trong ba run có tương quan về tải và tài nguyên. So với baseline đại diện 90 ms, chênh lệch tương đối là:

```text
Delta p95 (%) = (p95_B - p95_A) / p95_A * 100
              = (117 - 90) / 90 * 100
              = +30%
```

**Diễn giải đúng:** p95 được báo cao hơn 30% so với giá trị tham chiếu đã chọn. Chưa thể kết luận “code B gây chậm” nếu CPU quota, DB, dataset, time window, instrumentation hoặc cách gộp histogram đã thay đổi; cũng chưa xác lập độ tin cậy thống kê chỉ từ một lần B. Thay đổi cần được lặp lại hoặc đối chiếu với độ dao động của baseline và bằng chứng ở các tầng liên quan.

### Quy tắc so sánh có thể kiểm chứng

1. **So đúng đại lượng:** cùng tên metric, đơn vị, nhãn endpoint, định nghĩa lỗi, percentile estimator/histogram, thời lượng cửa sổ.
2. **So đúng điều kiện:** version, workload, data, heap/GC, CPU/memory limits, dependencies, collector. Với điều kiện khác, ghi điều kiện nào là biến thử nghiệm và điều kiện nào là yếu tố gây nhiễu.
3. **So sự phân bố:** p50, p95, p99, max, error/timeout và count; đừng chọn riêng một percentile “đẹp”.
4. **So qua nhiều run:** khác biệt có vượt dao động thường thấy không, xuất hiện lặp lại không, có tương ứng với GC/CPU/IO/queue tăng không.
5. **Giữ dấu vết quyết định:** kết luận, evidence link, run IDs, phương pháp và giới hạn; baseline không phải một con số tự động cập nhật không có lịch sử.

## 9. Các tình huống đặc thù của Java dễ làm baseline sai lệch

### 9.1 JVM chưa warm-up / JIT thay đổi

Ứng dụng Java khởi chạy có class loading, lazy initialization, cache fill và JIT compilation. Với workload biến thiên, các đoạn mã nóng ở lần đo này chưa chắc giống lần đo khác. Do đó ghi startup time, warm-up profile và chỉ bắt đầu steady-state theo điều kiện đã định trước. Nếu mục tiêu là cold-start latency, phải đo cold-start **như một scenario riêng**.

### 9.2 GC và heap không giống nhưng chỉ nhìn throughput

Hai build có cùng throughput nhưng một build dùng allocation rate cao, pause GC dài hoặc RSS gần giới hạn container có thể mang rủi ro khác nhau. Ghi GC algorithm, heap settings, pause distribution, used/committed heap và resource limits. Một lần GC dài tình cờ ngoài cửa sổ đo có thể làm baseline thiếu đại diện; cần đủ thời gian và nhiều run.

### 9.3 CPU throttling / host contention

Cùng “2 cores” trên hai môi trường có thể khác CPU microarchitecture, virtualization, noisy neighbor, affinity, quota và scheduling. Nếu một run liên tục bị throttling còn run kia không, không thể quy toàn bộ khác biệt cho code. Nên ghi giới hạn và các counter throttling cùng lúc với latency, nhất là với container/Kubernetes.

### 9.4 Cache, dataset và phụ thuộc ngoài JVM

Một đợt chạy có cache nóng và một đợt cache lạnh không tương đương. Thêm index DB, thay số bản ghi hoặc thay data distribution cũng có thể đổi query plan và latency. Giữ dataset snapshot/seed hoặc khai báo rõ trạng thái cache/dependency; khi dữ liệu production thay đổi tự nhiên, xây baseline theo nhóm điều kiện thay vì coi nó cố định.

### 9.5 Quan sát làm thay đổi hệ thống

Bật debug logging, stack sampling liên tục, Java agent, native profiler hoặc JFR cấu hình nặng đều có thể thêm overhead. Để so trước/sau, giữ cách đo nhất quán; nếu cần profiling chuyên sâu để tìm nguyên nhân, đánh dấu run đó là **diagnostic profile** và tránh trộn vào baseline không profiler.

### 9.6 Số liệu mất mẫu, reset và percentile thiếu yêu cầu

Scrape hụt, exporter restart, counter reset hoặc drop spans do sampling có thể phá tính liên tục. Một p99 khi chỉ có vài chục request không đại diện tail latency; histogram bucket quá thô không đủ độ phân giải. Luôn đọc count, histogram coverage và health của pipeline quan sát trước khi tin biểu đồ.

## 10. Lỗi phổ biến và cách tự kiểm tra

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lấy một điểm CPU làm “mốc bình thường” | Không có workload, scope và biến thiên theo thời gian | Ghi run window, request rate, CPU theo process/cgroup và lặp lại |
| So p95 từ endpoint khác hoặc cửa sổ khác | Khác phân bố request, cách tính và sample count | Giữ nhãn, cửa sổ, histogram algorithm và số mẫu |
| Gộp p95 bằng trung bình đơn giản | Percentile không cộng/trung bình như count | Gộp raw observations hoặc histogram tương thích |
| Không ghi JDK/GC/flags | Runtime có thể thay đổi latency và memory | Lưu runtime identity, startup/effective flags, GC và heap |
| Gọi “host rảnh” là “container không thiếu CPU” | Quota và throttling độc lập với mức CPU còn dư của host | Đo cgroup quotas và throttling cạnh process CPU |
| Trộn warm-up và steady-state | Chứa class loading/JIT/cache fill khác mục tiêu | Định nghĩa riêng từng pha và cửa sổ |
| Đổi tool đo giữa A và B | Overhead và semantics có thể khác | Giữ collection profile; ghi rõ mọi thay đổi |
| Coi baseline là SLO | Hiện trạng ổn định vẫn có thể kém chất lượng | Đánh giá baseline với mục tiêu nghiệp vụ riêng |
| Xóa run xấu mà không ghi lý do | Tạo thiên lệch lựa chọn kết quả | Định nghĩa tiêu chí loại trừ trước, giữ audit trail |
| Không lưu dữ liệu gốc hoặc manifest | Không thể kiểm lại kết luận khi metric thay đổi | Lưu run ID, dữ liệu, điều kiện, cách tính và phiên bản tool |

Có thể tự thực hiện một “mini-baseline” an toàn cho một service Java:

1. Chọn một request path, một mức tải và một định nghĩa latency rõ ràng.
2. Ghi bản build, JDK/GC/flags, CPU/memory limit, dataset, dependency, tool đo và thời gian UTC.
3. Tách warm-up với 5–10 phút đo *nếu kịch bản và tốc độ request phù hợp*; thời lượng thực tế phải do yêu cầu độ tin cậy và chu kỳ GC/tải quyết định, không coi 5–10 phút là chuẩn chung.
4. Thu per-request histogram/count/errors, throughput, queue, JVM GC/heap và process/container CPU, memory; giữ các cửa sổ đồng bộ.
5. Lặp lại trên cùng profile, lưu raw data và ghi nhận mức dao động.
6. Khi có dấu hiệu khác baseline, đối chiếu những biến đã thay đổi trước khi kết luận nguyên nhân.

## 11. Checklist chấp nhận một baseline để chẩn đoán

- [ ] **Danh tính:** đúng service, build/commit, runtime/JVM, process/container/host và run ID.
- [ ] **Điều kiện:** workload, payload, offered load, dataset, dependencies, flags, quota/limits và profile đo được mô tả.
- [ ] **Trạng thái:** cold start/warm-up/steady-state/peak tách rõ; cửa sổ chính thức có timestamp UTC.
- [ ] **Số đo:** đơn vị, nguồn, scope, mẫu số, sample count, sampling interval và percentile method đã xác định.
- [ ] **Độ tin cậy:** không có missing data nghiêm trọng, counter reset được xử lý, run bị loại có lý do.
- [ ] **Biến thiên:** có số liệu nhiều run hoặc nêu rõ hạn chế khi chưa đủ lặp lại.
- [ ] **Đối chiếu:** đủ bằng chứng ứng dụng + JVM + OS/container để phát hiện yếu tố gây nhiễu quan trọng.
- [ ] **Lưu trữ:** manifest, raw data/histogram, recording/log cần thiết và kết luận được gắn với cùng run ID.
- [ ] **Giới hạn:** baseline được mô tả như hiện trạng ở điều kiện đã đo; SLO/threshold là quyết định riêng.

**Kết luận:** Một baseline đáng tin là **một tập kết quả có thể tái hiện dưới điều kiện được ghi rõ**. Trong Java runtime diagnostics, phải đồng thời kiểm soát workload, trạng thái JVM (warm-up/JIT/GC), tài nguyên OS/container và cách thu metric. Chỉ sau đó mới có cơ sở nói một lần đo mới “khác bình thường” ở đâu, khác bao nhiêu và liệu khác biệt ấy có đủ bằng chứng để điều tra sâu.