# Mô phỏng timeout sau khi cổng thanh toán đã nhận giao dịch

## 1. Mục tiêu

Trong hệ thống Microservices, một thao tác thanh toán thường đi qua nhiều thành phần: client, API Gateway, Order Service, Payment Service, ngân hàng hoặc cổng thanh toán bên ngoài, rồi quay lại hệ thống qua response đồng bộ hoặc webhook bất đồng bộ.

Một tình huống rất dễ xảy ra là Payment Service gửi lệnh thanh toán và gateway đã nhận, thậm chí đã chuyển tiếp yêu cầu tới ngân hàng, nhưng response bị mất trên đường về. Payment Service hết thời gian chờ và chỉ nhìn thấy timeout. Nó không thể kết luận rằng giao dịch thất bại.

Đây là **kết quả không xác định (ambiguous outcome)**: lệnh có thể chưa được xử lý, đang xử lý, đã thành công hoặc đã thất bại; phía gọi chưa có đủ bằng chứng để phân biệt.

Nếu service lập tức gửi một lệnh thanh toán mới với định danh khác, khách hàng có thể bị trừ tiền hai lần. Nếu service đánh dấu thất bại dù gateway đã thu tiền, đơn hàng và payment ledger sẽ lệch nhau. Nếu service giữ request chờ vô hạn, tài nguyên bị chiếm dụng và người dùng không biết trạng thái.

Bài học này mô phỏng timeout xảy ra **sau khi gateway đã nhận giao dịch**, rồi thiết kế cách xử lý an toàn. Trọng tâm là:

- Phân biệt timeout trước khi gửi, trong lúc gửi và sau khi gateway đã nhận.
- Hiểu vì sao timeout không đồng nghĩa giao dịch thất bại.
- Thiết kế trạng thái thanh toán có trạng thái UNKNOWN/PENDING và chuyển trạng thái hợp lệ.
- Dùng idempotency key ổn định cho cùng một ý định thanh toán.
- Tra cứu trạng thái giao dịch bằng merchant reference hoặc provider transaction ID.
- Xử lý webhook, polling, duplicate notification và sự kiện đến sai thứ tự.
- Tách trạng thái Order khỏi trạng thái Payment và xác định nguồn sự thật.
- Dùng transactional outbox, saga và reconciliation để xử lý workflow phân tán.
- Xây mô phỏng gateway có khả năng nhận lệnh rồi làm mất response.
- Kiểm thử retry, crash, duplicate request, delayed callback và recovery.
- Theo dõi rủi ro tài chính bằng business metrics, audit trail và cảnh báo.

Ví dụ sử dụng Java/Spring Boot, REST API và một cổng thanh toán giả lập. Các trạng thái, endpoint và đoạn code là mô hình học tập; hợp đồng thật phải tuân theo tài liệu của nhà cung cấp thanh toán, chính sách ngân hàng, quy định bảo mật và quy trình tài chính của tổ chức.

## 2. Kịch bản thực tế

Một khách hàng bấm nút Thanh toán cho đơn hàng ORD-1001 trị giá 250.000 VND.

Luồng ban đầu:

~~~text
Customer
   |
   v
Checkout API
   |
   v
Order Service
   |
   v
Payment Service
   |
   | POST /charges
   v
Payment Gateway
   |
   v
Bank / Card Network
~~~

Tại thời điểm 10:00:00, Payment Service gửi yêu cầu tạo charge. Gateway nhận request, ghi nhận merchant reference và chuyển giao dịch tới hệ thống thanh toán. Nhưng response HTTP bị mất do network interruption. Payment Service chờ 3 giây rồi timeout.

Điều mà Payment Service biết:

- Nó đã gửi request.
- Kết nối đã timeout.
- Nó không nhận được response cuối cùng.
- Nó chưa có bằng chứng gateway từ chối hoặc hoàn tất giao dịch.

Điều mà Payment Service **không thể suy ra**:

- Gateway chưa nhận request.
- Ngân hàng chưa xử lý.
- Khách hàng chưa bị trừ tiền.
- Giao dịch chắc chắn thất bại.

Timeline minh họa:

| Thời điểm | Sự kiện | Góc nhìn của Payment Service |
|---|---|---|
| 10:00:00.000 | Bắt đầu gửi charge request | Đang gửi |
| 10:00:00.120 | Gateway nhận request | Chưa biết |
| 10:00:00.250 | Gateway tạo provider transaction | Chưa biết |
| 10:00:00.600 | Ngân hàng chấp thuận | Chưa biết |
| 10:00:00.700 | Gateway chuẩn bị response | Chưa biết |
| 10:00:03.000 | Client timeout | Chỉ biết kết quả không xác định |
| 10:00:04.000 | Gateway gửi webhook | Có thể chưa nhận được |
| 10:00:05.000 | Payment Service tra cứu trạng thái | Có thể xác minh được |
| 10:00:06.000 | Payment Service cập nhật PAID | Khi đã có bằng chứng hợp lệ |

Đây là ví dụ về thứ tự sự kiện. Trong hệ thống thật, webhook có thể đến trước timeout, sau timeout, lặp lại nhiều lần hoặc không đến; response đồng bộ và webhook có thể cạnh tranh cập nhật cùng một payment.

## 3. Phân biệt timeout và thất bại nghiệp vụ

Timeout là một kết quả ở tầng giao tiếp: caller không nhận được phản hồi trong deadline đã đặt. Nó không mô tả chắc chắn trạng thái nghiệp vụ ở phía server.

Có thể chia thành các trường hợp:

| Tình huống | Điều caller biết | Rủi ro |
|---|---|---|
| Timeout trước khi request rời client | Có thể request chưa được gửi | Thấp hơn, nhưng cần biết client/network semantics |
| Connect timeout | Không thiết lập được kết nối tới peer | Thường chưa gửi application request, nhưng cần xác minh tầng mạng/proxy |
| Write timeout | Có thể một phần hoặc toàn bộ request đã được gửi | Kết quả không chắc chắn |
| Read timeout sau khi gửi | Peer có thể đã nhận và xử lý request | Có thể đã tạo giao dịch |
| Gateway trả 4xx validation | Gateway từ chối theo contract | Có thể kết luận lỗi request nếu response đáng tin cậy |
| Gateway trả 5xx | Có thể lỗi trước hoặc sau khi xử lý | Không tự động coi là chưa có side effect |
| Gateway trả 202 Accepted | Gateway đã nhận xử lý bất đồng bộ | Chưa có kết quả thanh toán cuối cùng |
| Gateway trả success cuối cùng | Có bằng chứng theo contract của provider | Vẫn cần lưu và đối soát |

Không phải mọi HTTP 5xx đều mang cùng semantics. Một gateway có thể commit giao dịch rồi lỗi khi tạo response, hoặc một reverse proxy có thể trả 502 dù backend đã hoàn tất. Phải đọc contract và khả năng truy vấn trạng thái của provider.

### 3.1. Timeout là trạng thái quan sát, không phải trạng thái thanh toán

Có thể mô hình hóa riêng:

- **Transport result:** SUCCESS_RESPONSE, DEFINITE_REJECTION, TIMEOUT, CONNECTION_ERROR.
- **Payment business state:** CREATED, SUBMITTED, PENDING, AUTHORIZED, CAPTURED, FAILED, CANCELLED, REFUNDED, UNKNOWN/REQUIRES_RECONCILIATION.

Một transport timeout không nên tự động map thành payment FAILED. Payment có thể được đặt vào PENDING/UNKNOWN để tiếp tục xác minh.

## 4. Trạng thái thanh toán và state machine

Một state machine rõ ràng giúp ngăn các chuyển trạng thái sai.

Ví dụ:

~~~text
CREATED
   |
   v
SUBMITTED
   |
   +------> PENDING / UNKNOWN
   |             |
   |             +------> AUTHORIZED
   |             |
   |             +------> CAPTURED
   |             |
   |             +------> FAILED
   |
   +------> AUTHORIZED
   |
   +------> CAPTURED
   |
   +------> FAILED

AUTHORIZED
   |
   +------> CAPTURED
   |
   +------> VOIDED

CAPTURED
   |
   +------> PARTIALLY_REFUNDED
   |
   +------> REFUNDED
~~~

Các trạng thái có ý nghĩa:

- CREATED: payment intent đã được tạo nội bộ nhưng chưa gửi provider.
- SUBMITTED: đã bắt đầu gửi lệnh tới provider.
- PENDING: provider xác nhận đang xử lý hoặc chưa có kết quả cuối.
- UNKNOWN: caller mất khả năng xác định kết quả; cần query/reconciliation.
- AUTHORIZED: tiền được cấp phép/giữ hạn mức nhưng chưa nhất thiết đã capture.
- CAPTURED/PAID: giao dịch đã được capture/thu tiền theo semantics provider.
- FAILED: provider xác nhận giao dịch thất bại cuối cùng theo contract.
- VOIDED/CANCELLED: authorization hoặc giao dịch được hủy theo quy trình.
- PARTIALLY_REFUNDED: một phần số tiền đã được hoàn.
- REFUNDED: đã hoàn theo điều kiện được định nghĩa.

Không gộp AUTHORIZED và CAPTURED nếu nghiệp vụ có hai bước. Với một số phương thức thanh toán, provider có trạng thái khác; mapping phải được xây theo tài liệu chính thức.

### 4.1. UNKNOWN không có nghĩa là trạng thái cuối

UNKNOWN mô tả sự thiếu chắc chắn ở phía hệ thống của merchant. Nó thường phải dẫn đến một quy trình xác minh:

1. Tra cứu provider bằng merchant reference hoặc provider transaction ID.
2. Nếu provider báo PENDING, giữ trạng thái và lên lịch kiểm tra lại theo policy.
3. Nếu provider báo success, xác minh amount, currency, merchant account và reference rồi cập nhật.
4. Nếu provider báo definitive failure, cập nhật FAILED.
5. Nếu provider không tìm thấy giao dịch, không lập tức gửi charge mới; cần xem semantics lookup, consistency delay và khả năng request đầu chưa được index.
6. Nếu hết thời gian xử lý mà vẫn không rõ, đưa vào reconciliation/manual review theo risk tier.

### 4.2. Không cho phép chuyển trạng thái tùy tiện

Ví dụ không hợp lệ:

~~~text
CAPTURED -> FAILED
REFUNDED -> CAPTURED
FAILED_FINAL -> AUTHORIZED
~~~

Một webhook đến trễ không được phép đưa trạng thái từ REFUNDED trở lại CAPTURED chỉ vì event timestamp cũ hơn. Cần state transition rules, provider sequence/version hoặc truy vấn trạng thái authoritative.

## 5. Thiết kế dữ liệu payment intent

Không nên dùng một boolean paid=true/false để mô tả toàn bộ lifecycle. Một record payment intent có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| payment_id | ID nội bộ duy nhất |
| order_id | Đơn hàng liên quan |
| merchant_reference | Reference ổn định gửi tới provider |
| idempotency_key | Khóa chống tạo giao dịch trùng |
| provider | Tên gateway/provider |
| provider_transaction_id | ID giao dịch provider trả về nếu đã biết |
| amount_minor | Số tiền ở đơn vị nhỏ nhất theo currency |
| currency | Mã tiền tệ |
| status | Trạng thái nghiệp vụ hiện tại |
| attempt_count | Số lần gửi/kiểm tra theo semantics |
| last_transport_result | Kết quả giao tiếp gần nhất |
| submitted_at | Thời điểm gửi |
| last_checked_at | Lần cuối truy vấn trạng thái |
| next_reconcile_at | Thời điểm dự kiến kiểm tra lại |
| provider_status | Trạng thái thô theo provider |
| version | Version optimistic locking |
| created_at / updated_at | Mốc thời gian nội bộ |

Cần lưu attempt riêng nếu muốn giữ lịch sử nhiều lần giao tiếp:

~~~text
payment_attempts
  attempt_id
  payment_id
  idempotency_key
  request_hash
  submitted_at
  transport_result
  http_status
  provider_transaction_id
  response_received_at
  error_class
  correlation_id
~~~

Không ghi PAN, CVV, raw authorization headers, access token hoặc dữ liệu nhạy cảm của thẻ vào bảng này. Lưu tokenized payment method reference theo contract và PCI/security policy.

### 5.1. Amount và currency

Không dùng floating-point cho tiền. Lưu amount theo minor units hoặc decimal representation có scale được định nghĩa rõ. Currency có số chữ số thập phân khác nhau; không mặc định mọi currency đều có hai chữ số.

Ví dụ 250.000 VND có thể biểu diễn amount_minor=250000 nếu quy ước VND không dùng fractional minor unit trong ứng dụng. Quy tắc phải được chuẩn hóa theo currency.

## 6. Idempotency key: cùng một ý định, một giao dịch logic

**Idempotency** cho phép cùng một thao tác được gửi lại nhiều lần nhưng không tạo thêm side effect ngoài ý muốn.

Ví dụ merchant gửi:

~~~http
POST /charges
Idempotency-Key: pay-ord-1001-v1
Content-Type: application/json

{
  "merchantReference": "ORD-1001-PAY-1",
  "amount": 250000,
  "currency": "VND"
}
~~~

Nếu request đầu đã được provider nhận nhưng response bị mất, merchant retry với **cùng key và cùng payload semantics**. Provider có thể trả lại kết quả của lần xử lý đầu thay vì tạo charge thứ hai, nếu contract idempotency của họ hỗ trợ và key còn trong retention window.

### 6.1. Quy tắc sử dụng key

- Sinh key trước khi gửi lệnh đầu tiên.
- Lưu key bền vững cùng payment intent trước khi gọi gateway.
- Dùng lại cùng key cho retry của cùng một ý định.
- Không tạo key mới chỉ vì timeout.
- Ràng buộc key với merchant/account, operation và payload fingerprint theo contract.
- Nếu cùng key nhưng amount/currency/order khác, từ chối và điều tra.
- Xác định retention period của provider.
- Không tái sử dụng key cho một lần thanh toán mới sau khi intent cũ đã kết thúc.
- Không dùng order_id đơn thuần nếu một order có thể có nhiều payment attempts hợp lệ.

Một order có thể có lần thanh toán đầu thất bại cuối cùng, rồi khách hàng chủ động thử phương thức khác. Đó là ý định mới và có thể cần key mới, liên kết với payment intent mới, sau khi trạng thái attempt trước được xác định.

### 6.2. Merchant-side idempotency

Không chỉ dựa vào gateway. Payment Service nên có unique constraint hoặc cơ chế lock để ngăn hai request đồng thời tạo hai payment intent cho cùng một ý định nghiệp vụ.

Ví dụ constraint khái niệm:

~~~sql
CREATE UNIQUE INDEX uq_payment_merchant_reference
ON payments (merchant_account_id, merchant_reference);
~~~

Có thể thêm unique key cho idempotency scope. Chọn uniqueness theo contract nghiệp vụ: một order có thể cho phép nhiều lần thanh toán, nhưng không cho phép hai charge active cùng cho một attempt.

### 6.3. Payload fingerprint

Nếu key đã tồn tại mà client gửi payload khác, không trả kết quả cũ một cách mù quáng. Tính fingerprint trên các trường nghiệp vụ quan trọng như merchant, order, amount, currency, operation và payment method token reference; nếu khác thì trả conflict theo API contract.

Không hash raw secret/token rồi ghi ra logs. Fingerprint cần tránh lộ dữ liệu nhạy cảm và có versioned canonicalization.

## 7. Quy trình xử lý khi timeout sau khi gửi

Một luồng an toàn:

~~~text
1. Client gửi CreatePayment với client idempotency key
                 |
                 v
2. Payment Service tạo Payment Intent = CREATED
                 |
                 v
3. Lưu merchant reference + provider idempotency key
                 |
                 v
4. Đổi trạng thái thành SUBMITTED và gửi gateway
                 |
                 v
5. Read timeout sau khi gateway có thể đã nhận
                 |
                 v
6. Lưu transport result = TIMEOUT
   Payment state = UNKNOWN/PENDING
                 |
                 v
7. Trả response có payment_id và status=PENDING
                 |
                 v
8. Background reconciler / webhook / status query
                 |
        +--------+---------+
        |                  |
        v                  v
   Provider success   Provider final failure
        |                  |
        v                  v
   CAPTURED/PAID          FAILED
        |                  |
        +--------+---------+
                 |
                 v
          Cập nhật Order
~~~

Điểm quan trọng: không giữ HTTP request tới client mở vô thời hạn để đợi provider. Có thể trả 202 Accepted hoặc response trạng thái đang xử lý với payment resource URL. Việc dùng 202 hay 200 tùy API contract; điều cần giữ là biểu diễn rõ trạng thái chưa có kết quả cuối.

### 7.1. Response API cho client

Ví dụ:

~~~http
HTTP/1.1 202 Accepted
Location: /api/payments/pay-789
Retry-After: 2
Content-Type: application/json

{
  "paymentId": "pay-789",
  "orderId": "ORD-1001",
  "status": "PENDING",
  "message": "Payment result is being confirmed"
}
~~~

Client có thể polling GET payment status hoặc nhận cập nhật qua cơ chế phù hợp. Không nên hiển thị "Thanh toán thất bại" nếu backend chỉ biết timeout. UI có thể thông báo "Đang xác nhận kết quả thanh toán" và ngăn người dùng tạo một payment intent khác ngoài ý muốn.

### 7.2. Không để client tự quyết định retry một charge mới

Nếu client mất response của Payment Service, client cũng có thể gửi lại request tạo payment. Merchant API phải nhận diện cùng client idempotency key và trả cùng payment intent. Không dựa vào UI disable button làm cơ chế chống duplicate.

## 8. Query trạng thái giao dịch với provider

Nếu provider có endpoint truy vấn, sử dụng merchant reference hoặc provider transaction ID:

~~~http
GET /transactions/by-reference/ORD-1001-PAY-1
Authorization: Bearer ...
~~~

Kết quả minh họa:

~~~json
{
  "merchantReference": "ORD-1001-PAY-1",
  "transactionId": "gw-txn-8831",
  "status": "CAPTURED",
  "amount": 250000,
  "currency": "VND",
  "processedAt": "2026-11-12T03:00:00Z"
}
~~~

Đây là response giả lập. Provider thật có thể trả PENDING, AUTHORIZED, SETTLED, DECLINED hoặc trạng thái riêng.

### 8.1. Kiểm tra response trước khi cập nhật

Không chỉ nhìn status. Xác minh:

- Provider/account đúng.
- Merchant reference khớp payment intent.
- Provider transaction ID được liên kết đúng.
- Amount và currency khớp.
- Order/payment attempt đúng.
- Operation type đúng: authorize, capture, refund hay void.
- Status transition hợp lệ.
- Response có chữ ký/transport security theo contract.
- Dữ liệu không phải stale result đã bị một trạng thái mới hơn thay thế.

### 8.2. Lookup trả NOT_FOUND không có nghĩa chắc chắn request đầu chưa tới

Một số provider có độ trễ giữa lúc nhận request và lúc giao dịch xuất hiện trong query API. Nếu lookup quá sớm trả NOT_FOUND, không nên tạo charge mới ngay. Cần hiểu consistency delay, query semantics, retention và provider-specific idempotency.

Có thể tiếp tục query sau backoff hoặc chờ webhook trong một cửa sổ có giới hạn. Nếu provider bảo đảm NOT_FOUND có nghĩa chưa nhận giao dịch, hãy dựa trên contract đã xác minh.

## 9. Webhook: nhận kết quả bất đồng bộ

Gateway có thể gửi webhook khi giao dịch hoàn tất:

~~~http
POST /webhooks/payment-provider
Content-Type: application/json
X-Provider-Signature: ...
~~~

Payload minh họa:

~~~json
{
  "eventId": "evt-991",
  "eventType": "payment.captured",
  "merchantReference": "ORD-1001-PAY-1",
  "transactionId": "gw-txn-8831",
  "amount": 250000,
  "currency": "VND",
  "occurredAt": "2026-11-12T03:00:00Z"
}
~~~

Webhook có thể đến:

- Trước khi Payment Service nhận timeout.
- Sau khi client đã nhận PENDING.
- Nhiều lần do provider retry.
- Trễ hơn một event khác.
- Trong lúc service đang deploy/restart.
- Sau khi người dùng đã rời trang checkout.

### 9.1. Xác thực webhook

Trước khi tin payload:

1. Xác minh chữ ký theo đúng thuật toán và canonical payload của provider.
2. Kiểm tra timestamp/replay protection theo contract.
3. Xác định merchant account và environment.
4. Kiểm tra event ID và deduplication.
5. Xác minh amount, currency, merchant reference.
6. Không tin IP allowlist như lớp duy nhất nếu provider có signature verification.
7. Không ghi raw secret/signature/token vào log.
8. Lưu audit evidence theo chính sách.

Không cập nhật payment chỉ vì một request có JSON giống webhook. Endpoint công khai phải xử lý authentication, body size, replay và rate limiting.

### 9.2. Trả acknowledgement nhanh

Webhook handler nên:

- Xác minh chữ ký và cấu trúc.
- Lưu event hoặc enqueue xử lý bền vững.
- Trả acknowledgement theo contract trong thời gian ngắn.
- Xử lý domain state transition bất đồng bộ nếu cần.

Nếu handler làm nhiều việc đồng bộ rồi timeout, provider có thể gửi lại event. Duplicate webhook là hành vi bình thường cần được xử lý an toàn.

### 9.3. Deduplicate event

Lưu event ID với unique constraint theo provider/account:

~~~sql
CREATE TABLE payment_webhook_events (
    provider_account_id VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(200) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash VARCHAR(128) NOT NULL,
    processing_status VARCHAR(40) NOT NULL,
    PRIMARY KEY (provider_account_id, provider_event_id)
);
~~~

Schema chỉ minh họa. Không nhất thiết lưu toàn bộ payload nhạy cảm. Nếu cùng event ID xuất hiện lại, không áp dụng side effect lần nữa; có thể cập nhật received counter/last seen trong audit.

### 9.4. Webhook đến sai thứ tự

Ví dụ:

~~~text
10:01 payment.pending
10:02 payment.captured
10:03 payment.pending (duplicate hoặc delayed)
~~~

Không để event pending đến trễ làm payment quay lại PENDING. Dùng event sequence/version nếu provider cung cấp; nếu không, query trạng thái authoritative và áp dụng transition rules. Event timestamp không luôn đủ để quyết định vì clock và delivery ordering có thể khác nhau.

## 10. Payment state machine và Order state machine là hai thứ khác nhau

Order Service sở hữu vòng đời đơn hàng; Payment Service sở hữu trạng thái giao dịch thanh toán.

Ví dụ:

~~~text
Order:
CREATED -> PAYMENT_PENDING -> CONFIRMED
                      |
                      +----> PAYMENT_FAILED / CANCELLED

Payment:
CREATED -> SUBMITTED -> UNKNOWN -> CAPTURED
                             |
                             +----> FAILED
~~~

Order có thể ở PAYMENT_PENDING trong khi payment chưa rõ kết quả. Không nhất thiết phải hủy order ngay sau timeout.

Một command Capture thành công có thể làm Payment chuyển CAPTURED; Payment Service phát PaymentCaptured event; Order Service nhận event và chuyển Order sang CONFIRMED theo domain rules.

Không để Order Service tự sửa bảng payments, và Payment Service không tự ghi bảng orders của Order Service. Giao tiếp qua API/commands/events theo contract.

### 10.1. Không xác nhận đơn hàng quá sớm

Nếu đơn hàng chỉ được CONFIRMED sau khi thanh toán đã capture, thì trạng thái UNKNOWN phải giữ order ở trạng thái chờ. Nếu nghiệp vụ cho phép reserve inventory trước payment, cần TTL/compensation để giải phóng reservation khi payment thất bại cuối cùng.

### 10.2. Read model và UX

UI có thể hiển thị:

- Đang chờ xác nhận.
- Đã thanh toán.
- Thanh toán thất bại.
- Cần hỗ trợ/xác minh.

Không hiển thị trạng thái chắc chắn khi backend chỉ có kết quả không xác định. Cung cấp payment status endpoint và hướng dẫn người dùng không gửi thêm payment intent cho cùng đơn trong lúc đang xác minh.

## 11. Transactional outbox và phát Payment events

Sau khi Payment Service cập nhật trạng thái trong database, nó có thể cần phát event cho Order Service. Ghi DB và publish broker trực tiếp là dual-write: DB có thể commit nhưng broker publish fail, hoặc event được phát rồi transaction rollback.

Transactional outbox ghi payment state và event trong cùng database transaction:

~~~text
Payment Service transaction
   |
   +-- UPDATE payments SET status = CAPTURED
   +-- INSERT outbox_events(PaymentCaptured)
   |
  COMMIT
   |
   v
Outbox relay / CDC
   |
   v
Message broker
   |
   v
Order Service consumer
~~~

Ví dụ event:

~~~json
{
  "eventId": "payment-event-2001",
  "eventType": "PaymentCaptured",
  "eventVersion": 1,
  "paymentId": "pay-789",
  "orderId": "ORD-1001",
  "merchantReference": "ORD-1001-PAY-1",
  "amount": 250000,
  "currency": "VND",
  "occurredAt": "2026-11-12T03:00:00Z"
}
~~~

Event ID phải ổn định qua retry. Consumer Order Service cần idempotent; nếu event được gửi lại, order không được xác nhận hai lần hoặc tạo thêm side effect.

### 11.1. Transaction boundary

Webhook event được xác minh và payment state được cập nhật trong một transaction nội bộ. Outbox row được ghi cùng transaction. Relay phát sau commit.

Không giữ DB transaction mở trong lúc gọi provider hoặc đợi webhook. Network calls không nên nằm trong một transaction database dài vì sẽ giữ connection/locks và không tạo atomicity xuyên provider.

## 12. Saga và compensation

Payment workflow thường có nhiều service và side effects:

~~~text
Create Order
    |
    v
Reserve Inventory
    |
    v
Authorize Payment
    |
    v
Capture Payment
    |
    v
Confirm Order
~~~

Nếu một bước thất bại, không thể rollback toàn bộ hệ thống bằng một database transaction duy nhất. Saga biểu diễn chuỗi local transactions và compensation actions.

Ví dụ:

| Bước | Hành động | Compensation có thể có |
|---|---|---|
| 1 | Tạo order PENDING | Hủy order nếu chưa có side effect khác |
| 2 | Reserve inventory | Release reservation |
| 3 | Authorize payment | Void authorization |
| 4 | Capture payment | Refund theo chính sách; không phải rollback DB đơn giản |
| 5 | Confirm order | Có thể chuyển sang remediation nếu bước sau lỗi |

Refund không phải rollback hoàn hảo. Nó là một giao dịch tài chính mới, có phí, độ trễ và khả năng thất bại riêng.

### 12.1. Khi payment outcome UNKNOWN

Không chạy compensation như thể payment đã thất bại. Trước tiên phải xác minh trạng thái. Nếu release inventory quá sớm trong khi payment đã capture, hệ thống có thể thu tiền nhưng không còn hàng.

Một policy có thể giữ reservation trong một khoảng thời gian, kéo dài reservation khi status pending theo giới hạn, rồi chuyển sang reconciliation/manual review nếu quá hạn.

### 12.2. Orchestration và choreography

- Orchestration: một coordinator theo dõi bước và quyết định command tiếp theo.
- Choreography: các service phản ứng với domain events.

Với payment có rủi ro cao, orchestration thường giúp quan sát workflow state và timeout rõ hơn. Choreography có thể giảm coupling điều phối nhưng cần correlation, idempotency và cách nhìn toàn bộ saga. Chọn theo độ phức tạp và khả năng vận hành.

## 13. Retry an toàn và retry không an toàn

Không phải request nào cũng nên retry giống nhau.

| Operation | Retry khi timeout? | Điều kiện |
|---|---|---|
| GET payment status | Thường có | Timeout/backoff, giới hạn tải |
| POST charge | Chỉ khi cùng idempotency key và provider contract cho phép | Payload không đổi, key còn hiệu lực |
| POST authorize | Có điều kiện | Idempotency và trạng thái chưa rõ được xử lý |
| POST capture | Có điều kiện | Key ổn định, provider lookup và amount kiểm tra |
| POST refund | Rất thận trọng | Refund intent riêng, idempotency và reconciliation |
| Webhook acknowledgement | Provider sẽ retry theo contract | Handler dedupe event |
| Internal status update | Có thể | Optimistic locking và idempotent transition |

### 13.1. Retry budget và backoff

Không retry liên tục mỗi 100 ms. Một policy minh họa:

~~~text
Attempt 1: gửi charge với idempotency key K
Timeout: chuyển payment sang UNKNOWN
Sau 2 giây: query status
Sau 5 giây: query status
Sau 15 giây: query status
Sau 30 giây: query status
Sau đó: backoff tăng dần, có jitter và giới hạn
~~~

Đây là lịch ví dụ. Tần suất phải theo rate limits, provider SLA, payment risk và deadline nghiệp vụ. Tra cứu trạng thái thường an toàn hơn gửi lại charge, nhưng cũng phải có giới hạn để không làm quá tải provider.

### 13.2. Không tạo key mới khi retry

Lỗi nghiêm trọng:

~~~text
Timeout request #1 -> idempotency key A
Retry request #2   -> idempotency key B
~~~

Provider có thể coi đó là hai giao dịch khác nhau. Cách đúng khi cùng một payment intent:

~~~text
Request #1 -> key A
Retry #2   -> key A
Retry #3   -> key A
Status lookup -> merchant reference của intent A
~~~

Một payment intent mới chỉ được tạo sau khi intent cũ có trạng thái terminal phù hợp và nghiệp vụ cho phép thử lại.

## 14. Thiết kế API Payment Service

Một API minh họa:

~~~text
POST /api/payments
GET  /api/payments/{paymentId}
GET  /api/payments/by-reference/{merchantReference}
POST /api/payments/{paymentId}/capture
POST /api/payments/{paymentId}/void
POST /api/payments/{paymentId}/refunds
POST /webhooks/{provider}
~~~

### 14.1. Tạo payment intent

Request:

~~~json
{
  "orderId": "ORD-1001",
  "amount": 250000,
  "currency": "VND",
  "paymentMethodToken": "tok-example"
}
~~~

Header:

~~~http
Idempotency-Key: checkout-ORD-1001-attempt-1
~~~

Response ban đầu có thể là:

~~~json
{
  "paymentId": "pay-789",
  "orderId": "ORD-1001",
  "status": "SUBMITTED"
}
~~~

Nếu kết quả mơ hồ:

~~~json
{
  "paymentId": "pay-789",
  "orderId": "ORD-1001",
  "status": "PENDING",
  "reason": "PROVIDER_RESPONSE_TIMEOUT",
  "statusUrl": "/api/payments/pay-789"
}
~~~

Không trả provider stack trace hoặc raw gateway response nhạy cảm cho client.

### 14.2. Tra cứu payment

GET status nên trả:

- Payment ID và Order ID theo quyền truy cập.
- Status hiện tại.
- Amount/currency theo policy.
- Thời điểm cập nhật.
- Một mã reason có thể hiển thị.
- Retry-after hoặc thông tin polling nếu phù hợp.
- Không trả token, PAN hoặc raw provider credential.

Client cần authorization theo order/payment ownership. Không để đoán payment ID là có thể xem trạng thái giao dịch của người khác.

## 15. Java/Spring: mô hình domain tối giản

Ví dụ enum:

~~~java
public enum PaymentStatus {
    CREATED,
    SUBMITTED,
    PENDING,
    UNKNOWN,
    AUTHORIZED,
    CAPTURED,
    FAILED,
    VOIDED,
    PARTIALLY_REFUNDED,
    REFUNDED
}
~~~

Payment aggregate có thể chứa:

~~~java
public record PaymentSnapshot(
    UUID paymentId,
    String orderId,
    String merchantReference,
    String idempotencyKey,
    long amountMinor,
    String currency,
    PaymentStatus status,
    String providerTransactionId,
    long version
) {}
~~~

Đây là mô hình minh họa. Trong ứng dụng thực, cần entity/value object, currency type, versioning, audit và quy tắc chuyển trạng thái.

### 15.1. State transition method

~~~java
public Payment markUnknown(String reason) {
    if (status == PaymentStatus.CAPTURED
            || status == PaymentStatus.REFUNDED
            || status == PaymentStatus.FAILED) {
        return this;
    }

    return copyWith(
        PaymentStatus.UNKNOWN,
        reason,
        version + 1
    );
}
~~~

Code minh họa không đủ để xử lý mọi race. Cần xác định provider sequence/version, state transition matrix và optimistic locking. Một trạng thái terminal có thể cần adjustment/refund flow thay vì sửa ngược trạng thái.

### 15.2. Gửi request tới gateway

Pseudo-code:

~~~java
public PaymentSubmissionResult submit(PaymentIntent intent) {
    try {
        ProviderChargeResponse response = gatewayClient.charge(
            intent.merchantReference(),
            intent.idempotencyKey(),
            intent.amountMinor(),
            intent.currency()
        );

        return mapProviderResponse(response);
    } catch (SocketTimeoutException ex) {
        return PaymentSubmissionResult.unknown(
            "PROVIDER_RESPONSE_TIMEOUT"
        );
    } catch (ConnectException ex) {
        return classifyConnectFailure(ex);
    }
}
~~~

Không nên chỉ bắt một loại exception. HTTP client có thể phát nhiều exception cho connect, write, read, pool acquire và cancellation. Adapter cần phân loại theo semantics thực của thư viện và giữ evidence về request phase khi có thể.

### 15.3. Không giữ transaction database trong lúc gọi gateway

Một use case an toàn hơn thường chia thành:

1. Transaction A: tạo payment intent và idempotency record, commit.
2. Gửi provider request ngoài transaction.
3. Transaction B: lưu transport result/provider reference và outbox/event nếu có trạng thái chắc chắn.
4. Nếu timeout, lưu UNKNOWN/PENDING và lên lịch reconciliation.
5. Nếu process crash giữa các bước, background worker có thể tiếp tục từ trạng thái bền vững.

Cần thiết kế crash recovery cho trạng thái SUBMITTED mà process chết trước khi lưu kết quả. Không để payment intent mắc kẹt vô hạn.

## 16. Mô phỏng gateway nhận request rồi làm mất response

Đây là phần thực hành chính. Ta cần một gateway giả lập với behavior có thể điều khiển:

- Nhận request charge.
- Lưu giao dịch vào bộ nhớ hoặc database giả.
- Tạo transaction ID.
- Chuyển trạng thái thành CAPTURED hoặc PENDING.
- Không trả response HTTP về caller trong một kịch bản.
- Vẫn cho phép query transaction bằng merchant reference.
- Gửi webhook sau một khoảng trễ.
- Có thể phát webhook duplicate.
- Có thể trả response bình thường ở kịch bản khác.

Mô hình:

~~~text
Payment Service
     |
     | POST /mock/charges
     v
Mock Gateway
     |
     +-- persist transaction
     |
     +-- mark CAPTURED
     |
     +-- simulate lost response
     |
     +-- POST webhook later
     |
     +-- GET /mock/transactions/by-reference/{ref}
~~~

### 16.1. Các chế độ lỗi của mock gateway

| Mode | Hành vi | Mục đích |
|---|---|---|
| NORMAL | Nhận request, trả success | Baseline |
| REJECT | Trả definitive decline | Kiểm thử FAILED |
| ACCEPT_PENDING | Nhận request, trả pending | Async flow |
| ACCEPT_DROP_RESPONSE | Lưu charge rồi đóng/giữ kết nối để client timeout | Tình huống chính |
| DROP_BEFORE_ACCEPT | Không ghi nhận giao dịch, không trả response | Phân biệt failure trước acceptance |
| DELAY_RESPONSE | Xử lý xong nhưng trả response sau deadline | Timeout sau processing |
| DUPLICATE_WEBHOOK | Gửi cùng event nhiều lần | Deduplication |
| OUT_OF_ORDER_WEBHOOK | Gửi event sai thứ tự | State transition |
| QUERY_DELAY | Lookup ban đầu trả pending/not found theo contract mô phỏng | Eventual consistency |
| PROVIDER_5XX_AFTER_ACCEPT | Đã ghi giao dịch nhưng trả 5xx | Ambiguous HTTP error |

Trong chế độ ACCEPT_DROP_RESPONSE, mock gateway phải ghi transaction trước khi làm caller timeout. Nếu chỉ sleep trước khi ghi transaction, ta đang mô phỏng một tình huống khác.

### 16.2. Pseudocode mock gateway

~~~java
@PostMapping("/mock/charges")
public ResponseEntity<?> charge(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody MockChargeRequest request) {

    MockTransaction tx = store.findByKey(key)
        .orElseGet(() -> store.createCapturedTransaction(
            key,
            request.merchantReference(),
            request.amount(),
            request.currency()
        ));

    if (mode == Mode.ACCEPT_DROP_RESPONSE) {
        responseSimulator.dropConnectionAfterAccept();
        return ResponseEntity.status(599).build();
    }

    return ResponseEntity.ok(toResponse(tx));
}
~~~

Đây là pseudocode; HTTP status 599 chỉ minh họa một cách mô phỏng proxy error, không phải status chuẩn của gateway. Trong integration test, có thể dùng mock server, fault-injection proxy hoặc server đóng socket sau khi persist để mô phỏng chính xác việc response bị mất.

### 16.3. Query endpoint

~~~http
GET /mock/transactions/by-reference/ORD-1001-PAY-1
~~~

Nếu gateway đã nhận, endpoint trả lại cùng transaction ID và trạng thái. Payment Service đối chiếu reference, amount và currency trước khi cập nhật payment.

### 16.4. Không dùng sleep làm mô hình duy nhất

Sleep cố định có thể mô phỏng response chậm, nhưng không mô phỏng đầy đủ việc connection bị reset sau khi server commit. Hãy phân biệt:

- Server xử lý chậm nhưng response cuối cùng vẫn tới.
- Server commit rồi đóng socket.
- Proxy timeout nhưng upstream tiếp tục xử lý.
- Request không tới server.
- Server nhận nhưng chưa commit.

Fault injection nên đặt ở đúng boundary để bài tập phản ánh đúng failure mode.

## 17. Một test case end-to-end

Scenario:

- Order ORD-1001 được tạo.
- Payment intent pay-789 có merchant reference ORD-1001-PAY-1.
- Mock gateway chạy mode ACCEPT_DROP_RESPONSE.
- Gateway lưu charge CAPTURED rồi đóng kết nối.
- Payment Service timeout sau 3 giây.
- Payment state chuyển UNKNOWN/PENDING.
- Order vẫn PAYMENT_PENDING.
- Reconciler query gateway bằng merchant reference.
- Gateway trả CAPTURED, transaction ID gw-txn-8831.
- Payment Service xác minh amount/currency/reference.
- Payment chuyển CAPTURED và ghi outbox event.
- Order Service nhận PaymentCaptured và chuyển CONFIRMED.
- Webhook duplicate đến sau đó, không tạo side effect lần hai.

Expected result:

| Thành phần | Kết quả mong đợi |
|---|---|
| Mock gateway | Chỉ một charge cho idempotency key |
| Payment Service | Một payment intent, trạng thái cuối CAPTURED |
| Order Service | Order CONFIRMED một lần |
| Outbox | Một logical PaymentCaptured event |
| Consumer | Duplicate event được deduplicate |
| UI | Không hiển thị thất bại khi kết quả chưa rõ |
| Reconciliation | Không có mismatch amount/currency/reference |
| Audit | Lưu được timeout và bằng chứng query/webhook |

## 18. Kiểm thử bằng curl hoặc HTTP client

Tạo payment intent:

~~~bash
curl -i -X POST http://localhost:8080/api/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: checkout-ORD-1001-attempt-1" \
  -d '{
    "orderId": "ORD-1001",
    "amount": 250000,
    "currency": "VND",
    "paymentMethodToken": "tok-test-001"
  }'
~~~

Kiểm tra trạng thái:

~~~bash
curl -i http://localhost:8080/api/payments/pay-789
~~~

Gửi lại cùng request với cùng key:

~~~bash
curl -i -X POST http://localhost:8080/api/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: checkout-ORD-1001-attempt-1" \
  -d '{
    "orderId": "ORD-1001",
    "amount": 250000,
    "currency": "VND",
    "paymentMethodToken": "tok-test-001"
  }'
~~~

Kết quả mong đợi là cùng payment intent, không tạo thêm charge. ID trong ví dụ chỉ minh họa; endpoint và payload phải khớp ứng dụng thực hành.

## 19. Test case cần có

| Test | Kịch bản | Assertion |
|---|---|---|
| T01 | Gateway success response | Payment CAPTURED, Order chuyển đúng |
| T02 | Gateway decline rõ ràng | Payment FAILED, không retry charge |
| T03 | Timeout trước acceptance | Reconcile xác định không có giao dịch theo contract |
| T04 | Gateway accept rồi drop response | Payment UNKNOWN/PENDING, không tạo charge mới |
| T05 | Retry cùng idempotency key | Một provider transaction |
| T06 | Retry bằng key mới khi intent cũ UNKNOWN | Bị chặn hoặc yêu cầu xác minh |
| T07 | Lookup trả PENDING | Payment tiếp tục chờ |
| T08 | Lookup trả CAPTURED | Payment chuyển CAPTURED sau validation |
| T09 | Webhook success tới trước query | State cập nhật idempotent |
| T10 | Webhook duplicate | Không nhân đôi side effect |
| T11 | Webhook đến sai thứ tự | Không rollback state terminal |
| T12 | Webhook signature sai | Từ chối, không đổi payment |
| T13 | Amount/currency mismatch | Quarantine/alert, không mark paid |
| T14 | Payment Service crash sau provider accept | Recovery bằng idempotency/query |
| T15 | Broker outage khi ghi outbox | Payment state và outbox vẫn atomic |
| T16 | Consumer crash trước ack | Duplicate event được xử lý an toàn |
| T17 | Reconciler chạy hai lần đồng thời | Không tạo side effect trùng |
| T18 | Provider query rate limit | Backoff và alert đúng |
| T19 | Payment capture rồi refund | State history đúng, không ghi đè |
| T20 | Order hết reservation khi payment pending | Compensation theo policy, không mất dấu payment |

## 20. Reconciler: xử lý payment chưa rõ kết quả

Một background worker có thể quét những payment cần xác minh:

~~~sql
SELECT payment_id
FROM payments
WHERE status IN ('UNKNOWN', 'PENDING', 'SUBMITTED')
  AND next_reconcile_at <= now()
ORDER BY next_reconcile_at
LIMIT 100;
~~~

Đây là SQL minh họa; production cần index, locking/claim strategy và giới hạn concurrency. Nhiều worker không nên đồng thời query cùng một payment quá mức.

Một vòng xử lý:

1. Claim payment bằng optimistic locking hoặc row lease.
2. Đọc merchant reference/provider transaction ID.
3. Query provider status.
4. Xác minh account, amount, currency, operation và reference.
5. Áp dụng state transition nếu kết quả authoritative.
6. Lưu query attempt, timestamp và evidence.
7. Ghi outbox event cùng transaction khi business state đổi.
8. Tính next reconcile time nếu vẫn pending.
9. Đưa vào manual review khi quá SLA hoặc có mismatch.
10. Release lease và ghi metrics.

### 20.1. Không query provider quá dày

Nếu hàng nghìn payment cùng timeout, polling mỗi giây có thể làm provider quá tải. Dùng backoff, jitter, concurrency cap, circuit breaker và rate limit. Ưu tiên webhook nếu provider hỗ trợ đáng tin cậy, nhưng vẫn giữ reconciliation vì webhook có thể mất hoặc bị trễ.

### 20.2. Lease và concurrency

Có thể dùng SELECT FOR UPDATE SKIP LOCKED hoặc claim token/lease để phân chia payment giữa workers. Cần lease expiration để worker crash không giữ payment mãi. Update phải dùng version để tránh kết quả cũ ghi đè trạng thái mới do webhook.

## 21. Webhook và reconciler chạy đồng thời

Một race condition:

~~~text
Worker A: query provider -> thấy CAPTURED
Worker B: nhận webhook -> thấy CAPTURED
Worker A: update payment
Worker B: update payment
~~~

Cả hai có thể cùng cố phát PaymentCaptured. Cần state transition và event emission atomically:

- Đọc current state/version.
- Xác định transition có thực sự thay đổi state không.
- Update với optimistic lock.
- Chỉ tạo outbox event nếu transition thành công lần đầu.
- Unique key hoặc dedup logic bảo vệ logical event.
- Consumer downstream idempotent.

Không tạo event chỉ vì handler chạy; tạo event vì **một transition nghiệp vụ mới đã được commit**.

### 21.1. Compare-and-set

Ví dụ khái niệm:

~~~sql
UPDATE payments
SET status = 'CAPTURED',
    provider_transaction_id = :provider_txn,
    version = version + 1,
    updated_at = now()
WHERE payment_id = :payment_id
  AND status IN ('SUBMITTED', 'PENDING', 'UNKNOWN')
  AND version = :expected_version;
~~~

Nếu số dòng cập nhật bằng 0, một worker khác có thể đã thay đổi state; cần đọc lại và xử lý theo trạng thái mới. Outbox event phải được insert trong cùng transaction với update thành công.

## 22. Audit trail và bằng chứng tài chính

Một payment cần lịch sử có thể giải thích:

~~~text
10:00:00 Payment intent created
10:00:00 Idempotency key persisted
10:00:00 Charge submitted to provider
10:00:03 Read timeout
10:00:03 Status changed to UNKNOWN
10:00:05 Provider lookup returned CAPTURED
10:00:05 Amount/currency/reference verified
10:00:05 Payment state changed to CAPTURED
10:00:05 PaymentCaptured outbox committed
10:00:06 Order consumer processed event
~~~

Audit trail nên ghi:

- Actor/system component.
- Correlation ID và payment ID.
- Provider reference/transaction ID đã mask hoặc theo policy.
- Event/action type.
- Before/after state.
- Timestamp và source evidence.
- Decision reason.
- Idempotency key reference/hash phù hợp.
- Manual override/approver nếu có.

Không sửa lịch sử bằng cách ghi đè một trạng thái cũ. Nếu có điều chỉnh tài chính, tạo record/event adjustment riêng với lý do và quyền phê duyệt.

## 23. Reconciliation với báo cáo của provider

Ngoài query từng transaction, tổ chức thường cần đối soát theo batch/settlement report:

- Giao dịch merchant đã ghi CAPTURED.
- Giao dịch provider ghi thành công.
- Amount/currency/fee/settlement status.
- Refund/void/chargeback.
- Transaction chưa match.
- Duplicate hoặc missing records.
- Cutoff/timezone và settlement date.

Ba nhóm mismatch điển hình:

1. Merchant ghi PENDING/UNKNOWN nhưng provider CAPTURED.
2. Merchant ghi CAPTURED nhưng provider không có giao dịch hoặc đã reversed.
3. Cùng merchant reference nhưng amount/currency/transaction ID khác nhau.

Đối soát không nên tự động sửa mọi mismatch. Đưa vào queue điều tra, xác định nguồn authoritative, lưu evidence và dùng workflow điều chỉnh được audit. Với payment, dữ liệu ngân hàng/provider và ledger nội bộ cần được so khớp theo settlement semantics chứ không chỉ timestamp request.

## 24. UX và thông điệp cho khách hàng

Khi payment đang UNKNOWN/PENDING:

- Hiển thị rõ đang xác minh kết quả.
- Không thông báo thất bại khi chưa có bằng chứng.
- Không khuyến khích bấm thanh toán lại bằng một intent mới.
- Cung cấp mã tham chiếu hỗ trợ.
- Cho phép xem trạng thái đơn/thanh toán.
- Cập nhật khi webhook/reconciler xác nhận.
- Nếu quá thời gian kỳ vọng, hướng dẫn liên hệ hỗ trợ theo quy trình.
- Không hiển thị thông tin thẻ hoặc raw provider response.

Ví dụ:

~~~text
Chúng tôi đã nhận yêu cầu thanh toán và đang xác minh kết quả với cổng thanh toán.
Bạn chưa cần thực hiện lại giao dịch.
Mã tham chiếu: ORD-1001-PAY-1.
Vui lòng kiểm tra trạng thái đơn hàng sau ít phút.
~~~

Nội dung thật cần phù hợp chính sách hỗ trợ và thời gian xử lý của provider. Không hứa chắc giao dịch sẽ thành công hoặc hoàn tiền trong thời gian chưa được xác nhận.

## 25. Timeout, deadline và connection pool

Đặt timeout quá dài khiến request giữ connection/thread trong thời gian không cần thiết. Đặt quá ngắn có thể tạo nhiều kết quả UNKNOWN dù provider xử lý bình thường.

Cần phân biệt:

- Connection pool acquire timeout.
- DNS lookup timeout.
- TCP connect timeout.
- TLS handshake timeout.
- Request write timeout.
- Response/read timeout.
- Overall operation deadline.
- Provider processing SLA.
- Webhook delivery delay.
- Reconciliation SLA.

Ví dụ:

~~~text
Payment API request deadline: 4 seconds
Provider connect timeout:     500 ms
Provider response timeout:    2 seconds
Local persistence budget:     300 ms
Response serialization:       100 ms
Remaining margin:             1.1 seconds
~~~

Đây là budget minh họa. Cần đo latency distribution và provider SLA. Nếu provider xử lý bất đồng bộ, response có thể chỉ xác nhận acceptance; không cần giữ HTTP connection tới khi giao dịch capture xong.

### 25.1. Timeout không phải retry budget

Tăng timeout lên 30 giây không giải quyết ambiguous outcome. Có thể chỉ làm client chờ lâu hơn. Dù timeout 3 giây hay 30 giây, nếu connection mất sau khi provider commit thì caller vẫn không biết kết quả.

## 26. Circuit breaker và rate limiting

Nếu provider đang chậm, nhiều request cùng chờ có thể làm cạn connection pool. Circuit breaker giúp ngăn gửi thêm request mới khi failure rate vượt policy. Tuy nhiên:

- Không được coi circuit open là payment FAILED.
- Không tạo idempotency key mới khi breaker đóng/mở.
- Giữ payment intent ở trạng thái phù hợp và lên lịch xử lý.
- Query status có thể có quota riêng với charge requests.
- Circuit breaker cho charge và status query có thể cần tách.
- Khi provider hồi phục, không xả toàn bộ backlog cùng lúc.

Rate limit phải phân biệt create/charge, status lookup, capture và refund. Một provider có thể áp quota riêng cho từng endpoint.

## 27. Security và bảo vệ dữ liệu thanh toán

Môi trường mô phỏng không nên dùng thẻ thật hoặc credential production. Dùng provider sandbox/mock, token giả và dữ liệu test.

Các yêu cầu:

- Không lưu CVV hoặc full card data.
- Tokenize payment method theo provider.
- Giới hạn quyền service account.
- TLS và xác minh chứng thư.
- Xác minh chữ ký webhook.
- Secret manager và rotation.
- Không log raw request/response có dữ liệu nhạy cảm.
- Mask provider transaction identifiers khi cần.
- Audit mọi thao tác refund/void/manual override.
- Kiểm soát quyền xem payment status.
- Không để client tự truyền amount có quyền quyết định; lấy amount từ order đã được xác thực.
- Ràng buộc merchant reference và order ownership.

### 27.1. Amount phải do server xác định

Không tin amount do trình duyệt gửi lại khi thanh toán. Order Service hoặc một nguồn dữ liệu có thẩm quyền phải xác định tổng tiền, currency, discount, tax và shipping theo contract. Payment Service kiểm tra số tiền với payment intent/order snapshot.

Nếu gateway callback báo amount khác, không tự cập nhật theo callback. Quarantine và điều tra.

## 28. Observability cho payment timeout

Metrics cần phân biệt timeout, kết quả mơ hồ và kết quả cuối cùng.

| Metric | Ý nghĩa |
|---|---|
| payment_submission_total | Số lần gửi lệnh theo provider/result |
| payment_submission_timeout_total | Số transport timeout |
| payment_unknown_current | Số payment đang UNKNOWN |
| payment_pending_age_seconds | Tuổi của payment pending |
| payment_status_query_total | Số lần query provider |
| payment_status_query_latency | Latency query |
| payment_webhook_received_total | Số webhook nhận được |
| payment_webhook_duplicate_total | Số event duplicate |
| payment_webhook_invalid_signature_total | Webhook không xác thực |
| payment_reconciliation_mismatch_total | Mismatch trong đối soát |
| payment_recovery_duration_seconds | Thời gian từ UNKNOWN tới trạng thái xác định |
| payment_duplicate_charge_detected_total | Charge trùng được phát hiện |

Label nên có cardinality thấp như provider, operation, result class và environment. Không đưa payment_id, order_id, card token hoặc merchant reference vào metric label. Các ID cụ thể có thể dùng trong logs/traces có access control.

### 28.1. Dashboard

Một dashboard hữu ích hiển thị:

- Submission rate và timeout ratio.
- Số payment UNKNOWN/PENDING theo tuổi.
- Phân bố provider response codes.
- Webhook delivery delay.
- Status lookup lag và rate limit.
- Capture/decline rate.
- Duplicate charge signals.
- Reconciliation mismatches.
- Outbox lag và consumer lag.
- Payment-to-order consistency.
- Số manual reviews và backlog age.

### 28.2. Alert theo tuổi và tác động

Một alert "payment timeout > 0" có thể quá nhạy. Nên phân loại:

- Tăng đột biến timeout ratio.
- Payment UNKNOWN quá thời gian provider SLA.
- UNKNOWN backlog tăng liên tục.
- Webhook signature failures.
- Amount/currency mismatch.
- Duplicate charge suspected.
- Reconciliation batch chưa hoàn tất.
- Outbox event không được publish.
- Provider status query rate limit.

Một giao dịch mismatch tài chính có thể cần alert ngay dù số lượng nhỏ; timeout transient tự phục hồi trong vài giây có thể chỉ cần metric/tracing. Severity theo risk và customer impact.

## 29. Incident response khi không xác định được kết quả

Khi nhiều payment bị UNKNOWN:

1. Xác nhận provider nào và operation nào bị ảnh hưởng.
2. Dừng rollout/config change có liên quan nếu cần.
3. Giữ nguyên idempotency keys và merchant references.
4. Không gửi charge mới bằng key mới cho cùng intent.
5. Kiểm tra provider status page và API health.
6. Xem số lượng payment UNKNOWN theo thời gian/amount.
7. Query status với concurrency/rate limit phù hợp.
8. Đối chiếu webhook logs, signatures và event IDs.
9. Bảo đảm Order không được xác nhận khi payment chưa đủ bằng chứng.
10. Kiểm tra inventory reservations và TTL.
11. Mở reconciliation/manual review cho giao dịch quá hạn hoặc mismatch.
12. Cập nhật khách hàng qua kênh đã quy định.
13. Khi provider phục hồi, xử lý backlog có kiểm soát.
14. Reconcile với settlement report.
15. Ghi timeline, impact và corrective actions.

Không dùng thao tác bulk "mark all unknown as failed" để giải phóng backlog. Đây là hành động có thể gây sai lệch tài chính.

## 30. Thiết kế lab với Docker Compose

Một môi trường học tập có thể gồm:

~~~text
payment-lab/
  order-service
  payment-service
  mock-gateway
  postgres
  rabbitmq
  optional-observability
~~~

Topology:

~~~text
Client
  |
  v
Order Service ---- Order DB
  |
  v
Payment Service ---- Payment DB
  |
  +----> Mock Gateway
  |          |
  |          +---- transaction store
  |          +---- status query API
  |          +---- webhook sender
  |
  +----> RabbitMQ / Outbox relay
                 |
                 v
             Order consumer
~~~

Mock gateway cần có endpoint điều khiển mode trong môi trường test, ví dụ:

~~~text
POST /admin/scenario
{
  "mode": "ACCEPT_DROP_RESPONSE",
  "webhookDelayMs": 5000,
  "duplicateWebhook": true
}
~~~

Admin endpoint chỉ được expose trong profile test/local và không được đưa vào production build public. Có thể dùng một mock server riêng thay vì tự viết gateway nếu công cụ hỗ trợ fault injection đủ chính xác.

### 30.1. Data store mock gateway

Mock gateway cần lưu:

- idempotency key.
- merchant reference.
- provider transaction ID.
- amount/currency.
- provider status.
- event IDs đã gửi.
- thời điểm accept/process/callback.
- mode của scenario.

Khi cùng idempotency key được gửi lại với payload tương đương, trả cùng logical transaction. Nếu payload khác, trả conflict để bài test phát hiện bug.

## 31. Ví dụ test với WireMock hoặc fault-injection proxy

Có thể dùng WireMock để mô phỏng response delay hoặc status code, nhưng delay response không hoàn toàn giống việc server đã commit rồi đóng socket. Một server giả lập có state hoặc fault-injection proxy ở giữa sẽ giúp tái hiện chính xác hơn.

Test sequence:

~~~text
Given:
  Mock Gateway mode = ACCEPT_DROP_RESPONSE
  Payment intent key = K1
  Merchant reference = R1

When:
  Payment Service POST /charges with K1
  Gateway persists transaction T1 as CAPTURED
  Gateway drops response
  Payment Service reaches read timeout

Then:
  Payment status = UNKNOWN/PENDING
  Gateway has exactly one transaction for K1
  No new idempotency key is generated
  Order remains PAYMENT_PENDING

When:
  Reconciler queries by R1
  Gateway returns T1/CAPTURED

Then:
  Payment status = CAPTURED
  One PaymentCaptured logical event is committed
  Order becomes CONFIRMED once
~~~

### 31.1. Kiểm tra duplicate

Gửi cùng webhook hai lần. Kết quả:

- Event ID chỉ được xử lý logic một lần.
- Payment state không thay đổi lần hai.
- Outbox không tạo event business mới lần hai.
- Order consumer không xác nhận lại hoặc gửi notification trùng.
- Audit vẫn có thể ghi nhận webhook duplicate đã nhận.

### 31.2. Kiểm tra crash recovery

Cho Payment Service crash sau khi gateway nhận charge nhưng trước khi lưu response. Khi restart:

- Payment intent vẫn tồn tại.
- Idempotency key vẫn bền vững.
- Worker tìm được intent SUBMITTED/UNKNOWN quá hạn.
- Query gateway bằng merchant reference.
- Cập nhật trạng thái và phát event theo transaction.
- Không gửi charge mới với key khác.

## 32. Các failure mode nâng cao

### 32.1. Gateway nhận request nhưng chưa commit

Caller timeout; query ngay trả PENDING hoặc NOT_FOUND. Cần chờ theo provider contract, không gửi charge mới chỉ vì lookup chưa thấy.

### 32.2. Gateway commit capture nhưng webhook bị mất

Reconciler và settlement report là cơ chế dự phòng. Webhook không phải nguồn duy nhất để biết kết quả.

### 32.3. Gateway gửi webhook trước response

Webhook chuyển payment CAPTURED, sau đó HTTP response cũ báo PENDING. State transition phải ngăn response cũ ghi đè kết quả mới. Dùng version/sequence hoặc query authoritative.

### 32.4. Payment Service crash sau commit nhưng trước publish

Transactional outbox bảo đảm event còn trong DB để relay phát lại. Consumer cần dedupe.

### 32.5. Client retry đồng thời

Hai request cùng idempotency key tới hai replica. Cần unique constraint/atomic claim để chỉ một payment intent và một logical provider operation được tạo.

### 32.6. Provider idempotency key hết hạn

Nếu provider chỉ giữ key trong một khoảng thời gian, retry sau thời hạn có thể tạo giao dịch mới. Trước khi gửi lại, phải query theo merchant reference hoặc dùng quy trình provider-specific. Không giả định idempotency là vĩnh viễn.

### 32.7. Query status cũng timeout

Không kết luận payment thất bại. Giữ UNKNOWN, backoff, giới hạn query và tăng tuổi backlog metric. Khi quá SLA, đưa vào reconciliation/manual review.

### 32.8. Provider báo CAPTURED nhưng amount sai

Không mark order paid theo amount khác. Quarantine, alert và xử lý theo quy trình tài chính.

### 32.9. Refund trong lúc capture chưa rõ

Không tạo refund mới nếu chưa xác định charge có tồn tại và trạng thái có thể refund. Truy vấn giao dịch, xác nhận capture, rồi tạo refund intent riêng có idempotency key riêng.

### 32.10. Hai provider callback mâu thuẫn

Lưu cả evidence, query provider authoritative và không chọn event đến sau theo timestamp một cách mù. Có thể cần manual review nếu trạng thái không thể giải thích.

## 33. Các quyết định thiết kế cần ghi lại

Một ADR cho payment timeout nên trả lời:

- Provider có idempotency contract không? Scope và retention bao lâu?
- Merchant reference được tạo và lưu thế nào?
- Endpoint query status có consistency delay không?
- Webhook có signature, event ID, sequence và retry policy gì?
- State mapping provider -> domain ra sao?
- Timeout nào khiến outcome UNKNOWN?
- Khi nào retry request, khi nào chỉ query?
- Polling schedule và rate limit?
- Khi nào chuyển manual review?
- Order và inventory xử lý PENDING thế nào?
- Ai là authoritative owner của payment?
- Outbox/event contract ra sao?
- Reconciliation report nào được dùng?
- Amount/currency validation thế nào?
- Audit và retention policy?
- Runbook và on-call ownership?
- Customer communication?
- Rollback/forward-fix khi provider behavior thay đổi?

Không nên để các quyết định quan trọng chỉ tồn tại trong code hoặc trong trí nhớ của người trực.

## 34. Bài tập tình huống

### Bài 1 — Gateway đã nhận, response mất

Gateway ghi charge thành công nhưng Payment Service read timeout sau 3 giây.

**Câu hỏi:** Có được đánh dấu FAILED không?

**Đáp án:** Không. Kết quả chưa xác định. Đặt UNKNOWN/PENDING, giữ merchant reference/idempotency key và truy vấn provider hoặc chờ webhook.

### Bài 2 — Retry với key mới

Request đầu dùng key K1, timeout. Client gửi lại cùng order nhưng tạo key K2.

**Câu hỏi:** Rủi ro?

**Đáp án:** Provider có thể tạo charge thứ hai vì K2 là operation mới. Merchant API phải giữ key ổn định cho cùng intent và chống duplicate ở phía mình.

### Bài 3 — Query NOT_FOUND

Ngay sau timeout, status API trả NOT_FOUND.

**Câu hỏi:** Có gửi charge lại với key mới không?

**Đáp án:** Không mặc định. Xác minh query consistency và contract provider. Có thể giao dịch chưa được index hoặc request đang xử lý. Tiếp tục xác minh theo policy.

### Bài 4 — Webhook duplicate

Provider gửi payment.captured ba lần với cùng event ID.

**Câu hỏi:** Hệ thống cần tạo bao nhiêu logical state transition và event?

**Đáp án:** Một transition từ trạng thái chưa capture sang CAPTURED và một logical PaymentCaptured event. Các delivery duplicate chỉ được ghi nhận/deduplicate.

### Bài 5 — Webhook sai chữ ký

Một request có payload đúng nhưng chữ ký sai.

**Câu hỏi:** Có cập nhật payment không?

**Đáp án:** Không. Reject/quarantine theo security policy, ghi metrics/audit an toàn và không tin payload.

### Bài 6 — Response cũ đến sau webhook

Webhook đã xác nhận CAPTURED; sau đó HTTP response cũ báo PENDING.

**Câu hỏi:** Trạng thái cuối nên là gì?

**Đáp án:** Không được downgrade CAPTURED về PENDING. State machine và provider sequence/query authoritative phải bảo vệ transition.

### Bài 7 — Hai replica xử lý cùng intent

Hai Payment Service replicas cùng nhận request retry với cùng idempotency key.

**Câu hỏi:** Chỉ dùng kiểm tra SELECT trước INSERT có đủ không?

**Đáp án:** Không, vì race condition. Cần unique constraint/atomic claim/transaction và xử lý duplicate key bằng cách đọc lại intent đã tồn tại.

### Bài 8 — Payment capture, Order consumer lỗi

Payment CAPTURED và outbox đã commit, nhưng Order Service đang down.

**Câu hỏi:** Có nên hoàn tiền ngay không?

**Đáp án:** Không tự động. Event được giữ/retry qua broker/outbox, Order Service phục hồi và xử lý idempotent. Chỉ compensation nếu business policy và timeout workflow yêu cầu sau khi đánh giá đầy đủ.

### Bài 9 — Reservation hết hạn

Inventory reservation hết TTL trong lúc payment UNKNOWN; sau đó gateway xác nhận CAPTURED.

**Câu hỏi:** Cần xử lý gì?

**Đáp án:** Workflow cần compensation/remediation: thử reserve lại nếu có hàng, xử lý fulfillment thay thế hoặc refund theo policy. Không giả định reservation và payment tự đồng bộ.

### Bài 10 — Provider idempotency retention hết hạn

Payment UNKNOWN đã tồn tại lâu hơn thời hạn provider giữ key.

**Câu hỏi:** Có thể retry charge bằng key cũ không?

**Đáp án:** Không giả định. Query bằng merchant reference, đối soát provider report và áp dụng manual review nếu cần. Retry có thể tạo giao dịch mới sau khi idempotency record hết hạn.

### Bài 11 — Amount mismatch

Merchant gửi 250.000 VND nhưng webhook báo 2.500.000 VND.

**Câu hỏi:** Có mark PAID không?

**Đáp án:** Không. Xác minh transaction, merchant account, currency/scale và provider evidence; quarantine và escalation.

### Bài 12 — Status lookup bị rate limit

Hàng nghìn payment UNKNOWN cùng query provider và nhận 429.

**Câu hỏi:** Cần điều chỉnh gì?

**Đáp án:** Backoff/jitter, concurrency cap, circuit breaker cho query, phân loại priority theo tuổi/risk và tiếp tục nhận webhook. Không tạo thêm charge requests.

## 35. Checklist production cho ambiguous payment outcome

### Trước khi gửi giao dịch

- [ ] Payment intent được lưu bền vững trước provider call.
- [ ] Merchant reference ổn định và unique theo nghiệp vụ.
- [ ] Idempotency key được sinh và lưu trước request đầu.
- [ ] Amount/currency lấy từ nguồn nghiệp vụ có thẩm quyền.
- [ ] Payment attempt và correlation ID được ghi.
- [ ] Provider/account và operation type được xác định.
- [ ] Timeout budget và retry policy được document.

### Khi timeout

- [ ] Phân biệt connect/write/read/overall timeout nếu có thể.
- [ ] Không map timeout thành definitive FAILED.
- [ ] Đặt UNKNOWN/PENDING và giữ nguyên idempotency key.
- [ ] Trả response trạng thái chưa xác định cho client.
- [ ] Không tự động tạo intent/key mới.
- [ ] Ghi audit evidence và metrics.
- [ ] Lên lịch query/webhook reconciliation.

### Khi nhận kết quả

- [ ] Webhook signature được xác minh.
- [ ] Event ID được deduplicate.
- [ ] Merchant reference, transaction ID, amount và currency khớp.
- [ ] State transition hợp lệ và chống stale event.
- [ ] DB state và outbox được commit atomically.
- [ ] Consumer downstream idempotent.
- [ ] Order/inventory workflow được cập nhật đúng.
- [ ] UI phản ánh đúng trạng thái cuối.

### Khi vận hành

- [ ] Có reconciler và retry schedule có backoff.
- [ ] Có rate limit/concurrency control cho provider.
- [ ] Có alert theo UNKNOWN age/backlog và mismatch.
- [ ] Có settlement reconciliation.
- [ ] Có manual review và quyền phê duyệt.
- [ ] Có runbook cho provider outage.
- [ ] Có cơ chế phục hồi sau process crash.
- [ ] Có audit trail bất biến theo chính sách.
- [ ] Không log dữ liệu thẻ hoặc secret.
- [ ] Đã kiểm thử duplicate, out-of-order, timeout và idempotency expiry.

## 36. Những sai lầm thường gặp

1. **Coi timeout là thất bại:** có thể bỏ sót giao dịch đã được capture.
2. **Retry với key mới:** tạo duplicate charge.
3. **Chỉ dựa vào HTTP status:** proxy 5xx không chứng minh provider chưa commit.
4. **Không lưu payment intent trước khi gọi gateway:** crash làm mất merchant reference và key.
5. **Không có status lookup:** hệ thống không thể tự xác minh kết quả mơ hồ.
6. **Chỉ dựa vào webhook:** callback có thể trễ, duplicate hoặc mất.
7. **Không verify webhook signature:** attacker có thể giả payment success.
8. **Không deduplicate webhook:** gửi PaymentCaptured nhiều lần.
9. **Cho event cũ ghi đè state mới:** payment bị downgrade sai.
10. **Order và Payment cùng ghi database:** phá vỡ ownership.
11. **Giữ transaction DB mở khi gọi provider:** giữ lock/connection lâu nhưng không tạo atomicity.
12. **Không có outbox:** DB commit nhưng event có thể mất.
13. **Tin exactly-once của broker:** side effects ngoài broker vẫn có thể lặp.
14. **Không xử lý provider idempotency expiry:** retry muộn có thể tạo charge mới.
15. **Query provider quá dày:** tạo thêm tải trong lúc provider đang sự cố.
16. **Không đối soát settlement:** mismatch tài chính tồn tại lâu.
17. **Đánh dấu order CONFIRMED khi payment UNKNOWN:** nghiệp vụ được coi là hoàn tất dù chưa có bằng chứng.
18. **Giải phóng inventory quá sớm:** payment có thể capture sau đó.
19. **Refund khi chưa biết charge có tồn tại:** có thể tạo workflow sai hoặc không thể thực hiện.
20. **Chỉ đo latency, không đo correctness:** hệ thống nhanh nhưng thu tiền sai vẫn là sự cố nghiêm trọng.

## 37. Ghi nhớ

Khi Payment Service timeout sau khi gửi request, nó chỉ biết rằng không nhận được response đúng hạn. Gateway có thể chưa nhận, đang xử lý, đã từ chối hoặc đã thu tiền. **Không có response không đồng nghĩa không có giao dịch.**

Cách xử lý an toàn bắt đầu bằng payment intent bền vững, merchant reference và idempotency key ổn định. Timeout tạo trạng thái UNKNOWN/PENDING, không tự động tạo một charge mới. Hệ thống dùng status lookup, webhook và reconciliation để tìm bằng chứng authoritative; mọi kết quả phải được xác minh về merchant, reference, amount, currency và operation.

Payment và Order có state machine/ownership riêng. Khi payment được xác nhận, transactional outbox giúp phát event bền vững; consumers phải idempotent. Saga/compensation xử lý các bước liên quan như inventory reservation, order confirmation và refund. Rollback hoặc retry cần xem xét cả side effects đã commit, không chỉ HTTP connection.

Mô phỏng gateway nhận charge rồi làm mất response là bài kiểm tra quan trọng cho distributed systems. Hãy kiểm tra duplicate requests, webhook lặp/sai thứ tự, process crash, provider outage, idempotency expiry và reconciliation backlog. Theo dõi số payment UNKNOWN, tuổi pending, webhook delay, mismatch và duplicate charge signals.

**Nguyên tắc cốt lõi: khi kết quả thanh toán không rõ, giữ nguyên một ý định thanh toán với cùng idempotency key, xác minh trạng thái bằng nguồn có thẩm quyền, và chỉ chuyển Order/Payment sang trạng thái cuối khi có bằng chứng nghiệp vụ hợp lệ.**