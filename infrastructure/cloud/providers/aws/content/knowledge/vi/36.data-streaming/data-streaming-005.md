# Enhanced fan-out, ordering và dữ liệu đến muộn

Một Kinesis data stream có thể phục vụ nhiều consumer cùng lúc: ứng dụng xử lý giao dịch, fraud detection, dashboard vận hành, data lake và mô hình phân tích. Những consumer này có thể cần cùng một bản ghi nhưng có yêu cầu throughput và độ trễ khác nhau. Nếu tất cả dùng cơ chế đọc chia sẻ, chúng sẽ cạnh tranh quota đọc của từng shard. Đồng thời, khi stream có nhiều shard, thứ tự record chỉ được bảo đảm trong phạm vi nhất định; một consumer có thể nhìn thấy event theo thứ tự khác với thời điểm nghiệp vụ thực sự xảy ra.

Amazon Kinesis Data Streams cung cấp **Enhanced Fan-Out (EFO)** để cấp throughput đọc riêng cho từng consumer trên mỗi shard. Dịch vụ cũng dùng partition key và sequence number để tổ chức thứ tự record. Ở tầng xử lý, các framework như Managed Service for Apache Flink dùng event time, watermark và allowed lateness để xử lý event đến trễ hoặc không theo thứ tự thời gian.

Ba vấn đề cần phân biệt:

- **Fan-out:** nhiều consumer cùng đọc một stream mà không tranh chấp read throughput.
- **Ordering:** các record liên quan được đưa vào shard và xử lý theo thứ tự nào.
- **Late data:** event đến hệ thống sau khi thời điểm nghiệp vụ của nó đã xảy ra, hoặc đến sau khi watermark của cửa sổ đã tiến qua.

EFO không tự sắp xếp record theo event timestamp. Partition key không tạo ra thứ tự toàn cục giữa nhiều shard. Watermark cũng không làm dữ liệu đến trễ biến mất; nó giúp hệ thống quyết định khi nào có thể phát kết quả cửa sổ và cần giữ state trong bao lâu.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích Enhanced Fan-Out và phân biệt nó với shared-throughput consumer.
- Đăng ký EFO consumer, đọc bằng SubscribeToShard và hiểu vòng đời subscription.
- Chọn partition key để duy trì thứ tự cho các event cùng thực thể mà vẫn phân phối tải tốt.
- Phân biệt thứ tự trong shard, thứ tự theo partition key và event-time order.
- Giải thích ảnh hưởng của retry, PutRecords, resharding, KCL checkpoint và KPL aggregation tới ordering.
- Phân biệt processing time, ingestion/arrival time và event time.
- Dùng watermark, bounded out-of-orderness, idleness và allowed lateness để xử lý event đến muộn.
- Thiết kế side output hoặc luồng reconciliation cho event vượt quá thời gian chấp nhận.
- Theo dõi consumer lag, watermark progress, shard throughput và retention để tránh mất dữ liệu.

## 1. Bối cảnh: một stream, nhiều consumer

Kinesis Data Streams lưu record trong các shard. Producer ghi record vào stream; consumer đọc record để xử lý, enrich hoặc chuyển kết quả sang dịch vụ khác.

Một kiến trúc có thể có nhiều consumer độc lập:

~~~mermaid
flowchart LR
    P["Producers"] --> K["Kinesis Data Stream"]
    K --> C1["Consumer A: fraud"]
    K --> C2["Consumer B: analytics"]
    K --> C3["Consumer C: data lake"]
    K --> C4["Consumer D: notifications"]
    C1 --> O1["Risk decisions"]
    C2 --> O2["Metrics / aggregates"]
    C3 --> O3["Amazon S3"]
    C4 --> O4["Notification service"]
~~~

Các consumer có thể cần cùng dữ liệu nhưng không nhất thiết có cùng tốc độ xử lý. Consumer fraud cần độ trễ thấp; consumer analytics có thể cần throughput lớn; consumer data lake có thể chạy theo batch. Nếu consumer chậm, không nên để nó làm giảm khả năng đọc của các consumer khác.

Kinesis có hai mô hình đọc stream phổ biến:

- **Shared throughput:** các consumer dùng GetRecords và chia sẻ giới hạn đọc của shard.
- **Enhanced Fan-Out:** mỗi consumer đăng ký nhận một luồng dữ liệu được push riêng qua SubscribeToShard.

Với công việc xử lý độc lập từng record, Kinesis còn có queue consumer cho On-demand streams. Queue theo dõi trạng thái acknowledgement của record và phù hợp với xử lý stateless; stream consumer phù hợp hơn khi logic cần giữ state và xử lý record theo thứ tự shard.

## 2. Enhanced Fan-Out là gì?

Enhanced Fan-Out là tính năng cho phép một consumer đã đăng ký nhận throughput đọc riêng lên tới khoảng 2 MB dữ liệu mỗi giây trên mỗi shard. Throughput này không bị chia sẻ với các consumer EFO khác hoặc shared-throughput consumer.

EFO sử dụng mô hình push:

1. Đăng ký consumer vào stream.
2. Kinesis cấp ARN cho consumer.
3. Consumer gọi SubscribeToShard cho shard cần đọc.
4. Kinesis đẩy SubscribeToShardEvent qua kết nối HTTP/2.
5. Consumer xử lý record, lưu checkpoint và gia hạn subscription để tiếp tục đọc.

Một consumer EFO có thể đọc tất cả shard trong stream bằng KCL hoặc subscribe vào từng shard bằng API. EFO chỉ thay đổi cách phân phối dữ liệu và read throughput; ordering semantics của stream vẫn phụ thuộc partition key, shard và cách consumer xử lý.

### 2.1. Shared throughput và EFO

| Tiêu chí | Shared-throughput consumer | Enhanced Fan-Out consumer |
|---|---|---|
| API đọc | GetRecords | SubscribeToShard |
| Mô hình | Consumer pull dữ liệu qua HTTP | Kinesis push dữ liệu qua HTTP/2 |
| Throughput đọc | Tổng tối đa khoảng 2 MB/s mỗi shard được chia sẻ giữa các consumer đọc shard đó | Mỗi consumer có throughput riêng lên tới khoảng 2 MB/s mỗi shard |
| Độ trễ truyền record | Tài liệu AWS đưa ra mức trung bình tham khảo khoảng 200 ms với một consumer; có thể tăng khi nhiều consumer chia sẻ | Mức trung bình tham khảo khoảng 70 ms trong ví dụ AWS, ít phụ thuộc số consumer |
| Cạnh tranh quota | Có khi nhiều consumer đọc cùng shard | Giảm cạnh tranh giữa các consumer EFO |
| Chi phí | Không có khoản consumer-shard hour riêng cho shared read | Có thể phát sinh phí consumer-shard hour và data retrieval tùy capacity mode |
| Phù hợp | Một consumer hoặc ít consumer, tải đọc vừa phải | Nhiều consumer độc lập, throughput cao hoặc yêu cầu độ trễ thấp |

Các con số latency là số liệu tham khảo của AWS trong điều kiện thử nghiệm, không phải SLA hay cam kết latency cho mọi workload.

### 2.2. Giới hạn đăng ký consumer

Theo quota hiện hành:

| Capacity mode | Registered consumers tối đa trên mỗi stream |
|---|---:|
| Provisioned | 20 |
| On-demand Standard | 20 |
| On-demand Advantage | 50 |

Giới hạn 50 consumer của On-demand Advantage chỉ áp dụng tại các Region AWS hỗ trợ mức quota này; cần kiểm tra danh sách Region hiện hành trước khi thiết kế. Registered consumer limit được chia sẻ giữa enhanced fan-out consumers và queue registrations. Khi thiết kế nhiều consumer, cần kiểm tra tổng số consumer/queue đã đăng ký trên stream, không chỉ số consumer EFO đang hoạt động.

Một consumer đã đăng ký nhưng không còn dùng vẫn chiếm quota cho đến khi được deregister. Nên có quy trình quản lý vòng đời consumer và dọn các consumer thử nghiệm sau khi hoàn tất.

### 2.3. Khi nào nên dùng EFO?

EFO phù hợp khi:

- Nhiều ứng dụng cần đọc toàn bộ stream độc lập.
- Consumer có throughput cao và thường xuyên bị throttling do chia sẻ read capacity.
- Cần giảm độ trễ truyền record tới consumer.
- Consumer có tốc độ xử lý khác nhau và không muốn một consumer chậm ảnh hưởng consumer khác.
- Cần tách luồng xử lý fraud, observability, analytics và archival.

Shared throughput có thể phù hợp khi chỉ có một hoặc ít consumer, tốc độ đọc thấp và chi phí là ưu tiên lớn. EFO có thêm chi phí trong nhiều capacity mode, nên cần đo throughput, consumer count và độ trễ thực tế trước khi bật.

## 3. Đăng ký và sử dụng EFO

### 3.1. Đăng ký consumer bằng AWS CLI

Ví dụ đăng ký consumer có tên fraud-detector:

~~~bash
aws kinesis register-stream-consumer \
  --stream-arn arn:aws:kinesis:ap-southeast-1:111122223333:stream/orders \
  --consumer-name fraud-detector \
  --region ap-southeast-1
~~~

Kinesis trả về ConsumerARN. Consumer phải ở trạng thái ACTIVE trước khi gọi SubscribeToShard. Có thể dùng các lệnh sau để kiểm tra và quản lý:

~~~bash
aws kinesis describe-stream-consumer \
  --consumer-arn <CONSUMER_ARN> \
  --region ap-southeast-1

aws kinesis list-stream-consumers \
  --stream-arn <STREAM_ARN> \
  --region ap-southeast-1

aws kinesis deregister-stream-consumer \
  --consumer-arn <CONSUMER_ARN> \
  --region ap-southeast-1
~~~

Consumer ARN gắn với thời điểm đăng ký. Nếu deregister rồi tạo lại consumer cùng tên, ARN mới sẽ khác. IAM policy tham chiếu consumer ARN cần được cập nhật tương ứng.

### 3.2. SubscribeToShard và HTTP/2

SubscribeToShard thiết lập kết nối HTTP/2 giữa consumer ARN và một shard cụ thể. Kinesis gửi các SubscribeToShardEvent chứa records, continuation sequence number và thông tin child shards khi shard đã đóng.

Một subscription duy trì tối đa khoảng 5 phút. Consumer cần gọi SubscribeToShard tiếp để tiếp tục nhận dữ liệu. API giới hạn tần suất subscribe theo consumer và shard; không tạo vòng lặp gọi liên tục gây ResourceInUseException.

Khi shard đã đóng do split/merge, continuation sequence number có thể không còn giá trị tiếp tục đọc; event có thể trả về childShards để consumer khám phá shard con. Cần xử lý trường hợp này như một bước chuyển shard, không retry subscription vô hạn trên shard cũ.

Ví dụ Java với AWS SDK for Java 2.x minh họa phần đăng ký đọc một shard:

~~~java
KinesisAsyncClient client = KinesisAsyncClient.create();

SubscribeToShardRequest request = SubscribeToShardRequest.builder()
    .consumerARN(consumerArn)
    .shardId(shardId)
    .startingPosition(p -> p.type(ShardIteratorType.LATEST))
    .build();

SubscribeToShardResponseHandler handler =
    SubscribeToShardResponseHandler.builder()
        .subscriber(new SubscribeToShardResponseHandler.Visitor() {
            @Override
            public void visit(SubscribeToShardEvent event) {
                for (Record record : event.records()) {
                    processRecord(record);
                }

                // Persist progress only after the records are safely processed.
                saveCheckpoint(event.continuationSequenceNumber());
            }
        })
        .onError(error -> log.error("EFO subscription failed", error))
        .build();

client.subscribeToShard(request, handler).join();
~~~

Đây là phần khung xử lý; ứng dụng production cần triển khai retry/backoff, quản lý lifecycle client, xử lý lỗi, checkpoint bền vững và gia hạn subscription. Khi mở subscription tiếp theo, dùng continuation sequence number đã lưu cùng starting position phù hợp với semantics checkpoint của ứng dụng. Không lưu checkpoint trước khi kết quả xử lý được ghi bền vững.

### 3.3. IAM permissions

Consumer cần quyền phù hợp với stream và registered consumer. Các action thường gặp:

- kinesis:DescribeStreamSummary
- kinesis:ListShards
- kinesis:DescribeStreamConsumer
- kinesis:SubscribeToShard
- kinesis:RegisterStreamConsumer nếu consumer tự đăng ký
- kinesis:DeregisterStreamConsumer nếu ứng dụng tự quản lý vòng đời consumer

Nếu stream mã hóa bằng customer managed KMS key, producer và consumer còn cần quyền sử dụng key theo cấu hình. Dùng IAM role và least privilege; không nhúng access key dài hạn vào ứng dụng.

## 4. Chọn consumer model: stream consumer hay queue consumer?

Từ các khả năng hiện hành của Kinesis Data Streams, cần chọn consumer model theo semantics của công việc:

| Yêu cầu | Mô hình phù hợp |
|---|---|
| Tính toán stateful, cần xử lý record trong shard theo thứ tự | Stream consumer, shared hoặc EFO |
| Nhiều consumer độc lập cần throughput riêng | EFO stream consumer |
| Xử lý mỗi record độc lập, có thể scale worker và acknowledge từng record | Queue consumer |
| Cần window, aggregation, session hoặc anomaly detection | Stream consumer kết hợp Flink/KCL |
| Xử lý stateless như enrichment, gọi API, xử lý order riêng lẻ | Queue consumer có thể phù hợp |

Queue consumer theo dõi acknowledgement và có thể giao lại record chưa được acknowledge. Delivery là at-least-once; ứng dụng phải idempotent. Ordering của queue là best effort. Nếu nghiệp vụ cần xử lý tuần tự theo partition key, hãy đọc trực tiếp stream bằng stream consumer.

Không nên chuyển một luồng cần ordering sang queue chỉ để tăng số worker mà chưa kiểm tra tác động đến thứ tự và state.

## 5. Ordering trong Kinesis Data Streams

Ordering là khả năng consumer quan sát các record theo đúng trình tự mà nghiệp vụ yêu cầu. Trong Kinesis, thứ tự được tổ chức theo shard và partition key, không phải một thứ tự toàn cục trên toàn stream.

Mỗi data record có:

- Partition key do producer cung cấp trong user-managed partition-key mode.
- Shard ID do Kinesis chọn dựa trên hash range của partition key.
- Sequence number do Kinesis cấp khi ghi record.
- Payload là dữ liệu ứng dụng, Kinesis không tự diễn giải nội dung.

### 5.1. Partition key quyết định shard

Kinesis dùng MD5 hash của partition key để ánh xạ record tới hash key range của một shard. Các record có cùng partition key được định tuyến vào cùng shard trong user-managed partition-key mode.

Ví dụ với hệ thống đặt hàng:

- Partition key = orderId: các event của cùng một đơn hàng đi cùng shard.
- Partition key = customerId: các event của cùng khách hàng đi cùng shard.
- Partition key = region: có thể tạo một số ít key và gây hot shard.
- Partition key = constant: tất cả record có thể dồn về một shard, hạn chế throughput.

Chọn partition key theo thực thể cần giữ thứ tự, đồng thời phân tích cardinality và phân bố tải. Một partition key quá nóng có thể làm shard chứa key đó đạt giới hạn throughput dù các shard khác còn rảnh.

### 5.2. Phạm vi bảo đảm ordering

| Phạm vi | Ordering |
|---|---|
| Các record trong cùng shard | Consumer đọc shard theo sequence order |
| Cùng partition key ở user-managed mode | Được ánh xạ về cùng shard; phù hợp để giữ thứ tự record liên quan |
| Hai partition key khác nhau trong cùng shard | Có sequence order của shard nhưng không có quan hệ nghiệp vụ tự nhiên giữa hai key |
| Hai shard khác nhau | Không có thứ tự toàn cục giữa các record |
| Event time trong payload | Không được Kinesis tự sắp xếp theo timestamp nghiệp vụ |

Sequence number không phải global offset có thể so sánh giữa các shard. Không dùng sequence number của hai shard khác nhau để kết luận event nào xảy ra trước trong thế giới nghiệp vụ.

### 5.3. Service-managed record distribution

Kinesis hiện hỗ trợ hai record distribution strategies:

- **User-managed partition keys:** producer cung cấp partition key; Kinesis hash key để chọn shard. Dùng cho workload cần ordering giữa các record liên quan.
- **Service-managed record distribution:** Kinesis tự phân phối record đều giữa các shard; phù hợp workload stateless không yêu cầu ordering.

Service-managed distribution không cung cấp ordering guarantee. Partition key có thể bị bỏ qua khi phân phối shard; consumer cũng có thể nhận record không có partition key. Không trộn hai strategy trong cùng một stream. Nếu có cả workload cần ordering và workload không cần ordering, cân nhắc tách stream.

## 6. Bảo đảm thứ tự từ phía producer

### 6.1. PutRecord và SequenceNumberForOrdering

PutRecord gửi từng record. Khi cần bảo đảm sequence number tăng nghiêm ngặt cho cùng partition key, producer có thể gửi tuần tự và truyền sequence number của record trước vào SequenceNumberForOrdering của record kế tiếp.

~~~java
String previousSequenceNumber = null;

for (OrderEvent event : eventsForSameOrder) {
    PutRecordRequest.Builder builder = PutRecordRequest.builder()
        .streamName("orders")
        .partitionKey(event.orderId())
        .data(SdkBytes.fromUtf8String(event.toJson()));

    if (previousSequenceNumber != null) {
        builder.sequenceNumberForOrdering(previousSequenceNumber);
    }

    PutRecordResponse response = kinesisClient.putRecord(builder.build());
    previousSequenceNumber = response.sequenceNumber();
}
~~~

Đây là mẫu tuần tự cho một partition key. Trong ứng dụng concurrent, cần serialize các thao tác ghi cùng key hoặc dùng cơ chế sequencing riêng. Không dùng một biến sequence number toàn cục cho nhiều key.

SequenceNumberForOrdering không tạo thứ tự giữa các partition key khác nhau.

### 6.2. PutRecords và partial failure

PutRecords gửi nhiều record trong một request để tăng throughput. API trả kết quả tương ứng từng record; một số record có thể thành công trong khi record khác bị throttling hoặc lỗi tạm thời.

Producer cần:

1. Kiểm tra FailedRecordCount.
2. Xác định chính xác record có ErrorCode.
3. Retry chỉ các record thất bại với exponential backoff và jitter.
4. Theo dõi thứ tự nghiệp vụ của các record được retry.
5. Có idempotency key ở tầng ứng dụng để xử lý trường hợp producer không chắc request đã được ghi hay chưa.

PutRecords không có tham số SequenceNumberForOrdering. Nếu strict per-key ordering là yêu cầu bắt buộc, phải thiết kế producer tuần tự hóa ghi theo key và cơ chế retry không để record sau vượt record trước. Không giả định retry failed records trong một batch luôn bảo toàn thứ tự nghiệp vụ nếu các record sau đã được ghi thành công.

### 6.3. Hot partition key và throughput

Một shard có giới hạn capacity. Nếu quá nhiều record của cùng một partition key đi vào một shard, shard đó có thể bị nóng trong khi shard khác ít tải.

Các cách giảm hot shard:

- Chọn key có cardinality cao nhưng vẫn phản ánh thứ tự nghiệp vụ cần giữ.
- Tránh dùng một key cố định cho toàn bộ stream.
- Theo dõi IncomingBytes, IncomingRecords và throttling theo shard.
- Tách loại dữ liệu có yêu cầu ordering khác nhau sang stream riêng.
- Dùng shard split/reshard hoặc capacity mode phù hợp khi tổng tải tăng.

Không thêm random suffix vào partition key một cách tùy tiện nếu điều đó phá vỡ thứ tự cần giữ. Nếu phải chia một thực thể nóng thành nhiều partition, ứng dụng cần sequence number hoặc reorder buffer riêng để tái lập thứ tự ở downstream.

## 7. Ordering khi resharding

Resharding là thay đổi số shard bằng split hoặc merge. Sau split/merge, shard cũ trở thành parent shard ở trạng thái CLOSED; dữ liệu đã ghi trong parent vẫn có thể được đọc trong thời gian retention. Record mới được định tuyến sang child shard theo hash range.

Điều này tạo ra một rủi ro: nếu consumer đọc child shard trước khi đọc hết record còn lại trong parent shard, thứ tự của cùng partition key có thể bị đảo trong kết quả xử lý.

### 7.1. KCL xử lý parent và child shard

Kinesis Client Library (KCL) quản lý lease theo shard, phân phối shard cho worker, checkpoint tiến độ và thích ứng với split/merge. KCL bảo đảm child shard chỉ được xử lý sau khi parent shard đã được xử lý và checkpoint hoàn tất.

KCL cung cấp at-least-once processing. Sau crash/restart, một số record có thể được xử lý lại từ checkpoint gần nhất. Sink hoặc business logic phải idempotent.

### 7.2. Custom consumer cần làm gì?

Nếu tự xây consumer bằng API:

1. Theo dõi trạng thái shard và quan hệ parent/child.
2. Đọc hết record còn lại ở parent shard.
3. Xác nhận iterator/continuation báo đã hết dữ liệu parent.
4. Sau đó mới bắt đầu đọc child shard theo trình tự phù hợp.
5. Persist checkpoint và shard lineage.
6. Kiểm thử split/merge trong môi trường test.

Không giả định shard ID hoặc số shard sẽ cố định trong suốt vòng đời stream.

## 8. KPL aggregation và checkpoint

Kinesis Producer Library (KPL) có thể gom nhiều user records vào một Kinesis data record để giảm overhead và tăng hiệu quả ingest. Consumer cần de-aggregate để lấy lại các user records ban đầu.

Khi aggregation được bật:

- Nhiều user records có thể dùng chung sequence number của Kinesis record.
- KPL user record còn có subsequence number.
- Checkpoint chỉ theo sequence number có thể không đủ để chỉ ra chính xác subrecord cuối đã xử lý.
- KCL hỗ trợ de-aggregation và checkpoint theo record/subsequence.

Với KCL, ưu tiên checkpoint bằng record object nếu cần phân biệt các KPL user records. Nếu tự lưu checkpoint, phải lưu cả sequence number và subsequence number. Nếu chỉ checkpoint sequence number của batch nhưng consumer crash giữa batch, có thể phát lại hoặc bỏ sót user record tùy cách checkpoint.

Service-managed record distribution không hỗ trợ KPL aggregation; hãy kiểm tra compatibility trước khi đổi distribution strategy.

## 9. Vì sao event đến muộn?

Một record có thể đến Kinesis đúng thứ tự ingest nhưng vẫn là event đến muộn theo thời gian nghiệp vụ. Ví dụ:

- Thiết bị IoT mất mạng 10 phút rồi gửi lại dữ liệu đã buffer.
- Ứng dụng mobile gửi event sau khi thiết bị reconnect.
- Producer retry request sau timeout.
- Một shard được consumer xử lý chậm hơn các shard khác.
- Backfill hoặc replay đưa dữ liệu cũ vào stream.
- Đồng hồ thiết bị lệch hoặc timestamp được tạo ở nhiều hệ thống không đồng bộ.

Cần phân biệt ba loại thời gian:

| Loại thời gian | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm sự kiện thực sự xảy ra theo nghiệp vụ. | order_created_at hoặc sensor_timestamp. |
| Ingestion/arrival time | Thời điểm Kinesis nhận record. | ApproximateArrivalTimestamp. |
| Processing time | Thời điểm consumer xử lý record. | Thời điểm Flink/KCL chạy business logic. |

Ví dụ:

- Event xảy ra lúc 10:00:00.
- Thiết bị mất kết nối và gửi lúc 10:07:00.
- Kinesis nhận record lúc 10:07:01.
- Consumer xử lý lúc 10:07:02.

Theo event time, record thuộc cửa sổ 10:00. Theo ingestion time và processing time, nó xuất hiện vào khoảng 10:07. Nếu dashboard dùng processing time, số liệu 10:00 có thể không được điều chỉnh dù record cũ vừa tới.

Kinesis không tự sắp xếp record theo event timestamp trong payload. Ứng dụng phải quyết định timestamp nào là nguồn sự thật.

## 10. Event time và watermark trong Apache Flink

Apache Flink hỗ trợ ba khái niệm thời gian thường dùng:

- **Processing time:** thời gian trên máy xử lý khi operator nhận record.
- **Event time:** timestamp được gắn với thời điểm nghiệp vụ xảy ra.
- **Ingestion time:** thời điểm record được đưa vào pipeline hoặc nguồn tiếp nhận, tùy cấu hình.

Event-time window cần biết khi nào có thể coi dữ liệu của một khoảng thời gian đã tương đối đầy đủ. Flink dùng watermark để biểu diễn tiến độ event time.

### 10.1. Watermark là gì?

Watermark T biểu thị rằng hệ thống giả định sẽ không còn event có timestamp nhỏ hơn hoặc bằng T đến trong luồng bình thường, theo chiến lược watermark đã chọn. Watermark là một giả định vận hành, không phải bảo đảm tuyệt đối rằng event cũ không thể xuất hiện.

Với bounded out-of-orderness 30 giây, một watermark đơn giản được tính gần theo:

\[
Watermark = MaxEventTimeObserved - 30s
\]

Nếu một event có timestamp cũ hơn watermark hiện tại đến sau đó, nó được coi là late event đối với cửa sổ liên quan.

### 10.2. Watermark strategy

Một số chiến lược thường dùng:

| Chiến lược | Khi dùng |
|---|---|
| Monotonous timestamps | Event time tăng đơn điệu theo từng source/subtask. |
| Bounded out-of-orderness | Chấp nhận event có thể đến lệch tối đa một khoảng đã đo, ví dụ 30 giây hoặc 2 phút. |
| Custom watermark generator | Khi dữ liệu có quy luật riêng hoặc cần điều chỉnh theo nguồn. |
| Idleness detection | Khi một shard/partition không có event và đang giữ watermark chung lại. |

Với Kinesis, Managed Service for Apache Flink có thể dùng approximate arrival time làm timestamp mặc định từ source connector. Nếu payload chứa eventTime đáng tin cậy, cần trích xuất timestamp nghiệp vụ và áp dụng TimestampAssigner.

Ví dụ DataStream API:

~~~java
WatermarkStrategy<OrderEvent> watermarkStrategy =
    WatermarkStrategy
        .<OrderEvent>forBoundedOutOfOrderness(Duration.ofSeconds(30))
        .withTimestampAssigner(
            (event, previousTimestamp) -> event.eventTimeMillis())
        .withIdleness(Duration.ofMinutes(1));

DataStream<OrderEvent> timestamped =
    source.assignTimestampsAndWatermarks(watermarkStrategy);
~~~

Khoảng 30 giây là ví dụ. Hãy đo phân bố độ trễ event trong thực tế để chọn bound. Nếu chọn quá nhỏ, nhiều event hợp lệ bị xem là late; nếu quá lớn, window output bị trì hoãn và state cần giữ lâu hơn.

## 11. Allowed lateness và side output

Watermark quyết định khi nào window có thể phát kết quả chính. Tuy nhiên, event có thể đến sau khi watermark đã vượt qua cuối window.

Flink cung cấp allowed lateness để giữ state của window thêm một khoảng thời gian. Ví dụ, window 10:00–10:05 với allowed lateness 5 phút có thể nhận thêm event cho window đó cho tới khi watermark vượt mốc kết thúc cộng 5 phút.

Ví dụ:

~~~java
OutputTag<OrderEvent> lateOutputTag =
    new OutputTag<OrderEvent>("late-orders") {};

SingleOutputStreamOperator<OrderSummary> summaries =
    timestamped
        .keyBy(OrderEvent::customerId)
        .window(TumblingEventTimeWindows.of(Time.minutes(5)))
        .allowedLateness(Time.minutes(5))
        .sideOutputLateData(lateOutputTag)
        .aggregate(new OrderAggregate());

DataStream<OrderEvent> tooLate =
    summaries.getSideOutput(lateOutputTag);
~~~

Ví dụ minh họa cách cấu hình DataStream API; cần bổ sung aggregate function, output type và imports phù hợp với ứng dụng.

### 11.1. Late firing và kết quả được cập nhật

Nếu event đến sau watermark nhưng vẫn trong allowed lateness:

- Flink có thể thêm event vào window state.
- Window có thể phát kết quả lần nữa.
- Kết quả phát sau là phiên bản cập nhật của kết quả trước.

Do đó, downstream không nên giả định mỗi window chỉ phát một kết quả. Cần có window key, version hoặc upsert semantics để ghi đè kết quả cũ đúng cách.

### 11.2. Event vượt quá allowed lateness

Khi event đến sau thời hạn allowed lateness:

- Window state có thể đã bị xóa.
- Event không còn được nhập vào kết quả window chính.
- Nếu đã cấu hình sideOutputLateData, event bị loại khỏi window có thể được chuyển sang side output.
- Side output có thể được ghi vào S3, DLQ hoặc repair stream để điều tra và backfill.

Không nên bỏ late events một cách im lặng nếu chúng ảnh hưởng số liệu tài chính, tồn kho hoặc compliance. Cần có metric đếm late records, alert theo ngưỡng và quy trình reconciliation.

## 12. Shard idleness và watermark bị giữ lại

Flink tổng hợp watermark của các input song song theo watermark nhỏ nhất. Nếu một source subtask đang đọc shard không có event, watermark của subtask đó có thể không tiến lên. Những shard khác vẫn có dữ liệu nhưng window downstream có thể không được đóng vì watermark chung bị giữ lại.

Có thể dùng withIdleness để Flink loại input idle khỏi phép tính watermark sau một khoảng thời gian.

Tuy nhiên, cần hiểu hai giới hạn:

- withIdleness không tạo watermark mới khi shard idle; nó chỉ bỏ watermark cũ của subtask idle khỏi phép tính watermark chung.
- Nếu toàn bộ stream không có event, watermark built-in có thể không tiến lên và window cuối cùng không đóng.

Trong test với một tập event hữu hạn, cần chủ động phát watermark kết thúc hoặc dùng test harness phù hợp. Trong production, phải kiểm tra watermark progress, shard assignment và source idleness; không tăng allowed lateness để che lỗi watermark bị đứng.

Managed Service for Apache Flink cũng lưu ý rằng khi đọc nhiều shard song song, một shard có thể được xử lý nhanh hơn shard khác. Nếu các subtask phát watermark chênh lệch, event có thể bị xem là late hoặc operator phải buffer dữ liệu. Hãy kiểm tra watermark strategy, shard assigner và khả năng watermark alignment của source connector đang dùng.

## 13. Late event khác consumer lag như thế nào?

Hai vấn đề này thường bị nhầm lẫn:

| Hiện tượng | Nguyên nhân | Dấu hiệu |
|---|---|---|
| Late event theo event time | Producer gửi event cũ sau thời điểm nghiệp vụ; timestamp trong payload nhỏ hơn watermark | Event time thấp nhưng arrival/processing time mới |
| Consumer lag | Consumer xử lý chậm hơn tốc độ ghi vào stream | Iterator age hoặc MillisBehindLatest tăng |
| Watermark stall | Một input/shard idle hoặc subtask không phát watermark | Window không đóng dù các shard khác vẫn có dữ liệu |
| Out-of-order arrival | Producer concurrency, retry, shard interleaving hoặc replay | Sequence order và event-time order khác nhau |

Nếu consumer lag tăng, trước tiên xử lý throughput, throttling, backpressure và dependency. Nếu event time cũ đến muộn nhưng consumer vẫn caught up, hãy xử lý bằng watermark/allowed lateness và reconciliation.

## 14. Retention và replay để phục hồi dữ liệu

Kinesis Data Streams lưu record tạm thời theo retention period:

- Mặc định: 24 giờ.
- Có thể tăng tối đa 365 ngày.
- Extended/long-term retention có thể phát sinh chi phí bổ sung.
- Khi giảm retention, record cũ hơn mốc mới có thể trở nên không truy cập được gần như ngay lập tức.

Retention là cửa sổ thời gian để consumer khôi phục sau lỗi. Nó không phải backup lâu dài. Nếu consumer bị dừng lâu hơn retention, record cũ sẽ hết hạn và không thể replay từ stream.

Các starting position thường dùng:

| Starting position | Mục đích |
|---|---|
| LATEST | Chỉ đọc record mới sau thời điểm consumer bắt đầu. |
| TRIM_HORIZON | Đọc record cũ nhất còn nằm trong retention. |
| AT_TIMESTAMP | Bắt đầu đọc từ timestamp được chỉ định. |
| AT_SEQUENCE_NUMBER / AFTER_SEQUENCE_NUMBER | Tiếp tục theo sequence number đã checkpoint. |

Với late-event repair, có thể replay một khoảng thời gian từ Kinesis nếu record còn trong retention, hoặc lấy raw event từ S3/data lake nếu tổ chức đã lưu trữ lâu dài.

Không giảm retention khi consumer đang lag mà chưa đánh giá nguy cơ mất dữ liệu. Theo dõi iterator age và tăng retention tạm thời khi cần thêm thời gian khôi phục, nhưng vẫn phải xử lý nguyên nhân consumer chậm.

## 15. Theo dõi EFO, ordering và late data

Một dashboard vận hành nên kết hợp metric từ Kinesis, KCL và Managed Service for Apache Flink.

| Metric / tín hiệu | Ý nghĩa | Hành động khi tăng bất thường |
|---|---|---|
| SubscribeToShardEvent.MillisBehindLatest | Consumer EFO chậm bao nhiêu so với đầu stream | Kiểm tra throughput, xử lý record, downstream dependency và backpressure |
| SubscribeToShard.Success | Subscription EFO có được thiết lập thành công | Kiểm tra consumer ARN, IAM và chu kỳ renew |
| SubscribeToShard.RateExceeded | Subscription bị gọi vượt quota hoặc đang có subscription | Điều chỉnh retry/renew loop và concurrency |
| GetRecords.IteratorAgeMilliseconds | Độ tuổi record cuối consumer đọc được | Cảnh báo trước khi record hết retention |
| ReadProvisionedThroughputExceeded | Consumer shared bị throttling đọc | Giảm số consumer chia sẻ, tối ưu polling hoặc cân nhắc EFO |
| WriteProvisionedThroughputExceeded | Producer bị throttling ghi | Kiểm tra hot shard, partition key và capacity |
| IncomingBytes / IncomingRecords | Tốc độ ingest vào stream | So sánh với capacity và baseline |
| OutgoingBytes / OutgoingRecords | Lưu lượng đọc ra | Xác định shard/consumer có tải bất thường |
| KCL lease/checkpoint metrics | Worker, shard ownership và checkpoint | Kiểm tra worker failure, lease contention và checkpoint delay |
| Flink currentInputWatermark | Watermark hiện tại ở operator | Xác định shard idle, skew hoặc watermark strategy sai |
| Custom late-event counter / side-output count | Số event bị loại hoặc chuyển sang luồng xử lý trễ | Điều chỉnh lateness, nguồn timestamp hoặc repair process |
| Flink backPressure / busyTime | Operator bị nghẽn | Tối ưu CPU, parallelism, serialization và sink throughput |

### 15.1. Cảnh báo retention

Dùng GetRecords.IteratorAgeMilliseconds cho shared consumer và SubscribeToShardEvent.MillisBehindLatest cho EFO. Đặt cảnh báo đủ sớm so với retention period. Nếu iterator age vượt khoảng 50% retention, nguy cơ record hết hạn tăng và cần xử lý ngay.

Không chỉ dùng Average. Một shard nóng hoặc một consumer cụ thể có thể lag trong khi metric trung bình toàn stream vẫn thấp. Dùng maximum hoặc shard/consumer-level metrics khi cần điều tra.

Enhanced shard-level monitoring có thể phát sinh chi phí CloudWatch bổ sung. Bật đúng những metric cần thiết cho troubleshooting và capacity planning.

## 16. Thiết kế ví dụ: order events và fraud analytics

Một hệ thống thương mại điện tử phát các event:

- OrderCreated
- PaymentAuthorized
- InventoryReserved
- OrderShipped
- OrderCancelled

Mỗi event có orderId, customerId, eventType, eventTime, producerId và eventVersion.

### 16.1. Partition key

Chọn orderId làm partition key để các event cùng đơn hàng được đưa về cùng shard. Consumer có thể kiểm tra eventVersion hoặc sequence nghiệp vụ để phát hiện event bị lặp hoặc sai thứ tự.

Không dùng customerId nếu một khách hàng có lượng event quá lớn gây hot key. Nếu business yêu cầu ordering theo customer thay vì order, phải xác định rõ mức throughput và trade-off.

### 16.2. EFO consumers

Đăng ký các consumer độc lập:

- Fraud detector: cần đọc nhanh để đánh giá giao dịch.
- Real-time analytics: tính doanh thu và funnel.
- Data lake writer: lưu raw event để replay.
- Customer notification: gửi email/SMS sau khi order state phù hợp.

EFO cho phép các consumer có throughput đọc riêng. Mỗi consumer vẫn cần xử lý lỗi và checkpoint độc lập.

### 16.3. Event-time analytics

Giả sử ứng dụng cần tính số đơn theo cửa sổ 5 phút dựa trên eventTime. Producer có thể gửi event sau 2 phút do thiết bị hoặc network delay.

Một watermark bound 30 giây có thể không đủ nếu dữ liệu thực tế thường trễ 2 phút. Nhóm cần đo latency distribution và chọn bounded out-of-orderness phù hợp, ví dụ 3 phút, cùng allowed lateness 5 phút.

Event đến trong allowed lateness cập nhật lại kết quả window. Event vượt quá thời hạn được đưa sang late-event stream và chạy reconciliation để sửa aggregate nếu cần.

### 16.4. Correctness

- Dùng idempotency key theo eventId.
- Dùng orderId + eventVersion để phát hiện event trùng hoặc cũ.
- Không phát notification hai lần khi Flink window late-fires.
- Dùng upsert sink hoặc lưu window version.
- Lưu raw event ở S3 để backfill.
- Theo dõi late-event rate và consumer lag riêng biệt.

## 17. Chi phí và lựa chọn kiến trúc

Chi phí EFO phụ thuộc capacity mode và pricing tại Region. Với Provisioned và On-demand Standard, EFO có thể có consumer-shard hour và data retrieval charge. Consumer-shard hours phụ thuộc số shard nhân với số consumer EFO và thời gian đăng ký.

On-demand Advantage có mô hình giá khác; tài liệu pricing hiện hành nêu không có khoản phí EFO riêng ngoài chi phí data read theo mô hình đó. Đổi lại, mode này áp dụng mức tối thiểu 25 MB/s ingest và 25 MB/s retrieval cộng gộp cho các On-demand streams trong Region; nếu usage thấp hơn, có thể phát sinh khoản shortfall theo pricing. Cần tính tổng ingest, retrieval, retention và các stream khác trước khi bật.

Các yếu tố cần đưa vào cost model:

- Số shard trung bình và peak.
- Số EFO consumers đăng ký.
- GB dữ liệu mỗi consumer đọc.
- Consumer-shard hours.
- Retention vượt 24 giờ.
- Enhanced CloudWatch metrics.
- KCL worker và DynamoDB lease/checkpoint tables.
- Managed Service for Apache Flink compute, snapshots, storage và log ingestion.

EFO không giảm lượng dữ liệu mà mỗi consumer phải xử lý. Nếu có 5 consumer đọc toàn bộ stream, tổng data retrieval có thể gần gấp 5 lần lượng ingest (tùy record/filtering). Chỉ bật EFO cho consumer có nhu cầu throughput/latency rõ ràng.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer EFO nhận ResourceNotFound hoặc ResourceInUse | Consumer chưa ACTIVE, ARN sai hoặc subscription đang mở | Describe consumer, kiểm tra trạng thái và renew đúng chu kỳ |
| SubscribeToShard bị RateExceeded | Gọi API quá thường xuyên hoặc trùng subscription | Giới hạn một subscription đang hoạt động cho consumer/shard và backoff |
| Consumer EFO lag tăng | Xử lý record chậm, downstream nghẽn hoặc shard quá nóng | Kiểm tra MillisBehindLatest, processing time và sink |
| Shared consumer bị throttling | Nhiều consumer chia sẻ read throughput | Giảm số consumer hoặc chuyển consumer cần hiệu năng sang EFO |
| Record cùng entity sai thứ tự | Partition key không phản ánh entity hoặc producer retry song song | Dùng stable key, serialize write theo key và kiểm soát retry |
| Hot shard | Partition key cardinality thấp hoặc một key quá nóng | Đổi key strategy, tách workload hoặc reshard |
| Ordering bị lỗi sau reshard | Custom consumer đọc child trước khi drain parent | Xử lý parent-child lineage hoặc dùng KCL |
| Duplicate records sau restart | KCL at-least-once/checkpoint sau khi sink commit chưa đúng | Idempotent sink và checkpoint sau durable write |
| KPL record bị lặp hoặc bỏ sót khi restart | Checkpoint chỉ lưu sequence number, bỏ subsequence | Dùng KCL checkpoint(record) hoặc lưu sequence + subsequence |
| Window Flink không đóng | Watermark bị giữ bởi shard idle hoặc không có event mới | Kiểm tra currentInputWatermark, withIdleness và bounded test completion |
| Late records bị drop | Watermark bound hoặc allowed lateness quá ngắn | Đo event-time lag, tăng bound/lateness hoặc dùng side output |
| Window output xuất hiện nhiều lần | Late firing cập nhật window | Dùng upsert/versioning và deduplicate output |
| Replay không tìm thấy record | Record đã vượt retention | Lấy raw data từ S3/archive hoặc nguồn lưu trữ dài hạn |

## 19. Bài thực hành: EFO và late event

Mục tiêu: thiết kế stream order-events với hai consumer độc lập, giữ ordering theo orderId và xử lý event đến muộn bằng event-time window.

### Bước 1: Thiết kế dữ liệu

Tạo schema event gồm:

- eventId: định danh duy nhất.
- orderId: partition key.
- eventVersion: số thứ tự nghiệp vụ của order.
- eventTime: thời điểm event xảy ra.
- eventType: loại sự kiện.
- payload: dữ liệu nghiệp vụ.

### Bước 2: Tạo stream và đăng ký consumer

Tạo Kinesis Data Stream tại Region phù hợp. Đăng ký consumer fraud và analytics bằng RegisterStreamConsumer. Đợi cả hai consumer ở trạng thái ACTIVE.

### Bước 3: Ghi record

Producer ghi event theo partition key orderId. Với luồng cần strict order, serialize các PutRecord cho cùng orderId và dùng SequenceNumberForOrdering. Với PutRecords, kiểm tra từng record result và thiết kế retry để không làm đảo thứ tự nghiệp vụ.

### Bước 4: Subscribe và xử lý

Dùng SubscribeToShard hoặc KCL. Xác nhận mỗi consumer đọc được dữ liệu độc lập. Lưu checkpoint sau khi output đã được ghi bền vững; đảm bảo xử lý idempotent.

### Bước 5: Kiểm thử late events

Gửi event có eventTime 10:00 nhưng arrival time 10:02. Gửi thêm event có eventTime 10:01 nhưng arrival time 10:04. Kiểm tra window 5 phút, watermark bound và allowed lateness.

### Bước 6: Kiểm thử event vượt lateness

Gửi event thuộc window 10:00 sau khi watermark đã vượt end + allowed lateness. Xác minh event đi vào side output và được ghi vào S3/repair stream.

### Bước 7: Kiểm thử failure

- Dừng consumer rồi khởi động lại từ checkpoint.
- Tạo duplicate eventId.
- Tăng tải một partition key để quan sát hot shard.
- Split shard trong môi trường test và xác minh parent/child ordering.
- Làm chậm sink để quan sát consumer lag.
- Cho một shard idle để kiểm tra watermark progress.

### Bước 8: Đánh giá kết quả

So sánh latency, consumer lag, late-event rate, dropped late records, duplicate rate, EFO cost và correctness của aggregate. Ghi lại partition key strategy, watermark bound và allowed lateness trong ADR.

## 20. Những hiểu lầm cần tránh

1. **EFO sắp xếp record theo event time.** EFO chỉ thay đổi delivery model và throughput; event-time logic do ứng dụng xử lý.
2. **EFO tạo thứ tự toàn cục.** Ordering không được bảo đảm giữa các shard.
3. **Cùng một stream nghĩa là mọi consumer chia sẻ throughput.** EFO cấp throughput riêng cho consumer đã đăng ký.
4. **Tăng số consumer luôn cần EFO.** Shared throughput vẫn phù hợp khi ít consumer và tải thấp.
5. **Partition key càng ít càng tốt.** Cardinality thấp có thể gây hot shard.
6. **Sequence number là global offset.** Sequence number gắn với shard và partition key, không thể so sánh toàn stream.
7. **PutRecords luôn giữ thứ tự sau retry.** Partial failure và retry cần được xử lý theo từng record và nghiệp vụ.
8. **Resharding không ảnh hưởng ordering.** Custom consumer phải xử lý parent-child shard lineage.
9. **KCL đảm bảo exactly-once.** KCL cung cấp at-least-once; sink cần idempotency.
10. **Kinesis arrival timestamp là event time.** Event time phải lấy từ payload nếu muốn phản ánh thời điểm nghiệp vụ.
11. **Watermark bảo đảm không còn event cũ.** Watermark là giả định tiến độ, event muộn vẫn có thể xuất hiện.
12. **Allowed lateness giữ event mãi mãi.** State window chỉ được giữ đến thời hạn lateness.
13. **Late firing chỉ phát một kết quả.** Window có thể phát kết quả cập nhật nhiều lần.
14. **withIdleness tự tạo watermark khi stream không có dữ liệu.** Nó chỉ loại input idle khỏi phép tính watermark.
15. **Tăng retention giải quyết mọi consumer lag.** Retention chỉ kéo dài thời gian replay; vẫn phải xử lý bottleneck.
16. **Queue consumer bảo toàn ordering như stream consumer.** Queue phù hợp xử lý stateless; ordering là best effort.

## 21. Câu hỏi tự kiểm tra

**1. Enhanced Fan-Out giải quyết vấn đề gì?**

Cấp read throughput riêng cho mỗi consumer EFO trên mỗi shard và dùng push qua HTTP/2 để giảm cạnh tranh đọc.

**2. EFO có throughput bao nhiêu trên mỗi shard?**

Tối đa khoảng 2 MB/s cho mỗi consumer trên mỗi shard.

**3. Shared throughput khác EFO thế nào?**

Shared consumer chia sẻ tổng read capacity của shard; EFO consumer có throughput riêng.

**4. Một partition key dùng để làm gì?**

Định tuyến record vào shard bằng hash và gom các record liên quan về cùng shard.

**5. Kinesis có bảo đảm thứ tự giữa hai shard không?**

Không. Không có thứ tự toàn cục giữa các shard.

**6. SequenceNumberForOrdering có phạm vi nào?**

Nó giúp bảo đảm sequence tăng nghiêm ngặt cho cùng partition key khi producer ghi tuần tự bằng PutRecord; không tạo thứ tự giữa nhiều partition key.

**7. Vì sao PutRecords cần kiểm tra từng record?**

Một batch có thể có record thành công và record thất bại; producer phải retry đúng các record lỗi và bảo toàn nghiệp vụ.

**8. KCL xử lý resharding như thế nào?**

KCL theo dõi lease và shard lineage, xử lý parent shard trước child shard và checkpoint tiến độ.

**9. Vì sao KCL có thể xử lý lại record?**

KCL cung cấp at-least-once; crash xảy ra sau khi sink commit nhưng trước checkpoint có thể khiến record được phát lại.

**10. Event time khác arrival time thế nào?**

Event time là thời điểm nghiệp vụ xảy ra; arrival time là lúc Kinesis nhận record.

**11. Watermark có nghĩa gì?**

Watermark biểu thị tiến độ event time mà hệ thống giả định dữ liệu cũ hơn sẽ không còn đến trong luồng bình thường.

**12. Bounded out-of-orderness 30 giây làm gì?**

Tạo watermark lùi lại khoảng 30 giây so với event time lớn nhất đã quan sát để chấp nhận một mức đảo thứ tự hữu hạn.

**13. Allowed lateness có tác dụng gì?**

Giữ state window thêm một khoảng sau khi watermark qua cuối window để nhận event đến trễ.

**14. Vì sao late firing cần upsert hoặc dedup?**

Một window có thể phát lại kết quả đã cập nhật sau khi nhận late event.

**15. withIdleness giải quyết vấn đề gì?**

Loại watermark của shard/subtask idle khỏi phép tính watermark chung để input đó không chặn window downstream.

**16. Vì sao consumer lag khác late event?**

Consumer lag là độ trễ xử lý so với đầu stream; late event là event có event time cũ đến sau theo thời gian nghiệp vụ hoặc watermark.

**17. Retention mặc định của Kinesis Data Streams là bao lâu?**

24 giờ; có thể tăng tối đa 365 ngày theo cấu hình và chi phí tương ứng.

**18. Khi nào nên dùng queue consumer?**

Khi mỗi record có thể xử lý độc lập, cần acknowledgement và scale worker mà không cần giữ shard lease/order semantics.

## 22. Checklist production

- [ ] Mỗi consumer có throughput, latency và business objective rõ ràng.
- [ ] EFO chỉ bật cho consumer cần throughput riêng hoặc latency thấp.
- [ ] Tổng registered consumers và queue registrations không vượt quota.
- [ ] Consumer đã ACTIVE trước khi SubscribeToShard.
- [ ] Subscription được renew đúng chu kỳ, có retry/backoff và xử lý child shards.
- [ ] IAM role chỉ có quyền stream/consumer cần thiết.
- [ ] Partition key phản ánh đúng entity cần ordering.
- [ ] Partition key có cardinality và phân bố tải phù hợp.
- [ ] Producer serialize writes theo key khi strict order là yêu cầu.
- [ ] PutRecords xử lý partial failures theo từng record.
- [ ] KCL checkpoint sau khi sink ghi bền vững; sink idempotent.
- [ ] Custom consumer xử lý parent/child lineage sau resharding.
- [ ] KPL aggregation có de-aggregation và subsequence checkpoint phù hợp.
- [ ] Event schema có eventId, eventTime và eventVersion.
- [ ] Watermark bound dựa trên số liệu event-time delay thực tế.
- [ ] Allowed lateness phù hợp SLA freshness và state budget.
- [ ] Late events vượt hạn có side output, alert và repair process.
- [ ] Watermark idleness được cấu hình và theo dõi.
- [ ] IteratorAge/MillisBehindLatest có cảnh báo trước khi chạm retention.
- [ ] Retention đủ dài cho recovery/replay và có lưu trữ dài hạn nếu cần.
- [ ] Có test cho duplicate, out-of-order, late events, resharding và sink outage.
- [ ] Có dashboard theo stream, shard, consumer và Flink operator.
- [ ] Đã tính EFO, retrieval, retention, CloudWatch và Flink state/snapshot cost.
- [ ] Runbook ghi rõ rollback, replay, reconciliation và owner.

## Tài liệu tham khảo

- [Enhanced Fan-Out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Develop enhanced fan-out consumers with the AWS SDK for Java](https://docs.aws.amazon.com/streams/latest/dev/building-enhanced-consumers-api.html)
- [RegisterStreamConsumer API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_RegisterStreamConsumer.html)
- [SubscribeToShard API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_SubscribeToShard.html)
- [SubscribeToShardEvent API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_SubscribeToShardEvent.html)
- [Kinesis Data Streams terminology and concepts](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Develop producers using the AWS SDK for Java](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-sdk.html)
- [Service-managed record distribution](https://docs.aws.amazon.com/streams/latest/dev/service-managed-record-distribution.html)
- [Important considerations for service-managed distribution](https://docs.aws.amazon.com/streams/latest/dev/service-managed-pk-considerations.html)
- [Use Kinesis Client Library](https://docs.aws.amazon.com/streams/latest/dev/kcl.html)
- [Resharding, scaling and parallel processing with KCL](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-scaling.html)
- [Develop producers using Kinesis Producer Library](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-kpl.html)
- [KPL consumer de-aggregation and checkpointing](https://docs.aws.amazon.com/streams/latest/dev/kinesis-kpl-consumer-deaggregation.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis Data Streams quotas and limits](https://docs.aws.amazon.com/streams/latest/dev/service-sizes-and-limits.html)
- [Monitor Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Troubleshoot Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/troubleshooting-consumers.html)
- [Managed Service for Apache Flink best practices: watermarks and idle shards](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html)
- [Apache Flink: Generating Watermarks](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/event-time/generating_watermarks/)
- [Apache Flink: Windows and allowed lateness](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/)
- [Amazon Kinesis Data Streams pricing](https://aws.amazon.com/kinesis/data-streams/pricing/)

