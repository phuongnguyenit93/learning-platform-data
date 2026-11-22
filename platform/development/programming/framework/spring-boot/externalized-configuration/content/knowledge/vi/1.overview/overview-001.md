# Cấu hình ngoài (Externalized Configuration) trong Spring Boot là gì và giải quyết vấn đề nào?

## 1. Khái niệm

**Externalized configuration (cấu hình ngoài)** là cách đưa những giá trị có thể thay đổi theo môi trường triển khai ra khỏi logic chương trình, để ứng dụng đọc chúng từ các nguồn cấu hình khi chạy. Giá trị có thể nằm trong file `application.properties`/`application.yml`, file đặt cạnh ứng dụng, biến môi trường, Java system properties, đối số dòng lệnh hoặc nguồn cấu hình được tích hợp thêm.

Ví dụ, cùng một ứng dụng Spring Boot có thể cần:

- Máy lập trình: chạy HTTP ở cổng `8080`, kết nối cơ sở dữ liệu thử nghiệm, log ở mức `DEBUG`.
- Môi trường kiểm thử: chạy cổng do nền tảng cấp, dùng database kiểm thử, log ở mức `INFO`.
- Production: dùng địa chỉ database production, giới hạn timeout phù hợp, lấy bí mật từ hệ thống quản lý secret.

Những khác biệt này thuộc về **cấu hình vận hành**, không nhất thiết phải thay đổi mã Java. Mục tiêu là dùng **cùng một bản build (cùng JAR hoặc container image)** ở nhiều môi trường, rồi cung cấp các giá trị phù hợp cho từng lần triển khai.

> Cấu hình ngoài là một cơ chế cung cấp và ghi đè giá trị cho ứng dụng. Nó không có nghĩa mọi giá trị bắt buộc phải nằm ngoài JAR: file cấu hình đóng gói bên trong JAR vẫn có thể làm giá trị mặc định, còn nguồn bên ngoài ghi đè khi cần.

## 2. Những vấn đề mà cấu hình ngoài giải quyết

### 2.1. Tránh hard-code các giá trị phụ thuộc môi trường

Nếu viết cố định `jdbc:postgresql://localhost:5432/demo`, port `8080` hay URL của dịch vụ đối tác trong mã nguồn, mỗi môi trường có thể đòi hỏi sửa code, build và phát hành lại. Cấu hình ngoài cho phép mã nguồn chỉ biết **tên thuộc tính** như `spring.datasource.url` hoặc `app.partner.base-url`; nơi triển khai quyết định giá trị.

### 2.2. Giảm tình trạng mỗi môi trường một bản build

Khi đội ngũ phải tạo `app-dev.jar`, `app-staging.jar` và `app-prod.jar` chỉ vì khác URL hoặc port, rất khó chắc chắn các môi trường đang chạy cùng một phiên bản chương trình. Với externalized configuration, một artifact có thể được quảng bá tuần tự qua các môi trường. Khác biệt nằm ở dữ liệu cấu hình được cấp cho artifact đó.

### 2.3. Dễ triển khai tự động và chạy trên nhiều nền tảng

CI/CD, Docker, Kubernetes và các nền tảng cloud thường truyền cấu hình qua environment variables, file mount hoặc secret store. Ứng dụng Spring Boot có thể đọc các nguồn đó mà không cần code tùy biến cho từng máy. Ví dụ `SERVER_PORT` có thể cung cấp giá trị cho `server.port`.

### 2.4. Quản lý cấu hình tập trung, rõ trách nhiệm

Nhóm phát triển sở hữu logic và các tên thuộc tính; người vận hành hoặc hệ thống triển khai cung cấp giá trị cho môi trường cụ thể. Khi port, timeout hay endpoint thay đổi, có thể sửa phần cấu hình của deployment mà không sửa mã nghiệp vụ. Tuy nhiên, việc triển khai lại hoặc khởi động lại có thể vẫn cần thiết để áp dụng giá trị mới.

### 2.5. Giảm nguy cơ lộ thông tin nhạy cảm trong mã nguồn

Mật khẩu, token, khóa API và chứng chỉ không nên được hard-code hay commit vào repository. Externalized configuration giúp ứng dụng nhận những giá trị này từ cơ chế cấp secret của môi trường. **Nó không tự mã hóa hay bảo vệ bí mật**: biến môi trường, file ngoài và log vẫn cần quyền truy cập, phân phối và giám sát phù hợp.

### 2.6. Cho phép điều chỉnh hành vi mà không sửa code

Timeout, số lần retry, kích thước pool, mức log hoặc một số cờ tính năng có thể được biểu diễn thành thuộc tính. Điều chỉnh chúng là thay đổi cấu hình, miễn là chương trình đã được viết để tiêu thụ các thuộc tính đó. Cấu hình không thể tự tạo ra chức năng mà code chưa hỗ trợ.

## 3. Spring Boot đọc cấu hình như thế nào?

Mô hình khái quát:

~~~text
Nguồn cấu hình
  application.yml / application.properties
  file bên ngoài JAR
  biến môi trường
  Java system properties
  đối số --key=value
  nguồn tích hợp thêm
          |
          v
Spring Environment + các PropertySource
          |
          v
Tra cứu thuộc tính và áp dụng thứ tự ưu tiên
          |
          v
Binding vào cấu hình Spring Boot / @Value / @ConfigurationProperties
          |
          v
Bean và thành phần ứng dụng dùng giá trị đã được cấu hình
~~~

`Environment` cung cấp khả năng truy xuất các property. Mỗi `PropertySource` đóng góp các cặp tên–giá trị. Khi nhiều nguồn định nghĩa cùng một tên thuộc tính, Spring Boot áp dụng **quy tắc ưu tiên** để chọn giá trị hiệu lực. Ngoài ra, cơ chế binding chuyển giá trị chuỗi thành kiểu phù hợp như số, boolean, `Duration` hoặc đối tượng cấu hình có cấu trúc.

Spring Boot đã dùng cơ chế này cho các thuộc tính quen thuộc:

- `server.port`: cổng HTTP của web server được nhúng.
- `spring.datasource.url`: JDBC URL của datasource khi có cấu hình datasource phù hợp.
- `logging.level.root`: mức log mặc định.
- `spring.profiles.active`: profile đang được kích hoạt.
- Các tiền tố riêng của ứng dụng như `app.timeout` hay `app.notification.enabled`.

Đọc cấu hình là một phần của quá trình khởi tạo ứng dụng. Đa số bean được tạo với những giá trị đã được xác định lúc startup; thay đổi nguồn bên ngoài sau đó **không mặc nhiên cập nhật** các bean đang chạy.

## 4. Các nguồn cấu hình thường gặp

| Nguồn | Ví dụ | Khi nào hữu ích? |
| --- | --- | --- |
| File đóng gói trong JAR | `src/main/resources/application.yml` | Cung cấp giá trị mặc định an toàn, dùng chung |
| File ngoài JAR | `./config/application.yml` | Điều chỉnh môi trường mà không build lại |
| Biến môi trường hệ điều hành | `SERVER_PORT=9090` | Container, pipeline, hệ thống triển khai |
| Java system property | `-Dserver.port=9090` | Truyền cấu hình khi khởi động JVM |
| Đối số ứng dụng | `--server.port=9090` | Thử nhanh hoặc ghi đè tại lần chạy |
| File theo profile | `application-prod.yml` | Nhóm giá trị gắn với một môi trường hoặc chế độ chạy |
| Nguồn tích hợp bổ sung | Config tree, secret mount, config server | Nhận cấu hình từ nền tảng vận hành |

Đây là các nguồn có thể phối hợp với nhau. **Profile** chỉ là cách kích hoạt một tập cấu hình có điều kiện; nó không thay thế toàn bộ cơ chế externalized configuration.

Spring Boot hỗ trợ `.properties` và YAML. Nên dùng cách biểu diễn nhất quán trong dự án để tránh khó tìm nguồn hiệu lực. Không nên xem tất cả nguồn là ngang nhau: chúng có độ ưu tiên khác nhau, và vị trí file hoặc profile đang bật ảnh hưởng tới kết quả cuối cùng.

## 5. Ví dụ: một JAR, hai môi trường

Giả sử ứng dụng có một số tùy chọn vận hành. File `src/main/resources/application.yml` được đóng gói cùng ứng dụng:

~~~yaml
server:
  port: 8080

logging:
  level:
    root: INFO

app:
  name: demo-service
  timeout: 5s
  notification:
    enabled: false
~~~

Ở máy phát triển, chạy:

~~~bash
java -jar app.jar
~~~

Ứng dụng dùng các giá trị mặc định trên: port `8080`, timeout `5s` và thông báo tắt (nếu code ứng dụng có đọc `app.notification.enabled`).

Khi triển khai, có thể dùng **chính file `app.jar` đó** và ghi đè qua environment variables:

~~~bash
SERVER_PORT=9090 APP_TIMEOUT=10s APP_NOTIFICATION_ENABLED=true java -jar app.jar
~~~

Ở lần chạy này, port là `9090`, timeout là `10s` và cờ thông báo là `true`. Không cần tạo một JAR mới chỉ để đổi các giá trị đó.

Nếu muốn dùng profile `prod`, có thể đặt file ngoài tại `./config/application-prod.yml` (đường dẫn tính theo thư mục làm việc khi khởi chạy):

~~~yaml
logging:
  level:
    root: WARN

app:
  timeout: 15s
~~~

Và kích hoạt profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Khi đó profile `prod` cho phép áp dụng các giá trị theo môi trường, còn những thuộc tính không được ghi đè vẫn có thể lấy từ cấu hình chung. Nếu đồng thời truyền `--app.timeout=20s`, đối số dòng lệnh thông thường có ưu tiên cao hơn giá trị trong các file cấu hình ở ví dụ này.

**Lưu ý:** Ví dụ dùng cú pháp gán biến môi trường trực tiếp của shell Unix. Trên PowerShell có thể dùng `$env:SERVER_PORT = "9090"` trước khi chạy `java -jar app.jar`; cách khai báo phụ thuộc shell/nền tảng.

## 6. Đọc property trong mã Java

Với một vài giá trị đơn giản, Spring hỗ trợ inject bằng `@Value`. Khi có một nhóm thuộc tính liên quan, Spring Boot khuyến khích binding có kiểu bằng `@ConfigurationProperties`.

Ví dụ với cấu hình ở trên:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
    String name,
    Duration timeout,
    Notification notification
) {
    public record Notification(boolean enabled) {}
}
~~~

Bật việc quét các lớp cấu hình trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Một service có thể nhận `AppProperties` qua constructor injection rồi sử dụng `properties.timeout()` hoặc `properties.notification().enabled()`. Giá trị `5s`/`10s` trong file hoặc biến môi trường được binding thành `Duration`; thuộc tính lồng nhau được binding vào record `Notification`.

Các cấu hình riêng của ứng dụng có thể được **validate ngay khi khởi động** (ví dụ tên bắt buộc không được trống, timeout phải dương). Có thể kết hợp `@Validated` và Jakarta Bean Validation, với dependency validation phù hợp. Điều này khiến ứng dụng thất bại rõ ràng khi cấu hình quan trọng bị thiếu hoặc sai, thay vì gặp lỗi khó hiểu khi xử lý request.

## 7. Thứ tự ưu tiên: vì sao cùng một thuộc tính có nhiều giá trị?

Ví dụ:

- Trong `application.yml` có `server.port=8080`.
- Trong môi trường chạy có `SERVER_PORT=9090`.
- Khi khởi chạy, truyền thêm `--server.port=9191`.

Với các nguồn thông dụng này, giá trị cuối cùng là **`9191`**, vì đối số dòng lệnh ứng dụng có ưu tiên cao hơn environment variables và file cấu hình. Nếu bỏ đối số, giá trị `9090` được dùng; nếu bỏ cả biến môi trường, giá trị `8080` từ file được dùng.

Đây là cơ chế ghi đè có chủ đích, nhưng dễ gây nhầm lẫn khi sửa file mà ứng dụng vẫn lấy giá trị từ nguồn ưu tiên cao hơn. Trật tự đầy đủ còn liên quan tới nhiều nguồn khác (như system properties, JSON environment, test properties, devtools), vì vậy khi gặp xung đột cần xác định **nguồn nào thực sự đang cấp giá trị** thay vì chỉ kiểm tra một file.

Tên property có dạng phân cấp như `spring.datasource.url`. Với biến môi trường, cách đặt tên thường chuyển dấu chấm thành gạch dưới và viết hoa, chẳng hạn `SPRING_DATASOURCE_URL`. Spring Boot dùng **relaxed binding** để ánh xạ các biến này với tên property tương ứng. Khi dùng tên thuộc tính phức tạp hoặc danh sách, cần tuân theo quy tắc đặt tên environment variable của Spring Boot thay vì tự suy đoán.

## 8. Externalized configuration và Profiles khác nhau thế nào?

**Externalized configuration** trả lời: *Ứng dụng nhận giá trị cấu hình từ những nguồn nào, áp dụng giá trị nào và đưa giá trị vào các thành phần ra sao?*

**Profiles** trả lời: *Khi kích hoạt một profile nhất định, phần cấu hình hoặc bean nào sẽ tham gia?* Ví dụ profile `dev` và `prod` có thể có giá trị log level khác nhau qua `application-dev.yml` và `application-prod.yml`.

Không phải mọi khác biệt môi trường đều cần một profile. Trong các hệ thống container, việc truyền cùng những property names qua environment variables thường đơn giản hơn. Ngược lại, profile hữu ích khi cần nhóm nhiều giá trị theo mục đích rõ ràng. Profile tự nó **không phải cơ chế lưu trữ bí mật**.

## 9. Giới hạn và nguyên tắc dùng đúng

**Không có tự động hot reload.** Thay đổi file cấu hình hoặc environment variable trong lúc ứng dụng đang chạy thường không làm giá trị trong bean được cập nhật ngay. Để làm mới động cần cơ chế riêng; nhiều hệ thống chọn deploy/restart có kiểm soát.

**Không biến secret thành thông tin an toàn chỉ nhờ chuyển vị trí.** Tránh ghi mật khẩu vào Git, log, câu lệnh dễ bị ghi vào lịch sử shell hay đối số dễ bị lộ qua process listing. Dùng secret manager, secret mount hoặc cơ chế cấp phát của nền tảng, phân quyền tối thiểu và có quy trình xoay vòng.

**Có giá trị mặc định hợp lý, nhưng fail fast với cấu hình bắt buộc.** Ví dụ timeout có thể có mặc định; thông tin kết nối đến hệ thống production quan trọng nên được cung cấp tường minh và kiểm tra khi startup. Tránh fallback âm thầm sang tài nguyên thử nghiệm trong production.

**Giữ tên thuộc tính rõ ràng.** Dùng nhóm nhất quán như `app.payment.timeout` hoặc `app.notification.enabled`, đơn vị thời gian rõ (`5s`, `500ms`), tài liệu hóa các giá trị hợp lệ và không dùng một property cho nhiều ý nghĩa.

**Không đưa dữ liệu nghiệp vụ biến đổi liên tục vào startup configuration.** Giá sản phẩm, trạng thái đơn hàng hay thông tin người dùng thuộc database hoặc hệ quản trị nghiệp vụ, vì thường cần cập nhật trong thời gian chạy và có yêu cầu quản lý khác.

**Quan sát cấu hình một cách an toàn.** Khi ứng dụng đọc sai giá trị, kiểm tra profile đang hoạt động, nguồn cấu hình đang được mount, biến môi trường và thứ tự ưu tiên. Spring Boot Actuator có endpoint liên quan đến environment và configuration properties nếu được bật; cần bảo vệ endpoint, kiểm soát thông tin nhạy cảm và không công khai toàn bộ giá trị secret.

## 10. Ví dụ tình huống thực tế

Một nhóm triển khai ứng dụng thanh toán trên laptop, môi trường staging và production:

1. **Code:** service đọc `app.partner.base-url`, `app.partner.timeout` và `app.partner.api-key`; không chứa URL hoặc key cố định.
2. **Build:** CI tạo một container image từ đúng commit đã kiểm thử.
3. **Deploy staging:** nền tảng cấp URL sandbox, timeout thử nghiệm và secret staging.
4. **Deploy production:** cùng image được cấp URL production, timeout thích hợp và secret production.
5. **Đổi timeout:** nhóm vận hành cập nhật giá trị trong cấu hình deployment rồi thực hiện rollout/restart theo cơ chế nền tảng, không cần sửa Java hay build lại image.
6. **Chẩn đoán sự cố:** nếu ứng dụng kết nối nhầm endpoint, xác định nguồn nào đã ghi đè `app.partner.base-url` và profile nào đang hoạt động.

Kết quả đạt được là **tách logic ứng dụng khỏi khác biệt môi trường**, giúp phát hành nhất quán, cấu hình linh hoạt và dễ truy vết hơn.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Cấu hình ngoài nghĩa là không được có `application.yml` trong JAR.” | File trong JAR có thể giữ default; các nguồn bên ngoài ghi đè khi cần. |
| “Đã đổi file YAML thì app sẽ đổi hành vi lập tức.” | Phần lớn cấu hình được binding lúc startup; thường phải restart hoặc có cơ chế refresh riêng. |
| “Có `application-prod.yml` thì production tự sử dụng.” | Profile tương ứng cần được kích hoạt; file còn phải nằm ở vị trí được Spring Boot tìm thấy hoặc được import đúng cách. |
| “Chuyển mật khẩu sang environment variable là bảo mật tuyệt đối.” | Vẫn phải quản lý secret, quyền đọc, log và cách cung cấp cho tiến trình. |
| “Cùng property xuất hiện ở hai nguồn là lỗi.” | Ghi đè là tính năng chủ đích; cần hiểu precedence và xác định giá trị cuối. |
| “Dùng `@ConfigurationProperties` thì mọi property đều tự hợp lệ.” | Binding kiểu dữ liệu có thể bắt lỗi chuyển đổi; ràng buộc nghiệp vụ cần khai báo validation cụ thể. |

## 12. Ghi nhớ

Cấu hình ngoài trong Spring Boot có ba ý quan trọng:

1. **Ứng dụng khai báo điều cần cấu hình** bằng property names và code đọc property; môi trường cung cấp giá trị.
2. **Nhiều nguồn có thể cùng tham gia**, với quy tắc ưu tiên quyết định giá trị hiệu lực.
3. **Một artifact có thể triển khai ở nhiều môi trường** với cấu hình khác nhau, miễn là đội ngũ quản lý tốt các giá trị bắt buộc, secret, validation và quy trình áp dụng thay đổi.

Khi gặp một giá trị cố định trong code, hãy tự hỏi: *Giá trị này là quy tắc nghiệp vụ bất biến, hay có thể khác giữa máy phát triển, staging và production?* Nếu là loại thứ hai, đó thường là ứng viên phù hợp để đưa vào externalized configuration.
