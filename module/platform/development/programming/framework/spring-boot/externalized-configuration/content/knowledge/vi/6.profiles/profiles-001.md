# Profile là gì và khi nào cần tách cấu hình theo môi trường

## 1. Vấn đề: cùng một ứng dụng nhưng các môi trường cần giá trị khác nhau

Giả sử một dịch vụ Spring Boot gửi thông báo cho người dùng. Khi phát triển trên máy cá nhân, ứng dụng nên gửi yêu cầu đến dịch vụ giả lập, dùng thời gian chờ rộng rãi và cho phép ghi log thuận tiện. Khi chạy ở môi trường kiểm thử, ứng dụng cần nói chuyện với các dịch vụ tích hợp dùng để kiểm chứng quy trình. Khi lên production, ứng dụng phải sử dụng endpoint thực tế, giới hạn thời gian chờ và chỉ bật những hành vi đã được chuẩn bị cho người dùng thật.

Nếu ghi trực tiếp các giá trị đó vào mã Java, mỗi lần đổi môi trường có thể dẫn đến sửa nguồn, biên dịch và đóng gói lại. Nếu tạo ra nhiều bản JAR khác nhau chỉ vì một địa chỉ dịch vụ, ta cũng khó bảo đảm các môi trường đang chạy đúng cùng một phiên bản mã.

Spring Boot giải quyết bài toán này bằng **cấu hình ngoài (externalized configuration)** và **profile**.

- *Externalized configuration* tách giá trị vận hành khỏi logic Java, cho phép cung cấp giá trị từ tệp, biến môi trường, tham số dòng lệnh và những nguồn khác.
- *Profile* cho phép đặt tên một **ngữ cảnh cấu hình đang hoạt động**, ví dụ `dev`, `test`, `staging` hoặc `prod`, để Spring Boot nạp thêm cấu hình và có thể đăng ký những bean phù hợp với ngữ cảnh đó.

Ý tưởng chính là **một bản dựng, nhiều môi trường chạy**. Profile giúp chọn phần cấu hình tương ứng; hệ thống nguồn cấu hình vẫn quyết định giá trị cuối cùng khi nhiều nơi khai báo cùng một khóa.

```text
                   Một mã nguồn / một JAR
                              |
                +-------------+-------------+
                |             |             |
             profile=dev  profile=staging profile=prod
                |             |             |
          Giá trị dev     Giá trị staging Giá trị prod
                |             |             |
                +-------------+-------------+
                              |
                    Bean dùng cấu hình
                              |
                      Hành vi ứng dụng
```

Sơ đồ trên minh họa ba lần chạy khác nhau của cùng một bản dựng. Mỗi tiến trình có tập profile và nguồn cấu hình của riêng mình.

## 2. Profile trong Spring Boot thực chất là gì?

Một Spring profile là **tên được Spring Environment quản lý**, dùng để biểu diễn nhóm điều kiện đang được kích hoạt. Một hoặc nhiều profile có thể hoạt động cùng lúc.

Chẳng hạn:

```text
dev
staging
prod
integration
cloud
```

Tên `dev` hay `prod` chỉ là quy ước do nhóm phát triển đặt; Spring Boot không tự suy ra một môi trường là production chỉ từ địa chỉ máy chủ, tên thư mục hoặc cách đặt tên JAR. Ứng dụng phải nhận được chỉ dẫn về profile đang hoạt động hoặc dùng những cấu hình mặc định tương ứng.

Profile thường ảnh hưởng đến hai việc:

1. **Chọn cấu hình theo profile:** bên cạnh `application.yml` chung, Spring Boot có thể nạp `application-dev.yml`, `application-prod.yml`, v.v. khi profile tương ứng hoạt động.
2. **Chọn bean theo điều kiện:** annotation `@Profile` có thể giới hạn một `@Configuration`, `@Component` hoặc phương thức `@Bean` chỉ được đăng ký khi biểu thức profile phù hợp.

Hai khả năng này liên quan nhưng khác nhau. Một nhóm giá trị có thể thay đổi theo profile mà không cần tạo nhiều lớp Java. Ngược lại, khi thật sự phải thay cả cách triển khai một chức năng, `@Profile` có thể giúp chọn bean phù hợp.

Profile **không phải** cơ chế bảo mật, không phải một môi trường triển khai được Spring Boot tự tạo, không thay thế hệ thống quản lý bí mật, và không bảo đảm mọi giá trị của một profile đều có hiệu lực cao nhất nếu có nguồn cấu hình khác ưu tiên hơn.

## 3. Cấu hình chung và cấu hình theo profile

Một cách tổ chức dễ hiểu là đặt giá trị dùng chung trong `application.yml` và chỉ đặt phần khác biệt trong các tệp có hậu tố profile.

Ví dụ dự án:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

Tệp chung `application.yml`:

```yaml
notification:
  enabled: false
  timeout: 3s
  endpoint: https://example.invalid/notification
```

Tệp `application-dev.yml`:

```yaml
notification:
  enabled: true
  timeout: 10s
  endpoint: http://localhost:9001/notification
```

Tệp `application-staging.yml`:

```yaml
notification:
  enabled: true
  timeout: 5s
  endpoint: https://staging.example.invalid/notification
```

Tệp `application-prod.yml`:

```yaml
notification:
  enabled: true
  timeout: 2s
  endpoint: https://production.example.invalid/notification
```

Các tên miền `example.invalid` ở đây chỉ là địa chỉ minh họa; chúng không đại diện cho dịch vụ có thể gọi thật.

Khi bật `dev`, các thuộc tính trong `application-dev.yml` tham gia cấu hình. Khi bật `prod`, `application-prod.yml` tham gia. Cấu hình chung vẫn được dùng cho các thuộc tính không bị nguồn có ưu tiên cao hơn ghi đè.

Ví dụ, nếu file `application-prod.yml` chỉ chứa:

```yaml
notification:
  timeout: 2s
```

thì `notification.timeout` có thể nhận `2s` từ tệp theo profile, còn `notification.enabled` và `notification.endpoint` tiếp tục dùng giá trị chung, miễn là không có nguồn khác ghi đè chúng.

Điều này giúp tránh chép toàn bộ cấu hình giống nhau sang từng file. Những giá trị chung thay đổi ở một chỗ; các khác biệt thực sự giữa môi trường được nhìn thấy rõ.

### File theo profile có được nạp tự động không?

Không phải cứ tồn tại `application-prod.yml` là ứng dụng sẽ nạp nó như cấu hình đang hoạt động. Cần có profile `prod` được kích hoạt, hoặc một cấu hình profile hợp lệ khác dẫn tới việc sử dụng nó.

Nếu không có profile chủ động nào, Spring dùng nhóm profile mặc định, thường mang tên `default`. `default` là **tên profile mặc định**, không đồng nghĩa với `dev`. Vì thế, đừng cho rằng khi chạy trên laptop Spring Boot sẽ tự bật `dev`.

Tương tự, khi một ứng dụng chạy trên máy production mà chưa được cấu hình kích hoạt `prod`, file `application-prod.yml` không tự nhiên trở thành cấu hình có hiệu lực.

## 4. Cách kích hoạt profile khi khởi động

Với Spring Boot, cách thông dụng nhất là truyền giá trị `spring.profiles.active` trước hoặc khi ứng dụng được khởi động.

### 4.1. Truyền tham số dòng lệnh

Ví dụ chạy JAR thực thi:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Để chạy trong production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

`app.jar` là tên minh họa: phải thay bằng JAR thực tế sau khi đóng gói ứng dụng. Tham số `--spring.profiles.active=prod` là một nguồn cấu hình dạng command-line argument mà Spring Boot hiểu trong cách khởi động tiêu chuẩn.

Đây là lựa chọn dễ quan sát khi thử nghiệm vì profile được thể hiện ngay trong lệnh chạy.

### 4.2. Dùng biến môi trường

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

Biến `SPRING_PROFILES_ACTIVE` cung cấp giá trị cho thuộc tính `spring.profiles.active`. Với hệ thống triển khai tự động, cách này thường thuận tiện vì cùng một JAR được khởi chạy với các biến môi trường khác nhau.

Trong PowerShell, nên gỡ biến sau buổi thực hành để lần chạy tiếp theo không vô tình kế thừa profile. Với Bash, dùng dạng `SPRING_PROFILES_ACTIVE=prod java -jar app.jar` chỉ áp dụng cho lệnh đó; nếu đã `export` biến, có thể phải `unset SPRING_PROFILES_ACTIVE` để xóa khỏi shell hiện tại.

### 4.3. Dùng Java system property

Có thể đặt profile qua thuộc tính JVM:

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

Ở đây `-Dspring.profiles.active=dev` phải đứng trước `-jar` để JVM nhận đó là system property. Khác với đối số `--spring.profiles.active=dev` được đặt sau tên JAR, dạng `-D` thuộc về JVM.

### 4.4. Cấu hình profile trong file chung

Trong một số ứng dụng, file `application.yml` có thể khai báo:

```yaml
spring:
  profiles:
    active: dev
```

Tuy nhiên, nếu muốn cùng một bản dựng dễ triển khai ở nhiều môi trường, thường nên để nền tảng chạy ứng dụng cung cấp profile qua biến môi trường hoặc tham số khởi động. Gắn cứng `dev` trong cấu hình đóng gói dễ khiến người triển khai quên rằng ứng dụng có một giá trị mặc định cho việc chọn profile.

Đặc biệt, **không đặt `spring.profiles.active` trong một tệp hoặc tài liệu YAML chỉ được kích hoạt theo profile**, vì Spring Boot hạn chế những thuộc tính điều khiển việc lựa chọn profile tại những vị trí như vậy. Chẳng hạn, không đặt `spring.profiles.active=prod` bên trong `application-dev.yml` với kỳ vọng nó sẽ tự chuyển sang profile `prod`.

## 5. Bean thực sự nhận cấu hình theo profile như thế nào?

Profile chọn nguồn cấu hình được xét; bean vẫn nhận giá trị qua cơ chế cấu hình của Spring Boot.

Giả sử ta định nghĩa:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        Duration timeout,
        URI endpoint
) {
}
```

Đăng ký cấu hình tại lớp khởi động:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
```

Với Spring Boot 3, record có một constructor như ví dụ có thể được constructor binding mà không cần thêm `@ConstructorBinding`.

Một service chỉ phụ thuộc vào đối tượng cấu hình:

```java
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean enabled() {
        return properties.enabled();
    }

    public String destination() {
        return properties.endpoint().toString();
    }
}
```

Khi khởi động với `--spring.profiles.active=dev`, giá trị endpoint trong `NotificationProperties` sẽ là `http://localhost:9001/notification` theo ví dụ. Khi khởi động với `prod`, endpoint sẽ là `https://production.example.invalid/notification`, giả sử không có biến môi trường hoặc tham số khác ghi đè.

Đáng chú ý: **`NotificationService` không chứa `if (profile.equals("prod"))`**. Nó chỉ sử dụng các giá trị đã được liên kết vào một phụ thuộc có kiểu. Đây là cách nên ưu tiên cho trường hợp các môi trường khác nhau về giá trị, còn logic nghiệp vụ giống nhau.

## 6. Khi nào nên tách cấu hình theo môi trường?

Nên dùng profile khi có **một tập khác biệt ổn định, có ý nghĩa vận hành rõ ràng** giữa các ngữ cảnh chạy. Các khác biệt đó thường xuất hiện cùng nhau và được lựa chọn khi khởi động một phiên ứng dụng.

| Nhu cầu | Ví dụ | Profile có phù hợp? |
| --- | --- | --- |
| Endpoint dịch vụ ngoài khác nhau | Dev gọi mock, staging gọi dịch vụ thử nghiệm, prod gọi dịch vụ thật | Có, nếu nhóm giá trị này gắn với môi trường |
| Chính sách quan sát khác nhau | Dev log chi tiết, prod log vừa đủ | Có thể dùng profile kết hợp cấu hình logging |
| Tài nguyên cơ sở khác nhau | Datasource hoặc tên hàng đợi theo môi trường | Có thể dùng profile cho tên/URL không nhạy cảm; bí mật cấp riêng |
| Chọn bean giả lập khi phát triển | Dev dùng adapter mô phỏng, prod dùng adapter thực | Có thể dùng `@Profile` cho bean |
| Bật một nhóm tùy chọn tích hợp theo ngữ cảnh | Profile `integration` kích hoạt cấu hình kiểm thử tích hợp | Có, nếu tập cấu hình dùng chung rõ ràng |
| Một người dùng muốn một tùy chọn cá nhân | Người dùng A thích giao diện sáng, B thích tối | Không; đây là dữ liệu hoặc sở thích người dùng, không phải profile ứng dụng |
| Mỗi khách hàng có mức giá khác nhau | Đọc từ cơ sở dữ liệu theo khách hàng | Không nên dùng một profile cho mỗi khách hàng |
| Tạm tắt một tính năng cụ thể | `feature.checkout-enabled=false` | Thường dùng thuộc tính/feature flag trực tiếp |
| Thay bí mật lúc vận hành | Token, mật khẩu, chứng chỉ | Dùng secret store/biến môi trường; profile không phải nơi giữ bí mật |

Câu hỏi cốt lõi khi thiết kế là: **“Các giá trị này thay đổi vì một ngữ cảnh khởi động chung, hay vì những quyết định độc lập?”**

Nếu nhiều cấu hình luôn đi cùng nhau theo môi trường, profile giúp tổ chức chúng dễ hiểu. Nếu một giá trị có thể thay đổi độc lập theo khách hàng, yêu cầu hoặc thời điểm, không nên tạo một profile mới chỉ để chứa nó.

## 7. Khi nào chỉ cần một thuộc tính mà không cần thêm profile?

Giả sử ứng dụng chỉ cần điều chỉnh thời gian chờ:

```yaml
notification:
  timeout: 3s
```

Khi triển khai, có thể ghi đè bằng:

```bash
java -jar app.jar --notification.timeout=7s
```

Hoặc biến môi trường tương ứng như `NOTIFICATION_TIMEOUT=7s`. Nếu chỉ có một giá trị thay đổi và không có một tập quy tắc theo môi trường cần tổ chức, một thuộc tính được cấp từ nguồn bên ngoài có thể đơn giản hơn so với tạo thêm `application-special.yml`.

Tương tự, nếu ứng dụng triển khai một tính năng tùy chọn:

```yaml
notification:
  enabled: false
```

thì một cờ cấu hình rõ nghĩa thường phù hợp hơn việc tạo profile `notification-off`. Một profile diễn đạt *ngữ cảnh hoặc tập điều kiện*; một cờ diễn đạt *trạng thái một chức năng*. Đừng biến profile thành danh sách dài gồm mọi tổ hợp của các cờ độc lập.

Ví dụ cần tránh:

```text
dev-with-email
dev-without-email
staging-with-email
staging-without-email
prod-with-email
prod-without-email
```

Nếu môi trường và việc bật email là hai quyết định độc lập, ta có thể chọn profile `dev/staging/prod` để quản lý khác biệt theo môi trường, rồi dùng `notification.enabled` để điều khiển chức năng. Cách này không làm số profile nhân lên theo mỗi cờ.

## 8. Cấu hình theo profile là ghi đè từng khóa, không phải thay toàn bộ ứng dụng

Xem ví dụ:

```yaml
# application.yml
notification:
  enabled: false
  timeout: 3s
  endpoint: https://example.invalid/notification
```

```yaml
# application-prod.yml
notification:
  timeout: 2s
  endpoint: https://production.example.invalid/notification
```

Khi profile `prod` được chọn, `timeout` và `endpoint` nhận giá trị từ file theo profile, còn `enabled` vẫn lấy từ cấu hình chung. Cơ chế hoạt động theo các thuộc tính mà nguồn cấu hình cung cấp, không có quy tắc mặc định rằng cả nhánh `notification` phải bị xóa rồi thay hoàn toàn.

Đối với các tập hợp phức tạp như list, quy tắc binding có thể khác so với từng thuộc tính độc lập; không nên suy ra rằng phần tử trong mọi danh sách đều được gộp từ nhiều profile theo cách tương tự map hoặc scalar. Với ví dụ đầu tiên, cả ba trường là những giá trị độc lập và dễ quan sát.

Tuy nhiên, **profile không vượt lên trên mọi nguồn cấu hình khác**. Ví dụ:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=9s
```

Trong cấu hình chuẩn, `--notification.timeout=9s` trên dòng lệnh có ưu tiên cao hơn `notification.timeout=2s` trong `application-prod.yml`. Bean sẽ nhận thời gian chờ chín giây. Khi điều tra cấu hình, cần kiểm tra toàn bộ nguồn ưu tiên, không chỉ file theo profile.

## 9. Nhiều profile có thể cùng hoạt động

Spring Boot có thể nhận nhiều profile trong một phiên chạy, ví dụ:

```bash
java -jar app.jar --spring.profiles.active=staging,cloud
```

Trường hợp này có thể hữu ích khi phân biệt hai chiều khác nhau:

- `staging` nói về giai đoạn triển khai và các endpoint dịch vụ.
- `cloud` nói về môi trường hạ tầng có một số tính năng hoặc cấu hình riêng.

Việc phối hợp chỉ hữu ích nếu ý nghĩa của hai profile được thiết kế rõ. Không nên kích hoạt đồng thời `dev` và `prod` rồi kỳ vọng Spring Boot tự biết giá trị nào mới là “đúng” cho từng mục đích.

Với các cấu hình theo profile ở cùng một nhóm vị trí nạp, profile được xét sau có thể ghi đè giá trị từ profile trước khi cả hai cùng khai báo một khóa. Vì vậy `--spring.profiles.active=staging,cloud` và `--spring.profiles.active=cloud,staging` có thể khác nhau nếu các file tương ứng định nghĩa trùng thuộc tính.

Dù vậy, thứ tự giữa **các nguồn cấu hình và nhóm vị trí** vẫn có ảnh hưởng. Một file bên ngoài JAR hoặc tham số dòng lệnh có độ ưu tiên khác với file đóng gói trong JAR. Không nên dùng quy tắc “profile cuối thắng” như kết luận tuyệt đối cho mọi cách tổ chức nguồn cấu hình.

### Profile mặc định

Khi không có active profile được đặt, Spring sử dụng profile mặc định, thường tên là `default`. Spring Boot có thể nạp file `application-default.yml` nếu nó tồn tại. Có thể điều chỉnh các profile mặc định bằng thuộc tính `spring.profiles.default` tại vị trí cấu hình hợp lệ.

Một lựa chọn thiết kế phổ biến là để `application.yml` chứa giá trị an toàn và không phụ thuộc vào môi trường cụ thể, sau đó bật tường minh `dev`, `staging` hoặc `prod` trong lệnh chạy. Nhờ vậy, việc triển khai vào môi trường thực có thể được quan sát và kiểm soát.

## 10. @Profile dùng khi cần chọn bean, không chỉ chọn giá trị

Có những khác biệt không giải quyết được chỉ bằng một URL hoặc một cờ: môi trường phát triển dùng một bean mô phỏng, còn môi trường khác dùng triển khai thật. Khi đó, Spring hỗ trợ `@Profile` để chỉ đăng ký bean khi điều kiện phù hợp.

Ví dụ muốn dùng đồng hồ cố định trong một profile thử nghiệm đặc biệt, còn các profile khác dùng đồng hồ hệ thống:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ClockConfiguration {

    @Bean
    @Profile("time-simulation")
    Clock simulationClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }

    @Bean
    @Profile("!time-simulation")
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

Khi `time-simulation` hoạt động, ứng dụng có bean `Clock` cố định; khi profile đó không hoạt động, ứng dụng nhận `Clock` hệ thống. Cú pháp `!time-simulation` là điều kiện phủ định của biểu thức profile.

`@Profile` có thể đặt ở lớp `@Configuration` hoặc ở phương thức `@Bean`. Nó cũng có thể áp dụng cho thành phần được quét bởi Spring, tùy mục đích.

Tuy nhiên, không nên dùng `@Profile` để tạo hai lớp service giống hệt nhau chỉ khác một URL. Trong trường hợp đó, một bean duy nhất nhận đối tượng `@ConfigurationProperties` thường rõ ràng hơn và giảm trùng lặp.

Cũng cần cân nhắc trường hợp thiếu bean hoặc có nhiều bean cùng loại vì kích hoạt tổ hợp profile không dự kiến. Nếu một phần của ứng dụng cần đúng một bean kiểu `Clock`, cấu hình phải bảo đảm mỗi tổ hợp profile được hỗ trợ đáp ứng điều kiện đó.

## 11. Profile và cấu hình dạng nhiều tài liệu YAML

Không nhất thiết phải tạo file riêng cho mỗi profile. Spring Boot còn hỗ trợ một file YAML chứa nhiều tài liệu ngăn bằng `---`, mỗi tài liệu có thể được kích hoạt theo profile qua `spring.config.activate.on-profile`.

Ví dụ thay thế cho bộ file riêng:

```yaml
# application.yml - tài liệu chung
notification:
  enabled: false
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

notification:
  enabled: true
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

notification:
  enabled: true
  timeout: 2s
```

Khi `dev` hoạt động, tài liệu `on-profile: dev` được áp dụng; khi `prod` hoạt động, tài liệu `on-profile: prod` được áp dụng.

Hai kiểu tổ chức đều có chỗ dùng:

- **Tệp riêng:** `application-dev.yml` và `application-prod.yml` giúp khác biệt lớn hoặc phức tạp của môi trường dễ nhìn, dễ rà soát.
- **Nhiều tài liệu trong một tệp:** tiện khi khác biệt nhỏ và muốn đọc tổng thể tại một nơi.

Chỉ chọn một cách tổ chức chủ đạo cho cùng nhóm thuộc tính trong bài thực hành để tránh khó lần theo kết quả. Việc Spring Boot hỗ trợ cả hai không có nghĩa phải sử dụng đồng thời.

Lưu ý, `spring.config.activate.on-profile` là điều kiện **kích hoạt tài liệu cấu hình**, còn `spring.profiles.active` là cơ chế **chọn active profile**. Không đặt các thuộc tính chọn profile như `spring.profiles.active`, `spring.profiles.default` hoặc `spring.profiles.include` trong tài liệu chỉ được kích hoạt theo profile vì có những ràng buộc của cơ chế Config Data.

## 12. Profile groups: gom các profile thành một tên dễ dùng

Khi một môi trường luôn cần nhiều profile đi cùng nhau, Spring Boot có cơ chế **profile groups**. Ví dụ môi trường production cần nhóm `prod-db` và `prod-messaging`:

```yaml
# application.yml - tài liệu chung, không gắn on-profile
spring:
  profiles:
    group:
      production:
        - prod-db
        - prod-messaging
```

Khi chạy:

```bash
java -jar app.jar --spring.profiles.active=production
```

nhóm `production` có thể làm các profile thành viên `prod-db` và `prod-messaging` cũng tham gia. Nhờ đó, lệnh triển khai thể hiện một ý nghĩa cấp cao mà không phải liệt kê mọi profile phụ thuộc.

Nhưng đừng tạo profile group chỉ vì một file cấu hình dài. Cơ chế này phù hợp khi một tập profile có ý nghĩa độc lập nhưng cần được bật cùng nhau trong nhiều tình huống.

Theo quy tắc Config Data của Spring Boot, khai báo `spring.profiles.group` phải nằm trong tài liệu cấu hình không phụ thuộc profile, tương tự cách xử lý `spring.profiles.active` và `spring.profiles.include`. Đặt group trong `application-prod.yml` để tự sinh thêm profile khi file đó được nạp là cách thiết kế không hợp lệ.

## 13. Kết hợp profile với biến môi trường và kho bí mật

Một nhầm lẫn phổ biến là coi `application-prod.yml` như nơi đặt toàn bộ thông tin production, kể cả mật khẩu và token. Nên tách vấn đề:

**Profile** phù hợp với các giá trị mô tả môi trường và không nhạy cảm, như timeout, URL công khai của một dịch vụ, giới hạn kết nối hoặc chính sách log.

**Nguồn bí mật** phù hợp với mật khẩu, khóa truy cập, token và chứng chỉ. Những giá trị này có thể được cấp qua biến môi trường, kho bí mật của nền tảng triển khai hoặc cơ chế Config Data phù hợp.

Ví dụ trong `application-prod.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.invalid:5432/app

notification:
  timeout: 2s
```

Và ở môi trường chạy, mật khẩu có thể được cấp qua biến môi trường tương ứng, ví dụ `SPRING_DATASOURCE_PASSWORD`, bằng công cụ quản lý bí mật của nền tảng. Không đưa mật khẩu thật vào Git chỉ để hoàn thiện file theo profile.

Cách này giữ ý định cấu hình rõ: profile `prod` chọn bộ tham số chung cho môi trường production, còn bí mật được cấp tại nơi có quyền quản lý chúng. Profile không tự mã hóa hoặc che giấu giá trị trong file.

Đối với thông tin nhạy cảm, cũng tránh in toàn bộ `Environment` hoặc log cấu hình lúc khởi động. Nếu phải chẩn đoán, chỉ quan sát những khóa vô hại hoặc sử dụng endpoint chẩn đoán đã được kiểm soát quyền truy cập và xử lý giá trị nhạy cảm.

## 14. Kiểm thử cấu hình theo profile

Một ứng dụng có nhiều profile có nguy cơ chỉ chạy đúng ở `dev` mà lỗi khởi động ở `prod` vì thiếu khóa, sai kiểu dữ liệu hoặc thiếu bean. Vì thế, cần có cách xác nhận mỗi tổ hợp profile được hỗ trợ.

### 14.1. Kiểm tra trực tiếp bằng lệnh chạy

Để kiểm tra lần lượt:

```bash
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=staging
java -jar app.jar --spring.profiles.active=prod
```

Mỗi lệnh là một lần chạy riêng; dừng tiến trình trước khi chạy lệnh tiếp theo nếu cần. Tất cả đều dùng cùng JAR và chỉ đổi cách khởi động. Không nên lấy việc chạy thành công ở `dev` làm bằng chứng tự động rằng `prod` cũng đúng.

### 14.2. Chọn profile trong kiểm thử Spring

Với kiểm thử sử dụng Spring Test, `@ActiveProfiles` cho phép chọn profile của context kiểm thử:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationApplicationTest {

    @Test
    void contextLoads() {
    }
}
```

Khi sử dụng profile `test`, có thể đặt `application-test.yml` dưới `src/test/resources` hoặc dùng những nguồn cấu hình kiểm thử khác cho phù hợp. Đây là cách tách môi trường kiểm thử khỏi cấu hình production mà không phải sửa source chính.

Cần nhớ `@ActiveProfiles` điều khiển profile **trong context kiểm thử**, không phải công tắc thay đổi biến môi trường của một tiến trình production đang chạy.

### 14.3. Quan sát profile và giá trị hiệu lực

Để phục vụ thí nghiệm, có thể in tên profile đang hoạt động và một khóa vô hại:

```java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// Đặt phương thức này trong một lớp @Configuration hoặc @SpringBootApplication.
@Bean
ApplicationRunner showConfig(Environment env) {
    return args -> {
        System.out.println("Active profiles: "
            + Arrays.toString(env.getActiveProfiles()));
        System.out.println("Notification timeout: "
            + env.getProperty("notification.timeout"));
    };
}
```

`getActiveProfiles()` cho biết profile được kích hoạt tường minh; khi danh sách này trống, Spring vẫn có thể sử dụng profile mặc định. Nếu muốn xem thêm, `getDefaultProfiles()` cung cấp danh sách mặc định.

Trong ứng dụng thật, ưu tiên các biện pháp quan sát đã được quản lý và tránh log dữ liệu nhạy cảm. Spring Boot Actuator có thể cung cấp thông tin môi trường hoặc các đối tượng `@ConfigurationProperties` khi được cấu hình phù hợp, nhưng những endpoint đó cần được bảo vệ.

## 15. Các sai lầm thường gặp

### 15.1. Cho rằng tên máy tự quyết định profile

Một máy có hostname chứa chữ `prod` không khiến Spring Boot tự kích hoạt profile `prod`. Cần đặt `SPRING_PROFILES_ACTIVE`, `spring.profiles.active` hoặc cơ chế chọn profile hợp lệ. Khi kiểm tra lỗi triển khai, nhìn profile thực sự hoạt động thay vì đoán từ tên máy.

### 15.2. Gắn cứng profile môi trường vào mã

Ví dụ:

```java
String active = "prod";
if ("prod".equals(active)) {
    // Chọn URL dịch vụ tại đây
}
```

Đây chỉ là nhánh điều kiện Java, không phải Spring profile. Cách viết này trộn quyết định triển khai vào logic nghiệp vụ và buộc sửa mã khi chuyển môi trường. Nếu chỉ khác URL, cấu hình thuộc tính sẽ phù hợp hơn.

### 15.3. Để một file profile chứa quá nhiều bí mật

Một file `application-prod.yml` trong repository không trở nên an toàn chỉ vì có chữ `prod`. Mật khẩu, token và khóa truy cập cần được cấp bằng kênh bảo mật phù hợp. Profile quyết định tài liệu hoặc bean nào được kích hoạt, không cấp quyền hay mã hóa dữ liệu.

### 15.4. Kích hoạt những profile mâu thuẫn

Nếu đồng thời bật `dev,prod`, hai bộ file có thể cùng khai báo `notification.endpoint`. Giá trị cuối cùng sẽ phụ thuộc quy tắc ưu tiên của các nguồn và thứ tự profile trong cấu hình đã nạp. Những bean `@Profile("dev")` và `@Profile("prod")` cũng có thể cùng được đăng ký và tạo xung đột nếu chúng phục vụ cùng một vai trò.

Thiết kế các profile tương thích với nhau; tránh bật đồng thời hai profile đại diện cho hai môi trường loại trừ nhau nếu ứng dụng không có quy tắc xử lý rõ ràng.

### 15.5. Cho rằng ứng dụng tự nạp lại profile đang chạy

Thay `application-prod.yml` hoặc biến môi trường sau khi ứng dụng khởi động không bảo đảm bean đã tạo tự đổi giá trị. Trong ứng dụng Spring Boot thông thường, người triển khai thường khởi động lại tiến trình để áp dụng cấu hình mới. Cơ chế làm mới động cần được thiết kế riêng.

### 15.6. Dùng profile cho quyết định theo người dùng hoặc theo từng yêu cầu

Spring profile liên quan đến context ứng dụng khi khởi động. Quyết định “khách hàng A được giảm giá 10%”, “người dùng B có quyền quản trị” hoặc “yêu cầu này phải chạy chiến dịch X” thường thuộc về dữ liệu nghiệp vụ, phân quyền hoặc feature flags. Không nên tạo profile Spring cho từng người dùng hoặc từng request.

## 16. Thực hành từng bước: một JAR cho ba môi trường

Hãy tạo ứng dụng có các file `application.yml`, `application-dev.yml` và `application-prod.yml` như phần 3, rồi giữ nguyên `NotificationProperties` và `NotificationService`.

**Bước 1 — Chạy với dev.**

```bash
java -jar app.jar --spring.profiles.active=dev
```

Dự đoán: `enabled=true`, `timeout=10s`, `endpoint=http://localhost:9001/notification`.

**Bước 2 — Chạy với prod.**

```bash
java -jar app.jar --spring.profiles.active=prod
```

Dự đoán: `enabled=true`, `timeout=2s`, `endpoint=https://production.example.invalid/notification`.

**Bước 3 — Ghi đè một khóa từ command line.**

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=8s
```

Dự đoán: endpoint vẫn đến từ cấu hình theo `prod`, còn timeout là tám giây do tham số dòng lệnh có ưu tiên cao hơn file Config Data trong tình huống tiêu chuẩn.

**Bước 4 — Bỏ profile và bỏ tham số override.**

```bash
java -jar app.jar
```

Nếu không có nguồn cấu hình hay profile nào khác tham gia, dự đoán: `enabled=false`, `timeout=3s` và endpoint mặc định từ `application.yml`. Nếu kết quả khác, kiểm tra active/default profiles thực tế cùng các biến môi trường còn tồn tại.

**Bước 5 — Tạo một test với `@ActiveProfiles("test")`.**

Đặt `application-test.yml` có `notification.timeout: 1s`. Viết kiểm thử khởi động context và đọc giá trị của `NotificationProperties.timeout()` để xác nhận giá trị dành cho test được liên kết đúng. Chỉ dùng endpoint giả và dữ liệu an toàn.

Sau mỗi bước, trả lời:

1. Profile nào đang hoạt động?
2. Tệp nào được nạp vì profile đó?
3. Khóa nào đến từ cấu hình chung và khóa nào được ghi đè?
4. Có nguồn ưu tiên cao hơn file theo profile không?
5. Bean có cần sửa mã Java khi chuyển môi trường không?

Câu trả lời của bước 5 đặc biệt quan trọng: profile giúp đổi tập cấu hình cho context kiểm thử, còn mã của bean không cần biết mình đang chạy ở `test` hay `prod`.

## 17. Một cách thiết kế cấu hình dễ duy trì

Khi bắt đầu xây dựng cấu hình cho một dịch vụ, có thể áp dụng trình tự quyết định sau:

1. **Xác định thuộc tính cần thiết:** endpoint, timeout, giới hạn kết nối, cờ bật/tắt, v.v.
2. **Đặt mặc định an toàn ở `application.yml`:** ưu tiên giá trị không gây thao tác nguy hiểm nếu người triển khai quên bật profile.
3. **Nhóm khác biệt thực sự theo môi trường:** chẳng hạn `application-dev.yml` và `application-prod.yml`, nhưng chỉ khi chúng biểu diễn một tập giá trị có ý nghĩa.
4. **Để biến môi trường hoặc nền tảng triển khai quyết định profile hoạt động:** cùng một bản dựng được phát hành đến các nơi khác nhau.
5. **Cấp bí mật riêng:** không đưa credential thật vào cấu hình đã commit.
6. **Liên kết cấu hình vào đối tượng có kiểu:** dùng `@ConfigurationProperties` để bean nhận giá trị dễ kiểm soát, thay vì rải tên khóa khắp mã.
7. **Chỉ dùng `@Profile` cho bean khi hành vi/triển khai thật sự khác nhau:** không tạo nhiều bean nếu chỉ khác vài giá trị.
8. **Kiểm thử các profile được hỗ trợ:** đặc biệt kiểm tra có đủ giá trị bắt buộc và không thiếu hoặc trùng bean.

Một bảng quy ước nhỏ trong tài liệu triển khai có thể giúp cả nhóm:

| Profile | Mục đích | Điểm khác biệt chính | Nguồn bí mật |
| --- | --- | --- | --- |
| `dev` | Phát triển tại máy cá nhân | Mock/local endpoint, log chi tiết | Máy phát triển hoặc secret dev |
| `test` | Chạy kiểm thử tự động | Service giả, cơ sở dữ liệu kiểm thử | Bí mật kiểm thử hoặc không cần |
| `staging` | Kiểm tra trước phát hành | Dịch vụ tích hợp, chính sách gần production | Secret staging |
| `prod` | Phục vụ người dùng thật | Endpoint thật, giới hạn tài nguyên phù hợp | Secret production |

Bảng chỉ là quy ước thiết kế tham khảo. Không phải mọi ứng dụng đều cần đủ bốn profile, và tên profile phải phản ánh đúng cách nhóm triển khai của dự án.

## 18. Ghi nhớ

Profile là **cơ chế lựa chọn ngữ cảnh cấu hình và đăng ký bean trong Spring**, giúp ứng dụng dùng những giá trị hoặc thành phần khác nhau theo môi trường chạy. Một profile không phải cả môi trường; nó là nhãn điều kiện mà Spring Boot có thể dùng để nạp các tệp cấu hình tương ứng và áp dụng `@Profile`.

Nên tách cấu hình theo profile khi một nhóm khác biệt đi cùng nhau theo môi trường, cần duy trì **một JAR cho nhiều nơi triển khai**, hoặc cần chọn một cách triển khai bean theo ngữ cảnh rõ ràng. Không nên dùng profile để thay thế cho các giá trị động theo người dùng, các cờ tính năng độc lập hay hệ thống quản lý bí mật.

Luồng thực tế là:

```text
Chọn profile lúc khởi động
       |
       v
Nạp cấu hình chung và cấu hình theo profile
       |
       v
Giải quyết ưu tiên giữa các nguồn thuộc tính
       |
       v
Binding / injection vào bean
       |
       v
Một mã Java hoạt động với giá trị phù hợp môi trường
```

Khi gặp hiện tượng “đã bật `prod` nhưng bean vẫn dùng giá trị khác”, hãy kiểm tra **profile thực sự hoạt động**, **tệp đã được nạp**, **nguồn có độ ưu tiên cao hơn**, rồi mới kiểm tra binding. Cách tiếp cận đó giúp phân biệt lỗi chọn profile với lỗi nguồn cấu hình hoặc lỗi liên kết dữ liệu.

Tài liệu tham khảo để học tiếp: [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) và [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).