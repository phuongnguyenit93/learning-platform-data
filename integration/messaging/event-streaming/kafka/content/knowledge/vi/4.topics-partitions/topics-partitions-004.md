# Chọn key theo thực thể và yêu cầu thứ tự nghiệp vụ

Trong Kafka, key của record là quyết định thiết kế có ảnh hưởng trực tiếp đến partition mà record được ghi vào. Nếu chọn key phù hợp với thực thể nghiệp vụ, các sự kiện liên quan có thể được định tuyến vào cùng partition và giữ thứ tự append trong phạm vi thực thể đó. Nếu chọn key tùy tiện, dữ liệu có thể bị phân tán, dồn tải vào một partition hoặc không còn đáp ứng thứ tự mà nghiệp vụ yêu cầu.

Với hệ thống event streaming dùng Java hoặc Spring Kafka, hãy bắt đầu từ câu hỏi: **những sự kiện nào bắt buộc phải được xử lý theo thứ tự với nhau?** Câu trả lời thường xác định key tốt hơn việc bắt đầu từ cấu trúc DTO hoặc tên topic. Ví dụ, nếu trạng thái của một đơn hàng được thay đổi qua `OrderCreated`, `OrderPaid` và `OrderShipped`, `orderId` thường là key phù hợp. Nếu cần tuần tự hóa thay đổi số dư, `accountId` thường là ranh giới thích hợp.

## Mục tiêu bài học

Sau bài học, bạn có thể:

- Xác định ranh giới thứ tự nghiệp vụ trước khi chọn key.
- Chọn key theo aggregate hoặc thực thể cần được xử lý tuần tự.
- Giải thích cách Kafka dùng key đã serialize để chọn partition.
- Nhận diện key null, key có độ phân bố lệch, composite key và thay đổi số partition ảnh hưởng thế nào đến luồng dữ liệu.
- Triển khai lựa chọn key bằng Java Kafka client và Spring Kafka.
- Phân biệt thứ tự trong log Kafka với thứ tự hoàn tất xử lý ở ứng dụng.

## 1. Bắt đầu từ yêu cầu thứ tự nghiệp vụ

Thứ tự không phải lúc nào cũng cần thiết cho toàn bộ topic. Phần lớn hệ thống chỉ cần tuần tự hóa các thay đổi liên quan đến cùng một thực thể. Ví dụ:

| Luồng nghiệp vụ | Các sự kiện cần theo thứ tự | Key thường phù hợp |
|---|---|---|
| Đơn hàng | `OrderCreated`, `OrderPaid`, `OrderShipped`, `OrderCancelled` | `orderId` |
| Tài khoản | `MoneyDeposited`, `MoneyWithdrawn`, `AccountFrozen` | `accountId` |
| Tồn kho | `StockReceived`, `StockReserved`, `StockReleased` | `warehouseId + sku` |
| Hồ sơ khách hàng | `CustomerRegistered`, `CustomerUpdated`, `CustomerDisabled` | `customerId` |
| Thiết bị IoT | Các lần đọc hoặc thay đổi trạng thái của cùng thiết bị | `deviceId` |

Key nên biểu diễn **đối tượng mà các sự kiện cần cùng một thứ tự**, thường là aggregate root hoặc định danh ổn định tương ứng. Chọn key theo phạm vi này giúp các sự kiện cùng thực thể đi vào cùng partition khi cách phân vùng không thay đổi.

### 1.1. Xác định phạm vi cần tuần tự hóa

Hãy mô tả quy tắc nghiệp vụ bằng một câu cụ thể. Chẳng hạn:

- Một đơn hàng không được chuyển sang `SHIPPED` trước khi trạng thái thanh toán đã được ghi nhận.
- Các giao dịch làm thay đổi số dư của cùng tài khoản phải được áp dụng theo thứ tự đã xác lập.
- Các cập nhật tồn kho của cùng một SKU tại cùng một kho phải được xử lý tuần tự.

Từ câu đó, xác định định danh chung của các sự kiện. Nếu quy tắc áp dụng cho một đơn hàng, dùng `orderId`; nếu áp dụng cho một tài khoản, dùng `accountId`; nếu cùng SKU ở các kho khác nhau được xử lý độc lập, dùng một composite key gồm `warehouseId` và `sku`.

Không nên chọn key chỉ vì trường đó có sẵn trong payload. Một sự kiện đơn hàng có thể chứa `customerId`, `orderId`, `regionId` và `eventId`, nhưng mỗi giá trị biểu diễn một phạm vi khác nhau. Nếu yêu cầu là giữ thứ tự thay đổi của từng đơn hàng, dùng `customerId` có thể gom nhiều đơn hàng của một khách hàng vào cùng partition và làm giảm khả năng song song mà không đem lại lợi ích cần thiết.

### 1.2. Key không nhất thiết là event ID

`eventId` nhận diện một lần phát sự kiện. Key thường nhận diện thực thể mà sự kiện mô tả. Hai khái niệm có mục đích khác nhau:

- `eventId`: giúp khử trùng, truy vết và nhận diện một sự kiện cụ thể.
- Kafka key: giúp định tuyến và nhóm các sự kiện có liên quan vào cùng partition.

Ví dụ, ba sự kiện của cùng đơn hàng có thể có ba `eventId` khác nhau nhưng dùng chung key `ORD-2026-00421`. Nếu dùng một UUID mới cho mỗi record làm key, các sự kiện của đơn hàng có thể bị phân tán sang các partition khác nhau và mất cơ sở giữ thứ tự theo đơn hàng.

```json
{
  "eventId": "evt-7f3c9a",
  "eventType": "OrderPaid",
  "orderId": "ORD-2026-00421",
  "occurredAt": "2026-11-20T09:15:00Z",
  "data": {
    "paymentId": "PAY-9021",
    "amount": 1250000
  }
}
```

Với record này, producer có thể dùng `ORD-2026-00421` làm key và giữ `evt-7f3c9a` trong payload làm event ID. Consumer có thể dùng event ID để khử trùng, trong khi Kafka dùng key để định tuyến.

## 2. Kafka dùng key để chọn partition như thế nào?

Khi tạo record, producer có thể chỉ định partition cụ thể. Nếu không chỉ định, partitioner của producer client sẽ chọn partition. Với partitioner mặc định của Kafka Java client và key khác `null`, lựa chọn thông thường dựa trên hash của byte key đã serialize và số partition hiện có. Vì vậy, cùng một key thường được đưa vào cùng partition trong cùng topic khi serializer, partitioner và số partition không thay đổi.

```text
Topic: orders (3 partitions)

key = ORD-101  ---> Partition 0: Created -> Paid -> Shipped
key = ORD-202  ---> Partition 1: Created -> Cancelled
key = ORD-303  ---> Partition 0: Created -> Paid
```

Sơ đồ chỉ minh họa một kết quả phân vùng. Hai đơn hàng khác nhau vẫn có thể rơi vào cùng partition; điều đó bình thường. Mục tiêu là các sự kiện cùng key được định tuyến nhất quán vào một partition, chứ không phải mỗi key có một partition riêng.

Kafka lưu record trong log của partition. Consumer đọc log theo thứ tự append, vì vậy nếu các sự kiện của cùng thực thể được ghi vào cùng partition theo đúng thứ tự cần thiết, consumer có thể quan sát chúng theo thứ tự đó.

### 2.1. Key được hash sau khi serialize

Kafka broker không đọc kiểu Java hay ý nghĩa nghiệp vụ của key. Producer serializer chuyển key thành byte trước khi partitioner tính toán. Với partitioner mặc định phổ biến trong Kafka Java client, hash được tính từ byte đã serialize rồi ánh xạ vào số partition.

Điều này có hai hệ quả:

- Producer phải serialize cùng một định danh logic thành cùng dãy byte. Ví dụ, `ORD-101` không nên lúc thì được viết hoa, lúc thì viết thường nếu hai dạng phải đại diện cho cùng một thực thể.
- Nếu các producer dùng serializer hoặc cách chuẩn hóa key khác nhau, cùng một giá trị nhìn thấy ở tầng nghiệp vụ có thể tạo byte khác nhau và được định tuyến khác nhau.

Với key chuỗi, `StringSerializer` là lựa chọn đơn giản nếu các producer cùng dùng một quy ước mã hóa và chuẩn hóa. Với key phức tạp, hãy xác định schema và quy tắc serialize ổn định, tương thích giữa các phiên bản ứng dụng.

### 2.2. Producer có thể chỉ định partition trực tiếp

`ProducerRecord` cho phép truyền số partition. Khi chỉ định partition, producer dùng partition đó thay vì để partitioner lựa chọn theo key. Cách này có thể hữu ích trong một số kiến trúc cần ánh xạ tùy chỉnh, nhưng làm tăng trách nhiệm của ứng dụng: phải bảo đảm partition hợp lệ và mọi producer tuân thủ cùng một quy tắc.

Nếu mục tiêu chỉ là gom sự kiện theo thực thể, hãy ưu tiên key và partitioner đã cấu hình rõ ràng. Chỉ định partition thủ công theo logic riêng có thể tạo ra lỗi khi số partition thay đổi hoặc khi nhiều dịch vụ không thống nhất thuật toán.

## 3. Chọn key cho các mô hình nghiệp vụ phổ biến

### 3.1. Một aggregate có nhiều loại sự kiện

Giả sử một đơn hàng có các trạng thái `CREATED`, `PAID`, `PACKED`, `SHIPPED`. Mỗi thay đổi phát ra một event riêng. Dùng `orderId` làm key:

```text
Topic: orders

key = ORD-900
  offset 120: OrderCreated
  offset 121: OrderPaid
  offset 122: OrderPacked
  offset 123: OrderShipped
```

Các sự kiện cùng đơn hàng đi vào một partition nên consumer đọc partition đó theo thứ tự log. Các đơn hàng khác vẫn có thể được xử lý song song nếu nằm ở partition khác.

### 3.2. Nhiều thực thể tạo nên một ranh giới nghiệp vụ

Với tồn kho, SKU `SKU-88` có thể tồn tại ở nhiều kho. Nếu yêu cầu là giữ thứ tự cập nhật riêng cho từng SKU tại từng kho, key cần bao gồm cả mã kho và mã SKU:

```text
key = WH-01|SKU-88
key = WH-02|SKU-88
```

Nếu chỉ dùng `sku`, các kho khác nhau bị gom vào cùng partition dù có thể xử lý độc lập. Nếu chỉ dùng `warehouseId`, mọi SKU trong cùng kho bị gom lại, làm giảm song song. Composite key biểu diễn đúng cặp định danh của đối tượng cần tuần tự hóa.

Khi ghép nhiều thành phần, cần quy định cách mã hóa không gây nhập nhằng. Ví dụ chuỗi ghép bằng dấu `|` chỉ an toàn khi thành phần không chứa dấu đó hoặc có quy tắc escape rõ ràng. Với định danh phức tạp, dùng một kiểu key có schema và serializer ổn định thay vì tự ghép chuỗi tùy tiện.

### 3.3. Một sự kiện tác động đến nhiều thực thể

Một giao dịch chuyển tiền có thể tác động đến cả tài khoản nguồn và tài khoản đích. Nếu dùng `transactionId` làm key, tất cả sự kiện của giao dịch được gom lại, nhưng các giao dịch khác nhau trên cùng tài khoản có thể nằm ở partition khác nhau. Nếu dùng `accountId`, mỗi tài khoản được tuần tự hóa, nhưng một giao dịch tác động đến hai tài khoản sẽ không tự động có thứ tự chung giữa hai partition.

Không có một key đơn lẻ nào tự tạo ra thứ tự nguyên tử trên nhiều thực thể hoặc nhiều partition. Cần xác định quy tắc sở hữu trạng thái, cách phối hợp cập nhật, version/sequence của aggregate và cơ chế xử lý giao dịch. Nếu nghiệp vụ cần một thứ tự toàn cục cho mọi giao dịch, có thể phải dùng một partition duy nhất hoặc một bộ điều phối có thứ tự, chấp nhận giới hạn thông lượng tương ứng.

## 4. Các đặc tính của một key tốt

Một key phù hợp nên đáp ứng đồng thời các yêu cầu sau:

1. **Đúng phạm vi thứ tự:** mọi sự kiện cần tuần tự hóa cùng nhau có cùng key.
2. **Ổn định:** định danh không thay đổi trong vòng đời thực thể và được serialize nhất quán.
3. **Có độ phân bố đủ tốt:** lượng record giữa các key không quá lệch khiến một partition trở thành nút thắt.
4. **Không làm mất khả năng song song không cần thiết:** tránh chọn key quá rộng, khiến nhiều thực thể độc lập bị gom chung.
5. **Tương thích với vòng đời topic:** nhóm vận hành hiểu tác động khi thay partitioner, serializer hoặc số partition.

Key không cần duy nhất trên toàn topic. Nhiều record có cùng key là điều thường gặp và thường chính là mục đích của việc định tuyến theo thực thể.

### 4.1. Tránh key có độ phân bố lệch

Giả sử một topic `orders` nhận sự kiện từ hàng nghìn khách hàng, nhưng một khách hàng lớn tạo ra 40% tổng số record. Nếu dùng `customerId` làm key trong khi yêu cầu thứ tự chỉ áp dụng theo từng đơn hàng, tất cả sự kiện của khách hàng lớn có thể dồn vào một partition. Partition đó trở thành hot partition, gây tăng consumer lag và làm giảm throughput tổng thể.

Hãy chọn key hẹp nhất vẫn đáp ứng đúng yêu cầu thứ tự. Với ví dụ này, `orderId` có thể phân tán tải tốt hơn mà vẫn giữ thứ tự trong từng đơn hàng. Tuy nhiên, nếu nghiệp vụ thật sự yêu cầu tuần tự hóa toàn bộ hoạt động của khách hàng, dùng `customerId` là một đánh đổi có chủ đích và cần đo tải thực tế.

Không thể chia nhỏ một key nóng thành nhiều partition tùy ý mà vẫn giữ thứ tự của key đó. Nếu một thực thể tạo ra lượng sự kiện quá lớn, cần xem lại mô hình nghiệp vụ, giới hạn tốc độ, phân tách aggregate hoặc thiết kế xử lý theo sequence. Thêm partition không làm một key duy nhất tự động chạy song song mà vẫn giữ thứ tự toàn phần.

### 4.2. Tránh key null khi cần thứ tự theo thực thể

Record có thể có key `null`. Với partitioner mặc định hiện đại, producer thường dùng sticky partitioning để gom các record không có key vào một partition trong một khoảng gửi nhằm cải thiện batching. Điều này không bảo đảm các sự kiện cùng thực thể luôn vào cùng partition.

Nếu yêu cầu nghiệp vụ cần ordering theo `orderId`, không để key null rồi kỳ vọng Kafka suy ra mã đơn hàng từ value hoặc headers. Hãy trích xuất định danh và gán làm key trước khi gửi. Header cũng không tự động thay thế key trong thuật toán phân vùng mặc định.

## 5. Thay đổi số partition có thể ảnh hưởng thứ tự

Với partitioner mặc định, key được ánh xạ dựa trên số partition hiện tại. Khi tăng số partition của topic, phép ánh xạ có thể thay đổi. Một key trước đây đi vào partition 1 có thể được đưa vào partition 4 sau khi mở rộng topic.

```text
Trước khi tăng partition                 Sau khi tăng partition
Topic orders: 3 partitions               Topic orders: 6 partitions

key ORD-900 -> partition 1               key ORD-900 -> partition 4
                                         
Các record cũ vẫn ở partition 1         Record mới có thể vào partition 4
```

Khi đó, các sự kiện cũ và mới của cùng một thực thể nằm ở hai partition khác nhau. Consumer không có một thứ tự log chung để tự sắp xếp chúng. Vì vậy, tăng partition là thay đổi có thể ảnh hưởng semantics của key, không chỉ là thao tác tăng throughput.

Trước khi mở rộng topic đang mang yêu cầu ordering theo key, cần đánh giá:

- Có thể tạm dừng producer và consumer để di chuyển hoặc hoàn tất dữ liệu cũ không?
- Có thể chuyển sang topic mới, định tuyến theo phiên bản và kiểm soát thời điểm chuyển đổi không?
- Có cần duy trì một partitioner tùy chỉnh với số shard ổn định không?
- Consumer có thể dùng sequence/version nghiệp vụ để phát hiện sự kiện đến sai thứ tự hoặc bị thiếu không?

Không có một quy trình di chuyển duy nhất phù hợp cho mọi hệ thống. Phải chọn phương án theo khả năng dừng dịch vụ, lượng backlog, mức độ chấp nhận dữ liệu trùng và yêu cầu phục hồi.

## 6. Key chỉ là một phần của bảo đảm thứ tự

Key giúp các record của cùng thực thể đi vào cùng partition, nhưng bản thân key không đảm bảo toàn bộ chuỗi xử lý nghiệp vụ luôn đúng thứ tự. Cần xem xét cả producer, broker, consumer và hệ thống đích.

### 6.1. Thứ tự ghi từ producer

Với một producer instance, các record gửi cùng partition được ghi theo thứ tự mà broker append chúng. Retry có thể làm phức tạp thứ tự nếu producer gửi nhiều request đồng thời và không dùng cấu hình phù hợp. Bật idempotence giúp producer xử lý retry an toàn hơn và duy trì thứ tự trong các trường hợp được Kafka hỗ trợ.

Ví dụ cấu hình producer tường minh:

```java
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
```

Các phiên bản Kafka client hiện đại đã bật idempotence theo mặc định trong nhiều cấu hình mặc định; việc cấu hình tường minh giúp ý định của ứng dụng rõ ràng. Khi dùng idempotence, cần tuân thủ các ràng buộc cấu hình tương thích của client, đặc biệt là `acks`, retries và số request đang chờ. Hãy đối chiếu phiên bản client đang triển khai.

Nếu có nhiều producer instance cùng phát sự kiện cho một thực thể, Kafka chỉ ghi theo thứ tự request thực tế đến partition. Key giống nhau không tự biết sự kiện nào có thứ tự nghiệp vụ trước. Cần có một nguồn xác lập thứ tự, chẳng hạn sequence/version tăng dần ở aggregate, transactional outbox cùng cơ chế phát có thứ tự, hoặc một publisher duy nhất chịu trách nhiệm cho từng phạm vi thực thể.

### 6.2. Thứ tự xử lý trong consumer

Trong consumer group truyền thống, một partition tại một thời điểm được gán cho tối đa một consumer. Vòng lặp poll tuần tự có thể xử lý record theo thứ tự nhận được. Tuy nhiên, nếu consumer đẩy công việc sang thread pool và hoàn tất tác dụng phụ bất đồng bộ, record sau có thể cập nhật hệ thống đích trước record trước.

Nếu thứ tự tác động đến trạng thái nghiệp vụ, hãy giữ xử lý tuần tự cho partition hoặc dùng cơ chế điều phối theo key có kiểm soát. Chỉ commit offset sau khi các công việc tương ứng đã hoàn tất theo chính sách đã chọn. Nếu xử lý bất đồng bộ, cần quản lý offset theo tiến độ liên tục an toàn, không commit vượt qua record chưa xử lý xong.

### 6.3. Kiểm tra version nghiệp vụ

Với các aggregate quan trọng, payload có thể chứa `aggregateVersion` hoặc `sequenceNumber`. Consumer kiểm tra phiên bản nhận được so với phiên bản hiện tại để phát hiện sự kiện cũ, trùng hoặc đến sai thứ tự.

```json
{
  "eventId": "evt-9002",
  "eventType": "OrderPaid",
  "orderId": "ORD-900",
  "aggregateVersion": 2,
  "data": {
    "paymentId": "PAY-77"
  }
}
```

Nếu consumer đang có version 1 và nhận version 2, nó có thể áp dụng thay đổi. Nếu nhận version 4 khi đang chờ version 3, consumer có thể tạm dừng, retry, yêu cầu phát lại hoặc đưa sự kiện vào quy trình xử lý lỗi tùy thiết kế. Version nghiệp vụ bổ sung khả năng phát hiện vấn đề; nó không tự thay thế partition ordering hay cơ chế đồng bộ.

## 7. Triển khai chọn key bằng Java Kafka client

Ví dụ sau phát các sự kiện đơn hàng với `orderId` làm key. Mọi sự kiện của cùng một đơn hàng dùng cùng key, trong khi `eventId` vẫn nằm trong payload để nhận diện từng lần phát.

```java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.serialization.StringSerializer;

public class OrderEventPublisher {
    public static void main(String[] args) throws Exception {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(props)) {
            publish(producer, "ORD-900", "evt-1", "OrderCreated");
            publish(producer, "ORD-900", "evt-2", "OrderPaid");
            publish(producer, "ORD-900", "evt-3", "OrderShipped");
        }
    }

    private static void publish(
        KafkaProducer<String, String> producer,
        String orderId,
        String eventId,
        String eventType
    ) throws Exception {
        String value = "{\"eventId\":\"" + eventId + "\","
            + "\"eventType\":\"" + eventType + "\","
            + "\"orderId\":\"" + orderId + "\"}";

        ProducerRecord<String, String> record = new ProducerRecord<>(
            "orders", orderId, value
        );

        RecordMetadata metadata = producer.send(record).get();
        System.out.printf(
            "event=%s key=%s partition=%d offset=%d%n",
            eventType, orderId, metadata.partition(), metadata.offset()
        );
    }
}
```

Đoạn mã dùng một producer instance và gửi tuần tự để minh họa thứ tự đơn giản. Ứng dụng thật nên dùng JSON serializer hoặc thư viện tạo payload thay vì nối chuỗi, xử lý exception theo loại lỗi và tránh gọi `get()` đồng bộ cho từng record nếu cần throughput cao. Idempotence hỗ trợ retry an toàn của producer; nó không sắp xếp lại các sự kiện sai thứ tự đã được tạo bởi nhiều nguồn độc lập.

### 7.1. Composite key trong Java

Với tồn kho theo kho và SKU, có thể tạo một key chuẩn hóa:

```java
String key = warehouseId + "|" + sku;
ProducerRecord<String, String> record =
    new ProducerRecord<>("inventory-events", key, payload);
```

Chỉ dùng cách ghép này khi quy ước mã định danh không chứa dấu phân cách hoặc đã có cơ chế escape. Trong hệ thống nhiều ngôn ngữ, hãy công bố định dạng key và kiểm tra các producer tạo ra byte giống nhau cho cùng một thực thể.

## 8. Dùng key với Spring Kafka

`KafkaTemplate` hỗ trợ gửi `ProducerRecord` hoặc gửi trực tiếp topic, key và value. Cách gửi tường minh giúp key được nhìn thấy ngay tại điểm publish:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
        String orderId,
        String payload
    ) {
        return kafkaTemplate.send("orders", orderId, payload);
    }
}
```

Đoạn mã giả định Spring Kafka 3.x và các import/configuration cần thiết đã có trong ứng dụng. Với phiên bản khác, kiểu trả về của `send` có thể khác; cần đối chiếu API của dependency thực tế.

Consumer có thể nhận `ConsumerRecord` để kiểm tra key và metadata partition:

```java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrderEvent(ConsumerRecord<String, String> record) {
    String orderId = record.key();
    String payload = record.value();
    int partition = record.partition();
    long offset = record.offset();

    // Xử lý tuần tự theo partition và kiểm tra version của aggregate nếu cần.
}
```

Nếu listener chỉ nhận DTO, key có thể không nằm trong DTO tùy cấu hình message converter. Khi logic cần key để kiểm tra aggregate hoặc ghi log tương quan, hãy nhận `ConsumerRecord`, `Message<?>` có header phù hợp hoặc cấu hình converter để giữ metadata cần thiết.

## 9. Kiểm thử quyết định chọn key

Không chỉ kiểm tra record có được gửi thành công hay không. Hãy kiểm tra trực tiếp rằng các sự kiện cùng thực thể được định tuyến nhất quán và consumer quan sát được thứ tự mong đợi.

Một kế hoạch kiểm thử có thể gồm:

1. Tạo topic thử nghiệm với số partition đã biết.
2. Phát nhiều sự kiện cho một thực thể, ví dụ `ORD-900`, với các loại event theo thứ tự nghiệp vụ.
3. Phát xen kẽ sự kiện của các thực thể khác để kiểm tra mức song song.
4. Đọc `RecordMetadata` hoặc `ConsumerRecord` để xác nhận các record cùng key vào cùng partition.
5. Đọc partition theo thứ tự log và xác nhận thứ tự append.
6. Thử key null, key lệch tải và composite key để phát hiện trường hợp không mong muốn.
7. Nếu dự kiến tăng partition, chạy thử trước và quan sát key nào bị remap.
8. Kiểm tra consumer xử lý bất đồng bộ có làm thay đổi thứ tự tác dụng phụ hay không.

Ví dụ bảng kết quả mong đợi:

| Key | Event | Partition dự kiến trong cùng cấu hình | Ý nghĩa |
|---|---|---|---|
| `ORD-900` | `OrderCreated` | 2 | Sự kiện đầu của đơn hàng |
| `ORD-900` | `OrderPaid` | 2 | Cùng key nên cùng partition |
| `ORD-900` | `OrderShipped` | 2 | Cùng key nên cùng partition |
| `ORD-901` | `OrderCreated` | Có thể là 0, 1 hoặc 2 | Đơn hàng khác có thể ở partition khác hoặc trùng partition |

Số partition cụ thể trong bảng chỉ là ví dụ. Không viết test khẳng định một key phải luôn vào một số partition cố định nếu partitioner hoặc số partition không được đóng băng trong hợp đồng kiểm thử.

## 10. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `eventId` ngẫu nhiên làm key cho mọi event | Sự kiện cùng thực thể có thể vào partition khác nhau | Dùng ID thực thể làm key, giữ `eventId` riêng trong payload |
| Chọn `customerId` dù chỉ cần thứ tự theo đơn hàng | Nhiều đơn hàng của một khách hàng bị gom vào cùng partition | Chọn `orderId` nếu đó là ranh giới thứ tự thực tế |
| Dùng key null rồi kỳ vọng Kafka đọc key từ value | Không có bảo đảm định tuyến theo thực thể | Gán key rõ ràng ở producer |
| Chọn key có độ lệch lớn | Hot partition, lag và throughput thấp | Chọn phạm vi key hẹp nhất đáp ứng ordering; đo phân bố tải |
| Tăng partition mà không đánh giá mapping | Sự kiện cũ và mới của cùng key có thể nằm ở partition khác nhau | Lập kế hoạch di chuyển và kiểm tra sequence/version |
| Nhiều producer phát đồng thời và giả định key tự sắp xếp sự kiện | Thứ tự append có thể khác thứ tự nghiệp vụ | Xác lập sequence và cơ chế phát có thứ tự theo aggregate |
| Consumer xử lý song song không kiểm soát | Tác dụng phụ có thể hoàn tất sai thứ tự | Tuần tự hóa xử lý theo partition/key và quản lý commit an toàn |
| Ghép composite key không có quy tắc escape | Hai thực thể khác nhau có thể tạo cùng chuỗi key | Dùng định dạng canonical có schema hoặc quy tắc mã hóa rõ ràng |

## 11. Quy trình quyết định key cho một topic

Trước khi triển khai producer, hãy trả lời các câu hỏi sau theo đúng thứ tự:

1. **Quy tắc nghiệp vụ nào cần thứ tự?** Viết rõ điều kiện trước/sau của các sự kiện.
2. **Thực thể nào sở hữu quy tắc đó?** Chọn aggregate root hoặc định danh tương ứng.
3. **Một hay nhiều định danh tạo nên thực thể?** Nếu nhiều thành phần, thiết kế composite key có định dạng ổn định.
4. **Key có phân bố tải phù hợp không?** Ước lượng số key, tần suất từng key và nguy cơ hot partition.
5. **Các producer có serialize key giống nhau không?** Chuẩn hóa chữ hoa/thường, encoding, null và version schema.
6. **Số partition có thể thay đổi không?** Xác định quy trình mở rộng topic và tác động đến ordering.
7. **Producer có nguồn thứ tự đáng tin cậy không?** Cân nhắc idempotence, sequence/version, outbox và phát tuần tự theo aggregate.
8. **Consumer có giữ thứ tự tác dụng phụ không?** Kiểm tra concurrency, thread pool, retry và commit offset.

## 12. Bài tập tự kiểm tra

Một nền tảng bán hàng phát các sự kiện `OrderCreated`, `OrderPaid`, `OrderCancelled` và `CustomerAddressChanged`. Mỗi khách hàng có thể có nhiều đơn hàng. Hãy trả lời:

1. Nếu cần giữ thứ tự thay đổi trạng thái riêng cho từng đơn hàng, nên chọn `customerId` hay `orderId` làm key? Giải thích.
2. Nếu các sự kiện tồn kho cần thứ tự theo SKU trong từng kho, hãy đề xuất composite key.
3. Vì sao `eventId` thường không phải key phù hợp cho yêu cầu ordering theo aggregate?
4. Nếu tăng số partition, vì sao các event mới của một key có thể không còn nằm cùng partition với event cũ?
5. Nếu hai producer instance cùng phát sự kiện cho một `orderId`, key có tự bảo đảm đúng thứ tự nghiệp vụ không?
6. Nếu consumer xử lý record bằng thread pool và commit offset ngay sau khi submit task, rủi ro gì có thể xảy ra?

Gợi ý: chọn key theo đối tượng cần được tuần tự hóa; giữ event ID riêng; xem xét mapping partition khi mở rộng topic; và kiểm soát thứ tự từ lúc tạo sự kiện đến khi tác dụng phụ được hoàn tất.

## Kết luận

Key tốt bắt nguồn từ ranh giới thứ tự của nghiệp vụ. Chọn định danh ổn định của aggregate hoặc thực thể cần xử lý tuần tự giúp Kafka định tuyến các sự kiện liên quan vào cùng partition, trong khi các thực thể độc lập vẫn có thể được xử lý song song. Để giữ thứ tự đầu cuối, cần phối hợp key với partitioner, cấu hình producer, nguồn phát sự kiện, concurrency của consumer và chiến lược commit. Thay đổi số partition hoặc cách serialize key phải được xem là thay đổi có thể ảnh hưởng hành vi của luồng dữ liệu.
