# Tombstone, delete.retention.ms và khả năng dựng lại trạng thái

Kafka có thể dùng một topic được cấu hình log compaction để lưu trạng thái mới nhất theo từng key. Khi một thực thể bị xóa, producer gửi một record đặc biệt gọi là **tombstone**: record có key của thực thể và value bằng **null**. Tombstone thông báo cho consumer rằng key đó phải bị loại khỏi trạng thái đang giữ.

Kafka không xóa ngay record cũ khi nhận tombstone. Log cleaner chạy bất đồng bộ để loại các phiên bản cũ của key và giữ tombstone trong một khoảng thời gian được cấu hình bởi **delete.retention.ms**. Khoảng thời gian này quan trọng với consumer đang quét topic để dựng lại snapshot: consumer phải hoàn tất lần quét trong cửa sổ tombstone còn được giữ để không bỏ lỡ dấu xóa trong lúc compaction diễn ra.

Bài học này tập trung vào vòng đời của tombstone, cách cấu hình và kiểm tra topic compacted, cách consumer áp dụng tombstone, cùng những điều kiện cần bảo đảm để dựng lại state store hoặc cache một cách đúng đắn.

## 1. Log compaction lưu trạng thái theo key

Một partition Kafka là log append-only. Producer ghi record mới vào cuối log; các phiên bản cũ vẫn còn cho đến khi chính sách lưu trữ hoặc compaction xử lý chúng.

Với topic có **cleanup.policy=compact**, Kafka giữ lại phiên bản mới nhất của mỗi key trong log đã được compact. Cơ chế này phù hợp với changelog hoặc state topic, nơi mỗi key đại diện cho một thực thể và value mô tả trạng thái hiện tại của thực thể đó.

Ví dụ topic **customer-state** nhận các thay đổi:

| Offset | Key | Value | Ý nghĩa |
|---:|---|---|---|
| 10 | customer-7 | {"name":"An","tier":"basic"} | Tạo trạng thái ban đầu |
| 14 | customer-7 | {"name":"An","tier":"gold"} | Cập nhật trạng thái |
| 21 | customer-7 | null | Xóa customer-7 |
| 22 | customer-9 | {"name":"Binh","tier":"basic"} | Tạo một khách hàng khác |

Trước khi cleaner chạy, log có thể chứa cả ba phiên bản của customer-7. Sau khi compaction xử lý các segment liên quan, những phiên bản cũ hơn của key có thể bị loại bỏ. Tombstone của customer-7 được giữ lại trong thời gian delete retention rồi cũng có thể được loại bỏ.

Compaction không sắp xếp lại record và không đánh số lại offset. Sau khi compact, log có thể có khoảng trống offset vì các record cũ đã bị loại bỏ.

## 2. Tombstone là gì?

Tombstone là một Kafka record có:

- **Key khác null**: xác định chính xác thực thể cần xóa.
- **Value bằng null**: biểu thị thao tác xóa key khỏi trạng thái được materialize.

Ví dụ:

~~~text
topic: customer-state
key: customer-7
value: null
~~~

Consumer đọc tombstone cần xóa key **customer-7** khỏi database, cache hoặc state store cục bộ. Chỉ bỏ qua record vì value null là sai nếu consumer đang duy trì một bản sao trạng thái: dữ liệu cũ sẽ tiếp tục tồn tại ở hệ thống đích.

Tombstone có ý nghĩa trong topic compacted. Với topic không dùng compaction, một record value null không tự tạo ra cơ chế xóa các record trước đó của cùng key.

### Phân biệt tombstone với value rỗng

**null** và payload rỗng không giống nhau:

| Record | Ý nghĩa |
|---|---|
| Key customer-7, value null | Tombstone: xóa key khỏi state |
| Key customer-7, value là chuỗi rỗng hoặc byte array rỗng | Một value tồn tại nhưng có nội dung rỗng |
| Key null, value null | Không xác định được key để xóa; không phải tombstone hữu ích cho một thực thể cụ thể |

Nếu nghiệp vụ cần lưu một giá trị null như dữ liệu hợp lệ, hãy dùng schema/envelope có trường operation hoặc trạng thái rõ ràng thay vì dùng tombstone. Ví dụ, value có thể chứa {"operation":"SET","field":null} để phân biệt với thao tác xóa toàn bộ key.

## 3. Vòng đời của tombstone trong log compaction

Giả sử log có các record:

~~~text
offset 10  customer-7 -> {"tier":"basic"}
offset 14  customer-7 -> {"tier":"gold"}
offset 21  customer-7 -> null
~~~

Luồng xử lý khái quát:

1. Producer ghi tombstone ở offset 21.
2. Consumer đọc tombstone và xóa customer-7 khỏi state cục bộ.
3. Log cleaner xử lý các segment đủ điều kiện, loại những phiên bản cũ của customer-7.
4. Tombstone được giữ trong khoảng thời gian cấu hình bởi **delete.retention.ms**.
5. Sau khi hết thời gian giữ và cleaner xử lý segment tương ứng, tombstone có thể bị loại bỏ.

~~~mermaid
flowchart TD
    A["Các phiên bản value của cùng key"] --> B["Producer ghi tombstone<br/>key có value null"]
    B --> C["Consumer áp dụng lệnh xóa<br/>trong state cục bộ"]
    C --> D["Log cleaner compact segment<br/>loại phiên bản cũ"]
    D --> E["Giữ tombstone theo<br/>delete.retention.ms"]
    E --> F["Cleaner có thể loại tombstone"]
    F --> G["Key không còn record<br/>trong log đã compact"]
~~~

Log cleaner chạy nền và xử lý segment đủ điều kiện, vì vậy compaction không diễn ra tức thì ngay sau khi producer gửi tombstone. **delete.retention.ms** cũng không phải bộ đếm đảm bảo tombstone bị xóa chính xác tại một thời điểm tuyệt đối; việc loại bỏ còn phụ thuộc lịch chạy cleaner và điều kiện segment.

## 4. delete.retention.ms kiểm soát điều gì?

**delete.retention.ms** là cấu hình topic quy định khoảng thời gian giữ các tombstone marker trong topic compacted. Giá trị mặc định phổ biến là 24 giờ, nhưng cần kiểm tra cấu hình thực tế của cluster và phiên bản đang dùng.

Cấu hình này có hai ý nghĩa vận hành:

1. Tombstone không bị giữ mãi mãi; sau khoảng thời gian cho phép, cleaner có thể loại marker khi compact segment.
2. Consumer đang quét log để dựng snapshot hợp lệ cần hoàn tất trong giới hạn thời gian tombstone còn được giữ. Nếu quét quá lâu, tombstone có thể biến mất trong khi lần quét chưa hoàn tất, khiến snapshot dựng ra không còn phản ánh đúng trạng thái cuối.

**delete.retention.ms** không phải là thời gian giữ tất cả record và cũng không phải **retention.ms**. Hai cấu hình phục vụ mục đích khác nhau:

| Cấu hình | Tác dụng |
|---|---|
| delete.retention.ms | Thời gian giữ tombstone marker trong topic compacted |
| retention.ms | Giới hạn thời gian lưu segment theo chính sách delete retention |
| retention.bytes | Giới hạn dung lượng log theo chính sách delete retention |
| cleanup.policy=compact | Giữ trạng thái mới nhất theo key và xử lý tombstone theo compaction |
| cleanup.policy=delete | Xóa segment theo thời gian hoặc dung lượng, không giữ trạng thái mới nhất theo key |
| cleanup.policy=compact,delete | Áp dụng cả compaction và xóa segment theo retention |

Nếu topic là nguồn dữ liệu chuẩn để dựng lại trạng thái hiện tại, cần cân nhắc kỹ trước khi dùng **cleanup.policy=compact,delete**. Chính sách delete có thể xóa segment chứa value mới nhất của một key chỉ vì segment đã quá hạn, kể cả khi key đó chưa được cập nhật gần đây. Khi đó consumer mới không còn đủ dữ liệu để dựng trạng thái đầy đủ.

## 5. Cấu hình topic compacted

Ví dụ tạo topic **customer-state** có ba partition và replication factor 3:

Windows PowerShell:

~~~powershell
& .\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --create --topic customer-state --partitions 3 --replication-factor 3 --config cleanup.policy=compact --config delete.retention.ms=86400000
~~~

Linux hoặc macOS:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic customer-state --partitions 3 --replication-factor 3 --config cleanup.policy=compact --config delete.retention.ms=86400000
~~~

Giá trị **86400000** tương đương 24 giờ. Replication factor 3 yêu cầu cluster có đủ broker để đặt ba replica cho mỗi partition; với cluster local một broker, hãy dùng replication factor 1 cho mục đích thực hành.

Nếu topic đã tồn tại, có thể cập nhật cấu hình:

Windows PowerShell:

~~~powershell
& .\bin\windows\kafka-configs.bat --bootstrap-server localhost:9092 --entity-type topics --entity-name customer-state --alter --add-config "cleanup.policy=compact,delete.retention.ms=86400000"
~~~

Linux hoặc macOS:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type topics --entity-name customer-state --alter --add-config cleanup.policy=compact,delete.retention.ms=86400000
~~~

Kiểm tra cấu hình được override:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type topics --entity-name customer-state --describe
~~~

Trên Windows, dùng **kafka-configs.bat** trong **bin/windows**. Lệnh describe hiển thị cấu hình được đặt riêng ở cấp topic; một số cấu hình mặc định có thể được kế thừa từ broker nên không nhất thiết xuất hiện trong danh sách override.

## 6. Consumer áp dụng tombstone vào state

Consumer dựng trạng thái bằng cách xử lý record theo thứ tự offset của từng partition:

- Value khác null: tạo hoặc cập nhật state theo key.
- Value null: xóa key khỏi state.

Producer có thể gửi value bình thường để cập nhật state và gửi null để tạo tombstone:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class CustomerStateProducer {

    private final KafkaTemplate<String, CustomerState> kafkaTemplate;

    public void upsert(String customerId, CustomerState state) {
        kafkaTemplate.send("customer-state", customerId, state);
    }

    public void delete(String customerId) {
        kafkaTemplate.send("customer-state", customerId, null);
    }
}
~~~

Lệnh delete gửi một record có key là customerId và value null. Nó không gọi API xóa topic hay xóa trực tiếp record cũ khỏi segment; việc loại các phiên bản cũ do log cleaner thực hiện theo cleanup policy.

Ví dụ với Spring Kafka:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class CustomerStateConsumer {

    private final CustomerStateRepository repository;

    public CustomerStateConsumer(CustomerStateRepository repository) {
        this.repository = repository;
    }

    @KafkaListener(
        topics = "customer-state",
        groupId = "customer-state-materializer"
    )
    public void onRecord(ConsumerRecord<String, CustomerState> record) {
        String customerId = record.key();
        CustomerState state = record.value();

        if (state == null) {
            repository.deleteById(customerId);
            return;
        }

        repository.save(customerId, state);
    }
}
~~~

Ví dụ giả định key được deserialize thành String và value được deserialize thành **CustomerState**. Tombstone được chuyển thành value null; consumer vẫn cần key để biết bản ghi nào phải xóa.

Nếu listener xử lý bất đồng bộ, hãy bảo đảm thao tác delete/update và commit offset không làm đảo thứ tự của cùng key. Khi xử lý record lỗi, retry hoặc dead-letter, cần tránh để record mới được áp dụng trước rồi record cũ được replay và ghi đè state.

## 7. Dựng lại trạng thái từ compacted topic

Một state topic có thể được dùng làm changelog để tạo lại cache, projection hoặc state store sau khi ứng dụng mất dữ liệu cục bộ. Quy trình cơ bản:

1. Tạo state store rỗng hoặc xóa bản state cũ theo một quy trình có thể phục hồi.
2. Lấy end offset cần dùng làm ranh giới snapshot cho từng partition.
3. Đọc từ đầu log (earliest) đến ranh giới đã ghi nhận.
4. Với mỗi record, dùng key để upsert value hoặc xóa key nếu value null.
5. Chỉ đánh dấu snapshot hoàn tất khi đã xử lý đến ranh giới của tất cả partition.
6. Lưu checkpoint/offset cùng trạng thái đã dựng theo cách nhất quán, sau đó tiếp tục xử lý record mới.

Điểm quan trọng là **cửa sổ quét**. Nếu quá trình dựng snapshot kéo dài hơn thời gian tombstone được giữ, cleaner có thể loại một tombstone trước khi consumer đọc đến vị trí đó. Vì vậy, cấu hình **delete.retention.ms** phải lớn hơn thời gian khôi phục tệ nhất có thể dự kiến, kèm biên an toàn cho tải tăng, restart và sự cố.

Ví dụ, nếu một state topic cần 8 giờ để quét hết trong điều kiện tải cao nhất, đặt delete retention đúng 8 giờ là quá sát. Cần thêm thời gian dự phòng để lần restore vẫn hoàn tất khi broker hoặc ứng dụng chậm hơn bình thường.

### Vì sao phải quét đủ nhanh?

Giả sử một consumer bắt đầu dựng snapshot khi log vẫn có value cũ của customer-7 và tombstone của key đó. Trong lúc consumer đang quét, cleaner có thể compact segment và hết thời hạn giữ tombstone. Nếu consumer chưa đọc xong vùng log liên quan, lần quét có thể không nhìn thấy dấu xóa cần thiết để kết luận key không còn tồn tại.

Đó là lý do Kafka mô tả **delete.retention.ms** như giới hạn thời gian mà consumer cần hoàn tất một lần scan để nhận được snapshot hợp lệ. Không nên coi đây chỉ là một tham số tiết kiệm dung lượng.

### Snapshot theo partition và tính nhất quán toàn cục

End offset được lấy riêng cho từng partition. Với state độc lập theo key, đây là cách thực tế để xác định ranh giới quét. Tuy nhiên, một tập end offset của nhiều partition không tự tạo ra snapshot nguyên tử toàn cục cho các cập nhật liên quan đến nhiều key/partition.

Nếu nghiệp vụ cần một giao dịch thay đổi nhiều key phải xuất hiện đồng thời trong snapshot, cần thêm cơ chế nhất quán ở tầng ứng dụng, transaction-aware processing hoặc một quy trình snapshot có version/epoch. Log compaction tự nó chỉ giữ trạng thái mới nhất theo key, không tạo một giao dịch snapshot xuyên partition.

## 8. Tương tác với Kafka Streams và changelog state store

Kafka Streams dùng changelog topic để khôi phục state store cục bộ. Khi một key bị xóa khỏi state store, thao tác xóa được biểu diễn bằng tombstone trong changelog compacted. Khi task được khởi tạo lại hoặc chuyển sang instance khác, Kafka Streams đọc changelog để khôi phục trạng thái.

Trong quá trình thiết kế:

- Chọn key ổn định để state của cùng thực thể được phân vùng nhất quán.
- Bảo đảm changelog topic dùng cleanup policy phù hợp cho khôi phục state.
- Cấu hình tombstone retention đủ dài so với thời gian restore tối đa.
- Theo dõi restore duration, consumer lag, changelog throughput và trạng thái task.
- Không tự ý xóa changelog topic hoặc thay đổi cleanup policy khi ứng dụng đang phụ thuộc vào nó để phục hồi state.

Nếu ứng dụng lưu snapshot/checkpoint ngoài Kafka, checkpoint và offset changelog phải được phối hợp nhất quán. Khôi phục state từ một checkpoint cũ rồi tiếp tục từ offset mới hơn có thể bỏ sót thay đổi; khôi phục từ checkpoint mới hơn nhưng đọc lại quá xa có thể tạo thao tác lặp. Thiết kế restore phải xác định rõ cặp state-version và offset tiếp tục.

## 9. Những lỗi thường gặp khi xử lý tombstone

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Key đã xóa trong Kafka nhưng vẫn còn ở database/cache | Consumer bỏ qua record value null | Xử lý null value thành thao tác delete theo key |
| Consumer restore vẫn thấy key đã xóa | Lần scan quá lâu, tombstone đã hết hạn hoặc state cũ chưa được xóa trước restore | Tăng delete retention, tối ưu thời gian restore và dựng vào state store rỗng |
| Key biến mất sau một thời gian dù không có tombstone mới | Topic dùng compact,delete và segment chứa value cuối cùng đã hết retention | Kiểm tra cleanup.policy và retention.ms/retention.bytes |
| Tombstone không biến mất ngay sau delete.retention.ms | Cleaner chạy nền, segment chưa đủ điều kiện compact | Kiểm tra trạng thái cleaner; không giả định thời điểm xóa chính xác |
| Consumer nhận value rỗng nhưng không xóa state | Ứng dụng nhầm empty payload với tombstone | Phân biệt null với byte array/chuỗi rỗng |
| State bị ghi lùi sau retry/replay | Record cũ được xử lý sau record mới hoặc xử lý song song thiếu kiểm soát | Dùng version/event sequence, xử lý idempotent và kiểm soát thứ tự |

## 10. Theo dõi và vận hành

Với topic compacted dùng làm nguồn khôi phục, nên theo dõi:

- **cleanup.policy**, **delete.retention.ms**, **min.compaction.lag.ms** và các cấu hình retention liên quan.
- Tốc độ ghi, kích thước log, số lượng tombstone và tỷ lệ key được cập nhật/xóa.
- Log cleaner activity, lượng dữ liệu đang chờ compact và thời gian segment chờ xử lý.
- Consumer lag và thời gian hoàn tất restore.
- Số lần restore thất bại, số key được upsert/delete và thời gian dựng state.
- Độ nhất quán giữa checkpoint, offset và state store.

**min.compaction.lag.ms** có thể được dùng để đặt thời gian tối thiểu một record phải nằm trong log trước khi được compact; nó phục vụ mục đích khác với **delete.retention.ms**. Không dùng hai tham số thay thế cho nhau.

Trước khi giảm **delete.retention.ms**, hãy xác nhận thời gian restore tối đa của mọi consumer phụ thuộc topic. Trước khi bật chính sách delete retention trên topic compacted, hãy xác nhận hệ thống có thể chấp nhận việc mất các key không được cập nhật trong thời gian retention.

## 11. Bài tập tự kiểm tra

1. Một record có key account-9 và value null biểu thị điều gì?
2. Vì sao tombstone không bị xóa ngay sau khi producer gửi?
3. delete.retention.ms khác retention.ms ở điểm nào?
4. Một consumer cần 30 giờ để dựng state, trong khi tombstone retention là 24 giờ. Rủi ro nào có thể xảy ra và nên điều chỉnh gì?
5. Vì sao cleanup.policy=compact,delete có thể làm mất khả năng dựng lại một key ít được cập nhật?
6. Khi consumer nhận tombstone, thao tác nào phải được thực hiện trên state store?
7. Vì sao checkpoint của state store cần nhất quán với offset changelog?

## Kết quả cần ghi nhận

Sau khi thực hành, hãy lưu:

- Cấu hình cleanup.policy và delete.retention.ms của topic.
- Một chuỗi record cùng key gồm nhiều phiên bản value và một tombstone.
- Kết quả consumer trước và sau khi nhận tombstone.
- Thời gian cần để dựng lại state từ đầu và so sánh với delete retention.
- Cách ứng dụng lưu checkpoint/offset để tiếp tục sau restore.

## Kết luận

Tombstone là record có key và value null, dùng để biểu diễn việc xóa một key trong topic compacted. Consumer phải áp dụng tombstone bằng cách xóa key khỏi state cục bộ. Log cleaner sẽ loại các phiên bản cũ và giữ tombstone theo **delete.retention.ms** trước khi có thể xóa marker đó.

Vì tombstone có thời hạn, một consumer dựng snapshot từ log phải hoàn tất lần quét trong cửa sổ retention và đồng bộ checkpoint với offset. Cấu hình retention phù hợp, state restore có kiểm soát và xử lý null value đúng cách giúp compacted topic trở thành nguồn dữ liệu đáng tin cậy để dựng lại trạng thái.
