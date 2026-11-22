# subscribe theo danh sách topic hoặc biểu thức chính quy

## Mục tiêu bài học

Kafka consumer có thể đăng ký đọc một danh sách topic cụ thể hoặc đăng ký theo một biểu thức chính quy để tự động nhận các topic có tên khớp mẫu. Hai cách đều dùng cơ chế quản lý consumer group của Kafka: consumer tham gia group, nhận partition assignment qua quá trình rebalance và đọc dữ liệu bằng `poll()`.

Sau bài học, bạn có thể:

- Dùng `subscribe(Collection<String>)` để đăng ký một hoặc nhiều topic theo tên.
- Dùng `subscribe(Pattern)` để đăng ký các topic theo quy tắc đặt tên.
- Viết regex Java đúng cách, đặc biệt với dấu chấm, dấu gạch và tiền tố topic.
- Hiểu cách consumer phát hiện topic mới khớp pattern và vì sao việc đó có thể gây rebalance.
- Phân biệt `subscribe()` với `assign()` và hiểu tác động của từng cách đến consumer group.
- Dùng `ConsumerRebalanceListener` để xử lý thu hồi và cấp phát partition.
- Thay đổi hoặc hủy subscription an toàn và kiểm tra các lỗi cấu hình thường gặp.

## 1. Subscription trong Kafka Consumer

### 1.1. Subscription mô tả topic cần đọc

Trong Java Kafka client, `KafkaConsumer` có thể đăng ký topic bằng hai API chính:

```java
consumer.subscribe(List.of("orders", "payments"));
```

hoặc:

```java
consumer.subscribe(Pattern.compile("^orders\\..+$"));
```

Ở cách thứ nhất, ứng dụng chỉ định các tên topic cụ thể. Ở cách thứ hai, ứng dụng đưa ra một quy tắc khớp tên; consumer sẽ đăng ký các topic mà tên của chúng khớp pattern.

Gọi `subscribe()` chưa có nghĩa partition được gán ngay lập tức. Consumer cần gọi `poll()` để tham gia group coordination, gửi subscription đến group coordinator và nhận assignment. Vì vậy, một ứng dụng gọi `subscribe()` rồi không `poll()` sẽ không bắt đầu tiêu thụ record theo cách thông thường.

### 1.2. Subscription do consumer group quản lý

Khi dùng `subscribe()`, consumer tham gia cơ chế quản lý group. Các member trong cùng group chia nhau các partition của những topic mà group đăng ký. Kafka coordinator và partition assignor phối hợp phân công partition; khi membership hoặc tập topic thay đổi, group có thể rebalance.

Ví dụ group `order-processors` đăng ký topic `orders` có sáu partition và chạy ba consumer:

```text
Consumer group: order-processors

Topic orders
  P0  P1  P2  P3  P4  P5
   |   |   |   |   |   |
   v   v   v   v   v   v
  C1  C1  C2  C2  C3  C3
```

Sơ đồ chỉ minh họa một assignment có thể xảy ra. Assignment thực tế phụ thuộc assignor, số member, số partition và trạng thái group. Trong cùng một group, một partition tại một thời điểm được gán cho tối đa một member; các group khác nhau có thể đọc cùng topic độc lập.

## 2. Đăng ký theo danh sách topic

### 2.1. `subscribe(Collection<String>)`

Dùng overload nhận `Collection<String>` khi ứng dụng biết chính xác topic cần đọc:

```java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("group.id", "order-service");
props.put("key.deserializer", StringDeserializer.class.getName());
props.put("value.deserializer", StringDeserializer.class.getName());

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders", "payments"));

    while (true) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, String> record : records) {
            System.out.printf(
                "topic=%s partition=%d offset=%d key=%s value=%s%n",
                record.topic(), record.partition(), record.offset(),
                record.key(), record.value()
            );
        }
    }
}
```

Các điểm cần chú ý:

- `group.id` xác định consumer group mà consumer tham gia.
- Key và value deserializer phải phù hợp với định dạng bytes producer đã ghi.
- `subscribe()` nhận tên topic, không nhận regex.
- `poll()` là vòng lặp chính để nhận record và duy trì hoạt động group coordination.
- Ví dụ dùng vòng lặp vô hạn để tập trung vào API; ứng dụng thật cần có quy trình shutdown và xử lý exception phù hợp.

### 2.2. Đăng ký nhiều topic cùng lúc

Nếu các topic cùng thuộc một nghiệp vụ và cần được xử lý bởi một consumer group, có thể đăng ký chúng trong một collection:

```java
List<String> topics = List.of(
    "orders",
    "payments",
    "shipments"
);

consumer.subscribe(topics);
```

Mọi partition của các topic đã đăng ký đều có thể được phân phối cho consumer group. Không có bảo đảm thứ tự tổng thể giữa các topic hoặc partition; nếu nghiệp vụ cần ordering, hãy xác định phạm vi ordering và dùng key/partition phù hợp.

### 2.3. Gọi lại `subscribe()` sẽ thay thế subscription hiện tại

`subscribe()` thiết lập tập subscription mới. Không nên giả định gọi thêm một lần với một topic mới sẽ tự động nối topic đó vào danh sách cũ.

Ví dụ, nếu ban đầu đăng ký `orders` rồi gọi:

```java
consumer.subscribe(List.of("payments"));
```

subscription mới là `payments`; `orders` không còn thuộc tập đăng ký. Nếu muốn thêm topic mà vẫn giữ các topic cũ, ứng dụng cần duy trì tập tên topic và gửi lại toàn bộ tập mong muốn:

```java
Set<String> topics = new HashSet<>(List.of("orders", "payments"));
topics.add("shipments");

consumer.subscribe(topics);
```

Thay đổi subscription có thể làm group rebalance và thay đổi partition assignment. Không nên cập nhật subscription liên tục theo từng record.

### 2.4. Overload có `ConsumerRebalanceListener`

Có thể truyền listener khi đăng ký:

```java
consumer.subscribe(
    List.of("orders", "payments"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            System.out.println("Revoked: " + partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            System.out.println("Assigned: " + partitions);
        }
    }
);
```

Listener hữu ích để lưu tiến độ xử lý, giải phóng tài nguyên gắn với partition hoặc khởi tạo trạng thái khi partition được giao. Phần xử lý chi tiết được trình bày ở mục về rebalance bên dưới.

## 3. Đăng ký theo biểu thức chính quy

### 3.1. `subscribe(Pattern)`

Dùng `Pattern` khi topic được đặt tên theo một quy ước và ứng dụng muốn nhận tất cả topic phù hợp mà không phải liệt kê từng tên:

```java
import java.util.regex.Pattern;

consumer.subscribe(Pattern.compile("^orders\\..+$"));
```

Pattern trên khớp các tên như:

- `orders.created`
- `orders.cancelled`
- `orders.refunded`

Nó không khớp `payments.created` hoặc tên `orders` không có phần hậu tố. Dấu `.` trong regex là ký tự đại diện cho một ký tự bất kỳ, vì vậy `\\.` trong chuỗi Java được dùng để khớp dấu chấm thực tế trong tên topic.

Kafka đánh giá pattern trên tên topic. Nên neo regex bằng `^` và `$` để thể hiện rõ phạm vi tên cần khớp, tránh pattern quá rộng ngoài ý muốn.

### 3.2. Ví dụ pattern thường dùng

| Nhu cầu | Regex Java | Ví dụ khớp |
|---|---|---|
| Tất cả topic bắt đầu bằng `orders-` | `Pattern.compile("^orders-.*$")` | `orders-created`, `orders-v2` |
| Topic theo domain orders hoặc payments | `Pattern.compile("^(orders|payments)\\..+$")` | `orders.created`, `payments.failed` |
| Topic có hậu tố `.events` | `Pattern.compile("^.+\\.events$")` | `orders.events`, `inventory.events` |
| Topic theo phiên bản số | `Pattern.compile("^orders-v[0-9]+$")` | `orders-v1`, `orders-v12` |

Ví dụ đăng ký cả hai domain:

```java
Pattern topicPattern = Pattern.compile(
    "^(orders|payments)\\..+$"
);

consumer.subscribe(topicPattern);
```

Pattern giúp giảm việc phải cập nhật danh sách topic trong ứng dụng khi có topic mới tuân theo quy ước. Tuy nhiên, nó cũng có thể khiến consumer nhận thêm topic mà nhóm ứng dụng không dự định xử lý nếu naming convention không đủ chặt.

### 3.3. Pattern được đánh giá trên metadata topic

Consumer cần biết tên topic trong cluster để xác định topic nào khớp pattern. Khi metadata được làm mới, client đánh giá lại tập topic phù hợp. Nếu một topic mới được tạo và tên của nó khớp pattern, consumer có thể tự động thêm topic đó vào subscription.

Ví dụ:

```text
Pattern: ^orders\\..+$

Lúc đầu metadata có:
  orders.created
  orders.cancelled

Subscription hiện tại:
  orders.created
  orders.cancelled

Sau đó quản trị viên tạo:
  orders.refunded

Khi consumer phát hiện metadata mới:
  orders.created
  orders.cancelled
  orders.refunded

Tập topic thay đổi -> consumer group có thể rebalance
```

Việc phát hiện topic mới không nhất thiết diễn ra ngay tại thời điểm topic được tạo. Nó phụ thuộc chu kỳ metadata refresh, request metadata và trạng thái kết nối của client. `metadata.max.age.ms` là một cấu hình liên quan đến việc làm mới metadata định kỳ; client cũng có thể refresh sớm hơn khi cần.

Pattern subscription không phải một lệnh tạo topic. Nó chỉ mô tả cách chọn tên topic từ metadata mà client nhìn thấy. Việc topic có được tạo tự động hay không là vấn đề riêng, phụ thuộc cấu hình broker/client và thao tác quản trị.

### 3.4. Overload pattern có listener

Có thể kết hợp regex với rebalance listener:

```java
Pattern pattern = Pattern.compile("^orders\\..+$");

consumer.subscribe(pattern, new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        saveProgressBeforeRevocation(partitions);
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        initializePartitionState(partitions);
    }
});
```

Các hàm trong ví dụ là logic minh họa do ứng dụng định nghĩa. Listener cũng có thể được dùng để log partition assignment, đóng resource theo partition hoặc khôi phục trạng thái xử lý.

## 4. Viết regex an toàn cho topic naming convention

### 4.1. Dùng namespace rõ ràng

Một quy ước tên topic nhất quán giúp pattern dễ giới hạn:

```text
<domain>.<entity-or-event>.<version>

orders.created.v1
orders.cancelled.v1
payments.completed.v1
inventory.changed.v2
```

Consumer của order service có thể dùng:

```java
Pattern.compile("^orders\\..+\\.v[0-9]+$")
```

Nếu topic naming convention không có namespace rõ ràng, regex rộng có thể vô tình match topic của service khác.

### 4.2. Tránh regex quá rộng

Ví dụ:

```java
Pattern.compile(".*")
```

Pattern này có thể khớp gần như mọi tên topic mà client nhìn thấy. Điều đó có thể khiến consumer đăng ký cả topic không liên quan, làm tăng số partition được phân phối, thay đổi consumer load và tạo rebalance khi topic mới xuất hiện.

Nên:

- Giới hạn bằng prefix/domain rõ ràng.
- Dùng nhóm lựa chọn cho các domain được phép.
- Neo pattern bằng `^` và `$`.
- Kiểm tra danh sách topic thực tế được match trong môi trường test trước khi triển khai.
- Xác nhận ACL và deserializer phù hợp với tất cả topic có thể được match.

### 4.3. Chú ý escaping trong Java string

Regex được viết trong Java string literal nên dấu backslash cần escape hai lần theo hai lớp cú pháp.

Ví dụ:

```java
// Regex mong muốn: ^orders\..+$
Pattern p = Pattern.compile("^orders\\..+$");
```

Nếu viết `"^orders\..+$"`, Java string có thể không hợp lệ vì `\.` không phải escape sequence hợp lệ trong Java string literal. Dùng raw regex trong một file cấu hình hoặc YAML cũng cần kiểm tra quy tắc escaping của định dạng chứa nó.

## 5. Consumer group và rebalance khi tập topic thay đổi

### 5.1. Vì sao subscription thay đổi có thể gây rebalance?

Group coordinator cần tính lại assignment khi một member tham gia/rời group hoặc khi tập topic/partition mà group quan tâm thay đổi. Các tình huống có thể kích hoạt rebalance gồm:

- Consumer mới tham gia hoặc consumer hiện tại rời group.
- Consumer không gửi heartbeat/poll đúng hạn và bị xem là không còn hoạt động.
- Subscription danh sách được thay đổi.
- Pattern subscription phát hiện topic mới khớp regex hoặc tập topic khớp thay đổi.
- Số partition hoặc trạng thái topic thay đổi.

Trong rebalance, một số partition có thể bị thu hồi khỏi consumer hiện tại rồi giao cho member khác. Ứng dụng cần xử lý offset và công việc đang dang dở đúng cách để tránh bỏ sót hoặc xử lý trùng.

### 5.2. `ConsumerRebalanceListener`

Listener có hai callback thường dùng:

- `onPartitionsRevoked`: được gọi khi các partition sắp bị thu hồi theo quy trình rebalance thông thường. Ứng dụng thường commit tiến độ đã xử lý an toàn và dừng tác vụ gắn với các partition đó.
- `onPartitionsAssigned`: được gọi sau khi partition được giao cho consumer. Ứng dụng có thể khởi tạo trạng thái hoặc khôi phục dữ liệu liên quan.

Các phiên bản Kafka client mới còn có callback `onPartitionsLost` để thông báo partition đã bị mất ownership mà không có quá trình revoke bình thường. Hãy kiểm tra API version đang dùng trước khi triển khai callback này.

Ví dụ listener đầy đủ với hai callback phổ biến:

```java
ConsumerRebalanceListener listener = new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        // Commit chỉ các offset đã xử lý hoàn tất.
        consumer.commitSync(offsetsForCompletedRecords(partitions));
        stopPartitionWorkers(partitions);
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        initializePartitionWorkers(partitions);
    }
};

consumer.subscribe(List.of("orders", "payments"), listener);
```

Các hàm `offsetsForCompletedRecords`, `stopPartitionWorkers` và `initializePartitionWorkers` là phần triển khai của ứng dụng. Không commit offset cao hơn vị trí liên tục đã xử lý thành công; nếu commit vượt qua record chưa hoàn tất, consumer mới có thể bỏ qua công việc đó.

### 5.3. Callback cần ngắn và an toàn

Rebalance listener được gọi trong luồng điều khiển consumer, thường gắn với lời gọi `poll()`. Không nên thực hiện công việc kéo dài, gọi HTTP không giới hạn hoặc chờ một worker vô thời hạn trong callback. Điều đó có thể kéo dài rebalance và làm consumer group mất ổn định.

Nếu ứng dụng xử lý record bất đồng bộ, trước khi partition bị thu hồi cần:

1. Ngừng nhận công việc mới cho partition đó.
2. Chờ hoặc hủy có kiểm soát các tác vụ đang chạy.
3. Xác định offset liên tục đã xử lý thành công.
4. Commit offset an toàn nếu còn quyền sở hữu và chính sách cho phép.
5. Giải phóng trạng thái/resource gắn với partition.

Consumer có thể nhận lại record sau rebalance hoặc crash. Vì vậy, side effect nghiệp vụ vẫn nên idempotent.

## 6. Thay đổi và hủy subscription

### 6.1. Cập nhật danh sách topic

Khi ứng dụng cần thêm hoặc bỏ một topic trong danh sách tĩnh, hãy xây dựng lại tập mong muốn và gọi `subscribe()` với toàn bộ tập đó:

```java
Set<String> topics = new HashSet<>(List.of("orders", "payments"));

// Sau khi cấu hình runtime thay đổi:
topics.add("shipments");
topics.remove("payments");

consumer.subscribe(topics);
```

Việc cập nhật nên được điều phối từ thread sở hữu consumer. `KafkaConsumer` không được thiết kế để nhiều thread gọi đồng thời các thao tác thông thường; chỉ `wakeup()` được cung cấp như cơ chế đánh thức thread consumer từ thread khác.

### 6.2. `unsubscribe()`

Gọi `unsubscribe()` để hủy subscription hiện tại:

```java
consumer.unsubscribe();
```

Sau khi hủy, consumer không còn đăng ký topic/partition qua group-managed subscription. Thao tác này có thể khiến group rebalance và các partition được giao cho member khác. Nếu ứng dụng không còn cần consumer, thường nên đóng consumer bằng `close()` để rời group và giải phóng tài nguyên.

### 6.3. Kiểm tra subscription và assignment

Hai API sau phục vụ hai mục đích khác nhau:

```java
Set<String> subscribedTopics = consumer.subscription();
Set<TopicPartition> assignedPartitions = consumer.assignment();
```

- `subscription()` cho biết các topic consumer đã đăng ký quan tâm.
- `assignment()` cho biết các partition hiện được gán cho consumer.

Sau `subscribe()` nhưng trước khi group coordination hoàn tất, assignment có thể còn rỗng. Không nên dùng `subscription()` để suy ra consumer đã có partition hoặc đang đọc được dữ liệu.

## 7. `subscribe()` khác `assign()` như thế nào?

`subscribe()` dùng group management để Kafka phối hợp phân chia partition giữa các consumer. `assign()` đặt trực tiếp partition mà một consumer sẽ đọc:

```java
consumer.assign(List.of(
    new TopicPartition("orders", 0),
    new TopicPartition("orders", 1)
));
```

So sánh:

| Tiêu chí | `subscribe()` | `assign()` |
|---|---|---|
| Đầu vào | Tên topic hoặc regex pattern | Danh sách `TopicPartition` cụ thể |
| Phân phối partition | Group coordinator/assignor quản lý | Ứng dụng tự chỉ định |
| Rebalance tự động | Có, theo consumer group | Không có group-managed partition assignment |
| Phát hiện topic mới theo regex | Có thể tự mở rộng subscription | Không; ứng dụng phải tự khám phá và assign |
| Phù hợp | Consumer service thông thường, mở rộng member | Công cụ đọc partition cụ thể, xử lý độc lập hoặc quản lý assignment riêng |

Không trộn `subscribe()` và `assign()` trên cùng consumer như hai cơ chế đồng thời. Gọi một API sẽ thay đổi chế độ subscription/assignment của consumer. Nếu ứng dụng dùng `assign()`, nó chịu trách nhiệm phân phối partition, xử lý ownership và tránh hai process cùng đọc/ghi tiến độ một cách không kiểm soát.

## 8. Cấu hình consumer và quyền truy cập

Một consumer dùng `subscribe()` thường cần:

| Cấu hình | Vai trò |
|---|---|
| `bootstrap.servers` | Danh sách broker để khởi đầu kết nối và lấy metadata |
| `group.id` | Tên consumer group |
| `key.deserializer` | Giải mã key bytes |
| `value.deserializer` | Giải mã value bytes |
| `auto.offset.reset` | Chính sách khi group chưa có offset hoặc offset không còn hợp lệ |
| `enable.auto.commit` | Bật/tắt commit offset tự động |
| `allow.auto.create.topics` | Cho phép consumer request metadata có thể kích hoạt auto topic creation trong điều kiện broker hỗ trợ |
| `metadata.max.age.ms` | Chu kỳ tối đa để làm mới metadata định kỳ |

Với regex subscription, consumer cần nhìn thấy metadata của các topic phù hợp. Principal cũng cần quyền phù hợp để mô tả và đọc các topic đó cùng quyền sử dụng consumer group. Nếu pattern match một topic mà principal không được phép truy cập, consumer có thể gặp lỗi authorization hoặc không thể tiêu thụ topic đó. Quy tắc ACL cụ thể phụ thuộc cơ chế bảo mật và phiên bản cluster.

Không nên dùng regex rộng rồi cấp quyền đọc toàn cluster chỉ để tránh lỗi. Hãy thiết kế namespace và ACL theo domain/service ownership.

## 9. Spring Kafka: khai báo topic list hoặc topic pattern

Trong Spring Kafka, `@KafkaListener` có thể đăng ký topic bằng danh sách tên hoặc bằng pattern:

```java
@KafkaListener(
    topics = {"orders", "payments"},
    groupId = "order-service"
)
public void consume(String payload) {
    process(payload);
}
```

Với pattern:

```java
@KafkaListener(
    topicPattern = "^(orders|payments)\\..+$",
    groupId = "order-service"
)
public void consume(String payload) {
    process(payload);
}
```

Spring Kafka xây dựng subscription tương ứng cho listener container. Pattern cũng chịu ảnh hưởng của metadata refresh, topic naming convention và group rebalance như Java client nền. Hãy kiểm tra phiên bản Spring Kafka đang dùng vì các thuộc tính annotation và cách cấu hình container có thể thay đổi theo phiên bản.

## 10. Các lỗi thường gặp

| Lỗi/anti-pattern | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng regex trong `subscribe(Collection<String>)` | Overload này nhận tên topic cụ thể | Dùng `subscribe(Pattern)` nếu cần regex |
| Pattern `orders.*` không khớp như mong đợi | Dấu `.` trong regex là wildcard; `*` lặp ký tự ngay trước nó | Dùng `^orders\\..+$` để khớp prefix `orders.` |
| Gọi `subscribe()` lần hai rồi mất topic cũ | Lần gọi mới thay thế tập subscription | Duy trì và gửi lại toàn bộ tập topic mong muốn |
| Topic mới chưa xuất hiện ngay trong pattern subscription | Client chưa refresh metadata hoặc topic chưa được tạo/hiển thị | Kiểm tra metadata, kết nối broker và chu kỳ refresh |
| Group rebalance liên tục sau khi topic mới được tạo | Nhiều topic mới hoặc subscription pattern quá rộng làm tập partition thay đổi | Thu hẹp naming convention và triển khai topic theo kế hoạch |
| Consumer gọi `subscribe()` nhưng không nhận record | Chưa `poll()`, topic không có dữ liệu, offset ở cuối hoặc lỗi deserializer/ACL | Kiểm tra poll loop, assignment, offset, log và quyền |
| Dùng `assign()` rồi kỳ vọng group tự chia partition | `assign()` là manual assignment | Dùng `subscribe()` nếu cần group management |
| Commit offset cao hơn record đã xử lý | Xử lý song song không theo dõi offset hoàn tất liên tục | Chỉ commit vị trí liên tục đã xử lý thành công |
| Regex match topic không mong muốn | Pattern thiếu namespace hoặc quá rộng | Neo regex, kiểm tra danh sách match và ACL |

## 11. Checklist chọn subscription

Trước khi triển khai consumer, hãy xác nhận:

- Topic list có ổn định và được biết trước không? Nếu có, ưu tiên danh sách tường minh.
- Có cần tự động nhận topic mới theo naming convention không? Nếu có, dùng pattern hẹp và được kiểm soát.
- Regex đã được test với tên topic hợp lệ và tên không được phép chưa?
- `group.id`, deserializer và offset policy đã được cấu hình chưa?
- Consumer có gọi `poll()` thường xuyên và xử lý shutdown đúng cách không?
- Có listener để lưu tiến độ khi partition bị revoke không?
- Ứng dụng có xử lý duplicate sau rebalance/crash không?
- ACL cho phép principal mô tả/đọc các topic được match và sử dụng group không?
- Đã kiểm tra hành vi khi topic mới được tạo hoặc topic bị xóa chưa?
- Đã phân biệt group-managed `subscribe()` với manual `assign()` chưa?

## 12. Câu hỏi tự kiểm tra

1. `subscribe(Collection<String>)` và `subscribe(Pattern)` khác nhau ở đầu vào nào?
2. Vì sao gọi `subscribe()` chưa có nghĩa partition được gán ngay lập tức?
3. Trong Java regex, vì sao cần viết `\\.` để khớp dấu chấm trong tên topic?
4. Pattern `^orders\\..+$` khớp những topic nào và không khớp những topic nào?
5. Consumer phát hiện topic mới khớp pattern thông qua cơ chế nào?
6. Vì sao việc topic mới khớp regex có thể kích hoạt rebalance?
7. Gọi `subscribe()` lần thứ hai có tự động thêm topic vào danh sách cũ không?
8. `onPartitionsRevoked` và `onPartitionsAssigned` nên được dùng vào việc gì?
9. `subscription()` khác `assignment()` như thế nào?
10. Vì sao không nên trộn `subscribe()` và `assign()` trên cùng consumer?
11. Nếu regex match một topic mà principal không có quyền đọc, ứng dụng có thể gặp vấn đề gì?
12. Khi nào nên chọn danh sách topic tường minh thay vì regex pattern?

## Kết luận

`subscribe(Collection<String>)` phù hợp khi ứng dụng biết rõ các topic cần đọc; `subscribe(Pattern)` phù hợp khi topic tuân theo một naming convention và consumer cần tự nhận topic mới khớp mẫu. Cả hai đều dựa vào group coordination, `poll()` và rebalance để phân phối partition. Regex cần được giới hạn chặt, listener cần xử lý revoke/assign an toàn và ứng dụng phải phân biệt subscription với assignment. Lựa chọn đúng giúp consumer mở rộng được mà vẫn kiểm soát topic, quyền truy cập và tiến độ xử lý.
