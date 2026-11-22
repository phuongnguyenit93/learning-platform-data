# Không đồng nhất exactly once với không duplicate tuyệt đối

Trong một hệ thống Spring Kafka, cụm từ **exactly-once semantics (EOS)** mô tả một bảo đảm về kết quả xử lý trong một phạm vi giao dịch được xác định. Nó không có nghĩa là một sự kiện không bao giờ được gửi lại, listener không bao giờ chạy lại, hoặc không có hai thông điệp giống nhau xuất hiện ở bất kỳ đâu trong hệ thống.

Để thiết kế vận hành đúng, cần phân biệt ba hiện tượng:

1. **Giao nhận lặp (duplicate delivery):** cùng một bản ghi được consumer nhận hoặc xử lý lại, thường do retry, rebalance hoặc offset chưa được commit.
2. **Bản ghi lặp (duplicate record):** cùng một sự kiện nghiệp vụ được producer ghi thành nhiều bản ghi Kafka, có thể do ứng dụng gửi lại lệnh sau timeout hoặc do replay.
3. **Tác động nghiệp vụ lặp (duplicate side effect):** một hành động như trừ tiền, tạo đơn hàng hoặc gửi email xảy ra nhiều lần cho cùng một sự kiện.

Ba hiện tượng có liên quan nhưng không đồng nghĩa. Một consumer có thể nhận một bản ghi nhiều lần nhưng chỉ cập nhật database một lần nhờ idempotency. Ngược lại, producer có thể ghi hai bản ghi khác offset cho cùng một `eventId`; Kafka vẫn coi đó là hai bản ghi hợp lệ, dù nội dung giống nhau.

## 1. Exactly-once thực sự bảo đảm điều gì?

Kafka cung cấp các cơ chế idempotent producer và transaction để xây dựng luồng xử lý có exactly-once semantics trong phạm vi Kafka. Trường hợp điển hình là **consume-process-produce**: một ứng dụng đọc bản ghi từ topic đầu vào, xử lý, ghi bản ghi đầu ra sang topic khác và commit offset đầu vào trong cùng một Kafka transaction.

Khi transaction commit, bản ghi đầu ra và offset đầu vào cùng có hiệu lực. Khi transaction abort, bản ghi đầu ra của transaction đó không được consumer dùng `read_committed` nhìn thấy và offset đầu vào không được tiến lên như một giao dịch thành công. Vì vậy, nếu ứng dụng chạy lại sau lỗi, bản ghi đầu vào có thể được xử lý lại và tạo một lần thử mới, trong khi chỉ kết quả của transaction đã commit được công bố cho consumer đọc theo isolation phù hợp.

Đây là bảo đảm về **kết quả đã commit và được quan sát trong Kafka**, không phải lời hứa rằng code nghiệp vụ chỉ chạy đúng một lần. Listener có thể được gọi lại sau khi transaction bị abort. Side effect ngoài Kafka cũng không tự động nằm trong transaction đó.

Ví dụ: dịch vụ `order-enricher` đọc `orders.raw`, bổ sung dữ liệu và ghi vào `orders.enriched`. Nếu output và offset được commit trong cùng transaction, consumer `read_committed` của `orders.enriched` chỉ quan sát output từ transaction đã commit. Nếu ứng dụng chết trước commit, lần xử lý đó có thể chạy lại; output của transaction bị abort không trở thành kết quả đã commit.

### 1.1. Phạm vi bảo đảm

| Phạm vi | Kafka có thể bảo đảm điều gì? | Điều vẫn cần xử lý ở ứng dụng |
|---|---|---|
| Producer retry trong cùng producer session với idempotence | Kafka nhận biết sequence của producer để loại bỏ bản ghi gửi lại do retry giao thức | Client gửi lại cùng lệnh nghiệp vụ như một lần gửi mới vẫn có thể tạo bản ghi mới |
| Ghi nhiều bản ghi Kafka trong một transaction | Các bản ghi của transaction được commit hoặc abort cùng nhau | Code trước/sau transaction có thể chạy lại; dịch vụ ngoài Kafka không tự tham gia transaction |
| Consume-process-produce trong Kafka transaction | Offset đầu vào và output Kafka có thể commit nguyên tử | Listener có thể được gọi lại; tác động database, HTTP, email cần cơ chế riêng |
| Consumer dùng `read_committed` | Chỉ đọc bản ghi thuộc transaction đã commit, bỏ qua bản ghi transaction bị abort | Consumer vẫn có thể nhận cùng một bản ghi đã commit lần nữa nếu offset/luồng xử lý được khởi động lại ở vị trí cũ |
| Replay hoặc backfill | Kafka cho phép đọc lại dữ liệu theo offset hoặc ghi lại dữ liệu vào topic | Replay có thể lặp lại tác động nghiệp vụ nếu consumer không idempotent |

Vì vậy, khi nói một luồng có exactly-once, phải chỉ rõ đầu vào, đầu ra, ranh giới transaction, isolation level và loại side effect được bao phủ. Không nên dùng cụm từ này như thuộc tính chung cho toàn bộ hệ thống phân tán.

## 2. Phân biệt các cơ chế thường bị gọi chung là exactly once

### 2.1. Idempotent producer

Producer idempotent giúp chống duplicate do retry ở tầng giao thức Kafka. Kafka gắn định danh producer và sequence cho các batch. Nếu producer phải gửi lại một batch do không nhận được phản hồi, broker có thể nhận biết đó là sequence đã xử lý và tránh ghi batch lần thứ hai.

Trong Spring Kafka, idempotence có thể được bật trực tiếp:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
```

Khi dùng Kafka transaction, idempotence là một phần của cơ chế producer giao dịch. Với producer không giao dịch, cần bảo đảm các thuộc tính tương thích theo phiên bản Kafka client; `acks=all`, retry và giới hạn in-flight request phải đáp ứng yêu cầu của idempotent producer. Kafka client hiện đại có thể tự bật một số mặc định phù hợp khi idempotence được cho phép, nhưng cấu hình production nên được kiểm tra rõ ràng.

Idempotence không khử trùng hai lệnh gửi độc lập. Ví dụ, API nhận yêu cầu tạo đơn hàng, gửi sự kiện thành công tới Kafka nhưng bị timeout trước khi trả response. Caller không biết lần gửi đầu đã thành công và gửi lại yêu cầu. Nếu ứng dụng tạo một lần gửi producer mới cho yêu cầu thứ hai, Kafka có thể ghi hai record khác offset. Cần dùng `requestId`, `orderId` hoặc `eventId` ổn định và kiểm tra trùng ở tầng nghiệp vụ.

### 2.2. Kafka transaction

Kafka transaction nhóm nhiều thao tác Kafka vào một đơn vị commit/abort. Với luồng consume-process-produce, Spring Kafka có thể dùng transaction của listener container để gửi output và đưa offset đầu vào vào cùng transaction. Consumer downstream cần đặt `isolation.level=read_committed` nếu chỉ được phép nhìn thấy kết quả đã commit.

Ví dụ các thuộc tính nền tảng trong Spring Boot:

```properties
spring.kafka.producer.transaction-id-prefix=${INSTANCE_ID:local}-orders-
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.properties[isolation.level]=read_committed
```

`transaction-id-prefix` phải duy nhất giữa các instance ứng dụng hoạt động đồng thời trong cùng môi trường Kafka. Giá trị ví dụ dùng `INSTANCE_ID` để minh họa; khi triển khai thực tế, cần cấp một định danh ổn định và duy nhất cho từng instance hoặc nhóm instance theo cách triển khai. Spring Kafka dùng prefix để tạo transactional producer có suffix riêng. Nếu nhiều instance dùng cùng prefix, chúng có thể fence producer của nhau và làm giao dịch thất bại.

Khi bật transaction cho listener container, phải bảo đảm container thực sự dùng transaction manager Kafka phù hợp và các lần gửi output được thực hiện trong transaction đang hoạt động. Chỉ cấu hình một `KafkaTemplate` có khả năng giao dịch nhưng để listener chạy không có transaction không tự tạo ra consume-process-produce atomicity.

Một số điểm cần nhớ:

- Offset của record được xử lý phải được gửi vào Kafka transaction cùng với output.
- Consumer downstream cần `read_committed` để không đọc output chưa commit hoặc đã abort.
- Transaction có thời gian timeout; xử lý quá lâu có thể khiến broker abort giao dịch.
- Transactional ID cần được quản lý duy nhất để tránh fencing ngoài ý muốn.
- Transaction Kafka chỉ bao phủ các thao tác được thực hiện trong Kafka transaction đó.

### 2.3. Consumer idempotency

Idempotency ở consumer là khả năng áp dụng cùng một sự kiện nhiều lần nhưng kết quả nghiệp vụ chỉ thay đổi một lần. Đây là lớp bảo vệ quan trọng vì at-least-once delivery và retry vẫn có thể làm handler chạy lại.

Ví dụ, khi xử lý `PaymentCaptured`, consumer lưu `eventId` vào bảng inbox có unique constraint và cập nhật trạng thái thanh toán trong cùng một database transaction. Nếu cùng sự kiện đến lần nữa, thao tác insert bị trùng khóa và consumer bỏ qua side effect đã áp dụng.

```sql
BEGIN;

INSERT INTO processed_event (event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ cập nhật nghiệp vụ khi INSERT vừa tạo được một hàng mới.
-- Thực hiện kiểm tra số hàng được insert trong ứng dụng.
UPDATE payment
SET status = 'CAPTURED'
WHERE payment_id = :payment_id;

COMMIT;
```

Đoạn SQL mô tả ý tưởng; ứng dụng phải kiểm tra kết quả insert và chỉ chạy `UPDATE` khi event ID mới được ghi nhận. Hai thao tác phải nằm trong cùng transaction database. Nếu event ID đã tồn tại, kết thúc transaction mà không lặp lại side effect. Nếu cập nhật nghiệp vụ thất bại, việc ghi event ID cũng phải rollback để lần xử lý sau có thể thử lại.

Consumer idempotency bảo vệ kết quả nghiệp vụ ngay cả khi Kafka giao lại bản ghi. Nó không nhất thiết ngăn bản ghi lặp xuất hiện trong topic hoặc ngăn listener được gọi nhiều lần.

## 3. Vì sao duplicate vẫn xuất hiện trong hệ thống có exactly-once?

### 3.1. Timeout tạo ra kết quả không chắc chắn

Một timeout không chứng minh thao tác phía server đã thất bại. Producer có thể đã gửi record và broker đã commit, nhưng phản hồi bị mất trên đường về. Ở phía client, trạng thái có thể là không rõ: thao tác đã thành công hay chưa.

Nếu ứng dụng tạo một yêu cầu gửi mới với một producer sequence mới, broker không thể suy ra rằng hai yêu cầu đó là cùng một hành động nghiệp vụ. Idempotent producer chủ yếu xử lý retry của cùng producer protocol session, còn khử trùng request nghiệp vụ cần một idempotency key ổn định.

### 3.2. Consumer xử lý xong nhưng chưa commit offset

Trong mô hình at-least-once, consumer thường hoàn tất side effect rồi mới commit offset. Nếu database đã commit nhưng consumer chết trước khi Kafka ghi nhận offset mới, Kafka sẽ giao lại record. Đây là hành vi đúng để tránh mất dữ liệu, nhưng side effect có thể lặp nếu handler không idempotent.

Ví dụ trình tự:

```text
1. Consumer đọc record ở offset 120.
2. Consumer cập nhật database thành công.
3. Process dừng trước khi commit offset 121.
4. Consumer khởi động lại và đọc lại offset 120.
5. Handler chạy lần nữa.
```

Nếu database không có inbox hoặc unique business key, ứng dụng có thể tạo hai giao dịch nghiệp vụ cho cùng một record. Với consumer idempotent, lần xử lý thứ hai nhận ra event ID đã hoàn tất và không lặp tác động.

### 3.3. Caller retry yêu cầu nghiệp vụ

Một REST client, scheduler hoặc upstream service có thể gửi lại cùng lệnh khi không nhận được phản hồi. Nếu producer tạo event ID mới cho mỗi lần nhận request, duplicate nghiệp vụ xuất hiện dù producer idempotence đang bật.

Giải pháp là để caller gửi idempotency key hoặc để hệ thống tạo/tra cứu một business operation ID ổn định trước khi phát sự kiện. Mọi lần retry cùng một thao tác phải dùng cùng ID. Nếu hệ thống không có cách nhận biết hai request có cùng ý định, không thể khử trùng một cách đáng tin cậy chỉ dựa trên nội dung payload.

### 3.4. Retry topic, DLT và replay

Retry topic có thể đưa record sang topic khác để thử lại sau một khoảng thời gian. Khi record được chuyển, bản ghi gốc và bản ghi retry là các bản ghi Kafka khác nhau. Một nghiệp vụ có thể vì thế xuất hiện trong nhiều topic hoặc được listener thực hiện lại.

DLT lưu bản ghi không thể xử lý sau chính sách retry. Khi vận hành replay DLT, người trực có thể gửi lại bản ghi vào topic chính. Nếu bản ghi đã từng tạo một phần side effect trước khi lỗi xảy ra, replay có thể lặp phần side effect đó.

Replay từ offset cũ, khôi phục consumer group, chạy backfill hoặc chuyển cluster cũng có thể phát lại sự kiện đã xử lý. Cần quyết định rõ replay là:

- **Reprocessing để tái tạo trạng thái:** side effect phải được ghi vào môi trường đích riêng hoặc có chiến lược thay thế trạng thái.
- **Retry một sự kiện chưa hoàn tất:** dùng event ID cũ và consumer idempotent để hoàn thành phần còn thiếu.
- **Phát lại như sự kiện mới:** chỉ tạo event ID mới khi nghiệp vụ thực sự định nghĩa một hành động mới.

Không tự động thay event ID khi replay chỉ để tránh unique constraint; làm vậy sẽ vô hiệu hóa cơ chế deduplication.

### 3.5. Side effect ngoài Kafka

Kafka transaction không bao gồm một cách tự động các thao tác như:

- Ghi hoặc cập nhật database quan hệ.
- Gọi REST API hoặc RPC tới dịch vụ khác.
- Gửi email, SMS hoặc push notification.
- Ghi file vào object storage.
- Gọi cổng thanh toán hoặc hệ thống kế toán.

Nếu listener gọi API thanh toán rồi transaction Kafka abort, lần xử lý tiếp theo có thể gọi API lần nữa. Nếu listener commit database rồi offset chưa commit, record có thể được giao lại. Đây là các cửa sổ lỗi giữa hai hệ thống độc lập.

Đối với side effect bên ngoài, cần dùng idempotency key được hệ thống đích hỗ trợ, inbox/outbox, unique constraint hoặc một giao thức phân tán được thiết kế rõ ràng. Không được suy luận rằng bật `transaction-id-prefix` đã làm cho database và Kafka cùng commit nguyên tử.

## 4. Chọn delivery semantics theo loại luồng

Ba mô hình thường được nhắc đến là at-most-once, at-least-once và exactly-once semantics. Mỗi mô hình có đánh đổi riêng.

| Mô hình | Đặc điểm | Rủi ro chính | Trường hợp phù hợp |
|---|---|---|---|
| At-most-once | Offset có thể được commit trước khi xử lý hoàn tất; record không được giao lại sau lỗi ở một số tình huống | Có thể mất tác động xử lý | Metric hoặc tín hiệu có thể mất một mẫu, không dùng cho sự kiện nghiệp vụ quan trọng nếu mất dữ liệu không chấp nhận được |
| At-least-once | Xử lý xong mới commit; record có thể được giao lại | Có thể xử lý trùng | Luồng nghiệp vụ có consumer idempotent, database inbox hoặc downstream hỗ trợ idempotency |
| Kafka EOS | Offset đầu vào và output Kafka nằm trong cùng transaction; consumer `read_committed` quan sát kết quả đã commit | Listener vẫn có thể chạy lại; side effect ngoài Kafka không được bao phủ | Pipeline consume-transform-produce giữa các topic Kafka |

Không nên chọn at-most-once chỉ để tránh duplicate nếu hậu quả mất một sự kiện là nghiêm trọng. Trong nhiều hệ thống nghiệp vụ, at-least-once kết hợp idempotent consumer đem lại hành vi dễ phục hồi hơn: bản ghi có thể được giao lại nhưng kết quả nghiệp vụ vẫn ổn định.

## 5. Thiết kế luồng Spring Kafka theo ranh giới giao dịch

### 5.1. Kafka-to-Kafka

Với pipeline chỉ đọc Kafka, biến đổi và ghi Kafka, dùng transaction của listener container để kết hợp output với offset đầu vào. Cần xác nhận consumer group không auto-commit offset độc lập, output producer tham gia transaction và consumer đích dùng `read_committed`.

Sơ đồ logic:

```text
Input topic
    |
    v
Spring Kafka listener
    |
    +---- transform / validate
    |
    v
Kafka transaction
    |                 |
    |                 +---- commit input offset
    +---- write output topic
    |
    v
Commit transaction
    |
    v
Downstream read_committed consumer
```

Nếu xử lý lỗi, transaction abort và input offset không được commit cùng output. Khi container retry hoặc consumer nhận lại record, ứng dụng có thể thực hiện lại logic. Các hàm biến đổi nên tránh side effect ngoài transaction; nếu có side effect, cần idempotency riêng.

### 5.2. Kafka-to-database

Khi consumer cập nhật database, Kafka offset và database commit là hai thao tác riêng trừ khi dùng một giải pháp phân tán chuyên biệt. Mẫu thông dụng là at-least-once cộng với inbox:

```text
Kafka record
    |
    v
Spring Kafka listener
    |
    v
Database transaction
    |-- insert eventId into inbox (unique)
    |-- apply business update if eventId is new
    |
    v
Database commit
    |
    v
Kafka offset commit
```

Nếu database commit thành công nhưng offset commit thất bại, record sẽ được giao lại; inbox phát hiện event ID đã tồn tại và không áp dụng update lần nữa. Nếu database transaction rollback, cả inbox row và update nghiệp vụ cùng rollback; lần giao lại có thể xử lý bình thường.

Không nên ghi event ID vào inbox trong một transaction độc lập trước khi cập nhật nghiệp vụ. Nếu process dừng giữa hai thao tác, inbox sẽ nói rằng event đã xử lý trong khi dữ liệu nghiệp vụ chưa thay đổi; lần retry tiếp theo có thể bị bỏ qua sai.

### 5.3. Database-to-Kafka

Khi ứng dụng cập nhật database và phát sự kiện, mẫu transactional outbox tránh khoảng trống giữa hai thao tác:

1. Trong một database transaction, cập nhật dữ liệu nghiệp vụ và insert một hàng outbox có event ID ổn định.
2. Một relay đọc outbox và publish sang Kafka.
3. Relay đánh dấu hàng outbox đã gửi sau khi nhận xác nhận phù hợp.
4. Consumer phía sau dùng inbox hoặc idempotency key để chống xử lý lặp.

Nếu relay publish thành công nhưng dừng trước khi đánh dấu outbox, relay có thể publish lại cùng event. Vì vậy outbox bảo đảm không mất sự kiện trong cửa sổ ghi database và publish, nhưng bản ghi Kafka vẫn có thể lặp. Consumer idempotent hoàn tất thiết kế đầu cuối.

## 6. Định danh sự kiện và chiến lược deduplication

Một hệ thống muốn xử lý duplicate an toàn cần định danh sự kiện ổn định, duy nhất trong phạm vi nghiệp vụ. Ví dụ:

```json
{
  "eventId": "evt-8f2a...",
  "eventType": "PaymentCaptured",
  "aggregateId": "payment-2048",
  "occurredAt": "2026-11-15T10:20:30Z",
  "schemaVersion": 2
}
```

`eventId` dùng để nhận diện đúng một sự kiện; `aggregateId` thường dùng làm Kafka key để giữ thứ tự cho cùng aggregate; `schemaVersion` giúp consumer xử lý thay đổi schema. Không nên chỉ dùng hash payload làm định danh nếu hai sự kiện độc lập có thể có payload giống nhau hoặc cùng sự kiện có thể được serialize khác nhau.

Các lựa chọn lưu trạng thái deduplication:

- **Inbox table trong database:** phù hợp khi side effect chính nằm trong cùng database. Dùng unique constraint trên event ID và ghi inbox cùng transaction nghiệp vụ.
- **Idempotency key ở dịch vụ đích:** phù hợp khi gọi payment gateway hoặc API có hỗ trợ key. Gửi cùng key cho mọi lần retry của cùng hành động.
- **Unique business constraint:** phù hợp khi bản thân mô hình dữ liệu có khóa duy nhất như `orderId` hoặc `invoiceNumber`.
- **State store hoặc cache có TTL:** có thể dùng cho deduplication ngắn hạn hoặc luồng có ràng buộc thời gian rõ ràng; cần đánh giá eviction, restart, consistency và thời hạn lưu.

Thời gian lưu dấu deduplication phải dài ít nhất bằng khoảng thời gian có thể retry, replay, khôi phục hoặc phát lại sự kiện. Nếu xóa inbox sau một ngày nhưng DLT có thể replay sau một tuần, duplicate cũ có thể gây side effect mới. Với nghiệp vụ tài chính hoặc dữ liệu cần kiểm toán, lịch sử event ID có thể cần được giữ lâu dài theo chính sách dữ liệu.

## 7. Thứ tự xử lý và duplicate

Kafka giữ thứ tự trong một partition, không tạo thứ tự toàn cục giữa nhiều partition. Cùng một key thường được đưa về cùng partition, giúp duy trì thứ tự của các sự kiện cho một aggregate khi partitioning ổn định.

Duplicate và ordering là hai vấn đề khác nhau:

- Deduplication có thể loại bỏ một sự kiện đã áp dụng, nhưng không tự sửa thứ tự của hai sự kiện khác nhau.
- Retry topic có thể làm một record lỗi được xử lý sau record đến sau nó, khiến thứ tự nghiệp vụ thay đổi.
- Thêm partition hoặc thay đổi partitioner có thể làm key được phân phối khác trước, ảnh hưởng thứ tự qua thời gian.
- Một consumer group có thể xử lý các partition song song; thứ tự chỉ được bảo đảm trong từng partition.

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo đơn hàng hoặc tài khoản, cần dùng key phù hợp, giữ các chuyển trạng thái trong cùng partition, và thiết kế retry sao cho không cho phép sự kiện sau vượt qua sự kiện trước khi điều đó vi phạm nghiệp vụ. Deduplication phải kết hợp với kiểm tra version/sequence của aggregate nếu sự kiện đến sai thứ tự.

## 8. Vận hành và quan sát duplicate

Không có một metric đơn lẻ chứng minh hệ thống không duplicate. Cần đo ở từng lớp:

| Lớp | Tín hiệu nên thu thập | Điều cần điều tra |
|---|---|---|
| Producer | Retry rate, timeout, delivery failure, event ID trùng trong request log | Caller retry, timeout không rõ kết quả, producer restart |
| Kafka | Transaction abort rate, producer fencing, request errors, consumer lag | Transaction timeout, transactional ID xung đột, broker lỗi |
| Consumer | Số record nhận, số event ID mới, số event ID đã thấy, handler retry, commit failure | Redelivery, rebalance, offset không tiến triển |
| Database | Unique constraint conflict, inbox duplicate count, số update bị bỏ qua do idempotency | Duplicate delivery hoặc replay; kiểm tra có phải hành vi dự kiến không |
| Nghiệp vụ | Số giao dịch trùng, số lần side effect theo business ID, kết quả đối soát | Lỗi deduplication, event ID không ổn định, side effect ngoài transaction |

Log nên mang theo `eventId`, `correlationId`, topic, partition, offset, consumer group và attempt number khi có. Không ghi toàn bộ payload nhạy cảm chỉ để điều tra duplicate. Metric duplicate cần phân biệt bản ghi được nhận lại nhưng đã bỏ qua an toàn với tác động nghiệp vụ thực sự bị lặp.

Một số cảnh báo hữu ích:

- Transaction abort hoặc producer fencing tăng đột biến.
- Consumer commit failure hoặc rebalance tăng kéo dài.
- Inbox unique conflict tăng khác thường sau deploy hoặc replay.
- DLT/retry topic tăng đột biến.
- Một business ID có nhiều side effect trong hệ thống đích.

Duplicate delivery có thể là một phần bình thường của at-least-once. Cảnh báo nên tập trung vào tỷ lệ bất thường, tác động nghiệp vụ và các dấu hiệu cho thấy idempotency không hoạt động.

## 9. Kiểm thử các cửa sổ lỗi

Kiểm thử exactly-once và idempotency cần chủ động dừng ứng dụng ở những thời điểm có thể tạo trạng thái không chắc chắn. Một số kịch bản thực tế:

1. Dừng producer sau khi broker nhận record nhưng trước khi ứng dụng nhận phản hồi.
2. Gửi lại cùng request ID từ caller sau timeout.
3. Dừng consumer sau database commit nhưng trước Kafka offset commit.
4. Làm listener throw exception sau khi đã gửi output trong Kafka transaction, rồi xác minh transaction abort.
5. Dừng relay outbox sau khi publish Kafka nhưng trước khi đánh dấu outbox đã gửi.
6. Replay cùng event ID từ DLT hoặc offset cũ.
7. Gây rebalance trong lúc consumer đang xử lý batch.
8. Khởi động hai instance với transactional ID prefix trùng nhau để xác minh cảnh báo fencing và quy trình cấu hình đúng.

Với mỗi kịch bản, kiểm tra cả ba lớp: số bản ghi Kafka, số lần handler được gọi và số tác động nghiệp vụ cuối cùng. Một bài kiểm thử chỉ đếm số lần listener chạy sẽ kết luận sai rằng hệ thống không exactly-once nếu handler được retry nhưng transaction abort và kết quả cuối cùng chỉ được commit một lần.

Nên đối soát bằng event ID và business key. Xác minh rằng mỗi event ID chỉ tạo một kết quả nghiệp vụ, đồng thời các sự kiện độc lập không bị gộp nhầm chỉ vì payload giống nhau. Ghi nhận kết quả cho cả trường hợp process restart, retry, replay và failover.

## 10. Cách diễn đạt chính xác trong thiết kế và vận hành

Khi mô tả một luồng, hãy dùng câu cụ thể có phạm vi:

- “Luồng đọc topic A, ghi topic B và commit offset đầu vào trong cùng Kafka transaction; consumer B dùng `read_committed`.”
- “Producer bật idempotence để loại bỏ duplicate do retry giao thức trong phạm vi producer session.”
- “Consumer xử lý at-least-once và dùng inbox table với unique event ID để bảo đảm tác động database idempotent.”
- “Outbox relay có thể publish lặp nếu dừng sau publish; consumer đích khử trùng theo event ID.”
- “Replay DLT giữ nguyên event ID và được thực hiện qua quy trình có đối soát.”

Tránh các phát biểu tuyệt đối như “Kafka bảo đảm không bao giờ có duplicate”, “listener chỉ chạy đúng một lần” hoặc “bật exactly-once sẽ bảo vệ cả database và API bên ngoài”. Những phát biểu này bỏ qua retry, timeout, redelivery, replay và ranh giới giao dịch.

Một thiết kế đáng tin cậy thường kết hợp nhiều lớp: idempotent producer giảm duplicate do retry giao thức; Kafka transaction bảo vệ tính nguyên tử của offset và output Kafka; consumer inbox hoặc idempotency key bảo vệ side effect; outbox bảo vệ việc phát sự kiện từ database; quy trình replay và đối soát kiểm soát các lần phát lại. Mỗi lớp giải quyết một cửa sổ lỗi cụ thể.

## 11. Tiêu chí lựa chọn và vận hành

Trước khi tuyên bố một luồng Spring Kafka có exactly-once semantics, đội ngũ cần trả lời:

1. Exactly-once áp dụng cho thao tác nào: producer retry, Kafka transaction hay tác động nghiệp vụ cuối cùng?
2. Input offset và output Kafka có nằm trong cùng transaction không?
3. Consumer downstream có dùng `read_committed` không?
4. Transactional ID prefix có duy nhất giữa các instance không và transaction timeout có phù hợp với thời gian xử lý không?
5. Có side effect ngoài Kafka nào trong listener không? Side effect đó dùng idempotency key, inbox hay outbox ra sao?
6. Caller có thể retry cùng một yêu cầu không? ID của cùng thao tác có ổn định qua các lần retry không?
7. DLT, retry topic, replay và backfill có giữ nguyên event ID và có quy trình đối soát không?
8. Thời gian lưu dấu deduplication có bao phủ retention và cửa sổ phục hồi/replay không?
9. Có kiểm thử các điểm dừng giữa side effect và offset commit không?
10. Dashboard có phân biệt duplicate delivery, duplicate record và duplicate side effect không?

Exactly-once là một bảo đảm hữu ích khi được đặt đúng ranh giới. Mục tiêu vận hành thực tế là giữ cho kết quả nghiệp vụ chính xác khi có retry, restart, rebalance, timeout, replay và failover. Điều đó đòi hỏi xác định rõ transaction nào được Kafka bảo vệ, side effect nào cần idempotency, và cách hệ thống phát hiện cũng như xử lý duplicate còn lại.
