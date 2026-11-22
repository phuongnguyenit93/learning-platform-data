# Phân biệt profile Spring với profile hoặc task của build tool

Trong một dự án Spring Boot, từ **profile** có thể xuất hiện ở cả Spring Framework, Maven và Gradle. Chúng thường được đặt những tên giống nhau như `dev`, `test` hoặc `prod`, nhưng không mang cùng ý nghĩa. Một **Spring profile** quyết định cấu hình và bean nào được sử dụng khi ApplicationContext khởi tạo; một **Maven profile** thay đổi mô hình build của Maven; còn **Gradle task** chỉ định công việc build hoặc chạy ứng dụng mà Gradle sẽ thực hiện.

Nhầm lẫn ba khái niệm này có thể dẫn đến tình huống chạy lệnh build thành công nhưng ứng dụng vẫn kết nối nhầm môi trường, hoặc đóng gói một JAR tưởng là production nhưng khi triển khai lại hoạt động với cấu hình mặc định.

## 1. Ba câu hỏi khác nhau: build gì, chạy gì, cấu hình nào?

Hãy phân biệt các câu hỏi:

- **Build tool:** cần biên dịch, kiểm thử, đóng gói hay xuất bản artifact? Có cần thay dependency hoặc cách build không?
- **Spring profile:** khi ứng dụng chạy, bean và cấu hình ứng dụng nào phải được kích hoạt?
- **Môi trường triển khai:** tiến trình được chạy ở đâu, với biến môi trường, file cấu hình và secret nào?

Ví dụ một service có thể:

1. Dùng Maven hoặc Gradle để tạo `catalog-service.jar`.
2. Đưa chính JAR đó lên staging và production.
3. Khởi chạy staging với Spring profile `staging`.
4. Khởi chạy production với Spring profile `prod`.

Không cần tạo một JAR riêng cho mỗi Spring profile nếu logic và dependency đóng gói vẫn giống nhau. Cách này giúp artifact bất biến và làm cho quá trình phát hành dễ kiểm chứng hơn.

### Bảng so sánh nhanh

| Khái niệm | Thuộc hệ thống | Thời điểm tác động | Tác dụng chính |
|---|---|---|---|
| Spring profile | Spring Framework / Spring Boot | Khi tạo ApplicationContext | Chọn bean, điều kiện `@Profile`, file cấu hình theo profile |
| Maven profile | Maven | Khi Maven xây dựng effective POM và chạy lifecycle | Chọn properties, dependencies, plugins, build settings theo cấu hình POM |
| Gradle task | Gradle | Khi chạy build hoặc lệnh task | Thực hiện công việc như `test`, `bootJar`, `bootRun`, `publish` |
| Gradle project property (`-P`) | Gradle | Khi đọc và thực thi build script | Cung cấp giá trị đầu vào cho build script; chỉ có hiệu lực nếu script sử dụng |
| Gradle `--profile` | Gradle | Khi chạy Gradle build | Tạo báo cáo profiling hiệu năng build, không phải Spring profile |

Tên giống nhau chỉ là quy ước do dự án đặt. Spring không tự động đọc Maven profile đang bật hay tên Gradle task để quyết định `spring.profiles.active`.

## 2. Spring profile điều khiển điều gì?

Spring profile là một nhóm cấu hình logic. Spring sử dụng active profiles để quyết định bean có điều kiện `@Profile` nào được đăng ký, đồng thời Spring Boot sử dụng chúng khi chọn Config Data theo profile.

Ví dụ, ứng dụng có hai implementation của `NotificationGateway`:

~~~java
public interface NotificationGateway {
    void send(String message);
}
~~~

Implementation dành cho môi trường phát triển:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class LoggingNotificationGateway implements NotificationGateway {

    @Override
    public void send(String message) {
        System.out.println("DEV notification: " + message);
    }
}
~~~

Implementation dành cho production:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class HttpNotificationGateway implements NotificationGateway {

    @Override
    public void send(String message) {
        // Gửi qua dịch vụ thông báo đã cấu hình.
    }
}
~~~

Khi profile `dev` hoạt động, Spring xét đăng ký `LoggingNotificationGateway`. Với profile `prod`, Spring xét `HttpNotificationGateway`.

`@Profile` chỉ là một điều kiện đăng ký bean, không phải cơ chế chạy build. Nếu hai profile cùng được kích hoạt, cả hai implementation có thể cùng tồn tại và dẫn đến nhiều candidate cho injection theo interface. Cần thiết kế tổ hợp profile, `@Primary`, `@Qualifier` hoặc điều kiện rõ ràng theo nhu cầu.

### Cấu hình file theo Spring profile

Trong `src/main/resources`, có thể đặt:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

File chung:

~~~yaml
spring:
  application:
    name: notification-service

app:
  notifications:
    timeout: 5s
~~~

File `application-dev.yml`:

~~~yaml
app:
  notifications:
    endpoint: http://localhost:8081
    timeout: 1s
~~~

File `application-prod.yml`:

~~~yaml
app:
  notifications:
    endpoint: https://notifications.example.test
    timeout: 3s
~~~

Khi Spring profile `prod` được kích hoạt, Spring Boot nạp tài liệu cấu hình theo profile tương ứng theo thứ tự ưu tiên Config Data. Các thuộc tính không được ghi đè có thể tiếp tục lấy từ `application.yml` và các nguồn cấu hình khác.

`application-prod.yml` **không tự được kích hoạt** chỉ vì build sử dụng một tham số tên `prod`. Spring Boot phải nhận được active profile trong quá trình khởi động.

## 3. Cách kích hoạt Spring profile khi chạy ứng dụng

Spring Boot có nhiều cách cung cấp `spring.profiles.active`. Đây là thuộc tính của **ứng dụng đang chạy**, không phải lệnh chọn cấu hình build.

### Tham số dòng lệnh Spring Boot

Sau khi đóng gói JAR:

~~~bash
java -jar build/libs/notification-service.jar --spring.profiles.active=dev
~~~

Với Maven, vị trí artifact thường là `target/`:

~~~bash
java -jar target/notification-service.jar --spring.profiles.active=prod
~~~

Tên JAR thực tế phụ thuộc cấu hình build. Điều quan trọng là `--spring.profiles.active=prod` được truyền sau tên JAR, để Spring Boot đọc nó như application argument.

### Biến môi trường

Trên Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar notification-service.jar
~~~

Trong Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar notification-service.jar
~~~

Biến `SPRING_PROFILES_ACTIVE` tương ứng với thuộc tính `spring.profiles.active` theo cơ chế externalized configuration.

### Java system property

Có thể truyền một JVM system property bằng `-D` **trước** `-jar`:

~~~bash
java -Dspring.profiles.active=prod -jar notification-service.jar
~~~

Khác biệt giữa hai dạng:

~~~text
java -Dspring.profiles.active=prod -jar app.jar
java -jar app.jar --spring.profiles.active=prod
~~~

Dòng đầu dùng JVM system property; dòng sau dùng Spring Boot command-line property. Cả hai có thể kích hoạt Spring profile nhưng thuộc những nguồn cấu hình khác nhau và chịu quy tắc ưu tiên riêng.

### Chọn profile mặc định

Có thể chỉ định giá trị khi chưa kích hoạt profile nào:

~~~yaml
spring:
  profiles:
    default: local
~~~

Giá trị `spring.profiles.default` quy định default profile set được dùng khi không có active profile. Nếu không cấu hình rõ, Spring sử dụng default profile có tên `default`.

Default profile không có nghĩa mọi môi trường đều là `local`; đó chỉ là fallback do dự án chọn. Cần kiểm tra mục đích trước khi dùng default profile cho các tích hợp có tác động thật.

## 4. Maven profile: thay đổi cách Maven build

Maven profile là một phần của POM, được dùng để chọn hoặc điều chỉnh cấu hình build như properties, dependencies, plugin configuration và những thành phần build được Maven hỗ trợ.

Ví dụ POM khai báo profile `ci` để thiết lập một property cho quá trình build:

~~~xml
<project>
    <!-- Các phần cấu hình POM thông thường -->

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <build.channel>continuous-integration</build.channel>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Kích hoạt profile đó:

~~~bash
mvn -Pci package
~~~

Khi Maven tạo effective POM, nó đưa các cấu hình hợp lệ từ Maven profile `ci` vào mô hình build. Trong ví dụ trên, property `build.channel` chỉ tạo khác biệt thực tế nếu phần khác của build tiêu thụ nó; một property tùy ý không tự thay đổi Java code hoặc môi trường chạy.

Lưu ý:

- `-Pci` là tham số của **Maven**, không phải `spring.profiles.active`.
- `package` là một phase của Maven lifecycle.
- Maven profile có thể được kích hoạt bằng `-P`, theo điều kiện trong POM hoặc qua thiết lập Maven phù hợp.
- Tên Maven profile `prod` không có ý nghĩa đặc biệt với Spring Boot nếu dự án chưa viết cấu hình liên kết chúng.

Ví dụ:

~~~bash
mvn -Pprod package
~~~

Lệnh này yêu cầu Maven dùng build profile tên `prod` nếu profile đó được khai báo và kích hoạt thành công. Nó **không** tự động tương đương với:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Một artifact được build bằng Maven profile `prod` vẫn có thể chạy với Spring profile `dev`, `test` hoặc không có active profile, trừ khi build đã chủ động thay đổi những resource hoặc logic khác.

### Maven profile có thể thay đổi artifact

Maven profile có thể thay dependencies, build properties, resource filtering hoặc plugin execution. Nếu dự án quyết định dùng Maven profile để đóng gói file riêng cho từng môi trường, output JAR có thể khác nhau.

Đó là **quyết định cấu hình build**, không phải bản chất của Spring profile. Cách làm này có thể hữu ích cho các biến thể sản phẩm thật sự khác nhau, nhưng khiến việc xác nhận một artifact duy nhất dùng được ở mọi môi trường khó hơn.

Nếu nhu cầu chỉ là đổi endpoint, timeout hoặc thông tin triển khai, thường nên giữ artifact giống nhau và truyền Spring properties khi khởi chạy thay vì dùng Maven profile để nhúng giá trị môi trường vào JAR.

## 5. Gradle task: thực hiện công việc, không tự chọn Spring profile

Gradle tổ chức build quanh các **task**. Một dự án Spring Boot thường có các task liên quan như:

| Task | Vai trò |
|---|---|
| `compileJava` | Biên dịch source Java |
| `test` | Chạy các bài kiểm thử theo cấu hình Gradle |
| `bootJar` | Đóng gói executable Spring Boot JAR |
| `bootRun` | Chạy ứng dụng bằng Gradle |
| `build` | Thực hiện lifecycle build theo các dependency task |
| `publish` | Xuất bản artifact khi được cấu hình plugin publishing phù hợp |

Ví dụ:

~~~bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
~~~

Các lệnh này yêu cầu Gradle chạy task tương ứng. Bản thân tên task không chỉ định active Spring profile.

`bootJar` **đóng gói ứng dụng**; nó không chạy ứng dụng theo Spring profile nào. `bootRun` **chạy ứng dụng**; khi đó Spring profile có thể được cung cấp như argument hoặc environment của tiến trình được chạy.

### Chạy bootRun với Spring profile

Gradle hỗ trợ truyền application arguments cho `bootRun`:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

Trên Windows PowerShell, có thể dùng:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
~~~

Ở đây:

- `bootRun` là Gradle task.
- `--args` là tham số Gradle dùng để truyền argument đến ứng dụng Java do task chạy.
- `--spring.profiles.active=dev` mới là tham số Spring Boot nhận để kích hoạt Spring profile.

Nếu muốn build JAR rồi chạy production, đó là hai bước độc lập:

~~~bash
./gradlew bootJar
java -jar build/libs/notification-service.jar --spring.profiles.active=prod
~~~

Đường dẫn JAR mang tính minh họa; hãy dùng đúng filename do `bootJar` tạo ra.

## 6. Gradle -P không phải Spring profile

Gradle có option `-P` để cung cấp **project property** cho build script:

~~~bash
./gradlew -PtargetEnv=prod bootJar
~~~

Giá trị `targetEnv=prod` thuộc Gradle. Nó chỉ có tác dụng nếu `build.gradle` hoặc `build.gradle.kts` đọc property đó và sử dụng trong logic build.

Ví dụ trong Gradle Kotlin DSL, có thể đọc project property để hiển thị thông tin build:

~~~kotlin
val targetEnv = providers.gradleProperty("targetEnv")
    .orElse("unspecified")

tasks.register("printTargetEnvironment") {
    doLast {
        println("Build target: " + targetEnv.get())
    }
}
~~~

Chạy:

~~~bash
./gradlew -PtargetEnv=prod printTargetEnvironment
~~~

Kết quả có thể là:

~~~text
Build target: prod
~~~

Đây vẫn chỉ là giá trị trong **Gradle build script**. Không có Spring ApplicationContext nào được tạo bởi task minh họa này, nên không có Spring profile nào được kích hoạt.

### Cẩn thận với Gradle --profile

Gradle cũng có option:

~~~bash
./gradlew build --profile
~~~

`--profile` ở đây dùng để tạo báo cáo profiling của quá trình Gradle build. Nó không tương đương `spring.profiles.active` và không có nghĩa kích hoạt một Spring profile tên `build`.

Vì vậy, nên tránh dùng riêng từ “profile” khi trao đổi trong team mà không nói rõ đang đề cập đến Spring hay build tool.

## 7. Maven spring-boot:run và Spring profile

Spring Boot Maven Plugin hỗ trợ goal `spring-boot:run`, cho phép chạy ứng dụng trong giai đoạn phát triển.

Có thể truyền profile bằng user property dành cho plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Trong lệnh này:

- `spring-boot:run` là goal của Spring Boot Maven Plugin.
- `-Dspring-boot.run.profiles=dev` là property cấu hình goal chạy ứng dụng.
- Plugin truyền `dev` vào quá trình chạy để Spring Boot kích hoạt Spring profile tương ứng.

Lệnh này **khác** `mvn -Pdev spring-boot:run`. Nếu Maven profile `dev` không có cấu hình riêng liên kết với goal chạy, nó không tự kích hoạt `dev` trong Spring.

Đây là ví dụ cho thấy build tool **có thể được cấu hình để truyền profile khi chạy**, nhưng cơ chế đó phải rõ ràng. Nó không phải mối liên hệ tự động chỉ vì hai profile cùng tên.

### Vì sao không nên coi -D trong Maven và java -D là một?

Cú pháp `-D` được cả Maven và JVM sử dụng, nhưng tham số được nhận bởi tiến trình khác nhau.

~~~text
mvn -Dsome.property=value ...
java -Dsome.property=value -jar ...
~~~

Dòng đầu đặt Maven user property. Dòng sau đặt JVM system property cho tiến trình Java đang chạy. Không nên giả định mọi Maven `-Dspring.profiles.active=...` sẽ tự đi tới JVM ứng dụng, nhất là khi plugin có cơ chế fork hoặc cấu hình argument riêng.

Khi dùng `spring-boot:run`, nên truyền thuộc tính mà plugin hỗ trợ hoặc cấu hình plugin tường minh, sau đó xác nhận active profile trong log của ứng dụng.

## 8. Build profile và Spring profile có thể dùng cùng tên không?

Có thể, nhưng nên hiểu chúng có **hai không gian ý nghĩa riêng**.

Ví dụ một dự án có:

- Maven profile `prod`: chọn cấu hình build phù hợp pipeline phát hành.
- Spring profile `prod`: chọn beans và Config Data khi JVM chạy trong môi trường production.

Hai cấu hình đó có thể cùng tồn tại:

~~~bash
mvn -Pprod package
java -jar target/notification-service.jar --spring.profiles.active=prod
~~~

Lệnh thứ nhất chọn Maven build profile. Lệnh thứ hai chọn Spring runtime profile.

Không nhất thiết phải dùng chung tên. Một cách tổ chức dễ hiểu hơn có thể là:

- Maven profiles: `ci`, `release`, `integration-tests`.
- Gradle tasks: `test`, `bootJar`, `integrationTest`, `publish`.
- Spring profiles: `local`, `staging`, `prod`.

Cách đặt tên dựa trên **mục đích** giúp giảm nguy cơ nhầm lẫn. Build profile nói về cách tạo artifact; Spring profile nói về cách ứng dụng vận hành.

## 9. Bài toán thường gặp: chạy test với Spring profile test

Việc chạy Gradle task `test` hoặc Maven phase `test` không đồng nghĩa Spring profile `test` tự được kích hoạt.

~~~bash
./gradlew test
mvn test
~~~

Hai lệnh trên yêu cầu build tool chạy test. Trong một bài test Spring Boot, có thể chọn profile bằng annotation `@ActiveProfiles`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTests {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertThat(environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("test")
        )).isTrue();
    }
}
~~~

`@ActiveProfiles("test")` thuộc Spring Test. Nó điều khiển active profiles cho ApplicationContext được dựng trong bài test; Gradle và Maven chỉ đảm nhiệm việc chạy các test class theo cấu hình build.

Có thể thêm file `application-test.yml` vào `src/test/resources` để cấu hình riêng cho test. Khi dùng `@ActiveProfiles("test")`, Spring Boot có thể nạp Config Data theo profile này cho context của bài test.

Trong dự án có nhiều loại test, nên quyết định profile ở cấp test hoặc test configuration thay vì mặc định dùng tên build task làm profile Spring. Ví dụ task `integrationTest` không tự khiến mọi test của task đó dùng Spring profile `integrationTest`.

## 10. Active profiles và property sources không thuộc build tool

Khi một ứng dụng khởi chạy, Spring Boot giải quyết `spring.profiles.active` từ các nguồn cấu hình, chẳng hạn:

- Command-line arguments: `--spring.profiles.active=prod`.
- Environment variable: `SPRING_PROFILES_ACTIVE=prod`.
- JVM system property: `-Dspring.profiles.active=prod`.
- Property trong file `application.yml` không thuộc profile-specific document.
- Cấu hình chương trình qua `SpringApplication` hoặc `Environment` ở thời điểm phù hợp.

Nếu nhiều nguồn cùng đặt giá trị, Spring áp dụng thứ tự ưu tiên property sources.

Ví dụ, file `application.yml` chứa:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Nhưng tiến trình chạy với:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Tham số dòng lệnh có độ ưu tiên cao hơn cấu hình file theo quy tắc thông thường, nên `prod` là profile được chọn. Đây là quyết định khi ứng dụng chạy, không liên quan tới Maven profile hoặc Gradle task dùng để build JAR.

### Không đặt spring.profiles.active trong file profile-specific

Không nên cấu hình `spring.profiles.active` trong `application-prod.yml` hoặc trong YAML document đã được kích hoạt bằng `spring.config.activate.on-profile`. Spring Boot giới hạn các thuộc tính kích hoạt profile ở tài liệu cấu hình không phụ thuộc profile để tránh vòng lặp hoặc kết quả khó dự đoán.

Ví dụ nên dùng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

thay vì đặt `spring.profiles.active: prod` bên trong chính `application-prod.yml`.

### Nhiều profile đồng thời

Spring hỗ trợ nhiều active profiles, ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=prod,metrics
~~~

Các bean và file cấu hình được kích hoạt theo những profile tương ứng, chịu quy tắc kết hợp và ưu tiên của Spring Boot. Nếu hai profile cung cấp các bean cùng kiểu hoặc những cấu hình mâu thuẫn, cần thiết kế điều kiện và độ ưu tiên rõ ràng.

Đừng biến profile thành một cách thay thế hoàn toàn cho typed configuration. Với thay đổi chỉ là URL, timeout hoặc bật/tắt một tính năng đơn lẻ, property thường là lựa chọn đơn giản hơn việc tạo thêm nhiều profile.

## 11. Khi nào cần build artifact khác nhau?

Có những trường hợp thực sự cần thay đổi tại build time, chẳng hạn:

- Build nhiều sản phẩm có dependency khác nhau.
- Tạo distribution cho các nền tảng hoặc runtime khác nhau.
- Dùng toolchain hoặc compiler option riêng.
- Chỉ chạy một nhóm test, tạo docs hoặc publish artifact.
- Sử dụng resource processing có chủ đích để đưa metadata build vào artifact.

Khi đó Maven profile hoặc Gradle task/property là phù hợp. Tuy nhiên, không nên dùng build-time configuration để che giấu một quyết định thực chất cần diễn ra tại runtime.

Ví dụ, nếu staging và production dùng cùng Java code, chỉ khác endpoint, credential và giới hạn, nên sử dụng cùng một JAR và cung cấp các giá trị qua externalized configuration.

Sơ đồ triển khai:

~~~text
Source code + build.gradle / pom.xml
                |
                v
       Maven package / Gradle bootJar
                |
                v
        notification-service.jar
                |
         +------+------+
         |             |
         v             v
      Staging       Production
         |             |
         v             v
SPRING_PROFILES_  SPRING_PROFILES_
ACTIVE=staging    ACTIVE=prod
         |             |
         v             v
Spring context    Spring context
dành cho staging  dành cho production
~~~

Artifact giống nhau nhưng ApplicationContext có thể có bean và giá trị cấu hình khác nhau khi khởi chạy.

## 12. Phân biệt các lệnh thường bị nhầm

| Lệnh | Tác động trực tiếp |
|---|---|
| `mvn -Pprod package` | Kích hoạt Maven profile `prod` khi chạy phase `package` |
| `mvn spring-boot:run -Dspring-boot.run.profiles=prod` | Chạy ứng dụng qua Maven plugin với Spring profile `prod` |
| `./gradlew -PtargetEnv=prod bootJar` | Đưa Gradle property `targetEnv` vào build; chạy task `bootJar` |
| `./gradlew bootRun --args='--spring.profiles.active=prod'` | Chạy ứng dụng bằng Gradle với Spring profile `prod` |
| `./gradlew build --profile` | Chạy build và bật báo cáo profiling hiệu năng của Gradle |
| `java -jar app.jar --spring.profiles.active=prod` | Chạy JAR với Spring profile `prod` |
| `SPRING_PROFILES_ACTIVE=prod java -jar app.jar` | Truyền biến môi trường cho tiến trình Java trong shell phù hợp |
| `java -Dspring.profiles.active=prod -jar app.jar` | Chạy JVM với system property kích hoạt Spring profile `prod` |

Từ bảng có thể thấy cùng chuỗi `prod` nhưng vai trò rất khác nhau tùy vị trí của nó trong lệnh.

## 13. Những lỗi thường gặp

### Build bằng -Pprod rồi tưởng Spring đã bật prod

`mvn -Pprod package` chỉ kích hoạt Maven build profile, nếu được khai báo. `./gradlew -PtargetEnv=prod bootJar` chỉ tạo một Gradle project property mà build script có thể dùng. Cả hai không tự thiết lập `spring.profiles.active`.

Cần kiểm tra lệnh chạy JAR, biến môi trường của tiến trình và effective Spring configuration.

### Đóng gói application-prod.yml nhưng ứng dụng vẫn đọc default

File `application-prod.yml` có thể đã nằm trong JAR nhưng Spring không tự kích hoạt `prod` chỉ vì file tồn tại. Cần có Spring profile `prod` hoạt động hoặc cơ chế Config Data kích hoạt tài liệu tương ứng.

### Coi task test là Spring test profile

Gradle task `test` và Maven phase `test` chỉ chạy kiểm thử. Để dùng Spring profile `test` trong ApplicationContext của test, hãy dùng `@ActiveProfiles("test")` hoặc cấu hình context phù hợp.

### Dùng profile để chứa secret trong source code

Không nên commit `application-prod.yml` có credential thật hoặc token riêng cho production. Spring profile chỉ chọn cấu hình; nó không bảo vệ thông tin bí mật. Secret cần được cung cấp qua cơ chế quản lý secret của môi trường triển khai và quyền truy cập thích hợp.

### Dùng Maven profile để tạo một artifact riêng cho mỗi endpoint

Nếu chỉ khác giá trị runtime, cách này thường khiến quá trình quản lý artifact phức tạp hơn. Giữ artifact bất biến và dùng cấu hình ngoài JAR thường dễ kiểm soát hơn.

### Tin rằng active profile không thể bị ghi đè

Một file classpath có thể đặt profile mặc định hoặc active profile, nhưng command-line argument, environment variable hoặc system property ưu tiên cao hơn có thể ghi đè. Khi ứng dụng dùng sai profile, hãy kiểm tra toàn bộ property sources, không chỉ đọc `application.yml`.

### Không kiểm tra bean theo nhiều active profiles

Nếu `dev` và `prod` đều được kích hoạt mà hai class cùng triển khai một interface, ứng dụng có thể gặp lỗi ambiguous dependency hoặc hành vi ngoài ý muốn. Hãy kiểm tra tổ hợp profile hợp lệ và cấu hình điều kiện rõ ràng.

## 14. Quy trình chọn cơ chế phù hợp

Khi nhận yêu cầu “cần profile cho môi trường X”, hãy làm rõ bản chất của thay đổi:

1. Nếu cần thay bean hoặc nạp file `application-{profile}.yml` khi ApplicationContext tạo, dùng **Spring profile**.
2. Nếu cần thay compiler, dependency, plugin hoặc quá trình đóng gói, dùng **Maven profile** hoặc cấu hình build tương ứng.
3. Nếu cần quyết định công việc build/test/run, dùng **Gradle task** hoặc Maven lifecycle goal/phase.
4. Nếu build script cần tham số, dùng Gradle `-P` hoặc Maven property/profile theo cơ chế của build tool.
5. Nếu chỉ thay endpoint, timeout hoặc feature flag theo môi trường, cân nhắc **externalized configuration** thay vì tạo một artifact build khác.
6. Nếu muốn chạy ứng dụng trực tiếp qua Maven/Gradle với một Spring profile, truyền tham số chạy ứng dụng theo cách plugin/task hỗ trợ.
7. Khi triển khai JAR, xác nhận `SPRING_PROFILES_ACTIVE`, `spring.profiles.active` và các file cấu hình bên ngoài mà JVM thực sự nhận.
8. Với test, chọn Spring profile của context bằng cơ chế Spring Test và kiểm tra trường hợp profile được kích hoạt như mong muốn.

Điểm mấu chốt: **Spring profile chọn cấu hình của ApplicationContext; Maven profile chọn cấu hình build; Gradle task chọn công việc build hoặc chạy.** Các cơ chế có thể phối hợp, nhưng không tự động liên kết chỉ vì cùng tên `dev` hoặc `prod`. Khi tách rõ quyết định build-time và runtime, một dự án Spring Boot sẽ dễ triển khai, kiểm thử và chẩn đoán hơn.

