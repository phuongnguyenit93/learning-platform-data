# Tombstone và ý nghĩa xóa theo key

Trong Apache Kafka, một record có thể mang **key** và **value**. Với topic bật log compaction, tổ hợp **key khác null và value bằng null** có ý nghĩa đặc biệt: đó là một *tombstone* (bản ghi đánh dấu xóa). Tombstone thông báo rằng trạng thái hiện tại của key tương ứng đã bị xóa. Kafka dùng dấu này khi dọn log compacted; consumer cũng có thể dùng nó để xóa key khỏi bảng trạng thái hoặc kho dữ liệu cục bộ.

Tombstone thường xuất hiện trong các topic lưu trạng thái mới nhất theo key, chẳng hạn trạng thái khách hàng, tài khoản hoặc cấu hình. Để hiểu đúng hành vi này, cần phân biệt ba việc: ứng dụng phát một dấu xóa, consumer áp dụng dấu xóa vào trạng thái của mình, và Kafka dọn các record cũ khỏi log. Ba việc có liên quan nhưng không xảy ra đồng thời.

## 1. Tombstone là record có key và value null

Một tombstone là Kafka record có:

- **Key khác null:** xác định thực thể hoặc mục dữ liệu cần xóa, ví dụ customer-42.
- **Value bằng null:** biểu thị thao tác xóa key đó trong ngữ cảnh topic compacted.
- **Metadata của record:** vẫn có thể có timestamp, headers, partition và offset như những record khác.

Ví dụ, topic customers.state lưu trạng thái mới nhất của khách hàng theo customerId. Một record thông thường có thể là:

~~~text
topic:     customers.state
key:       customer-42
value:     {"name":"An","tier":"GOLD"}
partition: 1
offset:    105
~~~

Khi khách hàng bị xóa khỏi trạng thái hiện tại, producer gửi một record mới với cùng key và value null:

~~~text
topic:     customers.state
key:       customer-42
value:     null
partition: 1
offset:    132
~~~

Record ở offset 132 là tombstone. Nó không chứa một đối tượng khách hàng có trường deleted=true; bản thân value null là dấu hiệu xóa trong compacted topic. Khi consumer đọc đến tombstone, consumer hiểu rằng key customer-42 cần được loại khỏi trạng thái đang duy trì.

Điều kiện về key rất quan trọng. Kafka compaction đối chiếu record theo key trong từng partition. Nếu key là null, broker không có định danh để xác định mục dữ liệu nào cần xóa. Một record có key null và value null không thể thay thế tombstone theo key.

## 2. Tombstone khác với value rỗng hoặc chuỗi "null"

Không phải mọi payload trông có vẻ rỗng đều là tombstone. Kafka phân biệt value null với value có dữ liệu nhưng biểu diễn một nội dung rỗng:

| Value được gửi | Ý nghĩa ở cấp Kafka record | Là tombstone? |
|---|---|---|
| null | Không có payload value | Có, nếu key khác null và topic dùng compaction |
| Chuỗi rỗng ("") | Value có độ dài 0 sau serialization | Không |
| Mảng byte rỗng (byte[0]) | Value tồn tại nhưng có 0 byte | Không |
| Chuỗi "null" | Payload chứa bốn ký tự null | Không |
| JSON {"deleted":true} | Payload JSON bình thường có trường deleted | Không |

Ví dụ, JSON null được serializer mã hóa thành các byte ký tự n, u, l, l; đó vẫn là một value có dữ liệu. Nó khác với ProducerRecord có value Java null.

Sự phân biệt này ảnh hưởng trực tiếp đến logic consumer. Với Java consumer, kiểm tra record.value() == null để nhận diện tombstone. Không dùng isEmpty() hoặc so sánh chuỗi với "null" để thay thế kiểm tra này.

## 3. Log compaction sử dụng tombstone như thế nào?

**Log compaction** là cơ chế dọn log của Kafka để giữ lại trạng thái mới nhất theo key trong mỗi partition. Nó phù hợp với topic biểu diễn trạng thái hiện tại, nơi ứng dụng cần biết giá trị mới nhất của mỗi thực thể thay vì giữ mọi phiên bản thay đổi trong bản log compacted.

Giả sử topic customers.state nhận các record sau cho cùng key:

~~~text
offset  key           value
------  ------------  -------------------------------
100     customer-42   {"name":"An","tier":"SILVER"}
105     customer-42   {"name":"An","tier":"GOLD"}
132     customer-42   null
~~~

Trước khi cleaner chạy, log có thể chứa cả ba record. Khi compaction xử lý các segment phù hợp, Kafka nhận ra record tại offset 132 là trạng thái mới nhất cho key customer-42; các phiên bản cũ hơn của cùng key có thể được loại khỏi log. Tombstone được giữ lại trong một khoảng thời gian để consumer có cơ hội nhận biết việc xóa. Sau khi thời gian giữ tombstone hết hạn và các điều kiện dọn log phù hợp được đáp ứng, chính tombstone cũng có thể bị loại bỏ.

~~~mermaid
flowchart TD
    P["Producer gửi key=customer-42<br/>value=null"] --> T["Topic compacted<br/>customers.state"]
    T --> L["Partition log<br/>offset 100: value SILVER<br/>offset 105: value GOLD<br/>offset 132: tombstone"]
    L --> C["Log cleaner chạy compaction"]
    C --> R["Loại các phiên bản cũ<br/>theo key"]
    R --> D["Giữ tombstone trong<br/>delete.retention.ms"]
    D --> X["Tombstone có thể được dọn<br/>sau khi hết thời gian giữ"]
    T --> U["Consumer đọc tombstone"]
    U --> S["Xóa customer-42 khỏi<br/>state store / bảng trạng thái"]
~~~

Có một số điểm cần hiểu rõ:

- **Compaction chạy bất đồng bộ.** Gửi tombstone không làm Kafka xóa ngay các record cũ khỏi đĩa. Log cleaner xử lý các segment theo lịch và điều kiện của broker.
- **Compaction diễn ra theo partition.** Kafka không hợp nhất cùng một key ở các partition khác nhau. Producer và partitioner cần định tuyến ổn định để các record của cùng key đi vào cùng partition.
- **Offset không được đánh số lại.** Sau compaction có thể xuất hiện khoảng trống offset vì record cũ đã bị loại bỏ. Offset vẫn là vị trí trong lịch sử partition, không phải số thứ tự liên tục của các record còn nhìn thấy.
- **Tombstone không tồn tại vô thời hạn.** Kafka giữ dấu xóa trong khoảng thời gian cấu hình; sau đó cleaner có thể loại tombstone khỏi log.
- **Compaction không phải thao tác xóa toàn topic.** Tombstone chỉ đánh dấu xóa dữ liệu của key tương ứng trong log compacted.

## 4. Cấu hình topic compacted

Để tombstone có ý nghĩa xóa theo key trong cơ chế compaction, topic phải bật chính sách compact trong cleanup.policy.

Ví dụ cấu hình ý nghĩa:

~~~properties
cleanup.policy=compact
delete.retention.ms=86400000
~~~

cleanup.policy=compact bật log compaction. delete.retention.ms xác định khoảng thời gian Kafka giữ các tombstone trước khi chúng đủ điều kiện bị dọn. Giá trị 86.400.000 ms trong ví dụ tương đương một ngày; hãy chọn khoảng thời gian dựa trên thời gian tối đa mà consumer cần để bắt kịp và nhận dấu xóa.

Một số topic có thể dùng cả compact và delete trong cleanup.policy. Khi đó, compaction vẫn giữ trạng thái mới nhất theo key, đồng thời chính sách retention theo thời gian hoặc dung lượng có thể loại bỏ các segment cũ. Cần đánh giá cả hai cơ chế khi thiết kế khả năng khôi phục trạng thái.

delete.retention.ms có ý nghĩa đặc biệt với consumer duy trì state cục bộ. Nếu consumer đã đọc một giá trị cũ, sau đó ngừng hoạt động lâu hơn thời gian tombstone được giữ, consumer đó có thể bỏ lỡ dấu xóa khi quay lại. Consumer đang duy trì trạng thái cần có kế hoạch bắt kịp, dựng lại state hoặc đồng bộ lại khi không bảo đảm được thời gian xử lý.

## 5. Producer gửi tombstone bằng Java

Với Kafka Java Producer, gửi tombstone bằng cách tạo ProducerRecord có key hợp lệ và value Java null. Ví dụ sau dùng StringSerializer cho cả key và value:

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class CustomerStatePublisher {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {
            ProducerRecord<String, String> tombstone =
                new ProducerRecord<>(
                    "customers.state",
                    "customer-42",
                    null
                );

            producer.send(tombstone).get();
        }
    }
}
~~~

Trong ví dụ:

- customers.state là topic đã được cấu hình compaction.
- customer-42 là key của mục dữ liệu cần xóa.
- null là value null thực sự, tạo tombstone.
- send(...).get() chờ broker xác nhận kết quả gửi để ví dụ dễ quan sát; ứng dụng thực tế có thể dùng callback hoặc xử lý bất đồng bộ và cần xử lý lỗi gửi.

Nếu dùng serializer tùy chỉnh, cần bảo đảm serializer giữ đúng ngữ nghĩa null thay vì biến null thành chuỗi "null" hoặc một payload đánh dấu riêng. Consumer cũng cần nhận được value null từ deserializer để nhận diện tombstone.

## 6. Consumer áp dụng tombstone vào trạng thái

Consumer đọc compacted topic thường duy trì một bản đồ trạng thái theo key. Khi nhận record có value khác null, consumer thêm mới hoặc cập nhật giá trị. Khi nhận tombstone, consumer xóa key khỏi bản đồ.

Ví dụ logic xử lý:

~~~java
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerRecord;

static void applyRecord(
        ConsumerRecord<String, String> record,
        Map<String, String> stateStore) {
    String key = record.key();
    String value = record.value();

    if (key == null) {
        // Không thể xác định thực thể theo key.
        // Xử lý theo quy ước riêng của ứng dụng.
    } else if (value == null) {
        stateStore.remove(key);
    } else {
        stateStore.put(key, value);
    }
}
~~~

Đoạn mã nhận record đã được poll và một Map đại diện cho state store của ứng dụng. Nếu consumer ghi state ra cơ sở dữ liệu, cần phối hợp cập nhật dữ liệu và tiến độ offset phù hợp để tránh tình huống đã commit offset nhưng chưa xóa dữ liệu, hoặc đã xóa dữ liệu nhưng xử lý lại record.

Trong Kafka Streams, tombstone được biểu diễn bằng null value của một key. Với KTable, record có value null được hiểu là xóa key khỏi bảng. Các phép biến đổi và phép join trên bảng cần tính đến khả năng key biến mất sau khi nhận tombstone.

Consumer không nên giả định rằng mỗi key chỉ xuất hiện một lần. Trước khi compaction hoàn tất, nó có thể đọc nhiều phiên bản của cùng key rồi mới đến tombstone. Logic dựng trạng thái cần áp dụng record theo thứ tự offset trong từng partition và chấp nhận cập nhật lặp theo cách an toàn.

## 7. Tombstone không giống sự kiện nghiệp vụ xóa

Cần phân biệt tombstone với một sự kiện nghiệp vụ như CustomerDeleted.

~~~text
CustomerDeleted event:
key   = customer-42
value = {"eventType":"CustomerDeleted","reason":"requested"}

Tombstone:
key   = customer-42
value = null
~~~

CustomerDeleted là một sự kiện có payload, mô tả việc khách hàng đã bị xóa theo nghiệp vụ. Nó có thể mang lý do, thời điểm, người thực hiện và các thông tin cần cho kiểm toán. Nếu được lưu trong topic lịch sử sự kiện không compaction, sự kiện này là một phần của lịch sử.

Tombstone là dấu xóa của một key trong topic compacted. Nó phục vụ việc duy trì trạng thái mới nhất và cho phép cleaner loại các phiên bản cũ của key. Sau thời gian giữ tombstone, chính dấu xóa có thể biến mất khỏi log.

Vì vậy, nếu cần lịch sử nghiệp vụ hoặc bằng chứng kiểm toán, không nên chỉ dựa vào tombstone trong compacted topic. Có thể phát sự kiện CustomerDeleted vào topic sự kiện nghiệp vụ và đồng thời phát tombstone vào topic trạng thái đã compact để các consumer dựng projection biết cần loại key.

## 8. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gửi value là chuỗi "null" | Consumer nhận payload văn bản, cleaner không xem đó là tombstone | Gửi value null thực sự |
| Gửi value rỗng hoặc JSON null | Record vẫn có payload, không có ngữ nghĩa tombstone | Phân biệt null ở cấp Kafka record với dữ liệu JSON |
| Gửi tombstone với key null | Không xác định được key cần xóa | Luôn cung cấp key khác null |
| Topic không bật cleanup.policy=compact | Không có hành vi compaction theo key như mong đợi | Kiểm tra cấu hình topic |
| Cùng một key bị định tuyến sang nhiều partition | Compaction từng partition không xóa phiên bản ở partition khác | Dùng partitioning ổn định theo key |
| Consumer bỏ lỡ tombstone | State cục bộ có thể giữ dữ liệu đã bị xóa | Bắt kịp trong thời gian giữ tombstone hoặc dựng lại state |
| Dùng tombstone làm lịch sử kiểm toán duy nhất | Dấu xóa có thể bị dọn sau thời gian retention | Lưu sự kiện nghiệp vụ ở nguồn lịch sử phù hợp |

Khi kiểm tra một lỗi xóa key, hãy xác minh lần lượt: key thực tế của record, value có null thật hay không, topic có bật compaction không, record nằm ở partition nào, consumer có đọc đến offset tombstone chưa và thời gian giữ tombstone có đủ cho consumer không.

## 9. Tự kiểm tra cách hiểu

1. Tombstone có cấu trúc thế nào? — Một record có key khác null và value null.
2. Value là chuỗi "null" có phải tombstone không? — Không, đó là payload chứa ký tự.
3. Tombstone có xóa dữ liệu trên đĩa ngay khi producer gửi không? — Không. Log cleaner thực hiện compaction bất đồng bộ.
4. Compaction có hợp nhất cùng key trên tất cả partition của topic không? — Không. Compaction xử lý từng partition.
5. Vì sao cần delete.retention.ms? — Để giữ dấu xóa đủ lâu cho consumer có cơ hội nhận và áp dụng nó.
6. Tombstone có thay thế sự kiện CustomerDeleted trong lịch sử nghiệp vụ không? — Không. Tombstone phục vụ xóa trạng thái theo key trong compacted log; sự kiện nghiệp vụ có payload và ý nghĩa lịch sử riêng.

Khi dùng Kafka để lưu trạng thái mới nhất theo key, tombstone là tín hiệu quan trọng giúp cả log compacted và các consumer duy trì cùng một cách hiểu về việc một mục dữ liệu đã bị xóa. Hãy bảo đảm key được định tuyến ổn định, value null được giữ nguyên qua serializer, topic bật compaction và consumer xử lý dấu xóa trong khoảng thời gian cấu hình.

