# Đọc cấu hình hiệu lực và chẩn đoán sai tên hoặc sai cấp thuộc tính

Spring Cloud Stream sử dụng tên binding để nối hàm Supplier, Function hoặc Consumer với destination trên broker. Một cấu hình có thể trông hợp lệ nhưng không có tác dụng nếu tên binding sai, thuộc tính nằm sai cấp hoặc một nguồn cấu hình khác ghi đè giá trị dự kiến. Khi đó ứng dụng có thể khởi động nhưng đọc nhầm destination, dùng consumer group ngoài ý muốn hoặc không bật được tùy chọn riêng của binder.

Để chẩn đoán chính xác, cần lần theo ba lớp: tên hàm và binding mà Spring Cloud Function tạo ra; cấu trúc thuộc tính chung của Spring Cloud Stream; và thuộc tính riêng của binder đang kết nối Kafka, RabbitMQ hoặc Pulsar. Sau đó kiểm tra nguồn nào cung cấp giá trị cuối cùng trong môi trường chạy.

## 1. Hiểu tên binding trước khi đọc cấu hình

Spring Cloud Stream tạo tên binding từ tên bean hàm và hướng dữ liệu. Với các hàm độc lập, quy tắc phổ biến là:

| Kiểu hàm | Binding | Hướng |
|---|---|---|
| Supplier tên orderSource | orderSource-out-0 | Đầu ra |
| Function tên normalizeOrder | normalizeOrder-in-0 | Đầu vào |
| Function tên normalizeOrder | normalizeOrder-out-0 | Đầu ra |
| Consumer tên storeOrder | storeOrder-in-0 | Đầu vào |

Phần tên hàm phải khớp với bean được đăng ký trong Spring ApplicationContext. Hậu tố in biểu thị cổng đầu vào, out biểu thị cổng đầu ra; chỉ số 0 là cổng thứ nhất. Với hàm có nhiều đầu vào hoặc đầu ra, chỉ số có thể tăng theo thứ tự cổng.

Ví dụ:

~~~java
@Bean
Function<OrderSubmitted, OrderAccepted> normalizeOrder() {
    return order -> new OrderAccepted(
        order.orderId(),
        order.customerId()
    );
}
~~~

Nếu hàm được chọn bằng cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

thì hai binding mặc định là normalizeOrder-in-0 và normalizeOrder-out-0. Tên destination không quyết định tên binding. Destination chỉ là tên topic, queue hoặc tài nguyên đích mà binding được ánh xạ tới.

Một lỗi thường gặp là khai báo normalize-order-in-0 trong khi bean thực tế tên normalizeOrder. Spring Cloud Stream không tự suy luận rằng hai tên này tương đương. Hãy lấy tên bean và tên binding chính xác từ cấu hình function, sau đó dùng thống nhất trong mọi thuộc tính.

## 2. Phân biệt binding name, destination và group

Ba giá trị này giải quyết ba mục đích khác nhau:

| Giá trị | Ý nghĩa | Ví dụ |
|---|---|---|
| Binding name | Tên cổng logic trong ứng dụng Spring Cloud Stream | normalizeOrder-in-0 |
| Destination | Tên tài nguyên trên broker mà binding kết nối | orders.submitted |
| Group | Danh tính nhóm consumer cùng tiêu thụ một destination theo ngữ nghĩa binder | order-normalizer |

Binding name thuộc ứng dụng. Destination là điểm giao tiếp trên broker. Group xác định cách consumer tham gia vào việc nhận thông điệp. Vì vậy, không đặt tên binding thành tên topic theo thói quen rồi giả định framework tự ánh xạ, trừ khi cấu hình destination thực sự chỉ định như vậy.

Nếu không khai báo destination, Spring Cloud Stream thường dùng tên binding làm destination mặc định. Cơ chế mặc định này hữu ích cho thử nghiệm đơn giản, nhưng môi trường triển khai nên khai báo destination rõ ràng để tránh vô tình tạo hoặc kết nối tới topic/queue có tên không mong muốn.

Group thường được đặt trực tiếp trong binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.submitted
          group: order-normalizer
~~~

group không nằm trong nhánh consumer của cấu hình binding. Ví dụ normalizeOrder-in-0.consumer.group là sai cấp; cấu hình đúng là normalizeOrder-in-0.group.

## 3. Cấu trúc các cấp thuộc tính Spring Cloud Stream

Một binding thường có ba nhóm thuộc tính:

1. Thuộc tính chung của binding: destination, group, content-type và binder.
2. Thuộc tính consumer hoặc producer dùng chung: retry, backoff, partitioning hoặc các tùy chọn trừu tượng do Spring Cloud Stream cung cấp.
3. Thuộc tính riêng của binder: concurrency, acknowledgement, queue/exchange, Kafka offset hoặc DLQ tùy loại broker.

Ví dụ cấu hình chung:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.submitted
          group: order-normalizer
          content-type: application/json
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
        normalizeOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Trong ví dụ này:

- spring.cloud.function.definition chọn bean hàm cần kích hoạt.
- spring.cloud.stream.bindings.normalizeOrder-in-0 là nhóm thuộc tính của input binding.
- destination, group và content-type nằm trực tiếp dưới binding.
- consumer chứa các thuộc tính tiêu thụ dùng chung.
- normalizeOrder-out-0 là output binding của cùng hàm.

Hãy chú ý mức thụt đầu dòng của YAML. Nếu group bị đặt bên trong consumer, hoặc consumer bị đặt ngang hàng với bindings, ứng dụng có thể không bind được giá trị như mong đợi.

## 4. Thuộc tính chung và thuộc tính riêng của binder

Spring Cloud Stream cung cấp abstraction chung, nhưng không phải mọi tính năng của broker đều có một thuộc tính chung. Cấu hình binder-specific dùng namespace riêng:

| Broker | Namespace thuộc tính riêng cho binding | Ví dụ vị trí |
|---|---|---|
| Kafka | spring.cloud.stream.kafka.bindings | kafka.bindings.normalizeOrder-in-0.consumer |
| RabbitMQ | spring.cloud.stream.rabbit.bindings | rabbit.bindings.normalizeOrder-in-0.consumer |
| Pulsar | Namespace cấu hình theo phiên bản Pulsar binder | pulsar.bindings của binder đang dùng |

Ví dụ, cấu hình Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
        bindings:
          normalizeOrder-in-0:
            consumer:
              start-offset: earliest
              enable-dlq: true
~~~

brokers là cấu hình cấp binder, vì vậy nó nằm dưới spring.cloud.stream.kafka.binder. start-offset và enable-dlq là tùy chọn của Kafka consumer binding, nên chúng nằm dưới spring.cloud.stream.kafka.bindings.normalizeOrder-in-0.consumer.

Một cấu hình sai thường gặp là đặt start-offset trong spring.cloud.stream.bindings.normalizeOrder-in-0.consumer. Đây là nhánh thuộc tính consumer chung, không phải nhánh Kafka-specific. Nếu binder không nhận thuộc tính tại vị trí đó, giá trị mong muốn sẽ không được áp dụng. Cần đối chiếu tên thuộc tính và namespace trong tài liệu của đúng binder và phiên bản.

Với RabbitMQ, tùy chọn riêng có thể liên quan đến exchange, queue, routing key, requeue, acknowledge hoặc dead-letter exchange. Với Pulsar, tùy chọn riêng có thể liên quan đến subscription type, schema, tenant và namespace. Không chuyển nguyên tên thuộc tính Kafka sang binder khác chỉ vì chúng cùng cấu hình một binding.

## 5. Đổi tên binding tường minh khi cần

Trong đa số trường hợp, nên giữ tên binding mặc định để dễ đối chiếu với tên bean hàm. Khi muốn tên binding ngắn hoặc cần ổn định tên logic dù tên hàm thay đổi, Spring Cloud Stream cho phép ánh xạ tên binding ngầm định sang tên tường minh bằng spring.cloud.stream.function.bindings.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        bindings:
          normalizeOrder-in-0: ordersinput
          normalizeOrder-out-0: ordersoutput
      bindings:
        ordersinput:
          destination: orders.submitted
          group: order-normalizer
        ordersoutput:
          destination: orders.accepted
~~~

Sau ánh xạ này, các thuộc tính của binding được khai báo bằng tên tường minh ordersinput và ordersoutput. Nếu chỉ ánh xạ input mà quên output, hoặc khai báo thuộc tính theo tên cũ sau khi đã ánh xạ, cấu hình có thể bị chia thành hai nhánh không được sử dụng như dự định.

Chỉ dùng ánh xạ tên khi có lý do cụ thể. Nó thêm một bước cần kiểm tra và khiến việc tìm binding trong log phức tạp hơn. Khi sử dụng, hãy ghi lại bảng đối chiếu giữa tên ngầm định, tên tường minh và destination.

## 6. Nguồn cấu hình nào đang thắng?

Spring Boot có thể nạp cấu hình từ nhiều nguồn. Các nguồn phổ biến gồm:

- File application.yml hoặc application.properties đóng gói trong ứng dụng.
- File theo profile như application-dev.yml, application-prod.yml.
- File cấu hình bên ngoài artifact, ví dụ file mount trong container.
- Biến môi trường của hệ điều hành hoặc container.
- Thuộc tính JVM truyền qua -D.
- Tham số dòng lệnh truyền khi khởi động ứng dụng.

Các nguồn có thứ tự ưu tiên. Trong các tình huống triển khai thông thường, tham số dòng lệnh có thể ghi đè thuộc tính JVM; thuộc tính JVM và biến môi trường có thể ghi đè cấu hình trong file. Profile-specific config có thể ghi đè cấu hình cơ sở trong cùng nhóm vị trí. Spring Boot còn có các nguồn khác như SPRING_APPLICATION_JSON, test properties và config import; vì vậy, khi cần kết luận chính xác, hãy kiểm tra property source thực tế thay vì dựa vào một thứ tự rút gọn.

Ví dụ file mặc định khai báo:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        bindings:
          normalizeOrder-in-0: ordersinput
          normalizeOrder-out-0: ordersoutput
      bindings:
        ordersinput:
          destination: orders.submitted
          group: order-normalizer
        ordersoutput:
          destination: orders.accepted
~~~

Môi trường production đặt biến:

~~~text
SPRING_CLOUD_STREAM_BINDINGS_ORDERSINPUT_DESTINATION=orders.submitted.v2
~~~

Giá trị được nạp từ môi trường có thể ghi đè destination trong file. Ví dụ này dùng binding alias viết thường là ordersinput để tránh sự mơ hồ về chữ hoa/chữ thường của map key khi bind biến môi trường. Khi đọc application.yml thấy đúng orders.submitted nhưng log cho thấy ứng dụng kết nối orders.submitted.v2, cần kiểm tra các nguồn có ưu tiên cao hơn.

Tên biến môi trường cho thuộc tính lồng nhau cần tuân theo quy tắc relaxed binding của Spring Boot: dấu chấm được chuyển thành dấu gạch dưới, tên được viết hoa và dấu gạch ngang trong tên thuộc tính được loại bỏ. Map key trong biến môi trường có thể được chuẩn hóa chữ thường; với tên binding camelCase hoặc có ký tự đặc biệt, hãy kiểm tra cách bind thực tế trong Actuator hoặc ưu tiên file YAML/command line để tránh đoán sai tên biến.

## 7. Kiểm tra profile và Config Data

Profile quyết định tập cấu hình nào được nạp. Có thể kích hoạt profile bằng:

~~~bash
java -jar stream-app.jar --spring.profiles.active=prod
~~~

Hoặc biến môi trường:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Nếu ứng dụng chạy với profile prod, hãy kiểm tra cả application.yml, application-prod.yml và file cấu hình bên ngoài được nạp. Đừng giả định file application-dev.yml được sử dụng chỉ vì IDE đang dùng file đó trong lần chạy trước.

Các thuộc tính spring.config.import, spring.config.location và spring.config.additional-location cũng ảnh hưởng nơi Spring Boot đọc cấu hình. spring.config.location có thể thay đổi các vị trí mặc định; spring.config.additional-location thêm vị trí ngoài các vị trí mặc định. Khi container mount file cấu hình, kiểm tra đường dẫn mount và tham số khởi động để biết file nào thật sự được đọc.

Một dấu hiệu hữu ích là log khởi động Spring Boot có thông tin profile đang hoạt động. Tuy nhiên, log profile chỉ cho biết profile đã chọn; nó không chứng minh từng thuộc tính binding đã được nạp đúng. Cần tiếp tục kiểm tra giá trị và nguồn của thuộc tính cụ thể.

## 8. Đọc cấu hình hiệu lực bằng Spring Boot Actuator

Actuator cung cấp hai endpoint hữu ích:

| Endpoint | Mục đích |
|---|---|
| /actuator/env | Xem các property source và giá trị cấu hình mà Spring Environment nhìn thấy |
| /actuator/configprops | Xem các đối tượng @ConfigurationProperties sau khi Spring bind thuộc tính |

Để dùng trong môi trường phát triển, thêm dependency spring-boot-starter-actuator và cấu hình exposure phù hợp. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
~~~

Sau khi khởi động ứng dụng, có thể truy vấn:

~~~text
GET /actuator/env
GET /actuator/env/spring.cloud.stream.bindings.ordersinput.destination
GET /actuator/configprops
~~~

env giúp tìm property source nào cung cấp giá trị và có thể hiển thị nguồn/origin của thuộc tính. configprops giúp kiểm tra giá trị đã bind vào các đối tượng cấu hình. Hai endpoint trả lời hai câu hỏi khác nhau: Environment nhìn thấy gì và đối tượng cấu hình đã nhận được gì.

Giá trị nhạy cảm thường được Actuator che đi theo cơ chế sanitization. Không tắt sanitization chỉ để xem password hoặc token. Không mở rộng các endpoint này ra Internet hoặc mạng không tin cậy. Nếu cần dùng trong staging, hãy giới hạn quyền truy cập bằng Spring Security, network policy hoặc cơ chế bảo vệ của nền tảng triển khai, và chỉ expose endpoint cần thiết.

Nếu env cho thấy thuộc tính đúng nhưng configprops không có giá trị như mong muốn, hãy kiểm tra tên thuộc tính, prefix của đối tượng cấu hình, điều kiện tạo bean và binder đang được sử dụng. Nếu cả hai đều không thấy thuộc tính, kiểm tra file, profile, config import và biến môi trường.

## 9. Đọc log để xác định binding đã được tạo

Khi cấu hình không đúng, bật log chi tiết có giới hạn trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.cloud.stream: DEBUG
    org.springframework.cloud.function: DEBUG
~~~

Log có thể giúp nhận biết:

- Bean hàm nào được phát hiện và function definition nào được chọn.
- Binding nào được tạo và binder nào được dùng.
- Destination và consumer group mà binding kết nối.
- Lỗi khi tạo binding, chuyển đổi payload hoặc kết nối broker.
- Thuộc tính cấu hình nào bị từ chối hoặc không thể áp dụng, nếu binder phát cảnh báo.

Mức DEBUG có thể tạo nhiều log và làm lộ metadata vận hành. Chỉ bật trong thời gian chẩn đoán, giới hạn phạm vi package và tắt lại sau khi đã tìm ra nguyên nhân. Tránh ghi payload hoặc credential vào log.

--debug của Spring Boot chủ yếu tạo condition evaluation report cho quá trình auto-configuration. Báo cáo này hữu ích khi một auto-configuration không được kích hoạt, nhưng không phải bản dump đầy đủ của mọi binding property. Hãy kết hợp nó với Actuator, log Spring Cloud Stream và dependency/configuration thực tế.

## 10. Các lỗi tên hoặc cấp thuộc tính thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không thấy input binding | Sai tên bean, thiếu function definition hoặc tên binding sai | Kiểm tra bean name, spring.cloud.function.definition và log khởi tạo |
| Binding kết nối destination mặc định | Thiếu destination hoặc đặt sai cấp | Xem env và configprops của binding |
| Consumer group không như dự kiến | Đặt group bên trong consumer hoặc profile khác ghi đè | Đưa group trực tiếp dưới binding và xem property source |
| Kafka offset không có tác dụng | Đặt thuộc tính Kafka trong nhánh common consumer | Dùng spring.cloud.stream.kafka.bindings.binding-name.consumer |
| RabbitMQ không dùng routing key | Đặt thuộc tính ở nhánh Kafka hoặc sai cấp binder | Kiểm tra spring.cloud.stream.rabbit.bindings.binding-name |
| Một binding nhận payload sai kiểu | content-type, native decoding hoặc serializer không phù hợp | Kiểm tra header, content type và cấu hình binder |
| Cấu hình trong YAML đúng nhưng runtime khác | Environment, JVM, command line hoặc profile ghi đè | Kiểm tra /actuator/env và origin |
| Ứng dụng khởi động nhưng một thuộc tính không có tác dụng | Sai chính tả hoặc binder không hỗ trợ thuộc tính đó | So khớp tên thuộc tính với tài liệu đúng phiên bản; xem log |

Ví dụ một cấu hình sai:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.submitted
          consumer:
            group: order-normalizer
            start-offset: earliest
~~~

Trong ví dụ này, group được đặt sai cấp. start-offset cũng là thuộc tính riêng của Kafka binder, nên nó không thuộc nhánh consumer chung. Cấu hình đúng cần tách rõ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.submitted
          group: order-normalizer
    kafka:
      binder:
        brokers: localhost:9092
      bindings:
        normalizeOrder-in-0:
          consumer:
            start-offset: earliest
~~~

Khi di chuyển thuộc tính, không chỉ sửa thụt dòng mà phải đặt nó dưới đúng prefix. Một thuộc tính có tên hợp lệ nhưng ở sai namespace vẫn không cấu hình được thành phần mong muốn.

## 11. Quy trình chẩn đoán theo từng bước

Khi một binding không hoạt động như dự kiến, thực hiện theo thứ tự sau:

1. **Xác định hàm:** kiểm tra tên bean Supplier/Function/Consumer và giá trị spring.cloud.function.definition.
2. **Tính tên binding:** suy ra tên input/output theo quy tắc function-name-in-0 hoặc function-name-out-0; kiểm tra mọi ánh xạ tên tường minh.
3. **Xác định destination và group:** kiểm tra chúng nằm trực tiếp dưới spring.cloud.stream.bindings.binding-name.
4. **Xác định cấp thuộc tính:** phân loại thuộc tính là common, consumer/producer hay binder-specific.
5. **Xác định binder:** kiểm tra binder được chọn và namespace riêng, ví dụ spring.cloud.stream.kafka.bindings hoặc spring.cloud.stream.rabbit.bindings.
6. **Kiểm tra profile và nguồn cấu hình:** xác nhận profile đang hoạt động, file import, biến môi trường, JVM property và command line.
7. **Đọc cấu hình hiệu lực:** dùng Actuator env và configprops trong môi trường được bảo vệ.
8. **Đọc log:** bật DEBUG có giới hạn để xem function, binding, destination và lỗi khởi tạo.
9. **Kiểm thử lại:** dùng Test Binder cho luồng trong ứng dụng và broker thật cho các tính năng đặc thù.
10. **Thu hẹp thay đổi:** sửa đúng thuộc tính hoặc nguồn đang sai, khởi động lại và xác minh giá trị hiệu lực một lần nữa.

Không nên thay đổi nhiều thuộc tính cùng lúc trong khi chưa biết nguồn gây lỗi. Nếu thay đổi đồng thời function definition, binding name, destination và binder, rất khó xác định điều gì đã giải quyết vấn đề.

## 12. Checklist trước khi bàn giao cấu hình

- [ ] Tên bean hàm trùng với function definition đã chọn.
- [ ] Tên binding được suy ra đúng hoặc được ánh xạ tường minh có chủ đích.
- [ ] destination và group nằm trực tiếp dưới binding.
- [ ] Thuộc tính common nằm dưới spring.cloud.stream.bindings.
- [ ] Thuộc tính riêng nằm dưới namespace của đúng binder.
- [ ] Profile và Config Data được xác nhận ở môi trường đích.
- [ ] Nguồn cấu hình có ưu tiên cao hơn không ghi đè giá trị dự kiến.
- [ ] Actuator hoặc log xác nhận binding kết nối đúng destination và group.
- [ ] Test Binder và integration test phù hợp đã chạy.
- [ ] Endpoint chẩn đoán được bảo vệ và không làm lộ thông tin nhạy cảm.

## Tài liệu tham khảo chính thức

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, profile và thứ tự ưu tiên.
- [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cách expose và bảo vệ endpoint quản trị.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html): binding, function, binder và cấu hình chung.
- [Spring Cloud Stream Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html): cấu hình riêng cho Kafka binder.
- [Spring Cloud Stream RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): cấu hình riêng cho RabbitMQ binder.
