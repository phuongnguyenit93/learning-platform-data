# Thử broker lỗi với các cấu hình acks và min.insync.replicas

Trong Kafka, producer có thể nhận xác nhận sau khi leader ghi record, hoặc chờ toàn bộ replica đang nằm trong ISR xác nhận. Mức xác nhận được điều khiển bởi `acks`; số replica tối thiểu cần có khi producer yêu cầu xác nhận đầy đủ được điều khiển bởi `min.insync.replicas`. Kết hợp hai cấu hình này quyết định luồng ghi ưu tiên độ sẵn sàng hay độ bền dữ liệu khi broker gặp sự cố.

Bài thực hành này dựng một topic có ba replica, gửi dữ liệu khi cụm khỏe mạnh, dừng một broker follower, quan sát ISR thay đổi và thử lại với `acks=all` cùng `acks=1`. Sau đó, thay đổi ngưỡng `min.insync.replicas` để thấy vì sao cấu hình `replication.factor=3` và `min.insync.replicas=2` thường cho phép tiếp tục ghi khi mất một replica.

## 1. Mục tiêu và kết quả cần đạt

Sau bài thực hành, người học có thể:

- Tạo topic có replication factor bằng 3 và quan sát leader, replicas, ISR.
- Giải thích `acks=0`, `acks=1` và `acks=all` theo góc nhìn producer.
- Chứng minh `min.insync.replicas` được áp dụng cho write request dùng `acks=all`.
- Mô phỏng một broker follower dừng hoạt động và theo dõi ISR giảm từ ba xuống hai.
- So sánh kết quả ghi khi `min.insync.replicas=3` và khi giá trị này bằng 2.
- Khôi phục broker, xác nhận replica quay lại ISR và kiểm tra dữ liệu đã ghi.

Kết quả mong đợi trong kịch bản chính:

| Trạng thái cụm | `min.insync.replicas` | Producer `acks=all` | Producer `acks=1` |
| --- | ---: | --- | --- |
| Ba replica đều trong ISR | 3 | Thành công | Thành công |
| Một follower dừng, ISR còn 2 | 3 | Bị từ chối vì ISR thấp hơn ngưỡng | Có thể thành công vì leader đã ghi nhận |
| Một follower dừng, ISR còn 2 | 2 | Thành công sau khi hai replica trong ISR xác nhận | Thành công |

Đây là lab trong môi trường thử nghiệm. Không dừng broker hoặc thay đổi ngưỡng ISR trên cụm production để tái hiện bài học.

## 2. Hiểu các cấu hình trước khi thực hành

### 2.1. `acks` của producer

| Giá trị | Điều producer chờ | Rủi ro và cách dùng |
| --- | --- | --- |
| `0` | Không chờ broker xác nhận. Producer không có xác nhận đáng tin cậy rằng broker đã ghi record. | Độ trễ thấp nhưng có thể mất dữ liệu mà producer không biết; không phù hợp khi cần bảo đảm giao nhận. |
| `1` | Chờ leader ghi record vào log cục bộ rồi xác nhận. | Nếu leader hỏng trước khi follower sao chép record, record có thể mất khi leader mới được bầu. |
| `all` hoặc `-1` | Chờ các replica hiện nằm trong ISR xác nhận record. | Tăng độ bền dữ liệu; write có thể thất bại nếu ISR thấp hơn `min.insync.replicas`. |

`acks=all` không có nghĩa là chờ mọi replica được khai báo trong replication factor bất kể trạng thái. Nó chờ các replica đang thuộc ISR. Replica đã rời ISR không tham gia điều kiện xác nhận tại thời điểm đó.

### 2.2. `min.insync.replicas`

`min.insync.replicas` đặt số replica tối thiểu phải có trong ISR để broker chấp nhận một write dùng `acks=all`. Nếu ISR thấp hơn ngưỡng, broker từ chối write. Cấu hình này không buộc producer dùng `acks=all`; với `acks=1`, leader có thể xác nhận dù ISR thấp hơn ngưỡng.

Ví dụ phổ biến là replication factor 3 và `min.insync.replicas=2`. Khi một replica dừng, hai replica còn lại vẫn có thể tạo thành ISR đủ ngưỡng để tiếp tục ghi với `acks=all`. Nếu cả hai replica còn lại không đáp ứng được ngưỡng, write sẽ bị từ chối để bảo vệ mức độ bền dữ liệu đã chọn.

### 2.3. Idempotence và retries

Producer bật idempotence cần `acks=all`, retries lớn hơn 0 và `max.in.flight.requests.per.connection` không vượt quá giới hạn mà Kafka hỗ trợ cho idempotence (tối đa 5). Kafka client hiện đại tự thiết lập các giá trị tương thích khi idempotence được bật nếu ứng dụng không ghi đè xung đột.

Trong phần so sánh `acks=1`, ví dụ sẽ tắt idempotence vì cấu hình này không tương thích với idempotence. Đây là producer thí nghiệm để quan sát khác biệt về acknowledgement, không phải cấu hình khuyến nghị cho luồng dữ liệu quan trọng.

## 3. Chuẩn bị môi trường

### 3.1. Yêu cầu

- Một Kafka cluster thử nghiệm có ít nhất ba broker.
- Topic thử nghiệm có thể tạo với replication factor 3.
- Quyền tạo topic, xem cấu hình topic và đọc thông tin partition.
- Quyền dừng và khởi động một broker trong môi trường lab.
- Kafka CLI tương thích với phiên bản cluster, Java và Kafka client.

Nếu cluster dùng KRaft với ba node vừa làm broker vừa làm controller, chỉ dừng một node trong bài này. Hai controller còn lại vẫn giữ đa số quorum 2/3. Không dừng hai node cùng lúc trong bài lab này vì quorum controller có thể mất đa số, khiến việc quan sát replication và khôi phục phức tạp hơn.

Một Kafka container đơn lẻ hoặc Testcontainers `KafkaContainer` mặc định không đủ để thực hành replication factor 3. Hãy dùng cluster ba broker hoặc môi trường lab được cấp sẵn. Trong các lệnh bên dưới, thay `localhost:9092` bằng bootstrap server của cluster và thay tên service/container theo môi trường thực tế.

Đặt các biến dùng trong ví dụ:

```bash
export BOOTSTRAP_SERVERS=localhost:9092
export TOPIC=acks-min-isr-lab
```

Trên PowerShell có thể dùng:

```powershell
$env:BOOTSTRAP_SERVERS = "localhost:9092"
$env:TOPIC = "acks-min-isr-lab"
```

Các lệnh CLI phía dưới dùng trực tiếp địa chỉ `localhost:9092` và tên topic `acks-min-isr-lab` để dễ sao chép. Nếu cluster yêu cầu TLS hoặc SASL, bổ sung `--command-config` trỏ tới file cấu hình client phù hợp cho các lệnh quản trị và đọc dữ liệu.

### 3.2. Kiểm tra cluster có đủ broker

```bash
kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

Lệnh hiển thị broker có thể truy cập. Xác nhận có ba broker ID khác nhau và cả ba đều hoạt động trước khi tạo topic. Nếu dùng KRaft, có thể xem trạng thái quorum metadata:

```bash
kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
```

Ghi lại broker ID, địa chỉ và tên service/container tương ứng. Không suy luận broker ID từ thứ tự container.

## 4. Tạo topic ba replica

Tạo topic có một partition và ba replica. Đặt `min.insync.replicas=3` để có thể quan sát rõ tác động khi một replica rời ISR:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --create \
  --topic acks-min-isr-lab \
  --partitions 1 \
  --replication-factor 3 \
  --config min.insync.replicas=3
```

Kiểm tra phân bố replica:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe \
  --topic acks-min-isr-lab
```

Ví dụ kết quả khi cụm khỏe mạnh:

```text
Topic: acks-min-isr-lab  Partition: 0  Leader: 1
Replicas: 1,2,3  Isr: 1,2,3
```

Kết quả thực tế có thể dùng broker ID khác. Ghi lại broker leader và hai follower. Trong bài lab, chỉ dừng một follower để leader vẫn hoạt động và controller quorum vẫn giữ đa số.

Nếu topic đã tồn tại, lệnh `--create` sẽ báo lỗi. Hãy dùng topic mới hoặc kiểm tra topic cũ trước khi tiếp tục; không xóa topic có dữ liệu cần giữ.

## 5. Tạo producer Java để thử `acks`

Đoạn code sau dùng Kafka Java client để gửi một record và chờ kết quả. Với `acks=all`, bật idempotence; với `acks=1`, tắt idempotence để cấu hình hợp lệ.

```java
import java.util.Properties;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.serialization.StringSerializer;

public final class AcksLabProducer {
    private static final String TOPIC = "acks-min-isr-lab";
    private static final String BOOTSTRAP = "localhost:9092";

    public static void send(String acks, String messageId) throws Exception {
        boolean idempotence = "all".equals(acks);

        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, BOOTSTRAP);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, acks);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            Boolean.toString(idempotence));
        props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 3_000);
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 15_000);

        if (idempotence) {
            props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
            props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        } else {
            props.put(ProducerConfig.RETRIES_CONFIG, 0);
        }

        try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
            ProducerRecord<String, String> record = new ProducerRecord<>(
                TOPIC,
                messageId,
                "event-" + messageId
            );

            try {
                RecordMetadata metadata = producer.send(record)
                    .get(20, TimeUnit.SECONDS);
                System.out.printf(
                    "ACK OK: topic=%s partition=%d offset=%d acks=%s%n",
                    metadata.topic(), metadata.partition(), metadata.offset(), acks
                );
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause() == null ? ex : ex.getCause();
                System.err.printf(
                    "ACK FAILED: acks=%s cause=%s message=%s%n",
                    acks,
                    cause.getClass().getSimpleName(),
                    cause.getMessage()
                );
                throw ex;
            }
        }
    }
}
```

`delivery.timeout.ms` giới hạn tổng thời gian client cố gắng gửi record, gồm thời gian chờ acknowledgement và retry. Khi broker không đáp ứng `min.insync.replicas`, lỗi cuối cùng có thể được bọc hoặc kết thúc dưới dạng timeout sau các lần retry. Hãy đọc cause chain và log broker; tên exception quan sát được có thể phụ thuộc thời điểm ISR thay đổi và phiên bản Kafka.

Chạy `AcksLabProducer.send("all", "baseline-001")` khi cả ba replica nằm trong ISR. Sau đó chạy `AcksLabProducer.send("1", "baseline-002")`. Cả hai lần gửi đều phải thành công trong trạng thái khỏe mạnh. Ghi lại partition và offset trả về.

Với Spring Boot, cấu hình producer tương đương cho luồng thông thường có thể khai báo:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
```

`min.insync.replicas` là cấu hình của broker/topic, không phải producer property. Đặt nó bằng Kafka CLI, AdminClient hoặc quy trình quản trị topic.

## 6. Thí nghiệm A — Dừng một follower khi min ISR bằng 3

### Bước 1: Xác định follower cần dừng

Chạy lại lệnh describe:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic acks-min-isr-lab
```

Từ danh sách `Replicas`, xác định broker đang là follower (broker có ID khác `Leader`). Ghi lại tên container/service của follower đó. Không dừng leader trong thí nghiệm đầu tiên.

### Bước 2: Dừng đúng một follower

Ví dụ với Docker Compose, nếu follower là service `broker-2`:

```bash
docker compose stop broker-2
```

Nếu môi trường dùng container name trực tiếp:

```bash
docker stop kafka-broker-2
```

Thay tên bằng follower thực tế đã xác định ở bước trước. Không chạy cả hai lệnh nếu chúng trỏ tới hai broker khác nhau.

### Bước 3: Chờ ISR giảm còn hai

Chạy lệnh sau nhiều lần cho đến khi follower rời ISR:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic acks-min-isr-lab
```

Ví dụ:

```text
Topic: acks-min-isr-lab  Partition: 0  Leader: 1
Replicas: 1,2,3  Isr: 1,3
```

Leader vẫn hoạt động, nhưng ISR hiện chỉ có hai replica trong khi `min.insync.replicas=3`. Đợi đến khi trạng thái ISR phản ánh broker đã dừng; không dùng thời gian chờ cố định để giả định broker đã rời ISR.

### Bước 4: Gửi với `acks=all`

Chạy:

```java
AcksLabProducer.send("all", "min-isr-3-all-001");
```

Kết quả mong đợi là write thất bại vì số replica trong ISR nhỏ hơn 3. Broker có thể trả `NOT_ENOUGH_REPLICAS`; nếu producer retry đến hết `delivery.timeout.ms`, ứng dụng có thể nhìn thấy timeout cùng cause liên quan. Ghi lại exception, thời gian gửi và log broker.

Điểm cần xác nhận: producer không nhận acknowledgement thành công. Không đánh đồng lần gửi thất bại với việc chắc chắn không có record nào được ghi trong mọi tình huống lỗi; khi xử lý lỗi sau timeout, ứng dụng cần thiết kế idempotency hoặc kiểm tra trạng thái bằng event ID trước khi gửi lại.

### Bước 5: Gửi với `acks=1`

Chạy:

```java
AcksLabProducer.send("1", "min-isr-3-leader-ack-001");
```

Kết quả mong đợi là leader có thể xác nhận write dù ISR thấp hơn `min.insync.replicas=3`. Đây là khác biệt cốt lõi: `min.insync.replicas` bảo vệ write dùng `acks=all`; nó không buộc `acks=1` chờ follower.

Record được xác nhận bằng `acks=1` có nguy cơ mất nếu leader hỏng trước khi record được follower sao chép. Bài lab chỉ quan sát acknowledgement khi leader còn sống; không cần cố tình gây thêm sự cố để làm mất dữ liệu.

## 7. Thí nghiệm B — Min ISR bằng 2 cho phép ghi khi mất một replica

Khôi phục follower trước khi thay đổi cấu hình:

Trong các lệnh dưới đây, thay `broker-2` hoặc `kafka-broker-2` bằng đúng service/container follower bạn đã dừng ở thí nghiệm A.

```bash
docker compose start broker-2
```

Hoặc dùng container name:

```bash
docker start kafka-broker-2
```

Chờ đến khi `Isr` có đủ ba broker trở lại. Sau đó đổi cấu hình topic thành 2:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name acks-min-isr-lab \
  --alter \
  --add-config min.insync.replicas=2
```

Xác minh cấu hình:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name acks-min-isr-lab \
  --describe
```

Dừng lại cùng follower như thí nghiệm A, đợi ISR giảm còn hai rồi gửi:

```java
AcksLabProducer.send("all", "min-isr-2-all-001");
```

Lần này write phải thành công sau khi hai replica trong ISR xác nhận. Đây là mô hình phổ biến với replication factor 3 và `min.insync.replicas=2`: cụm có thể tiếp tục ghi khi một replica mất, đồng thời yêu cầu leader và ít nhất một follower cùng xác nhận.

Khôi phục follower và chờ ISR trở lại ba trước khi kết thúc bài thực hành.

## 8. Đọc lại dữ liệu và đối chiếu kết quả

Đọc các record đã gửi:

```bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic acks-min-isr-lab \
  --from-beginning \
  --property print.key=true \
  --property key.separator=:
```

Consumer chạy liên tục; nhấn `Ctrl+C` sau khi đã quan sát các record cần đối chiếu.

Đối chiếu các key `baseline-001`, `baseline-002`, `min-isr-3-leader-ack-001` và `min-isr-2-all-001`. Key của lần `acks=all` bị từ chối trong thí nghiệm A thường không xuất hiện, nhưng luôn xác minh dữ liệu thực tế trước khi kết luận vì lỗi timeout có thể xảy ra sau khi broker đã append mà client chưa nhận được acknowledgement.

Ghi kết quả vào bảng:

| Lần thử | ISR | Min ISR | Acks | Kết quả | Offset nếu thành công |
| --- | ---: | ---: | --- | --- | --- |
| Baseline | 3 | 3 | all |  |  |
| Baseline | 3 | 3 | 1 |  |  |
| Một follower dừng | 2 | 3 | all |  |  |
| Một follower dừng | 2 | 3 | 1 |  |  |
| Một follower dừng | 2 | 2 | all |  |  |

## 9. Quan sát broker và producer trong lúc lỗi

Khi follower dừng, quan sát:

- `Isr` của partition và leader hiện tại bằng `kafka-topics.sh --describe`.
- Số partition offline và under-replicated partitions.
- ISR shrink/expand rate và replica lag trên broker.
- Producer request latency, retry rate, error rate và delivery timeout.
- Log broker tại thời điểm nhận Produce request, đặc biệt lỗi thiếu replica trong ISR.

Một số metric broker hữu ích gồm `UnderReplicatedPartitions`, `OfflinePartitionsCount`, `IsrShrinksPerSec` và `IsrExpandsPerSec`. Tên metric và cách export phụ thuộc phiên bản, JMX reporter và hệ thống giám sát. Đọc metric cùng log và trạng thái partition; một con số đơn lẻ không đủ xác định nguyên nhân.

Nếu ISR không trở lại sau khi broker khởi động, kiểm tra log broker, kết nối giữa broker, thư mục log, trạng thái replica và khả năng bắt kịp leader. Không hạ `min.insync.replicas` hoặc bật unclean leader election chỉ để làm mất cảnh báo. Trước tiên xác định tại sao replica không thể đồng bộ.

## 10. Dọn dẹp và khôi phục trạng thái lab

1. Bảo đảm mọi broker đã được khởi động.
2. Chờ topic có đủ ba replica trong ISR.
3. Đặt lại `min.insync.replicas=2` nếu muốn giữ topic cho bài thực hành tiếp theo, hoặc xóa topic lab sau khi xác nhận dữ liệu không cần giữ.
4. Kiểm tra không còn container bị dừng ngoài dự kiến.

Đặt lại topic config về 2:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name acks-min-isr-lab \
  --alter \
  --add-config min.insync.replicas=2
```

Nếu cần xóa topic thử nghiệm:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --delete --topic acks-min-isr-lab
```

Chỉ xóa topic do chính bài lab tạo. Không chạy lệnh xóa nếu topic được dùng chung hoặc có dữ liệu khác.

## 11. Phân tích các tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Topic không tạo được với replication factor 3 | Cluster có ít hơn ba broker hoặc broker chưa sẵn sàng | Kiểm tra broker API versions và metadata cluster. |
| ISR không giảm ngay khi dừng broker | Broker chưa vượt ngưỡng thời gian phát hiện replica lag hoặc đang có vấn đề kết nối khác | Theo dõi describe và log đến khi trạng thái ổn định. |
| `acks=all` vẫn thành công khi một follower dừng | Min ISR đang bằng 2 hoặc thấp hơn; ISR còn lại vẫn đáp ứng ngưỡng | Đọc cấu hình topic hiệu lực và số broker trong ISR. |
| `acks=all` thất bại dù đủ số replica dự kiến | Replica chưa thực sự ở ISR, topic override khác dự kiến hoặc lỗi broker khác | Kiểm tra `Isr`, leader, topic config và log broker. |
| `acks=1` thất bại | Leader không sẵn sàng, metadata/network lỗi hoặc request bị từ chối vì nguyên nhân khác | Kiểm tra leader election, kết nối và exception gốc. |
| Producer nhận timeout thay vì `NotEnoughReplicasException` | Client đã retry lỗi retriable đến hết delivery timeout | Đọc cause chain, log broker và cấu hình delivery timeout. |
| Producer idempotent không khởi động với `acks=1` | Idempotence yêu cầu `acks=all` | Bật lại `acks=all` hoặc tắt idempotence cho producer thí nghiệm. |
| Broker đã khởi động nhưng ISR không phục hồi | Replica không bắt kịp, log directory lỗi hoặc kết nối giữa broker có vấn đề | Kiểm tra log broker, replica lag, disk và network. |

## 12. Bài tập mở rộng

**Bài 1 — Thử `min.insync.replicas=2`:** Giữ replication factor 3, dừng một follower và chứng minh `acks=all` vẫn thành công khi ISR còn hai. Giải thích vì sao kết quả khác với cấu hình min ISR bằng 3.

**Bài 2 — Mô phỏng leader failure:** Khôi phục đủ ba broker, xác định leader, sau đó dừng leader trong môi trường lab. Quan sát bầu leader mới, thời gian producer retry và kết quả gửi với `acks=all`. Không dừng thêm broker khi cluster dùng ba controller kết hợp.

**Bài 3 — So sánh `acks=0`:** Gửi một số record với `acks=0`, ghi nhận producer không có metadata acknowledgement đáng tin cậy. Giải thích vì sao không thể dùng kết quả lời gọi send như bằng chứng broker đã ghi dữ liệu.

**Bài 4 — Kiểm tra idempotence:** Gửi nhiều lần với `acks=all`, idempotence bật và retry trong lúc follower khởi động lại. Đối chiếu event ID trong topic để kiểm tra duplicate ở tầng ứng dụng; phân biệt producer idempotence với idempotency của nghiệp vụ downstream.

**Bài 5 — Thiết kế cấu hình production:** Đề xuất replication factor, min ISR, acks, retry, delivery timeout và cảnh báo metric cho một topic đơn hàng. Giải thích số replica tối thiểu còn lại khi một broker hoặc một vùng lỗi gặp sự cố.

## 13. Checklist hoàn thành

- [ ] Cluster có ba broker và topic có replication factor 3.
- [ ] Đã xác nhận trạng thái ban đầu có ba replica trong ISR.
- [ ] Producer baseline với `acks=all` và `acks=1` đều gửi thành công.
- [ ] Đã dừng đúng một follower và quan sát ISR giảm còn hai.
- [ ] Với min ISR bằng 3, đã quan sát `acks=all` thất bại và `acks=1` có thể thành công.
- [ ] Đã khôi phục follower, đặt min ISR bằng 2 và quan sát `acks=all` thành công khi ISR còn hai.
- [ ] Đã khởi động lại broker và xác nhận ISR trở lại ba.
- [ ] Đã đọc lại dữ liệu, đối chiếu key/offset và ghi lại exception.
- [ ] Đã giải thích được rủi ro độ bền của `acks=1` và vai trò của idempotence.

## 14. Tiêu chí hoàn thành

Người học hoàn thành bài khi có thể tự tạo topic ba replica, mô phỏng một follower dừng, quan sát ISR và dự đoán chính xác kết quả ghi theo từng cặp `acks`/`min.insync.replicas`. Người học cũng cần khôi phục broker, xác nhận dữ liệu và giải thích được cách chọn replication factor, min ISR và acknowledgement để cân bằng khả năng ghi liên tục với độ bền dữ liệu.
