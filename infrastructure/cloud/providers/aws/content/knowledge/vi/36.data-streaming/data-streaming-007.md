# Amazon MSK, broker và lựa chọn mô hình triển khai

Amazon Managed Streaming for Apache Kafka (Amazon MSK) là dịch vụ AWS quản lý hạ tầng Apache Kafka. Ứng dụng tiếp tục sử dụng Kafka protocol, producer, consumer, topic, partition, consumer group và Kafka client tương thích. Amazon MSK đảm nhiệm nhiều công việc hạ tầng như tạo cluster, quản lý broker node, bảo trì phần cứng, cập nhật phần mềm theo quy trình dịch vụ, tích hợp mạng, mã hóa và giám sát.

Khi thiết kế MSK, câu hỏi quan trọng không chỉ là “cần bao nhiêu broker?”. Đội kiến trúc phải xác định workload, thông lượng, số partition, retention, khả năng chịu lỗi, số kết nối, mô hình xác thực, vùng triển khai, mức độ kiểm soát cấu hình và cách mở rộng. Amazon MSK có hai lựa chọn triển khai cluster chính: **MSK Provisioned** và **MSK Serverless**. Với Provisioned, người dùng chọn broker type **Standard** hoặc **Express**. Mỗi mô hình có cách quản lý dung lượng, lưu trữ và chi phí khác nhau.

Bài học đặt MSK trong bối cảnh AWS gồm Region/AZ, VPC, IAM, KMS, CloudWatch, tích hợp streaming và kiến trúc hybrid. Mục tiêu là chọn mô hình triển khai phù hợp, hiểu vai trò broker và partition, bảo vệ dữ liệu, thiết kế khả năng sẵn sàng cao và vận hành cluster có thể mở rộng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Mô tả kiến trúc Kafka và vai trò của broker, controller, topic, partition, leader, replica và consumer group.
- Giải thích Amazon MSK quản lý phần hạ tầng nào và phần nào vẫn thuộc trách nhiệm của đội ứng dụng.
- Phân biệt MSK Provisioned với MSK Serverless.
- So sánh Standard broker với Express broker về cấu hình, storage, scaling, throughput và vận hành.
- Chọn broker type theo workload, khả năng kiểm soát và chi phí.
- Thiết kế cluster Multi-AZ, replication factor, min.insync.replicas và producer acknowledgment.
- Hiểu ZooKeeper mode và KRaft mode theo phiên bản Kafka.
- Thiết kế VPC, subnet, security group, bootstrap endpoint và kết nối nhiều VPC/account.
- Chọn IAM, SASL/SCRAM hoặc mutual TLS để xác thực client.
- Sử dụng CloudWatch, broker logs và Prometheus để giám sát.
- Nhận diện vai trò riêng của MSK Connect và MSK Replicator.
- Đánh giá đường nâng cấp Standard sang Express, gồm khả năng in-place upgrade được AWS công bố ngày 19/11/2026.

## 2. Amazon MSK giải quyết vấn đề gì?

Apache Kafka là nền tảng streaming phân tán. Producer ghi sự kiện vào topic; consumer đọc sự kiện theo offset. Topic có thể được chia thành nhiều partition để tăng khả năng song song và mở rộng. Kafka lưu dữ liệu theo log có thứ tự trong từng partition, hỗ trợ replication để tăng độ bền và khả năng chịu lỗi.

Nếu tự vận hành Kafka trên Amazon EC2, đội kỹ thuật phải chịu trách nhiệm nhiều lớp:
- Cấp phát và thay thế EC2 broker.
- Thiết kế EBS, throughput và dung lượng lưu trữ.
- Cấu hình Kafka, metadata management và broker placement.
- Quản lý patch, upgrade, broker replacement và partition reassignment.
- Xử lý sự cố broker, disk, network và controller.
- Xây dựng monitoring, log collection, backup/replication và runbook.
- Quản lý bảo mật, certificate, credential và quyền truy cập.

Amazon MSK giảm gánh nặng quản lý hạ tầng bằng cách cung cấp Kafka cluster được quản lý trong AWS. Người dùng vẫn làm việc với Kafka API và công cụ Kafka quen thuộc. MSK cung cấp control-plane API để tạo, cập nhật, mô tả và xóa cluster; data plane tiếp tục dùng Kafka protocol để tạo topic, publish, consume và quản trị tài nguyên Kafka.

MSK phù hợp khi:
- Ứng dụng đã dùng Kafka client hoặc hệ sinh thái Kafka.
- Cần streaming event giữa nhiều ứng dụng hoặc microservice.
- Cần giữ lại Kafka API, consumer group, partition và ecosystem.
- Muốn tích hợp với IAM, VPC, CloudWatch, KMS, Lambda, Glue Schema Registry hoặc Managed Service for Apache Flink.
- Muốn giảm công việc vận hành broker nhưng vẫn cần điều khiển topology Kafka.

Nếu workload không cần Kafka compatibility, hãy đánh giá cả các dịch vụ streaming khác như Amazon Kinesis Data Streams. Lựa chọn phụ thuộc giao thức client, mô hình partition/shard, hệ sinh thái hiện tại, yêu cầu tích hợp và chi phí vận hành.

## 3. Kiến trúc Kafka và vai trò của broker

Một Kafka cluster gồm nhiều broker. Mỗi broker là một node nhận yêu cầu từ client và lưu trữ một phần các partition hoặc replica của partition.

### 3.1 Broker làm gì?

Broker có các trách nhiệm chính:

- Nhận yêu cầu metadata từ producer và consumer.
- Nhận bản ghi do producer gửi đến partition leader.
- Lưu log segment trên storage.
- Phục vụ yêu cầu fetch từ consumer.
- Sao chép dữ liệu giữa leader và follower replica.
- Tham gia điều phối consumer group và xử lý các yêu cầu quản trị Kafka.
- Báo cáo trạng thái partition, replica, request và tài nguyên.

Broker không phải là nơi ứng dụng lưu logic nghiệp vụ. Broker lưu và phân phối event; producer quyết định event nào được ghi, consumer xử lý event và quản lý tiến độ bằng offset.

### 3.2 Topic và partition

Topic là tên logic của luồng sự kiện. Một topic gồm một hoặc nhiều partition.

Mỗi partition là một log có thứ tự append-only. Bản ghi được gán offset tăng dần trong partition. Kafka bảo đảm thứ tự trong một partition; không bảo đảm thứ tự toàn cục giữa các partition.

Producer có thể chọn partition bằng:
- Partition được chỉ định trực tiếp.
- Key được hash theo partitioner.
- Round-robin hoặc sticky partitioning khi không có key, tùy client và cấu hình.

Nếu các event có cùng key được định tuyến nhất quán vào cùng partition, chúng có thể giữ thứ tự theo key. Ví dụ, dùng `customerId` làm key để các event của một khách hàng được xử lý theo thứ tự trong một partition.

Partition ảnh hưởng đến:
- Mức độ song song của producer/consumer.
- Số lượng leader và replica cần phân phối lên broker.
- Dung lượng metadata.
- Thời gian rebalance consumer group.
- Tải CPU, network và storage.
- Chi phí giám sát và vận hành.

Tăng partition không phải lúc nào cũng làm hệ thống nhanh hơn. Quá ít partition có thể giới hạn throughput và consumer parallelism; quá nhiều partition làm tăng overhead metadata, file handle, memory, recovery và rebalance.

### 3.3 Leader và follower replica

Mỗi partition có một replica leader và có thể có nhiều follower replica. Producer ghi vào leader; follower sao chép log từ leader. Consumer thường đọc từ leader theo cấu hình client/cluster.

Ví dụ một topic có replication factor 3 trong cluster ba AZ:

~~~text
                 Amazon MSK - Region
       AZ-a                 AZ-b                 AZ-c
  +-------------+      +-------------+      +-------------+
  | Broker 1    |      | Broker 2    |      | Broker 3    |
  | Partition 0 |      | Partition 0 |      | Partition 0 |
  | Leader      | ---> | Follower    | ---> | Follower    |
  +-------------+      +-------------+      +-------------+

  Producer ----------------> Partition 0 leader
  Consumer <---------------- Partition 0 leader
~~~

Hình minh họa một partition; thực tế một broker có thể lưu nhiều leader và follower của nhiều topic/partition. MSK phân phối broker trên các AZ theo cấu hình cluster. Express brokers sử dụng replication trên ba AZ; với Standard brokers, chiến lược replication phụ thuộc topology và cấu hình topic.

### 3.4 In-Sync Replicas (ISR)

ISR là tập replica đang đồng bộ đủ gần với leader theo điều kiện Kafka. Khi producer dùng `acks=all`, leader chỉ xác nhận ghi theo chính sách replication và `min.insync.replicas`.

Một cấu hình thường dùng cho topic quan trọng trên cluster ba AZ:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
enable.idempotence = true
~~~

Ý nghĩa:
- Có ba bản sao của partition.
- Ít nhất hai replica phải còn trong ISR để chấp nhận ghi theo cấu hình min ISR.
- Producer chờ xác nhận từ replica theo cơ chế `acks=all`.
- Idempotent producer giúp giảm nguy cơ duplicate do retry trong phạm vi bảo đảm của Kafka producer protocol.

Nếu `min.insync.replicas` bằng replication factor, khi một replica tạm thời offline, producer có thể không ghi được. Nếu min ISR quá thấp, hệ thống có thể tiếp tục nhận ghi khi mức dự phòng dữ liệu đã suy giảm. Hãy chọn theo yêu cầu durability và availability.

AWS khuyến nghị replication factor ít nhất 3 cho Standard brokers. RF=1 có thể khiến partition offline trong rolling update; RF=2 có thể làm tăng nguy cơ mất dữ liệu trong một số tình huống bảo trì hoặc sự cố. Với Express brokers, replication trên ba AZ được dịch vụ áp dụng để tăng độ sẵn sàng.

### 3.5 Consumer group và offset

Consumer group cho phép nhiều consumer cùng chia sẻ việc đọc một topic. Mỗi partition tại một thời điểm được gán cho tối đa một consumer trong cùng group, nhưng một consumer có thể nhận nhiều partition.

Offset ghi nhận vị trí đọc của consumer. Khi consumer group rebalance, partition có thể được chuyển giữa các consumer. Ứng dụng cần xử lý:
- Consumer crash và restart.
- Rebalance khi thêm/bớt consumer.
- Xử lý bản ghi lâu hơn thời gian poll interval.
- Commit offset tự động hoặc thủ công.
- Retry và dead-letter topic.
- Duplicate delivery và idempotent processing.
- Consumer lag tăng do downstream chậm.

Kafka thường được sử dụng với mô hình at-least-once. Exactly-once semantics cần cấu hình producer transaction, consumer isolation và logic xử lý phù hợp; không thể chỉ bật một thuộc tính rồi mặc nhiên bảo đảm toàn bộ hệ thống bên ngoài Kafka chỉ thực hiện một lần.

## 4. Thành phần metadata: ZooKeeper và KRaft

Kafka cần quản lý metadata của cluster như broker membership, topic, partition, replica và controller state.

Amazon MSK hỗ trợ hai chế độ metadata management trên các phiên bản được hỗ trợ:

| Chế độ | Cách quản lý metadata | Ghi chú |
|---|---|---|
| ZooKeeper mode | Dùng các ZooKeeper node do MSK quản lý | Có trên các phiên bản Kafka còn hỗ trợ ZooKeeper |
| KRaft mode | Dùng nhóm Kafka controllers để quản lý metadata | MSK hỗ trợ tạo KRaft từ Kafka 3.7.x |

Trong KRaft, metadata được quản lý bởi các controller thuộc Kafka cluster, thay cho hệ ZooKeeper bên ngoài. MSK quản lý các metadata node/controller cho người dùng, không yêu cầu khách hàng tự cấp phát hay vận hành controller.

Một số điểm cần nhớ:
- KRaft được hỗ trợ trên Amazon MSK từ Kafka 3.7.x.
- Có thể tạo cluster ở ZooKeeper mode hoặc KRaft mode theo phiên bản và tùy chọn được hỗ trợ.
- Kafka 3.7.x dùng hậu tố version khác nhau khi tạo cluster bằng API để chỉ rõ KRaft hoặc ZooKeeper.
- Không cần thay đổi Kafka data-plane API chỉ vì chuyển sang KRaft.
- Công cụ quản trị không nên phụ thuộc kết nối trực tiếp ZooKeeper.
- Dùng `--bootstrap-server` thay cho `--zookeeper`; cờ `--zookeeper` đã deprecated và bị loại bỏ trong Kafka 3.0.
- MSK quản lý controller và không yêu cầu khách hàng truy cập trực tiếp controller để giám sát hoặc thao tác.

Ví dụ sơ đồ KRaft:

~~~text
              Amazon MSK cluster
       +--------------------------------+
       | Broker 1   Broker 2   Broker 3 |
       |     \        |        /        |
       |      \       |       /         |
       |       Kafka KRaft controllers  |
       |       quản lý cluster metadata|
       +--------------------------------+
                    |
             Kafka bootstrap
                    |
             Producer / Consumer
~~~

Không nên chọn Kafka version chỉ vì nó mới nhất. Hãy kiểm tra phiên bản được MSK hỗ trợ, end-of-support date, khả năng tương thích client, broker type, KRaft mode và các tính năng ứng dụng cần dùng.

## 5. Hai mô hình triển khai cluster

Amazon MSK cung cấp hai deployment option:

1. **MSK Provisioned**: người dùng cấu hình và quản lý quy mô cluster ở cấp broker.
2. **MSK Serverless**: MSK tự cấp phát và mở rộng compute/storage cho cluster; người dùng không chọn số broker hoặc kích thước broker.

MSK Provisioned có hai broker type:
- Standard.
- Express.

Không nhầm broker type với deployment option. Standard và Express đều là MSK Provisioned; Serverless là một deployment option riêng.

| Tiêu chí | Provisioned Standard | Provisioned Express | Serverless |
|---|---|---|---|
| Quản lý broker | Chọn số lượng và instance | Chọn broker size/count, MSK quản lý nhiều thao tác hơn | MSK quản lý toàn bộ broker capacity |
| Storage | Người dùng cấu hình EBS, throughput và retention; có tiered storage | MSK quản lý storage co giãn, pay-as-you-go | MSK quản lý storage |
| Cấu hình Kafka | Linh hoạt hơn | Có guardrail và cấu hình best-practice được quản lý nhiều hơn | Tập cấu hình được hỗ trợ giới hạn hơn |
| Scaling | Điều chỉnh broker size/count và storage theo kế hoạch | Scaling linh hoạt, có intelligent rebalancing | Tự động theo tải trong quota |
| Availability topology | Chọn AZ và replication strategy | Yêu cầu 3 AZ | MSK quản lý capacity và placement |
| Tính dự báo chi phí | Phụ thuộc broker, EBS, throughput, transfer | Broker và storage/ingestion theo usage | Theo thông lượng và dữ liệu lưu trữ/partition |
| Phù hợp | Cần kiểm soát cấu hình, workload ổn định | Workload cần throughput cao, scale nhanh, ít quản lý storage | Tải biến động, muốn giảm công việc capacity planning |

Quyết định phải dựa trên workload và feature requirements. Đừng chọn Serverless chỉ vì không cần quản lý broker; cũng đừng chọn Provisioned chỉ vì muốn có nhiều cấu hình mà ứng dụng không thực sự cần.

## 6. MSK Provisioned Standard brokers

Standard broker là mô hình Kafka truyền thống trong MSK Provisioned, cho phép kiểm soát nhiều cấu hình cluster và storage.

### 6.1 Đặc điểm

- Chọn broker instance family/size theo danh sách MSK hỗ trợ.
- Chọn số broker trong mỗi Availability Zone.
- Cấu hình EBS storage cho từng broker.
- Có thể sử dụng provisioned storage throughput, storage autoscaling và storage capacity alerts.
- Hỗ trợ tiered storage trên các Kafka version và cấu hình tương thích.
- Cho phép tùy chỉnh nhiều Kafka configuration hơn Express.
- Hỗ trợ các lựa chọn xác thực và mã hóa của MSK Provisioned.
- Có thể scale dọc bằng thay đổi broker size và scale ngang bằng thay đổi broker count.

Standard broker phù hợp khi cần khả năng tùy chỉnh sâu, workload có sizing tương đối rõ và đội vận hành sẵn sàng quản lý storage/partition balancing.

### 6.2 Chọn broker instance

Broker size ảnh hưởng đến:
- CPU để xử lý request, compression, encryption và replication.
- Memory cho page cache, request buffer và metadata.
- Network throughput.
- Khả năng phục vụ connection và partition.
- Khả năng chịu tải trong rolling maintenance hoặc broker failure.

Một broker có CPU thấp nhưng network hoặc disk throughput đã bão hòa vẫn có thể là bottleneck. Không sizing chỉ theo CPU.

T3 có thể phù hợp với workload nhỏ, thử nghiệm hoặc tải thấp có giới hạn burst. M5/M7g/M8g phù hợp với workload production tùy throughput, CPU, memory và network profile. Luôn kiểm tra broker instance types được hỗ trợ tại Region và Kafka version dự kiến.

### 6.3 Storage EBS

Với Standard broker, storage là phần cần dự báo và theo dõi. Ước lượng dung lượng dựa trên:
- Ingress rate trung bình và đỉnh.
- Retention theo thời gian hoặc kích thước.
- Replication factor.
- Compression ratio.
- Tốc độ tăng trưởng dữ liệu.
- Khoảng thời gian consumer có thể bị chậm.
- Dung lượng dự phòng cho compaction, recovery và hoạt động vận hành.

Công thức ước lượng sơ bộ cho một topic:

~~~text
Dung lượng logical gần đúng
  = Ingress bytes/second
    x Retention seconds

Dung lượng vật lý gần đúng trong cluster
  = Dung lượng logical
    x Replication factor
    x Hệ số dự phòng
~~~

Công thức này chỉ dùng để lập ngân sách sơ bộ. Dung lượng thực tế còn phụ thuộc compression, log segment, index, compaction, retention policy và phân bố partition trên broker.

MSK Standard cho phép tăng storage EBS trên mỗi broker. Storage không thể giảm sau khi đã tăng. Mỗi lần scale storage có cooldown period; thời gian có thể từ vài giờ đến hơn một ngày tùy dung lượng, mức sử dụng và traffic. Vì vậy, tránh đặt storage sát giới hạn rồi chờ đến khi cảnh báo mới tăng.

### 6.4 Tiered storage

Tiered storage cho Standard brokers cho phép giữ dữ liệu cũ trên tầng lưu trữ chi phí thấp hơn, trong khi dữ liệu mới vẫn ở tầng primary storage tối ưu hiệu năng.

Lợi ích:
- Kéo dài retention mà không cần tăng tương ứng EBS trên broker.
- Giảm áp lực dung lượng primary storage.
- Hỗ trợ replay dữ liệu cũ bằng Kafka API.
- Tách một phần chi phí lưu trữ dài hạn khỏi dung lượng broker.

Các giới hạn quan trọng:
- Chỉ áp dụng cho MSK Provisioned Standard brokers.
- Cần Kafka version tương thích.
- Không hỗ trợ compacted topics trong cấu hình tiered storage được mô tả hiện hành.
- Khi đọc dữ liệu remote tier, lần đọc ban đầu có thể có latency cao hơn.
- Một số cấu hình log cleanup/partition có giới hạn.
- Không phải mọi workload đều phù hợp với remote tier, nhất là workload cần replay ngẫu nhiên với latency rất thấp.

Đánh giá retention và consumer behavior trước khi bật tiered storage. Không giả định mọi dữ liệu đều có latency đọc giống nhau.

## 7. MSK Provisioned Express brokers

Express là broker type trong MSK Provisioned, hướng đến workload cần throughput cao, khả năng mở rộng nhanh và giảm công việc quản lý storage.

### 7.1 Đặc điểm

- Storage do MSK quản lý hoàn toàn, tự mở rộng theo nhu cầu và tính phí theo mức sử dụng.
- Không cần dự báo/provision EBS như Standard.
- Broker có best-practice configuration và guardrail cho một số cấu hình quan trọng.
- Enforce throughput quota cho client để hạn chế một client chiếm hết tài nguyên cluster.
- Hỗ trợ intelligent rebalancing để tự động phân bố partition khi scale.
- MSK quản lý bảo trì phần cứng liên tục; Express không dùng maintenance window theo cách Standard thường dùng.
- Hỗ trợ Multi-AZ ba AZ.
- Chọn từ các broker size được hỗ trợ; danh sách instance và version cần xác nhận theo Region.

AWS công bố Express có thể đạt đến 3 lần throughput mỗi broker, scale nhanh đến 20 lần và recovery nhanh hơn đến 90% so với Standard trong các điều kiện/size được so sánh. Đây là số liệu tối đa theo tài liệu AWS, không phải cam kết throughput cho mọi cluster. Hãy benchmark bằng workload thực tế.

### 7.2 Guardrail và giới hạn

Express giảm nhu cầu điều chỉnh sâu nhưng không có nghĩa mọi tính năng Kafka đều giống hệt Standard.

Theo tài liệu AWS hiện hành tại thời điểm biên soạn:
- Express chỉ triển khai ở cấu hình ba Availability Zones.
- Broker size Express dùng các instance family được AWS hỗ trợ, hiện gồm M7g và M8g; Standard có danh sách lựa chọn rộng hơn như T3, M5, M7g và M8g.
- Tài liệu Express hiện liệt kê Kafka 3.6, 3.8, 3.9 và 4.2; version support có thể thay đổi theo thời gian và Region.
- KRaft mode có thể được chọn khi tạo cluster từ các version Express được hỗ trợ, hiện tài liệu nêu Kafka 3.9 trở lên.
- Một số tính năng Kafka mới hoặc API chuyên biệt có thể chưa được hỗ trợ đầy đủ.
- Express chưa hỗ trợ đầy đủ Kafka Streams API theo ghi chú tính năng hiện hành.
- KIP-932 Queues for Kafka chưa được hỗ trợ theo tài liệu Express hiện hành.
- Các cấu hình quan trọng có thể bị giới hạn để bảo vệ durability và availability.

Nếu ứng dụng dùng Kafka Streams, transaction, compacted topic, custom broker configuration hoặc plugin đặc thù, phải kiểm tra ma trận feature support trước khi chọn Express.

### 7.3 Intelligent rebalancing

Khi thêm/bớt broker, Kafka cần phân phối partition và replica để tránh broker mới trống trong khi broker cũ vẫn quá tải.

Intelligent rebalancing trên Express giúp tự động cân bằng partition trong các thao tác scaling. Cluster Express mới được bật tính năng này theo mặc định. Với cluster được nâng cấp tại chỗ từ Standard sang Express, cần kiểm tra trạng thái intelligent rebalancing sau upgrade vì AWS hướng dẫn bật tính năng này trước khi right-size số broker.

## 8. MSK Serverless

MSK Serverless là mô hình cluster trong đó AWS tự quản lý compute và storage capacity. Người dùng không chọn instance type, số broker hoặc tự điều chỉnh cluster capacity theo biến động throughput.

### 8.1 Đặc điểm

- Tạo cluster trong VPC và chọn subnet cho client connectivity.
- MSK tự cấp phát và mở rộng capacity khi workload thay đổi.
- Quản lý partition và broker capacity theo mô hình dịch vụ.
- Tương thích với Kafka client.
- Tích hợp IAM access control, AWS PrivateLink, AWS Glue Schema Registry, Managed Service for Apache Flink và Lambda.
- Tính phí theo throughput và dữ liệu lưu trữ/retention theo bảng giá hiện hành.

Serverless phù hợp với:
- Workload có lưu lượng biến động lớn hoặc khó dự báo.
- Nhóm muốn thử nghiệm streaming mà không sizing broker.
- Nhiều producer/consumer với nhu cầu capacity tăng giảm theo thời điểm.
- Ứng dụng không cần cấu hình broker sâu và nằm trong quota dịch vụ.

### 8.2 Các giới hạn cần biết

MSK Serverless yêu cầu IAM access control cho mọi cluster. Apache Kafka ACL không được hỗ trợ như cơ chế authorization trên Serverless. Vì vậy, ứng dụng cần dùng IAM policy và IAM authentication.

Serverless có quota theo cluster, account và Region. Các quota liên quan có thể gồm:
- Ingress/egress throughput.
- Throughput trên mỗi partition.
- Số partition và consumer group.
- Số kết nối và tốc độ tạo kết nối.
- Kích thước message.
- Số VPC client được kết nối.
- Số cluster trong account.

Quota có thể được điều chỉnh theo quy trình AWS và thay đổi theo thời gian. Trước khi đưa workload production vào Serverless, hãy kiểm tra trang MSK quotas và Service Quotas tại Region dự kiến.

Serverless giảm việc quản lý hạ tầng nhưng không loại bỏ trách nhiệm thiết kế partition, key, retention, producer retry, consumer lag, schema evolution và idempotent processing.

## 9. Chọn mô hình triển khai theo workload

| Workload | Gợi ý ban đầu | Lý do và điều cần xác minh |
|---|---|---|
| Event pipeline có traffic ổn định, cần custom config | Provisioned Standard | Kiểm soát broker, storage, throughput và Kafka configuration |
| Streaming throughput cao, cần scale nhanh | Provisioned Express | Storage managed, throughput/broker cao, intelligent rebalancing |
| Workload mới, traffic không đều, muốn tránh sizing | Serverless | Tự scale capacity; cần kiểm tra quota và IAM-only access |
| Dùng Kafka Streams API chuyên sâu | Standard trước khi xác nhận Express support | Express có giới hạn API cần kiểm tra |
| Cần tiered storage cho retention dài | Provisioned Standard | Tiered storage áp dụng cho Standard |
| Cần kiểm soát EBS, storage throughput và broker config | Provisioned Standard | Linh hoạt hơn Express |
| Muốn quản lý partition tự động khi scale | Express | Intelligent rebalancing tích hợp |
| Ứng dụng cần auth bằng IAM policy | Provisioned hoặc Serverless | Serverless bắt buộc IAM; Provisioned hỗ trợ IAM cùng các lựa chọn khác |
| Cần nhiều cấu hình Kafka đặc thù | Standard | Express có guardrail và cấu hình do MSK quản lý nhiều hơn |

Quy trình chọn lựa:
1. Xác định ingress/egress trung bình và đỉnh.
2. Đo số connection, partition, consumer group và message size.
3. Xác định retention và khả năng replay.
4. Liệt kê Kafka API, plugin, transaction và feature bắt buộc.
5. Chọn yêu cầu AZ, RPO, durability và maintenance.
6. Xác định mức kiểm soát broker/storage cần thiết.
7. So sánh chi phí theo tải thực tế và tải đỉnh.
8. Chạy benchmark và fault-injection rehearsal trước production.

## 10. Thiết kế broker count, AZ và replication

### 10.1 Multi-AZ

Cluster MSK Provisioned được triển khai trong một AWS Region và phân phối broker qua các Availability Zone. Khi tạo cluster, chọn các subnet tương ứng với AZ và số broker trên mỗi AZ.

Với Standard broker, topology ba AZ thường được chọn cho workload production cần khả năng chịu lỗi AZ. Tài liệu AWS khuyến nghị client bootstrap string nên chứa broker từ nhiều AZ để client có thể kết nối khi một broker đang bảo trì hoặc offline.

Express brokers yêu cầu ba AZ.

### 10.2 Broker count

Số broker phải đáp ứng:
- Throughput của producer.
- Throughput của consumer.
- Replication traffic giữa broker.
- Số partition và replica.
- Connection count.
- CPU và network headroom.
- Khả năng duy trì tải khi một broker offline.

Không sizing theo tổng dung lượng disk đơn thuần. Một cluster có đủ disk nhưng thiếu CPU hoặc network vẫn có thể throttle producer và tăng consumer lag.

### 10.3 Partition count

Ước lượng partition dựa trên:
- Throughput cần đạt.
- Mức song song của consumer group.
- Số key và phân bố key.
- Ordering requirement.
- Số broker và partition-per-broker guidance.
- Thời gian rebalance và recovery.

Nếu một partition nhận traffic quá lớn, tăng tổng partition không giải quyết triệt để nếu key partitioning vẫn dồn mọi record vào một partition. Cần xem lại key design và skew.

AWS công bố khuyến nghị partition per Standard broker theo instance size. Đây là guidance vận hành, không phải một con số chung cho mọi workload. Đếm cả leader và follower replica khi đánh giá partition-per-broker.

### 10.4 Replication và availability

Với topic quan trọng:
- Dùng replication factor 3 khi topology cho phép.
- Cân nhắc `min.insync.replicas=2`.
- Dùng producer `acks=all` và idempotence khi phù hợp.
- Theo dõi `UnderReplicatedPartitions`, `OfflinePartitionsCount` và ISR shrink/expand.
- Không giảm RF chỉ để tiết kiệm storage nếu durability yêu cầu nhiều bản sao.
- Test producer retry và client failover khi broker bị dừng.

Replication bảo vệ trước lỗi broker/AZ trong phạm vi thiết kế. Nó không thay thế backup, retention policy, cross-Region DR hoặc bảo vệ trước lỗi logic như producer ghi sai dữ liệu.

## 11. Thiết kế topic, key và retention

Broker capacity chỉ là một phần. Topic design quyết định khả năng phân phối tải và cách ứng dụng đọc dữ liệu.

### 11.1 Chọn topic boundary

Một topic thường đại diện cho một luồng event có schema, retention và consumer contract tương đối rõ.

Ví dụ:
- `orders.created`
- `orders.cancelled`
- `payments.authorized`
- `inventory.changed`
- `audit.events`

Không tạo topic mới cho từng customer hoặc từng request. Topic quá nhỏ gây overhead quản trị; topic quá rộng làm schema, ACL và retention khó quản lý.

### 11.2 Chọn key

Key nên phản ánh ordering boundary và partition distribution.

Ví dụ:
- `orderId`: giữ thứ tự event của một đơn hàng.
- `customerId`: giữ thứ tự event của một khách hàng.
- `deviceId`: giữ thứ tự telemetry của một thiết bị.

Nếu một key có traffic áp đảo, nó tạo hot partition. Hãy kiểm tra skew bằng phân bố record/byte theo partition và cân nhắc composite key hoặc thiết kế lại consumer semantics. Không thêm random suffix nếu nghiệp vụ cần giữ thứ tự theo entity.

### 11.3 Retention

Retention có thể dựa trên thời gian hoặc kích thước. Cần xác định:
- Consumer có thể offline bao lâu?
- Có cần replay sau incident không?
- Dữ liệu có chứa thông tin nhạy cảm hoặc PII không?
- Có quy định retention/audit riêng không?
- Chi phí storage tăng ra sao theo replication factor?
- Có cần compacted topic để giữ trạng thái cuối cùng theo key không?

Retention dài giúp replay và khôi phục consumer nhưng tăng chi phí storage và yêu cầu quản trị dữ liệu. Compaction phù hợp với topic lưu trạng thái theo key, nhưng không thay thế event history khi cần toàn bộ lịch sử.

### 11.4 Ví dụ tạo topic

Lấy bootstrap broker string từ MSK console hoặc API, rồi dùng Kafka CLI tương thích với phiên bản cluster.

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_BROKERS" \
  --command-config client.properties \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3
~~~

Ví dụ này giả định Provisioned Standard cluster có topology ba AZ và client được cấu hình authentication phù hợp. Với Express, kiểm tra quota/cấu hình topic được hỗ trợ. Với Serverless, tuân thủ quota và cấu hình topic mà dịch vụ cho phép.

Xem mô tả topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_BROKERS" \
  --command-config client.properties \
  --describe \
  --topic orders.created
~~~

Các thao tác quản trị hiện đại nên dùng `--bootstrap-server`. Không dựa vào ZooKeeper connection string để tạo topic hoặc quản trị cluster.

## 12. Producer và consumer configuration

### 12.1 Producer

Các tham số quan trọng:

| Tham số | Mục đích | Lưu ý |
|---|---|---|
| `acks` | Mức xác nhận ghi | `all` thường phù hợp với topic quan trọng |
| `enable.idempotence` | Giảm duplicate do retry | Kiểm tra compatibility và các tham số liên quan |
| `retries` | Retry khi lỗi tạm thời | Cần timeout và idempotence phù hợp |
| `delivery.timeout.ms` | Giới hạn thời gian giao bản ghi | Đặt theo latency/SLA và retry policy |
| `linger.ms` | Chờ gom batch | Có thể tăng throughput nhưng tăng latency |
| `batch.size` | Kích thước batch | Cân bằng throughput, memory và latency |
| `compression.type` | Nén record batch | Đánh giá CPU so với network/storage |
| `max.in.flight.requests.per.connection` | Số request đang chờ | Cần tương thích với idempotence và ordering |

Ví dụ cấu hình khái niệm:

~~~properties
acks=all
enable.idempotence=true
compression.type=lz4
linger.ms=5
batch.size=65536
delivery.timeout.ms=120000
~~~

Đây là điểm bắt đầu để benchmark, không phải cấu hình tối ưu cho mọi ứng dụng.

### 12.2 Consumer

Các tham số quan trọng:

| Tham số | Mục đích | Lưu ý |
|---|---|---|
| `group.id` | Định danh consumer group | Dùng group riêng theo workload/logic |
| `enable.auto.commit` | Tự động commit offset | Cân nhắc manual commit khi xử lý cần kiểm soát |
| `auto.offset.reset` | Vị trí bắt đầu khi không có offset | `earliest` có thể replay nhiều dữ liệu |
| `max.poll.records` | Số record mỗi poll | Cân bằng batch và processing time |
| `max.poll.interval.ms` | Thời gian xử lý giữa các poll | Tránh rebalance do xử lý quá lâu |
| `session.timeout.ms` | Phát hiện consumer mất kết nối | Phụ thuộc heartbeat và group protocol |
| `fetch.min.bytes` | Kích thước tối thiểu để fetch | Tăng batching, có thể tăng latency |
| `isolation.level` | Đọc transaction committed hay cả record chưa commit | Dùng `read_committed` khi cần transactional visibility |

Consumer phải commit offset theo đúng thời điểm xử lý. Nếu commit trước khi xử lý thành công, lỗi process có thể làm mất event khỏi luồng xử lý của ứng dụng. Nếu commit sau khi xử lý, crash giữa xử lý và commit có thể dẫn đến xử lý lặp. Hãy thiết kế idempotency hoặc transaction phù hợp.

## 13. Kết nối mạng và bootstrap endpoint

Amazon MSK chạy trong VPC và tạo network interface trong các subnet được chọn. Broker không mặc định public trên Internet. Client cần network path đến broker endpoint và security group cho phép traffic cần thiết.

### 13.1 Client trong cùng VPC

Cần kiểm tra:
- Client subnet route table.
- MSK subnet route table.
- Security group của broker ENI.
- Security group của client.
- Network ACL và firewall.
- DNS resolution.
- Kafka listener port tương ứng với authentication.
- TLS trust chain và client authentication.

Chỉ cho phép nguồn client cụ thể truy cập listener cần thiết. Không mở toàn bộ port cho `0.0.0.0/0`.

### 13.2 Bootstrap broker string

Bootstrap string là danh sách broker endpoint mà client dùng để khởi tạo kết nối và lấy metadata cluster. Kafka client sau đó biết partition leader và kết nối broker tương ứng.

Nên đưa broker từ nhiều AZ vào bootstrap list để client có nhiều điểm kết nối khi broker đang bảo trì hoặc lỗi.

Các bootstrap endpoint khác nhau theo authentication mode, ví dụ:
- IAM.
- SASL/SCRAM.
- TLS/mTLS.
- Unauthenticated nếu được bật.

Không hardcode endpoint broker đơn lẻ vào toàn bộ ứng dụng. Lưu endpoint theo môi trường và cấu hình deployment, đồng thời chuẩn bị cập nhật khi cluster thay đổi.

### 13.3 Kết nối từ nhiều VPC và account

Multi-VPC private connectivity của MSK dùng AWS PrivateLink để client ở VPC/account khác kết nối đến cluster mà traffic vẫn nằm trong AWS network.

Lợi ích:
- Giảm nhu cầu quản lý VPC peering hoặc Transit Gateway routing phức tạp.
- Hỗ trợ VPC có CIDR overlap.
- Có thể dùng cluster policy để cho account khác tạo managed VPC connection.
- Phù hợp mô hình nhiều account và shared streaming platform.

Cần kiểm tra:
- Kafka version tối thiểu được hỗ trợ.
- Authentication mode (IAM, TLS hoặc SASL/SCRAM).
- Apache Kafka ACL khi dùng SASL/SCRAM hoặc mTLS.
- Subnet và Availability Zone ID tương ứng.
- Giới hạn kết nối và phí liên quan.
- Multi-VPC private connectivity trong cùng Region; đây không phải kết nối xuyên Region.

### 13.4 On-premises và hybrid

Nguồn client on-premises có thể kết nối qua AWS Site-to-Site VPN hoặc AWS Direct Connect. Thiết kế cần:
- Route giữa data center và VPC.
- DNS resolution từ on-premises.
- Security group và firewall rule.
- MTU, packet loss, latency và throughput.
- TLS và certificate trust.
- Khả năng dự phòng khi VPN hoặc Direct Connect gián đoạn.
- Băng thông cho producer, consumer và replication.

Không đánh giá network chỉ bằng ping. Kafka sử dụng nhiều kết nối TCP dài hạn, request/response và replication traffic. Hãy benchmark bằng producer/consumer throughput và test broker failover.

## 14. Bảo mật: authentication, authorization và encryption

### 14.1 IAM access control

IAM access control kết hợp authentication và authorization. Client sử dụng AWS credentials/role để xác thực; IAM policy quyết định client có thể thực hiện thao tác Kafka nào trên cluster/topic/group.

Ưu điểm:
- Không cần duy trì username/password riêng cho từng client.
- Tích hợp IAM role cho EC2, ECS, EKS, Lambda hoặc workload AWS.
- Quản lý quyền theo principal và tài nguyên.
- Có thể audit các access event theo cơ chế AWS hỗ trợ.

Lưu ý:
- MSK Serverless bắt buộc dùng IAM access control.
- Với IAM authorization, Apache Kafka ACL không quyết định quyền của IAM identity; cần IAM policy.
- Non-Java client cần Kafka version và thư viện hỗ trợ theo tài liệu.
- Dùng role tách biệt cho producer, consumer và admin.

### 14.2 SASL/SCRAM

SASL/SCRAM dùng username/password được lưu trong AWS Secrets Manager và liên kết với cluster. MSK bật TLS cho client-broker traffic khi cấu hình SCRAM.

Phù hợp khi hệ thống hiện tại đã có Kafka client sử dụng SCRAM hoặc cần mô hình credential riêng. Cần quản lý:
- Secret lifecycle.
- Rotation.
- Quyền đọc secret.
- Kafka ACL cho authorization.
- Quy trình thu hồi credential.
- Không ghi password vào source code, log hoặc file cấu hình công khai.

### 14.3 Mutual TLS (mTLS)

mTLS xác thực client bằng certificate. MSK dùng AWS Private CA để ký client certificate trong mô hình được hỗ trợ.

Cần quản lý:
- CA và trust chain.
- Certificate issuance/renewal.
- Private key protection.
- Mapping identity với Kafka ACL.
- Quy trình thu hồi certificate và xử lý certificate bị compromise.

Amazon MSK không hỗ trợ certificate revocation list (CRL) theo tài liệu hiện hành. Do đó, thiết kế thu hồi/quản lý client certificate cần kết hợp ACL và security group phù hợp; không giả định CRL sẽ tự chặn certificate đã bị lộ.

### 14.4 Encryption at rest và in transit

Hai lớp mã hóa giải quyết hai rủi ro khác nhau:

- At rest: mã hóa dữ liệu lưu trữ bằng AWS KMS key theo cấu hình cluster.
- In transit: TLS giữa client và broker, cũng như giữa các thành phần broker/metadata theo cấu hình MSK.

Khi dùng IAM, SASL/SCRAM hoặc mTLS, client-broker traffic phải dùng TLS theo các tổ hợp bảo mật được MSK hỗ trợ. Không dùng plaintext listener cho dữ liệu production nhạy cảm.

### 14.5 Authorization theo topic và consumer group

Áp dụng least privilege:
- Producer chỉ có quyền ghi topic cần thiết.
- Consumer chỉ có quyền đọc topic và group cần thiết.
- Admin role được tách khỏi runtime role.
- Connector role chỉ truy cập topic/source/sink cần dùng.
- Hạn chế quyền tạo/xóa topic trong production.
- Rà soát wildcard ACL/IAM resource policy định kỳ.

## 15. MSK Connect và MSK Replicator

Hai dịch vụ này bổ trợ MSK nhưng không phải broker type.

### 15.1 MSK Connect

MSK Connect là dịch vụ quản lý Kafka Connect connector. Connector có thể đọc từ hoặc ghi tới hệ thống khác, ví dụ:
- Amazon S3.
- OpenSearch.
- Database.
- Data warehouse.
- Hệ thống SaaS hoặc Kafka-compatible khác.

MSK Connect quản lý worker và connector lifecycle. Người dùng vẫn phải chọn plugin, cấu hình connector, IAM role, network, secret, capacity và error handling.

Không nhầm MSK Connect với broker:
- Broker lưu topic/partition và phục vụ Kafka protocol.
- Connector di chuyển hoặc tích hợp dữ liệu giữa Kafka và hệ thống khác.

### 15.2 MSK Replicator

MSK Replicator sao chép topic data và metadata giữa Kafka cluster nguồn và đích theo cấu hình hỗ trợ. Nó có thể dùng cho:
- Cross-Region replication.
- Disaster recovery.
- Di chuyển cluster.
- Tách workload theo Region.
- Chuyển từ Kafka self-managed sang MSK.

MSK Replicator hoạt động bất đồng bộ. Replication latency phụ thuộc khoảng cách Region, throughput, partition count và capacity của hai cluster.

Cần phân biệt:
- Replicator có thể đồng bộ topic data/config và consumer offsets theo khả năng hỗ trợ.
- Replicator không sao chép trạng thái nội bộ của ứng dụng stateful như Flink/Kafka Streams.
- Stateful application có thể cần rebuild state hoặc custom checkpoint restoration khi migration.
- Cross-Region replication không thay thế quy trình kiểm thử failover/failback.

## 16. Scaling và capacity management

### 16.1 Scale dọc

Scale dọc là thay đổi broker size để tăng CPU, memory hoặc network capacity. Đây thường là cách tăng compute capacity mà không cần tự phân phối lại partition theo cùng cách với scale ngang.

Với Standard brokers:
- Có thể thay đổi broker size theo danh sách instance được hỗ trợ.
- Có giới hạn về việc scale xuống; tài liệu AWS nêu không thể đổi sang broker size nhỏ hơn trong một số luồng cập nhật Standard.
- Cần giữ headroom để rolling operation không làm cluster quá tải.

Với Express:
- Có thể thay đổi broker size trong các lựa chọn được hỗ trợ.
- Cấu hình và guardrail do MSK quản lý nhiều hơn.
- Intelligent rebalancing hỗ trợ phân phối tài nguyên khi scaling.

### 16.2 Scale ngang

Scale ngang là tăng hoặc giảm số broker. Khi thêm broker, cần xem partition placement và phân bố leader/follower.

Với Standard, việc thêm broker không đồng nghĩa mọi partition tự động được phân phối tối ưu lên broker mới. Cần kế hoạch reassignment và có thể dùng Kafka reassignment tool hoặc Cruise Control theo hướng dẫn MSK.

Với Express, intelligent rebalancing giúp quản lý partition movement khi scale. Kiểm tra trạng thái tính năng, đặc biệt với cluster vừa nâng cấp tại chỗ từ Standard.

### 16.3 Scale storage

Với Standard:
- Có thể tăng EBS storage.
- Không thể giảm storage đã cấp.
- Storage autoscaling có thể mở rộng theo ngưỡng.
- Cần theo dõi disk utilization, retention và growth rate.
- Mỗi lần scale storage có cooldown.

Với Express và Serverless, MSK quản lý storage capacity. Người dùng vẫn phải theo dõi dung lượng dữ liệu được giữ, retention, throughput và chi phí sử dụng.

### 16.4 Partition reassignment và headroom

Partition movement tạo thêm network và disk I/O. Nếu cluster đã gần saturation, rebalancing có thể làm producer latency tăng và consumer lag phình to.

Trước scaling:
1. Kiểm tra CPU, network, disk và request latency.
2. Kiểm tra under-replicated/offline partition.
3. Kiểm tra partition count theo broker.
4. Đánh giá replication traffic và background operation.
5. Chọn maintenance window hoặc thời điểm tải thấp khi cần.
6. Theo dõi reassignment và consumer lag.
7. Xác minh leader distribution sau khi hoàn tất.

## 17. Monitoring và logging

Amazon MSK tích hợp CloudWatch để thu thập metric Kafka. Provisioned cluster còn có thể bật Open Monitoring bằng Prometheus.

### 17.1 Metric cần theo dõi

| Metric/nhóm | Ý nghĩa | Tín hiệu cần điều tra |
|---|---|---|
| CPU User/System | Tải xử lý broker | CPU duy trì cao, thiếu headroom |
| BytesInPerSec | Throughput ghi | Tăng đột biến hoặc broker lệch tải |
| BytesOutPerSec | Throughput đọc | Consumer traffic tăng hoặc egress bottleneck |
| Request latency | Thời gian xử lý request | Producer/consumer response chậm |
| UnderReplicatedPartitions | Replica chưa theo kịp | Replication lag, broker/network/storage |
| OfflinePartitionsCount | Partition không có leader khả dụng | Rủi ro gián đoạn đọc/ghi |
| ActiveControllerCount | Trạng thái controller ở cấp cluster | Giá trị bất thường hoặc controller election |
| Consumer lag | Khoảng cách giữa log end và consumer offset | Consumer xử lý chậm hoặc dừng |
| Disk/storage usage | Dung lượng lưu trữ | Retention tăng, disk gần đầy |
| Connection count | Số kết nối client | Connection storm hoặc pool không giới hạn |
| Network throughput | Tải mạng broker | Saturation hoặc AZ traffic tăng |

Tên metric và mức monitoring có thể khác nhau giữa Standard, Express và Serverless. Kiểm tra metric namespace và dimensions hiện hành của broker type.

### 17.2 Monitoring level

MSK Provisioned có các mức monitoring, ví dụ:
- Default/cluster-level.
- Per-broker.
- Per-topic-per-broker.
- Per-topic-per-partition.

Mức chi tiết cao giúp tìm hot partition và broker imbalance nhưng tạo nhiều metric hơn, có thể phát sinh chi phí CloudWatch. Chọn mức theo nhu cầu điều tra và ngân sách.

### 17.3 Broker logs

MSK Provisioned có thể gửi broker logs tới:
- Amazon CloudWatch Logs.
- Amazon S3.
- Amazon Data Firehose.

Log hỗ trợ điều tra authentication failure, request error, broker event và hoạt động vận hành. Log destination cần được tạo và cấp quyền phù hợp trước khi bật delivery.

### 17.4 Open Monitoring

Provisioned cluster có thể bật Prometheus exporter để thu thập JMX/host metrics. Có thể dùng Amazon Managed Service for Prometheus, Amazon Managed Grafana hoặc hệ thống quan sát tương thích Prometheus.

Open Monitoring hỗ trợ phân tích chi tiết, nhưng cần tính network transfer và chi phí lưu trữ/query metrics. Không bật mọi metric ở mức partition nếu không có nhu cầu.

### 17.5 Alert và runbook

Nên có cảnh báo cho:
- Offline partition khác 0.
- Under-replicated partition kéo dài.
- Consumer lag vượt SLA.
- CPU/network/storage vượt ngưỡng vận hành.
- Broker connection hoặc authentication failure tăng đột biến.
- Disk gần giới hạn với Standard.
- Replicator lag tăng.
- DMS/connector error nếu pipeline có thành phần tích hợp.

Alert cần gắn với runbook và owner. Không tạo cảnh báo chỉ dựa vào một điểm dữ liệu ngắn nếu workload có burst bình thường.

## 18. Chi phí Amazon MSK

Chi phí phụ thuộc deployment option, broker type, số broker, storage, throughput, retention, data transfer và monitoring.

### 18.1 Provisioned Standard

Các thành phần chi phí thường gồm:
- Broker instance-hours.
- EBS storage được cấp.
- Provisioned storage throughput nếu sử dụng.
- Tiered storage nếu bật.
- Data transfer theo quy tắc AWS.
- CloudWatch metrics/logs và các dịch vụ tích hợp.

Storage đã cấp nhưng chưa sử dụng vẫn có thể phát sinh chi phí. Vì vậy, sizing EBS quá dư làm tăng bill; sizing quá thấp làm tăng rủi ro hết dung lượng.

### 18.2 Provisioned Express

Các thành phần chi phí thường gồm:
- Broker-hours.
- Storage managed theo usage.
- Data ingestion/storage theo bảng giá Express.
- CloudWatch monitoring/logging và tích hợp tùy chọn.

Express có thể cần ít broker hơn cho một workload cùng throughput so với Standard, nhưng không nên suy ra Express luôn rẻ hơn. Hãy benchmark, tính chi phí theo workload và retention, rồi so sánh tổng chi phí.

### 18.3 Serverless

Serverless tính phí theo dữ liệu streaming và lưu trữ/partition theo bảng giá hiện hành. Không phải trả tiền cho một số lượng broker instance do người dùng chọn, nhưng throughput, partition count và retention vẫn ảnh hưởng chi phí.

Serverless có thể phù hợp tải biến động; với workload ổn định và throughput cao liên tục, Provisioned có thể có economics tốt hơn tùy Region và cấu hình.

### 18.4 Chi phí monitoring và replication

CloudWatch enhanced metrics có thể phát sinh phí theo metric. Prometheus, log delivery, S3 retention và cross-Region replication cũng có chi phí riêng.

Lập cost model nên bao gồm:
- Baseline throughput.
- Peak throughput.
- Retention.
- Replication factor.
- Số partition.
- Data transfer.
- Monitoring level.
- Replicator/connector.
- Growth và burst headroom.

## 19. Tạo cluster và kết nối client: quy trình thực hành

Ví dụ triển khai một cluster Provisioned Standard cho workload order events.

### Bước 1: Chuẩn bị kiến trúc

Xác định:
- Region triển khai.
- Ba AZ cho production.
- Ba private subnet, mỗi subnet ở một AZ.
- Security group riêng cho MSK.
- Client workload chạy trong VPC hoặc kết nối hybrid.
- Authentication dùng IAM hoặc SASL/SCRAM.
- KMS key cho encryption at rest.
- CloudWatch metrics và broker log destination.

### Bước 2: Tạo cluster

Trong Amazon MSK console:
1. Chọn Create cluster.
2. Chọn cluster type Provisioned.
3. Chọn Kafka version còn được hỗ trợ.
4. Chọn broker type Standard hoặc Express.
5. Chọn broker size và số broker mỗi AZ.
6. Chọn ba AZ cho topology production phù hợp.
7. Chọn storage/throughput nếu Standard.
8. Chọn VPC, private subnet và security group.
9. Bật authentication và encryption.
10. Chọn monitoring level và broker log destination.
11. Tạo cluster và chờ trạng thái ACTIVE.

Nếu chọn Express, xác nhận Kafka version, broker size, 3 AZ và các API/feature mà ứng dụng cần. Nếu chọn Serverless, chọn subnet/VPC cho client và cấu hình IAM access control theo hướng dẫn.

### Bước 3: Lấy bootstrap brokers

Dùng MSK console hoặc API để lấy bootstrap broker string tương ứng với authentication mode. Không dùng endpoint của cluster khác môi trường.

Ví dụ lệnh mô tả cluster:

~~~bash
aws kafka describe-cluster \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN"
~~~

Thay `ap-southeast-1` và ARN bằng giá trị môi trường thực tế. Bootstrap broker string có thể lấy qua API tương ứng như `get-bootstrap-brokers`.

### Bước 4: Cấu hình client

Với IAM authentication, Java client có thể dùng cơ chế `AWS_MSK_IAM` và thư viện `aws-msk-iam-auth` theo phiên bản tương thích.

Ví dụ `client.properties`:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=AWS_MSK_IAM
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required;
sasl.client.callback.handler.class=software.amazon.msk.auth.iam.IAMClientCallbackHandler
~~~

Client cần AWS credentials thông qua IAM role/profile hoặc cơ chế credentials provider an toàn. Không ghi access key dài hạn vào file cấu hình.

### Bước 5: Tạo topic và kiểm tra producer/consumer

Dùng Kafka CLI tương thích với Kafka version. Tạo topic theo partition/replication policy đã thiết kế, rồi gửi và đọc một số event kiểm thử.

Kiểm tra:
- Client kết nối đúng listener.
- TLS và authentication thành công.
- Producer nhận acknowledgment.
- Consumer đọc được record.
- Offset được commit.
- Consumer group hoạt động đúng.
- CloudWatch metrics xuất hiện.
- Broker logs được gửi tới destination.

## 20. Nâng cấp tại chỗ từ Standard sang Express (cập nhật 19/11/2026)

Trước đây, cách phổ biến để chuyển một workload từ Standard sang Express là tạo cluster mới rồi dùng MSK Replicator hoặc MirrorMaker 2 để di chuyển topic và client. Ngày 19/11/2026, AWS công bố khả năng **in-place upgrade** từ Standard broker sang Express broker cho một số MSK Provisioned cluster đủ điều kiện.

Đây là thay đổi mới; cần kiểm tra tài liệu và Region trước khi lập kế hoạch. Không phải mọi Standard cluster đều có thể nâng cấp tại chỗ.

### 20.1 Điều kiện tiên quyết

Theo thông báo AWS ngày 19/11/2026, cluster cần đáp ứng các điều kiện chính:

- MSK Provisioned dùng Standard brokers.
- Kafka version 3.9 và KRaft metadata mode.
- Cluster được triển khai trên ba Availability Zones.
- Không bật tiered storage.
- Broker instance type nằm trong danh sách hỗ trợ.
- Partition count nằm trong quota Express.
- Các cấu hình topic/broker đáp ứng Express guardrail, gồm:
  - `replication.factor=3`
  - `min.insync.replicas=2`
  - `unclean.leader.election.enable=false`
  - `segment.ms` ít nhất 60.000 ms
  - `max.message.bytes` không vượt 8 MiB
  - `max.compaction.lag.ms` ít nhất 24 giờ

Nếu cluster đang ở Kafka version cũ hơn hoặc ZooKeeper mode, cần nâng cấp lên Kafka 3.9 và chuyển sang KRaft trước. Thực hiện từng bước theo quy trình AWS, có rehearsal và backup/rollback phù hợp.

### 20.2 Assessment trước upgrade

AWS cung cấp assessment API để kiểm tra broker/topic configuration trước khi bắt đầu. Ví dụ:

~~~bash
aws kafka create-assessment \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-type UPDATE_BROKER_TYPE \
  --assessment-parameters TargetInstanceType=express.m8g.large
~~~

Lấy assessment ARN từ response, sau đó mô tả assessment và đọc findings:

~~~bash
aws kafka describe-assessment \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-arn "$ASSESSMENT_ARN"
~~~

~~~bash
aws kafka list-assessment-findings \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-arn "$ASSESSMENT_ARN"
~~~

Các finding mức ERROR là blocker cần xử lý. WARNING/INFO cần được review và ghi nhận quyết định trước khi nâng cấp.

### 20.3 Khởi động upgrade

Quy trình dùng `UpdateBrokerType` với target instance type và chế độ reassignment topic.

Có hai cách:
- `AUTO`: MSK quản lý việc chuyển toàn bộ topic sang Express theo batch.
- `MANUAL`: MSK thêm Express broker, đội vận hành chuyển topic theo từng nhóm và xác minh từng bước.

Ví dụ khởi động AUTO:

~~~bash
aws kafka update-broker-type \
  --cluster-arn "$CLUSTER_ARN" \
  --current-version "$CURRENT_VERSION" \
  --target-instance-type kafka.m7g.large-express.m8g.large \
  --topic-reassignment AUTO
~~~

Các giá trị ví dụ phải được thay bằng Standard instance hiện tại, Express target hợp lệ và current version của cluster thực tế.

Trong giai đoạn chuyển đổi, Standard và Express broker cùng tồn tại. MSK di chuyển partition replica và leader bằng quy trình Kafka. Ứng dụng tiếp tục dùng cluster endpoint hiện tại; topic offsets được giữ theo quy trình upgrade AWS mô tả.

### 20.4 Theo dõi và xác minh

Theo dõi:
- Cluster operation state.
- Topic reassignment progress.
- Broker type và số partition trên từng broker.
- `PartitionCount`, `BytesInPerSec`, `BytesOutPerSec`.
- `LeaderCount` trên Standard broker.
- `ActiveControllerCount`.
- `OfflinePartitionsCount`.
- Producer/consumer throughput và latency.
- Consumer lag và trạng thái ứng dụng stateful.

Khi tất cả topic đã chuyển, kiểm tra ứng dụng ít nhất một chu kỳ xử lý đầy đủ. Nếu có vấn đề, có thể chuyển topic trở lại Standard trong giai đoạn Standard broker vẫn còn trong cluster.

### 20.5 Hoàn tất và giới hạn rollback

Chỉ decommission Standard broker sau khi đã xác nhận:
- Topic/partition đã chuyển đầy đủ.
- Producer/consumer throughput và latency đạt baseline.
- Stateful application hoạt động đúng.
- Không có offline partition.
- Consumer group và offsets được bảo toàn.
- Dashboard/alert đã được cập nhật.

Khi Standard broker đã bị decommission, rollback về Standard không còn là thao tác in-place. Cần tạo cluster mới và di chuyển dữ liệu bằng MSK Replicator hoặc phương án migration được hỗ trợ.

Trong thời gian Standard và Express cùng chạy, chi phí cả hai nhóm broker được tính. Metrics của Express khác Standard; ví dụ cần thay `KafkaDataLogsDiskUsed` bằng `StorageUsed` và bỏ các metric EBS như `BurstBalance` khỏi dashboard phù hợp.

Tài liệu AWS:
[Announcing in-place upgrades from Standard brokers to Express brokers for Amazon MSK (19 Nov 2026)](https://aws.amazon.com/blogs/big-data/announcing-in-place-upgrades-from-standard-brokers-to-express-brokers-for-amazon-msk/)

## 21. Bảo trì, version upgrade và vận hành

MSK quản lý nhiều thao tác hạ tầng nhưng cluster vẫn cần kế hoạch bảo trì.

### 21.1 Kafka version

- Theo dõi end-of-support date.
- Dùng version được MSK hỗ trợ và tương thích với client.
- Đọc release notes trước khi upgrade.
- Kiểm tra plugin, Kafka Connect, Kafka Streams và admin tooling.
- Rehearse trên cluster staging.
- Giữ headroom cho rolling restart.
- Theo dõi partition availability, ISR và consumer lag.

MSK có thể áp dụng chính sách version support và tự động nâng cấp version đã hết hỗ trợ theo điều kiện công bố. Không để cluster production chạy phiên bản cũ mà không có kế hoạch.

### 21.2 Broker maintenance và client resilience

Broker có thể offline trong bảo trì, patching, hardware failure hoặc network event. Kafka client phải:
- Có nhiều bootstrap broker.
- Retry có backoff và jitter.
- Refresh metadata.
- Tái kết nối sau leader change.
- Xử lý timeout và duplicate.
- Không giữ connection pool vô hạn hoặc tạo connection storm.
- Theo dõi producer error và consumer rebalance.

### 21.3 Cluster configuration

MSK cho phép tạo configuration revision và áp dụng cho cluster trong phạm vi broker type/version hỗ trợ. Express quản lý nhiều cấu hình hơn và có guardrail; Standard cho phép tùy chỉnh rộng hơn.

Không thay đổi hàng loạt config production mà không:
1. Lưu cấu hình hiện tại.
2. Xác định tác động.
3. Test trên staging.
4. Áp dụng theo cửa sổ phù hợp.
5. Theo dõi metric và error.
6. Có phương án rollback.

## 22. Các lỗi thường gặp và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Client timeout | Security group, route, DNS hoặc broker endpoint | Kiểm tra network path, port và bootstrap string |
| Authentication failed | Sai IAM policy, secret, certificate hoặc listener | Xác minh auth mode, role, secret và TLS |
| Producer throttling | Broker/client throughput quota hoặc cluster saturation | Xem BytesIn, request latency, CPU và quota |
| Consumer lag tăng | Consumer chậm, rebalance hoặc downstream lỗi | Xem lag, processing time, group membership |
| Offline partition | Không đủ replica/ISR hoặc broker/network failure | Xem broker health, ISR, RF và min ISR |
| Under-replicated partition | Follower không theo kịp leader | Kiểm tra disk, network, CPU và replication traffic |
| Disk gần đầy (Standard) | Retention dài, ingress tăng hoặc storage sizing thấp | Xem retention, bytes in, storage autoscaling |
| Partition skew | Key nóng hoặc partition assignment lệch | Phân tích traffic theo partition và key |
| Connection storm | Client restart đồng loạt hoặc retry quá nhanh | Backoff/jitter, pool lifecycle, connection metrics |
| Rebalance liên tục | Consumer timeout, xử lý lâu hoặc autoscaling quá nhanh | Xem poll interval, heartbeat và processing duration |
| Upgrade bị chặn | Version, quota, config hoặc partition count không phù hợp | Đọc assessment/operation findings |
| Express API không hoạt động | Tính năng Kafka chưa hỗ trợ trên Express | Kiểm tra feature support matrix và version |

## 23. Checklist thiết kế production

- [ ] Đã xác định workload ingress/egress trung bình và đỉnh.
- [ ] Đã xác định số topic, partition, replica và consumer group.
- [ ] Đã thiết kế partition key tránh hot partition.
- [ ] Đã xác định retention, replay và compaction policy.
- [ ] Đã chọn Provisioned Standard, Provisioned Express hoặc Serverless bằng tiêu chí rõ ràng.
- [ ] Đã xác minh Kafka version và feature support.
- [ ] Đã chọn ZooKeeper hoặc KRaft mode phù hợp version.
- [ ] Đã triển khai Multi-AZ theo yêu cầu availability.
- [ ] Replication factor và min ISR phù hợp durability.
- [ ] Producer có retry, idempotence và acknowledgment phù hợp.
- [ ] Consumer xử lý offset, retry, duplicate và rebalance an toàn.
- [ ] Bootstrap broker string có nhiều AZ.
- [ ] VPC, subnet, route, security group và DNS đã được kiểm tra.
- [ ] IAM/SCRAM/mTLS được chọn theo threat model và client capability.
- [ ] Encryption at rest và in transit được bật phù hợp.
- [ ] Secret/certificate được quản lý và rotation có quy trình.
- [ ] CloudWatch metrics, broker logs và consumer lag có dashboard/alert.
- [ ] Đã kiểm tra partition quota, connection quota và service quota.
- [ ] Đã benchmark broker throughput và client behavior.
- [ ] Đã diễn tập broker failure, AZ disruption và client reconnect.
- [ ] Đã có runbook cho scaling, upgrade, failover và recovery.
- [ ] Chi phí broker, storage, data transfer, metrics và retention đã được dự toán.
- [ ] Nếu nâng Standard lên Express, đã xác nhận điều kiện in-place upgrade và rollback boundary.

## 24. Bài tập thực hành

### Bài 1: Chọn mô hình triển khai

Một ứng dụng gửi event đơn hàng với tải biến động mạnh theo chiến dịch. Đội chưa biết chính xác throughput đỉnh và không cần tùy chỉnh broker sâu.

Yêu cầu: đề xuất mô hình ban đầu và các giới hạn cần kiểm tra.

Đáp án gợi ý: thử MSK Serverless nếu IAM-only access, quota và feature support phù hợp. Benchmark throughput/partition, kiểm tra quota Region, connection và chi phí theo data in/out/retention. Nếu tải cao ổn định hoặc cần custom config, so sánh Provisioned Express/Standard.

### Bài 2: Chọn Standard hay Express

Một nền tảng streaming có throughput cao, cần scale nhanh và muốn giảm công việc quản lý EBS. Ứng dụng dùng Kafka API thông thường.

Đáp án: Provisioned Express là ứng viên phù hợp. Cần kiểm tra ba AZ, Kafka version, broker size, quota, API support và giá storage/throughput. Nếu ứng dụng cần Kafka Streams API chuyên sâu hoặc config đặc thù, kiểm tra feature support trước khi chốt.

### Bài 3: Replication factor

Một topic quan trọng chạy trên Standard cluster ba AZ. Đội dự án đề xuất RF=1 để giảm storage.

Yêu cầu: phân tích rủi ro.

Đáp án: RF=1 không có follower replica, broker/AZ failure có thể làm partition offline hoặc mất dữ liệu. AWS khuyến nghị RF ít nhất 3 cho Standard broker production; đánh giá durability và storage cost trước khi quyết định.

### Bài 4: Chọn partition key

Topic `orders` có traffic dồn vào một khách hàng lớn. Đội dùng `customerId` làm key và thấy một partition nóng.

Đáp án: key giữ ordering theo customer nhưng một customer hot sẽ dồn tải. Xác định yêu cầu ordering thực tế, cân nhắc chia nhỏ theo orderId hoặc composite key nếu nghiệp vụ cho phép, rồi benchmark. Không thay key nếu làm mất thứ tự cần thiết.

### Bài 5: Consumer lag

Consumer group có 24 consumer nhưng topic chỉ có 12 partition.

Đáp án: tại một thời điểm, tối đa 12 consumer trong group có thể nhận partition; consumer còn lại không có partition được gán. Tăng consumer không tăng parallelism nếu partition count không tăng. Cần xem processing rate, partition design và quota.

### Bài 6: Chọn authentication

Một workload chạy trên ECS cần truy cập MSK Provisioned và tổ chức muốn tránh quản lý password.

Đáp án: IAM access control là lựa chọn phù hợp nếu Kafka client/driver hỗ trợ. Gắn task role, viết IAM policy tối thiểu cho topic/group/cluster và bật TLS. Kiểm tra non-Java/Java client version nếu có.

### Bài 7: Serverless quota

MSK Serverless bắt đầu throttle khi throughput tăng mạnh trong chiến dịch.

Đáp án: kiểm tra ingress/egress quota tổng và per-partition, hot partition, message size, connection và request rate. Tối ưu key/partition, batch/compression và xin quota increase nếu use case được chấp thuận. Đừng chỉ tăng số consumer nếu bottleneck nằm ở partition leader hoặc throughput quota.

### Bài 8: Standard sang Express

Một Standard cluster dùng Kafka 3.8, ZooKeeper mode và tiered storage. Đội muốn in-place upgrade sang Express.

Đáp án: chưa đủ điều kiện theo thông báo AWS 19/11/2026. Cần xử lý version lên 3.9, chuyển sang KRaft, đánh giá tiered storage (cluster có tiered storage không được hỗ trợ trong luồng in-place được công bố), topology ba AZ, config guardrail và partition quota. Rehearse, chạy assessment và chỉ hoàn tất khi ứng dụng được xác minh.

## 25. Câu hỏi tự kiểm tra

1. Amazon MSK khác Kafka tự quản lý trên EC2 ở điểm nào?
2. Broker có trách nhiệm gì trong Kafka cluster?
3. Topic và partition khác nhau như thế nào?
4. Kafka bảo đảm thứ tự ở phạm vi nào?
5. Leader và follower replica có vai trò gì?
6. ISR là gì?
7. `replication.factor=3` và `min.insync.replicas=2` giúp gì?
8. Consumer group và offset dùng để làm gì?
9. ZooKeeper mode khác KRaft mode ở điểm nào?
10. MSK Provisioned khác MSK Serverless ra sao?
11. Standard broker khác Express broker ở storage và configuration thế nào?
12. Vì sao Express chỉ triển khai ba AZ theo tài liệu hiện hành?
13. Khi nào tiered storage hữu ích và giới hạn nào cần lưu ý?
14. Vì sao quá nhiều partition có thể gây overhead?
15. IAM access control khác SASL/SCRAM và mTLS ở điểm nào?
16. MSK Serverless có hỗ trợ Kafka ACL để authorize IAM identity không?
17. MSK Connect khác MSK Replicator như thế nào?
18. Consumer lag tăng cần kiểm tra những thành phần nào?
19. Multi-VPC private connectivity sử dụng công nghệ gì?
20. Điều kiện quan trọng của in-place upgrade Standard sang Express công bố ngày 19/11/2026 là gì?

Gợi ý trả lời:

1. MSK quản lý nhiều phần hạ tầng broker/control plane; người dùng vẫn quản lý topic, client, schema và workload.
2. Nhận request, lưu partition/replica, phục vụ produce/fetch và replication.
3. Topic là luồng logic; partition là log có thứ tự bên trong topic.
4. Trong từng partition, không phải toàn topic nếu có nhiều partition.
5. Leader nhận ghi và phục vụ đọc; follower sao chép dữ liệu.
6. Tập replica đang đồng bộ theo điều kiện Kafka.
7. RF3 tạo ba replica; min ISR2 yêu cầu ít nhất hai replica đồng bộ để nhận ghi theo cấu hình.
8. Group chia partition cho consumer; offset ghi vị trí đọc.
9. ZooKeeper dùng node ngoài để quản lý metadata; KRaft dùng Kafka controllers.
10. Provisioned cho người dùng chọn broker capacity; Serverless tự quản lý compute/storage capacity.
11. Standard quản lý EBS và linh hoạt config; Express managed storage và guardrail nhiều hơn.
12. Đây là topology yêu cầu của Express theo tài liệu AWS hiện hành.
13. Giữ retention dài với tầng lưu trữ chi phí thấp; cần kiểm tra version, topic policy và remote read latency.
14. Tăng metadata, file handle, memory, recovery và rebalance overhead.
15. IAM dùng IAM principal/policy; SCRAM dùng username/password trong Secrets Manager; mTLS dùng client certificate.
16. Serverless yêu cầu IAM và không hỗ trợ Kafka ACL như authorization mechanism.
17. Connect chạy connector tích hợp hệ thống; Replicator sao chép topic/metadata giữa cluster.
18. Consumer processing, partition assignment, rebalance, downstream và broker/network.
19. AWS PrivateLink.
20. Provisioned Standard, Kafka 3.9 KRaft, ba AZ, không tiered storage, config/partition/broker đáp ứng Express requirements và assessment không còn blocker.

## 26. Tài liệu tham khảo chính thức

- [What is Amazon MSK?](https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html)
- [Amazon MSK broker types](https://docs.aws.amazon.com/msk/latest/developerguide/broker-instance-types.html)
- [Amazon MSK Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-broker-types-standard.html)
- [Amazon MSK Express brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-broker-types-express.html)
- [What is MSK Serverless?](https://docs.aws.amazon.com/msk/latest/developerguide/serverless.html)
- [Amazon MSK quotas](https://docs.aws.amazon.com/msk/latest/developerguide/limits.html)
- [Best practices for Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/bestpractices.html)
- [Metadata management: ZooKeeper and KRaft](https://docs.aws.amazon.com/msk/latest/developerguide/metadata-management.html)
- [Supported Apache Kafka versions](https://docs.aws.amazon.com/msk/latest/developerguide/supported-kafka-versions.html)
- [IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control.html)
- [SASL/SCRAM authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password-howitworks.html)
- [Mutual TLS authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication.html)
- [Multi-VPC private connectivity](https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html)
- [Monitoring an MSK Provisioned cluster](https://docs.aws.amazon.com/msk/latest/developerguide/monitoring.html)
- [Tiered storage for Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-tiered-storage.html)
- [Amazon MSK FAQ](https://aws.amazon.com/msk/faqs/)
- [In-place upgrades from Standard to Express brokers (19 Nov 2026)](https://aws.amazon.com/blogs/big-data/announcing-in-place-upgrades-from-standard-brokers-to-express-brokers-for-amazon-msk/)

Tính năng, broker size, Kafka version, Region availability, API support và quota của Amazon MSK thay đổi theo thời gian. Trước khi triển khai, hãy kiểm tra tài liệu đúng Region/version và chạy performance test, failure test cùng client compatibility test trên workload thực tế.

