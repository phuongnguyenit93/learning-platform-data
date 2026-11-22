# Chạy nhất quán bằng IDE và công cụ build

Một bài test Spring có thể chạy thành công trong IDE nhưng thất bại khi chạy bằng Gradle hoặc Maven trên máy khác. Cũng có trường hợp test chạy qua ở máy lập trình viên nhưng thất bại trên CI. Những khác biệt này thường đến từ cách khởi chạy test: JDK khác nhau, runner khác nhau, profile hoặc biến môi trường không giống nhau, working directory khác, bộ lọc test khác, hoặc cấu hình song song và fork JVM khác.

Mục tiêu của kiểm thử nhất quán là làm cho cùng một test nhận cùng dependency, cấu hình, tài nguyên và điều kiện chạy dù được khởi động từ IDE, terminal hay CI. Công cụ build nên là nguồn cấu hình có thể tái lập; IDE cần đồng bộ dự án với công cụ build và dùng cùng JDK, classpath, profile, system property và test filter.

Không phải mọi khác biệt giữa IDE và build tool đều là lỗi của Spring. IDE có thể dùng runner JUnit riêng, còn Gradle hoặc Maven chạy JUnit Platform trong JVM do build tool quản lý. Muốn chẩn đoán chính xác, cần biết test được chạy bằng runner nào và cấu hình nào đã được truyền vào tiến trình test.

## 1. Vì sao cùng một test có thể cho kết quả khác nhau?

Một test Spring phụ thuộc vào nhiều yếu tố ngoài nội dung method test:

| Yếu tố | Khác biệt có thể xảy ra |
|---|---|
| JDK | IDE dùng JDK 21 trong khi Gradle daemon hoặc Maven dùng JDK 17 |
| Test runner | IDE chạy trực tiếp bằng JUnit runner; build tool chạy qua JUnit Platform |
| Dependency | IDE chưa đồng bộ phiên bản mới nhất từ Maven/Gradle |
| Profile | IDE đặt spring.profiles.active=test; terminal không truyền profile |
| Biến môi trường | Run configuration có API URL test nhưng shell không có |
| System property | IDE truyền user.timezone hoặc spring.*; build tool không truyền |
| Working directory | IDE chạy từ module con, build tool chạy từ root project |
| Test discovery | IDE tìm thấy method; Surefire/Failsafe hoặc Gradle filter không chọn class đó |
| Parallel/fork | IDE chạy tuần tự trong một JVM; CI chạy nhiều worker hoặc fork |
| Tài nguyên ngoài | Docker có trong máy local nhưng không có trong CI; port hoặc service khác nhau |
| Thứ tự test | Test phụ thuộc state do một test trước đó tạo ra |

Khi kết quả khác nhau, không nên lập tức sửa assertion hoặc thêm sleep. Trước tiên hãy so sánh môi trường và lệnh chạy thực tế. Một test ổn định phải tự thiết lập các điều kiện mà nó cần và không phụ thuộc vào trạng thái ngẫu nhiên của IDE.

## 2. Chọn công cụ build làm nguồn cấu hình chính

IDE là nơi viết, chạy từng test và debug. Gradle hoặc Maven mô tả dependency, source set, test engine, JVM, system property, task và lifecycle. CI nên chạy bằng wrapper của chính dự án để dùng đúng phiên bản build tool.

Với Gradle:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Với Maven:

~~~bash
./mvnw test
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd test
~~~

Wrapper giúp developer và CI dùng phiên bản Gradle hoặc Maven đã được dự án khai báo. Tránh yêu cầu mỗi máy cài một phiên bản global khác nhau rồi kỳ vọng kết quả giống hệt.

Trong IDE, hãy import dự án từ build.gradle hoặc pom.xml, đồng bộ dependency và cấu hình runner dựa trên build tool. Khi IDE cho phép chọn cách chạy test bằng runner nội bộ hoặc Gradle/Maven, dùng build tool runner khi cần tái hiện chính xác hành vi CI. Runner nội bộ vẫn hữu ích để debug nhanh, nhưng cần biết nó có thể dùng cách discovery hoặc JVM khác.

## 3. Đồng bộ JDK giữa IDE, build tool và test JVM

Một dự án có thể có nhiều lựa chọn JDK:

- JDK của IDE hoặc Project SDK.
- JDK chạy Gradle daemon hoặc Maven process.
- Java toolchain dùng để compile source.
- JVM chạy test worker hoặc fork.
- JDK của CI runner.

Các giá trị này không tự động luôn giống nhau. Ví dụ IDE có Project SDK 21 nhưng Gradle JVM vẫn là 17; build compile bằng toolchain 21 nhưng test task được cấu hình fork với executable khác.

### 3.1. Khai báo Java toolchain trong Gradle

Với Gradle, dùng toolchain để mô tả phiên bản Java mà project cần:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Test task có thể dùng launcher từ toolchain:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )
}
~~~

Toolchain cho phép Gradle chọn JDK phù hợp cho compile và test. Máy chạy build vẫn cần có JDK phù hợp hoặc được cấu hình để Gradle tải toolchain theo chính sách của dự án.

### 3.2. Khai báo Java release trong Maven

Với Maven Compiler Plugin, có thể khai báo release:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Thuộc tính maven.compiler.release kiểm soát ngôn ngữ và API Java mục tiêu khi compile. Nó không tự bảo đảm mọi Maven process hoặc test fork đang chạy bằng cùng một JDK. Nếu dự án dùng Maven Toolchains Plugin, cấu hình toolchain để chọn JDK cụ thể cho compiler và plugin liên quan.

### 3.3. Kiểm tra JDK thực tế

Khi nghi ngờ môi trường khác nhau, ghi nhận:

~~~bash
java -version
./gradlew -version
./mvnw -version
~~~

Trong test có thể kiểm tra phiên bản runtime bằng System.getProperty("java.version"). Chỉ dùng assertion phiên bản khi đây là yêu cầu của dự án; thông thường log runtime trong build giúp chẩn đoán mà không làm test phụ thuộc quá chặt vào patch version.

IDE cần trỏ Project SDK và Gradle JVM/Maven runner JRE tới cấu hình tương thích với toolchain. Nếu dùng JDK khác nhau có chủ đích, phải bảo đảm phiên bản đó nằm trong ma trận hỗ trợ của dự án.

## 4. Dùng cùng JUnit Platform và test engine

Spring Framework testing thường dùng JUnit Jupiter. JUnit Platform là nền tảng discovery và execution cho các engine; Jupiter là một engine trên nền tảng đó.

Trong Gradle, cần bật JUnit Platform cho test task:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Với Spring Boot, dependency management có thể cung cấp phiên bản JUnit phù hợp qua starter test. Tránh khai báo các phiên bản JUnit Platform, Jupiter API và engine không tương thích nhau nếu không có nhu cầu cụ thể.

Trong Maven, cấu hình Surefire phiên bản tương thích với JUnit Platform và dependency engine tương ứng. Ví dụ cấu hình plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Số phiên bản trên là ví dụ minh họa; dự án nên dùng phiên bản được Spring Boot BOM hoặc chính sách plugin nội bộ quản lý. Quan trọng là Surefire phải hỗ trợ JUnit Platform và classpath có Jupiter engine. Nếu dùng JUnit 4, cần engine hoặc provider tương ứng; không trộn cấu hình JUnit 4 và Jupiter một cách vô ý.

Nếu IDE chạy test nhưng Maven/Gradle báo không tìm thấy test, hãy kiểm tra engine, dependency scope, test source directory và tên class. IDE có thể chạy trực tiếp một class dù Surefire/Failsafe không chọn class đó theo include pattern.

## 5. Đồng bộ cách phát hiện test

Một test chỉ được chạy khi runner phát hiện class và method đó. Quy ước tên file, thư mục source và filter có thể khác giữa build tool.

### 5.1. Gradle

Gradle mặc định chạy test đã compile trong test source set và dùng JUnit Platform nếu được cấu hình useJUnitPlatform(). Có thể chạy riêng một class hoặc method:

~~~bash
./gradlew test --tests "com.example.order.OrderServiceTest"
./gradlew test --tests "com.example.order.OrderServiceTest.createsOrder"
~~~

Với task integration test riêng, phải gọi đúng task đó, ví dụ:

~~~bash
./gradlew integrationTest
~~~

Nếu project tạo source set và task integrationTest, task này có thể không nằm trong test mặc định. Xem task graph và cấu hình check để biết integration test có được chạy trong CI hay không.

### 5.2. Maven Surefire và Failsafe

Maven Surefire thường chạy unit test trong phase test. Quy ước include mặc định thường nhận các tên như Test*, *Test, *Tests và *TestCase. Một class tên OrderServiceSpec có thể chạy trong IDE nhưng không được Surefire phát hiện nếu không cấu hình include phù hợp.

Chạy một class:

~~~bash
./mvnw -Dtest=OrderServiceTest test
~~~

Maven Failsafe thường dành cho integration test với các tên như IT*, *IT hoặc *ITCase. Chạy qua lifecycle để Failsafe thực hiện cả integration-test và verify:

~~~bash
./mvnw verify
~~~

Chỉ gọi integration-test mà bỏ qua verify có thể bỏ qua bước tổng hợp kết quả hoặc kiểm tra lỗi mà plugin thực hiện ở cuối lifecycle. Dùng verify làm điểm gọi thông thường cho integration test Maven.

### 5.3. Tên class và source set phải rõ ràng

Đặt tên theo quy ước thống nhất:

- OrderServiceTest cho unit hoặc slice test.
- OrderRepositoryIT hoặc OrderWorkflowIT cho integration test nếu build tool được cấu hình tương ứng.

Tên chỉ là quy ước; cấu hình plugin/task mới quyết định test nào được chạy. Đừng dựa vào việc IDE hiển thị icon chạy màu xanh để kết luận CI cũng sẽ chọn class đó.

## 6. Đồng bộ Spring profile và cấu hình test

Spring Boot có thể nạp cấu hình theo profile. Một test chạy trong IDE với profile test nhưng chạy từ terminal không có profile có thể kết nối nhầm database hoặc dùng cấu hình không mong muốn.

Có thể chỉ định profile trên test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {
}
~~~

Với test cần cấu hình riêng, đặt file application-test.yml trong src/test/resources:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test;DB_CLOSE_DELAY=-1
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Đây chỉ là ví dụ cho một cấu hình database test; nếu cần kiểm tra dialect production, dùng database tương ứng thay vì H2.

ActiveProfiles("test") làm profile rõ ngay trong test class và ít phụ thuộc Run Configuration của IDE. Có thể dùng profile qua system property hoặc environment variable khi cần chạy cùng một bộ test với nhiều cấu hình:

~~~bash
./gradlew test -Dspring.profiles.active=test
./mvnw -Dspring.profiles.active=test test
~~~

Tuy nhiên, đừng để test quan trọng chỉ chạy đúng khi developer nhớ nhập một profile thủ công. Hãy đưa cấu hình bắt buộc vào test annotation hoặc build configuration được quản lý trong repository.

### 6.1. Thứ tự nguồn cấu hình

Spring Boot có nhiều nguồn property và thứ tự ưu tiên. Test property, @DynamicPropertySource, system property, environment variable và file cấu hình có thể ghi đè lẫn nhau theo quy tắc của Spring Boot. Khi IDE và CI khác kết quả, kiểm tra property thực tế được resolve thay vì chỉ đọc một file YAML.

Với dependency động như Testcontainers, @DynamicPropertySource phù hợp để đăng ký URL, username và password từ container đang chạy:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Cách này tránh hardcode port ngẫu nhiên hoặc giả định container luôn chạy ở cùng địa chỉ.

## 7. Đồng bộ environment variable và system property

IDE có thể lưu biến môi trường trong Run Configuration. Terminal và CI cần thiết lập các biến tương đương. Ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=test
PAYMENT_API_URL=http://localhost:9090
FEATURE_NEW_CHECKOUT=false
~~~

Đối với biến cần thiết cho test, có thể khai báo trong cấu hình build hoặc file cấu hình test. Không đưa secret thật vào repository. Dùng giá trị giả, service giả hoặc secret store của CI theo đúng mục đích.

Gradle có thể truyền system property cho test JVM:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("user.timezone", "UTC")
    systemProperty("user.language", "en")
}
~~~

Maven Surefire có thể truyền system property:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <user.timezone>UTC</user.timezone>
            <user.language>en</user.language>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Chỉ cố định locale hoặc timezone khi test cần hành vi xác định theo một chuẩn. Nếu sản phẩm phải hỗ trợ nhiều locale/timezone, viết test tham số hóa cho các trường hợp đó thay vì giả định toàn bộ hệ thống luôn chạy UTC.

Không đọc secret từ máy developer rồi để test phụ thuộc secret đó. Test tự động phải có cấu hình không nhạy cảm và có thể chạy trong CI sạch.

## 8. Working directory và tài nguyên test

IDE có thể đặt working directory là module hoặc thư mục project; Gradle/Maven thường chạy task với working directory theo project/module. Nếu test đọc file bằng đường dẫn tương đối như new File("src/test/resources/data.json"), kết quả có thể khác giữa hai runner.

Ưu tiên đọc tài nguyên từ classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("fixtures/orders/valid-order.json");

try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

Đặt fixture trong src/test/resources hoặc thư mục test resource được khai báo trong build. Classpath resource hoạt động ổn định hơn đường dẫn phụ thuộc working directory.

Với file được tạo trong test, dùng JUnit @TempDir:

~~~java
@Test
void writesExport(@TempDir Path tempDir) throws IOException {
    Path output = tempDir.resolve("export.json");
    // Ghi và đọc file trong thư mục tạm của test.
}
~~~

Không ghi fixture hoặc output test vào thư mục source chung. Test chạy song song có thể ghi đè file của nhau nếu dùng cùng tên hoặc thư mục cố định.

## 9. Đồng bộ dependency và plugin

IDE có thể giữ trạng thái project model cũ nếu chưa reload Maven/Gradle. Khi dependency vừa thay đổi, runner nội bộ có thể dùng classpath khác với build tool.

Quy trình khi gặp ClassNotFoundException, NoSuchMethodError hoặc hành vi JUnit khác nhau:

1. Reload Gradle hoặc Maven project trong IDE.
2. Kiểm tra dependency tree của build tool.
3. Xác nhận test runtime có đúng JUnit engine và Spring Test version.
4. Kiểm tra BOM hoặc dependency constraints có quản lý phiên bản nhất quán không.
5. Chạy test bằng wrapper để xác định lỗi có tái hiện ngoài IDE không.

Với Gradle, có thể xem dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.junit.jupiter,org.junit.platform
~~~

Không thêm một phiên bản JUnit riêng chỉ để IDE hết cảnh báo nếu Spring Boot BOM đang quản lý bộ phiên bản tương thích. Thay đổi dependency cần dựa trên dependency graph và phiên bản Spring/Boot thực tế.

## 10. Đồng bộ test filter, tag và nhóm test

JUnit Jupiter hỗ trợ @Tag để phân loại:

~~~java
@Tag("integration")
@SpringBootTest
class OrderWorkflowIT {
}
~~~

Gradle có thể lọc tag qua JUnit Platform configuration:

~~~kotlin
tasks.test {
    useJUnitPlatform {
        excludeTags("integration")
    }
}

tasks.register<Test>("integrationTest") {
    useJUnitPlatform {
        includeTags("integration")
    }
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
}
~~~

Đây là khung cấu hình minh họa; project có thể dùng source set riêng cho integration test và cần thêm quan hệ task, dependency hoặc output directory tương ứng.

Với Maven Surefire/Failsafe, có thể cấu hình groups/tags theo JUnit Platform provider mà plugin đang dùng. Ví dụ:

~~~xml
<configuration>
    <groups>integration</groups>
</configuration>
~~~

Hãy kiểm tra cấu hình plugin và engine thực tế của dự án trước khi sao chép. Cùng một tag có thể được xử lý khác nhau nếu IDE, Surefire và Gradle được cấu hình filter khác nhau.

Trong IDE, khi chạy một method hoặc class cụ thể, runner thường bỏ qua một số filter của task build. Khi cần tái hiện CI, hãy chạy task/tag filter tương ứng bằng wrapper.

## 11. Parallel execution, fork JVM và test isolation

IDE thường chạy một test class trong một tiến trình hoặc runner do IDE quản lý. Build tool có thể chạy nhiều test worker, nhiều fork JVM hoặc nhiều task đồng thời.

Với Gradle:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxParallelForks = 1
}
~~~

Giá trị 1 giữ số fork của task ở mức một. Khi test đã độc lập và thread-safe, có thể tăng maxParallelForks để rút ngắn thời gian chạy. Cần phân biệt fork JVM của Gradle với parallel execution của JUnit Jupiter bên trong một JVM; đây là hai lớp cấu hình riêng.

JUnit Jupiter có thể bật parallel execution qua junit-platform.properties trong test resources:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=same_thread
~~~

Chỉ bật parallel khi test không chia sẻ mutable state hoặc đã có cơ chế khóa phù hợp. Test dùng cùng database record, system property, file cố định, singleton bean mutable hoặc executor dùng chung có thể gây race condition.

Maven Surefire có các cấu hình fork như forkCount và reuseForks. Nếu test phụ thuộc static state hoặc cache trong JVM, thay đổi fork có thể làm kết quả khác. Không nên tắt fork hoặc parallel toàn cục để che một test không độc lập; trước hết xác định state nào đang bị chia sẻ và cô lập nó.

### 11.1. Những nguồn gây lỗi khi chạy song song

- Nhiều test dùng cùng một username hoặc business key trong database.
- Test cùng ghi một file cố định trong target hoặc build.
- Test sửa system property hoặc default timezone mà không khôi phục.
- Một test shutdown executor hoặc dọn bean singleton đang được test khác dùng.
- Test phụ thuộc thứ tự chạy hoặc dữ liệu do test trước tạo.
- Test dùng port cố định và hai process cùng cố bind.
- Testcontainers hoặc mock server được chia sẻ nhưng một test dừng container/server quá sớm.

Ưu tiên dữ liệu riêng cho từng test, random port, @TempDir, fixture độc lập và lifecycle được quản lý. Nếu tài nguyên buộc phải dùng chung, dùng khóa hoặc chạy nhóm test đó tuần tự một cách có chủ đích.

## 12. Testcontainers và Docker giữa IDE, local và CI

Test dùng Testcontainers cần Docker-compatible runtime. IDE có thể chạy trên máy developer có Docker Desktop, trong khi CI runner có thể không có Docker socket hoặc không được cấp quyền.

Để nhất quán:

- Pin image tag hoặc digest theo chính sách dự án.
- Không hardcode port host; lấy mapped port từ container.
- Khởi tạo container bằng lifecycle của Testcontainers/JUnit.
- Chờ health check hoặc readiness thay vì dùng sleep.
- Cung cấp cấu hình Spring qua @DynamicPropertySource hoặc cơ chế service connection phù hợp với phiên bản Spring Boot.
- Đảm bảo CI runner có Docker-compatible runtime và quyền truy cập cần thiết.

Nếu CI không hỗ trợ Docker, cần quyết định rõ: chạy nhóm integration test ở runner có Docker, dùng dịch vụ database được cấp riêng, hay tách nhóm test. Không nên silently skip test quan trọng chỉ vì môi trường thiếu dependency.

## 13. Spring ApplicationContext cache và khác biệt giữa chạy lẻ với chạy cả suite

Spring TestContext cache application context để tránh khởi tạo lại cho từng test class có cùng cấu hình. Điều này tăng tốc suite nhưng có thể làm lộ test phụ thuộc state:

- Test sửa singleton bean hoặc static state rồi không khôi phục.
- Test thay đổi system property sau khi context đã được tạo.
- Test dùng @DirtiesContext làm context bị đóng trong khi test khác đang phụ thuộc.
- Một bean giữ cache hoặc dữ liệu trong bộ nhớ giữa nhiều test class.

Một test chạy riêng có thể pass vì nhận context mới; chạy cả suite lại fail vì context được tái sử dụng hoặc thứ tự test khác. Cách khắc phục là giữ test độc lập, dọn state sau mỗi test, không sửa bean singleton dùng chung và chỉ dùng @DirtiesContext khi context thực sự bị thay đổi không thể khôi phục.

Khi test phụ thuộc cấu hình profile hoặc property, đặt chúng ngay trong test context bằng annotation/configuration phù hợp. Đừng dựa vào một system property do test class khác thiết lập.

## 14. Cấu hình timeout và môi trường thời gian

Test có thể chạy khác nhau nếu phụ thuộc timezone, locale, clock hoặc thời gian thực:

- Ngày bắt đầu/kết thúc có thể khác khi timezone của JVM khác nhau.
- Parse số hoặc ngày theo locale có thể khác giữa developer và CI.
- Test dùng Instant.now() có thể vượt qua ranh giới ngày hoặc timeout.
- Test async dựa vào Thread.sleep() dễ thất bại khi máy CI tải cao.

Với nghiệp vụ thời gian, ưu tiên inject Clock:

~~~java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Test có thể cung cấp clock cố định:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T00:00:00Z"),
        ZoneOffset.UTC);
~~~

Điều này làm test thời gian có thể lặp lại mà không phụ thuộc đồng hồ hệ thống. Với test chờ async, dùng future, latch, Awaitility hoặc StepVerifier có timeout hữu hạn thay vì sleep.

## 15. Chạy cùng một test từ IDE, terminal và CI

Một quy trình thực tế có thể gồm:

1. Chạy một method trong IDE để debug nhanh.
2. Chạy toàn bộ class bằng Gradle/Maven runner trong IDE hoặc terminal.
3. Chạy cùng task qua wrapper từ root project.
4. Chạy nhóm test cần thiết với cùng profile, tag và environment.
5. Chạy lệnh CI hoặc pipeline local tương ứng trước khi tạo pull request.

Ví dụ với Gradle:

~~~bash
./gradlew test
./gradlew test --tests "com.example.order.OrderServiceTest"
./gradlew integrationTest
./gradlew check
~~~

Ví dụ với Maven:

~~~bash
./mvnw test
./mvnw -Dtest=OrderServiceTest test
./mvnw verify
~~~

check trong Gradle có thể phụ thuộc vào các verification task đã được cấu hình; verify trong Maven chạy các phase trước đó cùng các plugin gắn vào lifecycle. Đừng giả định chúng chạy integration test nếu project chưa gắn task/plugin tương ứng.

Trong IDE, chọn runner Gradle hoặc Maven khi cần cùng lifecycle với CI. Nếu dùng runner JUnit nội bộ để debug, sau khi sửa xong hãy chạy lại bằng wrapper để xác nhận build tool cũng phát hiện và thực thi test.

## 16. Đọc report từ build tool để chẩn đoán

Khi IDE và build tool khác kết quả, report của build tool giúp biết test nào thực sự được chạy:

- Gradle thường tạo HTML report trong build/reports/tests/test/ và XML report trong build/test-results/test/.
- Maven Surefire thường tạo report trong target/surefire-reports/.
- Maven Failsafe thường tạo report trong target/failsafe-reports/.

Đường dẫn có thể thay đổi nếu project đổi output directory hoặc task name. Report giúp xác định số test được phát hiện, test bị skip, exception và stack trace. So sánh report với danh sách test IDE đã chạy để phát hiện test bị filter hoặc discovery khác nhau.

Bật test logging vừa đủ để thấy tên test và lỗi:

~~~kotlin
tasks.test {
    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
~~~

Không bật log quá chi tiết cho toàn bộ suite nếu nó che khuất lỗi chính hoặc làm CI output quá lớn. Có thể tăng log cho task hoặc nhóm test đang điều tra.

## 17. Checklist cho Run Configuration trong IDE

Khi một test chạy khác terminal, kiểm tra lần lượt:

| Thành phần | Cần xác nhận |
|---|---|
| Project SDK | Cùng phiên bản Java mà project hỗ trợ |
| Gradle JVM/Maven runner JRE | Phù hợp với wrapper và toolchain |
| Test runner | IDE runner hay Gradle/Maven runner |
| Module/classpath | Đúng module chứa test và dependency test |
| Working directory | Đúng root project/module mà build giả định |
| Active profile | Giống cấu hình test được khai báo trong repository |
| Environment variables | Đủ biến cần thiết, không dùng secret cá nhân |
| VM options/system properties | Giống cấu hình build tool |
| Test filters/tags | Không vô tình bỏ qua hoặc thêm nhóm test |
| Parallel execution | Phù hợp với isolation và tài nguyên dùng chung |
| Before launch tasks | Dependency/resource generation cần thiết đã chạy |

Nên lưu cấu hình dùng chung vào project/build configuration khi có thể. Tránh để một test chỉ chạy được vì Run Configuration cá nhân chưa được chia sẻ hoặc vì máy developer có biến môi trường không được ghi lại.

## 18. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| IDE chạy được nhưng Maven/Gradle không tìm thấy test | Tên class không khớp include pattern, source set hoặc task filter | Kiểm tra quy ước tên, test source directory và plugin/task |
| IDE pass nhưng build tool lỗi class/method | Dependency model chưa đồng bộ hoặc runner dùng classpath khác | Reload project, kiểm tra dependency tree và chạy wrapper |
| Test dùng profile khác nhau | Run Configuration có profile nhưng build không có | Dùng ActiveProfiles hoặc cấu hình profile trong build |
| Test đọc fixture chỉ chạy được trong IDE | Dùng đường dẫn phụ thuộc working directory | Đọc từ classpath hoặc TempDir |
| Test chỉ fail trên CI | JDK, locale, timezone, environment, Docker hoặc parallel khác | So sánh runtime và property; loại bỏ phụ thuộc máy cá nhân |
| Test pass khi chạy riêng nhưng fail trong suite | Shared state, context cache, thứ tự hoặc race condition | Làm test độc lập, dọn state và dùng resource lock khi cần |
| Integration test không chạy trong test | Task/source set hoặc Failsafe lifecycle chưa được nối | Gọi đúng task hoặc cấu hình check/verify |
| IDE dùng JDK khác Gradle daemon | Project SDK và Gradle JVM khác nhau | Đồng bộ IDE settings và toolchain |
| Test container chạy local nhưng fail CI | CI thiếu Docker-compatible runtime hoặc quyền truy cập | Dùng runner có Docker và kiểm tra readiness |
| Test thời gian thất thường | Dùng clock hệ thống, sleep hoặc timeout quá sát | Inject Clock và đồng bộ bằng signal có timeout |

## 19. Quy trình chuẩn hóa cho một dự án Spring

Để developer mới có thể chạy test mà không cần thiết lập thủ công riêng, dự án nên thống nhất:

1. Commit Gradle Wrapper hoặc Maven Wrapper và dùng wrapper trong tài liệu, CI.
2. Khai báo Java version/toolchain rõ ràng.
3. Dùng JUnit Platform và dependency engine tương thích.
4. Quy định tên test, source set và task cho unit/integration test.
5. Khai báo profile và test property trong repository.
6. Đọc fixture từ classpath và file tạm từ TempDir.
7. Đặt timeout, locale và timezone theo yêu cầu nghiệp vụ.
8. Quy định parallel/fork sau khi test đã độc lập.
9. Khai báo dependency ngoài như Testcontainers và yêu cầu môi trường CI.
10. Cung cấp các lệnh wrapper chuẩn để chạy test lẻ, test suite và integration test.
11. Lưu report và log đủ để chẩn đoán test bị bỏ qua hoặc thất bại.
12. Cấu hình IDE để đồng bộ project model và ưu tiên runner build tool khi cần tái hiện CI.

## 20. Ví dụ một quy ước chạy test thống nhất

Một README nội bộ của dự án có thể công bố các lệnh ngắn:

~~~text
Chạy unit và slice test:
  ./gradlew test
  ./mvnw test

Chạy một class:
  ./gradlew test --tests "com.example.OrderServiceTest"
  ./mvnw -Dtest=OrderServiceTest test

Chạy integration test:
  ./gradlew integrationTest
  ./mvnw verify

Chạy toàn bộ verification:
  ./gradlew check
  ./mvnw verify
~~~

Chỉ công bố các lệnh tương ứng với build tool thực sự được dự án sử dụng; không cần duy trì cả Gradle lẫn Maven nếu repository chỉ có một build system. Các task integrationTest, check hoặc plugin Failsafe phải được cấu hình trước khi đưa vào hướng dẫn.

Khi IDE, terminal và CI dùng cùng wrapper, JDK, test engine, profile, test filter và dependency, kết quả sẽ dễ tái lập hơn. Nếu vẫn có khác biệt, hãy so sánh JVM thực tế, classpath, property, working directory, số test được discovery và report của build tool để tìm nguyên nhân cụ thể.

Chạy nhất quán không có nghĩa mọi test phải được chạy theo cùng một cách thủ công. Nó có nghĩa dự án định nghĩa rõ môi trường và lệnh chuẩn, IDE có thể tái hiện cấu hình đó, và CI chạy đúng nguồn cấu hình đã được version control. Nhờ vậy, kết quả test phản ánh code và hợp đồng của ứng dụng thay vì trạng thái riêng trên một máy phát triển.
