# Chính sách tự tạo topic và quản lý cấu hình topic

## Mục tiêu bài học

Kafka có thể tự tạo topic khi client tham chiếu đến một topic chưa tồn tại nếu broker và request cho phép. Cơ chế này tiện cho môi trường thử nghiệm, nhưng trong hệ thống thật, topic cần có số partition, replication, retention, cleanup policy và quyền truy cập phù hợp với yêu cầu vận hành. Bài học này giải thích cách Kafka tạo topic, nơi các giá trị mặc định được lấy, và cách quản lý topic một cách có kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt tự tạo topic với tạo topic chủ động bằng công cụ quản trị hoặc ứng dụng quản trị.
- Giải thích các cấu hình broker ảnh hưởng đến topic được tự tạo.
- Chọn chiến lược tạo topic phù hợp giữa môi trường local, test và production.
- Tạo và kiểm tra topic bằng Kafka CLI, Java AdminClient và Spring Kafka.
- Quản lý topic-level configuration, nhận diện cấu hình mặc định và cấu hình override.
- Phân biệt thay đổi cấu hình topic với thay đổi partition hoặc replica assignment.

## 1. Topic được tạo khi nào?

### 1.1. Tạo topic chủ động

Tạo topic chủ động nghĩa là một thao tác quản trị xác định trước tên topic, số partition, replication factor và các cấu hình cần thiết. Thao tác có thể được thực hiện bằng Kafka CLI, AdminClient, Spring Kafka `KafkaAdmin`, hoặc hệ thống quản lý hạ tầng.

Ví dụ một topic cho sự kiện đơn hàng có thể được chuẩn bị với:

- Tên `orders`.
- 6 partition để phân phối tải và cho phép consumer group xử lý song song.
- Replication factor 3 để có ba bản sao của mỗi partition.
- Retention theo thời gian phù hợp với yêu cầu replay.
- `min.insync.replicas` phù hợp với chính sách durability khi producer dùng `acks=all`.

Các con số trên chỉ là ví dụ. Số partition cần dựa trên thông lượng, số consumer, ordering theo key và khả năng tăng trưởng. Replication factor cần dựa trên số broker, vị trí lỗi cần chịu được và dung lượng lưu trữ.

### 1.2. Tự động tạo topic

Kafka broker có cấu hình `auto.create.topics.enable` để quyết định có cho phép tự tạo topic hay không. Khi một client gửi request metadata tham chiếu đến topic chưa tồn tại và request cho phép auto creation, broker có thể tạo topic theo các giá trị mặc định của cluster.

Ở phía consumer, cấu hình `allow.auto.create.topics` kiểm soát việc consumer có cho phép request metadata của nó kích hoạt tự tạo topic hay không. Đặt cấu hình này thành `false` giúp consumer không vô tình tạo topic chỉ vì tên topic sai hoặc topic chưa được triển khai. Hành vi thực tế vẫn phụ thuộc cấu hình broker và loại request/client đang sử dụng.

Luồng khái quát:

```text
Client tham chiếu topic "orders"
              |
              v
      Topic đã tồn tại?
         /         \
       Có           Không
       |              |
       v              v
  Trả metadata   Broker cho phép auto-create?
                    /       \
                  Có         Không
                  |            |
                  v            v
          Tạo theo defaults   Client không có topic metadata
                  |            |
                  v            v
             Trả metadata   Request có thể thất bại
```

Tự tạo topic không có nghĩa mọi thao tác gửi dữ liệu đều chắc chắn thành công. Broker vẫn phải xử lý metadata, tạo partition và leader, đáp ứng quyền truy cập và các điều kiện cluster. Client có thể thấy lỗi tạm thời trong quá trình topic được tạo hoặc leader được bầu.

### 1.3. Các giá trị mặc định khi tự tạo

Khi broker tự tạo topic, các giá trị mặc định chính thường liên quan đến:

| Broker configuration | Vai trò |
|---|---|
| `auto.create.topics.enable` | Bật/tắt khả năng broker tự tạo topic |
| `num.partitions` | Số partition mặc định cho topic được tạo tự động |
| `default.replication.factor` | Replication factor mặc định cho topic được tạo tự động |
| `log.retention.*` | Giá trị retention mặc định ở cấp broker nếu topic không override |
| `log.cleanup.policy` | Chính sách cleanup mặc định ở cấp broker nếu topic không override |
| `min.insync.replicas` | Ngưỡng ISR mặc định ở cấp broker nếu topic không override |

Trong nhiều cấu hình Kafka, `num.partitions` mặc định là 1 và `default.replication.factor` mặc định là 1. Các giá trị này có thể không phù hợp cho production. Không nên giả định cluster đang chạy dùng đúng các giá trị mặc định; nhà vận hành có thể thay đổi chúng và nhà cung cấp Kafka managed có thể áp dụng chính sách riêng.

Điểm quan trọng: giá trị mặc định được lấy từ cấu hình broker/cluster tại thời điểm topic được tạo. Thay đổi broker default sau đó không tự động đồng nghĩa mọi topic hiện có sẽ được cập nhật theo. Hãy kiểm tra topic-level config và nguồn cấu hình thực tế khi cần xác nhận.

## 2. Khi nào nên bật hoặc tắt auto creation?

### 2.1. Môi trường local và thử nghiệm

Auto creation có thể hữu ích khi:

- Người học muốn chạy producer/consumer nhanh mà chưa phải thực hiện bước tạo topic riêng.
- Môi trường demo hoặc sandbox được tạo mới thường xuyên.
- Topic thử nghiệm không cần retention, replication hoặc ACL đặc biệt.

Tuy vậy, ngay trong lab, tạo topic tường minh cũng có lợi: người học nhìn thấy số partition, replication factor và cấu hình thực tế thay vì vô tình dùng mặc định của broker.

### 2.2. Môi trường production

Production thường nên tạo topic chủ động trước khi triển khai producer và consumer. Cách này giúp đội vận hành review các quyết định về partition, replication, retention, cleanup và security.

Nếu auto creation được bật rộng rãi, các vấn đề có thể xuất hiện:

- Lỗi đánh máy trong tên topic tạo ra một topic mới không ai dự định quản lý.
- Topic được tạo với một partition và replication factor thấp hơn yêu cầu.
- Topic nhận retention hoặc cleanup policy không phù hợp với dữ liệu.
- Không có quy trình rõ ràng để gắn ACL, quota, schema và ownership.
- Số lượng topic tăng ngoài kiểm soát, gây thêm metadata và chi phí vận hành.

Một chính sách thường dùng là tắt `auto.create.topics.enable` ở production và tạo topic qua pipeline quản trị. Consumer cũng nên đặt `allow.auto.create.topics=false` nếu không có lý do cụ thể để cho phép tự tạo. Cần triển khai topic trước khi ứng dụng bắt đầu sử dụng; nếu không, client có thể nhận lỗi topic chưa tồn tại.

### 2.3. Phân quyền tạo topic

Tạo topic là thao tác quản trị cluster. Nên dùng một principal hoặc pipeline có quyền tạo và thay đổi topic. Producer/consumer runtime chỉ nên có quyền cần thiết để ghi, đọc và truy cập consumer group theo thiết kế bảo mật.

ACL và cơ chế authorization cụ thể phụ thuộc cấu hình cluster. Trong một số cấu hình, thao tác tạo topic có thể được cấp quyền ở phạm vi topic hoặc cluster. Không nên cấp quyền tạo topic rộng cho mọi service chỉ để khắc phục lỗi `UNKNOWN_TOPIC_OR_PARTITION`.

Khi kiểm tra lỗi, phân biệt:

- Topic chưa tồn tại hoặc chưa có metadata.
- Principal không có quyền tạo hoặc truy cập topic.
- Broker chưa sẵn sàng hoặc partition chưa có leader.
- Tên topic trong cấu hình client không khớp với tên được provision.

## 3. Quản lý topic như một tài nguyên có khai báo

### 3.1. Khai báo cấu hình mong muốn

Một topic production nên có định nghĩa rõ ràng về:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Name | Tên topic theo quy ước nào, team/service nào sở hữu? |
| Partitions | Cần bao nhiêu mức song song và lưu lượng tối đa dự kiến? |
| Replication factor | Cần chịu được bao nhiêu lỗi broker/rack? |
| `min.insync.replicas` | Cần tối thiểu bao nhiêu replica đồng bộ khi ghi với `acks=all`? |
| `retention.ms` / `retention.bytes` | Consumer cần replay trong bao lâu và cluster có bao nhiêu dung lượng? |
| `cleanup.policy` | Giữ log theo thời gian/dung lượng hay compact theo key? |
| `compression.type` | Broker dùng kiểu nén nào theo chính sách cluster/topic? |
| `max.message.bytes` | Kích thước record/batch tối đa có phù hợp producer và consumer không? |
| ACL | Principal nào được ghi, đọc, tạo hoặc mô tả topic? |

Lưu định nghĩa này trong hệ thống quản lý cấu hình hoặc Infrastructure as Code giúp review thay đổi, truy vết lịch sử và dựng lại môi trường. Có thể dùng Terraform, Ansible, Helm, pipeline riêng hoặc công cụ quản trị đang được tổ chức chuẩn hóa; điều quan trọng là một nguồn khai báo có chủ sở hữu.

### 3.2. Tách broker defaults và topic overrides

Kafka có cấu hình ở nhiều cấp. Broker config đặt giá trị mặc định hoặc hành vi chung cho broker. Topic config có thể override một số thuộc tính cho một topic cụ thể.

Ví dụ:

```text
Broker default:
  log.retention.hours = 168
  log.cleanup.policy = delete
  min.insync.replicas = 1

Topic "orders" override:
  retention.ms = 2592000000
  min.insync.replicas = 2
```

Trong ví dụ, topic `orders` có retention riêng và yêu cầu tối thiểu hai ISR. Những giá trị khác vẫn có thể kế thừa broker default nếu không được override. Các tên cấu hình và cách ưu tiên cần được xác nhận trên phiên bản Kafka đang chạy.

Một số topic config thường gặp:

| Topic config | Ý nghĩa |
|---|---|
| `retention.ms` | Thời gian giữ log theo thời gian |
| `retention.bytes` | Giới hạn dung lượng log theo partition |
| `cleanup.policy` | `delete`, `compact` hoặc kết hợp `compact,delete` |
| `min.insync.replicas` | Ngưỡng ISR tối thiểu để chấp nhận ghi với `acks=all` |
| `compression.type` | Chính sách nén record batch ở broker |
| `max.message.bytes` | Giới hạn kích thước record batch được chấp nhận ở topic |
| `segment.bytes` | Kích thước mục tiêu của log segment |
| `message.timestamp.type` | Chọn `CreateTime` hoặc `LogAppendTime` |

Không cần override tất cả cấu hình. Mỗi override làm tăng số quyết định cần review và theo dõi. Chỉ tạo override khi có yêu cầu rõ ràng khác với mặc định cluster.

### 3.3. Hiểu cleanup policy trước khi chọn retention

`cleanup.policy=delete` giữ log trong giới hạn retention theo thời gian hoặc dung lượng rồi xóa segment đủ điều kiện. Đây là lựa chọn thường gặp cho event stream cần lưu lịch sử trong một khoảng thời gian.

`cleanup.policy=compact` giữ lại giá trị mới nhất theo key theo tiến trình compaction. Nó hữu ích cho topic biểu diễn trạng thái hiện tại theo key, chẳng hạn cấu hình thiết bị hoặc trạng thái tài khoản. Compaction chạy nền; nó không xóa ngay lập tức mọi phiên bản cũ khi có record mới.

`cleanup.policy=compact,delete` kết hợp compaction với giới hạn retention. Cần hiểu rõ mục đích khôi phục và thời gian giữ dữ liệu trước khi chọn kết hợp này.

Tombstone là record có key và value `null`, thường dùng để biểu thị xóa key trong compacted topic. Tombstone chỉ được giữ theo các quy tắc liên quan như `delete.retention.ms`; consumer cần có thời gian phù hợp để quan sát tombstone nếu cần tái dựng trạng thái.

## 4. Tạo topic bằng Kafka CLI

### 4.1. Tạo topic tường minh

Trên Linux/macOS, lệnh thường có dạng:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
```

Trên Windows, dùng `kafka-topics.bat` nếu bản phân phối Kafka cung cấp script `.bat` tương ứng. Thay bootstrap server bằng địa chỉ listener mà máy chạy CLI truy cập được.

Replication factor không được lớn hơn số broker có thể nhận replica. Nếu cluster chỉ có một broker, ví dụ trên sẽ thất bại; với lab một broker, có thể dùng replication factor 1 để thực hành nhưng không đại diện cho cấu hình chịu lỗi production.

### 4.2. Kiểm tra topic và partition assignment

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả mô tả số partition, replication factor, leader, replica và ISR của từng partition. Hãy kiểm tra mọi partition có leader hợp lệ và số replica đúng dự kiến. Replication factor được khai báo khi tạo topic là mục tiêu phân bổ replica; trạng thái ISR thực tế có thể thấp hơn nếu broker mất kết nối hoặc replica chưa đồng bộ.

### 4.3. Kiểm tra và thay đổi topic config

Xem cấu hình topic:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Thay đổi một số cấu hình topic có thể được thực hiện bằng lệnh alter:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=2592000000,min.insync.replicas=2
```

Lệnh cụ thể và các config có thể thay đổi phụ thuộc phiên bản Kafka và quyền principal. Sau khi thay đổi, chạy lại `--describe` để xác nhận giá trị được áp dụng. Với môi trường được quản lý bằng IaC, cập nhật nguồn khai báo cùng lúc để tránh lần triển khai sau ghi đè thay đổi thủ công.

## 5. Tạo topic bằng Java AdminClient

AdminClient cung cấp API quản trị để tạo topic, mô tả topic và thay đổi cấu hình. Nó phù hợp cho công cụ provisioning hoặc service quản trị có quyền phù hợp.

### 5.1. Tạo topic

```java
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.ExecutionException;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.errors.TopicExistsException;

Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");

try (AdminClient admin = AdminClient.create(props)) {
    NewTopic orders = new NewTopic("orders", 6, (short) 3)
        .configs(Map.of(
            "retention.ms", "2592000000",
            "min.insync.replicas", "2",
            "cleanup.policy", "delete"
        ));

    try {
        admin.createTopics(List.of(orders)).all().get();
        System.out.println("Topic orders created");
    } catch (ExecutionException ex) {
        if (ex.getCause() instanceof TopicExistsException) {
            System.out.println("Topic already exists; verify its actual configuration");
        } else {
            throw ex;
        }
    }
}
```

Đây là ví dụ Java minh họa API; cần có dependency `kafka-clients` tương thích với cluster và cấu hình bảo mật nếu cluster yêu cầu TLS/SASL. `Map.of` yêu cầu Java 9 trở lên.

`createTopics` không phải thao tác reconcile toàn bộ trạng thái. Nếu topic đã tồn tại, Kafka trả lỗi `TopicExistsException`; ứng dụng không nên coi điều đó là bằng chứng topic đã đúng. Hãy tiếp tục gọi `describeTopics` và `describeConfigs` để kiểm tra số partition, replica assignment và các config cần thiết.

### 5.2. Mô tả topic và cấu hình

```java
var descriptions = admin.describeTopics(List.of("orders"))
    .allTopicNames()
    .get();

var description = descriptions.get("orders");
System.out.println("partitions=" + description.partitions().size());

for (var partition : description.partitions()) {
    System.out.printf(
        "partition=%d leader=%s replicas=%d isr=%d%n",
        partition.partition(),
        partition.leader(),
        partition.replicas().size(),
        partition.isr().size()
    );
}
```

Đoạn mã trên cho biết trạng thái partition assignment hiện tại. Để đọc topic config, tạo `ConfigResource` kiểu `TOPIC` với tên topic rồi gọi `describeConfigs`. Khi đọc kết quả, chú ý nguồn của cấu hình: giá trị có thể là topic override, broker default hoặc giá trị mặc định của Kafka. Các config nhạy cảm có thể không trả về giá trị thật.

### 5.3. Thay đổi cấu hình

Kafka client hiện đại hỗ trợ `incrementalAlterConfigs` để đặt, thêm, trừ hoặc xóa override theo từng config. Ví dụ khái niệm:

```java
ConfigResource topicResource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    "orders"
);

AlterConfigOp setRetention = new AlterConfigOp(
    new ConfigEntry("retention.ms", "2592000000"),
    AlterConfigOp.OpType.SET
);

admin.incrementalAlterConfigs(
    Map.of(topicResource, List.of(setRetention))
).all().get();
```

Ví dụ cần import `ConfigResource`, `ConfigEntry` và `AlterConfigOp` từ Kafka Admin API. Hãy xác nhận config là dynamic và có thể thay đổi trên phiên bản cluster đang dùng. Một số thuộc tính là read-only hoặc yêu cầu thay đổi ở broker level.

Khi xóa một topic override bằng thao tác `DELETE`, topic sẽ quay lại kế thừa giá trị mặc định theo cấu hình broker. Xóa override không có nghĩa giá trị trở thành 0 hoặc vô hạn; hãy đọc lại cấu hình sau khi thay đổi để xác nhận.

## 6. Tạo topic bằng Spring Kafka

Spring Kafka hỗ trợ khai báo `NewTopic` bean. Khi `KafkaAdmin` được cấu hình trong ứng dụng, các bean này có thể được dùng để gửi yêu cầu tạo topic khi application context khởi động.

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
            .partitions(6)
            .replicas(3)
            .config("retention.ms", "2592000000")
            .config("min.insync.replicas", "2")
            .config("cleanup.policy", "delete")
            .build();
    }
}
```

Ứng dụng cần có cấu hình `KafkaAdmin`/bootstrap server và quyền tạo topic. Spring Boot thường tự cấu hình `KafkaAdmin` khi có Spring Kafka trên classpath và có cấu hình kết nối tương ứng; hãy kiểm tra cấu hình của dự án cụ thể. Không nên để mọi service runtime đều tạo hoặc thay đổi toàn bộ topic nếu tổ chức đã có pipeline quản trị tập trung.

Khai báo bean giúp topic được tạo khi chưa tồn tại. Với topic đã tồn tại, việc kiểm tra và cập nhật cấu hình phụ thuộc phiên bản Spring Kafka và thiết lập admin; hãy xác minh hành vi thực tế, không xem bean như một cơ chế migration hoàn chỉnh cho mọi thay đổi topology.

## 7. Những thay đổi nào có thể thực hiện sau khi tạo?

Không phải mọi thuộc tính topic đều có thể sửa theo cùng một cách.

| Thay đổi | Cách xử lý và lưu ý |
|---|---|
| Topic-level config động như `retention.ms` | Có thể thay đổi qua Admin API/CLI nếu config được hỗ trợ là dynamic |
| Số partition | Có thể tăng; không hỗ trợ giảm số partition trực tiếp trong topic hiện có |
| Replication factor | Thay đổi bằng partition reassignment, không phải chỉ sửa topic config |
| Replica placement | Dùng partition reassignment để chuyển replica giữa broker/rack |
| Tên topic | Không có thao tác rename topic thông thường; thường tạo topic mới rồi migrate |
| Xóa topic | Thao tác phá hủy dữ liệu; cần quy trình kiểm soát và xác nhận ownership |

### 7.1. Tăng partition

Tăng partition có thể tăng mức song song cho consumer group và phân phối tải ghi. Tuy nhiên, nó có thể thay đổi mapping key-partition của partitioner dựa trên hash và làm các event mới của cùng key đi vào partition khác với event cũ. Điều này ảnh hưởng đến ordering theo key.

Trước khi tăng partition:

- Đo throughput và lag để xác định partition là nút thắt.
- Kiểm tra số consumer, giới hạn xử lý và tải broker.
- Xác định có yêu cầu ordering theo key hay không.
- Đánh giá partitioner và kế hoạch chuyển đổi nếu mapping key thay đổi.
- Xác nhận hệ thống downstream có chịu được số partition mới không.

### 7.2. Thay đổi replication factor

Replication factor xác định số replica của từng partition. Tăng hoặc giảm replica yêu cầu thay đổi assignment; việc này có thể tạo lưu lượng mạng và I/O đáng kể trong quá trình đồng bộ. Nên thực hiện theo từng đợt, theo dõi ISR, disk, network và trạng thái broker.

Không nhầm replication factor với `min.insync.replicas`. Replication factor là số bản sao được phân bổ; `min.insync.replicas` là ngưỡng replica đồng bộ tối thiểu để chấp nhận ghi với `acks=all`. Ví dụ RF=3 và min ISR=2 cho phép ghi khi ít nhất hai replica nằm trong ISR; nếu ISR tụt dưới 2, ghi có thể bị từ chối cho đến khi cluster phục hồi hoặc chính sách được thay đổi.

### 7.3. Thay đổi retention và cleanup

Giảm `retention.ms` hoặc `retention.bytes` có thể khiến segment đủ điều kiện bị xóa sớm hơn, làm giảm khả năng replay. Tăng retention làm tăng dung lượng cần thiết. Với compacted topic, thay đổi cleanup policy có thể ảnh hưởng cách hệ thống tái dựng trạng thái.

Trước khi thay đổi, hãy ước lượng tốc độ ghi, kích thước record, replication factor, thời gian replay cần hỗ trợ và dung lượng còn trống. Sau thay đổi, theo dõi disk usage và tốc độ xóa/compaction.

## 8. Quản lý drift và vòng đời topic

Một topic có thể lệch khỏi định nghĩa mong muốn vì ai đó thay đổi thủ công, pipeline triển khai thất bại hoặc broker defaults được cập nhật. Đây là configuration drift.

Một quy trình reconcile có thể gồm:

1. Đọc định nghĩa mong muốn từ repository hoặc hệ thống quản lý hạ tầng.
2. Gọi Admin API để mô tả topic, partition assignment và config hiện tại.
3. So sánh các thuộc tính có thể thay đổi an toàn với giá trị mong muốn.
4. Tạo topic còn thiếu; với topic đã tồn tại, kiểm tra thay đổi có tương thích và được phép không.
5. Áp dụng topic config động; lập kế hoạch riêng cho partition increase hoặc replica reassignment.
6. Xác minh lại trạng thái và ghi log/audit kết quả.

Không tự động xóa topic chỉ vì nó không còn xuất hiện trong file khai báo mà không có quy trình xác nhận. Topic có thể còn được consumer khác sử dụng hoặc chứa dữ liệu cần lưu giữ. Xóa topic và tạo lại cùng tên không khôi phục được dữ liệu đã mất.

Nên ghi lại owner, mục đích, data classification, retention, contact và quy trình decommission cho từng topic. Khi một service ngừng hoạt động, xác nhận không còn producer/consumer phụ thuộc trước khi thu hồi ACL hoặc xóa topic.

## 9. Checklist triển khai topic

Trước khi đưa topic vào production, kiểm tra:

- Tên topic đúng quy ước, có owner và mục đích rõ ràng.
- Số partition đáp ứng throughput, consumer parallelism và ordering theo key.
- Replication factor phù hợp số broker và failure domain.
- `min.insync.replicas` phù hợp với producer `acks` và mục tiêu durability.
- Retention và cleanup policy đáp ứng replay, compaction và dung lượng.
- Message size, compression và timestamp policy tương thích producer/consumer.
- ACL cấp quyền tối thiểu cho từng principal.
- Topic được tạo trước khi ứng dụng cần dùng nếu auto creation đã tắt.
- Topic config được quản lý trong nguồn khai báo và có quy trình phát hiện drift.
- Có dashboard/alert cho under-replicated partitions, offline partitions, ISR, disk usage và request errors.

## 10. Câu hỏi tự kiểm tra

1. Broker config nào bật hoặc tắt khả năng tự tạo topic?
2. `num.partitions` và `default.replication.factor` ảnh hưởng thế nào đến topic được tạo tự động?
3. Vì sao auto creation tiện cho lab nhưng có thể nguy hiểm trong production?
4. `allow.auto.create.topics` ở consumer có vai trò gì?
5. Sự khác nhau giữa broker defaults và topic-level overrides là gì?
6. `cleanup.policy=delete` khác `compact` như thế nào?
7. Vì sao `createTopics` trả `TopicExistsException` không chứng minh topic hiện tại đúng cấu hình mong muốn?
8. Có thể giảm số partition của topic hiện có không? Vì sao tăng partition có thể ảnh hưởng ordering theo key?
9. Replication factor khác `min.insync.replicas` ở điểm nào?
10. Vì sao thay đổi topic config thủ công cần được cập nhật vào nguồn khai báo quản lý hạ tầng?

## Kết luận

Auto creation dùng broker defaults để giúp client bắt đầu nhanh, nhưng không thay thế việc thiết kế topic. Với hệ thống vận hành thật, hãy khai báo topic tường minh, chọn partition và replication theo yêu cầu, đặt retention/cleanup phù hợp, cấp ACL tối thiểu và kiểm tra trạng thái sau mỗi thay đổi. AdminClient, Spring Kafka và Kafka CLI cung cấp các cách thực hiện; một nguồn cấu hình có quản lý giúp topic nhất quán qua nhiều môi trường và vòng đời triển khai.
