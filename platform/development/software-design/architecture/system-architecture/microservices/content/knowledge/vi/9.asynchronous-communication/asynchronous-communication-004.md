# Phạm vi và giới hạn của bảo đảm xử lý exactly-once

## 1. Exactly-once thực sự bảo đảm điều gì?

Khi xây dựng hệ thống giao tiếp bất đồng bộ, các nhóm phát triển thường sử dụng message broker như Kafka, RabbitMQ hoặc các dịch vụ queue managed để truyền sự kiện giữa microservices. Một bài toán xuất hiện ngay sau đó: điều gì xảy ra nếu cùng một message được giao lại, người tiêu thụ bị crash, producer không nhận acknowledgment hoặc một cuộc gọi bên ngoài trả timeout?

Các thuật ngữ **at-most-once**, **at-least-once** và **exactly-once** mô tả những đặc điểm giao nhận và xử lý, nhưng ý nghĩa cụ thể luôn phụ thuộc **phạm vi, transaction boundary và loại tác dụng** được bảo đảm.

Điểm quan trọng nhất: **Exactly-once processing trong một nền tảng không đồng nghĩa toàn bộ quy trình nghiệp vụ xuyên nhiều nền tảng chỉ thực hiện đúng một lần.** Kafka có thể cung cấp các bảo đảm transaction cho luồng đọc từ Kafka, xử lý và ghi lại Kafka. Điều đó không tự làm cho PostgreSQL, hệ thống email hay cổng thanh toán bên ngoài tham gia cùng một giao dịch.

Ví dụ Order Service phát sự kiện OrderPaid. Invoice Service nhận event, tạo hóa đơn rồi ACK. Nếu Invoice Service đã commit hóa đơn nhưng crash trước khi ACK, broker có thể giao lại message. Nếu logic chỉ tạo hóa đơn vô điều kiện, hệ thống có thể phát hành hai hóa đơn dù broker hoàn toàn hoạt động đúng theo hợp đồng.

Một ví dụ khác: Payment Worker gọi cổng thanh toán, provider đã thu tiền nhưng phản hồi bị mất. Worker timeout và gửi lại yêu cầu với một mã giao dịch khác, dẫn đến nguy cơ thu tiền hai lần. Bật exactly-once ở message broker không thể tự giải quyết trường hợp này.

Vì vậy, câu hỏi kiến trúc cần trả lời không phải “công nghệ có exactly-once không?” mà là:

1. Exactly-once đối với **message delivery**, **state update** hay **business side effect**?
2. Các thành phần nào thực sự tham gia **cùng một transaction**?
3. Sau crash hoặc timeout, có thể biết điều gì đã commit và điều gì chưa?
4. Nếu code được chạy lại, có bảo đảm tác dụng nghiệp vụ không bị nhân đôi?
5. Nếu kết quả chưa rõ, ai chịu trách nhiệm **đối soát và chốt trạng thái cuối**?

Bài này làm rõ các bảo đảm trong giao tiếp bất đồng bộ, giới hạn giữa broker/database/API ngoài, cùng cách dùng idempotency, transaction, outbox, inbox và reconciliation.

## 2. Ba loại delivery semantics

### 2.1. At-most-once: tối đa một lần giao, có thể mất

Mô hình at-most-once ưu tiên hạn chế giao lại message. Trong các trường hợp lỗi, message có thể bị mất.

~~~text
Broker giao message M
Consumer ACK M trước khi ghi DB
Consumer crash
DB chưa có thay đổi
Broker coi M đã xử lý
~~~

Hệ quả: tác dụng nghiệp vụ chưa xảy ra nhưng hệ thống có thể không giao lại thông điệp. Mô hình này có thể phù hợp với dữ liệu telemetry không quan trọng mà mẫu mới sẽ đến liên tục, nhưng rủi ro lớn với thanh toán, đơn hàng hoặc kế toán.

Không nên diễn giải at-most-once thành “mỗi message chắc chắn được xử lý một lần”; nó có thể được xử lý **không lần nào**.

### 2.2. At-least-once: cố gắng không mất, chấp nhận giao trùng

Mô hình at-least-once cho phép broker redeliver khi chưa nhận xác nhận xử lý trong phạm vi hợp đồng của broker.

~~~text
Broker giao M
Consumer ghi database và COMMIT
Consumer crash trước ACK
Broker giao lại M
Consumer chạy logic lần nữa
~~~

Ưu điểm là giảm nguy cơ mất công việc sau lỗi tạm thời. Nhược điểm là **duplicate delivery** và có thể **duplicate side effect**. Một event OrderConfirmed được giao hai lần không được phép tự động khiến hệ thống gửi hai khoản thanh toán hoặc xuất hai hóa đơn nếu nghiệp vụ chỉ cho phép một.

Trong thực tế, **at-least-once + idempotent consumer** là chiến lược phổ biến và dễ kiểm chứng hơn lời tuyên bố exactly-once end-to-end không có ranh giới rõ.

At-least-once cũng là một cam kết có điều kiện: cấu hình persistence, replication, retention, TTL, maximum redelivery và các chính sách DLQ/drop ảnh hưởng đến khả năng giữ message. Không thể hứa sẽ giao mãi mãi bất chấp dữ liệu bị xóa hoặc hạ tầng mất toàn bộ bản sao.

### 2.3. Exactly-once: hiệu lực commit một lần trong phạm vi xác định

Exactly-once processing semantics thường hướng tới việc **một input tạo một kết quả được commit và quan sát được** trong một phạm vi hệ thống/transaction đã định nghĩa, ngay cả khi code phải chạy lại.

Điều này không nhất thiết có nghĩa:

- Listener method chỉ được gọi đúng một lần.
- Thread xử lý không bao giờ chạy lại sau restart.
- Mọi API bên ngoài chỉ nhận request một lần.
- Thanh toán không bao giờ phát sinh hai giao dịch nếu nghiệp vụ không thiết kế chống lặp.
- Toàn bộ hệ thống phân tán là một atomic transaction.

Nếu một hệ thống thực thi code hai lần nhưng chỉ commit kết quả đúng một lần theo transaction và idempotency, nó vẫn có thể đáp ứng yêu cầu **effectively-once business effect** ở phạm vi dữ liệu đó.

### 2.4. So sánh nhanh

| Tiêu chí | At-most-once | At-least-once | Exactly-once trong phạm vi hỗ trợ |
| --- | --- | --- | --- |
| Có thể mất message trong lỗi? | Có | Cố gắng tránh theo hợp đồng broker | Tránh mất hiệu lực đã commit trong phạm vi transaction |
| Có thể giao lại message? | Thường hạn chế | Có | Code có thể thực thi lại |
| Side effect ngoài broker tự duy nhất? | Không | Không | Không tự động |
| Cần idempotency nghiệp vụ? | Tùy mức độ quan trọng | Thường cần | Vẫn cần ngoài transaction boundary |
| Độ phức tạp | Thấp hơn trong một số luồng | Retry, ACK, dedup | Transaction, state, config, fencing |
| Phù hợp | Tín hiệu có thể bỏ | Event nghiệp vụ cần phục hồi | Pipeline có thể nằm trong cùng phạm vi giao dịch |

Không có mô hình delivery tối ưu cho mọi use case. Điều cần bảo vệ là **bất biến nghiệp vụ và kết quả có thể khôi phục**.

## 3. Bốn lớp bảo đảm rất khác nhau

Một event có thể đi qua chuỗi:

~~~mermaid
flowchart LR
    P["Producer"] --> B[("Message Broker")]
    B --> C["Consumer"]
    C --> D[("Business DB")]
    C --> X["External Provider"]
~~~

Cần phân biệt:

**Lớp A — Message được ghi vào broker:** Producer nhận ACK từ broker theo chính sách acks, replication và persistence. Broker đã nhận message, nhưng không chứng minh consumer đã làm gì.

**Lớp B — Consumer nhận hoặc ACK:** Một consumer đã lấy message hoặc xác nhận với broker. Không tự chứng minh transaction nghiệp vụ đã commit.

**Lớp C — Business state đã commit:** PostgreSQL hoặc cơ sở dữ liệu khác đã ghi thay đổi theo local transaction. Điều đó không bảo đảm event phản hồi đã publish hoặc API ngoài đã thực hiện.

**Lớp D — External side effect đã xảy ra:** Email đã gửi, đơn vận chuyển đã tạo hoặc provider đã thu tiền. Local database rollback không tự đảo ngược tác dụng ở provider.

Mỗi lớp có thể thất bại riêng biệt. Vì vậy, mô tả chính xác phải có **đối tượng được bảo đảm**, **phạm vi transaction** và **các điều kiện còn nằm ngoài bảo đảm**.

## 4. Vì sao một transaction không tự kéo dài qua nhiều hệ thống?

Giả sử một consumer cần:

1. Đọc PaymentRequested từ broker.
2. Ghi payment intent vào database.
3. Gửi yêu cầu tới payment provider.
4. Cập nhật payment status.
5. Phát PaymentSucceeded.
6. Commit consumer offset hoặc ACK.

Không có lý do mặc định để coi các bước đó là một transaction atomic. Database có thể dùng transaction SQL, broker có transaction của broker, còn provider có hệ thống sổ cái riêng. Một HTTP request tới provider thường không tham gia transaction do ứng dụng của bạn quản lý.

Hệ quả là các lỗi:

- Database đã commit nhưng publish message chưa chạy.
- Broker đã nhận nhưng ACK producer bị mất.
- Consumer đã commit SQL nhưng chưa ACK broker.
- Consumer đã ACK broker nhưng SQL chưa commit.
- Provider đã xử lý nhưng response bị mất.
- Event phát lại sau khi dedup cache đã hết hạn.
- Hai consumer nhận cùng event đồng thời.
- Event tới sai thứ tự khiến trạng thái nghiệp vụ bị ghi đè.

Bảo đảm đúng một lần tại một nơi không tự di chuyển qua các ranh giới này.

## 5. Crash matrix: thực tế có thể hỏng ở đâu?

| Thời điểm crash | Business DB | ACK/offset | Nguy cơ |
| --- | --- | --- | --- |
| Trước khi nhận message | Chưa đổi | Chưa ack | Cần broker giao lại |
| Sau khi nhận, trước SQL commit | Chưa commit | Chưa ack | Code chạy lại |
| Sau SQL commit, trước ACK | Đã đổi | Chưa ack | Message giao lại, side effect có thể trùng |
| Sau ACK, trước SQL commit | Chưa commit | Đã ack | Mất công việc |
| Sau publish event, trước đánh dấu đã publish | Event có thể đã lên broker | Flag chưa ghi | Publish trùng |
| Sau API ngoài thành công, trước khi lưu kết quả | Provider đã thực hiện | Local state chưa rõ | Retry có thể nhân tác dụng |

Một thiết kế có trách nhiệm phải mô tả xử lý an toàn cho mỗi điểm lỗi có liên quan. Chỉ test luồng thành công không đủ để chứng minh hệ thống chống trùng.

### 5.1. SQL commit trước ACK là điều kiện cần nhưng chưa đủ

Nếu consumer commit SQL rồi ACK, khi crash giữa hai bước broker sẽ giao lại. Điều này giảm nguy cơ mất message, nhưng cần idempotency để lần giao lại không tạo hiệu lực thứ hai.

### 5.2. ACK trước SQL commit nguy hiểm

Nếu ACK thành công rồi database write thất bại, message không còn được giao lại theo mô hình at-most-once của chuỗi đó. Một command quan trọng có thể biến mất mà không có đường khôi phục.

## 6. Idempotency: nguyên tắc bảo vệ tác dụng nghiệp vụ

**Idempotency** ở mức nghiệp vụ nghĩa là thực hiện lại **cùng một ý định** không gây thêm tác dụng không mong muốn.

Ví dụ:

- Set order status thành CONFIRMED có thể idempotent nếu transition được kiểm soát.
- Tăng số lượng hàng bằng một đơn vị không idempotent theo mặc định.
- Gửi email không idempotent nếu gửi hai lần tạo hai email.
- Charge thẻ không idempotent trừ khi provider và hệ thống dùng khóa/thao tác chống lặp.

Idempotency không tự xuất hiện vì listener nhận eventId. Nó cần **state bền vững**, một key phù hợp và cơ chế xử lý concurrency.

### 6.1. Chọn key theo business intent, không theo network attempt

Một số loại ID khác nhau:

| ID | Vai trò |
| --- | --- |
| eventId | Nhận diện một event cụ thể |
| commandId | Nhận diện một command cần thực hiện |
| operationId | Nhận diện tác vụ nghiệp vụ qua nhiều lần retry |
| paymentId | Nhận diện payment intent/attempt theo contract |
| orderId | Nhận diện aggregate đơn hàng |
| traceId | Kết nối logs/traces, không phải business dedup key |
| aggregateVersion | Kiểm soát thay đổi và ordering |

Không dùng UUID mới cho mỗi retry nếu mục tiêu vẫn là một payment intent. Không dùng traceId thay operationId vì retry ở thời điểm khác có thể sinh trace khác.

### 6.2. Event dedup và business dedup không giống nhau

Một consumer có thể nhận:

~~~text
E100: CreateInvoice(orderId=8421)
E101: CreateInvoice(orderId=8421)
~~~

E100 và E101 có eventId khác nhau nhưng cùng business intent. Dedup theo eventId chặn redelivery của E100, nhưng không tự chặn E101. Nếu nghiệp vụ yêu cầu mỗi order có một hóa đơn chính thức, còn cần **UNIQUE business key** tương ứng.

Ngược lại, không nên máy móc đặt UNIQUE(orderId) nếu sản phẩm cho phép nhiều hóa đơn điều chỉnh hoặc nhiều hóa đơn cho từng phần của một đơn. Khóa duy nhất phải phản ánh đúng quy tắc nghiệp vụ.

### 6.3. Cùng key, payload khác

Ví dụ hai yêu cầu cùng idempotency key nhưng khác amount:

~~~text
Key: payment-order-8421
Request A: amount 250000 VND
Request B: amount 900000 VND
~~~

Provider hoặc service không nên coi cả hai là cùng một request hợp lệ mà không kiểm tra. Cần so sánh payload hoặc thông tin bất biến theo contract và từ chối conflict khi key bị tái sử dụng với nội dung khác.

### 6.4. Idempotency TTL và replay

Một dedup table chỉ giữ eventId trong 30 phút không bảo vệ được replay sau một tuần. TTL phải được cân nhắc cùng thời hạn retry, retention của broker, backfill, lịch sử đối soát và bảo vệ invariant lâu dài.

Không phải mọi key cần giữ vô hạn, nhưng với nghiệp vụ tài chính quan trọng, một business uniqueness constraint ở dữ liệu bền vững thường đáng tin hơn chỉ dùng cache ngắn hạn.

## 7. Inbox pattern và atomic update trong một database

Một cách phổ biến để xây **idempotent consumer** là lưu marker đã xử lý event trong cùng database transaction với thay đổi nghiệp vụ.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    invoice_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL
);
~~~

Luồng logic:

~~~text
BEGIN TRANSACTION
  INSERT processed_messages(consumer_name, event_id)
  ON CONFLICT DO NOTHING

  Nếu event đã xử lý:
      COMMIT và ACK, không tạo effect mới

  Nếu event mới:
      Validate business transition
      INSERT/UPDATE invoices với ràng buộc UNIQUE
COMMIT TRANSACTION
ACK message
~~~

Điều then chốt:

1. Inbox marker và business update **cùng một transaction**.
2. UNIQUE được database thực thi, không chỉ check trong code.
3. ACK/offset chỉ được thực hiện sau durable commit phù hợp.
4. Nếu có crash trước commit, transaction rollback và redelivery an toàn.
5. Nếu có crash sau commit trước ACK, marker chặn tạo effect lần thứ hai.

### 7.1. Cẩn thận race condition

Hai consumer cùng SELECT và cùng thấy event chưa xử lý có thể đều chạy update. Chỉ dùng SELECT rồi INSERT không có UNIQUE hoặc lock là không an toàn.

Một ràng buộc UNIQUE hoặc atomic insert/upsert trong transaction giúp chọn ra một xử lý được commit; những consumer khác sẽ thấy conflict hoặc chờ theo semantics database. Nếu logic còn cập nhật aggregate song song, cần version check, lock hoặc optimistic concurrency phù hợp.

### 7.2. Marker phải có ý nghĩa rõ

Nếu chỉ lưu marker “đã nhận” rồi ACK trước khi business effect thành công, hệ thống có thể làm mất công việc. Cần phân biệt:

- Event đã nhận.
- Operation đã lưu bền vững.
- State đã commit.
- External effect chưa rõ.
- Workflow đạt kết quả cuối.
- Broker ACK/offset đã commit.

Không đánh tráo các trạng thái để chỉ còn một cờ processed đơn giản khi thực tế còn bước cần hoàn tất.

## 8. Transactional Outbox: không mất event giữa database và broker

Một lỗi thường gặp:

~~~text
Order Service:
  UPDATE order status='CONFIRMED'
  COMMIT database
  publish OrderConfirmed event
  -- crash trước publish --
~~~

Order đã được xác nhận nhưng các consumer không biết. Đây là **dual-write problem** vì database update và broker publish không nằm trong cùng local transaction.

**Transactional Outbox** ghi business state và ý định phát event trong cùng SQL transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = '8421';

INSERT INTO outbox (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    'evt-order-8421-v3',
    '8421',
    'OrderConfirmed',
    '{"orderId":"8421","version":3}',
    now()
);

COMMIT;
~~~

Một worker hoặc CDC connector đọc outbox và publish. Nếu publish thành công nhưng worker crash trước khi đánh dấu sent, nó có thể gửi lại, nên consumer vẫn phải idempotent.

Outbox giúp giảm nguy cơ **business commit rồi quên publish**, nhưng không hứa broker chỉ nhận event một lần trong mọi tình huống.

### 8.1. Outbox cần vận hành thế nào?

Một triển khai production cần:

- EventId ổn định qua retry.
- Cơ chế claim/lease hoặc cách phân phối không ghi trùng sai mục đích.
- Retry có giới hạn/backoff và cơ chế điều tra khi lỗi kéo dài.
- Theo dõi outbox backlog, thời gian pending và số lỗi publish.
- Chính sách cleanup/retention tương thích khả năng khôi phục.
- Version theo aggregate khi thứ tự quan trọng.
- Cách xử lý schema evolution, poison message và dữ liệu nhạy cảm.

CDC không xóa vấn đề replay và duplicate. Connector có thể restart, snapshot lại hoặc gửi chậm; downstream vẫn cần dedup và ordering policy.

## 9. Kafka exactly-once processing có phạm vi gì?

Kafka hỗ trợ một số cơ chế nhằm đạt **exactly-once processing semantics** cho pipeline nằm trong phạm vi Kafka:

- **Idempotent producer** giảm duplicate append từ retry của producer theo những điều kiện hỗ trợ.
- **Transactional producer** cho phép commit hoặc abort một tập ghi Kafka.
- **Consumer offsets trong Kafka transaction** giúp kết hợp tiến độ đọc với output Kafka đã được ghi.
- **Producer fencing** ngăn instance cũ tiếp tục ghi với cùng transactional identity trong tình huống failover phù hợp.
- **Read-committed consumer isolation** giúp consumer phù hợp không đọc các record của transaction đã abort.

Trong Kafka-to-Kafka processing:

~~~mermaid
flowchart LR
    A[("Topic A")] --> P["Kafka Processor"]
    P --> B[("Topic B")]
    P --> S[("Kafka State Store")]
~~~

Một processor có thể đọc input, biến đổi, ghi output và commit consumed offsets theo transaction Kafka. Sau crash, code có thể chạy lại nhưng kết quả được consumer quan sát theo semantics transactional đã cấu hình.

**Giới hạn quyết định:** SQL transaction của PostgreSQL hoặc lệnh charge qua HTTP **không tự trở thành thành phần của Kafka transaction**. Chỉ vì Kafka Streams bật exactly-once không có nghĩa side effect ở một API ngoài được rollback khi transaction Kafka abort.

### 9.1. Idempotent producer không bằng full EOS

Idempotent producer giải quyết một số duplicate append do producer retry. Nó không tự gom consumer offset và output thành một transaction, và cũng không bảo vệ database ngoài Kafka.

### 9.2. Consumer isolation quan trọng

Nếu đọc các kết quả transactional, consumer cần cấu hình isolation phù hợp, ví dụ read-committed khi muốn tránh record đã abort. Hệ thống có thể kết hợp nhiều consumer/framework, vì vậy phải kiểm tra cấu hình thực, source topic, sink topic và phiên bản thư viện.

### 9.3. Cách viết một phát biểu bảo đảm có trách nhiệm

Thay vì ghi “Kafka bảo đảm exactly-once cho toàn hệ thống”, hãy ghi:

“Trong pipeline Kafka read-process-write này, input offsets và output records được commit atomically theo transaction Kafka ở các điều kiện cấu hình đã xác định. Side effects trên database ngoài Kafka và provider API được xử lý riêng bằng local transaction, idempotency và reconciliation.”

Phát biểu thứ hai mô tả ranh giới kiểm chứng được.

## 10. Commit offset và SQL transaction: điểm lỗi kinh điển

Consumer Kafka đọc event và cập nhật PostgreSQL có ba cách điển hình.

### 10.1. Commit offset trước SQL

~~~text
read event
commit Kafka offset
write PostgreSQL
crash trước COMMIT SQL
~~~

Kafka có thể coi input đã xử lý, trong khi business database chưa ghi. Nếu không có cơ chế khôi phục khác, tác dụng nghiệp vụ có thể bị mất.

### 10.2. Commit SQL trước offset

~~~text
read event
write PostgreSQL
COMMIT SQL
crash trước Kafka offset commit
~~~

Message được đọc lại sau restart. Nếu xử lý không idempotent, cùng event có thể tăng tiền, tạo hóa đơn hoặc chuyển trạng thái lần nữa.

### 10.3. Commit SQL có Inbox rồi commit offset

~~~text
read event
BEGIN SQL
  INSERT inbox marker with UNIQUE(eventId, consumerName)
  apply business update if new event
COMMIT SQL
commit Kafka offset
~~~

Sau crash trước offset, lần replay thấy marker và không tạo lại effect SQL. **Không có một distributed transaction tự động giữa Kafka và PostgreSQL**; thay vào đó, replay trở thành an toàn nhờ idempotency và transaction cục bộ.

Đây là khác biệt quan trọng giữa **exactly-once delivery** và **effectively-once effect trong một ranh giới dữ liệu**.

## 11. External side effects: trường hợp khó nhất

Các tác dụng như thanh toán, gửi email, SMS, tạo shipment hoặc ghi vào SaaS bên thứ ba không nhất thiết tham gia transaction local.

~~~text
Consumer nhận PaymentRequested
Consumer gọi Payment Provider
Provider xử lý thành công
Response bị mất
Consumer timeout
Consumer retry cùng thao tác
~~~

Nếu retry bằng paymentId mới, nguy cơ thu hai lần. Nếu không retry và cũng không đối soát, hệ thống có thể treo ở trạng thái chưa biết.

Cần phối hợp:

1. **Business operation ID ổn định** lưu bền trước khi gọi.
2. **Idempotency key phía provider** nếu được hỗ trợ.
3. **Lưu request parameters** để không đổi amount/currency khi retry cùng key.
4. **State machine rõ ràng** cho PENDING, SUCCEEDED, FAILED, UNKNOWN.
5. **API tra cứu kết quả hoặc callback xác thực** từ provider.
6. **Reconciliation job** cho thao tác chưa rõ hoặc callback bị mất.
7. **Audit và cảnh báo** cho các trường hợp kéo dài.

Nếu provider không hỗ trợ idempotency hoặc query status đáng tin, cần **thừa nhận giới hạn bảo đảm** và thay đổi hợp đồng tích hợp hoặc áp dụng quy trình xử lý rủi ro; broker configuration không thể thay thế điều đó.

### 11.1. Vì sao timeout không đồng nghĩa payment thất bại?

Khi client không nhận response, provider có thể chưa nhận, đang xử lý, đã xử lý thành công hoặc đã từ chối nhưng response mất. Không có một sự thật duy nhất suy ra từ timeout.

Một trạng thái **PENDING_CONFIRMATION** kèm operationId cho phép tiếp tục đối soát. Không đánh dấu FAILED chỉ vì network read timeout nếu có thể đã charge thành công.

### 11.2. Email cũng không mặc nhiên exactly-once

Nếu gửi email thành công nhưng consumer crash trước khi ghi local status, retry có thể gửi lần nữa. Một số provider có idempotency trong phạm vi thời gian nhất định; số khác không. Có thể giảm duplicate qua unique notification key, tracking và trạng thái gửi, nhưng không hứa chắc người nhận chỉ thấy một email khi không kiểm soát hoàn toàn bên ngoài.

## 12. Ví dụ đầy đủ: phát hành hóa đơn từ OrderConfirmed

Giả định nghiệp vụ quy định một đơn hàng chỉ có một hóa đơn chính thức.

Order Service phát event:

~~~json
{
  "eventId": "evt-order-8421-confirmed-v3",
  "eventType": "OrderConfirmed",
  "aggregateId": "8421",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-11T10:45:00Z",
  "payload": {
    "orderId": "8421",
    "customerId": "C17"
  }
}
~~~

Invoice Service dùng database riêng:

~~~sql
CREATE TABLE invoices (
    invoice_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    invoice_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL
);

CREATE TABLE inbox (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Quy trình transaction:

1. Consumer nhận event.
2. Insert inbox marker dựa trên consumerName và eventId.
3. Nếu marker đã tồn tại, không tạo invoice mới.
4. Nếu event mới, kiểm tra điều kiện nghiệp vụ và insert invoice.
5. Ràng buộc UNIQUE(orderId) trong ví dụ bảo vệ trường hợp hai event khác nhau cùng yêu cầu tạo hóa đơn.
6. Commit local SQL transaction.
7. ACK message sau khi commit.

### 12.1. Nếu crash sau commit trước ACK

~~~text
Lần 1:
  INSERT inbox E100
  INSERT invoice(order=8421)
  COMMIT
  crash trước ACK

Lần 2:
  Broker redeliver E100
  INSERT inbox E100 -> conflict
  Không tạo invoice mới
  ACK
~~~

Listener method có thể chạy hai lần; database chỉ có một hiệu lực theo transaction/unique constraint.

### 12.2. Nếu hai event khác nhau cùng orderId

Nếu E100 và E101 cùng yêu cầu phát hành một invoice cho orderId 8421, inbox nhận thấy đây là hai event mới. **Business UNIQUE(orderId)** mới là guard cuối cùng ngăn hai hóa đơn trong bối cảnh đã giả định.

Nếu domain thực tế cho phép nhiều hóa đơn điều chỉnh hoặc từng phần, khóa business phải được thiết kế khác; không chép UNIQUE(orderId) máy móc.

## 13. Ví dụ Java/Spring Boot về consumer idempotent

Ví dụ minh họa logic, chưa phải một project chạy hoàn chỉnh:

~~~java
@Service
public class OrderConfirmedHandler {

    private final InboxRepository inbox;
    private final InvoiceRepository invoices;

    public OrderConfirmedHandler(
            InboxRepository inbox,
            InvoiceRepository invoices) {
        this.inbox = inbox;
        this.invoices = invoices;
    }

    @Transactional
    public void handle(OrderConfirmed event) {
        boolean inserted = inbox.tryInsert(
            "invoice-consumer",
            event.eventId());

        if (!inserted) {
            // Đã commit event trước đó: duplicate delivery.
            return;
        }

        invoices.createIfAbsentForOrder(
            event.orderId(),
            event.customerId());
    }
}
~~~

Các điều kiện để ý tưởng trên thực sự an toàn:

- Inbox và invoice được cập nhật trong **cùng transaction**.
- tryInsert phải atomic dựa trên UNIQUE hoặc upsert; không chỉ SELECT rồi INSERT thiếu khóa.
- createIfAbsentForOrder có ràng buộc business unique hoặc transaction isolation/locking phù hợp.
- Consumer chỉ ACK/commit offset khi transaction thành công; phải hiểu semantics của listener framework.
- Crash sau COMMIT nhưng trước ACK dẫn đến redelivery và no-op an toàn.
- Crash trước COMMIT khiến toàn bộ marker và business update rollback.
- Nếu logic gọi external API, annotation Transactional **không tự rollback provider**; cần operation state/idempotency/reconciliation riêng.
- Cần xử lý schema validation, out-of-order events, authorization và logging không chứa secret.

**Mục tiêu là một hiệu lực được commit, không phải ngăn listener method chạy lại.**

## 14. Ordering: Exactly-once không bảo vệ thứ tự nghiệp vụ

Ngay cả khi mỗi event chỉ gây một hiệu lực, kết quả vẫn có thể sai nếu consumer áp dụng event cũ sau event mới.

~~~text
OrderCreated      version 1
OrderConfirmed    version 2
OrderCancelled    version 3
~~~

Nếu consumer nhận version 3 rồi version 2, nó không được ghi CONFIRMED chỉ vì version 2 chưa được lưu trong inbox. Cần:

- Aggregate version hoặc sequence trong event.
- Kiểm tra version trước khi update.
- Conditional update hoặc optimistic locking.
- Xử lý gap và replay khi event cần thứ tự.
- State machine để không có transition bất hợp lệ.

Partition key theo aggregateId có thể giúp giữ thứ tự trong phạm vi partition của một broker cụ thể, nhưng không tạo thứ tự toàn cục và không tự giải quyết reprocessing từ nhiều nguồn.

### 14.1. Replay không đồng nghĩa làm lại mọi side effect

Khi replay event lịch sử để dựng lại read model, không được vô tình gửi email cũ hoặc charge tiền lại.

Nên phân biệt:

- **Projection replay:** dựng trạng thái đọc từ event lịch sử.
- **Command retry:** thử lại cùng operation theo idempotency contract.
- **New business command:** một ý định nghiệp vụ mới thật sự.

Cần chế độ replay có kiểm soát, event version, key ổn định và chính sách dedup/retention phù hợp.

## 15. DLQ, poison message và trách nhiệm xử lý

Một message sai schema hoặc vi phạm invariant có thể thất bại mãi. Retry vô hạn làm consumer lag và tốn tài nguyên; ACK bỏ qua lại có thể mất nghiệp vụ.

Có thể dùng:

- Số attempt tối đa và backoff có jitter.
- Dead-letter queue (DLQ) hoặc quarantine có lý do lỗi.
- Metrics về DLQ backlog, age, retry count và consumer lag.
- Runbook, người chịu trách nhiệm kiểm tra và replay an toàn.
- Cơ chế chuyển workflow sang trạng thái cần điều tra nếu có side effect quan trọng.

**Đưa message vào DLQ không đồng nghĩa nghiệp vụ đã hoàn tất.** Với PaymentRequested, cần có owner tiếp tục đối soát; với telemetry ít quan trọng, chính sách bỏ qua có thể được cho phép. Phân loại theo tác động thực tế.

## 16. Phối hợp Outbox + Inbox để bảo vệ hai đầu

Một mô hình phổ biến:

~~~mermaid
flowchart LR
    O[("Order DB + Outbox")] --> Pub["Outbox Publisher"]
    Pub --> B[("Broker")]
    B --> C["Invoice Consumer"]
    C --> I[("Inbox + Invoice DB")]
~~~

**Producer:** ghi business transaction và outbox record atomically; publisher phát event có thể lặp.

**Consumer:** nhận event, ghi inbox marker và business effect cùng một transaction; ACK sau commit.

Kết quả mong muốn: không bỏ quên event sau business commit và không nhân đôi business effect vì redelivery, trong giới hạn dữ liệu/transaction/retention đã định.

Giới hạn còn lại:

- Broker có thể backlog hoặc tạm unavailable.
- Outbox publisher có thể phát lại.
- Consumer có thể xử lý code nhiều lần.
- Event ordering cần bảo vệ riêng.
- External APIs chưa thuộc transaction này.
- Mọi thao tác phải có cơ chế quan sát/khôi phục và owner rõ ràng.

Đây không phải “transaction xuyên toàn hệ thống”, mà là **chuỗi các giao dịch cục bộ được thiết kế để có thể retry an toàn**.

## 17. Các cấp bảo đảm có thể viết rõ trong API/event contract

Một hợp đồng kỹ thuật tốt nên nói:

**Ví dụ 1 — Read model**

“Consumer có thể nhận OrderChanged nhiều lần. Với cùng eventId, effect cập nhật read model được ghi không quá một lần trong DB transaction của consumer. Event có aggregateVersion để không áp dụng bản cũ. Projection có thể chậm so với Order Service.”

**Ví dụ 2 — Hóa đơn**

“Consumer xử lý at-least-once. Với mỗi business key đã quy định, database invoice ngăn tạo bản ghi chính thức trùng qua unique constraint và transaction. Nếu phát hành hóa đơn sang nhà cung cấp bên ngoài, tính duy nhất phụ thuộc thêm vào provider API contract.”

**Ví dụ 3 — Thanh toán**

“Payment intent có paymentId ổn định và idempotency key dùng xuyên retry. Sau timeout từ provider, trạng thái được giữ pending/unknown đến khi tra cứu hoặc đối soát có kết quả. Hệ thống không suy ra thất bại nghiệp vụ chỉ từ network timeout.”

**Ví dụ 4 — Kafka transformation**

“Input offsets và output records được commit theo Kafka transaction trong pipeline đã cấu hình; bảo đảm không bao phủ các side effects ở hệ thống ngoài Kafka.”

Những câu phát biểu này có thể kiểm chứng bằng test và metrics. “Exactly-once everywhere” không có ranh giới thì không thể kiểm chứng nghiêm túc.

## 18. Thử nghiệm bằng fault injection

Không chỉ test happy path, cần mô phỏng crash ở những vị trí gây tranh chấp giữa transaction và ACK:

| Kịch bản | Điều phải kiểm chứng |
| --- | --- |
| Producer không nhận ACK dù broker đã ghi | Retry không tạo hiệu lực trùng ngoài giới hạn đã công bố |
| Outbox publisher crash sau publish trước mark-sent | Consumer chặn duplicate |
| Consumer crash trước DB commit | Không có marker/effect commit dở |
| Consumer crash sau DB commit trước ACK | Redelivery không tạo effect DB lần hai |
| Hai consumer cùng nhận event | Unique/lock/transaction chặn race |
| Hai event khác ID nhưng cùng business key | Business invariant vẫn đúng |
| External charge thành công nhưng response mất | Truy vấn/cùng key, không charge bằng intent mới |
| Event đến sai thứ tự | Version/state guard không ghi đè sai |
| Replay sau thời gian dài | Không kích hoạt side effect cũ |
| Dedup key hết hạn | Chính sách retention và uniqueness bảo vệ hoặc báo rủi ro |
| Message vào DLQ | Có trạng thái ngoại lệ và người xử lý |
| Restart sau khi workflow pending | Tiến trình tiếp tục từ state bền vững |

Với ứng dụng Java/Spring Boot, nên có **integration test** sử dụng database thật hoặc môi trường gần thật, vì mock repository thường không tái tạo race condition của UNIQUE, isolation hay commit ordering.

### 18.1. Ví dụ test crash sau commit

~~~text
Given:
  Event E100 = OrderConfirmed(orderId=8421)
  Chưa có hóa đơn của order 8421

When:
  Consumer xử lý E100 và COMMIT SQL
  Giả lập crash trước broker ACK
  Broker phát lại E100

Then:
  Số hóa đơn của order 8421 = 1
  Inbox marker của E100 tồn tại
  Consumer ACK an toàn lần phát lại
  Không phát sinh side effect ngoài ý muốn
~~~

Nên mở rộng test cho concurrency và eventId khác nhau nhưng cùng business intent.

## 19. Quan sát và giám sát bảo đảm

Các chỉ số vận hành hữu ích:

| Metrics | Mục đích |
| --- | --- |
| Message redelivery rate | Phát hiện broker hoặc consumer retry nhiều |
| Inbox duplicate hit rate | Số event trùng được chặn |
| Business key conflicts | Phát hiện ý định nghiệp vụ trùng dù event khác |
| Outbox backlog và oldest age | Event chưa publish |
| Consumer lag và DLQ backlog | Message chưa hoàn tất |
| Retry attempts và retry budget | Tải do retry |
| Transaction abort/producer fencing | Sự cố transaction broker nếu dùng |
| Reconciliation pending count/age | Tác vụ bên ngoài chưa rõ kết quả |
| Duplicate invoice/payment incidents | Sai lệch nghiệp vụ thực tế |
| Out-of-order/version conflict | Sự kiện đến sai tiến độ |
| Time-to-terminal outcome | Thời gian workflow kết thúc sau khi accepted |

Một hệ thống có rất nhiều dedup hit nhưng **không có duplicate effect** có thể đang tự bảo vệ tốt trước lỗi retry. Tuy nhiên cần tìm nguyên nhân redelivery tăng để tránh lãng phí tài nguyên.

Với payment, chỉ thống kê message broker là chưa đủ. Phải theo dõi **kết quả giao dịch, refund, chargeback, reconciliation và số operation pending quá hạn** theo nguồn sự thật có thẩm quyền.

## 20. Sai lầm thường gặp

**Sai lầm 1: “Broker hứa exactly-once nên không cần idempotency.”**  
Sai khi có state hoặc side effect ngoài transaction boundary.

**Sai lầm 2: “ACK là đã hoàn thành nghiệp vụ.”**  
ACK chỉ phản ánh việc xác nhận theo broker/consumer contract.

**Sai lầm 3: “Commit offset trước sẽ nhanh và an toàn.”**  
Có nguy cơ mất business effect nếu crash trước DB commit.

**Sai lầm 4: “Đã có inbox thì không cần business UNIQUE.”**  
Inbox dedup cùng eventId; event khác vẫn có thể cùng ý định nghiệp vụ.

**Sai lầm 5: “Đã có business UNIQUE thì mọi transition đều đúng.”**  
Cần ordering, version và state machine riêng.

**Sai lầm 6: “Dùng Kafka transaction rollback được REST payment.”**  
External provider không tự tham gia Kafka transaction.

**Sai lầm 7: “Transactional Outbox chỉ phát event một lần.”**  
Publisher có thể gửi lại khi mất ACK hoặc crash sau publish.

**Sai lầm 8: “Transactional annotation bảo vệ API ngoài.”**  
Local SQL transaction không rollback external side effect không tham gia.

**Sai lầm 9: “Timeout chứng minh provider chưa thực hiện.”**  
Kết quả có thể đã xảy ra, response bị mất. Cần query/reconciliation.

**Sai lầm 10: “Dedup cache TTL một giờ đủ cho mọi trường hợp.”**  
Replay sau nhiều ngày có thể vượt TTL. Chọn retention theo lifecycle.

**Sai lầm 11: “Exactly-once tự sắp thứ tự event.”**  
Ordering và transition consistency là bài toán riêng.

**Sai lầm 12: “DLQ là xử lý xong.”**  
Workflow quan trọng vẫn phải có chủ sở hữu trạng thái cuối hoặc xử lý ngoại lệ.

## 21. Quy trình thiết kế thực dụng

1. Xác định **tác dụng nghiệp vụ** cần bảo vệ: thay đổi state, tạo hóa đơn, charge tiền, gửi email.
2. Xác định **nguồn sự thật** và owner: database nào, service nào, provider nào.
3. Vẽ các **transaction boundary**: broker, local DB, API ngoài, cache.
4. Chọn delivery semantics phù hợp, không chọn theo khẩu hiệu.
5. Thiết kế **eventId + operationId + business key** rõ phạm vi.
6. Dùng inbox và local transaction để xử lý idempotent ở consumer.
7. Dùng outbox nếu cần phát event gắn với business commit.
8. Thiết kế provider idempotency và reconciliation cho external side effect.
9. Thiết kế ordering, aggregate version, replay và state transition.
10. Xử lý poison messages, DLQ, timeout, retry và các trạng thái pending.
11. Kiểm chứng bằng crash/fault-injection tests ở từng ranh giới.
12. Ghi ADR nêu rõ **điều được bảo đảm và điều không được bảo đảm**.

Không phải use case nào cũng cần tất cả pattern. Một thống kê không quan trọng có thể chấp nhận mất vài message, trong khi thu tiền và hóa đơn đòi hỏi bảo vệ nghiêm ngặt. Mức phức tạp nên tương xứng hậu quả lỗi.

## 22. Mẫu ADR cho xử lý event tạo hóa đơn

~~~markdown
# ADR: Chống tạo hóa đơn trùng do redelivery

Trạng thái: Accepted (ví dụ)

## Bối cảnh
- Order phát OrderConfirmed qua broker.
- Broker có thể giao event lại sau lỗi.
- Mỗi đơn chỉ có một hóa đơn chính thức theo nghiệp vụ.
- Invoice lưu PostgreSQL riêng.

## Phương án
A. ACK trước SQL commit.
B. SQL commit rồi ACK, không idempotency.
C. SQL transaction chứa inbox + invoice,
   dùng UNIQUE trên business key, ACK sau COMMIT.

## Quyết định
Chọn C. Producer dùng transactional outbox.

## Bảo đảm
- Same eventId không tạo tác dụng DB lần hai.
- Event khác cùng business key được unique guard.
- Crash trước/sau SQL commit có đường retry an toàn.

## Giới hạn
- Không có transaction nguyên tử giữa broker và Invoice DB.
- External provider không tự được bảo vệ.
- Ordering và replay có xử lý riêng.

## Kiểm chứng
- Integration tests crash trước/sau COMMIT và trước ACK.
- Test concurrent consumers.
- Test replay và business key conflict.
- Metrics DLQ, outbox age, dedup hits.
~~~

ADR nên mô tả cả cái **không** được bảo đảm, để đội vận hành không hiểu sai kỳ vọng.

## 23. Bài tập tình huống

### Bài tập A — Consumer tạo hóa đơn

Broker giao OrderConfirmed nhiều lần. Invoice lưu PostgreSQL. Thiết kế inbox table, business unique constraint, transaction boundary và thời điểm ACK. Giải thích vì sao eventId khác nhưng cùng orderId vẫn cần bảo vệ.

### Bài tập B — Thanh toán bị timeout

Payment Consumer gọi provider; provider đã charge thành công nhưng response mất. Sau restart, consumer nhận lại message. Hãy xác định operationId phải giữ thế nào, state nào được lưu, cách query/reconcile, và điều gì xảy ra nếu provider không hỗ trợ idempotency.

### Bài tập C — Kafka Streams

Một ứng dụng đọc OrderEvents, tổng hợp doanh thu rồi ghi RevenueAggregates, cả hai đều là Kafka topics. Giải thích phạm vi Kafka EOS. Sau đó thêm PostgreSQL sink và chỉ ra vì sao phải thiết kế bảo đảm tại ranh giới database ngoài.

### Bài tập D — Replay lịch sử

Nhóm replay 90 ngày OrderConfirmed để xây lại báo cáo. Consumer cũ cũng gửi email. Đề xuất kiến trúc replay projection mà không gửi lại email cũ; phân biệt event, command và external effect.

### Bài tập E — Race condition

Hai consumer cùng SELECT thấy event chưa xử lý rồi cùng cập nhật dữ liệu. Giải thích vì sao check trước khi insert chưa an toàn và cách dùng UNIQUE/upsert/transaction để giải quyết.

## 24. Tự kiểm tra kiến thức

1. At-most-once khác at-least-once như thế nào?
2. Vì sao exactly-once processing không nhất thiết là code chỉ chạy một lần?
3. Broker ACK cho producer xác nhận điều gì?
4. Consumer ACK có đồng nghĩa database đã commit không?
5. Nếu SQL commit trước ACK rồi consumer crash, điều gì xảy ra?
6. Inbox marker cần nằm cùng transaction với dữ liệu nào?
7. Vì sao event dedup key khác business idempotency key?
8. Kafka transaction bảo vệ phần nào trong read-process-write pipeline?
9. Vì sao external database/API không tự nằm trong Kafka transaction?
10. Transactional Outbox giải quyết dual-write problem nào?
11. Vì sao publisher outbox vẫn có thể phát event trùng?
12. Sau payment provider timeout, vì sao không được ghi FAILED ngay?
13. Dedup retention phải liên hệ với replay như thế nào?
14. Exactly-once effect có ngăn event sai thứ tự không?
15. Một message vào DLQ có nghĩa workflow đã kết thúc chưa?
16. Cần kiểm thử gì khi crash sau business COMMIT trước broker ACK?
17. Loại metrics nào phản ánh tác dụng nghiệp vụ trùng thay vì chỉ duplicate message?
18. Câu phát biểu bảo đảm đáng tin phải nói rõ những ranh giới nào?

## 25. Checklist thiết kế

- [ ] Xác định rõ exactly-once đối với **điều gì**.
- [ ] Mô tả phạm vi transaction của broker, DB và API ngoài.
- [ ] Không ACK/commit offset sớm trước durable state phù hợp.
- [ ] Có eventId, operationId và business key riêng khi cần.
- [ ] Consumer idempotent với UNIQUE/transaction hoặc cơ chế tương đương.
- [ ] Có xử lý concurrency và race condition.
- [ ] Producer có chiến lược không mất event sau business commit.
- [ ] External API có provider idempotency, status query hoặc reconciliation.
- [ ] Có state machine, version và quy tắc event trễ/sai thứ tự.
- [ ] Có retention/replay policy và dedup TTL phù hợp.
- [ ] Có DLQ, cảnh báo và owner xử lý trường hợp chưa xác định.
- [ ] Có fault injection và integration tests tại các điểm commit.
- [ ] Không hứa exactly-once end-to-end khi bảo đảm chỉ nằm trong broker.

## 26. Kết luận

**Exactly-once là một bảo đảm có phạm vi, không phải phép màu xóa mọi duplicate, retry và crash khỏi hệ thống phân tán.** Có thể đạt hiệu lực được commit đúng một lần trong transaction của một nền tảng, nhưng khi đi qua broker, database và API bên ngoài, từng ranh giới cần cơ chế bảo vệ riêng.

Mục tiêu thực dụng là thiết kế sao cho **message có thể được giao lại, code có thể chạy lại, nhưng bất biến nghiệp vụ vẫn đúng**. Để làm được điều đó, hãy kết hợp idempotency, ràng buộc dữ liệu, local transaction, transactional outbox/inbox, ordering guards, provider idempotency và reconciliation; đồng thời ghi rõ điều kiện và giới hạn của từng bảo đảm.

Hệ thống tốt không tuyên bố rằng không bao giờ cần retry, mà chứng minh được rằng **retry không tạo thêm tác dụng sai**, các kết quả chưa rõ có thể được xác minh và các workflow quan trọng có chủ sở hữu chịu trách nhiệm hoàn tất.