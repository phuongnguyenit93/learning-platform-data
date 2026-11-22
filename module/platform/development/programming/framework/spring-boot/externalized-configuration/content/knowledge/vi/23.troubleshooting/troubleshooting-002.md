# Xem profile hoạt động và thông tin nạp Config Data trong log

## 1. Mục tiêu của bài học

Trong Spring Boot Externalized Configuration, một ứng dụng có thể đọc cấu hình từ nhiều nơi: `application.yml`, `application.properties`, các tài liệu theo profile, thư mục ngoài JAR, `spring.config.import`, biến môi trường, Java system properties và đối số dòng lệnh.

Khi một giá trị cấu hình không đúng, câu hỏi đầu tiên thường không phải “sửa code ở đâu?” mà là:

- **Profile nào đang hoạt động trong lần chạy này?**
- Spring Boot đã nạp những tài liệu Config Data nào?
- Có một tệp cấu hình bên ngoài JAR đang ghi đè file trong classpath không?
- Tài liệu `application-prod.yml` có thực sự được kích hoạt không?
- `spring.config.import` đã được phân giải và nạp thành công hay chưa?
- Một khóa có bị ghi đè bởi biến môi trường, JVM option hoặc đối số dòng lệnh không?
- Có phải cấu hình không được nạp, hay đã được nạp nhưng lỗi binding/conversion/validation?

Spring Boot cung cấp nhiều tín hiệu chẩn đoán:

1. **Log khởi động ở mức INFO:** thường hiển thị active profiles hoặc default profile.
2. **Log DEBUG/TRACE của nhóm `org.springframework.boot.context.config`:** giúp quan sát việc xử lý Config Data và phân giải các vị trí cấu hình.
3. **Spring `Environment` và danh sách `PropertySource`:** cho biết các nguồn có mặt và giá trị hiệu lực tại một thời điểm.
4. **Thông báo lỗi Config Data, binding, conversion và validation:** chỉ ra vấn đề xảy ra ở tầng nào.
5. **Spring Boot Actuator** (nếu được bật, bảo vệ đúng cách): hỗ trợ quan sát môi trường và configuration properties của một ứng dụng đang chạy.

Mục tiêu là xây dựng một quy trình đọc log có căn cứ, không suy đoán chỉ từ việc một file YAML đang tồn tại trong repository.

## 2. Vì sao một file cấu hình đúng vẫn có thể cho kết quả sai?

Giả sử dự án có ba tài liệu:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

Tệp chung:

```yaml
# application.yml
notification:
  endpoint: "https://default.example.invalid"
  timeout: 5s
  max-attempts: 3
```

Tệp dev:

```yaml
# application-dev.yml
notification:
  endpoint: "https://dev.example.invalid"
  timeout: 2s
```

Tệp prod:

```yaml
# application-prod.yml
notification:
  endpoint: "https://prod.example.invalid"
  timeout: 10s
  max-attempts: 5
```

Nếu chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

thì Spring Boot có thể sử dụng giá trị từ tài liệu dev cho những khóa mà tài liệu ấy ghi đè. Ngược lại, khi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

nó có thể sử dụng các giá trị dành cho production.

Nhưng nếu command line có thêm:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=750ms
```

thì timeout cuối cùng thông thường đến từ command-line property `750ms`, không còn là `10s` trong `application-prod.yml`.

Bởi vậy, **chỉ mở file `application-prod.yml` không đủ để xác định giá trị thực sự được dùng**. Phải kiểm tra profile, các vị trí Config Data đã nạp và những nguồn có độ ưu tiên cao hơn.

## 3. Phân biệt active profile, default profile và tài liệu được nạp

Ba khái niệm dễ bị gộp thành một:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Active profiles | Các tên profile đang được Spring Environment xem là hoạt động |
| Default profiles | Các profile mặc định được xét khi không có active profile |
| Config Data documents | Những tài liệu hoặc nguồn cấu hình được tìm thấy, phân giải và nạp theo cơ chế Config Data |

Ví dụ, khi không khai báo:

```properties
spring.profiles.active
```

Spring Boot có thể ghi log cho biết **không có active profile**, rồi nhắc tới default profile (thường là `default` trong cấu hình thông thường).

Điều đó **không có nghĩa** ứng dụng không đọc `application.yml`. Tài liệu cơ sở vẫn có thể được nạp.

Tương tự, khi active profile là `prod`:

```text
active profiles: [prod]
```

không thể suy ra mọi giá trị phải đến từ `application-prod.yml`. Spring Boot vẫn có thể nạp tài liệu cơ sở, tài liệu import, các vị trí ngoài classpath và các nguồn property không thuộc Config Data.

**Kết luận:** active profile là một mảnh thông tin quan trọng, nhưng nó không phải bản liệt kê đầy đủ tất cả PropertySource hay giá trị cấu hình có hiệu lực.

## 4. Log khởi động thường hiển thị profile như thế nào?

Trong một lần khởi động Spring Boot thông thường với startup info được bật, log ở mức INFO có thể chứa thông điệp có ý nghĩa tương tự:

```text
The following 1 profile is active: "dev"
```

hoặc:

```text
No active profile set, falling back to 1 default profile: "default"
```

**Đây là ví dụ minh họa về hình thức thông báo.** Số lượng profile, nội dung, ngôn ngữ và định dạng logger có thể khác giữa các phiên bản Spring Boot cũng như cấu hình logging.

Khi xem log, hãy tập trung vào:

- Có active profile hay không.
- Những profile nào được liệt kê.
- Dòng log thuộc **lần khởi động nào**.
- Có nhiều tiến trình ứng dụng hoặc container cùng phát log không.
- Có hệ thống tự thêm active profile từ environment hoặc launcher không.

Nếu log đang là kết quả của phiên bản JAR cũ hoặc của một pod khác, bạn có thể chẩn đoán nhầm dù dòng profile đọc được hoàn toàn hợp lệ.

## 5. Xem profile bằng Spring Environment

Khi muốn xác nhận chắc chắn những profile mà ứng dụng nhìn thấy sau khi context khởi tạo, có thể đọc `Environment`.

Ví dụ:

```java
package com.example.configdemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfilePrinter implements ApplicationRunner {

    private final Environment environment;

    public ProfilePrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("defaultProfiles="
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
```

Nếu kích hoạt `dev`, một kết quả minh họa:

```text
activeProfiles=[dev]
defaultProfiles=[default]
```

Nếu không có active profile:

```text
activeProfiles=[]
defaultProfiles=[default]
```

Ở đây `getActiveProfiles()` và `getDefaultProfiles()` trả về hai tập thông tin khác nhau.

**Chú ý về thời điểm:** `ApplicationRunner` chạy sau khi Spring context đã được refresh. Đây là cách xác nhận trạng thái Environment ở thời điểm ấy; nó không phải log chi tiết từng bước mà Config Data đã thực hiện trước đó.

## 6. Những cách kích hoạt profile cần kiểm tra

Một active profile có thể được cấp theo nhiều cách.

### 6.1. Đối số dòng lệnh

```bash
java -jar app.jar --spring.profiles.active=dev
```

### 6.2. Java system property

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

Đối với JVM, `-D...` cần đặt trước `-jar` nếu muốn nó được xem là Java system property.

### 6.3. Biến môi trường

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar .\app.jar
```

### 6.4. Run configuration của IDE

Trong IDE, người phát triển có thể đặt:

```text
Program arguments:
--spring.profiles.active=dev
```

hoặc:

```text
VM options:
-Dspring.profiles.active=dev
```

hoặc một environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

Chúng đến từ **những PropertySource khác nhau**, nên khi cùng tên khóa có nhiều giá trị, quy tắc ưu tiên nguồn quyết định kết quả.

### 6.5. Gradle bootRun

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Với PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

`--args` truyền program arguments vào tiến trình ứng dụng. Đừng nhầm tùy chọn `-D...` cấp cho chính Gradle với một system property chắc chắn được cấp cho JVM ứng dụng.

## 7. Profile là nhiều tên chứ không nhất thiết chỉ một tên

Một ứng dụng có thể chạy với nhiều active profiles:

```bash
java -jar app.jar --spring.profiles.active=dev,debug
```

Khi đó các tài liệu hoặc bean gắn điều kiện `dev` và `debug` có thể được xét tùy cơ chế và điều kiện tương ứng.

Giả sử:

```text
application.yml
application-dev.yml
application-debug.yml
```

Không nên chỉ nhìn profile `dev` rồi bỏ qua sự có mặt của `debug`, bởi tài liệu/nhóm cấu hình khác có thể ghi đè một số giá trị.

**Thứ tự profile có thể có ý nghĩa** trong việc lựa chọn tài liệu profile-specific và giá trị ghi đè khi nhiều profile đồng thời áp dụng. Nếu hai tài liệu cung cấp cùng khóa, hãy kiểm tra thứ tự và các nguồn có hiệu lực trong ứng dụng thật.

Khi log báo nhiều profile, cần ghi lại **toàn bộ danh sách**, không chỉ profile đầu tiên.

## 8. spring.profiles.include và profile groups

Ngoài `spring.profiles.active`, Spring Boot hỗ trợ những cơ chế mở rộng tập profile.

Ví dụ, trong một tài liệu không bị giới hạn bởi profile:

```yaml
spring:
  profiles:
    include: "observability"
```

Một ứng dụng được chạy với `prod` có thể đồng thời kích hoạt profile bổ sung `observability`.

Tương tự, có thể định nghĩa profile group:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

Khi `production` được kích hoạt, nhóm cấu hình này giúp kích hoạt các profile thành viên theo cơ chế Spring Boot.

**Lưu ý quan trọng:** `spring.profiles.active`, `spring.profiles.include` và các định nghĩa profile group phải tuân theo quy tắc nơi được phép khai báo. Chúng không được đặt tùy ý trong các tài liệu profile-specific hoặc các tài liệu đã được điều kiện hóa bằng `spring.config.activate.on-profile`.

Khi log cho biết số active profile nhiều hơn giá trị bạn tự nhập, hãy kiểm tra:

1. Có `spring.profiles.include` hay không.
2. Có profile groups hay không.
3. Có mã khởi động hoặc test framework đã kích hoạt profile không.
4. Có một nguồn cấu hình có ưu tiên cao hơn ghi đè `spring.profiles.active` không.

Không kết luận đây là lỗi chỉ vì số active profiles trong log khác số profile đã gõ trực tiếp.

## 9. spring.config.activate.on-profile khác spring.profiles.active

Ví dụ một file `application.yml` nhiều tài liệu:

```yaml
notification:
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

notification:
  timeout: 10s
```

Dấu `---` tách các YAML documents.

Thuộc tính:

```text
spring.config.activate.on-profile
```

quy định **điều kiện để một tài liệu cấu hình có hiệu lực**, chứ không có ý nghĩa tự kích hoạt profile `prod`.

Muốn dùng tài liệu thứ hai, profile `prod` phải hoạt động từ nguồn cấu hình/điểm khởi động thích hợp.

Trong log TRACE, bạn có thể thấy dấu vết xử lý và xét điều kiện của các tài liệu Config Data. Tuy nhiên, không nên đồng nhất “một tài liệu đã được khám phá” với “tài liệu đó đã có hiệu lực trong Environment”.

Mô hình:

```text
Tài liệu trong application.yml
               |
               v
Có spring.config.activate.on-profile?
               |
        +------+------+
        |             |
      Không          Có
        |             |
        v             v
  Dùng theo       Kiểm tra điều kiện
  quy tắc chung   active profile
                      |
                +-----+-----+
                |           |
               Đúng        Sai
                |           |
                v           v
            Có thể nạp    Không áp dụng
            theo quy tắc  tài liệu ấy
```

Trong thực tế, chi tiết resolver và cách sắp xếp tài liệu phức tạp hơn sơ đồ đơn giản trên.

## 10. Config Data là gì trong Spring Boot?

**Config Data** là cơ chế của Spring Boot để nạp và kết hợp các tài liệu cấu hình từ những vị trí được hỗ trợ, ví dụ:

- File `application.properties` hoặc `application.yml` trên classpath.
- File/thư mục cấu hình bên ngoài ứng dụng.
- File theo active profile.
- Nguồn được khai báo qua `spring.config.import`.
- Những loại location được cung cấp bởi Config Data extensions.

Một luồng khái quát:

```text
SpringApplication.run()
          |
          v
Chuẩn bị Environment
          |
          v
Config Data:
  - Xác định tên/vị trí
  - Xử lý import
  - Xét profile/activation
  - Nạp tài liệu thích hợp
  - Sắp xếp mức ưu tiên
          |
          v
Spring Environment có nhiều PropertySource
          |
          v
ConfigurationProperties Binder
          |
          v
Bean cấu hình của ứng dụng
```

Config Data không phải tên gọi chung cho **mọi PropertySource**. Ví dụ Java system properties và biến môi trường thường tham gia Environment, nhưng bản thân chúng không phải những tài liệu YAML được Config Data loader nạp.

Đây là lý do khi thấy các tệp Config Data đã được nạp, bạn vẫn cần xem nguồn ngoài Config Data nếu giá trị cuối cùng bất ngờ.

## 11. Bật TRACE cho nhóm logger Config Data

Khi log INFO chỉ hiển thị profile mà không đủ thông tin để tìm file đã nạp, một cách hữu ích là bật TRACE cho nhóm logger:

```text
org.springframework.boot.context.config
```

Ví dụ chạy JAR:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Trong PowerShell:

```powershell
java -jar .\app.jar --spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE
```

Nhóm logger này bao phủ các thành phần liên quan tới việc chuẩn bị và xử lý Config Data trong những phiên bản Spring Boot có cấu trúc package tương ứng.

Khi bật TRACE, log **có thể** cung cấp chi tiết về:

- Xử lý các vị trí Config Data.
- Phân giải ứng viên location.
- Nhận diện tài liệu profile-specific.
- Import các nguồn được khai báo.
- Các giai đoạn tải/áp dụng tài liệu.
- Những tình huống không có cấu hình hoặc tài liệu không phù hợp.

**Không có cam kết rằng mọi phiên bản Boot sẽ in chính xác cùng thông báo hoặc cùng bộ sự kiện**. Logger, câu chữ và mức log có thể thay đổi theo phiên bản và logging implementation.

Cũng không nên coi TRACE là API máy-máy ổn định để viết parser phụ thuộc từng dòng log trong nhiều phiên bản.

## 12. Vì sao nên truyền logging.level bằng đối số khởi chạy?

Cơ chế Config Data hoạt động **rất sớm** trong vòng đời Spring Boot. Nếu bạn chỉ khai báo:

```yaml
# application-prod.yml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

thì tùy thời điểm LoggingSystem được cấu hình và Config Data được xử lý, có thể không nhìn thấy **toàn bộ các sự kiện sớm nhất** của quá trình chuẩn bị môi trường.

Để thử chẩn đoán, cách dễ kiểm soát là cấp logger level ngay lúc khởi động:

```bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Hoặc bằng Java system property:

```bash
java -Dlogging.level.org.springframework.boot.context.config=TRACE \
     -jar app.jar
```

Các cách này làm cấu hình logging có thể được truy cập từ nguồn khởi động sớm, dù không nên hứa rằng bất kỳ hệ thống logging hay bootstrapping tùy biến nào cũng có cùng mốc thời gian.

**Khuyến nghị thực hành:** thử bằng CLI hoặc JVM property trước, ghi lại đúng lệnh đã chạy, rồi đọc log của chính tiến trình ấy.

## 13. Cách chạy TRACE từ IDE

Với IDE chạy trực tiếp main class, cấu hình Program arguments:

```text
--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE
```

Hoặc trong VM options:

```text
-Dspring.profiles.active=dev -Dlogging.level.org.springframework.boot.context.config=TRACE
```

Hai lựa chọn tạo ra các loại PropertySource khác nhau nhưng đều có thể cấp log level và profile cho Spring Boot.

Nếu IDE có ô riêng như **Active profiles**, hãy hiểu đó là một tiện ích của cấu hình chạy IDE. Nó không phải một định nghĩa profile thứ hai của Spring Framework.

Khi đọc log trong IDE:

1. Xác nhận bạn thực sự khởi động lần chạy mới.
2. Xác nhận Run configuration thuộc đúng module/main class.
3. Xem có Program arguments và VM options nào đang ghi đè nhau.
4. Phân biệt console chạy main class và console của Gradle task.
5. Nếu IDE lọc dòng DEBUG/TRACE, kiểm tra khả năng hiển thị console.
6. Không lấy log từ một phiên debug đã dừng rồi coi là log của tiến trình hiện tại.

## 14. Cách chạy TRACE bằng Gradle bootRun

Với Spring Boot Gradle plugin:

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --logging.level.org.springframework.boot.context.config=TRACE"
```

Ở đây `--args` là tùy chọn của task để truyền **program arguments vào tiến trình ứng dụng**.

Không nên nhầm:

```bash
./gradlew -Dlogging.level.org.springframework.boot.context.config=TRACE bootRun
```

với một lệnh chắc chắn cấp Java system property đó cho JVM ứng dụng; `-D` đặt ở lệnh Gradle thường ảnh hưởng JVM Gradle và có thể không được task truyền tiếp như mong đợi.

Nếu cần system property cho JVM của `bootRun`, cấu hình task tường minh hoặc dùng program arguments như trên.

**Phân biệt log:** Gradle cũng in log tác vụ của nó. Các dòng về dependency resolution hoặc Gradle daemon không phải là log Config Data của Spring Boot.

## 15. Cách chạy TRACE bằng java -jar

Giả sử đã có executable JAR:

```text
build/libs/config-demo.jar
```

Lệnh:

```bash
java -jar build/libs/config-demo.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Hoặc:

```bash
java -Dspring.profiles.active=prod \
     -Dlogging.level.org.springframework.boot.context.config=TRACE \
     -jar build/libs/config-demo.jar
```

Với cách `-D...`, các system properties nằm **trước** `-jar`.

Sai lầm phổ biến:

```bash
java -jar app.jar -Dspring.profiles.active=prod
```

Ở vị trí sau tên JAR, `-D...` không được JVM diễn giải thành JVM system property. Nếu ứng dụng không có cách phân tích đối số tùy biến cho dạng đó, kết quả không giống lệnh đúng.

Một lệnh dễ đọc hơn khi muốn cấp Spring Boot command-line properties:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

## 16. --debug không đồng nghĩa với Config Data TRACE

Spring Boot hỗ trợ tham số:

```bash
java -jar app.jar --debug
```

Nó có thể kích hoạt mức log gỡ lỗi cho một số nhóm logger và hỗ trợ xuất **Condition Evaluation Report** khi phù hợp.

Condition Evaluation Report tập trung vào các điều kiện quyết định auto-configuration: vì sao một auto-configuration được chọn hoặc không được chọn.

Đó là câu hỏi khác với:

> Spring Boot đã phân giải `file:./config/application-prod.yml` thế nào và nạp tài liệu nào?

Vì vậy:

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Xem profile hoạt động cơ bản | Startup INFO log và `Environment#getActiveProfiles()` |
| Xem các bước Config Data | TRACE logger `org.springframework.boot.context.config` |
| Xem auto-configuration condition | `--debug` / Condition Evaluation Report |
| Xem giá trị runtime có hiệu lực | `Environment` hoặc Actuator được bảo vệ |
| Xem vì sao bean cấu hình bị lỗi | Binding/conversion/validation exception |

**Không chỉ bật `--debug` rồi kết luận không có log TRACE về file là do file không được nạp.**

Nếu cần cả hai loại thông tin, có thể kết hợp `--debug` và cấu hình logging category TRACE, nhưng cần cân nhắc lượng log và dữ liệu nhạy cảm.

## 17. Đọc log TRACE theo trình tự

Khi bật Config Data TRACE, nên đọc theo quy trình, thay vì tìm một dòng đơn lẻ rồi suy luận toàn bộ.

**Bước 1 — Xác định một lần khởi động cụ thể.** Ghi lại application name, process/container, thời điểm khởi động và phiên bản artifact nếu có.

**Bước 2 — Tìm thông tin active/default profiles.** Ghi đúng danh sách profile mà ứng dụng xác nhận.

**Bước 3 — Tìm các thông điệp về location và resource.** Xem nguồn trên classpath, thư mục ngoài JAR, file được import và những vị trí không tìm thấy.

**Bước 4 — Tìm xử lý tài liệu theo profile.** Có tài liệu chỉ áp dụng khi profile phù hợp hay không?

**Bước 5 — Tìm lỗi nạp Config Data.** Phân biệt file thiếu, import không phân giải được, sai cú pháp hoặc điều kiện kích hoạt không phù hợp.

**Bước 6 — Đối chiếu giá trị runtime có hiệu lực.** Log Config Data chỉ cho biết một phần đường đi; CLI, environment variable hoặc Java system property có thể thắng.

**Bước 7 — Nếu bean vẫn lỗi, kiểm tra binding/conversion/validation.** Một file nạp thành công chưa bảo đảm mọi giá trị trong file đúng kiểu và hợp lệ.

Không nên cố đọc log TRACE như một danh sách tuyệt đối của các thuộc tính đã được sử dụng. Nó là tín hiệu hỗ trợ chẩn đoán, không phải database truy vết đầy đủ từng key.

## 18. Ví dụ log minh họa khi có active profile

Giả sử chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Một bản diễn giải log có thể có cấu trúc ý nghĩa tương tự:

```text
INFO  ... Starting ConfigDemoApplication ...
INFO  ... The following 1 profile is active: "dev"
TRACE ... Considering configuration locations ...
TRACE ... Processing classpath application configuration ...
TRACE ... Processing profile-specific configuration ...
TRACE ... Applying configuration for active profile dev ...
INFO  ... Started ConfigDemoApplication ...
```

**Đoạn này chỉ là mô phỏng nội dung để học cách đọc**, không phải stdout nguyên văn từ một phiên bản Spring Boot cụ thể.

Trong log thực tế, tên logger, thông điệp và thứ tự các dòng có thể khác. Một phiên bản có thể log đối tượng `ConfigDataResource` và một phiên bản khác log thông tin ở cấp resolver/loader.

Điều cần rút ra:

- Profile được ghi nhận là `dev`.
- Có hoạt động liên quan tới xử lý Config Data.
- Muốn chắc chắn file nào đã đóng góp giá trị, cần kết hợp với thứ tự PropertySource hoặc thông tin runtime.

## 19. Tài liệu không nạp do profile chưa hoạt động

Giả sử:

```yaml
# application-prod.yml
notification:
  timeout: 10s
```

Chạy ứng dụng không bật `prod`:

```bash
java -jar app.jar
```

Trong tình huống thông thường, `application-prod.yml` không đóng góp giá trị profile-specific nếu `prod` không hoạt động.

Một người có thể đọc `application-prod.yml` trên repository và kết luận ứng dụng phải dùng `10s`. Nhưng runtime lại dùng timeout từ `application.yml`.

Cách chẩn đoán:

1. Kiểm tra dòng log active/default profiles.
2. Xem CLI, VM options, environment variable có kích hoạt `prod` hay không.
3. Bật TRACE Config Data để quan sát xử lý theo profile.
4. Xác nhận giá trị hiệu lực qua bean `@ConfigurationProperties` hoặc một nguồn quan sát an toàn.
5. Nếu cần, chạy một test tích hợp với `prod` được kích hoạt tường minh.

**Sửa đúng tầng:** kích hoạt đúng profile hoặc điều chỉnh thiết kế nguồn cấu hình, không nên đổi giá trị mặc định một cách tùy tiện chỉ để che lỗi chọn profile.

## 20. Một tài liệu được tìm thấy nhưng chưa chắc được áp dụng

Giả sử `application.yml` có nhiều document:

```yaml
notification:
  enabled: true
  timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

notification:
  timeout: 10s
```

Config Data có thể gặp cả hai document trong quá trình phân tích nguồn. Nhưng document thứ hai chỉ áp dụng khi điều kiện `on-profile: prod` phù hợp.

Do đó, khi tìm các chuỗi như tên file trong TRACE log, phải phân biệt:

- **Đã kiểm tra hoặc tìm thấy resource:** resolver/loader có tương tác với vị trí đó.
- **Đã parse tài liệu:** cú pháp tài liệu đã được đọc.
- **Đã áp dụng vào Environment:** tài liệu thỏa điều kiện và được đưa vào danh sách nguồn có hiệu lực.
- **Giá trị thực sự thắng trong Environment:** không có nguồn ưu tiên cao hơn ghi đè khóa đó.

Bốn trạng thái này không hoàn toàn tương đương.

## 21. Vị trí Config Data mặc định và working directory

Trong cấu hình Spring Boot thông thường, các vị trí tìm kiếm mặc định bao gồm nguồn trong classpath và những vị trí bên ngoài ứng dụng, chẳng hạn:

```text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
```

Các vị trí có thể được xử lý theo nhóm và thứ tự ưu tiên cụ thể của Config Data, không nên coi danh sách giản lược trên là một sơ đồ precedence đầy đủ.

**`./` phụ thuộc vào working directory của tiến trình Java.**

Ví dụ:

```text
/opt/team/
  config/
    application.yml
  apps/
    service.jar
```

Người vận hành chạy:

```bash
cd /opt/team
java -jar apps/service.jar
```

có thể khiến `./config/` trỏ tới `/opt/team/config/`.

Nhưng:

```bash
cd /opt/team/apps
java -jar service.jar
```

khiến `./config/` trỏ tới `/opt/team/apps/config/`.

**Cùng một JAR, cùng profile nhưng working directory khác nhau có thể dẫn đến tập Config Data khác nhau.**

Nếu TRACE log cho thấy chỉ có classpath config, trong khi bạn mong có file ngoài, hãy kiểm tra thư mục làm việc trước khi kết luận Boot không hỗ trợ external configuration.

## 22. spring.config.location và additional-location

Có hai thuộc tính quan trọng:

```text
spring.config.location
spring.config.additional-location
```

Khác biệt khái quát:

- `spring.config.location` định nghĩa lại các vị trí tìm kiếm Config Data mặc định theo cơ chế tương ứng.
- `spring.config.additional-location` **bổ sung** những vị trí bên cạnh các vị trí mặc định.

Ví dụ:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/team/config/
```

Đường dẫn `file:/opt/team/config/` là một location dạng thư mục. Dấu `/` cuối rất quan trọng để loader nhận diện nó là thư mục cấu hình.

Tiền tố `optional:` được dùng khi muốn việc thiếu location không nhất thiết khiến ứng dụng thất bại.

Nếu bạn dùng:

```bash
java -jar app.jar \
  --spring.config.location=file:/opt/team/config/
```

thì cần hiểu rằng bạn đang thay thế danh sách vị trí mặc định, thay vì đơn giản thêm một nơi nữa.

Trong quá trình đọc TRACE, chú ý xem location được chỉ định là **một file**, **một thư mục**, **classpath resource**, hay **một location tùy chỉnh**.

## 23. Tại sao Config Data không thể được chẩn đoán bằng mỗi application.yml?

Một ứng dụng có thể đóng gói:

```text
BOOT-INF/classes/application.yml
```

nhưng khi chạy còn nhận:

```bash
--spring.config.additional-location=file:/etc/my-service/
```

hoặc:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION
```

được cấp từ môi trường tiến trình.

Khi đó các tài liệu ngoài JAR có thể tham gia nguồn cấu hình, tùy quy tắc thứ tự của Config Data.

Một tình huống khác là file `application.yml` trong repository khác với file được đóng gói trong executable JAR đang chạy. Vì vậy nên xác nhận:

- Artifact hiện tại có đúng version không.
- File resource đã được build vào JAR chưa.
- Working directory có đúng không.
- Cơ chế `spring.config.location` có thay thế mặc định không.
- Có import location mới không.
- Profile có khớp điều kiện tài liệu không.

Khi cần kiểm tra JAR:

```bash
jar tf app.jar
```

Với Boot executable JAR thông dụng, tài nguyên của ứng dụng thường nằm trong `BOOT-INF/classes/`. Một file không nằm trong artifact không thể tự xuất hiện qua classpath resource của artifact ấy.

## 24. spring.config.import và cách đọc dấu vết import

Spring Boot hỗ trợ import tài liệu:

```yaml
spring:
  config:
    import: "optional:file:./extra-config.yml"
```

Khi nguồn này được nạp, Config Data processing có thể phân giải thêm location được import.

Những câu hỏi cần trả lời khi xem log:

1. Tài liệu chứa `spring.config.import` có được nạp không?
2. Thuộc tính import có đúng tên và cú pháp không?
3. Đường dẫn là location tương đối hay cố định?
4. Resource được import có tồn tại không?
5. Có tiền tố `optional:` không?
6. Có profile nào ảnh hưởng tới tài liệu import không?
7. Có nhiều import cùng đóng góp một khóa không?
8. Có nguồn ưu tiên cao hơn ghi đè kết quả import không?

Ví dụ:

```text
application.yml
       |
       +-- spring.config.import
                 |
                 v
          extra-config.yml
                 |
                 v
          PropertySource từ import
```

Import không chỉ có nghĩa là “một file khác được nối thêm ở cuối”. Spring Boot có quy tắc về vị trí và mức ưu tiên của các tài liệu được import.

Trong những trường hợp thông thường, dữ liệu import có thể ghi đè tài liệu khai báo import theo quy tắc Config Data. Tuy nhiên giá trị cuối còn phụ thuộc những nguồn khác và thứ tự import.

## 25. Import thiếu: optional khác với bắt buộc

Xem:

```yaml
spring:
  config:
    import: "file:./local-overrides.yml"
```

Nếu file không tồn tại, Config Data có thể gây lỗi khởi động vì location bắt buộc không tìm thấy.

Biểu hiện có thể liên quan tới ngoại lệ `ConfigDataLocationNotFoundException` hoặc dạng lỗi Config Data tương ứng, tùy tình huống cụ thể.

Nếu viết:

```yaml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
```

thì việc không có resource có thể được bỏ qua theo cơ chế optional.

**Không nên biến mọi import thành optional chỉ để bỏ qua lỗi khởi động.** Nếu file chứa cấu hình bắt buộc như endpoint production hoặc chính sách bảo mật, optional có thể khiến ứng dụng dùng giá trị mặc định ngoài ý định.

Quy trình:

- Nếu file là tùy chọn thật: dùng optional và kiểm thử tình huống thiếu.
- Nếu file là bắt buộc: để lỗi xuất hiện sớm và sửa đường dẫn/quyền triển khai.
- Nếu file tồn tại nhưng sai nội dung: optional **không đồng nghĩa** bỏ qua mọi lỗi parse/binding.
- Nếu file import được nạp nhưng giá trị bị ghi đè: phải kiểm tra thứ tự nguồn thay vì chỉ thêm optional.

## 26. Một ví dụ đầy đủ để thực hành xem Config Data log

Tạo dự án với cấu trúc:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
  extra-flags.yml
```

Tệp cơ sở:

```yaml
# application.yml
spring:
  application:
    name: config-log-demo
  config:
    import: "classpath:extra-flags.yml"

demo:
  message: "base"
  timeout: 5s
  max-attempts: 3
```

Tệp dev:

```yaml
# application-dev.yml
demo:
  message: "development"
  timeout: 2s
```

Tệp prod:

```yaml
# application-prod.yml
demo:
  message: "production"
  timeout: 10s
```

Tệp import:

```yaml
# extra-flags.yml
demo:
  enabled: true
```

Một record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String message,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        boolean enabled) {
}
```

Các ví dụ dùng Java và Jakarta Validation cho Spring Boot 3.x. Nếu dùng phiên bản khác, cần điều chỉnh dependency, package và API cho phù hợp.

Đăng ký với:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigLogDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigLogDemoApplication.class, args);
    }
}
```

Khi chạy với `dev`, bạn có một kịch bản nhỏ đủ để quan sát:

- File mặc định.
- File dev.
- File được import.
- Profile hoạt động.
- Giá trị được bind vào record.

## 27. In giá trị không nhạy cảm để đối chiếu với TRACE

Thêm runner:

```java
package com.example.configdemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DemoConfigPrinter implements ApplicationRunner {

    private final DemoProperties properties;
    private final Environment environment;

    public DemoConfigPrinter(
            DemoProperties properties,
            Environment environment) {
        this.properties = properties;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("active="
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("message=" + properties.message());
        System.out.println("timeout=" + properties.timeout());
        System.out.println("maxAttempts=" + properties.maxAttempts());
        System.out.println("enabled=" + properties.enabled());
    }
}
```

Khi chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

trong ví dụ không có nguồn ghi đè khác, giá trị dự kiến có ý nghĩa:

```text
active=[dev]
message=development
timeout=PT2S
maxAttempts=3
enabled=true
```

Vì:

- `application-dev.yml` ghi đè `demo.message` và `demo.timeout` từ tệp chung.
- `demo.max-attempts` vẫn nhận từ cấu hình cơ sở.
- `extra-flags.yml` cung cấp `demo.enabled`.

**Không nhầm dòng giá trị cuối từ ApplicationRunner với log của Config Data loader.** Runner chỉ hiển thị kết quả đã được bind sau khi Spring context sẵn sàng.

## 28. Làm sao biết khóa bị nguồn nào ghi đè?

TRACE Config Data giúp xác nhận luồng nạp. Nhưng để biết nguồn nào đang **cung cấp một giá trị cụ thể**, có thể quan sát danh sách `PropertySource` trong `ConfigurableEnvironment`.

Ví dụ chỉ in **tên nguồn**:

```java
package com.example.configdemo;

import org.springframework.core.env.ConfigurableEnvironment;

public final class PropertySourceReporter {

    private PropertySourceReporter() {
    }

    public static void printSourceNames(
            ConfigurableEnvironment environment) {

        int index = 0;

        for (var source : environment.getPropertySources()) {
            System.out.println(
                    (++index) + ". " + source.getName());
        }
    }
}
```

Trong một test hoặc runner, gọi:

```java
PropertySourceReporter.printSourceNames(environment);
```

Thứ tự danh sách thường phản ánh ưu tiên khi Spring tra cứu các thuộc tính tương ứng: những nguồn ở phía trước thường có mức ưu tiên cao hơn.

**Cảnh báo:** một số nguồn có cấu trúc tổng hợp, ánh xạ tên đặc biệt hoặc cách tra cứu riêng. Không nên viết mã production phụ thuộc vào tên hoặc số lượng PropertySource nội bộ cố định.

### 28.1. Xác định nguồn đầu tiên có một khóa không nhạy cảm

Để chẩn đoán trong test/dev:

```java
import org.springframework.core.env.ConfigurableEnvironment;

public static void printCandidateSources(
        ConfigurableEnvironment environment,
        String key) {

    for (var source : environment.getPropertySources()) {
        Object value = source.getProperty(key);

        if (value != null) {
            System.out.println(
                    "Có khóa " + key
                    + " trong nguồn " + source.getName());
        }
    }
}
```

Đoạn code cố ý **không in giá trị**, vì một khóa có thể chứa token, mật khẩu hoặc dữ liệu nhạy cảm.

Nó minh họa cách quan sát nơi cung cấp thuộc tính theo tra cứu đơn giản. Không phải mọi PropertySource đều hiển thị mọi biến thể tên khóa theo cùng cách, đặc biệt với relaxed binding của biến môi trường. Vì vậy không coi kết quả này là lời giải thích đầy đủ cho mọi trường hợp Binder.

Đối với `@ConfigurationProperties`, binder có thể xử lý tên thuộc tính, cấu trúc collection và conversion phức tạp hơn một lần gọi `source.getProperty(key)` trực tiếp.

## 29. Sử dụng Environment để đọc một khóa có hiệu lực

Ví dụ:

```java
import org.springframework.core.env.Environment;

String message =
        environment.getProperty("demo.message");
```

Nếu bạn tự cung cấp:

```bash
java -jar app.jar --demo.message=from-cli
```

thì trong cơ chế Spring Boot thông thường, command-line property có thể thắng giá trị từ `application.yml`.

Đọc kết quả:

```text
demo.message = from-cli
```

nhưng **không nên suy ra Config Data không được nạp** chỉ vì CLI thắng. Tệp YAML vẫn có thể nằm trong Environment và đóng góp những khóa khác.

Đây là nguyên nhân khiến log TRACE và giá trị có hiệu lực cần được dùng **cùng nhau**:

- TRACE: giúp thấy đường nạp cấu hình.
- Environment: giúp thấy giá trị tại thời điểm hiện tại.
- Validation/binder: giúp hiểu vì sao giá trị có hoặc không tạo được bean.

## 30. Actuator env và configprops hỗ trợ điều tra

Nếu ứng dụng có Spring Boot Actuator và những endpoint được bật/bảo vệ phù hợp, hai endpoint hữu ích là:

```text
/actuator/env
/actuator/configprops
```

Khái quát:

- `env`: thông tin về Environment/PropertySources và thuộc tính.
- `configprops`: thông tin về các bean `@ConfigurationProperties` và dữ liệu binding có thể được công cụ hiển thị.

Tuy nhiên:

1. Các endpoint có thể không được expose mặc định.
2. Hình dạng response và cơ chế che giá trị nhạy cảm có thể khác giữa phiên bản Spring Boot.
3. Chúng có thể tiết lộ tên hoặc cấu trúc cấu hình nội bộ, thậm chí dữ liệu bí mật nếu cấu hình sai.
4. Không nên bật công khai trên Internet để giải quyết một lỗi config.
5. Phải dùng xác thực, ủy quyền, mạng quản trị riêng và chính sách hiển thị giá trị phù hợp.

Chỉ nên mở endpoint cần thiết, trong môi trường có kiểm soát, rồi đóng hoặc thu hẹp quyền sau khi điều tra.

Không nên tắt sanitization chỉ để “xem hết mọi giá trị” trong production. Với secret, xác minh sự hiện diện/trạng thái qua cơ chế an toàn thay vì yêu cầu phản hồi rõ token.

## 31. Khác biệt giữa log Config Data và log binding

Sau khi Config Data được xử lý, Spring Boot tiếp tục tạo bean cấu hình. Lỗi có thể xuất hiện ở bước này.

Ví dụ:

```yaml
# application-prod.yml
demo:
  timeout: many-seconds
```

Bean mong đợi:

```java
Duration timeout;
```

Có thể xảy ra chuỗi:

```text
Config Data nạp application-prod.yml thành công
                |
                v
Environment có demo.timeout="many-seconds"
                |
                v
Binder tìm demo.timeout
                |
                v
ConversionService cố chuyển String -> Duration
                |
                v
Lỗi chuyển đổi / binding
```

Tệp đã được nạp; lỗi không nằm ở loader. Nếu bạn tiếp tục bật TRACE Config Data mà không xem nguyên nhân conversion, có thể mất thời gian.

Ngược lại, nếu ứng dụng báo Config Data location không tồn tại trước khi tạo bean, sửa annotation `@DurationUnit` sẽ không xử lý được lỗi file thiếu.

**Chẩn đoán theo đúng tầng:** nạp nguồn → chọn giá trị → binding → conversion → validation → tạo bean.

## 32. Phân biệt lỗi thiếu file và lỗi thiếu property

**Thiếu file bắt buộc:**

```yaml
spring:
  config:
    import: "file:./critical-settings.yml"
```

Nếu resource không có, lỗi có thể xảy ra trong Config Data loading.

**Thiếu property bên trong nguồn đã nạp:**

```yaml
# application.yml
demo:
  message: "hello"
```

Bean lại yêu cầu:

```java
@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotNull Duration timeout) {
}
```

Tệp có thể được nạp thành công nhưng `demo.timeout` không được cấp. Nếu validation chạy, bean có thể thất bại vì giá trị bắt buộc bị thiếu.

Sự khác nhau:

| Vấn đề | Dấu hiệu chính | Hướng tìm |
| --- | --- | --- |
| Location Config Data thiếu | Lỗi nạp location/import | Path, prefix `optional:`, quyền đọc |
| File được nạp nhưng property thiếu | Binding hoặc validation báo thiếu | Prefix, khóa, nguồn override, validation |
| Có property sai định dạng | Conversion/binding failure | Kiểu đích, giá trị thô, converter |
| Đúng kiểu nhưng sai giới hạn | Validation failure | `@Min`, `@NotBlank`, constructor invariant |

Một log INFO “profile prod đã active” không chứng minh mọi property bắt buộc của production đã tồn tại.

## 33. Phân biệt lỗi tên khóa sai với lỗi giá trị sai

Bean:

```java
@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @Min(1) int maxAttempts) {
}
```

Trường hợp A:

```yaml
demo:
  max-attemps: 4
```

Khóa `max-attemps` bị sai chính tả. Binder không tự hiểu đây là `max-attempts` trong mọi trường hợp.

Trường hợp B:

```yaml
demo:
  max-attempts: many
```

Tên đúng, giá trị không chuyển được thành `int`.

Trường hợp C:

```yaml
demo:
  max-attempts: -5
```

Tên đúng, số nguyên hợp lệ về kiểu nhưng sai ràng buộc `@Min(1)`.

Ba trường hợp có thể tạo ra lỗi khởi động khác nhau.

Nếu muốn tăng khả năng phát hiện khóa lạ trong một prefix được bind, có thể cân nhắc:

```java
@ConfigurationProperties(
        prefix = "demo",
        ignoreUnknownFields = false)
```

Nhưng cơ chế này **không phải trình kiểm tra tất cả các khóa từ mọi nguồn**. Nếu gõ sai chính prefix `demo` thành `dmeo`, bean prefix `demo` có thể không thấy nhóm mới đó.

TRACE Config Data giúp biết tài liệu nào được nạp, không tự xác nhận mọi khóa trong tài liệu đều được bean đọc đúng.

## 34. Thứ tự ưu tiên nguồn có thể che một file đúng

Tệp chung:

```yaml
demo:
  timeout: 5s
```

Tệp prod:

```yaml
demo:
  timeout: 10s
```

Biến môi trường:

```text
DEMO_TIMEOUT=30s
```

Đối số dòng lệnh:

```bash
--demo.timeout=750ms
```

Nếu tất cả đều có mặt, thứ tự ưu tiên Spring Boot thông thường có thể khiến giá trị từ CLI thắng các nguồn còn lại.

Điều này không có nghĩa các tài liệu YAML không được nạp. Chúng vẫn có thể góp nhiều khóa khác.

Sơ đồ:

```text
Config Data cơ sở    demo.timeout=5s
Config Data prod      demo.timeout=10s
Environment variable demo.timeout=30s
Command-line property demo.timeout=750ms
                         |
                         v
          Giá trị có hiệu lực: 750ms
                         |
                         v
              Duration.ofMillis(750)
```

Vì vậy khi người vận hành nói “trong application-prod.yml tôi đã đặt 10s”, câu hỏi tiếp theo nên là “trong tiến trình đang chạy, có biến môi trường hoặc CLI nào ghi đè không?”.

## 35. Vì sao logging của Config Data và logging.level từ YAML có thể gây hiểu nhầm?

Giả sử muốn xem TRACE nạp `application-prod.yml`, nhưng lại đặt chính logger level trong `application-prod.yml`:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Một phần quá trình giải quyết Config Data có thể diễn ra trước khi logging configuration đó được áp dụng đầy đủ.

Khi không thấy các thông điệp sớm, không nên suy ra file chưa được nạp. Hãy chuyển logger level sang CLI/JVM option ngay từ khi khởi động:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Sau đó đối chiếu với active profile và PropertySource.

Tuy nhiên, ngay cả khi dùng CLI, những thông điệp được xuất ra vẫn phụ thuộc logger implementation, phiên bản Spring Boot và hành vi bootstrap. Không nên lấy “thiếu một chuỗi TRACE cụ thể” làm bằng chứng duy nhất rằng một file không tồn tại.

## 36. Dùng logger cấp package thay vì chỉ logger của một class

Ví dụ:

```text
org.springframework.boot.context.config
```

là một logger category rộng hơn việc chọn một class cụ thể như:

```text
org.springframework.boot.context.config.ConfigDataEnvironment
```

Bật cả package ở TRACE thường giúp bao phủ hoạt động của những thành phần liên quan hơn, nhất là khi chưa biết chính xác resolver/loader nào xử lý dữ liệu.

Nếu log quá nhiều, bạn có thể thu hẹp category sau khi đã nhận diện khu vực cần điều tra.

**Chú ý:** tên implementation class có thể thay đổi theo version; package logger thường là điểm bắt đầu thực dụng hơn cho chẩn đoán, không phải một public API được đảm bảo bất biến qua mọi bản phát hành.

## 37. Không để TRACE kéo dài trong production

Log TRACE có thể gây:

- Lượng log tăng đáng kể.
- Chi phí lưu trữ, vận chuyển và tìm kiếm log cao hơn.
- Khó phân biệt sự kiện quan trọng giữa nhiều thông điệp nội bộ.
- Khả năng tiết lộ đường dẫn triển khai, location nội bộ, tên tài nguyên hoặc thông tin cấu hình cần bảo vệ.
- Tăng rủi ro nếu có logger/custom code in giá trị nhạy cảm.

Cách làm an toàn:

1. Bật TRACE trong môi trường dev/test trước khi áp dụng production.
2. Nếu cần chạy production, giới hạn phạm vi và thời gian thao tác.
3. Dùng quyền truy cập log phù hợp.
4. Tránh ghi mật khẩu, token, URL có credentials hoặc thông tin nhạy cảm vào thông điệp bổ sung.
5. Thu hẹp logger hoặc trả về INFO sau khi điều tra.
6. Không đưa file log chứa secrets vào ticket hoặc kênh công khai.

**Không nên dùng TRACE làm chế độ vận hành mặc định chỉ để phòng trường hợp có lỗi cấu hình trong tương lai.**

## 38. Kịch bản: chạy từ IDE đúng nhưng java -jar sai

Triệu chứng:

- IDE chạy profile dev, `demo.timeout=2s`.
- JAR nhận `demo.timeout=5s`.
- Cùng repository.

Những giả thuyết cần kiểm tra:

1. IDE có Program argument `--spring.profiles.active=dev` nhưng lệnh JAR không có.
2. IDE được truyền environment variable, còn shell chạy JAR không có.
3. IDE chạy source/resources mới, còn JAR chưa được build lại.
4. JAR khởi động từ working directory khác, nên nạp file ngoài khác.
5. JAR được truyền `spring.config.location` thay thế vị trí mặc định.
6. Có một command-line property ghi đè cấu hình dev.
7. Có tệp `application-dev.yml` bị loại khỏi artifact do cấu hình build.

Quy trình:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Sau đó đọc log profile, các vị trí nạp và giá trị có hiệu lực.

Nếu vẫn khác, xác minh đúng artifact:

```bash
jar tf app.jar
```

và tìm các tài nguyên `application*.yml` trong JAR.

**Không kết luận “Spring Boot đọc YAML khác nhau giữa IDE và JAR” trước khi kiểm tra đầu vào và artifact.**

## 39. Kịch bản: profile prod đã active nhưng file prod không được dùng

Có thể có những nguyên nhân:

- File `application-prod.yml` không được đóng gói hoặc không có ở vị trí được tìm kiếm.
- Bạn đã đặt `spring.config.location` nên các vị trí mặc định bị thay thế.
- File cấu hình thật mang một tên base khác với `application`.
- Có `spring.config.name` trỏ tới tên khác.
- Một tài liệu có `spring.config.activate.on-profile` không thỏa điều kiện.
- Có Config Data location ngoài với ưu tiên cao hơn.
- Có command-line hoặc environment property ghi đè giá trị của file prod.
- Bạn đang đọc log của một tiến trình khác.

Để phân biệt:

1. Kiểm tra active profile thực tế.
2. Bật TRACE cho `org.springframework.boot.context.config` từ startup.
3. Xem location và resource được xử lý.
4. Liệt kê PropertySource names.
5. Đọc giá trị hiệu lực của một khóa minh họa không nhạy cảm.
6. Kiểm tra JAR và filesystem nếu resource mong đợi không được tìm thấy.

Chỉ khi xác định được tầng lỗi mới sửa. Tự thêm một `@PropertySource` hoặc một `EnvironmentPostProcessor` mới chỉ vì file prod “không ăn” có thể làm hệ thống phức tạp hơn mà không giải quyết nguyên nhân.

## 40. Kịch bản: application.yml đã có spring.config.import nhưng không thấy giá trị

Ví dụ:

```yaml
spring:
  config:
    import: "optional:file:./feature-flags.yml"
```

Một số nguyên nhân:

1. `feature-flags.yml` không tồn tại ở working directory đang dùng.
2. Import là optional nên Spring tiếp tục mà không tải file thiếu.
3. Tài liệu chứa import không được áp dụng theo profile.
4. File có nội dung nhưng không khai báo khóa bạn đang tìm.
5. Khóa bị ghi đè bởi một nguồn ưu tiên cao hơn.
6. File được nạp nhưng binder không nhận ra tên property.
7. Đường dẫn được hiểu tương đối với ngữ cảnh Config Data khác dự đoán.

Các câu hỏi trong log:

- Location `feature-flags.yml` có được xét không?
- Có dấu hiệu không tìm thấy resource không?
- Có tài liệu import nào thực sự được áp dụng không?
- Bean configuration properties nhận giá trị gì?

**Không nên chỉ nhìn `optional:` rồi kết luận Spring Boot “đã nạp thành công”.** `optional:` cho phép thiếu location theo quy tắc tương ứng; nó không xác nhận file hiện diện.

## 41. Kịch bản: lỗi profile-specific document chứa spring.profiles.active

Ví dụ không nên làm:

```yaml
# application-prod.yml
spring:
  profiles:
    active: "prod"
```

Một tài liệu chỉ được nạp khi `prod` hoạt động không phải nơi thích hợp để tuyên bố kích hoạt lại profile đó.

Spring Boot hạn chế việc đặt các thuộc tính như `spring.profiles.active` và `spring.profiles.include` trong các tài liệu profile-specific hoặc tài liệu được kích hoạt theo profile.

Cách đúng thường là:

```bash
java -jar app.jar --spring.profiles.active=prod
```

và:

```yaml
# application-prod.yml
demo:
  timeout: 10s
```

Nếu gặp lỗi về profile activation trong Config Data, xem vị trí khai báo các thuộc tính profile thay vì chỉ cố tăng mức logging.

Log TRACE có thể hỗ trợ chỉ ra tài liệu liên quan, nhưng **sửa hợp đồng khai báo profile** mới giải quyết lỗi.

## 42. Kịch bản: có nhiều profile và khóa bị ghi đè

Giả sử:

```yaml
# application-dev.yml
demo:
  mode: "development"
  timeout: 2s
```

```yaml
# application-debug.yml
demo:
  mode: "debug"
  timeout: 1s
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev,debug
```

Tùy quy tắc áp dụng profile-specific Config Data và các nguồn khác, một trong hai tài liệu có thể đóng góp giá trị có hiệu lực cho `demo.timeout`.

Để xác nhận chính xác:

1. Ghi lại thứ tự active profiles.
2. Kiểm tra file/thư mục thực tế được nạp.
3. Xác định những PropertySource chứa `demo.timeout`.
4. Xem nguồn nào đứng trước trong Environment.
5. Đọc giá trị cuối cùng trên bean/Environment.

Không nên ghi câu “profile dev luôn thắng debug” hoặc ngược lại mà không xét cách tổ chức tài liệu và thứ tự áp dụng trong hệ thống đang chạy.

Nếu cần một giá trị tuyệt đối, có thể chuyển quy tắc môi trường sang một nguồn có ưu tiên được kiểm soát rõ ràng thay vì dựa vào thứ tự khó hiểu.

## 43. Kịch bản: dùng @PropertySource và mong thấy trong Config Data TRACE

Spring Framework có annotation:

```java
@Configuration
@PropertySource("classpath:company.properties")
public class CompanyPropertiesConfiguration {
}
```

Cơ chế `@PropertySource` được xử lý trong quá trình xây dựng Spring context, khác với cơ chế Config Data của Spring Boot.

Vì thế, nếu một property được cung cấp bởi `@PropertySource`, log TRACE của package `org.springframework.boot.context.config` **không phải công cụ duy nhất hoặc luôn trực tiếp để quan sát việc xử lý nguồn ấy**.

Khi cần chẩn đoán:

- Xác định nguồn đến từ Config Data hay từ annotation/context.
- Xem danh sách PropertySource trong Environment.
- Lưu ý `@PropertySource` có thể được thêm tương đối muộn, không phù hợp để điều khiển một số thuộc tính khởi động sớm.

Không nên gom mọi cơ chế thêm PropertySource vào cùng một khái niệm “Config Data loader”.

## 44. Kịch bản: EnvironmentPostProcessor thêm nguồn tùy chỉnh

Một ứng dụng có thể có:

```java
public final class CompanySettingsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "companyOverrides",
                        Map.of("demo.timeout", "30s")
                )
        );
    }
}
```

Đoạn này minh họa logic của một `EnvironmentPostProcessor`; để được Spring Boot gọi, processor còn phải được đăng ký theo SPI tương ứng.

Nếu nguồn `companyOverrides` được đưa lên đầu và chứa `demo.timeout`, giá trị có thể thắng cả tài liệu Config Data.

Trong tình huống ấy, TRACE nạp `application-prod.yml` có thể xác nhận file đã được load, nhưng **timeout cuối cùng vẫn là `30s` từ PropertySource tùy chỉnh**.

Đây là nguyên nhân thứ hai để không coi Config Data TRACE là một bảng kê toàn bộ thứ tự ưu tiên runtime.

## 45. Khai báo log category ở application.yml

Đối với chẩn đoán nhẹ hơn khi không yêu cầu quan sát sự kiện sớm nhất, có thể dùng:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

trong cấu hình mà Spring Boot có thể đọc.

Hoặc Properties:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

Khi cần quay lại mức bình thường:

```yaml
logging:
  level:
    org.springframework.boot.context.config: INFO
```

Nhưng hãy nhớ:

- Một file YAML phải được nạp trước khi giá trị của nó ảnh hưởng tới logging.
- Nếu file bị thiếu hoặc profile không active, tùy chọn TRACE bên trong file đó có thể không có hiệu lực.
- Các bước bootstrap rất sớm không nhất thiết được ghi lại đầy đủ khi logging level chỉ được cấu hình qua một tài liệu nạp muộn.

Để điều tra chính quá trình Config Data của một profile nghi vấn, **truyền logger level khi khởi động** là cách dễ kiểm soát hơn.

## 46. Tại sao không nên in mọi thuộc tính ra log?

Khi chưa rõ giá trị được chọn từ đâu, một số developer thử:

```java
// Không khuyến nghị:
for (var source : environment.getPropertySources()) {
    System.out.println(source.getSource());
}
```

Lệnh này có thể in toàn bộ nội dung nguồn, bao gồm password, API token, client secret, connection string hoặc thông tin nội bộ.

Ngay cả việc serialize cả bean `@ConfigurationProperties` cũng có thể làm lộ secret nếu bean là record có `toString()` tự sinh.

Cách an toàn hơn:

- In **tên PropertySource**, không in Map giá trị.
- Chỉ đọc một vài khóa đã xác định không nhạy cảm.
- Với secret, chỉ xác nhận nó có mặt hay không bằng một phép kiểm tra có kiểm soát.
- Không gửi log chứa secret sang kênh chung.
- Giữ mức logging và quyền truy cập Actuator phù hợp.

Một lỗi thiếu cấu hình không được biến thành sự cố lộ dữ liệu.

## 47. Chẩn đoán bằng logging khác với validation

Giả sử một record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @Min(1) int maxThreads,
        @NotNull Duration timeout) {
}
```

Config Data:

```yaml
worker:
  max-threads: -4
  timeout: 3s
```

Log TRACE có thể cho thấy tài liệu YAML được nạp thành công. `Duration` cũng có thể được chuyển kiểu thành công. Nhưng `maxThreads=-4` vi phạm `@Min(1)` khi validation được thực thi với provider phù hợp.

Đây không phải lỗi nạp Config Data.

Một quy trình chẩn đoán tách bạch:

```text
Config Data: file đã nạp? ----------> Có
Environment: khóa đã có? ----------> Có
Binding: "3s" thành Duration? ------> Có
Validation: maxThreads >= 1? -------> Không
Kết quả: bean cấu hình thất bại
```

Sửa một vấn đề validation bằng cách đổi `spring.config.location` là đi sai hướng.

## 48. Kiểm thử profile trong ApplicationContext

Nếu muốn xác nhận thực tế một profile được kích hoạt và tài liệu tương ứng được nạp, có thể tạo integration test.

Ví dụ:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DevProfileConfigurationTest {

    @Autowired
    private Environment environment;

    @Autowired
    private DemoProperties properties;

    @Test
    void devProfileIsActive() {
        assertThat(environment.getActiveProfiles())
                .contains("dev");
    }

    @Test
    void devDocumentProvidesExpectedValues() {
        assertThat(properties.message())
                .isEqualTo("development");
    }
}
```

Test này giả định có các file `application.yml`/`application-dev.yml` và record `DemoProperties` được đăng ký như ví dụ trước.

Nếu một nguồn test property ghi đè `demo.message`, assertion cần phản ánh tập nguồn thực tế. Vì thế một integration test nên kiểm soát đầu vào để tránh phụ thuộc vô tình vào cấu hình developer.

**Điểm khác biệt:** test trên kiểm tra một behavior runtime của profile và binding, trong khi đọc log TRACE chủ yếu là kỹ thuật chẩn đoán khi hệ thống đang chạy.

## 49. Kiểm thử một ứng dụng chạy với profile prod

Một test khác:

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProductionConfigurationTest {

    @Autowired
    private DemoProperties properties;

    @Test
    void usesProductionTimeout() {
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(10));
    }
}
```

Để đoạn này biên dịch, cần import tương ứng cho JUnit, AssertJ, `Duration`, Spring Boot Test và dependency test như trong dự án.

Test dựa trên dữ liệu ví dụ:

```yaml
# application-prod.yml
demo:
  timeout: 10s
```

Nó không xác nhận thư mục triển khai production có đúng path hay secret hay không; đó là phạm vi của integration/smoke test ở môi trường triển khai.

Nếu mục tiêu là xác định nguyên nhân **lần chạy JAR production** nhận giá trị khác, hãy so sánh log và PropertySource của chính tiến trình production thay vì chỉ dựa vào test dùng classpath của dự án.

## 50. Kiểm tra profile khi chạy java -jar thật

Đối với artifact đã build, dùng cùng một câu lệnh chuẩn trong tài liệu vận hành:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Sau đó:

1. Xem INFO profile.
2. Tìm các sự kiện Config Data.
3. Xem ứng dụng có nạp file ngoài mong đợi không.
4. Xem startup có lỗi loader/binder/validation hay không.
5. Xem giá trị không nhạy cảm trong runner hoặc một công cụ quan sát đã được bảo vệ.
6. Khi đã có kết luận, tắt TRACE hoặc quay lại mức log bình thường.

Nếu trong một deployment nhiều replica chỉ một replica lỗi, cần gắn log với **instance/pod/container** cụ thể. Có thể hai replica chạy khác version hoặc khác environment variables.

Đọc một dòng profile không có thông tin định danh tiến trình trong hệ thống phân tán dễ tạo kết luận sai.

## 51. Log của Docker/Kubernetes và profile thật

Một container có thể được chạy với:

```text
SPRING_PROFILES_ACTIVE=prod
```

nhưng không nên giả định biến đó chắc chắn đã vào đúng container chỉ vì file manifest hoặc Docker Compose config có nhắc tới nó.

Các điểm kiểm tra:

- Biến có được truyền vào tiến trình Java cuối cùng không?
- Có entrypoint script sửa hoặc xóa biến không?
- Có đối số command-line ghi đè active profile không?
- Working directory/container filesystem có chứa external config path không?
- File mount có thành công không?
- Có nhiều replica hoặc revision đang cùng chạy không?

Trong môi trường nhiều instance, log của ứng dụng là một bằng chứng về **profile mà tiến trình thực sự nhận**, nhưng để xác định vì sao profile có giá trị ấy còn cần xem cấu hình container và launch command.

Không nên in toàn bộ environment của container vào log để điều tra nếu nó chứa secret.

## 52. Bật logging qua biến môi trường có thể gặp vấn đề đặt tên

Spring Boot hỗ trợ relaxed binding của environment variables. Tuy nhiên, các property dạng logging category có dấu chấm/phân biệt chữ hoa khi biểu diễn tên class cần được xử lý cẩn thận.

Ví dụ category package:

```text
logging.level.org.springframework.boot.context.config
```

có thể được biểu diễn bằng cơ chế môi trường phù hợp trong nhiều trường hợp, nhưng những logger class phân biệt chữ hoa/chữ thường có thể gây khó khăn nếu chuyển toàn bộ tên thành uppercase environment variable.

Để chẩn đoán dễ tái lập, **CLI hoặc Java system property với tên category đầy đủ** thường rõ ràng hơn:

```bash
--logging.level.org.springframework.boot.context.config=TRACE
```

hoặc:

```bash
-Dlogging.level.org.springframework.boot.context.config=TRACE
```

Nó giữ lại chính xác dấu chấm và tên logger.

## 53. Chú ý dữ liệu về profile do code tự kích hoạt

Ngoài property `spring.profiles.active`, mã khởi động hoặc test có thể thêm profile thông qua API cấu hình Environment.

Ví dụ ở mức khái niệm:

```java
ConfigurableEnvironment environment = ...;
environment.addActiveProfile("debug");
```

Nếu thay đổi được thực hiện đúng thời điểm, tập profile Environment có thể khác với giá trị chỉ đọc từ một property đơn.

Tuy nhiên **không nên thay đổi active profile sau khi Config Data đã được phân giải rồi giả định Spring Boot sẽ tự nạp lại mọi tài liệu profile-specific**.

Khi phát hiện active profiles trong log nhiều hơn mong đợi, hãy kiểm tra custom initializer, environment post-processor, test annotations và cách SpringApplication được cấu hình.

Thay đổi profile ở một điểm quá muộn cũng có thể tạo trạng thái khó suy luận giữa active profiles và những tài liệu đã nạp.

## 54. Tại sao đổi profile lúc chạy không tự nạp lại Config Data?

Config Data được chuẩn bị trong giai đoạn khởi động. Khi ứng dụng đã chạy, bạn có thể sửa một environment variable trong shell khác hoặc thay tệp YAML trên đĩa, nhưng không nên giả định Spring Boot sẽ tự động:

1. Nhận sự thay đổi.
2. Tính lại active profile.
3. Tải lại tất cả Config Data documents.
4. Áp dụng lại thứ tự nguồn.
5. Rebind toàn bộ `@ConfigurationProperties`.
6. Tái tạo các service đã sử dụng giá trị cũ.

Để có refresh động, ứng dụng cần cơ chế riêng, ví dụ một giải pháp configuration refresh được thiết kế và kiểm thử. Việc đổi một tệp trên filesystem không tương đương một lần khởi động mới.

Vì thế, khi log startup ghi `prod`, một người sau đó thay environment variable thành `dev` ở một terminal khác **không chứng minh ứng dụng đang dùng dev**.

Nếu muốn xác nhận profile hiện tại, đọc Environment của **tiến trình đang chạy**, không chỉ biến trong shell người quan sát.

## 55. Khi nào nên dùng --trace thay vì logger category?

Spring Boot cũng có tùy chọn chẩn đoán logging toàn cục trong một số cách chạy, ví dụ:

```bash
java -jar app.jar --trace
```

Tuy nhiên việc bật trace tổng quát có thể làm lượng log tăng mạnh và không nhất thiết tập trung vào đúng phần Config Data.

Khi mục tiêu đã rõ là **xem quá trình nạp cấu hình**, ưu tiên bật đúng category:

```text
org.springframework.boot.context.config=TRACE
```

Nếu cần thêm thông tin của logging startup, có thể bổ sung các logger khác theo kết quả điều tra, thay vì mở toàn bộ log TRACE không kiểm soát.

Không coi `--trace` hoặc `--debug` là một công cụ “in ra mọi giá trị của Config Data” — chúng thay đổi mức ghi log, chứ không biến Spring Boot thành một trình giải thích hoàn chỉnh cho mỗi key.

## 56. Cách ghi lại bằng chứng chẩn đoán để nhóm khác tái hiện

Một báo cáo lỗi cấu hình tốt nên có:

| Thông tin | Ví dụ |
| --- | --- |
| Tên ứng dụng/artifact | `config-demo.jar` |
| Phiên bản/commit | Một định danh build đã xác nhận |
| Thời gian và instance | Thời điểm startup, pod/container |
| Active/default profiles | `[prod]` / `[default]` |
| Lệnh khởi chạy đã bỏ secrets | `java -jar app.jar --spring.profiles.active=prod` |
| Working directory | `/opt/team` |
| Config Data locations | Tên/vị trí không nhạy cảm |
| Khóa gặp vấn đề | `demo.timeout` |
| Kiểu đích | `Duration` |
| Giá trị đã che nếu nhạy cảm | Không đưa token/password vào ticket |
| Lỗi log chính | Ví dụ loại exception, tên key |
| Kết quả mong đợi | `10s` |
| Kết quả thực tế | `750ms` |
| PropertySource khả nghi | Tên nguồn có ưu tiên cao hơn |

Không cần gửi toàn bộ TRACE log nếu những đoạn ấy chứa quá nhiều thông tin môi trường hoặc credentials. Chọn đoạn hỗ trợ chẩn đoán với sự kiểm soát thông tin.

## 57. Bảng phân biệt công cụ chẩn đoán

| Triệu chứng | Công cụ đầu tiên nên dùng |
| --- | --- |
| Không biết profile đang active | Startup INFO log, `Environment#getActiveProfiles()` |
| Nghi file profile chưa nạp | Config Data TRACE |
| Nghi spring.config.import sai đường dẫn | Config Data TRACE và lỗi location |
| Nghi nguồn ngoài JAR bị bỏ qua | Working directory, location, Config Data TRACE |
| File được nạp nhưng giá trị lạ | Danh sách PropertySource, `Environment#getProperty()` |
| CLI/env có thể ghi đè YAML | Kiểm tra thứ tự nguồn và đầu vào tiến trình |
| Sai kiểu Duration/DataSize/Integer | Binding/conversion exception |
| Giá trị âm hoặc chuỗi trống | Bean Validation/constructor invariant |
| Auto-configuration không kích hoạt | Condition Evaluation Report, `--debug` |
| Bean @ConfigurationProperties không tồn tại | ConfigurationPropertiesScan/EnableConfigurationProperties |
| Giá trị có trong repo nhưng JAR không có | `jar tf`, artifact/version |
| Giá trị thay đổi mà bean không đổi | Thời điểm binding và cơ chế refresh |

Khi biết đúng công cụ, quá trình tìm nguyên nhân sẽ ngắn hơn và tránh sửa sai tầng.

## 58. Bài tập A: không có active profile

Bạn thấy log có ý nghĩa:

```text
No active profile set, falling back to 1 default profile: "default"
```

Tệp `application.yml` có:

```yaml
demo:
  message: "base"
```

**Câu hỏi:** có thể kết luận Spring Boot không nạp `application.yml` không?

**Đáp án:** không. Không có active profile không đồng nghĩa không nạp tài liệu cơ sở. Các tài liệu mặc định vẫn có thể tham gia Config Data.

## 59. Bài tập B: profile prod nhưng timeout không phải 10s

Tệp `application-prod.yml`:

```yaml
demo:
  timeout: 10s
```

Lệnh chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --demo.timeout=500ms
```

**Câu hỏi:** nếu bean nhận timeout 500ms, có chứng minh file prod không nạp không?

**Đáp án:** không. Command-line property thông thường có độ ưu tiên cao hơn Config Data, nên file prod có thể đã nạp nhưng giá trị bị ghi đè.

## 60. Bài tập C: bật TRACE đúng category

**Yêu cầu:** chạy JAR với profile dev và mở log TRACE của Config Data.

Lệnh:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

**Câu hỏi:** vì sao không chỉ dùng `--debug`?

**Đáp án:** `--debug` phục vụ nhiều thông tin gỡ lỗi và Condition Evaluation Report; khi mục tiêu là Config Data processing, đặt đúng logger category TRACE trực tiếp hơn.

## 61. Bài tập D: import optional

Tệp:

```yaml
spring:
  config:
    import: "optional:file:./extra.yml"
```

Không tồn tại `./extra.yml`.

**Câu hỏi:** có thể khởi động tiếp mà không có file import không?

**Đáp án:** có thể, vì tiền tố optional cho phép thiếu location theo cơ chế tương ứng. Tuy nhiên, nếu ứng dụng còn có bean bắt buộc một khóa chỉ file đó cung cấp, nó vẫn có thể lỗi ở bước binding/validation.

## 62. Bài tập E: tài liệu có on-profile

Tệp:

```yaml
demo:
  message: "base"
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  message: "production"
```

Chạy không kích hoạt `prod`.

**Câu hỏi:** document thứ hai có tự khiến prod hoạt động không?

**Đáp án:** không. `spring.config.activate.on-profile` đặt điều kiện áp dụng document, không tự kích hoạt profile.

## 63. Bài tập F: working directory

Có file:

```text
/opt/apps/config/application.yml
```

Người A chạy:

```bash
cd /opt/apps
java -jar my-service.jar
```

Người B chạy:

```bash
cd /home/user
java -jar /opt/apps/my-service.jar
```

**Câu hỏi:** hai lần chạy có chắc dùng cùng `./config/application.yml` không?

**Đáp án:** không. Đường dẫn tương đối dựa trên working directory của tiến trình. Nếu yêu cầu cùng file, dùng location tuyệt đối hoặc chuẩn hóa working directory.

## 64. Bài tập G: phân biệt ba loại lỗi

**Tình huống 1**

```yaml
spring:
  config:
    import: "file:./missing-required.yml"
```

File không tồn tại.

**Tình huống 2**

```yaml
demo:
  timeout: not-a-duration
```

Bean cần `Duration`.

**Tình huống 3**

```yaml
demo:
  retries: -3
```

Bean cần `@Min(1) int retries`.

Đáp án:

1. Lỗi liên quan Config Data location/import nếu location bắt buộc không tồn tại.
2. Lỗi conversion/binding vì chuỗi không chuyển được thành `Duration`.
3. Lỗi validation khi giá trị số đúng kiểu nhưng vi phạm `@Min(1)`.

TRACE Config Data là công cụ quan trọng cho tình huống 1, nhưng không thay thế việc xem exception của tình huống 2 và 3.

## 65. Bài tập H: profile nhóm và số lượng profile

Tệp cơ sở:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

Lệnh:

```bash
java -jar app.jar --spring.profiles.active=production
```

**Câu hỏi:** tại sao log có thể báo nhiều profile hoạt động thay vì chỉ `production`?

**Đáp án:** vì group có thể kích hoạt thêm các profile thành viên theo cơ chế Spring Boot. Hãy kiểm tra tập active profiles thực tế qua Environment và log.

## 66. Bài tập I: log TRACE không có dòng cho file import

Bạn bật logger Config Data TRACE và tìm tên `local-settings.yml` nhưng không thấy.

**Câu hỏi:** đã đủ cơ sở khẳng định file không được nạp chưa?

**Chưa.** Mức độ chi tiết và cách diễn đạt log phụ thuộc phiên bản/logger; ngoài ra cần kiểm tra đúng tiến trình, đúng cách bật log, liệu source có thực sự khai báo import và giá trị hiệu lực có đến từ file hay không.

Nên kết hợp log với kiểm tra cấu hình khởi chạy, PropertySource và lỗi khi resource bắt buộc không tồn tại.

## 67. Quy trình tổng hợp: từ một lỗi cấu hình tới nguyên nhân

Khi người vận hành báo “ứng dụng production dùng sai cấu hình”, có thể thực hiện:

1. **Định danh đúng tiến trình:** tên service, JAR/image, instance, timestamp.
2. **Xác nhận profile:** đọc INFO log, `Environment#getActiveProfiles()`, đồng thời xem default profiles khi cần.
3. **Xác nhận đầu vào khởi chạy:** CLI, JVM properties, environment variables, working directory, profile groups/includes.
4. **Bật Config Data TRACE đúng category:** `org.springframework.boot.context.config=TRACE` từ nguồn khởi động sớm nếu cần.
5. **Xác nhận vị trí nguồn:** classpath, external files, additional-location, location, import.
6. **Phân biệt nguồn đã khám phá với tài liệu được áp dụng.**
7. **Xác nhận PropertySource có hiệu lực và thứ tự ưu tiên.**
8. **Đối chiếu một khóa không nhạy cảm:** giá trị ở Environment và bean cấu hình.
9. **Kiểm tra lỗi binder/validation nếu bean không được tạo.**
10. **Sửa đúng tầng gây lỗi:** profile, location, precedence, key spelling, type hoặc constraint.
11. **Khởi động lại bằng cùng phương pháp có thể tái lập**, trừ khi hệ thống có cơ chế refresh riêng được thiết kế rõ.
12. **Tắt log TRACE không cần thiết và bảo vệ chứng cứ chẩn đoán.**

Một lỗi khó không nhất thiết cần nhiều log hơn; nó cần log **đúng giai đoạn và đúng trách nhiệm**.

## 68. Tổng kết

- Log INFO khởi động thường cho biết active profile hoặc default profile. **Không có active profile không nghĩa là không nạp `application.yml`.**
- Active profiles, default profiles và Config Data documents là các khái niệm liên quan nhưng **không đồng nghĩa**.
- Bật **`logging.level.org.springframework.boot.context.config=TRACE`** để quan sát quá trình xử lý Config Data trong những phiên bản Spring Boot có nhóm logger tương ứng.
- Khi muốn xem các sự kiện chuẩn bị cấu hình sớm, ưu tiên cấp logger level bằng CLI hoặc JVM system property **ngay lúc khởi động**.
- **`--debug` không phải thay thế trực tiếp cho Config Data TRACE.** Nó còn phục vụ việc điều tra auto-configuration/condition report.
- `spring.config.activate.on-profile` chỉ kiểm soát điều kiện của tài liệu; nó không tự kích hoạt profile.
- `spring.config.import`, `spring.config.location`, `spring.config.additional-location` và working directory ảnh hưởng việc tìm, nạp tài liệu.
- **File đã được nạp không đồng nghĩa giá trị của file sẽ thắng.** CLI, system properties, environment variables và các nguồn có ưu tiên cao hơn có thể ghi đè.
- Có thể liệt kê tên PropertySource qua `ConfigurableEnvironment` và đọc một khóa không nhạy cảm để đối chiếu với log.
- Đọc log Config Data **không thay thế** việc phân tích lỗi binding, chuyển đổi kiểu và Bean Validation.
- Khi xem log ở production, hạn chế phạm vi TRACE, che secret và bảo vệ các endpoint/diagnostic output.
- Quy trình đáng tin cậy là **xác định tiến trình → xác nhận profile → xem Config Data → đối chiếu nguồn ưu tiên → kiểm tra bean và lỗi → sửa đúng tầng**.
