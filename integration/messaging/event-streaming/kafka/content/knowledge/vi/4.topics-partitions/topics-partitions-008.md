# Tăng số partition và ảnh hưởng đến ánh xạ key

Trong Kafka, partition là đơn vị lưu trữ, thứ tự và xử lý song song của một topic. Tăng số partition có thể giúp topic tiếp nhận nhiều luồng ghi hơn và cho consumer group xử lý song song nhiều hơn. Tuy nhiên, với producer dùng key để chọn partition, thay đổi số partition cũng làm thay đổi phép ánh xạ từ key sang partition. Một key trước đây được ghi vào partition này có thể được chuyển sang partition khác trong những lần gửi tiếp theo.

Đây là thay đổi kiến trúc, không chỉ là thao tác tăng một con số cấu hình. Các record cũ vẫn nằm trong partition ban đầu, trong khi record mới có thể được ghi sang partition mới. Vì Kafka chỉ bảo đảm thứ tự trong từng partition, việc một key xuất hiện ở hai partition có thể làm mất thứ tự quan sát được giữa lịch sử cũ và sự kiện mới. Với topic compacted, cùng key có thể còn xuất hiện ở nhiều partition và compaction không hợp nhất chúng trên toàn topic.

Bài viết này giải thích cách Kafka ánh xạ key, điều gì xảy ra khi tăng partition, các rủi ro với ordering và log compaction, cũng như cách lập kế hoạch mở rộng an toàn cho hệ thống Java/Spring Kafka.

## 1. Partition và key trong một topic

Một topic được chia thành một hoặc nhiều partition. Mỗi partition là một log độc lập, trong đó record được nối tiếp và có offset tăng dần. Kafka bảo đảm thứ tự đọc trong một partition. Giữa các partition khác nhau không có một thứ tự tổng thể.

Producer có thể gửi record theo một trong các cách:

- Chỉ định trực tiếp partition trong ProducerRecord.
- Gửi key và để partitioner chọn partition.
- Gửi record không có key và để partitioner phân phối record.
- Sử dụng custom partitioner để áp dụng quy tắc định tuyến riêng.

Trong trường hợp phổ biến nhất, producer gửi một key nghiệp vụ như orderId, customerId hoặc accountId. Key giúp các record thuộc cùng thực thể được đưa về cùng partition. Consumer trong cùng group có thể xử lý các partition khác nhau song song, trong khi các record của cùng key được đọc theo thứ tự trong partition đó.

Ví dụ, topic orders có bốn partition:

~~~text
orders
  partition 0: order-100, order-104, order-108, ...
  partition 1: order-101, order-105, order-109, ...
  partition 2: order-102, order-106, order-110, ...
  partition 3: order-103, order-107, order-111, ...
~~~

Đây chỉ là hình minh họa. Trong thực tế, partition được chọn bằng hàm băm trên key đã serialize, không phải bằng cách lấy phần số trong orderId.

Nếu mọi sự kiện của order-100 được gửi với cùng key, cùng serializer, cùng partitioner và cùng số partition, producer sẽ định tuyến chúng về cùng partition. Consumer có thể xử lý các sự kiện đó theo thứ tự offset trong partition.

## 2. Kafka ánh xạ key sang partition như thế nào?

Với Java producer dùng partitioner mặc định và record có key, Kafka thường chọn partition bằng cách băm byte của key đã serialize rồi lấy phần dư theo số partition.

Có thể biểu diễn khái quát như sau:

\[
partition = positiveHash(serializedKey) \bmod partitionCount
\]

Với DefaultPartitioner phổ biến của Kafka Java client, hàm băm dựa trên Murmur2. Điều cần chú ý là Kafka băm **byte sau serialize**, không băm trực tiếp đối tượng Java hay chuỗi ký tự mà người phát triển nhìn thấy.

Ví dụ, nếu key là chuỗi order-42 và StringSerializer tạo ra một dãy byte xác định, producer dùng dãy byte đó để tính partition. Nếu hai producer serialize cùng key thành hai dãy byte khác nhau, chúng có thể chọn hai partition khác nhau dù giá trị hiển thị giống nhau.

Một số yếu tố quyết định kết quả ánh xạ:

- **Nội dung key:** hai key khác nhau có thể cho kết quả hash khác nhau.
- **Serializer:** cùng đối tượng nhưng cách serialize khác có thể tạo byte khác.
- **Partitioner:** partitioner mặc định và custom partitioner có thể dùng thuật toán khác nhau.
- **Số partition:** là mẫu số của phép ánh xạ; thay đổi nó có thể làm thay đổi partition của key.
- **Partition được chỉ định tường minh:** nếu ProducerRecord đã chỉ định partition, producer không cần chọn partition bằng hash key.

Với record không có key, producer không thể dùng hash theo thực thể. Default partitioner của Java client hiện đại thường dùng sticky partitioning: giữ một partition trong một khoảng gửi để gom batch hiệu quả rồi chuyển sang partition khác khi cần. Vì vậy, null key cũng không tạo ra bảo đảm ordering theo một thực thể cụ thể.

### Ví dụ với bốn partition

Giả sử một key có giá trị hash dương minh họa là 42. Với bốn partition:

\[
42 \bmod 4 = 2
\]

Key đó được ghi vào partition 2.

Nếu topic được tăng từ bốn lên sáu partition, phép tính trở thành:

\[
42 \bmod 6 = 0
\]

Cùng key đó có thể được ghi vào partition 0 trong các lần gửi mới.

Một key khác có hash minh họa là 12:

\[
12 \bmod 4 = 0,\qquad 12 \bmod 6 = 0
\]

Key này vẫn được ánh xạ vào partition 0. Vì vậy, không phải mọi key đều chắc chắn chuyển partition khi tăng số partition; nhưng ứng dụng không nên dựa vào việc một số key tình cờ giữ nguyên vị trí.

Các con số 42 và 12 ở đây chỉ minh họa phép modulo, không phải kết quả hash thực tế của các chuỗi orderId tương ứng.

## 3. Điều gì thay đổi khi tăng số partition?

Giả sử topic orders đang có bốn partition và được tăng lên sáu partition.

Trước khi mở rộng, các record mới được định tuyến vào partition 0 đến 3. Sau khi mở rộng, producer có thể định tuyến record vào partition 0 đến 5 tùy kết quả partitioner.

Có ba điều cần tách biệt:

1. **Partition cũ vẫn tồn tại.** Partition 0 đến 3 không bị đổi ID hoặc tự động đổi tên.
2. **Partition mới được tạo thêm.** Partition 4 và 5 ban đầu chưa có record do topic mới được mở rộng; các record mới có thể bắt đầu được ghi vào chúng.
3. **Record cũ không tự di chuyển.** Kafka không đọc lại toàn bộ log để phân phối record cũ sang sáu partition theo ánh xạ mới.

Do đó, lịch sử của một key có thể bị chia thành hai phần:

~~~text
Trước khi tăng partition:
  order-42 -> partition 2
      offset 0: OrderCreated
      offset 8: PaymentAuthorized
      offset 15: OrderPacked

Sau khi tăng từ 4 lên 6:
  order-42 -> partition 0 (theo hash và số partition mới)
      offset 0: OrderShipped
      offset 1: OrderDelivered

Lịch sử vẫn còn ở partition 2;
các sự kiện mới có thể xuất hiện ở partition 0.
~~~

Offset chỉ có ý nghĩa bên trong partition. Offset 1 của partition 0 không thể so sánh trực tiếp với offset 15 của partition 2 để suy ra thứ tự nghiệp vụ. Consumer group cũng có thể xử lý hai partition ở các thời điểm khác nhau.

### Tăng partition không phải là di chuyển dữ liệu

Thao tác tăng partition không thực hiện repartition toàn bộ record hiện có. Nó mở rộng cấu trúc topic để các lần ghi tiếp theo có thể sử dụng thêm partition.

Nếu cần toàn bộ lịch sử của một key nằm trong cùng partition mới, phải thực hiện một quy trình di chuyển hoặc phát lại dữ liệu có kiểm soát sang topic đích. Chỉ tăng số partition không đáp ứng yêu cầu đó.

### Tăng partition không tự động tăng replication factor

Partition count và replication factor là hai cấu hình khác nhau:

- Partition count quyết định số log độc lập và mức song song tiềm năng.
- Replication factor quyết định số bản sao của mỗi partition trên các broker.

Tăng partition không có nghĩa là tăng replication factor. Cần kiểm tra việc gán replica cho partition mới, phân bố leader và tải giữa các broker theo chính sách cụm.

## 4. Ảnh hưởng đến thứ tự sự kiện theo key

Kafka bảo đảm thứ tự record trong một partition, không bảo đảm thứ tự giữa các partition. Khi số partition thay đổi, cùng một key có thể được ánh xạ sang partition khác. Đây là rủi ro quan trọng nhất nếu nghiệp vụ phụ thuộc thứ tự theo thực thể.

Giả sử đơn hàng order-42 có các sự kiện:

1. OrderCreated
2. PaymentAuthorized
3. OrderShipped

Trước khi mở rộng, cả ba sự kiện được ghi vào partition 2. Consumer đọc theo offset nên quan sát được thứ tự này.

Sau khi tăng partition, OrderDelivered có thể được ghi vào partition 0. Nếu consumer xử lý partition 0 trước khi hoàn tất các record còn lại ở partition 2, hệ thống có thể quan sát OrderDelivered trước OrderShipped.

Điều này có thể gây ra các lỗi nghiệp vụ:

- Trạng thái đơn hàng bị lùi về trạng thái cũ khi sự kiện đến muộn được áp dụng sau.
- Read model hiển thị sai trạng thái trong một khoảng thời gian.
- Một consumer phát thông báo hoặc gọi dịch vụ ngoài theo thứ tự không mong muốn.
- Logic kiểm tra chuyển trạng thái từ chối sự kiện vì nó đến trước sự kiện tiền nhiệm.
- Retry và xử lý song song làm thứ tự quan sát càng khó dự đoán.

Ngay cả khi chỉ có một consumer instance, consumer vẫn đọc nhiều partition và không có thứ tự tổng thể giữa chúng. Nếu listener hoặc ứng dụng xử lý song song, khả năng hoàn thành công việc lệch thứ tự còn rõ hơn.

### Khi key vẫn ở cùng partition

Một số key có thể tình cờ vẫn ánh xạ đến cùng partition ID sau khi tăng partition. Những key đó tiếp tục có lịch sử cũ và record mới trong cùng log. Tuy nhiên, đây là kết quả của phép hash và modulo, không phải bảo đảm chung cho topic.

Không nên thiết kế tính đúng đắn nghiệp vụ dựa trên giả định rằng key sẽ không đổi partition.

### Cách bảo vệ tính đúng đắn nghiệp vụ

Nếu thứ tự là yêu cầu bắt buộc, hãy bổ sung cơ chế kiểm tra ở tầng ứng dụng:

- Gắn sequence number tăng dần theo thực thể hoặc phiên bản trạng thái.
- Consumer chỉ áp dụng sự kiện có version hợp lệ; sự kiện cũ hoặc trùng lặp được bỏ qua hoặc đưa vào quy trình xử lý riêng.
- Dùng cập nhật có điều kiện trong cơ sở dữ liệu, ví dụ chỉ cập nhật khi version mới lớn hơn version hiện tại.
- Thiết kế handler idempotent để sự kiện được giao lại không làm lặp side effect.
- Với nghiệp vụ cần xử lý tuần tự tuyệt đối, duy trì một tuyến xử lý ổn định cho key và thực hiện cutover có kiểm soát khi thay đổi tuyến.

Sequence number không tạo ra thứ tự vận chuyển giữa hai partition. Nó giúp ứng dụng phát hiện và kiểm soát thứ tự nghiệp vụ khi record đến lệch thứ tự.

## 5. Ảnh hưởng đặc biệt với compacted topic

Với topic bật log compaction, Kafka giữ trạng thái mới nhất theo key trong từng partition. Compaction hoạt động trên từng partition, không quét toàn bộ topic để hợp nhất các key giống nhau nằm ở các partition khác nhau.

Nếu một key trước đây được ghi vào partition 2, nhưng sau khi tăng partition lại được ghi vào partition 0, topic có thể chứa:

~~~text
partition 2:
  key=customer-42, value=ACTIVE

partition 0:
  key=customer-42, value=SUSPENDED
~~~

Mặc dù hai record có cùng key, log cleaner không hợp nhất chúng xuyên partition. Cả hai giá trị có thể còn tồn tại sau compaction.

Vấn đề nghiêm trọng hơn khi có tombstone:

~~~text
partition 2:
  key=customer-42, value=ACTIVE

partition 0:
  key=customer-42, value=null   (tombstone)
~~~

Tombstone ở partition 0 chỉ đánh dấu xóa key trong phạm vi partition đó. Nó không xóa record ACTIVE ở partition 2. Nếu consumer dựng state store bằng cách đọc nhiều partition và xử lý không có một thứ tự toàn cục, trạng thái cuối cùng có thể không như mong đợi.

Vì vậy, việc tăng partition của compacted topic đang lưu trạng thái theo key cần được xem xét rất cẩn thận. Hợp đồng phổ biến của compacted topic giả định cùng một key luôn được đưa về cùng partition trong suốt vòng đời của dữ liệu. Thay đổi số partition có thể phá vỡ giả định này đối với các lần ghi mới.

Nếu cần thay đổi cấu trúc compacted topic, hãy lập kế hoạch di chuyển sang topic mới, chuyển toàn bộ lịch sử hoặc trạng thái cần thiết theo một ánh xạ nhất quán, xác định điểm cutover và kiểm tra kết quả state store trước khi chuyển consumer.

## 6. Tăng partition ảnh hưởng consumer group ra sao?

Trong một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer trong group. Nhiều consumer có thể xử lý song song các partition khác nhau.

Ví dụ:

| Số partition | Số consumer trong group | Mức sử dụng song song tối đa |
|---:|---:|---|
| 4 | 1 | 1 consumer xử lý 4 partition |
| 4 | 2 | Tối đa 2 consumer hoạt động |
| 4 | 4 | Tối đa 4 consumer hoạt động |
| 4 | 6 | 2 consumer không được gán partition |
| 8 | 4 | Tối đa 4 consumer, mỗi consumer có thể nhận nhiều partition |
| 8 | 8 | Tối đa 8 consumer hoạt động |

Tăng partition có thể tạo thêm cơ hội song song cho consumer group, nhưng không tự khởi tạo thêm consumer. Nếu group vẫn chỉ có hai consumer, việc tăng từ bốn lên tám partition không làm số consumer hoạt động vượt quá hai.

Khi metadata topic thay đổi, consumer group có thể thực hiện rebalance để phân bổ lại partition. Trong quá trình rebalance, việc xử lý có thể tạm dừng hoặc bị gián đoạn tùy assignor, giao thức rebalance và cấu hình client. Với cooperative rebalancing, việc thu hồi và phân bổ lại có thể diễn ra theo từng phần, nhưng ứng dụng vẫn cần tính đến thay đổi assignment.

Một số tác động vận hành khác:

- Consumer cần cập nhật metadata để nhận biết partition mới.
- Assignment thay đổi có thể làm tăng thời gian rebalance và ảnh hưởng latency.
- Mỗi partition bổ sung thêm chi phí quản lý log, index, file, metadata và replica trên broker.
- Nhiều partition hơn có thể làm tăng chi phí phục hồi, leader election và xử lý khi broker mất kết nối.
- Số partition cao không tự động giải quyết một key nóng, vì tất cả record của key đó vẫn được định tuyến về một partition tại một thời điểm.

### Partition count đặt giới hạn song song, không phải mục tiêu tự thân

Trong một consumer group, số partition thường giới hạn số consumer có thể thực sự xử lý đồng thời. Tuy nhiên, chọn số partition quá lớn cũng có chi phí trên broker, client và vận hành. Hãy xác định số consumer dự kiến, throughput trên mỗi partition, kích thước record, độ trễ và khả năng mở rộng của cụm trước khi quyết định.

## 7. Ví dụ tăng partition bằng CLI và Java AdminClient

### Dùng kafka-topics.sh

Giả sử topic orders có bốn partition và muốn tăng lên tám:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders \
  --partitions 8
~~~

Giá trị truyền vào là tổng số partition mong muốn sau khi thay đổi, không phải số partition cần cộng thêm. Trong ví dụ này, Kafka tăng từ bốn lên tám.

Kiểm tra cấu trúc topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Đầu ra cho biết số partition và replica assignment. Hãy kiểm tra leader, replica và ISR của các partition mới sau khi thay đổi.

Kafka cho phép tăng số partition của topic, nhưng không hỗ trợ giảm số partition trực tiếp. Nếu cần ít partition hơn, thường phải tạo topic mới và di chuyển dữ liệu theo kế hoạch.

### Dùng AdminClient trong Java

Có thể quản lý partition bằng Kafka AdminClient:

~~~java
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.ExecutionException;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewPartitions;

public class TopicPartitionManager {
    public static void increaseOrdersPartitions()
            throws InterruptedException, ExecutionException {
        Properties properties = new Properties();
        properties.put(
            "bootstrap.servers",
            "localhost:9092"
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            admin.createPartitions(
                Map.of("orders", NewPartitions.increaseTo(8))
            ).all().get();
        }
    }
}
~~~

Trong ứng dụng thực tế, thao tác quản trị topic thường được thực hiện bởi deployment job hoặc thành phần quản trị có quyền phù hợp, thay vì để mọi instance của service tự ý thay đổi cấu trúc topic khi khởi động.

Lệnh createPartitions chỉ hoàn thành thao tác tạo partition. Nó không tự di chuyển record cũ, không đảm bảo key giữ nguyên partition và cũng không kiểm tra rằng thứ tự nghiệp vụ vẫn đúng. Các điều kiện đó phải được đánh giá riêng.

## 8. Khi nào nên tăng partition?

Tăng partition là lựa chọn phù hợp khi có bằng chứng rằng số partition hiện tại đang giới hạn throughput hoặc parallelism và hệ thống có đủ tài nguyên để vận hành thêm partition.

Các dấu hiệu nên kiểm tra:

- Consumer lag tăng kéo dài dù consumer đã được tối ưu và có đủ tài nguyên.
- Số consumer hoạt động bị giới hạn bởi số partition hiện tại.
- Throughput trên mỗi partition đã chạm giới hạn thực tế của producer, broker hoặc consumer.
- Dữ liệu có đủ số lượng key để phân phối tải đều qua nhiều partition.
- Broker còn khả năng đáp ứng chi phí bổ sung về storage, replication, file và network.

Tuy nhiên, nếu chỉ có một key nóng chiếm phần lớn lưu lượng, tăng partition không chia nhỏ tải của key đó. Vì key vẫn được định tuyến vào một partition, consumer xử lý key nóng vẫn có thể trở thành nút thắt. Khi đó cần xem xét mô hình key, cách chia thực thể, giới hạn nghiệp vụ hoặc thiết kế xử lý riêng cho hot key.

Trước khi tăng partition, hãy đánh giá:

1. Topic có yêu cầu ordering nghiêm ngặt theo key không?
2. Topic có bật compaction và đang được dùng làm nguồn dựng state không?
3. Producer có dùng default partitioner, custom partitioner hay chỉ định partition trực tiếp?
4. Các producer có dùng cùng serializer và quy tắc tạo key không?
5. Consumer có chịu được sự kiện của cùng thực thể xuất hiện ở nhiều partition không?
6. Số consumer, broker, replica và tài nguyên lưu trữ có phù hợp với số partition mới không?
7. Có thể thực hiện thay đổi trong thời điểm tải thấp và quan sát rebalance không?

Nếu topic lưu event history mà ứng dụng chỉ cần đọc toàn bộ sự kiện, việc mở rộng có thể chấp nhận được sau khi đánh giá ordering. Nếu topic lưu trạng thái compacted theo key hoặc nghiệp vụ phụ thuộc thứ tự chặt chẽ, cần thiết kế migration trước khi thay đổi.

## 9. Các phương án giữ ánh xạ key ổn định khi cần mở rộng

Không có một cách tăng partition nào tự động giữ nguyên ánh xạ key cho mọi topic. Lựa chọn phụ thuộc yêu cầu ordering, compaction, khả năng downtime và cách consumer dựng trạng thái.

### Giữ số partition và tối ưu trước

Nếu chưa thực sự cần thêm partition, có thể tối ưu producer batching, compression, linger, số request đồng thời, consumer xử lý theo lô, truy vấn cơ sở dữ liệu và cấu hình broker. Đây là lựa chọn ít tác động đến key mapping nhất.

### Dùng custom partitioner hoặc bảng định tuyến ổn định

Ứng dụng có thể quản lý một ánh xạ rõ ràng từ key hoặc logical shard sang partition. Khi thêm partition, hệ thống chỉ chuyển những shard được chọn sau một kế hoạch cutover. Cách này đòi hỏi mọi producer tuân thủ cùng một bảng định tuyến và phiên bản cấu hình.

Không nên chỉ thêm một custom partitioner dùng modulo mới rồi cho rằng đã giữ ổn định key. Nếu thuật toán vẫn lấy hash modulo số partition hiện tại, vấn đề remapping vẫn còn.

### Dùng virtual shard

Thay vì ánh xạ trực tiếp key vào số partition vật lý, ứng dụng ánh xạ key vào một tập virtual shard có số lượng ổn định. Một bảng định tuyến riêng ánh xạ virtual shard sang partition vật lý. Khi mở rộng, có thể chuyển quyền sở hữu một số shard theo từng đợt.

Virtual shard giúp kiểm soát phạm vi di chuyển, nhưng không loại bỏ bài toán chuyển dữ liệu và thứ tự. Khi một shard được chuyển sang partition khác, cần xác định điểm dừng ghi, chuyển trạng thái hoặc lịch sử cần thiết, rồi mới chuyển producer sang tuyến mới.

### Tạo topic mới và migrate có kiểm soát

Với compacted topic hoặc luồng yêu cầu thứ tự chặt chẽ, tạo topic mới thường dễ kiểm soát hơn việc thay đổi trực tiếp partition count của topic đang chạy.

Một quy trình migration có thể gồm:

1. Tạo topic mới với số partition và replication factor đã tính toán.
2. Xác định key serializer, partitioner và quy tắc định tuyến cố định cho topic đích.
3. Chọn điểm cutover hoặc tạm dừng ghi để tránh hai tuyến cùng phát sự kiện không đồng bộ.
4. Chuyển trạng thái hiện tại hoặc phát lại lịch sử cần thiết sang topic mới, bảo đảm tất cả sự kiện của cùng key đi theo cùng một tuyến.
5. Ghi nhận event ID hoặc sequence number để consumer phát hiện trùng lặp và sự kiện đến sai thứ tự.
6. Kiểm tra số lượng record, trạng thái theo key, tombstone, lag và replica assignment.
7. Chuyển consumer và producer sang topic mới theo một thời điểm được kiểm soát.
8. Chỉ ngừng topic cũ sau khi xác nhận không còn consumer hoặc quy trình cần dữ liệu từ topic đó.

Chi tiết migration phải phù hợp với retention, dung lượng dữ liệu, thời gian downtime cho phép và yêu cầu lưu lịch sử. Không nên xóa topic cũ ngay sau khi producer đổi cấu hình.

## 10. Checklist trước và sau khi tăng partition

| Thời điểm | Việc cần kiểm tra |
|---|---|
| Trước thay đổi | Ghi lại partition count, replica assignment, leader và ISR |
| Trước thay đổi | Xác nhận topic có compact hay không, có yêu cầu ordering theo key không |
| Trước thay đổi | Kiểm tra serializer, partitioner và cách tạo key ở tất cả producer |
| Trước thay đổi | Ước lượng số consumer, throughput, storage và broker capacity |
| Khi thay đổi | Tăng đến tổng partition count mong muốn và theo dõi lỗi Admin API |
| Sau thay đổi | Kiểm tra partition mới, leader, replica và ISR |
| Sau thay đổi | Theo dõi consumer rebalance, lag, throughput và latency |
| Sau thay đổi | Kiểm tra cùng key có bị xuất hiện ở partition khác nhau hay không |
| Sau thay đổi | Xác minh sequence/version, trạng thái nghiệp vụ và hành vi duplicate |
| Sau thay đổi | Với compacted topic, kiểm tra state store và tombstone trên toàn bộ luồng dữ liệu |

Một đợt mở rộng chỉ nên được coi là ổn định khi hệ thống đạt throughput mục tiêu, consumer group hoạt động bình thường và các bất biến nghiệp vụ theo key vẫn được giữ.

## 11. Những nhầm lẫn thường gặp

- **“Tăng partition sẽ tự chia lại record cũ.”** Kafka giữ record cũ trong partition ban đầu. Việc tăng partition chỉ mở thêm nơi ghi cho record mới.
- **“Cùng key luôn ở cùng partition dù số partition thay đổi.”** Điều đó chỉ đúng khi các yếu tố định tuyến, gồm partition count, serializer và partitioner, vẫn tương thích.
- **“Tăng partition luôn làm tăng throughput.”** Nó tăng khả năng song song tiềm năng. Broker, producer, consumer, network hoặc một key nóng vẫn có thể là nút thắt.
- **“Một consumer group có thể xử lý song song không giới hạn.”** Số partition giới hạn số consumer có thể được gán partition tại cùng thời điểm.
- **“Compaction tự hợp nhất cùng key ở mọi partition.”** Compaction diễn ra trong từng partition. Cùng key nằm ở hai partition có thể còn hai giá trị độc lập.
- **“Tăng partition tương đương tăng replication factor.”** Hai cấu hình giải quyết hai vấn đề khác nhau: parallelism và độ dư thừa dữ liệu.
- **“Có thể giảm partition count bằng lệnh alter.”** Kafka hỗ trợ tăng partition trực tiếp; giảm số partition thường cần tạo topic mới và migrate dữ liệu.

## 12. Kết luận

Tăng số partition có thể cải thiện khả năng mở rộng và parallelism của Kafka, nhưng cũng thay đổi phép ánh xạ key của các record mới. Các record cũ không được di chuyển, vì vậy cùng một key có thể có lịch sử ở partition cũ và sự kiện mới ở partition khác. Điều này ảnh hưởng trực tiếp đến ordering, consumer processing và đặc biệt là compacted topic.

Trước khi mở rộng, hãy xác định rõ yêu cầu ordering theo key, serializer và partitioner đang dùng, trạng thái compaction, năng lực consumer group và tài nguyên broker. Với luồng không phụ thuộc thứ tự toàn cục, tăng partition có thể là một bước mở rộng phù hợp sau khi kiểm tra tải. Với compacted topic hoặc nghiệp vụ cần thứ tự chặt chẽ, hãy dùng chiến lược định tuyến ổn định và migration có kiểm soát để giữ tính nhất quán của dữ liệu.
