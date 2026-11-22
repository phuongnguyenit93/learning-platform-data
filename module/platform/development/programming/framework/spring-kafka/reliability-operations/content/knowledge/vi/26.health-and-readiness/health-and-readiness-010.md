# DLT producer không gửi được

Trong Spring Kafka, Dead Letter Topic (DLT) là nơi lưu những records mà consumer không thể xử lý theo policy đã cấu hình. Error handler có thể retry record nhiều lần, rồi gọi `DeadLetterPublishingRecoverer` để publish record sang DLT. Nhưng **gọi recoverer không đồng nghĩa record đã được lưu an toàn vào DLT**: producer có thể gặp lỗi serialization, thiếu quyền ghi, topic/partition không hợp lệ, broker unavailable, timeout hoặc transaction rollback.

Nếu DLT producer không gửi được mà ứng dụng vẫn coi record nguồn đã recovery thành công, record có thể bị bỏ qua ở source topic trong khi bản sao DLT không tồn tại. Đây là failure mode nguy hiểm vì dashboard consumer lag có thể tiếp tục giảm, nhưng dữ liệu cần điều tra hoặc replay đã biến mất khỏi luồng chính.

Bài học này giải thích cách Spring Kafka xử lý DLT publish failures, cách cấu hình để lỗi gửi DLT được phản ánh ngược về error handler, cách đưa tình trạng DLT producer vào health/readiness, và cách vận hành khi DLT path không còn đáng tin cậy.

## 1. DLT producer nằm ở đâu trong error-handling flow?

Một consumer listener có thể ném exception khi xử lý record. Spring Kafka error handler áp dụng retry/backoff; khi hết retry hoặc exception được phân loại non-retryable, recoverer được gọi.

~~~mermaid
flowchart TD
    A["ConsumerRecord từ source topic"] --> B["Listener xử lý"]
    B -->|Thành công| C["Ack / commit theo container"]
    B -->|Exception| D["DefaultErrorHandler"]
    D --> E{"Còn retry?"}
    E -->|Có| F["Backoff rồi retry record"]
    F --> B
    E -->|Không| G["DeadLetterPublishingRecoverer"]
    G --> H["KafkaTemplate / DLT producer"]
    H --> I{"Broker acknowledge thành công?"}
    I -->|Có| J["Recovery hoàn tất"]
    J --> K["Source offset được xác nhận theo policy"]
    I -->|Không| L["Recovery failure"]
    L --> M["Exception quay lại error-handling flow"]
    M --> N["Record chưa được coi là recovered"]
~~~

Điều quan trọng là DLT publish là **một thao tác I/O độc lập**. Listener đã thất bại; recoverer cần ghi record tới đích phục hồi. Chỉ khi publish outcome được xác nhận theo cấu hình và recovery handler trả về thành công thì container mới có thể tiếp tục commit source progress theo policy.

Nếu send được thực hiện bất đồng bộ mà kết quả chưa được kiểm tra, ứng dụng có thể nhầm lẫn giữa “đã gửi yêu cầu publish” và “broker đã acknowledge record”.

## 2. Vì sao DLT publish failure đặc biệt nguy hiểm?

Giả sử record tại `orders-3@1842` bị lỗi business processing. Error handler đã hết retry và gọi DLT recoverer.

~~~text
Source record: orders partition 3 offset 1842
       |
       v
Listener throws InvalidOrderException
       |
       v
Retry exhausted
       |
       v
DLT producer sends to orders.DLT
       |
       +-- Send succeeds -> record can be recovered
       |
       +-- Send fails but failure is ignored
              |
              v
          Recoverer returns normally
              |
              v
          Source offset may advance
              |
              v
          Original record is no longer redelivered
          and no DLT copy exists
~~~

Nếu recovery được xem là thành công trong khi DLT send thất bại, hệ thống có thể mất khả năng phục hồi record. Hậu quả:

- Business event không được xử lý.
- DLT không có bản ghi để operator điều tra.
- Source consumer group có thể commit offset đi qua record.
- Consumer lag giảm, tạo cảm giác pipeline đã khỏe.
- Việc replay bằng DLT workflow không thể thực hiện vì record không tồn tại.
- Audit trail và incident reconstruction bị thiếu dữ liệu.

Vì vậy, **DLT producer là một phần của reliability path**, không phải một tiện ích logging phụ.

## 3. DeadLetterPublishingRecoverer sử dụng KafkaTemplate

Spring Kafka cung cấp `DeadLetterPublishingRecoverer` để publish record lỗi tới một topic đích. Recoverer sử dụng `KafkaTemplate`/`KafkaOperations` đã được cung cấp trong constructor hoặc resolver.

Ví dụ cơ bản:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

Khi dùng recoverer mặc định, Spring Kafka thường tạo destination topic bằng cách nối hậu tố `.DLT` vào source topic và giữ partition number của record nguồn. Ví dụ:

~~~text
source: orders partition 3 offset 1842
destination: orders.DLT partition 3
~~~

Đây là convention mặc định phổ biến; ứng dụng có thể cấu hình destination resolver để dùng topic/partition khác.

**Phải bảo đảm destination tồn tại và có partition tương thích.** Nếu source topic có 12 partitions mà DLT chỉ có 3 partitions, cố gửi record source partition 8 sang DLT partition 8 có thể thất bại. Topic creation, ACL và partition count cần được kiểm tra trước khi đưa listener vào production.

## 4. Đừng nhầm send request với send acknowledgement

`KafkaTemplate.send()` là bất đồng bộ. Nó trả về một future cho biết kết quả send sau khi producer nhận response từ broker hoặc gặp lỗi.

~~~java
CompletableFuture<SendResult<Object, Object>> future =
        kafkaTemplate.send("orders.DLT", key, value);
~~~

Chỉ việc gọi `send()` thành công không chứng minh record đã được broker lưu. Những failure có thể xảy ra sau khi method trả về:

- Broker không acknowledge trước timeout.
- Network connection bị reset.
- Topic hoặc partition không tồn tại.
- Authorization bị từ chối.
- Serializer ném exception.
- Record vượt giới hạn kích thước.
- Producer bị fencing hoặc transaction abort.
- Broker không đủ replicas theo `acks` và `min.insync.replicas`.

Vì vậy, khi DLT publish là điều kiện để đánh dấu record nguồn đã recovery, phải có cơ chế **quan sát kết quả future và chuyển send failure thành recovery failure**.

## 5. Cấu hình recoverer để send failure không bị bỏ qua

`DeadLetterPublishingRecoverer` có cấu hình `failIfSendResultIsError` để quyết định có ném exception khi send result thất bại hay không. Khi cần bảo đảm DLT send phải thành công trước khi recovery được coi là hoàn tất, hãy bật hành vi fail-on-send-error theo API của phiên bản Spring Kafka đang dùng.

Ví dụ:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    recoverer.setFailIfSendResultIsError(true);

    return recoverer;
}
~~~

Khi cấu hình này được bật, send failure được phản ánh bằng exception từ recoverer thay vì chỉ log rồi coi như đã recovery. Error handler có thể nhận biết recovery thất bại và áp dụng policy tương ứng.

Hãy kiểm tra default của đúng Spring Kafka version đang chạy; đừng dựa vào một giá trị mặc định ghi nhớ từ version khác. Trong hệ thống quan trọng, cấu hình rõ ràng và có integration test cho tình huống DLT broker unavailable sẽ dễ kiểm soát hơn.

## 6. Thời gian chờ kết quả send

Recoverer có thể cần chờ send result trong một khoảng thời gian hữu hạn. Spring Kafka cung cấp cấu hình thời gian chờ send result trên `DeadLetterPublishingRecoverer` ở các phiên bản hỗ trợ, gồm `setWaitForSendResultTimeout` và `setTimeoutBuffer`.

Ví dụ minh họa:

~~~java
recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(20));
~~~

Tên API và overload có thể khác theo version; hãy kiểm tra dependency đã pin.

Một timeout quá ngắn có thể khiến recovery bị coi là thất bại dù broker vẫn có thể acknowledge muộn. Timeout quá dài giữ consumer/error-handling thread chờ lâu, có thể kéo dài processing và làm tăng lag. Hãy chọn timeout theo producer `delivery.timeout.ms`, network latency, broker SLA và tổng ngân sách retry.

Không đặt timeout vô hạn. Nếu producer send bị treo, hệ thống cần một giới hạn để có thể phát hiện và chuyển sang incident handling.

## 7. Destination resolver và partition mapping

Recoverer có thể tùy biến destination resolver để quyết định DLT topic và partition:

~~~java
@Bean
DeadLetterPublishingRecoverer recoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
            (record, exception) -> {
                String dltTopic = record.topic() + ".DLT";
                return new TopicPartition(
                    dltTopic,
                    record.partition()
                );
            };

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate, resolver);

    recoverer.setFailIfSendResultIsError(true);
    return recoverer;
}
~~~

Đoạn code minh họa giữ nguyên partition. Có thể route theo exception type hoặc business domain, nhưng phải tránh logic destination không xác định hoặc đưa record tới một partition không tồn tại.

Nếu resolver trả về `null`, behavior phụ thuộc cấu hình/API của recoverer; hãy quyết định rõ record có được bỏ qua, xử lý theo fallback hay phải coi là recovery failure. Với dữ liệu quan trọng, không để một resolver lỗi âm thầm biến thành “recovery thành công”.

## 8. DLT topic cần có đủ partitions

Nếu giữ nguyên partition từ source, DLT cần có partition tương ứng. Một cách đơn giản là giữ cùng số partitions:

~~~text
orders topic:      12 partitions
orders.DLT topic:  12 partitions
~~~

Lý do:

- Partition mapping mặc định dễ dự đoán.
- Original partition có thể được giữ trong metadata.
- DLT replay có thể giữ một phần ordering theo source partition.
- Operator có thể tìm record bằng source coordinates.

Nếu chủ đích route mọi records vào một DLT partition, phải hiểu rằng ordering giữa nhiều source partitions không thể được khôi phục chỉ bằng offset. DLT partition count và partition resolver là một quyết định kiến trúc.

Tạo DLT bằng infrastructure-as-code hoặc topic provisioning job. Không phụ thuộc broker auto topic creation trong production nếu cần kiểm soát replication factor, retention, ACL và partition count.

## 9. Cấu hình DefaultErrorHandler

Một ví dụ non-transactional listener container:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    return handler;
}
~~~

`FixedBackOff(1_000L, 2L)` minh họa hai lần retry sau lần xử lý đầu tiên, với khoảng chờ một giây giữa các lần. Cấu hình thực tế cần dựa trên loại exception và dependency behavior.

Gắn handler vào factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Khi retry exhausted, handler gọi recoverer. Nếu recoverer trả về bình thường, record được coi là recovered theo policy handler. Nếu recoverer ném exception do DLT send thất bại, record **không được coi là đã gửi DLT thành công**; error handler có thể tiếp tục xử lý recovery failure theo semantics của version/configuration.

Đừng bắt exception từ recoverer rồi return bình thường trong custom error handler. Làm như vậy có thể biến failure thành success giả và cho phép source offset tiến lên.

## 10. Recovery failure khác listener failure

Có hai lỗi riêng biệt:

1. **Listener failure:** business method không xử lý được record.
2. **Recovery failure:** sau khi retry, hệ thống không thể publish record lỗi tới DLT.

Ví dụ:

~~~text
Record A
  |
  +-- Listener attempt 1 -> DB timeout
  +-- Listener attempt 2 -> DB timeout
  +-- Listener attempt 3 -> DB timeout
  |
  +-- DLT publish -> authorization failure
~~~

Lỗi cuối không phải một lần business listener thất bại khác. Nó là failure của cơ chế bảo toàn record sau khi listener đã thất bại.

Log và metrics cần phân biệt:

~~~text
event=listener_processing_failed
event=dlt_publish_attempted
event=dlt_publish_failed
event=recovery_failed
~~~

Nếu tất cả chỉ được ghi dưới một nhãn “consumer error”, operator sẽ khó biết cần sửa business logic, DLT ACL hay broker connectivity.

## 11. Điều gì xảy ra với source offset khi DLT publish thất bại?

Trong non-transactional flow, khi recoverer ném exception thay vì return bình thường, error handler không nên coi record là recovered. Tùy ack mode, seek/retry và recovery policy, record có thể được redeliver hoặc xử lý lại sau đó.

Mô hình mong muốn:

~~~text
Listener fails
    |
Retry exhausted
    |
DLT send fails
    |
Recoverer throws
    |
Recovery not completed
    |
Source record remains eligible for retry/redelivery
~~~

Không nên phát biểu đơn giản rằng “offset chắc chắn không bao giờ commit” nếu chưa xét cấu hình container, ack mode, error handler, transactional mode và version. Điều cần bảo đảm là **recovery failure được truyền về control flow** để source record không bị đánh dấu recovered chỉ vì send request đã được tạo.

Hãy test chính xác behavior của ứng dụng: DLT broker tạm ngắt, listener ném lỗi, recoverer fail, broker phục hồi, rồi xác nhận record nguồn được xử lý lại hoặc recovery được tiếp tục theo policy.

## 12. DLT send có thể thành công nhưng acknowledgement bị mất

Một failure khó hơn: producer gửi record, broker đã append, nhưng response bị mất do network timeout. Producer/future báo lỗi trong khi record có thể đã tồn tại trong DLT.

~~~text
Attempt 1:
  Broker appends DLT record
  Ack response lost
  Producer reports timeout

Attempt 2:
  Source record is retried
  DLT record is sent again
  Broker acknowledges
~~~

Khi source record được giao lại và recoverer gửi lần nữa, DLT có thể có **hai bản sao** của cùng business event.

Đây là lý do DLT consumer nên có idempotency dựa trên business event ID hoặc original source coordinates. DLT producer idempotence có thể giảm duplicate do retry nội bộ của producer trong session, nhưng không thay thế deduplication khi ứng dụng thực hiện một lần send mới sau redelivery/restart.

Nếu cần exactly-once giữa source offset và DLT output, phải thiết kế transactional recovery phù hợp. Không giả định non-transactional send và source offset commit tự atomic.

## 13. DLT producer serialization failure

DLT có thể giữ record value sau khi deserialize hoặc raw bytes nếu lỗi xảy ra trước khi payload được deserialize. Điều này làm serializer của DLT producer trở thành một phần quan trọng của recovery.

Ví dụ source listener dùng JSON deserializer, nhưng DLT producer chỉ được cấu hình serializer cho DTO. Nếu record value là `byte[]` do deserialization failure, producer serializer có thể không xử lý đúng kiểu đó.

Với nhiều loại payload, có thể cấu hình nhiều KafkaTemplates hoặc serializer phù hợp. Spring Kafka hỗ trợ recoverer dùng template resolver theo kiểu key/value trong những phiên bản tương ứng.

Thiết kế cần tính đến:

- Payload deserialized thành DTO.
- Payload là raw `byte[]` khi deserialization thất bại.
- Key có kiểu khác value.
- Tombstone record có `value=null`.
- Header và exception metadata có serializer/size constraints.
- DLT consumer cần hiểu schema/version của payload.

Không loại bỏ payload gốc chỉ vì deserialize thất bại. Nếu mục tiêu DLT là forensic/replay, raw bytes và metadata gốc có thể cần được giữ lại.

## 14. Ví dụ chọn KafkaTemplate theo payload type

Một ý tưởng là cung cấp template cho DTO và template cho raw bytes:

~~~java
Map<Class<?>, KafkaOperations<?, ?>> templates = new LinkedHashMap<>();
templates.put(OrderCreated.class, orderTemplate);
templates.put(byte[].class, bytesTemplate);
templates.put(Object.class, fallbackTemplate);

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            record -> selectTemplate(record, templates)
        );
~~~

Đây là pseudocode mô tả lựa chọn template; constructor và resolver overload cần đối chiếu Spring Kafka version. Không copy nguyên ví dụ nếu type inference/constructor trong dependency không khớp.

Điều quan trọng là template được chọn phải có key/value serializers tương thích với record thực tế. Cần integration test cho payload hợp lệ, raw bytes, tombstone và header metadata.

## 15. Broker, topic và ACL failures

Các nguyên nhân thường làm DLT producer không gửi được:

| Failure | Triệu chứng có thể gặp | Kiểm tra |
|---|---|---|
| Broker unavailable | Timeout, disconnect | Cluster health, bootstrap, network |
| Topic không tồn tại | Metadata/unknown topic error | Topic provisioning, auto-create policy |
| Partition không hợp lệ | Invalid partition | DLT partition count, resolver |
| Thiếu WRITE ACL | Authorization exception | Principal, topic ACL |
| Thiếu DESCRIBE ACL | Metadata/authorization issue | ACL cho topic và cluster theo policy |
| Leader unavailable | Not leader/leader unavailable | Partition leader, broker state |
| ISR không đủ | Not enough replicas | Replication, min.insync.replicas |
| Message quá lớn | RecordTooLarge | Broker/topic/producer max message size |
| Serializer lỗi | SerializationException | Serializer config và runtime type |
| Network/TLS/auth lỗi | SSL/SASL/timeout | Certificates, credentials, truststore |
| Quota/throttle | Request delay/throttle | Client/broker quota |
| Transaction fencing | ProducerFencedException | Transactional ID ownership/lifecycle |
| Buffer pressure | BufferExhausted/timeout | Producer buffer, downstream broker health |

Không xử lý mọi lỗi bằng cách tăng timeout. Authorization, serialization và invalid partition là lỗi cấu hình/dữ liệu cần sửa; retry vô hạn chỉ giữ source partition và làm backlog tăng.

## 16. DLT producer có cần idempotence không?

Producer idempotence giúp Kafka producer chống duplicate do retry nội bộ của producer theo protocol trong một producer session và điều kiện cấu hình phù hợp. Nó hữu ích nhưng không giải quyết mọi duplicate DLT.

Các trường hợp duplicate vẫn có thể xuất hiện:

- Source record được giao lại và recoverer tạo send mới.
- Ứng dụng restart sau khi broker append nhưng trước khi source offset commit.
- Send acknowledgement bị mất.
- DLT replay hoặc operator republish cùng event.
- Hai consumer instances cùng xử lý một logical operation do lỗi coordination.

Vì vậy, DLT record nên giữ một business event ID hoặc source identity ổn định. DLT consumer và công cụ replay nên hỗ trợ deduplicate hoặc yêu cầu operator xác nhận khi replay.

Không dùng current DLT offset làm idempotency key cho logical source event, vì mỗi lần republish có thể nhận offset mới.

## 17. Transactional recovery

Nếu listener container dùng Kafka transactions, recovery flow có thể được cấu hình để gửi DLT record và commit source offset theo một transaction boundary phù hợp, thường thông qua after-rollback processor và transactional KafkaTemplate.

Mục tiêu là:

~~~text
Kafka transaction
   |
   +-- Send record to DLT
   |
   +-- Send source consumer offset to transaction
   |
   +-- Commit both
~~~

Nếu transaction commit thất bại, cả DLT output và source offset trong transaction được rollback theo semantics Kafka transaction. Điều này giảm cửa sổ một bên thành công, một bên thất bại.

Tuy nhiên, transactional recovery đòi hỏi:

- Producer factory có transaction configuration phù hợp.
- Transactional IDs duy nhất và không xung đột giữa instances.
- Container transaction manager/error recovery được cấu hình đúng.
- DLT publishing sử dụng template phù hợp với transaction.
- Consumer downstream dùng isolation level phù hợp nếu chỉ muốn thấy committed records.
- Retry/recovery processor được thiết lập đúng cho Spring Kafka version.

Không trộn transactional recoverer với một template non-transactional rồi giả định source offset và DLT output atomic. Cũng không xem Kafka transaction bảo vệ DB side effect bên ngoài Kafka.

## 18. DLT publish failure và Health

Một service có thể đang xử lý records bình thường, nhưng khi gặp một record lỗi thì DLT producer không thể gửi. Đây là **degraded recovery capability**.

Health cần trả lời những câu hỏi khác nhau:

- Process còn sống không?
- Listener container có running không?
- Consumer group còn poll/được assign không?
- Business dependencies có đủ capacity không?
- DLT producer có thể publish vào DLT topic không?
- Error handler có thể bảo toàn record khi recovery cần thiết không?

Một `HealthIndicator` chỉ kiểm tra KafkaTemplate bean tồn tại là chưa đủ. Producer object có thể được tạo thành công nhưng broker unreachable hoặc principal thiếu ACL.

Health state có thể được mô hình hóa:

| State | Ý nghĩa |
|---|---|
| UP | DLT path đã được xác nhận healthy theo policy |
| UNKNOWN | Chưa có bằng chứng đủ mới hoặc probe chưa chạy |
| DEGRADED | Có send failures hoặc DLT path đang gặp sự cố |
| DOWN | Recovery path không thể đáp ứng yêu cầu và service không nên nhận thêm workload |

Đây là phân loại application-level; Spring Boot Health API có thể dùng `UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN` hoặc status custom theo cấu hình. Cần mapping status thành HTTP status rõ ràng.

## 19. Health check không nên gửi thử DLT record thật tùy tiện

Một health check chạy mỗi vài giây và gửi record test vào production DLT có thể tạo noise, làm consumer DLT nhận event giả hoặc kích hoạt alert.

Các cách quan sát an toàn hơn:

1. Theo dõi producer send success/failure metrics.
2. Theo dõi exception từ recoverer và DLT send result.
3. Kiểm tra cluster metadata và topic description bằng quyền phù hợp.
4. Kiểm tra ACL qua provisioning/deployment validation.
5. Dùng synthetic probe topic riêng nếu cần end-to-end send/consume test.
6. Thực hiện probe có kiểm soát, với marker riêng và cleanup/retention rõ ràng.
7. Không dùng health endpoint làm nơi thực hiện synchronous send có thể block lâu.

Một metadata check không chứng minh write ACL hay serializer path chắc chắn hoạt động. Ngược lại, một send thật tới DLT topic là bằng chứng mạnh hơn nhưng có side effect. Chọn probe theo mức assurance cần thiết.

## 20. Readiness khác liveness

Nếu DLT producer bị lỗi, có nên restart pod không? Thông thường **không nên làm liveness fail chỉ vì DLT broker tạm thời unavailable**. Restart liên tục không sửa được ACL, broker outage hoặc serializer configuration; nó có thể gây rebalance và làm hệ thống tệ hơn.

Readiness có thể phù hợp hơn nếu ứng dụng không thể an toàn tiếp tục consume records mới vì recovery path không sẵn sàng. Khi pod được đánh dấu not-ready, cần nhớ Kubernetes readiness chủ yếu ảnh hưởng Service routing; nó **không tự dừng Kafka listener container**. Muốn ngừng intake phải có cơ chế pause/stop được thiết kế riêng.

| Probe | Vai trò | DLT failure policy thường hợp lý |
|---|---|---|
| Liveness | Process có bị deadlock/crash không? | Không fail chỉ vì broker DLT tạm mất |
| Readiness | Pod có đủ khả năng nhận workload theo contract không? | Có thể DEGRADED/OUT_OF_SERVICE nếu không thể bảo toàn recovery |
| Startup | App đã hoàn tất khởi tạo chưa? | Dùng cho startup dependencies/time budget |
| Business health | Workflow có đạt SLO không? | Theo dõi DLT failure rate, backlog, error handler |

Nếu source listener vẫn có thể xử lý bình thường và DLT chỉ cần khi gặp một số lỗi hiếm, policy readiness có thể khác với một consumer mà mọi record lỗi đều bắt buộc phải được lưu DLT. Đây là quyết định theo business risk.

## 21. Readiness không tự pause consumer

Một lỗi triển khai thường gặp là đánh dấu pod not-ready rồi nghĩ Kafka consumer sẽ dừng. Kafka consumers không phụ thuộc Kubernetes Service routing; chúng tự join consumer group và poll broker.

Do đó, nếu policy yêu cầu ngừng nhận records khi DLT recovery path không hoạt động:

~~~text
DLT send failures detected
       |
       v
Set application recovery state = DEGRADED
       |
       v
Backpressure controller requests listener pause
       |
       v
Wait for pause effective / drain in-flight work
       |
       v
Keep consumer group polling while paused
       |
       v
DLT path restored and verified
       |
       v
Resume under controlled policy
~~~

Pause container giúp tạm dừng dispatch records nhưng vẫn duy trì poll loop theo cơ chế Spring Kafka. Nó không hủy record đang xử lý và không thay thế retry/error handling của record hiện tại.

Nếu chỉ đánh dấu readiness false mà không pause/stop listener, consumer vẫn có thể tiếp tục nhận và xử lý records.

## 22. Tránh tự động pause vì một lỗi send thoáng qua

Một timeout đơn lẻ có thể do network jitter hoặc broker failover ngắn. Nếu mỗi failure lập tức pause tất cả consumers, hệ thống có thể flapping và tạo backlog lớn.

Một control policy có thể dùng:

- Ngưỡng số DLT send failures trong cửa sổ.
- Consecutive failures hoặc error ratio.
- Thời gian dependency degraded.
- Circuit breaker state.
- Minimum pause duration và recovery stability window.
- Manual override cho maintenance.

Ví dụ:

~~~text
Pause intake khi:
  DLT send failures >= 3 lần liên tiếp
  OR failure ratio > 20% trong 1 phút

Resume khi:
  DLT probe thành công
  AND producer send failures = 0 trong 2 phút
  AND operator maintenance lock đã được clear
~~~

Đây là logic minh họa, không phải default Spring Kafka. Threshold phải được chọn theo volume và SLO. Với traffic thấp, ratio có thể không ổn định; với traffic cao, một failure rate nhỏ cũng có thể tương ứng nhiều records.

## 23. Quan sát DLT producer metrics

Theo dõi metrics của Kafka producer và application recovery flow:

| Metric/tín hiệu | Câu hỏi |
|---|---|
| DLT send attempts | Bao nhiêu lần recoverer thử publish? |
| DLT send success | Bao nhiêu records được broker acknowledge? |
| DLT send failure | Bao nhiêu sends thất bại? |
| DLT send latency | Broker acknowledge mất bao lâu? |
| Producer record-error-rate | Producer gặp lỗi gửi record ở mức nào? |
| Request latency/throttle | Broker/network có phản hồi chậm không? |
| Buffer available / queue time | Producer có bị buffer pressure không? |
| Recoverer exceptions | Recovery flow bị fail bao nhiêu lần? |
| Source lag | Source records có bị giữ lại không? |
| DLT topic ingress/lag | DLT consumer có xử lý kịp không? |
| DLT retention age | Record lỗi có nguy cơ hết retention không? |

Tên metrics Kafka client cụ thể phụ thuộc Kafka client version và metrics binder. Hãy kiểm tra registry thực tế thay vì hardcode tên metric từ một cluster khác.

Không gắn event ID hoặc offset vào metric labels. Dùng logs/traces để truy vết từng record; metrics chỉ cần listener/topic/result/exception class hoặc các dimension có cardinality thấp.

## 24. Structured logs cho DLT send outcome

Nên log riêng attempt và kết quả:

~~~text
event=dlt_publish_attempted
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
destination_partition=3
event_id=evt-91fe

event=dlt_publish_acknowledged
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
destination_partition=3
destination_offset=91
event_id=evt-91fe
~~~

Khi lỗi:

~~~text
event=dlt_publish_failed
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
error_type=TopicAuthorizationException
recovery_result=not_recovered
~~~

Các fields quan trọng:

- Source coordinates.
- Destination topic/partition.
- Event ID hoặc operation ID được phép log.
- Recoverer attempt/result.
- Exception type.
- Consumer group/listener/instance.
- Retry count hoặc recovery stage nếu có metadata.

Không log payload thô hoặc header chứa token. Với serializer failure, log type mong đợi và type thực tế; không dump toàn bộ object nếu nó chứa dữ liệu nhạy cảm.

## 25. DLT producer serialization và nhiều KafkaTemplates

Nếu ứng dụng dùng nhiều loại payload, một KafkaTemplate với serializer duy nhất có thể không phù hợp cho mọi records. Đặc biệt, khi listener gặp deserialization exception, recoverer có thể cần publish raw bytes.

Một số thiết kế:

- Template chuyên DTO JSON.
- Template hỗ trợ `byte[]` cho raw payload.
- Template hỗ trợ key serializer tương ứng.
- Resolver chọn template theo runtime type của key/value.
- Fallback template được kiểm soát cho null/tombstone.

Nếu template resolver chọn sai serializer, DLT send sẽ fail trước khi broker nhận record. Đây là lý do cần test DLT với cả record deserialize thành công và record malformed.

Tombstone record có value null; template/serializer phải hỗ trợ null value đúng semantics compacted topic. Không tự biến null thành chuỗi "null" nếu mục tiêu là giữ tombstone.

## 26. Header metadata và kích thước DLT record

Recoverer có thể thêm headers mô tả original topic, partition, offset, consumer group và exception. Những headers này hữu ích cho forensic/replay nhưng cũng làm record lớn hơn.

Một số lỗi:

- Exception message/stack trace quá dài.
- Header lặp lại nhiều lần sau retry/DLT forwarding.
- Tổng record size vượt giới hạn broker/topic/producer.
- Serializer không hỗ trợ header value encoding mong muốn.
- Một số headers chứa thông tin nội bộ hoặc dữ liệu nhạy cảm.

Cần kiểm tra cấu hình header functions/retention theo version. Nếu truncate stack trace, vẫn giữ exception class, original coordinates và một reference tới log/trace có quyền truy cập. Không xóa original coordinates nếu chúng cần cho audit.

## 27. DLT publish và source offset trong non-transactional flow

Trong non-transactional flow, DLT publish và source offset commit là hai thao tác độc lập. Có hai failure windows:

~~~text
A. DLT send thất bại
   -> recoverer throws
   -> source record cần được retry/recovered lại theo policy

B. DLT send thành công
   -> process crash trước source offset commit
   -> source record được redeliver
   -> DLT có thể nhận bản sao thứ hai
~~~

Do đó, non-transactional DLT flow cần:

- Fail send phải được propagate.
- DLT consumer có idempotency/dedup.
- Original source coordinates và event ID được giữ.
- Source offset commit semantics được test.
- Operator có thể phân biệt retry send và duplicate DLT records.

Transactional recovery có thể giảm failure window giữa output DLT và input offset, nhưng cần cấu hình đúng transaction manager/template/processor và không mở rộng bảo đảm sang database.

## 28. Retry khi chính DLT producer gặp lỗi

Một câu hỏi vận hành là: nếu listener đã hết retry nhưng DLT send thất bại, retry cái gì?

Có hai lớp retry:

1. **Business listener retry:** thử lại record vì business processing failure.
2. **Recovery/DLT publish retry:** thử lại thao tác publish record lỗi sang DLT.

Không phải mọi cấu hình error handler tự động retry recovery vô hạn. Hành vi sau khi recoverer ném exception phụ thuộc handler, retry state, backoff và version. Cần quyết định policy rõ:

- Thử lại DLT publish với backoff hữu hạn.
- Giữ source record để redelivery khi recovery failure.
- Pause intake khi DLT path outage kéo dài.
- Alert operator nếu recovery không thành công sau budget.
- Không discard record hoặc commit source offset chỉ vì retry budget đã hết.

Nếu dùng một retry state cho listener và recovery, hãy kiểm tra `resetStateOnRecoveryFailure` và các behavior của version đang chạy. Không tự viết policy chỉ dựa trên giả định.

## 29. DLT publish failure không nên dẫn tới infinite retry storm

Nếu DLT topic bị thiếu ACL, mọi record lỗi đều không thể publish. Retry DLT send vô hạn trên cùng partition có thể giữ consumer thread và làm backlog không kiểm soát.

Cần một recovery budget:

- Backoff có giới hạn hoặc exponential backoff.
- Phân biệt lỗi transient với lỗi cấu hình permanent.
- Circuit breaker cho DLT producer path.
- Pause intake khi điều kiện bảo toàn record không còn.
- Alert ngay cho owner DLT/topic ACL.
- Giữ record ở source cho tới khi recovery có thể tiếp tục.
- Không chuyển record sang một fallback DLT chưa được kiểm chứng.

Một fallback topic có thể giúp giảm phụ thuộc vào DLT chính, nhưng chỉ có giá trị nếu fallback cluster/topic/ACL/serializer/retention được provision và kiểm thử trước. Nếu fallback dùng cùng broker/ACL failure domain, nó không tạo thêm độ tin cậy.

## 30. Kiểm tra DLT path trước khi deploy

Một pre-deployment checklist nên xác minh:

1. DLT topics đã được tạo.
2. Partition count tương thích với source/resolver.
3. Replication factor và min ISR đáp ứng yêu cầu.
4. Producer principal có WRITE/appropriate ACL.
5. Consumer/operator principal có READ/DESCRIBE nếu cần.
6. Serializer hỗ trợ payload types và raw bytes.
7. Message size limits tương thích với DLT headers/payload.
8. TLS/SASL credentials và trust chain hợp lệ.
9. Producer delivery timeout và recoverer wait timeout có quan hệ hợp lý.
10. Metrics/logs được xuất và alert có owner.
11. DLT retention đủ dài cho incident response.
12. Replay procedure đã được kiểm soát và có idempotency.

Provisioning thành công chỉ xác nhận config; integration test gửi một record đại diện mới xác nhận được end-to-end write path trong môi trường test.

## 31. Kiểm thử DLT producer failure

Một bộ integration test nên kiểm tra các trường hợp:

| Scenario | Kết quả mong đợi |
|---|---|
| DLT send thành công | Recoverer hoàn tất và source progress theo policy |
| DLT broker unavailable | Recoverer báo lỗi; record không bị coi là recovered |
| Thiếu WRITE ACL | Failure được phản ánh, có alert/log |
| DLT topic không tồn tại | Recovery failure rõ ràng |
| DLT partition không tồn tại | Không silently drop |
| Serializer không hỗ trợ DTO | Recovery failure |
| Raw byte[] sau deserialization failure | DLT giữ được payload gốc |
| Broker ack timeout | Hệ thống xử lý khả năng send outcome không chắc chắn |
| DLT send thành công nhưng source offset commit fail | Duplicate DLT được dedup/điều tra |
| DLT publish transaction rollback | DLT record và offset tuân theo transaction semantics |
| DLT consumer replay | Business idempotency được bảo vệ |

Test quan trọng nhất: làm cho DLT send thất bại có kiểm soát, rồi xác nhận error handler **không đánh dấu recovery thành công**. Không chỉ assert log có error; cần kiểm tra source offset/redelivery behavior và DLT record count.

Đây là thiết kế kiểm thử cho người học, không phải kết quả test của ứng dụng trong bài viết.

## 32. Runbook: DLT producer không gửi được

Khi nhận alert `dlt_publish_failed`:

1. Xác định source topic, partition, offset, event ID và consumer group.
2. Xác định destination DLT topic/partition mà resolver chọn.
3. Đọc exception root cause: authorization, metadata, serialization, timeout, broker, message size hay transaction.
4. Kiểm tra Kafka cluster/broker availability và leader của destination partition.
5. Kiểm tra topic tồn tại, partition count và replication/ISR.
6. Kiểm tra producer principal, WRITE ACL, TLS/SASL credentials.
7. Kiểm tra serializer cho payload runtime type và raw bytes/tombstone.
8. Kiểm tra producer delivery timeout, buffer pressure và recoverer wait timeout.
9. Xác nhận `failIfSendResultIsError` đang được bật theo policy.
10. Xem source record có còn eligible để retry/redelivery không.
11. Khắc phục DLT path và thực hiện một test publish được kiểm soát.
12. Cho recovery tiếp tục theo error-handler policy; không reset offsets bừa bãi.
13. Theo dõi DLT success, source lag, retry count và duplicate records.
14. Ghi lại incident với original source coordinates.

Nếu lỗi là ACL, tăng retry/backoff không sửa được nguyên nhân. Nếu broker unavailable, restart từng consumer pod không khôi phục broker.

## 33. Runbook: readiness chuyển DEGRADED do DLT path

1. Xác định health component nào báo degraded và evidence nào kích hoạt nó.
2. Kiểm tra đây là send failure thực tế hay probe/metadata check thất bại.
3. Xác định service còn có thể xử lý records không cần recovery hay không.
4. Kiểm tra số records đang chờ recovery và source partitions.
5. Nếu policy yêu cầu bảo toàn mọi failed record, yêu cầu pause intake theo control plane.
6. Đợi pause effective và xem in-flight listener operations.
7. Sửa DLT topic, ACL, serializer hoặc broker connectivity.
8. Xác nhận DLT send thành công trong test path an toàn.
9. Clear degraded reason theo control policy.
10. Resume intake có kiểm soát.
11. Theo dõi source lag và DLT throughput cho tới khi bắt kịp.
12. Giữ liveness ổn định; không restart loop chỉ vì DLT dependency tạm thời mất.

Readiness false không tự dừng Kafka consumer. Nếu muốn ngừng nhận records, cần điều khiển listener container rõ ràng.

## 34. Runbook: source offset đã tiến nhưng không có DLT record

Đây là tình huống cần xử lý như incident dữ liệu:

1. Xác nhận source topic/partition/offset và consumer group.
2. Kiểm tra committed offset và thời điểm commit.
3. Tìm recoverer logs quanh thời điểm xử lý.
4. Kiểm tra `failIfSendResultIsError` và send result wait configuration.
5. Kiểm tra DLT topic, partition, retention và compaction.
6. Kiểm tra destination resolver có route tới topic khác không.
7. Kiểm tra broker transaction commit/rollback nếu transactional recovery.
8. Tìm DLT record bằng event ID và original coordinates ở mọi DLT partitions.
9. Kiểm tra có duplicate/replay hoặc manual forwarding không.
10. Nếu record thực sự bị mất, xác định có thể khôi phục từ source retention, archive hoặc producer outbox không.
11. Replay theo quy trình có idempotency và audit.
12. Sửa configuration/test để recovery failure không bị coi là success.

Không xóa marker idempotency hoặc reset group offset hàng loạt trước khi xác định business side effects đã xảy ra chưa.

## 35. Những sai lầm thường gặp

### Chỉ log send failure nhưng vẫn return success

Nếu recoverer không propagate send error, error handler có thể coi record đã recovery và source offset tiến lên. Log error không đủ để bảo vệ record.

### Tin rằng KafkaTemplate.send() trả về là broker đã lưu

Send là asynchronous; phải kiểm tra future outcome hoặc dùng recoverer configuration chờ và fail đúng cách.

### DLT topic ít partitions hơn source

Default resolver giữ partition source có thể gửi tới partition không tồn tại. Provision partition count và resolver cùng nhau.

### Chỉ cấu hình JSON serializer

Deserialization failure có thể để lại raw bytes. DLT producer phải hỗ trợ payload types thực tế.

### Retry DLT publish vô hạn

Có thể giữ consumer thread, tăng lag và gây storm. Dùng retry budget, alert và backpressure.

### Đánh dấu liveness DOWN khi broker DLT tạm mất

Kubernetes có thể restart loop mà không sửa được dependency failure. Liveness và readiness có mục tiêu khác nhau.

### Cho rằng readiness false sẽ dừng Kafka listener

Consumer group hoạt động độc lập với Service routing. Muốn dừng intake cần pause/stop control.

### Không xử lý ambiguous send outcome

Broker có thể append record nhưng ack bị mất; retry có thể tạo duplicate. Giữ event ID/original coordinates và deduplicate.

### Cho rằng Kafka transaction bảo vệ database

Kafka transaction chỉ atomic các Kafka records/offset thuộc transaction. DB side effect cần transaction/idempotency riêng.

## 36. Checklist triển khai DLT producer reliability

- [ ] Dùng `DeadLetterPublishingRecoverer` với KafkaTemplate đúng serializer.
- [ ] Cấu hình destination topic/partition rõ ràng.
- [ ] DLT partitions tương thích với source partition mapping.
- [ ] `failIfSendResultIsError` được bật theo policy bảo toàn record.
- [ ] Send-result timeout phù hợp producer delivery timeout và broker SLA.
- [ ] Recoverer send exception được propagate về error handler.
- [ ] Recovery failure không bị biến thành success giả.
- [ ] Source offset behavior được kiểm tra cho AckMode và transaction thực tế.
- [ ] Có hỗ trợ DTO, raw byte[], key và tombstone nếu cần.
- [ ] DLT topic/ACL/replication/retention được provision trước deploy.
- [ ] Có metrics/logs riêng cho DLT attempts, success, failure và latency.
- [ ] Readiness phản ánh khả năng recovery theo business policy.
- [ ] Liveness không fail chỉ vì DLT broker outage tạm thời.
- [ ] Nếu pause intake, có control plane và resume policy rõ.
- [ ] DLT consumer có idempotency cho duplicate/replay.
- [ ] Có integration test khi DLT send fail, ack timeout và transaction rollback.
- [ ] Có runbook cho ACL, broker, topic, partition, serializer và source-offset anomalies.

## 37. Nguồn tham khảo

- [Spring Kafka Reference — Dead Letter Publishing Recoverer](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka API — DeadLetterPublishingRecoverer](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Boot Reference — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)

**Kết luận:** DLT producer không gửi được là một failure của recovery path và phải được xử lý như một vấn đề bảo toàn dữ liệu. Cấu hình `DeadLetterPublishingRecoverer` để send failure được phản ánh thành recovery failure, xác nhận kết quả publish trước khi source record được coi là recovered, và kiểm soát topic/partition/serializer/ACL/timeout. Đưa trạng thái DLT path vào readiness khi business policy yêu cầu, nhưng không dùng liveness để restart loop vì broker outage; readiness false cũng không tự dừng Kafka consumers. Cuối cùng, giữ source coordinates và event ID, kiểm thử failure windows, và có runbook để phục hồi mà không làm mất record hoặc tạo duplicate ngoài kiểm soát.
