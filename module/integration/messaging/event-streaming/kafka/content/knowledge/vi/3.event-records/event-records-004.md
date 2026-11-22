# Phân biệt null key, null value và thông điệp rỗng

Trong Apache Kafka, một record có thể có key, value hoặc cả hai trường mang giá trị null. Một record cũng có thể chứa value rỗng, chẳng hạn chuỗi rỗng hoặc mảng byte có độ dài bằng 0. Những trường hợp này trông giống nhau khi chỉ nhìn vào log ứng dụng, nhưng Kafka xử lý chúng khác nhau, đặc biệt khi topic bật log compaction.

Phân biệt chính xác các trường hợp này giúp tránh xóa nhầm dữ liệu, phân vùng sai luồng sự kiện và bỏ sót bản ghi khi consumer dựng lại trạng thái. Quy tắc quan trọng nhất là: **null key không phải tombstone; null value chỉ mang ý nghĩa tombstone khi đi cùng key khác null trên topic có compaction; value rỗng vẫn là một payload có thật.**

## 1. Cấu trúc record và ý nghĩa của null

Một Kafka record chứa metadata và dữ liệu, trong đó các trường thường được ứng dụng quan tâm là:

- **Topic:** luồng mà producer ghi record vào.
- **Partition:** phân vùng chứa record.
- **Offset:** vị trí của record trong partition.
- **Key:** dữ liệu định danh hoặc phân vùng record; có thể null.
- **Value:** payload của record; có thể null.
- **Timestamp và headers:** thời điểm cùng metadata bổ sung.

Ở tầng dữ liệu, key và value được biểu diễn dưới dạng byte. Mỗi trường có thể là null hoặc là một dãy byte. Một dãy byte có độ dài bằng 0 vẫn khác null: null nghĩa là không có giá trị byte, còn mảng rỗng là một giá trị byte hợp lệ nhưng không chứa byte nào.

| Trường hợp | Key | Value | Có record trong Kafka? | Ý nghĩa thường gặp |
|---|---|---|---|---|
| Null key | null | Có dữ liệu | Có | Record không có khóa định danh |
| Null value | Có key | null | Có | Có thể là tombstone trên topic compacted |
| Cả key và value đều null | null | null | Có | Record không có key và payload; không phải tombstone |
| Value rỗng | Có thể null hoặc có key | Mảng byte độ dài 0 | Có | Payload tồn tại nhưng rỗng |
| Không gửi record | Không áp dụng | Không áp dụng | Không | Không có record, offset mới hay sự kiện để consumer đọc |

Cần phân biệt hai cách nói thường bị nhập làm một:

- **Record có value null:** producer vẫn gửi một record; record có thể có partition, offset, timestamp và headers.
- **Không có record:** producer không gửi gì lên Kafka; consumer không nhận được record tương ứng.

Một lời gọi gửi record với value null không tương đương với việc bỏ qua lời gọi gửi.

## 2. Null key: record không có khóa định danh

Null key có nghĩa là trường key của record không chứa dữ liệu. Record vẫn có thể có value bình thường, timestamp và headers.

Ví dụ, một dịch vụ phát heartbeat hoặc số liệu độc lập:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("system-events", (String) null, "heartbeat");

producer.send(record);
~~~

Record trên vẫn được ghi vào topic system-events. Nó chỉ không mang key.

### Null key ảnh hưởng đến partition như thế nào?

Với default partitioner của Kafka producer hiện đại, record không có key thường được đưa vào một sticky partition để gom batch và cải thiện hiệu quả gửi. Khi batch hoàn tất hoặc partitioner chuyển sang batch khác, record không có key tiếp theo có thể đi vào partition khác. Nếu producer cấu hình partition cụ thể hoặc dùng custom partitioner, quy tắc phân vùng sẽ phụ thuộc cấu hình đó.

Vì vậy, null key không cung cấp bảo đảm rằng các sự kiện liên quan đến cùng một đối tượng sẽ luôn nằm trong cùng partition. Nếu nghiệp vụ cần thứ tự theo khách hàng, đơn hàng hoặc tài khoản, hãy gửi một key ổn định, chẳng hạn customerId, orderId hoặc accountId.

Khi key khác null, default partitioner thường dùng byte đã serialize của key để chọn partition. Với cùng key, cùng cách serialize và số partition không đổi, các record thường được đưa về cùng partition. Thứ tự được Kafka bảo đảm trong partition đó.

### Null key trong topic compacted

Log compaction dựa trên key để xác định những record nào thuộc cùng một thực thể. Record có null key không tham gia cơ chế gom và giữ bản ghi mới nhất theo key. Do đó, không nên phát các record không có key vào compacted topic nếu kỳ vọng chúng được compact theo một thực thể.

Nếu topic chỉ bật compact, record null key có thể không được loại bỏ bởi quá trình compaction theo key. Nếu cần giới hạn dung lượng cho loại record này, phải cân nhắc chính sách retention phù hợp, ví dụ kết hợp compact và delete khi thiết kế topic cho phép.

## 3. Null value: payload không tồn tại

Null value có nghĩa là value sau khi serialize là null, tức Kafka record không có dãy byte payload. Record vẫn tồn tại và vẫn có thể mang key, timestamp, headers, partition và offset.

Ví dụ:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("customer-state", "customer-42", null);

producer.send(record);
~~~

Record trên có key customer-42 nhưng value null. Ý nghĩa của nó phụ thuộc vào cấu hình topic.

### Null value trên topic thông thường

Nếu topic chỉ dùng cleanup policy delete, null value không tự động xóa một record cũ hoặc một hàng trong cơ sở dữ liệu. Nó là một record có payload null. Consumer có thể đọc được record và phải quyết định cách xử lý theo hợp đồng dữ liệu của ứng dụng.

Kafka không tự suy luận rằng null có nghĩa là xóa khách hàng, hủy đơn hàng hay đặt một trường về trạng thái trống.

### Null value trên compacted topic: tombstone

Nếu topic bật log compaction, một record có key khác null và value null được gọi là **tombstone**. Tombstone đánh dấu rằng trạng thái của key tương ứng đã bị xóa.

Ví dụ, topic customer-state đang lưu trạng thái mới nhất của từng khách hàng:

| Offset | Key | Value | Diễn giải |
|---:|---|---|---|
| 10 | customer-42 | ACTIVE | Khách hàng đang hoạt động |
| 18 | customer-42 | SUSPENDED | Trạng thái mới nhất chuyển thành tạm khóa |
| 27 | customer-42 | null | Tombstone: xóa trạng thái của key này |

Khi log cleaner chạy, Kafka có thể loại bỏ những record cũ của customer-42 và giữ tombstone trong khoảng thời gian quy định. Sau khi tombstone hết thời gian lưu giữ, một lượt compaction sau đó có thể loại bỏ cả tombstone. Kết quả là các giá trị cũ của key đã được dọn khỏi log compacted.

Một số điểm cần nhớ:

- Tombstone phải có key khác null để xác định trạng thái cần xóa.
- Topic phải bật cleanup policy có compact thì tombstone mới có ý nghĩa xóa theo key.
- Compaction chạy nền, không xóa ngay tại thời điểm producer gửi tombstone.
- Tombstone được giữ trong thời gian cấu hình bởi delete.retention.ms trước khi có thể bị loại bỏ.
- Consumer dựng lại state store cần lưu ý thời gian giữ tombstone. Consumer đọc quá chậm hoặc bắt đầu đọc sau khi tombstone đã bị dọn có thể không quan sát được dấu xóa đó.

Topic có thể dùng cleanup.policy=compact hoặc kết hợp compact,delete. Khi kết hợp hai chính sách, record còn chịu tác động của retention theo thời gian hoặc dung lượng bên cạnh compaction.

### Tombstone không phải domain event đầy đủ

Tombstone phù hợp để biểu diễn việc xóa trạng thái hiện tại theo key trong compacted topic. Nếu hệ thống cần lưu lịch sử nghiệp vụ như ai xóa khách hàng, vì sao xóa, xóa lúc nào hoặc yêu cầu pháp lý liên quan, hãy phát một domain event có payload rõ ràng, ví dụ CustomerDeleted. Tombstone có thể được dùng bổ sung để cập nhật compacted state topic.

## 4. Value rỗng: payload có tồn tại nhưng không chứa nội dung

Value rỗng là một dãy byte có độ dài bằng 0. Đây là dữ liệu khác null. Kafka lưu record với value rỗng như một payload hợp lệ.

Ví dụ với StringSerializer:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("customer-state", "customer-42", "");

producer.send(record);
~~~

Chuỗi rỗng được serialize thành mảng byte độ dài 0. Record vẫn có value khác null, nên **không phải tombstone**.

Một số biểu diễn cần phân biệt:

| Giá trị ở tầng ứng dụng | Dữ liệu byte sau serialize (ví dụ) | Kafka value có null không? |
|---|---|---|
| Java null với StringSerializer | null | Có |
| Chuỗi rỗng "" với StringSerializer | Mảng byte độ dài 0 | Không |
| JSON string rỗng | Hai byte biểu diễn dấu ngoặc kép | Không |
| JSON literal null | Các byte biểu diễn chữ null | Không |
| JSON object rỗng {} | Các byte biểu diễn dấu ngoặc và ngoặc nhọn | Không |

Serializer quyết định cách đối tượng ứng dụng được chuyển thành byte. Kafka chỉ nhìn thấy kết quả serialize. Ví dụ, chuỗi ký tự null hoặc JSON literal null là payload byte bình thường; chúng không phải Kafka null value.

Với byte array, có thể kiểm tra rõ ràng:

~~~java
byte[] emptyPayload = new byte[0];

ProducerRecord<String, byte[]> record =
    new ProducerRecord<>("raw-events", "event-42", emptyPayload);

producer.send(record);
~~~

Nếu consumer nhận được value là mảng byte không null và có length bằng 0, nó đã nhận một record có payload rỗng.

## 5. So sánh ba trường hợp trong Java và Spring Kafka

Với producer dùng StringSerializer, có thể tạo ba loại record như sau:

~~~java
@Service
public class KafkaRecordPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaRecordPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishWithoutKey(String event) {
        // Có record, nhưng key là null.
        kafkaTemplate.send("system-events", null, event);
    }

    public void publishTombstone(String customerId) {
        // Chỉ là tombstone nếu topic bật log compaction.
        kafkaTemplate.send("customer-state", customerId, null);
    }

    public void publishEmptyValue(String customerId) {
        // Value là chuỗi rỗng, không phải tombstone.
        kafkaTemplate.send("customer-state", customerId, "");
    }
}
~~~

Cả ba lời gọi đều gửi record. Chúng khác nhau ở key và value:

- publishWithoutKey gửi key null, value có nội dung.
- publishTombstone gửi key khác null, value null.
- publishEmptyValue gửi key khác null, value rỗng.

Nếu không gọi kafkaTemplate.send, sẽ không có record nào được gửi. Không nên dùng một biến null ở tầng nghiệp vụ mà không xác định rõ ý nghĩa: bỏ qua sự kiện, phát tombstone, hay phát một record có payload rỗng.

## 6. Consumer cần kiểm tra null trước khi kiểm tra nội dung

Khi đọc bằng ConsumerRecord, ứng dụng có thể kiểm tra riêng key và value:

~~~java
@Component
public class CustomerStateListener {
    @KafkaListener(
        topics = "customer-state",
        groupId = "customer-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String key = record.key();
        String value = record.value();

        if (value == null) {
            if (key != null) {
                // Tombstone trên compacted topic:
                // xóa trạng thái customer tương ứng.
                deleteCustomerState(key);
            } else {
                // Record không có key và không có value.
                // Xử lý theo hợp đồng dữ liệu của ứng dụng.
            }
            return;
        }

        if (value.isEmpty()) {
            // Payload rỗng: record vẫn có value.
            handleEmptyPayload(key);
            return;
        }

        // Payload có nội dung.
        updateCustomerState(key, value);
    }

    private void deleteCustomerState(String customerId) {
        // Xóa trạng thái khỏi read model hoặc state store.
    }

    private void handleEmptyPayload(String key) {
        // Xử lý payload rỗng theo quy ước nghiệp vụ.
    }

    private void updateCustomerState(String key, String value) {
        // Cập nhật trạng thái hiện tại.
    }
}
~~~

Đoạn mã minh họa cách phân nhánh, không phải một chính sách nghiệp vụ áp dụng cho mọi topic. Trước khi coi null value là yêu cầu xóa, consumer phải biết topic đó có hợp đồng tombstone hay không. Nếu topic không dùng compact hoặc ứng dụng quy định null mang ý nghĩa khác, hãy xử lý theo hợp đồng tương ứng.

Một số lưu ý khi viết consumer:

1. Kiểm tra value null trước khi gọi isEmpty(), length hoặc deserialize payload.
2. Nếu tombstone được phép, kiểm tra key để xác định thực thể cần xóa.
3. Không chuyển null thành chuỗi rỗng một cách tự động trong tầng mapping, vì thao tác đó làm mất khả năng nhận diện tombstone.
4. Khi deserialize JSON hoặc Avro, phân biệt Kafka null với một payload hợp lệ mã hóa giá trị null theo định dạng dữ liệu.
5. Nếu dùng Spring Kafka với tham số payload đơn giản, hãy cân nhắc nhận ConsumerRecord khi cần kiểm tra cả key, value, offset và headers.

## 7. Những lỗi thiết kế thường gặp

### Nhầm null key với tombstone

Một record key null và value có dữ liệu không xóa trạng thái của bất kỳ key nào. Nó chỉ là record không có key. Tombstone cần key khác null cùng value null trên compacted topic.

### Dùng chuỗi rỗng để xóa dữ liệu

Chuỗi rỗng là payload có thật. Log compaction không coi nó là dấu xóa. Nếu cần xóa trạng thái theo key, gửi null value đúng hợp đồng tombstone.

### Cho rằng null value luôn xóa bản ghi cũ

Trên topic chỉ dùng cleanup policy delete, null value không kích hoạt xóa theo key. Ý nghĩa tombstone thuộc về log compaction.

### Gộp null và empty trong bước deserialize

Một lớp mapping có thể biến null thành chuỗi rỗng, hoặc serializer có thể mã hóa giá trị null thành byte. Khi đó consumer mất thông tin cần thiết để phân biệt tombstone và payload hợp lệ. Hãy thống nhất serializer, schema và hợp đồng dữ liệu giữa producer với consumer.

### Cho rằng tombstone được xóa ngay lập tức

Tombstone được ghi như một record và được xử lý qua các lượt compaction nền. Nếu consumer duy trì bản sao trạng thái, nó phải áp dụng tombstone khi đọc được. Khi cần dựng lại state từ đầu, phải thiết kế thời gian lưu tombstone và quy trình bootstrap phù hợp.

### Dùng null key cho dữ liệu cần thứ tự theo thực thể

Các record không có key không có cơ chế phân vùng ổn định theo thực thể. Nếu cần ordering theo customerId hoặc orderId, hãy dùng key ổn định và giữ cấu hình partitioner phù hợp.

## 8. Quy ước thiết kế nên áp dụng

Trước khi triển khai producer và consumer, hãy thống nhất một hợp đồng rõ ràng cho từng topic:

| Câu hỏi | Quy ước cần xác định |
|---|---|
| Key có bắt buộc không? | Chọn key nghiệp vụ ổn định nếu cần ordering hoặc compaction |
| Null key có được chấp nhận không? | Nêu rõ loại record nào được phép không có key |
| Null value có ý nghĩa gì? | Chỉ định rõ có dùng tombstone hay không |
| Topic có compaction không? | Xác định cleanup.policy và thời gian giữ tombstone |
| Value rỗng có hợp lệ không? | Quy định đây là payload rỗng hay dữ liệu không hợp lệ |
| Consumer xử lý tombstone thế nào? | Xóa state theo key và bảo đảm thao tác có thể lặp an toàn |
| Serializer/schema nào được dùng? | Bảo đảm null, empty và giá trị null trong định dạng dữ liệu không bị nhập làm một |

Với topic lưu trạng thái mới nhất theo thực thể, một quy ước phổ biến là:

- Key luôn chứa ID thực thể.
- Value khác null chứa trạng thái mới nhất.
- Value null là tombstone để xóa trạng thái theo key.
- Value rỗng chỉ được dùng nếu ứng dụng định nghĩa rõ payload rỗng là hợp lệ.
- Consumer xử lý tombstone theo cách idempotent để việc nhận lại record không gây sai lệch.

Với topic lưu domain event, thường nên dùng event có schema và tên rõ nghĩa, ví dụ CustomerCreated, CustomerUpdated hoặc CustomerDeleted. Một event xóa có payload giúp lưu lại nguyên nhân, thời điểm và actor nếu nghiệp vụ cần. Không nên dùng tombstone thay cho mọi sự kiện xóa trong event history.

## 9. Kết luận

Null key, null value và value rỗng là ba trạng thái dữ liệu khác nhau. Null key nói rằng record không có khóa để định danh hoặc phân vùng theo thực thể. Null value nói rằng record không có payload; khi key khác null và topic bật compaction, nó có thể là tombstone đánh dấu xóa trạng thái. Value rỗng vẫn là payload có thật và không kích hoạt xóa theo key.

Khi thiết kế Kafka topic, hãy xác định rõ key, serializer, cleanup policy và hợp đồng giữa producer với consumer. Việc phân biệt đúng ba trường hợp này giúp giữ ordering theo thực thể, vận hành log compaction chính xác và tránh biến một payload rỗng thành thao tác xóa dữ liệu ngoài ý muốn.
