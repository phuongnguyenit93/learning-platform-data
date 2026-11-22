# Kích thước bản ghi và lựa chọn lưu dữ liệu lớn bên ngoài Kafka

Kafka được tối ưu cho việc truyền và lưu trữ luồng sự kiện theo các record batch. Một event thường nên mang dữ liệu cần để các dịch vụ phối hợp với nhau: định danh, loại sự kiện, thời điểm, trạng thái và những thuộc tính nghiệp vụ cần thiết. Khi event chứa cả tệp ảnh, video, PDF, bản sao dữ liệu hoặc payload hàng chục MB, chi phí truyền, sao chép, lưu trữ và xử lý sẽ tăng mạnh.

Bài học này giúp xác định khi nào nên giữ payload trong Kafka, khi nào nên nén hoặc tăng giới hạn kích thước, và khi nào nên lưu nội dung ở object storage rồi gửi tham chiếu qua Kafka theo Claim Check pattern.

## 1. Record, record batch và kích thước dữ liệu

Một Kafka record gồm key, value, timestamp và headers. Ứng dụng serialize các trường này thành dữ liệu nhị phân trước khi gửi đến broker. Producer có thể gom nhiều record của cùng partition vào một **record batch** để giảm số request và tăng hiệu quả nén.

Cần phân biệt ba khái niệm:

- **Kích thước payload:** số byte của dữ liệu nghiệp vụ trước khi serialize, ví dụ nội dung một tệp PDF.
- **Kích thước record:** kích thước sau khi serialize key, value, headers và phần metadata của record.
- **Kích thước record batch:** kích thước nhóm record được gửi/lưu cùng nhau. Giới hạn broker **message.max.bytes** và topic **max.message.bytes** áp dụng cho record batch sau nén.

Do đó, tệp gốc 900 KiB không có nghĩa Kafka record cũng chỉ 900 KiB. JSON, header, key, serializer và encoding có thể làm dữ liệu lớn hơn. Nếu chuyển byte array sang Base64 để nhúng vào JSON, kích thước phần nội dung thường tăng khoảng một phần ba trước cả khi tính overhead JSON.

Kafka cũng có giới hạn cho kích thước record sau giải nén. Trong Kafka 4.4, topic config **max.decompressed.message.bytes** giới hạn kích thước đã giải nén của một record riêng lẻ. Giới hạn này khác với **max.message.bytes**, vốn giới hạn kích thước record batch trên đường truyền sau nén.

## 2. Vì sao record lớn ảnh hưởng đến Kafka?

Kafka lưu record trong log phân vùng, sao chép dữ liệu sang replica và phục vụ các consumer đọc lại theo offset. Một record lớn vì thế có thể tạo chi phí ở nhiều nơi:

- **Producer:** phải serialize và giữ dữ liệu trong bộ đệm; request lớn làm tăng áp lực bộ nhớ và thời gian gửi.
- **Broker:** cần nhận request, xác thực batch, ghi log và phục vụ replica. Các batch lớn thường làm tăng áp lực heap và giảm số record có thể nằm trong page cache.
- **Replication:** leader phải truyền batch đến follower. Khi mạng chậm hoặc follower bị tụt lại, batch lớn làm tăng lượng dữ liệu cần sao chép và thời gian bắt kịp.
- **Consumer:** cần tải, giải nén, deserialize và xử lý payload. Consumer có thể phát nhiều fetch song song; dữ liệu sau giải nén và object trung gian cũng làm bộ nhớ thực tế lớn hơn lượng byte nhận từ broker.
- **Retention và replay:** payload lớn làm log tăng nhanh. Khi consumer cần phát lại dữ liệu, toàn bộ payload tiếp tục đi qua mạng và bộ nhớ.
- **Vận hành:** request lớn có thể chạm giới hạn của proxy, gateway, dịch vụ Kafka managed, quota hoặc hệ thống giám sát bên ngoài.

Tài liệu vận hành của Confluent khuyến nghị giữ giới hạn mặc định khoảng 1 MB trong hầu hết trường hợp. Nếu thường xuyên cần tăng giới hạn, hãy đánh giá compression, tách payload hoặc lưu payload ngoài Kafka trước khi thay đổi cấu hình. Record lớn liên tục có thể gây phân mảnh heap, làm giảm hiệu quả page cache và buộc phải điều chỉnh bộ đệm cả producer lẫn consumer.

## 3. Các giới hạn kích thước trong Kafka 4.4

Các giới hạn nằm ở nhiều thành phần. Chỉ tăng một giá trị không đảm bảo luồng dữ liệu lớn hoạt động.

| Thành phần | Cấu hình | Mặc định Kafka 4.4 | Ý nghĩa |
|---|---|---:|---|
| Broker | **message.max.bytes** | 1.048.588 byte | Kích thước record batch tối đa broker chấp nhận sau nén; là mặc định cho topic nếu topic không override |
| Topic | **max.message.bytes** | 1.048.588 byte | Giới hạn record batch của riêng topic; có thể override mặc định broker |
| Topic/broker | **max.decompressed.message.bytes** | 2.147.483.639 byte | Giới hạn kích thước đã giải nén của một record |
| Producer | **max.request.size** | 1.048.576 byte | Giới hạn request producer; đồng thời giới hạn hiệu dụng cho kích thước record batch chưa nén |
| Producer | **batch.size** | 16.384 byte | Kích thước buffer mục tiêu để gom record cùng partition; không phải giới hạn tối đa của một record |
| Producer | **buffer.memory** | 33.554.432 byte | Bộ nhớ producer dùng để đệm record chờ gửi; không phải hard limit cho toàn bộ bộ nhớ producer |
| Consumer | **max.partition.fetch.bytes** | 1.048.576 byte | Lượng dữ liệu mục tiêu tối đa trả về cho mỗi partition trong một fetch |
| Consumer | **fetch.max.bytes** | 52.428.800 byte | Lượng dữ liệu mục tiêu tối đa cho toàn bộ fetch request |
| Broker replica | **replica.fetch.max.bytes** | 1.048.576 byte | Lượng dữ liệu mục tiêu replica fetch cho mỗi partition |
| Broker replica | **replica.fetch.response.max.bytes** | 10.485.760 byte | Lượng dữ liệu mục tiêu cho toàn bộ fetch response của replica |

Các giá trị trên là mặc định được công bố trong tài liệu cấu hình Kafka 4.4. Dịch vụ managed hoặc bản phân phối khác có thể đặt giới hạn riêng; hãy kiểm tra cấu hình và quota thực tế trước khi áp dụng.

### 3.1. Các giới hạn fetch không phải lúc nào cũng là hard cap

Kafka có một ngoại lệ quan trọng để bảo đảm tiến triển: nếu record batch đầu tiên của partition không rỗng lớn hơn **max.partition.fetch.bytes** hoặc **fetch.max.bytes**, broker vẫn trả batch đó để consumer có thể đọc tiếp. Replica fetch cũng có cơ chế tương tự với batch đầu tiên.

Điều này không có nghĩa có thể bỏ qua cấu hình fetch. Khi một batch lớn được trả về, consumer vẫn phải có đủ bộ nhớ để giải nén và xử lý. Nếu một fetch đồng thời đọc nhiều partition, tổng dữ liệu và số request song song có thể làm bộ nhớ tăng đáng kể.

### 3.2. batch.size không phải giới hạn kích thước record

**batch.size** quyết định producer dành bao nhiêu byte cho việc gom các record cùng partition thành batch. Producer không cố gom những record lớn hơn giá trị này vào batch. Một record có thể lớn hơn **batch.size** nhưng vẫn được gửi nếu **max.request.size** và các giới hạn broker/topic cho phép.

Chỉ tăng **batch.size** khi có lý do muốn gom nhiều record lớn vào cùng batch và đã đo được lợi ích. Giá trị lớn hơn có thể làm producer cấp phát nhiều bộ nhớ hơn cho các partition đang hoạt động. **buffer.memory** cũng cần được cân nhắc theo số partition và số producer đồng thời.

## 4. Chọn cách xử lý payload lớn

Không có một ngưỡng byte duy nhất đúng cho mọi hệ thống. Quyết định phụ thuộc vào kích thước thực tế, tần suất gửi, khả năng nén, số consumer, yêu cầu replay và thời gian lưu trữ.

| Tình huống | Cách xử lý phù hợp | Lý do |
|---|---|---|
| Event nhỏ, có cấu trúc và được đọc thường xuyên | Lưu trực tiếp trong Kafka | Consumer có thể xử lý ngay mà không cần gọi thêm dịch vụ |
| JSON hoặc văn bản lớn nhưng có nhiều phần lặp | Nén ở producer | Giảm lượng dữ liệu truyền và ghi log |
| Payload vừa phải, hiếm khi lớn và có giới hạn rõ | Tăng giới hạn cho topic chuyên biệt, đồng bộ producer/consumer | Giữ payload trong một record, tránh logic ghép mảnh |
| Ảnh, video, PDF, bản xuất dữ liệu hoặc binary lớn | Lưu ở object storage và gửi tham chiếu trong Kafka | Kafka chỉ vận chuyển metadata; dịch vụ cần payload mới tải nội dung |
| Bắt buộc chia nội dung thành nhiều sự kiện | Event Chunking | Có thể truyền từng phần qua Kafka, nhưng ứng dụng phải quản lý và ghép các chunk |

### 4.1. Nén trước khi tăng giới hạn

Producer Kafka hỗ trợ **gzip**, **snappy**, **lz4** và **zstd**. Nén được thực hiện trên record batch; batch càng có nhiều dữ liệu tương tự nhau thì khả năng nén thường càng tốt.

Ví dụ cấu hình Java producer:

~~~java
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");
~~~

- **lz4** thường phù hợp khi ưu tiên tốc độ nén/giải nén.
- **zstd** có thể cho tỷ lệ nén tốt với dữ liệu văn bản và payload phù hợp.
- **gzip** phổ biến nhưng có thể tiêu tốn CPU nhiều hơn một số codec khác.
- **snappy** là lựa chọn khác khi cần cân bằng chi phí CPU và kích thước.

Nén không giúp nhiều với JPEG, MP4, ZIP, PDF đã nén hoặc dữ liệu mã hóa. Hãy đo tỷ lệ nén trên dữ liệu thật, đồng thời theo dõi CPU và latency. Broker có thể giữ codec do producer chọn khi topic dùng **compression.type=producer**.

### 4.2. Khi nào nên tăng giới hạn Kafka?

Có thể cân nhắc tăng giới hạn khi payload chỉ lớn hơn mặc định một mức vừa phải, kích thước có giới hạn rõ ràng, tần suất gửi không quá cao và các consumer đều có thể xử lý payload đó.

Nên tạo topic riêng cho luồng cần record lớn. Điều này giúp giữ mặc định an toàn cho các topic còn lại, đồng thời dễ đặt quota, giám sát và chính sách retention riêng. Không nên tăng giới hạn toàn cluster chỉ vì một loại event đặc biệt.

Khi tăng, cần tính cả overhead serialize, key, headers và kích thước batch. Hãy cấu hình producer, topic/broker, consumer và replica fetch theo cùng mục tiêu; kiểm tra thêm giới hạn của managed service, proxy và mạng.

### 4.3. Khi nào nên lưu payload bên ngoài Kafka?

Dùng object storage hoặc hệ thống lưu trữ phù hợp khi payload là tệp nhị phân lớn, cần lưu lâu, có thể được tải theo nhu cầu hoặc chỉ một số consumer thực sự cần nội dung.

Các lựa chọn thường gặp:

- Object storage như Amazon S3, Azure Blob Storage, Google Cloud Storage hoặc MinIO.
- Hệ thống lưu trữ tệp dùng chung như HDFS hoặc NAS trong môi trường phù hợp.
- Database hoặc kho dữ liệu chuyên dụng khi payload là dữ liệu có cấu trúc và cần truy vấn theo nghiệp vụ.

Kafka tiếp tục mang sự kiện và tham chiếu. Object store giữ bytes của tệp. Hai hệ thống có vòng đời và quyền truy cập riêng, nên ứng dụng phải quản lý tính nhất quán giữa chúng.

## 5. Claim Check pattern: lưu nội dung ngoài, gửi tham chiếu qua Kafka

Claim Check là mẫu tích hợp trong đó producer lưu payload vào một kho bên ngoài, sau đó gửi một event nhỏ chứa thông tin để consumer tìm và tải payload. Event trong Kafka có thể chứa URI hoặc các trường như bucket, object key và metadata cần thiết.

### 5.1. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Object Storage
    participant K as Kafka
    participant C as Consumer
    P->>S: Upload payload
    S-->>P: object key, version, checksum
    P->>K: Publish event chứa tham chiếu
    K-->>C: Deliver event
    C->>S: Download object theo tham chiếu
    S-->>C: Payload bytes
    C->>C: Verify checksum và xử lý
    C-->>K: Commit offset sau khi xử lý thành công
~~~

Quy trình tổng quát:

1. Producer tạo **eventId** duy nhất và một object key ổn định cho lần gửi đó.
2. Producer upload payload vào object storage. Lưu metadata như kích thước, content type, checksum và version của object.
3. Chỉ sau khi upload hoàn tất và có thể đọc được object, producer mới publish event chứa tham chiếu.
4. Kafka lưu và phân phối event nhỏ đến các consumer group.
5. Consumer dùng danh tính dịch vụ của mình để truy cập object storage, tải đúng object version và xác minh checksum.
6. Consumer xử lý payload. Chỉ commit offset sau khi đã hoàn thành hoặc đã lưu trạng thái xử lý đủ an toàn theo thiết kế của ứng dụng. Nếu tải hoặc xử lý kéo dài, cần bảo đảm consumer tiếp tục poll trong giới hạn `max.poll.interval.ms` hoặc dùng cơ chế worker/pause-resume có kiểm soát để tránh rebalance ngoài ý muốn.

### 5.2. Thiết kế event envelope

Không nên chỉ gửi một chuỗi URL không có ngữ cảnh. Hãy tạo một schema rõ ràng để consumer có thể xác thực, truy xuất và xử lý vòng đời của payload.

Ví dụ event JSON:

~~~json
{
  "eventId": "evt-8f1d2c",
  "eventType": "DocumentUploaded",
  "schemaVersion": 1,
  "occurredAt": "2026-11-20T10:15:30Z",
  "documentId": "doc-2026-001",
  "payload": {
    "store": "s3",
    "bucket": "private-documents",
    "objectKey": "tenant-42/documents/evt-8f1d2c.pdf",
    "objectVersion": "3Lg...abc",
    "contentType": "application/pdf",
    "sizeBytes": 7340032,
    "checksumAlgorithm": "SHA-256",
    "checksum": "8f434346648f6b96df89dda901c5176b..."
  }
}
~~~

Ý nghĩa các trường:

| Trường | Mục đích |
|---|---|
| **eventId** | Định danh event, hỗ trợ deduplicate và truy vết |
| **eventType**, **schemaVersion** | Xác định loại event và cách diễn giải schema |
| **documentId** | Định danh thực thể nghiệp vụ |
| **store**, **bucket**, **objectKey** | Xác định nơi lưu payload |
| **objectVersion** | Đọc đúng phiên bản object khi key có thể được ghi đè |
| **contentType** | Kiểm tra định dạng và chọn bộ xử lý |
| **sizeBytes** | Đối chiếu kích thước khi tải |
| **checksumAlgorithm**, **checksum** | Phát hiện payload bị thiếu hoặc sai lệch |

Không đặt access key, secret key, password hoặc thông tin xác thực dài hạn trong Kafka event. Thông thường, consumer dùng IAM role, workload identity hoặc credential provider riêng để truy cập object storage. Nếu cần URL ký tạm thời, nên tạo URL khi consumer chuẩn bị tải dữ liệu; URL hết hạn có thể làm hỏng khả năng replay event cũ.

### 5.3. Ví dụ tích hợp với Spring Kafka

Ví dụ sau minh họa luồng upload rồi publish. **ObjectStore** là adapter do ứng dụng triển khai cho S3, Azure Blob, GCS hoặc MinIO; **PayloadObject** chứa metadata trả về từ kho lưu trữ. Producer cần được cấu hình serializer phù hợp với event DTO.

~~~java
public record PayloadReference(
        String bucket,
        String objectKey,
        String objectVersion,
        long sizeBytes,
        String contentType,
        String sha256
) {}

public record DocumentUploadedEvent(
        String eventId,
        String documentId,
        PayloadReference payload
) {}

public void publishDocument(String documentId, byte[] bytes) throws Exception {
    String eventId = UUID.randomUUID().toString();
    String objectKey = "documents/" + eventId;

    // Adapter upload và trả về version, size, content type, checksum.
    PayloadObject stored = objectStore.put(objectKey, bytes);

    PayloadReference reference = new PayloadReference(
            stored.bucket(),
            stored.objectKey(),
            stored.version(),
            stored.sizeBytes(),
            stored.contentType(),
            stored.sha256()
    );

    DocumentUploadedEvent event =
            new DocumentUploadedEvent(eventId, documentId, reference);

    // Chờ kết quả gửi để luồng minh họa chỉ báo thành công sau ACK.
    kafkaTemplate.send("document-uploaded", documentId, event).get();
}
~~~

Đây là ví dụ minh họa thứ tự upload và publish. Trong ứng dụng production, cần xử lý timeout, retry, idempotency và trường hợp upload thành công nhưng publish thất bại. Không coi việc **send()** trả về ngay là broker đã xác nhận ghi event; phải quan sát kết quả gửi theo cơ chế của producer.

### 5.4. Quản lý lỗi giữa object storage và Kafka

Kafka transaction không tự tạo một transaction phân tán bao trùm object storage. Vì vậy, upload object và publish event có thể rơi vào trạng thái thành công một nửa.

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Upload thất bại | Event có thể trỏ đến object không tồn tại | Không publish event; trả lỗi hoặc retry upload |
| Upload thành công nhưng publish thất bại | Object không có event tham chiếu, gây tốn storage | Retry publish với cùng **eventId** và object key; có job dọn object mồ côi sau thời gian chờ |
| Publish thành công nhưng producer timeout trước khi nhận ACK | Producer không biết chắc event đã được ghi hay chưa | Retry theo event ID ổn định; consumer deduplicate theo **eventId** |
| Consumer tải object gặp lỗi mạng tạm thời | Xử lý bị gián đoạn | Retry có backoff và giới hạn số lần; không commit offset trước khi hoàn thành |
| Object không còn tồn tại hoặc checksum sai | Event không thể được xử lý đúng | Ghi lỗi có ngữ cảnh vào DLQ/quy trình điều tra; cảnh báo và khôi phục object nếu có bản sao |

Nếu metadata nghiệp vụ được lưu trong database, có thể kết hợp Transactional Outbox: upload object, ghi trạng thái nghiệp vụ và outbox event trong một transaction database, sau đó dispatcher publish outbox sang Kafka. Transactional Outbox giúp đồng bộ thay đổi database với việc phát event; nó vẫn không biến object storage thành một phần của transaction database. Cần có cơ chế retry và đối soát object mồ côi.

Dùng object key ổn định dựa trên **eventId** hoặc một định danh upload đã được cấp trước giúp retry không tạo ra nhiều object trùng. Tuy nhiên, chỉ bật idempotent producer không giải quyết toàn bộ retry ở cấp nghiệp vụ: ứng dụng vẫn cần event ID và xử lý trùng ở consumer.

## 6. Vòng đời object và Kafka event phải được đồng bộ

Kafka và object storage không tự xóa dữ liệu của nhau. Khi Kafka xóa event theo retention hoặc compaction, object được tham chiếu vẫn còn trong kho ngoài. Ngược lại, nếu object hết hạn trước khi Kafka event hết hạn, consumer replay có thể nhận được một tham chiếu không còn hợp lệ.

Hãy xác định chính sách vòng đời dựa trên các yếu tố sau:

- **Topic retention:** object phải tồn tại trong toàn bộ khoảng thời gian consumer có thể đọc event.
- **Consumer lag và replay:** cộng thêm thời gian trễ tối đa, cửa sổ phục hồi sự cố và nhu cầu chạy lại nghiệp vụ.
- **Nhiều consumer group:** không xóa object ngay sau khi một consumer xử lý xong nếu consumer group khác còn cần đọc.
- **Compacted topic:** compaction chỉ loại bỏ hoặc giữ lại record theo key trong Kafka; nó không tự xóa object được record tham chiếu. Với topic compacted, cần chính sách TTL hoặc garbage collection riêng dựa trên tham chiếu còn hiệu lực.
- **Yêu cầu pháp lý và nghiệp vụ:** một số tệp cần giữ lâu hơn event hoặc phải được xóa theo yêu cầu riêng.

Có thể đặt object TTL dài hơn topic retention cộng với khoảng đệm cho consumer lag và replay. Với compacted topic hoặc dữ liệu cần lưu lâu, không nên dùng một TTL cố định nếu nó có thể xóa object vẫn còn được event hiện hành tham chiếu. Nên có job đối soát định kỳ giữa danh sách object và các tham chiếu còn hiệu lực.

Không xóa object ngay khi consumer đầu tiên xử lý xong. Nếu cần thu hồi payload sớm, phải có quy ước ownership, theo dõi trạng thái của tất cả consumer cần thiết và giữ khả năng phục hồi theo yêu cầu nghiệp vụ.

## 7. Bảo mật khi dùng object storage

Khi Kafka event chỉ chứa tham chiếu, object storage trở thành một phần của đường xử lý dữ liệu. Cần bảo vệ cả event lẫn object:

- Dùng bucket/container private; cấp quyền đọc theo service identity và nguyên tắc least privilege.
- Mã hóa dữ liệu khi lưu trữ và khi truyền; quản lý khóa qua dịch vụ chuyên dụng.
- Phân vùng object key theo tenant hoặc miền nghiệp vụ, nhưng không xem tên key khó đoán là một cơ chế phân quyền.
- Xác minh checksum và kích thước trước khi xử lý; kiểm tra content type và định dạng thực tế khi payload đến từ người dùng.
- Không đưa credential, token hoặc URL ký tạm thời có thời hạn ngắn vào event tồn tại lâu.
- Ghi audit log cho upload, download và delete; giới hạn quyền xóa object.
- Áp dụng retention, lifecycle và quy trình xóa theo chính sách dữ liệu của hệ thống.

Nếu payload có dữ liệu cá nhân hoặc bí mật kinh doanh, hãy áp dụng phân loại dữ liệu, mã hóa và kiểm soát truy cập phù hợp cho cả Kafka topic lẫn object storage. Chuyển payload ra ngoài Kafka không làm giảm trách nhiệm bảo vệ dữ liệu.

## 8. Event Chunking: chia payload thành nhiều record

Chunking là phương án chia một payload thành nhiều phần nhỏ, gửi mỗi phần như một event riêng và ghép lại ở consumer. Mỗi chunk cần metadata để nhận diện event gốc và vị trí của nó.

Ví dụ metadata:

~~~json
{
  "eventId": "evt-8f1d2c",
  "chunkIndex": 2,
  "totalChunks": 8,
  "chunkSizeBytes": 524288,
  "checksum": "sha256:...",
  "data": "..."
}
~~~

Consumer phải lưu các chunk đã nhận, phát hiện chunk thiếu hoặc trùng, kiểm tra checksum và chỉ ghép khi đã nhận đủ các phần. Nếu cần giữ thứ tự chunk, dùng cùng Kafka key để các chunk của một payload được đưa vào cùng partition; consumer vẫn phải xử lý duplicate, retry và phục hồi khi rebalance.

Chunking làm tăng độ phức tạp của ứng dụng:

- Consumer phải giữ trạng thái cho các payload đang ghép; payload càng lớn thì bộ nhớ và thời gian chờ càng tăng.
- Một chunk bị thiếu có thể làm cả payload không hoàn chỉnh.
- Consumer có thể nhận lại chunk sau retry hoặc sau khi khôi phục offset.
- Cần timeout và chính sách dọn trạng thái của payload chưa đủ chunk.
- Phải xác định thời điểm commit offset sao cho không mất chunk khi ứng dụng gặp sự cố.

Vì vậy, chỉ dùng chunking khi có lý do kiến trúc rõ ràng, chẳng hạn không có kho lưu trữ ngoài phù hợp hoặc các phần dữ liệu cần được xử lý như stream độc lập. Với tệp lớn cần tải nguyên vẹn, Claim Check thường đơn giản hơn.

## 9. Cấu hình ví dụ khi thực sự cần record khoảng 2 MiB

Giả sử một topic chuyên biệt cần nhận record batch khoảng 2 MiB. Đây chỉ là cấu hình minh họa cho Kafka tự quản lý; hãy kiểm tra giới hạn dịch vụ managed, proxy và phiên bản client trước khi dùng. Cần chừa khoảng trống cho key, headers, serialization và batch overhead, vì kích thước payload nghiệp vụ không bằng kích thước record.

Ví dụ đặt giới hạn topic cao hơn mục tiêu payload để có khoảng đệm:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name large-events \
  --alter --add-config max.message.bytes=4194304
~~~

Producer Java:

~~~java
props.put(ProducerConfig.MAX_REQUEST_SIZE_CONFIG, 4 * 1024 * 1024);
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");

// Chỉ tăng batch.size khi muốn gom nhiều record lớn vào cùng batch
// và đã đo bộ nhớ/throughput thực tế.
~~~

Consumer Java:

~~~java
props.put(ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG, 4 * 1024 * 1024);
props.put(ConsumerConfig.FETCH_MAX_BYTES_CONFIG, 32 * 1024 * 1024);
~~~

Nếu record được nén mạnh, hãy kiểm tra cả kích thước batch sau nén và kích thước record sau giải nén. **max.decompressed.message.bytes** phải cho phép record lớn nhất mà broker cần chấp nhận. Nếu cấu hình replica fetch được tăng để phù hợp với nhiều batch lớn, hãy đánh giá **replica.fetch.max.bytes** và **replica.fetch.response.max.bytes** theo số partition, bộ nhớ và băng thông của broker.

Kiểm tra cấu hình topic sau khi cập nhật:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name large-events --describe
~~~

Các giá trị fetch lớn hơn không có nghĩa consumer sẽ luôn nhận đúng lượng dữ liệu đó. Kafka trả dữ liệu theo batch và có thể trả batch đầu tiên lớn hơn giới hạn để bảo đảm tiến triển. Hãy kiểm thử bằng record lớn nhất dự kiến, nhiều partition và nhiều consumer đồng thời.

## 10. Quy trình lựa chọn và kiểm thử

1. **Đo dữ liệu thật:** đo kích thước payload trước serialize, kích thước record sau serialize và kích thước batch sau nén ở các phân vị p50, p95, p99 và trường hợp lớn nhất.
2. **Xác định nhu cầu consumer:** tất cả consumer có cần payload không? Có cần replay lâu dài không? Có thể tải payload theo nhu cầu không?
3. **Thử nén:** chọn codec và đo CPU, latency, throughput cùng tỷ lệ giảm kích thước.
4. **Đánh giá Claim Check:** nếu dữ liệu là tệp lớn hoặc consumer chỉ cần tham chiếu, lưu payload ở object storage.
5. **Chỉ tăng giới hạn khi cần:** ưu tiên override ở topic riêng; đồng bộ producer, broker/topic, consumer và replica fetch.
6. **Kiểm thử lỗi:** thử upload thất bại, publish timeout, consumer tải object lỗi, checksum sai, object hết hạn, consumer restart và rebalance.
7. **Kiểm tra vòng đời:** replay event cũ, chạy nhiều consumer group và xác minh object vẫn tồn tại theo chính sách retention.
8. **Theo dõi production:** quan sát kích thước record, tỷ lệ lỗi gửi, latency, producer buffer, consumer lag, heap, GC, network, dung lượng log, object storage và số object mồ côi.

### Checklist trước khi triển khai

- [ ] Đã đo kích thước record sau serialize, không chỉ đo file gốc.
- [ ] Đã xác định record batch và record sau giải nén nằm trong giới hạn.
- [ ] Đã thử nén trên payload thật.
- [ ] Nếu tăng giới hạn, đã đồng bộ topic/broker, producer, consumer và replica fetch.
- [ ] Topic cần record lớn có cấu hình riêng và quota phù hợp.
- [ ] Nếu dùng Claim Check, event có event ID, object key/version, size và checksum.
- [ ] Producer xử lý được tình huống upload thành công nhưng publish thất bại.
- [ ] Consumer có quyền truy cập object storage và xử lý retry, duplicate, object không tồn tại.
- [ ] Object retention đáp ứng topic retention, consumer lag và nhu cầu replay.
- [ ] Có cơ chế dọn object mồ côi và giám sát lỗi tải payload.
- [ ] Có kiểm thử bảo mật, phân quyền và audit cho object storage.

## 11. Tài liệu tham khảo

- [Apache Kafka 4.4 – Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 – Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Confluent – Best Practices: Handling Large Message Sizes](https://docs.confluent.io/platform/current/kafka/post-deployment.html#handling-large-message-sizes)
- [Confluent – Claim Check Pattern](https://developer.confluent.io/patterns/event-processing/claim-check/)
- [Confluent – Event Chunking Pattern](https://developer.confluent.io/patterns/event-processing/event-chunking/)

Luôn kiểm tra tài liệu của đúng phiên bản Kafka và nhà cung cấp đang chạy. Giới hạn record là một phần của hợp đồng vận hành giữa producer, broker, replica và consumer; còn khi dùng Claim Check, hợp đồng đó mở rộng sang quyền truy cập và vòng đời của object storage.
