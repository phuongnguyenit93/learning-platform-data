# ACL cho DLT trong Spring Kafka

Dead Letter Topic (DLT) lưu những Kafka records không thể xử lý thành công sau retry hoặc được phân loại là lỗi không thể retry. DLT giúp giữ lại dữ liệu để điều tra, quarantine và replay. Khi Kafka cluster bật authorization, việc gửi record sang DLT là một thao tác publish mới và phải được cấp quyền rõ ràng.

Một consumer có thể đọc topic nguồn bình thường nhưng không có quyền ghi vào DLT. Khi đó listener thất bại, error handler gọi DeadLetterPublishingRecoverer, KafkaTemplate gửi record nhưng broker từ chối vì ACL. Nếu ứng dụng không xử lý đúng send failure, source record có thể bị coi là recovered trong khi bản DLT chưa được lưu thành công.

**ACL cho DLT** cần được thiết kế theo vai trò: source consumer, DLT publisher, DLT consumer, replay operator và administrator. Mỗi principal chỉ được cấp quyền trên đúng topic, consumer group và transactional ID mà nó cần. Không cấp quyền rộng trên toàn cluster chỉ để làm cho DLT hoạt động.

Bài học này giải thích Kafka ACL resources và operations, principal mapping, lệnh kafka-acls, Spring Kafka DeadLetterPublishingRecoverer, retry topics, transactional producer, pre-provision topic, authorization failures và quy trình kiểm tra production.

## 1. Vì sao DLT cần ACL riêng?

Giả sử service orders đọc topic orders.events. Khi một record không xử lý được, recoverer gửi nó sang orders.events.DLT.

~~~text
Kafka topic: orders.events
       |
       v
orders-service consumer
       |
       v
@KafkaListener
       |
       +--> xử lý thành công
       |
       +--> exception
                |
                v
          DefaultErrorHandler
                |
                +--> retry
                |
                +--> hết retry / non-retryable
                         |
                         v
                DeadLetterPublishingRecoverer
                         |
                         v
                   KafkaTemplate
                         |
                         v
                orders.events.DLT
~~~

Có ít nhất hai thao tác Kafka độc lập:

1. Consumer đọc record từ topic nguồn.
2. Producer ghi record mới vào DLT.

Quyền READ trên orders.events **không tự cấp quyền WRITE trên orders.events.DLT**. ACL được đánh giá theo principal, resource và operation của từng request.

Một listener có thể xử lý business records bình thường trong nhiều ngày rồi chỉ gặp lỗi khi cần DLT. Nếu ACL chưa được cấp, lỗi authorization chỉ xuất hiện đúng lúc recovery. Vì vậy, quyền DLT cần được chuẩn bị và kiểm tra trước production.

## 2. Những principal và vai trò thường có

Không nên mặc định mọi thành phần dùng cùng một principal. Một deployment có thể tách credentials theo nhiệm vụ:

| Principal / role | Nhiệm vụ | Quyền chính |
|---|---|---|
| orders-source-consumer | Đọc topic nguồn và xử lý record | READ source topic, READ consumer group |
| orders-dlt-publisher | Gửi record lỗi vào DLT | WRITE DLT topic |
| orders-dlt-consumer | Đọc và điều tra DLT | READ DLT topic, READ DLT consumer group |
| orders-replay-operator | Đọc DLT và publish record replay | READ DLT, READ group, WRITE destination topic |
| kafka-admin | Provision topic, ACL và cấu hình | Quyền quản trị được kiểm soát riêng |

Nếu source consumer và DLT publisher dùng cùng Kafka principal, principal đó cần cả quyền đọc nguồn và ghi DLT. Đây là cấu hình đơn giản thường gặp. Tách publisher credentials có thể giảm phạm vi quyền và giúp audit rõ hơn.

**Principal là danh tính broker xác thực được**, không nhất thiết là tên Spring bean, listener ID hay Kubernetes service account. ACL phải khớp principal mà broker nhìn thấy sau SASL/mTLS authentication và principal mapping.

## 3. ACL resource và operation của Kafka

Kafka authorization áp dụng trên các loại resource. Những loại liên quan nhiều nhất đến DLT:

| Resource type | Đại diện cho | Ví dụ |
|---|---|---|
| Topic | Một topic hoặc nhóm topic theo pattern | orders.events.DLT |
| Group | Consumer group | orders-dlt-investigation |
| Cluster | Tài nguyên cấp cluster | IdempotentWrite hoặc thao tác cluster |
| TransactionalId | Producer transactional ID | orders-dlt-publisher- |
| DelegationToken | Delegation token nếu dùng | token identity |

Các operations thường gặp:

| Operation | Ý nghĩa khái quát |
|---|---|
| READ | Đọc record hoặc sử dụng group theo resource tương ứng |
| WRITE | Ghi record vào topic hoặc sử dụng transactional ID theo resource |
| DESCRIBE | Đọc metadata resource |
| CREATE | Tạo resource |
| DELETE | Xóa resource |
| ALTER | Thay đổi resource |
| DESCRIBE_CONFIGS | Đọc cấu hình |
| ALTER_CONFIGS | Sửa cấu hình |
| IDEMPOTENT_WRITE | Quyền liên quan tới idempotent producer trên cluster |
| CLUSTER_ACTION | Một số thao tác nội bộ/cluster |
| ALL | Tất cả operations được áp dụng cho resource |

Quyền được kiểm tra theo resource type. READ trên Topic khác READ trên Group; không thể dùng ACL topic để thay thế quyền consumer group.

Kafka authorizer có các quan hệ operation implication, chẳng hạn một số quyền đọc/ghi cũng bao hàm khả năng describe theo semantics của broker. Khi triển khai, hãy kiểm tra ma trận authorization của đúng Kafka version và authorizer thay vì cấp mọi operation theo thói quen.

## 4. Quyền tối thiểu cho DLT publisher

Nếu service orders dùng một principal để đọc source và publish DLT, các quyền tối thiểu điển hình là:

- READ trên topic nguồn orders.events.
- READ trên consumer group orders-service.
- WRITE trên topic đích orders.events.DLT.
- Quyền bổ sung nếu producer sử dụng transactions hoặc idempotent authorization theo broker policy.

Sơ đồ:

~~~text
Principal: User:orders-service

Topic orders.events
  READ

Group orders-service
  READ

Topic orders.events.DLT
  WRITE
~~~

Publisher không cần DELETE trên DLT để gửi record. Nó cũng không cần ALTER_CONFIGS chỉ vì sử dụng KafkaTemplate.

Nếu publisher có thể ghi vào nhiều DLT topics, hãy liệt kê đúng tập destination. Không cấp WRITE trên toàn bộ topic namespace nếu service chỉ gửi vào một số DLT cụ thể.

## 5. Quyền cho DLT consumer

Một service điều tra hoặc quarantine DLT cần:

- READ trên DLT topic.
- READ trên consumer group mà nó sử dụng.
- Metadata access theo authorization behavior của broker.

Ví dụ:

~~~text
Principal: User:orders-dlt-investigator

Topic orders.events.DLT
  READ

Group orders-dlt-investigation
  READ
~~~

Quyền READ trên topic cho phép consumer fetch records theo ACL; quyền READ trên group cho phép consumer tham gia group và quản lý offsets theo consumer group protocol.

Nếu operator dùng Kafka UI hoặc AdminClient để xem topic metadata, offsets hay cấu hình, có thể cần thêm DESCRIBE hoặc quyền quản trị tương ứng. Không cấp quyền ALTER hoặc DELETE cho một consumer chỉ có nhiệm vụ đọc và quarantine records.

## 6. Source consumer, retry topic và DLT có quyền riêng

Một flow dùng retry topics có thể cần nhiều quyền hơn DLT đơn giản:

~~~text
orders.events
     |
     +--> source consumer
     |
     +--> retry publish
              |
              v
       orders.events-retry
              |
              +--> retry consumer
                       |
                       +--> success
                       |
                       +--> exhausted
                                |
                                v
                         orders.events.DLT
~~~

Với non-blocking retry, ứng dụng có thể vừa consume source/retry topics vừa publish sang retry/DLT destinations. ACL cần được lập theo topology:

| Topic/resource | Operation thường cần |
|---|---|
| orders.events | READ |
| orders.events-retry | READ và/hoặc WRITE tùy vai trò |
| orders.events-retry-5000 | READ và/hoặc WRITE tùy topology |
| orders.events.DLT | WRITE từ publisher; READ từ DLT consumer |
| orders-service group | READ |
| retry consumer group | READ |
| DLT investigation group | READ |

Không suy ra quyền chỉ từ tên topic. Hãy liệt kê từng listener endpoint, retry publisher, recoverer, group ID và destination resolver để biết principal nào thực sự cần operation nào.

Nếu source consumer dùng một principal cho cả source và retry/DLT publishing, quyền có thể được gộp. Nếu tách producer factory, hãy cấp WRITE cho principal producer tương ứng.

## 7. Cấp ACL bằng kafka-acls.sh

Kafka cung cấp công cụ kafka-acls.sh để thêm, liệt kê và xóa ACL. Lệnh dưới đây minh họa một DLT publisher principal.

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.events.DLT
~~~

Nếu cần cấp quyền READ cho source topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Read \
  --topic orders.events
~~~

Quyền consumer group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Read \
  --group orders-service
~~~

Trong các ví dụ, admin-client.properties chứa cấu hình kết nối và xác thực của tài khoản quản trị có quyền quản lý ACL. Không dùng credentials quản trị trong ứng dụng orders-service.

## 8. Cấp ACL cho DLT consumer

Ví dụ principal chỉ đọc DLT:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-investigator \
  --operation Read \
  --topic orders.events.DLT
~~~

Và group riêng:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-investigator \
  --operation Read \
  --group orders-dlt-investigation
~~~

Principal này không cần WRITE vào source hoặc DLT chỉ để xem records. Nếu công cụ điều tra có chức năng replay, hãy xem replay là một vai trò riêng và cấp WRITE vào topic đích mà operator được phép phát lại.

Một nguyên tắc hữu ích là **read-only investigator** và **replay operator** có quyền khác nhau. Điều tra record không đồng nghĩa được phép phát lại nó vào production topic.

## 9. Xem lại ACL đã cấp

Sau khi thêm ACL, liệt kê quyền trên một topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --topic orders.events.DLT
~~~

Liệt kê quyền của consumer group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --group orders-dlt-investigation
~~~

Liệt kê ACL toàn cluster có thể trả về rất nhiều kết quả; chỉ dùng khi cần audit phạm vi rộng và có quyền phù hợp.

Kết quả ACL nên được so sánh với một bảng desired state đã review. Việc thấy một principal có WRITE không đủ để biết nó có đang được cấp quyền quá rộng trên prefix hay có DENY ACL nào xung đột.

## 10. Literal resource và prefixed resource patterns

Kafka ACL có thể áp dụng cho một resource literal hoặc một prefix pattern.

**Literal** chỉ áp dụng cho resource có tên chính xác:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.events.DLT \
  --resource-pattern-type literal
~~~

**Prefixed** áp dụng cho các resource có tên bắt đầu bằng prefix được chỉ định:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders. \
  --resource-pattern-type prefixed
~~~

Ví dụ prefix orders. có thể bao phủ orders.events, orders.events.DLT và các topics khác cùng prefix. Điều này thuận tiện khi có nhiều DLT topics nhưng cũng mở rộng phạm vi quyền.

Dùng literal cho DLT cố định thường dễ audit nhất. Chỉ dùng prefixed ACL khi naming convention được quản trị và tất cả topics trong prefix thực sự thuộc cùng trust boundary.

## 11. DENY ACL và allowlist

Kafka ACL hỗ trợ allow và deny entries. Khi có các ACL chồng lấn, DENY có thể làm request bị từ chối dù principal có một ALLOW khác phù hợp.

~~~text
ALLOW User:orders-service WRITE Topic:orders.events.DLT
DENY  User:orders-service WRITE Topic:orders.events.DLT
~~~

Trong một policy có DENY phù hợp, operator không nên chỉ thấy dòng ALLOW rồi kết luận quyền hoạt động. Phải xem toàn bộ ACL áp dụng cho principal, host và resource pattern.

Thiết kế khuyến nghị:

- Bắt đầu từ quyền tối thiểu.
- Dùng principal riêng cho từng service/role.
- Hạn chế wildcard/prefix.
- Chỉ thêm DENY khi có policy cụ thể và hiểu precedence.
- Audit cả ALLOW lẫn DENY.
- Không dùng một DENY rộng khiến service không thể publish DLT trong incident.

Nếu cluster không có ACL phù hợp và policy mặc định cho phép hoặc từ chối, hành vi còn phụ thuộc authorizer configuration. Hãy xác nhận cấu hình broker trước khi giả định "không có ACL" đồng nghĩa với một kết quả cụ thể.

## 12. Pre-create DLT topic thay vì phụ thuộc auto-create

Một lỗi phổ biến là chỉ cấp WRITE cho publisher và mong Kafka tự tạo DLT topic. Việc tạo topic là một thao tác quản trị riêng.

Trong production, nên provision DLT topic trước:

- Số partitions tương thích với destination resolver.
- Replication factor phù hợp với cluster.
- min.insync.replicas theo durability requirement.
- Retention đủ dài cho điều tra/replay.
- Cleanup policy phù hợp với cách sử dụng DLT.
- Quota và storage capacity.
- ACL cho publisher và consumers.

Nếu DeadLetterPublishingRecoverer mặc định giữ partition nguồn khi chọn destination, DLT thường cần số partitions tương ứng hoặc lớn hơn. Nếu DLT có ít partition hơn source, destination resolver có thể chọn partition không tồn tại. Có thể cấu hình resolver trả partition -1 để Kafka producer tự chọn partition khi phù hợp với yêu cầu ordering.

Không cấp CREATE trên toàn cluster cho business consumer chỉ để giải quyết thiếu DLT topic. Hãy để provisioning pipeline hoặc administrator tạo topic và ACL theo change đã review.

## 13. Destination resolver phải khớp ACL

DeadLetterPublishingRecoverer có thể dùng destination resolver để chọn topic/partition đích. Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        -1
                )
        );
~~~

Với source topic orders.events, destination là orders.events.DLT. ACL publisher phải cho phép WRITE trên đúng destination đó.

Nếu resolver chọn theo exception category:

~~~text
orders.events + validation error
    -> orders.validation.DLT

orders.events + database error
    -> orders.infrastructure.DLT
~~~

thì publisher cần WRITE trên cả hai destination. Không cấp WRITE chỉ cho orders.events.DLT rồi quên một nhánh resolver hiếm gặp.

Một số hệ thống có topic routing dựa trên tenant hoặc payload. Tránh tạo topic DLT tùy ý theo input record vì sẽ làm topic governance và ACL trở nên không kiểm soát được. Hãy map vào một tập destination cố định.

## 14. Cấu hình Spring Kafka cho DLT publisher

Ví dụ error handler dùng KafkaTemplate:

~~~java
@Configuration
public class DltConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        recoverer.setFailIfSendResultIsError(true);

        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );
    }
}
~~~

Ví dụ minh họa API Spring Kafka có hỗ trợ setFailIfSendResultIsError. Hãy đối chiếu version của ứng dụng để xác nhận API và timeout/send-result behavior.

Điểm quan trọng là khi Kafka broker từ chối DLT publish, lỗi phải được phản ánh vào recovery path theo policy. Nếu send result error bị bỏ qua, ứng dụng có thể coi recovery hoàn tất và tiến offset nguồn trong khi DLT record không tồn tại.

Không chỉ log một thông báo "sent to DLT" ngay sau khi gọi send. Cần phân biệt request đã được tạo, producer send đã hoàn tất và broker đã xác nhận theo durability policy.

## 15. Cùng principal hay tách riêng DLT publisher credentials?

Có hai cách tổ chức.

**Một principal cho source consumer và DLT producer**

~~~text
User:orders-service
  READ  Topic:orders.events
  READ  Group:orders-service
  WRITE Topic:orders.events.DLT
~~~

Ưu điểm: cấu hình đơn giản, ít producer factories và credentials hơn.

Hạn chế: một service credential có quyền vừa đọc source vừa ghi DLT; nếu bị lộ, phạm vi hành động rộng hơn.

**Principal riêng cho DLT publisher**

~~~text
User:orders-source-consumer
  READ Topic:orders.events
  READ Group:orders-service

User:orders-dlt-publisher
  WRITE Topic:orders.events.DLT
~~~

Cách tách này cần KafkaTemplate/ProducerFactory có credentials riêng cho DLT. Error handler sử dụng đúng template đó. Cần kiểm tra tracing, serializers, transaction settings và security properties của template riêng.

Tách principal có lợi cho audit và least privilege nhưng tăng số cấu hình và secret cần quản lý. Chọn theo threat model, khả năng quản trị credentials và mức độ quan trọng của DLT.

## 16. Cấu hình SASL_SSL và ACL là hai lớp khác nhau

**Authentication** xác định client là ai. **Authorization** quyết định principal đó được phép làm gì.

~~~text
Spring Kafka client
       |
       v
TLS/SASL authentication
       |
       v
Broker xác định principal
       |
       v
Kafka authorizer kiểm tra ACL
       |
       +--> ALLOW
       |
       +--> DENY
~~~

Ví dụ các thuộc tính kết nối:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
~~~

Đây chỉ là một phần cấu hình. JAAS credentials, truststore và những secret khác cần được cấp qua secret manager/environment injection phù hợp; không hard-code password trong source code hoặc commit file cấu hình có secret.

TLS/SASL thành công không có nghĩa ACL cho phép WRITE DLT. Ngược lại, một ACL đúng cũng không giúp client đăng nhập nếu authentication thất bại.

Khi broker log principal khác với ACL principal đã cấp, kiểm tra principal mapping, SASL username, mTLS distinguished name và cấu hình authorizer.

## 17. Phân biệt authorization errors theo loại resource

Một số lỗi thường gặp:

| Exception/error | Khả năng nguyên nhân | Cần kiểm tra |
|---|---|---|
| TopicAuthorizationException | Thiếu quyền trên topic | READ/WRITE/Describe đúng topic |
| GroupAuthorizationException | Thiếu quyền trên consumer group | READ group đúng group.id |
| ClusterAuthorizationException | Thiếu quyền cấp cluster | Operation cluster hoặc thao tác admin |
| TransactionalIdAuthorizationException | Thiếu quyền transactional ID | WRITE trên TransactionalId resource |
| AuthenticationException | Không xác thực được | SASL, TLS, credentials, principal mapping |
| Topic not found/metadata failure | Topic chưa được tạo hoặc metadata không hợp lệ | Provision topic, resolver, bootstrap metadata |
| Invalid partition | Destination partition không tồn tại | DLT partition count/resolver |
| SerializationException | Serializer không hỗ trợ payload DLT | Key/value serializer và raw bytes |

Tên exception cụ thể và cách chúng được wrap có thể khác theo Kafka client/Spring Kafka version. Một lỗi send có thể xuất hiện trong CompletableFuture cause chain thay vì ném ngay tại dòng gọi KafkaTemplate.send.

Không quy mọi lỗi DLT thành "thiếu WRITE ACL". Hãy phân biệt authentication, authorization, metadata, partition, serialization và broker availability.

## 18. Producer idempotence và transactional DLT publisher

Nếu DLT producer dùng idempotence hoặc Kafka transactions, có thể cần ACL bổ sung.

Với **idempotent producer**, broker authorization có thể yêu cầu operation IDEMPOTENT_WRITE trên Cluster resource tùy Kafka version và authorizer policy.

Với **transactional producer**, producer dùng một transactional.id. ACL thường cần WRITE trên TransactionalId resource tương ứng, ngoài quyền WRITE trên các topic mà producer gửi tới. Một số flow còn cần cluster-level idempotent-write authorization.

Ví dụ transactional ID prefix:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-dlt-publisher-
~~~

ACL transactional ID prefix minh họa:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-publisher \
  --operation Write \
  --transactional-id orders-dlt-publisher- \
  --resource-pattern-type prefixed
~~~

Nếu broker yêu cầu cluster-level IDEMPOTENT_WRITE:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-publisher \
  --operation IdempotentWrite \
  --cluster
~~~

Chỉ cấp các quyền này khi producer configuration và broker authorization thực sự cần. Không thêm transactional ID ACL cho producer non-transactional chỉ vì DLT được dùng cùng Spring Kafka.

**Kafka transaction chỉ bao phủ Kafka resources tham gia transaction.** Nó không tự rollback database hoặc HTTP side effects của listener. ACL cho transaction bảo đảm quyền sử dụng giao dịch, không tạo thêm atomicity với hệ thống ngoài Kafka.

## 19. Retry topics cũng cần ACL

Với Spring Kafka non-blocking retries, framework có thể tạo retry topics và publish record sang những topics này trước khi đưa sang DLT.

Ví dụ topology:

~~~text
orders.events
    |
    +--> orders.events-retry-1000
    |
    +--> orders.events-retry-5000
    |
    +--> orders.events.DLT
~~~

Tùy cách cấu hình, ứng dụng có thể cần:

- READ trên source topic.
- WRITE trên retry topics.
- READ trên retry topics.
- WRITE trên DLT.
- READ trên consumer groups của retry listeners.
- READ trên source consumer group.

Nếu retry topics được tạo bằng provisioning/admin process, ứng dụng không cần CREATE cluster-wide chỉ để consume/publish chúng. Cần cấp ACL cho mọi topic thực sự xuất hiện trong topology.

Tên retry topics và cách routing phụ thuộc RetryTopicConfiguration, suffix, attempts và Spring Kafka version. Tạo ACL dựa trên topology đã được xác định, không đoán từ một tên topic mẫu.

## 20. Auto topic creation và quyền CREATE

Một số Kafka clusters tắt auto topic creation để tránh topic phát sinh ngoài quy hoạch. Nếu DLT chưa tồn tại, producer có thể gặp lỗi metadata hoặc authorization tùy broker configuration.

Có hai lựa chọn:

1. **Pre-provision DLT topics:** khuyến nghị cho production.
2. **Cho phép ứng dụng tạo topic:** cần cấp quyền CREATE theo resource/cluster policy và chấp nhận rủi ro quản trị.

Pre-provision giúp kiểm soát:

- Partition count.
- Replication factor.
- min.insync.replicas.
- Retention.
- Cleanup policy.
- Quota.
- ACL.
- Monitoring và ownership.

Một business service thường không cần quyền CREATE hoặc DELETE trên cluster để gửi DLT. Tách provisioning role khỏi runtime producer là cách least privilege rõ ràng hơn.

Nếu DLT topic được tạo sau khi service start, kiểm tra metadata refresh và startup ordering để tránh failure ban đầu bị hiểu nhầm là listener data errors.

## 21. ACL cho replay operator

Replay record từ DLT về source topic là một thao tác có thể kích hoạt business side effects lần nữa. Vì vậy replay operator cần quyền khác với DLT investigator.

Một role replay có thể cần:

- READ trên DLT topic.
- READ trên group dùng để đọc DLT nếu replay qua consumer.
- WRITE trên source/replay destination topic.
- Quyền bổ sung nếu dùng transactions.
- Quyền truy cập công cụ/audit theo chính sách nội bộ.

~~~text
User:orders-dlt-investigator
  READ Topic:orders.events.DLT
  READ Group:orders-dlt-investigation

User:orders-replay-operator
  READ  Topic:orders.events.DLT
  READ  Group:orders-replay
  WRITE Topic:orders.events
~~~

Không cấp WRITE source topic cho mọi người có thể đọc DLT. Replay cần quy trình approval/audit, idempotency và xác minh side effects trước khi phát lại.

Nếu replay sang một topic trung gian, chỉ cấp WRITE vào topic đó. Một replay processor có thể là service riêng với principal riêng, thay vì chia sẻ credentials với DLT investigation UI.

## 22. Cấu hình Kafka ACL trên KRaft và cluster cũ

Cơ chế authorizer phụ thuộc Kafka deployment:

- Kafka chạy KRaft thường dùng StandardAuthorizer.
- Các cluster ZooKeeper-based cũ có thể dùng ZooKeeper-based authorizer.
- Managed Kafka service có thể cung cấp authorization layer và công cụ quản trị riêng.
- Principal mapping có thể thay đổi danh tính từ SASL/mTLS trước khi authorizer so khớp ACL.

Ví dụ cấu hình KRaft authorizer thuộc phạm vi broker administrator:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:kafka-admin
~~~

Đây là ví dụ cấu hình minh họa; super.users, listener configuration và default ACL behavior phải phù hợp deployment thực tế. Thay đổi authorizer trên broker có thể ảnh hưởng toàn cluster, không phải việc một Spring application tự thực hiện.

Không thay đổi broker authorizer để sửa một lỗi WRITE DLT đơn lẻ. Trước tiên hãy xác định principal và ACL thiếu. Quyền super user cũng nên rất hạn chế, được audit và không dùng làm runtime principal cho mọi business service.

## 23. Principal mapping và lý do ACL đúng tên vẫn bị từ chối

ACL có thể được cấp cho User:orders-service, nhưng broker lại nhìn thấy principal khác, ví dụ một username có prefix/suffix hoặc một distinguished name từ certificate.

Các điểm cần kiểm tra:

- SASL mechanism và username thực tế.
- JAAS configuration có được load từ đúng environment không.
- TLS client certificate subject và principal builder/mapping.
- Broker logs ghi authenticated principal nào.
- Client có đang dùng ProducerFactory/KafkaTemplate khác với dự kiến không.
- DLT producer có dùng cùng credentials với source consumer không.
- Có DENY ACL hoặc host restriction phù hợp không.

Không log password, JAAS string hoặc private key để điều tra principal mismatch. Log principal đã xác thực có thể cần được bảo vệ như metadata bảo mật.

Một lỗi thường gặp là source consumer factory dùng credentials A nhưng DLT KafkaTemplate được tạo từ producer factory B với credentials khác. Source READ thành công, nhưng DLT WRITE bị từ chối. Cần kiểm tra cấu hình thực tế của cả consumer và producer factories.

## 24. Spring Boot có thể dùng cấu hình security chung hoặc riêng

Nếu source consumer và DLT producer dùng cùng principal, Spring Boot có thể dùng chung Kafka properties cho consumer/producer. Nếu muốn tách principal, có thể cấu hình ProducerFactory riêng cho DLT.

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildProducerProperties());

    properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.net:9093"
    );

    // Credentials DLT publisher được inject từ secret configuration.
    // Không hard-code username/password tại đây.

    return new DefaultKafkaProducerFactory<>(properties);
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {

    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

Đoạn code minh họa factory riêng; cách lấy properties phụ thuộc Spring Boot version. Trong production, hãy tạo properties map theo security binding riêng cho DLT principal, tránh kế thừa vô tình credentials hoặc serializers không đúng.

Nếu DLT publisher dùng KafkaTemplate khác, hãy chắc chắn DeadLetterPublishingRecoverer nhận đúng bean đó. Một bean tên dltKafkaTemplate chưa có nghĩa recoverer tự động sử dụng nó nếu constructor/wiring chọn template khác.

Cần kiểm tra cả key serializer, value serializer/raw bytes serializer, security protocol, SASL mechanism, JAAS credentials, transactional ID prefix nếu dùng transactions và Observation nếu cần.

## 25. ACL cho DLT raw bytes và deserialization failures

Một record lỗi deserialize có thể được recoverer xuất sang DLT dưới dạng raw byte[] cùng exception headers. DLT publisher vẫn cần WRITE ACL giống các record DLT khác, nhưng producer serializer phải hỗ trợ kiểu payload thực tế.

~~~text
orders.events
     |
     v
Deserializer failure
     |
     v
ErrorHandlingDeserializer
     |
     +--> raw bytes + error metadata
     |
     v
DeadLetterPublishingRecoverer
     |
     v
KafkaTemplate
     |
     v
orders.events.DLT
~~~

Nếu KafkaTemplate chỉ serialize OrderCreated nhưng DLT record value là byte[], send có thể thất bại vì serialization trước khi broker xử lý ACL. Đừng kết luận mọi send failure đều là authorization error.

DLT topic có thể chứa cả domain object và raw bytes tùy recovery path. Hãy cấu hình serializer tương thích hoặc nhiều templates phù hợp. ACL WRITE chỉ giải quyết quyền broker; nó không sửa serializer.

## 26. DLT publish bị TopicAuthorizationException thì điều gì xảy ra?

Một failure path:

~~~text
Source record lỗi
      |
      v
DefaultErrorHandler
      |
      v
DeadLetterPublishingRecoverer
      |
      v
KafkaTemplate.send(DLT)
      |
      v
Broker kiểm tra ACL
      |
      +--> WRITE bị DENY
                |
                v
       TopicAuthorizationException
                |
                v
       Recoverer báo send failure
                |
                v
       Error handler/container xử lý recovery failure
~~~

Khi DLT publisher thiếu WRITE:

- Record nguồn chưa được lưu ở DLT.
- Recoverer cần phản ánh lỗi publish.
- Source offset không nên được coi là recovered thành công.
- Record có thể tiếp tục được giao lại theo error handling/offset policy.
- Lặp lại vô hạn có thể tạo incident và consumer stall.
- Cần alert ngay vì recovery path không còn hoạt động.

Cần kiểm tra behavior của Spring Kafka version và cấu hình send-result policy. Với những phiên bản hỗ trợ, bật fail-if-send-result-is-error để lỗi send được surface thay vì chỉ log. Không nuốt TopicAuthorizationException rồi return bình thường từ custom recoverer.

## 27. Tránh vòng lặp retry vô hạn khi ACL DLT sai

Một record poison pill có thể thất bại liên tục. Error handler cố đưa record vào DLT, nhưng publisher không có quyền WRITE. Nếu lỗi recovery bị lặp lại mà không có alert, partition có thể bị giữ ở record đó và các record sau không tiến triển theo policy.

Một runbook nên:

1. Phân loại lỗi gốc của record.
2. Phân biệt lỗi gốc với DLT publish authorization failure.
3. Kiểm tra principal của producer.
4. Liệt kê ACL trên destination topic.
5. Kiểm tra DENY, host và resource pattern.
6. Cấp đúng WRITE ACL qua admin workflow.
7. Xác nhận producer có thể publish vào DLT.
8. Xác nhận source record được recovery theo policy.
9. Theo dõi lag và số lần delivery.
10. Không seek/skip source offset chỉ để giải phóng partition khi chưa có quyết định nghiệp vụ.

Nếu lỗi gốc là validation nhưng recovery fail do ACL, cả hai nguyên nhân cần được giữ trong log/alert. Đừng chỉ ghi exception cuối cùng mà mất nguyên nhân ban đầu.

## 28. Audit, rotation và revoke ACL

ACL là một phần của security lifecycle, không phải cấu hình tạo một lần rồi quên.

Nên duy trì:

- Owner của mỗi principal.
- Lý do cấp từng ACL.
- Resource/pattern cụ thể.
- Ngày cấp và thời hạn review.
- Quy trình rotation credentials.
- Quy trình thu hồi quyền khi service ngừng hoạt động.
- Audit log của admin changes.
- Desired ACL state trong infrastructure-as-code hoặc provisioning repo.
- Kiểm tra drift giữa ACL mong muốn và ACL thực tế.

Khi service ngừng hoạt động, xóa ACL của principal cũ sau khi xác nhận không còn workloads sử dụng. Không thu hồi quyền DLT publisher giữa lúc service đang xử lý recovery mà không có kế hoạch, vì các record lỗi có thể không được chuyển an toàn.

Nếu cần rotate credentials:

1. Tạo principal/credential mới.
2. Cấp ACL tối thiểu tương ứng.
3. Cập nhật secret/config của service.
4. Xác nhận authentication và publish/consume test.
5. Chuyển traffic.
6. Thu hồi principal cũ sau khi chắc chắn không còn client sử dụng.

Không ghi secret trong audit ticket hoặc structured logs.

## 29. Kiểm tra ACL trước khi triển khai

Một quy trình pre-production có thể xác nhận các thao tác bằng principal runtime thật:

| Kiểm tra | Principal | Kết quả mong đợi |
|---|---|---|
| Consume source topic | source consumer | Được phép |
| Join source group | source consumer | Được phép |
| Publish DLT | DLT publisher | Được phép |
| Consume DLT | DLT investigator | Được phép |
| Join DLT group | DLT investigator | Được phép |
| Publish source topic từ investigator | DLT investigator | Bị từ chối nếu read-only |
| Delete DLT topic từ runtime principal | service principal | Bị từ chối |
| Publish vào topic ngoài allowlist | DLT publisher | Bị từ chối |
| Publish DLT với raw byte[] | DLT publisher | Được phép nếu serializer đúng |
| DLT send khi topic unavailable | DLT publisher | Recovery failure được surface |

Một smoke test publish một record synthetic vào DLT có thể xác nhận quyền WRITE. Dùng topic/test environment riêng và không gửi dữ liệu production thật chỉ để thử ACL.

Không chỉ test bằng admin principal. Admin có thể bypass ACL, làm test thành công giả trong khi runtime principal vẫn bị từ chối.

## 30. Observability cho ACL failures

Nên có logs và metrics riêng cho authorization failures:

| Tín hiệu | Mục đích |
|---|---|
| DLT publish attempts | Bao nhiêu lần recoverer gọi producer |
| DLT publish success/failure | Bao nhiêu lần send được xác nhận/thất bại |
| TopicAuthorizationException count | Thiếu quyền topic |
| GroupAuthorizationException count | Thiếu quyền consumer group |
| TransactionalIdAuthorizationException count | Thiếu quyền transaction |
| AuthenticationException count | Lỗi xác thực |
| DLT oldest record age | DLT backlog cần điều tra |
| Source consumer lag | Source partition có bị kẹt không |
| Recovery failure rate | Error handler không thể hoàn tất recovery |
| Principal/resource denied logs | Tìm ACL mismatch |

Structured log cần ghi:

~~~json
{
  "level": "ERROR",
  "event": "kafka_dlt_publish_failed",
  "principal": "User:orders-service",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "exception_type": "TopicAuthorizationException",
  "recovery_outcome": "failed"
}
~~~

Ví dụ này không chứa credentials hoặc raw payload. Chỉ ghi principal đã xác thực nếu logging policy cho phép. Metric labels nên có cardinality thấp; không đưa offset, eventId hoặc raw principal từ nguồn tùy ý thành label.

## 31. Checklist ACL cho từng loại flow

### Flow source consumer và DLT publisher cùng principal

- READ source topic.
- READ source consumer group.
- WRITE trên từng DLT destination.
- Quyền transactional ID/cluster nếu producer thực sự dùng transactions/idempotent authorization theo broker policy.
- Không có quyền DELETE/ALTER không cần thiết.

### Flow tách DLT publisher principal

- Source consumer chỉ có READ source và READ group.
- DLT publisher chỉ có WRITE trên DLT destinations.
- DLT KafkaTemplate dùng đúng producer credentials.
- Serializer hỗ trợ domain object/raw bytes cần thiết.
- DLT send failure được surface.
- Credentials riêng được rotation/audit.

### DLT investigator

- READ DLT.
- READ group riêng.
- Không có WRITE nếu chỉ điều tra.
- Quarantine storage có access control.
- Không log raw payload nhạy cảm.

### Replay operator

- READ DLT và group phù hợp.
- WRITE vào đúng replay/source destination.
- Có audit và approval.
- Idempotency và side effects được xem xét trước replay.
- Không cấp cluster-wide admin.

## 32. Những sai lầm thường gặp

**Cấp READ trên source topic và nghĩ DLT publisher cũng có quyền ghi DLT**

Không. WRITE trên destination topic là một quyền riêng.

**Cấp ALL trên toàn bộ cluster để sửa TopicAuthorizationException**

Cách này mở rộng quyền quá mức và che mất principal/resource đang sai. Xác định exact topic và operation.

**Dùng admin principal trong ứng dụng**

Admin có thể bypass ACL và làm mất ý nghĩa least privilege. Runtime phải dùng principal riêng.

**Quên consumer group ACL**

Consumer có READ topic nhưng không được phép tham gia group. Cần READ trên đúng Group resource.

**Quên retry topics**

Non-blocking retry publish có thể thất bại trước khi record tới DLT. Provision và cấp ACL cho toàn bộ retry topology.

**Không tạo DLT topic trước**

Producer có thể gặp topic missing hoặc authorization errors nếu auto-create bị tắt. Provision topic theo pipeline.

**Resolver chọn destination khác ACL**

Một nhánh exception routing có thể gửi sang topic chưa được cấp WRITE. Kiểm tra toàn bộ resolver mapping.

**Ghi log thành công ngay sau KafkaTemplate.send**

Send request không phải broker acknowledgement. Kiểm tra future/recoverer send-result semantics.

**Nuốt TopicAuthorizationException**

Container có thể coi recovery thành công dù record không ở DLT. Để lỗi recovery được surface và giữ source record an toàn.

**Cấp WRITE DLT cho mọi investigator**

Đọc DLT không đồng nghĩa được phép publish/replay. Tách role.

**Nhầm SASL authentication với ACL authorization**

Credentials hợp lệ chỉ xác định principal; broker vẫn có thể từ chối operation.

**Cho rằng Kafka transaction giải quyết quyền DLT**

Transaction không bypass ACL. Producer vẫn cần quyền topic và transactional ID tương ứng.

## 33. Runbook khi DLT publish bị từ chối

Khi alert cho thấy TopicAuthorizationException:

1. Lấy source topic, partition, offset và destination topic từ structured logs.
2. Xác định KafkaTemplate/ProducerFactory thực sự gửi DLT.
3. Xác định principal broker đã authenticate cho producer.
4. Dùng admin identity liệt kê ACL trên DLT destination.
5. Kiểm tra literal/prefixed pattern, host restriction và DENY entries.
6. Cấp WRITE đúng principal trên đúng DLT topic qua quy trình change.
7. Nếu dùng transaction, kiểm tra transactional ID ACL và cluster idempotent permission theo cấu hình.
8. Xác nhận DLT topic tồn tại và partition resolver hợp lệ.
9. Chạy smoke test bằng runtime principal.
10. Theo dõi DLT send result và source offset recovery.
11. Kiểm tra source lag, retry count và DLT ingress.
12. Xác nhận record chỉ được xử lý lại theo policy, không seek/skip thủ công ngoài quy trình.
13. Ghi audit cho ACL change và incident closure.

Nếu exception là GroupAuthorizationException, điều tra consumer group của DLT listener hoặc source listener. Nếu AuthenticationException, sửa credentials/TLS/SASL trước; cấp thêm ACL không giải quyết lỗi xác thực.

## 34. Checklist đưa DLT ACL vào production

- Xác định principal thật mà broker nhìn thấy.
- Tách source consumer, DLT publisher, DLT investigator và replay operator theo least privilege.
- Source consumer có READ đúng source topics.
- Consumer group có READ đúng Group resource.
- DLT publisher có WRITE đúng từng destination topic.
- DLT consumer có READ DLT và group của nó.
- Retry topics có ACL phù hợp với topology thực tế.
- DLT topics được pre-provision.
- Partition count khớp destination resolver.
- Retention, replication và min.insync.replicas phù hợp durability requirement.
- Không cấp CREATE/DELETE/ALTER cho runtime principal nếu không cần.
- Không dùng ALL trên cluster để xử lý lỗi một topic.
- Prefixed ACL chỉ dùng khi namespace có ownership rõ.
- Kiểm tra cả DENY entries và principal mapping.
- SASL/TLS authentication tách biệt với authorization.
- TransactionalId và IDEMPOTENT_WRITE chỉ cấp khi producer configuration yêu cầu.
- DLT KafkaTemplate dùng đúng principal và serializer.
- Recoverer báo send failure theo policy.
- Source offset không được coi là recovered nếu DLT send thất bại.
- Structured logs giữ source/destination coordinates và error category.
- Metrics cảnh báo authorization/recovery failures.
- ACL changes được audit và review định kỳ.
- Credentials được lưu trong secret manager và có rotation.
- Đã smoke test bằng runtime principal, không dùng admin principal.
- Replay operator có quyền riêng và idempotency policy.

**Kết luận:** ACL cho DLT là một phần của đường recovery, không phải một quyền phụ thêm sau khi listener đã chạy. Source consumer cần READ trên nguồn và group; DLT publisher cần WRITE trên đúng DLT destinations; DLT consumer cần READ trên DLT và group của nó. Khi có retry topics hoặc Kafka transactions, ACL phải mở rộng đúng theo các resources thực tế đó. Hãy pre-provision topics, xác định principal broker authenticate, giữ quyền tối thiểu và bảo đảm DLT send failure được surface. Một record chỉ được coi là recovery thành công khi **DLT publish đã được xác nhận theo policy**, không phải chỉ vì recoverer đã gọi KafkaTemplate.send.

