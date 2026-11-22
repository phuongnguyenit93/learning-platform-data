## Mục tiêu thực hành

Bài lab mô phỏng một hệ thống xử lý đơn hàng chạy trên hai cụm Kafka độc lập: **primary** nhận sự kiện và **backup** nhận bản sao qua MirrorMaker 2. Bạn sẽ chủ động tạo backlog, đo consumer lag, tăng số consumer trong cùng group để rút ngắn thời gian xử lý, sau đó diễn tập chuyển consumer và producer sang cụm dự phòng.

Sau bài thực hành, bạn có thể:

- Tạo tải và quan sát backlog qua **CURRENT-OFFSET**, **LOG-END-OFFSET** và **LAG**.
- Ước lượng thời gian drain backlog và xác định giới hạn song song theo số partition.
- Mở rộng consumer group bằng cách tăng số instance.
- Sao chép topic và checkpoint consumer group giữa hai cụm bằng MirrorMaker 2.
- Chuyển ứng dụng sang cụm dự phòng, kiểm tra offset đã dịch và đánh giá nguy cơ mất hoặc xử lý trùng sự kiện.

## 1. Kiến trúc và điều kiện

Chuẩn bị hai Kafka cluster độc lập, đều chạy KRaft và có thể truy cập từ máy thực hành:

| Thành phần | Primary | Backup |
|---|---|---|
| Bootstrap server | **localhost:9092** | **localhost:9094** |
| Vai trò | Nhận và xử lý sự kiện ban đầu | Nhận bản sao, sẵn sàng tiếp quản |
| Topic nguồn/đích | **orders.events** | **primary.orders.events** |
| Consumer group | **orders-lab-group** | Cùng group ID sau khi offset được đồng bộ |

Lab giả định hai cluster đã khởi động, mỗi cluster có ít nhất một broker, không bật TLS/SASL và cho phép truy cập bằng Kafka CLI. Dùng Kafka distribution có Kafka Connect và MirrorMaker 2. Ví dụ đặt replication factor bằng 1 để chạy được với broker đơn; môi trường production cần replication factor và **min.insync.replicas** phù hợp với số broker cùng yêu cầu độ bền.

Bạn cần JDK tương thích với phiên bản Kafka client; mã Java trong bài dùng các API có từ Java 11. Các lệnh dưới đây dùng tên script Linux/macOS. Trên Windows, dùng các file **.bat** tương ứng trong **bin/windows**, ví dụ **kafka-topics.bat**, **kafka-consumer-groups.bat** và **connect-mirror-maker.bat**.

## 2. Tạo topic trên primary

Tạo topic có 6 partition để có thể quan sát việc tăng consumer song song đến giới hạn của topic:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.events \
  --partitions 6 \
  --replication-factor 1
~~~

Xác nhận topic và partition:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events
~~~

Ghi lại partition count và leader. Không xóa topic đang có dữ liệu nếu chưa xác định rõ quyền sở hữu; hãy chọn tên topic lab khác trong trường hợp tên đã được sử dụng.

Chạy lab một lần trên topic và group ID mới. Khi thực hành lại, hãy tạo tên topic/group riêng rồi cập nhật đồng bộ tên trong mã Java và bộ lọc MirrorMaker 2; hoặc chỉ reset offset sau khi xác nhận đó là group lab và hiểu rõ phạm vi record sẽ được đọc lại.

## 3. Cấu hình MirrorMaker 2

Tạo file **mm2-lab.properties** trong thư mục cấu hình của Kafka:

~~~properties
clusters = primary, backup

primary.bootstrap.servers = localhost:9092
backup.bootstrap.servers = localhost:9094

primary->backup.enabled = true
primary->backup.topics = orders\\.events
primary->backup.groups = orders-lab-group

primary->backup.emit.heartbeats.enabled = true
primary->backup.emit.checkpoints.enabled = true
primary->backup.sync.group.offsets.enabled = true

replication.factor = 1
offset-syncs.topic.replication.factor = 1
heartbeats.topic.replication.factor = 1
checkpoints.topic.replication.factor = 1
~~~

Các thiết lập trên tạo luồng sao chép một chiều từ primary sang backup. Bộ lọc topic giới hạn việc sao chép vào **orders.events**; bộ lọc group giới hạn checkpoint và đồng bộ offset cho **orders-lab-group**. Với replication policy mặc định, topic đích có tiền tố alias cluster nguồn: **primary.orders.events**.

Khởi chạy MirrorMaker 2 trong một terminal riêng và giữ tiến trình hoạt động:

~~~bash
bin/connect-mirror-maker.sh config/mm2-lab.properties
~~~

Trên Windows, chạy **bin\windows\connect-mirror-maker.bat config\mm2-lab.properties**. Chạy lệnh từ thư mục gốc của Kafka distribution.

Kiểm tra topic trên backup:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9094 \
  --list

bin/kafka-topics.sh \
  --bootstrap-server localhost:9094 \
  --describe \
  --topic primary.orders.events
~~~

Chờ MirrorMaker 2 tạo topic đích và đủ 6 partition trước khi tiếp tục. Nếu topic chưa xuất hiện, xem trạng thái connector/task và log của tiến trình MirrorMaker 2; kiểm tra bootstrap server, quyền tạo/ghi topic, bộ lọc topic và replication factor.

MirrorMaker 2 sao chép bất đồng bộ. Record vừa được ghi ở primary có thể chưa xuất hiện ở backup ngay lập tức. Checkpoint consumer group cũng được phát và đồng bộ theo chu kỳ; không coi việc topic đích đã tồn tại là bằng chứng offset đã sẵn sàng cho failover.

## 4. Tạo tải để hình thành backlog

Tạo class **BacklogProducer** trong một project Java có Kafka client:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class BacklogProducer {

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Use: bootstrapServers topic runId recordCount");
        }

        String bootstrapServers = args[0];
        String topic = args[1];
        String runId = args[2];
        int recordCount = Integer.parseInt(args[3]);

        Properties properties = new Properties();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        properties.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        properties.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        try (KafkaProducer<String, String> producer =
                     new KafkaProducer<>(properties)) {

            for (int i = 0; i < recordCount; i++) {
                String key = "customer-" + (i % 100);
                String value = "eventId=" + runId + "-" + i
                        + ";sequence=" + i;

                producer.send(new ProducerRecord<>(topic, key, value)).get();
            }

            producer.flush();
        }

        System.out.printf(
                "Sent %d records to %s on %s%n",
                recordCount,
                topic,
                bootstrapServers);
    }
}
~~~

Chạy producer trên primary để gửi 10.000 record:

~~~text
BacklogProducer localhost:9092 orders.events primary 10000
~~~

Key **customer-0** đến **customer-99** giúp các event của cùng customer được định tuyến cùng partition khi dùng default partitioner. **eventId** duy nhất giúp nhận diện record trong quá trình đối chiếu và phát lại. Producer chờ xác nhận từng lần gửi nên tốc độ tạo tải vừa phải; có thể tăng **recordCount** nếu backlog hình thành chưa rõ.

## 5. Chạy consumer chậm để tạo backlog

Tạo class **SlowOrderConsumer**. Consumer xử lý mỗi record với độ trễ giả lập, tắt auto commit và commit offset sau mỗi batch đã xử lý:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.errors.WakeupException;
import org.apache.kafka.common.serialization.StringDeserializer;

public class SlowOrderConsumer {

    public static void main(String[] args) throws Exception {
        if (args.length != 6) {
            throw new IllegalArgumentException(
                    "Use: bootstrapServers topic groupId clientId delayMs offsetReset");
        }

        String bootstrapServers = args[0];
        String topic = args[1];
        String groupId = args[2];
        String clientId = args[3];
        long delayMs = Long.parseLong(args[4]);
        String offsetReset = args[5];

        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        properties.put(ConsumerConfig.CLIENT_ID_CONFIG, clientId);
        properties.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, offsetReset);
        properties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 10);

        KafkaConsumer<String, String> consumer = new KafkaConsumer<>(properties);
        AtomicBoolean stopping = new AtomicBoolean(false);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            stopping.set(true);
            consumer.wakeup();
        }));

        long processed = 0;
        consumer.subscribe(List.of(topic));

        try {
            while (!stopping.get()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                for (ConsumerRecord<String, String> record : records) {
                    // Thay bằng xử lý nghiệp vụ thực tế trong ứng dụng.
                    if (delayMs > 0) {
                        Thread.sleep(delayMs);
                    }
                    processed++;
                }

                if (!records.isEmpty()) {
                    consumer.commitSync();
                    System.out.printf(
                            "client=%s batch=%d processed=%d%n",
                            clientId,
                            records.count(),
                            processed);
                }
            }
        } catch (WakeupException exception) {
            if (!stopping.get()) {
                throw exception;
            }
        } finally {
            consumer.close();
        }
    }
}
~~~

Chạy một consumer trên primary với cùng group ID sẽ dùng xuyên suốt bài lab:

~~~text
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-1 100 earliest
~~~

Để tiến trình chạy trong terminal riêng. Tham số **100** tạo độ trễ 100 ms cho mỗi record; **earliest** cho phép group mới đọc từ đầu topic. Vì producer đã ghi 10.000 record trước khi consumer khởi động, group mới sẽ có backlog để xử lý. Muốn quan sát backlog tiếp tục tăng, hãy chạy thêm một producer với **runId** khác trong terminal riêng khi consumer đang hoạt động.

Mở terminal khác và xem lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-lab-group
~~~

Đọc các cột:

- **CURRENT-OFFSET**: offset đã commit của consumer group trên partition.
- **LOG-END-OFFSET**: vị trí cuối hiện có của partition.
- **LAG**: số record ước tính còn phải xử lý theo chênh lệch offset.

Ghi lại lag của cả 6 partition. Chạy lệnh nhiều lần để quan sát lag giảm khi consumer xử lý backlog. Nếu chạy thêm producer trong lúc consumer đang hoạt động, lag sẽ tăng khi tốc độ đầu vào lớn hơn throughput xử lý và giảm khi consumer xử lý nhanh hơn tốc độ ghi.

## 6. Mở rộng consumer group và đo thời gian drain

Giữ consumer **primary-1** đang chạy, sau đó mở hai terminal và chạy hai instance cùng group ID, mỗi instance có **clientId** riêng:

~~~text
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-2 100 earliest
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-3 100 earliest
~~~

Đợi rebalance hoàn tất rồi chạy lại lệnh **kafka-consumer-groups --describe**. Quan sát cách 6 partition được chia cho 3 consumer. Tiếp tục thêm instance thứ tư, thứ năm và thứ sáu:

~~~text
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-4 100 earliest
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-5 100 earliest
SlowOrderConsumer localhost:9092 orders.events orders-lab-group primary-6 100 earliest
~~~

Mỗi consumer trong cùng group nhận các partition khác nhau tại một thời điểm. Với 6 partition, tối đa 6 consumer có thể được gán partition của topic này. Thêm consumer thứ bảy không tạo thêm khả năng đọc song song cho topic; instance dư sẽ không được gán partition.

Đo theo từng giai đoạn: ghi lag lúc chỉ có consumer thứ nhất; ghi lại khi hai consumer mới đã tham gia và rebalance hoàn tất; cuối cùng ghi lại khi đủ sáu consumer. Ghi lag ở đầu giai đoạn và sau 30 giây, rồi theo dõi thời gian backlog giảm về gần 0. Có thể dùng bảng:

| Số consumer | Tổng lag lúc bắt đầu đo | Lag sau 30 giây | Thời gian drain ước tính |
|---:|---:|---:|---:|
| 1 | ghi kết quả | ghi kết quả | ghi kết quả |
| 3 | ghi kết quả | ghi kết quả | ghi kết quả |
| 6 | ghi kết quả | ghi kết quả | ghi kết quả |

Ước lượng thời gian drain bằng:

~~~text
thời gian drain ≈ backlog / (throughput xử lý - throughput đầu vào)
~~~

Công thức chỉ có ý nghĩa khi throughput xử lý lớn hơn throughput đầu vào. Nếu consumer xử lý không nhanh hơn tốc độ producer tiếp tục ghi, backlog sẽ không giảm. Thông lượng thực tế còn phụ thuộc kích thước record, xử lý nghiệp vụ, I/O, batch, rebalance, broker và dependency bên ngoài; không giả định tăng gấp đôi consumer sẽ luôn tăng gấp đôi throughput.

Sau khi hoàn tất đo đạc, dừng các instance bằng Ctrl+C và đợi group ổn định. Consumer commit offset theo batch, nên dừng sau khi đã quan sát batch commit gần nhất.

## 7. Xác nhận dữ liệu và checkpoint đã sang backup

Kiểm tra topic được MirrorMaker 2 tạo trên backup:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9094 \
  --describe \
  --topic primary.orders.events
~~~

Topic đích phải có đủ 6 partition. Dùng console consumer để kiểm tra một số record đã được sao chép:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9094 \
  --topic primary.orders.events \
  --from-beginning \
  --max-messages 10 \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Đợi MirrorMaker 2 phát checkpoint sau khi consumer group trên primary đã commit offset và không còn consumer hoạt động. Kiểm tra group trên backup:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9094 \
  --describe \
  --group orders-lab-group
~~~

Nếu group chưa có committed offset hoặc chưa có dữ liệu checkpoint, chưa chuyển consumer sang backup. Kiểm tra log và trạng thái MirrorMaker 2, bộ lọc group, checkpoint topic, quyền truy cập và thời điểm commit cuối trên primary. Offset giữa hai cluster có thể khác nhau; không sao chép nguyên số offset từ primary sang backup bằng thao tác thủ công. MirrorMaker 2 dùng offset-sync/checkpoint để ánh xạ vị trí đọc sang topic đích.

## 8. Diễn tập failover sang backup

Trước khi chuyển cụm, thống nhất thời điểm dừng ghi và dừng consumer trên primary. Trong một hệ thống thật, cần fence primary để tránh hai cụm cùng nhận ghi hoặc cùng xử lý một luồng nghiệp vụ. Lab này chỉ mô phỏng failover trên hai cluster thử nghiệm; không dừng broker hay thay đổi route của môi trường dùng chung.

Thực hiện theo thứ tự:

1. Dừng producer ghi vào primary.
2. Dừng tất cả consumer **orders-lab-group** trên primary và xác nhận group không còn member hoạt động.
3. Đợi MirrorMaker 2 phát checkpoint mới nhất; kiểm tra group **orders-lab-group** trên backup đã có committed offset.
4. Dừng tiến trình MirrorMaker 2 để kết thúc chiều sao chép primary sang backup trước khi backup nhận ghi mới.
5. Khởi động consumer trên backup bằng cùng group ID, topic đích và **auto.offset.reset=none**:

~~~text
SlowOrderConsumer localhost:9094 primary.orders.events orders-lab-group backup-1 0 none
~~~

Giá trị **none** khiến consumer báo lỗi nếu partition không có offset đã commit. Đây là dấu hiệu cần dừng và điều tra offset translation/checkpoint, thay vì âm thầm đọc từ đầu. Nếu offset đã được đồng bộ, kiểm tra consumer bắt đầu gần vị trí đã xử lý trên primary và tiếp tục đọc phần còn lại.

Gửi một lô sự kiện mới trực tiếp vào topic trên backup:

~~~text
BacklogProducer localhost:9094 primary.orders.events backup 1000
~~~

Xác nhận consumer backup xử lý các event có ID bắt đầu bằng **backup-**. Từ thời điểm này, backup là cụm đang nhận ghi trong kịch bản lab.

Offset sync và replication của MirrorMaker 2 là bất đồng bộ. Có thể tồn tại một khoảng dữ liệu cuối chưa được sao chép hoặc checkpoint chưa kịp cập nhật tại thời điểm primary gặp sự cố. Đây là phần RPO cần đo và chấp nhận trong thiết kế DR. Khi offset không sẵn sàng, cần một quy trình replay có kiểm soát dựa trên checkpoint và event ID; không tự đặt offset đích bằng con số offset nguồn.

## 9. Kiểm soát duplicate và failback

Failover có thể khiến một số event được xử lý lại, đặc biệt khi record đã được xử lý ở primary nhưng offset cuối chưa được đồng bộ sang backup. Consumer nghiệp vụ nên idempotent. Một cách phổ biến là lưu **eventId** cùng kết quả xử lý trong database có unique constraint, để lần nhận lại cùng event ID không tạo tác dụng phụ lần thứ hai.

Trong lab, đối chiếu **eventId** của các record cuối cùng đã xử lý ở primary với record đầu tiên consumer đọc ở backup. Ghi nhận:

- Event cuối đã commit trên primary.
- Checkpoint/offset group được nhìn thấy trên backup.
- Event đầu tiên được xử lý sau failover.
- Có event bị xử lý lặp hoặc khoảng event chưa được nhận hay không.

Không bật đồng thời luồng MirrorMaker 2 ngược từ backup về primary ngay sau khi failover. Failback cần kế hoạch riêng: xác định cụm có thẩm quyền ghi, chặn ghi ở cụm cũ, chọn hướng đồng bộ một chiều, xử lý topic remote và offset translation, đối chiếu event ID rồi mới chuyển producer/consumer. Nếu bật hai chiều thiếu kiểm soát, dữ liệu có thể bị lặp hoặc tạo vòng sao chép.

## 10. Kết quả và tiêu chí hoàn thành

Ghi lại kết quả thực nghiệm:

| Chỉ số | Kết quả cần ghi |
|---|---|
| Số partition của topic nguồn | 6 |
| Tổng record đã tạo | 10.000 hoặc số đã chọn |
| Lag lớn nhất quan sát được | Số đo từ consumer group |
| Consumer để đo | 1, 3 và 6 |
| Thời gian drain ở mỗi mức | Thời gian đo thực tế |
| Topic mirror trên backup | **primary.orders.events**, 6 partition |
| Group offset trên backup | Có/không và vị trí đã kiểm tra |
| Event cuối ở primary và event đầu ở backup | Event ID thực tế |
| Sự kiện trùng hoặc thiếu quan sát được | Kết quả đối chiếu |

Bài lab đạt yêu cầu khi bạn tạo được backlog có số đo, chứng minh lag thay đổi khi scale consumer, xác nhận topic và checkpoint được sao chép, chuyển được consumer sang backup bằng offset đã dịch và giải thích được giới hạn RPO cùng nguy cơ duplicate.

## 11. Câu hỏi phân tích vận hành

1. Khi nào backlog được xem là sự cố? Bạn sẽ đặt ngưỡng theo tổng lag, tuổi record cũ nhất hay thời gian drain dự kiến?
2. Vì sao tăng consumer vượt số partition không làm tăng throughput của một topic?
3. Nếu tốc độ đầu vào liên tục cao hơn throughput xử lý, cần thay đổi consumer, partition, batch, xử lý nghiệp vụ hay năng lực broker?
4. Vì sao offset số học của primary không thể dùng nguyên trạng trên topic mirror ở backup?
5. RPO và RTO của hệ thống bị ảnh hưởng bởi replication lag, checkpoint interval, thời gian phát hiện sự cố và thời gian chuyển route như thế nào?
6. Cần lưu event ID và thiết kế idempotency ra sao để chịu được replay sau failover?
7. Quy trình failback cần điều kiện gì để tránh split-brain và vòng lặp replication?

## 12. Bài học triển khai production

Backlog cần được giám sát bằng cả lag, tuổi record và tốc độ tăng/giảm; chỉ nhìn một con số lag có thể che khuất partition bị nghẽn riêng lẻ. Số consumer hữu ích bị giới hạn bởi partition count và năng lực xử lý của từng instance. Hãy scale dựa trên throughput đo được và thời gian drain mà nghiệp vụ chấp nhận.

MirrorMaker 2 cung cấp sao chép liên cluster và checkpoint offset, nhưng không biến hai cluster thành một cụm đồng bộ tức thời. Cần theo dõi replication lag, checkpoint freshness, trạng thái connector/task và dung lượng backup. Thiết kế DR phải xác định rõ RPO, RTO, quyền ghi tại mỗi thời điểm, quy trình fence primary, cách dịch offset, xử lý duplicate và thủ tục failback.
