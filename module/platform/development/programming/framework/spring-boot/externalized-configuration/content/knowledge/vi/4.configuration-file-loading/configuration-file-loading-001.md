# Các vị trí tìm `application.properties` và `application.yaml` mặc định trong Spring Boot

## 1. Mục tiêu và bối cảnh

Spring Boot cho phép một ứng dụng sử dụng cấu hình nằm trong JAR và cấu hình nằm bên ngoài JAR. Vì vậy, một file `application.yaml` trong mã nguồn không nhất thiết là nơi duy nhất cung cấp giá trị, và một file `application.properties` nằm cạnh JAR cũng không chắc được đọc nếu tiến trình được khởi động từ thư mục khác.

Bài này nằm trong nhóm **Tìm và nạp tệp** của **Spring Boot Externalized Configuration**. Trọng tâm là các **vị trí tìm file mặc định** của cơ chế Config Data trong Spring Boot 3.3.x. Đây là một phần của cơ chế Externalized Configuration; các nguồn như biến môi trường, Java system property và đối số dòng lệnh cũng có thể tác động đến giá trị hiệu lực nhưng không phải là vị trí tìm file mặc định.

Sau khi thực hành, bạn có thể:

- Nêu đúng năm vị trí Spring Boot tìm `application.properties`, `application.yaml` và `application.yml` nếu không chỉnh location.
- Phân biệt đường dẫn classpath, đường dẫn tương đối với working directory và đường dẫn wildcard.
- Dự đoán file nào sẽ ghi đè khi nhiều vị trí cùng định nghĩa một khóa.
- Hiểu vì sao cùng một JAR chạy ở hai thư mục có thể nhận cấu hình khác nhau.
- Viết ứng dụng quan sát `Environment` và chạy các thí nghiệm lặp lại được.
- Giải thích tác động khác nhau của `spring.config.name`, `spring.config.location` và `spring.config.additional-location`.
- Nhận diện lỗi thường gặp về tên file, profile, thư mục chạy và thứ tự ưu tiên.

## 2. Năm vị trí mặc định

Spring Boot tìm những file có tên cơ sở mặc định `application` ở các location sau, theo thứ tự được xử lý:

| Thứ tự | Location | File ví dụ |
| --- | --- | --- |
| 1 | `classpath:/` | `classpath:/application.yaml` |
| 2 | `classpath:/config/` | `classpath:/config/application.properties` |
| 3 | `file:./` | `./application.properties` |
| 4 | `file:./config/` | `./config/application.yaml` |
| 5 | `file:./config/*/` | `./config/team-a/application.yaml` |

**Thứ tự quan trọng:** trong tập file mặc định này, location được xử lý sau có thể ghi đè giá trị cùng khóa từ location trước. Ví dụ, nếu một khóa cùng xuất hiện ở file trong JAR và `./config/application.yaml`, giá trị bên ngoài thường thắng khi không có nguồn cấu hình ưu tiên cao hơn hoặc thiết lập location đặc biệt.

Đừng hiểu bảng trên là năm file bắt buộc. Mỗi location có thể không tồn tại; Spring Boot vẫn có thể khởi động. Nếu nhiều file được nạp, các khóa không trùng nhau được tổng hợp. Khi trùng khóa, thứ tự ưu tiên quyết định giá trị hiệu lực.

```text
      NGUỒN TRONG CLASSPATH                     NGUỒN BÊN NGOÀI JAR
      ---------------------                     ------------------
        classpath:/                                file:./
        classpath:/config/                         file:./config/
                                                   file:./config/*/
                    \                              /
                     \                            /
                      +------ Config Data --------+
                                   |
                                   v
                         Spring Environment
                                   |
                                   v
                         Giá trị ứng dụng dùng
```

### 2.1. `classpath:/` là gì?

Đây là gốc classpath của tiến trình Spring Boot. Trong dự án Gradle hoặc Maven thông thường, file:

```text
src/main/resources/application.yaml
```

được đưa vào classpath sau khi build. Trong executable JAR kiểu chuẩn của Spring Boot, tài nguyên ứng dụng thường nằm ở:

```text
BOOT-INF/classes/application.yaml
```

`src/main/resources` là **đường dẫn lúc phát triển**, không phải một location runtime mà Spring Boot tự quét theo tên đó. Khi chạy JAR, Spring Boot đọc tài nguyên thông qua classpath.

### 2.2. `classpath:/config/` là gì?

Nếu dự án có:

```text
src/main/resources/config/application.properties
```

thì file này trở thành tài nguyên ở location:

```text
classpath:/config/application.properties
```

và thường được đóng gói ở `BOOT-INF/classes/config/application.properties`. Đặt cấu hình trong thư mục `config` thuộc resources vẫn là **đóng gói trong ứng dụng**; nó khác thư mục `config` nằm ngoài JAR.

Trong bảng thứ tự mặc định, `classpath:/config/` đứng sau `classpath:/`. Khi cả hai nơi có cùng khóa và không có nguồn mạnh hơn, file tại `classpath:/config/` có thể quyết định giá trị hiệu lực.

### 2.3. `file:./` là gì?

`file:` chỉ file hoặc thư mục trên filesystem. Dấu `.` nghĩa là **working directory của tiến trình lúc chạy**.

Ví dụ:

```bash
cd /srv/run
java -jar /opt/apps/my-app.jar
```

Spring Boot sẽ tìm file `file:./application.properties` tương ứng với:

```text
/srv/run/application.properties
```

chứ không tự động chuyển sang `/opt/apps/application.properties` chỉ vì JAR nằm ở đó.

Đây là nguồn gây nhầm lẫn lớn trong vận hành: IDE, Gradle `bootRun`, terminal, Docker và systemd có thể thiết lập working directory khác nhau. Hãy kiểm tra giá trị `user.dir` hoặc cấu hình working directory của launcher.

### 2.4. `file:./config/` là gì?

Nếu tiến trình có working directory `/srv/run`, Spring Boot có thể đọc:

```text
/srv/run/config/application.properties
/srv/run/config/application.yaml
/srv/run/config/application.yml
```

Đây là cách phổ biến để đặt cấu hình bên ngoài JAR. File được chỉnh riêng theo môi trường mà không cần đóng gói lại mã ứng dụng. Tuy nhiên, sau khi sửa file, ứng dụng trong bài học này cần **khởi động lại** để nạp lại config data; không mặc nhiên có hot reload.

### 2.5. `file:./config/*/` là gì?

`*` là ký hiệu wildcard để mở rộng **các thư mục con trực tiếp** của `./config/`. Ví dụ:

```text
working-dir/
└── config/
    ├── team-a/
    │   └── application.yaml         # được tìm
    ├── team-b/
    │   └── application.properties   # được tìm
    └── team-c/
        └── nested/
            └── application.yaml     # không được tìm trực tiếp
```

Wildcard mặc định chỉ đi một cấp thư mục dưới `./config/`, không quét đệ quy vô hạn. Cơ chế wildcard location như thế này áp dụng cho nguồn bên ngoài classpath. Nếu có nhiều thư mục con, các location wildcard được sắp xếp theo đường dẫn tuyệt đối theo thứ tự chữ cái. Cần tránh khai báo trùng khóa ở nhiều thư mục con khi không chủ đích quản lý thứ tự ưu tiên.

## 3. Tên file và định dạng được nhận diện

Tên cơ sở mặc định là `application`. Các tên file thông dụng được hỗ trợ:

```text
application.properties
application.yaml
application.yml
```

`application.properties` dùng cú pháp key-value:

```properties
lab.origin=packaged-root
lab.retry-count=3
lab.feature-enabled=true
```

`application.yaml` biểu diễn cùng dữ liệu:

```yaml
lab:
  origin: packaged-root
  retry-count: 3
  feature-enabled: true
```

Cả hai có thể nạp vào `Environment`. Tuy nhiên, khi đồng thời có `.properties` và YAML ở **cùng một location**, Spring Boot ưu tiên `.properties`. Nên dùng một định dạng chủ đạo cho từng location và hạn chế để hai file cùng khai báo một khóa.

Khi kích hoạt profile, ví dụ `dev`, Spring Boot còn xét các file profile-specific cùng cơ chế tìm location:

```text
application-dev.properties
application-dev.yaml
application-dev.yml
```

Tên `application-dev.yaml` không tự động kích hoạt `dev`. Bạn cần cấu hình profile đang hoạt động, chẳng hạn khi chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Khi nhiều profile hoặc nhiều location group được dùng, ưu tiên có thể phức tạp hơn danh sách năm dòng cơ bản. Bài này giữ một profile và một nhóm location mặc định để tập trung vào việc tìm file.

## 4. Ví dụ về cách các file được kết hợp

Giả sử có cùng một khóa `lab.origin` trong năm file:

| File | Giá trị của `lab.origin` |
| --- | --- |
| `classpath:/application.yaml` | `packaged-root` |
| `classpath:/config/application.yaml` | `packaged-config` |
| `file:./application.properties` | `external-root` |
| `file:./config/application.yaml` | `external-config` |
| `file:./config/team-a/application.properties` | `external-team-a` |

Nếu đang dùng location mặc định, không có profile hoặc nguồn ghi đè khác, kết quả mong đợi là:

```text
lab.origin = external-team-a
```

Nguồn nằm ở location được xét sau ghi đè **khóa trùng**. Các thuộc tính khác có thể vẫn đến từ các file đứng trước. Ví dụ, nếu chỉ file `classpath:/application.yaml` định nghĩa `lab.retry-count=3`, giá trị ấy vẫn có thể được sử dụng dù `lab.origin` đến từ file bên ngoài.

Điểm cần nhớ là **tìm file** và **chọn giá trị hiệu lực** là hai giai đoạn liên quan nhưng khác nhau. Đừng kết luận một file đã bị bỏ qua chỉ vì thuộc tính của nó bị một nguồn khác ghi đè.

## 5. Tạo ứng dụng mẫu để quan sát location

Ta tạo một ứng dụng console tối giản có tên `config-locations`. Nó dùng Java 21, Spring Boot 3.3.x và Gradle. Ứng dụng in working directory, profile đang hoạt động, giá trị hiệu lực của `lab.origin` và tên những `PropertySource` có thể cung cấp khóa này. Không cần mở HTTP endpoint.

Cấu trúc:

```text
config-locations/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    └── main/
        ├── java/dev/example/configlocations/
        │   └── ConfigLocationsApplication.java
        └── resources/
            ├── application.yaml
            └── config/
                └── application.yaml
```

Có thể tạo bộ khung bằng Spring Initializr, chọn Java, Gradle và Spring Boot tương thích với 3.3.x; giữ Gradle Wrapper do dự án sinh ra. File `settings.gradle`:

```groovy
rootProject.name = 'config-locations'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu bạn đang ở trong repository quản lý phiên bản plugin tập trung, dùng phiên bản và cấu trúc Gradle của repository đó.

### 5.1. Mã in bằng chứng từ `Environment`

`src/main/java/dev/example/configlocations/ConfigLocationsApplication.java`:

```java
package dev.example.configlocations;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootApplication
public class ConfigLocationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigLocationsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ConfigurableEnvironment environment) {
        return args -> {
            String key = "lab.origin";

            System.out.println("=== CONFIG LOCATIONS ===");
            System.out.println("workingDirectory = "
                    + System.getProperty("user.dir"));
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("effectiveValue = "
                    + environment.getProperty(key, "<missing>"));

            System.out.println("Matching property sources:");
            for (PropertySource<?> source
                    : environment.getPropertySources()) {

                // Bỏ adapter tổng hợp để tập trung vào các
                // PropertySource cụ thể nằm bên dưới.
                if ("configurationProperties".equals(source.getName())) {
                    continue;
                }

                Object value = source.getProperty(key);
                if (value != null) {
                    System.out.println("- " + source.getName()
                            + " => " + value);
                }
            }
        };
    }
}
```

Hai loại kết quả cần phân biệt:

- `effectiveValue` là giá trị Spring `Environment` trả về cho `lab.origin`.
- `Matching property sources` là những nguồn trả về giá trị khi tra cứu trực tiếp khóa này, theo thứ tự duyệt.

Tên hiển thị của nguồn có thể khác theo cách đóng gói và phiên bản. Bộ quan sát này phục vụ **ba kiểu cấu hình đơn giản trong bài lab**; nó không phải công cụ truy vết đầy đủ cho mọi trường hợp relaxed binding, placeholder, import hoặc nguồn cấu hình tùy biến. Vì chỉ in khóa giả lập `lab.origin`, mã mẫu không vô tình xuất toàn bộ secret từ ứng dụng.

### 5.2. Hai file trong classpath

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

lab:
  origin: packaged-root
  retry-count: 3
```

`src/main/resources/config/application.yaml`:

```yaml
lab:
  origin: packaged-config
```

Đặt `web-application-type: none` để ứng dụng console chạy xong có thể kết thúc, không cần cổng HTTP.

Từ thư mục gốc dự án, thực hiện:

macOS/Linux:

```bash
./gradlew bootJar
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
.\gradlew.bat bootRun
```

Nếu ở thư mục gốc không có file ngoài cùng tên cấu hình và không có nguồn ưu tiên cao hơn, kết quả mong đợi:

```text
effectiveValue = packaged-config
```

Bởi vì `classpath:/config/` được xét sau `classpath:/`. Trong kết quả in ra, các source tương ứng có thể chứa cả giá trị `packaged-root` lẫn `packaged-config`, nhưng giá trị hiệu lực là `packaged-config`.

## 6. Thí nghiệm với cùng một JAR

Mỗi lần thay đổi bên dưới, hãy chạy **tiến trình Java mới**. Giữ nguyên JAR đã tạo để chứng minh cấu hình bên ngoài thay đổi mà không cần build lại.

### Bước A — đổi working directory

Trong project, tạo thư mục `lab-run` trống.

macOS/Linux:

```bash
mkdir -p lab-run
cd lab-run
java -jar ../build/libs/config-locations-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force lab-run | Out-Null
Push-Location lab-run
java -jar ..\build\libs\config-locations-0.0.1-SNAPSHOT.jar
```

Nếu chưa có file cấu hình bên ngoài trong `lab-run`, dự đoán:

```text
workingDirectory = .../config-locations/lab-run
effectiveValue = packaged-config
```

Kết quả chứng minh file trong classpath vẫn được nạp dù không chạy Java từ thư mục nguồn.

### Bước B — thêm file ở `file:./`

Trong `lab-run`, tạo `application.properties`:

```properties
lab.origin=external-root
```

Chạy lại `java -jar ...` từ `lab-run`. Kỳ vọng:

```text
effectiveValue = external-root
```

Location `file:./` bây giờ trỏ vào thư mục `lab-run`. File ngoài được ưu tiên hơn giá trị trong classpath theo quy tắc mặc định.

### Bước C — thêm file ở `file:./config/`

Tạo `lab-run/config/application.yaml`:

```yaml
lab:
  origin: external-config
```

Cấu trúc:

```text
lab-run/
├── application.properties
└── config/
    └── application.yaml
```

Chạy lại cùng JAR. Kỳ vọng:

```text
effectiveValue = external-config
```

Điểm cần phân biệt: kết quả do **thứ tự hai location khác nhau**. Không áp dụng nhầm quy tắc `.properties` thắng YAML cùng một location: ở đây một file nằm tại `./`, file còn lại tại `./config/`.

### Bước D — thêm file trong thư mục con của `config`

Tạo `lab-run/config/team-a/application.properties`:

```properties
lab.origin=external-team-a
```

Cây thư mục:

```text
lab-run/
├── application.properties
└── config/
    ├── application.yaml
    └── team-a/
        └── application.properties
```

Chạy lại:

```text
effectiveValue = external-team-a
```

Nguồn này được nạp vì `team-a/` là một thư mục con trực tiếp được wildcard `file:./config/*/` nhận diện.

### Bước E — kiểm chứng giới hạn một cấp của wildcard

Thêm file:

```text
lab-run/config/team-b/nested/application.properties
```

Nội dung:

```properties
lab.origin=deeply-nested
```

Chạy lại trong điều kiện không có import hoặc additional location:

```text
effectiveValue = external-team-a
```

File ở `team-b/nested/` không được tự động tìm bởi `file:./config/*/`, vì wildcard chỉ đưa Spring Boot tới một cấp thư mục con trực tiếp của `config`.

### Bước F — `.properties` và YAML trong cùng location

Tạm đưa file `lab-run/config/team-a/application.properties` ra ngoài `lab-run/config/` để không còn nguồn wildcard ghi đè. Giữ `lab-run/config/application.yaml` từ bước C và tạo thêm:

`lab-run/config/application.properties`:

```properties
lab.origin=properties-at-same-location
```

Cả hai file ở `file:./config/`:

```text
lab-run/config/
├── application.properties
└── application.yaml
```

Chạy lại:

```text
effectiveValue = properties-at-same-location
```

Đây mới là tình huống **`.properties` ưu tiên hơn YAML ở cùng một location**.

### Bảng ghi chép kết quả

| Bước | Đầu vào khác biệt | Kỳ vọng `lab.origin` | Giá trị quan sát được |
| --- | --- | --- | --- |
| A | Chỉ file trong classpath | `packaged-config` | Tự điền |
| B | Thêm `./application.properties` | `external-root` | Tự điền |
| C | Thêm `./config/application.yaml` | `external-config` | Tự điền |
| D | Thêm `./config/team-a/application.properties` | `external-team-a` | Tự điền |
| E | Thêm file trong `team-b/nested` | `external-team-a` | Tự điền |
| F | Bỏ nguồn `team-a`; thêm `.properties` cạnh YAML trong `./config/` | `properties-at-same-location` | Tự điền |

Mỗi khi giá trị khác cột kỳ vọng, trước tiên hãy xem `workingDirectory`, `activeProfiles`, tên các file thật đang tồn tại, rồi các dòng `Matching property sources`. Không nên sửa nhiều file cùng lúc khi đang tìm nguyên nhân.

Trên Windows PowerShell, sau khi thực hành có thể dùng `Pop-Location` để trở lại thư mục trước khi vào `lab-run`.

## 7. Thử một file theo profile

Khi đã dọn những file trùng khóa trong các thư mục wildcard và chỉ giữ file nền `lab-run/config/application.yaml`, tạo thêm:

`lab-run/config/application-dev.yaml`:

```yaml
lab:
  origin: external-config-dev
```

Chạy:

```bash
java -jar ../build/libs/config-locations-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
```

Windows thay phần đường dẫn JAR bằng cú pháp dùng `\`.

Khi không có nguồn ưu tiên cao hơn, đầu ra dự đoán:

```text
activeProfiles = [dev]
effectiveValue = external-config-dev
```

Spring Boot tìm file theo profile ở những location phù hợp, và giá trị profile-specific có thể ghi đè giá trị nền. Nếu không truyền `--spring.profiles.active=dev`, file `application-dev.yaml` không tự được kích hoạt chỉ vì nó tồn tại.

Một điều cần tránh là đặt `spring.profiles.active` ngay trong một tài liệu YAML dành riêng cho profile đang muốn kích hoạt. Thuộc tính chọn profile phải được cung cấp ở nơi hợp lệ trước khi chọn tài liệu cấu hình theo profile.

## 8. Điều chỉnh cách tìm file

Nhóm `spring.config.*` dưới đây được dùng khi cấu hình theo quy ước mặc định chưa đáp ứng yêu cầu.

### 8.1. `spring.config.name`: thay tên cơ sở

Mặc định Spring Boot tìm file có tên cơ sở `application`. Nếu muốn tìm `service.properties` hoặc `service.yaml`, truyền:

```bash
java -jar app.jar --spring.config.name=service
```

Lúc này tập tên file được tìm sẽ thay đổi. Đừng giả định những thuộc tính chỉ có trong `application.yaml` cũ vẫn được nạp. Nếu app cần `spring.main.web-application-type=none`, hãy đặt nó vào nguồn sẽ được nạp hoặc truyền từ nguồn phù hợp.

Đổi `spring.config.name` **khác** với thêm một location; nó thay đổi tên cơ sở để Spring Boot tìm ở các location.

### 8.2. `spring.config.location`: thay tập location mặc định

Ví dụ:

```bash
java -jar app.jar --spring.config.location=optional:file:./ops/
```

Đây là cách chỉ định một tập location thay cho danh sách location mặc định. Nếu không đưa classpath vào danh sách mới, các file mặc định trong classpath có thể không còn được nạp. Dùng khi thật sự muốn kiểm soát rõ vùng đọc cấu hình.

Ký hiệu `optional:` cho phép location vắng mặt mà không bắt ứng dụng thất bại vì chính location đó. Với location kiểu **thư mục**, kết thúc bằng `/` để Spring Boot có thể ghép tên file cần tìm.

### 8.3. `spring.config.additional-location`: thêm location

Nếu muốn vẫn dùng các file mặc định và đọc thêm `./ops/`, truyền:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./ops/
```

Giả sử `./ops/application.yaml` có:

```yaml
lab:
  origin: from-ops
```

và không có nguồn khác ưu tiên cao hơn, giá trị hiệu lực có thể là `from-ops`. Cấu hình ở các location mặc định vẫn đóng góp các thuộc tính còn lại.

Thuộc tính `spring.config.additional-location` thích hợp khi vận hành muốn bổ sung thư mục cấu hình ngoài JAR mà vẫn giữ cấu hình nền đóng gói.

### 8.4. Vì sao các thuộc tính này phải được thiết lập sớm?

Spring Boot cần biết **phải tìm file ở đâu** trước khi đọc chính các file đó. Do vậy `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được đọc ở giai đoạn sớm, thường qua đối số dòng lệnh, biến môi trường hoặc Java system property. Không đặt chúng trong một file chưa được tìm thấy rồi kỳ vọng file ấy hướng dẫn Spring Boot đi tìm chính nó.

Nếu truyền nhiều location, dấu phân cách `,` và `;` có ý nghĩa với **location groups**, đặc biệt khi cùng lúc có profile-specific files. Không nên suy rộng quy tắc đơn giản của bài lab cho mọi cách kết hợp location tùy biến.

### 8.5. Khi nào dùng `spring.config.import`?

`spring.config.import` có thể nhập thêm config data từ một file hoặc nguồn khác đã được khai báo trong cấu hình được nạp. Đây là cơ chế riêng, phù hợp với các tình huống import có chủ đích. Nó không phải một location mặc định thứ sáu. Khi debugging, nếu một giá trị xuất hiện từ đường dẫn ngoài năm vị trí, hãy kiểm tra xem có import hoặc nguồn bổ sung nào được khai báo hay không.

## 9. Phân biệt đường dẫn lúc code, lúc build, lúc chạy

Một ví dụ tổng hợp:

```text
LÚC CODE
project/
└── src/main/resources/application.yaml
                         |
                         | Gradle build
                         v
TRONG EXECUTABLE JAR
app.jar!/BOOT-INF/classes/application.yaml
                         |
                         | java -jar /opt/apps/app.jar
                         | working directory = /srv/run
                         v
CẤU HÌNH BÊN NGOÀI
/srv/run/application.properties
/srv/run/config/application.yaml
/srv/run/config/team-a/application.yaml
```

Ba cấp đường dẫn phải được nhìn riêng:

1. **Source path:** `src/main/resources` tồn tại khi phát triển.
2. **Classpath runtime:** tài nguyên đóng gói và được truy cập qua `classpath:/`.
3. **Filesystem runtime:** file ngoài JAR được tìm qua `file:./` và các location tương đối với thư mục làm việc.

Nếu bạn chuyển JAR sang thư mục khác nhưng giữ nguyên working directory, các location `file:./...` vẫn tính từ working directory. Nếu bạn đổi working directory mà giữ nguyên JAR, file ngoài mặc định có thể thay đổi. Đó là lý do hai máy chạy cùng artifact nhưng nhận giá trị khác nhau mà không nhất thiết có lỗi đóng gói.

## 10. Các lỗi thường gặp và cách tìm nguyên nhân

**“Đã đặt `application.properties` ngay cạnh JAR nhưng không thấy giá trị.”** Kiểm tra `user.dir` của tiến trình. File cạnh JAR chỉ được tìm theo location mặc định nếu cũng phù hợp với working directory, hoặc đã có location bên ngoài được cấu hình để trỏ tới đó.

**“Có file trong `src/main/resources`, nhưng production không có thư mục này.”** Điều đó bình thường: tài nguyên được đóng gói vào classpath. Kiểm tra artifact build thay vì tìm đường dẫn `src/main/resources` trên máy chạy JAR.

**“Có `settings.yaml` hoặc `config-prod.yaml`, nhưng ứng dụng không tự đọc.”** Tên mặc định là `application`. Đổi tên file theo quy ước, đổi `spring.config.name` hoặc cấu hình import/location phù hợp. Một file YAML bất kỳ không tự được nạp chỉ vì nằm trong `./config`.

**“Có `application-dev.yaml`, nhưng `activeProfiles` vẫn trống.”** Bật profile `dev` từ một nguồn hợp lệ; chỉ tạo file chưa đủ. Kiểm tra cả khả năng có nguồn khác ghi đè giá trị sau khi profile được bật.

**“File ở `config/team-a/nested` không có tác dụng.”** Wildcard location mặc định chỉ mở rộng một cấp từ `config`. Muốn đọc sâu hơn, cần cơ chế location/import riêng.

**“Hai file YAML và properties đều ở `./config`, nhưng giá trị khác mong đợi.”** Kiểm tra có `.properties` và `.yaml` cùng location hay không, và có file ở `./config/<thư-mục-con>/` ưu tiên cao hơn hay không.

**“Tôi sửa YAML và gửi lại request, nhưng ứng dụng không đổi.”** Externalized configuration mặc định được nạp khi khởi động. Hãy restart ứng dụng để kiểm chứng trong bài lab, trừ khi hệ thống đang dùng cơ chế refresh được thiết kế riêng.

**“Có nhiều thư mục con `config`, không rõ khóa nào thắng.”** Liệt kê các directory được wildcard mở rộng, tên file profile-specific và tất cả nguồn có khóa đó; giảm trùng lặp hoặc dùng một location rõ ràng khi vận hành.

**“`spring.config.location` làm mất một số giá trị nền.”** Đây là thuộc tính **thay** location mặc định. Nếu mong giữ mặc định, dùng `spring.config.additional-location` hoặc liệt kê rõ mọi location cần thiết.

**“Giá trị từ file vẫn thua dù file ở location cuối.”** Bài học chỉ mô tả ưu tiên giữa các vị trí file mặc định. Hãy kiểm tra biến môi trường, system property, CLI, test, import và các nguồn bổ sung có độ ưu tiên cao hơn hoặc hành vi khác.

## 11. Câu hỏi luyện tập

Trước khi đọc gợi ý, hãy tự trả lời:

1. Năm location mặc định của Spring Boot 3.3 là gì?
2. Khi chạy `java -jar /apps/app.jar` từ `/home/service`, `file:./config/` trỏ tới đâu?
3. `src/main/resources/config/application.yaml` được nạp từ filesystem ngoài JAR hay từ classpath?
4. File ở `./config/team-a/application.yaml` có được tìm không? Còn `./config/team-a/nested/application.yaml` thì sao?
5. Nếu chỉ file trong classpath đặt `lab.retry-count=3`, còn file ngoài chỉ đặt `lab.origin`, khóa `retry-count` có bị mất không?
6. Vì sao hai file `application.properties` và `application.yaml` cùng location có thể gây nhầm lẫn?
7. File `application-dev.yaml` có tự kích hoạt profile `dev` không?
8. Khi muốn thêm `./ops/` nhưng vẫn giữ file nền trong JAR, dùng thuộc tính nào?
9. Khi muốn thay toàn bộ tập location mặc định, dùng thuộc tính nào?
10. Sau khi sửa file ngoài, thao tác nào giúp lần chạy tiếp theo thực sự nạp lại file?

**Gợi ý:**

1. `classpath:/`, `classpath:/config/`, `file:./`, `file:./config/`, `file:./config/*/`.
2. `/home/service/config/`.
3. Từ classpath, vì file nguồn được đóng gói thành tài nguyên runtime.
4. File trong `team-a` có, file sâu trong `nested` không được tìm trực tiếp qua wildcard mặc định.
5. Không, các khóa không trùng vẫn có thể đến từ nguồn khác đã nạp.
6. `.properties` được ưu tiên hơn YAML khi cùng location.
7. Không; cần bật profile bằng nguồn hợp lệ.
8. `spring.config.additional-location`.
9. `spring.config.location`.
10. Khởi động lại tiến trình với working directory và profile được kiểm soát.

## 12. Ứng dụng thực tế và nguyên tắc an toàn

Trong môi trường thật, dùng cấu hình nền không nhạy cảm bên trong artifact, còn cấu hình thay đổi theo môi trường nên đến từ nguồn vận hành được quản lý. Cần kiểm soát thư mục làm việc, quyền đọc file, profile và các thuộc tính `spring.config.*` của tiến trình triển khai. Không đưa mật khẩu, token hay toàn bộ environment variables vào endpoint/log chỉ để xem ưu tiên cấu hình.

Bài lab dùng `lab.origin` là giá trị giả lập an toàn. Mục tiêu không phải ghi nhớ mọi thuộc tính Spring Boot, mà là hình thành quy trình tìm nguồn cho một khóa cụ thể: **xác định working directory → kiểm kê năm location mặc định → xác định tên file và profile → đối chiếu giá trị hiệu lực với các PropertySource → tìm nguồn ghi đè → thử lại bằng tiến trình mới**. Quy trình này giúp giải thích vì sao cùng một JAR có thể hoạt động khác nhau giữa máy phát triển, CI và production.