# @Profile: chọn bean theo profile và liên hệ với tệp cấu hình

## 1. Vấn đề: cùng một ứng dụng nhưng cần những thành phần khác nhau

Một ứng dụng Spring Boot có thể chạy ở máy lập trình viên, môi trường kiểm thử, staging và production. Những môi trường này thường dùng **cùng mã nguồn**, nhưng có hai loại khác biệt:

1. **Giá trị cấu hình khác nhau**: địa chỉ API, mức ghi log, cổng HTTP, thời gian chờ hoặc tên dịch vụ.
2. **Thành phần Java cần được tạo khác nhau**: ở máy phát triển dùng bộ gửi thông báo ra console; ở production dùng bộ gửi thông báo tới hệ thống bên ngoài.

Spring Boot có hai cơ chế liên quan nhưng đảm nhận hai việc khác nhau:

- **Profile và Config Data**: chọn các tệp hoặc tài liệu cấu hình phù hợp, chẳng hạn `application-dev.yaml` và `application-prod.yaml`. Giá trị trong những nguồn này đi vào `Environment`.
- **`@Profile` của Spring Framework**: đặt điều kiện để **đăng ký bean** vào `ApplicationContext` tùy theo profile hiện đang có hiệu lực.

Nếu nhầm hai cơ chế, bạn có thể gặp tình huống tệp `application-prod.yaml` đã được đọc nhưng bean production chưa xuất hiện; hoặc bean production đã được tạo nhưng vẫn nhận giá trị từ nguồn cấu hình khác có ưu tiên cao hơn.

Bài này giải thích điểm giao nhau: **Spring xác định profile đang hoạt động → nạp cấu hình phù hợp → đánh giá `@Profile` → tạo bean đủ điều kiện và tiêm phụ thuộc**.

## 2. Profile trong Spring là gì?

Profile là **nhãn môi trường logic** mà Spring sử dụng để bật hoặc tắt các nhóm bean hay cấu hình. Một số tên thường gặp là:

- `dev`: phát triển.
- `test`: kiểm thử.
- `staging`: môi trường kiểm thử trước triển khai.
- `prod`: production.
- `cloud`, `local`: đặc điểm hạ tầng hoặc cách chạy.

Đây là những **tên do ứng dụng lựa chọn**, không phải danh sách cố định Spring Boot bắt buộc sử dụng. Bạn có thể chọn các tên phù hợp hệ thống; quan trọng là thống nhất giữa cấu hình, mã Java và cách khởi chạy.

Một ứng dụng có thể kích hoạt **nhiều profile cùng lúc**. Ví dụ `prod,cloud` nghĩa là cả `prod` và `cloud` đang hoạt động; nó không tạo ra một profile ghép mới tên `prod,cloud`.

Cơ chế profile xuất phát từ `Environment`. Spring Framework cung cấp:

~~~java
Environment environment;

String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
~~~

`getActiveProfiles()` cho biết những profile được kích hoạt rõ ràng. `getDefaultProfiles()` cung cấp nhóm profile mặc định được dùng khi không có profile nào được kích hoạt rõ ràng. Theo mặc định của Spring, tên profile mặc định là `default`.

**Profile không đồng nghĩa một máy chủ hay một file.** Một profile có thể chọn nhiều bean và nhiều nguồn cấu hình. Ngược lại, nhiều profile có thể cùng hoạt động trong một lần chạy.

## 3. @Profile thực sự làm gì?

`@Profile` là annotation của Spring Framework:

~~~java
import org.springframework.context.annotation.Profile;
~~~

Nó đặt **điều kiện đăng ký thành phần vào Spring container**. Khi cấu hình được xử lý, Spring kiểm tra điều kiện này dựa trên các profile có hiệu lực trong `Environment`:

- Điều kiện phù hợp → bean hoặc cấu hình được xem xét đăng ký.
- Điều kiện không phù hợp → định nghĩa bean ấy không được đăng ký từ cấu hình đó.
- Nếu một thành phần khác bắt buộc tiêm đúng bean đang vắng mặt → quá trình tạo context có thể lỗi vì thiếu phụ thuộc.

Điểm khác biệt rất quan trọng:

> `@Profile` không chỉ đổi giá trị trả về của một bean đã tồn tại; nó quyết định liệu **định nghĩa bean có được đăng ký và khởi tạo** trong context tương ứng hay không.

`@Profile` thường xuất hiện ở:

- Lớp `@Component`, `@Service`, `@Repository` hoặc cấu hình tương tự.
- Lớp `@Configuration` để điều kiện áp dụng cho toàn bộ cấu hình bên trong.
- Phương thức `@Bean` để chỉ điều kiện hóa một bean cụ thể.

Nó không phải công cụ dùng để đặt giá trị thuộc tính và không tự động nạp tệp YAML. Nhiệm vụ đó thuộc về `Environment`, Config Data và cơ chế gắn kết cấu hình của Spring Boot.

## 4. Ví dụ đầu tiên: tạo hai bean theo dev và prod

Giả sử ứng dụng cần một cổng gửi thông báo. Để đơn giản, mỗi cách triển khai trả về mô tả kênh sử dụng; ví dụ không thực hiện kết nối mạng.

Định nghĩa một giao diện Java:

~~~java
package com.example.demo.notice;

public interface NoticeChannel {
    String describe();
}
~~~

Cấu hình có hai bean:

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NoticeChannelConfiguration {

    @Bean
    @Profile("dev")
    NoticeChannel localNoticeChannel() {
        return () -> "Gửi thông báo qua console trong môi trường dev";
    }

    @Bean
    @Profile("prod")
    NoticeChannel productionNoticeChannel() {
        return () -> "Gửi thông báo qua hệ thống production";
    }
}
~~~

Với profile `dev`, Spring đăng ký `localNoticeChannel` và bỏ qua `productionNoticeChannel`. Với profile `prod`, điều ngược lại xảy ra.

Một service dùng bean đang tồn tại:

~~~java
package com.example.demo.notice;

import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final NoticeChannel channel;

    public NoticeService(NoticeChannel channel) {
        this.channel = channel;
    }

    public String currentChannel() {
        return channel.describe();
    }
}
~~~

Bây giờ khởi chạy:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`NoticeService` nhận bean dành cho dev. Khi chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

nó nhận bean dành cho prod.

### Hai tình huống cần dự đoán trước

**Không có profile phù hợp:** Nếu không kích hoạt profile nào, theo mặc định `default` có hiệu lực. Hai điều kiện `@Profile("dev")` và `@Profile("prod")` đều không thỏa. `NoticeService` cần một `NoticeChannel`, nhưng không có bean phù hợp. Context có thể không khởi động được vì không giải quyết được phụ thuộc.

**Cùng bật dev và prod:** Với `--spring.profiles.active=dev,prod`, **cả hai bean** `NoticeChannel` đều được đăng ký. Constructor `NoticeService(NoticeChannel)` sẽ mơ hồ vì có hai ứng viên cùng kiểu, trừ khi bạn quy định cách chọn qua `@Qualifier`, `@Primary` hoặc thiết kế điều kiện loại trừ nhau.

Điều này cho thấy `@Profile` là một điều kiện lựa chọn độc lập cho **mỗi bean**, không phải công tắc bảo đảm toàn ứng dụng có đúng một chế độ.

## 5. Dùng biểu thức profile để diễn đạt điều kiện chính xác

Ngoài một tên đơn lẻ, `@Profile` hỗ trợ biểu thức profile.

### 5.1. Điều kiện phủ định: !prod

~~~java
@Bean
@Profile("!prod")
NoticeChannel localNoticeChannel() {
    return () -> "Kênh dùng ngoài production";
}

@Bean
@Profile("prod")
NoticeChannel productionNoticeChannel() {
    return () -> "Kênh production";
}
~~~

`@Profile("!prod")` có nghĩa **profile `prod` không hoạt động**. Nó phù hợp khi:

- `dev` hoạt động nhưng `prod` không hoạt động.
- `test` hoặc `staging` hoạt động mà không có `prod`.
- Không có profile chủ động và chỉ có `default`, vì `prod` vẫn không hoạt động.

Nếu `prod` hoạt động, bean `localNoticeChannel` bị loại. Cách viết này thường phù hợp hơn cặp `dev`/`prod` khi bạn muốn có một triển khai dự phòng cho mọi môi trường ngoài production.

### 5.2. Nhiều tên trong một annotation: điều kiện OR

~~~java
@Bean
@Profile({"dev", "test"})
NoticeChannel developmentNoticeChannel() {
    return () -> "Kênh dành cho dev hoặc test";
}
~~~

Khi dùng mảng tên như trên, bean đủ điều kiện nếu **ít nhất một** biểu thức/tên phù hợp. Nói cách khác, `dev` **hoặc** `test` đều kích hoạt bean.

### 5.3. Toán tử AND, OR và NOT

~~~java
@Bean
@Profile("prod & cloud")
NoticeChannel cloudProductionChannel() {
    return () -> "Kênh cho production chạy trên cloud";
}
~~~

Điều kiện này chỉ thỏa khi **đồng thời có** `prod` và `cloud`.

~~~java
@Bean
@Profile("dev | test")
NoticeChannel sandboxChannel() {
    return () -> "Kênh cho dev hoặc test";
}
~~~

Dùng `|` khi muốn một trong hai profile; ký hiệu `&` khi muốn cả hai; `!` khi muốn phủ định. Với biểu thức phức tạp, dùng ngoặc để tránh nhập nhằng:

~~~java
@Profile("(prod & cloud) | staging")
~~~

Ý nghĩa: production trên cloud **hoặc** staging. Không nên viết biểu thức trộn `&` và `|` mà không có ngoặc rõ ràng.

### 5.4. Điều kiện ở cấp lớp và cấp phương thức

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("cloud")
class CloudConfig {

    @Bean
    @Profile("prod")
    NoticeChannel cloudNoticeChannel() {
        return () -> "Kênh production trên cloud";
    }
}
~~~

Lớp cấu hình chỉ được xử lý khi `cloud` phù hợp. Bên trong nó, phương thức tạo bean còn yêu cầu `prod`. Kết quả là bean chỉ xuất hiện khi **cả hai điều kiện đều thỏa**.

Không nên hiểu điều kiện trên phương thức là ghi đè điều kiện của cả lớp. Nếu lớp cấu hình không được đưa vào context, bean bên trong không thể được đăng ký từ lớp ấy.

## 6. Cách kích hoạt profile cho ứng dụng

Cơ chế `@Profile` dựa vào profile đang có hiệu lực trong `Environment`. Có một số cách khai báo chúng.

### 6.1. Tham số dòng lệnh

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Nhiều profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod,cloud
~~~

Đây là cách minh bạch cho ví dụ và lệnh chạy thử. Các đối số dòng lệnh kiểu `--key=value` thường có độ ưu tiên cao trong tập nguồn cấu hình của Spring Boot.

### 6.2. Biến môi trường

Trên shell kiểu Unix:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
java -jar app.jar
~~~

Hoặc:

~~~bash
SPRING_PROFILES_ACTIVE=prod,cloud java -jar app.jar
~~~

Spring Boot gắn biến môi trường `SPRING_PROFILES_ACTIVE` với thuộc tính `spring.profiles.active`.

Trên Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
~~~

Nếu có cả biến môi trường và tham số dòng lệnh `--spring.profiles.active=prod`, theo thứ tự nguồn mặc định, tham số dòng lệnh có thể ghi đè giá trị biến môi trường.

### 6.3. Java System property

~~~bash
java -Dspring.profiles.active=dev -jar app.jar
~~~

Chú ý `-D...` là tùy chọn của **JVM** và thường đặt trước `-jar`; `--spring.profiles.active=...` là đối số ứng dụng đặt sau `app.jar`.

### 6.4. application.yaml không đặc thù profile

Có thể đặt profile mặc định cho cách khởi chạy ứng dụng trong tài liệu cấu hình thông thường:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Tuy nhiên, việc đóng gói sẵn `active: dev` vào tệp chung có thể không phản ánh đúng ý định khi triển khai production. Nên cho môi trường triển khai quyết định profile qua cơ chế cấu hình phù hợp.

**Ràng buộc quan trọng của Spring Boot Config Data:** `spring.profiles.active` và `spring.profiles.default` chỉ hợp lệ trong **tài liệu không đặc thù profile**. Không đặt chúng trong `application-prod.yaml` hoặc trong một tài liệu YAML được kích hoạt bằng `spring.config.activate.on-profile`. Những tài liệu ấy không được dùng để tự quyết định profile đang hoạt động.

### 6.5. Thiết lập bằng SpringApplication

~~~java
import org.springframework.boot.SpringApplication;

public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(DemoApplication.class);
        application.setAdditionalProfiles("local");
        application.run(args);
    }
}
~~~

`setAdditionalProfiles` bổ sung profile vào tập có hiệu lực. Đây là tùy chọn lập trình khi thực sự cần điều khiển quá trình khởi động. Trong các ứng dụng triển khai qua nhiều môi trường, khai báo từ bên ngoài thường thuận tiện hơn vì không cần biên dịch lại.

## 7. Mối liên hệ với application-dev.yaml và application-prod.yaml

Spring Boot không chỉ dùng profile để đánh giá `@Profile`. Nó còn dùng profile để chọn các tài liệu Config Data phù hợp.

Giả sử có:

~~~text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
~~~

Tệp nền:

~~~yaml
# application.yaml
app:
  notice:
    title: "Thông báo"
    endpoint: "https://example.invalid"
    retry-count: 2
~~~

Tệp dev:

~~~yaml
# application-dev.yaml
app:
  notice:
    title: "Thông báo phát triển"
    endpoint: "http://localhost:8089"
    retry-count: 1
~~~

Tệp prod:

~~~yaml
# application-prod.yaml
app:
  notice:
    title: "Thông báo chính thức"
    endpoint: "https://notify.example.com"
    retry-count: 5
~~~

Với:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Spring Boot thường nạp cấu hình nền rồi bổ sung tài liệu theo profile `dev`. Các khóa ở `application-dev.yaml` có thể ghi đè khóa trùng trong `application.yaml` theo quy tắc ưu tiên Config Data.

Với `--spring.profiles.active=prod`, cấu hình `application-prod.yaml` được xét thay vì biến thể dev, và giá trị hiệu lực cho các khóa minh họa là:

| Thuộc tính | Với dev | Với prod |
| --- | --- | --- |
| `app.notice.title` | `Thông báo phát triển` | `Thông báo chính thức` |
| `app.notice.endpoint` | `http://localhost:8089` | `https://notify.example.com` |
| `app.notice.retry-count` | `1` | `5` |

Các giá trị thực tế vẫn có thể bị biến môi trường, Java System property, tham số CLI hoặc các nguồn khác có ưu tiên cao hơn ghi đè. Profile chỉ quyết định **tài liệu nào có cơ hội tham gia**; nó không bảo đảm tệp theo profile luôn thắng mọi nguồn.

### Phân biệt rõ hai câu hỏi

**“Khi prod hoạt động, app.notice.endpoint lấy từ đâu?”**

Đó là câu hỏi về **nguồn cấu hình và thứ tự ưu tiên**. Spring Boot giải quyết nó qua Config Data và `Environment`.

**“Khi prod hoạt động, bean NoticeChannel nào tồn tại?”**

Đó là câu hỏi về **điều kiện đăng ký bean**. Spring Framework đánh giá `@Profile`.

Hai cơ chế có cùng đầu vào là profile đang hoạt động, nhưng chúng không thay thế cho nhau.

## 8. Ghép hoàn chỉnh: @Profile và @ConfigurationProperties

Một thiết kế thực tế thường cần **đúng loại bean** và **đúng các tham số cho bean đó**. Ta có thể để `@Profile` chọn cách triển khai, rồi dùng `@ConfigurationProperties` cung cấp giá trị cấu hình.

### 8.1. Định nghĩa lớp thuộc tính có kiểu

~~~java
package com.example.demo.notice;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notice")
public record NoticeProperties(
        String title,
        URI endpoint,
        int retryCount) {
}
~~~

Trong lớp `@SpringBootApplication`, bật quét cấu hình:

~~~java
package com.example.demo;

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

### 8.2. Tạo bean theo profile và đọc giá trị qua properties

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NoticeConfiguration {

    @Bean
    @Profile("!prod")
    NoticeChannel localChannel(NoticeProperties properties) {
        return () -> "[LOCAL] " + properties.title()
                + " -> " + properties.endpoint();
    }

    @Bean
    @Profile("prod")
    NoticeChannel productionChannel(NoticeProperties properties) {
        return () -> "[PROD] " + properties.title()
                + " -> " + properties.endpoint();
    }
}
~~~

Trong ví dụ:

- `@Profile("!prod")` và `@Profile("prod")` quyết định bean nào được đăng ký.
- `NoticeProperties` được gắn từ các thuộc tính `app.notice.*` có hiệu lực.
- `application-dev.yaml` và `application-prod.yaml` là những nguồn cung cấp giá trị trong số các nguồn Spring Boot nạp.
- Nếu một biến môi trường hay đối số CLI ghi đè `app.notice.title`, bean đang được chọn sẽ nhận giá trị hiệu lực mới ở lúc tạo, chứ không tự động giữ giá trị gốc của tệp theo profile.

Chẳng hạn:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.notice.title="Thông báo khẩn"
~~~

Bean `productionChannel` được đăng ký vì `prod` đang hoạt động; nhưng tiêu đề nhận vào là `Thông báo khẩn` do tham số CLI ghi đè thuộc tính trong tệp.

**Đặc biệt lưu ý:** phương thức `NoticeChannel.describe()` chỉ trả về chuỗi minh họa. Trong hệ thống thật, phần triển khai có thể dùng HTTP client hoặc message broker, nhưng cần thêm cấu hình và xử lý lỗi tương ứng. Ví dụ này tập trung vào lựa chọn bean và gắn cấu hình.

## 9. Dùng @Profile trên lớp thay vì @Bean

Bạn có thể gắn trực tiếp `@Profile` lên lớp thành phần:

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevNoticeChannel implements NoticeChannel {
    @Override
    public String describe() {
        return "Thông báo dành cho môi trường dev";
    }
}
~~~

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProdNoticeChannel implements NoticeChannel {
    @Override
    public String describe() {
        return "Thông báo dành cho môi trường prod";
    }
}
~~~

Spring component scan tìm thấy các lớp này, nhưng `@Profile` quyết định chúng có được đăng ký thành bean hay không.

Lựa chọn giữa hai cách:

- **Gắn vào lớp `@Component`** khi thành phần độc lập, tự đủ phụ thuộc và phù hợp component scan.
- **Gắn vào phương thức `@Bean`** khi việc xây dựng đối tượng cần logic cấu hình, đối tượng thuộc thư viện ngoài hoặc bạn muốn tập trung cấu hình tạo bean ở một chỗ.
- **Gắn vào lớp `@Configuration`** khi cả một nhóm bean chỉ tồn tại trong một môi trường nhất định.

Không cần kết hợp cả ba cách cho cùng một đối tượng trong ví dụ thực tế; hãy chọn một cách đăng ký rõ ràng để tránh tạo nhiều bean ngoài ý muốn.

## 10. @Profile("default") và trường hợp không đặt profile

Spring Framework có profile mặc định `default`. Khi **không có profile được kích hoạt rõ ràng**, nhóm profile mặc định được dùng để đánh giá điều kiện.

Ví dụ:

~~~java
@Bean
@Profile("default")
NoticeChannel defaultChannel() {
    return () -> "Kênh mặc định";
}
~~~

Khi chạy thông thường mà không đặt `spring.profiles.active`, bean trên có thể được đăng ký vì `default` đang có hiệu lực. Nhưng nếu chạy với `spring.profiles.active=dev`, profile mặc định không còn đóng vai trò thay cho nhóm active; điều kiện `@Profile("default")` không tự nhiên phù hợp chỉ vì Spring có khái niệm mặc định.

Có thể chỉ định các profile mặc định qua `spring.profiles.default` trong một tài liệu không đặc thù profile:

~~~properties
spring.profiles.default=local
~~~

Khi đó, nếu không có profile active rõ ràng, `local` có thể đóng vai trò profile mặc định. Spring Boot cũng hỗ trợ `spring.profiles.default=none` để không kích hoạt profile mặc định thông thường.

So sánh hai lựa chọn:

~~~java
@Profile("default")
~~~

có nghĩa **chỉ** theo profile tên `default` phù hợp.

~~~java
@Profile("!prod")
~~~

có nghĩa **không có `prod` trong nhóm profile hiệu lực**. Điều kiện thứ hai rộng hơn: nó còn phù hợp với `dev`, `test`, `staging` và nhiều tình huống khác mà `prod` không hoạt động.

Nếu mục tiêu là một lựa chọn dự phòng cho mọi môi trường ngoài production, `!prod` thường diễn đạt đúng hơn `default`.

## 11. Tài liệu YAML kích hoạt theo profile

Ngoài việc tách nhiều tệp `application-{profile}.yaml`, Spring Boot hỗ trợ **nhiều tài liệu trong cùng một tệp YAML** bằng dấu phân cách `---` và điều kiện `spring.config.activate.on-profile`.

Ví dụ:

~~~yaml
# application.yaml — tài liệu dùng chung
app:
  banner: "Ứng dụng Demo"
  notice:
    retry-count: 2

---
spring:
  config:
    activate:
      on-profile: dev

app:
  banner: "Ứng dụng Demo — DEV"
  notice:
    retry-count: 1

---
spring:
  config:
    activate:
      on-profile: prod

app:
  banner: "Ứng dụng Demo — PROD"
  notice:
    retry-count: 5
~~~

Khi profile `dev` hoạt động, tài liệu có `on-profile: dev` được kích hoạt. Khi `prod` hoạt động, tài liệu có `on-profile: prod` được kích hoạt.

Điều kiện này cũng có thể dùng biểu thức profile, ví dụ:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
~~~

**Không nhầm hai annotation/cấu hình:**

- `@Profile("prod")` là điều kiện đăng ký **bean Java**.
- `spring.config.activate.on-profile: prod` là điều kiện kích hoạt **tài liệu cấu hình**.

Chúng giống nhau ở tên profile, khác nhau ở đối tượng mà chúng kiểm soát.

### Điều cần tránh

Đừng đặt:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: dev
~~~

Tài liệu được kích hoạt theo profile không phải nơi hợp lệ để quyết định `spring.profiles.active`. Cấu hình điều khiển việc chọn profile phải ở nguồn có hiệu lực trước quá trình kích hoạt tài liệu profile-specific, chẳng hạn tài liệu chung hoặc tham số khởi chạy.

Tương tự, trong Spring Boot hiện đại, không nên dùng cú pháp cũ `spring.profiles` bên trong một tài liệu YAML để kích hoạt nó. Hãy dùng `spring.config.activate.on-profile`.

## 12. Nhiều profile cùng hoạt động: hai ảnh hưởng riêng

Lệnh:

~~~bash
java -jar app.jar --spring.profiles.active=dev,cloud
~~~

có hai hệ quả:

1. Các nguồn cấu hình theo `dev` và `cloud` có thể được nạp; nếu trùng khóa, Spring Boot áp dụng quy tắc thứ tự Config Data, trong đó profile khai báo sau thường có ưu tiên hơn khi các nguồn có cùng cấp liên quan.
2. Một bean với `@Profile("dev")` hoặc `@Profile("cloud")` đều có thể đủ điều kiện; bean `@Profile("dev & cloud")` cũng đủ điều kiện.

Giả sử:

~~~java
@Bean
@Profile("dev")
NoticeChannel devChannel() {
    return () -> "dev";
}

@Bean
@Profile("cloud")
NoticeChannel cloudChannel() {
    return () -> "cloud";
}
~~~

Với cả `dev` và `cloud` hoạt động, **cả hai bean được đăng ký**. Việc tệp `application-cloud.yaml` có ưu tiên cao hơn `application-dev.yaml` đối với cùng một thuộc tính **không loại bỏ bean** `devChannel`.

Đây là nhầm lẫn quan trọng: **độ ưu tiên của cấu hình không phải độ ưu tiên của bean theo `@Profile`**.

Nếu muốn chỉ có một bean, hãy thiết kế điều kiện loại trừ nhau, hoặc chọn bean khi tiêm qua `@Primary` hay `@Qualifier` theo chủ đích. Đừng phụ thuộc vào thứ tự profile để Spring tự chọn “bean chiến thắng”.

### Profile group

Spring Boot hỗ trợ nhóm profile để kích hoạt nhiều profile liên quan bằng một tên:

~~~yaml
spring:
  profiles:
    group:
      production:
        - "proddb"
        - "prodmq"
~~~

Khi kích hoạt `production`, các profile thành viên `proddb` và `prodmq` cũng được thêm vào tập profile có hiệu lực. Từ đó, các bean hoặc tài liệu với điều kiện theo những tên này cũng có thể được kích hoạt.

Khai báo nhóm profile thuộc cấu hình không đặc thù profile; không đặt nó trong tài liệu `application-production.yaml` hoặc một tài liệu chỉ hoạt động khi profile khác phù hợp.

Nhóm profile giúp giảm số tên phải gõ khi khởi chạy, nhưng không tự xử lý sự mơ hồ giữa những bean cùng kiểu.

## 13. Khác nhau giữa @Profile và @ConditionalOnProperty

Trong Spring Boot, bên cạnh `@Profile` còn có điều kiện dựa vào **giá trị thuộc tính**:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

So sánh:

| Nhu cầu | Lựa chọn thường hợp lý |
| --- | --- |
| Dùng một triển khai khác khi chạy production | `@Profile("prod")` |
| Dùng một bean khi chạy dev hoặc test | `@Profile({"dev", "test"})` |
| Bật tính năng khi `app.audit.enabled=true` | `@ConditionalOnProperty` |
| Chỉ tạo bean nếu một class/thành phần khác tồn tại | Các annotation điều kiện khác, ví dụ `@ConditionalOnClass`, `@ConditionalOnBean` |
| Chỉ đổi endpoint, thời gian chờ, số lần thử lại | `@ConfigurationProperties` hoặc `@Value`; không nhất thiết cần bean khác |

Ví dụ bật tính năng bằng một giá trị cấu hình:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true")
AuditReporter auditReporter() {
    return new AuditReporter();
}
~~~

Giả sử `AuditReporter` là lớp do ứng dụng định nghĩa. Bean này được tạo nếu thuộc tính `app.audit.enabled` có giá trị phù hợp; quyết định không bắt buộc gắn với tên `dev` hay `prod`.

Khi một tính năng có thể bật/tắt ở bất kỳ môi trường nào, điều kiện dựa trên thuộc tính thường linh hoạt hơn việc tạo thêm nhiều profile cho từng tổ hợp lựa chọn.

Ngược lại, khi bạn muốn mô tả **nhóm môi trường vận hành**, `@Profile` vẫn có ý nghĩa rõ ràng.

## 14. Điều gì xảy ra khi bean không tồn tại?

Đây là hậu quả thực tế cần dự đoán trước khi đặt `@Profile`.

### 14.1. Thiếu bean bắt buộc

~~~java
@Service
class NoticeFacade {
    NoticeFacade(NoticeChannel channel) {
        // ...
    }
}
~~~

Nếu `NoticeChannel` chỉ được tạo với `@Profile("prod")` nhưng ứng dụng chạy `dev`, Spring sẽ không tìm được bean thỏa kiểu yêu cầu. Context thường thất bại khi khởi động với lỗi không giải quyết được phụ thuộc.

Các cách xử lý đúng phụ thuộc thiết kế:

- Cung cấp triển khai phù hợp cho môi trường còn lại.
- Chuyển chính thành phần tiêu thụ vào cùng điều kiện profile, nếu toàn bộ chức năng chỉ thuộc một môi trường.
- Định nghĩa phụ thuộc tùy chọn khi chức năng thật sự tùy chọn, thay vì bỏ qua sự thiếu vắng ngoài ý muốn.
- Dùng điều kiện phủ định hoặc bean dự phòng có chủ đích.

### 14.2. Nhiều bean cùng kiểu

Khi nhiều điều kiện cùng đúng, cả hai bean có thể được tạo:

~~~java
@Bean
@Profile("dev")
NoticeChannel firstChannel() {
    return () -> "first";
}

@Bean
@Profile("cloud")
NoticeChannel secondChannel() {
    return () -> "second";
}
~~~

Nếu cả `dev` và `cloud` hoạt động, việc tiêm `NoticeChannel` đơn lẻ có thể không xác định được ứng viên duy nhất. Cách sửa có thể dùng `@Qualifier` tại điểm tiêm:

~~~java
@Service
class NoticeFacade {
    private final NoticeChannel channel;

    NoticeFacade(@Qualifier("firstChannel") NoticeChannel channel) {
        this.channel = channel;
    }
}
~~~

Trong đoạn mã trên cần import `org.springframework.beans.factory.annotation.Qualifier`. Điều kiện profile vẫn quyết định `firstChannel` có tồn tại hay không; `@Qualifier` chỉ chọn bean trong số các bean đã được đăng ký.

Nếu `firstChannel` không có khi chạy prod, `@Qualifier` không tạo ra nó. Hãy cân nhắc kỹ trước khi dùng giải pháp này như một lựa chọn mặc định cho nhiều môi trường.

## 15. Kiểm thử bean theo profile

Một cách trực tiếp để kiểm thử cấu hình theo môi trường trong Spring Boot là sử dụng `@ActiveProfiles` cùng `@SpringBootTest`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("dev")
class NoticeProfileTest {

    @Autowired
    NoticeChannel channel;

    @Test
    void loadsDevChannel() {
        assertTrue(channel.describe().contains("dev"));
    }
}
~~~

`@ActiveProfiles("dev")` cung cấp profile cho context của lần kiểm thử, giúp các bean theo `@Profile("dev")` đủ điều kiện. Trong ví dụ trên, giả sử ứng dụng có cấu hình bean `dev` tương ứng và không có bean `NoticeChannel` thứ hai cũng phù hợp.

Có thể viết một lớp test khác với `@ActiveProfiles("prod")` để kiểm tra ngữ cảnh production.

Một thử nghiệm hữu ích hơn chỉ kiểm tra chuỗi là xác nhận **kiểu bean, số lượng bean và cấu hình được gắn**. Ví dụ trong test dev:

~~~java
@Autowired
ApplicationContext context;

@Test
void registersOnlyOneNoticeChannel() {
    assertEquals(1, context.getBeansOfType(NoticeChannel.class).size());
}
~~~

Cần import `org.springframework.context.ApplicationContext` và `org.junit.jupiter.api.Assertions.assertEquals`. Kiểm thử này xác nhận cấu hình không vô tình tạo hai bean cùng loại dưới profile đã chọn.

### Test profile và dữ liệu cấu hình test

Tệp `application-test.yaml` có thể cung cấp dữ liệu khi `test` hoạt động:

~~~yaml
app:
  notice:
    title: "Test notification"
    endpoint: "http://localhost:9999"
    retry-count: 0
~~~

Nhưng chỉ có file này trong `src/test/resources` chưa bảo đảm test dùng profile `test`; hãy kích hoạt bằng `@ActiveProfiles("test")` hoặc cách cấu hình tương đương phù hợp.

Đối với test cần bean chỉ có trong production, cần cân nhắc phụ thuộc bên ngoài. Không nên để một kiểm thử tích hợp vô tình kết nối đến dịch vụ production chỉ vì bật profile `prod`. Cơ chế mock hoặc nguồn cấu hình test vẫn cần được thiết kế rõ ràng.

## 16. Quan sát profile và nguồn cấu hình khi khởi động

Trong môi trường phát triển, có thể in **tên profile** để biết context đang chạy với nhóm nào:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileLogger implements ApplicationRunner {
    private final Environment environment;

    ProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Default profiles = "
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

Nếu `getActiveProfiles()` trả về mảng rỗng, điều đó **không có nghĩa** không có profile nào liên quan đến quá trình đánh giá điều kiện. Lúc ấy các profile mặc định có thể đang được dùng.

Để kiểm tra một điều kiện cụ thể, có thể dùng:

~~~java
import org.springframework.core.env.Profiles;

boolean prod = environment.acceptsProfiles(Profiles.of("prod"));
boolean nonProd = environment.acceptsProfiles(Profiles.of("!prod"));
~~~

Phương thức này phản ánh việc Spring đánh giá biểu thức profile. Nó không tự tạo bean; muốn biết bean nào đã được đăng ký, cần quan sát `ApplicationContext`.

Spring Boot cũng có **Condition Evaluation Report** phục vụ chẩn đoán tự cấu hình và điều kiện bean. Chạy với `--debug` hoặc dùng thông tin từ công cụ quan sát phù hợp để kiểm tra vì sao một điều kiện được áp dụng hoặc không được áp dụng. Tránh in toàn bộ thuộc tính có thể chứa bí mật.

Nếu dùng Spring Boot Actuator, endpoint `/actuator/conditions` có thể hỗ trợ tìm nguyên nhân điều kiện thỏa/không thỏa; `/actuator/env` có thể hỗ trợ xem nguồn thuộc tính. Các endpoint này cần được cấu hình và bảo vệ thích hợp vì chúng có thể tiết lộ chi tiết nội bộ.

## 17. Thay profile khi ứng dụng đang chạy có tự đổi bean không?

Thông thường **không**.

Khi Spring Boot khởi động, nó chuẩn bị `Environment`, xử lý Config Data, đánh giá điều kiện đăng ký và tạo `ApplicationContext`. `@Profile` được dùng trong quá trình thiết lập context.

Nếu người vận hành chỉnh `application-prod.yaml` trên ổ đĩa sau khi ứng dụng đã chạy, điều đó không làm Spring Boot tự nạp lại mọi giá trị. Tương tự, tự thay đổi tập profile active trên một `Environment` đang dùng **không tự loại bỏ hoặc tạo lại** những bean đã đăng ký theo `@Profile`.

Muốn chuyển từ triển khai dev sang prod một cách tin cậy, thông thường hãy **khởi động lại ứng dụng với tập profile phù hợp**. Hệ thống cần thay đổi cấu hình hoặc thành phần động trong lúc chạy đòi hỏi cơ chế làm mới và quản lý vòng đời riêng; `@Profile` đơn lẻ không cung cấp cơ chế đó.

## 18. Tình huống vận hành: profile prod nhưng giá trị từ biến môi trường

Giả sử cấu hình:

~~~yaml
# application.yaml
app:
  notice:
    endpoint: "https://fallback.invalid"
~~~

~~~yaml
# application-prod.yaml
app:
  notice:
    endpoint: "https://notify.internal"
~~~

Bean:

~~~java
@Bean
@Profile("prod")
NoticeChannel prodChannel(NoticeProperties properties) {
    return () -> properties.endpoint().toString();
}
~~~

Lệnh:

~~~bash
APP_NOTICE_ENDPOINT=https://gateway.example.com \
java -jar app.jar --spring.profiles.active=prod
~~~

Kết quả theo thứ tự nguồn mặc định của Spring Boot:

- `prod` là profile active, nên `prodChannel` được đăng ký.
- `application-prod.yaml` có thể được nạp nhờ profile `prod`.
- `APP_NOTICE_ENDPOINT` ghi đè thuộc tính `app.notice.endpoint` từ tệp, nên giá trị nhận qua `NoticeProperties` là `https://gateway.example.com`.

Nếu chỉ nhìn vào `application-prod.yaml`, bạn có thể kết luận sai rằng bean production phải sử dụng `https://notify.internal`. Thực tế profile và độ ưu tiên nguồn là **hai trục quyết định khác nhau**.

Khi chẩn đoán, hãy hỏi theo thứ tự:

1. Tập profile nào đang có hiệu lực?
2. Điều kiện `@Profile` của bean nào thỏa?
3. Những tệp cấu hình theo profile nào được nạp?
4. Giá trị thuộc tính cuối cùng đến từ nguồn ưu tiên nào?
5. Thành phần nhận giá trị vào thời điểm nào?

## 19. Những lỗi thường gặp khi dùng @Profile

### 19.1. Nghĩ tên profile tự sinh ra bean tương ứng

Kích hoạt `prod` không tự sinh ra một bean `ProductionService`. Bean chỉ xuất hiện nếu có định nghĩa thông qua component scan, `@Bean` hoặc cơ chế đăng ký khác và tất cả điều kiện liên quan được thỏa.

### 19.2. Cho rằng file YAML tạo bean

`application-prod.yaml` cung cấp **giá trị cấu hình** khi profile `prod` hoạt động. Nó không tự tạo một class Java hoặc bean chỉ vì có thuộc tính mô tả tên class.

### 19.3. Cho rằng chỉ một profile được bật

Spring hỗ trợ nhiều profile đồng thời. `@Profile("dev")` và `@Profile("cloud")` có thể cùng đúng. Điều này dễ gây nhiều bean cùng kiểu và lỗi tiêm phụ thuộc.

### 19.4. Gắn @Profile("default") như thể đó là “mọi môi trường ngoài prod”

`default` là một profile có ngữ nghĩa riêng khi không có active profile rõ ràng. `!prod` mới là điều kiện phủ định profile production.

### 19.5. Đặt spring.profiles.active trong application-prod.yaml

Trong hệ thống Config Data hiện đại, `spring.profiles.active` không được khai báo ở tài liệu cấu hình chỉ dành cho một profile. Hãy khai báo ở tài liệu chung hoặc nguồn cấu hình sớm thích hợp.

### 19.6. Dùng profile cho mọi cờ tính năng

Nếu chỉ muốn bật một tính năng ở cả dev và production tùy theo `app.feature.enabled`, điều kiện dựa vào thuộc tính có thể rõ hơn việc tạo thêm hàng loạt profile như `dev-feature-on` và `prod-feature-off`.

### 19.7. Nhầm @Profile với Spring Security role

Tên `prod`, `admin` hoặc `test` trong `@Profile` là **profile vận hành**, không phải vai trò người dùng trong cơ chế phân quyền. `@Profile("admin")` không kiểm tra danh tính hay quyền của người gửi HTTP request.

### 19.8. Mong profile đổi sau khi application đã khởi động

Bean được chọn khi tạo context. Đổi biến môi trường hoặc tệp cấu hình trên đĩa sau đó không tự đánh giá lại tất cả `@Profile`.

### 19.9. Để một cấu hình chỉ hoạt động ở test mà thiếu khi chạy thật

Nếu một bean thiết yếu chỉ có `@Profile("test")`, ứng dụng có thể chạy test thành công nhưng không khởi động được trong production vì thiếu bean. Hãy kiểm tra các biến thể khởi động mà ứng dụng cần hỗ trợ.

## 20. Bài thực hành: dự đoán bean và giá trị

### Bài 1 — chọn bean

~~~java
@Bean
@Profile("dev")
NoticeChannel dev() {
    return () -> "DEV";
}

@Bean
@Profile("prod")
NoticeChannel prod() {
    return () -> "PROD";
}
~~~

Hãy dự đoán số bean `NoticeChannel` trong bốn trường hợp:

| Active profiles | Số bean |
| --- | ---: |
| `dev` | 1 |
| `prod` | 1 |
| `dev,prod` | 2 |
| Không chỉ định (mặc định `default`) | 0 |

Giải thích: mỗi điều kiện được đánh giá độc lập. Không có quy tắc profile “đứng trước thắng” khi đăng ký bean.

### Bài 2 — sử dụng phủ định

Thay định nghĩa thứ nhất bằng:

~~~java
@Bean
@Profile("!prod")
NoticeChannel nonProd() {
    return () -> "NON_PROD";
}
~~~

Giữ định nghĩa thứ hai `@Profile("prod")`. Dự đoán:

- `dev` → bean `nonProd`.
- Không đặt profile active → bean `nonProd`.
- `prod` → bean `prod`.
- `dev,prod` → bean `prod` vì `!prod` không thỏa.

### Bài 3 — phân biệt bean và dữ liệu cấu hình

~~~yaml
# application.yaml
app:
  mode: base
~~~

~~~yaml
# application-dev.yaml
app:
  mode: dev-file
~~~

~~~yaml
# application-prod.yaml
app:
  mode: prod-file
~~~

Bean:

~~~java
@Bean
@Profile("prod")
ModeReporter modeReporter(Environment environment) {
    return new ModeReporter(environment.getProperty("app.mode"));
}
~~~

Giả sử `ModeReporter` là lớp nhận một chuỗi trong constructor.

Hỏi: Với `--spring.profiles.active=prod --app.mode=cli`, bean có tồn tại không và thuộc tính của nó có giá trị gì?

**Đáp án:** Bean tồn tại vì `prod` hoạt động; giá trị `app.mode` là `cli` do đối số CLI ưu tiên cao hơn tệp profile. Nếu chỉ thay `--spring.profiles.active=dev` và giữ cấu hình bean, `modeReporter` không được đăng ký.

### Bài 4 — biểu thức kết hợp

Điều kiện:

~~~java
@Profile("(prod & cloud) | staging")
~~~

Hãy xem nó đúng hay sai:

| Active profiles | Điều kiện |
| --- | --- |
| `prod` | Sai |
| `cloud` | Sai |
| `prod,cloud` | Đúng |
| `staging` | Đúng |
| `dev,staging` | Đúng |
| `prod,local` | Sai |

### Bài 5 — kiểm thử

Tạo hai test Spring Boot độc lập: một dùng `@ActiveProfiles("dev")`, một dùng `@ActiveProfiles("prod")`. Trong mỗi test, tiêm `ApplicationContext` và kiểm tra số lượng `NoticeChannel`. Sau đó thêm một test với cả `dev` và `prod` để quan sát lý do cần điều kiện loại trừ nhau hoặc cách chọn bean tường minh.

Thực hành này giúp phân biệt việc **tạo bean** với việc **lấy giá trị thuộc tính**.

## 21. Bảng chọn công cụ phù hợp

| Câu hỏi đang giải quyết | Cơ chế phù hợp |
| --- | --- |
| Chạy app với tập môi trường logic nào? | `spring.profiles.active` hoặc cấu hình active profile tương ứng. |
| Khi dev/prod hoạt động, tài liệu cấu hình nào được nạp? | `application-{profile}.yaml`, `spring.config.activate.on-profile` và Config Data. |
| Khi prod hoạt động, bean nào được đăng ký? | `@Profile("prod")` trên lớp hoặc `@Bean`. |
| Một thuộc tính có giá trị cuối là bao nhiêu? | `Environment`, `@ConfigurationProperties`, thứ tự `PropertySource`. |
| Bật/tắt một tính năng theo cờ độc lập với tên môi trường? | `@ConditionalOnProperty`. |
| Khi nhiều bean cùng kiểu tồn tại, chọn bean nào để tiêm? | `@Qualifier`, `@Primary` hoặc thiết kế điều kiện loại trừ nhau. |
| Muốn thay triển khai khi đang chạy mà không restart? | Cơ chế vòng đời/làm mới riêng; `@Profile` không tự làm việc này. |

## 22. Ghi nhớ

Profile là ngữ cảnh chung mà Spring Framework và Spring Boot sử dụng để chọn thành phần và nguồn cấu hình. **`@Profile` điều khiển việc đăng ký bean**. **Config Data điều khiển việc nạp các tài liệu cấu hình theo profile**. Cả hai dựa trên những profile đang có hiệu lực, nhưng một cơ chế không thay thế cơ chế còn lại.

Khi phân tích lỗi môi trường, hãy tách ba câu hỏi:

1. **Profile nào đang hoạt động?**
2. **Bean nào đủ điều kiện xuất hiện trong `ApplicationContext`?**
3. **Thuộc tính mà bean nhận được thực sự đến từ nguồn nào trong `Environment`?**

Trả lời được ba câu hỏi này giúp tránh những lỗi phổ biến: bean bị thiếu, nhiều bean cùng kiểu, và giá trị cấu hình không giống tệp YAML vừa đọc.

## Tài liệu tham khảo

- [Spring Framework — Bean Definition Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles).
- [Spring Framework — @Profile](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).