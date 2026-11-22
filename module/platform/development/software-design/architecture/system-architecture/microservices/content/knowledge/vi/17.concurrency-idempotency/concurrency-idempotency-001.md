# Phân biệt idempotency, chống trùng và bảo đảm chỉ xử lý một lần

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Đồng thời và lặp an toàn  
> **Mục tiêu:** Thiết kế hệ thống có thể chịu retry, redelivery, timeout, crash và xử lý đồng thời mà không thực hiện trùng tác dụng nghiệp vụ; phân biệt tính idempotent, deduplication, at-most-once, at-least-once và exactly-once theo phạm vi cam kết thực tế.

## 1. Vì sao ba khái niệm này dễ bị nhầm lẫn?

Một khách hàng nhấn nút thanh toán. Mobile gửi yêu cầu, payment provider thực hiện capture, nhưng response bị mất do timeout. Mobile thử lại. Song song, message PaymentCaptured được broker giao hai lần cho consumer tạo đơn giao hàng. Worker xử lý thành công nhưng crash trước khi xác nhận message. Những hiện tượng này không hiếm trong hệ thống phân tán.

Nếu không có cơ chế đúng, hệ thống có thể:

- Thu tiền khách hai lần vì mỗi retry biến thành một lệnh capture mới.
- Tạo hai shipment vì cùng một sự kiện được giao lại.
- Gửi ba email xác nhận vì có nhiều consumer attempt.
- Ghi một bản ghi thanh toán hai lần vào sổ phụ.
- Tạo một đơn hàng mới khi người dùng nhấn nút submit lại.
- Cập nhật số lượng tồn kho sai khi hai worker cùng thực hiện.
- Trả kết quả “thất bại” cho client dù thao tác thực đã thành công.
- Bỏ mất tác vụ vì consumer xác nhận message quá sớm.

Ba khái niệm thường được dùng để giải quyết những phần khác nhau:

1. **Idempotency (tính lặp an toàn):** cùng một thao tác logic lặp lại không làm thay đổi kết quả cuối thêm lần nữa ngoài lần đầu tiên, trong phạm vi đã định nghĩa.
2. **Deduplication (chống trùng/lọc bản sao):** nhận biết nhiều lần xuất hiện của cùng một request, command, event hoặc message để bỏ qua hoặc gộp các bản sao.
3. **Exactly-once (chỉ xử lý một lần):** cam kết một hành động hoặc một tác dụng chỉ được thực hiện đúng một lần **trong phạm vi và giả định cụ thể**; không thể suy từ tên tính năng của broker ra việc toàn hệ thống có đúng một tác dụng nghiệp vụ.

Điểm cần nhớ: **một message có thể được giao nhiều lần nhưng tác dụng nghiệp vụ vẫn chỉ xảy ra một lần**, nếu consumer có cơ chế thích hợp. Ngược lại, **một message chỉ giao một lần** cũng chưa bảo đảm nghiệp vụ hoàn tất, vì worker có thể crash trước khi ghi dữ liệu.

### Kết quả học tập

Sau bài này, người học có thể:

- Mô tả idempotency dưới góc nhìn toán học, API, command và tác dụng phụ.
- Phân biệt dedup bằng eventId, requestId và khóa nghiệp vụ với idempotent handler.
- Giải thích at-most-once, at-least-once và exactly-once theo delivery, processing và side effect.
- Thiết kế REST API với Idempotency-Key, request fingerprint, trạng thái in-flight và kết quả được lưu.
- Viết consumer chống trùng bằng unique constraint/inbox, atomic transaction và ack đúng thời điểm.
- Xử lý race giữa hai request giống nhau, timeout, commit thành công nhưng response thất lạc, và retry sau khi dữ liệu đã đổi.
- Hiểu giới hạn của transactional broker, producer deduplication, external side effects và distributed transactions.
- Chọn TTL, namespace khóa, mức nhất quán, observability và failure-injection test cho từng loại nghiệp vụ.

## 2. Bắt đầu từ câu hỏi: “Một lần” là một lần cái gì?

Không có một khái niệm “một lần” duy nhất. Trong một request xuyên nhiều lớp:

~~~text
User
  |
  | HTTP request — có thể gửi lại
  v
API Gateway / BFF
  |
  | command — có thể retry
  v
Ordering
  |
  | local database transaction — commit hoặc rollback
  |
  +--> outbox event — relay có thể publish lại
           |
           v
      Message Broker
           |
           | delivery attempt — có thể giao lại
           v
      Payments Consumer
           |
           | external HTTP call — response có thể thất lạc
           v
      Payment Provider
           |
           | capture tiền — tác dụng nghiệp vụ
           v
      Ledger / Settlement
~~~

Cần nêu đích danh đối tượng muốn bảo vệ:

- **Một yêu cầu API:** hai lần submit cùng một ý định tạo đơn có tạo hai order không?
- **Một command:** một yêu cầu ReserveInventory có được thực thi hơn một lần không?
- **Một event:** cùng một PaymentCaptured có bị consumer áp dụng hai lần không?
- **Một transaction DB:** một row/ledger entry được ghi trùng không?
- **Một external effect:** tiền bị thu hai lần, email gửi hai lần, shipment tạo hai lần không?
- **Một kết quả phản hồi:** client retry có nhận cùng một kết quả logic không?
- **Một workflow:** một saga có thể có nhiều attempts nhưng nên dẫn đến một kết quả cuối hợp lệ ra sao?

Khi nói “chúng tôi hỗ trợ exactly-once”, phải hỏi tiếp: **exactly-once ở layer nào, theo key nào, trong cửa sổ thời gian nào, qua những lỗi gì và dựa vào storage nào?**

### Bảng thuật ngữ

| Thuật ngữ | Trọng tâm | Không tự bảo đảm |
| --- | --- | --- |
| Idempotent operation | Lặp thao tác không nhân tác dụng theo định nghĩa | Message không bị giao trùng |
| Deduplication | Nhận diện và lọc bản sao theo identity | Mọi hành động khác nhau đều idempotent |
| At-most-once delivery | Một message không bị giao lại theo cam kết transport | Message chắc chắn được xử lý |
| At-least-once delivery | Có thể giao lại để tăng xác suất xử lý thành công | Tác dụng nghiệp vụ chỉ xảy ra một lần |
| Exactly-once processing | Một tác dụng được commit đúng một lần trong phạm vi được định nghĩa | Mọi side effect bên ngoài cùng đúng một lần |
| Atomic transaction | Nhiều thay đổi cùng commit/rollback trong một ranh giới transaction | Atomic xuyên mọi DB, broker và provider |
| Idempotency key | Nhận diện một ý định/request logic qua các attempts | Khóa luôn duy nhất nếu scope/TTL sai |
| Event ID | Nhận diện một sự kiện cụ thể qua redelivery | Hai sự kiện khác nhau nhưng có cùng business outcome |
| Business uniqueness | Bất biến nghiệp vụ như một payment intent không tạo hai capture | Không có request/reply trùng trên mạng |

## 3. Idempotency là gì?

Trong cách diễn đạt đơn giản của toán học, một phép biến đổi f là idempotent khi áp dụng hai lần cho cùng đối tượng cho kết quả như áp dụng một lần:

~~~text
f(f(state, operation), operation) = f(state, operation)
~~~

Ví dụ đặt một trạng thái thành CANCELLED, nếu transition được thiết kế thích hợp và không phát thêm tác dụng phụ khi đã CANCELLED, có thể idempotent. Ví dụ tăng số lượt tải bằng 1 mỗi lần xử lý không idempotent.

### 3.1. Ví dụ idempotent và không idempotent

| Thao tác | Tính chất | Ghi chú |
| --- | --- | --- |
| Set profile language = vi | Có thể idempotent | Cùng request được áp dụng lại không đổi giá trị cuối |
| Add 100 reward points | Thường không idempotent | Lặp lại sẽ cộng 200 điểm nếu không bảo vệ |
| Create order with stable request ID | Có thể được làm idempotent | Cùng key phải trả cùng order logic |
| Create order without request identity | Thường không | Retry có thể tạo hai order |
| SendWelcomeEmail | Không tự nhiên idempotent | Gửi lại tạo thêm email |
| Set reservation status RELEASED | Có thể idempotent | Chỉ khi không sinh thêm side effects ngoài ý muốn |
| Transfer 500.000 VND | Không tự nhiên idempotent | Phải ràng buộc vào transfer intent duy nhất |
| Acknowledge đã đọc notification | Có thể idempotent | Nhưng audit/counter phụ có thể khiến handler không còn idempotent |

Một thao tác nhìn đơn giản như set status vẫn có thể **không idempotent toàn bộ handler** nếu mỗi lần gọi tạo event mới, gửi email mới, cập nhật updatedAt và tính phí mới. Phải xác định tính lặp an toàn ở **tác dụng nghiệp vụ**, không chỉ so sánh một cột dữ liệu.

### 3.2. Idempotency theo trạng thái cuối và theo quan sát bên ngoài

Có hai mức cần phân biệt:

- **State idempotency:** trạng thái lưu trữ sau nhiều lần xử lý giống một lần xử lý.
- **Effect idempotency:** các hậu quả bên ngoài — charge, email, vận đơn, cấp quyền, ledger entry — cũng không bị nhân lên.

Ví dụ hai request cùng đặt status PAID có thể giữ DB state giống nhau, nhưng nếu mỗi request gửi email “Đã thanh toán” và phát lệnh tạo shipment mới, handler **không idempotent theo nghĩa nghiệp vụ**.

### 3.3. API idempotency mạnh hơn “PUT là idempotent”

HTTP định nghĩa một số method có semantics idempotent, như PUT và DELETE theo ý định áp dụng cùng request. Nhưng server vẫn có thể triển khai sai, và method idempotent không ngăn mọi tác dụng phụ thứ cấp. Ngược lại, một POST tạo thanh toán có thể được thiết kế idempotent bằng khóa request riêng.

Không nên dựa vào tên method để quyết định retry an toàn:

- GET phải không có side effect nghiệp vụ đáng kể, nhưng request có thể làm tăng metric.
- PUT tạo/cập nhật trạng thái cuối có thể idempotent nếu đúng contract.
- DELETE lặp lại có thể trả 204 rồi 404 nhưng resource vẫn vắng mặt; phải phân biệt response code với trạng thái cuối.
- POST thường không được giả định idempotent nếu server chưa có cơ chế tương ứng.

### 3.4. Tính idempotent theo cùng một ý định

Nếu client tạo hai lệnh chuyển tiền độc lập, cùng amount và account, đó có thể là **hai giao dịch hợp lệ**. Hệ thống không được bỏ lệnh thứ hai chỉ vì payload trông giống lệnh đầu. Idempotency áp dụng cho **cùng một business intent**, không phải mọi request “giống nhau”.

Ví dụ khách chủ động mua hai chiếc vé giống nhau trong hai phiên đặt vé khác nhau: hai purchase intents độc lập cần được xử lý. Nếu dùng hash payload đơn thuần làm khóa, có thể gộp nhầm hai đơn.

## 4. Deduplication là gì?

Deduplication nhận diện các lần xuất hiện được coi là cùng một thực thể logic rồi xử lý chúng theo chính sách đã định.

Ví dụ message eventId = evt-218 được gửi tới consumer ba lần. Consumer có thể lưu eventId đã xử lý để bỏ qua lần thứ hai và thứ ba.

~~~text
eventId=evt-218, attempt=1 --> process --> committed
eventId=evt-218, attempt=2 --> already processed --> skip
eventId=evt-218, attempt=3 --> already processed --> skip
~~~

Điểm quan trọng là **định nghĩa thế nào là cùng một message/command**. Dedup không thể chỉ dựa vào payload: hai OrderPlaced khác nhau có cùng amount, product và customer vẫn là hai sự kiện khác nhau. Ngược lại, một event có thể được serialize khác nhau giữa retries mà vẫn đại diện cùng một eventId.

### 4.1. Các khóa dùng để chống trùng

| Key | Khi dùng | Sai lầm thường gặp |
| --- | --- | --- |
| HTTP Idempotency-Key | Một ý định gửi từ client qua retry | Dùng lại khóa cho thao tác mới |
| requestId / commandId | Một command logic trong application | Tạo ID mới cho mỗi retry |
| eventId | Một event đã phát sinh | Consumer bỏ mọi event có cùng aggregateId |
| paymentIntentId | Cùng ý định thanh toán | Nhầm với payment attempt ID |
| providerTransactionId | Một giao dịch thật ở provider | Không có trước lần tạo đầu tiên |
| shipmentRequestId | Cùng ý định tạo vận đơn | Tạo mới sau timeout mơ hồ |
| workflowId + stepId | Một bước cụ thể trong saga | Dùng workflowId cho mọi bước khác nhau |
| consumerName + eventId | Chống trùng theo consumer độc lập | Một consumer khác bị chặn nhầm |
| aggregateId + version | Dedupe/update projection theo phiên bản | Bỏ qua các sự kiện độc lập cùng aggregate |

Chọn key theo **ranh giới sở hữu** và **đơn vị tác dụng phụ**. Một eventId ổn định qua redelivery chưa chắc đủ chống trùng khi **hai events khác nhau** cùng yêu cầu tạo một side effect lẽ ra chỉ được phép một lần.

### 4.2. Time-window dedup và durable dedup

Có broker cung cấp khả năng lọc duplicate trong một cửa sổ thời gian dựa trên message ID hoặc producer sequence. Điều này hữu ích nhưng:

- Có thể không bảo vệ retry xảy ra sau cửa sổ đó.
- Có thể không bảo vệ khi client tạo key mới.
- Có thể chỉ áp dụng tại một topic/queue hoặc producer session.
- Không tự bảo vệ database hay external side effect.
- Có thể không hoạt động nếu publisher thay đổi payload identity.

Khi nghiệp vụ đòi cam kết mạnh, consumer/domain cần lưu trạng thái chống trùng bền vững trong phạm vi retention của nghiệp vụ, không chỉ tin vào một cache TTL ngắn.

### 4.3. Dedup không giải quyết tất cả concurrency

Nếu hai request **khác ID** cùng cố giữ chiếc ghế cuối cùng, dedup theo ID không giúp gì. Đây là vấn đề đồng thời và bất biến: cần transaction, unique constraint, conditional update, compare-and-swap hoặc lock hợp lý.

Ngược lại, hai request cùng ID có thể được gửi **đồng thời**. Nếu chỉ kiểm tra “đã tồn tại chưa?” rồi mới ghi, cả hai có thể cùng thấy chưa tồn tại và chạy side effect. Dedup phải có điểm quyết định atomic.

## 5. “Exactly once” là một hợp đồng có phạm vi

Trong hệ thống phân tán, câu “chỉ xử lý một lần” có ít nhất ba cách hiểu:

1. **Exactly-once delivery:** transport cố gắng để bên nhận thấy mỗi message đúng một lần.
2. **Exactly-once processing trong một hạ tầng:** xử lý các input và output thuộc cùng một transactional scope đúng một lần ở trạng thái đã commit.
3. **Exactly-once business effect:** tác dụng như chuyển tiền, ghi ledger, tạo đơn, cấp quyền xuất hiện đúng một lần theo ý định nghiệp vụ, kể cả khi request/message có nhiều attempts.

Điểm 3 thường là thứ doanh nghiệp cần, nhưng nó không được suy ra từ điểm 1 hoặc 2.

### 5.1. At-most-once

~~~text
Broker --> Consumer: deliver
Consumer acknowledges/offset advances early
Consumer crashes before business commit
Result: có thể mất tác dụng, broker không giao lại
~~~

At-most-once hạn chế duplicate, nhưng **không bảo đảm hoàn tất**. Có thể phù hợp telemetry best-effort, sự kiện không quan trọng, hoặc trường hợp hệ thống chấp nhận mất dữ liệu; không phải mặc định cho thanh toán và đơn hàng.

### 5.2. At-least-once

~~~text
Broker --> Consumer: deliver attempt 1
Consumer COMMIT business change
Consumer crashes before ack
Broker --> Consumer: deliver attempt 2
Consumer must recognize already-applied effect
~~~

At-least-once tăng độ tin cậy giao nhận, nhưng có thể gây trùng. Kết hợp với idempotent business handler và durable dedup giúp đạt **effect-once trong ranh giới đã định nghĩa**, nếu các giả định về DB transaction, identity và recovery được đáp ứng.

### 5.3. Exactly-once within stream processing

Một số hệ thống stream hỗ trợ transactional producer, atomic offset/output commit hoặc cơ chế exactly-once processing. Ví dụ xử lý record từ stream A và ghi sang stream B trong cùng cơ chế transaction của hạ tầng có thể tránh output trùng khi restart.

Nhưng nếu consumer đồng thời:

- Gửi email bằng SMTP.
- Gọi payment provider để capture tiền.
- Ghi vào database bên ngoài không tham gia transaction.
- Gửi request tạo vận đơn tới hãng vận chuyển.

...thì transaction của broker **không tự mở rộng** sang các side effects này. Cần idempotency/external operation key, outbox/inbox, transaction/bù trừ hoặc reconciliation phù hợp.

### 5.4. Không đánh đồng “ack một lần” và “effect một lần”

Một consumer có thể xử lý message, ghi DB, rồi ack. Nếu broker mất ack, message lại được giao. Một consumer khác có thể xử lý message trùng trong một thời điểm nếu lease hết hạn. Hệ thống phải duy trì correctness **dù số attempts không biết trước**.

Thước đo an toàn không phải attempts == 1; mà là **số tác dụng nghiệp vụ được phép bằng một theo intent**, và tất cả lần thử thêm đều trả/đi tới kết quả tương đương.

## 6. Vòng đời request và failure windows

Giả sử POST /orders tạo đơn, server lưu vào DB rồi trả response.

| Thời điểm lỗi | Server đã làm gì? | Client biết gì? | Thiết kế cần |
| --- | --- | --- | --- |
| Trước khi request tới server | Không có tác dụng | Timeout/network error | Retry cùng key |
| Sau khi nhận, trước khi commit | Có thể chưa commit | Không chắc | Check status/retry cùng key |
| Sau DB commit, trước khi trả response | Order đã tạo | Chỉ thấy timeout | Đọc lại kết quả theo key |
| Sau response thành công | Order đã tạo và client thấy | Có xác nhận | Retry cùng key vẫn trả cùng order |
| Hai requests cùng key đến đồng thời | Hai attempts cạnh tranh | Không rõ cái nào thắng | Unique/atomic claim và result reuse |
| Retry cùng key nhưng payload thay đổi | Mơ hồ ý định | Có thể là bug client | Reject mismatch rõ ràng |
| Retry sau idempotency TTL | Dữ liệu key có thể hết | Hệ thống quên ý định cũ | Contract TTL + business uniqueness |
| DB commit rồi process crash khi broker publish | Có thể thiếu event | Client không biết downstream | Transactional outbox |
| Downstream committed rồi consumer crash trước ack | Message được giao lại | Broker nghĩ chưa xong | Inbox/idempotent effect |

Các “cửa sổ lỗi” này xuất hiện ngay cả khi hạ tầng khỏe mạnh hầu hết thời gian. Trong thiết kế, hãy vẽ rõ thứ tự nhận–ghi–phát–ack và hỏi: **crash sau mỗi bước thì còn một bản ghi nào chứng minh sự thật?**

## 7. Idempotency cho REST API: thiết kế end-to-end

Một hợp đồng API ví dụ:

~~~http
POST /v1/orders
Idempotency-Key: 4d5377ec-a881-43d2-a171-4e61fa450712
Content-Type: application/json
Authorization: Bearer <token>

{
  "cartId": "cart-742",
  "shippingAddressId": "addr-51"
}
~~~

Client tạo key một lần **cho một ý định tạo order**, lưu key trong quá trình retry, không tự tạo key khác mỗi khi timeout. Server gắn key với principal/tenant, endpoint/operation và fingerprint request theo chính sách.

### 7.1. Các trạng thái idempotency record

~~~text
                first request
NONE ----------------------------> PROCESSING
                                     |
                          +----------+----------+
                          |                     |
                       success               terminal error
                          |                     |
                          v                     v
                      COMPLETED               FAILED
                          |
                     same key retry
                          |
                          v
                  return stored result

PROCESSING quá hạn / worker crash:
          RECOVER / INSPECT / RECONCILE
~~~

Trạng thái FAILED cần định nghĩa: có lỗi validation trước khi bắt đầu xử lý, lỗi nghiệp vụ cuối cùng, hay lỗi hạ tầng chưa biết kết quả? Không nên cache vĩnh viễn mọi 500 như một kết quả cố định. Nếu nghiệp vụ có side effect mơ hồ, kết quả phải được tra cứu/reconcile thay vì tự thử với key mới.

### 7.2. Khóa gồm phạm vi, không chỉ chuỗi ngẫu nhiên

Một khóa an toàn có thể được xác định bởi tuple:

~~~text
(tenantId, principalId, operationName, idempotencyKey)
~~~

Tùy use case, scope có thể theo merchant account, application client hoặc resource. Mục tiêu:

- Hai khách khác nhau dùng cùng chuỗi key không đụng nhau.
- Một key cho CreateOrder không vô tình chặn RefundPayment.
- Một principal không thể đoán key để đọc response của người khác.
- Retry cùng ý định được nhận diện dù đi qua instance server khác.

Cần áp dụng authorization khi lookup record; không coi việc biết key là đủ quyền xem dữ liệu hoặc status.

### 7.3. Request fingerprint

Server nên bảo vệ trường hợp client tái sử dụng cùng key nhưng khác ý định:

~~~text
Request A:
  key = X, amount = 500000, currency = VND

Request B:
  key = X, amount = 800000, currency = VND

Response cho B: CONFLICT / IDEMPOTENCY_KEY_REUSED
~~~

Fingerprint có thể hash những trường có ngữ nghĩa ảnh hưởng kết quả sau chuẩn hóa (canonicalization). Không hash raw JSON một cách máy móc nếu khoảng trắng/thứ tự trường không quan trọng nhưng gây mismatch giả. Ngược lại, không loại bỏ nhầm amount, currency, beneficiary hoặc cart version khỏi fingerprint.

### 7.4. Response cho request trùng

Một lựa chọn thiết kế:

| Trường hợp | Phản hồi |
| --- | --- |
| First request thành công | 201 Created + orderId |
| Retry sau khi hoàn tất | 201 hoặc 200 theo contract, cùng orderId và kết quả logic |
| Retry khi request gốc đang xử lý | 202 Processing hoặc 409 In Progress, kèm status URL/retry hint |
| Same key, fingerprint khác | 409 Conflict + lỗi xác định |
| Operation thực đã tạo nhưng response mất | Truy vấn record và trả kết quả gốc |
| Record không xác minh được sau crash | PENDING_RECONCILIATION, không tạo effect mới |
| Key đã hết hạn | Áp dụng documented retention/business protection policy |

Không có một HTTP status duy nhất bắt buộc cho tất cả hệ thống. Quan trọng là **contract nhất quán**, client không thể hiểu nhầm in-progress thành failed, và server không thực hiện lại side effect.

### 7.5. Giới hạn thời gian lưu key

TTL của idempotency record phải phù hợp:

- Cửa sổ retry hợp lệ của client.
- Thời gian tối đa job/workflow có thể chạy.
- Độ trễ callback/provider có thể xuất hiện.
- Mức rủi ro của tác dụng nghiệp vụ.
- Nghĩa vụ kiểm toán và lưu trữ dữ liệu.

Một record 24 giờ có thể đủ cho loại API đơn giản nhưng không đủ cho một quy trình hoàn tiền kéo dài nhiều ngày. Ngược lại, lưu mọi payload request mãi mãi gây tốn dung lượng và rủi ro dữ liệu. Có thể giữ **business operation identity** và unique invariant lâu hơn TTL của response cache.

Không tuyên bố đúng một lần “mãi mãi” nếu khóa được dọn sau một thời hạn và không có ràng buộc nghiệp vụ khác.

## 8. Hai request cùng key đến đồng thời: kiểm tra rồi ghi là không đủ

### 8.1. Race condition điển hình

~~~text
Request A                         Request B
---------                         ---------
SELECT key=X -> absent           SELECT key=X -> absent
Create payment                   Create payment
INSERT idempotency record        INSERT idempotency record
                                 
=> Hai side effects có thể đã xảy ra trước khi phát hiện trùng
~~~

Việc chỉ dùng một ConcurrentHashMap cục bộ cũng không đủ khi service chạy nhiều instance hoặc restart, chưa kể side effect ngoài DB.

### 8.2. Unique constraint và atomic claim

Tạo bảng có khóa duy nhất theo scope của intent:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id        VARCHAR(64) NOT NULL,
    operation_name   VARCHAR(80) NOT NULL,
    idempotency_key  VARCHAR(160) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(24) NOT NULL,
    business_ref     VARCHAR(160),
    response_json    JSONB,
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Đây là schema minh họa theo phong cách PostgreSQL. Tên trường, index, kiểu dữ liệu và retention cần thích ứng. Khi cố insert cùng key, chỉ một transaction được phép thắng unique constraint. Request còn lại không tự thực thi nghiệp vụ; nó đọc record hiện có, xác thực hash/owner và chọn trả kết quả hoặc thông báo đang xử lý.

### 8.3. Cẩn thận với PROCESSING bị kẹt

Nếu server ghi PROCESSING rồi crash trước khi hoàn tất, record có thể tồn tại vô hạn. Thiết kế cần:

- Lease/expiresAt hoặc trạng thái cần phục hồi.
- Một recovery worker có quyền claim lại theo version.
- Checkpoint cho những side effects đã thực thi.
- Query trạng thái domain/provider trước khi retry command mơ hồ.
- Idempotent handler để worker mới có thể tiếp tục an toàn.
- Cơ chế cảnh báo và manual case nếu không xác minh được outcome.

Không đơn giản xóa record PROCESSING cũ rồi cho request mới chạy lại khi có external side effect chưa biết kết quả.

## 9. Transactional idempotency cho create order

Một mô hình hợp lý là **ghi idempotency record, business row và outbox** trong cùng DB transaction.

~~~text
BEGIN TRANSACTION
  claim stable idempotency key (unique)
  validate request fingerprint
  create order if not already created
  insert OrderCreated into outbox
  mark idempotency operation COMPLETED with orderId
COMMIT
~~~

Sau commit, dù process chết trước HTTP response, retry cùng key đọc lại orderId. Nếu transaction rollback, claim/business row/outbox cùng rollback và request có thể được xử lý lại theo quy tắc.

### 9.1. Phân biệt kiểm tra input với thực thi nghiệp vụ

Trước khi claim, có thể validate schema/auth. Nhưng khi một request tiến tới tạo side effect, phải có ranh giới atomic hoặc recovery path rõ.

Ví dụ:

~~~sql
BEGIN;

-- Atomic claim; chỉ một request cùng scope + key đi tiếp.
INSERT INTO idempotency_records (
    tenant_id, operation_name, idempotency_key,
    request_hash, state, created_at, updated_at
)
VALUES (
    :tenantId, 'CREATE_ORDER', :idempotencyKey,
    :requestHash, 'PROCESSING', now(), now()
)
ON CONFLICT DO NOTHING;

-- Nếu không insert được: đọc bản ghi hiện hữu và so fingerprint.
-- Chỉ khi claim thành công mới tạo order.
INSERT INTO orders(order_id, tenant_id, cart_id, status)
VALUES (:orderId, :tenantId, :cartId, 'ACCEPTED');

INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload)
VALUES (:eventId, :orderId, 'OrderCreated', :eventPayload);

UPDATE idempotency_records
SET state='COMPLETED',
    business_ref=:orderId,
    updated_at=now()
WHERE tenant_id=:tenantId
  AND operation_name='CREATE_ORDER'
  AND idempotency_key=:idempotencyKey;

COMMIT;
~~~

**Chú ý:** đây là pseudo-SQL thể hiện các bước, không phải một thủ tục copy chạy nguyên xi. Application phải kiểm tra kết quả INSERT claim và **không thực thi ba lệnh tiếp** khi claim không thành công; transaction isolation, unique key, quyền và retry khi deadlock cũng phải được thiết kế. Nếu logic domain làm việc với database khác hoặc provider ngoài, không thể gói toàn bộ thành một DB transaction như ví dụ này.

### 9.2. Business uniqueness độc lập với idempotency key

Ngay cả khi client tạo hai key khác nhau do bug, nghiệp vụ có thể vẫn cần unique invariant:

~~~sql
-- Ví dụ: một request đặt chỗ duy nhất cho cùng bookingIntentId.
CREATE UNIQUE INDEX uq_booking_intent
ON bookings(tenant_id, booking_intent_id);
~~~

Nếu use case hỗ trợ nhiều booking hợp lệ từ cùng một cart, không được dùng cartId làm unique key quá rộng. Phải có khái niệm ý định đặt chỗ rõ ràng.

## 10. Message broker: redelivery là hành vi cần chấp nhận

Trong at-least-once messaging, message có thể được giao lại vì:

- Worker chết khi đang xử lý.
- Visibility timeout/lease hết hạn.
- Consumer rebalance hoặc session mất kết nối.
- Ack tới broker bị mất.
- Producer publish lại vì không chắc lần trước thành công.
- Outbox relay crash sau khi publish nhưng trước checkpoint.
- Đội vận hành chủ động replay hoặc re-drive DLQ.
- Broker failover và cơ chế recovery.

Không nên sửa bằng cách “cấm broker giao trùng” nếu broker không có hợp đồng đó. Hệ thống consumer phải chịu được số lần nhận nhiều hơn một.

### 10.1. Mô hình đúng của message identity

~~~json
{
  "eventId": "evt-901",
  "eventType": "PaymentCaptured",
  "schemaVersion": 2,
  "aggregateId": "pay-173",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-11T09:12:00Z",
  "correlationId": "checkout-742",
  "payload": {
    "paymentId": "pay-173",
    "orderId": "ord-742",
    "amountMinor": 500000,
    "currency": "VND"
  }
}
~~~

eventId nhận diện **một sự kiện**, aggregateId nhận diện đối tượng, version giúp xử lý ordering khi phù hợp. Đừng chỉ dùng orderId làm dedup key: cùng một order có thể có OrderPlaced, OrderPaid, OrderCancelled và nhiều sự kiện hợp lệ khác.

### 10.2. Consumer phải chọn ack sau điểm bền vững

~~~text
Receive event
    |
    v
Check duplicate + apply business transaction atomically
    |
    v
Commit durable state
    |
    v
Ack message / commit offset
~~~

Nếu ack trước commit, crash có thể làm mất effect. Nếu commit trước ack, crash có thể gây redelivery nhưng consumer có thể nhận diện duplicate. Thiết kế chấp nhận attempt lặp để tránh mất dữ liệu.

## 11. Inbox / processed-message table

Một consumer có thể lưu danh sách event đã xử lý theo namespace của chính nó.

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một database transaction:

1. Thử insert (consumerName, eventId) với unique constraint.
2. Nếu đã tồn tại, xác nhận message đã xử lý theo quy tắc và không áp dụng side effect lại.
3. Nếu insert thành công, thực thi thay đổi nghiệp vụ trong **cùng transaction**.
4. Commit, rồi ack message.

### 11.1. Pseudo-SQL cho consumer cập nhật Order projection

~~~sql
BEGIN;

INSERT INTO processed_messages(
    consumer_name, event_id, processed_at
)
VALUES ('order_projection', :eventId, now())
ON CONFLICT DO NOTHING;

-- Ứng dụng chỉ được chạy phần UPDATE nếu INSERT mới thành công.
UPDATE order_projection
SET payment_status = 'CAPTURED',
    payment_version = :newVersion
WHERE order_id = :orderId
  AND payment_version < :newVersion;

COMMIT;
~~~

Cần thực hiện kiểm tra row count của INSERT và transition/version đúng trong application hoặc trong stored procedure atomic. Nếu cứ UPDATE dù insert conflict thì chưa có dedup thực.

### 11.2. Vì sao marker và effect phải cùng transaction?

Nếu lưu marker trước, rồi commit, sau đó xử lý nghiệp vụ nhưng crash, message giao lại sẽ bị xem là “đã xử lý” dù tác dụng chưa xảy ra.

Nếu xử lý nghiệp vụ trước, commit, sau đó mới lưu marker, crash có thể khiến redelivery áp dụng effect lần nữa.

~~~text
Không an toàn:
  COMMIT marker
  crash
  business effect chưa xảy ra

Không an toàn:
  COMMIT effect
  crash
  marker chưa lưu, event bị xử lý lại

An toàn trong cùng DB:
  BEGIN
    INSERT marker
    APPLY effect
  COMMIT cả hai
~~~

Nếu marker và effect nằm ở hai database khác nhau, một transaction cục bộ không bảo vệ toàn bộ; phải dùng cơ chế khác (business idempotency, outbox, workflow, reconciliation).

### 11.3. Mỗi consumer có namespace riêng

Notifications và Search Projection cùng nhận PaymentCaptured nhưng cần thực hiện hai công việc độc lập. Không dùng một bảng processed_messages toàn cục với unique(eventId) nếu điều đó làm consumer Search bị bỏ qua sau khi Notifications đã xử lý.

Khóa nên ít nhất nhận diện **consumer logic**. Nếu mỗi replica cùng một logical consumer, chúng chia một namespace dedup. Nếu tạo consumer mới để rebuild projection, cần xác định intentional replay policy và không nhân side effects.

### 11.4. Ghi marker không đồng nghĩa đã làm thành công ngoài DB

Consumer gửi email, sau đó lưu processed marker: crash sau gửi trước marker khiến gửi lại. Nếu lưu marker trước gửi: crash khiến email bị mất. Đây là vấn đề **external side effect**; marker và SMTP không chia sẻ transaction.

Có thể dùng outbox email intents với unique key theo business operation, rồi một notification delivery service có provider idempotency hoặc trạng thái gửi/đối soát phù hợp. Nếu nhà cung cấp email không hỗ trợ idempotency hoặc tra cứu outcome, có thể không bảo đảm gửi đúng một email trong mọi sự cố. Phải chọn chính sách chấp nhận duplicate hoặc missing theo nghiệp vụ và công bố giới hạn.

## 12. Transactional outbox chống mất sự kiện, không tự chống duplicate

Một producer lưu business state và publish event trực tiếp:

~~~text
1. COMMIT OrderCreated
2. PUBLISH OrderCreated
~~~

Nếu crash giữa hai bước, Order đã có nhưng event không được phát. Nếu publish trước commit, consumer có thể nhận event về Order chưa thực sự tồn tại.

**Transactional outbox** ghi business change và outbox record trong cùng transaction:

~~~text
BEGIN
  INSERT order
  INSERT outbox event with stable eventId
COMMIT

Relay:
  read outbox
  publish event
  checkpoint/mark published
~~~

Relay có thể publish trùng nếu mất kết nối trước khi ghi checkpoint. Đó là lý do outbox thường kết hợp với inbox/idempotent consumers.

### 12.1. Một eventId ổn định qua retry

Relay không được tạo một eventId mới mỗi lần thử publish cùng outbox entry. Nếu thay ID, consumer dedup theo eventId sẽ coi là hai event khác nhau. Giữ event identity và payload semantics ổn định; attemptId có thể thay đổi để quan sát.

### 12.2. CDC và outbox

Một số hệ thống dùng change data capture để phát outbox records. CDC có thể cung cấp tiến độ và thứ tự theo transaction log, nhưng consumer vẫn cần hiểu duplicate, restart, snapshot, retention và schema. “Có CDC” không phải phép màu exactly-once toàn hệ thống.

### 12.3. Publish acknowledgement mơ hồ

Nếu broker đã lưu event nhưng producer timeout trước khi nhận ack, producer không thể chắc lần publish đã thành công. Có thể retry với event/message ID ổn định. Một số broker hỗ trợ producer dedup trong phạm vi giới hạn; consumer vẫn phải dự phòng trùng nếu sự cố vượt giả định.

## 13. At-least-once + idempotent effect: một chứng minh thực dụng

Mục tiêu: một consumer ghi đúng một lần hiệu ứng cấp quyền từ PaymentCaptured.

Giả định:

1. eventId ổn định qua redelivery.
2. Consumer sử dụng DB transaction duy nhất cho marker và entitlement update.
3. Unique constraint trên (consumerName, eventId) và/hoặc unique business entitlement intent.
4. Consumer ack sau commit.
5. Hạ tầng tiếp tục redeliver tới khi được ack trong giới hạn retention/retry đã định.
6. Không có side effect ngoài phạm vi transaction mà không có idempotency riêng.

Khi message được nhận lần đầu, transaction commit marker + entitlement. Nếu worker crash trước commit, cả marker và effect rollback; redelivery có thể xử lý. Nếu crash sau commit trước ack, redelivery thấy marker tồn tại và skip; effect không nhân đôi.

**Như vậy số effect đã commit là không quá một** theo unique key. Để nói “đúng một” còn cần message không bị mất vĩnh viễn, consumer có thể phục hồi và xử lý thành công cuối cùng. At-least-once không tự đảm bảo liveness nếu message bị chuyển DLQ không ai xử lý, dữ liệu lỗi vĩnh viễn hoặc operation bị hủy theo policy.

### 13.1. Một lần effect không phải một lần attempt

~~~text
attempt 1: message received -> transaction committed -> crash before ack
attempt 2: redelivered -> duplicate detected -> ack

delivery attempts = 2
business effect commits = 1
~~~

Đây thường là mục tiêu thực tế, thay vì cố buộc attempts = 1.

### 13.2. Cửa sổ retention ảnh hưởng chứng minh

Nếu processed marker hết hạn sau 7 ngày nhưng event được replay sau 30 ngày, consumer có thể áp dụng effect lại. Muốn bảo đảm dài hơn, cần giữ identity/invariant lâu hơn, hoặc tái xử lý trên read model cô lập, hoặc dựa vào unique business constraints bền vững.

## 14. Không dùng dedup để che lỗi thứ tự

Hai sự kiện khác nhau về cùng một aggregate:

~~~text
OrderPaid      version=5, eventId=e5
OrderCancelled version=6, eventId=e6
~~~

Consumer nhận e6 trước e5. Dedup theo eventId **không xử lý out-of-order**, vì hai event đều mới. Nếu consumer cập nhật state trực tiếp theo thứ tự nhận, e5 tới muộn có thể đưa Order từ CANCELLED về PAID.

Các giải pháp tùy use case:

- Partition key theo aggregateId nếu broker hỗ trợ ordering theo partition.
- Aggregate version và conditional update chỉ chấp nhận version mới hơn.
- State machine từ chối transition không hợp lệ.
- Buffer hoặc xử lý thiếu sequence khi cần tất cả events theo thứ tự.
- Rebuild projection từ log theo thứ tự đã xác định.
- Khác source thì cần causal semantics rõ, không dựa mù vào timestamp.

**Business ordering và duplicate filtering là hai vấn đề riêng**, dù thường kết hợp trong một consumer.

### 14.1. Version không thay thế eventId

Một aggregateVersion cho phép reject stale update; nhưng nếu cùng version có nhiều event hợp lệ trong một transaction tùy mô hình, cần định nghĩa thứ tự/định danh riêng. Không giả định mọi kiến trúc đều có một global version.

### 14.2. Event time và processing time

Một event xảy ra lúc 10:00 nhưng xử lý lúc 10:05; replay sau một tháng không làm event trở thành mới. Dùng thời điểm/sequence phù hợp cho nghiệp vụ, đồng thời giữ attempt time để debug. Không dùng đồng hồ của nhiều service làm thứ tự tuyệt đối nếu không có giao thức nhất quán.

## 15. Concurrency, optimistic locking và idempotency khác nhau ra sao?

**Idempotency** giải quyết **cùng thao tác lặp lại**. **Concurrency control** giải quyết **nhiều thao tác có thể cùng thay đổi một trạng thái**. Chúng giao nhau nhưng không thay thế nhau.

### 15.1. Ví dụ tranh ghế cuối cùng

Có một ghế với available=1. Hai yêu cầu ReserveSeat A và B có **idempotency keys khác nhau**.

~~~text
A reads available=1
B reads available=1
A decrements to 0
B decrements to 0
Both claim success -> overselling
~~~

Dedup không nhận đây là duplicate, vì A và B là hai ý định độc lập.

Có thể dùng conditional update:

~~~sql
UPDATE seats
SET available = available - 1,
    version = version + 1
WHERE seat_id = :seatId
  AND available > 0;
~~~

Chỉ request thực sự cập nhật một row theo transaction isolation/lock phù hợp được coi là thành công. Với bán một ghế duy nhất theo seatId, unique constraint trên active reservation/booking seat có thể biểu diễn bất biến rõ hơn.

### 15.2. Optimistic locking

~~~sql
UPDATE inventory
SET quantity = :newQuantity,
    version = version + 1
WHERE sku = :sku
  AND version = :expectedVersion;
~~~

Nếu zero row affected, có thay đổi cạnh tranh. Caller cần đọc lại và quyết định: retry phép tính an toàn, trả conflict hoặc chuyển workflow. Không tự động tăng retry vô hạn.

### 15.3. Two requests same key versus different key

| Trường hợp | Công cụ chính |
| --- | --- |
| Cùng user retry một POST giống hệt | Idempotency key + durable result |
| Cùng event giao lại nhiều lần | Inbox/dedup marker + idempotent handler |
| Hai user cùng giành một ghế | Unique constraint/conditional update/lock |
| Hai worker xử lý cùng job do lease hết hạn | Fencing/claim version + idempotency |
| Hai command khác nhau cùng thay đổi đơn | Aggregate version + state machine |
| Payment provider callback đến hai lần | Stable event/transaction reference + idempotent transition |
| Một command mới hợp lệ sau command cũ | Business version/intent, không dedup nhầm |

### 15.4. Lock không tự tạo idempotency

Một mutex ngăn hai requests chạy **đồng thời**, nhưng khi lock được thả, retry có thể lại thực thi side effect nếu không có persisted result hoặc business invariant. Ngược lại, idempotency key ngăn same intent lặp nhưng không giải quyết tranh chấp giữa các intents khác nhau.

## 16. Worker lease, fencing và khi “một job một worker” không còn đúng

Một queue có visibility timeout 30 giây. Worker A nhận job và xử lý 40 giây. Sau 30 giây, lease hết; Worker B cũng nhận job. Trong 10 giây có thể hai worker cùng làm việc.

~~~text
time 0:  Worker A claims job (lease version 10)
time 30: A stalled, lease expires
time 31: Worker B claims job (lease version 11)
time 35: B commits result
time 40: A wakes and tries to commit stale result
~~~

Nếu chỉ kiểm tra “job status = RUNNING”, A có thể ghi đè kết quả B. Dùng **fencing token/lease generation** ở storage chịu side effect:

~~~sql
UPDATE jobs
SET result_ref=:result,
    status='SUCCEEDED'
WHERE job_id=:jobId
  AND lease_generation=:myGeneration
  AND status='RUNNING';
~~~

A với generation 10 không thể commit sau khi B sở hữu generation 11. Nhưng nếu A đã gọi provider ngoài, DB fencing token **không tự ngăn side effect ngoài**. External operation vẫn cần stable idempotency key và status reconciliation.

### 16.1. Heartbeat và gia hạn lease

Worker có thể gia hạn lease khi job dài, nhưng cần tránh hai worker cùng cho rằng mình còn quyền. Lưu version/owner và precondition khi gia hạn. Khi worker mất quyền, nên dừng các bước còn có thể hủy; không giả định cancellation sẽ thu hồi một HTTP request ngoài đã gửi.

### 16.2. Work queue và consumer group

Competing consumers thường cố giao một job cho một worker tại một thời điểm, nhưng không hứa không bao giờ có overlap hoặc retry. Idempotency là cơ chế correctness cuối cùng ở điểm ghi tác dụng nghiệp vụ.

## 17. External side effects: ranh giới khó nhất

### 17.1. Vì sao không thể atomic với mọi hệ thống?

Trong DB nội bộ, insert marker và update nghiệp vụ có thể chung transaction. Nhưng giữa database của ứng dụng và cổng thanh toán, bạn thường không thể gộp hai commit thành một transaction ACID thực tế.

~~~text
Local DB transaction                  External Provider
--------------------                  -----------------
write operation intent
commit local DB
                                     capture money
receive response
write outcome to DB
~~~

Nếu provider capture thành công rồi response bị mất, local DB vẫn có thể PENDING. Một retry bằng request ID mới có nguy cơ tạo capture mới. Transaction của broker hoặc DB không biết chắc hiệu ứng ở provider.

### 17.2. Phương án đúng: định danh bên ngoài ổn định

Nếu provider hỗ trợ idempotency key, sử dụng một key cố định cho cùng payment intent và giữ nguyên qua retry.

~~~text
paymentIntentId = pi-742
providerRequestId = capture-pi-742-v1

attempt 1: POST capture, key=capture-pi-742-v1 --> timeout
attempt 2: GET status by key/reference --> captured
result: record captured; no second capture
~~~

Nếu provider có API lookup và contract rõ, dùng lookup trước khi gửi lại operation. Nếu provider không hỗ trợ cả idempotency lẫn truy vấn kết quả đáng tin, phải công nhận **không thể bảo đảm exactly-once external effect trong mọi failure mode** chỉ bằng code của caller. Có thể phải chấp nhận duplicate và xây reconciliation/refund/manual handling.

### 17.3. Phân biệt authorization, capture và settlement

Một payment có thể được AUTHORIZED rồi CAPTURED rồi SETTLED. Mỗi bước là một hành động nghiệp vụ riêng, có thể có partial capture/refund. Không dùng một khóa duy nhất cho mọi hành động của một payment nếu provider/contract cho phép nhiều operation hợp lệ.

Ví dụ:

- captureIntentId: lần thu tiền cụ thể.
- refundIntentId: một lần hoàn tiền cụ thể.
- providerTransactionId: side effect đã được provider tạo.
- ledgerEntryId: một bút toán nội bộ.
- attemptId: lần thử HTTP.

Chống trùng bằng paymentId đơn thuần có thể bỏ nhầm một partial refund hợp lệ. Chọn identity theo tác dụng được phép một lần.

### 17.4. Email, SMS và thông báo

Một notification có thể được tạo một lần theo intent, nhưng việc giao tới hộp thư là side effect của provider. Nếu gửi email thành công rồi response thất lạc, gửi lại có thể tạo email trùng. Có thể dùng provider message ID/idempotency nếu hỗ trợ, lưu delivery status và thiết kế nội dung chịu được duplicate. Nếu cam kết email chính xác một lần là bất khả thi theo provider, tài liệu SLO phải phản ánh giới hạn này.

### 17.5. Vận đơn và cấp quyền

- Tạo shipment: dùng merchant shipment request ID, query provider trước retry sau timeout.
- Cấp entitlement: unique(userId, productId, grantIntentId) theo quy tắc và kiểm tra quyền trước tạo.
- Hoàn tiền: refundIntentId ổn định, trạng thái UNKNOWN phải tra cứu trước khi tạo lại.
- Phát hành hóa đơn: unique document intent, số hóa đơn/chứng từ theo quy tắc pháp lý và audit.

Idempotency không phải phương án thay thế domain validation.

## 18. Nhận biết và xử lý kết quả chưa rõ

Một trạng thái UNKNOWN không đồng nghĩa FAILED.

~~~text
SENT
  |
  +-- provider confirms success --> SUCCEEDED
  |
  +-- provider confirms rejected --> REJECTED
  |
  +-- timeout/no response -------> UNKNOWN
                                     |
                                     v
                              reconcile/lookup
                                     |
                       +-------------+-------------+
                       |                           |
                   confirmed                   still unknown
                       |                           |
                       v                           v
                    finalize                wait/escalate
~~~

Nếu UNKNOWN, hệ thống có thể:

1. Kiểm tra idempotency record và business operation hiện tại.
2. Query provider theo stable reference.
3. Đọc webhook inbox, outbox, audit và ledger.
4. Chờ một khoảng indexing/settlement hợp lệ khi provider chưa thể tra cứu ngay.
5. Giữ trạng thái đang xử lý và không tạo operation mới nếu có rủi ro duplicate.
6. Mở case đối soát có owner/deadline nếu tự động không đủ bằng chứng.

Không được trả “FAILED, hãy thanh toán lại” chỉ vì một HTTP timeout, khi thực tế tiền có thể đã bị thu.

## 19. Saga, compensation và tính lặp an toàn của bước bù

Một saga có bước:

~~~text
ReserveInventory --> CapturePayment --> CreateShipment
          |                 |                 |
     ReleaseInventory   RefundPayment    CancelShipment
~~~

Nếu CreateShipment thất bại, saga có thể chạy RefundPayment và ReleaseInventory. Nhưng các lệnh bù cũng có thể được retry/redeliver.

### 19.1. Mỗi bước bù cần identity riêng

Một compensation command nên có:

- sagaId/workflowId.
- stepId và compensation intent.
- idempotency key ổn định cho cùng hành động bù.
- expected business state/version.
- lý do và reference tới operation gốc.
- trạng thái PENDING, SUCCEEDED, REJECTED, UNKNOWN.
- bằng chứng xác minh nếu effect nằm ngoài service.

Không sử dụng chung key với CapturePayment cho RefundPayment: đây là hai hành động khác nhau. Không tạo key refund mới mỗi lần compensation timeout.

### 19.2. Compensation không phải rollback ACID

RefundPayment là giao dịch mới chứ không xóa capture gốc. ReleaseInventory có thể không còn hợp lệ nếu hàng đã giao. CancelShipment có thể thất bại sau khi hàng đã vận chuyển. Exactly-once của mỗi command không làm mọi bước bù thành công.

### 19.3. Idempotency trong workflow dài

Nếu một saga chạy nhiều ngày, cần giữ event/command identity đủ lâu. Nếu workflow engine retry một activity, activity phải chịu được cùng input/intent lặp. Không dùng “engine chạy đúng một workflow instance” để suy ra external API chỉ được gọi một lần.

## 20. Java/Spring: thiết kế idempotent command handler

Các ví dụ dưới đây trình bày cấu trúc và bất biến, không phải dự án hoàn chỉnh có thể copy production ngay. Muốn dùng thật cần thay thế repository, transaction handling, validation, security và các loại lỗi theo hệ thống.

### 20.1. Controller nhận khóa ở biên

~~~java
@RestController
@RequestMapping("/v1/orders")
public class CreateOrderController {
    private final CreateOrderApplicationService service;

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderRequest request,
            Authentication authentication) {

        String tenantId = getAuthorizedTenant(authentication);
        CreateOrderResult result =
            service.create(tenantId, key, request);

        return ResponseEntity
            .status(result.isNew() ? 201 : 200)
            .body(result.toResponse());
    }
}
~~~

Trong thực tế phải giới hạn độ dài/format key, validate tenant resource ownership, chống replay giữa principal khác nhau và map lỗi rõ. Không tin tenantId do client tự cung cấp nếu chưa được xác thực.

### 20.2. Application service với transactional claim

~~~java
@Service
public class CreateOrderApplicationService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public CreateOrderResult create(
            String tenantId,
            String key,
            CreateOrderRequest request) {

        String hash = canonicalRequestHash(request);

        ClaimResult claim =
            idempotency.tryClaim(tenantId, "CREATE_ORDER", key, hash);

        if (claim.isExisting()) {
            claim.verifySameFingerprint(hash);
            return claim.toStoredOrInProgressResult();
        }

        Order order = Order.create(
            tenantId, request.cartId(), request.shippingAddressId());
        orders.save(order);

        outbox.save(OrderCreated.from(order));

        idempotency.markCompleted(
            tenantId, "CREATE_ORDER", key, order.id());

        return CreateOrderResult.newOrder(order.id());
    }
}
~~~

Hàm tryClaim phải thực sự dùng ràng buộc atomic của DB, không phải check-then-insert không khóa. Nếu request trùng tới khi transaction chưa commit, cần xác định hành vi block/wait/conflict theo isolation của DB. Nếu service gọi provider ngoài, ví dụ này không bảo đảm hiệu ứng ngoài DB; nên tách workflow/outbox và provider idempotency.

### 20.3. Consumer với inbox trong cùng transaction

~~~java
@Service
public class PaymentCapturedHandler {
    private final ProcessedMessageRepository inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public void handle(PaymentCaptured event) {
        boolean claimed = inbox.tryInsert(
            "ordering.payment_projection", event.eventId());

        if (!claimed) {
            return; // Đã xử lý; broker có thể ack sau commit.
        }

        Order order = orders.getForUpdate(event.orderId());
        order.applyPaymentCaptured(
            event.paymentId(), event.amount(), event.version());

        orders.save(order);
        outbox.save(OrderPaymentUpdated.from(order, event));
    }
}
~~~

Consumer framework chỉ ack **sau khi transaction thành công**. Nếu handle() throw, rollback marker và domain update, message có thể được redeliver. applyPaymentCaptured vẫn nên kiểm tra business transition, payment identity và amount; inbox chỉ dedup cùng eventId, không bảo vệ mọi duplicate business effect từ các events khác nhau.

### 20.4. Chống cập nhật trùng bằng SQL conditional update

~~~sql
UPDATE orders
SET payment_state='CAPTURED',
    payment_version=:incomingVersion
WHERE order_id=:orderId
  AND payment_version < :incomingVersion
  AND payment_state IN ('PENDING', 'AUTHORIZED');
~~~

Đây là ví dụ xử lý projection theo version. Tùy state machine, event đến trễ có thể phải ghi nhận trong audit và đối soát thay vì bị loại bỏ hoàn toàn. Nếu một payment có partial captures, một cột payment_state đơn giản có thể không đủ.

### 20.5. Không nhầm Spring @Transactional với external exactly-once

@Transactional quản lý transaction của resource được cấu hình. Nó không tự khiến một HTTP call tới provider, Kafka publish và database commit trở thành một giao dịch atomic. Phải xác định những transaction managers/participants thực sự được phối hợp và các giới hạn failover.

## 21. Lựa chọn nơi áp dụng idempotency

Một request nhiều lớp có thể cần nhiều điểm bảo vệ:

| Lớp | Identity | Bảo vệ |
| --- | --- | --- |
| Client | Idempotency-Key theo business intent | Retry không biến thành tác vụ mới |
| API/BFF | Principal + operation + key + fingerprint | Cùng request không chạy handler hai lần |
| Domain command | Business operation ID / unique constraint | Hai keys khác nhau không phá invariant |
| Database | Transaction, unique index, CAS/version | Atomic state và concurrency |
| Outbox relay | Stable event ID | Retry publish không biến event logic thành sự kiện mới |
| Broker | Message ID/producer sequence theo khả năng | Giảm duplicate trên transport trong phạm vi hỗ trợ |
| Consumer inbox | Consumer namespace + eventId | Redelivery không áp dụng cùng event lại |
| External provider | Provider idempotency key/reference | Retry không tạo side effect ngoài mới |
| Reconciliation | Business operation + provider evidence | Khôi phục outcome UNKNOWN |
| Operational repair | Case/action ID + approval + version | Operator retry không sửa hai lần |

Không nhất thiết mọi use case cần đủ mười lớp. Chọn theo rủi ro, nhưng đừng đặt tất cả niềm tin vào một tầng mà nó không thể nhìn thấy side effect ở tầng khác.

### 21.1. Hai khóa có vẻ tương tự nhưng phạm vi khác

- **Request idempotency key** đảm bảo cùng request logic được nhận diện.
- **Event dedup key** đảm bảo cùng event được xử lý một lần cho một consumer.
- **Business unique key** đảm bảo invariant như một quyền cấp theo một purchase.
- **External provider request key** đảm bảo cùng external operation không nhân đôi.

Có thể liên kết các key qua correlationId nhưng không dùng một key cho mọi khái niệm nếu vòng đời và semantics khác nhau.

## 22. Error handling: không cache lỗi một cách mù quáng

### 22.1. Lỗi trước khi thực thi

Validation fail 400 hoặc unauthorized 403 xảy ra trước khi side effect; chính sách có thể không lưu như idempotent terminal result, hoặc lưu theo contract trong thời gian ngắn. Quan trọng là client biết sửa request sẽ cần key mới hay không.

### 22.2. Business rejection

Một lệnh hợp lệ bị từ chối vì hết hàng có thể là terminal outcome của intent. Nếu retry cùng key, trả kết quả từ chối logic tương đương; không tự chuyển thành accepted chỉ vì tồn kho vừa tăng, trừ khi contract định nghĩa intent có thể được reevaluate.

### 22.3. Infrastructure failure trước commit

Nếu chắc chắn transaction rollback và chưa có external effect, có thể cho retry cùng key với retry budget.

### 22.4. Unknown outcome

Khi side effect có thể đã xảy ra, không gắn FAILED cuối cùng khi thiếu bằng chứng. Lưu PENDING/UNKNOWN và query status hoặc đối soát.

### 22.5. Status codes của duplicate requests

- 200/201 với cùng resource/result cho completed.
- 202 + status URL cho accepted nhưng chưa hoàn tất.
- 409 cho conflicting payload hoặc duplicate in progress theo contract.
- 429 cho quá giới hạn, kèm Retry-After khi hợp lý.
- 503 cho tạm không thể xử lý với retry policy rõ.

Không có status code nào tự định nghĩa idempotency. Hợp đồng phải nói rõ **client giữ key cũ khi nào, tạo key mới khi nào và đọc trạng thái ở đâu**.

## 23. Thời hạn khóa, dọn dẹp và replay lịch sử

### 23.1. Đánh đổi giữa storage và bảo đảm

Lưu idempotency records, processed events và outbox mãi mãi sẽ tạo áp lực storage/index. Dọn quá sớm lại mở cửa duplicate sau retry hoặc replay. Có thể phân lớp:

- Response cache cho API retry ngắn hạn.
- Business intent table giữ lâu theo vòng đời giao dịch.
- Processed event marker giữ theo retention/replay policy.
- Ledger/entitlement uniqueness giữ theo nghĩa vụ nghiệp vụ.
- Event log lưu theo retention/compaction và khả năng rebuild.
- Audit records theo quy định bảo mật/tuân thủ.

### 23.2. Key hết hạn nhưng nghiệp vụ còn tồn tại

Nếu API record hết TTL, có thể tìm business resource qua client intent ID hoặc merchant reference. Nếu không có unique/business lookup, retry sau TTL có thể tạo effect mới. Hợp đồng phải nêu rõ giới hạn này.

### 23.3. Replay consumer sau vài tháng

Nếu replay để xây lại search index, tạo consumer group/namespace riêng và ghi dữ liệu vào index mới. Không cho replay đồng thời thực thi RefundPayment/SendEmail. Có thể rebuild projection bằng event log có đủ lịch sử, nhưng các business side effects cần cách xử lý khác.

### 23.4. Khi retention không đủ

Đừng tuyên bố “có thể replay từ đầu” nếu log cũ đã xóa hoặc compact. Phải có snapshot/backfill từ source of truth và quy trình đối soát phần thiếu.

## 24. Khả năng quan sát: biết trùng ở đâu và có gây effect trùng không

Các metric quan trọng:

- API idempotency claim success, duplicate hit, conflict fingerprint.
- In-flight key age, stuck PROCESSING count, recovery outcome.
- Inbox dedup hit rate theo consumer.
- Number of delivery attempts per event, ack failures, redelivery rate.
- Outbox backlog age, repeated publish count.
- Provider unknown-outcome rate, status lookup/reconciliation rate.
- Business duplicate-effect incidents: duplicate charge/shipment/entitlement.
- Unique constraint conflict rate; concurrency retry rate.
- Lease expiry/fencing rejection rate.
- DLQ age, re-drive attempt, replay side effect prevention.
- Tỷ lệ request đã thành công nhưng client nhận timeout.
- Thời gian từ unknown outcome đến trạng thái được xác minh.

**Dedup hit rate cao không nhất thiết là sự cố:** at-least-once broker sẽ có trùng hợp lệ khi crash/rebalance. Nhưng đột biến có thể chỉ ra consumer timeout, ack problem hoặc publisher retry storm. Cần kết hợp error/latency/throughput để đánh giá.

### 24.1. Log và tracing

~~~text
trace checkout-742
  requestId = req-12
  idempotencyKeyHash = ...
  businessIntent = pi-742
  commandId = cmd-515
  eventId = evt-901
  consumer = ordering.payment_projection
  processingAttempt = 2
  outcome = ALREADY_APPLIED
~~~

Không log raw access token, secrets, toàn bộ payload nhạy cảm. Key có thể chứa thông tin nhận dạng do client tạo, nên cân nhắc hash/masking. Trong metric không dùng requestId/eventId làm label nếu gây cardinality quá cao.

### 24.2. Các dashboard cần phân biệt

- Transport duplicate: broker redelivery.
- Domain duplicate prevented: unique/business constraint đã chặn.
- Real duplicate effects: side effect thật bị nhân đôi.
- Unknown outcomes awaiting reconciliation.
- Processing stuck và retry backlog.
- SLO của operation end-to-end thay vì chỉ broker uptime.

Một hệ thống có 1.000 dedup hits và 0 duplicate charges có thể hoạt động đúng. Một hệ có 0 dedup hits nhưng 3 double charges là lỗi nghiêm trọng.

## 25. Bảng phân tích crash theo thứ tự commit/ack

| Trình tự | Crash xảy ra | Hậu quả không được bảo vệ | Cách xử lý |
| --- | --- | --- | --- |
| Ack → DB commit | Sau ack, trước commit | Effect bị mất | Ack sau commit |
| DB commit → ack | Sau commit, trước ack | Message redeliver | Idempotent transaction/inbox |
| Marker commit → effect commit | Ở giữa | Bỏ effect vì marker đã có | Marker và effect cùng transaction |
| Effect commit → marker commit | Ở giữa | Effect trùng sau retry | Marker và effect cùng transaction |
| DB commit → broker publish | Ở giữa | Event không phát | Transactional outbox |
| Broker publish → DB mark sent | Ở giữa | Event publish trùng | Stable eventId + consumer dedup |
| External charge → local record | Response mất | Outcome UNKNOWN, có thể double charge | Provider key + lookup + reconciliation |
| Operator action → HTTP response | Sau effect trước response | Người vận hành nhấn lại | Action idempotency + status query |
| Job claim → long work | Lease hết hạn | Hai worker đồng thời | Fencing/version + effect idempotency |
| Stream output commit → offset commit rời | Ở giữa | Reprocessing và output trùng | Atomic stream transaction trong phạm vi hỗ trợ |

Bảng giúp xác định nơi cần **atomicity** và nơi cần **khả năng chịu lặp**. Không thể chỉ chữa bằng tăng timeout.

## 26. Anti-pattern và cách sửa

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| Retry POST bằng key mới khi timeout | Biến cùng intent thành operation mới | Giữ stable idempotency key |
| Dedup theo hash payload đơn thuần | Gộp nhầm hai intents hợp lệ | Business intent ID/key |
| Check tồn tại rồi insert ngoài transaction | Hai requests đều đi qua | Unique constraint/atomic claim |
| Lưu processed marker trước business effect | Crash làm mất effect | Cùng DB transaction |
| Ack message trước commit | Mất effect nhưng broker không giao lại | Commit rồi ack |
| Tin broker exactly-once cho external API | Không bao trùm side effect ngoài broker | Provider key/lookup/reconciliation |
| Dùng requestId mới cho mỗi retry | Dedup không nhận ra cùng request | Stable ID qua attempts |
| Một global processed-event table cho mọi consumer | Consumer độc lập bị chặn nhầm | Namespace theo logical consumer |
| Chỉ dùng aggregateId để dedup mọi event | Bỏ những event hợp lệ sau đó | eventId + version/business rule |
| Chỉ dùng lock cục bộ | Không bảo vệ nhiều replicas/restart | Durable unique/transaction/lease |
| Chỉ dùng mutex mà không lưu outcome | Retry sau lock vẫn gây effect mới | Idempotency record/business invariant |
| Coi timeout = thất bại cuối | Tạo command mới khi effect đã xảy ra | UNKNOWN + lookup |
| Cache mọi lỗi 500 mãi mãi | Một lỗi tạm chặn operation | Error taxonomy + recovery policy |
| Xóa key PROCESSING quá hạn rồi tạo lại | Có thể nhân external effects | Recovery state + evidence |
| Dùng cùng key cho capture và refund | Hai actions độc lập bị gộp | Action-specific stable intents |
| Replay production events vào live side-effect consumers | Gửi email, charge, ship lại | Isolated replay/projection |
| Giữ inbox marker ngắn hơn replay horizon | Duplicate sau expiration | Retention aligned với business invariant |
| Tưởng Kafka transaction = ACID toàn hệ | False exactly-once claim | Ghi rõ transaction scope |
| Idempotency nhưng bỏ qua ordering | Event cũ ghi đè event mới | Version/state machine |
| Dùng idempotency thay optimistic locking | Khác key vẫn đua cùng resource | CAS/unique/business validation |
| Không log trace của duplicate | Khó điều tra redelivery | Correlation/eventId/attemptId và metrics |

## 27. Bài tập 1: API tạo đơn bị timeout

**Bối cảnh:** người dùng đặt mua hàng. App gửi POST /orders với Idempotency-Key K1. Order được tạo và outbox event đã commit, nhưng HTTP response bị mất. App retry cùng K1; đồng thời người dùng mở app trên thiết bị khác và nhấn “Mua ngay” với key K2 nhưng cùng cartId.

**Câu hỏi:**

1. Kết quả retry với K1 phải như thế nào?
2. Nếu K1 đang PROCESSING, API nên trả gì?
3. Nếu K1 được gửi lại với shippingAddressId khác, xử lý ra sao?
4. K2 cùng cartId có luôn là duplicate không? Vì sao?
5. Cần định nghĩa business intent nào để chống tạo hai order ngoài ý muốn?
6. Làm sao ghi order, idempotency result và outbox atomic?
7. Nếu relay phát OrderCreated hai lần, consumer xử lý thế nào?
8. Nếu K1 hết hạn sau vài giờ, chính sách gì ngăn tạo lại order cũ?
9. Nêu các metric và trace fields giúp biết lần tạo nào thắng.
10. Viết failure-injection test crash sau commit trước response.

**Một hướng giải:** retry K1 phải trả cùng orderId. Với K2, cần biết hai hành động có phải cùng purchase intent hay là hai ý định hợp lệ; không dedup mù theo cartId. Unique business intent có thể bổ sung cho API key. Order/outbox/idempotency record commit cùng transaction; consumer có inbox và business invariant. Nếu K1 đang chạy, API trả status rõ, không tạo order thứ hai.

## 28. Bài tập 2: Payment provider timeout sau capture

**Bối cảnh:** Payments gọi provider capture 500.000 VND với requestId P1. Provider đã thu tiền nhưng response timeout. Worker retry bằng P2 và provider tạo capture thứ hai. Sau đó callback hai captures đến qua broker, một callback được giao lại ba lần.

**Yêu cầu:**

1. Chỉ ra hai lớp duplicate khác nhau.
2. Phân biệt P1/P2 là attemptId, operationId hay provider idempotency key.
3. Thiết kế paymentIntentId, captureIntentId và merchantReference.
4. Nếu provider hỗ trợ idempotency key, quy tắc retry ra sao?
5. Nếu provider không hỗ trợ idempotency nhưng có lookup API, làm gì?
6. Nếu provider không có lookup đáng tin và outcome UNKNOWN, cần chính sách gì?
7. Consumer nhận cùng callback ba lần nên dedup theo trường nào?
8. Nếu hai captures thật đã xảy ra, dedup callback có giải quyết double charge không?
9. Cần đối soát provider settlement và ledger như thế nào?
10. Tình huống nào đòi refund/adjustment và phê duyệt?

**Một hướng giải:** dedup cùng callback chỉ loại redelivery, không xóa được hai tác dụng capture thật. Phải ngăn tạo P2 như một external intent mới khi P1 chưa rõ kết quả. Khi đã double charge, cần xác minh và điều chỉnh theo nghiệp vụ/pháp lý. Các bước manual cần evidence/audit; không chỉ đổi payment status cho “đúng”.

## 29. Bài tập 3: Consumer bị crash và retry cạnh tranh

**Bối cảnh:** consumer cấp chứng chỉ sau khi CourseCompleted. Event E1 được giao Worker A; A ghi entitlement thành công nhưng crash trước ack. Broker giao E1 cho B; cùng lúc event E2 với cùng user/course nhưng từ một bước business khác tới.

**Câu hỏi:**

1. Inbox marker và entitlement phải commit theo thứ tự nào?
2. E1 redelivery phải được xử lý ra sao?
3. E2 có luôn là duplicate không?
4. Nếu một user có thể nhận chứng chỉ nhiều lần theo course edition, business key là gì?
5. Nếu A và B cùng xử lý vì lease hết hạn, fencing hỗ trợ ra sao?
6. Nếu việc tạo PDF ở object storage thành công nhưng DB commit fail, cần idempotency gì?
7. Nếu hệ thống replay E1 để rebuild projection, làm sao không cấp lại chứng chỉ thật?
8. Nếu processed marker hết hạn trước replay, hậu quả gì?
9. Test crash tại các điểm nào?
10. Đo business duplicate-effect rate thay vì chỉ redelivery count bằng cách nào?

**Gợi ý:** dùng (consumerName,eventId) để chống redelivery của E1, kết hợp unique entitlement intent để bảo vệ business rule cho E2. Chứng chỉ PDF cần deterministic object key hoặc generation ID, trạng thái job bền vững và reconciliation nếu storage/DB không atomic. Replay projection phải cô lập khỏi external side effects.

## 30. Bài tập 4: Hai giao dịch khác nhau cạnh tranh tài nguyên

**Bối cảnh:** một phòng khách sạn còn một suất đặt chỗ. Hai khách gửi hai CreateBooking requests khác key và khác identity, đồng thời đều đọc trạng thái AVAILABLE.

**Yêu cầu:**

1. Tại sao request idempotency không giải quyết double booking?
2. Cần unique/conditional update hay lock theo resource nào?
3. Nếu một khách gửi retry cùng key sau timeout, làm sao biết booking nào đã được tạo?
4. Nếu booking holder timeout và lease hết, cần fencing như thế nào?
5. Nếu provider hotel confirmation mất response, có được gọi tạo booking bằng reference mới không?
6. Nếu hệ thống báo 409 CONFLICT cho khách thứ hai, đây có phải idempotency-key conflict không?
7. Thiết kế state machine cho PENDING, CONFIRMED, EXPIRED và UNKNOWN.
8. Định nghĩa SLO theo số booking được xác minh và tỷ lệ oversell.

**Gợi ý:** concurrency control bảo vệ sự khan hiếm; idempotency bảo vệ retry cùng intent. Hai vấn đề cần được xử lý đồng thời, không dùng một cơ chế thay cho cơ chế kia.

## 31. ADR mẫu: idempotency cho thanh toán và consumer

~~~markdown
# ADR: Stable idempotency cho Payment Capture và Order Projection

## Bối cảnh
Mobile có retry sau timeout. Payments gọi external provider;
provider có callback bất đồng bộ và broker hỗ trợ at-least-once.
Order Projection nhận PaymentCaptured và có thể redelivery.

## Quyết định
- Mỗi payment intent có capture intent ID ổn định.
- Provider idempotency key dùng lại qua mọi retry của cùng capture.
- Trong outcome UNKNOWN, query provider/status trước khi tạo action mới.
- Payments giữ state machine và business unique constraints.
- Dữ liệu domain + outbox commit cùng transaction cục bộ.
- EventId ổn định cho cùng outbox event qua publish retries.
- Order Projection lưu (consumerName,eventId) cùng effect trong DB transaction.
- Ack broker sau DB commit; duplicate delivery được coi là bình thường.
- Aggregate version và state machine bảo vệ ordering.
- Replay projection chạy trong namespace cô lập, không gửi external effects.
- Case reconciliation có owner cho unknown/duplicate external captures.

## Không cam kết
- Không tuyên bố exactly-once HTTP attempts.
- Không tuyên bố broker transaction bảo vệ provider capture.
- Không hứa mọi external side effect là exactly-once khi provider
  không hỗ trợ idempotency/lookup.

## Lựa chọn đã cân nhắc
A. Không retry request và chấp nhận mất thao tác.
B. Broker dedup là cơ chế bảo vệ duy nhất.
C. API idempotency + domain uniqueness + outbox/inbox + provider key.
D. Distributed transaction xuyên broker/DB/provider.

## Hệ quả
- Thêm bảng key/marker, retention và recovery jobs.
- Có chi phí provider lookup và xử lý UNKNOWN.
- Cần metrics duplicate attempts và duplicate effects riêng.
- Phải test crash sau commit trước response/ack.

## Kiểm chứng
- Retry cùng key trả cùng payment result.
- Same key khác fingerprint bị từ chối.
- Duplicate event không tạo hai Order projection effects.
- Hai captures thật từ provider được phát hiện, không bị che.
- Consumer crash/redelivery và operator re-drive đều an toàn.

## Điều kiện xem lại
- Provider thay đổi idempotency/lookup contract.
- Business support partial captures/refunds mới.
- Replay horizon hoặc retention thay đổi.
~~~

## 32. Checklist triển khai trong dự án thật

**Định nghĩa nghiệp vụ**

- [ ] Biết “một lần” đang nói về request, message, DB commit hay side effect.
- [ ] Xác định business intent cho mọi tác vụ có rủi ro duplicate.
- [ ] Đã phân biệt retry cùng intent và operation mới hợp lệ.
- [ ] Có invariant trong domain/DB cho trường hợp nhiều key khác nhau.
- [ ] Chỉ rõ các giới hạn của exactly-once claim theo phạm vi transaction.

**API và idempotency**

- [ ] Có Idempotency-Key hoặc ID ổn định qua retry cho command cần bảo vệ.
- [ ] Key có scope theo principal/tenant/operation và xác thực owner.
- [ ] Có fingerprint kiểm tra cùng key khác request semantics.
- [ ] Claim key là atomic, không check-then-insert race.
- [ ] Kết quả đã commit có thể tìm lại sau response timeout.
- [ ] Có trạng thái PROCESSING/UNKNOWN và recovery policy.
- [ ] Có TTL/retention đủ cho retry horizon và business lifecycle.
- [ ] Có contract rõ cho 200/201/202/409/503 và lỗi terminal.

**Message và transaction**

- [ ] Producer có stable eventId và cơ chế outbox khi cần.
- [ ] Consumer lưu dedup marker theo logical consumer namespace.
- [ ] Marker và DB effect commit atomically trong một transaction.
- [ ] Ack/offset commit sau điểm business state bền vững.
- [ ] Chịu được redelivery, rebalance, publish retry và DLQ re-drive.
- [ ] Có cách xử lý out-of-order bằng version/state machine.
- [ ] Retention inbox phù hợp replay horizon và business uniqueness.
- [ ] Replay không tạo external side effects thật ngoài ý muốn.

**Concurrent operations**

- [ ] Hai requests cùng key chạy đồng thời không tạo effect đôi.
- [ ] Hai intents khác nhau cạnh tranh resource dùng constraint/lock/CAS đúng.
- [ ] Worker lease có owner/version/fencing khi cần.
- [ ] Không chỉ dùng mutex trong RAM cho service nhiều replica.
- [ ] Retry không làm tăng trạng thái cũ hoặc ghi đè version mới.

**External providers**

- [ ] External operation có stable reference/idempotency key.
- [ ] Timeout không bị coi là FAILED khi kết quả có thể đã thành công.
- [ ] Có lookup/reconciliation cho trạng thái UNKNOWN.
- [ ] Có cách phát hiện duplicate external effects thực.
- [ ] Có manual escalation nếu không thể xác minh an toàn.
- [ ] Có audit và approval cho việc điều chỉnh tiền/quyền/hàng hóa.

**Vận hành và kiểm thử**

- [ ] Metrics phân biệt duplicate message và duplicate business effect.
- [ ] Tracing gắn operation ID, event ID, attempt ID và correlation ID.
- [ ] Test crash trước/sau commit, trước/sau publish, trước/sau ack.
- [ ] Test same-key race, mismatch fingerprint, key expiry và replay.
- [ ] Test provider success + lost response, callback đến muộn, double-charge.
- [ ] Có runbook xử lý PROCESSING stuck, dedup conflict và UNKNOWN outcome.
- [ ] Dashboard/SLO ưu tiên tác dụng nghiệp vụ đúng, không chỉ transport success.

## 33. Tổng kết

**Idempotency** là đặc tính của một thao tác và những tác dụng được nó tạo ra khi lặp lại. **Deduplication** là cơ chế nhận diện bản sao để không xử lý lại cùng một identity. **Exactly-once** là cam kết một tác dụng chỉ được commit đúng một lần **trong phạm vi xác định**, không phải bảo đảm mặc định cho mọi thành phần chỉ vì broker có chế độ giao nhận đặc biệt.

Trong thực tế, hệ thống đáng tin cậy thường **chấp nhận message/request có thể lặp**, rồi bảo vệ tác dụng bằng nhiều ranh giới:

- Client và API dùng stable idempotency key cho cùng một business intent.
- Database dùng unique constraint, transaction và state machine để bảo vệ bất biến.
- Producer dùng outbox và stable event ID để chịu được publish retry.
- Consumer dùng inbox/dedup marker cùng business effect trong một transaction, sau đó mới ack.
- Worker concurrency dùng version/fencing nếu lease có thể chồng nhau.
- External API dùng provider idempotency key, status lookup và reconciliation; nếu không có những hỗ trợ ấy, giới hạn exactly-once phải được ghi nhận.
- Các tiến trình dài và lỗi mơ hồ có đường phục hồi, báo động và xử lý thủ công có owner.

**Bài học cốt lõi:** đừng cố chứng minh một request “chỉ đến một lần”. Hãy thiết kế để request có thể đến nhiều lần, nhưng mỗi **ý định nghiệp vụ hợp lệ** chỉ tạo những **tác dụng được phép** và kết quả luôn có thể được nhận diện, xác minh, phục hồi.
