# Quy tắc đặt tên và quản lý cấu hình giữa các môi trường

Trong Spring Cloud Stream, tên hàm, tên binding và tên destination liên kết với nhau nhưng đại diện cho những khái niệm khác nhau. Tên hàm xác định thành phần xử lý trong ứng dụng; tên binding xác định cổng vào hoặc ra của hàm; destination xác định nơi binder kết nối trên Kafka, RabbitMQ hoặc Pulsar. Cấu hình binding còn có thể chứa consumer group, content type, retry và các thuộc tính riêng của broker.

Khi triển khai cùng một ứng dụng ở môi trường phát triển, kiểm thử và production, cần giữ hợp đồng binding ổn định trong khi thay đổi destination, group, thông tin kết nối và các tham số vận hành theo môi trường. Quy tắc đặt tên rõ ràng cùng externalized configuration giúp tránh việc đổi tên bean làm hỏng cấu hình, gửi nhầm dữ liệu sang broker hoặc dùng chung consumer group ngoài ý muốn.

## 1. Phân biệt tên hàm, tên binding và destination

Trong mô hình hàm, Spring Cloud Stream suy ra tên binding từ tên bean và hướng dữ liệu:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên bean hàm | `createOrder` | Tên hàm `Supplier`, `Function` hoặc `Consumer` được Spring phát hiện. |
| Binding đầu vào | `createOrder-in-0` | Cổng đầu vào thứ nhất của hàm. |
| Binding đầu ra | `createOrder-out-0` | Cổng đầu ra thứ nhất của hàm. |
| Destination | `orders.commands` | Đích logic mà binder ánh xạ tới tài nguyên trên broker. |
| Consumer group | `order-service` | Nhóm logic các consumer cùng chia sẻ việc nhận dữ liệu. |

Quy tắc cơ bản:

- `Supplier<T>` có binding đầu ra dạng `<functionName>-out-0`.
- `Function<T, R>` có binding đầu vào `<functionName>-in-0` và đầu ra `<functionName>-out-0`.
- `Consumer<T>` có binding đầu vào `<functionName>-in-0`.
- Với hàm có nhiều cổng vào hoặc ra, chỉ số tăng theo thứ tự cổng, chẳng hạn `-in-1` hoặc `-out-1`.

Ví dụ, bean `createOrder` có kiểu `Function<CreateOrder, OrderCreated>` sẽ có hai binding `createOrder-in-0` và `createOrder-out-0`. Có thể ánh xạ chúng tới hai destination riêng:

```yaml
spring:
  cloud:
    function:
      definition: createOrder
    stream:
      bindings:
        createOrder-in-0:
          destination: orders.commands
          group: order-command-handler
        createOrder-out-0:
          destination: orders.events
```

Tên binding được dùng trong cấu hình và khi quan sát ứng dụng. Tên destination được dùng để tổ chức luồng dữ liệu trên broker. Hai ứng dụng có thể dùng tên hàm khác nhau nhưng cùng đọc một destination; ngược lại, cùng một hàm có thể được cấu hình đọc hoặc ghi destination khác nhau ở mỗi môi trường.

## 2. Quy tắc đặt tên có thể duy trì lâu dài

Tên hàm nên thể hiện trách nhiệm nghiệp vụ và dùng nhất quán với quy ước đặt tên bean trong Java, thường là lower camel case: `createOrder`, `enrichOrder`, `updateInventory`. Tránh các tên quá chung như `process`, `handler` hoặc `function1` vì chúng khó phân biệt khi ứng dụng có nhiều binding.

Tên destination nên phản ánh loại dữ liệu hoặc luồng nghiệp vụ, không phụ thuộc tên class Java hay tên instance đang chạy. Ví dụ:

- `orders.commands`: các yêu cầu xử lý đơn hàng.
- `orders.events`: các sự kiện về vòng đời đơn hàng.
- `inventory.reservations`: yêu cầu hoặc dữ liệu giữ hàng, theo hợp đồng đã định nghĩa.
- `payments.authorized`: sự kiện thanh toán đã được chấp thuận.

Tên destination cần nhất quán về số nhiều, dấu phân cách và ngữ nghĩa. Tránh dùng cùng một destination cho các payload khác schema hoặc khác mục đích chỉ vì chúng có cùng cấu trúc ở thời điểm hiện tại. Khi cần thay đổi hợp đồng, có thể dùng phiên bản rõ ràng như `orders.events.v2` hoặc một chiến lược schema compatibility có kế hoạch.

Consumer group nên mô tả một loại xử lý logic, chẳng hạn `billing-projection` hoặc `inventory-service`. Các instance thuộc cùng một dịch vụ xử lý thường dùng chung group để chia tải. Hai dịch vụ độc lập cần nhận toàn bộ bản tin thường phải dùng group/subscription riêng, tùy cách broker triển khai fan-out.

Không nên đưa tên môi trường (`dev`, `staging`, `prod`) vào tên bean hoặc binding nếu chỉ có destination và thông tin kết nối thay đổi. Có thể đưa môi trường vào tên tài nguyên broker nếu hạ tầng yêu cầu cô lập, nhưng nên thực hiện qua cấu hình để mã nguồn giữ ổn định.

## 3. Chọn function được kích hoạt rõ ràng

Ứng dụng có thể chứa nhiều bean hàm. Thuộc tính `spring.cloud.function.definition` xác định bean hoặc chuỗi hàm mà Spring Cloud Stream cần kích hoạt:

```yaml
spring:
  cloud:
    function:
      definition: createOrder;updateInventory
```

Danh sách nhiều hàm độc lập được phân tách bằng dấu chấm phẩy. Nếu muốn ghép các hàm theo thứ tự, Spring Cloud Function sử dụng dấu `|`, ví dụ `validateOrder|enrichOrder`. Hai cách khai báo mang ý nghĩa khác nhau: dấu `;` chọn nhiều hàm độc lập, còn dấu `|` tạo một pipeline nối đầu ra bước trước với đầu vào bước sau.

Nên khai báo definition tường minh trong cấu hình triển khai thay vì dựa vào việc framework tự phát hiện mọi bean hàm. Khi thêm một bean `Consumer` phụ trợ hoặc một hàm chỉ dùng trong kiểm thử, definition rõ ràng giúp tránh vô tình tạo binding ngoài ý muốn.

Khi đổi tên bean, các tên binding mặc định cũng đổi theo. Ví dụ, đổi `createOrder` thành `handleOrderCommand` làm tên binding chuyển từ `createOrder-in-0` sang `handleOrderCommand-in-0`. Cần cập nhật đồng bộ `function.definition`, binding properties, alias, dashboard, cảnh báo và kiểm thử có tham chiếu tên cũ.

## 4. Dùng binding alias khi cần tên cấu hình ổn định

Mặc định, tên binding gắn với tên hàm. Nếu cần tách tên binding trong cấu hình khỏi tên bean Java, có thể khai báo alias bằng `spring.cloud.stream.function.bindings`:

```yaml
spring:
  cloud:
    function:
      definition: createOrder
    stream:
      function:
        bindings:
          createOrder-in-0: order-command-input
          createOrder-out-0: order-event-output
      bindings:
        order-command-input:
          destination: orders.commands
          group: order-command-handler
        order-event-output:
          destination: orders.events
```

Sau khi khai báo alias, cấu hình destination và các thuộc tính binding dùng tên alias (`order-command-input`, `order-event-output`). Tên hàm Java vẫn là `createOrder`; alias chỉ thay tên binding được dùng trong cấu hình.

Alias có ích khi cần duy trì tên cấu hình ổn định qua nhiều lần đổi tên bean hoặc khi tên binding mặc định quá dài. Tuy nhiên, alias tạo thêm một lớp ánh xạ mà người vận hành cần hiểu. Nếu không có nhu cầu cụ thể, tên mặc định thường dễ truy vết hơn và phù hợp với tài liệu Spring Cloud Stream.

## 5. Tách cấu hình chung khỏi cấu hình theo môi trường

Những giá trị giống nhau ở mọi môi trường nên đặt trong `application.yml`; những giá trị thay đổi theo môi trường có thể đặt trong file profile như `application-dev.yml`, `application-test.yml` và `application-prod.yml`.

Ví dụ, file `application.yml` giữ tên hàm, binding và content type:

```yaml
spring:
  application:
    name: order-stream-service
  cloud:
    function:
      definition: createOrder
    stream:
      bindings:
        createOrder-in-0:
          content-type: application/json
          consumer:
            max-attempts: 3
        createOrder-out-0:
          content-type: application/json
```

File `application-dev.yml` có thể trỏ tới tài nguyên dùng trong môi trường phát triển:

```yaml
spring:
  cloud:
    stream:
      bindings:
        createOrder-in-0:
          destination: dev.orders.commands
          group: order-command-handler-dev
        createOrder-out-0:
          destination: dev.orders.events
```

File `application-prod.yml` cung cấp destination và group của production:

```yaml
spring:
  cloud:
    stream:
      bindings:
        createOrder-in-0:
          destination: orders.commands
          group: order-command-handler
        createOrder-out-0:
          destination: orders.events
```

Kích hoạt profile từ môi trường chạy, ví dụ:

```text
SPRING_PROFILES_ACTIVE=prod
```

Khi profile `prod` hoạt động, cấu hình trong `application-prod.yml` bổ sung hoặc ghi đè các giá trị tương ứng trong cấu hình chung. Không nên đặt `spring.profiles.active` bên trong file cấu hình dành riêng cho profile; profile cần được chọn từ nguồn cấu hình bên ngoài hoặc tham số khởi chạy.

Một cách khác là dùng nhiều YAML document với `spring.config.activate.on-profile`, nhưng cần thống nhất một kiểu tổ chức để nhóm vận hành dễ tìm nguồn của mỗi giá trị.

## 6. Externalized configuration và biến môi trường

Externalized configuration cho phép cùng một artifact ứng dụng chạy ở nhiều môi trường mà không phải sửa mã nguồn hoặc đóng gói lại chỉ để thay destination hay endpoint broker.

Có thể dùng placeholder để lấy giá trị từ biến môi trường hoặc nguồn cấu hình khác:

```yaml
spring:
  cloud:
    stream:
      bindings:
        createOrder-in-0:
          destination: ${ORDERS_COMMANDS_DESTINATION:orders.commands}
          group: ${ORDERS_COMMANDS_GROUP:order-command-handler}
```

Trong ví dụ, nếu biến `ORDERS_COMMANDS_DESTINATION` được cung cấp thì ứng dụng dùng giá trị đó; nếu không, giá trị mặc định `orders.commands` được sử dụng. Có thể áp dụng cách tương tự cho group, địa chỉ broker, timeout hoặc các tham số vận hành.

Spring Boot hỗ trợ relaxed binding giữa tên property và tên biến môi trường. Ví dụ, property:

```text
spring.cloud.stream.bindings.createOrder-in-0.destination
```

có thể được đặt qua biến môi trường:

```text
SPRING_CLOUD_STREAM_BINDINGS_CREATEORDER_IN_0_DESTINATION
```

Khi chuyển property sang biến môi trường, tên được viết hoa, dấu chấm được thay bằng dấu gạch dưới và dấu gạch ngang được loại bỏ theo quy tắc ánh xạ của Spring Boot. Với tên binding phức tạp, cần kiểm tra tên biến thực tế trong môi trường chạy và tránh các tên dễ gây nhầm lẫn.

Các nguồn cấu hình của Spring Boot có thứ tự ưu tiên; nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trong file cấu hình. Trong triển khai thông thường, biến môi trường, system property hoặc tham số dòng lệnh có thể ghi đè giá trị đóng gói trong file. Thứ tự chính xác còn phụ thuộc phiên bản Spring Boot và cách nạp Config Data, vì vậy cần thống nhất quy ước và kiểm tra cấu hình hiệu lực khi vận hành.

## 7. Quản lý thông tin kết nối và bí mật

Địa chỉ broker, username, password, token và chứng thư không nên được ghi trực tiếp vào file cấu hình được commit vào Git. Thay vào đó, dùng biến môi trường được cấp khi triển khai, secret manager hoặc nền tảng quản lý cấu hình bảo mật của tổ chức.

Ví dụ placeholder cho thông tin kết nối:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS}
          configuration:
            security.protocol: ${KAFKA_SECURITY_PROTOCOL:SASL_SSL}
            sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
```

Đây là ví dụ cho Kafka binder; RabbitMQ và Pulsar có các thuộc tính kết nối, xác thực và TLS riêng. Không dùng nguyên cấu hình Kafka cho binder khác. Các giá trị secret cần được cấp qua kênh bảo mật, giới hạn quyền đọc và luân chuyển theo chính sách. Không ghi password hoặc token ra log khi ứng dụng khởi động hay khi in cấu hình đã bind.

Nếu một placeholder bắt buộc không được cung cấp, nên để ứng dụng thất bại sớm khi khởi động thay vì âm thầm dùng một endpoint hoặc thông tin mặc định không an toàn. Giá trị mặc định phù hợp cho tên destination trong môi trường local có thể không phù hợp với credential hoặc địa chỉ production.

## 8. Cấu hình thuộc tính chung và thuộc tính riêng của binder

Các thuộc tính ở `spring.cloud.stream.bindings` mô tả cấu hình chung của binding, chẳng hạn destination, group, content type và một số tùy chọn consumer/producer. Các thuộc tính riêng của broker nằm trong namespace binder tương ứng.

| Nhu cầu | Cấu hình thường gặp | Lưu ý |
|---|---|---|
| Destination và group | `spring.cloud.stream.bindings.<binding>.destination`, `.group` | Dùng để xác định nơi gửi/nhận và nhóm xử lý. |
| Content type | `spring.cloud.stream.bindings.<binding>.content-type` | Phải tương thích với serializer/converter và schema. |
| Retry consumer | `spring.cloud.stream.bindings.<binding>.consumer.max-attempts` | Chi tiết retry và DLQ phụ thuộc binder. |
| Kafka broker | `spring.cloud.stream.kafka.binder.*` | Dành cho kết nối và tùy chọn riêng của Kafka binder. |
| RabbitMQ binder | `spring.cloud.stream.rabbit.binder.*` | Dành cho kết nối và tùy chọn riêng của Rabbit binder. |
| Pulsar binder | Namespace cấu hình của Pulsar binder và Pulsar client | Kiểm tra tài liệu đúng phiên bản binder/client. |

Không nên đặt thuộc tính riêng của broker dưới binding chung nếu binder không nhận diện thuộc tính đó. Khi cần cấu hình consumer/producer riêng cho từng binding, dùng namespace mở rộng mà binder hỗ trợ và đặt đúng tên binding.

## 9. Nhiều binder trong cùng một ứng dụng

Một ứng dụng có thể dùng nhiều binder, chẳng hạn một luồng publish tới Kafka và một luồng khác gửi tới RabbitMQ. Khi có nhiều binder trên classpath, cần khai báo rõ binder nào được sử dụng cho binding nào.

Ví dụ minh họa cách gán binder theo tên:

```yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvents-out-0:
          destination: audit.events
          binder: kafkaCluster
        notificationRequests-out-0:
          destination: notifications.requests
          binder: rabbitCluster
      binders:
        kafkaCluster:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_BROKERS}
        rabbitCluster:
          type: rabbit
          environment:
            spring:
              cloud:
                stream:
                  rabbit:
                    binder:
                      nodes: ${RABBIT_NODES}
```

Đây là cấu trúc minh họa; các thuộc tính kết nối cụ thể cần được đối chiếu với phiên bản binder đang dùng. Khi cấu hình nhiều binder, kiểm tra `defaultCandidate`, môi trường cấu hình lồng nhau, dependency trên classpath và quyền truy cập tới từng broker. Không để binding quan trọng tự chọn binder mặc định khi ứng dụng có nhiều lựa chọn.

## 10. Quản lý group và destination giữa các môi trường

Consumer group là một phần quan trọng của hành vi giao nhận. Nếu hai instance của cùng dịch vụ dùng chung group, chúng thường chia sẻ việc nhận message theo cơ chế broker. Nếu hai dịch vụ độc lập dùng cùng group, chúng có thể chia tải với nhau thay vì mỗi dịch vụ nhận toàn bộ sự kiện.

Đối với Kafka, group gắn với offset và phân phối partition. Với RabbitMQ, binder có thể tạo queue gắn với group; không có group thường tương ứng với queue ẩn danh hoặc không bền vững theo cấu hình. Với Pulsar, group thường ánh xạ tới subscription. Chi tiết khác nhau giữa binder, do đó tên group cần được thiết kế có chủ đích.

Một số quy tắc thực hành:

- Mỗi loại xử lý logic có group riêng nếu cần nhận đầy đủ luồng sự kiện độc lập.
- Các instance của cùng một dịch vụ dùng cùng group để chia tải.
- Tránh dùng chung group giữa môi trường dev và production; nếu kết nối cùng broker, chúng có thể cạnh tranh nhận message.
- Không thay group production tùy tiện vì group mới có thể bắt đầu đọc từ vị trí khác theo chính sách offset/subscription.
- Đặt destination tách biệt giữa môi trường nếu cần ngăn dữ liệu thử nghiệm đi vào luồng production.
- Xác định retention, quyền truy cập và chính sách tạo/xóa topic, queue hoặc subscription cùng với cấu hình ứng dụng.

## 11. Kiểm soát cấu hình khi phát hành

Cấu hình binding ảnh hưởng trực tiếp tới luồng dữ liệu, vì vậy nên được quản lý và kiểm tra như một phần của phiên bản triển khai:

1. Lưu cấu hình không chứa secret trong hệ thống quản lý phiên bản.
2. Review thay đổi tên hàm, binding, destination và group như thay đổi hợp đồng tích hợp.
3. Kiểm tra profile được kích hoạt và xác nhận các placeholder bắt buộc đã có giá trị.
4. Khởi chạy ứng dụng với profile tương ứng trong môi trường kiểm thử để phát hiện lỗi binding hoặc converter.
5. Xác minh destination, group, partition, quyền truy cập và binder thực tế trước khi rollout production.
6. Theo dõi log khởi động, publish/consume rate, consumer lag, lỗi xác thực, retry và DLQ sau phát hành.
7. Có kế hoạch rollback cấu hình, nhất là khi đổi destination, group, schema hoặc thuộc tính partition.

Thay đổi destination có thể làm ứng dụng đọc một luồng dữ liệu mới; thay đổi group có thể làm thay đổi vị trí tiêu thụ; thay đổi content type có thể khiến consumer không giải mã được payload. Vì vậy, các thay đổi này cần được kiểm thử như thay đổi tích hợp, không chỉ là chỉnh sửa văn bản YAML.

## 12. Checklist thiết kế tên và cấu hình

Trước khi hoàn tất cấu hình cho một binding, hãy xác minh:

1. Tên bean có mô tả đúng trách nhiệm nghiệp vụ và được khai báo trong `spring.cloud.function.definition` không?
2. Binding mặc định có đúng hướng `in`/`out` và chỉ số cổng không?
3. Có lý do cụ thể để dùng alias hay nên giữ tên mặc định?
4. Destination có thể hiện rõ loại dữ liệu và hợp đồng schema không?
5. Consumer group có phân biệt đúng các loại xử lý và các môi trường không?
6. Content type và schema có tương thích giữa producer và consumer không?
7. Giá trị thay đổi theo môi trường có được externalize bằng profile, placeholder hoặc biến môi trường không?
8. Credential và token có được lấy từ nguồn bí mật an toàn, không commit vào repository không?
9. Thuộc tính broker có nằm đúng namespace binder và đúng phiên bản không?
10. Thay đổi cấu hình có được kiểm thử, quan sát và có phương án rollback không?

Khi tên hàm, binding, destination và group được phân biệt rõ, còn cấu hình môi trường được quản lý tập trung và có kiểm soát, ứng dụng Spring Cloud Stream sẽ dễ triển khai trên nhiều môi trường, dễ đổi broker và dễ điều tra sự cố hơn.
