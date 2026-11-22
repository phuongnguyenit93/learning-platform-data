# Kiểm tra replay an toàn

Replay trong Kafka là việc đọc lại một hoặc nhiều bản ghi đã từng được consumer xử lý, thường để khôi phục dữ liệu, dựng lại projection, chạy lại logic sau khi sửa lỗi hoặc đưa bản ghi từ dead-letter topic (DLT) trở lại luồng xử lý. Replay rất hữu ích, nhưng mỗi lần đọc lại đều có thể kích hoạt lại thay đổi dữ liệu và tác dụng phụ bên ngoài. Vì vậy, một lần replay chỉ an toàn khi ta xác định được chính xác dữ liệu sẽ được đọc, hiểu được logic sẽ chạy và chứng minh được việc xử lý lặp không làm sai trạng thái nghiệp vụ.

Trong Spring Kafka, cần phân biệt ba tình huống:

- **Retry** là thử lại một lần giao nhận đang thất bại, thường do lỗi tạm thời như timeout hoặc dịch vụ phụ thuộc chưa sẵn sàng.
- **Replay theo offset** là đưa vị trí đọc của consumer group về một offset cũ để consumer đọc lại các bản ghi trong topic.
- **DLT replay** là lấy những bản ghi đã được chuyển sang dead-letter topic, sửa nguyên nhân hoặc điều kiện xử lý rồi phát chúng trở lại luồng phù hợp.

Ba tình huống có thể dùng chung cơ chế idempotency, nhưng khác nhau về phạm vi dữ liệu, cách kiểm soát thứ tự và cách theo dõi tiến độ.

## 1. Các điều kiện phải xác nhận trước khi replay

Một kế hoạch replay cần trả lời được các câu hỏi sau trước khi consumer bắt đầu đọc:

| Nội dung | Điều cần xác nhận |
|---|---|
| Nguồn dữ liệu | Topic, partition, offset bắt đầu và phạm vi offset kết thúc đã được xác định. |
| Consumer | Consumer group nào sẽ đọc; group đó có consumer đang chạy hay không; cấu hình và phiên bản ứng dụng nào sẽ được dùng. |
| Đích xử lý | Bản ghi sẽ cập nhật bảng nghiệp vụ, projection, cache, topic khác hay dịch vụ bên ngoài. |
| Định danh sự kiện | Mỗi sự kiện có ID ổn định, được giữ nguyên qua retry, DLT và replay. |
| Idempotency | Việc nhận cùng một sự kiện nhiều lần không tạo ra nhiều lần thay đổi nghiệp vụ ngoài ý muốn. |
| Thứ tự | Có yêu cầu xử lý theo thứ tự trong partition hoặc theo từng aggregate hay không. |
| Dung lượng | Tốc độ replay phù hợp với database, downstream và giới hạn lưu lượng của hệ thống. |
| Dừng và khôi phục | Có điều kiện dừng, người chịu trách nhiệm và cách quay lại trạng thái vận hành bình thường. |

Không bắt đầu replay nếu chưa xác định được nguồn, phạm vi, consumer group hoặc tác dụng phụ. Một lệnh reset offset có thể khiến cả group đọc lại một lượng dữ liệu lớn; việc chọn nhầm group hoặc nhầm topic có thể tạo ra thay đổi ngoài phạm vi dự kiến.

## 2. Chọn cách replay phù hợp

Không phải lần replay nào cũng cần reset offset của consumer group đang phục vụ production.

| Cách thực hiện | Dùng khi nào | Điểm cần kiểm soát |
|---|---|---|
| Consumer group riêng | Dựng lại projection, backfill hoặc chạy thử một tập dữ liệu. | Group mới có offset độc lập. Nếu đích là dữ liệu production, vẫn phải kiểm soát idempotency và tác dụng phụ. |
| Reset offset của group hiện tại | Cần cho consumer production đọc lại một đoạn dữ liệu trong chính luồng hiện có. | Dừng toàn bộ consumer của group, xem trước kết quả reset, giới hạn đúng topic và partition. |
| DLT replay | Bản ghi đã thất bại được xử lý lại sau khi sửa dữ liệu hoặc khắc phục dependency. | Giữ nguyên event ID và metadata nguồn; tránh vòng lặp DLT vô hạn; theo dõi từng bản ghi được phát lại. |
| Topic replay riêng | Cần kiểm tra logic mới hoặc chạy lại dữ liệu trong môi trường có kiểm soát. | Tách đích replay, cấu hình quyền truy cập và tốc độ; không để consumer production vô tình nhận bản ghi thử nghiệm. |

Consumer group riêng thường phù hợp cho backfill vì không làm thay đổi offset đang dùng của group production. Tuy nhiên, group riêng không tự làm cho replay an toàn: nếu listener vẫn ghi vào cùng bảng hoặc gọi cùng API production, các tác dụng phụ vẫn xảy ra. Khi có thể, hãy chạy thử vào database hoặc topic đích riêng trước khi chuyển kết quả sang production.

## 3. Idempotency là hàng rào chính chống xử lý trùng

Kafka consumer thường được vận hành theo ngữ nghĩa **at-least-once**: một bản ghi có thể được giao lại nếu ứng dụng đã hoàn tất thay đổi dữ liệu nhưng bị dừng trước khi offset được commit. Replay chủ động cũng tạo ra cùng tình huống lặp. Vì vậy, không nên giả định rằng một event chỉ được xử lý đúng một lần.

Mỗi sự kiện nghiệp vụ nên có một `eventId` bất biến. Kafka record key thường đại diện cho aggregate hoặc thực thể dùng để phân vùng và giữ thứ tự; nó không nhất thiết là event ID. Hai sự kiện khác nhau của cùng một đơn hàng có thể dùng cùng Kafka key nhưng phải có hai event ID riêng.

Với xử lý ghi vào database, một cách phổ biến là lưu dấu vết đã xử lý trong bảng inbox hoặc bảng deduplication. Khóa duy nhất thường gồm tên consumer logic và event ID. Việc ghi dấu đã xử lý và thay đổi dữ liệu nghiệp vụ phải nằm trong cùng một transaction database.

Ví dụ sau dùng cú pháp PostgreSQL để minh họa thao tác chèn có kiểm tra trùng:

```java
@Service
public class OrderEventProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final OrderProjectionRepository projectionRepository;

    public OrderEventProcessor(
            JdbcTemplate jdbcTemplate,
            OrderProjectionRepository projectionRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.projectionRepository = projectionRepository;
    }

    @Transactional
    public void applyOnce(OrderCreated event) {
        int inserted = jdbcTemplate.update(
            """
            INSERT INTO consumed_event (consumer_name, event_id, processed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-projection-v1",
            event.eventId()
        );

        if (inserted == 0) {
            // Sự kiện đã được xử lý thành công trước đó.
            return;
        }

        projectionRepository.apply(event);
    }
}
```

Trong ví dụ này, database cần có unique constraint trên `(consumer_name, event_id)`. Nếu cập nhật projection thất bại, transaction rollback sẽ hoàn tác cả bản ghi inbox; lần giao tiếp theo có thể thử lại. Nếu transaction đã commit nhưng Kafka offset chưa commit, bản ghi được giao lại và thao tác insert trả về `0`, vì thế projection không bị cập nhật lần thứ hai.

Đoạn code chỉ minh họa cho PostgreSQL; với database khác, cần dùng cú pháp insert-if-absent và cơ chế unique constraint tương ứng. Không nên triển khai theo kiểu `SELECT` kiểm tra trước rồi mới `INSERT` mà không có ràng buộc duy nhất, vì hai consumer chạy đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

### Chú ý khi thay đổi phiên bản logic

Khóa deduplication phải phản ánh đúng phạm vi xử lý. Nếu `order-projection-v1` đã xử lý toàn bộ event và ta muốn dựng lại projection bằng logic mới, dùng lại cùng namespace có thể khiến mọi event bị bỏ qua. Có thể tạo namespace riêng như `order-projection-v2` và ghi vào projection mới, sau đó đối chiếu rồi chuyển sang sử dụng projection mới.

Không xóa hàng loạt dữ liệu deduplication chỉ để replay chạy lại. Việc đó có thể mở lại tác dụng phụ của những event đã được xử lý, chẳng hạn gửi email, trừ tiền hoặc tạo vận đơn. Với lệnh thanh toán hay API bên ngoài, hãy dùng idempotency key ổn định do nhà cung cấp hỗ trợ, hoặc thiết kế quy trình đối soát trước khi gửi lại yêu cầu.

## 4. Kiểm soát offset và consumer group

Offset là vị trí đọc của một consumer group trong từng partition. Reset offset thay đổi vị trí tiếp theo mà group sẽ đọc; nó không xóa bản ghi trong topic và cũng không hoàn tác các tác dụng phụ đã xảy ra ở database hoặc hệ thống bên ngoài.

### Đọc lại bằng group riêng

Với một group mới, `auto.offset.reset=earliest` cho phép consumer bắt đầu từ bản ghi sớm nhất còn được lưu khi group chưa có offset hợp lệ. Thuộc tính này **không** tự đưa một group đang có committed offset về đầu topic. Nếu group đã có offset, consumer tiếp tục từ offset đã commit.

Đặt group ID riêng cho từng lượt backfill có kiểm soát giúp theo dõi offset và lag độc lập. Ghi lại group ID, topic, thời điểm bắt đầu, cấu hình `auto.offset.reset`, phiên bản ứng dụng và đích dữ liệu để có thể giải thích kết quả sau này.

### Reset offset của group hiện tại

Trước khi dùng Kafka consumer group command để reset offset:

1. Dừng toàn bộ instance đang tham gia group và xác nhận group không còn consumer hoạt động.
2. Ghi lại committed offset hiện tại của từng partition để có điểm đối chiếu.
3. Chọn đúng group, topic và partition; xác định offset bắt đầu cần đọc lại.
4. Chạy `--dry-run` và kiểm tra từng offset mà lệnh dự kiến thay đổi.
5. Chỉ sau khi xác nhận phạm vi, mới chạy lại với `--execute`.
6. Khởi động consumer và theo dõi lag, tốc độ xử lý, lỗi và tác động lên downstream.

Ví dụ xem trước việc đưa một topic về đầu cho một group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <consumer-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Sau khi xem kết quả và xác nhận đúng group/topic, thực hiện thay đổi bằng cách thay `--dry-run` thành `--execute`. Nếu chỉ cần reset một partition, có thể chỉ định topic-partition, ví dụ `--topic orders:0`. Với một offset cụ thể, dùng `--to-offset <offset>` sau khi xác minh offset đó thuộc partition cần replay.

Lệnh reset chỉ đặt vị trí bắt đầu. Nếu cần replay một khoảng có điểm kết thúc, phải có cơ chế giới hạn consumer ở offset kết thúc đã định, hoặc dừng group khi đạt mốc đã theo dõi. Không giả định rằng reset về offset bắt đầu sẽ tự giới hạn lượng dữ liệu được đọc.

### Retention và compacted topic

Replay chỉ có thể đọc dữ liệu còn tồn tại. Kiểm tra `retention.ms`, `retention.bytes`, tình trạng lưu trữ và offset sớm nhất hiện có của từng partition. Với topic dùng `cleanup.policy=compact`, Kafka có thể loại bỏ các phiên bản cũ của cùng một key; topic compacted không bảo đảm còn đầy đủ lịch sử chuyển trạng thái để dựng lại mọi thay đổi nghiệp vụ.

Nếu offset cần đọc đã nằm ngoài vùng dữ liệu còn lưu, reset offset không thể khôi phục các record đã bị xóa. Cần tìm nguồn lưu trữ hoặc bản sao dữ liệu phù hợp trước khi tiếp tục.

## 5. Bảo toàn thứ tự và giới hạn tốc độ

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các event của cùng aggregate cần được xử lý theo thứ tự, producer phải dùng key ổn định để đưa chúng vào cùng partition và consumer phải giữ được quy tắc xử lý tương ứng.

Replay có thể làm sai thứ tự quan sát ở tầng nghiệp vụ trong một số trường hợp:

- Tăng số partition có thể làm thay đổi cách key được ánh xạ sang partition cho những record mới; không giả định mọi record lịch sử và record mới của cùng key luôn ở cùng partition sau khi thay đổi partition count.
- Nhiều consumer xử lý song song hoặc listener tự đẩy công việc sang thread pool có thể hoàn tất event sau trước event trước.
- Non-blocking retry bằng retry topic hoặc `@RetryableTopic` có thể đưa event lỗi trở lại sau các event đến sau. Cách này phù hợp khi hệ thống chấp nhận xử lý trễ hoặc có cơ chế kiểm tra sequence; không phù hợp nếu thứ tự tuyệt đối là yêu cầu bắt buộc.
- DLT replay có thể phát lại nhiều event cùng aggregate theo thứ tự khác với thứ tự ban đầu nếu thao tác chọn và gửi lại không được sắp xếp.

Nếu nghiệp vụ yêu cầu thứ tự, hãy kiểm tra sequence/version của aggregate trong database. Chỉ áp dụng event có version kế tiếp hợp lệ; phát hiện event đến sớm hoặc đến muộn thì đưa vào hàng chờ xử lý lại hoặc quy trình đối soát. Với replay DLT, nhóm record theo key và sắp xếp theo sequence hoặc metadata offset gốc trước khi gửi lại.

Tốc độ replay cần được giới hạn theo năng lực của database và dịch vụ phụ thuộc. Theo dõi consumer lag, thời gian xử lý mỗi record, connection pool, lock wait, CPU, lỗi timeout và rate limit. Có thể giảm concurrency, giới hạn số record mỗi batch hoặc tạm dừng replay khi downstream vượt ngưỡng. Chỉ tăng tốc sau khi có số liệu cho thấy hệ thống chịu được tải.

## 6. Cấu hình xử lý lỗi trong Spring Kafka

Spring Kafka cung cấp các cơ chế retry và recoverer để kiểm soát lỗi listener. Khi dùng `DefaultErrorHandler`, có thể cấu hình retry có giới hạn và `DeadLetterPublishingRecoverer` để chuyển record không xử lý được sang DLT. Cần phân loại lỗi trước khi chọn retry:

- Lỗi tạm thời như timeout, lỗi mạng hoặc dịch vụ phụ thuộc đang quá tải thường có thể retry với backoff và giới hạn số lần.
- Lỗi dữ liệu như schema không hợp lệ, thiếu trường bắt buộc hoặc vi phạm quy tắc nghiệp vụ thường không tự hết khi retry. Nên chuyển sang DLT hoặc quy trình xử lý dữ liệu lỗi.
- Lỗi lập trình hoặc lỗi cấu hình cần được sửa trước khi replay hàng loạt; retry liên tục chỉ làm tăng tải và kéo dài thời gian xử lý.

Khi dùng DLT, cần bảo đảm topic đích tồn tại và có số partition phù hợp với cách `DeadLetterPublishingRecoverer` định tuyến. Cấu hình recoverer, chiến lược đặt tên DLT, serializer và quyền ghi topic phải được kiểm tra trong môi trường triển khai thực tế.

Với `@RetryableTopic`, Spring Kafka có thể tạo các retry topic và DLT để thực hiện non-blocking retry. Cách này giúp partition chính tiếp tục xử lý các record khác trong khi record lỗi chờ retry, nhưng có thể làm thay đổi thứ tự quan sát. Nếu thứ tự theo key là bắt buộc, cần chọn chiến lược retry phù hợp và có kiểm soát sequence.

### Commit offset sau khi xử lý

Với listener container, Spring Kafka quản lý commit theo `AckMode`. Chọn chế độ phù hợp với cách listener xử lý record; `AckMode.RECORD` thường dễ diễn giải khi muốn commit sau mỗi record listener xử lý thành công. Nếu dùng manual acknowledgment, chỉ acknowledge sau khi công việc cần thiết đã hoàn tất thành công.

Đối với raw Kafka consumer, thường cần `enable.auto.commit=false` để ứng dụng chủ động kiểm soát commit. Với Spring Kafka listener container, để container quản lý commit theo cấu hình của nó và tránh bật auto-commit theo cách làm mất khả năng kiểm soát thứ tự xử lý.

Khi listener cập nhật database, hãy để transaction database hoàn tất trước khi listener trả về thành công để container commit offset. Vẫn có một khoảng thời gian giữa database commit và Kafka offset commit; nếu ứng dụng dừng trong khoảng đó, record có thể được giao lại. Inbox/idempotency xử lý chính xác trường hợp này.

### Kafka transaction không bao phủ mọi tác dụng phụ

Spring Kafka hỗ trợ transaction cho luồng consume-process-produce giữa các topic Kafka. Producer transaction và consumer `isolation.level=read_committed` giúp consumer chỉ đọc các record thuộc transaction đã commit. Cơ chế exactly-once semantics của Kafka có phạm vi ở các thao tác Kafka được tham gia vào transaction đó.

Transaction Kafka không tự làm cho cập nhật database, gửi email, gọi API thanh toán hoặc thao tác trên hệ thống bên ngoài trở thành exactly-once. Với luồng database-to-Kafka, cân nhắc transactional outbox; với luồng Kafka-to-database, cân nhắc inbox và idempotency trong transaction database. Thiết kế phải xác định rõ ranh giới transaction của từng hệ thống.

## 7. Replay DLT có kiểm soát

DLT là nơi cách ly record không thể xử lý theo chính sách hiện tại. Trước khi replay DLT, cần phân loại nguyên nhân: dữ liệu sai, schema không tương thích, lỗi code, dependency tạm thời hay cấu hình sai. Chỉ phát lại sau khi nguyên nhân đã được xử lý hoặc có quyết định nghiệp vụ rõ ràng về cách bỏ qua/sửa dữ liệu.

Quy trình khuyến nghị:

1. Trích xuất số lượng record theo topic, partition, exception và thời điểm; chọn đúng nhóm record cần xử lý.
2. Kiểm tra payload, event ID, Kafka key, correlation ID và metadata của record gốc. Xác nhận schema và consumer mới có thể đọc record.
3. Giữ nguyên event ID và dữ liệu nghiệp vụ gốc. Gắn metadata replay riêng như `replay-id`, thời điểm replay và mã yêu cầu vận hành để truy vết.
4. Nếu cần sửa payload, lưu lại bản gốc, nội dung đã sửa, lý do và người phê duyệt theo quy trình vận hành. Không âm thầm thay đổi dữ liệu trong lúc replay.
5. Gửi thử một lượng nhỏ vào topic đích, xác nhận kết quả và tác dụng phụ, sau đó mới mở rộng phạm vi.
6. Theo dõi record thành công, record tiếp tục lỗi và record được chuyển DLT lần nữa. Đặt giới hạn số lần replay để tránh vòng lặp vô hạn.

Khi phát lại, giữ metadata gốc như topic, partition và offset ban đầu nếu thư viện và định dạng record cho phép. Không ghi đè event ID bằng replay ID: replay ID dùng để nhận diện một lượt vận hành, còn event ID dùng để nhận diện sự kiện nghiệp vụ xuyên suốt mọi lần giao nhận.

Không xóa record gốc khỏi DLT ngay sau khi gửi lại. Giữ lại dữ liệu và audit trail theo chính sách retention để có thể đối chiếu kết quả. Việc dọn DLT nên là thao tác riêng, có chính sách lưu trữ và thời hạn rõ ràng.

## 8. Quan sát trong và sau replay

Trong suốt lượt replay, theo dõi tối thiểu:

- **Tiến độ Kafka:** committed offset, end offset, lag theo từng partition, số record đã đọc và tốc độ tiêu thụ.
- **Kết quả listener:** số record thành công, số lần retry, số record chuyển DLT, exception theo loại và thời gian xử lý.
- **Idempotency:** số event bị nhận diện trùng, lỗi unique constraint bất thường và số event bị bỏ qua theo namespace consumer.
- **Database:** throughput ghi, connection pool, transaction rollback, lock wait, deadlock và độ trễ truy vấn.
- **Downstream:** API error, timeout, rate limit, số yêu cầu có idempotency key và trạng thái tác dụng phụ.
- **Tính đúng nghiệp vụ:** số lượng bản ghi trước/sau, tổng tiền hoặc số lượng theo aggregate, sequence bị thiếu và kết quả đối soát.

Đặt ngưỡng dừng trước khi bắt đầu, ví dụ lỗi tăng vượt ngưỡng, downstream bị rate limit liên tục, lag tăng nhanh ngoài dự kiến hoặc số liệu đối soát lệch. Khi dừng, pause consumer hoặc dừng replay theo runbook, lưu lại offset và replay ID cuối cùng, sau đó điều tra trước khi chạy tiếp.

Sau khi hoàn tất, so sánh số record trong phạm vi với số record thành công, số record trùng được bỏ qua, số record còn lỗi và số record bị loại theo quyết định nghiệp vụ. Kiểm tra trạng thái cuối của các aggregate quan trọng và xác nhận không phát sinh tác dụng phụ trùng lặp.

## 9. Kiểm thử trước khi replay production

Một lượt replay cần được diễn tập với dữ liệu đại diện trước khi chạy trên production. Bộ tình huống nên bao gồm:

| Tình huống | Kết quả mong đợi |
|---|---|
| Cùng một event được giao hai lần | Chỉ có một thay đổi nghiệp vụ được commit. |
| Ứng dụng dừng sau database commit nhưng trước offset commit | Record được giao lại và bị inbox/dedup nhận diện là đã xử lý. |
| Database transaction rollback | Dấu inbox và thay đổi nghiệp vụ cùng rollback; record có thể xử lý lại. |
| Hai consumer cùng nhận một event trong tình huống cạnh tranh | Unique constraint bảo vệ khỏi hai lần áp dụng; lỗi cạnh tranh được xử lý có chủ đích. |
| Event đến sai sequence | Không ghi đè trạng thái mới bằng trạng thái cũ; event được chờ hoặc đưa vào đối soát. |
| Dependency tiếp tục lỗi | Retry dừng theo giới hạn và record đi đến DLT đúng chính sách. |
| Replay DLT thành công | Event ID gốc được giữ, replay metadata truy vết được và record không tạo tác dụng phụ trùng. |
| Schema hoặc payload không tương thích | Record được cách ly và có thông tin lỗi đủ để điều tra. |

Ngoài kết quả từng record, hãy kiểm tra tổng thể: replay có thể chạy lại nhiều lần mà trạng thái cuối không đổi ngoài dự kiến hay không; tốc độ có thể giảm/tăng mà không làm sai thứ tự nghiệp vụ hay không; và quy trình có thể dừng rồi tiếp tục từ offset đã ghi nhận hay không.

## 10. Checklist vận hành

Trước khi bắt đầu:

- [ ] Đã xác định topic, partition, offset bắt đầu và giới hạn kết thúc.
- [ ] Đã xác định consumer group, phiên bản ứng dụng, cấu hình và đích xử lý.
- [ ] Đã kiểm tra retention, offset sớm nhất và khả năng đọc schema.
- [ ] Đã xác nhận event ID ổn định và idempotency hoạt động ở nơi phát sinh tác dụng phụ.
- [ ] Đã xác nhận yêu cầu thứ tự, concurrency và giới hạn tốc độ.
- [ ] Đã lưu offset hiện tại, replay ID, lý do replay và điều kiện dừng.
- [ ] Đã chạy thử trên phạm vi nhỏ hoặc môi trường đích riêng.

Trong khi chạy:

- [ ] Theo dõi lag, lỗi listener, retry, DLT và sức khỏe downstream.
- [ ] Kiểm tra số lượng event trùng và kết quả idempotency.
- [ ] Dừng khi chạm ngưỡng đã định hoặc số liệu nghiệp vụ sai lệch.
- [ ] Ghi lại offset cuối, thời điểm và replay ID khi tạm dừng hoặc hoàn tất.

Sau khi chạy:

- [ ] Đã đối chiếu số record trong phạm vi với kết quả thành công, trùng, lỗi và bị loại.
- [ ] Đã xác nhận trạng thái aggregate và các tác dụng phụ quan trọng.
- [ ] Đã xử lý riêng các record còn nằm trong DLT.
- [ ] Đã khôi phục cấu hình/concurrency vận hành bình thường và lưu audit trail.

Replay được xem là hoàn tất khi phạm vi dữ liệu đã xử lý được đối chiếu, trạng thái nghiệp vụ đúng, các record lỗi còn lại có chủ sở hữu xử lý và consumer group đã trở về trạng thái vận hành dự kiến. Việc consumer hết lag chỉ chứng minh nó đã đọc đến cuối dữ liệu hiện có; điều đó chưa đủ để chứng minh replay đúng về nghiệp vụ.
