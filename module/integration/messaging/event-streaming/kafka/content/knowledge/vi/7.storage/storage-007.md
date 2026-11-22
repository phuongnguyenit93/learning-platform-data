# Log compaction và trạng thái mới nhất theo key

Kafka thường được dùng để lưu một luồng sự kiện có lịch sử theo thời gian. Tuy nhiên, có những topic chủ yếu biểu diễn trạng thái hiện tại của từng thực thể, chẳng hạn hồ sơ khách hàng, cấu hình thiết bị hoặc thông tin tài khoản. Nếu lưu mọi phiên bản mãi mãi, topic có thể tăng dung lượng dù ứng dụng chỉ cần giá trị mới nhất của mỗi key để dựng lại trạng thái.

**Log compaction** là cơ chế dọn dẹp log theo key. Kafka giữ lại bản ghi mới nhất theo thứ tự offset của từng key trong mỗi partition và có thể loại bỏ các phiên bản cũ hơn khi log cleaner chạy. Nhờ vậy, một compacted topic có thể hoạt động như changelog để khôi phục trạng thái hiện tại mà không cần giữ toàn bộ lịch sử thay đổi.

Compaction không xóa bản ghi ngay khi producer ghi phiên bản mới. Nó chạy nền, có độ trễ và chịu ảnh hưởng bởi segment, cấu hình topic cùng năng lực log cleaner. Để thiết kế đúng, cần hiểu key, tombstone, offset, retention và giới hạn của việc khôi phục state từ một log đã compact.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích mục đích và cách hoạt động của log compaction.
- Phân biệt compacted topic với event log lưu toàn bộ lịch sử.
- Chọn key ổn định để biểu diễn một thực thể hoặc một mục trạng thái.
- Dùng tombstone để biểu diễn thao tác xóa một key.
- Hiểu vì sao compaction tạo khoảng trống offset nhưng không đánh số lại log.
- Cấu hình cleanup.policy, các tham số compaction và retention.
- Xây dựng producer Java/Spring Kafka phát bản cập nhật và tombstone.
- Dựng lại trạng thái từ compacted topic và nhận diện các rủi ro khi replay.

## 1. Event log và changelog trạng thái khác nhau thế nào?

Hãy xét một khách hàng có ba lần thay đổi hồ sơ:

| Thứ tự ghi | Key | Value |
|---:|---|---|
| 1 | customer-42 | {"name":"An","tier":"Silver"} |
| 2 | customer-42 | {"name":"An","tier":"Gold"} |
| 3 | customer-42 | {"name":"An","tier":"Platinum"} |

Một event log lưu toàn bộ ba thay đổi vì mỗi thay đổi đều có ý nghĩa lịch sử. Một compacted topic có thể dần loại bỏ hai phiên bản cũ và giữ phiên bản mới nhất cho key customer-42.

Hai cách lưu trữ phục vụ mục tiêu khác nhau:

| Tiêu chí | Event log với cleanup.policy=delete | Compacted topic |
|---|---|---|
| Mục đích | Lưu lịch sử sự kiện trong một cửa sổ thời gian | Giữ trạng thái mới nhất theo key |
| Bản ghi cũ | Tồn tại đến khi segment hết retention | Có thể bị loại bỏ khi cleaner compact |
| Khôi phục trạng thái hiện tại | Phải đọc và áp dụng lịch sử còn lưu | Có thể đọc log đã compact để dựng state |
| Truy vấn lịch sử mọi lần thay đổi | Phù hợp hơn nếu retention đủ dài | Không được bảo đảm |
| Xóa một thực thể | Phát sự kiện nghiệp vụ hoặc xử lý theo logic riêng | Có thể phát tombstone cho key |

Một topic compacted vẫn là log append-only về mặt cách ghi: producer tiếp tục append record mới. Compaction chỉ dọn các phiên bản cũ trong nền. Vì vậy, trong một khoảng thời gian, topic có thể vẫn chứa nhiều phiên bản của cùng key.

Không nên dùng compacted topic làm kho audit nếu yêu cầu phải giữ mọi lần thay đổi, ai thực hiện, lý do thay đổi và thời điểm nghiệp vụ. Có thể lưu event log riêng cho lịch sử và dùng compacted topic làm changelog hoặc state snapshot cho hệ thống cần trạng thái hiện tại.

## 2. Log cleaner thực hiện compaction như thế nào?

Kafka chạy log cleaner ở broker để compact các log có cấu hình cleanup.policy=compact. Cleaner xem xét các segment đã đóng, xác định phần log cần dọn và xây dựng ánh xạ key đến offset mới nhất trong vùng đang được compact. Những record cũ hơn có cùng key có thể bị loại bỏ khi segment được viết lại.

Có thể hình dung đơn giản:

~~~mermaid
flowchart TD
    A["Producer append record"] --> B["Partition log"]
    B --> C["Active segment"]
    B --> D["Closed segments"]
    D --> E["Log cleaner"]
    E --> F["Tìm offset mới nhất theo key"]
    F --> G["Viết lại segment"]
    G --> H["Giữ phiên bản mới nhất"]
    G --> I["Giữ tombstone trong thời gian quy định"]
~~~

Ví dụ, log của một partition trước khi compaction:

| Offset | Key | Value |
|---:|---|---|
| 0 | customer-42 | Silver |
| 1 | customer-99 | Bronze |
| 2 | customer-42 | Gold |
| 3 | customer-42 | Platinum |
| 4 | customer-99 | Silver |

Sau khi cleaner compact vùng log chứa các record này, kết quả có thể chỉ còn:

| Offset gốc | Key | Value |
|---:|---|---|
| 1 | customer-99 | Bronze |
| 3 | customer-42 | Platinum |
| 4 | customer-99 | Silver |

Record offset 0 và 2 đã bị loại bỏ vì có phiên bản mới hơn của cùng key. Offset 1, 3 và 4 vẫn giữ số offset ban đầu. Kafka không đánh lại số offset thành 0, 1, 2.

Đây là ví dụ rút gọn. Trong thực tế, cleaner xử lý theo segment và vùng log đủ điều kiện; không có cam kết mọi bản ghi cũ biến mất ngay sau khi producer gửi giá trị mới.

### Active segment và độ trễ compaction

Segment đang active tiếp tục nhận record nên chưa được cleaner xử lý như các segment đã đóng. Segment chỉ đóng khi đạt điều kiện roll, thường liên quan đến segment.bytes hoặc segment.ms. Vì vậy, tốc độ compaction chịu ảnh hưởng bởi cách segment được roll và lượng dữ liệu phát sinh.

Ngoài ra, cleaner chạy nền và phải chia sẻ tài nguyên CPU, bộ nhớ và I/O với broker. Nếu log phát sinh nhanh hoặc cleaner không đủ năng lực, dữ liệu cũ có thể tồn tại lâu hơn dự kiến.

Các yếu tố thường ảnh hưởng:

- Kích thước và thời gian roll segment.
- Tỷ lệ dữ liệu đã ghi nhưng chưa compact.
- Số cleaner thread và tài nguyên broker dành cho cleaner.
- Kích thước bộ nhớ deduplication map của cleaner.
- Lượng dữ liệu và số lượng key khác nhau trong các segment cần compact.

Không nên xem compaction là thao tác đồng bộ được hoàn tất ngay khi producer nhận ProduceResponse.

## 3. Key là đơn vị trạng thái mà Kafka compact

Kafka compact theo key trong từng partition. Mọi phiên bản của cùng một thực thể cần dùng cùng một key và phải được định tuyến vào cùng partition nếu muốn compaction giữ một trạng thái duy nhất cho thực thể đó.

Ví dụ, topic customer-state có thể dùng customerId làm key:

- customer-42 đại diện hồ sơ khách hàng 42.
- device-17 đại diện trạng thái thiết bị 17.
- account-9001 đại diện trạng thái tài khoản 9001.

Key phải ổn định giữa các producer. Nếu một producer dùng customer-42, producer khác dùng CUSTOMER-42, Kafka xem đây là hai key khác nhau nếu byte sau serialize khác nhau. Compaction sẽ giữ trạng thái riêng cho từng byte key.

Cần thống nhất:

- Kiểu dữ liệu và serializer của key.
- Quy tắc chữ hoa/thường, Unicode và chuẩn hóa chuỗi.
- Phạm vi duy nhất của ID, đặc biệt trong hệ thống nhiều tenant.
- Cách tạo key tổng hợp nếu một ID chỉ duy nhất trong phạm vi tenant.
- Không đưa timestamp hoặc trạng thái thay đổi vào key.

Nếu key là customerId, mọi thay đổi hồ sơ khách hàng nên giữ nguyên key đó. Không thay key thành addressId ở một loại sự kiện khác nếu mục tiêu là compact toàn bộ trạng thái khách hàng thành một bản ghi mới nhất.

### Null key không thể đại diện một trạng thái cần compact

Record không có key (null key) không thể được log cleaner gom theo danh tính thực thể. Nếu topic dùng compaction, không nên gửi record null key cho dữ liệu mà ứng dụng kỳ vọng được giữ lại dưới dạng trạng thái mới nhất.

Giá trị key rỗng ("") cũng khác với null key: nó là một key có byte biểu diễn cụ thể. Nếu nhiều record cùng dùng key rỗng, chúng có thể bị compact thành một trạng thái duy nhất cho key đó, điều thường không phải ý định của ứng dụng.

### Key và partition count

Partitioner mặc định thường băm byte của key để chọn partition. Với cùng partitioner, cùng byte key và cùng số partition, các producer thường định tuyến key đó đến cùng partition.

Compaction diễn ra trong từng partition, không hợp nhất key trùng nhau ở các partition khác nhau. Nếu tăng số partition hoặc thay partitioner khiến một key được định tuyến sang partition khác, lịch sử cũ vẫn nằm ở partition trước và bản ghi mới nằm ở partition mới. Cleaner không thể hợp nhất hai lịch sử này thành một trạng thái toàn cục.

Với compacted topic, thay đổi số partition là một quyết định cần đánh giá kỹ. Nếu cần đổi partition count, hãy có kế hoạch chuyển đổi dữ liệu, tạo topic phiên bản mới hoặc quy trình migration đảm bảo consumer dựng state đúng.

## 4. Tombstone: biểu diễn xóa một key

Trong compacted topic, producer xóa một trạng thái bằng cách gửi record có key khác null và value bằng null. Record này được gọi là **tombstone**.

Ví dụ:

| Offset | Key | Value | Ý nghĩa |
|---:|---|---|---|
| 10 | customer-42 | Hồ sơ Gold | Tạo hoặc cập nhật trạng thái |
| 11 | customer-42 | Hồ sơ Platinum | Cập nhật trạng thái mới |
| 12 | customer-42 | null | Đánh dấu xóa key |

Khi cleaner xử lý log, tombstone giúp loại bỏ các phiên bản cũ của customer-42. Sau khi hết thời gian lưu tombstone và được cleaner xử lý, chính tombstone cũng có thể bị loại bỏ. Khi đó, key này không còn xuất hiện trong phần log đã compact.

Tombstone không phải một JSON object có trường deleted=true. Nó là record Kafka có key và value thực sự null.

Cần phân biệt:

| Dữ liệu được gửi | Có phải tombstone? |
|---|---|
| Key customer-42, value null | Có |
| Key customer-42, value là chuỗi JSON null | Không; đây là payload có byte |
| Key customer-42, value là chuỗi rỗng | Không; đây là payload rỗng |
| Key null, value null | Không phải tombstone cho một thực thể có key |

Nếu ứng dụng cần giữ lịch sử xóa như một sự kiện nghiệp vụ, hãy phát thêm event riêng, ví dụ CustomerDeleted, vào event log. Tombstone của compacted topic phục vụ quản lý trạng thái key; sau khi được compact, nó có thể biến mất.

## 5. delete.retention.ms và thời gian tồn tại của tombstone

Tombstone cần tồn tại đủ lâu để consumer có thể nhìn thấy tín hiệu xóa khi dựng lại trạng thái. Kafka dùng cấu hình delete.retention.ms để xác định thời gian lưu tombstone trước khi nó đủ điều kiện bị loại bỏ bởi compaction.

Điều này đặc biệt quan trọng với consumer đang dựng snapshot từ đầu log. Nếu consumer đọc quá chậm và tombstone bị cleaner loại bỏ trước khi consumer tới vị trí đó, consumer có thể không quan sát được việc xóa và giữ lại trạng thái cũ trong kho đích.

Khi thiết kế, cần tính:

- Dung lượng topic và tốc độ đọc tối đa của consumer khôi phục.
- Thời gian cần để đọc toàn bộ partition và áp dụng dữ liệu.
- Thời gian gián đoạn tối đa của consumer.
- Tần suất replay hoặc dựng lại state.
- Thời gian tombstone cần tồn tại để các consumer có thể bắt kịp.

Không đặt delete.retention.ms quá thấp nếu có consumer thường xuyên phải dựng lại state từ đầu. Cũng không nên hiểu đây là cam kết tombstone sẽ bị xóa chính xác tại thời điểm hết hạn; cleaner còn phụ thuộc lịch chạy và khả năng xử lý.

## 6. Các cấu hình compaction quan trọng

### cleanup.policy

Thuộc tính này quyết định cách Kafka dọn log:

| Giá trị | Ý nghĩa |
|---|---|
| delete | Xóa segment theo retention time/size |
| compact | Compact các record theo key |
| compact,delete | Áp dụng cả compaction và retention xóa segment |

Dùng compact khi cần giữ trạng thái mới nhất theo key. Dùng delete khi cần giữ event log trong một cửa sổ thời gian. Dùng compact,delete khi muốn compact nhưng vẫn giới hạn tuổi hoặc dung lượng của dữ liệu.

Với compact,delete, retention vẫn có thể xóa segment cũ. Do đó, không thể giả định mọi key sẽ được lưu trạng thái vô thời hạn. Chỉ chọn cấu hình kết hợp khi nghiệp vụ chấp nhận dữ liệu cũ có thể biến mất theo retention.

### min.cleanable.dirty.ratio

Tỷ lệ dirty thể hiện phần dữ liệu cần được cleaner xử lý so với log. min.cleanable.dirty.ratio đặt ngưỡng để log đủ điều kiện được đưa vào quá trình compaction dựa trên tỷ lệ dirty.

Ngưỡng thấp hơn có thể khiến cleaner xử lý thường xuyên hơn và dữ liệu cũ được dọn sớm hơn, nhưng tăng I/O và CPU. Ngưỡng cao hơn có thể giảm tần suất chạy cleaner nhưng khiến nhiều phiên bản cũ tồn tại lâu hơn.

Không có một giá trị tối ưu cho mọi topic. Hãy điều chỉnh theo tốc độ ghi, dung lượng, độ trễ chấp nhận được và năng lực broker.

### min.compaction.lag.ms và max.compaction.lag.ms

- min.compaction.lag.ms quy định khoảng thời gian tối thiểu trước khi record đủ điều kiện compact. Nó hữu ích khi muốn giữ một khoảng lịch sử ngắn để subscriber có thời gian quan sát các phiên bản.
- max.compaction.lag.ms đặt giới hạn thời gian record có thể ở trạng thái chưa đủ điều kiện compact trước khi trở nên đủ điều kiện. Đây không phải lời hứa rằng cleaner chắc chắn hoàn tất compaction đúng thời hạn nếu broker đang thiếu tài nguyên hoặc bị backlog.

Hai tham số này điều chỉnh thời điểm record đủ điều kiện được compact, không thay đổi quy tắc key nào là phiên bản mới nhất.

### delete.retention.ms

Quy định thời gian tombstone được giữ trước khi đủ điều kiện bị loại bỏ. Cần chọn dựa trên thời gian tối đa consumer cần để đọc snapshot và nhận biết các thao tác xóa.

### retention.ms và retention.bytes

Hai cấu hình này đặc biệt cần chú ý với cleanup.policy=compact,delete:

- retention.ms giới hạn tuổi dữ liệu theo retention.
- retention.bytes giới hạn dung lượng lưu giữ theo partition.

Nếu dữ liệu cần giữ state lâu dài, không nên vô tình bật retention delete quá ngắn. Với compact-only, retention delete không phải cơ chế chính để dọn các phiên bản cũ; compaction mới là cơ chế theo key.

### Segment và log cleaner broker

Các cấu hình segment như segment.bytes và segment.ms ảnh hưởng thời điểm log roll, từ đó ảnh hưởng thời điểm segment có thể được cleaner xử lý.

Ở cấp broker, các thiết lập như log.cleaner.enable, log.cleaner.threads và log.cleaner.dedupe.buffer.size ảnh hưởng khả năng chạy cleaner và bộ nhớ dành cho quá trình tìm key trùng. Không nên tăng thread hoặc bộ nhớ mà không theo dõi CPU, heap và I/O của broker.

## 7. Tạo compacted topic và kiểm tra cấu hình

Có thể tạo topic trạng thái với ba partition và replication factor phù hợp cụm:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic customer-state --partitions 3 --replication-factor 3 --config cleanup.policy=compact
~~~

Kiểm tra topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic customer-state
~~~

Xem cấu hình topic:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 --entity-type topics --entity-name customer-state --describe
~~~

Có thể thay đổi cấu hình compaction của topic hiện có:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 --entity-type topics --entity-name customer-state --alter --add-config min.cleanable.dirty.ratio=0.2,min.compaction.lag.ms=60000,delete.retention.ms=86400000
~~~

Các giá trị trên chỉ minh họa cách cấu hình. Hãy chọn theo tốc độ ghi và yêu cầu phục hồi thực tế. Cần kiểm tra phiên bản Kafka, quyền Admin và kết quả cấu hình sau khi thay đổi.

Replication factor 3 chỉ hợp lệ khi cụm có đủ broker phù hợp. Nó liên quan đến độ sẵn sàng của partition, không thay đổi ý nghĩa compaction theo key.

## 8. Producer Java và Spring Kafka: cập nhật state và gửi tombstone

Ví dụ mô hình hồ sơ khách hàng:

~~~java
public record CustomerProfile(
        String name,
        String tier,
        long version
) {
}
~~~

Producer dùng customerId làm key cho mọi phiên bản:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerStatePublisher {

    private static final String TOPIC = "customer-state";

    private final KafkaTemplate<String, CustomerProfile> kafkaTemplate;

    public CustomerStatePublisher(
            KafkaTemplate<String, CustomerProfile> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String customerId, CustomerProfile profile) {
        kafkaTemplate.send(TOPIC, customerId, profile);
    }

    public void delete(String customerId) {
        ProducerRecord<String, CustomerProfile> tombstone =
                new ProducerRecord<>(TOPIC, customerId, null);

        kafkaTemplate.send(tombstone);
    }
}
~~~

Ở đây, cùng một customerId luôn được dùng làm key. Khi xóa, producer gửi value null để tạo tombstone. Key serializer vẫn phải hoạt động bình thường; value serializer cần hỗ trợ giá trị null theo cách Kafka client gửi tombstone.

Nếu value serializer chuyển một đối tượng null thành chuỗi JSON null hoặc byte rỗng, record đó không còn là tombstone theo nghĩa Kafka. Hãy kiểm tra serializer thực tế và quan sát record trong môi trường thử nghiệm.

### Dùng event version để kiểm soát cập nhật

Compaction chọn record theo vị trí trong log, không so sánh trường version trong payload. Nếu hai producer gửi cùng key và phiên bản nghiệp vụ 12 được append trước phiên bản 11, record phiên bản 11 có offset lớn hơn và có thể trở thành trạng thái được giữ lại.

Vì vậy, nếu nhiều instance có thể cập nhật cùng một thực thể, cần tuần tự hóa nguồn phát hoặc có cơ chế kiểm tra version. Ví dụ, nguồn dữ liệu chỉ phát version kế tiếp sau khi cập nhật aggregate thành công. Consumer cũng có thể từ chối version thấp hơn version đang lưu trong kho đích.

Không giả định compaction tự chọn version lớn nhất. Nó chọn record mới nhất theo thứ tự offset trong partition.

## 9. Consumer dựng lại trạng thái từ compacted topic

Một consumer có thể đọc compacted topic từ offset sớm nhất còn có thể đọc và áp dụng các bản ghi theo thứ tự trong từng partition để dựng state.

Logic cốt lõi:

- Key có value khác null: tạo hoặc cập nhật trạng thái của key.
- Key có value null: xóa trạng thái của key.
- Record cùng key có thể xuất hiện nhiều lần nếu compaction chưa hoàn tất; áp dụng tuần tự sẽ đưa state đến phiên bản cuối cùng mà consumer đọc được.
- Consumer phải xử lý idempotent vì có thể khởi động lại hoặc đọc lại record.

Ví dụ logic xử lý một record:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;

public class CustomerStateApplier {

    private final CustomerRepository repository;

    public CustomerStateApplier(CustomerRepository repository) {
        this.repository = repository;
    }

    public void apply(ConsumerRecord<String, CustomerProfile> record) {
        String customerId = record.key();

        if (customerId == null) {
            throw new IllegalArgumentException(
                    "customer-state yêu cầu key không null");
        }

        if (record.value() == null) {
            repository.deleteById(customerId);
            return;
        }

        repository.upsert(customerId, record.value());
    }
}
~~~

Nếu consumer ghi vào database, thao tác upsert và delete cần idempotent. Khi tiến trình dừng sau khi database commit nhưng trước khi Kafka commit offset, record có thể được đọc lại. Repository phải chịu được lần áp dụng lặp.

Trong hệ thống nhiều partition, consumer group có thể phân công partition cho nhiều instance. Mỗi partition được xử lý theo thứ tự offset; nếu ứng dụng chuyển record sang thread pool, cần bảo đảm không làm đảo thứ tự cập nhật cùng key và không commit offset vượt qua record chưa hoàn tất.

### Tái dựng state bằng group mới

Khi muốn dựng một read model mới, có thể dùng group ID mới và cấu hình auto.offset.reset=earliest. Consumer đọc phần log còn lưu, áp dụng value và tombstone vào kho đích mới. Sau khi hoàn tất, đối chiếu số lượng key và trạng thái nghiệp vụ trước khi chuyển ứng dụng sang kho đích đó.

Với compacted topic, consumer không nhất thiết nhìn thấy mọi phiên bản lịch sử. Mục tiêu của quá trình là dựng trạng thái hiện tại theo log đã compact, không phải tái hiện mọi hành động đã từng xảy ra.

Nếu có tombstone, consumer cần đọc nó trước khi tombstone bị cleaner loại bỏ. Thời gian quét toàn bộ topic phải nằm trong giới hạn thiết kế của delete.retention.ms.

## 10. Offset vẫn giữ nguyên sau compaction

Compaction xóa record cũ nhưng không đánh lại offset. Vì vậy, log có thể có các offset không liên tục.

Ví dụ:

~~~text
Trước compaction:  0  1  2  3  4  5  6
Sau compaction:    1     3        6
~~~

Offset 2, 4 và 5 không còn record tương ứng trong ví dụ, nhưng offset của các record còn lại không đổi. Consumer fetch từ một offset đã bị compact có thể tiếp tục tại record còn tồn tại kế tiếp trong partition.

Do đó:

- Không giả định offset liên tiếp khi đọc compacted topic.
- Không dùng số lượng offset đã tăng để suy ra chính xác số record còn lưu.
- Không coi offset bị thiếu là dữ liệu bị mất ngoài dự kiến; có thể đó là kết quả của compaction.
- Khi kiểm tra lag, hiểu rằng offset range và số record vật lý còn lại là hai đại lượng khác nhau.

Compaction cũng không sắp xếp lại các record còn lại. Thứ tự tương đối theo offset trong partition được giữ nguyên.

## 11. Các tình huống cần thận trọng

### Producer phát sự kiện sai thứ tự

Compaction giữ record có offset mới hơn, không giữ record có timestamp hoặc version lớn nhất. Nếu producer cũ gửi lại một trạng thái stale sau trạng thái mới, stale record có thể trở thành giá trị cuối cùng.

Giải pháp là quản lý thứ tự ở nguồn phát, dùng version đơn điệu, idempotent producer trong phạm vi retry phù hợp và kiểm tra version ở consumer.

### Thay đổi key hoặc serializer

Nếu định dạng key thay đổi giữa các phiên bản ứng dụng, cùng thực thể có thể xuất hiện dưới hai key byte khác nhau. Cleaner sẽ giữ hai trạng thái riêng. Cần xem key là hợp đồng dữ liệu ổn định và có kế hoạch migration khi thay đổi serializer hoặc chuẩn hóa.

### Tăng partition hoặc đổi partitioner

Key có thể chuyển partition sau khi partition count hoặc partitioner thay đổi. Vì compaction chỉ diễn ra trong từng partition, bản ghi cũ và mới của một thực thể có thể không được hợp nhất. Hãy đánh giá migration trước khi thay đổi topology topic compacted.

### Dùng compacted topic cho audit

Compaction loại bỏ các phiên bản cũ. Nếu nghiệp vụ cần biết mọi lần cập nhật, không thể chỉ dựa vào compacted topic. Hãy duy trì event log riêng hoặc kho lịch sử phù hợp.

### Retention xóa dữ liệu cần thiết

Với compact,delete, segment có thể bị xóa theo retention. Một key không được bảo đảm tồn tại vô thời hạn nếu topic có chính sách xóa theo tuổi hoặc dung lượng. Kiểm tra retention và khả năng khôi phục trước khi dùng topic làm nguồn state duy nhất.

### Tombstone bị xóa trước khi consumer khôi phục

Nếu consumer đọc snapshot quá lâu, tombstone có thể hết thời gian lưu và bị compact trước khi consumer tới vị trí đó. Tăng delete.retention.ms, cải thiện tốc độ rebuild hoặc dùng snapshot/backfill có kiểm soát để tránh state cũ hồi sinh trong kho đích.

## 12. Quan sát và kiểm thử compaction

Không nên kiểm tra compaction chỉ bằng cách gửi một vài record rồi lập tức đọc lại. Cleaner chạy nền và có thể chưa xử lý segment chứa record thử nghiệm.

Một bài thực hành có thể tiến hành:

1. Tạo topic customer-state với cleanup.policy=compact.
2. Gửi ba phiên bản khác nhau cho key customer-42.
3. Gửi một phiên bản cho key customer-99.
4. Gửi tombstone cho customer-42.
5. Quan sát các record bằng console consumer với key, partition và offset.
6. Chờ segment roll và cleaner xử lý; theo dõi log cleaner hoặc metric liên quan.
7. Đọc lại topic từ đầu bằng một group mới và áp dụng state.
8. Kiểm tra customer-42 không còn state nếu tombstone còn được quan sát; customer-99 vẫn có giá trị mới nhất.
9. Lặp lại thử nghiệm với nhiều key và nhiều partition để xác minh định tuyến.

Có thể đọc topic bằng CLI:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic customer-state --from-beginning --property print.key=true --property print.partition=true --property print.offset=true
~~~

Console consumer chỉ hiển thị dữ liệu đang còn đọc được; nó không chứng minh cleaner đã hoàn tất mọi segment. Kết quả cần được diễn giải cùng thời điểm roll segment, cấu hình compaction và trạng thái cleaner.

Các chỉ số nên quan sát gồm:

- Số byte log cần compact và số byte đã được cleaner xử lý.
- Tỷ lệ dirty log hoặc trạng thái cleanable log theo metric broker có sẵn.
- Tốc độ I/O và thời gian hoạt động của log cleaner.
- Dung lượng partition trước và sau compaction.
- Consumer lag và thời gian hoàn tất một lượt state restoration.
- Số tombstone và độ trễ từ lúc phát tombstone đến lúc nó được loại bỏ.

Tên metric cụ thể có thể thay đổi theo phiên bản Kafka và hệ thống metrics exporter. Hãy xác minh tên metric trong môi trường đang chạy.

## 13. Checklist thiết kế compacted topic

- [ ] Topic thực sự cần trạng thái mới nhất theo key, không phải toàn bộ lịch sử event.
- [ ] Mọi record trạng thái đều có key khác null.
- [ ] Key ổn định về giá trị và byte serialization giữa mọi producer.
- [ ] Các phiên bản của cùng thực thể được định tuyến vào cùng partition.
- [ ] Nguồn phát bảo đảm thứ tự hoặc có version để phát hiện dữ liệu stale.
- [ ] Tombstone được gửi bằng value null thực sự.
- [ ] delete.retention.ms đủ dài cho consumer dựng lại state.
- [ ] min.cleanable.dirty.ratio và compaction lag phù hợp tải ghi.
- [ ] Segment roll và năng lực log cleaner đáp ứng dung lượng topic.
- [ ] compact,delete chỉ được dùng khi chấp nhận retention xóa dữ liệu cũ.
- [ ] Có kế hoạch khi tăng partition hoặc thay đổi key serializer.
- [ ] Consumer xử lý idempotent, nhận tombstone và chịu được offset gap.
- [ ] Đã thử dựng lại state bằng group mới và đối chiếu kết quả.

## Kết luận

Log compaction giúp Kafka giữ trạng thái mới nhất theo key bằng cách loại bỏ các phiên bản cũ trong nền. Key phải ổn định và cùng thực thể phải được định tuyến vào cùng partition. Tombstone biểu diễn xóa một key, nhưng chỉ tồn tại trong thời gian được cấu hình trước khi có thể bị loại bỏ. Compaction giữ nguyên offset của record còn lại và không bảo toàn toàn bộ lịch sử nghiệp vụ.

Hãy dùng compacted topic cho changelog hoặc state cần khôi phục, thiết kế riêng event log nếu phải giữ lịch sử đầy đủ, và kiểm tra kỹ retention, tombstone, partition count cùng tốc độ log cleaner. Khi producer phát đúng thứ tự và consumer áp dụng idempotent, compacted topic trở thành nguồn dữ liệu hiệu quả để dựng lại trạng thái hiện tại của hệ thống.

