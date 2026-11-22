# Timeout, retries, backoff và circuit breaker khi gọi GCP APIs

## 1. Vì sao lời gọi API cần cơ chế chịu lỗi?

Một ứng dụng chạy trên Cloud Run, GKE hoặc Compute Engine thường gọi nhiều Google Cloud APIs để đọc cấu hình, lấy secret, quản lý tài nguyên, ghi dữ liệu hoặc phát hành workload. Những lời gọi này đi qua mạng và phụ thuộc vào quota, trạng thái dịch vụ, DNS, kết nối TLS, xác thực, tải của client và tải của backend. Ngay cả khi API hoạt động bình thường trong phần lớn thời gian, một đợt tăng tải, lỗi mạng ngắn hoặc quota bị chạm vẫn có thể làm một nhóm request thất bại.

Ví dụ, một Cloud Run service nhận yêu cầu tạo báo cáo. Để xử lý một yêu cầu, service gọi Cloud Asset Inventory để lấy danh sách tài nguyên, Secret Manager để đọc cấu hình kết nối và Cloud Storage để lưu kết quả. Nếu một lời gọi bị treo, thread hoặc request slot vẫn bị chiếm dụng. Nếu client retry quá nhanh, số request tăng lên đúng lúc dịch vụ đang quá tải. Nếu nhiều tầng cùng retry, một thao tác của người dùng có thể tạo ra hàng chục lời gọi API.

Bốn cơ chế thường được phối hợp để kiểm soát tình huống này:

- **Timeout** giới hạn thời gian một lần gọi hoặc toàn bộ thao tác được phép tiêu thụ.
- **Retry** thực hiện lại một lời gọi khi lỗi có khả năng tạm thời và thao tác an toàn khi lặp lại.
- **Backoff** giãn khoảng cách giữa các lần retry để giảm áp lực lên dịch vụ.
- **Circuit breaker** tạm ngừng gửi request đến một dependency đang lỗi hoặc phản hồi quá chậm, sau đó thử lại có kiểm soát.

Đây là các cơ chế bổ trợ nhau. Timeout không tự sửa lỗi; retry không làm một API lỗi trở nên khỏe hơn; backoff không thay thế quota management; circuit breaker không giới hạn số request đồng thời. Cần thiết kế chúng theo ngân sách thời gian, ngữ nghĩa thao tác và SLO của ứng dụng.

Trong module `CLOUD_PROVIDERS_GCP`, các cơ chế này gắn trực tiếp với việc vận hành IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Mỗi API có thể có đặc tính lỗi, quota và chính sách retry riêng, vì vậy không nên dùng một cấu hình giống nhau cho mọi dịch vụ.

## 2. Timeout và deadline

### 2.1. Phân biệt timeout và deadline

**Timeout** là khoảng thời gian tối đa mà một thao tác được phép chạy. **Deadline** là thời điểm tuyệt đối mà sau đó caller không còn chờ kết quả. Ví dụ, một request bắt đầu lúc 10:00:00 với timeout 3 giây có deadline lúc 10:00:03.

Trong hệ thống phân tán, deadline thường hữu ích hơn một timeout mới được đặt lại ở từng tầng. Giả sử API gateway dành 4 giây cho request, ứng dụng đã dùng 1 giây để xác thực và đọc cache. Khi gọi Google Cloud API, ứng dụng chỉ còn khoảng 3 giây. Nếu ứng dụng lại đặt timeout 4 giây cho lời gọi tiếp theo, tổng thời gian có thể vượt ngân sách mà caller ban đầu chấp nhận.

Một deadline end-to-end nên bao gồm:

- Thời gian chờ trong queue hoặc thread pool.
- Thời gian thiết lập kết nối, DNS, TLS và xác thực khi có phát sinh.
- Thời gian xử lý của từng API attempt.
- Thời gian chờ backoff giữa các attempt.
- Thời gian xử lý kết quả và trả response cho caller.

Không đặt timeout quá dài chỉ để tăng tỷ lệ thành công. Request đã hết giá trị với người dùng vẫn có thể giữ kết nối, bộ nhớ và worker trong khi backend đang gặp sự cố.

### 2.2. Timeout theo từng attempt và timeout toàn thao tác

Khi có retry, cần phân biệt hai giới hạn:

| Giới hạn | Ý nghĩa | Ví dụ |
|---|---|---|
| Attempt timeout | Thời gian tối đa cho một lần gọi API | Mỗi lần gọi tối đa 1 giây |
| Operation deadline / total timeout | Tổng thời gian cho lần gọi ban đầu, mọi retry và backoff | Toàn bộ thao tác tối đa 4 giây |

Ví dụ một thao tác có ngân sách 4 giây, attempt timeout 1 giây và backoff tăng dần. Nếu attempt đầu mất 1 giây, lần retry tiếp theo phải dùng phần ngân sách còn lại. Không được bắt đầu một attempt mới nếu thời gian còn lại không đủ để nó có ích.

Có thể hình dung:

~~~text
Tổng deadline: 4.000 ms
|--- Attempt 1: 1.000 ms ---|-- Backoff: 200 ms --|
                                      |-- Attempt 2: tối đa 1.000 ms --|
                                                                       |-- phần còn lại --|
~~~

Đây chỉ là ví dụ phân bổ thời gian; attempt timeout và số lần retry phải được điều chỉnh theo latency thực tế, độ quan trọng của request và SLO.

### 2.3. Chọn timeout có cơ sở

Không có một timeout đúng cho mọi GCP API. Hãy bắt đầu từ thời gian người dùng hoặc upstream có thể chờ, sau đó đo latency ở điều kiện tải bình thường và khi có sự cố. Một thao tác đọc metadata nhanh có thể dùng timeout ngắn; một thao tác tạo snapshot, export dữ liệu hoặc chờ long-running operation cần mô hình timeout và polling riêng.

Các bước chọn timeout:

1. Xác định SLO và ngân sách latency end-to-end của request.
2. Đo p50, p95 và p99 của API theo method, project và region.
3. Tách thời gian kết nối khỏi thời gian xử lý nếu HTTP client hoặc RPC library cho phép.
4. Đặt attempt timeout lớn hơn latency thường gặp nhưng đủ ngắn để giải phóng tài nguyên khi backend treo.
5. Đặt total timeout nhỏ hơn hoặc bằng phần ngân sách còn lại của caller.
6. Kiểm thử ở tải cao, khi quota bị giới hạn và khi backend chậm.
7. Theo dõi tỷ lệ timeout và điều chỉnh dựa trên dữ liệu, không dựa trên một lần thử.

Timeout quá ngắn gây lỗi giả khi backend chỉ hơi chậm. Timeout quá dài làm request tồn tại lâu, tăng số tác vụ đang chờ và khiến lỗi ở một dependency lan sang các tầng khác.

### 2.4. Truyền deadline và hủy công việc

Khi một service nhận request rồi gọi service khác, nó cần truyền phần thời gian còn lại xuống lời gọi tiếp theo. Với gRPC, deadline propagation giúp các tầng biết caller không còn chờ sau thời điểm nào. Tài liệu gRPC cho biết Java và Go hỗ trợ propagation mặc định trong các tình huống được mô tả; các client HTTP hoặc thư viện khác có thể cần truyền timeout/cancellation rõ ràng.

Nếu caller hủy request hoặc deadline đã hết, ứng dụng nên hủy các công việc phụ thuộc khi có thể. Chỉ dừng chờ ở client nhưng vẫn để các tác vụ nền tiếp tục chạy có thể tiêu tốn CPU, connection và quota mà không còn tạo ra kết quả hữu ích.

Dùng đồng hồ monotonic như `System.nanoTime()` để đo thời lượng và tính ngân sách trong tiến trình. Không dùng đồng hồ lịch như `LocalDateTime.now()` để đo elapsed time vì đồng hồ hệ thống có thể được điều chỉnh.

## 3. Khi nào nên retry?

Retry phù hợp khi lỗi có khả năng tạm thời, thao tác có thể lặp lại an toàn và vẫn còn ngân sách thời gian. Trước khi retry, cần trả lời ba câu hỏi:

1. Lỗi có khả năng tự hết sau một khoảng ngắn không?
2. Server có thể đã thực hiện thao tác dù client chưa nhận được response không?
3. Có đủ thời gian và quota để thử lại không?

### 3.1. Phân loại lỗi

Bảng sau là hướng dẫn khởi đầu. Mã lỗi có thể khác giữa HTTP/JSON và gRPC; chính sách cụ thể của từng API và client library luôn được ưu tiên.

| HTTP / gRPC thường gặp | Ý nghĩa | Cách xử lý thường phù hợp |
|---|---|---|
| `408` / `DEADLINE_EXCEEDED` | Request hoặc RPC vượt thời gian | Chỉ retry nếu thao tác an toàn, còn deadline và có lý do tin rằng lần tiếp theo có thể thành công |
| `429` / `RESOURCE_EXHAUSTED` | Quota hoặc rate limit bị chạm | Giảm tốc độ, đọc thông tin quota và thời gian retry do server/API cung cấp; backoff dài hơn |
| `500` / `INTERNAL` | Lỗi nội bộ phía server | Có thể retry thao tác idempotent với backoff |
| `502`, `503`, `504` / `UNAVAILABLE` | Gateway hoặc dịch vụ tạm thời không sẵn sàng | Có thể retry thao tác idempotent, có giới hạn |
| `400` / `INVALID_ARGUMENT` | Request sai tham số | Sửa request; retry nguyên trạng thường không có ích |
| `401` / `UNAUTHENTICATED` | Thiếu hoặc hết hạn thông tin xác thực | Làm mới credential theo cơ chế hợp lệ rồi thử lại có kiểm soát nếu phù hợp |
| `403` / `PERMISSION_DENIED` | Không đủ quyền hoặc bị policy chặn | Kiểm tra IAM, Organization Policy, VPC Service Controls hoặc cấu hình; không retry liên tục |
| `404` / `NOT_FOUND` | Tài nguyên hoặc method không tồn tại trong ngữ cảnh hiện tại | Kiểm tra tên, scope và trạng thái tài nguyên; chỉ retry khi tài liệu API mô tả eventual consistency |
| `409` / `ALREADY_EXISTS`, `ABORTED` | Xung đột trạng thái hoặc transaction | Đọc lại trạng thái; có thể phải chạy lại toàn bộ transaction theo hướng dẫn |
| `412` (HTTP) | Precondition thất bại | Đọc lại generation, metageneration hoặc ETag; xác minh trạng thái rồi quyết định thao tác mới |
| `FAILED_PRECONDITION` (gRPC) | Trạng thái hiện tại không đáp ứng điều kiện của operation; trong mapping Google API thường là HTTP 400 | Sửa điều kiện hoặc trạng thái resource; không retry nguyên trạng |

Không phân loại chỉ bằng chuỗi message. Google Cloud cảnh báo error message có thể thay đổi; hãy dùng HTTP status, gRPC status code và structured error details như `google.rpc.ErrorInfo` hoặc `RetryInfo` khi API cung cấp.

Một số hướng dẫn Google Cloud cho Service Usage và Service Infrastructure khuyến nghị retry với exponential intervals cộng randomness, đồng thời nêu khoảng tối thiểu 30 giây cho lỗi quota `429` và 1 giây cho `500`/`503`. Đây là hướng dẫn cho các API/tình huống được tài liệu đó đề cập, không phải một con số áp dụng đồng loạt cho mọi GCP API. Nếu API cụ thể trả `Retry-After`, `RetryInfo` hoặc tài liệu quota đưa ra thời gian khác, hãy tuân theo thông tin đó.

### 3.2. Không phải timeout nào cũng có nghĩa request chưa chạy

Một client gửi lệnh tạo tài nguyên, server thực hiện thành công, nhưng response bị mất trên đường về. Client chỉ thấy timeout. Nếu client gửi lại lệnh tạo mà không có cơ chế chống trùng, có thể tạo hai tài nguyên hoặc hai tác vụ.

Với thao tác có side effect, cần xác định trạng thái trước khi retry. Các lựa chọn gồm:

- Dùng idempotency key hoặc request ID nếu API hỗ trợ.
- Dùng precondition như generation, metageneration hoặc ETag.
- Ghi nhận operation ID để tra cứu long-running operation.
- Đọc trạng thái resource trước khi gửi lại lệnh tạo/cập nhật.
- Thiết kế thao tác theo kiểu upsert hoặc ghi đè có điều kiện khi API hỗ trợ.

Không tự giả định mọi Google Cloud API hỗ trợ idempotency key. Hãy đọc hợp đồng của method cụ thể.

## 4. Idempotency: điều kiện an toàn trước khi retry

Một thao tác **idempotent** nếu thực hiện nhiều lần với cùng điều kiện vẫn dẫn đến cùng trạng thái cuối cùng như thực hiện một lần. Ví dụ, đọc một resource hoặc liệt kê danh sách thường có thể lặp lại an toàn. Tạo một notification mới hoặc gửi một thông điệp có thể tạo thêm đối tượng mỗi lần gọi, nên không mặc nhiên idempotent.

### 4.1. Phân loại thao tác

| Loại thao tác | Ví dụ | Nguyên tắc retry |
|---|---|---|
| Read-only | GET, list, get metadata | Thường an toàn để retry lỗi tạm thời |
| Set state theo giá trị cố định | Đặt cấu hình thành `enabled=true` | Có thể idempotent nếu API semantics đảm bảo |
| Create | Tạo VM, subscription, notification | Chỉ retry khi có request ID, precondition hoặc cách tra cứu kết quả |
| Increment / append | Tăng counter, append event | Không retry mù; cần deduplication hoặc sequence key |
| Delete | Xóa resource | Kiểm tra semantics khi resource đã bị xóa; dùng version/precondition nếu cần |
| Long-running operation | Export, import, snapshot, deploy | Phân biệt retry lệnh bắt đầu operation với retry thao tác poll |

### 4.2. Dùng precondition trong Cloud Storage

Cloud Storage minh họa rõ vì sao idempotency quan trọng. Một số thao tác cập nhật object chỉ an toàn khi request mang precondition phù hợp. Ví dụ, `ifGenerationMatch` có thể ràng buộc thao tác với generation mong đợi; `ifMetagenerationMatch` hoặc ETag có thể bảo vệ cập nhật metadata. Nếu trạng thái resource đã thay đổi, precondition thất bại thay vì ghi đè nhầm phiên bản mới.

Ví dụ Java minh họa ghi object chỉ khi object chưa tồn tại:

~~~java
BlobId blobId = BlobId.of(bucketName, objectName);
BlobInfo blobInfo = BlobInfo.newBuilder(blobId).build();

Blob created = storage.create(
    blobInfo,
    payload,
    Storage.BlobTargetOption.doesNotExist()
);
~~~

`doesNotExist()` tạo điều kiện tương ứng để thao tác không ghi đè object đã tồn tại. Khi response bị mất, lần thử lại có thể gặp precondition failure vì lần đầu đã tạo object thành công. Khi đó cần đọc metadata và xác minh generation/nội dung thay vì tiếp tục retry create.

Tên option và cách truyền precondition khác nhau giữa các thư viện và phiên bản. Đối chiếu API reference của client đang sử dụng trước khi áp dụng.

### 4.3. Long-running operations

Một số API trả về operation thay vì kết quả hoàn tất ngay. Hãy tách hai giai đoạn:

1. **Start operation:** tạo export, import, snapshot hoặc tác vụ dài. Cần xử lý trường hợp request thành công nhưng response chứa operation name bị mất.
2. **Poll operation:** truy vấn trạng thái của operation đã có. Poll thường là thao tác đọc, có thể dùng backoff riêng và không được tạo operation mới.

Nếu có operation ID, lưu ID bền vững để có thể tiếp tục theo dõi sau khi process restart. Không gửi lại lệnh bắt đầu chỉ vì một lần poll bị timeout.

## 5. Exponential backoff và jitter

### 5.1. Exponential backoff

Khi nhiều client retry ngay lập tức, server nhận thêm tải trong lúc đang phục hồi. Exponential backoff tăng thời gian chờ sau mỗi lần thất bại:

\[
d_n = \min(d_{\max}, d_0 \times m^n)
\]

Trong đó:

- \(d_0\): thời gian chờ ban đầu.
- \(m\): hệ số nhân, thường lớn hơn 1.
- \(n\): số thứ tự lần retry, bắt đầu từ 0.
- \(d_{\max}\): giới hạn trên của thời gian chờ.

Ví dụ với \(d_0=200\) ms, \(m=2\), \(d_{\max}=2\) giây:

| Lần retry | Backoff trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 trở đi | 2.000 ms |

Giới hạn trên giúp thời gian chờ không tăng vô hạn. Giới hạn số lần retry và total deadline giúp thao tác kết thúc có kiểm soát.

### 5.2. Jitter để tránh retry đồng loạt

Nếu hàng nghìn instance cùng retry sau đúng 1, 2, 4 giây, chúng có thể tạo ra các đợt tải đồng bộ. Hiện tượng này thường được gọi là thundering herd. **Jitter** thêm ngẫu nhiên vào thời gian chờ để các client phân tán thời điểm gọi lại.

Một biến thể phổ biến là full jitter:

\[
d_{\text{actual}} = random(0, d_n)
\]

Ví dụ backoff cho lần retry là 800 ms thì client chọn ngẫu nhiên một khoảng từ 0 đến 800 ms. Đây là một thuật toán minh họa; các thư viện có thể dùng biến thể jitter khác. Google Cloud Client Libraries for Java luôn bật jitter trong retry mechanism và tài liệu mô tả độ trễ ngẫu nhiên trong khoảng từ 1 đến giá trị retry delay đã tính.

Không tự thêm một lớp jitter bên ngoài nếu client library đã thực hiện backoff và jitter, trừ khi bạn hiểu rõ cách hai lớp phối hợp.

### 5.3. Kết hợp backoff với Retry-After và quota

Khi server trả `Retry-After` hoặc structured retry information, hãy ưu tiên thời gian server yêu cầu. Nếu server cho biết quota sẽ được mở lại sau một khoảng thời gian, retry nhanh hơn chỉ làm tăng lỗi và có thể tiếp tục tiêu thụ quota.

Đối với lỗi quota, backoff cần đủ dài để tốc độ request giảm thực sự. Cùng lúc đó, kiểm tra:

- Quota đang bị giới hạn theo project, user, method hay region?
- Có một batch job hoặc nhiều service cùng dùng quota không?
- Có thể gom request, cache kết quả hoặc dùng batch API không?
- Có cần giảm concurrency hoặc điều chỉnh lịch chạy không?
- Có cần yêu cầu tăng quota sau khi tối ưu tải không?

Retry là cơ chế phục hồi lỗi tạm thời; nó không phải cách giải quyết thiếu quota kéo dài.

## 6. Giới hạn retry và retry budget

### 6.1. Giới hạn theo request

Một logical operation nên có giới hạn rõ ràng:

- Số lần gọi tối đa, tính cả lần đầu.
- Total timeout hoặc deadline.
- Maximum backoff.
- Danh sách lỗi có thể retry.
- Điều kiện idempotency.
- Điều kiện dừng khi caller hủy hoặc deadline hết.

Không retry vô hạn. Khi hết ngân sách, trả lỗi có thể xử lý ở tầng gọi, chuyển tác vụ sang queue hoặc dùng kết quả dự phòng nếu nghiệp vụ cho phép.

### 6.2. Vì sao retry nhiều tầng gây khuếch đại tải?

Giả sử frontend, backend và một lớp SDK đều cho phép 3 lần retry sau lần gọi đầu. Một thao tác ban đầu có thể tạo tối đa:

\[
4 \times 4 \times 4 = 64 \text{ lần gọi ở tầng thấp nhất}
\]

Khi backend đang quá tải, các lần gọi bổ sung làm tình hình xấu hơn. Google SRE mô tả retry amplification là một yếu tố có thể biến một tỷ lệ lỗi nhỏ thành cascading failure.

Chọn một tầng làm **retry owner** cho từng lời gọi. Nếu GAX client library đã retry RPC, tầng nghiệp vụ không nên tự retry cùng lỗi một cách mù quáng. Nếu tầng nghiệp vụ cần retry vì một workflow lớn gồm nhiều RPC, phải tính rõ ngân sách và trạng thái đã hoàn tất của từng bước.

### 6.3. Retry budget cấp tiến trình hoặc service

Retry budget giới hạn tổng số retry mà một process hoặc service được phép tạo trong một khoảng thời gian. Có thể biểu diễn theo:

- Số retry tối đa mỗi phút.
- Tỷ lệ retry trên số request gốc.
- Token bucket cho phép một lượng retry nhất định và nạp lại theo thời gian.
- Giới hạn retry riêng cho từng API method hoặc quota domain.

Khi budget cạn, request mới không được retry tự động. Cách này bảo vệ backend và quota khi lỗi lan rộng. Mức budget cần được chọn qua load test và SLO; một con số cố định không phù hợp cho mọi service.

## 7. Circuit breaker

### 7.1. Circuit breaker giải quyết vấn đề gì?

Retry hữu ích khi lỗi thoáng qua. Nhưng nếu dependency liên tục lỗi hoặc latency tăng mạnh, tiếp tục gửi request chỉ làm client giữ thêm connection và worker, đồng thời tăng tải lên backend. Circuit breaker theo dõi kết quả gọi dependency và tạm chặn request khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng.

Circuit breaker thường có ba trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Lỗi hoặc slow-call vượt ngưỡng
    OPEN --> HALF_OPEN: Hết thời gian chờ
    HALF_OPEN --> CLOSED: Probe thành công
    HALF_OPEN --> OPEN: Probe tiếp tục thất bại
~~~

- **CLOSED:** request được phép đi qua; breaker ghi nhận kết quả và thời gian.
- **OPEN:** request bị từ chối nhanh mà không gọi dependency; ứng dụng có thể trả lỗi, dùng cache hoặc đưa công việc vào queue.
- **HALF_OPEN:** sau thời gian chờ, chỉ một số lượng probe giới hạn được phép đi qua để kiểm tra dependency đã phục hồi chưa.

Một số thư viện có thêm trạng thái như `METRICS_ONLY`, `DISABLED` hoặc `FORCED_OPEN`. Ý nghĩa và cách vận hành phụ thuộc thư viện.

### 7.2. Cấu hình circuit breaker

Các tham số quan trọng gồm:

| Tham số | Mục đích |
|---|---|
| Sliding window | Số request gần nhất hoặc khoảng thời gian dùng để tính tỷ lệ |
| Minimum number of calls | Số mẫu tối thiểu trước khi đánh giá tỷ lệ lỗi |
| Failure rate threshold | Tỷ lệ lỗi khiến breaker chuyển OPEN |
| Slow call duration threshold | Thời gian một call được xem là chậm |
| Slow call rate threshold | Tỷ lệ call chậm khiến breaker mở |
| Wait duration in OPEN | Thời gian giữ breaker ở OPEN trước khi cho probe |
| Permitted calls in HALF_OPEN | Số probe được phép thực hiện |
| Record/ignore exceptions | Phân loại lỗi được tính vào failure rate |

Không bật breaker với ngưỡng quá nhạy. Một service ít request có thể chưa đủ mẫu để tính tỷ lệ lỗi; một lỗi xác thực hoặc tham số sai không phản ánh tình trạng sức khỏe của dependency. Hãy ghi nhận lỗi mạng, timeout và lỗi server có tính tạm thời; phân loại riêng lỗi quota, lỗi nghiệp vụ và lỗi cấu hình.

Circuit breaker thường được tạo riêng cho một dependency hoặc nhóm method có cùng failure domain. Không dùng một breaker chung cho mọi Google Cloud APIs: Cloud Storage có thể khỏe trong khi Compute Engine gặp sự cố. Mở breaker toàn cục sẽ chặn cả những dịch vụ vẫn hoạt động bình thường.

### 7.3. Circuit breaker không phải bulkhead hoặc rate limiter

Ba cơ chế có mục đích khác nhau:

- Circuit breaker ngừng gọi một dependency đang có dấu hiệu không khỏe.
- Rate limiter giới hạn tốc độ request được gửi đi.
- Bulkhead giới hạn số tác vụ đồng thời để một dependency không chiếm hết worker hoặc connection của ứng dụng.

Circuit breaker không tự giới hạn số call đang chạy. Thư viện Resilience4j cũng lưu ý rằng sliding window không phải giới hạn concurrency; muốn giới hạn số tác vụ đồng thời cần dùng Bulkhead.

## 8. Kết hợp timeout, retry, backoff và circuit breaker

Một thứ tự xử lý hợp lý cho một logical operation:

1. Caller xác định deadline end-to-end.
2. Circuit breaker kiểm tra dependency có đang OPEN không.
3. Nếu được phép, client library thực hiện một attempt với timeout không vượt phần ngân sách còn lại.
4. Nếu lỗi thuộc nhóm retryable và thao tác idempotent, retry engine chờ backoff có jitter.
5. Trước mỗi lần thử, kiểm tra deadline, retry budget và trạng thái cancellation.
6. Kết quả cuối cùng được ghi nhận vào circuit breaker và telemetry.
7. Nếu thất bại, tầng nghiệp vụ quyết định trả lỗi, dùng cache, queue hoặc phương án degraded.

Khi circuit breaker bao quanh logical call đã có retry nội bộ, breaker thường ghi nhận kết quả cuối cùng của cả operation. Nếu đặt breaker bên trong retry decorator, breaker có thể ghi nhận từng attempt và mở mạch trong khi retry của cùng operation vẫn đang chạy. Chọn thứ tự theo mục tiêu đo lường và kiểm thử hành vi thực tế.

Không tạo nhiều lớp retry chồng nhau. Ví dụ, nếu GAX đã thực hiện 4 attempts, một retry wrapper bên ngoài có thể khiến số lần gọi tăng thêm nhiều lần. Hãy kiểm tra cấu hình mặc định của client trước khi thêm retry ở application layer.

## 9. Cấu hình retry trong Google Cloud Java Client Libraries

### 9.1. Hiểu cấu hình mặc định trước khi thay đổi

Cloud Client Libraries for Java dùng GAX để cấu hình retry. Default retry được đội ngũ của từng dịch vụ chọn theo từng RPC. Một service có thể bật retry cho một số method và tắt cho method khác. Cấu hình retryable status code và các giới hạn thời gian nằm trong generated `*StubSettings`.

`RetrySettings` thường có các tham số:

- `initialRetryDelayDuration`: thời gian chờ ban đầu.
- `retryDelayMultiplier`: hệ số tăng backoff.
- `maxRetryDelayDuration`: giới hạn thời gian chờ.
- `initialRpcTimeoutDuration`: timeout của attempt đầu.
- `rpcTimeoutMultiplier`: hệ số thay đổi timeout giữa các attempt.
- `maxRpcTimeoutDuration`: giới hạn timeout mỗi attempt.
- `totalTimeoutDuration`: tổng thời gian tối đa cho operation.
- `maxAttempts`: giới hạn số lần gọi.

GAX tách giới hạn cho từng RPC attempt và giới hạn cho toàn bộ operation. Khi cấu hình retry, phải đặt `totalTimeoutDuration` hoặc `maxAttempts` để tránh retry không giới hạn. Jitter được bật trong cơ chế retry của Cloud Client Libraries for Java.

### 9.2. Ví dụ cấu hình cho một RPC

Đoạn mã sau minh họa cấu hình retry cho RPC `listAssets` của Cloud Asset API. Đây là ví dụ về cách thiết lập cho một method cụ thể; retryable code và thời gian thực tế phải được đối chiếu với tài liệu của API đang gọi.

~~~java
import com.google.api.gax.retrying.RetrySettings;
import com.google.api.gax.rpc.StatusCode;
import com.google.cloud.asset.v1.AssetServiceClient;
import com.google.cloud.asset.v1.AssetServiceSettings;
import com.google.cloud.asset.v1.AssetServiceStubSettings;
import com.google.common.collect.ImmutableSet;

import java.time.Duration;

RetrySettings retrySettings =
    RetrySettings.newBuilder()
        .setInitialRetryDelayDuration(Duration.ofMillis(200))
        .setRetryDelayMultiplier(2.0)
        .setMaxRetryDelayDuration(Duration.ofSeconds(2))
        .setInitialRpcTimeoutDuration(Duration.ofSeconds(2))
        .setRpcTimeoutMultiplier(1.0)
        .setMaxRpcTimeoutDuration(Duration.ofSeconds(2))
        .setTotalTimeoutDuration(Duration.ofSeconds(8))
        .setMaxAttempts(4)
        .build();

AssetServiceStubSettings.Builder stubBuilder =
    AssetServiceStubSettings.newBuilder();

stubBuilder
    .listAssetsSettings()
    .setRetrySettings(retrySettings)
    .setRetryableCodes(
        ImmutableSet.of(StatusCode.Code.UNAVAILABLE)
    );

AssetServiceSettings settings =
    AssetServiceSettings.create(stubBuilder.build());

try (AssetServiceClient client = AssetServiceClient.create(settings)) {
    // Gọi client.listAssets(request) với request và scope phù hợp.
}
~~~

Trong ví dụ này, `UNAVAILABLE` được dùng để minh họa một lỗi dịch vụ tạm thời. Không sao chép nguyên danh sách retryable code này cho mọi RPC. Nếu method có thể trả quota exhaustion, hãy xem status code, quota guidance và cấu hình mặc định của method đó. Với thao tác không idempotent, không bật retry chỉ vì thấy mã lỗi có vẻ tạm thời.

### 9.3. Kiểm tra cấu hình thực tế của client

Trước khi ghi đè cấu hình:

1. Xác định phiên bản Cloud Client Library và GAX đang dùng.
2. Mở generated `*StubSettings` của client để xem retryable codes và `RetrySettings` mặc định.
3. Xác định method có idempotent hoặc conditional-idempotent không.
4. So sánh total timeout với deadline của request gọi đến.
5. Kiểm tra xem ứng dụng, HTTP transport hoặc service mesh có retry thêm lần nữa không.
6. Kiểm thử số lần gọi thực tế bằng log hoặc metric; không suy luận số attempts chỉ từ cấu hình vì jitter và total timeout có thể làm attempt cuối không được chạy.

Với Cloud Storage Java client, tài liệu có retry strategy riêng: non-idempotent calls không được retry tự động; một số thao tác conditionally idempotent chỉ được retry khi có điều kiện phù hợp. Ví dụ, `ifGenerationMatch`, `ifMetagenerationMatch` hoặc ETag có thể là điều kiện cần cho một số thao tác.

## 10. Circuit breaker trong ứng dụng Java

Cloud Client Libraries cung cấp retry settings cho RPC. Circuit breaker thường được triển khai ở tầng ứng dụng bằng một thư viện resilience như Resilience4j. Breaker giúp bảo vệ ứng dụng khỏi việc liên tục gọi một dependency đang chậm hoặc lỗi; nó không thay thế retry settings của GAX.

Ví dụ cấu hình minh họa:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import java.time.Duration;
import java.util.function.Supplier;

CircuitBreakerConfig breakerConfig =
    CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .slowCallRateThreshold(50)
        .slowCallDurationThreshold(Duration.ofSeconds(2))
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(3)
        .recordException(this::isTransientGcpFailure)
        .ignoreExceptions(IllegalArgumentException.class)
        .build();

CircuitBreaker breaker =
    CircuitBreaker.of("cloud-asset-api", breakerConfig);

// GAX client đã xử lý retry bên trong logical call.
Supplier<MyResult> protectedCall =
    CircuitBreaker.decorateSupplier(
        breaker,
        () -> invokeCloudAssetApi()
    );

MyResult result = protectedCall.get();
~~~

`MyResult`, `isTransientGcpFailure()` và `invokeCloudAssetApi()` đại diện cho kiểu dữ liệu và logic của ứng dụng. Trong triển khai thật, hãy phân loại exception theo status code của GAX/HTTP và bỏ qua lỗi validation hoặc lỗi nghiệp vụ không phản ánh sức khỏe của dependency.

Cấu hình mẫu dùng sliding window 20 calls, tối thiểu 10 mẫu, ngưỡng 50% và 3 probe khi HALF_OPEN. Đây chỉ là giá trị minh họa, không phải cấu hình production mặc định. Tuning phải dựa trên traffic, latency, SLO và thời gian phục hồi của API.

Nếu dùng Resilience4j Retry bên ngoài GAX, cần quyết định rõ tầng nào sở hữu retry. Không để cả hai lớp cùng retry cùng một lỗi mà không có giới hạn chung.

## 11. Tình huống thực hành: Cloud Run gọi Cloud Asset API

Một Cloud Run service nhận yêu cầu tạo inventory báo cáo cho một project. Service gọi Cloud Asset API để liệt kê tài nguyên rồi lưu kết quả vào Cloud Storage. Khi lượng request tăng, Cloud Asset API bắt đầu trả `429` và đôi lúc `UNAVAILABLE`.

### Triệu chứng

- p95 latency của endpoint tăng từ dưới một giây lên nhiều giây.
- Tỷ lệ `429` tăng theo số instance Cloud Run.
- Số request đến Cloud Asset API cao hơn nhiều so với số yêu cầu tạo báo cáo.
- Nhiều request vẫn đang chờ khi người dùng đã đóng trang hoặc hết deadline.
- Retry làm số request tăng thêm và quota càng khó phục hồi.

### Cách xử lý

1. **Đo đúng dependency:** tách latency và error rate của Cloud Asset API khỏi latency của Cloud Run endpoint. Ghi nhận method, project, status code, attempt count và trace ID.
2. **Đặt deadline:** xác định ngân sách end-to-end của báo cáo. Trừ thời gian đã dùng trước khi gọi Cloud Asset API và giới hạn total timeout của operation.
3. **Phân loại lỗi:** retry `UNAVAILABLE` khi thao tác đọc an toàn; với `429`, giảm concurrency, đọc quota guidance và áp dụng khoảng chờ theo tài liệu API.
4. **Giảm tải:** cache dữ liệu inventory nếu yêu cầu freshness cho phép, gom request theo lịch hoặc chuyển báo cáo sang background job thay vì giữ request HTTP mở lâu.
5. **Kiểm tra idempotency:** `listAssets` là thao tác đọc nên có thể lặp lại; nếu workflow tạo export operation, lưu operation name để không tạo lại tác vụ khi response bị mất.
6. **Giới hạn retry:** đặt max attempts, total timeout và retry budget. Chỉ một tầng chịu trách nhiệm retry RPC.
7. **Mở circuit breaker:** nếu tỷ lệ lỗi hoặc slow call vượt ngưỡng, tạm dừng lời gọi mới đến Cloud Asset API. Trả trạng thái đang xử lý, dùng dữ liệu cache hoặc đưa job vào queue tùy yêu cầu nghiệp vụ.
8. **Probe có kiểm soát:** khi breaker HALF_OPEN, cho phép số lượng nhỏ request đọc thử. Nếu thành công ổn định, đóng breaker; nếu tiếp tục lỗi, mở lại.
9. **Xác minh phục hồi:** theo dõi tỷ lệ 429/503, retry rate, p95/p99 và số request đang chờ. Chỉ tăng concurrency khi quota và backend có đủ khả năng.

### Kết quả mong đợi

Cloud Run không giữ request vô hạn; số lần gọi API có giới hạn; retry được phân tán theo thời gian; quota không bị khuếch đại bởi nhiều tầng; dependency lỗi được cô lập; người dùng nhận response hoặc trạng thái xử lý trong ngân sách đã xác định.

## 12. Theo dõi và cảnh báo trong vận hành

Không thể đánh giá retry/circuit breaker chỉ bằng việc endpoint cuối cùng trả HTTP 200. Cần đo cả số lần thử, độ trễ và trạng thái dependency.

Các metric nên theo dõi:

| Metric | Ý nghĩa vận hành |
|---|---|
| Request count theo API/method/status | Nhận biết lưu lượng và mã lỗi đang tăng |
| Attempt count / retries per logical operation | Phát hiện retry amplification |
| First-attempt success rate | Đo mức độ ổn định trước khi retry |
| Attempt latency và total operation latency | Phân biệt một attempt chậm với nhiều attempt |
| Timeout và `DEADLINE_EXCEEDED` | Phát hiện ngân sách thời gian không phù hợp hoặc dependency chậm |
| `429` / `RESOURCE_EXHAUSTED` | Theo dõi quota và rate limit |
| `5xx` / `UNAVAILABLE` | Theo dõi lỗi dịch vụ tạm thời |
| Circuit breaker state và rejected calls | Biết khi nào dependency đang bị cô lập |
| Retry budget remaining / retry denied | Kiểm tra cơ chế bảo vệ có đang hoạt động |
| In-flight calls và queue depth | Phát hiện worker hoặc connection bị chiếm dụng |

Nên phân tách metric theo service, method, project và region khi cardinality cho phép. Không đưa user ID, resource ID có độ đa dạng cao hoặc secret vào label metric. Dùng structured logs và trace để điều tra một logical operation xuyên qua nhiều lần gọi.

Cloud Monitoring có thể hiển thị metric và cảnh báo khi error rate, latency, quota usage hoặc số call bị từ chối vượt ngưỡng. OpenTelemetry có thể bổ sung span cho từng attempt, thuộc tính `retry.attempt`, trạng thái breaker và thời gian backoff. Không ghi access token, API key, nội dung secret hoặc payload nhạy cảm vào log.

Cảnh báo nên tập trung vào tác động đến SLO. Ví dụ: tỷ lệ request quá deadline tăng, retry ratio tăng liên tục, quota gần cạn, breaker OPEN kéo dài hoặc một dependency không phục hồi sau nhiều chu kỳ HALF_OPEN. Một số retry đơn lẻ là bình thường; retry tăng nhanh cùng latency và error rate là dấu hiệu cần điều tra.

## 13. Kiểm thử khả năng chịu lỗi

Trước khi phát hành, kiểm thử các tình huống có thể xảy ra:

- API phản hồi chậm hơn attempt timeout.
- Kết nối bị reset trước khi nhận response.
- Server xử lý thành công nhưng response bị mất.
- API trả `429`, `500`, `503` hoặc status không được retry.
- Caller hủy request giữa thời gian backoff.
- Deadline hết trước khi có thể chạy attempt tiếp theo.
- Retry budget cạn.
- Circuit breaker chuyển OPEN khi dependency lỗi và HALF_OPEN khi phục hồi.
- Một instance lỗi trong khi các instance khác vẫn hoạt động.
- Client restart giữa lúc theo dõi long-running operation.

Kiểm tra rằng retry không lặp side effect, không vượt deadline và không tạo đợt request đồng bộ. Với breaker, kiểm tra lỗi validation/permission không làm mạch mở sai, và một API lỗi không chặn các API GCP độc lập.

Có thể dùng mock server, fault injection hoặc môi trường thử nghiệm để mô phỏng lỗi. Khi chạy load test, quan sát cả hệ thống gọi API và dependency; một bài test chỉ đo response của frontend có thể bỏ sót số lần gọi tăng ở phía sau.

## 14. Checklist thiết kế cho một GCP API call

Trước khi đưa lời gọi API vào production, hãy xác nhận:

- [ ] Đã xác định deadline end-to-end và ngân sách thời gian còn lại cho API call.
- [ ] Attempt timeout và total timeout được cấu hình riêng, không vượt deadline của caller.
- [ ] Đã phân loại lỗi retryable theo tài liệu của đúng API và đúng RPC.
- [ ] Đã xác định thao tác idempotent, conditional-idempotent hay non-idempotent.
- [ ] Có request ID, precondition, ETag hoặc cách tra cứu trạng thái khi cần chống tạo trùng.
- [ ] Exponential backoff có giới hạn trên và jitter.
- [ ] Tôn trọng Retry-After, RetryInfo, quota guidance hoặc khoảng chờ của API.
- [ ] Có max attempts, total timeout và retry budget.
- [ ] Chỉ một tầng sở hữu retry cho mỗi RPC.
- [ ] Circuit breaker ghi nhận đúng lỗi và được tách theo dependency.
- [ ] Có rate limiter hoặc bulkhead khi cần kiểm soát tốc độ và concurrency.
- [ ] Có fallback hoặc cách xử lý khi breaker OPEN.
- [ ] Metric, log và trace thể hiện logical operation lẫn từng attempt.
- [ ] Đã kiểm thử timeout, mất response, quota, retry và phục hồi breaker.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một timeout 5 giây được đặt lại ở từng tầng có thể khiến request vượt deadline 5 giây của người dùng?
2. Khi Cloud API trả `429`, vì sao tăng số lần retry có thể làm tình hình quota xấu hơn?
3. Một request tạo resource bị timeout nhưng server có thể đã xử lý thành công. Bạn cần dùng cơ chế nào trước khi gửi lại?
4. Exponential backoff và jitter giải quyết hai vấn đề khác nhau nào?
5. Vì sao retry ở frontend, backend và GAX client cùng lúc có thể tạo ra nhiều lần gọi hơn dự kiến?
6. Circuit breaker ở trạng thái OPEN nên xử lý request mới như thế nào? Khi nào chuyển sang HALF_OPEN?
7. Vì sao circuit breaker không thể thay thế bulkhead hoặc rate limiter?
8. Khi nào nên để GAX client library retry và khi nào workflow ở tầng ứng dụng cần quản lý retry riêng?
9. Với long-running operation, vì sao retry lệnh bắt đầu operation khác với retry lệnh poll?
10. Những metric nào giúp phân biệt lỗi dependency thực sự với retry amplification?

## Tài liệu tham khảo

- [Configure client-side retries for Java Cloud Client Libraries](https://docs.cloud.google.com/java/docs/client-retries)
- [GAX RetrySettings reference](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.retrying.RetrySettings)
- [Cloud Storage retry strategy](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Cloud Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Service Usage API troubleshooting and retry intervals](https://docs.cloud.google.com/service-usage/docs/troubleshooting)
- [Troubleshoot the Cloud Monitoring API](https://docs.cloud.google.com/monitoring/api/troubleshooting)
- [gRPC deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC retry](https://grpc.io/docs/guides/retry/)
- [Google SRE Book: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)

