# Đặt giá trị mặc định an toàn và ghi rõ đơn vị của tham số

Kho cấu hình tập trung thường chứa nhiều tham số ảnh hưởng trực tiếp đến độ ổn định và bảo mật của ứng dụng: timeout, kích thước request, số kết nối đồng thời, số lần retry, giới hạn bộ nhớ hay trạng thái của tính năng. Một giá trị thiếu hoặc khó hiểu về đơn vị có thể khiến dịch vụ chờ quá lâu, tạo tải lớn lên hệ thống phụ thuộc hoặc hoạt động khác nhau giữa các môi trường.

Khi thiết kế repository cho Spring Cloud Config, cần xác định giá trị mặc định có hành vi an toàn, ghi đơn vị ngay trong giá trị hoặc tên key, và kiểm tra ràng buộc trước khi ứng dụng nhận cấu hình. Cấu hình chung nên cung cấp baseline có thể vận hành; cấu hình theo profile hoặc ứng dụng chỉ ghi đè khi có lý do cụ thể và đã được kiểm tra.

## 1. Vì sao giá trị mặc định và đơn vị quan trọng?

Giả sử hai ứng dụng cùng đọc key `client.timeout` nhưng một nhóm hiểu số `500` là mili giây, nhóm khác hiểu là giây. Một thay đổi tưởng như nhỏ có thể làm request timeout sau nửa giây hoặc sau hơn tám phút. Tương tự, `max-size: 10` không cho biết đó là 10 byte, 10 KB hay 10 MB.

Giá trị mặc định giúp ứng dụng có hành vi dự đoán được khi người triển khai chưa khai báo một tham số tùy chọn. Đơn vị rõ ràng giúp người viết cấu hình, người review và chương trình cùng hiểu một ý nghĩa. Hai nguyên tắc này cần đi cùng nhau:

- Mặc định phải có giới hạn và phù hợp với hành vi an toàn của tính năng.
- Đơn vị phải thể hiện rõ trong tên key hoặc giá trị, và kiểu dữ liệu trong Java cần phản ánh đúng đại lượng đó.
- Tham số bắt buộc cho bảo mật hoặc kết nối quan trọng phải được kiểm tra khi khởi động; không tự thay bằng một giá trị dễ dãi chỉ để ứng dụng chạy tiếp.

Không có một bộ giá trị mặc định phù hợp cho mọi dịch vụ. Các con số trong bài là baseline minh họa để bắt đầu thiết kế; cần điều chỉnh theo SLA, lưu lượng, giới hạn tài nguyên và kết quả kiểm thử tải của hệ thống.

## 2. Đặt baseline trong kho cấu hình

Với Spring Cloud Config dùng Git, có thể đặt các giá trị dùng chung trong `application.yml`, sau đó chỉ ghi đè phần cần thiết ở cấu hình theo môi trường hoặc theo ứng dụng.

Ví dụ cấu trúc repository:

```text
config-repo/
├── application.yml
├── application-dev.yml
├── application-prod.yml
├── order-service.yml
└── order-service-prod.yml
```

Ý nghĩa:

- `application.yml`: baseline dùng chung cho các ứng dụng.
- `application-dev.yml`: giá trị phù hợp với môi trường phát triển.
- `application-prod.yml`: giá trị chung đã được duyệt cho production.
- `order-service.yml`: tham số riêng của `order-service`.
- `order-service-prod.yml`: phần ghi đè chỉ dành cho `order-service` ở production.

Đặt key có cùng ý nghĩa tại cùng một vị trí logic trong các tệp. Không tạo các tên như `timeout`, `timeoutValue`, `request-time` ở những ứng dụng khác nhau nếu chúng thực sự biểu diễn cùng một loại thời gian. Quy ước thống nhất giúp có thể so sánh, rà soát và tự động kiểm tra cấu hình.

Ví dụ baseline trong `application.yml`:

```yaml
app:
  http:
    connect-timeout: 500ms
    read-timeout: 3s
    max-connections: 50
    max-request-size: 2MB

  retry:
    max-retries: 2
    initial-backoff: 200ms
    max-backoff: 2s

  features:
    bulk-import-enabled: false
```

Các key được đặt tên theo ý nghĩa: timeout là thời lượng, `max-connections` là số lượng kết nối, `max-request-size` là kích thước dữ liệu và `bulk-import-enabled` là cờ bật/tắt. Giá trị mặc định giới hạn kết nối, request size và số lần retry; tính năng có thể tạo tải lớn được tắt cho đến khi có quyết định bật rõ ràng.

## 3. Thế nào là một giá trị mặc định an toàn?

Giá trị an toàn phụ thuộc vào tác động khi tham số được dùng. Hãy xem xét hậu quả của giá trị đó khi ứng dụng gặp lỗi, khi tải tăng và khi hệ thống phụ thuộc không phản hồi.

### 3.1. Đặt giới hạn thay vì vô hạn

Các tham số tài nguyên nên có giới hạn hữu hạn:

- Timeout kết nối và timeout đọc cần có giá trị hữu hạn để request không chờ mãi.
- Connection pool cần giới hạn số kết nối để tránh tạo tải không kiểm soát lên database hoặc dịch vụ bên ngoài.
- Kích thước request, upload và message cần có giới hạn để tránh tiêu thụ bộ nhớ quá mức.
- Retry cần giới hạn số lần thử và khoảng chờ; retry vô hạn có thể làm hệ thống phụ thuộc quá tải nặng hơn.

Không dùng `0`, số âm hoặc giá trị rất lớn nếu thư viện hiểu chúng là vô hạn, tắt timeout hoặc bỏ giới hạn. Ý nghĩa của `0` khác nhau giữa các thư viện; phải kiểm tra tài liệu của thành phần sử dụng trước khi chọn giá trị này.

### 3.2. Chọn mặc định theo hướng an toàn khi chưa có quyết định

Với các tính năng có thể phát sinh chi phí, thay đổi dữ liệu hoặc mở rộng bề mặt truy cập, trạng thái mặc định thường nên là tắt hoặc hạn chế. Ví dụ:

```yaml
app:
  features:
    bulk-import-enabled: false
    experimental-payment-flow-enabled: false

  access:
    allow-anonymous: false
```

Đây là các key do ứng dụng định nghĩa; chúng chỉ có hiệu lực khi mã nguồn bind và thực thi chúng. `allow-anonymous: false` thể hiện lựa chọn mặc định yêu cầu xác thực. Không được coi việc đặt key trong Git là đủ để bảo vệ endpoint nếu security configuration không sử dụng key đó.

Không dùng giá trị mặc định yếu cho thông tin bảo mật như mật khẩu, signing key, token, hoặc danh sách quyền. Bí mật phải được cấp từ secret manager hoặc cơ chế bảo mật tương ứng. Nếu thiếu một bí mật bắt buộc, ứng dụng nên báo lỗi rõ ràng thay vì dùng chuỗi rỗng, mật khẩu mẫu hoặc credential mặc định.

### 3.3. Phân biệt mặc định với cấu hình bắt buộc

Một tham số tùy chọn có thể có mặc định hợp lý, chẳng hạn kích thước request tối đa. Một tham số bắt buộc để xác thực hoặc kết nối tới hệ thống quan trọng có thể không có mặc định an toàn. Cần phân loại rõ:

| Loại tham số | Cách xử lý khi thiếu | Ví dụ |
|---|---|---|
| Tùy chọn, có thể hoạt động an toàn với baseline | Dùng mặc định hữu hạn | `read-timeout: 3s` |
| Bắt buộc theo môi trường | Kiểm tra và dừng khởi động nếu thiếu | URL database production, issuer xác thực |
| Bí mật | Lấy từ secret manager; lỗi nếu thiếu | Password, private key, API token |
| Tính năng rủi ro cao | Mặc định tắt, chỉ bật qua thay đổi được duyệt | Bulk import, thao tác ghi hàng loạt |

Nếu client dùng `optional:configserver:`, ứng dụng có thể khởi động khi Config Server không truy cập được. Chỉ dùng cách này khi các giá trị mặc định trong ứng dụng đủ để hoạt động an toàn và không bỏ qua tham số bắt buộc. Nếu cấu hình từ xa là điều kiện bắt buộc để kết nối hoặc bảo vệ dịch vụ, hãy để ứng dụng thất bại sớm khi không nạp được cấu hình.

## 4. Ghi rõ đơn vị của tham số

Có hai cách phổ biến để tránh nhập nhằng: dùng kiểu dữ liệu có đơn vị và hậu tố trong giá trị, hoặc ghi đơn vị trong tên key khi buộc phải dùng số nguyên.

### 4.1. Thời lượng: dùng hậu tố `ms`, `s`, `m`, `h`

Spring Boot có thể bind chuỗi thời lượng vào `java.time.Duration`. Ví dụ:

```yaml
app:
  http:
    connect-timeout: 500ms
    read-timeout: 3s
  retry:
    initial-backoff: 200ms
    max-backoff: 2s
```

Các giá trị này biểu diễn rõ mili giây và giây. Tránh cấu hình `timeout: 500` nếu không có quy ước đơn vị đi kèm. Khi cần dùng số nguyên theo mili giây, đặt tên key như `connect-timeout-ms: 500` và bind thành kiểu số nguyên có tên rõ ràng.

### 4.2. Kích thước: dùng hậu tố và kiểu `DataSize`

Với kích thước request, file hoặc buffer, có thể dùng các giá trị như `2MB`, `512KB` và bind vào `org.springframework.util.unit.DataSize`:

```yaml
app:
  http:
    max-request-size: 2MB
    upload-chunk-size: 512KB
```

Nếu một API hoặc thư viện chỉ nhận số byte, dùng key `max-request-size-bytes` và ghi rõ giá trị đã quy đổi. Không để `max-request-size: 2` rồi dựa vào việc người đọc tự đoán đơn vị.

### 4.3. Số lượng, tốc độ và tỷ lệ

Không phải tham số nào cũng là thời lượng hay kích thước. Với số lượng, tên key nên nói rõ đó là số phần tử hoặc kết nối:

```yaml
app:
  http:
    max-connections: 50
  retry:
    max-retries: 2
  rate-limit:
    requests-per-second: 100
  cache:
    hit-ratio-threshold: 0.85
```

`requests-per-second` nêu rõ tốc độ theo số request mỗi giây. `hit-ratio-threshold` dùng tỷ lệ từ `0` đến `1`; cần ghi rõ quy ước này trong tài liệu hoặc đổi tên thành `hit-ratio-percent` nếu muốn lưu giá trị từ `0` đến `100`. Tránh trộn hai quy ước trong các ứng dụng.

Với tiền tệ, luôn xác định đơn vị tiền tệ bằng trường riêng hoặc mã ISO như `VND`, `USD`; không lưu một số tiền đơn lẻ mà không cho biết loại tiền. Với thời điểm lịch, xác định múi giờ hoặc dùng UTC để tránh diễn giải khác nhau giữa các môi trường.

### 4.4. Chọn kiểu dữ liệu Java tương ứng

Khi bind cấu hình, chọn kiểu dữ liệu phản ánh đúng đại lượng:

| Đại lượng | Kiểu Java gợi ý | Ví dụ giá trị cấu hình |
|---|---|---|
| Thời lượng | `java.time.Duration` | `500ms`, `3s`, `2m` |
| Kích thước dữ liệu | `org.springframework.util.unit.DataSize` | `512KB`, `2MB` |
| Số kết nối, số lần retry | `int` hoặc `long` | `50`, `2` |
| Tỷ lệ | `BigDecimal` hoặc `double` theo yêu cầu | `0.85` hoặc `85` nếu key ghi rõ percent |
| Bật/tắt tính năng | `boolean` | `true`, `false` |

Không nên bind một thời lượng vào `long` rồi để mọi nơi tự hiểu đơn vị. Nếu dùng `long`, hãy quy định đơn vị ngay trong tên thuộc tính, ví dụ `readTimeoutMs` hoặc `read-timeout-ms`.

## 5. Bind và xác thực cấu hình bằng `@ConfigurationProperties`

`@ConfigurationProperties` gom các key liên quan vào một đối tượng có kiểu dữ liệu. Ví dụ record sau nhận các tham số trong nhóm `app.http`:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import org.springframework.util.unit.DataSize;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

@ConfigurationProperties(prefix = "app.http")
@Validated
public record HttpProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) @Max(200) int maxConnections,
        @NotNull DataSize maxRequestSize) {
}
```

Đăng ký properties scan ở lớp ứng dụng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
```

Để validation được kích hoạt, project cần có Jakarta Bean Validation implementation, thường được thêm qua `spring-boot-starter-validation`. Các ràng buộc `@NotNull`, `@Min` và `@Max` giúp ứng dụng từ chối cấu hình thiếu hoặc vượt giới hạn ngay khi khởi động. Có thể bổ sung kiểm tra quan hệ giữa các giá trị, ví dụ `max-backoff` phải lớn hơn hoặc bằng `initial-backoff`.

Record trên coi các trường là bắt buộc: repository cần cung cấp đủ key. Với tham số tùy chọn, có thể đặt giá trị mặc định trong class cấu hình bằng field initializer hoặc dùng `@DefaultValue` trên constructor binding ở phiên bản Spring Boot hỗ trợ. Dù dùng cách nào, cần có một nguồn xác định duy nhất cho giá trị baseline và kiểm tra rằng fallback trong binary không lệch khỏi baseline trong Git.

## 6. Ghi đè theo profile mà vẫn giữ baseline

Các môi trường có tải và giới hạn khác nhau có thể cần giá trị riêng. Hãy bắt đầu từ baseline chung rồi chỉ ghi đè các key thực sự cần thay đổi.

Ví dụ `application-prod.yml` tăng giới hạn kết nối sau khi đã kiểm thử tải:

```yaml
app:
  http:
    max-connections: 100
    max-request-size: 2MB
```

Ví dụ `order-service-prod.yml` điều chỉnh thời gian đọc vì dịch vụ phụ thuộc có độ trễ cao hơn:

```yaml
app:
  http:
    read-timeout: 5s
```

Không sao chép toàn bộ `application.yml` vào từng tệp profile. Khi baseline được cải thiện, các profile kế thừa sẽ nhận thay đổi mà không phải cập nhật nhiều bản sao. Chỉ ghi đè khi có dữ liệu vận hành hoặc yêu cầu môi trường chứng minh cần thiết.

Khi nhiều property source cùng khai báo một key, thứ tự ưu tiên quyết định giá trị cuối cùng. Biến môi trường, JVM system property, command-line argument và chính sách override của Spring Cloud Config cũng có thể tác động đến giá trị hiệu lực. Vì vậy, hãy kiểm tra Environment và `PropertySource` thực tế của client khi cần xác nhận, không chỉ đọc một tệp YAML.

## 7. Ví dụ đầy đủ: timeout và retry có giới hạn

Một cấu hình HTTP client có thể được tổ chức như sau:

```yaml
# application.yml
app:
  http:
    connect-timeout: 500ms
    read-timeout: 3s
    max-connections: 50
    max-request-size: 2MB
  retry:
    max-retries: 2
    initial-backoff: 200ms
    max-backoff: 2s
```

Ý nghĩa vận hành:

- Kết nối mới phải hoàn tất trong khoảng thời gian hữu hạn.
- Một lần đọc response có giới hạn thời gian riêng.
- Pool không mở số lượng kết nối vô hạn.
- Request lớn hơn giới hạn phải bị từ chối hoặc xử lý theo chính sách upload riêng.
- Retry có số lần tối đa và thời gian chờ có trần.

Retry chỉ nên áp dụng cho thao tác có thể thử lại an toàn, thường là request idempotent hoặc có idempotency key. Không retry mù quáng các thao tác ghi tiền, tạo đơn hàng hoặc thanh toán vì có thể tạo tác dụng phụ trùng lặp. Khi dịch vụ phụ thuộc đang quá tải, retry dồn dập còn có thể làm sự cố lan rộng; nên kết hợp backoff, jitter và circuit breaker theo đặc điểm hệ thống.

## 8. Xử lý khi cấu hình từ xa thiếu hoặc không truy cập được

Thiết kế giá trị mặc định cần tính đến thời điểm Config Client không lấy được cấu hình từ Config Server:

- Nếu mọi giá trị cần thiết đã có fallback an toàn trong ứng dụng, có thể cân nhắc `optional:configserver:` cho môi trường phù hợp.
- Nếu thiếu cấu hình sẽ khiến xác thực, kết nối database hoặc định tuyến sai, hãy coi remote config là bắt buộc và để ứng dụng dừng khởi động.
- Không dùng giá trị mặc định để che giấu lỗi cú pháp, sai profile, sai label hoặc thiếu secret.
- Ghi log lỗi theo key và nguồn cấu hình ở mức đủ chẩn đoán; không in giá trị bí mật.

Ví dụ: nếu `app.http.read-timeout` có mặc định `3s`, client vẫn có thể phục vụ an toàn khi thiếu override theo môi trường. Nhưng nếu `security.jwt.issuer-uri` bắt buộc cho xác minh token, không nên thay bằng một issuer giả hoặc tắt xác minh để ứng dụng tiếp tục chạy.

## 9. Quy trình review thay đổi giá trị mặc định

Trước khi merge một thay đổi vào kho cấu hình, reviewer nên kiểm tra:

1. **Ý nghĩa và đơn vị:** tên key, giá trị và kiểu Java cùng biểu diễn một đại lượng; không dùng số không có đơn vị cho thời lượng hoặc kích thước.
2. **Giới hạn:** timeout, số lần retry, số kết nối và kích thước payload có giới hạn hữu hạn, hợp lý.
3. **Hành vi khi thiếu:** phân biệt tham số tùy chọn, tham số bắt buộc và secret; không fallback sang giá trị yếu.
4. **Phạm vi ảnh hưởng:** xác định thay đổi nằm ở `application.yml`, profile hay ứng dụng cụ thể; kiểm tra các client khác có kế thừa key đó không.
5. **Tương thích:** xác minh mã nguồn đang bind key và kiểu dữ liệu tương ứng; kiểm tra thư viện sử dụng tham số có cùng đơn vị hay không.
6. **Kiểm thử:** kiểm tra cấu hình trong từng profile, validation khi thiếu/vượt giới hạn và hành vi dưới tải.
7. **Truy vết và rollback:** ghi nhận commit/label được phát hành và biết cách quay về phiên bản trước.

Không đưa mật khẩu, token, private key hoặc certificate private vào Git. Các giá trị bảo mật phải được lấy từ secret manager và có quyền truy cập tối thiểu. Repository cấu hình cần review tương tự mã nguồn vì một giá trị sai có thể làm thay đổi hành vi của nhiều ứng dụng mà không cần build artifact mới.

## 10. Các lỗi thiết kế thường gặp

- **`timeout: 500`:** không biết đơn vị; đổi thành `timeout: 500ms` hoặc `timeout-ms: 500`.
- **`max-size: 10`:** không rõ byte hay MB; dùng `max-request-size: 10MB` hoặc `max-request-size-bytes`.
- **Retry không giới hạn:** có thể làm hệ thống phụ thuộc quá tải; giới hạn số lần và backoff.
- **Dùng `0` để biểu thị mặc định:** thư viện có thể hiểu là vô hạn hoặc tắt tính năng; đọc tài liệu và chọn giá trị tường minh.
- **Cấu hình bắt buộc có fallback yếu:** có thể khiến dịch vụ khởi động trong trạng thái không an toàn; xác thực và dừng sớm khi thiếu.
- **Sao chép toàn bộ baseline vào từng profile:** tạo nhiều bản sao dễ lệch nhau; chỉ ghi đè phần khác biệt.
- **Không kiểm tra kiểu bind:** YAML có giá trị nhưng ứng dụng không dùng được hoặc diễn giải sai; dùng `@ConfigurationProperties` và validation.
- **Cho rằng Git là giá trị cuối cùng:** property source khác có thể ghi đè; kiểm tra Environment thực tế.

Một kho cấu hình tốt giúp người vận hành hiểu ngay mỗi tham số kiểm soát điều gì, được đo bằng đơn vị nào, có giới hạn ra sao và hành vi nào xảy ra khi thiếu. Với Spring Cloud Config, baseline dùng chung, override theo profile có kiểm soát và validation ở Config Client tạo nên cấu hình dễ review, dễ truy vết và an toàn hơn khi phân phối đến nhiều ứng dụng Spring Boot.
