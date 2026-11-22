# Giới hạn của tuyên bố xử lý đúng một lần khi có hệ thống bên ngoài

Một hệ thống hàng đợi có thể giao cùng một message nhiều lần. Consumer có thể đã xử lý xong nhưng bị mất kết nối trước khi gửi ACK; broker không biết kết quả nên giao lại. Ngược lại, consumer có thể gửi ACK trước khi commit dữ liệu, rồi bị dừng giữa chừng khiến message đã được xác nhận nhưng thay đổi nghiệp vụ chưa được lưu.

Khi chỉ có một database, transaction và unique constraint có thể giúp bảo đảm một hiệu ứng nghiệp vụ chỉ được ghi một lần. Nhưng khi quy trình còn gọi payment gateway, gửi email, publish sang broker khác hoặc ghi vào một hệ thống bên ngoài, transaction của database không thể tự rollback những tác dụng phụ đã xảy ra ở nơi khác.

Vì vậy, cần phân biệt ba điều: message được giao bao nhiêu lần, đoạn xử lý được chạy bao nhiêu lần và hiệu ứng nghiệp vụ xuất hiện bao nhiêu lần. Một kiến trúc có thể giao message ít nhất một lần nhưng vẫn tạo hiệu ứng nghiệp vụ đúng một lần trong phạm vi được bảo vệ bằng idempotency. Phạm vi đó luôn có giới hạn và phải được thiết kế rõ.

## 1. “Đúng một lần” có thể nói về những điều khác nhau

Các thuật ngữ sau mô tả những cam kết khác nhau:

| Cách giao/ xử lý | Ý nghĩa | Rủi ro chính |
|---|---|---|
| At-most-once | Message được giao hoặc xử lý tối đa một lần; có thể mất message | ACK hoặc đánh dấu hoàn tất quá sớm làm mất công việc |
| At-least-once | Message sẽ được giao lại cho đến khi được xác nhận theo chính sách broker; có thể trùng | Consumer phải chịu được xử lý lặp |
| Exactly-once delivery | Message chỉ xuất hiện đúng một lần ở phía nhận | Khó bảo đảm qua lỗi mạng, crash và ranh giới hệ thống độc lập |
| Exactly-once processing | Logic xử lý được thực thi đúng một lần | Crash có thể khiến logic chạy lại dù lần trước đã tạo một phần hiệu ứng |
| Exactly-once effect | Kết quả nghiệp vụ quan sát được chỉ xuất hiện một lần | Cần phối hợp nguyên tử hoặc idempotency/deduplication ở nơi tạo hiệu ứng |

Trong thực tế, broker thường cung cấp at-least-once delivery hoặc một số cơ chế exactly-once trong phạm vi nội bộ của broker. Ứng dụng thường đạt hiệu ứng nghiệp vụ một lần bằng cách làm cho lần xử lý lặp trở nên an toàn.

Ví dụ, consumer nhận message `ChargeOrder(orderId=42)`. Broker có thể giao message này hai lần. Nếu lần đầu đã tạo khoản thu 100.000 đồng ở payment provider nhưng consumer crash trước ACK, lần thứ hai sẽ được giao lại. Nếu consumer gọi API thanh toán lần nữa mà không có idempotency key, khách hàng có thể bị trừ tiền hai lần.

## 2. Vì sao không thể chỉ dựa vào ACK?

ACK xác nhận với broker rằng consumer đã nhận hoặc xử lý message theo giao thức. ACK không tự động chứng minh mọi hệ thống bên ngoài đã hoàn tất hiệu ứng.

Giả sử consumer cập nhật database rồi ACK:

```text
Consumer nhận message
        |
        v
UPDATE database
        |
        v
COMMIT thành công
        |
        v
Gửi ACK cho broker
```

Nếu consumer crash sau `COMMIT` nhưng trước ACK, broker có thể giao lại message. Nếu consumer không lưu dấu vết message đã xử lý, nó sẽ cập nhật hoặc thực hiện nghiệp vụ lần nữa.

Đảo thứ tự cũng nguy hiểm:

```text
Consumer nhận message
        |
        v
Gửi ACK cho broker
        |
        v
Crash trước COMMIT
```

Broker đã xem message là hoàn tất và không giao lại, trong khi database chưa có thay đổi. Công việc có thể bị mất.

Với một database và broker độc lập, không có thứ tự ACK/COMMIT đơn giản nào loại bỏ cả hai cửa sổ lỗi. Cần một giao thức bổ sung như inbox, outbox, idempotency hoặc distributed transaction nếu mọi participant hỗ trợ.

## 3. Vấn đề dual-write: ghi database và gửi hệ thống bên ngoài

Một dual-write xảy ra khi ứng dụng cần thực hiện hai thay đổi ở hai hệ thống độc lập, ví dụ:

- Cập nhật đơn hàng trong database.
- Publish `OrderConfirmed` lên message broker.

Hai thao tác không nằm trong cùng một local transaction. Có hai thứ tự phổ biến, và mỗi thứ tự đều có cửa sổ lỗi.

### Ghi database trước, publish sau

```text
COMMIT order.status = CONFIRMED
        |
        v
Ứng dụng crash
        |
        v
Không publish OrderConfirmed
```

Database cho biết đơn hàng đã xác nhận nhưng consumer khác không bao giờ nhận được event. Trạng thái nghiệp vụ và message bị lệch nhau.

### Publish trước, ghi database sau

```text
Publish OrderConfirmed thành công
        |
        v
Ứng dụng crash
        |
        v
Không commit order.status = CONFIRMED
```

Consumer khác đã nhận event nhưng database nguồn chưa xác nhận đơn hàng. Nếu ứng dụng thử lại, event có thể được publish lần nữa.

Đây là vấn đề nhất quán giữa hai hệ thống. Chỉ dùng `try/catch`, retry hoặc ACK không tạo ra tính nguyên tử giữa hai nơi.

## 4. Transactional outbox giải quyết dual-write như thế nào?

Transactional outbox ghi thay đổi nghiệp vụ và sự kiện cần phát vào cùng một database transaction. Một tiến trình relay đọc bảng outbox rồi publish sự kiện ra broker.

Ví dụ schema:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);
```

Ứng dụng ghi cả hai trong một transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = 42;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload
)
VALUES (
    'evt-order-42-confirmed-v1',
    42,
    'OrderConfirmed',
    '{"orderId":42}'
);

COMMIT;
```

Nếu transaction rollback, cả thay đổi đơn hàng và outbox event đều không tồn tại. Nếu commit thành công, event được lưu bền vững cùng trạng thái nghiệp vụ. Relay có thể publish lại sau khi khởi động, nên không bỏ lỡ event chỉ vì ứng dụng crash giữa database commit và publish.

### Outbox relay vẫn có thể publish trùng

Giả sử relay thực hiện:

1. Đọc event chưa publish.
2. Publish event lên broker.
3. Đánh dấu `published_at` trong database.

Nếu broker đã nhận event nhưng relay crash trước bước 3, lần chạy sau sẽ publish lại event đó. Vì vậy, transactional outbox bảo đảm event được lưu cùng thay đổi nghiệp vụ và hỗ trợ giao ít nhất một lần; nó không tự bảo đảm broker chỉ nhận một bản.

Đánh dấu đã publish trước khi gửi cũng không an toàn: relay có thể crash sau khi đánh dấu nhưng trước khi broker nhận event, làm event bị mất. Thứ tự publish rồi đánh dấu thường chấp nhận duplicate để tránh mất event. Consumer phải có idempotency.

### Nhiều relay và thứ tự event

Nếu nhiều worker cùng đọc outbox, cần cơ chế claim event an toàn, ví dụ transaction ngắn với `FOR UPDATE SKIP LOCKED` ở database hỗ trợ. Không giữ transaction database mở trong khi chờ broker phản hồi lâu.

Nếu thứ tự event của cùng một aggregate quan trọng, cần lưu sequence/version và bảo đảm relay hoặc consumer xử lý theo thứ tự cần thiết. `ORDER BY created_at` đơn lẻ không đủ nếu nhiều worker publish song song hoặc timestamp trùng. Có thể dùng partition key theo aggregate, sequence number và cơ chế phát hiện event đến sai thứ tự.

## 5. Inbox và deduplication ở consumer

Outbox giúp producer không làm mất event, nhưng consumer vẫn có thể nhận cùng event nhiều lần. Inbox pattern lưu dấu message đã được xử lý trong cùng transaction với thay đổi nghiệp vụ của consumer.

Ví dụ:

```sql
CREATE TABLE inbox_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, message_id)
);
```

Consumer xử lý message theo một transaction:

```sql
BEGIN;

INSERT INTO inbox_messages (consumer_name, message_id)
VALUES ('billing-projection', 'evt-order-42-confirmed-v1');

-- Nếu INSERT thành công, áp dụng thay đổi nghiệp vụ.
UPDATE billing_projection
SET order_confirmed = TRUE
WHERE order_id = 42;

COMMIT;
```

Nếu message đã được xử lý, khóa chính inbox bị trùng. Consumer nhận ra duplicate và bỏ qua phần hiệu ứng nghiệp vụ tương ứng.

Điểm quyết định là ghi inbox và thay đổi dữ liệu nghiệp vụ phải cùng một database transaction. Nếu ghi inbox trước rồi commit riêng, consumer có thể crash sau khi đánh dấu nhưng trước khi cập nhật dữ liệu; message giao lại sẽ bị bỏ qua dù hiệu ứng chưa xảy ra. Nếu cập nhật nghiệp vụ trước rồi ghi inbox riêng, crash giữa hai thao tác có thể khiến hiệu ứng bị lặp.

### Thứ tự ACK và COMMIT

Với inbox pattern, thứ tự phổ biến là:

```text
Nhận message
     |
     v
BEGIN database transaction
     |
     v
INSERT inbox key (deduplicate)
     |
     v
Áp dụng thay đổi nghiệp vụ nếu key mới
     |
     v
COMMIT
     |
     v
ACK broker
```

Nếu crash sau commit nhưng trước ACK, broker giao lại message. Inbox key đã tồn tại nên consumer không lặp hiệu ứng; sau đó ACK bản giao lại. Nếu crash trước commit, cả inbox key và thay đổi nghiệp vụ rollback; message được giao lại và xử lý từ đầu.

Đây là cách đạt hiệu ứng một lần trong database consumer, trong khi delivery vẫn có thể là at-least-once.

## 6. Inbox không tự bảo vệ tác dụng phụ ở hệ thống khác

Giả sử consumer cần:

1. Ghi `inbox_messages` trong database.
2. Gửi email qua dịch vụ email bên ngoài.
3. Commit database.

Không thể đặt HTTP request gửi email vào cùng transaction ACID với database thông thường. Nếu email được gửi thành công rồi database rollback, message giao lại có thể gửi email lần nữa. Nếu database commit inbox trước rồi crash trước khi gửi email, lần giao lại sẽ bị bỏ qua và email không được gửi.

Tương tự, nếu consumer gọi payment API rồi mới ghi inbox, crash sau khi payment thành công có thể khiến lần giao lại thu tiền lần nữa. Nếu ghi inbox trước rồi gọi payment, crash sau commit inbox nhưng trước payment sẽ làm mất thao tác thanh toán.

Inbox chỉ bảo vệ các hiệu ứng nằm trong cùng transaction database. Đối với hệ thống bên ngoài, cần idempotency ở API đích, một outbox tiếp theo hoặc quy trình đối soát/compensation.

## 7. Idempotency key ở API bên ngoài

Một API hỗ trợ idempotency cho phép client gửi lại cùng một yêu cầu với cùng một key. Server nhận diện đó là cùng một thao tác và trả lại kết quả đã ghi nhận thay vì thực hiện hiệu ứng lần nữa.

Ví dụ:

```http
POST /payments
Idempotency-Key: order-42-charge-v1
Content-Type: application/json

{
  "orderId": 42,
  "amount": 100000,
  "currency": "VND"
}
```

Nếu client không nhận được phản hồi do timeout, nó gửi lại cùng request với key `order-42-charge-v1`. Nếu provider đã xử lý lần đầu, provider có thể trả lại kết quả cũ thay vì tạo khoản thanh toán mới.

### Key phải ổn định qua mọi lần retry

Idempotency key phải đại diện cho một ý định nghiệp vụ duy nhất, chẳng hạn “thu tiền lần đầu cho đơn hàng 42”. Không tạo key mới ở mỗi lần retry. Nếu mỗi lần retry dùng một key mới, provider sẽ coi đó là yêu cầu mới và có thể thực hiện nhiều khoản thu.

Không tái sử dụng một key cho hai payload khác nhau. Nhiều API từ chối key đã dùng với payload khác hoặc trả lại kết quả của request đầu tiên. Ứng dụng nên lưu key cùng loại thao tác, đối tượng nghiệp vụ, payload hash và trạng thái xử lý để phát hiện sử dụng sai.

### Phạm vi và thời hạn của key

Hành vi idempotency phụ thuộc hợp đồng của provider:

- Key có hiệu lực trong phạm vi tài khoản, endpoint hoặc loại thao tác nào?
- Provider lưu key trong bao lâu?
- Request cùng key nhưng payload khác được xử lý thế nào?
- Request đang xử lý đồng thời với key giống nhau trả kết quả gì?
- Có API tra cứu trạng thái bằng key hoặc payment reference không?
- Provider trả lại response ban đầu hay response hiện tại của tài nguyên?

Nếu provider chỉ giữ key trong 24 giờ, retry sau 3 ngày có thể không còn được deduplicate. Hệ thống cần biết thời hạn này và có quy trình tra cứu/đối soát trước khi gửi lại request đã quá hạn.

## 8. Cửa sổ lỗi khi gọi API ngoài

Một consumer gọi API thanh toán có thể gặp các trường hợp:

| Thời điểm crash/lỗi | Trạng thái có thể xảy ra | Cách xử lý |
|---|---|---|
| Trước khi gửi request | Provider chưa nhận yêu cầu | Có thể thử gửi với cùng idempotency key |
| Request đã gửi nhưng chưa biết provider nhận chưa | Kết quả không xác định | Gửi lại cùng key nếu provider bảo đảm idempotency |
| Provider xử lý thành công nhưng response bị mất | Hiệu ứng đã xảy ra, client không biết | Tra cứu bằng key/reference hoặc gửi lại cùng key theo hợp đồng provider |
| Nhận response thành công nhưng crash trước khi ghi trạng thái local | Provider đã thực hiện, database local chưa cập nhật | Retry cùng key hoặc reconcile để đồng bộ trạng thái |
| Ghi trạng thái local trước khi gọi provider rồi crash | Local báo hoàn tất nhưng provider chưa thực hiện | Không đánh dấu hoàn tất trước khi có kết quả; dùng trạng thái pending và outbox |

Không thể suy ra “provider chưa xử lý” chỉ từ timeout ở phía client. Timeout chỉ cho biết client không nhận được phản hồi trong thời hạn. Request có thể đã được xử lý, đang xử lý hoặc chưa tới provider.

Với payment, nên lưu trạng thái trung gian như `PENDING`, `SUCCEEDED`, `FAILED` hoặc `UNKNOWN`. Trạng thái `UNKNOWN` biểu thị cần tra cứu/đối soát trước khi quyết định thử một thao tác mới.

## 9. Mô hình xử lý thanh toán có outbox và idempotency

Một luồng có thể được thiết kế như sau:

1. API nhận yêu cầu tạo thanh toán với request key ổn định.
2. Một database transaction ghi payment intent ở trạng thái `PENDING` và outbox event `ChargeRequested`.
3. Relay publish event lên broker; có thể publish lặp nếu crash ở cửa sổ publish/mark.
4. Consumer nhận event, dùng inbox để deduplicate trong database của consumer.
5. Consumer gọi payment provider bằng idempotency key ổn định gắn với payment intent.
6. Consumer lưu kết quả provider và tạo outbox event `ChargeSucceeded` hoặc `ChargeFailed` trong transaction local.
7. Event kết quả được publish; service đơn hàng cập nhật trạng thái qua inbox/dedup tương tự.
8. Một tác vụ reconciliation kiểm tra các payment ở trạng thái `PENDING` hoặc `UNKNOWN` quá lâu bằng API tra cứu của provider.

```text
Order API
   |
   v
DB transaction: PaymentIntent(PENDING) + Outbox(ChargeRequested)
   |
   v
Outbox relay ----publish----> Broker
                                |
                                v
                         Payment consumer
                                |
                         Inbox dedup (DB)
                                |
                                v
                  Payment API + idempotency key
                                |
                                v
                     Provider result / lookup
                                |
                                v
                  DB state + result outbox event
                                |
                                v
                         Broker / Order service
```

Mỗi ranh giới hệ thống có cơ chế riêng: outbox cho dual-write giữa DB và broker; inbox cho duplicate delivery vào consumer; idempotency key cho API thanh toán; reconciliation cho kết quả không xác định hoặc lỗi kéo dài.

## 10. Exactly-once của message broker có giới hạn phạm vi

Một số broker có giao dịch hoặc tính năng exactly-once semantics. Chúng có thể phối hợp việc đọc message, ghi message đầu ra và cập nhật offset/position trong cùng phạm vi broker.

Ví dụ với Kafka, producer transaction có thể ghi các output record và commit consumer offsets trong một Kafka transaction. Consumer đọc với `isolation.level=read_committed` chỉ thấy các record từ transaction đã commit. Điều này hỗ trợ exactly-once processing cho luồng consume-transform-produce nằm trong phạm vi Kafka được cấu hình đúng.

Nhưng nếu handler còn ghi vào một database độc lập hoặc gọi HTTP payment API, Kafka transaction không tự commit/rollback những hệ thống đó. Nếu consumer ghi database rồi Kafka transaction abort, message có thể được đọc lại và database write có thể lặp. Nếu commit Kafka trước rồi database write thất bại, output có thể đã được công bố dù database chưa đổi.

Muốn mở rộng cam kết qua nhiều resource manager, cần cơ chế phối hợp giao dịch được tất cả participant hỗ trợ, chẳng hạn distributed transaction/XA với hai-phase commit. HTTP API, email provider và nhiều dịch vụ SaaS không tham gia XA; 2PC cũng có chi phí vận hành, khả năng blocking và phụ thuộc coordinator. Không nên tuyên bố exactly-once end-to-end chỉ vì broker có tính năng exactly-once.

## 11. Deduplication có thể thất bại nếu giữ dấu vết quá ngắn

Inbox hoặc bảng idempotency cần lưu dấu vết đủ lâu để bao phủ thời gian message có thể được giao lại hoặc replay.

Nếu consumer xóa inbox row sau 7 ngày nhưng broker cho phép replay message từ 30 ngày trước, event cũ có thể được xử lý lại sau khi dấu dedup đã biến mất. Tương tự, nếu provider hết hạn idempotency key sau một ngày, retry cùng key vào ngày thứ ba có thể không còn được bảo vệ.

Thời hạn lưu cần dựa trên:

- Retention của broker và khả năng replay/backfill.
- Thời gian retry tối đa của producer, relay và consumer.
- Thời gian phục hồi sau outage hoặc disaster recovery.
- Chính sách lưu trữ của provider bên ngoài.
- Yêu cầu kiểm toán và thời hạn đối soát nghiệp vụ.

Với nghiệp vụ tài chính, có thể cần lưu payment reference và lịch sử giao dịch lâu hơn thời hạn idempotency của API. Khi key đã hết hạn, hệ thống nên tra cứu trạng thái theo mã giao dịch trước khi gửi một lệnh mới.

## 12. Idempotency không giải quyết mọi vấn đề thứ tự và nghiệp vụ

Idempotency bảo vệ trước việc cùng một ý định bị thực hiện lặp. Nó không tự giải quyết hai event khác nhau đến sai thứ tự.

Ví dụ:

```text
OrderUpdated(version=5, status=PAID)
OrderUpdated(version=4, status=PENDING)
```

Hai event có message ID khác nhau nên inbox dedup không loại event version 4. Nếu event cũ đến sau, consumer có thể ghi đè trạng thái mới. Cần sequence/version guard:

```sql
UPDATE order_projection
SET status = :status,
    version = :incoming_version
WHERE order_id = :order_id
  AND version < :incoming_version;
```

Consumer cũng cần xác định cách xử lý version bị thiếu, event đến sai thứ tự và event không thể áp dụng. Có thể buffer, retry, đọc lại trạng thái nguồn hoặc phát hiện gap để reconciliation.

Ngoài ra, một message có thể đại diện cho một thao tác nghiệp vụ không thể đảo ngược. Idempotency key cần gắn với đúng ý định nghiệp vụ; hai lần thanh toán hợp lệ cho hai lần mua khác nhau phải có hai key khác nhau dù cùng order/customer.

## 13. Saga và compensation khi không có transaction phân tán

Khi quy trình trải qua nhiều service, mỗi service thường commit transaction cục bộ rồi phát event cho bước tiếp theo. Nếu một bước sau thất bại, hệ thống có thể thực hiện hành động bù (compensation) để đưa nghiệp vụ về trạng thái chấp nhận được.

Ví dụ đặt phòng:

1. Giữ chỗ phòng.
2. Thu tiền.
3. Xác nhận đặt phòng.

Nếu bước thu tiền thất bại sau khi giữ phòng, hệ thống có thể hủy giữ chỗ. Nếu thu tiền thành công nhưng bước xác nhận đặt phòng thất bại, có thể hoàn tiền và giải phóng phòng.

Compensation không phải rollback vật lý của transaction đã commit. Nó là một thao tác nghiệp vụ mới, có thể thất bại, cần retry và cũng phải idempotent. Ví dụ, hoàn tiền hai lần là một lỗi khác cần được ngăn bằng idempotency key riêng cho thao tác hoàn tiền.

Saga thường cung cấp eventual consistency và khả năng phục hồi theo quy trình. Trong một khoảng thời gian, các service có thể quan sát trạng thái trung gian như `RESERVING`, `PAYMENT_PENDING` hoặc `COMPENSATING`. Giao diện và API cần thể hiện đúng trạng thái thay vì báo thành công cuối cùng quá sớm.

## 14. Thiết kế idempotency key và trạng thái xử lý

Một bảng theo dõi request nội bộ có thể lưu:

```sql
CREATE TABLE idempotency_records (
    operation_key VARCHAR(150) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Quy trình cơ bản:

1. Client gửi một key ổn định cho ý định nghiệp vụ.
2. Server tạo record với unique key và hash của request.
3. Nếu key đã tồn tại với cùng payload, trả kết quả đã lưu hoặc trạng thái đang xử lý.
4. Nếu key tồn tại nhưng payload khác, từ chối để tránh dùng lại key sai mục đích.
5. Thực hiện thay đổi nghiệp vụ và lưu kết quả trong cùng transaction nếu hiệu ứng nằm trong database.
6. Với hiệu ứng bên ngoài, dùng outbox và idempotency key của provider; lưu provider reference và trạng thái.
7. Nếu trạng thái không xác định, tra cứu/đối soát trước khi phát lệnh mới.

Khi nhiều request cùng key đến đồng thời, unique constraint là điểm phân xử cuối cùng. Ứng dụng phải xử lý duplicate-key/concurrent insert và đọc lại record hiện có. Một trạng thái `PROCESSING` cần lease/timeout hoặc cơ chế phục hồi nếu worker chết giữa chừng; không để record processing treo vĩnh viễn.

## 15. Những tuyên bố cần tránh

| Tuyên bố quá rộng | Cách diễn đạt chính xác hơn |
|---|---|
| “Broker bảo đảm message chỉ được xử lý đúng một lần.” | “Broker cung cấp semantics trong phạm vi được hỗ trợ; consumer vẫn có thể nhận lại hoặc phải xử lý duplicate tùy cấu hình và failure window.” |
| “Chúng tôi dùng Kafka exactly-once nên payment không thể bị trùng.” | “Kafka transaction bảo vệ luồng Kafka; payment API cần idempotency key và reconciliation riêng.” |
| “Outbox bảo đảm publish đúng một lần.” | “Outbox bảo đảm event được lưu cùng thay đổi DB và relay có thể publish at-least-once; consumer cần dedup.” |
| “Inbox làm toàn bộ workflow đúng một lần.” | “Inbox bảo vệ hiệu ứng trong transaction DB của consumer; API bên ngoài cần cơ chế idempotency riêng.” |
| “HTTP timeout nghĩa là provider chưa xử lý.” | “Timeout tạo kết quả không xác định; cần dùng cùng idempotency key hoặc tra cứu trạng thái.” |
| “Retry an toàn vì request giống nhau.” | “Retry an toàn khi cùng một ý định dùng key ổn định, payload được ràng buộc và hệ thống đích thực thi idempotency theo hợp đồng.” |
| “Compensation rollback mọi thứ.” | “Compensation là thao tác nghiệp vụ mới, có thể thất bại và cần idempotency/retry riêng.” |

## 16. Quy trình kiểm chứng cam kết end-to-end

Khi thiết kế một workflow qua nhiều hệ thống, hãy vẽ từng ranh giới ghi và xác định failure window:

1. Liệt kê database, broker, API provider, email service và các participant khác.
2. Với mỗi bước, xác định thao tác nào được commit nguyên tử cùng thao tác nào.
3. Ghi rõ message ID, idempotency key, aggregate ID và sequence/version được tạo ở đâu.
4. Kiểm tra crash sau mỗi điểm: trước gửi, sau gửi, trước ACK, sau ACK, trước commit, sau commit nhưng trước khi nhận response.
5. Bảo đảm outbox event không mất khi database commit thành công.
6. Bảo đảm inbox/dedup và thay đổi database consumer nằm trong cùng transaction.
7. Bảo đảm API ngoài nhận key ổn định qua mọi retry và xác nhận thời hạn lưu key.
8. Thiết kế trạng thái `PENDING`/`UNKNOWN` và reconciliation cho kết quả không xác định.
9. Đặt retention cho dedup record đủ dài để bao phủ retry và replay.
10. Kiểm thử duplicate, reorder, timeout, crash và phục hồi sau outage.
11. Xác định compensation và quy trình hỗ trợ thủ công cho các bước không thể tự phục hồi.
12. Viết cam kết chính xác theo từng ranh giới, không gắn nhãn exactly-once cho toàn workflow nếu chưa chứng minh được mọi participant.

## 17. Tự kiểm tra

**Consumer commit database thành công rồi crash trước khi ACK. Broker có thể làm gì?**

Broker có thể giao lại message vì chưa nhận ACK. Inbox record được commit cùng thay đổi nghiệp vụ giúp consumer nhận ra message đã xử lý và bỏ qua hiệu ứng lặp.

**Transactional outbox có bảo đảm broker chỉ nhận đúng một bản event không?**

Không. Relay có thể publish thành công rồi crash trước khi đánh dấu outbox row đã gửi. Lần chạy sau publish lại. Outbox giải quyết việc ghi DB và lưu event nguyên tử; consumer cần deduplicate.

**Inbox có ngăn gửi email trùng không?**

Không nếu email provider là hệ thống bên ngoài và không tham gia transaction inbox. Cần idempotency ở provider, outbox riêng và/hoặc cơ chế đối soát phù hợp.

**API thanh toán timeout có nghĩa thanh toán thất bại không?**

Không. Provider có thể đã thu tiền nhưng response bị mất. Gửi lại cùng idempotency key theo hợp đồng provider hoặc tra cứu bằng payment reference trước khi tạo thao tác mới.

**Kafka exactly-once có bảo vệ một lệnh ghi database độc lập không?**

Không tự động. Kafka transaction bảo vệ các thao tác nằm trong phạm vi Kafka transaction; database độc lập cần outbox/inbox, idempotency hoặc cơ chế giao dịch phân tán được hỗ trợ.

**Vì sao cần giữ inbox record lâu hơn thời gian retry thông thường?**

Message có thể được replay sau outage hoặc từ retention của broker. Nếu dấu dedup đã bị xóa, event cũ có thể tạo hiệu ứng lần nữa.

**Saga compensation có giống rollback database không?**

Không. Compensation là thao tác nghiệp vụ mới để bù cho bước đã commit. Nó có thể thất bại và cần retry/idempotency riêng.

Một tuyên bố xử lý đúng một lần chỉ có ý nghĩa khi nói rõ **một lần ở ranh giới nào, đối với hiệu ứng nào, trong thời gian lưu dấu dedup bao lâu và khi hệ thống ngoài không phản hồi thì phục hồi ra sao**. Với workflow nhiều hệ thống, cách thực tế là kết hợp delivery at-least-once, transaction cục bộ, outbox/inbox, idempotency key và reconciliation. Những cơ chế này không làm mạng trở nên không lỗi; chúng giúp mỗi failure window có một cách phục hồi có thể quan sát và kiểm chứng.
