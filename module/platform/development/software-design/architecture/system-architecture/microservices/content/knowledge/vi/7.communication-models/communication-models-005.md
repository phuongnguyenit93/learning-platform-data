# Luồng người dùng tương tác trực tiếp và công việc nền

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Mô hình giao tiếp  
> **Trọng tâm:** Tách trải nghiệm cần phản hồi ngay của người dùng khỏi những công việc có thể chạy sau, đồng thời giữ tính đúng đắn nghiệp vụ, khả năng theo dõi tiến độ, xử lý lỗi và vận hành đáng tin cậy trong kiến trúc phân tán.

## 1. Bài toán: mọi thao tác đều có hai loại thời gian

Người dùng nhấn nút để đạt một mục đích: gửi biểu mẫu, mua hàng, tạo báo cáo, tải video hoặc nhập dữ liệu. Họ cần biết **hệ thống đã tiếp nhận yêu cầu hay chưa**, **kết quả đã hoàn tất hay chưa**, và **phải làm gì tiếp theo**. Ba câu hỏi này không phải lúc nào cũng cần trả lời trong một HTTP request.

Một số hành vi cần kết quả tức thì để người dùng tiếp tục thao tác: đăng nhập, xem giá, kiểm tra số dư, xác nhận đầu vào, đọc danh sách sản phẩm. Các hành vi khác mất lâu, phụ thuộc hệ thống ngoài hoặc có thể chạy sau: xử lý video, lập báo cáo lớn, gửi hàng nghìn email, import dữ liệu, xây lại chỉ mục tìm kiếm, xử lý ảnh, đồng bộ dữ liệu đối tác.

Nếu giữ kết nối người dùng mở trong suốt công việc dài, hệ thống có thể gặp timeout, tiêu tốn connection/thread, khó retry và gây cảm giác ứng dụng “đứng”. Nếu đẩy mọi thứ xuống nền mà không có mô hình trạng thái, người dùng lại dễ nhầm “đã gửi yêu cầu” thành “đã thành công”.

Mục tiêu của thiết kế là chọn đúng **ranh giới giữa tương tác trực tiếp và xử lý nền**, rồi định nghĩa rõ giao kèo, trạng thái, thông báo, lỗi và quyền sở hữu nghiệp vụ.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt luồng đồng bộ request–response, công việc bất đồng bộ, event-driven reaction và workflow dài.
- Xác định hành vi cần phản hồi ngay, hành vi có thể chuyển xuống nền, và điều kiện không nên tách.
- Thiết kế API tạo job, lấy trạng thái, theo dõi tiến độ, truy xuất kết quả, retry và hủy.
- Dùng queue/worker để giới hạn tải, chịu lỗi, tránh mất yêu cầu, xử lý trùng và quan sát hệ thống.
- Nhận biết vấn đề consistency, giao dịch, thứ tự, bảo mật và trải nghiệm người dùng khi xử lý phân tán.
- Lựa chọn polling, push notification, webhook, orchestration hoặc choreography phù hợp với từng bối cảnh.

## 2. Phân biệt hai luồng bằng trách nhiệm và kỳ vọng

### 2.1. Luồng tương tác trực tiếp (interactive flow)

Đây là hành trình người dùng đang **chờ phản hồi** để đưa ra quyết định hoặc thực hiện thao tác kế tiếp. Thường bắt đầu từ web/mobile/API client, đi qua gateway/BFF/application service, rồi trả HTTP response hoặc thông điệp tương đương.

Ví dụ:

- Đăng nhập và nhận kết quả xác thực.
- Xem giỏ hàng với giá hiện hành.
- Kiểm tra mã ưu đãi có hợp lệ để hiển thị ngay.
- Bấm “Lưu bản nháp” và cần biết dữ liệu đã lưu.
- Kiểm tra quyền truy cập trước khi mở tài liệu.

Đặc điểm quan trọng không phải “chạy nhanh” theo một ngưỡng tuyệt đối, mà là **người dùng cần kết quả trong cùng vòng tương tác**. Luồng có thể đồng bộ qua HTTP/gRPC, nhưng phải có giới hạn thời gian hợp lý và phản hồi thất bại rõ ràng.

### 2.2. Công việc nền (background job)

Công việc nền là thao tác không cần giữ vòng chờ trực tiếp của người dùng cho tới lúc hoàn thành. Nó có thể được khởi tạo bởi người dùng, sự kiện nghiệp vụ, lịch chạy, tác vụ hệ thống hoặc một bước workflow.

Ví dụ:

- Chuyển đổi video sang nhiều độ phân giải.
- Tạo báo cáo Excel/PDF từ dữ liệu lớn.
- Nhập một tệp CSV hàng trăm nghìn dòng.
- Gửi thông báo sau khi giao dịch đã được ghi nhận.
- Đối soát thanh toán cuối ngày.
- Tạo thumbnail sau khi người dùng tải ảnh lên.

Một background job thường cần **định danh**, **trạng thái**, **cơ chế thực thi**, **xử lý thất bại** và **khả năng truy vết**. “Chạy ở thread khác trong web server” chưa chắc là thiết kế công việc nền đáng tin cậy: nếu process restart, công việc có thể biến mất.

### 2.3. Luồng lai (hybrid flow)

Rất nhiều quy trình cần làm một phần ngay, phần còn lại sau:

1. Nhận và kiểm tra đầu vào.
2. Xác thực người dùng, quyền và quota.
3. Ghi lại yêu cầu một cách bền vững.
4. Trả ngay một phản hồi xác nhận tiếp nhận cùng mã theo dõi.
5. Để worker hoàn thành công việc và cập nhật trạng thái.
6. Cho người dùng kiểm tra kết quả hoặc nhận thông báo.

Ví dụ, người dùng yêu cầu xuất báo cáo. API xác nhận rằng yêu cầu hợp lệ và job đã được tạo; vài phút sau mới có tệp để tải. Phản hồi “Đã nhận yêu cầu” **khác** “Đã tạo báo cáo thành công”.

## 3. Chọn đồng bộ hay bất đồng bộ theo tiêu chí nào?

Không chọn async chỉ vì tác vụ nghe có vẻ phức tạp. Cần đánh giá việc người dùng có phải đợi hay không, mức độ trễ, tính đúng đắn và ảnh hưởng của việc chạy muộn.

| Tiêu chí | Nghiêng về phản hồi đồng bộ | Nghiêng về background job |
| --- | --- | --- |
| Kỳ vọng người dùng | Cần quyết định ngay trước hành động kế | Có thể rời màn hình và xem kết quả sau |
| Thời gian thực thi | Dự đoán được, đáp ứng ngân sách latency | Dài hoặc biến thiên lớn theo dữ liệu/tải |
| Phụ thuộc bên ngoài | Ít, có SLA và timeout rõ | Nhiều API ngoài, dễ chậm, cần retry |
| Khối lượng xử lý | Nhỏ, tài nguyên giới hạn | Batch, CPU/GPU nặng, nhập/xuất khối lớn |
| Tính cần thiết | Kết quả quyết định ngay tính hợp lệ | Có thể trì hoãn sau một bước ghi nhận |
| Mô hình lỗi | Có thể trả lỗi trong cùng request | Cần lưu trạng thái, phục hồi và thông báo |
| Tải cao | Đáp ứng qua capacity đồng bộ | Có thể đệm bằng queue và giới hạn worker |
| Khả năng hủy | Thường request ngắn | Có thể yêu cầu cancel hoặc ngừng ở checkpoint |

Một tác vụ rất nhanh nhưng không quan trọng đối với phản hồi, như cập nhật analytics, có thể chạy nền. Một tác vụ khá tốn thời gian nhưng là điều kiện pháp lý/kinh doanh để chấp nhận giao dịch có thể yêu cầu chờ kết quả xác nhận hoặc hiển thị trạng thái pending thay vì hứa thành công.

### 3.1. Câu hỏi quyết định

- Người dùng cần nhìn thấy sự thật nào **trước khi tiếp tục**?
- Việc chậm 1–5 giây, 30 giây hoặc vài phút ảnh hưởng gì đến trải nghiệm?
- Hệ thống có cam kết chắc rằng công việc được lưu và sẽ được thử thực hiện không?
- Nếu job thất bại sau khi API đã phản hồi, ai biết và ai xử lý?
- Người dùng có thể gửi lại cùng yêu cầu? Tránh tạo nhiều job/hóa đơn thế nào?
- Nếu một bước chạy nền mất vài giờ, dữ liệu đầu vào có còn hợp lệ?
- Có quyền hủy hoặc sửa job khi đang chạy không?
- Cần bảo đảm thứ tự thực hiện, giới hạn tốc độ hay deadline không?

Nên viết một quyết định rõ ràng cho từng use case: **đầu vào được chấp nhận khi nào, phản hồi ngay nói điều gì, kết quả cuối được xác nhận khi nào, ai chịu trách nhiệm xử lý lỗi**.

## 4. Các mô hình giao tiếp thường gặp

### 4.1. Đồng bộ request–response

~~~text
Người dùng        Web/API          Domain service
    |                |                    |
    |-- yêu cầu ---->|-- xử lý ---------->|
    |                |<---- kết quả -------|
    |<-- phản hồi ---|                    |
~~~

Dùng cho thao tác ngắn, cần thông tin ngay. Phải đặt timeout theo ngân sách latency end-to-end; hệ thống có thể trả lỗi hoặc trạng thái tạm thời khi phụ thuộc quá chậm.

**Sai lầm thường gặp:** cho rằng “đặt timeout 30 giây” là giải quyết được công việc kéo dài 5 phút. Timeout chỉ giới hạn thời gian đợi; không cho biết xử lý phía sau đã thực hiện hay chưa.

### 4.2. Nhận yêu cầu → tạo job → xử lý nền

~~~text
Người dùng       API             DB/Outbox         Queue            Worker
    |             |                 |                |                |
    |-- tạo ------>|                 |                |                |
    |             |-- lưu job ------>|                |                |
    |<-- 202 + id--|                 |                |                |
    |             |                 |-- phát job ---->|                |
    |             |                 |                |-- giao ------->|
    |             |                 |                |                |-- chạy
    |             |                 |<------- cập nhật trạng thái -----|
    |-- GET status ---------------->|                |                |
    |<-- RUNNING / SUCCEEDED ------|                |                |
~~~

Công việc được ghi nhận bền vững trước khi trả lời “accepted”. Queue có thể tách nhịp nhận yêu cầu khỏi nhịp xử lý. Người dùng không cần giữ một kết nối mở suốt thời gian chạy.

### 4.3. Xử lý hậu sự kiện

~~~text
Order service --(OrderPlaced)--> Event broker
                                  |          |
                                  v          v
                          Email consumer   Analytics consumer
~~~

Một sự kiện là **sự thật đã xảy ra**. Các consumer độc lập có thể tạo thông báo, cập nhật chỉ mục hoặc ghi analytics. Luồng này hữu ích khi bên phát không cần chờ phản ứng của từng subscriber để công bố kết quả nghiệp vụ.

Tuy vậy, không nên biến những bước bắt buộc để quyết định đơn hàng hợp lệ thành việc “fire-and-forget” không ai giám sát. Phải phân biệt phần quyết định cốt lõi với các tác dụng phụ có thể xử lý sau.

### 4.4. Workflow nhiều bước kéo dài

~~~text
[Đặt hàng]
     |
[Giữ tồn kho] -- thất bại --> [Hủy/giải phóng]
     |
[Thanh toán] -- thất bại --> [Giải phóng tồn]
     |
[Chuẩn bị giao] -- lỗi --> [Xử lý ngoại lệ]
     |
[Hoàn tất]
~~~

Đây không đơn thuần là một job chạy dài. Nó có nhiều tác nhân, deadline, hành động bù và trạng thái nghiệp vụ. Có thể cần **process manager, saga hoặc workflow engine**. Mỗi bước có thể được thực thi bởi worker, nhưng toàn bộ workflow phải có một nơi chịu trách nhiệm theo dõi tiến trình và kết quả cuối.

## 5. Phân biệt command, job và event

Ba khái niệm thường đi chung trong kiến trúc bất đồng bộ nhưng có ý nghĩa khác nhau.

| Khái niệm | Ví dụ | Ngữ nghĩa |
| --- | --- | --- |
| **Command** | GenerateMonthlyReport | Yêu cầu một bên thực hiện hành động; có thể từ chối |
| **Job/task** | ReportJob #581, status QUEUED | Bản ghi công việc cần được thực thi và theo dõi |
| **Domain event** | MonthlyReportGenerated | Sự thật nghiệp vụ đã xảy ra |
| **Integration event** | ReportReadyV1 | Hợp đồng công bố thông tin hữu ích sang hệ khác |
| **Scheduled trigger** | 01:00 mỗi ngày | Điều kiện thời gian để tạo lệnh/job, chưa phải kết quả |

Một yêu cầu GenerateMonthlyReport có thể tạo job; worker thực thi; khi hoàn tất, hệ thống ghi nhận sự kiện ReportGenerated. Không nên gọi job là event đã xảy ra, vì điều đó làm consumer nhầm “đã yêu cầu” với “đã hoàn thành”.

Queue có thể chở command, thông báo event hoặc tín hiệu gọi job. **Cấu trúc message và ý nghĩa nghiệp vụ** mới quyết định cách xử lý, không phải việc dùng RabbitMQ, Kafka, SQS hay database queue.

## 6. Thiết kế một API tạo công việc nền

Hãy xét tính năng “Xuất báo cáo doanh thu”. Người dùng chọn khoảng thời gian và nhấn “Tạo báo cáo”. Thời gian chạy có thể từ vài giây tới nhiều phút.

### 6.1. Phản hồi nhận yêu cầu

~~~http
POST /v1/report-jobs
Authorization: Bearer <token>
Idempotency-Key: 12f6a1a3-req-001
Content-Type: application/json

{
  "reportType": "revenue",
  "from": "2026-10-01",
  "to": "2026-10-31",
  "format": "csv"
}
~~~

Nếu request hợp lệ và job đã được ghi bền vững, API có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/report-jobs/job-8b72
Content-Type: application/json

{
  "jobId": "job-8b72",
  "status": "QUEUED",
  "statusUrl": "/v1/report-jobs/job-8b72",
  "submittedAt": "2026-11-11T08:30:00Z"
}
~~~

Mã HTTP 202 nghĩa là **yêu cầu đã được chấp nhận để xử lý**, không bảo đảm xử lý đã xong. Trước khi trả 202, hệ thống cần xác nhận đã lưu đủ thông tin để có thể phục hồi hoặc phát hành công việc về sau; nếu chỉ gọi hàm enqueue không chắc chắn, cần làm rõ semantics của thao tác đó.

Nếu request không hợp lệ, hãy trả lỗi đồng bộ phù hợp (ví dụ 400/422 tùy contract). Nếu người dùng không có quyền, trả 403; nếu vượt quota, trả 429 hoặc lỗi nghiệp vụ phù hợp. Không tạo job cho đầu vào chắc chắn phải từ chối chỉ để worker báo lỗi muộn.

### 6.2. Truy vấn trạng thái

~~~http
GET /v1/report-jobs/job-8b72

HTTP/1.1 200 OK
Content-Type: application/json

{
  "jobId": "job-8b72",
  "status": "RUNNING",
  "phase": "aggregating",
  "progress": {
    "processed": 7200,
    "estimatedTotal": 12000
  },
  "createdAt": "2026-11-11T08:30:00Z",
  "startedAt": "2026-11-11T08:30:05Z",
  "updatedAt": "2026-11-11T08:30:22Z"
}
~~~

Khi hoàn tất:

~~~json
{
  "jobId": "job-8b72",
  "status": "SUCCEEDED",
  "result": {
    "downloadUrl": "/v1/report-jobs/job-8b72/download",
    "expiresAt": "2026-11-18T08:30:00Z"
  },
  "finishedAt": "2026-11-11T08:31:47Z"
}
~~~

Tệp kết quả có thể nằm trong object storage và được tải qua endpoint kiểm tra quyền hoặc một URL ký ngắn hạn. Không nên công khai đường dẫn dễ đoán mà thiếu xác thực.

### 6.3. Thông báo lỗi

~~~json
{
  "jobId": "job-8b72",
  "status": "FAILED",
  "error": {
    "code": "DATA_SOURCE_UNAVAILABLE",
    "message": "Không thể lấy dữ liệu báo cáo.",
    "retryable": true
  },
  "finishedAt": "2026-11-11T08:33:10Z"
}
~~~

Thông điệp trả cho người dùng nên có ý nghĩa và tránh rò chi tiết hạ tầng/secret. Log nội bộ giữ trace ID, nguyên nhân và stack trace; không trả thông tin nhạy cảm qua public API.

### 6.4. Tính bất biến của request và idempotency

Các trường của yêu cầu đã nhận thường nên được lưu cùng job. Nếu user thay đổi bộ lọc trên giao diện sau khi tạo job, job hiện tại vẫn chạy theo phiên bản input đã được chấp nhận; thao tác mới tạo job mới.

Client có thể gửi lại POST do mất mạng. Một **Idempotency-Key** hợp lệ trong phạm vi chủ thể, endpoint và thời hạn đã công bố có thể trả về cùng job cho cùng nội dung request, tránh tạo hai báo cáo tương đương hoặc hai hành động có tác dụng phụ. Nếu cùng khóa nhưng payload khác, nên có kết quả lỗi xung đột rõ ràng, không âm thầm tái sử dụng.

Idempotency của API và idempotency của worker là **hai lớp khác nhau**: API tránh tạo job trùng do client retry; worker tránh thực hiện tác dụng phụ trùng khi message được giao nhiều lần.

## 7. Mô hình trạng thái công việc

Trạng thái không chỉ phục vụ giao diện; nó là hợp đồng quan sát và điều phối.

~~~text
CREATED
   |
   v
QUEUED --------> CANCELLED
   |
   v
RUNNING -------> SUCCEEDED
   |  \
   |   +-------> FAILED (terminal)
   |
   +-----------> RETRY_WAIT ---> QUEUED
   |
   +-----------> CANCEL_REQUESTED ---> CANCELLED
~~~

Một mô hình khác có thể gộp CREATED và QUEUED, hoặc biểu diễn FAILED_RETRYABLE tách khỏi FAILED_PERMANENT. Quy tắc chuyển trạng thái phải rõ ràng và tránh các chuyển đổi bất hợp lệ.

| Trạng thái | Ý nghĩa với hệ thống | Thông điệp với người dùng |
| --- | --- | --- |
| CREATED/QUEUED | Đã ghi nhận và đang chờ nhận worker | Đã nhận yêu cầu |
| RUNNING | Đang thực hiện một attempt | Đang xử lý |
| RETRY_WAIT | Lỗi tạm thời, chờ thử lại | Tạm gián đoạn, hệ thống đang thử lại |
| SUCCEEDED | Kết quả đầu cuối được xác nhận | Hoàn thành, có thể xem/tải |
| FAILED | Hết khả năng thử lại tự động hoặc lỗi không phục hồi | Không hoàn thành; có hướng xử lý |
| CANCEL_REQUESTED | Đã nhận lệnh hủy nhưng tác vụ chưa dừng hẳn | Đang hủy |
| CANCELLED | Đã ngừng theo contract và xử lý hậu quả cần thiết | Đã hủy |
| EXPIRED | Kết quả hoặc quyền truy cập đã hết hạn | Cần tạo yêu cầu mới hoặc liên hệ hỗ trợ |

**Job** và **attempt** không phải một: job giữ định danh và mục tiêu ổn định, attempt là một lần worker thực thi. Sau lỗi tạm thời, job có thể chạy nhiều attempt mà không biến thành nhiều yêu cầu nghiệp vụ khác nhau.

Nên lưu tối thiểu:

- Job ID, owner/tenant, loại công việc và tham chiếu input.
- Trạng thái, thời điểm tạo/bắt đầu/kết thúc/cập nhật.
- Số attempt, next retry time và lỗi được chuẩn hóa.
- Correlation ID, trace ID, thông tin audit phù hợp.
- Result reference và chính sách thời hạn lưu.
- Version của job schema/handler khi cần xử lý job cũ sau deploy.

Với tiến độ, nên dùng số đơn vị đã xử lý (dòng CSV, file, bước công việc) nếu có thể đo. Nếu tổng khối lượng chưa biết, hiển thị **giai đoạn đang làm** thay vì phần trăm tưởng tượng.

## 8. Kịch bản trọn vẹn: nhập CSV hàng trăm nghìn dòng

Giả sử quản trị viên tải tệp CSV chứa 500.000 sản phẩm. Mỗi dòng phải được kiểm tra và ghi vào catalog. Đây là ví dụ điển hình cho luồng lai.

### 8.1. Luồng người dùng

1. User chọn file và nhấn “Nhập sản phẩm”.
2. Client upload trực tiếp lên object storage bằng cơ chế có kiểm soát hoặc gửi qua API hỗ trợ multipart.
3. API xác thực quyền, kích thước, loại tệp và quota; tạo bản ghi import với input reference.
4. API trả mã import job và trạng thái QUEUED.
5. UI điều hướng sang “Lịch sử nhập” để theo dõi tiến độ mà không giữ kết nối POST.
6. Worker đọc tệp theo lô, validate từng dòng, áp dụng chính sách duplicate và ghi dữ liệu.
7. Kết quả tổng hợp số dòng thành công/thất bại, file lỗi theo dòng và thời gian kết thúc.
8. User tải báo cáo lỗi rồi sửa và import tiếp nếu cần.

### 8.2. Luồng kiến trúc

~~~text
[Admin UI]
    |
    | 1. Upload / create import
    v
[Import API] ---------> [Object Storage: input.csv]
    |
    | 2. DB transaction
    v
[Import DB: ImportJob] + [Outbox: ImportRequested]
    |
    | 3. Outbox relay
    v
[Queue: import-jobs]
    |
    v
[Import Worker Pool]
    |-- đọc tệp theo stream/chunk
    |-- validate schema + quy tắc nghiệp vụ
    |-- ghi theo batch / checkpoint
    |-- lưu lỗi theo dòng
    v
[Import DB: progress + result]
    |
    +---- [Object Storage: error-report.csv]
    |
    v
[Status API / notifications]
    |
    v
[Admin UI]
~~~

Không cần dùng toàn bộ các thành phần này cho ứng dụng nhỏ. Nếu tần suất nhập thấp, một database-backed job queue có thể là đủ. Nhưng dù chọn công nghệ nào, hệ thống cần biết làm sao **không mất việc đã nhận** và **không nhập trùng ngoài ý muốn**.

### 8.3. Quyết định nghiệp vụ phải xác nhận

- Nếu 10% dòng lỗi, nhập 90% dòng còn lại hay rollback toàn bộ?
- Nếu cùng sản phẩm xuất hiện hai lần trong một file, lấy bản ghi nào?
- Nếu file nhập lại, có ghi đè dữ liệu đã chỉnh thủ công không?
- Một file đã upload được giữ trong bao lâu và ai được tải?
- Nếu worker chết sau khi ghi được 200.000 dòng, tiếp tục từ đâu?
- User được phép hủy ở giữa chừng không? Hủy có xóa dữ liệu đã nhập hay chỉ dừng phần còn lại?
- Hai job của cùng tenant có được chạy song song nếu cùng cập nhật một catalog?
- Việc import có làm gián đoạn truy vấn tìm sản phẩm đang phục vụ người mua không?

Những quyết định này ảnh hưởng thiết kế checkpoint, transaction và trạng thái; không thể tự động giải quyết chỉ bằng việc thêm queue.

### 8.4. Ghi theo chunk và checkpoint

Thay vì đọc toàn bộ 500.000 dòng vào memory, worker có thể stream từng chunk, validate, ghi batch và cập nhật checkpoint sau các bước đã cam kết. Nếu một attempt bị mất, worker tiếp tục từ checkpoint an toàn hoặc xử lý lại các chunk theo cách idempotent.

Ví dụ:

~~~text
ImportJob:
  id = import-529
  status = RUNNING
  committedRows = 200000
  errors = 417
  checkpoint = chunk-40

Attempt:
  id = attempt-3
  leasedBy = worker-7
  leaseUntil = ...
~~~

**Checkpoint phải phản ánh dữ liệu đã được commit**, không đơn thuần là “đã đọc tới dòng N”. Nếu update checkpoint trước khi dữ liệu được ghi thành công, quá trình khôi phục có thể bỏ sót. Nếu dữ liệu commit trước khi checkpoint và worker chết giữa chừng, cần cơ chế ghi lặp an toàn.

## 9. Queue là bộ đệm tải, không phải phép màu

### 9.1. Thành phần và trách nhiệm

- **Producer:** tạo command/job message sau khi yêu cầu được chấp nhận.
- **Broker/queue:** giữ và chuyển message tới worker theo delivery semantics.
- **Worker/consumer:** lấy việc, thực thi và ghi kết quả.
- **Job store:** giữ trạng thái nghiệp vụ của công việc và thông tin kiểm tra.
- **Scheduler/retry manager:** đưa công việc trở lại trạng thái có thể chạy khi tới thời gian.
- **Status API:** cung cấp trạng thái có quyền truy cập để UI/client theo dõi.

Một broker có thể hỗ trợ nhiều khả năng tích hợp sẵn, nhưng không nên trông chờ broker lưu toàn bộ trạng thái người dùng cần xem trong nhiều ngày. Job state cần mô hình bền vững phù hợp với sản phẩm.

### 9.2. Đệm tải và giới hạn concurrency

Nếu 1.000 user đồng thời yêu cầu xuất báo cáo, hệ thống không cần chạy ngay 1.000 job CPU nặng. Queue nhận việc; pool worker chỉ chạy số công việc mà database và hạ tầng chịu được.

Cần kiểm soát:

- Worker concurrency theo loại job và tài nguyên thực tế.
- Queue backlog và tuổi của message cũ nhất.
- Số job mỗi tenant/user đang chạy hoặc đang chờ.
- Priority/fairness để job nhỏ không bị kẹt vô hạn sau job rất lớn.
- Giới hạn import/export để bảo vệ transaction path.
- Backpressure: khi quá tải cần trì hoãn, từ chối có hướng dẫn hoặc giảm tốc producer.

Queue dài không tự biến một hệ thống thiếu năng lực xử lý thành hệ thống ổn định; nó chỉ chuyển vấn đề “request chậm” thành “người dùng đợi job lâu”. Phải đo thời gian chờ và khả năng xử lý đầu ra.

### 9.3. Tính toán năng lực sơ bộ

Gọi:

- λ: số job tới trung bình mỗi giây.
- S: thời gian xử lý trung bình của một job (giây) trên một worker.
- c: số worker chạy song song hiệu quả.
- μ ≈ c/S: năng lực hoàn tất lý thuyết của pool (job/giây).

Ví dụ giả định: mỗi job mất trung bình 30 giây, có 10 worker, năng lực xấp xỉ 10/30 = 0,333 job/giây, khoảng 20 job/phút. Nếu công việc liên tục tới 1 job/giây, backlog sẽ tăng; queue không thể giải quyết nếu không giảm thời gian xử lý, tăng capacity hay thay chính sách nhận yêu cầu.

Công thức này là ước lượng đơn giản, bỏ qua I/O, phân phối thời gian chạy, retry và overhead. Muốn thiết kế thực tế phải kiểm tra tải, phân phối job size, p95 queue wait và nhu cầu theo mùa.

Với hệ ổn định, định luật Little cho biết **số công việc trung bình trong hệ ≈ tốc độ đến × thời gian trung bình ở trong hệ**. Nếu một service nhận nhiều job với thời gian chờ kéo dài, số job tồn sẽ tăng ngay cả khi CPU worker chưa đầy do lock hoặc giới hạn downstream.

### 9.4. Queue nào cho loại tác vụ nào?

| Tình huống | Cơ chế phù hợp để cân nhắc | Lưu ý |
| --- | --- | --- |
| Job đơn giản, tải nhỏ, một ứng dụng | Bảng DB + background worker hoặc job scheduler | Cần lock/lease, retry, dọn dữ liệu và HA phù hợp |
| Job task queue nhiều worker | Queue broker có ack, delay/retry và DLQ | Thiết kế idempotency và visibility/lease |
| Phản ứng với domain event | Event broker/pub-sub hoặc stream | Xử lý fan-out, schema, replay, thứ tự |
| Lịch chạy định kỳ | Scheduler + job store/queue | Tránh chạy trùng khi nhiều replica cùng tick |
| Workflow nhiều bước có chờ lâu | Process manager/workflow engine | Quản lý state, timeout, compensation, version |
| Tính toán CPU/GPU lớn | Worker pool chuyên biệt | Isolation, capacity, job placement, quotas |

Không có công cụ thắng trong mọi hệ thống. Chi phí vận hành broker, đội ngũ hiện có, semantics cần thiết và khối lượng thật quyết định lựa chọn.

## 10. Độ tin cậy: làm sao job đã nhận không biến mất?

### 10.1. Vấn đề ghi DB rồi phát message

Giả sử API làm hai thao tác:

~~~text
1. INSERT job status=QUEUED vào database
2. publish message ImportRequested vào queue
~~~

Nếu bước 1 thành công nhưng bước 2 thất bại, job nằm mãi ở QUEUED mà không có worker nhận. Đảo thứ tự cũng có vấn đề: broker nhận message nhưng DB chưa tạo job, worker không tìm thấy dữ liệu.

Không có transaction phân tán chung, không thể giả định hai thao tác này sẽ thành công hoặc rollback cùng nhau.

### 10.2. Transactional outbox

Một cách thường dùng:

~~~text
DB transaction:
  INSERT ImportJob(...)
  INSERT OutboxEvent(type="ImportRequested", payload=...)
COMMIT

Outbox relay:
  đọc outbox chưa gửi
  publish vào broker
  đánh dấu đã chuyển/tiến checkpoint
~~~

Hai bản ghi được commit nguyên tử trong cùng database. Relay có thể bị dừng và tiếp tục, nên có khả năng phát lại; consumer phải chấp nhận message trùng. Outbox giúp tránh mất việc do khoảng cách giữa commit và publish, nhưng không tự tạo exactly-once end-to-end.

Cần theo dõi outbox backlog, thời gian chậm phát, lỗi schema và quyền truy cập. Với hệ nhỏ, worker cũng có thể quét trực tiếp job store theo lease/lock thay vì dùng broker riêng.

### 10.3. At-least-once, duplicate và idempotency

Nhiều queue cung cấp cơ chế giao message ít nhất một lần hoặc có thể giao lặp khi timeout/retry. Vì vậy worker cần xử lý an toàn:

- Kiểm tra job còn hợp lệ và chưa SUCCEEDED/CANCELLED.
- Claim job bằng thao tác nguyên tử hoặc lease có fencing/version.
- Gắn attempt ID và cập nhật trạng thái theo điều kiện.
- Với side effect như ghi tiền/gửi yêu cầu đối tác, dùng idempotency key nghiệp vụ hoặc cơ chế chống lặp phù hợp.
- Ack message sau khi trạng thái bền vững đã được ghi; nếu crash tại ranh giới ack/commit, phải chịu được retry.
- Có cơ chế phát hiện lease hết hạn và đưa việc còn dang dở về trạng thái phục hồi.

Đừng dựa vào “consumer của tôi chỉ có một thread” để cho rằng không có duplicate: lỗi kết nối, restart và broker redelivery vẫn có thể tạo attempt mới.

### 10.4. Lease và fencing tránh hai worker cùng ghi

Ví dụ worker A nhận job, giữ lease 30 giây rồi bị pause. Worker B nhận lại sau lease hết hạn và bắt đầu chạy. Worker A bất ngờ tiếp tục, cả hai có thể cùng ghi kết quả.

Có thể dùng **attempt token/lease version** tăng dần khi claim. Chỉ attempt mang token hiện hành mới được cập nhật trạng thái job; với side effect bên ngoài vẫn cần cơ chế idempotency hoặc khóa phù hợp. Lease đơn thuần không loại bỏ mọi race, nhất là khi side effect đã đi qua ranh giới của mình.

### 10.5. Retry có phân loại

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời | Network timeout, 503, quota có thể hồi phục | Retry có giới hạn và backoff/jitter |
| Dữ liệu không hợp lệ | CSV sai schema, thiếu trường bắt buộc | FAILED kèm báo cáo lỗi; không retry vô hạn |
| Xung đột nghiệp vụ | Voucher đã hết hạn, lệnh không còn hợp lệ | Quyết định trạng thái cuối/điều chỉnh nghiệp vụ |
| Phụ thuộc bị gián đoạn kéo dài | Đối tác offline nhiều giờ | Retry chậm, circuit breaker, cảnh báo và runbook |
| Lỗi code hoặc poison message | Exception lặp lại ở cùng payload | Giới hạn attempt, chuyển vùng điều tra/DLQ |

Retry với backoff và jitter tránh hàng nghìn worker đồng loạt gọi lại downstream sau sự cố. DLQ không phải “thùng rác quên đi”: cần owner, alert, công cụ xem lỗi và quy trình xử lý/re-drive an toàn, có bảo vệ duplicate.

**Exactly-once** thường không thể giả định ở cấp tác dụng phụ toàn hệ thống; khả năng thực tế thường dựa trên delivery at-least-once và logic idempotent/transactional theo từng ranh giới.

## 11. Tính nhất quán và ranh giới nghiệp vụ

### 11.1. Phần phải chắc ngay khi phản hồi

Ví dụ người dùng đổi email tài khoản và hệ thống hứa “Đã lưu email mới”. Nếu thay đổi cốt lõi chưa commit, lời hứa này sai. Có thể lưu email đồng bộ trước, rồi phát job gửi email thông báo sau.

Tương tự, với thao tác đặt hàng, cần xác định điều kiện nào cấu thành “đơn đã được chấp nhận”: đã kiểm tra giá? đã giữ tồn? đã xác nhận thanh toán? Mỗi miền có quy tắc khác nhau. Có hệ thống trả “Đơn hàng đang được xử lý” kèm mã theo dõi, rồi xác nhận sau khi đủ điều kiện. Không được dùng câu “Đặt hàng thành công” nếu sự thật nghiệp vụ chưa hoàn tất.

### 11.2. Tác dụng phụ không chặn được tương tác

Sau khi một thay đổi quan trọng đã được ghi đúng:

- Gửi email/SMS xác nhận.
- Cập nhật search index.
- Đẩy dữ liệu sang analytics.
- Tạo bản sao báo cáo.
- Chạy quy tắc phát hiện bất thường không bắt buộc để chấp nhận request.

Các công việc này thường là ứng viên cho xử lý nền. Tuy nhiên, nếu việc gửi một chứng từ, thông báo pháp lý hoặc kiểm soát gian lận là điều kiện bắt buộc của nghiệp vụ, cần mô hình hóa trạng thái riêng và trách nhiệm khi thất bại.

### 11.3. Eventual consistency phải được nhìn thấy trong UX

Khi data được cập nhật không đồng thời giữa các thành phần:

- Một màn hình có thể hiển thị số liệu cũ trong vài giây.
- User có thể thấy job đã xong nhưng kết quả chưa xuất hiện ở search index.
- Một consumer trễ có thể gửi thông báo sau khi người dùng đã thay đổi quyết định.
- Truy vấn kết quả cần nhận biết version hoặc thời điểm cập nhật.

Cần mô tả rõ trạng thái pending, dấu thời gian và thao tác refresh hợp lý. Nếu một luồng cần read-your-writes, hãy thiết kế cách lấy trạng thái từ nguồn đã ghi hoặc cơ chế bảo đảm tương ứng.

### 11.4. Saga và hành động bù

Với nhiều bước qua ranh giới service, không thể kỳ vọng một DB transaction rollback toàn bộ thế giới.

Ví dụ: giữ chỗ → thu tiền → phát hành vé. Nếu phát hành vé thất bại sau khi đã thu tiền, có thể cần hoàn tiền, hỗ trợ thủ công hoặc chờ phục hồi. Đây là quy trình nghiệp vụ nhiều bước, không đơn giản là retry job “vô hạn”.

Các hành động bù phải được xác định với domain expert: có thể hoàn tiền hay không, thời hạn, thứ tự và ai chịu trách nhiệm. Không biến “cancel” trên UI thành lời hứa rằng mọi side effect bên ngoài đã được đảo ngược.

## 12. Thiết kế trải nghiệm người dùng cho công việc nền

### 12.1. Phân biệt ba thời điểm

1. **Yêu cầu đã được tiếp nhận:** user có job ID và biết cách xem tiếp.
2. **Công việc đang được xử lý:** có trạng thái, tiến độ hoặc ước lượng đáng tin nếu đo được.
3. **Kết quả cuối:** SUCCEEDED, FAILED, CANCELLED hoặc trạng thái nghiệp vụ khác; người dùng có hành động rõ ràng.

Tránh đổi ngay nút “Tạo báo cáo” thành nhãn “Đã tạo xong” khi job chỉ mới vào hàng đợi.

### 12.2. Cơ chế cập nhật trạng thái

| Cơ chế | Phù hợp | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| HTTP polling | Job kéo dài giây/phút, ít cập nhật | Đơn giản, hoạt động với hầu hết client | Tần suất hợp lý, backoff, dừng khi terminal |
| Long polling | Muốn giảm request rỗng | Phản hồi khi có thay đổi/trễ timeout | Cần quản lý connection |
| Server-Sent Events (SSE) | Đẩy cập nhật một chiều tới trình duyệt | Dễ dùng với cập nhật progress | Reconnect, event ID, authorization |
| WebSocket | Tương tác hai chiều theo thời gian thực | Gửi/nhận nhiều loại trạng thái | Quản lý kết nối và mở rộng phức tạp hơn |
| Push notification/email | Công việc dài, user đã rời ứng dụng | Gọi user trở lại khi cần | Có thể trễ, bị chặn; không thay job status |
| Webhook | Thông báo cho hệ thống khách hàng | Tự động hóa tích hợp server-to-server | Ký request, retry, idempotent consumer, xác nhận đích |

Không mặc định WebSocket chỉ vì cần progress. Đối với một báo cáo vài phút, polling mỗi vài giây có thể đủ. Với event push, vẫn cần endpoint đọc trạng thái làm nguồn sự thật sau khi client mất kết nối.

### 12.3. Mẫu UI dễ hiểu

~~~text
Báo cáo doanh thu tháng 10
[Đang xử lý]  Đã tổng hợp 7.200 / khoảng 12.000 bản ghi

Bạn có thể đóng trang. Báo cáo sẽ xuất hiện trong
"Lịch sử báo cáo" khi hoàn tất.

[ Xem lịch sử ]   [ Yêu cầu hủy ]
~~~

Khi thành công:

~~~text
[Hoàn tất] Báo cáo đã sẵn sàng
[ Tải xuống ]  Hết hạn: 18/11/2026
~~~

Khi lỗi:

~~~text
[Không hoàn tất] Không thể truy cập nguồn dữ liệu.
Bạn có thể thử lại hoặc liên hệ bộ phận hỗ trợ.
[ Thử lại ]   [ Xem chi tiết ]
~~~

Chỉ hiển thị số phần trăm nếu có định nghĩa đáng tin. Nếu không biết tổng số dòng hoặc bước thực hiện có khối lượng rất khác nhau, dùng các giai đoạn “đã nhận → đang chuẩn bị → đang xử lý → đang hoàn tất” và thời điểm cập nhật cuối.

### 12.4. Hủy, tạm dừng, chạy lại

Hủy là một command có thể **không có hiệu lực tức thì**:

- Nếu QUEUED, hệ thống có thể chuyển thẳng CANCELLED khi không có attempt đang chạy.
- Nếu RUNNING, đánh dấu CANCEL_REQUESTED; worker kiểm tra ở checkpoint và dừng.
- Nếu đã gọi một dịch vụ ngoài không hỗ trợ hủy, một số side effect có thể vẫn xảy ra; phải giải thích contract.
- Nếu SUCCEEDED, yêu cầu hủy có thể bị từ chối hoặc chuyển sang quy trình nghiệp vụ khác.

Một retry do user chủ động cũng cần xác định là **thử lại cùng job** hay **tạo job mới**, đặc biệt nếu đầu vào đã thay đổi. Việc chọn phải nhất quán trên API và UX.

## 13. Bảo mật và quyền truy cập

Công việc nền tồn tại lâu hơn vòng request trực tiếp, do đó thông tin xác thực và quyền có thể thay đổi trong khi job chờ xử lý.

Cần bảo vệ:

- **Ownership:** user A không được đọc trạng thái, input hoặc kết quả job của user B chỉ bằng cách đoán job ID.
- **Tenant isolation:** queue, storage, job query và worker phải thực thi phân vùng dữ liệu phù hợp, không chỉ tin tenant ID từ client.
- **Quyền lúc chạy:** xác định cần kiểm tra lại quyền khi worker thực thi hay job được ủy quyền theo quyền tại thời điểm tạo; quyết định phải rõ với những hành vi nhạy cảm.
- **Dữ liệu nhạy cảm:** tránh đưa token, thông tin cá nhân, file content hoặc secret vào message/log không cần thiết.
- **File artifact:** URL tải xuống có thời hạn, kiểm tra quyền, retention và xóa phù hợp.
- **Input validation:** kiểm tra size, định dạng, antivirus nếu cần, giới hạn decompression và nội dung độc hại.
- **Quota/rate limit:** mỗi user/tenant có giới hạn số job, dung lượng, concurrency và tần suất gửi.
- **Audit:** ai tạo/hủy/chạy lại công việc, thay đổi trạng thái quan trọng và nguồn kết quả.

Không lưu access token của user không có thời hạn vào payload để worker dùng nhiều ngày sau. Có thể sử dụng identity của worker với phạm vi quyền phù hợp, hoặc token ủy quyền ngắn hạn được cấp an toàn, theo chính sách của hệ thống.

## 14. Quan sát và vận hành hai luồng khác nhau

Luồng interactive và background cần chỉ số SLO riêng. API trả 202 nhanh chưa chứng minh trải nghiệm người dùng tốt nếu queue bị tắc 30 phút.

### 14.1. Chỉ số cho interactive flow

- Tỷ lệ request hợp lệ được chấp nhận.
- Latency p50/p95/p99 end-to-end.
- Error rate theo loại lỗi nghiệp vụ/hạ tầng.
- Thời gian để người dùng có phản hồi đầu tiên.
- Tỷ lệ retry do timeout hoặc mất kết nối.
- Mức độ trùng request/idempotency conflict.

### 14.2. Chỉ số cho background jobs

- Queue depth và **oldest job age**.
- Queue wait time: từ accepted đến lúc worker bắt đầu.
- Processing duration và completion time tổng thể.
- Tỷ lệ SUCCEEDED, FAILED, CANCELLED, EXPIRED.
- Số lần retry/attempt trung bình, tỷ lệ chuyển DLQ.
- Throughput job/giây/phút theo loại, worker utilization.
- Số job bị kẹt RUNNING, lease expiration, outbox backlog.
- Tỷ lệ kết quả bị sai/đối soát lệch, không chỉ tỷ lệ process crash.
- Tỷ lệ job vượt deadline cam kết với user.

Một hệ thống có nhiều job “RUNNING” mãi mãi nhưng không phát sinh lỗi HTTP vẫn là hệ thống đang lỗi.

### 14.3. Correlation và tracing

Gắn correlation ID từ request tạo job vào bản ghi job và message. Trace tương tác trực tiếp sẽ kết thúc trước khi worker chạy, nhưng có thể dùng span link hoặc cùng correlation ID để nối vết theo nghiệp vụ. Không giả định một trace đồng bộ kéo dài hàng giờ là cách duy nhất.

Khi điều tra, cần có đường:

~~~text
requestId -> jobId -> enqueue/outbox eventId
          -> attemptId -> workerId
          -> downstream calls -> resultId
~~~

Log nên ghi ID và trạng thái, tránh ghi toàn bộ payload chứa dữ liệu cá nhân. Có thể tạo dashboard để truy vấn theo job ID từ UI hỗ trợ vận hành.

### 14.4. SLO phải phản ánh giá trị người dùng

Ví dụ minh họa, chưa phải chỉ tiêu mặc định:

- 99% request tạo báo cáo hợp lệ nhận phản hồi accepted trong 1 giây.
- 95% báo cáo nhỏ hoàn tất trong 2 phút tính từ khi được chấp nhận.
- Job tồn trong queue quá 10 phút phải phát cảnh báo.
- Mọi job có kết quả terminal hoặc được đưa vào luồng xử lý ngoại lệ có chủ sở hữu.

Khi viết SLO, nên phân loại độ lớn job hoặc các tier khách hàng; một báo cáo 10 GB không nên mặc nhiên dùng cùng mục tiêu với báo cáo 100 dòng.

## 15. Quy tắc thiết kế cho chuỗi gọi nhiều dịch vụ

Một luồng tương tác có thể đi qua API gateway, BFF, ordering, pricing và payment. Nếu mỗi service chờ hàng chục giây mới timeout, toàn bộ request sẽ bị treo hoặc bị retry lặp.

### 15.1. Ngân sách thời gian end-to-end

Đặt một latency budget phù hợp với hành vi. Mỗi downstream call nhận timeout nhỏ hơn ngân sách còn lại, có propagation deadline hoặc cơ chế tương đương. Hạn chế retry đồng thời ở nhiều lớp làm nhân bản lưu lượng và kéo dài request.

Ví dụ giả định:

~~~text
Client chấp nhận đợi tối đa: 2.000 ms
Gateway/BFF và mạng:         250 ms
Business processing:         700 ms
Downstream A:                450 ms
Downstream B:                400 ms
Dự phòng:                    200 ms
~~~

Đây là cách phân bổ để trao đổi thiết kế, không phải công thức cứng. Khi phụ thuộc vượt ngân sách, cần trả lỗi/đang xử lý theo ngữ nghĩa đã thỏa thuận hoặc dùng nhánh nền nếu nghiệp vụ cho phép.

### 15.2. BFF và API aggregation

Nếu UI cần dữ liệu từ nhiều context, BFF có thể tổng hợp read-only call song song, dùng cache hoặc projection. Nhưng BFF không nên trở thành nơi âm thầm điều phối một quy trình kéo dài cần saga.

Với thao tác ghi, cần rõ component nào quyết định kết quả và chịu trách nhiệm điều phối nếu request đến nhiều service. Nếu BFF timeout giữa chừng, client phải biết cách kiểm tra một operation ID thay vì gửi lại mù một giao dịch có tác dụng phụ.

### 15.3. Không biến async thành call stack ẩn

Một message từ A yêu cầu B; B chờ C; C chờ D; cuối cùng A vẫn phải đợi mọi phần để xác nhận nghiệp vụ. Hệ thống lúc đó có thể giữ những phụ thuộc đồng bộ về mặt ngữ nghĩa dù transport bất đồng bộ. Cần làm rõ ai giữ trạng thái, deadline và quyết định cuối, thay vì chỉ thay HTTP bằng event bus.

## 16. Thiết kế trong microservices: quyền sở hữu công việc

Trong kiến trúc microservices, công việc nền cần có **owner**. Không nên tạo một “background-service” làm tất cả việc của mọi miền rồi trở thành nơi chứa logic và quyền truy cập dữ liệu vô hạn.

Ví dụ:

| Công việc | Context nên sở hữu ý nghĩa nghiệp vụ | Hệ thống hỗ trợ có thể dùng chung |
| --- | --- | --- |
| Tạo hóa đơn | Billing | Queue broker, scheduler, telemetry |
| Đối soát thanh toán | Payments | Queue và workflow infrastructure |
| Xuất báo cáo doanh thu | Reporting/Analytics | Object storage, worker platform |
| Xử lý ảnh sản phẩm | Media/Catalog theo mô hình miền | Storage, compute pool |
| Gửi email theo event | Notifications | Email provider connector |
| Đồng bộ trạng thái vận chuyển | Shipping/Fulfillment | Event bus, retry framework |

Thành phần dùng chung như queue, scheduler, notification gateway và observability có thể do platform team vận hành. Nhưng **quy tắc “khi nào hoàn tất”, “thất bại nghĩa là gì”, “ai có quyền hủy”, “cần bù thế nào”** nên thuộc về miền nghiệp vụ tương ứng.

### Monolith, modular monolith hay microservices?

Một luồng async đáng tin cậy không bắt buộc dùng microservice:

- **Monolith:** controller tạo job và worker chạy ở cùng codebase nhưng có bảng job/broker, vẫn có thể độc lập vòng đời xử lý.
- **Modular monolith:** module Reporting sở hữu job API, logic, state machine; worker có thể chạy dưới một process riêng từ cùng codebase nếu cần cô lập tài nguyên.
- **Microservices:** service Reporting sở hữu job và dữ liệu, worker triển khai riêng; cần hợp đồng tích hợp và vận hành phân tán.

Lựa chọn service boundary dựa trên trách nhiệm, mức tải, quyền triển khai, bảo mật và chi phí. “Đưa xuống nền” không đồng nghĩa “tách thành một service mới”.

## 17. Ví dụ mã giả trong Java/Spring: tạo job an toàn

Ví dụ dưới đây tập trung vào luồng ứng dụng. Tên type/method là gợi ý, không phải bản triển khai đầy đủ production.

### 17.1. API handler và transaction

~~~java
@RestController
@RequestMapping("/v1/report-jobs")
final class ReportJobController {
    private final ReportJobApplication app;

    @PostMapping
    ResponseEntity<JobAccepted> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ReportRequest input,
            Principal principal) {

        JobAccepted accepted = app.accept(
            principal.getName(), key, input);

        URI location = URI.create(
            "/v1/report-jobs/" + accepted.jobId());

        return ResponseEntity.accepted()
            .location(location)
            .body(accepted);
    }
}
~~~

~~~java
@Service
final class ReportJobApplication {
    private final JobRepository jobs;
    private final OutboxRepository outbox;
    private final JobIdempotencyRepository idempotency;

    @Transactional
    JobAccepted accept(String ownerId, String key, ReportRequest input) {
        validateRequestAndPermission(ownerId, input);

        // Cần unique constraint trên (ownerId, operation, key).
        // Khi có trùng khóa: so sánh fingerprint input, trả cùng
        // job hoặc báo conflict; không tạo thêm tác dụng phụ.
        Job existing = idempotency.findExisting(ownerId, key, input);
        if (existing != null) return JobAccepted.from(existing);

        Job job = Job.queued(ownerId, input);
        jobs.save(job);
        idempotency.save(ownerId, key, fingerprint(input), job.id());

        outbox.save(OutboxMessage.forJob("ReportRequested", job.id()));
        return JobAccepted.from(job);
    }
}
~~~

Phải xử lý race khi hai request cùng khóa đến đồng thời bằng constraint/transaction và logic đọc lại theo conflict; việc “find trước rồi insert” đơn thuần không bảo vệ được trường hợp race. Cần triển khai đầy đủ validation, security, DB isolation và error mapping trong dự án thật.

### 17.2. Worker và trạng thái

~~~java
final class ReportJobWorker {
    void onMessage(JobRequested msg) {
        Lease lease = jobs.tryClaim(msg.jobId());
        if (lease == null) return;  // đã chạy, đã xong hoặc worker khác giữ

        try {
            ReportFile file = generator.generate(
                lease.input(), lease::checkpoint);

            jobs.completeIfLeaseCurrent(
                lease.jobId(), lease.version(), file.reference());

        } catch (TransientReportException e) {
            jobs.scheduleRetryIfLeaseCurrent(
                lease.jobId(), lease.version(), classifyRetry(e));

        } catch (InvalidReportException e) {
            jobs.failIfLeaseCurrent(
                lease.jobId(), lease.version(), "INVALID_REPORT");
        }
    }
}
~~~

Điểm quan trọng: worker nhận message rồi **kiểm tra job state/lease hiện hành**, không tin rằng message chỉ đến một lần. Nếu generator có side effect ngoài DB, phải bổ sung idempotency tương ứng. Việc lưu file và cập nhật job terminal cần có quy trình dọn kết quả mồ côi/đối soát nếu một bên thành công trước bên còn lại.

### 17.3. Status endpoint

~~~java
@GetMapping("/{jobId}")
JobStatusView status(@PathVariable String jobId, Principal user) {
    Job job = repository.findOwnedBy(jobId, user.getName())
        .orElseThrow(NotFoundException::new);
    return JobStatusView.from(job);
}
~~~

Truy vấn theo owner hoặc tenant nhằm bảo vệ job của người khác. Không phân quyền bằng client-provided ownerId; job ID ngẫu nhiên cũng không thay thế authorization.

## 18. Chuyển một tính năng từ đồng bộ sang background

Giả sử endpoint xuất báo cáo hiện tại xử lý 90 giây rồi trả file, thường xuyên bị gateway timeout. Một kế hoạch migration có thể đi theo các bước:

1. **Đo hiện trạng:** phân phối thời gian chạy, kích thước dữ liệu, tỉ lệ timeout, tỉ lệ user bấm lại, peak request, memory/CPU.
2. **Định nghĩa contract mới:** POST tạo job, GET status, GET download; state machine, code lỗi và thời gian giữ artifact.
3. **Xác định nguồn sự thật:** dữ liệu đầu vào, snapshot/version và kết quả thuộc module nào; quyền truy cập theo tenant ra sao.
4. **Lưu job bền vững:** job table và outbox hoặc DB queue; bảo vệ tạo job trùng bằng idempotency key.
5. **Tách worker:** chuyển xử lý nặng khỏi request path; thêm retry, checkpoint, concurrency limit và backpressure.
6. **Phát triển UI:** màn hình trạng thái, refresh/polling, lỗi rõ ràng, lịch sử job và tải kết quả sau.
7. **Kiểm chứng kết quả:** so sánh báo cáo cũ/mới trên tập dữ liệu đủ đại diện; kiểm tra các số liệu nghiệp vụ, không chỉ file mở được.
8. **Thử lỗi:** restart worker, message trùng, database timeout, upload result thất bại, queue outage, job hủy giữa chừng.
9. **Rollout từng phần:** chỉ chuyển một nhóm user hoặc loại báo cáo; theo dõi completion time và backlog.
10. **Chuyển hoàn toàn:** cập nhật contract client, quan sát consumer cũ rồi mới xóa endpoint đồng bộ sau thời hạn đã thống nhất.

Để giữ tương thích, có thể cung cấp endpoint đồng bộ cũ cho job nhỏ trong giai đoạn chuyển tiếp hoặc trả redirect/hướng dẫn rõ trong API version mới. Không tự ý đổi cùng một endpoint từ trả file sang trả job ID mà không quản lý hợp đồng client.

## 19. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách tiếp cận đúng |
| --- | --- | --- |
| Trả “thành công” ngay khi message được gửi | Người dùng hiểu nhầm kết quả nghiệp vụ | Phân biệt accepted, running, succeeded |
| Bắn một thread nền trong web process rồi quên | Restart mất job, thiếu retry và trạng thái | Dùng job store/queue bền vững và worker có giám sát |
| Dùng queue nhưng không lưu job state | Không biết ai đang chờ, lỗi gì, kết quả ở đâu | Mô hình job ID, status, attempt và artifact |
| API ghi DB và publish tách rời, không cơ chế phục hồi | Job tồn nhưng không bao giờ chạy, hoặc message không có dữ liệu | Outbox/DB queue và reconciliation |
| Tin rằng mỗi message chỉ nhận một lần | Tạo side effect trùng, thất thoát tiền/dữ liệu | Idempotency, claim, lease/fencing |
| Retry mọi lỗi vô hạn | Poison job chiếm queue, quá tải downstream | Phân loại lỗi, giới hạn attempt, DLQ và owner |
| Dùng progress 100% ước lượng vô căn cứ | Mất lòng tin khi job bị kẹt ở 99% | Số đơn vị đã xử lý hoặc giai đoạn thực tế |
| Không phân biệt job và attempt | Người dùng thấy nhiều tác vụ cho một yêu cầu | Stable job ID, attempt riêng để vận hành |
| Không có cơ chế giới hạn tải | Queue dài vô hạn, DB/worker bị quá tải | Quota, concurrency, admission control, backpressure |
| Chỉ theo dõi latency API 202 | Không thấy thời gian chờ nền và lỗi âm thầm | SLO cả queue wait, completion time, failure rate |
| Cho phép đoán job ID để xem kết quả | Lộ dữ liệu giữa các user/tenant | Authorization trên status, download và cancel |
| Gộp tất cả job miền nghiệp vụ vào một service tổng hợp | Ownership mơ hồ, phụ thuộc dữ liệu xuyên miền | Mỗi context sở hữu ý nghĩa; chia sẻ hạ tầng |
| Đổi một luồng bắt buộc phải xác nhận thành fire-and-forget | Trạng thái nghiệp vụ sai và khó bù | Xác định invariant, pending và workflow state |
| Không tính deadline, cancellation, retention | Job mồ côi, chi phí lưu trữ tăng | Lifecycle, cleanup, policy và runbook rõ |

## 20. Bài tập thực hành

**Bối cảnh:** một ứng dụng quản lý khóa học cho phép giáo viên: (a) xem danh sách học viên, (b) tạo bài kiểm tra, (c) nhập 100.000 điểm từ CSV, (d) gửi email kết quả cho từng học viên, (e) xuất báo cáo tổng kết dạng PDF.

**Yêu cầu:**

1. Phân loại mỗi thao tác thành interactive, background hoặc hybrid và giải thích vì sao.
2. Thiết kế API tạo job cho thao tác nhập điểm, gồm request, 202 response và status endpoint.
3. Vẽ state machine tối thiểu cho một job import: QUEUED, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED, CANCELLED.
4. Đề xuất cách kiểm tra quyền để giáo viên lớp A không đọc được báo cáo lớp B.
5. Giả sử worker chết sau khi đã nhập 60.000 dòng: mô tả checkpoint và cơ chế xử lý trùng.
6. Với 20 worker, mỗi job import mất trung bình 40 giây, ước tính năng lực tối đa đơn giản theo job/phút; trình bày vì sao cần đo thêm I/O và phân phối job size.
7. Thiết kế thông báo cho người dùng khi import hoàn tất nhưng 350 dòng dữ liệu không hợp lệ.
8. Nếu yêu cầu gửi email ngay khi có điểm mới, xác định điều kiện phát sự kiện và thời điểm gửi an toàn.
9. Lập bộ metric gồm latency của API tạo job, queue wait, job duration, backlog và failure rate.
10. Đề xuất ít nhất ba kịch bản lỗi để thử trước khi rollout.

### Gợi ý hướng giải

- Xem danh sách và tạo bài kiểm tra nhỏ thường là luồng tương tác; lưu bài kiểm tra cần xác nhận ngay việc ghi dữ liệu.
- Import lượng lớn và xuất PDF có thể là job nền, với trạng thái và kết quả tải về.
- Gửi email là tác dụng phụ có thể xử lý sau khi dữ liệu điểm đã được ghi bền vững; nếu cần duyệt kết quả trước khi gửi thì workflow phải có trạng thái “đã duyệt”.
- Một import có thể thành công một phần, ví dụ SUCCEEDED_WITH_ERRORS, **nếu** chính sách nghiệp vụ cho phép. Cần công bố contract này rõ; nếu nguyên tắc là tất cả hoặc không gì, phải chọn chiến lược dữ liệu khác.
- Năng lực lý thuyết của 20 worker với trung bình 40 giây/job là 0,5 job/giây, khoảng 30 job/phút. Kết quả thực tế thường thấp hơn do I/O, lock, retry và kích thước tệp khác nhau.

## 21. Checklist dùng khi thiết kế tính năng thực tế

**Trước khi chọn mô hình giao tiếp**

- [ ] Đã xác định phần người dùng phải biết ngay và phần có thể hoàn thành sau.
- [ ] Đã mô tả ý nghĩa của accepted, pending, succeeded, failed với nghiệp vụ.
- [ ] Đã xác định SLO trải nghiệm người dùng và giới hạn thời gian tương tác.
- [ ] Đã so sánh xử lý trực tiếp, job nền, event reaction và workflow dài.

**Trước khi đưa vào production**

- [ ] Có job ID, state machine, owner/tenant và thời gian lưu kết quả.
- [ ] Yêu cầu đã nhận được ghi bền vững, có cơ chế xử lý publish lỗi.
- [ ] Producer và consumer có chiến lược retry/idempotency phù hợp.
- [ ] Worker có claim/lease, timeout và giới hạn concurrency.
- [ ] Có cơ chế dừng, hủy, retry và recovery được định nghĩa theo nghiệp vụ.
- [ ] Có UI/API theo dõi tiến độ, lỗi và kết quả cuối.
- [ ] Có quản lý quyền truy cập input, output và dữ liệu nhạy cảm.
- [ ] Có monitoring queue age, completion time, stuck job, DLQ và data correctness.
- [ ] Đã thử crash, duplicate delivery, outage và migration compatibility.
- [ ] Đã biết ai trực sự cố và xử lý job mắc kẹt.

## 22. Tổng kết kiến thức

Thiết kế tốt không chỉ là giảm thời gian chờ trên màn hình. Hệ thống phải trả lời đúng **điều gì đã xảy ra**, **điều gì còn đang chờ** và **ai chịu trách nhiệm nếu công việc không hoàn tất**. Luồng tương tác trực tiếp tập trung vào quyết định tức thời và latency; công việc nền tập trung vào thực thi bền vững, năng lực xử lý, idempotency, retry, state và khả năng quan sát.

Trong monolith, modular monolith hay microservices, có thể dùng cùng nguyên tắc: ghi nhận yêu cầu một cách đáng tin, trao cho người dùng định danh và trạng thái, xử lý nặng sau bằng worker/queue khi cần, và chỉ tuyên bố hoàn tất khi kết quả nghiệp vụ thực sự được xác nhận.

Khi ranh giới giữa trực tiếp và nền được mô hình hóa rõ, ứng dụng vừa phản hồi nhanh hơn vừa vận hành dễ hơn, trong khi tránh nhầm lẫn tai hại giữa **đã tiếp nhận**, **đang xử lý** và **đã thành công**.
