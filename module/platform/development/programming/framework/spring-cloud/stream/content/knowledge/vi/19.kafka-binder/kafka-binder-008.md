# Tombstone, KafkaNull và sự kiện xóa dữ liệu

Trong Kafka, một bản ghi có **key khác null** và **value bằng null** được gọi là tombstone. Trên topic bật log compaction, tombstone biểu thị rằng giá trị hiện tại của key đó đã bị xóa. Đây là cách Kafka truyền thay đổi trạng thái theo key, chẳng hạn xóa khách hàng khỏi topic trạng thái đã compact.

Spring Messaging không cho phép một `Message<?>` có payload Java là `null`. Vì vậy Spring for Apache Kafka cung cấp `KafkaNull.INSTANCE` làm giá trị đại diện khi gửi tombstone qua một Spring Message. Kafka binder chuyển sentinel này thành Kafka record có value null. Khi nhận bằng Spring Cloud Stream function, tombstone được biểu diễn bằng payload kiểu `KafkaNull`; khi dùng Kafka listener API trực tiếp, payload có thể là null và cần đánh dấu `@Payload(required = false)`.

Tombstone phù hợp với topic lưu trạng thái mới nhất theo key. Nó không thay thế event nghiệp vụ có nội dung như `CustomerDeleted` nếu các consumer cần biết ai xóa, vì sao xóa hoặc thời điểm xóa.

## 1. Tombstone là gì?

Kafka record có cấu trúc chính gồm topic, partition, key, value, timestamp và headers. Với topic compacted, key xác định thực thể hoặc mục trạng thái, còn value chứa trạng thái mới nhất.

~~~text
Key                 Value
customer-42         { "name": "An", "status": "ACTIVE" }
customer-42         { "name": "An", "status": "SUSPENDED" }
customer-42         null       <- tombstone: xóa key customer-42
~~~

Tombstone là một record thật được ghi vào log với key và value null. Nó không phải thao tác xóa vật lý ngay tại thời điểm publish. Kafka log cleaner xử lý compaction ở nền; sau khi compact, các giá trị cũ của key bị loại và tombstone cũng được giữ trong một khoảng thời gian trước khi có thể bị loại bỏ.

Các điều kiện quan trọng:

- Key phải khác null để Kafka biết cần xóa trạng thái của key nào.
- Value phải là null thực sự ở tầng Kafka record.
- Tombstone phải dùng đúng key và cách serialize key giống các record trạng thái trước đó.
- Topic phải có cleanup policy bao gồm `compact`.
- Consumer phải hiểu null value là tín hiệu xóa, không phải một object trạng thái thông thường.

Nếu gửi record không có key và value null, Kafka không có định danh để xóa một mục cụ thể. Nếu gửi key đúng nhưng value là chuỗi rỗng hoặc JSON `null`, đó vẫn là một value có bytes, không phải tombstone.

## 2. Log compaction giữ trạng thái mới nhất theo key

Log compaction là cơ chế dọn log theo key. Kafka giữ bản ghi mới nhất cho mỗi key trong các segment đã được compact, đồng thời giữ thứ tự offset của các record còn lại. Nó khác với retention theo thời gian/kích thước vốn xóa cả segment cũ.

Ví dụ log trước khi compact:

~~~text
Offset  Key             Value
100     customer-42     ACTIVE
101     customer-77     ACTIVE
102     customer-42     SUSPENDED
103     customer-88     ACTIVE
104     customer-42     null
105     customer-77     PREMIUM
~~~

Sau khi log cleaner compact các segment phù hợp, trạng thái cuối cùng có thể được biểu diễn bởi:

~~~text
Key             Value
customer-77     PREMIUM
customer-88     ACTIVE
~~~

Các record cũ của `customer-42` và tombstone của nó đã được xử lý để key không còn trạng thái hiện hành. Việc này diễn ra bất đồng bộ; không được giả định rằng record cũ biến mất ngay sau khi gửi tombstone.

Topic có thể bật compaction bằng cấu hình:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic customers.state \
  --partitions 3 \
  --replication-factor 1 \
  --config cleanup.policy=compact \
  --config delete.retention.ms=86400000
~~~

Trong ví dụ, `cleanup.policy=compact` bật log compaction. `delete.retention.ms=86400000` đặt thời gian giữ tombstone là 24 giờ. Đây là giá trị minh họa; cần chọn theo thời gian consumer có thể bị offline và thời gian cần để dựng lại snapshot.

Có thể kiểm tra cấu hình topic:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name customers.state --describe
~~~

Nếu dùng `cleanup.policy=compact,delete`, Kafka áp dụng cả compaction và retention xóa segment theo thời gian/kích thước. Điều này có thể làm mất cả trạng thái mới nhất của key khi segment hết hạn. Với topic làm nguồn trạng thái chuẩn để dựng lại projection, chỉ bật `compact` thường dễ dự đoán hơn; chỉ kết hợp `delete` khi retention giới hạn là một quyết định nghiệp vụ có chủ đích.

## 3. Tombstone khác với các dạng “rỗng” khác

Các payload sau có ý nghĩa khác nhau:

| Giá trị ghi vào Kafka | Có phải tombstone? | Ý nghĩa |
|---|---|---|
| Value null, key có giá trị | Có | Xóa trạng thái của key trong topic compacted |
| Value là chuỗi rỗng `""` | Không | Một value có độ dài 0 |
| Value là JSON `null` | Không | Bytes chứa ký tự JSON null |
| Value là JSON object rỗng `{}` | Không | Một object có nội dung rỗng |
| Key null, value null | Không phải tombstone hữu ích | Không xác định được key cần xóa |
| Value không deserialize được | Không nhất thiết | Có thể là lỗi serializer/deserializer |

Không dùng một DTO như `CustomerDeleted` làm tombstone nếu mục tiêu là ghi value null. DTO đó serialize thành JSON bytes và Kafka sẽ xem nó là một value bình thường. Ngược lại, nếu consumer cần lý do xóa, thời điểm, actor hoặc thông tin tuân thủ, hãy phát một event nghiệp vụ có payload thay vì chỉ gửi tombstone.

## 4. Phân biệt tombstone với event nghiệp vụ xóa

Tombstone là tín hiệu cập nhật trạng thái theo key. Event `CustomerDeleted` là một sự kiện nghiệp vụ có dữ liệu và có thể được lưu giữ để audit.

| Tiêu chí | Tombstone | `CustomerDeleted` |
|---|---|---|
| Kafka value | null | Payload không null |
| Key | ID của thực thể bị xóa | Có thể dùng cùng customer ID |
| Mục tiêu | Xóa giá trị hiện hành trong compacted topic | Công bố sự thật nghiệp vụ đã xóa |
| Dữ liệu lý do/actor | Không có trong value | Có thể chứa deletedAt, actor, reason |
| Compaction | Xóa trạng thái key cũ | Record event vẫn là một value; không tự xóa trạng thái |
| Audit/replay nghiệp vụ | Không đủ thông tin một mình | Phù hợp hơn nếu contract có metadata cần thiết |

Một kiến trúc có thể phát cả hai:

~~~text
Command xóa khách hàng
        |
        v
Customer service
        |
        +----> customers.events
        |        CustomerDeleted {
        |          eventId, customerId,
        |          deletedAt, reason, actor
        |        }
        |
        +----> customers.state (compacted)
                 key = customerId
                 value = null
~~~

Topic `customers.events` lưu lịch sử sự kiện theo contract. Topic `customers.state` lưu trạng thái mới nhất theo key; tombstone xóa trạng thái khách hàng khỏi snapshot compacted. Hai topic có mục đích khác nhau và không nên dùng lẫn nhau.

## 5. Gửi tombstone bằng KafkaNull qua Spring Cloud Stream

Vì Spring Messaging không cho phép payload null trong `Message<?>`, dùng `KafkaNull.INSTANCE`. Kafka binder chuyển sentinel thành record có value null.

Ví dụ publisher dùng `StreamBridge`:

DTO trạng thái là contract được serialize thành value JSON khi publish record thông thường:

~~~java
public record CustomerState(
    String customerId,
    String name,
    String status
) {}
~~~

Đặt record này trong file `CustomerState.java`. Các ví dụ publisher và consumer bên dưới dùng cùng DTO trong một package contract chung.

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.KafkaNull;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CustomerStatePublisher {

    private final StreamBridge streamBridge;

    public CustomerStatePublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(CustomerState state) {
        Message<CustomerState> message = MessageBuilder
            .withPayload(state)
            .setHeader(KafkaHeaders.KEY, state.customerId())
            .build();

        return streamBridge.send("customerState-out-0", message);
    }

    public boolean delete(String customerId) {
        Message<?> tombstone = MessageBuilder
            .withPayload(KafkaNull.INSTANCE)
            .setHeader(KafkaHeaders.KEY, customerId)
            .build();

        return streamBridge.send("customerState-out-0", tombstone);
    }

}
~~~

Trong Spring Kafka từ phiên bản 2.9, `KafkaHeaders.KEY` là header dùng để đặt record key; các phiên bản cũ có thể dùng `KafkaHeaders.MESSAGE_KEY`. Dùng đúng hằng số theo phiên bản Spring Kafka được quản lý bởi BOM của ứng dụng. Key trong tombstone phải giống key đã dùng khi publish trạng thái trước đó, bao gồm cả kiểu và cách serialize.

Cấu hình output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: customerState-out-0
      bindings:
        customerState-out-0:
          destination: customers.state
          content-type: application/json
~~~

`StreamBridge.send` trả về boolean cho việc gửi message vào binding/channel. Không xem giá trị true là bằng chứng phổ quát rằng record đã được broker lưu bền vững. Nếu cần xác nhận kết quả publish, cấu hình cơ chế producer acknowledgment/record metadata phù hợp với Kafka binder và quan sát kết quả gửi.

Nếu dùng `KafkaTemplate` trực tiếp, Spring Kafka cho phép gửi null value bằng overload `send(topic, key, null)`. Với overload nhận một Spring `Message<?>`, dùng `KafkaNull.INSTANCE` thay cho payload null.

## 6. Nhận tombstone trong Spring Cloud Stream function

Khi nhận qua Spring Cloud Stream Kafka binder, payload tombstone được biểu diễn bằng kiểu `org.springframework.kafka.support.KafkaNull`. Vì thế function nên nhận `Message<T>` để vừa đọc payload vừa đọc key header.

Repository là adapter của ứng dụng; ví dụ dưới đây giả định nó cập nhật projection theo customer ID:

~~~java
public interface CustomerRepository {
    void save(CustomerState state);
    void deleteById(String customerId);
}
~~~

Đặt interface trong file `CustomerRepository.java`; implementation thực tế có thể dùng Spring Data, JDBC hoặc một kho projection khác.

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.KafkaNull;
import org.springframework.messaging.Message;

@Configuration
public class CustomerStateConsumers {

    @Bean
    Consumer<Message<CustomerState>> customerStateConsumer(
            CustomerRepository repository) {

        return message -> {
            Object payload = message.getPayload();
            String key = (String) message.getHeaders()
                .get(KafkaHeaders.RECEIVED_KEY);

            if (payload instanceof KafkaNull) {
                if (key == null || key.isBlank()) {
                    throw new IllegalArgumentException(
                        "Tombstone record is missing its Kafka key"
                    );
                }

                repository.deleteById(key);
                return;
            }

            CustomerState state = (CustomerState) payload;
            repository.save(state);
        };
    }

}
~~~

`KafkaHeaders.RECEIVED_KEY` là header key nhận vào trong Spring Kafka từ phiên bản 2.9. Với phiên bản cũ, tên hằng số có thể là `KafkaHeaders.RECEIVED_MESSAGE_KEY`. Kiểu Java của key phụ thuộc key deserializer; ví dụ dùng `String`, còn key dạng byte array cần giải mã tương ứng.

Cấu hình consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: customerStateConsumer

    stream:
      bindings:
        customerStateConsumer-in-0:
          destination: customers.state
          group: customer-state-projection
          content-type: application/json
~~~

Không khai báo tham số chỉ là `CustomerState` nếu function cần phân biệt tombstone và truy cập key. Dùng `Message<CustomerState>` cho phép đọc cả payload sentinel lẫn header. Với các phiên bản binder khác nhau, hãy xác minh cách converter chuyển tombstone bằng integration test.

### Nếu dùng Kafka listener API trực tiếp

Khi dùng `@KafkaListener` thay vì Spring Cloud Stream function, Spring Kafka có thể truyền payload null thật. Đánh dấu tham số payload là không bắt buộc và đọc key từ header:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class CustomerTombstoneListener {

    private final CustomerRepository customerRepository;

    public CustomerTombstoneListener(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @KafkaListener(
        id = "customer-tombstone-listener",
        topics = "customers.state"
    )
    public void listen(
            @Payload(required = false) CustomerState value,
            @Header(KafkaHeaders.RECEIVED_KEY) String key) {

        if (value == null) {
            customerRepository.deleteById(key);
        } else {
            customerRepository.save(value);
        }
    }
}
~~~

Ở API này, tham số `value` là null khi nhận tombstone; nó không phải object `KafkaNull`. Đừng trộn hai cách biểu diễn: Spring Cloud Stream function dùng message payload sentinel, còn listener method có thể dùng `@Payload(required = false)` để nhận null.

## 7. Key phải ổn định từ lúc ghi đến lúc xóa

Compaction hoạt động theo key trong từng partition. Vì vậy producer cần dùng cùng key cho mọi phiên bản trạng thái và tombstone:

~~~text
customer-42 -> ACTIVE
customer-42 -> SUSPENDED
customer-42 -> null       (delete)
~~~

Nếu record trạng thái dùng key `customer-42` nhưng tombstone dùng key `42`, Kafka xem đây là hai key khác nhau và không xóa trạng thái cũ.

Các điểm phải thống nhất:

- Key đại diện cho định danh nghiệp vụ ổn định, ví dụ customer ID.
- Key serializer và định dạng bytes giống nhau giữa record trạng thái và tombstone.
- Producer dùng cùng partitioning strategy để key được ghi vào cùng partition.
- Không đổi kiểu key từ String sang Long hoặc đổi cách chuẩn hóa chuỗi mà không có kế hoạch migration.
- Không dùng header nghiệp vụ tùy chỉnh thay cho Kafka record key nếu binder chưa được cấu hình ánh xạ header đó thành key.

Khi thay đổi số partition, partitioner mặc định có thể ánh xạ một key sang partition khác. Compaction chỉ xử lý key trong từng partition, không gộp các record cùng key ở hai partition. Với compacted topic đang lưu trạng thái, tăng partition có thể khiến giá trị cũ còn ở partition trước trong khi giá trị mới/tombstone vào partition khác. Hãy lập kế hoạch migration hoặc dựng lại topic nếu thay đổi partition count ảnh hưởng đến key mapping.

## 8. Tombstone và Kafka Streams KTable

Kafka Streams dùng semantics key/value để biểu diễn bảng trạng thái. Với `KTable<K, V>`, record có value null được hiểu là xóa key khỏi bảng. Điều này phù hợp với tombstone của compacted topic.

~~~java
KTable<String, CustomerState> customers =
    builder.table("customers.state");
~~~

Nếu topic phát:

~~~text
customer-42 -> CustomerState(...)
customer-42 -> null
~~~

thì `KTable` không còn hàng cho `customer-42` sau khi xử lý tombstone. State store và các luồng changelog liên quan cũng phản ánh việc xóa theo semantics của Kafka Streams.

Cần phân biệt `KTable` với `KStream`: KTable biểu diễn trạng thái mới nhất theo key, còn KStream biểu diễn chuỗi record. Trong KStream, record null-value vẫn là record được phát ra và toán tử cần xử lý null một cách tường minh. Không truy cập field của value trước khi kiểm tra null.

Tombstone cũng được dùng trong changelog topic của state store để ghi nhận việc xóa key. Không tự xóa record changelog hoặc compacted topic bằng thao tác ngoài Kafka Streams khi ứng dụng đang quản lý state store; hãy dùng API và quy trình migration phù hợp.

## 9. Tombstone được giữ bao lâu?

Kafka không loại tombstone ngay khi producer gửi. Log cleaner chạy ở nền và chỉ compact các segment đủ điều kiện. Sau khi tombstone được giữ ít nhất trong khoảng `delete.retention.ms`, marker có thể bị loại trong một lần compaction cùng với các giá trị cũ của key.

`delete.retention.ms` cũng đặt giới hạn thời gian mà một consumer dựng snapshot từ offset 0 phải hoàn thành để bảo đảm nhìn thấy các tombstone cần thiết. Nếu consumer chậm hơn cửa sổ này, tombstone có thể bị cleaner loại trước khi consumer đọc tới; local state của consumer có thể giữ dữ liệu đã bị xóa.

Cần chọn thời gian giữ tombstone dựa trên:

- Thời gian tối đa consumer có thể offline.
- Kích thước topic và tốc độ consumer cần để scan lại từ đầu.
- Thời gian phục hồi sau sự cố hoặc nâng cấp.
- Chính sách replay và cách dựng lại projection.
- Mức độ chấp nhận việc dựng snapshot không đầy đủ.

Đối với consumer có local database, hãy có quy trình bootstrap/snapshot hoặc rebuild nếu nó vượt quá cửa sổ đọc tombstone. Không giả định một consumer có thể offline vô thời hạn rồi đọc lại compacted topic và luôn thấy mọi delete marker trong lịch sử.

## 10. Tombstone không thay thế xóa dữ liệu ở hệ thống khác

Gửi tombstone chỉ ghi một record vào Kafka. Nó không tự xóa row trong database, cache, search index hoặc object storage. Mỗi consumer cần nhận tombstone và thực hiện hành động xóa trong projection của chính nó.

Ví dụ một sự kiện xóa khách hàng có thể đi qua nhiều projection:

~~~text
customers.state
      |
      +----> customer-search-index: delete document
      |
      +----> customer-cache: evict key
      |
      +----> customer-reporting: remove current row
      |
      +----> customer-state-store: remove key
~~~

Nếu một consumer lỗi hoặc không nhận tombstone, dữ liệu ở projection đó có thể còn tồn tại. Cần theo dõi consumer lag, lỗi xử lý, DLQ/quarantine và khả năng replay. Với dữ liệu nhạy cảm hoặc yêu cầu xóa theo quy định, cần một quy trình xóa có xác nhận, audit và đối soát tất cả bản sao; tombstone là tín hiệu truyền trạng thái, không phải bằng chứng mọi hệ thống đã xóa xong.

## 11. Kiểm thử tombstone end-to-end

Kiểm thử nên xác nhận cả record key/value trên Kafka và hành vi consumer.

### Kiểm thử gửi

Dùng KafkaTemplate để tạo hai trạng thái và một tombstone:

~~~java
// Trong test method khai báo throws Exception để chờ kết quả gửi.
kafkaTemplate.send(
    "customers.state",
    "customer-42",
    new CustomerState("customer-42", "An", "ACTIVE")
).get();

kafkaTemplate.send(
    "customers.state",
    "customer-42",
    new CustomerState("customer-42", "An", "SUSPENDED")
).get();

kafkaTemplate.send(
    "customers.state",
    "customer-42",
    null
).get();
~~~

Overload `send(topic, key, value)` của `KafkaTemplate` cho phép value null. Nếu gửi bằng Spring Messaging `Message<?>`, dùng `KafkaNull.INSTANCE` vì Spring Message không chấp nhận payload null.

### Kiểm thử nhận

- Gửi state record và xác nhận consumer tạo/cập nhật projection.
- Gửi tombstone cùng key và xác nhận consumer xóa projection.
- Gửi tombstone không có key và xác nhận ứng dụng từ chối hoặc cảnh báo.
- Gửi chuỗi rỗng hoặc JSON `null` và xác nhận chúng không bị hiểu nhầm là tombstone.
- Gửi cùng key với serializer/partitioner đã dùng trong production.
- Khởi động lại consumer và xác nhận state được dựng lại đúng theo topic compacted.

### Kiểm thử compaction

Compaction chạy bất đồng bộ, vì vậy không kiểm tra rằng record cũ biến mất ngay sau khi gửi tombstone. Kiểm thử logic consumer bằng cách đọc tombstone trước; kiểm thử compaction riêng bằng topic thử nghiệm, cleaner và thời gian chờ phù hợp. Với test tự động, ưu tiên xác minh consumer nhận value null và xóa projection thay vì phụ thuộc vào thời điểm log cleaner chạy.

Dùng Testcontainers Kafka hoặc broker Kafka tích hợp để kiểm tra serialization, header key, tombstone value và binder converter. Test unit chỉ gọi method với `KafkaNull.INSTANCE` không chứng minh binder thật sự ghi value null vào Kafka.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Consumer không xóa trạng thái | Producer gửi DTO `CustomerDeleted` thay vì null value | Dùng `KafkaNull.INSTANCE` hoặc KafkaTemplate value null |
| Tombstone không xóa key cũ | Key khác key của record trạng thái | Dùng cùng key và serializer |
| Function ném lỗi khi nhận tombstone | Code giả định payload luôn là DTO | Nhận `Message<T>` và kiểm tra `KafkaNull` |
| Consumer listener không nhận tombstone | Payload bị yêu cầu bắt buộc | Dùng `@Payload(required = false)` với Kafka listener trực tiếp |
| Chuỗi rỗng bị xóa nhầm | Code coi empty string là null | Phân biệt zero-byte value với Kafka null |
| Consumer dựng state bị thiếu delete | Consumer offline lâu hơn `delete.retention.ms` | Điều chỉnh retention và quy trình snapshot/rebuild |
| Compaction chưa loại record cũ | Log cleaner chưa xử lý segment | Chờ compaction; không kỳ vọng xóa tức thời |
| Một số key còn bản cũ sau tăng partition | Key mới chuyển sang partition khác | Lập kế hoạch migration/rebuild compacted topic |
| Audit không biết ai xóa và vì sao | Chỉ phát tombstone | Phát thêm event nghiệp vụ `CustomerDeleted` |

## 13. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với topic trạng thái khách hàng:

1. Tạo topic `customers.state` với `cleanup.policy=compact`.
2. Định nghĩa `CustomerState` và thống nhất customer ID làm Kafka key.
3. Viết publisher dùng StreamBridge, gửi state record với `KafkaHeaders.KEY`.
4. Viết phương thức delete dùng `KafkaNull.INSTANCE` và giữ nguyên key.
5. Cấu hình output binding trỏ tới `customers.state`.
6. Viết Spring Cloud Stream consumer nhận `Message<CustomerState>`.
7. Kiểm tra payload `KafkaNull`, đọc `KafkaHeaders.RECEIVED_KEY` và xóa projection tương ứng.
8. Gửi state, update state và tombstone cho cùng một customer ID.
9. Xác nhận consumer xóa đúng key; kiểm tra key khác vẫn còn.
10. Thử chuỗi rỗng, JSON null và tombstone thiếu key để phân biệt semantics.
11. Quan sát log cleaner và thử dựng snapshot trong cửa sổ `delete.retention.ms`.
12. Phát thêm `CustomerDeleted` event nếu cần audit, reason hoặc actor.
13. Chạy integration test với Kafka binder thật và ghi lại phiên bản Spring Cloud Stream/Spring Kafka.

Hoàn thành bài khi có thể giải thích record key/value của tombstone; gửi tombstone bằng `KafkaNull.INSTANCE`; nhận và nhận diện tombstone qua Spring Cloud Stream; xóa projection theo key; cấu hình compacted topic; và thiết kế retention/replay sao cho consumer không bỏ lỡ delete marker.

## 14. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Tombstone Records](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/tombstone.html) — cách nhận tombstone trong Spring Cloud Stream function.
- [Spring for Apache Kafka — Null Payloads and Log Compaction of Tombstone Records](https://docs.spring.io/spring-kafka/reference/kafka/tombstones.html) — `KafkaNull.INSTANCE`, gửi null payload và nhận tombstone.
- [Apache Kafka — Log Compaction](https://kafka.apache.org/documentation/#compaction) — semantics compaction, delete marker và giới hạn consumer scan.
- [Apache Kafka — Topic Configs](https://kafka.apache.org/43/configuration/topic-configs/) — `cleanup.policy`, `delete.retention.ms` và các cấu hình topic.
- [Spring Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html) — header key gửi và nhận của Kafka.
- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html) — cấu hình và tích hợp Kafka binder.

