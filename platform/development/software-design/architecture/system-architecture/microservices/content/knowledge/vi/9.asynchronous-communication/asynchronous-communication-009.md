# Thời gian lưu, phát lại và tác dụng phụ khi tái xử lý

## 1. Vì sao cần thiết kế retention và replay từ đầu?

Trong kiến trúc microservices giao tiếp bất đồng bộ, producer công bố event và consumer xử lý chúng vào thời điểm có thể khác nhau. Consumer có thể mất kết nối, gặp lỗi, bị triển khai sai, hoặc cần xây dựng lại dữ liệu đọc từ lịch sử. Khi đó, hệ thống thường phải **đọc lại thông điệp cũ** (*replay*) và **xử lý lại** (*reprocessing*).

Ví dụ một hệ thống thương mại điện tử có các event:

~~~text
Order Service
    |
    | OrderCreated
    v
Event Broker
    |
    +----> Order Search Projection
    |
    +----> Analytics
    |
    +----> Email Notification
    |
    +----> Fulfillment Workflow
~~~

Nếu Search Projection bị lỗi ba ngày, nhóm có thể muốn phát lại event để xây dựng lại chỉ mục tìm kiếm. Nhưng cùng một luồng event mà vô tình chạy lại Email Notification có thể khiến khách nhận email xác nhận đơn hàng lần thứ hai. Nếu handler thanh toán chạy lại thiếu kiểm soát, tác dụng phụ còn nghiêm trọng hơn.

Thiết kế đúng phải trả lời cả hai câu hỏi:

1. **Dữ liệu sự kiện được giữ bao lâu, có còn đủ để khôi phục không?**
2. **Khi xử lý lại, tác dụng phụ nào được phép xảy ra, tác dụng phụ nào phải bị chặn hoặc đối soát?**

Học xong bài này, bạn có thể:

- Phân biệt retention, replay, redelivery, retry, dead-letter và reprocessing.
- Chọn cách lưu thông điệp phù hợp với nhu cầu khôi phục, kiểm toán và chi phí.
- Hiểu giới hạn của event log, message queue, log compaction và snapshot.
- Xác định consumer nào có thể tái dựng an toàn và consumer nào tạo tác dụng phụ.
- Thiết kế idempotency, inbox, outbox và cơ chế ngăn tác dụng phụ lặp.
- Lập runbook phát lại có phạm vi, điểm bắt đầu/kết thúc, quyền kiểm soát và phép đo.
- Kiểm thử tình huống consumer lỗi, broker xóa dữ liệu, duplicate và replay nhiều lần.

**Nguyên tắc quan trọng:** replay là hành động có thể gây thay đổi hệ thống. Khả năng đọc lại một event không tự đảm bảo việc chạy lại handler là an toàn.

## 2. Phân biệt các khái niệm thường bị trộn lẫn

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Retention** | Chính sách giữ thông điệp trong broker hoặc kho lịch sử | Giữ event theo thời gian hoặc dung lượng cấu hình |
| **Replay** | Đọc lại các event đã được ghi nhận trước đó | Đọc lại OrderCreated để dựng lại search index |
| **Reprocessing** | Chạy lại logic xử lý event; có thể tạo trạng thái/tác dụng phụ mới | Consumer dựng lại projection từ những event cũ |
| **Redelivery** | Broker chuyển lại thông điệp chưa được xử lý/xác nhận thành công | Consumer crash trước ack, message được giao lại |
| **Retry** | Thử lại xử lý sau một lỗi có thể hồi phục | Gọi lại API phụ thuộc với backoff |
| **Dead-letter queue (DLQ)** | Nơi cách ly message không xử lý được theo policy | Event sai schema hoặc luôn gây lỗi validation |
| **Checkpoint / offset** | Dấu mốc consumer đã đọc hoặc xử lý đến đâu | Kafka consumer group offset |
| **Snapshot** | Trạng thái tổng hợp tại một mốc, giúp tái dựng nhanh hơn | Số dư/aggregate version tại một sequence |
| **Log compaction** | Giữ các bản ghi mới nhất theo key theo chính sách cleanup | Key trạng thái của một thực thể |
| **Tombstone** | Dấu hiệu xóa trong một số mô hình keyed log/compaction | Key với giá trị null trên Kafka compacted topic |

Các thao tác này không tương đương. **Redelivery** có thể xảy ra tự động ngay trong hoạt động bình thường; **replay lịch sử** thường là quyết định có chủ đích để khôi phục hoặc xây dựng lại dữ liệu. Một DLQ không mặc định là kho lịch sử đầy đủ. Snapshot giúp khôi phục trạng thái nhanh nhưng có thể không chứa tất cả biến cố đã xảy ra.

## 3. Thời gian lưu phải trả lời nhu cầu nào?

Không nên chọn retention bằng cách lấy một con số phổ biến rồi áp vào mọi topic. Hãy xác định mục đích giữ dữ liệu:

1. **Chống consumer ngừng hoạt động tạm thời.** Nếu consumer ngừng hai ngày, log phải còn những event chưa đọc khi quay lại.
2. **Khôi phục khi logic xử lý có lỗi.** Nếu một bug làm dữ liệu projection sai trong nhiều ngày trước khi được phát hiện, cần lịch sử đủ xa để tái dựng.
3. **Onboarding consumer mới.** Một consumer phân tích mới có thể cần đọc từ một thời điểm lịch sử.
4. **Đối soát và điều tra sự cố.** Cần dữ liệu sự kiện, correlation ID và thay đổi trạng thái tương ứng.
5. **Yêu cầu lưu trữ hoặc xóa dữ liệu.** Không phải dữ liệu nào cũng được phép giữ lâu; bảo mật và chính sách xóa dữ liệu có thể đặt giới hạn ngược lại.
6. **Kiểm soát chi phí và hiệu năng.** Broker không phải kho lưu trữ miễn phí; dung lượng, replica, IO, egress và thời gian khôi phục đều có chi phí.

Một ước lượng khởi đầu cho cửa sổ giữ:

~~~text
Retention window cần thiết >=
    thời gian ngừng consumer tối đa dự kiến
  + thời gian phát hiện, xử lý sự cố và khôi phục
  + khoảng đệm cho vận hành / tải bất thường
~~~

Đây là cách tư duy lập kế hoạch, **không phải công thức bảo đảm**: cần tính cả chính sách xóa theo dung lượng, hành vi cleanup của broker, khả năng phát hiện lỗi muộn và nhu cầu backfill dài hạn. Nếu muốn replay sự kiện nhiều tháng mà chỉ giữ broker log vài ngày, hãy có kho lịch sử riêng hoặc kế hoạch tái dựng từ nguồn sự thật.

### 3.1. Ví dụ ước lượng dung lượng

Giả sử topic nhận khoảng **2 triệu event/ngày**, mỗi event trung bình **1 KiB**:

~~~text
Khối lượng logic mỗi ngày  ≈ 2.000.000 KiB ≈ 1,91 GiB
Trong 14 ngày             ≈ 26,7 GiB dữ liệu payload
~~~

Đây chỉ là số lượng payload logic theo giả định. Dung lượng thực tế phụ thuộc key, header, index, compression, segment, replica, cơ chế lưu trữ, retention-by-size và overhead của broker. Cần đo trên workload thật, rồi ước tính cả chi phí đọc lại khi cần replay.

Nếu consumer chỉ cần khôi phục sau vài giờ nhưng nhóm nghiệp vụ cần điều tra lịch sử sáu tháng, có thể phân tầng: broker phục vụ dòng sự kiện vận hành; kho archive/ledger đáng tin cậy phục vụ lịch sử dài hạn theo chính sách.

## 4. Các kiểu lưu thông điệp và giới hạn của chúng

### 4.1. Append-only event log

Một log có tính chất cho phép consumer đọc theo vị trí đã lưu và có thể đọc lại phần vẫn còn được giữ. Ví dụ điển hình là Kafka topic có retention.

~~~text
Partition 0:
offset 100 -> 101 -> 102 -> ... -> 350
                  ^           ^
              checkpoint     latest

Consumer có thể seek lại các offset còn tồn tại.
~~~

Điểm quan trọng:

- Offset là vị trí trong partition, **không phải định danh nghiệp vụ toàn cục**.
- Consumer group lưu tiến độ; topic có thể vẫn giữ dữ liệu sau khi consumer đã đọc.
- Retention theo thời gian/dung lượng có thể loại bỏ bản ghi cũ dù consumer chưa xử lý.
- Khi một offset quá cũ đã bị xóa, việc seek đến đó không làm dữ liệu tự xuất hiện trở lại.
- Thứ tự thường được đảm bảo trong **một partition**, không phải toàn bộ topic nhiều partition.
- Topic được compact có thể không còn mọi lần thay đổi cũ.

### 4.2. Work queue

Một message queue có thể tối ưu cho việc giao công việc cho consumer và xóa/đánh dấu hoàn tất sau ack. Hành vi lưu và replay phụ thuộc broker cụ thể: RabbitMQ queue, SQS, Kafka log và các hệ thống khác có cơ chế hoàn toàn khác nhau.

**Không giả định** rằng “message được ack rồi vẫn replay được”. Với nhiều work queue, message đã hoàn tất không còn trong queue. Nếu có yêu cầu xây dựng lại lịch sử, cần event store, archive hoặc một log độc lập.

### 4.3. Dead-letter queue không thay thế archive

DLQ thường chỉ chứa **những thông điệp không xử lý được**, nên không có đủ event thành công để dựng lại trạng thái. DLQ cũng có retention, giới hạn dung lượng, payload có thể chứa dữ liệu nhạy cảm và nguy cơ bị gửi lại nhiều lần.

Quy trình xử lý DLQ cần nêu rõ:

- Khi nào đẩy message vào DLQ?
- Lý do thất bại và số lần retry ở đâu?
- Ai quyết định sửa schema/code hoặc bỏ event không hợp lệ?
- Khi phát lại từ DLQ có dùng lại event ID và idempotency key không?
- Thứ tự với các event mới và phiên bản dữ liệu hiện tại được xử lý thế nào?
- Khi nào cần dừng replay để tránh tiếp tục tạo lỗi?

## 5. Retention theo thời gian, dung lượng và compaction

Trong hệ thống dùng Kafka, cần phân biệt ít nhất ba chính sách:

### 5.1. Time-based retention

Broker có thể giữ log theo cấu hình thời gian, nhưng việc xóa diễn ra theo segment và cleanup policy, không có nghĩa mọi message biến mất chính xác tại một mili giây cụ thể. Đừng biến retention time thành lời hứa lưu đến đúng thời điểm nếu chưa kiểm tra behavior vận hành.

### 5.2. Size-based retention

Một topic có thể được giới hạn dung lượng. Khi lưu lượng tăng đột biến, dữ liệu cũ có thể bị xóa sớm hơn khoảng thời gian bạn dự tính từ chính sách theo thời gian. Khi các điều kiện retention cùng có hiệu lực, cần kiểm tra điều kiện cleanup thực tế của broker và từng partition.

Vì vậy, **cửa sổ replay hiệu dụng** phải được đo, không chỉ đọc giá trị retention trong file cấu hình.

### 5.3. Log compaction

Log compaction giữ lại các bản ghi theo **key** để consumer có thể xây dựng trạng thái keyed gần nhất; nó không giữ toàn bộ lịch sử thay đổi của từng key.

Ví dụ:

~~~text
Event theo key = order-42:

offset 10: status = CREATED
offset 25: status = PAID
offset 81: status = SHIPPED

Sau compaction, một số bản ghi cũ có thể không còn.
~~~

Nếu mục đích là dựng trạng thái mới nhất của bảng tham chiếu, compacted log có thể phù hợp. Nếu cần phát lại **đầy đủ mọi bước nghiệp vụ** để tính kiểm toán hay thanh toán, compacted log không bảo đảm dữ liệu cần thiết.

Tombstone biểu diễn việc xóa key trong compacted topic và có vòng đời retention riêng. Nếu consumer mới phục hồi từ snapshot cũ nhưng không còn nhìn thấy tombstone cần thiết, dữ liệu đã xóa có thể bị hồi sinh trong projection. Phải đưa quy trình xóa và compaction vào chiến lược replay.

## 6. Sự kiện cần có định danh và ngữ nghĩa ổn định

Ví dụ envelope cho event đặt hàng:

~~~json
{
  "eventId": "evt_84c7",
  "eventType": "order.created.v1",
  "aggregateId": "ord_731",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T08:00:00Z",
  "correlationId": "req_52d1",
  "producer": "order-service",
  "payload": {
    "orderId": "ord_731",
    "customerId": "cus_93",
    "currency": "VND",
    "totalAmount": 240000
  }
}
~~~

Các trường phục vụ mục đích khác nhau:

| Trường | Dùng cho | Lưu ý |
|---|---|---|
| **eventId** | Nhận diện một event khi dedup/replay | ID phải ổn định khi redelivery hoặc replay cùng event |
| **eventType/version** | Chọn handler và schema | Version phải phản ánh tương thích ngữ nghĩa |
| **aggregateId** | Nhóm event theo thực thể | Có thể dùng làm partition key để giữ thứ tự theo aggregate |
| **aggregateVersion** | Phát hiện event cũ, out-of-order hoặc thiếu version | Phải được producer tăng và bảo vệ đúng |
| **occurredAt** | Thời điểm nghiệp vụ/event được tạo | Khác thời điểm consumer xử lý |
| **correlationId** | Truy vết luồng yêu cầu | Không dùng thay eventId |
| **producer** | Xác định chủ sở hữu sự kiện | Consumer không được tự sửa dữ liệu của producer |
| **payload** | Dữ liệu hợp đồng cho consumer | Hạn chế PII; không giả định chứa mọi trường nội bộ |

Có event ID **không đủ** để bảo đảm idempotency. Consumer phải lưu và kiểm tra ID một cách bền vững. Nếu producer phát hai event với ID khác nhau cho cùng một thao tác nghiệp vụ, dedup bằng eventId không nhận ra chúng trùng: cần business operation ID hoặc invariant theo domain.

## 7. Event được giao lại là tình huống bình thường

Giả sử consumer làm các bước:

~~~text
1. Broker giao OrderCreated
2. Consumer ghi dữ liệu vào database
3. Consumer commit thành công
4. Consumer crash trước khi ack / commit offset
5. Broker giao lại cùng event
~~~

Nếu handler ghi thêm bản ghi hoặc trừ số dư thêm một lần, hệ thống sẽ sai dù lần đầu xử lý thành công. Đây là tình huống **at-least-once delivery** thông dụng.

Một số hệ thống có chức năng transaction hoặc “exactly once processing” trong phạm vi stream/broker được định nghĩa rõ. Tuy nhiên, không được suy ra **exactly once business effect trên mọi hệ thống bên ngoài**. Gọi HTTP tới cổng thanh toán, gửi email hoặc ghi vào database không cùng transaction với broker vẫn có thể bị lặp khi crash.

Một consumer an toàn cần phân biệt:

- **Delivery:** message có thể đến một hay nhiều lần.
- **Processing:** handler có thể được chạy lại.
- **Business effect:** kết quả nghiệp vụ có được tạo thêm lần nữa không.

Điều cần bảo vệ thường là **một hiệu ứng nghiệp vụ duy nhất cho một thao tác logic**, trong phạm vi idempotency đã xác định.

## 8. Tác dụng phụ khi reprocessing: phân loại trước khi replay

Không phải mọi consumer đều có thể được phát lại theo cùng một cách.

| Consumer / tác vụ | Khi phát lại event cũ | Chiến lược an toàn |
|---|---|---|
| **Search projection** | Cập nhật hoặc tái tạo chỉ mục | Xây dựng vào index mới, dùng version/ordering, đổi alias sau khi xác minh |
| **Read model / CQRS projection** | Tái dựng trạng thái từ event | Dựng bảng mới, xử lý có thứ tự, atomically switch khi đúng |
| **Analytics** | Có thể cộng số liệu thêm lần nữa | Tái tính vào dataset mới hoặc upsert theo event/business key |
| **Email/SMS** | Có thể gửi trùng thông báo | Tắt tác dụng phụ trong chế độ rebuild, dedup theo notification intent |
| **Inventory reservation** | Có thể giữ hàng lần thứ hai | Không replay trực tiếp lệnh tác động tồn kho; kiểm tra trạng thái và invariant |
| **Payment / refund** | Có nguy cơ thu/hoàn tiền hai lần | Đối soát với provider, dùng idempotency key và trạng thái thao tác |
| **Webhook tới đối tác** | Có thể kích hoạt xử lý bên thứ ba | Phát lại qua cơ chế có kiểm soát, policy đối tác, event ID ổn định |
| **Audit log** | Có thể ghi thêm dòng giống hành động mới | Ghi nhận nguồn replay, xử lý event identity ổn định, không giả mạo thời điểm |
| **Cache** | Có thể ghi đè bản mới bằng dữ liệu cũ | Kiểm tra version/fencing hoặc invalidate rồi rebuild |

**Không nên phát lại mọi consumer trên cùng topic chỉ để sửa một projection.** Tách nhóm consumer và đường xử lý để replay có phạm vi rõ. Có thể dùng một consumer group riêng hoặc pipeline rebuild riêng để không ảnh hưởng luồng live.

## 9. Thiết kế handler idempotent cho trạng thái nội bộ

Với dữ liệu được ghi trong **cùng database**, một mô hình thường dùng là **inbox** / bảng các event đã xử lý. Lưu marker dedup và thay đổi nghiệp vụ trong **cùng transaction**.

Ví dụ lược đồ PostgreSQL minh họa:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    aggregate_version BIGINT NOT NULL
);
~~~

Quy trình xử lý:

~~~text
BEGIN TRANSACTION

  INSERT (consumer_name, event_id) vào consumer_inbox
  với UNIQUE constraint;

  Nếu event đã tồn tại:
      bỏ qua hiệu ứng nghiệp vụ;

  Nếu event chưa tồn tại:
      áp dụng thay đổi lên projection theo aggregate version;

COMMIT TRANSACTION

Sau khi commit thành công:
  ack message / commit offset tương ứng.
~~~

Ví dụ Java với Spring JdbcTemplate, giả định consumer được gọi trong một transaction Spring quản lý:

~~~java
@Service
public class OrderProjectionHandler {
    private final JdbcTemplate jdbc;

    public OrderProjectionHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void onOrderCreated(OrderCreated event) {
        int accepted = jdbc.update("""
            INSERT INTO consumer_inbox (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-projection-v1",
            event.eventId()
        );

        if (accepted == 0) {
            return; // Event này đã được xử lý trong cùng consumer scope.
        }

        jdbc.update("""
            INSERT INTO order_projection (
                order_id, status, aggregate_version
            )
            VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                aggregate_version = EXCLUDED.aggregate_version
            WHERE order_projection.aggregate_version
                  < EXCLUDED.aggregate_version
            """,
            event.orderId(),
            "CREATED",
            event.aggregateVersion()
        );
    }
}
~~~

Mã trên minh họa **gắn marker và projection trong một local transaction**; còn phần nhận message, ack, mapping event, thứ tự và quyền truy cập phải được triển khai phù hợp thực tế.

Các điều kiện quan trọng:

1. **Consumer identity + event ID** tạo phạm vi dedup cụ thể.
2. Marker inbox và thay đổi projection phải commit hoặc rollback cùng nhau. Nếu đánh dấu “đã xử lý” trước khi ghi trạng thái rồi crash, event có thể mất hiệu ứng.
3. Ack/commit offset sau khi local transaction thành công. Nếu crash sau commit nhưng trước ack, event có thể đến lại; unique constraint khiến handler bỏ qua.
4. Version guard giúp event cũ không ghi đè trạng thái mới; nhưng logic xử lý sự kiện nghiệp vụ có thể cần phát hiện **khoảng trống version** thay vì chỉ so lớn hơn.
5. Nếu cần rebuild lại toàn bộ dữ liệu bằng phiên bản handler mới, không dùng marker inbox cũ để vô tình bỏ qua toàn bộ sự kiện. Dựng projection/inbox mới theo namespace mới rồi kiểm chứng.
6. Với nhiều nguồn sự kiện hoặc không có aggregateVersion, cần một chiến lược ordering cụ thể; không giả định version luôn tồn tại.

### 9.1. Giới hạn của kho dedup

Giả sử broker giữ event 30 ngày, nhưng bảng inbox xóa marker sau 2 ngày. Khi replay một event cũ 10 ngày, inbox đã quên event đó và handler có thể thực hiện tác dụng phụ lần thứ hai.

Vì vậy, **thời hạn dedup phải tương thích với cửa sổ mà event có thể xuất hiện lại và với yêu cầu nghiệp vụ**. Có domain cần giữ định danh thao tác hoặc trạng thái chống lặp lâu hơn broker retention. Không nhất thiết giữ mọi event marker vô hạn: có thể dùng business key, trạng thái cuối, snapshot, archive hoặc chính sách lưu có căn cứ. Nhưng xóa dedup marker phải là quyết định rõ ràng.

## 10. Side effect bên ngoài database cần thiết kế riêng

Một local transaction không bao trùm API gửi email, cổng thanh toán hay webhook đối tác.

### 10.1. Tránh kiểu xử lý không an toàn

~~~text
Nhận OrderPaid
  |
Gọi Email Provider: gửi mail thành công
  |
Consumer crash trước ack
  |
OrderPaid được giao lại
  |
Gọi Email Provider lần nữa -> mail trùng
~~~

Đánh dấu event đã xử lý **trước** khi gửi email cũng không giải quyết trọn vẹn: nếu crash trước khi gửi, thông báo có thể bị mất.

### 10.2. Transactional outbox và idempotent dispatch

Một thiết kế thường dùng:

1. Consumer nhận event và kiểm tra idempotency.
2. Trong transaction nội bộ, ghi thay đổi dữ liệu, inbox marker và một **notification intent** vào outbox.
3. Transaction commit; event đầu vào được ack theo quy tắc.
4. Worker gửi notification intent tới provider.
5. Khi worker bị crash/timeout, retry bằng **cùng intent ID/idempotency key** nếu provider hỗ trợ.
6. Nếu provider không cung cấp idempotency, chỉ có thể giảm rủi ro bằng trạng thái gửi, xác nhận/đối soát, quy tắc retry và hạn mức; không hứa exactly-once gửi ra ngoài.

~~~text
OrderPaid event
     |
     v
DB transaction:
  dedup event
  update domain state
  insert outbox(notificationIntentId)
     |
     v
COMMIT
     |
     v
Outbox Dispatcher --(stable request ID)--> Email Provider
~~~

**Outbox bảo đảm ý định phát đi được ghi bền vững cùng transaction**, nhưng worker có thể gửi trùng khi không biết provider đã xử lý hay chưa. Muốn một hiệu ứng bên ngoài chính xác một lần cần sự hợp tác của provider, khóa idempotency hợp lệ và/hoặc quy trình đối soát.

### 10.3. Không biến replay thành gửi lại tác dụng phụ

Trong chế độ rebuild, một handler có thể:

- Ghi dữ liệu vào projection mới nhưng **không** tạo thêm notification intent.
- Ghi intent giả lập vào bảng kiểm kê để đo tác động mà không dispatch.
- Chỉ tái phát hành những tác vụ bị thiếu, sau khi đã đối chiếu business status và dedup key.
- Có quyền cấu hình riêng cho replay, được ghi lại trong runbook và quan sát qua metrics.

Cờ **replayMode** không được truyền tùy tiện từ client bên ngoài để làm thay đổi bảo đảm nghiệp vụ. Nó là chế độ vận hành được quản lý, giới hạn quyền và phạm vi. Phải tránh một biến toàn cục có thể vô tình tắt notifications ở luồng live.

## 11. Tái dựng projection khác với tái kích hoạt workflow

Đây là khác biệt thiết kế rất quan trọng:

**Projection rebuild** đọc event lịch sử để tạo lại cách nhìn dữ liệu. Ví dụ, từ OrderCreated, OrderPaid, OrderShipped, dựng một bảng trạng thái đơn hàng hiện tại. Nếu thực hiện đúng, việc đọc lại nhiều lần có thể tạo ra cùng projection mà không gửi lệnh nghiệp vụ mới.

**Workflow re-execution** chạy lại quá trình ra quyết định và có thể phát command mới. Nếu đọc lại OrderCreated rồi tự gửi ReserveInventory lần nữa, workflow có thể khởi động lại việc giữ hàng vốn đã xảy ra.

Cần tách:

~~~text
Historical events
      |
      +--> Pure / idempotent projection rebuild --> New read model
      |
      +--> Workflow handler có side effect
                |
                +--> Chỉ chạy theo policy và trạng thái nghiệp vụ
~~~

Một event cũ không có nghĩa hành động tương ứng **nên được thực hiện lại ở hiện tại**. Những điều kiện nghiệp vụ đã thay đổi: giá, số lượng tồn, chính sách hoàn tiền, trạng thái order hoặc quyền khách hàng. Đừng áp lại luật hôm nay lên lệnh cũ mà không có kế hoạch đối soát và phiên bản quy tắc.

## 12. Định nghĩa phạm vi replay chính xác

Không nên vận hành bằng chỉ dẫn mơ hồ “replay cả topic từ đầu”. Kế hoạch cần xác định:

| Thuộc tính | Câu hỏi |
|---|---|
| **Nguồn** | Topic/partition, archive, event store hay snapshot nào? |
| **Mốc bắt đầu** | Offset, timestamp, sequence hoặc event ID nào? |
| **Mốc kết thúc** | High-watermark/snapshot cutoff nào? |
| **Consumer mục tiêu** | Chỉ projection mới hay cả nhóm live? |
| **Kiểu xử lý** | Rebuild state, retry lỗi thiếu, đối soát, hay re-execute workflow? |
| **Tác dụng phụ** | Gửi email, gọi payment, update inventory, webhook có bị cấm không? |
| **Schema** | Event cũ có tương thích với handler hiện tại không? |
| **Thứ tự** | Ordering/partition key/aggregate version có được bảo vệ không? |
| **Hiệu năng** | Throughput tối đa, throttle, rate limit và tác động tới broker? |
| **Checkpoint** | Lưu tiến độ và resume ra sao khi replay dở? |
| **Điều kiện dừng** | Trường hợp nào phải ngừng lập tức? |
| **Xác minh** | Đếm record, checksum, aggregate state, KPI nào? |

Mốc replay nên có khả năng tái lập. Timestamp có thể khó xác định chính xác khi event trễ hoặc nhiều partition; offset phải được ghi **theo từng partition**. Nếu dùng một thời điểm “đến hiện tại”, bạn cần một cutoff rõ ràng để biết lúc nào đã bắt kịp stream.

## 13. Quy trình replay an toàn từ đầu đến cuối

### Bước 1: Xác định vấn đề và phạm vi

Ví dụ: consumer Search Projection có bug làm sai trạng thái tìm kiếm của đơn hàng trong một tuần. Mục tiêu là dựng lại search index, **không** gửi email hoặc tạo lệnh fulfillment mới.

Ghi ticket, người phụ trách, phạm vi dữ liệu, phiên bản handler, window lịch sử và nguồn khôi phục. Kiểm tra có đủ event tương ứng để dựng lại không.

### Bước 2: Chọn cách phục hồi

Ưu tiên phương án ít ảnh hưởng:

- Khôi phục từ snapshot đầy đủ rồi đọc phần event tiếp theo.
- Đọc toàn bộ retained log vào projection mới.
- Dùng archive/event store khi broker retention không đủ.
- Đối soát từ nguồn dữ liệu nghiệp vụ có thẩm quyền nếu event history bị thiếu.

**Không suy đoán dữ liệu đã tồn tại trong broker chỉ vì cấu hình nói giữ bảy ngày.** Xác minh earliest/latest offset hoặc mốc sự kiện thực tế trước khi bắt đầu.

### Bước 3: Cách ly pipeline replay

Tạo consumer group riêng hoặc job rebuild riêng để tránh làm thay đổi offset của consumer live. Ghi kết quả vào **bảng/index mới**, tránh ghi đè trạng thái production đang phục vụ.

~~~text
Live consumer group   ---> Active read model

Replay consumer group ---> Shadow read model
                              |
                        Xác minh đầy đủ
                              |
                        Đổi alias/route đọc
~~~

Đối với hệ thống không thể dựng song song, phải có phương án maintenance, backup, rollback và giới hạn tác động rõ ràng trước khi reset offset hoặc xóa dữ liệu hiện hành.

### Bước 4: Bật chính sách side effect phù hợp

Replay chỉ phục vụ projection phải loại bỏ hoặc thay thế side effect ra ngoài. Nếu cần khôi phục những tác vụ thất bại, dùng danh sách operation đã được đối soát và idempotency key ổn định. Đừng chỉ dựa vào “chắc handler sẽ không gửi lại”.

### Bước 5: Ghim điểm bắt đầu, điểm kết thúc và version

Chụp cutoff theo partition (hoặc mô hình sequence tương đương), kiểm tra schema handler phù hợp với event cũ, ghi lại version code đang chạy. Nếu lượng event lớn, có thể bắt đầu từ snapshot hợp lệ rồi replay phần sau.

### Bước 6: Chạy có kiểm soát

Thực thi với giới hạn throughput, concurrency và số retry. Theo dõi consumer lag, error rate, độ trễ broker, DB load và queue depth. Hệ thống live không nên bị suy giảm đáng kể chỉ vì pipeline replay đang hút hết băng thông.

### Bước 7: Xác minh trước khi chuyển đổi

So sánh tổng số bản ghi, tổng hợp nghiệp vụ, version tối đa, số event bỏ qua, số dead-letter và checkpoint đã đến cutoff. Với projection nhạy cảm, đối soát thêm các mẫu cụ thể theo business ID.

### Bước 8: Chuyển sang trạng thái mới và theo dõi

Nếu dùng shadow projection, thực hiện cutover theo cơ chế an toàn (ví dụ đổi alias/route) và tiếp tục đọc live stream mà không bỏ sót sự kiện giữa cutoff và thời điểm đổi. Giữ khả năng rollback trong thời gian quan sát.

### Bước 9: Lưu bằng chứng

Ghi lại phạm vi, mốc offset, version consumer, số event đã đọc/được áp dụng/bỏ qua, lỗi, kết quả đối soát, người quyết định và sự cố phát sinh. Nhờ vậy lần khôi phục sau có thể lặp lại quy trình.

## 14. Kafka: replay offset có những bẫy nào?

Kafka được dùng làm ví dụ cơ chế log; hành vi chi tiết còn tùy phiên bản, thư viện và cấu hình cluster.

### 14.1. Consumer group và offset

Một consumer group đã commit offset sẽ tiếp tục từ vị trí đã lưu theo quy tắc của group. Việc đặt **auto.offset.reset=earliest** thường chỉ áp dụng khi group **không có offset hợp lệ**, không tự reset group đang chạy về đầu.

Muốn replay có kiểm soát có thể:

- Tạo consumer group mới và xác định vị trí đọc.
- Dùng API **seek** tới các offset mong muốn.
- Reset offset của một group theo quy trình vận hành phù hợp khi group đã dừng, nếu công cụ/cluster cho phép.

**Cảnh báo:** reset offset của group đang phục vụ live có thể khiến handler nhận lại nhiều event và tạo tác dụng phụ ngoài ý muốn. Lựa chọn group riêng cho rebuild thường dễ cách ly hơn.

### 14.2. Retention và earliest offset

Topic có thể còn offset 2000–9000 nhưng checkpoint của consumer là 1500. Nếu các record trước offset 2000 đã bị xóa, Kafka không thể phục hồi chúng từ chính topic. Cần archive/snapshot hoặc nguồn dữ liệu có thẩm quyền khác.

Khi retention theo size/time hoạt động đồng thời, hãy kiểm tra **earliest available offset theo partition**. Không dựa vào ngày ước lượng hoặc thông số retention duy nhất.

### 14.3. Ordering theo partition

Kafka đảm bảo thứ tự các record trong một partition theo offset. Nếu event cùng aggregate được gửi vào nhiều partition, **không có thứ tự toàn cục** để dựng trạng thái chỉ bằng cách sort offset. Dùng partition key ổn định khi cần thứ tự theo aggregate và bảo vệ version tại consumer.

Nếu replay dùng nhiều worker, đảm bảo không có hai worker ghi trạng thái của cùng aggregate theo thứ tự đảo ngược; version guard, fencing hoặc partition affinity có thể cần thiết.

### 14.4. Compaction và tombstones

Một topic compacted có thể phù hợp dựng trạng thái mới nhất theo key nhưng **không** phù hợp tái dựng mọi biến cố từng xảy ra. Tombstone có thể bị cleanup theo policy; nếu dùng snapshot quá cũ và bỏ lỡ tombstone, projection có thể hồi sinh dữ liệu đáng lẽ phải xóa.

### 14.5. “Exactly once” cần ghi rõ phạm vi

Các tính năng Kafka transactions, idempotent producer và Kafka Streams có thể cung cấp những bảo đảm xử lý cụ thể trong **phạm vi Kafka** khi cấu hình và thực hiện đúng. Chúng không tự biến lời gọi tới Email Provider, Payment Gateway hoặc một database ngoài transaction Kafka thành một hiệu ứng ngoài hệ thống chính xác một lần.

## 15. Schema evolution và replay event cũ

Một producer có thể đã đổi event schema qua nhiều phiên bản. Consumer mới đọc dữ liệu cũ cần hiểu:

- Event type/version được nhận diện bằng gì?
- Field nào từng không tồn tại hoặc có ý nghĩa khác?
- Default values cũ có hợp lệ theo nghiệp vụ hiện tại không?
- Có migration/upcaster từ v1 sang mô hình hiện hành không?
- Tên enum hoặc đơn vị tiền tệ đã thay đổi thế nào?
- Schema registry giữ đủ schema lịch sử trong thời hạn replay không?
- Consumer có xử lý event bị thiếu hoặc đến sai thứ tự không?

Ví dụ, một event cũ ghi số tiền bằng đơn vị đồng, event mới ghi đơn vị nhỏ nhất kèm currency. Nếu consumer áp cách parse của phiên bản mới lên bản cũ, projection có thể sai hệ số rất lớn. **Đừng dựa vào giá trị mặc định hiện tại để diễn giải lại lịch sử** khi hợp đồng nghiệp vụ đã thay đổi.

Có thể viết *upcaster* chuyển representation của event cũ sang dạng chung cho consumer, nhưng không nên biến đổi trái với ý nghĩa ban đầu. Giữ bản ghi gốc có kiểm soát để đối soát.

## 16. Event time, processing time và dữ liệu đến trễ

Trong replay, ba thời điểm có thể rất khác nhau:

| Thời điểm | Ý nghĩa |
|---|---|
| **occurredAt** | Khi sự kiện xảy ra theo hệ thống nguồn |
| **publishedAt** | Khi sự kiện được công bố hoặc broker nhận |
| **processedAt** | Khi consumer xử lý event |

Nếu một event đặt hàng ngày 01/11 được replay ngày 11/11, **processedAt là 11/11**, nhưng doanh thu/đơn hàng phải được tổng hợp theo **ngày nghiệp vụ phù hợp**, thường từ event time đã được xác minh. Nếu consumer dùng thời gian xử lý để cộng doanh thu hôm nay, replay sẽ làm sai báo cáo.

Với stream processing và window aggregation, cần chính sách late events, watermark, allowed lateness và window state retention. Một cửa sổ đã đóng có được cập nhật lại khi event cũ đến không? Nếu không, pipeline cần backfill riêng hoặc xây dựng lại toàn bộ window.

Không tự cho rằng event time luôn đáng tin: producer có thể sai đồng hồ, gửi trễ, hoặc có mô hình hiệu lực nghiệp vụ khác thời điểm phát. Tài liệu phải phân biệt mốc nghiệp vụ với mốc hệ thống.

## 17. Snapshot giúp khôi phục nhưng cũng tạo rủi ro

Giả sử có 100 triệu event, đọc lại tất cả mất nhiều giờ. Có thể dùng snapshot của aggregate/projection tại sequence 95 triệu, rồi áp những event sau snapshot.

~~~text
Event history: 1 ......................... 100.000.000
                            |
                        snapshot
                      seq=95.000.000
                            |
                   replay 95.000.001 ...
~~~

Snapshot phải có:

- Mốc sequence/offset hợp lệ và đủ để biết event nào đã phản ánh trong snapshot.
- Version của mô hình dữ liệu và code tạo snapshot.
- Checksum hoặc biện pháp kiểm tra tính toàn vẹn.
- Bằng chứng rằng snapshot và checkpoint nhất quán với nhau.
- Chính sách loại bỏ/tái tạo snapshot cũ.
- Xử lý tombstone và các yêu cầu xóa dữ liệu.

Nếu snapshot được chụp giữa một batch nhưng checkpoint lại chỉ đến cuối batch, replay có thể **bỏ sót** những event không thực sự nằm trong snapshot. Ngược lại, nếu checkpoint quá cũ, có thể **áp dụng trùng** sự kiện. Quy tắc tạo snapshot/checkpoint phải bảo đảm một cut nhất quán hoặc consumer idempotent đủ mạnh để chịu replay.

## 18. Xóa dữ liệu, quyền riêng tư và replay

Giữ event càng lâu càng tốt **không phải luôn đúng**. Event có thể chứa tên, email, địa chỉ, giao dịch hoặc dữ liệu cá nhân. Một hệ thống phải tuân thủ chính sách lưu trữ và quyền xóa dữ liệu được áp dụng.

Các câu hỏi thiết kế:

1. Event nào bắt buộc lưu để đối soát; event nào có thể thay bằng dữ liệu tối thiểu?
2. Dữ liệu cá nhân có thể được tách khỏi event payload, tokenize hoặc quản lý khóa mã hóa không?
3. Khi thực hiện yêu cầu xóa, archive, backup, DLQ, snapshot và hệ thống phân tích được xử lý ra sao?
4. Replay từ archive cũ có thể **tái tạo dữ liệu đã xóa** vào read model mới không?
5. Cơ chế tombstone, deletion registry hoặc denylist có được đưa vào quy trình rebuild không?
6. Ai có quyền truy cập dữ liệu lịch sử và ai được khởi chạy replay?

Đừng giả định xóa bản ghi trong database production là đủ nếu broker, archive và projection vẫn giữ bản sao. Cần kế hoạch xóa xuyên toàn vòng đời dữ liệu và kiểm thử rằng replay không hồi sinh thông tin đã bị loại bỏ.

## 19. Khi retention không đủ: kế hoạch phục hồi

Tình huống giả định:

~~~text
Broker giữ event trong khoảng 72 giờ.
Consumer Inventory Analytics ngừng hoạt động 5 ngày.
Earliest available offset đã vượt checkpoint của consumer.
~~~

Lúc này, consumer **không thể chỉ resume** để nhận toàn bộ sự kiện bị bỏ lỡ. Cần một phương án:

- Dùng archive/event store có đầy đủ event lịch sử.
- Khôi phục snapshot có mốc thời gian phù hợp, sau đó bắt kịp log còn lại.
- Đối soát và dựng lại từ cơ sở dữ liệu nghiệp vụ có thẩm quyền.
- Trường hợp không có đủ nguồn: công bố **data gap**, xác định ảnh hưởng và kế hoạch bù dữ liệu thay vì tuyên bố đã khôi phục đầy đủ.

Nếu dữ liệu cần cho thuế, hóa đơn hoặc báo cáo quan trọng, không tự điền số 0 cho những ngày mất event. Phải xác định nguồn sự thật đáng tin và đánh dấu phần dữ liệu chưa thể đối soát.

## 20. Retry lỗi tạm thời và replay lịch sử cần khác chính sách

Một message thất bại vì dependency tạm thời có thể retry với backoff và số lần giới hạn. Một message thất bại vì schema không tương thích cần sửa code/schema; retry cùng dữ liệu hàng nghìn lần chỉ tạo tải vô ích.

| Tình huống | Hướng xử lý |
|---|---|
| HTTP 503 tạm thời | Retry giới hạn, backoff có jitter |
| Rate limit 429 | Tuân theo retry-after khi có và kiểm soát tổng tải |
| Lỗi parse schema cũ | Dừng/đưa DLQ, bổ sung compatibility hoặc upcaster |
| Lỗi invariant nghiệp vụ | Cách ly và điều tra, không retry mù |
| Replay sửa projection | Đọc lại có phạm vi, tắt side effect |
| Tái gửi notification bị thiếu | Đối chiếu intent + trạng thái provider, không gửi lại hàng loạt |
| Consumer ngừng lâu hơn retention | Phục hồi từ archive/snapshot hoặc báo data gap |

Phân biệt **poison message** với **transient failure**. Một poison message có thể chặn cả partition nếu consumer không có policy xử lý; nhưng bỏ qua nó tùy tiện cũng có thể phá vỡ trạng thái. Hành vi skip, quarantine, patch và replay phải được quy định.

## 21. Kiểm thử tính an toàn của replay

Đừng chỉ kiểm thử consumer nhận được event. Hãy kiểm tra trạng thái và hiệu ứng sau khi chạy lại nhiều lần:

| Kịch bản | Hành động | Kỳ vọng |
|---|---|---|
| Redelivery sau commit | Crash sau DB commit, trước ack | Không tạo hiệu ứng nghiệp vụ lần hai |
| Retry cùng eventId | Gửi event hai lần | Inbox/unique constraint ngăn trùng |
| Replay projection toàn bộ | Dựng read model mới hai lần | Kết quả cuối giống nhau theo quy tắc |
| Event out-of-order | Gửi version 3 rồi version 2 | Không ghi đè trạng thái mới bằng cũ |
| Event bị thiếu | Bỏ version 2 rồi gửi version 3 | Phát hiện gap nếu domain yêu cầu liên tục |
| Schema cũ | Replay v1 khi consumer hiểu v2 | Upcaster/compatibility xử lý đúng |
| Replay notification | Phát lại OrderPaid | Không gửi email hàng loạt ngoài chủ đích |
| Payment timeout | Provider xử lý nhưng mất response | Không thu tiền hai lần; đối soát được |
| Inbox marker đã hết hạn | Replay event cũ | Có business safeguard, không tạo tác dụng phụ trùng |
| Replay từ archive | Archive có tombstone/xóa | Không hồi sinh dữ liệu đã xóa |
| Consumer catch-up | Đọc đến cutoff rồi tiếp tục live | Không mất event ở khoảng chuyển tiếp |
| Replay quá tải | Tăng tốc đọc lịch sử | Throttle, backpressure và guardrails hoạt động |
| Broker retention ngắn | Earliest offset vượt checkpoint | Báo thiếu dữ liệu, dùng nguồn phục hồi khác |

### 21.1. Ví dụ kiểm thử tính idempotent

Với event **OrderPaid(eventId=evt-88, orderId=ord-10)**:

1. Gửi event lần đầu; hệ thống tạo đúng một trạng thái **PAID**.
2. Gửi lại event có cùng eventId; không tạo thêm khoản thanh toán hay email.
3. Crash ngay sau local DB commit nhưng trước ack, rồi redeliver.
4. Xác minh database, outbox và trạng thái provider vẫn chỉ phản ánh **một thao tác logic**.
5. Dùng cùng business operation với eventId khác để kiểm tra tầng chống trùng bằng operation ID, không chỉ bằng event ID.

Nếu chỉ kiểm tra “handler return success”, test có thể bỏ qua lỗi side effect nghiêm trọng.

## 22. Quan sát retention và quá trình replay

Các metric và log nên có:

| Chỉ số | Ý nghĩa |
|---|---|
| Earliest/latest available offset theo partition | Đo thực tế vùng dữ liệu còn replay được |
| Consumer lag theo thời gian và số bản ghi | Phát hiện consumer bị tụt |
| Topic/storage growth và cleanup | Theo dõi retention thực, capacity và chi phí |
| Replay throughput, checkpoint, estimated backlog | Biết tiến độ và khả năng hoàn thành |
| Số event accepted/skipped/duplicated/failed | Kiểm chứng độ đầy đủ |
| DLQ volume/age và poison message count | Phát hiện lỗi không hồi phục |
| Projection mismatch / reconciliation errors | Đo tính đúng đắn của dữ liệu dựng lại |
| External side-effect calls trong replay | Phát hiện email/webhook/payment không mong muốn |
| Outbox pending age / retry count | Theo dõi lệnh gửi bên ngoài chưa hoàn tất |
| Schema upcast failures | Phát hiện event lịch sử không tương thích |
| Deleted data resurrected | Phát hiện vi phạm chính sách xóa sau rebuild |

Bổ sung runbook và cảnh báo trước khi retention bị vượt bởi consumer lag. Nếu chỉ phát hiện sau khi broker xóa dữ liệu, việc khôi phục sẽ phụ thuộc archive/snapshot.

Cẩn trọng khi đưa eventId, aggregateId và customerId làm label metric có độ phân biệt cực cao; nên ghi chúng vào log/tracing có kiểm soát, metric dùng nhãn tổng hợp ít cardinality.

## 23. Mẫu quyết định retention và replay cho một topic

~~~markdown
# Retention & Replay Contract: <topic hoặc stream>

## A. Sở hữu và mục đích
- Producer và business capability:
- Event types / schema versions:
- Consumer chính:
- Dữ liệu nhạy cảm và quyền truy cập:

## B. Retention
- Broker / cleanup policy:
- Retention theo thời gian:
- Retention theo dung lượng:
- Compaction/tombstone nếu có:
- Earliest available thực tế và cách giám sát:
- Kho archive/snapshot và thời hạn riêng:
- Cơ chế xóa dữ liệu, backup và nghĩa vụ tuân thủ:

## C. Hợp đồng sự kiện
- eventId / aggregateId / aggregateVersion:
- Partition key và ordering:
- occurredAt / publishedAt:
- Schema registry và cách đọc version cũ:

## D. Tiêu thụ
- Delivery semantics:
- Ack/checkpoint sau bước nào:
- Inbox/dedup scope và retention:
- Retry/backoff/DLQ policy:
- Tác dụng phụ và idempotency bên ngoài:

## E. Replay
- Mục đích và điều kiện kích hoạt:
- Người được phép thực hiện:
- Nguồn, phạm vi, mốc bắt đầu và cutoff:
- Consumer group / pipeline cách ly:
- Side-effect policy:
- Shadow projection và phương pháp cutover:
- Rate limit, guardrails và điều kiện dừng:
- Resume/checkpoint/rollback:
- Verification và reconciliation:

## F. Vận hành
- Dashboard, alert, runbook:
- SLA/SLO và khả năng phục hồi:
- Người chịu trách nhiệm:
- Ngày xem xét lại:
~~~

Các giá trị trong mẫu phải phản ánh **cấu hình và behavior thực tế**, không chỉ mong muốn. Nếu không có archive hoặc dedup đủ dài, ghi rõ giới hạn phục hồi để consumer không nghĩ có thể replay vô hạn.

## 24. Bài tập thực hành

Một hệ thống đặt hàng dùng Kafka, có ba consumer:

- **OrderSearch** xây dựng chỉ mục tìm kiếm.
- **CustomerEmail** gửi email mỗi khi đơn được thanh toán.
- **RevenueAnalytics** cộng doanh thu theo ngày nghiệp vụ.

Giả sử topic OrderEvents có retention theo thời gian **7 ngày**, nhưng lưu lượng cao có thể khiến giới hạn dung lượng xóa record cũ sớm hơn. OrderSearch bị lỗi logic và sai dữ liệu từ 10 ngày trước; CustomerEmail và RevenueAnalytics vẫn hoạt động bình thường. Các email đã gửi thành công không cần gửi lại.

Hãy thực hiện:

1. Giải thích vì sao chỉ đặt **auto.offset.reset=earliest** không đủ để dựng lại toàn bộ 10 ngày.
2. Chọn nguồn phục hồi phù hợp: archive, snapshot hoặc dữ liệu Order nguồn. Nêu cách xác minh không còn data gap.
3. Thiết kế replay **chỉ cho OrderSearch**, gồm consumer group, cutoff, shadow index và cutover.
4. Chỉ ra cách đảm bảo CustomerEmail không gửi trùng khi OrderEvents được đọc lại.
5. Nếu RevenueAnalytics cần rebuild, hãy giải thích khác nhau giữa **occurredAt** và **processedAt** để không ghi doanh thu ngày cũ vào ngày replay.
6. Nếu broker đã xóa tombstone về một đơn bị xóa theo chính sách, hệ thống phải xử lý gì trước khi đưa chỉ mục mới vào hoạt động?
7. Đề xuất ba metric và hai điều kiện dừng để vận hành replay an toàn.
8. Nêu cách kiểm thử redelivery sau DB commit và trước ack.

**Gợi ý hướng giải:** dùng nguồn lịch sử đủ phủ 10 ngày; dựng chỉ mục bóng với handler không gửi side effect; đánh dấu cutoff theo partition; so sánh số record, trạng thái, version và các trường hợp xóa; chuyển alias sau khi bắt kịp live. Nếu không còn nguồn tin cậy, phải ghi nhận phần dữ liệu chưa thể khôi phục thay vì tuyên bố thành công.

## 25. Checklist trước khi triển khai

- [ ] Có lý do giữ dữ liệu theo nghiệp vụ, recovery và pháp lý.
- [ ] Biết loại broker/queue và khả năng replay sau ack.
- [ ] Đã tính retention theo thời gian, dung lượng, compaction và chi phí.
- [ ] Có cảnh báo khi consumer lag đe dọa cửa sổ retention.
- [ ] Có archive/snapshot hoặc quy trình giải quyết trường hợp broker log không đủ.
- [ ] Event có identity, schema version và ordering semantics rõ.
- [ ] Consumer có idempotency và ranh giới transaction phù hợp.
- [ ] Đã xác định policy chống trùng khi replay sau khi dedup marker hết hạn.
- [ ] External side effects có outbox, idempotency hoặc cơ chế đối soát.
- [ ] Projection rebuild được tách khỏi workflow tạo lệnh nghiệp vụ.
- [ ] Replay có phạm vi, cutoff, checkpoint, throttle, guardrail và rollback.
- [ ] Sự kiện cũ và schema cũ có đường đọc tương thích.
- [ ] Có chính sách tombstone và không hồi sinh dữ liệu bị xóa.
- [ ] Có test duplicate, redelivery, out-of-order, failure và side-effect suppression.
- [ ] Có bằng chứng đối soát trước khi chuyển shadow projection sang live.

## 26. Ghi nhớ

**Retention quyết định phần lịch sử nào còn có thể đọc lại; replay quyết định phần lịch sử ấy được đọc như thế nào; reprocessing quyết định hệ thống sẽ thay đổi ra sao khi event cũ được xử lý lại.** Một broker có thể giao lại cùng message, một compacted topic có thể thiếu event cũ và một consumer có thể chạy lại side effect sau crash. Thiết kế đáng tin cậy cần kết hợp chính sách lưu phù hợp, event identity, idempotency, ownership dữ liệu, ranh giới transaction, kiểm soát side effect, archive/snapshot, quan sát và runbook replay. Mục tiêu không chỉ khôi phục dữ liệu đọc mà còn **tránh tạo lại những hành động nghiệp vụ không còn hợp lệ**.
