# Sử dụng bootTestRun hoặc cấu hình chạy với test classpath khi phù hợp

## 1. Khi nào cần chạy ứng dụng bằng test classpath?

Trong quá trình phát triển Spring Boot, đôi khi bạn muốn **khởi động ứng dụng thật** nhưng cho phép sử dụng những thành phần chỉ có trong test scope:

- Một launcher phục vụ việc xem trước chức năng, đặt trong `src/test/java`.
- Bean giả lập dịch vụ bên ngoài, dữ liệu demo hoặc adapter dành riêng cho máy phát triển.
- Một dependency chỉ có ở `testImplementation`, chẳng hạn thư viện tạo test fixture.
- Tài nguyên trong `src/test/resources`, ví dụ cấu hình sandbox hoặc mẫu dữ liệu.
- Các thành phần hỗ trợ phát triển như Testcontainers, nếu dự án chủ động thiết kế startup/cleanup của chúng.

Spring Boot Gradle Plugin cung cấp sẵn task **`bootTestRun`** cho nhu cầu này. Với Maven, Spring Boot Maven Plugin có goal **`spring-boot:test-run`**; goal `spring-boot:run` cũng có lựa chọn `useTestClasspath` khi chỉ muốn bổ sung test classpath.

Đây là tính năng **chạy ứng dụng khi phát triển**, không phải phương thức thay thế bài kiểm thử tự động. Bài học sẽ trình bày khác biệt giữa chạy bằng main runtime classpath, test runtime classpath, chọn main class đúng và phân phối artifact.

Sau bài học, bạn có thể:

1. Giải thích tại sao `bootRun` và `bootTestRun` có kết quả khác nhau.
2. Tạo launcher ở `src/test/java` để khởi động ứng dụng với cấu hình/bean dùng riêng lúc phát triển.
3. Cấu hình `bootTestRun` trong Gradle Groovy DSL và Kotlin DSL.
4. Tạo task `BootRun` riêng hoặc cấu hình IDE với test runtime classpath khi cần.
5. Chọn lệnh Maven tương đương, đối chiếu với test runner và kiểm tra Boot JAR không chứa thành phần test-only.
6. Tránh các lỗi về main class, classpath, profile, port, test dependency và vòng đời chạy.

**Ngữ cảnh phiên bản:** các ví dụ dùng Spring Boot `3.3.13`, Gradle với Java plugin và Java 17. Những con số này giúp ví dụ nhất quán, không có nghĩa đây là phiên bản mới nhất. Khi dùng dự án thật, xem build tool wrapper và tài liệu đúng phiên bản Spring Boot Gradle/Maven Plugin.

## 2. Phân biệt ba hoạt động rất dễ nhầm

| Hoạt động | Gradle | Classpath thường dùng | Mục đích |
| --- | --- | --- | --- |
| Khởi động ứng dụng chuẩn lúc phát triển | `bootRun` | `sourceSets.main.runtimeClasspath` | Chạy main class và các dependency runtime của ứng dụng |
| Khởi động biến thể dành cho test/dev | `bootTestRun` | `sourceSets.test.runtimeClasspath` | Chạy main class tìm trong test output, có test dependencies/resources |
| Chạy bài kiểm thử tự động | `test` | Test runtime classpath | JUnit/TestNG test runner thực thi test methods và báo pass/fail |

**`bootTestRun` là một `BootRun` task, không phải `Test` task.** Nó khởi động Java process và có thể tiếp tục chạy như ứng dụng web bình thường cho tới khi dừng. Nó không tự tìm và thực thi những phương thức gắn `@Test`.

Spring Boot 3.3 mô tả `bootTestRun` là task được đăng ký cùng `bootRun` khi plugin tích hợp với Java plugin. Task sử dụng **main class trong output của test source set** và **test runtime classpath**. Với `bootRun`, Spring Boot tìm main class trong main output và dùng main runtime classpath.

### 2.1. Main và test classpath khác nhau thế nào?

Theo Gradle Java plugin, cấu trúc thường gặp:

~~~text
src/main/java       → compileJava       → build/classes/java/main
src/main/resources  → processResources  → build/resources/main

src/test/java       → compileTestJava   → build/classes/java/test
src/test/resources  → processTestResources → build/resources/test
~~~

Hai runtime classpath được hiểu khái quát:

~~~text
main.runtimeClasspath
  = main classes + main resources + runtime dependencies

test.runtimeClasspath
  = test classes + test resources
    + main classes/resources + test runtime dependencies
    + các dependency runtime liên quan
~~~

Đây là sơ đồ logic, không phải lệnh tạo classpath thủ công; cấu hình Gradle thật có thể bổ sung/xóa dependencies. Test runtime classpath chứa khả năng dùng code của main, vì code kiểm thử cần gọi code đang được kiểm tra.

Một dependency khai báo `testImplementation` không mặc nhiên xuất hiện trong main runtime classpath. Vì vậy `bootRun` thường không sử dụng nó, còn `bootTestRun` có thể.

### 2.2. Khác nhau giữa “thư viện có trong classpath” và “bean được dùng”

Classpath chỉ quyết định **những class và resource Java có thể nhìn thấy**. Nó không tự:

- Đăng ký mọi class bất kỳ thành Spring bean.
- Chọn một `@Configuration` cụ thể để import.
- Bật Spring profile tên `test`.
- Thay thế bean production bằng mock.
- Chạy JUnit test methods.

Muốn biến thể preview, phải có **quy tắc cấu hình rõ ràng**: launcher riêng, `@Import`, `@Configuration`, profile hay bean override được thiết kế có chủ đích. Đây là điểm quan trọng để tránh suy đoán rằng “đã dùng test classpath thì ứng dụng tự dùng mock”.

## 3. Ví dụ thực hành: production trả một giá trị, preview trả giá trị khác

Ta tạo ứng dụng Spring Boot web có endpoint `GET /greeting`. Bình thường endpoint trả:

~~~text
production
~~~

Khi chạy `bootTestRun`, ứng dụng được khởi động bởi launcher dưới test source set và dùng bean `@Primary` dành riêng cho preview; endpoint trả:

~~~text
preview-from-test
~~~

Sự khác biệt quan sát được chứng minh rằng launcher và cấu hình test-only thực sự có hiệu lực. Đồng thời ta sẽ xác nhận `bootJar` không chứa launcher và preview configuration trong test source set.

### 3.1. Cấu trúc thư mục

~~~text
boot-test-run-demo/
├── settings.gradle               # hoặc settings.gradle.kts
├── build.gradle                  # hoặc build.gradle.kts
└── src/
    ├── main/
    │   └── java/com/example/demo/
    │       ├── DemoApplication.java
    │       ├── GreetingService.java
    │       ├── ProductionGreetingService.java
    │       └── GreetingController.java
    └── test/
        └── java/
            ├── com/example/preview/
            │   ├── PreviewLauncher.java
            │   └── PreviewConfiguration.java
            └── com/example/demo/
                └── ProductionGreetingServiceTest.java
~~~

`PreviewConfiguration` đặt ở package `com.example.preview`, ngoài vùng component scan mặc định của `DemoApplication` trong `com.example.demo`. Như vậy nó chỉ được đăng ký khi launcher preview đưa cấu hình này vào ứng dụng. Đây là lựa chọn có chủ đích để bảo đảm chạy main bình thường không vô tình kích hoạt bean preview.

Trong một repository thật, không cần tạo cả hai bộ Gradle DSL. Dùng một trong hai cặp tệp ở mục 4; chúng là hai biểu diễn tương đương.

## 4. Hai cấu hình Gradle đầy đủ

### 4.1. Groovy DSL

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'boot-test-run-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootTestRun') {
    mainClass = 'com.example.preview.PreviewLauncher'
}
~~~

Khi `java` và Spring Boot Gradle Plugin được áp dụng, Spring Boot đăng ký `bootRun`/`bootTestRun`. Phần `tasks.named('bootTestRun')` giúp chọn launcher test một cách **tường minh**. Nếu không khai báo, Gradle Plugin sẽ tìm main class trong test output; nếu có nhiều class chứa `public static void main(String[])`, bạn nên đặt `mainClass` để tránh phụ thuộc vào cách chọn mặc định.

### 4.2. Kotlin DSL

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-test-run-demo"
~~~

Tệp `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootRun>("bootTestRun") {
    mainClass.set("com.example.preview.PreviewLauncher")
}
~~~

Trong Kotlin DSL, `BootRun` thuộc `org.springframework.boot.gradle.tasks.run.BootRun`; import ở đầu file giúp dùng generic `tasks.named<BootRun>`. Thay đổi `mainClass` không thay đổi classpath của task: `bootTestRun` vẫn dùng test runtime classpath mặc định.

**Cần có Gradle wrapper hoặc Gradle cài đúng phiên bản.** Các tệp cấu hình trên không tự tạo `gradlew`/`gradlew.bat`. Dự án tạo từ Spring Initializr thường đã có wrapper; dùng wrapper được repository cung cấp. Spring Boot 3.3 hỗ trợ JDK 17+; kiểm tra Gradle version/JVM thực tế trước khi build.

### 4.3. Vì sao chỉ có dependency test ở `testImplementation`?

Ví dụ dùng `spring-boot-starter-test` để có JUnit Jupiter và Spring Boot Test utilities trong test compilation. Nó thuộc test scope, không cần là runtime dependency của ứng dụng production. Spring context và annotation thường dùng trong main đã đến từ `spring-boot-starter-web`.

Nếu test launcher dùng thư viện ngoài chỉ dành cho preview, khai báo chúng trong `testImplementation` hoặc `testRuntimeOnly` theo nhu cầu compile/runtime. Không chuyển toàn bộ test dependencies sang `implementation` chỉ để `bootRun` tìm thấy chúng; cách làm này khiến main runtime classpath phình ra và có thể ảnh hưởng packaging.

## 5. Mã Java production: main class, service và endpoint

### 5.1. Main class

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Vùng component scan mặc định bắt đầu ở `com.example.demo`. Code production của bài học nằm trong package này.

### 5.2. Giao diện dùng chung

Tệp `src/main/java/com/example/demo/GreetingService.java`:

~~~java
package com.example.demo;

public interface GreetingService {
    String message();
}
~~~

Public interface để cả production code và test-only launcher ở package khác có thể sử dụng.

### 5.3. Bean production

Tệp `src/main/java/com/example/demo/ProductionGreetingService.java`:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class ProductionGreetingService implements GreetingService {

    @Override
    public String message() {
        return "production";
    }
}
~~~

Khi chạy ứng dụng bình thường, component scan nhận bean này. Nó là implementation mặc định của `GreetingService`.

### 5.4. Controller

Tệp `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting() {
        return greetingService.message();
    }
}
~~~

Spring dùng constructor injection để cung cấp bean `GreetingService`. Bình thường chỉ có bean `ProductionGreetingService` nên `GET /greeting` trả body `production`.

**Lưu ý:** các ví dụ Java là các file riêng theo đúng tên public class. Không chép tất cả vào một tệp Java duy nhất.

## 6. Mã Java test-only: launcher và cấu hình preview

### 6.1. Một cấu hình bean chỉ nằm trong `src/test/java`

Tệp `src/test/java/com/example/preview/PreviewConfiguration.java`:

~~~java
package com.example.preview;

import com.example.demo.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class PreviewConfiguration {

    @Bean
    @Primary
    GreetingService previewGreetingService() {
        return () -> "preview-from-test";
    }
}
~~~

`@Configuration` định nghĩa một bean `GreetingService` khác, `@Primary` khiến Spring ưu tiên bean này khi constructor chỉ yêu cầu một `GreetingService` nhưng có nhiều ứng viên. Component scan của `DemoApplication` chỉ quét `com.example.demo` nên nó **không tự quét `com.example.preview`**. Ta sẽ đăng ký cấu hình preview tường minh ở launcher.

Đặt class này dưới test source root nghĩa là main runtime classpath và Boot JAR thông thường không chứa nó; chỉ môi trường có test classes mới nhìn thấy class này.

### 6.2. Launcher dành cho test runtime

Tệp `src/test/java/com/example/preview/PreviewLauncher.java`:

~~~java
package com.example.preview;

import com.example.demo.DemoApplication;
import org.springframework.boot.SpringApplication;

public class PreviewLauncher {

    public static void main(String[] args) {
        SpringApplication.run(
                new Class<?>[] {
                    DemoApplication.class,
                    PreviewConfiguration.class
                },
                args
        );
    }
}
~~~

Dòng `SpringApplication.run(new Class<?>[] {...}, args)` sử dụng cả ứng dụng production và preview configuration làm nguồn Spring Boot. Spring vẫn quét controller/service production; cấu hình preview bổ sung thêm một bean được ưu tiên nhờ `@Primary`.

Đây là một **Java main method thông thường**, không có `@Test` và không phụ thuộc JUnit runner. Khi `bootTestRun` chạy, Java process gọi `PreviewLauncher.main` rồi tiếp tục chạy web server đến khi người dùng dừng. Vì launcher nằm trong test output, `bootRun` thông thường sẽ không chọn nó và không thể trông chờ vào test classes.

### 6.3. Một JUnit test riêng để chứng minh hai khái niệm khác nhau

Tệp `src/test/java/com/example/demo/ProductionGreetingServiceTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProductionGreetingServiceTest {

    @Test
    void productionMessage() {
        GreetingService service = new ProductionGreetingService();
        assertEquals("production", service.message());
    }
}
~~~

Test này sử dụng JUnit 5 và chạy khi task `test` chạy; nó **không được `bootTestRun` thực thi như một test method**. Khi gọi `bootTestRun`, Gradle có thể biên dịch mã test để tạo test classpath, nhưng biên dịch file test khác với chạy task JUnit Test.

## 7. Chạy thử và quan sát hai kết quả

### 7.1. Chuẩn bị và kiểm tra task

Trong thư mục project chứa build script:

~~~bash
java -version
./gradlew --version
./gradlew tasks --all
./gradlew clean test
~~~

Trên Windows PowerShell, dùng `.\gradlew.bat` thay cho `./gradlew`. Chỉ dùng wrapper nếu repository thực sự có `gradlew`/`gradlew.bat` và `gradle/wrapper`.

Tìm `bootRun`, `bootTestRun` và `test` trong danh sách task. Nếu `bootTestRun` không tồn tại, kiểm tra Spring Boot Gradle Plugin và Java plugin đã được apply đúng module chưa, Gradle sync có lỗi không, và phiên bản plugin có hỗ trợ task không.

`clean test` chạy JUnit test đã khai báo; với sample này `ProductionGreetingServiceTest.productionMessage` cần pass.

### 7.2. Chạy production main qua `bootRun`

~~~bash
./gradlew bootRun --args='--server.port=18080'
~~~

Trong một terminal khác:

~~~bash
curl -s http://localhost:18080/greeting
~~~

Body mong đợi:

~~~text
production
~~~

`bootRun` dùng main runtime classpath và chọn `DemoApplication` từ main output. Không có `PreviewConfiguration` vì nó nằm ở test source set/package và không được đăng ký.

Dừng bằng Ctrl+C. Nếu muốn chạy đồng thời hai biến thể, có thể giữ terminal này mở và dùng cổng khác cho preview như bên dưới.

### 7.3. Chạy test launcher qua `bootTestRun`

~~~bash
./gradlew bootTestRun --args='--server.port=18081'
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:18081/greeting
~~~

Body mong đợi:

~~~text
preview-from-test
~~~

Tại sao có khác biệt?

1. `bootTestRun` lấy `PreviewLauncher` từ test compiled output.
2. Task có classpath bao gồm test classes, main classes/resources và test dependencies.
3. `PreviewLauncher` gọi `SpringApplication.run` với `PreviewConfiguration` trong sources.
4. Spring context có cả production bean và preview bean; `@Primary` chọn preview bean khi inject vào controller.
5. Endpoint vẫn là `/greeting` do production controller định nghĩa; chỉ implementation được inject đổi.

Hai output được mô tả là **body HTTP** từ ứng dụng mẫu khi build/chạy thành công; Gradle và Spring Boot còn in nhiều dòng log startup khác. Nếu cổng bị chiếm, đổi `server.port` và truy cập đúng cổng. Lệnh `curl -s` không tự thêm newline vào response.

### 7.4. Vì sao `bootTestRun` không cần gọi `test` trước?

Task `bootTestRun` dùng test output và test runtime classpath; Gradle có quan hệ producer/task để lấy classes/resources cần thiết. Khi gọi nó, Gradle có thể chạy `compileTestJava`, `processTestResources`, `testClasses` và các task phụ thuộc liên quan. Điều này không đồng nghĩa Gradle sẽ chạy task `test`. Muốn bảo đảm JUnit tests pass trước khi preview, thực hiện `./gradlew test` riêng hoặc tạo dependency rõ ràng theo chính sách dự án.

Đừng dùng “task đã compile test classes” như bằng chứng “bài kiểm thử JUnit đã chạy thành công”.

## 8. Cấu hình thêm cho `bootTestRun` bằng Groovy/Kotlin DSL

`bootTestRun` là loại task `BootRun`, kế thừa khả năng của Gradle `JavaExec`. Có thể cấu hình main class, args, JVM system properties, environment và làm việc với working directory.

### 8.1. Chỉ định main class rõ ràng

**Groovy — fragment bổ sung vào build.gradle có Spring Boot + Java plugin:**

~~~groovy
tasks.named('bootTestRun') {
    mainClass = 'com.example.preview.PreviewLauncher'
}
~~~

**Kotlin — fragment bổ sung vào build.gradle.kts có import BootRun:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    mainClass.set("com.example.preview.PreviewLauncher")
}
~~~

Không cần copy fragment lần thứ hai nếu bản build đầy đủ ở mục 4 đã có cấu hình này.

Đặt main class tường minh có giá trị khi test output có nhiều phương thức `public static void main(String[])`, chẳng hạn nhiều launcher thử nghiệm. Nếu đặt sai package/class name, Gradle có thể báo class not found hoặc không tìm được main.

### 8.2. Đặt tham số mặc định cho một cổng preview

**Groovy:**

~~~groovy
tasks.named('bootTestRun') {
    args '--server.port=18081'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    args("--server.port=18081")
}
~~~

Đây là các fragment bổ sung. Khi đã đặt default args trong script, tránh vô tình truyền thêm tham số cùng tên mà không hiểu cách Spring xử lý các giá trị lặp. Trong bài học này, dùng `--args` trên CLI để thay đổi cổng từng lần là đủ và ít làm thay đổi build script.

### 8.3. Truyền system property riêng cho preview

**Groovy:**

~~~groovy
tasks.named('bootTestRun') {
    systemProperty 'demo.preview', 'true'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    systemProperty("demo.preview", "true")
}
~~~

`System.getProperty("demo.preview")` hoặc Spring property resolution có thể đọc giá trị khi ứng dụng được cấu hình để sử dụng nó. Đừng nhầm JVM system property với Gradle project property `-Pdemo.preview=true`: truyền `-P` cho Gradle không tự chuyển nó vào JVM của app.

### 8.4. Chạy với Spring profile

~~~bash
./gradlew bootTestRun --args='--spring.profiles.active=local'
~~~

Lệnh này bật Spring profile tên `local` cho ứng dụng; chỉ có tác dụng nếu ứng dụng có configuration/bean phụ thuộc profile đó. **Sử dụng test classpath không tự bật profile `test`**. Tương tự, Spring `@ActiveProfiles` trên một class JUnit không tự động áp dụng khi bạn chỉ gọi main method ở `bootTestRun`.

Nếu muốn bật profile cố định, thiết kế launcher hoặc cấu hình task để truyền args/properties phù hợp. Kiểm tra log active profiles trước khi cho rằng profile đã thay đổi.

## 9. Tùy chọn: chạy main production với test runtime classpath

Đôi khi bạn chỉ muốn main class chuẩn `DemoApplication` nhìn thấy dependencies/resources test (ví dụ driver thử nghiệm) mà chưa cần launcher khác. Có thể đăng ký **task BootRun riêng** và đặt classpath là `sourceSets.test.runtimeClasspath`.

### 9.1. Groovy DSL

Fragment cho `build.gradle`:

~~~groovy
tasks.register(
    'runMainWithTestClasspath',
    org.springframework.boot.gradle.tasks.run.BootRun
) {
    group = 'application'
    description = 'Runs the production main with test runtime classpath'
    mainClass = 'com.example.demo.DemoApplication'
    classpath = sourceSets.test.runtimeClasspath
}
~~~

### 9.2. Kotlin DSL

Fragment cho `build.gradle.kts` đã import `BootRun`:

~~~kotlin
tasks.register<BootRun>("runMainWithTestClasspath") {
    group = "application"
    description = "Runs the production main with test runtime classpath"
    mainClass.set("com.example.demo.DemoApplication")
    classpath = sourceSets["test"].runtimeClasspath
}
~~~

Chạy:

~~~bash
./gradlew runMainWithTestClasspath --args='--server.port=18082'
~~~

Nếu dùng chính ứng dụng mẫu của bài, endpoint `GET /greeting` vẫn trả:

~~~text
production
~~~

Vì sao kết quả không thành `preview-from-test` dù test classes đã nằm trên classpath? Main class `DemoApplication` không import `PreviewConfiguration` và component scan không quét package `com.example.preview`. Classpath mới chỉ cho phép class có mặt; nó **không tự đăng ký bean preview**.

Để có preview thật, chọn `PreviewLauncher` làm main hoặc thêm cơ chế cấu hình/activation có kiểm soát. Task riêng ở mục này phù hợp khi cần **test dependency hoặc resource**, trong khi vẫn muốn giữ hành vi startup của production.

### 9.3. Có nên sửa luôn classpath của `bootRun`?

Bạn có thể cấu hình chính `bootRun` dùng test runtime classpath. Tuy nhiên điều đó làm thay đổi ý nghĩa quen thuộc của `bootRun` và có thể khiến thành viên khác tưởng đang chạy với production runtime. Khi có nhu cầu chạy song song hai chế độ, task `runMainWithTestClasspath` có tên riêng thường rõ ràng hơn.

Nếu team quyết định cấu hình `bootRun` sử dụng classpath test, phải tài liệu hóa hành vi đó, chỉ rõ mainClass và kiểm tra tác động tới dev workflow. Không copy test classes/resources vào `src/main` chỉ để `bootRun` tìm thấy chúng.

## 10. Maven: những lựa chọn tương đương

Maven không có Gradle task tên `bootTestRun`. Với Spring Boot Maven Plugin 3.3, những goal/option tương ứng:

| Nhu cầu | Maven | Ý nghĩa |
| --- | --- | --- |
| Khởi động production main bình thường | `spring-boot:run` | Main output/runtime của ứng dụng |
| Khởi động bằng test runtime và ưu tiên test main | `spring-boot:test-run` | Goal dành cho biến thể test/development |
| Giữ goal `run` nhưng thêm test classpath | `spring-boot:run -Dspring-boot.run.useTestClasspath=true` | Bổ sung test dependencies/classpath; không tương đương việc tự chọn test launcher |
| Chạy JUnit | `test` | Maven Surefire/JUnit runner; không phải Spring Boot run goal |

Tài liệu Spring Boot Maven Plugin 3.3 cho biết `test-run` xác định main class theo thứ tự: **mainClass được cấu hình**, sau đó main class tìm trong test classes directory, rồi tới main classes directory. Với ví dụ có `PreviewLauncher`, nên chọn main tường minh để không phụ thuộc số lượng entrypoints.

### 10.1. POM Maven tối thiểu cho cùng ứng dụng

Nếu dự án dùng Maven thay vì Gradle, có thể dùng `pom.xml` sau cùng **các file Java ở mục 5–6**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>boot-test-run-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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
</project>
~~~

Đây là **POM hoàn chỉnh** trong một project Maven riêng. Không dùng đồng thời các lệnh Gradle và Maven như các bước tuần tự của cùng pipeline nếu repository chỉ chọn một build tool. Nếu có Maven wrapper, dùng `./mvnw`/`.\mvnw.cmd`; nếu không, dùng Maven CLI cài phù hợp.

### 10.2. Chạy production và test launcher

Chạy ứng dụng production:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=18080
~~~

Chạy test launcher:

~~~bash
mvn spring-boot:test-run -Dspring-boot.run.main-class=com.example.preview.PreviewLauncher -Dspring-boot.run.arguments=--server.port=18081
~~~

Với ứng dụng mẫu và điều kiện môi trường hợp lệ, kết quả `/greeting` tương ứng là `production` và `preview-from-test`. Goal `test-run` dùng test classpath và test main theo cấu hình; nó vẫn khởi động **ứng dụng Java**, không thay thế `mvn test`.

Nếu chỉ muốn production main có test runtime classpath:

~~~bash
mvn spring-boot:run -Dspring-boot.run.useTestClasspath=true -Dspring-boot.run.main-class=com.example.demo.DemoApplication -Dspring-boot.run.arguments=--server.port=18082
~~~

Lựa chọn `useTestClasspath` của `spring-boot:run` có mặc định false. Trong ví dụ, nó làm các test dependencies/classes khả dụng nhưng không import preview bean vì vẫn khởi động `DemoApplication`. Kết quả endpoint dự kiến vẫn là `production`.

Khi Maven plugin/version khác, kiểm tra tên goal và user properties trong tài liệu tương ứng; không suy luận rằng Maven có option tên `bootTestRun` như Gradle.

## 11. IDE: chạy với test classpath mà không thêm build task

Bạn có thể cần một IDE run configuration để debug test launcher nhanh:

1. Import project bằng Maven/Gradle từ đúng root và đồng bộ dependencies.
2. Chọn Java main class **`com.example.preview.PreviewLauncher`**; đừng chọn `DemoApplication` nếu cần bean preview.
3. Chọn module/classpath của **test source set/test output**, gồm cả test dependencies và main output.
4. Chọn JDK tương thích và program arguments `--server.port=18081`; giữ working directory hợp lệ.
5. Run/Debug, gọi `/greeting`, xác nhận trả `preview-from-test` và xem log active profiles/beans khi cần.

Tên giao diện cụ thể khác nhau giữa IntelliJ IDEA, Eclipse/STS và VS Code:

- **IntelliJ IDEA:** tạo Application run configuration, chọn main class và “Use classpath of module” phù hợp; với Gradle project cần xem module test/classpath IDE đang ánh xạ. Có thể dùng Gradle task `bootTestRun` trực tiếp từ Gradle tool window để bám build configuration.
- **Eclipse/STS:** tạo Java Application run configuration cho `PreviewLauncher`, xác nhận project Build Path chứa test output/dependencies sau Gradle/Maven refresh.
- **VS Code:** Java extension có Java launch configuration; kiểm tra target main class và classpath/module resolution đã nhận test source root. Chạy Gradle/Maven goal trong terminal khi IDE chưa đồng bộ.

**Điểm kiểm chứng cuối cùng:** việc IDE cho phép chọn `PreviewLauncher` không chứng minh run config đang dùng đúng test runtime dependencies. Hãy chạy task/goal chuẩn trên terminal và đối chiếu main class, JDK, args, active profile và output. Đừng thêm test-only dependency vào production runtime để “sửa nhanh” IDE.

## 12. Lưu ý về Spring test configuration, resources và Testcontainers

### 12.1. Không nhầm `@TestConfiguration` và launcher thông thường

Trong Spring Boot tests, `@TestConfiguration` dùng để thêm cấu hình phục vụ kiểm thử, thường với `@Import` hoặc cơ chế Spring Boot Test phù hợp. Nó không có nghĩa mọi `@TestConfiguration` nằm trong test classpath sẽ tự được thêm vào mọi application context.

Ví dụ ở bài dùng một class `@Configuration` bình thường dưới **test source root nhưng ngoài package scan**, rồi launcher đăng ký nó một cách tường minh. Thiết kế này dễ chứng minh: production run không quét config, preview launcher bổ sung config, `@Primary` quyết định injection.

Khi dùng `@TestConfiguration`, hãy đảm bảo cách import và cấu hình khởi động thật sự áp dụng nó. Đừng để ứng dụng chạy “đúng” chỉ vì may mắn classpath scan.

### 12.2. Test resources có thể ảnh hưởng cấu hình runtime

`src/test/resources` thuộc test runtime classpath. Nếu ở đó có `application.properties` hoặc `application.yml`, ứng dụng khởi động bằng `bootTestRun` có thể nhận những property khác `bootRun`, tùy tài nguyên nào có trên classpath và quy tắc ưu tiên của Spring Boot.

Không nên dựa vào duplicate resource path và thứ tự classpath mơ hồ khi muốn điều khiển cấu hình. Ưu tiên đặt file có tên rõ ràng, dùng `spring.config.import` hoặc profile properties có chủ đích, và truyền profile/arguments tường minh. Luôn xem effective configuration/active profiles nếu hành vi khác dự kiến.

Các resource test chỉ phục vụ phát triển không nên bị trộn vào `src/main/resources` hoặc đóng gói vào executable Boot JAR.

### 12.3. Testcontainers và dịch vụ giả lập

Một ứng dụng dev chạy với test classpath có thể dùng thư viện Testcontainers/fixture chỉ có trong `testImplementation`. Tuy nhiên:

- Có class Testcontainers trên classpath **không tự làm container khởi động**; cần code quản lý lifecycle hoặc cơ chế Spring Boot service connection phù hợp.
- Testcontainer thường cần môi trường Docker/container runtime khả dụng.
- Launcher dev chạy lâu, vì vậy cần xem cơ chế đóng container khi app dừng, tránh resource leak.
- Không dùng endpoint/secret/sandbox credentials của môi trường khác mà không xác định rõ quyền và mục đích.

Với bài học cơ bản, bean preview dùng lambda là đủ để hiểu classpath/launcher; không cần Docker hay database để chạy ví dụ.

## 13. `bootTestRun` không thay đổi packaging production

Một ranh giới cần kiểm tra kỹ: **chạy với test classpath không đồng nghĩa đóng test code vào release artifact**.

Theo cấu hình Java/Spring Boot Gradle Plugin thông thường:

- `bootJar` đóng gói classes/resources của **main source set** và production runtime dependencies.
- `src/test/java`, `src/test/resources` và `testImplementation` phục vụ test/dev và không tự đi vào Boot JAR.
- `bootTestRun` khởi động từ test classes/runtime trong môi trường phát triển; nó không thay `bootJar`, không tạo executable JAR để triển khai.

Để kiểm tra:

~~~bash
./gradlew clean test
./gradlew bootJar
jar tf build/libs/boot-test-run-demo-1.0.0.jar
~~~

Trong archive, tìm:

~~~text
BOOT-INF/classes/com/example/demo/DemoApplication.class
BOOT-INF/classes/com/example/demo/GreetingController.class
BOOT-INF/classes/com/example/demo/ProductionGreetingService.class
~~~

Thông thường **không có**:

~~~text
BOOT-INF/classes/com/example/preview/PreviewLauncher.class
BOOT-INF/classes/com/example/preview/PreviewConfiguration.class
BOOT-INF/classes/com/example/demo/ProductionGreetingServiceTest.class
~~~

Tên archive dựa trên root project `boot-test-run-demo` và version `1.0.0` ở ví dụ; nếu dự án có classifier/archiveFileName tùy chỉnh, phải dùng output thực tế thay vì copy cứng đường dẫn.

Kiểm tra ứng dụng đóng gói:

~~~bash
java -jar build/libs/boot-test-run-demo-1.0.0.jar --server.port=18083
~~~

Gọi `GET http://localhost:18083/greeting`, body mong đợi là `production`. Nếu file đóng gói ra `preview-from-test` hoặc chứa preview class, cần kiểm tra việc bạn đã thêm test source set/test dependencies vào `bootJar`/main runtime một cách vô ý.

Maven Spring Boot Plugin `repackage` cũng thông thường đóng production artifact; `spring-boot:test-run` không tự chuyển test-only classes thành nội dung JAR triển khai.

## 14. Khi nào nên chọn cách nào?

| Tình huống | Cách thích hợp | Vì sao |
| --- | --- | --- |
| Chạy ứng dụng như production nhưng dễ debug | `bootRun` hoặc `spring-boot:run` | Main output/runtime chuẩn |
| Cần main class ở `src/test/java` | `bootTestRun` hoặc `spring-boot:test-run` | Test output và test runtime classpath được dùng trực tiếp |
| Chỉ cần runtime có test dependencies, giữ main chuẩn | BootRun task riêng với `test.runtimeClasspath`; Maven `run` + `useTestClasspath` | Tránh viết launcher mới khi không cần |
| Muốn kiểm tra JUnit assertions | `gradlew test` hoặc `mvn test` | Có test runner và kết quả pass/fail |
| Muốn integration test dùng database thật/container | Test task/suite được cấu hình; có thể có test launcher để demo | Cần hợp đồng setup/teardown và assertions |
| Muốn tạo artifact triển khai | `bootJar`/`bootWar` hoặc Maven `package` + `repackage` | Production packaging không dùng test launcher |
| Muốn xem ứng dụng với fixture/mock development | `bootTestRun` cùng test-only configuration được import rõ | Giữ boundary production/test |
| Dự án có source set integrationTest riêng, không dùng test source set mặc định | BootRun task tùy chỉnh với đúng `integrationTest.runtimeClasspath` | `bootTestRun` mặc định chỉ trỏ `test` source set |

Nếu chỉ cần bật profile `local` mà không dùng test dependency/test class, `bootRun --args='--spring.profiles.active=local'` có thể đủ. Thêm test classpath chỉ khi có **nhu cầu thực sự về test-only classes, resources hoặc dependencies**.

## 15. Lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Task 'bootTestRun' not found` | Chưa apply Spring Boot Gradle Plugin hoặc Java plugin vào module; plugin version không hỗ trợ | Xem `plugins`, `./gradlew tasks --all` và version/plugin |
| `Could not find or load main class PreviewLauncher` | File test chưa compile, package/class sai hoặc mainClass không đúng | Kiểm tra `src/test/java`, output `build/classes/java/test` và giá trị `mainClass` |
| Có nhiều main methods và chạy nhầm launcher | Phụ thuộc vào auto-detection | Chỉ định `mainClass` tường minh trong BootRun task |
| `bootTestRun` vẫn trả `production` | Có test classpath nhưng chưa import cấu hình preview/bean chưa được chọn | Kiểm tra launcher, package scan, `@Import`/sources, `@Primary` |
| `bootRun` không thấy dependency test | Test scope không thuộc main runtime classpath | Chọn `bootTestRun` hoặc BootRun task có test classpath; không chuyển dependency production tùy tiện |
| `bootTestRun` không chạy JUnit tests | Đây là task khởi động ứng dụng, không phải test runner | Chạy `gradlew test` hoặc `mvn test` riêng |
| Preview startup lỗi port already in use | Hai app dùng cổng mặc định giống nhau | Truyền `--server.port` khác nhau cho mỗi process |
| `@ActiveProfiles("test")` không hiệu lực | Annotation trên JUnit test không điều khiển Java main launcher | Truyền `--spring.profiles.active=test` hoặc cấu hình launcher |
| IDE chạy khác Gradle | IDE dùng main/test classpath, JVM hoặc args khác | So sánh run config với task `bootTestRun` trong CLI |
| Preview chạy nhưng production JAR lỗi | Preview phụ thuộc test-only bean/dependency | Kiểm tra `bootRun`, `bootJar`/`java -jar` và production dependencies |
| `ClassNotFoundException` chỉ ở `java -jar` | Code release vô tình gọi class thuộc test scope | Chuyển runtime dependency hợp lệ về main hoặc bỏ phụ thuộc test-only |
| Resource test không được nạp | File chưa ở `src/test/resources` hoặc path sai | Kiểm tra `processTestResources`, test output và classpath |
| BootTestRun với Testcontainers treo/không khởi động | Docker hoặc container lifecycle chưa được cấu hình | Xem launcher/service-connection code, Docker availability, log |
| Test source set mới `integrationTest` nhưng bootTestRun không dùng | Task mặc định chọn `test` chứ không phải mọi source set | Tạo BootRun task tùy chỉnh với integrationTest runtime classpath |
| Maven `test-run` không được nhận diện | Plugin prefix/version hoặc project configuration chưa hợp lệ | Kiểm tra Spring Boot Maven Plugin trong POM và version tương thích |

**Đừng nhầm “đã compile được test sources” với “đã chạy tests pass” hoặc “đã có artifact release”.** Ba việc cần được kiểm chứng bằng ba đường chạy khác nhau.

## 16. Quy trình kiểm chứng thực tế

Một quy trình có thể lặp lại khi dự án muốn thêm chế độ preview/test runtime:

1. **Xác định nhu cầu:** cần launcher ở test sources, test dependency, hay chỉ cần Spring profile?
2. **Giữ dependency đúng scope:** production ở `implementation`/`runtimeOnly`, test-only ở `testImplementation`/`testRuntimeOnly`.
3. **Cấu hình launcher minh bạch:** chọn main class rõ ràng và import test-only configuration có chủ đích.
4. **Kiểm tra task:** `./gradlew tasks --all` xác nhận `bootRun`/`bootTestRun` tồn tại trong module ứng dụng.
5. **Chạy unit tests:** `./gradlew clean test`, ghi lại kết quả. Nếu chỉ có launcher mà không có JUnit tests, không tuyên bố tests pass chỉ vì bootTestRun chạy.
6. **Chạy production:** `bootRun` trên cổng riêng, xác nhận endpoint production.
7. **Chạy preview:** `bootTestRun` trên cổng riêng, xác nhận endpoint test-only.
8. **Kiểm tra release:** `bootJar`/`java -jar` phải cho behavior production; dùng `jar tf` xác nhận test-only classes không đóng trong artifact.
9. **Đồng bộ IDE và CI:** ghi rõ task nào dành cho demo/dev, task nào dành cho tests và task nào dành cho packaging.

### Bài tập 1: đọc đúng task/classpath

**Câu hỏi:** `bootTestRun` dùng `sourceSets.test.runtimeClasspath`, vậy có chắc nó tự động chạy mọi JUnit test class tìm thấy không?

**Đáp án:** Không. Task chạy main method của ứng dụng, không là JUnit runner. Muốn chạy assertions dùng `test` và framework kiểm thử.

### Bài tập 2: thêm một test-only dependency

Trong bản Gradle, giả sử preview launcher cần một thư viện mô phỏng, chỉ có ở `testImplementation`. Nó được compile trong `src/test/java` và chạy qua `bootTestRun`. Vì sao `bootRun` không thấy thư viện đó?

**Đáp án:** `bootRun` dùng main runtime classpath. Test dependency không mặc nhiên nằm trong đó; chỉ test runtime classpath mới có. Cần chọn task/classpath đúng mục đích.

### Bài tập 3: phân biệt classpath và bean activation

**Câu hỏi:** `runMainWithTestClasspath` nhìn thấy `PreviewConfiguration.class` nhưng `/greeting` vẫn là `production`. Đây có phải lỗi Gradle thiếu dependency không?

**Đáp án:** Không. Class tồn tại trên classpath nhưng Spring context không được yêu cầu import nó. Launcher preview sử dụng `SpringApplication.run` với thêm source `PreviewConfiguration.class`, sau đó `@Primary` mới áp dụng.

### Bài tập 4: Maven

**Câu hỏi:** khác nhau giữa `spring-boot:test-run` và `spring-boot:run -Dspring-boot.run.useTestClasspath=true`?

**Đáp án:** `test-run` được thiết kế khởi động với test runtime và ưu tiên main từ test classes; `run` với option true giữ goal run nhưng bổ sung test classpath. Khi cần main test, chọn rõ `test-run` hoặc `mainClass` phù hợp.

### Bài tập 5: production packaging

**Câu hỏi:** nếu JAR đã publish có `PreviewLauncher.class` hoặc dependency chỉ dành cho test, điều gì cần kiểm tra?

**Đáp án:** Kiểm tra `sourceSets.main`, `bootJar.classpath`, custom copy/packaging, dependency scopes và có ai đưa test output vào production archive không. Không dựa vào việc bootTestRun hoạt động để kết luận release JAR sạch.

**Tiêu chí đạt:** bạn khởi động được production và preview trên hai cổng, quan sát đúng `production`/`preview-from-test`, chạy được JUnit test riêng, giải thích được test runtime classpath khác main runtime, và chứng minh Boot JAR release không chứa preview launcher.

## 17. Tài liệu chính thức để đối chiếu

- Spring Boot 3.3 — Gradle Plugin, Running your Application / Using a Test Main Class: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — Maven Plugin, Running your Application / `spring-boot:test-run` / `useTestClasspath`: https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html
- Gradle Java Plugin — Source Sets: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle JavaExec task: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html
- Spring Boot 3.3 — Packaging Executable Archives with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html

Khi triển khai trên dự án thật, tra tài liệu đúng Gradle wrapper và Spring Boot plugin version đang chạy. **`bootTestRun` là công cụ tạo một biến thể ứng dụng để phát triển bằng test runtime classpath; tính đúng đắn của tests và tính sạch của artifact production vẫn phải được xác nhận độc lập.**
