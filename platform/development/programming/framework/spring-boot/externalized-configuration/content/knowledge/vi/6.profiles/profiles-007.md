# Gom profile theo chức năng bằng spring.profiles.group

## 1. Bài toán: nhiều profile nhỏ, khó kích hoạt đúng

Một ứng dụng Spring Boot có thể cần nhiều nhóm cấu hình tùy theo môi trường và khả năng đang bật:

- **proddb**: cấu hình kết nối cơ sở dữ liệu dùng ở production.
- **prodmq**: cấu hình hệ thống nhắn tin hoặc hàng đợi ở production.
- **observability**: cấu hình quan sát hệ thống như các mức log và metric phù hợp.
- **localdb**: cấu hình dữ liệu dành cho máy phát triển.
- **devtools**: một số thiết lập dành cho quá trình phát triển.

Nếu không có cơ chế gom nhóm, mỗi lần triển khai production phải nhớ cả danh sách:

~~~bash
java -jar app.jar --spring.profiles.active=proddb,prodmq,observability
~~~

Việc nhập thiếu một profile có thể làm ứng dụng thiếu thông số cần thiết hoặc không bật đúng một nhóm bean. Danh sách cũng phải được sao chép ở nhiều nơi: script, cấu hình CI/CD, manifest triển khai và hướng dẫn vận hành.

**spring.profiles.group** giải quyết việc này bằng cách đặt **một tên profile mang ý nghĩa tổng hợp** cho nhiều profile liên quan. Khi kích hoạt tên tổng hợp, Spring Boot kích hoạt luôn các profile thành viên.

~~~text
spring.profiles.active=production
               |
               v
      Profile group production
               |
       +-------+--------+
       |       |        |
       v       v        v
     proddb  prodmq  observability
~~~

Nhờ đó người vận hành chỉ cần chọn **production**, còn ứng dụng giữ một danh sách các thành phần cần thiết trong cấu hình chung.

## 2. spring.profiles.group hoạt động như thế nào?

Trong Spring Boot 3.3, mỗi group được khai báo theo dạng:

~~~text
spring.profiles.group.<tên-nhóm> = [profile-1, profile-2, ...]
~~~

Ví dụ bằng **application.yml**:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
~~~

Khi khởi động:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot kích hoạt những profile sau:

~~~text
production
proddb
prodmq
observability
~~~

**Tên nhóm production cũng là một profile đang hoạt động.** Nó không bị thay thế hay biến mất sau khi mở rộng nhóm. Do đó cả **application-production.yml** và các file như **application-proddb.yml** đều có thể được xét.

Đây là khác biệt quan trọng giữa một profile group với phép đổi tên văn bản. Profile group giúp chọn đồng thời nhiều profile trong cơ chế quản lý profile của Spring Boot; những nơi kiểm tra profile bằng **@Profile** hoặc **Environment.acceptsProfiles(...)** cũng quan sát được các profile thành viên đã kích hoạt.

Không cần tạo một annotation riêng để định nghĩa group. Group được cấu hình trong nguồn cấu hình hợp lệ của Spring Boot, còn việc chọn nó diễn ra bằng **spring.profiles.active** hoặc cơ chế kích hoạt profile tương ứng.

## 3. Khai báo trong application.yml và application.properties

### 3.1. YAML: dễ đọc khi số thành viên nhiều

~~~yaml
spring:
  profiles:
    group:
      production:
        - "proddb"
        - "prodmq"
        - "observability"
      development:
        - "localdb"
        - "console-logs"
~~~

Có hai nhóm độc lập:

| Group | Profile thành viên | Mục đích |
| --- | --- | --- |
| **production** | **proddb**, **prodmq**, **observability** | Kết hợp những nhóm cấu hình phục vụ triển khai production |
| **development** | **localdb**, **console-logs** | Kết hợp những nhóm cấu hình cần khi phát triển |

Kích hoạt **production** không tự kích hoạt **development**. Khi chọn **development**, ứng dụng kích hoạt **development**, **localdb** và **console-logs**.

### 3.2. Properties: dùng chỉ số của danh sách

Ví dụ tương đương bằng **application.properties**:

~~~properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
spring.profiles.group.production[2]=observability

spring.profiles.group.development[0]=localdb
spring.profiles.group.development[1]=console-logs
~~~

Trong **.properties**, cú pháp **[0]**, **[1]**, **[2]** biểu diễn thứ tự các phần tử của danh sách thành viên. Không viết nhiều dòng cùng một key đơn giản rồi cho rằng Spring Boot sẽ tự cộng dồn thành một danh sách.

Thông thường chỉ cần chọn một định dạng YAML hoặc properties phù hợp với dự án. Nếu nhiều nguồn cấu hình khác nhau cùng định nghĩa một group, kết quả cuối còn phụ thuộc thứ tự ưu tiên và cách binding danh sách của nguồn được áp dụng; nên giữ định nghĩa group ở một nơi nhất quán.

## 4. Ví dụ đầy đủ: một lệnh kích hoạt ba nhóm chức năng

Giả sử một ứng dụng Java 21 dùng Spring Boot 3.3 và **spring-boot-starter-web**. Ta muốn minh họa việc profile group kích hoạt các file cấu hình khác nhau mà không phụ thuộc vào database hoặc message broker thật.

Cấu trúc dự án:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/profiles/
    │       ├── ProfileGroupApplication.java
    │       └── ProfileController.java
    └── resources/
        ├── application.yml
        ├── application-production.yml
        ├── application-proddb.yml
        ├── application-prodmq.yml
        └── application-observability.yml
~~~

### 4.1. application.yml: khai báo group và giá trị mặc định

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability

demo:
  environment: general
  database-mode: none
  messaging-mode: none
  metrics-enabled: false
~~~

Ở đây **demo.*** là các property minh họa, chưa kết nối database hoặc message broker. Các giá trị mặc định giúp quan sát rõ sự thay đổi khi profile được kích hoạt.

### 4.2. application-production.yml: cấu hình chung cho cả nhóm

~~~yaml
demo:
  environment: production
~~~

Vì **production** vẫn là profile hoạt động, file **application-production.yml** có thể được nạp. File này phù hợp với những giá trị chung cho toàn bộ môi trường production.

### 4.3. application-proddb.yml: phần dữ liệu

~~~yaml
demo:
  database-mode: postgresql
~~~

### 4.4. application-prodmq.yml: phần nhắn tin

~~~yaml
demo:
  messaging-mode: rabbitmq
~~~

### 4.5. application-observability.yml: phần quan sát

~~~yaml
demo:
  metrics-enabled: true
~~~

Ba tệp được chia theo **mối quan tâm chức năng**. Chúng không cần biết group tên gì; tên profile riêng của từng file mới là điều kiện để Spring Boot nạp cấu hình tương ứng.

Trong hệ thống thực tế, file cho nhóm dữ liệu có thể chứa **spring.datasource.url** hoặc thông số pool, còn file nhắn tin có thể chứa endpoint broker. Không đưa mật khẩu thật, token hoặc khóa bí mật vào repository; những giá trị đó nên được cung cấp từ cơ chế quản lý secret của môi trường chạy.

### 4.6. Một API để nhìn thấy profile đang hoạt động

**ProfileGroupApplication.java**:

~~~java
package com.example.profiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileGroupApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileGroupApplication.class, args);
    }
}
~~~

**ProfileController.java**:

~~~java
package com.example.profiles;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    private final Environment environment;

    public ProfileController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/profiles")
    public Map<String, Object> profiles() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("active", Arrays.asList(environment.getActiveProfiles()));
        result.put("environment",
                environment.getProperty("demo.environment", "unknown"));
        result.put("database",
                environment.getProperty("demo.database-mode", "unknown"));
        result.put("messaging",
                environment.getProperty("demo.messaging-mode", "unknown"));
        result.put("metricsEnabled",
                environment.getProperty("demo.metrics-enabled", Boolean.class, false));
        return result;
    }
}
~~~

Controller đọc thông tin từ **Environment** thay vì tự quyết định profile. Khi triển khai thực tế, một API tiết lộ cấu hình không nên mở công khai; endpoint trên chỉ là ví dụ học tập với các giá trị không nhạy cảm.

### 4.7. Build và chạy

Từ dự án có Spring Boot Gradle plugin và web starter:

~~~bash
./gradlew bootJar
~~~

Giả sử artifact được đặt tên **app.jar**, chạy:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Sau đó gọi:

~~~bash
curl http://localhost:8080/profiles
~~~

Kết quả minh họa (thứ tự trường JSON có thể khác):

~~~json
{
  "active": [
    "production",
    "proddb",
    "prodmq",
    "observability"
  ],
  "environment": "production",
  "database": "postgresql",
  "messaging": "rabbitmq",
  "metricsEnabled": true
}
~~~

Điều đáng chú ý:

1. Lệnh chạy chỉ chỉ định một profile **production**.
2. Group làm xuất hiện thêm các profile **proddb**, **prodmq** và **observability**.
3. Spring Boot xét file cấu hình tương ứng với từng profile đang hoạt động.
4. Không cần sửa mã Java hay build riêng một JAR cho từng nhóm thành viên.

Nếu chạy không có active profile và không có nguồn override khác, giá trị có thể giữ các mặc định **general**, **none**, **none**, **false**.

## 5. Group kích hoạt cả điều kiện @Profile

Spring Profiles không chỉ dùng để chọn **application-{profile}.yml**. Một **@Component**, **@Configuration** hoặc **@Bean** cũng có thể được ràng buộc với điều kiện profile.

Ví dụ một bean chỉ tồn tại khi **observability** hoạt động:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    @Profile("observability")
    public MonitoringMarker monitoringMarker() {
        return new MonitoringMarker("monitoring-enabled");
    }

    public record MonitoringMarker(String value) {
    }
}
~~~

Khi chạy **--spring.profiles.active=production**, group kích hoạt **observability**, nên bean **MonitoringMarker** đủ điều kiện đăng ký. Khi chạy với một profile không liên quan và không có cơ chế nào khác kích hoạt **observability**, bean đó sẽ không được đăng ký.

Có thể quan sát bằng **ApplicationContext.containsBean("monitoringMarker")** trong một bài test hoặc đoạn thử nghiệm cục bộ.

**Một phân biệt hữu ích:** một file **application-observability.yml** chỉ nạp cấu hình. Nó không tự cài dependency hay tự tạo các bean mà dự án chưa khai báo. Nếu muốn thực sự bật cơ chế metric, messaging hoặc database, ứng dụng vẫn cần dependency, bean, auto-configuration và các điều kiện phù hợp.

## 6. spring.profiles.group không phải alias thay thế tên profile

Có hai cách hiểu khác nhau:

~~~text
Cách hiểu sai:
production được thay thế bởi proddb, prodmq, observability

Cơ chế đúng:
production đang hoạt động và làm hoạt động thêm
proddb, prodmq, observability
~~~

Ví dụ, nếu cùng lúc có:

~~~text
application-production.yml
application-proddb.yml
application-prodmq.yml
application-observability.yml
~~~

thì tất cả đều có thể được xem xét theo những profile đang hoạt động, với thứ tự ưu tiên Config Data tương ứng.

Vì thế, có thể đặt các thiết lập chung cho production trong **application-production.yml**, còn các thiết lập của từng mối quan tâm ở file riêng.

Đừng đặt lại toàn bộ nhóm cấu hình giống nhau trong **application-production.yml** rồi sao chép tiếp vào **application-proddb.yml**. Một mô hình rõ ràng hơn là **mỗi file đảm nhiệm một phần** và có rất ít key trùng lặp.

## 7. So sánh group với active, include và default

Spring Boot có nhiều thuộc tính liên quan đến profile. Chúng phục vụ các mục đích khác nhau.

| Cơ chế | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **spring.profiles.active** | Chọn profile chủ động kích hoạt | **production** |
| **spring.profiles.group** | Khai báo các profile đi kèm một profile group | **production → proddb, prodmq** |
| **spring.profiles.include** | Thêm profile được bao gồm bên cạnh những profile chủ động kích hoạt | **common, local** |
| **spring.profiles.default** | Chọn profile mặc định nếu không có active profile | **dev** hoặc **none** |

### 7.1. spring.profiles.active chọn điểm bắt đầu

Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Lệnh này kích hoạt group **production** và các thành viên được khai báo. Bạn cũng có thể kích hoạt trực tiếp nhiều profile:

~~~bash
java -jar app.jar --spring.profiles.active=proddb,prodmq
~~~

Tuy nhiên, cách kích hoạt trực tiếp khiến người vận hành phải tự nhớ danh sách. Nếu **observability** là một phần bắt buộc trong nhóm production, lệnh thứ hai bỏ sót profile đó.

Đối với thuộc tính **spring.profiles.active**, các nguồn cấu hình có độ ưu tiên cao hơn có thể thay thế giá trị từ nguồn thấp hơn. Ví dụ tham số dòng lệnh thường có thể ghi đè active profile mặc định trong **application.yml**.

### 7.2. spring.profiles.include thêm profile dùng chung

~~~yaml
spring:
  profiles:
    include:
      - common
      - audit
~~~

**include** bổ sung các profile đã nêu, kể cả khi người chạy chọn active profile khác. Những profile được include được thêm trước các profile được chọn qua **spring.profiles.active**.

Ngược lại, **group** là một tập thành viên được **kích hoạt có điều kiện** khi tên group tương ứng hoạt động. Nếu chỉ chọn **development** thì group **production** không tự mở rộng.

Dùng **include** khi một profile nên được cộng thêm một cách nhất quán ở phạm vi cấu hình đang khai báo. Dùng **group** khi muốn **đặt tên cho một tổ hợp chức năng**, cho phép lựa chọn tổ hợp đó khi chạy.

### 7.3. spring.profiles.default chỉ dùng khi không có active profile

~~~properties
spring.profiles.default=dev
~~~

Nếu không có active profile, Spring Boot có thể sử dụng **dev** làm default profile. Nếu chạy **--spring.profiles.active=production**, default profile không được dùng để bổ sung tự động thành viên cho production.

Group cũng có thể được khai báo cho một tên profile sẽ được kích hoạt qua cơ chế phù hợp, nhưng không nên nhầm thuộc tính **default** với một danh sách **include**.

## 8. Khai báo group ở đâu là hợp lệ?

Đây là một quy tắc quan trọng trong Spring Boot 3.3:

**spring.profiles.group chỉ được khai báo trong tài liệu cấu hình không phụ thuộc profile** (*non-profile-specific documents*).

Tương tự, **spring.profiles.active**, **spring.profiles.default** và **spring.profiles.include** cũng bị ràng buộc về nơi khai báo.

### 8.1. Hợp lệ: khai báo trong application.yml chung

~~~yaml
# src/main/resources/application.yml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

File **application.yml** ở ví dụ này không có điều kiện kích hoạt bằng profile nên là nơi hợp lệ để khai báo group.

### 8.2. Không hợp lệ: đặt group trong application-production.yml

Ví dụ sau **sai vị trí khai báo**:

~~~yaml
# src/main/resources/application-production.yml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Lý do: **application-production.yml** là tài liệu chỉ được dùng khi profile **production** đang hoạt động. Nếu cho phép khai báo group tại đây, việc xác định tập profile cần kích hoạt sẽ phụ thuộc vòng lặp nạp tài liệu theo profile.

### 8.3. Không hợp lệ: đặt group trong document có on-profile

Một file YAML có thể gồm nhiều document, phân tách bằng **---**. Khai báo group trong document bị ràng buộc bởi **spring.config.activate.on-profile** là không hợp lệ:

~~~yaml
# application.yml - phần chung hợp lệ
demo:
  name: sample
---
# Document này không được khai báo spring.profiles.group
spring:
  config:
    activate:
      on-profile: production
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Để sửa, chuyển **spring.profiles.group.production** ra document chung đầu tiên, còn document theo profile chỉ giữ những property nghiệp vụ hoặc vận hành thực sự phụ thuộc profile.

### 8.4. Một file external chung cũng có thể chứa group

Nếu bạn quản lý cấu hình từ bên ngoài JAR, có thể khai báo group trong một nguồn cấu hình được nạp **không phụ thuộc profile**. Quan trọng là nguồn ấy phải có mặt đủ sớm và không nằm trong một file hoặc document chỉ được kích hoạt bởi chính profile cần khai báo.

Ví dụ cấp file config ngoài bằng **spring.config.additional-location**; trong file cấu hình chung bên ngoài, đặt phần **spring.profiles.group**. Không cần buộc group phải nằm trong Java source.

## 9. Dùng group với nhiều môi trường và nhiều mối quan tâm

Một cách tổ chức có thể trông như sau:

~~~yaml
spring:
  profiles:
    group:
      development:
        - dev-db
        - console-logs
      staging:
        - stage-db
        - stage-messaging
        - observability
      production:
        - prod-db
        - prod-messaging
        - observability
~~~

Sơ đồ:

~~~text
development
  |-- dev-db
  +-- console-logs

staging
  |-- stage-db
  |-- stage-messaging
  +-- observability

production
  |-- prod-db
  |-- prod-messaging
  +-- observability
~~~

Các thành viên **observability** có thể được chia sẻ giữa staging và production nếu nội dung cấu hình thực sự dùng chung.

Trong dự án thực tế, tách profile theo **đặc tính cấu hình** có thể giúp tái sử dụng, nhưng tránh biến mỗi key thành một profile riêng. Tên profile nên mô tả một tập tính năng, tích hợp hoặc chế độ triển khai có ý nghĩa.

Đừng tạo group chỉ để đổi tên một profile đơn lẻ mà không có nhu cầu gom nhiều phần. Giữ số lượng group đủ ít để người đọc hiểu được profile nào được chọn khi nhìn vào lệnh triển khai.

## 10. Khi nhiều thành viên khai báo cùng một key

Group kích hoạt nhiều profile, nhưng **không loại bỏ quy tắc ưu tiên cấu hình**.

Giả sử:

**application-proddb.yml**:

~~~yaml
demo:
  shared-name: from-database-profile
~~~

**application-prodmq.yml**:

~~~yaml
demo:
  shared-name: from-messaging-profile
~~~

Khi group **production** kích hoạt cả hai, **demo.shared-name** xuất hiện ở nhiều tài liệu cấu hình. Spring Boot vẫn áp dụng quy tắc thứ tự nạp Config Data và ưu tiên nguồn; ở cùng một nhóm vị trí, các profile được xử lý theo thứ tự có thể khiến một giá trị được nạp sau ghi đè giá trị được nạp trước.

**Cách thiết kế dễ kiểm soát hơn:** tránh định nghĩa trùng key giữa những file chức năng nếu chúng không có chủ đích override. Hãy dùng những namespace riêng như:

~~~yaml
demo:
  database:
    mode: postgresql
~~~

và:

~~~yaml
demo:
  messaging:
    mode: rabbitmq
~~~

Nếu cần override giá trị chung, hãy ghi rõ quy ước ưu tiên và kiểm tra giá trị thực tế từ **Environment** khi ứng dụng khởi động. Đừng dựa vào cảm nhận “profile này quan trọng hơn” vì Spring Boot không xếp hạng theo ý nghĩa tên **db**, **mq** hay **production**.

Tương tự, một property trong **application-production.yml** có thể tương tác với property trùng tên ở file thành viên. Group không tạo cơ chế “merge thông minh” cho mọi giá trị; cấu hình cuối còn phụ thuộc nguồn, thứ tự nạp và loại dữ liệu.

## 11. Kiểm tra những profile nào thực sự hoạt động

**Environment.getActiveProfiles()** trả về những profile đang hoạt động trong môi trường của ứng dụng. Đây là cách trực tiếp để quan sát tác động của group.

Ví dụ kiểm tra bằng một runner:

~~~java
package com.example.profiles;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ProfileDiagnosticsConfiguration {

    @Bean
    CommandLineRunner printActiveProfiles(Environment environment) {
        return args -> System.out.println(
                "Active profiles = "
                        + Arrays.toString(environment.getActiveProfiles()));
    }
}
~~~

Khi chọn **production**, log có thể chứa tên **production** và tất cả thành viên.

Tuy nhiên, không nên coi thứ tự in ra trong một log là một hợp đồng API ổn định để các service khác phụ thuộc vào. Mục đích kiểm tra là biết **profile nào đang active**, còn giá trị cuối của từng property nên được kiểm tra bằng:

~~~java
String databaseMode =
        environment.getProperty("demo.database-mode");
~~~

Trong bài test có JUnit, có thể viết assertion về tập tên profile hoặc giá trị thuộc tính. Đừng mở endpoint xuất toàn bộ Environment ra Internet để debug; nhiều property có thể chứa thông tin nhạy cảm.

## 12. Ví dụ thử nghiệm điều kiện @Profile

Giả sử dự án có hai bean triển khai một interface:

~~~java
package com.example.profiles;

public interface MessageSender {
    String destination();
}
~~~

Bean thứ nhất chỉ dành cho chế độ nhắn tin production:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prodmq")
public class ProductionMessageSender implements MessageSender {
    @Override
    public String destination() {
        return "production-broker";
    }
}
~~~

Bean thứ hai dành cho chế độ gửi cục bộ:

~~~java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("localmq")
public class LocalMessageSender implements MessageSender {
    @Override
    public String destination() {
        return "in-memory";
    }
}
~~~

Chẳng hạn, khai báo thêm group:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
      local:
        - localdb
        - localmq
~~~

Khi chọn **--spring.profiles.active=production**, điều kiện **@Profile("prodmq")** được thỏa mãn. Khi chọn **local**, điều kiện **@Profile("localmq")** được thỏa mãn.

Hai bean trên chỉ là phần minh họa. Nếu thực tế nhiều profile được bật đồng thời khiến cả hai bean cùng tồn tại, việc tiêm một **MessageSender** duy nhất có thể bị mơ hồ. Vì vậy nên thiết kế group và quy tắc **@Profile** sao cho mỗi cấu hình triển khai tạo đúng tập bean mong muốn.

## 13. Cấu hình từ CI/CD, Docker và Kubernetes

Group không yêu cầu một cơ chế triển khai riêng. Nền tảng triển khai chỉ cần cấp **spring.profiles.active** như bình thường.

### 13.1. Lệnh Java

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

### 13.2. Biến môi trường

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar app.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "production"
java -jar app.jar
~~~

### 13.3. Docker

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=production \
  my-application:1.0.0
~~~

Nếu group **production** đã được khai báo trong tài liệu cấu hình được ứng dụng nạp, profile thành viên sẽ được kích hoạt khi container khởi động.

### 13.4. Kubernetes

Ví dụ một đoạn khai báo biến môi trường trong Pod template:

~~~yaml
containers:
  - name: app
    image: my-application:1.0.0
    env:
      - name: SPRING_PROFILES_ACTIVE
        value: "production"
~~~

Đây chỉ là đoạn minh họa cho trường **env** trong cấu hình container, không phải toàn bộ Deployment manifest.

**Quan trọng:** group giúp chọn các cấu hình hợp lệ; nó không phải công cụ quản lý secret. Những giá trị như password, token và private key cần được cấp bằng giải pháp phù hợp với môi trường triển khai, không nhúng cứng vào profile file trong repository.

## 14. Các lỗi thường gặp

### Lỗi 1: đặt group trong application-production.yml

Nếu file chứa định nghĩa group chỉ được nạp khi profile production đã kích hoạt, Spring Boot không chấp nhận kiểu khai báo đó. Cách sửa là chuyển **spring.profiles.group** sang một file hoặc document cấu hình chung.

### Lỗi 2: đặt group trong YAML document có on-profile

**spring.config.activate.on-profile** làm document phụ thuộc profile. Không khai báo **spring.profiles.group** ở document này. Tách định nghĩa group và những cấu hình theo profile thành các document riêng, đặt group ở document không phụ thuộc profile.

### Lỗi 3: chỉ định tên group rồi quên rằng bản thân group cũng active

Khi kích hoạt **production**, file **application-production.yml** và bean đánh dấu **@Profile("production")** có thể hoạt động bên cạnh các thành viên. Đó là hành vi đúng của group, không phải một profile “ảo” chỉ dùng để tham chiếu.

### Lỗi 4: lạm dụng spring.profiles.include

Nếu mục tiêu là tạo tổ hợp **production** chỉ khi người vận hành chọn nó, không nên dùng **include** chung để thêm toàn bộ thành viên production trong mọi môi trường. Dùng **group** để điều khiển việc cộng thêm thành viên theo tên group.

### Lỗi 5: chỉ khai báo group mà không thực sự kích hoạt nó

**spring.profiles.group.production** định nghĩa quan hệ giữa các profile, nhưng không mặc định bật production. Cần chọn **spring.profiles.active=production** hoặc kích hoạt profile theo cơ chế tương ứng.

### Lỗi 6: tưởng group tự tạo database hoặc message broker

Các profile được kích hoạt khiến tài liệu cấu hình và bean có điều kiện phù hợp được xét. Chúng không thay thế dependency, hạ tầng, DNS, account hay quyền truy cập. Ví dụ **prodmq** không làm RabbitMQ tự xuất hiện nếu hệ thống chưa triển khai broker.

### Lỗi 7: nhiều group làm các bean xung đột

Nếu một lần chạy kích hoạt các group chứa nhiều cách triển khai thay thế nhau (ví dụ **localmq** và **prodmq**), có thể có nhiều bean cùng kiểu. Hãy thiết kế profile thành viên và điều kiện bean rõ ràng; tránh chọn cùng lúc những tổ hợp không tương thích.

### Lỗi 8: cho rằng thứ tự thành viên thay thế toàn bộ quy tắc PropertySource

Group làm nhiều profile active. Khi một key được định nghĩa ở nhiều nơi, Spring Boot vẫn giải quyết theo thứ tự Config Data, vị trí file và nguồn cấu hình bên ngoài. Cần kiểm tra thuộc tính thực tế khi có override.

### Lỗi 9: đưa cấu hình nhạy cảm vào nhóm cấu hình commit lên Git

Không đưa bí mật thực vào **application-proddb.yml** hoặc **application-production.yml**. Tên file chứa **prod** không làm nội dung trở nên an toàn.

## 15. Bài thực hành

### Bài A: kích hoạt một nhóm gồm ba profile

1. Tạo **application.yml** với **spring.profiles.group.production** gồm **proddb**, **prodmq** và **observability**.
2. Tạo ba file **application-proddb.yml**, **application-prodmq.yml**, **application-observability.yml**, mỗi file chỉ thay một key riêng.
3. Chạy **--spring.profiles.active=production**.
4. Dùng **Environment.getActiveProfiles()** và **Environment.getProperty(...)** để quan sát cả danh sách profile và giá trị cấu hình.

**Kết quả cần hiểu:** một profile được chọn có thể kích hoạt đồng thời các profile thành viên.

### Bài B: kích hoạt riêng từng thành viên

1. Dừng lượt chạy trước.
2. Khởi động bằng **--spring.profiles.active=proddb**.
3. Đọc danh sách profile và các property minh họa.

**Kết quả cần hiểu:** kích hoạt trực tiếp **proddb** không có nghĩa group **production** cũng được kích hoạt ngược lại. Group định nghĩa chiều **production → thành viên**.

### Bài C: thêm nhóm development

1. Khai báo **spring.profiles.group.development** gồm **localdb** và **console-logs**.
2. Tạo **application-localdb.yml** và **application-console-logs.yml** với các key minh họa riêng.
3. Chạy **--spring.profiles.active=development**.
4. Kiểm tra không có **proddb** hoặc **prodmq** khi không có nguồn nào khác kích hoạt chúng.

**Kết quả cần hiểu:** mỗi group diễn tả một tổ hợp do người vận hành lựa chọn.

### Bài D: nhìn thấy sự khác nhau giữa group và include

1. Ở bản thử nghiệm riêng, thêm **spring.profiles.include: [common]** trong file cấu hình chung.
2. Chạy profile **production**, rồi chạy profile **development**.
3. Quan sát **common** vẫn được bổ sung khi chọn các nhóm khác nhau.
4. Bỏ **include** rồi thử lại để quan sát nhóm được kích hoạt độc lập.

**Kết quả cần hiểu:** include là cơ chế cộng thêm profile ở phạm vi khai báo, còn group là cơ chế cộng thêm các thành viên khi tên nhóm được kích hoạt.

### Bài E: quy tắc đặt group trong tài liệu cấu hình chung

1. Thử đặt group trong **application-production.yml** của bản thử nghiệm.
2. Quan sát lỗi cấu hình khi Spring Boot xử lý định nghĩa không hợp lệ.
3. Chuyển định nghĩa về **application.yml** không gắn điều kiện profile.
4. Khởi động lại bằng **--spring.profiles.active=production**.

**Kết quả cần hiểu:** định nghĩa quan hệ profile phải nằm ở nơi có thể được xử lý trước và độc lập với việc lựa chọn một profile cụ thể.

## 16. Điểm cốt lõi

- **spring.profiles.group** đặt tên cho một tổ hợp profile có liên quan, ví dụ **production → proddb + prodmq + observability**.
- Chọn **--spring.profiles.active=production** kích hoạt **production** và các profile thành viên.
- Khai báo group bằng danh sách YAML hoặc các phần tử có chỉ số trong **application.properties**.
- Group ảnh hưởng đến việc nạp **application-{profile}** và điều kiện như **@Profile**.
- Định nghĩa **spring.profiles.group** chỉ hợp lệ trong tài liệu cấu hình **không phụ thuộc profile**; không đặt trong **application-production.yml** hoặc document có **spring.config.activate.on-profile**.
- **spring.profiles.active** chọn tên cần kích hoạt; **include** thêm các profile theo cách khác; **default** chỉ áp dụng khi không có active profile.
- Tách profile theo nhóm chức năng giúp cấu hình dễ dùng lại, nhưng vẫn phải quản lý trùng key, điều kiện bean và secret phù hợp.

**Tài liệu tham khảo chính thức:**

- Spring Boot 3.3 — Profiles, mục *Profile Groups*: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Externalized Configuration, mục *Profile Specific Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — Profiles và Environment: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
