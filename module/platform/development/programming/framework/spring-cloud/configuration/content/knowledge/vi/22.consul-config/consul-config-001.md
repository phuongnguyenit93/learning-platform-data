# Nạp cấu hình từ Consul KV bằng `spring.config.import`

Spring Cloud Consul Config cho phép ứng dụng Spring Boot đọc cấu hình trực tiếp từ Consul Key/Value Store (KV) và đưa các giá trị đó vào Spring `Environment`. Ứng dụng dùng `spring.config.import` để khai báo Consul là một nguồn Config Data; Spring Cloud Consul tự tìm các context theo tên ứng dụng và profile, tạo các `PropertySource`, rồi áp dụng chúng theo thứ tự ưu tiên.

Mô hình này giúp nhiều ứng dụng dùng chung cấu hình nền trong Consul và ghi đè bằng cấu hình riêng theo application/profile. Không cần triển khai một Spring Cloud Config Server riêng: mỗi Config Client kết nối tới Consul Agent/API để đọc KV. Đổi lại, Consul trở thành dependency trực tiếp trong quá trình khởi động và cập nhật cấu hình của từng ứng dụng.

## 1. Consul KV và Spring Cloud Consul Config

Consul KV là kho lưu trữ key/value có thể dùng cho cấu hình và metadata. Consul lưu dữ liệu trên các server trong cluster; Consul Agent cung cấp API để client truy cập. Spring Cloud Consul dùng HTTP API của Consul để đọc các key theo prefix và chuyển chúng thành property source trong Spring. Mỗi datacenter có KV store riêng; Consul không tự nhân bản KV giữa các datacenter, vì vậy cần có kế hoạch đồng bộ nếu ứng dụng đọc cấu hình từ nhiều DC.

Các thành phần chính:

- **Consul Server cluster:** lưu trữ dữ liệu KV và đồng bộ trạng thái trong cùng datacenter.
- **Consul Agent:** endpoint mà ứng dụng Spring Cloud Consul kết nối; mặc định là `localhost:8500`.
- **Consul KV:** nơi lưu các key và value cấu hình.
- **Spring Cloud Consul Config:** starter và auto-configuration đọc KV, xác định context theo application/profile và thêm property source vào Environment.
- **Spring Boot Config Data:** cơ chế nạp nguồn cấu hình qua `spring.config.import`.

Spring Cloud Consul Config là một cách nạp cấu hình tập trung thay thế mô hình Config Server/Client. Ứng dụng đọc trực tiếp từ Consul; Consul không tự cung cấp toàn bộ chức năng quản trị Git, label, API Environment và phân phối cấu hình của Spring Cloud Config Server.

## 2. Thêm dependency

Trong ứng dụng Config Client, thêm starter `spring-cloud-starter-consul-config`. Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án để quản lý version:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-config</artifactId>
    </dependency>
</dependencies>
```

Không tự chọn version starter khác release train đang dùng. Hãy kiểm tra bảng tương thích Spring Boot/Spring Cloud và dependency tree khi nâng cấp.

## 3. Khai báo `spring.config.import`

Spring Boot 2.4 trở lên cung cấp Config Data API thông qua `spring.config.import`. Đây là cách mặc định được Spring Cloud Consul khuyến nghị để nạp cấu hình từ Consul.

Ví dụ tối giản trong `application.yml`:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "consul:"
```

Nếu không chỉ định host/port trong import, client kết nối Consul Agent tại `http://localhost:8500`. Có thể khai báo địa chỉ trong import:

```yaml
spring:
  config:
    import: "consul:consul-agent.internal:8500"
```

Hoặc cấu hình host và port riêng:

```yaml
spring:
  cloud:
    consul:
      host: consul-agent.internal
      port: 8500
```

Khi URI trong `spring.config.import` có host/port, giá trị đó được ưu tiên hơn `spring.cloud.consul.host` và `spring.cloud.consul.port`.

### Bắt buộc kết nối hay cho phép thiếu Consul?

Hai dạng import có hành vi khác nhau:

```yaml
spring:
  config:
    import: "consul:"
```

Không có tiền tố `optional:` nghĩa là nguồn Consul được yêu cầu. Nếu Config Client không kết nối hoặc không nạp được nguồn bắt buộc, quá trình khởi động sẽ thất bại.

```yaml
spring:
  config:
    import: "optional:consul:"
```

Có `optional:` nghĩa là ứng dụng có thể tiếp tục khởi động khi Consul không sẵn sàng hoặc nguồn cấu hình tùy chọn không tồn tại. Cách này phù hợp với một số môi trường phát triển/test có default an toàn. Trong production, nếu endpoint database, chế độ bảo mật hoặc giới hạn nghiệp vụ bắt buộc phải lấy từ Consul, hãy dùng import bắt buộc để tránh chạy âm thầm với cấu hình thiếu.

Thuộc tính `spring.cloud.consul.config.fail-fast` cũng điều khiển cách Config module xử lý lỗi tra cứu: mặc định `true` sẽ ném exception; đặt `false` sẽ ghi warning và cho phép ứng dụng tiếp tục. Hãy chọn rõ chính sách lỗi thay vì dùng optional/fail-fast để che giấu sự cố Consul.

## 4. Không cần `bootstrap.yml` khi dùng Config Data import

Với mô hình `spring.config.import`, khai báo kết nối Consul và các tùy chọn Consul Config trong `application.yml` là đủ. Không cần thêm `spring-cloud-starter-bootstrap` chỉ để đọc KV.

Ví dụ cấu hình hoàn chỉnh cho một ứng dụng:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "consul:consul-agent.internal:8500"
  cloud:
    consul:
      config:
        enabled: true
        prefixes:
          - config
        default-context: application
        profile-separator: ","
        format: KEY_VALUE
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
        watch:
          enabled: true
          delay: 1000
          wait-time: 55
```

Trong ví dụ này, `CONSUL_CONFIG_ACL_TOKEN` phải được cấp từ môi trường triển khai hoặc secret manager. Không lưu token duy nhất trong Consul KV mà chính token đó cần truy cập.

Nếu dự án chủ động bật legacy bootstrap bằng `spring.cloud.bootstrap.enabled=true`, `spring.config.use-legacy-processing=true` hoặc thêm `spring-cloud-starter-bootstrap`, các thuộc tính Consul Config cần được đặt trong `bootstrap.yml` theo cơ chế legacy. Không trộn hai mô hình nạp cấu hình nếu không có lý do rõ ràng.

## 5. Bốn context Consul được tra cứu tự động

Spring Cloud Consul tạo các context dựa trên:

- `spring.cloud.consul.config.prefixes`: một hoặc nhiều prefix KV. Mặc định là một prefix `config`.
- `spring.cloud.consul.config.name`: tên application dùng để tra cứu; mặc định lấy từ `spring.application.name`.
- `spring.cloud.consul.config.default-context`: context dùng chung; mặc định là `application`.
- Active profiles của Spring Environment.
- `spring.cloud.consul.config.profile-separator`: ký tự phân tách profile; mặc định là dấu phẩy `,`.

Giả sử ứng dụng có:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
```

Với prefix `config`, default context `application` và profile separator `,`, các context được tạo theo thứ tự cụ thể đến tổng quát:

```text
config/order-service,prod/
config/order-service/
config/application,prod/
config/application/
```

Property source cụ thể hơn đứng trước và có ưu tiên cao hơn. Các key trong `config/application/` là cấu hình nền có thể dùng chung cho các ứng dụng. Các key trong `config/order-service/` chỉ áp dụng cho application có tên `order-service`.

Ví dụ cùng một thuộc tính được khai báo ở nhiều context:

| Context | `orders.timeout` |
|---|---:|
| `config/application/` | `2s` |
| `config/application,prod/` | `4s` |
| `config/order-service/` | `3s` |
| `config/order-service,prod/` | `5s` |

Với thứ tự property source ở trên, `order-service` chạy profile `prod` nhận `5s`. Giá trị ở context cụ thể nhất thắng. Nếu một key không có ở context đó, Spring tiếp tục lấy giá trị từ context có độ ưu tiên thấp hơn.

Khi ứng dụng có nhiều active profile, hãy kiểm tra property source thực tế trong môi trường chạy thay vì tự suy luận thứ tự kết hợp profile. Profile separator có thể tùy chỉnh, nhưng phải dùng cùng quy ước khi tạo key trong Consul.

## 6. Tổ chức prefix và context

Trong Spring Cloud Consul 5.1, nên dùng `prefixes` để khai báo một hoặc nhiều thư mục gốc:

```yaml
spring:
  cloud:
    consul:
      config:
        prefixes:
          - configuration
          - shared
        default-context: applications
        profile-separator: "::"
```

Với cấu hình trên, Spring Cloud Consul tìm context theo prefix `configuration` và `shared`, dùng `applications` làm context chung và nối profile bằng `::`.

Ví dụ context có thể được tạo thành:

```text
configuration/order-service::prod/
configuration/order-service/
configuration/applications::prod/
configuration/applications/
shared/order-service::prod/
shared/order-service/
shared/applications::prod/
shared/applications/
```

`spring.cloud.consul.config.prefix` là thuộc tính đơn lẻ cũ và đã được đánh dấu deprecated trong tài liệu hiện hành; dùng `prefixes` cho cấu hình mới. Có thể khai báo danh sách bằng YAML hoặc chuỗi phân tách dấu phẩy trong `application.properties`.

Nếu muốn tự chỉ định các context thay vì để Spring Cloud Consul tính bốn context mặc định, có thể đưa chúng vào URI import:

```properties
spring.config.import=optional:consul:consul-agent.internal:8500/contextone;/context/two
```

Ví dụ này yêu cầu nạp tùy chọn từ `/contextone` và `/context/two`. Khi dùng danh sách context tùy chỉnh, hãy xác minh lại cấu trúc key và thứ tự ưu tiên mà ứng dụng cần.

## 7. Chọn định dạng dữ liệu trong Consul KV

Spring Cloud Consul hỗ trợ nhiều cách biểu diễn cấu hình trong KV. Thuộc tính `spring.cloud.consul.config.format` quyết định cách đọc:

| Format | Cách lưu | Phù hợp khi |
|---|---|---|
| `KEY_VALUE` | Mỗi thuộc tính là một KV entry riêng | Muốn cập nhật từng key và tổ chức key theo prefix |
| `YAML` | Một tài liệu YAML được lưu trong key `data` (mặc định) của context | Muốn giữ cấu trúc YAML và nhóm thuộc tính liên quan |
| `PROPERTIES` | Một nội dung Java Properties trong key `data` | Muốn dùng định dạng `.properties` |
| `FILES` | Mỗi file YAML/Properties được đưa vào một key riêng | Dùng cùng công cụ `git2consul` để đồng bộ file từ Git vào KV |

### KEY_VALUE: một key cho mỗi thuộc tính

`KEY_VALUE` là format mặc định. Ví dụ:

```text
config/application/server/port = 8080
config/application/management/endpoints/web/exposure/include = health,info
config/order-service,prod/orders/timeout = 5s
config/order-service,prod/orders/retry-limit = 3
```

Các đoạn đường dẫn dưới context được ánh xạ thành tên thuộc tính phân tách bằng dấu chấm. Ví dụ `config/order-service,prod/orders/timeout` cung cấp thuộc tính `orders.timeout` cho context tương ứng.

Ưu điểm của cách này là có thể thay một thuộc tính mà không ghi lại cả tài liệu YAML. Khi cần cập nhật nhiều key liên quan như một đơn vị, nên dùng quy trình ghi có kiểm soát và kiểm tra kết quả để tránh ứng dụng đọc trạng thái cấu hình dở dang giữa các lần ghi.

### YAML: một tài liệu trong key `data`

Đặt format:

```yaml
spring:
  cloud:
    consul:
      config:
        format: YAML
        data-key: data
```

Với `order-service` và profile `prod`, các key được tra cứu có thể là:

```text
config/order-service,prod/data
config/order-service/data
config/application,prod/data
config/application/data
```

Giá trị của key `config/order-service,prod/data` là nội dung YAML:

```yaml
orders:
  timeout: 5s
  retry-limit: 3

payment:
  gateway-url: https://payments.internal
```

`data-key` mặc định là `data`; có thể đổi nếu quy ước lưu trữ của tổ chức dùng tên khác. Hãy bảo đảm nội dung trong key là một tài liệu YAML hợp lệ.

### PROPERTIES: một tài liệu Java Properties

Đặt `format: PROPERTIES`; key `data` (hoặc tên `data-key` đã cấu hình) chứa nội dung dạng:

```properties
orders.timeout=5s
orders.retry-limit=3
payment.gateway-url=https://payments.internal
```

Các context và quy tắc ưu tiên vẫn dựa trên application/profile; chỉ cách phân tích value thay đổi.

### FILES: tích hợp với git2consul

`git2consul` là công cụ cộng đồng đồng bộ file từ Git vào Consul KV. Khi dùng format `FILES`, Spring Cloud Consul đọc các key có tên file, ví dụ:

```text
config/application.yml
config/order-service.yml
config/order-service-prod.yml
config/inventory-service.yml
```

Giá trị của mỗi key phải là nội dung YAML hoặc Properties hợp lệ. Với profile `prod` và application `order-service`, Spring Cloud Consul có thể tạo property source từ file theo tên ứng dụng/profile và file chung. Chọn `FILES` khi pipeline đã dùng git2consul; nếu tự ghi key/value trực tiếp, dùng `KEY_VALUE`, `YAML` hoặc `PROPERTIES` phù hợp hơn.

## 8. Ghi và kiểm tra key bằng Consul CLI

Trong môi trường phát triển, có thể dùng Consul CLI để kiểm tra dữ liệu:

```bash
consul kv put config/application/server/port 8080
consul kv put config/order-service,prod/orders/timeout 5s
consul kv get config/order-service,prod/orders/timeout
consul kv get -recurse config/order-service,prod/
```

Lệnh `kv put` ghi một key; `kv get` đọc một key; `-recurse` liệt kê và đọc các key dưới prefix. Khi bật ACL, lệnh CLI phải dùng token có quyền tương ứng.

Đối với YAML format, tạo key context có tên `data` và lưu toàn bộ tài liệu YAML vào value. Không tạo từng key con như `orders/timeout` trong cùng context nếu ứng dụng đang cấu hình `format: YAML`; format YAML chờ một blob trong `data-key`.

Consul KV coi key là chuỗi opaque. Dấu `/` hữu ích để tổ chức prefix và truy vấn đệ quy, nhưng không phải thư mục filesystem thực. Consul KV giới hạn mỗi value tối đa 512 KB; không dùng KV để lưu file nhị phân lớn hoặc dữ liệu cần một hệ quản trị chuyên dụng.

## 9. Bảo vệ Consul KV bằng ACL token

Khi bật Consul ACL, ứng dụng cần token hợp lệ có quyền đọc KV. Spring Cloud Consul Config có thuộc tính riêng:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
```

Đây là token cho Config KV. Nếu ứng dụng đồng thời dùng Consul Service Discovery, thuộc tính `spring.cloud.consul.discovery.acl-token` là token cho các thao tác discovery; không mặc định rằng hai phạm vi quyền cần dùng chung một token.

Token phải được cấp trước khi Config Data import truy cập Consul. Đưa token vào biến môi trường, secret manager hoặc cơ chế cấp bí mật của nền tảng. Không đặt token chỉ trong chính Consul KV mà token đó cần đọc; như vậy sẽ tạo vòng phụ thuộc.

### Policy chỉ đọc cho một ứng dụng

Với Consul 1.10 trở lên, thao tác đọc đệ quy một prefix KV cần quyền `list` trên prefix; quyền `list` cũng cho phép đọc các key con. Policy `list` cần được bật trong cấu hình ACL của Consul (`acl.enable_key_list_policy=true`) nếu cluster chưa bật sẵn. Ví dụ policy minh họa cho `order-service` và context dùng chung `application`:

```hcl
key_prefix "config/order-service/" {
  policy = "list"
}

key_prefix "config/order-service," {
  policy = "list"
}

key_prefix "config/application/" {
  policy = "list"
}

key_prefix "config/application," {
  policy = "list"
}
```

Hai prefix cho application bao phủ context không có profile (`order-service/`) và context có profile (`order-service,prod/`). Hai prefix `application` cho phép đọc cấu hình nền mà ứng dụng kế thừa. Nếu dùng prefix khác, default context khác, profile separator khác hoặc nhiều prefixes, hãy điều chỉnh policy cho đúng đường dẫn thực tế.

Policy trên chỉ minh họa quyền đọc đệ quy. Không cấp `write` cho Config Client nếu ứng dụng chỉ cần nạp cấu hình. Dùng token quản trị chỉ để tạo policy/token; không dùng management token cho workload.

## 10. Kết nối HTTPS và bảo vệ token

Mặc định Consul Agent được truy cập qua HTTP ở cổng `8500`. Trong production, hãy dùng HTTPS/TLS theo cấu hình của Consul cluster và xác minh chứng thư của agent/server. Không tắt xác minh TLS để xử lý nhanh lỗi certificate.

Ví dụ khai báo scheme:

```yaml
spring:
  cloud:
    consul:
      scheme: https
      host: consul-agent.internal
      port: 8501
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
```

Nếu Consul dùng certificate hoặc trust store riêng, cấu hình các thuộc tính TLS của Spring Cloud Consul theo cách triển khai của tổ chức. Bảo vệ file certificate/private key và password của keystore như các secret khác.

Token ACL thường được gửi trong header `X-Consul-Token` khi client gọi Consul HTTP API. Không ghi header này vào log, trace hoặc exception report. Nên cấp token read-only theo từng ứng dụng hoặc nhóm ứng dụng, rotate khi có thay đổi quyền và thu hồi token cũ sau khi rollout hoàn tất.

## 11. Config Watch và cập nhật khi KV thay đổi

Nếu bật Config Watch (mặc định `true`), Spring Cloud Consul dùng khả năng blocking query theo prefix của Consul để phát hiện key liên quan đến ứng dụng đã thay đổi. Khi có dữ liệu mới, một Refresh Event được phát trong ứng dụng; hành vi này tương đương việc gọi endpoint Actuator `/refresh`.

Các thuộc tính quan trọng:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---:|---|
| `spring.cloud.consul.config.watch.enabled` | `true` | Bật/tắt Config Watch |
| `spring.cloud.consul.config.watch.delay` | `1000` ms | Khoảng nghỉ sau khi lần watch trước hoàn tất trước khi bắt đầu lần tiếp theo |
| `spring.cloud.consul.config.watch.wait-time` | `55` giây | Thời gian blocking query chờ Consul trả kết quả |

Ví dụ tắt watch:

```yaml
spring:
  cloud:
    consul:
      config:
        watch:
          enabled: false
```

Watch dùng `TaskScheduler`; mặc định là `ThreadPoolTaskScheduler` với một thread. `wait-time` mặc định 55 giây thấp hơn timeout mặc định 60 giây của Consul client. Nếu tăng wait-time, phải bảo đảm HTTP client timeout lớn hơn thời gian chờ blocking query; nếu không request có thể bị timeout trước khi Consul trả lời.

Config Watch không có nghĩa mọi bean singleton đều được tạo lại. Refresh Event cập nhật Environment và kích hoạt các cơ chế refresh/rebinding được Spring Cloud hỗ trợ. Bean cần tái tạo target thường phải dùng `@RefreshScope`; bean giữ giá trị đã copy trong field có thể tiếp tục giữ giá trị cũ. Kiểm tra `@ConfigurationProperties`, `@RefreshScope` và lifecycle của các dependency trước khi coi một thuộc tính là runtime-refreshable.

## 12. Fail-fast và retry khi Consul không sẵn sàng

`spring.cloud.consul.config.fail-fast` mặc định là `true`. Nếu Config Client không thể nạp cấu hình bắt buộc, ứng dụng dừng khởi động. Có thể đặt `false` để ghi warning và tiếp tục với các nguồn cấu hình còn lại:

```yaml
spring:
  cloud:
    consul:
      config:
        fail-fast: false
```

Chỉ dùng cách này khi ứng dụng có default an toàn và nhóm chấp nhận chạy mà thiếu một phần cấu hình Consul. Không dùng nó cho giá trị bắt buộc như credential database, policy bảo mật hoặc endpoint thanh toán nếu thiếu cấu hình sẽ làm ứng dụng hoạt động sai.

Spring Cloud Consul cũng hỗ trợ retry khi agent tạm thời không sẵn sàng. Các thuộc tính thường dùng:

```yaml
spring:
  cloud:
    consul:
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1000
        max-interval: 2000
        multiplier: 1.1
```

Theo tài liệu Spring Cloud Consul 5.0.x, retry cần `spring-retry` và `spring-boot-starter-aspectj` trên classpath; tên dependency có thể thay đổi theo release train đang chạy. Mặc định được tài liệu mô tả là sáu lần thử, backoff ban đầu một giây và multiplier 1.1; `max-interval` giới hạn khoảng nghỉ tối đa. Kiểm tra dependency tree và tài liệu đúng phiên bản trước khi dựa vào retry trong production.

Retry chỉ giúp xử lý gián đoạn tạm thời. Nếu token hết hạn, ACL thiếu quyền, prefix sai hoặc YAML không hợp lệ, tăng số lần retry không sửa được nguyên nhân.

## 13. Xác minh ứng dụng đã nhận đúng cấu hình

Sau khi ghi KV và khởi động client, kiểm tra theo thứ tự:

1. **Kết nối Consul Agent:** host/port/scheme đúng; agent có thể truy cập từ container hoặc máy chạy ứng dụng.
2. **ACL:** token được cấp đúng và có quyền `list`/`read` trên mọi prefix mà ứng dụng cần.
3. **Application/profile:** `spring.application.name`, active profile và `spring.cloud.consul.config.name` đúng với context đang lưu.
4. **Prefix/context:** `prefixes`, `default-context` và `profile-separator` khớp key thực tế.
5. **Format:** `KEY_VALUE`, `YAML`, `PROPERTIES` hoặc `FILES` khớp cách dữ liệu được ghi.
6. **Environment:** kiểm tra property source và giá trị đã phân giải trong Spring.
7. **Bean:** xác nhận `@ConfigurationProperties` hoặc `@RefreshScope` thực sự nhận giá trị mới sau refresh.

Trong ứng dụng có Actuator, endpoint `env` giúp xem property source và giá trị hiện tại; `configprops` giúp kiểm tra giá trị đã bind vào bean. Chỉ expose endpoint chẩn đoán trong mạng quản trị, bật xác thực/phân quyền và giữ sanitization cho password/token.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng không khởi động và báo Consul Config Data resource không tồn tại | Consul không truy cập được, sai host/port hoặc import bắt buộc | Kiểm tra agent, network, URI và quyết định optional/required |
| Consul trả `403` | ACL token thiếu quyền hoặc token không đúng | Kiểm tra `spring.cloud.consul.config.acl-token`, policy và quyền `list` trên prefix |
| Discovery hoạt động nhưng Config không đọc được KV | Có `discovery.acl-token` nhưng thiếu token riêng cho config, hoặc policy chỉ cấp service permission | Cấu hình `config.acl-token` và quyền KV phù hợp |
| Không thấy key dù Consul UI có dữ liệu | Sai prefix, default context, application name hoặc profile separator | Đối chiếu đường dẫn context mà client tính với key trong KV |
| YAML không được bind | Chọn `KEY_VALUE` nhưng lưu blob YAML, hoặc thiếu key `data` | Chọn `format: YAML`, kiểm tra `data-key` và nội dung YAML |
| Một số thuộc tính không có | Sai cấu trúc key, sai format hoặc key nằm ngoài context được đọc | Dùng `consul kv get -recurse` kiểm tra prefix và key path |
| Giá trị từ context chung thắng ngoài dự kiến | Sai giả định về thứ tự property source | Kiểm tra thứ tự bốn context; application-specific context đứng trước context chung |
| KV đổi nhưng bean vẫn dùng giá trị cũ | Watch tắt, refresh event không tới hoặc bean không hỗ trợ refresh | Kiểm tra watch log, Environment, `@ConfigurationProperties` và `@RefreshScope` |
| Watch thường xuyên timeout | `wait-time` lớn hơn HTTP client timeout hoặc mạng tới agent không ổn định | Giữ wait-time thấp hơn client timeout, kiểm tra TLS/network |
| App vẫn khởi động dù thiếu cấu hình | Import có `optional:` hoặc `fail-fast=false` | Kiểm tra policy lỗi và default an toàn |

## 15. Quản trị thay đổi và vận hành Consul KV

Consul KV là kho lưu trữ cấu hình, không tự cung cấp workflow review và lịch sử pull request giống Git. Để quản trị thay đổi nhất quán, nên:

- Định nghĩa quy ước prefix, application, profile và format trước khi nhiều nhóm cùng ghi dữ liệu.
- Giữ `application` context cho giá trị thực sự dùng chung; đặt giá trị riêng dịch vụ dưới application context.
- Dùng ACL token riêng cho writer/pipeline và read-only token cho workload đọc cấu hình.
- Thực hiện review thay đổi trong Git hoặc pipeline trước khi ghi vào KV.
- Ghi nhận người thay đổi, thời điểm, key path và giá trị trước/sau trong audit log; không log secret dạng rõ.
- Có backup và phương án khôi phục. Consul hỗ trợ snapshot để sao lưu trạng thái; kiểm thử quy trình restore định kỳ.
- Tránh ghi nhiều key liên quan thành các trạng thái không đồng bộ; nếu cần cập nhật nhiều KV pair có tính nguyên tử, xem xét Consul transaction API và giới hạn của nó.
- Theo dõi Config Watch, lỗi ACL, thời gian lấy cấu hình và trạng thái refresh của ứng dụng.
- Xem xét tách prefix hoặc Consul cluster/trust zone khi các nhóm có yêu cầu bí mật và quyền truy cập khác nhau.

## 16. Checklist triển khai

| Hạng mục | Điều kiện đạt |
|---|---|
| Dependency | Có `spring-cloud-starter-consul-config` và Spring Cloud BOM tương thích |
| Config Data | Có `spring.config.import=consul:` hoặc URI Consul chính xác |
| Agent | Consul Agent truy cập được từ môi trường chạy ứng dụng |
| Application/profile | Tên ứng dụng và profile khớp context KV |
| Prefixes | Prefix và default context thống nhất với quy ước lưu key |
| Format | Cấu trúc KV khớp `KEY_VALUE`, `YAML`, `PROPERTIES` hoặc `FILES` |
| ACL | Token riêng, quyền đọc đệ quy đúng prefix, không dùng management token |
| TLS | HTTPS/certificate được xác minh trong production |
| Watch | Bật/tắt theo nhu cầu; wait-time nhỏ hơn HTTP client timeout |
| Fail-fast | Có quyết định rõ khi Consul không sẵn sàng |
| Retry | Có dependency hỗ trợ và backoff hữu hạn phù hợp |
| Refresh | Bean được thiết kế để rebinding hoặc refresh scope khi cần |
| Observability | Có log, metric, kiểm tra Environment/configprops và cảnh báo ACL |
| Backup | Có snapshot và quy trình khôi phục được kiểm thử |

## 17. Nguyên tắc cần ghi nhớ

- Dùng `spring-cloud-starter-consul-config` và `spring.config.import=consul:` để nạp KV vào Spring Boot Config Data.
- `optional:consul:` cho phép khởi động khi Consul không sẵn sàng; import bắt buộc sẽ làm startup thất bại khi không nạp được nguồn.
- Consul Agent mặc định ở `localhost:8500`; URI trong import có host/port ưu tiên hơn `spring.cloud.consul.host/port`.
- Context mặc định dùng prefix `config`, application từ `spring.application.name`, default context `application` và profile separator dấu phẩy.
- Context application/profile cụ thể có ưu tiên cao hơn context tổng quát; `application` là cấu hình nền dùng chung.
- Dùng `prefixes` cho cấu hình mới; `prefix` đơn đã deprecated.
- `KEY_VALUE` lưu từng thuộc tính thành key riêng; `YAML` và `PROPERTIES` lưu nội dung trong `data-key` mặc định `data`; `FILES` dành cho luồng git2consul.
- Cấp `spring.cloud.consul.config.acl-token` với quyền KV tối thiểu; quyền discovery là một phạm vi riêng.
- Config Watch dùng blocking query để phát Refresh Event; không phải mọi singleton bean đều tự được tạo lại.
- Đặt `wait-time` nhỏ hơn timeout HTTP client; xử lý lỗi tạm thời bằng retry có giới hạn.
- Bảo vệ token, dùng TLS, backup Consul KV và quản trị thay đổi qua review/audit.

`spring.config.import` nối Spring Boot với Consul KV ngay trong giai đoạn nạp Config Data. Khi quy ước prefix, application/profile, format và ACL được thiết kế rõ ràng, nhiều ứng dụng có thể dùng chung cấu hình nền và ghi đè bằng context riêng. Config Watch giúp phát hiện thay đổi trong KV, còn việc áp dụng giá trị vào bean phụ thuộc vào cơ chế refresh mà ứng dụng lựa chọn.

## Tài liệu tham khảo

- [Spring Cloud Consul 5.1 — Distributed Configuration with Consul](https://docs.spring.io/spring-cloud-consul/reference/config.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Consul Retry](https://docs.spring.io/spring-cloud-consul/reference/retry.html)
- [Consul — Key/Value Store overview](https://developer.hashicorp.com/consul/docs/automate/kv)
- [Consul — ACL rules for Key/Value](https://developer.hashicorp.com/consul/docs/reference/acl/rule)
- [Consul — KV HTTP API](https://developer.hashicorp.com/consul/api-docs/kv)
