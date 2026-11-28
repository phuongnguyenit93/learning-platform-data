# Lựa chọn đường dẫn tường minh và tiền tố thuộc tính để tránh trùng khóa

Spring Cloud Vault đưa dữ liệu từ Vault vào Spring `Environment` dưới dạng các `PropertySource`. Khi một ứng dụng lấy cấu hình từ nhiều context Vault, các context có thể chứa những tên khóa giống nhau như `username`, `password`, `url` hoặc `token`. Nếu đưa chúng vào `Environment` mà không phân biệt tên, các giá trị có thể shadow nhau theo thứ tự ưu tiên và ứng dụng khó xác định nguồn thực sự của từng thuộc tính.

Hai công cụ giúp kiểm soát việc này là **contextual location** để chọn chính xác đường dẫn cần đọc và **query parameter `prefix`** để đổi tên thuộc tính khi đưa vào `Environment`. Kết hợp cả hai giúp một ứng dụng đọc nhiều context Vault mà vẫn giữ được ranh giới tên khóa rõ ràng.

## 1. Từ Vault context tới Spring PropertySource

Vault Key-Value (KV) backend lưu dữ liệu theo context path. Mỗi context có thể chứa nhiều cặp key-value. Ví dụ:

```text
secret/apps/billing/database
  username = billing_db_user
  password = <secret>
  url      = jdbc:postgresql://db.internal:5432/billing

secret/apps/billing/payment
  username = payment_gateway_user
  password = <secret>
  url      = https://payments.internal.example
```

Hai context có cùng các tên khóa `username`, `password` và `url`, nhưng chúng đại diện cho hai mục đích khác nhau. Nếu cả hai được đưa vào Spring Environment mà giữ nguyên tên thuộc tính, hai nguồn sẽ cùng khai báo `username`, `password` và `url`. Kết quả phân giải phụ thuộc thứ tự ưu tiên property source; một nguồn có thể che khuất giá trị từ nguồn còn lại.

Spring Cloud Vault tạo một `PropertySource` cho mỗi location/context được mount. Vì vậy, đường dẫn chọn context và tên thuộc tính xuất ra Environment là hai vấn đề riêng:

- **Context path** xác định Vault sẽ đọc dữ liệu ở đâu.
- **Property prefix** xác định các key từ context đó xuất hiện dưới tên nào trong Spring Environment.

## 2. Location mặc định và contextual location

Spring Cloud Vault hỗ trợ hai dạng Config Data location:

| Dạng | Ý nghĩa |
| --- | --- |
| `vault://` | Location mặc định; mount các secret backend được bật và áp dụng cách tính context mặc định |
| `vault:///<context-path>` | Contextual location; mount một context path được chỉ định tường minh |

Với location mặc định, KV backend thường lấy context theo tên ứng dụng và profile. Ví dụ, với backend mount `secret` và application name `billing-api`, các context thường gặp là:

```text
secret/billing-api
secret/billing-api/prod
```

Tên backend, application name, default context và profile có thể được cấu hình. Location mặc định tiện khi ứng dụng tuân theo quy ước đường dẫn chung. Nhưng khi cần đọc các context chuyên biệt hoặc nhiều vùng dữ liệu có cùng key names, contextual location cho phép khai báo chính xác nguồn cần lấy.

Ví dụ dùng hai context tường minh:

```yaml
spring:
  config:
    import:
      - "vault:///apps/billing/database"
      - "vault:///apps/billing/payment"
```

Các location được mount riêng thành các property source. Đường dẫn trong ví dụ là context path được cấu hình cho Vault KV backend; mount path của backend và phiên bản KV phải được thiết lập phù hợp trong ứng dụng. Không nhầm contextual location với URL REST đầy đủ của Vault.

Khi dùng contextual location, ứng dụng kiểm soát trực tiếp các context được import. Nếu muốn lấy thêm context mặc định, có thể kết hợp location tường minh với `vault://`; khi đó phải chủ động xem xét thứ tự import và thứ tự ưu tiên property source.

## 3. Dùng prefix để tránh trùng tên thuộc tính

Spring Cloud Vault cho phép thêm query parameter `prefix` vào từng location. Prefix được thêm nguyên văn vào trước mọi property name mà Vault trả về. Nếu muốn có dấu chấm ngăn cách giữa prefix và key gốc, hãy đặt dấu chấm ở cuối prefix.

Ví dụ:

```yaml
spring:
  config:
    import:
      - "vault:///apps/billing/database?prefix=billing.db."
      - "vault:///apps/billing/payment?prefix=billing.payment."
```

Với dữ liệu Vault ở trên, các property name được đưa vào Spring Environment sẽ là:

| Context Vault | Key gốc | Key sau prefix |
| --- | --- | --- |
| `apps/billing/database` | `username` | `billing.db.username` |
| `apps/billing/database` | `password` | `billing.db.password` |
| `apps/billing/database` | `url` | `billing.db.url` |
| `apps/billing/payment` | `username` | `billing.payment.username` |
| `apps/billing/payment` | `password` | `billing.payment.password` |
| `apps/billing/payment` | `url` | `billing.payment.url` |

Nhờ vậy, hai context vẫn có thể dùng các tên key đơn giản trong Vault nhưng không còn đụng tên nhau trong Spring Environment.

### Vì sao dấu chấm cuối prefix quan trọng?

Prefix được nối trực tiếp vào key, không tự thêm dấu phân cách. Ví dụ:

| Location prefix | Key trong Vault | Property name tạo ra |
| --- | --- | --- |
| `billing.db.` | `username` | `billing.db.username` |
| `billing.db` | `username` | `billing.dbusername` |
| `billing_` | `username` | `billing_username` |

Vì thế, nếu quy ước thuộc tính dùng dấu chấm, hãy ghi rõ dấu chấm cuối prefix. Prefix không tự động chuyển key thành nested object; nó chỉ thay đổi tên property theo phép nối chuỗi.

## 4. Tham chiếu các thuộc tính đã được prefix

Sau khi import, ứng dụng có thể dùng tên đầy đủ để bind cấu hình:

```yaml
spring:
  datasource:
    username: ${billing.db.username}
    password: ${billing.db.password}
    url: ${billing.db.url}

payments:
  gateway:
    username: ${billing.payment.username}
    password: ${billing.payment.password}
    url: ${billing.payment.url}
```

Hoặc bind trực tiếp vào hai nhóm `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "billing.db")
public record BillingDatabaseProperties(
        String username,
        String password,
        String url) {
}
```

```java
@ConfigurationProperties(prefix = "billing.payment")
public record PaymentGatewayProperties(
        String username,
        String password,
        URI url) {
}
```

Đăng ký các record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nên dùng validation cho các giá trị bắt buộc và tránh log object có chứa password/token.

## 5. Tổ chức đường dẫn Vault theo ứng dụng và mục đích

Một cấu trúc path dễ quản trị thường thể hiện môi trường, ứng dụng và mục đích sử dụng. Ví dụ:

```text
secret/
└── platform/
    └── billing/
        ├── database/
        ├── payment/
        └── messaging/
```

Ứng dụng có thể import riêng từng context:

```yaml
spring:
  config:
    import:
      - "vault:///platform/billing/database?prefix=billing.db."
      - "vault:///platform/billing/payment?prefix=billing.payment."
      - "vault:///platform/billing/messaging?prefix=billing.messaging."
```

Mỗi context chứa các key liên quan tới một tích hợp. Cách tổ chức này hỗ trợ policy Vault cấp quyền theo path, tách vòng đời credential và audit truy cập. Tên path cần thống nhất với mount và policy thực tế của Vault.

Không nên gom mọi secret của tổ chức vào một context `application` dùng chung nếu các ứng dụng không cần cùng quyền đọc. Tách path theo ứng dụng hoặc chức năng giúp giới hạn phạm vi khi một token hoặc service account bị lộ.

## 6. Kết hợp profile với đường dẫn tường minh

Location mặc định có thể tự tạo context theo active profile, ví dụ `secret/billing-api/prod`. Với contextual location, đường dẫn được chỉ định tường minh; không nên giả định Spring Cloud Vault tự nối thêm profile vào path đó.

Có thể đặt location riêng trong tài liệu profile-specific:

```yaml
# application.yml
spring:
  config:
    import:
      - "vault:///platform/billing/common?prefix=billing.common."
```

```yaml
# application-prod.yml
spring:
  config:
    import:
      - "vault:///platform/billing/prod/database?prefix=billing.db."
      - "vault:///platform/billing/prod/payment?prefix=billing.payment."
```

Khi profile `prod` hoạt động, ứng dụng nạp context chung cùng các location dành riêng cho production. Với profile `dev`, có thể khai báo các context khác trong `application-dev.yml`. Cách này làm rõ nguồn secret của từng môi trường thay vì phụ thuộc vào quy tắc ghép path ngầm định.

Khi có nhiều profile hoặc nhiều import, hãy kiểm tra thứ tự Config Data và property source thực tế. Một profile hoặc location được nạp sau có thể có ưu tiên khác; không nên để hai context cùng cung cấp một property name nếu chưa định nghĩa rõ nguồn nào được phép thắng.

## 7. Thứ tự ưu tiên giữa các Vault PropertySource

Mỗi contextual location được mount thành một `PropertySource` riêng. Có thể kết hợp nhiều Vault location với nhau hoặc với các hệ thống cấu hình khác trong `spring.config.import`. Thứ tự location và thứ tự Config Data ảnh hưởng đến việc nguồn nào thắng khi hai nguồn vẫn khai báo cùng một property name.

Ví dụ không có prefix:

```yaml
spring:
  config:
    import:
      - "vault:///platform/billing/database"
      - "vault:///platform/billing/legacy"
```

Nếu cả hai context có `username`, ứng dụng sẽ phải dựa vào thứ tự property source để phân giải. Điều này dễ gây shadowing và khó bảo trì. Cách tốt hơn là:

- Dùng prefix khác nhau khi hai giá trị cùng tồn tại và có ý nghĩa riêng.
- Chỉ giữ cùng tên khi chủ đích là override một giá trị theo thứ tự ưu tiên.
- Dùng một nguồn authoritative cho mỗi thuộc tính nếu không cần override.
- Kiểm tra `Environment` thực tế thay vì suy luận từ thứ tự dòng YAML.

Prefix giải quyết trùng tên trong Environment; nó không thay thế phân quyền Vault. Một client vẫn cần token có policy chỉ cho phép đọc những context mà ứng dụng được cấp quyền.

## 8. KV v1, KV v2 và đường dẫn API

Vault KV có hai phiên bản phổ biến:

| Phiên bản | Đặc điểm |
| --- | --- |
| KV v1 | API đọc/ghi trực tiếp tại context path, không có lớp versioned data |
| KV v2 | Có versioning; API sử dụng segment `data/` và response có cấu trúc bọc dữ liệu |

Spring Cloud Vault cần biết phiên bản backend để gọi đúng API. Với KV v2, thư viện xử lý segment API `data/` theo cấu hình backend version. Contextual location biểu diễn context cần đọc; không nên tự thêm `data/` chỉ vì thấy segment đó trong URL HTTP của Vault, nếu không sẽ có nguy cơ tạo path sai hoặc lặp segment.

Ví dụ cấu hình backend KV:

```yaml
spring:
  cloud:
    vault:
      kv:
        enabled: true
        backend: secret
        backend-version: 2
```

Tên thuộc tính cấu hình có thể khác giữa các release train cũ và mới. Hãy dùng metadata/configuration properties của đúng phiên bản Spring Cloud Vault đang triển khai và bảo đảm mount `secret` thực sự được bật ở KV v2.

## 9. Xử lý optional location và context không tồn tại

Một Vault Config Data location mặc định là bắt buộc. Có thể thêm `optional:` nếu muốn ứng dụng tiếp tục khi Vault integration bị tắt theo cấu hình:

```yaml
spring:
  config:
    import:
      - "optional:vault:///platform/billing/extra?prefix=billing.extra."
```

Lưu ý: context path không tồn tại và trả HTTP 404 có thể được bỏ qua theo cơ chế Config Data ngay cả khi location không có tiền tố `optional:`. Nếu muốn fail-fast khi path bắt buộc bị thiếu, cần xem xét cấu hình Vault Client Fail Fast của phiên bản đang dùng.

Không dùng optional cho một secret thiết yếu như database password nếu ứng dụng không thể hoạt động an toàn khi thiếu giá trị. Với các path bắt buộc, kiểm thử cả trường hợp path tồn tại, path sai tên, token không đủ policy và Vault không khả dụng.

## 10. Kiểm tra kết quả trong Spring Environment

Sau khi cấu hình import, cần xác minh tên property đã được prefix đúng. Có thể kiểm tra trong code:

```java
@Component
public class VaultPropertyCheck {

    private final Environment environment;

    public VaultPropertyCheck(Environment environment) {
        this.environment = environment;
    }

    public void verifyNames() {
        boolean databaseUserPresent = environment.containsProperty(
                "billing.db.username");
        boolean paymentUserPresent = environment.containsProperty(
                "billing.payment.username");

        if (!databaseUserPresent || !paymentUserPresent) {
            throw new IllegalStateException(
                    "Required Vault properties are missing");
        }
    }
}
```

Kiểm tra sự hiện diện của key mà không in giá trị bí mật. Nếu dùng Actuator `env` hoặc `configprops`, chỉ bật trong môi trường quản trị được bảo vệ và kiểm tra masking trước khi truy vấn.

Khi kiểm thử, nên tạo hai context có cùng tên key nhưng giá trị thử nghiệm khác nhau. Xác nhận:

1. Cả hai location đều được mount thành property source.
2. Prefix tạo ra đúng property name, kể cả dấu chấm cuối.
3. Placeholder hoặc `@ConfigurationProperties` đọc đúng context.
4. Không có property source khác ghi đè ngoài ý muốn.
5. Token chỉ đọc được path cần thiết theo Vault policy.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Property không xuất hiện | Sai context path, sai mount, token không có quyền hoặc backend KV chưa bật |
| Hai secret cùng tên bị ghi đè | Không dùng prefix hoặc prefix giống nhau |
| Property name bị dính chữ | Prefix thiếu dấu phân cách cuối, ví dụ `billingdb.username` |
| KV v2 trả 404 | Sai mount/backend version hoặc nhầm context path với API path có `data/` |
| Ứng dụng đọc nhầm secret | Import order hoặc property source khác đang shadow key |
| Profile không lấy đúng path | Contextual location không tự ghép profile; cần khai báo path theo profile |
| Startup bỏ qua path bắt buộc | Context 404 bị skip hoặc location được đánh dấu optional; cần cấu hình fail-fast và kiểm tra log |

Khi debug, xác định lần lượt: Vault mount có tồn tại không, context path có đúng không, token có quyền đọc không, Spring Cloud Vault có tạo property source không, prefix có được áp dụng đúng không và giá trị cuối cùng có bị nguồn khác ghi đè không.

## 12. Bảo mật và quản trị prefix/path

Đường dẫn tường minh và prefix giúp tránh nhầm lẫn thuộc tính, nhưng không phải cơ chế bảo mật độc lập. Hãy kết hợp với các nguyên tắc:

- Dùng AppRole, Kubernetes auth hoặc workload identity phù hợp; tránh token root hoặc token dài hạn dùng chung.
- Cấp policy chỉ đọc đúng path mà ứng dụng cần.
- Tách path theo ứng dụng, môi trường và mục đích sử dụng.
- Dùng TLS và xác minh certificate khi kết nối Vault.
- Không log giá trị secret, token hoặc toàn bộ `Environment`.
- Theo dõi audit device của Vault và rotation/renewal của token, lease.
- Review thay đổi path, prefix và policy cùng nhau để tránh vô tình mở rộng quyền đọc.

Tên prefix nên phản ánh miền nghiệp vụ hoặc nguồn dữ liệu, chẳng hạn `billing.db.`, `billing.payment.` hoặc `billing.messaging.`. Tránh prefix quá chung như `config.` nếu nhiều hệ thống cùng import, vì vẫn có thể xảy ra va chạm với property source khác.

## 13. Checklist thiết kế Vault location

- [ ] Xác định backend mount và phiên bản KV v1/v2.
- [ ] Chọn `vault://` mặc định hay contextual location cho từng context.
- [ ] Ghi rõ context path theo ứng dụng, profile và mục đích.
- [ ] Dùng `prefix` khác nhau khi các context có cùng key names.
- [ ] Đặt dấu chấm cuối prefix nếu muốn property dạng `prefix.key`.
- [ ] Kiểm tra thứ tự import và property source precedence.
- [ ] Không tự thêm `data/` vào contextual path nếu thư viện đã xử lý KV v2 API mapping.
- [ ] Quyết định location nào bắt buộc và location nào có thể optional.
- [ ] Kiểm tra Vault policy chỉ cấp quyền đọc path cần thiết.
- [ ] Xác minh tên property trong Environment mà không in giá trị secret.
- [ ] Kiểm thử path sai, token thiếu quyền, profile khác và key trùng.

## 14. Tham khảo tài liệu chính thức

- [Spring Cloud Vault — Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): default/contextual locations, import order và `prefix` query parameter.
- [Spring Cloud Vault — Secret Backends](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html): KV backend, application/profile context và cấu hình KV v1/v2.
- [Spring Vault — Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html): cách Vault property được đưa vào Spring `Environment`.

Đường dẫn tường minh cho biết ứng dụng cần đọc secret ở context nào; prefix cho biết các key của context đó được đặt tên ra sao trong Spring Environment. Dùng hai cơ chế cùng với thứ tự import và Vault policy rõ ràng sẽ tránh shadowing, giúp mỗi nhóm thuộc tính có tên ổn định và giữ được ranh giới truy cập theo ứng dụng.
