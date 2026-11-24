# Phụ thuộc giữa các job và điều phối workflow

Một quy trình xử lý nền thường gồm nhiều job có quan hệ với nhau. Job tải dữ liệu phải hoàn tất trước khi job làm sạch bắt đầu; các job xử lý từng phân vùng có thể chạy song song; job tổng hợp chỉ được chạy khi tất cả phân vùng đã xong; cuối cùng một bước kiểm tra mới quyết định có xuất bản kết quả hay không. Nếu chỉ lên lịch từng job độc lập, hệ thống dễ chạy sai thứ tự, xử lý dữ liệu chưa sẵn sàng hoặc bỏ sót bước khi một job thất bại.

**Phụ thuộc giữa các job (job dependency)** mô tả điều kiện để một job được phép bắt đầu hoặc được xem là hoàn tất. **Điều phối workflow (workflow orchestration)** quản lý thứ tự, trạng thái, điều kiện, retry, timeout, lịch chạy và kết quả của toàn bộ quy trình.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, workflow có thể chạy trên VM, container, Kubernetes Job, batch service hoặc serverless task. Thiết kế cần tách logic nghiệp vụ khỏi bộ điều phối, mô hình hóa phụ thuộc rõ ràng, kiểm soát concurrency và bảo đảm quy trình có thể tiếp tục hoặc phục hồi khi một worker, node hay dịch vụ gặp lỗi.

## 1. Job, task và workflow

Các thuật ngữ có thể khác nhau giữa nền tảng, nhưng thường có ý nghĩa:

- **Job:** một đơn vị công việc có mục tiêu hoàn thành rõ ràng, ví dụ nhập một tập dữ liệu hoặc tạo báo cáo ngày.
- **Task/step:** một bước nhỏ trong job hoặc workflow, thường có input, output và trạng thái riêng.
- **Worker:** tiến trình hoặc container thực thi job/task.
- **Queue:** nơi lưu yêu cầu công việc đang chờ worker nhận.
- **Workflow:** tập hợp job/task cùng quan hệ phụ thuộc và quy tắc điều phối.
- **Scheduler:** thành phần quyết định thời điểm hoặc thứ tự job được đưa vào thực thi.
- **Orchestrator:** thành phần quản lý trạng thái và điều phối các bước trong workflow.

Một job có thể chạy trên một VM, trong container, dưới dạng Kubernetes Job hoặc bằng một dịch vụ managed batch. Workflow không nên phụ thuộc vào một worker cụ thể; nó nên mô tả công việc cần làm và giao cho worker phù hợp thực thi.

### 1.1. Đặc điểm của một job tốt

Một job nên có:

- Định danh duy nhất cho lần chạy hoặc đơn vị dữ liệu.
- Input và output được xác định rõ.
- Điều kiện hoàn tất có thể kiểm tra.
- Timeout và giới hạn tài nguyên.
- Hành vi retry có kiểm soát.
- Cơ chế idempotency hoặc chống xử lý trùng.
- Log, metric và trạng thái đủ để điều tra.
- Cách hủy hoặc phục hồi khi tiến trình bị dừng.

Job nên xử lý một phạm vi dữ liệu có giới hạn. Job quá lớn khó retry và khó phục hồi; job quá nhỏ có thể tạo overhead điều phối, queue và network quá cao.

### 1.2. Workflow như một đồ thị phụ thuộc

Workflow thường được biểu diễn bằng đồ thị có hướng. Mỗi node là một job hoặc task; mỗi edge chỉ ra một bước cần hoàn tất hoặc đáp ứng điều kiện trước khi bước khác được chạy.

Ví dụ pipeline dữ liệu:

~~~mermaid
flowchart TD
    A["Tải dữ liệu"] --> B["Kiểm tra định dạng"]
    B --> C["Làm sạch dữ liệu"]
    C --> D1["Xử lý phân vùng A"]
    C --> D2["Xử lý phân vùng B"]
    C --> D3["Xử lý phân vùng C"]
    D1 --> E["Tổng hợp"]
    D2 --> E
    D3 --> E
    E --> F["Kiểm tra chất lượng"]
    F --> G["Xuất bản kết quả"]
~~~

Job tải dữ liệu và kiểm tra định dạng chạy tuần tự. Sau khi làm sạch hoàn tất, ba job phân vùng có thể chạy song song. Job tổng hợp là bước fan-in, chờ đủ kết quả từ các nhánh. Kết quả chỉ được xuất bản sau khi kiểm tra chất lượng đạt.

## 2. Các loại phụ thuộc giữa job

Phụ thuộc không chỉ là “job A chạy trước job B”. Cần mô tả rõ điều kiện nào cho phép job tiếp theo bắt đầu.

### 2.1. Phụ thuộc theo thứ tự hoàn tất

Job B chỉ được bắt đầu sau khi Job A kết thúc. Tùy workflow, “kết thúc” có thể gồm nhiều trạng thái:

- Chỉ chạy B khi A thành công.
- Chạy B sau khi A kết thúc dù thành công hay thất bại.
- Chỉ chạy B nếu A thất bại.
- Chạy B nếu A bị bỏ qua theo điều kiện đã định.

Ví dụ, bước dọn tài nguyên tạm cần chạy sau khi job xử lý kết thúc, kể cả job xử lý thất bại. Trong khi đó, bước xuất bản chỉ chạy nếu tất cả bước kiểm tra thành công.

### 2.2. Phụ thuộc dữ liệu

Job B cần output do Job A tạo ra. Điều kiện phụ thuộc nên xác minh cả sự tồn tại và tính hợp lệ của dữ liệu:

- File hoặc object đã được ghi hoàn tất.
- Manifest chứa đủ phân vùng.
- Schema và version tương thích.
- Checksum hoặc record count đạt yêu cầu.
- Dữ liệu đã commit và có thể đọc từ nơi tiêu thụ.

Chỉ kiểm tra file tồn tại có thể không đủ. Job A có thể tạo file rỗng, ghi dở hoặc tạo output không đúng phiên bản.

### 2.3. Phụ thuộc tài nguyên hoặc dịch vụ

Một job chỉ chạy khi tài nguyên cần thiết đã sẵn sàng:

- Database đã được cấp phát và chấp nhận kết nối.
- Volume đã được attach và mount.
- Container image đã được tải.
- Credential hoặc secret đã được cấp.
- GPU hoặc node pool phù hợp còn capacity.
- Rate limit của API bên ngoài cho phép tiếp tục.

Đây là loại phụ thuộc có thể thay đổi theo thời gian. Orchestrator cần phân biệt “chưa sẵn sàng, hãy chờ” với “không thể đáp ứng, cần kết thúc hoặc chuyển nhánh lỗi”.

### 2.4. Phụ thuộc thời gian và lịch

Job có thể phụ thuộc vào:

- Thời điểm cố định, chẳng hạn chạy sau 01:00 UTC.
- Cửa sổ dữ liệu, chẳng hạn chỉ xử lý ngày đã đóng sổ.
- Sự kiện đến từ hệ thống khác.
- Thời gian chờ tối thiểu sau một bước.
- Deadline cần hoàn thành trước một thời điểm.

Lịch chạy và dependency graph là hai khái niệm riêng. Lịch tạo một lần chạy workflow; dependency graph xác định thứ tự và điều kiện giữa các bước trong lần chạy đó.

### 2.5. Phụ thuộc điều kiện

Workflow có thể rẽ nhánh dựa trên output hoặc trạng thái:

- Nếu dữ liệu có bản ghi mới, chạy bước transform.
- Nếu không có dữ liệu mới, ghi nhận no-op và kết thúc thành công.
- Nếu quality check thất bại, chuyển sang quarantine.
- Nếu lỗi thuộc nhóm có thể phục hồi, retry.
- Nếu lỗi không thể phục hồi, chuyển đến nhánh xử lý thủ công.

Điều kiện nên được xác định bằng output có cấu trúc hoặc trạng thái rõ ràng, tránh phân tích log văn bản để suy ra logic nghiệp vụ.

## 3. DAG và thứ tự thực thi

DAG là viết tắt của Directed Acyclic Graph, đồ thị có hướng không có chu trình. DAG là cách biểu diễn phổ biến cho batch workflow vì nó cho phép xác định các bước có thể chạy song song mà không tạo vòng lặp phụ thuộc.

### 3.1. Directed: có hướng

Một edge A → B có nghĩa B phụ thuộc vào A theo một điều kiện đã định. Chiều edge phải nhất quán: từ bước tiền nhiệm đến bước kế nhiệm.

### 3.2. Acyclic: không có chu trình

Nếu A phụ thuộc B, B phụ thuộc C và C lại phụ thuộc A, không có bước nào có thể bắt đầu. Orchestrator nên kiểm tra chu trình trước khi chấp nhận workflow.

Một số workflow nghiệp vụ có vòng lặp, chẳng hạn thử lại bước kiểm tra hoặc xử lý từng trang dữ liệu. Không nên biểu diễn vòng lặp bằng cách tạo chu trình trong DAG tĩnh. Hãy dùng loop, map/reduce, retry policy hoặc child workflow có giới hạn và điều kiện kết thúc.

### 3.3. Topological order

Topological order là một thứ tự tuyến tính hợp lệ của các node sao cho mọi node tiền nhiệm xuất hiện trước node kế nhiệm. Có thể có nhiều thứ tự hợp lệ nếu một số job độc lập.

Ví dụ:

~~~text
fetch -> validate -> transform
                    |-> partition-A
                    |-> partition-B
                    |-> partition-C
                         |
                         v
                      aggregate -> publish
~~~

Ba partition có thể chạy theo bất kỳ thứ tự nào hoặc đồng thời, miễn là transform đã hoàn tất và tài nguyên đủ.

### 3.4. Critical path

Critical path là chuỗi phụ thuộc dài nhất quyết định thời gian hoàn tất sớm nhất của workflow khi các tài nguyên cần thiết đều sẵn có.

Nếu fetch mất 2 phút, validate 1 phút, transform 3 phút, ba partition lần lượt mất 8, 5 và 6 phút, aggregate mất 2 phút, publish mất 1 phút thì nhánh partition-A là nhánh dài nhất. Tổng thời gian lý tưởng là 2 + 1 + 3 + 8 + 2 + 1 = 17 phút, chưa tính thời gian xếp hàng, khởi động worker, retry và tranh chấp tài nguyên.

Tối ưu một job không nằm trên critical path có thể không làm giảm thời gian hoàn tất tổng thể. Tối ưu job trên critical path hoặc tăng mức song song của nhánh dài nhất thường có tác động rõ hơn.

## 4. Tuần tự, song song, fan-out và fan-in

### 4.1. Tuần tự

Các bước chạy nối tiếp khi output của bước trước là input cần thiết của bước sau. Tuần tự hóa đơn giản và dễ kiểm soát nhưng kéo dài thời gian hoàn tất.

### 4.2. Fan-out

Một bước chia dữ liệu hoặc công việc thành nhiều nhánh độc lập. Ví dụ chia một tập dữ liệu thành 100 partition và giao cho worker xử lý song song.

Fan-out cần xác định:

- Số nhánh tối đa.
- Kích thước mỗi partition.
- Cách đặt tên và nhận diện output.
- Cách retry một nhánh thất bại.
- Cách giới hạn concurrency và tài nguyên.
- Cách xử lý partition bị thiếu hoặc trùng.

Không nên tạo vô hạn task chỉ vì input có nhiều phần tử. Giới hạn fan-out để tránh cạn quota, tạo quá nhiều pod hoặc làm quá tải database.

### 4.3. Fan-in

Fan-in chờ kết quả từ nhiều nhánh rồi tiếp tục. Điều kiện có thể là:

- Tất cả nhánh thành công.
- Đủ một tỷ lệ nhánh thành công.
- Đạt số lượng kết quả tối thiểu.
- Hết deadline và xử lý các nhánh còn thiếu theo policy.

Nếu workflow yêu cầu đủ tất cả partition, không được đánh dấu fan-in thành công chỉ vì phần lớn nhánh đã hoàn tất. Nếu chấp nhận kết quả một phần, cần ghi rõ partition thiếu và thể hiện trạng thái partial-success.

### 4.4. Map và reduce

Map áp dụng cùng một phép xử lý lên nhiều phần tử hoặc partition. Reduce tổng hợp các kết quả thành một output chung. Mẫu này thường dùng trong ETL, analytics, xử lý ảnh, batch inference và tính toán phân tán.

Ví dụ:

1. Đọc manifest gồm 500 file.
2. Map tạo task xử lý từng nhóm file.
3. Worker ghi output theo partition ID.
4. Reduce đọc manifest output, kiểm tra đủ partition.
5. Tổng hợp và ghi kết quả cuối.

Nên truyền tham chiếu đến object hoặc manifest thay vì nhét dữ liệu lớn trực tiếp vào payload điều phối.

## 5. Orchestration và choreography

Hai cách tổ chức phổ biến là orchestration tập trung và choreography dựa trên sự kiện.

### 5.1. Orchestration

Một workflow engine hoặc orchestrator giữ trạng thái tổng thể và quyết định bước tiếp theo.

Ưu điểm:

- Nhìn được toàn bộ trạng thái workflow.
- Dễ biểu diễn dependency, branch, timeout và retry.
- Có lịch sử thực thi và khả năng resume.
- Có thể áp dụng policy chung cho concurrency và deadline.

Đánh đổi:

- Orchestrator là thành phần quan trọng cần HA và backup.
- Workflow có thể phụ thuộc API hoặc định dạng trạng thái của nền tảng.
- Workflow lớn có thể tạo tải lưu trạng thái và điều phối.

### 5.2. Choreography

Trong choreography, mỗi service phát event khi hoàn thành hoặc khi có thay đổi. Service khác đăng ký nhận event và tự quyết định hành động.

Ưu điểm:

- Các service ít phụ thuộc trực tiếp vào một bộ điều phối trung tâm.
- Có thể mở rộng theo event consumer.
- Phù hợp kiến trúc event-driven và các nhóm service độc lập.

Đánh đổi:

- Khó nhìn toàn bộ tiến trình end-to-end.
- Dễ tạo vòng lặp event hoặc xử lý trùng nếu contract không rõ.
- Cần correlation ID, event schema, idempotency và tracing.
- Khó xác định trạng thái hoàn tất chung nếu không có process manager.

### 5.3. So sánh

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Điều khiển | Trung tâm quyết định bước tiếp theo | Service phản ứng với event |
| Theo dõi trạng thái | Workflow engine giữ state | Phân tán ở service/event store |
| Dependency | Khai báo rõ trong workflow | Thể hiện qua event contract |
| Thay đổi quy trình | Sửa workflow definition | Thay đổi producer/consumer và contract |
| Phù hợp | DAG, batch, quy trình nhiều bước | Event-driven, service độc lập |
| Rủi ro | Orchestrator dependency và state growth | Khó quan sát, event loop, eventual consistency |

Hai mô hình có thể kết hợp. Một workflow engine điều phối quy trình cấp cao, còn từng service dùng event để thực hiện các bước nội bộ.

## 6. Trạng thái và vòng đời workflow

Orchestrator cần lưu trạng thái bền vững để có thể tiếp tục sau khi worker hoặc control process bị restart.

### 6.1. Trạng thái thường gặp

| Trạng thái | Ý nghĩa |
| --- | --- |
| Pending | Đang chờ dependency, lịch hoặc capacity |
| Ready | Đủ điều kiện để được dispatch |
| Queued | Đã đưa vào hàng đợi |
| Running | Worker đang thực thi |
| Succeeded | Hoàn tất và output đã được xác nhận |
| Failed | Kết thúc do lỗi không thể tiếp tục theo policy |
| Retrying | Đang chờ lần thực thi lại |
| Skipped | Không cần chạy do điều kiện workflow |
| Cancelled | Bị hủy theo yêu cầu hoặc policy |
| TimedOut | Vượt thời hạn thực thi |
| Compensating | Đang thực hiện hành động bù |
| PartialSuccess | Chỉ một phần nhánh hoàn tất theo policy |

Không nên dùng một trạng thái Failed cho mọi tình huống. Timeout, cancellation, dependency failure và validation failure cần được phân biệt để retry và báo cáo chính xác.

### 6.2. Trạng thái job và trạng thái workflow

Một job có thể thành công trong khi workflow vẫn đang chạy vì còn nhánh khác. Workflow chỉ hoàn tất khi các bước bắt buộc và điều kiện kết thúc đã được thỏa mãn.

Ví dụ:

- 9 trong 10 partition thành công.
- Partition còn lại đang retry.
- Workflow vẫn Running hoặc Waiting, chưa được đánh dấu Succeeded.
- Nếu policy cho phép partial result sau deadline, workflow có thể kết thúc PartialSuccess.

### 6.3. Durable state và checkpoint

State cần được lưu bền vững, không chỉ nằm trong RAM của orchestrator hoặc worker. Tùy hệ thống, state có thể gồm:

- Workflow ID và run ID.
- Job ID và attempt number.
- Dependency status.
- Input/output reference.
- Checkpoint và offset.
- Timestamps và deadline.
- Worker lease hoặc ownership token.
- Error classification và retry schedule.

Checkpoint cho phép tiếp tục từ một mốc đã lưu thay vì chạy lại toàn bộ job. Checkpoint phải được ghi theo thứ tự an toàn và liên kết với version dữ liệu để tránh resume trên input khác.

## 7. Quản lý input, output và artifact giữa các job

Workflow cần một hợp đồng dữ liệu rõ ràng giữa producer và consumer.

### 7.1. Truyền dữ liệu trực tiếp hay truyền tham chiếu?

Payload nhỏ như job ID, partition ID, version và URI có thể đi qua queue hoặc workflow state. Dữ liệu lớn nên lưu ở object storage, shared storage hoặc database rồi truyền reference.

| Cách truyền | Phù hợp | Rủi ro |
| --- | --- | --- |
| Payload trong message | Metadata nhỏ, command ngắn | Giới hạn kích thước, nhân bản dữ liệu |
| Object storage reference | File lớn, batch output | Cần quyền truy cập, lifecycle và consistency |
| Shared filesystem | Nhiều worker cần đọc/ghi file chung | Locking, mount topology và throughput |
| Database record | Trạng thái giao dịch hoặc metadata cần query | Connection pressure và coupling schema |
| Queue/event | Thông báo bất đồng bộ và phân phối công việc | Duplicate, ordering và retention |

### 7.2. Output manifest

Với fan-out/fan-in, manifest mô tả output của từng nhánh:

~~~json
{
  "workflow_id": "daily-report-2026-11-22",
  "input_version": "dataset-v42",
  "partitions": [
    {
      "partition_id": "part-000",
      "status": "SUCCEEDED",
      "uri": "s3://example-bucket/output/part-000.parquet",
      "checksum": "sha256:..."
    },
    {
      "partition_id": "part-001",
      "status": "SUCCEEDED",
      "uri": "s3://example-bucket/output/part-001.parquet",
      "checksum": "sha256:..."
    }
  ]
}
~~~

Đây là cấu trúc minh họa. Manifest thực tế cần schema version, timestamp, owner và thông tin kiểm tra dữ liệu. Consumer chỉ nên đọc output đã được đánh dấu hoàn tất và xác minh đúng input version.

### 7.3. Ghi output nguyên tử

Tránh để consumer đọc file đang được producer ghi dở. Một pattern phổ biến:

1. Ghi output vào tên tạm hoặc prefix riêng cho attempt.
2. Flush/close và xác minh checksum hoặc record count.
3. Ghi manifest hoặc marker hoàn tất.
4. Công bố reference chính thức bằng thao tác atomic phù hợp với storage.
5. Consumer chỉ đọc output đã được công bố.

Object storage thường không cung cấp rename nguyên tử giống filesystem. Có thể dùng manifest hoặc pointer object được cập nhật sau khi upload hoàn tất.

## 8. Scheduling, queue và concurrency

Workflow có thể xác định job nào đã sẵn sàng, nhưng scheduler vẫn phải quyết định khi nào dispatch và worker nào được nhận.

### 8.1. Ready queue

Khi tất cả dependency bắt buộc đã đạt trạng thái phù hợp, job được chuyển sang Ready và đưa vào hàng đợi. Worker nhận job dựa trên năng lực, priority, tenant, resource requirement và giới hạn concurrency.

Không nên dispatch job trước khi kiểm tra dependency. Worker không cần tự polling các job tiền nhiệm nếu orchestrator có thể xác định readiness.

### 8.2. Giới hạn concurrency

Các giới hạn có thể áp dụng ở nhiều cấp:

- Toàn workflow.
- Một loại job.
- Một tenant hoặc customer.
- Một queue.
- Một worker pool.
- Một database/API dependency.
- Một zone hoặc node pool.

Ví dụ, có thể cho phép tối đa 20 partition chạy đồng thời nhưng chỉ 5 job được query database cùng lúc. Như vậy vẫn tận dụng CPU mà không làm database quá tải.

### 8.3. Backpressure

Backpressure làm chậm producer hoặc giảm dispatch khi consumer/dependency không theo kịp.

Các tín hiệu:

- Queue depth tăng liên tục.
- Queue age hoặc thời gian chờ lớn.
- Worker utilization gần 100%.
- Database connection pool cạn.
- API dependency trả 429 hoặc 503.
- Error/retry rate tăng.

Biện pháp:

- Giới hạn số job đang chạy.
- Điều chỉnh tốc độ enqueue.
- Dùng token bucket hoặc rate limit.
- Tách queue theo workload hoặc priority.
- Giảm batch size hoặc tăng worker khi dependency còn capacity.
- Tạm dừng nhánh không thiết yếu.

Tăng worker không phải lúc nào cũng giải quyết backlog. Nếu bottleneck là database hoặc API bên ngoài, thêm worker có thể làm lỗi tăng nhanh hơn.

### 8.4. Fairness và priority

Một tenant có thể gửi nhiều job và chiếm hết worker. Có thể dùng queue riêng, weighted fair scheduling, quota hoặc priority class để workload quan trọng không bị starvation.

Priority cần có giới hạn. Nếu mọi job đều được đánh dấu highest priority, cơ chế ưu tiên không còn ý nghĩa.

## 9. Retry, timeout và xử lý lỗi trong workflow

Mỗi task cần timeout và retry policy phù hợp. Retry không thay thế dependency graph; nó chỉ quyết định cách một task thất bại được thử lại.

### 9.1. Phân loại lỗi

- **Transient:** lỗi tạm thời như network timeout, throttling hoặc service unavailable; có thể retry.
- **Permanent:** input sai, schema không hợp lệ, quyền bị từ chối hoặc business rule fail; thường không retry tự động.
- **Resource/capacity:** thiếu CPU, memory, quota hoặc worker; cần chờ, scale hoặc chuyển pool.
- **Dependency:** database, queue hoặc API không sẵn sàng; cần timeout, circuit breaker và retry có giới hạn.
- **Unknown:** chưa phân loại; nên lưu bằng chứng và áp dụng policy thận trọng.

### 9.2. Retry policy

Một policy thường gồm:

- Số lần thử tối đa.
- Timeout mỗi attempt.
- Backoff giữa các attempt.
- Jitter để tránh nhiều job retry cùng lúc.
- Deadline tổng thể của task/workflow.
- Lỗi nào được retry và lỗi nào phải dừng.
- Dead-letter hoặc manual intervention sau khi hết retry.

Exponential backoff có thể dùng khoảng chờ tăng dần: 1 giây, 2 giây, 4 giây, 8 giây... Jitter ngẫu nhiên giúp giảm đồng loạt retry. Cần đặt trần backoff và giới hạn tổng thời gian.

### 9.3. Timeout theo tầng

Nên có timeout riêng cho:

- Queue wait time.
- Worker startup/provisioning.
- Job execution.
- Network request đến dependency.
- Lock acquisition.
- Workflow deadline.

Timeout của request đến dependency thường phải nhỏ hơn thời gian còn lại của job. Nếu job còn 5 giây deadline mà mỗi lần gọi API timeout 30 giây, policy không còn hợp lý.

### 9.4. Idempotency và xử lý trùng

Queue và worker thường có semantics at-least-once: cùng một message có thể được giao nhiều lần khi ack bị mất hoặc worker crash sau khi ghi dữ liệu.

Job cần idempotent hoặc có cơ chế deduplication:

- Dùng idempotency key theo workflow/run/partition.
- Ghi trạng thái kết quả cùng transaction nếu có thể.
- Dùng unique constraint hoặc conditional write.
- Lưu attempt ID riêng nhưng giữ logical job ID ổn định.
- Chỉ ack message sau khi kết quả đã được ghi bền vững.

Exactly-once end-to-end thường không phải đặc tính đơn giản có thể bật bằng một cờ. Có thể đạt hiệu quả gần exactly-once bằng idempotency, transaction boundary và deduplication, nhưng cần xác định rõ phạm vi.

### 9.5. Dead-letter và manual recovery

Khi hết retry, job có thể được chuyển sang dead-letter queue hoặc trạng thái cần can thiệp. Bản ghi cần giữ:

- Job/workflow ID.
- Input reference và version.
- Attempt count.
- Error class và message đã làm sạch thông tin nhạy cảm.
- Timestamps.
- Worker/image version.
- Trace/correlation ID.

Không nên xóa dead-letter ngay sau khi alert. Cần có quy trình phân tích, sửa nguyên nhân, replay an toàn hoặc đánh dấu không thể phục hồi.

## 10. Cancellation, compensation và workflow dài hạn

Một workflow có thể bị hủy do người dùng, deadline hoặc sự cố. Hủy workflow không có nghĩa mọi task đang chạy dừng tức thì.

### 10.1. Cancellation

Orchestrator nên:

- Ngăn dispatch job mới.
- Gửi tín hiệu cancel đến worker đang chạy.
- Cho phép worker dọn tài nguyên hoặc ghi checkpoint.
- Thu hồi lease sau timeout.
- Ghi trạng thái Cancelled và lý do.
- Không đánh dấu Succeeded nếu chỉ một phần công việc đã hoàn tất.

Worker phải xử lý cancellation một cách hợp tác; kill process đột ngột có thể để lại file dở, lock hoặc transaction chưa rõ trạng thái.

### 10.2. Compensation

Một số workflow có bước tạo side effect không thể rollback bằng transaction đơn. Khi bước sau thất bại, cần chạy hành động bù:

- Hủy reservation đã tạo.
- Hoàn lại hạn mức đã giữ.
- Đánh dấu đơn hàng bị hủy.
- Xóa artifact tạm.
- Gửi sự kiện bù để cập nhật hệ thống phụ thuộc.

Đây là mẫu Saga. Compensation không nhất thiết khôi phục chính xác trạng thái cũ; nó tạo một hành động nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được.

### 10.3. Workflow dài hạn

Với workflow chạy nhiều giờ hoặc nhiều ngày:

- Lưu state bền vững.
- Dùng timer/event thay vì giữ worker idle.
- Checkpoint ở ranh giới bước.
- Đặt deadline và policy cho bước chờ.
- Version hóa workflow definition.
- Xử lý tương thích khi workflow đang chạy gặp phiên bản mới.
- Có khả năng resume và manual intervention.

## 11. Ví dụ workflow batch: xử lý báo cáo hằng ngày

Một hệ thống cần tải dữ liệu giao dịch, xác minh, chia partition, tính tổng và xuất báo cáo. Mỗi lần chạy có run ID theo ngày dữ liệu.

### 11.1. Dependency graph

~~~mermaid
flowchart TD
    A["Create run + input manifest"] --> B["Download source files"]
    B --> C["Validate schema and checksum"]
    C --> D["Normalize records"]
    D --> E1["Partition 1"]
    D --> E2["Partition 2"]
    D --> E3["Partition 3"]
    E1 --> F["Verify all partitions"]
    E2 --> F
    E3 --> F
    F --> G["Aggregate metrics"]
    G --> H["Business quality checks"]
    H --> I{"Quality passed?"}
    I -- "Yes" --> J["Publish report"]
    I -- "No" --> K["Quarantine + alert"]
    J --> L["Mark run complete"]
    K --> M["Mark run failed / needs review"]
~~~

### 11.2. Quy tắc điều phối

| Bước | Điều kiện bắt đầu | Điều kiện hoàn tất |
| --- | --- | --- |
| Create run | Đến lịch hoặc nhận event | Run ID và manifest được lưu |
| Download | Run đã tạo | Tất cả file nguồn được tải và xác minh |
| Validate | Download thành công | Schema/checksum hợp lệ |
| Normalize | Validate thành công | Output chuẩn hóa đã công bố |
| Partition | Normalize thành công | Từng partition có output và status |
| Verify | Tất cả partition đã terminal | Đủ partition thành công theo policy |
| Aggregate | Verify đạt | Dataset tổng hợp được ghi |
| Quality check | Aggregate thành công | Các rule nghiệp vụ đạt |
| Publish | Quality check đạt | Báo cáo được công bố và có version |

Nếu một partition lỗi transient, chỉ retry partition đó. Không chạy lại toàn bộ workflow nếu các partition khác đã hoàn tất và output của chúng vẫn hợp lệ.

### 11.3. Pseudocode điều phối

~~~python
def run_daily_report(run_id, manifest):
    source = download_sources(manifest)
    validate_sources(source)
    normalized = normalize(source, run_id)

    partition_refs = split_manifest(normalized)
    results = map_with_limit(
        items=partition_refs,
        max_concurrency=12,
        task=lambda item: process_partition(
            run_id=run_id,
            partition_id=item.id,
            input_ref=item.uri,
            idempotency_key=f"{run_id}:{item.id}",
        ),
    )

    verify_complete_partition_set(results, manifest)
    report = aggregate(results)
    quality_check(report)
    publish_versioned_report(run_id, report)
~~~

Pseudocode minh họa logic, không phải API của một workflow engine cụ thể. Hàm map_with_limit cần giới hạn concurrency, lưu trạng thái từng partition và chỉ retry lỗi được phân loại là transient. Các hàm ghi dữ liệu phải idempotent hoặc dùng output path theo attempt/version.

## 12. Chọn công cụ điều phối

Nền tảng được chọn cần phù hợp với loại workflow, môi trường compute và năng lực vận hành.

| Công cụ/nhóm | Mô hình phù hợp | Điểm cần cân nhắc |
| --- | --- | --- |
| Apache Airflow | DAG theo lịch, data pipeline và batch orchestration | Scheduler/metadata database, worker executor, backfill và DAG version |
| Argo Workflows | Workflow container-native trên Kubernetes | Pod lifecycle, artifact repository, RBAC, cluster capacity và workflow CRD |
| Temporal | Workflow dài hạn, stateful orchestration và retry bền vững | Workflow code compatibility, worker deployment và persistence service |
| AWS Step Functions | Managed state machine và tích hợp AWS | State transition cost, service integration và giới hạn dịch vụ |
| Azure Durable Functions | Durable orchestration cho function/app trên Azure | Replay semantics, function versioning và storage backend |
| Google Cloud Workflows | Điều phối dịch vụ và API theo bước | Connector, execution limits và tích hợp dịch vụ |
| Queue + custom worker | Công việc đơn giản, event-driven | Tự xây state tracking, retry, dedupe, visibility và recovery |

Không chọn công cụ chỉ vì số lượng tính năng. Cần đánh giá độ bền state, khả năng replay, lịch chạy, concurrency, observability, chi phí, giới hạn execution và mức phụ thuộc nhà cung cấp.

## 13. Bảo mật và quyền truy cập giữa các job

Mỗi job chỉ nên có quyền cần thiết cho input, output và dịch vụ mà nó sử dụng.

- Dùng workload identity hoặc service account riêng cho worker pool.
- Cấp quyền đọc input và ghi đúng output prefix.
- Không đưa access key dài hạn vào queue payload hoặc workflow definition.
- Mã hóa dữ liệu lưu trữ và truyền tải.
- Kiểm soát ai được tạo, sửa, hủy hoặc replay workflow.
- Làm sạch secret và dữ liệu nhạy cảm khỏi error message/log.
- Ghi audit cho thao tác thủ công và elevated permission.
- Giới hạn network egress của worker theo dependency cần thiết.

Nếu nhiều tenant dùng chung worker pool, cần phân vùng dữ liệu, queue, identity và resource quota để job của tenant này không truy cập output của tenant khác.

## 14. Quan sát và vận hành workflow

Theo dõi cả workflow và từng job:

| Nhóm | Metric hoặc tín hiệu |
| --- | --- |
| Workflow | Số run, success/failure rate, duration, age và deadline miss |
| Job | Queue wait, execution time, attempt count, timeout và status |
| Dependency | Ready job count, blocked job count và dependency wait |
| Queue | Depth, oldest message age, redelivery và dead-letter count |
| Worker | CPU, memory, concurrency, restart, OOM và utilization |
| Data | Input/output bytes, partition completeness, checksum và schema errors |
| Dependency service | API latency, 429/5xx, DB connection và throttling |
| Cost | Compute time, storage, transfer, orchestration events và cost per run |

### 14.1. Correlation ID

Mỗi workflow run nên có correlation ID truyền xuyên suốt log, trace, queue message và output manifest. Mỗi job có job ID và attempt ID riêng. Nhờ đó có thể tìm một run và xem toàn bộ nhánh mà không phải ghép log chỉ bằng timestamp.

### 14.2. Alert hữu ích

Ví dụ alert:

- Workflow quan trọng chưa bắt đầu trong cửa sổ lịch.
- Job bị blocked lâu hơn ngưỡng.
- Queue age tăng liên tục.
- Retry rate tăng bất thường.
- Dead-letter count khác 0 đối với pipeline quan trọng.
- Một dependency trả 429/5xx kéo dài.
- Workflow sắp vượt deadline.
- Partition output thiếu hoặc checksum sai.

Alert nên chỉ rõ workflow ID, job ID, attempt, dependency và runbook liên quan. Alert chung như “job failed” mà không có context làm tăng thời gian xử lý sự cố.

## 15. Tối ưu thời gian và chi phí workflow

### 15.1. Tối ưu critical path

Đo duration của từng node và xác định nhánh dài nhất. Tối ưu job nằm trên critical path trước, ví dụ:

- Tăng parallelism của partition.
- Giảm thời gian chờ dependency.
- Dùng compute phù hợp CPU/RAM/I/O.
- Đưa worker gần data source.
- Giảm kích thước artifact hoặc số lần serialize.

### 15.2. Chọn batch size

Batch quá lớn làm retry tốn kém và tăng thời gian một worker giữ tài nguyên. Batch quá nhỏ tạo nhiều job, queue message, orchestration transition và overhead startup.

Chọn batch size bằng benchmark với các mức:

- Thời gian xử lý trung bình.
- Memory footprint.
- Tỷ lệ lỗi.
- Số lần retry.
- Throughput tổng.
- Chi phí điều phối trên mỗi đơn vị dữ liệu.

### 15.3. Tận dụng compute phù hợp

- CPU-bound: node/VM compute-optimized.
- Memory-bound: đủ RAM để tránh spill hoặc OOM.
- I/O-bound: storage/network throughput và concurrency phù hợp.
- Workload ngắt quãng: worker có thể scale theo queue.
- Job chịu interruption: cân nhắc Spot/Preemptible với checkpoint.

Không tăng concurrency vượt khả năng database hoặc API. Một workflow có thể hoàn thành nhanh hơn nhưng làm tăng tổng chi phí do throttling, retry và scale dependency.

### 15.4. Dừng job không còn cần thiết

Khi một nhánh thất bại và workflow không thể thành công theo policy, cân nhắc hủy các nhánh không còn giá trị. Trước khi hủy, xác định worker có hỗ trợ cancellation và cleanup an toàn hay không.

## 16. Các lỗi thiết kế thường gặp

- Không khai báo dependency, để job tự dò trạng thái của job khác.
- Tạo DAG có chu trình hoặc nhánh không có điều kiện kết thúc.
- Coi job đã được enqueue là job đã chạy.
- Fan-out không giới hạn làm cạn worker, quota hoặc database connection.
- Fan-in chỉ đếm số kết quả mà không xác minh đủ partition.
- Truyền payload lớn qua queue hoặc workflow state.
- Retry lỗi permanent và làm tăng tải vô ích.
- Không dùng idempotency, dẫn đến duplicate khi message được giao lại.
- Timeout job nhưng worker vẫn tiếp tục ghi output.
- Không version hóa input/output schema.
- Không lưu state bền vững và không thể resume sau orchestrator restart.
- Dùng một service account quá rộng cho mọi job.
- Không có deadline nên workflow chờ vô hạn.
- Không có dead-letter hoặc quy trình replay.
- Chỉ quan sát worker mà bỏ qua dependency và queue.

## 17. Checklist thiết kế workflow

**Dependency graph**

- [ ] Mỗi job có input, output và điều kiện hoàn tất rõ ràng.
- [ ] DAG không có chu trình ngoài các loop có kiểm soát.
- [ ] Dependency theo success/failure/always được định nghĩa.
- [ ] Fan-out có giới hạn và fan-in kiểm tra đủ kết quả.
- [ ] Conditional branch có output/status có cấu trúc.

**Execution**

- [ ] Có queue wait timeout, execution timeout và workflow deadline.
- [ ] Có concurrency limit theo workflow, tenant và dependency.
- [ ] Có backpressure, priority và fairness phù hợp.
- [ ] Job có idempotency hoặc deduplication.
- [ ] Retry chỉ áp dụng cho lỗi được phân loại và có backoff/jitter.
- [ ] Có cancellation, checkpoint và compensation nếu cần.

**Data**

- [ ] Input/output schema và version được ghi nhận.
- [ ] Dữ liệu lớn được truyền bằng reference.
- [ ] Output được công bố sau khi ghi hoàn tất và xác minh.
- [ ] Manifest theo dõi partition, checksum và input version.
- [ ] Retention và cleanup được cấu hình.

**Operations**

- [ ] Workflow state được lưu bền vững.
- [ ] Có correlation ID xuyên suốt các job.
- [ ] Dashboard thể hiện critical path và blocked jobs.
- [ ] Có alert cho queue age, retry, timeout và deadline miss.
- [ ] Có dead-letter, replay và manual recovery procedure.
- [ ] Worker identity có quyền tối thiểu.
- [ ] Có ước lượng cost per run và cost per completed unit.

## 18. Quy trình triển khai workflow an toàn

1. Xác định mục tiêu nghiệp vụ và đơn vị dữ liệu của workflow.
2. Chia quy trình thành các job nhỏ có input/output rõ ràng.
3. Vẽ DAG và xác định dependency success/failure/conditional.
4. Xác định nhánh có thể chạy song song và critical path.
5. Chọn orchestrator, queue và worker runtime.
6. Thiết lập state store, artifact store và manifest.
7. Đặt timeout, retry, idempotency, concurrency và deadline.
8. Thiết lập identity, network policy, secret và audit.
9. Chạy thử với input nhỏ, lỗi có chủ đích và worker restart.
10. Kiểm tra duplicate, partial result, cancellation và resume.
11. Đo duration, throughput, queue wait, resource usage và cost.
12. Triển khai dần, theo dõi alert và điều chỉnh policy theo dữ liệu thực tế.

## 19. Nguyên tắc vận hành

1. **Mô hình hóa dependency rõ ràng:** dùng DAG hoặc state machine thay vì dựa vào thứ tự ngầm.
2. **Phân biệt trạng thái job và workflow:** một job thành công không đồng nghĩa toàn workflow hoàn tất.
3. **Chỉ chạy khi dependency đạt điều kiện:** success, failure, always hoặc conditional phải được khai báo.
4. **Tận dụng song song có giới hạn:** fan-out/fan-in giúp tăng throughput nhưng cần concurrency control.
5. **Lưu state bền vững:** orchestrator và worker có thể restart mà không mất tiến trình.
6. **Thiết kế idempotent:** message redelivery hoặc retry không tạo side effect trùng.
7. **Giới hạn thời gian và retry:** mọi job cần timeout, deadline và policy lỗi rõ ràng.
8. **Kiểm soát backpressure:** bảo vệ database, API và worker pool khỏi tải dồn.
9. **Truyền artifact bằng reference:** dùng manifest/version/checksum để bảo đảm dữ liệu đúng.
10. **Quan sát end-to-end:** correlation ID, queue age, critical path và cost per run giúp vận hành hiệu quả.

Phụ thuộc giữa các job là nền tảng của xử lý nền và batch workflow. Khi dependency được mô hình hóa thành DAG hoặc state machine, orchestrator có thể xác định bước sẵn sàng, chạy song song có kiểm soát, lưu trạng thái và phục hồi sau lỗi. Kết hợp hợp đồng dữ liệu rõ ràng, idempotency, timeout, retry, backpressure và observability giúp workflow xử lý khối lượng lớn một cách đáng tin cậy, có thể mở rộng và kiểm soát được chi phí.
