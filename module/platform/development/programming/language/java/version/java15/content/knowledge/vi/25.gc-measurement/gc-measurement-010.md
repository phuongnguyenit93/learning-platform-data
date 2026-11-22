# Chọn cấu hình GC tối thiểu dựa trên bằng chứng — Java 15 và JDK hiện đại

## Mục tiêu

Một ứng dụng Java có thể dùng hàng chục cờ JVM để điều chỉnh garbage collection (GC). Nhưng **càng nhiều cờ không đồng nghĩa càng nhanh, càng ít GC pause hoặc càng ổn định**. Những heuristic mặc định của JVM được phát triển và thay đổi theo phiên bản; một cấu hình từng có ích cho workload khác hoặc JDK cũ có thể vô tác dụng, làm giảm hiệu năng, thậm chí không còn được hỗ trợ.

Bài thuộc nhóm **Đo lường GC** của Java 15 và trả lời câu hỏi thực tế: **làm thế nào chọn cấu hình ít tùy chọn nhất nhưng vẫn đáp ứng các ràng buộc hiệu năng, bộ nhớ và độ tin cậy đã đo được?**

Bạn sẽ học:

1. Đặt mục tiêu có thể đo: **p99 latency, throughput, CPU, RSS, heap headroom, Full GC và allocation stalls**.
2. Lấy **baseline mặc định**, không đoán JVM đã chọn collector hoặc heap size nào.
3. Dùng **GC unified logging, JFR, JMX, OS/container metrics** để phân biệt triệu chứng với nguyên nhân.
4. Thực hiện thí nghiệm **mỗi lần thay một giả thuyết/cấu hình nhỏ**, không sửa hàng loạt cờ.
5. Phân biệt **G1 pause-time goal** với cam kết độ trễ thực tế; chỉ chọn ZGC khi có bằng chứng cần trade-off.
6. Quyết định dựa trên **nhiều lần chạy, mọi SLO và giới hạn chi phí**, không nhìn mỗi con số GC pause.
7. Chạy ví dụ **Java 17+** có mã nguồn đầy đủ, kiểm tra policy dựa trên dữ liệu đo và trả về cấu hình đạt mục tiêu với **ít flag nhất**.

**Giới hạn kiến thức hiện hành:** Bài chỉ đề xuất cách đo và các cờ GC còn áp dụng trên JDK hiện đại. **ZGC từ JDK 24 chỉ còn chế độ generational**; không dùng tùy chọn điều khiển `ZGenerational` cũ. Những collector/cờ đã bị loại như CMS hoặc các mẹo nội bộ của JDK rất cũ không phải phương án cho cấu hình mới. Java 15 là ngữ cảnh của module; phần mã mẫu biên dịch với `--release 17` và chỉ dùng Java API ổn định.

## 1. “Tối thiểu” không phải “ít RAM nhất” hay “ít pause nhất”

Trong thực hành, **cấu hình tối thiểu** có nghĩa:

> Trong các cấu hình có đủ bằng chứng và **đáp ứng đồng thời mọi điều kiện bắt buộc**, ưu tiên cấu hình ít override mặc định nhất, đơn giản nhất để giải thích, duy trì và nâng cấp.

Đây là nguyên tắc vận hành, không phải thuật toán mặc định do JVM tự áp dụng.

Một bộ tiêu chí ví dụ (số **minh họa**, không phải SLO chung):

| Điều kiện bắt buộc | Ngưỡng ví dụ | Tại sao cần |
| --- | ---: | --- |
| API p99 latency | ≤ 40 ms | Bảo vệ trải nghiệm tại tail latency |
| Throughput tại tải mục tiêu | ≥ 1.000 req/s | Không được giảm công suất chỉ để giảm GC pause |
| CPU của tiến trình | ≤ 2,0 core-equivalents | Không vượt ngân sách CPU |
| RSS đỉnh của tiến trình | ≤ 1.024 MiB | Không vượt memory budget dành cho tiến trình |
| Full GC bất thường | 0 trong khoảng thử | Tránh những lần dừng dài hoặc sự cố thu gom |
| Allocation stall không được phép | 0 trong khoảng thử | Phát hiện ứng dụng phải chờ cấp phát |

Các điều kiện trên phải được định nghĩa cho **tải, thời lượng và môi trường cụ thể**. Ví dụ, Full GC count không phải cùng một tín hiệu giữa mọi collector: cần hiểu log, hành vi cụ thể và bổ sung mục tiêu như OOM, allocation stall, GC failures theo công nghệ dùng.

**Không tối ưu một chỉ số đơn lẻ:** ZGC có thể giảm đáng kể pause nhưng tăng CPU hoặc giảm throughput; một heap lớn có thể làm giảm tần suất GC nhưng tăng RSS. Nếu cấu hình không đáp ứng budget tổng thể, nó không phải “tốt nhất” chỉ vì GC pause nhỏ nhất.

### 1.1. Cấu hình ít flag giúp ích gì?

- Dễ giải thích: mỗi flag thêm vào có một giả thuyết và phép đo chứng minh.
- Dễ nâng JDK: giảm phụ thuộc heuristic/chi tiết JVM đã thay đổi.
- Dễ debug: ít tương tác giữa các cờ khiến nguyên nhân khó xác định.
- Dễ rollback: một thay đổi có tác dụng xấu thì hoàn tác đúng nó.
- Dễ giám sát: biết collector nào đang chạy, giới hạn heap thực và các điều kiện đã phê duyệt.

**Tối thiểu không có nghĩa phải để mọi thông số mặc định bằng mọi giá.** Nếu container có memory limit, đặt `-Xmx` theo ngân sách là một quyết định có cơ sở ngay cả khi không cần đổi collector. Nếu target p99 rất gắt, chọn ZGC có thể là lựa chọn tối thiểu phù hợp.

## 2. Baseline: hãy đo trước khi chỉnh

Hướng dẫn hiện hành cho G1 thường khuyên bắt đầu với **cài đặt mặc định**, có thể xác định giới hạn heap bằng `-Xmx` nếu cần, và chỉ điều chỉnh mục tiêu pause khi phép đo cho thấy cần. Hướng dẫn ZGC cũng nhấn mạnh **heap max/headroom** là tham số tuning quan trọng.

### 2.1. Các bước baseline

1. Ghi rõ **JDK vendor, version, build, OS, CPU quota, memory limit, loại container/VM**.
2. Chạy ứng dụng bằng **cấu hình JVM hiện tại** mà không thêm một loạt flag thử nghiệm.
3. Xác nhận GC đã chọn qua startup log, không giả định mọi server JVM đều dùng cùng một collector.
4. Ghi `-Xms/-Xmx` hoặc heap max hiệu dụng, heap used/committed, process RSS, CPU, allocation rate.
5. Thu **GC log** và request latency với timestamp có thể đối chiếu.
6. Chạy **workload đại diện** trong khoảng đủ dài: warm-up, steady-state, burst, recovery.
7. Giữ baseline có thể tái tạo: command line, image, config, version, commit của ứng dụng, dữ liệu thử và điều kiện môi trường.

Ví dụ bật logging mà **không đổi collector**:

```bash
java '-Xlog:gc*,safepoint=info:file=gc-baseline.log:time,uptime,level,tags:filecount=3,filesize=20m' \
  -jar service.jar
```

Đây là lệnh Bash, không phải lệnh Java hoàn chỉnh nếu chưa có `service.jar` thực tế. Trên PowerShell, nhập trên **một dòng**. Cờ `-Xlog` chỉ bật logging; nó không tự chọn GC.

Xem GC hiện tại trên HotSpot:

```bash
java -Xlog:gc -version
```

Dòng “Using ...” cho biết collector của lần chạy ấy, nhưng **không thay thế kiểm tra command line và startup log của chính service production**. Một container/service có thể có flag hoặc điều kiện khác với câu lệnh `java -version` bạn chạy ngoài môi trường.

### 2.2. Baseline phải chứa SLO nghiệp vụ

Không nên tạo baseline chỉ gồm:

```text
GC pause p99 = 5 ms
GC count     = 200
```

Nó bỏ sót CPU, bộ nhớ, throughput và request latency. Nên có ít nhất:

| Nhóm đo | Dữ liệu |
| --- | --- |
| Workload | req/s thực tế, concurrency, payload size, traffic mix, dataset |
| Ứng dụng | p50/p95/**p99**/p99.9, max latency, error/timeout rate |
| JVM | collector, JDK build, heap used/committed/max, allocation rate, GC cycles |
| GC | STW pause distribution, Full GC, allocation stalls, concurrent phases |
| Hệ điều hành | process CPU, RSS/working set, CPU quota/throttling |
| Container | memory usage/limit, OOM kills, CPU throttling |
| Chi phí | resource budget và throughput trong SLO |

**GC pause và request latency là hai loại thời gian khác nhau**. Một request p99 cao có thể do database, network, lock, CPU throttling hoặc queueing. Không sửa JVM flags để chữa một nguyên nhân chưa được xác định.

## 3. Thử nghiệm phải có giả thuyết, không phải “copy danh sách flag”

Một thí nghiệm tốt có cấu trúc:

```text
Quan sát -> Giả thuyết -> Chỉ một thay đổi có mục đích
        -> Chạy cùng workload -> Đo cùng metric
        -> Đạt mọi ngưỡng? -> Giữ hoặc rollback
```

Ví dụ:

- **Quan sát:** p99 tăng cùng thời điểm heap gần Xmx và GC chạy liên tục.
- **Giả thuyết:** không đủ heap headroom gây áp lực GC.
- **Thay đổi nhỏ:** tăng `-Xmx` một mức **vẫn nằm trong memory budget của container**.
- **Kiểm chứng:** p99/throughput được cải thiện? RSS và CPU vẫn chấp nhận? Full GC/stalls giảm?
- **Quyết định:** giữ chỉ khi đáp ứng mục tiêu; nếu không, hoàn tác và điều tra hướng khác.

Ngược lại:

- **Quan sát:** p99 tăng nhưng GC log không có pause/stall bất thường; tracing cho thấy database chậm.
- **Giả thuyết đúng:** DB/index/queueing có vấn đề.
- **Hành động:** điều tra database, không tự thêm `-XX:MaxGCPauseMillis` hoặc bật ZGC.

### 3.1. Mỗi lần đổi một biến có ý nghĩa

Khi đánh giá cờ GC, cố gắng giữ nguyên các yếu tố còn lại. Có những trường hợp một **phương án collector** cần thêm flag để mô tả chính nó; so sánh G1 và ZGC là **một thí nghiệm thay collector** đã định nghĩa, không phải phép đo tác dụng của từng flag cùng lúc.

Một ma trận ví dụ:

| Cấu hình | Flags thay đổi | Giả thuyết |
| --- | --- | --- |
| Baseline | Không override GC/heap mới | Xem JVM mặc định đã đủ chưa |
| Heap 768 MiB | `-Xmx768m` | Tăng headroom có thể giảm áp lực thu gom |
| G1 với mục tiêu pause | `-Xmx768m -XX:+UseG1GC -XX:MaxGCPauseMillis=80` | Nếu p99 bị chi phối bởi G1 pauses, mục tiêu mềm 80 ms có thể cải thiện |
| ZGC hiện đại | `-Xmx768m -XX:+UseZGC` | Nếu cần GC pauses thấp hơn và chấp nhận CPU/throughput trade-off |

**Mọi giá trị heap và pause trong bảng chỉ là ví dụ**, không phải cấu hình chuẩn khuyến nghị. Khi chạy thử, đảm bảo `-Xmx768m` nhỏ hơn ngân sách JVM heap thực sự khả dụng. Nếu baseline đã đạt SLO và chi phí, **đừng đổi chỉ để “cho hiện đại”**.

## 4. Đọc bằng chứng trước khi chọn flag

### 4.1. G1: mục tiêu pause là soft goal, không phải deadline

G1 được thiết kế cân bằng throughput và pause. Một cấu hình có thể là:

```bash
java -Xmx768m -XX:+UseG1GC -XX:MaxGCPauseMillis=80 -jar service.jar
```

- `-XX:MaxGCPauseMillis=80` là **mục tiêu mềm** để JVM điều chỉnh quá trình thu gom, **không phải cam kết mọi pause dưới 80 ms**.
- Giảm mục tiêu pause có thể làm G1 chọn vùng young nhỏ hơn, tăng tần suất GC hoặc overhead; điều này có thể ảnh hưởng throughput.
- Nếu mục tiêu quá gắt hoặc heap headroom thiếu, G1 có thể không đạt và request p99 cũng chưa chắc cải thiện.

Hướng dẫn hiện hành khuyến nghị **không khóa young generation bằng `-Xmn`/`-XX:NewRatio` trong cấu hình G1 thông thường** vì thao tác này có thể vô hiệu hóa phần lớn khả năng điều chỉnh young generation để đạt pause goal.

Chỉ thêm pause target khi **có bằng chứng G1 pauses góp phần vào vấn đề latency**, và phải xem tác động tới các điều kiện còn lại.

### 4.2. ZGC: chọn vì yêu cầu latency, không vì mặc định phải dùng

ZGC làm nhiều công việc concurrent, nhắm tới GC pauses thấp. Cấu hình khởi đầu đơn giản:

```bash
java -Xmx768m -XX:+UseZGC -jar service.jar
```

- ZGC có thể giảm các pha stop-the-world nhưng cần CPU và **heap headroom** để chạy concurrent.
- Nếu allocation rate cao và heap quá sát live set, vẫn có thể xuất hiện **allocation stalls**, gây request latency dù STW pause rất nhỏ.
- Thử ZGC phải quan sát **throughput, CPU, RSS, p99 và stalls** cùng thời gian với GC log.
- Trên **JDK 24+**, ZGC chỉ còn **generational**; không bật tùy chọn `ZGenerational` đã bị loại.

Đừng áp dụng mù quáng `-XX:MaxGCPauseMillis` như một “núm vặn pause” tương đương cho mọi collector. Cờ có ý nghĩa thực tế theo thuật toán GC và tài liệu version; G1 và ZGC có cơ chế kiểm soát khác nhau.

### 4.3. Heap sizing thường đáng thử trước những cờ quá chi tiết

- `-Xmx` đặt **heap ceiling**, không giới hạn tổng RSS của JVM.
- `-Xms` đặt heap ban đầu/tối thiểu theo cơ chế JVM; để `-Xms` thấp hơn `-Xmx` có thể cho phép điều chỉnh footprint khi cần.
- Đặt `-Xms=Xmx` có thể giảm thay đổi kích thước heap nhưng tăng footprint; với ZGC nó cũng hạn chế khả năng uncommit dưới minimum.
- `-XX:SoftMaxHeapSize` là **soft goal của ZGC**, không phải trần cứng: ZGC vẫn có thể dùng tới Xmx khi cần tránh stall.
- Không đặt `-Xmx` bằng toàn bộ memory limit container vì JVM còn metaspace, code cache, thread stacks, direct buffers và native memory.

Các flag như số lượng GC threads, kích thước region, young generation size, tenuring, parallel reference processing chỉ nên được điều chỉnh **sau khi log chỉ rõ nút thắt cụ thể** và tài liệu **đúng JDK release** xác nhận ý nghĩa hiện hành.

## 5. Xác định phép đo nào có ý nghĩa

### 5.1. Các percentiles

Request latency **p99** là thời gian mà khoảng 99% request trong một tập quan sát không vượt quá, theo cách tính percentile của hệ thống đo. Nó không phải GC pause p99 và không phải giá trị trung bình.

Nếu một lần test có p99=39 ms và lần khác p99=43 ms, không đủ cơ sở kết luận chỉ từ một lần chạy rằng thay đổi đã cải thiện; cần xem:

- Số lượng request/bucket, thời lượng đo và sampling.
- Tính tương đương của workload.
- Warm-up/JIT và outliers.
- Nhiều lần chạy, variance/confidence, so sánh worst acceptable run.
- Error rate, retry, timeout: việc loại bỏ request thất bại khỏi latency histogram có thể làm p99 trông đẹp hơn sai lệch.

### 5.2. GC log và JFR

Bật log GC/safepoint có rotation:

```bash
java '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=3,filesize=20m' \
  -jar service.jar
```

Phân biệt:

- **Pause ...**: thời gian dừng ứng dụng cho một pha GC.
- **Concurrent ...**: công việc GC chạy đồng thời, **không được coi toàn bộ là stop-the-world**.
- **Garbage Collection ...** hoặc summary cycle: duration toàn chu kỳ, có thể bao gồm concurrent work.
- **Allocation Stall**, Full GC, evacuation failure hoặc thông báo phù hợp collector/version: tín hiệu cần tìm nguyên nhân.

Không đưa ra điều kiện “GC pause nhỏ nhất là thắng” nếu request p99/throughput/RSS không đáp ứng.

Khi cần điều tra sâu, dùng **Java Flight Recorder**:

```bash
java -XX:StartFlightRecording=filename=gc-evidence.jfr,settings=profile,dumponexit=true \
  -jar service.jar
```

JFR có thể giúp liên kết CPU, allocation, GC, safepoints, lock và thread scheduling. Nó không thay thế việc đo process RSS từ OS. Ghi rõ overhead/log retention; không mặc định bật ghi cực chi tiết mọi lúc.

### 5.3. RSS và CPU cần đúng đối tượng đo

| Tên metric | Nguồn phổ biến | Điều không nên suy ra |
| --- | --- | --- |
| Heap used/committed/max | `MemoryMXBean`/JMX, `jcmd GC.heap_info` | Không bằng process RSS |
| Process CPU time | OS, JDK management APIs | Không tách riêng GC CPU |
| Process RSS/working set | `ps`/`/proc`/PowerShell `Get-Process` | Không bằng container memory |
| Cgroup memory usage | cgroup v2/Prometheus/cAdvisor | Không chỉ của một process nếu nhiều process/cache |
| CPU throttling | cgroup `cpu.stat` | CPU% thấp không đồng nghĩa dư CPU |
| Native memory categories | NMT/`jcmd` | NMT reserved/committed không phải RSS |
| Application p99 | APM, tracing, load generator | Không suy được chỉ từ GC log |

**Không cộng heap used với RSS**: các trang heap resident đã nằm trong resident memory theo cách OS tính. Không lấy `RSS - used` làm số “native leak” chính xác vì committed/reserved/shared mappings khác nhau.

### 5.4. Nhiều lần chạy và khoảng tin cậy

Ba lần chạy là **ngưỡng tối thiểu minh họa** trong chương trình demo phía dưới, không phải số lượng mẫu thống kê luôn đủ để triển khai. Với hệ thống production:

- Chạy nhiều lần với thứ tự nhánh được luân phiên/randomize khi thích hợp.
- Sử dụng thời gian warm-up đủ dài, đo steady-state riêng.
- Đo peak/burst và recovery, không chỉ tải trung bình.
- Báo giá trị trung vị, phân tán, peak và phân bố request latency theo số lượng request thực.
- Nếu các khoảng kết quả chồng lấn hoặc variance lớn, **không tuyên bố có cải thiện** chỉ vì một run tốt.
- Không cherry-pick lần chạy có số đẹp nhất.

Ví dụ thuật toán demo **yêu cầu mọi run vượt qua mọi ngưỡng** (gating bảo thủ). Trong production, policy cần dựa trên SLO thực và phương pháp thống kê phù hợp thay vì bê nguyên các con số ví dụ.

## 6. Từ log đến quyết định: một ma trận thay đổi nhỏ

| Quan sát dưới tải | Giả thuyết cần xác minh | Thay đổi đầu tiên đáng thử |
| --- | --- | --- |
| Heap thường sát max, GC liên tục, có stalls | Không đủ headroom | Thử tăng Xmx trong budget; đo RSS và p99 |
| G1 pauses trùng với p99 spikes | Pause GC đóng góp đáng kể | Thử goal G1, đo p99 + throughput |
| GC pause không bất thường, DB chậm | Nút thắt ngoài GC | Không thay GC; điều tra DB/queue |
| ZGC pause thấp nhưng CPU tăng, RPS giảm | Concurrent overhead/CPU quota | So GC activity, CPU throttling, cân nhắc collector khác |
| RSS gần container limit dù heap used thấp | Native/committed/mappings khác | NMT/OS/cgroup; không vội tăng Xmx |
| Full GC/evacuation failure G1 | Heap pressure/live data/large objects | Phân tích log, object churn, heap headroom |
| OOM-kill dù heap chưa đạt Xmx | Tổng cgroup memory vượt limit | Điều chỉnh native+heap memory budget |
| Các lần run biến động lớn | Môi trường/workload không ổn định | Ổn định test, đo lại trước khi tune |
| Baseline đáp ứng SLO | Không có lý do đổi collector | Giữ mặc định, chỉ giám sát |

**Mấu chốt:** Một phép thử phải có **giả thuyết trước**, không tự nghĩ giả thuyết sau khi nhìn thấy một kết quả thuận lợi.

## 7. Chương trình Java hoàn chỉnh: chọn cấu hình ít flag nhất từ bằng chứng

Chương trình bên dưới hiện thực **bộ lọc điều kiện** có thể chạy độc lập trên **JDK 17+**. Nó nhận kết quả các lần benchmark theo schema CSV hoặc mặc định dùng **bộ dữ liệu tự tạo hoàn toàn giả lập**.

**Ranh giới bắt buộc:** Các giá trị hardcode trong fixture **không phải đo đạc thực tế**, không có ý nghĩa rằng `-Xmx768m` luôn tốt nhất. Fixture chỉ dùng để **kiểm chứng thuật toán ra quyết định**. Khi đánh giá hệ thống thật, bạn phải cấp CSV từ monitoring/load test của chính service và rà soát tính hợp lệ của dữ liệu.

### 7.1. Chính sách ví dụ

Giả sử chỉ chấp nhận cấu hình nếu **cả ba lần chạy** đều:

- p99 không quá **40 ms**;
- throughput không dưới **1.000 req/s**;
- process CPU không quá **2,0 core-equivalents**;
- process RSS peak không quá **1.024 MiB**;
- không có Full GC bất thường hoặc allocation stall được log trong khoảng đo.

Trong những cấu hình PASS, chọn **số JVM flag ít nhất**. Nếu hòa thì giữ thứ tự được khai báo để quyết định deterministic; trong thực tế cần thêm bước đánh giá rủi ro, maintenance và confidence. Nếu không ai đạt, in `selected=NONE` — **không ép chọn một cấu hình không đáp ứng điều kiện**.

Các trường CSV `fullGc` và `allocationStalls` yêu cầu người làm benchmark **định nghĩa và thu thập từ log theo collector**. Khi collector không có sự kiện cùng tên, phải xây policy tương đương về GC failures/stalls thay vì giả định “không thấy dòng log = 0” một cách mù quáng.

### 7.2. Mã đầy đủ: GcMinimalEvidenceDemo.java

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class GcMinimalEvidenceDemo {
    private record Run(String config, double p99Ms, double rps,
                       double cpuCores, long rssMiB,
                       int fullGc, int allocationStalls) {}

    private static final LinkedHashMap<String, List<String>> OPTIONS =
            new LinkedHashMap<>();

    static {
        OPTIONS.put("baseline", List.of());
        OPTIONS.put("heap768", List.of("-Xmx768m"));
        OPTIONS.put("g1Pause", List.of(
                "-Xmx768m", "-XX:+UseG1GC", "-XX:MaxGCPauseMillis=80"));
        OPTIONS.put("zgc", List.of("-Xmx768m", "-XX:+UseZGC"));
    }

    private static List<Run> fixture() {
        // INVENTED data for learning only, NOT an actual benchmark.
        return List.of(
                new Run("baseline", 58, 1080, 1.25, 690, 0, 0),
                new Run("baseline", 56, 1090, 1.30, 700, 0, 0),
                new Run("baseline", 53, 1060, 1.28, 705, 0, 0),

                new Run("heap768", 36, 1080, 1.40, 860, 0, 0),
                new Run("heap768", 34, 1070, 1.35, 870, 0, 0),
                new Run("heap768", 35, 1060, 1.45, 890, 0, 0),

                new Run("g1Pause", 30, 1050, 1.55, 900, 0, 0),
                new Run("g1Pause", 31, 1040, 1.60, 905, 0, 0),
                new Run("g1Pause", 29, 1060, 1.55, 910, 0, 0),

                new Run("zgc", 9, 990, 1.70, 960, 0, 0),
                new Run("zgc", 10, 1001, 1.75, 965, 0, 0),
                new Run("zgc", 8, 985, 1.72, 970, 0, 0)
        );
    }

    private static List<Run> readCsv(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        if (lines.isEmpty() || !lines.get(0).trim().equals(
                "config,p99Ms,rps,cpuCores,rssMiB,fullGc,allocationStalls")) {
            throw new IllegalArgumentException("Unexpected CSV header");
        }
        List<Run> runs = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            String line = lines.get(i).trim();
            if (line.isEmpty()) continue;
            String[] c = line.split(",", -1);
            if (c.length != 7 || !OPTIONS.containsKey(c[0].trim())) {
                throw new IllegalArgumentException("Bad row " + (i + 1));
            }
            runs.add(new Run(
                    c[0].trim(),
                    Double.parseDouble(c[1].trim()),
                    Double.parseDouble(c[2].trim()),
                    Double.parseDouble(c[3].trim()),
                    Long.parseLong(c[4].trim()),
                    Integer.parseInt(c[5].trim()),
                    Integer.parseInt(c[6].trim())));
        }
        return runs;
    }

    private static void validate(List<Run> runs) {
        for (Run r : runs) {
            if (!Double.isFinite(r.p99Ms) || r.p99Ms <= 0
                    || !Double.isFinite(r.rps) || r.rps <= 0
                    || !Double.isFinite(r.cpuCores) || r.cpuCores < 0
                    || r.rssMiB <= 0 || r.fullGc < 0
                    || r.allocationStalls < 0) {
                throw new IllegalArgumentException(
                        "Invalid measured data in " + r.config);
            }
        }
    }

    private static String gate(List<Run> runs) {
        if (runs.size() < 3) return "too-few-runs";
        for (Run r : runs) {
            if (r.p99Ms > 40) return "p99";
            if (r.rps < 1000) return "throughput";
            if (r.cpuCores > 2.0) return "cpu";
            if (r.rssMiB > 1024) return "rss";
            if (r.fullGc > 0) return "full-gc";
            if (r.allocationStalls > 0) return "allocation-stall";
        }
        return "PASS";
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException("Usage: java GcMinimalEvidenceDemo [measurements.csv]");
        }
        boolean fromCsv = args.length == 1;
        List<Run> data = fromCsv ? readCsv(Path.of(args[0])) : fixture();
        validate(data);

        Map<String, String> results = new LinkedHashMap<>();
        System.out.println("source=" + (fromCsv ? "CSV" : "SYNTHETIC_FIXTURE"));
        for (String name : OPTIONS.keySet()) {
            List<Run> sample = data.stream()
                    .filter(r -> r.config.equals(name)).toList();
            String result = gate(sample);
            results.put(name, result);
            System.out.println(name + "=" +
                    (result.equals("PASS") ? "PASS" : "REJECT:" + result));
        }

        String selected = "NONE";
        for (String name : OPTIONS.keySet()) {
            if (results.get(name).equals("PASS")
                    && (selected.equals("NONE")
                        || OPTIONS.get(name).size() < OPTIONS.get(selected).size())) {
                selected = name;
            }
        }
        System.out.println("selected=" + selected);
        System.out.println("flags=" + (selected.equals("NONE")
                ? "N/A" : String.join(" ", OPTIONS.get(selected))));

        if (!fromCsv) {
            if (!selected.equals("heap768")) {
                throw new AssertionError("Fixture outcome unexpectedly changed");
            }
            System.out.println("fixtureDecision=PASS");
        }
    }
}
```

### 7.3. Biên dịch, chạy và expected stdout

```bash
javac --release 17 -encoding UTF-8 GcMinimalEvidenceDemo.java
java GcMinimalEvidenceDemo
```

**Stdout chính xác với dữ liệu giả lập mặc định:**

```text
source=SYNTHETIC_FIXTURE
baseline=REJECT:p99
heap768=PASS
g1Pause=PASS
zgc=REJECT:throughput
selected=heap768
flags=-Xmx768m
fixtureDecision=PASS
```

Giải thích:

- `baseline=REJECT:p99`: cả ba lần baseline đều vượt mục tiêu 40 ms, dù throughput/RSS/CPU trong giả lập ổn.
- `heap768=PASS`: trong fixture, cả ba lần đều đạt mọi ngưỡng với **một flag**.
- `g1Pause=PASS`: cũng đạt nhưng có **ba flag**, nên không được ưu tiên chỉ vì p99 có thể thấp hơn một chút.
- `zgc=REJECT:throughput`: giả lập có p99 chỉ khoảng 8–10 ms, **nhưng có run không đạt 1.000 req/s**. Low latency không thay thế yêu cầu throughput.
- `selected=heap768` là kết quả **chỉ của dữ liệu giả lập**, không phải lời khuyên mọi service dùng `-Xmx768m`.
- `fixtureDecision=PASS` kiểm tra rằng thuật toán vẫn ra expected selection khi fixture không đổi.

Đoạn code **không chạy load test và không tự thu GC logs**. Nó chỉ đưa ra **lựa chọn chính sách** từ dữ liệu đã có. Đó là tách trách nhiệm đúng: công cụ load test/monitoring cung cấp bằng chứng, bộ lọc đánh giá điều kiện đã được định nghĩa.

### 7.4. Chạy với CSV đo thực tế

Lệnh:

```bash
java GcMinimalEvidenceDemo measurements.csv
```

Schema file `measurements.csv`:

```csv
config,p99Ms,rps,cpuCores,rssMiB,fullGc,allocationStalls
baseline,58,1080,1.25,690,0,0
baseline,56,1090,1.30,700,0,0
baseline,53,1060,1.28,705,0,0
heap768,36,1080,1.40,860,0,0
heap768,34,1070,1.35,870,0,0
heap768,35,1060,1.45,890,0,0
g1Pause,30,1050,1.55,900,0,0
g1Pause,31,1040,1.60,905,0,0
g1Pause,29,1060,1.55,910,0,0
zgc,9,990,1.70,960,0,0
zgc,10,1001,1.75,965,0,0
zgc,8,985,1.72,970,0,0
```

Các hàng CSV **vẫn là dữ liệu giả lập giống fixture**, chỉ dùng để thử nhánh đọc file. **Khi làm việc thật, thay bằng metric được thu từ hệ thống của bạn**, ghi rõ mỗi row là một lần chạy đã warm-up và đo trong cửa sổ tải nào.

Output với CSV mẫu giống về trạng thái lựa chọn, nhưng dòng đầu là `source=CSV` và **không có `fixtureDecision=PASS`**. Điều này giúp người học phân biệt chế độ đang dùng file đầu vào với fixture nội bộ.

### 7.5. Giới hạn của thuật toán demo

Bộ lọc có chủ ý **đơn giản và bảo thủ** để dạy nguyên tắc:

- Mỗi candidate phải có **ít nhất 3 run**; đây **không phải** yêu cầu thống kê đủ cho mọi dịch vụ thật.
- Một run vi phạm bất kỳ ngưỡng nào khiến candidate bị từ chối.
- Nó chỉ in **lý do đầu tiên** theo thứ tự p99 → throughput → CPU → RSS → Full GC → stalls, không in tất cả vi phạm.
- “Ít flag nhất” là proxy cho **độ đơn giản**, không đo toàn bộ rủi ro vận hành.
- Không tự kiểm tra độ tin cậy của monitoring, cách thu CPU% hay RSS, tính tương đương của các lần load test.
- Không tự phát hiện collector thực tế của mỗi run; **người thu dữ liệu phải xác minh** JVM đã chạy đúng flags/collector và lưu artifact.
- Không phân biệt các cảnh báo riêng cho mỗi GC nếu CSV được tính sai; phải chuẩn hóa schema theo policy.

**Vì vậy, đừng nối thẳng output của chương trình vào quy trình deploy tự động mà bỏ review.** Bộ lọc là một bước trợ giúp sau khi dữ liệu đã được QA, không thay thế đánh giá tính đúng của thử nghiệm.

## 8. Thu thập dữ liệu thật theo từng candidate

Với service thực, mỗi candidate cần cùng một test protocol:

1. Triển khai cùng binary/application commit, JDK build, OS, dataset và runtime limits.
2. Chạy warm-up đủ để JIT, cache và connection pools ổn định.
3. Chạy steady-state ở tải mục tiêu và ghi số request thành công/thất bại.
4. Chạy peak/burst nếu production có spike, không chỉ steady-state.
5. Ghi application latency/throughput, process CPU/RSS và GC log/JFR trong cùng timeframe.
6. Lặp lại nhiều lần với thứ tự thay đổi nhánh hợp lý để giảm ảnh hưởng môi trường.
7. Thu số đo rồi lập `measurements.csv` với **định nghĩa rõ ràng cho từng cột**.

Một row không nên là “số đẹp nhất” đã chọn tùy ý. Chẳng hạn `p99Ms` là p99 **của chính lần chạy đó**, `rps` là throughput trong cùng cửa sổ, `cpuCores` là mức quy đổi core từ process CPU time, `rssMiB` là peak RSS process của run đó, `fullGc`/`allocationStalls` là số lần sự kiện đã định nghĩa trong khoảng đo.

### 8.1. CPU core-equivalent

Có thể lấy từ chênh lệch **process CPU time** trong một khoảng:

```text
cpuCoreEquivalents =
    (processCpuTimeNs_end - processCpuTimeNs_start)
    / (monotonicWallTimeNs_end - monotonicWallTimeNs_start)
```

Ví dụ tiến trình tiêu thụ 1,7 giây CPU trong 1 giây wall time ⇒ **1,7 core tương đương**, không phải 170% toàn máy. Trong container, xem thêm CPU quota và throttling; một dashboard khác có thể chuẩn hóa % theo toàn host.

Java có `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` trên JDK phù hợp hoặc dùng OS metrics. Ghi phương pháp đo để đối chiếu các run.

### 8.2. Process RSS

Linux:

```bash
ps -o pid=,etime=,%cpu=,rss=,vsz= -p "$pid"
```

`rss` của `ps` thường là **KiB**, phải chia 1024 để thành MiB. Đừng dùng `vsz` (virtual size) thay RSS. Khi chạy trong cgroup/container, `memory.current` là memory charge của **cgroup**, không phải process RSS; nên thu cả hai khi cần đánh giá OOM risk.

Windows:

```powershell
Get-Process -Id 12345 |
    Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64
```

`WorkingSet64` là byte working set trên Windows, **không đồng nhất tuyệt đối với Linux RSS**. Khi nhập file CSV, cần ghi rõ nguồn và chuyển đơn vị nhất quán.

### 8.3. Heap và native memory

- `MemoryMXBean.getHeapMemoryUsage()` cho heap used/committed/max.
- `jcmd <pid> GC.heap_info` cho thông tin heap theo JVM/collector.
- Bật `-XX:NativeMemoryTracking=summary` khi có mục đích điều tra native memory và chấp nhận overhead; sau đó `jcmd <pid> VM.native_memory summary scale=MB`.
- NMT `reserved` là virtual address space, không phải resident RAM; NMT không bao phủ mọi cấp phát thư viện ngoài JVM.
- `-Xmx` là trần **heap**, không phải RSS/process memory limit. Đừng đặt Xmx sát container limit mà quên non-heap/native.

### 8.4. Thông báo lỗi và kết quả cần loại bỏ

Một run **không hợp lệ** nếu:

- Load generator không đạt traffic mục tiêu; request lỗi/timeout bị bỏ khỏi metric làm p99 giả thấp.
- JVM không chạy đúng collector/flags; một flag bị bỏ qua hoặc không nhận.
- Máy khác bị ảnh hưởng bởi background load hoặc quota/host khác nhau.
- GC log/JFR/OS metric thiếu dữ liệu hoặc clock/time window không khớp.
- Chỉ ghi dữ liệu lúc idle, hoặc quên warm-up/JIT.
- Chỉ đọc một lần RSS/CPU thay vì đo trong suốt thời gian thử.

Không điền `0` cho Full GC hoặc stalls nếu **chưa thu được event**. “Không đo được” không có nghĩa “số lần bằng 0”. Hãy làm lại phép thử hoặc đánh dấu dữ liệu thiếu trước khi đưa vào bộ lọc.

## 9. Quy tắc lựa chọn và rollback

Một quyết định có thể được diễn đạt minh bạch:

```text
A. Baseline PASS toàn bộ SLO?
   Có -> giữ baseline, không thêm flag.
   Không -> xác định metric không đạt.

B. Có bằng chứng vấn đề thuộc GC/heap?
   Không -> điều tra ứng dụng, I/O, DB, CPU quota.
   Có -> nêu giả thuyết và thử một thay đổi nhỏ.

C. Candidate PASS toàn bộ latency/throughput/CPU/RSS/stability?
   Không -> rollback; giữ số liệu để học.
   Có -> so với các candidate PASS khác.

D. Có candidate ít override nhất và đủ biên an toàn?
   Có -> chọn sau review, kiểm tra trên canary.
   Không -> bổ sung phép đo hoặc cải thiện code/kiến trúc.
```

Khi nhiều candidate cùng PASS:

- Ưu tiên **cấu hình ít override và dễ quản lý** nếu mức đo đủ biên an toàn.
- Không bỏ qua p99.9/peak/variance chỉ vì p99 vừa qua ngưỡng trong ba lần chạy.
- Kiểm tra sự tương thích với môi trường sẽ dùng khi deploy (JDK build, container limits, cloud instance size).
- Ghi lại **lý do giữ cờ**: metric nào cải thiện, với workload nào, rủi ro nào chấp nhận.
- Dự trù rollback khi nâng JVM, thay CPU quota, thay tải hoặc thay đổi dữ liệu/live set.

Nếu **không candidate nào PASS**, câu trả lời đúng không phải “chọn cái tốt nhất trong những cái lỗi” mà là **xem lại ngân sách, workload, code, kiến trúc, DB hoặc phương án mở rộng capacity**.

### 9.1. Cấu hình cuối nên trông như thế nào?

Giả sử **hệ thống thật** đã có chứng cứ rằng chỉ cần tăng max heap, bản cấu hình có thể là:

```bash
java -Xmx768m \
  '-Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=3,filesize=20m' \
  -jar service.jar
```

Các số/flag chỉ là **cú pháp minh họa**, không phải quyết định từ dữ liệu fixture. Đặt `-Xmx` theo ngân sách production; logging có thể có yêu cầu retention khác. Không giữ thêm các flag đã thử nhưng không chứng minh được lợi ích.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “Càng nhiều -XX thì càng tối ưu” | Khó nâng JDK, khó tìm nguyên nhân | Bắt đầu defaults; mỗi flag phải có bằng chứng |
| Copy cờ từ blog cũ | Flag bị bỏ, đổi nghĩa hoặc không còn hiệu quả | Dùng tài liệu đúng release/JDK |
| Đặt mục tiêu G1 pause như SLA cứng | JVM có thể không đạt trong mọi tình huống | Coi là **soft goal**, đo GC/request latency thật |
| Thấy p99 cao rồi lập tức bật ZGC | Có thể nguyên nhân ở DB/lock/CPU | Đối chiếu tracing với GC logs trước |
| Chỉ tối ưu max GC pause | Bỏ qua throughput, CPU, RSS, allocation stalls | Chọn theo multi-metric SLO |
| Một run đẹp là kết luận | Variance, warm-up, nhiễu môi trường | Nhiều lần chạy và đo burst/steady |
| Dùng p99 của GC thay p99 request | Hai metric khác nhau | Giữ cả hai và time alignment |
| Đọc `heap used` như RSS | Native/mappings/committed không được tính đúng | Lấy process RSS từ OS |
| Dùng `-Xmx` bằng container limit | OOM-kill vì native memory | Dành headroom toàn tiến trình |
| Thay 5 flag cùng lúc | Không quy được nguyên nhân | Giữ một giả thuyết/thay đổi rõ |
| Force young generation G1 không có bằng chứng | Giảm khả năng thích nghi pause goal | Cho G1 tự điều chỉnh theo defaults |
| Dùng `ZGenerational` trên JDK 24+ | Cờ không còn được hỗ trợ | Bật `-XX:+UseZGC` nếu cần ZGC |
| Bỏ qua CPU quota của ZGC | Concurrent workers thiếu CPU, stalls tăng | Xem cgroup throttling/CPU load |
| Chỉ kiểm tra trung bình | Bỏ qua tail latency của request | p95/p99/p99.9, error rate |
| Bỏ qua throughput khi ZGC giảm pause | Có thể không đạt tải mục tiêu | Coi throughput là điều kiện bắt buộc |
| Điền số zero cho sự kiện chưa đo | Candidate PASS giả | Loại bỏ run thiếu dữ liệu |
| So G1/ZGC ở hai JDK/host khác nhau | Không kết luận được về collector | Giữ điều kiện thử giống nhau |
| Thử synthetic fixture và gọi là benchmark thật | Quyết định không có giá trị vận hành | Thu dữ liệu thật và QA nguồn metrics |
| Không lưu log/command/version | Không tái tạo được cấu hình | Lưu artifact đo và rollback plan |
| Đổi flag chỉ vì GC count tăng | GC count không phải SLO | Xem pause, CPU, memory và ứng dụng |

## 11. Bài tập và đáp án

**Bài 1.** Baseline đã đạt p99, throughput, CPU, RSS và không có stalls. Có nên thử ZGC rồi luôn deploy vì nó có GC pause ngắn hơn?

**Đáp án:** Không tự động. Nếu baseline đạt mọi mục tiêu, giữ cấu hình đơn giản hơn; ZGC chỉ nên được chọn khi đem lại lợi ích có giá trị và không làm hại ngân sách khác.

**Bài 2.** G1 có một số lần pause vượt `MaxGCPauseMillis=80`. Đây có chứng minh JVM không tuân theo hợp đồng không?

**Đáp án:** Không. Đây là **soft goal**. Cần phân tích log, heap headroom, workload và SLO thực.

**Bài 3.** Một ZGC candidate có p99 9 ms, còn heap-only có p99 35 ms. SLO là p99 ≤ 40 ms, throughput ≥ 1.000 req/s. ZGC chỉ đạt 990 req/s trong một lần chạy. Nên chọn ai nếu heap-only đạt mọi ngưỡng?

**Đáp án:** Theo chính sách bài tập, heap-only PASS, còn ZGC bị loại do không đạt throughput. “GC pause hoặc p99 nhỏ hơn” không đủ để vượt điều kiện bắt buộc khác.

**Bài 4.** Thêm `-Xmx` có thể tăng RSS hay không?

**Đáp án:** Có thể. `-Xmx` là giới hạn heap, không đồng nghĩa process RSS cố định, nhưng tăng headroom có thể cho JVM sử dụng/commit thêm memory. Phải đo footprint thực.

**Bài 5.** Nếu chỉ thấy GC cycle 200 ms trong log, có thể nói ứng dụng đã stop-the-world 200 ms không?

**Đáp án:** Không. Có thể có các pha concurrent. Phải đọc sự kiện pause đúng loại.

**Bài 6.** Vì sao cần giữ log có timestamp và chạy cùng workload giữa baseline/candidate?

**Đáp án:** Để đối chiếu đúng thời điểm GC với request latency, CPU/RSS và tránh kết luận nhầm từ sự thay đổi tải/môi trường.

**Bài 7.** Chương trình mẫu in `selected=heap768`. Có phải mọi Java 15+ service nên dùng `-Xmx768m`?

**Đáp án:** Không. Output sinh từ **fixture hoàn toàn giả lập**. Quyết định thật cần đo ứng dụng thật và xác định ngân sách container/host.

**Bài 8.** Một số run không có GC log nhưng người đánh giá gán `allocationStalls=0`. Lỗi nằm ở đâu?

**Đáp án:** Đây là **dữ liệu thiếu**, không phải xác nhận zero. Phải bổ sung phép đo hoặc loại run khỏi bộ lọc.

**Bài 9.** Có ba candidate PASS: baseline không thêm flag, tăng heap một flag, ZGC hai flag. Nên chọn gì theo nguyên tắc tối thiểu?

**Đáp án:** Baseline nếu đủ margin và đã kiểm thử đáng tin. Không cần thêm cờ chỉ để giảm một metric vốn đã đạt SLO.

## Ghi nhớ

**Cấu hình GC tốt nhất không phải cấu hình có nhiều tùy chọn nhất mà là cấu hình ít override nhất đáp ứng tất cả mục tiêu đã đo.** Bắt đầu bằng baseline với JVM defaults, xác định collector/heap và ghi p99 nghiệp vụ, throughput, CPU, RSS, GC pauses, stalls. Nếu có chỉ số không đạt, nêu **một giả thuyết**, đổi một phần cấu hình có chủ đích, chạy cùng workload nhiều lần, giữ hoặc rollback dựa trên bằng chứng. Với G1, `MaxGCPauseMillis` là **mục tiêu mềm**; với ZGC, hiệu năng phụ thuộc headroom và CPU cho concurrent GC. Trên JDK hiện đại, chỉ áp dụng cờ còn hỗ trợ, không mang mẹo GC cũ sang hệ thống mới.

### Tài liệu chính thức

- [Oracle JDK 25 — Garbage-First Garbage Collector Tuning: ưu tiên defaults và Xmx](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle JDK 25 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/z-garbage-collector.html)
- [Oracle JDK 24 — ZGC generational only, SoftMaxHeapSize, headroom](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html)
- [Oracle JDK 25 — java command, UseG1GC/UseZGC, Xlog, JVM options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [OpenJDK JEP 377 — ZGC production (Java 15)](https://openjdk.org/jeps/377)
- [OpenJDK JEP 439 — Generational ZGC (JDK 21)](https://openjdk.org/jeps/439)
- [OpenJDK JEP 474 — Generational ZGC by Default (JDK 23)](https://openjdk.org/jeps/474)
- [OpenJDK JEP 490 — Remove Non-Generational ZGC (JDK 24)](https://openjdk.org/jeps/490)
- [Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Java SE 17 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
