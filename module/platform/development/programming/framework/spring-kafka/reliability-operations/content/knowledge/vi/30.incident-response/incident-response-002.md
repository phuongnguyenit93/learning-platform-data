# Runbook khi producer send thất bại

## Mục tiêu và phạm vi

Runbook này dùng khi một ứng dụng Java/Spring Kafka không gửi được record tới Kafka, gửi chậm bất thường hoặc nhận lỗi khi chờ kết quả gửi. Mục tiêu xử lý là xác định đúng tầng gây lỗi, khôi phục luồng gửi và bảo toàn sự kiện theo yêu cầu nghiệp vụ.

Phạm vi gồm lời gọi **KafkaTemplate.send()**, Kafka producer client, kết nối tới broker, quyền truy cập topic và phản hồi xác nhận từ broker. Runbook không xử lý lỗi consumer sau khi record đã được broker chấp nhận, trừ bước phân biệt hai tình huống này.

Chỉ coi một record đã được gửi thành công khi future/callback hoàn tất thành công theo cấu hình **acks**. Điều đó xác nhận mức ghi mà producer đã yêu cầu; nó không chứng minh consumer đã đọc hoặc xử lý record.

## 1. Phản ứng ban đầu

Khi cảnh báo send failure xuất hiện:

1. Ghi nhận thời điểm bắt đầu, service, môi trường, phiên bản ứng dụng, topic, cluster và số instance bị ảnh hưởng.
2. Xác định lỗi ảnh hưởng một record, một partition, một topic hay toàn bộ producer. So sánh ít nhất một instance đang lỗi với instance khác nếu có.
3. Lưu exception đầy đủ, nguyên nhân gốc, trace/correlation ID, topic, key ở dạng đã che/mã hóa và metadata record. Không đưa payload nhạy cảm, token, mật khẩu hoặc thông tin cá nhân vào log/ticket.
4. Kiểm tra thay đổi vừa triển khai: cấu hình bootstrap server, serializer, TLS/SASL, ACL, topic, kích thước record và phiên bản client.
5. Nếu lỗi bắt đầu ngay sau deploy hoặc thay đổi cấu hình, cân nhắc rollback theo quy trình phát hành đã được phê duyệt. Nếu broker hoặc mạng đang gặp sự cố diện rộng, phối hợp nhóm Kafka/platform trước khi tăng tải bằng retry thủ công.

Không xóa topic, không tạo lại topic, không tắt xác thực/TLS, không hạ acks xuống 0 và không tắt idempotence để làm cảnh báo biến mất. Những thao tác đó có thể che nguyên nhân hoặc làm mất bảo đảm dữ liệu.

## 2. Xác định lỗi xảy ra ở giai đoạn nào

Lời gọi **KafkaTemplate.send()** thường trả về một future để theo dõi kết quả bất đồng bộ. Tuy nhiên, lỗi có thể xuất hiện ngay trong lúc gọi send() hoặc xuất hiện sau đó khi producer giao tiếp với broker.

| Giai đoạn | Dấu hiệu | Hướng kiểm tra |
|---|---|---|
| Trước khi record được đưa vào buffer | send() ném exception ngay; thường gặp lỗi serializer, cấu hình, producer đã đóng, thiếu metadata hoặc không cấp phát được buffer trong thời hạn | Serializer, topic/metadata, max.block.ms, buffer.memory, vòng đời producer |
| Gửi bất đồng bộ | Future hoàn tất exceptionally hoặc callback nhận exception | Broker, network, ACL, authentication, kích thước record, timeout, replication |
| Future thành công nhưng không thấy dữ liệu ở nơi mong đợi | Không có send exception; ứng dụng downstream không nhận record | Cluster/topic đích, partition, consumer group, offset, bộ lọc và thời điểm đọc |

Cần phân biệt các timeout:

- **max.block.ms** giới hạn thời gian producer chờ metadata hoặc chờ chỗ trống trong buffer khi gọi send(). Đây không phải thời hạn broker phải xác nhận record.
- **request.timeout.ms** giới hạn thời gian chờ phản hồi cho một request tới broker.
- **delivery.timeout.ms** giới hạn tổng thời gian một record được giao, bao gồm thời gian chờ batch và các lần retry. Giá trị này phải được cấu hình phù hợp với request.timeout.ms và linger.ms.

Một lỗi timeout có thể xảy ra sau khi broker đã ghi record nhưng producer không nhận được phản hồi. Trong trường hợp đó, gửi lại ở tầng ứng dụng có thể tạo bản ghi trùng nếu hệ thống không có cơ chế idempotency ở cấp nghiệp vụ.

## 3. Bảng chẩn đoán theo triệu chứng

| Triệu chứng / exception thường gặp | Nguyên nhân có thể | Bằng chứng cần kiểm tra | Hành động |
|---|---|---|---|
| SerializationException | Serializer không hỗ trợ kiểu dữ liệu, schema không hợp lệ, dữ liệu null không được xử lý, cấu hình key/value serializer sai | Stack trace tại serializer, kiểu record, schema/version, thay đổi DTO | Sửa dữ liệu hoặc serializer; kiểm thử với record lỗi; không retry vô hạn cùng một payload |
| TimeoutException khi gọi send hoặc khi chờ delivery | Không lấy được metadata, broker/network chậm, buffer cạn, request không được xác nhận kịp | Giai đoạn phát sinh, max.block.ms, delivery.timeout.ms, request latency, buffer available, broker health | Xác định timeout ở client hay broker; xử lý nguyên nhân trước khi điều chỉnh timeout |
| NotEnoughReplicasException hoặc NotEnoughReplicasAfterAppendException | ISR nhỏ hơn yêu cầu của min.insync.replicas khi dùng acks=all | ISR, trạng thái replica, broker mất kết nối, cấu hình topic | Khôi phục replica/broker và ISR; giữ nguyên chính sách durability trong lúc điều tra |
| TopicAuthorizationException hoặc ClusterAuthorizationException | Principal thiếu ACL cần thiết hoặc dùng sai principal | Principal thực tế, ACL topic/cluster, môi trường và secret được mount | Cấp đúng quyền tối thiểu qua quy trình quản trị; xác minh principal mà ứng dụng đang dùng |
| AuthenticationException, lỗi SSL/SASL hoặc handshake | Credential hết hạn/sai, truststore/keystore, cơ chế SASL hoặc chứng thư không khớp | Log handshake đã loại bỏ secret, thời hạn chứng thư, cơ chế auth, cấu hình client/broker | Khôi phục credential/chứng thư và cấu hình tương ứng; không ghi secret vào log |
| RecordTooLargeException | Record hoặc batch vượt giới hạn ở producer, broker hay topic | Kích thước serialized record, max.request.size, message.max.bytes, max.message.bytes | Giảm payload hoặc điều chỉnh giới hạn đồng bộ ở các tầng theo chuẩn vận hành |
| BufferExhaustedException hoặc timeout khi chờ buffer | Producer tạo record nhanh hơn tốc độ gửi, broker/network chậm, buffer quá nhỏ hoặc thread bị nghẽn | buffer-available-bytes, bufferpool-wait-time, waiting-threads, send rate và request latency | Giảm tốc độ phát sinh hoặc backpressure; kiểm tra broker/network; chỉ tăng buffer sau khi đánh giá heap và tải |
| ProducerFencedException | Một producer khác dùng cùng transactional ID và fence producer hiện tại | Transactional ID, số replica ứng dụng, vòng đời transaction | Đảm bảo transactional ID duy nhất cho từng producer logic và khởi tạo transaction đúng cách |
| OutOfOrderSequenceException hoặc lỗi sequence/producer epoch | Lỗi trạng thái producer idempotent/transactional, cấu hình hoặc vòng đời producer bất thường | Kafka client log, transactional ID, retry/in-flight config, lịch sử restart | Giữ nguyên log; xử lý theo hướng dẫn Kafka client/version và kiểm tra cấu hình idempotence/transaction |
| UnknownTopicOrPartitionException hoặc InvalidTopicException | Sai tên topic, topic chưa được tạo, metadata chưa cập nhật hoặc tên topic không hợp lệ | Topic thực tế trên cluster, bootstrap server, environment, quyền describe | Xác minh đúng cluster và topic; tạo topic qua quy trình quản trị nếu được yêu cầu |
| NetworkException, DisconnectException hoặc connection timeout | DNS, route, firewall, broker listener, connection limit hoặc broker restart | DNS từ pod, kết nối tới từng broker, broker logs, network policy | Khôi phục đường mạng/listener; kiểm tra toàn bộ broker được metadata quảng bá, không chỉ bootstrap server |

Tên exception và cách Spring Kafka bọc exception có thể khác theo phiên bản. Luôn xem cause chain đầy đủ thay vì chỉ phân loại theo tên exception ngoài cùng.

## 4. Quy trình điều tra

### 4.1. Thu thập log phía ứng dụng

Tìm log trong khoảng thời gian cảnh báo, bao gồm cả log trước exception đầu tiên:

~~~bash
kubectl logs -n <namespace> deploy/<service> --since=15m \
  | grep -Ei 'Kafka|producer|SerializationException|TimeoutException|AuthorizationException|AuthenticationException|RecordTooLarge'
~~~

Nếu workload có nhiều pod, kiểm tra từng pod bị ảnh hưởng và đối chiếu thời điểm restart:

~~~bash
kubectl get pods -n <namespace> -l app=<service> -o wide
kubectl describe pod -n <namespace> <pod-name>
~~~

Ghi lại các trường có sẵn: timestamp, service/pod, topic, partition (nếu đã có), key đã che, trace ID, exception class, cause chain và thời gian từ lúc gửi tới lúc thất bại. Không bật log payload hoặc log wire protocol ở production nếu chưa đánh giá tác động và dữ liệu nhạy cảm.

### 4.2. Kiểm tra cluster và topic

Xác nhận ứng dụng đang trỏ tới đúng cluster của môi trường. Một bootstrap server truy cập được không đảm bảo mọi broker được quảng bá trong metadata đều truy cập được từ pod.

Dùng công cụ Kafka phù hợp với phiên bản và quyền của môi trường:

~~~bash
kafka-topics.sh --bootstrap-server <bootstrap-server> \
  --describe --topic <topic-name>
~~~

Kiểm tra leader, partition, replica và ISR. Nếu có lỗi authorization, nhờ người có quyền kiểm tra ACL:

~~~bash
kafka-acls.sh --bootstrap-server <bootstrap-server> \
  --list --topic <topic-name>
~~~

Kiểm tra cấu hình topic khi cần:

~~~bash
kafka-configs.sh --bootstrap-server <bootstrap-server> \
  --entity-type topics --entity-name <topic-name> --describe
~~~

Các lệnh trên có thể cần cấu hình client properties để xác thực TLS/SASL. Không đưa mật khẩu hoặc nội dung credential trực tiếp vào lịch sử shell hay ticket. Chỉ chạy lệnh thay đổi cấu hình khi đã có phê duyệt vận hành.

### 4.3. Kiểm tra metrics producer và broker

Đối chiếu thời điểm lỗi với metrics producer. Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và hệ thống export, nhưng các tín hiệu cần tìm gồm:

- **record-send-rate / record-send-total**: tốc độ và tổng số record được gửi.
- **record-error-rate / record-error-total**: lỗi gửi.
- **record-retry-rate / record-retry-total**: số lần retry.
- **request-latency-avg / request-latency-max**: độ trễ request tới broker.
- **record-queue-time-avg**: thời gian record nằm trong queue/batch phía producer.
- **buffer-available-bytes, bufferpool-wait-time-total và waiting-threads**: áp lực buffer.
- Broker side: request handler/network processor saturation, request queue, under-replicated partitions, offline partitions, ISR shrink/expand, disk latency và tình trạng broker.

Diễn giải theo tương quan:

- Error và retry tăng cùng request latency: ưu tiên kiểm tra broker, network và replication.
- Buffer available giảm về gần 0, buffer wait tăng: producer bị backpressure hoặc không giao record đủ nhanh.
- Lỗi chỉ xuất hiện ở một topic: kiểm tra ACL, cấu hình topic, leader và kích thước record của topic đó.
- Lỗi đồng thời trên nhiều topic/instance: ưu tiên bootstrap/listener, DNS/network, authentication hoặc cluster health.
- Send success bình thường nhưng consumer không thấy record: chuyển điều tra sang cluster/topic đích, partition và consumer; không tiếp tục xử lý như producer send failure.

### 4.4. Kiểm tra cấu hình và thay đổi gần nhất

Đối chiếu cấu hình đang chạy với cấu hình đã biết là tốt:

- bootstrap.servers và listener mà pod có thể truy cập.
- Key/value serializer, schema registry (nếu có), subject và schema compatibility.
- Security protocol, SASL mechanism, principal, truststore/keystore và thời hạn chứng thư.
- acks, idempotence, retries, delivery.timeout.ms, request.timeout.ms, linger.ms.
- max.block.ms, buffer.memory và max.request.size.
- Topic tồn tại, ACL đúng, giới hạn record/batch và min.insync.replicas.

Kiểm tra config thực tế sau khi Spring Boot đã bind property; không chỉ dựa vào file YAML trong repository. Secret manager, environment variable, ConfigMap hoặc Helm values có thể ghi đè cấu hình.

## 5. Mẫu xử lý lỗi trong Spring Kafka

Với Spring Kafka 3.x, KafkaTemplate.send() trả về CompletableFuture<SendResult<K, V>>. Đăng ký whenComplete để ghi nhận kết quả bất đồng bộ. Với Spring Kafka 2.x, kiểu future có thể là ListenableFuture; điều chỉnh mẫu theo đúng phiên bản của ứng dụng.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

class OrderPublisher {
    private static final Logger log = LoggerFactory.getLogger(OrderPublisher.class);
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(String topic, String key, OrderEvent event, String traceId) {
        try {
            CompletableFuture<SendResult<String, OrderEvent>> future =
                    kafkaTemplate.send(topic, key, event);

            future.whenComplete((result, exception) -> {
                if (exception != null) {
                    Throwable cause = unwrapCompletionException(exception);
                    // Chỉ log metadata an toàn; không log payload hoặc secret.
                    log.error("Kafka send failed: topic={}, traceId={}",
                            topic, traceId, cause);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.debug("Kafka send acknowledged: topic={}, partition={}, offset={}",
                        metadata.topic(), metadata.partition(), metadata.offset());
            });
        } catch (RuntimeException exception) {
            // Bắt lỗi phát sinh đồng bộ trước khi future được trả về.
            log.error("Kafka send could not be started: topic={}, traceId={}",
                    topic, traceId, exception);
            throw exception;
        }
    }

    private static Throwable unwrapCompletionException(Throwable exception) {
        Throwable current = exception;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

OrderEvent là kiểu dữ liệu ví dụ của ứng dụng. Đoạn mã minh họa việc quan sát kết quả gửi; cần bổ sung xử lý nghiệp vụ phù hợp với hệ thống. Không gọi get() hoặc join() trên request thread chỉ để chờ gửi xong, vì việc đó có thể làm nghẽn thread và tăng latency.

Callback có thể chạy trên thread của producer hoặc thread hoàn tất future. Giữ callback ngắn, tránh thực hiện thao tác blocking hoặc gọi lại cùng luồng gửi theo cách gây đệ quy. Chuyển công việc phục hồi nặng sang cơ chế nền có giới hạn và có giám sát.

## 6. Phục hồi an toàn

Chọn hành động theo nguyên nhân đã xác định:

- **Lỗi dữ liệu/serializer:** cách ly record lỗi theo cơ chế nghiệp vụ, sửa schema hoặc dữ liệu nguồn rồi phát lại có kiểm soát. Retry nguyên trạng một record không serialize được sẽ tiếp tục thất bại.
- **Lỗi authentication/ACL:** khôi phục principal, credential, chứng thư hoặc quyền cần thiết. Sau khi sửa, xác nhận producer tạo kết nối và gửi được record kiểm thử đã được phép.
- **Lỗi network/broker/replication:** phối hợp nhóm phụ trách cluster, khôi phục broker/route/ISR và theo dõi retry tự động. Tránh tạo thêm tải bằng cách restart đồng loạt hoặc replay toàn bộ backlog cùng lúc.
- **Lỗi buffer/backpressure:** giảm tốc độ phát sinh, áp dụng backpressure ở upstream hoặc tăng năng lực xử lý sau khi đo heap, request latency và throughput. Tăng buffer.memory đơn thuần có thể làm tăng áp lực heap mà không giải quyết được broker chậm.
- **Lỗi kích thước:** giảm payload, chuyển dữ liệu lớn sang object storage và chỉ gửi tham chiếu nếu kiến trúc cho phép; hoặc điều chỉnh giới hạn đồng bộ ở producer, broker và topic sau khi đánh giá tác động.
- **Lỗi transactional/fencing:** kiểm tra transactional ID, quyền sở hữu producer và ranh giới transaction. Không tạo nhiều instance dùng chung một transactional ID ngoài thiết kế.

### 6.1. Retry và nguy cơ record trùng

Ưu tiên retry của Kafka producer cùng idempotence khi phù hợp với cấu hình và phiên bản client. Idempotence giúp producer tránh duplicate do retry protocol trong một producer session; nó không tự động loại bỏ duplicate do ứng dụng gửi lại cùng event sau timeout, restart hoặc xử lý lại từ nguồn khác.

Nếu phải retry ở tầng ứng dụng:

1. Dùng event ID ổn định để nhận diện cùng một sự kiện qua các lần thử.
2. Xác định chính sách backoff có giới hạn, jitter và giới hạn số lần thử; tránh vòng lặp retry nóng.
3. Giữ nguyên key nếu key quyết định partition/thứ tự nghiệp vụ.
4. Đảm bảo nơi nhận có thể deduplicate hoặc xử lý idempotent.
5. Lưu trạng thái retry bền vững nếu sự kiện không được phép mất khi tiến trình restart.
6. Theo dõi số record đang chờ, tuổi record cũ nhất, tốc độ retry và số record bị đưa vào trạng thái lỗi cuối cùng.

Không dùng DLQ của consumer như một nơi thay thế mặc định cho producer send failure. Nếu broker không nhận được record, producer không thể giả định rằng gửi record đó vào cùng Kafka cluster qua một topic lỗi sẽ thành công. Với yêu cầu không mất dữ liệu, cân nhắc transactional outbox hoặc kho retry bền vững ở upstream, cùng quy trình phát lại có kiểm soát.

### 6.2. Khi timeout tạo kết quả không chắc chắn

Nếu producer hết thời gian chờ, cần xác định record có thể đã được broker ghi nhưng ACK bị mất hay không. Trước khi replay:

- Tra cứu event ID hoặc business key ở phía downstream nếu hệ thống có khả năng này.
- Kiểm tra offset/record bằng công cụ được phép và đúng cluster/topic/partition.
- Nếu không thể xác định chắc chắn, xử lý theo chính sách at-least-once và bảo đảm consumer deduplicate.
- Ghi nhận trạng thái không chắc chắn để tránh retry song song nhiều lần.

Không kết luận record chắc chắn bị mất chỉ dựa trên TimeoutException.

## 7. Cấu hình reliability cần rà soát

Ví dụ dưới đây minh họa các thuộc tính quan trọng trong Spring Boot. Các giá trị timeout chỉ là ví dụ để bắt đầu thảo luận; hãy điều chỉnh theo SLO, độ trễ broker, kích thước batch và thời gian phục hồi cho phép.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        linger.ms: 5
~~~

Lưu ý khi rà soát:

- acks=all yêu cầu broker xác nhận theo ISR hiện tại; kết hợp với min.insync.replicas ở topic/broker để xác định mức durability mong muốn.
- enable.idempotence=true giúp retry ở producer không tạo duplicate do retry protocol trong phạm vi bảo đảm của Kafka. Xác nhận các cấu hình acks, retries và max.in.flight.requests.per.connection tương thích với phiên bản client.
- delivery.timeout.ms nên lớn hơn hoặc bằng tổng request.timeout.ms và linger.ms; đặt quá thấp có thể làm record hết hạn trước khi retry đủ thời gian.
- max.block.ms ảnh hưởng thời gian gọi send() có thể bị chặn khi đợi metadata/buffer. Chọn theo latency budget của luồng gọi.
- buffer.memory và max.request.size phải phù hợp với heap, kích thước record/batch và giới hạn broker/topic.
- Nếu dùng transaction, rà soát transactional.id, transaction timeout và cách tạo producer theo instance. Không áp dụng cấu hình transactional cho producer thường nếu ứng dụng không dùng transaction.

Không thay đổi đồng thời nhiều thông số trong incident. Mỗi thay đổi cần có giả thuyết, phạm vi áp dụng, người phê duyệt, cách đo kết quả và phương án rollback.

## 8. Xác nhận khôi phục

Chỉ đóng incident khi đã kiểm tra được các điều kiện phù hợp với mức độ ảnh hưởng:

- Producer tạo kết nối tới đúng cluster và gửi thành công record kiểm thử được cho phép.
- Future/callback hoàn tất thành công; metadata topic/partition/offset hợp lệ khi acks yêu cầu xác nhận.
- Error rate và retry rate trở về ngưỡng bình thường; request latency và buffer wait không còn tăng bất thường.
- Broker/topic có leader và ISR phù hợp; không còn offline partition hoặc lỗi replication liên quan.
- Backlog/retry store (nếu có) đang giảm theo tốc độ kiểm soát được; không có record quá hạn chưa xử lý.
- Downstream xác nhận record được nhận theo quy trình nghiệp vụ; kiểm tra duplicate nếu đã có timeout hoặc replay.
- Alert đã hết và không tái xuất hiện trong khoảng quan sát theo quy định vận hành.

Trong biên bản incident, ghi rõ timeline, phạm vi ảnh hưởng, nguyên nhân gốc đã xác nhận (hoặc ghi chưa xác định), số record thành công/thất bại/đang chờ, thay đổi đã thực hiện, nguy cơ duplicate hoặc mất dữ liệu còn lại và hành động theo dõi tiếp theo.

## 9. Checklist thao tác nhanh

- [ ] Xác định lỗi xảy ra đồng bộ trong send() hay bất đồng bộ trong future/callback.
- [ ] Ghi exception đầy đủ và cause chain; bảo vệ payload, credential và dữ liệu cá nhân.
- [ ] Xác nhận đúng bootstrap server, cluster, topic, principal và pod bị ảnh hưởng.
- [ ] Kiểm tra serializer/schema, ACL/authentication, kích thước record và trạng thái topic/ISR.
- [ ] Đối chiếu error/retry rate, request latency, buffer availability và broker health.
- [ ] Khôi phục nguyên nhân gốc; giữ idempotence và durability theo yêu cầu nghiệp vụ.
- [ ] Đánh giá khả năng record đã được ghi trước timeout trước khi replay.
- [ ] Xác nhận send thành công, backlog được xử lý, downstream nhận đúng và alert ổn định.
- [ ] Ghi lại nguyên nhân, phạm vi ảnh hưởng, thao tác phục hồi và rủi ro còn lại.

