# Tích hợp GitHub hoặc GitLab và xác minh webhook theo phiên bản

Khi cấu hình trong Git thay đổi, Spring Cloud Config Server có thể nhận webhook từ GitHub hoặc GitLab để thông báo cho các ứng dụng cần refresh. Webhook giúp tự động hóa bước phát hiện commit mới, nhưng bản thân request HTTP chỉ là tín hiệu: Config Server phải phân tích payload, xác định ứng dụng bị ảnh hưởng, chuyển sự kiện qua Spring Cloud Bus hoặc gửi HTTP refresh đến client, và bảo vệ endpoint khỏi request giả mạo.

Việc tích hợp cần được kiểm tra theo đúng phiên bản Spring Cloud Config đang chạy. Cách bật `/monitor` có từ các phiên bản trước, nhưng cơ chế xác minh secret và các lựa chọn notifier đã thay đổi. Đặc biệt, những bản cũ có lỗ hổng xác thực webhook đã được Spring công bố trong năm 2026. Không nên lấy cấu hình từ tài liệu phiên bản mới rồi áp dụng cho một server cũ mà không kiểm tra release và security advisory.

## 1. Luồng webhook từ Git đến ứng dụng

Một luồng cơ bản gồm các bước:

```text
Developer push commit
        |
        v
GitHub / GitLab tạo webhook delivery
        |
        v
POST https://config.example.com/monitor
        |
        v
Config Server xác minh secret/signature
        |
        v
spring-cloud-config-monitor phân tích payload
        |
        v
Tìm file cấu hình đã thay đổi
        |
        v
Ánh xạ file sang application cần refresh
        |
        v
Spring Cloud Bus hoặc HTTP notifier
        |
        v
Config Client refresh Environment và bean phù hợp
```

Webhook không thay thế Git backend. Commit phải được push vào repository mà Config Server đọc. Webhook chỉ thông báo rằng có thay đổi; Config Server và client vẫn phải lấy được nội dung commit mới. Nếu Config Server chưa fetch commit, client có thể refresh nhưng nhận lại cấu hình cũ.

## 2. Thành phần cần có ở Config Server

Config Server cần dependency `spring-cloud-config-monitor` để xử lý webhook. Ví dụ Maven, không khai báo version riêng nếu dự án đang quản lý Spring Cloud bằng BOM:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-monitor</artifactId>
</dependency>
```

Ứng dụng Config Server vẫn cần bật `@EnableConfigServer` và cấu hình backend Git như thông thường. Khi tích hợp với Spring Cloud Bus, thêm một binder tương ứng, ví dụ RabbitMQ:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-amqp</artifactId>
</dependency>
```

Hoặc dùng Kafka nếu hệ thống đang vận hành Kafka:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-kafka</artifactId>
</dependency>
```

Các ứng dụng Config Client cũng phải tham gia Bus nếu muốn nhận `RefreshRemoteApplicationEvent` qua broker. Có Bus ở Config Server nhưng thiếu Bus ở client thì sự kiện không được truyền tới client theo cơ chế Bus.

Trong các phiên bản hiện hành có hỗ trợ HTTP property-path notifier, Config Server có thể gửi HTTP refresh trực tiếp đến từng client khi Bus không có. Cơ chế này cần `DiscoveryClient` trên classpath và các client phải expose endpoint refresh phù hợp. Phần lựa chọn notifier được trình bày ở mục 7; không mặc định rằng mọi phiên bản cũ đều có hành vi này.

## 3. Endpoint `/monitor` và định tuyến

Webhook mặc định gửi HTTP `POST` đến:

```text
https://config.example.com/monitor
```

Nếu Config Server được triển khai dưới context path, Config Server prefix hoặc reverse proxy prefix, URL webhook phải chứa đúng các phần đường dẫn đó. Ví dụ server dùng context path `/platform`, endpoint công khai có thể là `/platform/monitor`.

Đường dẫn phải truy cập được từ hạ tầng webhook của nhà cung cấp Git. Nếu Config Server chỉ nằm trong private network, cần một ingress/gateway có kiểm soát để nhận webhook và chuyển tiếp request đến server. Không mở toàn bộ API Config Server ra Internet chỉ để nhận một endpoint notification.

## 4. Cấu hình webhook trên GitHub

Trong repository GitHub chứa cấu hình:

1. Mở **Settings → Webhooks → Add webhook**.
2. Đặt Payload URL là `https://config.example.com/monitor`.
3. Chọn content type `application/json`.
4. Nhập một secret ngẫu nhiên có entropy cao vào trường Secret.
5. Chọn sự kiện `Just the push event` nếu chỉ cần refresh khi commit được push.
6. Lưu webhook và dùng Recent Deliveries để kiểm tra request/response.

GitHub gửi `POST` với JSON payload chứa thông tin repository và danh sách commit. Header `X-GitHub-Event` cho biết loại event; với push event, giá trị là `push`. Payload push chứa các danh sách file được thêm, sửa hoặc xóa trong từng commit. Spring Cloud Config dùng thông tin đường dẫn này để xác định application cần refresh.

GitHub ký raw request body bằng HMAC-SHA256. Chữ ký được gửi trong header:

```text
X-Hub-Signature-256: sha256=<hex-digest>
```

Config Server phiên bản có webhook secret validation hỗ trợ thuộc tính:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          github:
            webhook-secret: ${CONFIG_GITHUB_WEBHOOK_SECRET}
```

`CONFIG_GITHUB_WEBHOOK_SECRET` phải là cùng secret đã nhập trong cài đặt webhook GitHub. Đưa giá trị vào secret manager hoặc biến môi trường của nền tảng triển khai; không commit secret vào repository cấu hình.

Chữ ký được tính trên raw body. Nếu một reverse proxy hoặc middleware đọc rồi serialize lại JSON trước khi chuyển tiếp, byte của body có thể thay đổi và chữ ký không còn hợp lệ. Hãy giữ nguyên request body và các header xác minh khi proxy chuyển tiếp.

## 5. Cấu hình webhook trên GitLab

Trong GitLab project hoặc group chứa cấu hình:

1. Mở **Settings → Webhooks**.
2. Nhập URL `https://config.example.com/monitor`.
3. Cấu hình Secret token theo cơ chế tương thích mà Config Server đang dùng.
4. Bật `Push events`; chỉ bật các event khác nếu đã xác định rõ cách xử lý.
5. Lưu webhook và dùng nút Test để gửi một Push Hook.
6. Kiểm tra Recent events để xem request, response, status và thời gian phản hồi.

GitLab gửi header event:

```text
X-Gitlab-Event: Push Hook
```

Với Secret token kiểu truyền thống, GitLab gửi giá trị token trong:

```text
X-Gitlab-Token: <secret-token>
```

Config Server có hỗ trợ webhook secret validation dùng thuộc tính:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          gitlab:
            webhook-secret: ${CONFIG_GITLAB_WEBHOOK_SECRET}
```

Biến `CONFIG_GITLAB_WEBHOOK_SECRET` phải trùng với Secret token được cấu hình cho webhook. Đây là cách xác minh GitLab được tài liệu Spring Cloud Config hiện hành mô tả.

### Lưu ý GitLab 19.0 trở lên: signing token

GitLab 19.0 giới thiệu signing token theo chuẩn Standard Webhooks. Khi dùng signing token, GitLab gửi các header `webhook-id`, `webhook-timestamp` và `webhook-signature`; chữ ký HMAC-SHA256 được tính trên chuỗi gồm message ID, timestamp và raw body. Cơ chế này mạnh hơn Secret token truyền thẳng trong `X-Gitlab-Token`.

Tuy nhiên, bảng xác minh webhook của Spring Cloud Config 5.0.x/5.1.x hiện mô tả GitLab bằng `X-Gitlab-Token`, không liệt kê `webhook-signature` như một cơ chế xác minh tích hợp. Vì vậy, không giả định chỉ bật GitLab signing token là Config Server có thể xác minh request.

Nếu cần tương thích trực tiếp với Config Server built-in validator, giữ Secret token để GitLab gửi `X-Gitlab-Token` và cấu hình `gitlab.webhook-secret` ở Config Server. GitLab cho phép dùng signing token song song với Secret token trong giai đoạn chuyển đổi, nhưng Config Server vẫn xác minh theo header `X-Gitlab-Token` được hỗ trợ. Nếu chính sách bảo mật yêu cầu chỉ dùng Standard Webhooks signing token, cần một gateway/receiver riêng xác minh `webhook-signature` trước khi chuyển tiếp notification đến Config Server, hoặc một integration đã được xác nhận hỗ trợ cơ chế đó.

## 6. Config Server xác định ứng dụng nào cần refresh?

`spring-cloud-config-monitor` dùng một `PropertyPathNotificationExtractor` để chuyển header và payload thành danh sách đường dẫn file đã thay đổi. Extractor mặc định hỗ trợ payload của GitHub, GitLab và một số nhà cung cấp khác. Nó không refresh mọi ứng dụng một cách vô điều kiện; Config Server so khớp đường dẫn với tên application.

Ví dụ:

| File thay đổi trong Git | Ứng dụng được nhắm tới |
|---|---|
| `order-service.yml` | `order-service` |
| `order-service-prod.yml` | `order-service` |
| `inventory-service-prod.yml` | `inventory-service` |
| `application.yml` | Tất cả ứng dụng |

Các file theo tên ứng dụng giúp giới hạn phạm vi refresh. File `application.*` là cấu hình dùng chung; thay đổi nó có thể ảnh hưởng nhiều ứng dụng và dẫn đến broadcast rộng hơn.

Nếu repository có cấu trúc thư mục hoặc quy tắc đặt tên riêng, hãy kiểm tra đường dẫn thực tế mà webhook gửi. Có thể tùy biến `PropertyPathNotificationExtractor` khi payload hoặc quy tắc ánh xạ không phù hợp. Interface nhận HTTP headers và payload, sau đó trả về danh sách đường dẫn thay đổi; việc tùy biến extractor phải đi kèm kiểm thử cho GitHub/GitLab payload thực tế.

### Bỏ qua những file không cần refresh

Có thể loại trừ các đường dẫn không phải cấu hình bằng regular expression:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          ignored-paths:
            - "docs/.*"
            - "scripts/.*"
            - "\.github/.*"
```

Mỗi biểu thức được so khớp với toàn bộ đường dẫn webhook. Các đường dẫn bị bỏ qua sẽ không tham gia bước xác định application cần refresh.

Config Server xử lý tối đa 20 path trong một notification theo mặc định. Có thể tăng giới hạn bằng:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          max-paths: 50
```

Nếu payload có nhiều đường dẫn hơn giới hạn, các path còn lại không được xử lý và server ghi warning. Đặt giới hạn theo kích thước thay đổi thực tế để tránh payload lớn gây quá tải.

## 7. Từ webhook đến client: Spring Cloud Bus hoặc HTTP notifier

### Cách A: Spring Cloud Bus

Khi Spring Cloud Bus được kích hoạt ở cả Config Server và các Config Client, monitor gửi `RefreshRemoteApplicationEvent` đến các ứng dụng được nhắm mục tiêu. Broker có thể là RabbitMQ hoặc Kafka tùy binder.

Luồng:

```text
GitHub/GitLab webhook
        |
        v
Config Server /monitor
        |
        v
PropertyPathNotificationExtractor
        |
        v
RefreshRemoteApplicationEvent
        |
        v
RabbitMQ / Kafka
        |
        v
Các Config Client nhận event
        |
        v
Refresh Environment / bean hỗ trợ refresh
```

Để Bus hoạt động, cần:

- `spring-cloud-config-monitor` ở Config Server.
- Bus starter và cấu hình broker ở Config Server.
- Bus starter và cấu hình cùng broker ở các client cần nhận event.
- Mạng, credential và topology broker cho phép server/client publish và subscribe.
- ID/destination của ứng dụng được thiết lập phù hợp nếu cần giới hạn event theo service.

Nếu Bus chỉ có ở Config Server hoặc chỉ có ở client, event không thể đi hết tuyến. Webhook có thể đã được nhận nhưng ứng dụng không refresh.

### Cách B: HTTP property-path notifier

Tài liệu Spring Cloud Config 5.1.0 mô tả HTTP notifier được dùng tự động khi Spring Cloud Bus không khả dụng. Notifier tìm các instance ứng dụng qua `DiscoveryClient` rồi gửi `POST` tới refresh endpoint của từng instance. Cần có Discovery Client implementation trên classpath và client phải expose endpoint tương ứng.

Endpoint mặc định là:

```text
/actuator/refresh
```

Có thể cấu hình endpoint theo application:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          http:
            endpoints:
              orders: /management/refresh
              inventory: /actuator/custom-refresh
```

Hoặc cung cấp metadata `refresh-endpoint` trên `ServiceInstance`. Cấu hình endpoint riêng theo application có ưu tiên cao hơn metadata của instance. Các client đích phải expose endpoint được chọn và bảo vệ nó bằng xác thực/phân quyền.

HTTP notifier này được mô tả trong tài liệu 5.1.0; không suy ra rằng release cũ có cùng hành vi chỉ vì nó có `/monitor`. Với 4.3.x hoặc 5.0.x, kiểm tra tài liệu đúng minor version và dependency graph trước khi thiết kế không dùng Bus.

## 8. Webhook không đồng nghĩa với Git fetch đã hoàn tất

Khi Config Server nhận notification, nó xác định repository và application bị ảnh hưởng. Trong tài liệu 5.1.0, nếu payload có URL repository khớp với Git URI đã cấu hình, Config Server có thể expire `refresh-rate` của repository đó để request cấu hình tiếp theo fetch commit mới ngay, không phải chờ hết khoảng refresh.

Việc khớp repository URL được thực hiện theo host và repository path; giao thức, credential, SSH username và port không quyết định kết quả khớp trong mô tả hiện hành. Payload GitHub thường có `repository.clone_url` hoặc `repository.ssh_url`; GitLab có `project.git_http_url` hoặc `project.git_ssh_url`.

Với các phiên bản không có cơ chế expire refresh interval theo notification, hành vi cập nhật Git phụ thuộc cấu hình `spring.cloud.config.server.git.refreshRate` và cách repository được fetch. Nếu `refreshRate` lớn hơn 0, có thể có khoảng trễ trước khi commit mới xuất hiện trong response Config Server. Đừng đánh đồng việc webhook trả thành công với việc client chắc chắn đã nhận đúng commit mới.

## 9. Xác minh webhook secret và bảo vệ `/monitor`

Endpoint `/monitor` có thể kích hoạt refresh cấu hình. Nếu người ngoài gọi được endpoint mà không có xác minh, họ có thể tạo refresh giả, gây tải lên broker/client hoặc kích hoạt đọc cấu hình ngoài kế hoạch. Vì vậy cần xác minh webhook ở lớp nhận request, dùng TLS và giới hạn đường truy cập.

Trong các phiên bản Spring Cloud Config có webhook secret validation, cơ chế tích hợp được mô tả như sau:

| Provider | Cách xác minh | Header | Thuộc tính Config Server |
|---|---|---|---|
| GitHub | HMAC-SHA256 trên raw request body | `X-Hub-Signature-256: sha256=<hex>` | `spring.cloud.config.server.monitor.github.webhook-secret` |
| GitLab | So khớp secret token dạng plain text | `X-Gitlab-Token` | `spring.cloud.config.server.monitor.gitlab.webhook-secret` |

Ví dụ khai báo cả hai secret qua biến môi trường:

```yaml
spring:
  cloud:
    config:
      server:
        monitor:
          github:
            webhook-secret: ${CONFIG_GITHUB_WEBHOOK_SECRET}
          gitlab:
            webhook-secret: ${CONFIG_GITLAB_WEBHOOK_SECRET}
```

Nếu không cấu hình bất kỳ webhook secret nào, các phiên bản có validation filter được bật mặc định sẽ từ chối incoming webhook. Hãy cấu hình secret cho từng provider mà server cần chấp nhận. Khi secret không hợp lệ hoặc thiếu, endpoint trả `403 Forbidden`.

Không tắt validation toàn cục trong production. Thuộc tính `validation-filter-enabled: false` có thể vô hiệu hóa filter; `validation-enabled: false` có thể tắt validation cho một provider nhưng vẫn xử lý event; `enabled: false` tắt hẳn tích hợp provider. Những tùy chọn này chỉ phù hợp cho tình huống kiểm thử có kiểm soát hoặc khi một lớp gateway khác đã xác minh request và có thiết kế bảo mật được review.

Ngoài secret validation:

- Chỉ mở endpoint webhook qua HTTPS.
- Giới hạn mạng nguồn tại ingress/firewall khi có thể, nhưng không dùng IP allowlist thay cho chữ ký/secret.
- Đặt giới hạn kích thước request body và rate limit phù hợp.
- Không ghi `X-Gitlab-Token`, chữ ký hoặc raw payload nhạy cảm vào log.
- Tách quyền truy cập `/monitor` khỏi API đọc cấu hình và endpoint Actuator.
- Theo dõi số lần delivery, mã HTTP, latency và refresh event được phát ra.
- Thiết kế xử lý lặp an toàn; webhook có thể được gửi lại khi provider timeout hoặc người vận hành bấm redeliver.

## 10. Xác minh phiên bản và các bản vá bảo mật

Webhook secret validation không xuất hiện trong tài liệu của mọi release. Ví dụ tài liệu Spring Cloud Config 4.3.4 mô tả `/monitor` và Bus nhưng chưa liệt kê webhook secret validation. Tài liệu 5.0.7 và 5.1.0 có mục Webhook Secret Validation với các thuộc tính GitHub/GitLab nêu ở trên.

Spring công bố CVE-2026-47837 về việc webhook request đến `/monitor` không được xác minh. Advisory liệt kê các dải bị ảnh hưởng và bản sửa như sau:

| Nhánh Spring Cloud Config | Phiên bản bị ảnh hưởng | Bản sửa được advisory nêu |
|---|---|---|
| 5.0.x | 5.0.0 đến 5.0.4 | 5.0.5 (OSS) |
| 4.3.x | 4.3.0 đến 4.3.4 | 4.3.5 (Enterprise Support Only) |
| 4.0.x đến 4.2.x | 4.0.0 đến 4.2.8 | 4.2.9 (Enterprise Support Only) |
| 3.1.x | 3.1.14 và các bản trước đó | 3.1.15 (Enterprise Support Only) |

Advisory CVE-2026-59315 cũng nêu các dải phiên bản trên bị ảnh hưởng bởi lỗi từ chối dịch vụ qua monitor payload và các bản sửa tương ứng. Với bản OSS, ưu tiên nâng lên một release đã được sửa trong nhánh được hỗ trợ; tại thời điểm tài liệu được tra cứu, Spring Cloud Config 5.0.7 và 5.1.0 có tài liệu webhook validation. Với nhánh enterprise, làm theo ma trận hỗ trợ và bản vá được nhà cung cấp cấp.

Không chỉ kiểm tra version của `spring-cloud-config-server`. Hãy kiểm tra version thực tế của `spring-cloud-config-monitor` trong dependency tree/runtime classpath; tránh trường hợp server và monitor kéo về các version không đồng bộ. Dùng Spring Cloud BOM tương thích với Spring Boot của dự án, không override riêng một module mà không kiểm tra release train.

Sau khi nâng cấp, xác nhận bằng các test âm/dương:

- Webhook GitHub có secret đúng được chấp nhận.
- GitHub thiếu hoặc sai `X-Hub-Signature-256` bị từ chối.
- GitLab có `X-Gitlab-Token` đúng được chấp nhận.
- GitLab thiếu hoặc sai token bị từ chối.
- Payload không được xác thực không tạo refresh event.
- Provider và server dùng cùng secret sau khi secret được rotate.

## 11. Kiểm tra delivery và kết quả refresh

### Kiểm tra từ GitHub

Trong **Settings → Webhooks → Recent Deliveries**:

1. Chọn một delivery có event `push`.
2. Xác nhận URL và HTTP method là `POST`.
3. Xem request headers có `X-GitHub-Event: push` và `X-Hub-Signature-256`.
4. Kiểm tra response status và body của Config Server.
5. Nếu thất bại, dùng Redeliver sau khi sửa endpoint/secret.

### Kiểm tra từ GitLab

Trong **Settings → Webhooks → Recent events**:

1. Chọn delivery Push Hook.
2. Kiểm tra `X-Gitlab-Event` và `X-Gitlab-Token` nếu đang dùng Secret token.
3. Xem request/response details và HTTP status.
4. Dùng Test → Push events để gửi lại một event thử nghiệm.
5. Kiểm tra webhook không bị tự động disable do nhiều lần lỗi liên tiếp.

### Kiểm tra ở Config Server và client

Theo dõi log Config Server để xác nhận request vào `/monitor`, extractor nhận diện đường dẫn, application được nhắm mục tiêu và notifier được gọi. Nếu dùng Bus, kiểm tra broker publish/subscribe và log nhận `RefreshRemoteApplicationEvent` ở client. Nếu dùng HTTP notifier, kiểm tra DiscoveryClient tìm thấy instance và refresh endpoint của client trả response thành công.

Cuối cùng, truy vấn Config Server Environment API và Actuator `env`/`configprops` trên client để xác nhận giá trị đã thay đổi. Webhook HTTP 2xx chỉ chứng minh endpoint đã nhận/xử lý request; nó không tự chứng minh mọi bean trong ứng dụng đã được refresh thành công.

## 12. Mã lỗi thường gặp

| Kết quả | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `2xx` nhưng client chưa đổi cấu hình | Webhook được nhận nhưng Bus/client notifier chưa chạy, Git chưa fetch commit mới hoặc bean không hỗ trợ refresh | Kiểm tra log monitor, broker/DiscoveryClient, Git refresh và giá trị ở client |
| `403 Forbidden` | Thiếu/sai webhook secret hoặc chữ ký/token không khớp | So sánh secret ở provider và Config Server; kiểm tra raw body proxy có bị thay đổi không |
| `404 Not Found` | Sai URL, context path, Config Server prefix hoặc route proxy | Gọi đúng `/monitor` qua đường dẫn công khai và kiểm tra rewrite |
| `400 Bad Request` | Payload/event không đúng định dạng mà extractor hỗ trợ | Xem event type, content type và payload; kiểm tra extractor/version |
| `5xx` | Lỗi xử lý monitor, broker, Git backend hoặc notifier | Đối chiếu stack trace, Git URI, broker và client endpoint |
| Timeout | Config Server/gateway phản hồi chậm hoặc backend quá tải | Đưa xử lý nặng sang async nếu có custom receiver; kiểm tra Git fetch và broker |
| Một số ứng dụng refresh, số khác không | File path không khớp application hoặc bị ignored-paths loại bỏ | Kiểm tra danh sách path và quy tắc ánh xạ |
| GitLab tự disable webhook | Nhiều delivery liên tiếp trả lỗi hoặc timeout | Sửa endpoint, secret, TLS và phản hồi nhanh; gửi test để bật lại |

## 13. Checklist triển khai production

| Kiểm tra | Điều kiện đạt |
|---|---|
| Phiên bản | Config Server và config-monitor dùng bản đã vá; BOM và Spring Boot tương thích |
| Dependency | Có `spring-cloud-config-monitor`; Bus binder hoặc DiscoveryClient phù hợp với notifier đã chọn |
| URL | Webhook trỏ đúng HTTPS URL, context path/prefix và ingress route |
| Event | Chỉ bật Push events nếu mục tiêu là thay đổi commit cấu hình |
| Secret | GitHub HMAC hoặc GitLab token được cấu hình khớp với provider |
| GitLab signing token | Đã xác nhận cơ chế header tương thích; không giả định `webhook-signature` được built-in validator hỗ trợ |
| Payload | Extractor nhận diện đúng đường dẫn file thay đổi và application đích |
| Scope | `ignored-paths` và `max-paths` phù hợp với cấu trúc repository |
| Notifier | Bus có ở server/client hoặc HTTP notifier có DiscoveryClient và refresh endpoint |
| Git freshness | Config Server fetch được commit mới; refresh-rate không làm client nhận cấu hình cũ ngoài dự kiến |
| Security | `/monitor` được xác minh secret, giới hạn mạng, TLS, rate limit và log được làm sạch |
| Observability | Có delivery history, request ID, log monitor, Bus/notifier metrics và kiểm tra giá trị client |
| Recovery | Có hướng dẫn rotate secret, redeliver webhook và rollback commit cấu hình |

## 14. Nguyên tắc cần ghi nhớ

- `spring-cloud-config-monitor` cung cấp khả năng nhận notification tại `/monitor`; webhook thường là HTTP `POST`.
- GitHub push dùng `X-GitHub-Event: push`; GitLab push dùng `X-Gitlab-Event: Push Hook`.
- Mặc định extractor dùng đường dẫn file thay đổi để xác định application; file `application.*` có thể tác động tới mọi ứng dụng.
- `ignored-paths` loại trừ file không cần refresh; `max-paths` mặc định xử lý tối đa 20 path mỗi notification.
- `RefreshRemoteApplicationEvent` qua Bus cần Bus ở cả Config Server và Config Client.
- HTTP property-path notifier được tài liệu 5.1.0 mô tả khi Bus không khả dụng; nó cần DiscoveryClient và refresh endpoint ở client.
- GitHub dùng HMAC-SHA256 trong `X-Hub-Signature-256`; GitLab built-in validation của Config Server dùng `X-Gitlab-Token`.
- Không giả định GitLab Standard Webhooks signing token mới được built-in validator hỗ trợ nếu tài liệu release chưa liệt kê header đó.
- Nâng cấp khỏi các phiên bản bị ảnh hưởng CVE-2026-47837 và CVE-2026-59315; kiểm tra đúng artifact `spring-cloud-config-monitor`.
- Webhook 2xx không bảo đảm bean đã đổi giá trị; xác minh cả Git fetch, event delivery và Environment/bean ở client.

Webhook biến một commit cấu hình thành tín hiệu refresh tự động. Tích hợp đáng tin cậy cần đồng thời đúng endpoint, payload extractor, notifier, Git freshness và xác minh danh tính của provider. Hãy kiểm tra theo đúng phiên bản Spring Cloud Config và GitLab/GitHub đang chạy; đây là cách tránh một webhook trông có vẻ hoạt động nhưng thực tế không refresh, hoặc một endpoint monitor nhận được request giả mạo.

## Tài liệu tham khảo

- [Spring Cloud Config 5.1 — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html)
- [Spring Cloud Config 5.0 — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/5.0/server/push-notifications-and-bus.html)
- [Spring Cloud Config 4.3 — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/4.3/server/push-notifications-and-bus.html)
- [Spring Security Advisory CVE-2026-47837 — Monitor endpoint webhook validation](https://spring.io/security/cve-2026-47837/)
- [Spring Security Advisory CVE-2026-59315 — Config Monitor denial of service](https://spring.io/security/cve-2026-59315/)
- [GitHub Docs — Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [GitHub Docs — Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [GitLab Docs — Webhooks and signing tokens](https://docs.gitlab.com/user/project/integrations/webhooks/)
