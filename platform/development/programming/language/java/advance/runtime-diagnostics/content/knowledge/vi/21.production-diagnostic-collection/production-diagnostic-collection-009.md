# 21.9. Xác nhận phục hồi, so sánh với mốc bình thường và lưu kết luận có căn cứ

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **đã giảm tác động (mitigated)**, **dịch vụ đã phục hồi (recovered)**, **nguyên nhân gốc đã sửa (root cause fixed)** và **incident đã được đóng theo quy trình (closed)**.
- Xác lập **mốc bình thường (baseline)** phù hợp để so sánh với giai đoạn sự cố và giai đoạn sau khi xử lý, không nhầm “alert hết đỏ” với “mọi chức năng đã trở lại bình thường”.
- Kiểm tra đồng thời **tác động người dùng, error rate, latency p95/p99, traffic/throughput, saturation, Java CPU/GC/heap/native memory, thread/I/O**, và sức khỏe của dependency.
- Dùng các công cụ Java như **JFR, JDK Mission Control (JMC), `jcmd`, `jfr`**, kết hợp log, tracing và metrics để bổ sung bằng chứng giải thích hiện tượng.
- Xây dựng một **recovery gate** có nhiều cửa sổ quan sát, điều kiện tải so sánh được và ngưỡng được định nghĩa trước.
- Lưu một kết luận có căn cứ: nêu **thời điểm, phạm vi, điều đã làm, số liệu trước/sau, dẫn chứng, độ tin cậy, giới hạn và follow-up**; không biến giả thuyết thành sự thật đã được chứng minh.

**Ngữ cảnh:** Java 17+ trong vận hành ứng dụng/JVM. Tên công cụ và câu lệnh có thể phụ thuộc JDK/OS; không chạy lệnh chẩn đoán nặng trên production khi chưa cân nhắc tác động. Những ngưỡng trong ví dụ chỉ là **dữ liệu minh họa**, không phải SLO chung cho mọi hệ thống.

## 1. “Đã phục hồi” thực sự nghĩa là gì?

Trong một incident, sửa một cấu hình, rollback hoặc restart JVM mới chỉ là **hành động**. Sự kiện “triển khai thành công” là tín hiệu của hệ thống deployment; nó **chưa phải** bằng chứng rằng khách hàng đã hết lỗi.

| Trạng thái | Cách diễn đạt chính xác | Bằng chứng tối thiểu cần có |
|---|---|---|
| **Đang bị ảnh hưởng** | Người dùng/luồng xử lý vẫn gặp lỗi, chậm hoặc sai kết quả | SLI, lỗi theo request, kết quả kiểm thử chức năng hoặc dữ liệu người dùng |
| **Đã giảm tác động (mitigated)** | Biện pháp tạm đã giảm/hạn chế ảnh hưởng, nhưng vẫn có rủi ro | Đường traffic bị ảnh hưởng giảm, tỷ lệ lỗi giảm, impact được khoanh vùng |
| **Đã phục hồi (recovered)** | Dịch vụ đáp ứng tiêu chí hoạt động đã xác định trong **khoảng quan sát đủ dài**, dưới tải đại diện | Tỷ lệ lỗi, latency, traffic, chức năng, resource guardrails và dependency ổn định |
| **Nguyên nhân gốc đã được sửa** | Thay đổi giải quyết cơ chế tạo lỗi và qua kiểm thử phù hợp | Test tái hiện lỗi cũ không còn, tương quan mã/cấu hình và bằng chứng xác minh |
| **Incident đã đóng** | Người có trách nhiệm đồng ý kết thúc ứng cứu, thông báo trạng thái, còn follow-up được quản lý | Quyết định, thời điểm, người xác nhận, bằng chứng và các action items |

Các trạng thái **không nhất thiết xảy ra cùng lúc**. Ví dụ rollout bị lỗi được rollback để khôi phục dịch vụ, trong khi bug code chưa được sửa. Khi đó có thể báo **“dịch vụ đã phục hồi nhờ rollback; root cause đang điều tra”**, không được báo “đã sửa xong lỗi” chỉ vì khách hàng hết gặp vấn đề.

Một restart JVM làm CPU giảm hoặc heap used giảm **không chứng minh memory leak đã hết**. Với leak cần quan sát một thời gian hoặc đủ chu kỳ workload để biết slope sau warm-up có trở lại mức bình thường không.

## 2. Xác lập baseline có thể so sánh

**Baseline** là tập dữ liệu của một trạng thái hoạt động được biết là **bình thường và đại diện**, thường lấy từ khoảng thời gian trước incident, cùng service và điều kiện tương tự. Nó không phải một con số bất biến trong mọi hoàn cảnh.

### 2.1. Chọn mốc theo tính tương đương, không theo tính tiện lợi

Khi chọn **before / during / after**, ghi rõ:

- **Service, endpoint, operation, tenant/region** nào; không lấy trung bình toàn cluster làm che giấu một nhóm người dùng lỗi.
- **Khối lượng traffic** và hình dạng workload: requests/second, concurrency, batch size, payload size, read/write mix, cache hit rate.
- **Mốc thời gian** (UTC), độ dài cửa sổ, ngày trong tuần/mùa vụ, giờ cao điểm/thấp điểm, thời điểm batch/scheduler.
- **Phiên bản application, JDK, GC, flags, cấu hình, số instance, giới hạn CPU/memory**, vùng chạy và những dependency liên quan.
- **Chất lượng dữ liệu**: đủ mẫu, exporter đang chạy, không mất scrape interval, metrics lag, counter reset, dashboard query không thay đổi.

Ví dụ, so p99 của hệ thống lúc **100 RPS** trước incident với p99 lúc **10 RPS** sau khi cắt 90% traffic là so sánh **không cùng điều kiện**. Một “phục hồi” như vậy có thể chỉ là bớt tải hoặc bỏ rơi người dùng. Cần kiểm tra cả **served traffic, rejected traffic và success traffic**, không chỉ latency của request được phục vụ.

Không phải baseline nào cũng phải giống tuyệt đối. Nếu tải có thay đổi tự nhiên, dùng **đường biên chấp nhận được** hoặc chia theo traffic bucket; ghi rõ biến số nào khác và vì sao vẫn có thể kết luận ở mức nào. Nếu không có baseline đáng tin, ghi “**baseline unavailable**” và dùng **SLO/SLI + historical range + kiểm thử chức năng** làm cơ sở thay thế, đồng thời nêu giới hạn.

### 2.2. Ba cửa sổ tối thiểu

Một khung quan sát:

```text
UTC time ------------------------------------------------------------>
        A: BASELINE     B: INCIDENT     [change]    C: RECOVERY 1  D: RECOVERY 2
        known-good      impact          rollback    observe        observe
        metrics/JFR     metrics/JFR      action      without       recurrence?
                                                   major action
```

Các cửa sổ phải được đánh dấu theo **cùng timezone, cùng phạm vi hệ thống và cùng định nghĩa metric**. Chọn độ dài dựa trên thời gian phát hiện sự cố, nhịp tải, latency/GC cycle, thời gian đồng bộ dữ liệu và nguy cơ tái phát; không lấy “2 phút xanh” làm chuẩn tuyệt đối cho mọi loại incident.

Không sửa, tổng hợp hoặc xóa dữ liệu gốc để “vẽ đường phục hồi”. Hãy giữ query, timestamp, metric label và liên kết dashboard ở dạng có thể mở lại.

## 3. Những chỉ số nào thực sự xác nhận phục hồi?

Tổ chức bằng các nhóm **triệu chứng người dùng, nguyên nhân/guardrail hệ thống và chất lượng bằng chứng**.

| Nhóm kiểm tra | Chỉ số/câu hỏi | Điều kiện phục hồi cần đối chiếu |
|---|---|---|
| **Lỗi từ góc nhìn khách hàng** | Request error rate, timeout, HTTP 5xx, failed payments, dữ liệu sai, retry exhaustion | Trở lại SLO/biên bình thường của **những tác vụ bị ảnh hưởng**; kiểm thử luồng nghiệp vụ |
| **Latency** | p50, p95, **p99**, deadline miss, queue wait; histogram đúng scope | Đạt SLO trong cùng endpoint/traffic mix; không chỉ average latency |
| **Traffic và throughput** | Incoming QPS, accepted vs served requests, successful ops/s, retry count | Lượng công việc được xử lý thực sự đã trở lại; không “xanh” vì ngừng nhận request |
| **Capacity/saturation** | CPU per instance và per request, run queue, thread pool, queue depth, active connections | Không còn bão hòa, backlog giảm bền vững, có headroom đủ dự kiến |
| **GC/heap** | GC pause, collection frequency, allocation rate, old-gen after GC, committed/used | Không còn nguyên nhân GC bất thường, không có slope tăng nguy hiểm sau warm-up |
| **Native/container memory** | RSS, cgroup `memory.current`, `memory.events`, memory limit, OOM restarts | Không còn tăng đến limit hay phát sinh OOM; không nhầm RSS với Java heap used |
| **Locks/threads/I/O** | Blocked/waited threads, JVM thread pool, file/socket I/O latency | Lock contention / I/O bottleneck đã về mức chấp nhận được |
| **Dependencies và correctness** | DB latency, connection pool, downstream error, cache, consistency, data backlog | Không chuyển lỗi từ service này sang service khác; dữ liệu sau incident được xử lý |
| **Observability** | Collector/scrape healthy, sample count, query coverage, clock sync | Bằng chứng đủ mới và đủ độ bao phủ để tin rằng trạng thái xanh có ý nghĩa |

**Quan trọng:** Không có một “green indicator” tự động thay toàn bộ điều kiện. Recovery criteria phải được chọn trước hoặc được thống nhất trong incident cho **chính tác động đang xảy ra**. Đối với incident đọc dữ liệu sai, HTTP 200 và latency nhanh vẫn **không** chứng minh phục hồi nếu dữ liệu trả về còn sai.

### Ba lớp bằng chứng

1. **Primary/user-facing evidence:** SLI/SLO và tác vụ người dùng — trả lời *người dùng còn bị ảnh hưởng không?*
2. **Supporting/runtime evidence:** CPU, GC, memory, queue, JFR, thread/I/O — trả lời *JVM có trở lại trạng thái vận hành khỏe không?*
3. **Change/causal evidence:** timeline, diff config/deploy, test tái hiện, repro/rollback — trả lời *biện pháp có liên hệ hợp lý tới sự thay đổi được quan sát không?*

Ưu tiên lớp 1 để tuyên bố service recovered. Lớp 2 giúp loại trừ nguy cơ tiềm ẩn và lớp 3 giúp kết luận/điều tra root cause. Khi thiếu một lớp, ghi rõ sự thiếu hụt.

## 4. Quy trình xác nhận phục hồi theo bảy bước

### Bước 1 — Khóa phạm vi và dấu mốc thời gian

Ghi incident ID, người điều phối/owner, môi trường, region, application/JDK version, bản deploy và **UTC start/detection/mitigation/end**. Phân tách **thời điểm hành động** (rollback lúc 10:42) với **thời điểm SLI phục hồi** (error rate bình thường từ 10:47); hai thời điểm không đương nhiên trùng nhau.

Đối với rolling deployment, thêm tỷ lệ traffic chạy bản cũ/mới; khi phục hồi chưa được rollout đến hết fleet, **chưa nên khẳng định toàn hệ thống recovered**.

### Bước 2 — Gắn triệu chứng với tiêu chí qua ngưỡng

Viết trước những gì phải đạt, ví dụ trong một service giả lập:

- Request error rate ≤ **0,1%** trong các cửa sổ đã thống nhất.
- p99 request latency ≤ **250 ms**, tính từ histogram đúng endpoint và không trộn nhầm percentile.
- Served traffic trong khoảng đại diện so với baseline **±10%** (đây là điều kiện so sánh của ví dụ, không phải SLO phổ quát).
- JVM CPU ≤ 75% mức tài nguyên đo nhất quán, container RSS không vượt vùng an toàn.
- Kiểm tra nghiệp vụ đặc thù và **ít nhất hai cửa sổ liên tiếp**; thời lượng tùy SLO, cycle của workload và đánh giá on-call.

Không lén chỉnh ngưỡng sau khi xem số liệu chỉ để nhận dấu PASS. Nếu tiêu chí thay đổi vì workload chính đáng, phải **ghi lại quyết định, lý do và người chấp thuận**.

### Bước 3 — Kiểm chứng tác động đã giảm trên luồng người dùng

Thực hiện synthetic checks có kiểm soát, đọc dashboard SLI, và xác nhận tình trạng thực tế của endpoint/operation từng bị ảnh hưởng. Đối với async systems, còn phải kiểm tra **backlog, dead-letter queue, duplicate processing, delayed jobs**; request HTTP ngoài cùng đã trả về 200 nhưng processing phía sau còn lỗi thì chưa phục hồi đầy đủ.

Nếu incident ảnh hưởng dữ liệu, kiểm tra **integrity/consistency**, nhu cầu reconciliation/replay; đừng gọi recovered chỉ dựa vào CPU thấp và log lỗi đã tắt.

### Bước 4 — Quan sát ổn định qua thời gian

Dùng ít nhất một khoảng đủ để phản ánh chu kỳ lỗi: GC cycle, cache reload, cron, queue drain, TTL, connection rotation hoặc peak load. Khẳng định “đã phục hồi” ở cấp độ đã xác minh, đồng thời giữ theo dõi mạnh hơn cho lỗi có nguy cơ tái phát theo chu kỳ dài.

**Không có một độ dài phổ quát**. Nếu memory leak chỉ bộc lộ sau 6 giờ, hai cửa sổ 10 phút chưa loại trừ được leak. Nếu thao tác đã kéo dài hàng ngày, cần chọn giám sát sau incident và có người chịu trách nhiệm.

### Bước 5 — So sánh baseline / incident / recovery trong cùng điều kiện

Dùng bảng với đơn vị và khoảng đo rõ ràng. Khi nhìn thấy “CPU giảm 95% xuống 40%”, hỏi traffic hoặc instance count có giảm/mở rộng không. Nếu lượng request tăng gấp đôi hoặc scale từ 2 lên 8 JVM, CPU per instance có thể giảm dù tổng CPU cost/operation vẫn cao.

Khi traffic thay đổi, dùng metric chuẩn hóa như CPU-seconds per successful operation hoặc **GC pause time trên một đơn vị wall time** (đúng định nghĩa), trong chừng mực collector và dữ liệu hỗ trợ. Không lấy CPU%/RPS như công thức chính xác cho mọi workload khi CPU% từ nhiều core/containers khác nhau.

### Bước 6 — Kiểm tra regression và khả năng rollback an toàn

Sau canary/rollback/fix, xác nhận các luồng:

- Request bình thường, lỗi input, timeout và retry.
- Đường cache hit/miss, batch hay peak path từng kích hoạt sự cố.
- Các region/tenant/endpoint bị ảnh hưởng; không chỉ một synthetic endpoint dễ.
- DB/cache/queue và service phụ thuộc.
- Data correctness/side effects, schema compatibility, hoạt động async sau restart.

Nếu một guardrail thất bại hoặc xuất hiện regression mới, **không đóng incident vội**; áp dụng kế hoạch phản hồi/rollback theo quyền hạn, tiếp tục thu evidence.

### Bước 7 — Kết luận có giới hạn và bàn giao follow-up

Ghi rõ: “Từ 11:10–11:30 UTC, hai cửa sổ 10 phút đều đạt tiêu chí ..., với 99–101 RPS so baseline 100 RPS. Service recovered ở scope X. Chưa chứng minh root cause Y; theo dõi tiếp 24 giờ để bắt chu kỳ Z.”

Đây là **mẫu diễn đạt**, chỉ dùng khi số liệu thực phù hợp. Phân công owner điều tra root cause và follow-up; ghi trạng thái incident theo quy trình tổ chức, không tự chuyển “recovered” thành “root cause fixed”.

## 5. Đo và so sánh đúng: công thức, đơn vị, dữ liệu thiếu

### 5.1. Error rate và throughput

Trong một cửa sổ xác định:

```text
Error rate (%) = 100 × số request thất bại / tổng request đủ điều kiện
Throughput      = số operation thành công / số giây của cửa sổ
Incoming RPS    = số request đến / số giây của cửa sổ
```

**Mẫu số phải phù hợp SLI**: không tự tính failed background jobs trên tổng HTTP health checks. Nếu có request bị chặn trước khi vào ứng dụng (ingress, LB, CDN), metrics chỉ từ JVM có thể **không thấy toàn bộ request thất bại**. Cần đối chiếu edge/LB, service và dependency.

Khi metrics là **cumulative counter**, lấy hiệu giữa đầu/cuối cửa sổ, dùng `rate/increase` phù hợp của hệ thống metrics và xử lý **counter reset sau JVM restart**. Không lấy hiệu âm hay tổng counter của bản cũ với bản mới như thể cùng process liên tục. Kiểm tra timestamp và sampling delay.

### 5.2. Percentile latency: đừng trung bình hai số p99

p95/p99 là **phân vị trên tập request**. Không thể tính p99 của 20 phút bằng cách lấy trung bình hai p99 của hai cửa sổ 10 phút. Cần histogram hoặc distribution gốc và phương pháp aggregation đúng.

Cũng không lấy trung bình p99 của một endpoint nhanh với một endpoint chậm rồi gọi đó là p99 hệ thống. Khi request mix thay đổi, p99 tổng thể có thể đẹp hơn dù một endpoint chiến lược vẫn lỗi. Theo dõi **per endpoint/status/region** và ưu tiên những SLI thể hiện tác động người dùng.

### 5.3. Resource metrics không giống nhau

- **JVM heap used** đo vùng heap đang dùng tại thời điểm đo, không phải RSS; heap committed khác reserved/max.
- **RSS** là bộ nhớ vật lý resident ở mức process, gồm nhiều nguồn ngoài Java heap.
- **Cgroup memory.current** là sử dụng memory theo cgroup và có thể bao gồm các phần mà process RSS không phản ánh trực tiếp.
- **GC collection count/time** là counters, có thể reset khi restart JVM; `getCollectionTime()` chỉ xấp xỉ, và một số collector trả `-1`.
- CPU user/system, percent per process và CPU-quota container có thể dùng **mẫu số khác nhau**. Ghi rõ cách tính.

Không xác nhận “memory leak đã sửa” chỉ vì heap thấp ngay sau restart; hãy so **old-gen after GC/retained objects/slope** trong workload tương đương và kiểm tra vòng đời đủ dài.

### 5.4. Thiếu mẫu và khác điều kiện

Một bảng so sánh có 0 lỗi khi chỉ có **5 request** không bằng một bảng 0 lỗi khi có **50.000 request**. Bảo đảm denominator đủ lớn so với ngưỡng mong muốn và độ tin cậy kỳ vọng. Không dùng số 0 như bằng chứng “không còn lỗi” nếu metrics exporter đã mất kết nối hoặc traffic không có.

Khi thiếu baseline, missing metric, JFR không có event, dashboard query không bao phủ scope, hãy báo **“chưa đủ bằng chứng”**, ghi nguồn thay thế và việc phải làm để hoàn thiện. Không điền số “0” thay `NA`/missing.

## 6. Java runtime-diagnostics trong bước xác nhận

### 6.1. Dùng JFR đúng vai trò

JFR cung cấp **dữ liệu event đã được cấu hình ghi**, không thay thế user-facing SLI. Nếu ứng dụng đã có baseline JFR và incident JFR:

1. Kiểm tra recording có đúng JVM/app/version/period, **event settings**, duration và scope tương đương không.
2. Xem event như `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.GarbageCollection`, allocation, monitor/lock, file/socket I/O khi có trong file.
3. Dùng JMC để chọn **cùng time range** hoặc workload phase, xem CPU/method profiling, Memory/GC, Threads/Locks, I/O.
4. Kiểm tra số lượng event và threshold/sampling; không có event **không chứng minh** hiện tượng không xảy ra.
5. Đối chiếu với dashboard ứng dụng và OS/container. Một GC pause giảm không bảo đảm checkout thành công.

Ví dụ CLI với **file đã tồn tại**:

```bash
jfr summary before.jfr
jfr summary after.jfr

jfr print --events jdk.GarbageCollection before.jfr
jfr print --events jdk.GarbageCollection after.jfr
```

Hai file chỉ so được nếu **bao phủ pha workload có ý nghĩa** và được ghi với cấu hình đủ tương đồng. `jfr summary` xác nhận type/count và dung lượng; count không chuẩn hóa theo duration/traffic sẽ dễ gây kết luận sai. `jfr print` có thể rất dài, nên dùng JMC/luồng phân tích phù hợp thay vì đổ tất cả output vào incident chat.

### 6.2. Thu recording sau khắc phục trên JVM đang chạy

Nếu chưa có recording, dùng `jcmd` trong môi trường được phép:

```bash
jcmd -l
jcmd <PID> JFR.start name=RecoveryCheck settings=profile duration=60s filename=recovery.jfr
jcmd <PID> JFR.check
```

**Thay `<PID>` bằng PID thật** và bảo đảm có quyền attach. `jcmd` thường cần chạy cùng máy và phù hợp quyền user. `settings=profile` có thể tăng overhead so với `default`; chọn dựa trên mục đích, không nhất thiết profile mọi production JVM.

Sau khi recording có thời lượng kết thúc, kiểm tra `recovery.jfr` bằng `jfr summary` và mở trong JMC. Nếu cần snapshot từ recording đang chạy, dùng `JFR.dump`; dump **không tự dừng recording**. Đừng khẳng định so sánh được baseline JFR **khi không có file trước sự cố**; trong trường hợp này, so metrics/logs lịch sử và nói rõ phạm vi của JFR chỉ sau fix.

### 6.3. Khi cần bổ sung nhanh thông tin JVM

```bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print -l
```

Các lệnh là **gợi ý chẩn đoán**, không phải phép kiểm tra luôn cần chạy. `GC.heap_info` chỉ là snapshot; `Thread.print -l` có tác động phụ thuộc số lượng thread; đừng spam chúng trong vòng lặp. Một vài command có tên/tác động khác giữa JDK implementations; kiểm tra `jcmd <PID> help` khi nghi ngờ.

Nếu có JVM restart/rollout, ghi **PID, start time, build version, flags** cho cả trước/sau. Cùng hostname không có nghĩa cùng instance, và đổi `-Xmx`/GC type đồng thời với thay application code là **confounder** khi suy diễn nguyên nhân.

## 7. Ví dụ Java 17+ runnable: recovery gate có kiểm tra tải và hai cửa sổ

Đây là một bài thực hành **không kết nối production**, dùng dữ liệu mô phỏng để minh họa cách **không xác nhận phục hồi chỉ vì một metric xanh**. Chương trình xem bốn cửa sổ 600 giây: baseline, incident, recovery-1, recovery-2; tính RPS, error rate và áp dụng guardrails.

**Tiêu chí minh họa**, không phải chuẩn SLO chung:

- Mỗi recovery window có ít nhất 1.000 request; RPS sai khác so baseline không quá 10%.
- Error rate ≤ 0,10%; p99 ≤ 250 ms.
- CPU đo theo **cùng quy ước** ≤ 75%.
- RSS ≤ 120% baseline (chỉ làm cảnh báo tăng memory, **không chứng minh leak không tồn tại**).
- Cả **hai** recovery windows phải đạt.

### 7.1. Mã hoàn chỉnh

Tạo tệp **`RecoveryGateDemo.java`**:

```java
import java.util.Locale;

public class RecoveryGateDemo {
    record Window(String name, int seconds, long requests, long failures,
                  int p99Ms, int cpuPercent, int rssMiB) {
        double rps() { return requests / (double) seconds; }
        double errorPercent() { return failures * 100.0 / requests; }
    }

    static boolean healthy(Window w, Window baseline) {
        double loadDifference = Math.abs(w.rps() - baseline.rps())
                / baseline.rps();
        return w.requests >= 1000
                && loadDifference <= 0.10
                && w.errorPercent() <= 0.10
                && w.p99Ms() <= 250
                && w.cpuPercent() <= 75
                && w.rssMiB() <= baseline.rssMiB() * 1.20;
    }

    static void print(Window w) {
        System.out.printf(Locale.ROOT,
                "%s: rps=%.1f error=%.3f%% p99=%dms cpu=%d%% rss=%dMiB%n",
                w.name(), w.rps(), w.errorPercent(), w.p99Ms(),
                w.cpuPercent(), w.rssMiB());
    }

    public static void main(String[] args) {
        Window baseline = new Window("baseline", 600, 60000, 6, 140, 42, 512);
        Window incident = new Window("incident", 600, 54000, 2160, 1200, 95, 710);
        Window recovery1 = new Window("recovery-1", 600, 59400, 6, 155, 47, 535);
        Window recovery2 = new Window("recovery-2", 600, 60600, 3, 148, 45, 530);

        print(baseline);
        print(incident);
        print(recovery1);
        print(recovery2);
        System.out.println("Incident healthy: " + healthy(incident, baseline));
        System.out.println("Recovery window 1 healthy: " + healthy(recovery1, baseline));
        System.out.println("Recovery window 2 healthy: " + healthy(recovery2, baseline));
        System.out.println("Two-window recovery confirmed: "
                + (healthy(recovery1, baseline) && healthy(recovery2, baseline)));
    }
}
```

### 7.2. Biên dịch và chạy

```bash
javac --release 17 RecoveryGateDemo.java
java RecoveryGateDemo
```

**Stdout chính xác** khi chạy chương trình với dữ liệu mô phỏng:

```text
baseline: rps=100.0 error=0.010% p99=140ms cpu=42% rss=512MiB
incident: rps=90.0 error=4.000% p99=1200ms cpu=95% rss=710MiB
recovery-1: rps=99.0 error=0.010% p99=155ms cpu=47% rss=535MiB
recovery-2: rps=101.0 error=0.005% p99=148ms cpu=45% rss=530MiB
Incident healthy: false
Recovery window 1 healthy: true
Recovery window 2 healthy: true
Two-window recovery confirmed: true
```

Ví dụ đã được **biên dịch `javac --release 17` và chạy thực tế**. Chỉ dữ liệu giả lập tạo output này; không có kết nối JVM live, không tự lấy metrics và không kết luận bất kỳ service thực nào đã phục hồi.

### 7.3. Đọc kết quả một cách đúng đắn

- Baseline 60.000 requests/600 s = **100 RPS**; incident 54.000/600 = **90 RPS** nhưng error rate tăng **4%** và p99 thành **1.200 ms**.
- Recovery-1 có 99 RPS, 6 lỗi/59.400 requests ≈ **0,010%**, p99 **155 ms**, CPU **47%** và RSS **535 MiB**, qua các guardrails giả lập.
- Recovery-2 có 101 RPS, 3 lỗi/60.600 requests ≈ **0,005%**, p99 **148 ms**, CPU **45%** và RSS **530 MiB**.
- p99 recovery-1 (**155 ms**) vẫn cao hơn baseline (**140 ms**) khoảng **10,7%**; recovery không nhất thiết trả từng con số **chính xác** bằng baseline nếu SLO và vùng an toàn cho phép.
- Hai cửa sổ giả lập đều đạt nên chương trình in `true`; điều này **chỉ chứng minh predicate trong ví dụ**, chưa xác minh traffic mix, user journey, data correctness, dependency, observability freshness, tính liên tục của thời gian hay leak lộ sau vài giờ.

**Hạn chế kỹ thuật của ví dụ:** `Window` không kiểm tra timestamp hay cửa sổ có liên tiếp thật không; payload được viết sẵn. Trong sản phẩm thật, đầu vào phải lấy từ hệ thống metrics đáng tin, có time range, labels, units và sample counts; kiểm tra cửa sổ không overlap/không bị missing data, và không tính p99 từ trung bình các p99 riêng lẻ.

### 7.4. Bài tập với chương trình

1. Đổi `recovery2` thành p99 **380 ms**. Recovery 2 và kết quả hai cửa sổ phải chuyển sang `false`.
2. Đổi `recovery1` thành `requests=600`. Dù error rate có thể thấp, ngưỡng tối thiểu số request phải chặn kết luận.
3. Đổi `recovery1` thành 20 RPS tương đương 12.000 requests/600s và latency rất đẹp: check **loadDifference** phải không đạt.
4. Bỏ condition RSS, rồi nhận xét vì sao recovery gate yếu hơn khi incident là memory leak; sau đó bổ sung **slope/old-gen after GC trong khoảng đủ dài**, thay vì tin mỗi một RSS snapshot.
5. Thử mô phỏng cùng request rate nhưng chuyển phần lớn traffic sang endpoint nhẹ hơn: giải thích vì sao gate chỉ dựa trên RPS **không đủ**.

## 8. Bảng so sánh tốt và bảng so sánh gây hiểu lầm

### Bảng tốt: đo cùng cửa sổ/đơn vị/đối tượng

| Metric (10 phút, cùng API region) | Baseline | Incident | Recovery-1 | Recovery-2 | Tiêu chí ví dụ |
|---|---:|---:|---:|---:|---|
| Served RPS | 100 | 90 | 99 | 101 | Gần baseline ±10% |
| Error rate (%) | 0,010 | 4,000 | 0,010 | 0,005 | ≤0,10% |
| Request p99 (ms) | 140 | 1.200 | 155 | 148 | ≤250 ms |
| CPU (%) | 42 | 95 | 47 | 45 | ≤75% cùng quy ước |
| RSS (MiB) | 512 | 710 | 535 | 530 | Không vượt guardrail, không tăng dai dẳng |

Bảng là **dữ liệu giả lập** từ chương trình, không phải một report incident thật. Các con số có thể so sánh về mặt bài tập vì do ta định nghĩa cùng 10 phút và cùng loại traffic; với dữ liệu thực phải có query chứng minh điều kiện đó.

### Bảng gây hiểu lầm: chỉ dùng màu xanh

```text
Alert: OK
Deployment: SUCCESS
CPU: 20%
=> Resolved
```

Không đủ: CPU có thể giảm do **service không nhận traffic**, exporter chết, kill/restart JVM, chuyển tải sang region khác hoặc ẩn tác động người dùng. Muốn tuyên bố phục hồi, cần user-facing SLI, tải, coverage, thử nghiệm chức năng và thời gian quan sát.

### Đề xuất trình bày khi viết status

Đừng chỉ viết “CPU giảm 50%”. Hãy viết “CPU JVM trung bình giảm từ X xuống Y với số instance, traffic class và RPS gần tương đương; đồng thời error rate/p99 đáp ứng mục tiêu trong hai cửa sổ ...”. Nếu điều kiện không tương đương, hãy nói rõ: “CPU giảm nhưng traffic cũng giảm; chưa đủ cơ sở kết luận khắc phục vấn đề hiệu năng”.

## 9. Những trường hợp dễ báo “phục hồi” sai

### 9.1. Khối lượng traffic biến mất

Triệu chứng: từ 100 RPS xuống 5 RPS, CPU và latency đều đẹp. Có thể load balancer đã loại instance hoặc ingress bị chặn. Hãy kiểm tra **incoming/served/rejected**, routing, health checks và luồng người dùng toàn hệ thống. Đừng chỉ nhìn metrics của instance còn nhận traffic.

### 9.2. Restart làm metric reset

JVM restart khiến **GC counters, heap used, thread count** đổi; nhiều bảng hiển thị CPU thấp vì warm-up chưa đến peak. Kiểm tra process start time, instance lifecycle, ramp-up, cache rehydration, JIT compilation và memory slope sau warm-up; không so cumulative metric trước/sau restart mà không xử lý reset.

### 9.3. Một region xanh, một region vẫn đỏ

Dashboard tổng có thể đẹp vì đa số traffic ở region khỏe. So các region/tenant/endpoint bị ảnh hưởng theo cùng tiêu chí. Dịch vụ **phục hồi một phần** phải được nêu rõ, không che bằng trung bình toàn hệ thống.

### 9.4. Error rate giảm nhưng queue backlog còn nguyên

Một consumer đã trả 200 cho yêu cầu nhận job, nhưng job xử lý chậm, dead-letter queue tăng, retry storm tiếp tục. Phục hồi cần xác nhận **processed/successful work**, queue depth/slope và data consistency, không chỉ synchronous API latency.

### 9.5. Không có lỗi vì hệ thống metric đã mất dữ liệu

Một dashboard hiển thị 0 errors khi exporter bị stop hoặc Prometheus query trả “no data”. Cần kiểm tra **scrape freshness, missing time series, sample count, collector health, clocks và alert rule behavior**. Phân biệt *zero observed errors* với *no observations*.

### 9.6. Fix triệu chứng nhưng root cause chưa xử lý

Rollback làm service lại chạy, nhưng bug chưa có test/patch; tăng heap làm OOM tạm hết, nhưng leak vẫn tồn tại. Kết luận chính xác là **mitigation/recovery trong phạm vi được kiểm chứng** và action item cho nguyên nhân gốc. Không viết “permanent fix” khi chỉ có cải thiện ngắn hạn.

### 9.7. Nhầm tương quan với quan hệ nhân quả

Cùng lúc triển khai hotfix, DB tự phục hồi hoặc traffic giảm. SLI cải thiện sau thay đổi không tự chứng minh thay đổi là nguyên nhân. Dựa vào timeline, diff, reproduction tests, canary/control cohort và nhiều tín hiệu; nếu chưa thể chứng minh, dùng chữ **“phù hợp với giả thuyết...”** thay vì **“đã chứng minh do...”**.

## 10. Lưu kết luận incident có căn cứ: điều gì bắt buộc phải ghi?

Một biên bản phục hồi/postmortem tốt phải giúp **người không có mặt lúc sự cố** kiểm tra lại số liệu và hiểu phạm vi kết luận. Tránh chỉ dán ảnh screenshot không có query, thời gian, units hoặc chủ sở hữu.

### 10.1. Mẫu ghi nhận

```text
Incident ID:
Service / environment / region / tenant:
Severity / user impact:
Owner / incident commander:
Timezone (UTC preferred):
Detected at:
Mitigation action and time:
Recovery observation window(s):
Baseline window(s) and reason comparable:
Criteria agreed (SLI/SLO + guardrails + data checks):
Evidence links (dashboards, log query, trace, JFR, deploy diff):
Metrics before / during / recovery (units, denominator, sample count):
Dependency and functional checks:
Remaining risks / unresolved questions:
Conclusion and confidence (recovered / mitigated / not yet verified):
Root cause status (confirmed / hypothesis / unknown):
Next action, owner, due date:
Approval / communication time:
```

Mẫu này là cấu trúc **điền từ incident thực**, không có sẵn giá trị hoặc khẳng định nào. Nếu một trường thiếu bằng chứng, ghi **“chưa có số liệu / chưa xác minh”**, không ước đoán thành số chính xác.

### 10.2. Ví dụ một kết luận đạt yêu cầu

```text
Phạm vi: checkout API ở region A (không bao gồm batch worker).
Tác động: 10:10–10:42 UTC, error rate tăng và p99 vượt SLO.
Hành động: rollback build B sang build A lúc 10:42 UTC.
Bằng chứng: dashboard X/query Y, trace Z, JFR sample W (đủ phạm vi).
So sánh: 10:50–11:10 UTC, hai cửa sổ 10 phút có
  error rate <=0,1%, p99 <=250ms và RPS gần baseline.
Kiểm tra: canary checkout OK, dependency DB healthy, backlog đã giảm.
Kết luận: Checkout API region A recovered theo tiêu chí thống nhất.
Giới hạn: Chưa loại trừ lỗi hiếm theo chu kỳ 6 giờ; root cause
  của build B còn ở trạng thái giả thuyết.
Follow-up: owner O xác nhận root cause/test và theo dõi 24 giờ.
```

Đây là **ví dụ giả lập**, không phải báo cáo sự cố xảy ra thật. Có thể tuyên bố *recovered* trong phạm vi region A nhưng **không tuyên bố service toàn cầu recovered** nếu region khác chưa được kiểm tra.

### 10.3. Độ tin cậy và loại kết luận

Nên phân biệt:

- **Observed:** “error rate trong window X giảm từ A xuống B theo query Q”.
- **Correlated:** “Sự giảm diễn ra sau rollback nhưng còn thay đổi traffic cùng lúc”.
- **Hypothesis:** “Có thể do connection pool exhaustion”.
- **Confirmed:** “Có testcase tái hiện với cấu hình cũ, bản fix chặn điều kiện đó, cùng dữ liệu vận hành tương thích”.
- **Unknown/insufficient evidence:** “Không có baseline/tracing trước incident; chưa xác định nguyên nhân”.

**Không cần chờ xác định root cause tuyệt đối để xác nhận người dùng đã phục hồi**, nhưng bắt buộc mô tả ranh giới giữa hai kết luận. Incident closure có thể diễn ra sau recovery khi việc giao tiếp và bàn giao đã xong.

## 11. Case studies: các kiểu phục hồi khác nhau

### Case A — CPU/GC spike sau rollout

Sau deploy Java service, CPU tăng 30% → 95%, p99 tăng; rollback làm CPU giảm. Baseline cần so với **RPS, số JVM, JDK flags, GC type, request mix** giống nhau. Dùng JFR để kiểm tra **CPU samples, GC pauses, allocation events** nếu có. Nếu sau rollback error rate/p99 và capacity ổn qua đủ peak cycle, có thể ghi “dịch vụ recovered sau rollback”; **root cause của build mới chưa confirmed** cho tới khi có testcase và causal evidence.

### Case B — OOM sau restart trông như đã hết

JVM bị OOM, restart khiến RSS/heap used rơi xuống thấp và alert ngừng. Đây là **phục hồi tạm**; nếu object/native allocation tiếp tục tích lũy, OOM sẽ lặp. Cần theo dõi **old-gen after GC, RSS/cgroup `memory.current`, allocation rate và OOM events** đủ lâu dưới tải đại diện. Ghi rõ thời gian quan sát và còn thiếu chu kỳ nào nếu chưa thể loại trừ leak.

### Case C — DB phục hồi nhưng queue chưa xử lý xong

DB latency trở về mức bình thường, HTTP ingress phản hồi nhanh. Nhưng backlog 500.000 items và retry rate vẫn cao, dữ liệu người dùng chưa cập nhật. Service frontend có thể *partial recovered*, còn pipeline async chưa. Xác nhận **drain rate, oldest-job age, successful processing, DLQ, consistency** trước khi nói toàn bộ hệ thống recovered.

### Case D — Scale-out che chi phí một request tăng

Thêm 6 JVM làm CPU mỗi instance giảm, p99 tốt lên. Tuy nhiên **CPU-seconds per successful request** có thể vẫn tăng vì code mới tính toán đắt. Có thể đáp ứng SLO **nhờ tăng capacity**, nhưng tài liệu phải nói rõ đây là biện pháp mitigation có chi phí; điều tra algorithm/GC và cost per request là follow-up.

### Case E — Canary chỉ chứa người dùng dễ

Canary thử 1% traffic trên endpoint phổ biến, không gặp lỗi; nhưng incident liên quan một operation hiếm của tenant cụ thể. Tiêu chí phục hồi phải bao gồm **affected cohort**, không dùng tổng lỗi của canary đại diện toàn bộ service. Cần synthetic test/traces/feature path cho nhóm ảnh hưởng, đồng thời giữ giám sát khi rollout rộng hơn.

## 12. Bảo vệ bằng chứng và giảm tác động của việc thu thập

- **Bảo vệ dữ liệu:** JFR, log, trace, heap dump và incident notes có thể chứa usernames, endpoint, class/method, token, request payload hoặc PII. Chỉ lưu và chia sẻ trong nơi có quyền phù hợp, retention rõ ràng; tránh tải heap dump lên ticket công khai.
- **Không thay đổi sản phẩm chỉ để đo:** Đừng bật mọi JFR event, lấy heap dump hoặc ép full GC trên production khi chưa cân nhắc overhead. `GC.heap_dump` có tác động cao; không dùng nó làm health check định kỳ.
- **Nguồn và độ chính xác:** Ghi link truy vấn có timestamp/scope, đơn vị, labels, phiên bản collector. Graph screenshot không có metadata dễ gây hiểu nhầm.
- **Không làm mất lịch sử:** Khi capture baseline/recovery files, giữ bản gốc và checksum/ownership nếu áp dụng; không sửa file chứng cứ để có kết luận đẹp hơn.
- **Phân quyền rõ:** Người xác nhận phục hồi phải có phạm vi trách nhiệm; follow-up root cause có người sở hữu riêng nếu cần. Không phải mọi người đọc một đồ thị xanh đều có quyền đóng incident.

## 13. Checklist xác nhận phục hồi

1. Xác nhận incident tác động tới **tác vụ người dùng nào, cohort/region nào**, không chỉ JVM/host.
2. Chọn **baseline known-good** có thời gian, traffic, instance count, versions và query được ghi lại.
3. Đặt SLI/SLO, resource guardrails, chức năng/data checks và **khoảng quan sát đủ dài** trước khi kết luận.
4. Kiểm tra **traffic còn đang được phục vụ**, denominators không quá nhỏ, dashboard không thiếu data.
5. So **baseline / incident / recovery** cùng units và scope; tránh so sai cumulative counters, p99 averages, reset sau JVM restart.
6. Kiểm tra JVM: CPU/GC/heap/native memory, thread/lock/I/O, JFR/JMC nếu có recording có đủ event.
7. Kiểm tra dependency, backlog, data consistency và các đường lỗi đã kích hoạt incident.
8. Giữ evidence links, timestamp UTC, deployment change, người xác minh và trạng thái root cause.
9. Chỉ tuyên bố **recovered** trong phạm vi thực sự đã kiểm chứng; ghi rõ điều kiện/giới hạn chưa chắc chắn.
10. Phân công giám sát tái phát, follow-up test/fix, owner và deadline; đóng incident theo quy trình sau khi truyền thông.

### Câu hỏi tự kiểm tra

- Vì sao sau rollback, CPU và p99 cùng giảm nhưng vẫn chưa đủ để nói root cause đã được sửa?
- Nếu error rate bằng 0 nhưng chỉ có 8 request và exporter bị mất dữ liệu, mức tự tin của kết luận phục hồi là bao nhiêu?
- Có được lấy trung bình p99 của hai cửa sổ để suy ra p99 cả 20 phút không? Tại sao?
- Khi traffic giảm mạnh trong lúc incident, nên bổ sung các metric nào trước khi gọi service recovered?
- Vì sao Heap used sau restart thấp chưa chứng minh memory leak biến mất?
- Nếu một region OK còn region khác lỗi, kết luận nên ghi phạm vi như thế nào?
- Trong `RecoveryGateDemo`, điều kiện nào phát hiện “metrics đẹp vì ít tải”? Điều kiện nào dùng để phát hiện nguy cơ RSS cao?
- Để một kết luận có căn cứ, sự khác nhau giữa “observed”, “hypothesis” và “confirmed root cause” là gì?

## Tài liệu tham khảo

- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): ưu tiên giảm tác động, phối hợp sự cố, kiểm tra phục hồi trước khi kết thúc ứng cứu.
- [Google SRE Workbook — Monitoring](https://sre.google/workbook/monitoring/): giám sát SLI, logs/metrics, data freshness, thay đổi deployment và dependency.
- [Google SRE Book — Example Postmortem](https://sre.google/sre-book/example-postmortem/): cấu trúc impact, root causes/trigger, resolution, timeline, evidence và action items.
- [Oracle Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): JFR start/check/dump và các lệnh chẩn đoán JVM.
- [Oracle Java SE 21 — `jfr`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, print, filtering event từ recording files.
- [Oracle JDK Mission Control 9 — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): phân tích Code, Memory, Threads/Locks, I/O và timeline.
- [Oracle Java SE 21 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): phân biệt used, committed, max trong JVM.
- [Oracle Java SE 21 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): counters, collection time và giới hạn measurement.
