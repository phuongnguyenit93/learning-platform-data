# Timeout sau khi server đã xử lý và kết quả không xác định

## 1. Bối cảnh: không nhận được phản hồi không có nghĩa thao tác thất bại

Trong một REST API, client gửi yêu cầu qua mạng và nhận phản hồi HTTP. Nhưng giữa hai hành động ấy có nhiều điểm lỗi: kết nối bị cắt, reverse proxy hết thời gian chờ, client đóng ứng dụng, server restart, phản hồi bị mất hoặc gateway trả timeout dù hệ thống phía sau vẫn tiếp tục xử lý.

Xét yêu cầu tạo đơn:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <test-token>
Content-Type: application/json
Idempotency-Key: order-attempt-7f2d

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":2}]}
~~~

Server có thể đã **lưu đơn và commit transaction**, nhưng phản hồi 201 Created không tới được client. Client chỉ biết rằng thời gian chờ đã hết; nó **không biết chắc** kết quả nghiệp vụ. Nếu ứng dụng lập tức tạo một yêu cầu mới với idempotency key khác, nó có thể tạo hai đơn. Với thanh toán, sai lầm tương tự có thể dẫn tới thu tiền hai lần.

Bài học này thuộc chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**, nơi HTTP method, mã trạng thái, hợp đồng dữ liệu, xác thực, phân quyền, xử lý lỗi và kiểm thử phải phối hợp để tạo ra thao tác đáng tin cậy.

Sau bài học, người học có thể:

1. Phân biệt **request thất bại có xác nhận**, **thành công có xác nhận** và **kết quả chưa xác định** sau timeout.
2. Giải thích tại sao **HTTP timeout không phải transaction rollback** và tại sao retry mù quáng nguy hiểm.
3. Thiết kế idempotency key, request fingerprint, phạm vi key, chính sách lưu giữ và cách trả kết quả khi retry.
4. Đặt ranh giới transaction để chống tạo trùng khi hai request đồng thời hoặc server crash sau commit.
5. Phân biệt xử lý DB cục bộ với side effect tới cổng thanh toán, message broker và đối tác bên ngoài.
6. Thiết kế endpoint tra cứu trạng thái, reconciliation, retry/backoff, HTTP/OpenAPI contract và xử lý lỗi.
7. Kiểm thử bằng cách cố ý gây timeout tại những thời điểm nguy hiểm nhất.

> **Nguyên tắc cốt lõi:** Timeout nói về *việc quan sát kết quả qua kênh giao tiếp*, không tự khẳng định *trạng thái đã được commit của nghiệp vụ*. Khi kết quả chưa xác định, trước hết phải dùng cơ chế định danh/tra cứu đáng tin cậy để xác định hoặc tiếp tục **cùng một thao tác**, không tự tạo thao tác mới.

## 2. Các mốc lỗi và “kết quả không xác định”

### 2.1. Cùng một timeout, bốn diễn biến khác nhau

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Orders API
    participant D as Database
    C->>G: POST /orders (key K)
    G->>A: Chuyển yêu cầu
    A->>D: INSERT order + idempotency record
    D-->>A: COMMIT thành công
    A-->>G: 201 Created
    Note over G,C: Kết nối lỗi hoặc client hết thời gian chờ
    G--xC: Phản hồi không đến client
    Note over C: Không biết đơn đã được tạo
~~~

Một request có thể kết thúc theo nhiều cách:

| Tình huống | Server đã thực hiện gì? | Client quan sát được gì? | Có thể kết luận gì? |
|---|---|---|---|
| A. Không đến server | Không nhận yêu cầu | Network error / timeout | Thao tác ở server chưa thực hiện **nếu có bằng chứng chắc chắn request chưa tới** |
| B. Đang xử lý | Có thể đã ghi tạm trong transaction hoặc gọi dependency | Timeout | Chưa biết sẽ commit hay rollback |
| C. Đã commit | Đơn được ghi bền vững | Timeout hoặc connection reset | Thành công nghiệp vụ có thể đã xảy ra |
| D. Đã trả phản hồi nhưng bị mất | Có kết quả HTTP 2xx/4xx/5xx nào đó nhưng client không nhận | Timeout | Không biết kết quả nào đã được trả hoặc trạng thái cuối |

Tại client, các tình huống B, C và D thường **không thể phân biệt chỉ bằng một timeout**. Thậm chí lỗi kết nối xảy ra sớm không phải lúc nào cũng chứng minh server chưa nhận dữ liệu vì các tầng mạng và proxy có thể đã chuyển tiếp.

### 2.2. Ba trạng thái nhận thức quan trọng

| Trạng thái của client | Điều kiện | Hành động hợp lý |
|---|---|---|
| **Confirmed success** | Đã nhận kết quả thành công có thể xác minh hoặc tra cứu thấy outcome đã commit | Hiển thị trạng thái nghiệp vụ, không tạo giao dịch mới |
| **Confirmed failure** | Có phản hồi đáng tin cậy cho thấy yêu cầu bị từ chối mà chưa sinh side effect theo hợp đồng | Sửa lỗi hoặc khởi tạo thao tác mới khi phù hợp |
| **Unknown outcome** | Timeout, network reset, gateway timeout, crash, phản hồi mơ hồ | Tra cứu operation/key; retry **cùng key** theo hợp đồng; reconciliation khi cần |

Đặc biệt, **HTTP 500 không luôn có nghĩa nghiệp vụ đã rollback** nếu hệ thống có side effect trước khi phát sinh lỗi. Ví dụ cổng thanh toán đã ghi giao dịch rồi server gặp lỗi khi lưu receipt: response 500 không thể xóa việc thu tiền ở đối tác. Phải phân tích ranh giới commit và nguồn sự thật.

### 2.3. Những cửa sổ nguy hiểm

~~~text
T0  Client tạo operation ID / idempotency key K
T1  Client gửi POST K
T2  API nhận và kiểm tra K
T3  API bắt đầu transaction hoặc gọi hệ thống ngoài
T4  DB commit / đối tác đã xử lý
T5  API dựng response
T6  Gateway gửi response
T7  Client nhận response

         [T1......................T7]
             timeout có thể xảy ra ở nhiều thời điểm
                       ^--- T4: nghiệp vụ đã hoàn tất
                       ^------- T6: response có thể bị mất
~~~

Nếu client chỉ kiểm soát timeout đến T7, nó không có quyền suy luận rằng T4 chưa xảy ra. **Một giao thức retry đúng phải chịu được cửa sổ “đã commit nhưng chưa nhận ACK/HTTP response”.**

## 3. Timeout, HTTP status và retry không phải là một khái niệm

### 3.1. Các kiểu timeout thường gặp

| Loại | Ví dụ | Cần phân biệt |
|---|---|---|
| **Connect timeout** | Không thiết lập kết nối TCP/TLS trong hạn | Có thể chưa gửi request, nhưng không biến thành quy tắc tạo key mới khi chưa chắc |
| **Read/response timeout** | Đã gửi request nhưng chờ phản hồi quá lâu | Outcome ở server có thể đã commit |
| **Gateway timeout** | Gateway trả **504 Gateway Timeout** vì upstream không phản hồi kịp | Upstream có thể tiếp tục và commit |
| **Server request timeout** | Server trả **408 Request Timeout** theo ngữ nghĩa không nhận đủ request trong hạn | Không đồng nghĩa với 504 hoặc transaction rollback |
| **Client disconnect** | Browser/app đóng kết nối khi request đang chạy | Backend có thể vẫn thực hiện, tùy framework/cancellation |
| **Dependency timeout** | Orders API gọi payment provider và không nhận được response | Provider có thể đã thu tiền |

Một số proxy ghi **499** trong access log khi client đóng kết nối. **499 không phải mã trạng thái HTTP chuẩn** để thiết kế hợp đồng công khai; đó là mã ghi nhận riêng của một số hệ thống.

### 3.2. Các mã HTTP hữu ích trong contract

| Tình huống có thể xác nhận | Mã gợi ý | Ý nghĩa và lưu ý |
|---|---|---|
| Đơn được tạo đồng bộ | **201 Created** | Có thể kèm Location tới tài nguyên đơn |
| Thao tác được tiếp nhận, kết quả cuối chưa có | **202 Accepted** | Cần URI/trạng thái theo dõi; không tuyên bố đã hoàn tất |
| Đọc operation đang xử lý | **200 OK** với state PROCESSING | GET trả trạng thái hiện hành của operation |
| Retry cùng key, cùng payload sau khi hoàn tất | Trả lại kết quả đã lưu theo contract, ví dụ **201** | Không thực thi side effect mới |
| Retry cùng key nhưng payload khác | **409 Conflict** theo chính sách API | Cùng key không được dùng cho hai ý định khác nhau |
| Thao tác đang được xử lý với cùng key | **202**, hoặc **409** kèm thông tin còn xử lý theo hợp đồng | Không chạy song song side effect |
| Quá nhiều request | **429 Too Many Requests** | Retry-After có thể chỉ thời gian thử lại |
| Tạm không thể phục vụ | **503 Service Unavailable** | Có thể gửi Retry-After; client vẫn cần giữ key nếu outcome mơ hồ |
| Gateway không chờ được upstream | **504 Gateway Timeout** | Không được hiểu là server chắc chắn không xử lý |
| Precondition cập nhật không đạt | **412 Precondition Failed** | Không dùng retry mù để vượt concurrency control |

**Không có một mã HTTP duy nhất mang nghĩa “server có thể đã commit nhưng tôi chưa biết”.** Bản thân client gặp network timeout thậm chí không nhận được status nào. API phải dùng **hợp đồng idempotency, operation status và đối soát** để giải quyết sự không chắc chắn đó.

### 3.3. Một lời cảnh báo về “retry 5xx”

Không nên thiết kế quy tắc “hễ 5xx thì gửi POST mới”:

- 5xx nói rằng server hoặc tầng trung gian gặp vấn đề, **không chắc side effect chưa xảy ra**.
- 504 thường phản ánh giới hạn chờ của gateway, không phải rollback của upstream.
- 503 có thể có Retry-After, nhưng lần gửi lại POST vẫn phải được chống trùng.
- Nếu một request đã được tiếp nhận và đang chạy, retry liên tục có thể tạo thêm tải và khiến outage trầm trọng hơn.

Một chính sách retry cần xét **method, khả năng idempotent ở nghiệp vụ, thời gian còn lại, loại lỗi, idempotency key và cơ chế tra cứu outcome**.

## 4. HTTP idempotency khác cơ chế idempotency key

### 4.1. Ngữ nghĩa HTTP method

| Method | Idempotent theo HTTP? | Lưu ý trong bài toán timeout |
|---|---|---|
| **GET** | Có | Đọc lại không có nghĩa được bỏ qua kiểm tra quyền; dữ liệu có thể đổi giữa hai GET |
| **HEAD** | Có | Tương tự GET nhưng không yêu cầu response body |
| **PUT** | Có | Cùng một PUT hợp lệ hướng tới cùng trạng thái tài nguyên; response có thể khác, log/counter phụ trợ vẫn có thể thay đổi |
| **DELETE** | Có | Retry DELETE có thể nhận 204 lần đầu, 404 lần sau tùy contract; effect xóa không nhân đôi |
| **POST** | Không mặc nhiên | Tạo đơn, charge payment, phát lệnh phải có bảo vệ riêng khi cần retry |
| **PATCH** | Không mặc nhiên | PATCH kiểu cộng thêm số lượng sẽ lặp hiệu ứng nếu gửi lại; một PATCH cụ thể có thể thiết kế idempotent |

**Idempotent không nghĩa là mọi lần request trả cùng status/body**, cũng không nghĩa request được đảm bảo chạy một lần. Nó có nghĩa nhiều request giống nhau có tác động dự kiến lên trạng thái server giống với một request theo ngữ nghĩa của method.

Ví dụ:

~~~http
PUT /api/users/u-42/preferences HTTP/1.1
Content-Type: application/json

{"theme":"dark"}
~~~

Gửi lại cùng representation thường vẫn đặt theme thành dark. Nhưng:

~~~http
PATCH /api/counters/42 HTTP/1.1
Content-Type: application/json

{"incrementBy":1}
~~~

có thể tăng giá trị thêm một lần nữa nếu gửi lại. Với API POST/ PATCH có side effect, cần idempotency key hoặc cơ chế concurrency control phù hợp.

### 4.2. Idempotency-Key là hợp đồng ứng dụng

Nhiều API sử dụng header **Idempotency-Key**:

~~~http
Idempotency-Key: order-attempt-7f2d
~~~

Header này không phải một đảm bảo “tự động” của HTTP server/proxy: ứng dụng phải **định nghĩa phạm vi, kiểm tra và lưu bền vững**. Tên header xuất hiện trong các API thực tế và công việc chuẩn hóa IETF, nhưng client không được mặc định bất kỳ REST API nào cũng hỗ trợ nó nếu OpenAPI/hợp đồng chưa công bố.

Một cơ chế đúng cần trả lời:

1. Một key đại diện cho **ý định nghiệp vụ nào**?
2. Key có hiệu lực trong **phạm vi tenant/user, route/operation, môi trường** nào?
3. Nếu cùng key đi với **payload khác** thì xử lý ra sao?
4. Nếu hai request cùng key đến **đồng thời** thì request nào được thực thi?
5. Key và outcome được lưu **bao lâu**, có bền vững qua restart/failover không?
6. Nếu server xử lý xong nhưng mất response thì client nhận lại điều gì?
7. Khi gọi external provider hoặc phát event, chống side effect trùng như thế nào?

### 4.3. Retry dùng lại cùng key, không tạo key mới

Với cùng một ý định tạo đơn:

~~~text
Lần 1: POST /orders, key=K, payload=P -> timeout
Lần 2: POST /orders, key=K, payload=P -> kết quả của cùng operation
~~~

Không làm:

~~~text
Lần 1: POST /orders, key=K1, payload=P -> timeout
Lần 2: POST /orders, key=K2, payload=P -> có thể tạo đơn thứ hai
~~~

Client phải tạo key **trước khi phát request lần đầu** và giữ nó cùng payload/operation trong khi retry, kể cả khi app reconnect. Nếu người dùng chủ động tạo **một đơn mới thực sự**, cần một key mới để phân biệt ý định mới.

## 5. Thiết kế hợp đồng Idempotency-Key

### 5.1. Phạm vi key phải rõ ràng

Một khóa như order-attempt-7f2d không nên được so sánh **toàn hệ thống** mà thiếu ngữ cảnh. Ví dụ hợp đồng OmniOrder định nghĩa:

~~~text
Idempotency identity =
  tenant đã xác thực
  + loại thao tác (POST /api/orders)
  + Idempotency-Key do client tạo
~~~

Với cùng phạm vi này, key chỉ đại diện cho **một ý định tạo một đơn**, bất kể request đến replica A hay replica B. Hai tenant khác nhau có thể tình cờ dùng cùng key mà không trộn kết quả. Khi authorization thay đổi, server phải **kiểm tra quyền hiện tại trước khi replay response**, không dùng key làm bằng chứng sở hữu đơn.

Khuyến nghị thực hành:

- Dùng khóa có độ ngẫu nhiên cao và đủ khó đoán, chẳng hạn UUID v4 hoặc chuỗi ngẫu nhiên an toàn.
- Phát sinh key ở client trước lần gửi đầu và lưu với trạng thái pending.
- Không tái sử dụng một key cho một ý định mới, ngay cả khi payload trông giống hệt.
- Định nghĩa độ dài/định dạng tối đa để tránh lạm dụng bộ nhớ và log.
- Không nhét token, số thẻ, thông tin cá nhân hoặc payload nghiệp vụ vào key.
- Không dùng raw key làm metric label có cardinality rất cao hoặc đưa vào URL công khai.

### 5.2. Request fingerprint: cùng key phải cùng ý định

Nếu client vô tình gửi:

~~~text
POST /orders, key=K, items=[BOOK x1]
POST /orders, key=K, items=[BOOK x3]
~~~

thì request thứ hai **không phải retry tương đương**. Server nên từ chối với mã như **409 Conflict** và mã lỗi máy đọc được, thay vì trả đơn cũ hoặc tạo đơn mới.

Một bảng dữ liệu có thể lưu **request fingerprint**:

~~~text
fingerprint = digest(
    method
    + normalized operation identity
    + canonical request payload / relevant headers
)
~~~

Cách chuẩn hóa phụ thuộc hợp đồng:

- Nếu yêu cầu cùng key phải có **bytes JSON giống hệt**, có thể hash raw body đã giới hạn kích thước; hai JSON chỉ khác khoảng trắng vẫn sẽ khác fingerprint.
- Nếu yêu cầu cùng **ý nghĩa dữ liệu**, canonicalize JSON theo quy tắc được công bố: thứ tự key, default values, number representation, Unicode, null/missing, item order nếu có ý nghĩa.
- Với API có schema version hoặc các header ảnh hưởng lệnh, phải đưa yếu tố đó vào operation identity/fingerprint.
- Một hash thông thường không thay thế authorization và không chứng minh bên gửi sở hữu tài nguyên. Với payload nhạy cảm và không gian giá trị nhỏ, cân nhắc HMAC phía server để tránh lộ thông tin từ digest lưu trữ.

**Không dùng hash một cách ngây thơ rồi coi là “chắc chắn cùng thao tác”.** Sự khác biệt giữa 1, 1.0, trường thiếu và null, thứ tự phần tử hoặc địa chỉ hóa tiền tệ có thể quan trọng. Hợp đồng phải định nghĩa chính xác cái gì được xem là cùng request.

### 5.3. Kết quả được giữ trong bao lâu?

Một key không thể được giữ vô hạn trong mọi hệ thống. API cần công bố:

| Quy tắc | Ví dụ minh họa |
|---|---|
| Phạm vi | Theo tenant và operation POST /api/orders |
| Thời gian giữ outcome | 24 giờ kể từ khi hoàn tất, **chỉ là giả định ví dụ** |
| Cùng key + cùng fingerprint trong thời gian giữ | Không thực thi lại; trả kết quả hoặc trạng thái cùng operation |
| Cùng key + khác fingerprint | 409 Conflict |
| Key đã hết hạn | Contract phải nói rõ: có thể bị xem là ý định mới, hoặc yêu cầu tra cứu/đối soát trước |
| Xử lý đang dở | 202 với URI trạng thái hoặc phản hồi xung đột tạm theo chính sách |
| Bảo mật | Key không phải credential; kết quả vẫn phải qua authentication/authorization |

**TTL không phải cửa sổ bảo đảm trọn đời.** Nếu client offline lâu hơn thời gian lưu idempotency record, retry cùng key có thể tạo nghiệp vụ mới nếu server đã quên key. Với thanh toán, chuyển tiền, đặt chỗ hoặc nghiệp vụ không được phép trùng, cần thêm **business unique identifier**, ledger bền vững, operation lookup hoặc đối soát với hệ thống nguồn sự thật. Không dựa riêng vào TTL 24 giờ để cam kết không bao giờ thu tiền trùng.

### 5.4. Quy tắc trả lại kết quả

Một API đồng bộ có thể cam kết: sau khi tạo đơn thành công, retry cùng key/cùng payload sẽ **replay cùng kết quả ban đầu**:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/ord-741
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-741","status":"PENDING_PAYMENT"}
~~~

Client gửi lại cùng key thì **không tạo đơn thứ hai**; service lấy outcome đã lưu và trả lại response đã cam kết, ví dụ vẫn là 201 với Location ord-741.

Điều này **không bắt buộc theo HTTP**; đó là lựa chọn contract. Một API khác có thể dùng 200 cho replay hoặc chuyển client đến operation status. Phải mô tả trong OpenAPI và kiểm thử từng client. Nếu lưu response snapshot, trạng thái trong body replay có thể là **ảnh chụp thời điểm lần đầu**, không phải trạng thái đơn hiện tại. Khi cần trạng thái mới nhất, client nên GET tài nguyên ở Location.

### 5.5. Những phản hồi nào cần lưu?

Không nên lưu mọi status thiếu phân biệt:

- **Lỗi validation trước khi thực thi** như 400/422: có thể từ chối mà chưa “chiếm” key, nếu hợp đồng quy định rõ.
- **Thành công sau commit:** nên lưu outcome một cách bền vững cùng side effect nghiệp vụ.
- **Từ chối nghiệp vụ có tính kết luận:** có thể lưu một terminal result nếu nó thuộc cùng ý định và cần replay ổn định.
- **Lỗi hệ thống/transient:** không tự ghi một bản 500 “FINAL” nếu side effect bên dưới có thể đã hoàn tất. Cần đánh dấu/đối soát trạng thái trước khi quyết định retry thực thi.

Một provider thương mại cụ thể có thể chọn “cache kết quả đầu tiên kể cả 500”, nhưng không nên biến đó thành quy tắc chung cho mọi REST API. Chính sách của bài tập ưu tiên **outcome được xác minh**, còn kết quả chưa biết phải chuyển sang trạng thái cần tra cứu/phục hồi.

## 6. Trạng thái xử lý: key chưa có, đang chạy, hoàn tất và cần đối soát

Một hệ thống có thể lưu bản ghi operation với state machine:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED: Nhận key hợp lệ
    ACCEPTED --> PROCESSING: Bắt đầu thực thi
    PROCESSING --> SUCCEEDED: Commit outcome được xác minh
    PROCESSING --> FAILED_FINAL: Từ chối nghiệp vụ có kết luận
    PROCESSING --> RECONCILE: Dependency timeout / crash nghi ngờ side effect
    RECONCILE --> SUCCEEDED: Đối soát chứng minh đã hoàn tất
    RECONCILE --> FAILED_FINAL: Đối soát chứng minh không thực hiện / thất bại cuối
    RECONCILE --> PROCESSING: Có căn cứ an toàn để tiếp tục cùng operation
    ACCEPTED --> FAILED_FINAL: Bị từ chối trước thực thi theo contract
~~~

Các state là **mô hình ứng dụng**, không phải các status code HTTP. Một request HTTP có thể hết thời gian chờ trong lúc operation vẫn PROCESSING; ngược lại, operation có thể SUCCEEDED dù response đã bị mất.

| State | Có thể biết gì? | Hành vi khi retry cùng key |
|---|---|---|
| **Không có record** | Chưa thấy key trong store hiện tại | Có thể bắt đầu lệnh, nhưng phải xét TTL và business uniqueness |
| **ACCEPTED** | Hệ thống đã nhận ý định | Không tạo bản mới; trả status/operation ID |
| **PROCESSING** | Một worker/instance đang thực hiện | Không chạy song song side effect; trả status, đợi có giới hạn hoặc retry later |
| **SUCCEEDED** | Outcome đã xác minh | Replay outcome hoặc trả link tới tài nguyên đã tạo |
| **FAILED_FINAL** | Thao tác đã kết thúc với kết quả từ chối xác định | Replay failure theo contract, không chạy lại âm thầm |
| **RECONCILE** | Có khả năng đã xảy ra side effect ngoài hệ thống nhưng chưa biết kết quả | Tra cứu nguồn sự thật; không charge/tạo lại tùy tiện |

### 6.1. Đừng nhầm “đang PROCESSING” với “đã bị treo”

Một record PROCESSING có thể là:

- Request thật đang chạy tại một instance.
- Worker đã restart sau khi bắt đầu.
- Lease đã hết hạn nhưng external provider vẫn có thể đang xử lý.
- Transaction nội bộ đã commit nhưng cập nhật trạng thái operation bị lỗi.

Không nên chỉ dùng quy tắc “sau 30 giây thì cho request mới chạy lại” mà không có **lease, fencing token, owner hoặc kiểm tra trạng thái tại nguồn sự thật**. Worker cũ có thể vẫn đang chạy và tạo side effect sau khi worker mới lấy việc.

### 6.2. Terminal state và nguồn sự thật

Với một order chỉ dùng một DB, **orders row và idempotency outcome** có thể cùng commit một transaction. Với payment provider, nguồn sự thật cho lệnh thu tiền có thể là provider ledger; local operation record chỉ là trạng thái quan sát của hệ thống của bạn. Muốn chuyển từ RECONCILE sang SUCCEEDED, có thể cần query provider theo **merchant reference / provider idempotency key** và đối soát số tiền, currency, khách hàng, trạng thái.

## 7. Hai request đến đồng thời: cần tính nguyên tử

Giả sử hai request có cùng key K đến hai replica:

~~~mermaid
sequenceDiagram
    participant C1 as Client retry A
    participant A as API replica A
    participant DB as Durable store
    participant B as API replica B
    participant C2 as Client retry B
    C1->>A: POST K, payload P
    C2->>B: POST K, payload P
    A->>DB: Atomic claim scoped key K
    B->>DB: Atomic claim scoped key K
    DB-->>A: Claim thành công
    DB-->>B: Đã có owner / chờ outcome
    A->>DB: Thực thi và commit kết quả
    DB-->>A: Outcome ord-741
    B->>DB: Đọc outcome của K
    DB-->>B: Outcome ord-741
    A-->>C1: 201 ord-741
    B-->>C2: Cùng outcome / status
~~~

**Không an toàn:**

~~~text
if (!repository.existsByKey(key)) {
    createOrder();
    repository.saveKey(key);
}
~~~

Hai instance có thể đều thấy “key chưa tồn tại”, rồi cả hai cùng tạo order. Đây là lỗi **check-then-act race**. Chỉ một cache cục bộ trong JVM hoặc synchronized block ở một replica không giải quyết được khi có nhiều instance, restart hoặc failover.

### 7.1. Những cơ chế atomic claim có thể dùng

- **Unique constraint** trên (tenant_id, operation_type, idempotency_key) trong một database bền vững.
- Transaction và row-level locking hoặc thao tác INSERT ... ON CONFLICT phù hợp với DB.
- Conditional write / compare-and-swap trên một store có tính nhất quán và khả năng lưu bền vững phù hợp.
- Một durable queue với consumer ownership và business uniqueness, nếu luồng được thiết kế theo job bất đồng bộ.

Nút thắt cốt lõi không phải dùng đúng sản phẩm database nào mà là **một thao tác kiểm tra/claim nguyên tử có hiệu lực xuyên mọi replica**, kết hợp một quy trình commit outcome đáng tin cậy.

### 7.2. Bảng idempotency mẫu

Với PostgreSQL, một schema minh họa:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id          text NOT NULL,
    operation_type     text NOT NULL,
    idempotency_key    text NOT NULL,
    request_hash       text NOT NULL,
    state              text NOT NULL,
    http_status        integer,
    resource_id        text,
    response_body      jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    completed_at       timestamptz,
    expires_at         timestamptz,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key),
    CHECK (state IN (
        'PROCESSING', 'SUCCEEDED', 'FAILED_FINAL', 'RECONCILE'))
);
~~~

Phải cân nhắc bảo mật và retention với response_body; không lưu token, mật khẩu hoặc dữ liệu thanh toán nhạy cảm chỉ để replay. Khi body có PII, có thể lưu **resource ID và response metadata an toàn**, tạo lại một representation phù hợp hợp đồng sau khi kiểm tra quyền, hoặc mã hóa dữ liệu outcome theo chính sách.

Khi lưu outcome cuối, **đừng cho phép thay đổi key hoặc request_hash**. Nếu một key bị tái sử dụng với payload khác, trả lỗi thay vì “reset record” cho hợp lệ.

### 7.3. Ranh giới transaction quyết định tính đúng

Trong trường hợp tạo đơn **chỉ dùng một relational DB**, có thể làm:

~~~text
BEGIN TRANSACTION
  1. Atomic claim (tenant, operation, key) với UNIQUE constraint
  2. Nếu key đã tồn tại: kiểm tra fingerprint và đọc outcome
  3. Nếu key mới:
       INSERT order
       INSERT event vào outbox (nếu cần)
       UPDATE idempotency_record thành SUCCEEDED,
              lưu orderId + response status/body
COMMIT
Trả HTTP 201 (response có thể bị mất)
~~~

Nếu transaction rollback, **không có order lẫn outcome thành công**. Nếu commit thành công nhưng response bị mất, retry cùng key đọc lại outcome đã lưu. Đây là cách đóng cửa sổ lỗi nguy hiểm giữa “đã ghi đơn” và “chưa lưu kết quả idempotency”.

Ngược lại, thiết kế:

~~~text
INSERT order; COMMIT
INSERT idempotency_record; COMMIT
~~~

có cửa sổ crash ở giữa: order đã tồn tại nhưng key chưa được ghi; retry có thể tạo trùng. Không thể giải quyết bằng việc chỉ “kiểm tra key trước khi chạy”.

### 7.4. Transaction DB không bao trùm cổng thanh toán

Một transaction database **không tự rollback** lệnh charge ở payment provider. Nếu gọi provider bên trong transaction, provider có thể hoàn tất rồi DB rollback; khóa DB còn bị giữ khi chờ network. Nếu gọi provider sau commit mà không có durable intent/outbox, server có thể crash làm mất bước tiếp theo.

Do đó, với side effect bên ngoài, cần thiết kế **workflow và reconciliation riêng**, được phân tích ở phần sau. Không dùng từ “exactly once” cho toàn hệ thống phân tán khi chưa định nghĩa rất cụ thể phạm vi và giả định lỗi.

## 8. Timeout khi gọi cổng thanh toán: xử lý unknown outcome ở nhiều hệ thống

### 8.1. Tình huống thu tiền có thể đã xảy ra

Hệ thống gửi:

~~~http
POST /provider/charges HTTP/1.1
Host: payment-provider.example.test
Authorization: Bearer <provider-test-token>
Idempotency-Key: merchant-charge-ord-741
Content-Type: application/json

{"merchantReference":"ord-741","amount":350000,"currency":"VND"}
~~~

Provider có thể đã tạo charge nhưng HTTP response bị timeout trên đường trở về:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders API
    participant D as DB + Outbox
    participant W as Payment Worker
    participant P as Payment Provider
    C->>O: POST /orders (key K)
    O->>D: Commit đơn + payment intent + outbox
    O-->>C: 202 + operation ID
    W->>D: Nhận durable payment intent
    W->>P: POST /charges với provider key cố định
    P->>P: Tạo charge thành công
    P--xW: Response bị timeout
    W->>D: Mark RECONCILE / giữ provider reference
    W->>P: Query status theo merchant reference
    P-->>W: Charge đã thành công
    W->>D: Ghi nhận kết quả có kiểm tra trạng thái
    C->>O: GET /operations/op-741
    O-->>C: 200 SUCCEEDED + resourceRef
~~~

**Điểm không thể bỏ qua:** Retry từ client và retry từ worker là hai lớp khác nhau. Một idempotency key của API bạn **không tự động bảo vệ cổng thanh toán**. Cần cơ chế của provider hoặc một định danh giao dịch nghiệp vụ có thể đối soát.

### 8.2. Thiết kế payment intent và provider reference

Một payment intent bền vững có thể có:

| Trường | Mục đích |
|---|---|
| payment_intent_id | ID nội bộ của ý định thanh toán, tạo một lần |
| order_id | Đơn liên quan, dùng kiểm tra invariant |
| merchant_reference | Định danh nghiệp vụ truyền cho provider |
| provider_idempotency_key | Key ổn định cho **cùng lệnh charge** tại provider |
| amount, currency | Các giá trị phải bất biến trong cùng lệnh |
| state | PENDING, PROCESSING, SUCCEEDED, FAILED_FINAL, RECONCILE |
| provider_charge_id | ID charge khi đã xác định |
| last_checked_at / attempts | Dữ liệu vận hành và reconciliation |

Đặt unique constraint phù hợp, ví dụ **một intent thu tiền chính cho một order và lần thanh toán được xác định rõ**, tùy quy tắc retry/đổi phương thức thanh toán. Không nên áp dụng cứng “mỗi order chỉ có một lần thanh toán trong lịch sử” nếu nghiệp vụ cho phép thất bại rồi thanh toán lại bằng intent **mới có kiểm soát**.

### 8.3. Khi provider hỗ trợ idempotency

1. Tạo provider idempotency key **một lần** cho intent và lưu bền vững.
2. Mỗi lần worker gửi lại **cùng lệnh, cùng key, cùng amount/currency/merchant reference**.
3. Trước retry, kiểm tra tài liệu provider về thời gian giữ key, trạng thái request đang chạy, lỗi có thể retry và cách đối soát.
4. Nếu provider trả charge đã tồn tại, cập nhật local state theo **kết quả xác minh**, không tạo charge mới.
5. Nếu provider response timeout mà không thể tra cứu, để operation ở **RECONCILE** và tiếp tục quy trình kiểm tra có giới hạn; không coi ngay là thất bại.

**Không mặc định** mọi provider cung cấp chính sách giống nhau về key expiration, replay status hoặc idempotency sau 500. Tài liệu/hợp đồng tích hợp của provider là nguồn quyết định.

### 8.4. Khi provider không hỗ trợ idempotency

Không thể tự “cài exactly-once HTTP call” trên một kết nối không đáng tin chỉ bằng cách retry. Các lựa chọn thực tế:

- Dùng **merchant reference duy nhất** nếu provider cho tra cứu và xử lý trùng theo reference.
- Tra cứu transaction ở provider theo khoảng thời gian, amount, currency, reference và account trước khi gửi lại.
- Chấp nhận trạng thái **cần xác minh thủ công** với giao dịch giá trị cao hoặc không có API tra cứu đáng tin.
- Thương lượng contract/bổ sung tích hợp để provider hỗ trợ idempotency hoặc inquiry.
- Giới hạn retry tự động khi kết quả chưa biết; tránh tạo một charge thứ hai chỉ vì API call đầu timeout.

**Không có giao thức đối soát đáng tin cậy thì không thể cam kết không thu tiền trùng trong mọi tình huống crash/network partition.** Cần ghi rủi ro, người xử lý và hành trình người dùng cho trạng thái chờ.

### 8.5. Webhook/callback cũng có thể gửi lặp

Provider có thể gửi callback nhiều lần hoặc gửi sai thứ tự. Endpoint callback cần:

- Xác thực chữ ký/cơ chế chứng thực được provider công bố và chống replay phù hợp.
- Có khóa event ID hoặc charge ID để **deduplicate**.
- Áp dụng state machine: chỉ cho phép những bước chuyển hợp lệ; không hạ SUCCEEDED về PROCESSING vì callback cũ.
- Ghi event/ledger cùng thay đổi trạng thái trong transaction khi có thể.
- Có đối soát định kỳ nếu callback bị mất.
- Không dùng nội dung callback do người gọi tự khai báo làm bằng chứng đã thu tiền nếu chưa xác minh.

Một cách xử lý tốt là **at-least-once delivery + idempotent consumer + durable ledger**, thay vì kỳ vọng callback chỉ đến đúng một lần.

## 9. Transactional outbox và thông điệp sau commit

Trong một order flow, sau khi tạo đơn còn phải gửi email, cập nhật tồn kho, phát sự kiện tới hệ thống vận hành. Nếu code:

~~~text
COMMIT order vào DB
PUBLISH OrderCreated lên broker
~~~

thì server có thể crash **giữa hai bước** và event bị mất. Nếu đổi thứ tự:

~~~text
PUBLISH OrderCreated lên broker
COMMIT order vào DB
~~~

thì consumer có thể nhận event của một đơn chưa commit hoặc transaction DB rollback.

### 9.1. Lưu event cùng transaction nghiệp vụ

Với **transactional outbox**:

~~~text
BEGIN DB TRANSACTION
  INSERT orders(...)
  INSERT idempotency_records(...) hoặc UPDATE outcome(...)
  INSERT outbox_events(event_id, aggregate_id, payload, state='NEW')
COMMIT

Outbox relay (bất đồng bộ):
  Đọc event chưa phát
  Publish lên broker
  Đánh dấu delivered / retry an toàn
~~~

Đơn, record chống trùng và event intent được ghi bền vững cùng nhau. Nhưng vẫn có cửa sổ:

~~~text
Broker đã nhận event
Relay crash trước khi đánh dấu delivered
Relay restart và phát lại cùng event
~~~

Do đó outbox thường bảo đảm **không mất intent đã commit** và cho phép **phát ít nhất một lần**, chứ **không đảm bảo consumer chỉ thấy event một lần**. Consumer cần deduplicate theo eventId và áp dụng invariant nghiệp vụ trong transaction của mình.

### 9.2. Không trộn ba khóa khác nhau

| Định danh | Phạm vi | Giải quyết vấn đề |
|---|---|---|
| **Client Idempotency-Key** | Lệnh HTTP từ client tới Orders API | Client retry mà không tạo lại lệnh |
| **Outbox eventId** | Sự kiện đã commit và chuyển qua broker | Consumer nhận trùng một event |
| **Provider idempotency key / merchant reference** | Lệnh thanh toán tại provider | Không charge lại cùng payment intent |

Có thể có quan hệ giữa các định danh nhưng chúng **không luôn là cùng một chuỗi và không thể thay thế tùy ý**. Ví dụ một order có nhiều lần giao hàng, nhiều sự kiện OrderUpdated nhưng chỉ một idempotency key tạo đơn ban đầu.

## 10. Một endpoint tra cứu operation để giải quyết timeout

Khi lệnh có thể mất nhiều giây/phút hoặc phụ thuộc đối tác, **202 Accepted + operation resource** thường rõ ràng hơn buộc client chờ một POST rất lâu.

### 10.1. Phản hồi khi tiếp nhận

~~~http
POST /api/payments HTTP/1.1
Authorization: Bearer <test-token>
Content-Type: application/json
Idempotency-Key: pay-order-741-attempt-1

{"orderId":"ord-741","amount":350000,"currency":"VND"}

HTTP/1.1 202 Accepted
Location: /api/operations/op-741
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{
  "operationId": "op-741",
  "state": "PROCESSING",
  "statusUrl": "/api/operations/op-741"
}
~~~

**202 nghĩa là request đã được tiếp nhận để xử lý**, không xác nhận việc thu tiền đã hoàn tất. Retry-After trong ví dụ là gợi ý nhịp polling của **hợp đồng ứng dụng**; client không được mặc định mọi HTTP library tự hiểu nó như cam kết hoàn thành sau 3 giây.

Nếu POST trả 202 bị mất và client retry **cùng key/cùng payload**, server nên trả **cùng operation ID** (hoặc kết quả cuối đã xác minh), không tạo payment intent thứ hai.

### 10.2. Tra cứu trạng thái bằng GET

~~~http
GET /api/operations/op-741 HTTP/1.1
Authorization: Bearer <test-token>

HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "op-741",
  "state": "RECONCILING",
  "message": "Đang kiểm tra kết quả với đối tác",
  "result": null
}
~~~

Sau đối soát:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "op-741",
  "state": "SUCCEEDED",
  "result": {
    "paymentId": "pay-512",
    "orderId": "ord-741"
  }
}
~~~

Một API cũng có thể dùng **303 See Other** ở operation endpoint sau khi hoàn tất để client GET tài nguyên kết quả; đó là quyết định riêng cần tài liệu hóa. Trong ví dụ này, GET trả 200 với state trong body và link/ID để client tự truy cập resource cuối.

### 10.3. Quy tắc bảo mật operation resource

Operation ID **không phải bằng chứng quyền truy cập**. GET /operations/{id} phải xác thực và kiểm tra tenant/owner/scope, không để client đoán ID để thấy trạng thái thanh toán người khác. Không dùng Location chứa token hoặc thông tin nhạy cảm.

Khi key đã hết TTL nhưng operation vẫn cần đối soát, operation ID hoặc business reference cần được giữ theo **chính sách vòng đời riêng**. Không xóa hồ sơ kiểm toán/ledger chỉ vì bản cache HTTP của idempotency đã hết hạn.

### 10.4. Hạn chế polling và kết quả lâu không xác định

Client nên:

- Tôn trọng Retry-After hoặc nhịp polling được API khuyến nghị.
- Có deadline và retry budget; sau deadline hiển thị “đang xác minh” thay vì “thanh toán thất bại chắc chắn”.
- Cho phép người dùng quay lại xem trạng thái bằng GET.
- Có kênh thông báo/callback được xác thực nếu phù hợp.
- Tránh để mỗi người dùng bấm nút lần nữa tạo **một payment intent mới** khi intent cũ đang RECONCILING.

Một operation có thể ở trạng thái không xác định lâu hơn SLA mong muốn vì provider gặp sự cố. Hệ thống cần **runbook, alert, queue kiểm tra và quy trình hỗ trợ**; không dùng trạng thái PROCESSING vô hạn mà không có owner.

## 11. Chính sách retry phía client: cùng key, có giới hạn và có tra cứu

### 11.1. Retry chỉ khi có cơ sở an toàn

Client cần phân loại kết quả trước khi quyết định:

| Quan sát của client | Hướng xử lý |
|---|---|
| 201/200 xác nhận kết quả cuối của cùng operation | Kết thúc retry, lưu resource ID |
| 202 với operation ID | Poll trạng thái theo nhịp hợp đồng; không tạo ý định mới |
| 400/422 do request không hợp lệ và chưa thực thi | Người dùng sửa dữ liệu; nếu ý định thay đổi, dùng key mới sau khi xác nhận |
| 401/403 | Xử lý authentication/authorization, không retry dồn dập |
| 409 vì cùng key nhưng fingerprint khác | Dừng; kiểm tra bug client hoặc trùng key, không tự tạo key để vượt qua |
| 409 vì operation đang được xử lý (nếu API dùng quy ước này) | Giữ key; tra cứu trạng thái hoặc chờ theo contract |
| 429/503 | Tôn trọng Retry-After nếu có; kiểm soát số lần và deadline |
| 500/502/504 hoặc network timeout | Outcome có thể chưa biết; tra cứu rồi retry cùng key nếu contract bảo vệ |
| Connection reset sau khi gửi body | Không biết server đã nhận/commit; giữ key và đi vào nhánh unknown |

Một request 400/422 được cho là “chưa thực thi” **chỉ khi API cam kết kiểm tra trước khi tạo side effect**. Lỗi 4xx trả từ một đối tác hoặc một gateway khác không tự có bảo đảm này.

### 11.2. Exponential backoff với jitter

Nếu API cho phép retry, dùng **bounded exponential backoff** thay vì vòng lặp tức thì:

\[
d_n = \min(d_{\max},\, d_{\text{base}}\cdot 2^n)
\]

Sau đó chọn một khoảng chờ ngẫu nhiên trong giới hạn phù hợp (**jitter**) để tránh nhiều client đồng loạt gửi lại một lúc. Các giá trị base/max và số lần retry phải được xác định theo SLO, tải, loại thao tác, Retry-After và thời hạn key.

Ví dụ minh họa, không phải cấu hình chung:

~~~text
attempt 1: POST K -> timeout
wait: 200-400 ms jitter
attempt 2: POST K -> 202, operation op-741
GET op-741 -> PROCESSING
wait: theo retry advice của API
GET op-741 -> SUCCEEDED, order ord-741
STOP: không gửi POST lần 3 với key mới
~~~

### 11.3. Tách timeout từng lần gọi khỏi deadline nghiệp vụ

- **Connection timeout:** giới hạn thời gian kết nối.
- **Per-request response timeout:** giới hạn thời gian đợi một HTTP response.
- **Overall deadline/retry budget:** thời gian client sẵn sàng tự động thử/tra cứu trước khi bàn giao cho UI hoặc xử lý sau.
- **Business deadline:** thời điểm đặt hàng, giữ chỗ hoặc thanh toán phải hoàn tất theo quy tắc nghiệp vụ.

Không cấu hình timeout HTTP ngắn hơn thời gian xử lý dự kiến rồi retry hàng trăm lần. Với thao tác dài, dùng mô hình 202/operation resource hoặc callback/push hợp lệ. **Deadline của client hết không đồng nghĩa server phải hoặc đã hủy công việc.**

### 11.4. Pseudocode quyết định retry

~~~text
onUserConfirm(command):
    operationKey = generateSecureRandomKey()
    persistPendingIntent(operationKey, command)
    submitSameIntent(operationKey, command)

submitSameIntent(key, originalCommand):
    while withinRetryBudget:
        try:
            response = POST /api/orders
                       with Idempotency-Key = key
                       and EXACT SAME logical command
        catch timeout_or_connection_reset:
            outcome = queryOperationIfKnown(key)
            if outcome is terminal:
                finishWith(outcome)
                return
            backoffWithJitter()
            continue

        if response is definitive success:
            finishWith(response)
            return
        if response provides operation status URL:
            pollWithBoundedBudget(status URL)
            return
        if response is key-payload conflict:
            stopAndReportClientBug()
            return
        if response is retryable under contract:
            backoffWithJitter()
            continue
        stopOrAskUserToCorrect()
        return

    showPendingVerification()
    retainKeyAndCommandForLaterReconciliation()
~~~

**Điểm nhấn:** khi hết retry budget, client không hiển thị “đặt đơn thất bại chắc chắn” nếu outcome còn unknown, và cũng không âm thầm phát sinh key mới. Thông điệp như “Đã gửi yêu cầu, đang kiểm tra kết quả” phản ánh trạng thái thật hơn.

### 11.5. Client bị restart hoặc mở nhiều tab

Key chỉ lưu trong biến RAM có thể mất khi app crash. Với hành trình có giá trị lớn, client có thể lưu pending intent trong kho lưu trữ phù hợp bảo mật và đồng bộ trạng thái qua nhiều tab/device. Không lưu token truy cập hoặc dữ liệu thanh toán nhạy cảm vào local storage chỉ để hỗ trợ retry.

Khi app khởi động lại:

1. Tải danh sách pending intents thuộc người dùng hiện tại.
2. Xác thực lại nếu cần.
3. Tra cứu operation/resource bằng định danh đã lưu.
4. Chỉ retry cùng key nếu vẫn trong thời hạn hợp đồng và không phát hiện outcome cuối.
5. Nếu key hết hạn và không thể xác minh outcome, chuyển sang hỗ trợ/reconciliation trước khi cho phép hành động có thể tạo trùng.

## 12. Ví dụ Java/Spring: tạo đơn và lưu outcome trong cùng transaction

Phần này minh họa **trường hợp đơn giản có một relational database**. Mục tiêu là ngăn tạo hai order khi client retry POST vì mất response. Nó **không tự giải quyết cổng thanh toán ngoài DB**; trường hợp đó dùng workflow ở phần 8–10.

### 12.1. Quy trình cần bảo đảm

~~~text
POST cùng tenant + cùng operation + key K
       |
       v
Authentication / authorization / validation
       |
       v
Transaction DB:
    atomic insert idempotency record with unique key
       |
       +-- key mới --> insert order, outbox, save 201 outcome --> COMMIT
       |
       +-- key cũ --> compare fingerprint
                        |
                        +-- khác --> 409
                        +-- giống --> đọc saved outcome, không INSERT order
       |
       v
Trả response (có thể bị mất)
~~~

Điều kiện quan trọng: **order row, outbox intent và idempotency outcome phải cùng nằm trong transaction DB**. Sử dụng @Transactional sẽ không tạo ra tính nguyên tử nếu các repository thực sự ghi vào nhiều datasource/transaction manager độc lập.

### 12.2. Schema tối thiểu cho orders

Ngoài bảng idempotency_records ở phần 7, một ví dụ minh họa:

~~~sql
CREATE TABLE orders (
    id              uuid PRIMARY KEY,
    tenant_id       text NOT NULL,
    customer_id     text NOT NULL,
    status          text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX orders_by_tenant
    ON orders (tenant_id, created_at DESC);
~~~

Đây không phải toàn bộ schema đặt hàng: hệ thống thật cần order_items, giá snapshot, transaction, các ràng buộc nghiệp vụ và outbox. Với một nghiệp vụ nhạy cảm, có thể thêm **unique business request ID** ở orders để bảo vệ cả khi record idempotency bị xóa theo TTL.

### 12.3. DTO và các kiểu kết quả

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import java.util.UUID;

record OrderItemInput(
        @NotBlank String sku,
        @Min(1) int quantity) {}

record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderItemInput> items) {}

record StoredOrderResult(
        int httpStatus,
        String orderId,
        String responseJson) {}

interface OrderWriter {
    // Cùng DB và transaction của idempotency ledger.
    UUID insertOrderAndOutbox(
            String authorizedTenantId,
            CreateOrderRequest command);
}

interface RequestFingerprinter {
    // Triển khai canonicalization ổn định theo hợp đồng, không dùng raw toString().
    String fingerprint(CreateOrderRequest command);
}
~~~

OrderWriter và RequestFingerprinter là các điểm tích hợp của ứng dụng; phải hiện thực và kiểm thử chúng. Fingerprint không được phụ thuộc thứ tự duyệt HashMap, dấu cách của JSON hoặc những trường transport không mang ý nghĩa của thao tác.

### 12.4. Service xử lý idempotency bằng JDBC và @Transactional

~~~java
import java.util.Objects;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class IdempotentOrderService {
    private static final String OP = "POST /api/orders";

    private final JdbcTemplate jdbc;
    private final OrderWriter writer;
    private final RequestFingerprinter fingerprinter;

    IdempotentOrderService(
            JdbcTemplate jdbc,
            OrderWriter writer,
            RequestFingerprinter fingerprinter) {
        this.jdbc = jdbc;
        this.writer = writer;
        this.fingerprinter = fingerprinter;
    }

    @Transactional
    public StoredOrderResult create(
            String tenantId,
            String idempotencyKey,
            CreateOrderRequest command) {

        String hash = fingerprinter.fingerprint(command);

        // PostgreSQL: UNIQUE/PK quyết định ai được claim key.
        // INSERT xung đột sẽ chờ transaction tranh chấp kết thúc
        // theo cơ chế của database.
        int inserted = jdbc.update("""
            INSERT INTO idempotency_records
                (tenant_id, operation_type, idempotency_key,
                 request_hash, state)
            VALUES (?, ?, ?, ?, 'PROCESSING')
            ON CONFLICT (tenant_id, operation_type, idempotency_key)
            DO NOTHING
            """, tenantId, OP, idempotencyKey, hash);

        if (inserted == 0) {
            var saved = jdbc.queryForObject("""
                SELECT request_hash, state, http_status,
                       resource_id, response_body::text AS body
                FROM idempotency_records
                WHERE tenant_id = ?
                  AND operation_type = ?
                  AND idempotency_key = ?
                """,
                (rs, rowNum) -> new SavedRow(
                        rs.getString("request_hash"),
                        rs.getString("state"),
                        rs.getObject("http_status", Integer.class),
                        rs.getString("resource_id"),
                        rs.getString("body")),
                tenantId, OP, idempotencyKey);

            if (!Objects.equals(hash, saved.requestHash())) {
                throw new IdempotencyConflictException();
            }
            if (!"SUCCEEDED".equals(saved.state())) {
                // Với flow một transaction này, PROCESSING
                // không được commit riêng. Nếu có bản ghi trạng thái
                // khác do migration/workflow, đừng thực thi lại mù quáng.
                throw new OperationNeedsReviewException();
            }
            return new StoredOrderResult(
                    saved.httpStatus(),
                    saved.resourceId(),
                    saved.responseBody());
        }

        // Cùng transaction DB với insert claim và update outcome.
        UUID orderId = writer.insertOrderAndOutbox(tenantId, command);

        // Chỉ minh họa: UUID do server tạo và trạng thái cố định,
        // nên JSON được dựng từ những ký tự đã biết an toàn.
        String body = "{\"id\":\"" + orderId
                + "\",\"status\":\"PENDING_PAYMENT\"}";

        jdbc.update("""
            UPDATE idempotency_records
            SET state = 'SUCCEEDED',
                http_status = 201,
                resource_id = ?,
                response_body = CAST(? AS jsonb),
                completed_at = now()
            WHERE tenant_id = ?
              AND operation_type = ?
              AND idempotency_key = ?
            """, orderId.toString(), body,
                tenantId, OP, idempotencyKey);

        return new StoredOrderResult(
                201, orderId.toString(), body);
    }

    private record SavedRow(
            String requestHash,
            String state,
            Integer httpStatus,
            String resourceId,
            String responseBody) {}
}

class IdempotencyConflictException extends RuntimeException {}
class OperationNeedsReviewException extends RuntimeException {}
~~~

**Giới hạn và giả định của ví dụ:**

- Đây là **mã minh họa kiến trúc**, chưa chứa toàn bộ xử lý lỗi SQL, chống lạm dụng key, authorization, canonicalization, cleanup và monitoring.
- Cả JdbcTemplate và OrderWriter phải dùng **cùng database và transaction manager**. Method @Transactional được gọi qua Spring proxy, không gọi self-invocation bỏ qua AOP.
- Ví dụ kỳ vọng isolation **READ COMMITTED** trên PostgreSQL. Với một duplicate request chạm unique constraint khi transaction đầu còn mở, câu INSERT có thể phải chờ commit/rollback. Khi giao dịch đầu commit xong, SELECT sau đó có thể đọc outcome đã commit. Với isolation khác, serialization error, lock timeout hoặc DB failover, phải có retry transaction **cùng key** theo thiết kế.
- Bản ghi PROCESSING được INSERT trong transaction nhưng **chưa commit riêng**, nên không phải hàng “đang chạy” để một client khác đọc ngay. Cách này phù hợp với thao tác DB ngắn; công việc dài/ngoài DB nên dùng durable operation/lease ở phần 6–10.
- Khi code crash **trước COMMIT**, order/outbox/outcome cùng rollback. Khi crash **sau COMMIT nhưng trước HTTP response**, request sau đọc lại outcome 201.
- Nếu một client gửi lại cùng key nhưng thay fingerprint, trả 409. Không tự ghi đè fingerprint hoặc outcome.
- Với response JSON phức tạp, phải dùng serializer có cấu hình ổn định và lưu snapshot an toàn trong transaction, không nối chuỗi JSON từ input tùy ý.
- Nếu chưa chắc business outcome sau lỗi của hệ thống phụ thuộc, **không** tạo một HTTP 500 cố định như outcome cuối mà bỏ qua reconciliation.

Lưu ý thêm: kiểu jsonb có thể chuẩn hóa lại thứ tự key/định dạng JSON. Nếu hợp đồng đòi **replay chính xác từng byte** của HTTP response, không nên coi response_body::text từ jsonb là bản sao byte-identical; cần lưu một snapshot dạng text/bytes hoặc tái dựng response theo một quy tắc ổn định đã công bố.

### 12.5. Controller trả response đã commit

~~~java
import java.net.URI;
import jakarta.validation.Valid;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrdersController {
    private final IdempotentOrderService service;

    OrdersController(IdempotentOrderService service) {
        this.service = service;
    }

    @PostMapping("/api/orders")
    ResponseEntity<String> create(
            @Valid @RequestBody CreateOrderRequest request,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) {

        // Chỉ lấy tenant từ JWT đã được xác thực và cho phép.
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        if (key.isBlank() || key.length() > 128) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid Idempotency-Key");
        }

        StoredOrderResult result = service.create(
                tenantId, key, request);

        return ResponseEntity.status(result.httpStatus())
                .location(URI.create("/api/orders/" + result.orderId()))
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                .body(result.responseJson());
    }
}
~~~

Một retry trả về **201 của cùng orderId** và không insert order mới. Lớp security phải xác minh JWT signature, issuer, audience và scope trước khi đến controller. Đối với API production, thêm kiểm tra quyền tạo order thuộc tenant được phép, giới hạn nội dung key và chống brute force/DoS.

### 12.6. Trả lỗi khi cùng key nhưng khác payload

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class IdempotencyErrorAdvice {

    @ExceptionHandler(IdempotencyConflictException.class)
    ProblemDetail keyConflict() {
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.CONFLICT);
        problem.setType(URI.create(
                "https://api.example.test/problems/idempotency-conflict"));
        problem.setTitle("Idempotency key conflict");
        problem.setDetail(
                "Khóa này đã được dùng cho một yêu cầu khác");
        problem.setProperty("code", "IDEMPOTENCY_KEY_REUSED");
        return problem;
    }
}
~~~

Đây là xử lý **409 Conflict** theo hợp đồng ví dụ. OperationNeedsReviewException cần handler riêng trả trạng thái tạm và đường tra cứu phù hợp hoặc thông báo có kiểm soát để hỗ trợ xử lý. **Đừng ép mọi record PROCESSING/RECONCILE thành lỗi “key bị dùng cho payload khác”.**

## 13. Bảng phân tích từng điểm crash và cách phục hồi

Một hệ thống nên được đánh giá bằng **những vị trí có thể crash**, không chỉ một “happy path”:

| Điểm crash / lỗi | Trạng thái có thể có | Khả năng retry an toàn |
|---|---|---|
| Trước khi API nhận request | Không có operation | Có thể gửi lại cùng key; không cần sinh key mới |
| Sau khi validate, trước DB transaction | Chưa có side effect nếu validation không ghi | Gửi lại cùng key |
| Sau atomic claim nhưng trước commit của transaction DB | Claim chưa commit, sẽ rollback nếu process chết | Retry cùng key có thể claim lại sau rollback |
| Sau commit order + idempotency outcome, trước response | Order tồn tại và outcome đã lưu | Retry cùng key đọc outcome, **không tạo đơn mới** |
| Response 201 đã tới gateway nhưng bị rớt tới client | Server đã commit; client chưa biết | Retry hoặc GET trạng thái bằng key/operation ID |
| DB commit order, chưa publish event | Outbox intent đã commit nếu thiết kế đúng | Relay phát sau restart; consumer vẫn xử lý trùng |
| Broker nhận event, relay crash trước ack | Event có thể phát lần nữa | Consumer deduplicate eventId |
| Provider thu tiền, API timeout | Local state chưa chắc chắn; provider có charge | Tra cứu provider/reference, không charge mới tùy tiện |
| Provider callback thành công nhưng local DB ghi lỗi | Provider và local state lệch nhau | Retry callback idempotent hoặc reconciliation |
| Client offline quá TTL key | Record có thể đã bị xóa | Tra business reference/ledger trước khi cho phép thao tác mới |
| Hai worker cùng lấy một pending operation | Có nguy cơ cùng gọi provider | Lease/fencing + provider idempotency + unique intent |

Đặc biệt, **không phải mọi cửa sổ lỗi đều được giải quyết bằng retry**. Một số cửa sổ cần:

- Transaction nguyên tử giữa business row và outcome.
- Durable outbox + idempotent consumer.
- Provider idempotency hoặc inquiry.
- Fencing/lease, trạng thái nghiệp vụ một chiều và reconciliation.
- Chỉ dẫn rõ cho client khi “chưa thể xác nhận”.

### 13.1. “Exactly once” cần định nghĩa phạm vi

Nhiều hệ thống tuyên bố “exactly-once processing” nhưng thực tế phải hỏi: **exactly once của cái gì?**

- Một row order được tạo một lần nhờ unique constraint và transaction?
- Một HTTP request đến server một lần? **Không bảo đảm**.
- Một message được broker giao một lần? Có thể nhận lại theo delivery model.
- Một charge được provider ghi đúng một lần? Phụ thuộc idempotency và ledger của provider.
- Một email được gửi đúng một lần đến người dùng? Có thể khó xác nhận tuyệt đối sau timeout từ email provider.

Kiến trúc thường hướng tới **một business effect có thể kiểm chứng đối với cùng một intent**, dù các request, message hoặc callback có thể lặp. Cần nói rõ điều kiện bảo đảm, thời gian lưu key, hệ thống nguồn sự thật và rủi ro còn lại.

## 14. Hợp đồng OpenAPI cho lệnh có thể bị timeout

Một API đáng tin phải tài liệu hóa **Idempotency-Key**, response khi thành công/đang xử lý, xung đột key và cách truy vấn operation.

~~~yaml
openapi: 3.1.0
info:
  title: OmniOrder API
  version: 1.0.0
paths:
  /api/orders:
    post:
      summary: Create one order idempotently
      description: >
        Retry the same logical command with the same Idempotency-Key.
        Keys are scoped by authenticated tenant and this operation.
        Duplicate keys with changed payload are rejected.
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
            minLength: 1
            maxLength: 128
          description: >
            Client-generated opaque key for a single creation intent.
            Retention window and replay behavior are documented by API policy.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: >
            Order created, or stored creation outcome replayed
            for the same key and logical payload.
          headers:
            Location:
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderCreated'
        '400':
          description: Malformed Idempotency-Key or request
        '401':
          description: Missing or invalid authentication
        '403':
          description: Insufficient permission
        '409':
          description: Reuse of a key with a different payload
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '422':
          description: Validation failure before execution
        '503':
          description: Temporarily unavailable, outcome may require lookup
  /api/operations/{id}:
    get:
      summary: Check a long-running operation
      description: >
        Example alternative for asynchronous commands.
        The caller must own or be authorized for the operation.
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Operation status including terminal outcome if known
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OperationStatus'
        '401':
          description: Authentication required
        '403':
          description: Not authorized to view operation
        '404':
          description: Operation not found or deliberately hidden
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId:
          type: string
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [sku, quantity]
            properties:
              sku:
                type: string
              quantity:
                type: integer
                minimum: 1
    OrderCreated:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
    OperationStatus:
      type: object
      required: [id, state]
      properties:
        id:
          type: string
        state:
          type: string
          enum: [ACCEPTED, PROCESSING, RECONCILING,
                 SUCCEEDED, FAILED_FINAL]
        result:
          type: object
    ApiProblem:
      type: object
      properties:
        type:
          type: string
        title:
          type: string
        status:
          type: integer
        code:
          type: string
~~~

**Lưu ý phạm vi:** Ví dụ này chủ yếu mô tả POST tạo đơn **đồng bộ** có replay 201. API payment **bất đồng bộ** ở phần 10 có thể dùng một OpenAPI operation khác trả 202 và Location tới status URL. Không nên quảng cáo 202 cho một endpoint nếu nó không thực sự có cơ chế lưu/truy vấn operation.

OpenAPI không tự bảo đảm idempotency. Nó mới diễn đạt hợp đồng; ứng dụng vẫn phải có unique constraint, transaction, replay store, quyền, retry policy và kiểm thử failover. Ngoài ra cần xác định rõ thời hạn key, request canonicalization, trạng thái cùng key đang chạy và cách client tra cứu nếu đã quá thời hạn.

Trong các ví dụ, **RECONCILE** là tên trạng thái nội bộ của record cần đối soát, còn **RECONCILING** là nhãn thân thiện ở API trạng thái. Hợp đồng thật phải định nghĩa cách ánh xạ và dùng nhất quán, không để client dựa vào hai cách viết mâu thuẫn.

## 15. Kiểm thử chủ đích “server đã commit nhưng response mất”

Kiểm thử happy path 201 Created chưa đủ để chứng minh cơ chế idempotency. **Trường hợp quan trọng nhất là thao tác đã commit thành công nhưng client không thấy response.** Phải chủ động mô phỏng điều kiện này thay vì chỉ chờ lỗi ngẫu nhiên.

### 15.1. Kịch bản A — Mất response sau commit

**Thiết lập:** chạy API với DB test và một proxy có khả năng chặn response sau khi backend đã ghi nhận commit. Dùng dữ liệu giả, không gọi cổng thanh toán thật.

1. Client tạo key K và body P, gửi POST /api/orders.
2. DB commit order ord-741 và idempotency outcome 201.
3. Test proxy **cắt response trên đường về client**.
4. Client nhận network error hoặc read timeout; chưa biết outcome.
5. Client gửi lại **cùng key K và cùng body P**.
6. Server trả lại 201 với **ord-741**, không insert order thứ hai.
7. Kiểm tra database có đúng **một order**, một record key và outbox event không nhân đôi.

Đây là phép thử quan trọng hơn việc chỉ mô phỏng timeout trước khi request đến server. **Nếu test ném exception trước transaction commit**, nó chứng minh rollback chứ không mô phỏng đúng cửa sổ “commit rồi mất response”.

### 15.2. Kịch bản B — Hai retry đồng thời

**Thiết lập:** hai HTTP client/threads dùng cùng tenant, operation, K và P, đồng thời gọi endpoint.

Kỳ vọng:

- Unique constraint bảo đảm chỉ một request claim key thành công.
- Không có hai orders hoặc hai durable outbox intents cho cùng ý định.
- Request còn lại được trả outcome của cùng đơn hoặc kết quả “đang xử lý” theo hợp đồng.
- Nếu database lock timeout trong khi chờ giao dịch đầu, client nhận lỗi tạm và có thể retry **cùng K** sau backoff.

Không chỉ dùng test đơn luồng với hai request tuần tự; race thường chỉ xuất hiện khi các request đến đồng thời trên nhiều replica.

### 15.3. Kịch bản C — Cùng key nhưng payload khác

~~~http
POST /api/orders
Idempotency-Key: K
Content-Type: application/json

{"items":[{"sku":"BOOK-01","quantity":1}]}
~~~

Sau khi request đầu đã tạo đơn, gửi:

~~~http
POST /api/orders
Idempotency-Key: K
Content-Type: application/json

{"items":[{"sku":"BOOK-01","quantity":3}]}
~~~

Kỳ vọng **409 Conflict** theo hợp đồng, không tạo thêm order và không sửa order trước. Cần test thêm khác biệt về thứ tự JSON key, whitespace, kiểu số và trường mặc định theo quy tắc fingerprint đã chọn; nếu API coi hai body tương đương về ngữ nghĩa, kết quả hash phải phản ánh điều đó.

### 15.4. Kịch bản D — Crash trước commit

1. Cho request đầu claim key trong transaction.
2. Gây lỗi có kiểm soát **trước COMMIT**, khiến transaction rollback.
3. Retry cùng key.
4. Kỳ vọng một lần thực thi hợp lệ có thể hoàn tất sau rollback.
5. Không có một order “mồ côi” đã commit hoặc outcome SUCCEEDED giả.

Phải tách test này khỏi kịch bản A: **trước commit** và **sau commit** có ý nghĩa hoàn toàn khác nhau.

### 15.5. Kịch bản E — Payment provider đã xử lý nhưng timeout

Fake payment provider cho phép:

- Ghi charge với provider key cố định.
- Trả timeout sau khi charge đã được lưu.
- Trả kết quả khi hệ thống inquiry theo merchant reference.
- Gửi callback thành công lặp hai lần.

Kỳ vọng:

1. Hệ thống ghi intent trạng thái RECONCILE thay vì tự tạo charge mới với key khác.
2. Worker tra cứu provider theo reference.
3. Chuyển intent sang SUCCEEDED đúng một lần về nghiệp vụ.
4. Callback lặp không làm tăng amount hoặc tạo payment record thứ hai.
5. API status và UI phản ánh sự thật, không báo thất bại ngay khi timeout.

### 15.6. Kịch bản F — Key hết hạn

Giả sử hợp đồng lưu idempotency record 24 giờ. Sau 25 giờ, client offline mở lại và gửi lại POST với cùng key. Nếu record đã bị xóa, unique key ở lớp idempotency **không còn ngăn tạo đơn**.

Kiểm thử cần xác nhận một trong những chính sách đã công bố:

- Có **business request ID** được lưu lâu hơn và unique, nên server tìm thấy đơn cũ.
- Client phải gọi API đối soát theo operation ID/merchant reference trước khi cho gửi lại.
- API từ chối tự retry thao tác nhạy cảm sau TTL và yêu cầu xác minh thủ công.

**Không tuyên bố “tránh tạo trùng tuyệt đối” chỉ vì đã kiểm thử retry trong vài giây đầu.**

### 15.7. Ma trận kiểm thử tổng hợp

| STT | Kịch bản | Kết quả chính cần xác minh |
|---:|---|---|
| 1 | POST lần đầu hợp lệ | 201 + Location; một order được commit |
| 2 | Retry cùng key + cùng fingerprint | Cùng order/outcome, không insert mới |
| 3 | Retry cùng key + fingerprint khác | 409, không sửa outcome cũ |
| 4 | Hai request đồng thời trên hai replica | Unique claim; không tạo hai side effects |
| 5 | Crash trước transaction commit | Rollback toàn bộ, retry có thể thực thi |
| 6 | Mất 201 response sau commit | Retry vẫn đọc đúng outcome |
| 7 | DB lock timeout khi key đang bị claim | Không sinh side effect song song; client có đường retry |
| 8 | DB failover hoặc replica lag | Không replay dữ liệu sai hoặc tạo trùng |
| 9 | Thiếu token | 401; không phát lộ record/key |
| 10 | Token thiếu quyền | 403/404 theo hợp đồng, không bypass bằng key |
| 11 | Cùng key ở tenant khác | Không trộn kết quả giữa tenant |
| 12 | Provider timeout sau khi charge | Reconcile; không charge lại tùy tiện |
| 13 | Provider trả kết quả trùng / callback lặp | Một state transition hợp lệ, ledger không nhân đôi |
| 14 | Relay phát outbox event hai lần | Consumer xử lý idempotent |
| 15 | Retry-After / 429 / 503 | Client có backoff, deadline và giữ key |
| 16 | Key hết TTL | Không hứa bảo đảm ngoài thời hạn; có quy trình fallback |
| 17 | Client đóng app sau POST | Pending intent được khôi phục/tra cứu |
| 18 | Operation ID người khác | Không cho truy cập trạng thái hoặc dữ liệu |
| 19 | 202 trong khi chờ provider | Không bị trình bày thành đã thanh toán |
| 20 | Reconciliation thất bại dài | Alert, owner, runbook và không retry vô hạn |

### 15.8. Gợi ý integration test với Spring/JUnit

Một bài integration test sử dụng **PostgreSQL thực trong môi trường test** có thể gọi IdempotentOrderService hai lần và kiểm tra một order. Pseudocode JUnit (các fixture/helper là thành phần ứng dụng cần xây):

~~~java
@Test
void retryAfterCommitReturnsSameOrder() {
    String key = "order-attempt-123";
    var request = validOrderRequest();

    StoredOrderResult first =
            service.create("tenant-a", key, request);
    StoredOrderResult retried =
            service.create("tenant-a", key, request);

    assertEquals(201, first.httpStatus());
    assertEquals(first.orderId(), retried.orderId());
    assertEquals(1, orderRepository.countByTenantAndIntent(
            "tenant-a", key));
}
~~~

Test trên minh họa ý định; nếu schema orders không lưu key, phải đổi phép đếm thành truy vấn qua idempotency ledger hoặc business reference. Nó **không thay thế test mất response sau commit qua HTTP proxy** vì gọi service hai lần tuần tự không có network failure.

Để test concurrency, dùng hai kết nối/transaction thật và một đồng bộ khởi phát như CountDownLatch, barrier hoặc test proxy. Không đặt toàn bộ bài test trong **một transaction bao quanh cả hai request** vì có thể che mất hành vi commit/locking thật. Test cần xác minh trạng thái DB và sự kiện, không chỉ status HTTP.

## 16. Quan sát vận hành và đối soát

### 16.1. Dashboard cần phân biệt các loại outcome

| Metric/log | Mục đích |
|---|---|
| idempotency.new / replay / conflict | Biết số lần nhận ý định mới, retry đúng, reuse key sai |
| operation.PROCESSING age | Phát hiện thao tác chạy lâu hoặc kẹt |
| operation.RECONCILE count / oldest age | Nhìn thấy số outcome chưa xác định |
| db.unique_conflict / lock_wait | Phát hiện retry đồng thời, contention và bottleneck |
| payment.provider_timeout và inquiry_result | Đo độ tin cậy tích hợp ngoài |
| outbox.backlog / duplicate_event | Theo dõi event sau commit và consumer deduplication |
| duplicate_business_effect_count | Chỉ số an toàn quan trọng, nên hướng tới 0 |
| 201 / 202 / 409 / 429 / 503 / 504 | Phân biệt loại phản hồi và nguyên nhân retry |
| client.unknown_outcome_count | Số phiên giao dịch client không nhận kết quả cuối |
| reconciliation_time_p95/p99 | Đo thời gian đi từ unknown tới kết luận cuối |

**Không đưa raw Idempotency-Key, orderId, paymentId hoặc userId có cardinality cao vào nhãn metric**. Dùng counter theo route, tenant tier, outcome class và mã lỗi được phép. Log chi tiết cần phân quyền, retention và masking; một key ngẫu nhiên không phải mật khẩu nhưng vẫn có thể giúp liên kết giao dịch cá nhân.

### 16.2. Trace một operation xuyên các hệ thống

Gắn correlation ID cho hành trình:

~~~text
clientRequestId -> API request -> businessOperationId
                                   |-> orderId
                                   |-> outbox eventId
                                   |-> paymentIntentId
                                   |-> provider reference
                                   |-> reconciliation run
~~~

Mỗi ID có **phạm vi và trách nhiệm riêng**. Một trace ID có thể thay đổi giữa những lần retry, còn businessOperationId và provider reference phải bền vững cho cùng intent. Không dùng một request trace ID mới để kết luận đó là business intent mới.

### 16.3. Runbook khi số operation RECONCILE tăng

1. Xác nhận sự cố tại gateway, DB, broker hay provider; không chỉ nhìn 504.
2. Kiểm tra tần suất timeout, lock wait và trạng thái ledger.
3. Tạm giảm hoặc ngắt retry tự động tới provider nếu có nguy cơ charge trùng.
4. Phân loại operation theo reference, thời gian, số tiền, trạng thái.
5. Dùng inquiry/API của provider, webhook ledger và đối soát để xác minh outcome.
6. Chuyển trạng thái bằng transaction với kiểm tra phiên bản/invariant; ghi audit ai đã quyết định.
7. Thông báo cho người dùng theo kết quả thật và xử lý trường hợp bất định còn lại.
8. Rút kinh nghiệm từ thời gian phát hiện, số giao dịch không xác định, thời gian đối soát và số lần phát sinh side effect trùng.

Một hệ thống có idempotency nhưng **không có quy trình xử lý trạng thái mồ côi** vẫn có thể để người dùng chờ vô hạn hoặc cho phép thao tác mới quá sớm.

## 17. Những anti-pattern phổ biến

| Anti-pattern | Vì sao nguy hiểm? | Cách thay thế |
|---|---|---|
| **“Timeout = thất bại”** | Server có thể đã commit hoặc provider đã charge | Unknown outcome, operation lookup và reconciliation |
| **Retry POST với key mới** | Tạo ý định thứ hai, có thể sinh order/charge trùng | Giữ nguyên key và logical payload cho cùng intent |
| **Chỉ kiểm tra existsByKey rồi mới insert** | Check-then-act race giữa replica | Atomic claim + unique constraint/conditional write |
| **Lưu key sau khi commit order** | Crash ở giữa để lại order không có record chống trùng | Cùng transaction cho order + key outcome |
| **Lưu key trong memory của app** | Restart/scale-out làm mất hoặc không chia sẻ record | Durable store chung và quản lý retention |
| **Key giống nhau, payload khác vẫn được chạy** | Một key đại diện cho hai ý định | Fingerprint và 409 |
| **Không giới hạn tuổi key** | Store phình to, chi phí cao, khó cleanup | TTL công bố + business ledger theo nhu cầu |
| **Xóa key sớm nhưng hứa chống trùng mãi mãi** | Client offline retry sau TTL tạo bản mới | Business uniqueness/tra cứu/reconciliation |
| **Chờ lock không giới hạn** | Nhiều request treo và cạn connection | Timeout có kiểm soát + retry cùng key + status endpoint |
| **Mark PROCESSING là FAILED khi lease hết** | Worker cũ/provider vẫn có thể hoàn tất | Fencing/lease và inquiry trước khi quyết định |
| **Coi 504 là rollback của upstream** | Gateway chỉ ngừng chờ, upstream có thể đang chạy | Tách transport outcome và business outcome |
| **Retry provider charge với key khác** | Charge có thể đã thành công ở lần đầu | Stable provider reference, tra cứu trước |
| **Lưu kết quả 500 thành outcome cuối khi chưa biết side effect** | Client không biết phải reconciliation | Phân loại transient/unknown/terminal theo nguồn sự thật |
| **Dùng trace ID thay business operation ID** | Mỗi retry có trace mới nên mất dedup | Business intent ID bền vững, trace chỉ phục vụ quan sát |
| **Tin Idempotency-Key thay auth** | Người biết key có thể đọc outcome người khác | Authentication/tenant/authorization cho mọi lần đọc/replay |
| **Dùng 202 như đã thanh toán thành công** | Gây sai UI và hoàn tất đơn trước kết quả provider | State PROCESSING/RECONCILING/SUCCEEDED rõ |
| **Outbox nhưng consumer không deduplicate** | Event được giao lại có thể xử lý lặp | Event ID + idempotent consumer + state invariant |
| **Không phân biệt retryable và non-retryable** | 400/403 bị retry dồn dập, làm tăng lỗi | Phân loại status, backoff, deadline và dừng khi cần |

### 17.1. Vì sao chỉ có một unique constraint chưa đủ?

Unique key ở API có thể ngăn tạo hai **order** cùng intent trong một database, nhưng nếu đã có các side effect:

~~~text
Create order -> Charge provider -> Send email -> Reserve inventory
~~~

thì mỗi bước cần một mô hình định danh, trạng thái, retry và deduplication phù hợp. Một unique constraint của orders không khiến payment provider, email provider hoặc inventory service hiểu thế nào là “cùng một lệnh”.

### 17.2. Vì sao “bắt tất cả exception rồi retry” nguy hiểm?

Không phải exception nào cũng có nghĩa thực thi chưa bắt đầu. Sau khi lệnh gọi provider timeout, không thể tự cho là chưa charge. Sau khi DB commit mà HTTP writer bị lỗi, transaction đã thành công. Một retry wrapper tổng quát không biết **commit boundary** có thể nhân side effect. Retry phải được thiết kế **ở đúng lớp có khả năng định danh và xác minh operation**.

## 18. Case study nhỏ: một lượt checkout bị mất phản hồi

### 18.1. Tình huống

Người mua xác nhận giỏ 350.000 VND. Ứng dụng gửi POST /api/orders với K1. Gateway có timeout 2 giây; Orders API cần 2,4 giây để hoàn tất transaction dưới tải cao.

~~~text
12:00:00.000  Client gửi POST K1
12:00:00.050  API nhận request
12:00:01.900  DB commit ord-741 và outcome K1
12:00:02.000  Gateway hết timeout; client thấy lỗi mạng
12:00:02.100  Client dự định gửi lần nữa
12:00:02.150  Retry POST K1 được chuyển tới replica khác
12:00:02.170  Replica đọc record K1 = SUCCEEDED, order ord-741
12:00:02.200  Client nhận 201, Location /orders/ord-741
~~~

**Kết quả đúng:** một order tồn tại, client biết order ID từ retry và tiếp tục theo dõi thanh toán.

**Kết quả sai nếu tạo key K2:** API xem K2 là intent mới, có thể tạo ord-742, dẫn tới hai đơn giống nhau.

### 18.2. Thay đổi tình huống: payment timeout

Orders API đã tạo ord-741 và outbox payment intent. Payment worker gọi provider với key P1; provider thu tiền nhưng response bị mất.

~~~text
12:00:03  Worker gửi charge P1, amount 350000 VND
12:00:04  Provider đã ghi charge ch-512
12:00:05  Worker timeout, local payment intent = RECONCILE
12:00:08  Worker tra cứu merchant reference ord-741
12:00:09  Provider xác nhận ch-512 thành công
12:00:10  Local ledger cập nhật payment SUCCEEDED
12:00:12  Client GET /operations/op-741 thấy SUCCEEDED
~~~

**Kết quả đúng:** không phát charge P2; không báo “thất bại” chỉ vì timeout; đối soát trước khi xác nhận.

Nếu provider không hỗ trợ inquiry hoặc không đưa ra kết quả đáng tin, trạng thái tiếp tục **chưa xác định** và cần quy trình hỗ trợ. Không tự đặt quy tắc rằng “chờ 10 giây thì charge chắc chắn thất bại”.

### 18.3. Chi phí của sự đúng đắn

Một hệ thống triển khai đầy đủ cơ chế này có thêm:

- Idempotency records và business ledger cần storage/cleanup.
- Unique index, transaction/lock có thể tăng DB contention.
- Operation status endpoint và worker/reconciliation.
- Telemetry, alert, audit và runbook.
- Kiểm thử chaos/fault injection ở các điểm lỗi hiếm gặp.

Đây là đánh đổi có chủ đích. Không phải mọi POST đơn giản đều cần workflow nhiều bước, nhưng **tạo đơn, thanh toán, chuyển tiền, giữ chỗ và lệnh có side effect đắt đỏ** cần mức bảo vệ tương xứng hậu quả của thao tác trùng.

## 19. Bài tập thực hành

### Bài 1 — Phân biệt lỗi mạng và kết quả nghiệp vụ

Một client gửi POST /payments và nhận 504 sau 5 giây. Gateway log nói upstream vẫn đang xử lý, nhưng client không có response.

**Câu hỏi:** Có thể kết luận payment thất bại không? Client nên làm gì?

**Gợi ý:** Không. 504 chỉ là gateway timeout. Client cần giữ key, tra cứu operation hoặc provider result qua API có quyền; retry cùng intent nếu hợp đồng bảo vệ, không tạo key mới ngay.

### Bài 2 — Tìm lỗi check-then-act

Cho pseudocode:

~~~java
if (!repository.existsByIdempotencyKey(key)) {
    paymentProvider.charge(amount);
    repository.save(key, "SUCCEEDED");
}
~~~

**Câu hỏi:** Nêu ít nhất bốn lỗ hổng.

**Gợi ý:** Hai request đồng thời đều qua check; key không gắn tenant/operation/fingerprint; provider charge trước khi ledger lưu bền; crash giữa charge/save; không có provider idempotency/reference; không có đối soát khi timeout; không kiểm tra authorization.

### Bài 3 — Một transaction hay hai transaction?

Phương án A:

~~~text
BEGIN -> INSERT order -> INSERT idempotency outcome -> COMMIT
~~~

Phương án B:

~~~text
BEGIN -> INSERT order -> COMMIT
BEGIN -> INSERT idempotency outcome -> COMMIT
~~~

**Câu hỏi:** Phương án nào tránh duplicate khi server crash ngay sau commit order nhưng trước response?

**Đáp án:** A, nếu cùng database/transaction manager và có unique claim phù hợp. B tạo cửa sổ có order nhưng chưa có outcome key.

### Bài 4 — Cùng key nhưng dữ liệu khác

Client gửi cùng K cho POST tạo đơn quantity=1 và sau đó quantity=2. Server đã tạo đơn quantity=1 ở lần đầu nhưng client gặp timeout.

**Câu hỏi:** Server có nên tạo order quantity=2, trả lại order cũ hay báo lỗi?

**Gợi ý:** Báo **409 key/payload conflict** theo hợp đồng. Không âm thầm đổi payload hoặc tạo đơn thứ hai trong cùng intent. Nếu khách thật sự muốn đặt lại số lượng mới, cần xác minh kết quả cũ rồi thực hiện thao tác điều chỉnh/hủy hoặc tạo intent mới phù hợp.

### Bài 5 — Provider không hỗ trợ idempotency

Đối tác thanh toán không chấp nhận Idempotency-Key, nhưng có API tìm charge theo merchant reference. Sau POST /charges, worker nhận read timeout.

**Câu hỏi:** Đề xuất state và kế hoạch retry.

**Gợi ý:** Đánh dấu RECONCILE, query charge theo merchant reference và xác thực amount/currency/status; chỉ quyết định gửi lệnh mới sau khi đã có cơ sở an toàn, kèm giới hạn retry. Nếu inquiry không đáng tin trong một khoảng thời gian, đưa vào manual review thay vì charge lặp.

### Bài 6 — Key hết hạn

API công bố key có hiệu lực 24 giờ. Client offline 48 giờ sau request đầu bị timeout, bây giờ tự động gửi lại cùng POST và K.

**Câu hỏi:** Cơ chế idempotency 24 giờ có bảo đảm không tạo đơn thứ hai không?

**Đáp án:** Không. Record K có thể đã bị dọn. Client phải tra cứu theo operation/business reference, kiểm tra đơn hiện tại và chính sách khôi phục trước khi tạo lại.

### Bài 7 — Sửa trạng thái UI

Sau timeout, UI hiện thông báo: “Thanh toán thất bại. Nhấn lại để thanh toán lần nữa.” Nhưng backend đang RECONCILING.

**Câu hỏi:** Viết lại thông báo và hành vi UI.

**Gợi ý:** “Chúng tôi đã nhận yêu cầu và đang xác minh kết quả thanh toán. Vui lòng kiểm tra trạng thái đơn trước khi thử lại.” Hiển thị đường tra cứu, ngăn tạo payment intent mới không kiểm soát và có phương án hỗ trợ nếu xác minh kéo dài.

### Bài 8 — Thiết kế một kiểm thử chịu lỗi

Hãy mô tả test có chủ đích cho trường hợp **DB đã commit nhưng HTTP response mất**, bao gồm điểm chèn lỗi, request retry, kết quả DB và kết quả HTTP.

**Gợi ý:** Dùng proxy bỏ response 201 sau khi backend commit; retry cùng key/body; xác minh chỉ một order, một outbox intent và response trỏ cùng order ID. Không dùng exception ném trong transaction để giả lập lỗi sau commit.

### Bài 9 — Nâng cấp yêu cầu

Doanh nghiệp muốn giảm TTL key từ 24 giờ xuống 30 phút để giảm chi phí. Khách hàng dùng mobile có thể offline một ngày.

**Câu hỏi:** Những dữ kiện/biện pháp nào phải có trước khi duyệt thay đổi?

**Gợi ý:** Đo độ trễ retry thực, tần suất offline, tỷ lệ duplicate, business uniqueness, operation lookup, nguy cơ thu tiền trùng và chi phí lưu ledger. Có thể giảm TTL của cache replay nhưng giữ business transaction reference đủ lâu để đối soát. Không quyết định chỉ từ dung lượng bảng key.

## 20. Checklist trước khi phát hành endpoint có retry

- [ ] Đã phân biệt **timeout của transport** và **outcome nghiệp vụ** trong hợp đồng/API/UI?
- [ ] Đã liệt kê các vị trí crash trước, trong và sau commit, đặc biệt sau commit trước response?
- [ ] Client tạo key **trước lần gửi đầu** và dùng lại cùng key cho cùng logical intent?
- [ ] Key có phạm vi tenant/operation, định dạng/giới hạn, TTL và chính sách hết hạn rõ?
- [ ] Payload fingerprint ổn định; cùng key khác payload bị từ chối theo contract?
- [ ] Atomic claim dùng unique constraint/conditional write xuyên mọi replica, không chỉ check-then-act?
- [ ] Với thao tác DB cục bộ, business effect và outcome chống trùng commit cùng transaction?
- [ ] Retry cùng key sau commit không thực hiện lại side effect?
- [ ] Transaction isolation, lock wait, failover và lỗi serialization có chiến lược xử lý?
- [ ] Với workflow bất đồng bộ, có operation resource, state machine và quyền tra cứu?
- [ ] PROCESSING treo/lease hết hạn không tự động tạo một side effect mới chưa được kiểm chứng?
- [ ] Có unique business reference/ledger cho thao tác nhạy cảm ngoài TTL key?
- [ ] External provider có idempotency/reference/inquiry được xác minh theo hợp đồng riêng?
- [ ] Outbox event có event ID và consumer có deduplication khi nhận lại?
- [ ] Callback/webhook được xác thực, xử lý idempotent và không làm sai state machine?
- [ ] Client retry có backoff/jitter, Retry-After, retry budget và deadline rõ?
- [ ] 201/202/409/429/503/504 được giải thích đúng; không coi 504 là rollback?
- [ ] Lỗi validation/quyền không bị retry mù; lỗi 500 chưa rõ side effect không bị đóng thành final sai?
- [ ] Không dùng key thay authentication; API replay và GET operation kiểm tra tenant/owner/scope?
- [ ] Có giới hạn lưu PII/secret trong key, fingerprint, response snapshot và log?
- [ ] OpenAPI mô tả header, response replay, pending state và conflict rõ ràng?
- [ ] Có test mất response sau commit, concurrent retries, payload conflict, TTL và provider timeout?
- [ ] Có metrics cho replay/conflict/unknown, dashboard, alert và runbook reconciliation?
- [ ] UI nói rõ **“chưa xác định, đang xác minh”** thay vì tự kết luận thất bại?

## 21. Kết luận

Khi một REST client gặp **timeout sau khi server đã xử lý**, sự thật quan trọng nhất là: **client không nhận được phản hồi không đồng nghĩa server chưa commit**. Retry một POST với key mới có thể nhân đôi đơn hàng, thanh toán hoặc side effect khác. Trạng thái đúng trong nhiều trường hợp là **kết quả chưa xác định**, cần được tra cứu, tiếp tục cùng operation hoặc đối soát.

Để xử lý đáng tin cậy, hãy kết hợp **idempotency key có phạm vi và fingerprint rõ**, **atomic claim và transaction bền vững**, **replay outcome**, **operation status endpoint**, **retry có giới hạn**, và **reconciliation với hệ thống ngoài**. Với workflow phân tán, transactional outbox và idempotent consumer hỗ trợ giao sự kiện an toàn nhưng không thay thế bảo vệ phía provider. Quan trọng nhất, phải kiểm thử cửa sổ **“đã commit nhưng response bị mất”** và xác định giới hạn bảo đảm khi key hết hạn hoặc đối tác không hỗ trợ idempotency.

Một API được thiết kế tốt không hứa rằng mạng sẽ không bao giờ timeout. Nó bảo đảm rằng khi timeout xảy ra, các bên **không phải đoán kết quả và không tạo side effect trùng chỉ để thử lại** — trong phạm vi hợp đồng, dữ liệu nguồn sự thật và cơ chế đối soát đã được thiết kế.
