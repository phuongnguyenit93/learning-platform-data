# Kích thước payload

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua những thông tin nghiệp vụ đã được công bố. Kích thước payload ảnh hưởng trực tiếp đến thời gian serialize, dung lượng lưu trữ, băng thông, bộ nhớ consumer và khả năng phục hồi khi event được retry hoặc replay. Một event quá lớn có thể làm chậm cả luồng xử lý dù số lượng event mỗi giây không cao.

**Payload size** là lượng dữ liệu của message sau khi được biểu diễn để lưu hoặc truyền. Khi thiết kế, cần phân biệt kích thước object trong bộ nhớ, kích thước JSON hoặc binary sau serialization, kích thước message trên transport và lượng dữ liệu thực tế đi qua mạng sau compression. Các con số này không giống nhau. Giới hạn payload phải được đo ở đúng ranh giới mà hệ thống cần bảo vệ.

Mục tiêu không phải làm mọi event nhỏ nhất có thể. Payload phải đủ dữ liệu để consumer thực hiện đúng nghiệp vụ và hiểu được sự kiện tại thời điểm nó xảy ra. Thiết kế tốt cân bằng giữa tính tự chứa của event, coupling, độ trễ, chi phí lưu trữ và khả năng xử lý khi có lỗi.

## 1. Vì sao kích thước payload quan trọng?

Một event lớn tác động lên nhiều thành phần trong pipeline:

- Producer phải tạo object, serialize và có thể nén payload.
- Event Publication Registry hoặc persistence adapter có thể phải lưu nội dung event cùng metadata publication.
- Transactional outbox phải ghi payload, index và trạng thái gửi.
- Broker phải nhận, lưu, replicate, định tuyến và giao message.
- Consumer phải nhận bytes, deserialize, giữ object graph và xử lý nghiệp vụ.
- Retry, redelivery, dead-letter và replay có thể nhân số lần lưu hoặc truyền cùng một payload.

Ví dụ, một event OrderConfirmed có vài trường định danh và tổng tiền thường nhỏ. Nếu event chứa toàn bộ lịch sử đơn hàng, hàng nghìn dòng chi tiết, ảnh sản phẩm hoặc tài liệu đính kèm, mỗi lần phát event sẽ kéo theo chi phí lớn hơn ở mọi consumer.

Kích thước còn ảnh hưởng tới độ ổn định. Một consumer có thể xử lý được 500 event nhỏ mỗi giây nhưng chỉ xử lý được vài event lớn cùng lúc do giới hạn heap, CPU hoặc I/O. Khi payload tăng, garbage collection, allocation, network transfer và thời gian transaction cũng có thể tăng theo.

## 2. Phân biệt kích thước object, serialized payload và wire size

Không dùng số ký tự của một chuỗi hoặc kích thước object Java để kết luận message có nằm trong giới hạn broker hay không.

| Đại lượng | Ý nghĩa | Dùng để quyết định |
|---|---|---|
| Object footprint | Bộ nhớ object và object graph trong JVM | Heap, allocation và GC |
| Serialized size | Số byte sau serializer, thường là UTF-8 JSON hoặc binary | Payload budget, DB và broker limit |
| Envelope size | Payload cộng metadata, headers và framing theo contract | Giới hạn message ở ranh giới ứng dụng |
| Compressed size | Số byte sau compression | Băng thông và lưu trữ khi transport hỗ trợ |
| Wire size | Dữ liệu thực tế truyền trên mạng, gồm protocol framing và transport overhead | Network capacity và latency |

Với JSON, ký tự Unicode có thể chiếm nhiều hơn một byte trong UTF-8. Phương thức String.length() của Java đếm UTF-16 code units, không phải số byte được gửi. Một payload có 10.000 ký tự tiếng Việt có thể lớn hơn 10.000 byte sau UTF-8 encoding.

Hãy đo bằng chính serializer và encoding mà ứng dụng sử dụng:

~~~java
byte[] serialized = objectMapper.writeValueAsBytes(event);
int payloadBytes = serialized.length;
~~~

Đoạn code trên cho kích thước JSON bytes trước compression và transport framing. Nếu adapter thêm envelope hoặc headers vào body, hãy đo cả representation cuối cùng ở ranh giới adapter. Không dùng số byte của object trước khi serialize làm giá trị thay thế.

## 3. Đặt payload budget cho từng loại event

Payload budget là giới hạn kích thước được chấp nhận cho một event type hoặc một nhóm event. Nên có ngưỡng cảnh báo và ngưỡng từ chối rõ ràng, thay vì đợi broker hoặc database báo lỗi khi payload vượt khả năng.

Một budget nên xác định:

- Định dạng serialization và encoding, ví dụ JSON UTF-8.
- Đo body hay toàn bộ envelope.
- Kích thước tối đa tính bằng byte.
- Ngưỡng cảnh báo thấp hơn giới hạn cứng.
- Phân vị kích thước cần theo dõi như p50, p95, p99 và maximum.
- Consumer và transport nào phải tiếp nhận payload.
- Quy tắc xử lý event vượt budget.
- Phiên bản contract và owner chịu trách nhiệm khi schema tăng kích thước.

Có thể bắt đầu bằng phân loại event nhỏ, vừa và lớn, sau đó đặt số byte cụ thể theo năng lực hệ thống. Các giá trị ví dụ như 16 KiB, 64 KiB hoặc 256 KiB chỉ là điểm tham khảo để thảo luận; không phải giới hạn mặc định của Spring Modulith hay mọi broker. Giới hạn cuối cùng phải dựa trên load test, cấu hình transport, database và consumer.

Nên thiết kế theo kích thước phân vị, không chỉ theo trung bình. Nếu phần lớn event nhỏ nhưng một số event có thể chứa hàng chục megabyte, p99 và maximum mới thể hiện rủi ro bộ nhớ và timeout. Cũng cần kiểm tra trường hợp payload tăng đột ngột do một field mới hoặc một collection bất thường.

## 4. Ước lượng chi phí trên toàn pipeline

Một payload được phát một lần có thể được lưu và truyền qua nhiều bản sao. Ước lượng đơn giản cho lượng dữ liệu thô:

**Tổng byte xấp xỉ = payload bytes × số bản sao lưu × số lần truyền.**

Ví dụ, payload 200 KiB được lưu ở outbox, broker và hai consumer inbox/projection; nếu event được retry ba lần, lượng I/O có thể lớn hơn nhiều so với 200 KiB ban đầu. Broker replication, backup, index và log có thể tiếp tục nhân chi phí. Đây chỉ là mô hình ước lượng; số thực tế phụ thuộc batching, compression, deduplication và cơ chế lưu trữ.

Cần xét cả concurrency. Nếu 20 consumer cùng lúc nhận payload 1 MiB và mỗi consumer giữ nhiều message trong bộ nhớ, payload thô đã tạo ra áp lực đáng kể trước khi tính object graph sau deserialize. Khi listener xử lý chậm, message có thể nằm trong buffer lâu hơn và làm tăng heap usage.

Kích thước cũng ảnh hưởng transaction duration. Ghi payload lớn vào outbox hoặc registry trong transaction nghiệp vụ có thể tăng thời gian ghi database, WAL/redo log và replication lag. Hãy đo thời gian commit cùng kích thước row, không chỉ đo thời gian publish.

## 5. Thiết kế event chỉ chứa dữ liệu cần thiết

Nguyên tắc đầu tiên là tránh đưa toàn bộ aggregate hoặc entity persistence vào event. Hãy chọn các field consumer cần để phản ứng với sự kiện.

Ví dụ payload gọn cho OrderConfirmed:

~~~json
{
  "eventId": "d8f2e3a1-0c51-4d6a-9e77-6a1c0d0b2f11",
  "eventType": "orders.order-confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T14:30:00Z",
  "orderId": "ORD-2026-00125",
  "total": 125000,
  "currency": "VND"
}
~~~

Payload này truyền định danh, loại event, version, thời điểm và dữ liệu cần thiết. Nếu consumer cần thêm chi tiết đơn hàng, hãy cân nhắc liệu thông tin đó có phải snapshot cần thiết tại thời điểm xác nhận hay chỉ là dữ liệu có thể truy vấn từ module Order.

Data minimization giúp payload nhỏ hơn và giảm dữ liệu nhạy cảm bị sao chép. Tuy nhiên, event quá nghèo dữ liệu cũng có thể buộc consumer gọi ngược producer cho nhiều field, tạo coupling runtime và làm tăng độ trễ. Hãy quyết định theo semantics:

- Dùng snapshot khi consumer cần biết trạng thái hoặc giá trị đúng tại thời điểm event xảy ra.
- Dùng reference khi dữ liệu có thể được truy vấn sau và producer bảo đảm quyền truy cập cùng vòng đời tham chiếu.
- Dùng event riêng cho các thay đổi lớn hoặc có consumer riêng thay vì nhét nhiều mục đích vào một payload.
- Không gửi field chỉ để “phòng khi cần” nếu chưa có use case.
- Không đưa entity, lazy collection, binary attachment hoặc lịch sử không giới hạn vào payload.

## 6. Snapshot hay reference?

Đây là quyết định quan trọng khi payload có dữ liệu lớn.

**Snapshot** mang dữ liệu cần thiết tại thời điểm event phát sinh. Consumer có thể xử lý độc lập và không phải gọi lại producer. Snapshot phù hợp khi ngữ nghĩa yêu cầu dữ liệu lịch sử chính xác, ví dụ giá và địa chỉ được chốt khi đơn hàng xác nhận. Đổi lại, payload lớn hơn và dữ liệu có thể được sao chép ở nhiều nơi.

**Reference** mang định danh hoặc URI tới dữ liệu được lưu ở một nơi khác. Payload nhỏ hơn, dữ liệu lớn được phân phối bằng cơ chế phù hợp với file hoặc object storage. Consumer phải có quyền truy cập, xử lý khi reference hết hạn và hiểu dữ liệu tham chiếu có thể đã thay đổi hay không.

| Tiêu chí | Snapshot trong event | Reference tới dữ liệu |
|---|---|---|
| Tự chứa | Cao | Thấp hơn |
| Kích thước message | Có thể lớn | Thường nhỏ |
| Độc lập khi producer ngừng hoạt động | Consumer có thể xử lý ngay | Có thể cần truy cập kho ngoài |
| Ngữ nghĩa thời điểm | Ghi lại dữ liệu tại thời điểm phát | Có nguy cơ đọc trạng thái mới hơn |
| Quyền truy cập | Dữ liệu lan tới mọi consumer | Có thể kiểm soát truy cập tập trung |
| Retention/xóa | Phải xử lý mọi bản sao payload | Phải quản lý cả object và reference |

Không dùng reference nếu dữ liệu tham chiếu có thể bị thay đổi hoặc xóa trước khi consumer đọc mà không có chính sách rõ ràng. Với snapshot, chỉ giữ field cần thiết và xác định retention của bản sao. Với reference, nên dùng định danh ổn định và quyền truy cập theo consumer, không đưa credential hoặc signed URL dài hạn vào event.

## 7. Dùng object storage cho dữ liệu lớn

Với tài liệu, hình ảnh, tệp export hoặc snapshot lớn, object storage thường phù hợp hơn message broker. Event chỉ mang metadata và reference tới object.

Một envelope tham khảo:

~~~json
{
  "eventId": "8f9b3a21-7d55-4b1c-a111-223344556677",
  "eventType": "documents.export-ready",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T14:30:00Z",
  "object": {
    "bucket": "event-artifacts",
    "key": "exports/2026/11/8f9b3a21.json",
    "contentType": "application/json",
    "contentLength": 7340032,
    "sha256": "..."
  }
}
~~~

Producer nên upload object trước, xác nhận object đã sẵn sàng, sau đó commit event/reference qua outbox. Consumer kiểm tra contentLength, checksum, content type và quyền truy cập trước khi tải. Nếu upload thành công nhưng transaction event rollback, object có thể trở thành orphan; cần cleanup job dựa trên metadata và tuổi object.

Reference cần có vòng đời phù hợp với event. Không xóa object trước khi mọi consumer cần nó hoàn tất hoặc hết retention. Nếu dùng signed URL, thời hạn URL phải đủ cho retry dự kiến nhưng không quá dài; thường nên cấp quyền qua service identity hoặc tạo URL ngắn hạn theo yêu cầu consumer.

Object storage giảm kích thước message nhưng thêm một dependency và một bước đọc. Cần đo latency, throughput, lỗi truy cập, chi phí egress và hành vi khi object bị xóa hoặc không khả dụng.

## 8. Compression: giảm byte nhưng tăng CPU

Compression có thể giảm dung lượng truyền và lưu trữ, đặc biệt với JSON có nhiều tên field lặp lại hoặc văn bản dài. Tuy nhiên, compression tiêu thụ CPU và có thể tăng latency; payload đã nén hoặc mã hóa thường khó nén thêm.

Cần phân biệt:

- **Application-level compression:** producer nén body rồi đặt content-encoding hoặc metadata tương ứng; consumer phải giải nén trước deserialize.
- **Transport/batch compression:** broker client hoặc protocol nén batch/message theo cơ chế của transport.
- **Storage compression:** database hoặc object store có thể nén khi lưu, nhưng điều đó không nhất thiết giảm bytes trên mạng.

Kafka hỗ trợ compression ở producer/batch với codec phù hợp phiên bản và cấu hình. Với RabbitMQ, ứng dụng có thể nén payload trước khi publish; broker không tự động làm cho mọi body JSON nhỏ hơn theo cùng một chính sách. Hãy xác định rõ lớp nào thực hiện compression và lớp nào chịu trách nhiệm giải nén.

Không nén payload nhỏ theo mặc định nếu phần header/CPU lớn hơn lợi ích thu được. Đo cả kích thước trước và sau nén, CPU producer/consumer, p95/p99 latency và throughput. Không giải nén dữ liệu không tin cậy mà không giới hạn kích thước đầu ra, vì payload nén có thể mở rộng rất lớn (decompression bomb).

## 9. Base64, binary và nội dung đính kèm

JSON không có kiểu binary. Nếu nhúng byte[] thành Base64, kích thước biểu diễn thường tăng khoảng một phần ba so với dữ liệu nhị phân ban đầu, chưa tính JSON field name và envelope. Một file 3 MiB có thể trở thành khoảng 4 MiB trong JSON Base64.

Nếu payload chứa binary lớn, cân nhắc:

- Đưa binary vào object storage và gửi reference.
- Dùng binary serialization khi contract và hệ sinh thái consumer hỗ trợ.
- Tách metadata và nội dung thành hai kênh có định danh liên kết.
- Chỉ dùng Base64 cho dữ liệu nhỏ, có giới hạn và thực sự cần nằm trong message.

Không serialize ảnh hoặc file thành chuỗi Base64 chỉ vì JSON tiện dùng. Cũng không dùng Java native serialization làm contract tích hợp giữa các module hoặc hệ thống; nó gắn chặt với class và runtime.

## 10. Chunking và giới hạn của việc chia nhỏ message

Chia payload lớn thành nhiều chunk có thể cần thiết khi transport hoặc consumer có giới hạn kích thước. Tuy nhiên, chunking biến một event thành một quy trình nhiều message và phát sinh thêm vấn đề:

- Manifest phải mô tả tổng số chunk, thứ tự, checksum và version.
- Consumer cần lưu chunk đến trước khi đủ dữ liệu.
- Chunk có thể đến trùng, thiếu hoặc sai thứ tự.
- Retry từng chunk và retry toàn bộ artifact cần semantics rõ.
- Phải giới hạn số artifact/chunk đồng thời để bảo vệ bộ nhớ và storage.
- Cần timeout, cleanup cho artifact chưa đủ chunk và xử lý late chunk.
- Chỉ phát event “artifact ready” sau khi toàn bộ nội dung đã được kiểm tra.

Nếu dùng chunking, mỗi chunk nên có artifactId, chunkIndex, totalChunks, checksum và eventId riêng. Manifest nên có contentLength tổng, checksum toàn bộ và thời hạn. Consumer chỉ công bố artifact hoàn chỉnh sau khi xác thực mọi chunk.

Với file lớn, object storage thường đơn giản hơn việc tự xây giao thức chunking qua broker. Chỉ dùng chunking khi có yêu cầu streaming, transport hoặc xử lý phân mảnh cụ thể và đội ngũ có thể vận hành trạng thái tập hợp chunk.

## 11. Giới hạn kích thước theo broker và adapter

Không có một payload limit chung cho mọi broker. Cần kiểm tra giới hạn ở cả producer, broker, topic/queue, consumer, framework adapter và các proxy trung gian.

**RabbitMQ/AMQP.** Cần phân biệt frame size với kích thước toàn message body. Message có thể được chia qua nhiều frame; frame_max không nên bị hiểu đơn giản là giới hạn tối đa của toàn bộ payload. Kích thước lớn vẫn làm tăng memory, disk, network và thời gian delivery. Queue limits, memory/disk alarms, consumer prefetch và cấu hình client cũng ảnh hưởng tới khả năng xử lý.

**Kafka.** Cần căn chỉnh giới hạn ở producer, broker/topic và consumer. Các cấu hình liên quan có thể gồm max.request.size, message.max.bytes hoặc max.message.bytes theo broker/topic, cùng fetch.max.bytes và max.partition.fetch.bytes phía consumer. Tên và quan hệ chính xác phụ thuộc phiên bản, cấu hình topic và client. Một record có thể được đóng gói trong batch; compression không loại bỏ nhu cầu căn chỉnh giới hạn giữa các phía.

**Spring adapter.** Serializer, message converter, header mapping và framework có thể tạo thêm envelope hoặc giới hạn riêng. Hãy đo payload sau converter thực tế và kiểm tra cấu hình adapter đang chạy. Không giả định giới hạn của broker là giới hạn duy nhất.

Khi triển khai trên nhiều transport, hãy chọn budget thấp hơn giới hạn nhỏ nhất trong toàn pipeline và dành khoảng trống cho header, envelope, phiên bản mới và biến động payload.

## 12. Tác động tới Spring Modulith Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication của application event tới các transactional listeners. Với persistence adapter lưu thông tin event, kích thước event có thể ảnh hưởng dung lượng row hoặc payload được lưu, thời gian serialize/deserialize, thời gian transaction và chi phí resubmit.

Cần đánh giá:

- Event nội bộ có mang object graph lớn hoặc lazy relationship không?
- Persistence adapter lưu event theo dạng nào và giới hạn cột/kho lưu là gì?
- Publication incomplete có giữ payload lớn lâu hơn dự kiến không?
- Resubmit có phải deserialize toàn bộ object graph không?
- Nhiều listener có làm tăng số publication record và chi phí lưu trữ không?
- Cleanup publication completed có theo retention phù hợp không?

Không giả định mọi adapter persistence của Spring Modulith lưu event giống nhau. Cấu trúc lưu trữ và serializer phụ thuộc phiên bản cùng cấu hình. Hãy đo với implementation thực tế. Dù event chỉ dùng nội bộ, payload quá lớn vẫn có thể làm tăng chi phí registry và heap của ứng dụng.

Nếu nhiều module cần dữ liệu khác nhau, cân nhắc phát các event có mục đích rõ ràng hoặc dùng event reference thay vì đưa mọi dữ liệu vào một application event duy nhất. Tuy nhiên, không phân tách đến mức tạo hàng chục message nhỏ cho một thay đổi đơn giản; số lượng publication và điều phối cũng có chi phí.

## 13. Tác động tới transactional outbox và database

Outbox ghi message trong transaction cùng thay đổi nghiệp vụ. Payload lớn làm row lớn hơn, tăng I/O, WAL/redo log, replication và thời gian commit. Nếu dispatcher đọc payload lớn theo batch, nó có thể chiếm bộ nhớ và làm chậm các message nhỏ hơn.

Các biện pháp:

- Chỉ chọn các cột cần thiết khi dispatcher đọc outbox.
- Dùng batch size phù hợp với byte budget, không chỉ số dòng.
- Tránh giữ nhiều payload lớn trong bộ nhớ cùng lúc.
- Tách bảng metadata và payload nếu mô hình storage cần tối ưu.
- Lưu object reference cho artifact lớn.
- Archive hoặc purge bản ghi đã gửi theo retention.
- Theo dõi tuổi outbox pending và dung lượng payload theo event type.

Một batch gồm 100 event 1 KiB khác hoàn toàn 100 event 5 MiB. Vì vậy, giới hạn batch nên dựa trên tổng byte dự kiến hoặc kết hợp cả số record và byte. Cần kiểm tra query plan và index để cleanup không làm ảnh hưởng luồng ghi mới.

Không lưu một bản payload lớn trong cả outbox, audit table và log nếu không có lý do. Hãy xác định kho nào là nguồn lưu nội dung, kho nào chỉ giữ metadata và cách truy xuất khi điều tra.

## 14. Backpressure và bộ nhớ consumer

Consumer phải giữ message trong buffer, deserialize thành object và thực hiện nghiệp vụ. Kích thước payload có thể tăng nhiều lần trong heap do String, collection, object header, reference và object graph.

Một ước lượng ban đầu:

**Heap đang dùng cho payload ≈ số message đồng thời × kích thước object footprint trung bình.**

Không thay serialized bytes trực tiếp bằng heap footprint; hãy đo bằng profiler hoặc load test vì hệ số phụ thuộc cấu trúc object, serializer và JVM. Nếu consumer nhận 50 message lớn đồng thời, footprint có thể cao hơn nhiều lần tổng byte JSON.

Các biện pháp kiểm soát:

- Giới hạn payload bytes trước khi deserialize.
- Giới hạn concurrency và prefetch theo kích thước message cùng năng lực xử lý.
- Dùng streaming parser hoặc streaming I/O cho nội dung lớn.
- Tránh tạo nhiều bản sao byte[]/String không cần thiết.
- Giải phóng tham chiếu sau khi xử lý và tránh giữ payload trong cache lâu.
- Đặt timeout cho dependency và giới hạn số tác vụ song song.
- Theo dõi heap, allocation rate, GC pause, queue depth và processing latency.

Prefetch theo số lượng message không phải giới hạn byte. Mười message 10 KiB và mười message 10 MiB có tải bộ nhớ rất khác nhau. Nếu kích thước biến động lớn, hãy chọn prefetch bảo thủ, giới hạn payload và cân nhắc routing event lớn sang luồng xử lý riêng.

## 15. Kiểm tra kích thước trước khi publish

Producer có thể đo payload sau serialization và từ chối event vượt budget trước khi gửi tới registry/adapter hoặc broker, tùy vị trí mà ứng dụng kiểm soát được. Với event được publish vào Spring application event bus, việc chặn tại publisher hoặc một adapter chuyên biệt cần được thiết kế sao cho không làm thay đổi semantics transaction và listener.

Ví dụ kiểm tra DTO trước khi externalize:

~~~java
@Component
class EventPayloadSizer {

    private final ObjectMapper objectMapper;
    private final int maxPayloadBytes;

    EventPayloadSizer(ObjectMapper objectMapper, int maxPayloadBytes) {
        this.objectMapper = objectMapper;
        this.maxPayloadBytes = maxPayloadBytes;
    }

    byte[] serializeWithinBudget(Object event)
            throws JsonProcessingException {
        byte[] payload = objectMapper.writeValueAsBytes(event);

        if (payload.length > maxPayloadBytes) {
            throw new EventPayloadTooLargeException(
                payload.length,
                maxPayloadBytes
            );
        }

        return payload;
    }
}
~~~

Ví dụ dùng ObjectMapper để đo JSON bytes và kiểm tra giới hạn 64 KiB minh họa. Trong ứng dụng thực tế, cần dùng cùng serializer/converter với adapter để số đo khớp payload gửi đi. Không serialize lần thứ hai nếu adapter đã tạo byte[]; có thể giữ representation đã đo để tránh lặp CPU.

Khi payload vượt budget, không cắt ngắn JSON hoặc âm thầm bỏ field. Hãy từ chối rõ ràng, ghi metric và log metadata phù hợp, hoặc chuyển dữ liệu lớn sang object storage/reference theo contract. Việc từ chối phải xảy ra trước khi hệ thống ghi nhận một trạng thái publication mà không thể hoàn tất.

## 16. Versioning và kiểm soát payload tăng theo thời gian

Schema có thể lớn dần khi thêm field. Một field mới chứa danh sách hoặc nội dung tự do có thể làm payload tăng mạnh dù các field khác không đổi.

Nên quản lý:

- Payload budget theo event type và schema version.
- Thay đổi field collection có thể tăng kích thước không giới hạn.
- Giới hạn số phần tử và độ dài string.
- Default/optional field để consumer tương thích.
- Chỉ đưa snapshot mới khi có lý do nghiệp vụ.
- Kiểm thử fixture lớn nhất hợp lệ.
- Theo dõi p95/p99 sau mỗi lần phát hành schema.

Không thay đổi ý nghĩa field hoặc đơn vị dữ liệu chỉ để giảm byte. Nếu cần rút gọn tên field hoặc dùng binary format, phải cân nhắc khả năng đọc, debug và tương thích của mọi consumer.

Với event có danh sách item, đặt giới hạn số item hoặc tách sự kiện theo aggregate khi nghiệp vụ cho phép. Nếu danh sách cần đầy đủ để thể hiện một snapshot, cân nhắc reference tới artifact có checksum thay vì phát nhiều event nhỏ làm mất tính toàn vẹn snapshot.

## 17. Observability cho payload size

Không thể tối ưu nếu không biết kích thước thực tế theo event type, producer và destination. Nên thu thập histogram hoặc distribution của serialized payload bytes trước và sau compression.

Các chỉ số hữu ích:

- event.payload.bytes: kích thước serialized body.
- event.payload.compressed.bytes: kích thước sau compression nếu có.
- event.payload.serialize.duration: thời gian serialize.
- event.payload.deserialize.duration: thời gian deserialize.
- event.payload.rejected.total: số event vượt budget.
- event.payload.externalized.total: số event dùng reference/object storage.
- Outbox/registry storage bytes và tuổi publication pending.
- Consumer heap, allocation, GC, processing latency và redelivery.

Tag metrics chỉ nên dùng giá trị có cardinality thấp như eventType đã kiểm soát, adapter và destination logic. Không dùng eventId, orderId, customerId hoặc object key làm metric tag. Các định danh cụ thể thuộc log/trace và cần tuân theo chính sách dữ liệu.

Log nên ghi eventId, eventType, schemaVersion, payloadBytes, compressedBytes, destination và kết quả. Tránh ghi payload chỉ để chẩn đoán kích thước. Dashboard nên hiển thị p50/p95/p99, maximum, tỷ lệ vượt budget và xu hướng kích thước theo phiên bản schema.

## 18. Kiểm thử payload size và hành vi tải

Kiểm thử cần dùng serializer thực tế và dữ liệu đại diện, gồm cả trường hợp lớn nhất hợp lệ. Một test chỉ tạo DTO nhỏ mặc định không chứng minh payload production sẽ nằm trong budget.

Các kịch bản nên có:

1. **Serialized byte budget:** xác nhận kích thước UTF-8 sau serialization không vượt giới hạn event type.
2. **Unicode:** kiểm tra tiếng Việt, emoji và ký tự đa byte.
3. **Maximum collection:** kiểm tra số item lớn nhất hợp lệ và string dài nhất.
4. **Envelope overhead:** đo body cùng metadata/header theo contract.
5. **Compression ratio:** xác nhận kích thước trước/sau nén và CPU tiêu thụ.
6. **Oversized rejection:** payload vượt giới hạn bị từ chối rõ ràng trước khi publish.
7. **Reference availability:** consumer truy cập được object và kiểm tra checksum.
8. **Object lifecycle:** object không bị xóa trước khi consumer hoàn tất hoặc hết retention.
9. **Chunk failure:** nếu dùng chunking, kiểm tra duplicate, missing chunk, ordering và cleanup.
10. **Broker boundary:** xác nhận producer, broker/topic/queue và consumer chấp nhận cùng một budget.
11. **Registry/outbox persistence:** đo thời gian và dung lượng khi lưu publication hoặc outbox payload lớn.
12. **Concurrent consumers:** kiểm tra heap, GC, latency và throughput với payload lớn đồng thời.
13. **Retry/replay:** message lớn được gửi lại mà không làm vượt giới hạn hoặc gây memory spike.
14. **Schema regression:** payload không tăng bất thường sau thay đổi DTO.

Load test nên giữ workload và concurrency ổn định khi thay đổi một yếu tố như payload size hoặc compression. Đo throughput, p95/p99 latency, network bytes, heap, GC, database I/O và backlog. Đừng kết luận compression hoặc payload reference tốt hơn chỉ từ kích thước file; phải tính cả thời gian và lỗi của toàn pipeline.

## 19. Quy trình tối ưu kích thước payload

Khi một event gây tốn băng thông, memory hoặc storage, có thể thực hiện theo thứ tự:

1. Đo serialized bytes bằng serializer thực tế tại ranh giới publish.
2. Xác định field, collection hoặc binary nào chiếm phần lớn payload.
3. Đặt payload budget theo event type, consumer và transport.
4. Loại bỏ field không cần và giới hạn collection/string.
5. Chọn snapshot hoặc reference theo semantics thời điểm và khả năng truy cập.
6. Đưa artifact lớn sang object storage nếu phù hợp.
7. Đánh giá compression sau khi đo CPU và latency.
8. Chỉ dùng chunking khi có yêu cầu cụ thể và có manifest/recovery rõ ràng.
9. Căn chỉnh giới hạn producer, adapter, broker, queue/topic và consumer.
10. Điều chỉnh prefetch/concurrency theo byte footprint và năng lực consumer.
11. Theo dõi p95/p99, rejected payload, backlog, heap và storage.
12. Kiểm thử regression, retry, replay và trường hợp payload lớn nhất hợp lệ.

Kích thước payload là một thuộc tính của hợp đồng event và toàn bộ pipeline, không chỉ là con số cấu hình của broker. Khi đo đúng serialized bytes, đặt budget theo event type, chỉ gửi dữ liệu cần thiết và chọn snapshot/reference/compression có chủ đích, hệ thống Spring Modulith có thể giữ event đủ ý nghĩa nghiệp vụ mà vẫn kiểm soát được network, storage, heap và độ trễ. Kết hợp kiểm thử payload lớn, observability và giới hạn concurrency giúp luồng application events ổn định khi schema và tải tăng theo thời gian.

