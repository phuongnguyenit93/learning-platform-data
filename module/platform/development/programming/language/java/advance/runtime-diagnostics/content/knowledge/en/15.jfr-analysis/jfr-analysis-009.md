# 15.9 Đối chiếu kết quả phân tích tự động với bằng chứng và ngữ cảnh tải

## Mục tiêu

Sau khi mở một bản ghi Java Flight Recorder (JFR), Java Mission Control (JMC) hoặc công cụ phân tích tự động có thể đưa ra nhận xét như “CPU cao”, “có contention”, “nhiều GC”, “allocation đáng chú ý” hoặc “hot method”. Đây là **tín hiệu để điều tra**, chưa tự nó chứng minh nguyên nhân của latency, throughput giảm hay lỗi ứng dụng.

Bài học này tập trung vào bước thường bị bỏ qua: **đối chiếu nhận xét tự động với sự kiện JFR thực tế và ngữ cảnh tải của hệ thống**. Người phân tích cần biết công cụ đã dựa trên dữ liệu nào, dữ liệu có đủ đại diện hay không, kết quả có khớp timeline triệu chứng hay không, và điều gì cần đo thêm trước khi thay code, heap, GC hoặc hạ tầng.

Sau bài này, bạn có thể:

1. Đọc một kết quả phân tích tự động dưới dạng **giả thuyết có thể kiểm chứng** thay vì kết luận.
2. Kiểm tra chất lượng recording: thời gian, loại event, event threshold, sampling, stack traces, phần dữ liệu bị thiếu và giới hạn của công cụ.
3. Xác minh phát hiện bằng các sự kiện JFR gốc, timeline APM/logs/OS và chỉ số ứng dụng.
4. Chuẩn hóa so sánh theo thời lượng, request rate, loại workload, concurrency, kích thước dữ liệu và điều kiện môi trường.
5. Đánh giá phát hiện trái chiều, phân biệt tương quan với nhân quả, và quyết định khi nào dữ liệu đủ để thử một thay đổi.
6. Ghi lại kết luận có nguồn, phạm vi tin cậy, điều kiện phản chứng và kế hoạch đo lại.

Phạm vi: HotSpot/OpenJDK Java 17+ (các lệnh jfr minh họa theo JDK 21), JFR/JMC và các hệ thống phân tích dựa trên dữ liệu JFR. Tên quy tắc, điểm số, event mặc định và giao diện JMC có thể thay đổi theo phiên bản. Không giả định mọi bản ghi đều chứa mọi loại event.

## 1. Phân tích tự động thực sự cung cấp gì?

Một công cụ phân tích JFR có thể:

- **Tổng hợp dữ liệu:** số lượng event, thời lượng, phân phối, CPU samples, allocation samples, stack frames, thread states, GC phases.
- **Áp quy tắc/threshold:** ví dụ đánh dấu mức sử dụng CPU cao, GC pause dài, số lần chờ monitor hoặc lượng event profiling ít.
- **So sánh mẫu:** so snapshot, khoảng thời gian hoặc baseline nếu công cụ được cấp dữ liệu tương ứng.
- **Đưa lời giải thích/khuyến nghị:** chuyển một tín hiệu thành đoạn văn mô tả nút thắt hoặc hướng tối ưu, kể cả khi công cụ dùng AI/LLM.

Cần phân biệt bốn tầng:

| Tầng | Ví dụ | Mức độ có thể khẳng định |
| --- | --- | --- |
| **Raw observation** | JFR có 35 event jdk.GarbageCollection trong khoảng đã ghi | Sự kiện được ghi nhận trong file, với điều kiện file hợp lệ |
| **Derived metric** | GC pause tổng cộng X ms/phút trong một đoạn | Phụ thuộc lựa chọn event, cửa sổ tính và tránh cộng trùng |
| **Heuristic finding** | Rule đánh dấu “GC có thể gây ảnh hưởng hiệu suất” | Một dấu hiệu theo ngưỡng của rule, cần kiểm tra bối cảnh |
| **Root-cause claim** | “GC là nguyên nhân chính khiến checkout p99 tăng” | Cần đối chiếu thêm request latency, thời điểm, workload và nguyên nhân cạnh tranh |

Kết quả tự động thường giúp **ưu tiên điều tra**. Điểm severity/score trong một số phiên bản JMC là cách xếp hạng theo quy tắc, **không phải xác suất kết luận đúng**, không phải p-value, cũng không nói trực tiếp mức thiệt hại người dùng. Một rule có thể đánh dấu một sự kiện hợp lệ nhưng không quan trọng với SLO; ngược lại một sự cố đáng kể có thể không được đánh dấu nếu event không bật hoặc threshold bỏ qua.

**Ví dụ:** “Found monitor contention” cho biết có event tương ứng; để kết luận contention gây timeout, còn phải kiểm tra thread, stack, thời lượng, tần suất, giai đoạn tải và request bị ảnh hưởng.

## 2. Ba câu hỏi cốt lõi trước khi tin một phát hiện

### 2.1. Công cụ đang nói về cái gì?

Biến mô tả thành câu đo được:

> Trong khoảng T1–T2, trên JVM P, với cấu hình C, dấu hiệu E xuất hiện ở mức M, liên quan tới thread/method/GC phase K.

Ghi nguyên văn tên rule, mức cảnh báo, đối tượng bị nêu, thời gian và dẫn chiếu event. Nếu một AI summary nói “memory leak” nhưng không nêu object retention, xu hướng heap sau GC hoặc classloader roots, đó chỉ là giả thuyết.

### 2.2. Dữ liệu nào trực tiếp hỗ trợ?

Truy ngược tới một hoặc nhiều event type, field, aggregation, stack trace và recording interval. Nêu rõ:

- Event được **ghi từng lần**, ghi theo threshold, hay **sample**?
- Có đủ samples để nhận diện xu hướng? Có event bị tắt, filter bớt, thiếu stack hay timeout trước khi flush không?
- Kết quả tính theo **toàn file** hay chỉ **đoạn xảy ra triệu chứng**? Có bị pha warm-up/idle che mất?
- Có kiểm tra lại số liệu trên bản JFR đã được xuất thực sự, thay vì chỉ xem ảnh chụp dashboard?

### 2.3. Ngữ cảnh tải có khớp không?

Đối chiếu thời điểm ghi và trạng thái ứng dụng: requests/s, request mix, concurrency, payload, batch size, CPU quota/throttling, heap/GC flags, instance count, số worker, JDK version, warm-up, deployment/restart và lỗi upstream/downstream. Hai recordings có số sự kiện khác nhau do **lượng công việc khác nhau** chưa chắc là regression.

Một phát hiện chỉ đáng ưu tiên khi có đủ **triệu chứng quan trọng + bằng chứng cơ chế + quan hệ thời gian + bối cảnh tương đương hoặc đã giải thích được khác biệt**.

## 3. Lập hồ sơ recording trước khi phân tích nội dung

File .jfr không tự mang đủ toàn bộ ngữ cảnh hệ thống. Mở đầu incident bằng bảng tối thiểu:

| Nhóm | Thông tin cần ghi | Vì sao quan trọng |
| --- | --- | --- |
| Danh tính | Service, instance/pod, PID, build/commit, deployment | Tránh ghép nhầm dữ liệu của tiến trình khác |
| JVM | JDK/vendor/version, collector, JVM flags và memory limits | Event và hành vi thay đổi theo JVM/cấu hình |
| Recording | Filename, start/end time, duration, timezone, settings .jfc, sampling/thresholds | Xác định file có quan sát đúng cửa sổ không |
| Chất lượng dữ liệu | Loại event hiện diện, count, stack availability, tệp bị cắt/truncated, chunk coverage nếu có | Không kết luận từ dữ liệu không tồn tại |
| Workload | RPS, request mix, concurrency, payload/batch size, warm-up/steady-state | So đúng lượng công việc |
| SLO | p95/p99, error rate, timeout, throughput, CPU/RSS, yêu cầu kinh doanh | Biết phát hiện có ảnh hưởng thực tế không |
| Mốc thay đổi | Deploy, rollout, autoscaling, cache rebuild, batch job, traffic event | Giải thích nhiễu và điều kiện trước/sau |

Không phải file nào cũng chứa JDK/OS settings hoặc event cấu hình đầy đủ dưới dạng dễ tra. Khi metadata thiếu, lấy từ deployment manifest, launch command, metric labels, Java version và logs có cùng thời gian. Ghi “không rõ” nếu không xác minh được.

### 3.1. Độ dài bản ghi và khoảng dữ liệu thực có thể khác nhau

Continuous recording với maxage/maxsize có thể chỉ giữ vài phút cuối dù recording đã chạy nhiều giờ. Fixed-duration có thể dừng trước khi alert xảy ra. Một phần recording xuất muộn hoặc ghi trên filesystem không ổn định có thể thiếu giai đoạn cần phân tích.

Đầu tiên phải chứng minh **file bao phủ thời điểm xảy ra lỗi**, có dữ liệu trước–trong–sau khi cần. Nếu không bao phủ thì kết luận đúng là **không đủ bằng chứng**, không phải “không có bất thường”.

### 3.2. Chọn đúng khoảng thời gian

Tối thiểu chia thành:

1. **Baseline:** trước spike, workload và cấu hình tương đối ổn định.
2. **Incident:** thời đoạn p99/errors/throughput/CPU vi phạm mục tiêu.
3. **Recovery:** sau spike, nếu có.
4. **Control:** khoảng khác có tải tương tự nhưng không phát sinh lỗi, khi có thể lấy.

Bất kỳ báo cáo “toàn recording” nào cũng cần được kiểm tra lại trên **incident window**. Nếu 58 phút đầu idle và 2 phút cuối peak load, số trung bình toàn 60 phút che khuất đỉnh thực. Ngược lại một cảnh báo do 200 ms bất thường không tự đại diện cho hai giờ hoạt động.

### 3.3. Căn chỉnh đồng hồ

Dùng timestamp rõ timezone/UTC, và biết hệ thống nào phát sinh timestamp: JFR, application logger, APM, container runtime, node. Nếu đồng hồ lệch, một pause và một request timeout có thể trông như cùng lúc hoặc lệch nhau không thật. Các event dạng duration có start time/end time, event dạng sample chỉ có thời điểm quan sát. Đối chiếu theo khoảng giao nhau thay vì ghép tùy tiện hai điểm.

**Không dùng thời gian mở file hoặc thời gian upload artifact** làm thời điểm xảy ra sự kiện. Không dùng PID của process sau restart để giải thích process cũ.

## 4. JFR quan sát có giới hạn: coverage, threshold và sampling

### 4.1. “Không thấy event” có nhiều nghĩa

Không thấy jdk.JavaMonitorEnter hay jdk.SocketRead có thể do:

- Cấu hình recording không bật loại event đó.
- Threshold chỉ ghi hoạt động kéo dài trên một ngưỡng; các thao tác ngắn bị bỏ qua.
- Recording bắt đầu sau khi hiện tượng kết thúc.
- File chỉ giữ rolling window mới nhất; dữ liệu cũ đã bị loại.
- Event bị filter khi export/print; stack depth hiển thị quá ngắn.
- Event sampling thưa, thời đoạn quan sát ngắn hoặc thiếu samples.
- Ứng dụng dùng cơ chế khác với event bạn đang tìm: ví dụ chờ ReentrantLock/park không đồng nghĩa chờ Java object monitor.
- Hoạt động có thật nhưng không vượt ngưỡng phát hiện của rule.

Do đó **0 event được ghi ≠ 0 hoạt động ngoài đời**, trừ khi chứng minh cơ chế quan sát bao phủ đầy đủ hoạt động được hỏi.

### 4.2. Sample không phải bộ đếm tuyệt đối

jdk.ExecutionSample và các phương pháp CPU stack sampling cung cấp **mẫu stack**, không phải mọi lần gọi method. Method có nhiều samples có thể là hotspot; nhưng tỉ lệ samples không tự bằng tỉ lệ wall-clock latency của request, nhất là khi thread chờ I/O/lock hoặc có CPU native/GC/JIT. “Không có sample ở method A” không chứng minh A không tiêu thời gian.

Với allocation sampling, số sample không phải số allocation thật; dùng trọng số/ước lượng và phạm vi hỗ trợ của tool khi kết luận về allocation rate. Sampling mode, period, data volume, stack filtering và version khác nhau khiến so sánh raw count dễ sai.

### 4.3. Duration, thresholds và các event chồng lấp

Một jdk.GarbageCollection event có thể mô tả hoạt động GC; các GC phase events (nếu có trong file) có cấu trúc riêng. Đừng cộng tổng thời lượng của parent GC event và các subphase event làm “tổng pause” vì sẽ đếm trùng; đừng coi mọi GC duration là Stop-The-World pause nếu collector có pha concurrent. Tìm chính xác sự kiện pause hoặc GC log phù hợp collector khi cần đối chiếu latency.

Đối với jdk.JavaMonitorEnter, jdk.ThreadPark, file/socket I/O, threshold có thể khiến chỉ hoạt động trên ngưỡng được ghi. Một bản ghi dùng threshold 20 ms và một bản ghi dùng 5 ms **không có mẫu sự kiện tương đương**, dù event type giống nhau.

### 4.4. Automated analysis rule có tiền điều kiện

Một rule có thể yêu cầu đủ CPU samples, đủ thời lượng, hoặc event tương ứng. Khi thiếu dữ liệu, kết quả “OK” đôi lúc chỉ là “rule không kích hoạt”. Cần xem diễn giải của rule, preconditions, danh sách event được bật, thiếu samples và mức tin cậy mà công cụ công bố; không biến “không cảnh báo” thành “ứng dụng khỏe”.

Với AI/LLM tóm tắt, yêu cầu nó dẫn tới event type, metric, khoảng thời gian, đơn vị và lập luận có thể tái lập. Một lời giải thích trôi chảy nhưng không thể đối chiếu không đủ giá trị vận hành.

## 5. Đối chiếu bằng chứng theo từng loại phát hiện

| Phát hiện tự động | JFR evidence cần xem | Bằng chứng độc lập | Câu hỏi phản chứng |
| --- | --- | --- | --- |
| “High CPU / Hot Methods” | jdk.CPULoad, jdk.ThreadCPULoad, jdk.ExecutionSample, stack/call tree và sample count | Process/container CPU, throttling, RPS, native/GC/JIT CPU, traces | CPU tăng vì tải gấp đôi hay do regression? Sample có đủ không? |
| “GC impact / Pause dài” | GC events/pause phases, heap before/after, thời lượng và timestamp | GC logs, p99 latency, allocation rate, CPU, heap headroom | Pause có trùng với request chậm không? Có concurrent phase bị hiểu sai? |
| “Allocation pressure” | Allocation sampling, class và stack, estimated rates nếu tool hỗ trợ | Allocation profiler, RPS/payload, heap trend, GC rate | Số allocation tăng vì requests tăng? Có chứng cứ retention/leak không? |
| “Possible memory leak” | Live object/old object samples nếu bật, heap usage và GC trend | Heap dump/dominator tree, GC roots, cache occupancy, cùng tải | Object còn reachable lâu dài hay chỉ workload hợp lệ? |
| “Monitor contention” | jdk.JavaMonitorEnter, monitor class, blocking thread, stack, duration | Thread dumps, request trace, lock metrics, thread pool | Chờ monitor có trùng sự cố và nằm trên critical path không? |
| “Thread parking / blocked” | jdk.ThreadPark, stack, parked duration, thread state | Executor queue, pool saturation, DB connection pool, p99 traces | Chờ có phải thiết kế bình thường hay nghẽn resource? |
| “I/O chậm” | jdk.SocketRead/SocketWrite, jdk.FileRead/FileWrite (nếu bật) | Network RTT, DB latency, filesystem metrics, upstream errors | Phía nào chậm? Event vượt threshold có đại diện traffic không? |
| “Classloading/JIT cao” | Class load/compile events nếu ghi, code paths và timeline warm-up | Deploy/restart, cache warm-up, compilation counters | Chỉ xuất hiện lúc khởi động hay steady state? |
| “CPU thấp nhưng latency cao” | ThreadPark/monitor/socket/file events, CPU samples nếu có | Traces, downstream latency, queuing, CPU throttling | Ứng dụng chờ điều gì? CPU thấp có nghĩa đang idle hay blocked? |

Bảng là **lộ trình kiểm chứng**, không phải tuyên bố rằng mọi event trên đều bật trong default.jfc. Với từng file, kiểm tra event type có tồn tại và số mẫu trước khi chọn lệnh.

## 6. Chuẩn hóa theo workload thay vì so tổng event thô

### 6.1. So cửa sổ có cùng thời lượng hoặc chuẩn hóa theo thời gian

Giả sử bản A dài 10 phút, bản B dài 20 phút. B có 100 GC events, A có 70. Kết luận “B tệ hơn vì nhiều GC hơn” là thiếu cơ sở. Tính events/minute, GC pause ms/minute và throughput tương ứng; sau đó xem loại collector, mix tải và mỗi event có ý nghĩa gì.

Các tỷ lệ thường hữu ích khi mẫu đủ đại diện:

- **Request rate:** requests / seconds quan sát.
- **Event rate:** số event được ghi / phút (chỉ so hợp lý nếu cùng settings/threshold).
- **Allocation rate:** bytes/s hoặc bytes/request nếu tool cho phép ước lượng đáng tin.
- **GC pause burden:** tổng **STW pause** / thời gian tương ứng; không gộp concurrent phases hoặc event lồng nhau.
- **Wait burden:** tổng thời gian chờ trên các thread liên quan, cần tránh nhầm tổng chờ đồng thời của nhiều thread với thời gian clock của một request.
- **Error rate:** lỗi / request cùng loại.
- **CPU:** CPU process/cgroup theo thời gian, cân nhắc quota và throttling.

### 6.2. Chuẩn hóa theo số request, mix và kích thước công việc

Cùng 100 events/minute có thể khác ý nghĩa nếu:
- A phục vụ 200 requests/s, B phục vụ 2.000 requests/s;
- A đọc payload 2 KiB, B đọc 2 MiB;
- A chủ yếu cache hit, B chủ yếu database writes;
- A concurrency 20, B concurrency 1.000;
- A có 1 replica, B có 8 replica và traffic không phân bổ đều.

Đếm per request chỉ hữu ích với loại event gắn hợp lý với request và event coverage tương đồng. Với batch jobs, có thể chuẩn hóa theo records processed, jobs, MiB dữ liệu hay transaction type thay vì HTTP requests. **Không dùng tỷ lệ per request để thay thế latency per request:** một request chậm có thể kéo dài dù tổng event rate thấp.

### 6.3. Vấn đề phân phối: p99 không bằng average

Latency p99 tăng không thể giải thích chỉ bằng giá trị GC average. Một số ít pause hoặc lock waits đồng thời với các request xấu có thể gây tail latency; ngược lại GC tổng thời gian lớn mà không trùng critical requests chưa chứng minh GC gây vi phạm SLO.

Phải xem:
- Biểu đồ đồng thời theo thời gian (request p99, GC pauses, CPU, lock, I/O).
- Percentiles và số mẫu theo route/transaction, đặc biệt nhóm người dùng bị ảnh hưởng.
- Số requests trong mỗi bucket thời gian; p99 của nhóm 20 request rất nhiễu.
- Điều kiện nền, burst/tải peak và thời gian đã warm-up.

**Simpson's paradox:** latency toàn service có thể tăng chỉ vì tỷ trọng route chậm tăng, dù từng route giữ nguyên. Kiểm tra route mix trước khi kết luận JVM regression.

### 6.4. Thay đổi cấu hình quan sát làm thay đổi kết quả

Recording A dùng default.jfc, B dùng profile.jfc hoặc custom threshold khác; raw count và số stack samples không trực tiếp tương đương. Nếu buộc phải so, chỉ sử dụng các event có cấu hình/coverage tương thích hoặc tạo recording đối chứng với **cùng event settings**. Ghi lại profile overhead để tránh chính quan sát làm thay đổi workload.

## 7. Một quy trình kiểm chứng tuần tự, có thể tái lập

### Bước 1 — Chụp phát hiện nguyên văn

Lưu kết quả analyzer: tên rule, version của công cụ, mức cảnh báo/score, mô tả, thread/method/class nếu có, công thức/threshold nếu biết, khoảng thời gian, số samples và URL/đường dẫn trang chi tiết. Không diễn giải lại thành root cause ngay.

### Bước 2 — Xác định câu hỏi kinh doanh/kỹ thuật

Ví dụ: “Trong 10:03–10:05, checkout p99 vượt 500 ms so với SLO 200 ms; liệu monitor contention đang chiếm phần lớn thời gian critical path?” Câu hỏi cụ thể tốt hơn “JFR có vấn đề gì?”.

### Bước 3 — Kiểm tra chất lượng recording

Kiểm tra file mở được, đúng JVM, timestamp coverage, sự kiện liên quan có dữ liệu, sampling/threshold phù hợp, stack traces có thể tra, có thiếu chunk hoặc hạn chế retention không. Nếu thiếu, ghi limitation trước khi kết luận.

### Bước 4 — Truy ngược về raw events và tính lại đơn vị

Ví dụ rule về GC: mở GC/pause events, xem khoảng thời gian, duration và cause; so với GC logs nếu có. Với monitor contention: xem event duration, lock class, thread và stack; không chỉ đếm số event. Với CPU: xem sample counts, period, process CPU, GC/JIT/native activity. Nếu tool không công bố công thức, trình bày metric tự tính với phương pháp rõ ràng.

### Bước 5 — Ghép timeline với ứng dụng và tài nguyên

Dùng cùng timezone/UTC, ghép JFR với APM p95/p99, error rate, request counts, thread/queue pool, service dependencies, CPU throttling, RSS/GC logs. Tìm **đúng lúc** chỉ số xấu đi và đánh giá độ dài sự kiện có đủ để giải thích tác động không.

### Bước 6 — Kiểm tra ngữ cảnh tải và giả thuyết cạnh tranh

So request mix, throughput, payload, deployment, warm-up, cache, CPU/memory quota, replica, service dependency. Đặt ít nhất một giả thuyết cạnh tranh: database chậm, CPU quota thấp, network, queue saturation, memory leak, batch job, application bug. Bằng chứng nào sẽ bác bỏ từng giả thuyết?

### Bước 7 — Phân mức độ tin cậy và hành động

Ghi “đã quan sát”, “có khả năng”, “chưa xác minh” theo bằng chứng. Nếu đủ, thiết kế thí nghiệm nhỏ với guardrails; nếu chưa đủ, chỉ rõ **cần thu gì**, trong bao lâu và ở đâu. Tránh tuning CPU/GC/heap/locking từ một cảnh báo màu đỏ.

**Quy tắc thực hành:** Mỗi khuyến nghị phải có chuỗi **phát hiện → raw evidence → workload context → triệu chứng → giả thuyết → phép kiểm chứng**.

## 8. Công cụ dòng lệnh: tự đối chiếu thay vì chỉ đọc summary

Các ví dụ dùng lệnh jfr của JDK 21 và file recording.jfr đã có, ở nơi chạy lệnh có quyền đọc. Với JDK 17, xác nhận subcommands tương ứng bằng jfr help vì công cụ/phiên bản có thể khác nhau. Không có lệnh nào dưới đây tự tạo dữ liệu thiếu trong file.

### 8.1. Kiểm tra nội dung file và danh sách event

~~~bash
jfr --version
jfr summary recording.jfr
jfr metadata recording.jfr
jfr --help print
~~~

- **summary:** khoảng thời gian, kích thước, loại event và số lượng đã ghi; event count là count trong file, không phải count mọi hoạt động runtime.
- **metadata:** mô tả event types, fields/schema; loại event tồn tại trong metadata không chứng minh có event instance tương ứng.
- **help:** xác minh cú pháp trên bản JDK cài đặt, tránh dùng options mới trên JDK cũ.

Nếu file rất lớn, không in toàn bộ event ra console; dùng filter, export JSON có kiểm soát hoặc phân tích trong JMC. File JFR có thể chứa thông tin vận hành nhạy cảm.

### 8.2. Xem các raw event liên quan

~~~bash
jfr print --events jdk.GarbageCollection recording.jfr
jfr print --events jdk.CPULoad recording.jfr
jfr print --events jdk.JavaMonitorEnter recording.jfr
jfr print --events jdk.ThreadPark recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
~~~

Các lệnh hiển thị những event phù hợp **nếu đã được ghi**. Một lệnh không in event nào không đủ kết luận dịch vụ không có GC/CPU/locks; hãy xem settings, khoảng ghi, threshold và summary.

Để lấy output có cấu trúc dùng trong script kiểm chứng:

~~~bash
jfr print --json --events jdk.GarbageCollection recording.jfr
~~~

Cấu trúc JSON phụ thuộc schema event/JDK; không hard-code giả định mọi vendor và phiên bản đều có các field giống nhau. Nếu cần dựng bảng thời gian, parse JSON, lấy startTime/duration phù hợp với event type, rồi ghép với APM metrics theo timestamp. Trong hệ thống production, chọn xuất có kiểm soát để không phơi bày dữ liệu nhạy cảm.

### 8.3. Khi dùng JMC

Có thể làm theo trình tự:

1. Mở đúng recording và xem **Automated Analysis Results** (tên vị trí có thể khác theo version).
2. Chọn cảnh báo quan tâm, ghi tên rule và logic/threshold nếu hiển thị.
3. Theo liên kết đến trang gốc: GC, Memory, Threads, Java Application, Code/Hot Methods, I/O hoặc sự kiện tương ứng.
4. Chọn time range trùng khoảng SLO vi phạm; so event histogram và timeline.
5. Mở stack trace/call tree và thread details để xem điểm phát sinh, nhưng nhớ stack của nơi ghi sự kiện không nhất thiết là nơi giữ object hay nguyên nhân upstream.
6. Ghi rõ event count, sample count, threshold và evidence có thể xuất lại bằng CLI/API.
7. So với metrics ngoài JFR, rồi cập nhật nhận định.

Tên tab, rule và cách hiển thị tùy phiên bản JMC. Các rule tự động không thay thế hiểu biết về semantics của JFR events.

## 9. Ví dụ 1 — Cảnh báo Hot Methods nhưng ứng dụng chủ yếu đang chờ

Công cụ tự động liệt kê method A chiếm 60% execution samples và kết luận “method A là nguyên nhân gây request latency”.

**Bước đối chiếu:**
- Kiểm tra tổng số samples và thời gian profile. Nếu chỉ 10 samples, 6 samples tại A không đủ đại diện cho hàng nghìn requests.
- Kiểm tra process CPU/jdk.CPULoad. Nếu CPU thấp, method A có thể chiếm tỷ lệ lớn **trong rất ít thời gian CPU**.
- Truy vết request chậm; nếu phần lớn wall-clock time là socket read đến DB hoặc chờ queue, CPU hotspot A không giải thích được toàn bộ latency.
- Kiểm tra có native code, GC/JIT activity, thiếu sampling coverage hoặc thread khác làm việc.
- So hai khoảng cùng workload và settings, xem A tăng cả **mức tuyệt đối** lẫn tác động tới p99 không.

**Kết luận hợp lý:** “A nổi bật trong execution samples; chưa chứng minh A chi phối end-to-end latency”. Nếu A thật sự chiếm CPU lớn trong thời gian service bị giới hạn CPU, tối ưu A mới là giả thuyết đáng thử.

**Sai lầm thường gặp:** quy tỷ lệ 60% samples thành “60% requests bị chậm do A” hoặc “60% thời gian người dùng chờ nằm trong A”. Đây là các mẫu số khác nhau.

## 10. Ví dụ 2 — Rule GC cảnh báo nhưng request timeout do downstream

Tình huống minh họa (số liệu giả định):

| Metric | 10:00–10:05 baseline | 10:10–10:15 incident |
| --- | --- | --- |
| Checkout p99 | 120 ms | 750 ms |
| Requests/s | 400 | 420 |
| GC pause tổng cộng | 400 ms/5 phút | 650 ms/5 phút |
| Full GC | 0 | 0 |
| DB query p99 | 85 ms | 680 ms |
| CPU throttling | Không đáng kể | Không đáng kể |

JMC đánh dấu số lượng young GC tăng. Nhưng tổng pause tăng thêm 250 ms **trên năm phút**, trong khi nhiều requests cùng chịu database p99 tăng. Cần kiểm tra GC pause timestamp có trùng các request chậm không; dữ liệu tổng không đủ để phân bổ độ trễ của từng request. DB latency và trace là giả thuyết mạnh hơn để điều tra trước.

**Không kết luận rằng GC vô hại chỉ từ tổng nhỏ:** một pause đơn lẻ dài trùng một nhóm requests vẫn có thể ảnh hưởng tail latency. Tuy nhiên cũng không được kết luận “GC là root cause” chỉ vì dashboard tô đỏ GC.

Nếu GC logs cho thấy pause hàng trăm ms **đúng lúc** p99 spikes và trace DB ổn định, hướng giả thuyết có thể đổi. Lập luận phải theo bằng chứng, không theo thứ tự cảnh báo của tool.

## 11. Ví dụ 3 — Allocation samples tăng do tải tăng

Hai recordings cùng settings, mỗi file 10 phút:

| Số đo | Baseline | Peak |
| --- | --- | --- |
| Throughput | 200 req/s | 400 req/s |
| Tổng requests | 120.000 | 240.000 |
| Allocation sample count | 1.000 | 2.200 |
| GC CPU hoặc pause | Đo riêng | Đo riêng |
| Tỷ lệ route, payload | Giả sử tương đương | Phải xác minh |

Nếu chỉ nhìn 1.000 → 2.200 samples, công cụ có thể xếp “allocation nhiều hơn”. Nhưng tải cũng tăng gấp đôi. Số samples/request tăng khoảng 10% **trong điều kiện sampling tương đương**; nếu settings, sample period, event weights hoặc workload mix khác thì tỷ lệ ấy có thể đánh lừa.

Nếu cần kết luận allocation efficiency, ưu tiên bytes/request ước lượng từ công cụ có xử lý sampling weights, thêm allocation profile của code path, route/payload mix và GC/CPU. **Sampling count không tự chuyển thành số object được tạo hoặc bytes thực tế**.

Một bài toán retention/leak còn cần chứng cứ object **được giữ** sau GC, heap growth/dominator paths; allocation pressure lớn không đồng nghĩa memory leak.

## 12. Ví dụ 4 — Monitor contention tăng nhưng chưa chắc là bottleneck

Automated rule cảnh báo nhiều jdk.JavaMonitorEnter events ở một synchronized block. Hỏi:

1. Event capture threshold là gì? Một bản ghi threshold 5 ms sẽ có count khác hẳn bản 20 ms.
2. Có bao nhiêu thread tham gia, stack nào, lock class/object nào và tổng thời gian chờ ở critical path?
3. Thời gian chờ có trùng request latency spikes hay diễn ra trong batch background không?
4. Request RPS, concurrency và queue length thay đổi ra sao?
5. Có ReentrantLock, thread parking hoặc connection pool waits nằm ngoài JavaMonitorEnter không?
6. Điều gì sẽ xảy ra khi giảm contention? p99 giảm, CPU tăng hay throughput thay đổi?

Nếu 80 events/s ở hệ thống 50.000 req/s, mức quan trọng có thể khác 80 events/s ở 100 req/s. Dù vậy vẫn phải xem duration: vài blocking events rất dài có thể làm nghẽn luồng quan trọng. Cần **tỷ lệ, độ dài, đối tượng, timeline và impact**.

## 13. Ví dụ 5 — CPU thấp, threads chờ nhiều, rule báo “ứng dụng idle”

Một số công cụ xem CPU usage thấp và execution samples ít như tín hiệu workload không làm gì. Nhưng checkout p99 vẫn có thể cao vì:

- Threads đang chờ database/socket, network, mutex hoặc connection pool.
- Queue tăng và request chưa được xử lý bởi worker.
- Container bị CPU throttling theo burst; CPU average không thể hiện rõ thời điểm bị giới hạn.
- Số requests/second thấp do upstream backpressure, trong khi những requests còn lại rất chậm.

Cần so thread states/park/socket events với APM traces, pool metrics, upstream/downstream latency và số requests; phân biệt **không có việc** với **có việc nhưng không chạy được**. Rule “idle” có thể đúng theo định nghĩa sử dụng CPU nhưng không đúng cho kết luận “ứng dụng khỏe”.

## 14. Ví dụ Java 17+: chuẩn hóa và so sánh bằng chứng đã tổng hợp

Chương trình sau **không đọc file JFR** và không giả vờ suy ra root cause. Nó minh họa phép kiểm tra bắt buộc trước khi so hai kết quả tự động: chuẩn hóa một số event counts theo requests, GC pause theo phút, đồng thời giữ p99 làm chỉ số mục tiêu.

Giả sử hai khoảng đều dài 600 giây, cùng JDK/collector/event settings/threshold, không thiếu dữ liệu quan trọng. Các số chỉ dùng để học phương pháp.

Lưu thành file **EvidenceRates.java**:

~~~java
import java.util.Locale;

public class EvidenceRates {
    record Window(
            String name,
            long seconds,
            long requests,
            long monitorEvents,
            long gcPauseMillis,
            double p99Millis) {

        double requestsPerSecond() {
            return (double) requests / seconds;
        }

        double monitorEventsPerTenThousandRequests() {
            return monitorEvents * 10_000.0 / requests;
        }

        double gcPauseMillisPerMinute() {
            return gcPauseMillis * 60.0 / seconds;
        }
    }

    static void show(Window window) {
        System.out.printf(
                Locale.ROOT,
                "%s: rps=%.0f, monitor/10k=%.1f, GC-pause-ms/min=%.0f, p99=%.0fms%n",
                window.name(),
                window.requestsPerSecond(),
                window.monitorEventsPerTenThousandRequests(),
                window.gcPauseMillisPerMinute(),
                window.p99Millis());
    }

    public static void main(String[] args) {
        Window baseline = new Window("baseline", 600, 120_000, 24, 900, 110);
        Window incident = new Window("incident", 600, 240_000, 80, 1_200, 330);

        show(baseline);
        show(incident);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac EvidenceRates.java
java EvidenceRates
~~~

Stdout chính xác của chương trình:

~~~text
baseline: rps=200, monitor/10k=2.0, GC-pause-ms/min=90, p99=110ms
incident: rps=400, monitor/10k=3.3, GC-pause-ms/min=120, p99=330ms
~~~

Ý nghĩa:

- Monitor events thô tăng từ 24 lên 80, nhưng requests tăng gấp đôi. Chuẩn hóa giúp nhìn 2,0 → 3,3 events/10.000 requests, dù **vẫn chưa biết event duration hay critical path**.
- GC pause tổng tăng từ 900 lên 1.200 ms trong 10 phút, tức 90 → 120 ms/phút. Dữ liệu này chưa chỉ ra các pause có trùng p99 spikes hay không.
- p99 tăng từ 110 lên 330 ms, nhưng **không thể quy ba lần latency cho monitor hoặc GC** chỉ từ các con số tổng.
- Trước khi dùng tỷ lệ monitor/10k, phải chắc cùng loại event, threshold và request mix; nếu event được sample/filter thì đếm có thể không đại diện.
- Muốn hành động, cần drill-down raw events và timestamps, traces, CPU/pool, định vị đối tượng/stack, baseline với tải tương đương hoặc thí nghiệm có kiểm soát.

**Giới hạn của minh họa:** aggregate trên 10 phút có thể che thời điểm sự cố; giả định các events không chồng lấp không được thiết lập; “GC pause ms” phải lấy từ nguồn pause đúng và tránh double-count. Chương trình chỉ làm phép tính rõ ràng, không tự xác thực semantics của dữ liệu đầu vào.

## 15. Khi kết quả của các nguồn mâu thuẫn

Sự mâu thuẫn là tín hiệu cần điều tra nguồn quan sát:

| Automated finding | Bằng chứng khác | Cách đọc phù hợp |
| --- | --- | --- |
| High CPU hotspot | CPU process thấp | Xem sample count, thời điểm lấy mẫu, thread lọc, thời gian idle |
| GC pause gây p99 | p99 spikes không trùng pause | Chưa chứng minh nguyên nhân; xem DB/queue/network |
| Allocation hotspot tăng mạnh | RPS/payload tăng tương ứng | Chuẩn hóa theo công việc; xem bytes/request và hậu quả GC |
| Không có lock contention | JFR không bật lock event/threshold quá cao | Kết luận “chưa quan sát được”, không kết luận “không có” |
| Memory leak | Heap after-GC ổn định qua cùng workload | Cần object retention trend/heap dump trước khi gọi leak |
| File I/O chậm | Most requests chờ remote DB | Chọn critical path, không tối ưu I/O ngoài phạm vi tác động |
| “OK” hoặc không warning | JFR chỉ chứa 30 giây idle | Coverage thiếu; không ngoại suy sang peak |
| Nhiều thread samples ở A | p99 tăng khi B downstream chậm | Đặt lại giả thuyết theo distributed trace/timestamp |

Các bước giải quyết:

1. Kiểm tra mỗi nguồn đang đo đúng **đơn vị** và **phạm vi** chưa.
2. Kiểm tra đồng bộ thời gian, window, sampling/threshold, aggregation và missing data.
3. Xác định nguồn nào trực tiếp nhất cho câu hỏi: latency → traces/SLO; GC pause → pause events/GC log; code CPU → CPU samples cộng process CPU; memory retention → heap trend/dump.
4. Ghi lý do nguồn bất đồng và chứng cứ cần bổ sung; không xóa hoặc chọn bỏ dữ liệu trái ý.
5. Nếu dữ liệu vẫn không phân xử được, kết luận **inconclusive**, không tự chèn một lời giải chắc chắn.

## 16. Cấp độ bằng chứng và quyết định hành động

Dùng phân cấp thực hành, không coi đây là quy tắc thống kê phổ quát:

| Mức | Có gì | Quyết định |
| --- | --- | --- |
| **Tín hiệu** | Một cảnh báo hoặc AI summary thiếu dẫn chiếu | Tạo giả thuyết; chưa tuning |
| **Quan sát có nguồn** | Raw event + cấu hình ghi + cửa sổ thời gian xác minh | Điều tra đúng resource/thread/method |
| **Tương quan hợp lý** | JFR event trùng triệu chứng, có workload/SLO/traces | Ưu tiên thử kiểm chứng, giữ giả thuyết cạnh tranh |
| **Thử nghiệm xác nhận** | Baseline và candidate cùng điều kiện, một biến chính, kết quả lặp lại, không vi phạm guardrails | Có cơ sở triển khai có kiểm soát |
| **Không đủ dữ liệu** | Recording thiếu event/time range, settings khác, không có workload context | Thu dữ liệu bổ sung và báo rõ giới hạn |

Một rule có score cao vẫn có thể ở mức “tín hiệu” nếu thiếu raw evidence. Một rule score thấp vẫn có thể quan trọng nếu số ít events nằm trên đường xử lý giao dịch quan trọng và gây timeout. Hãy ưu tiên **mức ảnh hưởng SLO và chất lượng bằng chứng**, không ưu tiên chỉ theo màu sắc UI.

## 17. Kiểm chứng bằng thí nghiệm có đối chứng

Giả sử bạn nghi queue/lock contention sau khi xem JFR. Thiết kế một thay đổi nhỏ và đo:

1. **Khóa điều kiện nền:** build, JDK, JVM flags/GC, pool sizes ngoài biến thử, CPU/memory limits, số replica, dependencies, request mix và payload.
2. **Định nghĩa giả thuyết có thể bác bỏ:** “Giảm synchronized critical section sẽ giảm thời gian chờ cùng stack X ở peak 800 RPS, đồng thời cải thiện checkout p99”.
3. **Đo baseline:** cùng recording settings, event threshold, window sau warm-up, p95/p99, error rate, throughput, CPU/RSS, GC, thread/queue và monitor event durations.
4. **Thay đúng một biến chính:** code hoặc pool/config liên quan; tránh đồng thời đổi GC và hạ tầng.
5. **Chạy cùng tải, lặp lại:** nhiều lần, tránh trộn burst với steady state và đo cả rủi ro regressions.
6. **Xác nhận cơ chế:** sự kiện contention tại stack X giảm trong raw JFR **và** p99/throughput được cải thiện tương ứng. Nếu chỉ event count giảm do threshold thay đổi hoặc workload giảm, không phải thành công.
7. **Guardrails và rollback:** SLO, error rate, CPU/GC/memory footprint, downstream pressure. Nếu một chỉ số đẹp hơn nhưng hệ thống không an toàn, rollback.
8. **Ghi kết luận theo mức chắc chắn:** giữ thay đổi chỉ khi bằng chứng lặp lại và cost/benefit hợp lý.

Với GC/heap tuning, cùng logic áp dụng: cần hiểu live set, allocation pressure, pause timeline, container memory headroom và chọn collector/cờ thích hợp. Một khuyến nghị tự động “tăng heap” khi process đã gần cgroup limit có thể khiến OOMKilled.

## 18. Mẫu báo cáo phân tích có thể audit

Có thể sử dụng Markdown sau cho một ticket điều tra. Đó là **khung thông tin thực tế cần điền trong incident**, không phải kết luận sẵn:

~~~text
# JFR finding cross-check

Service / instance / PID:
Build / JDK / collector / JVM flags:
Recording file / SHA-256 (nếu cần lưu bằng chứng):
Recording time range / timezone:
JFR settings / event thresholds / sampling:
Incident window and SLO violation:
Traffic RPS / route mix / concurrency / payload:
Automated tool version / rule name / score:
Original recommendation:

Raw event evidence:
- Event types:
- Event count / duration / sample count:
- Affected thread/method/stack:
- Exact timestamps / time window:
- Missing data / coverage limits:

Independent evidence:
- APM traces, p95/p99, errors:
- CPU/RSS/throttling, GC logs, thread/pool metrics:
- Deployment, warm-up, downstream events:

Alternative hypotheses / what would falsify each:
Current confidence / why:
Decision: investigate / controlled experiment / defer
Candidate change / measurement / guardrails / rollback:
Follow-up recording and outcome:
~~~

Không ghi mẫu này vào JFR file; đây là mô hình ghi lại quá trình điều tra. Khi chia sẻ file .jfr/stack traces, kiểm tra dữ liệu nhạy cảm như paths, class names, thread names, custom event payload và các token do ứng dụng tự ghi.

## 19. Checklist đánh giá một kết quả tự động

- [ ] Tôi có nguyên văn tên rule/kết quả, phiên bản công cụ và khoảng thời gian mà rule đánh giá.
- [ ] Tôi biết phát hiện là raw event, metric tổng hợp, heuristic hay suy đoán nguyên nhân.
- [ ] Tôi có đúng JFR file của process/instance/phiên bản đang gặp sự cố.
- [ ] Tôi đã xác minh recording bao phủ khoảng trước–trong–sau incident hoặc ghi rõ hạn chế.
- [ ] Tôi biết event types có bật không, sampling/threshold ra sao, có đủ samples/stack dữ liệu không.
- [ ] Tôi kiểm tra raw event timestamps, durations, thread/method/stack và cách công cụ tổng hợp.
- [ ] Tôi không suy “không có event” thành “không có hoạt động” khi coverage chưa đủ.
- [ ] Tôi căn chỉnh timeline với APM traces, p95/p99, error rate, GC logs, OS/cgroup metrics.
- [ ] Tôi ghi workload: RPS, request mix, payload, concurrency, warm-up, batch/caches/deploy.
- [ ] Tôi so rates phù hợp và không cộng trùng events/nested phases hoặc nhầm samples với actual counts.
- [ ] Tôi xem ít nhất một giả thuyết cạnh tranh và một điều kiện có thể bác bỏ khuyến nghị tự động.
- [ ] Tôi chỉ đề xuất thay code/config khi có phép thử xác nhận tác động đến SLO cùng guardrails/rollback.
- [ ] Tôi ghi rõ mức tin cậy và thiếu sót thay vì đưa ra root cause chắc chắn khi dữ liệu không đủ.

## 20. Kết luận

**Phân tích tự động giúp tìm nơi đáng nhìn trước; bằng chứng JFR gốc và ngữ cảnh tải mới quyết định có thể tin kết luận đến đâu.** Trình tự chẩn đoán đúng là:

**Phát hiện tự động → xác minh recording và event coverage → tính lại metric trên đúng window → ghép timeline SLO/trace/OS → chuẩn hóa workload → loại trừ giả thuyết cạnh tranh → thử nghiệm có đối chứng → kết luận có giới hạn.**

Khi công cụ đưa một cảnh báo hấp dẫn nhưng không chỉ được đúng event, đúng thời điểm, đúng nguồn tài nguyên và tác động lên hành vi người dùng, cách xử lý chính xác là **thu thêm bằng chứng**. Ngược lại, khi raw events, application traces và workload context cùng chỉ vào một cơ chế và phép thử xác nhận cải thiện, kết quả tự động đã hoàn thành vai trò của nó: giúp rút ngắn con đường từ quan sát tới quyết định kỹ thuật có thể kiểm tra.

### Tài liệu tham khảo

- Oracle JDK 21 — jfr command (summary, metadata, print, view): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 17 — Troubleshoot Performance Issues Using JFR: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — jcmd/JFR controls: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- OpenJDK Mission Control project: https://github.com/openjdk/jmc
