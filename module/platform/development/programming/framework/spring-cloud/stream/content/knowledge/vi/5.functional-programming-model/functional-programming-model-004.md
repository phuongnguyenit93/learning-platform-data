# Tự phát hiện hàm và kiểm soát function.autodetect

Spring Cloud Stream sử dụng mô hình hàm của Spring Cloud Function để kết nối các bean Supplier, Function và Consumer với hệ thống truyền tin. Khi ứng dụng khởi động, framework có thể tìm các bean hàm đã được Spring đăng ký và tự động tạo binding cho chúng. Cơ chế này giúp một ứng dụng nhỏ bắt đầu xử lý sự kiện với ít cấu hình, nhưng có thể gây bất ngờ khi ứng dụng có nhiều hàm hoặc chứa những bean hàm chỉ phục vụ mục đích nội bộ.

Thuộc tính **spring.cloud.stream.function.autodetect** kiểm soát hành vi tự phát hiện và tự động binding của Spring Cloud Stream. Khi cần xác định chính xác hàm nào được kết nối với broker, hãy kết hợp thuộc tính này với **spring.cloud.function.definition**. Hai thuộc tính có vai trò khác nhau: một thuộc tính điều khiển tự động phát hiện, thuộc tính còn lại chỉ định hàm hoặc chuỗi hàm mà ứng dụng muốn sử dụng.

## 1. Spring Cloud Stream phát hiện bean hàm như thế nào?

Trong mô hình hàm, một bean có kiểu Java functional interface thường là điểm vào của luồng sự kiện:

| Kiểu hàm | Vai trò | Binding mặc định |
|---|---|---|
| Supplier với kiểu đầu ra T | Tạo dữ liệu và phát ra thông điệp. | **tên-hàm-out-0** |
| Function nhận T và trả R | Nhận dữ liệu, chuyển đổi hoặc xử lý rồi phát kết quả. | **tên-hàm-in-0** và **tên-hàm-out-0** |
| Consumer nhận T | Nhận dữ liệu và thực hiện tác động, không phát kết quả. | **tên-hàm-in-0** |

Spring đăng ký các bean này trong ApplicationContext. Spring Cloud Function cung cấp FunctionCatalog để tra cứu và gọi các hàm; Spring Cloud Stream sử dụng các hàm được chọn để thiết lập binding với binder. Binder đảm nhiệm việc kết nối binding tới Kafka, RabbitMQ hoặc Pulsar.

Ví dụ một ứng dụng có hàm chuyển đổi đơn hàng:

~~~java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<String, String> normalizeOrder() {
        return payload -> payload.trim().toUpperCase();
    }
}
~~~

Tên bean mặc định lấy từ tên phương thức **@Bean**, trong ví dụ này là **normalizeOrder**. Với hàm Function, binding đầu vào là **normalizeOrder-in-0**, còn binding đầu ra là **normalizeOrder-out-0**. Spring Cloud Stream có thể dùng các tên binding này để ánh xạ tới destination của broker.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders
          group: order-normalizer
        normalizeOrder-out-0:
          destination: normalized-orders
~~~

Khi đó, thông điệp được nhận từ destination **orders**, chuyển qua hàm **normalizeOrder**, rồi kết quả được gửi tới **normalized-orders**. Việc đặt tên hàm rõ ràng giúp xác định binding tương ứng và đọc log dễ hơn.

## 2. Hành vi tự phát hiện mặc định

Spring Cloud Stream hỗ trợ tự tìm các bean thuộc **Supplier**, **Function** hoặc **Consumer** để cấu hình luồng. Đây là cách thuận tiện khi ứng dụng chỉ có một chức năng xử lý chính hoặc khi mọi hàm được phát hiện đều được dự định sử dụng cho luồng messaging.

Ví dụ ứng dụng chỉ khai báo một Consumer:

~~~java
@Configuration
public class AuditFunctions {

    @Bean
    public Consumer<String> auditEvent() {
        return event -> System.out.println("Audit event: " + event);
    }
}
~~~

Với cấu hình đơn giản, Spring Cloud Stream có thể phát hiện bean **auditEvent** và tạo binding đầu vào có tên **auditEvent-in-0**. Ứng dụng có thể cấu hình destination tương ứng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvent-in-0:
          destination: audit-events
          group: audit-service
~~~

Điểm cần lưu ý là việc phát hiện bean và việc chọn hàm nghiệp vụ là hai quyết định khác nhau. Khi ứng dụng phát triển, một cấu hình lớp có thể chứa thêm hàm thử nghiệm, hàm hỗ trợ, Supplier phát heartbeat hoặc Consumer phục vụ một luồng khác. Nếu dựa hoàn toàn vào tự phát hiện, thay đổi số lượng bean hàm có thể làm thay đổi những hàm được binding khi ứng dụng khởi động.

Vì vậy, hãy xem tự phát hiện là tiện ích khởi đầu. Với ứng dụng có nhiều chức năng, việc khai báo rõ hàm cần binding giúp cấu hình ổn định và dễ kiểm tra hơn.

## 3. Kiểm soát tự phát hiện bằng function.autodetect

Để tắt hành vi tự phát hiện của Spring Cloud Stream, đặt:

~~~yaml
spring:
  cloud:
    stream:
      function:
        autodetect: false
~~~

Thuộc tính đúng là **spring.cloud.stream.function.autodetect**. Đây là thuộc tính thuộc cấu hình Spring Cloud Stream. Không nhầm nó với một thuộc tính cùng tên đặt dưới **spring.cloud.function**.

Khi tắt tự phát hiện, ứng dụng cần chỉ rõ hàm sẽ được binding bằng thuộc tính **spring.cloud.function.definition**:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        autodetect: false
      bindings:
        normalizeOrder-in-0:
          destination: orders
          group: order-normalizer
        normalizeOrder-out-0:
          destination: normalized-orders
~~~

Trong cấu hình này:

- **spring.cloud.stream.function.autodetect: false** ngăn framework tự động binding mọi bean hàm chỉ vì bean đó được phát hiện.
- **spring.cloud.function.definition: normalizeOrder** chọn bean hàm có tên **normalizeOrder**.
- Các binding **normalizeOrder-in-0** và **normalizeOrder-out-0** khai báo destination cụ thể cho hàm đã chọn.

Tắt tự phát hiện không có nghĩa là xóa bean khỏi Spring ApplicationContext hoặc vô hiệu hóa FunctionCatalog. Bean vẫn có thể được Spring quản lý và được thành phần khác sử dụng; ứng dụng chỉ không dựa vào cơ chế tự động binding tất cả hàm được phát hiện.

Nếu tắt tự phát hiện mà không khai báo hàm cần binding, ứng dụng có thể khởi động nhưng luồng messaging mong đợi sẽ không được tạo. Hãy kiểm tra **spring.cloud.function.definition** cùng các binding tương ứng khi chủ động tắt thuộc tính này.

## 4. Chọn một hàm khi ứng dụng có nhiều bean

Một ứng dụng thực tế có thể chứa nhiều hàm phục vụ các luồng độc lập:

~~~java
@Configuration
public class MessagingFunctions {

    @Bean
    public Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(event.orderId(), true);
    }

    @Bean
    public Consumer<PaymentFailed> recordPaymentFailure() {
        return event -> System.out.println("Payment failed: " + event.paymentId());
    }

    @Bean
    public Supplier<Heartbeat> heartbeat() {
        return () -> new Heartbeat(Instant.now());
    }
}
~~~

Nếu chỉ muốn binding hàm kiểm tra đơn hàng, hãy khai báo rõ:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      function:
        autodetect: false
      bindings:
        validateOrder-in-0:
          destination: orders
          group: order-validation
        validateOrder-out-0:
          destination: validated-orders
~~~

Hai bean **recordPaymentFailure** và **heartbeat** vẫn có thể tồn tại trong ApplicationContext, nhưng không được chọn để tạo luồng messaging theo cấu hình trên. Điều này hữu ích khi ứng dụng dùng chung các lớp cấu hình hoặc có những bean hàm được gọi trực tiếp trong logic nội bộ.

Nếu cần nhiều hàm độc lập, Spring Cloud Function cho phép liệt kê tên các hàm trong **definition**, phân cách bằng dấu chấm phẩy:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder;recordPaymentFailure
    stream:
      function:
        autodetect: false
~~~

Trong trường hợp này, cả hai hàm được chọn để binding. Mỗi hàm có binding riêng theo tên và kiểu đầu vào/đầu ra. Hãy khai báo destination và group cho từng binding cần cấu hình; không giả định một hàm sẽ dùng chung destination với hàm còn lại.

**definition** cũng hỗ trợ ghép các Function tương thích bằng ký hiệu **|**, ví dụ **validateOrder|enrichOrder**. Đây là một chuỗi xử lý nối tiếp: đầu ra của hàm trước trở thành đầu vào của hàm sau. Các kiểu dữ liệu giữa hai bước phải tương thích. Dấu chấm phẩy chọn nhiều hàm độc lập, còn dấu **|** biểu diễn composition; không dùng hai cú pháp thay thế cho nhau.

## 5. Phân biệt function definition với binding name

Tên hàm và tên binding liên quan chặt chẽ nhưng không giống nhau:

- **Function name** là tên bean hàm được Spring đăng ký, ví dụ **normalizeOrder**.
- **Binding name** là tên đầu vào hoặc đầu ra do Spring Cloud Stream tạo từ tên hàm, ví dụ **normalizeOrder-in-0** và **normalizeOrder-out-0**.
- **Destination** là tài nguyên messaging trên broker mà binding kết nối tới, ví dụ topic Kafka **orders** hoặc queue RabbitMQ tương ứng.
- **Group** là danh tính nhóm tiêu thụ cho binding đầu vào, giúp các instance phối hợp nhận thông điệp theo ngữ nghĩa của binder.

Không đặt **spring.cloud.function.definition** bằng tên destination. Ví dụ, nếu bean là **normalizeOrder** và destination là **orders**, giá trị definition phải là **normalizeOrder**, còn **orders** được đặt trong **destination** của binding.

Nếu cần tên binding khác tên mặc định, Spring Cloud Stream có cơ chế ánh xạ binding bằng thuộc tính **spring.cloud.stream.function.bindings**. Chỉ nên dùng khi có lý do rõ ràng, bởi tên mặc định giúp liên hệ giữa function và binding dễ đọc hơn. Khi đổi tên binding, phải cập nhật đồng bộ cấu hình destination, group, partition, retry và các thuộc tính liên quan tới đúng binding mới.

## 6. Supplier, Function và Consumer trong ứng dụng nhiều luồng

Ba kiểu hàm thể hiện ba hướng xử lý khác nhau. Tự phát hiện không thay đổi hợp đồng của chúng:

~~~java
@Bean
public Supplier<String> generatedEvent() {
    return () -> "system-ready";
}

@Bean
public Function<String, String> transformEvent() {
    return value -> value.toUpperCase();
}

@Bean
public Consumer<String> consumeEvent() {
    return value -> process(value);
}
~~~

| Hàm | Hướng dữ liệu | Binding cần cấu hình |
|---|---|---|
| **generatedEvent** | Ứng dụng tạo thông điệp rồi gửi ra broker. | **generatedEvent-out-0** |
| **transformEvent** | Nhận từ broker, xử lý, gửi kết quả ra broker. | **transformEvent-in-0**, **transformEvent-out-0** |
| **consumeEvent** | Nhận từ broker và xử lý tại ứng dụng. | **consumeEvent-in-0** |

Một Supplier thường được gọi theo lịch polling của Spring Cloud Stream. Việc tự phát hiện hoặc khai báo **definition** quyết định hàm có được đưa vào luồng binding hay không; chu kỳ phát dữ liệu được kiểm soát bởi cấu hình poller và đặc điểm của Supplier. Không dùng **function.autodetect** để thay thế cấu hình tốc độ polling.

Khi nhiều hàm cùng có mặt, hãy xác định rõ mục tiêu:

1. Muốn mọi hàm được chọn cho messaging: liệt kê rõ trong **definition**.
2. Chỉ muốn một luồng hoạt động: chọn đúng một hàm.
3. Muốn nhiều bước xử lý nối tiếp: dùng composition với **|** khi kiểu dữ liệu tương thích.
4. Muốn một bean hàm chỉ phục vụ gọi nội bộ: không đưa nó vào danh sách hàm cần binding và cân nhắc tắt tự phát hiện.

## 7. Đặt cấu hình autodetect theo môi trường

Có thể dùng profile để bật hoặc tắt tự phát hiện tùy môi trường. Ví dụ, môi trường local có thể giữ cấu hình tối giản, trong khi production chọn hàm rõ ràng:

**application.yml**

~~~yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders
          group: order-normalizer
        normalizeOrder-out-0:
          destination: normalized-orders
~~~

**application-prod.yml**

~~~yaml
spring:
  cloud:
    stream:
      function:
        autodetect: false
~~~

Kích hoạt profile production từ môi trường chạy:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Cấu hình trong ví dụ đảm bảo profile production không tự động binding các bean hàm ngoài lựa chọn đã khai báo. Hãy giữ **definition** ở một nguồn cấu hình được nạp cho profile đó và xác minh cấu hình đã phân giải khi khởi động.

Nếu muốn tắt autodetect ở mọi môi trường, đặt thuộc tính trong **application.yml**. Nếu chỉ một profile cần tắt, đặt thuộc tính trong tệp profile tương ứng. Tránh khai báo cùng thuộc tính ở nhiều nơi với các giá trị mâu thuẫn, vì khi đó việc xác định hành vi thực tế phụ thuộc thứ tự ưu tiên của các property source.

## 8. Kiểm thử hành vi phát hiện và binding

Kiểm thử cấu hình cần chứng minh hàm dự kiến được binding và hàm ngoài danh sách không tạo luồng messaging ngoài ý muốn. Test binder của Spring Cloud Stream có thể hỗ trợ kiểm thử luồng trong ứng dụng mà không cần broker thật. Với hành vi riêng của Kafka, RabbitMQ hoặc Pulsar, cần integration test với binder tương ứng.

Một bộ kiểm thử nên bao gồm:

| Tình huống | Thiết lập | Điều cần xác nhận |
|---|---|---|
| Một bean hàm | Chỉ khai báo một **Consumer** hoặc **Function**. | Binding có tên theo quy tắc và nhận/gửi đúng thông điệp. |
| Nhiều bean hàm, chọn một | Khai báo nhiều bean và đặt **definition** bằng một tên. | Chỉ luồng được chọn được binding theo cấu hình. |
| Tắt autodetect | Đặt **spring.cloud.stream.function.autodetect=false** và chọn hàm bằng **definition**. | Hàm được chọn vẫn hoạt động; bean hàm ngoài danh sách không tự tạo binding. |
| Tắt autodetect nhưng không chọn hàm | Đặt **autodetect=false** và bỏ **definition**. | Không có luồng hàm tự động được tạo; kiểm thử phát hiện cấu hình thiếu. |
| Nhiều hàm độc lập | Dùng danh sách tên phân cách bằng dấu chấm phẩy. | Từng hàm có binding và destination đúng. |
| Function composition | Dùng **functionA|functionB** với kiểu dữ liệu tương thích. | Đầu ra của bước đầu trở thành đầu vào của bước sau. |
| Profile khác nhau | Chạy với profile local và prod. | Giá trị autodetect và definition đúng với môi trường. |

Ví dụ kiểm thử tích hợp với test binder có thể gửi một thông điệp vào binding và xác nhận kết quả đầu ra:

~~~java
@SpringBootTest(properties = {
    "spring.cloud.function.definition=normalizeOrder",
    "spring.cloud.stream.function.autodetect=false"
})
class NormalizeOrderBindingTest {
    // Dùng InputDestination và OutputDestination của test binder
    // để gửi payload vào normalizeOrder-in-0 và đọc kết quả
    // từ normalizeOrder-out-0.
}
~~~

Đoạn mã trên minh họa cấu hình kiểm thử; lớp test cần khai báo test binder và dependency tương ứng trong dự án. Không coi việc ApplicationContext khởi động thành công là bằng chứng duy nhất. Hãy xác nhận thông điệp đi qua đúng binding và các bean không được chọn không tạo luồng ngoài dự kiến.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Một hàm ngoài dự kiến được binding | Tự phát hiện đang bật và bean hàm được Spring đăng ký. | Xem các bean Supplier/Function/Consumer và đặt **autodetect=false** nếu cần. |
| Không có binding sau khi tắt autodetect | Chưa khai báo **spring.cloud.function.definition** hoặc tên hàm sai. | Đối chiếu tên bean và definition. |
| Binding được tạo nhưng không kết nối đúng đích | Cấu hình dùng tên function thay cho binding name hoặc đặt sai destination. | Kiểm tra binding đầu vào **tên-hàm-in-0** và binding đầu ra **tên-hàm-out-0**. |
| Hàm không được phát hiện | Bean chưa được đăng ký, kiểu trả về không phải functional interface được hỗ trợ hoặc cấu hình bean không được nạp. | Kiểm tra ApplicationContext và kiểu bean thực tế. |
| Một hàm chạy ở local nhưng không chạy ở production | Profile ghi đè **definition** hoặc **autodetect** theo cách khác. | Kiểm tra profile active và property source. |
| Composition không chạy | Tên hàm sai hoặc kiểu đầu ra/đầu vào giữa hai hàm không tương thích. | Kiểm tra từng bean và chữ ký generic của Function. |
| Cấu hình **autodetect** không có tác dụng | Đặt sai namespace hoặc sai cấp YAML. | Dùng đúng **spring.cloud.stream.function.autodetect**. |

Khi điều tra, nên kiểm tra theo thứ tự: bean đã tồn tại trong ApplicationContext chưa, function name có đúng không, **definition** đang chọn hàm nào, autodetect đang bật hay tắt, binding name có đúng không, cuối cùng mới kiểm tra binder và destination. Cách này giúp tách lỗi phát hiện hàm khỏi lỗi kết nối broker.

## 10. Quy tắc lựa chọn cho ứng dụng thực tế

- Với ứng dụng nhỏ có một hàm xử lý chính, tự phát hiện giúp giảm cấu hình ban đầu.
- Với ứng dụng có nhiều Supplier, Function hoặc Consumer, khai báo **spring.cloud.function.definition** để lựa chọn rõ ràng.
- Với ứng dụng có bean hàm phụ trợ hoặc cần kiểm soát nghiêm ngặt các binding, đặt **spring.cloud.stream.function.autodetect=false**.
- Khi tắt tự phát hiện, luôn kiểm tra rằng definition và các binding cần thiết đã được khai báo.
- Dùng tên bean ổn định và binding name theo quy ước để cấu hình dễ bảo trì.
- Kiểm thử cả trường hợp hàm được chọn lẫn hàm không được chọn.
- Xác minh thuộc tính và hành vi theo phiên bản Spring Cloud Stream đang sử dụng, đặc biệt khi nâng cấp major version.

Tự phát hiện hàm giúp Spring Cloud Stream rút ngắn cấu hình cho luồng đơn giản. Khi ứng dụng có nhiều bean chức năng, **spring.cloud.function.definition** và **spring.cloud.stream.function.autodetect** giúp kiểm soát rõ hàm nào được kết nối với broker. Việc lựa chọn tường minh, đặt tên binding nhất quán và kiểm thử cả trường hợp bật lẫn tắt autodetect giúp luồng xử lý sự kiện dễ dự đoán hơn khi triển khai.
