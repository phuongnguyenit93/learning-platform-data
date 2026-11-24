# Từ lời gọi đồng bộ đến xử lý dựa trên sự kiện

Trong một ứng dụng nhỏ, cách dễ hiểu nhất để phối hợp các thành phần thường là gọi trực tiếp: dịch vụ đặt hàng gọi dịch vụ kiểm tra đơn, chờ kết quả, rồi gọi dịch vụ kho. Cách làm này phù hợp khi bên gọi cần kết quả ngay và số thành phần còn ít. Khi hệ thống lớn dần, mỗi lời gọi trực tiếp lại tạo thêm một mối phụ thuộc về địa chỉ, giao thức, thời gian phản hồi và khả năng sẵn sàng của dịch vụ được gọi.

Xử lý dựa trên sự kiện thay đổi cách phối hợp đó. Thành phần phát sự kiện ghi nhận một việc đã xảy ra và gửi thông điệp qua một hạ tầng truyền tin. Thành phần quan tâm đến sự kiện có thể nhận và xử lý độc lập. Spring Cloud Stream cung cấp mô hình lập trình và lớp tích hợp để ứng dụng Java làm việc với các hệ thống truyền tin như Kafka, RabbitMQ hoặc Pulsar mà không phải gắn toàn bộ logic nghiệp vụ vào API riêng của từng broker.

Bài này mở đầu chương **Tổng quan** của module `SPRING_CLOUD_STREAM`. Module đi từ mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder đến consumer group, partition, schema thông điệp, retry/DLQ, xử lý trạng thái với Kafka Streams, kiểm thử và bảo đảm giao nhận khi triển khai. Để học các phần sau có nền tảng vững, trước hết cần hiểu vì sao một hệ thống chuyển từ lời gọi đồng bộ sang trao đổi sự kiện, cũng như những đánh đổi đi kèm.

## 1. Lời gọi đồng bộ hoạt động như thế nào?

Trong mô hình đồng bộ, bên gọi gửi yêu cầu đến một thành phần cụ thể và thường giữ luồng xử lý cho đến khi nhận được phản hồi hoặc hết thời gian chờ. Ví dụ, khi khách hàng đặt hàng, ứng dụng có thể lần lượt gọi dịch vụ kiểm tra đơn, dịch vụ tồn kho và dịch vụ thanh toán.

```text
Ứng dụng đặt hàng
    |-- HTTP: kiểm tra đơn ------> Dịch vụ đơn hàng
    |<-- HTTP: hợp lệ ------------|
    |-- HTTP: giữ hàng ----------> Dịch vụ kho
    |<-- HTTP: đã giữ hàng -------|
    |-- HTTP: thanh toán --------> Dịch vụ thanh toán
    |<-- HTTP: thành công --------|
    |
    +-- trả kết quả cho khách hàng
```

Đặc điểm của cách phối hợp này:

- **Biết trước người nhận:** bên gọi phải biết endpoint hoặc client dùng để truy cập dịch vụ đích.
- **Phụ thuộc thời gian:** dịch vụ đích cần phản hồi trong thời gian chờ mà bên gọi chấp nhận.
- **Luồng điều khiển tập trung:** bên gọi quyết định thứ tự gọi, cách xử lý phản hồi và thường cả cách thử lại.
- **Kết quả tức thời:** thuận tiện khi giao diện cần biết ngay thao tác thành công hay thất bại.

Lời gọi đồng bộ không phải là lựa chọn sai. Nó phù hợp với truy vấn cần phản hồi ngay, thao tác tương tác trực tiếp và các bước mà kết quả của bước trước quyết định ngay bước tiếp theo. Vấn đề xuất hiện khi một yêu cầu phải gọi qua quá nhiều dịch vụ hoặc khi các thành phần cần hoạt động độc lập với nhau.

## 2. Vì sao chuỗi lời gọi trực tiếp trở nên khó mở rộng?

Giả sử dịch vụ đặt hàng gọi ba dịch vụ khác nhau. Nếu dịch vụ kho chậm, luồng đặt hàng phải chờ dù việc ghi nhận đơn hàng có thể đã hoàn tất. Nếu dịch vụ thanh toán tạm thời không khả dụng, bên gọi phải quyết định giữ kết nối, thử lại, hoàn tác hay trả lỗi. Khi nhiều dịch vụ cùng chậm, thời gian chờ có thể cộng dồn và giữ nhiều luồng hoặc kết nối trong hệ thống.

Một số dạng phụ thuộc thường gặp:

| Dạng phụ thuộc | Biểu hiện | Hệ quả |
|---|---|---|
| Phụ thuộc địa chỉ | Bên gọi biết URL, tên dịch vụ hoặc client của bên nhận | Thay đổi cách triển khai có thể kéo theo thay đổi ở bên gọi |
| Phụ thuộc thời gian | Bên gọi chờ phản hồi trực tiếp | Sự cố hoặc tải cao ở một dịch vụ lan sang các dịch vụ gọi nó |
| Phụ thuộc triển khai | Hai bên phải thống nhất thời điểm thay đổi API | Khó triển khai và mở rộng từng thành phần độc lập |
| Phụ thuộc luồng nghiệp vụ | Một dịch vụ điều phối nhiều lời gọi nối tiếp | Logic điều phối tập trung và khó xử lý các tác vụ đến muộn |

Thử lại lời gọi đồng bộ cũng cần thận trọng. Nếu bên gọi thử lại trong khi yêu cầu trước đã được xử lý nhưng phản hồi bị thất lạc, thao tác có thể được thực hiện hai lần. Nếu nhiều bên cùng thử lại theo một nhịp, tải tăng đột biến có thể làm sự cố kéo dài hơn. Timeout, giới hạn số lần thử, backoff và tính idempotent vẫn cần được thiết kế ngay cả khi dùng messaging.

## 3. Tư duy dựa trên sự kiện

Trong kiến trúc hướng sự kiện, thành phần phát tin công bố một sự kiện mô tả điều đã xảy ra, ví dụ `OrderPlaced`, `PaymentAuthorized` hoặc `InventoryReserved`. Bên phát không cần gọi trực tiếp từng dịch vụ sẽ phản ứng với sự kiện đó. Một broker tiếp nhận và chuyển thông điệp đến các consumer đã đăng ký.

```text
                       +----------------------+
                       |       Broker         |
                       | topic / queue         |
                       +----------+-----------+
                                  ^
                                  | publish event
                                  |
+------------------+              |
| Dịch vụ đặt hàng |--------------+
+------------------+
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
       +-------------------+             +-------------------+
       | Consumer tồn kho  |             | Consumer thông báo|
       +-------------------+             +-------------------+
```

Trình tự xử lý thường là:

1. Một nghiệp vụ xảy ra trong ứng dụng phát tin, chẳng hạn đơn hàng được tạo.
2. Ứng dụng chuyển sự kiện thành message và gửi đến destination đã cấu hình.
3. Broker lưu giữ hoặc định tuyến message theo cơ chế của nó.
4. Consumer nhận message qua binding đầu vào và thực hiện phần việc của mình.
5. Consumer có thể kết thúc xử lý hoặc phát ra một sự kiện mới để bước tiếp theo tiếp tục.

Sự kiện nên diễn tả một sự thật đã xảy ra, thường dùng tên ở dạng quá khứ như `OrderPlaced`. Một command như `ReserveInventory` lại diễn tả yêu cầu người nhận thực hiện việc gì. Phân biệt hai khái niệm này giúp thiết kế hợp đồng rõ ràng: sự kiện thông báo điều đã xảy ra; command yêu cầu một hành động và thường có một bên chịu trách nhiệm xử lý.

Các consumer có thể phát triển và triển khai độc lập. Dịch vụ đặt hàng chỉ cần công bố hợp đồng sự kiện mà các bên quan tâm cùng hiểu. Dịch vụ kho có thể giữ hàng; dịch vụ thông báo có thể gửi email; dịch vụ phân tích có thể cập nhật số liệu. Khi cần thêm consumer mới, thường không phải sửa luồng gọi trực tiếp trong dịch vụ phát tin.

## 4. Những lợi ích và đánh đổi

Trao đổi sự kiện làm giảm phụ thuộc trực tiếp giữa các dịch vụ và giúp hấp thụ tải tốt hơn khi broker có khả năng lưu đệm. Consumer có thể mở rộng số instance phù hợp với lượng message và năng lực xử lý. Một consumer bị dừng trong thời gian ngắn có thể tiếp tục xử lý message còn được broker lưu giữ sau khi hoạt động trở lại, tùy cấu hình và chính sách lưu giữ.

Đổi lại, hệ thống trở nên bất đồng bộ. Bên phát thường chỉ biết message đã được gửi theo mức xác nhận mà hạ tầng cung cấp; nó không đồng nghĩa mọi consumer đã xử lý xong nghiệp vụ. Trạng thái có thể nhất quán sau một khoảng thời gian, thay vì thay đổi đồng thời trong một request. Người dùng và các dịch vụ liên quan cần chấp nhận hoặc biểu diễn trạng thái trung gian như `PENDING`, `PROCESSING` hay `CONFIRMED`.

| Khía cạnh | Gọi đồng bộ | Xử lý dựa trên sự kiện |
|---|---|---|
| Giao tiếp | Gọi một dịch vụ và chờ phản hồi | Gửi message; consumer xử lý sau |
| Phụ thuộc | Bên gọi biết người nhận và API | Bên phát phụ thuộc vào hợp đồng message và destination |
| Thời điểm hoàn tất | Thường nằm trong thời gian request | Có thể hoàn tất sau request ban đầu |
| Mở rộng | Thường mở rộng theo dịch vụ được gọi | Có thể mở rộng consumer theo lượng message |
| Khả năng phục hồi | Cần xử lý timeout và thử lại ở luồng gọi | Có thể lưu đệm, phát lại hoặc chuyển message lỗi tùy broker và cấu hình |
| Độ phức tạp | Dễ theo dõi trong luồng ngắn | Cần quản lý schema, trùng lặp, thứ tự, retry và quan sát xuyên dịch vụ |

Không nên chuyển mọi lời gọi thành message. Một truy vấn cần dữ liệu ngay vẫn có thể dùng HTTP hoặc một giao thức request-response. Một hệ thống thực tế thường kết hợp hai kiểu: đồng bộ cho tương tác cần phản hồi tức thời, bất đồng bộ cho các tác vụ có thể xử lý sau hoặc có nhiều bên cùng quan tâm.

## 5. Spring Cloud Stream đứng ở đâu?

Spring Cloud Stream là framework xây dựng ứng dụng hướng message trên Spring Boot. Nó cung cấp mô hình hàm và các abstraction để logic nghiệp vụ làm việc với message thông qua **binding**. Một **binder** kết nối binding của ứng dụng với hệ thống truyền tin cụ thể như Kafka, RabbitMQ hoặc Pulsar.

Có thể hình dung các lớp như sau:

```text
Logic ứng dụng
  Supplier / Function / Consumer
            |
            v
       Binding của ứng dụng
            |
            v
          Binder
            |
            v
  Kafka / RabbitMQ / Pulsar
```

Ba khái niệm cần phân biệt:

- **Message:** đơn vị dữ liệu được truyền, thường gồm payload và headers. Payload mang nội dung nghiệp vụ; headers có thể mang thông tin như content type, correlation ID hoặc metadata phục vụ định tuyến.
- **Binding:** điểm kết nối logic giữa hàm trong ứng dụng và luồng message. Tên binding thường được suy ra từ tên hàm và vai trò input/output.
- **Binder:** bộ tích hợp giao tiếp với broker. Binder ánh xạ các binding sang cơ chế tương ứng của Kafka, RabbitMQ hoặc Pulsar.

`destination` là tên tài nguyên đích trên broker, chẳng hạn topic hoặc queue tùy loại binder. Tên destination và tên binding có mục đích khác nhau: binding là tên điểm nối trong ứng dụng; destination là nơi message được gửi đến hoặc đọc từ đó. Việc đổi broker thường chủ yếu tác động đến dependency và cấu hình binder, trong khi logic hàm có thể giữ nguyên nếu hợp đồng message và ngữ nghĩa cần thiết vẫn tương thích.

## 6. Mô hình hàm Supplier, Function và Consumer

Spring Cloud Stream tích hợp với Spring Cloud Function. Ứng dụng có thể biểu diễn các vai trò xử lý message bằng ba kiểu hàm quen thuộc:

| Kiểu hàm | Vai trò | Binding thường gặp |
|---|---|---|
| `Supplier<T>` | Tạo dữ liệu đầu ra để phát message | `<functionName>-out-0` |
| `Function<T, R>` | Nhận dữ liệu, xử lý và tạo dữ liệu đầu ra | `<functionName>-in-0`, `<functionName>-out-0` |
| `Consumer<T>` | Nhận và xử lý dữ liệu, không tạo đầu ra từ hàm | `<functionName>-in-0` |

`Supplier` phù hợp khi ứng dụng chủ động tạo message, ví dụ đọc dữ liệu cần phát theo chu kỳ. Với supplier thông thường, framework gọi hàm thông qua cơ chế polling; chu kỳ polling cần được cân nhắc để tránh phát dữ liệu quá dày hoặc bỏ lỡ yêu cầu nghiệp vụ. `Function` phù hợp cho bước biến đổi hoặc kiểm tra message. `Consumer` phù hợp cho bước xử lý cuối như cập nhật kho hoặc gửi thông báo. Một ứng dụng có thể chỉ dùng một vai trò hoặc kết hợp nhiều hàm.

Ví dụ sau minh họa một hàm kiểm tra sự kiện đơn hàng và phát sự kiện xác nhận. Các record chỉ mô tả payload để tập trung vào luồng xử lý; trong ứng dụng thực tế, chúng cần được đặt trong package và hợp đồng phù hợp.

```java
import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, BigDecimal total) {}

record OrderAccepted(String orderId, BigDecimal total) {}

@Configuration
class OrderEventFunctions {

    @Bean
    Function<OrderPlaced, OrderAccepted> validateOrder() {
        return event -> {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (event.total() == null || event.total().signum() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }

            return new OrderAccepted(event.orderId(), event.total());
        };
    }
}
```

Khi hàm `validateOrder` được chọn làm function definition, Spring Cloud Stream tạo binding đầu vào và đầu ra theo quy ước. Ví dụ cấu hình YAML dưới đây nối chúng với hai destination:

```yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.placed
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Ứng dụng cần có dependency binder tương ứng với broker đã chọn và cấu hình kết nối broker theo môi trường triển khai. Ví dụ trên dùng tên binding mặc định được suy ra từ hàm; `orders.placed` và `orders.accepted` là destination. Thuộc tính `group` đặt nhóm consumer cho binding đầu vào để các instance cùng nhóm phối hợp tiêu thụ theo khả năng của broker. Ý nghĩa chi tiết của group, partition và cách phân phối message sẽ được học ở các bài chuyên sâu.

Hàm ví dụ ném exception khi dữ liệu không hợp lệ để minh họa điểm có thể phát sinh lỗi. Một ứng dụng vận hành thực tế phải quyết định rõ lỗi nào được retry, lỗi nào chuyển sang dead-letter queue (DLQ), cách ghi log và cách bảo đảm xử lý lặp an toàn. Không nên xem việc hàm trả về hoặc binder gửi message là bằng chứng rằng toàn bộ quy trình nghiệp vụ ở mọi consumer đã hoàn tất.

## 7. Message là một hợp đồng giữa các thành phần

Khi hai dịch vụ giao tiếp bằng message, payload trở thành hợp đồng mà cả bên phát và bên nhận cùng phụ thuộc. Hợp đồng cần có tên trường rõ nghĩa, kiểu dữ liệu ổn định và quy tắc xử lý khi trường được thêm, bỏ hoặc thay đổi. Một vài nguyên tắc hữu ích:

- Đặt tên sự kiện theo sự thật nghiệp vụ đã xảy ra, chẳng hạn `OrderPlaced`.
- Có định danh sự kiện hoặc định danh nghiệp vụ để consumer nhận biết message trùng lặp.
- Cân nhắc thời điểm xảy ra, phiên bản schema và correlation ID khi cần truy vết một luồng nghiệp vụ.
- Tránh đưa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào payload.
- Thống nhất quy tắc tương thích schema trước khi triển khai producer và consumer ở các phiên bản khác nhau.

Không phải message nào cũng có một bản sao duy nhất hoặc đến đúng thứ tự toàn cục. Kafka thường tổ chức dữ liệu theo topic và partition; RabbitMQ có exchange, queue và routing; Pulsar có topic và subscription. Mỗi binder ánh xạ binding của Spring Cloud Stream sang những khái niệm và khả năng riêng của broker. Vì vậy, cần hiểu ngữ nghĩa broker đang dùng thay vì giả định mọi binder hoạt động hoàn toàn giống nhau.

## 8. Các vấn đề phải giải quyết khi xử lý bất đồng bộ

Kiến trúc sự kiện giảm phụ thuộc trực tiếp nhưng đưa thêm trách nhiệm vận hành. Những câu hỏi sau cần được trả lời trong thiết kế:

1. **Message có thể bị giao nhiều lần không?** Consumer nên idempotent: xử lý lại cùng một sự kiện không làm nghiệp vụ bị nhân đôi. Có thể dùng event ID, khóa duy nhất hoặc bảng inbox để phát hiện message đã xử lý.
2. **Thứ tự nào cần được bảo toàn?** Nếu các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, cần chọn key, partition hoặc cơ chế tuần tự hóa phù hợp với broker và binder.
3. **Điều gì xảy ra khi consumer lỗi?** Cần xác định số lần retry, khoảng nghỉ, loại lỗi có thể thử lại và nơi lưu message không thể xử lý. DLQ giúp cô lập message lỗi để điều tra và xử lý lại có kiểm soát.
4. **Producer có thể ghi dữ liệu nghiệp vụ nhưng không gửi được event không?** Nếu cập nhật database và gửi message không nằm trong cùng một giao dịch phân tán được bảo đảm, transactional outbox là một mẫu thường dùng để ghi sự kiện cần phát cùng giao dịch dữ liệu rồi chuyển tiếp sau.
5. **Làm sao biết message đang ở đâu?** Cần log có correlation ID, metric về tốc độ vào/ra, độ trễ, số lần retry, backlog và cảnh báo khi consumer bị nghẽn.
6. **Có cần trạng thái hay phép tính trên một luồng liên tục không?** Kafka Streams và các cơ chế xử lý stateful có thể duy trì trạng thái theo key, cửa sổ thời gian hoặc topology; chúng cần được thiết kế và kiểm thử riêng.

Các bảo đảm giao nhận như at-most-once, at-least-once và các cấu hình gần với exactly-once phụ thuộc vào broker, binder, giao dịch và cách ứng dụng xử lý dữ liệu. Không nên khẳng định hệ thống có exactly-once chỉ vì đã bật một thuộc tính cấu hình. Tính idempotent và ranh giới giao dịch của nghiệp vụ vẫn là phần quan trọng của thiết kế.

## 9. Khi nào nên chọn mỗi cách?

Hãy dùng lời gọi đồng bộ khi bên gọi cần dữ liệu ngay để tiếp tục tương tác, chẳng hạn tra cứu giá hiện tại hoặc kiểm tra quyền truy cập. Hãy cân nhắc sự kiện khi một nghiệp vụ đã xảy ra và nhiều thành phần có thể phản ứng độc lập, chẳng hạn đơn hàng được tạo cần cập nhật kho, gửi thông báo và ghi nhận dữ liệu phân tích.

Một quy trình đặt hàng có thể kết hợp cả hai:

1. API nhận yêu cầu đặt hàng và đồng bộ kiểm tra dữ liệu bắt buộc để phản hồi nhanh.
2. Dịch vụ ghi nhận đơn hàng cùng sự kiện cần phát theo một cơ chế bảo đảm phù hợp, ví dụ transactional outbox.
3. Một tiến trình chuyển tiếp phát `OrderPlaced` lên broker.
4. Các consumer độc lập xử lý giữ hàng, thanh toán hoặc thông báo theo quy trình riêng.
5. Khi có kết quả, các dịch vụ phát sự kiện tiếp theo như `InventoryReserved` hoặc `PaymentAuthorized`; trạng thái đơn hàng được cập nhật theo tiến trình.

Với cách này, API có thể trả trạng thái đã tiếp nhận thay vì chờ mọi tác vụ nền hoàn tất. Giao diện cần hiển thị trạng thái trung gian và có cách truy vấn hoặc nhận cập nhật khi quy trình hoàn tất.

## 10. Lộ trình chuyển đổi an toàn

Không cần chuyển cả hệ thống sang event-driven trong một lần. Có thể bắt đầu từ một nghiệp vụ có ranh giới rõ và ít yêu cầu phản hồi tức thời:

1. Xác định sự kiện nghiệp vụ và thời điểm sự kiện được xem là đã xảy ra.
2. Thiết kế payload, định danh, schema và quy tắc tương thích.
3. Chọn broker, binder và destination dựa trên yêu cầu lưu giữ, định tuyến, thứ tự, tải và vận hành.
4. Viết producer và consumer nhỏ; làm cho consumer chịu được message trùng lặp.
5. Thiết lập retry, DLQ, timeout, metric, log và cảnh báo trước khi tăng lưu lượng.
6. Kiểm thử tình huống thành công, lỗi tạm thời, lỗi dữ liệu, consumer dừng, message trùng và thay đổi schema.
7. Triển khai theo từng bước, quan sát backlog và độ trễ, rồi mới mở rộng số consumer hoặc thêm bên nhận.

Trong Spring Cloud Stream, các bài tiếp theo sẽ cụ thể hóa lộ trình này: cách cấu hình binding và binder; cách chọn consumer group và partition; cách chuyển đổi payload và quản lý schema; cách xử lý lỗi, retry và DLQ; cách dùng Kafka Streams cho xử lý có trạng thái; và cách kiểm thử, quan sát, bảo mật, tối ưu cũng như triển khai ứng dụng.

## 11. Tự kiểm tra

- [ ] Có thể giải thích vì sao chuỗi lời gọi đồng bộ tạo phụ thuộc về thời gian và khả năng sẵn sàng.
- [ ] Có thể phân biệt một sự kiện mô tả điều đã xảy ra với một command yêu cầu hành động.
- [ ] Có thể mô tả vai trò của message, binding, binder và destination trong Spring Cloud Stream.
- [ ] Có thể nhận diện khi nào dùng `Supplier`, `Function` hoặc `Consumer`.
- [ ] Hiểu rằng xử lý bất đồng bộ cần thiết kế cho trùng lặp, thứ tự, lỗi, schema và quan sát.
- [ ] Biết rằng binder giúp tích hợp với broker nhưng không xóa bỏ khác biệt ngữ nghĩa giữa Kafka, RabbitMQ và Pulsar.

## Kết luận

Chuyển từ gọi trực tiếp sang trao đổi sự kiện giúp các thành phần phản ứng độc lập và mở rộng theo nhu cầu, nhưng cũng làm quy trình trở nên bất đồng bộ và đòi hỏi quản lý hợp đồng message, trạng thái, lỗi cùng khả năng quan sát. Spring Cloud Stream giúp tổ chức ứng dụng quanh các hàm xử lý và binding, còn binder kết nối ứng dụng với broker. Khi nắm được ranh giới giữa logic nghiệp vụ, binding và hạ tầng truyền tin, ta có nền tảng để thiết kế các luồng sự kiện tin cậy và dễ vận hành.
