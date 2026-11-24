# Tên binding và cấu hình đầu cuối của hàm ghép

Spring Cloud Stream dùng mô hình hàm của Spring Cloud Function để kết nối logic xử lý với broker. Khi một ứng dụng ghép nhiều function bean thành một chuỗi, Spring Cloud Stream xem chuỗi đó như một endpoint hàm có đầu vào và đầu ra bên ngoài. Tên binding được suy ra từ biểu thức ghép, vì vậy cấu hình destination, group và content type phải dùng đúng tên binding của toàn chuỗi.

Bài học này hướng dẫn cách đặt tên và cấu hình binding cho function composition từ lúc khai báo bean đến khi message đi qua broker. Bạn sẽ phân biệt ghép hàm bằng dấu | với khai báo nhiều hàm độc lập bằng dấu ;, dùng alias để đặt tên binding dễ quản lý và xác định khi nào các bước xử lý chạy trong cùng tiến trình hay trao đổi qua destination riêng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách Spring Cloud Function ghép nhiều function bean thành một function.
- Phân biệt dấu | dùng để composition với dấu ; dùng để khai báo nhiều function độc lập.
- Suy ra tên input binding và output binding của một function ghép.
- Dùng binding alias để thay tên dài của function composition bằng tên cấu hình ngắn, ổn định.
- Cấu hình end-to-end destination, group, content type và binder cho một chuỗi hàm.
- Phân biệt composition trong cùng ứng dụng với pipeline có broker ở giữa các stage.
- Kiểm thử cả logic ghép hàm và cấu hình binding thực tế.

## 1. Function composition hoạt động như thế nào?

Function composition là cách nối đầu ra của một hàm vào đầu vào của hàm tiếp theo. Nếu hàm đầu tiên có kiểu Function<A, B> và hàm kế tiếp có kiểu Function<B, C>, ta có thể ghép chúng thành một hàm có kiểu Function<A, C>.

Ví dụ xử lý đơn hàng:

1. enrichOrder nhận OrderCreated và tạo EnrichedOrder.
2. validateOrder nhận EnrichedOrder và tạo ValidatedOrder.
3. createNotification nhận ValidatedOrder và tạo NotificationRequested.

~~~mermaid
flowchart LR
    A["OrderCreated"] --> B["enrichOrder"]
    B --> C["EnrichedOrder"]
    C --> D["validateOrder"]
    D --> E["ValidatedOrder"]
    E --> F["createNotification"]
    F --> G["NotificationRequested"]
~~~

Spring Cloud Function cho phép khai báo chuỗi này bằng biểu thức:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder|createNotification
~~~

Dấu | yêu cầu framework ghép các function theo thứ tự từ trái sang phải. Message đi vào enrichOrder, kết quả được chuyển trực tiếp cho validateOrder, sau đó tiếp tục đến createNotification.

Các function phải có kiểu đầu ra và đầu vào tương thích. Nếu enrichOrder trả về EnrichedOrder nhưng validateOrder nhận String, composition không thể hoạt động nếu không có bước chuyển đổi rõ ràng ở giữa.

### Composition khác với nhiều function độc lập

Dấu chấm phẩy ; khai báo nhiều function cần kích hoạt độc lập:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory;billing;notification
~~~

Trong trường hợp này, inventory, billing và notification là ba endpoint function riêng. Mỗi function có binding riêng và có thể kết nối tới destination riêng. Dấu ; không nối đầu ra của function trước vào đầu vào của function sau.

| Biểu thức | Ý nghĩa | Binding |
|---|---|---|
| enrichOrder\|validateOrder\|createNotification | Một function ghép gồm ba bước | Một input và một output cho toàn chuỗi trong ví dụ Function–Function–Function |
| inventory;billing;notification | Ba function độc lập | Mỗi function có binding riêng |
| source\|normalize\|publish | Một chuỗi bắt đầu bằng Supplier và kết thúc bằng Function | Đầu vào ngoài không có; có output binding |
| parse\|validate\|store | Một chuỗi kết thúc bằng Consumer | Có input binding; không có output binding do Consumer là điểm cuối |

Composition là luồng gọi hàm trong cùng ứng dụng. Các bước trung gian không tự tạo topic hoặc queue riêng. Nếu cần triển khai từng stage độc lập, scale riêng hoặc lưu message giữa các stage, hãy cấu hình các function độc lập và nối chúng qua destination của broker.

## 2. Tên bean và tên binding của function ghép

Spring Cloud Stream suy ra tên binding từ tên function được kích hoạt. Với function đơn:

- Supplier<T> tên orderSource tạo output binding orderSource-out-0.
- Function<I, O> tên normalizeOrder tạo normalizeOrder-in-0 và normalizeOrder-out-0.
- Consumer<T> tên recordOrder tạo input binding recordOrder-in-0.

Với function ghép, tên các function bean được nối theo đúng biểu thức composition. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder|createNotification
~~~

Tên binding bên ngoài của chuỗi là:

| Hướng | Tên binding mặc định |
|---|---|
| Input | enrichOrder\|validateOrder\|createNotification-in-0 |
| Output | enrichOrder\|validateOrder\|createNotification-out-0 |

Hai binding này đại diện cho biên ngoài của toàn chuỗi. Không có binding mặc định riêng cho validateOrder ở giữa, vì đầu ra của nó được chuyển trực tiếp sang hàm kế tiếp trong cùng tiến trình.

Tên binding có chứa ký tự |. Khi khai báo trong YAML, nên đặt tên key trong dấu nháy để dễ đọc và tránh cách diễn giải ngoài ý muốn của parser:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        "enrichOrder|validateOrder|createNotification-in-0":
          destination: orders
          group: order-notification
        "enrichOrder|validateOrder|createNotification-out-0":
          destination: order-notifications
~~~

Tên bean là một phần của hợp đồng cấu hình. Khi đổi tên function hoặc thay đổi thứ tự composition, tên binding mặc định cũng thay đổi. Những file cấu hình profile, dashboard hoặc triển khai đang tham chiếu tên cũ cần được cập nhật đồng bộ.

## 3. Khai báo các function bean có kiểu tương thích

Trước khi cấu hình binding, hãy khai báo các bean có chữ ký đầu vào/đầu ra nối được với nhau.

Các kiểu dữ liệu minh họa:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}

public record EnrichedOrder(
    String eventId,
    String orderId,
    BigDecimal total,
    String customerTier
) {}

public record ValidatedOrder(
    String eventId,
    String orderId,
    BigDecimal total,
    String customerTier,
    boolean eligible
) {}

public record NotificationRequested(
    String eventId,
    String orderId,
    String message
) {}
~~~

Khai báo ba function:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    Function<OrderCreated, EnrichedOrder> enrichOrder() {
        return event -> new EnrichedOrder(
            event.eventId(),
            event.orderId(),
            event.total(),
            "STANDARD"
        );
    }

    @Bean
    Function<EnrichedOrder, ValidatedOrder> validateOrder() {
        return order -> new ValidatedOrder(
            order.eventId(),
            order.orderId(),
            order.total(),
            order.customerTier(),
            order.total().compareTo(BigDecimal.ZERO) > 0
        );
    }

    @Bean
    Function<ValidatedOrder, NotificationRequested> createNotification() {
        return order -> new NotificationRequested(
            order.eventId(),
            order.orderId(),
            order.eligible()
                ? "Đơn hàng đã được tiếp nhận"
                : "Đơn hàng cần được kiểm tra"
        );
    }
}
~~~

Ba chữ ký tương thích theo chuỗi:

- OrderCreated → EnrichedOrder
- EnrichedOrder → ValidatedOrder
- ValidatedOrder → NotificationRequested

Function đầu tiên nhận payload từ input binding của toàn chuỗi. Function cuối cùng tạo payload cho output binding. Các function ở giữa được gọi theo thứ tự mà composition định nghĩa.

## 4. Cấu hình binding trực tiếp theo tên composition

Có thể cấu hình trực tiếp hai tên binding mặc định mà không cần alias:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder|createNotification
    stream:
      bindings:
        "enrichOrder|validateOrder|createNotification-in-0":
          destination: orders
          group: order-notification
          contentType: application/json

        "enrichOrder|validateOrder|createNotification-out-0":
          destination: order-notifications
          contentType: application/json
~~~

Cấu hình này thiết lập luồng từ broker vào toàn bộ chuỗi và từ kết quả cuối cùng ra broker:

- Input binding đọc message từ destination orders.
- Group order-notification xác định subscription của consumer.
- Các function được gọi lần lượt trong cùng ứng dụng.
- Output binding gửi NotificationRequested đến destination order-notifications.
- Content type application/json hướng dẫn message conversion cho payload ở hai biên.

Nếu dùng Kafka, destination thường ánh xạ tới topic. Với RabbitMQ, destination thường ánh xạ tới exchange và queue của group. Với Pulsar, destination thường ánh xạ tới topic và group thành subscription. Logic composition không thay đổi theo broker, nhưng cấu hình binder và tài nguyên broker phải phù hợp.

## 5. Dùng binding alias để rút gọn tên

Tên binding có chứa toàn bộ biểu thức composition. Khi chuỗi dài hoặc tên bean thay đổi, cấu hình trực tiếp có thể khó đọc và khó duy trì. Spring Cloud Stream cho phép ánh xạ tên binding mặc định sang alias thông qua thuộc tính spring.cloud.stream.function.bindings.

Ví dụ ánh xạ input thành orders-in và output thành notifications-out:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder|createNotification
    stream:
      function:
        bindings:
          "enrichOrder|validateOrder|createNotification-in-0": orders-in
          "enrichOrder|validateOrder|createNotification-out-0": notifications-out
      bindings:
        orders-in:
          destination: orders
          group: order-notification
          contentType: application/json

        notifications-out:
          destination: order-notifications
          contentType: application/json
~~~

Khi đã khai báo alias, phần spring.cloud.stream.bindings sử dụng tên alias. Cấu hình destination, group và content type không cần lặp lại biểu thức function dài.

| Tên binding mặc định | Alias | Mục đích |
|---|---|---|
| enrichOrder\|validateOrder\|createNotification-in-0 | orders-in | Đầu vào của chuỗi |
| enrichOrder\|validateOrder\|createNotification-out-0 | notifications-out | Đầu ra của chuỗi |

Alias chỉ đổi tên dùng trong cấu hình. Nó không đổi tên bean, không thay đổi thứ tự composition và không tạo một function mới. Khi kiểm tra log hoặc actuator binding, có thể thấy tên binding đã được ánh xạ; hãy đối chiếu alias với function definition để xác định đúng endpoint.

### Khi nào nên dùng alias?

Nên dùng alias khi:

- Biểu thức composition dài hoặc chứa nhiều ký tự đặc biệt.
- Muốn tên binding thể hiện ý nghĩa nghiệp vụ thay vì tên các bước triển khai.
- Cần giữ tên destination binding ổn định khi refactor tên function bean.
- Có nhiều profile cấu hình và muốn giảm lặp lại tên function ghép.

Nếu chuỗi composition thay đổi, cần xác minh alias vẫn trỏ tới binding mới. Alias không tự động ánh xạ một tên composition cũ sang tên mới nếu key nguồn trong function.bindings không được cập nhật.

## 6. Cấu hình end-to-end từ function đến broker

Một cấu hình hoàn chỉnh cần kết hợp bốn phần:

1. Function definition xác định chuỗi hàm được kích hoạt.
2. Function beans cung cấp logic và chữ ký tương thích.
3. Binding alias hoặc tên binding mặc định xác định hai biên vào/ra.
4. Destination, group, content type và binder kết nối hai biên với broker.

Ví dụ đầy đủ với alias:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder|createNotification
    stream:
      defaultBinder: kafka
      function:
        bindings:
          "enrichOrder|validateOrder|createNotification-in-0": orders-in
          "enrichOrder|validateOrder|createNotification-out-0": notifications-out
      bindings:
        orders-in:
          destination: orders
          group: order-notification
          contentType: application/json
        notifications-out:
          destination: order-notifications
          contentType: application/json
~~~

Nếu dùng Kafka, có thể cấu hình kết nối qua Spring Kafka:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Trong production, địa chỉ broker và thông tin xác thực nên được cung cấp qua profile hoặc biến môi trường. Nếu dùng RabbitMQ hoặc Pulsar, chọn binder tương ứng và khai báo endpoint, credentials, TLS cùng các thuộc tính riêng của binder.

### Đường đi của một message

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Broker destination orders
    participant A as Spring Cloud Stream app
    participant F1 as enrichOrder
    participant F2 as validateOrder
    participant F3 as createNotification
    participant O as Broker destination order-notifications
    P->>K: OrderCreated
    K->>A: Input binding orders-in
    A->>F1: OrderCreated
    F1->>F2: EnrichedOrder
    F2->>F3: ValidatedOrder
    F3->>A: NotificationRequested
    A->>O: Output binding notifications-out
~~~

Broker chỉ tham gia ở hai biên của chuỗi. Các bước trung gian được gọi trong tiến trình ứng dụng. Nếu một bước ném exception, kết quả đầu ra của chuỗi không được phát hành theo đường đi bình thường; cách retry, xử lý lỗi và xác nhận message phụ thuộc cấu hình consumer và binder.

## 7. Phân biệt composition trong tiến trình với pipeline qua broker

Hai kiến trúc có thể nhìn giống nhau về mặt nghiệp vụ nhưng có ranh giới vận hành khác nhau.

**Composition trong cùng tiến trình**:

- Các function được nối bằng biểu thức |.
- Đầu ra của bước trước trở thành đầu vào bước sau ngay trong ứng dụng.
- Chỉ có binding ở biên ngoài của chuỗi.
- Các bước trung gian không có destination, consumer group hay offset riêng.
- Scale và triển khai các bước cùng nhau theo ứng dụng chứa composition.

**Pipeline qua broker**:

- Mỗi stage được kích hoạt như một function độc lập, thường khai báo bằng dấu ;.
- Stage trước phát message tới destination trung gian.
- Stage tiếp theo có input binding riêng và đọc destination đó.
- Có thể triển khai, scale, retry và quan sát từng stage độc lập.
- Broker tạo ranh giới lưu giữ và giao nhận giữa các stage.

Ví dụ khai báo hai function độc lập:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder;notifyOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders
          group: order-enricher
        enrichOrder-out-0:
          destination: enriched-orders
        notifyOrder-in-0:
          destination: enriched-orders
          group: order-notifier
~~~

Trong ví dụ này, enrichOrder và notifyOrder là hai endpoint độc lập. Message được ghi vào destination enriched-orders rồi consumer thứ hai nhận lại qua broker. Đây không phải function composition trong cùng tiến trình.

| Nhu cầu | Chọn composition | Chọn pipeline qua broker |
|---|---|---|
| Các bước nhỏ, luôn triển khai cùng nhau | Phù hợp | Có thể dư thừa |
| Cần scale từng stage độc lập | Không thuận tiện | Phù hợp |
| Cần lưu message giữa các bước | Không có broker boundary ở bước giữa | Phù hợp |
| Cần retry hoặc quan sát riêng từng stage | Cần tự tổ chức ở cấp ứng dụng | Có thể cấu hình theo từng binding |
| Muốn giảm số destination và endpoint | Phù hợp | Ít phù hợp hơn |

Không có lựa chọn đúng cho mọi hệ thống. Hãy chọn composition khi các bước là một đơn vị xử lý hợp lý; chọn pipeline qua broker khi cần ranh giới triển khai, giao nhận hoặc khả năng phục hồi giữa các stage.

## 8. Supplier và Consumer ở hai đầu chuỗi

Composition không chỉ áp dụng cho Function–Function. Kiểu đầu vào và đầu ra của chuỗi được quyết định bởi function ở hai đầu.

| Chuỗi | Vai trò bên ngoài |
|---|---|
| Supplier<T>\|Function<T, R> | Không có input binding; có output binding |
| Function<T, R>\|Function<R, O> | Có input và output binding |
| Function<T, R>\|Consumer<R> | Có input binding; không có output binding |
| Supplier<T>\|Function<T, R>\|Consumer<R> | Nguồn dữ liệu và điểm tiêu thụ cuối; không có input/output message binding bên ngoài theo chữ ký hàm |

Ví dụ chuỗi bắt đầu bằng Supplier:

~~~yaml
spring:
  cloud:
    function:
      definition: readPendingOrders|enrichOrder
    stream:
      bindings:
        "readPendingOrders|enrichOrder-out-0":
          destination: enriched-orders
~~~

Supplier được poll theo cấu hình poller; dữ liệu do supplier tạo được chuyển qua function rồi phát ra output binding của chuỗi. Không có input binding cho chuỗi vì Supplier không nhận tham số đầu vào.

Ví dụ chuỗi kết thúc bằng Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: parseOrder|validateOrder|storeOrder
    stream:
      bindings:
        "parseOrder|validateOrder|storeOrder-in-0":
          destination: raw-orders
          group: order-storage
~~~

Consumer cuối nhận kết quả từ function trước và thực hiện tác động nghiệp vụ. Chuỗi không tạo output binding vì Consumer không trả về payload.

Khi kết hợp Supplier hoặc Consumer với các function khác, cần kiểm tra chữ ký generic thực tế và cơ chế poller/consumer. Không cấu hình một output binding cho chuỗi kết thúc bằng Consumer hoặc input binding cho chuỗi bắt đầu bằng Supplier.

## 9. Routing và function composition

Composition xác định thứ tự các bước xử lý cố định. Routing quyết định function hoặc nhánh xử lý được chọn dựa trên message hoặc điều kiện. Hai khái niệm có thể kết hợp nhưng không đồng nghĩa.

Ví dụ, một function ghép có thể xử lý chung phần chuẩn hóa, sau đó định tuyến theo loại sự kiện ở một bước riêng. Khi dùng routing function của Spring Cloud Function/Spring Cloud Stream, cần cấu hình rõ cách chọn function đích, header hoặc routing expression và danh sách function được phép gọi.

Không nên dùng routing expression để thay thế một chuỗi composition cố định nếu mọi message đều phải đi qua cùng các bước. Ngược lại, không nên tạo nhiều composition tĩnh nếu message cần chọn một trong nhiều nhánh theo dữ liệu. Hãy tách rõ:

- Composition: thứ tự các hàm trong một chuỗi.
- Routing: chọn hàm hoặc nhánh xử lý cho message.
- Binding: kết nối biên vào/ra của endpoint với destination.
- Group: xác định subscription của consumer ở biên input.

Khi có routing động, kiểm thử cả trường hợp header hợp lệ, header thiếu và giá trị không nằm trong danh sách cho phép. Không cho phép message bên ngoài tự do gọi mọi bean function trong ứng dụng.

## 10. Kiểm thử tên binding và function composition

Kiểm thử cần bao phủ cả chữ ký function, function definition và binding thực tế.

### Kiểm thử logic ghép hàm

Có thể kiểm tra các function theo từng bước hoặc ghép bằng Java để xác nhận kiểu dữ liệu:

~~~java
Function<OrderCreated, EnrichedOrder> enrich = event ->
    new EnrichedOrder(
        event.eventId(),
        event.orderId(),
        event.total(),
        "STANDARD"
    );

Function<EnrichedOrder, ValidatedOrder> validate = order ->
    new ValidatedOrder(
        order.eventId(),
        order.orderId(),
        order.total(),
        order.customerTier(),
        order.total().compareTo(BigDecimal.ZERO) > 0
    );

Function<ValidatedOrder, NotificationRequested> notify = order ->
    new NotificationRequested(
        order.eventId(),
        order.orderId(),
        order.eligible() ? "Accepted" : "Review"
    );

Function<OrderCreated, NotificationRequested> composed =
    enrich.andThen(validate).andThen(notify);
~~~

Unit test xác minh dữ liệu đầu ra, thứ tự xử lý và trường hợp lỗi nghiệp vụ. Đây là kiểm thử logic hàm; nó chưa xác nhận Spring Cloud Stream đã tạo đúng binding.

### Kiểm thử function definition và binding

Dùng Spring Application Context test hoặc binding test để xác nhận:

1. Các bean có đúng tên và được đăng ký.
2. Function definition chứa đúng thứ tự function.
3. Function composition có chữ ký đầu vào/đầu ra mong đợi.
4. Tên binding mặc định được tạo từ biểu thức ghép.
5. Binding alias được ánh xạ đúng nếu có dùng.
6. Input binding trỏ tới destination và group mong đợi.
7. Output binding trỏ tới destination mong đợi.
8. Message có content type và payload đúng ở cả hai biên.

Test binder có thể xác minh message đi qua input/output binding ở cấp ứng dụng. Broker integration test cần thiết để xác nhận tài nguyên và ngữ nghĩa thực tế của Kafka, RabbitMQ hoặc Pulsar.

### Kiểm thử sau khi đổi tên function

Khi đổi tên bean hoặc thứ tự composition:

- Xác nhận function definition đã cập nhật.
- Kiểm tra binding name mới.
- Kiểm tra alias key vẫn trỏ tới tên binding mới.
- Kiểm tra profile và biến môi trường không giữ cấu hình cũ.
- Gửi message thử và xác nhận đúng output destination.

## 11. Lỗi thường gặp khi cấu hình binding cho hàm ghép

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tạo được function ghép | Một bean không tồn tại hoặc tên trong definition sai | Kiểm tra tên bean và function definition |
| Composition không tương thích kiểu | Output type của bước trước khác input type bước sau | Sửa chữ ký hoặc thêm function chuyển đổi |
| Không thấy input binding | Dùng sai tên binding hoặc chuỗi bắt đầu bằng Supplier | Kiểm tra function definition và chữ ký đầu chuỗi |
| Không thấy output binding | Chuỗi kết thúc bằng Consumer | Kiểm tra chữ ký cuối chuỗi |
| Binding name không khớp YAML | Cấu hình theo tên function đơn thay vì tên composition | Dùng tên đầy đủ của biểu thức ghép hoặc alias |
| Alias không hoạt động | Key trong function.bindings không trùng binding name mặc định | Đối chiếu chính xác biểu thức ghép và hậu tố -in-0/-out-0 |
| Destination không nhận message | Output alias hoặc destination cấu hình sai | Kiểm tra binding được kích hoạt và broker |
| Function độc lập bị hiểu thành composition | Dùng dấu \| thay vì dấu ; hoặc ngược lại | Chọn đúng dấu phân cách theo ý định |
| Message bị xử lý hai lần | Nhiều group độc lập hoặc nhiều endpoint cùng đọc destination | Kiểm tra group và function definition |
| Đổi tên bean làm binding biến mất | Tên binding mặc định thay đổi | Cập nhật alias và cấu hình liên quan |
| Không thể scale một bước riêng | Các bước đang chạy trong cùng composition | Tách stage thành function độc lập và nối qua broker nếu cần |

Khi chẩn đoán, hãy kiểm tra theo thứ tự: function bean, function definition, kiểu dữ liệu giữa các bước, tên binding mặc định, alias, destination/group và kết nối binder. Trình tự này giúp xác định lỗi ở composition hay ở cấu hình broker.

## 12. Bài thực hành: cấu hình đầu cuối cho OrderCreated

Tạo một ứng dụng xử lý đơn hàng với chuỗi enrichOrder|validateOrder|createNotification:

1. Khai báo các record OrderCreated, EnrichedOrder, ValidatedOrder và NotificationRequested.
2. Khai báo ba function bean với chữ ký đầu vào/đầu ra tương thích.
3. Cấu hình spring.cloud.function.definition theo đúng thứ tự composition.
4. Ghi lại tên input và output binding mặc định của toàn chuỗi.
5. Tạo alias orders-in và notifications-out bằng spring.cloud.stream.function.bindings.
6. Cấu hình orders-in đọc destination orders với group order-notification.
7. Cấu hình notifications-out gửi tới destination order-notifications.
8. Chọn content type application/json cho hai biên.
9. Khởi động ứng dụng và xác nhận binder tạo đúng endpoint.
10. Gửi một OrderCreated mẫu và kiểm tra NotificationRequested ở output.
11. Đổi tên một function bean rồi cập nhật definition và alias; xác nhận binding vẫn hoạt động.
12. Tạo một biến thể dùng ; để chạy các function độc lập, sau đó so sánh số binding và đường đi của message.
13. Tách một stage thành endpoint độc lập qua broker nếu cần scale hoặc retry riêng; kiểm tra lại destination trung gian.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Function beans | Tất cả bean tồn tại và có tên đúng |
| Composition | Thứ tự function đúng, kiểu dữ liệu tương thích |
| Input binding | Tên mặc định hoặc alias đúng |
| Output binding | Tên mặc định hoặc alias đúng |
| Destination | Input và output trỏ đúng luồng |
| Consumer group | Ổn định và đúng vai trò nghiệp vụ |
| Message conversion | Producer và consumer thống nhất content type |
| Broker | Binder kết nối đúng Kafka, RabbitMQ hoặc Pulsar |
| End-to-end | Message vào một lần và tạo kết quả mong đợi |
| Refactor | Đổi tên bean đã cập nhật function definition và alias |

Khi hoàn thành, bạn cần giải thích được tên binding được tạo từ biểu thức composition như thế nào, alias thay đổi tên cấu hình ra sao và tại sao các function trung gian không có destination riêng khi được ghép trong cùng tiến trình.

## Kết luận

Function composition biến nhiều function bean tương thích thành một endpoint xử lý duy nhất. Với biểu thức a|b|c, Spring Cloud Stream tạo binding ở biên ngoài của chuỗi; tên binding mặc định dựa trên toàn bộ biểu thức ghép và có thể được rút gọn bằng alias trong spring.cloud.stream.function.bindings.

Hãy cấu hình function definition, tên binding, alias, destination, group và content type như một hợp đồng đầu cuối. Chọn composition khi các bước cần chạy cùng nhau trong một tiến trình; chọn các function độc lập nối qua broker khi cần triển khai, scale, lưu giữ hoặc xử lý lỗi từng stage riêng. Kiểm thử cả logic ghép hàm và binding thực tế để phát hiện lỗi tên trước khi triển khai.

