# So sánh kiến trúc CPU và lựa chọn runtime bằng benchmark

## 1. Vì sao phải benchmark CPU architecture và runtime?

Một Java function có thể chạy trên nhiều kiến trúc CPU và runtime khác nhau. Cùng một mã nguồn có thể được triển khai trên `x86_64` hoặc `arm64`; cùng một workload Java có thể dùng managed Java runtime, custom runtime hoặc native executable. Những lựa chọn này ảnh hưởng đến thời gian khởi tạo, thời gian xử lý, mức dùng bộ nhớ, khả năng tương thích thư viện và chi phí.

Không có kiến trúc hoặc runtime tốt nhất cho mọi function. Một API chủ yếu chờ database có thể gần như không thay đổi khi chuyển CPU; một function mã hóa, nén hoặc xử lý ảnh có thể hưởng lợi rõ rệt từ tập lệnh CPU và cache khác. Một ứng dụng Spring khởi tạo nhiều bean có thể bị chi phối bởi cold start; một worker xử lý batch dài có thể được quyết định bởi throughput ổn định sau khi JVM đã warm.

Benchmark giúp trả lời bằng số liệu thực tế:

- `arm64` có cải thiện latency hoặc giá trên mỗi request so với `x86_64` không?
- Memory nào cân bằng tốt giữa CPU được cấp, duration và chi phí?
- Java managed runtime nào phù hợp với dependency và thời hạn hỗ trợ?
- Native Image có giảm startup đủ nhiều để bù chi phí build và giới hạn tương thích không?
- Cold start, warm invocation, throughput và p95/p99 thay đổi ra sao?
- Lựa chọn nào đáp ứng SLO khi tải tăng và có thể rollback an toàn?

Trong module CLOUD_SERVERLESS, lựa chọn CPU/runtime cần được đánh giá cùng trigger, concurrency, memory, timeout, dependency, network và mô hình chi phí của FaaS. Không kết luận từ một lần chạy hoặc chỉ nhìn thời gian trung bình.

## 2. Hai trục lựa chọn độc lập: CPU architecture và runtime

CPU architecture xác định tập lệnh và loại processor mà function sử dụng. Runtime xác định cách hệ thống khởi chạy chương trình, nhận event và gọi handler. Hai quyết định liên quan nhưng không phải một.

| Trục | Lựa chọn thường gặp | Câu hỏi chính |
|---|---|---|
| CPU architecture | `x86_64`, `arm64` | Code và native dependency có tương thích? Workload chạy nhanh/kinh tế hơn trên kiến trúc nào? |
| Java runtime | Managed Java 17/21/25, custom runtime, Native Image | Cần tính năng JVM nào? Startup, compatibility và vận hành ra sao? |
| Deployment format | ZIP/JAR, container image | Artifact, native library, image size và quy trình build cần gì? |
| JVM execution mode | JIT, SnapStart, Provisioned Concurrency | Cần tối ưu cold start hay throughput ổn định? |

Ví dụ, có thể chạy Java 21 managed runtime trên cả `x86_64` và `arm64`. Cũng có thể đóng gói Java Native Image thành executable chạy trên OS-only runtime, nhưng binary phải được build cho đúng Linux architecture đích.

AWS Lambda hỗ trợ `x86_64` và `arm64` (AWS Graviton) cho các managed runtimes hiện hành. Tính sẵn có của `arm64` phụ thuộc Region; cần xác minh trước khi triển khai. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

## 3. So sánh x86_64 và arm64 trên AWS Lambda

### x86_64

`x86_64` là kiến trúc 64-bit thuộc họ x86. Đây thường là lựa chọn tương thích rộng với các thư viện native, agent, extension và binary lâu đời. Nếu ứng dụng phụ thuộc thư viện chỉ phát hành artifact x86, `x86_64` có thể là lựa chọn thực tế nhất cho đến khi có bản ARM64 tương ứng.

### arm64 và AWS Graviton

`arm64` là kiến trúc AArch64 chạy trên processor AWS Graviton. AWS nêu các lợi ích tiềm năng như cache L2 lớn hơn trên mỗi vCPU, tăng hiệu năng một số thao tác mã hóa và tập lệnh hữu ích cho một số workload tính toán. Graviton có thể cải thiện price/performance, nhưng kết quả phụ thuộc code, runtime và dependency. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

AWS quản lý phần cứng bên dưới và không cam kết function luôn chạy trên một thế hệ Graviton cụ thể. Ứng dụng cần tương thích với kiến trúc `arm64`, không được giả định có một chipset cố định.

| Tiêu chí | x86_64 | arm64 |
|---|---|---|
| Hệ processor | x86 64-bit | ARM 64-bit, AWS Graviton |
| Java bytecode thuần | Thường chạy không cần đổi mã | Thường chạy không cần đổi mã |
| JNI/native library | Cần binary x86_64 | Cần binary ARM64 |
| Lambda layers/extensions | Phải xác minh từng layer/extension | Phải có bản ARM64 tương thích |
| Container image | Build cho `linux/amd64` | Build cho `linux/arm64` |
| Tương thích dependency cũ | Thường rộng hơn | Có thể cần thay native dependency |
| Hiệu năng | Phụ thuộc workload | Có thể tốt hơn ở một số workload, cần đo |
| Chi phí | Theo bảng giá x86 của Region | Theo bảng giá Arm của Region; có thể có lợi thế |

Không thể suy ra `arm64` nhanh hơn chỉ từ benchmark CPU tổng hợp. Một function chờ I/O, bị giới hạn database hoặc chịu cold start do framework có thể không hưởng lợi nhiều khi đổi kiến trúc.

## 4. Memory cũng quyết định CPU trên Lambda

Trên AWS Lambda, người dùng cấu hình memory; CPU được phân bổ tỷ lệ thuận với memory. Memory có thể cấu hình từ 128 MB đến 10.240 MB. Ở mức 1.769 MB, function có mức CPU tương đương một vCPU; mức cao nhất có thể cung cấp tới sáu vCPU. CPU không phải một tham số độc lập để cấu hình riêng. <https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html>

Điều này có nghĩa tăng memory đôi khi làm function chạy nhanh hơn đáng kể dù heap thực tế không tăng tương ứng. Với workload CPU-bound, nhiều CPU hơn có thể giảm duration. Với workload I/O-bound, tăng CPU có thể không cải thiện nhiều vì function vẫn chờ network hoặc database.

Ví dụ, giả sử một function xử lý JSON mất 900 ms ở 512 MB và 330 ms ở 1.769 MB. Mức memory cao hơn có thể có chi phí mỗi invocation tương đương hoặc thấp hơn nếu thời gian giảm đủ nhiều. Phải tính theo giá GB-second và request thực tế của Region, không chỉ so memory.

Khi benchmark architecture, phải giữ memory giống nhau giữa hai kiến trúc trong mỗi cặp so sánh. Sau đó mới sweep memory để tìm cấu hình tối ưu. Nếu vừa đổi CPU architecture vừa đổi memory, không thể xác định yếu tố nào tạo ra khác biệt.

## 5. Phân loại workload trước khi benchmark

Trước khi chọn test matrix, xác định function bị giới hạn bởi tài nguyên nào.

| Loại workload | Dấu hiệu | Điều cần benchmark |
|---|---|---|
| CPU-bound | Tính toán, nén, mã hóa, xử lý ảnh, parse lớn; CPU bận trong thời gian handler | Architecture, memory/CPU, JIT/native code, throughput |
| Memory-bound | Heap hoặc native memory gần giới hạn, GC thường xuyên, OOM | Memory, allocation rate, GC, object lifetime |
| I/O-bound | Phần lớn thời gian chờ database, HTTP hoặc object storage | Connection pool, network, concurrency, retry; CPU architecture có thể ít ảnh hưởng |
| Cold-start-bound | `Init Duration` lớn, latency p99 cao khi environment mới | Runtime, framework startup, SnapStart, Native Image, Provisioned Concurrency |
| Batch-bound | Nhiều record mỗi invocation, duration dài, batch lớn | Throughput mỗi batch, memory, parallelism, partial failure |
| Burst-bound | Traffic tăng đột ngột, concurrency tăng nhanh | Scale-out latency, throttling, connection pressure và queue age |

Không dùng benchmark tổng hợp như phép nhân ma trận để đại diện cho mọi workload. Dùng payload, thư viện và dependency gần với production nhưng dữ liệu đã được tạo giả hoặc làm sạch.

## 6. Lựa chọn Java runtime

### Managed Java runtime

Managed runtime do Lambda duy trì runtime environment, bản vá và cập nhật nền tảng. Đây thường là lựa chọn đầu tiên cho Java function nếu không có yêu cầu đặc biệt về runtime hoặc binary.

Tại thời điểm viết bài, AWS Lambda liệt kê các managed runtime Java 25 (`java25`), Java 21 (`java21`), Java 17 trên Amazon Linux 2023 (`java17.al2023`) cùng một số runtime cũ hơn. Kiểm tra bảng runtime và ngày deprecation trước khi chọn; không dựa vào ví dụ cũ trong repository. <https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html>

| Runtime | Điểm cần cân nhắc |
|---|---|
| Java 25 | Phiên bản mới hơn, có AOT cache cho Runtime Interface Client trong managed runtime và thay đổi mặc định JVM; cần kiểm thử framework/dependency |
| Java 21 | Lựa chọn LTS hiện đại, managed runtime dựa trên Amazon Linux 2023 |
| Java 17 | Phù hợp hệ thống còn dependency/Framework cần Java 17; chọn runtime AL2023 khi bắt đầu mới |
| Java cũ | Chỉ duy trì khi có lý do tương thích; kiểm tra deprecation và kế hoạch nâng cấp |

Các runtime được Lambda hỗ trợ đều có thể chạy trên cả hai kiến trúc `x86_64` và `arm64`. Việc chọn Java version không tự quyết định CPU architecture. <https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html>

### Custom runtime

Custom runtime phù hợp khi cần tự kiểm soát bootstrap, runtime interface hoặc dùng ngôn ngữ/runtime chưa được Lambda cung cấp dưới dạng managed runtime. Nó làm tăng trách nhiệm build, patch, kiểm tra tương thích và vận hành. Không chọn custom runtime chỉ vì nghĩ rằng nó mặc định nhanh hơn managed Java.

### GraalVM Native Image

GraalVM Native Image biên dịch Java bytecode và reachable code thành executable native trong giai đoạn build. Trên Lambda, Java Native Image thường dùng OS-only runtime `provided.al2023` cùng Lambda Runtime Interface Client (RIC). Binary phải được build cho Linux và đúng architecture `x86_64` hoặc `arm64`. <https://docs.aws.amazon.com/lambda/latest/dg/runtimes-provided.html>

Native Image có thể giảm thời gian khởi động và footprint runtime, nhưng cần đánh giá:

- Reflection, dynamic proxy, classpath scanning và serialization cần metadata phù hợp.
- Một số thư viện dùng JNI hoặc native dependency cần build đúng architecture.
- Build native có thể lâu và phức tạp hơn JVM JAR.
- Runtime behavior, GC, peak throughput và memory cần benchmark riêng.
- Không phải mọi framework/plugin đều tương thích như nhau với AOT.
- OS-only runtime không có cùng trải nghiệm cập nhật managed Java runtime; nhóm phát triển phải kiểm soát runtime interface và binary.

Native Image không đồng nghĩa luôn nhanh hơn. Với function warm lâu hoặc xử lý CPU nặng, JVM JIT có thể đạt throughput cao hơn sau khi tối ưu. Với function chạy ngắn và cold start thường xuyên, Native Image có thể có lợi thế đáng kể.

## 7. JIT, SnapStart và Provisioned Concurrency

Đây là các cách xử lý startup và runtime behavior, không phải kiến trúc CPU.

### JVM JIT

JVM có thể diễn giải bytecode và biên dịch các đoạn code nóng thành native code. Tiered compilation cân bằng startup và hiệu năng lâu dài. Một function ngắn có thể kết thúc trước khi JIT đạt mức tối ưu cao; một worker warm lâu có thể hưởng lợi từ tối ưu hóa sau nhiều invocation.

Lambda có thiết lập JVM mặc định theo Java runtime. Theo tài liệu hiện hành, Java 17/21 mặc định dừng tiered compilation ở level 1; Java 25 cũng dùng level 1 mặc định, ngoại trừ khi dùng SnapStart hoặc Provisioned Concurrency thì JVM dùng default tiered compilation. Có thể tinh chỉnh bằng `JAVA_TOOL_OPTIONS`, nhưng cần đo trước khi thay đổi. <https://docs.aws.amazon.com/lambda/latest/dg/java-customization.html>

### SnapStart

SnapStart khởi tạo function khi publish version rồi lưu snapshot trạng thái memory/disk để tạo execution environment từ snapshot thay vì khởi động hoàn toàn từ đầu. Nó hỗ trợ Java 11 trở lên trong các managed runtimes tương ứng, chỉ áp dụng cho published versions và aliases trỏ đến version. Cần kiểm tra compatibility của random/unique values, temporary credentials và network connections được tạo trong initialization. <https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html>

### Provisioned Concurrency

Provisioned Concurrency giữ execution environments đã khởi tạo sẵn để giảm cold start latency cho workload có yêu cầu phản hồi nghiêm ngặt. Nó tạo chi phí duy trì capacity ngay cả khi không có request; cần so sánh với SnapStart và tải thực tế.

Không benchmark SnapStart bằng cách chỉ gọi `$LATEST` nếu cấu hình yêu cầu published version. Không so một function dùng Provisioned Concurrency với một function không dùng rồi kết luận khác biệt đến từ CPU architecture.

## 8. Kiểm tra tương thích trước khi đổi architecture

Java bytecode thuần thường chạy trên cả hai kiến trúc, nhưng package có thể chứa thành phần native. Lập inventory trước khi chuyển `x86_64` sang `arm64`:

- JNI/JNA library và native executable.
- Lambda layers.
- Lambda extensions, telemetry agents và security agents.
- Dependency đóng gói trong JAR, ZIP hoặc container.
- Compression, cryptography, image/video codecs và database drivers có native acceleration.
- Build/test/deploy tools và Docker base image.
- Script bootstrap có kiểm tra `uname -m` hoặc tải binary theo architecture.

AWS khuyến nghị kiểm tra từng third-party library/package có bản ARM64, đồng thời kiểm tra layer, extension và container image. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

Ví dụ kiểm tra architecture của binary trên Linux:

```bash
file native/libimagecodec.so
readelf -h native/libimagecodec.so | grep Machine
```

Kết quả `AArch64`/`ARM aarch64` tương ứng ARM64; `Advanced Micro Devices X86-64` tương ứng x86_64. Chạy lệnh trong build container tương ứng hoặc trên môi trường có toolchain phù hợp.

## 9. Build artifact đúng architecture

### JAR thuần Java

Nếu JAR chỉ chứa Java bytecode và resource portable, có thể dùng cùng artifact cho cả `x86_64` và `arm64`. Tuy nhiên, mọi native dependency được nhúng trong JAR/layer vẫn phải có binary phù hợp và được chọn đúng ở runtime.

### Container image

Build image đúng platform:

```bash
# x86_64 Lambda
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --load \
  -t orders-function:x86_64 .

# arm64 Lambda
docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  --load \
  -t orders-function:arm64 .
```

`--platform` phải khớp với architecture của Lambda function. AWS yêu cầu image tương thích với kiến trúc function; build trên máy ARM không tự bảo đảm image dùng đúng platform nếu không chỉ định. <https://docs.aws.amazon.com/lambda/latest/dg/java-image.html>

Trong ví dụ, `--load` đưa image một platform vào local Docker image store để chạy test. Khi build để triển khai, có thể thay bằng `--push` và tag image bằng URI của ECR repository tương ứng; repository/image cũng phải giữ đúng architecture đã chọn.

### GraalVM Native Image

Native Image phải được build trong môi trường Linux có toolchain tương thích với architecture đích. Không compile binary x86_64 rồi upload cho function ARM64 hoặc ngược lại. Nếu CI build trên một architecture khác, dùng cross-compilation/toolchain được hỗ trợ hoặc build container theo platform đích.

## 10. Xây dựng test matrix công bằng

Benchmark phải cô lập từng biến. Một matrix khởi đầu có thể như sau:

| Biến | Giá trị thử nghiệm |
|---|---|
| CPU architecture | `x86_64`, `arm64` |
| Runtime | Java 21 managed, Java 25 managed; Native Image nếu phù hợp |
| Memory | 512 MB, 1.024 MB, 1.769 MB, 3.008 MB |
| Startup mode | On-demand cold, warm, SnapStart hoặc Provisioned Concurrency nếu hỗ trợ |
| Payload | Nhỏ, trung bình, lớn theo production distribution |
| Concurrency | 1, mức thông thường, peak và burst |
| Region | Cùng một Region có hỗ trợ cả hai architecture |
| Dependency | Cùng version, endpoint, network path và dữ liệu test |

Không nhất thiết chạy toàn bộ tích Descartes của matrix ngay từ đầu. Một trình tự tiết kiệm hơn:

1. Chọn runtime/deployment format tương thích và benchmark baseline `x86_64`.
2. Sweep memory trên baseline để tìm vùng cấu hình có hiệu quả tốt.
3. Chạy `arm64` với cùng runtime, artifact, memory và workload.
4. Benchmark runtime variant (ví dụ managed JVM so với Native Image) trên architecture phù hợp.
5. Kiểm tra lại cấu hình tốt nhất dưới concurrency và payload production-like.
6. Chạy thử traffic canary nếu cần xác nhận hành vi thực tế.

Nếu thay nhiều biến cùng lúc, không thể biết nguyên nhân cải thiện hoặc suy giảm. Mỗi cặp benchmark phải chỉ thay một biến chính.

## 11. Chuẩn bị workload benchmark đại diện

Một benchmark hữu ích phải đại diện cho công việc thật. Chuẩn bị một tập scenario:

| Scenario | Ví dụ | Mục tiêu |
|---|---|---|
| Startup | Khởi tạo Spring context, load configuration và dependency injection | Đo cold start/init |
| CPU hot path | Parse/validate JSON, transform, hash hoặc compress | So sánh CPU architecture và memory |
| I/O path | Đọc DynamoDB, gọi HTTP service hoặc S3 | Xác định network/dependency bottleneck |
| Batch | Xử lý 10/100/500 event records | Đo throughput và memory theo batch |
| Large payload | Deserialize payload lớn, transform object graph | Đo allocation, GC và memory peak |
| Burst | Tăng concurrency nhanh | Đo scale-out, throttling và connection pressure |

Dữ liệu test cần có phân phối kích thước giống production. Một payload nhỏ cố định có thể khiến kết quả quá lạc quan. Dùng synthetic data hoặc dữ liệu đã loại bỏ thông tin nhạy cảm.

Giữ cố định:

- Cùng commit/source code và dependency versions.
- Cùng handler, event schema, payload và số record.
- Cùng Region, VPC/subnet, security group và endpoint.
- Cùng trạng thái cache/database và connection pool.
- Cùng concurrency profile, thời gian chạy và công cụ tạo tải.
- Cùng log level, tracing, extensions và telemetry configuration.
- Cùng timeout, retry policy và downstream service quotas.

Nếu thay architecture nhưng một function dùng layer/extension khác hoặc chạy trong subnet khác, kết quả không còn là so sánh CPU thuần.

## 12. Tách cold start và warm invocation

Cold start và warm invocation đo các chi phí khác nhau. Đừng gộp chúng thành một con số trung bình.

### Cold start

Cold start có thể gồm:

- Tạo execution environment.
- Tải package/container và khởi chạy runtime.
- Khởi tạo JVM, class loading và framework.
- Khởi tạo static field, dependency injection và client.
- VPC/network initialization nếu function dùng VPC.
- Restore snapshot nếu dùng SnapStart.

Trong log Lambda, `Init Duration` thường cho biết phần khởi tạo của execution environment. Với SnapStart, theo dõi thêm restore-related information và trạng thái function version. Đừng coi duration của handler là toàn bộ cold start.

### Warm invocation

Warm invocation đo handler sau khi environment đã sẵn sàng. Cần gọi nhiều lần trên environment warm, nhưng Lambda có thể tái sử dụng hoặc tạo environment mới tùy tải. Vì vậy, phải phân loại sample theo log/request metadata và chạy đủ số lần.

### Bảng đo riêng

| Nhóm | Chỉ số |
|---|---|
| Cold | Init Duration, restore duration nếu có, end-to-end first request latency |
| Warm | Handler Duration, p50/p95/p99, throughput |
| Memory | Max Memory Used, OOM, GC behavior nếu quan sát được |
| Platform | Throttles, ConcurrentExecutions, errors, queue age |
| Cost | GB-seconds, request charges, snapshot/provisioned capacity và telemetry cost |

Chạy cold-start test trên nhiều environment mới, không chỉ một invocation đầu tiên. Một sample đơn lẻ không đủ để mô tả p95/p99.

## 13. Đo các chỉ số hiệu năng

Các chỉ số cơ bản:

- **Duration:** thời gian function thực thi; xem phân phối thay vì chỉ average.
- **Billed Duration:** thời gian được tính phí theo quy tắc của Lambda.
- **Init Duration:** thời gian khởi tạo environment được ghi trong log report.
- **Max Memory Used:** mức memory tối đa quan sát trong invocation/environment.
- **Concurrency:** số execution environment đang xử lý đồng thời.
- **Throttles:** số invocation bị giới hạn do concurrency/quota.
- **Error rate:** tỷ lệ invocation lỗi hoặc timeout.
- **Throughput:** request/event xử lý trên giây hoặc trên một đơn vị chi phí.
- **Cost per operation:** chi phí ước tính cho một request/event hoàn tất thành công.

Không so sánh chỉ dựa trên `Duration` nếu hai function có tỷ lệ lỗi, số lần retry hoặc output khác nhau. Một function chạy nhanh nhưng thất bại nhiều hơn không phải lựa chọn tốt.

AWS Lambda ghi `Duration`, `Billed Duration`, `Memory Size` và `Max Memory Used` trong REPORT log. Memory setting ảnh hưởng CPU, do đó cần xem duration và memory cùng nhau. <https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html>

## 14. Thiết kế benchmark lặp lại và có ý nghĩa thống kê

Quy trình benchmark gợi ý:

1. Deploy một biến thể function với cấu hình đã khóa.
2. Chờ deployment hoàn tất và xác minh runtime/architecture thực tế.
3. Thực hiện warm-up riêng, không đưa warm-up vào tập đo warm latency.
4. Chạy cold-start samples trên environment mới hoặc phiên bản mới theo cách có kiểm soát.
5. Chạy warm workload với concurrency và payload cố định.
6. Thu thập ít nhất vài trăm invocation cho latency phân vị; số lượng cụ thể phụ thuộc traffic và độ ổn định.
7. Lặp lại các lượt benchmark ở nhiều thời điểm để giảm ảnh hưởng nhiễu nền tảng.
8. Tính p50, p90, p95, p99, throughput, error rate và cost.
9. Ghi lại runtime version, artifact hash, architecture, memory, Region và test profile.
10. So sánh kết quả với baseline và SLO trước khi kết luận.

Nếu benchmark có ít mẫu, p99 có thể không ổn định. Hãy ghi rõ số sample và confidence/độ biến động; không báo p99 từ vài chục invocation như một kết luận chắc chắn.

## 15. Ví dụ tạo hai Lambda function để so sánh architecture

Có thể tạo hai function riêng để tránh thay đổi cấu hình giữa các lượt chạy. Cả hai dùng cùng Java runtime, artifact, memory, timeout và environment variables; chỉ khác architecture và tên function.

Ví dụ AWS CLI (giả sử JAR đã build và execution role đã có):

```bash
aws lambda create-function \
  --function-name orders-java21-x86 \
  --runtime java21 \
  --architectures x86_64 \
  --handler com.example.orders.Handler::handleRequest \
  --role arn:aws:iam::123456789012:role/orders-lambda-role \
  --zip-file fileb://target/orders-function.jar \
  --memory-size 1769 \
  --timeout 30

aws lambda create-function \
  --function-name orders-java21-arm \
  --runtime java21 \
  --architectures arm64 \
  --handler com.example.orders.Handler::handleRequest \
  --role arn:aws:iam::123456789012:role/orders-lambda-role \
  --zip-file fileb://target/orders-function.jar \
  --memory-size 1769 \
  --timeout 30
```

Ví dụ này phù hợp khi JAR không chứa native dependency hoặc mọi native dependency tương thích với cả hai architecture. Nếu dùng layer hoặc extension, kiểm tra architecture compatibility của từng thành phần.

Đọc lại cấu hình:

```bash
aws lambda get-function-configuration \
  --function-name orders-java21-arm \
  --query '{Runtime:Runtime,Architectures:Architectures,Memory:MemorySize,Timeout:Timeout}'
```

Khi function đã tồn tại, có thể dùng `update-function-configuration` để thay memory/architecture, nhưng cần publish version mới và kiểm tra alias/version trước khi benchmark. Hai function riêng thường giúp lưu kết quả và rollback dễ hơn.

## 16. Ví dụ cấu hình architecture bằng AWS CDK Java

Trong CDK, architecture được chọn bằng `Architecture.X86_64` hoặc `Architecture.ARM_64`:

```java
import software.amazon.awscdk.Duration;
import software.amazon.awscdk.services.lambda.Architecture;
import software.amazon.awscdk.services.lambda.Code;
import software.amazon.awscdk.services.lambda.Function;
import software.amazon.awscdk.services.lambda.Runtime;

Function armFunction = Function.Builder.create(this, "OrdersArmFunction")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.ARM_64)
        .handler("com.example.orders.Handler::handleRequest")
        .code(Code.fromAsset("target/orders-function.jar"))
        .memorySize(1769)
        .timeout(Duration.seconds(30))
        .build();

Function x86Function = Function.Builder.create(this, "OrdersX86Function")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.X86_64)
        .handler("com.example.orders.Handler::handleRequest")
        .code(Code.fromAsset("target/orders-function.jar"))
        .memorySize(1769)
        .timeout(Duration.seconds(30))
        .build();
```

Hai function cần được gắn cùng dependency, environment, VPC, IAM policy, tracing và trigger nếu mục tiêu là so sánh công bằng. Trong stack production, không tạo hai function có side effect thật cùng xử lý một event; dùng test event hoặc traffic mirror an toàn.

## 17. Tối ưu memory bằng AWS Lambda Power Tuning

AWS Lambda Power Tuning dùng Step Functions để chạy function ở nhiều mức memory, thu thập duration và chi phí ước tính rồi hiển thị cấu hình có hiệu năng/chi phí phù hợp. Công cụ hữu ích cho memory tuning; architecture và runtime vẫn cần được so sánh như các biến riêng.

Quy trình gợi ý:

1. Chọn function và payload đại diện.
2. Chọn memory range, ví dụ 512–3.008 MB.
3. Chạy tuning trên môi trường test với downstream dependency ổn định.
4. Xem duration, cost và kết quả theo từng memory.
5. Lặp lại trên architecture khác nếu muốn so sánh.
6. Xác nhận cấu hình cuối bằng tải/concurrency gần production.

Không chạy power tuning trên function có side effect không idempotent hoặc gọi dịch vụ tính phí mà không kiểm soát. Công cụ có thể tạo nhiều invocation; cần dùng test data, sandbox và giới hạn tải.

Tham khảo: <https://github.com/alexcasalboni/aws-lambda-power-tuning>

## 18. Tính cost per successful operation

Để so sánh kinh tế, dùng chi phí trên mỗi request/event hoàn tất thành công thay vì chỉ duration.

Một ước lượng đơn giản:

```text
Compute cost per invocation
  ≈ configured memory in GB
    × billed duration in seconds
    × price per GB-second for architecture/Region

Total cost per successful operation
  ≈ (compute + request + downstream + telemetry + network cost)
    / successful operations
```

Phải tính cả retry, DLQ, API Gateway, SQS, database, NAT, log ingestion, tracing và các khoản phí liên quan. Với SnapStart, xem thêm snapshot caching/restore charges theo pricing hiện hành; với Provisioned Concurrency, tính capacity được giữ sẵn. Giá khác nhau theo Region, architecture và thời điểm; dùng AWS Lambda Pricing/AWS Pricing Calculator thay vì ghi một tỷ lệ tiết kiệm cố định trong code review.

Một architecture có duration thấp hơn nhưng giá GB-second khác hoặc tỷ lệ lỗi cao hơn có thể không rẻ hơn trên mỗi giao dịch thành công. Hãy so sánh cả latency SLO và unit economics.

## 19. Đo latency end-to-end, không chỉ thời gian handler

Một request serverless có thể đi qua API Gateway, Lambda, SQS, worker và database. Thời gian handler không bao gồm toàn bộ latency người dùng quan sát.

Nên đo:

- API Gateway integration latency và total latency.
- Lambda `Init Duration` và `Duration`.
- Queue `ApproximateAgeOfOldestMessage` và thời gian chờ trước khi worker nhận message.
- Database/client latency và connection acquisition.
- Retry/backoff và số lần delivery.
- End-to-end completion time từ lúc request được chấp nhận đến khi trạng thái nghiệp vụ hoàn tất.

Giữ trace/correlation ID nhất quán để phân biệt function chậm với queue backlog hoặc dependency chậm. Nếu chỉ đo handler, một kiến trúc có thể trông nhanh hơn nhưng người dùng vẫn chờ lâu vì queue hoặc database.

## 20. Đánh giá kết quả benchmark

Ví dụ bảng kết quả giả định để minh họa cách đọc (không phải số liệu AWS cam kết):

| Variant | p50 warm | p95 warm | p95 cold/init | Max memory | Cost/success |
|---|---:|---:|---:|---:|---:|
| Java 21 x86_64, 1.769 MB | 42 ms | 78 ms | 820 ms | 640 MB | 1,00× |
| Java 21 arm64, 1.769 MB | 39 ms | 71 ms | 790 ms | 625 MB | 0,86× |
| Java 25 arm64, 1.769 MB | 37 ms | 68 ms | 730 ms | 620 MB | 0,84× |
| Native Image arm64, 1.024 MB | 45 ms | 82 ms | 180 ms | 310 MB | 0,91× |

Trong ví dụ, Native Image có cold start thấp hơn nhưng warm p95 không tốt bằng Java 25 managed runtime. Nếu SLO tập trung cold start, Native Image có thể đáng thử; nếu workload warm và CPU-intensive, managed runtime có thể phù hợp hơn. Giá trị cost chỉ là hệ số giả định nhằm minh họa, không được dùng làm dự toán.

Đánh giá theo thứ tự:

1. Biến thể có đáp ứng SLO p95/p99 không?
2. Error rate, timeout và throttling có tăng không?
3. Cost per successful operation là bao nhiêu?
4. Cold start có ảnh hưởng đủ lớn đến user journey không?
5. Native dependency, build pipeline và vận hành có chấp nhận được không?
6. Kết quả có lặp lại ở nhiều lượt và dưới concurrency không?

## 21. Canary và chuyển đổi architecture

Sau benchmark trong sandbox, có thể triển khai canary để kiểm tra trên traffic thực. AWS khuyến nghị staged deployment và alias routing để phân phối một phần traffic giữa phiên bản x86 và ARM rồi so sánh metrics. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

Một quy trình an toàn:

1. Build và kiểm thử artifact tương thích với architecture đích.
2. Deploy version mới trong môi trường staging.
3. Chạy integration/load test và kiểm tra native dependency.
4. Publish version và cấu hình alias/traffic shifting phù hợp.
5. Bắt đầu với tỷ lệ canary nhỏ.
6. Theo dõi latency, error, throttles, memory và cost.
7. Tăng traffic nếu đạt ngưỡng; rollback nếu vi phạm SLO.
8. Sau khi ổn định, chuyển phần traffic còn lại và giữ phương án quay lại.

Nếu architecture là cấu hình cấp function/version trong cách triển khai đang dùng, kiểm tra khả năng alias routing giữa các version và xác minh mỗi version thực sự chạy đúng architecture. Không giả định hai alias/version khác nhau có thể trỏ đến cấu hình bất kỳ nếu deployment model không hỗ trợ.

## 22. Lỗi thường gặp khi benchmark

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Chỉ chạy một invocation | Bị chi phối bởi cold start hoặc nhiễu | Lặp nhiều lượt, tách cold và warm |
| Đổi architecture và memory cùng lúc | Không biết biến nào tạo khác biệt | Giữ một biến cố định trong từng cặp |
| Dùng payload quá nhỏ | Không đại diện workload thật | Dùng phân phối payload production-like |
| Không kiểm tra JNI/layer | Function có thể fail hoặc chạy fallback | Kiểm tra từng native dependency/extension |
| Build image sai platform | Binary không chạy trên Lambda | Dùng `linux/amd64` hoặc `linux/arm64` đúng đích |
| Chỉ xem average duration | Che khuất tail latency | So p50/p95/p99 và cold start riêng |
| Không tính retry/error | Cost per request bị đánh giá thấp | Tính cost per successful operation |
| Benchmark qua database biến động | Nhiễu che khác biệt CPU | Dùng dataset, endpoint và concurrency ổn định |
| Bỏ qua telemetry/extension | Production có overhead khác benchmark | Giữ cấu hình observability giống production |
| Kết luận ARM luôn nhanh/rẻ hơn | Hiệu năng phụ thuộc workload và dependency | Đo trên workload thật và xem bảng giá Region |
| Dùng Native Image mà không test reflection | Lỗi runtime hoặc thiếu class/resource | Cấu hình metadata và chạy integration test đầy đủ |
| Dùng SnapStart mà không xử lý uniqueness | State/secret/random value có thể bị dùng lại | Khởi tạo giá trị duy nhất sau restore và kiểm tra connection |

## 23. Quy trình chọn architecture và runtime

1. **Xác định SLO:** latency p95/p99, cold start, throughput, error rate và chi phí mục tiêu.
2. **Phân loại workload:** CPU-bound, I/O-bound, memory-bound, cold-start-bound hay burst-bound.
3. **Chọn baseline runtime:** ưu tiên managed Java runtime còn hỗ trợ nếu không có yêu cầu custom.
4. **Kiểm tra dependency:** JNI, layer, extension, container base image và native binary.
5. **Tạo baseline x86_64:** cố định runtime, memory, payload và network.
6. **Sweep memory:** tìm vùng duration/cost phù hợp.
7. **So sánh arm64:** giữ nguyên biến còn lại và chạy đủ warm/cold samples.
8. **So sánh runtime variant:** Java managed, SnapStart, Provisioned Concurrency hoặc Native Image khi có lý do.
9. **Đo end-to-end:** tính queue delay, downstream latency và retry.
10. **Tính unit economics:** cost per successful operation theo Region.
11. **Canary:** rollout từng bước và quan sát production metrics.
12. **Ghi quyết định:** lưu benchmark report, artifact hash, runtime, architecture và ngày đo để tái kiểm tra sau nâng cấp.

## 24. Checklist trước production

- [ ] Đã xác định SLO và workload đại diện.
- [ ] CPU architecture và runtime được benchmark như hai trục riêng.
- [ ] Region hỗ trợ architecture đã chọn.
- [ ] Mọi JNI/native library, layer, extension và container image tương thích.
- [ ] Native binary được build cho đúng Linux architecture.
- [ ] Memory sweep đã được thực hiện và CPU/memory bottleneck đã được phân loại.
- [ ] Cold start và warm invocation được đo riêng.
- [ ] Có p50/p95/p99, throughput, error rate và throttling.
- [ ] Test dùng cùng payload, dependency, Region, VPC và telemetry configuration.
- [ ] Cost per successful operation đã tính cả request, compute, retry, network và observability.
- [ ] SnapStart/Provisioned Concurrency được benchmark đúng published version và pricing.
- [ ] Native Image đã kiểm tra reflection, serialization, JNI và resource metadata.
- [ ] CI/CD có build platform đúng architecture và artifact hash được ghi lại.
- [ ] Canary/rollback plan đã được chuẩn bị.
- [ ] Runtime support/deprecation được kiểm tra lại trước release.

## Tài liệu AWS tham khảo

- [Selecting and configuring a Lambda instruction set architecture](https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html)
- [AWS Lambda Java runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html)
- [AWS Lambda runtime support and deprecation](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html)
- [Configure Lambda memory and CPU allocation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html)
- [Customize Java runtime startup behavior](https://docs.aws.amazon.com/lambda/latest/dg/java-customization.html)
- [Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [OS-only runtimes and Native AOT](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-provided.html)
- [Deploy Java Lambda functions with container images](https://docs.aws.amazon.com/lambda/latest/dg/java-image.html)
- [AWS Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning)

## Kết luận

Chọn CPU architecture và Java runtime bằng benchmark trên workload đại diện. `arm64`/Graviton có thể cải thiện price/performance, còn `x86_64` có lợi thế tương thích với một số native dependency; Java managed runtime thường đơn giản để vận hành, trong khi Native Image có thể giảm startup nhưng tăng yêu cầu build và compatibility. Trước khi kết luận, phải kiểm tra native library, giữ memory và workload cố định, tách cold start khỏi warm latency, đo p95/p99 và tính chi phí trên mỗi thao tác thành công. Canary cùng phương án rollback giúp chuyển đổi dựa trên bằng chứng và giữ SLO khi đưa lựa chọn mới vào production.
