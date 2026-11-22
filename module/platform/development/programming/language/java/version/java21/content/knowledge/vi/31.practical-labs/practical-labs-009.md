# So sánh G1 với Generational ZGC bằng tải đại diện

Lab này so sánh Garbage-First (G1) và Generational ZGC trên cùng một ứng dụng Java 21 bằng workload đại diện. Mục tiêu là xác định collector nào đáp ứng tốt hơn các yêu cầu thực tế về latency, throughput, CPU và memory footprint; không giả định một collector luôn nhanh hơn collector còn lại.

G1 hướng đến sự cân bằng giữa throughput và các khoảng pause tương đối ngắn, ổn định. Generational ZGC ưu tiên độ trễ thấp bằng cách thực hiện phần lớn công việc thu gom đồng thời với ứng dụng và tận dụng sự khác nhau về vòng đời object ở Young/Old Generation. Vì ZGC chạy đồng thời, cần quan sát cả CPU và headroom của heap, không chỉ thời gian pause.

## 1. Kết quả cần đạt

Sau lab, bạn có thể:

- Chạy cùng artifact lần lượt bằng G1 và Generational ZGC.
- Tạo tải có tốc độ request cố định, cùng dữ liệu và cùng thời lượng.
- Thu thập GC log, JFR, latency, throughput, CPU và memory.
- Phân biệt stop-the-world pause với thời gian GC chạy đồng thời.
- Nhận biết khi nào G1 phù hợp hơn, khi nào Generational ZGC đáng chọn và khi nào GC không phải bottleneck chính.
- Ghi lại kết quả đủ rõ để người khác có thể lặp lại phép đo.

## 2. Môi trường và điều kiện thử nghiệm

Chuẩn bị:

| Thành phần | Yêu cầu |
|---|---|
| Runtime | Cùng một bản phân phối và bản cập nhật JDK 21 cho cả hai lần chạy |
| Ứng dụng | Cùng artifact, cấu hình nghiệp vụ và dependency |
| Heap | Cùng giá trị -Xms và -Xmx |
| CPU/memory | Cùng máy hoặc cùng CPU quota, memory limit và hệ điều hành |
| Load generator | k6 hoặc công cụ tương đương, tốt nhất chạy trên máy riêng |
| Quan sát | Unified GC logging, JFR/JDK Mission Control và OS/container metrics |
| Dữ liệu | Cùng dataset, cache warm-up, request mix và trạng thái dependency |

G1 là collector mặc định trên server-class HotSpot JVM, nhưng lab vẫn chỉ định -XX:+UseG1GC để cấu hình được ghi rõ. Với Java 21, phải bật Generational ZGC bằng cả -XX:+UseZGC và -XX:+ZGenerational.

Không so sánh G1 trên JDK 21 với ZGC trên một JDK khác trong cùng lượt thử. Khi đó khác biệt JIT, thư viện, runtime và collector bị trộn lẫn. Nếu muốn đánh giá nâng cấp JDK, hãy thực hiện một ma trận thử nghiệm riêng.

### Khác biệt cờ ZGC theo phiên bản

| Runtime | Cách bật ZGC |
|---|---|
| Java 21 | -XX:+UseZGC -XX:+ZGenerational |
| JDK 23 | Generational mode trở thành mặc định khi chọn ZGC |
| JDK 24 trở lên | Chỉ còn Generational ZGC; dùng -XX:+UseZGC, không truyền -XX:+ZGenerational vì option đã bị loại bỏ |

Lab chính bên dưới dùng đúng cờ Java 21. Nếu mục tiêu triển khai là JDK hiện hành mới hơn, chạy lại phép đo trên đúng runtime đó và dùng cờ tương ứng với phiên bản.

## 3. Chọn workload đại diện

Ưu tiên endpoint hoặc luồng nghiệp vụ thật của ứng dụng, có dữ liệu và dependency gần production. Chọn workload thể hiện được:

- Request rate bình thường và giờ cao điểm.
- Tỷ lệ request đọc/ghi, kích thước payload và độ phân bố dữ liệu.
- Allocation rate thực tế, gồm object tạm, buffer và collection trung gian.
- Live set thực tế, gồm cache, session, queue hoặc dữ liệu được giữ lâu.
- Các lời gọi database, HTTP hoặc messaging nếu chúng nằm trên đường xử lý request.

Không dùng một endpoint trả về chuỗi hằng hoặc một vòng lặp cấp phát object nhỏ để kết luận collector nào phù hợp production. Nếu chưa có workload thật, tạo endpoint thử nghiệm mô phỏng cùng phân bố payload, tỷ lệ object ngắn hạn/dài hạn và thời gian gọi dependency; ghi rõ đây chỉ là synthetic workload.

Đặt trước một mức tải mục tiêu từ dữ liệu vận hành. Có thể thử ba mức: tải bình thường, tải cao điểm và tải stress. Ví dụ 300 request/giây trong các lệnh bên dưới chỉ là giá trị minh họa; thay bằng mức tải phù hợp với ứng dụng và capacity của môi trường thử.

## 4. Giữ phép so sánh công bằng

Trong lượt baseline, chỉ thay đổi lựa chọn collector. Giữ nguyên:

1. Cùng JDK vendor, JDK patch version và artifact.
2. Cùng -Xms, -Xmx, CPU quota, memory limit và cấu hình container.
3. Cùng dữ liệu, cache state, dependency, TLS, connection pool và application configuration.
4. Cùng script, request rate, thời lượng, timeout và số lần lặp.
5. Cùng mức log và công cụ profiling.

Ví dụ dùng -Xms2g -Xmx4g cho cả hai collector. Thay bằng giá trị phù hợp với live set và memory limit thực tế. Chừa dung lượng ngoài heap cho metaspace, code cache, thread stack, direct buffer và native memory.

Không thêm -XX:MaxGCPauseMillis, -Xmn, -XX:NewRatio hoặc các cờ tuning riêng cho G1 trong lượt baseline. Những cờ này có thể thay đổi hành vi collector và làm phép so sánh ban đầu mất công bằng. Sau khi có baseline, có thể thực hiện lượt tuning riêng cho từng collector theo mục tiêu SLO.

Nếu production sử dụng -Xms nhỏ hơn -Xmx, hãy giữ đúng cặp giá trị đó ở cả hai lượt. Không đặt -Xms = -Xmx chỉ để làm kết quả đẹp hơn; việc cố định toàn bộ heap có thể thay đổi hành vi commit/uncommit và memory footprint của ZGC.

## 5. Khởi chạy ứng dụng bằng G1

Mở một tiến trình mới cho lượt G1:

~~~shell
java -XX:+UseG1GC -Xms2g -Xmx4g '-Xlog:gc*,safepoint:file=gc-g1.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar application.jar
~~~

Giải thích:

- -XX:+UseG1GC chọn G1 tường minh.
- -Xms2g -Xmx4g đặt heap ban đầu và heap tối đa; thay bằng giá trị của môi trường thử.
- -Xlog:gc*,safepoint ghi GC và safepoint event bằng Unified Logging.
- filecount và filesize giới hạn các file log luân phiên để tránh log tăng không kiểm soát.

Kiểm tra tiến trình dùng đúng JDK và cờ:

~~~shell
java --version
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.flags
~~~

Ghi lại PID, command line, CPU quota, memory limit và thời điểm khởi động. Chờ ứng dụng ready và warm-up theo cùng quy trình trước khi đo.

## 6. Khởi chạy ứng dụng bằng Generational ZGC

Dừng hoàn toàn tiến trình G1, giữ nguyên artifact và cấu hình, rồi khởi động tiến trình mới:

~~~shell
java -XX:+UseZGC -XX:+ZGenerational -Xms2g -Xmx4g '-Xlog:gc*,safepoint:file=gc-zgc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar application.jar
~~~

Kiểm tra lại java --version, VM.version và VM.flags. Xác nhận log cho biết JVM đang dùng ZGC và chế độ generational. Nếu flag không được runtime nhận diện, dừng phép thử và xác minh bản JDK; không bỏ flag rồi tiếp tục gọi kết quả là Generational ZGC.

Trên ZGC, heap cần đủ chỗ cho live set và headroom để phục vụ allocation trong khi collector chạy đồng thời. Nếu workload gần chạm -Xmx, ghi nhận allocation stall hoặc dấu hiệu thiếu headroom. Không tăng heap riêng cho ZGC trong lượt baseline; hãy thực hiện lượt capacity tuning riêng sau khi so sánh với cùng giới hạn tài nguyên.

## 7. Chuẩn bị tải cố định bằng k6

Dùng constant-arrival-rate để giữ tốc độ bắt đầu iteration độc lập với thời gian phản hồi của ứng dụng. Đây là open-model workload, phù hợp hơn mô hình cố định số virtual user khi cần so sánh ở cùng request arrival rate.

Tạo file gc-load.js:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL;
if (!baseUrl) {
  throw new Error('BASE_URL is required');
}

export const options = {
  discardResponseBodies: true,
  scenarios: {
    representative: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 300),
      timeUnit: '1s',
      duration: __ENV.DURATION || '10m',
      preAllocatedVUs: Number(__ENV.PREALLOCATED_VUS || 100),
      maxVUs: Number(__ENV.MAX_VUS || 500),
    },
  },
};

export default function () {
  const response = http.get(baseUrl + '/api/representative', {
    timeout: '5s',
  });

  check(response, {
    'response is successful': (r) => r.status >= 200 && r.status < 300,
  });
}
~~~

Thay /api/representative bằng endpoint thực tế. Nếu ứng dụng có nhiều loại request, tạo cùng một request mix trong script và dùng cùng dữ liệu cho cả hai collector. Không thêm sleep ở cuối iteration vì executor arrival-rate đã điều phối tốc độ bắt đầu.

Chạy cùng script cho G1:

~~~shell
k6 run -e BASE_URL=http://127.0.0.1:8080 -e RATE=300 -e DURATION=10m -e PREALLOCATED_VUS=100 -e MAX_VUS=500 --summary-export=g1-summary.json gc-load.js
~~~

Sau khi chạy lại ứng dụng bằng Generational ZGC, chạy cùng script và lưu kết quả riêng:

~~~shell
k6 run -e BASE_URL=http://127.0.0.1:8080 -e RATE=300 -e DURATION=10m -e PREALLOCATED_VUS=100 -e MAX_VUS=500 --summary-export=zgc-summary.json gc-load.js
~~~

Các con số trong ví dụ phải được thay bằng tải đại diện. Load generator nên chạy trên máy riêng hoặc có đủ CPU riêng để không tranh tài nguyên với JVM đang được đo.

Theo dõi dropped_iterations. Nếu metric này tăng, k6 không khởi chạy đủ iteration theo tốc độ yêu cầu; nguyên nhân có thể là thiếu VU ở load generator hoặc ứng dụng phản hồi quá chậm. Kiểm tra số VU đã dùng, CPU của máy phát tải và latency của server trước khi kết luận. Khi kiểm tra giới hạn capacity, dropped iteration cũng là một tín hiệu saturation cần được ghi lại.

## 8. Quy trình cho mỗi lượt đo

Thực hiện cùng một trình tự cho từng collector:

1. Khởi động JVM mới và xác nhận đúng collector/flags.
2. Chờ health check thành công và các dependency sẵn sàng.
3. Warm-up bằng workload giống nhau trong khoảng thời gian cố định, ví dụ 5–10 phút.
4. Chờ metric ổn định; không tính startup và JIT warm-up vào cửa sổ đo chính.
5. Chạy k6 với arrival rate và thời lượng đã chọn.
6. Ghi GC log, request latency, throughput, CPU, RSS/container memory và heap metrics trong cùng khoảng thời gian.
7. Lưu summary, log, JFR và thông tin môi trường vào thư mục riêng theo collector.
8. Dừng ứng dụng một cách bình thường trước khi bắt đầu lượt tiếp theo.

Chạy tối thiểu ba lần cho mỗi collector. Luân phiên thứ tự, ví dụ G1 → ZGC → ZGC → G1, để giảm ảnh hưởng của nhiệt độ máy, cache hệ điều hành, tải nền và thứ tự chạy. So sánh median giữa các lần chạy và ghi cả độ biến động; không chọn kết luận từ một lần chạy thuận lợi.

Nếu ứng dụng có cache warm-up dài, hãy dùng thời gian warm-up đủ để cache đạt trạng thái tương đương. Nếu hệ thống có downstream không ổn định, ghi nhận trạng thái dependency hoặc chạy trên môi trường test riêng.

## 9. Thu thập JFR để xem allocation và GC phases

GC log đủ để xem collection và pause. Khi cần hiểu allocation site, thread hoặc phase chi tiết hơn, tạo JFR recording trong cùng cửa sổ đo. Sau warm-up, tìm PID:

~~~shell
jcmd -l
~~~

Bắt đầu recording cho lượt G1:

~~~shell
jcmd <pid> JFR.start name=gc-compare settings=profile duration=10m filename=g1.jfr
~~~

Với lượt Generational ZGC, dùng tên file khác:

~~~shell
jcmd <pid> JFR.start name=gc-compare settings=profile duration=10m filename=zgc.jfr
~~~

Dùng cùng recording settings và thời lượng cho cả hai lượt. profile thu thập nhiều thông tin hơn default, vì vậy có thể tăng overhead; chỉ so sánh hai lượt nếu cả hai dùng cùng cấu hình. Nếu overhead profiling ảnh hưởng đáng kể tới latency, chạy lượt benchmark chính chỉ với GC log rồi thực hiện lượt JFR chẩn đoán riêng.

Kiểm tra recording:

~~~shell
jcmd <pid> JFR.check
jfr summary g1.jfr
jfr summary zgc.jfr
~~~

Mở hai file trong JDK Mission Control (JMC), chọn cùng khoảng thời gian đo và kiểm tra:

- Garbage Collections: loại collection, pause, thời lượng và các phase.
- Memory: allocation theo class/thread/stack trace và xu hướng heap.
- Threads: thread state, park, monitor và thời gian chờ.
- Code: execution samples nếu cần kiểm tra CPU hotspot.

Không bật Heap Statistics chỉ để lấy thêm biểu đồ trong phép đo latency. Tính năng này có thể kích hoạt old/full GC ở đầu và cuối recording, làm thay đổi chính hành vi đang đo. Chỉ dùng khi thực sự cần dữ liệu heap statistics và ghi rõ tác động đó.

## 10. Các chỉ số cần ghi lại

Không chỉ so sánh số lần GC hoặc thời gian pause. Tạo bảng cho mỗi lượt:

| Nhóm | Chỉ số | Nguồn |
|---|---|---|
| Latency | p50, p95, p99, p99.9 và max request duration | k6/APM |
| Throughput | Request hoàn tất mỗi giây | k6 và server metrics |
| Độ tin cậy | Error rate, timeout, retry và dropped iterations | k6/application metrics |
| GC pause | Số pause, p95/max pause, tổng thời gian stop-the-world | GC log/JMC |
| GC CPU | CPU time và mức CPU process khi collector hoạt động | OS/container metrics, JFR |
| Heap | Peak used/committed, live set sau GC, headroom | GC log/JFR |
| Allocation | Allocation rate và class tạo nhiều object | JFR |
| Process | CPU, RSS, thread count và container memory | OS/container metrics |
| Khởi động | Thời gian startup và thời gian warm-up | Application/CI timing |

Ghi rõ đơn vị và khoảng thời gian. Với latency, dùng cùng percentile và cùng cửa sổ đo. Với CPU, so sánh mức tiêu thụ trung bình và peak trên cùng CPU quota.

## 11. Đọc GC log đúng cách

G1 thường có các dòng pause như Pause Young, Pause Mixed và trong trường hợp áp lực nghiêm trọng có thể xuất hiện Pause Full. Khi thấy Full GC, evacuation failure hoặc thời gian pause tăng, kiểm tra allocation rate, live set, humongous object, heap headroom và khả năng concurrent marking hoàn tất đúng lúc.

Generational ZGC có các chu kỳ thu gom Young/Old và nhiều phase chạy đồng thời. Các pause rất ngắn không có nghĩa toàn bộ công việc GC miễn phí: concurrent phase vẫn sử dụng CPU và băng thông bộ nhớ trong khi application thread chạy.

Điểm quan trọng khi so sánh:

- So sánh stop-the-world pause của hai collector bằng pause duration và tail latency.
- Không cộng toàn bộ thời gian một chu kỳ ZGC chạy đồng thời rồi gọi đó là pause time.
- So sánh GC CPU và process CPU để thấy chi phí concurrent work.
- Xem heap occupancy cùng live set và allocation rate; heap used cao chưa chắc là live set cao.
- Đối chiếu thời điểm pause/GC phase với request p99 tăng. Một pause dài nhưng không trùng với latency spike của đường request quan trọng có thể không phải bottleneck chính.

Có thể dùng JFR/JMC để đi từ một khoảng latency cao tới event, thread và stack trace liên quan. GC log và JFR bổ sung cho nhau; không dùng một dòng log riêng lẻ làm kết luận nguyên nhân gốc.

## 12. Bảng kết quả để điền sau khi chạy

Ghi median của ít nhất ba lần chạy ở cùng tải:

| Chỉ số | G1 | Generational ZGC | Collector tốt hơn theo SLO |
|---|---:|---:|---|
| Request rate mục tiêu | | | Phải giống nhau |
| Completed requests/s | | | |
| p50 latency | | | |
| p95 latency | | | |
| p99 latency | | | |
| Error rate | | | |
| Dropped iterations | | | |
| GC pause p95 | | | |
| GC pause max | | | |
| Tổng STW pause time | | | |
| Process CPU trung bình | | | |
| Peak RSS/container memory | | | |
| Peak heap used | | | |
| Allocation rate | | | |
| Full GC hoặc allocation stall | | | |

Không điền số giả định vào bảng. Nếu kết quả dao động lớn giữa các lần chạy, điều tra môi trường test và tăng số lần lặp trước khi quyết định.

## 13. Diễn giải kết quả

Một số mẫu kết quả thường gặp:

| Quan sát | Cách diễn giải và bước tiếp theo |
|---|---|
| ZGC giảm p99 rõ, throughput vẫn đạt mục tiêu, CPU còn headroom | ZGC có thể phù hợp nếu SLO latency quan trọng hơn chi phí tài nguyên tăng thêm |
| G1 đạt p95/p99 mục tiêu với CPU và memory thấp hơn | G1 có thể là lựa chọn hiệu quả hơn cho workload này |
| ZGC pause rất ngắn nhưng CPU hoặc RSS tăng đáng kể | Đánh giá lại CPU quota, heap headroom và chi phí concurrent work |
| G1 có Full GC hoặc pause dài | Điều tra live set, allocation/promotion rate, humongous object và heap sizing |
| Cả hai có p99 cao nhưng GC pause thấp | Tìm bottleneck ở lock, I/O, database, network, queue hoặc CPU application |
| ZGC có allocation stall hoặc heap gần -Xmx | Heap không có đủ headroom cho allocation trong lúc GC chạy; kiểm tra live set và capacity |
| Cả hai đạt kết quả gần như nhau | Ưu tiên collector có vận hành đơn giản hơn và tiếp tục theo dõi production metrics |

G1 có thể đáp ứng latency tốt mà không cần tuning sâu. Generational ZGC phù hợp để thử khi yêu cầu pause time rất thấp hoặc workload có allocation rate lớn; tuy nhiên cần đủ CPU và heap headroom. Kết quả thực tế phụ thuộc workload, phần cứng, JDK build và cấu hình bộ nhớ.

## 14. Lượt thử thứ hai: tuning có kiểm soát

Sau khi có baseline, nếu G1 chưa đạt latency mục tiêu, có thể thử thay đổi pause-time goal bằng -XX:MaxGCPauseMillis. Đây là hint cho G1, không phải cam kết hard real-time. G1 có thể thay đổi kích thước young generation và tần suất collection để tiến gần mục tiêu; pause thấp hơn có thể làm giảm throughput.

Với ZGC, bắt đầu bằng việc bảo đảm -Xmx đủ cho live set cộng headroom. Có thể thử -XX:SoftMaxHeapSize như soft target trong một lượt riêng, nhưng không dùng nó thay cho -Xmx và không giả định heap sẽ luôn nằm dưới soft limit.

Mỗi lượt tuning chỉ thay một yếu tố, lưu lại command line và lặp lại cùng workload. Không mang các cờ tuning từ collector này sang collector kia nếu chúng không có cùng ý nghĩa.

## 15. Các lỗi làm phép đo mất giá trị

- Chạy load generator cùng máy và để CPU của generator tranh với JVM.
- Dùng fixed-VU/closed-loop load nhưng kết luận như thể request arrival rate không đổi khi server chậm.
- Không warm-up JIT hoặc cache như nhau.
- Chạy hai collector với heap, CPU quota hoặc JDK patch khác nhau.
- Bật JFR profile cho một collector nhưng không bật cho collector còn lại.
- Để logging, APM agent hoặc background job khác nhau giữa các lần chạy.
- Chỉ xem average latency mà bỏ qua p95/p99 và error rate.
- So sánh toàn bộ concurrent GC cycle duration của ZGC với STW pause duration của G1.
- Chọn collector từ một lần chạy hoặc một synthetic endpoint không đại diện production.

Nếu dropped_iterations xuất hiện, kiểm tra cả VU allocation và tài nguyên máy phát tải. k6 có thể drop iteration vì thiếu VU hoặc vì hệ thống phản hồi chậm khiến không đủ VU để duy trì arrival rate. Ghi nhận metric này cùng latency và CPU để phân biệt giới hạn của generator với saturation của ứng dụng.

## 16. Checklist hoàn tất lab

- [ ] Cùng JDK 21 build, artifact, dependency và cấu hình ứng dụng.
- [ ] Xác nhận G1 bằng -XX:+UseG1GC.
- [ ] Xác nhận Generational ZGC bằng -XX:+UseZGC -XX:+ZGenerational.
- [ ] Giữ cùng -Xms, -Xmx, CPU quota và memory limit.
- [ ] Chọn request mix và dataset đại diện.
- [ ] Dùng cùng k6 constant-arrival-rate script và cùng request rate.
- [ ] Đặt load generator trên máy riêng hoặc kiểm soát tài nguyên của nó.
- [ ] Warm-up như nhau và chạy ít nhất ba lần mỗi collector.
- [ ] Lưu GC log, JFR, k6 summary và OS/container metrics.
- [ ] So sánh p95/p99, throughput, error rate, GC pause, GC CPU và RSS.
- [ ] Phân biệt stop-the-world pause với concurrent GC work.
- [ ] Ghi lại command line, runtime version, môi trường và kết luận.
- [ ] Chỉ thực hiện tuning sau khi đã lưu baseline.

## 17. Kết luận thực nghiệm

Điền kết luận sau khi hoàn thành phép đo:

- Workload và request rate đã dùng: ...
- SLO latency/throughput cần đạt: ...
- G1 đáp ứng SLO ở mức tải: ...
- Generational ZGC đáp ứng SLO ở mức tải: ...
- Khác biệt lớn nhất về p99, CPU và memory: ...
- Collector được chọn và lý do: ...
- Điều kiện cần tiếp tục theo dõi sau rollout: ...

Không có collector chiến thắng cho mọi ứng dụng. G1 thường là điểm bắt đầu hợp lý nhờ khả năng cân bằng throughput và pause. Generational ZGC đáng cân nhắc khi pause time là ràng buộc quan trọng và ứng dụng có đủ CPU cùng heap headroom. Chọn collector theo SLO và số liệu của chính workload, sau đó xác nhận lại bằng canary hoặc tải production có kiểm soát.

## Tài liệu tham khảo

- [Oracle Java SE 21 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector1.html)
- [Oracle Java SE 21 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [Oracle JDK 21 Release Notes — Generational ZGC](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
- [Grafana k6 — Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [Grafana k6 — Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/)
- [Oracle Java SE 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java SE 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
