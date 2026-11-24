# Phát hành và đăng ký nhận thông điệp (publish-subscribe)

Trong kiến trúc hướng sự kiện, một dịch vụ thường cần thông báo cho nhiều phần khác nhau của hệ thống khi một việc nghiệp vụ đã xảy ra. Ví dụ, sau khi đơn hàng được tạo, hệ thống kho cần giữ hàng, hệ thống thanh toán cần chuẩn bị giao dịch và hệ thống thông báo cần gửi email. Nếu dịch vụ đơn hàng gọi trực tiếp từng dịch vụ, nó phải biết danh sách người nhận và cách xử lý khi một dịch vụ tạm thời không hoạt động.

Mô hình **publish-subscribe (pub/sub)** cho phép bên phát hành gửi một thông điệp đến một đích chung. Broker tiếp nhận thông điệp và phân phối nó đến các nhóm đăng ký. Publisher không cần biết có bao nhiêu nhóm đang lắng nghe hoặc mỗi nhóm có bao nhiêu instance.

Spring Cloud Stream cung cấp mô hình lập trình và lớp tích hợp broker để xây dựng pub/sub với Kafka, RabbitMQ, Pulsar hoặc binder phù hợp khác. Bài học tập trung vào cách phát hành thông điệp, cách các nhóm đăng ký nhận bản tin và cách biểu diễn quan hệ đó bằng binding, destination và consumer group.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của publisher, subscriber, broker, destination và consumer group.
- Phân biệt phát tán thông điệp đến nhiều nhóm với chia tải giữa nhiều instance trong cùng một nhóm.
- Cấu hình output binding và input binding bằng mô hình hàm của Spring Cloud Stream.
- Chọn consumer group phù hợp để mỗi dịch vụ nhận được luồng sự kiện độc lập.
- Nhận biết giới hạn về thứ tự, lưu giữ, xác nhận và giao nhận khi dùng các broker khác nhau.

## 1. Tình huống: một sự kiện, nhiều phản ứng

Giả sử dịch vụ đơn hàng phát hành sự kiện `OrderCreated` khi một đơn hàng mới được xác nhận. Các bộ phận khác nhau cần phản ứng với sự kiện này:

- Nhóm kho cập nhật số lượng hàng có thể xuất.
- Nhóm thanh toán tạo yêu cầu thu tiền.
- Nhóm thông báo gửi email hoặc thông báo trong ứng dụng.
- Nhóm phân tích ghi nhận dữ liệu phục vụ báo cáo.

Đây là sự kiện mô tả điều đã xảy ra, không phải lệnh yêu cầu một dịch vụ cụ thể thực hiện công việc. Dịch vụ đơn hàng công bố sự kiện lên destination `orders`. Mỗi nhóm nghiệp vụ đăng ký nhận destination đó và tự quyết định cách xử lý.

~~~mermaid
flowchart LR
    P["Dịch vụ đơn hàng<br/>Publisher"] -->|"OrderCreated"| B[("Broker<br/>destination: orders")]
    B --> G1["Consumer group: inventory"]
    B --> G2["Consumer group: billing"]
    B --> G3["Consumer group: notification"]
    G1 --> I1["Kho instance A"]
    G1 --> I2["Kho instance B"]
    G2 --> T1["Thanh toán instance A"]
    G3 --> N1["Thông báo instance A"]
    G3 --> N2["Thông báo instance B"]
~~~

Ba group nghiệp vụ đều có thể nhận sự kiện `OrderCreated`. Nếu nhóm kho có hai instance, hai instance này thường chia nhau xử lý công việc của nhóm kho; chúng không mặc nhiên nhận hai bản sao riêng biệt của mọi sự kiện.

Mô hình này giảm phụ thuộc giữa các dịch vụ: publisher chỉ cần biết hợp đồng sự kiện và destination; subscriber có thể được triển khai, mở rộng hoặc thay đổi độc lập; một subscriber gặp lỗi không nhất thiết ngăn publisher gửi sự kiện cho broker; và có thể bổ sung subscriber mới mà không phải sửa mã publisher.

Pub/sub không tự động giải quyết mọi vấn đề giao nhận. Khả năng lưu giữ thông điệp, thời gian thử lại, xác nhận xử lý và hành vi khi subscriber ngừng hoạt động còn phụ thuộc broker và cấu hình binder.

## 2. Các thành phần của mô hình pub/sub

| Thành phần | Vai trò |
|---|---|
| Publisher | Tạo và phát hành sự kiện hoặc thông điệp. |
| Message/Event | Dữ liệu được truyền, thường biểu diễn một sự kiện nghiệp vụ đã xảy ra. |
| Destination | Tên logic của nơi publisher gửi và subscriber nhận thông điệp. |
| Broker | Hệ thống trung gian tiếp nhận, lưu giữ hoặc định tuyến thông điệp. |
| Subscription / consumer group | Nhóm đăng ký nhận luồng thông điệp và có trạng thái tiêu thụ riêng. |
| Subscriber | Thành phần xử lý thông điệp nhận được. |
| Binder | Lớp Spring Cloud Stream kết nối binding với công nghệ broker cụ thể. |

Trong Spring Cloud Stream, **binding** là cầu nối giữa hàm ứng dụng và hệ thống truyền tin. Input binding đưa thông điệp từ broker vào hàm; output binding đưa dữ liệu từ hàm hoặc ứng dụng ra broker. Binding được cấu hình với destination và các thuộc tính tiêu thụ như group.

Cần phân biệt ba khái niệm:

- **Binding** mô tả điểm kết nối của ứng dụng.
- **Destination** xác định luồng hoặc địa chỉ logic mà binding kết nối tới.
- **Group** xác định một nhóm subscriber có tiến độ tiêu thụ độc lập trên destination đó.

Nhiều binding có thể cùng trỏ tới một destination. Khi chúng thuộc các group khác nhau, mỗi group có thể nhận toàn bộ luồng sự kiện theo cơ chế của broker.

## 3. Phát tán giữa các group và chia tải trong một group

Đây là khác biệt quan trọng nhất khi thiết kế pub/sub.

### Các group khác nhau: mỗi nhóm nhận luồng sự kiện

Nếu `inventory`, `billing` và `notification` là ba group riêng, mỗi group có subscription hoặc vị trí đọc độc lập. Khi publisher phát hành một sự kiện, cả ba nhóm đều có thể nhận và xử lý sự kiện đó.

Đây là hành vi phát tán (fan-out) thường được mong đợi khi nhiều dịch vụ độc lập cùng quan tâm đến một sự kiện.

### Nhiều instance trong cùng group: chia sẻ công việc

Nếu nhóm `inventory` chạy ba instance, các instance tham gia cùng một group để chia nhau xử lý thông điệp. Broker quyết định instance nào nhận thông điệp hoặc phân vùng nào được giao cho instance nào.

Vì vậy, cùng một thông điệp thường chỉ được một thành viên trong group xử lý tại một thời điểm theo cơ chế phân phối của broker. Không nên tạo nhiều instance cùng group với kỳ vọng mỗi instance sẽ nhận một bản sao của mọi sự kiện.

| Cách tổ chức | Hành vi mong đợi |
|---|---|
| Ba dịch vụ, ba group khác nhau | Mỗi dịch vụ nhận luồng sự kiện độc lập. |
| Ba instance, cùng một group | Các instance chia tải xử lý của một dịch vụ. |
| Ba instance, ba group riêng | Mỗi instance có subscription riêng và có thể nhận toàn bộ luồng; thường không phải cách mở rộng một dịch vụ. |

Trong production, nên đặt tên group ổn định theo vai trò nghiệp vụ, chẳng hạn `inventory`, `billing` hoặc `notification`. Tên group giúp broker nhận diện subscription và duy trì tiến độ tiêu thụ theo khả năng của binder.

Nếu bỏ qua group, Spring Cloud Stream và binder có thể tạo subscription ẩn danh. Cách hoạt động và thời gian tồn tại của subscription ẩn danh khác nhau giữa các broker. Không nên dựa vào hành vi đó cho consumer cần tiếp tục đọc sau khi ứng dụng khởi động lại; hãy cấu hình group có tên rõ ràng.

## 4. Biểu diễn pub/sub bằng Spring Cloud Stream

Spring Cloud Stream khuyến khích mô hình lập trình hàm:

| Kiểu hàm | Hướng dữ liệu | Binding mặc định |
|---|---|---|
| `Supplier<T>` | Tạo dữ liệu để phát hành | `<functionName>-out-0` |
| `Function<I, O>` | Nhận dữ liệu, biến đổi và phát hành kết quả | `<functionName>-in-0` và `<functionName>-out-0` |
| `Consumer<T>` | Nhận dữ liệu và xử lý | `<functionName>-in-0` |

Tên binding được tạo từ tên bean hàm. Ví dụ, bean `inventory` có input binding mặc định là `inventory-in-0`. Có thể cấu hình binding đó trỏ đến destination `orders` và group `inventory`.

Khi cần phát hành sự kiện từ một luồng xử lý nghiệp vụ thông thường, `StreamBridge` cho phép gửi dữ liệu vào một output binding. Cách này hữu ích khi sự kiện được tạo trong service, controller hoặc thành phần không phải `Supplier`.

### Ví dụ cấu hình

Ví dụ dưới đây mô tả một ứng dụng có hai consumer function và một output binding được gửi qua `StreamBridge`. Trong hệ thống thực tế, publisher và các subscriber có thể nằm trong những ứng dụng triển khai độc lập; mỗi ứng dụng chỉ cần cấu hình binding mà nó sử dụng.

~~~yaml
spring:
  cloud:
    function:
      definition: inventory;billing
    stream:
      bindings:
        orders-out-0:
          destination: orders
        inventory-in-0:
          destination: orders
          group: inventory
        billing-in-0:
          destination: orders
          group: billing
~~~

Cấu hình trên có ý nghĩa:

- `orders-out-0` gửi thông điệp đến destination `orders`.
- `inventory-in-0` nhận từ cùng destination nhưng thuộc group `inventory`.
- `billing-in-0` cũng nhận từ destination `orders`, nhưng thuộc group `billing`.
- Hai group có tiến độ tiêu thụ riêng nên đều có thể xử lý sự kiện được phát hành.

### Khai báo sự kiện

Sự kiện nên có cấu trúc rõ ràng, ổn định và chỉ chứa dữ liệu subscriber cần:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt,
    BigDecimal total,
    int schemaVersion
) {}
~~~

`eventId` định danh sự kiện; `orderId` là khóa nghiệp vụ; `occurredAt` cho biết thời điểm sự kiện xảy ra; `schemaVersion` hỗ trợ quản lý thay đổi hợp đồng. Đây là ví dụ tối giản, có thể bổ sung tiền tệ hoặc thông tin cần thiết khác theo hợp đồng của hệ thống.

### Các subscriber

Mỗi consumer function là một subscriber. Tên bean quyết định tên input binding:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumers {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            // Yêu cầu nghiệp vụ kho xử lý event.orderId()
        };
    }

    @Bean
    Consumer<OrderCreated> billing() {
        return event -> {
            // Tạo yêu cầu thanh toán cho event.orderId()
        };
    }
}
~~~

Khi ứng dụng có nhiều function bean, khai báo `spring.cloud.function.definition` giúp Spring Cloud Stream biết những hàm nào cần được kích hoạt làm endpoint. Trong ví dụ, `inventory;billing` kích hoạt cả hai consumer.

### Publisher dùng StreamBridge

Publisher gửi sự kiện qua output binding đã cấu hình:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(OrderCreated event) {
        boolean sent = streamBridge.send("orders-out-0", event);

        if (!sent) {
            throw new IllegalStateException(
                "Không thể gửi sự kiện OrderCreated"
            );
        }
    }
}
~~~

Tên `orders-out-0` trong lời gọi phải khớp với output binding đã cấu hình. Kết quả boolean cho biết thao tác gửi qua binding có thành công ở bước gửi hay không; nó không chứng minh tất cả subscriber đã nhận hoặc xử lý xong sự kiện.

Có thể dùng `Supplier<OrderCreated>` nếu ứng dụng chủ động cung cấp dữ liệu cho luồng đầu ra, hoặc `Function<A, B>` nếu cần nhận một thông điệp rồi phát hành thông điệp đã biến đổi. Dù dùng kiểu hàm nào, nguyên tắc pub/sub vẫn nằm ở destination và các subscription/group được cấu hình cho destination đó.

## 5. Destination và group được binder ánh xạ ra sao?

Spring Cloud Stream giữ nguyên mô hình binding ở cấp ứng dụng, còn binder chuyển cấu hình sang khái niệm tương ứng của broker.

| Khái niệm Spring Cloud Stream | Kafka binder | RabbitMQ binder | Pulsar binder |
|---|---|---|---|
| Destination | Topic | Exchange và các queue được liên kết | Topic |
| Consumer group | Kafka consumer group | Queue dành cho group, được liên kết với exchange | Subscription name |
| Chia tải trong group | Các consumer chia partition | Nhiều consumer cùng đọc queue | Phụ thuộc subscription type |
| Trạng thái đọc | Offset theo partition và group | Trạng thái queue, acknowledgement và message còn tồn | Trạng thái subscription/cursor |

Một publisher gửi tới destination `orders` không cần biết binder đang kết nối với Kafka, RabbitMQ hay Pulsar. Tuy nhiên, các chi tiết như tạo tài nguyên, xác nhận, lưu giữ, phân phối và thứ tự vẫn chịu ảnh hưởng của broker.

### Với Kafka

Destination thường ánh xạ tới một topic. Mỗi consumer group có offset riêng, vì vậy hai group độc lập có thể đọc cùng một topic mà không làm mất tiến độ của nhau. Các instance trong cùng group chia nhau partition; số partition và cách gán partition giới hạn mức song song của group.

Kafka bảo đảm thứ tự trong phạm vi một partition. Nếu các sự kiện liên quan đến cùng một đơn hàng cần giữ thứ tự, publisher nên dùng khóa phân vùng phù hợp, chẳng hạn `orderId`, để các sự kiện của đơn hàng đó đi vào cùng partition.

### Với RabbitMQ

Destination thường ánh xạ tới exchange. Binder tạo queue cho consumer group và liên kết queue đó với exchange. Các group độc lập có queue riêng nên có thể nhận cùng một thông điệp; nhiều consumer trong cùng group có thể cạnh tranh đọc queue của group.

Cần chú ý cấu hình queue bền vững, acknowledgement, prefetch và xử lý message bị từ chối hoặc đưa lại queue. Những thiết lập này ảnh hưởng đến khả năng phục hồi và phân phối tải.

### Với Pulsar

Destination ánh xạ tới topic và group ánh xạ tới subscription. Nhiều subscription độc lập có thể đọc cùng topic. Cách phân phối thông điệp giữa các consumer trong một subscription phụ thuộc subscription type và cấu hình của Pulsar binder.

Không nên giả định mọi binder có cùng hành vi mặc định. Khi chuyển broker, hãy kiểm tra lại cấu hình subscription, thứ tự, xác nhận, retry và lưu giữ.

## 6. Vòng đời một thông điệp pub/sub

Một luồng phát hành và tiêu thụ thường diễn ra theo các bước sau:

1. Dịch vụ nghiệp vụ xác định một sự kiện đã xảy ra, ví dụ đơn hàng được tạo thành công.
2. Publisher tạo payload theo hợp đồng sự kiện và gửi qua output binding.
3. Binder chuyển payload thành định dạng phù hợp, rồi gửi đến broker.
4. Broker định tuyến hoặc lưu thông điệp theo destination và các subscription/group đã đăng ký.
5. Mỗi group nhận thông điệp theo cơ chế của broker; các instance trong group chia sẻ công việc.
6. Subscriber xử lý thông điệp và xác nhận theo cơ chế acknowledgement hoặc offset của binder.
7. Nếu xử lý thất bại, hành vi retry, lưu giữ hoặc chuyển thông điệp sang dead-letter destination phụ thuộc cấu hình và broker.

Publisher thường không chờ tất cả subscriber hoàn thành công việc. Điều đó cho phép các dịch vụ hoạt động độc lập, nhưng cũng có nghĩa trạng thái nghiệp vụ ở các dịch vụ có thể cập nhật vào những thời điểm khác nhau. Đây là đặc tính nhất quán cuối cùng (eventual consistency) thường gặp trong kiến trúc hướng sự kiện.

Một subscriber mới chỉ có thể đọc lại sự kiện cũ nếu broker còn lưu dữ liệu và subscription/offset của subscriber được thiết lập phù hợp. Việc đăng ký một group mới không đồng nghĩa mọi broker sẽ tự động phát lại toàn bộ lịch sử; cần hiểu chính sách retention, offset hoặc cursor của hệ thống đang dùng.

## 7. Thiết kế hợp đồng sự kiện cho nhiều subscriber

Một sự kiện được nhiều dịch vụ sử dụng sẽ trở thành hợp đồng tích hợp giữa các thành phần. Vì vậy, hãy thiết kế payload với các nguyên tắc sau:

- **Diễn đạt sự kiện đã xảy ra:** ưu tiên tên như `OrderCreated`, `PaymentCaptured` hoặc `ShipmentDispatched`. Tên sự kiện nên phản ánh sự thật nghiệp vụ, không gắn với một subscriber cụ thể.
- **Có định danh ổn định:** dùng `eventId` để hỗ trợ ghi nhận, chống xử lý trùng và truy vết.
- **Mang khóa nghiệp vụ:** `orderId` giúp subscriber tìm đúng đối tượng và có thể làm khóa phân vùng.
- **Có thời điểm và phiên bản:** `occurredAt` và `schemaVersion` giúp phân tích lịch sử và quản lý thay đổi.
- **Giữ payload vừa đủ:** chỉ công bố dữ liệu cần thiết; tránh gửi nguyên entity persistence hoặc dữ liệu nội bộ không thuộc hợp đồng công khai.
- **Tương thích khi thay đổi:** ưu tiên thêm field tùy chọn có giá trị mặc định hợp lý; thay đổi tên, kiểu hoặc ý nghĩa field cần có chiến lược chuyển đổi và phối hợp consumer.

Nếu publisher và subscriber được triển khai độc lập, thay đổi schema cần được xem như thay đổi API. Nên có kiểm thử tương thích schema hoặc kiểm thử tích hợp giữa các phiên bản producer và consumer trước khi phát hành.

## 8. Các bảo đảm cần hiểu đúng

Pub/sub giúp phân phối thông điệp đến nhiều nhóm, nhưng không tự tạo ra một bảo đảm giao nhận giống nhau cho mọi broker và mọi cấu hình.

**Gửi thành công không đồng nghĩa xử lý hoàn tất.** Kết quả từ `StreamBridge.send` không phải bằng chứng rằng từng subscriber đã xử lý xong. Nếu nghiệp vụ cần biết subscriber đã hoàn tất, cần thiết kế một sự kiện phản hồi hoặc quy trình điều phối riêng.

**Thông điệp có thể được xử lý lặp.** Với cơ chế giao nhận ít nhất một lần (at-least-once), subscriber có thể nhận lại thông điệp khi lỗi xảy ra sau khi thực hiện tác động nghiệp vụ nhưng trước khi xác nhận. Handler nên idempotent: xử lý cùng một `eventId` nhiều lần không tạo ra tác động nghiệp vụ lặp ngoài ý muốn.

**Thứ tự có phạm vi.** Không nên giả định có thứ tự toàn cục giữa nhiều partition, queue hoặc subscription. Nếu thứ tự theo một thực thể quan trọng, hãy dùng khóa phù hợp và xác minh giới hạn thứ tự của binder.

**Gửi thông điệp và cập nhật cơ sở dữ liệu không tự động nguyên tử.** Nếu ứng dụng ghi đơn hàng vào database rồi gửi sự kiện, sự cố giữa hai thao tác có thể khiến dữ liệu và sự kiện không đồng bộ. Với yêu cầu tin cậy cao, có thể áp dụng transactional outbox hoặc cơ chế tích hợp giao dịch phù hợp.

**Subscriber cần có chiến lược lỗi.** Retry có giới hạn, dead-letter queue/topic, giám sát và quy trình phát lại giúp xử lý thông điệp lỗi. Các chủ đề này cần được cấu hình theo binder và kiểm tra trong môi trường gần production.

## 9. Kiểm thử luồng publish-subscribe

Nên kiểm thử ở nhiều cấp độ:

1. **Unit test cho handler:** gọi trực tiếp consumer function với một sự kiện mẫu; xác minh hành vi nghiệp vụ và khả năng xử lý lặp.
2. **Binding test:** dùng test binder của Spring Cloud Stream để xác minh ứng dụng gửi và nhận đúng binding, payload và header.
3. **Broker integration test:** chạy broker phù hợp, chẳng hạn bằng Testcontainers, để xác minh ánh xạ destination/group và hành vi thực tế của binder.
4. **Kiểm thử fan-out:** phát hành một sự kiện và xác minh hai group độc lập đều nhận được.
5. **Kiểm thử chia tải:** chạy nhiều instance cùng group và xác minh công việc được phân phối theo cơ chế broker.
6. **Kiểm thử lỗi:** mô phỏng subscriber dừng, xử lý thất bại, retry và phục hồi để xác minh thông điệp không bị mất ngoài chính sách đã chọn.

Unit test đơn lẻ không chứng minh được hành vi fan-out của broker. Đặc biệt, cần có kiểm thử tích hợp khi thay đổi binder hoặc cấu hình group.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng chung một group cho các dịch vụ cần nhận độc lập | Các dịch vụ chia nhau thông điệp; một dịch vụ có thể không nhận sự kiện mà nó cần | Tạo group riêng theo từng vai trò subscriber |
| Tạo group riêng cho từng replica chỉ để mở rộng | Mỗi replica có subscription độc lập và có thể nhận lại toàn bộ luồng | Cho các replica của cùng dịch vụ tham gia một group |
| Không cấu hình group ổn định | Hành vi subscription ẩn danh có thể không phù hợp khi restart hoặc triển khai nhiều instance | Đặt tên group rõ ràng cho consumer production |
| Cho rằng publisher chờ subscriber xử lý xong | Luồng nghiệp vụ phụ thuộc sai vào thời điểm phản hồi | Thiết kế acknowledgement hoặc sự kiện phản hồi nếu thực sự cần |
| Cho rằng mọi broker có cùng thứ tự và retry | Có thể xử lý sai khi đổi binder | Đọc và kiểm thử ngữ nghĩa của binder cụ thể |
| Handler không idempotent | Retry hoặc giao nhận lặp có thể tạo tác động nghiệp vụ trùng | Dùng event ID và cơ chế chống trùng phù hợp |
| Thay đổi schema không có kế hoạch | Consumer cũ có thể lỗi khi nhận payload mới | Quản lý phiên bản và kiểm thử tương thích |

## 11. Quy trình thực hành

Với bài toán `OrderCreated`, hãy triển khai theo trình tự:

1. Xác định những bộ phận thực sự cần nhận sự kiện và đặt group riêng cho từng bộ phận.
2. Thiết kế payload `OrderCreated` có `eventId`, `orderId`, `occurredAt` và phiên bản schema.
3. Cấu hình output binding `orders-out-0` trỏ đến destination `orders`.
4. Tạo các consumer function có tên `inventory` và `billing`, rồi cấu hình input binding tương ứng cùng group riêng.
5. Phát hành một sự kiện mẫu bằng `StreamBridge`.
6. Xác minh cả hai group đều nhận được sự kiện.
7. Tăng số instance của consumer kho nhưng giữ nguyên group `inventory`; quan sát cách broker chia tải.
8. Gửi lại cùng một `eventId` và xác minh handler không tạo tác động nghiệp vụ trùng.
9. Lặp lại kiểm thử với binder đang triển khai để xác nhận hành vi thực tế.

Khi hoàn thành, bạn cần giải thích được vì sao hai dịch vụ dùng hai group khác nhau sẽ cùng nhận một sự kiện, trong khi hai instance dùng chung một group chủ yếu chia nhau xử lý.

## Kết luận

Publish-subscribe cho phép một publisher phát hành sự kiện đến destination mà không cần biết danh sách subscriber. Trong Spring Cloud Stream, binding kết nối hàm ứng dụng với destination, còn consumer group xác định phạm vi subscription và tiến độ tiêu thụ độc lập. Các group khác nhau tạo ra khả năng phát tán; nhiều instance trong cùng group tạo ra khả năng chia tải.

Thiết kế đúng destination, group và hợp đồng sự kiện là nền tảng để các dịch vụ Spring Cloud Stream phối hợp độc lập. Khi triển khai, hãy kiểm chứng thêm ngữ nghĩa giao nhận, thứ tự, lưu giữ và retry của binder Kafka, RabbitMQ hoặc Pulsar mà hệ thống đang sử dụng.
