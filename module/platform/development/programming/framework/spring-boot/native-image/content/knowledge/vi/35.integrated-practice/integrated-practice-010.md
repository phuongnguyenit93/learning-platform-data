# Lập báo cáo lựa chọn JVM hay native dựa trên chức năng, số đo và chi phí build

Chọn JVM hay GraalVM Native Image là quyết định kiến trúc và vận hành. Native executable thường có lợi thế về thời gian khởi động và footprint bộ nhớ trong nhiều workload. JVM có JIT compiler, hệ sinh thái runtime linh hoạt và thường có pipeline build đơn giản hơn. Không thể kết luận một phương án tốt hơn chỉ từ startup hoặc kích thước binary.

Một quyết định có thể bảo vệ được cần trả lời bốn câu hỏi:

1. Cả hai phương án có thực hiện đầy đủ chức năng và đáp ứng yêu cầu tương thích không?
2. Chúng khác nhau thế nào khi đo startup, latency, throughput, CPU và memory trong cùng điều kiện?
3. Chi phí tạo, kiểm thử, lưu trữ và phát hành native artifact tăng bao nhiêu?
4. Lợi ích runtime có đủ lớn để bù chi phí build, bảo trì và vận hành không?

Bài thực hành này xây dựng báo cáo lựa chọn cho dịch vụ Spring Boot Order API. Thí nghiệm so sánh ba biến thể: JVM thông thường, JVM chạy code do Spring AOT sinh ra và GraalVM Native Image. Biến thể AOT-on-JVM giúp tách ảnh hưởng của Spring AOT khỏi ảnh hưởng của native compilation.

## 1. Xác định quyết định cần đưa ra

Trước khi benchmark, hãy viết rõ phạm vi quyết định. Ví dụ:

> Chọn cách đóng gói cho Order API chạy liên tục trong Kubernetes, có lưu lượng ổn định, cần đáp ứng p95 latency dưới 200 ms, startup khi rolling deployment dưới 10 giây và giới hạn memory theo container.

Một quyết định khác có thể dành cho worker xử lý job ngắn hạn:

> Chọn runtime cho worker được scale từ zero, thường chỉ xử lý một job trong vài giây, cần sẵn sàng trong dưới một giây và có giới hạn memory nghiêm ngặt.

Hai dịch vụ cùng dùng Spring Boot nhưng có thể có kết quả lựa chọn khác nhau. Mục tiêu workload quyết định số đo nào có giá trị.

Ghi rõ các ràng buộc trước khi đo:

- Chức năng và integration bắt buộc.
- SLO/SLA về startup, latency, throughput và error rate.
- Giới hạn CPU, memory và số replica.
- Nền tảng triển khai: Linux/AMD64, Linux/ARM64, Windows hay macOS.
- Tần suất release và số platform artifact phải build.
- Yêu cầu observability, security, debugging và incident response.
- Mức linh hoạt cần có với plugin, dynamic class loading và cấu hình runtime.

Không thay đổi tiêu chí sau khi đã xem kết quả chỉ để hợp thức hóa một phương án yêu thích.

## 2. So sánh ba biến thể để tách tác động của AOT

Dùng ba biến thể cùng một source code và dependency graph:

| Biến thể | Cách chạy | Điều muốn biết |
| --- | --- | --- |
| JVM thường | Executable JAR chạy trên JVM, không bật Spring AOT generated initialization | Baseline của ứng dụng hiện tại |
| JVM + Spring AOT | JAR có AOT generated assets, chạy trên JVM với AOT enabled | Lợi ích của Spring AOT mà vẫn giữ JVM runtime |
| Native Image | Executable do GraalVM Native Image tạo ra | Lợi ích và giới hạn của native compilation |

Nếu chỉ so sánh JVM thường với native, có thể quy nhầm lợi ích từ Spring AOT cho native executable. Biến thể thứ hai giúp nhận biết phần cải thiện startup đến từ việc chuẩn bị ApplicationContext lúc build.

Spring Boot có thể chạy ứng dụng trên JVM bằng code AOT-generated khi bật `spring.aot.enabled=true`. JAR phải được build để chứa các AOT assets. Với Maven, profile `native` là cách phổ biến để kích hoạt xử lý AOT; với Gradle, plugin GraalVM Native Image áp dụng AOT task cần thiết.

### Build mẫu

Với Maven, baseline JVM thông thường:

~~~bash
./mvnw clean package
java -jar target/orders-api.jar
~~~

Tạo JAR có Spring AOT assets và chạy AOT trên JVM:

~~~bash
./mvnw -Pnative package -DskipTests
java -Dspring.aot.enabled=true -jar target/orders-api.jar
~~~

Tạo native executable:

~~~bash
./mvnw -Pnative native:compile
~~~

Với Gradle:

~~~bash
# JVM thông thường
./gradlew clean bootJar

# Xử lý AOT rồi đóng gói JAR để chạy AOT trên JVM
./gradlew processAot bootJar

# Native executable
./gradlew nativeCompile
~~~

Các task và profile cụ thể phụ thuộc cấu hình Maven/Gradle của project. Kiểm tra output để bảo đảm JAR AOT thực sự chứa generated assets và native build sử dụng đúng GraalVM version. Không benchmark một JAR thường rồi bật property AOT ở runtime mà không có generated code.

## 3. Đặt cổng chức năng trước khi tính điểm

Tương thích chức năng là điều kiện bắt buộc, không phải một tiêu chí có thể bù bằng điểm startup hoặc memory.

Tạo cùng một test suite cho ba biến thể, bao gồm:

- Khởi tạo Spring ApplicationContext và tất cả bean bắt buộc.
- REST API, validation, serialization/deserialization và error handling.
- Database driver, connection pool và transaction.
- HTTP client, message broker hoặc integration bên ngoài.
- Security filter, authentication, authorization và TLS.
- Reflection, resource, dynamic proxy, JNI hoặc thư viện bên thứ ba có dùng.
- Health/readiness endpoint, graceful shutdown và context propagation.
- Các profile/cấu hình được hỗ trợ trong thiết kế deployment.

| Điều kiện hard gate | JVM thường | JVM + AOT | Native |
| --- | --- | --- | --- |
| Unit và integration tests bắt buộc | Pass/Fail | Pass/Fail | Pass/Fail |
| Luồng nghiệp vụ trọng yếu | Pass/Fail | Pass/Fail | Pass/Fail |
| Dependency và native integration | Pass/Fail | Pass/Fail | Pass/Fail |
| Security và TLS | Pass/Fail | Pass/Fail | Pass/Fail |
| Health/readiness/shutdown | Pass/Fail | Pass/Fail | Pass/Fail |
| Chạy trên target platform | Pass/Fail | Pass/Fail | Pass/Fail |

Nếu một phương án không qua hard gate, đánh dấu **không đủ điều kiện**. Không cộng điểm hiệu năng để bù cho lỗi chức năng, lỗ hổng security hoặc thiếu platform support.

Spring Boot khuyến nghị tiếp tục chạy phần lớn unit/integration test trên JVM để feedback nhanh, sau đó tập trung native test vào AOT processing, reachability hints và các đường code có hành vi khác biệt. Có thể chạy AOT-generated code trên JVM trước native compilation để phát hiện lỗi AOT với chi phí thấp hơn.

## 4. Thiết kế workload đại diện

Benchmark chỉ có ý nghĩa nếu workload giống cách ứng dụng được sử dụng trong production.

Với Order API, chọn ít nhất ba nhóm:

| Nhóm workload | Ví dụ request | Mục đích |
| --- | --- | --- |
| Đọc dữ liệu | Lấy đơn hàng, tìm kiếm theo trạng thái | Đo latency và throughput của truy vấn phổ biến |
| Ghi dữ liệu | Tạo đơn, cập nhật trạng thái, transaction | Đo CPU, database interaction và error rate |
| Integration | Gọi payment/partner service | Đo tác động của network, client instrumentation và timeout |

Xác định trước:

- Tỷ lệ request đọc/ghi/integration.
- Kích thước payload và phân phối dữ liệu.
- Tỷ lệ cache hit/miss.
- Số kết nối database và connection pool limit.
- Concurrency, request rate và thời gian chạy.
- Tỷ lệ lỗi có chủ đích trong workload.
- Tập dữ liệu và trạng thái database trước mỗi lần đo.

Không dùng một endpoint trả chuỗi cố định để đại diện cho toàn bộ hệ thống nếu production có database, serialization và external calls. Endpoint đơn giản chỉ phù hợp để kiểm tra chi phí HTTP framework ở một lát cắt hẹp.

Ví dụ SLO benchmark:

~~~text
Functional tests: 100% pass
HTTP error rate: < 0.5%
p95 latency: < 200 ms at 200 requests/second
p99 latency: < 400 ms at 200 requests/second
Startup to ready: < 10 seconds
Container memory: < 512 MiB at target load
Sustainable throughput: >= 1,000 requests/second
~~~

Các con số trên chỉ là ví dụ. Thay bằng SLO thực tế của dịch vụ và ghi lại phiên bản tiêu chí trong báo cáo.

## 5. Kiểm soát điều kiện thí nghiệm

Giữ các yếu tố sau giống nhau giữa các biến thể:

- Cùng commit source, dependency versions và business configuration.
- Cùng OS, CPU model, architecture và kernel khi so sánh runtime.
- Cùng CPU quota, memory limit, container runtime và network path.
- Cùng database, dataset, pool size và trạng thái cache.
- Cùng request mix, payload, concurrency và load generator.
- Cùng số replica hoặc quy tắc scale khi so sánh một instance.
- Cùng logging level, metrics/tracing exporters và sampling policy.

Không chạy JVM trên máy 32 CPU rồi native trên máy 8 CPU. Không để JVM dùng heap limit lớn trong khi native bị giới hạn container thấp hơn. Nếu cấu hình GC, heap hoặc thread khác nhau vì cần tối ưu production, ghi rõ mỗi cấu hình và thực hiện thêm một lượt so sánh baseline với điều kiện tương đương.

### Tách cold start và steady state

Hai phép đo trả lời hai câu hỏi khác nhau:

- **Cold start:** mất bao lâu từ lúc process/container được khởi chạy đến khi service thật sự nhận request.
- **Steady state:** ứng dụng xử lý tải ổn định thế nào sau giai đoạn khởi động và warm-up.

JVM có JIT compilation và có thể cải thiện throughput sau khi code nóng được biên dịch. Native executable không có JIT compiler như HotSpot, nhưng vẫn chịu ảnh hưởng của cache CPU, filesystem cache, connection pool và các bước khởi tạo lazy. Vì vậy, không so sánh một JVM đã warm-up với một native process vừa khởi chạy.

## 6. Đo startup và thời gian sẵn sàng

Spring Boot Actuator cung cấp hai startup metrics:

- `application.started.time`: thời gian ứng dụng cần để khởi động.
- `application.ready.time`: thời gian từ khi bắt đầu cho tới khi ứng dụng sẵn sàng phục vụ request.

Hai số đo này hữu ích để so sánh startup bên trong Spring. Tuy nhiên, readiness của nền tảng còn có thể phụ thuộc vào container startup, network, probe interval và load balancer. Nên đo thêm từ bên ngoài: thời điểm container được tạo đến khi nhận response thành công đầu tiên.

Quy trình đo:

1. Khởi chạy process mới cho mỗi lần đo.
2. Ghi thời điểm bắt đầu process/container.
3. Poll readiness endpoint theo chu kỳ cố định.
4. Ghi thời điểm readiness thành công và request nghiệp vụ đầu tiên thành công.
5. Dừng process, chờ tài nguyên được giải phóng rồi chạy lần tiếp theo.
6. Lặp lại tối thiểu 20 lần cho mỗi biến thể; nếu kết quả dao động lớn, tăng số lần đo.
7. Báo cáo median, p95 và min/max; không chỉ chọn lần nhanh nhất.

Đo riêng thời gian pull image nếu deployment thực tế phải tải image mới. Đừng gộp thời gian pull image vào startup process mà không ghi rõ, vì đó là chi phí phân phối artifact chứ không phải thời gian Spring khởi động.

| Startup metric | JVM thường | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Median ready time | ... | ... | ... |
| p95 ready time | ... | ... | ... |
| Median first successful request | ... | ... | ... |
| p95 first successful request | ... | ... | ... |

Nếu service có lazy initialization, readiness thành công chưa chắc chứng minh mọi dependency đã sẵn sàng. Hãy dùng cùng readiness policy và thực hiện một request nghiệp vụ thực tế sau startup.

## 7. Đo throughput, latency và error rate

Đo steady state sau một giai đoạn warm-up cố định. Một kịch bản HTTP có thể dùng k6:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 40,
  duration: '10m',
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<200', 'p(99)<400']
  }
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/orders/benchmark'
  );

  check(response, {
    'status is 200': (res) => res.status === 200
  });
}
~~~

Chạy cùng script, cùng dữ liệu và cùng load generator cho từng biến thể. Thực hiện nhiều mức tải, chẳng hạn 50, 100, 200 và 400 requests/second, thay vì chỉ đo một điểm.

Thu thập:

- Requests/second thực tế.
- p50, p95 và p99 latency.
- Error rate và timeout.
- Số request bị queue hoặc từ chối.
- CPU utilization và số core sử dụng.
- Database connection wait, pool saturation và external dependency latency.

Tăng tải từng bước đến khi một trong các giới hạn bị vi phạm: p95, p99, error rate, CPU hoặc memory. Throughput tối đa chỉ có ý nghĩa khi các SLO còn đạt. Một biến thể có throughput lớn hơn nhưng error rate cao hoặc p99 vượt ngưỡng không được xem là nhanh hơn cho production.

## 8. Đo CPU và hiệu quả xử lý

CPU usage tuyệt đối có thể gây hiểu nhầm nếu một biến thể xử lý nhiều request hơn biến thể còn lại. Hãy chuẩn hóa theo công việc hoàn thành.

Các số đo nên ghi:

- Average và peak CPU cores.
- CPU seconds trên mỗi 1.000 request thành công.
- Throughput tại cùng CPU quota.
- p95/p99 tại cùng request rate.
- CPU throttling trong container.
- GC CPU và pause time nếu có.

Ví dụ, native dùng 0,9 core để xử lý 1.000 request trong khi JVM dùng 0,8 core. Nếu native dùng ít memory hơn nhưng tiêu thụ CPU nhiều hơn, kết quả phụ thuộc giới hạn tài nguyên và chi phí từng loại tài nguyên của nền tảng.

Không dùng phần trăm CPU của host khi hai process chạy trên host có số core khác nhau. Ưu tiên core-seconds hoặc CPU time được tính từ cùng container/cgroup.

## 9. Đo memory đúng cách

Không so sánh JVM heap với Native Image heap như thể chúng là cùng một đại lượng. JVM heap là một phần memory; RSS và container memory còn bao gồm code, metadata, thread stacks, direct buffers, native allocations và shared libraries.

| Số đo | Ý nghĩa |
| --- | --- |
| RSS idle | Resident memory khi service đã ready nhưng gần như không có request |
| RSS steady state | Resident memory khi xử lý workload ổn định |
| Peak RSS | Mức RSS cao nhất trong cửa sổ đo |
| Container/cgroup memory | Memory mà container bị tính vào quota |
| JVM heap used/committed | Chỉ có ở biến thể JVM; dùng để chẩn đoán nội bộ |
| Native heap/GC metrics | Chỉ dùng khi runtime và binder cung cấp; không thay thế RSS/cgroup |
| OOM/restart count | Xác định biến thể có vượt giới hạn hoặc bị hệ thống kill |

Đo memory ở idle và tại cùng request rate. Một native executable có RSS thấp khi idle nhưng tăng nhanh dưới tải có thể không tiết kiệm tổng thể như dự đoán.

Quy tắc so sánh:

- Dùng cùng memory limit của container.
- Dùng cùng số request đang xử lý và cùng thời gian ổn định.
- Theo dõi peak và percentile, không chỉ một snapshot.
- Ghi rõ memory có bao gồm sidecar, proxy và agent hay không.
- Giữ metrics/tracing configuration giống nhau vì telemetry cũng tiêu thụ memory.

Nếu JVM được cấu hình `-Xmx` quá lớn, RSS vẫn có thể thấp hơn heap maximum; không dùng Xmx làm số đo memory thực tế.

## 10. Đo chi phí build và pipeline CI/CD

Native Image build thường tốn CPU, memory và thời gian hơn JVM packaging. Native Build có thể cần runner nhiều RAM, toolchain hệ điều hành và một job riêng cho từng platform.

Ghi lại cho mỗi pipeline:

- Clean build duration và incremental build duration.
- Native Image compilation duration.
- Peak RSS hoặc memory limit của builder.
- CPU time, số thread và thời gian queue.
- Tỷ lệ build fail/retry.
- Số OS/architecture target phải tạo.
- Thời gian kiểm thử native và thời gian publish.
- Dung lượng artifact/container image và chi phí lưu trữ/transfer.

GraalVM Build Output cung cấp thông tin về tài nguyên build, peak RSS, CPU load, thời gian các stage và build artifacts. Dùng output đó để xác định native build cần runner bao nhiêu RAM/CPU, thay vì chỉ ghi tổng thời gian.

Native pipeline có thể cần matrix runner theo OS/architecture, kiểm thử riêng cho reflection/resources/JNI/serialization, quản lý GraalVM/Native Build Tools version, theo dõi reachability metadata, xử lý khác biệt ABI/libc/CPU target và build lại nhiều image khi có bản vá bảo mật. Nếu chỉ tính thời gian compile mà không tính test, retry, runner, artifact và engineering effort, báo cáo sẽ đánh giá thấp tổng chi phí.

## 11. Mô hình hóa tổng chi phí

Tách chi phí theo vòng đời:

\[
C_{\text{total}} =
C_{\text{CI}} +
C_{\text{runtime}} +
C_{\text{distribution}} +
C_{\text{operations}}
\]

Trong đó:

- `C_CI`: runner minutes, native build workers, cache và retry.
- `C_runtime`: CPU, memory, replica count và thời gian chạy.
- `C_distribution`: image storage, registry transfer và artifact retention.
- `C_operations`: công sức bảo trì pipeline, hints, platform matrix và incident response.

Công thức ước lượng chi phí CI:

\[
C_{\text{CI}} =
N_{\text{builds}}
\times
\sum_{i=1}^{n}
\left(
\frac{T_i}{60}
\times
R_i
\right)
\]

`T_i` là số phút của job platform i; `R_i` là giá runner mỗi phút. Dùng giá thực tế của CI provider và loại runner. Nếu job chạy song song, tổng runner-minutes vẫn là tổng thời gian tính phí của từng job.

Chi phí runtime phải dựa trên số replica thực sự cần để đáp ứng SLO. Một native replica có thể dùng ít memory hơn nhưng throughput thấp hơn; khi đó hệ thống có thể cần nhiều replica hoặc CPU hơn. Đừng giả định giảm RSS trên một instance tự động làm giảm hóa đơn cloud.

## 12. Ví dụ dữ liệu benchmark

Bảng dưới đây là **dữ liệu giả định để minh họa cách phân tích**, không phải số đo mặc định của Spring Boot hay GraalVM. Giả sử cả ba biến thể đều qua toàn bộ functional gate và được đo trên cùng host, cùng container limits, cùng dataset và cùng workload.

| Chỉ số | JVM thường | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Median ready time | 2,75 s | 2,10 s | 0,58 s |
| RSS idle | 210 MiB | 198 MiB | 92 MiB |
| RSS tại 200 req/s | 390 MiB | 382 MiB | 248 MiB |
| p95 tại 200 req/s | 96 ms | 94 ms | 103 ms |
| p99 tại 200 req/s | 185 ms | 178 ms | 196 ms |
| Max throughput trong SLO | 1.280 req/s | 1.300 req/s | 1.160 req/s |
| CPU core-seconds / 1.000 request | 0,82 | 0,79 | 0,87 |
| Clean build duration | 1,6 min | 2,4 min | 12,5 min |
| Peak builder RSS | 1,4 GiB | 1,8 GiB | 7,4 GiB |

### Đọc kết quả

- Spring AOT cải thiện ready time từ 2,75 giây xuống 2,10 giây ngay cả khi vẫn chạy trên JVM.
- Native đạt ready time thấp nhất và giảm RSS idle/steady-state trong ví dụ.
- JVM + AOT có throughput cao hơn một chút và p95 thấp hơn native tại cùng 200 req/s.
- Native dùng nhiều CPU hơn trên mỗi 1.000 request trong bộ dữ liệu minh họa.
- Native build lâu hơn và cần peak builder memory lớn hơn rõ rệt.

Không suy luận rằng native luôn có throughput thấp hơn. Kết quả phụ thuộc workload, GraalVM version, optimization, GC, PGO, CPU target và thư viện. Dữ liệu trên chỉ mô tả một phép đo giả định.

## 13. Ma trận chấm điểm và quyết định

Chỉ chấm điểm sau khi các phương án đã qua functional gate. Đặt trọng số theo mục tiêu dịch vụ; điểm 1–5, trong đó 5 là tốt nhất. Với tiêu chí chi phí và độ phức tạp, điểm cao nghĩa là ít tốn kém hoặc dễ vận hành hơn.

Ví dụ cho Order API chạy liên tục:

| Tiêu chí | Trọng số | JVM + AOT | Native |
| --- | ---: | ---: | ---: |
| Startup/ready time | 15 | 3 | 5 |
| Steady-state throughput | 15 | 5 | 4 |
| p95 latency | 20 | 5 | 4 |
| RSS tại tải mục tiêu | 15 | 2 | 5 |
| CPU trên mỗi request | 10 | 5 | 4 |
| CI/build cost | 15 | 5 | 1 |
| Operational complexity | 10 | 5 | 3 |
| **Tổng trọng số** | **100** |  |  |

Tính điểm có trọng số:

\[
S = \frac{\sum_i w_i \times s_i}{100}
\]

Với điểm ví dụ:

- JVM + AOT: 4,25/5.
- Native: 3,75/5.

Trong workload giả định này, JVM + AOT là khuyến nghị ban đầu cho Order API chạy liên tục: startup 2,10 giây vẫn đạt ngưỡng 10 giây, throughput và p95 tốt hơn, còn chi phí CI và vận hành thấp hơn.

Native vẫn có lợi thế rõ ràng về startup và memory. Nếu workload chuyển thành worker scale-to-zero với yêu cầu ready time dưới một giây hoặc giới hạn container memory dưới 300 MiB tại tải mục tiêu, JVM + AOT có thể không qua hard gate trong khi native vẫn đạt. Khi đó, quyết định phải đổi sang native dù điểm trung bình ở ma trận cũ thấp hơn.

### Thử độ nhạy của trọng số

Không để một bộ trọng số tùy ý quyết định kiến trúc. Hãy thử ít nhất hai kịch bản:

- **Throughput-first:** tăng trọng số throughput, p95 và CPU/request cho service chạy dài hạn.
- **Startup/memory-first:** tăng trọng số ready time, RSS và mật độ replica cho worker ngắn hạn hoặc scale-to-zero.

Nếu khuyến nghị thay đổi chỉ vì thay trọng số một ít, báo cáo cần ghi rằng quyết định nhạy với mục tiêu và cần thêm dữ liệu. Nếu một hard SLA loại một phương án, không cần dùng điểm tổng để che lấp kết quả đó.

## 14. Khi nào nên chọn từng phương án?

### JVM thường hoặc JVM + AOT

Ưu tiên JVM khi:

- Service chạy lâu, JIT có đủ thời gian tối ưu workload.
- Throughput hoặc latency steady-state là tiêu chí chính.
- Thư viện phụ thuộc dynamic class loading, Java agent hoặc runtime behavior khó chuyển sang Native Image.
- Release thường xuyên và chi phí build native làm chậm feedback.
- Cần debugging, profiling và ecosystem tooling quen thuộc.

Cân nhắc JVM + AOT khi startup cần cải thiện nhưng vẫn muốn giữ JVM runtime. AOT có các giới hạn về classpath, bean graph, profile và condition được quyết định trong build; phải kiểm tra cấu hình deployment thực tế.

### GraalVM Native Image

Ưu tiên native khi:

- Cold start hoặc time-to-ready là hard requirement.
- Memory footprint quyết định mật độ workload hoặc số replica.
- Service/worker có vòng đời ngắn, thường scale từ zero.
- Dependency và chức năng đã được xác minh tương thích Native Image.
- Tổ chức có CI runner, native test và quy trình metadata đủ trưởng thành.

Native Image có các optimization level và cơ chế PGO; nếu workload CPU-bound, có thể benchmark PGO sau khi đã có baseline ổn định. PGO đòi hỏi instrumented build và workload đại diện để tạo profile, nên phải tính cả bước thu profile vào quy trình phát hành.

### Không bắt buộc toàn hệ thống dùng một runtime

Một hệ thống có thể dùng native cho API cần scale-to-zero, JVM + AOT cho service khởi động vừa phải và JVM thường cho worker CPU-bound chạy lâu. Đưa quyết định về cấp service/workload để tránh chuyển đổi toàn bộ nền tảng chỉ vì một lợi thế cục bộ.

## 15. Mẫu báo cáo quyết định

Dùng cấu trúc sau để biến benchmark thành một quyết định có thể review:

~~~text
DECISION REPORT: JVM vs GRAALVM NATIVE IMAGE

1. Executive summary
   - Service:
   - Workload:
   - Recommended runtime:
   - Decision owner:
   - Date / source commit:

2. Requirements and hard gates
   - Functional test results:
   - Security / integration compatibility:
   - Startup SLO:
   - Latency / throughput SLO:
   - Memory / CPU limits:
   - Supported OS / architecture:

3. Variants
   - Regular JVM:
   - JVM + Spring AOT:
   - GraalVM Native Image:
   - JDK / GraalVM / Spring Boot versions:

4. Measurement methodology
   - Hardware / container limits:
   - Dataset and request mix:
   - Warm-up and run duration:
   - Repetitions and percentile method:
   - Metrics and tools:

5. Results
   - Ready time:
   - p50 / p95 / p99:
   - Throughput / error rate:
   - CPU per successful request:
   - RSS / cgroup memory:
   - Build duration / peak builder memory:

6. Cost model
   - CI runner cost:
   - Runtime compute:
   - Artifact / image storage:
   - Engineering and operational cost:

7. Decision matrix
   - Criteria and weights:
   - Scores:
   - Sensitivity scenarios:

8. Recommendation
   - Chosen runtime:
   - Why it meets hard gates:
   - Trade-offs accepted:
   - Risks and mitigations:

9. Rollout and review
   - Canary scope:
   - Rollback condition:
   - Metrics to watch:
   - Re-evaluation trigger:
~~~

Báo cáo phải lưu raw data, script benchmark, config, build logs và source commit để người khác có thể tái hiện. Không chỉ lưu bảng điểm cuối cùng.

## 16. Rollout, xác nhận production và điều kiện đánh giá lại

Benchmark trong lab là cơ sở lựa chọn, chưa phải bằng chứng cuối cùng về chi phí production. Sau khi chọn:

1. Deploy một canary nhỏ với cùng resource limit và traffic policy.
2. Theo dõi startup/ready time, p95/p99, throughput, CPU, RSS/cgroup memory và error rate.
3. So sánh cùng cửa sổ thời gian và workload với phiên bản hiện tại.
4. Kiểm tra autoscaling, rollout duration, crash/restart và graceful shutdown.
5. Ghi nhận build duration, retry và thời gian phát hành trong CI.
6. Chỉ mở rộng rollout khi hard SLO và functional checks đều đạt.
7. Giữ rollback artifact và quy trình quay về runtime trước đó.

Đánh giá lại khi có thay đổi lớn về Spring Boot, GraalVM, JDK, dependency, traffic profile, CPU architecture, cloud pricing hoặc CI platform. Một dependency mới có thể làm native build chậm hơn hoặc không còn tương thích; một JDK mới có thể cải thiện JVM baseline; một workload mới có thể làm thay đổi lợi thế memory/throughput.

## 17. Bài thực hành: lập báo cáo cho Order API

Dùng một ứng dụng Spring Boot có REST API, database, một HTTP client gọi partner service và Actuator.

### Phần A — chuẩn bị ba biến thể

1. Build và chạy JAR JVM thông thường.
2. Build AOT assets và chạy trên JVM với `spring.aot.enabled=true`.
3. Build native executable bằng GraalVM.
4. Giữ cùng commit, dependency versions, endpoint và business configuration.
5. Ghi lại mọi khác biệt về JVM options, GC, Native Image arguments và container base image.

### Phần B — functional gate

1. Chạy cùng bộ unit/integration test cho cả ba biến thể.
2. Kiểm tra database transaction, serialization, security và partner HTTP client.
3. Kiểm tra health/readiness, graceful shutdown và logging.
4. Chạy native test cho reflection, resources, proxy, serialization hoặc JNI nếu ứng dụng có dùng.
5. Loại phương án không qua chức năng bắt buộc khỏi vòng chấm điểm.

### Phần C — benchmark

1. Đo ít nhất 20 cold starts cho mỗi biến thể.
2. Đo ready time và first successful request.
3. Warm-up theo cùng thời gian.
4. Chạy tải 50, 100, 200 và 400 req/s bằng cùng k6 script.
5. Thu p50/p95/p99, throughput, error rate, CPU core-seconds và RSS.
6. Ghi peak RSS của native-image builder và tổng thời gian CI.
7. Lặp lại thí nghiệm nếu host nhiễu hoặc kết quả biến động lớn.

### Phần D — báo cáo và quyết định

1. Điền raw data vào bảng so sánh.
2. Xác định phương án nào qua tất cả hard gate.
3. Tính chi phí CI theo số build và số platform.
4. Ước lượng runtime cost theo số replica cần để đáp ứng SLO.
5. Chọn trọng số và tính decision score.
6. Thử kịch bản throughput-first và startup/memory-first.
7. Viết khuyến nghị, trade-off, rollout plan và rollback condition.
8. Nêu rõ dữ liệu nào còn thiếu và cách thu thập trong production canary.

### Câu hỏi tự kiểm tra

1. Vì sao cần so sánh JVM thường, JVM + AOT và native thay vì chỉ hai biến thể?
2. Functional compatibility phải được dùng như hard gate như thế nào?
3. `application.ready.time` khác thời điểm request đầu tiên thành công ra sao?
4. Vì sao phải tách cold start khỏi steady-state benchmark?
5. Vì sao JVM heap không thể thay thế RSS hoặc cgroup memory khi so sánh native?
6. Throughput tối đa phải gắn với những SLO nào?
7. Vì sao cần chuẩn hóa CPU time theo số request thành công?
8. Những yếu tố nào tạo nên chi phí build native ngoài thời gian compile?
9. Vì sao giảm memory trên một replica chưa chắc làm giảm runtime bill?
10. Khi nào JVM + AOT là một lựa chọn trung gian hợp lý?
11. Khi nào hard startup/memory SLO khiến native trở thành lựa chọn bắt buộc?
12. Vì sao cần thử độ nhạy của trọng số decision matrix?
13. Những thay đổi nào khiến báo cáo JVM/native cần được đánh giá lại?

**Tiêu chí đạt:** xây dựng được ba biến thể so sánh; xác định và kiểm tra đầy đủ hard functional gates; thiết kế benchmark cold start và steady state có kiểm soát; đo startup, latency, throughput, error rate, CPU, RSS và chi phí native build; tính được chi phí CI/runtime; lập decision matrix có trọng số và sensitivity analysis; cuối cùng viết báo cáo khuyến nghị kèm trade-off, rollout và rollback dựa trên dữ liệu.

## Tài liệu chính thức

- Spring Boot — Metrics and Application Startup Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Testing GraalVM Native Images: https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html
- Spring Boot — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/reference/packaging/aot.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/4.2/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Maven Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
- Spring Boot — Gradle Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- GraalVM — Optimizations and Performance: https://www.graalvm.org/jdk25/reference-manual/native-image/optimizations-and-performance/
- GraalVM — Native Image Build Output: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/
- GraalVM — Native Image Basics: https://www.graalvm.org/latest/reference-manual/native-image/basics/
