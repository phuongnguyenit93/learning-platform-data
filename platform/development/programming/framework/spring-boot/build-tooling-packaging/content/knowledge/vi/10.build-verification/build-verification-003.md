# Tách kiểm thử tích hợp bằng Maven Failsafe hoặc Gradle test suite

## 1. Vì sao cần tách unit test và integration test?

Khi phát triển Spring Boot, **unit test** thường kiểm tra một hàm hoặc một class riêng lẻ, không cần khởi tạo toàn bộ ứng dụng. **Integration test** kiểm tra sự phối hợp giữa nhiều thành phần: HTTP controller, Spring application context, cơ sở dữ liệu, message broker hoặc một dịch vụ khác. Hai nhóm có chi phí và điều kiện chạy khác nhau.

Ví dụ trong ứng dụng có endpoint GET /greet:

- **Unit test** gọi trực tiếp phương thức GreetingService.greet(" Ada ") và kiểm tra chuỗi kết quả. Không chạy HTTP server.
- **Integration test** khởi động Spring Boot trên **cổng ngẫu nhiên**, gửi HTTP GET /greet?name=Ada bằng một client, rồi so sánh status code và response body. Nó kiểm tra wiring, request mapping, HTTP stack và logic xử lý chung.

Nếu trộn mọi test vào một task/pha, mỗi lần sửa một hàm nhỏ cũng có thể phải khởi động Spring context hoặc hạ tầng ngoài. Việc tách giúp **feedback nhanh**, dễ chia nhóm kiểm thử trên CI và nhìn rõ lỗi do code đơn vị hay do tích hợp. Tuy nhiên, test tích hợp vẫn phải được chạy ở cổng kiểm soát chất lượng thích hợp, không được “tách” rồi quên chạy.

Có hai cơ chế tương ứng:

1. **Maven:** dùng **maven-surefire-plugin** chạy unit test và **maven-failsafe-plugin** chạy integration test theo các pha Maven lifecycle.
2. **Gradle:** dùng **JVM Test Suite plugin** (cung cấp qua Java plugin), khai báo suite **integrationTest** với nguồn, dependency, task và báo cáo tách khỏi suite **test** mặc định.

**Ngữ cảnh cấu hình:** Spring Boot **3.3.5**, Java **17**, Maven Surefire/Failsafe **3.5.4** và Gradle **8.5**. Đây là một bộ phiên bản mẫu để minh họa cú pháp; không đồng nghĩa là bản mới nhất hoặc phù hợp với mọi repository. Luôn kiểm tra tương thích Gradle/Maven, Java và Spring Boot khi nâng cấp.

## 2. Phân biệt phạm vi các loại kiểm thử

| Đặc điểm | Unit test | Integration test | End-to-end (E2E) test |
| --- | --- | --- | --- |
| Mục tiêu | Một class/hàm hoặc nhóm nhỏ độc lập | Nhiều thành phần kết hợp theo contract thực | Một luồng người dùng/hệ thống gần môi trường thật |
| Mức khởi tạo | Thường không khởi động Spring | Có thể khởi động Spring context, HTTP server, DB | Có thể cần nhiều service, frontend, browser |
| Tốc độ điển hình | Nhanh, dễ lặp lại | Chậm hơn, nhiều setup hơn | Thường chậm và tốn tài nguyên nhất |
| Phụ thuộc ngoài | Nên tránh | Có thể dùng database/container/mock server có kiểm soát | Có thể dùng môi trường staging |
| Ví dụ | GreetingServiceTest | GreetingHttpIT | Đăng nhập UI → đặt hàng → nhận xác nhận |

**Tên file không tự quyết định loại test.** Một lớp có tên MyIntegrationTest vẫn có thể chỉ là unit test, và một lớp MyIT có thể chứa kiểm tra rất đơn giản. Tên, thư mục và Gradle/Maven configuration là **cách tổ chức chạy**, còn mức “tích hợp” đến từ hành vi test thực sự.

Một số test ở mức trung gian như **@WebMvcTest + MockMvc** kiểm tra MVC slice mà không khởi động HTTP server thật; chúng thường nhẹ hơn **@SpringBootTest(webEnvironment = RANDOM_PORT)**. Phân nhóm theo chi phí và mục tiêu kiểm tra, không chỉ theo annotation.

## 3. Sơ đồ hai tuyến kiểm thử

~~~text
                 Nguồn ứng dụng
                 src/main/java
                      |
                      v
                   compile
                      |
          +-----------+------------+
          |                        |
          v                        v
  UNIT TEST PIPELINE      INTEGRATION TEST PIPELINE
  GreetingServiceTest     GreetingHttpIT
  không HTTP server       khởi động Spring Boot HTTP
  chạy nhanh              gọi endpoint thật bằng HTTP
          |                        |
          v                        v
     Surefire/test          Failsafe/integrationTest
          |                        |
          +-----------+------------+
                      |
                      v
                GATE: verify/check
                      |
                      v
                báo cáo & artifact
~~~

Trong Maven, Failsafe mặc định lấy integration test theo **pattern tên class** trong cùng nguồn test chuẩn. Trong Gradle JVM Test Suite, ta tạo **source set riêng** cho integration tests; điều này cho phép tách cả dependency và resource của test.

**Không nhầm:** Tách *thực thi test* không đồng nghĩa tự động tạo môi trường database/container. Nếu integration test cần PostgreSQL thật, Kafka hoặc Redis, phải cấu hình lifecycle khởi tạo/dọn dẹp riêng và cấp đủ quyền CI.

## 4. Maven: Surefire dành cho unit test, Failsafe dành cho integration test

### 4.1. Maven lifecycle liên quan

Maven có các pha chính:

~~~text
validate → compile → test-compile → test → package
                                  Surefire     |
                                              v
                                    pre-integration-test
                                              |
                                         integration-test
                                           Failsafe IT
                                              |
                                    post-integration-test
                                              |
                                            verify
                                        Failsafe verify
~~~

**Surefire** thường gắn với pha **test** để chạy unit test. **Failsafe** thiết kế riêng cho integration test:

- Goal **failsafe:integration-test** chạy integration test ở pha **integration-test**.
- Goal **failsafe:verify** kiểm tra kết quả ở pha **verify**.
- Kết quả IT thất bại được Failsafe giữ để **verify** báo build failure, thay vì ngừng lifecycle ngay tại integration-test. Điều này cho phép **post-integration-test** (nếu có cấu hình) dọn dẹp hạ tầng.
- Vì vậy **mvn verify** là điểm gọi thích hợp để chạy đầy đủ vòng đời IT. **Không lấy mvn integration-test làm cổng CI cuối cùng**, vì chưa chạy các pha dọn dẹp và kiểm tra Failsafe verify.

**Lưu ý:** Trong ví dụ HTTP tích hợp này, test dùng **@SpringBootTest(RANDOM_PORT)** tự khởi động/tắt embedded server cùng Spring test context, nên không phải cấu hình một server bên ngoài ở pre/post integration-test. Nếu project cần dịch vụ ngoại vi, mới thêm lifecycle setup/cleanup phù hợp.

### 4.2. Quy ước tên test mặc định

Surefire mặc định chọn các class có tên:

~~~text
Test*.java
*Test.java
*Tests.java
*TestCase.java
~~~

Failsafe mặc định chọn:

~~~text
IT*.java
*IT.java
*ITCase.java
~~~

Các mẫu trên có thể thay đổi bằng **includes/excludes** trong từng plugin.

Ví dụ:

| Lớp test | Surefire mặc định | Failsafe mặc định |
| --- | --- | --- |
| GreetingServiceTest | Có | Không |
| GreetingServiceTests | Có | Không |
| GreetingHttpIT | Không | Có |
| ITDatabaseRepository | Không | Có |
| PaymentITCase | Không | Có |

Nếu đặt tên **GreetingIntegrationTest**, nó kết thúc bằng **Test**, nên Surefire có thể chạy nó như unit test. Muốn giữ quy ước Failsafe mặc định, đặt tên **GreetingHttpIT** như ví dụ. Điều chỉnh include/exclude khi dự án có naming policy riêng.

### 4.3. Khác biệt quan trọng giữa Maven và Gradle

**Maven mặc định không tạo source set Java độc lập cho Failsafe.** Cả GreetingServiceTest và GreetingHttpIT đều nằm trong **src/test/java**, resource test trong **src/test/resources** và compile chung ở **test-compile**. Việc tách ở đây chủ yếu là **plugin thực thi, pattern tên và thời điểm chạy**. Nếu muốn thư mục IT/dependency tách hẳn, phải cấu hình bổ sung qua plugin hoặc module khác.

**Gradle JVM Test Suite** tạo suite riêng có source/resources/dependencies riêng và một Test task riêng. Đây là ranh giới mạnh hơn ở cấp build.

## 5. Bài thực hành thống nhất: HTTP Greeting trong Spring Boot

Ta viết một ứng dụng Spring Boot nhỏ để dùng **cùng một ý tưởng kiểm thử** trong Maven và Gradle. Mã **main** giống nhau cho cả hai; khác biệt nằm ở vị trí integration test và cấu hình build.

### 5.1. Cây thư mục theo từng công cụ

**Maven:**

~~~text
greeting-checks/
├── pom.xml
└── src/
    ├── main/java/com/example/greeting/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/
        ├── java/com/example/greeting/
        │   ├── GreetingServiceTest.java
        │   └── GreetingHttpIT.java
        └── resources/application-it.properties
~~~

**Gradle:**

~~~text
greeting-checks/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/greeting/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    ├── test/java/com/example/greeting/
    │   └── GreetingServiceTest.java
    └── integrationTest/
        ├── java/com/example/greeting/GreetingHttpIT.java
        └── resources/application-it.properties
~~~

**Chỉ chọn một bộ file build** phù hợp với Maven hoặc Gradle. Các file Java main và nội dung hai class test giống nhau, nhưng GreetingHttpIT được đặt **src/test/java** khi dùng Maven, **src/integrationTest/java** khi dùng Gradle. Điều đó quyết định công cụ nào phát hiện/chạy test.

### 5.2. File GreetingApplication.java

**src/main/java/com/example/greeting/GreetingApplication.java**:

~~~java
package com.example.greeting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {
    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
~~~

Đây là class **entry point** hoàn chỉnh. Spring Boot quét các class dưới package **com.example.greeting**, bao gồm service và controller bên dưới.

### 5.3. File GreetingService.java

**src/main/java/com/example/greeting/GreetingService.java**:

~~~java
package com.example.greeting;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Dùng **String.strip()** của Java 11+, hợp lệ với JDK 17. Unit test có thể tạo class bằng **new GreetingService()** mà không cần Spring context; khi chạy ứng dụng, **@Service** giúp Spring quản lý bean này.

### 5.4. File GreetingController.java

**src/main/java/com/example/greeting/GreetingController.java**:

~~~java
package com.example.greeting;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam(defaultValue = "World") String name) {
        return service.greet(name);
    }
}
~~~

Controller nhận GreetingService qua constructor injection. Với GET **/greet?name=Ada**, body dự kiến là **Hello, Ada!**. Cả hai file Java đều có package khai báo trùng đường dẫn thư mục.

### 5.5. Unit test không cần Spring context

**src/test/java/com/example/greeting/GreetingServiceTest.java**:

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void trimsWhitespaceAndFormatsGreeting() {
        assertEquals("Hello, Ada!", service.greet("  Ada  "));
    }
}
~~~

JUnit Jupiter chạy test thuần Java. **Không có @SpringBootTest, HTTP client, server hay database**. Test này lý tưởng cho vòng phản hồi nhanh mỗi lần sửa logic greet().

### 5.6. Integration test khởi động HTTP server thật

**Maven:** file **src/test/java/com/example/greeting/GreetingHttpIT.java**.

**Gradle:** cùng nội dung file nhưng đặt tại **src/integrationTest/java/com/example/greeting/GreetingHttpIT.java**.

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("it")
class GreetingHttpIT {

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private Environment environment;

    @Test
    void servesHttpRequestAndUsesItProfile() {
        ResponseEntity<String> response =
                client.getForEntity("/greet?name=Ada", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada!", response.getBody());
        assertEquals("enabled",
                environment.getProperty("demo.integration.mode"));
    }
}
~~~

Các annotation có ý nghĩa:

- **@SpringBootTest(webEnvironment = RANDOM_PORT)** khởi động **web application context** với embedded HTTP server trên cổng còn trống do hệ điều hành chọn. Không hard-code cổng 8080 để tránh đụng môi trường CI.
- **TestRestTemplate** do Spring Boot test hỗ trợ và được cấu hình tương ứng với server random port; dùng URL tương đối **/greet?name=Ada**.
- **@ActiveProfiles("it")** kích hoạt profile **it** trong Spring test context.
- **Environment** giúp xác minh resource của suite/IT đã được nạp đúng.
- **assertEquals** kiểm tra HTTP 200, response body và property; nếu controller/service/route sai, integration test sẽ thất bại.

Không cần gọi **java -jar** hoặc chạy **bootRun** trước để integration test hoạt động: **@SpringBootTest(RANDOM_PORT)** đã tự start server trong JVM test. Đây là integration test thật ở mức HTTP, nhưng **không** kiểm chứng JAR đã được đóng gói/deploy trên production.

### 5.7. Resource riêng cho integration test

Tạo file **application-it.properties** chứa:

~~~properties
demo.integration.mode=enabled
spring.main.banner-mode=off
~~~

- **Maven:** đặt ở **src/test/resources/application-it.properties** (test resources chung của Maven).
- **Gradle:** đặt ở **src/integrationTest/resources/application-it.properties** (resources riêng của integrationTest suite).

**@ActiveProfiles("it")** sẽ giúp Spring Boot tìm cấu hình profile này trên test runtime classpath. Unit test không cần active profile và không phụ thuộc property đó. Đừng đặt một file fixture chỉ dành IT trong **src/main/resources** khi không muốn đóng gói vào ứng dụng.

**Lưu ý về chữ “tách”:** Maven dùng cùng thư mục test resources mặc định cho cả Surefire/Failsafe; nếu yêu cầu cô lập resource hoàn toàn, phải cấu hình nguồn test phụ hoặc module riêng. Gradle suite có test resource source set riêng, nên mô hình cô lập rõ hơn.

## 6. Maven: pom.xml hoàn chỉnh với Surefire và Failsafe

Tạo **pom.xml** ở thư mục gốc cho phương án Maven:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>greeting-checks</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>greeting-checks</name>

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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM đầy đủ cho Java 17/Spring Boot 3.3.5** khi dùng Maven. Parent Spring Boot quản lý version của các starter và các thiết lập plugin liên quan. Khai báo Surefire và Failsafe cùng phiên bản cụ thể nhằm tránh lệch provider/JUnit Platform giữa hai nhóm.

Với các pattern tên mặc định:

- Surefire chạy **GreetingServiceTest** trong pha **test**.
- Failsafe chạy **GreetingHttpIT** trong pha **integration-test**, rồi **verify** kiểm tra kết quả.
- Starter test là dependency **scope test**, nên các lớp JUnit và TestRestTemplate có mặt trên test classpath mà không thành dependency production của JAR.

### 6.1. Chạy unit test nhanh

Từ project root có Maven Wrapper:

~~~bash
./mvnw clean test
~~~

Maven chạy qua **compile → test-compile → test**. Surefire thấy **GreetingServiceTest**, còn **GreetingHttpIT** không khớp các pattern mặc định của Surefire. Vì vậy không có embedded server từ test IT.

Nếu máy chưa có wrapper, có thể dùng **mvn clean test** với Maven tương thích đã được cài. Trên Windows dùng **mvnw.cmd**.

**Kỳ vọng:** một test unit chạy và thành công, không tự chạy GreetingHttpIT. Kết quả plugin và số lượng test còn tùy tập test khác nếu người học thêm file.

### 6.2. Chạy toàn bộ kiểm tra bằng verify

~~~bash
./mvnw clean verify
~~~

Dòng này chạy các pha trước **verify**, bao gồm test của Surefire, package/repackage của Spring Boot, integration-test của Failsafe, cleanup trong post-integration-test nếu có, và verification của Failsafe. Đối với ví dụ, **GreetingHttpIT** khởi động Spring HTTP server cổng ngẫu nhiên và kiểm tra endpoint.

**Quan trọng:** Không thay **verify** bằng **integration-test** khi muốn CI phát hiện build failure từ IT. Failsafe thiết kế để báo lỗi cuối vòng đời ở verify và cho phép chạy pha cleanup.

### 6.3. Chạy package có chạy IT không?

~~~bash
./mvnw clean package
~~~

Theo Maven lifecycle, **package nằm trước integration-test**, nên lệnh này chạy unit test và build artifact nhưng **không đi qua Failsafe integration-test/verify**. Đây là khác biệt cốt lõi với **verify**. Nếu pipeline chỉ gọi **mvn package**, integration test có thể không được chạy dù POM đã khai báo Failsafe.

### 6.4. Đọc báo cáo Maven

Thông thường:

~~~text
target/surefire-reports/TEST-com.example.greeting.GreetingServiceTest.xml
target/failsafe-reports/TEST-com.example.greeting.GreetingHttpIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Tên cụ thể của report phụ thuộc package/class, phiên bản plugin và config. Trong CI, có thể thu thập glob:

~~~text
target/surefire-reports/TEST-*.xml
target/failsafe-reports/TEST-*.xml
~~~

Nếu Failsafe báo không tìm thấy test, kiểm tra tên class kết thúc **IT**, đường dẫn **src/test/java**, cấu hình plugin/execution goals và compile test có thành công không. Không nên tùy tiện thêm tùy chọn bỏ qua failure để “làm xanh” pipeline.

## 7. Gradle: build.gradle với JVM Test Suite

Gradle sử dụng **source set và test task riêng** thay vì phát hiện IT chỉ qua tên class.

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'greeting-checks'
~~~

### 7.2. build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

testing {
    suites {
        test {
            useJUnitJupiter()
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter()

            dependencies {
                implementation project()
                implementation 'org.springframework.boot:spring-boot-starter-test'
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named('test'))
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn(testing.suites.integrationTest)
}
~~~

**Đây là build.gradle Groovy DSL hoàn chỉnh** cho phương án Gradle. Sử dụng Gradle **8.5** hoặc bản khác có JVM Test Suite DSL tương thích; Gradle Java plugin đã tích hợp chức năng JVM Test Suite cần thiết nên không nhất thiết khai báo riêng **id 'jvm-test-suite'**.

Giải thích chính xác:

1. **test { useJUnitJupiter() }** cấu hình test suite mặc định dùng JUnit Jupiter. Các test của suite này nằm ở **src/test/java**; task chạy tên **test**.
2. **integrationTest(JvmTestSuite)** đăng ký suite mới. Theo convention, source code đặt ở **src/integrationTest/java** và resource ở **src/integrationTest/resources**. Gradle tạo task **integrationTest**, compiler task và classpath riêng cho suite.
3. **implementation project()** bên trong suite là bắt buộc cho việc suite tự tham chiếu **mã production của project**. Các suite tùy chỉnh không được thừa hưởng quyền truy cập production source giống suite test mặc định.
4. **implementation 'org.springframework.boot:spring-boot-starter-test'** trong suite cho phép dùng **@SpringBootTest, TestRestTemplate, JUnit/AssertJ** khi chạy IT. Đây là dependency thuộc **integrationTestImplementation**, không phải dependency production.
5. **shouldRunAfter(tasks.named('test'))** ưu tiên integrationTest chạy sau unit test khi cả hai có trong task graph; **không tự tạo quan hệ phụ thuộc**.
6. **tasks.named('check') { dependsOn(...) }** mới là dòng khiến **./gradlew check** chạy integrationTest cùng các bước verification khác. Nếu bỏ dòng này, **check** theo convention không tự chạy suite tùy chỉnh.
7. Plugin **io.spring.dependency-management** cùng Spring Boot plugin quản lý version dependency starter theo BOM của Boot. Một môi trường Gradle/Boot nâng cấp có thể cần kiểm tra version JUnit platform launcher; không nên phụ thuộc vào internal classpath rò rỉ.

**JVM Test Suite là API ở trạng thái incubating trong các Gradle version được dẫn ở đây**, có thể thay đổi theo phiên bản. Pin Gradle Wrapper và kiểm tra release notes khi nâng cấp.

### 7.3. Các thư mục và classpath Gradle tạo

~~~text
src/main/java                          → compileJava → main classes
src/test/java                          → compileTestJava → test classes
src/integrationTest/java               → compileIntegrationTestJava → IT classes
src/integrationTest/resources          → processIntegrationTestResources

testImplementation / testRuntimeClasspath
integrationTestImplementation / integrationTestRuntimeClasspath

test task                              → chỉ default test suite
integrationTest task                   → chỉ integrationTest suite
check task                             → test + integrationTest (vì dependsOn)
~~~

**Không copy GreetingHttpIT vào src/test/java trong phương án Gradle** nếu muốn test nhanh chỉ chạy unit test. Gradle test task không tự phân biệt “IT”/“Test” theo tên như Maven Failsafe, mà lấy những class thuộc **source set** được cấu hình. Đặt sai thư mục có thể làm test chậm chạy trong pipeline unit.

### 7.4. Những lệnh Gradle cần nhớ

~~~bash
./gradlew clean test
./gradlew integrationTest
./gradlew check
./gradlew build
~~~

- **clean test**: chạy suite mặc định, trong ví dụ chỉ có GreetingServiceTest. Không tự chạy suite integrationTest chỉ vì nó tồn tại.
- **integrationTest**: chạy suite tích hợp, trong ví dụ GreetingHttpIT, cùng các task compile/resources mà suite cần.
- **check**: chạy cả unit và IT vì đã thêm **dependsOn(testing.suites.integrationTest)**.
- **build**: phụ thuộc vòng đời **check** và **assemble**; theo cấu hình trên có cả hai nhóm test và build artifact.

Gradle Wrapper trên Windows dùng **gradlew.bat**. Những dòng log như **UP-TO-DATE** hoặc **FROM-CACHE** không có nghĩa Gradle luôn chạy lại một test không thay đổi; dùng **--rerun-tasks** khi thực sự muốn cưỡng bức chạy lại trong chẩn đoán.

### 7.5. Báo cáo Gradle ở đâu?

Sau khi chạy test suite, Gradle thường có:

~~~text
build/test-results/test/TEST-*.xml
build/test-results/integrationTest/TEST-*.xml

build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html
~~~

Vì hai task khác nhau, CI có thể upload báo cáo JUnit XML theo từng đường dẫn. Khi test lỗi, xem **task name** trong output và HTML/XML report để biết lỗi đến từ unit test hay integration test.

### 7.6. Khi Gradle báo thiếu class TestRestTemplate hay JUnit

Kiểm tra **dependencies** nằm **bên trong suite integrationTest**, không chỉ top-level testImplementation. Suite integrationTest không tự kế thừa dependency testImplementation của suite mặc định. Xem resolved classpath:

~~~bash
./gradlew dependencies --configuration integrationTestCompileClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath
~~~

Đồng thời xác nhận **implementation project()** có mặt, vì không có nó integration test có thể không compile các class của app.

## 8. So sánh Maven Failsafe và Gradle JVM Test Suite

| Tiêu chí | Maven Surefire + Failsafe | Gradle JVM Test Suite |
| --- | --- | --- |
| Cách phân nhóm mặc định | **Tên class**: *Test vs *IT | **Source set/suite**: test vs integrationTest |
| Source của integration test | **src/test/java** theo cấu hình chuẩn | **src/integrationTest/java** |
| Test resource | **src/test/resources** dùng chung | **src/integrationTest/resources** độc lập theo suite |
| Library cho integration tests | Thường dùng dependency scope **test** chung | Khai báo trong **integrationTest.dependencies** |
| Unit task/pha | **test**, Surefire | **test** task |
| IT task/pha | **integration-test + verify**, Failsafe | **integrationTest** task |
| CI gate cả hai | **mvn verify** | **./gradlew check** nếu đã wire; hoặc **build** |
| Báo cáo | surefire-reports, failsafe-reports | test-results/test và test-results/integrationTest |
| Setup/teardown ngoài test | Maven pre/post integration-test phases có thể dùng | Gradle cần task/service phù hợp và dependency/finalizer |
| Điểm lưu ý | Đừng dừng ở **mvn integration-test** | Đừng quên **check.dependsOn(integrationTest)** |

**Không đánh đồng** tên integrationTest của Gradle với pha integration-test của Maven. Một bên là **task Gradle** được tạo cho suite, bên kia là **pha Maven lifecycle** với Failsafe goals.

## 9. Pipeline CI: nhanh ở pull request, đầy đủ trước phát hành

### 9.1. Đề xuất hai mức kiểm tra

**Mức nhanh (trên mỗi chỉnh sửa hoặc push)** ưu tiên unit test:

~~~bash
# Maven
./mvnw -B clean test

# Gradle
./gradlew --no-daemon clean test
~~~

**Mức đầy đủ (pull request, merge gate hoặc trước phát hành)** chạy cả unit + integration test:

~~~bash
# Maven
./mvnw -B clean verify

# Gradle
./gradlew --no-daemon clean check
~~~

Đây là **hai phương án thay thế** cho từng công cụ, không phải yêu cầu chạy cả Maven lẫn Gradle trong một repository. Theo chính sách chất lượng dự án, integration tests có thể phải chạy trên **mọi pull request**, không chỉ trước release. Nếu test tích hợp chậm, cân nhắc parallel jobs, cache dependency và môi trường test dùng một lần thay vì âm thầm bỏ IT.

**Đối với Gradle** nếu cần đồng thời đóng gói, gọi **./gradlew clean build**; vì đã wire integrationTest vào check, build chạy cả hai bộ test theo lifecycle.

### 9.2. Dependency môi trường và Testcontainers

Khi integration test cần PostgreSQL/Kafka/Redis, không để kết quả phụ thuộc dữ liệu cá nhân trong máy dev:

- Dùng database/container dùng một lần hoặc schema riêng cho mỗi job.
- Testcontainers có thể khởi tạo container từ JUnit/Spring test setup, nhưng CI phải có container runtime/permissions thích hợp.
- Chỉ dùng cổng ngẫu nhiên khi phù hợp; tránh dùng hard-coded port cố định dễ xung đột giữa các CI job.
- Thiết lập timeout và cleanup rõ ràng; không để test thất bại rồi giữ lại container/service chạy ngầm.
- Giữ mật khẩu/token CI trong secret store; không commit credential thật vào **application-it.properties**.
- Nếu test cần mạng hoặc image chưa được cache, offline run có thể thất bại; ghi rõ điều kiện môi trường.

Trong ví dụ Hello HTTP của bài, không có DB/broker nên **không yêu cầu Docker**. Đừng tự thêm Testcontainers vào POM/Gradle khi bài thực hành chưa sử dụng nó.

### 9.3. Môi trường test và production khác nhau

**@SpringBootTest(RANDOM_PORT)** chạy app với classpath của test và một embedded server trong JVM kiểm thử. Nó **không** hoàn toàn tương đương việc triển khai executable JAR lên Kubernetes, Docker hoặc server thật. Nếu yêu cầu kiểm thử packaging/deployment, bổ sung smoke test của artifact đã build (thường là một stage CI khác).

### 9.4. Bảo toàn báo cáo khi IT lỗi

Với Maven, cần để **failsafe:verify** chạy để phát hiện failure theo đúng lifecycle, đồng thời lưu **target/failsafe-reports**. Với Gradle, đừng cấu hình **ignoreFailures = true** cho IT ở gate bắt buộc. Hệ thống CI nên luôn upload test report sau job, kể cả khi build thất bại, và phải trả exit code thất bại ra trạng thái pipeline.

## 10. Các trường hợp kiểm thử tích hợp phổ biến

**10.1. HTTP controller + service:** như ví dụ này. Test chạy Spring context và HTTP server thật, xác nhận route, injection và response. Phù hợp làm bài đầu tiên.

**10.2. Repository + database:** test truy vấn/ghi data và kiểm tra transaction/schema. H2 in-memory hữu ích cho demo nhanh, nhưng nếu production dùng PostgreSQL/MySQL, khác biệt SQL/dialect có thể khiến test H2 bỏ sót lỗi. Với yêu cầu tương thích thật, dùng database engine tương ứng trong container.

**10.3. Messaging:** test publish/consume message và retry/dead-letter. Cần môi trường broker ổn định, tránh dùng queue chung giữa các job. Tách fixture và cleanup để test không làm nhiễm trạng thái nhau.

**10.4. REST client gọi dịch vụ khác:** dùng MockWebServer/WireMock để kiểm tra HTTP contract ổn định, hoặc chạy contract test với service thật ở môi trường kiểm soát. Không nên test unit vô tình gọi internet công cộng.

**10.5. Security filters:** dùng Spring test context và HTTP client để xác nhận status 401/403/200 khi có hoặc không có token phù hợp. Cần phân biệt test authentication ở mức mock với tích hợp authentication provider thật.

**10.6. Data migration:** chạy migration trên database sạch và kiểm tra schema/data quan trọng. Đây thường là integration test chậm hơn, nên thuộc suite riêng và cần hoàn nguyên dữ liệu sau test.

Trong mọi trường hợp, test phải **deterministic**, độc lập thứ tự và có thời gian thực thi có thể quản lý. Một test chỉ pass khi chạy sau test khác là tín hiệu có shared state hoặc cleanup không đúng.

## 11. Khi nào dùng JUnit tags thay vì Maven/Gradle suite riêng?

**JUnit Jupiter @Tag** giúp phân loại test theo nhãn, ví dụ:

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ExampleTaggedTest {
    @Test
    @Tag("integration")
    void tagged() {
        assertTrue(true);
    }
}
~~~

Đây là **một ví dụ Java/JUnit hoàn chỉnh**, không nằm trong các file của bài thực hành chính ở mục 5. Dùng **@Tag("integration")** không tự đổi lifecycle Maven hoặc tạo Gradle source set. Cần cấu hình include/exclude groups/tags trong Surefire, Failsafe hoặc Test task nếu dùng hướng này. Không để cùng một test bị chạy hai lần không chủ ý chỉ vì vừa match naming pattern vừa match tag.

**Khi nào đáng dùng tags?** Khi muốn phân nhóm ngay trong cùng một source set, hoặc có những chiều phân loại độc lập như **slow**, **database**, **contract**. **Khi nào nên dùng suite riêng?** Khi cần classpath, resources, task, timeout hoặc policy CI khác nhau; Gradle JVM Test Suite rất phù hợp với cách phân tách này.

Với **Maven Failsafe**, convention ***IT** đơn giản, dễ dự đoán. Với **Gradle JVM Test Suite**, không cần dựa vào hậu tố **IT** để phát hiện, nhưng nên giữ hậu tố để người đọc code dễ nhận biết mục đích.

## 12. Lỗi thường gặp và cách xử lý

**Lỗi 1 — Maven integration test chạy trong mvn test.** Class có tên **GreetingIntegrationTest** kết thúc bằng Test nên Surefire chọn. Đổi tên thành **GreetingHttpIT** hoặc cấu hình includes/excludes phù hợp; xác minh plugin report.

**Lỗi 2 — Maven verify không chạy IT.** Kiểm tra **maven-failsafe-plugin** đã khai báo trong build/plugins với goals **integration-test** và **verify**, tên test đúng ***IT**, cùng class test được compile ở src/test/java. Đặt plugin chỉ trong **pluginManagement** chưa đủ để tự chạy nếu không được khai báo/activate trong plugins.

**Lỗi 3 — CI chỉ gọi mvn package.** Package diễn ra trước pha integration-test. Đổi gate đầy đủ thành **mvn verify**; không suy ra IT được chạy từ việc JAR được tạo thành công.

**Lỗi 4 — Chỉ gọi mvn integration-test và xem build thành công là đủ.** Failsafe có thể ghi nhận test thất bại để đánh giá ở **verify**. Phải gọi **mvn verify** để chạy đến pha kiểm tra và cleanup.

**Lỗi 5 — Gradle khai báo suite nhưng ./gradlew check không chạy IT.** Các suite tùy chỉnh không tự được nối vào **check**. Thêm **dependsOn(testing.suites.integrationTest)**, rồi xác nhận task graph.

**Lỗi 6 — Gradle đặt GreetingHttpIT ở src/test/java.** Task **test** nhìn thấy nó, làm chậm vòng unit test; hoặc integrationTest task không thấy. Chuyển sang **src/integrationTest/java**, giữ unit tests trong src/test/java.

**Lỗi 7 — Gradle integrationTest compile lỗi vì không thấy main class.** Suite không tự có project production outputs; khai báo **implementation project()** trong **integrationTest.dependencies**.

**Lỗi 8 — Gradle integrationTest thiếu @SpringBootTest/TestRestTemplate.** **testImplementation** của default test suite không tự chảy sang integrationTest. Khai báo **spring-boot-starter-test** trong **integrationTest.dependencies**.

**Lỗi 9 — Tưởng shouldRunAfter làm IT thành dependency của test.** **shouldRunAfter** chỉ điều chỉnh thứ tự khi cả hai task đã trong graph. Dùng **check.dependsOn** để bảo đảm IT được chạy trong gate.

**Lỗi 10 — @SpringBootTest không gọi server thật.** Mặc định **@SpringBootTest** dùng MOCK web environment. Muốn thử HTTP thật, dùng **webEnvironment = RANDOM_PORT** và client tới server đã start.

**Lỗi 11 — Test HTTP trùng cổng 8080.** Dùng RANDOM_PORT; tránh hard-code host/port cho server embedded. Với test gọi dịch vụ ngoài, cũng nên cấp port ngẫu nhiên/isolated environment.

**Lỗi 12 — @ActiveProfiles("it") nhưng property bị thiếu.** Xem vị trí **application-it.properties** đúng source set: Maven src/test/resources; Gradle src/integrationTest/resources. Kiểm tra tên profile, file extension, classpath và overrides khác.

**Lỗi 13 — IT thất bại không làm CI đỏ.** Với Maven, thiếu failsafe:verify hoặc pipeline không gọi verify. Với Gradle, job bỏ qua integrationTest hoặc đặt **ignoreFailures**; sửa pipeline/task dependency.

**Lỗi 14 — Test muốn kết nối database nhưng CI không có database.** Phải cung cấp database/container, cấu hình URL/credentials riêng cho test, chờ readiness và cleanup. Lỗi môi trường không được chữa bằng cách skip integration tests vô điều kiện.

**Lỗi 15 — Chỉ chạy unit test rồi tuyên bố mọi tích hợp đều tốt.** Unit test không phát hiện mọi lỗi Spring wiring, servlet mapping, JSON serialization, schema migration hoặc network. Cần chạy suite IT ở gate theo mức rủi ro của dự án.

**Lỗi 16 — Tất cả test đều chạy @SpringBootTest.** Unit test không cần Spring context thì tránh boot context để feedback nhanh. Chỉ test nghiệp vụ có cơ sở tích hợp mới khởi tạo context/HTTP server.

**Lỗi 17 — Maven Failsafe và Surefire dùng provider/version không nhất quán.** Cố định version tương thích và bảo đảm JUnit Jupiter engine có trong test classpath. Spring Boot starter-test cung cấp hệ sinh thái JUnit cần thiết cho ví dụ.

**Lỗi 18 — Suite Gradle không dùng được JUnit Platform launcher trong phiên bản Gradle mới.** Đọc thông báo lỗi và tài liệu Gradle tương ứng; trong môi trường yêu cầu khai báo launcher rõ ràng, thêm dependency **org.junit.platform:junit-platform-launcher** ở runtimeOnly của suite thích hợp và chọn version được quản lý tương thích, không dựa vào dependency nội bộ rò rỉ.

**Lỗi 19 — Integration tests làm bẩn môi trường chung.** Tạo dữ liệu duy nhất cho mỗi test/job, dùng cleanup, transaction phù hợp và test resource isolation. Khi test HTTP chạy server thread khác, @Transactional ở test không tự rollback mọi transaction được server xử lý.

## 13. Checklist trước khi hoàn tất việc tách test

- [ ] Xác định ranh giới unit test và integration test theo hành vi chứ không chỉ tên.
- [ ] Viết unit test không cần Spring context nếu có thể.
- [ ] Viết IT cho ít nhất một đường đi tích hợp thật (HTTP, DB, message).
- [ ] Maven: Surefire chạy ***Test**, Failsafe chạy ***IT**, có hai goals **integration-test** và **verify**.
- [ ] Maven: CI đầy đủ dùng **mvn verify**, không dừng ở package hay integration-test.
- [ ] Gradle: khai báo **integrationTest(JvmTestSuite)**, đặt source/resource riêng.
- [ ] Gradle: suite có **implementation project()** và test framework/dependencies riêng.
- [ ] Gradle: **check.dependsOn(testing.suites.integrationTest)** nếu muốn check/build chạy IT.
- [ ] Kiểm tra **RANDOM_PORT**, profile/resource, không phụ thuộc port cố định.
- [ ] Kiểm tra riêng report của unit/IT và exit status khi có test hỏng.
- [ ] Cấp hạ tầng test cô lập và cleanup khi có DB/broker/service ngoài.
- [ ] Chạy lại hai nhóm sau khi thay đổi Spring Boot/Gradle/Maven/JUnit version.

## 14. Tài liệu chính thức

- Apache Maven — Failsafe Plugin Introduction và lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Apache Maven — Failsafe Plugin Inclusions/Exclusions: https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html
- Apache Maven — Surefire Plugin Inclusions/Exclusions: https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html
- Apache Maven — Lifecycle Phases: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle — JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

**Tóm lại:** Maven tách unit/IT bằng **Surefire, Failsafe, pattern tên test và lifecycle verify**; Gradle tách bằng **JVM Test Suite có source set, dependency, task riêng**, rồi nối **integrationTest** vào **check**. Cả hai đều cho phép chạy unit test nhanh và giữ integration test làm cổng kiểm soát bắt buộc khi phát hành.