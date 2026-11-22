# Xử lý lỗi tích hợp trong DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao lỗi thường xuất hiện tại ranh giới giữa ứng dụng và hệ thống bên ngoài.
- Phân loại lỗi tích hợp theo nguồn gốc, khả năng phục hồi và tác động nghiệp vụ.
- Thiết kế mô hình lỗi thống nhất để adapter, connector và workflow cùng sử dụng.
- Phân biệt lỗi kết nối, timeout, lỗi giao thức, lỗi xác thực, lỗi dữ liệu và lỗi nghiệp vụ.
- Chọn chính sách retry phù hợp với idempotency, backoff, jitter và deadline.
- Áp dụng circuit breaker, bulkhead, rate limiting và backpressure để bảo vệ hệ thống.
- Xử lý partial failure, kết quả không chắc chắn và thao tác phân tán bằng compensation hoặc Saga.
- Ánh xạ lỗi của hệ thống ngoài thành lỗi miền có thể hiểu và xử lý trong DSL.
- Thiết kế log, metric, distributed trace và audit để điều tra sự cố.
- Kiểm thử khả năng phục hồi bằng fault injection, timeout giả lập và tình huống lỗi thực tế.

## 1. Lỗi tích hợp là gì?

Lỗi tích hợp (integration error) xảy ra khi một ứng dụng giao tiếp với một thành phần khác nhưng quá trình trao đổi hoặc xử lý không diễn ra như mong đợi. Thành phần bên ngoài có thể là REST API, SOAP service, message broker, database, hệ thống thanh toán, dịch vụ định danh, nền tảng lưu trữ hoặc một ứng dụng nội bộ khác.

Ví dụ, một workflow xử lý đơn hàng có thể gọi ba hệ thống:

1. Dịch vụ kho để giữ sản phẩm.
2. Cổng thanh toán để xác thực giao dịch.
3. Dịch vụ vận chuyển để tạo yêu cầu giao hàng.

Một lời gọi có thể thất bại vì mạng mất kết nối, dịch vụ quá tải, thông tin xác thực hết hạn, payload không còn tương thích hoặc nghiệp vụ từ chối yêu cầu. Những lỗi này có nguồn gốc và cách xử lý khác nhau.

Trong DSL tích hợp ứng dụng, xử lý lỗi cần được biểu diễn như một phần của luồng thực thi. Người thiết kế phải chỉ rõ lỗi nào có thể retry, lỗi nào cần chuyển sang nhánh xử lý khác, khi nào cần fallback, khi nào cần dừng quy trình và khi nào phải thực hiện hành động bù.

Ví dụ cú pháp minh họa:

~~~text
integration "reserve_inventory" {
    call inventory.reserve(order.items)

    timeout = 5 seconds

    retry {
        maxAttempts = 3
        on = [TIMEOUT, TEMPORARY_UNAVAILABLE]
        backoff = exponential
    }

    onError {
        PERMANENT_FAILURE -> route "manual_review"
        otherwise -> failWorkflow
    }
}
~~~

Cú pháp thực tế tùy DSL, nhưng contract cần diễn đạt được lỗi, policy và hành vi sau lỗi một cách rõ ràng.

## 2. Vì sao ranh giới tích hợp dễ phát sinh lỗi?

Một lời gọi nội bộ và một lời gọi qua ranh giới ứng dụng có đặc điểm khác nhau. Khi gọi một hệ thống khác, ứng dụng không kiểm soát hoàn toàn trạng thái, tốc độ, khả năng sẵn sàng và phiên bản của hệ thống đó.

Các nguyên nhân phổ biến:

- **Network failure:** mất kết nối, DNS lỗi, TLS handshake thất bại hoặc kết nối bị reset.
- **Timeout:** hệ thống ngoài phản hồi chậm hơn thời gian chờ cho phép.
- **Service unavailable:** dịch vụ đang bảo trì, quá tải hoặc bị restart.
- **Rate limit:** client gửi quá nhiều request trong một khoảng thời gian.
- **Authentication failure:** token hết hạn, chữ ký sai hoặc credential bị thu hồi.
- **Authorization failure:** danh tính hợp lệ nhưng không có quyền thực hiện thao tác.
- **Protocol error:** request hoặc response không đúng giao thức hay media type.
- **Schema mismatch:** field bị đổi tên, sai kiểu, thiếu dữ liệu hoặc phiên bản contract không tương thích.
- **Business rejection:** hệ thống nhận request nhưng từ chối theo quy tắc nghiệp vụ.
- **Data conflict:** tài nguyên đã thay đổi, version không còn khớp hoặc khóa bị trùng.
- **Partial failure:** một phần thao tác thành công nhưng phần khác thất bại.
- **Unknown outcome:** client không biết server đã thực hiện thao tác hay chưa vì response bị mất.

### 2.1. Hệ thống ngoài có thể thành công dù client thấy lỗi

Giả sử client gửi yêu cầu tạo thanh toán. Cổng thanh toán xử lý thành công, nhưng kết nối bị đứt trước khi response về client. Client nhận timeout và không biết giao dịch đã được tạo hay chưa.

Nếu client gửi lại một request mới mà không có idempotency key, khách hàng có thể bị tính tiền hai lần.

Đây là lý do timeout không đồng nghĩa với thao tác thất bại. Hệ thống cần phân biệt:
- Chắc chắn chưa gửi request.
- Đã gửi nhưng không nhận được response.
- Đã nhận response thành công.
- Đã nhận response lỗi rõ ràng.
- Không thể xác định kết quả và cần đối soát.

### 2.2. Lỗi là điều bình thường trong hệ thống phân tán

Không thể giả định mạng luôn ổn định, service luôn sẵn sàng hoặc hai hệ thống luôn cập nhật cùng lúc. Một integration framework tốt thiết kế cho lỗi có thể xảy ra và xác định hành vi khi lỗi xuất hiện.

### 2.3. Lỗi cần được phân loại trước khi xử lý

Không nên retry mọi lỗi. Retry lỗi xác thực thường không giúp ích; retry một thao tác tạo dữ liệu không idempotent có thể tạo bản ghi trùng; bỏ qua lỗi nghiệp vụ có thể làm sai quyết định.

## 3. Phân loại lỗi tích hợp

Phân loại rõ giúp policy được chọn đúng và giúp người vận hành hiểu nguyên nhân.

### 3.1. Lỗi tạm thời (transient)

Lỗi có thể tự hết sau một khoảng thời gian:
- Connection reset.
- Temporary DNS failure.
- Service unavailable trong thời gian ngắn.
- Rate limit có thời hạn.
- Một số lỗi database deadlock.
- Timeout do tải đột biến.

Có thể retry nếu operation an toàn và vẫn còn deadline.

### 3.2. Lỗi lâu dài hoặc không thể retry (permanent)

Lỗi thường không tự hết nếu giữ nguyên request:
- Field bắt buộc bị thiếu.
- Sai định dạng dữ liệu.
- Resource không tồn tại.
- Operation không được hỗ trợ.
- Business rule từ chối.
- Credential bị thu hồi.
- Caller không có quyền.

Cần sửa input, cấu hình hoặc quyền trước khi thử lại.

### 3.3. Lỗi hạ tầng (infrastructure)

Lỗi liên quan mạng, DNS, TLS, connection pool, broker, database hoặc tài nguyên runtime. Một số lỗi hạ tầng là transient; một số là cấu hình sai kéo dài.

### 3.4. Lỗi giao thức (protocol)

Ví dụ:
- HTTP status không nằm trong contract.
- Response không đúng Content-Type.
- JSON không parse được.
- SOAP Fault.
- Message không đúng envelope.
- Header bắt buộc bị thiếu.

Adapter cần chuyển lỗi giao thức thành mô hình lỗi thống nhất.

### 3.5. Lỗi xác thực và phân quyền

401 thường biểu thị thông tin xác thực thiếu hoặc không hợp lệ. 403 biểu thị danh tính đã được xác thực nhưng không có quyền. Với các protocol khác, mã lỗi có thể khác nhưng semantics cần được giữ khi ánh xạ.

### 3.6. Lỗi dữ liệu và schema

Một hệ thống ngoài có thể trả dữ liệu sai kiểu, thiếu field, enum mới hoặc timestamp không đúng format. Đây có thể là lỗi contract, dữ liệu nguồn hoặc thay đổi phiên bản.

### 3.7. Lỗi nghiệp vụ

Ví dụ:
- Không đủ số dư.
- Không còn hàng.
- Đơn hàng đã ở trạng thái terminal.
- Khách hàng không đủ điều kiện.
- Giao dịch vượt hạn mức.

Lỗi nghiệp vụ thường không nên retry tự động nếu trạng thái hoặc input không thay đổi.

### 3.8. Lỗi một phần

Một batch có thể xử lý thành công 8 trong 10 phần tử. Một workflow song song có thể có hai nhánh thành công và một nhánh thất bại. Không nên gộp các trạng thái này thành một lỗi duy nhất mà bỏ mất kết quả đã có.

## 4. Mô hình lỗi thống nhất

Mỗi connector có thể nhận lỗi theo định dạng riêng. Một lớp tích hợp nên chuẩn hóa chúng thành một mô hình chung để workflow không phải phụ thuộc vào chi tiết của từng nhà cung cấp.

Một kiểu lỗi minh họa:

~~~text
IntegrationError {
    code: ErrorCode
    category: ErrorCategory
    message: String
    operation: String
    system: String
    retryable: Boolean
    retryAfter: Duration?
    correlationId: String?
    externalRequestId: String?
    occurredAt: Instant
    details: Map<String, Value>
    cause: Error?
}
~~~

### 4.1. Error code

Error code là định danh ổn định để chương trình phân nhánh. Không nên dùng message tự do làm điều kiện logic vì message có thể đổi theo ngôn ngữ hoặc phiên bản.

Ví dụ:
- INTEGRATION_TIMEOUT.
- CONNECTION_UNAVAILABLE.
- AUTHENTICATION_FAILED.
- RATE_LIMITED.
- INVALID_RESPONSE.
- SCHEMA_MISMATCH.
- RESOURCE_CONFLICT.
- BUSINESS_REJECTED.
- UNKNOWN_OUTCOME.

### 4.2. Category

Category gom các lỗi có hành vi tương tự:
- TRANSIENT.
- PERMANENT.
- AUTHENTICATION.
- AUTHORIZATION.
- VALIDATION.
- BUSINESS.
- PROTOCOL.
- CAPACITY.
- UNKNOWN.

Một error code có thể thuộc một category. Category hỗ trợ policy tổng quát, còn code hỗ trợ xử lý cụ thể.

### 4.3. Retryable

Thuộc tính retryable là gợi ý từ adapter hoặc connector. Workflow vẫn cần xem xét idempotency, deadline và retry budget trước khi retry.

Không nên hiểu retryable = true là lệnh bắt buộc retry. Nó chỉ cho biết lỗi có thể tạm thời.

### 4.4. Retry-After

Một số service trả thời gian chờ trước khi thử lại. Adapter nên giữ lại thông tin này dưới dạng duration hoặc instant đã chuẩn hóa. Retry policy có thể kết hợp Retry-After với backoff cục bộ.

### 4.5. Cause chain

Cause chain giữ lỗi gốc để điều tra, ví dụ IntegrationTimeout do SocketTimeout do ConnectionReset. Cần giới hạn độ sâu và loại bỏ dữ liệu nhạy cảm khỏi message.

### 4.6. Message dành cho người dùng và message dành cho vận hành

Không nên dùng cùng một chuỗi lỗi nội bộ cho cả API response và log. Message người dùng cần dễ hiểu, không tiết lộ hạ tầng. Log kỹ thuật có thể chứa mã lỗi, service, operation và nguyên nhân đã được lọc an toàn.

## 5. Lớp adapter và ranh giới lỗi

Adapter chuyển đổi giữa mô hình nội bộ và protocol của hệ thống ngoài.

~~~text
Workflow DSL
     |
     v
Integration Contract
     |
     v
Connector / Adapter
     |
     v
Protocol Client
     |
     v
External System
~~~

### 5.1. Adapter chịu trách nhiệm gì?

Adapter thường:
- Serialize request theo contract ngoài.
- Gửi request qua HTTP, message broker hoặc protocol khác.
- Xác thực và gắn metadata.
- Parse response.
- Kiểm tra status và schema.
- Chuyển lỗi ngoài thành IntegrationError.
- Giữ correlation ID và external request ID.
- Áp dụng timeout cấp transport nếu phù hợp.

### 5.2. Không để workflow phụ thuộc lỗi riêng của vendor

Nếu mỗi workflow phải kiểm tra các mã lỗi riêng của từng nhà cung cấp, logic tích hợp sẽ bị phân tán và khó thay thế connector.

Adapter nên ánh xạ lỗi vendor thành code nội bộ ổn định. Chi tiết vendor vẫn có thể được lưu trong cause hoặc details đã lọc.

### 5.3. Anti-corruption layer

Anti-corruption layer ngăn mô hình dữ liệu và lỗi của hệ thống ngoài làm biến dạng domain model nội bộ. Nó chuyển đổi thuật ngữ, trạng thái, kiểu dữ liệu và semantics giữa hai hệ thống.

Ví dụ, provider trả trạng thái PAYMENT_DECLINED, còn domain model nội bộ dùng PaymentRejected với reason code được chuẩn hóa.

### 5.4. Contract rõ ràng

Integration contract cần xác định operation, request schema, response schema, error schema, timeout mặc định, authentication, retry semantics và version. Adapter không nên tự đoán hành vi khi contract thiếu thông tin.

## 6. Ánh xạ lỗi từ protocol sang domain

Một hệ thống ngoài có thể dùng HTTP, SOAP, gRPC hoặc message broker. Mỗi protocol có cách biểu diễn lỗi khác nhau.

### 6.1. HTTP

HTTP status code là tín hiệu quan trọng nhưng không đủ để xác định toàn bộ semantics.

Ví dụ:
- 400 có thể là lỗi request.
- 401 là authentication.
- 403 là authorization.
- 404 là không tìm thấy.
- 409 là conflict.
- 429 là rate limit.
- 500 hoặc 503 có thể là lỗi server tạm thời hoặc không rõ.
- 504 có thể biểu thị gateway timeout.

Adapter cần đọc thêm error body và contract của provider để phân loại chính xác.

### 6.2. SOAP Fault

SOAP có thể trả Fault code, reason và detail. Adapter nên parse các trường này, ánh xạ Fault code sang error category và giữ correlation hoặc provider request ID nếu có.

### 6.3. gRPC

gRPC có status code như UNAVAILABLE, DEADLINE_EXCEEDED, INVALID_ARGUMENT, PERMISSION_DENIED và NOT_FOUND. Không nên ánh xạ tất cả status khác OK thành cùng một lỗi generic.

### 6.4. Message broker

Broker có thể báo:
- Publish failure.
- Negative acknowledgement.
- Consumer timeout.
- Message lock expired.
- Poison message.
- Dead-letter routing failure.

Lỗi publish khác với lỗi xử lý message ở consumer. Cần giữ rõ giai đoạn nào thất bại.

### 6.5. Database

Database error có thể gồm constraint violation, deadlock, serialization failure, connection loss hoặc query timeout. Một số có thể retry transaction; một số cần sửa dữ liệu hoặc query.

### 6.6. Bảng ánh xạ minh họa

| Lỗi ngoài | Lỗi nội bộ | Hành vi thường cân nhắc |
|---|---|---|
| HTTP 429 | RATE_LIMITED | Chờ theo Retry-After |
| HTTP 503 | TEMPORARY_UNAVAILABLE | Retry có giới hạn |
| HTTP 401 | AUTHENTICATION_FAILED | Refresh credential nếu được phép |
| HTTP 403 | AUTHORIZATION_FAILED | Dừng và báo quyền |
| HTTP 409 | RESOURCE_CONFLICT | Đọc lại hoặc xử lý conflict |
| gRPC DEADLINE_EXCEEDED | INTEGRATION_TIMEOUT | Kiểm tra unknown outcome |
| gRPC INVALID_ARGUMENT | INVALID_REQUEST | Sửa payload |
| DB deadlock | TRANSIENT_DATABASE_CONFLICT | Retry transaction an toàn |
| Invalid JSON | INVALID_RESPONSE | Báo lỗi contract, không retry mù |

Bảng này chỉ là quy tắc khởi đầu. Semantics cuối cùng phải theo contract của từng operation.

## 7. Timeout và deadline

Timeout giới hạn thời gian một thao tác được phép chờ. Không có timeout, một workflow có thể bị treo vô hạn khi hệ thống ngoài không phản hồi.

### 7.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối. Nó khác với thời gian chờ response sau khi kết nối đã được tạo.

### 7.2. Read timeout

Read timeout giới hạn thời gian chờ dữ liệu phản hồi hoặc khoảng thời gian giữa các lần nhận dữ liệu, tùy client library.

### 7.3. Total request timeout

Total timeout giới hạn tổng thời gian operation, bao gồm các bước cần thiết theo semantics của client. Đây thường là giới hạn quan trọng đối với workflow.

### 7.4. Deadline propagation

Nếu workflow có deadline 30 giây và đã dùng 12 giây ở các bước trước, operation tiếp theo chỉ còn khoảng 18 giây. Truyền deadline còn lại xuống connector và service con giúp tránh tiếp tục xử lý sau khi kết quả không còn hữu ích.

~~~text
workflow "submit_order" {
    deadline = 30 seconds

    call inventory.reserve(order)
        timeout = remainingDeadline()

    call payment.authorize(order)
        timeout = remainingDeadline()
}
~~~

### 7.5. Timeout lồng nhau

Timeout của client, gateway, service và workflow cần được cấu hình có quan hệ rõ. Nếu gateway timeout sau 10 giây nhưng client chờ 60 giây, client có thể chờ một kết quả không bao giờ đến từ gateway.

### 7.6. Timeout không chứng minh server chưa thực hiện

Nếu request đã tới server, server có thể tiếp tục xử lý sau khi client timeout. Với operation có tác dụng phụ, cần idempotency key hoặc query trạng thái để giải quyết kết quả không chắc chắn.

### 7.7. Chọn timeout

Timeout nên dựa trên latency thực tế, SLA, deadline của workflow và khả năng của hệ thống đích. Timeout quá ngắn tạo lỗi giả; timeout quá dài giữ tài nguyên và làm chậm phục hồi.

## 8. Retry có kiểm soát

Retry là gửi lại operation sau một lỗi được xem là có thể phục hồi.

~~~text
retry {
    maxAttempts = 4
    initialDelay = 200 milliseconds
    backoff = exponential
    maxDelay = 5 seconds
    retryOn = [TIMEOUT, TEMPORARY_UNAVAILABLE, RATE_LIMITED]
}
~~~

### 8.1. Chỉ retry lỗi phù hợp

Có thể cân nhắc retry:
- Connection reset.
- Temporary unavailable.
- Một số timeout.
- Rate limit sau thời gian chờ.
- Một số lỗi conflict tạm thời có thể giải quyết bằng retry transaction.

Không nên retry mù:
- Invalid input.
- Authentication bị thu hồi.
- Authorization denied.
- Business rejection.
- Schema mismatch.
- Unsupported operation.

### 8.2. Exponential backoff

Thời gian chờ tăng theo số lần thử:

\[
delay_n = \min(maxDelay,\ initialDelay \times 2^{n-1})
\]

Ví dụ initialDelay 200 ms:
- Lần retry 1: 200 ms.
- Lần retry 2: 400 ms.
- Lần retry 3: 800 ms.
- Lần retry 4: 1.6 giây.

Giới hạn maxDelay để thời gian chờ không tăng vô hạn.

### 8.3. Jitter

Nếu nhiều client cùng retry theo lịch giống nhau, chúng có thể tạo một đợt tải mới cùng thời điểm. Jitter thêm độ ngẫu nhiên vào delay để phân tán request.

Một dạng full jitter:

\[
delay = random(0,\ cappedExponentialDelay)
\]

### 8.4. Retry-After

Nếu server gửi Retry-After, client nên tôn trọng hướng dẫn đó trong giới hạn deadline và policy của mình. Không nên retry sớm hơn chỉ vì backoff cục bộ nhỏ hơn.

### 8.5. Max attempts

Cần xác định maxAttempts có bao gồm lần gọi đầu hay chỉ số lần retry. Ví dụ maxAttempts = 3 thường có nghĩa tối đa ba lần gọi tổng cộng, nhưng DSL phải nói rõ.

### 8.6. Retry budget

Retry budget giới hạn tổng số retry trong một khoảng thời gian hoặc trên một tỷ lệ request. Khi service đang quá tải, retry budget giúp tránh khuếch đại tải.

### 8.7. Retry phải tôn trọng deadline

Không bắt đầu một lần retry nếu thời gian còn lại không đủ để thực hiện operation và trả kết quả hữu ích.

### 8.8. Tránh retry ở nhiều tầng

Nếu client, gateway, adapter và service đều retry ba lần, một request có thể tạo ra rất nhiều lời gọi. Chọn một tầng chịu trách nhiệm retry chính hoặc thiết kế ngân sách tổng thể.

## 9. Idempotency và kết quả không chắc chắn

Idempotency là thuộc tính quan trọng khi retry operation có tác dụng phụ.

### 9.1. Idempotent operation

Một operation idempotent có thể được thực hiện lặp lại mà trạng thái cuối cùng không thay đổi so với thực hiện một lần, theo semantics đã định.

GET thường idempotent. PUT có thể idempotent nếu nó đặt tài nguyên về một biểu diễn xác định. POST tạo thanh toán thường không idempotent nếu không có cơ chế hỗ trợ.

### 9.2. Idempotency key

Client gửi key duy nhất cho một thao tác logic:

~~~http
POST /payments
Idempotency-Key: payment-order-2048
Content-Type: application/json

{
  "orderId": "ORD-2048",
  "amount": "550000.00",
  "currency": "VND"
}
~~~

Server lưu kết quả theo key. Khi nhận request lặp với cùng key và cùng nội dung, server có thể trả lại kết quả trước đó.

### 9.3. Key và payload không khớp

Nếu cùng key được gửi với payload khác, server nên trả conflict hoặc lỗi tương ứng. Không nên âm thầm xem đây là cùng một thao tác.

### 9.4. Deduplication window

Server cần định nghĩa thời gian lưu key và kết quả. Sau khi key hết hạn, request cũ có thể bị xem như thao tác mới. Client cần biết giới hạn này.

### 9.5. Unknown outcome

Nếu client timeout sau khi gửi request:
1. Dùng cùng idempotency key để retry nếu contract hỗ trợ.
2. Hoặc truy vấn trạng thái operation bằng external reference.
3. Chỉ tạo thao tác mới khi đã xác định thao tác cũ chưa thành công hoặc đã được xử lý an toàn.

### 9.6. Exactly-once

Trong hệ thống phân tán, không nên hứa exactly-once execution một cách chung chung. Thực tế thường kết hợp at-least-once delivery, idempotent processing, deduplication và transaction boundary để đạt hiệu ứng nghiệp vụ một lần trong phạm vi xác định.

## 10. Circuit breaker

Circuit breaker ngăn ứng dụng tiếp tục gọi một service đang liên tục thất bại.

### 10.1. Ba trạng thái

- **CLOSED:** request được phép đi qua; lỗi được thống kê.
- **OPEN:** request bị chặn ngay hoặc trả lỗi nhanh.
- **HALF_OPEN:** cho một số request thử nghiệm đi qua để kiểm tra service đã phục hồi chưa.

Luồng trạng thái:

~~~text
CLOSED
  | failure threshold reached
  v
OPEN
  | reset timeout elapsed
  v
HALF_OPEN
  | probe succeeds
  +-----------------> CLOSED
  |
  | probe fails
  v
OPEN
~~~

### 10.2. Ngưỡng mở circuit

Circuit có thể mở khi tỷ lệ lỗi vượt ngưỡng trong một cửa sổ thời gian, số lỗi liên tiếp vượt giới hạn hoặc latency quá cao. Cần bỏ qua các lỗi không phản ánh sức khỏe service, chẳng hạn validation error từ client.

### 10.3. Reset timeout

Sau một khoảng thời gian, circuit chuyển HALF_OPEN để thử service. Nếu probe thành công, circuit đóng lại. Nếu thất bại, circuit mở lại.

### 10.4. Fallback khi circuit mở

Workflow có thể dùng cache nếu dữ liệu đủ mới, trả trạng thái pending, chuyển sang manual processing, dùng provider dự phòng hoặc từ chối nhanh với lỗi tạm thời.

Fallback phải phù hợp nghiệp vụ. Không nên dùng dữ liệu cũ cho một thao tác cần độ chính xác tuyệt đối.

### 10.5. Circuit breaker không thay thế timeout

Một request đơn lẻ vẫn có thể treo nếu không có timeout. Circuit breaker thường cần timeout để phát hiện lỗi và cần metrics để đánh giá sức khỏe.

### 10.6. Circuit breaker theo dependency

Có thể dùng breaker riêng theo service, operation hoặc endpoint. Breaker quá rộng có thể chặn cả operation khỏe mạnh; breaker quá nhỏ có thể tạo quá nhiều state và khó vận hành.

## 11. Bulkhead và giới hạn concurrency

Bulkhead cô lập tài nguyên để sự cố ở một dependency không làm sụp toàn bộ ứng dụng.

### 11.1. Connection pool riêng

Dịch vụ thanh toán và dịch vụ báo cáo có thể dùng connection pool riêng. Khi báo cáo chậm, nó không chiếm hết connection của thanh toán.

### 11.2. Worker pool riêng

Các integration có đặc điểm latency khác nhau có thể dùng worker pool riêng hoặc quota riêng.

### 11.3. Giới hạn in-flight request

~~~text
integration "payment" {
    maxConcurrent = 20
    queueLimit = 100
}
~~~

Khi đạt giới hạn, request mới có thể chờ, bị từ chối nhanh hoặc được đưa vào queue bền vững theo policy.

### 11.4. Queue limit

Queue không giới hạn có thể làm bộ nhớ tăng vô hạn và khiến request chờ lâu hơn deadline. Queue limit giúp hệ thống từ chối sớm khi không còn khả năng xử lý.

### 11.5. Bulkhead và fairness

Quota theo tenant hoặc workflow giúp một khách hàng không chiếm toàn bộ capacity của dependency.

## 12. Rate limiting và backpressure

Rate limiting giới hạn tốc độ request. Backpressure điều chỉnh tốc độ producer theo khả năng xử lý của consumer.

### 12.1. Rate limit

Provider có thể cho phép 100 request mỗi phút. Vượt giới hạn có thể trả 429 hoặc một mã lỗi riêng.

### 12.2. Token bucket

Token bucket cho phép một lượng request bùng nổ trong giới hạn bucket, đồng thời duy trì tốc độ trung bình. Mỗi request tiêu thụ một token; token được bổ sung theo thời gian.

### 12.3. Leaky bucket

Leaky bucket xử lý request theo tốc độ ổn định, giúp làm phẳng burst. Nó có thể phù hợp với hệ thống cần tải đều.

### 12.4. Backpressure

Nếu consumer xử lý chậm, producer nên giảm tốc độ gửi hoặc tạm dừng phát sinh thêm công việc. Với stream hoặc message queue, backpressure giúp tránh buffer tăng vô hạn.

### 12.5. Phối hợp với retry

Retry làm tăng lượng request. Rate limiting và retry policy phải được thiết kế cùng nhau. Nếu provider đang trả 429, retry ngay có thể làm tình trạng tệ hơn.

## 13. Fallback và chế độ suy giảm

Fallback là hành vi thay thế khi dependency chính không sẵn sàng.

Ví dụ:
- Đọc từ cache khi dịch vụ catalog tạm thời lỗi.
- Dùng phương thức giao hàng mặc định khi dịch vụ tính phí không phản hồi.
- Lưu yêu cầu vào queue để xử lý sau.
- Chuyển một quyết định sang manual review.
- Trả kết quả một phần và đánh dấu dữ liệu còn thiếu.

### 13.1. Fallback cần được định nghĩa theo nghiệp vụ

Fallback giá vận chuyển bằng 0 có thể gây thất thoát. Fallback dùng giá ước tính có thể chấp nhận nếu response ghi rõ đó là provisional quote.

### 13.2. Cache fallback

Cần xác định TTL, độ cũ tối đa được chấp nhận, cache miss behavior, cách đánh dấu dữ liệu stale và có được dùng cache cho thao tác ghi hay không.

### 13.3. Degraded mode

Một ứng dụng có thể tiếp tục một số chức năng khi một dependency lỗi. DSL nên cho phép biểu diễn rõ phần chức năng nào bị suy giảm và phần nào phải dừng.

### 13.4. Không che giấu lỗi

Nếu fallback được sử dụng, log và response nên ghi nhận trạng thái degraded. Nếu không, người vận hành có thể nghĩ hệ thống đang hoạt động bình thường trong khi dữ liệu bị cũ hoặc thiếu.

## 14. Partial failure và batch integration

Một operation tích hợp có thể chứa nhiều phần tử. Không phải tất cả đều thành công hoặc thất bại cùng nhau.

Ví dụ request batch:

~~~json
{
  "items": [
    {"id": "A-1", "quantity": 2},
    {"id": "A-2", "quantity": 5},
    {"id": "A-3", "quantity": 1}
  ]
}
~~~

Response một phần:

~~~json
{
  "results": [
    {"id": "A-1", "status": "SUCCEEDED"},
    {"id": "A-2", "status": "FAILED", "code": "OUT_OF_STOCK"},
    {"id": "A-3", "status": "SUCCEEDED"}
  ],
  "summary": {
    "succeeded": 2,
    "failed": 1
  }
}
~~~

### 14.1. Atomic batch

Atomic batch bảo đảm toàn bộ thao tác thành công hoặc không thao tác nào được commit. Điều này chỉ có thể thực hiện nếu hệ thống hỗ trợ transaction phù hợp.

### 14.2. Non-atomic batch

Non-atomic batch cho phép mỗi phần tử có kết quả riêng. Client cần đọc từng kết quả và chỉ retry phần thất bại.

### 14.3. Không retry toàn bộ batch một cách mù quáng

Nếu hai phần tử đã thành công và một phần tử lỗi, gửi lại toàn bộ batch có thể tạo tác dụng phụ trùng. Dùng item ID, idempotency key theo phần tử hoặc endpoint kiểm tra trạng thái.

### 14.4. Kết quả một phần trong workflow

Workflow có thể lưu kết quả thành công, đưa phần thất bại vào retry queue và tiếp tục khi đạt điều kiện. Cần có policy rõ cho trường hợp không bao giờ đạt đủ kết quả.

## 15. Transaction và lỗi phân tán

Một transaction database thường không bao phủ được nhiều hệ thống độc lập. Khi tích hợp nhiều service, cần xác định consistency model và cách phục hồi.

### 15.1. Local transaction

Một adapter có thể dùng transaction trong một database để cập nhật trạng thái nội bộ và ghi outbox event cùng lúc.

### 15.2. Distributed transaction

Một số hệ thống hỗ trợ distributed transaction hoặc two-phase commit. Cơ chế này có thể giữ tính nguyên tử nhưng tăng coupling, latency và yêu cầu hỗ trợ từ mọi participant.

### 15.3. Saga

Saga chia quy trình thành nhiều local transaction. Mỗi bước có thể có compensation để xử lý khi bước sau thất bại.

Ví dụ:
1. Giữ hàng.
2. Authorize payment.
3. Tạo shipment.
4. Commit order.

Nếu bước tạo shipment thất bại, workflow có thể void payment và release inventory theo policy.

### 15.4. Compensation không phải rollback hoàn hảo

Một email đã gửi không thể thu hồi. Một khoản tiền đã capture có thể cần refund thay vì xóa transaction. Compensation là hành động nghiệp vụ mới và có thể thất bại.

### 15.5. Thứ tự compensation

Có thể chạy bù theo thứ tự ngược với các bước đã commit hoặc theo dependency graph. Không nên giả định mọi compensation đều có thể chạy song song.

### 15.6. Manual recovery

Nếu compensation thất bại, lưu trạng thái cần can thiệp và cung cấp thao tác vận hành có audit. Không đánh dấu Saga thành công chỉ vì đã gửi yêu cầu compensation.

## 16. Outbox, Inbox và message delivery

Message broker có thể giao message nhiều lần hoặc consumer có thể crash trong lúc xử lý.

### 16.1. Transactional outbox

Ứng dụng ghi business state và event vào cùng một database transaction. Một publisher riêng đọc outbox rồi gửi event tới broker.

Điều này tránh tình huống database commit thành công nhưng event không được publish vì process crash ở giữa.

### 16.2. Inbox và deduplication

Consumer lưu message ID đã xử lý. Khi nhận message trùng, consumer có thể bỏ qua hoặc trả lại kết quả trước đó theo semantics.

### 16.3. Acknowledgement

Chỉ acknowledge message sau khi xử lý và commit theo quy tắc đã định. Ack quá sớm có thể làm mất message; ack quá muộn có thể tạo redelivery.

### 16.4. Poison message

Message luôn gây lỗi có thể bị retry vô hạn. Sau ngưỡng nhất định, chuyển nó sang dead-letter queue cùng error metadata để điều tra và replay sau khi sửa mapping.

### 16.5. Ordering

Nếu các event phải được xử lý theo thứ tự, cần partition key hoặc sequence number. Retry và redelivery có thể làm thứ tự thay đổi nếu không có cơ chế phù hợp.

## 17. Ánh xạ lỗi sang luồng DSL

DSL nên cho phép chọn nhánh theo error code, category hoặc trạng thái retryable.

~~~text
integration "get_customer" {
    call customerApi.get(customerId)
    timeout = 3 seconds

    onError {
        INTEGRATION_TIMEOUT -> retryOrRoute("customer_lookup_retry")

        AUTHENTICATION_FAILED -> refreshToken then retryOnce

        RESOURCE_NOT_FOUND -> return NotFound

        RATE_LIMITED -> wait retryAfter then retry

        otherwise -> fail with IntegrationFailure
    }
}
~~~

### 17.1. Match theo error code

Match theo code ổn định và rõ ràng. Không match theo message text vì message có thể thay đổi.

### 17.2. Match theo category

Category hữu ích khi muốn policy chung cho nhiều connector, ví dụ mọi lỗi TRANSIENT đều được đưa qua retry policy mặc định.

### 17.3. Thứ tự handler

Nếu handler có thể match cả category lẫn code cụ thể, DSL cần quy định thứ tự ưu tiên. Thường handler cụ thể hơn được xét trước, sau đó mới đến handler tổng quát.

### 17.4. Catch và rethrow

Handler có thể xử lý lỗi, chuyển đổi lỗi hoặc rethrow. Cần giữ cause chain để không mất nguyên nhân gốc.

### 17.5. Error scope

Một lỗi có thể được xử lý ở operation cụ thể, integration block, workflow step, toàn workflow hoặc global runtime policy. Policy cục bộ nên override policy chung theo quy tắc rõ ràng.

### 17.6. Error handler không được che lỗi ngoài ý muốn

Một handler otherwise có thể ghi log và chuyển sang fallback, nhưng nếu mọi lỗi đều bị biến thành thành công giả, hệ thống sẽ khó phát hiện dữ liệu sai. Cần phân biệt recovered error và suppressed error.

## 18. Ví dụ DSL cho retry và circuit breaker

Một integration block có thể khai báo nhiều policy:

~~~text
integration "shipping_quote" {
    connector = ShippingProvider

    request {
        orderId = order.id
        destination = order.shippingAddress
    }

    timeout {
        connect = 1 second
        total = 4 seconds
    }

    retry {
        maxAttempts = 3
        retryOn = [
            CONNECTION_UNAVAILABLE,
            INTEGRATION_TIMEOUT,
            TEMPORARY_UNAVAILABLE
        ]
        backoff = exponential
        initialDelay = 200 milliseconds
        maxDelay = 2 seconds
        jitter = full
    }

    circuitBreaker {
        failureRateThreshold = 50 percent
        minimumCalls = 20
        window = 30 seconds
        openDuration = 10 seconds
        halfOpenPermits = 2
    }

    onError {
        RATE_LIMITED -> wait retryAfter then retry
        BUSINESS_REJECTED -> route "manual_shipping_review"
        otherwise -> useCachedQuote(maxAge = 10 minutes)
    }
}
~~~

### 18.1. Phối hợp policy

Timeout xác định thời gian chờ của mỗi lần gọi. Retry quyết định có thử lại hay không. Circuit breaker quyết định có cho phép request đi qua dependency đang lỗi hay không. Fallback quyết định hành vi thay thế nếu không thể lấy kết quả chính.

### 18.2. Tránh retry khi circuit đã mở

Nếu circuit OPEN, request thường bị fail fast. Không nên tiếp tục retry liên tục bên trong cùng operation khi breaker đang chặn dependency.

### 18.3. Fallback phải ghi trạng thái

Nếu dùng cache, kết quả nên có metadata như source = CACHE và stale = true để workflow biết dữ liệu không đến từ provider trực tiếp.

## 19. Authentication refresh và lỗi credential

Credential có thể hết hạn hoặc bị thu hồi trong lúc workflow đang chạy.

### 19.1. Token refresh

Nếu access token hết hạn và có refresh token hợp lệ, connector có thể refresh rồi retry một lần. Cần tránh nhiều worker đồng thời refresh cùng một credential và ghi đè token mới.

### 19.2. Không retry vô hạn

Nếu refresh token bị thu hồi, retry không giúp ích. Workflow cần dừng, yêu cầu cấu hình lại credential hoặc chuyển sang quy trình xử lý phù hợp.

### 19.3. Secret rotation

Khi secret được rotate, connector nên hỗ trợ version hoặc key reference. Log không được ghi secret thô.

### 19.4. Permission change

Một token có thể hợp lệ nhưng quyền đã thay đổi. Đây là lỗi authorization, cần báo quyền thiếu thay vì retry.

## 20. Schema mismatch và lỗi dữ liệu

Integration contract có thể lệch với response thực tế.

Ví dụ DSL mong đợi:

~~~text
type PaymentResponse {
    paymentId: String required
    status: PaymentStatus required
    amount: Decimal required
}
~~~

Nhưng provider trả:

~~~json
{
  "id": 9001,
  "state": "AUTHORIZED",
  "amount": "550000"
}
~~~

Có thể cần adapter mapping:
- id thành paymentId.
- state thành status.
- amount string thành Decimal.

### 20.1. Missing required field

Nếu paymentId không có, adapter không nên tạo ID rỗng và tiếp tục như thành công. Cần báo INVALID_RESPONSE hoặc SCHEMA_MISMATCH.

### 20.2. Unknown enum

Provider có thể thêm trạng thái mới. Cần quyết định:
- Chấp nhận unknown enum dưới dạng UNKNOWN.
- Giữ raw value để xử lý sau.
- Từ chối response nếu trạng thái ảnh hưởng quyết định an toàn.

### 20.3. Type coercion

Chuyển chuỗi thành số có thể hợp lệ nếu contract cho phép. Không nên ép kiểu âm thầm khi dữ liệu mơ hồ hoặc mất precision.

### 20.4. Version compatibility

Adapter có thể hỗ trợ nhiều version provider thông qua mapping riêng. Không nên để thay đổi của provider lan vào domain model nội bộ.

### 20.5. Quarantine dữ liệu lỗi

Message hoặc record không parse được có thể được đưa vào quarantine hoặc dead-letter storage để điều tra và replay sau khi sửa mapping.

## 21. Security và thông tin lỗi

Lỗi tích hợp có thể chứa dữ liệu nhạy cảm như URL nội bộ, request body, access token hoặc thông tin khách hàng.

### 21.1. Không log secret

Không ghi:
- Authorization header.
- Password.
- API key.
- Refresh token.
- Private key.
- Session cookie.

Nếu cần điều tra, ghi credential identifier hoặc version thay vì secret.

### 21.2. Redaction

Redaction loại bỏ hoặc che field nhạy cảm trước khi ghi log hoặc trả lỗi.

Ví dụ:

~~~json
{
  "customerId": "CUS-1042",
  "cardNumber": "************4242",
  "token": "[REDACTED]"
}
~~~

### 21.3. Error response công khai

API nên trả mã lỗi ổn định, thông điệp an toàn, correlation ID và hướng dẫn hành động phù hợp. Không trả stack trace, hostname nội bộ hoặc query chứa secret.

### 21.4. Tenant isolation

Không để error details của tenant này xuất hiện trong response hoặc log mà tenant khác có thể truy cập.

### 21.5. Replay và dữ liệu nhạy cảm

Khi lưu request để retry hoặc replay, cần mã hóa, giới hạn retention và kiểm soát quyền truy cập. Payload có thể chứa dữ liệu cá nhân hoặc thông tin thanh toán.

## 22. Observability: log, metric và trace

Khi một workflow thất bại ở hệ thống ngoài, cần trả lời được operation nào lỗi, request nào liên quan và trạng thái nghiệp vụ đã đến đâu.

### 22.1. Structured logging

Một log event nên có các trường:
- timestamp.
- workflowId.
- operationId.
- integrationName.
- externalSystem.
- attempt.
- errorCode.
- category.
- duration.
- correlationId.
- traceId.
- outcome.

### 22.2. Metrics

Các metric hữu ích:
- Request count theo dependency và operation.
- Error rate theo category.
- Timeout rate.
- Retry count.
- Circuit state.
- Request latency p50, p95, p99.
- Queue depth.
- In-flight requests.
- Fallback rate.
- Unknown outcome count.
- Compensation failure count.

### 22.3. Distributed tracing

Một trace có thể bao gồm workflow span, integration operation span, HTTP client span, provider span nếu có instrumentation, retry attempt span và compensation span.

Trace ID và correlation ID giúp nối sự kiện qua nhiều service.

### 22.4. External request ID

Nếu provider trả request ID, lưu nó cùng lỗi. Khi liên hệ nhà cung cấp, ID này giúp họ tra log phía server.

### 22.5. Audit

Với thao tác tài chính hoặc thay đổi dữ liệu quan trọng, audit cần ghi ai hoặc service nào khởi tạo, operation, resource, kết quả, thời điểm và rule version. Audit không nhất thiết chứa toàn bộ payload.

### 22.6. Alert

Alert nên dựa trên tỷ lệ lỗi, latency, queue backlog hoặc số workflow bị mắc kẹt. Không nên cảnh báo riêng từng lỗi transient nếu hệ thống tự phục hồi bình thường.

## 23. Dead-letter queue và quy trình xử lý lỗi thủ công

Một message hoặc operation có thể thất bại sau nhiều lần retry.

### 23.1. Dead-letter queue

Dead-letter queue lưu message không thể xử lý theo policy bình thường. Metadata nên bao gồm message ID, original destination, attempt count, error code, first/last failure time, correlation ID và payload reference an toàn.

### 23.2. Manual review

Một số lỗi nghiệp vụ cần con người quyết định, ví dụ thiếu chứng từ hoặc xung đột dữ liệu không thể tự giải quyết.

### 23.3. Replay

Replay đưa một message hoặc operation trở lại luồng xử lý. Cần xác định schema version, idempotency key, kết quả đã commit, khả năng replay sau khi policy thay đổi và quyền được phép replay.

### 23.4. Không replay mù

Nếu lỗi do dữ liệu sai hoặc thao tác đã thành công nhưng response bị mất, replay có thể làm hỏng trạng thái hoặc tạo tác dụng phụ trùng. Cần kiểm tra trạng thái trước khi replay.

## 24. Tích hợp đồng bộ và bất đồng bộ

Cách xử lý lỗi phụ thuộc vào kiểu giao tiếp.

### 24.1. Synchronous request-response

Client chờ response trong cùng call. Timeout và retry là policy phổ biến. Unknown outcome cần được giải quyết bằng idempotency hoặc status lookup.

### 24.2. Asynchronous message

Producer publish message và nhận acknowledgement từ broker. Consumer xử lý sau đó. Lỗi có thể dẫn đến redelivery, retry queue hoặc dead-letter queue.

### 24.3. Callback và webhook

Server ngoài gọi ngược vào endpoint của ứng dụng. Ứng dụng cần xác thực chữ ký, chống replay, deduplicate event và trả acknowledgement nhanh.

### 24.4. Polling

Client định kỳ hỏi trạng thái job. Cần backoff để không tạo tải quá lớn và xác định khi nào dừng polling.

### 24.5. Webhook retry

Provider có thể gửi lại webhook nếu không nhận 2xx. Consumer cần idempotent theo event ID vì cùng event có thể đến nhiều lần.

## 25. Workflow lỗi và compensation

Một DSL quy trình có thể mô tả lỗi ở từng bước và policy phục hồi.

~~~text
workflow "fulfill_order" {
    step reserveInventory {
        call inventory.reserve(order.items)
        onError:
            retry transient maxAttempts 3
    }

    step authorizePayment {
        call payment.authorize(order.total)
        onError:
            compensate reserveInventory
            fail with PaymentAuthorizationFailed
    }

    step createShipment {
        call shipping.create(order)
        onError:
            compensate authorizePayment
            compensate reserveInventory
            route "manual_fulfillment"
    }

    step confirmOrder {
        update order.status = "CONFIRMED"
    }
}
~~~

### 25.1. Step state

Mỗi step nên có trạng thái như PENDING, RUNNING, SUCCEEDED, FAILED, RETRYING, COMPENSATING, COMPENSATED hoặc NEEDS_ATTENTION.

### 25.2. Compensation registry

Runtime cần biết step nào đã thực hiện tác dụng phụ và compensation tương ứng. Không gọi compensation cho step chưa commit hoặc không có side effect.

### 25.3. Failure boundary

Có thể chia workflow thành các transaction boundary. Sau mỗi boundary, checkpoint trạng thái và quyết định cách phục hồi.

### 25.4. Manual override

Người vận hành có thể cần retry, skip, compensate hoặc mark resolved. Các thao tác này cần kiểm tra quyền và audit.

### 25.5. Trạng thái không chắc chắn

Nếu call payment timeout, không được tự đánh dấu payment FAILED. Có thể cần trạng thái UNKNOWN và bước query provider trước khi tiếp tục hoặc compensation.

## 26. Kiểm thử xử lý lỗi tích hợp

Kiểm thử không chỉ xác nhận đường thành công. Cần mô phỏng các lỗi có thể xảy ra ở ranh giới hệ thống.

### 26.1. Unit test cho error mapping

Cung cấp response hoặc exception mẫu từ provider và xác nhận adapter tạo đúng IntegrationError:
- HTTP 429 thành RATE_LIMITED.
- HTTP 401 thành AUTHENTICATION_FAILED.
- Timeout thành INTEGRATION_TIMEOUT.
- JSON sai thành INVALID_RESPONSE.

### 26.2. Retry test

Dùng fake clock và fake client để kiểm tra số lần thử, delay tăng đúng, jitter trong khoảng cho phép, Retry-After được tôn trọng, không retry lỗi permanent và dừng khi hết deadline.

### 26.3. Idempotency test

Gửi cùng operation nhiều lần với cùng key. Xác nhận không tạo tác dụng phụ trùng. Gửi cùng key với payload khác và xác nhận conflict.

### 26.4. Circuit breaker test

Kiểm tra CLOSED, OPEN và HALF_OPEN. Xác nhận request bị chặn khi OPEN, probe có giới hạn và circuit đóng lại sau khi service phục hồi.

### 26.5. Bulkhead test

Làm một dependency chậm và xác nhận nó không chiếm toàn bộ worker hoặc connection của dependency khác.

### 26.6. Partial failure test

Cho một số item thành công và một số item lỗi. Xác nhận response giữ đúng kết quả từng item và retry chỉ phần cần thiết.

### 26.7. Contract test

Kiểm tra schema request/response, error code, status mapping và version compatibility với provider giả lập hoặc môi trường contract.

### 26.8. Fault injection

Cố ý tạo network disconnect, latency tăng, DNS failure, invalid JSON, HTTP 500/503/429, credential hết hạn, duplicate message, broker unavailable và database deadlock.

### 26.9. Crash recovery test

Dừng process ở các thời điểm:
- Trước khi gửi request.
- Sau khi gửi nhưng trước response.
- Sau khi provider thành công nhưng trước khi lưu kết quả.
- Sau khi commit outbox.
- Trong lúc compensation.

Xác nhận resume và deduplication không tạo tác dụng phụ trùng.

### 26.10. Chaos testing

Trong môi trường được kiểm soát, tạo lỗi ngẫu nhiên hoặc gián đoạn dependency để đánh giá khả năng phục hồi ở cấp workflow. Cần có giới hạn blast radius và tiêu chí dừng thử nghiệm.

## 27. Những lỗi thiết kế thường gặp

### 27.1. Retry mọi lỗi

Retry validation, authentication hoặc business rejection chỉ tạo tải thêm và không sửa nguyên nhân. Phân loại lỗi trước khi retry.

### 27.2. Timeout quá dài hoặc không có timeout

Request treo giữ tài nguyên và làm workflow không thể tiến triển. Dùng timeout theo operation và deadline tổng.

### 27.3. Retry không có backoff

Retry ngay lập tức có thể khuếch đại sự cố. Dùng exponential backoff, jitter và retry budget.

### 27.4. Retry thao tác không idempotent

Một thao tác tạo dữ liệu hoặc thanh toán có thể bị thực hiện hai lần. Dùng idempotency key, status lookup hoặc deduplication.

### 27.5. Không phân biệt timeout với thất bại chắc chắn

Timeout có thể tạo unknown outcome. Trước khi tạo request mới, cần kiểm tra trạng thái thao tác cũ.

### 27.6. Circuit breaker dùng sai ngưỡng

Nếu tính cả lỗi validation từ client, breaker có thể mở dù provider khỏe. Chỉ tính các lỗi phản ánh tình trạng dependency.

### 27.7. Fallback che giấu dữ liệu stale

Dùng cache mà không đánh dấu dữ liệu cũ khiến downstream tin rằng dữ liệu mới. Gắn metadata và giới hạn tuổi dữ liệu.

### 27.8. Nuốt lỗi trong adapter

Adapter trả object rỗng khi parse thất bại khiến workflow tưởng operation thành công. Hãy phát IntegrationError rõ ràng.

### 27.9. Log toàn bộ payload

Payload có thể chứa secret hoặc dữ liệu cá nhân. Redact trước khi log và giới hạn retention.

### 27.10. Compensation không được kiểm soát

Compensation có thể thất bại hoặc tạo side effect mới. Cần trạng thái, retry, audit và manual recovery.

## 28. Quy trình thiết kế xử lý lỗi tích hợp

Một quy trình thực tế:

1. Liệt kê dependency, operation và protocol.
2. Xác định error taxonomy cho từng connector.
3. Định nghĩa mô hình IntegrationError thống nhất.
4. Ánh xạ lỗi ngoài sang error code và category nội bộ.
5. Chọn timeout, deadline và deadline propagation.
6. Xác định lỗi retryable và yêu cầu idempotency.
7. Thiết kế backoff, jitter, retry budget và Retry-After.
8. Cấu hình circuit breaker, bulkhead, rate limit và queue limit.
9. Quy định fallback, partial success và manual review.
10. Thiết kế transaction boundary, outbox/inbox và compensation.
11. Bảo vệ secret, payload và tenant context.
12. Bổ sung structured log, metrics, trace và audit.
13. Viết unit, contract, fault injection và recovery tests.
14. Theo dõi production metrics và điều chỉnh policy theo dữ liệu thực tế.

## 29. Ví dụ tổng hợp: tích hợp thanh toán và kho

Một workflow xác nhận đơn hàng cần giữ hàng và authorize thanh toán.

~~~text
workflow "confirm_order" {
    let operationKey = "order:" + order.id + ":confirm"

    step reserveInventory {
        call inventory.reserve(order.items) {
            idempotencyKey = operationKey + ":inventory"
            timeout = 4 seconds
        }

        retry {
            maxAttempts = 3
            retryOn = [TIMEOUT, TEMPORARY_UNAVAILABLE]
            backoff = exponential
            jitter = full
        }

        onError {
            OUT_OF_STOCK -> fail OrderRejected
            otherwise -> route "inventory_attention"
        }
    }

    step authorizePayment {
        call payment.authorize(order.total) {
            idempotencyKey = operationKey + ":payment"
            timeout = 6 seconds
        }

        retry {
            maxAttempts = 2
            retryOn = [CONNECTION_UNAVAILABLE, TEMPORARY_UNAVAILABLE]
        }

        onError {
            PAYMENT_DECLINED -> compensate reserveInventory
                               then fail PaymentRejected

            INTEGRATION_TIMEOUT -> queryPaymentStatus(operationKey + ":payment")
                                   then resolveUnknownOutcome

            otherwise -> compensate reserveInventory
                         then route "payment_attention"
        }
    }

    step confirm {
        update order.status = "CONFIRMED"
    }
}
~~~

### 29.1. Lỗi tồn kho

Nếu provider trả OUT_OF_STOCK, đây là business rejection. Không retry tự động theo cùng input. Workflow từ chối đơn hoặc đề nghị người dùng thay đổi số lượng.

### 29.2. Lỗi tạm thời của kho

Nếu kết nối bị reset trước khi có kết quả, retry có thể được thực hiện với cùng idempotency key. Nếu provider đã giữ hàng, key giúp tránh giữ trùng khi provider hỗ trợ.

### 29.3. Thanh toán bị từ chối

Nếu payment provider trả PAYMENT_DECLINED rõ ràng, workflow chạy compensation để giải phóng hàng đã giữ.

### 29.4. Thanh toán timeout

Nếu timeout xảy ra, trạng thái thanh toán có thể là UNKNOWN. Workflow truy vấn trạng thái theo idempotency key hoặc external reference trước khi retry hay compensation.

### 29.5. Dịch vụ thanh toán mất kết nối kéo dài

Circuit breaker có thể mở, workflow fail fast hoặc chuyển sang payment_attention. Các request mới không tiếp tục tạo tải lên dependency đang lỗi.

### 29.6. Quan sát

Log và trace liên kết order ID, workflow ID, operation key, attempt, external request ID và error code. Không ghi token hoặc dữ liệu thanh toán nhạy cảm.

## 30. Bài tập tự kiểm tra

### Bài 1: Phân loại lỗi

Một API trả 429, 401, 409 và 503. Hãy phân loại từng lỗi và giải thích lỗi nào có thể retry, điều kiện cần có là gì.

### Bài 2: Unknown outcome

Client gọi API tạo thanh toán nhưng timeout. Hãy mô tả vì sao không thể kết luận giao dịch thất bại và thiết kế cách tra cứu hoặc retry an toàn.

### Bài 3: Error model

Thiết kế IntegrationError có error code, category, retryable, retryAfter, correlationId, externalRequestId và cause. Giải thích trường nào phục vụ logic, trường nào phục vụ vận hành.

### Bài 4: Retry policy

Một service trả 503 không ổn định. Hãy chọn max attempts, exponential backoff, jitter, max delay và deadline. Giải thích cách tránh retry storm.

### Bài 5: Circuit breaker

Mô tả trạng thái CLOSED, OPEN và HALF_OPEN. Đưa ra một ngưỡng minh họa và giải thích vì sao không nên tính lỗi validation vào failure rate.

### Bài 6: Bulkhead

Một ứng dụng gọi dịch vụ thanh toán và dịch vụ báo cáo. Hãy thiết kế worker pool, connection pool và queue limit để lỗi báo cáo không làm ảnh hưởng thanh toán.

### Bài 7: Partial failure

Một batch 100 phần tử có 95 phần tử thành công và 5 phần tử lỗi. Hãy thiết kế response, retry strategy và idempotency key theo item.

### Bài 8: Saga và compensation

Workflow giữ hàng, authorize payment rồi tạo shipment. Nếu shipment thất bại, hãy xác định compensation cần chạy và cách xử lý nếu compensation cũng lỗi.

### Bài 9: Message delivery

Một consumer xử lý message rồi crash trước khi acknowledgement. Hãy giải thích redelivery, inbox deduplication và cách tránh xử lý tác dụng phụ hai lần.

### Bài 10: Observability và testing

Lập kế hoạch log, metric, trace và fault injection cho một connector. Nêu cách kiểm tra timeout, invalid response, credential expiry, circuit breaker và crash recovery.

## Kết luận

Xử lý lỗi tích hợp là phần thiết yếu của DSL kết nối các ứng dụng và dịch vụ độc lập. Một thiết kế đáng tin cậy bắt đầu bằng error taxonomy và mô hình lỗi thống nhất, sau đó ánh xạ lỗi protocol thành lỗi domain có ý nghĩa. Timeout, retry, backoff, jitter, idempotency, circuit breaker, bulkhead và backpressure phối hợp để bảo vệ hệ thống khi dependency chậm hoặc không sẵn sàng. Với thao tác có tác dụng phụ, cần phân biệt timeout với kết quả thất bại chắc chắn, đồng thời dùng deduplication, outbox/inbox hoặc Saga và compensation để phục hồi. Structured logging, metrics, distributed tracing, audit và fault injection giúp giải thích sự cố và kiểm chứng rằng workflow vẫn giữ được trạng thái nhất quán khi một phần tích hợp gặp lỗi.
