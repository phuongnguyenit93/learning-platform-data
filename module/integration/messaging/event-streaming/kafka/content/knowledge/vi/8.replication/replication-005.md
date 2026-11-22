# Vì sao acks=all không có nghĩa chờ mọi replica đã cấu hình

Khi producer ghi record vào Apache Kafka, thuộc tính **acks** quyết định mức xác nhận mà producer yêu cầu từ broker. Giá trị **acks=all** (tương đương **acks=-1**) thường được chọn khi ứng dụng cần độ bền dữ liệu cao. Tuy nhiên, chữ all ở đây có nghĩa là tất cả replica đang thuộc **ISR (In-Sync Replicas)** của partition, không phải tất cả replica được cấu hình trong replication factor.

Sự khác biệt này rất quan trọng khi một follower bị chậm, mất kết nối hoặc bị loại khỏi ISR. Ví dụ, partition có replication factor bằng 3 nhưng chỉ còn 2 replica trong ISR. Với acks=all, producer chờ cả 2 replica trong ISR đáp ứng điều kiện replication. Replica thứ ba vẫn nằm trong assignment nhưng đã ngoài ISR nên không nằm trong tập replica mà lần ghi đó phải chờ.

Muốn giới hạn mức suy giảm khả năng chịu lỗi khi ISR co lại, cần kết hợp acks=all với **min.insync.replicas**. Bài học này giải thích cách hai cấu hình phối hợp, điều gì xảy ra khi replica mất đồng bộ và cách kiểm tra trạng thái thực tế của partition.

## 1. Replication factor và ISR là hai khái niệm khác nhau

Mỗi partition có một tập replica được gán trước. Số lượng replica được gán cho partition được gọi là **replication factor (RF)**. Ví dụ, RF=3 nghĩa là partition có ba bản sao được phân công trên ba broker khác nhau, thường gồm một leader và hai follower.

Tuy nhiên, không phải lúc nào cả ba replica cũng theo kịp leader. Kafka duy trì một tập con gọi là **ISR**:

- ISR gồm leader và các follower đang đủ điều kiện được xem là đồng bộ với leader.
- Follower trong ISR thường xuyên fetch dữ liệu từ leader và không vượt quá giới hạn lag theo cấu hình broker.
- Follower chậm hoặc không liên lạc được có thể bị loại khỏi ISR.
- Khi follower hoạt động trở lại và bắt kịp log của leader, nó có thể được đưa trở lại ISR.

Do đó, RF mô tả số replica được gán cho partition, còn ISR mô tả những replica hiện đang tham gia tập đồng bộ. Số lượng ISR có thể thay đổi theo tình trạng broker, mạng và tải hệ thống.

| Khái niệm | Ý nghĩa | Tính chất |
|---|---|---|
| Replication factor | Số replica được gán cho partition | Cấu hình assignment; thay đổi khi thay đổi replica assignment |
| Leader | Replica đang nhận ghi và phục vụ vai trò leader của partition | Một leader tại một thời điểm |
| Follower | Replica sao chép dữ liệu từ leader | Có thể theo kịp hoặc bị lag |
| ISR | Tập replica đang đồng bộ, bao gồm leader | Thay đổi theo trạng thái replication |
| Out-of-sync replica | Replica được gán nhưng hiện không thuộc ISR | Không nằm trong tập mà acks=all phải chờ |

Ví dụ một partition có RF=3:

~~~text
Partition orders-0

Replica assignment:
  broker-1  leader
  broker-2  follower
  broker-3  follower

ISR hiện tại:
  broker-1
  broker-2

Out of ISR:
  broker-3
~~~

Partition vẫn có ba replica được gán, nhưng chỉ có hai replica trong ISR. Việc broker-3 vẫn xuất hiện trong assignment không có nghĩa producer phải đợi broker-3 khi dùng acks=all.

## 2. acks quyết định producer chờ xác nhận ở mức nào

Producer có ba lựa chọn chính cho acks:

| Giá trị | Điều kiện phản hồi | Đặc điểm |
|---|---|---|
| 0 | Producer không chờ broker xác nhận | Độ trễ thấp, producer không biết chắc broker đã ghi thành công |
| 1 | Leader xác nhận sau khi append record vào log cục bộ | Không chờ follower replicate xong |
| all hoặc -1 | Chờ tất cả replica trong ISR đáp ứng điều kiện xác nhận | Độ bền cao hơn, phụ thuộc kích thước và trạng thái ISR |

Với acks=1, leader có thể trả thành công ngay sau khi append record vào log của mình. Nếu leader gặp sự cố trước khi follower khác nhận record, record có thể bị mất khi một leader mới được chọn.

Với acks=all, leader chỉ trả xác nhận sau khi record đã được replicate đến các replica thuộc ISR theo cơ chế replication của Kafka. Điều kiện commit được thể hiện qua **high watermark (HW)**: record phải nằm dưới mốc đã được replicate đủ theo ISR. Producer vì thế có thể phải chờ lâu hơn nếu một follower vẫn nằm trong ISR nhưng đang fetch chậm.

Điểm mấu chốt là tập replica được xét là ISR tại thời điểm xử lý replication và xác nhận. Kafka không chờ một follower đã bị loại khỏi ISR chỉ vì follower đó vẫn còn trong replica assignment.

## 3. Ví dụ: RF=3 nhưng acks=all chỉ chờ hai replica

Giả sử topic orders có partition orders-0 với replication factor bằng 3:

- broker-1 là leader.
- broker-2 và broker-3 là follower.
- Ban đầu cả ba replica đều nằm trong ISR.

Khi producer gửi record với acks=all và cả ba replica còn trong ISR, leader cần chờ điều kiện replication của cả ba replica.

Sau đó, broker-3 bị chậm hoặc mất kết nối đủ lâu để bị loại khỏi ISR. Trạng thái mới là:

~~~text
Replica assignment: [broker-1, broker-2, broker-3]
ISR hiện tại:       [broker-1, broker-2]
Out of ISR:         [broker-3]
~~~

Một record mới được gửi với acks=all. Producer chờ broker-1 và broker-2 đáp ứng điều kiện replication. Producer không phải chờ broker-3 vì broker-3 đã ngoài ISR.

~~~mermaid
flowchart TD
    P["Producer<br/>acks=all"] --> L["broker-1<br/>Partition leader"]
    L --> F1["broker-2<br/>Follower trong ISR"]
    L -.-> F2["broker-3<br/>Follower ngoài ISR"]
    F1 --> A["Đủ replica trong ISR<br/>đáp ứng điều kiện"]
    A --> ACK["Leader trả ACK cho producer"]
    F2 -.-> N["Không thuộc tập phải chờ<br/>của lần ghi này"]
~~~

Sơ đồ minh họa trạng thái khi broker-3 đã ra khỏi ISR. Đường nét đứt thể hiện broker-3 vẫn được gán làm replica và có thể tiếp tục đồng bộ về sau, nhưng không nằm trong tập ISR hiện tại.

Nếu broker-3 bắt kịp leader, Kafka có thể đưa nó trở lại ISR. Khi đó, các lần ghi tiếp theo với acks=all sẽ phải đáp ứng điều kiện của tập ISR mới, gồm cả broker-3.

## 4. min.insync.replicas đặt ngưỡng tối thiểu cho lần ghi

**min.insync.replicas** là cấu hình đặt số replica tối thiểu phải có trong ISR để broker chấp nhận ghi khi producer dùng acks=all.

Cấu hình này thường được đặt ở cấp topic hoặc broker. Khi producer gửi record với acks=all:

- Nếu kích thước ISR bằng hoặc lớn hơn min.insync.replicas, broker có thể chấp nhận ghi và chờ điều kiện xác nhận từ ISR.
- Nếu kích thước ISR thấp hơn min.insync.replicas, broker từ chối ghi thay vì chấp nhận một mức replication thấp hơn ngưỡng đã đặt.

Cấu hình min.insync.replicas không bắt buộc mọi replica đã gán phải online. Nó đặt ngưỡng tối thiểu cho số replica hiện thuộc ISR.

### Ví dụ với RF=3 và min.insync.replicas=2

~~~properties
min.insync.replicas=2
~~~

Giả sử topic được tạo với replication factor bằng 3. Kết quả theo kích thước ISR:

| ISR hiện tại | acks=all | Kết quả khi min.insync.replicas=2 |
|---:|---|---|
| 3 | Chờ cả 3 replica trong ISR | Có thể ghi thành công |
| 2 | Chờ cả 2 replica trong ISR | Có thể ghi thành công |
| 1 | Chỉ còn leader trong ISR | Bị từ chối vì dưới ngưỡng 2 |
| 0 | Không có ISR hợp lệ | Không thể ghi |

Cụm từ “có thể ghi thành công” còn phụ thuộc broker, partition leader, timeout, quyền truy cập và các điều kiện lỗi khác. Bảng chỉ minh họa tác động của kích thước ISR và min.insync.replicas.

Với RF=3 và min.insync.replicas=2, cluster có thể tiếp tục nhận ghi khi một replica bị loại khỏi ISR, nhưng sẽ từ chối ghi khi chỉ còn một replica trong ISR. Điều này tạo ra một điểm cân bằng giữa tính sẵn sàng ghi và mức replication tối thiểu mà ứng dụng yêu cầu.

### Tại sao không đặt min.insync.replicas bằng replication factor?

Nếu đặt min.insync.replicas=3 với RF=3, chỉ cần một follower ra khỏi ISR thì broker sẽ từ chối ghi mới với acks=all. Cách đặt này buộc cả ba replica phải ở trong ISR để tiếp tục ghi.

Đây có thể là lựa chọn phù hợp với một số workload ưu tiên yêu cầu replication tối đa, nhưng làm giảm khả năng tiếp tục ghi khi có lỗi một broker. Với nhiều hệ thống production, RF=3 và min.insync.replicas=2 là cấu hình phổ biến để duy trì ít nhất hai bản sao đồng bộ khi ghi được chấp nhận.

Không có một giá trị phù hợp cho mọi hệ thống. Hãy chọn ngưỡng theo mức mất dữ liệu có thể chấp nhận, yêu cầu khả dụng, topology broker và khả năng chịu lỗi của từng workload.

## 5. Cấu hình topic và producer trong Java

Có thể tạo topic với ba replica và đặt min.insync.replicas bằng 2 bằng lệnh:

~~~bash
bin/kafka-topics.sh --bootstrap-server broker-1:9092 --create --topic orders --partitions 6 --replication-factor 3 --config min.insync.replicas=2
~~~

Với topic đã tồn tại, có thể thay đổi cấu hình topic bằng công cụ quản trị phù hợp:

~~~bash
bin/kafka-configs.sh --bootstrap-server broker-1:9092 --entity-type topics --entity-name orders --alter --add-config min.insync.replicas=2
~~~

Producer Java có thể cấu hình acks=all và bật idempotence:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class ReliableOrderProducer {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "broker-1:9092,broker-2:9092,broker-3:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {
            ProducerRecord<String, String> record = new ProducerRecord<>(
                "orders",
                "order-1042",
                "{\"status\":\"PLACED\"}"
            );
            producer.send(record).get();
        }
    }
}
~~~

Trong ví dụ:

- acks=all yêu cầu xác nhận theo toàn bộ ISR hiện tại.
- enable.idempotence=true giúp producer tránh tạo bản ghi trùng do retry trong phạm vi bảo đảm của producer idempotence.
- min.insync.replicas=2 trên topic đặt ngưỡng tối thiểu hai replica trong ISR cho lần ghi dùng acks=all.

Idempotence không làm tăng số replica, không thay đổi ISR và không biến acks=all thành chờ mọi replica được cấu hình. Nó giải quyết một vấn đề khác: tránh duplicate record do retry của producer trong các điều kiện được Kafka hỗ trợ.

## 6. Khi ISR thay đổi trong lúc producer đang ghi

ISR không phải một danh sách cố định. Nó thay đổi khi follower mất khả năng theo kịp hoặc bắt kịp leader. Điều này tạo ra một số tình huống mà producer cần xử lý.

### Follower chậm nhưng vẫn ở trong ISR

Nếu follower còn trong ISR nhưng fetch chậm, acks=all có thể phải chờ follower đó. Thời gian chờ tăng có thể khiến producer tiến gần request.timeout.ms hoặc delivery.timeout.ms. Việc timeout không tự động chứng minh record chưa được ghi; producer và ứng dụng cần xử lý retry theo cấu hình và semantics phù hợp.

### Follower bị loại khỏi ISR

Khi follower không đáp ứng điều kiện theo kịp, leader có thể loại follower khỏi ISR. Sau khi ISR thu hẹp, các lần ghi với acks=all chỉ cần đáp ứng điều kiện của ISR hiện tại, với điều kiện kích thước ISR không thấp hơn min.insync.replicas.

Nếu follower bị loại khỏi ISR trong lúc record đang chờ xác nhận, high watermark có thể tiến lên theo ISR mới và giải phóng request đang chờ mà không đợi follower đã bị loại bắt kịp. Vì vậy, acks=all phản ánh trạng thái đồng bộ mà leader đang dùng để xác định commit, không phải toàn bộ replica assignment ban đầu.

Nếu ISR giảm xuống dưới ngưỡng tối thiểu, broker từ chối ghi. Tùy thời điểm phát hiện, producer có thể nhận lỗi như NotEnoughReplicasException hoặc NotEnoughReplicasAfterAppendException. Trường hợp lỗi sau append có nghĩa record có thể đã được ghi ở leader nhưng broker không thể hoàn thành mức xác nhận yêu cầu. Ứng dụng không nên diễn giải mọi lỗi gửi thành bằng chứng chắc chắn rằng record chưa từng được append.

### Follower bắt kịp và trở lại ISR

Follower cần fetch đủ dữ liệu và đáp ứng các điều kiện đồng bộ trước khi được đưa trở lại ISR. Sau khi gia nhập ISR, follower lại tham gia điều kiện xác nhận của các lần ghi acks=all tiếp theo.

Việc một follower xuất hiện lại trong ISR không có nghĩa producer đang chờ một lần ghi cũ phải tự động gửi lại. Producer xử lý kết quả request theo giao thức và chính sách retry; ứng dụng cần dùng event ID hoặc idempotence khi phù hợp để quản lý trường hợp kết quả không rõ ràng.

## 7. Kiểm tra replica assignment và ISR thực tế

Đừng suy ra số replica đang được chờ chỉ từ replication factor trong cấu hình topic. Hãy xem trạng thái partition để biết replica assignment và ISR tại thời điểm kiểm tra.

Có thể dùng:

~~~bash
bin/kafka-topics.sh --bootstrap-server broker-1:9092 --describe --topic orders
~~~

Kết quả minh họa:

~~~text
Topic: orders
Partition: 0
Leader: 1
Replicas: 1,2,3
Isr: 1,2
~~~

Cách đọc:

- Replicas: 1,2,3 cho biết ba broker được gán replica cho partition.
- Leader: 1 cho biết broker 1 đang là leader.
- Isr: 1,2 cho biết chỉ broker 1 và 2 đang nằm trong ISR.
- Broker 3 vẫn được gán nhưng hiện ngoài ISR.

Khi vận hành, nên theo dõi kích thước ISR, số replica ngoài ISR, thời gian follower lag và lỗi producer. Một lần mô tả topic chỉ là ảnh chụp tại một thời điểm; cần quan sát liên tục hoặc dùng metrics để phát hiện ISR thay đổi bất thường.

## 8. acks=all bảo đảm điều gì và không bảo đảm điều gì?

Kết hợp acks=all với min.insync.replicas phù hợp giúp tăng độ bền của dữ liệu đã được xác nhận, nhưng không phải lời hứa tuyệt đối rằng mọi bản sao được gán đều đã ghi dữ liệu hoặc mọi tình huống lỗi đều không mất dữ liệu.

| Phát biểu | Đúng hay sai | Giải thích |
|---|---|---|
| acks=all chờ mọi replica trong replica assignment | Sai | Nó chờ các replica thuộc ISR hiện tại |
| acks=all chờ mọi replica trong ISR | Đúng | Đây là tập replica được dùng cho điều kiện xác nhận |
| min.insync.replicas buộc mọi replica được gán phải online | Sai | Nó đặt ngưỡng số replica trong ISR |
| RF=3, ISR=2, min ISR=2 có thể nhận ghi | Đúng | Hai replica trong ISR đủ ngưỡng |
| RF=3, ISR=1, min ISR=2 vẫn ghi thành công với acks=all | Sai | Broker từ chối vì ISR dưới ngưỡng |
| acks=all có nghĩa mọi replica đã fsync dữ liệu xuống thiết bị vật lý | Sai | ACK phản ánh điều kiện replication của Kafka, không phải cam kết fsync vật lý trên từng broker |
| enable.idempotence làm tăng số bản sao | Sai | Idempotence xử lý duplicate do retry, không điều khiển replication factor |

Một số giới hạn cần nhớ:

- **Replica assignment không phải tập xác nhận.** Replica ngoài ISR có thể chưa có record khi producer đã nhận ACK.
- **min.insync.replicas là ngưỡng, không phải số bản sao cố định.** Với ISR lớn hơn ngưỡng, acks=all vẫn chờ tất cả ISR hiện tại.
- **ACK không đồng nghĩa fsync trên mọi ổ đĩa.** Kafka dựa vào replication và cơ chế lưu trữ log; không nên diễn giải ACK là mỗi replica đã flush dữ liệu xuống media vật lý.
- **Mất toàn bộ bản sao còn lại vẫn có thể gây mất dữ liệu.** Mức an toàn phụ thuộc số replica thực sự giữ record, lỗi tương quan, chính sách vận hành và cấu hình durability khác.
- **Producer timeout có thể tạo kết quả không rõ ràng.** Record có thể đã được append dù ứng dụng chưa nhận ACK; cần xử lý retry và idempotence đúng cách.

## 9. Cách chọn cấu hình theo yêu cầu hệ thống

Có thể bắt đầu bằng các lựa chọn sau rồi điều chỉnh theo yêu cầu cụ thể:

| Mục tiêu | Replication factor | min.insync.replicas | Producer acks | Đánh đổi |
|---|---:|---:|---|---|
| Môi trường thử nghiệm đơn giản | 1 | 1 | all hoặc 1 | Không có dự phòng replica |
| Hệ thống cần tiếp tục ghi khi mất một broker | 3 | 2 | all | Cần ít nhất hai replica trong ISR để ghi |
| Ưu tiên replication đủ cả ba replica trước khi nhận ghi | 3 | 3 | all | Một replica ra khỏi ISR có thể làm ghi bị từ chối |
| Workload chấp nhận rủi ro cao hơn để ưu tiên khả dụng | 3 | 1 | all | Có thể ghi khi chỉ còn một replica trong ISR |

Đây là các ví dụ lựa chọn chính sách, không phải cấu hình áp dụng cho mọi hệ thống. Với dữ liệu quan trọng, thường nên:

1. Chọn replication factor đủ lớn và phân bố replica qua các broker hoặc failure domain khác nhau.
2. Đặt min.insync.replicas theo số bản sao tối thiểu cần có khi chấp nhận ghi.
3. Cấu hình producer dùng acks=all.
4. Bật idempotence nếu phù hợp để giảm duplicate do retry.
5. Theo dõi ISR shrink/expand, producer error rate và thời gian xác nhận.
6. Kiểm thử tình huống broker dừng, follower lag và mất kết nối để xác minh chính sách thực tế.

Nếu cần độ bền cao, hãy đánh giá cả vị trí đặt replica, rack awareness, cấu hình broker, khả năng phục hồi và quy trình xử lý khi mất quorum dữ liệu. Chỉ tăng replication factor mà không kiểm tra ISR và min.insync.replicas sẽ không đảm bảo lần ghi đang xét chờ đủ số bản sao mong muốn.

## 10. Tự kiểm tra cách hiểu

1. RF=3 có nghĩa gì? — Partition được gán ba replica.
2. ISR=2 có nghĩa gì? — Hiện có hai replica, bao gồm leader, nằm trong tập đồng bộ.
3. Khi acks=all, producer chờ tập nào? — Tất cả replica trong ISR hiện tại của partition.
4. Nếu RF=3 nhưng một follower ngoài ISR, producer có phải chờ follower đó không? — Không.
5. min.insync.replicas=2 có tác dụng gì? — Từ chối ghi dùng acks=all nếu ISR có ít hơn hai replica.
6. RF=3, ISR=2 và min ISR=2 thì ghi có thể thành công không? — Có, nếu các điều kiện ghi khác đều đáp ứng; acks=all chờ cả hai replica trong ISR.
7. Nếu ISR giảm còn một trong khi min ISR bằng hai thì sao? — Broker từ chối ghi; producer phải xử lý lỗi.
8. acks=all có chứng minh mọi replica đã fsync dữ liệu xuống ổ đĩa không? — Không. Nó thể hiện điều kiện replication của Kafka.

Khi đánh giá độ bền dữ liệu Kafka, hãy nhìn đồng thời vào replication factor, ISR, min.insync.replicas và acks của producer. **acks=all có nghĩa chờ tất cả replica đang đồng bộ, còn min.insync.replicas quyết định số replica đồng bộ tối thiểu để broker chấp nhận lần ghi.** Hai cấu hình này phối hợp mới tạo nên chính sách ghi phù hợp với mức rủi ro mà hệ thống chấp nhận.

