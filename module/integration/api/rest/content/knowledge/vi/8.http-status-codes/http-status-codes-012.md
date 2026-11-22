# 429, Retry-After và phản hồi khi quá hạn mức

## 1. Khi API đúng chức năng nhưng không thể nhận mọi yêu cầu

Trong REST API, không phải yêu cầu có URI, phương thức HTTP, JSON và quyền truy cập hợp lệ đều được xử lý ngay. Một client có thể gửi quá nhiều request trong thời gian ngắn; nhiều client có thể cùng tạo tải đột biến; hoặc một tài nguyên khan hiếm như cơ sở dữ liệu, dịch vụ thanh toán, công cụ tạo báo cáo đang chạm giới hạn công suất.

Để diễn đạt trường hợp **bên gọi vượt giới hạn tốc độ hoặc hạn mức được áp dụng**, HTTP có mã **429 Too Many Requests**. Server cũng có thể trả header **Retry-After** để gợi ý khi nào bên gọi nên thử lại. Hợp đồng API cần cho client biết:

1. Yêu cầu hiện tại **được xử lý hay bị từ chối**?
2. Giới hạn được tính **theo người dùng, API key, tenant, địa chỉ IP, endpoint, chi phí thao tác hay toàn dịch vụ**?
3. Khi nào có thể thử lại, và client phải **giảm nhịp gửi** như thế nào?
4. Nếu request tạo hoặc thay đổi dữ liệu, việc thử lại có **an toàn trước thao tác lặp** không?
5. Client có thể theo dõi hạn mức, nhận cảnh báo hoặc yêu cầu nâng gói bằng cơ chế nào?

Bài học thuộc chương **Mã trạng thái** của module **INTEGRATION_API_REST**, kết nối ngữ nghĩa HTTP với thiết kế resource và URI, phương thức, hợp đồng phản hồi rõ ràng, idempotency, caching, xác thực/phân quyền, OpenAPI và kiểm thử Java/Spring. Mục tiêu là thiết kế một API **công bằng, có thể dự đoán và phục hồi được khi chịu tải lớn**.

> **Nguyên tắc:** **429** diễn đạt một giới hạn đã được áp dụng cho bên gọi hoặc nhóm yêu cầu. **Retry-After** là chỉ dẫn chờ có ích, nhưng không phải lời bảo đảm lần thử sau chắc chắn được chấp nhận.

## 2. Ngữ nghĩa chính xác của 429 Too Many Requests

RFC 6585 định nghĩa **429 Too Many Requests** để cho biết người dùng/client đã gửi **quá nhiều yêu cầu trong một khoảng thời gian nhất định**. “Người dùng” ở đây là khái niệm áp dụng chính sách: tùy API, có thể là một người đăng nhập, tenant, API key, thiết bị, địa chỉ IP hoặc một nhóm lưu lượng.

### Phản hồi 429 cơ bản

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Bạn đã vượt hạn mức tạo báo cáo. Hãy giảm tần suất yêu cầu.",
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

Phản hồi này cho biết request bị từ chối vì giới hạn; **30** là số giây server đề nghị chờ trước khi thử tiếp. Body theo kiểu **Problem Details** giúp client phân loại lỗi có cấu trúc. Header **Cache-Control: no-store** ở đây chỉ nhằm nhấn mạnh ý định tránh lưu; bản thân RFC 6585 đã yêu cầu **response 429 không được lưu trong HTTP cache**.

### Những điều cần nhớ

| Thuộc tính | Quy tắc diễn giải |
|---|---|
| Mã trạng thái | **429** thuộc nhóm **4xx**, chỉ tình huống vượt hạn mức áp dụng cho request |
| Body | Nên có thông tin đủ để client hiểu giới hạn và điều chỉnh; không có schema bắt buộc riêng của 429 |
| Retry-After | **Có thể** được gửi cùng 429; không phải header bắt buộc đối với mọi 429 |
| Đếm hạn mức | HTTP không quy định một thuật toán đếm hoặc phạm vi giới hạn duy nhất |
| Cache | Response **429 không được HTTP cache lưu trữ** theo RFC 6585 |
| Quyền truy cập | 429 không thay thế 401/403 và không có nghĩa client được quyền với resource |
| Trạng thái nghiệp vụ | 429 không có nghĩa yêu cầu trước đó đã hoàn thành, cũng không bảo đảm retry là an toàn |

Nếu API muốn trả một **chính sách hạn mức theo ngày/tháng**, nên công bố rõ thời gian đặt lại, quyền được sử dụng và quy tắc nâng hạn mức. Một request bị từ chối do hết **quota hàng tháng** có thể vẫn trả 429 theo chính sách API, nhưng gợi ý “thử lại sau 1 giây” sẽ gây hiểu nhầm.

### 429 không phải cơ chế chống tấn công đầy đủ

Rate limiting hỗ trợ bảo vệ tài nguyên và công bằng giữa người dùng, nhưng vẫn cần **authentication, authorization, bảo vệ mạng/WAF, kiểm soát abuse, quota tổng và giám sát**. Không nên tiết lộ dữ liệu nhạy cảm về tài khoản, lượng tài nguyên của người khác hoặc cấu trúc nội bộ thông qua body lỗi.

## 3. Phân biệt 429 với các mã trạng thái gần nhau

| Tình huống | Mã thường phù hợp | Ý nghĩa và hành động |
|---|---|---|
| Một API key vượt 100 request/phút | **429** | Giảm tốc độ; có thể chờ theo Retry-After |
| Một tenant dùng hết số lượt tạo báo cáo theo chính sách | **429** nếu mô hình quota được API định nghĩa như vậy | Xem lịch reset/nâng gói hoặc đợi kỳ tiếp theo |
| Toàn bộ dịch vụ tạm không đủ công suất hoặc đang bảo trì | **503 Service Unavailable** | Lỗi khả dụng của dịch vụ; có thể kèm Retry-After |
| Chưa gửi chứng thực hợp lệ cho endpoint bảo vệ | **401 Unauthorized** | Xác thực lại; 429 không thay bước xác thực |
| Đã xác thực nhưng không có quyền sử dụng chức năng | **403 Forbidden** | Cần quyền/chính sách; chờ một lúc không tạo thêm quyền |
| Một cập nhật xung đột trạng thái resource | **409 Conflict** | Giải quyết xung đột nghiệp vụ |
| Điều kiện If-Match không thỏa | **412 Precondition Failed** | Lấy ETag/trạng thái mới và xử lý xung đột |
| Payload không hợp lệ theo quy tắc nghiệp vụ | **422 Unprocessable Content** nếu dùng mã này trong contract | Sửa dữ liệu; retry nguyên request thường không giúp |
| Đang tạo báo cáo bất đồng bộ và đã ghi bền vững | **202 Accepted** | Request đã được nhận để xử lý tiếp; không phải 429 |

**503 và 429 có thể cùng xuất hiện trong một hệ thống.** Ví dụ, API gateway trả 429 cho tenant vượt giới hạn cá nhân; khi database production không thể nhận thêm request dù tenant chưa vượt quota, tầng ứng dụng có thể trả 503. Hai mã đều có thể mang **Retry-After**, nhưng nguyên nhân và cách vận hành khác nhau.

Đừng dùng **429 cho mọi lỗi công suất** vì client cần biết khi nào tự giảm tốc độ theo chính sách, khi nào dịch vụ gặp sự cố diện rộng. Ngược lại, khi đã áp dụng giới hạn tốc độ cho một client cụ thể, trả 500 sẽ khiến client tưởng server bị lỗi và có thể retry quá mạnh.

## 4. Hạn mức, giới hạn tốc độ và số request đang xử lý

Các giới hạn thường phục vụ mục tiêu khác nhau:

| Loại giới hạn | Ví dụ | Tác dụng chính |
|---|---|---|
| **Rate limit** | 60 request/phút/API key | Khống chế nhịp gọi theo thời gian |
| **Burst limit** | Tối đa 20 request dồn trong thời gian rất ngắn | Hấp thụ burst nhỏ, chặn đột biến lớn |
| **Quota tổng** | 10.000 lượt xử lý/ngày/tenant | Kiểm soát mức sử dụng theo chu kỳ |
| **Concurrency limit** | Tối đa 5 báo cáo đang chạy cùng lúc/tenant | Bảo vệ tài nguyên xử lý đắt |
| **Global safety limit** | Tối đa 500 thao tác ghi/giây toàn cụm | Bảo vệ database, downstream hoặc chi phí chung |
| **Weighted limit** | GET tốn 1 đơn vị; tạo report tốn 10 đơn vị | Phản ánh mức tiêu thụ tài nguyên khác nhau |

Một API có thể áp dụng **nhiều giới hạn đồng thời**. Ví dụ người dùng còn quota ngày nhưng đã vượt burst limit tại thời điểm hiện tại; vẫn cần trả 429 cho request bị từ chối. Hợp đồng nên giải thích **giới hạn nào đang bị chạm** ở mức hữu ích và an toàn.

### Định danh bên gọi chính xác

Trong hệ thống đã xác thực, ưu tiên định danh đáng tin cậy từ **API key, user ID, tenant ID hoặc service identity**. Với endpoint chưa đăng nhập, có thể giới hạn theo IP hay thiết bị, kết hợp chính sách chống abuse. Khi đứng sau reverse proxy, **không tin trực tiếp X-Forwarded-For do client tự gửi**; chỉ sử dụng thông tin đã được một proxy tin cậy chuẩn hóa.

Rate limit chỉ dựa trên IP có thể khiến nhiều người dùng chung NAT bị chặn oan. Ngược lại, chỉ dựa trên API key có thể bị lạm dụng ở endpoint xác thực chưa có key. Có thể cần **giới hạn thô tại edge** và **giới hạn theo tenant/user tại API**, mỗi lớp có mục tiêu, ngưỡng và owner rõ ràng.

## 5. Retry-After: cú pháp, ý nghĩa và giới hạn

Theo HTTP Semantics (RFC 9110), header **Retry-After** chỉ dẫn client nên đợi bao lâu trước khi gửi yêu cầu tiếp theo. Giá trị có **hai dạng hợp lệ**:

1. **delay-seconds:** số nguyên thập phân không âm, đơn vị **giây**.
2. **HTTP-date:** ngày giờ tuyệt đối theo định dạng ngày HTTP.

### Dạng khoảng chờ

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

**Retry-After: 60** nghĩa là server gợi ý chờ **60 giây**, không phải 60 mili giây, không phải timestamp Unix. Không sử dụng **Retry-After: 0.5** như một giá trị chuẩn vì delay-seconds là **số nguyên không âm**. Nếu chính sách cho phép chờ ngắn hơn một giây, vẫn phải quyết định hợp đồng phản hồi phù hợp với tính chính xác của header.

### Dạng ngày giờ tuyệt đối

~~~http
HTTP/1.1 429 Too Many Requests
Date: Wed, 18 Nov 2026 09:30:00 GMT
Retry-After: Wed, 18 Nov 2026 09:31:00 GMT
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

Ví dụ trên đề nghị thử lại sau **09:31:00 GMT**, tương đương 60 giây sau Date. Client phải **phân tích ngày HTTP**, không nhầm sang ngày giờ địa phương hoặc ngày theo định dạng tự phát. Cần tính đến sai lệch đồng hồ giữa client/server và độ trễ truyền mạng.

### Khi nào nên trả Retry-After?

- Có **cửa sổ reset** tương đối xác định, chẳng hạn giới hạn cố định mỗi phút.
- Có thể tính **thời điểm sớm nhất** mà token hoặc slot mới dự kiến sẵn sàng.
- Server hoặc downstream đang bảo trì/tạm quá tải và có ước lượng phục hồi hợp lý.

Nếu API không biết khi nào hạn mức được cấp lại (ví dụ quota đã hết và cần quản trị viên nâng gói), không nên bịa một khoảng chờ nhỏ. Có thể **bỏ Retry-After**, trả lỗi có code rõ ràng và link tài liệu, hoặc gửi thời điểm reset thực sự biết được.

### Retry-After không phải đặt chỗ

Ngay cả khi chờ đủ số giây, request có thể lại nhận 429 vì **những client khác đã tiêu thụ quota**, nhiều quota khác đồng thời có hiệu lực, hoặc dịch vụ đang giảm công suất. Client cần giữ **retry budget**, dùng **backoff có jitter**, giới hạn tổng thời gian và báo trạng thái phù hợp cho người dùng.

Header này cũng có thể xuất hiện với **503 Service Unavailable** và trong các ngữ cảnh HTTP khác, ví dụ chuyển hướng; không được lập trình logic “có Retry-After nghĩa là chắc chắn 429”.

## 6. Headers mô tả hạn mức và hợp đồng phản hồi

Ngoài Retry-After, nhiều API cung cấp thông tin hạn mức còn lại hoặc thời gian đặt lại. Có nhiều cách đặt tên và quy ước khác nhau, ví dụ các trường **RateLimit-Limit**, **RateLimit-Remaining**, **RateLimit-Reset** hoặc họ header **X-RateLimit-*** của nhà cung cấp.

**Các header giới hạn không luôn hiện diện và không mặc nhiên có cùng ngữ nghĩa ở mọi API**; cần công bố định dạng, đơn vị và cách chọn giới hạn nào được phản ánh. Khi triển khai, hãy theo hợp đồng của phiên bản đặc tả/proxy đang sử dụng thay vì giả định các tên có thể thay thế nhau.

Ví dụ minh họa **một hợp đồng API tự công bố**:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
RateLimit-Limit: 100
RateLimit-Remaining: 0
RateLimit-Reset: 30
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Giới hạn 100 yêu cầu trong cửa sổ được áp dụng đã hết.",
  "code": "RATE_LIMIT_EXCEEDED",
  "limitScope": "api-key"
}
~~~

Ở **ví dụ hợp đồng này**, Limit thể hiện giới hạn được báo, Remaining là số lượng còn lại và Reset được quy ước tính bằng giây tới mốc reset. Nếu API dùng bộ header hoặc định dạng RateLimit khác, **không được suy nghĩa chỉ dựa trên tên**. Khi có nhiều giới hạn (mỗi giây, phút, ngày), chính sách cần nêu rõ cặp giá trị tương ứng với giới hạn nào và điều gì xảy ra nếu một giới hạn khác bị chạm.

### Dùng Problem Details để máy và người đều đọc được

Các trường chuẩn của **Problem Details** gồm **type**, **title**, **status**, **detail**, **instance** khi phù hợp. API có thể thêm extension như **code**, **limitScope**, **requestId** hoặc link tài liệu.

Một quy ước hữu ích:

| Trường | Ví dụ | Công dụng |
|---|---|---|
| **type** | URI mô tả loại lỗi | Client có thể phân loại theo lỗi ổn định |
| **title** | Too Many Requests | Mô tả ngắn |
| **status** | 429 | Phản ánh mã HTTP |
| **detail** | “Giới hạn 100 request/phút đã hết.” | Giải thích dễ hiểu; không lộ nội bộ |
| **code** (mở rộng) | RATE_LIMIT_EXCEEDED | Client phân nhánh không phụ thuộc ngôn ngữ detail |
| **limitScope** (mở rộng) | tenant | Giúp xử lý công bằng, nếu thông tin an toàn để lộ |
| **requestId** (mở rộng) | req-8a21 | Tra cứu logs và hỗ trợ |

Không đưa **API key thô, địa chỉ nội bộ, ID người dùng khác, cấu trúc database hoặc thông tin bí mật** vào body lỗi. Phía client nên ưu tiên **status/code/type** cho logic; **detail** dùng cho hiển thị và debug có kiểm soát.

### CORS và việc đọc Retry-After trên trình duyệt

Nếu web frontend gọi API cross-origin, phản hồi 429 cũng cần **CORS headers hợp lệ** để JavaScript đọc được body/status. Trường **Retry-After** không thuộc nhóm response header tự động được JavaScript truy cập trong mọi trường hợp; nếu frontend cần đọc nó qua **fetch**, hãy đưa header này vào **Access-Control-Expose-Headers** theo chính sách phù hợp.

~~~http
HTTP/1.1 429 Too Many Requests
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Retry-After, RateLimit-Remaining
Vary: Origin
Retry-After: 30
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

Ví dụ áp dụng khi origin trên nằm trong allowlist của server. **CORS không thay authentication/authorization**, và preflight OPTIONS cần được xử lý theo chính sách riêng để tránh trình duyệt bị chặn trước khi gửi request chính.

## 7. Chọn thuật toán giới hạn tốc độ

Không có thuật toán đúng cho tất cả workload. Mỗi thuật toán đánh đổi giữa độ chính xác, công bằng, khả năng hấp thụ burst, tài nguyên lưu trạng thái và mức độ khó vận hành.

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế cần lưu ý |
|---|---|---|---|
| **Fixed window** | Đếm request trong cửa sổ cố định, ví dụ từng phút | Dễ hiểu, dễ triển khai | Có thể cho burst lớn sát ranh giới hai cửa sổ |
| **Sliding window log** | Lưu thời điểm request trong khoảng trượt | Chính xác cho khoảng trượt | Tốn bộ nhớ/ghi khi lưu lượng lớn |
| **Sliding window counter** | Ước lượng dựa trên bộ đếm các cửa sổ liền kề | Ít trạng thái hơn log | Có sai số tùy cách nội suy |
| **Token bucket** | Token được bổ sung theo tốc độ; request tiêu thụ token | Cho burst ngắn, kiểm soát tốc độ dài hạn | Cần quyết định capacity/refill/cost và xử lý đồng thời |
| **Leaky bucket / paced queue** | Điều tiết luồng ra với nhịp đều hoặc giới hạn xả | Giảm dồn tải xuống downstream | Tăng độ trễ; cần giới hạn hàng chờ và timeout |
| **Concurrency semaphore** | Chỉ cho một số thao tác chạy đồng thời | Hữu ích với công việc tốn RAM/connection | Không trực tiếp giới hạn số request theo thời gian |

### Fixed window: ranh giới cửa sổ

Giả sử giới hạn là **100 request/phút**. Một client gửi 100 request vào cuối phút trước và 100 request vào đầu phút sau có thể được chấp nhận **200 request trong vài giây** dù mỗi cửa sổ riêng không vượt 100. Nếu database cần bảo vệ trước burst cực ngắn, fixed window đơn độc có thể chưa đủ.

### Token bucket: tốc độ trung bình và burst

Một tenant có token bucket:

- **Capacity = 20 token** (cho burst tối đa 20 thao tác cùng lúc).
- **Refill rate = 1 token/giây** (tốc độ bền vững khoảng 60 thao tác/phút).
- Mỗi thao tác thường tiêu tốn **1 token**.

Nếu bucket đang đầy và **50 request đồng thời** tới, một cách triển khai atomic có thể **nhận 20** và trả **429 cho 30**. Sau 4 giây không có request mới, bucket bổ sung khoảng **4 token**, không phải reset thành 20. **Retry-After: 1** chỉ gợi ý lúc dự kiến có token kế tiếp; không có nghĩa cả 30 request bị chặn đều có thể thử đồng loạt sau 1 giây.

Đặt số token tiêu thụ theo chi phí thực tế khi có endpoint quá đắt:

- **GET /reports/{id}**: 1 đơn vị.
- **POST /reports**: 10 đơn vị.
- **POST /reports/export**: 20 đơn vị.

Các trọng số này là **ví dụ hợp đồng nội bộ**, cần đo CPU, truy vấn, memory, queue và chi phí downstream để chọn. Việc thay trọng số sau khi phát hành ảnh hưởng client và có thể là thay đổi hợp đồng/giá dịch vụ.

### Concurrency limit

Một request tạo báo cáo có thể chạy 5 phút, nên giới hạn **5 báo cáo đồng thời/tenant** dù tenant còn quota/phút. Nếu API đã lưu bền vững một job vào queue và trả 202, cách giới hạn số **job đang chạy** có thể nằm ở worker scheduler; nếu endpoint buộc xử lý đồng bộ, một request vượt số slot có thể nhận 429 hoặc mã lỗi phù hợp với chính sách đã công bố.

Đừng trả 429 chỉ vì **queue tạm thời có backlog** nếu API trước đó đã cam kết có thể nhận công việc và vẫn còn công suất nhận an toàn. Cần phân biệt **khả năng chấp nhận job**, **khả năng xử lý job** và **deadline hoàn tất**.

## 8. Thiết kế rate limiting trong kiến trúc phân tán

Một thiết kế đám mây thực tế có thể kết hợp **hạn mức thô ở edge**, **hạn mức chi tiết ở API** và **giới hạn công suất ở downstream**:

~~~mermaid
flowchart TD
    C["Client"] --> E["CDN / WAF / API Gateway<br/>giới hạn IP và kết nối"]
    E --> A["Auth + định danh tenant/API key"]
    A --> L["Rate-limit decision<br/>tenant + endpoint + quota"]
    L <--> S[("Shared quota state<br/>atomic update + TTL")]
    L --> D{"Còn hạn mức?"}
    D -- "Không" --> R["429 + Problem Details<br/>Retry-After nếu tính được"]
    D -- "Có" --> P["REST endpoint / service"]
    P --> DB[("Database / downstream")]
    DB -. "capacity & errors" .-> O["Metrics, alert, capacity policy"]
    L -. "admitted/rejected" .-> O
    R --> C
    P --> C
~~~

### Ba lớp bảo vệ và trách nhiệm

1. **Edge:** chặn burst hoặc abuse trước khi tải đến ứng dụng, nhất là với endpoint công khai/chưa xác thực. Cần cấu hình theo IP đáng tin cậy, tránh chặn oan người dùng chung NAT.
2. **API/application:** áp dụng quota theo **tenant, API key, user, endpoint, gói sử dụng hoặc giá trị chi phí**. Có thể kết hợp global limit để bảo vệ database hoặc cổng thanh toán.
3. **Worker/downstream:** giới hạn **concurrency, connection pool, throughput** và retry, tránh trường hợp hàng nghìn request hợp lệ cùng làm nghẽn tài nguyên đích.

**Không nên để mọi instance tự đếm quota độc lập** nếu hợp đồng yêu cầu quota thống nhất trên toàn cụm. Ví dụ ba pod, mỗi pod tự cho 100 request/phút, có thể dẫn tới khoảng 300 request/phút cho cùng API key tùy cân bằng tải.

### Dữ liệu hạn mức dùng chung

Có thể dùng managed gateway có rate limiting, Redis/data store hỗ trợ phép cập nhật atomic, hoặc một hệ thống quota chuyên dụng. Với token bucket phân tán, logic **đọc trạng thái → tính refill → kiểm tra token → trừ token → ghi trạng thái** cần thực hiện **nguyên tử** theo khóa chính sách; nếu đọc và ghi riêng, hai request song song có thể cùng dùng một token.

Phác thảo thuật toán:

~~~text
decision = atomic_token_bucket(tenantKey, endpointKey, cost, now):
    state = load_state_or_initialize()
    elapsed = max(0, now - state.lastRefillAt)
    tokens = min(capacity, state.tokens + elapsed * refillPerSecond)

    if cost > capacity:
        return REJECT_NON_RETRIABLE_CONFIG_OR_CONTRACT

    if tokens >= cost:
        state.tokens = tokens - cost
        state.lastRefillAt = now
        save_atomically_with_expiry(state)
        return ACCEPT

    missing = cost - tokens
    retrySeconds = ceil(missing / refillPerSecond)
    state.tokens = tokens
    state.lastRefillAt = now
    save_atomically_with_expiry(state)
    return REJECT_429(retrySeconds)
~~~

Đây là **giả mã thuật toán**, không phải cú pháp Redis/Spring có thể chạy ngay. Cần giải quyết trường hợp **refillPerSecond = 0**, đồng hồ lệch, request lớn hơn capacity, key hết hạn, chính sách thay đổi, và độ chính xác thời gian. Chính sách cho request có cost lớn hơn capacity phải được xác định rõ, **không yêu cầu client retry vĩnh viễn** một thao tác không thể vừa bucket.

### Chọn phương án khi kho đếm quota gặp sự cố

- **Fail-open:** tạm cho qua nhiều request, tăng khả dụng nhưng có thể làm downstream quá tải hoặc vượt quota tài chính.
- **Fail-closed:** chặn request khi không xác minh được quota, bảo vệ nguồn lực nhưng gây suy giảm dịch vụ ngay khi bộ đếm lỗi.
- **Fallback cục bộ/giới hạn bảo vệ:** có thể hữu ích với một số endpoint, nhưng cần nêu rõ độ chính xác giảm và giới hạn an toàn.

Chọn theo **rủi ro nghiệp vụ và mức độ quan trọng**, không tự động coi một lựa chọn là tốt hơn. Gắn **metrics, alert, runbook, owner và phép thử sự cố** cho tầng quota; nó có thể trở thành thành phần trọng yếu của đường xử lý.

## 9. Thiết kế chuỗi phản hồi khi quá hạn mức

### Khi request đến gateway và API

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant G as Gateway
    participant A as Application
    participant Q as Quota Store
    C->>G: GET /api/reports?page=1
    G->>A: Request đã qua kiểm tra đầu vào của gateway
    A->>Q: Check-and-consume quota (tenant, endpoint, cost)
    alt Còn quota
        Q-->>A: ACCEPT
        A-->>C: 200 OK + dữ liệu
    else Vượt quota
        Q-->>A: REJECT, retryAfter=30s
        A-->>C: 429 + Retry-After: 30 + Problem Details
        Note over C: Chờ, giảm tốc độ và kiểm tra retry budget
        C->>G: Retry sau khi đủ điều kiện
    end
~~~

Trong thực tế gateway thường chuyển phản hồi qua cùng đường về client; sơ đồ rút gọn đường trả để tập trung vào quota. Nếu **gateway** đã tự trả 429, application có thể **không nhìn thấy request**. Do đó cần log/metric từ cả gateway và ứng dụng, với request ID thống nhất khi có thể.

### Một hợp đồng phản hồi thống nhất

Các endpoint nên nhất quán về:

- **Status 429** khi vượt quy tắc giới hạn được định nghĩa.
- **Problem Details** với loại lỗi và code ổn định, không lẫn cùng lỗi validation.
- **Retry-After** khi có ước lượng đáng tin, đơn vị/định dạng đúng chuẩn.
- **Chỉ số hạn mức** khi công bố; rõ đơn vị, scope và ý nghĩa.
- **CORS** và request ID để client và vận hành chẩn đoán được.
- **Chính sách retry/idempotency** cho phương thức có side effect.
- **Tài liệu giới hạn** và cách cấp quota, nhất là với đối tác công khai.

Nếu một yêu cầu phải được xử lý an toàn sau khi đã **accepted**, tránh trường hợp ghi thay đổi nghiệp vụ rồi vẫn trả 429 như thể request chắc chắn chưa được nhận. Hạn mức thường nên kiểm tra **trước khi thực hiện side effect**, đồng thời cần xác định tình huống giao dịch timeout sau khi commit có thể khiến client không biết kết quả.

## 10. Client xử lý 429 đúng cách

Một client “mạnh mẽ” không phải client retry nhanh nhất; nó phải giúp hệ thống hồi phục, không nhân đôi giao dịch và không vượt quá hạn mức.

### Thuật toán ứng xử đề xuất

1. Khi nhận **429**, đọc **Retry-After** nếu có và hợp lệ.
2. Kiểm tra request có **thể retry an toàn** không. GET/HEAD thường an toàn về ngữ nghĩa; POST tạo giao dịch cần idempotency key hoặc cách tra cứu kết quả.
3. Tính thời điểm có thể gửi lại; nếu không có Retry-After, dùng **exponential backoff có jitter** với giới hạn.
4. Tôn trọng **deadline tổng** và **retry budget** (số lần thử, thời gian, mức tải). Không để tất cả thread cùng retry ngay.
5. Điều chỉnh **tốc độ gửi lâu dài** nếu liên tục gặp 429; một vòng retry không thay thế limiter ở phía client.
6. Nếu phải dừng, trả thông tin thân thiện và trạng thái rõ ràng cho người dùng; không biến 429 thành “đã tạo đơn thành công”.

Giả mã:

~~~text
request_with_retry(request, deadline, maxAttempts):
    for attempt in 1..maxAttempts:
        response = send(request)
        if response.status != 429:
            return response

        if not request.isSafeToReplay():
            return MANUAL_OR_STATUS_LOOKUP_REQUIRED

        if attempt == maxAttempts:
            return RATE_LIMIT_RETRY_EXHAUSTED

        if validRetryAfter(response.headers):
            baseWait = parseRetryAfter(response.headers, response.date)
        else:
            baseWait = boundedExponentialBackoff(attempt)

        wait = applyNonNegativeBoundsAndJitter(baseWait, deadline)
        if waitDoesNotFitDeadline(wait):
            return RATE_LIMIT_DEADLINE_EXCEEDED
        sleep(wait)

    return RATE_LIMIT_RETRY_EXHAUSTED
~~~

Khi **Retry-After** là ngày tuyệt đối, parser cần xử lý chênh lệch đồng hồ; khi là delay-seconds, đơn vị là **giây**. Giới hạn chờ phải hợp với nghiệp vụ: một giao diện tìm kiếm không nên giữ spinner hàng giờ vì quota ngày đã hết. Không gộp các giới hạn thời gian vào một con số tùy ý rồi trả về cho mọi loại request.

### Exponential backoff và jitter

Với lỗi tạm thời và không có Retry-After:

\[
\text{baseDelay}(n)=\min(D_{\max},\,D_0\times2^{n-1}).
\]

Giả sử \(D_0 = 1\) giây, \(D_{\max}=16\) giây, các giá trị trước jitter là **1, 2, 4, 8, 16 giây**. **Jitter** làm nhiều client không cùng thức dậy vào một giây rồi gây “thundering herd”. Nếu Retry-After cung cấp thời điểm sớm nhất, chiến lược jitter không nên khiến client thử lại **trước** thời điểm server đã đề nghị.

### Thao tác không idempotent

**GET** và **HEAD** là safe; **PUT** và **DELETE** idempotent ở cấp ngữ nghĩa HTTP nếu server thực thi đúng, nhưng vẫn phải xem rủi ro của trạng thái nghiệp vụ và lỗi mạng. **POST** thường không idempotent nếu không có cơ chế riêng.

Ví dụ client gọi:

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
Idempotency-Key: payment-order-913-v1
Content-Type: application/json

{"orderId":"ord-913","amount":150000,"currency":"VND"}
~~~

Nếu API trả 429 **trước khi nhận yêu cầu** thì client có thể retry theo chính sách. Tuy nhiên trong một hệ thống thực, timeout hoặc lỗi đường truyền có thể xảy ra **sau khi server đã commit**. Do đó, với thanh toán cần **idempotency key được lưu bền vững và ràng buộc với payload/người gọi**, hoặc endpoint tra cứu trạng thái giao dịch. Đừng chỉ dựa vào status 429 của một lần gọi để kết luận mọi request tương tự đều chưa từng được thực hiện.

### Tránh retry storm

Khi API gateway, service trung gian, SDK và ứng dụng đều retry một request ba lần, lượng lời gọi cuối cùng có thể tăng mạnh. Cần xác định **tầng được phép retry**, dùng **retry budget chung**, timeout end-to-end và giới hạn concurrency để giảm nhân bội tải. 429 lặp lại nhiều lần là tín hiệu cần **giảm tốc độ**, không phải tín hiệu tăng số client thread.

## 11. Triển khai phản hồi 429 trong Java/Spring

### 11.1. Nơi quyết định hạn mức

Trong ứng dụng Spring, việc áp dụng rate limit có thể nằm ở API gateway, filter, interceptor, service hoặc một dịch vụ quota. Quyết định cần được đưa ra **trước side effect nghiệp vụ** nếu request sẽ bị từ chối. Với môi trường nhiều instance, bộ đếm nên dùng **shared state có cập nhật atomic** hoặc dịch vụ quản lý đáp ứng hợp đồng.

Ví dụ nhỏ dưới đây tập trung vào **cách ánh xạ lỗi hạn mức thành HTTP 429 và Retry-After**. Nó giả định rằng một limiter riêng đã phát hiện vượt giới hạn và tạo exception. Nó **không triển khai thuật toán hạn mức** bằng bộ đếm trong RAM.

~~~java
import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

final class QuotaExceededException extends RuntimeException {
    private final long retryAfterSeconds;

    QuotaExceededException(long retryAfterSeconds) {
        super("Rate limit exceeded");
        this.retryAfterSeconds = Math.max(0L, retryAfterSeconds);
    }

    long retryAfterSeconds() {
        return retryAfterSeconds;
    }
}

@RestControllerAdvice
class RateLimitExceptionHandler {

    @ExceptionHandler(QuotaExceededException.class)
    ResponseEntity<ProblemDetail> handle(QuotaExceededException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.TOO_MANY_REQUESTS,
                "Đã vượt giới hạn yêu cầu. Vui lòng giảm tốc độ gửi.");
        problem.setType(URI.create(
                "https://api.example.test/problems/rate-limit-exceeded"));
        problem.setTitle("Too Many Requests");
        problem.setProperty("code", "RATE_LIMIT_EXCEEDED");

        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header(HttpHeaders.RETRY_AFTER,
                        Long.toString(ex.retryAfterSeconds()))
                .cacheControl(org.springframework.http.CacheControl.noStore())
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Ví dụ dành cho **Spring Framework 6 / Spring Boot 3** và các phiên bản tương thích. Một ứng dụng thật có thể tách lớp, package và cấu hình exception handler phù hợp. **Nếu không biết thời gian retry hợp lý**, exception/handler nên cho phép **bỏ Retry-After** thay vì ép giá trị 0. Ví dụ này luôn có thời gian chờ vì đó là hợp đồng của loại exception minh họa.

### 11.2. Tích hợp với limiter và phương thức HTTP

Giả mã ở tầng service:

~~~java
// Pseudocode: dùng limiter thực có trạng thái chia sẻ giữa các instance.
QuotaDecision decision = quotaService.tryConsume(
        authenticatedTenantId,
        "POST:/api/reports",
        10 /* cost của một lần tạo báo cáo */);

if (!decision.allowed()) {
    throw new QuotaExceededException(
            decision.retryAfterSeconds());
}

// Chỉ đi vào xử lý nghiệp vụ khi quota được chấp nhận.
return reportService.createReport(command);
~~~

**Không đưa tenantId do client tự nhập vào đây nếu chưa xác thực và xác minh quyền.** Hệ thống cần quy định khi nào quota bị tính: request được chấp nhận, request xử lý thành công, hay tác vụ thực sự hoàn tất; mỗi lựa chọn có tác động công bằng và chi phí. Nếu giới hạn theo số tác vụ đang chạy, điểm tính/quy hoàn quota phải khớp vòng đời job.

### 11.3. Filter, proxy và Spring Security

Một gateway có thể trả 429 **trước khi request đến Spring**, nên exception handler phía ứng dụng không thay được chính sách của gateway. Khi ứng dụng tự áp dụng hạn mức:

- Phân biệt **đối tượng đã xác thực** với IP công khai để chọn quota key.
- Không vô tình chặn **CORS preflight OPTIONS** như một thao tác nghiệp vụ có chi phí lớn.
- Giữ hành vi **401/403** rõ ràng với quyền truy cập, đồng thời giới hạn thô ở edge khi có nguy cơ abuse.
- Chỉ tin thông tin forwarding từ reverse proxy tin cậy.
- Đảm bảo mọi phản hồi 429, kể cả từ gateway, có **request ID**, CORS và định dạng lỗi nhất quán khi khả thi.

Trong kiến trúc sử dụng nhiều filter, thứ tự **security → định danh quota → application** và điểm chặn thực tế cần được thiết kế theo rủi ro. Một endpoint login chưa xác thực thường cần giới hạn theo IP/định danh được chuẩn hóa; endpoint nghiệp vụ có thể cần quota theo tenant.

## 12. Mô tả trong OpenAPI

Hợp đồng OpenAPI nên khai báo **429**, **Retry-After**, cấu trúc **Problem Details** và những mã khác có thể xuất hiện trong tình huống giới hạn. Ví dụ OpenAPI 3.1 rút gọn cho thao tác tạo báo cáo:

~~~yaml
openapi: 3.1.0
info:
  title: Report API
  version: 1.0.0
paths:
  /api/reports:
    post:
      summary: Tạo yêu cầu tạo báo cáo
      description: >
        Có giới hạn tần suất và hạn mức theo tenant.
        Yêu cầu đã được nhận bền vững sẽ trả 202.
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
      responses:
        '202':
          description: Đã nhận yêu cầu và bắt đầu xử lý bất đồng bộ
        '429':
          description: Vượt hạn mức áp dụng cho bên gọi
          headers:
            Retry-After:
              description: >
                Số giây không âm hoặc ngày HTTP; có thể vắng mặt
                khi không xác định được thời điểm thử lại phù hợp.
              schema:
                type: string
              example: "30"
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  type:
                    type: string
                    format: uri-reference
                  title:
                    type: string
                  status:
                    type: integer
                    enum: [429]
                  detail:
                    type: string
                  code:
                    type: string
                    example: RATE_LIMIT_EXCEEDED
        '503':
          description: Tạm không thể tiếp nhận an toàn do dịch vụ quá tải
~~~

Đoạn YAML minh họa **hợp đồng được API chủ động chọn**. Nếu API không hỗ trợ idempotency key hoặc không trả 202, tài liệu phải được sửa theo hành vi thật. Với API do gateway áp quota, cần phối hợp để **tài liệu, phản hồi gateway và response ứng dụng thống nhất**.

Không nên biến mọi trường mô tả quota thành bắt buộc nếu tầng gateway không thể cung cấp chính xác. Hãy nêu rõ **giới hạn theo route, tenant, chi phí request, phiên bản API và chính sách thay đổi hạn mức** trong tài liệu dành cho client.

## 13. Kiểm thử API và hành vi client

### 13.1. Kiểm tra 429 bằng curl

~~~bash
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  https://api.example.test/api/reports
~~~

Thay host và token bằng giá trị trong môi trường thử nghiệm. Để kiểm tra 429, cần **cấu hình quota nhỏ dành cho test**, ví dụ 2 request trong một cửa sổ phù hợp, hoặc dựng một mock limiter có đồng hồ điều khiển. Không nên tạo flood request trên hệ thống production chỉ để ép phát sinh 429.

Khi nhận 429, kiểm tra:

- Status đúng **429 Too Many Requests**.
- **Retry-After** nếu có: là số giây nguyên không âm hoặc ngày HTTP hợp lệ.
- Body lỗi được định nghĩa rõ; không lộ thông tin nhạy cảm.
- Request bị từ chối không tạo side effect.
- Sau khi quota có lại, request hợp lệ có thể được xét tiếp theo chính sách.

### 13.2. Ma trận test quan trọng

| Tình huống | Điều cần chứng minh |
|---|---|
| Dưới ngưỡng quota | Request đi tới xử lý thông thường; quota bị trừ theo đúng chính sách |
| Đúng ranh giới giới hạn | Không bị off-by-one; request thứ N và N+1 cho kết quả dự kiến |
| Hai request đồng thời tranh token cuối | Chỉ một request tiêu thụ token nếu policy yêu cầu atomic |
| Burst sát ranh giới hai phút | Không vượt giới hạn burst đã cam kết |
| Nhiều instance xử lý cùng API key | Quota tổng vẫn đúng, không nhân theo số instance |
| Hai tenant độc lập | Tenant A vượt giới hạn không chặn oan B |
| Một tenant qua nhiều API key | Hạn mức theo tenant vẫn có tác dụng nếu hợp đồng yêu cầu |
| Retry-After dạng giây | Client đọc đúng giây và đợi phù hợp |
| Retry-After dạng HTTP-date | Client parse ngày HTTP, xử lý clock skew |
| Không có Retry-After | Client dùng backoff/jitter, không retry vòng lặp nóng |
| POST tạo đơn hoặc thanh toán bị từ chối | Không tạo giao dịch trùng hoặc phản hồi thành công giả |
| Redis/quota store gặp lỗi | Hành vi fail-open/fail-closed/fallback đúng thiết kế |
| 429 do gateway tạo | CORS, body, request ID, logs và tài liệu không mâu thuẫn |
| 503 do service quá tải | Client phân biệt nguyên nhân với 429 |
| API bị giới hạn quota ngày | Không bảo client retry vô hạn mỗi giây |
| CORS preflight và 429 từ request thật | Browser đọc được status, body và Retry-After khi policy cho phép |

### 13.3. Kiểm thử với đồng hồ giả

Thay vì ngủ nhiều giây trong unit test, dùng một **clock có thể điều khiển** để kiểm tra refill/reset:

~~~text
Given: capacity=2, refill=1 token/second, tokens=2
At t=0.0s:
    request A -> ACCEPT
    request B -> ACCEPT
    request C -> 429; Retry-After khoảng 1 giây

Advance clock to t=1.0s, không có request trung gian:
    request D -> ACCEPT
    request E -> 429; Retry-After khoảng 1 giây

Concurrent test:
    đưa bucket về 1 token
    gửi đồng thời 2 request cho cùng quota key
    assert đúng 1 ACCEPT, đúng 1 REJECT
~~~

Trong triển khai thực tế, tính Retry-After phải tuân thủ cách làm tròn số giây của contract. Test cần xác minh **atomicity**, **phạm vi quota** và trường hợp race condition; không chỉ so sánh thuật toán với chính nó.

## 14. Quan sát, bảo mật và vận hành quota

### Metric nên theo dõi

| Chỉ số | Câu hỏi vận hành |
|---|---|
| **Allowed vs rejected requests** theo route/tenant/tier | Ai đang chạm giới hạn, ở khu vực nào? |
| **429 rate** và tỷ lệ 429/total | Chặn phù hợp với dự kiến hay quota quá chặt? |
| **Retry-After distribution** | Người dùng phải chờ bao lâu? |
| **p95/p99 latency** của bước kiểm tra quota | Limiter có thành nút thắt không? |
| **Quota store errors/timeouts** | Có fail-open/fail-closed bất thường không? |
| **5xx/503 và downstream saturation** | Hạn mức có bảo vệ được tài nguyên không? |
| **Client retry rate / burst patterns** | Client có đang tạo retry storm không? |
| **Cost per tenant/endpoint** | Chính sách có phù hợp chi phí compute, database, API bên thứ ba? |

**429 không phải lúc nào cũng là sự cố hệ thống.** Trong nhiều dịch vụ, một số phản hồi 429 là cơ chế bảo vệ có chủ đích. Cảnh báo nên tập trung vào **tỷ lệ tăng bất thường, nhóm khách bị ảnh hưởng, lỗi cấu hình, tỷ lệ 503, vi phạm SLO hoặc quota store lỗi**, thay vì mặc định mọi 429 đều là pager incident.

### Bảo mật và công bằng

- Tránh phân loại quota chỉ theo dữ liệu client tự khai báo; xác minh tenant/identity trước khi gắn quota key.
- Không ghi raw token/API key vào log, metric labels hoặc error body; dùng định danh nội bộ an toàn.
- Tránh label theo số lượng user ID không giới hạn trong metrics, gây **cardinality cao**; dùng aggregate và truy vấn log theo yêu cầu.
- Thiết kế ưu tiên hợp lý cho endpoint đặc biệt như login, password reset, emergency/admin; vừa ngăn abuse vừa tránh khóa tất cả người dùng hợp lệ.
- Phân biệt request giá rẻ và tác vụ đắt; một endpoint tạo báo cáo nhiều phút không nên được bảo vệ bằng cùng một giới hạn request/giây đơn giản với GET metadata.
- Khi quota store hỏng, cần alert, owner, runbook và phương án tránh đẩy rủi ro sang database hoặc chi phí đối tác.

### Runbook khi 429 tăng đột ngột

1. Xác định **người gọi/tier/route**, thời điểm bắt đầu, phiên bản cấu hình mới và ảnh hưởng nghiệp vụ.
2. So sánh 429 với **lưu lượng hợp lệ, lỗi 5xx/503, CPU, DB connection, quota của downstream**.
3. Xác minh chính sách có được áp đúng đối tượng hay bị sai định danh sau thay đổi proxy/auth.
4. Kiểm tra **quy tắc rate/capacity**, TTL, thời gian refill và lỗi distributed state.
5. Nếu client tăng retry, hướng dẫn **backoff/jitter**, giảm concurrency hoặc phát cảnh báo quota từ SDK.
6. Chỉ thay quota sau khi biết **capacity headroom** và tác động công bằng; nâng quota không được làm sập hệ thống đích.
7. Sau khôi phục, so sánh SLO, hiệu suất, chi phí và ghi quyết định thay đổi chính sách.

## 15. Tình huống thực hành: API tạo báo cáo theo gói sử dụng

### Yêu cầu nghiệp vụ giả định

Một dịch vụ cung cấp REST API cho đối tác:

- **Basic:** 60 thao tác thông thường/phút, burst tối đa 20.
- **Pro:** 600 thao tác thông thường/phút, burst tối đa 100.
- **POST /api/reports** tiêu tốn **10 token** vì tạo job xử lý nền.
- **GET /api/reports/{id}** tiêu tốn **1 token** vì chỉ tra cứu trạng thái.
- Mỗi tenant được định danh qua API key đã xác thực; tenant có thể dùng nhiều key.
- Khi chạm hạn mức ngắn hạn, server cố gắng trả **Retry-After**.
- Một tenant có thể có **tối đa 5 report đang chạy** để bảo vệ worker pool.

Các thông số là **giả định để thiết kế**, không phải giới hạn của nhà cung cấp cloud cụ thể.

### Lựa chọn mô hình

Dùng **token bucket theo tenant**:

| Tier | Capacity | Refill | Thông lượng dài hạn giả định |
|---|---:|---:|---:|
| Basic | 20 token | 1 token/giây | Khoảng 60 token/phút |
| Pro | 100 token | 10 token/giây | Khoảng 600 token/phút |

Vì **POST tạo report tốn 10 token**, không nên hiểu Basic có thể tạo 60 báo cáo/phút. Nếu chỉ gọi POST, mức tiêu thụ dài hạn lý thuyết tương đương khoảng **6 lần tạo report/phút**, và concurrency limit 5 có thể tiếp tục hạn chế số job chạy.

### Tính thử một burst

Giả sử Basic có **20 token**, đồng thời gửi **5 request POST tạo report** ở cùng thời điểm, mỗi request cần 10 token. Nếu cập nhật quota atomic:

\[
\text{Số POST nhận ngay}=\left\lfloor \frac{20}{10}\right\rfloor=2.
\]

**2 request** được phép xét tiếp theo nghiệp vụ; **3 request** còn lại nhận 429 do quota. Sau khi tiêu hết token, cần khoảng **10 giây** để tích lại 10 token cho một POST mới (trong giả định không có request khác). Nếu server trả **Retry-After: 10**, đó chỉ là thời điểm **một POST** có thể có đủ token, không phải giấy phép cho cả ba request cùng được nhận.

Giả sử worker report đã có đủ **5 job đang chạy**. Một request mới có thể cần chờ slot, nhận 429 theo chính sách concurrency, hoặc được nhận vào queue và trả 202 nếu hệ thống bảo đảm tiếp nhận bền vững và công bố thời hạn hoàn thành. **Chọn một hợp đồng rõ ràng**, không nhận job vào hàng đợi rồi báo 429 như thể chưa nhận.

### Luồng client nên thực hiện

1. Đọc quota tài liệu, chủ động dùng client-side limiter theo tenant và trọng số.
2. Khi nhận 429, đọc Retry-After và thông báo người dùng thay vì gửi POST liên tục.
3. Gửi **Idempotency-Key** khi tạo report để tránh duplicate do timeout/retry.
4. Với **202 Accepted**, gọi status endpoint theo nhịp hợp lý, tránh việc polling quá nhanh làm tốn quota cho GET.
5. Khi quota ngày/tháng hết hoặc tài khoản không có quyền chức năng, đưa ra hướng xử lý khác, không chỉ “thử lại ngay”.

## 16. Bài tập và gợi ý lời giải

Một REST API quản lý đơn hàng áp dụng **token bucket** cho mỗi tenant với **capacity 30 token**, bổ sung **5 token/giây**; mỗi request GET tiêu thụ 1 token và mỗi POST tạo đơn tiêu thụ 6 token. Bucket đang đầy trước khi bắt đầu bài.

### Câu hỏi

1. Trong cùng một thời điểm, client gửi **45 GET** đồng thời. Bao nhiêu request được chấp nhận qua limiter, bao nhiêu request nhận 429, giả sử phép trừ token atomic?
2. Ngay sau burst, không có request mới trong **4 giây**. Bucket có bao nhiêu token?
3. Sau 4 giây, client gửi cùng lúc **25 GET**. Bao nhiêu GET có thể được chấp nhận?
4. Nếu bucket rỗng và client muốn gửi **POST tốn 6 token**, cần chờ tối thiểu bao nhiêu giây trong mô hình lý tưởng, không có request cạnh tranh?
5. Viết một response 429 hợp lệ cho trường hợp vừa hết token, gồm **Retry-After** và Problem Details.
6. Nếu client đã vượt quota **theo ngày** và server không biết thời điểm được nâng quota, có nên trả Retry-After: 1 không? Vì sao?
7. API đặt hàng đang gọi cổng thanh toán; response bị mất trên mạng sau khi thanh toán thành công. Vì sao không thể dựa vào retry HTTP đơn thuần để đảm bảo không trừ tiền hai lần?
8. Nếu tất cả tenant đều chưa vượt quota nhưng database production hết connection, **429 hay 503** phù hợp hơn cho lỗi thiếu khả dụng chung? Cần thêm cơ chế bảo vệ nào?
9. Hãy đề xuất tối thiểu **năm test** và **bốn metric** chứng minh giới hạn thực sự công bằng trên nhiều instance.

### Gợi ý đáp án

**Câu 1:** Có 30 token, mỗi GET tốn 1; **30 GET được limiter cho qua**, **15 GET trả 429**.

**Câu 2:** Không có request khác, sau 4 giây bổ sung \(4\times5=20\) token; bucket có **20 token**, chưa đạt capacity 30.

**Câu 3:** Với 20 token, **20 GET được cho qua**, **5 GET trả 429**.

**Câu 4:** POST cần 6 token; tại tốc độ 5 token/giây, thời gian lý tưởng là \(6/5=1{,}2\) giây. Nếu dùng header Retry-After dạng **delay-seconds**, giá trị số nguyên an toàn có thể là **2 giây** (làm tròn lên), trong điều kiện không có cạnh tranh và không có giới hạn khác.

**Câu 5:** Ví dụ khi vừa cần 1 token và phải đợi tối thiểu 0,2 giây, server có thể làm tròn lên:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 1
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Hạn mức ngắn hạn đã hết.",
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

**Câu 6:** Không. Nếu không có ước lượng đáng tin, nên bỏ Retry-After và cung cấp thông tin quota/hỗ trợ rõ ràng. Một giá trị ngắn gây retry storm nhưng không làm quota ngày được cấp lại.

**Câu 7:** Server có thể đã hoàn tất side effect dù client không nhận response. Cần **idempotency key bền vững**, khóa theo giao dịch nghiệp vụ, cơ chế tra cứu/đối soát và chính sách retry an toàn; không thể suy rằng timeout là “chưa thanh toán”.

**Câu 8:** Nếu đây là lỗi thiếu khả dụng **toàn dịch vụ**, **503** thường phù hợp hơn; có thể kèm Retry-After nếu biết thời điểm nên thử tiếp. Cần **global admission control, bounded concurrency, connection pool limits và backpressure**, bên cạnh quota theo tenant.

**Câu 9:** Kiểm thử **ranh giới capacity**, **đồng thời tranh token cuối**, **quota giữa nhiều pod**, **độc lập hai tenant**, **nhiều API key cùng tenant**, **clock/reset**, **quota store failure**, **POST với idempotency**. Theo dõi **allowed/rejected**, **429 rate theo route/tier**, **quota store latency/error**, **DB connection/503**, và **Retry-After distribution**.

### Tiêu chí đánh giá bài làm

| Nhóm năng lực | Điểm gợi ý | Điều kiện đạt |
|---|---:|---|
| Hiểu 429 và Retry-After | 25 | Chọn đúng status, hai dạng header, phân biệt 503 |
| Tính quota/token bucket | 25 | Tính đúng burst/refill và hiểu giới hạn Retry-After |
| An toàn khi retry | 20 | Idempotency, deadline, backoff/jitter, không nhân đôi giao dịch |
| Thiết kế phân tán | 15 | Atomic shared quota, multi-tenant fairness và bảo vệ downstream |
| Kiểm thử và quan sát | 15 | Test race condition, contract, metric và incident response |

## 17. Checklist cho API production

- [ ] Có **định nghĩa quota/rate limit rõ ràng** theo principal, tier, endpoint, thời gian và trọng số.
- [ ] Phân biệt **429** của bên gọi với **503** của lỗi thiếu khả dụng diện rộng.
- [ ] Response **429** có body đủ hiểu, status đúng và không làm rò rỉ dữ liệu nhạy cảm.
- [ ] **Retry-After** chỉ được gửi khi có ước lượng phù hợp; dùng đúng **giây nguyên không âm** hoặc **HTTP-date**.
- [ ] Không giả định Retry-After là lời bảo đảm; client có backoff, jitter, deadline và retry budget.
- [ ] Với POST/side effect, có **idempotency key**, trạng thái và cách đối soát khi response bị mất.
- [ ] Rate limit được kiểm tra **trước side effect** cho request bị từ chối; tránh “đã ghi rồi vẫn báo chưa nhận”.
- [ ] Nhiều instance dùng **atomic shared quota state** hoặc dịch vụ rate limit đủ tin cậy; không đếm sai theo pod.
- [ ] Có chính sách **fail-open/fail-closed/fallback** và runbook khi quota store lỗi.
- [ ] Bảo vệ IP/endpoint công khai, tenant, workload đắt tiền và **global downstream capacity** theo các lớp phù hợp.
- [ ] Nếu trả các header RateLimit tùy chọn, đã công bố **ngữ nghĩa, đơn vị, scope** và kiểm thử tính nhất quán.
- [ ] Phản hồi 429 không được HTTP cache lưu; CORS cho phép frontend đọc status/header cần thiết.
- [ ] OpenAPI và hành vi gateway/Spring đồng nhất; kiểm thử 429, 503, quota ngày và concurrent race.
- [ ] Quan sát được 429 theo tier/route, quota errors, retry storm, 5xx/503 và mức tiêu thụ tài nguyên.
- [ ] Quota được đánh giá lại bằng **số liệu tải, công bằng và chi phí** khi nghiệp vụ thay đổi.

**Điểm cần nhớ:** **429 Too Many Requests** cho biết bên gọi đang vượt chính sách hạn mức; **Retry-After** đề nghị một mốc thử lại nếu server có thể tính được. Thiết kế tốt phải có **quy tắc quota rõ, phản hồi HTTP nhất quán, client retry an toàn, bảo vệ hệ thống đích và khả năng quan sát trên toàn cụm**. Không tăng tốc retry chỉ để “vượt qua” 429: hãy điều chỉnh nhịp gửi và xử lý đúng ngữ nghĩa nghiệp vụ.

### Tài liệu chuẩn để tra cứu

- **RFC 6585 — Additional HTTP Status Codes:** mục 429 Too Many Requests và quy tắc không cache phản hồi 429.
- **RFC 9110 — HTTP Semantics:** định nghĩa Retry-After, HTTP-date, mã trạng thái và cách diễn đạt phản hồi.
- **RFC 9457 — Problem Details for HTTP APIs:** định dạng lỗi máy có thể đọc với media type application/problem+json.
- **OpenAPI Specification 3.1:** mô tả response 429, headers, schema lỗi và hợp đồng API.
