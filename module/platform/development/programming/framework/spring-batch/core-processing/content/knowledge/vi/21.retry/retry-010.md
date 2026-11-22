# Retry không an toàn với side effect

Trong Spring Batch, retry giúp thử lại một thao tác khi gặp lỗi có khả năng phục hồi. Tuy nhiên, retry có thể làm một đoạn code được thực hiện nhiều lần. Nếu đoạn code đó tạo side effect bên ngoài transaction hiện tại, lần thử lại có thể lặp hành động dù lần trước thực tế đã thành công.

Ví dụ, một writer gửi yêu cầu thanh toán đến API đối tác. Đối tác đã nhận và xử lý thanh toán, nhưng response bị timeout trên đường về. Ứng dụng chỉ nhìn thấy timeout và cho rằng request thất bại. Nếu Spring Batch retry writer, cùng yêu cầu có thể được gửi lần nữa và khách hàng bị trừ tiền hai lần.

Rủi ro cốt lõi là **không biết chắc lần thử trước đã tạo side effect hay chưa**. Rollback database không thể thu hồi một HTTP request, email, message đã publish hoặc file đã ghi ở hệ thống khác. Vì vậy, trước khi cấu hình retry cho reader, processor, writer hoặc Tasklet, cần xác định side effect nào có thể lặp, có cơ chế chống trùng hay không và cách đối soát khi kết quả không rõ ràng.

## 1. Side effect là gì?

Side effect là thay đổi quan sát được bên ngoài kết quả tính toán thuần của một phương thức. Trong Batch Job, các ví dụ thường gặp gồm:

- Gửi HTTP request để tạo đơn hàng, thu tiền, đặt chỗ hoặc cập nhật hệ thống đối tác.
- Gửi email, SMS hoặc thông báo push.
- Publish message vào Kafka, RabbitMQ hoặc một broker khác.
- Ghi, đổi tên, di chuyển hoặc xóa file.
- Ghi dữ liệu sang một database không tham gia transaction của Step.
- Gọi một service làm thay đổi trạng thái ở hệ thống bên ngoài.
- Cập nhật counter hoặc trạng thái nghiệp vụ trong một resource không được transaction hiện tại quản lý.

Các thao tác đọc cũng có thể có side effect nếu API ghi audit, tiêu thụ message, đánh dấu bản ghi đã đọc hoặc thay đổi cursor phía server. Không nên mặc định mọi lời gọi có tên `get` hoặc `read` đều hoàn toàn không gây tác dụng phụ.

Ngược lại, các phép tính như chuẩn hóa chuỗi, kiểm tra điều kiện, tính thuế từ dữ liệu đã có hoặc tạo một object mới thường không tạo side effect bên ngoài. Những phép tính này phù hợp hơn với `ItemProcessor` vì có thể gọi lại mà không làm thay đổi hệ thống khác.

## 2. Vì sao retry có thể lặp side effect?

Trong chunk Step, reader, processor và writer có thể được gọi lại khi retry hoặc khi chunk rollback được xử lý theo fault-tolerance policy. Writer có thể nhận lại một chunk hoặc một nhóm item liên quan trong quá trình xử lý lỗi. Do đó, code bên trong các thành phần này không nên giả định chỉ được gọi đúng một lần.

Một tình huống thường gặp với API:

```text
Spring Batch                         API đối tác
     |                                   |
     |---- POST /payments -------------->| 
     |                                   | Xử lý thanh toán thành công
     |<--- Response bị mất / timeout ----X
     |
     | Không biết API đã xử lý hay chưa
     |
     |---- Retry POST /payments -------->| 
     |                                   | Có thể tạo thanh toán lần hai
```

Ứng dụng nhận timeout, nhưng timeout chỉ nói rằng client không nhận được response đúng hạn. Nó không chứng minh server chưa thực hiện request. Server có thể đã commit thay đổi rồi mới mất kết nối hoặc response bị thất lạc.

Các tình huống tương tự:

| Side effect | Tình huống sau lần thử đầu | Rủi ro khi retry |
|---|---|---|
| Thanh toán API | Đối tác đã thu tiền nhưng response timeout | Thu tiền hai lần. |
| Gửi email | Mail server đã nhận thư nhưng client mất kết nối trước ACK | Người nhận nhận email trùng. |
| Publish message | Broker đã lưu message nhưng producer không nhận ACK | Message được publish nhiều lần. |
| Ghi file | File đã được ghi nhưng Job lỗi trước khi cập nhật metadata | Ghi đè, nối thêm hoặc tạo file trùng. |
| Database khác | Database đích đã commit, database metadata chưa commit | Ghi cùng bản ghi nhiều lần hoặc lệch trạng thái. |
| Đặt lịch/đặt chỗ | Hệ thống ngoài đã giữ chỗ nhưng response bị timeout | Tạo nhiều reservation. |

Retry chỉ an toàn khi thao tác có thể lặp mà không gây sai lệch, hoặc hệ thống có cách nhận diện và xử lý request lặp.

## 3. Transaction của chunk không rollback được hệ thống bên ngoài

Chunk Step thường chạy trong transaction do `PlatformTransactionManager` được cấu hình quản lý. Nếu writer ghi vào cùng database và cùng transaction, thay đổi chưa commit có thể được rollback khi chunk thất bại.

```text
Transaction của chunk
  |
  +--> INSERT orders
  +--> UPDATE batch_status
  +--> Exception
  +--> ROLLBACK các thay đổi tham gia transaction
```

Nhưng transaction JDBC thông thường không bao gồm mọi tài nguyên mà code có thể gọi:

```text
Transaction JDBC                    Hệ thống ngoài
  |                                      |
  +--> INSERT orders                    |
  |                                      |
  +--> HTTP POST ----------------------->| Đã xử lý request
  |                                      |
  +--> Exception                        |
  +--> ROLLBACK database                | Không tự rollback
                                         |
                                         +--> Side effect vẫn tồn tại
```

Một transaction manager chỉ điều phối các resource tham gia transaction mà nó quản lý. Gọi HTTP client, ghi file cục bộ hoặc gửi email không tự động được enlist vào transaction JDBC. Nếu Job dùng hai datasource với hai transaction manager độc lập, commit của database này cũng không tự động nguyên tử với database kia.

Do đó, câu “chunk rollback” không đồng nghĩa “mọi hành động trong chunk bị hủy”. Phải xác định từng side effect thuộc transaction nào.

## 4. Retry trong ItemProcessor có side effect

`ItemProcessor` được thiết kế để biến đổi hoặc kiểm tra từng item. Khi processor gọi một service bên ngoài có thay đổi trạng thái, retry có thể lặp thay đổi đó.

Ví dụ không an toàn:

```java
public class PaymentProcessor
        implements ItemProcessor<OrderInput, PaymentResult> {

    private final PaymentClient paymentClient;

    @Override
    public PaymentResult process(OrderInput order) {
        // Side effect: đối tác có thể thu tiền ngay tại đây.
        return paymentClient.charge(order.orderId(), order.amount());
    }
}
```

Nếu `charge` thành công ở server nhưng client timeout, processor ném exception. Khi exception được retry, `charge` có thể chạy lần nữa.

Thiết kế an toàn hơn là để processor tạo một command thuần, sau đó ghi ý định thực hiện vào database trong transaction của chunk:

```java
public record PaymentCommand(
        String paymentId,
        String orderId,
        BigDecimal amount) {
}

public class PaymentCommandProcessor
        implements ItemProcessor<OrderInput, PaymentCommand> {

    @Override
    public PaymentCommand process(OrderInput order) {
        String paymentId = "payment-for-order-" + order.orderId();
        return new PaymentCommand(
                paymentId,
                order.orderId(),
                order.amount());
    }
}
```

Processor chỉ tính toán command và tạo một định danh ổn định theo nghiệp vụ. Nó không gửi thanh toán. Writer có thể lưu command thành outbox record trong cùng transaction với dữ liệu đơn hàng.

## 5. Idempotency: làm cho thao tác lặp an toàn

Một thao tác là idempotent nếu thực hiện nhiều lần với cùng một định danh và cùng dữ liệu không tạo thêm thay đổi ngoài kết quả của lần đầu. Ví dụ, “đặt trạng thái đơn hàng thành `PAID`” có thể idempotent nếu update dựa trên business key và trạng thái mục tiêu; “cộng thêm 100.000 đồng vào số dư” thường không idempotent nếu không có mã giao dịch duy nhất.

### Idempotency key

Khi gọi API có tác dụng phụ, hãy tạo một idempotency key ổn định cho một business operation. Cùng một operation phải dùng cùng key ở mọi lần retry.

Ví dụ:

```java
String idempotencyKey = "charge-order-" + order.orderId();

paymentClient.charge(
        order.orderId(),
        order.amount(),
        idempotencyKey);
```

API đích cần thực sự hỗ trợ key này. Thông thường, server lưu key cùng kết quả xử lý; nếu nhận lại key đã tồn tại, server trả kết quả đã lưu thay vì thực hiện side effect lần nữa.

Một idempotency key tốt cần:

- Ổn định qua retry, rollback và restart của cùng business operation.
- Đại diện cho đúng một hành động nghiệp vụ, không chỉ một lần gọi HTTP.
- Không được tạo ngẫu nhiên mới ở mỗi lần retry.
- Được lưu hoặc tái tạo từ business key và loại operation.
- Có phạm vi uniqueness rõ ràng, ví dụ theo tenant hoặc merchant nếu hệ thống đích yêu cầu.

Nếu cùng một order có nhiều lần thu tiền hợp lệ, chỉ dùng `orderId` có thể chưa đủ. Key cần bao gồm mã lần thanh toán hoặc business operation ID để phân biệt hai lần thanh toán hợp lệ với một request bị gửi trùng.

### Idempotency phía hệ thống đích

Client gửi key không đủ để bảo đảm an toàn. Hệ thống nhận phải kiểm tra và lưu key theo cách đồng bộ với side effect. Nếu server chỉ ghi log key sau khi thu tiền, process crash giữa hai thao tác vẫn có thể gây thu tiền trùng.

Với database đích, có thể dùng unique constraint trên operation ID hoặc bảng deduplication. Với API đối tác, cần đọc hợp đồng API để xác nhận semantics, thời hạn lưu key, phạm vi key và cách truy vấn kết quả cũ.

## 6. Outbox pattern cho side effect bên ngoài

Transactional outbox là một cách phổ biến để tách thay đổi dữ liệu chính khỏi việc gửi request/message bên ngoài.

Trong transaction của chunk, writer ghi dữ liệu nghiệp vụ và một outbox record trong cùng database transaction. Một tiến trình relay riêng đọc các outbox record chưa gửi, gọi hệ thống ngoài, rồi đánh dấu đã gửi.

```text
Chunk transaction
  |
  +--> INSERT/UPDATE business data
  |
  +--> INSERT outbox(event_id, payload, status='PENDING')
  |
  +--> COMMIT
          |
          v
Outbox relay
  |
  +--> Đọc event PENDING
  |
  +--> Gửi đến API/broker với event_id làm idempotency key
  |
  +--> Đánh dấu SENT
```

Nếu chunk rollback, cả business data và outbox record cùng rollback. Không có outbox record để relay gửi đi. Nếu chunk commit, ý định gửi side effect đã được lưu bền vững và có thể được relay sau đó.

### Ví dụ schema outbox

```sql
CREATE TABLE batch_outbox (
    event_id       VARCHAR(100) PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    payload        TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    sent_at        TIMESTAMP NULL
);
```

`event_id` phải duy nhất và ổn định. Có thể bổ sung số lần thử, `next_attempt_at`, lỗi cuối cùng, lease/lock owner và các index phục vụ truy vấn relay.

### Writer lưu outbox trong transaction

Ví dụ minh họa writer lưu command vào bảng outbox:

```java
public class PaymentOutboxWriter implements ItemWriter<PaymentCommand> {

    private final JdbcTemplate jdbcTemplate;

    public PaymentOutboxWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends PaymentCommand> chunk) {
        for (PaymentCommand command : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO batch_outbox
                        (event_id, event_type, aggregate_id,
                         payload, status, created_at)
                    VALUES (?, 'PAYMENT_REQUESTED', ?, ?, 'PENDING', CURRENT_TIMESTAMP)
                    """,
                    command.paymentId(),
                    command.orderId(),
                    serialize(command));
        }
    }
}
```

Để outbox thực sự atomic với dữ liệu nghiệp vụ, `JdbcTemplate` phải dùng datasource/transaction manager tham gia cùng transaction của chunk. Cần có unique constraint trên `event_id`. Nếu writer được gọi lại, duplicate key phải được xử lý theo semantics đã thiết kế; không nên bắt mọi lỗi insert rồi bỏ qua vì có thể che lỗi dữ liệu khác.

### Relay vẫn cần idempotency

Outbox không tạo exactly-once delivery đến hệ thống ngoài. Relay có thể gửi request thành công rồi crash trước khi cập nhật `status = 'SENT'`. Khi chạy lại, relay sẽ gửi cùng event lần nữa.

Vì vậy, relay nên:

- Dùng `event_id` làm idempotency key khi gọi API hoặc publish message.
- Dùng claim/lease hoặc cơ chế locking để nhiều relay không xử lý cùng event đồng thời ngoài ý muốn.
- Đánh dấu trạng thái sau khi nhận kết quả thành công.
- Retry lỗi transient với backoff và giới hạn phù hợp.
- Lưu trạng thái lỗi cuối cùng để điều tra.
- Có quy trình đối soát cho kết quả không rõ ràng.

Outbox bảo đảm ý định side effect không bị mất khi transaction nghiệp vụ commit; idempotency ở consumer/đích xử lý việc relay gửi lặp.

## 7. Inbox hoặc deduplication ở consumer

Nếu Batch Job publish message đến broker, consumer có thể nhận cùng message nhiều lần do producer retry, broker redelivery hoặc consumer crash sau khi xử lý nhưng trước khi ACK.

Inbox pattern lưu `message_id` đã xử lý cùng với thay đổi nghiệp vụ của consumer trong một transaction:

```text
Message đến consumer
       |
       v
BEGIN transaction
       |
       +--> INSERT inbox(message_id) với unique key
       |
       +--> Nếu key đã tồn tại: không xử lý lại
       |
       +--> Nếu key mới: áp dụng thay đổi nghiệp vụ
       |
       +--> COMMIT
       |
       v
ACK message
```

Nếu consumer crash trước commit, cả inbox record và business change rollback; message có thể được giao lại và xử lý. Nếu transaction commit nhưng ACK bị mất, message được giao lại nhưng unique key trong inbox ngăn side effect nghiệp vụ bị thực hiện lần nữa.

Inbox cần dùng transaction phù hợp với dữ liệu nghiệp vụ. Chỉ lưu `message_id` ở một database khác rồi mới cập nhật dữ liệu chính sẽ tạo thêm khoảng trống không nguyên tử.

## 8. Gửi email và thông báo

Gửi email là side effect không thể rollback. Nếu SMTP server đã nhận email nhưng client timeout trước khi nhận response, retry có thể gửi email trùng.

Các lựa chọn:

- Ghi notification intent vào outbox trong transaction chunk.
- Dùng provider hỗ trợ idempotency hoặc request ID nếu có.
- Đưa business event ID vào metadata để phát hiện thông báo trùng ở phía nhận nếu hệ thống cho phép.
- Chấp nhận semantics at-least-once nếu provider không có deduplication và nghiệp vụ chấp nhận khả năng gửi lặp.
- Ghi trạng thái gửi và có quy trình tra cứu/đối soát khi kết quả không rõ ràng.

Không nên gửi email trực tiếp trong `ItemProcessor` hoặc `ItemWriter` rồi kỳ vọng transaction database rollback có thể thu hồi thư.

## 9. Ghi file và filesystem

Ghi file cũng là side effect bên ngoài transaction database. Nếu writer đã tạo file nhưng chunk rollback hoặc Job crash trước khi cập nhật metadata, lần retry/restart có thể ghi lại file.

Các cách giảm rủi ro:

- Ghi vào file tạm có tên gắn với business operation ID.
- Flush và đóng file trước khi công bố file hoàn chỉnh.
- Dùng atomic rename/move nếu filesystem hỗ trợ và nguồn/đích cùng filesystem.
- Nếu file đích đã tồn tại, kiểm tra checksum, manifest hoặc business key trước khi ghi đè.
- Ghi marker/manifest hoàn tất bằng một thao tác idempotent.
- Lưu trạng thái export trong database và có bước đối soát file với metadata.

Ví dụ quy trình:

```text
orders-2026-11-15.tmp
       |
       +--> ghi toàn bộ nội dung
       +--> flush/close
       +--> kiểm tra kích thước/checksum
       +--> atomic move
       v
orders-2026-11-15.csv
```

Nếu tiến trình dừng trước khi move, file tạm có thể được dọn hoặc tiếp tục theo manifest. Nếu dừng sau move nhưng trước khi Step ghi trạng thái hoàn tất, lần chạy lại cần nhận ra file đích đúng là output của operation đó thay vì tạo một bản thứ hai hoặc ghi đè dữ liệu không liên quan.

Atomic rename chỉ bảo đảm ở mức filesystem và điều kiện cụ thể; nó không tạo transaction chung với JobRepository. Vẫn cần lưu metadata và đối soát.

## 10. Ghi sang database khác

Nếu writer cập nhật database nghiệp vụ nhưng JobRepository nằm ở database metadata khác, cần xác định transaction manager thực tế. Một transaction JDBC thường chỉ quản lý một datasource/connection transaction.

Các trường hợp:

- Business data và Batch metadata cùng tham gia một transaction được quản lý: có thể commit/rollback nguyên tử trong phạm vi resource đó.
- Hai datasource có transaction manager độc lập: commit một bên không tự rollback bên kia.
- Có XA/JTA: có thể phối hợp distributed transaction nếu tất cả resource hỗ trợ và được cấu hình đúng, nhưng chi phí vận hành/phức tạp cao hơn.
- Dùng outbox hoặc business operation table: thường là cách thực tế để phối hợp dữ liệu và side effect qua nhiều hệ thống.

Không nên giả định vì writer được gọi trong một chunk nên mọi database mà nó kết nối đều nằm trong cùng transaction. Kiểm tra transaction manager, datasource và cách các repository/client lấy connection.

## 11. Retry an toàn cho reader, processor và writer

### Reader

Read retry an toàn khi lần đọc thất bại không làm nguồn dữ liệu tiến qua item chưa được trả về. Với API phân trang, dùng cursor ổn định; chỉ cập nhật cursor sau khi response được xác nhận và item đã được đưa vào luồng xử lý đúng cách. Với message queue, hiểu semantics ACK/NACK và transactional consumption.

Nếu API đọc có tác dụng phụ như consume token, claim job hoặc đánh dấu record đã đọc, hãy dùng request ID hoặc lease có thể khôi phục. Nếu không thể biết lần đọc trước đã tiêu thụ dữ liệu chưa, cần endpoint tra cứu trạng thái hoặc cơ chế deduplication.

### Processor

Process retry an toàn nhất khi processor gần như pure function: cùng input và cùng dữ liệu tham chiếu sẽ tạo output mà không thay đổi hệ thống ngoài. Nếu phải gọi dịch vụ bên ngoài, ưu tiên API read-only; nếu API thay đổi trạng thái, dùng idempotency key và timeout rõ ràng.

### Writer

Write retry an toàn khi thay đổi nằm trong transaction có thể rollback hoặc khi writer có idempotency. Database writer nên dùng business key/unique constraint/upsert theo quy tắc nghiệp vụ. Message/API/file writer cần outbox, idempotency key hoặc trạng thái operation có thể đối soát.

| Thành phần | Câu hỏi cần trả lời trước khi bật retry |
|---|---|
| Reader | Lần đọc thất bại có thể đã tiêu thụ/đánh dấu dữ liệu ở nguồn chưa? Gọi lại có trả đúng item không? |
| Processor | Gọi lại cùng item có tạo side effect hoặc thay đổi trạng thái bên ngoài không? |
| Writer | Một phần hoặc toàn bộ output có thể đã được hệ thống đích nhận trước exception không? Có deduplication không? |

## 12. Timeout không chứng minh thao tác thất bại

Một timeout là kết quả không rõ ràng. Client không nhận được response đúng hạn, nhưng server có thể đã thực hiện thao tác.

Khi gặp timeout với API có side effect, có ba trạng thái cần phân biệt:

1. **Chưa được xử lý:** request chưa đến server hoặc server từ chối trước khi tạo side effect.
2. **Đã xử lý:** server đã commit side effect, nhưng response bị mất hoặc đến muộn.
3. **Không rõ:** client không thể xác định trạng thái từ response hiện tại.

Không nên xem trạng thái thứ ba là thất bại chắc chắn rồi gửi lại một request mới. Cách xử lý an toàn hơn:

- Gửi lại cùng idempotency key nếu API hỗ trợ.
- Truy vấn operation status bằng business key/request ID.
- Đối chiếu trạng thái ở hệ thống đích trước khi tạo request mới.
- Nếu không thể xác định, đưa operation vào trạng thái cần reconciliation thay vì retry mù quáng.

## 13. Compensation khi không thể rollback

Với side effect đã xảy ra ở hệ thống ngoài, rollback kỹ thuật thường không thể thu hồi hành động. Một số nghiệp vụ có thể cần **compensation**: tạo một hành động nghiệp vụ khác để bù lại.

Ví dụ:

- Thanh toán đã thu tiền: tạo giao dịch refund.
- Đã đặt chỗ: gửi yêu cầu cancel reservation.
- Đã cấp hạn mức: tạo operation thu hồi hạn mức.
- Đã gửi dữ liệu sang đối tác: gửi event điều chỉnh hoặc yêu cầu hủy.

Compensation không phải rollback nguyên tử. Nó là một hành động mới, có thể thất bại và cũng cần idempotency, retry và audit. Cần lưu operation gốc, trạng thái compensation và business key để không refund hoặc cancel hai lần.

Với quy trình nhiều hệ thống, có thể dùng Saga pattern: mỗi bước thực hiện một transaction cục bộ và có một hành động bù tương ứng nếu bước sau thất bại. Saga phù hợp với quy trình dài qua nhiều resource khi distributed transaction không khả thi.

## 14. Retry, Skip và noRollback không giải quyết side effect trùng

Các cơ chế fault tolerance có mục đích khác nhau:

| Cơ chế | Mục đích | Có tự chống side effect trùng không? |
|---|---|---|
| Retry | Thử lại thao tác gặp lỗi có khả năng phục hồi | Không. Cần idempotency hoặc deduplication. |
| Skip | Bỏ qua item lỗi theo chính sách | Không. Side effect từ lần thử trước có thể đã xảy ra. |
| Rollback | Hoàn tác thay đổi thuộc transaction hiện tại | Không hoàn tác HTTP, email, file hoặc resource ngoài transaction. |
| `noRollback` | Không rollback với exception được chỉ định | Không; thậm chí có thể giữ lại thay đổi dở dang nếu dùng sai. |
| RetryListener | Quan sát retry attempt | Không; listener không quyết định hoặc khử trùng lặp side effect. |
| Outbox/inbox | Lưu ý định và deduplicate delivery/consumption | Giảm mất/lặp bằng transaction và khóa duy nhất; consumer vẫn cần xử lý idempotent. |

Skip sau khi retry hết lượt không chứng minh lần gọi đầu chưa thành công. Ví dụ, API thanh toán đã thu tiền nhưng client timeout ở mọi lần thử; nếu sau đó exception bị skip, Job có thể tiếp tục trong khi thanh toán đã tồn tại. Cần tra cứu/đối soát operation trước khi đánh dấu item là thất bại.

## 15. Vì sao after-commit callback không đủ để bảo đảm delivery?

Một cách thường được nghĩ đến là chỉ gọi API sau khi transaction commit, ví dụ qua transaction synchronization hoặc callback sau chunk. Cách này tránh gửi request khi transaction database còn có thể rollback, nhưng vẫn có một khoảng trống:

```text
Database COMMIT thành công
       |
       X  Process crash trước callback gửi API
       |
       v
Side effect chưa được gửi
```

Callback sau commit không phải một hàng đợi bền vững. Nếu process dừng sau commit nhưng trước khi callback chạy, sự kiện có thể bị mất. Nếu callback chạy nhưng response timeout, kết quả lại không rõ ràng.

Outbox giải quyết khoảng trống này bằng cách ghi ý định gửi vào database trong cùng transaction. Một relay độc lập đọc record đã commit và gửi lại khi cần. Relay vẫn cần idempotency vì có thể gửi nhiều lần.

## 16. Ví dụ kiến trúc: Batch import và phát sự kiện

Giả sử Job nhập đơn hàng và cần phát `OrderImported` đến hệ thống fulfillment.

Thiết kế dễ gặp lỗi:

```text
Reader -> Processor -> Writer
                         |
                         +--> INSERT orders
                         +--> POST fulfillment API
```

Nếu API thành công nhưng transaction database rollback, hệ thống fulfillment biết một đơn hàng chưa tồn tại trong database chính. Nếu database commit nhưng response API timeout và writer retry, hệ thống fulfillment có thể nhận sự kiện hai lần.

Thiết kế dùng outbox:

```text
Batch chunk transaction
  |
  +--> INSERT orders
  +--> INSERT outbox(OrderImported, event_id)
  +--> COMMIT
          |
          v
Outbox relay
  |
  +--> Publish event_id + payload
          |
          v
Fulfillment consumer
  |
  +--> INSERT inbox(event_id) với unique constraint
  +--> Xử lý đơn hàng nếu event_id mới
  +--> COMMIT
```

Khi chunk rollback, không có đơn hàng và outbox event được commit. Khi chunk commit, event đã được lưu bền vững. Relay có thể gửi lại nếu không nhận được ACK; consumer dùng inbox để không áp dụng thay đổi nghiệp vụ lần hai.

## 17. Chọn retry policy theo khả năng lặp an toàn

Không nên chỉ phân loại exception theo tên rồi bật retry. Cần xét cả tính chất thao tác được thực hiện khi exception xảy ra.

| Tình huống | Retry có an toàn? | Hướng thiết kế |
|---|---|---|
| SELECT database thuần, không consume/claim dữ liệu | Thường có | Retry lỗi kết nối/deadlock với giới hạn. |
| Processor tính toán thuần | Thường có | Giữ processor stateless/pure. |
| HTTP GET không side effect | Thường có, tùy API | Dùng timeout, retry/backoff và giới hạn. |
| HTTP POST tạo thanh toán, không có idempotency | Không an toàn khi outcome không rõ | Dùng idempotency key hoặc status lookup trước retry. |
| Gửi email qua SMTP không có deduplication | Không bảo đảm tránh gửi trùng | Outbox, provider request ID hoặc chấp nhận at-least-once. |
| Insert database cùng transaction của chunk | Có thể an toàn khi rollback thật sự bao phủ thao tác | Kiểm tra datasource/transaction manager và unique key. |
| Publish message không có deduplication | Có thể gửi lặp | Outbox + inbox/dedup ở consumer. |
| Ghi file append vào một file chung | Thường không an toàn | File tạm, record ID, manifest và atomic move. |

Một lỗi được gọi là transient không đồng nghĩa thao tác có thể lặp an toàn. Ví dụ, timeout là transient về mặt kết nối nhưng request thanh toán có thể đã được xử lý. Cần cả hai điều kiện: lỗi có khả năng phục hồi và operation có semantics replay an toàn.

## 18. Quan sát và đối soát side effect

Khi một operation có thể được retry, nên lưu đủ thông tin để biết lần thử nào đã xảy ra và trạng thái nghiệp vụ cuối cùng:

- Business operation ID ổn định.
- Idempotency key hoặc event ID.
- JobExecution/StepExecution ID và business key.
- Số lần thử, thời điểm thử và loại exception.
- Trạng thái cuối: pending, confirmed, failed, unknown hoặc needs-reconciliation.
- Response/reference ID từ hệ thống ngoài nếu có.

Không lưu password, token hoặc payload nhạy cảm vào log. Dùng metric tag có cardinality thấp như Job, Step, loại side effect và exception category; không dùng từng order ID làm metric tag.

Đối với kết quả không rõ ràng, có thể tạo một reconciliation Step/Job để truy vấn hệ thống đích bằng operation ID, đối chiếu trạng thái và quyết định gửi lại, đánh dấu thành công hoặc tạo compensation. Đừng tự động retry vô hạn những operation có thể đã tạo hậu quả tài chính hoặc nghiệp vụ.

## 19. Kiểm thử retry có side effect

Unit test chỉ kiểm tra số lần gọi mock có thể bỏ sót lỗi thực tế về transaction và thời điểm crash. Nên kết hợp unit test, integration test và kiểm thử failure scenario.

Các tình huống quan trọng:

1. API thất bại trước khi xử lý request: retry thành công ở lần sau.
2. API xử lý thành công nhưng response bị timeout: lần retry dùng cùng idempotency key và không tạo side effect thứ hai.
3. Database rollback sau khi outbox record được ghi: cả business data và outbox record đều không tồn tại.
4. Database commit nhưng relay crash trước khi gửi: relay gửi event khi chạy lại.
5. Relay gửi thành công nhưng crash trước khi đánh dấu SENT: lần gửi lại được consumer deduplicate.
6. Consumer commit nhưng ACK bị mất: message redelivery không áp dụng business change lần nữa.
7. Writer được gọi lại sau rollback: output không bị nhân đôi.
8. File đã được move nhưng Step metadata chưa cập nhật: restart nhận ra output đã hoàn tất.
9. Retry hết giới hạn: operation chuyển sang trạng thái cần xử lý/đối soát đúng quy tắc.

Hãy kiểm thử với transaction manager, database, broker hoặc API sandbox gần với môi trường triển khai. Mock đơn thuần không chứng minh được tính atomic của transaction hoặc semantics idempotency của hệ thống đích.

## 20. Những lỗi thường gặp

### Retry một POST tạo side effect mà không có idempotency

Timeout có thể xảy ra sau khi server đã xử lý. Dùng idempotency key ổn định hoặc tra cứu operation status trước khi gửi lại.

### Gửi email hoặc publish message trong processor

Processor có thể chạy lại cùng item. Tách side effect ra khỏi processor; ghi intent vào outbox và xử lý bằng relay.

### Cho rằng database rollback sẽ hủy HTTP request

Transaction JDBC không quản lý HTTP server. Side effect bên ngoài vẫn tồn tại sau rollback.

### Tạo idempotency key mới mỗi lần retry

Key mới khiến server xem request là operation mới. Tạo key theo business operation và giữ ổn định qua mọi lần thử.

### Dùng outbox nhưng không deduplicate ở consumer

Relay có thể gửi cùng event nhiều lần. Consumer cần inbox/unique message ID hoặc xử lý idempotent.

### Đánh dấu SENT trước khi gửi

Nếu process crash sau khi đánh dấu mà trước khi gửi, event bị mất. Thường gửi trước rồi mới đánh dấu, đồng thời chấp nhận khả năng gửi lặp và xử lý bằng idempotency.

### Dựa vào afterCommit để bảo đảm sự kiện không mất

Process có thể crash sau database commit nhưng trước callback. Lưu intent bền vững trong outbox cùng transaction.

### Coi skip là cách giải quyết side effect không rõ kết quả

Skip không cho biết hệ thống ngoài đã xử lý request hay chưa. Tra cứu và đối soát operation trước khi quyết định skip hoặc chạy bù.

### Dùng compensation như rollback tự động

Compensation là một hành động mới có thể thất bại hoặc bị lặp. Nó cần operation ID, idempotency, retry và audit riêng.

## 21. Quy trình quyết định có nên retry một thao tác

Trước khi thêm `.retry(...)` cho một exception, hãy trả lời các câu hỏi sau:

1. Exception có thực sự transient hay phản ánh lỗi dữ liệu/cấu hình cố định?
2. Thao tác có thể đã tạo side effect trước khi exception được ném không?
3. Nếu gọi lại cùng operation, hệ thống đích có nhận diện request trùng không?
4. Có idempotency key ổn định hoặc unique business key không?
5. Transaction hiện tại quản lý được resource nào; resource nào nằm ngoài transaction?
6. Nếu response timeout và outcome không rõ, có API tra cứu trạng thái không?
7. Nếu retry hết giới hạn, operation sẽ fail, skip hay vào hàng đợi reconciliation?
8. Có cần outbox/inbox hoặc compensation không?
9. Retry limit, backoff và timeout có phù hợp SLA không?
10. Đã kiểm thử crash giữa side effect và cập nhật metadata chưa?

| Điều kiện | Quyết định |
|---|---|
| Lỗi transient, thao tác thuần hoặc transaction rollback được toàn bộ | Có thể retry với giới hạn. |
| Lỗi transient nhưng side effect có thể đã xảy ra | Chỉ retry nếu có idempotency/status lookup/deduplication. |
| Lỗi dữ liệu cố định | Skip nếu nghiệp vụ cho phép, nếu không thì fail. |
| Side effect không có cách chống trùng và outcome không rõ | Không retry mù quáng; đưa vào reconciliation/manual review. |
| Quy trình qua nhiều hệ thống không có distributed transaction | Cân nhắc outbox/inbox hoặc Saga/compensation. |

## Kết luận

Retry không an toàn khi lần thử trước có thể đã tạo side effect nhưng ứng dụng không biết kết quả, đặc biệt với HTTP POST, thanh toán, email, message, file và database ngoài transaction. Rollback của chunk chỉ hoàn tác resource tham gia transaction; nó không thu hồi hành động đã xảy ra ở hệ thống khác. Trước khi retry, hãy làm operation idempotent bằng key ổn định, unique constraint hoặc deduplication; dùng transactional outbox/inbox để phối hợp dữ liệu và sự kiện; tra cứu hoặc đối soát khi timeout tạo kết quả không rõ; và dùng compensation cho nghiệp vụ cần bù lại side effect đã hoàn tất. Retry policy, skip và listener không tự bảo đảm chống trùng — điều đó phải được thiết kế ở ranh giới nghiệp vụ và hệ thống đích.
