# Network timeout

Trong hệ thống Spring Kafka, network timeout là nhóm lỗi xảy ra khi một thành phần không nhận được phản hồi hoặc không hoàn tất một thao tác mạng trong khoảng thời gian được cấu hình. Producer có thể gửi record nhưng không nhận ACK kịp thời; consumer có thể không nhận được dữ liệu từ broker; request commit offset có thể thất bại vì kết nối bị ngắt; hoặc ứng dụng không kết nối được broker sau khi DNS, TLS hay network path gặp vấn đề.

Trong chương **Phân loại lỗi**, cần nhận diện đúng network timeout vì nhiều exception có tên giống nhau nhưng xuất phát từ các lớp khác nhau. Một timeout có thể xảy ra khi thiết lập kết nối, chờ phản hồi của broker, chờ buffer hoặc metadata ở producer, gọi API đồng bộ, xử lý HTTP downstream hay chờ listener hoàn tất. Cách khôi phục phụ thuộc vào điểm xảy ra lỗi và việc kết quả thao tác đã được thực hiện hay chưa.

**Network timeout không đồng nghĩa record chắc chắn chưa được ghi.** Broker có thể đã append record nhưng ACK bị mất hoặc đến trễ. Consumer có thể đã xử lý nghiệp vụ nhưng commit offset chưa thành công. Vì vậy, xử lý timeout phải tính đến kết quả không rõ ràng, retry có giới hạn, idempotency và khả năng đối chiếu dữ liệu.

## 1. Network timeout trong luồng Spring Kafka

Một luồng Kafka đi qua nhiều ranh giới mạng và nhiều thao tác có timeout riêng:

~~~mermaid
flowchart LR
    A["Spring application"] --> B["Kafka client"]
    B --> C["DNS / route / TCP"]
    C --> D["TLS / SASL authentication"]
    D --> E["Kafka broker"]
    E --> F["Metadata / coordinator"]
    E --> G["Partition leader / replicas"]
    B --> H["Producer send / Consumer fetch"]
    H --> I["ACK / records / commit response"]
~~~

Một lỗi ở bất kỳ ranh giới nào cũng có thể khiến thao tác không hoàn tất:

- DNS không phân giải được hostname broker.
- TCP connection không thiết lập được hoặc bị reset.
- TLS handshake bị treo hoặc thất bại.
- SASL authentication không hoàn tất hoặc broker không phản hồi.
- Client gửi ProduceRequest, FetchRequest hoặc OffsetCommitRequest nhưng không nhận response đúng hạn.
- Broker quá tải nên xử lý request chậm.
- Network route, firewall, proxy hoặc load balancer cắt kết nối.
- Client đang kết nối tới địa chỉ broker được trả về trong metadata nhưng địa chỉ đó không thể truy cập từ network của ứng dụng.

Timeout là một giới hạn thời gian của thao tác. Nó không tự cho biết nguyên nhân gốc là mạng, broker, DNS, TLS, tải hệ thống hay downstream. Cần xem exception gốc, request đang chờ, broker đích và các metric tại cùng thời điểm.

### 1.1 Timeout khác với connection failure

Hai trạng thái thường bị gộp chung:

- **Connection failure**: client không thể thiết lập hoặc duy trì kết nối, ví dụ connection refused, connection reset hoặc unknown host.
- **Timeout**: thao tác không hoàn tất trước deadline, ví dụ connect không thành công trong thời gian cho phép hoặc request không nhận response đúng hạn.

Connection failure thường khiến client thử kết nối lại. Timeout có thể xảy ra dù kết nối TCP vẫn tồn tại, chẳng hạn broker nhận request nhưng xử lý quá lâu hoặc response bị mất trên đường về.

Một exception có thể là biểu hiện cuối cùng của chuỗi lỗi. Ví dụ, client thử reconnect nhiều lần sau khi connection reset, cuối cùng API hết deadline và ném TimeoutException. Nếu chỉ nhìn exception cuối, có thể bỏ lỡ lỗi kết nối ban đầu.

### 1.2 Timeout khác với lỗi xác thực

TLS handshake timeout và SASL authentication failure cần được phân biệt:

- TLS handshake timeout có thể do network chậm, broker quá tải, certificate negotiation hoặc proxy.
- Certificate invalid, hostname mismatch hoặc truststore thiếu CA thường là lỗi cấu hình/chứng thư, không phải timeout có thể giải quyết bằng retry vô hạn.
- SASL authentication failure thường cần kiểm tra username, password, mechanism, token hoặc ACL.
- Nếu broker không phản hồi trong lúc authentication, client có thể báo timeout hoặc disconnect.

Không đổi timeout lớn hơn chỉ để che lỗi certificate, credential hoặc ACL. Hãy phân loại theo exception gốc và log broker.

## 2. Các vị trí timeout thường gặp

### 2.1 DNS và địa chỉ broker

Producer và consumer thường dùng bootstrap servers để tìm metadata cluster. Bootstrap server chỉ là điểm khởi đầu. Sau khi nhận metadata, client kết nối tới địa chỉ advertised của broker/leader.

Một tình huống thường gặp trong Kubernetes hoặc cloud:

1. Ứng dụng kết nối được bootstrap endpoint.
2. Broker trả metadata chứa địa chỉ advertised listener.
3. Client cố kết nối tới địa chỉ đó.
4. Địa chỉ chỉ truy cập được trong network nội bộ khác, không truy cập được từ pod ứng dụng.
5. Client liên tục reconnect hoặc request timeout.

Vì vậy, bootstrap connection thành công không chứng minh mọi broker address đều reachable. Cần kiểm tra advertised.listeners, DNS, routing, security group, firewall, service mesh và network policy từ chính môi trường chạy ứng dụng.

Các dấu hiệu:

- Log có UnknownHostException hoặc lỗi phân giải hostname.
- Một số broker kết nối được, một số broker liên tục timeout.
- Producer chỉ lỗi khi record được route tới partition có leader trên broker cụ thể.
- Consumer có thể fetch được một số partition nhưng một số partition khác không tiến triển.

### 2.2 TCP connect và reconnect

Client cần thiết lập TCP connection tới broker. Kết nối có thể thất bại vì broker không lắng nghe, port bị chặn, route sai, backlog cạn hoặc firewall từ chối.

Kafka client có cơ chế reconnect với backoff. Các cấu hình thường liên quan:

- reconnect.backoff.ms: thời gian chờ cơ bản trước khi thử kết nối lại.
- reconnect.backoff.max.ms: giới hạn trên của reconnect backoff.
- socket.connection.setup.timeout.ms: thời gian tối đa để thiết lập connection.
- socket.connection.setup.timeout.max.ms: giới hạn tối đa cho thời gian setup connection trong các lần thử.

Tên property và giá trị mặc định phụ thuộc Kafka client version. Hãy kiểm tra tài liệu đúng phiên bản đang dùng. Backoff giúp tránh reconnect storm; nó không sửa được DNS, route hoặc broker listener sai.

### 2.3 Request-response giữa client và broker

Khi connection đã thiết lập, Kafka client gửi request và chờ broker response. Một số request liên quan đến:

- ProduceRequest: gửi record tới partition leader.
- FetchRequest: consumer lấy record từ broker.
- MetadataRequest: lấy metadata cluster/topic.
- OffsetCommitRequest: commit offset cho consumer group.
- FindCoordinator và request tới group coordinator.
- Transaction coordinator request cho producer transactional.
- Admin API request như describe topic hoặc alter configuration.

Nếu broker chậm, queue request bị nghẽn hoặc network mất packet, client có thể không nhận response đúng hạn.

### 2.4 Consumer fetch và poll

Consumer poll là vòng lặp lấy dữ liệu và thực thi listener theo container model. Poll có thể trả về rỗng khi chưa có record; điều đó không nhất thiết là timeout hay lỗi.

Các cấu hình cần phân biệt:

- fetch.max.wait.ms: broker có thể chờ tối đa thời gian này để fetch response đáp ứng fetch.min.bytes.
- fetch.min.bytes: ngưỡng dữ liệu tối thiểu broker cố gắng gom trước khi trả response.
- request.timeout.ms: giới hạn thời gian chờ response của một request client.
- pollTimeout trong Spring Kafka: thời gian container chờ trong một lần poll theo cấu hình container.
- max.poll.interval.ms: giới hạn thời gian giữa các lần poll của consumer group member.

pollTimeout không phải request.timeout.ms. max.poll.interval.ms cũng không phải network timeout; nó bảo vệ tiến độ gọi poll. Nếu listener xử lý quá lâu và không gọi poll lại đúng hạn, consumer có thể rời group dù network vẫn bình thường.

### 2.5 Offset commit

Sau khi xử lý record, consumer có thể gửi request commit offset. Nếu coordinator không reachable hoặc response không đến trước deadline, commit có thể thất bại.

Khi commit thất bại, cần xác định:

- Listener đã hoàn tất business effect chưa?
- Offset commit đã được broker áp dụng nhưng response bị mất hay chưa?
- Container sẽ retry commit hay record sẽ được giao lại?
- Ack mode đang dùng là gì?
- Ứng dụng có idempotent side effect không?

Không được suy luận rằng commit timeout luôn có nghĩa offset chưa được lưu. Đây cũng là một kết quả không rõ ràng. Nếu record đã được xử lý nhưng commit response bị mất, lần giao lại có thể tạo duplicate side effect.

## 3. Phân biệt các timeout configuration của Kafka

Không có một property duy nhất điều khiển tất cả network timeout. Producer, consumer, connection setup và các API có deadline riêng.

| Property | Phạm vi | Ý nghĩa chính |
|---|---|---|
| request.timeout.ms | Producer và consumer request | Thời gian client chờ response cho một request |
| delivery.timeout.ms | Producer | Tổng thời gian tối đa để báo kết quả gửi, gồm batching, request và retry |
| max.block.ms | Producer API | Thời gian send có thể block khi chờ metadata hoặc buffer |
| default.api.timeout.ms | Consumer API | Deadline mặc định cho một số API đồng bộ của consumer |
| socket.connection.setup.timeout.ms | Network connection | Thời gian tối đa để thiết lập kết nối |
| socket.connection.setup.timeout.max.ms | Network connection | Giới hạn trên của thời gian setup connection |
| reconnect.backoff.ms | Network connection | Backoff giữa các lần reconnect |
| reconnect.backoff.max.ms | Network connection | Backoff reconnect tối đa |
| retry.backoff.ms | Client request retry | Thời gian chờ giữa các lần retry request |
| fetch.max.wait.ms | Broker fetch | Thời gian broker chờ gom dữ liệu cho fetch |
| session.timeout.ms | Consumer group | Thời gian heartbeat/member timeout theo group protocol |
| heartbeat.interval.ms | Consumer group | Khoảng cách gửi heartbeat ở classic group protocol |
| max.poll.interval.ms | Consumer group | Thời gian tối đa giữa các lần poll |
| transaction.timeout.ms | Producer transaction | Thời gian tối đa transaction được phép mở |

Các property có thể thay đổi theo phiên bản Kafka. Một số API có timeout riêng hoặc dùng default.api.timeout.ms. Đọc tài liệu client version đang chạy và xác nhận cấu hình hiệu lực ở runtime.

### 3.1 request.timeout.ms

request.timeout.ms xác định thời gian client chờ response cho một request. Nếu request không hoàn tất trong thời gian này, client có thể đánh dấu lỗi, đóng hoặc thay đổi trạng thái request, rồi retry tùy loại request và policy.

Với producer, request timeout áp dụng cho request gửi record tới broker. Nếu broker append record nhưng response bị mất, client có thể timeout dù record đã được ghi. Idempotent producer giúp xử lý retry ở tầng protocol, nhưng ứng dụng vẫn cần hiểu delivery result và business idempotency.

Với consumer, request timeout có thể ảnh hưởng fetch, metadata hoặc các request khác. Consumer có thể reconnect và tiếp tục fetch sau khi broker/network phục hồi.

Không nên đặt request.timeout.ms quá thấp so với độ trễ mạng và broker thực tế. Giá trị quá thấp có thể gây timeout giả, retry không cần thiết và tăng tải. Giá trị quá cao có thể làm ứng dụng phát hiện sự cố chậm hơn.

### 3.2 delivery.timeout.ms

delivery.timeout.ms là deadline tổng thể cho việc gửi record của producer. Nó bao gồm thời gian record chờ trong batch, các request và retry. Khi hết thời gian mà producer chưa hoàn tất việc gửi, callback/future được hoàn thành với lỗi.

Với Kafka producer hiện đại, delivery.timeout.ms cần lớn hơn hoặc bằng tổng request.timeout.ms và linger.ms theo điều kiện client yêu cầu. Cần kiểm tra tài liệu của version cụ thể.

Ví dụ: request.timeout.ms là 30 giây, linger.ms là 5 mili giây, delivery.timeout.ms là 120 giây. Producer có thời gian tổng thể lớn hơn một request timeout để thử lại request trong giới hạn delivery deadline.

Tăng delivery timeout có thể giúp vượt qua một đợt broker failover ngắn, nhưng cũng khiến ứng dụng chờ lâu hơn trước khi biết send thất bại. Hãy chọn theo SLA và khả năng lưu event chờ gửi của ứng dụng.

### 3.3 max.block.ms

KafkaProducer.send() thường trả về bất đồng bộ, nhưng lời gọi send() vẫn có thể block trước khi trả về nếu producer cần lấy metadata hoặc chờ buffer có chỗ trống. max.block.ms giới hạn thời gian chờ cho một số tình huống đó.

Ví dụ:

- Producer chưa có metadata cho topic/partition và phải chờ metadata.
- Record cần buffer nhưng producer buffer đang đầy vì broker chậm.
- Network outage làm record tồn tại trong buffer lâu hơn và buffer không được giải phóng.

Do đó, ứng dụng có thể thấy lời gọi send() chưa trả về ngay cả khi callback/future chưa được tạo. Đây khác với việc future đã được trả về rồi hoàn tất lỗi do delivery timeout.

### 3.4 default.api.timeout.ms

Một số KafkaConsumer API đồng bộ dùng default.api.timeout.ms làm deadline mặc định nếu caller không truyền timeout riêng. Nó không thay thế request.timeout.ms; API deadline có thể bao gồm nhiều request hoặc chờ nội bộ.

Nếu ứng dụng gọi API đồng bộ như commitSync hoặc các thao tác quản trị consumer, cần phân biệt timeout của API tổng thể với timeout từng request tới broker.

### 3.5 session.timeout.ms và heartbeat.interval.ms

session.timeout.ms liên quan tới thời gian broker chờ heartbeat từ consumer group member trước khi coi member mất kết nối. heartbeat.interval.ms điều khiển nhịp heartbeat trong classic group protocol.

Đây không phải timeout cho một ProduceRequest hay FetchRequest. Consumer có thể bị loại khỏi group vì heartbeat không đến đúng hạn do network outage, process pause hoặc thread scheduling. Ngược lại, request fetch có thể timeout trong khi consumer vẫn giữ membership nếu heartbeat tiếp tục hoạt động.

Ở các group protocol mới, một số tham số heartbeat được điều khiển khác. Hãy dùng đúng cấu hình theo group protocol và Kafka client version.

### 3.6 max.poll.interval.ms

max.poll.interval.ms giới hạn thời gian giữa hai lần gọi poll. Nếu listener xử lý quá lâu hoặc consumer thread bị block, consumer có thể vượt quá giới hạn này và bị xem là không còn tiến triển.

Đây thường là vấn đề processing time hoặc thread starvation, không nhất thiết là network timeout. Tăng max.poll.interval.ms có thể phù hợp nếu batch xử lý hợp lệ lâu hơn dự kiến, nhưng không chữa được một HTTP call treo vô hạn hoặc database pool cạn.

### 3.7 transaction.timeout.ms

transaction.timeout.ms giới hạn thời gian một Kafka transaction được phép mở. Transaction mở lâu có thể bị coordinator abort. Đây là transaction timeout, không phải request timeout.

Một producer có thể gặp network timeout khi commit transaction; một transaction có thể timeout vì vượt thời gian cho phép; hai lỗi có thể cùng xuất hiện nhưng cần phân loại riêng.

## 4. Network timeout ở producer

Producer có thể gặp timeout trước khi send, trong khi gửi hoặc sau khi broker đã nhận record.

### 4.1 Các điểm có thể timeout

- Lấy metadata topic hoặc partition.
- Thiết lập kết nối tới broker leader.
- Chờ buffer trong producer.
- Chờ broker xử lý ProduceRequest.
- Retry request sau connection reset hoặc broker failover.
- Chờ delivery deadline tổng thể.
- Gọi transaction commit/abort hoặc coordinator API.

Một producer gửi tới nhiều topic/partition có thể chỉ timeout với một broker hoặc một số partition. Vì vậy, log topic và partition, broker node, client id cùng exception gốc rất quan trọng.

### 4.2 Các exception thường gặp

Tên exception phụ thuộc tầng lỗi và Kafka client version. Một số loại thường thấy:

| Exception / triệu chứng | Diễn giải thường gặp | Hướng kiểm tra |
|---|---|---|
| TimeoutException | Một thao tác không hoàn tất trong deadline | Xem API, request, delivery và max block timeout |
| NetworkException | Lỗi ở tầng network client | Connection, route, broker và socket |
| DisconnectException | Kết nối broker bị ngắt trong khi xử lý request | Broker restart, idle connection, proxy hoặc network reset |
| SocketTimeoutException | Socket không nhận dữ liệu đúng hạn ở một số tầng | Network path, broker response và timeout |
| UnknownHostException | DNS không phân giải được broker hostname | DNS, advertised.listeners và network namespace |
| NotLeaderOrFollowerException | Request tới broker không còn giữ vai trò phù hợp | Metadata refresh, leader election và broker state |
| RecordTooLargeException | Record vượt giới hạn kích thước | Producer, broker và topic size limit |
| KafkaException bọc lỗi gửi | Exception tổng hợp ở tầng client/Spring | Đọc root cause và metadata của failed record |

Không phải mọi TimeoutException đều do packet loss. Broker overload, thread starvation, metadata delay hoặc timeout cấu hình quá thấp cũng có thể tạo cùng biểu hiện.

### 4.3 Kết quả send không rõ ràng

Một trường hợp quan trọng:

1. Producer gửi record tới leader.
2. Leader append record thành công.
3. Broker gửi ACK.
4. Network mất response trước khi ACK tới producer.
5. Producer hết request/delivery timeout.
6. Ứng dụng nhận lỗi dù record có thể đã tồn tại trong Kafka.

Nếu ứng dụng lập tức tạo một event mới và gửi lại, record có thể bị duplicate. Cần phân biệt retry cùng một producer request với lần gửi nghiệp vụ mới.

Idempotent producer giúp loại bỏ duplicate do retry protocol trong cùng producer session. Tuy nhiên, nếu application restart hoặc gửi lại cùng event như một operation mới, nên dùng event id/business key ổn định và idempotency ở consumer/downstream.

### 4.4 Xử lý future của KafkaTemplate

Spring Kafka KafkaTemplate.send() trả về CompletableFuture trong các phiên bản Spring Kafka hiện đại. Ứng dụng nên quan sát kết quả bất đồng bộ thay vì bỏ qua lỗi.

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send(
            "orders",
            event.orderId(),
            event
        )
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed: eventId={}",
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Kafka send succeeded: eventId={}, topic={}, partition={}, offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

Future thành công nghĩa producer đã nhận kết quả theo ACK policy. Nó không chứng minh consumer downstream đã xử lý record.

Cũng cần nhớ lời gọi send() có thể block trước khi trả future do chờ metadata hoặc buffer theo max.block.ms. Nếu thread gọi send() bị block, callback chưa thể giúp giải phóng thread đó. Cần kiểm tra cả send call latency và future completion latency.

### 4.5 Không retry vô hạn trong callback

Một callback không nên gọi lại send ngay lập tức trong vòng lặp không giới hạn. Nếu broker đang outage, mọi producer instance có thể tạo retry storm, làm buffer đầy và tăng áp lực lên broker khi phục hồi.

Retry cần:

- Có số lần thử hoặc deadline tổng thể.
- Backoff, có jitter khi nhiều instance cùng retry.
- Phân loại lỗi retriable và non-retriable.
- Bảo toàn event id để chống duplicate.
- Có durable storage/outbox nếu event không được phép mất.
- Có metric cho pending send, retry, timeout và send failure.

Kafka producer đã có retry logic nội bộ. Retry ở application layer cần được tính cùng với retry của client để tránh nhân số lần thử ngoài dự kiến.

## 5. Network timeout ở consumer

Consumer nhận dữ liệu qua FetchRequest và gửi các request liên quan tới group coordination, offset commit và metadata. Network timeout có thể làm một consumer tạm ngừng fetch, mất coordinator connection hoặc không commit được offset.

### 5.1 Fetch timeout và consumer không có record

Consumer poll trả về rỗng không tự động có nghĩa network timeout. Có thể topic chưa có record mới, partition chưa được gán, consumer đang ở cuối log hoặc record chưa visible do isolation level.

Khi nghi network timeout, kiểm tra:

- Fetch request latency và error.
- Broker connection state.
- Consumer assigned partitions.
- Poll rate và record rate.
- Broker leader của partition.
- Consumer lag và offset position.
- DNS và advertised broker addresses.

Nếu consumer không nhận record từ một partition nhưng vẫn nhận từ partition khác, có thể partition đó có leader/network issue riêng.

### 5.2 Offset commit timeout

Commit offset có thể timeout khi coordinator không reachable hoặc response bị mất. Khi dùng manual acknowledgment hoặc container-managed commit, cần xem log container và commit failure metrics.

Nếu business effect đã hoàn tất nhưng commit chưa xác định được kết quả, record có thể được giao lại. Do đó:

- Business operation nên idempotent.
- Ghi event id và source offset vào log/tracing.
- Không commit offset trước khi business effect hoàn tất nếu muốn at-least-once.
- Không coi commit timeout là bằng chứng chắc chắn commit thất bại.

### 5.3 Heartbeat và session timeout

Khi network gián đoạn, consumer có thể không gửi được heartbeat. Nếu broker không nhận heartbeat trong session timeout, member bị loại khỏi group và partition được gán lại.

Điều này có thể tạo rebalance và record được giao cho consumer khác. Consumer cũ có thể vẫn đang chạy code listener trong một khoảng thời gian ngắn; nếu side effect không idempotent, hai instance có thể cùng tác động tới nghiệp vụ.

Khi khôi phục network, consumer có thể rejoin group. Theo dõi rebalance, assignment và offset để xác nhận group đã ổn định.

### 5.4 Network timeout hay listener xử lý chậm?

Listener chạy đồng bộ trên consumer thread có thể giữ thread quá lâu. Consumer không gọi poll lại đúng hạn, gây max.poll.interval.ms vượt ngưỡng. Đây là processing timeout hoặc poll interval violation, dù log có thể xuất hiện các lỗi consumer membership sau đó.

Ví dụ listener gọi API bên ngoài:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event) {
    paymentClient.charge(event);
}
~~~

Nếu paymentClient.charge() chờ HTTP response 5 phút, consumer thread không xử lý poll trong thời gian đó. Nếu max.poll.interval.ms ngắn hơn, consumer có thể bị loại khỏi group.

Giải pháp là đặt timeout hữu hạn cho HTTP call, giới hạn thời gian xử lý record/batch, thiết kế retry phù hợp và điều chỉnh poll interval theo thời gian xử lý hợp lệ. Không tăng request.timeout.ms của Kafka để chữa HTTP timeout của payment service.

## 6. Network timeout ở downstream không phải Kafka broker timeout

Một listener có thể gọi database, REST API, gRPC service hoặc object storage. Timeout ở các dependency này thường được bọc trong exception do client của dependency ném ra.

Ví dụ:

- HTTP connect timeout: không thiết lập được kết nối tới API.
- HTTP read/response timeout: kết nối đã có nhưng không nhận response đúng hạn.
- JDBC socket timeout: database query hoặc network response không hoàn tất.
- gRPC deadline exceeded: RPC không hoàn thành trước deadline.

Đây là lỗi mạng của dependency, không phải nhất thiết là lỗi kết nối Kafka. Tuy nhiên, nó có thể làm listener xử lý thất bại, dẫn tới retry, rollback hoặc không commit offset.

Cần log dependency name, operation, endpoint/service, timeout setting và correlation id. Tránh gộp mọi lỗi vào một metric kafka_network_timeout vì sẽ làm sai chẩn đoán.

### 6.1 Timeout downstream có thể làm Kafka lag tăng

Chuỗi tác động:

1. Consumer poll record.
2. Listener gọi downstream.
3. Downstream chậm hoặc mất kết nối.
4. Listener giữ consumer thread hoặc retry.
5. Consumer xử lý ít record hơn.
6. Consumer lag tăng.
7. Nếu poll interval vượt giới hạn, group rebalance.
8. Record chưa commit có thể được giao lại.

Lag tăng là triệu chứng ở Kafka consumer, nhưng nguyên nhân gốc có thể nằm ở downstream. Tăng concurrency khi database/API đang quá tải có thể làm tình trạng nghiêm trọng hơn.

### 6.2 Đặt timeout theo từng dependency

Không dùng một timeout tổng quát cho tất cả thao tác. Ví dụ:

- Connect timeout cho thiết lập TCP.
- Response/read timeout cho thời gian chờ dữ liệu.
- Deadline tổng thể cho cả request.
- Database query timeout và connection acquisition timeout.
- Kafka request timeout và delivery timeout.

Tổng thời gian của một lần xử lý phải phù hợp với retry budget và max.poll.interval.ms. Nếu một record gọi nhiều dependency tuần tự, tổng latency có thể lớn hơn timeout của từng call.

## 7. Phân biệt timeout với các lỗi Kafka khác

Timeout thường bị nhầm với các failure mode khác. Bảng sau giúp phân loại:

| Lỗi | Bản chất | Cần kiểm tra |
|---|---|---|
| Network timeout | Thao tác mạng không hoàn tất đúng hạn | Request, connection, DNS, route, broker latency |
| Connection refused | TCP endpoint từ chối kết nối | Broker listener, port, firewall, service |
| AuthenticationException | Client không xác thực được | SASL, credentials, token, TLS identity |
| AuthorizationException | Client không có quyền | ACL, principal, topic/group permissions |
| SerializationException | Không serialize/deserialize được dữ liệu | Serializer, schema, payload |
| NotLeaderOrFollowerException | Metadata/leader thay đổi hoặc request sai broker | Leader election, metadata refresh |
| NotEnoughReplicasException | ISR không đạt min ISR cho ghi | ISR, broker replica, min.insync.replicas |
| RecordTooLargeException | Kích thước record vượt giới hạn | Producer/broker/topic limits |
| CommitFailedException | Commit không thành công, thường liên quan group state | Rebalance, membership, commit timing |
| RebalanceInProgressException | Group đang rebalance | Member changes, poll, heartbeat |
| ListenerExecutionFailedException | Listener xử lý ném exception | Root cause trong business code |
| Max poll interval exceeded | Consumer không poll lại kịp | Listener duration, thread blocking, batch size |

Một exception wrapper của Spring có thể che exception Kafka hoặc dependency ở bên trong. Luôn xem root cause và stack trace đầy đủ, đồng thời ghi rõ operation đang thực hiện.

## 8. Cấu hình timeout trong Spring Boot

Một cấu hình minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        max.block.ms: 60000
        reconnect.backoff.ms: 250
        reconnect.backoff.max.ms: 5000
    consumer:
      enable-auto-commit: false
      properties:
        request.timeout.ms: 30000
        default.api.timeout.ms: 60000
        reconnect.backoff.ms: 250
        reconnect.backoff.max.ms: 5000
        retry.backoff.ms: 500
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
        max.poll.interval.ms: 300000
    listener:
      poll-timeout: 1500
~~~

Các con số trên chỉ là ví dụ để minh họa mối quan hệ giữa timeout. Không sao chép vào production mà chưa đo network latency, broker processing time, listener duration, SLA và group protocol.

Cần nhớ:

- Producer request timeout giới hạn một request; delivery timeout giới hạn toàn bộ thời gian gửi.
- max.block.ms có thể ảnh hưởng thời gian lời gọi send() chờ metadata/buffer.
- Consumer request timeout và default API timeout có phạm vi khác nhau.
- session.timeout.ms liên quan heartbeat/member liveness.
- max.poll.interval.ms liên quan khoảng cách giữa poll.
- poll-timeout là cấu hình listener container, không phải network request timeout.

Nếu dùng Spring Kafka với custom ProducerFactory/ConsumerFactory, hãy xác nhận properties được truyền vào đúng factory. Một property trong application.yml có thể không áp dụng cho factory tự tạo.

## 9. Chọn timeout theo latency và SLA

Không nên chọn timeout theo cảm tính hoặc đặt tất cả thật lớn. Cần xác định deadline cho từng tầng.

Một cách tiếp cận:

1. Đo latency bình thường và p95/p99 của network/broker.
2. Xác định thời gian gián đoạn ngắn mà hệ thống cần tự phục hồi.
3. Xác định SLA của producer send và consumer processing.
4. Chọn request timeout đủ lớn để tránh timeout giả trong điều kiện tải bình thường.
5. Chọn delivery timeout bao phủ số lần retry/backoff dự kiến.
6. Đảm bảo listener processing budget phù hợp với max.poll.interval.ms.
7. Đặt timeout dependency downstream riêng.
8. Kiểm tra shutdown timeout và transaction timeout nếu listener dùng transaction.

Ví dụ, nếu p99 ProduceRequest latency là 800 ms trong giờ cao điểm, request timeout 100 ms có thể tạo timeout giả. Nhưng đặt request timeout 10 phút cũng làm lỗi phát hiện quá chậm. Hãy dùng số đo thực tế và mục tiêu phục hồi.

### 9.1 Deadline lồng nhau

Một request nghiệp vụ có thể đi qua nhiều tầng:

~~~text
HTTP caller deadline
  -> application processing deadline
      -> Kafka producer delivery timeout
          -> individual request timeout
              -> TCP/network
~~~

Deadline ở tầng ngoài phải đủ cho các tầng trong, nhưng không nên cộng các timeout vô hạn. Nếu application deadline ngắn hơn delivery timeout, caller có thể bỏ cuộc trong khi producer vẫn tiếp tục gửi. Nếu application retry ngay, duplicate có thể xuất hiện.

Cần xác định ai sở hữu retry và deadline. Một tầng nên điều phối retry tổng thể, các tầng bên dưới có retry hữu hạn và không vượt budget.

### 9.2 Retry budget

Ví dụ một operation có deadline 90 giây. Ứng dụng có thể dành:

- 10 giây cho connect/metadata.
- Tối đa 3 lần request với timeout 20 giây.
- Backoff 1 và 2 giây giữa các lần thử.
- Phần còn lại cho callback và xử lý kết quả.

Đây chỉ là ví dụ. Quan trọng là tổng thời gian thử lại phải nằm trong deadline của operation và không giữ thread hoặc buffer vô hạn.

## 10. Retry và phục hồi network timeout

Retry phù hợp khi lỗi có khả năng tạm thời và operation có thể lặp an toàn. Không phải mọi timeout đều nên retry.

### 10.1 Phân loại lỗi trước khi retry

**Có thể retry có giới hạn:**

- Broker tạm thời không reachable.
- Connection reset.
- Leader election ngắn.
- Request timeout do broker/network chậm tạm thời.
- Downstream trả lỗi tạm thời hoặc rate limit có thời gian phục hồi.

**Cần sửa cấu hình hoặc dữ liệu trước:**

- Unknown topic hoặc sai bootstrap server.
- DNS hostname không tồn tại.
- TLS certificate invalid hoặc hostname mismatch.
- SASL credentials sai.
- ACL không đủ quyền.
- Record serialization lỗi.
- Record vượt giới hạn kích thước.
- Endpoint cấu hình sai.

Một số lỗi có thể xuất hiện dưới dạng timeout trước khi root cause rõ ràng. Dùng exception gốc, log và network probe để phân loại.

### 10.2 Exponential backoff và jitter

Retry liên tục ngay lập tức có thể làm broker hoặc downstream quá tải. Exponential backoff tăng dần thời gian chờ:

~~~text
attempt 1: wait 250 ms
attempt 2: wait 500 ms
attempt 3: wait 1 s
attempt 4: wait 2 s
attempt 5: wait 4 s
~~~

Có thể thêm jitter để các instance không retry cùng một thời điểm. Backoff cần có giới hạn tối đa và tổng retry deadline.

Kafka client đã có reconnect và retry backoff riêng. Application-level retry phải phối hợp với client retry, không nhân số lần thử vô hạn.

### 10.3 Circuit breaker và bulkhead

Nếu downstream liên tục timeout, circuit breaker có thể tạm ngừng gọi dependency để cho nó phục hồi. Bulkhead giới hạn số call đồng thời để một dependency chậm không chiếm hết thread hoặc connection.

Với Kafka listener, cần quyết định khi circuit mở:

- Listener ném exception để record được retry sau.
- Tạm pause container/partition theo policy.
- Chuyển record sang retry topic nếu semantics cho phép.
- Lưu event vào một durable queue/outbox khác đã thiết kế trước.

Không nuốt exception rồi commit offset nếu business effect chưa hoàn tất. Cũng không retry quá nhanh trên cùng record trong khi dependency vẫn outage.

### 10.4 Retry topic và blocking retry

Blocking retry giữ record trong luồng xử lý hiện tại và có thể chặn partition. Retry topic chuyển record sang topic khác để xử lý sau, giảm việc giữ consumer thread nhưng có thể thay đổi thứ tự.

Chọn theo yêu cầu ordering và SLA. Timeout broker/network ở tầng Kafka producer có thể cần xử lý bởi client retry trước khi listener-level retry. Timeout downstream từ business listener có thể phù hợp với error handler hoặc retry topic hơn.

## 11. Spring Kafka error handling khi timeout

Spring Kafka listener container gọi error handler khi listener ném exception. Việc retry phụ thuộc loại exception, cấu hình error handler và transaction mode.

Ví dụ minh họa cấu hình DefaultErrorHandler với retry có giới hạn:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            new FixedBackOff(1_000L, 3L)
        );

    handler.addRetryableExceptions(
        RetryableBusinessException.class
    );

    return handler;
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế:

- Error handler này xử lý exception phát sinh trong listener. Network request/reconnect nội bộ của Kafka consumer được Kafka client quản lý; không nên giả định các lỗi fetch/connection sẽ được chuyển vào listener error handler.
- Timeout từ HTTP/database có thể bị bọc trong exception của client dependency. Chuyển lỗi tạm thời thành một exception nghiệp vụ như RetryableBusinessException chỉ sau khi xác định operation có thể retry an toàn.
- Không thêm mọi exception vào retryable.
- Một số lỗi authentication/authorization/configuration không thể phục hồi bằng retry.
- Retry count cần hữu hạn và backoff cần phù hợp SLA.
- Với record không thể phục hồi, cân nhắc DLT.
- Nếu dùng transactional listener, rollback/retry/recovery transaction cần cấu hình phù hợp.

### 11.1 Timeout trong listener và retry

Nếu listener gọi downstream rồi nhận SocketTimeoutException, error handler có thể retry record. Nhưng retry chỉ có ý nghĩa nếu downstream có thể phục hồi trong khoảng thời gian retry.

Nếu listener đã thực hiện side effect một phần rồi timeout, record retry có thể thực hiện lại side effect. Cần idempotency key hoặc transaction/outbox/inbox phù hợp.

### 11.2 Không dùng retry để che broker outage kéo dài

Nếu toàn bộ Kafka cluster không reachable, listener retry record không sửa được network path. Producer của DLT cũng có thể không gửi được. Trong trường hợp đó, cần phục hồi kết nối broker hoặc dùng durable fallback đã thiết kế trước.

## 12. Kết quả không rõ ràng và idempotency

Timeout là một trong những nguyên nhân phổ biến tạo kết quả không rõ ràng. Client không biết chắc thao tác đã được thực hiện hay chưa.

### 12.1 Producer send timeout

Broker có thể append record rồi mất ACK. Ứng dụng nhận lỗi nhưng record có thể đã tồn tại. Retry bằng event id mới sẽ tạo một nghiệp vụ mới về mặt dữ liệu.

Giải pháp:

- Bật idempotent producer khi phù hợp.
- Giữ event id ổn định qua các lần gửi lại.
- Lưu ý định phát event trong transactional outbox nếu event bắt buộc.
- Consumer deduplicate theo event id hoặc business key.
- Đối chiếu topic/partition/offset khi điều tra.

### 12.2 Consumer commit timeout

Listener có thể hoàn tất database update nhưng commit offset timeout. Consumer group có thể đọc lại record sau rebalance/restart.

Giải pháp:

- Ghi event id và source offset trong log.
- Database có unique constraint/inbox table nếu nghiệp vụ yêu cầu.
- Business handler phải idempotent.
- Chỉ commit offset theo policy sau khi business effect hoàn tất.
- Không reset offset tùy tiện khi commit outcome chưa rõ.

### 12.3 HTTP timeout sau khi downstream đã xử lý

Một API có thể hoàn tất operation nhưng response bị mất. Retry request có thể tạo side effect lần hai.

Dùng idempotency key được downstream hỗ trợ. Nếu downstream không hỗ trợ, cần reconciliation hoặc mô hình nghiệp vụ có thể phát hiện duplicate.

## 13. Quan sát network timeout

Cần quan sát ở ba lớp: Kafka client, broker/network và business processing.

### 13.1 Producer metrics

Theo dõi:

- request-latency-avg và request-latency-max.
- record-error-rate và record-retry-rate.
- record-send-rate.
- request-rate và response-rate.
- buffer-available-bytes.
- record-queue-time-avg.
- batch-size-avg.
- connection creation/close và node connection state nếu exporter cung cấp.

Một số metric name thay đổi theo client version hoặc exporter. Xác nhận metric thực tế trước khi tạo dashboard.

### 13.2 Consumer metrics

Theo dõi:

- fetch-latency-avg/max.
- fetch-rate và records-consumed-rate.
- commit-latency-avg/max.
- heartbeat rate và response.
- assigned partitions.
- rebalance rate.
- consumer lag theo group/topic/partition.
- poll interval và listener processing duration.
- connection state và request error.

Lag tăng cùng fetch latency cao gợi ý vấn đề broker/network hoặc tải fetch. Lag tăng cùng listener duration cao gợi ý processing/downstream bottleneck.

### 13.3 Broker và network metrics

Theo dõi:

- Produce/Fetch request handler latency.
- Request queue time và handler saturation.
- Network processor idle percent.
- Bytes in/out, connection count và connection creation rate.
- CPU, disk I/O, page cache và filesystem.
- Broker availability và leader distribution.
- Under-replicated partitions, ISR shrink/expand.
- TCP retransmission, packet loss, connection reset nếu hạ tầng cung cấp.
- DNS resolution errors và TLS handshake failures.

Nếu nhiều service cùng timeout tới một broker, nghi ngờ broker hoặc network segment dùng chung. Nếu chỉ một pod lỗi, kiểm tra node, DNS cache, route, security policy và local resource của pod đó.

### 13.4 Log cần có

Mỗi lỗi nên ghi:

- Service name, environment và instance/pod.
- Kafka client id và group id nếu là consumer.
- Operation: metadata, produce, fetch, commit, transaction hay downstream call.
- Topic, partition và offset nếu có.
- Broker node/host/port đang được gọi.
- Exception class và root cause.
- Timeout setting/deadline liên quan.
- Event id/correlation id.
- Số lần retry và thời gian đã chờ.

Không log credential, SASL secret, token hoặc payload nhạy cảm.

## 14. Quy trình khoanh vùng khi có network timeout

Khi alert hoặc log xuất hiện timeout, đi theo thứ tự:

1. **Xác định operation**: producer send, metadata, consumer fetch, offset commit, transaction, hay HTTP/database downstream.
2. **Xác định phạm vi**: một pod, một broker, một partition, một service, một AZ hay toàn cluster.
3. **Đọc root cause**: TimeoutException, NetworkException, DisconnectException, UnknownHostException, SocketTimeoutException hay exception của dependency.
4. **Kiểm tra địa chỉ đích**: bootstrap server, advertised broker address, DNS, port và route từ chính pod bị lỗi.
5. **Kiểm tra kết nối**: TCP connect/reset, TLS handshake, SASL và firewall/network policy.
6. **Đối chiếu broker**: request latency, queue time, CPU, disk, network processor và broker restart.
7. **Kiểm tra timeout hierarchy**: request timeout, delivery timeout, max block, API timeout, session timeout, max poll interval và downstream deadline.
8. **Đánh giá kết quả thao tác**: record có thể đã append không? business effect có thể đã hoàn tất không? offset commit có thể đã được áp dụng không?
9. **Khôi phục có kiểm soát**: sửa network/config, để client reconnect, retry hữu hạn và tránh restart đồng loạt nếu không cần thiết.
10. **Xác minh sau phục hồi**: send/fetch/commit latency bình thường, consumer group ổn định, lag giảm và business event không bị mất hoặc duplicate.

Không bắt đầu bằng việc tăng tất cả timeout. Trước tiên xác định thao tác và root cause; nếu network route sai hoặc broker address unreachable, tăng timeout chỉ kéo dài thời gian chờ.

## 15. Các tình huống thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer send timeout tới một broker | Broker quá tải, leader broker unreachable hoặc network path lỗi | Xác định partition leader và broker; kiểm tra request latency, route và reconnect |
| Bootstrap kết nối được nhưng produce thất bại | advertised.listeners trả địa chỉ không truy cập được từ app | Kiểm tra metadata và advertised listener từ network của pod |
| Consumer fetch timeout | Broker chậm, network packet loss hoặc broker connection reset | Xem fetch latency, broker health và connection state |
| Offset commit timeout | Group coordinator unreachable hoặc response bị mất | Kiểm tra coordinator, rebalance và committed offset; bảo đảm idempotency |
| Nhiều pod cùng timeout | Broker, DNS, firewall hoặc network segment dùng chung | Đối chiếu lỗi theo broker và zone; kiểm tra hạ tầng chung |
| Chỉ một pod timeout | Node/pod DNS, route, CPU pause hoặc local resource | So sánh pod khỏe và pod lỗi trên cùng thời điểm |
| Timeout tăng khi traffic tăng | Broker/request handler/buffer hoặc downstream saturation | Kiểm tra queue, CPU, disk, pool và throughput |
| Listener timeout nhưng Kafka client khỏe | HTTP/database downstream chậm | Xem dependency latency và đặt timeout riêng |
| Consumer bị rebalance sau call chậm | Listener block vượt max.poll.interval.ms | Giới hạn processing time, điều chỉnh poll budget và retry |
| Timeout sau leader election | Client đang refresh metadata/reconnect | Theo dõi leader và retry; xác nhận record outcome |
| Transaction commit timeout | Coordinator/network hoặc transaction state không rõ | Kiểm tra transaction lifecycle, producer fencing và idempotency |

## 16. Ví dụ thực hành

### 16.1 Producer có timeout và idempotence

Cấu hình minh họa:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        max.block.ms: 60000
~~~

Trong ví dụ, producer chờ ACK theo acks=all, retry theo client policy trong giới hạn delivery timeout và chờ metadata/buffer tối đa theo max.block.ms. Cần đặt giá trị theo latency đo được và SLA.

### 16.2 Consumer timeout và poll budget

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        request.timeout.ms: 30000
        default.api.timeout.ms: 60000
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
        max.poll.interval.ms: 300000
    listener:
      poll-timeout: 1500ms
~~~

Cấu hình này minh họa rằng request, API, session, poll interval và container poll timeout là các giới hạn khác nhau. Điều chỉnh chúng theo consumer group protocol và version Kafka đang dùng.

### 16.3 Listener gọi downstream có timeout hữu hạn

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service-prod"
)
public void handle(OrderCreated event) {
    try {
        paymentClient.charge(
            event.orderId(),
            event.eventId()
        );
    } catch (SocketTimeoutException ex) {
        throw new RetryableBusinessException(
            "Payment service response timed out",
            ex
        );
    }
}
~~~

Ví dụ cho thấy timeout downstream được chuyển thành lỗi nghiệp vụ có thể retry theo policy. Trong ứng dụng thật, payment client phải có connect/read/deadline timeout riêng và eventId phải được downstream dùng như idempotency key. Không retry nếu kết quả charge không rõ ràng mà API không hỗ trợ idempotency hoặc reconciliation.

## 17. Kiểm thử network timeout

Kiểm thử trong môi trường staging hoặc test cluster có topology phù hợp. Không gây lỗi mạng trên production nếu chưa có phạm vi và cơ chế dừng rõ ràng.

Các tình huống có thể thử:

- Chặn kết nối TCP từ một consumer test tới một broker test.
- Làm DNS resolution thất bại cho một hostname broker trong môi trường cô lập.
- Tạo packet delay/loss có kiểm soát.
- Restart một broker để quan sát leader election và client reconnect.
- Tạo tải broker cao để quan sát request latency và timeout.
- Làm downstream HTTP service phản hồi chậm để phân biệt listener timeout với Kafka request timeout.
- Ngắt kết nối trong lúc producer gửi và đối chiếu event id/offset.
- Ngắt kết nối trong lúc commit offset và xác nhận xử lý lặp an toàn.
- Kiểm tra producer buffer khi broker không nhận request.
- Kiểm tra consumer heartbeat và rebalance khi network gián đoạn.

Mỗi bài test cần có giả thuyết, thời gian giới hạn, đối tượng thử nghiệm, record id và tiêu chí phục hồi. Ví dụ: sau khi broker trở lại, producer send thành công trong deadline; consumer group rejoin; offset tiến triển; không có side effect duplicate ngoài chính sách.

## 18. Checklist vận hành network timeout

**Phân loại**

- [ ] Biết timeout xảy ra ở producer, consumer, broker request, coordinator hay downstream.
- [ ] Root cause được ghi lại thay vì chỉ ghi exception wrapper.
- [ ] Phân biệt timeout, connection refused, authentication và authorization.
- [ ] Xác định broker/partition/operation liên quan.

**Cấu hình**

- [ ] request.timeout.ms phù hợp latency thực tế.
- [ ] delivery.timeout.ms đủ cho retry budget và phù hợp SLA.
- [ ] max.block.ms được cân nhắc cho metadata/buffer wait.
- [ ] default.api.timeout.ms được hiểu đúng cho consumer API.
- [ ] reconnect/retry backoff có giới hạn.
- [ ] session.timeout.ms và max.poll.interval.ms được phân biệt.
- [ ] Downstream connect/read/deadline timeout được cấu hình riêng.

**Độ an toàn dữ liệu**

- [ ] Producer idempotence được bật khi phù hợp.
- [ ] Event id/business key ổn định qua retry.
- [ ] Consumer side effect idempotent hoặc có inbox/deduplication.
- [ ] Offset chỉ commit theo policy sau business effect cần thiết.
- [ ] Có outbox hoặc durable fallback cho event bắt buộc.
- [ ] Không coi timeout là bằng chứng thao tác chưa được thực hiện.

**Quan sát và phục hồi**

- [ ] Theo dõi producer request latency, retry, error và buffer.
- [ ] Theo dõi consumer fetch/commit latency, lag và rebalance.
- [ ] Theo dõi broker queue, network, disk và connection.
- [ ] Log operation, broker, topic/partition, event id và timeout setting.
- [ ] Retry hữu hạn với backoff/jitter.
- [ ] Có runbook kiểm tra DNS, advertised.listeners, route, TLS và ACL.
- [ ] Đã diễn tập reconnect, leader loss, commit timeout và downstream timeout.

Network timeout là một tín hiệu về deadline của thao tác, không phải bằng chứng chắc chắn dữ liệu chưa được ghi hoặc xử lý. Trong Spring Kafka, cần xác định timeout ở tầng nào, phân biệt request timeout với delivery timeout, poll interval và timeout của downstream. Khi kết hợp quan sát client/broker, retry có giới hạn, idempotent producer, idempotent consumer và quy trình đối chiếu offset/event id, hệ thống có thể phục hồi network interruption mà vẫn kiểm soát được duplicate và backlog.

