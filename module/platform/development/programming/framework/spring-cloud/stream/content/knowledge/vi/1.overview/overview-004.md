# Vai trò bên phát, bên nhận và hệ thống môi giới thông điệp

Trong một hệ thống xử lý sự kiện, ứng dụng thường cần thông báo cho ứng dụng khác biết một việc đã xảy ra: đơn hàng được tạo, thanh toán hoàn tất, hàng tồn kho thay đổi hoặc thiết bị gửi lên một số đo mới. Nếu bên phát gọi trực tiếp từng bên nhận, hai phía phải biết địa chỉ, giao diện và trạng thái hoạt động của nhau. Khi số lượng dịch vụ tăng, việc kết nối trực tiếp khiến thay đổi khó triển khai và lỗi ở một dịch vụ có thể lan sang các dịch vụ còn lại.

Một hệ thống môi giới thông điệp (message broker) tạo ra điểm trung gian cho việc trao đổi. Bên phát gửi thông điệp đến broker; broker tiếp nhận, định tuyến và phân phối thông điệp; bên nhận lấy thông điệp để xử lý. Spring Cloud Stream cung cấp mô hình lập trình để ứng dụng Java làm việc với luồng thông điệp qua các binding và binder. Nhờ vậy, mã nghiệp vụ có thể tập trung vào việc tạo, biến đổi hoặc xử lý sự kiện, còn cấu hình binder đảm nhiệm kết nối với Kafka, RabbitMQ, Pulsar hoặc một nền tảng được hỗ trợ khác.

## 1. Ba vai trò trong luồng thông điệp

### 1.1. Bên phát (producer)

Bên phát là thành phần tạo ra thông điệp và gửi thông điệp vào hệ thống. Nguồn phát có thể là:

- Một dịch vụ nghiệp vụ vừa hoàn tất thao tác, chẳng hạn dịch vụ đơn hàng phát sự kiện OrderCreated.
- Một tiến trình định kỳ đọc dữ liệu rồi phát bản tin tổng hợp.
- Một adapter nhận dữ liệu từ HTTP, cơ sở dữ liệu, thiết bị hoặc hệ thống bên ngoài.
- Một hàm xử lý đã nhận thông điệp trước đó và tạo ra thông điệp tiếp theo.

Bên phát chịu trách nhiệm xác định ý nghĩa của thông điệp, tạo payload đúng hợp đồng dữ liệu và gửi đến đích logic đã cấu hình. Một sự kiện nên mô tả một sự thật đã xảy ra, chẳng hạn OrderCreated hoặc PaymentCompleted. Sự kiện thường mang mã định danh đối tượng, thời điểm xảy ra và dữ liệu cần thiết để bên nhận hiểu sự việc. Nếu thông điệp biểu đạt yêu cầu bên khác thực hiện hành động, ví dụ ReserveInventory, nó gần với một lệnh (command) hơn là sự kiện. Phân biệt hai loại này giúp tên gọi và trách nhiệm của các dịch vụ rõ ràng.

Bên phát không cần biết mỗi thông điệp sẽ được xử lý bởi bao nhiêu dịch vụ. Nó gửi thông điệp đến một đích logic; broker và cấu hình định tuyến quyết định cách phân phối. Điều này giảm sự phụ thuộc trực tiếp giữa các dịch vụ, nhưng không loại bỏ trách nhiệm thiết kế hợp đồng dữ liệu và xử lý lỗi khi gửi.

Trong mô hình hàm của Spring Cloud Stream, một bean Supplier có thể đóng vai trò nguồn phát. Supplier được framework gọi theo cơ chế poll để lấy dữ liệu và đẩy dữ liệu ra output binding. Với thao tác phát sinh từ một sự kiện bên ngoài, chẳng hạn một request HTTP, ứng dụng cũng có thể gửi qua StreamBridge để đưa dữ liệu vào output binding. Vì vậy, Supplier phù hợp với nguồn có thể được thăm dò; StreamBridge phù hợp khi mã ứng dụng chủ động quyết định thời điểm phát.

### 1.2. Bên nhận (consumer)

Bên nhận đăng ký nhận thông điệp từ một đích và thực hiện công việc tương ứng. Ví dụ:

- Dịch vụ kho nhận OrderCreated để kiểm tra và giữ hàng.
- Dịch vụ thanh toán nhận PaymentRequested để gọi cổng thanh toán.
- Dịch vụ thông báo nhận ShipmentDispatched để gửi email hoặc tin nhắn.
- Dịch vụ phân tích nhận các sự kiện giao dịch để cập nhật số liệu.

Bên nhận chịu trách nhiệm kiểm tra dữ liệu đầu vào, áp dụng quy tắc nghiệp vụ, ghi nhận kết quả và xử lý các lỗi có thể phục hồi. Bên nhận nên có khả năng xử lý lặp an toàn. Trong hệ thống phân tán, một thông điệp có thể được giao lại khi ứng dụng lỗi sau khi đã thực hiện một phần công việc nhưng trước khi broker ghi nhận việc xử lý hoàn tất. Nếu xử lý lại làm phát sinh thanh toán hoặc trừ kho lần thứ hai, hệ thống sẽ tạo ra sai lệch nghiệp vụ.

Spring Cloud Stream biểu diễn bên nhận cuối cùng bằng bean Consumer. Nếu cần biến đổi thông điệp rồi phát kết quả sang đích khác, dùng Function: hàm nhận đầu vào, thực hiện xử lý và trả về đầu ra. Function vì vậy có thể vừa là bên nhận của một luồng vừa là bên phát của luồng tiếp theo.

### 1.3. Hệ thống môi giới thông điệp (message broker)

Broker là hạ tầng trung gian tiếp nhận và phân phối thông điệp. Tùy sản phẩm và cấu hình, broker có thể cung cấp các khả năng:

- Tiếp nhận và lưu đệm thông điệp để bên nhận xử lý vào thời điểm phù hợp.
- Định tuyến thông điệp đến topic, queue hoặc subscription tương ứng.
- Phân phối cùng một luồng dữ liệu cho nhiều nhóm dịch vụ độc lập.
- Lưu giữ thông điệp trong một khoảng thời gian hoặc cho đến khi có xác nhận.
- Phân vùng dữ liệu để tăng khả năng xử lý song song.
- Hỗ trợ xác nhận, thử lại, lưu thông điệp lỗi và các cơ chế bảo đảm giao nhận.

Broker giúp tách thời điểm gửi khỏi thời điểm xử lý. Khi một bên nhận tạm ngừng, thông điệp có thể được giữ lại để xử lý sau nếu loại broker và cấu hình lưu trữ hỗ trợ điều đó. Tuy nhiên, broker không tự hiểu quy tắc nghiệp vụ. Nó không thể biết một khoản thanh toán đã được ghi nhận trong cơ sở dữ liệu hay chưa, và cũng không tự bảo đảm một thao tác nghiệp vụ chỉ xảy ra đúng một lần.

Ba vai trò có thể nằm trong ba hệ thống riêng, nhưng không nhất thiết phải là ba ứng dụng. Một ứng dụng có thể vừa phát vừa nhận thông điệp; broker thường là hạ tầng độc lập nằm ngoài ứng dụng và được nhiều dịch vụ cùng sử dụng.

## 2. Thông điệp đi qua hệ thống như thế nào?

Xét ví dụ khi dịch vụ đơn hàng tạo đơn mới. Dịch vụ này phát OrderCreated. Dịch vụ kho nhận sự kiện, kiểm tra tồn kho và phát ReservationRequested. Một dịch vụ khác nhận thông điệp đó để thực hiện việc giữ hàng.

~~~mermaid
flowchart LR
    P["Dịch vụ đơn hàng<br/>Producer"] -->|"OrderCreated"| B[("Message broker")]
    B -->|"Phân phối theo đích"| C["Dịch vụ kho<br/>Consumer / Function"]
    C -->|"ReservationRequested"| B
    B -->|"Thông điệp tiếp theo"| N["Dịch vụ giữ hàng<br/>Consumer"]
~~~

Quy trình cơ bản gồm các bước:

1. Bên phát tạo payload và các metadata cần thiết, sau đó gửi đến output binding.
2. Binding chuyển thông điệp qua binder tương ứng để đến destination trên broker.
3. Broker tiếp nhận và lưu hoặc định tuyến thông điệp theo cơ chế của nó.
4. Input binding của bên nhận lấy thông điệp từ destination đã cấu hình.
5. Spring Cloud Stream chuyển payload thành kiểu dữ liệu mà hàm xử lý khai báo, nếu cấu hình chuyển đổi nội dung phù hợp.
6. Consumer xử lý và kết thúc luồng, hoặc Function trả về một thông điệp mới để phát ra output binding.
7. Kết quả xác nhận, thử lại hoặc chuyển thông điệp lỗi phụ thuộc vào binder, broker và cấu hình xử lý.

Việc gửi thành công từ ứng dụng chỉ cho biết một bước của quy trình đã hoàn tất. Nó không đồng nghĩa mọi bên nhận đã xử lý thành công. Muốn theo dõi toàn bộ luồng, cần có mã tương quan (correlation ID), log, metric và cơ chế quan sát trạng thái ở từng dịch vụ.

## 3. Spring Cloud Stream kết nối ứng dụng với broker

Spring Cloud Stream cung cấp một lớp trừu tượng quanh việc gửi và nhận thông điệp. Ứng dụng khai báo các hàm xử lý và các binding logic; binder kết nối binding đó với công nghệ môi giới cụ thể.

| Thành phần | Vai trò |
|---|---|
| Supplier | Cung cấp dữ liệu đầu ra, thường được framework gọi theo chu kỳ poll |
| Function | Nhận dữ liệu đầu vào, biến đổi hoặc xử lý rồi trả về dữ liệu đầu ra |
| Consumer | Nhận và xử lý dữ liệu, không tạo đầu ra cho luồng đó |
| Binding | Liên kết một đầu vào hoặc đầu ra logic của hàm với một destination |
| Destination | Đích vật lý hoặc logic trên broker, ví dụ topic hay queue |
| Binder | Adapter kết nối binding với broker cụ thể như Kafka, RabbitMQ hoặc Pulsar |

### 3.1. Supplier, Function và Consumer

Các bean hàm được Spring Cloud Function nhận diện theo kiểu khai báo:

~~~java
@Bean
Supplier<PurchaseCreated> purchaseSource() {
    return () -> new PurchaseCreated(
        UUID.randomUUID().toString(),
        Instant.now()
    );
}
~~~

PurchaseSource minh họa một nguồn phát. Framework poll Supplier và gửi giá trị trả về đến output binding. Trong ứng dụng thực tế, dữ liệu thường đến từ một nguồn có ý nghĩa nghiệp vụ; không nên phát dữ liệu giả lập theo chu kỳ khi chưa cấu hình rõ tần suất và điều kiện phát.

~~~java
@Bean
Function<PurchaseCreated, ReservationRequested> reserveInventory() {
    return purchase -> new ReservationRequested(
        purchase.purchaseId(),
        Instant.now()
    );
}
~~~

ReserveInventory nhận một sự kiện mua hàng, xử lý và tạo thông điệp yêu cầu giữ hàng. Đầu vào và đầu ra của Function được nối với hai binding riêng.

~~~java
@Bean
Consumer<ReservationRequested> notifyWarehouse() {
    return request -> {
        // Gọi nghiệp vụ tiếp nhận yêu cầu giữ hàng.
        log.info("Nhận yêu cầu giữ hàng cho đơn {}", request.purchaseId());
    };
}
~~~

NotifyWarehouse nhận thông điệp và thực hiện tác vụ cuối của luồng. Nếu tác vụ cần gọi dịch vụ khác hoặc ghi dữ liệu, phần xử lý phải tính đến timeout, lỗi tạm thời và khả năng thông điệp được giao lại.

Các kiểu dữ liệu ví dụ có thể khai báo bằng record Java:

~~~java
public record PurchaseCreated(
    String purchaseId,
    Instant createdAt
) {}

public record ReservationRequested(
    String purchaseId,
    Instant requestedAt
) {}
~~~

Ví dụ trên tập trung vào hình dạng hàm; các import, cấu hình log và phần nghiệp vụ được lược bỏ. Trong một hệ thống thực tế, producer và consumer thường nằm ở các ứng dụng hoặc dịch vụ riêng.

### 3.2. Binding và tên binding

Binding là tên logic mà Spring Cloud Stream dùng để nối một hàm với destination. Với các bean hàm độc lập, tên binding được suy ra từ tên bean và hướng dữ liệu:

| Bean hàm | Binding | Hướng |
|---|---|---|
| purchaseSource | purchaseSource-out-0 | Đầu ra của Supplier |
| reserveInventory | reserveInventory-in-0 | Đầu vào của Function |
| reserveInventory | reserveInventory-out-0 | Đầu ra của Function |
| notifyWarehouse | notifyWarehouse-in-0 | Đầu vào của Consumer |

Hậu tố in biểu thị đầu vào, out biểu thị đầu ra; số 0 là chỉ số của cổng dữ liệu. Cách đặt tên này giúp một hàm có thể khai báo nhiều đầu vào hoặc đầu ra khi cần. Tên binding là định danh cấu hình trong ứng dụng, còn destination là tên tài nguyên mà binder ánh xạ sang broker.

Ví dụ cấu hình cho dịch vụ xử lý yêu cầu giữ hàng:

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: purchases.created
          group: inventory-service
          content-type: application/json
        reserveInventory-out-0:
          destination: inventory.reservation.requested
          content-type: application/json
~~~

Trong cấu hình này:

- reserveInventory là hàm được kích hoạt.
- reserveInventory-in-0 nhận thông điệp từ destination purchases.created.
- inventory-service là consumer group có tên ổn định của dịch vụ kho.
- reserveInventory-out-0 gửi kết quả đến inventory.reservation.requested.
- content-type khai báo định dạng nội dung để framework lựa chọn cách chuyển đổi phù hợp.

Producer và consumer có thể dùng cùng tên destination để trao đổi nhưng không cần dùng chung tên binding. Tên binding thuộc cấu hình của từng ứng dụng; tên destination là điểm gặp nhau trên broker. Khi đổi destination, cần phối hợp thay đổi cấu hình và kế hoạch chuyển đổi dữ liệu để tránh làm gián đoạn các bên đang sử dụng.

### 3.3. Binder và tính độc lập với công nghệ broker

Binder triển khai cách binding giao tiếp với broker. Ứng dụng có thể sử dụng binder Kafka, RabbitMQ hoặc Pulsar thông qua dependency tương ứng và cấu hình kết nối. Nhờ lớp trừu tượng này, mã Supplier, Function và Consumer ít phụ thuộc vào API riêng của broker.

Tuy nhiên, tính độc lập không có nghĩa mọi broker có cùng ngữ nghĩa hoặc cùng tính năng. Kafka tổ chức dữ liệu thành topic và partition; RabbitMQ định tuyến qua exchange đến queue; Pulsar cung cấp topic và subscription với nhiều chế độ nhận. Các tùy chọn về lưu giữ, thứ tự, xác nhận, retry, DLQ, transaction và khả năng mở rộng vẫn phải được hiểu theo binder và broker đang sử dụng.

| Broker | Khái niệm thường gặp | Cách hình dung |
|---|---|---|
| Apache Kafka | Topic, partition, offset, consumer group | Luồng bản ghi được lưu theo partition; consumer đọc theo offset |
| RabbitMQ | Exchange, queue, binding, routing key | Exchange định tuyến thông điệp đến queue; consumer lấy thông điệp từ queue |
| Apache Pulsar | Topic, subscription, subscription type | Consumer nhận dữ liệu qua subscription; loại subscription quyết định cách phân phối |

Khi triển khai, cần thêm đúng binder vào classpath, cấu hình địa chỉ broker và các thuộc tính xác thực, TLS, destination cùng tùy chọn riêng của binder. Không nên sao chép nguyên cấu hình của Kafka sang RabbitMQ hoặc Pulsar chỉ vì tên binding giống nhau.

## 4. Consumer group, phân vùng và khả năng mở rộng

Consumer group biểu diễn một nhóm consumer cùng xử lý một luồng logic. Cách broker triển khai nhóm có khác biệt, nhưng mục tiêu phổ biến là cho phép nhiều instance cùng chia tải.

Với Kafka, các consumer trong cùng một group chia nhau các partition của topic. Tại một thời điểm, mỗi partition được gán cho tối đa một consumer trong cùng group. Vì vậy, nếu topic có bốn partition thì một group thường không thể tận dụng hơn bốn consumer để đọc song song từ topic đó. Consumer dư vẫn có thể chạy nhưng không được gán partition. Khi tăng hoặc giảm số instance, Kafka có thể phân công lại partition (rebalance).

Hai group Kafka khác nhau có thể đọc cùng một topic độc lập. Ví dụ inventory-service và analytics-service đều nhận được các sự kiện đơn hàng, mỗi group duy trì vị trí đọc riêng. Trong cùng một group, các instance chia tải; giữa các group, mỗi dịch vụ có luồng tiêu thụ riêng.

Với RabbitMQ, các consumer cùng đọc một queue thường cạnh tranh nhận các thông điệp trong queue đó. Muốn nhiều dịch vụ độc lập đều nhận được bản sao của một sự kiện, thường cần các queue riêng được định tuyến từ exchange. Với Pulsar, subscription là điểm quản lý việc tiêu thụ; Exclusive, Failover, Shared và Key_Shared có quy tắc phân phối khác nhau. Do đó, không nên suy diễn rằng consumer group của Spring Cloud Stream sẽ có hành vi giống hệt nhau trên mọi binder.

Trong Spring Cloud Stream, thuộc tính group giúp đặt tên nhóm tiêu thụ ổn định. Với dịch vụ chạy nhiều instance, các instance thường dùng cùng một group để chia tải theo cách binder hỗ trợ. Nếu bỏ group, binder có thể tạo subscription hoặc queue ẩn danh; hành vi và thời gian tồn tại phụ thuộc vào broker. Môi trường production nên cấu hình group có chủ đích để kiểm soát việc phân phối và khả năng tiếp tục đọc sau khi ứng dụng khởi động lại.

### 4.1. Partition key và thứ tự xử lý

Partitioning chia một destination thành các phần để nhiều consumer có thể xử lý song song. Khi phát thông điệp, partition key thường được chọn từ một thuộc tính nghiệp vụ như purchaseId hoặc customerId. Các thông điệp có cùng khóa có thể được đưa vào cùng partition, nhờ đó giữ thứ tự tương đối trong phạm vi partition theo bảo đảm của broker.

Không nên hiểu rằng toàn bộ topic luôn có một thứ tự tuyệt đối khi có nhiều partition. Nếu hai sự kiện thuộc hai partition khác nhau, consumer có thể xử lý chúng đồng thời và hoàn tất theo thứ tự khác nhau. Khi nghiệp vụ yêu cầu thứ tự theo đơn hàng hoặc tài khoản, cần chọn khóa phù hợp và bảo đảm các sự kiện liên quan dùng cùng khóa.

Partition key cũng ảnh hưởng đến phân bố tải. Nếu mọi thông điệp đều dùng một khóa phổ biến, một partition có thể trở thành điểm nóng trong khi các partition khác ít việc. Cần cân nhắc số lượng partition, phân bố khóa và tốc độ tiêu thụ khi thiết kế.

## 5. Hợp đồng thông điệp và tương thích schema

Thông điệp thường có hai phần:

- Payload: dữ liệu nghiệp vụ, ví dụ mã đơn hàng, số tiền hoặc trạng thái thanh toán.
- Header: metadata phục vụ truyền tải và xử lý, ví dụ content type, correlation ID, mã định danh thông điệp, thời điểm phát hoặc thông tin định tuyến.

Spring Messaging biểu diễn thông điệp bằng Message với payload và headers. Khi cần tự đặt header, ứng dụng có thể dùng MessageBuilder; nếu chỉ trao đổi một đối tượng đơn giản, framework có thể thực hiện chuyển đổi payload theo content type đã cấu hình.

Hợp đồng dữ liệu là cam kết giữa producer và các consumer. Nếu producer đổi tên trường hoặc thay đổi ý nghĩa một giá trị, consumer cũ có thể không còn xử lý đúng. Một số nguyên tắc giúp giảm rủi ro:

1. Dùng tên sự kiện và trường dữ liệu có ý nghĩa rõ ràng.
2. Thêm trường mới theo cách tương thích, chẳng hạn trường tùy chọn có giá trị mặc định hợp lý.
3. Tránh đổi kiểu dữ liệu hoặc ý nghĩa của trường đang được consumer sử dụng.
4. Có chiến lược phiên bản schema khi thay đổi không thể tương thích.
5. Kiểm thử producer mới với consumer hiện tại trước khi triển khai đồng loạt.

JSON thường được dùng vì dễ quan sát và hỗ trợ nhiều ngôn ngữ, nhưng hệ thống có thể chọn Avro, Protobuf hoặc định dạng khác. Schema Registry, nếu được tích hợp, có thể quản lý phiên bản và kiểm tra quy tắc tương thích. Broker tự thân không nhất thiết hiểu hoặc xác thực schema; việc kiểm tra phụ thuộc vào serializer, binder và thành phần quản lý schema được cấu hình.

Không nên đưa toàn bộ đối tượng nội bộ của một dịch vụ vào payload. Hãy chỉ công bố dữ liệu cần thiết cho bên nhận và xem sự kiện đã phát là hợp đồng công khai. Cách này giảm phụ thuộc vào cấu trúc cơ sở dữ liệu và mô hình nội bộ của producer.

## 6. Giao nhận, xác nhận, retry và Dead Letter Queue

Khi thiết kế hệ thống thông điệp, cần xác định điều gì xảy ra nếu producer, broker hoặc consumer gặp lỗi. Ba cách mô tả ngữ nghĩa giao nhận thường gặp là:

| Ngữ nghĩa | Ý nghĩa | Hệ quả cần xử lý |
|---|---|---|
| At-most-once | Thông điệp được xử lý không quá một lần theo cơ chế giao nhận | Có thể mất thông điệp nếu lỗi xảy ra trước khi xử lý hoàn tất |
| At-least-once | Hệ thống cố gắng giao cho đến khi được xác nhận | Có thể nhận hoặc xử lý trùng, consumer cần idempotent |
| Exactly-once | Hạn chế kết quả trùng lặp trong một phạm vi xử lý được hỗ trợ | Phạm vi bảo đảm phụ thuộc broker, binder, transaction và hệ thống đích |

At-least-once thường là lựa chọn thực tế cho nhiều luồng nghiệp vụ vì ưu tiên không mất thông điệp. Đổi lại, consumer cần xử lý lặp an toàn. Một cách phổ biến là dùng message ID hoặc business key để kiểm tra một sự kiện đã được áp dụng hay chưa. Khi ghi dữ liệu và đánh dấu sự kiện đã xử lý, cần thiết kế transaction để tránh trạng thái một việc đã ghi nhưng dấu xử lý chưa được lưu, hoặc ngược lại.

Exactly-once cần được hiểu trong phạm vi cụ thể. Kafka có cơ chế transaction và hỗ trợ một số luồng xử lý đúng một lần trong ranh giới Kafka. Điều đó không tự động khiến một lời gọi HTTP, một lần gửi email hoặc một transaction ở cơ sở dữ liệu ngoài Kafka trở thành exactly-once. Với nghiệp vụ cập nhật database rồi phát sự kiện, có thể cân nhắc Transactional Outbox để lưu thay đổi nghiệp vụ và bản ghi sự kiện trong cùng transaction; một tiến trình riêng phát bản ghi đó lên broker. Consumer vẫn nên có cơ chế chống xử lý trùng.

### 6.1. Retry

Retry phù hợp với lỗi tạm thời như timeout mạng, dịch vụ phụ thuộc đang quá tải hoặc broker tạm thời không sẵn sàng. Cần giới hạn số lần thử, khoảng chờ và thời gian tổng thể. Backoff tăng dần, có thể kèm jitter, giúp tránh việc nhiều consumer cùng thử lại liên tục và làm hệ thống quá tải hơn.

Không phải lỗi nào cũng nên retry. Dữ liệu sai định dạng, thiếu trường bắt buộc hoặc vi phạm quy tắc nghiệp vụ thường là lỗi không thể tự phục hồi bằng cách gửi lại nguyên thông điệp. Nếu retry vô hạn, một thông điệp lỗi có thể chiếm tài nguyên và chặn tiến trình xử lý. Cấu hình retry trong Spring Cloud Stream có thể đặt theo binding; số lần thử và cách chờ cần được chọn dựa trên thời gian phục hồi của dịch vụ phụ thuộc.

### 6.2. Dead Letter Queue (DLQ)

DLQ là nơi lưu các thông điệp không xử lý được sau khi đã áp dụng chính sách retry. Tùy binder, cơ chế này có thể được gọi là dead-letter queue hoặc dead-letter topic. DLQ giúp tách thông điệp lỗi khỏi luồng chính để các thông điệp hợp lệ tiếp tục được xử lý.

DLQ chỉ hữu ích khi có quy trình vận hành đi kèm. Cần ghi nhận lý do lỗi, thời điểm, số lần thử và thông tin định danh; cảnh báo khi số lượng thông điệp lỗi tăng; xác định người chịu trách nhiệm điều tra; và có quy trình sửa dữ liệu hoặc mã xử lý trước khi phát lại. Phát lại một thông điệp vào luồng chính mà không kiểm tra có thể gây lặp tác vụ hoặc tái tạo lỗi.

Tên queue/topic DLQ, quyền truy cập và cách bật DLQ phụ thuộc binder. Ví dụ, Kafka binder và RabbitMQ binder có thuộc tính cấu hình riêng. Vì vậy, cần đọc cấu hình của binder đang dùng và kiểm thử tình huống lỗi thực tế, thay vì cho rằng chỉ cần khai báo một thuộc tính chung là mọi broker có cùng hành vi.

## 7. Xử lý trạng thái với Kafka Streams

Các hàm Supplier, Function và Consumer phù hợp với nhiều luồng thông điệp đơn giản. Khi cần tổng hợp theo cửa sổ thời gian, nối hai luồng, cập nhật bảng trạng thái hoặc tính toán liên tục theo khóa, Kafka Streams cung cấp mô hình xử lý luồng có trạng thái.

Kafka Streams binder của Spring Cloud Stream cho phép ứng dụng khai báo các hàm làm việc với kiểu dữ liệu như KStream, KTable hoặc GlobalKTable. Đây là binder chuyên biệt, có dependency và cấu hình riêng; không nên nhầm với Kafka message binder thông thường.

- KStream biểu diễn chuỗi bản ghi sự kiện. Mỗi bản ghi là một dữ liệu được xử lý theo luồng.
- KTable biểu diễn trạng thái được cập nhật theo khóa. Bản ghi mới có thể thay thế trạng thái trước đó của cùng khóa.
- GlobalKTable là bảng trạng thái được sao chép đến các instance theo cơ chế Kafka Streams, hữu ích cho một số phép tra cứu kết hợp.
- State store lưu trạng thái cục bộ phục vụ phép tính. Changelog topic có thể được dùng để khôi phục trạng thái khi instance khởi động lại hoặc chuyển vị trí xử lý.

Ví dụ, hệ thống bán hàng có thể gom tổng doanh thu theo cửa sổ năm phút. Khóa đơn hàng hoặc cửa hàng quyết định cách phân vùng; cửa sổ xác định khoảng thời gian gom nhóm; kết quả được phát thành một luồng tổng hợp. Khi dùng xử lý có trạng thái, cần thiết kế khóa, thời gian sự kiện, chính sách cửa sổ, lưu trạng thái và khả năng khôi phục. Cũng cần kiểm tra cách xử lý sự kiện đến muộn và dữ liệu trùng.

Kafka Streams phù hợp khi bài toán cần xử lý liên tục và giữ trạng thái gần với luồng dữ liệu. Nếu chỉ nhận một thông điệp rồi gọi một nghiệp vụ độc lập, Function hoặc Consumer thông thường thường dễ triển khai và vận hành hơn.

## 8. Kiểm thử và vận hành

Một luồng thông điệp nên được kiểm thử ở nhiều cấp:

| Cấp kiểm thử | Mục tiêu | Công cụ hoặc cách làm |
|---|---|---|
| Kiểm thử hàm | Xác minh Supplier, Function hoặc Consumer với dữ liệu đầu vào xác định | Gọi trực tiếp bean, dùng mock cho phụ thuộc nghiệp vụ |
| Kiểm thử binding | Xác minh payload đi vào và đi ra đúng binding | Spring Cloud Stream Test Binder với InputDestination và OutputDestination |
| Kiểm thử tích hợp broker | Kiểm tra cấu hình binder, group, partition, retry và DLQ trên broker thật | Kafka, RabbitMQ hoặc Pulsar chạy bằng môi trường kiểm thử như Testcontainers |
| Kiểm thử hợp đồng | Xác minh producer và consumer hiểu cùng cấu trúc thông điệp | Schema hoặc contract test giữa các dịch vụ |

Test Binder giúp kiểm tra luồng trong JVM mà không cần khởi chạy broker thật. Nó hữu ích để xác minh hàm và binding, nhưng không thay thế kiểm thử tích hợp cho các đặc tính riêng của broker như rebalance, xác nhận, thứ tự, transaction hoặc cấu hình DLQ. Với các tính năng đó, cần kiểm thử bằng broker tương ứng.

Khi vận hành, nên theo dõi ít nhất:

- Tốc độ thông điệp được phát và tiêu thụ, cùng độ trễ xử lý.
- Consumer lag hoặc độ dài queue để phát hiện bên nhận không theo kịp.
- Số lần retry, số thông điệp vào DLQ và nguyên nhân lỗi phổ biến.
- Tỷ lệ lỗi, timeout và thời gian xử lý của từng consumer.
- Correlation ID hoặc message ID để nối log giữa producer, broker và consumer.
- Thay đổi partition, rebalance và tình trạng kết nối broker.

Không nên ghi toàn bộ payload vào log nếu payload có dữ liệu nhạy cảm. Hãy ghi mã định danh, loại sự kiện và thông tin chẩn đoán đủ dùng; áp dụng chính sách bảo vệ dữ liệu của hệ thống.

## 9. Những lỗi thiết kế thường gặp

**Gắn chặt producer với từng consumer.** Nếu producer gọi trực tiếp từng dịch vụ, mỗi lần thêm consumer phải sửa producer và xử lý thêm các lỗi kết nối. Đưa thông điệp qua broker giúp các bên độc lập hơn.

**Dùng một consumer group cho các dịch vụ cần nhận bản sao độc lập.** Trong Kafka, các consumer cùng group chia partition nên mỗi bản ghi không được phát riêng cho từng instance trong group. Nếu hai dịch vụ cần cùng xử lý mọi sự kiện, chúng cần các group độc lập.

**Tăng số consumer mà không xem số partition.** Với Kafka, số consumer hữu ích trong một group bị giới hạn bởi số partition có thể gán. Cần cân đối partition và tải dự kiến.

**Giả định thông điệp chỉ đến một lần.** Retry, rebalance hoặc lỗi trong lúc xác nhận có thể khiến thông điệp được giao lại. Consumer cần idempotency và cách ghi nhận trạng thái nhất quán.

**Thay đổi schema mà không kiểm tra consumer cũ.** Producer có thể triển khai trước consumer hoặc ngược lại. Thay đổi hợp đồng phải có kế hoạch tương thích và triển khai theo thứ tự phù hợp.

**Coi DLQ là nơi lưu lỗi rồi bỏ quên.** Nếu không có cảnh báo, người phụ trách và quy trình phát lại, DLQ chỉ chuyển lỗi ra khỏi tầm nhìn của luồng chính.

**Cho rằng binder làm mọi broker giống nhau.** Binding thống nhất cách ứng dụng kết nối, nhưng group, partition, xác nhận, lưu giữ và DLQ vẫn mang ngữ nghĩa riêng của broker.

## 10. Cách xác định trách nhiệm khi thiết kế một luồng mới

Trước khi triển khai, nhóm phát triển nên trả lời các câu hỏi sau:

1. Sự kiện nào đã xảy ra và dịch vụ nào sở hữu sự kiện đó?
2. Những dịch vụ nào cần nhận sự kiện, và mỗi dịch vụ cần một bản sao độc lập hay chỉ cần chia tải giữa các instance?
3. Destination, binding và binder nào sẽ được sử dụng?
4. Khóa phân vùng nào giữ được thứ tự mà nghiệp vụ yêu cầu?
5. Payload và header nào tạo thành hợp đồng dữ liệu? Cách quản lý phiên bản schema ra sao?
6. Lỗi nào có thể retry, retry bao nhiêu lần và thông điệp lỗi được đưa đến DLQ nào?
7. Consumer chống xử lý trùng như thế nào? Ranh giới transaction nằm ở đâu?
8. Chỉ số, log, cảnh báo và quy trình phát lại nào giúp vận hành luồng?

Khi trách nhiệm được xác định rõ, producer có thể tập trung công bố sự kiện đúng hợp đồng; broker tiếp nhận và phân phối theo cấu hình; consumer xử lý độc lập và có khả năng phục hồi. Spring Cloud Stream kết nối ba phần này qua Supplier, Function, Consumer, binding và binder, đồng thời cho phép nhóm phát triển lựa chọn broker phù hợp với yêu cầu về lưu giữ, định tuyến, thứ tự và khả năng mở rộng.
