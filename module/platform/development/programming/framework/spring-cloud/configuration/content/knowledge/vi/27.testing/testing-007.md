# Kiểm thử Bus nhiều instance và địa chỉ đích

Spring Cloud Bus giúp phát sự kiện quản trị qua message broker đến nhiều instance Spring Boot. Khi kiểm thử một cụm Config Client, cần xác nhận đúng instance nhận refresh, các instance cùng service được cập nhật khi chọn destination theo service, và service ngoài phạm vi không bị tác động. Một bài kiểm thử chỉ xác nhận endpoint trả HTTP 200 chưa đủ: Bus là cơ chế truyền sự kiện bất đồng bộ, còn từng client phải nạp lại cấu hình và áp dụng giá trị mới.

Bài viết xây dựng kịch bản kiểm thử với nhiều replica của `orders-service` và một replica của `payment-service`. Nội dung tập trung vào service ID, destination pattern, broker dùng chung, endpoint `/actuator/busrefresh`, cách kiểm tra kết quả theo từng instance và xử lý các tình huống không nhận được sự kiện.

## 1. Kiến trúc kiểm thử nhiều instance

Một môi trường kiểm thử tối thiểu nên có:

- Một Config Server hoặc nguồn cấu hình giả lập trả revision hiện hành.
- Hai instance của cùng một Config Client, ví dụ `orders-service`.
- Một instance thuộc service khác, ví dụ `payment-service`.
- Một message broker chung như RabbitMQ hoặc Kafka.
- Một điểm quản trị được phép gọi endpoint Bus.
- Một cách đọc release ID hoặc giá trị kiểm thử trên từng instance.

~~~mermaid
flowchart TD
    OP[Operator / Integration Test] -->|POST busrefresh destination| O1[orders-service instance A]
    O1 -->|publish event| B[Spring Cloud Bus / Broker]
    B --> O1
    B --> O2[orders-service instance B]
    B --> P1[payment-service instance A]
    O1 -->|fetch config| CS[Config Server]
    O2 -->|fetch config| CS
    P1 -->|fetch config| CS
    O1 --> V1[Verify release ID]
    O2 --> V2[Verify release ID]
    P1 --> V3[Verify release ID]
~~~

Các instance cùng tham gia một Bus phải kết nối được tới cùng broker và cùng bus destination. Khi event được phát, các node nhận message sẽ kiểm tra destination pattern với service ID của chính mình. Node khớp destination mới xử lý refresh; node không khớp sẽ bỏ qua sự kiện đó.

Nên dùng một môi trường integration test riêng với broker và Config Server kiểm thử. Không gửi event thử nghiệm đến broker production hoặc expose endpoint quản trị công khai.

## 2. Dependency và cấu hình cơ bản

Mỗi ứng dụng tham gia Bus cần Spring Cloud Bus starter, Actuator và Config Client nếu nó lấy cấu hình từ Spring Cloud Config Server. Ví dụ Maven với RabbitMQ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bus-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Nếu dùng Kafka, thay `spring-cloud-starter-bus-amqp` bằng `spring-cloud-starter-bus-kafka`. Không thêm cả hai starter nếu ứng dụng chỉ dùng một transport. Quản lý phiên bản qua Spring Cloud BOM tương thích với Spring Boot của dự án.

Ví dụ cấu hình Config Client:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: test
  config:
    import: "configserver:http://config-server:8888"
  rabbitmq:
    host: rabbitmq
    port: 5672
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Config Server cũng cần Bus starter và kết nối broker nếu nó là thành phần phát sự kiện. Tất cả node cần dùng cùng broker, credentials phù hợp và cấu hình Bus destination nhất quán. Với Kafka, cấu hình `spring.kafka.bootstrap-servers` và security tương ứng thay cho RabbitMQ.

Endpoint `busrefresh` phải được expose trên ứng dụng phát lệnh. Chỉ expose các endpoint thật sự cần thiết; trong ví dụ này không mở `env`, `busenv` hoặc `busshutdown` vì bài kiểm thử chỉ cần refresh.

## 3. Service ID phải duy nhất cho từng instance

Spring Cloud Bus định danh mỗi instance bằng service ID. Giá trị có thể được đặt trực tiếp qua `spring.cloud.bus.id`. Nếu không đặt, ID mặc định được tạo từ thông tin môi trường, thường theo dạng:

~~~text
app:index:id
~~~

Trong đó:

- `app`: tên ứng dụng, thường lấy từ `spring.application.name`.
- `index`: chỉ số instance, có thể lấy từ `spring.application.index`, local/server port hoặc metadata nền tảng.
- `id`: instance ID do nền tảng cung cấp hoặc một giá trị ngẫu nhiên.

Ví dụ ba instance:

| Instance | Service ID |
| --- | --- |
| orders replica A | `orders-service:0:orders-a` |
| orders replica B | `orders-service:1:orders-b` |
| payment replica A | `payment-service:0:payment-a` |

Trong môi trường kiểm thử, có thể đặt ID tường minh để dễ dự đoán destination:

~~~yaml
spring:
  cloud:
    bus:
      id: ${spring.application.name}:${BUS_INSTANCE_INDEX}:${BUS_INSTANCE_ID}
~~~

Mỗi tiến trình phải nhận `BUS_INSTANCE_INDEX` và `BUS_INSTANCE_ID` riêng. Ví dụ:

~~~text
# orders replica A
BUS_INSTANCE_INDEX=0
BUS_INSTANCE_ID=orders-a

# orders replica B
BUS_INSTANCE_INDEX=1
BUS_INSTANCE_ID=orders-b
~~~

Không copy cùng một `spring.cloud.bus.id` sang mọi replica. ID trùng nhau làm Bus không thể phân biệt đúng sender và receiver; tài liệu Spring cảnh báo các instance có cùng ID có thể khiến event không được xử lý như mong đợi. Nếu dùng `spring.application.index` thay cho ID tùy chỉnh, giá trị index cũng phải khác nhau giữa các replica.

## 4. Destination chọn instance nào?

Endpoint Bus nhận destination ở phần path sau tên endpoint. Destination được so khớp với service ID bằng Spring `PathMatcher`, sử dụng dấu hai chấm `:` làm ký tự phân tách.

Có ba phạm vi thường dùng:

| Phạm vi | Destination | Ví dụ endpoint |
| --- | --- | --- |
| Tất cả node tham gia Bus | Không truyền destination | `POST /actuator/busrefresh` |
| Một instance cụ thể | Service ID đầy đủ | `POST /actuator/busrefresh/orders-service:0:orders-a` |
| Tất cả instance của một service | Pattern kết thúc bằng `:**` | `POST /actuator/busrefresh/orders-service:**` |

Với các ID trong bảng trước:

- `orders-service:0:orders-a` chỉ khớp replica A.
- `orders-service:**` khớp cả hai replica của orders-service.
- `payment-service:**` khớp các instance payment-service.
- Không truyền destination sẽ phát refresh cho tất cả ứng dụng đang tham gia Bus.

Dấu `**` là wildcard cho phần còn lại của service ID. Vì dấu hai chấm là separator, pattern `orders-service:**` giới hạn theo application name ở phần đầu và không phụ thuộc index hoặc instance ID.

Destination là bộ lọc sự kiện ở phía Bus, không phải địa chỉ HTTP trực tiếp tới từng pod. Người vận hành không cần gọi riêng từng instance nếu mục tiêu là tất cả replica của một service.

## 5. Kiểm thử refresh đúng một instance

Giả sử Config Server trả `config.release-id=release-test-2` cho `orders-service`, nhưng các client hiện đang dùng `release-test-1`.

Gọi endpoint đích đầy đủ:

~~~bash
curl --fail --silent --show-error -X POST \
  "http://orders-service-admin:8080/actuator/busrefresh/orders-service:0:orders-a"
~~~

Sau khi event được xử lý, kỳ vọng:

| Instance | Release ID trước | Release ID sau |
| --- | --- | --- |
| `orders-service:0:orders-a` | `release-test-1` | `release-test-2` |
| `orders-service:1:orders-b` | `release-test-1` | `release-test-1` |
| `payment-service:0:payment-a` | `release-test-1` | Không đổi |

Bảng này giả định Config Server có cấu hình mới cho orders-service và payment-service không bị thay đổi. Nếu endpoint được gọi từ một instance thuộc chính nhóm đích, instance gửi cũng có thể là một node cần xử lý theo destination; hãy tính nó vào tập kết quả mong đợi.

Sau khi gửi lệnh, không kiểm tra kết quả ngay lập tức chỉ bằng một request. Hãy đợi trong một khoảng timeout hữu hạn và đọc release ID trên từng instance. Bus truyền sự kiện bất đồng bộ nên thời điểm cập nhật có thể khác nhau giữa các node.

## 6. Kiểm thử refresh toàn bộ một service

Để refresh tất cả replica của orders-service, dùng pattern:

~~~bash
curl --fail --silent --show-error -X POST \
  "http://orders-service-admin:8080/actuator/busrefresh/orders-service:**"
~~~

Kết quả mong đợi:

| Instance | Có khớp destination? | Kết quả mong đợi |
| --- | --- | --- |
| `orders-service:0:orders-a` | Có | Nạp revision mới |
| `orders-service:1:orders-b` | Có | Nạp revision mới |
| `payment-service:0:payment-a` | Không | Giữ revision cũ |

Đây là bài test quan trọng nhất để xác nhận pattern theo service. Nếu chỉ một replica orders được refresh, kiểm tra ID của replica còn lại có đúng prefix `orders-service:` hay không, đồng thời kiểm tra nó có đang kết nối cùng broker và bus destination không.

Nếu payment-service cũng refresh, kiểm tra destination đã được gửi đúng chưa. Một lỗi thường gặp là bỏ trống destination hoặc dùng pattern quá rộng như `**`, khiến tất cả ứng dụng nhận sự kiện.

## 7. Kiểm thử broadcast tới toàn Bus

Khi bỏ destination, Bus phát refresh cho mọi node tham gia:

~~~bash
curl --fail --silent --show-error -X POST \
  "http://bus-admin:8080/actuator/busrefresh"
~~~

Kỳ vọng cả orders-service và payment-service đều nạp lại Environment. Chỉ dùng broadcast khi thay đổi thực sự áp dụng cho toàn bộ ứng dụng hoặc khi có lý do vận hành rõ ràng.

Không dùng broadcast như lựa chọn mặc định cho một thay đổi riêng service. Event diện rộng làm tăng tải lên Config Server và broker, đồng thời có thể tạo ra thay đổi runtime ngoài phạm vi mong muốn.

## 8. Phân biệt busrefresh với refresh cục bộ

| Endpoint | Phạm vi | Mục đích |
| --- | --- | --- |
| `POST /actuator/refresh` | Một application instance | Refresh Environment và các bean hỗ trợ trên chính instance đó |
| `POST /actuator/busrefresh` | Mọi node trên Bus | Phát refresh event cho toàn Bus |
| `POST /actuator/busrefresh/{destination}` | Node khớp destination | Phát refresh event có chọn lọc |

Bus refresh làm sạch cache của RefreshScope và rebind các bean `@ConfigurationProperties` theo cơ chế Spring Cloud Context. Nó không tự khởi động lại mọi singleton hoặc thay thế mọi tài nguyên runtime. Bean giữ giá trị trong field, connection pool hoặc client tự quản lý có thể cần một cơ chế cập nhật riêng.

Một request `busrefresh` thành công chỉ cho biết endpoint đã tiếp nhận yêu cầu phát event. Nó không phải acknowledgement rằng mọi client đã nạp cấu hình và mọi bean đã áp dụng giá trị mới. Cần kiểm tra từng instance sau khi phát event.

## 9. Chuẩn bị dữ liệu để xác minh kết quả

Không nên dùng password hoặc secret để chứng minh refresh. Thêm một property không nhạy cảm vào cấu hình kiểm thử:

~~~yaml
config:
  release-id: release-test-2

orders:
  feature:
    banner: "config-test-2"
~~~

Có thể đọc property trên từng client qua Actuator trong môi trường test:

~~~bash
curl --fail --silent --show-error \
  "http://orders-a:8081/actuator/env/config.release-id"

curl --fail --silent --show-error \
  "http://orders-b:8082/actuator/env/config.release-id"

curl --fail --silent --show-error \
  "http://payment-a:8083/actuator/env/config.release-id"
~~~

Để các lệnh trên hoạt động, profile integration-test cần expose thêm endpoint `env`, ví dụ `management.endpoints.web.exposure.include: health,info,busrefresh,env`. Chỉ mở endpoint này trong môi trường kiểm thử được cô lập và có xác thực. Trong production, ưu tiên health contributor hoặc metric chỉ trả release ID; không expose Environment rộng chỉ để kiểm tra Bus.

Endpoint `env` có thể tiết lộ thông tin cấu hình. Chỉ expose trong môi trường test hoặc mạng quản trị, bật authentication/authorization và giữ sanitization. Trong production, ưu tiên một health contributor hoặc metric chỉ trả release ID đã được phê duyệt.

Nếu muốn kiểm tra bean đã binding, expose `configprops` trong test hoặc tạo một test-only endpoint chỉ trả giá trị không nhạy cảm. Không trả toàn bộ Environment hoặc bean chứa secret.

## 10. Kịch bản integration test với nhiều context

Có thể chạy ba application context trong một integration test hoặc ba process riêng biệt:

- Context A: `orders-service:0:orders-a`.
- Context B: `orders-service:1:orders-b`.
- Context C: `payment-service:0:payment-a`.

Các context dùng chung một RabbitMQ Testcontainer hoặc Kafka Testcontainer. Config Server test trả release ID theo application. Sau khi cả ba context kết nối broker, test gọi endpoint busrefresh với destination cụ thể.

Một bài test theo trình tự:

1. Khởi động broker.
2. Khởi động Config Server test với cấu hình release 1.
3. Khởi động ba client context và đợi health/readiness của cả ba.
4. Xác nhận ba instance đều đang dùng release 1.
5. Thay cấu hình orders-service ở test backend thành release 2.
6. Gọi `/actuator/busrefresh/orders-service:0:orders-a`.
7. Đợi orders-a lên release 2; xác nhận orders-b và payment-a vẫn ở release 1.
8. Gọi `/actuator/busrefresh/orders-service:**`.
9. Đợi cả hai orders instance lên release 2; xác nhận payment-a không đổi.
10. Thay cấu hình chung, gọi broadcast không có destination và xác nhận tất cả node nhận giá trị mới.
11. Dừng context và broker sạch sẽ để test sau không nhận event cũ.

Nếu test dùng Git backend, phải cập nhật repository và bảo đảm Config Server đã nhìn thấy revision mới trước khi gửi refresh event. Nếu Config Server vẫn trả release 1, Bus có thể hoạt động đúng nhưng client vẫn nhận lại giá trị cũ.

## 11. Ví dụ kiểm tra bất đồng bộ bằng Awaitility

Vì Bus xử lý event bất đồng bộ, test nên đợi điều kiện cuối cùng thay vì sleep cố định. Ví dụ minh họa với helper đọc release ID của từng instance:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.awaitility.Awaitility.await;

class BusDestinationIntegrationTest {

    private final ConfigTestClient client = new ConfigTestClient();

    @Test
    void refreshOnlyTheTargetedOrdersInstance() {
        client.updateConfig("orders-service", "release-test-2");

        client.postBusRefresh(
                "http://bus-admin:8080",
                "orders-service:0:orders-a");

        await().atMost(Duration.ofSeconds(30)).untilAsserted(() -> {
            assertThat(client.releaseId("http://orders-a:8081"))
                    .isEqualTo("release-test-2");
            assertThat(client.releaseId("http://orders-b:8082"))
                    .isEqualTo("release-test-1");
            assertThat(client.releaseId("http://payment-a:8083"))
                    .isEqualTo("release-test-1");
        });
    }
}
~~~

`ConfigTestClient` là helper của test, chịu trách nhiệm cập nhật backend, gọi endpoint có xác thực và đọc release ID từ endpoint test-only. Đây là khung minh họa, không phải một class có sẵn của Spring Cloud Bus. Cần cấu hình helper để gọi đúng URL và kiểm tra response status.

Với test theo service, thay destination thành `orders-service:**` và kỳ vọng cả orders-a lẫn orders-b chuyển revision. Với broadcast, bỏ destination và kỳ vọng cả ba instance chuyển revision.

Không dùng `Thread.sleep()` để đoán thời điểm event đến. Awaitility cho phép đợi một điều kiện với timeout xác định và trả lỗi có ngữ cảnh nếu cụm không hội tụ.

## 12. Kiểm tra ID trùng và destination không khớp

Hai lỗi cấu hình có thể làm test destination thất bại:

**ID trùng nhau**

Nếu hai replica cùng khai báo `spring.cloud.bus.id=orders-service:0:orders-a`, Bus không thể phân biệt chúng như hai node riêng biệt. Hãy kiểm tra cấu hình runtime của từng process, không chỉ kiểm tra file YAML dùng chung.

**Destination không khớp**

Nếu instance có ID `orders-service:1:orders-b` nhưng test gửi `orders:*`, pattern có thể không khớp service ID thực tế. Destination cần được xây dựng từ ID mà từng instance thực sự đăng ký trên Bus.

Có thể ghi service ID đã đăng ký ở log khởi động hoặc expose một giá trị chẩn đoán không nhạy cảm. Không log broker password hoặc token khi bật debug để điều tra.

## 13. Kiểm tra broker và đường truyền event

Khi event không đến đúng instance, kiểm tra theo thứ tự:

1. Config Server/client có Bus starter tương ứng trên classpath không?
2. Tất cả node có kết nối cùng RabbitMQ/Kafka cluster không?
3. Các node có cùng cấu hình Bus destination và môi trường không?
4. Broker có connection/consumer/subscription của các instance không?
5. Có lỗi authentication, TLS, virtual host, topic ACL hoặc network không?
6. Service ID của từng instance có duy nhất không?
7. Destination pattern có khớp đúng ID không?
8. Client có nhận event nhưng fetch Config Server thất bại không?

Với RabbitMQ, quan sát connection, channel, exchange và queue theo topology do binder tạo. Với Kafka, kiểm tra topic, consumer group, partition assignment và consumer lag. Tên resource cụ thể phụ thuộc binder và phiên bản Spring Cloud Stream; không hard-code giả định topology khi chưa kiểm tra broker thực tế.

Có thể tạm ngắt kết nối một client trong môi trường test để xác nhận hệ thống phát hiện instance chưa hội tụ. Sau khi kết nối lại, kiểm tra liệu client có nhận event bị bỏ lỡ hay cần một lần refresh chủ động. Không giả định mọi broker hoặc cấu hình consumer đều lưu sự kiện đủ lâu cho một instance offline.

## 14. Kiểm tra event được xử lý đúng một phạm vi

Không nên chỉ đếm số HTTP request tới endpoint. Một lần phát event có thể được nhận bởi nhiều node, nhưng mỗi node tự quyết định có xử lý hay bỏ qua dựa trên destination. Nên xác minh:

- Node mục tiêu có đổi release ID.
- Node không nằm trong destination không đổi release ID.
- Node ngoài service không bị ảnh hưởng bởi pattern theo service.
- Một event không làm ứng dụng chạy nghiệp vụ lặp lại ngoài ý muốn.
- Refresh có thể gọi lặp mà không gây hỏng state hoặc tạo side effect nguy hiểm.

Bus refresh chủ yếu là thao tác nạp lại cấu hình. Nếu listener tùy biến của ứng dụng thực hiện side effect khi nhận Environment change, listener đó cần được thiết kế idempotent. Test không nên giả định broker bảo đảm exactly-once cho toàn bộ hành vi nghiệp vụ.

## 15. Bảo mật endpoint Bus trong kiểm thử và production

Endpoint `busrefresh` có thể thay đổi hành vi của một hoặc nhiều instance. Chỉ expose và cho phép gọi từ danh tính vận hành được phân quyền.

Ví dụ chỉ expose health và busrefresh:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Các biện pháp cần có:

- Bảo vệ endpoint bằng Spring Security hoặc gateway quản trị.
- Giới hạn truy cập theo mạng quản trị và service identity.
- Dùng TLS cho kết nối HTTP và broker.
- Cấp quyền broker tối thiểu cho publisher/consumer.
- Ghi audit người gọi, thời điểm, destination và release ID mục tiêu.
- Không log Authorization header, broker credential hoặc secret trong Environment.
- Không expose `busenv` hoặc `busshutdown` nếu bài toán không cần.
- Không dùng endpoint test-only để đọc toàn bộ cấu hình ở production.

Destination pattern càng rộng thì phạm vi tác động càng lớn. Trước khi broadcast toàn Bus, phải xác định các service tham gia và xác nhận thay đổi áp dụng cho tất cả.

## 16. Bảng test case đề xuất

| Mã | Tình huống | Destination | Kết quả cần xác nhận |
| --- | --- | --- | --- |
| BUS-01 | Một instance trong service | `orders-service:0:orders-a` | Chỉ orders-a đổi release ID |
| BUS-02 | Tất cả replica của một service | `orders-service:**` | orders-a và orders-b đổi; payment giữ nguyên |
| BUS-03 | Broadcast toàn Bus | Không có destination | Tất cả instance đổi |
| BUS-04 | Destination không khớp | `unknown-service:**` | Không instance nào trong cụm đổi |
| BUS-05 | ID trùng | Hai node cùng bus ID | Test phát hiện cấu hình ID không hợp lệ |
| BUS-06 | Một client mất kết nối broker | Theo service hoặc instance | Cảnh báo node chưa nhận event; xác minh phục hồi |
| BUS-07 | Config Server chưa có revision mới | Theo service | Event có thể đến nhưng client vẫn đọc revision cũ; test phải thất bại theo expected release |
| BUS-08 | Bean không hỗ trợ refresh | Theo instance | Environment đổi nhưng runtime assertion phát hiện bean còn giá trị cũ |
| BUS-09 | Broker từ chối xác thực | Broadcast | Publish/consume failure được ghi nhận |
| BUS-10 | Event gửi trùng | Cùng destination | Cấu hình cuối cùng đúng, không phát sinh side effect lặp nguy hiểm |

Test BUS-04 cần hiểu rõ phạm vi: event có thể được publish thành công nhưng không có instance nào match destination. HTTP response từ node phát lệnh không nhất thiết phản ánh số receiver khớp pattern.

## 17. Chẩn đoán khi kết quả không như mong đợi

| Hiện tượng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Endpoint trả 404 | Actuator hoặc busrefresh chưa được expose | Kiểm tra dependency và exposure include |
| Endpoint trả 401/403 | Security policy từ chối | Kiểm tra authentication/authorization |
| Endpoint trả thành công nhưng không node nào đổi | Destination không khớp hoặc event không tới broker | Kiểm tra bus ID, broker và log |
| Một replica không refresh | ID trùng, broker disconnect hoặc node offline | Xác minh service ID và connection của instance |
| Service khác cũng refresh | Destination bị bỏ trống hoặc pattern quá rộng | Kiểm tra path gửi đến endpoint |
| Client nhận event nhưng giá trị không đổi | Config Server chưa có revision mới hoặc label sai | Gọi Environment endpoint trực tiếp |
| Environment đổi nhưng bean vẫn cũ | Bean không hỗ trợ rebind/RefreshScope | Kiểm tra bean lifecycle hoặc restart |
| Local test chạy nhưng cluster lỗi | Mỗi local process có port khác, cluster lại dùng ID cố định | Cấu hình ID duy nhất theo replica |
| Test lúc qua lúc trượt | Assertion chạy trước khi event hoàn tất | Dùng Awaitility và timeout phù hợp |

Khi chẩn đoán, đi theo đường đi của event: endpoint → publish → broker → receiver → destination match → Config Server fetch → bean/runtime apply. Mỗi bước nên có log correlation hoặc metric riêng để biết sự kiện dừng ở đâu.

## 18. Nguyên tắc kiểm thử và vận hành

- Tạo ít nhất hai replica cùng service và một instance service khác để kiểm tra phạm vi.
- Gán service ID duy nhất cho từng instance.
- Dùng cùng broker và Bus destination cho các node thuộc cùng cụm.
- Kiểm thử cả exact instance ID, wildcard theo service và broadcast toàn Bus.
- Đổi revision tại Config Server trước khi phát refresh.
- Xác minh kết quả trên từng instance bằng release ID không nhạy cảm.
- Dùng Awaitility hoặc polling có timeout, không dùng sleep cố định.
- Kiểm tra node không thuộc destination vẫn giữ trạng thái cũ.
- Tách fetch failure, event delivery failure và bean refresh failure.
- Bảo vệ Actuator endpoint, broker credential và dữ liệu cấu hình.
- Không coi HTTP 200 là bằng chứng mọi instance đã hội tụ.

Kiểm thử Bus nhiều instance phải chứng minh được cả hai chiều: instance đúng đã nhận và áp dụng refresh, instance ngoài phạm vi không bị tác động. Service ID duy nhất giúp Bus phân biệt node; destination pattern giới hạn phạm vi event; broker vận chuyển sự kiện; Config Client fetch cấu hình và cập nhật bean theo vòng đời được hỗ trợ. Khi kiểm tra từng instance bằng release ID và đợi trạng thái hội tụ trong một timeout xác định, nhóm có thể tin cậy hơn vào việc refresh cấu hình có chọn lọc trong hệ thống Spring Boot chạy nhiều replica.

## Tài liệu tham khảo

- [Spring Cloud Bus – Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html)
- [Spring Cloud Bus – Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Bus – Quickstart](https://docs.spring.io/spring-cloud-bus/reference/quickstart.html)

