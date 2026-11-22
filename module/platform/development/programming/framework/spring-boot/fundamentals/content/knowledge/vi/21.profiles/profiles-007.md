# Profile group và cấu hình nhóm môi trường

Một ứng dụng Spring Boot thường cần nhiều bộ cấu hình để chạy ở máy cá nhân, môi trường kiểm thử tích hợp, staging và production. Chẳng hạn, local sử dụng database giả lập và ghi log ra console; staging sử dụng database dùng chung nhưng vẫn tắt việc gửi thông báo thật; production sử dụng database production, gửi thông báo thật và bật những thiết lập quan sát hệ thống.

Nếu mỗi môi trường chỉ tương ứng với một profile duy nhất, việc cấu hình có thể đơn giản. Nhưng khi các đặc tính môi trường bắt đầu kết hợp, bạn dễ gặp những danh sách dài như `production-db,production-mail,metrics,audit` trong lệnh chạy. Các danh sách này khó nhớ, dễ nhập thiếu và khó duy trì nhất quán giữa máy phát triển và hệ thống triển khai.

Spring Boot cung cấp **profile group** để gom nhiều profile thành viên dưới một tên dễ hiểu. Thay vì yêu cầu người triển khai nhớ toàn bộ profile thành phần, bạn khai báo một nhóm như `production`, rồi chỉ cần kích hoạt nhóm đó. Spring Boot sẽ mở rộng nhóm thành các profile thành viên để nạp cấu hình và xét các bean phụ thuộc profile.

Bài học thuộc chương **Profile** của **Spring Boot Fundamentals**. Chúng ta sẽ làm rõ cách khai báo `spring.profiles.group`, cách hoạt động khi ứng dụng khởi động, quy tắc về vị trí khai báo, thứ tự ưu tiên cấu hình, sự khác biệt với `spring.profiles.active` và `spring.profiles.include`, cùng một ví dụ thiết kế nhóm môi trường hoàn chỉnh.

## 1. Vấn đề: một môi trường thường gồm nhiều đặc tính

Hãy hình dung ứng dụng có ba chiều cấu hình độc lập:

- **Lưu trữ:** local database hoặc remote database.
- **Thông báo:** in ra console hoặc gửi bằng kênh production.
- **Quan sát:** bật audit/monitoring trong những môi trường cần theo dõi.

Nếu tự kết hợp profile bằng command line, bạn có thể phải chạy:

```bash
java -jar application.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

Vấn đề là tên profile dài và mang tính kỹ thuật. Một người triển khai chỉ cần nói “đây là production”, không nhất thiết phải nhớ mọi thành phần bên dưới.

Tương tự, staging có thể cần:

```bash
java -jar application.jar \
  --spring.profiles.active=remote-db,console-notify,observability
```

Hai môi trường dùng chung một số profile nhưng khác một số profile khác. Nếu sao chép các danh sách thủ công, việc bổ sung một đặc tính mới phải sửa nhiều nơi.

Profile group giải quyết việc này bằng cách ánh xạ:

```text
local
  ├── local-db
  └── console-notify

staging
  ├── remote-db
  ├── console-notify
  └── observability

production
  ├── remote-db
  ├── real-notify
  └── observability
```

Người vận hành chỉ cần kích hoạt `local`, `staging` hoặc `production`. Cấu hình nhóm tập trung mô tả mỗi môi trường gồm những thành phần nào.

## 2. Profile group là gì?

Profile group là một tính năng cấu hình của Spring Boot, được khai báo qua nhóm property:

```text
spring.profiles.group.<ten-nhom>
```

Trong đó:

- `spring.profiles.group` là prefix do Spring Boot hiểu.
- `<ten-nhom>` là tên profile nhóm, ví dụ `production`.
- Giá trị là danh sách những profile được kích hoạt khi profile nhóm được kích hoạt.

Ví dụ YAML:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - observability
```

Khi khởi động với:

```bash
java -jar application.jar --spring.profiles.active=production
```

Spring Boot kích hoạt profile `production` và những profile thành viên được khai báo trong nhóm.

Có thể hình dung:

```text
Kích hoạt profile "production"
                │
                ▼
Đọc spring.profiles.group.production
                │
                ▼
       ┌────────┼─────────┐
       ▼        ▼         ▼
  remote-db  real-notify  observability
       │        │         │
       └────────┼─────────┘
                ▼
     Nạp cấu hình theo profile
     Xét điều kiện @Profile
     Tạo bean definitions phù hợp
```

**Profile group không phải một ApplicationContext mới.** Nó là quy tắc giúp mở rộng tập profile active trong cùng quy trình khởi động ứng dụng.

### 2.1. Profile nhóm cũng là một profile

Nếu `production` được kích hoạt, tên `production` vẫn là profile active. Vì thế bạn có thể có cả:

```text
application-production.yml
application-remote-db.yml
application-real-notify.yml
application-observability.yml
```

và các thành phần Java:

```java
@Profile("production")
```

```java
@Profile("remote-db")
```

Tuy nhiên, mỗi annotation có phạm vi ý nghĩa khác nhau:

- `@Profile("production")` mô tả bean chỉ dành cho cả môi trường production.
- `@Profile("remote-db")` mô tả bean dùng khi đặc tính remote database được kích hoạt, dù đó là staging hay production.

Đây là lợi ích chính của group: tách **tên môi trường tổng thể** khỏi **các đặc tính có thể tái sử dụng**.

### 2.2. Có phải một profile group chứa các file hay thư mục?

Không. Profile group không khai báo đường dẫn đến file hoặc thư mục. Nó chỉ chứa **tên profile**.

Khi một profile thành viên được kích hoạt, Spring Boot có thể nạp file `application-<profile>.yml` hoặc các document có `spring.config.activate.on-profile` phù hợp, tùy những nguồn Config Data hiện có.

Nếu một profile thành viên không có file cấu hình riêng, nó vẫn có thể có ý nghĩa đối với `@Profile` trên class hoặc method.

## 3. Cú pháp YAML của spring.profiles.group

Cú pháp phổ biến nhất là một map từ tên nhóm đến danh sách thành viên:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
      staging:
        - remote-db
        - console-notify
        - observability
      production:
        - remote-db
        - real-notify
        - observability
```

Với cấu hình này:

| Profile kích hoạt | Các profile thành viên được kích hoạt |
|---|---|
| `local` | `local-db`, `console-notify` |
| `staging` | `remote-db`, `console-notify`, `observability` |
| `production` | `remote-db`, `real-notify`, `observability` |

Bạn không cần tự kích hoạt từng thành viên trong lệnh chạy.

### 3.1. Có thể dùng cú pháp danh sách trên một dòng

Trong YAML, dạng sau tương đương về ý tưởng:

```yaml
spring:
  profiles:
    group:
      production: [remote-db, real-notify, observability]
```

Dạng nhiều dòng dễ review hơn khi nhóm có nhiều thành viên. Dạng inline gọn khi nhóm rất ngắn.

### 3.2. Đừng đặt nhầm thành spring.profiles.active

Cấu hình:

```yaml
spring:
  profiles:
    active: production
```

có nghĩa là **chọn** profile `production` để kích hoạt.

Cấu hình:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

có nghĩa là **định nghĩa** nhóm `production` gồm những thành viên nào.

Định nghĩa nhóm không tự động kích hoạt nó. Bạn vẫn phải chọn một active profile phù hợp bằng command line, environment variable, cấu hình khởi động hoặc cơ chế tương ứng.

### 3.3. Cấu hình properties thay cho YAML

Spring Boot cũng hỗ trợ `application.properties`:

```properties
spring.profiles.group.local[0]=local-db
spring.profiles.group.local[1]=console-notify

spring.profiles.group.staging[0]=remote-db
spring.profiles.group.staging[1]=console-notify
spring.profiles.group.staging[2]=observability

spring.profiles.group.production[0]=remote-db
spring.profiles.group.production[1]=real-notify
spring.profiles.group.production[2]=observability
```

Các chỉ số `[0]`, `[1]`, `[2]` biểu diễn phần tử của danh sách.

Cú pháp indexed giúp danh sách hiện rõ trong file properties và tránh nhầm cách Spring Boot bind collection.

## 4. Phiên bản Spring Boot nào hỗ trợ profile group?

Profile groups được giới thiệu cùng cơ chế Config Data mới của **Spring Boot 2.4**.

Vì vậy, cần phân biệt:

- Với Spring Boot 2.3 trở về trước, không nên giả định `spring.profiles.group` được hỗ trợ.
- Với Spring Boot 2.4 và các dòng mới hơn, có thể dùng profile groups theo cơ chế cấu hình tương ứng.
- Khi nâng cấp một ứng dụng rất cũ, cần xem cả thay đổi liên quan `spring.config.activate.on-profile` và quy tắc đọc profile-specific documents.

Ví dụ, một ứng dụng Boot 2.3 từng dùng các quy tắc profile trong YAML đa document có thể phải điều chỉnh khi chuyển sang Boot 2.4+. Đừng chỉ thêm `spring.profiles.group` rồi kỳ vọng toàn bộ cấu hình cũ hoạt động y hệt.

Khi làm việc trong một dự án, hãy kiểm tra **phiên bản Spring Boot thực tế đang chạy** thay vì mặc định áp dụng cú pháp của một bài viết không ghi version.

## 5. Thiết kế cấu hình theo nhóm môi trường

Một cấu trúc đơn giản, dễ hiểu:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
├── application-production.yml
├── application-local-db.yml
├── application-remote-db.yml
├── application-console-notify.yml
├── application-real-notify.yml
└── application-observability.yml
```

Vai trò từng file:

| File | Trách nhiệm |
|---|---|
| `application.yml` | Cấu hình chung và định nghĩa profile groups |
| `application-local.yml` | Những giá trị chỉ thuộc môi trường local |
| `application-staging.yml` | Những giá trị chỉ thuộc môi trường staging |
| `application-production.yml` | Những giá trị chỉ thuộc môi trường production |
| `application-local-db.yml` | Giá trị áp dụng cho chế độ database local |
| `application-remote-db.yml` | Giá trị dùng chung cho các môi trường dùng remote DB |
| `application-console-notify.yml` | Cấu hình thông báo console |
| `application-real-notify.yml` | Cấu hình kênh thông báo thật |
| `application-observability.yml` | Cấu hình quan sát dùng chung |

Đây là cách tổ chức minh họa. Không phải mọi project đều cần tách nhiều file như vậy. Nếu cấu hình chỉ có vài key, một `application.yml` với nhiều document có thể dễ duy trì hơn.

### 5.1. application.yml: định nghĩa nhóm

```yaml
spring:
  application:
    name: profile-group-demo
  profiles:
    group:
      local:
        - local-db
        - console-notify
      staging:
        - remote-db
        - console-notify
        - observability
      production:
        - remote-db
        - real-notify
        - observability

app:
  greeting: "Xin chào từ cấu hình chung"
  http-client:
    timeout: 5s
```

File này **chưa yêu cầu** ứng dụng phải chạy local, staging hoặc production. Nó chỉ mô tả các nhóm.

Một người triển khai có thể chọn:

```bash
java -jar application.jar --spring.profiles.active=staging
```

Sau đó Boot nạp các Config Data áp dụng cho `staging` và những thành viên group liên quan.

### 5.2. application-local.yml: giá trị riêng local

```yaml
app:
  environment-name: local
  http-client:
    timeout: 2s
  demo-data:
    enabled: true
```

### 5.3. application-staging.yml: giá trị riêng staging

```yaml
app:
  environment-name: staging
  http-client:
    timeout: 4s
  demo-data:
    enabled: false
```

### 5.4. application-production.yml: giá trị riêng production

```yaml
app:
  environment-name: production
  http-client:
    timeout: 10s
  demo-data:
    enabled: false
```

### 5.5. application-local-db.yml: cấu hình thành phần

```yaml
app:
  storage:
    mode: in-memory
```

### 5.6. application-remote-db.yml: tái sử dụng giữa staging và production

```yaml
app:
  storage:
    mode: remote
    endpoint: "https://storage.example.test"
```

Trong project thực tế, endpoint remote cần lấy từ hệ thống cấu hình/secret phù hợp, không hard-code host production hoặc credentials trong repository.

### 5.7. application-console-notify.yml

```yaml
app:
  notification:
    channel: console
```

### 5.8. application-real-notify.yml

```yaml
app:
  notification:
    channel: external
```

### 5.9. application-observability.yml

```yaml
app:
  observability:
    audit-enabled: true
```

Nếu profile `observability` được kích hoạt trong staging hoặc production, các giá trị của file này có thể được nạp.

Như vậy, nhóm `staging` và `production` cùng dùng các thành phần `remote-db` và `observability`, nhưng chọn kênh thông báo khác nhau.

## 6. Kích hoạt một group bằng command-line argument

Giả sử JAR đã đóng gói các file cấu hình ở trên.

Chạy local:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=local
```

Chạy staging:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=staging
```

Chạy production:

```bash
java -jar profile-group-demo.jar --spring.profiles.active=production
```

Từ góc độ vận hành, các lệnh đơn giản hơn rất nhiều so với việc liệt kê thủ công `remote-db,real-notify,observability`.

### 6.1. Ưu điểm của việc kích hoạt một tên nhóm

- Người vận hành nhớ tên **môi trường**, không nhớ mọi chi tiết triển khai.
- Danh sách profile thành viên nằm trong cấu hình có thể review và version control.
- Khi thêm một thành phần mới, sửa định nghĩa group thay vì sửa mọi script/deployment.
- Có thể tái sử dụng cùng profile thành viên giữa các nhóm.
- Vẫn giữ `@Profile` và file theo profile làm cơ chế chuẩn để bật bean hoặc cấu hình.

### 6.2. Nhóm không loại bỏ quyền ghi đè cấu hình

Ví dụ production dùng timeout mặc định `10s` nhưng một deployment muốn `15s`:

```bash
java -jar profile-group-demo.jar \
  --spring.profiles.active=production \
  --app.http-client.timeout=15s
```

Property command line có thể ghi đè giá trị đến từ Config Data theo precedence thông thường.

Profile group quyết định **những profile nào active**. Nó không khóa cứng giá trị của mọi property và không cấm các nguồn ưu tiên cao hơn ghi đè cấu hình.

## 7. Kích hoạt group bằng biến môi trường

Trong container hoặc hệ thống CI/CD, thường dùng biến:

```text
SPRING_PROFILES_ACTIVE=production
```

Ví dụ trên shell hỗ trợ gán biến tạm:

```bash
SPRING_PROFILES_ACTIVE=production java -jar profile-group-demo.jar
```

Hoặc trong Docker Compose:

```yaml
services:
  app:
    image: example/profile-group-demo:latest
    environment:
      SPRING_PROFILES_ACTIVE: production
      APP_STORAGE_ENDPOINT: "https://storage.example.test"
```

Ở đây, ứng dụng nhận tên nhóm `production` thông qua biến môi trường. Các thành viên nhóm được Boot mở rộng trong quá trình chuẩn bị Config Data.

Lưu ý: `APP_STORAGE_ENDPOINT` chỉ ghi đè property `app.storage.endpoint` nếu project dùng tên và binding phù hợp. Nó không tự sửa profile group.

### 7.1. Cách đặt biến trong PowerShell

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar profile-group-demo.jar
```

Trên Bash hoặc shell tương tự:

```bash
export SPRING_PROFILES_ACTIVE=staging
java -jar profile-group-demo.jar
```

Cú pháp shell khác nhau, còn property mà Spring Boot đọc vẫn là `spring.profiles.active`.

## 8. Các profile thành viên ảnh hưởng tới @Profile thế nào?

Profile group không chỉ ảnh hưởng file YAML. Các profile thành viên cũng được dùng khi Spring xét annotation `@Profile`.

Ví dụ một interface:

```java
package com.example.demo.notification;

public interface MessageSink {
    void send(String message);
}
```

Implementation console:

```java
package com.example.demo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("console-notify")
public class ConsoleMessageSink implements MessageSink {

    @Override
    public void send(String message) {
        System.out.println("[CONSOLE] " + message);
    }
}
```

Implementation external:

```java
package com.example.demo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("real-notify")
public class ExternalMessageSink implements MessageSink {

    @Override
    public void send(String message) {
        System.out.println("[EXTERNAL-DEMO] " + message);
    }
}
```

Class `ExternalMessageSink` trong ví dụ **chỉ mô phỏng kênh external bằng log**, không thực sự gửi email/SMS.

Service sử dụng:

```java
package com.example.demo.notification;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSink sink;

    public NotificationService(MessageSink sink) {
        this.sink = sink;
    }

    public void notifyStarted() {
        sink.send("Ứng dụng đã khởi động");
    }
}
```

Khi kích hoạt:

- `local` → `console-notify` → đăng ký `ConsoleMessageSink`.
- `staging` → `console-notify` → đăng ký `ConsoleMessageSink`.
- `production` → `real-notify` → đăng ký `ExternalMessageSink`.

Dù người vận hành chỉ chọn `staging` hoặc `production`, các bean vẫn được quyết định dựa trên những profile thành viên.

### 8.1. Nếu cả hai profile đối nghịch cùng active

Giả sử bạn chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=staging,production
```

Hai nhóm này có thể cùng kích hoạt `console-notify` và `real-notify`. Khi đó cả hai bean `MessageSink` có thể được đăng ký, dẫn đến lỗi injection một bean duy nhất nếu không có `@Primary`, `@Qualifier` hoặc cách xử lý thích hợp.

**Profile group không tạo cơ chế loại trừ lẫn nhau**. Nó chỉ kích hoạt thêm profile. Nếu hai nhóm không được phép chạy đồng thời, cần có chính sách kiểm tra cấu hình để phát hiện tổ hợp không hợp lệ.

### 8.2. @Profile trên nhóm hay trên thành viên?

Dùng:

```java
@Profile("production")
```

khi bean chỉ có ý nghĩa trong môi trường production.

Dùng:

```java
@Profile("remote-db")
```

khi bean dùng chung cho mọi môi trường đã kích hoạt `remote-db`.

Không cần mọi class đều phải dùng `@Profile("production")`. Nếu một hạ tầng thực sự dùng chung giữa staging và production, đánh dấu theo profile chức năng giúp tái sử dụng tốt hơn.

## 9. Ví dụ runnable: nhóm local và production

Một ví dụ tối thiểu chỉ cần `spring-boot-starter`, không cần web server. Giả sử project sử dụng Spring Boot hiện đại và Java tương thích.

### 9.1. Cấu trúc file

```text
src/main/
├── java/com/example/profilegroup/
│   ├── ProfileGroupApplication.java
│   ├── NotificationService.java
│   ├── MessageSink.java
│   ├── ConsoleMessageSink.java
│   ├── ProductionMessageSink.java
│   └── ProfilePrinter.java
└── resources/
    ├── application.yml
    ├── application-local.yml
    ├── application-production.yml
    ├── application-console-notify.yml
    └── application-real-notify.yml
```

### 9.2. application.yml

```yaml
spring:
  application:
    name: profile-group-demo
  profiles:
    group:
      local:
        - console-notify
      production:
        - real-notify

app:
  notification:
    greeting: "Hello"
```

### 9.3. application-local.yml

```yaml
app:
  notification:
    greeting: "Xin chào từ local"
```

### 9.4. application-production.yml

```yaml
app:
  notification:
    greeting: "Xin chào từ production"
```

### 9.5. Interface và hai implementations

```java
package com.example.profilegroup;

public interface MessageSink {
    void send(String text);
}
```

```java
package com.example.profilegroup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("console-notify")
public class ConsoleMessageSink implements MessageSink {

    @Override
    public void send(String text) {
        System.out.println("[CONSOLE] " + text);
    }
}
```

```java
package com.example.profilegroup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("real-notify")
public class ProductionMessageSink implements MessageSink {

    @Override
    public void send(String text) {
        System.out.println("[PRODUCTION-DEMO] " + text);
    }
}
```

### 9.6. Service sử dụng cấu hình đã bind

```java
package com.example.profilegroup;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSink sink;
    private final String greeting;

    public NotificationService(
            MessageSink sink,
            @Value("${app.notification.greeting}") String greeting
    ) {
        this.sink = sink;
        this.greeting = greeting;
    }

    public void notifyStarted() {
        sink.send(greeting);
    }
}
```

### 9.7. Runner in active profiles

```java
package com.example.profilegroup;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfilePrinter implements CommandLineRunner {

    private final Environment environment;
    private final NotificationService notificationService;

    public ProfilePrinter(
            Environment environment,
            NotificationService notificationService
    ) {
        this.environment = environment;
        this.notificationService = notificationService;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(
                                environment.getActiveProfiles()
                        )
        );

        notificationService.notifyStarted();
    }
}
```

### 9.8. Main application

```java
package com.example.profilegroup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileGroupApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileGroupApplication.class, args);
    }
}
```

### 9.9. Chạy local

```bash
java -jar profile-group-demo.jar --spring.profiles.active=local
```

Log từ runner có thể có nội dung tương tự:

```text
Active profiles: [local, console-notify]
[CONSOLE] Xin chào từ local
```

### 9.10. Chạy production

```bash
java -jar profile-group-demo.jar --spring.profiles.active=production
```

Log minh họa:

```text
Active profiles: [production, real-notify]
[PRODUCTION-DEMO] Xin chào từ production
```

Danh sách và thứ tự hiển thị active profiles phụ thuộc việc có profile bổ sung từ nguồn khác hay không. Đây là kết quả dự kiến của ví dụ chỉ có một nhóm được kích hoạt.

### 9.11. Chạy không có profile thì sao?

Nếu không khai báo `spring.profiles.active`, nhóm `local` hoặc `production` **không tự động được kích hoạt chỉ vì chúng tồn tại**.

Với ví dụ trên, không có profile thành viên `console-notify` hoặc `real-notify`, nên không có bean `MessageSink`. `NotificationService` có constructor bắt buộc nhận `MessageSink`, do đó context có thể không khởi động.

Đây là ví dụ có chủ đích để thấy rằng **group là khai báo ánh xạ, không phải lệnh active mặc định**.

Nếu ứng dụng cần chạy local khi không có cấu hình ngoài, bạn phải thiết kế một mặc định rõ ràng: chẳng hạn kích hoạt profile khi chạy từ IDE hoặc cấu hình nhóm/default phù hợp ở bootstrap. Tránh ngầm giả định rằng tên `local` tự trở thành profile mặc định.

## 10. Quy tắc rất quan trọng: group chỉ khai báo ở document không đặc thù profile

Spring Boot có giới hạn cần nhớ:

**`spring.profiles.group` chỉ được sử dụng trong những document cấu hình không phải profile-specific.**

Nói cách khác, đặt group trong tài liệu cấu hình gốc như `application.yml` là phù hợp; đặt group trong `application-production.yml` hoặc một document được kích hoạt bằng `spring.config.activate.on-profile` là không hợp lệ theo quy tắc Config Data.

### 10.1. Đúng: định nghĩa group trong application.yml

```yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

### 10.2. Sai: định nghĩa group trong application-production.yml

```yaml
# application-production.yml — KHÔNG HỢP LỆ
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

Lý do: `application-production.yml` là profile-specific file. Việc dùng nó để định nghĩa thêm quan hệ active profile có thể tạo vòng phụ thuộc trong quá trình chọn document: trước tiên cần biết profile nào active để nạp file, nhưng lại cần nạp file để biết profile nào active.

Spring Boot ngăn kiểu cấu hình mơ hồ này bằng cách giới hạn vị trí khai báo các property ảnh hưởng việc kích hoạt profile.

### 10.3. Sai: đặt group trong document có on-profile

```yaml
# application.yml
app:
  name: demo
---
spring:
  config:
    activate:
      on-profile: production
  profiles:
    group:
      production:
        - real-notify
```

Document thứ hai được kích hoạt theo profile, nên không được dùng để khai báo `spring.profiles.group`.

### 10.4. Đúng: group ở document gốc, giá trị riêng ở document được kích hoạt

```yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify

app:
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: production

app:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: real-notify

app:
  notification:
    mode: external
```

Ở đây chỉ document đầu định nghĩa group. Các document sau đóng góp giá trị ứng dụng theo profile đã active.

### 10.5. Nếu vi phạm thì sao?

Spring Boot có thể báo lỗi cấu hình trong quá trình xử lý Config Data, chẳng hạn lỗi thuộc nhóm `InvalidConfigDataPropertyException` với nội dung property không được phép trong profile-specific resource/document.

Khi thấy lỗi liên quan `spring.profiles.group` trong profile-specific configuration, hãy chuyển phần định nghĩa group lên document không đặc thù profile. Đừng giải quyết bằng cách tắt validation hoặc đổi tên property để lách quy tắc.

## 11. spring.profiles.active, spring.profiles.include và spring.profiles.group

Ba cơ chế này có mục đích khác nhau.

| Cơ chế | Câu hỏi mà nó trả lời |
|---|---|
| `spring.profiles.active` | Profile nào được chọn kích hoạt? |
| `spring.profiles.include` | Những profile nào cần được bổ sung, ngoài tập profile được chọn? |
| `spring.profiles.group` | Nếu một tên profile được kích hoạt, nó đại diện thêm cho những profile nào? |

### 11.1. active: chọn trực tiếp

```yaml
spring:
  profiles:
    active: production
```

Cấu hình này chọn `production` làm profile active. Nếu có định nghĩa group cho tên đó, các thành viên sẽ được mở rộng.

Trong triển khai thực tế, thường để môi trường chạy lựa chọn active profiles qua biến môi trường hoặc command line thay vì hard-code `production` trong JAR chung.

### 11.2. include: thêm profile vào tập active

Ví dụ:

```yaml
spring:
  profiles:
    include:
      - observability
```

Mục đích là bổ sung `observability`, không phải định nghĩa một group có tên mới.

Khi chỉ muốn tạo một tên đại diện cho toàn bộ cấu hình production, dùng `group` rõ nghĩa hơn. Khi muốn thêm profile vào tập active mà không phụ thuộc profile môi trường nào được chọn, `include` có thể phù hợp.

### 11.3. group: định nghĩa quan hệ thành viên

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - observability
```

Chỉ khi profile `production` được active, các profile thành viên mới được kích hoạt theo quan hệ group.

### 11.4. active/include/group không được đặt trong profile-specific documents

Giống `spring.profiles.group`, hai property `spring.profiles.active` và `spring.profiles.include` cũng có hạn chế vị trí khai báo trong cơ chế Config Data của Spring Boot hiện đại.

Không khai báo chúng trong:

- `application-production.yml`.
- Document YAML có `spring.config.activate.on-profile`.
- Những profile-specific documents khác.

Đây là quy tắc quan trọng khi di chuyển từ cách cấu hình YAML cũ sang Spring Boot 2.4+.

### 11.5. Khi nào ưu tiên group thay include?

Nếu ý định là:

> “Mỗi lần bật production, cần tự động bật remote-db, real-notify và observability.”

thì dùng `spring.profiles.group.production`.

Nếu ý định là:

> “Bất kể đang chạy local hay production, ứng dụng này luôn cần thêm profile observability.”

thì `spring.profiles.include` có thể diễn đạt phù hợp hơn, với điều kiện được khai báo ở vị trí hợp lệ.

Không dùng một danh sách `include` khổng lồ để mô phỏng nhiều nhóm môi trường khác nhau.

## 12. Group và profile-specific configuration được xử lý khi nào?

Profile groups được giải quyết trong giai đoạn Spring Boot chuẩn bị Config Data và xác định active profiles, **trước khi phần lớn application beans được tạo**.

Luồng khái niệm:

```text
SpringApplication.run(...)
             │
             ▼
Chuẩn bị Environment và các nguồn Config Data
             │
             ▼
Đọc định nghĩa spring.profiles.group ở
non-profile-specific documents
             │
             ▼
Xác định spring.profiles.active
             │
             ▼
Mở rộng group thành các profile thành viên
             │
             ▼
Nạp profile-specific Config Data phù hợp
             │
             ▼
Đánh giá @Profile và điều kiện cấu hình
             │
             ▼
Đăng ký bean definitions
             │
             ▼
Tạo và inject bean
             │
             ▼
Ứng dụng sẵn sàng
```

Đây là mô hình học tập ở mức khái niệm. Spring Boot có thể cần nhiều lượt xử lý Config Data để xác định chính xác nguồn và profile có hiệu lực; không nên xem sơ đồ là mô tả từng method nội bộ.

Điểm thực tế: **định nghĩa group phải có ở giai đoạn Boot xác định tập profile active**, chứ không phải sau khi context đã khởi tạo.

### 12.1. Không thể dùng group như feature flag runtime

Nếu ứng dụng đã khởi động với `local`, sau đó một service gọi:

```java
environment.setActiveProfiles("production");
```

trên một `ConfigurableEnvironment` đã tồn tại, Spring Boot không tự chạy lại toàn bộ Config Data bootstrap để nạp lại mọi `application-production.yml`, đánh giá lại `@Profile` và thay tất cả bean local bằng bean production.

Đây không phải cách chuyển môi trường khi ứng dụng đang phục vụ request. Muốn đổi môi trường, thường cần restart với tập active profiles mới hoặc một hệ thống refresh/reconfiguration được thiết kế riêng.

### 12.2. Không đặt tên group bằng một property runtime tùy ý

`spring.profiles.group` là một phần của cấu hình bootstrap. Đừng dùng một service nghiệp vụ hoặc scheduler chạy sau startup để tự xây dựng group rồi kỳ vọng Spring nạp lại các profile-specific documents.

## 13. Thứ tự profile và precedence của cấu hình

Một nhóm có thể kích hoạt nhiều profile; đôi khi các file tương ứng cùng khai báo một key.

Ví dụ:

```yaml
# application.yml
spring:
  profiles:
    group:
      staging:
        - remote-db
        - observability

app:
  greeting: "base"
```

```yaml
# application-staging.yml
app:
  greeting: "staging"
```

```yaml
# application-remote-db.yml
app:
  greeting: "remote-db"
```

```yaml
# application-observability.yml
app:
  greeting: "observability"
```

Đây là một cách tổ chức **khó hiểu** vì property `app.greeting` bị lặp ở nhiều profile khác nhau. Giá trị cuối phụ thuộc vào thứ tự áp dụng Config Data và mức ưu tiên của các nguồn được nạp.

Spring Boot có quy tắc precedence cho profile-specific configuration, trong đó khi nhiều profile active, profile được xử lý sau có thể ghi đè giá trị từ profile trước ở cùng mức cấu hình tương ứng. Tuy nhiên, toàn bộ kết quả còn chịu ảnh hưởng bởi các location, imports, external configuration, command-line và environment variables.

Do đó, **đừng thiết kế profile group dựa vào một thứ tự ghi đè ngầm định giữa các thành viên** nếu có thể tránh được.

### 13.1. Thiết kế tốt: mỗi thành viên phụ trách một mảng

Ví dụ:

```yaml
# application-remote-db.yml
app:
  storage:
    mode: remote
```

```yaml
# application-observability.yml
app:
  observability:
    enabled: true
```

```yaml
# application-staging.yml
app:
  environment-name: staging
```

Mỗi file sở hữu các key riêng theo trách nhiệm. Khi đó thứ tự ghi đè ít ảnh hưởng kết quả, dễ hiểu và dễ kiểm thử hơn.

### 13.2. Ghi đè có chủ đích ở mức môi trường

Nếu một key thực sự cần khác nhau giữa staging và production, hãy đặt nó ở profile môi trường tương ứng:

```yaml
# application-staging.yml
app:
  http-client:
    timeout: 3s
```

```yaml
# application-production.yml
app:
  http-client:
    timeout: 10s
```

Tránh để cả `remote-db` và `observability` cũng định nghĩa `app.http-client.timeout` mà không có lý do rõ ràng.

### 13.3. Nguồn có ưu tiên cao hơn vẫn có thể thắng

Ngay cả khi các file profile đã nạp đúng, một environment variable hoặc command-line argument có thể ghi đè property:

```bash
java -jar app.jar \
  --spring.profiles.active=production \
  --app.http-client.timeout=20s
```

Đây là hành vi externalized configuration thông thường, không phải lỗi profile group.

## 14. Tên group, tên profile thành viên và quy ước đặt tên

Một quy ước tốt tách hai tầng:

- **Tên môi trường:** `local`, `test`, `staging`, `production`.
- **Tên đặc tính:** `local-db`, `remote-db`, `console-notify`, `real-notify`, `observability`.

Tên môi trường trả lời câu hỏi “ứng dụng chạy ở đâu?”. Tên đặc tính trả lời “môi trường này bật những khả năng nào?”.

### 14.1. Tránh tên mơ hồ

Nhóm như:

```yaml
spring:
  profiles:
    group:
      prod:
        - a
        - b
        - x
```

khó hiểu vì người đọc không biết `a`, `b` và `x` đại diện gì.

Nên dùng:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
        - audit
```

Tên rõ ràng giúp người triển khai và người review hiểu mục đích mà không phải tra nhiều tài liệu.

### 14.2. Tránh nhóm quá sâu hoặc có vòng tham chiếu

Để cấu hình dễ quản lý, nên tránh xây một mạng phức tạp gồm nhiều group lồng nhau, đặc biệt các quan hệ có thể thành vòng như `a -> b -> a`.

Một định nghĩa đơn giản, trực tiếp thường dễ dự đoán hơn:

```text
production
  ├── remote-db
  ├── real-notify
  └── observability
```

Nếu tổ chức muốn tái sử dụng group trong group, hãy kiểm tra hành vi cụ thể của phiên bản Boot và giữ quan hệ không có vòng, nhưng đừng mặc định biến nhóm profile thành một hệ dependency graph phức tạp.

### 14.3. Tên thành viên nên mô tả mối quan tâm cấu hình

Các tên kiểu `development`, `production` hợp lý cho môi trường. Các tên như `postgres`, `mock-payment`, `audit` có thể hợp lý cho tính năng.

Tuy nhiên, tránh đưa thông tin bí mật như hostname nội bộ, username hoặc mã môi trường nhạy cảm vào tên profile. Tên profile thường xuất hiện trong log startup.

## 15. Tổ chức theo orthogonal profiles

**Orthogonal profiles** là cách chia cấu hình thành các chiều tương đối độc lập. Ví dụ:

```text
Chiều lưu trữ
  local-db / remote-db

Chiều thông báo
  console-notify / real-notify

Chiều observability
  observability / no-observability
```

Mỗi nhóm môi trường chọn một lựa chọn phù hợp từ từng chiều:

| Môi trường | Lưu trữ | Thông báo | Observability |
|---|---|---|---|
| local | local-db | console-notify | Mặc định tối thiểu |
| staging | remote-db | console-notify | observability |
| production | remote-db | real-notify | observability |

Lợi ích:

- Có thể tái sử dụng profile chức năng.
- Cấu hình được chia theo trách nhiệm.
- Thay đổi một thành phần dùng chung không cần sao chép vào nhiều file.
- Test có thể kích hoạt riêng một profile thành viên khi cần kiểm thử.

### 15.1. Không chia nhỏ quá mức

Nếu một ứng dụng nhỏ chỉ có hai môi trường và mỗi môi trường khác vài property, tạo mười hai profile chức năng có thể khiến dự án phức tạp hơn.

Dùng profile group khi nó thực sự giảm sự lặp lại và làm các tổ hợp môi trường dễ hiểu hơn. Không cần biến mọi property boolean thành một profile riêng.

### 15.2. Khi nào nên dùng @ConditionalOnProperty thay @Profile?

`@Profile` hợp lý khi một bean/configuration gắn với **môi trường hoặc đặc tính cấp môi trường**.

`@ConditionalOnProperty` hợp lý khi cần bật/tắt một tính năng bằng một property rõ ràng:

```java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
```

Có thể dùng profile group để nạp file `application-observability.yml` chứa `app.audit.enabled=true`, rồi dùng `@ConditionalOnProperty` theo giá trị đó.

Như vậy group chọn tổ hợp cấu hình; property condition quyết định một feature theo cấu hình hiệu lực. Không nhất thiết mọi feature flag đều phải tạo thêm profile.

## 16. Kết hợp profile group và multi-document YAML

Nếu không muốn nhiều file, Spring Boot hỗ trợ nhiều document trong một file YAML, phân cách bằng `---`.

Ví dụ:

```yaml
# Document 1: cấu hình chung, không phụ thuộc profile
spring:
  profiles:
    group:
      local:
        - console-notify
      production:
        - real-notify
        - observability

app:
  greeting: "Hello"

---
# Document 2: chỉ khi local active
spring:
  config:
    activate:
      on-profile: local

app:
  greeting: "Hello local"

---
# Document 3: chỉ khi production active
spring:
  config:
    activate:
      on-profile: production

app:
  greeting: "Hello production"

---
# Document 4: khi observability active
spring:
  config:
    activate:
      on-profile: observability

app:
  audit:
    enabled: true
```

Đây là cách hợp lệ vì `spring.profiles.group` nằm ở document đầu không có `on-profile`. Các document còn lại chỉ chứa cấu hình được kích hoạt theo profile.

### 16.1. on-profile không định nghĩa thêm profile active

`spring.config.activate.on-profile` là điều kiện để **áp dụng document** hiện tại:

```yaml
spring:
  config:
    activate:
      on-profile: production
```

Nó không có nghĩa “hãy kích hoạt production”. Profile `production` phải đã active qua cơ chế khác.

### 16.2. Khác với cú pháp legacy

Trong các ví dụ Spring Boot rất cũ, bạn có thể thấy cách gắn profile cho YAML document bằng:

```yaml
spring:
  profiles: production
```

Cú pháp này không nên sao chép vào cách tổ chức Config Data của Spring Boot hiện đại. Với document phụ thuộc profile, dùng `spring.config.activate.on-profile`.

Quan trọng: không dùng `spring.profiles.group` bên trong document có `on-profile`.

## 17. Profile group và default profile

Khi không có active profile tường minh, Spring Framework có khái niệm default profiles, thường mặc định là `default`.

Bạn có thể xem:

```java
String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
```

Đây là hai khái niệm riêng:

- `getActiveProfiles()`: những profile active hiện tại.
- `getDefaultProfiles()`: những profile mặc định dùng khi không có active profile phù hợp.

### 17.1. Group không được chọn làm mặc định chỉ vì được khai báo

Ví dụ:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
```

Không có dòng nào ở đây yêu cầu Boot chọn `local` lúc startup. Tên nhóm chỉ được dùng để mở rộng khi nó được kích hoạt.

Nếu muốn một chế độ mặc định, hãy lựa chọn chính sách rõ:

- Cấu hình `spring.profiles.active` ở document không profile-specific nếu phù hợp với yêu cầu.
- Truyền `SPRING_PROFILES_ACTIVE` qua launcher hoặc IDE.
- Cung cấp lệnh chạy local được tài liệu hóa.
- Thiết kế bean mặc định không cần profile, với điều kiện cụ thể nếu cần.

Đừng đánh đồng `spring.profiles.default`, `spring.profiles.active` và `spring.profiles.group`.

### 17.2. Vì sao không hard-code production trong JAR chung?

Nếu đặt:

```yaml
spring:
  profiles:
    active: production
```

trong cấu hình đóng gói, ứng dụng có thể vô tình khởi động chế độ production khi chạy ở laptop nếu người dùng không override.

Với một artifact dùng nhiều môi trường, để hệ thống triển khai cung cấp tên môi trường thường an toàn và rõ ràng hơn. Cũng có thể thiết kế mặc định local nhưng phải đánh giá rủi ro vì local default không được phép chạy ngoài dự kiến ở production.

## 18. Kiểm tra active profiles tại runtime

Sau khi ứng dụng khởi động, có thể inject `Environment` để xem profile thực sự active:

```java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + Arrays.toString(
                                environment.getActiveProfiles()
                        )
        );
    }
}
```

Nếu chạy `--spring.profiles.active=production` với định nghĩa group phù hợp, bạn có thể quan sát `production` cùng các thành viên như `remote-db`, `real-notify`, `observability`.

### 18.1. Không dùng log để tiết lộ secrets

Danh sách tên profile thường không phải secret, nhưng tên profile có thể mang thông tin hạ tầng. Tránh dùng tên chứa mật khẩu, token hoặc hostname nhạy cảm.

Khi debug, không in toàn bộ `Environment` hoặc các PropertySources ra console; nhiều property có thể chứa thông tin bí mật.

### 18.2. Kiểm tra xem một profile có active không

`Environment` hỗ trợ `acceptsProfiles`:

```java
import org.springframework.core.env.Profiles;

boolean remoteDbActive =
        environment.acceptsProfiles(
                Profiles.of("remote-db")
        );

boolean productionOrStaging =
        environment.acceptsProfiles(
                Profiles.of("production | staging")
        );
```

API `Profiles.of(...)` cho phép biểu thức profile với toán tử như `!`, `&` và `|`. Sử dụng khi cần kiểm tra một điều kiện profile trong code chẩn đoán hoặc infrastructure.

Thông thường, business service không cần gọi `acceptsProfiles` liên tục. Nếu sự khác nhau là implementation, hãy để Spring chọn bean qua `@Profile` hoặc một cơ chế configuration rõ ràng.

## 19. Viết @Profile với biểu thức

`@Profile` chấp nhận biểu thức logic, không chỉ một tên profile đơn.

Ví dụ:

```java
@Profile("production & observability")
```

có nghĩa là cả `production` và `observability` đều phải active.

Ví dụ khác:

```java
@Profile("!production")
```

có nghĩa bean phù hợp khi `production` không active.

### 19.1. @Profile với nhiều giá trị là OR, không phải AND

Ví dụ:

```java
@Profile({"staging", "production"})
```

có nghĩa bean có thể active nếu **một trong hai** profile phù hợp, không phải phải có cả hai.

Nếu muốn AND, hãy dùng biểu thức:

```java
@Profile("staging & observability")
```

### 19.2. Dùng tên group hay dùng biểu thức?

Nếu `production` group đã bao gồm `observability`, một bean chuyên dành cho production có thể chỉ cần:

```java
@Profile("production")
```

Nếu bean yêu cầu observability bất kể môi trường:

```java
@Profile("observability")
```

Nếu muốn yêu cầu đồng thời staging và observability bất kể định nghĩa group nào được sửa sau này, dùng biểu thức AND có thể mô tả rõ chính sách đó.

## 20. Test profile group với Spring Boot Test

Test giúp bạn biết một group đã kích hoạt đúng tập bean/configuration chưa.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("staging")
class StagingProfileTest {

    @Autowired
    Environment environment;

    @Test
    void expandsStagingGroup() {
        assertThat(environment.getActiveProfiles())
                .contains("staging", "remote-db",
                          "console-notify", "observability");
    }
}
```

Trong một Spring Boot test context sử dụng Config Data của ứng dụng, `@ActiveProfiles("staging")` có thể dùng để chọn profile nhóm, sau đó bạn kiểm tra các profile thành viên đã được kích hoạt.

### 20.1. Test bean selection

Ví dụ:

```java
@SpringBootTest
@ActiveProfiles("local")
class LocalNotificationTest {

    @Autowired
    private MessageSink sink;

    @Test
    void usesConsoleSink() {
        assertThat(sink).isInstanceOf(ConsoleMessageSink.class);
    }
}
```

Và production:

```java
@SpringBootTest
@ActiveProfiles("production")
class ProductionNotificationTest {

    @Autowired
    private MessageSink sink;

    @Test
    void usesExternalSink() {
        assertThat(sink).isInstanceOf(ExternalMessageSink.class);
    }
}
```

Ví dụ giả định package ứng dụng chứa những component này và test có Spring Boot Test/AssertJ dependency.

### 20.2. Test một tổ hợp profile không hợp lệ

Nếu hai nhóm không được phép active đồng thời, bạn có thể tạo test hoặc startup validation để phát hiện:

```text
spring.profiles.active=staging,production
```

Chạy với tổ hợp đó có thể khiến cả hai `MessageSink` active. Test giúp đội phát triển phát hiện cấu hình không hợp lệ trước khi deploy.

### 20.3. Test không thay thế kiểm tra deployment

Ngay cả khi test profile group thành công, production deployment vẫn có thể cung cấp:

```text
SPRING_PROFILES_ACTIVE=staging
```

do nhầm biến môi trường. Vì vậy, cần quan sát active profiles thực tế lúc khởi động process và kiểm tra cấu hình CI/CD.

## 21. Những vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chạy `production` nhưng không có bean `real-notify` | Group chưa khai báo đúng hoặc không được nạp | Kiểm tra `spring.profiles.group.production` trong document gốc |
| Boot báo property `spring.profiles.group` không hợp lệ | Đặt group trong profile-specific document | Chuyển group lên non-profile-specific document |
| Chạy không truyền profile làm thiếu bean | Group được định nghĩa nhưng chưa được kích hoạt | Chọn active profile hoặc thiết kế bean mặc định |
| Hai bean cùng interface gây `NoUniqueBeanDefinitionException` | Hai nhóm/profile đối nghịch cùng active | Chỉ kích hoạt tổ hợp hợp lệ; kiểm tra cấu hình |
| Chỉ thấy tên môi trường, không thấy thành viên | Định nghĩa group không được Boot nạp hoặc version không hỗ trợ | Xem phiên bản, path Config Data và active profiles thực tế |
| application-production.yml không được áp dụng | `production` chưa active, sai tên file hoặc Config Data không được tìm thấy | Kiểm tra lệnh chạy, tên file và locations |
| Giá trị từ thành viên group ghi đè giá trị không như mong đợi | Có nhiều nguồn cùng key và quy tắc precedence | Kiểm tra Environment/Config Data và giảm key trùng |
| File YAML đổi nhưng bean không đổi | Profile/Config Data được xử lý lúc startup | Restart hoặc thiết kế refresh riêng |
| Đặt group trong `application-production.yml` để “tự mở rộng” | Đây là vị trí bị hạn chế | Chuyển định nghĩa sang `application.yml` |
| Test qua IDE đúng nhưng JAR sai | IDE và JAR có profile/config locations khác nhau | So sánh runtime classpath, Environment và biến triển khai |
| Dùng `@Profile({"production","staging"})` mà tưởng là AND | Mảng profile được hiểu như OR | Dùng biểu thức `"production & staging"` nếu thật sự muốn AND |
| Một nhóm quá nhiều thành viên khó kiểm soát | Profile granularity và naming chưa phù hợp | Đơn giản hóa, tách theo trách nhiệm và loại thành viên trùng lặp |

### 21.1. Lỗi thiếu bean khi group không active

Giả sử service yêu cầu `MessageSink`:

```java
public NotificationService(MessageSink sink) {
    this.sink = sink;
}
```

Nếu không có `console-notify` hoặc `real-notify` active, Spring không có candidate `MessageSink`. Startup có thể thất bại với `UnsatisfiedDependencyException` được bọc qua `NoSuchBeanDefinitionException`.

Để xử lý, kiểm tra active profiles và group definitions trước khi sửa injection code.

### 21.2. Nhầm feature group với việc nạp thư viện

Nếu `production` kích hoạt `real-notify` nhưng project không có class/bean cho real notification, chỉ kích hoạt profile không tự thêm dependency.

Profile group không tự thêm Maven/Gradle dependency, không tự tạo bean class chưa tồn tại và không kết nối mạng. Nó chỉ khiến các cấu hình và bean definitions **đã được cung cấp** có điều kiện profile phù hợp được xét.

### 21.3. Sự khác nhau giữa condition và group

`@Profile("real-notify")` xét tập profile active. `@ConditionalOnProperty` xét property trong Environment.

Nếu cùng một bean dùng cả hai điều kiện, cả hai đều cần phù hợp theo quy tắc kết hợp condition. Đừng cho rằng một group đã active sẽ bỏ qua những điều kiện khác của bean.

## 22. Kiểm tra giá trị hiệu lực và nguồn gốc cấu hình

Nếu một profile group hoạt động nhưng property nhận giá trị bất ngờ, hãy kiểm tra không chỉ tập profile mà còn **PropertySources**.

Một runner chẩn đoán đơn giản:

```java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentDiagnostics implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentDiagnostics(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("Storage mode: "
                + environment.getProperty(
                        "app.storage.mode", "<missing>"
                ));

        System.out.println("Notification channel: "
                + environment.getProperty(
                        "app.notification.channel", "<missing>"
                ));
    }
}
```

Ví dụ chỉ đọc các key không chứa bí mật.

### 22.1. Actuator có thể hỗ trợ chẩn đoán

Với Spring Boot Actuator, một số endpoint như:

- `/actuator/env`.
- `/actuator/configprops`.
- `/actuator/conditions`.

có thể giúp xem giá trị cấu hình hiệu lực, trạng thái binding và lý do điều kiện được áp dụng hay bỏ qua, tùy cấu hình exposure và bảo mật.

Không bật hiển thị toàn bộ property values trên production nếu có khả năng lộ secrets. Hãy ưu tiên kiểm tra các key không nhạy cảm và bảo vệ endpoint.

### 22.2. Đừng chỉ đọc application-production.yml

Một giá trị có thể đến từ:

- `application.yml`.
- `application-production.yml`.
- File của một profile thành viên như `application-remote-db.yml`.
- File Config Data được import.
- File cấu hình ngoài JAR.
- Java system property.
- OS environment variable.
- Command-line argument.

Vì vậy, muốn biết tại sao `app.storage.mode` là `remote`, cần xem cả group thành viên và precedence của các nguồn, không chỉ file đặt theo tên môi trường.

## 23. Profile groups trong CI/CD và container deployment

Trong hệ thống triển khai, mục tiêu là để mỗi môi trường có một tên được kiểm soát.

Ví dụ:

```text
Local developer:
  SPRING_PROFILES_ACTIVE=local

Staging deployment:
  SPRING_PROFILES_ACTIVE=staging

Production deployment:
  SPRING_PROFILES_ACTIVE=production
```

Cấu hình nhóm đi kèm artifact:

```yaml
spring:
  profiles:
    group:
      local: [local-db, console-notify]
      staging: [remote-db, console-notify, observability]
      production: [remote-db, real-notify, observability]
```

Nhờ đó pipeline không phải giữ các danh sách profile chức năng ở nhiều biến triển khai khác nhau.

### 23.1. Không dùng group để lưu secret

Trong group chỉ nên chứa **tên profile**, không chứa password hoặc token:

```yaml
spring:
  profiles:
    group:
      production:
        - remote-db
        - real-notify
```

Secrets như database password, API key và access token nên được cung cấp qua secret management, environment variables hoặc cơ chế configuration an toàn tương ứng.

### 23.2. Kiểm tra biến môi trường lúc deploy

Nếu hệ thống production vô tình dùng:

```text
SPRING_PROFILES_ACTIVE=staging
```

thì Spring Boot sẽ áp dụng group staging theo đúng cấu hình. Đây là lỗi deployment, không phải lỗi của profile group.

Nên có bước kiểm tra tên profile mà pipeline truyền vào và log active profiles ở mức an toàn để giúp chẩn đoán.

### 23.3. Cẩn trọng với tổ hợp nhiều nhóm

Một lệnh như:

```bash
java -jar app.jar --spring.profiles.active=production,staging
```

có thể làm các thành viên của cả hai nhóm active.

Nếu `production` và `staging` là hai môi trường loại trừ nhau, hãy thiết kế validation hoặc policy pipeline để từ chối tổ hợp này. Spring Boot không tự biết chính sách vận hành của tổ chức.

## 24. Migration từ danh sách profile dài sang group

Giả sử trước đây team chạy production bằng:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

Để migration:

### Bước 1 — Kiểm kê các tổ hợp đang dùng

Ghi lại những tổ hợp trên local, test, staging và production. Đặc biệt tìm các profile trùng nhau giữa nhiều môi trường.

### Bước 2 — Phân loại profile chức năng và profile môi trường

Ví dụ:

- Môi trường: `local`, `staging`, `production`.
- Chức năng: `local-db`, `remote-db`, `console-notify`, `real-notify`, `observability`.

### Bước 3 — Khai báo group trong file không profile-specific

```yaml
spring:
  profiles:
    group:
      production: [remote-db, real-notify, observability]
```

Đặt trong document gốc của `application.yml` hoặc một nguồn Config Data không đặc thù profile.

### Bước 4 — Đổi lệnh chạy

Từ:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

thành:

```bash
java -jar app.jar --spring.profiles.active=production
```

### Bước 5 — Kiểm tra file và bean theo thành viên

Xác nhận các file như `application-remote-db.yml` được nạp và bean `@Profile("real-notify")` được đăng ký khi `production` active.

### Bước 6 — Xem lại các key bị ghi đè

Nếu có nhiều profile cùng thiết lập một key, ghi rõ chủ sở hữu cấu hình hoặc điều chỉnh cấu trúc để giảm phụ thuộc vào thứ tự profile.

### Bước 7 — Kiểm thử nhiều môi trường

Chạy context riêng cho local, staging, production và kiểm tra những bean bắt buộc được đăng ký, những bean không phù hợp không xuất hiện, và những property quan trọng nhận giá trị đúng.

### Bước 8 — Cập nhật tài liệu triển khai

Đảm bảo runbook, Docker Compose, Kubernetes manifest, scripts và IDE run configurations sử dụng các tên group được thống nhất. Không để một số nơi dùng group còn nơi khác giữ danh sách cũ sai lệch.

## 25. Bài thực hành

### Bài 1 — Tạo profile group đầu tiên

Tạo project Spring Boot 2.4+ với `application.yml`:

```yaml
spring:
  profiles:
    group:
      local:
        - local-db
        - console-notify
```

Chạy bằng `--spring.profiles.active=local` và in danh sách active profiles qua `Environment`.

### Bài 2 — Tạo hai profile thành viên có file riêng

Tạo `application-local-db.yml` và `application-console-notify.yml`. Mỗi file khai báo một key khác nhau. Kiểm tra các giá trị đều có hiệu lực khi bật nhóm `local`.

### Bài 3 — Thêm staging và production

Tạo nhóm `staging` và `production` có chung `remote-db` nhưng khác profile thông báo. Chạy với từng tên nhóm, kiểm tra profile thành viên được kích hoạt.

### Bài 4 — Dùng @Profile để chọn bean

Tạo `MessageSink` cùng hai implementation: một `@Profile("console-notify")`, một `@Profile("real-notify")`. Inject `MessageSink` vào service và kiểm tra implementation theo từng môi trường.

### Bài 5 — Kiểm tra cấu hình ở vị trí không hợp lệ

Cố ý đặt `spring.profiles.group` trong `application-production.yml`. Quan sát lỗi Spring Boot báo. Sau đó chuyển định nghĩa group về document gốc `application.yml` và chạy lại.

### Bài 6 — Multi-document YAML

Thay các file thành viên bằng các document trong `application.yml` với `spring.config.activate.on-profile`. Giữ group definitions ở document không có `on-profile` rồi kiểm tra kết quả.

### Bài 7 — Phân biệt active, include và group

Tạo ví dụ dùng `spring.profiles.active` để chọn profile, `spring.profiles.include` để bổ sung một profile luôn cần và `spring.profiles.group` để mở rộng tên môi trường. Giải thích mỗi cơ chế giải quyết vấn đề gì.

### Bài 8 — Cấu hình cùng một key ở nhiều nguồn

Đặt `app.http-client.timeout` trong `application.yml`, `application-production.yml` và command-line argument. Dự đoán rồi quan sát giá trị hiệu lực từ `Environment#getProperty`.

### Bài 9 — Tổ hợp môi trường không hợp lệ

Thử chạy `--spring.profiles.active=staging,production` khi hai nhóm chọn các implementation thông báo khác nhau. Quan sát lỗi hoặc tập bean xuất hiện. Đề xuất validation để ngăn tổ hợp này.

### Bài 10 — Kiểm tra bằng @SpringBootTest

Viết test dùng `@ActiveProfiles("staging")`. Assert những profile thành viên cần thiết active và service nhận đúng implementation theo môi trường staging.

### Bài 11 — Migrate một lệnh chạy cũ

Giả sử runbook có:

```bash
java -jar app.jar \
  --spring.profiles.active=remote-db,real-notify,observability
```

Viết định nghĩa group `production` tương ứng, cập nhật lệnh chạy và giải thích lợi ích bảo trì.

### Bài 12 — Thay đổi profile sau startup

Khởi động ứng dụng với `local`. Sau đó thử thay giá trị biến môi trường trong shell khác hoặc thay file YAML. Quan sát những bean `@Profile` đã được đăng ký không tự thay thế. Giải thích vì sao group là quyết định bootstrap thay vì runtime feature flag.

## 26. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profiles, `spring.profiles.group`, `spring.profiles.include`, default profiles và giới hạn vị trí khai báo.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data, profile-specific files, document activation, thứ tự ưu tiên và nguồn cấu hình bên ngoài.
- [Spring Framework Reference — Bean Definition Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles): cách `@Profile` và `Environment` tham gia điều kiện bean.
- [Spring Framework Javadoc — Profile](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html): cú pháp và cách áp dụng annotation `@Profile`.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): API active/default profiles và truy vấn điều kiện profile.
- [Spring Boot 2.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes): thay đổi Config Data và sự xuất hiện của profile groups.

Trong Spring Boot, **profile group là một bản khai báo ánh xạ tên môi trường sang các profile thành viên**, giúp ứng dụng tái sử dụng cấu hình theo chức năng mà người vận hành vẫn chỉ cần chọn một tên môi trường rõ ràng. Hãy khai báo `spring.profiles.group` ở document không profile-specific, kích hoạt nhóm bằng `spring.profiles.active` hoặc biến môi trường, thiết kế các profile thành viên có trách nhiệm riêng và xác nhận tập active profiles cùng giá trị cấu hình thực tế khi startup. Cách tổ chức này giúp local, staging và production nhất quán hơn mà không đánh đồng profile groups với việc cập nhật cấu hình động trong lúc ứng dụng đang chạy.
