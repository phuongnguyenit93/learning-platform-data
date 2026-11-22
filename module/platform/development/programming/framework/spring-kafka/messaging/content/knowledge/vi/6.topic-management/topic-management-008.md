# Tạo topic bằng công cụ Kafka

Topic là nơi Kafka lưu các bản ghi sự kiện. Trước khi producer gửi dữ liệu và consumer đọc dữ liệu, topic cần tồn tại với số partition, replication factor và chính sách lưu trữ phù hợp. Kafka cung cấp các công cụ dòng lệnh để tạo, liệt kê, xem chi tiết, thay đổi cấu hình và xóa topic. Spring Kafka cũng có thể khai báo topic bằng `KafkaAdmin` và `NewTopic` khi ứng dụng khởi động.

Bài này sử dụng Kafka CLI với kết nối `--bootstrap-server`, cách làm phù hợp cho cả cluster chạy KRaft và các cluster Kafka hiện đại. Ví dụ dùng `localhost:9092`; hãy thay bằng địa chỉ bootstrap của môi trường đang thao tác. Các lệnh có hậu tố `.sh` dành cho Linux/macOS. Trên Windows, dùng script tương ứng trong `bin\windows` với hậu tố `.bat`.

## 1. Chuẩn bị công cụ và kết nối tới cluster

Kafka phân phối các script quản trị trong thư mục `bin` của bản cài đặt. Một số script thường dùng:

| Công cụ | Mục đích |
|---|---|
| `kafka-topics.sh` | Tạo, liệt kê, mô tả, tăng partition và xóa topic |
| `kafka-configs.sh` | Xem và thay đổi cấu hình của topic hoặc broker |
| `kafka-reassign-partitions.sh` | Lập và thực hiện kế hoạch phân phối lại replica giữa các broker |
| `kafka-consumer-groups.sh` | Kiểm tra consumer group và offset, hữu ích khi xác minh luồng đọc |

Trước khi chạy lệnh, cần biết địa chỉ bootstrap server có thể truy cập. Ví dụ cluster local:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Trên Windows PowerShell hoặc Command Prompt, lệnh tương ứng là:

```powershell
bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --list
```

Nếu Kafka chạy trong Docker, có thể chạy script từ container Kafka hoặc dùng địa chỉ port đã publish cho máy host. `localhost:9092` chỉ đúng khi broker thực sự lắng nghe trên địa chỉ đó từ nơi chạy lệnh. Trong môi trường bảo mật, truyền file cấu hình client bằng `--command-config`, ví dụ:

```bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config config/admin-client.properties \
  --list
```

File `admin-client.properties` chứa các thuộc tính kết nối và xác thực mà Kafka client cần, chẳng hạn cấu hình TLS hoặc SASL. Giữ file này trong vùng được bảo vệ và không đưa mật khẩu, token hay private key vào lệnh được lưu trong lịch sử terminal hoặc tài liệu chia sẻ.

Ưu tiên `--bootstrap-server` cho thao tác quản trị. Các hướng dẫn cũ có thể dùng `--zookeeper`; cách kết nối đó thuộc kiến trúc ZooKeeper cũ và không phải lựa chọn cho cluster KRaft.

## 2. Tạo topic

Lệnh tạo topic cơ bản cần tên topic, số partition và replication factor:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
```

Ý nghĩa các tham số:

- `--create`: yêu cầu Kafka tạo topic.
- `--topic orders`: tên topic cần tạo.
- `--partitions 6`: tạo sáu partition, được đánh số từ 0 đến 5.
- `--replication-factor 3`: mỗi partition có ba replica trên các broker khác nhau nếu cluster có đủ broker phù hợp.

Replication factor là số bản sao của mỗi partition, không phải số bản sao của toàn topic. Với replication factor bằng 3, một partition có một replica leader và tối đa hai replica follower. Producer và consumer thường giao tiếp với leader; follower sao chép dữ liệu để tăng khả năng chịu lỗi.

Cluster cần ít nhất ba broker có thể nhận replica để tạo topic với replication factor bằng 3. Nếu chỉ có một broker local, dùng `--replication-factor 1`. Không nên dùng replication factor 1 cho topic production quan trọng chỉ vì lệnh tạo topic chạy được trên máy local.

Để script triển khai có thể chạy lặp lại, dùng `--if-not-exists`:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --if-not-exists \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
```

Tùy chọn này tránh lỗi chỉ vì topic đã tồn tại. Nó không tự bảo đảm topic hiện hữu có đúng số partition, replication factor hoặc cấu hình mong muốn; hãy chạy bước kiểm tra sau khi tạo.

## 3. Liệt kê và mô tả topic

Liệt kê các topic mà tài khoản hiện tại được phép nhìn thấy:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Xem thông tin của một topic:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả thường hiển thị tổng số partition, replication factor, cấu hình topic và thông tin từng partition. Một dòng partition có các trường quan trọng:

```text
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
```

- `Partition`: mã partition.
- `Leader`: broker đang giữ vai trò leader của partition; giá trị `-1` cho biết hiện không có leader.
- `Replicas`: các broker được phân công giữ replica.
- `Isr`: tập replica đang đồng bộ (in-sync replicas) với leader.

Nếu một broker đang ngừng hoạt động, số replica trong ISR có thể thấp hơn số replica được phân công. Cần kiểm tra ISR và trạng thái broker trước khi kết luận topic đã sẵn sàng chịu lỗi. Có thể mô tả các partition đang thiếu replica đồng bộ bằng:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --under-replicated-partitions
```

Lệnh này giúp phát hiện partition có số replica trong ISR thấp hơn số replica được phân công. Trong vận hành, hãy kết hợp kết quả với log broker và tình trạng mạng/đĩa để tìm nguyên nhân.

## 4. Chọn partition và replication factor

Partition quyết định mức độ song song và phạm vi ordering của topic. Các bản ghi trong cùng một partition được đọc theo thứ tự offset. Kafka không bảo đảm thứ tự toàn cục giữa nhiều partition. Khi producer gửi record có key, partitioner thường dùng key để chọn partition, giúp các record cùng key đi cùng partition trong điều kiện số partition không đổi.

Một số nguyên tắc khi chọn số partition:

1. Ước lượng throughput cần đạt và khả năng xử lý song song của consumer group.
2. Xem số instance consumer dự kiến. Trong một consumer group, tại một thời điểm một partition chỉ được gán cho tối đa một consumer; số consumer vượt số partition sẽ có consumer nhàn rỗi.
3. Tính đến dung lượng lưu trữ, số file segment, chi phí phục hồi và thời gian rebalance. Tăng partition quá nhiều cũng làm tăng chi phí quản lý của broker.
4. Xem xét thứ tự theo key. Nếu nghiệp vụ cần các sự kiện của cùng một thực thể được xử lý theo thứ tự, producer phải gửi cùng key và thiết kế partition cần ổn định.

Replication factor quyết định mức dự phòng dữ liệu. Với replication factor 3 và `min.insync.replicas=2`, producer dùng `acks=all` chỉ được xác nhận khi có ít nhất hai replica đang ở ISR. Cấu hình này cân bằng khả năng chịu lỗi và tính sẵn sàng ghi; nếu ISR giảm dưới ngưỡng, producer có thể nhận lỗi thay vì ghi vào số replica quá ít. Hãy chọn các giá trị dựa trên số broker, yêu cầu độ bền dữ liệu và khả năng chấp nhận gián đoạn ghi.

Ví dụ tạo topic production có ba replica và sáu partition:

```bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.net:9092 \
  --create \
  --topic payments.events.v1 \
  --partitions 6 \
  --replication-factor 3
```

Đây chỉ là ví dụ về cú pháp. Số partition phù hợp còn phụ thuộc throughput, số broker, kích thước record, số consumer và SLA của hệ thống.

## 5. Xem và thay đổi cấu hình topic

Topic có các cấu hình ảnh hưởng đến lưu trữ và khả năng phục hồi. Một số cấu hình thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| `retention.ms` | Thời gian lưu dữ liệu trước khi segment đủ điều kiện bị xóa theo retention |
| `retention.bytes` | Giới hạn dung lượng lưu theo partition trước khi dữ liệu cũ đủ điều kiện bị loại bỏ |
| `cleanup.policy` | Chính sách dọn dữ liệu, thường là `delete` hoặc `compact` |
| `min.insync.replicas` | Số replica tối thiểu trong ISR để một số kiểu ghi như `acks=all` được chấp nhận |
| `segment.bytes` | Kích thước mục tiêu của một log segment |

Xem cấu hình topic:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Đặt thời gian retention thành bảy ngày và yêu cầu tối thiểu hai replica đồng bộ:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=604800000,min.insync.replicas=2
```

`604800000` mili giây tương đương bảy ngày. Cấu hình `min.insync.replicas=2` cần được phối hợp với replication factor và producer `acks`; đặt ngưỡng cao hơn số replica có thể duy trì trong ISR sẽ làm các lần ghi bị từ chối.

Để chuyển topic sang compaction:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact
```

`delete` giữ log trong khoảng retention rồi loại bỏ segment cũ. `compact` giữ lại giá trị mới nhất theo key qua quá trình compaction nền; tombstone có thể đánh dấu key cần xóa. Compaction không có nghĩa là chỉ còn đúng một record cho mỗi key ngay lập tức, vì các segment chưa được compact vẫn có thể chứa bản ghi cũ.

Xóa một override để topic quay về giá trị mặc định kế thừa:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --delete-config retention.ms
```

Sau khi thay đổi, chạy lại `--describe` để xác minh cấu hình hiệu lực. Giá trị mặc định có thể đến từ cấu hình broker và phiên bản Kafka; không nên giả định một giá trị cụ thể nếu chưa kiểm tra cluster.

## 6. Tăng số partition

Kafka cho phép tăng số partition của topic:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders \
  --partitions 9
```

Lệnh trên tăng topic từ sáu lên chín partition. Số partition chỉ có thể tăng theo cách này, không thể giảm bằng `kafka-topics --alter`. Muốn giảm số partition thường phải tạo topic mới với cấu trúc phù hợp rồi chuyển dữ liệu theo kế hoạch riêng.

Tăng partition có một hệ quả quan trọng với record có key: partitioner có thể ánh xạ cùng một key sang partition mới sau khi số partition thay đổi. Các record cũ vẫn nằm ở partition cũ trong khi record mới có thể sang partition khác. Vì vậy, thứ tự xử lý của một key xuyên suốt thời điểm thay đổi có thể không còn được duy trì như trước. Hãy đánh giá yêu cầu ordering, consumer group và quy trình migration trước khi tăng partition cho topic đang có dữ liệu.

Lệnh tăng partition không thay đổi replication factor. Thay đổi vị trí replica hoặc replication factor cần quy trình reassignment bằng công cụ `kafka-reassign-partitions.sh`, kèm kế hoạch tải mạng, dung lượng đĩa và trạng thái ISR. Không chỉnh trực tiếp metadata của broker để di chuyển replica.

## 7. Xóa topic

Khi topic không còn được sử dụng và dữ liệu có thể loại bỏ, lệnh xóa là:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic orders-test
```

Xóa topic là thao tác phá hủy dữ liệu. Việc xóa có thể diễn ra bất đồng bộ tùy trạng thái cluster và cấu hình broker; lệnh trả về không có nghĩa mọi file dữ liệu đã biến mất ngay lập tức. Quyền xóa còn phụ thuộc ACL và cấu hình cho phép xóa topic của cluster. Sau đó có thể dùng `--list` hoặc `--describe` để kiểm tra trạng thái.

Trước khi xóa topic production, cần xác nhận producer không còn ghi, consumer và ứng dụng phụ thuộc đã được chuyển đi, dữ liệu không còn nghĩa vụ lưu giữ và có phê duyệt vận hành cần thiết. Không dùng lệnh xóa để xử lý một topic đang lỗi replica hoặc consumer lag; hãy tìm nguyên nhân trước.

## 8. Tạo topic từ ứng dụng Spring Kafka

Khi muốn quản lý topic cùng cấu hình ứng dụng, Spring Kafka hỗ trợ khai báo bean `NewTopic`. `KafkaAdmin` dùng `AdminClient` để tạo topic khi ứng dụng khởi động nếu topic chưa tồn tại. Ví dụ:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .build();
    }
}
```

Ứng dụng cần cấu hình bootstrap server, ví dụ:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
```

Spring Boot thường cấu hình `KafkaAdmin` tự động khi có Spring Kafka trên classpath và có bootstrap server hợp lệ. Nếu dùng một broker local, đặt `.replicas(1)`; ví dụ `.replicas(3)` cần cluster có đủ broker nhận replica.

Khai báo `NewTopic` giúp việc tạo topic khi khởi động có thể lặp lại và đặt cấu hình mong muốn cạnh mã nguồn. Tuy nhiên, không nên coi bean này là công cụ migration tổng quát cho topic đã tồn tại. Khi topic đã được tạo, hãy kiểm tra trạng thái thực tế bằng Kafka CLI hoặc AdminClient và thực hiện thay đổi có chủ đích. Đặc biệt, giảm partition không được hỗ trợ và tăng partition có thể ảnh hưởng ordering theo key.

Trong production, nhóm vận hành có thể quản lý topic bằng pipeline triển khai hoặc công cụ quản trị tập trung; ứng dụng chỉ nên tự tạo topic nếu đó là quy ước đã thống nhất. Việc bật auto-create topic trên broker có thể khiến topic phát sinh với partition hoặc replication factor mặc định ngoài dự kiến. Chủ động khai báo topic giúp kiểm soát các thông số này tốt hơn.

## 9. Quy trình tạo và kiểm tra topic hoàn chỉnh

Một quy trình thực tế có thể gồm các bước sau:

1. Xác định tên topic theo domain và loại sự kiện, ví dụ `orders.created.v1`.
2. Chọn số partition dựa trên throughput, số consumer dự kiến và yêu cầu ordering theo key.
3. Chọn replication factor theo số broker và yêu cầu chịu lỗi.
4. Tạo topic bằng `kafka-topics` hoặc khai báo `NewTopic` theo quy trình triển khai của nhóm.
5. Thiết lập retention, cleanup policy và `min.insync.replicas` bằng `kafka-configs` nếu cần.
6. Chạy `--describe` để kiểm tra partition, leader, replicas và ISR.
7. Gửi thử một record, đọc thử bằng consumer thuộc group thử nghiệm và theo dõi log/metric trước khi chuyển traffic thật.

Ví dụ một bộ lệnh kiểm tra sau khi tạo topic:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders

bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Nếu partition không có leader hoặc ISR thấp hơn kỳ vọng, hãy xử lý tình trạng broker trước khi đưa producer vào sử dụng. Nếu số partition hoặc cấu hình không khớp, điều chỉnh theo quy trình thay đổi đã đánh giá tác động. Việc tạo topic thành công chỉ xác nhận metadata đã được chấp nhận; nó chưa chứng minh producer, consumer, quyền truy cập và chính sách lưu trữ đều hoạt động đúng.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp và hướng kiểm tra |
|---|---|
| `TopicExistsException` | Topic đã tồn tại; dùng `--if-not-exists` cho lệnh tạo lặp lại, sau đó `--describe` để kiểm tra cấu hình thực tế |
| `InvalidReplicationFactorException` | Replication factor lớn hơn số broker có thể nhận replica; kiểm tra cluster và chọn giá trị phù hợp |
| `InvalidPartitionsException` | Số partition không hợp lệ hoặc lệnh thay đổi không tăng số partition; kiểm tra giá trị hiện tại và giá trị yêu cầu |
| `TopicAuthorizationException` | Tài khoản thiếu ACL cho thao tác topic; nhờ quản trị viên cấp đúng quyền cần thiết |
| `TimeoutException` hoặc không kết nối được | Bootstrap server sai, listener/port không truy cập được, DNS hoặc TLS/SASL chưa đúng; kiểm tra từ đúng máy/container chạy CLI |
| Không có leader hoặc ISR thiếu replica | Broker ngừng hoạt động, replica chưa bắt kịp hoặc có vấn đề mạng/đĩa; kiểm tra broker log và trạng thái replica |
| Topic bị tạo với cấu hình ngoài dự kiến | Có thể topic đã được auto-create hoặc được tạo trước đó bởi pipeline khác; kiểm tra `--describe` và cấu hình broker |

## Checklist

- Đã kết nối đúng cluster bằng `--bootstrap-server` và tài khoản có quyền cần thiết.
- Tên topic, số partition và replication factor đã được xác định theo nhu cầu ứng dụng.
- Replication factor không vượt số broker có thể nhận replica.
- Retention, cleanup policy và `min.insync.replicas` phù hợp với yêu cầu dữ liệu.
- `--describe` cho thấy leader, replicas và ISR ở trạng thái mong muốn.
- Đã xem xét ảnh hưởng của tăng partition đối với ordering theo key.
- Các lệnh thay đổi hoặc xóa topic đã được kiểm tra đúng môi trường và đúng tên topic.

Kafka CLI cung cấp cách trực tiếp để quản lý vòng đời topic; Spring Kafka bổ sung khả năng khai báo topic cùng ứng dụng thông qua `KafkaAdmin` và `NewTopic`. Dù dùng cách nào, hãy xác minh metadata và trạng thái replica sau thao tác để bảo đảm topic sẵn sàng cho luồng messaging.
