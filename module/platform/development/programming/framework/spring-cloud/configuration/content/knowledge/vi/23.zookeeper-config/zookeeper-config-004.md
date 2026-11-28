# Chọn context tường minh và thứ tự nguồn thuộc tính

Spring Cloud Zookeeper Config đưa dữ liệu từ ZooKeeper vào Spring `Environment` dưới dạng nhiều `PropertySource`. Mỗi context là một vùng cấu hình trong namespace phân cấp của ZooKeeper. Ứng dụng có thể dùng các context được tính tự động từ tên application và profile, hoặc khai báo trực tiếp danh sách context cần đọc trong `spring.config.import`.

Việc chọn đúng context quyết định ứng dụng nhận được cấu hình dùng chung hay cấu hình riêng. Khi nhiều context cùng khai báo một property, thứ tự `PropertySource` quyết định giá trị nào thắng. Vì vậy, cần hiểu cách tạo context mặc định, cách chỉ định context tường minh và quy tắc ưu tiên trước khi tổ chức dữ liệu cho nhiều ứng dụng Spring Boot.

## 1. ZooKeeper context và Spring PropertySource

ZooKeeper cung cấp namespace phân cấp để lưu dữ liệu. Spring Cloud Zookeeper Config đọc các node cấu hình dưới một root mặc định là `/config` và tạo nhiều `PropertySource` dựa trên tên ứng dụng cùng các profile đang hoạt động.

Ví dụ ứng dụng có:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
```

Với root mặc định `config`, default context `application` và profile separator mặc định là dấu phẩy, các context được tạo theo thứ tự:

```text
config/billing-api,prod
config/billing-api
config/application,prod
config/application
```

Ý nghĩa:

- `config/billing-api,prod`: cấu hình riêng của `billing-api` trong profile `prod`.
- `config/billing-api`: cấu hình riêng của `billing-api`, không phụ thuộc profile.
- `config/application,prod`: cấu hình dùng chung cho profile `prod`.
- `config/application`: cấu hình dùng chung cho các ứng dụng.

Spring Cloud Zookeeper đặt nguồn cụ thể nhất ở đầu danh sách và nguồn ít cụ thể nhất ở cuối. Vì vậy, property trong `config/billing-api,prod` có thể ghi đè cùng property ở ba context còn lại. Các key không được khai báo ở context ưu tiên cao hơn vẫn có thể được lấy từ nguồn thấp hơn.

## 2. Các thuộc tính tạo context tự động

Spring Cloud Zookeeper Config dùng một số thuộc tính để tạo context path:

| Thuộc tính | Mặc định | Vai trò |
| --- | --- | --- |
| `spring.cloud.zookeeper.config.root` | `config` | Namespace gốc chứa cấu hình |
| `spring.cloud.zookeeper.config.name` | Giá trị `spring.application.name` | Tên application dùng để tìm context riêng |
| `spring.cloud.zookeeper.config.default-context` | `application` | Context dùng chung cho các ứng dụng |
| `spring.cloud.zookeeper.config.profile-separator` | `,` | Ký tự nối tên context với profile |
| `spring.cloud.zookeeper.config.enabled` | `true` | Bật hoặc tắt Zookeeper Config |

Ví dụ thay đổi root và context dùng chung:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
  cloud:
    zookeeper:
      config:
        enabled: true
        root: platform/config
        name: billing-api
        default-context: shared
        profile-separator: '::'
```

Với cấu hình này, bốn context tương ứng là:

```text
platform/config/billing-api::prod
platform/config/billing-api
platform/config/shared::prod
platform/config/shared
```

`name` có thể dùng để chọn tên context khác với `spring.application.name`. Đây là lựa chọn hữu ích khi tên service trong hệ thống triển khai khác với tên vùng cấu hình đã được chuẩn hóa. Tuy nhiên, nếu không cần ánh xạ riêng, giữ hai tên nhất quán sẽ giúp truy vết dễ hơn.

## 3. Thứ tự ưu tiên giữa các context

Với một application và một profile, thứ tự mặc định là từ cụ thể đến dùng chung:

1. Application + profile.
2. Application không gắn profile.
3. Default context + profile.
4. Default context không gắn profile.

Ví dụ `billing-api` chạy `prod` có các node sau:

```text
/platform/config/billing-api::prod/acme.billing.connect-timeout = 5s
/platform/config/billing-api/acme.billing.connect-timeout = 3s
/platform/config/shared::prod/acme.billing.connect-timeout = 4s
/platform/config/shared/acme.billing.connect-timeout = 2s
```

Giá trị được chọn cho `acme.billing.connect-timeout` là `5s`, vì property source `billing-api::prod` nằm ở đầu danh sách. Nếu khóa đó không có trong context đầu tiên, Spring tiếp tục tìm ở các context kế tiếp.

Một ví dụ khác cho thấy các khóa khác nhau có thể được hợp nhất:

```text
platform/config/shared/
  logging.level.root = INFO
  acme.http.read-timeout = 10s

platform/config/shared::prod/
  acme.http.read-timeout = 20s

platform/config/billing-api/
  acme.billing.retry.max-attempts = 3

platform/config/billing-api::prod/
  acme.http.connect-timeout = 5s
```

Kết quả mong đợi cho `billing-api`/`prod`:

| Property | Giá trị | Nguồn |
| --- | --- | --- |
| `logging.level.root` | `INFO` | `shared` |
| `acme.http.read-timeout` | `20s` | `shared::prod` |
| `acme.billing.retry.max-attempts` | `3` | `billing-api` |
| `acme.http.connect-timeout` | `5s` | `billing-api::prod` |

Thứ tự này mô phỏng cách Spring Cloud Config phân lớp cấu hình. Nguồn cụ thể hơn chỉ ghi đè các key trùng; nó không xóa những key chỉ tồn tại trong nguồn dùng chung.

## 4. Chỉ định context tường minh bằng Config Data import

Từ Spring Boot 2.4, Spring Cloud Zookeeper hỗ trợ Config Data import bằng `spring.config.import`. Đây là cách mặc định hiện đại để kết nối Zookeeper Config; không cần `bootstrap.yml` chỉ để import cấu hình theo cơ chế này.

Ví dụ khai báo hai context cụ thể:

```properties
spring.config.import=optional:zookeeper:zk.internal:2181/contextone;/context/two
```

Location trên yêu cầu Spring Cloud Zookeeper chỉ đọc hai context:

```text
/contextone
/context/two
```

Khi khai báo context trực tiếp, ứng dụng dùng chính các path được chỉ định thay cho bốn context tự động được tính từ application name, default context và profile. Điều này hữu ích khi cấu hình đã được tổ chức theo domain hoặc khi một ứng dụng cần lấy dữ liệu từ các vùng có tên riêng.

Có thể viết tương đương trong YAML:

```yaml
spring:
  config:
    import: 'optional:zookeeper:zk.internal:2181/contextone;/context/two'
```

Nếu muốn dùng connection string mặc định, có thể viết:

```yaml
spring:
  config:
    import: 'optional:zookeeper:'
```

Location sẽ kết nối tới `localhost:2181`. Có thể đặt địa chỉ bằng `spring.cloud.zookeeper.connect-string`; nếu connection string được ghi trực tiếp trong import location, giá trị trong location có độ ưu tiên cao hơn thuộc tính `connect-string`.

`optional:` cho phép ứng dụng tiếp tục nếu không thể kết nối tới Zookeeper cho nguồn import này. Bỏ tiền tố đó để việc kết nối Zookeeper là bắt buộc và startup thất bại khi không thể nạp cấu hình. Chỉ chọn optional nếu local fallback an toàn và các thuộc tính thiết yếu đã được kiểm tra.

## 5. Khi nào nên dùng context tự động?

Dùng context tự động khi tổ chức cấu hình theo quy ước thống nhất:

```text
<root>/<application><separator><profile>
<root>/<application>
<root>/<default-context><separator><profile>
<root>/<default-context>
```

Ví dụ với `root=config`, `application=billing-api`, `default-context=application`, `profile=prod` và separator `,`:

```text
config/billing-api,prod
config/billing-api
config/application,prod
config/application
```

Ưu điểm:

- Các ứng dụng có quy ước path giống nhau.
- Cấu hình dùng chung dễ quản trị tại default context.
- Cấu hình riêng của dịch vụ được tách theo application name.
- Profile-specific context hỗ trợ khác biệt theo môi trường.
- Ít phải khai báo danh sách path riêng trong từng ứng dụng.

Context tự động phù hợp khi nhiều ứng dụng dùng cùng root, naming convention và cách phân lớp cấu hình. Nhóm vận hành có thể dự đoán path từ tên ứng dụng và profile.

## 6. Khi nào nên dùng context tường minh?

Dùng explicit contexts khi một ứng dụng cần đọc một tập path cố định hoặc path không theo quy ước application/profile tự động.

Ví dụ một ứng dụng tổng hợp cần lấy cấu hình chung từ `platform/shared`, thông tin kết nối từ `teams/billing/database` và tích hợp thanh toán từ `integrations/payment`:

```yaml
spring:
  config:
    import: 'optional:zookeeper:zk.internal:2181/platform/shared;/teams/billing/database;/integrations/payment'
```

Lợi ích:

- Đường dẫn dữ liệu được thể hiện rõ trong cấu hình triển khai.
- Có thể chia sẻ một context giữa các ứng dụng có cấu trúc tên khác nhau.
- Có thể tách cấu hình theo nhóm sở hữu hoặc tích hợp.
- Không phụ thuộc hoàn toàn vào `spring.application.name`.

Đổi lại, từng ứng dụng cần quản lý danh sách context của nó. Khi thêm path hoặc đổi cấu trúc namespace, cần cập nhật import location, ACL và kiểm thử lại tất cả client liên quan.

Không nên giả định explicit contexts sẽ tự động bổ sung các context application/profile mặc định. Tài liệu Spring Cloud Zookeeper mô tả location tường minh là chỉ tải các context đã liệt kê. Nếu cần dữ liệu dùng chung hoặc profile-specific, hãy liệt kê các path đó rõ ràng hoặc chọn cách tạo context tự động.

## 7. Thứ tự nguồn khi có nhiều explicit contexts

Mỗi context được chỉ định tạo thành nguồn cấu hình trong `Environment`. Nếu hai context cùng chứa một property, thứ tự `PropertySource` thực tế quyết định giá trị thắng. Không nên chỉ dựa vào vị trí chuỗi trong `spring.config.import` để kết luận mà không kiểm tra kết quả của phiên bản đang dùng.

Ví dụ hai context cùng có khóa `acme.billing.region`:

```text
/platform/shared/acme.billing.region = global
/teams/billing/acme.billing.region = apac
```

Nếu ứng dụng import cả hai, hãy kiểm tra `Environment` để xác nhận nguồn nào được đặt ưu tiên cao hơn. Nếu hai giá trị có ý nghĩa khác nhau và cần cùng tồn tại, hãy đặt tên property riêng hoặc tách thành prefix theo miền nghiệp vụ:

```text
platform.region
billing.region
```

Nếu chủ đích là ghi đè, hãy ghi rõ quy ước nguồn authoritative, thứ tự dự kiến và một test xác nhận giá trị cuối cùng. Điều này tránh việc thay đổi thứ tự import hoặc nâng cấp dependency làm thay đổi kết quả ngoài dự kiến.

## 8. Nhiều profile đang hoạt động

Ứng dụng có thể bật một hoặc nhiều profile:

```yaml
spring:
  profiles:
    active: prod,cloud
```

Với context tự động, Spring Cloud Zookeeper tạo các nguồn profile-specific dựa trên application name, default context và `profile-separator`. Với profile separator mặc định, các path profile-specific được đặt theo tên context và profile. Khi nhiều profile cùng khai báo một key, thứ tự nguồn được nạp ảnh hưởng giá trị cuối cùng.

Đừng giả định thứ tự profile trong YAML có thể thay thế việc kiểm tra thứ tự `PropertySource`. Hãy kiểm tra danh sách nguồn thực tế ở client, nhất là khi cấu hình có cả `prod`, `cloud` và các profile bổ sung khác.

Với explicit contexts, các path đã liệt kê là nguồn được yêu cầu. Nếu muốn tách context theo profile, hãy khai báo path profile-specific tương ứng thay vì mong đợi thư viện tự thêm suffix profile vào mọi path tường minh.

## 9. Tổ chức key trong từng context

ZooKeeper context là một vùng namespace chứa các node key/value. Ví dụ:

```text
/config/application/
  logging.level.root = INFO
  acme.http.connect-timeout = 2s

/config/billing-api/
  acme.billing.retry.max-attempts = 3
  acme.billing.currency = VND

/config/billing-api,prod/
  acme.http.connect-timeout = 5s
```

Nên dùng tên key có namespace theo miền nghiệp vụ, ví dụ `acme.billing.*`, `acme.http.*` hoặc `logging.*`. Cách đặt tên này giảm xung đột khi nhiều context được hợp nhất vào cùng Spring `Environment`.

Không nên lưu các key quá chung như `url`, `username` hoặc `timeout` ở nhiều context nếu ứng dụng không có quy ước rõ ràng. Nếu các giá trị đại diện cho hai hệ thống khác nhau, dùng tên riêng như `billing.datasource.url` và `payment.gateway.url`.

## 10. Phân biệt context path với profile và root

Ba khái niệm thường bị nhầm:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Root | `configuration` | Namespace gốc chứa dữ liệu cấu hình |
| Context | `billing-api` hoặc `shared` | Nhóm key được đọc như một property source |
| Profile suffix | `,prod` hoặc `::prod` | Phân biệt cấu hình theo profile |

Ví dụ:

```yaml
spring:
  cloud:
    zookeeper:
      config:
        root: configuration
        default-context: shared
        profile-separator: '::'
```

Với application `billing-api` và profile `prod`, context tự động sẽ dùng root `configuration`, context application `billing-api`, default context `shared` và suffix `::prod`.

Đổi `root` không tự di chuyển dữ liệu. Đổi `default-context` không đổi `spring.application.name`. Đổi `profile-separator` không đổi tên profile. Khi thay một trong ba giá trị, các ứng dụng sẽ tìm path khác và cần dữ liệu tương ứng ở namespace mới.

## 11. Kiểm tra property source và giá trị cuối cùng

Sau khi khởi động client, cần xác minh hai điều: các context dự kiến đã được đọc và giá trị cuối cùng của từng key đúng như mong muốn.

Quy trình:

1. Xác nhận `spring.application.name`, active profiles và cấu hình `root`/`default-context`/`profile-separator`.
2. Dùng ZooKeeper CLI hoặc công cụ quản trị để kiểm tra các path dự kiến có tồn tại.
3. Gọi Config Data import hoặc khởi động client với đúng connection string.
4. Kiểm tra log khởi động để xác định context nào được đọc và có lỗi truy cập hay không.
5. Kiểm tra `Environment` và thứ tự property source; chỉ truy vấn giá trị nhạy cảm trong môi trường được bảo vệ.
6. So sánh giá trị đã bind vào `@ConfigurationProperties` với giá trị dự kiến.

Ví dụ bean cấu hình:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public record BillingProperties(
        @NotBlank String currency,
        @Min(1) int retryMaxAttempts) {
}
```

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Dùng validation cho các key bắt buộc để ứng dụng thất bại rõ ràng nếu context không tồn tại hoặc key bị thiếu.

Nếu cần Actuator `env` hoặc `configprops` để điều tra, chỉ expose trong mạng quản trị và bật masking phù hợp. Không log toàn bộ `Environment` hoặc giá trị secret.

## 12. ACL và quyền đọc theo context

Context path không phải cơ chế bảo mật. ZooKeeper ACL mới quyết định danh tính nào có quyền đọc hoặc ghi node. Khi chọn context tường minh, cần cấp quyền tương ứng cho từng path:

- Runtime client chỉ có quyền đọc context nó cần.
- Pipeline triển khai có quyền ghi đúng namespace được giao.
- Nhóm vận hành có quyền quản trị theo vai trò.
- Không cấp quyền quản trị toàn bộ ZooKeeper namespace cho service account của ứng dụng.

Spring Cloud Zookeeper hỗ trợ cung cấp thông tin xác thực ACL thông qua `CuratorFramework`, chẳng hạn cấu hình `addAuthInfo` trong bootstrap configuration đối với mô hình legacy. Với Config Data và phiên bản hiện hành, hãy cấu hình Curator/ZooKeeper authentication theo cách được release train hỗ trợ. Dùng TLS khi kết nối ZooKeeper nếu hạ tầng hỗ trợ, quản lý credential ngoài Git và audit thao tác đọc/ghi.

Khi đổi context path, phải cập nhật ACL trước hoặc đồng thời với việc chuyển client. Nếu path mới chưa có quyền đọc, ứng dụng có thể gặp lỗi dù dữ liệu đã được tạo đúng.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không tìm thấy cấu hình | Sai root, application name, default context hoặc context path tường minh |
| Chỉ có cấu hình chung, thiếu cấu hình riêng | `spring.cloud.zookeeper.config.name` không khớp tên context hoặc profile không đúng |
| Giá trị chung thắng giá trị ứng dụng | Property source không theo thứ tự dự kiến hoặc context cụ thể không được nạp |
| Profile-specific key không xuất hiện | Sai active profile hoặc profile separator không khớp path đã ghi |
| Explicit import vẫn đọc nhầm context mặc định | Location import chưa chứa path tường minh như mong muốn hoặc còn một import khác |
| Ứng dụng không kết nối ZooKeeper | Connection string, DNS, port, TLS hoặc network policy |
| Bị từ chối đọc path | ZooKeeper ACL thiếu quyền cho client identity |
| Giá trị Environment đúng nhưng bean sai | Binding, type conversion, validation hoặc nguồn cấu hình khác ghi đè |

Hãy kiểm tra theo thứ tự: kết nối ZooKeeper, root, context name, profile separator, path thực tế, ACL, danh sách property source và cuối cùng là bean binding. Không thay đổi đồng thời nhiều thuộc tính vì sẽ khó xác định nguyên nhân.

## 14. Quy trình chuyển từ context tự động sang context tường minh

Khi muốn thay naming convention hoặc chuyển sang explicit paths:

1. Ghi lại bốn context hiện đang được tính từ application và profile.
2. Liệt kê key và giá trị trong từng context; xác định các key trùng.
3. Thiết kế path mới theo nhóm ứng dụng, môi trường hoặc quyền sở hữu.
4. Tạo các path mới và sao chép dữ liệu đã được review.
5. Cấp ACL cho client và pipeline trên path mới.
6. Thay `spring.config.import` trong một client thử nghiệm để chỉ đọc explicit contexts.
7. So sánh property source order và giá trị bind với kết quả cũ.
8. Chuyển từng nhóm client, theo dõi lỗi thiếu key và quyền truy cập.
9. Chỉ xóa context cũ sau khi xác nhận không còn client sử dụng.

Trong giai đoạn chuyển tiếp, tránh để cùng một key có giá trị khác nhau ở cả path cũ và mới nếu chưa xác định rõ nguồn nào authoritative. Ghi nhận context path trong cấu hình triển khai để có thể truy vết và rollback.

## 15. Checklist lựa chọn context

- [ ] Xác nhận `spring.application.name` hoặc `spring.cloud.zookeeper.config.name`.
- [ ] Chọn root namespace phù hợp với quy ước của tổ chức.
- [ ] Chọn default context cho cấu hình dùng chung.
- [ ] Chọn profile separator và đồng bộ với cách đặt tên node.
- [ ] Liệt kê bốn context tự động theo đúng thứ tự ưu tiên.
- [ ] Xác định ứng dụng có phù hợp với naming convention tự động không.
- [ ] Nếu dùng explicit import, liệt kê đầy đủ mọi path cần đọc.
- [ ] Kiểm tra context tường minh thay thế các context tự động theo ý định.
- [ ] Kiểm tra property source order khi nhiều context có cùng key.
- [ ] Xác minh active profile và giá trị cuối cùng trong `Environment`.
- [ ] Cấp ACL chỉ đọc đúng path cho runtime client.
- [ ] Kiểm thử path không tồn tại, lỗi kết nối và ACL bị từ chối.

## 16. Tài liệu tham khảo

- [Spring Cloud Zookeeper — Distributed Configuration](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html): thứ tự bốn context tự động, explicit contexts qua `spring.config.import`, root, default context và profile separator.
- [Spring Cloud Zookeeper — Reference](https://docs.spring.io/spring-cloud-zookeeper/reference/): dependency, cấu hình kết nối và các tính năng tích hợp ZooKeeper.
- [Apache ZooKeeper — Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html): namespace phân cấp, znode và mô hình ACL.

Context tự động phù hợp khi các ứng dụng tuân theo quy ước root/application/profile chung; context tường minh phù hợp khi từng ứng dụng cần đọc một tập path xác định. Trong cả hai trường hợp, nguồn cụ thể nhất cần được đặt ưu tiên cao hơn, key trùng phải có quy tắc sở hữu rõ ràng và ACL phải giới hạn quyền đọc theo đúng namespace. Khi xác minh trực tiếp property source và giá trị đã bind, nhóm có thể kiểm soát cách cấu hình dùng chung và cấu hình riêng được hợp nhất trong Spring `Environment`.
