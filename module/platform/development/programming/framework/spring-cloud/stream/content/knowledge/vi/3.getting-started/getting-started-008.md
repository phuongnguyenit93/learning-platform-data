# Tách cấu hình theo môi trường bằng profile và biến môi trường

Một ứng dụng Spring Cloud Stream thường chạy ở nhiều môi trường: máy phát triển cá nhân, môi trường kiểm thử, staging và production. Mỗi môi trường có thể dùng broker, địa chỉ kết nối, tên destination, consumer group và thông tin xác thực khác nhau. Nếu các giá trị này nằm rải rác trong mã nguồn hoặc bị ghi cố định trong một tệp cấu hình, việc triển khai dễ nhầm môi trường, khó kiểm thử và có nguy cơ làm lộ thông tin bí mật.

Spring Boot hỗ trợ externalized configuration: ứng dụng đọc cấu hình từ tệp, biến môi trường, tham số dòng lệnh và các nguồn cấu hình bên ngoài. Spring Profiles cho phép chọn một tập cấu hình theo môi trường đang chạy. Spring Cloud Stream sử dụng các thuộc tính đó để cấu hình function, binding, destination, consumer và binder. Mục tiêu là giữ logic xử lý sự kiện ổn định, đồng thời cung cấp đúng cấu hình cho từng lần triển khai.

## 1. Phân chia cấu hình dùng chung và cấu hình theo môi trường

Trước tiên, phân loại cấu hình thành ba nhóm:

| Nhóm | Ví dụ | Cách quản lý |
|---|---|---|
| Cấu hình dùng chung | Tên ứng dụng, function definition, tên binding, số lần thử lại mặc định | Đặt trong **application.yml**. |
| Cấu hình phụ thuộc môi trường | Destination, consumer group, địa chỉ broker, cổng, chế độ bảo mật | Đặt trong profile hoặc truyền từ môi trường triển khai. |
| Thông tin bí mật | Mật khẩu broker, token, private key, credential | Lấy từ secret store hoặc cơ chế cấp secret của nền tảng; không commit vào Git. |

Không phải mọi giá trị khác nhau giữa các môi trường đều cần một profile riêng. Một quy tắc hữu ích là dùng profile cho lựa chọn có tính chất của môi trường, còn biến môi trường dùng cho giá trị triển khai cụ thể như hostname, tên topic hoặc credential. Ví dụ, profile **prod** có thể bật cấu hình dành cho production, trong khi **KAFKA_BOOTSTRAP_SERVERS** cung cấp địa chỉ cluster thực tế.

## 2. Spring Profiles hoạt động như thế nào?

Profile là nhãn dùng để kích hoạt một nhóm cấu hình. Spring Boot tự động đọc **application.yml** và các tệp profile tương ứng như **application-local.yml**, **application-test.yml** hoặc **application-prod.yml**. Cấu hình profile được áp dụng khi profile đó đang hoạt động và có thể ghi đè giá trị dùng chung.

Ví dụ cấu trúc tệp:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-prod.yml
~~~

Kích hoạt profile bằng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Hoặc truyền tham số khi chạy ứng dụng:

~~~bash
java -jar order-stream.jar --spring.profiles.active=prod
~~~

Khi chạy với profile **prod**, Spring Boot nạp cấu hình chung rồi áp dụng phần cấu hình dành cho **prod**. Nếu cùng một thuộc tính xuất hiện ở cả hai nơi, giá trị của nguồn cấu hình có độ ưu tiên cao hơn sẽ được sử dụng. Biến môi trường và tham số dòng lệnh thường được dùng để ghi đè các giá trị trong tệp cấu hình.

Không đặt **spring.profiles.active** trong tệp cấu hình dành riêng cho một profile như **application-prod.yml**. Hãy kích hoạt profile từ môi trường chạy, tham số dòng lệnh hoặc một nguồn cấu hình không phụ thuộc profile. Cách này tránh tình huống ứng dụng phải đọc một profile để biết profile nào cần kích hoạt.

### Ví dụ tách cấu hình bằng nhiều tệp

Tệp **application.yml** chứa phần dùng chung:

~~~yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing}
          consumer:
            max-attempts: ${APP_CONSUMER_MAX_ATTEMPTS:3}
~~~

Hàm được chọn có thể là một Consumer thông thường:

~~~java
@Bean
Consumer<OrderCreated> orderProcessor(OrderService orderService) {
    return event -> orderService.process(event);
}
~~~

Tên binding đầu vào **orderProcessor-in-0** được Spring Cloud Stream suy ra từ tên hàm **orderProcessor**. **destination** xác định đích nhận sự kiện; **group** xác định nhóm tiêu thụ. Các placeholder **${TEN_BIEN:gia_tri_mac_dinh}** cho phép lấy giá trị từ biến môi trường và cung cấp giá trị mặc định khi biến chưa được đặt.

Tệp **application-local.yml** có thể cấu hình môi trường phát triển:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders-local
          group: billing-local
      kafka:
        binder:
          brokers: localhost:9092
~~~

Tệp **application-prod.yml** có thể xác định tên destination và nhóm dành cho production, đồng thời yêu cầu địa chỉ broker được cung cấp từ môi trường:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing-v1}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

Trong ví dụ này, phần cấu hình binder Kafka được đặt dưới **spring.cloud.stream.kafka.binder**. Nếu ứng dụng dùng RabbitMQ hoặc Pulsar, cần sử dụng đúng thuộc tính kết nối của binder tương ứng. Không nên sao chép thuộc tính của Kafka sang một binder khác vì tên và ý nghĩa cấu hình không giống nhau.

Nếu profile production được kích hoạt nhưng **KAFKA_BOOTSTRAP_SERVERS** chưa được cung cấp, placeholder không có giá trị mặc định sẽ khiến ứng dụng không thể phân giải cấu hình cần thiết. Đây là cách hữu ích để phát hiện thiếu cấu hình ngay khi khởi động thay vì âm thầm kết nối tới một broker mặc định ngoài dự kiến.

### Dùng một tệp YAML với nhiều tài liệu

Khi số lượng khác biệt nhỏ, có thể dùng nhiều tài liệu YAML trong cùng **application.yml**, phân cách bằng **---**. Trường **spring.config.activate.on-profile** quy định tài liệu nào được áp dụng:

~~~yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders
          group: billing
---
spring:
  config:
    activate:
      on-profile: local
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders-local
          group: billing-local
---
spring:
  config:
    activate:
      on-profile: prod
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders
          group: billing-v1
~~~

Cách này phù hợp với module nhỏ có ít khác biệt. Khi mỗi môi trường có nhiều cấu hình broker, bảo mật và quan sát riêng, các tệp **application-{profile}.yml** thường dễ đọc và quản lý hơn.

## 3. Đưa giá trị triển khai vào biến môi trường

Biến môi trường giúp cùng một gói ứng dụng chạy ở nhiều nơi mà không cần đóng gói lại. Spring Boot hỗ trợ relaxed binding: tên biến môi trường có thể biểu diễn tên thuộc tính bằng chữ hoa, thay dấu chấm bằng dấu gạch dưới và bỏ dấu gạch ngang. Ví dụ:

| Thuộc tính Spring | Biến môi trường tương ứng |
|---|---|
| **spring.profiles.active** | **SPRING_PROFILES_ACTIVE** |
| **spring.cloud.stream.kafka.binder.brokers** | **SPRING_CLOUD_STREAM_KAFKA_BINDER_BROKERS** |
| **spring.rabbitmq.host** | **SPRING_RABBITMQ_HOST** |
| **spring.rabbitmq.username** | **SPRING_RABBITMQ_USERNAME** |
| **spring.rabbitmq.password** | **SPRING_RABBITMQ_PASSWORD** |
| **spring.pulsar.client.service-url** | **SPRING_PULSAR_CLIENT_SERVICEURL** |

Các thuộc tính trong bảng minh họa cách ánh xạ tên. Ứng dụng chỉ sử dụng thuộc tính tương ứng khi starter, binder và phiên bản Spring Boot đang dùng hỗ trợ cấu hình đó. Với Spring Cloud Stream, hãy xác nhận tài liệu của binder được chọn, đặc biệt khi cấu hình nhiều binder trong cùng ứng dụng.

Có thể dùng tên biến do ứng dụng tự định nghĩa trong placeholder. Chẳng hạn:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
~~~

Khi triển khai production, nền tảng có thể cấp các giá trị như:

~~~bash
SPRING_PROFILES_ACTIVE=prod
APP_ORDERS_DESTINATION=orders
APP_CONSUMER_GROUP=billing-v1
KAFKA_BOOTSTRAP_SERVERS=kafka-1.internal:9092,kafka-2.internal:9092
~~~

Đặt các biến này trong cấu hình container, manifest triển khai hoặc hệ thống quản lý cấu hình của nền tảng. Không ghi địa chỉ nội bộ, tên nhóm production hoặc thông tin xác thực vào ví dụ tài liệu dùng chung nếu chúng là thông tin nhạy cảm của tổ chức.

## 4. Hiểu thứ tự ưu tiên khi có nhiều nguồn cấu hình

Một thuộc tính có thể xuất hiện đồng thời trong tệp YAML, biến môi trường và tham số dòng lệnh. Spring Boot áp dụng thứ tự ưu tiên của các property source; nguồn có độ ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn. Trong cách vận hành thông thường:

1. Giá trị mặc định trong mã hoặc cấu hình dùng chung tạo nền tảng.
2. Tệp cấu hình ứng dụng và tệp profile cung cấp giá trị theo môi trường.
3. Biến môi trường và các nguồn cấu hình ngoài cung cấp giá trị của lần triển khai.
4. Tham số dòng lệnh có thể ghi đè cấu hình để phục vụ lần chạy cụ thể.

Đây là mô tả định hướng; thứ tự đầy đủ còn phụ thuộc các nguồn cấu hình được bật, phiên bản Spring Boot và cách ứng dụng khởi chạy. Khi một giá trị không như dự kiến, hãy kiểm tra nguồn cấu hình thực tế thay vì đoán từ riêng tệp YAML.

Ví dụ, nếu **application-prod.yml** đặt **group: billing-v1**, nhưng môi trường triển khai đồng thời đặt **APP_CONSUMER_GROUP=billing-canary** và YAML dùng placeholder **${APP_CONSUMER_GROUP:billing-v1}**, ứng dụng sẽ nhận **billing-canary**. Nếu thuộc tính được khai báo trực tiếp ở nhiều property source, biến môi trường có tên tương ứng cũng có thể ghi đè giá trị trong tệp.

Không nên tạo quá nhiều lớp ghi đè khó theo dõi. Hãy xác định rõ nguồn sở hữu từng loại cấu hình: tệp ứng dụng giữ cấu trúc, profile chọn hành vi môi trường, còn nền tảng triển khai cấp giá trị cụ thể.

## 5. Quản lý thông tin bí mật an toàn

Mật khẩu Kafka, RabbitMQ, Pulsar, token và khóa riêng không nên nằm trong **application.yml** đã commit. Nếu credential bị lưu trong Git, xóa dòng đó ở commit mới không làm bí mật biến mất khỏi lịch sử repository. Cần thay credential đã lộ và xử lý lịch sử theo quy trình bảo mật của tổ chức.

Các cách cấp secret thường gặp:

- Secret manager của tổ chức hoặc nền tảng đám mây.
- Kubernetes Secret được mount hoặc đưa vào container dưới dạng biến môi trường theo chính sách vận hành.
- Tệp cấu hình được mount từ hệ thống quản lý secret, với quyền đọc giới hạn cho tiến trình ứng dụng.
- Cơ chế xác thực workload hoặc danh tính dịch vụ, nếu broker và nền tảng hỗ trợ.

Ví dụ, Spring Boot có thể đọc biến môi trường cho thông tin kết nối RabbitMQ:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
~~~

Giá trị thật được cấp tại thời điểm chạy. Không in password, token hoặc toàn bộ cấu hình đã phân giải ra log. Cẩn thận với endpoint chẩn đoán như Actuator **env** và **configprops**: dù Spring Boot có cơ chế che một số giá trị nhạy cảm, việc mở các endpoint này ra ngoài vẫn có thể làm lộ thông tin cấu hình. Chỉ bật và bảo vệ chúng theo chính sách vận hành.

Nếu dùng tệp secret được mount, Spring Boot hỗ trợ config tree thông qua **spring.config.import**, ví dụ **optional:configtree:/run/secrets/**. Mỗi tệp trong thư mục có thể cung cấp một thuộc tính cấu hình. Cần xác nhận cách đặt tên tệp, quyền truy cập và đường dẫn mount của nền tảng trước khi áp dụng.

## 6. Tách cấu hình binder theo môi trường

Spring Cloud Stream binding mô tả cách hàm kết nối với destination. Binder chịu trách nhiệm giao tiếp với hệ thống truyền tin cụ thể. Vì vậy, khi chuyển từ môi trường local sang production, hãy kiểm tra cả hai lớp:

- **Binding:** function definition, destination, group, consumer concurrency, partitioning và retry.
- **Binder:** loại broker, địa chỉ cluster, thông tin xác thực, TLS, cơ chế xác thực và các tùy chọn riêng của broker.

Ví dụ với Kafka, thuộc tính **spring.cloud.stream.kafka.binder.brokers** chỉ ra địa chỉ broker cho Kafka binder. Với RabbitMQ, ứng dụng thường sử dụng các thuộc tính kết nối RabbitMQ như host, port, username và password. Với Pulsar, cần cấu hình service URL và các tùy chọn client/binder tương ứng. Tên thuộc tính cụ thể phụ thuộc starter và phiên bản đang sử dụng.

Nếu một ứng dụng kết nối nhiều binder, hãy đặt tên binder rõ ràng và cấu hình riêng từng binder theo tài liệu Spring Cloud Stream của phiên bản dự án. Tránh để một profile vô tình chọn nhầm binder hoặc trỏ tới cluster dùng chung giữa test và production.

Đặc biệt, destination và group là cấu hình có tác động đến dữ liệu. Nếu hai môi trường dùng chung destination và group ngoài ý muốn, consumer test có thể cạnh tranh nhận thông điệp với consumer production. Nếu đổi group trong production, broker có thể tạo tiến độ tiêu thụ mới và phát lại sự kiện theo chính sách của nó. Hãy xem việc thay đổi các giá trị này như một thay đổi vận hành cần được kiểm thử.

## 7. Chạy và kiểm tra theo từng môi trường

Với môi trường local, có thể kích hoạt profile và cung cấp địa chỉ broker trên máy phát triển:

~~~bash
SPRING_PROFILES_ACTIVE=local
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
~~~

Trên Windows PowerShell, cú pháp đặt biến cho phiên hiện tại là:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
java -jar ./target/order-stream.jar
~~~

Trong container, khai báo cùng các biến ở phần **environment** hoặc thông qua cơ chế secret/config của nền tảng. Không nên đóng gói các giá trị production vào image vì cùng một image cần được dùng nhất quán giữa các bước triển khai.

Kiểm thử profile có thể thực hiện bằng Spring Boot test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderProcessorConfigurationTest {

    @Test
    void loadsTestProfile() {
        // Xác minh cấu hình test và binding cần thiết.
    }
}
~~~

Kiểm thử cấu hình nên xác nhận ít nhất:

1. Profile mong muốn thực sự được kích hoạt.
2. Function definition trỏ tới đúng hàm xử lý.
3. Binding đầu vào có destination và group dự kiến.
4. Binder đang dùng là loại broker được môi trường cung cấp.
5. Giá trị bắt buộc như địa chỉ broker và credential được cấp đầy đủ.
6. Cấu hình test không thể vô tình trỏ tới destination hoặc group production.

Với integration test, dùng broker thử nghiệm riêng hoặc container dịch vụ phù hợp. Đừng chỉ kiểm tra ứng dụng khởi động thành công: hãy gửi một thông điệp mẫu và xác nhận consumer nhận đúng sự kiện từ đúng destination. Khi kiểm tra lỗi cấu hình, cố ý bỏ một biến bắt buộc để bảo đảm ứng dụng dừng với thông báo rõ ràng.

## 8. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng luôn dùng cấu hình local | Profile không được kích hoạt hoặc biến **SPRING_PROFILES_ACTIVE** chưa được truyền vào tiến trình. | Kiểm tra biến trong chính container/process và danh sách profile lúc khởi động. |
| Destination không thay đổi | Sai tên binding, profile không được nạp hoặc biến placeholder không tồn tại. | Đối chiếu tên function và binding, kiểm tra profile và tên biến. |
| Consumer không nhận sự kiện | Sai broker, destination, group, quyền truy cập hoặc cấu hình binder. | Kiểm tra binding đã được tạo, log kết nối và tài nguyên thực tế trên broker. |
| Consumer test nhận thông điệp production | Hai môi trường dùng chung destination hoặc group. | Tách destination/group và xác minh cấu hình cuối cùng trước khi chạy. |
| Ứng dụng khởi động nhưng dùng giá trị mặc định ngoài ý muốn | Placeholder có fallback không phù hợp với môi trường triển khai. | Bỏ fallback cho giá trị bắt buộc ở production hoặc kiểm tra cấu hình khi khởi động. |
| Credential không được nhận | Sai tên biến, sai cách mount secret hoặc quyền đọc không phù hợp. | Kiểm tra tên thuộc tính, môi trường tiến trình và quyền truy cập; không in giá trị bí mật. |
| Đổi profile làm sự kiện được xử lý lại | Group hoặc subscription thay đổi, tạo tiến độ tiêu thụ mới. | Đánh giá offset/cursor và chính sách phát lại trước khi triển khai. |

Một lỗi tinh vi là đặt tên biến môi trường gần giống nhưng không đúng quy tắc ánh xạ. Với thuộc tính Spring có cấu trúc sâu hoặc khóa chứa dấu gạch ngang, hãy dùng đúng quy tắc relaxed binding hoặc dùng placeholder có tên biến đơn giản do ứng dụng kiểm soát. Không giả định mọi tên YAML đều có thể chuyển sang biến môi trường bằng cách thay dấu chấm một cách tùy ý.

## 9. Quy trình đề xuất trước khi triển khai

1. Xác định profile cần kích hoạt và ghi rõ profile đó trong cấu hình triển khai.
2. Đặt các thuộc tính dùng chung trong **application.yml**; chỉ đưa phần khác biệt thực sự vào tệp profile.
3. Chuyển địa chỉ broker, destination có thể thay đổi và credential sang biến môi trường hoặc secret store.
4. Kiểm tra tên function, binding, destination và group trên từng môi trường.
5. Xác nhận binder và broker đích đúng với môi trường.
6. Chạy kiểm thử cấu hình và integration test với broker thử nghiệm.
7. Kiểm tra log khởi động, quyền truy cập và các chỉ số kết nối trước khi tăng số lượng consumer.
8. Ghi nhận thay đổi group, destination hoặc chính sách bảo mật như thay đổi vận hành có kế hoạch rollback.

Checklist ngắn:

- [ ] **SPRING_PROFILES_ACTIVE** được đặt rõ ràng khi triển khai.
- [ ] Tệp profile chỉ chứa các khác biệt cần thiết của môi trường.
- [ ] Không có mật khẩu, token hoặc private key trong repository.
- [ ] Placeholder bắt buộc không âm thầm dùng giá trị mặc định ở production.
- [ ] Mỗi binding trỏ tới destination và group đúng môi trường.
- [ ] Binder kết nối đúng cluster và dùng cơ chế bảo mật phù hợp.
- [ ] Test profile không thể nhận sự kiện production.
- [ ] Thay đổi group/destination đã được đánh giá tác động đến tiến độ và khả năng phát lại.
- [ ] Log và endpoint quản trị không làm lộ secret.

Tách cấu hình theo profile và biến môi trường giúp cùng một ứng dụng Spring Cloud Stream hoạt động nhất quán ở nhiều môi trường. Profile chọn cấu hình theo mục đích triển khai, biến môi trường cung cấp giá trị của lần chạy, còn secret store bảo vệ thông tin xác thực. Khi cả binding và binder đều được kiểm tra, nhóm phát triển có thể triển khai cùng một artifact với destination, consumer group và broker phù hợp mà không phải sửa logic xử lý sự kiện.
