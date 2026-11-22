# Tách tệp dùng chung bằng import và chứng minh thứ tự ghi đè trong Spring Boot 3.3

## 1. Mục tiêu của bài thực hành tổng hợp

Một ứng dụng Spring Boot thường có nhiều cấu hình dùng chung giữa các dịch vụ: thời gian chờ HTTP, số lần retry, feature flags, tên miền hệ thống và các lựa chọn quan sát. Nếu sao chép mọi giá trị vào nhiều tệp `application.properties`, một thay đổi sẽ phải được sửa ở nhiều nơi, khó kiểm soát và dễ tạo sai lệch.

Spring Boot hỗ trợ **Config Data import** qua khóa:

```properties
spring.config.import=...
```

Cơ chế này cho phép một tài liệu cấu hình khai báo các tài liệu khác cần nạp. Thế nhưng người dùng cần hiểu rõ **thứ tự ghi đè**: không phải vì một giá trị nằm trong `application.properties` mà nó luôn thắng giá trị trong tệp được import. Cũng không phải cứ đặt một dòng ở cuối file là nó thắng các tệp khác.

Bài thuộc nhóm **Thực hành tổng hợp** của chủ đề **Spring Boot Externalized Configuration**, sử dụng **Spring Boot 3.3.x**, **Java 17+**, JUnit 5 và một dự án Maven hoặc Gradle.

Chúng ta sẽ thiết kế cấu hình theo ba lớp:

```text
application.properties
  └── spring.config.import
       ├── config/shared.properties       (giá trị dùng chung)
       └── config/service.properties      (giá trị riêng dịch vụ)
```

Sau đó chứng minh:

1. Tệp import được Spring Boot thực sự nạp.
2. Tệp được import có thể **ghi đè** tệp khai báo `spring.config.import`.
3. Trong danh sách import cùng một khóa, **import về sau có ưu tiên cao hơn import trước**.
4. Đổi thứ tự import sẽ đổi giá trị thắng khi có key trùng.
5. Vị trí dòng `spring.config.import` trong cùng một document không quyết định precedence.
6. Đối số `--key=value` của ứng dụng có thể ghi đè giá trị đến từ Config Data.
7. Tệp theo profile của import có thể được phát hiện và tham gia precedence.
8. Import tương đối và import cố định giải quyết đường dẫn khác nhau.
9. Import tùy chọn có thể thiếu mà không làm ứng dụng fail, còn import bắt buộc thiếu thường khiến startup lỗi.
10. Một tài nguyên được import nhiều lần không nhất thiết được nạp lại nhiều lần.
11. Dùng `SpringApplication.run(...)` và `@TempDir` để kiểm chứng thay vì chỉ phỏng đoán từ tên tệp.
12. Tách bằng chứng “tệp đã được nạp” khỏi bằng chứng “giá trị nào thắng”.
13. Kiểm tra typed binding bằng `@ConfigurationProperties` và tránh làm lộ secret khi debug.

## 2. `spring.config.import` là gì?

Khai báo trong file `.properties`:

```properties
spring.config.import=classpath:/config/shared.properties
```

Hoặc YAML:

```yaml
spring:
  config:
    import: classpath:/config/shared.yaml
```

Spring Boot sẽ xử lý import trong giai đoạn **Config Data** khi chuẩn bị `Environment`, trước khi phần lớn bean ứng dụng được tạo.

Một cách hình dung:

```text
SpringApplication.run(...)
         |
         v
Config Data xử lý application.properties
         |
         +-- Phát hiện spring.config.import
         |
         v
Nạp tệp được import
         |
         v
Thêm các PropertySource theo thứ tự precedence
         |
         v
Environment#getProperty(...)
         |
         v
Binder liên kết vào @ConfigurationProperties
```

Import có thể chỉ đến:

- Tài nguyên trên classpath bằng `classpath:`.
- File trên hệ thống bằng `file:`.
- Đường dẫn tương đối với tệp chứa khai báo import.
- Config tree trong những tình huống được hỗ trợ.
- Loại location bổ sung từ các thư viện tích hợp Config Data API.

**Import không phải `@Import` trong Spring Java Configuration.** `@Import` dùng cho cấu hình bean; `spring.config.import` dùng để nạp **dữ liệu cấu hình**.

## 3. Quy tắc precedence quan trọng nhất

Tài liệu Spring Boot 3.3 ghi rõ:

- Tài liệu được import được xử lý như dữ liệu Config Data bổ sung gần tài liệu khai báo import.
- Giá trị từ tài liệu import **có thể ghi đè** giá trị trùng tên trong tài liệu đã khai báo import.
- Nhiều import khai báo trong **một** `spring.config.import` được xử lý theo thứ tự viết; **import về sau có ưu tiên cao hơn**.
- Vị trí của dòng `spring.config.import` **trong cùng document** không làm thay đổi quy tắc này.
- Import tương đối được giải quyết dựa trên vị trí tài liệu đang khai báo import.
- Một import trỏ cùng tài nguyên được nạp **một lần**, dù khai báo lặp nhiều lần.

Ví dụ:

```properties
# application.properties
spring.config.import=shared.properties
lab.import.mode=from-application
```

Và:

```properties
# shared.properties
lab.import.mode=from-shared
```

Nếu không có nguồn ưu tiên cao hơn, giá trị có hiệu lực sẽ là:

```text
lab.import.mode=from-shared
```

Điều đó có thể gây bất ngờ nếu bạn quen suy nghĩ “file chính luôn thắng file con”. Với Spring Boot Config Data, cần xét **vị trí tài liệu import trong cấu trúc nguồn**, không chỉ quan hệ file cha/con về mặt thư mục.

### Nhiều import

```properties
spring.config.import=shared.properties,service.properties
```

Nếu cả hai file đều khai:

```properties
lab.import.mode=...
```

thì `service.properties` thường thắng `shared.properties` trong ví dụ cùng document và không có nguồn ưu tiên cao hơn.

Mục đích bài thực hành là **chứng minh** bằng một startup thật, không chỉ chép lại quy tắc.

## 4. Kiến trúc “shared trước, service sau”

Giả sử đội kỹ thuật có:

- Bộ giá trị chung, được tái sử dụng cho nhiều ứng dụng.
- Bộ giá trị riêng của dịch vụ `orders`.
- Các giá trị triển khai theo profile hoặc biến môi trường.
- Những override tạm thời khi chạy CLI.

Kiến trúc:

```text
                  +------------------------------+
                  | application.properties       |
                  | app name, import declarations|
                  +---------------+--------------+
                                  |
                                  v
                      Config Data import list
                                  |
                    +-------------+--------------+
                    |                            |
                    v                            v
           shared.properties             service.properties
           timeout mặc định              timeout riêng
           retry mặc định                mode riêng
           feature chung                 owner riêng
                    |                            |
                    +-------------+--------------+
                                  |
                                  v
                           Spring Environment
                                  |
                                  v
                   @ConfigurationProperties / @Value
```

Để giá trị riêng của dịch vụ ghi đè dùng chung, thiết kế:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Đừng viết ngược thứ tự rồi mong `service.properties` vẫn thắng vì tên của nó “có vẻ riêng biệt” hơn.

### Một nguyên tắc phân quyền cấu hình

Tệp `shared.properties` nên chứa những giá trị **phổ thông và ít nhạy cảm** như retry mặc định, timeout mặc định, flag có ý nghĩa chung.

Tệp `service.properties` chứa những khác biệt của dịch vụ.

Các giá trị thuộc **môi trường triển khai thực tế** — token, mật khẩu, endpoint production, tên vùng cloud — nên được quản lý theo chính sách deploy, environment variables, config tree hoặc secret manager, không cố đóng cứng hết trong `shared.properties`.

## 5. Tạo dự án Spring Boot 3.3

Yêu cầu:

- JDK 17 hoặc mới hơn phù hợp Spring Boot 3.3.
- Maven Wrapper hoặc Gradle Wrapper.
- Dependency `spring-boot-starter`.
- Dependency test `spring-boot-starter-test`.

Ví dụ Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Project thực tế cần Spring Boot parent hoặc dependency management đồng bộ với **3.3.x**.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Bài thực hành chỉ cần console app; không nhất thiết thêm web starter hoặc cơ sở dữ liệu.

## 6. Cấu trúc thư mục đề xuất

```text
config-import-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/
    │   │       └── importlab/
    │   │           ├── ImportLabApplication.java
    │   │           └── ImportSettings.java
    │   └── resources/
    │       ├── application.properties
    │       └── config/
    │           ├── shared.properties
    │           ├── service.properties
    │           └── service-prod.properties
    └── test/
        └── java/
            └── example/
                └── importlab/
                    └── ImportPrecedenceTest.java
```

Ở đây:

```text
classpath:/config/shared.properties
```

chỉ đến:

```text
src/main/resources/config/shared.properties
```

sau khi file được đưa vào classpath/output build.

Cần phân biệt đường dẫn **trong repository** với location URI mà Spring Boot sử dụng. Prefix `classpath:` không có nghĩa đọc nguyên đường dẫn `src/main/resources` lúc runtime. Khi đóng JAR, tài nguyên nằm trong artifact.

## 7. File gốc: `application.properties`

Tạo:

`src/main/resources/application.properties`

```properties
spring.application.name=config-import-lab

# Config Data: shared trước, service sau.
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties

# Cố ý khai cùng key để chứng minh import thắng file gốc.
lab.import.mode=from-application

# Marker chỉ có trong file khai báo import.
lab.import.application-marker=loaded
```

Có hai loại dữ liệu:

- Khóa `lab.import.mode` là **key xung đột** để quan sát precedence.
- Khóa `lab.import.application-marker` là **marker** để xác nhận file gốc thực sự đã được nạp.

Nếu chỉ có xung đột nhưng không có marker, một assertion về giá trị cuối chưa chứng minh tất cả file đã tham gia.

### Vì sao dùng prefix `lab.import`?

Một prefix riêng giúp tránh bị các property vô tình có trong môi trường hệ thống ghi đè.

Không dùng khóa quá chung như:

```properties
mode=local
timeout=5s
```

trong bài thực hành lớn, vì tên chung dễ trùng với property từ thư viện hoặc cách cấu hình khác.

## 8. Tệp dùng chung: `shared.properties`

Tạo:

`src/main/resources/config/shared.properties`

```properties
# Giá trị mặc định dùng chung.
lab.import.mode=from-shared
lab.import.timeout=10s
lab.import.retry-count=2
lab.import.enabled=true

# Marker chỉ có trong shared.
lab.import.shared-marker=loaded

# Một đường dẫn mặc định có thể được service thay đổi.
lab.import.base-url=https://shared.example.test/api
```

Ý nghĩa:

| Key | Mục đích |
| --- | --- |
| `lab.import.mode` | Key được khai trùng ở cả ba tài liệu để chứng minh ghi đè |
| `lab.import.timeout` | Default thời gian chờ, sẽ bị service override |
| `lab.import.retry-count` | Default chung, service có thể giữ nguyên |
| `lab.import.enabled` | Cờ chung |
| `lab.import.shared-marker` | Bằng chứng shared file đã được nạp |
| `lab.import.base-url` | Một giá trị có thể khác theo môi trường |

Tên miền `.example.test` trong ví dụ là placeholder để minh họa, không phải API thật.

## 9. Tệp riêng dịch vụ: `service.properties`

Tạo:

`src/main/resources/config/service.properties`

```properties
# Giá trị này sẽ thắng shared và application.
lab.import.mode=from-service

# Service cần timeout thấp hơn default chung.
lab.import.timeout=3s

# Giữ nguyên retry-count=2 từ shared vì không khai lại.
lab.import.owner=orders-service
lab.import.service-marker=loaded
```

Từ ba tệp, ta có các giá trị dự kiến:

| Key | `application.properties` | `shared.properties` | `service.properties` | Giá trị cuối dự kiến |
| --- | --- | --- | --- | --- |
| `lab.import.mode` | `from-application` | `from-shared` | `from-service` | `from-service` |
| `lab.import.timeout` | — | `10s` | `3s` | `3s` |
| `lab.import.retry-count` | — | `2` | — | `2` |
| `lab.import.enabled` | — | `true` | — | `true` |
| `lab.import.owner` | — | — | `orders-service` | `orders-service` |
| `lab.import.application-marker` | `loaded` | — | — | `loaded` |
| `lab.import.shared-marker` | — | `loaded` | — | `loaded` |
| `lab.import.service-marker` | — | — | `loaded` | `loaded` |

**Bảng là dự kiến theo quy tắc Boot 3.3**, khi không có CLI, environment variable, system property, profile hoặc nguồn có ưu tiên cao hơn tác động tới những key này. Ở các bước sau, chúng ta kiểm chứng nó bằng `SpringApplication`.

## 10. Tệp theo profile: `service-prod.properties`

Tạo:

`src/main/resources/config/service-prod.properties`

```properties
# Config Data có thể xét profile-specific variant của imported file.
lab.import.mode=from-service-prod
lab.import.timeout=2s
lab.import.owner=orders-service-prod
```

Vì `application.properties` import:

```text
classpath:/config/service.properties
```

Spring Boot có thể xem xét biến thể:

```text
classpath:/config/service-prod.properties
```

khi profile `prod` hoạt động.

Khi không bật profile `prod`, giá trị mode từ `service.properties` là:

```text
from-service
```

Khi có profile `prod` và không có nguồn ưu tiên hơn:

```text
from-service-prod
```

**Tránh cho thêm `application-prod.properties` khai cùng key trong bài test đầu tiên**, vì khi đó sẽ có thêm một trục precedence làm khó xác định kết quả. Hãy cô lập mỗi thí nghiệm một quy tắc.

## 11. Model Java có kiểu bằng `@ConfigurationProperties`

Tạo:

`src/main/java/example/importlab/ImportSettings.java`

```java
package example.importlab;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab.import")
public record ImportSettings(
        String mode,
        Duration timeout,
        int retryCount,
        boolean enabled,
        String owner
) {
}
```

Spring Boot có thể liên kết:

```text
lab.import.retry-count -> retryCount
lab.import.timeout     -> Duration
```

Với file như trên, record có thể nhận:

```text
mode       = from-service
timeout    = PT3S
retryCount = 2
enabled    = true
owner      = orders-service
```

Cần đăng ký `ImportSettings` để runtime tạo bean cấu hình. Bài sử dụng `@EnableConfigurationProperties` nhằm tường minh.

### Không suy luận precedence chỉ từ typed bean

Nếu bean có `mode=from-service`, ta biết **kết quả binding**, nhưng chưa biết các nguồn khác có được nạp và bị ghi đè hay không. Vì vậy chúng ta cần kết hợp:

1. Marker ở mỗi file.
2. Giá trị sau `Environment#getProperty`.
3. Giá trị typed trong `ImportSettings`.

Ba phép quan sát đó trả lời ba câu hỏi hơi khác nhau.

## 12. Lớp ứng dụng đọc kết quả

Tạo:

`src/main/java/example/importlab/ImportLabApplication.java`

```java
package example.importlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(ImportSettings.class)
public class ImportLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportLabApplication.class, args);
    }

    @Bean
    ApplicationRunner displayResults(
            Environment environment,
            ImportSettings settings
    ) {
        return args -> {
            System.out.println("mode="
                    + environment.getProperty("lab.import.mode"));

            System.out.println("timeout="
                    + settings.timeout());

            System.out.println("retryCount="
                    + settings.retryCount());

            System.out.println("enabled="
                    + settings.enabled());

            System.out.println("owner="
                    + settings.owner());

            System.out.println("application-marker="
                    + environment.getProperty(
                            "lab.import.application-marker"));

            System.out.println("shared-marker="
                    + environment.getProperty(
                            "lab.import.shared-marker"));

            System.out.println("service-marker="
                    + environment.getProperty(
                            "lab.import.service-marker"));
        };
    }
}
```

`ApplicationRunner` chạy sau khi context đã khởi động. Đây là nơi thuận tiện để **quan sát** giá trị; các import đã được xử lý sớm hơn ở giai đoạn Config Data.

Không đưa password, API key hoặc toàn bộ `Environment` ra log thật. Bài chỉ in các giá trị mẫu không nhạy cảm.

## 13. Chạy thử trên máy phát triển

Với Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Với Gradle Wrapper:

```bash
./gradlew bootRun
```

Đầu ra từ `ApplicationRunner` dự kiến:

```text
mode=from-service
timeout=PT3S
retryCount=2
enabled=true
owner=orders-service
application-marker=loaded
shared-marker=loaded
service-marker=loaded
```

Điều quan trọng:

- Cả ba marker tồn tại ⇒ cả ba tệp đã tham gia.
- `mode=from-service` ⇒ import thứ hai thắng giá trị cùng key.
- `retryCount=2` ⇒ key không bị override vẫn giữ từ shared.
- `timeout=PT3S` ⇒ Binder đã chuyển chuỗi `3s` thành `Duration.ofSeconds(3)`.

Nếu đầu ra khác, cần xem profile, CLI, system properties, env variables hoặc cấu hình khác đang hoạt động. Không kết luận ngay rằng tài liệu Spring Boot sai.

## 14. Thử thay đổi thứ tự hai import

Giữ nguyên cả ba file, chỉ đổi trong `application.properties`:

Ban đầu:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Đảo lại:

```properties
spring.config.import=classpath:/config/service.properties,classpath:/config/shared.properties
```

Với các key trùng, **shared đứng sau** nên có thể thắng service:

```text
lab.import.mode=from-shared
lab.import.timeout=10s
```

Trong khi:

```text
lab.import.owner=orders-service
```

vẫn có mặt vì shared không khai trùng key này.

Đây là bài thực nghiệm đủ nhỏ để nhìn thấy sự thay đổi precedence mà **không đổi giá trị** trong bất kỳ file con nào.

### Bài học rút ra

Tên file `shared` không tự có ưu tiên thấp hơn tên `service`. Thứ tự trong danh sách import mới là dữ liệu điều khiển precedence trong tình huống này.

Tuy nhiên, trong một dự án lớn còn nhiều nguồn Config Data khác, kết quả cuối có thể chịu ảnh hưởng bởi profile và location groups. Bài thực hành dùng bộ dữ liệu cô lập để kiểm tra một quy tắc tại một thời điểm.

## 15. Đổi vị trí dòng import trong `application.properties` không làm đổi precedence

So sánh cách A:

```properties
spring.config.import=classpath:/config/shared.properties
lab.import.mode=from-application
```

và cách B:

```properties
lab.import.mode=from-application
spring.config.import=classpath:/config/shared.properties
```

Với cùng một **document**, hai cách đều cho phép tệp import ghi đè key `lab.import.mode`.

Đừng nhầm hai khái niệm:

- **Vị trí dòng trong một tài liệu:** không quyết định import thắng hay thua.
- **Thứ tự các location trong danh sách import:** có ý nghĩa khi các import có key trùng.

Với YAML nhiều document hoặc `.properties` nhiều document, thứ tự **giữa các document** lại là một quy tắc khác; không nên lấy ví dụ một document đơn để suy ra toàn bộ multi-document behavior.

## 16. Tại sao tệp dùng chung không nên được import sau cùng?

Một cấu trúc không phù hợp khi muốn có service overrides:

```properties
spring.config.import=classpath:/config/service.properties,classpath:/config/shared.properties
```

Ở đây, shared có thể ghi đè các key của service nếu cả hai khai cùng tên.

Nếu mục tiêu nghiệp vụ là:

```text
Giá trị riêng dịch vụ > Giá trị dùng chung
```

thì chọn:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

và ghi rõ quy ước trong README của repository:

> Các import ở bên phải được dùng cho override có ưu tiên cao hơn khi khai trùng property.

Nếu có nhiều lớp:

```text
defaults → organization → service → environment
```

có thể dùng danh sách import tương ứng, miễn là bạn hiểu các nguồn khác bên ngoài chuỗi này và đã kiểm chứng bằng test.

Không nên tạo một chuỗi import quá dài mà không có ownership. Từng file cần một mục đích rõ ràng và chính sách ghi đè được đội phát triển chấp nhận.

## 17. Import cố định: `classpath:` và `file:`

Một location:

```properties
spring.config.import=classpath:/config/shared.properties
```

là **fixed location**. Nó được giải quyết trong classpath, không phụ thuộc vị trí file `application.properties` đang khai báo import theo cách import-relative.

Một location khác:

```properties
spring.config.import=file:/opt/app/config/shared.properties
```

trỏ tới file trên filesystem theo đường dẫn cụ thể.

Trên Windows, tránh tự ghép những dấu `\` theo cách khiến URI sai. Khi viết test Java, nên dùng:

```java
path.toUri().toString()
```

để tạo URI hợp lệ từ `Path`.

Một file ngoài JAR có thể phù hợp khi:

- Cùng một artifact chạy ở nhiều môi trường.
- Người vận hành cung cấp cấu hình qua volume.
- Muốn thay đổi cấu hình mà không rebuild JAR.
- Giá trị riêng môi trường không nên đóng cứng vào code.

Lưu ý: thay file trên disk **không có nghĩa** Spring Boot core tự động nạp lại toàn bộ config data sau startup. Thường cần khởi động lại hoặc một cơ chế refresh được thiết kế riêng.

## 18. Import tương đối: `shared.properties`

Nếu file khai báo import nằm ở:

```text
/opt/app/config/application.properties
```

và có:

```properties
spring.config.import=shared.properties
```

thì đây là **import-relative location**: nó được giải quyết tương đối với file đã khai báo.

Nếu file đó nằm ở:

```text
/opt/app/config/shared.properties
```

nó có thể được tìm thấy mà không cần ghi đường dẫn tuyệt đối.

Với import lồng nhau:

```text
/opt/app/config/
  application.properties
  common/shared.properties
  common/extra/labels.properties
```

`application.properties`:

```properties
spring.config.import=common/shared.properties
```

`common/shared.properties`:

```properties
spring.config.import=extra/labels.properties
```

Import thứ hai được giải quyết tương đối với:

```text
/opt/app/config/common/shared.properties
```

không phải mặc nhiên tương đối với working directory của terminal.

### `optional:` không làm đổi loại location

Ví dụ:

```properties
spring.config.import=optional:shared.properties
```

vẫn là **import-relative** location, chỉ khác ở cách xử lý khi resource không tồn tại.

Trong khi:

```properties
spring.config.import=optional:file:./shared.properties
```

là **fixed** location có tiền tố `file:`, và đường dẫn tương đối của filesystem chịu ảnh hưởng working directory khi được giải quyết.

Chữ `optional:` không biến một import thành fixed location.

## 19. Mô hình tệp dùng chung giữa nhiều service

Giả sử có hai ứng dụng `orders` và `billing` dùng cùng một chuẩn mặc định.

Một cách tổ chức trong monorepo:

```text
configuration-bundle/
  shared.properties

orders-service/
  src/main/resources/
    application.properties
    config/orders.properties

billing-service/
  src/main/resources/
    application.properties
    config/billing.properties
```

Đây là tổ chức nguồn. Để `classpath:/config/shared.properties` hoạt động, build cần **đóng gói hoặc đưa shared resource vào classpath của từng ứng dụng**, ví dụ thông qua thư viện resources dùng chung.

**Không thể** chỉ vì file nằm trong cùng monorepo mà `classpath:` của JAR `orders` sẽ tự tìm được file bên ngoài classpath.

Một hướng khác là deploy một volume chung:

```text
/etc/company/config/shared.properties
```

Rồi mỗi ứng dụng import:

```properties
spring.config.import=optional:file:/etc/company/config/shared.properties,classpath:/config/orders.properties
```

Trong mô hình này, việc cấu hình giá trị nào được phép override cần dựa vào contract rõ ràng; không biến đường dẫn dùng chung thành một file chứa secrets cho toàn công ty rồi expose rộng.

### Ưu tiên tách lớp

Một quy ước có thể là:

```text
shared defaults
    ↓
service defaults
    ↓
environment-specific runtime config
    ↓
operator's CLI override
```

Nhưng thứ tự thực tế phải được tạo bằng các cơ chế Spring Boot phù hợp và kiểm thử; đừng tưởng mỗi mũi tên trong tài liệu tự được framework hiểu nếu chưa khai đúng location, profile và precedence.

## 20. `optional:` cho import dùng chung khi deploy không có file

Một ứng dụng đóng gói có thể chạy local mà chưa mount file chung:

```properties
spring.config.import=optional:file:./config/company.properties
```

Nếu file thiếu, Spring Boot có thể bỏ qua import và tiếp tục startup.

Nếu bỏ `optional:`:

```properties
spring.config.import=file:./config/company.properties
```

mà file thiếu, startup có thể thất bại do resource/location không tồn tại.

Chọn theo ý nghĩa nghiệp vụ:

- **File bắt buộc:** thiếu phải fail-fast.
- **File tùy chọn:** thiếu được chấp nhận, vì luôn có fallback phù hợp.
- **Secret bắt buộc:** thiếu không nên bị biến thành im lặng rồi ứng dụng chạy với credential mặc định không an toàn.

`optional:` **không phải** “bỏ qua tất cả lỗi”. Một file tồn tại nhưng lỗi YAML, nhập sai kiểu hoặc binding validation fail vẫn có thể khiến startup lỗi.

### Đừng dùng optional để che cấu hình production bắt buộc

Nếu ứng dụng không thể hoạt động an toàn khi thiếu `company.properties`, hãy giữ import bắt buộc hoặc khai validation phù hợp. Một bootstrap thành công với giá trị sai có thể nguy hiểm hơn một startup failure rõ ràng.

## 21. `spring.config.import` trong YAML

Nếu ứng dụng dùng YAML nhất quán, có thể viết:

`application.yaml`:

```yaml
spring:
  application:
    name: config-import-lab
  config:
    import:
      - classpath:/config/shared.yaml
      - classpath:/config/service.yaml

lab:
  import:
    mode: from-application
```

`config/shared.yaml`:

```yaml
lab:
  import:
    mode: from-shared
    timeout: 10s
    retry-count: 2
```

`config/service.yaml`:

```yaml
lab:
  import:
    mode: from-service
    timeout: 3s
```

Dạng danh sách biểu đạt thứ tự import.

Một file `.properties` có thể import YAML và ngược lại, miễn tài nguyên và location được Spring Boot hỗ trợ. Tuy nhiên, nhóm phát triển nên ưu tiên một style nhất quán để giảm nhầm lẫn.

Khi có cả `.properties` và YAML với cùng basename trong cùng location, Spring Boot 3.3 có quy tắc precedence riêng; không nên trộn hai format trùng tên mà không kiểm thử.

## 22. Profile-specific import

Tệp `service.properties` có thể có biến thể:

```text
service-dev.properties
service-prod.properties
```

Khi import:

```properties
spring.config.import=classpath:/config/service.properties
```

và bật profile `prod`, Spring Boot có thể xét:

```text
classpath:/config/service-prod.properties
```

Ví dụ:

`service.properties`:

```properties
lab.import.mode=from-service
lab.import.timeout=3s
```

`service-prod.properties`:

```properties
lab.import.mode=from-service-prod
lab.import.timeout=2s
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Đầu ra mong đợi của ví dụ cô lập:

```text
mode=from-service-prod
timeout=PT2S
```

Nếu CLI còn có:

```text
--lab.import.timeout=750ms
```

CLI có thể thắng giá trị `2s`, vì đây là một nguồn ưu tiên cao hơn Config Data trong cấu hình Boot mặc định.

### Phân biệt hai loại profile document

- `application-prod.properties` là một **tệp profile-specific của ứng dụng** được xét trong quá trình tìm Config Data.
- `service-prod.properties` là **profile-specific variant của tệp được import**.

Chúng cùng liên quan profile nhưng không nên tùy tiện mặc định tất cả tài liệu của chúng có cùng vị trí precedence trong mọi tổ hợp import/location. Khi thiết kế phức tạp, hãy viết test riêng cho đúng sơ đồ file của dự án.

## 23. Nhiều import không đồng nghĩa nhiều lần nạp cùng tài nguyên

Một cấu hình có thể vô tình khai lặp:

```properties
spring.config.import=shared.properties,shared.properties
```

Theo tài liệu Spring Boot 3.3, một import được nạp **một lần**, dù được khai báo nhiều lần.

Tính chất này giúp tránh một số tình huống xử lý lặp, nhưng không nên cố dựa vào khai lặp để tăng thứ tự ưu tiên:

```text
shared,service,shared
```

không phải một giải pháp rõ ràng để đảm bảo shared thắng service. Với cùng tài nguyên, cơ chế de-duplication và cách các tài liệu được phát hiện có thể khiến suy luận “lần cuối thắng” không đúng mong đợi.

Quy ước tốt: **mỗi tài nguyên cần import một lần tại một vị trí được chủ ý chọn**. Nếu nhiều module muốn cùng dùng một file, nên thống nhất một nơi chịu trách nhiệm import hoặc kiểm chứng theo từng context.

### Không kiểm tra duplicate import bằng cách đọc một giá trị duy nhất

Nếu `lab.import.mode=shared`, việc đọc ra `shared` chưa chứng minh file chỉ được nạp một lần. Muốn điều tra số lần import, cần quan sát PropertySource hoặc instrumentation phù hợp và chấp nhận tên nguồn nội bộ có thể thay đổi. Trong bài học, tính chất de-duplication được nêu theo hợp đồng tài liệu; các bài test runtime tập trung precedence và presence.

## 24. Vì sao một “file shared mặc định” có thể ghi đè không mong muốn?

Ví dụ người phát triển viết:

`application.properties`:

```properties
lab.import.timeout=1s
spring.config.import=classpath:/config/shared.properties
```

`shared.properties`:

```properties
lab.import.timeout=10s
```

Sau startup, timeout có thể là `10s`, **không phải** `1s`, vì imported document có precedence hơn declaring document.

Nếu ý định là application có override cao hơn shared, có nhiều giải pháp:

1. Đưa giá trị riêng vào một **tệp import đứng sau shared**:

   ```properties
   spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
   ```

2. Đặt override trong nguồn runtime được thiết kế có precedence cao hơn, như CLI/environment (khi thích hợp).
3. Tổ chức lại các file theo vị trí Config Data phù hợp, rồi kiểm thử precedence cho từng trường hợp.

Không nên dựa vào cách xếp dòng trong file gốc:

```properties
spring.config.import=classpath:/config/shared.properties
lab.import.timeout=1s
```

Việc đưa `timeout` xuống dòng cuối **không** tạo một precedence override cho imported document.

## 25. Chuẩn bị bộ kiểm thử startup thật

Một bài test chỉ làm:

```java
new MapPropertySource("shared", ...)
```

rồi tự sắp xếp vào `StandardEnvironment` có thể kiểm tra luật ưu tiên do chính test dựng, **nhưng không chứng minh `spring.config.import` đã được Spring Boot xử lý đúng**.

Vì vậy dùng:

```java
SpringApplication.run(...)
```

để đi qua giai đoạn chuẩn bị Config Data thật.

Một test có thể:

1. Tạo directory tạm qua `@TempDir`.
2. Viết `application.properties`, `shared.properties`, `service.properties`.
3. Cấp `--spring.config.location=file:.../application.properties` trước startup.
4. Gọi `SpringApplication.run(...)`.
5. Đọc `context.getEnvironment()`.
6. Assert marker của từng file.
7. Assert một key trùng ở nhiều file để chứng minh precedence.
8. Assert bean cấu hình có kiểu nếu muốn kiểm tra Binder.
9. Đóng `ConfigurableApplicationContext` trong `try-with-resources`.

Không cần web server hoặc DB để kiểm thử những quy tắc này.

## 26. Tại sao test dùng `@TempDir`?

Nếu test sửa trực tiếp:

```text
src/main/resources/application.properties
```

nó có thể làm bẩn repository hoặc ảnh hưởng tới test khác. Nếu test phụ thuộc:

```text
./config/shared.properties
```

kết quả có thể thay đổi theo working directory của Gradle, Maven, IDE hoặc CI.

`@TempDir` tạo một directory tạm độc lập:

```java
@TempDir
Path temp;
```

Sau đó:

```java
Path root = temp.resolve("case-one/application.properties");
Files.createDirectories(root.getParent());
Files.writeString(root, "...", StandardCharsets.UTF_8);
```

Và dùng:

```java
root.toUri()
```

để nhận một file URI phù hợp với hệ điều hành hiện tại.

Hãy truyền nó qua:

```java
"--spring.config.location=" + root.toUri()
```

thay vì tự xây chuỗi `file:` bằng cách nối `Path.toString()` với dấu `/` hoặc `\`.

## 27. Test class tối thiểu

Ví dụ bên dưới dùng JUnit Jupiter, AssertJ và một class Spring Boot tối thiểu.

`src/test/java/example/importlab/ImportPrecedenceTest.java`:

```java
package example.importlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;

class ImportPrecedenceTest {

    @TempDir
    Path temp;

    @ConfigurationProperties(prefix = "lab.import")
    record TestSettings(
            String mode,
            Duration timeout,
            int retryCount,
            boolean enabled,
            String owner
    ) {
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TestSettings.class)
    static class MinimalApp {
    }

    static Path write(Path file, String text)
            throws IOException {
        Files.createDirectories(file.getParent());
        Files.writeString(file, text, StandardCharsets.UTF_8);
        return file;
    }

    static ConfigurableApplicationContext start(
            Path applicationFile,
            String... overrides
    ) {
        SpringApplication app =
                new SpringApplication(MinimalApp.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        List<String> arguments = new ArrayList<>();
        arguments.add("--spring.config.location="
                + applicationFile.toUri());

        arguments.addAll(Arrays.asList(overrides));

        return app.run(arguments.toArray(new String[0]));
    }

    // Các phương thức @Test ở các mục tiếp theo
    // được đặt trong cùng class này.
}
```

### Vì sao không dùng `@SpringBootTest` trong từng test?

`@SpringBootTest` phù hợp với nhiều bài kiểm thử tích hợp khác. Nhưng trong bài này mỗi phép thử muốn **tự chọn location/import của một startup** và quan sát kết quả. `SpringApplication.run` giúp biểu đạt điều đó trực tiếp.

### Giới hạn của helper

Helper đặt `spring.config.location` trỏ tới **một file cụ thể**, nên nó **thay thế các default search locations**. Điều này làm các test tập trung vào bộ file tạm.

Nhờ vậy, `src/main/resources/application.properties` của ứng dụng demo không vô tình ảnh hưởng những test kiểm chứng thứ tự import.

## 28. Test A — imported file được nạp và thắng declaring file

Tạo tệp:

```text
test-a/
  application.properties
  shared.properties
```

Trong test:

```java
@Test
void importedDocumentOverridesDeclaringDocument()
        throws IOException {

    Path dir = temp.resolve("test-a");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab.import.mode=from-application\n"
            + "lab.import.application-marker=loaded\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.shared-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-shared");

        assertThat(env.getProperty(
                "lab.import.application-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.shared-marker"))
                .isEqualTo("loaded");
    }
}
```

Kết quả:

```text
application-marker=loaded
shared-marker=loaded
mode=from-shared
```

**Bằng chứng số 1:** marker của application và shared tồn tại ⇒ cả hai file đã được nạp.

**Bằng chứng số 2:** key `mode` được khai ở hai file và kết quả là `from-shared` ⇒ imported document thắng declaring document trong trường hợp này.

Nếu chỉ assert mode, test vẫn có thể pass do một nguồn ngoài ý muốn cung cấp `from-shared`. Marker và prefix test riêng giúp giảm rủi ro kết luận sai.

## 29. Test B — shared trước, service sau

Tiếp tục trong cùng test class, thêm method:

```java
@Test
void laterServiceImportOverridesSharedAndParent()
        throws IOException {

    Path dir = temp.resolve("test-b");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties,service.properties\n"
            + "lab.import.mode=from-application\n"
            + "lab.import.application-marker=loaded\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.timeout=10s\n"
            + "lab.import.retry-count=2\n"
            + "lab.import.enabled=true\n"
            + "lab.import.shared-marker=loaded\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
            + "lab.import.owner=orders-service\n"
            + "lab.import.service-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-service");

        assertThat(env.getProperty(
                "lab.import.application-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.shared-marker"))
                .isEqualTo("loaded");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");

        TestSettings settings = context.getBean(
                TestSettings.class);

        assertThat(settings.mode())
                .isEqualTo("from-service");

        assertThat(settings.timeout())
                .isEqualTo(Duration.ofSeconds(3));

        assertThat(settings.retryCount()).isEqualTo(2);
        assertThat(settings.enabled()).isTrue();
        assertThat(settings.owner())
                .isEqualTo("orders-service");
    }
}
```

Test này chứng minh cả hai tầng:

```text
Config Data import -> Spring Environment
Spring Environment -> @ConfigurationProperties Binder
```

`mode=from-service` là kết quả của **precedence giữa các import**.

`retryCount=2` chứng minh một key chỉ có trong shared không biến mất vì service file được nạp sau.

`Duration.ofSeconds(3)` chứng minh Binder có thể chuyển `3s` thành `Duration`, không chỉ giữ nguyên một chuỗi.

## 30. Test C — đảo thứ tự import làm đổi kết quả

Dùng cùng nội dung các file nhưng đảo danh sách:

```java
@Test
void reversingImportOrderMakesSharedWin()
        throws IOException {

    Path dir = temp.resolve("test-c");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=service.properties,shared.properties\n"
            + "lab.import.mode=from-application\n"
    );

    write(
            dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n"
            + "lab.import.timeout=10s\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
            + "lab.import.service-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-shared");

        assertThat(env.getProperty("lab.import.timeout"))
                .isEqualTo("10s");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");
    }
}
```

Kết quả:

```text
mode=from-shared
timeout=10s
service-marker=loaded
```

Cả shared và service vẫn được nạp. **Chỉ thay đổi thứ tự import** nhưng key trùng có giá trị cuối khác. Đây là bằng chứng trực tiếp về precedence.

Nếu nhóm muốn service overrides, test C chính là một trường hợp minh họa **không nên** dùng thứ tự này trong cấu hình ứng dụng thật.

## 31. Test D — dòng import ở đầu hay cuối file đều giống nhau

Đây là một kiểm thử mang ý nghĩa khác với test C.

Chuẩn bị hai directory:

```text
test-d/first/
  application.properties
  shared.properties

test-d/last/
  application.properties
  shared.properties
```

File A:

```properties
spring.config.import=shared.properties
lab.import.mode=from-root
```

File B:

```properties
lab.import.mode=from-root
spring.config.import=shared.properties
```

Cả hai thư mục có:

```properties
lab.import.mode=from-shared
```

Test:

```java
@Test
void positionOfImportLineDoesNotChangePrecedence()
        throws IOException {

    Path firstDir = temp.resolve("test-d/first");
    Path lastDir = temp.resolve("test-d/last");

    Path first = write(
            firstDir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab.import.mode=from-root\n"
    );

    Path last = write(
            lastDir.resolve("application.properties"),
            "lab.import.mode=from-root\n"
            + "spring.config.import=shared.properties\n"
    );

    write(firstDir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    write(lastDir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    try (ConfigurableApplicationContext firstContext =
                 start(first)) {
        assertThat(firstContext.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-shared");
    }

    try (ConfigurableApplicationContext lastContext =
                 start(last)) {
        assertThat(lastContext.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-shared");
    }
}
```

**Điều được chứng minh:** vị trí dòng `spring.config.import` trong cùng một document không làm thay đổi tính ưu tiên imported document so với declaring document.

**Điều không được chứng minh:** mọi thứ tự giữa nhiều tài liệu YAML/properties luôn giống nhau. Multi-document configuration có quy tắc riêng.

## 32. Test E — command-line argument thắng các file import

Tệp:

`application.properties`:

```properties
spring.config.import=shared.properties,service.properties
lab.import.mode=from-root
```

`shared.properties`:

```properties
lab.import.mode=from-shared
```

`service.properties`:

```properties
lab.import.mode=from-service
```

Chạy:

```java
@Test
void commandLinePropertyOverridesAllImportedFiles()
        throws IOException {

    Path dir = temp.resolve("test-e");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties,service.properties\n"
            + "lab.import.mode=from-root\n"
    );

    write(dir.resolve("shared.properties"),
            "lab.import.mode=from-shared\n");

    write(dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.service-marker=loaded\n");

    try (ConfigurableApplicationContext context = start(
            root,
            "--lab.import.mode=from-cli"
    )) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-cli");

        assertThat(env.getProperty(
                "lab.import.service-marker"))
                .isEqualTo("loaded");
    }
}
```

Kết quả:

```text
service-marker=loaded
mode=from-cli
```

Marker cho biết service import vẫn được nạp. Giá trị cuối từ CLI cho biết **CLI source có ưu tiên cao hơn Config Data** trong cấu hình mặc định.

### Gợi ý về `SpringApplication.setAddCommandLineProperties(false)`

Nếu ứng dụng chủ động gọi:

```java
application.setAddCommandLineProperties(false);
```

thì `--lab.import.mode=from-cli` không còn được tự động thêm làm property source theo cách mặc định. Bài test không thay đổi cấu hình này.

Vì vậy luôn phân biệt quy tắc **SpringApplication mặc định** với những ứng dụng đã tùy biến cách xử lý command-line args.

## 33. Test F — profile-specific variant của import

Dùng directory:

```text
test-f/
  application.properties
  service.properties
  service-prod.properties
```

```java
@Test
void profileSpecificVariantOfImportCanOverrideBase()
        throws IOException {

    Path dir = temp.resolve("test-f");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=service.properties\n"
    );

    write(
            dir.resolve("service.properties"),
            "lab.import.mode=from-service\n"
            + "lab.import.timeout=3s\n"
    );

    write(
            dir.resolve("service-prod.properties"),
            "lab.import.mode=from-service-prod\n"
            + "lab.import.timeout=2s\n"
    );

    try (ConfigurableApplicationContext context = start(
            root,
            "--spring.profiles.active=prod"
    )) {
        assertThat(context.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("from-service-prod");

        assertThat(context.getEnvironment()
                .getProperty("lab.import.timeout"))
                .isEqualTo("2s");
    }
}
```

Bằng chứng: Boot xét biến thể theo profile cho imported resource, chứ không chỉ đọc đúng một file `service.properties` bằng một API file đơn giản.

### Khi nào tránh kết luận quá rộng?

Nếu thêm các location khác hoặc nhiều active profiles như `prod,live`, precedence còn phụ thuộc **location groups và vị trí các tài liệu**. Test F chỉ chứng minh kịch bản cô lập một import với một profile.

## 34. Test G — import tương đối lồng nhau

Bộ file:

```text
test-g/
  application.properties
  common/
    shared.properties
    extra/
      feature.properties
```

`application.properties`:

```properties
spring.config.import=common/shared.properties
```

`common/shared.properties`:

```properties
spring.config.import=extra/feature.properties
lab.import.mode=from-shared
```

`common/extra/feature.properties`:

```properties
lab.import.mode=from-nested
lab.import.nested-marker=loaded
```

Test:

```java
@Test
void nestedImportResolvesRelativeToDeclaringFile()
        throws IOException {

    Path dir = temp.resolve("test-g");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=common/shared.properties\n"
    );

    write(
            dir.resolve("common/shared.properties"),
            "spring.config.import=extra/feature.properties\n"
            + "lab.import.mode=from-shared\n"
    );

    write(
            dir.resolve("common/extra/feature.properties"),
            "lab.import.mode=from-nested\n"
            + "lab.import.nested-marker=loaded\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        var env = context.getEnvironment();

        assertThat(env.getProperty("lab.import.mode"))
                .isEqualTo("from-nested");

        assertThat(env.getProperty(
                "lab.import.nested-marker"))
                .isEqualTo("loaded");
    }
}
```

Bài test có ý nghĩa vì nếu import thứ hai bị giải quyết nhầm tương đối với `application.properties` thay vì `common/shared.properties`, ứng dụng sẽ không tìm thấy:

```text
common/extra/feature.properties
```

Từ kết quả `nested-marker=loaded` có thể thấy file lồng đúng vị trí đã được nạp.

## 35. Test H — optional import thiếu vẫn chạy

Tạo:

`application.properties`:

```properties
spring.config.import=optional:missing.properties
lab.import.mode=fallback
```

Test:

```java
@Test
void optionalMissingImportStillAllowsStartup()
        throws IOException {

    Path dir = temp.resolve("test-h");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=optional:missing.properties\n"
            + "lab.import.mode=fallback\n"
    );

    try (ConfigurableApplicationContext context = start(root)) {
        assertThat(context.getEnvironment()
                .getProperty("lab.import.mode"))
                .isEqualTo("fallback");
    }
}
```

Điều được chứng minh: một **location được đánh dấu optional** không có file tương ứng không nhất thiết làm startup fail.

Không dùng ví dụ này để khẳng định mọi lỗi parser và binding sẽ được bỏ qua chỉ cần có `optional:`.

## 36. Test I — thiếu import bắt buộc gây startup failure

Không có `optional:`:

```properties
spring.config.import=missing.properties
```

Test:

```java
@Test
void requiredMissingImportFailsStartup()
        throws IOException {

    Path dir = temp.resolve("test-i");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=missing.properties\n"
            + "lab.import.mode=fallback\n"
    );

    assertThatThrownBy(() -> start(root))
            .isInstanceOf(RuntimeException.class);
}
```

Assertion trên chỉ nhằm chứng minh ứng dụng **không thể khởi động thành công**. Nếu dự án cần kiểm tra đúng loại lỗi, có thể kiểm tra exception chain chứa lỗi Config Data location/resource not found theo phiên bản Boot đang dùng.

Không nên buộc test so sánh nguyên văn toàn bộ exception message: đường dẫn tạm, OS và cách trình bày của Spring Boot có thể khác nhau giữa các bản patch.

### Lưu ý tài nguyên kiểm thử

Một project khác có thể đặt `missing.properties` ở classpath hoặc vị trí mà test vô tình nhìn thấy. Prefix và đường dẫn test nên đủ riêng để tránh trùng với tài nguyên thực của dự án.

## 37. Dùng `@TempDir` thay cho kiểm thử bằng tên `PropertySource` nội bộ

Một cách debug:

```java
for (PropertySource<?> source :
        context.getEnvironment().getPropertySources()) {
    System.out.println(source.getName());
}
```

Nhưng điều này đòi hỏi `ConfigurableEnvironment`. Trong test helper, bạn có thể:

```java
ConfigurableEnvironment environment =
        context.getEnvironment();

for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

Imports:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

Tên nguồn thường thể hiện Config Data resource, nhưng format tên có thể thay đổi theo phiên bản Boot hoặc đường dẫn thực tế.

**Không nên** tạo test chỉ pass nếu source name trùng chính xác một chuỗi dài như:

```text
Config resource 'file [...]' via location '...'
```

Một marker property unique trong mỗi file là bằng chứng ổn định hơn cho mục tiêu “file nào được nạp”.

### Tránh in toàn bộ nội dung PropertySource

Dữ liệu runtime có thể chứa secrets. Chỉ in **tên nguồn** hoặc vài key không nhạy cảm khi debug cục bộ; không xuất toàn bộ map, môi trường hay mật khẩu ra CI logs.

## 38. Thực hành thêm: file dùng chung ngoài JAR

Một tình huống deploy:

```text
workspace/
  app.jar
  config/
    shared.properties
```

Ứng dụng có thể import:

```properties
spring.config.import=optional:file:./config/shared.properties
```

Vì đây là file-relative location tính theo process working directory, hãy kiểm tra working directory thật khi chạy.

Một cách ổn định hơn trong môi trường có đường dẫn cố định là:

```properties
spring.config.import=file:/etc/myapp/shared.properties
```

hoặc dùng một biến/placeholder thích hợp được định nghĩa đủ sớm theo chính sách triển khai.

### Kết hợp file package và file ngoài

Có thể muốn:

```properties
spring.config.import=classpath:/config/shared.properties,optional:file:./config/service-overrides.properties
```

Với file ngoài đứng sau, một key trùng có thể lấy từ file ngoài nếu có. Nếu file ngoài thiếu, file classpath vẫn cung cấp giá trị mặc định.

Kiểm chứng bằng:

1. Chạy một lần **không có** file external.
2. Chạy một lần **có** file external chứa cùng key.
3. Assert marker file ngoài xuất hiện đúng lần có file.
4. Assert key trùng đổi theo precedence.

Đừng chỉ kiểm tra một lần có file; kiểm thử cả đường fallback khi không có file cũng quan trọng.

## 39. Vị trí file, `spring.config.location` và `spring.config.additional-location`

Ba cơ chế dễ bị nhầm:

| Cơ chế | Mục đích |
| --- | --- |
| `spring.config.import` | Một document chỉ ra các location bổ sung cần import |
| `spring.config.location` | **Thay thế** default search locations |
| `spring.config.additional-location` | **Bổ sung** locations bên cạnh default search locations |

Ví dụ:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties
```

đọc location tường minh, thay các default locations.

Với:

```bash
java -jar app.jar \
  --spring.config.additional-location=file:./config/
```

Boot giữ default search locations và bổ sung directory.

Không nên coi `spring.config.import` như một cách viết khác của `additional-location`. Import **gắn với một document**, có import-relative semantics và quy tắc ghi đè riêng. Additional location tham gia search locations ở cấp cấu hình ứng dụng.

### Vì sao test dùng location tường minh?

Trong JUnit, helper truyền:

```java
"--spring.config.location=" + root.toUri()
```

để cố ý chỉ dùng bộ file tạm. Đây là **chiến lược cô lập test**, không phải khuyến nghị mọi ứng dụng production phải dùng `spring.config.location`.

## 40. Đừng áp dụng nhầm nguyên tắc “dòng cuối thắng” của `.properties`

Một file `.properties` có thể có trường hợp cùng key xuất hiện lặp trong **chính một tài liệu**; parser xử lý duplicate keys theo hành vi tương ứng, nhưng không nên dựa vào đó để xây chính sách.

Thứ tự giữa **các file Config Data** và **thứ tự dòng trong một file** là hai việc khác nhau.

Sai lầm thường gặp:

```properties
spring.config.import=shared.properties
lab.import.mode=from-application
```

rồi nói:

> Vì `lab.import.mode` nằm ở cuối file nên nó thắng shared.

Quy tắc của Spring Boot về imported document khiến kết luận này sai.

Thay vì duplicate cùng key trong một file, hãy đặt từng giá trị vào đúng tầng:

```text
shared.properties  -> fallback chung
service.properties -> override của dịch vụ
runtime CLI/env    -> override deployment
```

Khi cần nhiều tài liệu trong cùng file, dùng đúng cú pháp multi-document properties hoặc YAML và kiểm tra activation/precedence của từng document.

## 41. Thử lỗi cố ý: import path sai

Giả sử:

```properties
spring.config.import=classpath:/configs/shared.properties
```

nhưng file thật:

```text
src/main/resources/config/shared.properties
```

khác ở `configs` và `config`.

Khi thiếu tài nguyên bắt buộc, Spring Boot có thể fail startup trước khi bean ứng dụng được tạo.

Cách chẩn đoán:

1. Đọc nguyên văn `spring.config.import`.
2. Xác định đây là fixed hay relative location.
3. Kiểm tra đúng đường dẫn và extension.
4. Kiểm tra tài nguyên đã được copy vào build output/JAR chưa.
5. Kiểm tra Gradle/Maven resource filtering có làm đổi file không.
6. Kiểm tra profile-specific file có hay không.
7. Đừng tự thêm `optional:` chỉ để che lỗi đánh máy nếu file là bắt buộc.

Với JAR, có thể xem nội dung bằng:

```bash
jar tf path/to/app.jar
```

Spring Boot executable JAR có thể mang resources dưới `BOOT-INF/classes`, khác JAR thư viện thường. Vì vậy tìm tên resource trong archive thay vì giả định mọi JAR có cấu trúc giống nhau.

## 42. Một lỗi khác: file ngoài bị file khác ghi đè

Bạn thấy:

```properties
# service.properties
lab.import.timeout=3s
```

nhưng ứng dụng nhận:

```text
lab.import.timeout=1s
```

Điều này có thể hợp lệ nếu runtime có:

```bash
java -jar app.jar --lab.import.timeout=1s
```

Hoặc Java system property:

```bash
java -Dlab.import.timeout=1s -jar app.jar
```

Hoặc biến môi trường:

```text
LAB_IMPORT_TIMEOUT=1s
```

Trong Spring Boot 3.3 thông thường, CLI có ưu tiên cao hơn Config Data, nên việc thấy timeout `1s` không chứng minh import bị lỗi.

Khi điều tra, cần tách:

```text
A. File đã được nạp?   -> marker
B. File nào thắng trong Config Data? -> key xung đột + test cô lập
C. Nguồn nào thắng toàn hệ thống?     -> Environment / PropertySources
D. Bean đã bind giá trị nào?         -> @ConfigurationProperties
```

Không dùng một nguồn bằng chứng duy nhất để kết luận cả bốn câu hỏi.

## 43. Placeholder trong file dùng chung

Một file:

```properties
lab.import.base-url=https://shared.example.test/api
```

có thể được file service tham chiếu:

```properties
lab.import.health-url=${lab.import.base-url}/health
```

Khi `Environment` resolve placeholder, nó có thể lấy giá trị có hiệu lực của `lab.import.base-url` theo các nguồn hiện tại.

Nếu CLI override:

```text
--lab.import.base-url=https://deploy.example.test/api
```

thì giá trị của `lab.import.health-url` có thể đổi khi được resolve.

### Hãy phân biệt hai nguồn

- Tài liệu **khai báo** `lab.import.health-url`.
- Nguồn **cung cấp giá trị** cho `${lab.import.base-url}`.

Một origin chỉ tới `service.properties` chưa mô tả toàn bộ nguồn của nội dung đã resolve. Khi config phức tạp, cần kiểm tra cả key tham chiếu.

### Placeholder có default

```properties
lab.import.health-url=${lab.import.base-url:https://local.example.test}/health
```

Đây là cú pháp default của placeholder; không phải một `spring.config.import` thứ hai. Không nhầm `:` bên trong `${...}` với phần URI của Config Data location.

## 44. Khi nào nên tách quá nhiều file?

Tách file có lợi khi:

- Nhiều service thực sự chia sẻ một bộ default rõ ràng.
- Mỗi file có owner và mục đích cụ thể.
- Giá trị riêng service được thể hiện ở tầng override dễ dự đoán.
- Các môi trường triển khai có đầu vào khác nhau.
- Có test xác minh mối quan hệ precedence.

Nhưng tách quá nhiều file có thể gây:

- Import chain khó theo dõi.
- Trùng key ở nhiều tầng mà không ai biết.
- Người sửa nhầm file có ưu tiên thấp.
- Import vòng hoặc đường dẫn lồng phức tạp.
- Profile, location group và CLI override khó suy luận.
- Chênh lệch giữa local, CI, staging và production.

Nên tránh một kiến trúc nơi một property được khai ở mười file chỉ để “chắc chắn có giá trị”. Thay vào đó, xác định một nguồn default và một hoặc hai tầng override có chủ đích.

## 45. Bảng các tình huống precedence

| Kịch bản | Khai báo | Giá trị `lab.import.mode` nếu không có nguồn cao hơn |
| --- | --- | --- |
| Không import | Chỉ `application.properties=application` | `application` |
| Import một file | Root=`application`, shared=`shared` | `shared` |
| Import hai file | Root=`application`, shared=`shared`, service=`service`; import `shared,service` | `service` |
| Đảo hai import | Import `service,shared` | `shared` |
| Chuyển dòng import xuống cuối root | Import vẫn `shared` | `shared` |
| CLI ghi đè | Import `shared,service`, CLI=`cli` | `cli` |
| Profile variant | Import `service.properties`, active prod, variant=`prod` | `prod` |
| Import optional thiếu | Root=`fallback`, `optional:missing` | `fallback` |
| Import bắt buộc thiếu | `missing.properties` không tồn tại | Startup fail |
| Import lồng nhau | Root→shared→nested, các key cùng tên | Tùy thứ tự giữa các document, ví dụ nested thắng shared |

Dòng kết quả chỉ mô tả các kịch bản cô lập. Nếu thêm profile-specific external files, system properties, CLI, test overrides hay custom `EnvironmentPostProcessor`, giá trị cuối có thể khác.

## 46. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Shared file không được nạp | Sai đường dẫn classpath/extension | Kiểm tra resource path và JAR |
| Service override không thắng | Service đứng trước shared trong import list | Đổi thứ tự thành `shared,service` |
| Root property bị import ghi đè | Đúng hợp đồng precedence | Chuyển override sang import về sau hoặc nguồn phù hợp |
| Đổi vị trí dòng `spring.config.import` không đổi kết quả | Vị trí dòng trong cùng document không quyết định precedence | Kiểm tra thứ tự import list |
| `optional:` che mất file production | Đánh dấu tài nguyên bắt buộc thành tùy chọn | Chọn fail-fast và validation |
| Test chỉ pass trên máy developer | Relative filesystem path phụ thuộc working directory | Dùng `@TempDir` + `Path.toUri()` |
| Test pass dù file chưa được đọc | Chỉ assert key trùng có giá trị từ CLI | Thêm marker riêng cho file |
| File `application-prod.properties` làm kết quả khác | Profile-specific Config Data tham gia precedence | Kiểm tra active profiles và nguồn |
| Import lồng tìm sai directory | Nhầm import-relative với working directory | Xác định vị trí file khai báo |
| Đường dẫn `file:` không chạy trên Windows | Ghép URI thủ công sai | Dùng `Path.toUri()` trong Java test |
| Có cả YAML và properties trùng basename | Định dạng khác nhau có precedence khác | Ưu tiên một format, test nếu cần |
| Source báo thiếu location | File bắt buộc không tồn tại | Sửa path, chỉ dùng `optional:` nếu thật sự tùy chọn |
| CLI override không như kỳ vọng | Ứng dụng vô hiệu hóa command-line properties hoặc nguồn tùy chỉnh | Kiểm tra `SpringApplication` config |
| Typed bean nhận null dù Environment có key | Model/binding/registration không phù hợp | Kiểm tra `@EnableConfigurationProperties`/Binder |
| Key `retry-count` không bind như kỳ vọng | Tên env var không theo canonical rules | Kiểm tra `LAB_IMPORT_RETRYCOUNT` |
| `service-prod.properties` không có hiệu lực | Profile không active hoặc file ở sai nơi | Kiểm tra profile và URI import |
| Output thay đổi sau khi chuyển môi trường | OS env/system properties khác | So sánh nguồn thực tế |
| Đọc được key nhưng feature không hoạt động | Binding khác với business logic | Test behavior riêng |
| Đã chỉnh file nhưng app vẫn dùng cũ | Config Data thường được nạp tại startup | Restart hoặc cơ chế refresh có chủ đích |
| Log chứa nhiều secrets | Dump toàn bộ Environment/CLI | Log chỉ key mẫu, dùng sanitization |

## 47. Chẩn đoán bằng Actuator khi cần

Spring Boot Actuator có các endpoint hữu ích:

```text
/actuator/env
/actuator/configprops
/actuator/conditions
```

Chúng phục vụ các câu hỏi khác nhau:

- `/actuator/env`: PropertySources và giá trị/origin được báo cáo.
- `/actuator/configprops`: các bean `@ConfigurationProperties` đã bind.
- `/actuator/conditions`: kết quả điều kiện auto-configuration, **không phải** bản kê giá trị mọi property.

Nếu `lab.import.mode` không đúng, hãy ưu tiên `Environment`/`env` để xác định nguồn có hiệu lực.

Khi endpoint trả giá trị `******`, đó có thể là sanitization để bảo vệ dữ liệu nhạy cảm, không phải giá trị thật. Không bật `management.endpoint.env.show-values=always` trên môi trường công khai chỉ để nhìn thấy một key.

Đối với bộ test trong bài, bạn có thể **không cần Actuator**: `SpringApplication.run` và `Environment#getProperty` đủ để kiểm chứng quy tắc import trong môi trường cô lập.

## 48. Kiểm thử bằng Gradle và Maven trong CI

Chạy Maven:

```bash
./mvnw test
```

Chạy riêng class nếu Surefire được cấu hình phù hợp:

```bash
./mvnw -Dtest=ImportPrecedenceTest test
```

Gradle:

```bash
./gradlew test
```

Hoặc:

```bash
./gradlew test --tests example.importlab.ImportPrecedenceTest
```

Nếu `ImportPrecedenceTest` là test trong module con, cần chạy đúng module/project path.

### Tại sao các test nên nằm trong CI?

Một lần chỉnh:

```properties
spring.config.import=shared.properties,service.properties
```

thành:

```properties
spring.config.import=service.properties,shared.properties
```

có thể không làm chương trình compile fail. Nhưng nó làm thay đổi kết quả config.

Test B/C có thể phát hiện sự thay đổi một cách sớm hơn so với chờ ứng dụng production dùng sai timeout hoặc sai feature flag.

### Không dùng test phụ thuộc máy CI

Tránh hardcode:

```text
C:\Users\someone\Desktop\configs\shared.properties
```

hoặc:

```text
/home/developer/work/config/shared.properties
```

trong test. `@TempDir` và `Path.toUri()` là một cách để test chạy trên Windows, Linux, macOS và máy CI khác nhau.

## 49. Bài tập mở rộng 1 — ba cấp import

Thiết kế:

```text
shared.properties
organization.properties
service.properties
```

Giá trị:

```text
shared:       lab.import.timeout=15s
organization: lab.import.timeout=8s
service:      lab.import.timeout=3s
```

**Câu hỏi:** Nếu muốn service thắng, import list nên viết thế nào?

**Đáp án:**

```properties
spring.config.import=shared.properties,organization.properties,service.properties
```

Kết quả được kỳ vọng:

```text
lab.import.timeout=3s
```

**Bài thực hành:** viết một test tạo ba file bằng `@TempDir`, assert marker của từng file và timeout cuối là `3s`.

## 50. Bài tập mở rộng 2 — giữ fallback khi service không khai key

Shared có:

```properties
lab.import.retry-count=4
lab.import.timeout=10s
```

Service chỉ khai:

```properties
lab.import.timeout=3s
```

**Câu hỏi:** `retry-count` có bị mất không?

**Đáp án:** Không. Trong ví dụ này, `retry-count=4` tiếp tục được cung cấp từ shared, còn `timeout=3s` lấy từ service.

Điều này là một lợi ích chính của mô hình shared defaults + service overrides: service chỉ khai những giá trị khác biệt.

## 51. Bài tập mở rộng 3 — chủ thể khai báo import

`application.properties`:

```properties
spring.config.import=shared.properties
lab.import.mode=root
```

`shared.properties`:

```properties
lab.import.mode=shared
```

**Câu hỏi:** Nếu đưa dòng `lab.import.mode=root` xuống cuối file gốc, có thắng không?

**Đáp án:** Không chỉ vì vị trí dòng. Trong một document đơn, imported data có thể override key cùng tên của declaring document.

## 52. Bài tập mở rộng 4 — optional import thiếu

Root:

```properties
spring.config.import=optional:secrets-local.properties
lab.import.mode=local
```

Không có `secrets-local.properties`.

**Câu hỏi:** Startup có bắt buộc thất bại không?

**Đáp án:** Không. `optional:` cho phép thiếu location trong trường hợp được hỗ trợ. Nhưng nếu ứng dụng cần secret bắt buộc, nó vẫn nên fail theo validation/chính sách khác thay vì tiếp tục vận hành thiếu thông tin.

## 53. Bài tập mở rộng 5 — file ngoài thắng shared classpath

Root:

```properties
spring.config.import=classpath:/config/shared.properties,optional:file:./config/override.properties
```

Shared:

```properties
lab.import.mode=shared
```

External override:

```properties
lab.import.mode=external
```

**Câu hỏi:** Giá trị cuối trong runtime sạch khi external file tồn tại là gì?

**Đáp án:** `external`, với danh sách import này và không có nguồn ưu tiên cao hơn.

**Bài thực hành:** tạo file ngoài, chạy app từ working directory đã xác định, rồi đổi tên file external và chạy lại. Quan sát chế độ fallback khi file optional không còn.

## 54. Bài tập mở rộng 6 — CLI thắng cả import

Shared:

```properties
lab.import.mode=shared
```

Service:

```properties
lab.import.mode=service
```

Chạy:

```bash
java -jar app.jar --lab.import.mode=operator
```

**Câu hỏi:** `Environment#getProperty("lab.import.mode")` thường trả gì?

**Đáp án:** `operator` trong cấu hình Boot command-line properties mặc định. Điều này không thay đổi cách hai import đã được nạp; chỉ thêm một nguồn có precedence cao hơn.

## 55. Bài tập mở rộng 7 — import-relative

Root trong:

```text
/project/config/application.properties
```

import:

```properties
spring.config.import=common/shared.properties
```

File `shared.properties` trong `/project/config/common/` import:

```properties
spring.config.import=more/extra.properties
```

**Câu hỏi:** Tìm `extra.properties` ở đâu?

**Đáp án:** Tương đối với file khai báo import thứ hai:

```text
/project/config/common/more/extra.properties
```

Không phải mặc nhiên trong `/project/config/more/` hay working directory.

## 56. Bài tập mở rộng 8 — profile-specific import

Import:

```properties
spring.config.import=service.properties
```

Có:

```text
service.properties
service-prod.properties
```

**Câu hỏi:** Khi bật profile `prod`, file nào có thể góp giá trị override?

**Đáp án:** `service-prod.properties` là một profile-specific variant của imported resource; cần kiểm chứng trong đúng sơ đồ config data của ứng dụng.

## 57. Bài tập mở rộng 9 — có source marker nhưng giá trị khác

Test ghi:

```text
shared-marker=loaded
service-marker=loaded
mode=from-cli
```

**Câu hỏi:** Vì sao marker từ hai file tồn tại dù mode không đến từ chúng?

**Đáp án:** Marker chứng minh hai file đã được nạp. `mode=from-cli` chứng minh một nguồn ưu tiên cao hơn đã thắng key trùng. Presence và precedence là hai loại bằng chứng khác nhau.

## 58. Bài tập mở rộng 10 — `@ConfigurationProperties`

File service:

```properties
lab.import.timeout=250ms
```

Trong Java:

```java
@ConfigurationProperties(prefix = "lab.import")
public record ImportSettings(Duration timeout) {}
```

**Câu hỏi:** Có nhất thiết dùng `String` để nhận giá trị `250ms` không?

**Đáp án:** Không. Spring Boot Binder có thể liên kết thời lượng sang `Duration` nếu model được đăng ký và giá trị đúng cú pháp. Test nên assert `Duration.ofMillis(250)`.

## 59. Checklist cho dự án thực tế

- [ ] Đã xác định file nào là shared defaults?
- [ ] Đã xác định file nào là service overrides?
- [ ] Mỗi file có owner và mục đích rõ ràng?
- [ ] Thứ tự import phản ánh precedence chủ đích?
- [ ] Các key trùng có được tài liệu hóa?
- [ ] Có marker/test chứng minh từng file được nạp?
- [ ] Có test import sau thắng import trước?
- [ ] Có test đảo thứ tự import cho một key trùng?
- [ ] Có test importing document thắng declaring document?
- [ ] Không dựa vào vị trí dòng để suy ra precedence?
- [ ] Đã phân biệt fixed và import-relative location?
- [ ] Đường dẫn ngoài JAR có phù hợp OS/working directory?
- [ ] Có chính sách file bắt buộc và file optional?
- [ ] Có kiểm tra profile-specific variants?
- [ ] Có test nguồn CLI/env system ghi đè khi cần?
- [ ] Không import cùng tài nguyên nhiều lần chỉ để tăng ưu tiên?
- [ ] Có typed binding test cho `Duration`/`int`/`boolean` quan trọng?
- [ ] Không chứa secret trong shared file đóng gói công khai?
- [ ] Không in toàn bộ PropertySource ra log?
- [ ] Có startup test thật bằng `SpringApplication`?
- [ ] Có dùng `@TempDir` và URI hợp lệ cho test?
- [ ] Mọi context được đóng sau assertion?
- [ ] Có kiểm soát thay đổi trong CI?
- [ ] Có kiểm tra behavior production riêng với test cấu hình?
- [ ] Đã dùng đúng phiên bản Boot của dự án để kiểm chứng?

## 60. Tóm tắt

Trong Spring Boot 3.3, cách tách cấu hình thành shared và service có thể viết:

```properties
spring.config.import=classpath:/config/shared.properties,classpath:/config/service.properties
```

Cấu trúc tư duy:

```text
application.properties
       |
       v
shared.properties
       |
       v
service.properties
       |
       v
Spring Environment
       |
       +-- CLI / system properties / environment có thể override
       |
       v
@ConfigurationProperties
```

Với một tình huống cô lập, khi cả ba file khai cùng key:

```text
application: mode=from-application
shared:      mode=from-shared
service:     mode=from-service
```

thì **service** có thể thắng vì là **import nằm sau**.

Nếu đảo import, **shared** có thể thắng. Nếu thêm CLI `--lab.import.mode=from-cli`, CLI có thể thắng cả các import. Nếu có `service-prod.properties` và active profile `prod`, biến thể profile có thể tham gia precedence.

Những điểm cốt lõi:

1. **Imported Config Data có thể override document khai báo import.**
2. **Import về sau trong cùng danh sách có precedence cao hơn import trước.**
3. **Vị trí dòng `spring.config.import` trong cùng document không đổi quy tắc này.**
4. **Import-relative** giải quyết đường dẫn theo file khai báo; `classpath:` và `file:` là fixed locations.
5. **`optional:` chỉ xử lý thiếu location**, không bỏ qua mọi lỗi nội dung hoặc validation.
6. **Một resource import được nạp một lần** theo hợp đồng của Spring Boot, không dùng khai lặp làm chiến lược precedence.
7. **Marker + key xung đột + typed bean** là ba cách kiểm chứng bổ sung cho nhau.
8. **Dùng `SpringApplication.run(...)` và `@TempDir`** để chứng minh hành vi thực của Config Data mà không phụ thuộc máy.
9. **Không nhầm thứ tự import với toàn bộ precedence runtime**: CLI, Java system properties, environment variables và các nguồn khác còn có thể quyết định giá trị cuối.
10. **Đóng gói chung nhưng triển khai riêng**: shared defaults nên ổn định, overrides được cấp rõ ràng, secrets cần quản lý an toàn.

Khi các quy tắc này được ghi thành test trong CI, việc tách tệp dùng chung trở thành một quyết định có bằng chứng, thay vì một chuỗi import khó dự đoán. Đó là mục tiêu của bài thực hành tổng hợp.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, Importing Additional Data, Fixed and Import Relative Locations, Property Ordering, Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 Java API — `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework API — `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html
- JUnit Jupiter User Guide — `@TempDir`: https://junit.org/junit5/docs/current/user-guide/
