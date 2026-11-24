# CPU, memory, thời gian chạy và dung lượng lưu trữ tạm

Serverless function cho phép triển khai logic mà không phải tự quản lý máy chủ, nhưng mỗi lần gọi vẫn cần tài nguyên tính toán hữu hạn. Cấu hình CPU, memory, thời gian thực thi và dung lượng lưu trữ tạm ảnh hưởng trực tiếp tới khả năng xử lý, latency, độ ổn định và chi phí. Cấp quá ít tài nguyên có thể khiến function chậm, hết bộ nhớ hoặc timeout; cấp quá nhiều có thể làm tăng chi phí mà không cải thiện đáng kể kết quả.

Khi sizing một function, cần nhìn cả một invocation và toàn bộ execution environment. Một số nền tảng gắn CPU với mức memory được cấp; nền tảng khác cho chọn CPU riêng hoặc dùng các tier cấu hình. Concurrency có thể khiến nhiều request chia sẻ CPU và memory của cùng instance. Temporary storage thường tồn tại theo vòng đời instance và không phải nơi lưu dữ liệu bền vững. Các chi tiết này phụ thuộc nhà cung cấp, runtime và plan, vì vậy cần đo trong đúng môi trường triển khai.

## 1. Bốn tài nguyên cần sizing

| Tài nguyên | Vai trò | Khi thiếu | Khi cấp dư |
|---|---|---|---|
| CPU | Thực thi mã, serialize, mã hóa, nén, tính toán và xử lý dữ liệu | CPU-bound task chậm, queue tăng, timeout | Tốn chi phí hoặc giữ capacity không cần thiết |
| Memory | Chứa runtime, code, thư viện, object, buffer, cache và dữ liệu đang xử lý | OOM, process bị kết thúc, GC nhiều, paging nếu nền tảng cho phép | Chi phí tăng; có thể không cải thiện workload CPU/I/O-bound |
| Execution time | Giới hạn thời gian một invocation được phép chạy | Invocation bị timeout trước khi hoàn tất | Worker có thể giữ tài nguyên lâu và che giấu tác vụ không có giới hạn |
| Temporary storage | Lưu file trung gian, download, extract, scratch data | Hết dung lượng, lỗi ghi file hoặc không thể xử lý payload | Tăng chi phí và diện tích dữ liệu tạm cần bảo vệ |

Bốn yếu tố liên quan nhau. Tăng memory có thể đồng thời tăng CPU trên một số nền tảng; tăng concurrency có thể làm memory working set và CPU contention tăng; tăng temporary storage không làm tăng memory; tăng timeout không làm một thuật toán kém hiệu quả trở nên tốt hơn.

## 2. Hiểu tài nguyên theo invocation và execution environment

Một function thường được gọi là serverless vì nhà cung cấp quản lý máy chủ và tự cấp phát execution environment. Tuy nhiên, không nên giả định mỗi invocation luôn có một máy ảo riêng.

Có hai phạm vi cần phân biệt:

- **Invocation:** một lần chạy function để xử lý event hoặc request. Invocation có thời điểm bắt đầu, kết thúc, timeout và kết quả riêng.
- **Execution environment/instance:** môi trường runtime mà nền tảng khởi tạo để chạy function. Môi trường có thể được tái sử dụng cho các invocation sau hoặc bị thay thế khi scale, cập nhật hay idle.

Tùy nền tảng, một execution environment có thể xử lý một invocation tại một thời điểm hoặc hỗ trợ nhiều invocation đồng thời. CPU, memory và temporary storage có thể được tính ở cấp instance, function hoặc invocation theo mô hình riêng. Hãy xác minh concurrency semantics của runtime trước khi tính capacity.

Ví dụ, nếu một instance xử lý đồng thời bốn request và mỗi request cần thêm 150 MB working set, memory đỉnh có thể tăng khoảng 600 MB ngoài phần nền của runtime, thư viện và cache. Nếu runtime chỉ xử lý một invocation mỗi environment, nền tảng có thể mở thêm nhiều environment thay vì chia sẻ cùng memory. Cùng một cấu hình memory nhưng hành vi khi tăng concurrency có thể rất khác.

## 3. CPU: năng lực tính toán cho mỗi lần gọi

CPU quyết định tốc độ thực thi các lệnh. Workload thường được chia thành ba nhóm:

- **CPU-bound:** nén/giải nén, mã hóa, xử lý ảnh, chuyển đổi dữ liệu, tính toán hoặc parse payload lớn.
- **Memory-bound:** thao tác trên tập dữ liệu lớn, cấu trúc dữ liệu có working set rộng hoặc thuật toán phụ thuộc tốc độ truy cập memory.
- **I/O-bound:** chờ database, object storage, HTTP API, queue hoặc filesystem.

Tăng CPU thường giúp workload CPU-bound. Nó có thể ít tác dụng với workload đang chờ database hoặc API ngoài. Với I/O-bound task, connection reuse, giảm số round trip, batch request và tối ưu query có thể hiệu quả hơn tăng CPU.

### 3.1. CPU có thể được cấp theo memory hoặc cấu hình riêng

Các nền tảng serverless có mô hình phân bổ CPU khác nhau:

- Một số nền tảng tăng CPU share theo mức memory được cấu hình.
- Một số nền tảng cho chọn CPU và memory độc lập theo các tier hợp lệ.
- Một số nền tảng dùng CPU quota hoặc concurrency limit thay vì một số vCPU cố định cho mỗi invocation.
- Một số môi trường container/serverless có thể giới hạn CPU theo request/limit hoặc theo instance.

Vì vậy, không thể suy ra số vCPU chỉ từ memory nếu chưa biết dịch vụ và plan. Khi tăng memory, hãy đo CPU utilization, duration và throughput để xác định lợi ích thực tế.

### 3.2. CPU contention khi concurrency tăng

Khi nhiều invocation cùng chạy trên một instance, chúng có thể tranh CPU. Dấu hiệu:

- Duration tăng khi concurrency tăng dù payload không đổi.
- CPU utilization duy trì gần giới hạn.
- Queue hoặc số invocation chờ tăng.
- p95/p99 tăng mạnh hơn p50.
- Một request CPU-heavy làm các request khác chậm theo.

Giảm concurrency có thể cải thiện latency mỗi request nhưng làm tăng số instance. Tăng concurrency có thể tận dụng tài nguyên tốt hơn với workload I/O-bound nhưng gây contention với CPU-bound task. Hãy benchmark ở concurrency dự kiến, không chỉ chạy một invocation đơn lẻ.

## 4. Memory: tính đủ cho runtime và dữ liệu xử lý

Memory không chỉ chứa object nghiệp vụ. Một function còn cần vùng nhớ cho:

- Runtime và interpreter/VM.
- Code, package và shared library đã load.
- Framework, SDK và client connection.
- Heap, stack và native allocation.
- Buffer cho request, response và serialization.
- Cache trong process.
- Dữ liệu download hoặc xử lý trung gian nếu giữ trong RAM.
- Nhiều invocation đồng thời nếu runtime chia sẻ instance.

Một công thức sizing khái niệm:

\[
M_{required} \approx
M_{runtime} + M_{libraries} + M_{baseline}
+ (C \times M_{request}) + M_{buffer}
\]

Trong đó C là số invocation đồng thời trên cùng environment. Công thức này là ước lượng ban đầu; cần đo peak resident memory và overhead của runtime trong điều kiện thực tế.

### 4.1. Dấu hiệu memory không đủ

- Function bị OOM hoặc runtime kết thúc bất thường.
- Memory utilization tiến sát giới hạn trong thời gian dài.
- GC chạy thường xuyên hoặc pause tăng với runtime có garbage collector.
- Process phải giải phóng cache liên tục.
- Tải lớn hơn một ngưỡng khiến invocation thất bại dù CPU còn dư.
- File được đọc toàn bộ vào RAM thay vì stream theo khối.

Nếu có OOM, hãy xem log/runtime metric để xác định memory peak. Đừng chỉ tăng memory trước khi kiểm tra leak, giữ object quá lâu, payload không giới hạn hoặc đọc file toàn bộ vào bộ nhớ.

### 4.2. Heap và native memory

Với Java, .NET, Node.js hoặc runtime có VM, memory limit của function không đồng nghĩa heap tối đa. Native memory, thread stack, JIT code, direct buffer, TLS và thư viện native cũng tiêu thụ memory. Heap được cấu hình quá sát giới hạn instance có thể khiến process OOM dù heap chưa chạm mức tối đa.

Với Python, object overhead và bản sao dữ liệu khi parse/transform có thể làm memory cao hơn kích thước payload nhiều lần. Với Node.js, buffer và object graph lớn có thể giữ memory lâu hơn dự kiến. Đo resident memory và runtime metrics thay vì chỉ dựa vào kích thước input.

### 4.3. Giảm memory trước khi tăng tier

Các biện pháp thường có ích:

- Stream file và response thay vì đọc toàn bộ vào RAM.
- Xử lý dữ liệu theo chunk hoặc batch nhỏ.
- Tránh tạo nhiều bản sao của payload.
- Giải phóng reference tới object lớn sau khi dùng.
- Giới hạn kích thước request và số item mỗi batch.
- Giảm cache không cần thiết hoặc đặt TTL/size bound.
- Dùng cấu trúc dữ liệu phù hợp với thao tác.
- Đặt concurrency phù hợp với working set mỗi invocation.

Nếu workload thực sự cần memory lớn, tăng tier là hợp lý. Mục tiêu là cấp đủ cho peak hợp lệ với headroom, không dùng giới hạn tối đa làm mặc định.

## 5. Chọn memory và CPU bằng benchmark

Thay vì chọn theo cảm tính, chạy cùng workload ở một số mức cấu hình hợp lệ. Ghi lại:

- Memory được cấp.
- CPU share hoặc vCPU nếu nền tảng công bố.
- Invocation duration p50/p95/p99.
- Peak memory và OOM count.
- CPU utilization/throttling.
- Concurrency và số execution environment.
- Error/timeout rate.
- Cost per successful invocation hoặc cost per batch.

Ví dụ minh họa với một workload xử lý JSON và nén dữ liệu:

| Cấu hình memory | Duration trung vị | Peak memory | Kết quả |
|---:|---:|---:|---|
| 512 MB | 1.200 ms | 470 MB | Có nguy cơ chạm giới hạn khi payload lớn |
| 1 GB | 720 ms | 520 MB | Hoàn tất ổn định |
| 2 GB | 390 ms | 540 MB | Nhanh hơn, nhưng mức cải thiện bắt đầu giảm |
| 4 GB | 360 ms | 550 MB | Cải thiện ít so với chi phí tăng |

Số liệu chỉ mang tính minh họa. Nếu CPU tăng cùng memory, duration có thể giảm đáng kể dù peak memory không đổi. Cấu hình 2 GB có thể là điểm cân bằng; cấu hình 4 GB chỉ hợp lý nếu yêu cầu latency cần thêm mức cải thiện đó hoặc chi phí mỗi tác vụ vẫn tốt hơn.

### 5.1. Tính chi phí theo kết quả hữu ích

Với mô hình tính giá theo GB-second, ước lượng chi phí compute của một invocation:

\[
C_{compute} \approx M_{GB} \times T_{billed} \times R_{GB-second}
\]

Trong đó:

- M là memory được cấp đổi sang GB.
- T là thời gian tính phí theo quy tắc của nền tảng.
- R là đơn giá GB-second.

Một số nền tảng tính CPU riêng, có mức phí request, concurrency hoặc minimum billing duration; do đó công thức cần điều chỉnh theo billing model thực tế. Có thể bổ sung phí temporary storage vượt mức miễn phí và các dịch vụ phụ trợ.

Chi phí trên một triệu invocation thành công:

\[
C_{1M} =
\frac{C_{total}}
{N_{successful}}
\times 1{,}000{,}000
\]

Không dùng số invocation được gọi làm mẫu số nếu một phần request timeout hoặc thất bại. Với batch, có thể dùng cost per million records hoặc cost per valid job.

## 6. Thời gian chạy và timeout của function

Execution timeout là thời gian tối đa nền tảng cho phép một invocation chạy trước khi bị kết thúc hoặc đánh dấu thất bại. Giới hạn cụ thể phụ thuộc nhà cung cấp, loại function, runtime, plan và phiên bản dịch vụ.

Timeout nên được chọn dựa trên phân bố duration thực tế và SLO:

- p50 cho biết thời gian xử lý điển hình.
- p95/p99 cho thấy phần đuôi chậm.
- Max duration giúp phát hiện outlier nhưng dễ bị nhiễu.
- Timeout cần đủ thời gian cho tải hợp lệ và biến động ngắn.
- Timeout không nên dài vô hạn để che giấu dependency treo hoặc job không có giới hạn.

Ví dụ, nếu p99 bình thường là 4 giây và SLO cho phép xử lý trong 8 giây, có thể đặt deadline invocation cao hơn p99 một khoảng hợp lý để có buffer, sau đó đặt timeout riêng cho từng dependency nhỏ hơn deadline còn lại.

### 6.1. Deadline tổng và timeout dependency

Một invocation có thể thực hiện nhiều bước: đọc event, lấy secret, gọi API, truy vấn database, ghi object và gửi message. Nếu mỗi bước có timeout độc lập quá dài, tổng thời gian có thể vượt execution timeout.

Nên truyền deadline còn lại qua các tầng:

\[
T_{remaining} = T_{deadline} - T_{now}
\]

Mỗi dependency nhận timeout không vượt quá thời gian còn lại trừ phần dự phòng cho cleanup và response. Đặt connect timeout, read timeout, query timeout và retry budget riêng.

Khi gần hết deadline, dừng bắt đầu công việc mới, hủy request có thể hủy và ghi lại trạng thái. Không bắt đầu retry nếu không còn đủ thời gian để hoàn tất hữu ích.

### 6.2. Timeout và xử lý side effect

Nếu function bị timeout sau khi đã gửi request ghi dữ liệu hoặc thanh toán, client có thể không biết thao tác đã hoàn tất hay chưa. Retry có thể tạo giao dịch trùng.

Biện pháp:

- Dùng idempotency key cho thao tác có side effect.
- Ghi trạng thái job theo transaction hoặc outbox pattern phù hợp.
- Thiết kế retry có giới hạn và backoff.
- Phân biệt lỗi chắc chắn thất bại với kết quả không xác định.
- Có cơ chế kiểm tra trạng thái trước khi thử lại.

Timeout không bảo đảm mọi hoạt động downstream tự động bị hủy. Một request đã tới database hoặc service ngoài có thể tiếp tục xử lý dù function đã kết thúc.

## 7. Khi nào cần tách job dài thành nhiều bước?

Nếu công việc thường xuyên tiến sát timeout, hãy xem lại mô hình thực thi. Function phù hợp với tác vụ ngắn, có giới hạn và có thể kích hoạt theo event. Job dài hoặc cần nhiều bước có thể chuyển thành workflow hoặc worker container.

Các dấu hiệu nên tách:

- Duration p95/p99 gần giới hạn timeout.
- Cần checkpoint sau mỗi phần dữ liệu.
- Có thể mất nhiều phút để chờ dependency.
- Retry toàn bộ job gây tốn kém.
- Một invocation cần giữ memory hoặc file tạm rất lớn.
- Cần pause/resume hoặc phê duyệt giữa các bước.
- Job cần tiến trình chạy dài hoặc kết nối liên tục.

Một cách thiết kế là chia file lớn thành chunk, đưa từng chunk vào queue và xử lý độc lập. Workflow orchestration có thể điều phối trạng thái, retry, timeout và nhánh lỗi. Cần bảo đảm thứ tự, idempotency và xử lý kết quả một phần.

## 8. Temporary storage là gì?

Temporary storage là không gian lưu trữ cục bộ dành cho dữ liệu tạm trong execution environment. Tùy nền tảng, nó có thể được mount vào một đường dẫn như /tmp hoặc được cung cấp dưới dạng scratch disk.

Các use case thường gặp:

- Download file từ object storage trước khi xử lý.
- Giải nén archive.
- Tạo file trung gian cho thư viện xử lý ảnh/video.
- Lưu model hoặc package được cache trong environment.
- Ghi kết quả tạm trước khi upload lên object storage.
- Dùng SQLite hoặc file scratch trong phạm vi một lần xử lý nếu yêu cầu phù hợp.

Temporary storage không phải database hay object storage bền vững. Environment có thể bị thu hồi, thay thế hoặc chạy trên instance khác. Không được giả định file sẽ tồn tại ở invocation tiếp theo.

### 8.1. Phân biệt memory và temporary storage

| Thuộc tính | Memory | Temporary storage |
|---|---|---|
| Cách truy cập | Biến, object, buffer trong process | File qua filesystem/API |
| Tốc độ | Thường rất nhanh | Phụ thuộc loại storage và I/O |
| Dung lượng | Giới hạn bởi memory tier/instance | Giới hạn bởi ephemeral storage quota |
| Vòng đời | Theo process/environment và runtime | Theo vòng đời storage/environment |
| Chia sẻ | Trong phạm vi process/runtime theo mô hình concurrency | Có thể dùng chung giữa invocation trên cùng environment nếu nền tảng giữ environment, nhưng không được bảo đảm |
| Mục đích | Working set đang xử lý | File trung gian, scratch data, cache tạm |
| Độ bền | Không phải nơi lưu bền vững | Không phải nơi lưu bền vững |

Nếu file có thể tái tạo từ nguồn bền vững thì temporary storage phù hợp. Nếu cần giữ kết quả sau khi invocation kết thúc, hãy ghi vào object storage, database hoặc dịch vụ bền vững trước khi return thành công.

### 8.2. Vòng đời và tính tái sử dụng

Một số nền tảng giữ execution environment để phục vụ invocation tiếp theo. Khi đó, file trong temporary directory có thể còn tồn tại trong một lần gọi warm sau. Tuy nhiên:

- Nền tảng có thể xóa environment bất kỳ lúc nào theo lifecycle của dịch vụ.
- Invocation khác có thể chạy trên environment khác.
- Scale-out tạo thêm environment với filesystem riêng.
- Deploy phiên bản mới có thể tạo environment mới.
- Không có bảo đảm về thứ tự hoặc affinity giữa các invocation.

Do đó, temporary storage chỉ nên được dùng như cache tối ưu hiệu năng, không phải nguồn dữ liệu chuẩn.

## 9. Sizing temporary storage

Cần ước lượng dung lượng lớn nhất có thể đồng thời tồn tại trên filesystem.

Một công thức tham khảo:

\[
D_{required} \approx
D_{input} + D_{extracted} + D_{intermediate}
+ D_{output} + D_{cache} + D_{safety}
\]

Cần chú ý file nén có thể giải nén lớn hơn nhiều lần. Một file video có thể tạo nhiều segment tạm. Một pipeline xử lý ảnh có thể giữ cả input, ảnh đã decode, ảnh resize và output cùng lúc.

Ví dụ, function nhận archive 300 MB, giải nén thành 1,2 GB, tạo file trung gian 500 MB và output 250 MB. Nếu tất cả cùng tồn tại, nhu cầu có thể vượt 2 GB trước khi tính cache và headroom. Hãy dọn file trung gian sớm hoặc xử lý theo streaming/chunk để giảm peak disk usage.

### 9.1. Dung lượng được cấp và dung lượng sử dụng

Một số nền tảng cho chọn kích thước ephemeral storage; một số cung cấp mức cố định hoặc quota theo plan. Cần xác minh:

- Dung lượng mặc định và tối đa.
- Dung lượng có tính phí hay có phần miễn phí.
- Storage là disk hay memory-backed filesystem.
- Có được dùng chung giữa các invocation trên một instance không.
- IOPS/throughput có giới hạn không.
- Dữ liệu có được mã hóa và cách ly giữa tenant/environment ra sao.
- File có bị xóa khi instance kết thúc hay không.

Không suy ra temporary storage từ memory limit. Tăng memory không nhất thiết làm filesystem lớn hơn.

## 10. Quản lý file tạm an toàn

File tạm có thể chứa dữ liệu khách hàng, token hoặc nội dung nghiệp vụ. Cần áp dụng nguyên tắc:

- Dùng tên file duy nhất và thư mục riêng cho invocation.
- Không tin tên file hoặc path do client gửi; ngăn path traversal.
- Tạo file với quyền hạn chế.
- Không ghi secret hoặc credential vào file tạm nếu không cần.
- Xóa file khi hoàn tất hoặc trong cleanup path.
- Dùng quota và giới hạn kích thước input.
- Không dựa vào cleanup chỉ chạy khi function kết thúc bình thường; timeout/crash có thể bỏ qua cleanup.
- Không để file từ invocation trước bị đọc nhầm bởi invocation sau.
- Không đưa nội dung file nhạy cảm vào log.

Ví dụ Python dùng thư mục tạm riêng:

~~~python
from pathlib import Path
from tempfile import TemporaryDirectory

def handler(event, context):
    with TemporaryDirectory(prefix="job-") as temp_dir:
        workdir = Path(temp_dir)
        input_path = workdir / "input.bin"
        output_path = workdir / "output.bin"

        # Tải dữ liệu từ nguồn bền vững vào input_path.
        # Xử lý theo chunk để kiểm soát memory.
        # Ghi output_path rồi upload kết quả tới object storage.

        return {"status": "completed"}
~~~

Đây là ví dụ khung. Phần download, xử lý và upload cần có timeout, kiểm tra kích thước, retry có giới hạn và xử lý lỗi. Với file lớn, nên stream trực tiếp hoặc xử lý theo chunk thay vì đọc toàn bộ vào memory.

## 11. Kết hợp memory và temporary storage khi xử lý file lớn

Một pipeline xử lý file thường có các lựa chọn:

1. **Load toàn bộ vào memory:** đơn giản và nhanh với file nhỏ, nhưng peak memory có thể lớn hơn kích thước file do decode và bản sao.
2. **Dùng temporary file:** giảm áp lực RAM nhưng cần đủ disk và I/O.
3. **Streaming:** đọc/ghi từng chunk, giảm cả memory và dung lượng trung gian.
4. **Chia thành nhiều function/job:** phù hợp khi file lớn hoặc thời gian xử lý dài, nhưng cần quản lý orchestration và chi phí gọi.

Ví dụ, không nên đọc một file 500 MB vào RAM nếu thư viện tạo thêm hai bản sao. Peak memory có thể vượt 1 GB. Nếu thuật toán hỗ trợ streaming, chunk 8 MB hoặc 16 MB có thể làm working set nhỏ hơn nhiều. Kích thước chunk phải benchmark theo CPU, I/O và throughput thực tế.

## 12. Concurrency ảnh hưởng tới CPU và memory

Concurrency là số invocation có thể chạy đồng thời. Có thể có nhiều cấp:

- Concurrency toàn function.
- Concurrency toàn account/project/region.
- Concurrency trên một execution environment.
- Concurrency của runtime hoặc worker thread bên trong process.
- Concurrency của dependency như database connection hoặc HTTP pool.

Khi tăng concurrency, throughput có thể tăng tới khi CPU, memory, network hoặc dependency đạt giới hạn. Sau điểm đó, latency và lỗi thường tăng nhanh.

Một ước lượng memory:

\[
M_{peak} \approx M_{base} + C \times M_{per-invocation}
\]

Nếu mỗi invocation giữ 120 MB working set và environment có 5 invocation đồng thời, phần memory theo request có thể khoảng 600 MB ngoài baseline. Cần đo vì runtime có thể chia sẻ cache hoặc tạo bản sao payload.

Không nên đặt concurrency chỉ theo số request mong muốn. Hãy kiểm tra connection limit của database, rate limit API ngoài, file descriptor, socket và khả năng xử lý của downstream.

### 12.1. Giới hạn concurrency để bảo vệ dependency

Nếu database chỉ chịu được 200 connection cho workload này, không thể để hàng nghìn function đồng thời mở connection trực tiếp. Có thể cần:

- Reserved/maximum concurrency ở function.
- Connection pooling hoặc proxy quản lý kết nối.
- Queue để hấp thụ burst.
- Batch request hoặc gộp thao tác.
- Backpressure và retry có jitter.
- Giới hạn tốc độ gọi dependency.

Concurrency là một guardrail của cả hệ thống, không chỉ là cách tăng throughput của function.

## 13. Cold start, warm start và resource sizing

Cold start là thời gian nền tảng cần tạo execution environment mới, khởi tạo runtime, load code/dependency và thực hiện initialization trước khi xử lý invocation. Warm invocation có thể tái sử dụng environment đã sẵn sàng.

CPU và memory ảnh hưởng tới startup theo cách khác nhau tùy nền tảng:

- CPU nhiều hơn có thể rút ngắn giải nén package, load module hoặc JIT.
- Memory lớn hơn có thể kéo theo CPU share lớn hơn trên một số dịch vụ.
- Package lớn, nhiều dependency hoặc initialization nặng làm cold start tăng.
- Runtime có JIT hoặc framework nặng có thể cần warm-up.
- Provisioned/warm capacity có thể giảm cold start nhưng làm tăng chi phí giữ môi trường sẵn sàng.

Hãy đo riêng cold-start latency và warm invocation duration. Không dùng average chung vì nó có thể che khuất trải nghiệm của request đầu tiên sau scale-out.

### 13.1. Giảm cold start

- Giảm kích thước package và dependency không cần thiết.
- Tránh khởi tạo client hoặc đọc cấu hình lặp lại nếu có thể tái sử dụng an toàn.
- Dùng runtime phù hợp với workload và yêu cầu startup.
- Giảm công việc nặng ở giai đoạn initialization.
- Dùng provisioned/warm capacity khi SLO yêu cầu và chi phí được chấp nhận.
- Đo cold start sau deploy, scale-out và khi environment idle lâu.

Không nên giữ state nghiệp vụ hoặc credential lâu trong global variable chỉ để giảm startup mà không đánh giá rủi ro. Tái sử dụng connection/client cần xử lý connection stale, credential rotation và lỗi network.

## 14. Chi phí liên quan tới CPU, memory, runtime và temporary storage

Billing model serverless khác nhau giữa các nhà cung cấp và loại dịch vụ. Các thành phần có thể gồm:

- Số invocation/request.
- Memory allocation nhân với thời gian tính phí.
- CPU allocation hoặc vCPU-time.
- Provisioned concurrency hoặc warm instance.
- Temporary storage vượt mức được bao gồm.
- Network egress và NAT.
- Log ingestion, metrics, traces.
- Queue, workflow, database và object storage.
- Retry hoặc invocation thất bại nếu nền tảng vẫn tính phí thực thi.

Một mô hình chi phí tổng quát:

\[
C_{total} =
C_{requests} + C_{compute} + C_{temp-storage}
+ C_{network} + C_{observability} + C_{dependencies}
\]

Đừng chỉ tối ưu giá invocation. Một function rẻ nhưng tạo nhiều retry, gọi database quá mức hoặc ghi log khối lượng lớn có thể làm tổng chi phí tăng.

### 14.1. Memory cao hơn có thể rẻ hơn nếu chạy nhanh hơn

Nếu nền tảng tăng CPU theo memory, cấu hình memory cao hơn có thể làm invocation hoàn tất nhanh hơn. Ví dụ minh họa:

| Cấu hình | Memory | Duration | GB-second xấp xỉ |
|---|---:|---:|---:|
| A | 0,5 GB | 0,8 s | 0,40 |
| B | 1,0 GB | 0,4 s | 0,40 |
| C | 2,0 GB | 0,3 s | 0,60 |

A và B có cùng mức GB-second theo mô hình đơn giản, nhưng B hoàn tất nhanh hơn và có thể tăng throughput hoặc giảm timeout. C nhanh hơn một chút nhưng có mức GB-second cao hơn. Đây chưa phải chi phí thực tế: còn request charge, CPU pricing riêng, rounding, concurrency, ephemeral storage và dependency cost.

### 14.2. Chi phí do timeout và retry

Nếu function timeout sau khi đã tiêu thụ phần lớn thời gian cho một dependency không phản hồi, lần retry có thể lặp lại cùng chi phí. Giảm timeout đơn thuần có thể làm lỗi tăng nếu dependency bình thường có tail latency cao. Cần kết hợp:

- Timeout hợp lý theo p99 và deadline.
- Retry chỉ với lỗi tạm thời và thao tác an toàn.
- Exponential backoff và jitter.
- Idempotency.
- Circuit breaker hoặc queue khi dependency suy giảm.
- Quan sát cost per successful operation.

## 15. Ví dụ cấu hình khái niệm

Các field dưới đây là cấu hình minh họa để thể hiện ý định sizing, không phải manifest dùng trực tiếp cho một nhà cung cấp:

~~~yaml
function:
  name: image-resizer
  runtime: python
  memory: 2048Mi
  cpu: platform-defined-by-memory-tier
  timeout: 30s
  concurrency:
    max-per-function: 40
    per-instance: platform-default
  temporary-storage:
    size: 3Gi
    use: intermediate-image-files
  observability:
    log-level: info
    capture-duration: true
    capture-memory-peak: true
~~~

Khi chuyển sang cấu hình thật, ánh xạ các field sang service, plan và API cụ thể. Một số nền tảng không cho cấu hình CPU riêng; một số dùng đơn vị MB thay vì MiB; concurrency per-instance có thể được quản lý ở runtime hoặc host.

### 15.1. Cách đọc cấu hình

- Memory 2 GiB là giới hạn/định mức của môi trường theo mô hình nền tảng, không phải lượng ứng dụng luôn sử dụng.
- CPU được cấp theo quy tắc của nền tảng; cần kiểm tra CPU share thực tế.
- Timeout 30 giây là ví dụ, phải dựa trên latency và SLO.
- Concurrency max 40 là giới hạn toàn function trong ví dụ; không hàm ý một instance chạy 40 invocation cùng lúc.
- Temporary storage 3 GiB dành cho file trung gian, không dùng làm nơi lưu kết quả lâu dài.
- Observability cần đo duration, memory peak và lỗi mà không ghi dữ liệu nhạy cảm.

## 16. Quy trình sizing từ workload thực tế

Một quy trình thực hiện:

1. **Mô tả workload:** input size, request rate, burst, tỷ lệ CPU/I/O và dependency.
2. **Xác định SLO:** latency p95/p99, error rate, thời gian tối đa và throughput.
3. **Xác định platform limits:** memory tier, CPU model, timeout, concurrency, ephemeral storage và payload limit.
4. **Chọn baseline:** cấu hình đủ nhỏ để đo nhưng không gây OOM ngay với workload chuẩn.
5. **Chạy benchmark:** thay một biến mỗi lần, ví dụ memory hoặc concurrency.
6. **Đo tài nguyên:** CPU, peak memory, duration, cold start, temporary disk usage.
7. **Kiểm thử peak:** payload lớn, burst, concurrency cao và dependency chậm.
8. **Tính cost per success:** bao gồm invocation, compute, storage và dependency.
9. **Chọn headroom:** để chịu biến động input và tải.
10. **Pilot production:** theo dõi thực tế và điều chỉnh theo telemetry.
11. **Đặt guardrail:** concurrency, timeout, input size và quota.
12. **Benchmark lại:** khi runtime, library, code, region hoặc billing model thay đổi.

### 16.1. Ma trận thử nghiệm

| Lần chạy | Memory | Concurrency | Input | Mục tiêu |
|---|---:|---:|---|---|
| 1 | Thấp hợp lệ | 1 | P50 | Baseline |
| 2 | Trung bình | 1 | P50 | Đo ảnh hưởng memory/CPU |
| 3 | Cao hơn | 1 | P50 | Tìm diminishing returns |
| 4 | Cấu hình chọn | Mức dự kiến | P50 | Kiểm tra contention |
| 5 | Cấu hình chọn | Peak dự kiến | P95 input | Kiểm tra memory/disk peak |
| 6 | Cấu hình chọn | Burst | P95 input | Kiểm tra scale-out, cold start và dependency |

Chỉ thay một nhóm biến trong mỗi vòng để hiểu nguyên nhân thay đổi. Nếu thay memory, timeout, runtime và concurrency cùng lúc, sẽ khó xác định yếu tố nào cải thiện hoặc làm xấu kết quả.

## 17. Ví dụ: function xử lý ảnh

Một function nhận event chứa object key, tải ảnh từ object storage, resize và ghi ảnh kết quả trở lại storage.

Các tài nguyên cần xem xét:

- **CPU:** decode, resize, encode ảnh; CPU nhiều hơn có thể giảm thời gian xử lý.
- **Memory:** ảnh đã decode có thể lớn hơn file nén nhiều lần; nhiều ảnh đồng thời làm peak memory tăng.
- **Timeout:** bao gồm download, decode, transform và upload; cần dự phòng cho tail latency của storage.
- **Temporary storage:** file gốc và file kết quả nếu thư viện cần filesystem; có thể giảm bằng streaming.
- **Concurrency:** giới hạn để tránh quá nhiều download/encode đồng thời và bảo vệ object storage.
- **Idempotency:** retry cùng event không tạo kết quả sai hoặc ghi đè không kiểm soát.

Một flow tham khảo:

~~~mermaid
flowchart TD
    A[Object-created event] --> B[Validate key and size]
    B --> C[Download or stream input]
    C --> D[Decode and resize]
    D --> E[Encode output]
    E --> F[Upload result]
    F --> G[Record completion]
    G --> H[Return success]
    C --> X[Retry or dead-letter on failure]
    D --> X
    F --> X
~~~

Nếu ảnh lớn, function nên kiểm tra kích thước và định dạng trước khi decode. Có thể dùng temporary file hoặc streaming tùy thư viện. Nếu thời gian xử lý vượt giới hạn function, chia ảnh thành tác vụ nhỏ hoặc dùng worker container phù hợp hơn.

## 18. Runtime và kích thước package

Runtime ảnh hưởng đến startup, memory baseline, CPU behavior và tương thích thư viện.

- Runtime nhẹ hoặc binary native có thể khởi động nhanh, nhưng cần kiểm tra thư viện và portability.
- Runtime có VM/JIT có thể cần warm-up và memory baseline cao hơn.
- Package nhiều dependency làm tăng thời gian tải và initialization.
- Native extension cần tương thích hệ điều hành, kiến trúc CPU và ABI.
- Container image lớn có thể làm cold start hoặc image pull lâu hơn tùy nền tảng.

Không có runtime tốt nhất cho mọi workload. Benchmark cùng chức năng và cùng điều kiện; đừng đổi runtime cùng lúc với thuật toán hoặc dataset rồi quy toàn bộ cải thiện cho CPU/memory.

## 19. Giới hạn nền tảng cần kiểm tra

Trước khi deploy, tra cứu cấu hình hiện hành của nhà cung cấp và plan đang dùng. Các giới hạn có thể gồm:

- Memory tối thiểu/tối đa và các bước tăng hợp lệ.
- CPU share, vCPU hoặc CPU quota.
- Execution timeout tối đa.
- Temporary storage mặc định/tối đa và đơn giá.
- Payload/request/response size.
- Package hoặc image size.
- Số file descriptor, thread và process.
- Concurrency per function, account hoặc region.
- Số execution environment và quota scale-out.
- Network access, VPC attachment và cold-start overhead.
- Hạn mức log, deployment và số lần gọi.

Giới hạn có thể khác giữa generation của dịch vụ, region, plan và runtime. Không sao chép một con số từ ví dụ của nhà cung cấp khác hoặc từ cấu hình cũ mà chưa xác minh.

## 20. Giám sát sau triển khai

Theo dõi các metric để biết cấu hình có phù hợp với workload production:

| Metric | Câu hỏi cần trả lời |
|---|---|
| Invocation duration p50/p95/p99 | Có tiến sát timeout không? |
| Max/peak memory | Có gần memory limit không? |
| CPU utilization/throttling | Function có CPU-bound hoặc bị giới hạn không? |
| Timeout/error count | Lỗi tập trung ở payload, dependency hay resource limit? |
| Concurrent executions | Có vượt khả năng downstream không? |
| Cold start/init duration | Scale-out có làm latency tăng không? |
| Temporary storage used | Có gần đầy hoặc tăng bất thường không? |
| Retry/DLQ count | Có lỗi lặp hoặc poison event không? |
| Cost per successful invocation | Chi phí mỗi kết quả hữu ích có tăng không? |
| Dependency latency | Thời gian bị tiêu thụ ở function hay dịch vụ ngoài? |

Cảnh báo nên dựa trên xu hướng và SLO, không chỉ một ngưỡng CPU. Ví dụ, memory peak gần limit kèm OOM là tín hiệu mạnh; CPU cao trong vài giây khi burst có thể là bình thường nếu latency vẫn đạt.

## 21. Checklist chọn CPU, memory, timeout và temporary storage

- [ ] Đã phân loại workload CPU-bound, memory-bound hay I/O-bound.
- [ ] Đã xác minh CPU được cấp theo memory hay cấu hình riêng.
- [ ] Đã đo runtime baseline, peak memory và working set theo request.
- [ ] Đã tính ảnh hưởng concurrency lên CPU và memory.
- [ ] Đã kiểm tra OOM, GC, buffer và memory leak.
- [ ] Đã đo p50/p95/p99 duration và cold-start latency.
- [ ] Timeout invocation và timeout dependency phù hợp với deadline tổng.
- [ ] Retry có giới hạn, backoff, jitter và idempotency khi có side effect.
- [ ] Đã phân biệt memory với temporary filesystem.
- [ ] Đã tính input, extracted, intermediate, output và safety headroom cho disk.
- [ ] File tạm được tạo riêng, giới hạn kích thước và cleanup.
- [ ] Dữ liệu cần giữ được ghi vào storage bền vững trước khi trả success.
- [ ] Đã kiểm tra concurrency limit và khả năng chịu tải của dependency.
- [ ] Đã benchmark nhiều cấu hình với cùng workload và chỉ số correctness.
- [ ] Cost per successful operation bao gồm compute, request, storage và dependency.
- [ ] Đã xác minh giới hạn hiện hành theo provider, plan, region và runtime.
- [ ] Có dashboard/cảnh báo cho duration, memory, concurrency, temp storage và cost.
- [ ] Có phương án tách job dài thành workflow hoặc worker khi cần.

## 22. Kết luận

CPU quyết định năng lực thực thi; memory phải chứa runtime, thư viện và working set ở peak concurrency; execution timeout giới hạn thời gian mỗi invocation; temporary storage chứa file trung gian trong vòng đời environment. Các tài nguyên có quan hệ với nhau nhưng không thể thay thế lẫn nhau: tăng memory không nhất thiết tăng disk, tăng timeout không sửa dependency chậm và tăng CPU không giúp nhiều nếu function chủ yếu chờ I/O.

Hãy sizing dựa trên workload thực tế, đo duration và peak resource ở nhiều mức concurrency, kiểm tra cold start, tính cost per successful operation và giữ headroom phù hợp. Temporary storage chỉ là scratch space; dữ liệu cần bền vững phải được ghi ra dịch vụ lưu trữ thích hợp. Khi giới hạn, timeout, cleanup và observability được thiết kế rõ ràng, serverless function có thể xử lý ổn định với mức tài nguyên và chi phí phù hợp.
