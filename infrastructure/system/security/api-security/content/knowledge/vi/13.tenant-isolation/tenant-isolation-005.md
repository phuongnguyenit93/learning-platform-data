# Quota, rate limit và log theo tenant

Trong hệ thống multi-tenant, nhiều khách hàng hoặc tổ chức cùng sử dụng một API và có thể chia sẻ CPU, bộ nhớ, database, connection pool, hàng đợi, băng thông và dịch vụ phụ thuộc. Nếu một tenant gửi quá nhiều request hoặc tạo ra công việc quá tốn kém, tenant đó có thể chiếm tài nguyên dùng chung và làm chậm hoặc gián đoạn dịch vụ của các tenant khác. Hiện tượng này thường được gọi là noisy neighbor.

Quota, rate limit và giám sát theo tenant giúp giới hạn mức tiêu thụ tài nguyên, phân bổ năng lực công bằng và phát hiện hành vi bất thường. Các cơ chế này cũng hỗ trợ điều tra sự cố: nhóm vận hành có thể xác định tenant nào tạo ra tải, endpoint nào bị sử dụng nhiều và giới hạn nào đã bị chạm.

Điều kiện quan trọng là tenant context phải được xác định từ danh tính đã xác thực và được truyền nhất quán qua các lớp xử lý. Nếu server tin tenantId do client tự gửi, kẻ gọi có thể đổi tenant để né quota hoặc làm sai lệch log.

## 1. Phân biệt quota, rate limit và concurrency limit

Ba khái niệm này liên quan nhưng giải quyết các vấn đề khác nhau:

| Cơ chế | Điều gì được giới hạn | Ví dụ |
|---|---|---|
| Rate limit | Tốc độ request hoặc thao tác trong một khoảng thời gian | Tenant được gọi tối đa 120 lần mỗi phút trên endpoint tìm kiếm |
| Quota | Tổng ngân sách tiêu thụ trong một chu kỳ | Tenant được tạo tối đa 50.000 bản ghi mỗi tháng |
| Concurrency limit | Số công việc đang chạy đồng thời | Tenant chỉ được có tối đa 5 tác vụ export đang xử lý |

Rate limit bảo vệ hệ thống trước lưu lượng tăng đột ngột hoặc lặp liên tục. Quota kiểm soát tổng lượng sử dụng trong một khoảng thời gian dài hơn. Concurrency limit ngăn một tenant giữ quá nhiều worker, thread hoặc connection cùng lúc.

Ngoài ra, một API có thể cần giới hạn kích thước request, số bản ghi mỗi batch, dung lượng lưu trữ, băng thông tải xuống, số tác vụ nền, thời gian xử lý hoặc chi phí truy vấn. Không nên chỉ đếm số HTTP request vì hai request có thể tạo ra chi phí rất khác nhau.

Ví dụ, một request đọc trạng thái đơn hàng có thể chỉ cần một truy vấn nhỏ, trong khi một request export có thể quét hàng triệu dòng và tạo file lớn. Nếu cả hai đều được tính là một request, rate limit đơn giản sẽ không phản ánh mức tiêu thụ tài nguyên.

## 2. Xác định tenant đáng tin cậy

Mọi quota và log theo tenant đều phụ thuộc vào việc xác định đúng tenant. Tenant context cần được tạo từ danh tính hoặc quan hệ đã được xác minh, chẳng hạn:

- Claim tenant trong access token đã được xác minh chữ ký, issuer, audience và thời hạn.
- Quan hệ thành viên giữa user và tenant được tra cứu từ dữ liệu tin cậy.
- API key hoặc service identity được ánh xạ đến tenant trong kho quản lý credential.
- Ngữ cảnh tenant được thiết lập bởi một gateway tin cậy sau khi xác thực và được bảo vệ khi chuyển tiếp.

Không lấy tenantId trong query, body hoặc header tùy ý làm nguồn quyết định quota. Ví dụ client gửi header X-Tenant-Id: tenant-b không có nghĩa request được tính vào tenant B. Server phải xác minh caller có quyền hoạt động trong tenant đó; nếu không, request cần bị từ chối.

### 2.1. Phân biệt người dùng, tenant và client

Một user có thể là thành viên của nhiều tenant; một tenant có thể có nhiều user, API key và service account. Vì vậy, hệ thống cần xác định rõ quota áp dụng cho đối tượng nào:

- **Tenant:** giới hạn tổng tài nguyên dùng chung của một tổ chức.
- **User:** ngăn một thành viên tạo tải quá lớn bên trong tenant.
- **API client/key:** giới hạn một ứng dụng tích hợp hoặc credential.
- **Endpoint/action:** bảo vệ riêng các thao tác tốn tài nguyên hoặc nhạy cảm.
- **Global:** bảo vệ năng lực chung của toàn hệ thống.

Các lớp giới hạn nên phối hợp. Một tenant có thể còn quota nhưng một user trong tenant vẫn bị rate limit; ngược lại, user không vượt giới hạn cá nhân nhưng tổng tải của tenant đã chạm ngân sách.

### 2.2. Truyền tenant context qua các service

Khi request đi qua nhiều service, tenant context cần được truyền bằng cơ chế nội bộ tin cậy. Các service phải xác minh nguồn gọi và không chấp nhận tenant header từ một nguồn không được phép.

Một luồng tham khảo:

~~~mermaid
flowchart TD
    A[Client request] --> B[Authenticate credential]
    B --> C[Resolve tenant membership]
    C --> D[Create trusted tenant context]
    D --> E[Apply global, tenant and user limits]
    E --> F[Execute API operation]
    F --> G[Propagate trusted context to services]
    G --> H[Record tenant-scoped logs and metrics]
~~~

Không nên lấy tenant context từ thread-local hoặc request context rồi dùng trong tác vụ bất đồng bộ mà không truyền tường minh. Khi đưa công việc vào queue, cần lưu tenant identity đã được xác minh cùng job metadata; worker phải xác thực nguồn message và kiểm tra job thuộc tenant nào trước khi xử lý.

## 3. Thiết kế quota theo tài nguyên và nghiệp vụ

Quota cần gắn với tài nguyên thực tế mà API tiêu thụ. Có thể chia thành các nhóm:

| Nhóm | Ví dụ quota | Rủi ro được kiểm soát |
|---|---|---|
| Request/API | Số request hoặc action theo chu kỳ | Lưu lượng gọi API quá lớn |
| Dữ liệu | Số record tạo mới, số record import/export | Tải lớn lên database và xử lý batch |
| Storage | Dung lượng file, số object lưu trữ | Cạn dung lượng và chi phí lưu trữ |
| Compute | Số tác vụ hoặc đơn vị xử lý được tính trọng số | Công việc tốn CPU hoặc thời gian |
| Network | Dung lượng upload/download | Chiếm băng thông |
| Concurrency | Số request nặng hoặc job đang chạy | Giữ worker, thread và connection |
| External dependency | Số lần gọi dịch vụ bên ngoài | Vượt quota của nhà cung cấp hoặc gây quá tải upstream |

### 3.1. Đặt quota theo endpoint và chi phí

Mỗi endpoint cần được phân loại theo mức tiêu thụ và tác động:

- Read đơn giản: có thể giới hạn theo request count và page size.
- Search: giới hạn tốc độ, số filter, độ sâu truy vấn và số kết quả.
- Batch create/update: giới hạn số phần tử và tổng thao tác.
- Export/report: giới hạn số job đang chạy, dữ liệu đầu ra và thời gian xử lý.
- Upload: giới hạn bytes, số file và dung lượng storage của tenant.
- Action tài chính: giới hạn tốc độ, kiểm tra idempotency và áp dụng kiểm soát nghiệp vụ riêng.

Một số endpoint nên tính cost unit thay vì mỗi request có trọng số bằng nhau. Ví dụ một truy vấn đọc nhỏ có cost 1, tìm kiếm phức tạp có cost 5 và export lớn có cost 50. Đây là mô hình minh họa; trọng số phải được hiệu chỉnh từ số liệu thực tế và không thay thế giới hạn riêng về bytes, concurrency hoặc thời gian.

### 3.2. Phân biệt hard quota và soft quota

- **Hard quota:** khi hết ngân sách, thao tác mới bị từ chối cho đến khi quota được bổ sung hoặc chu kỳ reset.
- **Soft quota:** hệ thống cảnh báo hoặc ghi nhận vượt ngưỡng, nhưng vẫn cho phép sử dụng trong khoảng dung sai hoặc thời gian ân hạn.

Ví dụ, tenant có hard quota về dung lượng lưu trữ nhưng nhận cảnh báo khi đạt 80% và 95%. Với một số dịch vụ, soft quota có thể cho phép hoàn tất công việc đang chạy trong khi chặn tạo job mới. Chính sách cần nêu rõ request nào bị từ chối và tài nguyên đã được cấp trước đó được xử lý thế nào.

### 3.3. Ví dụ bảng quota theo gói

Các con số sau chỉ minh họa cách mô hình hóa, không phải khuyến nghị mặc định cho mọi hệ thống:

| Loại tenant | Request đọc/phút | Job export đồng thời | Dung lượng lưu trữ |
|---|---:|---:|---:|
| Starter | 60 | 1 | 5 GB |
| Standard | 300 | 3 | 100 GB |
| Enterprise | 1.200 | 10 | Theo hợp đồng |

Không nên chỉ dựa vào tên gói để quyết định quyền. Quota hiệu lực cần lấy từ policy/configuration đã được quản lý, có version và được áp dụng nhất quán trên các instance.

## 4. Chọn thuật toán rate limit phù hợp

Mỗi thuật toán có cách xử lý burst, độ chính xác và chi phí lưu trạng thái khác nhau.

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Fixed window | Đếm request trong từng cửa sổ thời gian cố định | Đơn giản, ít trạng thái | Có thể tạo burst ở ranh giới hai cửa sổ |
| Sliding log | Lưu thời điểm từng request trong cửa sổ trượt | Chính xác theo thời gian | Tốn bộ nhớ và thao tác |
| Sliding window counter | Kết hợp bộ đếm cửa sổ hiện tại và trước đó | Cân bằng độ chính xác và chi phí | Kết quả có thể là xấp xỉ |
| Token bucket | Token được bổ sung theo tốc độ; mỗi request tiêu thụ token | Cho phép burst có giới hạn và kiểm soát tốc độ dài hạn | Cần lưu trạng thái token nhất quán |
| Leaky bucket | Request được xử lý hoặc phát ra với tốc độ đều | Làm phẳng burst | Có thể tăng độ trễ hoặc cần queue |

### 4.1. Token bucket

Token bucket thường phù hợp với API cần cho phép burst ngắn nhưng vẫn giữ tốc độ trung bình. Bucket có dung lượng tối đa B token; token được bổ sung theo tốc độ r token mỗi giây. Một request có cost c chỉ được chấp nhận nếu bucket còn ít nhất c token.

Ví dụ, bucket có dung lượng 100 token và refill 10 token mỗi giây. Tenant có thể gửi một burst tối đa theo lượng token tích lũy, nhưng nếu tiếp tục gửi liên tục thì tốc độ dài hạn bị giới hạn gần mức refill. Với endpoint có cost khác nhau, request nặng tiêu thụ nhiều token hơn.

### 4.2. Fixed window và burst ở ranh giới

Giả sử giới hạn là 100 request mỗi phút. Một tenant có thể gửi 100 request ở cuối phút này và thêm 100 request ngay đầu phút sau. Trong một khoảng ngắn, server có thể nhận gần 200 request dù mỗi cửa sổ đều không vượt ngưỡng.

Nếu endpoint dễ bị quá tải, hãy cân nhắc sliding window, token bucket hoặc kết hợp rate limit với concurrency limit. Thuật toán đơn giản có thể vẫn phù hợp cho quota tổng theo ngày hoặc tháng, nơi burst ở ranh giới ít ảnh hưởng hơn.

### 4.3. Concurrency limit

Rate limit không giới hạn số request đang chạy nếu request kéo dài. Ví dụ một tenant gọi 10 request mỗi giây, mỗi request mất 30 giây, có thể tích lũy hàng trăm request đồng thời.

Concurrency limit giữ số tác vụ đang chạy dưới một ngưỡng. Khi hết slot, hệ thống có thể từ chối ngay hoặc đưa request vào queue có giới hạn và thời gian chờ tối đa. Queue không giới hạn chỉ chuyển tình trạng quá tải từ thread sang bộ nhớ.

## 5. Áp dụng giới hạn theo nhiều cấp

Một kiến trúc multi-tenant nên có nhiều lớp giới hạn:

1. **Global limit:** bảo vệ tổng năng lực hệ thống và dịch vụ phụ thuộc.
2. **Tenant limit:** bảo đảm một tenant không chiếm phần lớn tài nguyên dùng chung.
3. **User/client limit:** ngăn một credential hoặc user tạo tải bất thường trong tenant.
4. **Endpoint/action limit:** bảo vệ thao tác đặc biệt tốn kém hoặc nhạy cảm.
5. **Object/business limit:** ví dụ số lần thử thanh toán trên một order hoặc số lần export một báo cáo.

Thứ tự kiểm tra cần được thiết kế để từ chối sớm mà không tạo side effect. Ví dụ, trước khi tạo job export, server có thể kiểm tra global capacity, tenant concurrency, user rate limit và quota export. Nếu bất kỳ lớp nào từ chối, không tạo job hoặc trừ quota nghiệp vụ không thể hoàn lại.

Không nên chỉ giới hạn theo IP. Nhiều user hợp lệ có thể dùng chung NAT hoặc proxy, trong khi một tenant có thể dùng nhiều IP hoặc API key. IP là một tín hiệu bổ sung, không thay thế tenant identity.

## 6. Triển khai rate limit phân tán

Trong môi trường có nhiều application instance, bộ đếm trong bộ nhớ của từng instance không tạo ra giới hạn tenant chính xác. Nếu có bốn instance và mỗi instance cho phép 100 request/phút, tenant có thể đạt tổng cộng khoảng 400 request/phút khi lưu lượng được phân tán.

Có thể dùng Redis hoặc một dịch vụ quota tập trung để chia sẻ trạng thái giữa các instance. Các thao tác kiểm tra và cập nhật bộ đếm phải nguyên tử để hai request đồng thời không cùng nhìn thấy quota còn trống rồi đều được chấp nhận.

### 6.1. Ví dụ fixed-window counter bằng Redis Lua

Script sau minh họa cách tăng bộ đếm và đặt TTL trong cùng một thao tác nguyên tử:

~~~lua
local current = redis.call('INCR', KEYS[1])

if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

local limit = tonumber(ARGV[2])
if current > limit then
    return {0, current}
end

return {1, current}
~~~

Ứng dụng truyền key của bucket, thời gian sống của cửa sổ và giới hạn request. Kết quả đầu tiên cho biết request được phép hay bị từ chối; kết quả thứ hai là số lần đã ghi nhận trong cửa sổ. Đây là ví dụ fixed window cơ bản, có đặc điểm burst ở ranh giới cửa sổ như đã nêu ở trên.

### 6.2. Thiết kế key theo tenant và action

Key cần phân biệt tenant, loại quota và phạm vi endpoint. Ví dụ:

~~~text
rate:{tenant-opaque-id}:orders-read:minute
rate:{tenant-opaque-id}:payment-refund:minute
quota:{tenant-opaque-id}:export:month
concurrency:{tenant-opaque-id}:export
~~~

Tenant identifier trong key phải lấy từ tenant context tin cậy. Có thể dùng ID nội bộ ổn định hoặc giá trị đã được làm mờ; không đưa email, tên tổ chức hoặc dữ liệu cá nhân vào key. Cần chuẩn hóa key để tránh ký tự đặc biệt, va chạm namespace và lỗi khi đổi tên tenant.

Với Redis Cluster, các key tham gia một thao tác Lua cần tuân thủ quy tắc slot của hệ thống. Nếu một request phải kiểm tra nhiều bucket cùng lúc, thiết kế key và script cần bảo đảm các key có thể được xử lý nguyên tử trong topology đang dùng. Không giả định nhiều key tùy ý luôn có thể nằm trong cùng một transaction phân tán.

### 6.3. Xử lý lỗi của kho quota

Nếu Redis hoặc quota service không khả dụng, cần có chính sách rõ:

- **Fail closed:** từ chối thao tác khi không xác minh được quota. Phù hợp với action rủi ro cao hoặc tài nguyên có giới hạn cứng.
- **Fail open có kiểm soát:** cho phép tạm thời trong một ngân sách dự phòng hoặc giới hạn cục bộ. Có thể phù hợp với một số endpoint đọc ít rủi ro, nhưng cần bảo vệ global capacity.

Không nên âm thầm chuyển sang bộ đếm local không giới hạn vì có thể nhân quota theo số instance. Nếu dùng fallback, phải có ngưỡng, thời gian tối đa, metric và cảnh báo rõ ràng.

Với multi-region, cần xác định quota có tính toàn cục hay theo region. Bộ đếm eventual consistency có thể cho phép vượt quota tạm thời; nếu giới hạn là hard quota, cần cơ chế cấp ngân sách theo region hoặc một nguồn điều phối có tính nhất quán phù hợp.

## 7. Xử lý request vượt giới hạn

Khi tenant vượt rate limit, API thường trả HTTP 429 Too Many Requests. Response có thể kèm Retry-After để client biết khi nào nên thử lại. Với quota dài hạn đã hết, contract cần giải thích thời điểm reset hoặc cách tenant được cấp thêm ngân sách.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Rate limit exceeded",
  "status": 429,
  "detail": "The tenant has exceeded the allowed request rate."
}
~~~

Các header RateLimit-Limit, RateLimit-Remaining và RateLimit-Reset có thể được sử dụng nếu phù hợp với chuẩn và contract của API. Giá trị cần mô tả đúng bucket đang áp dụng; tránh trả thông tin nội bộ nhạy cảm hoặc làm lộ quota của tenant khác.

Client nên dùng exponential backoff có jitter khi retry, tôn trọng Retry-After và tránh retry liên tục. Với request tạo dữ liệu hoặc action tài chính, cần idempotency key để việc gửi lại sau 429 hoặc timeout không tạo tác động trùng.

Nếu request bị từ chối trước khi xử lý, không tính nó như một thao tác nghiệp vụ thành công. Tuy nhiên, hệ thống có thể vẫn ghi nhận số lần bị từ chối vào một bộ đếm bảo vệ riêng để phát hiện abuse. Cần phân biệt request count, accepted operation và billable usage.

## 8. Công bằng giữa tenant và bảo vệ noisy neighbor

Rate limit theo tenant là nền tảng nhưng không bảo đảm công bằng nếu mọi tenant chia sẻ một queue hoặc pool mà tenant lớn có thể chiếm hết slot trước tenant nhỏ.

Các kỹ thuật hỗ trợ fairness:

- Giới hạn concurrency riêng cho từng tenant.
- Queue riêng hoặc logical queue theo tenant.
- Weighted fair queuing để phân bổ worker theo trọng số được phê duyệt.
- Giới hạn kích thước batch và thời gian xử lý.
- Giới hạn số connection hoặc truy vấn đồng thời theo tenant khi kiến trúc hỗ trợ.
- Ưu tiên công việc theo SLA nhưng vẫn giữ giới hạn cứng cho từng tenant.
- Circuit breaker và bulkhead để lỗi hoặc tải cao ở một tenant không lan sang tenant khác.

Ví dụ, một tenant có thể được phép có tối đa 3 export đồng thời trong khi toàn hệ thống có 20 worker export. Hàng đợi cần tránh để một tenant đưa hàng nghìn job vào trước và chiếm toàn bộ slot chờ. Có thể dùng queue theo tenant hoặc bộ lập lịch phân phối lượt xử lý.

Không nên dùng một quota chung cho tất cả tenant nếu hợp đồng hoặc mức tài nguyên khác nhau. Nhưng cũng không nên cho tenant trả phí cao bỏ qua hoàn toàn giới hạn global; global protection vẫn cần để bảo vệ dịch vụ và các tenant khác.

## 9. Quota cho tác vụ bất đồng bộ

Export, import, báo cáo, xử lý ảnh và đồng bộ dữ liệu thường chạy nền. Nếu chỉ rate limit request tạo job, tenant có thể tạo nhiều job đang chờ và làm đầy queue.

Cần kiểm soát:

- Số job đang chờ và đang chạy theo tenant.
- Số job được tạo trong một khoảng thời gian.
- Tổng số record hoặc bytes mà job được phép xử lý.
- Thời gian chạy tối đa và số lần retry.
- Dung lượng kết quả được lưu và thời hạn giữ file.
- Quyền tải kết quả và quyền xem trạng thái job.

Khi enqueue job, lưu tenant context đã xác minh, principal tạo job, loại operation, quota reservation và correlation ID. Worker cần xác minh message đến từ producer tin cậy, kiểm tra tenant và áp dụng quota ở bước thực thi. Không tin trường tenantId trong message nếu producer hoặc đường truyền chưa được xác thực.

Nếu quota được giữ chỗ khi tạo job, cần có cơ chế giải phóng khi job bị hủy hoặc thất bại trước khi tiêu thụ tài nguyên. Với job chạy lại, idempotency và trạng thái reservation phải tránh trừ quota nhiều lần. Nếu công việc đã tiêu thụ tài nguyên một phần, chính sách ghi nhận usage cần được xác định rõ.

## 10. Log, metric và trace theo tenant

Quota chỉ giúp từ chối hoặc điều tiết tải. Log và telemetry giúp biết điều gì đang xảy ra, tenant nào đang sử dụng tài nguyên và vì sao một request bị từ chối.

### 10.1. Trường log nên có

Log có cấu trúc có thể ghi:

- Tenant ID nội bộ hoặc mã định danh đã làm mờ.
- Principal/client identity ở dạng phù hợp chính sách.
- Endpoint template và HTTP method.
- Action hoặc loại tài nguyên.
- Kết quả: allowed, denied, throttled, quota_exceeded hoặc error.
- Loại bucket/quota và policy version.
- Kích thước request/response hoặc cost unit nếu cần.
- Latency, request ID và trace ID.
- Region hoặc service xử lý request.

Nên ghi endpoint template như /orders/{orderId} thay vì path chứa ID thực tế. Không ghi access token, API secret, mật khẩu, payload đầy đủ hoặc dữ liệu cá nhân không cần thiết. Nếu cần ghi object ID để điều tra, hãy dùng chính sách masking, quyền truy cập và retention phù hợp.

### 10.2. Phân biệt log vận hành và audit log

Log vận hành hỗ trợ chẩn đoán lỗi, latency và mức sử dụng. Audit log ghi lại hành động có ý nghĩa bảo mật hoặc nghiệp vụ như thay đổi role, export dữ liệu, refund hoặc vượt quyền. Hai loại log có mục đích, thời hạn lưu và quyền truy cập khác nhau.

Không nên để tenant đọc trực tiếp log vận hành hoặc audit log nội bộ của hệ thống. Nếu cung cấp usage report cho tenant, hãy tạo view riêng chỉ chứa dữ liệu thuộc tenant đó và không để lộ ID, request hoặc hoạt động của tenant khác.

### 10.3. Metric theo tenant và vấn đề cardinality

Các metric hữu ích:

- Request accepted/denied theo endpoint và kết quả.
- Số lần rate limit hoặc quota bị chạm.
- Request rate, latency và error rate.
- Bytes upload/download và storage usage.
- Job queued/running/failed và concurrency.
- Database query time hoặc external dependency calls theo nhóm workload.

Không nên mặc định đưa tenant ID tùy ý vào label của mọi metric. Một hệ thống có hàng chục nghìn tenant có thể tạo cardinality rất cao, làm tăng chi phí và giảm hiệu năng của monitoring backend.

Có thể dùng metric tổng hợp theo endpoint, plan, region hoặc loại quota; lưu chi tiết tenant trong log có kiểm soát; dùng dashboard top-N tenant theo mức sử dụng; hoặc gửi metric tenant-specific vào hệ thống theo dõi chuyên biệt. Cần bảo đảm cách tổng hợp vẫn đủ để phát hiện noisy neighbor và điều tra tenant cụ thể.

### 10.4. Truyền context trong distributed tracing

Trace context giúp nối request qua gateway, service, database và worker. Tenant attribute có thể được gắn ở dạng mã định danh đã làm mờ nếu cần điều tra, nhưng không nên gắn dữ liệu nhạy cảm hoặc tạo cardinality không cần thiết. Tracing sampling cần giữ lại đủ trace của request bị throttled, lỗi quota và action nhạy cảm.

## 11. Quản lý policy và thay đổi quota

Quota thường phụ thuộc gói dịch vụ, hợp đồng, mức rủi ro hoặc thỏa thuận riêng. Cần quản lý policy như cấu hình có version:

- Mỗi tenant có policy hiệu lực và ngày bắt đầu áp dụng.
- Có thể override theo tenant nhưng phải có lý do, người phê duyệt và thời hạn.
- Thay đổi quota cần được audit và triển khai nhất quán.
- Chu kỳ reset phải được xác định rõ theo UTC hoặc múi giờ nghiệp vụ.
- Policy mới cần có hiệu lực rõ ràng đối với request đang chạy và job đã enqueue.
- Khi tenant bị tạm ngưng, quota và quyền gọi API cần được xử lý theo quy trình.

Không nên chỉnh quota trực tiếp trong Redis mà không cập nhật nguồn policy chính. Nếu bộ đếm và policy tách rời, hệ thống cần cơ chế đồng bộ, cache invalidation và xử lý khi cấu hình thay đổi.

### 11.1. Reset quota và xử lý thời gian

Quota theo ngày, tháng hoặc kỳ hợp đồng cần định nghĩa:

- Mốc bắt đầu và kết thúc chu kỳ.
- Múi giờ áp dụng.
- Cách xử lý tháng có số ngày khác nhau.
- Hành vi khi policy đổi giữa chu kỳ.
- Cách xử lý usage đang chạy hoặc job chưa hoàn tất lúc reset.

Dùng UTC cho timestamp lưu trữ và tính toán thường giúp giảm lỗi do đổi múi giờ. Nếu hợp đồng yêu cầu reset theo múi giờ địa phương, cần chuyển đổi rõ ràng tại ranh giới chu kỳ và kiểm thử thời điểm đổi giờ.

### 11.2. Cảnh báo trước khi chạm quota

Thông báo ở các ngưỡng như 70%, 85% hoặc 95% giúp tenant và vận hành chủ động. Ngưỡng thực tế cần dựa trên tốc độ sử dụng, thời gian reset và mức độ quan trọng của dịch vụ.

Không gửi thông báo mỗi request khi tenant đang gần quota. Nên gom cảnh báo, áp dụng cooldown và cung cấp usage summary. Nội dung thông báo chỉ chứa dữ liệu của tenant nhận thông báo.

## 12. Kiểm thử quota, rate limit và tenant isolation

Test cần xác minh cả giới hạn lẫn ranh giới tenant. Một rate limiter có thể hoạt động đúng nhưng dùng nhầm key chung cho mọi tenant; khi đó tenant này có thể tiêu thụ quota của tenant khác.

| Nhóm test | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Tenant identity | Thay tenant ID trong header, query hoặc body | Không thể đổi tenant context nếu không có quyền |
| Isolation | Gửi tải lớn từ tenant A rồi gọi API bằng tenant B | Quota của B vẫn độc lập theo policy |
| Boundary | Gửi request ngay dưới, đúng và vượt ngưỡng | Hành vi đúng theo định nghĩa quota |
| Burst | Gửi burst ở đầu/cuối cửa sổ | Thuật toán xử lý đúng burst đã công bố |
| Concurrency | Tạo nhiều request/job đồng thời | Không vượt giới hạn concurrency của tenant |
| Distributed | Phân phối request qua nhiều application instance | Tổng quota vẫn được áp dụng nhất quán |
| Atomicity | Gửi request đồng thời tại thời điểm bucket gần cạn | Không có oversubscription ngoài dung sai được thiết kế |
| Redis failure | Làm quota store mất kết nối trong môi trường test | Hệ thống tuân thủ fail-open/fail-closed policy |
| Retry | Client retry sau 429 hoặc timeout | Tôn trọng Retry-After và không tạo side effect trùng |
| Background job | Tạo job, retry, cancel và chạy worker | Tenant context và reservation được giữ đúng |
| Logging | Gửi request từ nhiều tenant | Log gắn đúng tenant, không lộ dữ liệu chéo |
| Cardinality | Kiểm tra metric labels khi có nhiều tenant | Monitoring không phát sinh cardinality không kiểm soát |

Nên có test tích hợp qua gateway và nhiều application instance. Unit test cho một bộ đếm local không chứng minh quota phân tán hoạt động đúng. Với Redis Lua hoặc quota service, cần test thao tác đồng thời và thời điểm reset.

## 13. Những sai lầm thường gặp

- **Tin tenantId từ client:** caller có thể đổi tenant để né quota hoặc làm sai log.
- **Chỉ rate limit theo IP:** nhiều tenant có thể dùng chung NAT, còn một tenant có thể có nhiều IP.
- **Chỉ giới hạn request count:** request nặng và request nhẹ bị tính như nhau dù chi phí rất khác.
- **Chỉ dùng bộ đếm local:** nhiều instance nhân giới hạn theo số replica.
- **Dùng fixed window cho mọi endpoint:** burst ở ranh giới cửa sổ có thể gây quá tải.
- **Không có concurrency limit:** request dài hoặc job nền có thể tích lũy dù rate limit thấp.
- **Queue không giới hạn:** quá tải được chuyển sang hàng đợi và cuối cùng làm cạn bộ nhớ.
- **Key Redis không có tenant scope:** các tenant dùng chung bucket hoặc ghi đè trạng thái của nhau.
- **Không xử lý lỗi quota store:** fallback không giới hạn có thể vô hiệu hóa bảo vệ.
- **Trừ quota nhiều lần khi retry:** job hoặc action bị tính trùng do thiếu idempotency.
- **Ghi tenant ID và dữ liệu nhạy cảm tùy tiện:** log trở thành nguồn rò rỉ dữ liệu.
- **Đưa mọi tenant ID vào metric label:** monitoring backend có thể quá tải do cardinality.
- **Không tách usage report:** tenant có thể nhìn thấy hoạt động của tenant khác.
- **Không version hóa policy:** các instance có thể áp dụng ngưỡng khác nhau sau khi cấu hình đổi.

## 14. Checklist trước khi phát hành

- [ ] Tenant context được tạo từ credential hoặc membership đã xác minh.
- [ ] Tenant ID từ header, query hoặc body không thể tự thay đổi phạm vi caller.
- [ ] Có quota riêng cho các tài nguyên quan trọng như request, dữ liệu, storage, compute và job.
- [ ] Có rate limit theo tenant và lớp user/client/endpoint phù hợp.
- [ ] Có concurrency limit cho request hoặc job dài.
- [ ] Endpoint được phân loại theo chi phí; request nặng có cost hoặc giới hạn riêng.
- [ ] Thuật toán rate limit phù hợp với burst và mức chính xác yêu cầu.
- [ ] Quota phân tán được cập nhật nguyên tử và hoạt động nhất quán giữa các instance.
- [ ] Redis/quota store có timeout, fallback và fail-open/fail-closed policy rõ ràng.
- [ ] Job bất đồng bộ giữ tenant context đã xác minh và quản lý quota reservation.
- [ ] Response 429 có thông tin retry phù hợp với contract.
- [ ] Client retry có backoff, jitter và idempotency khi thao tác có side effect.
- [ ] Log và trace gắn tenant context đúng, không ghi token hoặc payload nhạy cảm.
- [ ] Metric tránh cardinality cao và vẫn hỗ trợ phát hiện noisy neighbor.
- [ ] Tenant chỉ xem được usage report và log thuộc tenant của mình.
- [ ] Policy quota có version, quy tắc reset, override và audit.
- [ ] Có test boundary, cross-tenant, concurrency, multi-instance, store failure và background job.

Quota, rate limit và log theo tenant cần được thiết kế như một phần của tenant isolation. Khi danh tính tenant được xác minh, giới hạn được áp dụng ở nhiều cấp và telemetry phản ánh đúng phạm vi, hệ thống có thể giảm noisy neighbor, phân bổ tài nguyên công bằng và điều tra sự cố mà không làm lộ dữ liệu giữa các tenant.
