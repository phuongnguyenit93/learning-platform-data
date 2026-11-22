# Write-ahead hoặc outbox output

Trong Spring Batch, một bước xử lý thường đọc dữ liệu, biến đổi rồi ghi kết quả ra một hoặc nhiều đích: cơ sở dữ liệu, message broker, API bên ngoài hoặc hệ thống lưu trữ. Thách thức xuất hiện khi một lần xử lý phải cập nhật nhiều tài nguyên nhưng các tài nguyên đó không cùng tham gia một giao dịch. Ví dụ, batch cập nhật trạng thái đơn hàng trong database rồi gửi sự kiện `OrderProcessed` lên Kafka. Nếu database commit thành công nhưng ứng dụng dừng trước khi gửi message, trạng thái nghiệp vụ và hệ thống nhận sự kiện sẽ không đồng nhất. Nếu gửi message trước rồi database rollback, hệ thống nhận có thể xử lý một sự kiện cho thay đổi chưa từng được commit.

Write-ahead và transactional outbox là hai cách tổ chức output để giảm khoảng trống này. Cả hai đều ghi nhận ý định hoặc kết quả cần phát ra một cách bền vững trước khi thực hiện bước phát ra bên ngoài. Chúng giải quyết những vấn đề liên quan nhưng không hoàn toàn giống nhau: write-ahead thường nhấn mạnh nhật ký ghi trước và khả năng phục hồi, còn outbox là một mẫu tích hợp cụ thể, trong đó bản ghi sự kiện được lưu cùng giao dịch với dữ liệu nghiệp vụ rồi một tiến trình khác chuyển tiếp sự kiện đó.

## Vấn đề nhất quán khi ghi nhiều output

Giả sử một chunk xử lý 100 giao dịch. Với mỗi giao dịch, batch cần:

1. Cập nhật bản ghi nghiệp vụ trong database.
2. Gửi một sự kiện sang broker để các dịch vụ khác tiếp tục xử lý.

Nếu hai thao tác dùng hai hệ thống giao dịch độc lập, không có thứ tự gọi nào tự nó bảo đảm cả hai cùng thành công. Gửi trước rồi cập nhật database tạo ra nguy cơ phát sự kiện cho dữ liệu chưa commit. Cập nhật database trước rồi gửi tạo ra nguy cơ mất sự kiện sau khi database đã commit.

| Thứ tự thao tác | Điểm lỗi có thể xảy ra | Hậu quả |
|---|---|---|
| Gửi message, sau đó commit database | Message đã được broker nhận nhưng database rollback | Consumer nhìn thấy sự kiện không tương ứng với trạng thái đã commit |
| Commit database, sau đó gửi message | Database commit xong, tiến trình dừng trước khi gửi | Dữ liệu đã đổi nhưng không có sự kiện |
| Ghi output trực tiếp trong writer | Writer hoặc chunk được retry sau lỗi một phần | Có thể ghi lặp hoặc chỉ hoàn tất một phần các output |

Ranh giới transaction của chunk trong Spring Batch thường quản lý các thao tác tài nguyên tham gia transaction manager được cấu hình cho step. Không nên suy luận rằng một lệnh gọi HTTP hay một lần publish lên broker tự động rollback cùng database. Cần xác định rõ tài nguyên nào tham gia transaction, transaction manager nào điều phối chúng và điều gì xảy ra khi tiến trình chết giữa hai thao tác.

## Write-ahead: ghi bền vững trước khi phát output

Write-ahead là nguyên tắc ghi thông tin cần thiết vào một nơi lưu trữ bền vững trước khi thực hiện thay đổi hoặc hành động có thể quan sát từ bên ngoài. Nhật ký được commit trước đóng vai trò bằng chứng để tiến trình có thể tiếp tục hoặc phát lại công việc sau sự cố.

Một bản ghi write-ahead có thể chứa:

- Mã định danh duy nhất của output hoặc tác vụ.
- Loại sự kiện và khóa của đối tượng nghiệp vụ.
- Payload hoặc dữ liệu đủ để tái tạo output.
- Trạng thái xử lý, thời điểm tạo và số lần thử.
- Thông tin cần thiết để xác định output đã được xác nhận hay còn phải phát lại.

Luồng tổng quát:

```text
Đọc item
   |
   v
Tạo bản ghi ý định/output trong kho bền vững
   |
   v
Commit bản ghi write-ahead
   |
   v
Phát output ra đích bên ngoài
   |
   v
Ghi nhận kết quả đã gửi hoặc cần thử lại
```

Nếu ứng dụng dừng sau khi commit nhật ký nhưng trước khi phát output, một tiến trình phục hồi có thể tìm các bản ghi chưa hoàn tất và tiếp tục. Nếu ứng dụng dừng sau khi đích nhận output nhưng trước khi nhật ký được đánh dấu hoàn tất, lần phục hồi có thể gửi lại. Vì vậy, write-ahead giúp tránh mất dấu công việc nhưng không tự động bảo đảm output chỉ được phát đúng một lần. Đích nhận hoặc consumer vẫn cần hỗ trợ idempotency, hoặc phải có cơ chế đối soát.

Write-ahead log là khái niệm rộng, được dùng trong cơ sở dữ liệu và nhiều hệ thống lưu trữ để bảo đảm khả năng phục hồi. Trong một ứng dụng batch, có thể xây dựng nhật ký tác vụ riêng cho output; cần phân biệt nhật ký ứng dụng này với WAL nội bộ của database. WAL của database bảo vệ tính bền vững của thay đổi database, nhưng không tự động ghi lại ý định gửi message tới một broker độc lập.

## Transactional outbox

Transactional outbox áp dụng nguyên tắc ghi trước cho bài toán cập nhật database và phát sự kiện. Thay vì publish sự kiện ngay trong transaction xử lý nghiệp vụ, ứng dụng ghi một bản ghi vào bảng outbox trong cùng transaction với thay đổi nghiệp vụ. Một publisher riêng đọc các bản ghi chưa gửi và chuyển chúng tới broker.

Ví dụ, khi xử lý một đơn hàng, cùng một transaction database sẽ:

1. Cập nhật trạng thái đơn hàng thành `PROCESSED`.
2. Thêm sự kiện `OrderProcessed` vào bảng `outbox_event`.
3. Commit cả hai thay đổi.

Nếu transaction rollback, cả trạng thái đơn hàng và bản ghi outbox đều không tồn tại dưới dạng thay đổi đã commit. Nếu transaction commit, sự kiện đã được lưu bền vững và publisher có thể gửi nó kể cả khi batch dừng ngay sau đó.

### Thiết kế bảng outbox

Một cấu trúc đơn giản có thể như sau:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_event (published_at, created_at);
```

`event_id` là định danh ổn định để publisher và consumer nhận biết bản gửi lặp. `aggregate_id` liên kết sự kiện với thực thể nghiệp vụ, chẳng hạn mã đơn hàng. `payload` lưu nội dung sự kiện hoặc dữ liệu đủ để tạo message. `published_at` biểu thị publisher đã ghi nhận việc gửi thành công; `attempt_count` hỗ trợ theo dõi retry. Với hệ thống tải cao, có thể bổ sung trạng thái claim/lease, `next_attempt_at`, thông tin lỗi gần nhất, phiên bản schema và chỉ mục phù hợp với truy vấn polling.

Không nên dùng riêng `published_at` làm cơ chế khóa đồng thời nếu có nhiều publisher. Các worker có thể cùng đọc một hàng chưa gửi. Cần claim bản ghi một cách nguyên tử, ví dụ bằng `SELECT ... FOR UPDATE SKIP LOCKED` nếu database hỗ trợ, hoặc dùng cột lease/claim token và cập nhật có điều kiện. Cú pháp và mức độ hỗ trợ phụ thuộc database.

### Ghi nghiệp vụ và outbox trong cùng transaction

Trong Spring Batch, phần ghi dữ liệu nghiệp vụ và phần thêm outbox nên chạy trên cùng database connection/transaction được quản lý bởi transaction manager của step. Ví dụ minh họa dưới đây dùng `JdbcTemplate`; các lớp domain và SQL cần điều chỉnh theo ứng dụng thực tế.

```java
public record ProcessedOrder(
        String orderId,
        String eventId,
        String eventPayload) {
}

public class OrderAndOutboxWriter
        implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    public OrderAndOutboxWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        for (ProcessedOrder item : chunk) {
            jdbcTemplate.update(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                "PROCESSED", item.orderId());

            jdbcTemplate.update("""
                INSERT INTO outbox_event
                    (event_id, aggregate_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                item.eventId(),
                item.orderId(),
                "OrderProcessed",
                item.eventPayload());
        }
    }
}
```

Đoạn code thể hiện nguyên tắc: writer chỉ ghi database, không gọi broker. Để hai câu lệnh thực sự cùng commit hoặc rollback, `JdbcTemplate` phải sử dụng `DataSource` gắn với transaction manager của step. Nếu writer ghi qua một datasource khác hoặc transaction manager khác, tính nguyên tử không còn được bảo đảm như ví dụ. Trong triển khai thực tế, cần kiểm tra cấu hình step, datasource và transaction manager đang được sử dụng.

`eventId` phải ổn định qua retry. Nếu mỗi lần gọi writer lại sinh một UUID mới, retry có thể tạo nhiều bản ghi outbox cho cùng một sự kiện nghiệp vụ. Có thể tạo event ID từ định danh nghiệp vụ và loại/phiên bản sự kiện, hoặc lưu ID đã tạo ở bước xử lý để nó được giữ nguyên qua retry. Thêm unique constraint phù hợp giúp database từ chối bản ghi trùng, nhưng logic xử lý xung đột vẫn phải được thiết kế rõ ràng.

### Publisher chuyển tiếp outbox

Một publisher độc lập có thể chạy theo lịch hoặc là một tiến trình nền. Nó lấy một lô sự kiện chưa gửi, claim chúng, publish lên broker, rồi đánh dấu đã gửi sau khi nhận xác nhận phù hợp từ broker.

```text
Outbox table
    |
    v
Publisher claim một lô bản ghi
    |
    v
Publish từng message (kèm event_id)
    |
    v
Broker xác nhận nhận message
    |
    v
Đánh dấu published_at và giải phóng claim
```

Thứ tự giữa publish và cập nhật trạng thái rất quan trọng. Nếu đánh dấu đã gửi trước khi broker xác nhận, sự cố có thể làm mất message. Nếu broker đã nhận message nhưng publisher dừng trước khi đánh dấu, publisher sẽ gửi lại ở lần chạy sau. Vì vậy, cách triển khai phổ biến ưu tiên không mất sự kiện và chấp nhận khả năng giao ít nhất một lần (at-least-once). Consumer phải xử lý message lặp an toàn.

Pseudo-code minh họa:

```java
for (OutboxEvent event : outboxRepository.claimBatch(batchSize)) {
    try {
        brokerPublisher.publish(event.eventId(), event.payload());
        outboxRepository.markPublished(event.eventId());
    } catch (TransientPublishException ex) {
        outboxRepository.recordFailure(event.eventId(), ex.getMessage());
        // Để sự kiện được thử lại theo chính sách retry.
    }
}
```

Đây là phác thảo luồng, không phải triển khai hoàn chỉnh cho mọi broker. Cần xác định `publish` trả về khi message đã được broker xác nhận hay chỉ khi request đã được xếp vào bộ đệm của client. Với API bất đồng bộ, publisher phải chờ kết quả xác nhận trước khi đánh dấu bản ghi. Nếu việc publish và đánh dấu outbox nằm trong hai hệ thống transaction độc lập, khoảng trống lỗi giữa chúng vẫn tồn tại; consumer idempotent là lớp bảo vệ cần thiết.

## Consumer idempotent và xử lý message lặp

Outbox thường cung cấp ngữ nghĩa at-least-once. Một consumer có thể nhận cùng `event_id` nhiều lần khi publisher retry hoặc khi broker redeliver. Consumer nên lưu dấu đã xử lý cùng transaction với thay đổi nghiệp vụ của chính nó.

Ví dụ bảng inbox:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Khi nhận message, consumer bắt đầu transaction, thử insert cặp `consumer_name` và `event_id`, rồi chỉ thực hiện thay đổi nghiệp vụ nếu insert thành công. Nếu khóa đã tồn tại, message đã được xử lý trước đó và có thể được xác nhận mà không chạy lại nghiệp vụ. Việc insert dấu đã xử lý và cập nhật dữ liệu phải cùng transaction; nếu tách chúng ra, lỗi giữa hai thao tác có thể khiến consumer bỏ qua công việc hoặc thực hiện lặp.

Idempotency cũng có thể được triển khai bằng cập nhật có điều kiện, upsert hoặc API đích nhận idempotency key. Cần chọn khóa theo ý nghĩa nghiệp vụ: cùng một event được gửi lại phải có cùng khóa, còn hai sự kiện hợp lệ khác nhau phải có khóa khác nhau.

## Áp dụng trong Spring Batch

Có một số cách bố trí outbox quanh job và step:

- **Ghi outbox ngay trong writer của step nghiệp vụ:** phù hợp khi dữ liệu nghiệp vụ và outbox cùng database, cùng transaction. Đây thường là lựa chọn đơn giản nhất vì commit/rollback của chunk bao trùm cả hai loại bản ghi.
- **Dùng step riêng để phát outbox:** step sau đọc các bản ghi outbox còn chờ và gửi message. Cách này phù hợp khi muốn quản lý việc phát message như một phần của job, nhưng cần xử lý cẩn thận việc claim, retry và cập nhật trạng thái.
- **Dùng publisher chạy độc lập:** phù hợp khi sự kiện cần được phát liên tục, không phụ thuộc lần chạy batch kế tiếp. Publisher có thể là service nền hoặc scheduled task và dùng chung bảng outbox.

Không nên gọi dịch vụ bên ngoài trực tiếp từ `ItemWriter` rồi giả định rollback chunk sẽ thu hồi được lời gọi đó. Một HTTP request đã được hệ thống từ xa xử lý thường không thể được database rollback. Nếu cần ghi file, gọi API hoặc phát message, hãy xác định liệu có thể ghi một chỉ thị bền vững vào database trước, rồi để một thành phần chuyên trách thực hiện output và ghi nhận kết quả hay không.

### Retry, skip và restart

Spring Batch có thể retry một item hoặc chunk tùy cấu hình, và có thể restart job từ trạng thái đã lưu. Điều này khiến tính lặp an toàn trở thành yêu cầu quan trọng:

- Tạo định danh output ổn định, không đổi qua retry/restart của cùng một sự kiện.
- Đặt unique constraint cho khóa sự kiện để ngăn tạo bản ghi outbox trùng ngoài ý muốn.
- Đảm bảo transaction rollback loại bỏ cả thay đổi nghiệp vụ và outbox khi chunk thất bại.
- Không đánh dấu outbox đã gửi trước khi nhận xác nhận phù hợp từ broker.
- Thiết kế retry có backoff và giới hạn hợp lý; lỗi lâu dài cần được lưu để điều tra hoặc chuyển sang trạng thái cần can thiệp.
- Nếu một item bị skip, xác định rõ có cần phát sự kiện lỗi/skip hay không. Không tự động phát sự kiện thành công cho item chưa hoàn tất nghiệp vụ.

Với job restart, repository của Spring Batch lưu trạng thái thực thi để điều phối việc tiếp tục step, nhưng repository đó không thay thế outbox nghiệp vụ. Trạng thái job cho biết tiến trình batch đã đi đến đâu; bảng outbox ghi lại các sự kiện cần chuyển tiếp. Hai cơ chế có mục đích khác nhau và cần được duy trì nhất quán.

## Thứ tự sự kiện và xử lý song song

Nếu các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, publisher cần duy trì thứ tự theo `aggregate_id` hoặc một sequence nghiệp vụ. Chỉ sắp xếp theo `created_at` có thể chưa đủ khi nhiều transaction tạo sự kiện đồng thời hoặc timestamp có độ phân giải thấp. Có thể lưu sequence tăng dần theo aggregate, sau đó phân vùng message theo aggregate key để broker giữ thứ tự trong một partition.

Khi nhiều publisher chạy song song, cần ngăn hai publisher cùng phát một bản ghi trong điều kiện bình thường. Claim bằng row lock, `SKIP LOCKED`, lease có thời hạn hoặc cơ chế phân vùng là các lựa chọn. Lease cần có timeout và token để publisher cũ không thể cập nhật trạng thái sau khi quyền claim đã chuyển sang worker khác. Dù claim đúng, sự cố sau khi broker nhận message vẫn có thể dẫn tới gửi lặp; consumer idempotent vẫn cần thiết.

## Vận hành và bảo trì outbox

Outbox là một phần của đường đi dữ liệu nên cần được quan sát như một hàng đợi. Những chỉ số hữu ích gồm:

- Số lượng bản ghi chưa publish.
- Tuổi của bản ghi chưa publish lâu nhất.
- Thời gian từ lúc tạo đến lúc broker xác nhận.
- Tỷ lệ publish lỗi, số lần thử và số bản ghi cần can thiệp.
- Tốc độ tạo sự kiện so với tốc độ publisher xử lý.

Nếu backlog tăng liên tục, publisher đang xử lý chậm hơn tốc độ batch tạo sự kiện hoặc broker đang gặp vấn đề. Cần đặt cảnh báo theo tuổi backlog và tốc độ tăng, vì chỉ đếm số lượng có thể không phản ánh mức độ trễ đối với hệ thống có lưu lượng biến động.

Các bản ghi đã publish có thể được lưu trong một khoảng thời gian phục vụ đối soát rồi dọn theo lô. Chính sách retention phải tính đến khả năng replay, yêu cầu kiểm toán và thời gian tối đa consumer có thể cần tra cứu. Không xóa bản ghi chưa publish hoặc bản ghi đang được claim. Với payload lớn, có thể lưu tham chiếu đến dữ liệu bất biến thay vì sao chép toàn bộ nội dung, nhưng tham chiếu phải còn khả dụng trong suốt thời gian retry và replay.

## Khi nào chọn write-ahead hoặc outbox?

Write-ahead là nguyên tắc tổng quát hữu ích khi cần lưu lại ý định hoặc tiến độ trước khi thực hiện output có thể thất bại. Nó phù hợp với các quy trình cần khả năng phục hồi, đối soát hoặc phát lại, kể cả khi output không phải message.

Transactional outbox phù hợp đặc biệt khi một transaction database vừa thay đổi dữ liệu nghiệp vụ vừa tạo sự kiện cho hệ thống khác. Nó thu hẹp bài toán thành một transaction cục bộ có thể quản lý: commit dữ liệu nghiệp vụ và bản ghi outbox cùng nhau; chuyển tiếp message được thực hiện sau đó với retry.

| Tiêu chí | Write-ahead log/record | Transactional outbox |
|---|---|---|
| Mục tiêu | Ghi bền vững ý định hoặc thao tác để phục hồi | Gắn thay đổi nghiệp vụ với sự kiện cần phát |
| Phạm vi | Khái niệm rộng, có thể áp dụng cho nhiều loại output | Mẫu tích hợp thường dùng với database và message broker |
| Ghi nhận | Nhật ký được ghi trước hành động | Bản ghi outbox commit cùng dữ liệu nghiệp vụ |
| Phát lại | Thành phần phục hồi đọc nhật ký chưa hoàn tất | Publisher đọc và gửi các hàng outbox chưa publish |
| Vấn đề còn lại | Có thể phát lặp nếu lỗi sau khi đích nhận | Có thể phát lặp nếu broker nhận nhưng trạng thái outbox chưa cập nhật |
| Bảo vệ cần có | ID ổn định, đối soát và xử lý lặp an toàn | Event ID, claim an toàn và consumer idempotent |

Nếu cả dữ liệu nghiệp vụ và output đều nằm trong cùng một database, ghi chúng trong một transaction có thể đã đủ. Nếu đích output là hệ thống bên ngoài và không tham gia transaction đó, outbox thường là lựa chọn dễ vận hành hơn so với cố gắng tạo một giao dịch phân tán. Nếu yêu cầu nghiệp vụ đòi hỏi bảo đảm mạnh hơn, cần đánh giá khả năng hỗ trợ giao dịch của broker, cơ chế xác nhận, idempotency và quy trình phục hồi toàn hệ thống; không nên tuyên bố “exactly once” chỉ vì đã dùng outbox.

## Checklist thiết kế trước khi triển khai

1. Xác định output nào nằm ngoài transaction của step và mô tả các điểm tiến trình có thể dừng.
2. Chọn nơi lưu bền vững cho ý định output; với sự kiện phát sinh từ thay đổi database, cân nhắc transactional outbox.
3. Bảo đảm thay đổi nghiệp vụ và bản ghi outbox dùng cùng datasource và transaction manager.
4. Xác định event ID ổn định và khóa duy nhất phù hợp với nghiệp vụ.
5. Thiết kế publisher có claim an toàn, xác nhận broker, retry và xử lý lỗi lâu dài.
6. Thiết kế consumer idempotent và commit dấu đã xử lý cùng thay đổi nghiệp vụ.
7. Quy định thứ tự theo aggregate nếu nghiệp vụ yêu cầu.
8. Theo dõi backlog, tuổi sự kiện, lỗi publish và dung lượng bảng; xác định chính sách retention.
9. Kiểm tra các tình huống dừng tiến trình ở từng ranh giới: trước commit, sau commit, trước publish, sau broker ack và trước khi đánh dấu published.

Mục tiêu của write-ahead và outbox là biến một hành động output dễ bị mất khi tiến trình gặp sự cố thành công việc bền vững, có thể tiếp tục và đối soát. Trong Spring Batch, cách triển khai hiệu quả bắt đầu từ việc đặt đúng ranh giới transaction của chunk, ghi outbox cùng dữ liệu nghiệp vụ, rồi xử lý việc chuyển tiếp bằng publisher có retry và consumer idempotent.
