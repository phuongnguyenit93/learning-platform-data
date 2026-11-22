# So sánh kết quả chức năng, tải, GC và mức dùng bộ nhớ khi nâng cấp lên Java 17

Khi nâng cấp ứng dụng lên Java 17, việc chương trình khởi động được và không có exception chưa đủ để kết luận nâng cấp thành công. Cần chứng minh rằng **kết quả nghiệp vụ vẫn đúng**, ứng dụng chịu được cùng mức tải, thời gian phản hồi nằm trong mục tiêu và mức dùng bộ nhớ/garbage collection (GC) không tạo ra rủi ro mới.

Cách so sánh đáng tin cậy là chạy bản hiện tại (baseline) và bản chạy trên Java 17 (candidate) trong điều kiện có thể đối chiếu: cùng workload, dữ liệu, cấu hình ứng dụng, giới hạn CPU/memory, dịch vụ phụ thuộc và cách đo. Sau đó phân tích riêng bốn nhóm:

1. **Chức năng:** đầu ra, side effect, lỗi và hành vi nghiệp vụ có tương đương không?
2. **Tải và hiệu năng:** throughput, latency, error rate, CPU và khả năng chịu tải thay đổi thế nào?
3. **GC:** tần suất, thời gian pause, allocation và mức độ ổn định của heap ra sao?
4. **Bộ nhớ:** heap, RSS, metaspace, direct memory, thread stack và tổng memory của container thay đổi thế nào?

Không nên gộp các nhóm thành một kết luận kiểu “bản Java 17 nhanh hơn”. Một bản có throughput cao hơn nhưng p99 latency xấu hơn, hoặc heap nhỏ hơn nhưng RSS tăng do native memory, cần được phân tích theo từng chỉ số.

## 1. Xác định mục tiêu và baseline trước khi nâng cấp

Trước khi chạy thử, ghi lại phiên bản đang dùng, phiên bản đích và điều kiện vận hành. Baseline là số liệu của ứng dụng hiện tại trong một môi trường đã biết; candidate là cùng ứng dụng sau khi chạy trên Java 17.

Thông tin tối thiểu:

| Nhóm | Cần ghi |
|---|---|
| Ứng dụng | Tên service, version, commit, artifact checksum |
| Java baseline | Vendor, runtime version, VM version, kiến trúc |
| Java candidate | JDK 17 vendor, patch/build, VM version, kiến trúc |
| Hệ điều hành | Distribution/build, kernel, kiến trúc CPU |
| Phần cứng | CPU model, số core/logical processor, RAM |
| Container | CPU quota, memory limit, cgroup version |
| JVM | Xms, Xmx, collector, JVM flags, system properties |
| Ứng dụng | Thread pool, connection pool, cache, timeout, feature flags |
| Dịch vụ phụ thuộc | Database, broker, HTTP service và version |
| Workload | Request mix, throughput mục tiêu, concurrency, payload |
| Thời gian | Warm-up, thời gian chạy ổn định, thời điểm lấy mẫu |

### 1.1. So sánh đúng hai runtime

Nếu mục tiêu là xác định tác động của việc đổi runtime, giữ nguyên source code và logic ứng dụng trong hai lượt chạy. Nếu ứng dụng có thể dùng cùng một artifact trên cả runtime cũ và Java 17, cách đó giúp cô lập tác động của JVM.

Nếu cần build lại ứng dụng để dùng API Java 17, ghi riêng thay đổi build và thay đổi runtime. Không nên gộp cả việc nâng dependency, sửa code, đổi cấu hình và đổi JDK vào một lần đo rồi quy toàn bộ chênh lệch cho Java 17.

Ghi rõ:

- JDK dùng để compile.
- JDK thực tế dùng để chạy.
- Artifact có giống nhau giữa hai lần chạy không.
- Dependency hoặc cấu hình nào thay đổi.
- Có bật/tắt agent, profiler hoặc instrumentation nào không.

### 1.2. Tách hai loại câu hỏi

Có hai phép so sánh hữu ích:

**So sánh có kiểm soát:** giữ cùng heap size, collector, JVM flags, workload và giới hạn tài nguyên để tìm ảnh hưởng của runtime mới. Đây là phép thử giúp cô lập nguyên nhân.

**So sánh cấu hình triển khai thực tế:** dùng cấu hình mà mỗi phiên bản sẽ thực sự chạy trong production. Cấu hình mặc định của các JDK có thể khác nhau; kết quả này phản ánh trải nghiệm vận hành nhưng không cô lập riêng tác động của runtime.

Nên thực hiện cả hai nếu cần đánh giá nâng cấp đầy đủ. Không diễn giải kết quả của phép thử thứ hai như một benchmark chỉ đo khác biệt mã nguồn JVM.

## 2. Chuẩn hóa môi trường đo

Một benchmark chỉ có ý nghĩa khi các yếu tố ngoài biến đang thử được kiểm soát.

### 2.1. Giữ cùng phần cứng và giới hạn tài nguyên

Tốt nhất chạy baseline và candidate trên cùng máy hoặc hai máy tương đương. Nếu dùng container, đặt cùng:

- CPU request/quota và CPU limit.
- Memory request/limit.
- Số replica và cách phân phối request.
- Storage class, mount và network path.
- Cấu hình autoscaling.
- Quyền và user chạy process.

Không so sánh một bản chạy trên máy 16 core với một bản chạy trên máy 8 core rồi chỉ chia CPU theo phần trăm. Ghi CPU model, quota và throttling để diễn giải kết quả.

### 2.2. Kiểm soát các dịch vụ phụ thuộc

Database, message broker, cache và HTTP service có thể làm sai lệch phép đo JVM. Cố gắng giữ cùng phiên bản/cấu hình dịch vụ, cùng dataset hoặc snapshot, cùng index/schema/cache state, cùng network path, cùng pool size, timeout và retry policy.

Nếu database tải cao ở lượt candidate nhưng nhàn ở lượt baseline, latency khác nhau không thể quy trực tiếp cho Java.

### 2.3. Chuẩn hóa thời gian và môi trường hệ thống

Ghi timezone, locale, charset, biến môi trường và system properties có ảnh hưởng tới ứng dụng.

Đặc biệt, Java 17 chưa áp dụng mặc định UTF-8 cho mọi môi trường theo thay đổi của JEP 400 (thay đổi này thuộc Java 18). Charset mặc định trong Java 17 vẫn có thể phụ thuộc nền tảng. Nếu ứng dụng xử lý file hoặc text, hãy dùng charset tường minh như `StandardCharsets.UTF_8` và dùng cùng dữ liệu đầu vào khi so sánh.

Không thay đổi đồng thời timezone, locale, charset, database collation hoặc dữ liệu thử nghiệm giữa hai lượt chạy.

## 3. So sánh kết quả chức năng

Phần chức năng trả lời câu hỏi: cùng một đầu vào và trạng thái ban đầu, bản chạy trên Java 17 có tạo ra kết quả và side effect đúng theo hợp đồng không?

Không chỉ so sánh log hoặc việc chương trình có chạy xong. Hãy so sánh kết quả mà người dùng và hệ thống phụ thuộc thực sự quan sát được.

### 3.1. Xác định contract cần giữ

Với mỗi luồng nghiệp vụ quan trọng, ghi đầu vào và điều kiện ban đầu, kết quả trả về/HTTP status, thay đổi database, event/message được phát ra, file/artifact được tạo, exception và cách xử lý lỗi, thứ tự hoặc tính nhất quán của side effect nếu hợp đồng yêu cầu.

Ví dụ:

| Scenario | Expected result | Cách xác nhận |
|---|---|---|
| Tạo hóa đơn hợp lệ | Trả hóa đơn và lưu đúng dữ liệu | So sánh response và database |
| Tạo hóa đơn trùng mã | Từ chối theo contract | So sánh status/error code và không có bản ghi thừa |
| Import file UTF-8 | Đọc đúng ký tự | So sánh dữ liệu sau import |
| Timeout database | Trả lỗi có kiểm soát | So sánh timeout, retry và transaction rollback |
| Gửi event | Event đúng schema và số lượng | Kiểm tra broker hoặc event store |

### 3.2. Dùng cùng dữ liệu và trạng thái ban đầu

Tạo fixture hoặc snapshot để hai runtime nhận cùng đầu vào. Với dữ liệu thay đổi theo thời gian, dùng clock giả lập hoặc cố định thời điểm kiểm thử nếu ứng dụng hỗ trợ.

Nếu đầu ra có trường không xác định như timestamp, UUID hoặc thứ tự collection không được contract bảo đảm, chuẩn hóa trường đó trước khi so sánh. Không loại bỏ những khác biệt có ý nghĩa nghiệp vụ chỉ để làm test pass.

### 3.3. So sánh theo nhiều lớp

- **Unit tests:** xác nhận quy tắc nghiệp vụ và xử lý biên.
- **Integration tests:** xác nhận database, file, network, serialization và transaction.
- **Contract tests:** xác nhận API, schema message và giao tiếp với dịch vụ phụ thuộc.
- **End-to-end tests:** xác nhận luồng người dùng từ đầu tới cuối.
- **Regression tests:** chạy lại các trường hợp từng gây lỗi trong runtime cũ.

Không dùng riêng unit test để kết luận nâng cấp runtime không làm thay đổi hành vi tích hợp.

### 3.4. Kiểm tra tương thích dữ liệu và serialization

Nếu ứng dụng lưu hoặc trao đổi Java serialized object, kiểm tra khả năng đọc dữ liệu được tạo bởi phiên bản trước và khả năng tương thích theo hợp đồng đang sử dụng. Java serialization có các quy tắc tương thích riêng; việc chương trình compile thành công không bảo đảm mọi dữ liệu cũ đều đọc được.

Với JSON, XML, CSV và file text, so sánh charset/byte encoding, quy tắc null/missing field, kiểu số/độ chính xác/rounding, ngày giờ/timezone/định dạng, thứ tự field nếu consumer phụ thuộc, schema version và default value.

Java 17 vẫn có charset mặc định phụ thuộc nền tảng. Dùng charset tường minh để tránh kết quả khác nhau giữa Linux, Windows và các môi trường triển khai.

### 3.5. Kiểm tra hành vi reflection và module access

Khi nâng cấp ứng dụng hoặc thư viện có reflection, kiểm tra các thao tác truy cập package nội bộ, private field/method và JDK internal API. Module encapsulation có thể khiến cách truy cập từng hoạt động trong runtime cũ không còn được phép hoặc cần cấu hình rõ ràng.

Ghi nhận lỗi như `IllegalAccessException`, `InaccessibleObjectException` và lỗi khởi tạo framework. Không xem việc thêm tùy chọn mở package rộng là một cách sửa mặc định; xác định đúng package và module cần mở.

### 3.6. Xác định tiêu chí pass/fail chức năng

Một scenario chỉ pass khi kết quả nghiệp vụ đúng, side effect đúng số lượng và nội dung, không có dữ liệu sai hoặc rò rỉ transaction, exception và error response đúng contract, không phát sinh regression ở luồng liên quan.

Lưu output so sánh theo scenario ID để có thể truy ngược tới đầu vào và môi trường của lần chạy.

## 4. So sánh tải và hiệu năng

Hiệu năng không phải một con số duy nhất. Cần nhìn throughput, latency, error rate, CPU, queue và mức bão hòa cùng lúc.

### 4.1. Các chỉ số chính

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Throughput | Số request/operation hoàn tất mỗi giây | Đánh giá năng lực xử lý |
| p50 latency | Thời gian phản hồi của median request | Mức trải nghiệm điển hình |
| p95 latency | 95% request hoàn tất trong thời gian này | Theo dõi phần đuôi |
| p99 latency | 99% request hoàn tất trong thời gian này | Phát hiện request rất chậm |
| Error rate | Tỷ lệ request lỗi/timeout | Bảo đảm throughput không tăng bằng cách bỏ lỗi |
| CPU utilization | Mức sử dụng CPU | Phát hiện CPU bottleneck |
| CPU time per operation | CPU tiêu thụ cho một thao tác thành công | So sánh hiệu quả tính toán |
| Queue depth | Số công việc đang chờ | Phát hiện backlog |
| Rejection rate | Tỷ lệ task bị từ chối | Phát hiện pool hoặc hệ thống bão hòa |

Không kết luận bản mới tốt hơn chỉ vì throughput tăng. Nếu error rate hoặc p99 tăng mạnh, ứng dụng có thể đang xử lý nhiều request hơn nhưng trải nghiệm và độ tin cậy kém hơn.

### 4.2. Dùng workload giống nhau

Ghi profile tải:

```text
Warm-up: 3 phút
Steady load: 15 phút
Burst: 60 giây
Request rate mục tiêu: 250 request/second
Concurrency: 200
Request mix:
  70% read
  20% update
  10% report
Payload:
  median 4 KB
  p95 80 KB
Metrics:
  throughput
  p50 / p95 / p99
  error rate
  CPU
  queue depth
```

Dùng cùng request mix, dữ liệu, thời gian warm-up và cách tạo tải cho baseline và candidate. Nếu workload có random, cố định seed hoặc ghi lại phân bố đầu vào.

### 4.3. Warm-up và JIT compilation

JVM có JIT compiler và tối ưu hóa code theo hành vi thực tế. Kết quả trong vài giây đầu sau startup có thể khác đáng kể so với trạng thái ổn định.

Một quy trình đo thường gồm:

1. Khởi động process mới.
2. Chạy warm-up để class loading, JIT và cache đạt trạng thái phù hợp.
3. Chạy steady load trong cửa sổ đã định.
4. Chạy burst nếu muốn đánh giá khả năng hấp thụ tải đột biến.
5. Ghi số liệu trong từng giai đoạn riêng.
6. Dừng process và lặp lại bằng JVM mới.

Không trộn dữ liệu warm-up với dữ liệu steady-state nếu mục tiêu là so sánh hiệu năng ổn định. Nếu startup time cũng là mục tiêu, đo riêng từ lúc process khởi động tới khi readiness thực sự đạt.

### 4.4. Đo nhiều lần và dùng phân phối

Chạy mỗi cấu hình qua nhiều lần độc lập. So sánh median và độ phân tán thay vì chọn lần chạy tốt nhất.

Ví dụ bảng kết quả:

| Metric | Baseline | Java 17 | Chênh lệch |
|---|---:|---:|---:|
| Throughput | 1.000 req/s | 1.080 req/s | +8% |
| p50 | 45 ms | 43 ms | -4,4% |
| p95 | 180 ms | 165 ms | -8,3% |
| p99 | 420 ms | 510 ms | +21,4% |
| Error rate | 0,2% | 0,3% | +0,1 điểm % |
| CPU/request | 1,8 ms | 1,7 ms | -5,6% |

Số liệu trên chỉ minh họa cách trình bày. Trong ví dụ, throughput và p95 tốt hơn nhưng p99 xấu hơn; không thể kết luận bản Java 17 tốt hơn ở mọi khía cạnh.

### 4.5. Tránh bottleneck từ load generator

Nếu máy tạo tải thiếu CPU, network hoặc connection, số throughput đo được sẽ bị giới hạn bởi load generator. Kiểm tra CPU và network của cả máy tạo tải.

Với hệ thống có latency thay đổi mạnh, chọn mô hình tải phù hợp. Closed-loop load generator thường gửi request tiếp theo sau khi request trước hoàn tất; khi server chậm, chính tốc độ tạo request cũng giảm. Open-loop hoặc rate-controlled load giúp duy trì tốc độ gửi mục tiêu, nhưng cần kiểm soát queue ở phía client và tránh tạo tải vượt khả năng môi trường.

### 4.6. Đo CPU theo công việc hoàn tất

CPU percentage một mình không đủ. Một bản có thể dùng CPU cao hơn vì xử lý nhiều request hơn.

Nên ghi CPU time tổng trong cửa sổ đo, số request thành công, CPU time trên mỗi request thành công, throughput tại cùng mức latency mục tiêu và CPU throttling nếu chạy container.

Nếu throughput tăng 10% và CPU tăng 5%, CPU trên mỗi request có thể đã giảm. Nếu throughput tăng nhưng error rate cũng tăng, cần tính cả request lỗi khi diễn giải.

## 5. Benchmark nhỏ và benchmark hệ thống

Hai loại benchmark trả lời câu hỏi khác nhau.

### 5.1. Microbenchmark với JMH

JMH phù hợp để đo một đoạn code nhỏ như thao tác collection, parser hoặc thuật toán. JMH quản lý warm-up, measurement iteration và fork để giảm một số sai lệch thường gặp.

Ví dụ khung benchmark:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringBenchmark {
    private final String input = "java-17-performance";

    @Benchmark
    public String uppercase() {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Cấu hình JMH nên có warm-up, measurement và nhiều fork:

```java
@org.openjdk.jmh.annotations.Warmup(
        iterations = 5,
        time = 1
)
@org.openjdk.jmh.annotations.Measurement(
        iterations = 5,
        time = 1
)
@org.openjdk.jmh.annotations.Fork(3)
```

Ví dụ chỉ minh họa annotation. Dự án cần khai báo JMH dependency và runner phù hợp. Không đo một vòng lặp bằng `System.nanoTime()` rồi xem kết quả đó là benchmark JVM đáng tin cậy; JIT, dead-code elimination và warm-up có thể làm sai kết quả.

### 5.2. Load test cho toàn hệ thống

JMH không thay thế load test cho service. Benchmark hệ thống cần đi qua network, serialization, thread pool, database, cache và các dịch vụ phụ thuộc như production.

Dùng công cụ load test mà nhóm đang vận hành, giữ cùng kịch bản và cấu hình giữa baseline và Java 17. Ghi rõ phiên bản công cụ tạo tải và số worker của nó.

### 5.3. Không dùng microbenchmark để suy ra hiệu năng production

Một method nhanh hơn 15% không có nghĩa API end-to-end nhanh hơn 15%. Method đó có thể chỉ chiếm 2% CPU tổng; phần lớn thời gian còn nằm ở database hoặc network.

Dùng microbenchmark để giải thích một code path đã được xác định là bottleneck. Dùng load test và production-like telemetry để kết luận hiệu năng hệ thống.

## 6. So sánh garbage collection (GC)

GC ảnh hưởng tới throughput, latency, CPU và bộ nhớ. Khi nâng cấp Java, cần quan sát GC thực tế của hai runtime thay vì chỉ so sánh tên collector hoặc một lần pause.

### 6.1. Các chỉ số GC cần ghi

| Chỉ số | Ý nghĩa |
|---|---|
| GC count | Số lần collection theo loại |
| GC pause duration | Thời gian ứng dụng bị dừng trong pause |
| Total pause time | Tổng thời gian pause trong cửa sổ đo |
| Max/percentile pause | Pause dài nhất hoặc phân vị pause |
| Allocation rate | Tốc độ tạo object |
| Heap before/after GC | Occupancy trước và sau collection |
| Promotion/old-gen growth | Object chuyển sang vùng sống lâu hoặc old generation tăng |
| Concurrent GC CPU | CPU dùng cho công việc GC chạy đồng thời |
| Full GC | Số lần và nguyên nhân nếu có |

Không chỉ nhìn số lần GC. Nhiều lần young collection ngắn có thể bình thường; ít lần collection nhưng pause rất dài vẫn có thể làm p99 latency vượt SLA.

### 6.2. Ghi GC log bằng unified logging

Java 17 dùng unified logging. Có thể bật:

```bash
-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m
```

Ý nghĩa:

- `gc*`: nhóm log liên quan GC.
- `safepoint`: thông tin safepoint.
- `time,uptime,level,tags`: timestamp, uptime, level và tag.
- `filecount=5`: giữ tối đa 5 file xoay vòng.
- `filesize=20m`: giới hạn kích thước mục tiêu mỗi file trước khi rotate.

Đặt option trong JVM arguments của service và xác nhận user chạy process có quyền ghi thư mục log. Dùng cùng định dạng log trong hai lượt chạy để dễ so sánh.

### 6.3. Kiểm tra collector thực tế

Ghi lại collector đang dùng và các cờ liên quan. Có thể lấy thông tin từ process:

```bash
jcmd 18420 VM.version
jcmd 18420 VM.flags
jcmd 18420 VM.flags -all
```

Hoặc kiểm tra đối số khởi chạy và log startup. Không giả định collector chỉ từ tên JDK.

Để cô lập tác động runtime, có thể chạy một lượt với cùng collector và heap configuration trên hai runtime nếu cả hai hỗ trợ cấu hình đó. Sau đó chạy thêm lượt với cấu hình production dự kiến. Đây là hai phép so sánh có mục tiêu khác nhau.

### 6.4. G1 và cấu hình mặc định

G1 là collector mặc định trên các máy server-class trong Java 17. Tuy nhiên, hãy xác nhận collector thực tế, vì ứng dụng có thể chỉ định collector khác hoặc chạy trên môi trường không thuộc nhóm đó.

Không nên áp dụng một bộ GC flags cũ chỉ vì nó từng có hiệu quả ở runtime trước. Trước hết hãy đo với cấu hình mặc định phù hợp của Java 17, sau đó chỉ thay đổi một tham số khi có bằng chứng.

### 6.5. Đọc GC log theo workload

Khi so sánh hai log, dùng cùng cửa sổ steady-state và ghi số young/mixed/old/full collections theo collector đang dùng, pause time tổng/median/p95/max, heap occupancy sau collection, allocation rate và xu hướng old-generation, thời gian concurrent cycle, safepoint ngoài GC nếu có, dấu hiệu allocation failure hoặc evacuation failure nếu log có.

Tên và loại event cụ thể phụ thuộc collector. Không áp một thuật ngữ của G1 cho collector khác; đọc tag và event theo log thực tế.

### 6.6. GC tốt hơn không chỉ có nghĩa pause ngắn hơn

Một collector có pause ngắn hơn nhưng dùng CPU concurrent nhiều hơn có thể giảm throughput ở cùng CPU quota. Một cấu hình giữ heap occupancy thấp hơn nhưng chạy GC thường xuyên hơn có thể tăng CPU.

Đánh giá GC cùng lúc với throughput, p95/p99 latency, CPU time, allocation rate, heap occupancy và tổng memory process/container.

### 6.7. Không ép GC để tạo số liệu đẹp

Không gọi `System.gc()` theo chu kỳ chỉ để so sánh heap sau GC. Việc ép collection làm thay đổi hành vi runtime và có thể tạo pause không giống workload thật.

Hãy đo trong workload ổn định và dùng GC log/JFR để quan sát các collection tự nhiên. Nếu cần heap dump hoặc class histogram, ghi rõ tác động và thời điểm thực hiện.

## 7. So sánh mức dùng bộ nhớ

Heap là phần bộ nhớ được quản lý bởi GC, nhưng tổng memory process lớn hơn heap. Vì vậy, “heap dùng ít hơn” không đủ để kết luận ứng dụng tiết kiệm RAM hơn.

### 7.1. Các vùng memory cần phân biệt

| Thành phần | Nội dung |
|---|---|
| Java heap | Object và array được cấp phát bởi Java heap allocator |
| Metaspace | Metadata của class |
| Code cache | Mã máy được JIT compiler tạo ra |
| Thread stacks | Stack của các thread |
| Direct buffers | Buffer ngoài heap, thường dùng cho I/O |
| Native/JNI memory | Allocation từ thư viện native và VM |
| Memory-mapped files | Vùng file được map vào address space |
| Shared libraries | Thư viện được map vào process |

Tổng resident memory (RSS/working set) còn phụ thuộc OS, page cache, shared pages và cách đo. Không cộng máy móc mọi số liệu vì một số vùng có thể chồng lấp hoặc được tính theo quy tắc khác nhau.

### 7.2. Heap: used, committed và max

Ba giá trị cần phân biệt:

- **Used:** dung lượng heap đang được sử dụng tại thời điểm đo.
- **Committed:** dung lượng heap JVM đã cam kết có thể dùng.
- **Max:** giới hạn heap tối đa mà JVM có thể sử dụng.

Có thể lấy snapshot bằng:

```bash
jcmd 18420 GC.heap_info
```

Ghi các số liệu theo thời gian, không chỉ lấy một lần. Heap committed có thể lớn hơn used và không nhất thiết giảm ngay sau collection.

### 7.3. Tổng memory của process

Linux:

```bash
ps -p 18420 -o pid,rss,vsz,%mem,%cpu,etime
cat /proc/18420/status
```

Windows PowerShell:

```powershell
Get-Process -Id 18420 |
    Select-Object Id, WorkingSet64, PrivateMemorySize64,
                  VirtualMemorySize64, Handles, Threads
```

Các trường của Windows và Linux không hoàn toàn tương đương. Khi so sánh hai runtime, nên dùng cùng OS và cùng phương pháp đo để giảm khác biệt về định nghĩa.

### 7.4. Metaspace và class loading

Nếu ứng dụng dùng nhiều class, proxy, dynamic class generation hoặc framework tạo class khi chạy, theo dõi metaspace và số class loaded/unloaded.

Có thể xem class loading qua JMX hoặc JFR. Nếu metaspace tăng liên tục qua nhiều chu kỳ workload và không ổn định, điều tra class loader retention hoặc việc tạo class không giới hạn.

Đừng kết luận có memory leak chỉ vì metaspace tăng trong giai đoạn warm-up; cần quan sát xu hướng sau khi hệ thống đạt trạng thái ổn định.

### 7.5. Direct memory và native memory

Ứng dụng dùng NIO, networking framework hoặc JNI có thể tiêu thụ native memory ngoài heap. Nếu RSS tăng nhưng heap không tăng tương ứng, xem xét direct buffer, thread stack, native allocation, code cache và memory-mapped files.

Native Memory Tracking (NMT) có thể cung cấp thông tin phân nhóm cho HotSpot JVM, nhưng phải bật từ lúc khởi động:

```bash
-XX:NativeMemoryTracking=summary
```

NMT có overhead và không theo dõi mọi allocation native của mọi thư viện bên thứ ba. Bật cùng cấu hình ở cả baseline và candidate nếu dùng để so sánh.

Sau khi khởi động với NMT:

```bash
jcmd 18420 VM.native_memory summary
```

Có thể tạo baseline NMT rồi so sánh mức thay đổi:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

Lệnh `baseline` ghi mốc để phép đo diff có ý nghĩa. Dùng cùng quy trình ở hai lượt chạy và ghi rõ NMT mode.

### 7.6. Thread count và stack memory

Số thread tăng có thể làm native memory tăng do stack và cấu trúc quản lý thread. Ghi tổng số thread của process, thread count theo pool, thread mới được tạo theo thời gian, trạng thái thread và stack size được cấu hình.

Có thể lấy thread dump:

```bash
jcmd 18420 Thread.print -l
```

Thread dump giúp tìm thread state và stack trace. Đối chiếu với metric thread pool để biết thread tăng do workload, pool configuration hay rò rỉ thread.

### 7.7. Container memory limit và OOM

Trong container, memory limit áp dụng cho tổng memory theo cơ chế cgroup, không chỉ Java heap. JVM có thể bị OOM kill dù heap chưa đạt Xmx.

Với cgroup v2, kiểm tra:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

Ghi cả heap max, RSS/process memory và container memory current. Nếu `memory.events` cho thấy OOM hoặc OOM kill, đối chiếu timestamp với JFR, GC log và process metrics.

## 8. Dùng JFR để liên kết CPU, GC và memory

Java Flight Recorder (JFR) ghi các sự kiện runtime theo thời gian. Nó giúp xác định thay đổi hiệu năng đến từ CPU sampling, allocation, GC, thread scheduling, lock contention hay I/O.

### 8.1. Bắt đầu recording trên JVM đang chạy

```bash
jcmd 18420 JFR.start name=java17-comparison settings=profile duration=15m filename=/var/tmp/java17-comparison.jfr
```

`profile` thu nhiều chi tiết hơn và phù hợp với cửa sổ điều tra ngắn. Với recording dài hơn, cân nhắc `default` để giảm mức chi tiết và dung lượng.

Kiểm tra recording:

```bash
jcmd 18420 JFR.check
```

Nếu đã có continuous recording, dump cửa sổ cần phân tích:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/incident-window.jfr
```

### 8.2. Bắt đầu recording từ JVM startup

Nếu sự cố xuất hiện sớm, thêm option:

```bash
-XX:StartFlightRecording=name=java17-startup,settings=profile,duration=15m,filename=/var/tmp/java17-startup.jfr
```

Đặt option vào JVM arguments của process. Ghi cùng kiểu recording trong baseline và candidate nếu mục tiêu là so sánh trực tiếp.

### 8.3. Xem summary và event

```bash
jfr summary /var/tmp/java17-comparison.jfr
```

Xem các event liên quan CPU, GC và allocation:

```bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.GarbageCollection,jdk.GCHeapSummary,jdk.ObjectAllocationSample /var/tmp/java17-comparison.jfr
```

Xem thread wait và I/O:

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /var/tmp/java17-comparison.jfr
```

Event có mặt hay không phụ thuộc recording settings và threshold. Không thấy event trong file không chứng minh sự kiện đó không xảy ra nếu event không được bật hoặc không vượt threshold.

### 8.4. Đọc JFR cùng application metrics

JFR không tự biết request nào là request thanh toán hay request báo cáo. Hãy dùng application log/metrics với timestamp hoặc correlation ID để đối chiếu:

- Latency tăng ở endpoint nào?
- Trong cùng thời điểm, CPU samples tập trung ở stack nào?
- Thread chờ monitor hoặc park có tăng không?
- GC pause hoặc allocation pressure có trùng thời điểm không?
- Socket/file I/O có duration bất thường không?
- Queue depth có tăng trước khi CPU hoặc GC thay đổi không?

JFR giải thích hoạt động JVM; application telemetry giải thích tác động nghiệp vụ. Cần cả hai để kết luận.

## 9. Quy trình chạy baseline và Java 17

Một quy trình có thể lặp lại:

### Bước 1 — Đóng băng test scenario

- Chọn commit/artifact.
- Chuẩn bị dataset giống nhau.
- Chọn request mix và load profile.
- Cố định các dịch vụ phụ thuộc hoặc ghi rõ biến động.
- Ghi expected result và ngưỡng pass/fail.

### Bước 2 — Ghi cấu hình runtime

Thu:

```bash
java -version
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

Ghi thêm CPU/memory limit, OS build và application configuration. Redact secret khỏi command line và system properties trước khi lưu.

### Bước 3 — Chạy chức năng

Chạy cùng bộ unit, integration, contract và end-to-end tests. Lưu output có scenario ID và so sánh database/event/file side effects.

Không chuyển sang benchmark hiệu năng nếu có regression chức năng nghiêm trọng chưa được giải thích.

### Bước 4 — Chạy workload có kiểm soát

- Khởi động process mới.
- Chạy warm-up.
- Chạy steady load.
- Chạy burst nếu cần.
- Thu throughput, p50/p95/p99, error rate, CPU và queue metrics.
- Lặp lại bằng process mới và ghi từng run riêng.

### Bước 5 — Thu GC và memory

Bật GC unified logging giống nhau trong hai lượt. Thu heap snapshot, process RSS/working set, thread count và container memory. Nếu cần NMT, bật từ đầu ở cả hai runtime.

### Bước 6 — Thu JFR

Ghi JFR trong cùng cửa sổ steady-state hoặc đúng khoảng thời gian có vấn đề. Lưu recording và summary. Ghi rõ settings và thời lượng.

### Bước 7 — Tổng hợp kết quả

So sánh theo từng nhóm: chức năng, throughput/latency, GC, heap và tổng memory. Ghi chênh lệch tuyệt đối và phần trăm, cùng số lần chạy và độ phân tán.

### Bước 8 — Tách giả thuyết và hành động

Ví dụ:

- p99 xấu hơn nhưng CPU/request giảm: xem queueing, lock, I/O hoặc GC pause.
- RSS tăng nhưng heap tương đương: xem native memory, direct buffer, thread stack hoặc shared mapping.
- GC pause giảm nhưng CPU tăng: xem concurrent GC work và allocation rate.
- Throughput tăng nhưng error rate tăng: xem saturation, timeout, retry và load generator.

Chỉ thay một yếu tố cấu hình trong mỗi lượt điều tra tiếp theo để xác định nguyên nhân.

## 10. Bảng kết quả so sánh đề xuất

Dùng một bảng chung cho từng run, nhưng giữ riêng các trường đo có đơn vị và cửa sổ thời gian rõ ràng.

| Nhóm | Metric | Baseline | Java 17 | Delta | Ghi chú |
|---|---|---:|---:|---:|---|
| Function | Passed scenarios |  |  |  |  |
| Function | Failed scenarios |  |  |  |  |
| Load | Throughput (req/s) |  |  |  |  |
| Load | p50 latency (ms) |  |  |  |  |
| Load | p95 latency (ms) |  |  |  |  |
| Load | p99 latency (ms) |  |  |  |  |
| Load | Error rate (%) |  |  |  |  |
| CPU | CPU time / successful request |  |  |  |  |
| GC | Total pause time (ms) |  |  |  |  |
| GC | Max pause (ms) |  |  |  |  |
| GC | GC count by type |  |  |  |  |
| GC | Allocation rate (MB/s) |  |  |  |  |
| Memory | Heap used after steady state (MB) |  |  |  |  |
| Memory | Heap committed/max (MB) |  |  |  |  |
| Memory | Process RSS/working set (MB) |  |  |  |  |
| Memory | Metaspace (MB) |  |  |  |  |
| Memory | Thread count |  |  |  |  |
| Container | Memory current/limit (MB) |  |  |  |  |
| Container | CPU throttling |  |  |  |  |

### 10.1. Cách tính delta

Với metric mà giá trị cao hơn là tốt hơn như throughput:

```text
delta (%) = (Java17 - Baseline) / Baseline × 100
```

Với metric mà giá trị thấp hơn là tốt hơn như latency hoặc CPU/request, cùng công thức có thể cho số âm khi Java 17 tốt hơn. Ghi rõ hướng tốt/xấu trong bảng để tránh hiểu nhầm.

Với error rate, ghi cả chênh lệch điểm phần trăm và chênh lệch tương đối. Ví dụ từ 0,2% lên 0,3% là tăng 0,1 điểm phần trăm, tương đương tăng 50% theo tỷ lệ tương đối.

### 10.2. Không chỉ báo cáo một con số tổng hợp

Không nên tạo một “performance score” duy nhất nếu nó che khuất trade-off. Báo cáo cần chỉ ra chỉ số nào cải thiện, chỉ số nào suy giảm, mức thay đổi có lặp lại qua nhiều run không, sự khác biệt có vượt ngưỡng SLA/SLO không và có khác biệt chức năng hoặc dữ liệu không.

## 11. Các tình huống thường gặp khi nâng cấp lên Java 17

### 11.1. Chức năng đúng nhưng p99 latency tăng

Kiểm tra JFR, GC pause, thread contention, pool wait và socket I/O. p50 có thể gần như không đổi trong khi một nhóm request bị chờ lâu.

### 11.2. Heap nhỏ hơn nhưng RSS lớn hơn

Heap có thể giảm trong khi direct buffer, thread stack, metaspace, code cache hoặc native allocation tăng. Đối chiếu `GC.heap_info`, OS RSS và NMT nếu đã bật.

### 11.3. GC pause ngắn hơn nhưng CPU tăng

Một số công việc GC có thể chạy đồng thời với ứng dụng. Pause giảm không đồng nghĩa tổng CPU giảm. So sánh CPU/request, throughput và tổng thời gian GC.

### 11.4. Throughput tăng nhưng error rate tăng

Kiểm tra timeout, retry, queue saturation, connection pool và load generator. Có thể ứng dụng đang nhận nhiều request hơn khả năng hoàn tất ổn định.

### 11.5. Chỉ lỗi trên một OS

Kiểm tra charset mặc định, filesystem semantics, case sensitivity, timezone, locale, native library và quyền file. Java 17 không khiến các khác biệt nền tảng tự biến mất.

### 11.6. Framework lỗi khi khởi tạo

Kiểm tra reflection vào package nội bộ và module encapsulation. Xác định thư viện nào cần truy cập, package nào cần mở và có bản thư viện tương thích Java 17 hay không.

### 11.7. Bộ nhớ tăng theo thời gian

So sánh heap occupancy sau các chu kỳ workload tương tự, số class loaded, metaspace, thread count, direct memory và RSS. Tăng memory trong warm-up chưa đủ chứng minh leak; cần quan sát xu hướng sau khi hệ thống đạt trạng thái ổn định.

## 12. Những sai lầm làm kết quả so sánh không đáng tin

- Chạy baseline và candidate trên phần cứng hoặc quota khác nhau mà không ghi nhận.
- Chỉ so sánh `java -version` trong shell, không kiểm tra runtime của process.
- Thay đồng thời JDK, dependency, JVM flags, heap và application config.
- Không chạy warm-up hoặc gộp warm-up với steady-state.
- Chỉ lấy một lần benchmark hoặc chọn lần chạy tốt nhất.
- Dùng average latency và bỏ qua p95/p99.
- So sánh throughput mà không xem error rate.
- So sánh heap mà không xem RSS, native memory và container limit.
- So sánh GC count mà không xem pause duration, CPU và allocation rate.
- Ép GC trong benchmark để tạo snapshot có vẻ dễ so sánh.
- Dùng JMH để kết luận hiệu năng của cả hệ thống.
- Bật profiler/recording khác nhau giữa hai runtime mà không ghi lại.
- Ghi log hoặc JFR có chứa dữ liệu nhạy cảm rồi chia sẻ không kiểm soát.
- Thay GC flags theo cảm tính trước khi có baseline.

## 13. Mẫu báo cáo nâng cấp Java 17

Có thể dùng cấu trúc sau cho mỗi đợt thử nghiệm:

```text
Upgrade comparison ID:
Application / version / commit:
Artifact checksum:

Baseline runtime:
  Vendor:
  JDK version:
  VM version:
  OS / architecture:

Candidate runtime:
  Vendor:
  JDK version:
  VM version:
  OS / architecture:

Environment:
  CPU model / quota:
  Memory / container limit:
  Database / broker / cache:
  JVM flags:
  Heap settings:
  GC collector:

Functional results:
  Scenarios passed:
  Scenarios failed:
  Data/API differences:
  Side-effect differences:

Load profile:
  Warm-up:
  Steady duration:
  Request mix:
  Throughput target:
  Concurrency:
  Payload distribution:

Performance:
  Throughput:
  p50 / p95 / p99:
  Error rate:
  CPU time per successful request:
  Queue / pool saturation:

GC:
  Collector:
  GC count by type:
  Total pause:
  Max / p95 pause:
  Allocation rate:
  Heap before/after collection:

Memory:
  Heap used / committed / max:
  Process RSS / working set:
  Metaspace:
  Direct/native memory:
  Thread count:
  Container memory current / limit:

Evidence:
  Test result files:
  Application metrics:
  GC logs:
  JFR recordings:
  Thread dumps:
  NMT output:
  Run timestamps (UTC):

Conclusion:
  Functional compatibility:
  Performance impact:
  GC impact:
  Memory impact:
  Known limitations:
  Follow-up experiments:
```

Kết luận nên dựa trên các ngưỡng đã thống nhất trước khi chạy. Ví dụ: tất cả scenario chức năng quan trọng phải pass; p95/p99 không vượt SLO; error rate không tăng quá ngưỡng cho phép; memory peak có headroom đủ so với container limit. Ngưỡng cụ thể phụ thuộc ứng dụng và cần được nhóm vận hành xác định.

## 14. Ghi nhớ

- So sánh Java 17 cần baseline rõ ràng và workload có thể lặp lại.
- Kiểm tra chức năng, side effect, serialization, charset, reflection và module access.
- Đo throughput cùng p50/p95/p99, error rate, CPU/request và queue depth.
- Warm-up JIT và cache trước khi đo steady-state; lặp lại bằng process mới.
- Dùng JMH cho microbenchmark và load test cho toàn hệ thống.
- Ghi GC log bằng unified logging; phân tích pause, allocation, heap occupancy và CPU cùng nhau.
- Heap không phải toàn bộ memory; theo dõi RSS, metaspace, direct/native memory, thread stack và container usage.
- Dùng JFR để liên kết CPU, GC, allocation, thread và I/O với timeline ứng dụng.
- NMT cần bật từ startup và có overhead; so sánh cùng cấu hình nếu sử dụng.
- Tách phép thử kiểm soát runtime khỏi phép thử cấu hình production thực tế.
- Không kết luận từ một metric hoặc một lần chạy; báo cáo cả cải thiện, suy giảm và giới hạn.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 — java launcher và VM options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Java SE 17 — jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Java SE 17 — jfr tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html).
- [Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/).
- [Java SE 17 — JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf).
- [Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html).
- [Java SE 17 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html).
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh).
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
- [JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331).
- [JEP 400 — UTF-8 by Default (Java 18)](https://openjdk.org/jeps/400).

