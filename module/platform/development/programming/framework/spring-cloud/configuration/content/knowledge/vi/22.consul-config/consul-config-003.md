# prefix, default-context và profile-separator

Spring Cloud Consul Config đọc dữ liệu từ Consul Key/Value Store và đưa chúng vào Spring `Environment` dưới dạng các `PropertySource`. Để nhiều ứng dụng có thể dùng chung cấu hình mà vẫn ghi đè được theo dịch vụ và môi trường, Spring Cloud Consul tổ chức dữ liệu theo các context path. Ba thuộc tính quyết định cách tạo những đường dẫn này là **`prefix`**, **`default-context`** và **`profile-separator`**.

- `prefix` xác định thư mục gốc trong Consul KV.
- `default-context` xác định context dùng chung cho các ứng dụng.
- `profile-separator` xác định ký tự phân cách giữa tên context và profile khi tạo context theo profile.

Hiểu đúng ba thuộc tính giúp nhóm dự đoán nơi cần ghi key trong Consul, tránh đọc nhầm context và kiểm soát thứ tự ưu tiên giữa cấu hình dùng chung, cấu hình theo ứng dụng và cấu hình theo profile.

## 1. Consul context và Spring PropertySource

Consul KV lưu dữ liệu dưới dạng cây key path. Spring Cloud Consul Config chọn một số context path dựa trên tên ứng dụng và các profile đang hoạt động. Mỗi context được đọc sẽ đóng góp một `PropertySource` vào Spring `Environment`.

Ví dụ ứng dụng có:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
```

Với cấu hình mặc định, Spring Cloud Consul Config tìm các context theo thứ tự từ cụ thể đến dùng chung:

```text
config/billing-api,prod/
config/billing-api/
config/application,prod/
config/application/
```

Trong ví dụ:

- `billing-api,prod` là cấu hình riêng của ứng dụng `billing-api` trong profile `prod`.
- `billing-api` là cấu hình riêng ứng dụng không gắn profile.
- `application,prod` là cấu hình dùng chung cho các ứng dụng trong profile `prod`.
- `application` là cấu hình dùng chung không gắn profile.

Context cụ thể hơn đứng trước và có ưu tiên cao hơn. Vì vậy, khóa được khai báo ở `config/billing-api,prod/` có thể ghi đè cùng khóa từ `config/billing-api/`, `config/application,prod/` hoặc `config/application/`. Khóa không có ở context ưu tiên cao hơn vẫn có thể được lấy từ context phía dưới.

## 2. prefix: thư mục gốc của cấu hình

`spring.cloud.consul.config.prefix` đặt thư mục gốc mà Spring Cloud Consul Config dùng để tìm các context. Giá trị mặc định là `config` trong cấu hình chuẩn của Spring Cloud Consul.

Ví dụ đổi root thành `configuration`:

```yaml
spring:
  cloud:
    consul:
      config:
        prefix: configuration
```

Khi đó, bốn context trong ví dụ `billing-api` và profile `prod` trở thành:

```text
configuration/billing-api,prod/
configuration/billing-api/
configuration/application,prod/
configuration/application/
```

`prefix` giúp tách dữ liệu cấu hình khỏi các key Consul khác như service metadata, feature flags của hệ thống khác hoặc dữ liệu vận hành. Nếu nhiều ứng dụng dùng chung một Consul cluster, nên thống nhất root theo domain hoặc môi trường, ví dụ `configuration`, `platform/config` hoặc `production/config`.

Không nhầm `prefix` với tên application hoặc profile. Nó chỉ thay đổi phần gốc của các context được tìm kiếm; tên ứng dụng, default context và profile vẫn được ghép theo quy tắc riêng.

## 3. default-context: context dùng chung cho mọi ứng dụng

`spring.cloud.consul.config.default-context` xác định tên context mặc định được dùng chung giữa các ứng dụng. Giá trị mặc định là `application`.

Ví dụ đổi context dùng chung thành `shared`:

```yaml
spring:
  cloud:
    consul:
      config:
        default-context: shared
```

Với `prefix: configuration`, ứng dụng `billing-api` và profile `prod` sẽ tìm các context:

```text
configuration/billing-api,prod/
configuration/billing-api/
configuration/shared,prod/
configuration/shared/
```

Các context `shared` cung cấp cấu hình nền cho nhiều ứng dụng, chẳng hạn mức log mặc định, timeout chung hoặc tên vùng triển khai. Context `billing-api` cung cấp cấu hình chuyên biệt cho dịch vụ thanh toán.

Ví dụ dữ liệu:

```text
configuration/shared/logging.level.root = INFO
configuration/shared/acme.http.connect-timeout = 2s

configuration/billing-api/acme.billing.retry.max-attempts = 3
configuration/billing-api,prod/acme.http.connect-timeout = 5s
```

Trong ví dụ này, tất cả ứng dụng dùng root `configuration` đều có thể nhận log level và timeout chung từ `shared`. Riêng `billing-api` có retry riêng; profile `prod` của ứng dụng đó ghi đè timeout thành `5s`.

`default-context` là tên context dùng chung, không phải tên profile mặc định. Profile mặc định và danh sách profile hoạt động vẫn do Spring Boot/Spring Cloud quyết định.

## 4. profile-separator: ký tự nối profile vào context

`spring.cloud.consul.config.profile-separator` xác định chuỗi phân cách giữa context name và profile khi Spring Cloud Consul tạo profile-specific context. Giá trị mặc định là dấu phẩy `,`.

Ví dụ đổi separator thành `::`:

```yaml
spring:
  cloud:
    consul:
      config:
        profile-separator: '::'
```

Với application `billing-api`, profile `prod`, prefix `configuration` và default context `shared`, các đường dẫn sẽ là:

```text
configuration/billing-api::prod/
configuration/billing-api/
configuration/shared::prod/
configuration/shared/
```

Thay separator chỉ thay đổi cách ghép tên context với profile. Nó không đổi tên profile `prod`, không thay `/` phân cấp thư mục và cũng không tự tạo profile mới.

### Khi nào nên đổi separator?

Đổi separator khi quy ước key path của tổ chức cần tránh dấu phẩy hoặc đã có công cụ đồng bộ/đặt tên context yêu cầu một dấu phân cách khác. Nếu không có nhu cầu rõ ràng, giữ giá trị mặc định `,` sẽ giúp cấu trúc Consul tương thích với quy ước mặc định và dễ đối chiếu tài liệu.

Separator phải thống nhất giữa các ứng dụng cùng đọc một bộ cấu hình. Nếu một ứng dụng dùng `,` còn ứng dụng khác dùng `::`, chúng có thể truy vấn hai context path khác nhau dù cùng application và profile.

## 5. Kết hợp ba thuộc tính trong một cấu hình hoàn chỉnh

Ví dụ Config Data import hiện đại:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
  config:
    import: 'optional:consul:consul.internal:8500'
  cloud:
    consul:
      host: consul.internal
      port: 8500
      config:
        enabled: true
        prefix: configuration
        default-context: shared
        profile-separator: '::'
```

Ứng dụng sẽ dùng Consul Agent tại `consul.internal:8500`, tìm cấu hình dưới root `configuration`, dùng `shared` làm context chung và ghép profile bằng `::`.

Các context dự kiến cho `billing-api`/`prod`:

| Thứ tự | Context path | Phạm vi |
| ---: | --- | --- |
| 1 | `configuration/billing-api::prod/` | Riêng ứng dụng và profile |
| 2 | `configuration/billing-api/` | Riêng ứng dụng, mọi profile |
| 3 | `configuration/shared::prod/` | Dùng chung cho profile |
| 4 | `configuration/shared/` | Dùng chung cho mọi ứng dụng |

`optional:` cho phép ứng dụng tiếp tục nếu nguồn Consul không thể được nạp, tùy chính sách Config Data và cấu hình fail-fast. Nếu cấu hình Consul là bắt buộc để ứng dụng hoạt động an toàn, bỏ `optional:` và kiểm tra chính sách startup phù hợp.

Với Config Data API của Spring Boot 2.4 trở lên, các thuộc tính trên có thể đặt trong `application.yml`. Nếu ứng dụng chủ động bật legacy bootstrap processing hoặc dùng `spring-cloud-starter-bootstrap`, hãy đặt các thuộc tính bootstrap tương ứng trong `bootstrap.yml` theo hướng dẫn của phiên bản Spring Cloud đang sử dụng.

## 6. Cách dữ liệu được phân lớp và ghi đè

Giả sử các context có dữ liệu sau:

```text
configuration/shared/
  acme.http.connect-timeout = 2s
  acme.http.read-timeout = 10s
  logging.level.root = INFO

configuration/shared::prod/
  acme.http.read-timeout = 20s

configuration/billing-api/
  acme.http.connect-timeout = 3s
  acme.billing.retry.max-attempts = 3

configuration/billing-api::prod/
  acme.http.connect-timeout = 5s
```

Khi `billing-api` chạy profile `prod`, kết quả mong đợi:

| Thuộc tính | Giá trị được chọn | Nguồn |
| --- | --- | --- |
| `acme.http.connect-timeout` | `5s` | `billing-api::prod` |
| `acme.http.read-timeout` | `20s` | `shared::prod` |
| `logging.level.root` | `INFO` | `shared` |
| `acme.billing.retry.max-attempts` | `3` | `billing-api` |

Ví dụ cho thấy profile-specific application có thể ghi đè cấu hình application chung, trong khi profile-specific shared vẫn cung cấp giá trị cho các khóa không có ở application-specific context. Property source cụ thể hơn được xét trước; những khóa không xuất hiện sẽ tiếp tục được tìm ở nguồn ít cụ thể hơn.

Các nguồn khác trong Spring `Environment` như biến môi trường, system properties hoặc command line vẫn có thể ghi đè Config Data theo thứ tự ưu tiên của Spring Boot. Vì vậy, khi giá trị runtime khác Consul KV, cần kiểm tra cả property source của Consul và các nguồn ngoài Consul.

## 7. Nhiều active profile

Một ứng dụng có thể kích hoạt nhiều profile, ví dụ:

```yaml
spring:
  profiles:
    active: prod,cloud
```

Spring Cloud Consul tạo các profile-specific context dựa trên danh sách profile đang hoạt động. `profile-separator` được dùng để ghép tên context với từng profile. Ví dụ với separator `::`, các context profile-specific có thể bao gồm:

```text
configuration/billing-api::prod/
configuration/billing-api::cloud/
configuration/shared::prod/
configuration/shared::cloud/
```

Các context không gắn profile vẫn được tìm để cung cấp cấu hình nền. Khi nhiều profile cùng khai báo một khóa, thứ tự profile active và thứ tự `PropertySource` ảnh hưởng giá trị cuối cùng. Hãy kiểm tra thứ tự nguồn trong ứng dụng đang chạy thay vì tự suy luận từ tên path.

Nếu có nhiều profile, không nên đặt cùng một khóa ở nhiều context profile-specific trừ khi thực sự cần override. Ghi nhận quy ước profile và thứ tự ưu tiên trong tài liệu triển khai để các nhóm không vô tình tạo ra giá trị khác nhau giữa các môi trường.

## 8. Phân biệt prefix với context tường minh trong spring.config.import

Thông thường, Spring Cloud Consul tự tính các context từ `prefix`, application name, `default-context` và active profiles. Nếu muốn chỉ định context cụ thể, Config Data import cho phép ghi các context path trực tiếp, ví dụ:

```properties
spring.config.import=optional:consul:consul.internal:8500/team-a/billing;/team-a/shared
```

Trong trường hợp này, ứng dụng yêu cầu các context được liệt kê trong location thay vì dựa hoàn toàn vào bốn context tự tính. Khi dùng đường dẫn tường minh, hãy kiểm tra chính xác path theo mount và quy ước KV của Consul; không mặc định các context tự động từ `default-context` hoặc profile separator vẫn được ghép thêm vào đường dẫn đã chỉ định.

Không trộn lẫn hai cách tổ chức mà không có chủ đích. Dùng computed contexts khi muốn chuẩn hóa naming theo application/profile; dùng explicit contexts khi cần một tập path cố định, có thể review trực tiếp trong cấu hình triển khai.

## 9. Key-Value format và YAML/Properties format

Ba thuộc tính path vẫn xác định context cần đọc, nhưng cách lưu dữ liệu bên trong context phụ thuộc `spring.cloud.consul.config.format`.

### Key-value format

Với format mặc định, mỗi thuộc tính có thể được lưu thành một key riêng dưới context:

```text
configuration/billing-api::prod/acme.billing.connect-timeout = 5s
configuration/billing-api::prod/acme.billing.retry.max-attempts = 5
```

### YAML format

Nếu dùng YAML, cấu hình YAML được lưu thành một blob trong key `data` mặc định của context:

```text
configuration/billing-api::prod/data
```

Giá trị của key `data`:

```yaml
acme:
  billing:
    connect-timeout: 5s
    retry:
      max-attempts: 5
```

Có thể đổi key chứa blob bằng `spring.cloud.consul.config.data-key`. Khi dùng YAML hoặc PROPERTIES format, cần lưu ý `data-key` và bảo đảm nội dung blob hợp lệ. Không đặt từng key YAML con vào cùng context theo cách của key-value format nếu ứng dụng đang mong đợi một blob dưới data key.

## 10. Thay đổi path có thể làm ứng dụng không tìm thấy cấu hình

Khi thay đổi `prefix`, `default-context` hoặc `profile-separator`, ứng dụng sẽ tìm các path khác. Consul không tự di chuyển dữ liệu cũ sang path mới.

Ví dụ đổi:

```yaml
prefix: config
default-context: application
profile-separator: ','
```

thành:

```yaml
prefix: configuration
default-context: shared
profile-separator: '::'
```

Ứng dụng sẽ tìm `configuration/billing-api::prod/` thay vì `config/billing-api,prod/`. Nếu chỉ cập nhật application mà không sao chép hoặc di chuyển các key tương ứng, Config Client có thể không tìm thấy giá trị mong muốn.

Quy trình đổi naming an toàn:

1. Ghi lại các context cũ và key đang được sử dụng.
2. Tạo các context mới theo root, default context và separator mới.
3. Copy dữ liệu sang path mới và kiểm tra ACL/policy tương ứng.
4. Triển khai thử một client với cấu hình mới; kiểm tra `Environment` và giá trị đã bind.
5. Chuyển các ứng dụng còn lại theo nhóm, theo dõi lỗi thiếu cấu hình.
6. Chỉ xóa path cũ sau khi xác nhận không còn client sử dụng.

Trong giai đoạn chuyển tiếp, có thể duy trì cả path cũ và mới, nhưng phải tránh hai nơi nhận các giá trị khác nhau mà không có quy tắc sở hữu rõ ràng.

## 11. Kiểm tra đường dẫn thực tế trong Consul

Với ví dụ `prefix=configuration`, `default-context=shared`, `profile-separator=::`, `spring.application.name=billing-api` và profile `prod`, hãy kiểm tra các key dưới:

```text
configuration/billing-api::prod/
configuration/billing-api/
configuration/shared::prod/
configuration/shared/
```

Có thể dùng Consul UI hoặc HTTP API/CLI phù hợp với phiên bản Consul để đọc các key prefix. Ví dụ với Consul CLI trong môi trường local:

```bash
consul kv get -recurse configuration/billing-api::prod/
consul kv get -recurse configuration/billing-api/
consul kv get -recurse configuration/shared::prod/
consul kv get -recurse configuration/shared/
```

Nếu dùng ACL, lệnh cần token có quyền đọc prefix tương ứng. Không đưa token thật vào shell history hoặc log CI. Có thể dùng `CONSUL_HTTP_TOKEN` từ secret manager hoặc môi trường chạy được bảo vệ.

Ở phía Spring Boot, kiểm tra log Config Data và `Environment`. Nếu bật Actuator `env`, chỉ expose trong mạng quản trị có xác thực và masking; endpoint này có thể tiết lộ cấu trúc hoặc giá trị cấu hình.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không tìm thấy key nào | Sai `prefix`, sai Consul host/port, sai mount hoặc token thiếu quyền |
| Chỉ nhận cấu hình dùng chung | `spring.application.name`/`spring.cloud.consul.config.name` không khớp context riêng |
| Không nhận cấu hình profile | `spring.profiles.active` không như mong đợi hoặc `profile-separator` khác path đã ghi |
| Ứng dụng dùng giá trị shared thay vì app-specific | Path ứng dụng sai, key thiếu ở context cụ thể hoặc property source không được nạp |
| Hai môi trường đọc nhầm cùng cấu hình | `default-context`/profile naming chưa tách rõ hoặc profile không được kích hoạt |
| Đổi separator xong mất cấu hình | Dữ liệu vẫn nằm ở path cũ dùng dấu phẩy |
| YAML blob không được parse | `format` không phải YAML, thiếu `data-key` hoặc nội dung blob không hợp lệ |
| Client báo lỗi ACL | Token không có quyền `read` đúng prefix/context |

Hãy debug theo thứ tự: kết nối Consul, prefix root, application name, default context, profile active, profile separator, key path và cuối cùng là thứ tự property source. Kiểm tra path thực tế trước khi thay đổi nhiều thuộc tính cùng lúc.

## 13. Bảo mật và quản trị naming convention

`prefix`, `default-context` và `profile-separator` là quy ước định tuyến dữ liệu, không phải ranh giới bảo mật. ACL của Consul mới là cơ chế quyết định token nào được đọc hoặc ghi key path nào.

- Cấp token theo đúng prefix và context ứng dụng cần đọc.
- Tách quyền ghi của pipeline khỏi quyền đọc của runtime client.
- Không cấp token quản trị toàn cluster cho ứng dụng chỉ cần đọc cấu hình.
- Dùng TLS tới Consul Agent và bảo vệ token bằng secret manager.
- Review thay đổi path cùng thay đổi ACL; chuyển path mà quên ACL sẽ làm client mất quyền đọc.
- Không lưu plaintext secret nếu chính sách yêu cầu dùng Vault hoặc secret manager chuyên dụng.
- Thống nhất naming convention giữa các team để tránh tạo nhiều root hoặc separator không cần thiết.

Một quy ước dễ duy trì là dùng một `prefix` theo domain, `default-context` cho cấu hình chung, application name nhất quán với service name và giữ separator mặc định nếu không có xung đột naming. Chỉ tùy chỉnh khi có lý do cụ thể và có kế hoạch migration.

## 14. Checklist trước khi triển khai

- [ ] Xác nhận `spring.application.name` hoặc `spring.cloud.consul.config.name`.
- [ ] Chọn `prefix` và xác minh root tương ứng tồn tại trong Consul KV.
- [ ] Chọn `default-context` cho cấu hình dùng chung.
- [ ] Chọn `profile-separator` và thống nhất với path được ghi.
- [ ] Liệt kê bốn context theo application/profile và kiểm tra thứ tự ưu tiên.
- [ ] Kiểm thử với profile mặc định và profile production.
- [ ] Nếu nhiều active profile, kiểm tra thứ tự PropertySource thực tế.
- [ ] Xác định dùng key-value, YAML hay PROPERTIES format và cấu hình `data-key` nếu cần.
- [ ] Nếu dùng explicit contexts, xác minh đường dẫn thay thế computed contexts.
- [ ] Cấp Consul ACL token chỉ đọc đúng path cần thiết.
- [ ] Khi đổi naming convention, copy dữ liệu và cập nhật ACL trước khi chuyển client.
- [ ] Kiểm tra Config Data import, fail-fast/optional và readiness khi Consul không khả dụng.

## 15. Tài liệu tham khảo

- [Spring Cloud Consul — Distributed Configuration](https://docs.spring.io/spring-cloud-consul/docs/current/reference/html/index.html#spring-cloud-consul-config): quy tắc context, Config Data import, tùy chỉnh prefix/default context/profile separator và định dạng YAML/Properties.
- [Spring Cloud Consul — Configuration Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html): tên thuộc tính cấu hình và giá trị mặc định theo release hiện hành.
- [Consul KV HTTP API](https://developer.hashicorp.com/consul/api-docs/kv): cách đọc, ghi và liệt kê key/value theo prefix.

`prefix` quyết định root của cây cấu hình; `default-context` xác định nguồn dùng chung; `profile-separator` xác định cách ghép profile vào context. Khi ba giá trị được thống nhất giữa ứng dụng, Consul KV và ACL policy, nhóm có thể tổ chức cấu hình theo lớp dùng chung, ứng dụng và môi trường mà vẫn kiểm soát được nguồn và thứ tự ưu tiên của từng thuộc tính.
