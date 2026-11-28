# Relaxed binding và ánh xạ tên thuộc tính sang biến môi trường

Trong một hệ thống Spring Boot có nhiều môi trường chạy, cùng một cấu hình có thể xuất hiện dưới nhiều dạng: `connect-timeout` trong YAML, `connectTimeout` trong Java, hoặc `ACME_BILLING_CONNECTTIMEOUT` trong biến môi trường. Spring Boot hỗ trợ **relaxed binding** để liên kết các cách viết tương đương này với cùng một thuộc tính có kiểu dữ liệu rõ ràng.

Kỹ thuật này đặc biệt hữu ích khi ứng dụng nhận cấu hình từ Spring Cloud Config Server. Config Server phân phối các property source theo ứng dụng, profile và label; Spring Boot hợp nhất chúng vào `Environment`, sau đó binder ánh xạ giá trị sang bean cấu hình. Hiểu đúng quy tắc đặt tên giúp nhóm vận hành ghi đè cấu hình bằng biến môi trường mà không tạo ra những khóa khác ngoài ý muốn.

## 1. Phân biệt tên thuộc tính và tên biến Java

Trong file cấu hình, nên viết tên thuộc tính theo dạng **lowercase kebab-case**: các từ viết thường và ngăn cách bằng dấu gạch nối. Ví dụ:

```yaml
acme:
  billing:
    connect-timeout: 2s
    read-timeout: 5s
    retry:
      max-attempts: 3
```

Bean Java có thể dùng camelCase theo quy ước của ngôn ngữ:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public record BillingProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @NotBlank String apiKey,
        @Valid Retry retry
) {
    public record Retry(@Min(1) int maxAttempts) {}
}
```

Đăng ký bean bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc dùng `@EnableConfigurationProperties(BillingProperties.class)`:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class BillingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BillingApplication.class, args);
    }
}
```

Khi ứng dụng khởi động, binder chuyển `acme.billing.connect-timeout` thành thành phần `connectTimeout` của record. Dấu gạch nối trong tên thuộc tính không cần xuất hiện trong tên trường Java. Binder cũng chuyển đổi giá trị văn bản sang kiểu đích, chẳng hạn `2s` thành `Duration`, `3` thành `int` và chuỗi thành `URI` hoặc enum nếu kiểu đích hỗ trợ chuyển đổi tương ứng.

`@ConfigurationProperties` phù hợp để gom một nhóm cấu hình có cấu trúc, hỗ trợ kiểu dữ liệu, validation và metadata. `@Value` phù hợp với một vài giá trị đơn lẻ; tuy nhiên, không nên dựa vào toàn bộ cơ chế relaxed binding của `@ConfigurationProperties` khi dùng `@Value`. Với placeholder, hãy dùng tên thuộc tính chuẩn, ví dụ `@Value("${acme.billing.connect-timeout}")`.

## 2. Quy tắc đổi tên thuộc tính thành biến môi trường

Spring Boot chuyển tên thuộc tính chuẩn sang tên biến môi trường theo các quy tắc sau:

1. Thay mỗi dấu chấm (`.`) phân cấp bằng dấu gạch dưới (`_`).
2. Loại bỏ dấu gạch nối (`-`), không thay dấu gạch nối bằng dấu gạch dưới.
3. Chuyển toàn bộ tên thành chữ hoa.

Ví dụ:

| Tên thuộc tính chuẩn | Tên biến môi trường |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `acme.billing.connect-timeout` | `ACME_BILLING_CONNECTTIMEOUT` |
| `acme.billing.retry.max-attempts` | `ACME_BILLING_RETRY_MAXATTEMPTS` |
| `logging.level.com.acme` | `LOGGING_LEVEL_COM_ACME` |

Điểm dễ nhầm là dấu gạch dưới trong biến môi trường biểu thị ranh giới giữa các phần của tên thuộc tính. Vì vậy, `ACME_BILLING_CONNECT_TIMEOUT` được phân tích như tên có thêm một cấp `timeout`, tương ứng gần với `acme.billing.connect.timeout`; nó không phải cách viết đúng của `acme.billing.connect-timeout`. Với thuộc tính có dấu gạch nối, hãy bỏ dấu gạch nối khi tạo biến môi trường.

Ví dụ triển khai cho cấu hình ở phần trước:

```bash
export ACME_BILLING_CONNECTTIMEOUT=4s
export ACME_BILLING_READTIMEOUT=8s
export ACME_BILLING_APIKEY='secret-from-deployment'
export ACME_BILLING_RETRY_MAXATTEMPTS=5
```

Trên Windows PowerShell, có thể đặt biến cho tiến trình hiện tại bằng cú pháp `$env:ACME_BILLING_CONNECTTIMEOUT = '4s'`. Cách khai báo phụ thuộc môi trường chạy, nhưng tên biến mà Spring Boot nhận được vẫn tuân theo quy tắc trên.

### Thuộc tính dạng danh sách

Với phần tử danh sách, đặt chỉ số số học thành một phần riêng và bao quanh chỉ số bằng dấu gạch dưới. Ví dụ thuộc tính `acme.billing.allowed-currencies[0]` được ánh xạ thành `ACME_BILLING_ALLOWEDCURRENCIES_0`:

```bash
export ACME_BILLING_ALLOWEDCURRENCIES_0=VND
export ACME_BILLING_ALLOWEDCURRENCIES_1=USD
```

Binder có thể dùng các giá trị này để tạo danh sách theo chỉ số. Cần kiểm tra quy tắc ghi đè khi cùng một danh sách được khai báo ở nhiều nguồn: một danh sách có độ ưu tiên cao hơn có thể thay thế danh sách ở nguồn thấp hơn thay vì nối thêm từng phần tử. Không nên giả định các phần tử từ YAML, Config Server và biến môi trường luôn được gộp thành một danh sách.

## 3. Áp dụng với Spring Cloud Config Client

Giả sử Config Server phục vụ cấu hình từ Git cho ứng dụng `billing-api`. Kho Git có thể chứa cấu hình dùng chung và cấu hình theo ứng dụng hoặc profile:

```text
application.yml
billing-api.yml
billing-api-prod.yml
```

Client khai báo tên ứng dụng, profile và Config Server trong cấu hình khởi động:

```yaml
spring:
  application:
    name: billing-api
  profiles:
    active: prod
  config:
    import: "optional:configserver:http://config-server:8888"
```

Nếu Config Server là bắt buộc để ứng dụng hoạt động, bỏ tiền tố `optional:` để ứng dụng báo lỗi khởi động khi không tải được cấu hình. Có thể chọn Git label bằng thuộc tính `spring.cloud.config.label`; ví dụ `SPRING_CLOUD_CONFIG_LABEL=release-2026` chọn label tương ứng nếu Config Server và repository có label đó.

Client gửi thông tin ứng dụng, profile và label để lấy một `Environment` từ Config Server. Các property source trả về được đưa vào Spring `Environment` cùng cấu hình cục bộ, biến môi trường và các nguồn khác. Sau đó, `@ConfigurationProperties` binder đọc thuộc tính theo tên chuẩn và thực hiện relaxed binding vào bean.

Hai bước này có trách nhiệm khác nhau:

- **Nạp và hợp nhất nguồn cấu hình** quyết định giá trị nào thắng khi nhiều nguồn khai báo cùng một khóa.
- **Relaxed binding** quyết định những cách viết tên nào có thể ánh xạ tới thuộc tính đích.

Relaxed binding không tự quyết định độ ưu tiên. Độ ưu tiên phụ thuộc thứ tự các property source trong Spring `Environment` và chính sách ghi đè mà Config Client được cấu hình. Vì vậy, không nên mặc định rằng biến môi trường luôn thắng cấu hình từ xa trong mọi cách triển khai. Khi cần một quy tắc cụ thể, hãy xác minh thứ tự nguồn cấu hình của ứng dụng đang chạy và kiểm thử với đúng phiên bản Spring Boot, Spring Cloud.

Ví dụ, cùng một khóa `acme.billing.connect-timeout` có thể xuất hiện trong `billing-api-prod.yml` trên Git và trong biến `ACME_BILLING_CONNECTTIMEOUT` ở container. Cả hai đều có thể bind vào `BillingProperties.connectTimeout`; giá trị cuối cùng là giá trị từ property source có độ ưu tiên cao hơn theo cấu hình thực tế.

## 4. Chuyển đổi kiểu và kiểm tra giá trị

Binder không chỉ đổi cách viết tên. Nó còn chuyển đổi giá trị văn bản sang kiểu Java, giúp bean cấu hình thể hiện đúng ý nghĩa:

| Kiểu Java | Ví dụ giá trị cấu hình | Ý nghĩa |
| --- | --- | --- |
| `Duration` | `250ms`, `5s`, `PT5S` | Khoảng thời gian |
| `DataSize` | `512KB`, `10MB` | Dung lượng |
| `boolean` | `true`, `false` | Bật hoặc tắt tính năng |
| `int` | `3` | Số lần thử lại |
| `List<String>` | Các phần tử YAML hoặc biến có chỉ số | Danh sách giá trị |
| `URI` | `https://api.example.com` | Địa chỉ tài nguyên |

Nên khai báo validation tại bean cấu hình để phát hiện lỗi sớm. Ví dụ `@NotNull` cho timeout bắt buộc, `@Min(1)` cho số lần thử lại và `@NotBlank` cho khóa API. Khi giá trị không chuyển đổi được hoặc vi phạm validation, ứng dụng nên thất bại ngay lúc khởi động với thông báo chỉ rõ thuộc tính gây lỗi, thay vì tiếp tục chạy với cấu hình sai.

Placeholder cũng là một cách lấy giá trị từ môi trường:

```yaml
acme:
  billing:
    api-key: ${BILLING_API_KEY:}
```

Ở ví dụ này, Spring phân giải placeholder `BILLING_API_KEY` và dùng chuỗi rỗng nếu biến không tồn tại. Đây là cơ chế phân giải placeholder trong `Environment`; nó khác với việc binder ánh xạ tên thuộc tính `acme.billing.api-key` thành `ACME_BILLING_APIKEY`. Hãy chọn một cách nhất quán và tránh khai báo cùng một bí mật ở nhiều nơi.

## 5. Quản lý bí mật và thay đổi cấu hình

Biến môi trường thường được dùng để đưa thông tin nhạy cảm vào container hoặc nền tảng triển khai mà không ghi trực tiếp giá trị vào kho Git. Tuy vậy, biến môi trường vẫn có thể bị lộ qua cấu hình container, quyền truy cập tiến trình, log hoặc công cụ chẩn đoán. Hãy dùng secret store của nền tảng hoặc cơ chế quản lý bí mật phù hợp, giới hạn quyền đọc, xoay vòng khóa và không ghi giá trị bí mật ra log.

Với Spring Cloud Config, kho Git nên chứa cấu hình có thể chia sẻ và lịch sử thay đổi có thể kiểm tra. Không commit mật khẩu, token hay private key ở dạng rõ. Dùng backend mã hóa hoặc tích hợp secret manager khi cần phân phối bí mật tập trung; kiểm soát quyền truy cập Config Server và repository theo nguyên tắc tối thiểu.

Thay đổi biến môi trường của một tiến trình đang chạy thường cần khởi động lại tiến trình hoặc triển khai lại container. Cơ chế refresh của Spring Cloud có thể cập nhật các property source từ xa và làm mới những bean hỗ trợ refresh, nhưng không thể tự sửa môi trường của tiến trình hệ điều hành. Với cấu hình từ Config Server, chỉ bật refresh hoặc Spring Cloud Bus khi ứng dụng thực sự cần cập nhật động; kiểm tra bean nào được rebind hoặc tạo lại, và xác định rõ cấu hình nào vẫn cần rollout.

## 6. Kiểm tra cấu hình hiệu lực

Khi một thuộc tính nhận giá trị không mong đợi, hãy kiểm tra theo thứ tự:

1. Xác nhận tên chuẩn mà bean cần, ví dụ `acme.billing.connect-timeout`.
2. Đổi tên sang biến môi trường theo đúng quy tắc; với ví dụ này phải là `ACME_BILLING_CONNECTTIMEOUT`.
3. Kiểm tra ứng dụng đang dùng đúng `spring.application.name`, active profile và Config Server label.
4. Xem property source nào cung cấp khóa và nguồn nào có độ ưu tiên cao nhất.
5. Kiểm tra giá trị có chuyển đổi được sang kiểu Java và có vượt qua validation hay không.
6. Xác nhận thay đổi có cần restart, refresh bean hay phát sự kiện qua Spring Cloud Bus.

Actuator có các endpoint như `env` và `configprops` để hỗ trợ kiểm tra nguồn thuộc tính và giá trị đã bind. Chỉ bật và bảo vệ các endpoint này bằng xác thực, phân quyền và chính sách che dữ liệu phù hợp; không công khai chúng trên mạng không tin cậy vì thông tin cấu hình có thể tiết lộ chi tiết hệ thống.

## 7. Ghi nhớ khi đặt tên

- Dùng kebab-case chữ thường làm dạng tên chuẩn trong YAML và `@ConfigurationProperties`.
- Khi chuyển sang biến môi trường, thay dấu chấm bằng `_`, bỏ dấu `-`, rồi viết hoa toàn bộ.
- Dùng `_0`, `_1`... cho chỉ số phần tử danh sách.
- Tách bạch việc chọn giá trị thắng giữa các property source với việc ánh xạ tên thuộc tính.
- Kiểm tra profile, label, kiểu dữ liệu, validation và yêu cầu restart/refresh khi cấu hình thay đổi.
- Giữ bí mật ngoài Git, giới hạn quyền truy cập và bảo vệ endpoint chẩn đoán.

Khi tuân thủ các quy tắc này, nhóm phát triển có thể giữ tên thuộc tính nhất quán giữa mã Java, YAML, Git và môi trường triển khai. Điều đó giúp cấu hình tập trung của nhiều ứng dụng Spring Boot dễ đọc, dễ ghi đè có chủ đích và dễ vận hành hơn.
