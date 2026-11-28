# Thứ tự giữa tệp cục bộ, nguồn import và cấu hình theo profile

Khi Spring Boot nhận cùng một khóa cấu hình từ nhiều nơi, giá trị được sử dụng phụ thuộc vào thứ tự ưu tiên của các `PropertySource` trong `Environment`. Với Spring Cloud Config Client, các nguồn thường gặp gồm tệp `application.yml` cục bộ, tệp theo profile, dữ liệu được import từ Config Server, biến môi trường, system property và tham số dòng lệnh. Hiểu đúng thứ tự này giúp giải thích vì sao giá trị trên Git khác với giá trị ứng dụng đang dùng.

Không có một quy tắc đơn giản rằng “cấu hình remote luôn thắng” hoặc “cấu hình local luôn thắng”. Cần phân biệt thứ tự giữa các tài liệu Config Data, quy tắc profile-specific, thứ tự các import và các nguồn bên ngoài Config Data như biến môi trường hoặc command line.

## 1. Spring Environment chọn giá trị như thế nào?

Spring `Environment` chứa một danh sách `PropertySource`. Khi ứng dụng hỏi giá trị của một khóa, Spring tìm nguồn theo thứ tự ưu tiên; nguồn có độ ưu tiên cao hơn và có chứa khóa đó sẽ quyết định giá trị được trả về.

Ví dụ cùng một khóa được khai báo ở ba nguồn:

```yaml
# application.yml
acme:
  billing:
    connect-timeout: 2s
```

```yaml
# application-prod.yml
acme:
  billing:
    connect-timeout: 3s
```

```bash
ACME_BILLING_CONNECTTIMEOUT=5s
```

Nếu biến môi trường được đưa vào `Environment` với độ ưu tiên cao hơn Config Data, ứng dụng sẽ dùng `5s`. Nếu không có biến môi trường, tài liệu profile `prod` có thể ghi đè tài liệu cơ sở và cung cấp `3s`.

Điều cần kiểm tra là **nguồn nào đứng trước trong Environment**, chứ không chỉ là khóa được viết trong file nào. Một tệp có chứa giá trị không có nghĩa nó là nguồn cuối cùng được chọn.

## 2. Thứ tự ưu tiên tổng quát của Spring Boot

Spring Boot có nhiều nguồn cấu hình ngoài Config Data. Theo thứ tự ưu tiên tổng quát, các nguồn như tham số dòng lệnh, `SPRING_APPLICATION_JSON`, system property và biến môi trường thường có thể ghi đè giá trị trong tệp cấu hình. Các nguồn test và thuộc tính được đặt trực tiếp trong ứng dụng kiểm thử cũng có thể có độ ưu tiên cao hơn tùy ngữ cảnh.

Bảng sau giúp định hướng khi điều tra; thứ tự đầy đủ còn có các nguồn như JNDI, servlet context, `@PropertySource` và test property source:

| Nguồn | Ví dụ | Vai trò thường gặp |
| --- | --- | --- |
| Command-line arguments | `--acme.billing.connect-timeout=6s` | Ghi đè khi chạy một tiến trình cụ thể |
| `SPRING_APPLICATION_JSON` | JSON truyền qua biến môi trường hoặc system property | Cung cấp nhiều thuộc tính trong một payload |
| JVM system properties | `-Dacme.billing.connect-timeout=6s` | Cấu hình theo tiến trình Java |
| OS environment variables | `ACME_BILLING_CONNECTTIMEOUT=5s` | Cấu hình theo container, host hoặc nền tảng triển khai |
| Config Data | `application.yml`, profile-specific files và imported config | Cấu hình mặc định, theo môi trường và từ Config Server |
| Default properties | `SpringApplication.setDefaultProperties(...)` | Giá trị dự phòng thấp nhất |

Đây là bảng định hướng chứ không phải danh sách thay thế tài liệu chính thức cho mọi loại ứng dụng. Khi có test framework, servlet environment hoặc `@PropertySource`, các nguồn bổ sung có thể tham gia vào thứ tự. Hãy xem `Environment` của tiến trình thực tế nếu cần kết luận chính xác.

## 3. Thứ tự giữa application.yml và tệp theo profile

Spring Boot nạp tài liệu cấu hình cơ sở và tài liệu dành cho profile đang hoạt động. Tài liệu profile-specific có độ ưu tiên cao hơn tài liệu không gắn profile trong cùng nhóm vị trí cấu hình.

Ví dụ:

```yaml
# application.yml
acme:
  billing:
    connect-timeout: 2s
    currency: VND
```

```yaml
# application-prod.yml
acme:
  billing:
    connect-timeout: 4s
```

Khi `prod` được kích hoạt:

- `acme.billing.connect-timeout` nhận `4s` từ `application-prod.yml`.
- `acme.billing.currency` vẫn nhận `VND` từ `application.yml` vì tài liệu profile không khai báo khóa này.

Profile-specific document chỉ ghi đè những khóa trùng. Các khóa khác vẫn được kế thừa từ nguồn có độ ưu tiên thấp hơn.

Nếu nhiều profile được kích hoạt, thứ tự profile có ý nghĩa. Ví dụ `spring.profiles.active=prod,cloud` áp dụng quy tắc last-wins cho các cấu hình trùng nhau; cấu hình của profile được xét sau có thể ghi đè cấu hình của profile trước. Hãy giữ thứ tự profile nhất quán trong môi trường triển khai.

## 4. Nguồn import được đặt ở đâu trong thứ tự Config Data?

Với Config Data API, một tài liệu có thể import nguồn khác bằng `spring.config.import`. Tài liệu được import được xử lý như một phần của Config Data và được đặt ngay dưới tài liệu khai báo import trong thứ tự xử lý. Vì vậy, giá trị từ nguồn import có độ ưu tiên cao hơn tài liệu đã khai báo import.

Ví dụ `application.yml` của Config Client:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:http://config-server:8888"

acme:
  billing:
    connect-timeout: 2s
```

Giả sử Config Server trả về:

```yaml
acme:
  billing:
    connect-timeout: 4s
    currency: VND
```

Giá trị từ nguồn Config Server được import có thể ghi đè `connect-timeout: 2s` trong tài liệu khai báo import. `currency` được bổ sung vào `Environment` dù không có trong tệp local.

Đây là quy tắc ở cấp tài liệu import. Nếu ứng dụng có nhiều tài liệu, nhiều location hoặc nhiều profile, thứ tự cuối cùng còn phụ thuộc vị trí khai báo import và thứ tự Config Data đã nạp. Vì vậy, khi cần biết một khóa cụ thể đang lấy từ đâu, hãy kiểm tra danh sách property source thực tế.

## 5. Thứ tự giữa nhiều nguồn import

Một ứng dụng có thể import nhiều nguồn Config Data. Thứ tự khai báo có ảnh hưởng khi nhiều nguồn cùng cung cấp một khóa. Các import được xử lý theo thứ tự xuất hiện; import được xử lý sau có thể có độ ưu tiên cao hơn import trước trong cùng ngữ cảnh khai báo.

Ví dụ minh họa hai file local:

```yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-primary:8888"
      - "optional:configserver:http://config-secondary:8888"
```

Nếu cả hai location cung cấp cùng một khóa, không nên dựa vào thứ tự tên server để suy luận kết quả. Hãy xác nhận thứ tự property source mà Config Data loader tạo ra trên phiên bản Spring Boot và Spring Cloud đang dùng. Trong production, tránh import nhiều Config Server độc lập nếu chưa có chính sách rõ ràng về nguồn nào là authoritative.

Với một Config Server duy nhất, thường nên giữ một location import rõ ràng và để server quản lý hợp nhất Git/composite repositories. Cách này giúp thứ tự ưu tiên giữa backend được quản trị ở một nơi và client dễ quan sát hơn.

## 6. Kết hợp tệp local, Config Server và profile

Một dự án có thể dùng local file để chứa thông tin kết nối ban đầu, Config Server để cung cấp cấu hình tập trung và profile-specific file để bổ sung cấu hình theo môi trường. Ví dụ:

```yaml
# application.yml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:http://config-server:8888"

acme:
  billing:
    connect-timeout: 2s
    currency: VND
```

```yaml
# application-prod.yml
acme:
  billing:
    currency: USD
    local-diagnostic-mode: false
```

```yaml
# Config Server: billing-api-prod.yml
acme:
  billing:
    connect-timeout: 4s
    retry:
      max-attempts: 5
```

Tệp local cơ sở khai báo import và giá trị mặc định. Config Server cung cấp các khóa tập trung cho `billing-api` và profile được yêu cầu. Tệp local theo profile bổ sung các giá trị dành cho profile `prod`. Cách các nguồn cùng tồn tại phụ thuộc vị trí và thứ tự import của Config Data; không nên suy ra kết quả chỉ từ ba đoạn YAML riêng lẻ.

Khi triển khai, hãy kiểm tra ít nhất các khóa trùng giữa ba nơi. Nếu `currency` xuất hiện trong cả local profile-specific và remote profile-specific, chỉ một nguồn có thể thắng; nguồn đó cần được xác định qua `Environment` của ứng dụng thay vì giả định rằng tên `*-prod.yml` quyết định ưu tiên.

## 7. Các nguồn ngoài Config Data có thể ghi đè cấu hình remote

Ngay cả khi Config Server thắng so với tài liệu local khai báo import, các nguồn có độ ưu tiên cao hơn Config Data vẫn có thể thay đổi giá trị cuối cùng.

Ví dụ:

```bash
export ACME_BILLING_CONNECTTIMEOUT=8s
```

Hoặc khi chạy JVM:

```bash
java -Dacme.billing.connect-timeout=7s -jar billing-api.jar
```

Tham số command line:

```bash
java -jar billing-api.jar --acme.billing.connect-timeout=9s
```

Trong trường hợp các nguồn này được bật và không có quy tắc đặc biệt thay đổi thứ tự, chúng có thể ghi đè giá trị `4s` mà Config Server trả về. Đây là hành vi hữu ích để thực hiện override có chủ đích trong một lần triển khai hoặc kiểm thử, nhưng cũng là nguồn gây sai khác nếu biến môi trường cũ còn tồn tại trong container.

Không nên khắc phục một giá trị sai bằng cách sửa Git ngay lập tức. Trước tiên hãy kiểm tra biến môi trường, JVM arguments, command line và JSON config để xem có nguồn ưu tiên cao hơn đang cung cấp giá trị hay không.

## 8. Cách kiểm tra nguồn và giá trị thực tế

### Kiểm tra response Config Server

Gọi endpoint với đúng application, profile và label:

```bash
curl -sS "http://localhost:8888/billing-api/prod/main"
```

Đọc `name`, `profiles`, `label`, `version` và `propertySources`. Response này cho biết những nguồn Config Server trả về và thứ tự của chúng, nhưng chưa bao gồm tất cả nguồn local, OS environment hoặc command line ở client.

### Kiểm tra Spring Environment

Nếu Actuator được bật và bảo vệ phù hợp, endpoint `env` có thể cho biết nguồn cung cấp một thuộc tính. Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env
```

Sau đó truy vấn `/actuator/env/acme.billing.connect-timeout` trên môi trường được phép chẩn đoán. Endpoint có thể tiết lộ tên nguồn hoặc giá trị nhạy cảm; không công khai nó trên mạng không tin cậy và giữ chính sách masking phù hợp.

Trong code, có thể kiểm tra giá trị cuối cùng bằng `Environment`:

```java
@Component
public class ConfigurationProbe {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    public Duration connectTimeout() {
        return environment.getProperty(
                "acme.billing.connect-timeout",
                Duration.class,
                Duration.ofSeconds(2)
        );
    }
}
```

Chỉ log các giá trị không nhạy cảm. Không log token, password, private key hoặc toàn bộ `Environment`.

## 9. Thứ tự ưu tiên và @ConfigurationProperties

`@ConfigurationProperties` bind từ `Environment` sau khi Config Data đã được nạp. Binder không tự chọn file nào thắng; nó nhận giá trị mà `Environment` đã phân giải theo thứ tự ưu tiên.

Ví dụ:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public record BillingProperties(
        @NotNull Duration connectTimeout,
        @Min(1) int retryMaxAttempts,
        @NotBlank String currency
) {}
```

Nếu bean nhận `connectTimeout` khác với giá trị trong Git, hãy kiểm tra theo thứ tự:

1. Config Server response có chứa khóa và giá trị mong đợi không?
2. Config Client có import đúng server, application, profile và label không?
3. Có local profile-specific document hoặc import khác khai báo cùng khóa không?
4. Có OS environment, JVM system property, `SPRING_APPLICATION_JSON` hoặc command line ghi đè không?
5. Kiểu dữ liệu và validation có làm giá trị bị từ chối hoặc chuyển đổi khác mong đợi không?

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Giá trị local không thắng giá trị Config Server | Nguồn import được đặt ưu tiên cao hơn tài liệu khai báo import |
| Profile-specific value không được áp dụng | Profile chưa active, tên file sai hoặc profile được yêu cầu tới Config Server khác với dự kiến |
| Giá trị từ profile này thắng profile khác | Thứ tự profile active và quy tắc last-wins |
| Config Server response đúng nhưng ứng dụng dùng giá trị khác | OS environment, system property, command line hoặc nguồn Config Data khác ghi đè |
| Giá trị thay đổi giữa local và production | Biến môi trường, profile, import URI, label hoặc thứ tự nguồn khác nhau |
| Khóa biến mất sau khi thêm import | Nguồn mới không cung cấp khóa, cấu hình optional bị bỏ qua hoặc tài liệu/profile không được nạp |

Khi chẩn đoán, lưu cả response từ Config Server và nguồn cuối cùng ở Config Client. Hai dữ liệu này trả lời hai câu hỏi khác nhau: server đã phân phối những gì và ứng dụng đã chọn giá trị nào sau khi hợp nhất toàn bộ nguồn.

## 11. Quy trình quản trị precedence trong môi trường nhiều ứng dụng

1. Dùng `application.yml` cho cấu hình cơ sở và khai báo Config Data import tại vị trí rõ ràng.
2. Dùng profile-specific files cho những khác biệt thật sự theo môi trường hoặc năng lực chạy.
3. Đặt cấu hình dùng chung và cấu hình theo ứng dụng trong Config Server; thống nhất profile và label giữa các dịch vụ.
4. Hạn chế khai báo cùng một khóa ở nhiều nguồn nếu không có lý do ghi đè rõ ràng.
5. Quy định nguồn nào được phép override bằng biến môi trường hoặc command line trong từng môi trường.
6. Kiểm tra `Environment` và response Config Server khi thay đổi cấu trúc import hoặc profile.
7. Bảo vệ endpoint chẩn đoán và không đưa giá trị bí mật vào log.

Một bảng quy ước có thể giúp nhóm tránh xung đột:

| Nhóm thuộc tính | Nguồn đề xuất | Quy tắc |
| --- | --- | --- |
| Giá trị mặc định an toàn | `application.yml` | Dùng làm fallback có chủ đích |
| Giá trị dùng chung nhiều dịch vụ | Config Server `application.yml` | Review và phát hành tập trung |
| Giá trị riêng dịch vụ | Config Server `<application>.yml` | Do nhóm sở hữu dịch vụ quản trị |
| Giá trị theo môi trường | Profile-specific config | Chỉ ghi đè khóa có khác biệt môi trường |
| Giá trị triển khai tạm thời | Environment variable hoặc command line | Có thời hạn, được ghi nhận trong metadata triển khai |
| Bí mật | Secret manager hoặc Vault | Không commit vào Git hay log |

## 12. Checklist kiểm tra trước khi phát hành

- [ ] Xác nhận đúng `spring.application.name`, active profiles và Config Server label.
- [ ] Kiểm tra vị trí `spring.config.import` và thứ tự các location được import.
- [ ] Liệt kê các khóa bị trùng giữa local base, local profile-specific và remote property sources.
- [ ] Xác nhận quy tắc ưu tiên profile khi có nhiều profile active.
- [ ] Kiểm tra biến môi trường, JVM system properties và command line của container.
- [ ] So sánh response Config Server với giá trị cuối cùng trong Spring `Environment`.
- [ ] Kiểm tra bean `@ConfigurationProperties` và validation.
- [ ] Bảo vệ Actuator, log và dữ liệu cấu hình nhạy cảm.

Thứ tự ưu tiên chỉ dễ vận hành khi nhóm biết mỗi khóa có một nguồn sở hữu chính và các lần ghi đè đều có chủ đích. Kết hợp hiểu biết về tài liệu local, nguồn import, profile-specific configuration và các nguồn bên ngoài Config Data sẽ giúp ứng dụng Spring Boot nhận cấu hình nhất quán, đồng thời rút ngắn thời gian tìm nguyên nhân khi giá trị thực tế khác với cấu hình trên Git.
