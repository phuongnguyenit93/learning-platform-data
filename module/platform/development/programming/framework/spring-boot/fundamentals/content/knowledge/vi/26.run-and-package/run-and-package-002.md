# Biên dịch, kiểm thử và đóng gói là các giai đoạn khác nhau

Khi phát triển ứng dụng Spring Boot, bạn thường gặp các lệnh `./gradlew compileJava`, `./gradlew test`, `./gradlew bootJar`, `./gradlew build`, `mvn compile`, `mvn test` và `mvn package`. Những lệnh này có thể gọi nhau thông qua task graph hoặc build lifecycle, nhưng **biên dịch, kiểm thử và đóng gói vẫn là ba công việc khác nhau**.

- **Biên dịch (compilation)**: biến Java source thành bytecode `.class`, kiểm tra cú pháp, kiểu và các quy tắc mà Java compiler có thể phát hiện.
- **Kiểm thử (testing)**: chạy những tình huống đã được viết dưới dạng test và so sánh kết quả thực tế với kỳ vọng.
- **Đóng gói (packaging)**: tạo một artifact, ví dụ JAR/WAR, từ compiled classes, resources và các dependency cần thiết theo cấu hình build.

Một ứng dụng **compile được** vẫn có thể có lỗi logic và test fail. Một project **tạo được JAR** vẫn có thể chưa chạy test. Một executable JAR **đóng gói thành công** vẫn có thể lỗi khi khởi động vì thiếu cấu hình, database không hoạt động hoặc runtime classpath có vấn đề.

Hiểu ranh giới từng giai đoạn giúp bạn đọc log build, lựa chọn lệnh khi phát triển, tổ chức pipeline CI/CD và không nhầm “có artifact” với “đã kiểm thử đầy đủ”.

Bài học dùng các ví dụ Spring Boot 3.x, Java 17/21, Gradle và Maven. Các lệnh/build file minh họa convention phổ biến; task graph hoặc plugin executions có thể được tùy biến trong dự án thực tế.

## 1. Ba câu hỏi khác nhau của một quy trình build

Khi một đồng đội hỏi “ứng dụng đã build xong chưa?”, câu hỏi này có thể mang ba nghĩa:

1. **Mã nguồn có biên dịch được không?** Trình biên dịch có tạo bytecode mà không gặp lỗi không?
2. **Ứng dụng có đáp ứng những test đã viết không?** JUnit test, integration test hoặc kiểm thử khác có pass không?
3. **Đã có file để chạy hoặc phát hành chưa?** Công cụ đóng gói có tạo đúng executable Spring Boot JAR/WAR không?

Bảng so sánh:

| Giai đoạn | Đầu vào chủ yếu | Kết quả | Không tự bảo đảm |
| --- | --- | --- | --- |
| Biên dịch | `.java` và compile classpath | `.class`, generated sources/metadata | Logic đúng, bean wiring hợp lệ, app chạy được |
| Kiểm thử | Test source, compiled classes, test runtime | Pass/fail, test reports | Bao phủ mọi lỗi, production giống test |
| Đóng gói | Compiled main classes, resources, runtime dependencies | JAR/WAR hoặc artifact khác | Tests đã chạy, service khởi động thành công |

Có thể hình dung chuỗi công việc:

~~~mermaid
flowchart TD
    S["src/main/java"] --> C["Compile main code"]
    R["src/main/resources"] --> RES["Process resources"]
    C --> CL["Main .class files"]
    T["src/test/java"] --> TC["Compile test code"]
    CL --> TC
    TC --> TE["Run test task"]
    TR["src/test/resources"] --> TC
    CL --> PK["Package artifact"]
    RES --> PK
    D["Runtime dependencies"] --> PK
    PK --> J["Plain JAR / Boot executable JAR / WAR"]
    J --> RUN["Run packaged artifact"]
    TE -. "CI quality gate" .-> RUN
~~~

Sơ đồ phân biệt hai quan hệ. Về mặt kỹ thuật, chạy test cần compile; đóng gói cần compiled classes và resources. Nhưng **đóng gói không nhất thiết phải chạy test**. Một CI pipeline có thể yêu cầu test thành công trước khi publish; đó là một chính sách được áp dụng thêm.

## 2. Biên dịch: tạo bytecode, chưa phải chạy ứng dụng

Các source Java thường nằm ở:

~~~text
src/main/java/
└── com/example/demo/
    ├── DemoApplication.java
    ├── service/PriceService.java
    └── web/PriceController.java
~~~

Khi biên dịch, công cụ như `javac` phân tích Java source, giải quyết các kiểu tham chiếu, kiểm tra quy tắc ngôn ngữ và sinh file `.class`.

Ví dụ:

~~~java
public class PriceCalculator {
    public long discount(long price, int percent) {
        return price * (100 - percent) / 100;
    }
}
~~~

Java compiler chấp nhận method này nếu mọi tham chiếu và kiểu dữ liệu hợp lệ. Nhưng nếu `percent = 200`, method trả kết quả âm. Compile thành công không khẳng định đây là kết quả được nghiệp vụ cho phép.

Một lỗi compiler:

~~~java
public int totalPrice() {
    return "100";  // String không thể trả về như int.
}
~~~

Đây là lỗi **compile-time**. Không cần khởi động Spring context hay chạy unit test để phát hiện.

### 2.1. Compiler kiểm tra những gì?

Java compiler có thể phát hiện:

- Cú pháp Java sai, thiếu dấu hoặc khai báo không hợp lệ.
- Kiểu dữ liệu không tương thích.
- Method, constructor hoặc field không được tìm thấy trên compile classpath.
- Vi phạm access modifier.
- Checked exception chưa được xử lý theo quy tắc Java.
- Một số ràng buộc generic và interface implementation.
- Lỗi từ annotation processor được cấu hình.

Compiler **không tự kiểm tra**:

- Spring đã đăng ký đủ bean cho constructor injection hay chưa.
- `application-prod.yml` có JDBC URL hợp lệ hay không.
- Database, Redis hoặc Kafka có hoạt động không.
- API trả đúng dữ liệu cho mọi input không.
- Một transaction có rollback theo mong đợi không.
- HTTP endpoint có khởi động và nhận request được không.

Các điều đó thường xuất hiện trong test, startup hoặc hoạt động runtime.

### 2.2. Output của compilation

Trong Gradle Java project thông thường:

~~~text
build/classes/java/main/com/example/demo/service/PriceService.class
~~~

Trong Maven:

~~~text
target/classes/com/example/demo/service/PriceService.class
~~~

Đây là output biên dịch. Những file `.class` chưa tự đóng gói thành executable JAR và chưa nhất thiết có runtime dependencies ở bên cạnh.

### 2.3. Compile classpath khác runtime classpath

Compiler cần nhìn thấy các class được source code tham chiếu. Khi chạy, JVM còn cần các implementation và dependency runtime.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ý nghĩa:

| Configuration | Vai trò |
| --- | --- |
| `implementation` | Dependency của main code trong mô hình compile/runtime Gradle Java |
| `compileOnly` | Cần khi compile, không tự đưa vào runtime |
| `annotationProcessor` | Chạy processor trong compiler |
| `runtimeOnly` | Cần khi chạy, không nhất thiết khi compile |
| `testImplementation` | Dùng cho việc compile và chạy test |
| `testRuntimeOnly` | Cung cấp dependency runtime chỉ cho test |

Ví dụ driver PostgreSQL có thể chỉ cần ở runtime vì source code dùng các JDBC abstractions thay vì trực tiếp import driver implementation.

Một project compile được vẫn có thể lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError` nếu thiếu dependency cần thiết khi chạy.

### 2.4. Annotation processing vẫn thuộc compilation

Lombok, MapStruct hoặc Spring Boot configuration processor có thể tạo source/metadata trong quá trình biên dịch:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Việc processor chạy không đồng nghĩa JUnit test đã chạy. Đây là hoạt động thuộc build/compile pipeline.

## 3. Kiểm thử: chạy code và so sánh với kỳ vọng

Test không chỉ xác định Java source hợp lệ mà còn **thực thi** một hành vi.

Ví dụ một service tính phí:

~~~java
package com.example.demo.service;

public class ShippingCalculator {

    public long calculate(int distanceKm) {
        if (distanceKm <= 10) {
            return 10_000L;
        }
        return 10_000L + (distanceKm - 10) * 500L;
    }
}
~~~

Class trên compile được nhưng có thể không đáp ứng yêu cầu “khoảng cách âm phải bị từ chối”.

JUnit 5 test:

~~~java
package com.example.demo.service;

import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class ShippingCalculatorTest {

    @Test
    void rejectsNegativeDistance() {
        ShippingCalculator calculator = new ShippingCalculator();

        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.calculate(-1)
        );
    }
}
~~~

Test này thất bại với implementation hiện tại vì method trả `10_000` chứ không ném `IllegalArgumentException`.

Điểm cần nhớ:

- **Compile main code** có thể thành công.
- **Compile test code** có thể thành công.
- **Chạy test** có thể thất bại vì assertion không đúng.

Không thể thay thế bước thứ ba bằng hai bước đầu.

### 3.1. Compile test khác execute test

Test cũng là Java source cần biên dịch:

~~~text
src/test/java/com/example/demo/service/ShippingCalculatorTest.java
~~~

Một quá trình test điển hình:

~~~mermaid
flowchart TD
    A["Main source"] --> B["Compile main"]
    B --> C["Main classes"]
    T["Test source"] --> D["Compile tests"]
    C --> D
    D --> E["Test classes"]
    E --> F["JUnit Platform / test runner"]
    F --> G{"Assertions"}
    G -->|Pass| H["Test result: passed"]
    G -->|Fail / exception| I["Test result: failed"]
~~~

Với Gradle:

~~~bash
./gradlew compileTestJava
~~~

thường biên dịch test source và prerequisite tasks nhưng **không chạy assertions**.

Trong khi:

~~~bash
./gradlew test
~~~

thường biên dịch các source cần thiết và thực thi test task theo cấu hình.

Với Maven:

~~~bash
mvn test-compile
~~~

chạy các phase đến test compilation; còn:

~~~bash
mvn test
~~~

chạy test phase, thông thường qua Maven Surefire Plugin.

### 3.2. Test pass có phạm vi

Một test pass chứng minh rằng **những assertion đã chạy** thỏa mãn trong môi trường test hiện tại. Nó không bảo đảm:

- Tất cả edge cases đều được kiểm tra.
- Mọi external service ở production đang khỏe.
- Không có race condition hoặc lỗi phụ thuộc thời gian.
- Performance đạt yêu cầu khi chịu tải lớn.
- Một artifact được đóng gói từ chính revision đang test.

Nếu muốn những bảo đảm khác, cần thêm loại kiểm thử và quy trình phát hành tương ứng.

## 4. Các loại test trong Spring Boot

| Loại test | Mục tiêu | Cần Spring context? |
| --- | --- | --- |
| Unit test | Một class/function độc lập | Không bắt buộc |
| MVC slice test | Controller, mapping, serialization trong slice | Có, giới hạn phạm vi |
| JPA slice test | Repository và persistence slice | Có, giới hạn phạm vi |
| Integration test | Nhiều component làm việc cùng nhau | Có thể có |
| Contract test | Hợp đồng giữa service/provider/client | Tùy công cụ |
| End-to-end test | Luồng hoàn chỉnh qua nhiều tầng | Thường cần môi trường gần thực tế |
| Smoke test | Chức năng tối thiểu sau khi chạy/deploy | Thường chạy trên artifact đã khởi động |
| Performance/load test | Latency, throughput, tài nguyên | Chạy với tải và môi trường riêng |

### 4.1. Unit test không cần boot context

Với `ShippingCalculator`, có thể tạo class bằng `new` và kiểm tra trực tiếp. Việc khởi tạo toàn bộ Spring container chỉ để test phép tính thường làm tăng thời gian và độ phụ thuộc.

### 4.2. SpringBootTest kiểm tra wiring/runtime context

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private PriceService service;

    @Test
    void loadsService() {
        assertThat(service).isNotNull();
    }
}
~~~

Test này có thể phát hiện lỗi bean wiring hoặc property binding khi khởi động Spring context. Nhưng nó thường chạy với profile và resources của môi trường test, không tự bảo đảm production configuration đúng.

### 4.3. Slice test không thay thế full integration test

Ví dụ:

~~~java
@WebMvcTest(PriceController.class)
class PriceControllerTest {
    // Kiểm tra MVC slice, mock dependency cần thiết.
}
~~~

`@WebMvcTest` giới hạn phạm vi khởi tạo hơn `@SpringBootTest` trong các cấu hình thường gặp. Controller slice test pass không chứng minh mọi bean và integration của toàn ứng dụng đều có thể khởi động.

### 4.4. Integration test thường là một task riêng

Một số project chỉ chạy unit tests trong Gradle `test`, còn integration tests ở task `integrationTest`. Maven có thể dùng Surefire cho unit tests và Failsafe cho integration tests.

Vì vậy câu “đã chạy test” cần có ngữ cảnh: **đã chạy task/test suite nào**? Nếu `integrationTest` không được liên kết vào build quality gate, nó sẽ không tự chạy chỉ vì bạn gọi `./gradlew build`.

## 5. Đóng gói: biến output thành artifact

Package tạo file để phân phối hoặc chạy, thường là JAR/WAR.

Plain JAR chứa các class/resource:

~~~text
demo-app.jar
├── META-INF/MANIFEST.MF
├── com/example/demo/DemoApplication.class
├── com/example/demo/service/PriceService.class
└── application.yml
~~~

Một JAR có đuôi `.jar` **không tự động** là một executable Spring Boot JAR có đủ dependencies.

### 5.1. Executable Spring Boot JAR

Khi dùng Spring Boot Gradle plugin `bootJar` hoặc Spring Boot Maven Plugin `repackage` đúng cách, artifact có thể có cấu trúc:

~~~text
demo-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/...
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        ├── spring-context-....jar
        ├── spring-web-....jar
        └── ...
~~~

Các phần chính:

- `BOOT-INF/classes`: application classes và resources.
- `BOOT-INF/lib`: runtime dependency JARs.
- Spring Boot loader và manifest: khởi động ứng dụng và nạp nested dependency JARs.

Một executable Boot JAR có thể chạy:

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

Tên file phụ thuộc project version/classifier/packaging configuration.

### 5.2. Plain JAR khác executable Boot JAR

| Thuộc tính | Plain JAR | Boot executable JAR |
| --- | --- | --- |
| Main classes/resources | Có | Có, thường ở `BOOT-INF/classes` |
| Runtime dependencies | Thường không được đóng gói vào cùng archive | Thường có ở `BOOT-INF/lib` |
| Boot launcher | Không mặc định | Có theo Boot executable layout |
| Chạy `java -jar` độc lập | Không bảo đảm | Được thiết kế để chạy như vậy |
| Mục đích | Thư viện/artifact Java | Ứng dụng Spring Boot chạy độc lập |

Nếu chạy một plain JAR bằng `java -jar` và gặp `no main manifest attribute` hoặc thiếu dependency, đây không nhất thiết là lỗi compiler. Bạn có thể đã lấy nhầm artifact.

### 5.3. Package thành công chưa bảo đảm runtime startup

Executable JAR được tạo hợp lệ vẫn có thể thất bại khi:

- Database hoặc Kafka không truy cập được.
- Port đã bị một tiến trình khác sử dụng.
- Biến môi trường/secret bắt buộc bị thiếu.
- Spring property binding hoặc bean configuration lỗi.
- Runtime Java version không tương thích.
- Classpath có thư viện thiếu hoặc xung đột.
- File external hoặc certificate không tồn tại.

Để phát hiện các lỗi đó, cần chạy/smoke test artifact trong môi trường thích hợp.

## 6. Gradle: các task độc lập nhưng có dependency graph

Với project sử dụng Java plugin và Spring Boot plugin, các task phổ biến:

| Task | Ý nghĩa | Có chạy JUnit test không? | Tạo executable Boot JAR? |
| --- | --- | --- | --- |
| `compileJava` | Biên dịch main source | Không | Không |
| `processResources` | Chuẩn bị main resources | Không | Không |
| `classes` | Hoàn tất đầu ra main classes/resources | Không | Không |
| `compileTestJava` | Biên dịch test source | Không chạy assertion | Không |
| `test` | Thực thi test task | Có | Không cần |
| `jar` | Tạo plain JAR | Không bắt buộc | Không |
| `bootJar` | Tạo executable Spring Boot JAR | Không bắt buộc | Có |
| `assemble` | Các artifact assembly tasks | Thường không | Thường có khi bootJar được liên kết |
| `check` | Verification tasks | Thường có `test` | Không bắt buộc |
| `build` | Assembly + verification | Thường có `test` | Thường có |
| `bootRun` | Chạy app từ runtime classpath | Không mặc định | Không |
| `clean` | Xóa outputs build | Không | Không |

Các câu “thường” quan trọng vì build script có thể disable tasks, thêm integration test hoặc thay đổi dependencies.

### 6.1. Biên dịch main code

~~~bash
./gradlew compileJava
~~~

Output main Java thường nằm tại:

~~~text
build/classes/java/main/
~~~

Lệnh này không cần tạo một executable JAR. Nó cũng không khởi động Spring container.

### 6.2. Biên dịch test và chạy test

~~~bash
./gradlew compileTestJava
./gradlew test
~~~

`test` thường kéo prerequisite tasks như compile main/test và process resources. Bạn không nhất thiết phải gọi cả hai lệnh trong vòng lặp hằng ngày; ví dụ trình bày chúng riêng để làm rõ chức năng.

### 6.3. Tạo executable JAR

~~~bash
./gradlew bootJar
~~~

`bootJar` cần compiled main classes/resources và runtime dependencies. Trong cấu hình thông thường, **task này không phụ thuộc vào `test`**, nên bạn có thể tạo JAR khi test chưa chạy.

Chỉ gọi `bootJar` có nghĩa bạn yêu cầu packaging, không phải đầy đủ verification.

### 6.4. Gradle build có những việc gì?

~~~bash
./gradlew build
~~~

Với Java/Spring Boot project thông thường, `build` phụ thuộc `assemble` và `check`:

~~~mermaid
flowchart TD
    BUILD["build"] --> ASSEMBLE["assemble"]
    BUILD --> CHECK["check"]
    ASSEMBLE --> JAR["jar"]
    ASSEMBLE --> BOOTJAR["bootJar, nếu có"]
    CHECK --> TEST["test"]
    JAR --> CLASSES["classes"]
    BOOTJAR --> CLASSES
    TEST --> TESTCLASSES["testClasses"]
    TESTCLASSES --> CLASSES
~~~

Vì vậy `build` thường tạo artifact **và** chạy test được liên kết vào `check`. Nhưng custom integration tests, security scans hoặc E2E tests chỉ chạy nếu bạn cấu hình chúng trong task graph/pipeline.

### 6.5. assemble khác check

~~~bash
./gradlew assemble
~~~

thường tạo artifacts mà không cần chạy test.

~~~bash
./gradlew check
~~~

thực hiện verification tasks, thường bao gồm `test`, không nhất thiết đóng gói.

Hai nhiệm vụ có thể xuất hiện ở các job CI khác nhau: một job tạo artifact, một job kiểm tra chất lượng; publish chỉ diễn ra khi cả hai thành công.

## 7. Ví dụ Gradle build.gradle cho Spring Boot

Ví dụ Groovy DSL dùng Spring Boot 3.3.x và Java 21:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phần:

- `java` tạo các task compile, test, jar và lifecycle tasks cơ bản.
- Spring Boot plugin thêm `bootJar` và `bootRun`.
- Dependency management/BOM thống nhất versions thư viện Spring Boot.
- Toolchain chọn JDK cho compile.
- `spring-boot-starter-web` đưa web stack vào runtime.
- `spring-boot-starter-test` cung cấp JUnit và test support.
- `useJUnitPlatform()` cho phép Gradle test task chạy test theo JUnit Platform.

Version chỉ là ví dụ cho dòng Spring Boot 3.3; trong dự án thật cần dùng phiên bản đã được kiểm soát bởi repository.

### 7.1. Nếu có hai file JAR

Với Boot Gradle plugin và Java plugin, project thường có thể tạo:

~~~text
build/libs/
├── demo-app-1.0.0.jar
└── demo-app-1.0.0-plain.jar
~~~

File không có classifier thường là executable Boot JAR từ `bootJar`; file `-plain.jar` thường do task `jar` tạo. Cấu hình project có thể thay tên hoặc disable một trong hai.

Không dùng wildcard mù quáng để chọn artifact deploy: nếu lấy nhầm `-plain.jar`, ứng dụng có thể không chạy `java -jar` như mong đợi.

### 7.2. Library module và application module

Một multi-module project có thể gồm:

~~~text
project/
├── common-model/
├── business-core/
└── api-app/
~~~

`common-model` và `business-core` thường chỉ cần plain library JAR. `api-app` mới cần executable Boot JAR.

Ví dụ trong `api-app/build.gradle`:

~~~groovy
dependencies {
    implementation project(':common-model')
    implementation project(':business-core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gọi:

~~~bash
./gradlew :api-app:bootJar
~~~

có thể compile các dependency modules cần thiết, nhưng **không tự chứng minh unit tests của tất cả modules đã chạy**. Một release pipeline cần verification gate bao phủ các module liên quan.

## 8. Maven: chạy theo lifecycle phases

Maven xây dựng một default lifecycle có nhiều phase. Các mốc thường gặp:

~~~mermaid
flowchart LR
    A["validate"] --> B["process-resources"]
    B --> C["compile"]
    C --> D["test-compile"]
    D --> E["test"]
    E --> F["package"]
    F --> G["integration-test"]
    G --> H["verify"]
    H --> I["install"]
    I --> J["deploy"]
~~~

Đây là sơ đồ rút gọn, không phải toàn bộ các phase trung gian. Maven chỉ làm những việc tương ứng với plugin goals đã được binding vào các phase.

Khác Gradle `bootJar` là một task độc lập, `mvn package` là lời gọi **lifecycle phase**. Maven sẽ chạy những phase cần thiết trước `package`.

### 8.1. mvn compile

~~~bash
mvn compile
~~~

Thường xử lý main resources rồi biên dịch main source. Output thường ở `target/classes`.

### 8.2. mvn test-compile

~~~bash
mvn test-compile
~~~

Chạy các phase tới test compilation, không tự execute test phase.

### 8.3. mvn test

~~~bash
mvn test
~~~

Thường compile main code, compile test code, rồi chạy tests qua Surefire Plugin.

### 8.4. mvn package

~~~bash
mvn package
~~~

Mặc định thực thi các phase tới package, **bao gồm `test`**. Nhưng tests có thể bị skip hoặc plugin bindings bị tùy biến.

Với Spring Boot app sử dụng `jar` packaging, Maven Jar Plugin có thể tạo JAR. Để biến thành executable Spring Boot JAR, cần Spring Boot Maven Plugin `repackage` được cấu hình thích hợp.

### 8.5. mvn verify

~~~bash
mvn verify
~~~

Đi qua các phase sau package, thường là nơi dự án liên kết integration tests và verification plugins. Chẳng hạn Maven Failsafe Plugin có thể chạy integration test trong `integration-test` rồi kiểm tra kết quả ở `verify`.

Tuy nhiên, nếu project không cấu hình integration tests, `verify` không tự sinh ra bộ test tích hợp.

### 8.6. install và deploy không phải triển khai lên server

`mvn install` đưa artifact vào local Maven repository theo convention. `mvn deploy` có thể publish artifact vào remote artifact repository theo cấu hình.

Chúng **không đồng nghĩa** tự động triển khai Spring Boot app vào Kubernetes, VM hoặc service runtime. Deploy application là một bước riêng trong CI/CD.

## 9. Ví dụ pom.xml Spring Boot

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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

Với Spring Boot starter parent, khai báo Spring Boot Maven Plugin theo convention thường kích hoạt cấu hình repackage thích hợp. Với custom Maven parent hoặc chỉ import dependency BOM, cần kiểm tra plugin version và goal executions; không phải mọi `mvn package` đều tự tạo executable Boot JAR.

### 9.1. So sánh lệnh Gradle/Maven

| Mong muốn | Gradle phổ biến | Maven phổ biến |
| --- | --- | --- |
| Compile main | `./gradlew compileJava` | `mvn compile` |
| Compile test | `./gradlew compileTestJava` | `mvn test-compile` |
| Run unit tests | `./gradlew test` | `mvn test` |
| Package Boot app | `./gradlew bootJar` | `mvn package` với repackage configured |
| Verification + assemble | `./gradlew build` | `mvn package` / `mvn verify` theo quality gates |
| Chạy app từ build output | `./gradlew bootRun` | `mvn spring-boot:run` |
| Xóa output | `./gradlew clean` | `mvn clean` |

Các lệnh có mục tiêu giống nhau không phải lúc nào gọi cùng số giai đoạn. Maven `package` thường chạy test trước; Gradle `bootJar` không mặc định yêu cầu test.

## 10. Không nhầm chạy từ source với chạy packaged artifact

Spring Boot hỗ trợ:

~~~bash
./gradlew bootRun
~~~

và:

~~~bash
mvn spring-boot:run
~~~

Hai cách này thường chạy ứng dụng từ compiled classes/resources cộng runtime classpath của project. Không nhất thiết tạo executable JAR trước.

Chạy artifact:

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

sử dụng JAR đã được đóng gói, manifest, Boot loader và nested libraries.

### 10.1. Điểm khác biệt quan trọng

| Đặc điểm | bootRun/spring-boot:run | java -jar |
| --- | --- | --- |
| Nguồn classes | Output của project | Classes trong artifact |
| Runtime dependencies | Runtime classpath do build tool cung cấp | Dependencies packaged trong executable archive |
| Cần executable Boot JAR | Không | Có |
| Tài nguyên classpath | Thường là thư mục output | Có thể là entry trong JAR |
| Kiểm chứng đúng artifact deploy | Không nhất thiết | Có, nếu chạy đúng file được deploy |

Ví dụ code:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

File file = resource.getFile();
~~~

có thể chạy được khi resource nằm ở `build/resources/main`, nhưng thất bại khi packaged JAR chứa `BOOT-INF/classes/data/catalog.json`. Một cách ít phụ thuộc layout hơn:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Parse nội dung.
}
~~~

Do đó, `bootRun` thành công không thay thế việc kiểm tra artifact chạy bằng `java -jar`.

## 11. Các output directory phổ biến

| Nội dung | Gradle thường dùng | Maven thường dùng |
| --- | --- | --- |
| Main class files | `build/classes/java/main` | `target/classes` |
| Main resources | `build/resources/main` | `target/classes` |
| Test class files | `build/classes/java/test` | `target/test-classes` |
| Test results | `build/test-results/test` | `target/surefire-reports` |
| HTML test report | `build/reports/tests/test` | Tùy reporting plugin |
| Package JAR | `build/libs` | `target` |

Không nên hard-code những thư mục trên vào runtime logic. Chúng là convention của build tool và có thể bị tùy biến.

Đặc biệt, `src/main/resources` là **thư mục source**, không phải vị trí mà ứng dụng deployed luôn truy cập được. File đóng gói vào classpath cần đọc qua resource abstraction.

## 12. Kiểm tra executable JAR sau khi đóng gói

Cách kiểm tra cơ bản:

### 12.1. Xác định đúng file

Ví dụ:

~~~text
build/libs/demo-app-1.0.0.jar
~~~

Nếu có cả `-plain.jar` và executable JAR, cần phân biệt rõ artifact nào được dùng để phát hành.

### 12.2. Kiểm tra nội dung

JDK cung cấp:

~~~bash
jar tf build/libs/demo-app-1.0.0.jar
~~~

Trong Boot JAR thường có:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
~~~

### 12.3. Kiểm tra manifest

Ví dụ manifest của Spring Boot 3.x có thể chứa:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
Spring-Boot-Version: 3.3.5
~~~

Nội dung thực tế tùy Boot version và plugin settings. `Main-Class` thường là launcher của Spring Boot; `Start-Class` là application entry point.

### 12.4. Smoke test artifact

Một smoke test tối thiểu sau package:

1. Chạy executable JAR trong môi trường thử nghiệm.
2. Truyền profile và external configuration phù hợp.
3. Đợi startup hoàn thành với timeout được xác định.
4. Gọi health endpoint hoặc một API kiểm tra đơn giản.
5. Quan sát exit code/log nếu startup thất bại.
6. Dừng process theo đường shutdown bình thường.

Ví dụ:

~~~http
GET /actuator/health
~~~

Response có thể là:

~~~json
{"status":"UP"}
~~~

Nếu có Spring Boot Actuator và endpoint được cấu hình, `UP` chỉ cho biết health checks được cấu hình đang báo tốt; nó không bảo đảm mọi luồng nghiệp vụ đã pass.

## 13. Vì sao một task có thể kéo nhiều task khác chạy theo?

Gradle dựa vào **task dependency graph**. Ví dụ:

~~~bash
./gradlew test
~~~

không chỉ thực thi một method JUnit ngay lập tức; Gradle cần compiled main/test classes và test resources, nên chạy các prerequisite tasks thích hợp.

Tương tự:

~~~bash
./gradlew bootJar
~~~

cần main classes và dependencies để đóng gói.

Nhưng **task dependencies không đồng nghĩa mọi verification đều tự chạy**. Nếu `bootJar` không phụ thuộc `test`, nó có thể hoàn thành mà không cần JUnit assertions.

### 13.1. UP-TO-DATE và FROM-CACHE

Gradle có thể hiển thị:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :test UP-TO-DATE
> Task :bootJar
~~~

Đây chỉ là log minh họa.

`UP-TO-DATE` cho biết Gradle tin rằng output hiện tại phản ánh input theo task up-to-date rules. `FROM-CACHE` có thể xuất hiện khi lấy output từ build cache. Cả hai khác với “task vừa chạy thực sự mọi test từ đầu”.

Khi giải thích kết quả CI, hãy biết task nào thực thi, task nào được skip và liệu việc dùng cache có nằm trong chính sách build.

### 13.2. clean không bắt buộc mọi lúc

~~~bash
./gradlew clean build
~~~

xóa output rồi tạo lại. Hữu ích khi muốn kiểm tra một clean build hoặc xử lý output cũ, nhưng sẽ giảm lợi ích incremental build. Trong phát triển hằng ngày, có thể chỉ cần chạy task phù hợp.

## 14. Bỏ qua test: tạo artifact không đồng nghĩa test pass

Một số lệnh cho phép đóng gói khi chưa chạy test.

### 14.1. Gradle -x test

~~~bash
./gradlew build -x test
~~~

`-x test` loại task `test` khỏi task graph được yêu cầu. Lệnh vẫn có thể chạy compile và package, cùng các task khác nếu được cấu hình.

Nếu dự án có task `integrationTest` riêng, `-x test` không tự loại mọi task test khác.

### 14.2. Maven -DskipTests

~~~bash
mvn package -DskipTests
~~~

Thông thường bỏ qua việc **thực thi test**, nhưng test source vẫn có thể được biên dịch.

### 14.3. Maven -Dmaven.test.skip=true

~~~bash
mvn package -Dmaven.test.skip=true
~~~

Trong mô hình Maven thông dụng, property này được Compiler/Surefire/Failsafe sử dụng để bỏ qua cả test compilation và execution.

### 14.4. Hệ quả

| Trường hợp | Kết quả |
| --- | --- |
| Compile main thành công | Main source biên dịch được |
| Test source compile thành công | Test source hợp lệ về cú pháp/kiểu |
| Test execution được skip | Không có bằng chứng assertion mới đã pass |
| bootJar/package thành công | Artifact được tạo theo build configuration |
| Artifact startup thành công | Đã vượt qua một phần kiểm chứng runtime |
| Integration/E2E tests pass | Những integration/E2E cases đã chạy đạt kỳ vọng |

Đừng báo “đã test pass” nếu test thực chất bị skip. Nếu cần phát hành an toàn, quality gate nên kiểm tra kết quả verification theo tiêu chuẩn dự án.

## 15. Phân biệt Maven package và Gradle bootJar

Một trong những nhầm lẫn phổ biến:

> “Cả hai đều tạo JAR nên chắc chắn có cùng bước kiểm thử.”

Không đúng.

Với Maven, `mvn package` đi qua các phase trước nó, thường bao gồm `test`. Với Gradle, `./gradlew bootJar` là một packaging task, không mặc định phụ thuộc vào `test`. Muốn Gradle làm verification theo lifecycle thông thường, `./gradlew build` phù hợp hơn, với điều kiện project đã nối đúng các task test vào `check`.

Ngay cả với Maven, cấu hình `-DskipTests` hoặc plugin tùy chỉnh có thể khiến tests không chạy. Kết luận luôn phải dựa trên task graph/lifecycle và báo cáo thực tế.

## 16. Integration tests không tự động xuất hiện trong build

Một project có thể tách test:

~~~text
src/test/java/                    # Unit và các test thuộc test task
src/integrationTest/java/         # Integration test source set nếu tự cấu hình
~~~

Gradle không tự biết `integrationTest` là một task chỉ vì tên thư mục tồn tại. Cần source set/task và wiring thích hợp.

Một build có thể có:

~~~bash
./gradlew test
./gradlew integrationTest
~~~

Nếu `integrationTest` không được nối vào `check`, gọi `./gradlew build` có thể chưa chạy nó.

Với Maven, một lựa chọn phổ biến là:

- Surefire Plugin chạy unit tests ở phase `test`.
- Failsafe Plugin chạy integration tests ở `integration-test` và kiểm tra kết quả ở `verify`.

Khi đã cấu hình đúng:

~~~bash
mvn verify
~~~

có thể chạy cả integration tests. Nhưng `mvn package` dừng trước `integration-test`, nên không tự chạy các test được ràng buộc sau package.

**Bài học:** muốn biết đã kiểm thử gì, hãy nhìn task/phase/plugin configuration và test report, không chỉ nhìn tên lệnh tổng hợp.

## 17. Multi-module: compile dependency khác test dependency

Giả sử project có:

~~~text
project/
├── common-model/
├── business-core/
└── api-app/
~~~

`api-app` phụ thuộc vào `business-core` và `common-model`:

~~~groovy
dependencies {
    implementation project(':common-model')
    implementation project(':business-core')
}
~~~

Khi chạy:

~~~bash
./gradlew :api-app:bootJar
~~~

Gradle có thể build các outputs cần thiết của dependency modules. Tuy nhiên, **không thể suy ra** các task `:business-core:test` hoặc `:common-model:test` đã chạy chỉ vì artifact app được tạo.

Một release pipeline multi-module nên xác định:

- Module nào có tests bắt buộc.
- Integration tests nào liên quan đến toàn hệ thống.
- App module nào tạo executable JAR.
- Library modules nào chỉ cần plain JAR.
- Điều kiện nào phải pass trước khi publish artifact.

Không nhất thiết bật Spring Boot plugin cho mọi library module. Một library có thể dùng `java-library` plugin, còn app module mới dùng `bootJar`.

## 18. CI/CD: build artifact và release gate là hai việc khác

Pipeline có thể tổ chức theo hai job song song:

~~~mermaid
flowchart TD
    C["Commit"] --> T["Job A: test / verification"]
    C --> P["Job B: package"]
    T --> G{"Quality gate"}
    P --> G
    G -->|Cả hai thành công| U["Publish artifact"]
    G -->|Một job thất bại| X["Block release"]
    U --> ST["Deploy staging / smoke test"]
    ST --> PR["Promote production theo policy"]
~~~

Một cấu hình giả lập:

~~~yaml
jobs:
  test:
    steps:
      - run: ./gradlew test

  package:
    steps:
      - run: ./gradlew bootJar

  publish:
    needs: [test, package]
    steps:
      - run: echo "Publish only after both jobs pass"
~~~

Đây là **pseudo YAML**, không phải một workflow hoàn chỉnh cho CI provider nào. Thực tế còn cần checkout source, setup JDK, lưu/truyền artifact, credentials và quyền publish.

Điểm quan trọng: **artifact được tạo** không đồng nghĩa **artifact được phép publish**.

### 18.1. Sử dụng cùng source revision

Nếu test job chạy commit A nhưng package job chạy commit B, kết quả test của A không chứng minh artifact B đạt yêu cầu.

CI nên gắn kết:

- Commit SHA/source revision.
- Build tool và JDK version.
- Dependency resolution.
- Artifact version/checksum.
- Test/verification result.
- Environment được dùng để chạy smoke test.

### 18.2. Promote một artifact thay vì rebuild tùy ý

Trong pipeline có staging và production, việc promote cùng một immutable artifact giúp giảm rủi ro rằng bản production khác bản đã test vì dependency hoặc generated resource thay đổi khi rebuild.

Nếu cần reproducible build, phải kiểm soát timestamp, versions, toolchains, generated inputs và các thành phần ảnh hưởng output.

## 19. Lỗi ở giai đoạn nào?

| Triệu chứng | Giai đoạn | Cách điều tra |
| --- | --- | --- |
| `cannot find symbol` | Compile | Sai tên class/method hoặc thiếu compile dependency |
| `incompatible types` | Compile | Kiểm tra kiểu, generics, method signature |
| Processor không tạo generated class | Annotation processing/compile | Kiểm tra processor path và config |
| `No tests found` | Test discovery | Kiểm tra JUnit engine, filter, source set |
| `AssertionFailedError` | Test execution | Đọc expected/actual và logic nghiệp vụ |
| `Failed to load ApplicationContext` trong test | Test runtime | Kiểm tra bean wiring/test profile/config |
| `Could not resolve dependencies` | Dependency resolution | Kiểm tra repository, version, network |
| `Main class name has not been configured` trong `bootJar` | Packaging | Kiểm tra main class detection/config |
| `no main manifest attribute` khi chạy | Artifact execution | Có thể chọn nhầm plain JAR |
| `ClassNotFoundException` khi chạy JAR | Runtime/classpath | Kiểm tra runtime deps/Boot loader |
| `Port already in use` | Runtime startup | Kiểm tra cấu hình port/process |
| `Failed to bind properties` | Runtime configuration | Kiểm tra config values, profile, validation |
| App chạy nhưng HTTP không đáp ứng | Runtime/deployment | Kiểm tra server, routing, health, network |

### 19.1. “BUILD FAILED” chỉ là kết luận tổng quát

Nếu log chứa:

~~~text
> Task :compileJava FAILED
~~~

đó là lỗi compile.

Nếu:

~~~text
> Task :test FAILED
~~~

đó là lỗi test task.

Nếu:

~~~text
> Task :bootJar FAILED
~~~

đó là lỗi task packaging hoặc prerequisite liên quan. Cần đọc **task thật sự thất bại đầu tiên**, không chỉ dòng `BUILD FAILED`.

Ví dụ chạy `./gradlew bootJar` mà `:compileJava` thất bại, thì compile prerequisite chưa thành công; Boot JAR có thể chưa được tạo.

### 19.2. Build báo success không có nghĩa đúng mục tiêu

Nếu bạn chạy `compileJava` và thấy success, nhưng cần executable JAR, bạn đã chọn **sai task** cho mục tiêu đó. Không phải compiler làm sai; đơn giản nó không được yêu cầu package.

Tương tự Maven project có packaging `pom` không nhất thiết tạo app JAR chỉ vì `mvn package` thành công.

## 20. Artifact tồn tại chưa có nghĩa test pass

Một case cụ thể:

~~~bash
./gradlew bootJar
~~~

có thể tạo `build/libs/demo-app-1.0.0.jar` ngay cả khi unit test:

~~~java
@Test
void shouldRejectNegativeDistance() {
    assertThrows(
            IllegalArgumentException.class,
            () -> new ShippingCalculator().calculate(-1)
    );
}
~~~

đang fail. Lệnh packaging không nhất thiết execute test.

Một case khác:

~~~bash
mvn package -DskipTests
~~~

có thể tạo artifact dù test execution bị bỏ qua.

Do đó khi xem pull request hoặc CI report, nên ghi rõ:

- Compile task/phase: thành công hay thất bại?
- Test task/phase: đã chạy, bị skip hay lấy từ cache?
- Số lượng test, failures, ignored tests.
- Packaging task: có tạo artifact đúng loại không?
- Smoke test từ artifact: đã thực thi chưa?
- Quality gate: có chặn publish khi kiểm thử thất bại không?

## 21. Khi nào cần clean build?

Lệnh:

~~~bash
./gradlew clean build
~~~

hoặc:

~~~bash
mvn clean verify
~~~

có thể hữu ích khi muốn xác nhận trạng thái từ output sạch. Tuy nhiên, clean làm mất lợi ích incremental build nên không cần mỗi lần bạn sửa một method.

Khi đang debug artifact khác thường, clean build có thể giúp loại trừ output cũ. Khi đang sửa logic đơn giản, chạy đúng unit test sẽ nhanh hơn.

### 21.1. Wrapper giúp đồng bộ công cụ build

Gradle wrapper:

~~~bash
./gradlew build
~~~

Maven wrapper, nếu repository có:

~~~bash
./mvnw verify
~~~

Wrapper giúp developer/CI dùng version công cụ build được project chỉ định, nhưng không tự cố định mọi dependency hay JDK version. Build reproducibility còn phụ thuộc toolchain và dependency locking/management.

## 22. Dùng cùng một ví dụ để so sánh ba giai đoạn

Giả sử có:

~~~text
src/main/java/com/example/demo/ShippingCalculator.java
src/test/java/com/example/demo/ShippingCalculatorTest.java
src/main/resources/application.yml
build.gradle
~~~

Các bước quan sát:

### 22.1. Bước A: compile

~~~bash
./gradlew compileJava
~~~

Đầu ra mong đợi: `ShippingCalculator.class` và các main classes khác. Việc input âm được xử lý đúng hay không chưa được khẳng định.

### 22.2. Bước B: test

~~~bash
./gradlew test
~~~

Đầu ra mong đợi: task test chạy và tạo report, pass hoặc fail theo JUnit assertions. Một test lỗi khiến task thất bại nếu không có cấu hình ignore failures.

### 22.3. Bước C: package

~~~bash
./gradlew bootJar
~~~

Đầu ra mong đợi: executable JAR có main classes, resources và runtime libraries. Task có thể thành công dù test fail nếu test không thuộc dependency graph packaging.

### 22.4. Bước D: chạy artifact

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

Đầu ra mong đợi: JVM dùng Spring Boot loader khởi động ứng dụng. Ở bước này có thể phát hiện lỗi khác như thiếu config hoặc database unavailable.

Bốn bước trả lời **bốn câu hỏi khác nhau**, dù các bước sau sử dụng kết quả từ bước trước.

## 23. Kiểm thử packaged artifact và test report

Một test chạy từ IDE/Gradle thường sử dụng main/test classes ở thư mục output. Artifact production có thể đóng gói classpath resources trong JAR. Vì vậy, một số lỗi chỉ xuất hiện khi chạy JAR.

Một pipeline đủ chặt chẽ có thể:

1. Chạy unit tests.
2. Chạy integration tests được yêu cầu.
3. Tạo executable Boot JAR.
4. Kiểm tra manifest/structure.
5. Khởi động artifact.
6. Chạy health/smoke tests.
7. Publish/promote artifact khi tất cả gates thành công.

Kết quả unit test có thể được lưu trong:

~~~text
build/test-results/test/
build/reports/tests/test/
target/surefire-reports/
~~~

Coverage report (ví dụ JaCoCo) là sản phẩm khác, cần plugin riêng. Coverage cao không tự chứng minh chất lượng của assertions; có test report cũng không tự khẳng định mọi scenario được bao phủ.

## 24. Bài tập thực hành

### Bài tập 1 — Phân biệt compile và test

Tạo một class tính phí có method biên dịch đúng nhưng xử lý input âm sai. Viết JUnit test yêu cầu ném exception cho input âm. Chạy `compileJava` và `test` riêng, ghi lại khác biệt.

### Bài tập 2 — Compile test nhưng chưa chạy test

Tạo một JUnit test có assertion sai. Chạy `compileTestJava` rồi `test`. Giải thích vì sao test source có thể compile trong khi test execution fail.

### Bài tập 3 — bootJar không nhất thiết chạy test

Dùng project có test cố ý fail. Chạy `bootJar` và quan sát task graph. Phân biệt khả năng tạo artifact với kết quả verification.

### Bài tập 4 — jar và bootJar

Tạo plain JAR và executable Boot JAR. Dùng `jar tf` xem `BOOT-INF/classes`, `BOOT-INF/lib` và manifest. Xác định artifact nào được thiết kế để chạy `java -jar`.

### Bài tập 5 — Gradle build và check

Chạy `./gradlew check` và `./gradlew assemble` trong một project ví dụ. Ghi lại task nào là verification, task nào là assembly.

### Bài tập 6 — Maven lifecycle

Trong project Maven Spring Boot, so sánh `mvn compile`, `mvn test`, `mvn package` và `mvn verify`. Xác định test plugin và packaging plugin được gọi ở phase nào.

### Bài tập 7 — So sánh cách skip test

So sánh `./gradlew build -x test`, `mvn package -DskipTests` và `mvn package -Dmaven.test.skip=true`. Ghi rõ bước test nào bị skip và điều gì vẫn có thể chạy.

### Bài tập 8 — Chạy từ bootRun và JAR

Đặt resource ở `src/main/resources/data/catalog.json`, đọc qua `ClassPathResource.getInputStream()`. Chạy từ `bootRun` và executable JAR; giải thích khác biệt classpath layout.

### Bài tập 9 — Multi-module

Tạo `common-model` và `api-app`. Chạy `:api-app:bootJar` và kiểm tra xem test của common module có được yêu cầu không. Đề xuất quality gate phù hợp cho release.

### Bài tập 10 — CI release gate

Thiết kế pseudo-pipeline có job unit test, package và publish. Chỉ cho publish chạy khi cả test và package đều thành công. Thêm artifact digest/source commit để bảo đảm deploy đúng file đã được kiểm soát.

### Bài tập 11 — Smoke test artifact

Chạy một executable Spring Boot JAR trong môi trường test với profile riêng. Gọi một endpoint an toàn hoặc `/actuator/health` và xác minh startup. Giải thích vì sao bước này bổ sung giá trị cho unit tests.

### Bài tập 12 — Phân loại build error

Với ba log có `compileJava FAILED`, `test FAILED` và `bootJar FAILED`, xác định giai đoạn thực sự thất bại và chọn nơi cần đọc diagnostics/test reports.

## 25. Ghi nhớ

**Biên dịch, kiểm thử và đóng gói có mục tiêu khác nhau.** Compile biến Java source thành bytecode và phát hiện lỗi cú pháp/kiểu. Test thực thi những tình huống có assertion và báo pass/fail trong môi trường test. Packaging tạo JAR/WAR từ classes, resources và dependencies theo cấu hình build. Một thành công không suy ra mọi thành công còn lại.

Với **Gradle**, `compileJava`, `test`, `jar`, `bootJar`, `check` và `build` là các task được nối bằng dependency graph. `bootJar` thường không bắt buộc chạy test; `build` thường kết hợp verification và assembly, nhưng custom test suites chỉ được chạy nếu đã cấu hình liên kết.

Với **Maven**, `compile`, `test`, `package` và `verify` là các lifecycle phases. Gọi `mvn package` thường chạy test trước package, trừ khi bị skip hoặc tùy biến. Executable Spring Boot JAR cần plugin/goal phù hợp, không chỉ đuôi `.jar`.

Sau cùng, **artifact tồn tại không có nghĩa test pass; test pass không có nghĩa production sẽ chạy đúng; deploy thành công không có nghĩa mọi luồng nghiệp vụ đã được kiểm tra**. Hãy chọn đúng lệnh cho câu hỏi muốn trả lời và thiết lập quality gates minh bạch trước khi phát hành.
