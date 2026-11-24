# Quản lý tài nguyên broker theo môi trường

Một ứng dụng Spring Cloud Stream có thể chạy ở local, development, test, staging và production, nhưng mỗi môi trường có tải, mức độ quan trọng, yêu cầu bảo mật và ngân sách khác nhau. Quản lý broker theo môi trường nghĩa là cấp phát đúng tài nguyên cho từng giai đoạn, cô lập dữ liệu và quyền truy cập, kiểm soát dung lượng, retention, replication, quota và kết nối, đồng thời giữ cấu hình có thể tái lập khi triển khai.

Binder chỉ giúp ứng dụng kết nối với broker. Nó không thay thế công việc quản trị cluster, topic, queue, namespace, storage, quota, ACL hoặc chính sách backup. Cần tách rõ cấu hình của ứng dụng khỏi tài nguyên hạ tầng do nền tảng cấp phát.

## 1. Vì sao phải quản lý tài nguyên theo môi trường?

Một môi trường development thường cần chi phí thấp, dễ tạo/xóa và dữ liệu thử nghiệm ngắn hạn. Production cần khả năng chịu lỗi, dung lượng dự phòng, kiểm soát truy cập, giám sát và quy trình khôi phục. Nếu dùng chung broker hoặc namespace mà không có ranh giới rõ ràng, test có thể làm đầy queue production, developer có thể đọc dữ liệu nhạy cảm hoặc một lần deploy có thể thay đổi cấu hình của dịch vụ khác.

Các mục tiêu chính:

- **Cô lập:** dữ liệu, credential, quota và quyền của từng môi trường có ranh giới rõ.
- **Đúng dung lượng:** partition, queue, storage, throughput và connection phù hợp với tải.
- **Độ bền:** replication, retention, backup và disaster recovery theo mức quan trọng.
- **Bảo mật:** TLS, authentication, ACL/RBAC và secret rotation.
- **Khả năng tái lập:** tài nguyên được khai báo bằng Infrastructure as Code (IaC), có review và lịch sử thay đổi.
- **Kiểm soát chi phí:** môi trường không dùng không giữ tài nguyên lớn hoặc dữ liệu vô hạn.
- **Vận hành nhất quán:** naming, monitoring, alert và runbook có chuẩn chung.

## 2. Phân loại môi trường và mức dịch vụ

Không nên cấp cùng một cấu hình cho mọi môi trường. Ma trận dưới đây là điểm khởi đầu; giá trị thực tế phụ thuộc tải, SLA, chính sách công ty và khả năng broker.

| Môi trường | Mục tiêu | Tài nguyên gợi ý | Dữ liệu và retention |
|---|---|---|---|
| Local | Phát triển nhanh trên máy cá nhân | Một broker đơn giản hoặc container; ít partition; dung lượng nhỏ | Dữ liệu giả, có thể xóa/reset |
| Development | Tích hợp nhóm và kiểm tra chức năng | Cluster dùng chung có namespace/vhost/topic riêng; quota thấp | Dữ liệu tổng hợp, retention ngắn |
| Test/CI | Chạy tự động, cô lập test | Broker ephemeral hoặc namespace riêng; tự động tạo và dọn | Dữ liệu chỉ tồn tại trong vòng đời test |
| Staging | Mô phỏng gần production | Topology, TLS, ACL, partition và policy tương tự production ở quy mô nhỏ hơn | Dữ liệu giả hoặc đã ẩn danh; retention đủ cho kiểm thử |
| Production | Phục vụ nghiệp vụ | Cluster HA, replication, quota, capacity headroom, backup/DR | Dữ liệu theo hợp đồng lưu trữ và yêu cầu tuân thủ |

Một cluster dùng chung cho nhiều môi trường chỉ phù hợp khi có cách ly đủ mạnh: tenant/vhost/namespace, credential, ACL, quota, naming và monitoring riêng. Với dữ liệu nhạy cảm hoặc workload có mức độ quan trọng cao, nên cân nhắc cluster riêng để tránh noisy neighbor và giảm blast radius.

## 3. Xác định ranh giới tài nguyên và ownership

Trước khi tạo topic hoặc queue, lập danh mục tài nguyên cho từng service và môi trường:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| Environment | dev, staging, prod | Chọn cluster và chính sách |
| Service | order-stream | Xác định owner |
| Binder type | kafka, rabbit, pulsar | Xác định hệ messaging |
| Destination | orders.created | Topic, exchange/queue hoặc Pulsar topic |
| Consumer group/subscription | order-projection-v1 | Tách tiến độ xử lý |
| Retention/TTL | 3 ngày, 7 ngày | Giới hạn vòng đời dữ liệu |
| Partition/replica | 12 partition, RF 3 | Throughput và độ bền |
| Quota | 20 MB/s, 100 connection | Giới hạn tài nguyên |
| Data classification | internal, confidential | Chọn quyền và chính sách lưu trữ |
| Owner/contact | đội Order Platform | Người chịu trách nhiệm |

Mỗi tài nguyên nên có owner, purpose, environment, ngày tạo hoặc ticket tham chiếu và chính sách cleanup. Tránh destination vô chủ hoặc tên chung như test-topic được nhiều đội dùng không kiểm soát.

Quy ước tên có thể gồm service, môi trường và mục đích, ví dụ:

    dev.order-stream.orders.created
    staging.order-stream.orders.created
    prod.order-stream.orders.created

Cách đặt tên thực tế tùy broker. Kafka topic thường không có cấu trúc tenant/namespace bắt buộc; RabbitMQ dùng virtual host, exchange và queue; Pulsar dùng tenant/namespace/topic. Dù cấu trúc khác nhau, tên nên cho biết owner và môi trường mà không đưa dữ liệu nhạy cảm vào tên.

## 4. Cấu hình Spring Cloud Stream theo môi trường

Ứng dụng nên lấy endpoint và credential từ profile, biến môi trường hoặc secret manager. Không commit địa chỉ production, password, token, truststore password hoặc private key vào repository.

Ví dụ cấu hình binding dùng chung:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: ${ORDERS_INPUT_DESTINATION}
              group: ${ORDERS_CONSUMER_GROUP}
              consumer:
                concurrency: ${ORDERS_CONCURRENCY:1}
            processOrder-out-0:
              destination: ${ORDERS_OUTPUT_DESTINATION}

Các biến môi trường được cung cấp theo môi trường triển khai. Tên destination và consumer group phải ổn định theo hợp đồng; không để test và production vô tình dùng chung group.

### 4.1. Kafka Binder

Ví dụ cấu hình kết nối Kafka:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: ${KAFKA_BOOTSTRAP_SERVERS}
              auto-create-topics: false
              auto-add-partitions: false

Production thường nên để quy trình hạ tầng tạo topic và partition trước khi ứng dụng khởi động. Tắt auto-create/auto-add giúp tránh ứng dụng vô tình tạo topic với partition count hoặc cấu hình retention mặc định không phù hợp. Với local/dev, có thể bật auto-create nếu được kiểm soát và broker được dùng riêng cho môi trường đó.

Kafka Binder có các thuộc tính kết nối broker và cấu hình producer/consumer. Những thuộc tính như topic retention, replication factor, min.insync.replicas, cleanup.policy, broker quota và ACL thuộc lớp quản trị Kafka; không nên giả định chỉ đặt chúng trong binding là broker sẽ áp dụng. Một số binder property hỗ trợ tạo topic hoặc partition, nhưng resource policy vẫn cần được quản lý theo cơ chế của cluster.

### 4.2. RabbitMQ Binder

Ứng dụng có thể nhận địa chỉ broker qua Spring Boot Rabbit connection properties:

    spring:
      rabbitmq:
        addresses: ${RABBITMQ_ADDRESSES}
        username: ${RABBITMQ_USERNAME}
        password: ${RABBITMQ_PASSWORD}
      cloud:
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-projection

RabbitMQ thường dùng virtual host để cô lập tài nguyên và quyền. Tên exchange, queue, binding, DLX, policy TTL, max-length, quorum queue và user permission cần được tạo hoặc quản lý bằng IaC/automation. Ứng dụng không nên dùng tài khoản administrator của broker để chạy consumer.

### 4.3. Pulsar Binder

Spring for Apache Pulsar cung cấp client configuration, còn Pulsar Binder nối binding với topic/subscription:

    spring:
      pulsar:
        client:
          service-url: ${PULSAR_SERVICE_URL}
      cloud:
        stream:
          bindings:
            processOrder-in-0:
              destination: persistent://${PULSAR_TENANT}/${PULSAR_NAMESPACE}/orders.created
              group: order-projection

Pulsar có tenant và namespace để tổ chức topic cùng policy. Administration endpoint và authentication có thể cần cấu hình riêng tùy Spring Boot/Spring Pulsar version. Tenant, namespace, retention, backlog quota, replication cluster và permission nên được provision bởi platform/IaC. Không dùng admin credential rộng quyền làm credential runtime cho ứng dụng.

Tên property cụ thể và khả năng provision khác nhau theo phiên bản Spring Cloud Stream, binder và Spring Boot. Quản lý version qua BOM, kiểm tra configuration metadata của release đang dùng và xác nhận effective config ở staging trước khi phát hành.

## 5. Tách cấu hình kết nối khỏi cấu hình tài nguyên broker

Cấu hình ứng dụng và cấu hình broker có mục đích khác nhau:

| Cấu hình ứng dụng/binder | Cấu hình broker/platform |
|---|---|
| Broker endpoint, credentials, TLS trust | Cluster size, broker node, storage pool |
| Destination và consumer group | Topic/queue/namespace creation |
| Consumer concurrency, retry, ack mode | Partition count, replication, queue type |
| Producer batching, compression, timeout | Retention, quota, storage policy |
| Binding content type và Serde | ACL, role, vhost permission |
| Client ID và connection settings | Broker network, listener, disk alert |

Ví dụ, đặt destination là orders.created không tự động bảo đảm topic có 12 partition, replication factor 3 hoặc retention 7 ngày. Cần kiểm tra topic thực tế qua broker admin API/CLI hoặc IaC state.

## 6. Quản lý tài nguyên Kafka theo môi trường

Kafka resource cần được quản lý ở cấp cluster và topic. Các quyết định chính:

- **Partition count:** dựa trên throughput, consumer parallelism và key distribution.
- **Replication factor:** số bản sao partition; production thường cần nhiều replica trên các broker khác nhau.
- **min.insync.replicas:** số replica đồng bộ tối thiểu cho producer yêu cầu acks phù hợp.
- **Retention:** thời gian hoặc dung lượng lưu record trước khi broker xóa.
- **Cleanup policy:** delete, compact hoặc kết hợp theo mục đích topic.
- **Quota:** giới hạn produce/consume throughput hoặc request theo principal/client.
- **ACL:** quyền read/write/describe/create theo topic và group.
- **Storage:** disk capacity, replication overhead và tốc độ tăng dữ liệu.

Ví dụ ma trận:

| Thuộc tính | Dev | Staging | Production |
|---|---|---|---|
| Broker | Một node hoặc cluster nhỏ | Cluster HA quy mô nhỏ | Cluster HA theo capacity |
| Replication factor | 1 nếu chấp nhận mất dữ liệu | 2 hoặc theo topology | Thường 3 khi có đủ broker |
| Partition | Ít, theo test | Gần cấu trúc production | Theo throughput và max consumer |
| Retention | Ngắn | Đủ cho test/replay | Theo nghiệp vụ và tuân thủ |
| ACL | Credential dev riêng | Credential staging riêng | Principal least privilege |
| Quota | Thấp | Gần tải kiểm thử | Theo capacity plan |

Không đặt replication factor 3 nếu cluster chỉ có hai broker; cũng không coi RF 1 là cấu hình an toàn cho production. min.insync.replicas phải tương thích replication factor và producer acks; nếu không, producer có thể bị từ chối ghi khi broker mất replica.

### 6.1. Tính dung lượng Kafka

Ước lượng dữ liệu thô:

    raw_bytes = average_message_bytes × messages_per_second × retention_seconds

Dung lượng cluster cần tính thêm replication và overhead:

    cluster_storage ≈ raw_bytes × replication_factor × overhead_factor

Ví dụ: message trung bình 2 KB, tốc độ 500 message/giây, retention 3 ngày:

    raw_bytes = 2,048 × 500 × 259,200
              ≈ 265.4 GB

Nếu replication factor là 3, dung lượng bản sao thô khoảng 796 GB trước khi tính index, compression, headroom và overhead. Đây là phép ước lượng ban đầu; message size thực tế sau compression, tombstone, compaction, segment và retention policy có thể làm kết quả khác đáng kể.

Không dùng dung lượng đĩa 100% làm capacity mục tiêu. Cần headroom cho rebalance replica, broker restart, traffic burst và thời gian vận hành xử lý sự cố.

### 6.2. Retention và loại topic

Topic event log cần retention đủ để consumer phục hồi hoặc replay trong phạm vi nghiệp vụ. Compacted topic dùng cho state/changelog hoặc latest value theo key; không áp dụng retention ngắn một cách tùy tiện nếu consumer cần dựng lại state.

Tách topic có mục đích khác nhau:
- Event history: lưu theo thời gian/dung lượng và yêu cầu replay.
- State/changelog: cleanup policy phù hợp với semantics state store.
- Retry/DLQ: retention đủ để điều tra và xử lý lại có kiểm soát.
- Metrics/telemetry: tránh đưa payload lớn hoặc dữ liệu nhạy cảm vào topic dùng chung.

## 7. Quản lý RabbitMQ theo môi trường

RabbitMQ thường tổ chức quyền và tài nguyên theo virtual host. Mỗi môi trường có thể dùng vhost riêng, ví dụ /orders-dev, /orders-staging và /orders-prod, hoặc cluster riêng khi cần cách ly mạnh.

Các tài nguyên cần quản lý:
- Virtual host và permission configure/write/read.
- Exchange type, queue, binding và durability.
- Queue type: classic hoặc quorum tùy yêu cầu.
- Dead-letter exchange/queue và routing key.
- TTL, max-length, max-length-bytes và overflow policy.
- Prefetch và consumer concurrency.
- User, password, TLS certificate và policy.
- Memory/disk watermark và connection/channel limits.

Ví dụ tách vhost qua profile:

    spring:
      rabbitmq:
        virtual-host: ${RABBITMQ_VHOST}
        addresses: ${RABBITMQ_ADDRESSES}

Không tạo một user có quyền configure/write/read trên mọi vhost cho tất cả service. Một consumer thường chỉ cần read trên queue/exchange liên quan; producer chỉ cần write vào exchange đích. Quyền configure nên thuộc provisioning identity.

### 7.1. Queue durability và replication

Queue durable không đồng nghĩa message luôn được bảo vệ trước mọi sự cố. Cần xem queue type và cluster topology. Quorum queue dùng replication dựa trên Raft để tăng độ bền, nhưng có chi phí tài nguyên và yêu cầu số node phù hợp. Classic mirrored queue là cơ chế cũ đã thay đổi theo các phiên bản RabbitMQ; không sao chép cấu hình từ tài liệu phiên bản cũ mà chưa xác nhận support.

Chọn queue type theo delivery requirement, throughput, latency và khả năng cluster. Staging nên dùng loại queue gần production để kiểm tra hành vi ack, failover và throughput.

### 7.2. TTL, DLX và giới hạn queue

Queue không nên giữ message vô hạn nếu nghiệp vụ không cần. Có thể đặt message TTL, queue TTL, max-length hoặc dead-letter exchange để xử lý message hết hạn/vượt giới hạn. Chính sách cần được review vì overflow có thể drop hoặc dead-letter message theo cấu hình. Không đặt TTL quá ngắn cho queue retry/DLQ khiến message biến mất trước khi được điều tra.

## 8. Quản lý tài nguyên Pulsar theo môi trường

Pulsar dùng tenant và namespace để tổ chức topic, permission và policy. Ví dụ:

    persistent://orders-dev/streaming/orders.created
    persistent://orders-staging/streaming/orders.created
    persistent://orders-prod/streaming/orders.created

Các tài nguyên/chính sách cần quản lý:
- Tenant và namespace.
- Partitioned topic và số partition.
- Namespace bundle và phân phối tải trên broker.
- Retention và backlog quota.
- Message TTL và compaction.
- Replication giữa cluster/region.
- Authentication role và namespace permission.
- Storage quota, backlog size và BookKeeper capacity.
- Subscription và consumer count.

### 8.1. Retention và backlog quota

Retention quy định message được giữ lại để đọc lại sau khi subscription đã acknowledge, trong phạm vi policy. Backlog quota giới hạn lượng dữ liệu chưa được acknowledge mà subscription có thể tích lũy. Hai chính sách có mục đích khác nhau: retention phục vụ lưu giữ/replay; backlog quota bảo vệ storage khi consumer chậm hoặc ngừng hoạt động.

Chọn policy theo môi trường:
- Dev: retention và backlog quota nhỏ, dễ cleanup.
- Staging: đủ dài để test restart, replay và load.
- Production: theo RPO/RTO, yêu cầu audit và capacity storage.

Nếu backlog quota bị vượt, broker có thể áp dụng policy như producer exception, consumer eviction hoặc giữ backlog tùy cấu hình. Phải hiểu hành vi cụ thể trước khi bật; một policy bảo vệ storage có thể ảnh hưởng producer hoặc subscription.

### 8.2. Replication và storage

Pulsar replication giữa cluster khác với replication ledger trong BookKeeper. Một cơ chế bảo vệ dữ liệu giữa bookie trong cluster; cơ chế kia sao chép dữ liệu topic giữa các cluster/region theo cấu hình. Không coi bật geo-replication là thay thế backup hoặc kiểm thử failover.

Theo dõi bookie disk, ledger availability, write/read latency, under-replicated ledger và broker ownership. Staging cần kiểm tra quyền, endpoint và policy tương tự production nhưng dùng dữ liệu thử nghiệm.

## 9. Quota và chống noisy neighbor

Cluster dùng chung có thể bị một service chiếm quá nhiều CPU, disk, connection hoặc throughput. Quota giúp giới hạn tác động giữa các tenant/client.

Các giới hạn thường cần:
- Produce/consume byte rate hoặc request rate.
- Số connection, channel hoặc consumer.
- Số topic/queue/partition.
- Storage quota và retention.
- Backlog size và message age.
- Max message size và batch size.
- Concurrent admin/provision requests.

Quota nên dựa trên capacity plan và được cảnh báo trước khi chạm ngưỡng. Nếu đặt quá thấp, producer có thể bị throttle và consumer không theo kịp. Nếu đặt quá cao, một workload lỗi có thể làm ảnh hưởng các service khác.

Khi có shared cluster, gắn quota theo service principal/client ID hoặc tenant/namespace/vhost phù hợp. Không chỉ dựa vào hostname ứng dụng vì nhiều service có thể chạy trên cùng node hoặc NAT.

## 10. Bảo mật và network theo môi trường

Mỗi môi trường cần endpoint và credential riêng. Production nên dùng TLS cho broker và admin endpoint, xác thực service identity và phân quyền tối thiểu.

Nguyên tắc:
- Tách secret dev/staging/prod; không tái sử dụng password hoặc token.
- Dùng secret manager hoặc Kubernetes Secret được mã hóa và có kiểm soát.
- Không ghi secret trong application.yml, Docker image, log hoặc file cấu hình chia sẻ.
- Giới hạn network path từ workload tới broker; chỉ mở port cần thiết.
- Dùng ACL/RBAC theo topic, queue, namespace và consumer group.
- Xoay vòng credential/certificate và có quy trình thu hồi.
- Tách quyền runtime publish/consume khỏi quyền provision tài nguyên.
- Kiểm tra TLS hostname, CA trust và certificate expiry.
- Không expose admin API hoặc management UI công khai nếu không cần.

Ứng dụng runtime nên có principal riêng cho mỗi service và môi trường. Nếu một credential bị lộ, phạm vi ảnh hưởng chỉ nên giới hạn ở tài nguyên mà service đó cần.

## 11. Infrastructure as Code và provisioning

Topic, queue, namespace, quota, ACL và policy nên được khai báo trong IaC hoặc provisioning automation có version control. Công cụ có thể là Terraform provider, Helm chart, Kubernetes operator, Ansible hoặc script quản trị đã được review. Chọn công cụ phù hợp broker và chuẩn vận hành của tổ chức.

Một quy trình quản lý tốt:
1. Khai báo resource name, owner, environment và policy.
2. Review thay đổi trong pull request.
3. Kiểm tra plan/diff trước khi apply.
4. Provision tài nguyên broker trước khi deploy ứng dụng.
5. Xác minh topic/queue/namespace, partition, retention và ACL.
6. Deploy ứng dụng bằng endpoint và secret của môi trường.
7. Chạy smoke test publish/consume.
8. Theo dõi lag, error, quota và resource usage.
9. Cleanup tài nguyên test/dev theo TTL và owner.

Không để mọi ứng dụng tự tạo tài nguyên production bằng admin credential khi khởi động. Cách đó khiến quyền ứng dụng quá rộng và resource policy khó review. Auto-provision có thể hữu ích ở local/dev, nhưng production nên có ownership và quy trình rõ ràng.

## 12. Quản lý cấu hình qua CI/CD

Một pipeline triển khai nên phân biệt artifact ứng dụng với cấu hình môi trường. Cùng một artifact có thể được promote qua dev, staging và production; endpoint, credentials và resource names được inject ở từng môi trường.

Ví dụ biến môi trường:

    KAFKA_BOOTSTRAP_SERVERS=kafka-prod.example.internal:9093
    ORDERS_INPUT_DESTINATION=prod.order-stream.orders.created
    ORDERS_CONSUMER_GROUP=order-projection-v2

Không dùng cùng consumer group cho môi trường khác nhau nếu chúng cần xử lý độc lập. Với Kafka, cùng group có thể chia partition và offset, khiến staging lấy mất dữ liệu của production nếu vô tình dùng chung cluster/topic/group. RabbitMQ và Pulsar cũng có nguy cơ dùng chung queue/subscription hoặc làm thay đổi tiến độ.

Các bước release:
- Validate schema/config.
- Provision hoặc kiểm tra resource.
- Kiểm tra ACL/TLS.
- Deploy consumer theo chiến lược an toàn.
- Chạy smoke test publish/consume.
- Xác nhận consumer group/subscription và backlog.
- Theo dõi alert sau deploy.
- Rollback app version hoặc config theo runbook.

Không đưa dữ liệu production thật vào staging nếu chưa có phê duyệt, ẩn danh và chính sách bảo vệ phù hợp.

## 13. Promotion và khác biệt cấu hình

Staging nên giống production về loại broker, phiên bản, authentication, TLS, topic/queue policy và binder behavior. Quy mô có thể nhỏ hơn, nhưng cần giữ các semantics quan trọng. Ví dụ:
- Kafka staging nên kiểm tra partition key, group, retention và consumer rebalance.
- Rabbit staging nên kiểm tra queue type, ack, DLX, TTL và prefetch.
- Pulsar staging nên kiểm tra tenant/namespace, subscription type, backlog quota và auth.

Không dùng một profile chung chỉ đổi host nếu các môi trường có policy khác nhau. Hãy khai báo rõ property cần khác, đồng thời giữ phần cấu hình chung để giảm drift.

## 14. Backup, retention và disaster recovery

Mỗi luồng cần xác định:
- RPO: lượng dữ liệu có thể chấp nhận mất khi xảy ra sự cố.
- RTO: thời gian cần để khôi phục dịch vụ.
- Retention: thời gian lưu record và khả năng replay.
- Replication: bản sao trong cluster hoặc giữa region.
- Backup/restore: dữ liệu nào được backup, tần suất và cách kiểm chứng.
- Recovery owner: ai thực hiện failover, replay và đối soát.

Replication không phải backup. Nó có thể sao chép cả thao tác xóa hoặc dữ liệu sai. Backup cần có retention độc lập, quyền truy cập và bài kiểm tra restore.

Kafka có thể dùng MirrorMaker 2 hoặc giải pháp replication cluster để sao chép topic/consumer offset theo kiến trúc. RabbitMQ có federation/shovel hoặc cơ chế cluster/backup tùy use case; không nhầm cluster replication với backup message. Pulsar hỗ trợ geo-replication giữa cluster; vẫn cần quy trình backup metadata/data và test failover phù hợp.

Kiểm tra failover trong staging:
1. Tạo một lượng event kiểm thử có ID duy nhất.
2. Xác nhận producer/consumer hoạt động trên cluster chính.
3. Mô phỏng mất kết nối hoặc chuyển endpoint theo runbook.
4. Xác nhận dữ liệu được nhận ở cluster dự phòng trong giới hạn RPO.
5. Chuyển consumer và kiểm tra duplicate/gap.
6. Đo thời gian phục hồi và đối soát event ID.
7. Khôi phục về trạng thái bình thường theo quy trình đã định.

## 15. Capacity planning theo môi trường

Dung lượng cần tính từ tốc độ dữ liệu, kích thước message, retention, replication và overhead. Không chỉ tính số partition hoặc số queue.

Ví dụ bảng capacity plan:

| Thành phần | Dev | Staging | Production |
|---|---:|---:|---:|
| Peak event rate | 20/s | 200/s | 2.000/s |
| Average payload | 1 KB | 1 KB | 2 KB |
| Retention | 1 ngày | 3 ngày | 7 ngày |
| Replication | 1 | 2 | 3 |
| Consumer instances | 1 | 2 | Theo load test |
| Storage headroom | 30% | 30% | Theo failover/burst plan |

Các số chỉ minh họa. Production capacity phải bao gồm peak/burst, replay, backlog drain, replication, compaction, index, log segment, message metadata và dung lượng trống để broker rebuild replica. Với RabbitMQ, tính cả message store, queue index và quorum log. Với Pulsar, tính ledger storage, backlog retention và bookie replication.

Không lấy capacity plan của dev rồi nhân một hệ số tùy ý để ra production. Hãy dùng load test và dữ liệu quan sát thực tế.

## 16. Theo dõi tài nguyên và cảnh báo

Theo dõi cả tài nguyên broker và ứng dụng:

| Hạng mục | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Storage | Disk per broker, log size, retention | Message store, queue index, disk alarm | Bookie disk, ledger size, backlog |
| Throughput | Bytes/sec, records/sec, request latency | Publish/deliver/ack rate | Publish/dispatch rate |
| Parallelism | Partition, consumer group lag | Queue consumers, unacked, prefetch | Partition, subscription, consumer count |
| Availability | Broker, controller, ISR | Node, quorum queue, connection | Broker, bookie, ledger |
| Quota | Client/user quota, request throttle | Connection/channel/resource limits | Namespace/tenant resource quota |

Cảnh báo nên gắn với tác động:
- Disk hoặc storage dự kiến cạn trước thời gian xử lý.
- Consumer lag/backlog age vượt SLO.
- Queue ready/unacked tăng liên tục.
- Under-replicated partition hoặc ledger health bất thường.
- Quota throttling kéo dài.
- Certificate sắp hết hạn.
- Connection/consumer count bằng 0 trong giờ hoạt động.
- Retention hoặc backlog quota sắp chạm giới hạn.

Không cảnh báo chỉ vì CPU tăng trong một phút nếu throughput và latency vẫn trong SLO. Dùng ngưỡng, thời gian duy trì, xu hướng và runbook để giảm alert noise.

## 17. Cleanup tài nguyên không còn sử dụng

Topic/queue/namespace cũ làm tăng chi phí và khiến người vận hành khó phân biệt tài nguyên còn sống. Cần quy trình cleanup có kiểm soát:
- Tài nguyên dev/test có owner và expiry/TTL.
- Xác nhận không còn producer/consumer hoạt động.
- Kiểm tra retention, DLQ và yêu cầu audit trước khi xóa.
- Export metadata cần thiết nếu có yêu cầu.
- Review approval cho tài nguyên staging/prod.
- Xóa bằng IaC hoặc quy trình admin có audit log.
- Xác nhận không có binding đang tham chiếu destination đó.

Không tự động xóa topic production chỉ vì không có traffic trong vài ngày; một topic có thể là nguồn replay hoặc audit. Cleanup phải dựa trên owner, contract và chính sách lưu trữ.

## 18. Runbook xử lý sự cố tài nguyên

### 18.1. Broker hết dung lượng

1. Xác định broker/node hoặc bookie bị ảnh hưởng.
2. Kiểm tra tốc độ tăng dữ liệu, retention và replication overhead.
3. Tìm topic/queue/namespace có storage lớn nhất.
4. Xác nhận có thể giảm retention hoặc cleanup theo policy không.
5. Mở rộng storage/broker nếu cần theo quy trình hạ tầng.
6. Theo dõi replica recovery, queue health và producer throttling.
7. Đối soát dữ liệu sau khi hệ thống ổn định.

Không xóa segment, ledger hoặc queue file thủ công để giải phóng dung lượng.

### 18.2. Quota bị vượt

1. Xác định principal/client/tenant bị throttle.
2. So sánh throughput thực tế với quota và SLO.
3. Kiểm tra burst, retry storm hoặc producer loop.
4. Xác định quota có đặt sai hoặc workload tăng hợp lệ.
5. Điều chỉnh quota có review, hoặc giảm tải producer.
6. Theo dõi lag/backlog và downstream sau thay đổi.

Không bỏ quota toàn cluster để xử lý một service gây tải bất thường.

### 18.3. Môi trường test ảnh hưởng môi trường khác

1. Xác định endpoint, topic/queue/subscription và credential đang được dùng.
2. Dừng producer/consumer test sai cấu hình.
3. Kiểm tra group/subscription có dùng chung tiến độ không.
4. Tách resource và credential theo môi trường.
5. Đối soát event bị đọc/ghi nhầm và đánh giá replay.
6. Thêm kiểm tra config trong CI để ngăn tái diễn.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Dùng chung topic/queue/group giữa dev và prod | Test lấy hoặc làm thay đổi dữ liệu production | Tách namespace/vhost/topic/group và credential |
| Auto-create resource trong production | Topic/queue được tạo sai policy | Provision trước bằng IaC và tắt auto-create nếu phù hợp |
| Dùng admin credential cho ứng dụng | Blast radius lớn khi secret lộ | Principal runtime least privilege |
| Retention không giới hạn | Storage tăng liên tục | Đặt retention và quota theo hợp đồng |
| Replication factor vượt số broker | Topic không thể provision hoặc thiếu ISR | Kiểm tra topology và min ISR |
| Chỉ tăng consumer mà không tăng capacity broker | Broker hoặc downstream quá tải | Capacity plan toàn pipeline |
| Staging khác production quá nhiều | Lỗi chỉ xuất hiện khi deploy thật | Giữ broker version và semantics gần production |
| Không quản lý secret theo môi trường | Lộ credential hoặc kết nối nhầm cluster | Secret manager và CI environment protection |
| Coi replication là backup | Không khôi phục được khi dữ liệu bị xóa/sai | Backup độc lập và restore test |
| Không cleanup tài nguyên test | Tăng chi phí và khó quản lý | Owner, expiry và IaC destroy có kiểm soát |

## 20. Quy trình quản lý broker theo môi trường

1. Phân loại dữ liệu, mức độ quan trọng và SLO của luồng.
2. Chọn mức cô lập: cluster riêng hay tenant/vhost/namespace riêng.
3. Tính partition, queue, throughput, connection và storage.
4. Chọn replication, retention, backlog quota và recovery policy.
5. Tạo principal, ACL, TLS certificate và secret riêng.
6. Khai báo resource bằng IaC và review diff.
7. Provision broker resources trước khi deploy ứng dụng.
8. Inject endpoint/credentials qua config store hoặc secret manager.
9. Deploy binder và binding với destination/group riêng.
10. Smoke test publish/consume và xác nhận resource policy.
11. Theo dõi lag, storage, quota, connection, DLQ và alert.
12. Review capacity/retention định kỳ và cleanup tài nguyên hết vòng đời.

## 21. Checklist trước khi triển khai

- [ ] Mỗi môi trường có endpoint, destination và consumer group/subscription riêng.
- [ ] Cluster hoặc tenant/vhost/namespace có ranh giới và owner rõ ràng.
- [ ] Topic, queue, partition và storage được provision theo IaC.
- [ ] Replication factor/quorum phù hợp topology và yêu cầu độ bền.
- [ ] Retention, TTL, DLQ và backlog quota có giá trị rõ ràng.
- [ ] Quota throughput, connection và storage được đặt theo capacity plan.
- [ ] Runtime principal chỉ có quyền publish/consume cần thiết.
- [ ] Admin/provisioning identity tách khỏi credential ứng dụng.
- [ ] TLS, secret rotation, network policy và certificate expiry được quản lý.
- [ ] Spring Cloud Stream profile lấy endpoint từ environment/secret store.
- [ ] Production không tự tạo tài nguyên ngoài quy trình đã duyệt.
- [ ] Staging mô phỏng broker version và semantics quan trọng của production.
- [ ] Có dashboard/alert cho lag, backlog, storage, quota và broker health.
- [ ] Có backup/DR plan với RPO/RTO và restore test.
- [ ] Có owner, expiry và quy trình cleanup cho tài nguyên dev/test.
- [ ] Có runbook xử lý hết dung lượng, quota và cấu hình nhầm môi trường.

Quản lý broker theo môi trường là quản lý cả vòng đời tài nguyên: cô lập môi trường, provision topic/queue/namespace, cấp quota, retention, replication, quyền truy cập, monitoring, backup và cleanup. Spring Cloud Stream chỉ là lớp ứng dụng kết nối tới các tài nguyên đó; broker policy cần được quản trị riêng và kiểm tra trước khi deploy. Khi cùng một artifact được promote qua các môi trường với endpoint, credential và destination được inject đúng, hệ thống giảm nguy cơ test ảnh hưởng production, kiểm soát chi phí và có khả năng phục hồi rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Apache Kafka — Operations and Configuration](https://kafka.apache.org/documentation/#operations)
- [RabbitMQ — Virtual Hosts and Access Control](https://www.rabbitmq.com/docs/vhosts)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Apache Pulsar — Tenants and Namespaces](https://pulsar.apache.org/docs/next/concepts-multi-tenancy/)
- [Apache Pulsar — Namespace Policies](https://pulsar.apache.org/docs/next/admin-api-namespaces/)

