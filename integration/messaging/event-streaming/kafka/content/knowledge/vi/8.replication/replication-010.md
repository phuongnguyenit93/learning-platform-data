# Preferred leader và cân bằng vai trò leader

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này tập trung vào **preferred leader**: replica được Kafka ưu tiên giữ vai trò leader của một partition theo thứ tự replica assignment.

Khi một broker gặp sự cố, partition có thể chuyển leader sang replica khác trong ISR. Sau khi broker ưu tiên phục hồi, leader của partition có thể vẫn nằm ở broker khác. Preferred leader election đưa leadership trở lại replica được ưu tiên khi replica đó đủ điều kiện. Cơ chế này giúp phân phối vai trò leader theo thiết kế ban đầu và cân bằng tải giữa các broker.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích preferred replica và preferred leader khác gì current leader.
- Xác định preferred replica từ danh sách replica của một partition.
- Mô tả vì sao leader có thể chuyển khỏi preferred replica sau sự cố.
- Giải thích điều kiện để preferred replica được bầu lại làm leader.
- Phân biệt preferred leader election với partition reassignment.
- Cấu hình và kiểm tra automatic preferred leader rebalance.
- Thực hiện preferred leader election bằng Kafka CLI hoặc AdminClient.
- Theo dõi mức độ mất cân bằng leadership và lựa chọn thời điểm rebalance an toàn.

## 2. Preferred replica và preferred leader là gì?

Một partition có một replica trên mỗi broker được phân công lưu partition đó. Trong danh sách replica assignment, **replica đứng đầu danh sách** được gọi là preferred replica (replica ưu tiên).

Khi preferred replica đang hoạt động và thuộc ISR, Kafka thường ưu tiên replica này làm leader. Khi nó giữ vai trò leader, ta gọi đó là preferred leader.

Ví dụ topic **orders** có ba partition:

| Partition | Replica assignment | Preferred replica |
|---|---|---|
| orders-0 | [1, 2, 3] | Broker 1 |
| orders-1 | [2, 3, 1] | Broker 2 |
| orders-2 | [3, 1, 2] | Broker 3 |

Nếu tất cả replica ưu tiên đều đủ điều kiện và đang giữ leadership, leadership sẽ được phân bố theo thiết kế assignment: broker 1 dẫn orders-0, broker 2 dẫn orders-1 và broker 3 dẫn orders-2.

Cần phân biệt ba thuật ngữ:

- **Replica assignment:** danh sách broker được phân công lưu bản sao của partition, theo thứ tự đã xác định.
- **Preferred replica:** replica đầu tiên trong danh sách assignment.
- **Current leader:** replica hiện đang giữ vai trò leader của partition.

Preferred replica là thuộc tính của assignment. Current leader là trạng thái vận hành tại thời điểm quan sát. Hai giá trị có thể khác nhau sau failover.

## 3. Vì sao current leader có thể khác preferred leader?

Giả sử partition **orders-0** có replica assignment:

~~~text
orders-0:
  Replicas = [1, 2, 3]
  Preferred replica = Broker 1
  Current leader = Broker 1
~~~

Ban đầu broker 1 là leader. Khi broker 1 dừng đột ngột, Kafka chọn một replica đủ điều kiện trong ISR để làm leader mới. Giả sử broker 2 được chọn:

~~~text
Sau khi broker 1 gặp sự cố:

orders-0:
  Replicas = [1, 2, 3]
  Preferred replica = Broker 1
  Current leader = Broker 2
  ISR = [2, 3]
~~~

Partition vẫn có leader và có thể tiếp tục phục vụ request nếu broker 2 hoạt động bình thường. Tuy nhiên, leadership hiện không nằm trên preferred replica.

Khi broker 1 khởi động lại, replica của nó cần bắt kịp dữ liệu và trở lại ISR. Việc broker 1 đã online không có nghĩa nó lập tức trở thành leader. Kafka cần xác nhận replica đủ điều kiện, sau đó preferred leader election mới có thể chuyển leadership trở lại broker 1.

Nếu preferred replica vẫn không nằm trong ISR, Kafka không nên ép nó làm leader chỉ để khôi phục trạng thái ưu tiên. Một replica ngoài ISR có thể thiếu các record đã được xác nhận trên leader hiện tại. Preferred leader election là clean election: chỉ replica đủ điều kiện trong ISR mới có thể được bầu.

## 4. Preferred leader election hoạt động như thế nào?

Preferred leader election yêu cầu Kafka chuyển leadership của partition về preferred replica khi replica đó nằm trong ISR và có thể nhận leadership.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B1 as Broker 1 (preferred)
    participant B2 as Broker 2 (current leader)
    participant C as Controller
    participant P as Producer / Consumer

    Note over B1,B2: Ban đầu B1 là leader của orders-0
    B1--xC: Broker 1 gặp sự cố
    C->>B2: Bầu B2 làm leader mới từ ISR
    B2-->>P: Tiếp tục phục vụ partition
    Note over B1,B2: Broker 1 khởi động lại và bắt kịp replica
    B1->>C: Replica B1 trở lại ISR
    C->>B1: Preferred leader election
    C->>B2: Chuyển leadership khỏi B2
    B1-->>P: B1 trở thành leader mới
~~~

Các bước chính:

1. Partition có preferred replica là broker 1.
2. Broker 1 dừng; controller thực hiện leader election theo trạng thái ISR.
3. Broker 2 được bầu làm current leader.
4. Broker 1 khởi động lại, fetch dữ liệu và bắt kịp replica.
5. Broker 1 trở lại ISR.
6. Automatic hoặc manual preferred leader election được kích hoạt.
7. Controller chuyển leadership về broker 1.
8. Broker 1 phục vụ request ghi/đọc với vai trò leader mới.

Preferred leader election chỉ thay đổi **vai trò leader**. Nó không thay đổi replica assignment, không sao chép lại toàn bộ dữ liệu sang broker khác và không thay đổi số partition của topic.

## 5. Lợi ích của việc cân bằng leadership

Kafka phân phối replica và preferred replica để tránh tập trung vai trò leader vào một số broker. Cân bằng leadership giúp phân phối tải request giữa các broker.

### 5.1. Phân phối tải đọc và ghi

Leader của partition tiếp nhận request ghi từ producer và phục vụ request đọc từ consumer. Nếu nhiều partition cùng có leader trên một broker, broker đó có thể chịu phần lớn tải network, CPU và disk I/O.

Khi preferred replica được phân bố hợp lý và leadership trở về đúng vị trí ưu tiên, tải leader có thể cân bằng hơn.

### 5.2. Giảm broker quá tải cục bộ

Một broker giữ quá nhiều leader có thể gặp:

- Network throughput cao hơn các broker khác.
- CPU tăng do xử lý produce/fetch request.
- Disk I/O tăng do ghi log và phục vụ đọc.
- Request latency cao và queue dài.
- Consumer fetch hoặc producer request tập trung vào broker đó.

Cân bằng leadership giúp giảm nguy cơ một broker trở thành điểm nóng do nhận quá nhiều request leader.

### 5.3. Duy trì phân bố leadership theo replica assignment

Replica assignment thường được tạo để phân bố preferred replica giữa các broker. Khi failover làm leader chuyển sang broker khác, phân bố thực tế có thể lệch khỏi thiết kế. Preferred leader election đưa leadership trở về vị trí được định trước khi các điều kiện cho phép.

### 5.4. Tận dụng tài nguyên cluster đồng đều hơn

Khi các broker có vai trò leader tương đối cân bằng, việc mở rộng hoặc vận hành cụm dễ dự đoán hơn. Tuy nhiên, cân bằng số lượng leader không bảo đảm cân bằng throughput tuyệt đối. Một partition có thể có lưu lượng cao hơn rất nhiều partition khác, vì vậy cần xem thêm traffic và kích thước dữ liệu.

## 6. Preferred leader election không phải partition reassignment

Đây là điểm rất dễ nhầm khi vận hành Kafka.

| Tiêu chí | Preferred leader election | Partition reassignment |
|---|---|---|
| Mục tiêu | Chuyển leadership về preferred replica | Thay đổi vị trí replica của partition giữa các broker |
| Replica assignment | Giữ nguyên | Có thể thay đổi |
| Di chuyển dữ liệu | Không yêu cầu di chuyển replica chỉ để đổi leader | Có thể phải sao chép dữ liệu sang broker mới |
| Thay đổi current leader | Có | Có thể có, tùy quá trình reassignment |
| Thay đổi số replica | Không | Có thể thay đổi nếu assignment mới khác số replica |
| Tác động chính | Phân phối request leader | Phân bố lưu trữ, replica và có thể cả leadership |

Ví dụ:

~~~text
Trước preferred leader election:
  Replicas = [1, 2, 3]
  Leader   = 2
  Preferred replica = 1

Sau preferred leader election:
  Replicas = [1, 2, 3]
  Leader   = 1
~~~

Danh sách replica không thay đổi.

Ngược lại, partition reassignment có thể đổi:

~~~text
Trước reassignment:
  Replicas = [1, 2, 3]

Sau reassignment:
  Replicas = [2, 3, 4]
~~~

Reassignment có thể tạo replica mới trên broker 4 và yêu cầu broker đó sao chép dữ liệu. Đây là thao tác có chi phí network và disk I/O, cần lập kế hoạch riêng.

Nếu mục tiêu chỉ là đưa leadership về broker ưu tiên đã có sẵn trong ISR, preferred leader election là cơ chế phù hợp. Nếu mục tiêu là di chuyển dữ liệu hoặc thay đổi phân bố replica, cần dùng partition reassignment.

## 7. Automatic preferred leader rebalance

Kafka broker có cấu hình điều khiển việc tự động cân bằng leadership.

Các cấu hình thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| **auto.leader.rebalance.enable** | Bật hoặc tắt automatic preferred leader election. |
| **leader.imbalance.per.broker.percentage** | Ngưỡng mất cân bằng leadership cho mỗi broker để controller xem xét rebalance. |
| **leader.imbalance.check.interval.seconds** | Khoảng thời gian giữa các lần kiểm tra mức mất cân bằng. |

Trong nhiều bản Kafka, automatic preferred leader rebalance được bật mặc định. Tuy nhiên, hãy kiểm tra giá trị thực tế trong broker config của cluster vì cấu hình có thể được thay đổi theo môi trường và phiên bản.

### 7.1. Cách automatic rebalance hoạt động

Khi automatic rebalance được bật, controller định kỳ kiểm tra các partition mà leader hiện tại không phải preferred replica. Nếu mức mất cân bằng vượt ngưỡng cấu hình và preferred replica đủ điều kiện, controller có thể thực hiện preferred leader election.

Ví dụ:

- Broker 1 có 100 partition được phân công làm preferred replica.
- Hiện tại chỉ 80 partition đang có leader ở broker 1.
- 20 partition còn lại đang do broker khác làm leader sau failover.
- Tỷ lệ mất cân bằng được đánh giá theo cấu hình và cách tính của Kafka.
- Khi vượt ngưỡng, controller có thể đưa leadership trở về các preferred replica đủ điều kiện.

Automatic rebalance không thể chuyển leadership về preferred replica đang offline hoặc không thuộc ISR. Trong trường hợp đó, partition tiếp tục dùng current leader đủ điều kiện.

### 7.2. Điều chỉnh ngưỡng rebalance

Ngưỡng quá thấp có thể khiến Kafka thường xuyên chuyển leadership khi có thay đổi nhỏ. Ngưỡng quá cao có thể để tình trạng mất cân bằng kéo dài.

Khoảng kiểm tra quá ngắn có thể khiến controller phải đánh giá thường xuyên; khoảng quá dài làm thời gian phát hiện mất cân bằng tăng.

Hãy lựa chọn theo:

- Số partition và số broker.
- Tần suất broker restart hoặc bảo trì.
- Tải produce/fetch và mức độ chênh lệch giữa broker.
- Thời gian replica cần để bắt kịp sau khi broker phục hồi.
- Mức độ chấp nhận leader movement trong môi trường production.

Ví dụ các thuộc tính trong file cấu hình broker:

~~~properties
auto.leader.rebalance.enable=true
leader.imbalance.per.broker.percentage=10
leader.imbalance.check.interval.seconds=300
~~~

Các con số trên chỉ là giá trị minh họa. Hãy kiểm tra cấu hình thực tế và tài liệu đúng phiên bản Kafka trước khi áp dụng. Có thể xem cấu hình broker bằng Kafka CLI:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type brokers --entity-name 1 --describe --all
~~~

Trên Windows PowerShell, dùng **.\\bin\\windows\\kafka-configs.bat** với cùng tham số. Cách cập nhật từng thuộc tính phụ thuộc việc thuộc tính đó có hỗ trợ dynamic broker configuration trong phiên bản đang chạy hay không; nếu không, hãy sửa cấu hình broker và áp dụng theo quy trình restart/bảo trì của cluster.

Không nên tăng tần suất rebalance để xử lý một broker quá tải do disk hoặc network. Preferred leader election chỉ phân phối vai trò leader; nó không sửa được nguyên nhân gốc như hot partition, key skew hoặc replica placement kém.

## 8. Kiểm tra trạng thái preferred leader

Dùng Kafka CLI để xem leader, replicas và ISR của topic.

Linux hoặc macOS:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả minh họa:

~~~text
Topic: orders
Partition: 0
Leader: 2
Replicas: 1,2,3
Isr: 1,2,3

Topic: orders
Partition: 1
Leader: 2
Replicas: 2,3,1
Isr: 2,3,1
~~~

Đọc kết quả:

- orders-0 có replica assignment [1,2,3], nên preferred replica là broker 1.
- Current leader là broker 2.
- Broker 1 nằm trong ISR, nên partition có thể đủ điều kiện cho preferred leader election.
- orders-1 có replica assignment [2,3,1], preferred replica là broker 2 và current leader cũng là broker 2.

Nếu preferred replica không xuất hiện trong ISR, không nên kỳ vọng preferred election chuyển leadership về replica đó ngay. Trước tiên cần xác định vì sao replica không đồng bộ và chờ nó bắt kịp.

## 9. Thực hiện preferred leader election bằng Kafka CLI

Kafka cung cấp công cụ **kafka-leader-election** để yêu cầu election.

### 9.1. Election cho một partition

Linux hoặc macOS:

~~~bash
bin/kafka-leader-election.sh \
  --bootstrap-server localhost:9092 \
  --election-type preferred \
  --topic orders \
  --partition 0
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-leader-election.bat --bootstrap-server localhost:9092 --election-type preferred --topic orders --partition 0
~~~

Lệnh yêu cầu Kafka đưa leader của partition orders-0 về preferred replica nếu replica đó đủ điều kiện.

### 9.2. Election cho toàn bộ partition

Một số phiên bản Kafka hỗ trợ tùy chọn **--all-topic-partitions** để yêu cầu preferred election trên toàn bộ partition:

Linux hoặc macOS:

~~~bash
bin/kafka-leader-election.sh \
  --bootstrap-server localhost:9092 \
  --election-type preferred \
  --all-topic-partitions
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-leader-election.bat --bootstrap-server localhost:9092 --election-type preferred --all-topic-partitions
~~~

Hãy kiểm tra trợ giúp của công cụ trong bản Kafka đang dùng nếu tên script hoặc tùy chọn khác nhau. Một số phiên bản hoặc bản phân phối có thể cung cấp cú pháp khác.

Sau khi chạy election, dùng kafka-topics --describe để xác nhận leader mới và ISR. Không nên chỉ dựa vào thông báo request đã gửi để kết luận mọi partition đã chuyển leadership thành công; partition có preferred replica không đủ điều kiện có thể không được election.

## 10. Thực hiện preferred leader election bằng Java AdminClient

Có thể gọi preferred leader election qua Kafka Admin API. Ví dụ dưới đây yêu cầu election cho một partition cụ thể:

~~~java
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.common.ElectionType;
import org.apache.kafka.common.TopicPartition;

import java.util.Properties;
import java.util.Set;

public class PreferredLeaderElection {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put(
            "bootstrap.servers",
            "localhost:9092"
        );

        try (Admin admin = Admin.create(properties)) {
            TopicPartition partition =
                new TopicPartition("orders", 0);

            admin.electLeaders(
                ElectionType.PREFERRED,
                Set.of(partition)
            ).all().get();

            System.out.println(
                "Preferred leader election request completed"
            );
        }
    }
}
~~~

Đây là thao tác quản trị cluster. Ứng dụng cần quyền phù hợp và phải xử lý exception nếu preferred replica không đủ điều kiện hoặc controller đang chuyển trạng thái.

Nếu muốn election cho nhiều partition, hãy truyền tập TopicPartition tương ứng. Không nên tự động gọi election liên tục từ ứng dụng nghiệp vụ; preferred leader election thường là thao tác vận hành hoặc được controller tự động thực hiện theo cấu hình.

## 11. Kiểm tra mức độ mất cân bằng leadership

Một cluster có thể có số lượng partition leader phân bố không đều. Để đánh giá, cần so sánh current leader với preferred replica và theo dõi tải thực tế của từng broker.

### 11.1. PreferredReplicaImbalanceCount

Kafka cung cấp metric controller có tên **PreferredReplicaImbalanceCount** trong nhiều phiên bản. Metric này phản ánh số partition có current leader khác preferred replica.

Nếu metric cao kéo dài, hãy kiểm tra:

- Preferred replica có online không?
- Preferred replica có nằm trong ISR không?
- Automatic preferred leader rebalance có được bật không?
- Ngưỡng leader imbalance có quá cao không?
- Controller có đang xử lý preferred election thất bại không?

Tên metric và cách expose có thể thay đổi theo phiên bản hoặc nền tảng giám sát. Hãy đối chiếu JMX metrics của Kafka đang chạy.

### 11.2. So sánh số leader theo broker

Ngoài metric imbalance, cần quan sát số lượng partition leader trên từng broker. Nếu broker 1 có 500 leader trong khi broker 2 và 3 chỉ có 100 leader, có thể leadership đang lệch đáng kể.

Tuy nhiên, số lượng leader bằng nhau không đảm bảo tải bằng nhau. Một partition có thể có throughput gấp hàng chục lần partition khác. Cần so sánh thêm:

- Bytes in per second.
- Bytes out per second.
- Produce request rate và fetch request rate.
- Request latency.
- CPU utilization.
- Disk I/O và network utilization.
- Partition count và leader count trên từng broker.

### 11.3. Đánh giá sau rebalance

Sau preferred leader election, kiểm tra:

1. PreferredReplicaImbalanceCount có giảm không?
2. Số lượng leader trên mỗi broker có cân bằng hơn không?
3. Produce/fetch throughput có phân bố hợp lý hơn không?
4. Request latency có cải thiện không?
5. ISR có ổn định không?
6. Có tăng lỗi client hoặc leader change bất thường không?

Nếu imbalance count giảm nhưng broker vẫn quá tải, hãy kiểm tra hot partition, key distribution và replica placement.

## 12. Khi nào nên thực hiện preferred leader election?

Các tình huống phù hợp:

- Broker vừa được bảo trì hoặc restart và replica đã bắt kịp ISR.
- Một số partition đang có leader ở broker khác preferred replica sau failover.
- Leadership bị lệch lâu dài so với replica assignment.
- Cần khôi phục phân bố leader sau một đợt sự cố đã kết thúc.
- Muốn chủ động cân bằng leadership trong maintenance window.

Các tình huống cần thận trọng:

- Preferred replica vẫn đang offline hoặc chưa vào ISR.
- Cluster đang có nhiều under-replicated partitions.
- Broker vừa phục hồi nhưng disk/network vẫn quá tải.
- Đang có reassignment hoặc leader election khác diễn ra.
- Producer/consumer latency đang cao và cluster chưa ổn định.

Preferred leader election có thể làm leader của nhiều partition thay đổi trong một khoảng thời gian ngắn. Client cần cập nhật metadata và gửi request đến leader mới. Vì thế, nếu chạy election trên toàn cluster, hãy xem xét số partition, tải client và khả năng xử lý của controller.

Không cần chạy preferred election ngay sau mỗi broker restart. Hãy để replica bắt kịp và xác minh ISR trước, sau đó thực hiện theo chính sách automatic rebalance hoặc một đợt thao tác có kiểm soát.

## 13. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Preferred election không chuyển leader | Preferred replica không nằm trong ISR hoặc không hoạt động. | Kiểm tra replica, ISR và trạng thái broker; chờ replica bắt kịp. |
| Leader vẫn nằm ở broker khác sau khi broker ưu tiên online | Replica chưa bắt kịp hoặc automatic rebalance bị tắt. | Kiểm tra ISR và auto.leader.rebalance.enable; thực hiện election khi đủ điều kiện. |
| PreferredReplicaImbalanceCount tăng | Nhiều partition đang có leader khác preferred replica. | Kiểm tra broker offline, ISR, cấu hình automatic rebalance và lỗi controller. |
| Leader chuyển đổi liên tục | Broker không ổn định, replica liên tục rời/vào ISR hoặc rebalance diễn ra quá thường xuyên. | Kiểm tra broker logs, network, disk, ISR và ngưỡng rebalance. |
| Broker vẫn quá tải sau preferred election | Tải partition không đồng đều hoặc có hot partition. | Phân tích throughput theo partition, key skew và replica placement. |
| Election báo lỗi một số partition | Partition không đủ điều kiện hoặc request bị từ chối. | Xem lỗi theo từng partition, kiểm tra preferred replica và ISR. |

Một số cấu hình nên kiểm tra:

- auto.leader.rebalance.enable
- leader.imbalance.per.broker.percentage
- leader.imbalance.check.interval.seconds
- unclean.leader.election.enable

**unclean.leader.election.enable** là cấu hình riêng về khả năng bầu replica ngoài ISR khi không còn replica ISR khả dụng. Nó không phải cách bật preferred leader election. Preferred election không nên được dùng để ép một replica ngoài ISR thành leader.

## 14. Bài tập thực hành

### Bài 1: Nhận diện preferred replica

Tạo hoặc chọn topic có một partition và replication factor 3. Dùng kafka-topics --describe để ghi lại:

- Partition ID.
- Replica assignment.
- Current leader.
- ISR.

Xác định preferred replica bằng phần tử đầu tiên của danh sách replica. So sánh preferred replica với current leader.

### Bài 2: Quan sát failover và preferred election

Trong cluster lab có ít nhất ba broker:

1. Xác nhận một partition có preferred replica là broker 1 và current leader là broker 1.
2. Dừng broker 1 trong môi trường lab.
3. Quan sát broker nào được bầu làm leader mới.
4. Khởi động broker 1 và chờ replica bắt kịp.
5. Xác nhận broker 1 đã trở lại ISR.
6. Thực hiện preferred leader election cho partition.
7. Dùng kafka-topics --describe xác nhận current leader đã trở về broker 1.

Không thực hiện thao tác dừng broker trên cluster production hoặc cluster dùng chung nếu chưa có kế hoạch bảo trì và quyền vận hành phù hợp.

### Bài 3: Quan sát automatic rebalance

1. Kiểm tra giá trị auto.leader.rebalance.enable.
2. Kiểm tra leader.imbalance.per.broker.percentage và leader.imbalance.check.interval.seconds.
3. Quan sát PreferredReplicaImbalanceCount trước và sau preferred election.
4. So sánh số lượng leader trên mỗi broker.
5. Giải thích vì sao metric imbalance giảm nhưng throughput có thể vẫn không đều.

### Bài 4: Phân biệt election và reassignment

Với một partition có assignment [1,2,3] và current leader là broker 2:

1. Xác định preferred replica.
2. Mô tả trạng thái sau preferred leader election.
3. Mô tả trạng thái sau reassignment sang [2,3,4].
4. Giải thích thao tác nào cần di chuyển dữ liệu và thao tác nào chỉ đổi vai trò leader.

## 15. Câu hỏi tự kiểm tra

1. Preferred replica được xác định từ phần nào trong replica assignment?
2. Preferred leader khác current leader ở điểm nào?
3. Vì sao broker phục hồi không lập tức trở thành leader?
4. Điều kiện quan trọng để preferred replica được bầu lại là gì?
5. Preferred leader election có thay đổi danh sách replica không?
6. Partition reassignment khác preferred election như thế nào?
7. Cấu hình nào bật/tắt automatic preferred leader rebalance?
8. PreferredReplicaImbalanceCount cho biết điều gì?
9. Vì sao cân bằng số lượng leader chưa chắc cân bằng throughput?
10. Khi nào không nên chạy preferred election trên toàn bộ cluster?
11. Preferred election có thể bầu một replica ngoài ISR làm leader không?
12. Nếu imbalance đã giảm nhưng broker vẫn quá tải, cần kiểm tra gì tiếp theo?

## Kết luận

Preferred replica là replica đầu tiên trong danh sách replica assignment của partition. Khi replica này đủ điều kiện và giữ vai trò leader, partition đang ở trạng thái preferred leadership. Sau failover, current leader có thể chuyển sang một replica khác trong ISR; preferred leader election đưa leadership trở về replica ưu tiên khi nó đã bắt kịp và có thể nhận vai trò leader.

Automatic preferred leader rebalance giúp Kafka tự kiểm tra và khôi phục phân bố leadership theo cấu hình broker. Người vận hành cũng có thể chủ động yêu cầu election bằng Kafka CLI hoặc AdminClient. Cần phân biệt thao tác này với partition reassignment: election chỉ chuyển vai trò leader, còn reassignment thay đổi vị trí replica và có thể cần di chuyển dữ liệu.

Để cân bằng cụm hiệu quả, hãy theo dõi preferred replica imbalance, leader count, throughput, request latency, ISR và tài nguyên broker. Preferred leader election là một phần của vận hành replication; nó phát huy tác dụng khi replica assignment hợp lý và các broker đủ khỏe để phục vụ tải.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Preferred replica | Replica đầu tiên trong replica assignment của partition. |
| Preferred leader | Preferred replica đang giữ vai trò leader. |
| Current leader | Replica hiện đang nhận request leader của partition. |
| Preferred leader election | Cơ chế chuyển leadership về preferred replica khi replica đủ điều kiện. |
| Automatic leader rebalance | Cơ chế controller định kỳ kiểm tra và cân bằng preferred leadership theo cấu hình. |
| ISR | Tập replica đang đồng bộ với leader theo điều kiện Kafka. |
| Partition reassignment | Thay đổi broker lưu replica của partition, có thể cần sao chép dữ liệu. |
| PreferredReplicaImbalanceCount | Metric controller phản ánh số partition có leader khác preferred replica trong các phiên bản hỗ trợ. |
| Leader imbalance | Tình trạng current leader không phân bố theo preferred replica assignment. |

