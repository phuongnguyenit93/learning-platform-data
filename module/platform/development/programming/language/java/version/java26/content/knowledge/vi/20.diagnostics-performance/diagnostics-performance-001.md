# Thiết lập tải đo, đường cơ sở và điều kiện tái hiện

Muốn biết một thay đổi Java có cải thiện hiệu năng hay không, trước tiên phải tạo được một phép đo có thể lặp lại. Kết quả chỉ có ý nghĩa khi workload, dữ liệu, môi trường chạy, cấu hình JVM và cách thu thập metric được ghi nhận rõ ràng. Một lần chạy nhanh hơn trên máy developer chưa đủ để kết luận ứng dụng sẽ nhanh hơn trong production.

Bài này trình bày quy trình xây dựng workload đại diện, thiết lập đường cơ sở (baseline), đo cold start và steady state riêng, kiểm soát nhiễu, thu thập dữ liệu bằng JFR/GC log/JMH và tái hiện một vấn đề từ production. Các cải tiến hiệu năng của JDK 26 như G1 giảm đồng bộ và AOT object caching được dùng làm ví dụ cho cách so sánh phiên bản JDK mà không nhầm thay đổi mặc định với lợi ích của code.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định giả thuyết, chỉ số thành công và workload đại diện trước khi đo.
- Phân biệt benchmark vi mô (microbenchmark), benchmark toàn ứng dụng và load test.
- Tạo baseline có thể lặp lại trên cùng phần cứng, runtime, dữ liệu và traffic profile.
- Đo throughput, latency percentile, error rate, CPU, memory, allocation và GC theo cùng một khoảng thời gian.
- Tách cold startup, JIT warm-up và steady-state performance.
- Dùng JMH cho microbenchmark và tránh các lỗi dead-code elimination, constant folding, thiếu warm-up hoặc đo trong IDE.
- Dùng JFR, `jcmd`, unified GC logging để tìm nguyên nhân khi số liệu cho thấy regression.
- Tái hiện vấn đề production bằng dữ liệu đã ẩn thông tin nhạy cảm và tải có kiểm soát.
- So sánh JDK 25/26 trong khi xét đến thay đổi mặc định của JDK 26.

## 1. Bắt đầu bằng câu hỏi và giả thuyết đo

Không bắt đầu bằng việc thêm cờ JVM hoặc chạy một benchmark ngẫu nhiên. Hãy mô tả vấn đề có thể quan sát được:

- Endpoint tìm kiếm có p99 cao hơn mục tiêu khi tải đồng thời tăng.
- Sau khi nâng JDK, startup container lâu hơn dù steady-state throughput không đổi.
- CPU tăng trong khi request rate gần như giữ nguyên.
- Số lần GC hoặc tổng pause tăng sau khi đổi cấu trúc object.
- Một luồng xử lý bị chờ lock hoặc I/O lâu hơn khi chạy dữ liệu lớn.

Chuyển câu hỏi thành giả thuyết có thể kiểm chứng. Ví dụ:

> Với cùng container, dữ liệu và request rate, JDK 26 sẽ giữ throughput của endpoint ở mức hiện tại, giảm p99 và không làm tăng error rate hoặc CPU throttling.

Xác định trước:

1. **Phạm vi:** một method, một service, một endpoint hay toàn bộ hệ thống.
2. **Workload:** thao tác nào, phân bố kích thước dữ liệu ra sao, bao nhiêu request/giây và mức đồng thời nào.
3. **Chỉ số chính:** ví dụ p99 latency hoặc throughput tại một error rate tối đa.
4. **Chỉ số bảo vệ:** CPU, memory, GC, error rate, queue depth, timeout và chi phí hạ tầng.
5. **Điều kiện đạt:** mức cải thiện tối thiểu và regression tối đa có thể chấp nhận.

Nếu không có tiêu chí trước khi chạy, nhóm rất dễ chọn metric thuận lợi sau khi đã nhìn kết quả.

## 2. Chọn đúng loại phép đo

Ba cấp độ đo trả lời các câu hỏi khác nhau:

| Loại phép đo | Đơn vị quan sát | Dùng để trả lời | Công cụ phù hợp |
|---|---|---|---|
| Microbenchmark | Method hoặc đoạn code nhỏ | Phương án A có rẻ hơn B trong điều kiện cô lập không? | JMH |
| Component/benchmark tích hợp | Một component với dependency đại diện | Chi phí của serialization, database client, cache hoặc HTTP client thay đổi thế nào? | Harness tích hợp, JMH nếu ranh giới đo phù hợp |
| Load test / system benchmark | Request hoặc tác vụ đầu cuối | Hệ thống chịu tải bao nhiêu, tail latency và error rate ra sao? | Gatling, k6, Locust hoặc harness nội bộ |

Không dùng microbenchmark để dự đoán trực tiếp throughput của toàn hệ thống. Một method nhanh hơn có thể không cải thiện request latency nếu bottleneck nằm ở database, network, lock hoặc queue. Ngược lại, một thay đổi làm method tốn thêm vài nanosecond có thể giảm allocation hoặc contention và cải thiện toàn hệ thống.

JMH là Java Microbenchmark Harness của OpenJDK, dành cho benchmark nano/micro/milli/macro trên JVM. Tài liệu JMH khuyến nghị tạo project benchmark độc lập bằng Maven archetype và bật annotation/bytecode processing để sinh mã harness. Chạy benchmark trong IDE hoặc project hiện có có thể làm setup phức tạp và giảm độ tin cậy.

## 3. Xây dựng workload đại diện

Workload cần thể hiện cách ứng dụng thật được sử dụng, không chỉ tạo ra nhiều lệnh gọi method.

### Mô tả request mix

Ghi lại tỷ lệ các loại thao tác. Ví dụ một API bán hàng có thể có:

| Nhóm thao tác | Tỷ lệ minh họa | Dữ liệu cần mô tả |
|---|---:|---|
| Đọc thông tin sản phẩm | 55% | Cache hit/miss, số trường, kích thước response |
| Tìm kiếm | 20% | Độ dài từ khóa, số kết quả, phân bố phổ biến/hiếm |
| Tạo đơn | 15% | Số mặt hàng, validate, transaction và ghi database |
| Cập nhật trạng thái | 10% | Số lần retry, lock và cạnh tranh cùng một đơn |

Các tỷ lệ chỉ là ví dụ. Dùng log/trace hoặc số liệu sản phẩm đã ẩn dữ liệu nhạy cảm để xác định request mix thật. Nếu chỉ benchmark thao tác đọc cache hit, kết quả không phản ánh hệ thống có database miss và ghi dữ liệu.

### Giữ nguyên phân bố dữ liệu

Không chỉ ghi tổng số bản ghi. Cần mô tả phân bố kích thước payload, số phần tử collection, độ dài chuỗi, cache hit ratio, tỷ lệ null, số lượng object sống và độ lệch dữ liệu. Workload có 90% request nhỏ và 10% request rất lớn có thể tạo tail latency khác hẳn workload mà mọi request đều cùng kích thước trung bình.

Nếu dùng production trace, loại bỏ token, thông tin cá nhân, dữ liệu bí mật và định danh có thể truy ngược người dùng. Giữ lại đặc tính kỹ thuật như kích thước, tần suất, thứ tự và tương quan request nếu điều đó cần cho việc tái hiện.

### Mô hình tải: closed-loop và open-loop

- **Closed-loop:** client gửi request tiếp theo sau khi request trước hoàn tất. Khi server chậm, tốc độ phát request tự giảm. Cách này hữu ích để kiểm tra tải theo số client đồng thời, nhưng có thể che khuất queueing và tail latency khi hệ thống quá tải.
- **Open-loop:** client phát request theo arrival rate đã đặt trước, không chờ request trước hoàn tất mới phát request tiếp theo. Cách này phù hợp để kiểm tra khả năng xử lý một tốc độ đến cố định và phát hiện queue growth. Phải theo dõi request bị xếp hàng, drop và timeout.

Khi đánh giá overload, cần cân nhắc coordinated omission: một client chỉ đo thời gian từ lúc gửi request thực tế có thể bỏ qua khoảng thời gian lẽ ra request phải được gửi nhưng client đang bị chậm. Dùng load generator hỗ trợ mô hình arrival-rate hoặc ghi nhận thời điểm phát request dự kiến để không đánh giá thấp tail latency.

### Xác định các mức tải

Một kịch bản có thể gồm:

1. **Smoke:** tải nhỏ để xác nhận test và dữ liệu hợp lệ.
2. **Normal:** mức traffic điển hình.
3. **Peak:** mức tải đỉnh thường gặp.
4. **Stress:** tăng tải vượt peak để tìm điểm bão hòa.
5. **Soak:** giữ tải ổn định trong thời gian dài để tìm memory leak, queue tích lũy hoặc suy giảm theo thời gian.

Không tăng tải ngay từ đầu tới mức tối đa. Xác nhận hệ thống chạy ổn định ở từng nấc và ghi rõ thời điểm bắt đầu, kết thúc cùng trạng thái warm-up.

## 4. Tạo đường cơ sở (baseline)

Baseline là kết quả đo của phiên bản đang được xem là chuẩn để so sánh. Baseline phải có cấu hình và môi trường được lưu lại, không chỉ là một con số throughput.

Một baseline tối thiểu nên ghi:

| Nhóm | Thông tin phải lưu |
|---|---|
| Source | Git commit, build ID, dependency lock/version, cấu hình ứng dụng |
| Java runtime | Vendor, `java -version`, build/update, architecture, JVM flags |
| OS/container | OS/kernel, image digest, CPU model, số CPU được cấp, memory limit, quota/throttling |
| JVM | Collector, `-Xms`, `-Xmx`, classpath/module path, agents, AOT cache state |
| Workload | Request mix, arrival rate, concurrency, dataset ID/checksum, payload distribution |
| Dependency | Database version/config, cache, broker, service giả lập hoặc remote dependency |
| Measurement | Warm-up duration, measurement duration, repetitions, load generator version |
| Results | Throughput, p50/p95/p99/max latency, error rate, CPU, RSS, heap, GC, queue depth |

Ví dụ ghi lại runtime và cờ của một JVM đang chạy:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.uptime
```

`jcmd` cần chạy trên cùng máy với JVM và thường phải dùng cùng effective user/group đã khởi chạy process. Danh sách lệnh có thể khác giữa các runtime; kiểm tra bằng `jcmd <pid> help`.

Đừng chỉ ghi `java -version` từ terminal của người chạy benchmark. JVM bên trong container, service manager hoặc build agent có thể là một executable khác. Thu thập thông tin từ đúng process đang được đo.

## 5. Kiểm soát môi trường để giảm nhiễu

Các yếu tố sau có thể làm một lần chạy nhanh hoặc chậm mà không liên quan tới thay đổi code:

- CPU đang bị process khác sử dụng, CPU frequency scaling, thermal throttling hoặc host oversubscription.
- Container có CPU quota thấp hơn số core mà host báo cáo; CPU throttling không được nhìn thấy nếu chỉ xem utilization trên host.
- Memory limit, swap, page fault, NUMA placement, Transparent Huge Pages và áp lực bộ nhớ của máy.
- Database/cache/network dùng chung bị tải từ workload khác.
- Log level, metrics exporter, tracing agent, JFR profile, debugger hoặc antivirus.
- JIT compilation, class loading, cache warming, connection pool và DNS lookup chưa ổn định.
- Dataset khác nhau, cache state khác nhau, random seed khác nhau hoặc thứ tự request thay đổi.

Trước mỗi lượt đo, xác nhận máy không chạy tác vụ nền nặng, container có cùng quota, dependency ở trạng thái tương đương và không có rollout khác diễn ra đồng thời. Với phép đo quan trọng, dùng máy hoặc node dành riêng và chạy các phiên bản theo thứ tự xen kẽ/ngẫu nhiên để giảm ảnh hưởng của nhiệt độ, tải nền và drift theo thời gian.

Nếu production dùng container, benchmark cũng phải chạy trong container với CPU/memory limit tương đương. Một phép đo trên máy 32 core không đại diện cho pod được giới hạn 2 CPU.

## 6. Tách cold start, warm-up và steady state

JVM cần thời gian để khởi động, nạp class, chạy interpreter, biên dịch JIT, tạo connection pool và làm nóng cache. Không gộp tất cả các giai đoạn vào một số throughput duy nhất.

| Pha | Đặc điểm | Cách đo |
|---|---|---|
| Cold start | Process mới, class chưa nạp, cache/connection chưa tạo | Khởi chạy process mới; đo từ mốc đã định đến readiness hoặc request đầu tiên hoàn tất |
| Warm-up | JIT, profile và cache dần ổn định | Gửi workload đại diện; ghi throughput/latency theo thời gian |
| Steady state | Các chỉ số không còn xu hướng thay đổi đáng kể | Đo trong cửa sổ cố định sau khi warm-up đạt tiêu chí |
| Shutdown | Đóng connection, flush và dừng process | Đo riêng nếu shutdown time là yêu cầu sản phẩm |

Không chọn warm-up chỉ theo một con số mặc định như “chờ 30 giây”. Theo dõi throughput, latency và compilation/CPU cho tới khi đạt tiêu chí ổn định đã định trước. Một số ứng dụng có workload dài hạn hoặc cache tăng dần nên không có steady state rõ ràng; trong trường hợp đó cần đo theo các giai đoạn vận hành thực tế.

Với cold start, mỗi mẫu nên bắt đầu từ một process mới. Ghi lại có hay không có page cache, container image đã được pull hay chưa, AOT cache được tạo/đọc hay không, và dependency đã sẵn sàng chưa. Không so cold start của một bản đã warm cache với bản còn lại vừa tạo mới.

Với steady state, không tính thời gian startup vào throughput nếu câu hỏi là hiệu năng request sau khi hệ thống đã sẵn sàng. Nếu câu hỏi là thời gian scale-out, startup và readiness lại là metric chính.

## 7. Chọn metric và đọc kết quả

Không có một chỉ số hiệu năng duy nhất. Ít nhất cần xem kết quả theo các nhóm sau:

| Metric | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Throughput | Request/operation hoàn tất trong một đơn vị thời gian | Hệ thống xử lý được bao nhiêu công việc? |
| p50 latency | Trung vị thời gian phản hồi | Trải nghiệm của request điển hình thế nào? |
| p95/p99 latency | Tail latency | Một tỷ lệ nhỏ request chậm đến mức nào? |
| Maximum latency | Request chậm nhất trong cửa sổ đo | Có outlier nghiêm trọng hay không? |
| Error/timeout rate | Tỷ lệ request không thành công | Tăng throughput có phải đổi bằng lỗi hay không? |
| CPU time/utilization | Tài nguyên CPU tiêu thụ | Chi phí xử lý có giảm hay bị throttling? |
| RSS/heap/live set | Bộ nhớ process và object còn sống | Có tăng footprint hoặc giữ object lâu hơn không? |
| Allocation rate | Lượng object được cấp phát theo thời gian | GC pressure có thể tăng do allocation không? |
| GC count/pause/CPU | Số lần GC, thời gian dừng và CPU dành cho GC | GC ảnh hưởng latency và throughput ra sao? |
| Queue depth | Công việc đang chờ xử lý | Hệ thống có tích lũy backlog không? |

Không chỉ báo cáo average latency. Average có thể trông tốt dù p99 rất xấu. Với hệ thống hướng người dùng, tail latency thường quyết định timeout và trải nghiệm. Cần ghi cả phân vị, cửa sổ thời gian và số lượng mẫu vì p99 tính từ vài chục request không đáng tin như p99 tính từ hàng triệu request.

Khi so sánh throughput, giữ error rate và latency trong giới hạn. Một hệ thống có thể tăng số request hoàn tất bằng cách trả lỗi nhanh hoặc bỏ request; đó không phải cải thiện hữu ích.

### Tính mức thay đổi

Với metric mà càng cao càng tốt như throughput:

\[
\text{Improvement (\%)} = \frac{B-A}{A} \times 100
\]

Với metric mà càng thấp càng tốt như latency hoặc CPU time:

\[
\text{Reduction (\%)} = \frac{A-B}{A} \times 100
\]

Trong đó `A` là baseline, `B` là kết quả sau thay đổi. Luôn ghi giá trị tuyệt đối bên cạnh phần trăm. Giảm p99 từ 2 giây xuống 1 giây khác ý nghĩa vận hành với giảm từ 2 ms xuống 1 ms dù cùng 50%.

## 8. Lặp lại và đánh giá độ tin cậy

Một lần chạy có thể bị ảnh hưởng bởi JIT, GC, CPU scheduling hoặc dependency. Với benchmark so sánh, hãy:

1. Chạy warm-up và measurement theo cùng quy trình.
2. Lặp lại nhiều fork/process độc lập; với JMH dùng `@Fork` để tạo JVM mới cho từng fork.
3. Xen kẽ hoặc ngẫu nhiên thứ tự baseline/candidate để giảm ảnh hưởng drift.
4. Giữ cùng dataset, request mix và thời lượng measurement.
5. Báo cáo phân bố kết quả giữa các lần chạy, không chỉ chọn lần tốt nhất.
6. Ghi rõ outlier và nguyên nhân nếu loại bỏ một lượt đo; không xóa kết quả xấu chỉ vì không phù hợp giả thuyết.

Với các phép đo có dao động, dùng median và khoảng tin cậy hoặc phương pháp thống kê phù hợp. Nếu hai kết quả chồng lấn trong mức nhiễu, không kết luận rằng một phiên bản nhanh hơn. Một thay đổi nhỏ hơn độ dao động của phép đo cần nhiều mẫu hơn hoặc một setup ít nhiễu hơn.

Không chạy baseline vào buổi sáng và candidate vào buổi tối trên hai máy khác nhau rồi so sánh như một thí nghiệm kiểm soát. Nếu không thể dùng cùng máy, ghi rõ khác biệt phần cứng và chạy một bộ đối chứng để ước lượng tác động môi trường.

## 9. Dùng JMH cho microbenchmark

JMH xử lý một số vấn đề khó của benchmark trên JVM: warm-up, fork, measurement iteration, đồng bộ kết quả và tạo harness. Không tự viết vòng lặp `System.nanoTime()` để đo một method nhỏ nếu JMH có thể mô hình hóa chính xác workload đó.

Ví dụ benchmark NFC normalization:

```java
import java.text.Normalizer;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class NormalizerBenchmark {
    @Param({"Tiếng Việt", "a\u0306\u0301", "A full width: ＡＢＣ"})
    public String input;

    @Benchmark
    public String normalizeNfc() {
        return Normalizer.normalize(input, Normalizer.Form.NFC);
    }
}
```

Các giá trị warm-up, measurement và fork trong ví dụ là điểm bắt đầu minh họa, không phải cấu hình đúng cho mọi benchmark. Hãy tăng thời lượng khi workload có compilation hoặc GC dài, và kiểm tra score có ổn định giữa các iteration không.

Một số quy tắc quan trọng:

- Trả về kết quả benchmark hoặc dùng `Blackhole.consume()` để kết quả không bị loại bỏ như dead code.
- Tránh input hằng mà JIT có thể constant-fold nếu production thực tế dùng nhiều dữ liệu.
- Đưa dữ liệu test vào `@State`/`@Param` để kiểm soát và tái sử dụng có chủ đích.
- Không tự viết một vòng lặp lớn bên trong method benchmark để “tăng thời gian đo”; điều đó có thể thay đổi hành vi JIT và làm sai đơn vị kết quả.
- Dùng `@Fork` để tách profile JIT giữa các lần chạy; tránh benchmark A và B liên tiếp trong cùng một JVM rồi để profile của A ảnh hưởng B.
- Chạy JMH từ project benchmark độc lập được cấu hình đúng annotation processor; không lấy số liệu từ debugger hoặc IDE làm kết quả chính thức.
- Đọc output JMH cùng error bar, score, unit, mode và số fork; không chỉ copy một con số.

JMH hỗ trợ throughput, average time, sample time và single-shot time. Chọn mode phù hợp với câu hỏi. `SingleShotTime` có thể phù hợp cho thao tác một lần/cold path nhưng vẫn cần kiểm soát fork và trạng thái process; nó không tự động tương đương startup của một ứng dụng hoàn chỉnh.

## 10. Tạo baseline cho ứng dụng đầu cuối

Một load test service cần cùng phiên bản client, cùng workload và cùng dependency. Quy trình tham khảo:

1. Build artifact từ commit baseline và lưu checksum.
2. Khởi chạy trên container/VM đã cố định CPU, memory và runtime.
3. Chờ readiness và thực hiện warm-up theo workload đại diện.
4. Chạy load test ở các mức normal, peak và stress.
5. Thu metrics ở cùng cửa sổ thời gian: throughput, p50/p95/p99, error rate, CPU, RSS, heap, GC và queue depth.
6. Lưu JFR/GC logs nếu cần chẩn đoán; ghi rõ profiling có bật trong lượt đo hay không.
7. Dừng ứng dụng, khởi chạy lại process mới và lặp lại theo cùng điều kiện.
8. Chạy candidate theo cùng kịch bản; nếu có thể, xen kẽ thứ tự baseline/candidate.

Không dùng một load generator duy nhất trên cùng máy nhỏ với server nếu CPU của client cạnh tranh với CPU server. Theo dõi tài nguyên của load generator và đặt nó trên node riêng khi cần đo chính xác.

Nếu database hoặc remote service là một phần của mục tiêu đo, hãy dùng dependency thật hoặc môi trường tương đương. Mock có thể hữu ích để cô lập CPU của service nhưng không thể thay thế phép đo end-to-end khi bottleneck thật nằm ở I/O.

## 11. Thu thập chẩn đoán bằng JFR và jcmd

JDK Flight Recorder (JFR) ghi các event có timestamp về JVM, thread, CPU, allocation, GC, lock và I/O. Đây là công cụ phù hợp để tìm nguyên nhân sau khi baseline cho thấy một chỉ số bất thường.

### Ghi khi khởi động ứng dụng

```bash
java \
  -XX:StartFlightRecording=filename=baseline.jfr,settings=profile,dumponexit=true \
  -jar app.jar
```

`profile.jfc` thu thập nhiều dữ liệu hơn `default.jfc` và có thể có overhead cao hơn. Oracle ghi nhận recording profile cố định với default settings có overhead dưới 2% với phần lớn ứng dụng, nhưng cần tự đo overhead trên workload của mình. Continuous recording dùng default settings thường có ảnh hưởng rất thấp và phù hợp giữ dữ liệu gần nhất để điều tra sự cố.

### Bắt đầu recording trên JVM đang chạy

```bash
jcmd <pid> JFR.start name=Performance settings=profile duration=5m filename=performance.jfr
jcmd <pid> JFR.check
```

Sau khi recording hoàn tất:

```bash
jfr summary performance.jfr
jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.ThreadCPULoad performance.jfr
```

Có thể mở file `.jfr` bằng JDK Mission Control (JMC) để xem hot methods, allocation, lock contention, GC, thread và I/O. JMC được phân phối riêng, không nhất thiết nằm trong bộ cài JDK.

### Event hữu ích theo triệu chứng

| Triệu chứng | Event/metric cần xem |
|---|---|
| CPU cao | `jdk.CPULoad`, `jdk.ThreadCPULoad`, execution samples |
| Lock contention | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, thread stack |
| Thread chờ hoặc bị park | `jdk.ThreadPark`, `jdk.ThreadSleep`, thread state |
| Network chậm | `jdk.SocketRead`, `jdk.SocketWrite` |
| File I/O chậm | `jdk.FileRead`, `jdk.FileWrite` |
| GC ảnh hưởng latency | `jdk.GCPhasePause`, allocation events, GC configuration |
| Virtual thread pinning | `jdk.VirtualThreadPinned` và stack trace liên quan |
| Exception tăng | `jdk.JavaExceptionThrow`, `jdk.JavaErrorThrow` |

Nhiều Java Application duration events mặc định chỉ ghi sự kiện dài hơn ngưỡng, thường là 20 ms. Không thấy event không chứng minh không có chờ ngắn hơn ngưỡng. Có thể giảm threshold khi điều tra một vấn đề cụ thể, nhưng ghi nhiều event hơn có thể làm tăng overhead và dung lượng recording.

Không bật Heap Statistics trong JFR khi đang đo latency thông thường. Tính năng này có thể kích hoạt một old GC ở đầu và cuối recording, làm thay đổi pause time của phép đo. Heap statistics phù hợp hơn khi điều tra live set hoặc memory leak.

## 12. GC log và môi trường JVM

Unified Logging giúp kiểm tra GC và safepoint trong cùng lần chạy:

```bash
java \
  -Xlog:gc*=info,gc+phases=debug,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

Khi phân tích, xem heap trước/sau GC, loại collection, pause time, phase chiếm thời gian, allocation pressure và Full GC. Phân biệt thời gian GC cycle với thời gian stop-the-world pause; G1 có nhiều công việc concurrent không làm ứng dụng dừng.

Không kết luận “GC chậm” chỉ từ số lần GC. Nếu pause thấp nhưng CPU GC cao, concurrent work có thể đang cạnh tranh CPU với application threads. Nếu pause dài nhưng CPU time thấp, kiểm tra CPU throttling, safepoint và môi trường OS.

Không thay đổi collector hoặc hàng loạt cờ tuning ngay sau khi thấy một pause. Trước hết xác định phase nào chiếm thời gian và liệu vấn đề đến từ live set, allocation rate, remembered set, reference processing, heap limit hay môi trường.

## 13. Tái hiện sự cố production

Một sự cố production chỉ có thể tái hiện khi giữ được những điều kiện gây ra nó. Hãy tạo một gói tái hiện có kiểm soát:

- Phiên bản ứng dụng và JDK/build chính xác.
- Runtime flags, container image, CPU/memory quota và giới hạn OS.
- Request mix, arrival rate, concurrency, payload size và dataset đã ẩn thông tin nhạy cảm.
- Trạng thái cache, connection pool, số lượng thread và dependency cần thiết.
- Khoảng thời gian trước, trong và sau khi sự cố xuất hiện.
- Metrics, log và JFR recording đã đồng bộ timestamp.

Tái hiện theo từng bước:

1. Chạy workload bình thường và xác nhận baseline.
2. Tăng đúng một yếu tố nghi ngờ, ví dụ concurrency hoặc tỷ lệ cache miss.
3. Quan sát metric nào thay đổi trước: queue depth, CPU, lock wait, I/O, allocation hay GC.
4. Lặp lại kịch bản để xác nhận hiện tượng có thể tái tạo.
5. Thay đổi một yếu tố kỹ thuật mỗi lần và đo lại.

Nếu cần tái hiện dữ liệu thật, dùng bản sao đã loại bỏ token, credential, thông tin cá nhân và dữ liệu khách hàng. Không đưa secret production vào file benchmark, command line, log hoặc repository.

Một vấn đề chỉ xuất hiện trong giờ cao điểm có thể do cạnh tranh tài nguyên hoặc phân bố request, không phải do một method đơn lẻ. Đừng rút gọn workload đến mức loại bỏ nguyên nhân cần tìm.

## 14. Những thay đổi hiệu năng cần xét khi đo trên JDK 26

Khi so sánh JDK 25 với JDK 26, hãy ghi nhận các thay đổi của runtime có thể ảnh hưởng kết quả ngay cả khi code ứng dụng không đổi:

### G1 giảm đồng bộ — JEP 522

JDK 26 cải thiện G1 bằng cách giảm đồng bộ giữa application threads và GC refinement threads. Mục tiêu là tăng throughput và giảm overhead write barrier, đặc biệt với workload cập nhật nhiều object reference. Đây là thay đổi đã hoàn tất, không phải preview và không cần cờ bật riêng.

Khi benchmark:

- Xác nhận cả hai JDK thực sự dùng G1 nếu mục tiêu là đo G1.
- Giữ heap và workload tương đương trong phép thử kiểm soát.
- Ghi throughput, CPU GC, tổng pause và request p99; không chỉ nhìn pause.
- Chọn dữ liệu có reference mutation đại diện cho ứng dụng; workload chỉ xử lý primitive có thể không thể hiện lợi ích.

### G1 `GCTimeRatio` mặc định — 12 sang 24

JDK 26 đặt mặc định `-XX:GCTimeRatio=24` cho G1. Theo công thức `1 / (1 + GCTimeRatio)`, đây là mục tiêu khoảng 4% thời gian dành cho GC trong cơ chế điều chỉnh heap. Đây là mục tiêu heuristic, không phải giới hạn cứng bảo đảm GC luôn tiêu thụ tối đa 4% CPU.

JDK trước đó thường dùng `12`, tương ứng khoảng 7,7%. Nếu muốn cô lập tác động JEP 522, có thể chạy một lượt kiểm soát với cùng `GCTimeRatio` trên hai JDK; sau đó chạy thêm lượt với default để phản ánh hành vi nâng cấp thực tế.

### AOT object caching — JEP 516

JDK 26 mở rộng AOT object caching để hoạt động với mọi garbage collector, gồm cả ZGC. Cải tiến này nhắm tới startup và warm-up bằng cách nạp cached Java objects theo cách trung lập với GC. Khi đo startup, phải ghi rõ AOT cache có được tạo và sử dụng hay không. Không so một lượt có cache với một lượt không cache rồi quy toàn bộ khác biệt cho JIT hoặc GC.

### Initial heap và các cờ cũ

JDK 26 bỏ default value trước đây của `InitialRAMPercentage`; nếu không chỉ định initial heap, JVM khởi tạo ở mức heap tối thiểu có thể. Vì vậy, cold startup và quá trình mở rộng heap có thể khác so với JDK cũ nếu ứng dụng dựa vào default. Ghi rõ `-Xms`, `-Xmx` và giá trị flag thực tế trong baseline.

`AggressiveHeap` và `MaxRAM` được đánh dấu deprecated trong JDK 26. Không dùng chúng như shortcut tuning mới. Khi cần kiểm soát heap, ưu tiên cấu hình rõ `-Xms`/`-Xmx` và đo trong giới hạn memory thực của container.

Các thay đổi trên là hành vi của runtime JDK 26. Không cần bật `--enable-preview` để sử dụng JEP 522 hoặc JEP 516.

## 15. Mẫu phiếu baseline

Dùng mẫu sau cho mỗi phép đo. Có thể lưu vào hệ thống benchmark nội bộ cùng artifact và recording:

| Trường | Giá trị cần ghi |
|---|---|
| Tên benchmark / mục tiêu | Tên scenario và giả thuyết |
| Baseline commit / candidate commit | Git SHA và build ID |
| JDK vendor/build | Ví dụ vendor, `java -version`, update/build number |
| Runtime flags | `-Xms`, `-Xmx`, GC, agents, AOT cache và các cờ khác |
| Máy/OS/container | CPU model, OS/kernel, image digest, CPU quota, memory limit |
| Dependency | DB/cache/broker version, cấu hình và dataset |
| Workload | Request mix, arrival rate, concurrency, payload distribution |
| Warm-up | Cách xác định ổn định và thời lượng thực tế |
| Measurement | Số lần lặp, thời lượng, thứ tự chạy |
| Throughput | Giá trị và đơn vị |
| Latency | p50, p95, p99, max và số mẫu |
| Errors | Error rate, timeout, retry và dropped requests |
| Resource | CPU, throttling, RSS, heap, allocation, queue depth |
| GC | Collector, count, pause, CPU và GC logs |
| Diagnostics | JFR filename, GC log, timestamp, tool versions |
| Kết luận | Đạt/không đạt, mức thay đổi và yếu tố gây nhiễu |

Ví dụ kết quả minh họa:

| Metric | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| Throughput | 8.000 req/s | 8.600 req/s | +7,5% |
| p50 | 18 ms | 17 ms | Giảm 5,6% |
| p95 | 65 ms | 61 ms | Giảm 6,2% |
| p99 | 180 ms | 205 ms | Tăng 13,9% |
| Error rate | 0,02% | 0,03% | Tăng |
| CPU | 72% | 79% | Tăng |

Ví dụ này cho thấy throughput tăng nhưng p99 và CPU xấu đi. Không thể tuyên bố candidate tốt hơn nếu mục tiêu dịch vụ yêu cầu tail latency thấp và CPU headroom còn đủ. Hãy xác định trade-off có phù hợp SLO và chi phí vận hành không.

## 16. Các lỗi thường gặp khi thiết lập phép đo

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Đo một lần rồi kết luận | Kết quả bị nhiễu bởi JIT, GC hoặc host | Lặp lại, dùng fork và báo cáo phân bố |
| So sánh hai máy khác nhau | Không tách được tác động phần cứng | Dùng cùng máy hoặc bộ đối chứng phần cứng |
| Bỏ qua warm-up | Đo interpreter/JIT compilation cùng steady state | Tách startup, warm-up và steady state |
| Chỉ đo average latency | Che khuất tail latency | Ghi p50/p95/p99/max và số mẫu |
| Load generator tự giảm tốc khi server chậm | Có thể che queueing và coordinated omission | Dùng open-loop/arrival-rate khi kiểm tra tải cố định |
| Benchmark method bằng `System.nanoTime()` | Dễ bị tối ưu hóa JIT, timer và loop overhead | Dùng JMH với fork/warm-up/measurement |
| Chỉ đo CPU, không đo error rate | Throughput có thể tăng nhờ drop hoặc trả lỗi nhanh | Theo dõi success, error, timeout và retry |
| Bật profiler khác nhau giữa hai phiên bản | Overhead đo không đồng nhất | Dùng cùng cấu hình instrumentation hoặc đo overhead riêng |
| Bật JFR Heap Statistics khi đo latency | Có thể kích hoạt old GC ở đầu/cuối recording | Tắt Heap Statistics trong benchmark latency |
| Thay nhiều JVM flags cùng lúc | Không biết flag nào tạo khác biệt | Thay một nhóm có giả thuyết và đo riêng |
| So JDK 25/26 nhưng bỏ qua default mới | Quy kết nhầm thay đổi cấu hình thành regression | Ghi flags thực tế; có lượt kiểm soát cùng flags |
| Không lưu commit và dataset | Không thể tái lập kết quả | Lưu SHA, checksum, cấu hình và artifact |

## 17. Bài tập thực hành

Một dịch vụ Java xử lý request tìm kiếm và ghi đơn hàng. Nhóm muốn nâng runtime từ JDK 25 lên JDK 26 và kiểm tra liệu throughput có tăng mà tail latency không xấu đi.

**Yêu cầu:**

1. Viết giả thuyết, metric chính và điều kiện đạt trước khi chạy.
2. Mô tả request mix, payload distribution, dataset và mức tải normal/peak/stress.
3. Tạo baseline với cùng commit, container image, CPU/memory quota, dependency và JDK 25 build cụ thể.
4. Tách cold startup, warm-up và steady state; ghi rõ trạng thái AOT cache.
5. Thu throughput, p50/p95/p99, max, error rate, CPU, RSS, heap, allocation, GC và queue depth.
6. Dùng JFR để tìm CPU hot methods, lock wait, socket/file I/O hoặc allocation pressure.
7. Dùng JMH để benchmark một method xử lý chuỗi hoặc chuyển đổi dữ liệu; dùng fork, warm-up và measurement iterations.
8. Chạy candidate trên JDK 26 cùng điều kiện và lưu `VM.version`, `VM.command_line`, `VM.flags`.
9. Tạo một lượt kiểm soát với cùng `GCTimeRatio` và heap nếu muốn tách tác động của JEP 522 khỏi default mới.
10. Phân tích trường hợp throughput tăng nhưng p99 hoặc error rate xấu đi; đưa ra kết luận theo SLO.

**Kết quả mong đợi:**

- Có baseline đầy đủ để người khác chạy lại.
- Workload thể hiện request mix và phân bố dữ liệu thực tế.
- Cold start, warm-up và steady state được báo cáo riêng.
- Kết quả có nhiều lần lặp và thể hiện cả biến thiên.
- Microbenchmark dùng JMH, load test dùng harness phù hợp với traffic model.
- JFR và GC log được dùng để tìm nguyên nhân thay vì đoán cờ JVM.
- Khác biệt mặc định của JDK 26 được ghi nhận khi so sánh.
- Kết luận dựa trên throughput, tail latency, error rate và chi phí tài nguyên cùng lúc.

## Tài liệu tham khảo

- [JDK 26 Troubleshooting Guide — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): JFR, overhead, bottleneck, GC, lock và I/O diagnostics.
- [JDK 26 Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html): JFR/JMC, `jcmd`, runtime flags, thread dump và chẩn đoán JVM.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): hướng dẫn setup benchmark độc lập, Maven archetype và các lưu ý khi viết benchmark.
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples): ví dụ về benchmark state, dead-code elimination, constant folding, forks và warm-up.
- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522): thay đổi G1 trong JDK 26.
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): AOT object caching và tác động startup/warm-up trên các GC.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): thay đổi runtime, heap sizing, JEP 522, JEP 516 và các flag deprecated.
- [Garbage-First Garbage Collector Tuning — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): G1 ergonomics, `GCTimeRatio` và cách phân tích GC.
- [JDK Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html): continuous recording, profile recording và quản lý recording bằng `jcmd`.
