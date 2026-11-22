# Kiểm tra metadata của topic

Kafka lưu metadata để mô tả cấu trúc topic và trạng thái phân phối partition trên các broker. Khi vận hành một luồng Spring Kafka, metadata cho biết topic có tồn tại hay không, có bao nhiêu partition, mỗi partition có leader nào, replica nào đang đồng bộ và topic đang dùng những cấu hình nào. Kiểm tra metadata giúp phát hiện sai cấu hình, thiếu replica, partition mất leader hoặc khác biệt giữa môi trường trước khi các vấn đề đó ảnh hưởng đến producer và consumer.

Metadata không chứa payload của record. Nó mô tả cách Kafka tổ chức và phục vụ log. Muốn kiểm tra dữ liệu thực tế cần dùng consumer hoặc công cụ đọc record; muốn kiểm tra cấu trúc và trạng thái topic thì dùng Kafka Admin API hoặc các lệnh quản trị.

## 1. Metadata của topic gồm những gì?

Khi mô tả một topic, các thông tin thường cần quan sát gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| Topic name | Tên topic mà producer và consumer sử dụng |
| Topic ID | Định danh nội bộ của topic trong cluster; không thay thế tên topic trong cấu hình ứng dụng |
| Internal topic | Cho biết topic có phải topic nội bộ do Kafka sử dụng hay không |
| Partition count | Số partition hiện có của topic |
| Replication factor | Số replica được gán cho mỗi partition theo cấu hình hiện tại |
| Partition leader | Broker đang nhận request đọc/ghi cho partition |
| Replicas | Danh sách broker được gán bản sao của partition |
| ISR | In-Sync Replicas, các replica đang theo kịp leader theo tiêu chí của Kafka |
| Offline replicas | Các replica hiện không khả dụng |
| Topic configs | Các cấu hình áp dụng ở cấp topic, ví dụ retention, cleanup policy và giới hạn kích thước record |

Một topic có thể có nhiều partition và mỗi partition có leader riêng. Ví dụ topic orders có 3 partition và replication factor bằng 3:

```text
Topic: orders
Partition 0: Leader 1, Replicas 1,2,3, ISR 1,2,3
Partition 1: Leader 2, Replicas 2,3,1, ISR 2,3,1
Partition 2: Leader 3, Replicas 3,1,2, ISR 3,1,2
```

Trong ví dụ này, mỗi partition có một leader và hai follower replica. Leader của partition 0 là broker 1, còn partition 1 và 2 có leader lần lượt là broker 2 và 3. Các broker đều nằm trong ISR, vì vậy tại thời điểm quan sát các replica đang đồng bộ.

## 2. Phân biệt replicas, leader và ISR

Khi đọc metadata, cần hiểu mối quan hệ giữa ba danh sách:

- **Replicas:** tất cả broker được gán lưu bản sao của partition, gồm cả leader và follower.
- **Leader:** một broker trong danh sách replicas, chịu trách nhiệm xử lý request đọc/ghi của partition.
- **ISR:** tập con các replica đang đáp ứng điều kiện đồng bộ với leader. Leader thông thường cũng thuộc ISR.

Ví dụ:

| Partition | Replicas | Leader | ISR | Nhận xét |
|---|---|---:|---|---|
| 0 | 1, 2, 3 | 1 | 1, 2, 3 | Các replica đều đồng bộ |
| 1 | 2, 3, 1 | 2 | 2, 3 | Broker 1 chưa theo kịp hoặc không còn trong ISR |
| 2 | 3, 1, 2 | - | - | Không có leader khả dụng tại thời điểm quan sát |

Khi ISR ít hơn số replicas, partition đang under-replicated. Nếu leader bị lỗi, Kafka cần bầu một leader mới từ replica đủ điều kiện. Khi không còn replica phù hợp để làm leader, partition có thể rơi vào trạng thái unavailable cho đến khi có replica đủ điều kiện hoặc người vận hành xử lý.

Replication factor là số bản sao được gán, không phải số bản sao hiện đang khỏe. Hãy so sánh Replicas, Isr và OfflineReplicas thay vì chỉ nhìn replication factor.

min.insync.replicas là một cấu hình khác với replication factor. Nó đặt ngưỡng ISR tối thiểu để một số thao tác ghi với acks=all được chấp nhận. Ví dụ replication factor bằng 3 và min.insync.replicas=2 cho phép ghi khi ít nhất hai replica còn trong ISR; nếu ISR giảm xuống 1, producer có thể nhận lỗi NotEnoughReplicas hoặc lỗi liên quan. Cấu hình này không tự tạo thêm replica và không bảo đảm rằng mọi replica luôn khỏe.

## 3. Xem metadata bằng Kafka CLI

### Liệt kê topic

Dùng kafka-topics.sh để liệt kê các topic mà principal hiện tại có quyền xem:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Kết quả giúp xác nhận tên topic, nhưng chưa cho biết trạng thái partition và replica. Danh sách có thể bao gồm topic nội bộ như __consumer_offsets tùy quyền và cách công cụ hiển thị.

### Mô tả một topic

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả điển hình có dạng:

```text
Topic: orders  TopicId: ...  PartitionCount: 3  ReplicationFactor: 3
  Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
  Topic: orders  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3
  Topic: orders  Partition: 2  Leader: 3  Replicas: 3,1,2  Isr: 3,1,2
```

Tên cột và định dạng có thể thay đổi theo phiên bản Kafka. Cách đọc các trường quan trọng:

| Trường | Cách diễn giải |
|---|---|
| PartitionCount | Tổng số partition của topic |
| ReplicationFactor | Số replica được gán cho mỗi partition trong mô tả tổng quát |
| Partition | Số thứ tự partition |
| Leader | Broker ID đang làm leader; giá trị -1 biểu thị không có leader |
| Replicas | Broker ID được gán replica |
| Isr | Broker ID hiện nằm trong ISR |

Để mô tả mọi topic, có thể bỏ tùy chọn --topic:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe
```

### Lọc partition có vấn đề

Một số phiên bản Kafka CLI hỗ trợ lọc các partition under-replicated hoặc unavailable:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --under-replicated-partitions

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --unavailable-partitions
```

Lệnh đầu tìm partition có số ISR nhỏ hơn số replica được gán. Lệnh thứ hai tìm partition không có leader khả dụng. Tùy phiên bản Kafka, tên tùy chọn hoặc cách lọc có thể khác; kiểm tra kafka-topics.sh --help trên đúng bộ công cụ đang triển khai.

## 4. Kiểm tra cấu hình ở cấp topic

Metadata về partition và replica không thay thế việc kiểm tra topic configs. Các cấu hình thường cần xem:

| Config | Ý nghĩa |
|---|---|
| cleanup.policy | Cách dọn dữ liệu: delete, compact hoặc kết hợp tùy phiên bản |
| retention.ms | Thời gian lưu dữ liệu theo chính sách retention |
| retention.bytes | Giới hạn dung lượng log theo partition |
| segment.bytes | Kích thước segment log mục tiêu |
| max.message.bytes | Giới hạn kích thước record batch ở cấp topic |
| min.insync.replicas | Số replica tối thiểu trong ISR cho ghi acks=all |
| message.timestamp.type | Chọn timestamp do producer gửi hay broker gán |

Dùng kafka-configs.sh để mô tả cấu hình topic:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Lệnh này thường hiển thị các cấu hình được override trực tiếp ở cấp topic. Để xem thêm cấu hình mặc định và nguồn cấu hình, có thể dùng --all nếu phiên bản Kafka CLI hỗ trợ:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe \
  --all
```

Khi kiểm tra, phân biệt cấu hình override tại topic với giá trị kế thừa từ broker hoặc giá trị mặc định của Kafka. Không thấy một khóa trong danh sách override không có nghĩa Kafka không có giá trị hiệu lực cho khóa đó.

Một số config là read-only, một số có thể thay đổi động và một số phụ thuộc phiên bản broker. Trước khi thay đổi config, hãy kiểm tra nguồn cấu hình, tính khả dụng của dynamic update và tác động đến retention, dung lượng hoặc khả năng ghi.

## 5. Kiểm tra metadata bằng AdminClient

Kafka cung cấp AdminClient để truy vấn metadata và quản trị tài nguyên. Có thể dùng describeTopics() để đọc mô tả topic từ Java:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.TopicPartitionInfo;

public class TopicMetadataReader {

    public void describe(AdminClient adminClient) throws Exception {
        Map<String, TopicDescription> topics = adminClient
                .describeTopics(List.of("orders"))
                .allTopicNames()
                .get(10, TimeUnit.SECONDS);

        TopicDescription description = topics.get("orders");
        if (description == null) {
            throw new IllegalStateException("Topic orders was not returned");
        }

        System.out.printf(
                "name=%s, topicId=%s, internal=%s%n",
                description.name(),
                description.topicId(),
                description.isInternal()
        );

        for (TopicPartitionInfo partition : description.partitions()) {
            String leader = partition.leader() == null
                    ? "none"
                    : Integer.toString(partition.leader().id());

            System.out.printf(
                    "partition=%d, leader=%s, replicas=%s, isr=%s, offline=%s%n",
                    partition.partition(),
                    leader,
                    partition.replicas(),
                    partition.isr(),
                    partition.offlineReplicas()
            );
        }
    }
}
```

describeTopics() trả về metadata của topic, gồm topic ID, cờ internal và danh sách partition. Mỗi TopicPartitionInfo cung cấp partition number, leader, replicas, ISR và offline replicas. Leader có thể là null khi partition chưa có leader khả dụng, vì vậy code nên kiểm tra trước khi truy cập broker ID.

AdminClient là client bất đồng bộ. Các phương thức trả về result chứa KafkaFuture; ví dụ trên chờ tối đa 10 giây bằng get(timeout, unit). Trong ứng dụng thực tế, cần xử lý timeout, lỗi authorization, topic không tồn tại và lỗi kết nối broker. Không nên chờ vô hạn trong request thread của API nghiệp vụ.

### Tạo AdminClient trong Spring Kafka

Nếu Spring Boot đã cấu hình KafkaAdmin, có thể tái sử dụng các thuộc tính kết nối đó để tạo AdminClient:

```java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
class KafkaAdminClientConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient topicAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
```

Bean được Spring đóng khi context dừng nhờ destroyMethod = "close". Nếu ứng dụng có nhiều cluster, hãy tạo AdminClient từ cấu hình của đúng cluster và đặt qualifier rõ ràng để tránh truy vấn nhầm môi trường.

Trong một ứng dụng đơn giản, chỉ cần KafkaAdmin và các bean NewTopic để khai báo topic khi khởi động. Chỉ tạo AdminClient riêng khi cần đọc metadata, kiểm tra config hoặc thực hiện thao tác quản trị theo luồng nghiệp vụ/vận hành.

## 6. Đọc topic configs bằng AdminClient

Metadata partition và topic config là hai truy vấn riêng. Có thể dùng describeConfigs() để đọc cấu hình topic:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.common.config.ConfigResource;

public class TopicConfigReader {

    public void describe(AdminClient adminClient) throws Exception {
        ConfigResource topic = new ConfigResource(
                ConfigResource.Type.TOPIC,
                "orders"
        );

        Map<ConfigResource, Config> configs = adminClient
                .describeConfigs(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS);

        Config config = configs.get(topic);
        for (Config.Entry entry : config.entries()) {
            System.out.printf(
                    "name=%s, source=%s, sensitive=%s, value=%s%n",
                    entry.name(),
                    entry.source(),
                    entry.isSensitive(),
                    entry.isSensitive() ? "<hidden>" : entry.value()
            );
        }
    }
}
```

Config.Entry cho biết tên, nguồn cấu hình, trạng thái sensitive/read-only và giá trị nếu được phép hiển thị. Một số giá trị nhạy cảm có thể bị ẩn; không ghi chúng vào log. Nguồn cấu hình giúp phân biệt override ở topic với cấu hình đến từ broker hoặc mặc định.

Nếu cần so sánh hai môi trường, hãy lấy cả topic description lẫn topic configs. Một topic có cùng tên và cùng số partition nhưng khác retention hoặc replication assignment vẫn có thể có hành vi vận hành khác nhau.

## 7. Khai báo topic bằng Spring Kafka

Spring Kafka cung cấp KafkaAdmin và NewTopic để khai báo topic bằng bean. Khi KafkaAdmin hoạt động trong application context, nó sử dụng broker admin API để tạo topic khi ứng dụng khởi động:

```java
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
class TopicConfiguration {

    @Bean
    KafkaAdmin.NewTopics applicationTopics() {
        return new KafkaAdmin.NewTopics(
                TopicBuilder.name("orders")
                        .partitions(6)
                        .replicas(3)
                        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
                        .build(),
                TopicBuilder.name("orders-dlt")
                        .partitions(6)
                        .replicas(3)
                        .build()
        );
    }
}
```

NewTopics gom nhiều khai báo topic trong một bean. TopicBuilder giúp mô tả partition count, replication factor và các topic config ngay trong mã nguồn. Các giá trị ví dụ giả định cluster có đủ broker để đáp ứng replication factor bằng 3.

Khai báo NewTopic giúp mô tả cấu hình mong muốn khi tạo topic. Với topic đã tồn tại, hành vi cần hiểu đúng:

- Spring Kafka có thể tăng số partition khi topic hiện có ít partition hơn khai báo, tùy khả năng broker và phiên bản framework.
- Kafka không hỗ trợ giảm số partition bằng thao tác alter partitions thông thường.
- Không nên mặc định rằng thay config trong bean NewTopic sẽ tự cập nhật mọi topic config của topic đã tồn tại. Dùng AdminClient incrementalAlterConfigs() hoặc kafka-configs.sh --alter cho thay đổi config có chủ đích.
- Nếu cluster quản lý topic bằng công cụ provisioning riêng, tránh để nhiều hệ thống cùng thay đổi một topic mà không có quy ước sở hữu.

## 8. Kiểm tra topic trước khi ứng dụng sử dụng

Một quy trình kiểm tra cơ bản cho topic orders có thể thực hiện theo thứ tự:

1. Xác nhận topic có trong danh sách bằng kafka-topics.sh --list.
2. Mô tả topic để kiểm tra partition count, replication factor, leader, replicas và ISR.
3. Kiểm tra topic configs như retention, cleanup policy và min.insync.replicas.
4. Kiểm tra partition unavailable và under-replicated.
5. Đối chiếu metadata với yêu cầu của producer, consumer và môi trường triển khai.

Ví dụ checklist:

| Hạng mục | Kỳ vọng minh họa | Dấu hiệu cần điều tra |
|---|---|---|
| Topic tồn tại | orders xuất hiện | Topic không tồn tại hoặc sai tên |
| Partition count | 6 | Không đủ mức song song dự kiến hoặc lệch giữa môi trường |
| Replication factor | 3 | Thấp hơn tiêu chuẩn độ bền của hệ thống |
| Leader | Mỗi partition có một broker leader | Leader là -1 hoặc không có leader |
| ISR | ISR bằng số replicas trong điều kiện khỏe | ISR giảm kéo dài |
| Offline replicas | Không có | Broker replica offline |
| Retention | Theo thời gian lưu nghiệp vụ | Retention quá ngắn hoặc quá dài |
| Cleanup policy | Phù hợp loại dữ liệu | Dùng compact/delete sai mục đích |
| min.insync.replicas | Phù hợp replication factor và acks | Giá trị làm producer ghi thất bại hoặc độ bền thấp hơn mong muốn |

Các giá trị trong bảng là ví dụ, không phải cấu hình đúng cho mọi topic. Hãy xác định mục tiêu về throughput, độ bền, retention và chi phí lưu trữ trước khi chọn thông số.

## 9. Những sai lệch thường gặp khi đọc metadata

| Hiện tượng | Cách hiểu đúng | Hướng xử lý |
|---|---|---|
| Topic tồn tại nhưng producer không ghi được | Metadata tồn tại không chứng minh producer có quyền ghi hoặc leader đang khả dụng | Kiểm tra ACL, leader, broker logs và lỗi producer |
| Replication factor là 3 nhưng ISR chỉ có 2 | Một replica đang chậm, mất kết nối hoặc chưa đủ điều kiện vào ISR | Kiểm tra broker, network, log replication và thời gian under-replicated |
| Partition có leader -1 | Không có leader khả dụng tại thời điểm truy vấn | Kiểm tra broker và replica; xác định nguyên nhân mất leader |
| Topic config không hiển thị mọi khóa | CLI có thể chỉ liệt kê override; giá trị khác được kế thừa | Dùng --all nếu hỗ trợ và xem config source |
| Thông tin client khác với CLI vừa chạy | Client có thể đang dùng metadata cache hoặc kết nối cluster khác | Xác nhận bootstrap servers, cluster identity và thời điểm refresh |
| Số partition đúng nhưng consumer không tăng throughput | Số consumer, partition assignment và tốc độ xử lý còn giới hạn song song | Kiểm tra consumer group và lag theo partition |
| Topic đã có nhưng bean NewTopic vẫn xuất hiện | Bean mô tả mong muốn; hành vi với topic tồn tại có giới hạn | Kiểm tra số partition và dùng API alter config riêng khi cần |

Metadata được broker quản lý và client thường cache để giảm số request. Sau khi thay đổi topic hoặc broker, kết quả quan sát từ client có thể chưa phản ánh ngay trạng thái mới. Khi so sánh, ghi nhận cluster, thời điểm truy vấn và dùng cùng một bootstrap endpoint để tránh kết luận sai.

## 10. Quyền truy cập và an toàn khi kiểm tra

Các lệnh metadata và Admin API cần quyền phù hợp. Tùy cấu hình bảo mật, principal có thể cần quyền mô tả topic, mô tả config hoặc quản trị cluster. Nếu gặp TopicAuthorizationException, ClusterAuthorizationException hoặc lỗi tương tự, hãy kiểm tra ACL của principal thay vì kết luận topic không tồn tại.

Không dùng tài khoản quản trị toàn quyền cho ứng dụng chỉ cần đọc metadata. Tách quyền theo mục đích:

- Ứng dụng runtime thường chỉ cần quyền mô tả và quyền đọc/ghi theo topic, group.
- Công cụ giám sát cần quyền đọc metadata và config ở phạm vi được phép.
- Quy trình provisioning cần quyền tạo topic, tăng partition hoặc alter config theo chính sách.

Các thao tác --alter, thay đổi replication assignment hoặc retention có thể tác động lớn đến dữ liệu và tải cluster. Khi chỉ cần kiểm tra, dùng lệnh read-only --list, --describe và --describe configs. Trước khi thay đổi, xác nhận đúng cluster, topic và kế hoạch khôi phục.

## 11. Checklist vận hành metadata topic

1. Xác nhận đúng bootstrap server và cluster trước khi truy vấn.
2. Kiểm tra topic name, topic ID và cờ internal khi cần phân biệt topic ứng dụng với topic nội bộ.
3. Kiểm tra partition count và replication factor theo yêu cầu thiết kế.
4. So sánh leader, replicas, ISR và offline replicas cho từng partition.
5. Đọc topic configs và phân biệt override với giá trị kế thừa.
6. Đối chiếu min.insync.replicas với replication factor và producer acks.
7. Dùng AdminClient hoặc KafkaAdmin trong Spring Kafka cho kiểm tra tự động có timeout và xử lý lỗi rõ ràng.
8. Cấp quyền metadata tối thiểu cần thiết cho ứng dụng và công cụ giám sát.
9. Ghi nhận cluster và thời điểm khi lưu kết quả kiểm tra để so sánh giữa các lần triển khai.

Metadata là bản mô tả cấu trúc và trạng thái phân phối của topic tại một thời điểm. Khi đọc đúng partition, leader, replicas, ISR và config source, nhóm phát triển có thể phát hiện sớm cấu hình sai hoặc broker gặp sự cố, đồng thời đưa ra quyết định phù hợp trước khi luồng gửi nhận sự kiện bị gián đoạn.
