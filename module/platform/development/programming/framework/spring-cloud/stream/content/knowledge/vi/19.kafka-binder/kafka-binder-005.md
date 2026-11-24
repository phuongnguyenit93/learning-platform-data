# Sử dụng topic có sẵn và phân quyền quản trị tài nguyên

Trong môi trường production, topic Kafka thường được tạo và quản lý trước bởi đội nền tảng hoặc quản trị Kafka. Ứng dụng Spring Cloud Stream chỉ cần kết nối vào topic đã có, đọc hoặc ghi dữ liệu theo quyền được cấp. Cách triển khai này giúp kiểm soát số partition, replication factor, retention, cleanup policy và quyền truy cập theo quy trình vận hành của tổ chức.

Kafka binder có thể tự tạo topic hoặc thêm partition trong một số cấu hình. Khi muốn dùng topic có sẵn, cần tắt các chức năng provision tương ứng trong binder, xác nhận topic đã có đủ partition, rồi cấp ACL đúng cho principal chạy ứng dụng. Quyền tạo topic, thay đổi cấu hình và cấp ACL nên thuộc về principal quản trị riêng; principal runtime của ứng dụng chỉ nên có quyền đọc hoặc ghi đúng tài nguyên cần dùng.

## 1. Topic là tài nguyên được quản trị trước

Spring Cloud Stream Kafka binder ánh xạ mỗi destination thành một Kafka topic. Consumer group của binding ánh xạ thành Kafka consumer group; partitioning của binder ánh xạ trực tiếp sang partition của topic.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processOrder-out-0:
          destination: orders.accepted
~~~

Trong ví dụ:

- **orders.submitted** là topic có sẵn mà input binding đọc.
- **order-service** là consumer group lưu offset đọc của ứng dụng.
- **orders.accepted** là topic có sẵn mà output binding ghi.
- **processOrder-in-0** và **processOrder-out-0** là tên binding logic trong ứng dụng.

Destination phải khớp chính xác với tên topic được tạo trên cluster. Việc đặt group không tạo một topic mới; nó xác định danh tính consumer group. Nếu không khai báo group, binding dùng anonymous consumer group; các instance có thể nhận luồng độc lập thay vì cùng chia tải trong một group có tên. Hãy đặt group tường minh khi các replica của một dịch vụ cần chia nhau xử lý và dùng chung vị trí offset.

## 2. Tắt topic provisioning của Kafka binder

Kafka binder có hai thuộc tính quan trọng:

| Thuộc tính | Khi bật | Khi tắt |
|---|---|---|
| autoCreateTopics | Binder tạo topic khi cần | Binder yêu cầu topic đã tồn tại; nếu topic không có, binding khởi tạo thất bại |
| autoAddPartitions | Binder có thể thêm partition khi số partition hiện tại thấp hơn mức cần thiết | Binder yêu cầu topic có sẵn đủ partition; nếu thiếu, binding khởi tạo thất bại |

Để chỉ sử dụng topic đã được provision:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processOrder-out-0:
          destination: orders.accepted
~~~

Hai thuộc tính được đặt ở cấp Kafka binder, không đặt dưới một binding riêng. Khi autoCreateTopics là false, topic chưa tồn tại sẽ khiến binder không khởi tạo được binding. Khi autoAddPartitions là false, binder không tự tăng partition nếu topic có ít partition hơn số lượng mà cấu hình producer hoặc partitioning yêu cầu.

Giá trị mặc định trong tài liệu binder hiện hành là autoCreateTopics=true và autoAddPartitions=false. Nên khai báo tường minh cả hai trong môi trường cần quản trị topic tập trung, để ý định triển khai không phụ thuộc giá trị mặc định của phiên bản.

### 2.1. Phân biệt cấu hình binder và cấu hình broker

autoCreateTopics của Spring Cloud Stream binder độc lập với auto.create.topics.enable của Kafka broker. Tắt auto-create ở binder không tự tắt khả năng broker tự tạo topic khi client gửi metadata request cho một tên topic chưa tồn tại.

Nếu yêu cầu vận hành là topic chỉ được tạo qua quy trình quản trị, quản trị viên cần kiểm tra cấu hình broker và cân nhắc tắt:

~~~properties
auto.create.topics.enable=false
~~~

Hai lớp này có mục đích khác nhau:

- spring.cloud.stream.kafka.binder.autoCreateTopics=false ngăn binder chủ động tạo topic qua cơ chế provisioning của nó.
- auto.create.topics.enable=false ngăn broker tự tạo topic theo yêu cầu metadata của client.

Trong cluster dùng chung, không nên giả định ứng dụng đã bị chặn tạo topic chỉ vì binder đặt autoCreateTopics=false. Hãy kiểm tra chính sách broker và ACL của principal runtime.

## 3. Chuẩn bị topic trước khi triển khai ứng dụng

Quản trị viên cần thống nhất tên topic, số partition, replication factor và cấu hình lưu giữ dữ liệu trước khi cấp quyền cho ứng dụng. Những giá trị này ảnh hưởng trực tiếp đến thứ tự, throughput, độ bền và dung lượng lưu trữ.

| Thuộc tính topic | Câu hỏi cần quyết định |
|---|---|
| Tên topic | Có tuân theo quy ước domain, môi trường và quyền sở hữu không? |
| Partition count | Cần bao nhiêu mức song song và có đủ cho consumer concurrency không? |
| Replication factor | Cần bao nhiêu bản sao và cluster có đủ broker không? |
| min.insync.replicas | Khi producer dùng acks=all, cần tối thiểu bao nhiêu replica đang đồng bộ? |
| retention.ms / retention.bytes | Dữ liệu được giữ theo thời gian hoặc dung lượng bao lâu? |
| cleanup.policy | Dùng delete, compact hay kết hợp cả hai theo mục đích dữ liệu? |
| max.message.bytes | Kích thước message tối đa có phù hợp với payload thực tế không? |

Ví dụ một topic sự kiện đơn hàng có sáu partition, replication factor ba và giữ dữ liệu bảy ngày:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092,kafka-2:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --create --if-not-exists \
  --topic orders.submitted \
  --partitions 6 \
  --replication-factor 3 \
  --config retention.ms=604800000 \
  --config min.insync.replicas=2
~~~

Đây là ví dụ lệnh quản trị. Đường dẫn admin-client.properties cần trỏ đến file cấu hình bảo mật dành cho principal quản trị và được bảo vệ theo chính sách của tổ chức. Không đưa mật khẩu thật vào dòng lệnh hoặc lưu file credential trong repository.

Topic đã có không cần tạo lại. Với topic có sẵn, hãy kiểm tra cấu hình hiện tại và chỉ thay đổi qua quy trình change management của cluster. Không chạy lệnh tạo hoặc sửa topic từ pipeline triển khai ứng dụng nếu pipeline đó chỉ được cấp quyền runtime.

## 4. Kiểm tra topic đã có đủ partition và cấu hình

Trước khi khởi động ứng dụng, dùng công cụ Kafka để xác nhận topic tồn tại:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --topic orders.submitted
~~~

Kết quả mô tả topic cho biết partition count, leader, replica và ISR (in-sync replicas). Cần kiểm tra tất cả partition đều có leader và replication assignment đáp ứng chính sách cluster.

Đọc cấu hình topic:

~~~bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --entity-type topics --entity-name orders.submitted
~~~

Kiểm tra ACL hiện có:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --list --topic orders.submitted
~~~

Sau khi ứng dụng chạy, có thể kiểm tra group và offset:

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --group order-service
~~~

Các lệnh trên cần quyền phù hợp với thao tác describe. Nếu principal không được phép xem cấu hình, ACL hoặc consumer group, công cụ có thể báo lỗi authorization dù topic vẫn tồn tại và ứng dụng có thể có quyền đọc/ghi dữ liệu.

## 5. Đảm bảo số partition tương thích với binding

Khi producer dùng partitioning, binder cần biết số partition mục tiêu. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-out-0:
          destination: orders.accepted
          producer:
            partition-key-expression: payload.customerId
            partition-count: 6
~~~

Với topic đã có, số partition thực tế cần đáp ứng cấu hình producer. Nếu partition-count yêu cầu sáu nhưng topic chỉ có bốn partition và autoAddPartitions=false, binder có thể từ chối khởi tạo binding thay vì tự thay đổi topic.

minPartitionCount chỉ có tác dụng khi autoCreateTopics hoặc autoAddPartitions được bật. Khi cả hai đều tắt, không dùng minPartitionCount để kỳ vọng binder điều chỉnh topic có sẵn.

Với producer không dùng partitioning tường minh, hãy kiểm tra các cấu hình khác có thể làm tăng số partition kỳ vọng, như instanceCount * concurrency trong trường hợp partitioned producer. Cấu hình ứng dụng và topic phải được thống nhất trước khi triển khai.

Không giảm số partition của topic như một thao tác điều chỉnh thông thường. Kafka không hỗ trợ giảm partition count theo cách an toàn như tăng partition; tăng partition cũng có thể thay đổi cách hash key ánh xạ sang partition và ảnh hưởng thứ tự tương đối của cùng một key. Hãy quyết định partition count có chủ đích từ đầu.

## 6. Tách quyền quản trị và quyền runtime

Nên sử dụng principal riêng cho các nhiệm vụ:

| Principal | Trách nhiệm | Quyền điển hình |
|---|---|---|
| kafka-platform-admin | Tạo topic, thay đổi partition/config, quản lý ACL | Create/Alter/Describe trên tài nguyên cần quản trị; quyền ACL theo chính sách cluster |
| order-producer | Gửi sự kiện vào topic đầu ra | Write và Describe trên topic đầu ra |
| order-consumer | Đọc topic đầu vào và commit offset | Read và Describe trên topic đầu vào; Read trên consumer group tương ứng |
| order-observer | Đọc thông tin vận hành | Describe hoặc DescribeConfigs trên tài nguyên được phép quan sát |

Principal runtime không nên có quyền Create trên toàn cluster, Delete topic hoặc AlterConfigs nếu ứng dụng không có nhiệm vụ quản trị. Việc tách quyền giảm ảnh hưởng khi credential của ứng dụng bị lộ và giúp audit dễ hơn.

Nếu ứng dụng chỉ đọc orders.submitted và ghi orders.accepted, principal có thể được cấp:

- Read/Describe trên orders.submitted.
- Read trên group order-service.
- Write/Describe trên orders.accepted.

Không cấp quyền đọc tất cả topic hoặc ghi tất cả topic chỉ để tránh lỗi authorization trong quá trình triển khai.

## 7. Các ACL Kafka thường dùng

Kafka ACL áp dụng lên các loại resource khác nhau. Những resource thường gặp khi dùng binder:

| Resource | Ví dụ | Mục đích |
|---|---|---|
| Topic | orders.submitted | Đọc hoặc ghi record và truy vấn metadata |
| Group | order-service | Tham gia consumer group và quản lý offset |
| Cluster | Cluster hiện tại | Một số thao tác quản trị hoặc idempotent producer |
| TransactionalId | Prefix transaction của producer | Gửi và commit transaction Kafka |

Các operation phổ biến:

| Operation | Ý nghĩa |
|---|---|
| Read | Đọc topic, tham gia group hoặc đọc offset tùy resource |
| Write | Ghi record hoặc thao tác transaction tùy resource |
| Create | Tạo resource |
| Alter | Thay đổi resource hoặc ACL theo ngữ cảnh |
| Describe | Đọc metadata cơ bản |
| DescribeConfigs | Đọc cấu hình resource |
| AlterConfigs | Thay đổi cấu hình resource |
| IdempotentWrite | Cho phép idempotent producer ở cấp cluster |

Với producer thông thường, thao tác produce cần Write trên topic; metadata lookup cần Describe trên topic. Với consumer group, consumer cần quyền phù hợp trên topic và group để đọc record, join group và commit/fetch offset.

Khi bật idempotence, Kafka có thể yêu cầu IdempotentWrite trên cluster. Khi dùng transactional producer, cần thêm quyền Write trên resource TransactionalId tương ứng; thao tác transaction có thể cần quyền trên topic và group liên quan. Hãy căn cứ vào API Kafka thực sự được ứng dụng sử dụng và ma trận authorization của phiên bản broker.

## 8. Cấp ACL cho producer và consumer

Ví dụ cấp quyền producer tối thiểu trên một topic:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-producer \
  --operation Write --operation Describe \
  --topic orders.accepted
~~~

Ví dụ cấp quyền consumer trên topic đầu vào:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Read --operation Describe \
  --topic orders.submitted
~~~

Cấp quyền cho consumer group:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Read \
  --group order-service
~~~

Nếu ứng dụng hoặc công cụ vận hành cần gọi API mô tả consumer group, có thể cần thêm Describe trên resource group:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Describe \
  --group order-service
~~~

Các ví dụ là mẫu cho ACL literal trên từng resource. Có thể dùng resource pattern dạng prefix khi nhiều topic tuân theo quy ước tên, nhưng chỉ nên cấp prefix đủ hẹp. Cần xem ACL đã có trước khi thêm mới để tránh xung đột allow/deny hoặc cấp quyền rộng ngoài dự kiến.

Kafka CLI có các tùy chọn tiện ích --producer và --consumer để tạo nhóm ACL phổ biến. Các tùy chọn này có thể cấp thêm quyền như Create hoặc Describe tùy vai trò và phiên bản Kafka. Khi áp dụng least privilege, dùng --operation tường minh giúp nhìn rõ từng quyền được cấp.

## 9. Quyền quản trị topic và partition

Nếu ứng dụng được phép tự tạo topic, principal cần quyền Create trên cluster hoặc topic theo cách broker authorizer kiểm tra. Nếu binder được phép thêm partition, principal cần quyền Alter phù hợp trên topic và các quyền metadata liên quan.

Nếu ứng dụng cần đọc cấu hình topic, principal có thể cần DescribeConfigs. Nếu ứng dụng cần thay đổi retention hoặc cleanup policy, thao tác đó yêu cầu quyền thay đổi cấu hình như AlterConfigs. Việc quản lý ACL cũng là thao tác quản trị riêng; không nên cấp quyền Alter cluster cho ứng dụng runtime chỉ để nó đọc/ghi record.

Với topic có sẵn, quy trình được khuyến nghị:

1. Quản trị viên tạo topic và đặt partition/replication/config.
2. Quản trị viên cấp ACL cho principal producer/consumer.
3. Ứng dụng dùng principal runtime kết nối vào topic đã có.
4. Binder kiểm tra topic và metadata nhưng không tự tạo topic hoặc thêm partition.
5. Nếu cần đổi partition hoặc config, thực hiện qua quy trình quản trị và change review.

Tài liệu Kafka mô tả thao tác Create, Alter, DescribeConfigs và AlterConfigs trên các resource riêng. Quyền cụ thể có thể khác theo broker version, authorizer và các API mà client gọi; hãy kiểm tra lỗi authorization thực tế và ma trận quyền của cluster.

## 10. Cấu hình xác thực và mã hóa kết nối

ACL quyết định principal được phép thao tác gì sau khi xác thực. Để xác thực client, Kafka thường dùng SASL hoặc TLS client certificate; để mã hóa đường truyền, dùng SSL/TLS.

Ví dụ cấu hình binder với SASL/SCRAM qua TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
            ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
            ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Các biến môi trường phải được cung cấp bởi secret manager hoặc hệ thống triển khai. Không ghi username/password thật vào application.yml, source code, log hoặc image container. File truststore và secret cần có quyền đọc hạn chế.

spring.cloud.stream.kafka.binder.configuration áp dụng các Kafka client properties dùng chung cho producer và consumer do binder tạo. Nếu cần tùy chỉnh riêng AdminClient, binder cung cấp AdminClientConfigCustomizer; việc cấu hình AdminClient phải phù hợp với cơ chế xác thực của cluster. Không giả định cấu hình cho producer/consumer tự động giải quyết mọi yêu cầu xác thực hoặc quyền quản trị.

Trong môi trường nhiều cluster, mỗi binder có thể cần broker list và JAAS/SASL configuration riêng. Dùng multi-binder configuration và chỉ định binder cho từng binding thay vì dùng chung credential hoặc bootstrap server không đúng cluster.

## 11. Kiểm tra quyền và lỗi authorization

Một ứng dụng có thể xác thực thành công nhưng vẫn không được phép truy cập topic hoặc group. Cần phân biệt lỗi xác thực với lỗi phân quyền:

| Lỗi hoặc biểu hiện | Nguyên nhân có thể | Nơi kiểm tra |
|---|---|---|
| Authentication failed | Sai username/password, SASL mechanism hoặc TLS certificate | Secret, JAAS config, truststore và broker log |
| TOPIC_AUTHORIZATION_FAILED | Thiếu Read, Write, Describe hoặc quyền topic tương ứng | ACL trên topic |
| GROUP_AUTHORIZATION_FAILED | Thiếu quyền Read/Describe trên consumer group | ACL trên group |
| CLUSTER_AUTHORIZATION_FAILED | Thiếu quyền cluster cho thao tác cần thiết | ACL cluster và API đang gọi |
| Topic không tồn tại | Topic chưa được provision hoặc sai tên destination | kafka-topics --describe |
| Binder khởi động thất bại vì partition | Topic có ít partition hơn mức cấu hình yêu cầu | partition-count, instanceCount, concurrency và partition thực tế |
| Metadata request tạo topic ngoài dự kiến | Broker đang bật auto topic creation | auto.create.topics.enable và broker policy |

Khi gặp lỗi, kiểm tra principal thực tế mà broker nhận được, không chỉ tên secret trong file cấu hình. Với SASL, principal thường được ánh xạ từ danh tính xác thực; ACL phải cấp cho đúng principal đó.

Không cấp All trên cluster chỉ để làm cho ứng dụng khởi động. Hãy xác định API nào bị từ chối, resource nào được kiểm tra và thêm operation nhỏ nhất cần thiết.

## 12. Triển khai theo môi trường

Các môi trường development, staging và production thường có topic và quyền khác nhau. Có thể dùng cùng cấu trúc cấu hình nhưng lấy broker, tên topic và group từ biến môi trường:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: ${ORDERS_INPUT_TOPIC}
          group: ${ORDERS_CONSUMER_GROUP}
        processOrder-out-0:
          destination: ${ORDERS_OUTPUT_TOPIC}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Tên topic và group nên được khai báo rõ trong từng môi trường. Không dùng cùng consumer group giữa hai môi trường nếu chúng phải có offset độc lập. Nếu hai môi trường dùng chung cluster và cùng group, chúng có thể chia nhau partition và gây ra hành vi không mong muốn.

Pipeline triển khai nên kiểm tra:

- Topic đã tồn tại trong đúng cluster.
- Partition count đáp ứng cấu hình producer/consumer.
- Replication factor và ISR policy phù hợp với môi trường.
- ACL đã cấp cho principal của ứng dụng.
- Principal runtime không có quyền quản trị không cần thiết.
- Binder tắt auto-create và auto-add-partitions theo chính sách.
- Broker auto topic creation được cấu hình theo chính sách cluster.

## 13. Quy trình xử lý khi topic đã tồn tại nhưng binding không khởi động

Thực hiện kiểm tra theo thứ tự:

1. Xác nhận destination trùng chính xác tên topic.
2. Dùng kafka-topics --describe để xác nhận topic tồn tại và có leader.
3. Kiểm tra partition count thực tế so với partition-count, minPartitionCount và yêu cầu partitioning.
4. Xác nhận autoCreateTopics=false và autoAddPartitions=false nếu ứng dụng chỉ dùng tài nguyên có sẵn.
5. Xác nhận broker không tự tạo topic ngoài quy trình nếu chính sách yêu cầu cấm.
6. Kiểm tra security.protocol, SASL mechanism, JAAS và TLS truststore.
7. Xác định principal thực tế trong broker log hoặc công cụ quản trị.
8. Kiểm tra ACL trên topic và group bằng kafka-acls --list.
9. Nếu lỗi liên quan AdminClient, kiểm tra quyền Describe và cấu hình AdminClient riêng.
10. Khởi động lại binding sau khi quản trị viên sửa topic hoặc ACL, rồi xác minh consumer group/producer hoạt động.

Không nên bật lại auto-create hoặc cấp quyền admin rộng như bước thử đầu tiên. Các thao tác đó có thể che khuất nguyên nhân thật và tạo tài nguyên không đúng chuẩn.

## 14. Checklist bàn giao cho production

- [ ] Topic input/output đã được tạo trước bởi quy trình quản trị.
- [ ] Tên destination khớp tên topic thực tế.
- [ ] Partition count đáp ứng yêu cầu của producer và consumer.
- [ ] Replication factor, min.insync.replicas và retention đã được thống nhất.
- [ ] autoCreateTopics=false và autoAddPartitions=false được khai báo tường minh.
- [ ] Broker auto topic creation được xem xét theo chính sách cluster.
- [ ] Principal runtime tách biệt với principal quản trị.
- [ ] Producer chỉ có Write/Describe trên topic đầu ra cần thiết.
- [ ] Consumer có Read/Describe trên topic đầu vào và quyền phù hợp trên group.
- [ ] TransactionalId/IdempotentWrite ACL được cấp nếu ứng dụng thực sự dùng transaction/idempotence.
- [ ] Kết nối dùng SASL/TLS phù hợp và secret không nằm trong source control.
- [ ] AdminClient có quyền cần thiết cho thao tác metadata/provisioning mà binder thực hiện.
- [ ] Đã kiểm tra topic, ACL, group, offset và log sau triển khai.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html): ánh xạ destination, consumer group và partition sang Kafka.
- [Spring Cloud Stream - Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): autoCreateTopics, autoAddPartitions, minPartitionCount, replicationFactor và cấu hình client.
- [Spring Cloud Stream - Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html): SASL, TLS, JAAS và khuyến nghị quản trị topic/ACL trong môi trường bảo mật.
- [Spring Cloud Stream - Customizing AdminClient Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/admin-client-config-cust.html): tùy chỉnh cấu hình AdminClient được binder sử dụng.
- [Apache Kafka - Authorization and ACLs](https://kafka.apache.org/40/security/authorization-and-acls/): resource, operation và ACL cho producer, consumer, group, cluster và transactional ID.
