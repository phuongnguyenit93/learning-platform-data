# Giá trị mặc định, placeholder và tham chiếu giữa các thuộc tính

Trong hệ thống dùng **Spring Cloud Configuration**, nhiều ứng dụng Spring Boot lấy cấu hình từ một Spring Cloud Config Server. Server đọc cấu hình từ Git và trả về các property source theo tên ứng dụng, profile và label. Mỗi ứng dụng còn có thể nhận cấu hình từ file cục bộ, biến môi trường, thuộc tính JVM hoặc tham số dòng lệnh. Vì vậy, một ứng dụng cần biết cách dùng giá trị mặc định, thay thế placeholder và tham chiếu thuộc tính khác để cấu hình có thể tái sử dụng mà vẫn dự đoán được giá trị cuối cùng.

Bài học này tập trung vào ba kỹ thuật đó, cách chúng được phân giải trong `Environment` của Spring, và cách áp dụng chúng khi cấu hình được phân phối tập trung.

## 1. Phân biệt giá trị mặc định và placeholder

Một giá trị mặc định là giá trị được dùng khi cấu hình không cung cấp giá trị cụ thể. Trong Spring Boot, giá trị mặc định có thể được đặt ở nhiều lớp khác nhau:

| Cách khai báo | Ví dụ | Ý nghĩa |
|---|---|---|
| Trong file cấu hình | `app.timeout: 3s` | Tạo một giá trị trong property source; nguồn có độ ưu tiên cao hơn vẫn có thể ghi đè. |
| Trong mã Java | `private Duration timeout = Duration.ofSeconds(3);` | Giá trị ban đầu của đối tượng cấu hình; Binder có thể thay thế khi tìm thấy thuộc tính tương ứng. |
| Trong placeholder | `${app.timeout:3s}` | Dùng `3s` khi không tìm thấy `app.timeout` trong các nguồn cấu hình đang được phân giải. |

Ba cách trên có mục đích gần nhau nhưng không hoàn toàn tương đương. Giá trị trong `application.yml` vẫn là một thuộc tính cấu hình bình thường và tham gia vào thứ tự ưu tiên giữa các property source. Giá trị khởi tạo trong Java là mặc định ở cấp đối tượng. Phần sau dấu `:` của placeholder là phương án dự phòng ngay tại nơi tham chiếu thuộc tính.

Ví dụ, ứng dụng có thể đặt cấu hình cơ sở trong `application.yml`:

```yaml
app:
  region: ap-southeast-1
  timeout: 3s
  retry-count: 2
```

Khi chạy ở môi trường production, một property source có độ ưu tiên cao hơn có thể thay `app.timeout` thành `1s`. Nếu không có nguồn nào cung cấp `app.retry-count`, giá trị `2` trong file cấu hình cơ sở vẫn được sử dụng.

## 2. Cú pháp placeholder

Placeholder cho phép một giá trị cấu hình tham chiếu đến thuộc tính khác. Cú pháp cơ bản là:

```text
${ten-thuoc-tinh}
```

Nếu thuộc tính có thể không tồn tại, hãy thêm giá trị dự phòng:

```text
${ten-thuoc-tinh:gia-tri-mac-dinh}
```

Ví dụ trong YAML:

```yaml
spring:
  application:
    name: orders-service

app:
  display-name: "${spring.application.name:unnamed-service}"
  region: "${APP_REGION:ap-southeast-1}"
  partner-base-url: "${PARTNER_BASE_URL:https://sandbox.example.com}"
```

Kết quả phân giải sẽ phụ thuộc vào `Environment` tại thời điểm ứng dụng nạp cấu hình:

- Nếu `spring.application.name` có giá trị, `app.display-name` nhận giá trị đó. Nếu không, nó nhận `unnamed-service`.
- Nếu môi trường chạy cung cấp `APP_REGION`, giá trị đó được dùng; nếu không, ứng dụng dùng `ap-southeast-1`.
- Nếu không có `PARTNER_BASE_URL`, ứng dụng kết nối đến URL sandbox được khai báo làm dự phòng.

Placeholder có thể xuất hiện trong file `.properties`, YAML và các giá trị được đưa vào Spring thông qua những cơ chế cấu hình tương ứng. Khi viết YAML, nên đặt giá trị placeholder trong dấu nháy nếu chuỗi có ký tự đặc biệt hoặc dấu `:` để tránh nhầm lẫn với cú pháp YAML.

Có thể lồng placeholder để tạo nhiều tầng dự phòng:

```yaml
app:
  service-id: "${APP_SERVICE_ID:${spring.application.name:unknown-service}}"
```

Spring sẽ tìm `APP_SERVICE_ID` trước, sau đó thử `spring.application.name`, cuối cùng dùng `unknown-service`. Chỉ nên dùng nhiều tầng khi thứ tự dự phòng thể hiện một quy tắc rõ ràng; biểu thức quá sâu khiến việc truy tìm nguồn của giá trị trở nên khó khăn.

Nếu viết `${app.endpoint}` mà không có `app.endpoint` trong bất kỳ nguồn cấu hình nào và cũng không khai báo giá trị dự phòng, quá trình phân giải có thể thất bại với lỗi unresolved placeholder. Đây thường là hành vi mong muốn đối với thuộc tính bắt buộc vì ứng dụng dừng sớm thay vì chạy với cấu hình không hợp lệ.

## 3. Tham chiếu giữa các thuộc tính

Một thuộc tính có thể được tạo từ một hoặc nhiều thuộc tính khác. Cách này giúp tránh lặp lại hostname, cổng, tên dịch vụ hoặc tiền tố URL ở nhiều nơi.

```yaml
app:
  database:
    host: "${DB_HOST:localhost}"
    port: "${DB_PORT:5432}"
    name: orders
    url: "jdbc:postgresql://${app.database.host}:${app.database.port}/${app.database.name}"
```

Trong ví dụ trên, `app.database.url` tham chiếu đến `app.database.host`, `app.database.port` và `app.database.name`. Nếu `DB_HOST` được cung cấp từ môi trường, giá trị host đó được dùng để tạo URL. Nếu không, host mặc định là `localhost`. Cùng một nguyên tắc có thể áp dụng cho URL dịch vụ, tên topic, đường dẫn lưu trữ hoặc các thông số kết nối khác.

Placeholder không bị giới hạn trong cùng một file. Khi một thuộc tính đã có trong `Environment`, thuộc tính khác có thể tham chiếu đến nó dù giá trị được khai báo từ file cấu hình cục bộ, cấu hình từ Config Server, biến môi trường hay nguồn thuộc tính khác. Điều kiện là nguồn đó đã được nạp vào `Environment` và tên thuộc tính được viết đúng.

Nên tham chiếu bằng tên thuộc tính chuẩn, nhất quán theo dạng chữ thường và dấu gạch nối, ví dụ `app.database.connect-timeout`. Tránh tạo vòng tham chiếu như `service.a: ${service.b}` và `service.b: ${service.a}`. Vòng tham chiếu khiến việc phân giải không thể hoàn tất hoặc gây lỗi khó chẩn đoán.

## 4. Giá trị cuối cùng và thứ tự ưu tiên nguồn cấu hình

Spring Boot gom các nguồn cấu hình vào `Environment`. Khi cùng một khóa xuất hiện ở nhiều nguồn, giá trị từ nguồn có độ ưu tiên cao hơn được chọn. Các nguồn có độ ưu tiên thấp hơn vẫn hữu ích làm giá trị cơ sở khi nguồn ưu tiên cao không khai báo khóa đó.

Ví dụ, giả sử cấu hình cơ sở có `app.timeout: 3s`, file dành cho profile `prod` có `app.timeout: 1s`, và môi trường triển khai có `APP_TIMEOUT=750ms`. Giá trị cuối cùng phụ thuộc vào thứ tự ưu tiên của các property source đang hoạt động. Trong cấu hình Spring Boot thông thường, cấu hình theo profile ghi đè cấu hình không theo profile; biến môi trường, thuộc tính JVM và tham số dòng lệnh cũng có vị trí ưu tiên riêng trong thứ tự externalized configuration.

Với Spring Cloud Config, cấu hình từ xa được đưa vào `Environment` của client như các property source. Quy tắc ghi đè giữa cấu hình từ xa và cấu hình cục bộ có thể được điều chỉnh bằng các thuộc tính như `spring.cloud.config.allowOverride`, `spring.cloud.config.overrideNone` và `spring.cloud.config.overrideSystemProperties`. Vì vậy, không nên giả định rằng mọi file cục bộ luôn thắng cấu hình Git, hoặc cấu hình Git luôn thắng mọi nguồn khác. Hãy xác định rõ chính sách override của hệ thống và kiểm tra thứ tự nguồn thực tế khi có giá trị bất ngờ.

### Profile và label tác động đến nguồn giá trị

Spring Cloud Config Server thường trả cấu hình theo ba thông tin: tên ứng dụng, profile và label. Với client tên `orders-service`, profile `prod` và label `main`, client yêu cầu cấu hình tương ứng với bộ giá trị đó. Trong backend Git:

- `application.yml` thường chứa thuộc tính dùng chung cho nhiều ứng dụng.
- `orders-service.yml` chứa thuộc tính mặc định riêng của ứng dụng.
- `orders-service-prod.yml` chứa phần cấu hình dành cho profile `prod`.
- Label `main` chọn nhánh, tag hoặc phiên bản Git mà Config Server dùng để đọc cấu hình.

Một client Spring Boot hiện đại có thể kết nối Config Server bằng Config Data API:

```yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      label: main
  config:
    import: "optional:configserver:http://localhost:8888"
```

Tiền tố `optional:` cho phép ứng dụng tiếp tục khởi động nếu Config Server không truy cập được. Chỉ dùng lựa chọn này khi ứng dụng có thể hoạt động an toàn với các nguồn cấu hình còn lại. Nếu cấu hình tập trung là điều kiện bắt buộc để chạy, hãy bỏ `optional:` để lỗi kết nối được phát hiện ngay lúc khởi động.

Có thể kiểm tra dữ liệu mà Config Server trả về bằng endpoint dạng `/{application}/{profile}/{label}`, ví dụ:

```text
http://localhost:8888/orders-service/prod/main
```

Khi một placeholder nhận giá trị không như mong đợi, hãy kiểm tra cả ba thành phần này trước khi kết luận rằng cú pháp placeholder sai.

## 5. Đưa cấu hình vào mã ứng dụng

Với một vài thuộc tính đơn lẻ, `@Value` là cách đọc ngắn gọn và hỗ trợ placeholder có giá trị dự phòng:

```java
@Component
public class PartnerClientSettings {

    @Value("${app.partner-base-url:https://sandbox.example.com}")
    private URI baseUrl;

    @Value("${app.timeout:3s}")
    private Duration timeout;
}
```

Khi cấu hình có nhiều thuộc tính liên quan, nên nhóm chúng bằng `@ConfigurationProperties`. Cách này giúp cấu trúc cấu hình rõ ràng, hỗ trợ chuyển đổi kiểu dữ liệu và dễ kiểm tra tính hợp lệ.

```java
@ConfigurationProperties(prefix = "app")
@Validated
public class AppProperties {

    private String region = "ap-southeast-1";
    private Duration timeout = Duration.ofSeconds(3);

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Đăng ký quét các lớp cấu hình bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Trong ví dụ này, `region` và `timeout` có giá trị ban đầu nếu không có thuộc tính tương ứng. Khi cấu hình được bind, giá trị được cung cấp từ `Environment` sẽ thay thế giá trị ban đầu. Có thể dùng `@Validated` cùng Jakarta Bean Validation như `@NotBlank`, `@NotNull` hoặc `@Min` để ứng dụng từ chối cấu hình thiếu hay không hợp lệ. Với thuộc tính bắt buộc, ưu tiên kiểm tra tính hợp lệ thay vì đặt một giá trị dự phòng có thể che giấu lỗi triển khai.

## 6. Thay đổi cấu hình và refresh

Tham chiếu thuộc tính được phân giải khi Spring nạp cấu hình hoặc khởi tạo thành phần sử dụng giá trị đó. Khi file trong Git thay đổi, Config Server có thể đọc phiên bản mới, nhưng các instance đang chạy không tự động nhận mọi thay đổi chỉ vì commit đã được tạo.

Trong hệ thống Spring Cloud, có thể phát sự kiện refresh cho client bằng endpoint Actuator phù hợp, hoặc dùng Spring Cloud Bus để phân phối sự kiện đến nhiều instance. Những bean cần được khởi tạo lại theo cấu hình mới thường được đặt trong refresh scope bằng `@RefreshScope`. Endpoint quản trị như `/actuator/refresh` hoặc `/actuator/busrefresh` phải được cấu hình và bảo vệ phù hợp; chỉ mở các endpoint cần thiết cho hệ thống vận hành.

Ví dụ, khi `app.timeout` đổi từ `3s` thành `1s` trong Git, quy trình vận hành cần bảo đảm client đã lấy đúng profile và label, sự kiện refresh đã đến các instance cần cập nhật, và thành phần sử dụng timeout đã nhận giá trị mới. Nếu không có quy trình refresh, instance có thể tiếp tục dùng giá trị đã nạp trước đó cho đến khi khởi động lại.

## 7. Bảo vệ bí mật khi dùng placeholder

Placeholder giúp tách giá trị bí mật khỏi mã nguồn, nhưng bản thân cú pháp `${...}` không mã hóa hay bảo vệ dữ liệu. Không commit mật khẩu, token hoặc private key dưới dạng rõ trong repository cấu hình Git.

Thay vào đó, hãy lấy giá trị bí mật từ secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai, rồi đưa giá trị vào môi trường chạy bằng quyền truy cập tối thiểu. Ứng dụng có thể tham chiếu đến biến môi trường bắt buộc, chẳng hạn `${DB_PASSWORD}`, để khởi động thất bại nếu bí mật chưa được cung cấp. Nếu dùng cơ chế mã hóa của Spring Cloud Config, cần quản lý khóa mã hóa riêng, giới hạn quyền truy cập và bảo đảm bí mật không xuất hiện trong log hoặc thông tin chẩn đoán.

Không nên đặt mật khẩu giả định làm giá trị mặc định trong cấu hình dùng chung. Giá trị dự phòng phù hợp với những thiết lập không nhạy cảm và có thể chạy an toàn, chẳng hạn thời gian chờ mặc định hoặc endpoint sandbox trong môi trường phát triển.

## 8. Cách chẩn đoán khi giá trị không đúng

Khi ứng dụng nhận một giá trị khác dự kiến, hãy kiểm tra theo thứ tự sau:

1. **Tên khóa:** kiểm tra chính tả, tiền tố và cách viết tên thuộc tính trong YAML, placeholder và mã Java.
2. **Nguồn cấu hình:** xác định khóa được khai báo trong file cục bộ, file Git, biến môi trường, thuộc tính JVM hay tham số dòng lệnh.
3. **Profile và label:** xác nhận `spring.application.name`, profile đang hoạt động và label mà client yêu cầu.
4. **Thứ tự ưu tiên:** kiểm tra property source nào đang ghi đè khóa và chính sách override của Spring Cloud Config.
5. **Giá trị tham chiếu:** kiểm tra từng khóa được dùng trong placeholder, giá trị dự phòng và khả năng tồn tại vòng tham chiếu.
6. **Kiểu dữ liệu:** kiểm tra giá trị có chuyển đổi được sang kiểu Java mong muốn hay không, ví dụ `750ms` sang `Duration`.
7. **Refresh:** nếu cấu hình vừa thay đổi, xác nhận client đã nhận sự kiện refresh và bean sử dụng giá trị đã được cập nhật.

Một giá trị mặc định hữu ích giúp ứng dụng chạy ổn định khi thiếu cấu hình tùy chọn. Tuy nhiên, mặc định quá rộng có thể che giấu lỗi tên khóa, sai profile hoặc thiếu cấu hình production. Hãy chọn rõ thuộc tính nào được phép có mặc định và thuộc tính nào phải được cung cấp đầy đủ.

## 9. Tổng kết

- Giá trị trong file cấu hình là một phần của các property source và có thể bị nguồn ưu tiên cao hơn ghi đè.
- Giá trị khởi tạo trong `@ConfigurationProperties` là mặc định ở cấp đối tượng; giá trị sau dấu `:` trong placeholder là dự phòng khi khóa không được tìm thấy.
- Placeholder `${key}` tham chiếu một thuộc tính trong `Environment`; `${key:default}` bổ sung giá trị dự phòng.
- Có thể kết hợp nhiều thuộc tính để tạo URL hoặc cấu hình dẫn xuất, nhưng cần tránh vòng tham chiếu và biểu thức lồng quá phức tạp.
- Trong Spring Cloud Config, ứng dụng, profile, label và chính sách override quyết định những property source nào được nạp và giá trị nào được chọn.
- Thay đổi trong Git cần đi cùng quy trình refresh phù hợp; bí mật cần được lấy từ hệ thống quản lý bí mật thay vì lưu trực tiếp trong repository.
