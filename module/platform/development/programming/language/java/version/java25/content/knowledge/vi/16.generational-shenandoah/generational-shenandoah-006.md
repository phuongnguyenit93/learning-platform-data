# Đo thông lượng, bộ nhớ và phân vị độ trễ với tải đại diện

> **Chương:** Generational Shenandoah  
> **Phiên bản:** Java 25 — JEP 521.  
> **Mục tiêu:** Thiết kế phép đo có thể lặp lại để so sánh G1, Shenandoah SATB và Generational Shenandoah bằng thông lượng ứng dụng, phân vị độ trễ, footprint bộ nhớ và dữ liệu GC.

## 1. Vì sao phải đo bằng workload của ứng dụng?

Một garbage collector có thể giảm thời gian pause nhưng tiêu thụ thêm CPU nền; một collector khác có thể đạt throughput cao nhưng tạo ra đuôi độ trễ lớn hơn. Nếu chỉ nhìn một con số như thời gian pause trung bình hoặc số lần GC, nhóm vận hành có thể chọn sai collector cho hệ thống.

Bài này tập trung vào ba nhóm kết quả:

1. **Thông lượng (throughput):** số thao tác nghiệp vụ thành công mà ứng dụng hoàn tất trong một đơn vị thời gian.
2. **Bộ nhớ (memory footprint):** heap đã dùng/đã commit và bộ nhớ thực tế của tiến trình hoặc container.
3. **Độ trễ (latency):** thời gian phản hồi của từng request, đặc biệt các phân vị p50, p95, p99 và p99.9.

Các số liệu phải được đo dưới **cùng tải đại diện**. Một benchmark chỉ cấp phát object giả lập có thể hữu ích để khảo sát GC, nhưng chưa đủ để quyết định collector cho một dịch vụ có database, cache, network, serialization và concurrency thực tế.

Sau bài học, bạn có thể bật Generational Shenandoah đúng bằng cờ Java 25; xác nhận JVM thực sự chạy collector/mode mong muốn; so sánh ba cấu hình G1, Shenandoah SATB và Shenandoah generational; thiết kế tải mở (open-loop) để đo tail latency; thu thập request rate, p50/p95/p99, heap, RSS/cgroup memory và GC pause; phân tích GC log và đưa ra kết luận dựa trên trade-off.

## 2. Xác nhận trạng thái Generational Shenandoah trong Java 25

Generational Shenandoah được đưa vào thử nghiệm qua JEP 404 và được hoàn thiện trong Java 25 qua **JEP 521**. Đây là tính năng của HotSpot Shenandoah trong JDK 25, không phải Java language preview. Không cần `--enable-preview` và không cần `-XX:+UnlockExperimentalVMOptions` cho cấu hình Java 25 này.

Cờ bật collector và chọn chế độ generational:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -version
~~~

Hai phần có ý nghĩa khác nhau:

| Cờ | Tác dụng |
|---|---|
| `-XX:+UseShenandoahGC` | Chọn Shenandoah làm garbage collector |
| `-XX:ShenandoahGCMode=generational` | Chọn chế độ generational thay cho chế độ một thế hệ SATB |

**Generational không phải mặc định.** Trong Java 25, `ShenandoahGCMode` mặc định là `satb`, tức Shenandoah một thế hệ. Vì vậy, nếu chỉ thêm `-XX:+UseShenandoahGC`, bạn chưa bật generational mode.

### Heuristic được hỗ trợ

`ShenandoahGCHeuristics` mặc định là `adaptive`. Khi chọn `ShenandoahGCMode=generational`, JDK 25 chỉ hỗ trợ heuristic `adaptive`. Không áp dụng các hướng dẫn tuning `static` hoặc `compact` của chế độ SATB cho generational mode.

### Xác nhận cờ và collector

Trước khi chạy benchmark, xác minh đúng runtime:

~~~bash
java --version
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xlog:gc+init=info \
     -version
~~~

Có thể xem các cờ cuối cùng của JVM:

~~~bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -XX:+PrintFlagsFinal \
     -version | grep -E 'UseShenandoahGC|ShenandoahGCMode|ShenandoahGCHeuristics'
~~~

Trong Windows PowerShell, thay `grep -E` bằng `Select-String` hoặc `findstr`. Nếu JDK vendor/build không cung cấp Shenandoah trên nền tảng mục tiêu, lệnh sẽ báo lỗi hoặc không chọn được collector; hãy kiểm tra bản phân phối JDK và nền tảng được hỗ trợ trước khi tiếp tục.

**Không sao chép nguyên hướng dẫn JDK 24:** ở giai đoạn JEP 404, generational mode còn experimental và cần cờ mở khóa experimental. Java 25 dùng cú pháp `ShenandoahGCMode=generational` đã được tài liệu hóa theo JEP 521.

Tài liệu `java` của Oracle JDK 26 và JDK 27 vẫn liệt kê `ShenandoahGCMode=generational`, giữ `satb` làm mặc định và chỉ hỗ trợ heuristic `adaptive` cho generational mode. Điều này xác nhận các cờ trong bài vẫn được duy trì ở các JDK mới hơn; khi triển khai, vẫn cần kiểm tra bản build/vendor và nền tảng thực tế.

## 3. Ba cấu hình cần so sánh

Để xác định lợi ích đến từ generational mode, không chỉ so sánh Generational Shenandoah với G1. Cần thêm Shenandoah SATB để tách ảnh hưởng của collector khỏi ảnh hưởng của cách chia thế hệ.

| Nhãn | Collector | Cờ chính | Mục đích |
|---|---|---|---|
| G1 | G1 GC | `-XX:+UseG1GC` | Baseline phổ biến của HotSpot server |
| Shenandoah SATB | Shenandoah một thế hệ | `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=satb` | Đối chứng cùng collector |
| Shenandoah Gen | Shenandoah generational | `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` | Đo tác động của hai thế hệ |

Có thể dùng cùng một JAR và cùng cấu hình heap, chỉ thay cờ collector giữa các lần chạy. Đừng thay heap size, CPU limit, dependency, workload hoặc JVM version cùng lúc với collector; nếu nhiều biến thay đổi, bạn sẽ không biết biến nào tạo ra khác biệt.

### Lệnh chạy mẫu

Ví dụ dưới đây giả định ứng dụng là `orders.jar`, heap tối đa 4 GB và thư mục `logs` đã được tạo.

**G1:**

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseG1GC \
  -Xlog:gc*,safepoint:file=logs/g1-gc.log:time,uptime,level,tags \
  -jar orders.jar
~~~

**Shenandoah SATB:**

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=satb \
  -Xlog:gc*,safepoint:file=logs/shenandoah-satb-gc.log:time,uptime,level,tags \
  -jar orders.jar
~~~

**Shenandoah generational:**

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc*,safepoint:file=logs/shenandoah-generational-gc.log:time,uptime,level,tags \
  -jar orders.jar
~~~

Các giá trị `4g` chỉ là ví dụ. Chọn heap phù hợp với ứng dụng và giới hạn container, sau đó giữ cùng `-Xms`/`-Xmx` giữa các cấu hình. Nếu production dùng heap tự tăng, benchmark cũng có thể giữ chính sách đó, nhưng phải áp dụng cùng một cách cho cả ba lần chạy và ghi lại heap committed.

## 4. Xác định workload đại diện trước khi đo

GC phản ứng với **tốc độ cấp phát, tuổi thọ object, tập object sống lâu và mức đồng thời**. Workload chỉ gọi một endpoint health hoặc chỉ cấp phát một mảng lớn không phản ánh các đặc tính này.

Với một dịch vụ Spring Boot, workload đại diện nên có các đường chạy như:

| Nhóm nghiệp vụ | Ví dụ | Đặc tính bộ nhớ |
|---|---|---|
| Đọc dữ liệu | Tìm đơn hàng, phân trang, tra cứu khách hàng | DTO, entity, map và object tạm thời |
| Ghi dữ liệu | Tạo/cập nhật đơn hàng | Validation, mapping, transaction và event |
| Serialization | JSON request/response lớn | String, byte array và buffer |
| Cache | Đọc/ghi cache trong ứng dụng | Object sống lâu và cấu trúc tham chiếu |
| Tích hợp | Gọi HTTP/database/message broker | Object tạm, buffer và trạng thái chờ |
| Burst | Tăng nhanh request rate trong thời gian ngắn | Allocation spike và áp lực lên GC |
| Soak | Tải ổn định trong thời gian dài | Xu hướng footprint và old-generation occupancy |

Trước khi đo, xác định tỷ lệ request theo nghiệp vụ, dữ liệu đầu vào, kích thước response, tỷ lệ lỗi, mức concurrency và tốc độ đến của request. Giữ tỷ lệ này cố định giữa các cấu hình.

### Đừng chỉ dùng workload CPU-bound

Một vòng lặp tính toán số nguyên có thể tạo CPU load nhưng không đại diện cho ứng dụng allocation-heavy. Ngược lại, workload chỉ chờ database có thể tạo latency cao mà không tạo đủ áp lực GC. Benchmark tốt cần phản ánh cả cấp phát, object sống lâu, I/O và concurrency của hệ thống thật.

## 5. Chọn mô hình tải: open-loop để đo tail latency

Có hai cách phổ biến để phát tải:

- **Closed-loop:** client gửi request mới sau khi request trước hoàn tất. Khi server chậm, tốc độ gửi tự giảm theo.
- **Open-loop:** client cố gắng gửi request theo tốc độ đã định, không đợi request trước hoàn tất mới quyết định tốc độ tiếp theo.

Khi đo p95/p99 trong điều kiện tải, open-loop giúp tránh hiện tượng coordinated omission: server chậm làm client closed-loop gửi ít request hơn, khiến phần độ trễ xấu có thể bị đánh giá thấp.

Một công cụ có thể dùng là k6 với executor `constant-arrival-rate`. Chạy load generator trên máy riêng để CPU của load generator không tranh tài nguyên với JVM đang đo.

### Ví dụ k6

Tạo file `orders-load.js`:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',
      rate: 250,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 80,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250', 'p(99)<500']
  }
};

export default function () {
  const response = http.get(BASE_URL + '/api/orders?limit=20');
  check(response, {
    'HTTP 200': (r) => r.status === 200
  });
}
~~~

Chạy:

~~~bash
k6 run -e BASE_URL=http://test-host:8080 orders-load.js
~~~

Các con số 250 request/giây, 10 phút và ngưỡng độ trễ chỉ là ví dụ. Điều chỉnh theo SLO và công suất thật của dịch vụ.

### Kiểm tra load generator có theo kịp không

Xem metric `dropped_iterations` của k6. Nếu có iteration bị bỏ vì không đủ virtual users, phép đo không thực hiện đúng arrival rate dự kiến. Tăng `preAllocatedVUs`/`maxVUs` hoặc giảm tốc độ phát tải, rồi chạy lại. Không so sánh hai collector nếu một lượt đo không đạt cùng offered load.

Nếu workload có nhiều endpoint, hãy xây dựng tỷ lệ request gần production, dùng dữ liệu có tính phân bố và tránh để cache luôn nóng theo một ID duy nhất.

## 6. Các chỉ số phải ghi lại

Không dùng một chỉ số đơn lẻ để chọn collector. Thu thập ít nhất bốn nhóm:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Ứng dụng | Successful operations/s hoặc requests/s | Throughput nghiệp vụ thực tế |
| Độ trễ | p50, p95, p99, p99.9, max | Phân bố thời gian phản hồi và tail latency |
| Bộ nhớ | Heap used/committed, RSS, cgroup memory current/peak | Footprint thực tế của tiến trình/container |
| GC | Pause count, pause duration, concurrent cycle time, allocation rate, full/degenerated events | Chi phí và hành vi collector |
| Tài nguyên | CPU user/system, GC CPU, thread count | Chi phí CPU và mức tranh chấp tài nguyên |
| Chất lượng | Error rate, timeout, dropped iterations | Xác nhận tải và kết quả hợp lệ |

### Phân biệt heap với footprint

- **Heap used:** lượng object đang chiếm heap theo số liệu JVM.
- **Heap committed:** vùng heap JVM đã commit và có thể dùng.
- **RSS:** số trang bộ nhớ vật lý hiện đang resident cho tiến trình.
- **Container memory:** mức bộ nhớ container bị tính vào giới hạn cgroup, có thể bao gồm heap, metaspace, code cache, thread stacks, native buffers và phần native khác.

Hai JVM có cùng `-Xmx` vẫn có thể có RSS khác nhau. Vì vậy, không kết luận footprint chỉ từ `-Xmx` hoặc heap used.

### Định nghĩa throughput nhất quán

Trong bài toán web, nên dùng **request thành công mỗi giây** hoặc **thao tác nghiệp vụ hoàn tất mỗi giây**, không chỉ lấy số request client đã gửi. Nếu một iteration có nhiều request, phân biệt rõ iteration/s và request/s. Ghi cả error rate để tránh collector có throughput nhìn cao do trả lỗi sớm.

## 7. Thu thập GC log và xác minh các pha

Unified logging là công cụ cơ bản để phân tích GC trong JDK 25. Tùy chọn:

~~~bash
-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags
~~~

ghi các thông điệp GC và safepoint ra file. Log có thể cho biết:

- Thời điểm bắt đầu/kết thúc collection.
- Pause do GC và thời lượng pause.
- Heap trước/sau collection.
- Các pha concurrent và thời gian thực hiện.
- Allocation failure, degenerated/full GC nếu xảy ra.
- Safepoint khác ngoài GC có thể ảnh hưởng latency.

Không so sánh chỉ tổng số GC cycle. Generational mode có thể chạy young collection thường xuyên hơn; số lần nhiều hơn không tự động có nghĩa tổng chi phí lớn hơn. Hãy xem thời gian pause, tổng thời gian concurrent, lượng bộ nhớ thu hồi, CPU và request latency trong cùng cửa sổ.

### Xác minh collector được chọn

Trong phần đầu GC log, tìm thông báo JVM đã chọn collector. Nếu log không cho thấy Shenandoah hoặc ứng dụng không khởi động với mode mong muốn, dừng phép đo và sửa cấu hình trước khi lấy số liệu.

### Đọc log với cùng time window

Cắt khoảng log tương ứng với thời gian load test. Bỏ giai đoạn startup/warm-up nếu mục tiêu là steady-state. Giữ lại burst và recovery nếu đang đo khả năng phục hồi sau tải tăng đột ngột.

Đừng cộng pause duration rồi coi đó là latency của request. Pause GC chỉ là một phần tác động; concurrent GC còn dùng CPU trong khi ứng dụng chạy, và request latency còn phụ thuộc scheduler, lock, network, database và hàng đợi.

## 8. Đo heap, RSS và container memory

Đo bộ nhớ ở nhiều lớp để thấy được footprint thật.

### 8.1. Heap

Có thể dùng JMX `MemoryMXBean`, `MemoryPoolMXBean`, JFR hoặc công cụ quản trị JVM để thu thập:

- Heap used và committed theo thời gian.
- Mức heap sau collection.
- Xu hướng live set sau các chu kỳ GC.
- Old-generation occupancy nếu có thể quan sát qua metric/log của collector.

Không gọi `System.gc()` định kỳ trong benchmark để cố tạo điểm đo sau GC. Lời gọi đó thay đổi hành vi ứng dụng và làm kết quả khác production.

### 8.2. RSS của tiến trình

Trên Linux, xem RSS:

~~~bash
ps -o pid,rss,vsz,comm -p <PID>
~~~

RSS thường được hiển thị theo KB. Có thể lấy mẫu định kỳ trong cửa sổ benchmark và tính peak/median/steady-state. Nếu dùng container, phải lấy PID trong đúng PID namespace.

### 8.3. Cgroup v2

Trong container Linux dùng cgroup v2, các file phổ biến gồm:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.max
~~~

- `memory.current`: mức memory hiện tại của cgroup.
- `memory.peak`: mức peak đã ghi nhận trong vòng đời cgroup.
- `memory.max`: giới hạn memory của cgroup.

Nếu nền tảng dùng cgroup v1 hoặc đường dẫn cgroup khác, đọc file tương ứng trong mount của hệ thống. Đừng mặc định các đường dẫn trên tồn tại ở mọi container runtime.

### 8.4. Native memory

Heap không bao gồm toàn bộ native memory. Nếu cần phân tích sâu, bật Native Memory Tracking trong một lượt đo riêng:

~~~bash
java -XX:NativeMemoryTracking=summary -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar orders.jar
~~~

Sau khi JVM chạy, dùng:

~~~bash
jcmd <PID> VM.native_memory summary
~~~

NMT có overhead và thay đổi chi phí runtime; nếu so sánh collector, hãy bật cùng cách cho mọi cấu hình và ghi rõ điều này. Không trộn số liệu từ lượt có NMT với lượt không NMT.

## 9. Đọc phân vị độ trễ và liên hệ với GC

Phân vị cho biết phần lớn request hoàn tất dưới một mốc thời gian nhất định:

- **p50:** một nửa request nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% request nhanh hơn hoặc bằng giá trị này.
- **p99:** 99% request nhanh hơn hoặc bằng giá trị này.
- **p99.9:** 99,9% request nhanh hơn hoặc bằng giá trị này.
- **max:** request chậm nhất trong cửa sổ đo; rất nhạy với outlier và số mẫu.

Ví dụ:

| Collector | p50 | p95 | p99 | p99.9 | Throughput |
|---|---:|---:|---:|---:|---:|
| G1 | 18 ms | 90 ms | 180 ms | 420 ms | 2.400 req/s |
| Shenandoah SATB | 17 ms | 75 ms | 140 ms | 310 ms | 2.350 req/s |
| Shenandoah generational | 16 ms | 62 ms | 105 ms | 240 ms | 2.520 req/s |

Các con số trên **chỉ là dữ liệu minh họa**, không phải kết quả benchmark hay cam kết hiệu năng của JEP 521. Kết quả thực tế phụ thuộc ứng dụng, heap, CPU, workload và build JDK.

### Khi p99 tăng nhưng GC pause vẫn thấp

Có thể có các nguyên nhân khác:

- Concurrent GC tranh CPU với application threads.
- Allocation spike làm tăng áp lực cấp phát.
- Old generation thiếu headroom hoặc cycle không kịp hoàn thành.
- Database/network/lock gây chờ.
- Container CPU throttling hoặc host noisy neighbor.

Vì vậy, đối chiếu timeline request với GC log, CPU, memory và dependency latency. Không kết luận GC là nguyên nhân chỉ vì p99 tăng cùng lúc có collection.

## 10. Quy trình benchmark có thể lặp lại

Dùng một quy trình cố định để kết quả giữa các collector có thể so sánh.

### Bước 1 — Cố định môi trường

Ghi lại JDK vendor, full version/build và architecture; OS/kernel, CPU model, số core, NUMA nếu có; CPU quota, memory limit và giới hạn container; JAR hash, dependency version, cấu hình ứng dụng; `-Xms`, `-Xmx`, GC flags và mọi JVM options; database/cache/network service và dữ liệu test; load generator, phiên bản, kịch bản và tốc độ phát tải.

### Bước 2 — Kiểm tra correctness

Chạy smoke test trên cả ba cấu hình. Xác nhận ứng dụng khởi động, endpoint hoạt động, dữ liệu kết quả đúng và log chọn đúng collector. Nếu một collector có lỗi hoặc khác hành vi nghiệp vụ, không tiếp tục benchmark hiệu năng như thể các lượt chạy tương đương.

### Bước 3 — Warm-up

Chạy tải đủ để JVM hoàn tất phần lớn JIT warm-up, cache ứng dụng ổn định và GC vào trạng thái vận hành bình thường. Ví dụ warm-up 5–15 phút, nhưng thời lượng thực tế phải dựa trên ứng dụng. Không tính giai đoạn này vào cửa sổ steady-state nếu mục tiêu là hiệu năng ổn định.

### Bước 4 — Steady-state

Giữ arrival rate, request mix và dữ liệu giống nhau trong 10–30 phút hoặc lâu hơn nếu ứng dụng cần thời gian để bộc lộ xu hướng old-generation/footprint. Thu request metrics, RSS, cgroup memory và GC log cùng time window.

### Bước 5 — Burst và recovery

Tăng tải trong một khoảng có kiểm soát, sau đó trả về mức bình thường. Ghi p99 trong burst, peak memory, GC cycles và pause trong burst, thời gian latency trở lại baseline, cùng số timeout/error/OOM nếu có.

### Bước 6 — Lặp và đảo thứ tự

Chạy ít nhất 5 lượt cho mỗi cấu hình nếu ngân sách cho phép. Đảo thứ tự hoặc xen kẽ các cấu hình (ví dụ G1 → Gen → SATB, rồi SATB → G1 → Gen) để giảm ảnh hưởng của nhiệt độ CPU, cache host và biến động hạ tầng. Báo cáo median và độ phân tán, không chọn một lượt đẹp nhất.

~~~mermaid
flowchart TD
    A["Cố định JDK, app, heap, CPU và dữ liệu"] --> B["Smoke test 3 cấu hình"]
    B --> C["Warm-up giống nhau"]
    C --> D["Steady-state open-loop load"]
    D --> E["Burst và recovery"]
    E --> F["Thu request, memory và GC metrics"]
    F --> G["Lặp nhiều lượt, đảo thứ tự"]
    G --> H["Tổng hợp median, spread và trade-off"]
~~~

## 11. Bảng kết quả và cách đưa ra quyết định

Dùng bảng kết quả để nhóm có thể kiểm tra từng lần chạy:

| Metric | G1 | Shenandoah SATB | Shenandoah generational |
|---|---:|---:|---:|
| Successful requests/s | — | — | — |
| Error rate | — | — | — |
| p50 latency | — | — | — |
| p95 latency | — | — | — |
| p99 latency | — | — | — |
| p99.9 latency | — | — | — |
| GC pause p95 / p99 / max | — | — | — |
| GC pause count | — | — | — |
| Concurrent GC CPU/time | — | — | — |
| Heap used / committed | — | — | — |
| Process RSS peak | — | — | — |
| Container memory peak | — | — | — |
| Allocation rate | — | — | — |
| Dropped iterations | — | — | — |

### Cách đọc kết quả

- Nếu throughput tăng nhưng p99 xấu đi, hãy kiểm tra SLO tail latency trước khi chọn cấu hình.
- Nếu pause giảm nhưng RSS tăng, đánh giá chi phí bộ nhớ trên mỗi instance và mật độ triển khai.
- Nếu memory peak giảm nhưng throughput giảm, xem CPU tiêu thụ bởi concurrent GC và allocation pressure.
- Nếu số GC cycle tăng nhưng pause và tổng CPU giảm, số cycle nhiều hơn có thể vẫn là kết quả tốt.
- Nếu p99 tăng đồng thời dropped iterations xuất hiện, load generator không đáp ứng tải; lượt đo không hợp lệ để so sánh trực tiếp.
- Nếu có full/degenerated GC, allocation failure, OOM hoặc latency spike lớn, điều tra log và headroom trước khi đưa kết luận.

Chọn collector theo **SLO và chi phí tổng thể**: throughput cần đạt, p99 cần giữ, bộ nhớ mỗi replica, CPU quota và độ ổn định khi burst. Không có collector luôn thắng trên mọi workload.

## 12. Những sai lầm làm sai lệch phép đo

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| So sánh JDK/vendor build khác nhau | Không tách được ảnh hưởng collector và runtime | Dùng cùng JDK full build |
| Thay heap size giữa các lần chạy | Thay đổi điều kiện cấp phát và footprint | Giữ cùng Xms/Xmx hoặc cùng chính sách heap |
| Chỉ đo một lần | Kết quả dễ bị nhiễu bởi host và JIT | Lặp nhiều lượt và báo cáo median/spread |
| Dùng closed-loop mà không để ý offered load | Server chậm làm client tự giảm tốc độ gửi | Dùng open-loop và kiểm tra dropped iterations |
| Chỉ xem average latency | Che giấu tail latency | Báo cáo p50/p95/p99/p99.9 |
| Chỉ nhìn GC pause | Bỏ qua concurrent CPU và memory pressure | Đối chiếu request metrics, CPU, RSS và GC logs |
| Chỉ nhìn heap used | Bỏ qua native memory và container footprint | Thu RSS/cgroup memory và heap metrics |
| Chạy load generator cùng máy với JVM | Hai bên tranh CPU/memory | Chạy load generator riêng |
| Bật NMT/JFR ở một cấu hình duy nhất | Overhead đo không đồng đều | Bật cùng cách cho mọi lượt hoặc đo riêng |
| Dùng dữ liệu/cache khác nhau | Workload và tỷ lệ allocation thay đổi | Reset dữ liệu và giữ request mix cố định |
| Bật tuning flags tùy tiện | Không còn biết cải thiện đến từ đâu | Bắt đầu từ cấu hình tối thiểu, thay một biến mỗi lần |
| Kết luận từ một burst ngắn | Không thấy old-gen/footprint dài hạn | Có steady-state và soak test |

### Lưu ý về heap sizing

Không cố định `-Xms` bằng `-Xmx` chỉ vì muốn log dễ đọc nếu production không vận hành như vậy. Một lượt benchmark cố định heap giúp kiểm soát biến số; một lượt khác nên phản ánh đúng cách JVM được triển khai. Ghi rõ mục tiêu của từng lượt và không trộn hai loại kết quả.

## 13. Tuning sau baseline

Sau khi có baseline, chỉ thay đổi một nhóm tham số mỗi lần. Trong Generational Shenandoah của Java 25:

- Bắt đầu bằng `ShenandoahGCHeuristics=adaptive`, là heuristic được hỗ trợ cho generational mode.
- Không áp dụng `static` hoặc `compact` cho generational mode; tài liệu Java 25 chỉ hỗ trợ `adaptive`.
- Giữ heap đủ headroom cho allocation spike và concurrent collection.
- Kiểm tra CPU quota; concurrent GC cần CPU để làm việc trong lúc application threads tiếp tục chạy.
- Theo dõi tỷ lệ object sống lâu, old-generation occupancy và tốc độ promotion qua workload thật.
- Thay đổi heap hoặc CPU resources theo một giả thuyết rõ ràng, rồi chạy lại cùng benchmark.

Không bắt đầu bằng cách tăng đồng thời heap, số GC threads, CPU limit và thay heuristic. Nếu kết quả tốt hơn, sẽ không xác định được thay đổi nào tạo ra tác động.

## 14. Checklist và bài tập thực hành

### Checklist trước khi benchmark

- [ ] Dùng JDK 25 build có hỗ trợ Shenandoah trên nền tảng triển khai.
- [ ] Xác nhận `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational` khởi động thành công.
- [ ] Không dùng cờ preview hoặc cờ experimental cũ của JDK 24.
- [ ] So sánh G1, Shenandoah SATB và Shenandoah generational.
- [ ] Giữ cùng application artifact, JDK, heap, CPU/memory limit và dữ liệu.
- [ ] Workload phản ánh request mix, allocation rate, object lifetime và concurrency thực tế.
- [ ] Dùng load model phù hợp; với open-loop, xác nhận không có dropped iterations ngoài dự kiến.
- [ ] Thu p50/p95/p99/p99.9, throughput và error rate.
- [ ] Thu heap used/committed, RSS/cgroup memory và GC logs.
- [ ] Có warm-up, steady-state, burst/recovery và nhiều lượt lặp.
- [ ] Báo cáo median/spread, không chọn một lượt chạy riêng lẻ.
- [ ] Đối chiếu SLO và footprint trước khi quyết định đổi collector.

### Bài tập: đo dịch vụ Order API

Một dịch vụ Spring Boot xử lý request đọc đơn hàng và tạo đơn hàng. Mục tiêu là giữ p99 dưới 250 ms ở 1.000 request/giây, error rate dưới 1% và container memory dưới giới hạn triển khai.

1. Chạy cùng JAR trên JDK 25 với G1.
2. Chạy lại với Shenandoah SATB.
3. Chạy lại với Shenandoah generational bằng cờ Java 25.
4. Dùng k6 open-loop với request mix đọc/ghi gần production.
5. Thực hiện warm-up, steady-state 15 phút và burst 2 phút.
6. Thu throughput, error rate, p50/p95/p99/p99.9, heap, RSS/cgroup memory và GC pause.
7. Lặp ít nhất 5 lần, đảo thứ tự collector.
8. Xác định cấu hình nào đáp ứng đồng thời SLO latency, throughput và memory; giải thích trade-off.

**Câu hỏi tự kiểm tra:**

1. Vì sao phải so sánh Shenandoah SATB với generational ngoài G1?
2. Vì sao `-XX:+UseShenandoahGC` chưa đủ để bật generational mode?
3. Tại sao `adaptive` là heuristic cần dùng với generational mode trong Java 25?
4. Vì sao p99 có thể xấu dù GC pause vẫn ngắn?
5. Tại sao phải đo cả heap và RSS/cgroup memory?
6. Coordinated omission làm sai lệch phép đo latency như thế nào?
7. Khi nào một lượt benchmark có dropped iterations không còn hợp lệ?
8. Vì sao phải chạy nhiều lượt và đảo thứ tự collector?

## 15. Tài liệu chính thức

- [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): đưa generational mode vào Shenandoah trong JDK 25.
- [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): giai đoạn thử nghiệm trước Java 25; chỉ tham khảo để hiểu lịch sử, không dùng làm hướng dẫn cờ hiện hành.
- [Oracle JDK 25 — The java Command, Advanced Garbage Collection Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các cờ `UseShenandoahGC`, `ShenandoahGCMode` và `ShenandoahGCHeuristics`.
- [Oracle JDK 27 — The java Command, Advanced Garbage Collection Options](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): xác nhận các tùy chọn generational Shenandoah tiếp tục được tài liệu hóa trong JDK mới hơn.
- [Oracle JDK 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): throughput, latency, footprint và phương pháp đo GC.
- [Oracle JDK 25 — Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/introduction-garbage-collection-tuning.html): chọn collector theo yêu cầu và đặc điểm workload.
- [k6 — Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): mô hình open-loop để phát iteration theo tốc độ xác định.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness benchmark JVM cho các microbenchmark; không thay thế load test end-to-end của dịch vụ.

> **Ghi nhớ:** Dùng cùng một ứng dụng và tải đại diện để so sánh G1, Shenandoah SATB và Generational Shenandoah. Đo đồng thời throughput, p50/p95/p99/p99.9, heap, RSS/cgroup memory và GC logs. Trong Java 25, bật generational bằng `-XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational`; mặc định Shenandoah vẫn là `satb`, và generational mode chỉ hỗ trợ heuristic `adaptive`.
