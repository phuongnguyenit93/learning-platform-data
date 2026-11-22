# logContainerConfig

Trong Spring Kafka, listener container quản lý vòng đời consumer, gọi poll, phân phối record đến listener và phối hợp acknowledgement với consumer group. Khi ứng dụng khởi động, container được tạo từ cấu hình Spring Boot, listener container factory và Kafka consumer factory. Nếu các giá trị đến từ nhiều nguồn, việc xác định container thực tế đang dùng cấu hình nào có thể mất thời gian.

`logContainerConfig` là tùy chọn giúp listener container ghi một thông điệp ở mức INFO tóm tắt các thuộc tính cấu hình của container. Khi bật, mỗi listener container ghi thông tin này trong quá trình khởi tạo. Đây là công cụ chẩn đoán hữu ích khi cần xác nhận cấu hình đang được áp dụng, nhất là ứng dụng có nhiều `@KafkaListener`, nhiều container factory hoặc nhiều môi trường triển khai.

Tùy chọn này không thay đổi cách consumer đọc record, commit offset hay tham gia consumer group. Nó chỉ bổ sung thông tin cấu hình vào log để đội vận hành dễ kiểm tra và đối chiếu.

## 1. logContainerConfig là gì?

`logContainerConfig` là thuộc tính của `ContainerProperties` trong Spring Kafka. Khi giá trị là `true` và log level `INFO` được bật cho logger liên quan, listener container ghi một thông điệp tóm tắt cấu hình của nó.

Các đặc điểm chính:

- Có từ Spring Kafka 2.1.1.
- Giá trị mặc định của `ContainerProperties` là `false`.
- Log được ghi ở mức `INFO`.
- Mỗi listener container ghi thông tin cấu hình khi khởi tạo.
- Nội dung là bản tóm tắt thuộc tính container, phục vụ chẩn đoán cấu hình.

`logContainerConfig` không phải Kafka broker setting và cũng không phải một consumer property được gửi đến broker. Nó là thuộc tính của Spring Kafka container. Vì vậy, không đặt nó trong `spring.kafka.consumer.properties` hoặc truyền nó như một Kafka client property.

~~~text
Spring Boot configuration
          |
          v
Listener container factory
          |
          v
ContainerProperties
          |
          +---- logContainerConfig = true
          |
          v
Listener container starts
          |
          v
INFO log: container configuration summary
~~~

## 2. Bật qua Spring Boot application.yml

Với listener container factory mặc định do Spring Boot auto-configure, cách đơn giản nhất là đặt property:

~~~yaml
spring:
  kafka:
    listener:
      log-container-config: true
~~~

Property có dạng kebab-case trong YAML là `log-container-config`; Spring Boot bind nó vào thuộc tính `logContainerConfig` của cấu hình listener.

Nếu dùng `application.properties`, cấu hình tương đương là:

~~~properties
spring.kafka.listener.log-container-config=true
~~~

Khi ứng dụng khởi động và container được tạo, Spring Kafka sẽ ghi thông điệp cấu hình ở mức `INFO`, miễn là logger đang cho phép mức này.

### 2.1. Bật theo profile

Có thể bật log cấu hình trong môi trường phát triển hoặc staging mà không cần bật mặc định ở mọi môi trường:

~~~yaml
# application-staging.yml
spring:
  kafka:
    listener:
      log-container-config: true
~~~

Trong production, quyết định bật hay tắt nên dựa trên nhu cầu chẩn đoán, lượng container và chính sách log. Nếu một ứng dụng có nhiều listener concurrency cao, log cấu hình của từng container con có thể làm tăng số dòng startup log. Hãy kiểm tra lượng log thực tế trước khi bật rộng rãi.

### 2.2. Kiểm tra property có được bind

Sau khi triển khai, kiểm tra:

1. Đúng profile Spring đang active.
2. Đúng file cấu hình được nạp trong môi trường chạy.
3. Property không bị ghi đè bởi biến môi trường hoặc command-line argument.
4. Ứng dụng đang sử dụng listener container factory mặc định hay một factory tùy chỉnh.
5. Logger liên quan đang cho phép `INFO`.

Nếu property được đặt nhưng không có log, không nên kết luận ngay rằng Spring Kafka không hỗ trợ tính năng. Có thể container chưa được khởi tạo, cấu hình đang áp dụng cho factory khác hoặc log level đã lọc mất thông điệp.

## 3. Bật trực tiếp trên ContainerProperties

Nếu ứng dụng tự tạo listener container hoặc muốn kiểm soát cấu hình bằng Java, có thể đặt thuộc tính trực tiếp:

~~~java
ContainerProperties containerProperties =
        new ContainerProperties("orders");

containerProperties.setGroupId("billing-service");
containerProperties.setLogContainerConfig(true);

KafkaMessageListenerContainer<String, OrderCreated> container =
        new KafkaMessageListenerContainer<>(
                consumerFactory,
                containerProperties);
~~~

Ví dụ này minh họa container được tạo trực tiếp. Trong ứng dụng thực tế, `consumerFactory`, key/value type và listener cần được cấu hình đầy đủ trước khi container được start.

Có thể đọc lại giá trị:

~~~java
boolean logConfig =
        containerProperties.isLogContainerConfig();
~~~

Getter và setter thuộc `ContainerProperties`. Hãy đặt giá trị trước khi container bắt đầu chạy để thông tin được ghi trong quá trình khởi tạo.

## 4. Bật cho container được tạo từ factory

Ứng dụng dùng `@KafkaListener` thường tạo container thông qua `ConcurrentKafkaListenerContainerFactory`. Có thể cấu hình các container được tạo từ factory bằng customizer:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.setContainerCustomizer(container ->
            container.getContainerProperties()
                    .setLogContainerConfig(true));

    return factory;
}
~~~

`ContainerCustomizer` cho phép tùy chỉnh container sau khi factory tạo và cấu hình nó. API này có từ Spring Kafka 2.3.4. Cần kiểm tra phiên bản dependency và kiểu container trong dự án.

Nếu ứng dụng đã có một factory tùy chỉnh, hãy bổ sung thuộc tính vào factory hiện tại thay vì tạo factory thứ hai chỉ để bật log. Điều này tránh thay đổi ngoài ý muốn về consumer factory, error handler, converter, interceptor, transaction manager hoặc concurrency.

### 4.1. Chú ý khi có nhiều listener container factory

Một ứng dụng có thể định nghĩa nhiều factory, ví dụ:

- Factory cho topic đơn hàng với concurrency cao.
- Factory cho topic audit với concurrency thấp.
- Factory cho listener batch.
- Factory có transaction hoặc error handler riêng.

Property `spring.kafka.listener.log-container-config` thuộc cấu hình listener của Spring Boot và được áp dụng cho factory auto-configured theo cơ chế bind của Boot. Nếu ứng dụng tự khai báo factory riêng, hãy xác nhận custom factory có nhận cấu hình đó hay không. Khi cần bảo đảm, đặt `setLogContainerConfig(true)` trên `ContainerProperties` hoặc dùng `ContainerCustomizer` của factory tương ứng.

Đừng chỉ kiểm tra một listener rồi kết luận tất cả container đều bật. Mỗi listener có thể chỉ định `containerFactory` khác nhau trong annotation:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        containerFactory = "orderKafkaListenerContainerFactory")
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

## 5. Nội dung log và phạm vi thông tin

Thông điệp được ghi là bản tóm tắt cấu hình container. Nó giúp nhận diện cấu hình Spring Kafka mà container đang sử dụng, chẳng hạn những thuộc tính thuộc `ContainerProperties` và thông tin liên quan đến listener container.

Khi đọc log, nên đối chiếu các nhóm thông tin có ảnh hưởng đến vận hành:

| Nhóm | Nội dung cần xác nhận |
|---|---|
| Listener identity | Bean/container name, listener id hoặc thông tin nhận diện container |
| Topic subscription | Topic, topic pattern hoặc partition được chỉ định |
| Consumer group | Group id mà listener sử dụng |
| Acknowledgement | Ack mode và các thiết lập liên quan đến commit |
| Polling | Poll timeout, concurrency và các thuộc tính container liên quan |
| Error handling | Error handler hoặc các cấu hình phục hồi liên quan nếu được thể hiện trong log |
| Transaction | Cấu hình transaction của container nếu được áp dụng |
| Monitoring | Các thuộc tính idle event, monitor và no-poll threshold nếu được thể hiện |

Không nên giả định thông điệp này là bản dump đầy đủ của mọi cấu hình trong toàn hệ thống. `logContainerConfig` tập trung vào cấu hình listener container; nó không thay thế việc kiểm tra toàn bộ `ConsumerFactory`, Kafka client properties, broker configuration, ACL, topic configuration hay trạng thái runtime.

Đặc biệt, log cấu hình không chứng minh rằng broker đã chấp nhận mọi giá trị, topic tồn tại, consumer có quyền đọc hoặc partition đã được gán. Để xác nhận các điều kiện đó, cần kết hợp log khởi động với consumer group state, broker metrics, ACL và kết quả hoạt động thực tế.

## 6. Điều kiện để log xuất hiện

Có hai điều kiện quan trọng:

1. `logContainerConfig` phải là `true` trên container được khởi tạo.
2. Logger phải cho phép mức `INFO`.

Ví dụ cấu hình log level:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka: INFO
~~~

Tên logger cụ thể phát ra thông điệp có thể thay đổi theo phiên bản và implementation. Nếu cần lọc chính xác, hãy quan sát logger trong dòng log thực tế rồi cấu hình category tương ứng. Không nên nâng toàn bộ logging của ứng dụng lên `DEBUG` chỉ để nhìn thấy thông điệp này.

Nếu logger liên quan chỉ cho phép `WARN` hoặc `ERROR`, thông điệp ở mức `INFO` sẽ không xuất hiện dù thuộc tính đã được bật.

### 6.1. Log được ghi khi nào?

Đây là log cấu hình trong giai đoạn container khởi tạo/startup, không phải log lặp theo từng record hoặc mỗi lần poll. Nó cũng không phải một dashboard cập nhật cấu hình theo thời gian thực.

Nếu thay đổi cấu hình khi ứng dụng đang chạy, thông điệp cũ vẫn phản ánh cấu hình tại thời điểm container được khởi tạo. Muốn có log cho cấu hình mới, cần áp dụng thay đổi theo lifecycle phù hợp và khởi tạo lại container. Không nên restart container chỉ để tạo log nếu không có lý do vận hành cần thiết.

## 7. Phân biệt với các loại log khác của Spring Kafka

`logContainerConfig` dễ bị nhầm với các tùy chọn logging khác. Chúng có mục đích riêng:

| Tùy chọn | Mục đích | Khi nào dùng |
|---|---|---|
| `logContainerConfig` | Ghi tóm tắt cấu hình listener container ở INFO khi khởi tạo | Xác nhận cấu hình container đang áp dụng |
| `commitLogLevel` | Chọn log level cho thông điệp liên quan đến offset commit | Điều tra thời điểm và kết quả commit |
| Logger của Kafka client | Ghi thông tin hoạt động nội bộ của consumer/producer client | Điều tra protocol, coordinator, network hoặc client behavior |
| `missingTopicsFatal` | Quyết định container có dừng khởi động khi topic cấu hình không tồn tại hay không | Kiểm soát hành vi startup khi thiếu topic |
| Application log | Ghi thông tin nghiệp vụ do ứng dụng chủ động phát | Theo dõi event id, kết quả xử lý và lỗi nghiệp vụ |

Ví dụ, `commitLogLevel` điều khiển mức log của offset commit; nó không bật log cấu hình container. Ngược lại, `logContainerConfig` không làm offset commit được ghi ở INFO và không thay đổi semantics commit.

Nếu cần điều tra commit, hãy cấu hình commit logging riêng:

~~~java
containerProperties.setCommitLogLevel(
        LogIfLevelEnabled.Level.INFO);
~~~

API và enum cần khớp phiên bản Spring Kafka. Chỉ tăng commit log level khi có nhu cầu vì log từng commit có thể tạo nhiều dòng khi throughput cao.

## 8. Dùng logContainerConfig trong quy trình triển khai

Một cách dùng hiệu quả là bật log cấu hình trong giai đoạn kiểm chứng release hoặc khi điều tra khác biệt giữa môi trường.

Quy trình tham khảo:

1. Xác định listener cần kiểm tra và factory mà listener đang sử dụng.
2. Bật `log-container-config` cho factory đó.
3. Khởi động ứng dụng hoặc container theo quy trình triển khai.
4. Tìm log cấu hình của đúng listener/container.
5. Đối chiếu topic, group id, ack mode, concurrency và các thuộc tính vận hành cần thiết với cấu hình mong muốn.
6. Nếu có khác biệt, truy nguồn giá trị từ YAML, profile, environment variable, factory customizer hoặc annotation.
7. Sửa nguồn cấu hình và triển khai lại.
8. Lưu lại log hoặc kết quả xác nhận theo quy trình change management nếu cần.

Với ứng dụng nhiều listener, có thể bật trong staging để lập baseline cấu hình của từng container. Khi đã xác nhận cấu hình, có thể tắt lại nếu log startup quá nhiều hoặc chính sách production không cần giữ thông tin này.

## 9. Kiểm tra cấu hình bị ghi đè

Spring Boot có thể nhận cấu hình từ nhiều nguồn. Một giá trị trong `application.yml` có thể bị ghi đè bởi:

- File cấu hình theo profile.
- Environment variable.
- Java system property.
- Command-line argument.
- Cấu hình được đặt trực tiếp trong bean.
- `ContainerCustomizer` hoặc code tạo container.

Ví dụ, YAML đặt `log-container-config: true`, nhưng custom factory sau đó gọi `setLogContainerConfig(false)`. Khi đó, log có thể không xuất hiện cho container được tạo bởi factory tùy chỉnh.

Khi điều tra, hãy tìm theo đúng thứ tự tạo container:

~~~text
External configuration
        |
        v
Spring Boot KafkaProperties
        |
        v
Auto-configured listener factory
        |
        +---- Custom factory?
        |         |
        |         v
        |    ContainerCustomizer
        |
        v
ContainerProperties
        |
        v
Container startup
~~~

Với factory tùy chỉnh, hãy đọc cấu hình cuối cùng sau khi customizer đã chạy. Việc nhìn thấy property trong YAML chỉ chứng minh nguồn cấu hình có giá trị đó, chưa chứng minh container cuối cùng giữ cùng giá trị.

## 10. Ảnh hưởng đến hiệu năng và dung lượng log

`logContainerConfig` chỉ ghi một thông điệp cấu hình trong quá trình khởi tạo container. Nó không ghi log cho từng record, nên thông thường chi phí runtime thấp so với logging ở đường xử lý message.

Tuy nhiên, số dòng startup log tăng theo số listener container được tạo. Với `ConcurrentMessageListenerContainer` có concurrency lớn, container có thể tạo nhiều child container/consumer thread; cần quan sát số thông điệp thực tế khi bật cấu hình.

Một số cân nhắc:

- Bật trong staging hoặc khi điều tra cấu hình có thể rất hữu ích.
- Bật lâu dài trong production vẫn có thể chấp nhận nếu số container ít và log được quản lý tốt.
- Tránh bật cùng lúc nhiều category `DEBUG` rộng chỉ để tìm thông điệp này.
- Không để log startup lặp liên tục do ứng dụng restart hoặc container bị stop/start ngoài ý muốn mà không điều tra nguyên nhân.
- Kiểm tra retention, quyền truy cập và chính sách lưu trữ log.

Không dùng `logContainerConfig` như một giải pháp giảm log hoặc kiểm soát log volume. Đây là công tắc bật/tắt một loại thông tin chẩn đoán cụ thể.

## 11. Bảo mật và quản lý log cấu hình

Log vận hành có thể chứa tên topic, group id, client id, listener id và các chi tiết triển khai. Những thông tin này có thể hữu ích cho người vận hành nhưng cũng có thể tiết lộ topology hệ thống nếu log được chia sẻ rộng.

Áp dụng các nguyên tắc:

- Giới hạn quyền đọc log theo vai trò.
- Không tự thêm password, SASL secret, token hoặc credential vào log cấu hình.
- Không giả định mọi phiên bản hoặc mọi custom `toString()` đều che giấu thông tin nhạy cảm; kiểm tra output thực tế.
- Áp dụng retention và masking theo chính sách bảo mật của tổ chức.
- Khi gửi log ra ngoài để hỗ trợ điều tra, loại bỏ thông tin nhạy cảm và định danh nội bộ không cần thiết.

Nếu log chứa thông tin nhạy cảm do code tùy chỉnh hoặc wrapper cấu hình, sửa cách ghi log hoặc nguồn dữ liệu đó. Tắt `logContainerConfig` chỉ là biện pháp tạm thời nếu nguyên nhân nằm ở một logger khác.

## 12. Chẩn đoán khi không thấy log

Nếu bật `log-container-config` nhưng không thấy thông điệp, kiểm tra theo trình tự:

1. Xác nhận giá trị cuối cùng của `ContainerProperties.isLogContainerConfig()` là `true`.
2. Xác nhận đúng listener container đã được tạo và start.
3. Xác nhận listener đang dùng đúng factory mà bạn đã cấu hình.
4. Xác nhận logger cho phép `INFO`.
5. Kiểm tra log aggregator có lọc category, message hoặc startup log không.
6. Kiểm tra container có được tạo trước khi cấu hình được áp dụng không.
7. Nếu dùng custom factory, kiểm tra `ContainerCustomizer` và các đoạn code đặt lại thuộc tính.
8. Xác nhận phiên bản Spring Kafka có hỗ trợ thuộc tính này.

### 12.1. Log xuất hiện nhưng giá trị không như mong đợi

Nếu thông điệp có cấu hình sai:

1. Tìm property gốc trong các file cấu hình và profile đang active.
2. Kiểm tra environment variable và command-line argument.
3. Kiểm tra factory nào tạo listener.
4. Kiểm tra các customizer và code gọi setter.
5. Đối chiếu annotation `@KafkaListener`, đặc biệt `groupId`, `id`, `containerFactory` và subscription.
6. Sửa đúng nguồn cấu hình, sau đó khởi tạo lại container và kiểm tra log mới.

Không sửa một giá trị consumer property tùy ý chỉ để làm log trông đúng. Hãy xác định giá trị nào thực sự cần thay đổi và tác động đến consumer group, offset hoặc partition assignment.

### 12.2. Log xuất hiện nhiều lần

Thông điệp có thể xuất hiện nhiều lần khi:

- Ứng dụng có nhiều listener container.
- Một listener container có concurrency tạo nhiều child container.
- Container bị stop và start lại.
- Ứng dụng restart hoặc triển khai rolling update.

Đếm số listener bean không đủ để dự đoán số dòng. Hãy đối chiếu container name, listener id và consumer thread name trong log để xác định mỗi thông điệp thuộc container nào.

## 13. Ví dụ cấu hình hoàn chỉnh

Một cấu hình Spring Boot đơn giản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
      log-container-config: true

logging:
  level:
    org.springframework.kafka: INFO
~~~

Listener:

~~~java
@Component
public class BillingListener {

    @KafkaListener(
            id = "billingOrders",
            topics = "orders")
    public void handle(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

Trong ví dụ, Spring Boot cấu hình listener factory mặc định dựa trên `spring.kafka.listener.*`. Khi listener container khởi tạo, nó ghi tóm tắt cấu hình ở INFO. `logContainerConfig` không thay đổi `ack-mode`, `concurrency`, group id hoặc subscription; các thuộc tính đó được đặt riêng trong YAML và annotation.

Nếu ứng dụng khai báo một `ConcurrentKafkaListenerContainerFactory` riêng, hãy cấu hình `setLogContainerConfig(true)` hoặc customizer trên factory đó và xác nhận listener dùng đúng tên factory.

## 14. Thực hành xác minh

Một bài thực hành ngắn giúp hiểu rõ phạm vi của tùy chọn:

1. Tạo một ứng dụng Spring Boot có một `@KafkaListener`.
2. Đặt `spring.kafka.listener.log-container-config: false`, khởi động và lưu log.
3. Đổi thành `true`, khởi động lại và tìm thông điệp cấu hình ở INFO.
4. Đổi logger liên quan thành `WARN`, khởi động lại và quan sát thông điệp INFO bị lọc.
5. Trả logger về INFO, đổi `concurrency` từ 1 lên 3 và quan sát số container/thread được tạo.
6. Thêm một factory tùy chỉnh, cấu hình log riêng và xác nhận listener nào sử dụng factory nào.
7. Đổi một property qua environment variable để quan sát nguồn cấu hình ghi đè YAML.
8. So sánh log sau mỗi lần khởi động và ghi lại nguồn của giá trị cuối cùng.

Thực hành này xác nhận ba điều: property có được bind hay không, logger có cho phép INFO hay không và container cuối cùng có nhận cấu hình mong đợi hay không.

## 15. Checklist vận hành

### Cấu hình

- [ ] Đã xác định Spring Kafka và Spring Boot version đang sử dụng.
- [ ] Đã bật đúng property `spring.kafka.listener.log-container-config` hoặc setter tương ứng.
- [ ] Đã xác nhận giá trị được đặt trên đúng listener container factory.
- [ ] Custom factory/customizer không ghi đè ngoài ý muốn.
- [ ] Logger liên quan cho phép mức INFO.

### Kiểm tra log

- [ ] Thông điệp xuất hiện khi container khởi tạo.
- [ ] Đã xác định listener/container tương ứng với từng thông điệp.
- [ ] Đã đối chiếu topic, group id, concurrency và ack mode cần thiết.
- [ ] Đã hiểu log là bản tóm tắt cấu hình, không phải trạng thái broker hoặc runtime đầy đủ.
- [ ] Log không để lộ credential hoặc dữ liệu nhạy cảm.

### Vận hành

- [ ] Đã chọn môi trường và thời gian bật phù hợp.
- [ ] Log volume được theo dõi khi có nhiều listener/concurrency.
- [ ] Quy trình nâng cấp kiểm tra lại tên logger và output nếu version thay đổi.
- [ ] Có runbook truy nguồn property khi cấu hình thực tế khác mong đợi.

## Kết luận

`logContainerConfig` là công tắc chẩn đoán đơn giản nhưng hữu ích của Spring Kafka. Khi bật, mỗi listener container ghi tóm tắt cấu hình ở mức INFO trong quá trình khởi tạo; mặc định thuộc tính này là `false`. Spring Boot hỗ trợ cấu hình qua `spring.kafka.listener.log-container-config`, còn ứng dụng tự tạo container có thể gọi `ContainerProperties.setLogContainerConfig(true)`. Hãy dùng thông điệp này để xác nhận cấu hình cuối cùng, kiểm tra đúng factory và profile, đồng thời kết hợp với consumer group state, broker logs và metrics khi điều tra sự cố. Nó cung cấp bằng chứng về cấu hình container tại startup, không thay thế việc kiểm tra trạng thái hoạt động thực tế của Kafka.

## Tài liệu tham khảo

- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
