# Luồng Git push đến /monitor rồi phát sự kiện làm mới

Trong Spring Cloud Config, việc một commit mới xuất hiện trong Git không tự động làm các ứng dụng đang chạy nạp cấu hình mới. Config Client thường lấy cấu hình khi khởi động hoặc khi nhận một yêu cầu refresh. Webhook giúp tự động hóa bước thông báo: Git provider gửi HTTP POST đến endpoint /monitor của Config Server sau một sự kiện push; Config Server phân tích các file thay đổi và phát sự kiện refresh đến những client phù hợp thông qua Spring Cloud Bus.

Luồng này tách ba việc: Git lưu revision mới, webhook thông báo có thay đổi, còn Config Client lấy lại Environment và cập nhật các bean hỗ trợ refresh. Hiểu rõ từng bước giúp tránh nhầm lẫn giữa việc webhook đã được nhận, sự kiện đã được phát và ứng dụng đã thực sự áp dụng cấu hình mới.

## 1. Kiến trúc tổng thể

Một triển khai thường có Git provider, Config Server, message broker và nhiều Config Client:

~~~mermaid
flowchart LR
    G[Git repository] -->|push commit| P[Git provider]
    P -->|HTTP POST webhook| M[Config Server /monitor]
    M -->|phân tích file thay đổi| E[RefreshRemoteApplicationEvent]
    E --> B[Spring Cloud Bus]
    B --> Q[Message broker<br/>RabbitMQ / Kafka]
    Q --> O[orders-service clients]
    Q --> S[payment-service clients]
    O -->|fetch Environment mới| C[Config Server]
    S -->|fetch Environment mới| C
    C -->|Git backend đọc revision| G
~~~

Các thành phần có vai trò riêng:

- **Git repository** lưu file cấu hình. Commit tạo ra một revision mới.
- **Git provider** như GitHub, GitLab hoặc Bitbucket phát webhook khi có push hoặc sự kiện được chọn.
- **Config Server** nhận POST tại /monitor, đọc payload và xác định ứng dụng bị ảnh hưởng.
- **Spring Cloud Bus** chuyển sự kiện refresh qua broker đến các ứng dụng đã tham gia Bus.
- **Config Client** nhận sự kiện, nạp lại cấu hình từ Config Server và cập nhật Environment/bean hỗ trợ refresh.

Config Server là điểm nhận webhook. Các client không cần mở endpoint webhook ra Internet. Chúng cần kết nối được tới broker và Config Server theo luồng nội bộ.

## 2. Dependency cần có

Config Server cần dependency cho Git backend, monitor endpoint và Bus. Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-monitor</artifactId>
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

Mỗi Config Client tham gia Bus cần Config Client và Bus starter tương ứng. Ví dụ dùng RabbitMQ:

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

Nếu hệ thống dùng Kafka, thay Bus AMQP starter bằng Bus Kafka starter và cấu hình Kafka broker cho tất cả thành phần. Config Server và client phải dùng các phiên bản Spring Boot/Spring Cloud tương thích; nên quản lý dependency bằng Spring Cloud BOM của release train đang triển khai, không tự ghép các phiên bản khác dòng.

## 3. Cấu hình Config Server đọc Git và tham gia Bus

Ví dụ application.yml của Config Server:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
    bus:
      enabled: true
  rabbitmq:
    host: rabbitmq
    port: 5672
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ứng dụng server bật Config Server:

~~~java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Dependency spring-cloud-config-monitor đăng ký endpoint /monitor. Endpoint này thuộc Config Server, không phải endpoint Actuator /actuator/refresh. Vì vậy, không cần expose monitor trong danh sách Actuator endpoints; cần bảo vệ đường dẫn HTTP /monitor theo chính sách mạng và xác thực webhook.

Config Server cũng phải có quyền đọc Git repository. Nếu repository riêng tư, cấp credential bằng secret manager hoặc cơ chế bảo mật của nền tảng. Không lưu access token trong Git hoặc image.

## 4. Cấu hình Config Client tham gia Bus

Mỗi client cần import cấu hình từ Config Server và kết nối tới cùng broker:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
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
        include: health,info
~~~

Trong Docker Compose hoặc Kubernetes, config-server và rabbitmq phải là hostname có thể phân giải từ network của client. Không dùng localhost trừ khi các tiến trình thật sự cùng network namespace.

Client không cần expose /actuator/refresh hoặc /actuator/busrefresh để nhận sự kiện Bus. Các endpoint này chỉ cần khi muốn chủ động gọi refresh từ một công cụ vận hành. Client cần kết nối broker và có Bus listener hoạt động để nhận sự kiện được phát từ Config Server.

Nếu dùng Bus Kafka, phần cấu hình spring.kafka.bootstrap-servers và thông tin xác thực phải thay cho RabbitMQ. Tất cả thành phần phải cùng tham gia một Bus có thể trao đổi message.

## 5. Git push tạo webhook như thế nào?

Trong Git provider, tạo webhook trỏ đến URL có thể truy cập của Config Server:

~~~text
https://config.example.internal/monitor
~~~

Chọn sự kiện push vào repository cấu hình. Nên giới hạn branch được theo dõi, ví dụ chỉ branch main hoặc branch phát hành được kiểm soát. Nếu Config Server phục vụ nhiều môi trường hoặc nhiều label, cần xác định rõ branch nào có quyền kích hoạt refresh cho nhóm client nào.

Khi có commit mới, Git provider gửi POST request chứa payload mô tả repository, ref và các file được thêm, sửa hoặc xóa. Cấu trúc payload phụ thuộc provider. Ví dụ payload kiểu GitHub rút gọn:

~~~json
{
  "ref": "refs/heads/main",
  "commits": [
    {
      "added": ["orders-service-prod.yml"],
      "modified": [
        "application.yml",
        "payment-service-prod.yml"
      ],
      "removed": []
    }
  ],
  "repository": {
    "full_name": "platform/config-repo"
  }
}
~~~

Đây là ví dụ minh họa các trường file thay đổi; payload thực tế của provider còn nhiều trường khác. Config Monitor có bộ xử lý payload cho một số provider phổ biến, nhưng định dạng được hỗ trợ và cách ánh xạ có thể khác theo release. Hãy xác nhận provider và payload đang dùng tương thích với phiên bản spring-cloud-config-monitor; nếu không, cần một webhook adapter chuyển payload sang định dạng mà endpoint hỗ trợ.

Không gửi payload giả định từ một provider khác rồi kết luận endpoint hoạt động. Khi cấu hình webhook, hãy dùng tùy chọn test delivery của provider và xem status cùng log Config Server.

## 6. /monitor xác định ứng dụng cần refresh

Config Monitor phân tích các đường dẫn file trong payload để xác định ứng dụng bị ảnh hưởng. Với quy ước tên file Config Server phổ biến:

| File thay đổi trong repository | Phạm vi refresh thường được nhắm tới |
| --- | --- |
| orders-service.yml | orders-service |
| orders-service-prod.yml | orders-service |
| payment-service-prod.yml | payment-service |
| application.yml | Cấu hình dùng chung, có thể ảnh hưởng tất cả ứng dụng |
| application-prod.yml | Cấu hình chung cho profile prod, có thể ảnh hưởng nhiều ứng dụng |

Cơ chế ánh xạ dựa trên tên file cấu hình và payload provider; không nên coi bảng này là bộ lọc chính xác cho mọi kiểu repository. Với search-paths, thư mục lồng nhau hoặc quy ước file tùy chỉnh, hãy kiểm tra kết quả mapping của phiên bản đang chạy. Nếu repository có nhiều file có cùng tên ở các vùng khác nhau, một webhook có thể không đủ ngữ cảnh để phân biệt nếu adapter chỉ xét tên file.

Khi file chung như application.yml thay đổi, nhiều ứng dụng có thể cần refresh. Đây là lý do nên giới hạn thay đổi trong pull request và kiểm tra phạm vi ảnh hưởng trước khi merge. Nếu chỉ thay file của một ứng dụng, Config Monitor có thể gửi sự kiện nhắm tới ứng dụng đó thay vì tất cả client.

## 7. Từ /monitor đến RefreshRemoteApplicationEvent

Sau khi nhận payload hợp lệ, Config Monitor tạo sự kiện refresh từ xa cho các ứng dụng được xác định. Spring Cloud Bus dùng broker để chuyển sự kiện đến các instance phù hợp.

Luồng xử lý khái quát:

1. Git provider gửi webhook đến Config Server.
2. Endpoint /monitor nhận POST và phân tích file thay đổi.
3. Config Monitor xác định application hoặc phạm vi ứng dụng cần thông báo.
4. Config Server phát RefreshRemoteApplicationEvent qua Spring Cloud Bus.
5. Broker chuyển message đến các client đang tham gia Bus.
6. Client nhận event, làm mới Environment từ Config Server.
7. Spring Cloud Context cập nhật các bean hỗ trợ refresh; bean thuộc @RefreshScope được tạo lại khi được truy cập.

Webhook không mang toàn bộ cấu hình mới đến client. Nó là tín hiệu thông báo. Client vẫn phải kết nối Config Server để lấy Environment theo application, profile và label của chính nó.

Tương tự, việc Config Server trả response HTTP thành công cho webhook không đồng nghĩa mọi client đã refresh xong. Cần quan sát log, revision hoặc metric ở các client để xác nhận trạng thái áp dụng.

## 8. Ví dụ kiểm thử /monitor bằng curl

Trước khi nối Git provider, có thể kiểm tra đường dẫn endpoint và kết nối nội bộ bằng một payload tương thích với provider adapter của phiên bản đang dùng. Ví dụ minh họa:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  https://config.example.internal/monitor \
  --data-binary @github-push-payload.json
~~~

File github-push-payload.json cần chứa payload thực hoặc fixture hợp lệ của provider. Header event phải khớp loại sự kiện mà adapter nhận diện. Một JSON tùy ý có trường commits không đảm bảo được chấp nhận nếu thiếu cấu trúc mà parser cần.

Sau khi gửi, kiểm tra:

- HTTP status trả về từ Config Server.
- Log của Config Server cho biết payload được nhận và application nào bị ảnh hưởng.
- Log Bus cho thấy refresh event được phát.
- Log từng client cho biết event được nhận và quá trình refresh bắt đầu/kết thúc.
- Endpoint Environment của Config Server trả giá trị mới ở đúng label.

Có thể kiểm tra cấu hình mới trực tiếp:

~~~bash
curl https://config.example.internal/orders-service/prod/main
~~~

Không dùng response chứa secret làm artifact kiểm thử. Chỉ so sánh các key không nhạy cảm hoặc kiểm tra sự hiện diện của property source.

## 9. Phân biệt /monitor, refresh và busrefresh

Ba endpoint/cơ chế này có vai trò khác nhau:

| Cơ chế | Nơi nhận request | Tác dụng |
| --- | --- | --- |
| POST /monitor | Config Server | Nhận webhook từ Git provider, xác định ứng dụng thay đổi và phát refresh event |
| POST /actuator/refresh | Một Config Client | Yêu cầu chính instance đó nạp lại cấu hình |
| POST /actuator/busrefresh | Một ứng dụng tham gia Bus | Chủ động phát sự kiện refresh qua Bus |

Nếu đã dùng webhook /monitor, thường không cần gọi tiếp /actuator/busrefresh cho cùng một commit; Monitor đã là nguồn phát sự kiện. Gọi cả hai có thể tạo hai lượt refresh không cần thiết.

/actuator/refresh phù hợp để thử một instance hoặc xử lý thủ công. /actuator/busrefresh phù hợp khi operator muốn chủ động phát refresh mà không cần một webhook Git. Cả hai endpoint Actuator cần được expose và bảo vệ riêng nếu sử dụng.

## 10. Bảo vệ webhook và Config Server

Endpoint /monitor có thể kích hoạt nhiều ứng dụng nạp lại cấu hình, vì vậy không được để bất kỳ caller nào tùy ý gửi POST. Kẻ tấn công có thể gây refresh liên tục, làm tăng tải Git/broker hoặc khiến các instance liên tục thay đổi cấu hình.

Các biện pháp bảo vệ:

- Dùng HTTPS cho webhook delivery.
- Xác minh chữ ký webhook theo cơ chế của Git provider, ví dụ HMAC signature header; không giả định Config Monitor tự xác minh chữ ký nếu chưa xác nhận ở phiên bản đang dùng.
- Có thể xác minh chữ ký tại reverse proxy, API gateway hoặc custom security filter trước khi request đến /monitor.
- Giới hạn repository, branch và loại event được phép kích hoạt.
- Dùng allowlist mạng/IP như một lớp bổ sung, không thay thế xác minh chữ ký.
- Giới hạn kích thước payload, request rate và timeout.
- Ghi audit repository, ref, commit và kết quả xử lý; không ghi token hoặc secret.
- Đặt Config Server và broker trong mạng riêng, hạn chế truy cập từ bên ngoài.
- Bảo vệ endpoint Actuator refresh và busrefresh bằng xác thực/phân quyền riêng.

Nếu Git provider có webhook secret, lưu secret trong secret manager và so sánh chữ ký theo đúng thuật toán, encoding và header của provider. So sánh chữ ký phải dùng dữ liệu request body nguyên gốc trước khi parse; không tự xây dựng HMAC trên JSON đã serialize lại vì thứ tự field hoặc whitespace có thể thay đổi.

## 11. Retry, duplicate delivery và sự kiện sai thứ tự

Webhook provider thường có thể retry khi không nhận được response thành công. Một commit cũng có thể tạo nhiều lần delivery do cấu hình event hoặc thao tác retry thủ công. Vì vậy, pipeline refresh nên chịu được duplicate event.

Các nguyên tắc:

- Không giả định mỗi push chỉ đến một lần.
- Ghi nhận delivery ID hoặc commit SHA để phục vụ idempotency và audit.
- Hạn chế refresh trùng lặp trong một khoảng ngắn nếu có thể mà không làm mất thay đổi mới hơn.
- Khi sự kiện đến sai thứ tự, client nên lấy cấu hình từ label/revision hiện tại theo chính sách phát hành, không áp dụng nội dung payload như một bản patch.
- Nếu webhook bị trễ, lần fetch tiếp theo phải lấy đúng revision mà deployment đang nhắm tới.

Webhook chỉ là thông báo rằng repository có thay đổi. Client không nên áp dụng trực tiếp danh sách file trong payload làm cấu hình runtime; Config Server mới là nguồn trả Environment theo application/profile/label.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Git provider nhận HTTP 404 | Thiếu dependency monitor hoặc sai base path | Kiểm tra spring-cloud-config-monitor và URL /monitor |
| HTTP 401/403 | Security filter từ chối webhook hoặc chữ ký không hợp lệ | Kiểm tra gateway, credential và signature verification |
| /monitor nhận request nhưng không có client refresh | Thiếu Bus dependency hoặc Config Server không kết nối broker | Kiểm tra Bus starter, broker và log server |
| Chỉ một số client refresh | Application mapping, destination hoặc client không kết nối Bus | Kiểm tra tên file, application name và log từng instance |
| Tất cả client refresh dù chỉ đổi một service | Payload không xác định được file hoặc file chung bị thay đổi | Kiểm tra danh sách added/modified/removed |
| Client refresh nhưng vẫn nhận giá trị cũ | Config Server chưa đọc revision mới, sai label hoặc cache/fetch policy | Kiểm tra endpoint Environment và Git revision |
| Webhook thành công nhưng bean không đổi | Bean không hỗ trợ refresh hoặc giữ state cũ | Kiểm tra @RefreshScope, rebind và vòng đời bean |
| Refresh lặp lại nhiều lần | Provider retry hoặc duplicate delivery | Dùng delivery ID, commit SHA và log correlation |
| Payload provider không được parse | Định dạng event không được adapter phiên bản hiện tại hỗ trợ | Kiểm tra payload fixture và phiên bản monitor |

Khi chẩn đoán, đi theo thứ tự từ ngoài vào trong:

1. Xác nhận Git provider đã gửi đúng URL, branch và event.
2. Xác nhận /monitor nhận request và parse được file thay đổi.
3. Xác nhận Config Server phát event lên Bus.
4. Xác nhận broker chuyển message và các client nhận event.
5. Xác nhận client gọi lại Config Server với application/profile/label đúng.
6. Xác nhận bean hoặc component runtime thực sự dùng giá trị mới.

Cách kiểm tra theo từng chặng giúp tránh kết luận nhầm rằng webhook thành công đồng nghĩa ứng dụng đã thay đổi.

## 13. Quy trình rollout cấu hình qua webhook

Một quy trình an toàn cho repository cấu hình có thể thực hiện như sau:

1. Developer tạo pull request và thay đổi file cấu hình.
2. CI kiểm tra cú pháp YAML/properties, schema và giá trị bắt buộc.
3. Reviewer đánh giá phạm vi ảnh hưởng theo application/profile.
4. Thay đổi được merge vào branch được phép phát hành.
5. Git provider gửi webhook đến /monitor.
6. Config Server phân tích payload và phát refresh event.
7. Bus chuyển event đến các client phù hợp.
8. Client nạp lại Environment và validate cấu hình.
9. Theo dõi revision, log, metric và lỗi sau refresh.
10. Nếu có lỗi, revert commit hoặc chọn lại label đã phê duyệt rồi kích hoạt refresh/rollout theo quy trình.

Với thay đổi ảnh hưởng nhiều service như application.yml, nên rollout theo nhóm hoặc dùng destination có kiểm soát nếu kiến trúc và phiên bản hỗ trợ. Đừng thay đổi hàng loạt timeout, retry hoặc connection pool mà không đánh giá tác động tải.

## 14. Nguyên tắc vận hành

- Coi webhook là tín hiệu thông báo; Config Server vẫn là nơi cung cấp Environment.
- Chỉ theo dõi branch và event được phê duyệt.
- Cài spring-cloud-config-monitor trên Config Server và Bus starter trên server/client.
- Bảo đảm mọi client tham gia cùng broker và có thể truy cập Config Server.
- Kiểm tra mapping từ file thay đổi sang application, nhất là với file chung và search path lồng nhau.
- Xác minh webhook signature trước khi cho phép gọi /monitor.
- Thiết kế retry và xử lý duplicate delivery có thể audit.
- Theo dõi từng instance cho đến khi xác nhận revision mới đã được áp dụng.
- Có quy trình rollback bằng Git revert hoặc label đã phê duyệt.
- Bảo vệ /monitor, Actuator, broker credential và API cấu hình.

Luồng Git push đến /monitor giúp tự động thông báo thay đổi cấu hình mà không cần người vận hành gọi refresh từng client. Git provider mô tả thay đổi, Config Server chuyển thông tin đó thành sự kiện, Spring Cloud Bus phân phối đến các ứng dụng và mỗi Config Client lấy lại Environment theo application/profile/label của mình. Khi bảo vệ webhook, kiểm soát phạm vi refresh và theo dõi kết quả trên từng instance, cấu hình tập trung có thể được cập nhật nhanh mà vẫn giữ khả năng truy vết và rollback.

