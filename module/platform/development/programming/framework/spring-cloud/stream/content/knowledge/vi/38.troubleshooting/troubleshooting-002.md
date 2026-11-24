# Không tìm thấy binder hoặc không xác định được binder mặc định

Ứng dụng Spring Cloud Stream có thể khởi động thất bại ngay khi thiết lập input/output binding vì framework không tìm thấy binder được chỉ định hoặc không biết phải dùng binder nào khi có nhiều lựa chọn. Đây là lỗi cấu hình và discovery ở giai đoạn tạo binding; nó **khác** với tình huống binder đã được chọn nhưng không kết nối được Kafka, RabbitMQ hay Pulsar.

Bài này tập trung vào cách chẩn đoán theo thứ tự: kiểm tra dependency thật sự có trên runtime classpath, xác định binder implementation nào được discovery, so sánh tên binder với cấu hình, chọn default binder, xử lý named binder configuration và phân biệt lỗi chọn binder với lỗi broker/network. Ví dụ dùng mô hình Supplier/Function/Consumer của Spring Cloud Stream, áp dụng cho Kafka, RabbitMQ và Pulsar.

## 1. Binder và binding khác nhau ở đâu?

Trong Spring Cloud Stream, **binding** là điểm kết nối logic của function với hệ thống nhắn tin. **Binder** là implementation kết nối điểm đó tới broker cụ thể.

Một function:

~~~java
@Configuration
class OrderHandlers {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(
                event.orderId(),
                event.customerId(),
                event.total());
    }
}
~~~

Có hai tên binding mặc định:

- `validateOrder-in-0`: nhận dữ liệu đầu vào.
- `validateOrder-out-0`: xuất dữ liệu đầu ra.

Cấu hình sau mô tả destination của hai binding nhưng chưa ghi rõ binder:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator
        validateOrder-out-0:
          destination: orders.validated
~~~

Các destination như `orders.created` và `orders.validated` **không phải** binder name. Để kết nối được, Spring Cloud Stream còn phải biết dùng Kafka Binder, RabbitMQ Binder, Pulsar Binder hoặc một binder khác.

## 2. Hai nhóm lỗi dễ bị nhầm

| Nhóm lỗi | Ý nghĩa | Điểm điều tra đầu tiên |
|---|---|---|
| **Không tìm thấy binder** | Tên binder được tham chiếu không tồn tại, implementation chưa có trên classpath hoặc không được đăng ký đúng | Dependency, binder type, alias và metadata discovery |
| **Không xác định được default binder** | Có nhiều binder có thể dùng cho binding không chọn riêng, nhưng không có lựa chọn mặc định rõ ràng | `spring.cloud.stream.default-binder` và `bindings.*.binder` |
| Binder đã chọn, kết nối broker thất bại | Implementation có thật nhưng DNS, credential, TLS, broker/queue/topic không hoạt động | Endpoint, security, broker health và provisioning |
| Function hoặc binding không được tạo | Chưa chọn function hoặc tên binding không khớp | `spring.cloud.function.definition`, tên bean và binding aliases |

Không sửa lỗi của nhóm thứ nhất bằng cách thay port Kafka. Cũng không giải quyết lỗi authentication bằng cách thêm `default-binder`; trước hết cần xác định framework đã chọn được binder hay chưa.

## 3. Cây quyết định chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Ứng dụng lỗi khi tạo binding"] --> B{"Log báo không tìm thấy binder?"}
    B -->|Có| C{"Binder artifact có trong runtime?"}
    C -->|Không| D["Thêm dependency / sửa packaging"]
    C -->|Có| E{"Tên alias/type đúng?"}
    E -->|Không| F["Sửa binder reference và binders config"]
    E -->|Có| G["Kiểm tra discovery metadata, phiên bản"]
    B -->|Không| H{"Log báo không chọn được mặc định?"}
    H -->|Có| I["Đặt default-binder hoặc binder từng binding"]
    H -->|Không| J{"Đã tạo binder nhưng không kết nối broker?"}
    J -->|Có| K["Điều tra DNS/TLS/auth/ACL/provision"]
    J -->|Không| L["Kiểm tra function definition và binding names"]
~~~

Nguyên tắc là đọc **exception đầu tiên có ích trong startup log**, sau đó truy vết các `Caused by`. Một exception cuối cùng có thể chỉ là `BeanCreationException` hoặc lỗi khởi tạo context; nguyên nhân thực chất thường nằm ở một nested exception liên quan BinderFactory, binding lifecycle hoặc Kafka/Rabbit/Pulsar client.

## 4. Những dấu hiệu trong log

Thông điệp chính xác thay đổi theo Spring Cloud Stream release train và binder implementation, nhưng có thể gặp các dạng sau:

~~~text
A default binder has been requested, but there are multiple binders...
No binder found for the given name ...
Unknown binder configuration ...
Unable to create binder ...
Failed to bind consumer ...
BeanCreationException ...
~~~

Đây là **nhóm dấu hiệu minh họa**, không phải lời cam kết từng phiên bản in nguyên văn như trên. Dùng tên binder/binding và chuỗi nguyên nhân trong log thực tế để phân loại.

Một số câu hỏi cần trả lời trước khi sửa:

1. Function nào đang được Spring Cloud Function chọn?
2. Input/output binding nào đang được tạo?
3. Binding có khai báo thuộc tính `binder` không?
4. Ứng dụng có đặt `default-binder` không?
5. Có khai báo `spring.cloud.stream.binders` (named binder configurations) không?
6. Binder implementation nào đang nằm trong **runtime** classpath?
7. Lỗi xảy ra trước hay sau lúc client cố kết nối broker?

Không thay nhiều cấu hình cùng lúc. Sửa từng nguyên nhân và xác nhận log startup thay đổi đúng dự đoán.

## 5. Trường hợp A: thiếu binder dependency

Thư viện `spring-cloud-stream` cung cấp abstraction; bản thân nó không mặc nhiên bao gồm mọi binder cho mọi broker. Nếu ứng dụng chỉ phụ thuộc vào core stream library nhưng binding cần Kafka, phải có Kafka Binder implementation tương ứng.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
~~~

Với RabbitMQ:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
</dependency>
~~~

Với Pulsar, dùng binder artifact được hỗ trợ trong Spring Cloud release train hiện hành, thường là `spring-cloud-stream-binder-pulsar`, và xác minh dependency compatibility với Spring Boot/Spring Cloud BOM của dự án.

### 5.1. Kiểm tra dependency đúng scope

Một lỗi phổ biến là dependency có trong test scope nhưng thiếu trong runtime, hoặc build profile loại artifact khỏi application package. Ví dụ:

- `testImplementation` chỉ đưa thư viện vào test runtime, không dùng cho application production.
- `<scope>test</scope>` trong Maven không phù hợp với production binder.
- Dependency được khai báo trong submodule nhưng application module chạy thực tế không phụ thuộc vào nó.
- Một Maven profile/Gradle variant khiến dependency chỉ xuất hiện trong IDE nhưng không có trong JAR hoặc image triển khai.

Các lệnh gợi ý **chạy tại project thực tế** khi chẩn đoán (không phải một bước bắt buộc cho bài học này):

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud

./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-stream-binder-kafka \
  --configuration runtimeClasspath
~~~

Kiểm tra dependency trong packaged artifact/container đang chạy, không chỉ trong IDE. Với executable Spring Boot JAR, có thể kiểm tra những thư viện nằm dưới `BOOT-INF/lib`; với OCI image, kiểm tra đúng image digest được triển khai.

### 5.2. Sai phiên bản hoặc dependency conflict

Một binder được build cho release khác có thể không tạo được bean hoặc không tương thích SPI dù JAR tồn tại. Dấu hiệu điển hình: `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi bean creation trước khi binding hoạt động.

Cách xử lý:

- Dùng BOM Spring Cloud phù hợp Spring Boot version.
- Tránh pin riêng version của Spring Cloud Stream và binder nếu BOM quản lý.
- Kiểm tra dependency tree để tìm nhiều phiên bản Spring Integration, Spring Cloud Stream hoặc broker client chồng chéo.
- Khôi phục bộ phiên bản tương thích rồi khởi động lại với cấu hình tối giản.

Không chữa `NoSuchMethodError` bằng cách đổi default binder; đó là vấn đề tương thích classpath.

## 6. Trường hợp B: có nhiều binder trên classpath

Ứng dụng có Kafka và RabbitMQ Binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
</dependency>
~~~

Nếu một binding không có `binder` và framework nhìn thấy nhiều default candidate, việc lựa chọn có thể mơ hồ. Đừng dựa vào thứ tự dependency hoặc tên broker xuất hiện đầu tiên trong log để suy ra binder mặc định.

Cách 1: đặt binder mặc định ở cấp ứng dụng:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator
        validateOrder-out-0:
          destination: orders.validated
~~~

Tên `kafka` là binder type/candidate mà Kafka Binder đăng ký trong cấu hình auto-discovery phổ biến. Với Rabbit Binder dùng `rabbit`; tên thực tế của các binder khác cần được xác minh từ metadata/discovery theo phiên bản.

Thuộc tính tài liệu thường thể hiện dưới dạng `spring.cloud.stream.defaultBinder`; Spring Boot relaxed binding cho phép dùng dạng YAML `default-binder`.

Cách 2: đặt binder riêng cho mỗi binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          binder: kafka
        validateOrder-out-0:
          destination: orders.validated
          binder: rabbit
~~~

Cấu hình này cố ý nhận từ Kafka và xuất sang RabbitMQ. Cần kiểm tra serialization, content type và semantics retry/ack khi kết nối hai broker. Chọn binder tường minh giúp giảm phụ thuộc vào default và đặc biệt hữu ích khi input/output ở các cluster khác nhau.

### 6.1. Chọn default hay chỉ định từng binding?

| Tình huống | Cách chọn |
|---|---|
| Hầu hết binding dùng một broker | Đặt `default-binder`, chỉ ghi `binder` ở binding ngoại lệ |
| Mỗi binding có broker/cluster khác nhau | Ghi `binder` tường minh trên từng binding |
| Có nhiều cấu hình cùng một binder type | Dùng named binder alias và tham chiếu alias |
| Binder mới chỉ dành cho một vài binding | Có thể đặt `default-candidate: false` cho named binder đó |
| Cần kết nối rất rõ ràng trong môi trường nhạy cảm | Khai báo `binder` tường minh và kiểm thử routing trong staging |

Một default rõ ràng giúp tránh lỗi startup, nhưng cũng có thể che một binding mới bị thiếu cấu hình. Với hệ thống nhiều broker, ưu tiên khai báo tường minh để hạn chế kết nối nhầm cluster.

## 7. Trường hợp C: gọi sai binder name hoặc alias

Giả sử có:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-main:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-main.internal:9092
~~~

`kafka-main` là **tên cấu hình binder**; `kafka` là **type của implementation**. Nếu binding viết:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          binder: kafkaMain
~~~

thì `kafkaMain` không khớp alias `kafka-main` đã khai báo. Đừng giả định tên alias được tự động suy ra từ tên broker, hay có thể tùy ý đổi dấu gạch nối/case trong một giá trị tham chiếu dạng chuỗi.

Cấu hình sửa:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-workers
          binder: kafka-main
~~~

Khi dùng named binders, hãy so sánh trực tiếp giá trị `bindings.<name>.binder` với key trong `spring.cloud.stream.binders`. Phân biệt **property key relaxed binding** với **giá trị alias**, vốn phải khớp tên cấu hình đã được tạo.

## 8. Trường hợp D: khai báo named binder nhưng quên binder khác

Khi khai báo tường minh `spring.cloud.stream.binders`, ứng dụng sử dụng các cấu hình binder được định nghĩa đó thay cho việc dựa hoàn toàn vào cơ chế cấu hình binder mặc định tự động. Vì vậy, không nên khai báo một binder phụ rồi giả định tất cả implementation khác trên classpath vẫn được chọn như lúc chưa có named binder configuration.

Ví dụ **sai về ý định**:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbit-audit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit-audit.internal
      bindings:
        mainOrders-in-0:
          destination: orders.created
          binder: kafka-main
~~~

Ở đây `kafka-main` chưa được khai báo trong `binders`, dù Kafka Binder JAR có thể có trên classpath. Sửa bằng cách khai báo cả hai:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka-main
      binders:
        kafka-main:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-main.internal:9092
        rabbit-audit:
          type: rabbit
          default-candidate: false
          environment:
            spring:
              rabbitmq:
                host: rabbit-audit.internal
                port: 5672
      bindings:
        mainOrders-in-0:
          destination: orders.created
          group: order-workers
          binder: kafka-main
        audit-out-0:
          destination: orders.audit
          binder: rabbit-audit
~~~

Ví dụ đã tách binder default và binder phụ rõ ràng. Với Spring Cloud Stream, mỗi named binder có environment/context riêng; cấu hình broker nằm đúng bên trong `environment` của binder tương ứng.

### 8.1. Type và alias không hoán đổi tùy ý

| Thuộc tính | Ví dụ | Giải thích |
|---|---|---|
| `spring.cloud.stream.binders.kafka-main` | kafka-main | Tên cấu hình do ứng dụng đặt |
| `spring.cloud.stream.binders.kafka-main.type` | kafka | Binder implementation cần nạp |
| `spring.cloud.stream.default-binder` | kafka-main | Binder mặc định, tham chiếu alias |
| `spring.cloud.stream.bindings.mainOrders-in-0.binder` | kafka-main | Binder mà binding sử dụng |
| `spring.cloud.stream.bindings.mainOrders-in-0.destination` | orders.created | Topic/destination trên broker |

Khi đã chọn cấu hình tường minh, nên dùng alias nhất quán ở mọi nơi. Giá trị `type` phải tương ứng một implementation có mặt trên classpath và được đăng ký.

## 9. Trường hợp E: nhiều cluster Kafka cùng một binder type

Một ứng dụng cần nhận từ Kafka nội bộ và xuất dữ liệu sang Kafka đối tác. Chỉ có Kafka Binder implementation là đủ, nhưng cần hai named binder configurations:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka-internal
      binders:
        kafka-internal:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-internal.internal:9092
        kafka-partner:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-partner.internal:9092
      bindings:
        forwardPartner-in-0:
          destination: orders.created
          group: partner-forwarder
          binder: kafka-internal
        forwardPartner-out-0:
          destination: partner.orders
          binder: kafka-partner
~~~

Nếu đặt `default-binder: kafka` nhưng trong named binders chỉ có `kafka-internal` và `kafka-partner`, việc lookup có thể không chọn được tên `kafka` mong muốn. Sử dụng **alias đã khai báo**.

Tách endpoint chưa đủ để bảo đảm tách quyền. Nếu dùng SASL/TLS hoặc client properties khác nhau, cần truyền credential, truststore và các config tương ứng vào đúng binder environment. Cảnh báo nếu application-level global properties vô tình chảy sang binder phụ.

## 10. Trường hợp F: `default-candidate` và `inherit-environment`

Đây là hai thuộc tính dễ gây nhầm với `default-binder`:

| Thuộc tính | Tác dụng | Lỗi thường gặp |
|---|---|---|
| `default-binder` | Chỉ rõ binder dùng cho binding chưa chọn riêng | Trỏ tới tên không tồn tại |
| `default-candidate` | Quy định một named binder có tham gia lựa chọn mặc định không | Đánh dấu nhầm binder chính thành false |
| `inherit-environment` | Điều khiển việc binder environment kế thừa thuộc tính môi trường cha | Tắt kế thừa nhưng không cấu hình đủ endpoint/auth |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka-primary
      binders:
        kafka-primary:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-primary.internal:9092
        kafka-archive:
          type: kafka
          default-candidate: false
          inherit-environment: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-archive.internal:9093
~~~

`default-candidate: false` không có nghĩa binder bị vô hiệu hóa. Binder vẫn có thể được binding chọn tường minh qua `binder: kafka-archive`. Nó chỉ không tham gia lựa chọn default candidate theo cơ chế tương ứng.

`inherit-environment: false` có thể giúp cô lập kết nối, nhưng khi thiếu thông số SSL/SASL hoặc credential trong context con, binder có thể được tạo thành công rồi kết nối broker thất bại. Khi đó **không phải lỗi binder discovery**; phân loại đúng sang lỗi kết nối/authentication.

## 11. Trường hợp G: tên function và binding không khớp

Không phải lỗi startup nào xuất hiện gần binder cũng do binder. Nếu function bean không được chọn hoặc binding properties nhắm vào sai tên, ứng dụng có thể không tạo channel như mong đợi.

Ví dụ function bean có tên `transformOrder`:

~~~java
@Bean
Function<OrderCreated, OrderValidated> transformOrder() {
    return this::validate;
}
~~~

Binding mặc định là `transformOrder-in-0` và `transformOrder-out-0`. Cấu hình dùng nhầm `validateOrder-in-0` sẽ không tự gắn vào input của function kia:

~~~yaml
spring:
  cloud:
    function:
      definition: transformOrder
    stream:
      bindings:
        transformOrder-in-0:
          destination: orders.created
          group: order-validator
          binder: kafka
        transformOrder-out-0:
          destination: orders.validated
          binder: kafka
~~~

Khi ứng dụng có nhiều function beans, đặt `spring.cloud.function.definition` để chọn đúng function/composition cần bind. Với explicit binding alias, kiểm tra `spring.cloud.stream.function.bindings` và dùng alias thực tế trong cấu hình.

Không suy luận “không có dữ liệu” đồng nghĩa “không tìm thấy binder”. Nếu ứng dụng khởi động bình thường, xem binding lifecycle, destination, group và producer/consumer activity.

## 12. Trường hợp H: tên custom binder type không được discovery

Custom binder cần metadata để Spring Cloud Stream phát hiện. Với cách tích hợp Binder SPI thông dụng, module có file:

~~~text
src/main/resources/META-INF/spring.binders
~~~

Ví dụ nội dung:

~~~properties
acme: com.example.messaging.AcmeBinderConfiguration
~~~

Nếu binder type `acme` được khai báo trong `binders.*.type` nhưng JAR custom binder không có runtime classpath hoặc resource discovery bị đóng gói sai, Spring không thể tạo binder tương ứng.

Kiểm tra:
- JAR custom binder có được đưa vào runtime không?
- Resource `META-INF/spring.binders` có nằm đúng đường dẫn trong JAR không?
- Tên type trong resource có khớp `type: acme` không?
- Configuration class có tồn tại và load được không?
- Shading/assembly có vô tình ghi đè resource metadata khi gộp nhiều JAR không?
- Binder bean có tương thích Spring Cloud Stream SPI của release đang chạy không?

Không tự tạo file `spring.binders` mới trong ứng dụng để chữa tạm nếu đội đã cung cấp binder artifact. Hãy sửa packaging hoặc module binder gốc, rồi kiểm thử discovery trên cùng runtime mà production sử dụng.

## 13. Trường hợp I: Test Binder chen vào lựa chọn production binder

Spring Cloud Stream có `spring-cloud-stream-test-binder` để kiểm thử function/binding trong JVM mà không cần broker. Dependency này thường phải nằm trong test scope. Nếu test binder bị đóng gói vào application runtime ngoài ý muốn hoặc cấu hình test được import vào production context, quá trình chọn binder có thể khác dự đoán.

Trong kiểm thử:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
@SpringBootTest
@Import(TestChannelBinderConfiguration.class)
class OrderFunctionTest {
    // Dùng InputDestination và OutputDestination trong test.
}
~~~

Ngược lại, production cần Kafka/RabbitMQ/Pulsar Binder thật tương ứng. Hãy kiểm tra build scopes và active profiles, tránh import test-specific configuration vào main application.

Test Binder trả lời câu hỏi business function có xử lý message qua abstraction không. Nó không xác minh kết nối, ACL, partition, retry, DLQ hay authentication của broker thật.

## 14. Trường hợp J: binder có rồi nhưng lỗi broker

Giả sử log đã cho thấy Kafka Binder được tạo và bắt đầu tạo consumer. Sau đó xuất hiện lỗi tương tự:

~~~text
UnknownHostException
TimeoutException
AuthenticationException
SSLHandshakeException
TopicAuthorizationException
~~~

Đây không còn là lỗi “không tìm thấy binder” hoặc “không có default”. Cần chẩn đoán theo lớp:

| Dấu hiệu | Giải thích có thể | Kiểm tra |
|---|---|---|
| `UnknownHostException` | DNS broker/advertised host sai | Resolve hostname từ chính pod/container |
| Kết nối timeout | Port, firewall, network policy, broker không sẵn sàng | Endpoint và route |
| TLS handshake lỗi | CA/truststore, scheme, hostname/certificate mismatch | TLS listener và certificate |
| Authentication failed | SASL/OAuth/token/username/password sai | Secret và auth mechanism |
| Authorization failed | Principal thiếu read/write/describe hoặc group permission | ACL/topic/group policy |
| Topic hoặc queue không tồn tại | Provision chưa chạy hoặc tên destination sai | Admin API/CLI, quyền provision |
| Consumer group không có dữ liệu | Offset/position hoặc group semantics không đúng | Consumer group, partition assignment |

Với RabbitMQ, phân biệt exchange/queue, virtual host và permission configure/write/read. Với Pulsar, phân biệt service URL dùng binary protocol và administration URL dùng HTTP(S), tenant/namespace, subscription permissions và broker advertised listener.

Đừng đổi binder default chỉ để tránh một exception của broker: việc đó có thể vô tình chuyển binding sang một hệ messaging khác thay vì sửa kết nối.

## 15. Bật logging chẩn đoán có kiểm soát

Trong môi trường thử nghiệm, có thể bật debug logging cho vùng Spring Cloud Stream và Spring Cloud Function để xem quyết định binding:

~~~yaml
logging:
  level:
    org.springframework.cloud.stream: DEBUG
    org.springframework.cloud.function: DEBUG
    org.springframework.integration: INFO
~~~

Có thể dùng tham số `--debug` của Spring Boot khi cần condition evaluation report. Tuy nhiên, log debug có thể dài và chứa tên topic, địa chỉ hoặc chi tiết cấu hình. Không bật lâu dài trên production nếu chưa đánh giá dung lượng log và dữ liệu nhạy cảm.

Cách đọc log nên theo trình tự:

1. Xem function definition và tên binding thực sự.
2. Xác định framework đã tìm thấy những binder configurations nào.
3. Xem binding chọn alias nào hoặc default binder nào.
4. Xem binder implementation có được instantiate thành công không.
5. Sau đó mới xem bootstrap servers, queue/topic provisioning, TLS và consumer startup.

Không chỉ grep mỗi cụm “binder not found”; một số thông tin quan trọng xuất hiện trong các dòng ngay trước nested exception.

## 16. Kiểm tra Actuator và trạng thái binding

Nếu ứng dụng có Spring Boot Actuator và phiên bản Spring Cloud Stream hỗ trợ endpoint quản lý binding, có thể dùng actuator bindings endpoint để xem và điều khiển trạng thái binding đang chạy. Cấu hình exposure chỉ trong môi trường quản trị được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Với base path mặc định, endpoint có thể ở `/actuator/bindings`. Cần kiểm tra Spring Cloud Stream version và Actuator security; không xem endpoint này là bắt buộc phải có trên mọi release hay là công cụ chữa lỗi context không khởi động được.

Nếu application context đã thất bại trước khi server mở cổng, Actuator có thể chưa sẵn sàng. Khi đó startup log và dependency inspection vẫn là công cụ chính.

## 17. Checklist năm phút khi gặp lỗi

Một trình tự ngắn trước khi thay đổi nhiều property:

1. **Đọc nested cause:** là missing binder, ambiguous default hay broker connection?
2. **Xác nhận binding:** function name, `definition` và binding suffix `-in-0`/`-out-0`.
3. **Kiểm tra classpath runtime:** binder Kafka/Rabbit/Pulsar hoặc custom module có thật không?
4. **Đọc `spring.cloud.stream.binders`:** nếu đã khai báo named binders, có đủ alias/type không?
5. **Đọc `default-binder`:** tên có khớp candidate hoặc alias không?
6. **Đọc từng `bindings.*.binder`:** có typo hoặc trỏ nhầm type/alias không?
7. **Kiểm tra `default-candidate`:** có vô tình loại binder chính khỏi mặc định không?
8. **Kiểm tra `inherit-environment`:** context con có đủ brokers/host/auth không?
9. **Chạy lại với logging phù hợp:** xem binder được chọn và lúc nào bắt đầu lỗi broker.
10. **Xác minh trên runtime thực tế:** IDE, test và container có thể có dependency/profile khác nhau.

## 18. Ma trận nguyên nhân và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Giải pháp |
|---|---|---|
| Không tìm thấy `kafka` | Chưa thêm Kafka Binder artifact vào runtime | Thêm dependency, kiểm tra BOM và packaging |
| Không tìm thấy alias `kafka-main` | Binding tham chiếu tên không khai báo | Khai báo named binder hoặc sửa `binder` |
| Có Kafka và Rabbit nhưng không có default | Nhiều binder candidates | Đặt `default-binder` hoặc ghi binder cho mọi binding |
| `default-binder` trỏ sai | Dùng tên destination hoặc typo | Dùng binder type/alias đúng |
| Có `binders` nhưng chỉ khai báo binder phụ | Mất cấu hình binder chính theo kỳ vọng | Khai báo mọi named binder cần thiết |
| Named binder có `type` sai | Implementation không được đăng ký | Sửa type theo discovery metadata |
| Custom binder không được nạp | Thiếu JAR/resource `spring.binders` | Sửa packaging và metadata |
| Bindings dùng sai function name | `definition` khác tên bean | Sửa binding name hoặc function alias |
| Binder tạo được nhưng không đọc được broker | DNS/TLS/auth/ACL | Chuyển sang quy trình kết nối broker |
| Chỉ thất bại khi deploy container | Runtime classpath/profile hoặc DNS khác IDE | So sánh packaged image và effective properties |
| Chỉ lỗi trong test | Test Binder chưa import hoặc binder selection nhầm | Dùng đúng test scope và test config |
| Hai Kafka cluster bị nối nhầm | Binding thiếu alias hoặc inherit config | Dùng named binders, chỉ định rõ binding và environment |
| Lỗi `NoSuchMethodError` | Dependency version conflict | Đồng bộ Spring Boot/Cloud/binder BOM |
| Kafka Binder và Kafka Streams Binder bị nhầm | Dùng type/binder không phù hợp model Function vs KStream | Dùng binder đúng với signature và kiểm tra config |

## 19. Tình huống 1: thêm RabbitMQ, Kafka đột ngột lỗi

**Bối cảnh:** ứng dụng trước đây chỉ có Kafka Binder. Sau khi thêm RabbitMQ Binder để gửi thông báo, một binding Kafka không còn được chọn tự động.

**Nguyên nhân:** ứng dụng hiện có nhiều binder candidate; các binding cũ dựa vào việc chỉ có một lựa chọn.

**Cách sửa:**

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        processPayment-in-0:
          destination: payments.created
          group: payment-workers
        notify-out-0:
          destination: payment.notifications
          binder: rabbit
~~~

Các binding không ghi binder tiếp tục dùng Kafka; binding thông báo dùng RabbitMQ. Kiểm thử end-to-end vì một Function kết nối input Kafka và output RabbitMQ không tự có transaction exactly-once xuyên hai broker.

## 20. Tình huống 2: Kafka cluster thứ hai không nhận dữ liệu

**Bối cảnh:** ứng dụng khai báo `kafka-internal` và `kafka-external`, nhưng một binding không có `binder` và luôn kết nối vào internal cluster.

**Nguyên nhân:** `default-binder: kafka-internal` chỉ áp dụng mặc định; cấu hình `destination` không tự động chọn cluster theo tên.

**Cách sửa:**

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        ingestExternal-in-0:
          destination: events.external
          group: external-ingestor
          binder: kafka-external
~~~

Kiểm tra `kafka-external` có tồn tại dưới `spring.cloud.stream.binders` và environment chứa brokers/auth đúng. Không đổi default binder toàn ứng dụng nếu chỉ một binding cần cluster phụ.

## 21. Tình huống 3: chỉ production lỗi, test thành công

**Bối cảnh:** unit/test context import Test Binder. Application production được build thành image nhưng không chứa Kafka Binder.

**Dấu hiệu:** Test dùng InputDestination/OutputDestination vẫn pass; production startup không tạo được binder thật.

**Hướng xử lý:** kiểm tra dependency test vs runtime, build profile, packaged JAR và container image. Thêm Kafka Binder vào runtime dependency. Chạy integration test trên broker thật và kiểm tra property kết nối để tránh có thêm lỗi sau khi binder được discovery.

Không dùng kết quả Test Binder để kết luận broker configuration production hợp lệ.

## 22. Tình huống 4: custom binder hoạt động trên IDE nhưng lỗi trong fat JAR

**Bối cảnh:** binder type `acme` được đăng ký qua `META-INF/spring.binders`. Chạy trên IDE thành công; đóng gói thành shaded JAR thì mất binder.

**Khả năng cao:** resource metadata bị loại bỏ hoặc ghi đè khi lắp ghép artifact. Không thể chỉ kết luận từ tên class.

**Cách sửa:** kiểm tra packaged resource và dependency của runtime. Sửa cách merge resource khi dùng shading/assembly, đồng bộ framework version rồi smoke test chính artifact sẽ deploy. Với Spring Boot repackaged JAR có nested dependencies, kiểm tra resource trong dependency tương ứng chứ không suy đoán chỉ từ danh sách root entries.

## 23. Ngăn lỗi bằng cấu hình và kiểm thử

### 23.1. Quy ước cấu hình

- Dùng alias dễ đọc như `kafka-orders`, `kafka-analytics`, `rabbit-notify`.
- Chỉ định binder tường minh khi nhiều cluster hoặc broker.
- Dùng `default-candidate: false` cho binder phụ không được chọn tự động.
- Quản lý named binders cùng destination và credential theo environment.
- Không thay đổi tên alias tùy tiện vì bindings đang tham chiếu trực tiếp.
- Review dependency tree khi thêm hoặc thay một binder.
- Giữ binder versions trong BOM tương thích với Spring Boot.

### 23.2. Kiểm thử matrix

| Kịch bản | Kỳ vọng |
|---|---|
| Chỉ một binder implementation | Binding không chọn riêng được gắn đúng binder |
| Thêm binder thứ hai, không cấu hình lựa chọn | Test thể hiện hành vi mơ hồ cần xử lý rõ ràng |
| Đặt `default-binder` hợp lệ | Binding không chọn riêng dùng default |
| Ghi `binder` trên output ngoại lệ | Output đi tới broker được chỉ định |
| Alias sai | Context báo lỗi tham chiếu binder rõ ràng |
| Type binder sai | Không instantiate nhầm binder; lỗi được ghi nhận |
| Named binder cùng type, khác brokers | Mỗi binding đi đúng cluster |
| `inherit-environment: false` | Context con có đủ endpoint và security |
| Dependency chỉ có trong test scope | Runtime test phát hiện thiếu binder thật |
| Broker bị từ chối kết nối | Phân loại connection failure, không chữa sai default |
| Custom binder đóng gói thành JAR | Metadata/discovery và lifecycle vẫn hoạt động |

Dùng Test Binder cho logic Function/Consumer, nhưng dùng broker thật hoặc Testcontainers cho bài kiểm tra selection, client connectivity, partition/group, acknowledgement, retry, DLQ và security. Tách hai loại test giúp lỗi được phát hiện đúng tầng.

## 24. Những việc không nên làm khi khắc phục

- Không thêm tất cả binder dependency với hy vọng lỗi missing biến mất; điều đó có thể tạo thêm ambiguity.
- Không đặt `default-binder` theo tên topic, queue hoặc function.
- Không gỡ dependency chỉ để application khởi động nếu tính năng vẫn cần binder đó.
- Không dùng credential production trong test để “thử xem có kết nối”.
- Không trộn `spring.cloud.stream.binders` alias với `spring.cloud.stream.bindings` name.
- Không đổi cả binder selection, destination và broker endpoint trong cùng một lần khắc phục.
- Không xem `ClassNotFoundException` như vấn đề broker outage.
- Không xem `AuthenticationException` như vấn đề thiếu binder.
- Không để Test Binder được import vào production application context.
- Không tự động tạo tài nguyên production ngoài quy trình provisioning để che lỗi cấu hình.

## 25. Checklist trước khi release

- [ ] `spring.cloud.function.definition` trỏ đúng function cần bind.
- [ ] Tên input/output binding khớp function bean hoặc alias đã khai báo.
- [ ] Binder dependency cho từng middleware có trong runtime artifact.
- [ ] Các binder types tương thích Spring Boot/Spring Cloud BOM.
- [ ] Nếu có nhiều candidate, default binder đã được chọn rõ hoặc các binding được chọn tường minh.
- [ ] `spring.cloud.stream.binders` khai báo đầy đủ những named binder đang tham chiếu.
- [ ] `spring.cloud.stream.default-binder` và `bindings.*.binder` khớp type/alias thực tế.
- [ ] `default-candidate` và `inherit-environment` được đặt theo chủ đích.
- [ ] Mỗi binder environment có broker endpoint, TLS và credential cần thiết.
- [ ] Custom binder có metadata `META-INF/spring.binders` và chạy được trong packaged artifact.
- [ ] Dependency test binder không rò vào production.
- [ ] Log startup xác nhận binder binding đúng broker/cluster.
- [ ] Integration test kiểm tra publish/consume thực tế, schema và consumer group.
- [ ] Có runbook phân biệt lỗi binder discovery với lỗi kết nối hoặc provisioning broker.

**Kết luận:** Khi Spring Cloud Stream báo không tìm thấy binder, trước hết xác minh implementation đã có trên runtime classpath và tên binder được tham chiếu đúng. Khi có nhiều binder, chọn `spring.cloud.stream.default-binder` hoặc chỉ định `binder` trên từng binding; nếu dùng named binder, phải nhất quán giữa alias, type và environment. Chỉ sau khi chứng minh binder đã được chọn và instantiate, mới chuyển sang kiểm tra DNS, authentication, TLS, ACL hoặc topic/queue provisioning. Chẩn đoán theo từng tầng vừa tránh sửa nhầm, vừa giảm nguy cơ kết nối nhầm broker trong môi trường production.

## Tài liệu tham khảo

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/testing.html)

