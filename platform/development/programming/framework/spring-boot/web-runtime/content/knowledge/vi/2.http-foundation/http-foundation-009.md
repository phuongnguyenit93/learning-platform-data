# Yêu cầu an toàn, tính lũy đẳng và tác động khi thử lại

## 1. Vì sao retry có thể gây lỗi nghiệp vụ?

Trong hệ thống phân tán, client và server trao đổi qua mạng nên một request có thể thất bại ở nhiều thời điểm: client không kết nối được, kết nối bị ngắt giữa chừng, server xử lý quá hạn timeout, proxy trả lỗi, hoặc server đã hoàn tất nghiệp vụ nhưng response không đến được client. Vì vậy, khi client nhìn thấy timeout hoặc lỗi mạng, client thường **không biết chắc server đã thực hiện nghiệp vụ hay chưa**.

Nếu client gửi lại request một cách máy móc, một thao tác có side effect có thể được thực hiện nhiều lần. Ví dụ, người dùng bấm thanh toán, server tạo giao dịch và gửi lệnh sang cổng thanh toán, nhưng response bị mất. Client timeout rồi gửi lại. Nếu server coi lần gửi lại là một yêu cầu mới, khách hàng có thể bị trừ tiền hai lần.

Retry là cơ chế phục hồi trước lỗi tạm thời. Tính an toàn của retry phụ thuộc vào ngữ nghĩa HTTP, thiết kế nghiệp vụ, khả năng nhận diện yêu cầu trùng và giới hạn retry. Một chính sách retry tốt phải trả lời được ba câu hỏi:

1. Lỗi này có khả năng tự hết khi thử lại không?
2. Nếu lần trước thực tế đã thành công, gửi lại có làm phát sinh thêm tác động không?
3. Có đủ thời gian và ngân sách để thử lại mà không làm hệ thống quá tải không?

Không có một cấu hình retry dùng chung an toàn cho mọi API. Cần thiết kế theo từng loại thao tác và side effect của nó.

## 2. Phân biệt safe method và idempotent method

HTTP định nghĩa một số thuộc tính ngữ nghĩa cho method. Hai thuộc tính quan trọng khi thiết kế retry là **safe** và **idempotent**.

- **Safe method**: client yêu cầu đọc hoặc lấy thông tin; thao tác được yêu cầu không làm thay đổi trạng thái nghiệp vụ của tài nguyên. Server vẫn có thể ghi access log, metrics hoặc thông tin vận hành.
- **Idempotent method**: thực hiện cùng một request một lần hay nhiều lần có cùng hiệu ứng dự kiến trên trạng thái tài nguyên. Response giữa các lần có thể khác nhau.
- **Retry**: client gửi lại request sau khi gặp một lỗi được xem là có khả năng phục hồi. Retry là quyết định của client hoặc tầng trung gian, không phải thuộc tính tự động của server.

| HTTP method | Safe? | Idempotent? | Ý nghĩa khi retry |
|---|---|---|---|
| GET | Có | Có | Có thể retry khi lỗi tạm thời nếu request thực sự chỉ đọc. |
| HEAD | Có | Có | Tương tự GET, nhưng response không có message body. |
| OPTIONS | Có | Có | Thường có thể retry khi cần khám phá capability. |
| TRACE | Có theo ngữ nghĩa HTTP | Có | Ít được bật trong ứng dụng thực tế; cần tuân thủ chính sách bảo mật. |
| PUT | Không | Có | Gửi cùng representation để đặt trạng thái tài nguyên về cùng một giá trị mong muốn. |
| DELETE | Không | Có | Yêu cầu tài nguyên ở trạng thái đã bị xóa; các response sau có thể khác response đầu. |
| POST | Không | Không được bảo đảm | Có thể tạo tài nguyên hoặc thực hiện side effect mới mỗi lần; chỉ retry an toàn khi hợp đồng nghiệp vụ hỗ trợ deduplication/idempotency. |
| PATCH | Không | Không được bảo đảm | Tùy cách định nghĩa patch document và logic cập nhật; phải đánh giá từng API. |

**Safe không đồng nghĩa với idempotent.** Một method safe cũng là idempotent, nhưng một method idempotent như PUT hoặc DELETE vẫn có thể thay đổi trạng thái tài nguyên.

**Idempotent không có nghĩa response phải giống hệt nhau.** Ví dụ, DELETE lần đầu có thể trả 204 No Content; lần thứ hai có thể trả 404 Not Found. Nếu mục tiêu nghiệp vụ là tài nguyên không còn tồn tại, trạng thái cuối cùng vẫn giống nhau. API cũng có thể chọn trả 204 cho cả trường hợp tài nguyên đã bị xóa để đơn giản hóa hợp đồng, miễn là hành vi được tài liệu hóa nhất quán.

### 2.1. Ví dụ về PUT và POST

Giả sử API có endpoint cập nhật địa chỉ giao hàng:

~~~http
PUT /customers/42/address
Content-Type: application/json

{
  "city": "Da Nang",
  "street": "Le Duan"
}
~~~

PUT đặt representation của địa chỉ khách hàng 42 thành giá trị được gửi. Gửi lại cùng request không tạo thêm một địa chỉ mới; trạng thái mong muốn vẫn là địa chỉ đó. Đây là dạng thao tác phù hợp với retry nếu các điều kiện nghiệp vụ khác cũng được đáp ứng.

Ngược lại:

~~~http
POST /payments
Content-Type: application/json

{
  "orderId": "ORD-2026-0042",
  "amount": 1500000
}
~~~

POST có thể tạo một payment mới mỗi lần nhận request. Nếu gửi lại, server có thể tạo hai payment cho cùng một đơn hàng. Muốn retry POST an toàn, API phải bổ sung cơ chế nhận diện yêu cầu trùng, thường thông qua header Idempotency-Key và lưu kết quả xử lý.

### 2.2. PATCH cần được đánh giá theo nội dung

Một PATCH dạng “đặt trạng thái thành APPROVED” có thể cho cùng trạng thái sau nhiều lần thực hiện. Một PATCH dạng “tăng số lượng lên 1” sẽ tăng thêm mỗi lần nhận request. Do đó không được suy luận PATCH luôn idempotent hoặc luôn không idempotent. Hãy xem patch document, precondition, version check và side effect thực tế.

## 3. Timeout không chứng minh nghiệp vụ chưa thực hiện

Giả sử client gửi request và đặt timeout 2 giây. Server có thể đã trải qua các bước sau:

1. Nhận và xác thực request.
2. Ghi dữ liệu nghiệp vụ trong database.
3. Gửi yêu cầu đến một hệ thống bên ngoài.
4. Tạo response.
5. Response bị chậm hoặc mất trên mạng.

Client chỉ nhìn thấy timeout ở bước 5. Nếu client gửi lại ngay, server có thể thực hiện lại bước 2 hoặc 3. Đây là tình huống **kết quả không xác định đối với client** (ambiguous outcome).

Cần phân biệt các trường hợp:

- Kết nối thất bại trước khi request được gửi: có thể chưa có xử lý ở server, nhưng client hoặc thư viện phải có đủ bằng chứng để kết luận.
- Request đã được gửi nhưng không nhận response: server có thể chưa xử lý, đang xử lý hoặc đã commit.
- Server trả 429, 503 hoặc lỗi tạm thời khác: có thể retry theo hợp đồng và hướng dẫn của server.
- Server trả lỗi validation hoặc authorization: retry cùng request thường không giúp ích.
- Client chủ động hủy request: việc hủy chờ response không đảm bảo server đã hủy nghiệp vụ đang chạy.

Đối với thao tác tạo thanh toán, đặt hàng, gửi tiền, phát hành vé hoặc gửi email, hãy giả định rằng request có thể đã được xử lý dù client không nhận được response. Idempotency phải được giải quyết ở phía server hoặc ở hệ thống thực hiện side effect.

## 4. Idempotency key cho các thao tác có side effect

Một cách phổ biến để hỗ trợ retry POST là client gửi một khóa nhận diện duy nhất trong header Idempotency-Key:

~~~http
POST /payments
Idempotency-Key: 8a8c7b2a-5a54-4a0c-b64c-3dbd7f0f4a21
Content-Type: application/json

{
  "orderId": "ORD-2026-0042",
  "amount": 1500000,
  "currency": "VND"
}
~~~

Client tạo key cho **một ý định nghiệp vụ** và dùng lại key đó cho mọi lần retry của ý định ấy. Nếu người dùng chủ động tạo một giao dịch mới, client phải tạo key mới. Không tạo key mới cho mỗi lần retry vì như vậy server không thể nhận ra các request thuộc cùng một thao tác.

Server tra cứu key trong phạm vi phù hợp, ví dụ tenant hoặc tài khoản + tên operation + key. Khi đã xử lý request, server lưu trạng thái và kết quả để lần gửi lại có thể trả lại kết quả đã ghi nhận thay vì thực hiện side effect lần nữa.

### 4.1. Vòng đời của một idempotency key

Một thiết kế cơ bản có thể có các trạng thái:

- IN_PROGRESS: request đầu tiên đã chiếm quyền xử lý key và đang thực hiện.
- COMPLETED: nghiệp vụ đã hoàn tất; server lưu status và response để replay.
- FAILED_FINAL: nghiệp vụ thất bại theo cách không nên thực hiện lại với cùng payload, tùy hợp đồng API.

Luồng xử lý:

1. Xác thực caller và xác định tenant/owner.
2. Kiểm tra key có tồn tại trong phạm vi operation không.
3. Tính fingerprint từ các trường nghiệp vụ có ý nghĩa của request.
4. Nếu key chưa tồn tại, tạo bản ghi IN_PROGRESS bằng thao tác có tính nguyên tử hoặc ràng buộc unique trong database.
5. Thực hiện nghiệp vụ.
6. Lưu trạng thái cuối cùng, mã HTTP và phần response cần replay.
7. Khi nhận lại cùng key và cùng fingerprint, trả lại kết quả đã lưu hoặc phản hồi trạng thái đang xử lý.
8. Khi nhận cùng key nhưng payload khác, từ chối vì client đã tái sử dụng key sai mục đích.

Một bảng lưu trữ minh họa:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id       VARCHAR(100) NOT NULL,
    operation_name  VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    state           VARCHAR(20) NOT NULL,
    response_status INTEGER,
    response_body   TEXT,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Đây là schema minh họa theo SQL phổ thông; kiểu dữ liệu, index và cách lưu response cần điều chỉnh theo database và chính sách bảo mật. Không lưu dữ liệu nhạy cảm hoặc thông tin thanh toán thô trong response cache nếu không có lý do và biện pháp bảo vệ phù hợp.

### 4.2. Unique constraint mới là lớp bảo vệ concurrency

Không nên triển khai idempotency chỉ bằng Map trong bộ nhớ của một instance ứng dụng. Khi có nhiều instance hoặc server restart, mỗi instance có thể không biết key đã được instance khác xử lý. Hai request đồng thời cũng có thể cùng kiểm tra “key chưa tồn tại” rồi cùng tạo side effect.

Ràng buộc unique ở database, transaction và xử lý xung đột insert là nền tảng để chỉ một request giành được quyền xử lý key. Cần định nghĩa rõ hành vi cho request đến trong lúc key đang IN_PROGRESS: chờ kết quả trong giới hạn, trả 202 Accepted kèm URL tra cứu trạng thái, hoặc trả 409 Conflict với mã lỗi có thể xử lý. Hãy tài liệu hóa hành vi để client biết có nên polling hay retry sau.

Nếu dùng distributed cache, cần hiểu độ bền dữ liệu, tính nguyên tử, failover và nguy cơ mất key. Cache chỉ có thể là lớp hỗ trợ khi vẫn bảo đảm được tính nhất quán cần thiết cho nghiệp vụ.

### 4.3. Không cho phép cùng key với payload khác

Nếu cùng key nhưng payload khác, server không được âm thầm coi đó là một request mới. Ví dụ client gửi key K1 cho khoản thanh toán 1.500.000 VND rồi vô tình dùng lại key K1 cho 2.000.000 VND. Server cần phát hiện request fingerprint khác nhau và trả lỗi rõ ràng, thường là 409 Conflict hoặc mã lỗi theo hợp đồng API.

Fingerprint nên dựa trên các trường nghiệp vụ ảnh hưởng kết quả. Cần chuẩn hóa representation trước khi hash để khác biệt không có ý nghĩa như thứ tự thuộc tính JSON không làm hai request tương đương trở thành khác nhau. Đồng thời, không bỏ qua trường có ý nghĩa như currency, account hoặc destination.

### 4.4. Thời gian lưu key và replay kết quả

Key cần được giữ lâu hơn khoảng thời gian client có thể retry, kể cả retry sau khi ứng dụng khởi động lại hoặc người dùng mở lại màn hình. Nếu xóa key quá sớm, một retry muộn có thể tạo side effect lần nữa.

Thời gian lưu phụ thuộc vào nghiệp vụ và hợp đồng với client. Một số API công bố thời hạn idempotency cụ thể. Khi hết hạn, client không được giả định server vẫn nhớ key. Hãy xác định rõ:

- Thời gian key được giữ.
- Response nào được replay.
- Cách xử lý key đang IN_PROGRESS.
- Có lưu lỗi cuối cùng hay không.
- Cách dọn dữ liệu cũ mà không xóa record đang xử lý.
- Hành vi khi cùng key được gửi sau thời hạn lưu.

Idempotency key không phải request ID hay trace ID. Request ID nhận diện một lần truyền request; trace ID liên kết các span của một luồng quan sát; idempotency key nhận diện một ý định nghiệp vụ xuyên suốt nhiều lần truyền request.

## 5. Side effect trong và ngoài database

Một transaction database có thể bảo đảm cập nhật các bảng trong cùng database theo tính nguyên tử, nhưng không tự động bao phủ một hệ thống bên ngoài. Ví dụ:

1. Ghi order vào database.
2. Gọi cổng thanh toán.
3. Gửi email xác nhận.

Nếu bước gọi cổng thanh toán thành công nhưng bước cập nhật database bị rollback, hệ thống có thể rơi vào trạng thái không nhất quán. Nếu retry toàn bộ transaction, lệnh thanh toán có thể bị gửi lần nữa.

Các hướng xử lý thường dùng:

- **Idempotency tại nhà cung cấp**: truyền cùng một idempotency key đến cổng thanh toán hoặc dịch vụ ngoài nếu họ hỗ trợ.
- **Transactional outbox**: ghi sự kiện cần gửi vào outbox trong cùng transaction với dữ liệu nghiệp vụ; worker gửi sự kiện sau commit.
- **Inbox/deduplication ở consumer**: consumer lưu event ID đã xử lý và bảo đảm một event không tạo side effect lặp.
- **Saga/compensation**: chia nghiệp vụ nhiều bước và định nghĩa hành động bù khi một bước thất bại; compensation không nhất thiết xóa được mọi tác động đã xảy ra.
- **Reconciliation**: đối soát định kỳ với hệ thống ngoài để xử lý trạng thái không xác định.

Không nên hứa hẹn “exactly once” chỉ vì có message broker hoặc retry. Trong hệ thống phân tán, delivery thường có thể lặp; mục tiêu thực tế là xử lý lặp an toàn bằng idempotency, deduplication, transaction boundary và đối soát.

## 6. Khi nào nên retry?

Chỉ retry lỗi có khả năng tạm thời và có lý do để kỳ vọng lần sau thành công. Một số tình huống thường được xem xét:

| Lỗi/kết quả | Có thể retry? | Điều kiện |
|---|---|---|
| Lỗi DNS hoặc kết nối tạm thời | Có thể | Xác định request chưa gây side effect hoặc thao tác đã được bảo vệ idempotency. |
| Timeout đọc response | Có thể | Với thao tác không idempotent, bắt buộc có cơ chế deduplication hoặc truy vấn trạng thái trước khi tạo lại. |
| HTTP 408 Request Timeout | Có thể | Tuân theo deadline và bảo đảm request lặp an toàn. |
| HTTP 429 Too Many Requests | Có thể | Tôn trọng Retry-After, giới hạn retry và giảm tải. |
| HTTP 500 Internal Server Error | Tùy trường hợp | Chỉ retry nếu lỗi có thể tạm thời; lỗi nghiệp vụ hoặc bug cố định sẽ không tự hết. |
| HTTP 502, 503, 504 | Có thể | Thường là lỗi gateway/service tạm thời; vẫn cần idempotency và deadline. |
| HTTP 400, 401, 403, 404, 422 | Thường không | Sửa payload, authentication, authorization hoặc tài nguyên trước khi gửi lại. |
| HTTP 409 Conflict | Tùy hợp đồng | Có thể là version conflict, key đang xử lý hoặc xung đột nghiệp vụ; không retry mù quáng. |
| HTTP 501 Not Implemented | Thường không | Server không hỗ trợ chức năng; retry cùng request không thay đổi điều đó. |

Danh sách trên là gợi ý, không phải luật áp dụng cho mọi API. Mã 500 có thể phát sinh sau khi side effect đã commit; 409 có thể biểu thị request cùng key đang xử lý và cần polling; 429 có thể đi kèm Retry-After. Hãy dựa vào error code của API và tài liệu của dịch vụ đích.

### 6.1. Backoff, jitter và giới hạn retry

Nếu nhiều client retry cùng thời điểm, tải có thể tăng đột biến và làm dịch vụ đang gặp sự cố càng khó phục hồi. Dùng exponential backoff để tăng dần khoảng chờ và jitter để phân tán thời điểm retry.

Một công thức tham khảo:

\[
delay_n = \min(cap,\ base \times 2^n \times random(0.5,\ 1.5))
\]

Trong đó n là số lần retry đã thực hiện; base là khoảng chờ ban đầu; cap là mức tối đa. Hệ thống thực tế có thể dùng cách jitter khác nhưng phải có giới hạn trên và dưới.

Chính sách retry cần có:

- Số lần thử tối đa, tính rõ lần đầu có được tính vào tổng số lần hay không.
- Deadline tổng cho toàn bộ operation.
- Timeout riêng cho mỗi lần gọi.
- Khoảng backoff và jitter.
- Danh sách exception/status được retry.
- Hành vi tôn trọng Retry-After.
- Giới hạn concurrency và retry budget để không khuếch đại tải.
- Log/metrics phân biệt lần gọi đầu với lần retry.

Không đặt số lần retry lớn mà không xét deadline. Ví dụ mỗi lần gọi timeout 5 giây và có 4 lần retry, cộng backoff có thể khiến một request kéo dài hàng chục giây, lâu hơn thời gian người dùng chờ hoặc deadline của gateway.

### 6.2. Tránh retry chồng tầng

Nếu frontend retry 3 lần, gateway retry 3 lần và service retry 3 lần, một thao tác có thể bị nhân lên đến 27 lần ở tầng sâu nhất. Hãy quyết định tầng nào sở hữu retry cho mỗi loại lỗi. Các tầng còn lại cần truyền deadline, tôn trọng cancellation và tránh tự retry thêm nếu không có hợp đồng rõ ràng.

Circuit breaker, bulkhead và rate limit có thể bổ sung cho retry. Retry xử lý lỗi tạm thời; circuit breaker tạm ngừng gọi dịch vụ đang lỗi; bulkhead giới hạn tài nguyên dành cho một nhóm dependency; rate limit bảo vệ năng lực xử lý. Chúng giải quyết các vấn đề khác nhau và cần phối hợp.

## 7. Áp dụng trong ứng dụng Spring Boot

### 7.1. API tạo payment nhận Idempotency-Key

Controller có thể yêu cầu key ở header:

~~~java
@RestController
@RequestMapping("/payments")
class PaymentController {

    private final PaymentService payments;

    PaymentController(PaymentService payments) {
        this.payments = payments;
    }

    @PostMapping
    ResponseEntity<PaymentResponse> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreatePaymentRequest request) {

        PaymentResponse response = payments.createOnce(key, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Đây là đoạn trích Spring MVC minh họa. Các kiểu PaymentService, PaymentResponse và CreatePaymentRequest thuộc ứng dụng. Trong production, controller còn cần xác thực caller, giới hạn độ dài/định dạng key, kiểm tra quyền truy cập và trả status phù hợp cho trường hợp key đang xử lý hoặc đã được dùng với payload khác.

Service cần thực hiện các bước kiểm tra key và ghi nhận kết quả trong persistence layer. Không đặt logic idempotency chỉ trong controller vì các đường gọi khác có thể bỏ qua nó. Cũng không dùng synchronized hoặc biến static làm cơ chế chính trong môi trường nhiều instance.

### 7.2. Tổ chức transaction

Nếu side effect chỉ là ghi trong cùng một relational database, việc tạo bản ghi idempotency, cập nhật dữ liệu nghiệp vụ và lưu kết quả có thể được phối hợp trong transaction phù hợp. Unique constraint bảo vệ hai request đồng thời cùng key. Khi request thứ hai gặp duplicate key, service đọc bản ghi hiện có và trả kết quả hoặc trạng thái đang xử lý.

Cần chú ý rằng một transaction dài giữ lock lâu có thể làm giảm throughput. Với nghiệp vụ cần gọi hệ thống ngoài, không giữ transaction database mở trong toàn bộ thời gian chờ mạng. Dùng outbox hoặc workflow có trạng thái để tách commit database khỏi việc gửi lệnh ra ngoài.

### 7.3. Retry một lời gọi HTTP bằng WebClient

Ví dụ sau minh họa retry có giới hạn cho một lời gọi POST đã gửi idempotency key. Chỉ retry lỗi được chọn:

~~~java
Mono<PaymentResult> submitPayment(
        WebClient webClient,
        PaymentCommand command,
        String idempotencyKey) {

    return webClient.post()
            .uri("/payments")
            .header("Idempotency-Key", idempotencyKey)
            .bodyValue(command)
            .retrieve()
            .bodyToMono(PaymentResult.class)
            .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .jitter(0.5)
                    .filter(this::isTransientFailure));
}

private boolean isTransientFailure(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 408
                || status == 429
                || status == 502
                || status == 503
                || status == 504;
    }
    return error instanceof WebClientRequestException;
}
~~~

Đây là đoạn trích cần các import Reactor, Spring WebFlux và các kiểu PaymentCommand/PaymentResult của ứng dụng. Ví dụ chưa xử lý Retry-After, deadline tổng, retry budget hoặc kiểm tra payload có thể gửi lại; phải bổ sung các chính sách này trước khi dùng production. Với POST, key phải được giữ nguyên qua mọi lần retry. Không retry một request tạo side effect nếu server không hỗ trợ idempotency.

Nếu dùng RestClient hoặc client đồng bộ khác, có thể triển khai retry ở service boundary hoặc dùng thư viện resilience phù hợp. Hãy bảo đảm exception được phân loại đúng, không retry validation/authentication, và không để nhiều tầng cùng retry ngoài dự kiến.

### 7.4. Phân biệt lỗi để trả response

API nên có error response ổn định, ví dụ:

~~~json
{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "The idempotency key was already used with a different request.",
  "traceId": "..."
}
~~~

traceId phục vụ quan sát và hỗ trợ; không dùng nó làm idempotency key. Client cần dựa vào code và HTTP status để quyết định hành động tiếp theo. Không đưa stack trace, thông tin database hoặc dữ liệu bí mật vào response.

## 8. Kiểm thử tính lũy đẳng và retry

Một bài test chỉ gọi endpoint một lần không chứng minh API hỗ trợ retry an toàn. Cần kiểm tra các tình huống lỗi và cạnh tranh:

1. Gửi cùng một PUT hai lần; trạng thái cuối cùng phải đúng như representation được yêu cầu.
2. Gửi DELETE hai lần; tài nguyên cuối cùng vẫn ở trạng thái đã xóa theo hợp đồng API.
3. Gửi cùng POST và cùng idempotency key hai lần; chỉ có một payment/order được tạo và lần sau nhận kết quả đã lưu hoặc trạng thái đã định nghĩa.
4. Gửi cùng key nhưng payload khác; server phải từ chối.
5. Gửi hai request đồng thời cùng key đến các instance khác nhau; chỉ một request được quyền tạo side effect.
6. Giả lập server commit thành công nhưng response bị mất; retry phải không tạo side effect thứ hai.
7. Giả lập key ở trạng thái IN_PROGRESS; client nhận đúng hành vi chờ, polling hoặc conflict.
8. Giả lập 429 kèm Retry-After; client tuân thủ thời điểm retry và vẫn nằm trong deadline.
9. Giả lập 400/401/403/422; client không retry mù quáng.
10. Khởi động lại service hoặc chuyển request sang instance khác; idempotency vẫn hoạt động vì trạng thái được lưu bền vững.
11. Kiểm tra thời điểm hết hạn key và tác động của retry muộn.
12. Kiểm tra outbox/consumer khi cùng một event được giao nhiều lần.

Các test concurrency nên sử dụng database hoặc môi trường tích hợp đủ gần production. Test với mock repository đơn lẻ không thể chứng minh unique constraint và transaction hoạt động đúng khi có nhiều request đồng thời.

## 9. Quan sát và vận hành

Theo dõi riêng các chỉ số:

- Số request ban đầu và số lần retry.
- Tỷ lệ retry thành công sau lỗi tạm thời.
- Số key được replay, số key đang IN_PROGRESS và số key bị dùng lại với payload khác.
- Tỷ lệ timeout, 429, 5xx và thời gian chờ theo dependency.
- Số side effect bị deduplicate.
- Tuổi của request đang xử lý và số bản ghi idempotency quá hạn.
- Retry exhaustion, circuit breaker open và retry budget đã dùng.

Log nên có trace ID, request ID, operation, trạng thái retry, số attempt và một dạng nhận diện key đã được che hoặc hash nếu key có thể chứa thông tin nhạy cảm. Tránh log toàn bộ request/response của payment hoặc dữ liệu cá nhân. Metrics cần có cardinality giới hạn; không gắn idempotency key duy nhất vào label vì sẽ làm bùng nổ số time series.

Khi điều tra một giao dịch bị timeout, cần tra được trạng thái nghiệp vụ và idempotency record. Client không nên tự suy ra rằng “không nhận response” đồng nghĩa “giao dịch thất bại”. Hãy cung cấp endpoint tra cứu trạng thái operation nếu nghiệp vụ cần người dùng hoặc hệ thống gọi biết kết quả cuối cùng.

## 10. Checklist thiết kế trước khi bật retry

- [ ] Xác định method và ngữ nghĩa của thao tác: safe, idempotent hay có side effect lặp.
- [ ] Xác định các side effect trong database và ở hệ thống bên ngoài.
- [ ] Với POST hoặc thao tác không idempotent, định nghĩa idempotency key và phạm vi duy nhất.
- [ ] Ràng buộc unique ở persistence layer và xử lý request đồng thời.
- [ ] Tính request fingerprint để phát hiện dùng lại key với payload khác.
- [ ] Quy định thời hạn lưu key, trạng thái IN_PROGRESS và cách replay response.
- [ ] Chỉ retry lỗi có khả năng tạm thời; không retry validation/authentication theo mặc định.
- [ ] Cấu hình max attempts, timeout, deadline, exponential backoff, jitter và Retry-After.
- [ ] Tránh retry chồng tầng và giới hạn retry budget.
- [ ] Kiểm thử trường hợp server commit nhưng response bị mất.
- [ ] Kiểm thử duplicate request đồng thời, restart và nhiều instance.
- [ ] Theo dõi retry, deduplication, timeout và side effect trong production.

## 11. Nguyên tắc cần nhớ

HTTP method cung cấp ngữ nghĩa để client hiểu request có thể lặp lại hay không, nhưng không tự bảo vệ mọi nghiệp vụ. GET thường phù hợp với retry; PUT và DELETE có ngữ nghĩa idempotent; POST và PATCH cần xem xét hợp đồng cụ thể. Khi client timeout, kết quả có thể chưa xác định vì server đã thực hiện side effect nhưng response bị mất.

Với thao tác tạo đơn hàng, thanh toán hoặc gửi lệnh ra hệ thống ngoài, hãy nhận diện một ý định nghiệp vụ bằng idempotency key, lưu trạng thái bền vững, xử lý cạnh tranh bằng ràng buộc duy nhất và replay kết quả đã ghi nhận. Retry chỉ nên áp dụng cho lỗi tạm thời, có backoff/jitter, deadline và giới hạn tải. Thiết kế như vậy giúp hệ thống phục hồi tốt hơn mà không biến một lỗi mạng thành giao dịch trùng.
