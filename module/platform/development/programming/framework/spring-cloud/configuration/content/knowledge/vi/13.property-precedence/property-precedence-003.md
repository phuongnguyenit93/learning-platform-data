# Đối chiếu biến môi trường, system property và tham số dòng lệnh

Một thuộc tính Spring Boot có thể được khai báo trong file cấu hình, biến môi trường của hệ điều hành, Java system property hoặc tham số dòng lệnh. Khi cùng một khóa xuất hiện ở nhiều nguồn, Spring Boot chọn giá trị theo thứ tự ưu tiên của các `PropertySource`. Hiểu thứ tự này giúp xác định vì sao một dịch vụ đang chạy với timeout, cổng hoặc profile khác với giá trị trong repository cấu hình.

Với ba nguồn thường dùng khi triển khai, thứ tự ưu tiên từ thấp đến cao là: **biến môi trường → Java system property → tham số dòng lệnh của Spring Boot**. Nguồn có ưu tiên cao hơn sẽ ghi đè giá trị cùng khóa ở nguồn thấp hơn. Đây là một phần trong thứ tự đầy đủ của Spring Boot; các nguồn khác như `SPRING_APPLICATION_JSON`, thuộc tính test hoặc cấu hình mặc định cũng có thể tham gia.

## 1. Ba nguồn cấu hình khác nhau ở đâu?

| Nguồn | Cách cung cấp | Ví dụ | Phạm vi thường dùng |
|---|---|---|---|
| Biến môi trường | Đặt trong môi trường của tiến trình trước khi khởi chạy | `ORDERS_TIMEOUT=4s` | Container, Kubernetes, máy chủ, pipeline |
| Java system property | Truyền cho JVM bằng tùy chọn `-D` | `-Dorders.timeout=5s` | Một lần chạy JVM hoặc cấu hình ở service wrapper |
| Tham số dòng lệnh | Truyền cho ứng dụng bằng option bắt đầu với `--` | `--orders.timeout=750ms` | Ghi đè tạm thời khi chạy hoặc kiểm thử |

Ba cách trên cuối cùng đều đưa giá trị vào Spring `Environment`, nhưng chúng được tạo ở những thời điểm và lớp khác nhau:

- Biến môi trường thuộc hệ điều hành hoặc môi trường thực thi của tiến trình. JVM đọc chúng từ môi trường khi khởi chạy.
- Java system property thuộc JVM và được truy cập qua `System.getProperties()`. Tùy chọn `-D` được xử lý bởi JVM trước khi ứng dụng Spring Boot bắt đầu.
- Tham số `--key=value` được Spring Boot phân tích từ đối số ứng dụng và thêm vào `Environment` theo mặc định.

Không nên nhầm `-Dorders.timeout=5s` với `--orders.timeout=5s`. Cả hai có thể xuất hiện trên cùng một dòng lệnh, nhưng một cái là tùy chọn của JVM, cái còn lại là thuộc tính ứng dụng do Spring Boot xử lý.

## 2. Thứ tự ưu tiên trong Spring Boot

Spring Boot có một thứ tự `PropertySource` được xác định. Nguồn được xét sau có thể ghi đè nguồn được xét trước. Với ba nguồn đang học, thứ tự là:

1. Biến môi trường của hệ điều hành.
2. Java system properties.
3. Tham số dòng lệnh của Spring Boot.

Do đó:

```text
application.yml / Config Data
        |
        v
OS environment variables
        |
        v
Java system properties (-D)
        |
        v
Spring Boot command-line options (--key=value)
        |
        v
Giá trị hiệu lực trong Environment
```

Sơ đồ này tập trung vào các nguồn triển khai thường gặp. Trong thứ tự đầy đủ hiện hành, Config Data (bao gồm file cấu hình và dữ liệu được import) được xét trước biến môi trường; `SPRING_APPLICATION_JSON` nằm sau các tham số servlet/JNDI và trước tham số dòng lệnh; các nguồn dành cho test có thể có ưu tiên cao hơn nữa. Vì vậy, không nên dùng sơ đồ rút gọn này để suy luận mọi trường hợp phức tạp.

Ví dụ, file `application-prod.yml` khai báo:

```yaml
orders:
  timeout: 2s
```

Tiến trình đồng thời nhận các giá trị:

```text
ORDERS_TIMEOUT=4s
-Dorders.timeout=5s
--orders.timeout=750ms
```

Giá trị cuối cùng trong Spring `Environment` là `750ms`, vì tham số dòng lệnh có ưu tiên cao hơn system property và biến môi trường. Nếu bỏ tham số `--orders.timeout`, giá trị hiệu lực sẽ là `5s`. Nếu bỏ cả `-Dorders.timeout`, giá trị sẽ là `4s`. Nếu cả ba nguồn đều không cung cấp khóa, ứng dụng dùng giá trị từ Config Data hoặc default đã định nghĩa.

## 3. Đặt biến môi trường đúng tên

Tên thuộc tính Spring thường dùng dạng canonical với chữ thường và dấu chấm, ví dụ `orders.timeout` hoặc `spring.application.name`. Tên biến môi trường bị giới hạn bởi quy tắc của hệ điều hành, nên Spring Boot hỗ trợ relaxed binding theo các bước:

1. Thay dấu chấm (`.`) bằng dấu gạch dưới (`_`).
2. Bỏ dấu gạch nối (`-`).
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Tên thuộc tính | Tên biến môi trường |
|---|---|
| `server.port` | `SERVER_PORT` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `orders.timeout` | `ORDERS_TIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.service[0].other` | `MY_SERVICE_0_OTHER` |

Lưu ý dấu gạch nối bị loại bỏ, không chuyển thành dấu gạch dưới. Ví dụ `spring.main.log-startup-info` trở thành `SPRING_MAIN_LOGSTARTUPINFO`, không phải `SPRING_MAIN_LOG_STARTUP_INFO`.

Trên Linux, có thể đặt biến cho một lần chạy:

```bash
ORDERS_TIMEOUT=4s java -jar order-service.jar
```

Hoặc export trong shell hiện tại:

```bash
export ORDERS_TIMEOUT=4s
java -jar order-service.jar
```

Trong PowerShell:

```powershell
$env:ORDERS_TIMEOUT = '4s'
java -jar order-service.jar
```

Biến được đặt trong PowerShell chỉ có hiệu lực với tiến trình con khởi chạy từ phiên đó và các tiến trình con tiếp theo. Muốn thay đổi môi trường cho Windows Service, cần đặt biến trong cấu hình service hoặc môi trường hệ thống phù hợp rồi khởi động lại dịch vụ.

### Biến môi trường cho danh sách và Map

Với thuộc tính dạng danh sách, chỉ số phần tử được đặt giữa các dấu gạch dưới. Ví dụ:

```text
my.service[0].other
```

được ánh xạ thành:

```text
MY_SERVICE_0_OTHER
```

Khi bind biến môi trường vào `Map`, Spring Boot chuyển tên biến thành chữ thường trước khi tạo khóa Map. Ví dụ `MY_PROPS_VALUES_KEY=value` tạo khóa `key` trong map `values`. Giá trị bên phải dấu `=` vẫn giữ nguyên chữ hoa/chữ thường.

## 4. Truyền Java system property bằng `-D`

Java system property dùng tên thuộc tính trực tiếp, giữ dấu chấm và dấu gạch nối. Đặt `-D` trước `-jar` hoặc trước tên main class để JVM nhận tùy chọn đó:

```bash
java -Dorders.timeout=5s -Dserver.port=9090 \
  -jar order-service.jar
```

Trong ví dụ này:

- `orders.timeout` có giá trị system property là `5s`.
- `server.port` có giá trị system property là `9090`.
- Những giá trị này có thể ghi đè biến môi trường và Config Data có cùng tên.

Vị trí của `-D` rất quan trọng. Lệnh sau không đặt Java system property:

```bash
java -jar order-service.jar -Dorders.timeout=5s
```

Sau `-jar order-service.jar`, phần còn lại được chuyển cho ứng dụng như đối số chương trình. Spring Boot không coi `-Dorders.timeout=5s` là một JVM system property. Nếu muốn đặt thuộc tính Spring bằng đối số ứng dụng, dùng cú pháp `--orders.timeout=5s`.

System property cũng có thể được đặt trong script khởi động, service wrapper hoặc cấu hình JVM của nền tảng. Vì system property áp dụng cho một JVM, nó thường hữu ích khi một máy chạy nhiều ứng dụng và mỗi JVM cần giá trị khác nhau.

## 5. Ghi đè bằng tham số dòng lệnh Spring Boot

Mặc định, `SpringApplication` chuyển các đối số dạng option bắt đầu bằng `--` thành thuộc tính trong Spring `Environment`:

```bash
java -jar order-service.jar \
  --orders.timeout=750ms \
  --server.port=9100
```

Tham số dòng lệnh có ưu tiên cao hơn system property và biến môi trường. Nó phù hợp cho một lần chạy đặc biệt, thử nghiệm nhanh hoặc chẩn đoán một instance.

Các đối số không có dạng option, ví dụ `repair-index`, vẫn có thể được ứng dụng đọc qua `ApplicationArguments`, nhưng không tự động trở thành property có tên tương ứng trong `Environment`.

Spring Boot cho phép tắt việc đưa command-line options vào `Environment` bằng:

```java
SpringApplication application = new SpringApplication(OrderServiceApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
```

Chỉ dùng thiết lập này khi ứng dụng có chủ đích không cho phép tham số dòng lệnh ghi đè cấu hình. Nếu tắt, các option `--key=value` không còn tham gia thứ tự ưu tiên thuộc tính mặc định; ứng dụng vẫn có thể đọc chúng qua cơ chế đối số nếu được thiết kế như vậy.

## 6. Ví dụ đầy đủ với Spring Cloud Config Client

Giả sử Config Server trả về cấu hình từ Git cho `order-service` và profile `prod`:

```yaml
# order-service-prod.yml trong repository cấu hình
orders:
  timeout: 2s
  retry-limit: 3

server:
  port: 8080
```

Config Client khai báo nguồn từ xa:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
```

Trong môi trường triển khai, nhóm đặt biến môi trường:

```text
ORDERS_TIMEOUT=4s
SERVER_PORT=8081
```

Service wrapper bổ sung JVM system property:

```bash
java -Dorders.timeout=5s -jar order-service.jar
```

Nếu cần chạy một instance để kiểm tra, người vận hành thêm tham số:

```bash
java -Dorders.timeout=5s -jar order-service.jar \
  --orders.timeout=750ms
```

Kết quả:

| Thuộc tính | Config Server | Environment | System property | Command line | Giá trị hiệu lực |
|---|---:|---:|---:|---:|---:|
| `orders.timeout` | `2s` | `4s` | `5s` | `750ms` | `750ms` |
| `orders.retry-limit` | `3` | Không có | Không có | Không có | `3` |
| `server.port` | `8080` | `8081` | Không có | Không có | `8081` |

Khi bỏ tham số command line, `orders.timeout` trở về `5s`. Khi bỏ thêm system property, nó trở về `4s`. Khi bỏ cả biến môi trường, giá trị `2s` từ Config Server được dùng. Đây là cách kiểm tra từng tầng ghi đè mà không cần thay đổi repository cấu hình.

Với Spring Cloud Config Client dùng Config Data import (`spring.config.import=configserver:...`), cấu hình từ xa được nạp trong quá trình xử lý Config Data. Theo thứ tự Spring Boot, biến môi trường, system properties và command-line options được xét sau Config Data nên có thể ghi đè giá trị từ xa. Composite repository chỉ quyết định thứ tự bên trong phần cấu hình mà Config Server trả về.

Nếu dự án vẫn dùng cơ chế Config First Bootstrap cũ (`bootstrap.yml` hoặc `spring-cloud-starter-bootstrap`), cần chú ý quy tắc riêng của Spring Cloud: remote property source mặc định có ưu tiên cao hơn local property sources và không cho phép ghi đè từ client. Để cho phép local system properties, biến môi trường và command-line arguments ghi đè, remote property source phải khai báo `spring.cloud.config.allow-override=true`. Khi được bật, `spring.cloud.config.override-system-properties` mặc định là `true`; nếu đặt `false`, system properties, biến môi trường và command-line arguments vẫn có thể ghi đè remote, nhưng local config files không thể. Nếu muốn mọi local property source có thể ghi đè, đặt `spring.cloud.config.override-none=true`. Các cờ này phải được đặt trong cấu hình từ xa; khai báo chúng cục bộ không cấp quyền ghi đè cho client.

Vì vậy, trước khi áp dụng ví dụ precedence, hãy xác nhận Config Client đang dùng Config Data import hay legacy bootstrap. Hai cách nạp cấu hình có quy tắc đặt remote property source khác nhau.

## 7. Những nguồn khác có thể làm kết quả khác đi

Thứ tự ba nguồn trong bài là một phần của thứ tự ưu tiên đầy đủ. Khi giá trị hiệu lực không như dự kiến, cần xem thêm:

- `SPRING_APPLICATION_JSON` hoặc `spring.application.json`: cung cấp một khối JSON thuộc tính. Trong thứ tự hiện hành, nguồn JSON được xét sau system properties nhưng trước command-line options.
- Thuộc tính test như `@SpringBootTest(properties=...)`, `@DynamicPropertySource` và `@TestPropertySource`: có thể ghi đè các nguồn triển khai trong quá trình test.
- `SpringApplication.setDefaultProperties`: cung cấp giá trị mặc định ở mức thấp.
- `@PropertySource`: thêm nguồn thuộc tính khi context được làm mới; một số thuộc tính được đọc sớm như `logging.*` và `spring.main.*` có thể không phù hợp để cấu hình bằng cách này.
- Các file Config Data khác, profile-specific files và `spring.config.import`: thứ tự import và vị trí file có thể ảnh hưởng giá trị trước khi các nguồn môi trường/JVM/command line được áp dụng.
- `spring.cloud.config.server.overrides`: thuộc tính phía Config Server; nếu được cấu hình, các giá trị override sẽ được đưa vào nguồn cấu hình mà server trả về cho client.

Đừng nhầm `SPRING_APPLICATION_JSON` với biến môi trường thông thường. JSON là một property source riêng, có quy tắc ưu tiên riêng. Tương tự, thuộc tính trong test có thể khiến một bài test thấy giá trị khác với khi chạy ứng dụng thật.

## 8. Đối chiếu giá trị đang có hiệu lực

Khi ứng dụng nhận giá trị không như mong đợi, hãy kiểm tra từ khóa thuộc tính cụ thể và tên nguồn cung cấp nó.

### Dùng Spring Boot Actuator

Nếu Actuator được cài đặt và endpoint `env` được expose có kiểm soát, có thể truy vấn một thuộc tính:

```bash
curl -sS http://localhost:8080/actuator/env/orders.timeout
```

Endpoint này có thể cho biết giá trị đã phân giải và property source đang cung cấp giá trị đó. Danh sách property source giúp thấy biến môi trường, system property, command line hoặc Config Data nào có cùng khóa. Endpoint `configprops` hữu ích để kiểm tra giá trị đã bind vào bean `@ConfigurationProperties`.

Chỉ expose endpoint chẩn đoán trong mạng quản trị hoặc cho danh tính được cấp quyền. Giữ cơ chế sanitization cho password, token và các giá trị nhạy cảm; không bật hiển thị mọi giá trị trong production chỉ để tìm một lỗi cấu hình.

### Kiểm tra system property trong Java

Có thể kiểm tra trực tiếp JVM system property:

```java
String timeout = System.getProperty("orders.timeout");
```

Đoạn code này chỉ đọc system property. Nó không trả về giá trị cuối cùng của Spring `Environment` nếu giá trị thắng đến từ biến môi trường, Config Data hoặc command line. Muốn đọc giá trị đã phân giải, dùng `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class TimeoutReporter {

    TimeoutReporter(Environment environment) {
        String timeout = environment.getProperty("orders.timeout");
        // Dùng giá trị đã được Spring phân giải theo thứ tự PropertySource.
    }
}
```

Trong ứng dụng thực tế, nên bind cấu hình có cấu trúc bằng `@ConfigurationProperties` và kiểm tra giá trị sau khi bind. Không nên rải lệnh `System.getenv()` hoặc `System.getProperty()` khắp nghiệp vụ vì sẽ bỏ qua cơ chế hợp nhất và chuyển đổi kiểu của Spring Boot.

## 9. Lỗi thường gặp khi so sánh ba nguồn

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Biến môi trường không ghi đè file | Tên biến không theo quy tắc relaxed binding hoặc tiến trình không nhận biến | Kiểm tra dấu chấm, dấu gạch nối, chữ hoa và môi trường của đúng tiến trình |
| System property không có hiệu lực | Đặt `-D` sau `-jar` hoặc sau tên main class | Chuyển `-Dkey=value` lên trước `-jar` |
| Command line không ghi đè | Dùng `-Dkey=value` thay vì `--key=value`, hoặc ứng dụng tắt command-line property source | Dùng `--key=value` và kiểm tra `setAddCommandLineProperties` |
| Config Server trả giá trị khác với client | Nguồn môi trường/JVM/CLI ở client ghi đè cấu hình từ xa | Kiểm tra `/actuator/env` trên đúng instance |
| Chạy trong IDE khác với chạy bằng service | IDE, shell, container hoặc service có môi trường và tham số khởi chạy khác nhau | Đối chiếu cấu hình launch thực tế của từng môi trường |
| Test có giá trị khác production | Test property source có ưu tiên cao | Kiểm tra `@SpringBootTest`, `@DynamicPropertySource`, `@TestPropertySource` |
| Giá trị đã bind khác giá trị Environment | Sai prefix, conversion, validation, default hoặc bean giữ giá trị cũ | Kiểm tra `env`, `configprops` và lớp cấu hình |

Một nguyên tắc quan trọng: phải kiểm tra môi trường của đúng tiến trình đang chạy. Biến được đặt trong terminal hiện tại không tự động thay đổi môi trường của một service đã khởi chạy trước đó. Tương tự, sửa tham số JVM yêu cầu khởi động lại JVM để có hiệu lực.

## 10. Quy ước vận hành để tránh ghi đè ngoài ý muốn

- Đặt giá trị mặc định hợp lý trong Config Data hoặc cấu hình từ xa để môi trường có thể khởi động theo quy ước chung.
- Dùng biến môi trường cho giá trị phụ thuộc môi trường như hostname, cổng hoặc giới hạn được nền tảng cấp.
- Dùng system property khi cần cấu hình riêng cho một JVM hoặc service wrapper.
- Dùng tham số `--key=value` cho lần chạy đặc biệt, kiểm thử hoặc thao tác có chủ đích; ghi lại nếu tham số được giữ lâu dài trong cấu hình triển khai.
- Không để nhiều tầng cùng khai báo một khóa nếu không có lý do; nếu có, tài liệu hóa nguồn nào được phép ghi đè.
- Không đưa mật khẩu hoặc token vào command line vì chúng có thể xuất hiện trong process list, log hoặc lịch sử shell; dùng secret manager và cơ chế cấp bí mật của nền tảng.
- Kiểm tra giá trị hiệu lực và nguồn của nó trên đúng instance trước khi kết luận Config Server trả sai.
- Sau khi điều tra, loại bỏ override tạm thời để instance trở lại cấu hình được quản lý theo quy trình.

## 11. Nguyên tắc cần ghi nhớ

- Trong ba nguồn được so sánh, biến môi trường có ưu tiên thấp nhất, system property đứng tiếp theo, command-line option `--key=value` có ưu tiên cao nhất.
- Biến môi trường dùng tên chữ hoa, thay `.` bằng `_` và loại bỏ `-`.
- Java system property dùng `-Dkey=value` trước `-jar`.
- Tham số dòng lệnh Spring Boot dùng `--key=value`; có thể tắt property source này bằng `setAddCommandLineProperties(false)`.
- Cấu hình từ Spring Cloud Config là Config Data ở phía client và vẫn có thể bị các nguồn ưu tiên cao hơn ghi đè.
- `System.getProperty()` chỉ đọc JVM system property; `Environment.getProperty()` đọc giá trị Spring đã phân giải.
- Dùng Actuator `env` và `configprops` để kiểm tra source và giá trị bind, đồng thời bảo vệ endpoint chẩn đoán.
- Không dùng command line để truyền bí mật; ưu tiên cơ chế quản lý secret của nền tảng.
- Nếu dùng legacy Config First Bootstrap, kiểm tra `allow-override`, `override-system-properties` và `override-none` ở remote property source trước khi giả định local override được phép.

Khi cần giải thích vì sao một thuộc tính có giá trị cụ thể, hãy bắt đầu từ property key, liệt kê các nguồn đang khai báo khóa đó rồi áp dụng thứ tự ưu tiên của Spring Boot. Với biến môi trường, system property và command line, quy tắc rất rõ: nguồn được áp dụng sau có thể ghi đè nguồn trước. Kiểm tra `Environment` trên đúng tiến trình sẽ cho biết ứng dụng thực sự đang sử dụng giá trị nào.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Binding From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables)
- [Spring Cloud Config Client — Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Context — Overriding Remote Properties](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#overriding-the-values-of-remote-properties)
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
