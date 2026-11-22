# Hành trình từ nguồn cấu hình đến giá trị được bean sử dụng

## 1. Bức tranh tổng thể

Trong Spring Boot, một bean thường cần các giá trị như địa chỉ dịch vụ bên ngoài, thời gian chờ, số lần thử lại hoặc cờ bật/tắt tính năng. Những giá trị này thay đổi theo môi trường triển khai, trong khi mã Java có thể giữ nguyên.

Điểm cần hiểu là: **bean không tự tìm rồi đọc trực tiếp từng tệp `application.yml` hay từng biến môi trường**. Spring Boot thu thập các nguồn cấu hình, sắp xếp chúng theo độ ưu tiên, cho phép tra cứu thuộc tính và chuyển giá trị phù hợp vào bean khi Spring khởi tạo ứng dụng.

Có thể hình dung hành trình như sau:

```text
application.yml / application-prod.yml
biến môi trường / tham số dòng lệnh / nguồn cấu hình khác
                         |
                         v
          Nạp và tổ chức nguồn cấu hình
                 (PropertySource)
                         |
                         v
                Spring Environment
       (tra cứu giá trị theo tên thuộc tính)
                         |
            +------------+-------------+
            |            |             |
            v            v             v
       @Value       Environment    @ConfigurationProperties
     placeholder     .getProperty      + Binder
            |            |             |
            +------------+-------------+
                         |
                         v
       Chuyển kiểu, kiểm tra ràng buộc nếu có
                         |
                         v
        Thuộc tính/đối tượng cấu hình trong bean
                         |
                         v
              Mã nghiệp vụ sử dụng
```

Sơ đồ mô tả **luồng khái niệm**. Ví dụ, cơ chế `Binder` của `@ConfigurationProperties` làm việc với các nguồn thuộc tính đã được Spring Boot chuẩn hóa từ `Environment`; không nên hiểu rằng mọi nhánh đều bắt buộc gọi tuần tự một phương thức `Environment.getProperty()`.

## 2. Bắt đầu từ một thuộc tính cụ thể

Giả sử ứng dụng có chức năng gửi thông báo. Bean gửi thông báo cần biết thời gian chờ và trạng thái bật/tắt. Trong `src/main/resources/application.yml`:

```yaml
checkout:
  notification:
    enabled: true
    timeout: 3s
```

Ta có hai thuộc tính:

- `checkout.notification.enabled`: có bật chức năng hay không.
- `checkout.notification.timeout`: thời gian chờ khi gọi dịch vụ thông báo.

Tên thuộc tính là địa chỉ để Spring tìm giá trị. `3s` là giá trị biểu diễn thời lượng ba giây; mã Java có thể nhận một đối tượng `Duration` thay vì phải tự tách chuỗi `"3s"`.

Cùng một khóa có thể được khai báo từ các nguồn khác. Chẳng hạn, trước khi chạy ứng dụng trên Linux/macOS:

```bash
export CHECKOUT_NOTIFICATION_TIMEOUT=5s
java -jar app.jar
```

Trong PowerShell:

```powershell
$env:CHECKOUT_NOTIFICATION_TIMEOUT = "5s"
java -jar app.jar
```

Hoặc truyền tham số ngay khi chạy:

```bash
java -jar app.jar --checkout.notification.timeout=2s
```

Đối với khóa này, cách viết biến môi trường `CHECKOUT_NOTIFICATION_TIMEOUT` có thể ánh xạ tới `checkout.notification.timeout`. Trong tình huống thông thường chỉ gồm ba nguồn ở trên, tham số dòng lệnh `2s` được ưu tiên hơn biến môi trường `5s`, và biến môi trường được ưu tiên hơn `application.yml` với giá trị `3s`.

Điều đó không có nghĩa Spring cộng ba thời gian chờ hoặc tạo ba bản bean. **Spring giải quyết một giá trị có hiệu lực cho khóa cần tra cứu**, dựa trên thứ tự ưu tiên của những nguồn đang tham gia.

## 3. Từ tệp và biến môi trường thành PropertySource

Khi gọi `SpringApplication.run(...)`, Spring Boot chuẩn bị `Environment` cho ứng dụng. Trong giai đoạn khởi động, cơ chế Config Data tìm và nạp các tệp cấu hình ứng dụng phù hợp, bao gồm cấu hình theo profile đang hoạt động. Các nguồn như biến môi trường hệ điều hành và tham số dòng lệnh cũng được đưa vào hệ thống thuộc tính.

Một `PropertySource` có thể hiểu là một nguồn có tên, biết trả về giá trị cho một khóa thuộc tính. `Environment` quản lý nhiều nguồn như vậy và cung cấp cách tra cứu giá trị sau khi xét độ ưu tiên.

Ví dụ:

```text
Khóa cần tìm: checkout.notification.timeout

Tham số dòng lệnh      -> 2s
Biến môi trường          -> 5s
application.yml         -> 3s

Kết quả tra cứu thông thường -> 2s
```

Bảng trên minh họa một trường hợp đơn giản, không phải danh sách thứ tự ưu tiên đầy đủ của Spring Boot. Trong ứng dụng thực tế còn có thể có cấu hình theo profile, tệp được import, thuộc tính dành cho kiểm thử và những nguồn khác. Nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị khi nhiều nguồn cùng cung cấp một khóa.

Nếu tạo `application-prod.yml`:

```yaml
checkout:
  notification:
    timeout: 10s
```

và kích hoạt profile bằng `--spring.profiles.active=prod`, cấu hình riêng cho `prod` có thể ghi đè giá trị cơ sở trong `application.yml`. Tuy nhiên, tham số dòng lệnh trực tiếp `--checkout.notification.timeout=2s` vẫn có thể ghi đè thời gian chờ từ tệp profile. Vì vậy, **profile quyết định những cấu hình nào được nạp; thứ tự ưu tiên quyết định giá trị nào thắng khi trùng khóa**.

`Environment` còn cho biết profile nào đang hoạt động. Cần phân biệt hai việc: lựa chọn nguồn cấu hình trong giai đoạn khởi động và đọc giá trị thuộc tính khi tạo bean.

## 4. Ba cách đưa giá trị vào mã Java

Sau khi thuộc tính đã có thể được tra cứu, mã ứng dụng thường sử dụng một trong ba cách sau. Cả ba đều dựa trên hệ thống cấu hình của Spring nhưng phục vụ các nhu cầu khác nhau.

### 4.1. Tra cứu trực tiếp qua Environment

Một bean có thể nhận `Environment` bằng dependency injection:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class NotificationConfigReader {
    private final Environment environment;

    public NotificationConfigReader(Environment environment) {
        this.environment = environment;
    }

    public String timeoutText() {
        return environment.getProperty(
            "checkout.notification.timeout",
            "3s"
        );
    }
}
```

`getProperty(key, defaultValue)` tìm giá trị theo khóa; nếu không có thì trả về giá trị mặc định. Ví dụ này trả về dạng `String`. `Environment` cũng có các phiên bản hỗ trợ kiểu đích, nhưng khi một nhóm cấu hình được dùng nhiều nơi, đọc từng khóa thủ công thường làm mã phân tán và khó bảo trì.

Cách này phù hợp khi cần tra cứu linh hoạt một vài khóa, hoặc khi đang tìm hiểu/kiểm tra giá trị có hiệu lực.

### 4.2. Chèn một giá trị bằng @Value

Spring hỗ trợ placeholder `${...}` trong `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class NotificationSwitch {
    private final boolean enabled;

    public NotificationSwitch(
            @Value("${checkout.notification.enabled:true}")
            boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

Khi tạo `NotificationSwitch`, Spring xử lý placeholder, lấy giá trị có hiệu lực, chuyển sang `boolean` và truyền vào constructor. Trong biểu thức `${checkout.notification.enabled:true}`, phần sau dấu hai chấm là giá trị mặc định `true` nếu thuộc tính không được tìm thấy.

`@Value` tiện khi chỉ có một hoặc hai thuộc tính đơn lẻ. Với nhiều thuộc tính liên quan, các khóa kiểu chuỗi lặp lại khắp mã Java sẽ khó đổi tên và khó kiểm soát hơn so với đối tượng cấu hình có kiểu rõ ràng. Nên viết khóa trong placeholder theo dạng chuẩn chữ thường, phân tách bằng dấu gạch ngang khi cần, để tương thích tốt hơn với quy tắc tên thuộc tính của Spring Boot.

### 4.3. Liên kết cả nhóm bằng @ConfigurationProperties

Với một nhóm cấu hình phục vụ cùng chức năng, `@ConfigurationProperties` tạo ranh giới rõ giữa cấu hình và mã nghiệp vụ.

Ví dụ với Spring Boot 3:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout.notification")
public record NotificationProperties(
        boolean enabled,
        Duration timeout
) {}
```

Để Spring đăng ký kiểu này thành bean, bật quét cấu hình ở lớp khởi động nằm trong package cha thích hợp:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
```

Khi đó, Spring Boot có thể tạo một bean `NotificationProperties`. Cơ chế binding đối chiếu `checkout.notification.enabled` với thành phần `enabled` và `checkout.notification.timeout` với thành phần `timeout`. Giá trị `"3s"` được chuyển thành `Duration.ofSeconds(3)`. Với `record` một constructor như ví dụ, Spring Boot 3 có thể dùng constructor đó để binding mà không cần thêm `@ConstructorBinding`.

Một bean nghiệp vụ chỉ việc nhận đối tượng cấu hình:

```java
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean shouldSendNotification() {
        return properties.enabled();
    }

    public Duration requestTimeout() {
        return properties.timeout();
    }
}
```

`NotificationService` không cần biết giá trị xuất phát từ YAML, biến môi trường hay tham số dòng lệnh. Nó sử dụng một phụ thuộc Java đã được Spring chuẩn bị. Đây là ưu điểm quan trọng của externalized configuration: **thay đổi nơi cấp giá trị mà không cần sửa logic nghiệp vụ**.

Trong ứng dụng có nhiều cấu hình, nên đăng ký đúng các lớp `@ConfigurationProperties` và giữ mỗi nhóm gần miền chức năng của nó. Có thể dùng `@EnableConfigurationProperties(NotificationProperties.class)` thay cho quét toàn bộ khi muốn đăng ký tường minh.

## 5. Điều gì xảy ra khi binding?

Binding không chỉ là chép văn bản từ YAML vào trường Java. Nó thực hiện một số bước khái niệm:

1. Xác định tiền tố, chẳng hạn `checkout.notification`.
2. Tìm các thuộc tính con từ những nguồn có hiệu lực.
3. Ghép tên cấu hình với tên thành phần Java, có hỗ trợ quy tắc *relaxed binding* của `@ConfigurationProperties`.
4. Chuyển kiểu nguồn sang kiểu đích, ví dụ chuỗi `"3s"` thành `Duration`, hoặc `"true"` thành `boolean`.
5. Tạo và cung cấp đối tượng cấu hình cho bean phụ thuộc; nếu cấu hình có kiểm tra ràng buộc thì bước kiểm tra được thực hiện theo cơ chế đã khai báo.

Quy tắc relaxed binding cho phép dùng các cách viết phù hợp với từng nguồn. Ví dụ, thuộc tính `checkout.notification.timeout` có thể nhận giá trị từ biến môi trường `CHECKOUT_NOTIFICATION_TIMEOUT`. Với tên có dấu gạch ngang, quy tắc chuyển sang biến môi trường thường là đổi dấu chấm thành gạch dưới, bỏ dấu gạch ngang và viết hoa; chẳng hạn `checkout.retry.max-attempts` tương ứng `CHECKOUT_RETRY_MAXATTEMPTS`.

Không nên suy ra rằng mọi cú pháp đều tương đương trong mọi API: việc liên kết nhóm bằng `@ConfigurationProperties` và việc giải quyết một placeholder tùy ý trong `@Value` có những khác biệt. Viết tên thuộc tính chuẩn ngay từ đầu giúp hạn chế lỗi không tìm được giá trị.

Nếu giá trị không thể chuyển sang kiểu khai báo, quá trình binding có thể thất bại khi khởi động và tạo thông báo lỗi liên quan đến tên thuộc tính, giá trị hoặc kiểu đích. Ví dụ `checkout.notification.timeout=hello` không biểu diễn một `Duration` hợp lệ theo cách mong đợi của ví dụ này. Điều này thường tốt hơn việc âm thầm sử dụng sai cấu hình đến khi nhận yêu cầu đầu tiên.

Nếu muốn bắt buộc một giá trị phải có mặt, có thể thêm ràng buộc Bean Validation lên lớp `@ConfigurationProperties`, dùng `@Validated` và các annotation thích hợp, đồng thời bảo đảm ứng dụng có thư viện validation cần thiết. Việc chọn giá trị mặc định hay bắt buộc giá trị là quyết định của chức năng, không phải một thuộc tính tự có của mọi nguồn cấu hình.

## 6. Thứ tự thời điểm: khi nào bean nhận giá trị?

Một trình tự khởi động điển hình:

```text
1. Gọi SpringApplication.run(...)
2. Chuẩn bị Environment và xác định các nguồn cấu hình hiệu lực
3. Xử lý Config Data và profile liên quan
4. Tạo/làm mới ApplicationContext, đăng ký các định nghĩa bean
5. Khởi tạo bean; giải quyết @Value và binding @ConfigurationProperties
6. Inject phụ thuộc và hoàn tất vòng đời bean
7. Ứng dụng bắt đầu xử lý công việc bằng giá trị đã được cấp
```

Trình tự trên được đơn giản hóa để học đường đi của giá trị; trong thực tế có các bước xử lý bean, điều kiện auto-configuration và callback vòng đời đan xen.

Hệ quả quan trọng: thay `application.yml` trên đĩa sau khi ứng dụng đã khởi động **không tự động** làm đối tượng `NotificationProperties` hoặc trường `@Value` đổi giá trị. Biến môi trường của tiến trình cũng thường được thiết lập trước lúc khởi chạy. Muốn áp dụng cấu hình mới, cách thông thường là khởi động lại ứng dụng hoặc sử dụng một cơ chế làm mới cấu hình được thiết kế riêng. Không nên mặc định rằng gọi lại phương thức nghiệp vụ sẽ nạp lại YAML.

Cũng cần hiểu thời điểm nạp nguồn: một số thuộc tính được Spring Boot dùng rất sớm để thiết lập chính quá trình khởi động. Nguồn bổ sung bằng `@PropertySource` trong quá trình xử lý context có thể quá muộn đối với các thuộc tính sớm như một số thiết lập logging. Vì vậy, nguồn Config Data và biến môi trường thường phù hợp hơn cho cấu hình khởi động ứng dụng.

## 7. Lần theo một giá trị từ đầu đến cuối

Xét tình huống:

```yaml
# application.yml
checkout:
  notification:
    enabled: true
    timeout: 3s
```

Máy chạy ứng dụng cung cấp:

```text
CHECKOUT_NOTIFICATION_TIMEOUT=5s
```

Lệnh khởi chạy:

```bash
java -jar app.jar --checkout.notification.timeout=2s
```

Hãy lần theo `NotificationService.requestTimeout()`:

| Chặng | Điều quan sát được |
| --- | --- |
| Nguồn | YAML cung cấp `3s`, biến môi trường cung cấp `5s`, dòng lệnh cung cấp `2s` |
| Nạp | Spring Boot đưa các nguồn phù hợp vào hệ thống cấu hình |
| Tra cứu | Với những nguồn trong ví dụ, giá trị có hiệu lực của `checkout.notification.timeout` là `2s` |
| Binding | `NotificationProperties.timeout` nhận một `Duration` có giá trị hai giây |
| Injection | `NotificationService` nhận bean `NotificationProperties` |
| Sử dụng | `requestTimeout()` trả về `Duration.ofSeconds(2)` |

Nếu bỏ tham số dòng lệnh, kết quả trong cùng tình huống là năm giây. Nếu tiếp tục bỏ biến môi trường, kết quả là ba giây. **Không có sửa đổi mã nguồn Java** trong cả ba lần chạy.

Đây là cách kiểm chứng tốt nhất khi mới học: giữ nguyên bean và lần lượt thay từng nguồn. Nó giúp nhìn rõ ranh giới giữa *nguồn cấu hình*, *giá trị có hiệu lực*, *liên kết kiểu* và *sử dụng trong bean*.

## 8. Chẩn đoán khi bean nhận giá trị không như dự kiến

Khi thấy timeout khác với `3s` trong YAML, hãy lần theo hành trình theo chiều ngược lại:

1. **Bean đang đọc khóa nào?** Kiểm tra `prefix` của `@ConfigurationProperties`, tên thành phần Java và placeholder của `@Value`. Một lỗi chính tả đủ làm không tìm được khóa.
2. **Nguồn nào đang cấp giá trị?** Xem tham số dòng lệnh, biến môi trường, cấu hình theo profile và các nguồn được import. Đừng chỉ mở `application.yml` rồi kết luận giá trị cuối cùng.
3. **Profile nào được kích hoạt?** Kiểm tra cách chọn profile và các tệp cấu hình đi kèm. `application-prod.yml` không tự có hiệu lực chỉ vì nó tồn tại.
4. **Có lỗi chuyển kiểu hoặc binding không?** Xem thông báo khởi động và kiểu đích như `Duration`, `int`, `boolean`. Phân biệt “không tìm được thuộc tính” với “tìm được nhưng không chuyển kiểu được”.
5. **Giá trị được chụp ở thời điểm nào?** Với bean đã khởi tạo, thay đổi tệp sau khi chạy không bảo đảm bean được cập nhật.
6. **Có hai cách đọc khác nhau?** So sánh `Environment`, `@Value` và `@ConfigurationProperties`; kiểm tra tên khóa chuẩn, giá trị mặc định và thời điểm gọi.

Khi Spring Boot Actuator được cài đặt và các endpoint thích hợp được bật, `/actuator/env` và `/actuator/configprops` có thể giúp quan sát nguồn và cấu hình đã bind. Cần tuân thủ cấu hình bảo mật của ứng dụng vì thuộc tính có thể chứa bí mật; không công khai các endpoint này hoặc ghi giá trị nhạy cảm ra log chỉ để gỡ lỗi.

Không nên giải quyết sai cấu hình bằng cách hardcode kết quả mong muốn vào bean. Làm vậy che mất nguyên nhân và khiến môi trường khác hoạt động không nhất quán.

## 9. Tự thực hành

Giữ nguyên `NotificationProperties` và `NotificationService` ở trên, sau đó thử bốn lần khởi động ứng dụng:

| Lần chạy | Điều kiện | Giá trị kỳ vọng của `requestTimeout()` |
| --- | --- | --- |
| 1 | Chỉ có `application.yml` khai báo `3s` | 3 giây |
| 2 | Thêm biến môi trường `CHECKOUT_NOTIFICATION_TIMEOUT=5s` | 5 giây |
| 3 | Giữ biến môi trường và thêm `--checkout.notification.timeout=2s` | 2 giây |
| 4 | Bỏ cả biến môi trường và tham số override; thay YAML thành `7s` rồi khởi động lại | 7 giây |

Để quan sát, có thể gọi `requestTimeout().toSeconds()` trong một đoạn mã chạy sau khi context đã khởi tạo. Chỉ in thuộc tính thử nghiệm không nhạy cảm; không áp dụng cách này cho mật khẩu hoặc token.

Sau mỗi lần, tự trả lời: **giá trị đến từ nguồn nào, vì sao nguồn đó thắng, ở bước nào chuỗi được đổi thành `Duration`, và bean nào thực sự sử dụng nó?**

Khi trả lời được bốn câu đó, bạn đã nắm đường đi cốt lõi của externalized configuration: **nguồn cấu hình → PropertySource/Environment → tra cứu và binding/chuyển kiểu → phụ thuộc của bean → hành vi ứng dụng**.