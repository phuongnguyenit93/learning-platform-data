# Phân quyền tối thiểu cho phát, nhận và cấp phát tài nguyên

Một ứng dụng Spring Cloud Stream thường thực hiện ba nhóm thao tác khác nhau với broker:

1. **Phát message:** ghi event vào topic, exchange hoặc destination.
2. **Nhận message:** đọc event từ topic, queue hoặc subscription và xác nhận việc xử lý.
3. **Cấp phát tài nguyên:** tạo topic, partition, exchange, queue, subscription, binding, schema hoặc thay đổi cấu hình broker.

Ba nhóm thao tác này không cần cùng một mức quyền. Ứng dụng chạy nghiệp vụ thường chỉ cần quyền phát hoặc nhận trên những destination cụ thể. Quyền tạo, xóa, đổi partition, cấu hình retention hay cấp quyền cho role khác thuộc về tác vụ quản trị hạ tầng.

**Phân quyền tối thiểu (least privilege)** là cấp cho mỗi danh tính đúng những thao tác và tài nguyên cần thiết để hoàn thành nhiệm vụ, trong đúng môi trường và khoảng thời gian cần thiết. Khi một credential bị lộ, phạm vi ảnh hưởng nhờ đó được giới hạn.

Bài học này áp dụng nguyên tắc đó cho Kafka, RabbitMQ và Pulsar binder của Spring Cloud Stream. Nội dung đi từ cách tách danh tính producer, consumer và provisioner đến ACL cụ thể, cấu hình xác thực trong Spring Boot, kiểm tra quyền và vận hành credential an toàn.

## 1. Authentication và authorization là hai việc khác nhau

**Authentication (xác thực)** trả lời câu hỏi: client là ai? Broker xác minh danh tính bằng username/password, SASL, certificate, token hoặc cơ chế được cấu hình.

**Authorization (phân quyền)** trả lời câu hỏi: danh tính đó được phép làm gì trên tài nguyên nào? Broker kiểm tra quyền khi client publish, consume, tạo topic, khai báo queue hoặc thực hiện thao tác quản trị.

~~~text
Spring Cloud Stream application
       |
       | 1. Authentication
       |    "Tôi là orders-projection-prod"
       v
Broker xác minh danh tính
       |
       | 2. Authorization
       |    "Role này có READ trên orders.created
       |     và READ trên group order-projection-v1?"
       v
Cho phép hoặc từ chối thao tác
~~~

Có credential hợp lệ không đồng nghĩa được quyền đọc hoặc ghi mọi topic. Ngược lại, khai báo ACL cho một principal cũng không giúp client kết nối nếu xác thực thất bại.

Một cấu hình chỉ bật authentication nhưng chưa bật authorization có thể vẫn cho principal đã xác thực quyền rộng hơn dự kiến. Ví dụ tài liệu Kafka nêu rõ nếu không cấu hình authorizer, các principal đã xác thực có thể có quyền đầy đủ. Pulsar cũng cảnh báo rằng chỉ bật authentication có thể cho role đã xác thực truy cập toàn bộ tài nguyên nếu authorization chưa được bật.

Vì vậy, khi thiết kế bảo mật phải kiểm tra cả hai lớp: broker đã nhận diện đúng service account chưa và authorizer có giới hạn thao tác trên resource chưa.

## 2. Tách danh tính theo vai trò

Không dùng một tài khoản quản trị chung cho mọi ứng dụng. Mỗi service, môi trường và nhiệm vụ nên có danh tính riêng.

Ví dụ hệ thống xử lý đơn hàng:

| Danh tính | Nhiệm vụ | Quyền cần thiết |
|---|---|---|
| `orders-api-prod` | Phát `orders.created` | Publish vào topic/exchange đầu ra |
| `orders-projection-prod` | Nhận `orders.created` | Consume topic/queue và dùng consumer group/subscription của chính nó |
| `billing-prod` | Nhận event để lập hóa đơn | Consume cùng destination qua group/subscription riêng |
| `stream-provisioner-prod` | Tạo topic, queue, exchange và policy | Quyền quản trị đúng namespace/vhost/resource cần cấp phát |
| `stream-monitor-prod` | Đọc metadata và số liệu vận hành | Quyền quan sát cần thiết; không mặc định có quyền đọc payload |
| `schema-publisher-prod` | Đăng ký schema nếu dùng schema registry | Quyền ghi schema cho subject/package được giao |

Nếu một service vừa nhận vừa phát message, nó có thể cần cả quyền consume trên input và publish trên output. Tuy vậy, quyền tổng hợp đó vẫn chỉ áp dụng trên các resource đã chỉ định.

Tách danh tính theo môi trường:

~~~text
orders-api-dev       != orders-api-staging
                    != orders-api-prod

orders-projection    != billing
                    != stream-provisioner
~~~

Không đưa hostname, pod name hoặc instance ID vào danh tính của từng replica nếu các replica phải cùng thực hiện một nhiệm vụ. Hãy dùng một service identity ổn định cho workload và để broker/binder điều phối consumer group hoặc subscription.

## 3. Ma trận quyền theo thao tác

Trước khi tạo ACL, liệt kê chính xác thao tác mà binding cần thực hiện.

| Thao tác | Producer | Consumer | Provisioner |
|---|---:|---:|---:|
| Kết nối và xác thực | Có | Có | Có |
| Publish vào destination | Có | Chỉ khi phát thêm event | Chỉ khi kiểm thử cần |
| Read/consume destination | Không | Có | Không |
| Join consumer group hoặc subscription | Không | Có | Không |
| Tạo topic/partition | Không | Không | Có |
| Tạo exchange/queue/binding | Không | Không | Có |
| Tạo namespace hoặc tenant | Không | Không | Có |
| Thay đổi retention, quota hoặc policy | Không | Không | Có khi được giao |
| Cấp/revoke quyền cho role khác | Không | Không | Chỉ admin được chỉ định |
| Xóa resource | Không | Không | Chỉ quy trình quản trị có phê duyệt |

Bảng là mô hình phân tách trách nhiệm, không phải danh sách ACL giống nhau trên mọi broker. Mỗi broker có cách biểu diễn quyền riêng; các phần sau ánh xạ các thao tác này sang Kafka, RabbitMQ và Pulsar.

Một ứng dụng chỉ consume không nên có quyền publish vào input topic. Một producer không cần quyền join consumer group. Cả hai không cần quyền tạo tenant, xóa queue hay sửa cấu hình broker.

## 4. Phân biệt runtime role và provisioning role

Binder có thể tự tạo resource khi ứng dụng khởi động. Điều đó tiện trong môi trường phát triển, nhưng có thể khiến service account runtime cần quyền quản trị ngoài ý muốn.

Kiến trúc production nên tách:

~~~text
Pipeline / Platform administrator
          |
          | Provisioning identity
          v
Create topics, exchanges, queues,
partitions, subscriptions and policies
          |
          v
Broker resources already exist
          |
          +------------------------------+
          |                              |
          v                              v
Producer runtime identity        Consumer runtime identity
WRITE only on output             READ only on input
          |                              |
          v                              v
Publish event                    Consume and acknowledge
~~~

Quy trình triển khai:

1. Platform hoặc pipeline tạo resource trước khi deploy service.
2. Quản trị viên cấp ACL cho producer/consumer role.
3. Ứng dụng nhận credential runtime từ secret store.
4. Binder kết nối tới resource đã có và thực hiện đúng thao tác nghiệp vụ.
5. Khi thay đổi topology, pipeline quản trị cập nhật resource và ACL theo phiên bản.

Không cấp quyền `CREATE`, `ALTER`, `DELETE`, `configure` hoặc tenant-admin chỉ vì binder đang cố khai báo resource lúc khởi động. Hãy kiểm tra binder đang provision gì và tách bước đó sang quy trình quản trị nếu có thể.

## 5. Đặt tên resource và phạm vi quyền

Tên resource nên phản ánh domain, môi trường và chức năng để ACL có thể giới hạn chính xác.

Ví dụ:

| Resource | Tên gợi ý |
|---|---|
| Kafka topic | `orders.created.v1` |
| Kafka consumer group | `orders-projection-prod-v1` |
| RabbitMQ vhost | `orders-prod` |
| Rabbit exchange | `orders.created` |
| Rabbit queue | `orders.created.orders-projection` |
| Pulsar namespace | `acme/orders-prod` |
| Pulsar topic | `persistent://acme/orders-prod/orders-created-v1` |
| Pulsar subscription | `orders-projection-prod-v1` |

Tránh quyền wildcard như `*`, `.*` hoặc quyền `All` trên toàn cluster/vhost/tenant cho service runtime. Wildcard có thể hợp lý cho một platform administrator được kiểm soát, nhưng không phải mặc định cho ứng dụng nghiệp vụ.

Nên giới hạn cả:

- Môi trường: dev, staging, production.
- Domain: orders, billing, inventory.
- Hướng dữ liệu: input và output.
- Consumer group/subscription: đúng danh tính workload.
- Resource phụ: retry topic, DLT, DLQ, changelog hoặc repartition topic nếu ứng dụng thực sự dùng.

## 6. Kafka: resource và ACL

Kafka ACL áp dụng lên các loại resource như:

- **Topic:** nơi producer ghi và consumer đọc.
- **Group:** consumer group dùng để phối hợp và lưu offset.
- **Cluster:** thao tác ở phạm vi toàn cluster.
- **TransactionalId:** định danh producer transaction.
- **User/DelegationToken:** một số thao tác quản lý credential.

Các operation thường gặp:

| Operation | Ý nghĩa |
|---|---|
| `Read` | Đọc topic hoặc tham gia consumer group theo giao thức tương ứng |
| `Write` | Ghi vào topic hoặc transaction resource |
| `Create` | Tạo topic/resource |
| `Delete` | Xóa resource |
| `Alter` | Thay đổi resource hoặc partition |
| `Describe` | Đọc metadata |
| `DescribeConfigs` | Đọc cấu hình |
| `AlterConfigs` | Thay đổi cấu hình |
| `IdempotentWrite` | Dùng producer idempotence ở phạm vi cluster |

Kafka ACL là tổ hợp principal, host, operation, resource pattern và quyền allow/deny. Nếu authorizer được cấu hình theo chế độ mặc định, thao tác không có ACL phù hợp sẽ bị từ chối.

## 7. Kafka: quyền tối thiểu cho producer

Một producer thông thường cần:

- `Write` trên topic đích.
- `Describe` trên topic để lấy metadata.
- Quyền bổ sung nếu dùng idempotence, transaction hoặc tự tạo topic.

Ví dụ cấp quyền cho principal `orders-api-prod` chỉ publish vào topic `orders.created.v1`:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-api-prod \
  --operation Write \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-api-prod \
  --operation Describe \
  --topic orders.created.v1
~~~

Hai ACL trên thể hiện quyền ghi và xem metadata của một topic cụ thể. Chúng không cấp quyền đọc topic, join group, tạo topic hay xóa topic.

Nếu producer dùng idempotence, Kafka có thể yêu cầu operation `IdempotentWrite` trên resource Cluster tùy client/broker và cách cấu hình. Nếu producer dùng `transactional.id`, nó cần quyền `Write` trên resource `TransactionalId`; các transaction có offset cũng có thể cần quyền trên group và topic liên quan. Hãy thêm các quyền này chỉ khi tính năng đó được bật và xác minh bằng broker version thực tế.

Không dùng `--producer` convenience option mà không xem quyền nó tạo ra. Tài liệu Kafka hiện hành cho biết option tiện ích này tạo các ACL `WRITE`, `DESCRIBE` và `CREATE` trên topic. Nếu topic đã được provision trước, producer runtime thường không cần `CREATE`.

## 8. Kafka: quyền tối thiểu cho consumer

Một consumer thông thường cần:

- `Read` trên input topic.
- `Describe` trên topic để lấy metadata.
- `Read` trên đúng consumer group để join/heartbeat và commit offset.
- `Describe` trên group nếu client/protocol cần fetch hoặc inspect committed offsets.
- Một số quyền bổ sung nếu dùng transaction hoặc tính năng Kafka đặc biệt.

Ví dụ principal `orders-projection-prod` đọc topic `orders.created.v1` với group `orders-projection-prod-v1`:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Read \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Describe \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Read \
  --group orders-projection-prod-v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Describe \
  --group orders-projection-prod-v1
~~~

Group ACL phải khớp consumer group mà binding sử dụng. Kafka protocol có các request yêu cầu `Read` trên group (join/heartbeat/commit) và các request fetch/describe offset yêu cầu `Describe` trên group; quyền cần thiết phụ thuộc API/client version và thao tác được dùng. Nếu cấu hình `group` trong Spring Cloud Stream thay đổi, ACL cũng cần được cập nhật.

Không cấp quyền đọc mọi group hoặc mọi topic cho một consumer. Nếu ứng dụng có nhiều input binding, lập danh sách từng topic và group cần thiết.

## 9. Kafka: quyền cho provisioner

Provisioner có thể cần quyền khác hẳn producer/consumer:

| Tác vụ provisioning | Quyền Kafka thường cần |
|---|---|
| Tạo topic | `Create` trên topic hoặc cluster theo policy |
| Tăng partition | `Alter` trên topic |
| Đọc metadata | `Describe` trên topic |
| Đọc cấu hình topic | `DescribeConfigs` trên topic |
| Sửa cấu hình topic | `AlterConfigs` trên topic |
| Xóa topic | `Delete` trên topic |
| Quản lý ACL | `Alter` trên Cluster resource |

Quyền chính xác phụ thuộc Kafka version, authorizer và thao tác Admin API mà công cụ provisioning thực hiện. Hãy cấp theo resource cụ thể, không cấp `All` trên Cluster cho mọi ứng dụng.

Spring Cloud Stream Kafka binder có các cờ provisioning:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
~~~

- `auto-create-topics=false`: binder dựa vào topic đã được tạo trước; nếu topic chưa tồn tại, ứng dụng không khởi động binding thành công.
- `auto-add-partitions=false`: binder không tự thêm partition nếu topic chưa đủ số lượng yêu cầu.

Đây là cấu hình hữu ích khi platform quản lý topic và ACL. Lưu ý broker vẫn có thể tự tạo topic khi `auto.create.topics.enable` được bật; cờ của binder không thay thế cấu hình auto-create phía broker.

## 10. Kafka: xác thực TLS và SASL trong Spring Cloud Stream

Kafka binder nhận các thuộc tính bảo mật Kafka qua `spring.cloud.stream.kafka.binder.configuration`.

Ví dụ dùng SASL/SCRAM qua TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            "security.protocol": SASL_SSL
            "sasl.mechanism": SCRAM-SHA-512
            "sasl.jaas.config": ${KAFKA_SASL_JAAS_CONFIG}
~~~

Giá trị `KAFKA_SASL_JAAS_CONFIG` được cung cấp từ secret store hoặc môi trường triển khai. Không đặt username/password thật trong file cấu hình được commit.

Kafka cũng hỗ trợ SSL client certificate, SASL/PLAIN, Kerberos và các cơ chế khác tùy broker. Cấu hình phải khớp listener và authentication mechanism của cluster.

Nếu ứng dụng kết nối nhiều Kafka cluster có credential khác nhau, cấu hình binder riêng cho từng cluster. Không dùng một principal có quyền trên tất cả cluster chỉ để giảm số lượng cấu hình.

## 11. Kafka: tách quyền cho retry, DLT và Kafka Streams

Một consumer có retry/DLT không còn chỉ đọc input topic. Nếu binder hoặc error handler publish record lỗi sang DLT, identity xử lý lỗi cần quyền ghi vào DLT đó.

Ví dụ:

| Resource | Consumer chính | Consumer có DLT |
|---|---:|---:|
| `orders.created.v1` | Read | Read |
| `orders.created.dlt` | Không | Write |
| `orders-projection-prod-v1` group | Read | Read |

Nếu dùng retry topic, cần bổ sung quyền đọc/ghi cho các retry topic theo cấu hình thực tế. Không cấp wildcard topic chỉ vì chưa biết binder tạo tên nội bộ nào; hãy xác định tên resource từ cấu hình và metadata broker.

Kafka Streams có thể cần thêm quyền cho:
- Source topics: Read/Describe.
- Sink topics: Write/Describe.
- Internal changelog/repartition topics: các quyền đọc/ghi và tạo cần thiết theo topology.
- Streams application group: các quyền group tương ứng.
- Transactional IDs nếu bật exactly-once processing.

Các internal topic thường có prefix theo application ID. Có thể dùng resource pattern dạng prefix để giới hạn một họ topic, nhưng phải chọn prefix đủ hẹp và kiểm tra không bao phủ workload khác.

## 12. RabbitMQ: vhost, resource permission và topic permission

RabbitMQ chia quyền thành ba lớp:

1. **Virtual host:** ranh giới chứa exchange, queue và binding.
2. **Resource permission:** quyền `configure`, `write`, `read` áp dụng cho tên exchange/queue trong vhost.
3. **Topic permission:** có thể giới hạn routing key trên topic exchange.

Ý nghĩa:

| Permission | Thao tác |
|---|---|
| `configure` | Tạo, xóa hoặc thay đổi exchange/queue |
| `write` | Publish vào exchange hoặc thực hiện thao tác bind/unbind trên resource đích |
| `read` | Consume/get message từ queue hoặc thực hiện bind theo resource nguồn |

Mỗi user chỉ được thao tác trong virtual host mà nó được cấp quyền. Cùng tên queue ở hai vhost là hai resource khác nhau.

Không dùng user mặc định `guest` cho service production. Hãy tạo service account riêng, credential riêng và vhost riêng theo domain hoặc môi trường.

## 13. RabbitMQ: quyền tối thiểu cho publisher

Với AMQP 0-9-1, thao tác `basic.publish` cần `write` trên exchange đích. Nếu exchange đã được tạo trước và client không cần khai báo resource, publisher không cần quyền `configure`.

Ví dụ chỉ cho phép `orders-publisher` ghi vào exchange `orders.created` trong vhost `orders-prod`:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-publisher \
  '^$' \
  '^orders\.created$' \
  '^$'
~~~

Thứ tự ba biểu thức là:

1. configure.
2. write.
3. read.

`^$` khớp tên rỗng, tức không cấp quyền với resource có tên thông thường. `^orders\.created$` giới hạn quyền write vào đúng exchange.

Nếu publisher cần khai báo exchange lúc khởi động, nó sẽ cần configure permission tương ứng. Trong production, có thể để provisioner tạo exchange và giữ publisher ở quyền write-only.

## 14. RabbitMQ: quyền tối thiểu cho consumer

Với AMQP 0-9-1, `basic.consume` cần `read` trên queue. Nếu queue và binding đã tồn tại, consumer không cần quyền publish vào exchange.

Ví dụ chỉ cho phép consumer đọc queue `orders.created.orders-projection`:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-projection \
  '^$' \
  '^$' \
  '^orders\.created\.orders-projection$'
~~~

Queue và exchange cần được provision trước. Nếu binder vẫn khai báo exchange, queue hoặc binding khi startup, nó có thể cần thêm quyền configure/write/read theo đúng thao tác AMQP được thực hiện.

RabbitMQ 4.3.1 trở lên cho phép passive declaration khi user có ít nhất một trong ba quyền trên resource; tuy nhiên, non-passive declaration vẫn cần configure. Kiểm tra broker version nếu binder dùng passive declaration để xác minh resource.

## 15. RabbitMQ: provisioning và quyền bind queue

Khi binder tự động tạo exchange, queue và binding, provisioner cần quyền rộng hơn runtime consumer/publisher.

Ví dụ queue `orders.created.orders-projection` được bind vào exchange `orders.created`:

- Tạo exchange cần configure trên exchange.
- Tạo queue cần configure trên queue.
- Bind queue vào exchange cần write trên queue đích và read trên exchange nguồn.

Ví dụ quyền provisioner cho đúng hai resource:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-provisioner \
  '^(orders\.created|orders\.created\.orders-projection)$' \
  '^orders\.created\.orders-projection$' \
  '^orders\.created$'
~~~

Nếu có dead-letter exchange/queue, retry queue hoặc alternate exchange, cần thêm đúng tên resource vào biểu thức. Không mở `.*` trên cả vhost chỉ để tránh lỗi provisioning.

Với Rabbit binder, mặc định binder có thể tự tạo topic exchange, queue và binding. Khi dùng resource đã được quản trị tạo sẵn, tài liệu binder cho phép tắt provisioning ở consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: orders-projection

      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              bind-queue: false
              declare-exchange: false
~~~

Với destination `orders.created` và group `orders-projection`, tên queue mặc định là `orders.created.orders-projection`; vì vậy cấu hình không bật `queue-name-group-only`. Ví dụ giả định exchange/queue đã tồn tại và queue đã được bind đúng. Với output binding, tắt khai báo exchange bằng `spring.cloud.stream.rabbit.bindings.<binding-name>.producer.declare-exchange=false` khi exchange được provision trước.

Ví dụ output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created

      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              declare-exchange: false
~~~

## 16. RabbitMQ: giới hạn routing key

Với topic exchange, quyền resource `write` cho phép publish vào exchange. RabbitMQ còn hỗ trợ topic authorization để giới hạn routing key đối với các protocol/flow có áp dụng.

Ví dụ publisher chỉ được phát routing key bắt đầu bằng `orders.created.`:

~~~bash
rabbitmqctl set_topic_permissions \
  -p orders-prod \
  orders-publisher \
  orders.created \
  '^orders\.created\..*$' \
  '^$'
~~~

Topic permission là lớp bổ sung; nó không thay thế quyền write trên exchange. Với AMQP 0-9-1, consumer thường consume từ queue, còn routing key được kiểm tra trong một số thao tác binding của topic exchange.

Chọn resource permission và topic permission theo giao thức thực tế. Không giả định routing-key ACL của MQTT/STOMP có cùng semantics với consumer queue của AMQP 0-9-1.

## 17. Pulsar: role, tenant và namespace

Pulsar dùng role để đại diện cho client đã xác thực. Authorization có thể cấp quyền ở phạm vi namespace hoặc topic.

Các action thường dùng:

- `produce`: publish message.
- `consume`: subscribe/consume message.

Ví dụ topic:

~~~text
persistent://acme/orders-prod/orders-created-v1
~~~

Trong đó:

- `acme` là tenant.
- `orders-prod` là namespace.
- `orders-created-v1` là topic.

Namespace là phạm vi quản trị phù hợp để nhóm các topic liên quan. Nếu role chỉ cần một topic, ưu tiên topic-level permission khi policy và phiên bản triển khai hỗ trợ; nếu role cần nhiều topic trong một namespace, cấp namespace permission có thể đơn giản hơn nhưng phạm vi rộng hơn.

Pulsar phân biệt authentication và authorization. Nếu chỉ bật authentication mà không bật authorization, role đã xác thực có thể được truy cập rộng theo cấu hình broker. Superuser có thể tạo/xóa tenant và có quyền rất lớn trên tài nguyên. Không dùng superuser role cho producer hoặc consumer runtime.

## 18. Pulsar: quyền tối thiểu cho producer và consumer

Cấp quyền produce cho producer role:

~~~bash
pulsar-admin namespaces grant-permission acme/orders-prod \
  --role orders-publisher \
  --actions produce
~~~

Cấp quyền consume cho consumer role:

~~~bash
pulsar-admin namespaces grant-permission acme/orders-prod \
  --role orders-projection \
  --actions consume
~~~

Hai role có quyền khác nhau trên cùng namespace. Producer không cần consume; consumer không cần produce nếu không phát event đầu ra.

Nếu ứng dụng vừa consume từ namespace này vừa publish sang namespace khác, cấp từng action riêng trên từng namespace. Không cấp `produce,consume` cho tất cả namespace chỉ để dùng một credential chung.

Quyền quản trị subscription, xóa topic, clear backlog hoặc thay policy có thể cần role admin cao hơn tùy thao tác và cấu hình authorization. Không đưa các quyền đó vào runtime consumer chỉ vì ứng dụng có subscription.

## 19. Pulsar: provisioning là quyền quản trị riêng

Tạo tenant, namespace, topic partitioned, thay policy hoặc cấp/revoke role là nhiệm vụ quản trị.

Pulsar có thể cấp quyền namespace cho role và có API quản lý quyền ở topic. Một tenant admin có thể quản lý namespace và grant/revoke quyền. Superuser có quyền rộng hơn nữa.

Spring Cloud Stream Pulsar binder có topic provisioner. Tài liệu binder mô tả provisioner dùng `PulsarAdministration` (PulsarAdmin) để tạo topic khi cần; vì vậy nó có thể cần thông tin kết nối admin và quyền quản trị phù hợp.

Đây là điểm cần lưu ý khi triển khai least privilege:

- `PulsarClient` runtime dùng để publish/consume.
- `PulsarAdmin` dùng cho provisioning và thao tác quản trị.
- Không đặt superuser token vào workload chỉ để topic được tạo lúc startup.
- Tạo tenant, namespace và topic bằng pipeline/platform role trước khi deploy.
- Kiểm tra hành vi provisioner của binder đúng phiên bản đang dùng; nếu binder vẫn gọi admin API, cần thiết kế bước provisioning hoặc cấu hình admin identity riêng theo môi trường triển khai, không âm thầm cấp superuser cho runtime.

Không suy luận rằng topic đã tồn tại thì provisioner chắc chắn không cần quyền admin. Hãy xác minh bằng integration test với đúng role runtime và cấu hình binder thực tế.

## 20. Pulsar: xác thực client trong Spring Boot

Pulsar binder sử dụng các thành phần của Spring for Apache Pulsar, nên các thuộc tính client của Spring Boot có thể dùng trong ứng dụng binder.

Ví dụ token authentication:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
~~~

Tên plugin và tham số phải đúng với authentication provider trên cluster. Không đặt token thật trong source control. TLS cần được cấu hình phù hợp với Spring Pulsar và phiên bản Spring Boot; ở các phiên bản mà auto-configuration chưa có đủ TLS property, dùng `PulsarClientBuilderCustomizer` theo hướng dẫn chính thức.

Nếu dùng OAuth2, token hoặc mTLS, hãy dùng identity gắn với service runtime. Certificate/private key phải được bảo vệ như secret và có kế hoạch rotation.

Nếu ứng dụng dùng PulsarAdmin cho provisioning, cấu hình xác thực admin phải được quản lý tách biệt với client runtime. Không dùng cùng token superuser cho cả hai chỉ để tiện cấu hình.

## 21. Cấu hình RabbitMQ connection trong Spring Boot

Rabbit binder thông thường dùng Spring AMQP/Rabbit connection factory. Ví dụ cấu hình connection tới vhost riêng:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.example
    port: 5671
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: orders-prod
    ssl:
      enabled: true
~~~

Tài khoản ở đây phải là user runtime đã được cấp permission trên vhost `orders-prod`. Không dùng tài khoản management administrator để chạy producer/consumer.

Với RabbitMQ, quyền trên vhost và quyền trên exchange/queue là hai điều kiện khác nhau. Client cần có quyền truy cập vhost và đúng resource permissions cho thao tác AMQP.

Nếu dùng OAuth2 hoặc certificate-based authentication, cấu hình auth backend và TLS theo chính sách broker. Không chỉ đổi username/password trong ứng dụng mà bỏ qua quyền resource ở phía RabbitMQ.

## 22. Cấu hình Kafka binding với identity runtime

Ví dụ service chỉ đọc topic và dùng consumer group riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created.v1
          group: orders-projection-prod-v1

      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
          configuration:
            "security.protocol": SASL_SSL
            "sasl.mechanism": SCRAM-SHA-512
            "sasl.jaas.config": ${KAFKA_SASL_JAAS_CONFIG}
~~~

Credential Kafka được ánh xạ tới principal đã có ACL Read/Describe trên topic và Read trên group; thêm Describe trên group nếu client cần fetch/inspect committed offsets. Không thêm quyền Create topic cho consumer này nếu topic đã tồn tại.

Nếu ứng dụng có nhiều binding với nhiều destination, ACL phải bao phủ đúng từng destination và group. Không dùng một prefix rộng hơn cần thiết.

## 23. Cấu hình nhiều binding với các quyền khác nhau

Một ứng dụng có thể vừa consume vừa publish. Ví dụ function nhận đơn hàng, xử lý và phát event đã chuẩn hóa:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(
        order.orderId(),
        "ACCEPTED"
    );
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder

    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created.v1
          group: order-acceptance-prod-v1

        acceptOrder-out-0:
          destination: orders.accepted.v1
~~~

Runtime identity cần:

- Read/Describe trên `orders.created.v1`.
- Read trên group `order-acceptance-prod-v1`.
- Write/Describe trên `orders.accepted.v1`.

Nó không cần quyền đọc `orders.accepted.v1`, tạo topic hoặc xóa resource. Nếu function có retry/DLT, thêm quyền publish tới resource lỗi tương ứng và chỉ resource đó.

Nếu producer và consumer thuộc các service độc lập, nên dùng credential riêng cho mỗi service. Nếu một JVM có nhiều binder/cluster, có thể cấu hình identity riêng cho từng binder để tránh quyền của cluster A bị trộn với cluster B.

## 24. Credential, secret và rotation

Credential của broker là secret vận hành. Không lưu secret trực tiếp trong:

- Git repository.
- Docker image hoặc build artifact.
- Log ứng dụng.
- Exception message hoặc Actuator response.
- File test dùng chung.
- Command line history hoặc script công khai.

Nên lấy secret từ Vault, cloud secret manager, Kubernetes Secret hoặc cơ chế secret store của nền tảng. Dùng biến môi trường chỉ là ví dụ truyền giá trị; với hệ thống production, secret store và quyền đọc secret cần được kiểm soát.

Quy trình rotation:

1. Tạo credential mới cho cùng service identity hoặc identity thay thế.
2. Cấp ACL tương đương nhưng vẫn giới hạn đúng resource.
3. Cập nhật secret store.
4. Restart/refresh workload theo cơ chế hỗ trợ.
5. Xác minh producer/consumer hoạt động với credential mới.
6. Thu hồi credential cũ.
7. Kiểm tra log broker để bảo đảm không còn client dùng credential cũ.

Không xoay credential bằng cách cấp quyền admin tạm thời rồi quên thu hồi. Credential rotation phải giữ nguyên phạm vi quyền cần thiết.

## 25. TLS và bảo vệ đường truyền

ACL không mã hóa message trên đường truyền. Cần kết hợp authentication, authorization và TLS.

- Kafka: dùng SASL_SSL hoặc SSL/mTLS tùy cluster.
- RabbitMQ: dùng AMQPS/TLS và xác thực certificate nếu được cấu hình.
- Pulsar: dùng `pulsar+ssl://`, TLS trust material và authentication plugin.
- Kiểm tra hostname verification và trust chain.
- Không tắt certificate validation để “sửa nhanh” lỗi kết nối.
- Giữ private key trong secret store hoặc file mount có quyền đọc tối thiểu.

TLS bảo vệ đường truyền và xác minh endpoint; nó không thay thế ACL. Một client có TLS hợp lệ vẫn phải bị từ chối nếu principal không có quyền publish/consume.

## 26. Quyền phụ cho schema, retry và dead-letter

Luồng xử lý thực tế có thể chạm thêm resource ngoài topic input/output chính.

| Thành phần | Quyền có thể cần |
|---|---|
| Schema Registry | Đọc schema hoặc đăng ký schema theo subject |
| Kafka retry topic | Read/Write trên retry topic và group liên quan |
| Kafka DLT | Write trên DLT nếu ứng dụng publish record lỗi |
| Rabbit DLX/DLQ | Provisioner tạo exchange/queue/binding; consumer cần quyền phù hợp nếu tự khai báo |
| Pulsar DLQ | Produce vào topic lỗi nếu client tự publish |
| Pulsar schema | Lookup/produce permission theo schema operation và authorization provider |
| Kafka Streams internal topics | Quyền trên changelog/repartition topics và group |
| Monitoring | Đọc metadata/metrics; không mặc định đọc message payload |

Không cấp quyền cho toàn bộ retry/DLT namespace nếu chỉ có một binding cần dùng. Ghi lại tên resource mà binder tạo, sau đó cấp quyền đúng prefix hoặc exact name.

Khi bật DLQ trong Kafka binder, consumer có thể vừa đọc input vừa ghi DLT. Hãy kiểm tra ACL cho cả hai hướng. Với Rabbit binder, nếu autoBindDlq tạo exchange/queue/binding thì identity khai báo cần quyền configure/write/read tương ứng; có thể pre-provision resource để runtime không phải giữ quyền quản trị.

## 27. Kiểm tra ACL và quyền thực tế

Không chỉ dựa vào file cấu hình Spring Boot. Phải kiểm tra policy ở broker.

### Kafka

Liệt kê ACL của principal:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --list \
  --principal User:orders-projection-prod
~~~

Kiểm tra:
- Topic input có Read/Describe không.
- Group có Read và Describe theo API/client đang dùng không.
- Output/DLT chỉ có Write khi cần.
- Không có ACL wildcard ngoài phạm vi.
- Provisioner role không bị dùng trong pod runtime.

### RabbitMQ

Liệt kê quyền theo vhost:

~~~bash
rabbitmqctl list_permissions -p orders-prod
rabbitmqctl list_user_permissions orders-projection
~~~

Kiểm tra regex configure/write/read có giới hạn đúng queue/exchange. Nếu vừa đổi permission mà client vẫn bị từ chối, kiểm tra kết nối/channel vì RabbitMQ có thể cache kết quả kiểm tra quyền; client có thể cần reconnect.

### Pulsar

Kiểm tra quyền namespace:

~~~bash
pulsar-admin namespaces permissions acme/orders-prod
~~~

Kiểm tra role producer chỉ có produce và consumer chỉ có consume. Nếu có topic-level permission, kiểm tra thêm quyền trên topic. Xác nhận authorization đã được bật ở broker; nếu chưa bật, kết quả kiểm tra role không thể chứng minh runtime bị giới hạn như mong đợi.

## 28. Kiểm thử positive và negative authorization

Một bài kiểm thử phân quyền phải chứng minh cả thao tác được phép và thao tác bị từ chối.

| Identity | Thao tác | Kết quả mong đợi |
|---|---|---|
| Producer | Publish đúng output topic | Thành công |
| Producer | Consume input topic | Bị từ chối |
| Producer | Tạo topic mới | Bị từ chối |
| Consumer | Read đúng input topic/group | Thành công |
| Consumer | Publish vào input topic | Bị từ chối |
| Consumer | Read topic khác | Bị từ chối |
| Consumer | Tạo hoặc xóa queue/topic | Bị từ chối |
| Provisioner | Tạo resource được giao | Thành công |
| Provisioner | Xóa resource ngoài phạm vi | Bị từ chối |
| Monitoring | Đọc metadata/metrics được cấp | Thành công |
| Monitoring | Publish hoặc consume payload | Bị từ chối nếu không có nhu cầu |

Kiểm thử negative rất quan trọng. Nếu chỉ kiểm tra producer gửi được message, ta chưa biết producer có vô tình được quyền đọc hoặc xóa resource khác hay không.

Có thể viết integration test với Kafka Testcontainers, RabbitMQ Testcontainers hoặc Pulsar Testcontainers. Test phải dùng chính credential/role đã được cấp ACL, không dùng administrator credentials để chạy assertion.

## 29. Lỗi thường gặp khi cấu hình least privilege

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Kafka producer bị TopicAuthorizationFailed | Thiếu Write hoặc Describe trên topic | Cấp quyền đúng topic |
| Kafka consumer bị GroupAuthorizationFailed | Thiếu Read trên consumer group | Cấp Read trên đúng group |
| Kafka producer không khởi động | Binder cố tạo topic nhưng principal không có Create | Pre-provision topic và tắt autoCreateTopics |
| Kafka Streams lỗi internal topic | Thiếu quyền trên changelog/repartition topic | Cấp quyền theo prefix internal topic của application |
| Rabbit publisher bị ACCESS_REFUSED | Thiếu write trên exchange hoặc sai vhost | Kiểm tra vhost và resource regex |
| Rabbit consumer không bind queue | Binder đang tự khai báo/bind nhưng role thiếu configure/write/read | Pre-provision và tắt provisioning hoặc cấp đúng quyền |
| Rabbit consumer không đọc được | Thiếu read trên queue | Kiểm tra queue name và permission regex |
| Pulsar client xác thực được nhưng publish bị từ chối | Authentication đã bật nhưng role thiếu produce | Bật authorization và grant produce |
| Pulsar consumer không subscribe | Thiếu consume hoặc sai namespace/subscription policy | Kiểm tra role và subscription |
| Pulsar binder không tạo topic | Provisioner thiếu quyền admin hoặc admin service URL | Tách provisioning role và xác minh PulsarAdministration |
| Chạy local được nhưng production lỗi | Local broker dùng quyền rộng hơn | Test với service account production-like |
| Rotation xong vẫn bị từ chối | Client còn kết nối bằng credential cũ | Reconnect/restart và xác minh broker principal |
| Retry/DLT không hoạt động | Consumer thiếu quyền ghi DLT hoặc retry topic | Cấp thêm đúng resource phụ |
| Permission thay đổi chưa có hiệu lực | Connection/channel cũ còn cache quyền | Tạo kết nối mới và kiểm tra lại |

## 30. Checklist trước khi triển khai

| Hạng mục | Câu hỏi |
|---|---|
| Identity | Mỗi service và môi trường đã có service account riêng chưa? |
| Producer | Chỉ có quyền publish vào output topic/exchange cần thiết chưa? |
| Consumer | Chỉ có quyền đọc input và group/subscription tương ứng chưa? |
| Provisioner | Có danh tính quản trị riêng cho việc tạo resource không? |
| Binder | Có tự động tạo topic/queue/exchange khi startup không? |
| Kafka | autoCreateTopics/autoAddPartitions đã phù hợp với ACL chưa? |
| RabbitMQ | Vhost và regex configure/write/read đã giới hạn đúng chưa? |
| Pulsar | Authorization đã bật và role có đúng produce/consume action chưa? |
| DLQ/retry | Các resource phụ đã được tính vào ACL chưa? |
| Schema | Quyền schema registry/Pulsar schema đã tách riêng chưa? |
| Secret | Credential lấy từ secret store và không nằm trong Git/log chưa? |
| TLS | Kết nối có mã hóa và xác minh certificate không? |
| Rotation | Có quy trình cấp mới, xác minh và thu hồi credential cũ không? |
| Negative test | Producer/consumer có bị từ chối đúng các thao tác không được phép không? |
| Audit | Có thể truy nguyên principal nào đã publish/consume/provision không? |

## 31. Bài thực hành: tách publisher, consumer và provisioner

Xây dựng luồng đơn hàng với destination `orders.created.v1`.

### Bước 1: xác định danh tính

Tạo ba identity riêng:

- `orders-api-prod`: producer.
- `orders-projection-prod`: consumer.
- `orders-provisioner-prod`: provisioner.

### Bước 2: xác định resource

- Kafka: topic `orders.created.v1`, group `orders-projection-prod-v1`.
- RabbitMQ: vhost `orders-prod`, exchange `orders.created`, queue `orders.created.orders-projection`.
- Pulsar: namespace `acme/orders-prod`, topic `orders-created-v1`, subscription `orders-projection-prod-v1`.

### Bước 3: cấp quyền

- Producer chỉ publish vào destination đầu ra.
- Consumer chỉ consume destination đầu vào và group/subscription riêng.
- Provisioner tạo resource và cấp/revoke quyền; không dùng credential này trong workload nghiệp vụ.

### Bước 4: cấu hình binder

- Cấu hình Kafka SASL_SSL, RabbitMQ TLS hoặc Pulsar token/mTLS.
- Đặt binding destination và group rõ ràng.
- Tắt hoặc tránh auto-provision trong runtime nếu platform quản lý resource trước.
- Đưa credential vào secret store.

### Bước 5: kiểm thử

- Producer publish thành công.
- Consumer đọc được message.
- Producer không thể consume.
- Consumer không thể publish vào input topic.
- Runtime role không thể tạo hoặc xóa resource.
- Provisioner chỉ thay đổi resource được giao.
- Thử rotation credential và xác nhận credential cũ không còn dùng được.

Hoàn thành bài khi có thể giải thích authentication khác authorization; tách được producer, consumer và provisioner identity; cấp ACL cụ thể cho Kafka, RabbitMQ và Pulsar; cấu hình binder không cần quyền quản trị ngoài ý muốn; và chứng minh các thao tác trái quyền bị broker từ chối.

## 32. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html) — SASL, JAAS, SSL và cấu hình security properties cho Kafka binder.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — autoCreateTopics, autoAddPartitions và các cấu hình provisioning.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/) — principal, resource, operation, group/topic/transactional ID và ACL.
- [RabbitMQ — Authentication, Authorisation, Access Control](https://www.rabbitmq.com/docs/access-control) — vhost, configure/write/read, topic permission và quản lý user.
- [Spring Cloud Stream — Using Existing Queues/Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html) — tắt provisioning exchange/queue khi dùng resource đã tạo trước.
- [Spring Cloud Stream — Rabbit Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html) — `declareExchange`, DLQ và các thuộc tính producer.
- [Spring Boot — AMQP Configuration](https://docs.spring.io/spring-boot/reference/messaging/amqp.html) — username, password, virtual host và SSL cho RabbitMQ.
- [Apache Pulsar — Authentication and Authorization](https://pulsar.apache.org/docs/5.0.x/security-authorization/) — role, superuser, tenant, namespace và authorization.
- [Apache Pulsar — Namespace Admin API](https://pulsar.apache.org/api/admin/5.0.x/org/apache/pulsar/client/admin/Namespaces.html) — grant/revoke produce và consume permission.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — Spring Pulsar client properties, extended binding properties và topic provisioner.
- [Spring Boot — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html) — client authentication và TLS.

