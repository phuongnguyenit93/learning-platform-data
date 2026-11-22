# Phân biệt giao nhận ít nhất một lần với hiệu ứng nghiệp vụ không bị lặp

Trong hệ thống sử dụng message queue, một message có thể được giao lại khi consumer xử lý xong nhưng acknowledgment bị mất, consumer bị crash hoặc broker không nhận được xác nhận đúng hạn. Vì vậy, nhiều hệ thống chọn **at-least-once delivery (giao nhận ít nhất một lần)**: broker tiếp tục giao message cho đến khi nhận được acknowledgment hoặc đạt giới hạn lưu giữ và retry đã cấu hình.

Hệ quả là cùng một message có thể đến consumer nhiều lần. Nếu mỗi lần nhận đều thực hiện một thay đổi nghiệp vụ mới, hệ thống có thể ghi sổ hai lần, trừ tồn kho nhiều lần, tạo nhiều đơn hàng hoặc gửi nhiều thông báo.

Để xử lý an toàn, cần phân biệt:

- **Delivery semantics:** broker giao message và xử lý acknowledgment, retry, redelivery như thế nào.
- **Processing semantics:** consumer thực hiện công việc gì khi nhận message.
- **Business effect:** trạng thái hoặc tác động nghiệp vụ cuối cùng mà hệ thống tạo ra.

At-least-once delivery cho phép message được giao lặp. **Idempotency (tính lũy đẳng)** giúp một ý định nghiệp vụ được áp dụng an toàn khi request hoặc message được xử lý lặp. Hai khái niệm bổ sung cho nhau: giao nhận lặp có thể là hành vi bình thường của hệ thống, còn consumer cần bảo đảm việc lặp không tạo ra hiệu ứng nghiệp vụ ngoài ý muốn.

## 1. At-least-once delivery bảo đảm điều gì?

Trong mô hình queue phổ biến, broker giữ message cho đến khi consumer xác nhận đã xử lý. Nếu consumer không gửi acknowledgment, kết nối bị ngắt hoặc broker không ghi nhận ACK, message có thể được đưa trở lại hàng đợi và giao cho consumer lần nữa.

Luồng cơ bản:

~~~text
Producer
   |
   | Publish message M
   v
Message Broker
   |
   | Deliver M
   v
Consumer
   |
   | Xử lý message
   |
   | ACK
   v
Message Broker xóa/đánh dấu M đã được xác nhận
~~~

At-least-once thường được hiểu là broker sẽ cố gắng giao message ít nhất một lần theo các giả định về độ bền message, xác nhận từ producer, cấu hình retry, retention và khả năng phục hồi của broker. Nó không có nghĩa consumer chắc chắn chỉ nhìn thấy message một lần.

Ví dụ, consumer cập nhật số dư thành công rồi crash trước khi ACK:

~~~text
1. Broker giao message M cho Consumer A.
2. Consumer A cập nhật database và COMMIT.
3. Consumer A crash trước khi gửi ACK.
4. Broker không thấy ACK.
5. Broker giao lại M cho Consumer B hoặc Consumer A sau khi phục hồi.
6. Consumer nhận lại M và có thể thực hiện cùng thao tác lần nữa.
~~~

Từ góc nhìn broker, message chưa được xác nhận. Từ góc nhìn database, thay đổi nghiệp vụ đã commit. Hai hệ thống không có một transaction chung tự động bao trùm cả COMMIT và ACK.

Đây là nguồn gốc phổ biến của duplicate processing.

### At-least-once không đồng nghĩa với xử lý nghiệp vụ ít nhất một lần thành công

Delivery là việc message được giao tới consumer. Processing là việc consumer chạy logic. Business effect là thay đổi có ý nghĩa nghiệp vụ được commit.

Một message có thể:

- Được giao nhưng consumer crash trước khi xử lý.
- Được giao và xử lý nhưng transaction rollback.
- Được xử lý và commit nhưng ACK bị mất, dẫn đến redelivery.
- Bị retry nhiều lần rồi chuyển sang dead-letter queue theo cấu hình.
- Hết thời gian retention hoặc bị loại bỏ theo chính sách vận hành.

Do đó, khi nói at-least-once, cần hiểu phạm vi bảo đảm của broker và cấu hình cụ thể. Consumer vẫn phải thiết kế để chịu được redelivery và có cơ chế quan sát các message không thể xử lý.

## 2. Vì sao giao nhận lặp có thể tạo ra hiệu ứng nghiệp vụ lặp?

Một thao tác không tự động idempotent chỉ vì nó được gọi bằng cùng một message.

Giả sử message yêu cầu trừ 100.000 đồng khỏi tài khoản:

~~~sql
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 42;
~~~

Nếu consumer chạy câu lệnh hai lần, số dư bị trừ 200.000 đồng. Đây là thao tác không lũy đẳng.

Ngược lại, một thao tác đặt trạng thái tài khoản thành SUSPENDED:

~~~sql
UPDATE accounts
SET status = 'SUSPENDED'
WHERE account_id = 42;
~~~

Chạy lại câu lệnh có thể vẫn để tài khoản ở trạng thái SUSPENDED. Xét riêng trạng thái đó, thao tác có tính lũy đẳng.

Tuy nhiên, cần xem toàn bộ hiệu ứng nghiệp vụ. Nếu mỗi lần đặt trạng thái đều tạo một audit record mới, gửi email hoặc phát một event khác, việc chạy lại vẫn có thể tạo tác động trùng.

### Ví dụ các thao tác

| Thao tác | Xử lý lặp có an toàn tự nhiên không? | Lý do |
|---|---|---|
| Đặt đơn hàng thành CONFIRMED | Thường có, nếu chỉ cập nhật trạng thái | Gán cùng một giá trị nhiều lần không làm trạng thái thay đổi thêm |
| Tăng số dư thêm 100.000 | Không | Mỗi lần chạy lại cộng thêm một lần |
| Trừ tồn kho 1 đơn vị | Không | Mỗi lần chạy lại giảm thêm một đơn vị |
| Ghi nhận payment đã thành công theo payment_id duy nhất | Có thể, nếu có ràng buộc duy nhất và xử lý kết quả cũ | Cùng giao dịch thanh toán không được ghi nhận thành giao dịch mới |
| Gửi email xác nhận | Không | Mỗi lần gửi có thể tạo một email mới |
| Tạo shipment | Không tự động | Dịch vụ có thể tạo nhiều vận đơn nếu không nhận diện cùng yêu cầu |
| Lưu kết quả đồng bộ theo một version cụ thể | Có thể | Có thể bỏ qua version đã xử lý hoặc cũ hơn theo quy tắc |

Điều quan trọng là đánh giá **toàn bộ business effect**, gồm cập nhật database, ghi ledger, phát event, gọi API, gửi email và các side effect khác.

## 3. Idempotency là gì?

Một thao tác có tính lũy đẳng nếu thực hiện cùng một ý định nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương với việc thực hiện một lần.

Có thể mô tả ở mức trạng thái:

\[
f(f(x)) = f(x)
\]

Trong ứng dụng phân tán, idempotency thường được triển khai bằng một định danh ổn định cho mỗi ý định nghiệp vụ, ví dụ:

- message_id của event.
- idempotency_key của request thanh toán.
- command_id của lệnh tạo đơn.
- operation_id của một lần chuyển tiền.

Consumer hoặc service nhận lưu lại những định danh đã xử lý. Khi nhận lại cùng một định danh, nó nhận ra đây là lần giao lại của cùng một ý định và không áp dụng business effect lần nữa.

Ví dụ:

~~~text
Message:
    message_id = evt-1001
    command = DebitAccount
    account_id = 42
    amount = 100000

Lần nhận thứ nhất:
    evt-1001 chưa được xử lý
    -> ghi nhận evt-1001
    -> trừ 100000
    -> COMMIT

Lần nhận thứ hai:
    evt-1001 đã được xử lý
    -> không trừ thêm
    -> trả ACK
~~~

Idempotency key phải đại diện cho cùng một ý định qua mọi lần retry. Nếu mỗi lần retry tạo một key mới, consumer sẽ coi đó là các thao tác khác nhau và không thể nhận diện bản giao lại.

## 4. Dùng Inbox hoặc bảng processed_messages để chống xử lý trùng

Một cách triển khai phổ biến là lưu message đã xử lý trong cùng database với dữ liệu nghiệp vụ. Mẫu này thường được gọi là **Inbox pattern** hoặc deduplication table.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Khóa chính kết hợp consumer_name và message_id cho phép cùng một event được xử lý bởi nhiều consumer độc lập, nhưng mỗi consumer chỉ ghi nhận event đó một lần.

Ví dụ consumer xử lý yêu cầu trừ tiền:

~~~sql
BEGIN;

INSERT INTO processed_messages (consumer_name, message_id)
VALUES ('account-debit-consumer', '00000000-0000-0000-0000-000000001001')
ON CONFLICT DO NOTHING
RETURNING message_id;

-- Nếu INSERT không trả về dòng:
-- message đã được consumer này ghi nhận trước đó.
-- Không áp dụng lại thay đổi nghiệp vụ.

-- Nếu INSERT trả về một dòng:
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 42;

COMMIT;
~~~

Ứng dụng cần kiểm tra kết quả INSERT trước khi chạy UPDATE. Nếu không có dòng nào được trả về, đây là message trùng đã được ghi nhận. Consumer kết thúc transaction thích hợp và ACK message mà không áp dụng business effect lần nữa.

### Vì sao phải ghi Inbox và business data trong cùng transaction?

Giả sử ứng dụng ghi processed_messages rồi commit, sau đó mới cập nhật số dư:

~~~text
Ghi processed_messages
COMMIT
    |
    X Consumer crash trước khi trừ tiền
~~~

Khi broker giao lại message, consumer thấy message đã được đánh dấu xử lý và bỏ qua. Nhưng số dư chưa được trừ. Business effect bị mất.

Trường hợp ngược lại, nếu cập nhật số dư rồi commit trước, sau đó mới ghi processed_messages:

~~~text
Trừ tiền
COMMIT
    |
    X Consumer crash trước khi ghi processed_messages
~~~

Message được giao lại và consumer trừ tiền lần nữa. Business effect bị lặp.

Vì vậy, marker chống trùng và thay đổi nghiệp vụ trong database phải được commit hoặc rollback cùng nhau:

~~~text
BEGIN DATABASE TRANSACTION
    |
    +-- Insert processed_messages
    |
    +-- Nếu message mới:
    |       +-- Cập nhật dữ liệu nghiệp vụ
    |
    +-- COMMIT cả hai thay đổi
             |
             v
        Gửi ACK cho broker
~~~

Nếu transaction rollback, cả marker và business change đều bị rollback. Khi message được giao lại, consumer có thể xử lý lại từ đầu.

Nếu transaction commit thành công nhưng consumer crash trước ACK, broker giao lại message. Lần sau, khóa duy nhất trên processed_messages cho biết event đã được xử lý, nên consumer không lặp business change.

### Xử lý hai consumer nhận cùng message đồng thời

Có thể hai consumer cùng nhận hoặc xử lý cùng một message do redelivery, rebalance hoặc cấu hình nhiều worker.

Khóa duy nhất trên (consumer_name, message_id) là điểm đồng bộ ở database. Một transaction insert thành công; transaction còn lại phải chờ kết quả xung đột unique. Khi transaction đầu commit, transaction sau không thể insert cùng khóa và biết message đã được ghi nhận.

Với PostgreSQL, INSERT ... ON CONFLICT DO NOTHING giúp xử lý tình huống này mà không cần bắt lỗi unique violation làm hỏng transaction. Cách viết cụ thể sẽ khác ở MySQL, SQL Server hoặc Oracle.

## 5. Thứ tự ACK và COMMIT quyết định nguy cơ mất hoặc lặp

Một quy tắc quan trọng của consumer là **chỉ ACK sau khi business transaction đã commit thành công**.

### ACK trước COMMIT có thể làm mất business effect

~~~text
Consumer nhận message
    |
    +-- Gửi ACK
    |
    +-- Broker đánh dấu message hoàn tất
    |
    +-- Consumer cập nhật database
    |
    X Database transaction rollback hoặc consumer crash
~~~

Broker đã ghi nhận message hoàn tất nên có thể không giao lại. Business effect chưa được commit nhưng message đã bị loại khỏi luồng xử lý. Đây là nguy cơ mất xử lý.

### COMMIT trước ACK có thể tạo redelivery nhưng có thể xử lý an toàn

~~~text
Consumer nhận message
    |
    +-- BEGIN
    |
    +-- Insert Inbox marker
    |
    +-- Cập nhật business data
    |
    +-- COMMIT
    |
    X Consumer crash trước ACK
    |
    +-- Broker giao lại message
    |
    +-- Inbox phát hiện message trùng
    |
    +-- Bỏ qua business change
    |
    +-- ACK
~~~

Với Inbox pattern, thứ tự COMMIT rồi ACK biến trường hợp crash thành một lần giao lại vô hại.

Có thể xảy ra tình huống consumer mất kết nối khi gửi COMMIT và không biết database đã commit hay chưa. Consumer không nên đoán. Có thể để message được giao lại; nếu transaction trước đã commit, Inbox marker sẽ nhận diện duplicate. Nếu transaction trước chưa commit, message có thể được xử lý bình thường.

## 6. Idempotency key cho API và dịch vụ bên ngoài

Inbox giải quyết việc xử lý lặp trong ranh giới database mà consumer kiểm soát. Nếu consumer gọi một dịch vụ bên ngoài, transaction database không tự bao trùm side effect của dịch vụ đó.

Ví dụ consumer nhận yêu cầu thu tiền:

~~~text
Consumer
    |
    +-- Gọi Payment API
    |
    +-- Payment Provider đã thu tiền
    |
    X Response bị mất
    |
    +-- Consumer không biết kết quả
    |
    +-- Message được giao lại
    |
    +-- Gọi Payment API lần nữa
~~~

Nếu API thanh toán tạo giao dịch mới cho mỗi request, khách hàng có thể bị thu tiền hai lần.

Giải pháp là gửi một **idempotency key ổn định** cho cùng một ý định thanh toán:

~~~http
POST /payments
Idempotency-Key: payment-order-1001
Content-Type: application/json
~~~

Payload minh họa:

~~~json
{
  "orderId": 1001,
  "amount": 100000,
  "currency": "VND"
}
~~~

Lần gửi đầu tiên, nhà cung cấp tạo giao dịch thanh toán và lưu kết quả theo key. Nếu response bị mất, consumer retry bằng đúng key đó. Nhà cung cấp nhận ra cùng ý định và trả lại kết quả đã lưu hoặc trạng thái giao dịch cũ, thay vì tạo khoản thu mới.

### Các nguyên tắc của idempotency key

- Key phải ổn định qua mọi lần retry của cùng một ý định.
- Key cần có phạm vi duy nhất rõ ràng, ví dụ theo merchant, operation type hoặc tenant.
- Cùng key nên đi kèm cùng payload nghiệp vụ. Nếu cùng key nhưng amount hoặc currency khác, service nên từ chối hoặc báo conflict.
- Service nhận phải lưu key và kết quả đủ lâu để bao phủ cửa sổ retry, redelivery và replay dự kiến.
- Consumer phải lưu hoặc có cách tái tạo key sau crash.
- Không tạo key mới chỉ vì timeout hoặc response bị mất.

Một key có thể là order_id nếu mỗi đơn chỉ có đúng một ý định thanh toán. Nếu đơn hàng cho phép thanh toán nhiều lần hoặc nhiều lần thử độc lập, cần một payment_attempt_id riêng để phân biệt các ý định hợp lệ.

### Idempotency không thể được giả định nếu API không hỗ trợ

Nếu dịch vụ bên ngoài không cung cấp idempotency key hoặc API tra cứu theo mã tham chiếu, consumer khó chứng minh rằng retry không tạo side effect trùng.

Có thể cần:

- Tra cứu trạng thái theo mã yêu cầu ổn định.
- Gửi client-generated reference mà dịch vụ bảo đảm duy nhất.
- Đối soát giao dịch sau timeout.
- Chuyển trạng thái sang UNKNOWN/PENDING_CONFIRMATION thay vì coi timeout là thất bại chắc chắn.
- Dùng thao tác bù nếu side effect đã xảy ra nhưng quy trình không thể tiếp tục.

Nếu API đích không hỗ trợ bất kỳ cơ chế nhận diện hoặc tra cứu nào, không thể tự tạo bảo đảm exactly-once effect chỉ bằng cách retry ở consumer.

## 7. Kết hợp Transactional Outbox và Inbox

Một hệ thống thường cần bảo vệ cả hai chiều:

- Producer ghi dữ liệu nghiệp vụ và ý định phát message.
- Consumer nhận message, cập nhật dữ liệu nghiệp vụ và ghi nhận message đã xử lý.

**Transactional Outbox** bảo đảm thay đổi nghiệp vụ và event được lưu cùng transaction ở producer. **Inbox** bảo đảm event và business effect ở consumer được ghi cùng transaction.

### Phía producer

~~~sql
BEGIN;

INSERT INTO orders (order_id, status, total_amount)
VALUES (1001, 'PENDING_PAYMENT', 100000);

INSERT INTO outbox_events (
    event_id,
    event_type,
    aggregate_id,
    payload,
    status
)
VALUES (
    '00000000-0000-0000-0000-000000001001',
    'PaymentRequested',
    '1001',
    '{"orderId":1001,"amount":100000}',
    'PENDING'
);

COMMIT;
~~~

Worker đọc outbox và publish event. Nếu publish thành công nhưng worker crash trước khi đánh dấu event đã gửi, worker có thể publish lại cùng event_id. Đây là lý do consumer vẫn cần Inbox hoặc idempotency.

### Phía consumer

~~~text
Broker giao event_id = E
    |
    v
Consumer bắt đầu transaction
    |
    +-- Insert Inbox marker cho E
    |
    +-- Nếu E đã tồn tại:
    |       +-- Không áp dụng lại business effect
    |
    +-- Nếu E mới:
            +-- Cập nhật dữ liệu nghiệp vụ
    |
    +-- COMMIT
    |
    v
ACK message
~~~

Cách kết hợp này thường tạo ra **at-least-once delivery với business effect được chống lặp trong ranh giới database**.

Nó không làm cho broker chỉ giao message một lần. Broker vẫn có thể giao lại, outbox relay vẫn có thể publish trùng, nhưng các lần giao lặp được xử lý an toàn bằng định danh ổn định và transaction.

## 8. Exactly-once delivery và exactly-once effect khác nhau

Cụm từ exactly-once thường được dùng theo nhiều nghĩa. Cần hỏi rõ bảo đảm được cung cấp trong phạm vi nào.

| Khái niệm | Ý nghĩa | Giới hạn |
|---|---|---|
| At-most-once delivery | Message được giao tối đa một lần theo cơ chế xác nhận | Có thể mất message nếu lỗi xảy ra sau khi message bị xác nhận hoặc loại bỏ |
| At-least-once delivery | Broker retry/redeliver cho đến khi được xác nhận hoặc đạt chính sách giới hạn | Consumer có thể nhận cùng message nhiều lần |
| Exactly-once delivery | Message được giao đúng một lần trong phạm vi hệ thống định nghĩa | Khó bảo đảm qua crash, network và nhiều hệ thống độc lập |
| Exactly-once processing trong một hệ thống | Hệ thống quản lý message và kết quả xử lý trong cùng ranh giới transaction | Không tự bao trùm database hoặc API bên ngoài |
| Exactly-once business effect | Một ý định nghiệp vụ chỉ được áp dụng một lần dù message/request có thể lặp | Cần idempotency, deduplication và ranh giới transaction rõ ràng |

Một số broker có tính năng transaction hoặc exactly-once semantics trong phạm vi nền tảng của chúng. Ví dụ, Kafka có thể phối hợp việc đọc offset và ghi output records trong một Kafka transaction để hỗ trợ exactly-once processing giữa các topic Kafka. Bảo đảm này không tự động làm một câu UPDATE trong database bên ngoài hoặc một HTTP payment call trở thành exactly-once.

Khi tích hợp broker với database, consumer vẫn cần Inbox/deduplication hoặc một cơ chế tương đương. Khi gọi dịch vụ bên ngoài, cần idempotency key hoặc quy trình đối soát.

Do đó, trong thiết kế thực tế, mục tiêu thường là **at-least-once delivery + idempotent processing**, thay vì dựa vào một tuyên bố exactly-once chung chung.

## 9. Idempotency key, message_id và business_id khác nhau thế nào?

Các định danh này có thể trùng giá trị trong hệ thống đơn giản, nhưng ý nghĩa không giống nhau.

| Định danh | Mục đích |
|---|---|
| message_id | Nhận diện một message cụ thể trong hệ thống messaging |
| idempotency_key | Nhận diện một ý định nghiệp vụ qua nhiều lần request hoặc retry |
| business_id | Định danh thực thể nghiệp vụ, ví dụ order_id hoặc account_id |
| correlation_id | Liên kết các log và thao tác thuộc cùng một quy trình |
| causation_id | Chỉ ra message/command đã gây ra event hiện tại |
| aggregate_version | Biểu thị thứ tự phiên bản của một aggregate hoặc thực thể |

Một đơn hàng có thể phát nhiều event:

- OrderCreated.
- PaymentRequested.
- PaymentCompleted.
- ShipmentRequested.

Tất cả có cùng order_id nhưng là những message và ý định khác nhau. Nếu chỉ dùng order_id làm dedup key cho mọi consumer, có thể vô tình loại bỏ những event hợp lệ sau event đầu tiên.

Ngược lại, cùng một PaymentRequested được publish lại do crash nên phải giữ nguyên event_id và idempotency key. Không tạo ID mới cho mỗi lần retry.

Khóa duy nhất thường nên có phạm vi theo consumer hoặc loại operation:

~~~sql
PRIMARY KEY (consumer_name, message_id)
~~~

Hoặc với API:

~~~sql
UNIQUE (merchant_id, operation_type, idempotency_key)
~~~

Phạm vi chính xác phụ thuộc yêu cầu multi-tenant, loại nghiệp vụ và chính sách lưu giữ.

## 10. Lưu kết quả để trả lại cho request trùng

Với API, chỉ lưu rằng key đã tồn tại đôi khi chưa đủ. Client retry có thể cần nhận lại response giống lần đầu.

Một bảng idempotency có thể lưu trạng thái và kết quả:

~~~sql
CREATE TABLE idempotency_records (
    scope_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (scope_id, idempotency_key)
);
~~~

Quy trình:

1. Nhận request và key.
2. Tính fingerprint/hash của payload đã chuẩn hóa.
3. Thử tạo record cho key.
4. Nếu key mới, xử lý nghiệp vụ và lưu kết quả trong cùng transaction nếu business effect nằm trong cùng database.
5. Nếu key đã tồn tại và payload giống nhau, trả lại kết quả đã lưu hoặc trạng thái đang xử lý.
6. Nếu key tồn tại nhưng payload khác, trả conflict theo API contract.

Với thao tác gọi dịch vụ bên ngoài, không thể giữ một database transaction mở rồi giả định API cùng commit. Cần dùng workflow có trạng thái như PENDING, SUCCEEDED, FAILED hoặc UNKNOWN, cùng outbox và cơ chế tra cứu/đối soát.

Cần định nghĩa hành vi khi hai request cùng key đến đồng thời. Unique constraint hoặc một thao tác insert nguyên tử phải chọn một request làm chủ xử lý. Request còn lại chờ kết quả, đọc record hiện có hoặc nhận trạng thái đang xử lý.

## 11. Deduplication có thời hạn và replay

Bảng processed_messages không thể tăng vô hạn mà không có chính sách lưu trữ. Nhưng xóa marker quá sớm sẽ làm message cũ được xử lý lại như message mới.

Thời gian lưu marker cần bao phủ:

- Thời gian retry tối đa của broker.
- Message retention và thời gian message có thể nằm trong queue.
- Thời gian consumer có thể ngừng hoạt động.
- Khoảng thời gian replay từ dead-letter queue.
- Quy trình replay thủ công hoặc phục hồi sau sự cố.
- Độ trễ của các hệ thống downstream.

Nếu hệ thống cho phép replay event sau nhiều tháng, marker chỉ lưu vài ngày có thể không đủ. Có thể lưu marker lâu hơn, archive theo partition hoặc dùng business constraint lâu dài để ngăn hiệu ứng trùng.

Không nên dùng TTL ngắn tùy tiện chỉ để giảm kích thước bảng. Cần thống nhất chính sách retention với khả năng replay của hệ thống.

### Replay có chủ đích

Một số quy trình cần chạy lại message để sửa lỗi logic hoặc xây dựng lại projection. Khi replay, cần quyết định đó là:

- Replay để khôi phục xử lý chưa hoàn thành, vẫn giữ idempotency key cũ.
- Rebuild một projection mới, dùng consumer identity hoặc namespace mới.
- Thực hiện một nghiệp vụ mới, cần command_id mới và có sự chấp thuận phù hợp.

Không nên xóa marker hoặc đổi message_id tùy tiện để ép message chạy lại, vì có thể gây lặp thanh toán, ghi sổ hoặc gửi thông báo.

## 12. Idempotency không tự giải quyết thứ tự message

Một message được xử lý lặp an toàn vẫn có thể làm sai trạng thái nếu đến sai thứ tự.

Ví dụ:

~~~text
Order version 5: status = PAID
Order version 6: status = SHIPPED
~~~

Nếu event version 6 được xử lý trước, rồi event version 5 đến muộn, consumer có thể ghi trạng thái PAID đè lên SHIPPED nếu chỉ kiểm tra idempotency theo message_id.

Có thể lưu aggregate_version và chỉ áp dụng event khi thứ tự hợp lệ:

~~~sql
UPDATE order_projection
SET status = 'SHIPPED',
    version = 6
WHERE order_id = 1001
  AND version = 5;
~~~

Hoặc với một projection chỉ cần trạng thái mới nhất, có thể bỏ qua event có version không lớn hơn version hiện tại theo quy tắc đã định nghĩa. Với các event mang delta cần áp dụng tuần tự, không thể đơn giản bỏ qua version cũ nếu còn thiếu một event trung gian; cần phát hiện gap và chờ hoặc rebuild.

Vì vậy:

- Idempotency ngăn cùng một ý định được áp dụng nhiều lần.
- Ordering/versioning bảo vệ thứ tự thay đổi.
- Concurrency control bảo vệ các cập nhật đồng thời.
- Business invariants bảo vệ các quy tắc nghiệp vụ.

Đây là các cơ chế khác nhau và có thể cần kết hợp.

## 13. Retry, poison message và dead-letter queue

At-least-once thường đi kèm retry. Nếu consumer liên tục lỗi với một message, broker có thể giao lại nhiều lần.

Cần phân biệt:

- **Transient error:** database tạm thời không sẵn sàng, network timeout hoặc service tạm gián đoạn. Có thể retry với backoff.
- **Permanent business error:** dữ liệu không hợp lệ hoặc yêu cầu vi phạm quy tắc. Retry nguyên trạng thường không giúp ích.
- **Poison message:** message luôn làm consumer lỗi do payload hoặc điều kiện không thể xử lý.
- **Unknown outcome:** thao tác bên ngoài có thể đã thành công nhưng response bị mất.

Dead-letter queue (DLQ) giữ message không thể xử lý sau chính sách retry. DLQ cần quy trình quan sát, phân loại, sửa lỗi và replay có kiểm soát.

Khi replay message từ DLQ:

- Giữ nguyên message_id nếu đó là cùng ý định.
- Kiểm tra Inbox marker trước khi áp dụng business effect.
- Nếu cần thực hiện một nghiệp vụ mới, tạo command/event mới với định danh mới.
- Không bỏ qua idempotency chỉ vì message được replay thủ công.
- Ghi nhận người thực hiện, lý do và thời điểm replay.

## 14. Thiết kế consumer chịu được redelivery

Một consumer xử lý message theo mô hình database transaction có thể đi theo trình tự:

1. Nhận message và xác định message_id, idempotency key, aggregate_id và version nếu có.
2. Mở transaction database.
3. Thử ghi Inbox marker bằng unique key.
4. Nếu marker đã tồn tại, không lặp business effect; kết thúc và ACK.
5. Nếu marker mới, kiểm tra điều kiện nghiệp vụ và cập nhật dữ liệu.
6. Ghi các event tiếp theo vào Outbox nếu cần.
7. Commit Inbox marker, business data và Outbox cùng nhau.
8. Sau commit mới ACK broker.
9. Nếu transaction thất bại, không ACK; để broker retry theo chính sách.
10. Nếu lỗi nghiệp vụ không thể retry, đưa vào luồng xử lý lỗi/DLQ theo contract.

Pseudocode:

~~~text
handle(message):
    key = (consumer_name, message.message_id)

    BEGIN DATABASE TRANSACTION

    inserted = INSERT inbox(key)
               ON CONFLICT DO NOTHING

    if not inserted:
        COMMIT
        ACK message
        return DUPLICATE

    validate message and business state
    apply business changes
    INSERT follow-up event into outbox if needed

    COMMIT
    ACK message
    return PROCESSED

on transient failure:
    ROLLBACK
    do not ACK
    let broker retry
~~~

Nếu consumer nhận message trùng nhưng marker đang nằm trong một transaction chưa commit của worker khác, thao tác unique insert có thể chờ. Sau khi worker đầu commit, worker sau nhận biết duplicate; nếu worker đầu rollback, worker sau có thể trở thành worker xử lý thành công.

Cần tránh ACK trước khi transaction hoàn tất. Với một số broker, ACK có thể tự động theo chế độ auto-ack; chế độ này không phù hợp nếu ứng dụng cần bảo đảm business transaction commit trước khi message được xác nhận.

## 15. Kiểm thử các điểm crash và retry

Kiểm thử idempotency cần chủ động tạo lỗi ở các ranh giới giữa broker, consumer và database.

| Điểm lỗi mô phỏng | Kết quả cần xác nhận |
|---|---|
| Consumer crash trước khi mở transaction | Message được giao lại và xử lý bình thường |
| Crash sau khi ghi Inbox nhưng trước business update, chưa commit | Transaction rollback; message giao lại có thể xử lý |
| Crash sau business update nhưng trước COMMIT | Cả business update và Inbox marker rollback |
| Crash sau COMMIT nhưng trước ACK | Message được giao lại; Inbox phát hiện duplicate và không lặp effect |
| ACK bị mất sau COMMIT | Redelivery không tạo business effect mới |
| Hai consumer nhận cùng message đồng thời | Unique key chỉ cho một transaction ghi nhận và áp dụng effect |
| Payment API thành công nhưng response bị mất | Retry cùng idempotency key không tạo khoản thu mới |
| Consumer nhận event cũ sau event mới | Version/ordering rule ngăn trạng thái bị ghi lùi |
| Message replay từ DLQ | Marker và key cũ vẫn bảo vệ hiệu ứng đã thực hiện |

Nên kiểm tra cả dữ liệu và side effect:

- Số dòng ledger được tạo.
- Tổng số tiền đã trừ.
- Số reservation hoặc shipment được tạo.
- Số email hoặc notification thực sự gửi.
- Trạng thái Inbox/Outbox.
- Số lần redelivery, retry và DLQ.
- Sự nhất quán giữa business record và message processing record.

Một test chỉ xác nhận consumer trả về thành công chưa chứng minh idempotency. Cần kiểm tra kết quả sau nhiều lần giao cùng message và sau các điểm crash.

## 16. Những nhầm lẫn thường gặp

**“At-least-once nghĩa là message chỉ được xử lý một lần.”**

Không. Broker có thể giao lại message. Consumer phải chịu được duplicate delivery.

**“Chỉ cần ACK sau khi nhận message.”**

ACK trước khi business transaction commit có thể làm mất xử lý nếu consumer crash hoặc transaction rollback.

**“Đã có message_id thì tự động chống trùng.”**

Message_id chỉ có tác dụng nếu consumer lưu và kiểm tra nó bằng một cơ chế nguyên tử, có unique constraint hoặc cơ chế tương đương. Chỉ log message_id không ngăn business effect lặp.

**“Ghi processed_messages sau khi cập nhật business data là đủ.”**

Nếu hai thao tác ở hai transaction khác nhau, crash giữa chúng có thể làm mất hoặc lặp hiệu ứng. Marker và thay đổi nghiệp vụ trong cùng database phải commit cùng nhau.

**“Idempotency key mới cho mỗi lần retry là an toàn.”**

Không. Key mới làm mỗi lần retry trông như một ý định mới. Cần giữ key ổn định qua retry của cùng một operation.

**“Exactly-once của broker bao trùm luôn database và HTTP API.”**

Không. Bảo đảm exactly-once của broker thường chỉ có hiệu lực trong ranh giới nền tảng hoặc transaction mà broker kiểm soát. Database và dịch vụ HTTP độc lập cần cơ chế phối hợp riêng.

**“Đã chống trùng thì không cần kiểm soát thứ tự.”**

Không. Message khác nhau có thể đến sai thứ tự. Cần version, sequence number hoặc quy tắc ordering nếu nghiệp vụ phụ thuộc thứ tự.

**“Có thể xóa dedup marker ngay sau khi xử lý.”**

Không nếu message còn khả năng redelivery hoặc replay. Retention của marker phải phù hợp với thời gian sống và chính sách replay của message.

## 17. Chọn cơ chế theo loại business effect

| Loại nghiệp vụ | Cơ chế nên cân nhắc |
|---|---|
| Cập nhật trạng thái theo giá trị đích | Gán trạng thái có điều kiện, kiểm tra version nếu cần |
| Trừ tiền hoặc ghi ledger | Inbox + unique business reference + transaction; không chỉ dựa vào trạng thái tài khoản |
| Gửi email hoặc notification | Outbox, notification id ổn định, provider hoặc worker hỗ trợ dedup nếu có |
| Gọi Payment API | Idempotency key ổn định, tra cứu giao dịch và đối soát |
| Tạo shipment | Idempotency key hoặc reference duy nhất ở nhà vận chuyển |
| Cập nhật projection từ event | Inbox + aggregate version/sequence |
| Xử lý message có nhiều bước | Workflow/Saga, trạng thái trung gian, retry và compensation |
| Replay event để rebuild dữ liệu | Namespace consumer riêng hoặc quy trình rebuild có kiểm soát |

Không phải mọi business effect đều có thể làm exactly-once theo nghĩa tuyệt đối. Với email hoặc hệ thống bên ngoài không hỗ trợ idempotency, có thể cần chấp nhận khả năng gửi trùng, thêm bước đối soát hoặc dùng một nhà cung cấp có API nhận diện yêu cầu.

## Kết luận

At-least-once delivery cho phép broker giao lại cùng message khi acknowledgment bị mất, consumer crash hoặc retry được kích hoạt. Đây là cơ chế tăng khả năng message được xử lý, nhưng nó không bảo đảm business effect chỉ xảy ra một lần.

Muốn tránh hiệu ứng nghiệp vụ lặp, consumer cần idempotency: dùng message_id hoặc idempotency key ổn định, ghi nhận xử lý bằng unique constraint, và commit marker cùng thay đổi dữ liệu nghiệp vụ trong một transaction. ACK chỉ nên được gửi sau commit. Với side effect ở dịch vụ ngoài, cần idempotency key ở phía nhận, Transactional Outbox, Inbox, tra cứu trạng thái hoặc quy trình đối soát.

Mục tiêu thực tế là cho phép message được giao lại mà hệ thống vẫn tạo ra kết quả nghiệp vụ đúng. Delivery có thể lặp; business effect phải được bảo vệ trong ranh giới mà ứng dụng kiểm soát.
