# Phân biệt Maven profile với Spring profile

Trong một dự án Spring Boot dùng Maven, từ **profile** xuất hiện ở hai tầng rất khác nhau. Ví dụ, `mvn -Pci clean verify` và `java -jar app.jar --spring.profiles.active=prod` đều đề cập “profile” nhưng có **đối tượng, thời điểm và tác dụng riêng**. Nhầm hai cơ chế này dễ dẫn đến tình huống “build với `-Pprod` rồi tưởng ứng dụng đã chạy ở cấu hình production”, hoặc vô tình tạo các JAR khác nhau cho từng môi trường dù thực tế chỉ cần thay cấu hình khi khởi động.

**Quy tắc cốt lõi:**

- **Maven profile** chọn **cấu hình của quá trình build**: properties, plugins, dependencies, repositories và các tác vụ Maven sẽ dùng. Nó được Maven xử lý khi xây dựng effective POM, trước/trong các goal biên dịch, kiểm tra và đóng gói.
- **Spring profile** chọn **cấu hình và bean của ứng dụng tại runtime**: tệp `application-{profile}.yml`, tài liệu cấu hình có điều kiện, bean được đánh dấu `@Profile` và những tham số môi trường mà Spring Boot đọc khi khởi động.
- **Hai profile cùng tên không tự liên kết.** `-Pdev` không có nghĩa `spring.profiles.active=dev`; `--spring.profiles.active=dev` cũng không kích hoạt Maven profile `dev`.

Bài này dùng Java 17, Spring Boot 3.3.13 và Maven 3.9.x làm mốc minh họa. Nếu dự án dùng phiên bản khác, kiểm tra tài liệu đúng release và giữ nguyên nguyên tắc phân biệt hai tầng.

## 1. So sánh trên một bảng

| Tiêu chí | Maven profile | Spring profile |
| --- | --- | --- |
| Ai xử lý? | **Apache Maven** khi tạo effective project model và thực thi build | **Spring Framework/Spring Boot** khi dựng application context |
| Kích hoạt trực tiếp | `mvn -Pci clean verify` | `--spring.profiles.active=dev`, `SPRING_PROFILES_ACTIVE=dev` hoặc API tương đương |
| Khai báo điển hình | `<profiles><profile><id>ci</id>...` trong `pom.xml`; cấu hình Maven settings | `application-dev.yml`, `@Profile("dev")`, các Spring config properties |
| Thời điểm chính | Build: resolve dependencies, compile, test, package, publish | App startup/runtime: load configuration, tạo bean và phục vụ request |
| Thứ được chọn | Plugin executions, properties, dependency/repository/build configuration | Bean definitions, profile-specific properties, tính năng ứng dụng tùy cấu hình |
| Thứ không tự làm | Không mặc nhiên đổi active Spring profile | Không tự sửa effective POM hoặc chọn Maven plugin |
| Kiểm chứng | `mvn help:active-profiles`, `mvn help:effective-pom`, build log | Spring startup log, `Environment#getActiveProfiles()`, test hoặc endpoint an toàn |
| Có thể dùng đồng thời? | Có, cùng một lần chạy development/CI | Có, vẫn phải chọn từng cơ chế hoặc cấu hình cầu nối rõ ràng |

Đọc câu lệnh theo đúng tầng:

```text
mvn -Pci clean verify
    └──── Maven profile "ci" → ảnh hưởng việc build/test

java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
                                          └──── Spring profile "prod" → ảnh hưởng lúc chạy

mvn -Pci spring-boot:run -Dspring-boot.run.profiles=dev
       │                       └──── Spring profile "dev" truyền qua Boot Maven Plugin
       └──── Maven profile "ci" cho tiến trình build/plugin
```

Lệnh thứ ba **chủ động dùng hai nút điều khiển**. Sự tương ứng tên profile chỉ là một quy ước nếu nhóm tự xây dựng, không phải cơ chế Maven hoặc Spring tự suy luận.

## 2. Maven profile hoạt động ở tầng build

Maven đọc `pom.xml`, parent POM, settings và trạng thái activation để dựng **effective POM**. Khi một Maven profile đang hoạt động, Maven hợp nhất những phần được cho phép của profile vào mô hình build: properties, dependencies, repositories, build plugins, plugin executions... Sau đó các phase/goal hoạt động trên mô hình này.

Maven profiles có thể được khai báo trong:

- **Project POM:** `<profiles>` của `pom.xml`; có thể điều chỉnh dependency, plugin và build.
- **User settings:** `~/.m2/settings.xml`; tập trung vào properties, repositories và pluginRepositories phù hợp với cơ chế settings.
- **Global Maven settings:** thư mục `conf/settings.xml` của bản Maven đang chạy, tác động ở cấp cài đặt.

**Các cơ chế kích hoạt thông dụng:**

```bash
mvn -Pci clean verify
mvn -Pci,quality clean verify
mvn -Dbuild.env=ci clean verify
mvn help:active-profiles
mvn help:effective-pom -Pci
```

Lệnh thứ ba chỉ kích hoạt profile nếu `pom.xml` có `<activation><property>` tương ứng; bản thân `-Dbuild.env=ci` chỉ đặt một Maven user property. Các profile còn có thể được kích hoạt theo JDK, OS, file tồn tại/không tồn tại, `activeByDefault` hoặc cấu hình settings. Profile mặc định theo `activeByDefault` trong một POM có thể bị tắt khi profile khác của cùng POM được kích hoạt; không dựa vào việc “chắc chắn cả hai đều chạy”.

**`-P` là tùy chọn của Maven.** Ví dụ `mvn -Pprod package` chỉ yêu cầu Maven tìm profile có id `prod` và áp dụng tác động build của nó. Nó không đi vào Spring Boot `Environment` chỉ vì id trùng tên tệp `application-prod.yml`.

### Ví dụ Maven profile chỉ thay đổi build

Fragment sau nằm trong `pom.xml`, dưới phần tử `<project>`:

```xml
<properties>
    <build.mode>standard</build.mode>
</properties>

<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.mode>ci</build.mode>
        </properties>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Với `-Pci`, property `build.mode` chuyển từ `standard` sang `ci` và Surefire được cấu hình thất bại nếu không phát hiện bài test theo quy tắc của nó. Đây là **quy định chất lượng build**. Property `build.mode` tự nó chưa được application code sử dụng hoặc xuất vào JAR; chỉ khi build plugin/resource filtering được cấu hình đọc nó thì nó mới gây tác động bổ sung.

Kiểm tra giá trị Maven property:

```bash
mvn help:evaluate -q -DforceStdout -Dexpression=build.mode
mvn -Pci help:evaluate -q -DforceStdout -Dexpression=build.mode
```

Giá trị liên quan được Maven Help Plugin đánh giá lần lượt là `standard` và `ci`. Tên property do dự án tự chọn; nó **không phải** một thuộc tính cấu hình đặc biệt của Spring Boot.

## 3. Spring profile hoạt động ở tầng ứng dụng

Khi Spring Boot bắt đầu tạo `ApplicationContext`, nó dựng một `Environment` từ nhiều nguồn: command-line arguments, environment variables, system properties, các tệp `application.yml`/`application.properties` và những nguồn cấu hình bên ngoài phù hợp. Active profiles giúp Spring chọn thêm các nguồn cấu hình và những bean có điều kiện tương ứng.

Các cách đặt Spring profile thường gặp:

```bash
# Chạy JAR đã build: command-line application argument
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev

# Chạy JAR với JVM system property; -D phải đứng trước -jar
java -Dspring.profiles.active=prod -jar target/profile-demo-1.0.0.jar

# Linux/macOS: environment variable cho riêng tiến trình
SPRING_PROFILES_ACTIVE=dev java -jar target/profile-demo-1.0.0.jar

# Chạy qua Spring Boot Maven Plugin
mvn spring-boot:run -Dspring-boot.run.profiles=dev
```

PowerShell (Windows) có cú pháp môi trường riêng:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar target/profile-demo-1.0.0.jar
```

Nếu bạn chạy `java -jar` trực tiếp, `-Dspring-boot.run.profiles=dev` **không phải** đối số runtime của Spring Boot Maven Plugin; dùng `--spring.profiles.active=dev` hoặc property/environment phù hợp. Ngược lại, khi chạy `mvn spring-boot:run`, `-Dspring-boot.run.profiles` là một user property riêng của Spring Boot Maven Plugin để kích hoạt profile cho ứng dụng được plugin khởi động.

Nếu không có active profile nào, Spring dùng **default profile**, thường tên `default`; điều đó không có nghĩa Maven tự kích hoạt một profile tên `default`. Bạn có thể dùng `spring.profiles.default` trong tài liệu cấu hình không phụ thuộc profile để đổi lựa chọn mặc định.

## 4. Một ví dụ chạy được: cùng ứng dụng, hai tầng profile độc lập

Dự án nhỏ dưới đây cho phép chạy **cùng một JAR** với hai cấu hình `dev` và `prod`; Maven profile `ci` chỉ làm thay đổi chính sách kiểm tra build. Điều này trực tiếp chứng minh hai cơ chế hoạt động độc lập.

### Cấu trúc dự án

```text
profile-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/profile/
    │   │   ├── ProfileDemoApplication.java
    │   │   ├── ProfileController.java
    │   │   └── DevOnlyNotice.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-dev.yml
    │       └── application-prod.yml
    └── test/
        └── java/dev/example/profile/
            └── ProfileDemoApplicationTests.java
```

### POM hoàn chỉnh

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>profile-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <build.mode>standard</build.mode>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <build.mode>ci</build.mode>
            </properties>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-surefire-plugin</artifactId>
                        <configuration>
                            <failIfNoTests>true</failIfNoTests>
                        </configuration>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
```

POM kế thừa quản lý dependency/plugin phù hợp từ Spring Boot starter parent. Khi bật `-Pci`, Maven thêm cấu hình Surefire vào effective POM; **không** đặt `spring.profiles.active`.

### Mã Java

`src/main/java/dev/example/profile/ProfileDemoApplication.java`:

```java
package dev.example.profile;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`src/main/java/dev/example/profile/ProfileController.java`:

```java
package dev.example.profile;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    private final String label;
    private final Environment environment;

    public ProfileController(@Value("${demo.label}") String label,
                             Environment environment) {
        this.label = label;
        this.environment = environment;
    }

    @GetMapping("/mode")
    public String mode() {
        String[] active = environment.getActiveProfiles();
        String names = active.length == 0 ? "(none)" : String.join(",", active);
        return "label=" + label + "; active=" + names;
    }
}
```

Endpoint minh họa này cố tình công khai **chỉ tên profile** và một nhãn vô hại. Không nên biến nó thành endpoint đọc toàn bộ `Environment` vì hệ thống thực có thể chứa mật khẩu, token và cấu hình nhạy cảm.

`src/main/java/dev/example/profile/DevOnlyNotice.java`:

```java
package dev.example.profile;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevOnlyNotice implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Dev-only startup hook");
    }
}
```

`@Profile("dev")` khiến bean `DevOnlyNotice` chỉ được tạo khi Spring profile `dev` đang hoạt động. Đây là quyết định **runtime bean registration**, không phụ thuộc Maven `-Pci`.

### Cấu hình chung và cấu hình theo Spring profile

`src/main/resources/application.yml`:

```yaml
demo:
  label: base
```

`src/main/resources/application-dev.yml`:

```yaml
demo:
  label: dev
```

`src/main/resources/application-prod.yml`:

```yaml
demo:
  label: prod
```

Khi chạy với `dev`, Spring Boot đọc cấu hình chung và biến thể `application-dev.yml`; giá trị `demo.label` trong biến thể `dev` có hiệu lực tại runtime. Khi chạy `prod`, nó dùng giá trị `prod`. Nếu không có active profile, cấu hình chung cho kết quả `base` (bởi ví dụ không có `application-default.yml`).

**Cả ba tệp YAML được đóng gói trong JAR**. Đóng gói nhiều tệp `application-{profile}.yml` không có nghĩa tất cả profile cùng hoạt động; việc lựa chọn diễn ra khi ứng dụng được khởi động. Trong thực tế, chỉ chứa các tham số không nhạy cảm ở đây; credentials và secret cần cấp từ môi trường triển khai hoặc secret manager.

### Test chọn Spring profile độc lập với Maven profile

`src/test/java/dev/example/profile/ProfileDemoApplicationTests.java`:

```java
package dev.example.profile;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("dev")
class ProfileDemoApplicationTests {
    @Autowired
    private MockMvc mvc;

    @Test
    void usesDevProfileConfiguration() throws Exception {
        mvc.perform(get("/mode"))
                .andExpect(status().isOk())
                .andExpect(content().string("label=dev; active=dev"));
    }
}
```

Ở đây `@ActiveProfiles("dev")` là annotation của **Spring TestContext Framework**: nó chỉ định Spring profile của test application context. Dù chạy `mvn test` hay `mvn -Pci test`, test này vẫn chủ động dùng `dev`. Profile Maven `ci` chỉ điều chỉnh Surefire và build property ở POM.

### Chạy và đối chiếu kết quả

Tại thư mục dự án có POM, cần cài JDK 17 và Maven phù hợp (hoặc thay `mvn` bằng Maven Wrapper `./mvnw` nếu có):

```bash
mvn -version
mvn clean verify
mvn -Pci clean verify
mvn -Pci help:active-profiles
mvn -Pci help:evaluate -q -DforceStdout -Dexpression=build.mode
```

Với POM mẫu, `-Pci` bật profile Maven `ci`; `build.mode` được đánh giá là `ci` và cấu hình kiểm tra “không có test thì fail” được áp dụng. Bài test `ProfileDemoApplicationTests` chạy với Spring profile `dev` nhờ `@ActiveProfiles`.

Sau khi đã tạo `target/profile-demo-1.0.0.jar`, thực hiện từng lệnh khởi động **riêng biệt**, dừng ứng dụng trước khi thử lệnh tiếp theo để tránh tranh cổng 8080.

**Trường hợp 1 — không kích hoạt Spring profile:**

```bash
java -jar target/profile-demo-1.0.0.jar
```

Từ terminal khác:

```bash
curl -s http://localhost:8080/mode
```

Body chính xác từ ví dụ:

```text
label=base; active=(none)
```

**Trường hợp 2 — Spring profile dev:**

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev
```

Body của `/mode`:

```text
label=dev; active=dev
```

Ứng dụng còn in dòng `Dev-only startup hook` trong stdout lúc khởi động (ngoài các log Spring Boot thay đổi theo môi trường).

**Trường hợp 3 — cùng JAR, Spring profile prod:**

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
```

Body của `/mode`:

```text
label=prod; active=prod
```

Lúc này bean `DevOnlyNotice` không tồn tại trong application context vì nó có `@Profile("dev")`.

**Trường hợp 4 — Maven profile ci và Spring profile dev cùng lúc, chạy từ source:**

```bash
mvn -Pci spring-boot:run -Dspring-boot.run.profiles=dev
```

Maven profile `ci` ảnh hưởng quá trình Maven xử lý POM; Spring Boot Maven Plugin chủ động truyền profile `dev` cho ứng dụng khi khởi động. Nếu bỏ `-Dspring-boot.run.profiles=dev` và không có nguồn cấu hình Spring khác, chỉ `-Pci` **không khiến** `application-dev.yml` được chọn.

## 5. Tại sao “Maven dev/prod” không đồng nghĩa “Spring dev/prod”?

Giả sử project có Maven profile id `prod` và tệp `application-prod.yml`:

```bash
mvn -Pprod package
```

Lệnh này **chỉ** làm Maven áp dụng profile `prod` khi có profile đó trong POM/settings. Maven có thể đổi plugin, dependency, resource filtering hoặc bản đóng gói dựa trên nội dung profile. Nhưng lệnh trên **không khởi động ứng dụng**, và cũng không tự ghi “Spring active profile=prod” vào JAR.

Sau đó nếu chạy:

```bash
java -jar target/profile-demo-1.0.0.jar
```

Spring vẫn dùng cấu hình mặc định nếu không có `spring.profiles.active`, biến môi trường hay một nguồn cấu hình runtime khác. Muốn profile prod, cần kích hoạt khi chạy:

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=prod
```

**Ngược lại**, nếu chạy `java -jar ... --spring.profiles.active=prod` thì Maven không chạy tại bước này, nên Maven profile `prod` không thể “bỗng nhiên” được kích hoạt. Mọi sự khác biệt build-time đã nằm trong artifact mà bạn chọn.

Một mô hình thường dùng trong CI/CD:

```text
Source + POM
    |
    | mvn -Pci clean verify
    v
Artifact đã qua kiểm thử (JAR duy nhất)
    |
    +--> Dev      : java -jar app.jar --spring.profiles.active=dev
    |
    +--> Staging  : java -jar app.jar --spring.profiles.active=staging
    |
    +--> Prod     : java -jar app.jar --spring.profiles.active=prod
```

Trong sơ đồ, các môi trường có cấu hình Spring khác nhau nhưng **tiêu thụ cùng một JAR đã được phê duyệt**, với điều kiện quy trình build không chủ đích thay code/resources theo môi trường. Điều này giúp tránh lỗi “QA kiểm thử một build, production chạy build khác”.

## 6. Khi nào nên chọn cơ chế nào?

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Bật thêm static analysis/coverage gate trong CI | Maven profile `ci` | Thay đổi plugin và phase/goal ở build |
| Chọn Maven repository mirror hoặc thông số plugin hợp lệ | Maven settings/POM profile | Thuộc quá trình resolve và build |
| Bật endpoint mock trong local nhưng không có ở prod | Spring profile `dev` + `@Profile` hoặc cấu hình điều kiện | Quyết định bean/runtime |
| Chọn logging level, URL dịch vụ, port | Spring runtime config/profile | Có thể đổi mà không build lại |
| Chọn database dev/test/prod | Spring profile + external configuration/secrets | Môi trường chạy quyết định kết nối |
| Test Spring beans dưới cấu hình `test` | `@ActiveProfiles("test")` và `application-test.yml` | Kiểm tra application context ở runtime của test |
| Thêm kiểm tra “build không có test phải fail” | Maven Surefire config trong profile `ci` | Chính sách chất lượng build |
| Tạo artifact có format hoặc dependency khác thực sự | Maven build profile nếu có yêu cầu cụ thể | Đây là thay đổi artifact, phải test từng biến thể |
| Triển khai cùng artifact sang nhiều môi trường | Spring profiles/runtime env | Giữ tính bất biến của artifact |

**Chọn theo ranh giới trách nhiệm**, không theo tên “dev/test/prod”. Việc có hai profile cùng tên có thể thuận tiện để tổ chức nhưng cần tài liệu chỉ ra chúng điều khiển những gì riêng biệt.

## 7. Cơ chế kích hoạt Spring profile và thứ tự cấu hình

Spring Boot hỗ trợ nhiều cách đặt active profiles:

- `spring.profiles.active=dev` trong tài liệu cấu hình chung.
- `SPRING_PROFILES_ACTIVE=dev` từ environment variable.
- `java -Dspring.profiles.active=dev -jar ...` bằng JVM system property.
- `java -jar ... --spring.profiles.active=dev` bằng command-line application argument.
- `SpringApplication.setAdditionalProfiles(...)` hoặc `Environment` khi cấu hình programmatically.
- `@ActiveProfiles` cho Spring integration tests.

**Ưu tiên cấu hình** tuân theo quy tắc property sources của Spring Boot. Với cấu hình mặc định, command-line application arguments có thể override giá trị `spring.profiles.active` trong `application.yml`. Đừng đoán giá trị cuối cùng chỉ vì có một file `application-dev.yml`: file đó chỉ được chọn khi profile đã hoạt động và không bị cơ chế cấu hình khác thay đổi.

### Profile-specific files

Khi kích hoạt `dev`, Spring Boot xét `application.yml` và `application-dev.yml`. Trong cùng nhóm vị trí cấu hình, giá trị trong file theo profile có thể override giá trị chung. Nếu kích hoạt nhiều profile như `dev,local`, các file theo profile được xét theo thứ tự phù hợp, thường “profile sau thắng” khi cùng khóa và cùng nhóm vị trí; thứ tự location và cấu hình bên ngoài có thể ảnh hưởng precedence.

Ví dụ:

```bash
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev,local
```

Điều này kích hoạt hai Spring profiles (không phải hai Maven profiles). Nếu không tồn tại `application-local.yml`, việc thiếu file đó **không mặc nhiên gây lỗi**; Spring vẫn xử lý `dev` và các nguồn khác.

### Dùng `spring.config.activate.on-profile` trong multi-document YAML

Ngoài file riêng, có thể dùng điều kiện ngay trong `application.yml`:

```yaml
demo:
  label: base
---
spring:
  config:
    activate:
      on-profile: dev
demo:
  label: dev
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  label: prod
```

Đây là **cách thay thế** cho ba file cấu hình trong ví dụ, không nên đặt cả hai mẫu cùng lúc nếu chưa tính đến precedence. Các khối YAML chỉ được áp dụng khi điều kiện Spring profile phù hợp; nó không liên quan Maven `<profiles>`.

**Không khai báo `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` hoặc `spring.profiles.group` bên trong tài liệu chỉ kích hoạt theo profile**, chẳng hạn `application-prod.yml` hoặc block có `spring.config.activate.on-profile`. Spring Boot giới hạn các thuộc tính chọn profile ở tài liệu không phụ thuộc profile; đặt sai vị trí có thể gây lỗi cấu hình khi khởi động.

Nếu muốn thêm profile nền, `spring.profiles.include` hoặc `spring.profiles.group.*` là công cụ của **Spring Boot runtime**, không phải cách nhập Maven profile. Chỉ dùng khi cần tổ hợp profile, tránh cấu hình vòng vo khiến khó biết những bean thực sự hoạt động.

### Bean theo profile

Các annotation thường gặp:

```java
@Profile("dev")
@Component
class DevDiagnostics {
    // Bean chỉ được đăng ký khi Spring profile dev hoạt động.
}
```

Đây là đoạn **minh họa**, không phải class đầy đủ có file/import. Trong ứng dụng thực, khai báo `@Profile` trên `@Component`, `@Configuration` hoặc `@Bean` theo nhu cầu; có thể dùng biểu thức như `@Profile("!prod")` nhưng cần cân nhắc nếu có nhiều active profiles. Không dựa vào Maven `-Pdev` để điều khiển bean.

## 8. Khi nào hai profile có liên hệ và cách tạo cầu nối có chủ đích

Có những hệ thống cố ý map một Maven property sang Spring runtime, thường qua cấu hình Spring Boot Maven Plugin, system properties, application arguments hoặc resource filtering. Ví dụ fragment POM:

```xml
<properties>
    <app.runtime.profile>dev</app.runtime.profile>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <profiles>${app.runtime.profile}</profiles>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **fragment bổ sung vào POM**, không phải POM độc lập. Khi dùng lệnh:

```bash
mvn spring-boot:run -Dapp.runtime.profile=prod
```

Maven đặt user property `app.runtime.profile=prod`, Spring Boot Maven Plugin nhận property thông qua `<profiles>` và truyền `prod` để kích hoạt Spring profile khi chạy ứng dụng **qua plugin**. Với `java -jar` của JAR đã đóng gói, cấu hình plugin `spring-boot:run` **không tiếp tục điều khiển runtime**; vẫn cần environment/CLI/system properties lúc khởi động JAR.

Nếu muốn gắn **Maven profile** với **Spring profile** một cách tường minh, có thể khai báo property `app.runtime.profile` trong một Maven profile rồi cấu hình plugin đọc property đó. Nhưng mô hình này làm hai tầng phụ thuộc nhau và dễ gây nhầm. Chỉ làm khi có yêu cầu rõ (ví dụ tiện chạy development), ghi rõ đường truyền và kiểm tra kết quả thực tế. Không dùng cầu nối như vậy để nhúng secrets hoặc “build riêng production” khi chỉ cần runtime config.

**Resource filtering là một cầu nối khác nhưng có hệ quả khác:** Maven có thể thay placeholder trong resources lúc build và đóng gói giá trị vào JAR. Khi đó artifact có thể thay đổi theo Maven profile; cần xây dựng, test và truy vết từng biến thể. Đặc biệt tránh lọc toàn bộ tài nguyên nhị phân hoặc nhúng password/token vào ứng dụng. Spring Boot starter parent có quy ước filtering và cú pháp placeholder riêng để tránh va chạm với biểu thức `${...}` của Spring; phải cấu hình có chủ đích, không giả định property Maven tự biến thành environment property.

## 9. Maven test, Spring test và Spring profile được chọn ra sao?

Maven profile có thể quyết định **plugin test nào chạy** hoặc thêm cơ chế kiểm tra, nhưng nó không mặc nhiên quyết định active Spring profile của test.

**Ba nơi điều khiển khác nhau:**

1. **Maven `-Pci`:** thay đổi effective POM và cấu hình Surefire/Failsafe/plugin, có thể ảnh hưởng test discovery hoặc JVM test properties nếu bạn chủ động cấu hình.
2. **Spring Test `@ActiveProfiles("test")`:** chỉ định active Spring profile cho application context của test, có thể phối hợp với `application-test.yml`.
3. **System property/environment Spring:** có thể cung cấp active profile cho test process nếu test framework/configuration cho phép; kết quả còn phụ thuộc `@ActiveProfiles` và các nguồn cấu hình được thiết lập.

**Lệnh mẫu:**

```bash
mvn -Pci clean verify
```

Với test `@ActiveProfiles("dev")` của mục 4, profile Spring trong test vẫn là `dev`, bất kể Maven đang áp dụng `ci`. Không suy ra `@ActiveProfiles("ci")` chỉ từ tên Maven profile.

Khi cần chạy integration test với database thật hoặc container, dùng cấu hình Spring test rõ ràng, test resources phù hợp và plugin/phase Maven thực sự đã bind. `mvn verify` không tự sinh integration test nếu dự án chưa cấu hình chúng.

## 10. Ghi nhớ giới hạn của từng công cụ

### Maven profile không phải quản lý môi trường runtime

- Không tự chọn `application-prod.yml` hay bean `@Profile("prod")`.
- Không chắc đã chạy nếu chỉ thấy profile id trong POM; xác nhận bằng `mvn help:active-profiles`.
- Có thể bị ảnh hưởng bởi parent, settings, môi trường build, các trigger activation và `-D`.
- Có thể làm thay đổi artifact; nếu tạo nhiều biến thể JAR, cần phân biệt rõ source, version, checksum và CI evidence.
- Không nên chứa secret trong POM. Repo credentials thuộc cơ chế Maven settings/CI secret manager, runtime secrets do môi trường chạy cấp.

### Spring profile không thay cấu hình build

- Không sửa dependency graph hay compiler plugin đã chạy trong Maven build.
- Không làm Maven chạy thêm Failsafe, JaCoCo hoặc Checkstyle.
- Không chuyển JAR sang executable JAR nếu Maven chưa cấu hình Spring Boot `repackage`.
- Có thể chọn bean/configuration khác nhau đáng kể ở runtime; cùng JAR nhưng hành vi không hoàn toàn giống nhau giữa các môi trường.
- Không tự bảo đảm an toàn của production config: cần health check, monitoring, validation và quản lý secrets.

### Lệnh `-P` và `-D` dễ gây nhầm

| Cú pháp | Bộ xử lý chính | Tác động trực tiếp |
| --- | --- | --- |
| `mvn -Pci package` | Maven | Kích hoạt Maven profile `ci` |
| `mvn -Dbuild.mode=ci package` | Maven | Đặt Maven user property `build.mode` |
| `mvn spring-boot:run -Dspring-boot.run.profiles=dev` | Maven Plugin rồi Spring | Plugin truyền active Spring profile cho ứng dụng |
| `java -Dspring.profiles.active=dev -jar app.jar` | JVM rồi Spring | Đặt JVM system property để Spring đọc |
| `java -jar app.jar --spring.profiles.active=dev` | Spring Boot | Command-line application property |
| `SPRING_PROFILES_ACTIVE=prod` | Môi trường tiến trình rồi Spring | Spring đọc biến môi trường khi chạy |

**Ký hiệu giống nhau không bảo đảm đối tượng nhận giống nhau.** `-D` của Maven là user property cho Maven/plugin; `-D` trước `-jar` là JVM system property cho tiến trình Java đang khởi động. Chỉ một cấu hình truyền cụ thể mới liên kết hai tầng.

## 11. Các lỗi phổ biến và cách kiểm tra

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh và sửa |
| --- | --- | --- |
| Chạy `mvn -Pdev package` nhưng ứng dụng dùng `base` | `-Pdev` chỉ kích hoạt Maven profile | Chọn `--spring.profiles.active=dev` khi chạy JAR; kiểm tra biến môi trường runtime |
| `mvn -Pci verify` thành công, test vẫn chạy với cấu hình `test` hoặc `dev` | Test dùng `@ActiveProfiles` hoặc Spring config riêng | Xem annotation, Spring startup log và cấu hình test |
| Không thấy profile Maven đang hoạt động | Profile id sai, cấu hình ở settings khác hoặc activation chưa khớp | `mvn help:active-profiles` và `mvn help:effective-pom` |
| JAR chạy với `prod` nhưng thông số vẫn giống `dev` | Nguồn cấu hình có precedence cao hơn, dùng nhầm file, env var còn sót | Xem startup log, kiểm tra property source và env của đúng tiến trình |
| Khởi động lỗi sau khi đặt `spring.profiles.active` trong `application-prod.yml` | Đặt thuộc tính chọn profile trong profile-specific file | Chuyển lựa chọn profile sang tài liệu không phụ thuộc profile hoặc tham số khởi động |
| `@Profile("dev")` bean không xuất hiện dù build bằng Maven `-Pdev` | Maven profile không kích hoạt Spring profile | Đặt active Spring profile, xác nhận `Environment` |
| `mvn spring-boot:run -Dspring-boot.run.profiles=dev` có tác dụng nhưng `java -jar` thì không | Property đó do Boot Maven Plugin nhận, không nằm trong JAR runtime args | Với JAR dùng `--spring.profiles.active=dev`/environment/system property |
| CI và local tạo JAR khác nhau | Maven profiles/filters/plugins/dependencies khác nhau | So sánh active Maven profiles, effective POM, Maven/JDK, artifact checksums |
| Lộ token trong artifact | Lọc giá trị môi trường/secrets vào resources lúc build | Loại secret khỏi POM/resources, cấp từ runtime/secret manager |
| Nhiều Spring profiles trùng một property | Spring config precedence và thứ tự file/profile | Xác nhận active profile list, thứ tự `spring.config.location` và nguồn property |

Để điều tra không phải thay đổi ứng dụng:

```bash
# Maven layer
mvn -Pci help:active-profiles
mvn -Pci help:effective-pom

# Spring runtime layer: nhìn log khi khởi động với tham số thật
java -jar target/profile-demo-1.0.0.jar --spring.profiles.active=dev
```

Trong log Spring Boot có thông tin về active profiles hoặc việc dùng default profile. Nếu ứng dụng có Actuator, các endpoint environment/configuration có thể chứa dữ liệu nhạy cảm; không mở công khai chỉ để chẩn đoán profile.

## 12. Bài tập tự kiểm tra

**Tình huống A.** Có Maven profile `ci` bật kiểm tra style và Spring profile `prod` chứa URL database production. Lệnh `mvn -Pci clean verify` có kết nối tới production DB không?

*Đáp án:* Không thể kết luận chỉ từ `-Pci`. Maven profile không tự bật Spring `prod`. Phải kiểm tra active Spring profile của các test và nguồn runtime config của test; với cấu hình bình thường, test không nên chạm production DB.

**Tình huống B.** Bạn muốn deploy cùng bản JAR đã kiểm thử tới `staging` và `prod` nhưng thay URL dịch vụ và mức logging. Nên chọn gì?

*Đáp án:* Giữ nguyên JAR, cấp Spring runtime properties và `spring.profiles.active` tương ứng tại từng môi trường; quản lý secrets ngoài artifact.

**Tình huống C.** Muốn CI fail nếu không có bài test nào được phát hiện. Nên dùng Maven hay Spring profile?

*Đáp án:* Dùng Maven plugin configuration, có thể đặt trong Maven profile `ci` như ví dụ Surefire. Spring `@Profile` không cấu hình chính sách Maven test discovery.

**Tình huống D.** Dự án có Maven profile id `prod`, nhưng `mvn -Pprod package` không tạo production config tự động. Vì sao?

*Đáp án:* Maven chỉ áp dụng nội dung build khai báo trong profile `prod`. Không có cầu nối sang Spring runtime trừ khi project chủ động cấu hình nó. Muốn chạy production, chọn Spring profile và nguồn cấu hình khi chạy ứng dụng.

**Tình huống E.** Trong test có `@ActiveProfiles("test")`, người phát triển chạy `mvn -Pdev test`. Spring test profile nào được chỉ định?

*Đáp án:* `test` bởi annotation Spring, trừ khi có thiết kế override test context cụ thể. Maven `dev` không thay annotation bằng tên profile của nó.

**Tình huống F.** Có file `application-dev.yml` và `application-prod.yml` trong JAR; vậy lúc chạy `java -jar app.jar` không truyền profile thì file nào hoạt động?

*Đáp án:* Không file nào được kích hoạt chỉ vì nó tồn tại. Spring dùng cấu hình chung và default profile theo quy tắc Spring. Với ví dụ mục 4, `/mode` trả `label=base; active=(none)`.

### Kết luận kiến thức cần nhớ

**Maven profile điều khiển cách tạo và kiểm tra artifact; Spring profile điều khiển cấu hình và bean của ứng dụng khi chạy.** Chúng có thể phối hợp nếu được nối qua plugin/property/filtering rõ ràng, nhưng không tự liên kết qua tên `dev`, `test` hay `prod`. Khi có lỗi, hỏi đúng hai câu: *Maven đã kích hoạt profile nào lúc build?* và *Spring đang kích hoạt profile nào trong tiến trình chạy?* Rồi xác minh bằng công cụ đúng tầng.

### Tài liệu chính thức

- Apache Maven — Introduction to Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven — Guide to Configuring Plugins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Boot 3.3 — Externalized Configuration (Profile-specific Files): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Framework — Integration Testing / @ActiveProfiles: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html