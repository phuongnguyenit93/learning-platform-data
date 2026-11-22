# Kiểm tra hợp đồng của message và sự kiện bất đồng bộ

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, các hệ thống giao tiếp với nhau không chỉ qua lời gọi API đồng bộ. Nhiều kiến trúc dùng message broker, hàng đợi hoặc cơ chế phát sự kiện để các thành phần trao đổi thông tin mà không cần chờ bên nhận xử lý ngay. Cách giao tiếp này giảm phụ thuộc thời gian giữa các bên, nhưng cũng tạo ra rủi ro về schema, phiên bản, định tuyến, thứ tự, gửi lặp, retry và xử lý lỗi.

**Kiểm tra hợp đồng message và sự kiện bất đồng bộ** (message/event contract testing) xác nhận bên phát và bên nhận thống nhất về cấu trúc, ý nghĩa và quy tắc trao đổi thông điệp. Hợp đồng cần mô tả đủ để producer tạo message mà consumer có thể hiểu và xử lý; đồng thời consumer phải biết cách phản ứng với message hợp lệ, không hợp lệ, trùng lặp, đến trễ hoặc không tương thích.

Kiểm tra hợp đồng giúp phát hiện sai lệch giữa các bên sớm hơn, trước khi lỗi xuất hiện trong một quy trình xuyên hệ thống. Tuy nhiên, hợp đồng hợp lệ không tự chứng minh broker, mạng, cấu hình triển khai hoặc toàn bộ quy trình nghiệp vụ vận hành đúng. Vì vậy, contract test cần được kết hợp với kiểm thử tích hợp, kiểm thử lỗi và kiểm tra vận hành theo mức rủi ro.

## 1. Message và event trong giao tiếp bất đồng bộ

Trong giao tiếp bất đồng bộ, bên gửi thường ghi message vào broker hoặc một kênh trung gian. Consumer nhận message vào thời điểm sau đó, có thể ngay lập tức hoặc sau một khoảng trễ. Producer không cần chờ consumer hoàn tất xử lý để tiếp tục công việc.

Hai thuật ngữ thường gặp:

- **Message (thông điệp):** một đơn vị dữ liệu được gửi đến một hoặc nhiều bên nhận để yêu cầu hành động, truyền dữ liệu hoặc thông báo điều gì đó. Message có thể mang lệnh, yêu cầu, phản hồi hoặc sự kiện.
- **Event (sự kiện):** bản ghi cho biết một điều đã xảy ra trong miền nghiệp vụ, thường được diễn đạt ở thì quá khứ, chẳng hạn `OrderPlaced` hoặc `PaymentCaptured`. Event mô tả sự thật đã xảy ra; consumer quyết định phản ứng theo nhu cầu của mình.

Trong thực tế, event thường được truyền dưới dạng message qua broker. Tuy nhiên, không phải mọi message đều là event. Ví dụ, `ReserveInventory` có thể là một command yêu cầu thực hiện hành động, trong khi `InventoryReserved` là event thông báo việc giữ hàng đã hoàn tất.

### Các thành phần trong một luồng message

Một luồng điển hình gồm:

1. **Producer:** tạo và gửi message hoặc event.
2. **Broker hoặc transport:** tiếp nhận, lưu tạm, định tuyến và chuyển message theo cấu hình.
3. **Topic, queue hoặc channel:** nơi message được công bố hoặc lưu chờ consumer.
4. **Consumer:** nhận và xử lý message.
5. **Schema hoặc contract:** quy định cấu trúc, kiểu dữ liệu, trường bắt buộc, ý nghĩa và các quy tắc tương thích.
6. **Dead-letter queue (DLQ):** nơi lưu message không thể xử lý sau chính sách retry hoặc theo quy tắc định tuyến.

```text
Producer
   |
   | publish message/event
   v
Broker / Topic / Queue
   |
   +------> Consumer A
   |
   +------> Consumer B
   |
   +------> Consumer C
              |
              +---- lỗi quá số lần retry ----> Dead-letter queue
```

Tùy nền tảng, broker có thể dùng topic và subscription, queue cạnh tranh, partition hoặc routing key. Các chi tiết này ảnh hưởng đến khả năng phân phối, thứ tự, số lần nhận và phạm vi kiểm thử.

## 2. Hợp đồng message cần quy định những gì?

Hợp đồng không chỉ là một JSON schema. Nó cần mô tả cấu trúc dữ liệu và các quy tắc trao đổi để producer, broker và consumer hiểu giống nhau.

### Envelope và metadata

Envelope là lớp bao quanh payload, chứa thông tin định danh và điều khiển message. Những trường thường gặp:

- `messageId` hoặc `eventId`: định danh duy nhất của message/event.
- `eventType` hoặc `messageType`: loại message, chẳng hạn `OrderPlaced`.
- `occurredAt`: thời điểm sự kiện xảy ra; có thể khác thời điểm broker nhận hoặc consumer xử lý.
- `schemaVersion`: phiên bản schema hoặc contract.
- `producer` hoặc `source`: hệ thống phát message.
- `correlationId`: mã liên kết các bước thuộc cùng một quy trình.
- `causationId`: định danh message hoặc hành động gây ra message hiện tại.
- `contentType`: định dạng payload, ví dụ `application/json` hoặc định dạng nhị phân.
- `partitionKey`, `routingKey` hoặc key tương đương: thông tin dùng để định tuyến hoặc giữ thứ tự theo nhóm.

Không phải nền tảng nào cũng sử dụng cùng tên trường. Hợp đồng phải nêu tên, kiểu, định dạng, ý nghĩa, tính bắt buộc và quy tắc sinh giá trị của từng metadata.

### Payload và schema

Payload chứa dữ liệu nghiệp vụ. Hợp đồng cần xác định:

- Trường bắt buộc và tùy chọn.
- Kiểu dữ liệu, định dạng, đơn vị và miền giá trị.
- Ý nghĩa nghiệp vụ và quan hệ giữa các trường.
- Quy tắc null, trường vắng mặt và giá trị mặc định.
- Định dạng thời gian, múi giờ, tiền tệ và số thập phân.
- Quy tắc mã hóa, giới hạn kích thước và dữ liệu nhạy cảm.
- Quy tắc tương thích khi thêm, bỏ hoặc thay đổi trường.

Ví dụ, trường `amount` cần nêu rõ là số tiền theo đơn vị nhỏ nhất hay số thập phân, trường `currency` dùng mã tiền tệ nào và thời điểm `occurredAt` dùng UTC hay có offset. Nếu không có các định nghĩa này, hai hệ thống có thể đọc cùng một message nhưng diễn giải khác nhau.

### Quy tắc vận hành và ngữ nghĩa

Ngoài cấu trúc, hợp đồng cần nêu các quy tắc ảnh hưởng đến xử lý:

- Topic, queue, subscription hoặc routing key được sử dụng.
- Producer nào có quyền phát loại message đó và consumer nào được phép nhận.
- Delivery semantics được cam kết hoặc giả định: at-most-once, at-least-once hoặc cơ chế khác.
- Thứ tự message có được bảo đảm hay chỉ trong một partition/key.
- Chính sách retry, backoff, timeout, poison message và DLQ.
- Quy tắc idempotency và cách consumer xử lý message trùng.
- Điều kiện xác nhận message (acknowledgement) và thời điểm được coi là xử lý hoàn tất.
- Chính sách lưu giữ, replay, retention và khả năng xử lý message cũ.
- Quy tắc bảo mật, phân quyền, mã hóa và kiểm toán.

Hợp đồng tốt giúp các bên thống nhất cả “message trông như thế nào” lẫn “khi nhận message thì phải hiểu và xử lý ra sao”.

## 3. Ví dụ một event contract

Giả sử hệ thống bán hàng phát sự kiện khi đơn hàng được tạo. Một payload JSON minh họa:

```json
{
  "eventId": "evt-8f31",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-16T08:30:00Z",
  "producer": "order-service",
  "correlationId": "checkout-2048",
  "payload": {
    "orderId": "ord-2048",
    "customerId": "cus-105",
    "totalAmountMinor": 259900,
    "currency": "VND",
    "items": [
      {
        "productId": "prd-17",
        "quantity": 2
      }
    ]
  }
}
```

Một contract tương ứng cần giải thích rõ:

- `eventId` là duy nhất cho mỗi sự kiện logic và được dùng để nhận diện message trùng.
- `eventType` xác định sự kiện; consumer không nên suy đoán loại message chỉ từ tên topic.
- `schemaVersion` xác định phiên bản cấu trúc payload.
- `occurredAt` là thời điểm đơn được tạo theo UTC, không phải thời điểm consumer nhận message.
- `totalAmountMinor` là tổng tiền theo đơn vị nhỏ nhất của tiền tệ; consumer phải dùng `currency` để diễn giải.
- `items` chứa ít nhất một dòng hàng; `quantity` là số nguyên dương theo quy tắc nghiệp vụ.
- Consumer có thể nhận cùng `eventId` nhiều lần và phải xử lý idempotent.

Ví dụ chỉ minh họa cách tổ chức event. Hệ thống thực tế cần xác định chính xác quy tắc định danh, quyền riêng tư, đơn vị tiền tệ và schema theo miền nghiệp vụ.

## 4. Kiểm tra hợp đồng ở cả producer và consumer

Contract testing cần xem xét hai phía vì mỗi phía có thể vi phạm hợp đồng theo cách khác nhau.

### Kiểm tra producer

Mục tiêu là xác nhận producer tạo message tuân thủ schema và ngữ nghĩa đã công bố. Các kiểm tra có thể gồm:

- Message có đúng `eventType`, `schemaVersion` và content type không?
- Trường bắt buộc có mặt, đúng kiểu và đúng định dạng không?
- Giá trị có nằm trong miền hợp lệ và tuân thủ quy tắc nghiệp vụ không?
- Metadata như event ID, correlation ID, partition key có được tạo đúng không?
- Producer có phát message vào đúng topic hoặc routing key không?
- Một giao dịch chỉ phát event khi điều kiện nghiệp vụ tương ứng được thỏa mãn không?
- Nếu thao tác lưu dữ liệu thành công nhưng publish thất bại, hệ thống có cơ chế bảo đảm hoặc khôi phục phù hợp không?

Producer test có thể dùng schema validator, serializer thật, broker test hoặc adapter được kiểm soát. Với các luồng quan trọng, cần kiểm tra rằng event phản ánh trạng thái đã commit, tránh phát thông báo về một giao dịch sau đó bị rollback.

### Kiểm tra consumer

Mục tiêu là xác nhận consumer có thể đọc và xử lý các message nằm trong hợp đồng mà producer được phép phát. Các kiểm tra có thể gồm:

- Consumer deserialize được payload hợp lệ của phiên bản được hỗ trợ không?
- Consumer xử lý đúng trường bắt buộc, trường tùy chọn và giá trị mặc định không?
- Message có trường mới mà consumer chưa biết được xử lý theo chính sách không?
- Message thiếu trường, sai kiểu hoặc có giá trị không hợp lệ được từ chối, cách ly hoặc đưa vào DLQ đúng không?
- Consumer xử lý trùng lặp, đến trễ và sai thứ tự ra sao?
- Consumer chỉ ack sau khi hoàn tất công việc theo cam kết không?
- Khi xử lý thất bại, retry có giới hạn và không gây tác dụng phụ trùng không?

Consumer test nên bao gồm message mẫu từ các phiên bản producer còn được hỗ trợ, không chỉ payload mới nhất do nhóm tự tạo. Điều này giúp phát hiện lỗi khi dữ liệu cũ vẫn còn trong broker hoặc được replay.

### Kiểm tra hợp đồng giữa producer và consumer

Khi có thể, dùng contract test để xác minh producer và consumer tương thích với cùng một hợp đồng được quản lý. Có thể kiểm tra producer tạo message mà consumer hiểu được, hoặc consumer khai báo các message/schema mà nó chấp nhận và provider xác minh khả năng đáp ứng.

Hợp đồng có thể được lưu trong schema registry, repository đặc tả hoặc kho quản lý API/event. Cần có quy trình review, versioning, phê duyệt thay đổi và kiểm tra tương thích trước khi triển khai producer hoặc consumer mới.

## 5. Kiểm tra khả năng tương thích schema và tiến hóa phiên bản

Producer và consumer thường được triển khai độc lập. Một consumer cũ có thể vẫn đang chạy khi producer mới bắt đầu phát message; hoặc message cũ có thể còn tồn tại trong queue nhiều giờ trước khi được xử lý. Vì vậy, thay đổi schema phải xét cả các phiên bản đang chạy lẫn dữ liệu đã phát.

### Các kiểu tương thích thường gặp

| Kiểu tương thích | Ý nghĩa khái quát | Ví dụ thay đổi thường an toàn hơn |
|---|---|---|
| Backward compatibility | Consumer mới có thể đọc dữ liệu được tạo theo schema cũ | Thêm trường tùy chọn có cách xử lý mặc định rõ ràng |
| Forward compatibility | Consumer cũ có thể đọc dữ liệu theo schema mới | Producer thêm trường mà consumer cũ bỏ qua được |
| Full compatibility | Đáp ứng cả backward và forward compatibility theo quy tắc của registry | Thay đổi được thiết kế để hai thế hệ producer/consumer cùng tương tác |

Tên gọi và thuật toán kiểm tra tương thích có thể khác nhau giữa JSON Schema, Avro, Protobuf hoặc nền tảng quản lý schema. Cần xác nhận quy tắc cụ thể mà công cụ và tổ chức đang áp dụng; không nên mặc định một thay đổi luôn tương thích chỉ vì trường mới được đánh dấu optional.

### Thay đổi thường ít rủi ro hơn

- Thêm trường tùy chọn khi consumer cũ có thể bỏ qua và consumer mới có xử lý trường vắng mặt.
- Thêm một giá trị enum chỉ khi consumer cũ có chiến lược xử lý giá trị chưa biết.
- Bổ sung event type mới mà không thay đổi ý nghĩa của event cũ.
- Thêm metadata không bắt buộc và không làm thay đổi routing hoặc bảo mật.

Ngay cả những thay đổi này cũng cần kiểm tra theo công cụ, ngôn ngữ và cách deserialize thực tế. Một số consumer có thể từ chối trường lạ hoặc enum không nhận diện.

### Thay đổi có nguy cơ phá vỡ tương thích

- Đổi tên hoặc xóa trường đang được consumer sử dụng.
- Đổi kiểu dữ liệu, đơn vị, định dạng hoặc ý nghĩa của trường.
- Chuyển trường tùy chọn thành bắt buộc mà không có giai đoạn chuyển đổi.
- Đổi tên event, topic, routing key hoặc quy tắc phân vùng.
- Thay đổi ý nghĩa nghiệp vụ nhưng giữ nguyên tên và kiểu trường.
- Thay đổi thứ tự hoặc quy tắc phát message mà consumer đang phụ thuộc.

Đổi `amount` từ đơn vị đồng sang đơn vị nghìn đồng nhưng vẫn giữ kiểu số nguyên là thay đổi ngữ nghĩa có thể gây lỗi nghiêm trọng dù schema validator vẫn pass. Contract test cần kiểm tra cả ý nghĩa và đơn vị, không chỉ cấu trúc.

### Chiến lược triển khai thay đổi

Với thay đổi có nguy cơ phá vỡ, có thể dùng quy trình mở rộng rồi thu hẹp:

1. Mở rộng schema bằng trường mới hoặc event version mới, giữ khả năng đọc dữ liệu cũ.
2. Triển khai consumer có thể đọc cả định dạng cũ và mới.
3. Chuyển producer sang phát định dạng mới sau khi consumer đã sẵn sàng.
4. Theo dõi message lỗi, tỷ lệ xử lý và khả năng tương thích trong thời gian chuyển đổi.
5. Chỉ ngừng phát định dạng cũ và xóa hỗ trợ cũ khi không còn consumer hoặc message tồn đọng cần nó.

Nếu dùng event version mới, cần xác định liệu version nằm trong tên event, metadata hay schema subject, và cách định tuyến consumer. Không nên tạo version mới chỉ để né việc quản lý tương thích; version cần phản ánh thay đổi có ý nghĩa và có chính sách vòng đời.

## 6. Kiểm tra delivery semantics, trùng lặp và thứ tự

Hợp đồng bất đồng bộ cần nêu rõ cách message được giao và những điều consumer phải giả định.

### At-most-once, at-least-once và exactly-once

- **At-most-once:** message được giao không quá một lần, nhưng có thể bị mất nếu lỗi xảy ra ở thời điểm không thuận lợi.
- **At-least-once:** message có thể được giao lại cho đến khi được xác nhận; consumer phải chấp nhận khả năng nhận trùng.
- **Exactly-once:** một số nền tảng cung cấp bảo đảm xử lý hoặc ghi nhận đúng một lần trong phạm vi và điều kiện nhất định. Không nên hiểu đây là bảo đảm tuyệt đối cho mọi tác dụng phụ bên ngoài broker hoặc mọi hệ thống tích hợp.

Trong nhiều hệ thống thực tế, at-least-once kết hợp với xử lý idempotent là lựa chọn phổ biến. Hợp đồng cần nêu rõ phạm vi bảo đảm, thời hạn lưu message và cách xử lý khi consumer xử lý thành công nhưng ack bị mất.

### Idempotency và xử lý message trùng

Consumer có thể nhận lại cùng message do timeout, retry, redelivery hoặc broker khôi phục sau sự cố. Idempotency bảo đảm việc xử lý lặp cùng một message không tạo thêm tác dụng phụ ngoài ý muốn.

Một cách thường dùng là lưu `eventId` đã xử lý trong cùng ranh giới giao dịch với thay đổi nghiệp vụ. Khi nhận lại event ID đó, consumer phát hiện đã xử lý và không lặp lại tác dụng phụ. Nếu thao tác gồm nhiều hệ thống, cần thiết kế idempotency key, outbox/inbox hoặc cơ chế đối soát phù hợp.

Test nên gửi cùng message nhiều lần, bao gồm trường hợp hai bản sao đến đồng thời, rồi xác minh dữ liệu và tác dụng phụ chỉ xuất hiện theo quy tắc đã định. Chỉ kiểm tra số lần gọi handler là chưa đủ; cần kiểm tra trạng thái lưu trữ, giao dịch và thông báo phát sinh tiếp theo.

### Thứ tự message

Không phải broker nào cũng bảo đảm thứ tự toàn cục. Một số nền tảng chỉ bảo đảm thứ tự trong một queue, partition hoặc theo cùng một key. Nếu consumer cần xử lý theo thứ tự, hợp đồng phải chỉ rõ phạm vi bảo đảm và cách phát hiện sự kiện cũ.

Ví dụ, một đơn hàng phát `OrderCreated`, `OrderPaid` và `OrderCancelled`. Nếu `OrderCancelled` đến trước `OrderPaid`, consumer không được tự động đưa đơn về trạng thái đã thanh toán chỉ vì event đến sau. Có thể dùng sequence number, aggregate version hoặc quy tắc chuyển trạng thái để phát hiện và xử lý sự kiện sai thứ tự.

Test nên bao gồm message đúng thứ tự, đảo thứ tự, đến trễ, thiếu một sự kiện và hai sự kiện đồng thời. Kết quả mong đợi phải phù hợp với mô hình trạng thái nghiệp vụ.

## 7. Kiểm tra retry, acknowledgement và dead-letter queue

Retry giúp xử lý lỗi tạm thời, nhưng cấu hình sai có thể tạo vòng lặp vô hạn, gây quá tải hoặc làm message trùng tác dụng phụ.

### Retry có kiểm soát

Hợp đồng và cấu hình cần xác định:

- Loại lỗi nào có thể retry, loại lỗi nào cần từ chối ngay.
- Số lần retry tối đa và khoảng chờ giữa các lần.
- Backoff cố định hay tăng dần, có jitter hay không.
- Thời hạn tối đa message được giữ để thử lại.
- Cách tránh retry đồng loạt gây tăng tải (retry storm).
- Consumer xử lý thế nào khi lỗi vẫn tồn tại sau lần thử cuối.

Lỗi mạng tạm thời có thể retry; payload sai schema thường không tự hết lỗi nếu gửi lại nguyên trạng. Phân loại lỗi giúp tránh tiêu tốn tài nguyên cho message không thể xử lý.

### Acknowledgement và tính nguyên tử

Nếu consumer ack trước khi lưu kết quả nghiệp vụ, message có thể bị mất khỏi luồng xử lý khi ứng dụng gặp sự cố ngay sau đó. Nếu consumer lưu kết quả rồi bị lỗi trước ack, broker có thể giao lại và tạo xử lý trùng. Vì vậy, cần xác định ranh giới giữa xử lý nghiệp vụ và ack, cùng cơ chế idempotency hoặc transaction phù hợp.

Test nên mô phỏng lỗi ở các thời điểm: trước khi xử lý, giữa khi xử lý, sau khi commit nhưng trước ack và sau ack. Xác minh dữ liệu cuối cùng và số tác dụng phụ không vượt quy tắc.

### Dead-letter queue

DLQ lưu message không thể xử lý sau chính sách retry hoặc do quy tắc từ chối. Cần quy định:

- Điều kiện đưa message vào DLQ.
- Metadata và ngữ cảnh lỗi được giữ lại.
- Ai có quyền xem và xử lý message.
- Cách sửa dữ liệu hoặc phiên bản consumer trước khi replay.
- Quy tắc chống replay gây tác dụng phụ trùng.
- Thời hạn lưu và quy trình xóa an toàn.

Test nên xác minh message lỗi được đưa vào đúng DLQ, vẫn có thể truy vết bằng ID, có lý do lỗi hữu ích và có thể replay an toàn sau khi khắc phục. Không nên replay hàng loạt message khi chưa đánh giá tác động và tính idempotent.

## 8. Kiểm tra bảo mật và quyền riêng tư của message

Message có thể đi qua broker, lưu trữ trong thời gian dài hoặc được nhiều consumer nhận. Vì vậy, kiểm tra hợp đồng cần xem cả dữ liệu và quyền truy cập.

Những nội dung nên kiểm tra:

- Producer chỉ được publish vào topic hoặc queue được cấp quyền.
- Consumer chỉ được subscribe vào kênh cần thiết.
- Xác thực và phân quyền broker được cấu hình đúng.
- Dữ liệu nhạy cảm được giảm thiểu, mã hóa hoặc token hóa theo yêu cầu.
- Không ghi secret, token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết vào payload và log.
- Chữ ký hoặc cơ chế xác minh nguồn gốc được kiểm tra nếu message đến qua webhook hoặc kênh không hoàn toàn tin cậy.
- Retention, replay, DLQ và quyền quản trị tuân thủ chính sách.

Kiểm thử bảo mật không chỉ kiểm tra rằng consumer đọc được message hợp lệ. Cần thử truy cập trái phép, message giả mạo, payload quá lớn, trường dữ liệu độc hại và quyền replay. Kết quả phải xác nhận hệ thống từ chối hoặc cách ly đúng cách mà không làm lộ thông tin.

## 9. Quy trình xây dựng bộ contract test

Một quy trình thực tế có thể triển khai theo các bước sau:

### Bước 1: Xác định producer, consumer và luồng nghiệp vụ

Liệt kê ai phát message, ai nhận, topic/queue, loại event, trạng thái nghiệp vụ và hậu quả nếu message sai, mất hoặc bị xử lý trùng. Xác định consumer hiện tại và consumer có thể được thêm trong tương lai.

### Bước 2: Thu thập và chuẩn hóa hợp đồng

Chọn nguồn hợp đồng có kiểm soát phiên bản, ví dụ schema registry, JSON Schema, Avro, Protobuf hoặc đặc tả AsyncAPI. Ghi rõ metadata, payload, quy tắc ngữ nghĩa, delivery, thứ tự, retry, bảo mật và tương thích.

### Bước 3: Tạo bộ message mẫu

Chuẩn bị message hợp lệ, message ở biên, message phiên bản cũ, message có trường tùy chọn vắng mặt, message có trường chưa biết, payload sai kiểu và message lỗi nghiệp vụ. Dữ liệu mẫu không chứa thông tin nhạy cảm thật.

### Bước 4: Kiểm tra producer

Chạy producer với các tình huống nghiệp vụ và xác minh message được tạo đúng schema, metadata, topic và thời điểm phát. Nếu dùng outbox, xác minh bản ghi nghiệp vụ và outbox được commit nhất quán; publisher có thể gửi lại mà không làm mất sự kiện.

### Bước 5: Kiểm tra consumer

Phát message mẫu vào consumer hoặc harness kiểm thử. Xác minh deserialize, validation, xử lý nghiệp vụ, idempotency, trạng thái ack, retry và DLQ. Chạy cả message của các phiên bản còn được hỗ trợ.

### Bước 6: Kiểm tra tương thích giữa phiên bản

Đánh giá schema mới với consumer cũ và schema cũ với consumer mới theo chính sách tương thích. Thử các tổ hợp phiên bản thực tế có thể cùng tồn tại trong giai đoạn rollout.

### Bước 7: Kiểm tra tích hợp với broker và môi trường đại diện

Dùng broker thật hoặc môi trường tích hợp phù hợp để xác minh routing, quyền, partition, retention, retry, ack, DLQ và hành vi khi broker mất kết nối. Contract test thuần schema không thay thế bước này.

### Bước 8: Đưa kiểm tra vào pipeline và quản lý thay đổi

Chạy schema validation và contract compatibility khi hợp đồng hoặc producer/consumer thay đổi. Yêu cầu review khi có thay đổi phá vỡ tương thích, lưu báo cáo và chỉ triển khai khi các consumer liên quan đã sẵn sàng.

## 10. Ví dụ xuyên suốt: sự kiện thanh toán và cập nhật đơn hàng

Giả sử Payment Service phát `PaymentCaptured` sau khi cổng thanh toán xác nhận đã thu tiền. Order Service nhận event và chuyển đơn sang trạng thái đã thanh toán; Notification Service nhận cùng event để gửi thông báo cho khách hàng.

### Hợp đồng nghiệp vụ

Event có thể gồm `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `paymentId`, `orderId`, `amountMinor`, `currency`, `paymentMethod` và `correlationId`. Hợp đồng quy định:

- Event chỉ được phát sau khi giao dịch thanh toán đã được xác nhận và trạng thái đã commit theo thiết kế.
- `eventId` là duy nhất và ổn định khi cùng một event được gửi lại.
- `amountMinor` dùng đơn vị tiền tệ nhỏ nhất; `currency` là mã tiền tệ chuẩn.
- `orderId` tham chiếu đến đơn hàng liên quan.
- Consumer có thể nhận event nhiều lần và phải xử lý idempotent.
- Event có thể đến trễ; consumer phải kiểm tra trạng thái hiện tại và quy tắc chuyển trạng thái.

### Các bài kiểm tra cần có

| Mục tiêu | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Producer tuân thủ schema | Thanh toán thành công và tạo event | Đủ trường bắt buộc, đúng kiểu, đơn vị và event type |
| Consumer đọc schema | Phát event phiên bản đang hỗ trợ | Deserialize và xử lý đúng dữ liệu |
| Tương thích phiên bản | Consumer mới nhận event cũ; consumer cũ nhận event mới có trường tùy chọn | Hành vi đúng theo chính sách compatibility |
| Idempotency | Gửi cùng `eventId` hai hoặc nhiều lần | Đơn chỉ chuyển trạng thái một lần, không gửi thông báo trùng theo chính sách |
| Thứ tự | `PaymentCaptured` đến sau `PaymentRefunded` hoặc event trạng thái cũ đến trễ | Không làm trạng thái đơn quay ngược trái quy tắc |
| Retry và ack | Consumer lỗi sau commit nhưng trước ack | Redelivery không tạo tác dụng phụ trùng |
| DLQ | Payload sai schema hoặc lỗi không thể retry | Message được cách ly, lưu ngữ cảnh và có thể điều tra |
| Bảo mật | Producer không có quyền publish hoặc message giả mạo | Bị từ chối, không cập nhật đơn |

### Phân tích một lỗi có thể xảy ra

Payment Service lưu giao dịch thành công nhưng ứng dụng gặp sự cố trước khi publish event. Nếu không có cơ chế bảo đảm, Order Service không bao giờ nhận được thông báo và đơn hàng vẫn ở trạng thái chờ thanh toán. Một cách xử lý thường dùng là transactional outbox: lưu thay đổi nghiệp vụ và bản ghi outbox trong cùng giao dịch; một publisher riêng đọc outbox và gửi event. Publisher có thể gửi lại nếu không chắc broker đã nhận, vì vậy consumer vẫn cần idempotency.

Contract test xác nhận cấu trúc và ý nghĩa event; kiểm thử tích hợp xác nhận outbox, broker và consumer phối hợp đúng; kiểm thử lỗi xác nhận hệ thống phục hồi sau khi publish hoặc ack bị gián đoạn. Các lớp bằng chứng này bổ sung cho nhau.

## 11. Tiêu chí hoàn tất và bằng chứng cần lưu

Một bộ kiểm tra hợp đồng có thể được xem là đủ cho phạm vi đã xác định khi:

- Schema và ngữ nghĩa của message được quản lý phiên bản, có chủ sở hữu và được review.
- Producer tạo đúng message, metadata, định tuyến và thời điểm phát theo hợp đồng.
- Consumer đọc được các phiên bản còn hỗ trợ và xử lý đúng message hợp lệ.
- Message không hợp lệ, trường lạ, giá trị biên và lỗi nghiệp vụ được xử lý theo chính sách.
- Tương thích schema được kiểm tra trước khi triển khai thay đổi.
- Delivery, thứ tự, trùng lặp, retry, ack và DLQ được kiểm tra theo rủi ro.
- Quyền truy cập, bảo mật và quyền riêng tư của payload được xem xét.
- Giới hạn môi trường, broker giả lập và tình huống chưa kiểm tra được ghi nhận.

Bằng chứng nên lưu gồm phiên bản schema, phiên bản producer/consumer, message mẫu đã ẩn dữ liệu nhạy cảm, kết quả validation, kết quả contract test, cấu hình broker liên quan, log/trace, mã build và các ngoại lệ đã được phê duyệt.

Không nên kết luận “hợp đồng đạt” chỉ từ việc JSON parse thành công. Parse chỉ chứng minh dữ liệu có cú pháp hợp lệ; nó không chứng minh trường có đúng ý nghĩa, consumer xử lý đúng, event được phát đúng thời điểm hoặc hệ thống chịu được redelivery.

## 12. Những sai lầm thường gặp

**Chỉ kiểm tra schema mà bỏ qua ngữ nghĩa.** Hai trường có cùng kiểu số vẫn có thể khác đơn vị hoặc ý nghĩa. Hợp đồng cần định nghĩa rõ miền giá trị, đơn vị và quy tắc nghiệp vụ.

**Chỉ kiểm tra producer hoặc chỉ kiểm tra consumer.** Producer có thể phát payload hợp lệ nhưng consumer không hỗ trợ phiên bản; consumer có thể đọc được ví dụ do nhóm tạo nhưng producer thực tế lại phát thiếu trường. Cần bằng chứng cho cả hai phía.

**Giả định message chỉ được giao một lần.** Nhiều broker và cấu hình thực tế có thể redeliver. Consumer cần idempotency và test gửi lặp, kể cả gửi đồng thời.

**Coi thứ tự toàn cục là mặc định.** Bảo đảm thứ tự thường có phạm vi giới hạn. Cần nêu rõ partition/key và kiểm tra sự kiện sai thứ tự hoặc đến trễ.

**Thay đổi schema mà không kiểm tra phiên bản đang chạy.** Producer và consumer có thể được rollout ở thời điểm khác nhau; queue còn có thể chứa message cũ. Cần kiểm tra tổ hợp phiên bản trong giai đoạn chuyển đổi.

**Retry mọi lỗi.** Payload sai hoặc lỗi nghiệp vụ vĩnh viễn không tự hết khi gửi lại. Phân loại lỗi, giới hạn retry và sử dụng DLQ để tránh vòng lặp vô hạn.

**Ack quá sớm.** Consumer có thể xác nhận message trước khi lưu kết quả, dẫn đến mất công việc khi gặp sự cố. Cần xác định ranh giới xử lý và ack, đồng thời kiểm tra lỗi ở các thời điểm khác nhau.

**Coi contract test thay thế kiểm thử broker và tích hợp.** Contract test không chứng minh cấu hình topic, quyền, mạng, retention, retry hoặc DLQ hoạt động đúng. Cần kiểm tra các phần này trong môi trường phù hợp.

**Replay DLQ mà không đánh giá tác dụng phụ.** Message cũ có thể làm thay đổi trạng thái hoặc phát sinh thông báo lặp. Cần sửa nguyên nhân, kiểm tra idempotency và đánh giá phạm vi trước khi replay.

## 13. Checklist kiểm tra hợp đồng message và event

Khi định nghĩa hợp đồng:

- [ ] Producer, consumer, topic/queue và mục đích nghiệp vụ đã được xác định.
- [ ] Envelope, metadata, payload, schema, đơn vị và ngữ nghĩa được mô tả rõ.
- [ ] Trường bắt buộc/tùy chọn, null, giá trị mặc định và miền hợp lệ đã được xác định.
- [ ] Phiên bản schema và chính sách backward/forward/full compatibility đã rõ.
- [ ] Delivery semantics, thứ tự, idempotency, retry, ack và DLQ được quy định.
- [ ] Quyền truy cập, dữ liệu nhạy cảm, retention và replay tuân thủ chính sách.

Khi kiểm thử:

- [ ] Producer được kiểm tra về schema, metadata, routing và thời điểm phát.
- [ ] Consumer được kiểm tra với message hợp lệ, không hợp lệ và phiên bản cũ.
- [ ] Có test message trùng, đến trễ, sai thứ tự, retry và lỗi trước/sau ack.
- [ ] Có kiểm tra tương thích giữa các tổ hợp producer/consumer có thể cùng tồn tại.
- [ ] Broker, quyền, topic/queue, partition, retention và DLQ được kiểm tra trong môi trường phù hợp.
- [ ] Test dữ liệu không làm lộ thông tin thật và có thể tái lập.

Trước khi triển khai thay đổi:

- [ ] Contract/schema change đã được review và kiểm tra compatibility trong pipeline.
- [ ] Consumer liên quan đã sẵn sàng trước khi producer phát định dạng mới.
- [ ] Kế hoạch rollout, theo dõi, rollback hoặc roll-forward đã được xác định.
- [ ] Bằng chứng, giới hạn và rủi ro tồn dư được lưu lại.

## 14. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Producer thêm trường tùy chọn `salesChannel` vào event. Consumer cũ bỏ qua trường lạ, consumer mới đọc trường nếu có và vẫn xử lý message cũ khi trường vắng mặt. Đây có thể là thay đổi tương thích, nhưng cần chạy kiểm tra theo schema format và chính sách registry đang dùng.

**Tình huống 2:** Consumer lưu đơn hàng đã thanh toán rồi gặp lỗi trước khi ack. Broker giao lại event. Consumer cần nhận ra `eventId` đã được xử lý hoặc dùng cơ chế tương đương để không tạo đơn hay thông báo trùng.

**Tình huống 3:** Event `OrderCancelled` đến trước `OrderPaid`. Consumer không nên chỉ áp dụng event theo thứ tự nhận. Cần dùng trạng thái hiện tại, sequence/version hoặc quy tắc nghiệp vụ để xử lý sự kiện cũ và sai thứ tự.

**Tình huống 4:** Schema validator pass nhưng consumer hiểu `amount` là đồng trong khi producer gửi số tiền theo đơn vị nhỏ nhất. Đây là lỗi ngữ nghĩa mà kiểm tra cú pháp không phát hiện. Hợp đồng cần định nghĩa đơn vị và test giá trị cụ thể.

**Tình huống 5:** Message sai schema bị retry liên tục và làm hàng đợi chậm. Nhóm cần phân loại đây là lỗi không thể tự hết, giới hạn retry, đưa message vào DLQ cùng ngữ cảnh và tạo quy trình điều tra/replay sau khi khắc phục.

Khi đánh giá một hợp đồng bất đồng bộ, hãy tự hỏi: **hai phía có hiểu cùng cấu trúc và ý nghĩa message không, các phiên bản có tương thích khi triển khai lệch thời điểm không, và hệ thống xử lý thế nào khi message bị lặp, trễ, sai thứ tự hoặc không thể xử lý?** Trả lời được những câu hỏi này giúp hợp đồng hỗ trợ giao tiếp ổn định trong suốt vòng đời của các producer và consumer.

## Kết luận

Kiểm tra hợp đồng message và sự kiện bất đồng bộ cần bao quát schema, metadata, ngữ nghĩa nghiệp vụ, phiên bản, delivery, thứ tự, idempotency, retry, acknowledgement, DLQ và bảo mật. Kiểm tra riêng producer và consumer giúp phát hiện lỗi ở từng phía; kiểm tra tương thích và tích hợp với broker giúp xác nhận các bên có thể phối hợp khi triển khai độc lập và khi xảy ra lỗi. Khi hợp đồng được quản lý phiên bản, kiểm tra tự động trong pipeline và bổ sung bằng chứng vận hành phù hợp, nhóm giảm nguy cơ lỗi giao tiếp lan sang các quy trình nghiệp vụ.
