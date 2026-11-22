# Đánh giá pause time, allocation stall, CPU và throughput

## Mục tiêu

Generational ZGC được thiết kế để duy trì độ trễ thấp bằng cách thực hiện phần lớn công việc thu gom rác đồng thời với ứng dụng. Tuy nhiên, pause time ngắn không tự động chứng minh cấu hình GC phù hợp. Collector vẫn sử dụng CPU, cần đủ headroom trong heap và có thể làm thread ứng dụng chờ khi không cấp phát được bộ nhớ kịp thời.

Khi đánh giá Generational ZGC, cần xem đồng thời bốn nhóm chỉ số: **pause time**, **allocation stall**, **CPU** và **throughput**. Bài học này trình bày cách thu thập dữ liệu, cách đọc từng chỉ số, cách chạy benchmark có thể so sánh và cách nhận biết tình trạng GC đang ảnh hưởng đến ứng dụng.

## 1. Xác định đúng phiên bản và chế độ ZGC trước khi đo

Generational ZGC được đưa vào JDK 21 dưới dạng tính năng experimental. Khi đánh giá đúng cấu hình Java 21, cần bật ZGC và generational mode bằng các cờ JVM tương ứng:

```bash
java \
  -XX:+UnlockExperimentalVMOptions \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -jar application.jar
```

Các bản JDK mới hơn đã thay đổi trạng thái của generational mode: từ JDK 23, Generational ZGC trở thành chế độ mặc định của ZGC; JDK 24 loại bỏ chế độ non-generational. Vì vậy, không mang nguyên bộ cờ dành cho Java 21 sang một JDK mới hơn mà không kiểm tra tài liệu và danh sách option của đúng runtime.

Trước khi thu thập số liệu, ghi lại ít nhất:

- Phiên bản và vendor của JDK (`java -version`).
- Collector thực tế được bật và các JVM flags liên quan.
- `-Xms`, `-Xmx`, giới hạn bộ nhớ container và CPU quota.
- Số lượng instance, cấu hình ứng dụng và cấu hình dependency.
- Phiên bản ứng dụng, workload và dữ liệu đầu vào của lần đo.

Không thể so sánh hai lần chạy một cách đáng tin cậy nếu một lần vô tình chạy ZGC không generational hoặc dùng một JDK khác với cấu hình mặc định khác.

## 2. Bốn chỉ số phải đánh giá cùng nhau

| Chỉ số | Câu hỏi cần trả lời | Dấu hiệu cần chú ý |
|---|---|---|
| Pause time | Ứng dụng bị dừng bởi các pha GC trong bao lâu? | p95/p99/max pause, tần suất pause và safepoint |
| Allocation stall | Thread ứng dụng có phải chờ để được cấp phát bộ nhớ không? | Số lần stall, thời gian stall tổng và stall dài nhất |
| CPU | Công việc GC đồng thời tiêu thụ bao nhiêu năng lực xử lý? | CPU toàn tiến trình, CPU GC, throttling và run queue |
| Throughput | Ứng dụng hoàn thành được bao nhiêu công việc trong một đơn vị thời gian? | Request/second, operation/second và tỷ lệ lỗi |

Các chỉ số có quan hệ với nhau. Ví dụ, CPU thiếu headroom có thể làm các pha GC đồng thời tiến triển chậm hơn; heap có thể thiếu vùng trống để cấp phát và gây allocation stall. Một cấu hình có pause time rất thấp nhưng tiêu thụ nhiều CPU hoặc giảm throughput vẫn có thể không phù hợp với mục tiêu vận hành.

## 3. Đánh giá pause time

Pause time là khoảng thời gian ứng dụng bị dừng trong các pha stop-the-world của GC. ZGC hướng đến pause rất ngắn, nhưng không có nghĩa mọi pause bằng 0 hoặc mọi request đều có latency thấp.

Khi phân tích pause time, cần xem:

- **p50:** mức pause điển hình.
- **p95 và p99:** các pause dài hơn mà một phần workload gặp phải.
- **Maximum:** pause dài nhất trong khoảng quan sát.
- **Frequency:** số pause trong một đơn vị thời gian.
- **Total pause time:** tổng thời gian ứng dụng bị dừng do các pause được ghi nhận.

Không chỉ dùng giá trị trung bình. Một vài pause dài có thể ảnh hưởng mạnh đến tail latency dù average pause vẫn rất thấp.

### Đọc pause trong GC log

Có thể bật unified logging của JVM:

```bash
java \
  -XX:+UnlockExperimentalVMOptions \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  '-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags' \
  -jar application.jar
```

GC log ghi lại chu kỳ thu gom, các pha GC và thông tin safepoint. Tên pha và mức chi tiết có thể thay đổi theo JDK update; hãy dùng log của chính runtime đang chạy thay vì phụ thuộc vào một chuỗi log cố định.

Để xem chi tiết hơn trong một lần điều tra, có thể tăng mức log:

```bash
java \
  -XX:+UnlockExperimentalVMOptions \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  '-Xlog:gc*=debug,safepoint=info:file=gc-debug.log:time,uptime,level,tags' \
  -jar application.jar
```

Mức debug tạo thêm dữ liệu và có thể tăng overhead ghi log. Chỉ bật khi cần chẩn đoán, sau đó quay về mức log phù hợp cho vận hành.

### Phân biệt GC pause với request latency

Pause time không phải tổng latency của request. Request còn có thể chờ network, database, lock, scheduler hoặc thread pool. Ngược lại, request có thể bị ảnh hưởng bởi một pause xảy ra ngay trước hoặc trong thời điểm xử lý dù bản thân pause rất ngắn.

Hãy đối chiếu timestamp của GC log với biểu đồ latency p95/p99 của ứng dụng. Nếu request latency tăng nhưng không có GC pause tương ứng, cần kiểm tra các nguyên nhân khác thay vì quy kết ngay cho ZGC.

Ngoài GC pause, hãy quan sát safepoint log. Một số safepoint của JVM không phải pha GC; nếu chỉ xem GC pause, có thể bỏ sót thời gian dừng do hoạt động JVM khác.

## 4. Đánh giá allocation stall

Allocation stall xảy ra khi thread ứng dụng cần cấp phát object nhưng JVM chưa thể đáp ứng ngay từ vùng heap sẵn sàng. Thread đó phải chờ trong khi GC hoặc hoạt động quản lý heap tạo thêm khả năng cấp phát.

Allocation stall khác với GC pause:

- GC pause dừng các thread ứng dụng trong một pha stop-the-world.
- Allocation stall có thể chỉ làm một hoặc một nhóm thread cấp phát bị chờ; các thread khác vẫn có thể tiếp tục chạy.
- Vì vậy, pause time thấp không loại trừ khả năng request bị chậm do allocation stall.

Trong GC log chi tiết, tìm các sự kiện hoặc thông báo `Allocation Stall` và ghi lại:

1. Số lần xảy ra trong mỗi khoảng thời gian.
2. Tổng thời gian thread bị stall.
3. Stall dài nhất và phân bố thời lượng.
4. Thread nào bị ảnh hưởng nếu log cung cấp thông tin đó.
5. Heap occupancy, allocation rate và hoạt động GC xung quanh thời điểm stall.

Một stall rất ngắn nhưng xảy ra thường xuyên có thể làm tăng CPU scheduling và tail latency. Một stall hiếm nhưng kéo dài có thể tạo ra request p99 rất xấu. Cần xem cả số lần và thời lượng, không chỉ một giá trị tổng.

### Nguyên nhân thường gặp

- Allocation rate tăng đột biến do traffic hoặc workload tạo nhiều object tạm thời.
- Heap max quá nhỏ so với live set và tốc độ cấp phát.
- GC concurrent cycle không theo kịp tốc độ tạo object.
- CPU bị bão hòa hoặc container bị throttling, làm GC thiếu thời gian xử lý.
- Ứng dụng giữ quá nhiều object sống lâu, làm giảm vùng heap có thể tái sử dụng.
- Có burst cấp phát lớn hoặc workload thay đổi đột ngột.

Generational ZGC phân biệt object trẻ và object già để thu gom object ngắn hạn hiệu quả hơn. Khi đánh giá, hãy quan sát hoạt động young/old generation trong log và JFR, nhưng không giả định mọi workload đều có cùng tỷ lệ object sống ngắn hoặc cùng hành vi promotion.

## 5. Đánh giá CPU và chi phí GC đồng thời

ZGC thực hiện phần lớn công việc đồng thời với ứng dụng. Điều này giảm thời gian pause nhưng không làm công việc GC biến mất. GC sử dụng CPU để đánh dấu, xử lý reference và di chuyển object; CPU đó cạnh tranh với CPU dành cho business logic.

Nên đo:

- CPU utilization toàn tiến trình và từng container.
- CPU time của JVM/GC nếu công cụ quan sát cho phép phân tách.
- Số core thực tế được cấp và CPU quota của container.
- CPU throttling, run queue và thời gian thread runnable phải chờ CPU.
- CPU seconds trên mỗi request hoặc trên một triệu operation.
- Thay đổi CPU khi tăng tải và khi GC cycle diễn ra dày hơn.

Không kết luận chỉ từ phần trăm CPU. Ví dụ, 70% CPU trên container 2 vCPU khác hoàn toàn 70% trên máy 32 core. Với container, cần đọc CPU quota và throttling thay vì chỉ nhìn số core của host.

Nếu CPU đã bão hòa, GC concurrent work có thể chậm lại và làm tăng heap pressure hoặc allocation stall. Tăng số worker hoặc tăng concurrency trong tình huống đó có thể làm cạnh tranh CPU nặng hơn.

## 6. Đánh giá throughput

Throughput thể hiện lượng công việc ứng dụng hoàn tất trong một đơn vị thời gian, chẳng hạn:

- HTTP request hoàn tất mỗi giây.
- Message xử lý mỗi giây.
- Transaction hoàn tất mỗi giây.
- Operation nghiệp vụ hoàn tất mỗi phút.

Hãy đo throughput cùng với latency và error rate. Nếu throughput tăng nhưng p99 vượt SLO hoặc tỷ lệ timeout tăng, cấu hình đó không phải cải thiện vận hành.

Generational ZGC tối ưu cho latency thấp và có thể sử dụng thêm CPU cho công việc GC đồng thời. Do đó, khi so sánh với collector khác, throughput có thể khác nhau. Không nên mặc định ZGC luôn có throughput cao hơn hoặc thấp hơn G1; kết quả phụ thuộc allocation rate, live set, heap, CPU, workload và phiên bản JDK.

### So sánh ở cùng điều kiện

Một benchmark có ý nghĩa cần giữ nhất quán:

- Cùng phiên bản ứng dụng và dữ liệu đầu vào.
- Cùng loại máy/container, CPU quota và giới hạn bộ nhớ.
- Cùng mức tải, thời gian warm-up và thời gian steady-state.
- Cùng dependency, network path và cấu hình connection pool.
- Cùng SLO latency và tiêu chí tính request thành công.
- Ghi nhận rõ khác biệt về heap flags và cấu hình collector giữa các lần chạy.

Nên đo nhiều vòng và dùng phân vị thay vì chỉ lấy một lần chạy. Có thể chạy một bài load test tăng tải dần để tìm điểm throughput tối đa trước khi p99, allocation stall hoặc error rate vượt ngưỡng.

## 7. Theo dõi heap, allocation rate và live set để giải thích kết quả

Pause time, allocation stall, CPU và throughput cho biết biểu hiện. Để hiểu nguyên nhân, cần xem thêm các chỉ số bộ nhớ:

| Chỉ số bổ sung | Ý nghĩa |
|---|---|
| Heap used/committed/max | Mức sử dụng và headroom của heap |
| Live set sau GC | Lượng object còn sống sau khi thu gom |
| Allocation rate | Tốc độ ứng dụng tạo object mới |
| Young/old generation activity | Tần suất và thời gian hoạt động của từng generation |
| Promotion/aging behavior | Cách object sống lâu chuyển sang vùng quản lý dài hạn |
| GC cycle duration | Thời gian các chu kỳ concurrent GC cần để hoàn thành |

Ví dụ, allocation rate tăng mạnh trong khi live set ổn định thường gợi ý workload tạo nhiều object ngắn hạn. Nếu live set tăng liên tục, cần điều tra retention hoặc cache tăng trưởng. Nếu GC cycle kéo dài cùng CPU throttling, vấn đề có thể nằm ở thiếu CPU headroom thay vì chỉ heap nhỏ.

Không chỉ nhìn heap used hiện tại. Hãy xem xu hướng theo thời gian, giá trị sau các chu kỳ GC và mức biến động trong giờ cao điểm.

## 8. Dùng Java Flight Recorder để đối chiếu

Java Flight Recorder (JFR) thu thập sự kiện runtime như GC, heap summary, allocation sampling, thread và CPU. Có thể bật recording khi khởi chạy ứng dụng:

```bash
java \
  -XX:+UnlockExperimentalVMOptions \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  '-XX:StartFlightRecording=filename=zgc.jfr,settings=profile,dumponexit=true' \
  -jar application.jar
```

Mở file recording bằng JDK Mission Control hoặc công cụ phân tích JFR phù hợp. Đối chiếu các sự kiện GC pause/concurrent phase, heap summary, allocation sample, thread state và CPU load với cùng khoảng thời gian trong GC log và metric ứng dụng.

Allocation sampling là dữ liệu lấy mẫu, không phải phép đếm chính xác mọi object được cấp phát. Dùng nó để tìm class hoặc call path có allocation đáng chú ý; không diễn giải sample count như tổng số allocation tuyệt đối.

JFR và GC log bổ sung cho nhau: log thuận tiện để theo dõi chu kỳ GC và stall; JFR hữu ích khi cần tương quan GC với allocation, thread và CPU. Recording chi tiết có chi phí nhất định, nên kiểm tra overhead trong môi trường gần production.

## 9. Quy trình benchmark có thể lặp lại

Một quy trình thực tế nên gồm các giai đoạn sau:

1. **Chốt baseline:** ghi JDK, flags, heap, CPU/memory limit, ứng dụng, dependency và workload.
2. **Warm-up:** chạy đủ lâu để ứng dụng đạt trạng thái ổn định, tránh lấy startup làm kết quả đại diện.
3. **Steady-state:** giữ tải ổn định trong khoảng thời gian đủ dài để quan sát nhiều chu kỳ GC.
4. **Peak/burst:** tạo tải tăng nhanh để quan sát allocation spike, stall và khả năng phục hồi.
5. **Soak:** chạy lâu hơn để phát hiện live set tăng, retention hoặc xu hướng throughput suy giảm.
6. **Lặp lại:** chạy nhiều vòng trong điều kiện tương đương và so sánh phân vị.
7. **Đối chiếu:** ghép GC log/JFR với request latency, throughput, error rate và CPU metrics.

Không dùng một microbenchmark nhỏ để kết luận collector phù hợp cho service thực tế. Workload phải đại diện cho kích thước payload, tỷ lệ request, object lifetime, concurrency và dependency của ứng dụng.

## 10. Bảng diễn giải triệu chứng

| Quan sát | Nguyên nhân có thể | Bước điều tra tiếp theo |
|---|---|---|
| Pause thấp, p99 request cao | I/O, lock, scheduler, allocation stall hoặc safepoint khác | Đối chiếu timestamp JFR, safepoint log và trace request |
| Pause thấp nhưng có Allocation Stall | Heap headroom thấp, allocation burst, GC không theo kịp | Xem allocation rate, live set, heap max và GC cycle duration |
| Allocation Stall tăng cùng CPU throttling | GC concurrent work và ứng dụng thiếu CPU | Kiểm tra quota, throttling, CPU seconds/request và tải |
| CPU tăng nhưng throughput không tăng | GC overhead, contention hoặc dependency đã bão hòa | Xem CPU profile, GC phases, queue time và dependency latency |
| Throughput tốt nhưng p99 xấu | Burst, tail allocation, stall hiếm hoặc dependency chậm | Xem histogram p99/max, stall duration và trace theo thời điểm |
| Heap occupancy tăng qua nhiều chu kỳ | Live set tăng, cache hoặc object retention | So sánh heap summary và allocation/retention profile |
| Pause tăng đột biến | Safepoint hoặc GC phase bất thường, áp lực hệ thống | Kiểm tra GC phase log và safepoint log chi tiết |

Các triệu chứng chỉ gợi ý hướng điều tra, không phải kết luận nguyên nhân. Luôn xác nhận bằng dữ liệu cùng timestamp và workload.

## 11. Ví dụ bảng kết quả benchmark

Giả sử một service chạy cùng workload trên hai cấu hình GC. Bảng dưới đây chỉ minh họa cách trình bày kết quả; các số liệu không phải benchmark tham chiếu cho ZGC:

| Metric | Cấu hình A | Cấu hình B |
|---|---:|---:|
| GC pause p99 | 1.8 ms | 0.9 ms |
| GC pause max | 7.0 ms | 3.2 ms |
| Allocation stall count | 0 | 4 |
| Allocation stall max | 0 ms | 12 ms |
| CPU utilization | 58% | 76% |
| Throughput | 8,900 req/s | 8,500 req/s |
| Request latency p99 | 42 ms | 55 ms |

Trong ví dụ giả định, cấu hình B có pause thấp hơn nhưng có allocation stall, dùng CPU cao hơn, throughput thấp hơn và request p99 xấu hơn. Nếu chỉ chọn theo pause time, có thể đưa ra quyết định sai. Cần kiểm tra heap headroom, allocation burst và CPU capacity để xác định liệu B có thể được cải thiện hay cấu hình A phù hợp hơn với SLO.

## 12. Nguyên tắc tuning dựa trên bằng chứng

Khi thấy vấn đề, thay đổi từng yếu tố và đo lại:

- Nếu có allocation stall, kiểm tra heap headroom, live set, allocation rate, CPU throttling và tốc độ GC cycle trước khi chỉ tăng `-Xmx`.
- Nếu CPU cao, xác định phần CPU do GC hay application; xem container quota và workload trước khi thêm CPU.
- Nếu throughput thấp, kiểm tra CPU, lock contention, dependency saturation và GC overhead.
- Nếu pause đã thấp nhưng latency vẫn cao, điều tra toàn bộ request path thay vì tiếp tục tối ưu pause.
- Nếu heap tăng đều, điều tra object retention và cache lifecycle thay vì mặc định đổi collector.

Không thay đổi đồng thời heap size, CPU quota, concurrency và cấu hình GC trong một lần benchmark. Khi nhiều biến đổi cùng lúc, khó xác định thay đổi nào tạo ra kết quả.

## 13. Checklist đánh giá Generational ZGC

Trước khi quyết định đưa cấu hình vào production, hãy xác nhận:

1. Đúng JDK và đúng generational mode đang được chạy chưa?
2. GC log có timestamp, phase và safepoint đủ để phân tích không?
3. Pause time được đánh giá bằng p95/p99/max và tần suất thay vì chỉ average chưa?
4. Allocation stall count và duration đã được kiểm tra riêng với GC pause chưa?
5. CPU utilization, CPU throttling và CPU time trên mỗi request đã được đo chưa?
6. Throughput có được đánh giá cùng latency percentile và error rate không?
7. Heap headroom, live set, allocation rate và young/old generation activity có được quan sát không?
8. Benchmark có warm-up, steady-state, peak/burst và soak test không?
9. Các lần so sánh có cùng workload, tài nguyên và dependency không?
10. Các thay đổi tuning có được thực hiện từng bước và đo lại không?

## Kết luận

Đánh giá Generational ZGC không thể chỉ dựa vào pause time. Pause p99/max cho biết mức dừng ứng dụng; allocation stall cho thấy thread cấp phát có phải chờ heap hay không; CPU cho biết chi phí concurrent GC và headroom còn lại; throughput cho biết lượng công việc thực sự hoàn tất. Hãy kết hợp GC log, safepoint log, JFR và metric ứng dụng trong cùng khoảng thời gian, chạy workload đại diện và so sánh ở cùng điều kiện. Trên Java 21 cần xác nhận generational mode được bật theo cách của phiên bản này; các JDK mới hơn đã chuyển Generational ZGC thành chế độ mặc định và thay đổi các flag liên quan.
