# Thứ tự ưu tiên cấu hình Spring Boot, binder và binding

Một ứng dụng Spring Cloud Stream dùng Pulsar có thể nhận cấu hình từ Spring Boot, từ Pulsar binder và từ từng input/output binding. Khi cùng một tùy chọn xuất hiện ở nhiều nơi, ứng dụng cần biết giá trị nào được áp dụng. Nếu không phân biệt các phạm vi này, một thay đổi ở file cấu hình có thể không có tác dụng, hoặc một binding vô tình dùng chung timeout, schema hay subscription với các binding khác.

Với Pulsar binder, tài liệu Spring Cloud Stream nêu rõ thứ tự áp dụng cho cùng một Pulsar option là **extended binding properties → binder properties → Spring Boot properties** (từ ưu tiên cao xuống thấp). Ngoài ra, Spring Boot có một thứ tự riêng giữa các nguồn cấu hình như YAML, environment variable, system property và command-line argument. Hai thứ tự này giải quyết hai câu hỏi khác nhau và không nên gộp thành một danh sách duy nhất.

Bài học này dùng ứng dụng có các bean Supplier/Function/Consumer để minh họa cách đặt cấu hình chung, cấu hình binder và cấu hình riêng cho binding. Các ví dụ tập trung vào Pulsar binder của Spring Cloud Stream; phần cấu hình chung của Spring Cloud Stream cũng áp dụng cho các binder khác, nhưng tên và semantics của extended properties phụ thuộc từng binder.

Các đường dẫn reference trong bài đối chiếu Spring Cloud Stream 5.1.0 và Spring Boot 4.2.0. Nếu dự án dùng release train khác, hãy kiểm tra lại configuration metadata và reference đúng phiên bản vì property có thể đổi tên hoặc thay đổi cách bind.

## 1. Bốn phạm vi cấu hình thường gặp

Trước tiên, phân biệt các nhóm prefix:

| Phạm vi | Prefix ví dụ | Mục đích |
|---|---|---|
| Spring Boot / Spring for Apache Pulsar | `spring.pulsar.*` | Cấu hình client, producer, consumer, administration dùng chung trong ứng dụng |
| Pulsar binder cấp ứng dụng | `spring.cloud.stream.pulsar.binder.*` | Cấu hình Pulsar được áp dụng chung qua binder cho các binding |
| Spring Cloud Stream common binding | `spring.cloud.stream.bindings.<bindingName>.*` | Cấu hình destination, group, content type, binder và thuộc tính producer/consumer chung của một binding |
| Pulsar extended binding | `spring.cloud.stream.pulsar.bindings.<bindingName>.*` | Cấu hình riêng cho một binding theo khả năng của Pulsar binder, như schema type, message type hoặc producer/consumer option |

Ngoài các prefix trên, Spring Cloud Stream còn có các prefix default:

- `spring.cloud.stream.default.*` áp dụng giá trị chung cho các binding.
- `spring.cloud.stream.pulsar.default.<producer|consumer>.*` áp dụng giá trị extended chung cho các binding Pulsar khi thuộc tính đó được binder hỗ trợ.
- Cấu hình cụ thể theo binding có thể ghi đè giá trị default tương ứng.

Đừng nhầm `spring.cloud.stream.pulsar.binder` với `spring.cloud.stream.binders.<configurationName>`. Prefix thứ nhất cấu hình Pulsar binder type. Prefix thứ hai khai báo một binder configuration instance có tên, thường dùng khi ứng dụng có nhiều binder hoặc nhiều kết nối broker.

## 2. Sơ đồ thứ tự ưu tiên của Pulsar binder

Khi cùng một Pulsar option được khai báo ở ba cấp, binder áp dụng theo thứ tự:

~~~mermaid
flowchart TD
    A[Extended binding properties<br/>spring.cloud.stream.pulsar.bindings.name.*] -->|Ưu tiên cao nhất| D[Giá trị hiệu lực cho binding]
    B[Binder properties<br/>spring.cloud.stream.pulsar.binder.*] -->|Fallback nếu binding chưa đặt| D
    C[Spring Boot Pulsar properties<br/>spring.pulsar.*] -->|Fallback thấp hơn| D
~~~

Ví dụ cùng thuộc tính `send-timeout`:

| Cấp | Key cấu hình | Giá trị |
|---|---|---:|
| Spring Boot | `spring.pulsar.producer.send-timeout` | `30s` |
| Pulsar binder | `spring.cloud.stream.pulsar.binder.producer.send-timeout` | `20s` |
| Binding `publishOrder-out-0` | `spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout` | `5s` |

Kết quả: binding `publishOrder-out-0` sử dụng `5s`. Các binding producer khác không có giá trị riêng sẽ dùng cấu hình binder `20s`; nếu binder cũng không khai báo, chúng dùng giá trị Spring Boot `30s`.

Thứ tự này là thứ tự áp dụng **giữa các phạm vi Pulsar binder cho cùng một tùy chọn**. Nó không nói rằng mọi key dưới `spring.cloud.stream.bindings` luôn thắng mọi key dưới `spring.pulsar`. Cần so sánh đúng loại property và đúng prefix mà tài liệu binder quy định.

## 3. Spring Boot property-source precedence là một trục khác

Spring Boot đọc giá trị từ nhiều nguồn. Khi **cùng một key** xuất hiện trong nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ thắng. Với ứng dụng chạy thông thường, các nguồn thường gặp theo thứ tự thấp đến cao gồm:

1. Default properties được đặt qua `SpringApplication.setDefaultProperties`.
2. `@PropertySource` trên cấu hình.
3. Config data, gồm `application.yml` và file profile.
4. Random value property source.
5. Environment variables của hệ điều hành/container.
6. Java system properties (`-D...`).
7. JNDI và các servlet context/config init parameter nếu môi trường có dùng.
8. `SPRING_APPLICATION_JSON`.
9. Command-line arguments như `--spring.pulsar.producer.send-timeout=...`.

Các nguồn test như `@SpringBootTest(properties=...)`, `@DynamicPropertySource` và `@TestPropertySource` có quy tắc riêng trong test context. Hãy tra reference của đúng Spring Boot version nếu cần so sánh chính xác trong kiểm thử.

Trong Config Data, thứ tự phổ biến là:

| Nguồn file | Mức ưu tiên |
|---|---|
| `application.yml` đóng gói trong JAR | Thấp hơn |
| `application-{profile}.yml` đóng gói trong JAR | Cao hơn file cơ sở đóng gói |
| `application.yml` bên ngoài JAR | Cao hơn file đóng gói |
| `application-{profile}.yml` bên ngoài JAR | Cao hơn file cơ sở bên ngoài |

Command-line argument mặc định ghi đè giá trị cùng key trong file cấu hình. Environment variable và system property cũng có thể ghi đè file; thứ tự chính xác phụ thuộc danh sách property sources của Spring Boot.

## 4. Vì sao không thể gộp hai thứ tự thành một?

Giả sử có hai key:

~~~text
spring.pulsar.producer.send-timeout
spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout
~~~

Đây là **hai key khác nhau**. Nếu command line ghi đè key thứ nhất, nó chỉ thay giá trị Spring Boot-level. Nếu key binding-level thứ hai vẫn được khai báo, Pulsar binder vẫn áp dụng giá trị binding-level vì scope extended binding có ưu tiên cao hơn binder/Boot cho cùng option.

Ví dụ:

~~~bash
java -jar order-app.jar \
  --spring.pulsar.producer.send-timeout=45s
~~~

Nếu file cấu hình vẫn có:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
~~~

Thì binding `publishOrder-out-0` vẫn dùng `5s`. Tham số dòng lệnh đã thay đổi giá trị ở key Spring Boot-level, nhưng không xóa hay ghi đè key binding-level khác.

Đây là điểm quan trọng nhất khi debug: **property-source precedence chỉ chọn giá trị cho cùng key; binder-scope precedence chọn phạm vi cấu hình áp dụng cho binding**.

## 5. Cấu hình mặc định cho Spring Cloud Stream

Spring Cloud Stream có common binding properties và default properties. Ví dụ đặt retry chung cho consumer, sau đó ghi đè riêng một binding:

~~~yaml
spring:
  cloud:
    stream:
      default:
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1s
          back-off-max-interval: 10s
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-service
          consumer:
            max-attempts: 5
        auditOrder-in-0:
          destination: order-audit
          group: audit-service
~~~

Trong ví dụ:

- `max-attempts: 3` là mặc định cho các consumer binding chưa khai báo giá trị riêng.
- `processOrder-in-0` có `max-attempts: 5` nên dùng 5 lần thử (bao gồm lần đầu).
- `auditOrder-in-0` không ghi đè nên dùng mặc định 3.
- `destination` và `group` được khai báo theo binding vì chúng mô tả đích và nhóm tiêu thụ cụ thể.

Tên binding được tạo từ tên bean function. Ví dụ bean `processOrder` kiểu `Consumer<T>` có binding mặc định `processOrder-in-0`. Nếu đổi tên function hoặc dùng alias qua `spring.cloud.stream.function.bindings`, phải cập nhật đúng binding name trong cấu hình.

Không đặt `destination` vào `spring.cloud.stream.default` để mong mọi binding tự dùng chung một topic. Destination là lựa chọn theo luồng dữ liệu và cần được cấu hình theo binding.

## 6. Cấu hình Pulsar ở cấp Spring Boot

Các property `spring.pulsar.*` đến từ Spring for Apache Pulsar và Spring Boot auto-configuration. Chúng cung cấp giá trị nền cho ứng dụng:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    admin:
      service-url: http://pulsar-admin:8080
    producer:
      send-timeout: 30s
      batching-enabled: true
    consumer:
      subscription:
        type: Shared
~~~

Các property cụ thể phụ thuộc Spring Boot/Spring for Apache Pulsar version. Ví dụ trên minh họa nơi cấu hình client URL, admin URL, producer và consumer; hãy kiểm tra tên property trong appendix configuration properties của đúng version trước khi triển khai.

Các cấu hình này thường được dùng chung trong application context. Nếu ứng dụng có nhiều function và nhiều Pulsar binding, chúng không phải cách thích hợp để đặt hai bộ timeout hoặc subscription khác nhau cho từng binding. Khi cần khác biệt theo binding, dùng extended binding properties.

## 7. Cấu hình Pulsar ở cấp binder

Pulsar binder cho phép đặt một số property Spring for Apache Pulsar tại cấp binder:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 20s
            batching-enabled: true
          consumer:
            subscription:
              type: Shared
~~~

Các property này áp dụng chung qua Pulsar binder trong ứng dụng. Theo tài liệu binder, chúng có ưu tiên cao hơn property tương ứng ở `spring.pulsar.*` nhưng thấp hơn extended binding property của từng binding.

Ví dụ nếu `spring.pulsar.producer.send-timeout` là `30s` và binder-level `send-timeout` là `20s`, các producer binding không đặt timeout riêng sẽ nhận `20s`.

Đừng nhầm cấp binder này với cấu hình kết nối nhiều binder instance. `spring.cloud.stream.pulsar.binder.*` cấu hình Pulsar binder type; `spring.cloud.stream.binders.<configurationName>.*` khai báo binder configuration có tên và có thể chứa environment riêng.

## 8. Cấu hình Pulsar extended binding cho từng luồng

Khi hai output binding cần schema hoặc producer option khác nhau, đặt extended properties theo tên binding:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
              schema-type: JSON
              message-type: com.example.events.OrderCreated
          publishAudit-out-0:
            producer:
              send-timeout: 15s
              schema-type: AVRO
              message-type: com.example.events.AuditRecord
~~~

Ở đây:

- `publishOrder-out-0` có timeout 5 giây và schema JSON.
- `publishAudit-out-0` có timeout 15 giây và schema Avro.
- Các giá trị này chỉ áp dụng cho binding tương ứng.
- Binding khác không có cấu hình riêng sẽ dùng giá trị extended default hoặc binder/Boot-level fallback phù hợp.

Tên binding phải khớp chính xác với function bean và hướng message. `Supplier` có output binding; `Consumer` có input binding; `Function` thường có cả input và output binding. Không dùng tên topic thay cho binding name ở vị trí prefix cấu hình.

## 9. Kết hợp core binding property với Pulsar extended property

Một số tùy chọn thuộc Spring Cloud Stream core, một số khác thuộc Pulsar binder. Khi dùng native Pulsar schema, hai nhóm này thường được khai báo cùng nhau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://public/default/orders
          producer:
            use-native-encoding: true
        processOrder-in-0:
          destination: persistent://public/default/orders
          group: order-service
          consumer:
            use-native-decoding: true
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              schema-type: JSON
              message-type: com.example.events.OrderCreated
          processOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.example.events.OrderCreated
~~~

`use-native-encoding` và `use-native-decoding` là core Spring Cloud Stream binding properties. `schema-type` và `message-type` là Pulsar extended binding properties. Cả hai nhóm phải nhất quán: producer native encoding và consumer native decoding cần dùng schema/type tương thích.

Nếu không bật native encoding/decoding, Spring Cloud Stream mặc định dùng content type và message conversion của framework. Trong trường hợp đó, không cần tự thêm schema type chỉ vì đang dùng Pulsar; hãy chọn một mô hình serialization nhất quán và kiểm tra bytes thực tế trên topic.

## 10. Cấu hình extended default cho các Pulsar binding

Khi nhiều binding có cùng cấu hình Pulsar producer hoặc consumer, có thể dùng extended default của binder type:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        default:
          producer:
            send-timeout: 10s
          consumer:
            subscription:
              type: Shared
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
~~~

`spring.cloud.stream.pulsar.default.producer` và `...default.consumer` là cách đặt extended defaults theo binder type. Binding `publishOrder-out-0` có giá trị cụ thể nên ghi đè giá trị default tương ứng.

Chỉ dùng các property mà Pulsar extended configuration class thực sự hỗ trợ. Một key không tồn tại trong metadata của binder không tự trở thành hợp lệ chỉ vì đặt dưới prefix `default`. Kiểm tra configuration metadata hoặc reference của đúng phiên bản.

## 11. Chọn binder cho một binding

Ngoài việc chọn giá trị property, Spring Cloud Stream còn phải xác định binder nào tạo binding. Nếu classpath chỉ có một binder, nó thường được chọn tự động. Khi có nhiều binder, có thể đặt default hoặc chỉ định binder theo binding:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: pulsar
      bindings:
        publishOrder-out-0:
          binder: pulsar
          destination: orders
        audit-out-0:
          binder: rabbit
          destination: order-audit
~~~

`binder` là common binding property để chọn binder cho binding cụ thể. `default-binder` là fallback khi binding không chỉ định binder. Hai property này không phải là giá trị của Pulsar producer/consumer option; chúng quyết định binding dùng binder nào.

Nếu binding được gán binder RabbitMQ, các extended properties của Pulsar không được áp dụng cho binding đó. Phải dùng extended configuration đúng binder tương ứng.

## 12. Phân biệt binder type với binder configuration instance

Khi kết nối nhiều Pulsar cluster, có thể khai báo hai binder configuration instance cùng type:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        pulsarWest:
          type: pulsar
          environment:
            spring:
              pulsar:
                client:
                  service-url: pulsar://pulsar-west:6650
        pulsarEast:
          type: pulsar
          environment:
            spring:
              pulsar:
                client:
                  service-url: pulsar://pulsar-east:6650
      bindings:
        publishWest-out-0:
          binder: pulsarWest
          destination: orders
        publishEast-out-0:
          binder: pulsarEast
          destination: orders
~~~

`pulsarWest` và `pulsarEast` là configuration name; `type: pulsar` chọn binder implementation. Cả hai cùng dùng Pulsar binder nhưng trỏ đến cluster khác nhau.

Đây là cơ chế multi-binder của Spring Cloud Stream, khác với `spring.cloud.stream.pulsar.binder.*`. Khi cấu hình `environment` riêng, cần hiểu `inheritEnvironment` và context của binder: các thuộc tính trong binder environment có thể được tách khỏi application context theo cấu hình. Không giả định mọi biến hoặc bean của ứng dụng đều tự động có trong binder context khi đã tách môi trường.

## 13. Ví dụ đầy đủ: một ứng dụng có producer và consumer

Ứng dụng có hai function:

~~~java
package com.example;

import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String orderId, String status) {}

@Configuration
class OrderFunctions {

    @Bean
    Supplier<OrderCreated> publishOrder() {
        return () -> new OrderCreated("O-100", "CREATED");
    }

    @Bean
    Consumer<OrderCreated> processOrder() {
        return event -> System.out.println(
                "Processing order " + event.orderId());
    }
}
~~~

Ví dụ này chỉ minh họa binding names; supplier trả cùng một event mỗi lần poll nên không dùng trực tiếp cho production. Một nguồn thật phải tạo event mới, có event ID ổn định và xử lý việc phát lặp an toàn.

Cấu hình:

~~~yaml
spring:
  application:
    name: order-pulsar-app
  pulsar:
    client:
      service-url: pulsar://pulsar:6650
    producer:
      send-timeout: 30s
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      default:
        consumer:
          max-attempts: 3
      bindings:
        publishOrder-out-0:
          destination: persistent://public/default/orders
          producer:
            use-native-encoding: true
        processOrder-in-0:
          destination: persistent://public/default/orders
          group: order-service
          consumer:
            max-attempts: 5
            use-native-decoding: true
      pulsar:
        binder:
          producer:
            send-timeout: 20s
        default:
          producer:
            send-timeout: 10s
        bindings:
          publishOrder-out-0:
            producer:
              send-timeout: 5s
              schema-type: JSON
              message-type: com.example.OrderCreated
          processOrder-in-0:
            consumer:
              schema-type: JSON
              message-type: com.example.OrderCreated
~~~

Giải thích kết quả:

- Producer ở binding `publishOrder-out-0` dùng timeout 5 giây vì extended binding cụ thể thắng binder-level 20 giây, extended default 10 giây và Spring Boot 30 giây.
- Các Pulsar producer binding khác không có timeout riêng có thể dùng extended default 10 giây; nếu không có extended default thì dùng binder-level 20 giây, rồi mới đến Spring Boot 30 giây.
- Consumer `processOrder-in-0` dùng `max-attempts: 5` vì common binding cụ thể thắng common default 3.
- Native encoding/decoding được bật ở core binding level; schema/type được đặt ở Pulsar extended binding level.
- Cả hai binding có destination rõ ràng; consumer group được khai báo ở input binding.

Khi áp dụng, bảo đảm classpath có Pulsar binder dependency và các class message type đúng package. Nếu dùng framework conversion mặc định thay vì Pulsar native schema, bỏ các cấu hình native encoding/decoding và schema/message type tương ứng.

## 14. Cách Spring Boot ghi đè cùng một key

Giả sử file đóng gói có:

~~~yaml
spring:
  pulsar:
    producer:
      send-timeout: 30s
~~~

File bên ngoài JAR có:

~~~yaml
spring:
  pulsar:
    producer:
      send-timeout: 40s
~~~

Với cùng key, file bên ngoài có độ ưu tiên cao hơn file đóng gói trong cấu hình mặc định của Spring Boot. Nếu environment variable đặt giá trị tiếp theo, nó có thể ghi đè:

~~~bash
SPRING_PULSAR_PRODUCER_SENDTIMEOUT=50s
~~~

Nếu chạy:

~~~bash
java -jar order-app.jar --spring.pulsar.producer.send-timeout=60s
~~~

thì giá trị Spring Boot-level của key đó là 60 giây vì command-line arguments có độ ưu tiên cao hơn file cấu hình. Nhưng nếu binding-specific extended property vẫn là 5 giây, binding đó tiếp tục dùng 5 giây theo precedence của Pulsar binder.

Environment variable sử dụng quy tắc relaxed binding: chuyển dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và viết hoa. Khi key có cấu trúc phức tạp, kiểm tra lại tên environment variable được Spring Boot bind để tránh sai chính tả.

## 15. Profile và external configuration

Có thể dùng profile để đặt cấu hình môi trường:

~~~yaml
# application.yml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-dev:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 20s
~~~

~~~yaml
# application-prod.yml
spring:
  pulsar:
    client:
      service-url: pulsar-prod.internal:6650
  cloud:
    stream:
      pulsar:
        binder:
          producer:
            send-timeout: 30s
~~~

Khi profile `prod` hoạt động, file profile được nạp theo quy tắc config data và có thể ghi đè giá trị file cơ sở. Giá trị theo từng binding vẫn có thể ghi đè binder-level nếu được khai báo.

Nếu dùng `spring.config.location`, Spring Boot thay thế các vị trí tìm kiếm mặc định bằng những vị trí được chỉ định. Nếu chỉ muốn bổ sung file cấu hình ngoài mà vẫn giữ vị trí mặc định, dùng `spring.config.additional-location`. Một file import qua `spring.config.import` được xử lý như config data bổ sung và có thể ghi đè file khai báo import.

Không tạo quá nhiều file profile có cùng key nhưng không có quy ước rõ. Ghi lại nguồn cấu hình theo môi trường để khi điều tra có thể biết giá trị đến từ file trong image, file mount, environment variable hay tham số khởi chạy.

## 16. Giá trị mặc định không phải lúc nào cũng là một property có thể ghi đè

Một số giá trị là default do framework/binder tính ra khi property không được khai báo:

- Binding name mặc định được tạo từ function bean name và hướng input/output.
- Destination mặc định có thể lấy từ binding name nếu không chỉ định destination.
- Pulsar binder có thể dùng schema mapping mặc định khi không chỉ định schema type.
- Một số producer/consumer option lấy default từ Spring for Apache Pulsar hoặc Pulsar client.

Không phải mọi giá trị mặc định đều có thể đặt ở prefix `spring.cloud.stream.default`. Prefix này chỉ áp dụng cho những common binding properties được Spring Cloud Stream hỗ trợ. Với extended properties, dùng prefix binder-type default hoặc binding-specific prefix tương ứng. Với default của Pulsar client, tra Spring for Apache Pulsar configuration properties.

Ví dụ: `spring.cloud.stream.default.consumer.max-attempts` là common binding default; nó không tự đặt `schema-type` cho Pulsar. Ngược lại, `spring.cloud.stream.pulsar.default.consumer.schema-type` chỉ có ý nghĩa nếu Pulsar binder expose property đó ở extended consumer properties.

## 17. Những thuộc tính không nên đặt nhầm cấp

| Nhu cầu | Nơi đặt phù hợp | Lý do |
|---|---|---|
| Pulsar service URL chung | `spring.pulsar.client.service-url` | Cấu hình client cấp Spring Boot |
| Producer send timeout chung qua Pulsar binder | `spring.cloud.stream.pulsar.binder.producer.send-timeout` | Áp dụng chung cho producer bindings |
| Send timeout riêng cho một output | `spring.cloud.stream.pulsar.bindings.<name>.producer.send-timeout` | Chỉ binding đó dùng giá trị riêng |
| Retry mặc định cho consumer | `spring.cloud.stream.default.consumer.max-attempts` | Common binding default |
| Retry riêng cho consumer | `spring.cloud.stream.bindings.<name>.consumer.max-attempts` | Core binding property |
| Schema JSON riêng cho output Pulsar | `spring.cloud.stream.pulsar.bindings.<name>.producer.schema-type` | Pulsar extended property |
| Native encoding cho output | `spring.cloud.stream.bindings.<name>.producer.use-native-encoding` | Core Spring Cloud Stream property |
| Chọn binder cho một input | `spring.cloud.stream.bindings.<name>.binder` | Chọn implementation binder của binding |
| Cấu hình một Pulsar cluster có tên | `spring.cloud.stream.binders.<configurationName>` | Khai báo binder configuration instance |

Nếu một key không tồn tại trong property metadata của đúng module/version, kiểm tra xem nó thuộc prefix khác hay không. Không di chuyển property qua các prefix chỉ dựa trên việc tên phần cuối giống nhau.

## 18. Kiểm tra cấu hình nào thực sự có hiệu lực

Khi ứng dụng dùng giá trị khác mong đợi, hãy làm theo trình tự:

1. Ghi chính xác key cần kiểm tra, ví dụ `send-timeout` hay `max-attempts`.
2. Xác định key thuộc Spring Boot Pulsar, Pulsar binder, core binding hay Pulsar extended binding.
3. Liệt kê mọi nơi khai báo key đó: application YAML, profile YAML, file mount, environment, system property và command line.
4. Kiểm tra đúng tên binding, bao gồm hậu tố `-in-0`/`-out-0`.
5. Áp dụng precedence theo scope của binder cho cùng Pulsar option.
6. Sau đó kiểm tra Spring Boot PropertySource để biết giá trị của từng key được nạp từ nguồn nào.
7. Kiểm tra cấu hình đã được binder chuyển thành producer/consumer thực tế hay chưa bằng log và integration test.

Actuator `env` và `configprops` có thể giúp xác định property source và giá trị đã bind vào configuration object. Chỉ expose chúng trong môi trường quản trị, bảo vệ bằng authentication/authorization và kiểm tra sanitization vì cấu hình broker có thể chứa secret. Không gửi toàn bộ output chứa credential vào ticket hoặc log công khai.

Trong code, có thể đọc giá trị qua `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class PulsarConfigDiagnostic {

    PulsarConfigDiagnostic(Environment environment) {
        String bootSendTimeout = environment.getProperty(
                "spring.pulsar.producer.send-timeout");
        String binderSendTimeout = environment.getProperty(
                "spring.cloud.stream.pulsar.binder.producer.send-timeout");
        String bindingSendTimeout = environment.getProperty(
                "spring.cloud.stream.pulsar.bindings.publishOrder-out-0.producer.send-timeout");

        // Chỉ log giá trị không nhạy cảm trong môi trường thử nghiệm.
    }
}
~~~

`Environment` cho biết các giá trị theo key trong Spring Environment; nó không tự tính ra giá trị cuối cùng sau khi Pulsar binder merge các scope. Muốn xác nhận giá trị hiệu lực, phải kiểm tra configuration object/consumer-producer binding sau khi binder áp dụng cấu hình, hoặc quan sát hành vi thực tế bằng test.

## 19. Kiểm thử precedence thay vì chỉ kiểm tra file YAML

Một test cấu hình tốt nên chứng minh giá trị hiệu lực, không chỉ kiểm tra file có chứa chuỗi mong muốn.

Ví dụ ma trận:

| Test | Boot-level | Binder-level | Binding-level | Kết quả kỳ vọng |
|---|---:|---:|---:|---:|
| Chỉ có Boot | 30s | — | — | 30s |
| Có binder | 30s | 20s | — | 20s |
| Có binding | 30s | 20s | 5s | 5s |
| Binding khác | 30s | 20s | — | 20s |
| CLI đổi Boot key | 60s | 20s | 5s | 5s cho binding đã chỉ định |

Trong integration test:

- Dùng context riêng để tránh bean/config từ test trước làm thay đổi kết quả.
- Đặt các property bằng test property source hoặc dynamic property source và ghi rõ key.
- Kiểm tra configuration object đã bind.
- Với producer/consumer option quan trọng, tạo Pulsar test broker hoặc môi trường tích hợp và xác nhận behavior thực tế.
- Kiểm tra ít nhất một binding không có override để xác nhận fallback.
- Kiểm tra binding cụ thể không vô tình nhận cấu hình của binding khác.

Test Binder của Spring Cloud Stream hữu ích cho logic function và binding, nhưng không tự xác minh mọi tùy chọn native Pulsar producer/consumer. Với schema, partition count, subscription hoặc send timeout, cần integration test dùng Pulsar binder thật.

## 20. Pulsar topic partition count cũng có hai cấp

Pulsar binder hỗ trợ đặt partition count khi provision topic:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 8
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 16
          publishAudit-out-0:
            producer:
              partition-count: 4
~~~

Binder-level `partition-count: 8` là mặc định chung cho topic do ứng dụng tạo. Binding `publishOrder-out-0` yêu cầu 16 partition, còn `publishAudit-out-0` yêu cầu 4 partition.

Đây là ví dụ về việc chọn cấu hình theo nhu cầu từng luồng. Topic đã tồn tại có thể không được thay đổi partition count chỉ bằng cách đổi cấu hình ứng dụng; hãy kiểm tra trạng thái topic và quy trình quản trị Pulsar trước khi kỳ vọng provisioner sửa tài nguyên hiện hữu.

Pulsar binder provisioner có thể tạo topic cơ bản nếu topic chưa tồn tại. Topic partitioned cần cấu hình partition count và quyền quản trị phù hợp. Địa chỉ administration service cũng cần được cấu hình khi không dùng endpoint mặc định.

## 21. Lỗi thường gặp khi xử lý cấu hình

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đổi `spring.pulsar.producer.send-timeout` nhưng binding không đổi | Có binder-level hoặc extended binding-level override | Kiểm tra lần lượt ba scope Pulsar |
| Tham số command line không thay giá trị binding | CLI thay key Boot-level, còn binding-level là key khác và có precedence cao hơn trong binder | Override đúng binding key hoặc bỏ cấu hình binding nếu không cần |
| Tất cả function dùng cùng subscription/timeout | Chỉ đặt property ở Spring Boot hoặc binder scope toàn ứng dụng | Đặt extended binding property cho từng binding |
| Một binding không nhận retry mặc định | Có common binding property cụ thể ghi đè | Kiểm tra `spring.cloud.stream.default` và `bindings.<name>` |
| Schema native không hoạt động | Chỉ bật native encoding nhưng thiếu schema/message type hoặc consumer không khớp | Cấu hình cả producer và consumer ở extended binding |
| Property không có tác dụng | Dùng nhầm prefix hoặc tên binding | Kiểm tra property metadata và binding name |
| Pulsar cluster không đúng | Nhầm binder type với named binder instance | Kiểm tra `spring.cloud.stream.binders.<name>` và `binding.binder` |
| Giá trị môi trường khác YAML | Environment, system property hoặc command line ghi đè cùng key | Dùng `env`/`configprops` có bảo vệ để xem nguồn |
| Topic không có số partition mong muốn | Topic đã tồn tại hoặc property đặt sai cấp | Kiểm tra provisioner và partition count theo binding |

## 22. Checklist trước khi triển khai

- Đã phân biệt Spring Boot property, Pulsar binder property, common binding property và Pulsar extended binding property.
- Đã xác định chính xác binding name của từng Supplier/Function/Consumer.
- Đã đặt giá trị chung ở default/binder scope và chỉ override khi binding có yêu cầu riêng.
- Đã áp dụng đúng precedence Pulsar: extended binding → binder → Spring Boot.
- Đã kiểm tra riêng Spring Boot PropertySource precedence cho cùng một key.
- Không coi command-line argument là override tự động cho một key ở scope khác.
- Đã chọn đúng binder bằng `default-binder` hoặc `bindings.<name>.binder`.
- Đã phân biệt Pulsar binder type với binder configuration instance.
- Đã đặt native encoding/decoding cùng schema/message type tương thích.
- Đã kiểm tra topic provisioning, partition count và administration service URL.
- Đã kiểm tra environment/profile/secret được truyền từ nền tảng triển khai.
- Đã kiểm tra giá trị thực tế bằng configuration inspection có bảo vệ.
- Đã có integration test cho các binding quan trọng bằng Pulsar binder thật.

## Tổng kết

Để xác định cấu hình Pulsar nào có hiệu lực, trước hết hãy xác định **phạm vi của property**. Với cùng một Pulsar option, extended binding property có ưu tiên cao nhất, tiếp theo là binder property, rồi đến Spring Boot Pulsar property. Common Spring Cloud Stream properties lại có cơ chế default và per-binding riêng. Sau đó mới xét Spring Boot PropertySource precedence để biết file, environment variable, system property hay command-line argument cung cấp giá trị cho từng key.

Không gộp hai cơ chế này thành một thứ tự duy nhất. Một giá trị từ command line chỉ ghi đè cùng key trong Environment; nó không tự loại bỏ một key extended binding có scope cao hơn. Đặt cấu hình chung ở đúng cấp, chỉ tạo override theo binding khi cần, và xác nhận kết quả bằng integration test giúp tránh việc các function trong cùng ứng dụng vô tình dùng chung timeout, schema hoặc subscription không phù hợp.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Pulsar Binder: Using Pulsar Properties in the Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream 5.1 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream 5.1 — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Boot 4.2 — Externalized Configuration and PropertySource Ordering](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot 4.2 — Application Properties for Pulsar](https://docs.spring.io/spring-boot/4.2/appendix/application-properties/)
- [Spring for Apache Pulsar — Reference Documentation](https://docs.spring.io/spring-pulsar/reference/)
