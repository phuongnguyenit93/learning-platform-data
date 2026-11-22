# Context failure threshold và thông báo lặp che nguyên nhân gốc trong Spring Boot Test

## 1. Tình huống thực tế: hàng chục tests đỏ nhưng chỉ một cấu hình bị hỏng

Bạn nâng cấp Spring Boot hoặc đổi một property cho profile `test`. Khi chạy cả bộ `@SpringBootTest`, nhiều lớp báo lỗi giống nhau:

~~~text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for
[MergedContextConfiguration@... testClass=..., classes=..., ...]
~~~

Người mới học dễ kết luận rằng phải tăng threshold, thêm `@DirtiesContext`, xóa cache hoặc sửa tất cả những test bị đánh dấu đỏ. Nhưng thông điệp trên thường **không phải nguyên nhân gốc**. Nó nói rằng **một lần khởi tạo ApplicationContext với cùng context-cache key đã thất bại**, và Spring TestContext Framework **chủ động không thử lại** cho các test tiếp theo có cùng key vì mặc định chỉ cho phép một lần thử thất bại.

Lỗi đầu tiên của cùng nhóm có thể là:

~~~text
java.lang.IllegalStateException:
Failed to load ApplicationContext for
[MergedContextConfiguration@...]
Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
Caused by: java.lang.IllegalArgumentException:
Missing property payment.gateway.url
~~~

Chỉ hàng cuối `Missing property payment.gateway.url` mới giúp xác định việc phải làm. Các thông báo `failure threshold exceeded` phía sau là **hậu quả của cùng cache key**, không phải bằng chứng rằng các test logic độc lập đều có bug.

**Đề bài:** “Context failure threshold và thông báo lặp che nguyên nhân gốc”, thuộc nhóm cha **Chẩn đoán lỗi kiểm thử** của Spring Boot testing. Trọng tâm là **cách truy lại nguyên nhân của lần context load đầu tiên** và hiểu vì sao hàng loạt lỗi lặp xuất hiện.

Sau bài học, bạn có thể:

1. Giải thích context-cache key, cache miss và `ApplicationContext` loading trong Spring TestContext.
2. Nêu đúng chính sách **context failure threshold được giới thiệu từ Spring Framework 6.1**, **mặc định bằng 1 cho mỗi key**.
3. Phân biệt **lần khởi tạo thật thất bại** với **lần bị bỏ qua trước khi khởi tạo**.
4. Biết cú pháp cấu hình `spring.test.context.failure.threshold` và nơi phải đặt **JVM system property trong test worker**.
5. Hiểu tại sao `-D...` đưa cho Gradle không luôn được tự chuyển sang JVM chạy tests nếu build script không forward.
6. Biết `@ActiveProfiles`, `@SpringBootTest(properties=...)`, `@TestPropertySource`, `@MockBean`, `@DynamicPropertySource` và cấu hình test khác có thể làm cache key đổi.
7. Đọc stack trace theo `Caused by`, tìm lỗi thấp nhất có ý nghĩa, thay vì chỉ nhìn summary test đỏ.
8. Ưu tiên test class/lần khởi tạo **đầu tiên theo execution chronology**, không mặc định lớp đứng đầu bảng tên chữ cái là nơi lỗi gốc.
9. Biết cách bật logs có chủ đích, xem Gradle XML/HTML test reports, và không dùng `--stacktrace` như một thay thế cho test exception chain.
10. Tạo **project Java 17 + Spring Boot 3.3.5** với `TestContextManager` để mô phỏng context khởi tạo lỗi mà **JUnit suite vẫn PASS**.
11. Kiểm được threshold=1, threshold=2, context keys độc lập, successful context reuse và khác biệt property profiles.
12. Phân biệt **context failure threshold**, **cache max size**, **`@DirtiesContext`** và **JUnit retry plugin**.
13. Xử lý đúng các nguồn gốc phổ biến: bean definition, missing property, database connectivity, migrations, credentials, port conflict và incompatible test overrides.
14. Không đưa dữ liệu bí mật trong diagnostic logs hoặc làm CI mất ổn định bằng cách vô hiệu hóa threshold toàn cục.

**Phiên bản ví dụ:** Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Spring TestContext và JUnit Jupiter 5 được Spring Boot dependency management lựa chọn. Ví dụ sử dụng API ổn định trong 6.1: `TestContextManager.getTestContext().getApplicationContext()`, `@ContextConfiguration`, `@TestPropertySource` và `ContextCacheUtils`.

## 2. Phân biệt Spring Boot context loading với test logic

Với một `@SpringBootTest`, trước khi `@Test` thực sự chạy, Spring TestContext phải chuẩn bị `ApplicationContext`:

~~~text
JUnit discovers test classes
        |
        v
SpringExtension / TestContextManager
        |
        v
Build MergedContextConfiguration (context cache key)
        |
        +--- Cache HIT ------> reuse already active ApplicationContext
        |
        +--- Cache MISS
                 |
                 v
          Is failure count for key >= threshold?
                 |
              +--+--+
              |     |
             YES    NO
              |     |
              v     v
         Skip load  Actually create/refresh context
              |     |
              |  +--+------------------+
              |  |                     |
              | SUCCESS               FAILURE
              |  |                     |
              | Cache context        Increment failure count for key
              |                        |
              v                        v
         IllegalStateException     Initial load error + causal chain
~~~

Điểm mấu chốt:

- **Lỗi trước thân `@Test`** có thể xảy ra trong component scan, autoconfiguration, bean init, web server bootstrap, database migration hoặc các `TestExecutionListener`.
- Khi context load thất bại, framework ghi **failure count** cho **context cache key** đó.
- Nếu threshold là **1**, lần kế tiếp cần cùng key sẽ bị **preemptively skipped** (bỏ qua ngay) và ném `IllegalStateException`.
- Spring **không cần thử tạo toàn bộ beans lần nữa**, vì loại lỗi môi trường/config thường không tự biến mất.
- Chỉ test có **key giống nhau** cùng chịu threshold count đó. Key khác có counter riêng.
- Một context load **thành công** được lưu và tái sử dụng; test sau không chịu khởi tạo thất bại nếu cache hit còn hợp lệ.

**Đây là cơ chế Spring TestContext, không phải retry logic của Spring Boot application.** Nó không gửi lại HTTP request, không retry Kafka consumer hoặc JDBC transaction. Lỗi `ApplicationContext failure threshold exceeded` ở test bootstrapping khác hoàn toàn với resilience4j retry/circuit breaker trong business code.

### 2.1. Vì sao lỗi ban đầu xuất hiện ở một test khác?

Ví dụ ba test classes A, B, C cùng cấu hình:

~~~text
Worker 1: Class A --> cache key K --> first load --> FAIL (DB URL invalid)
Worker 1: Class B --> cache key K --> load skipped (threshold 1 exceeded)
Worker 1: Class C --> cache key K --> load skipped (threshold 1 exceeded)
~~~

Nhưng trong một CI chạy parallel hoặc Gradle test order không cố định, **lớp nào chạm cache trước** có thể thay đổi. Một báo cáo test cases sắp xếp theo tên có thể hiển thị Class B đầu tiên mặc dù Class A mới là lớp gây actual bootstrap failure. Vì vậy **tìm log/test report đầu tiên theo thời gian khởi tạo context**, sau đó lần ngược `Caused by`.

Đừng coi `testClass=SomeTest` trong `MergedContextConfiguration` là bằng chứng SomeTest có lỗi business logic. Chuỗi thông tin đó dùng để mô tả configuration được nạp, không phải root exception.

### 2.2. Threshold=1 không có nghĩa “chỉ một test được chạy”

Nếu có các key K1, K2, K3 khác nhau:

~~~text
K1: first attempt FAIL -> subsequent K1 attempts skipped
K2: first attempt FAIL -> subsequent K2 attempts skipped
K3: first attempt SUCCESS -> K3 context cached/reused normally
~~~

Failure count được tính **theo key**, không theo cả JVM và cũng không phải “giới hạn tổng số lỗi của toàn suite”. Nếu có 10 context keys đều sai cấu hình, bạn vẫn có thể thấy 10 actual failed loads, mỗi key một lần. Nếu 100 tests chia sẻ một key đã lỗi, lần đầu thất bại và nhiều lần tiếp theo bị skip.

### 2.3. Context cache key gồm những gì?

Trong Spring Framework 6.1/Spring Boot 3.3, các yếu tố thường đóng góp vào `MergedContextConfiguration`:

| Thành phần | Ví dụ | Tại sao quan trọng |
|---|---|---|
| `classes` | `@ContextConfiguration(classes=...)`, Boot application class | Khác classes có thể thành khác key |
| `locations` | XML/config resource | Khác resource là khác config |
| `contextInitializerClasses` | Custom `ApplicationContextInitializer` | Khác cách init context |
| `contextCustomizers` | Boot test customizers, `@MockBean`, `@DynamicPropertySource` | Bean overrides/dynamic definitions có thể phân biệt keys |
| `contextLoader` | Context loader được chọn | Ảnh hưởng bootstrapping |
| `activeProfiles` | `@ActiveProfiles("test")` vs `"staging"` | Properties/beans khác |
| `propertySourceDescriptors` | Locations từ `@TestPropertySource` | Nguồn properties khác |
| `propertySourceProperties` | `@SpringBootTest(properties="x=1")` | Inline property khác |
| `parent` | Context hierarchy | Parent state và keys liên quan |
| `resourceBasePath` | WebApplicationContext resource path | Web resource khác |

Một test có `@MockBean PaymentGateway` và một test không có mock có thể tạo hai keys; vì thế chúng không nhất thiết chia sẻ failure count. Hai classes dùng **đúng cùng cấu hình** có thể chia sẻ key dù tên lớp khác nhau.

**Đừng tùy tiện đổi properties/profiles chỉ để tránh threshold**. Làm vậy có thể đổi chính nội dung thử nghiệm, tăng số context caches và che lỗi. Muốn thay key thì phải có lý do hợp đồng/config rõ ràng.

## 3. Spring 6.1 failure threshold: giá trị mặc định và cách cấu hình

**Từ Spring Framework 6.1**, `DefaultCacheAwareContextLoaderDelegate` hỗ trợ chính sách:

~~~properties
spring.test.context.failure.threshold=1
~~~

Giá trị **mặc định = 1**. Thuộc tính phải là **số nguyên dương**. Đây là **JVM system property của Spring TestContext** hoặc property thông qua `SpringProperties`; nó **không phải `spring.main.*`** và không nên chỉ đặt như một property runtime trong `application.yml` rồi giả định Spring TestContext đã đọc trước khi context được tạo.

| Giá trị | Hành vi theo từng context key |
|---:|---|
| `1` (mặc định) | Cho **một lần attempt thật**; nếu thất bại, các attempt sau bị skip |
| `2` | Cho **tối đa hai lần attempt thật bị lỗi** trước khi skip |
| `3` | Cho **tối đa ba lần attempt thật** trước khi skip |
| `1000000` | Gần như vô hiệu hóa threshold trong một test suite bình thường; không phải giá trị mặc định được khuyến nghị |

Số `2` **không** có nghĩa Spring tự retry hai lần trong cùng một `getApplicationContext()` call. Nó nghĩa là **nếu có yêu cầu load kế tiếp** cho cùng key và lần trước thất bại, framework vẫn cho một attempt thật nữa cho đến khi threshold đạt. Không có backoff hoặc recovery logic đi kèm.

### 3.1. JVM system property trong Gradle test worker

**Cấu hình rõ ràng trong `build.gradle`:**

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'spring.test.context.failure.threshold', '1'
}
~~~

Đây là nơi thích hợp vì Gradle chạy tests trong JVM worker. Trong dự án hỗ trợ benchmark/troubleshooting, có thể forward giá trị từ Gradle process sang test JVM:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    systemProperty 'spring.test.context.failure.threshold',
            System.getProperty(
                    'spring.test.context.failure.threshold', '1')
}
~~~

Với đoạn **forwarding** thứ hai, lệnh sau mới đi đúng vào test JVM:

~~~bash
./gradlew test -Dspring.test.context.failure.threshold=2
~~~

**Chú ý:** `-Dspring.test.context.failure.threshold=2` là JVM system property phía Gradle. Nếu build script **không forward property vào Test task**, không được tự cho rằng forked test JVM nhận được nó. Một cách khác là đặt trực tiếp `systemProperty` trong Test task hoặc dùng một biến môi trường được build script đọc có chủ đích.

**Không tự thay 1 bằng 1000000 như phương án sửa bug.** Làm vậy khiến mỗi lớp lại thử load một context đã biết lỗi, log có thể dài và CI chậm. Giá trị lớn chỉ là công cụ chẩn đoán ngắn hạn trong môi trường có chủ đích, sau đó phải khôi phục và sửa root cause.

### 3.2. Phạm vi của failure count

Count gắn với **context cache** theo key. Cache mặc định mang tính **static trong test JVM**, nên có thể được dùng lại giữa nhiều lớp Spring tests trong cùng process.

Khi Gradle:
- Chạy `maxParallelForks > 1`: mỗi test worker JVM có cache và counters riêng.
- Dùng `forkEvery`: một JVM mới sẽ không còn counters từ JVM cũ.
- Chạy hai lần `./gradlew test`: các test workers ở hai executions không chia sẻ static Java state.
- Chạy tests ở IDE và Gradle riêng: caches khác nhau.

Một cache key đã thất bại trong JVM A có thể lại được thử lần đầu trong JVM B. Đây không phải threshold policy bị hỏng mà là **phạm vi process khác nhau**.

**Đừng nhầm** `spring.test.context.failure.threshold` với `spring.test.context.cache.maxSize` (cache LRU tối đa mặc định 32). Cái trước điều khiển **failed loads per key**, cái sau điều khiển **số contexts đã load thành công có thể giữ trong cache**. Nâng maxSize không chữa lỗi bean creation; nâng failure threshold không chữa LRU cache misses.

## 4. Phân biệt hai thông báo lỗi một cách cơ học

### 4.1. Lần thất bại thật

Một lần actual load failure có thể chứa:

~~~text
java.lang.IllegalStateException:
Failed to load ApplicationContext for [MergedContextConfiguration@...]
    at org.springframework.test.context.cache.DefaultCacheAwareContextLoaderDelegate.loadContext(...)
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'orderController'
Caused by: org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
Caused by: java.lang.IllegalStateException:
MISSING_PAYMENT_URL: payment.gateway.url is absent in test environment
~~~

Đây là **trace minh họa**, tên beans và line numbers phụ thuộc project. Cách đọc:

1. `Failed to load ApplicationContext` nói **bootstrap context không thành công**.
2. `UnsatisfiedDependencyException` cho biết một bean cần dependency chưa dựng được.
3. `BeanCreationException` chỉ ra `paymentClient` là bean bị lỗi trong chain.
4. `MISSING_PAYMENT_URL` ở phần sâu nhất là **lỗi có thể hành động**.
5. Nếu chain sâu nhất là `ConnectException` hoặc `PSQLException`, root cause có thể nằm ở DB service/port/config chứ không phải Java injection.
6. Đừng vội sửa bean trên cùng trong chain mà chưa xem nguyên nhân sâu hơn.

**Không phải luôn “dòng Caused by cuối cùng” là toàn bộ câu trả lời.** Nếu root là `java.lang.NullPointerException` thiếu thông điệp, bạn vẫn cần đọc các frames/method/bean phía trên. Nhưng đó là điểm bắt đầu hợp lý; trong nhiều trường hợp, deepest meaningful cause chứa cấu hình thiếu hoặc resource unreachable.

### 4.2. Các thông báo lặp sau khi threshold đạt

~~~text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for
[MergedContextConfiguration@...]
~~~

Thông điệp thứ hai **không chứng minh Spring lại thử khởi tạo paymentClient**. Trái lại, chính sách skip được đặt ra để **tránh tạo lại**. Nó có thể không chứa sâu chuỗi `Caused by: ... MISSING_PAYMENT_URL`; vì thế việc chỉ mở stack trace của test cuối cùng có thể khiến bạn không biết cần sửa gì.

**Phân biệt đúng:**
- “Failed to load ApplicationContext”: xem chain và bean/resource thật.
- “Failure threshold exceeded / skipping repeated attempt”: tìm **lần failure đầu** của cùng cache key, đừng sửa skip message.
- “Failed to load ...” xuất hiện cho nhiều keys: có thể có **nhiều nguyên nhân gốc**, không ép cả suite vào một lỗi duy nhất.

### 4.3. Mã hóa một thao tác chẩn đoán dễ lặp

Khi đọc CI log:
1. Ghi lại `MergedContextConfiguration` và các phần `classes`, `activeProfiles`, `propertySourceProperties`, `contextCustomizers` có liên quan.
2. Tìm **những stack traces không có câu skip**.
3. Trong trace ấy tìm `Caused by` sâu nhất kèm tên bean/property/port/file.
4. So sánh keys để nhóm các test failures có cùng nguyên nhân.
5. Fix cấu hình, sau đó chạy **một test representative** rồi **full suite**.
6. Tránh biến log presentation thành một giả định về thứ tự thực thi; HTML report có thể sắp xếp theo test class thay vì thời điểm khởi tạo.

Một lệnh lọc chỉ giúp **định vị** trong log, không thay thế đọc trace đầy đủ:

~~~bash
grep -nE "Failed to load ApplicationContext|failure threshold|Caused by:" build.log
~~~

Lệnh này phù hợp Linux/macOS có `grep`; ở Windows PowerShell dùng `Select-String`. Dù lọc được, cần mở những dòng xung quanh để biết đúng root cause, không chỉ một dòng match.

## 5. Project runnable: Spring Boot 3.3.5, Java 17, JUnit Jupiter

Để học cơ chế mà **không khiến toàn bộ test suite cố ý đỏ**, project sẽ:
- Có một Spring Boot app thật cùng `GreetingService`, 2 `@SpringBootTest` tests chạy bình thường.
- Có một **JUnit class thuần** không annotate `@SpringBootTest` với các nested “probe classes” dùng `@ContextConfiguration`.
- Trong thân test, dùng `TestContextManager` yêu cầu Spring TestContext load các probe contexts.
- Cấu hình probe bean cố ý throw exception chứa marker, nhưng JUnit **`assertThrows`** bắt lỗi đó và kiểm các lần sau có bị skip đúng cách.
- Dùng static counters trong fixture config để phân biệt **actual failed load** với preemptively skipped.
- Dùng một test tạm đổi system property sang threshold=2 rồi restore bằng `finally`, và tắt parallel execution để tránh global-property interference.
- Dùng `@TestPropertySource` cho hai probe types có **cùng config class nhưng khác inline properties**, chứng minh key khác nhau có failure counts riêng.

**Lợi ích:** Các lỗi khởi tạo được tạo **có chủ đích trong sandbox** và được kiểm như dữ liệu, không làm CI báo một test thất bại ngoài dự kiến. Không cần DB, Docker, HTTP server hoặc external service.

### 5.1. Cấu trúc thư mục

~~~text
settings.gradle
build.gradle
src/main/java/demo/threshold/ThresholdDemoApplication.java
src/main/java/demo/threshold/GreetingService.java
src/test/resources/junit-platform.properties
src/test/java/demo/threshold/HealthyBootContextTest.java
src/test/java/demo/threshold/ContextFailureThresholdTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'context-failure-threshold-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Demo asserts threshold=1 except where a method
    // temporarily sets threshold=2 and restores it.
    systemProperty 'spring.test.context.failure.threshold', '1'

    // Cache và failure counters chỉ chia sẻ trong cùng JVM.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Lý do tắt Jupiter parallelism: một demo test tạm đổi **JVM-global system property** `spring.test.context.failure.threshold`, còn các tests tạo Spring context cần đọc giá trị nhất quán. Trong project thực bạn có thể bật parallel tests khi resources/isolation được kiểm soát, nhưng **không nên chia sẻ một mutable system property giữa parallel context loaders**.

**Dependency note:** `spring-boot-starter-test` đã mang `spring-test`/JUnit Jupiter. Không cần tự thêm `spring-test` từ version khác. Đừng trộn `javax.*` packages của Boot 2 với `jakarta.*` của Boot 3. Nguồn code tập trung vào Spring TestContext và không phụ thuộc HTTP starter.

### 5.2. Main class

**src/main/java/demo/threshold/ThresholdDemoApplication.java**

~~~java
package demo.threshold;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ThresholdDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ThresholdDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/threshold/GreetingService.java**

~~~java
package demo.threshold;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, guest";
        }
        return "Hello, " + name;
    }
}
~~~

Service đơn giản để có một **healthy Boot context**; nó không dùng external resources. Nếu `@SpringBootTest` của lớp sau không start được, lỗi thuộc app/test configuration, không phải lỗi môi trường DB từ ví dụ intentionally broken probe.

### 5.3. Hai smoke tests trên context thật, không lỗi

**src/test/java/demo/threshold/HealthyBootContextTest.java**

~~~java
package demo.threshold;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class HealthyBootContextTest {

    @Autowired
    GreetingService greetings;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void healthyContextCanInjectService() {
        assertEquals("Hello, Lan", greetings.greet("Lan"));
        assertSame(greetings, context.getBean(GreetingService.class));
    }

    @Test
    void healthyContextIsUsableForAnotherMethod() {
        assertEquals("Hello, guest", greetings.greet(" "));
        assertTrue(context.isActive());
    }
}
~~~

**Đúng 2 JUnit `@Test`** ở lớp này. Cấu hình `WebEnvironment.NONE` đảm bảo không mở embedded HTTP server. Hai methods cùng class có thể share context; test không assert số context loads tuyệt đối.

**Nhớ:** Lớp `HealthyBootContextTest` được SpringExtension hỗ trợ tự động vì `@SpringBootTest` và inject `ConfigurableApplicationContext` để có API `isActive()`. Các cấu hình probe gây lỗi ở lớp JUnit thuần dùng `@TestConfiguration`, tránh bị component scan thường của `@SpringBootApplication` nạp vào context thật. Lớp chẩn đoán dưới đây là JUnit thuần, dùng `new TestContextManager(...)` **chủ động** để test cơ chế Spring TestContext mà không làm JUnit extension tự động fail trước khi vào `@Test`.

## 6. Test harness: tạo lỗi khởi tạo có chủ đích nhưng JUnit vẫn PASS

**src/test/java/demo/threshold/ContextFailureThresholdTest.java**

~~~java
package demo.threshold;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.cache.ContextCacheUtils;

import static org.junit.jupiter.api.Assertions.*;

class ContextFailureThresholdTest {

    private static final String THRESHOLD =
            "spring.test.context.failure.threshold";

    // Mỗi lần gọi tạo một TestContextManager nhưng cùng
    // context-cache key vẫn chia sẻ static cache của Spring Test.
    private static ApplicationContext load(Class<?> probeClass) {
        return new TestContextManager(probeClass)
                .getTestContext()
                .getApplicationContext();
    }

    private static String causeMessages(Throwable failure) {
        StringBuilder result = new StringBuilder();
        Throwable item = failure;

        while (item != null) {
            result.append(item.getClass().getSimpleName())
                    .append(": ")
                    .append(item.getMessage())
                    .append('\n');
            item = item.getCause();
        }

        return result.toString();
    }

    private static void checkSkipped(IllegalStateException failure,
                                     int expectedThreshold) {
        String message = failure.getMessage();

        assertNotNull(message);
        assertTrue(
                message.contains(
                        "ApplicationContext failure threshold ("
                        + expectedThreshold + ") exceeded"),
                message);

        assertTrue(
                message.contains(
                        "skipping repeated attempt to load context"),
                message);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenAConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenBean() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_A: payment.gateway.url missing");
        }
    }

    @ContextConfiguration(classes = BrokenAConfig.class)
    static class ProbeA {
        // Metadata-only; not a JUnit test class.
    }

    @Test
    void firstFailureKeepsRootCauseSecondAttemptIsSkipped() {
        BrokenAConfig.ATTEMPTS.set(0);

        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeA.class));

        assertTrue(
                causeMessages(first).contains(
                        "ROOT_A: payment.gateway.url missing"));

        IllegalStateException second = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeA.class));

        checkSkipped(second, 1);
        assertEquals(1, BrokenAConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenBConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenBean() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_B: data source cannot connect");
        }
    }

    @ContextConfiguration(classes = BrokenBConfig.class)
    static class ProbeB {
    }

    @Test
    void anotherConfigurationKeyGetsItsOwnFirstAttempt() {
        BrokenBConfig.ATTEMPTS.set(0);

        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeB.class));

        assertTrue(causeMessages(first).contains("ROOT_B:"));
        assertEquals(1, BrokenBConfig.ATTEMPTS.get());

        IllegalStateException next = assertThrows(
                IllegalStateException.class,
                () -> load(ProbeB.class));

        checkSkipped(next, 1);
        assertEquals(1, BrokenBConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class VariantBrokenConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String brokenByVariant(Environment environment) {
            ATTEMPTS.incrementAndGet();

            throw new IllegalArgumentException(
                    "VARIANT_FAILURE:"
                    + environment.getProperty("case.variant"));
        }
    }

    @ContextConfiguration(classes = VariantBrokenConfig.class)
    @TestPropertySource(properties = "case.variant=alpha")
    static class VariantAlphaProbe {
    }

    @ContextConfiguration(classes = VariantBrokenConfig.class)
    @TestPropertySource(properties = "case.variant=beta")
    static class VariantBetaProbe {
    }

    @Test
    void differentInlinePropertiesCreateIndependentCacheKeys() {
        VariantBrokenConfig.ATTEMPTS.set(0);

        IllegalStateException alpha = assertThrows(
                IllegalStateException.class,
                () -> load(VariantAlphaProbe.class));

        IllegalStateException beta = assertThrows(
                IllegalStateException.class,
                () -> load(VariantBetaProbe.class));

        assertTrue(causeMessages(alpha).contains(
                "VARIANT_FAILURE:alpha"));
        assertTrue(causeMessages(beta).contains(
                "VARIANT_FAILURE:beta"));

        // Mỗi property variant có key riêng nên cả hai
        // đều được thử dựng context thật đúng một lần.
        assertEquals(2, VariantBrokenConfig.ATTEMPTS.get());

        IllegalStateException alphaAgain = assertThrows(
                IllegalStateException.class,
                () -> load(VariantAlphaProbe.class));

        checkSkipped(alphaAgain, 1);
        assertEquals(2, VariantBrokenConfig.ATTEMPTS.get());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class HealthyConfig {
        @Bean
        String greetingMarker() {
            return "HELLO_FROM_HEALTHY_CONFIG";
        }
    }

    @ContextConfiguration(classes = HealthyConfig.class)
    static class HealthyProbe {
    }

    @Test
    void successfulContextIsCachedAndReused() {
        ApplicationContext first = load(HealthyProbe.class);
        ApplicationContext second = load(HealthyProbe.class);

        assertSame(first, second);
        assertEquals(
                "HELLO_FROM_HEALTHY_CONFIG",
                first.getBean("greetingMarker", String.class));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class KeyValueConfig {
        @Bean
        String selectedVariant(Environment environment) {
            return environment.getRequiredProperty("case.variant");
        }
    }

    @ContextConfiguration(classes = KeyValueConfig.class)
    @TestPropertySource(properties = "case.variant=one")
    static class KeyOneProbe {
    }

    @ContextConfiguration(classes = KeyValueConfig.class)
    @TestPropertySource(properties = "case.variant=two")
    static class KeyTwoProbe {
    }

    @Test
    void sameBeanConfigurationWithDifferentPropertiesIsNotSameContext() {
        ApplicationContext one = load(KeyOneProbe.class);
        ApplicationContext two = load(KeyTwoProbe.class);

        assertNotSame(one, two);
        assertEquals("one",
                one.getBean("selectedVariant", String.class));
        assertEquals("two",
                two.getBean("selectedVariant", String.class));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BrokenThresholdTwoConfig {
        static final AtomicInteger ATTEMPTS = new AtomicInteger();

        @Bean
        String alwaysFailing() {
            ATTEMPTS.incrementAndGet();
            throw new IllegalStateException(
                    "ROOT_T2: deliberate failure");
        }
    }

    @ContextConfiguration(classes = BrokenThresholdTwoConfig.class)
    static class ThresholdTwoProbe {
    }

    @Test
    void thresholdTwoAllowsTwoActualLoadFailuresThenSkips() {
        String previous = System.getProperty(THRESHOLD);

        BrokenThresholdTwoConfig.ATTEMPTS.set(0);
        System.setProperty(THRESHOLD, "2");

        try {
            IllegalStateException first = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            IllegalStateException second = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            assertTrue(causeMessages(first).contains("ROOT_T2:"));
            assertTrue(causeMessages(second).contains("ROOT_T2:"));
            assertEquals(
                    2,
                    BrokenThresholdTwoConfig.ATTEMPTS.get());

            IllegalStateException third = assertThrows(
                    IllegalStateException.class,
                    () -> load(ThresholdTwoProbe.class));

            checkSkipped(third, 2);
            assertEquals(
                    2,
                    BrokenThresholdTwoConfig.ATTEMPTS.get());
        } finally {
            if (previous == null) {
                System.clearProperty(THRESHOLD);
            } else {
                System.setProperty(THRESHOLD, previous);
            }
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class NestedCauseConfig {
        @Bean
        String nestedFailure() {
            IllegalArgumentException database =
                    new IllegalArgumentException(
                            "ROOT_NESTED: database port is invalid");

            throw new IllegalStateException(
                    "Service initialization failed",
                    database);
        }
    }

    @ContextConfiguration(classes = NestedCauseConfig.class)
    static class NestedCauseProbe {
    }

    @Test
    void rootCauseMayBeDeeperThanBeanCreationException() {
        IllegalStateException first = assertThrows(
                IllegalStateException.class,
                () -> load(NestedCauseProbe.class));

        String chain = causeMessages(first);

        assertTrue(chain.contains(
                "Service initialization failed"));
        assertTrue(chain.contains(
                "ROOT_NESTED: database port is invalid"));

        Throwable deepest = first;

        while (deepest.getCause() != null) {
            deepest = deepest.getCause();
        }

        assertInstanceOf(
                IllegalArgumentException.class, deepest);
    }

    @Test
    void configuredDefaultThresholdIsOneInThisTestWorker() {
        // build.gradle passes the JVM property to Test worker.
        assertEquals(
                "1",
                System.getProperty(THRESHOLD));

        assertEquals(
                1, ContextCacheUtils.retrieveContextFailureThreshold());
    }
}
~~~

**Đếm chính xác:** Lớp `ContextFailureThresholdTest` chứa **8 `@Test`**; lớp `HealthyBootContextTest` có **2 `@Test`**. Tổng toàn project **10 JUnit Jupiter test methods**. Các nested classes `ProbeA`, `ProbeB`, `VariantAlphaProbe`, ... **không có `@Test`** và không được JUnit phát hiện như test classes độc lập; chúng chỉ cung cấp metadata cho `TestContextManager`.

**Vì sao tất cả có thể PASS dù bean cố ý throw?** Trong JUnit test method, `assertThrows(IllegalStateException.class, () -> load(...))` **mong đợi** exception từ `TestContextManager`. Phép kiểm PASS nếu Spring thực sự ném exception đúng lúc, không nếu bean load bình thường. Về mặt ứng dụng, nested probe configurations là **test-only failures**, không được `@Import` vào Boot main context.

**Vì sao phải gắn tên marker?** `ROOT_A`, `ROOT_B`, `VARIANT_FAILURE`, `ROOT_T2` và `ROOT_NESTED` giúp phân biệt root exception khỏi `Failed to load ApplicationContext` ở wrapper. Trong hệ thống thật, exception message có thể chứa JDBC URL hoặc credentials; **không đưa password/token thực vào test fixtures hoặc công khai toàn bộ log**.

### 6.1. Các assertions phản ánh điều gì?

| JUnit test | Điều được chứng minh |
|---|---|
| `firstFailureKeepsRootCauseSecondAttemptIsSkipped` | Threshold mặc định 1: attempt đầu ném root marker; attempt thứ hai bị skip; bean init count vẫn 1 |
| `anotherConfigurationKeyGetsItsOwnFirstAttempt` | Một key khác có lần failure đầu riêng và bị skip lần sau |
| `differentInlinePropertiesCreateIndependentCacheKeys` | Hai `@TestPropertySource` khác nhau -> hai attempts thật; retry của alpha bị skip |
| `successfulContextIsCachedAndReused` | Context thành công được cache và là cùng instance |
| `sameBeanConfigurationWithDifferentPropertiesIsNotSameContext` | Ngay cả cùng @Configuration class, properties khác khiến contexts khác |
| `thresholdTwoAllowsTwoActualLoadFailuresThenSkips` | Khi threshold 2: hai actual failures, lần thứ ba skip |
| `rootCauseMayBeDeeperThanBeanCreationException` | Root chain có wrapper và deeper `IllegalArgumentException` thật |
| `configuredDefaultThresholdIsOneInThisTestWorker` | Gradle đã truyền system property 1 vào test worker |

Với `@SpringBootTest` tests thực, lỗi xảy ra **trước thân test** nên JUnit đánh dấu failure. Với harness JUnit thuần, ta kiểm tra Spring behavior trong thân test, vì thế suite vẫn xanh. Hai mô hình không mâu thuẫn; chúng đứng ở hai cấp kiểm thử khác nhau.

### 6.2. Không tự dùng `ApplicationContext.getId()` để suy ra cache hit

Trong `successfulContextIsCachedAndReused`, `assertSame(first,second)` kiểm **đúng cùng instance**, chứ không so `getId()` (hai context khác nhau có thể được đặt cùng string id). Với các keys khác nhau, `assertNotSame(one,two)` xác minh instances khác; các bean property values cũng được kiểm.

Trong `BrokenAConfig.ATTEMPTS`, counter là **static** của test fixture, tồn tại qua context attempts trong JVM. Nếu Spring không thực sự thử dựng bean lần thứ hai, counter vẫn 1. Static counter **không được Spring context cache tự động reset**; project chỉ reset nó ở đầu method sử dụng key đó và giữ JUnit tests tuần tự.

### 6.3. Vì sao không sử dụng một `@SpringBootTest` cố ý lỗi?

Nếu viết:

~~~java
@SpringBootTest(properties = "payment.gateway.url=")
class IntentionallyBrokenBootTest {
    @Test
    void mustNotStart() {
        // This body is never reached when context fails to start.
    }
}
~~~

Đây là snippet **không thuộc project runnable** và chưa định nghĩa bean nào cần property nên chỉ minh họa rủi ro thiết kế. Nếu context khởi tạo lỗi thật, JUnit thường **không vào được thân test** để assert exception. Một `@Test` chỉ có `assertThrows` trong thân test không thể bắt lỗi xảy ra ở **test instance preparation** trước đó.

Muốn test Spring TestContext failure policy như một API, sử dụng `TestContextManager` bên trong một plain JUnit test, như ví dụ chính. Nếu muốn test startup failure của cả Boot app, dùng một harness riêng hoặc `ApplicationContextRunner` để assert root failure, nhưng **`ApplicationContextRunner` đơn lẻ không chứng minh Spring TestContext failure threshold**, vì nó không chạy qua cùng context cache policy.

## 7. Lệnh chạy, báo cáo Gradle và kết quả kỳ vọng

Project yêu cầu JDK 17, Gradle tương thích với plugin Spring Boot 3.3.5 và quyền tải dependencies từ Maven Central nếu cache chưa có. Không yêu cầu Docker, database, network HTTP hoặc SMTP.

Nếu đã tạo Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu mới chỉ tạo các file bên trên nhưng **chưa tạo `gradlew`, `gradlew.bat` và wrapper JAR**, `./gradlew` chưa chạy được. Dùng Gradle đã cài để tạo Wrapper, hoặc chạy:

~~~bash
gradle test
~~~

Chạy riêng các lớp:

~~~bash
./gradlew test --tests demo.threshold.HealthyBootContextTest
./gradlew test --tests demo.threshold.ContextFailureThresholdTest
~~~

Để chắc chắn Gradle không trả kết quả `UP-TO-DATE` mà bỏ qua một execution mới trong lúc chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Báo cáo:
- HTML: `build/reports/tests/test/index.html`.
- JUnit XML: `build/test-results/test/TEST-*.xml`.
- Stdout/stack trace có thể bị Gradle thu thập và hiển thị trong HTML/XML tùy test logging config.
- Log đầu tiên chứa `ROOT_A` thường đi kèm việc khởi tạo config bị lỗi, nhưng **thứ tự log/report các test không được dùng làm contract**.

**Kết quả dự kiến theo source và Spring 6.1 API:** **10 JUnit test methods được thiết kế PASS**, trong khi một số deliberate context attempts bên trong tests ném exceptions và được `assertThrows` bắt. Đây là kỳ vọng kỹ thuật từ code; **không phải tuyên bố đã chạy Gradle trong môi trường người đọc**. Framework/Gradle logging có thể hiện stack traces của các probe loads, vì chúng là test inputs dự kiến chứ không phải test failures ngoài ý muốn.

**Nếu test threshold 2 không đạt:** Đầu tiên kiểm `junit-platform.properties` đã tắt parallelism và `systemProperty` 1 đã được Gradle chuyển vào worker. Trong method, property được đổi tạm thành `"2"` trước khi `TestContextManager` đầu tiên cho `ThresholdTwoProbe` được tạo, và được restore trong `finally`. Lúc đó mỗi new TestContextManager có thể đọc threshold 2. Không nên có các tests bên ngoài cùng chạy sửa `spring.test.context.failure.threshold` trong JVM.

## 8. Điều tra lỗi thật theo trình tự đáng tin

### 8.1. Bắt đầu bằng một failure có đầy đủ cause chain

1. Chạy một **representative test class** bị lỗi để giảm nhiễu:
   `./gradlew test --tests com.example.OrderRepositoryTest --rerun-tasks`.
2. Nếu nó có cùng context key như các lớp đang lỗi, một run riêng thường khiến nó trở thành **first attempted load** trong test JVM mới; vì thế root cause hiển lộ thay vì skip.
3. Đọc JUnit XML/HTML report và full stack trace, không chỉ màn hình tổng `> Task :test FAILED`.
4. Tìm `Failed to load ApplicationContext` và các `Caused by` ở dưới.
5. Đọc bean name, property key, resource path, host/port, active profile và nested exception.
6. Kiểm với config thật: `@ActiveProfiles`, `@SpringBootTest(properties)`, `@MockBean`, `@DynamicPropertySource`.
7. Sửa root issue, rerun representative test.
8. Chạy suite đầy đủ và kiểm không có key khác vẫn failing.
9. Không tăng threshold chỉ để làm biến mất chuỗi “skipping repeated attempt”.

**Chạy riêng một lớp có thể thay đổi context key hoặc làm mất chứng cứ cross-class interference**, vì thế nếu lỗi chỉ xuất hiện khi chạy toàn suite hãy giữ full run logs, so sánh configurations và thứ tự test executions thay vì cho rằng bug đã biến mất. Lỗi do test pollution hay shared singleton có thể bị che khi chạy isolated.

### 8.2. Phân loại nguyên nhân từ root exception

| Root exception | Nguyên nhân khả dĩ | Kiểm tra tiếp |
|---|---|---|
| `NoSuchBeanDefinitionException` | Bean không được scan/import, profile loại bean, mock override sai | Component scan, `@Import`, `@Profile`, test slice |
| `NoUniqueBeanDefinitionException` | Nhiều beans cùng type nhưng không có qualifier | `@Primary`, `@Qualifier`, named beans |
| `UnsatisfiedDependencyException` | Dependency chain không dựng được | Xem tiếp `Caused by` sâu hơn |
| `BeanCreationException` | `@Bean`/constructor/`@PostConstruct` throw | Xem bean name, init method và nested cause |
| `BindException`/configuration bind errors | Property thiếu/sai kiểu/validation | Test profile, env vars, binding prefix |
| `IllegalArgumentException: Could not resolve placeholder` | Missing property | Key gốc, Spring config, env-specific property |
| `PSQLException`, `ConnectException` | DB hostname/port/credentials/network sai | Container readiness, DB URL, firewall |
| `FlywayException`/Liquibase exception | Migration thất bại | SQL scripts, schema permissions, version |
| `BindException: Address already in use` | Port cố định đang bị chiếm | Random port, resource lifecycle |
| Jackson/validation/linkage errors | Thiếu dependency hoặc version conflict | Dependency tree, Boot BOM, Jakarta APIs |
| Security config startup failure | Missing keystore/cert/credential | Test security profile, secrets mapping |
| TLS/SSL handshake exceptions | Truststore/cert không hợp | TLS config/test server |
| `OutOfMemoryError` hoặc resource exhaustion | JVM/container memory, nhiều contexts | Heap, cache size, test forks, lifecycle |

**Đây là bảng gợi ý chẩn đoán, không phải phép chứng minh.** Một `BeanCreationException` có thể do DB connection timeout, và một `IllegalStateException` có thể chỉ là wrapper. Phải đọc cause chain cụ thể và quan hệ dependency mới chọn được fix.

### 8.3. Phân biệt fault của ứng dụng và fault của test environment

Một test `@SpringBootTest` có thể fail vì:
- Sai cấu hình **trong source test**: `@MockBean` thiếu generic, profile sai, class test nằm ngoài package scan, `@DynamicPropertySource` trả port của container chưa start.
- Sai cấu hình **ứng dụng thật**: missing `@ConfigurationProperties`, circular dependency, invalid bean name, migration fail.
- Hạ tầng **test-only**: PostgreSQL container chưa ready, external API stub chưa start, Docker socket unavailable, cổng localhost bị chiếm.
- Khác phiên bản/thư viện: `javax.*` vs `jakarta.*` khi nâng Boot 2→3, driver và Hibernate mismatches.
- Tài nguyên **bị test trước làm nhiễm**: static state, global properties, shared cached context, incomplete cleanup.

Mỗi nhóm cần fix ở nơi sở hữu state. Context failure threshold chỉ báo rằng các lần load trùng key không được thử lại nữa; nó **không phân loại** nguyên nhân.

## 9. Tại sao `@DirtiesContext` không phải cách xử lý mặc định?

`@DirtiesContext` yêu cầu Spring **evict và đóng context** đang cache. Nó phù hợp khi một test đã **làm bẩn một context thành công**, ví dụ biến đổi singleton/configuration không thể reset an toàn.

Nhưng nếu một context **chưa bao giờ load thành công** do thiếu datasource property:
- Không có context usable để đơn giản “reset state”.
- Việc dirty không bổ sung URL còn thiếu hay fix bean.
- Cố recreate một context chắc chắn sai có thể tốn thời gian và tạo log dài.
- Với external PostgreSQL/Kafka, đóng context còn không nhất thiết reset dữ liệu/resource ngoài JVM.

**Không kết luận `@DirtiesContext` sẽ reset failure count của một key.** Trong Spring 6.1 cơ chế count nằm trong ContextCache; bất kỳ hiệu ứng nào của eviction cần được hiểu theo implementation và version. Không dùng annotation này làm công cụ “reset threshold” nếu mục tiêu là chẩn đoán root cause.

### 9.1. Một ví dụ sai

~~~java
@SpringBootTest
@DirtiesContext
class OrderIntegrationTest {
    // Nếu DataSource không kết nối được, context vẫn lỗi.
}
~~~

Đây là snippet minh họa (không thuộc project runnable). Việc thêm annotation có thể che một vấn đề khác hoặc làm build chậm, nhưng không thể sửa DB URL sai. Cần tìm root exception.

### 9.2. Một ví dụ hợp lệ

Nếu test mutate Spring-managed state khiến test sau nhận bean bị nhiễm và không có reset an toàn, `@DirtiesContext(methodMode=AFTER_METHOD)` có thể cô lập context sau một method. Tuy nhiên **đó là bài toán state sau startup thành công**, khác với **context loading failure threshold**. Cần tách hai nguyên nhân để tránh chọn sai công cụ.

## 10. Failure threshold không phải cache-size, retry hoặc circuit breaker

| Khái niệm | Tham số/chức năng | Đối tượng |
|---|---|---|
| **Failure threshold** | `spring.test.context.failure.threshold`, mặc định 1 | Số lần load context thật bị lỗi được phép cho **cùng key** trước khi skip |
| **Context cache size** | `spring.test.context.cache.maxSize`, mặc định 32 | Số contexts loaded thành công giữ trong LRU cache |
| **`@DirtiesContext`** | BEFORE/AFTER method/class phases | Evict/close context khi bị làm bẩn |
| **JUnit retries/flaky test reruns** | Tool/plugin tùy dự án | Chạy lại test method/task theo policy |
| **Spring Retry/Resilience4j** | Retry HTTP/DB/business operations | Hành vi ứng dụng, không phải TestContext bootstrap |
| **Testcontainers readiness** | Wait strategy/startup attempts | External container lifecycle |
| **Gradle forks** | `maxParallelForks`, `forkEvery` | JVM test workers và cache isolation |
| **Spring Boot startup logging** | DEBUG/TRACE/test reports | Observability của từng actual load |

**Threshold=1 không phải “chỉ có 1 lỗi hợp lệ trong toàn suite”.** Nó là cơ chế chống một chuỗi failed loads **cho mỗi context configuration**. Tương tự, “đổi `cache.maxSize` thành 64” không làm lỗi `NoSuchBeanDefinitionException` biến mất.

### 10.1. Một ví dụ về suite có hai root causes

~~~text
Group K1 (profile=test, mock PaymentGateway):
  actual failure: missing paymentClient bean
  12 subsequent skips

Group K2 (profile=integration, Testcontainers PostgreSQL):
  actual failure: DB connection refused
  8 subsequent skips

Group K3 (unit slice with mocked repository):
  loads successfully and tests run
~~~

Nếu chỉ tìm chuỗi `failure threshold exceeded` và nghĩ toàn bộ có một nguyên nhân, bạn sẽ sửa K1 rồi ngạc nhiên vì K2 vẫn fail. **Phân nhóm theo key trước, điều tra root cause của từng nhóm sau.**

## 11. Context key pitfalls đặc biệt trong Spring Boot testing

### 11.1. `@ActiveProfiles`

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
    // Context key chứa active profile "test".
}
~~~

Nếu lớp khác không khai báo `@ActiveProfiles("test")`, chúng có thể dùng key khác, và một test chỉ lỗi ở profile `test` vì datasource URL được lấy từ file tương ứng. Mỗi key có threshold counter riêng.

**Đừng đổi `@ActiveProfiles` chỉ để chạy xanh.** Profile là điều kiện kiểm thử; đổi nó có thể chuyển test sang môi trường khác không đại diện cho bài toán cần kiểm.

### 11.2. `@SpringBootTest(properties=...)`

~~~java
@SpringBootTest(
        properties = "feature.mail.enabled=false")
class MailDisabledTest {
}
~~~

Inline property được đưa vào merged configuration. Nếu một lớp khác dùng `feature.mail.enabled=true`, context key có thể khác; startup của cả hai có thể khác theo conditional beans. Nếu property chỉ cần đổi ở mức method, cân nhắc đơn vị test context/fixture phù hợp, đừng giả định `System.setProperty` sau startup sẽ reconfigure đã-created beans.

### 11.3. `@MockBean` và `@TestConfiguration`

Spring Boot 3.3 `@MockBean`/`@SpyBean` đi vào test context customizers, có thể khiến hai lớp khác mocks **không chia sẻ context**, dù cùng `@SpringBootTest`. Nếu test startup fail chỉ ở mock setup sai, mọi class có cùng overrides sẽ chịu threshold tương ứng.

**Unit test thuần** không cần `@SpringBootTest` để tạo mock. Với logic không phụ thuộc Spring wiring, dùng JUnit + Mockito giúp tránh context startup, cache key và failure threshold hoàn toàn. Ngược lại, kiểm autoconfiguration/bean graph thì `@SpringBootTest` có ý nghĩa.

### 11.4. `@DynamicPropertySource` và Testcontainers

~~~java
@DynamicPropertySource
static void db(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            () -> postgres.getJdbcUrl());
}
~~~

Snippet trên giả định có static `postgres` container đã start; không thuộc project runnable ở mục 5. Spring TestContext có thể dùng metadata của `@DynamicPropertySource` để phân biệt config keys, **không nhất thiết** lấy mỗi runtime port mới làm một key. Nếu test class kế tiếp reuse context nhưng container trước đã stop, connection pool vẫn trỏ port cũ có thể gây lỗi. Đây là **resource/context lifecycle mismatch**, cần align scope hoặc tách contexts phù hợp, không sửa bằng tăng threshold.

**Testcontainers cũng có readiness wait strategy**: một container chưa sẵn sàng là root lỗi hạ tầng. Failure threshold chỉ tránh Spring dựng lại context với DB chưa kết nối được; nó không khởi động lại container.

## 12. Giới hạn của việc chạy lại test để tìm lỗi

Trong một số trường hợp, chạy lại **một test class** trong JVM mới sẽ khiến actual load failure xuất hiện đầu tiên và dễ đọc. Nhưng có ít nhất bốn rủi ro:

1. **Order-dependent pollution:** Test A để lại global state làm B fail. Khi chạy B riêng, lỗi không tái hiện. Khi đó cần xem full-suite execution order.
2. **External resource race:** Cổng/broker/database bị dùng đồng thời chỉ trong CI parallel. Chạy riêng tránh cạnh tranh nên xanh.
3. **Different context key:** Chạy standalone có thể không bao gồm cùng test customizers/environment của suite hay test platform; phải giữ annotation/config tương đương.
4. **Gradle cached test results:** Task UP-TO-DATE có thể không thực thi, cần `--rerun-tasks` khi cần xác nhận.

**Lời khuyên:** Lưu artefacts của **lần CI lỗi đầu tiên** gồm XML test results, complete logs và test environment metadata; không chỉ lưu màn hình tổng kết. Sau khi trích root cause, tạo một reproduction nhỏ nhất **nhưng vẫn giữ điều kiện gây lỗi**.

### 12.1. Log mức nào hữu ích?

- `org.springframework.test.context.cache` ở DEBUG: cache size/hit/miss/failure statistics; hỗ trợ nhóm keys và phát hiện context churn.
- `org.springframework.test.context` hoặc `org.springframework.beans.factory.support` ở DEBUG: context/test listener/bean lifecycle; dùng có chọn lọc vì có thể rất nhiều log.
- `org.springframework.boot.autoconfigure.condition` và `--debug`/Condition Evaluation Report: hữu ích khi `@Conditional`/auto-configuration không tạo bean mà bạn tưởng phải có.
- `org.testcontainers` ở INFO/DEBUG: container startup/readiness; chỉ bật nếu thật sự dùng containers.
- JDBC/migration logs: chỉ bật chi tiết sau khi xác định nguồn vấn đề thuộc DB; che/mask credentials.

**Không bật TRACE cho toàn bộ Spring/HTTP clients vô điều kiện trên CI**, vì logs có thể chứa secrets, PII, header values và tạo dung lượng lớn. Bắt đầu từ error cause chain, sau đó mở rộng logger đúng package.

### 12.2. Gradle `--stacktrace` có ý nghĩa gì?

`./gradlew test --stacktrace` thường hiển thị **Gradle task failure stack**, ví dụ `There were failing tests. See report at ...`. Stack trace đó giúp hiểu task failed nhưng **không nhất thiết** hiển thị đầy đủ exception của Spring test class. Để thấy root:
- Mở test report HTML/XML.
- Cấu hình Gradle test logging cho failed tests / full exception format nếu cần.
- Dùng `--info` hoặc phù hợp để có thêm diagnostic logs; không cho rằng `--debug` là bắt buộc.
- Lấy stderr/stdout gốc khi CI gom logs.

**Ví dụ cấu hình logging cho giai đoạn chẩn đoán:**

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'failed'
        exceptionFormat = 'full'
        showCauses = true
        showStackTraces = true
    }
}
~~~

Đây là snippet cấu hình Gradle bổ sung; trong demo runnable trước đó `testLogging` chỉ khai event list gọn, còn người học có thể đổi sang full logging để chẩn đoán. Không dùng output có line number cụ thể làm expected stdout vì phụ thuộc Gradle/Spring/JDK version.

## 13. Quy trình điều tra tại CI khi có hàng loạt failure-threshold messages

**Bước 1.** Đảm bảo đang xem **cùng một CI run**. Đừng ghép stack traces từ hai executions khác profiles/forks.

**Bước 2.** Tìm những traces chứa `Failed to load ApplicationContext` và `Caused by`. Nếu chỉ thấy `failure threshold exceeded`, xem cả log/test XML hoặc chạy lại một representative key trong **JVM mới** để thu nguyên nhân thật.

**Bước 3.** Phân nhóm theo merged configuration:
- `classes`/Spring Boot main application.
- `activeProfiles`.
- `propertySourceProperties` và dynamic customizers.
- Mock overrides/test slice/context loader.
- Parent context nếu có hierarchy.

**Bước 4.** Từ actual load failure, lấy **root cause + action**:
- `Could not resolve placeholder`: property nào?
- `Connection refused`: host/port nào, container đã ready chưa?
- `NoSuchBeanDefinition`: thiếu component scan/import hay active profile?
- `BeanCurrentlyInCreation`/circular dependency: chuỗi beans nào?
- Liquibase/Flyway migration failure: statement/schema/permissions?
- `BindException: Address already in use`: fixed port do ai giữ?

**Bước 5.** Kiểm thứ tự startup của external resources, test profile, Gradle JVM properties, CI secrets mapping, Spring Security/SSL config, datasource URLs. Không log secret values để chứng minh config.

**Bước 6.** Sửa nguyên nhân; chạy representative test; chạy tiếp toàn suite ở cùng configuration, đặc biệt nếu phát hiện nhiều keys.

**Bước 7.** Nếu lỗi chỉ xảy ra parallel, tách shared external resources, dùng `@ResourceLock`/`@Isolated` chỉ khi scope phù hợp, không thay failure threshold thành một mutex.

**Bước 8.** Sau khi toàn suite pass, giữ threshold mặc định và ghi regression test/fixture guardrail phù hợp để lỗi không tái xuất hiện.

### 13.1. Những điều không nên làm

- Không nâng `spring.test.context.failure.threshold=1000000` vĩnh viễn vì “test report hết thông báo skip”; thực tế sẽ tạo nhiều bootstrap errors hơn.
- Không thêm `@DirtiesContext` cho mọi lớp không load được.
- Không sửa đồng loạt expected assertions của tests khi thân `@Test` chưa từng chạy.
- Không gán root cause cho test class đứng đầu XML report theo thứ tự chữ cái.
- Không đổi profile/`@MockBean` để chuyển sang context không đại diện cho test cần chạy.
- Không bật Spring DEBUG cho toàn bộ CI trong thời gian dài nếu có nguy cơ lộ secrets.
- Không cố xóa bộ nhớ/cache trong test JVM đang có tests khác dùng contexts mà không xem thread safety.
- Không dùng Gradle `--offline` nếu dependencies chưa có; khi đó lỗi dependency resolution không đồng nghĩa Spring ApplicationContext bootstrap failure.
- Không nói “một test fail = cả app fail” nếu các failures ở nhiều test keys, slices hoặc external resources khác nhau.

## 14. Các trường hợp khó: lỗi lặp trông giống root nhưng không phải

### 14.1. `BeanCreationException` xuất hiện ở nhiều contexts

Nếu Boot có ba slices `@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest`, chúng thường có keys khác nhau. Cùng `BeanCreationException` ở mỗi slice **có thể** do một common test `@Configuration` sai hoặc ba bean graphs riêng. Đừng khẳng định một context failure count được chia sẻ xuyên ba slices.

### 14.2. Context load đầu tiên thành công rồi bean hỏng khi test chạy

Failure threshold chỉ theo dõi **context loading**. Nếu context khởi tạo thành công nhưng `@Test` ném `NullPointerException`, đó **không phải context load failure** nên không tạo skip cho cùng key. Nếu có listener sau startup ném exception ở test phase khác, cần xác định lỗi xảy ra trong lifecycle nào.

### 14.3. External resource tạm hồi phục sau failure

Threshold=1 có thể làm bạn phải chạy một test execution mới khi resource khôi phục, vì key đã ghi nhận failed load trong JVM hiện tại. Đó là **trade-off có chủ đích**: giảm wasted retries, đổi lại không tự động retry context load cho cùng key khi điều kiện ngoài thay đổi giữa các tests.

Giải pháp ổn định không phải liên tục tăng threshold; hãy chuẩn bị resource **trước** khi Spring context được dựng bằng readiness/wait strategy, lifecycle đúng và thời gian chờ hợp lý.

### 14.4. Parallel tests và logs không có thứ tự trực quan

Nếu Jupiter/Gradle chạy nhiều worker JVM, thông báo đầu tiên **trong file log tổng hợp** có thể không tương ứng với lần đầu theo từng key/worker. Cần gắn timestamp, test worker, test class và config grouping nếu logs đủ thông tin. Context cache static trong một JVM; mỗi JVM có failure counts riêng.

### 14.5. Failure count không phải số lần bean constructor gọi

Một actual context attempt có thể gọi **nhiều beans**, bean init có thể có retries nội bộ hoặc exception trong một `BeanFactoryPostProcessor` trước khi một bean dự kiến được tạo. **Bean constructor count** trong demo chỉ là instrumentation cho một bean được thiết kế luôn fail đúng tại init. Trong production, số lượng constructor calls không thể thay cho Spring cache failure metrics.

## 15. Phân biệt root-cause visibility với hành vi framework

Một lần failure đầu có thể được log nhiều lần do:
- Spring's context loader log exception.
- JUnit báo test preparation failure.
- Gradle test task thu lại stderr.
- CI uploader/summarizer đăng cùng error excerpt.

Đây là **nhiều bản sao log của một actual failed load**, không nhất thiết có nhiều attempts. Ngược lại, một `failure threshold exceeded` message là **một lỗi test node riêng** (một attempt bị bỏ qua), nhưng không tự tạo lại bean lỗi.

Khi báo cáo sự cố, nên tách các metrics:

| Đại lượng | Ý nghĩa |
|---|---|
| Số test cases failed | Có bao nhiêu tests không chạy/xong đúng |
| Số context keys failing | Có bao nhiêu cấu hình khác nhau |
| Số actual failed context loads | Bao nhiêu lần loader thật sự cố khởi tạo rồi lỗi |
| Số preemptive skips | Bao nhiêu tests bị threshold ngăn nạp lại |
| Số root causes thực tế | Có thể ít hơn hoặc bằng số keys; cần phân tích |
| Số log messages | Không phải số attempts, vì logs có thể bị sao chép |

Báo cáo “30 tests đỏ” mà không nêu chúng cùng lỗi cấu hình test datasource sẽ khiến người đọc đánh giá sai phạm vi. Một báo cáo tốt sẽ là: “1 root cause: DB test URL sai; context key có 1 actual load failure và 29 skipped attempts; đã sửa property, representative test và suite đã pass” — **chỉ sử dụng các con số đó khi được đo từ run thật**, không dựa ví dụ minh họa.

## 16. Giải thích kỹ hơn `TestContextManager` harness

Trong mã ví dụ, `load(...)` làm việc sau:

~~~java
new TestContextManager(probeClass)
        .getTestContext()
        .getApplicationContext();
~~~

**Tầng 1:** `TestContextManager` đọc annotations test class: `@ContextConfiguration`, `@TestPropertySource` và các metadata khác.

**Tầng 2:** Nó xây `TestContext` với `MergedContextConfiguration` tương ứng và `CacheAwareContextLoaderDelegate`.

**Tầng 3:** Khi `getApplicationContext()` được gọi, framework tìm cache entry hoặc kiểm **failure count/threshold** trước khi nạp context.

**Tầng 4:** Nếu load fail, exception được truyền ra và JUnit `assertThrows` bắt lại. Nếu cùng key đã đạt threshold, delegate trả lỗi “skipping repeated attempt” **trước khi chạy bean init**.

**Tầng 5:** Nhờ count `AtomicInteger` trong `BrokenAConfig`, ta thấy lần hai không gọi bean factory method nữa. Đây là quan sát **thực chất**, không suy đoán từ chuỗi thông báo alone.

**Vì sao không khai báo `@ExtendWith(SpringExtension.class)` cho probe?** Các nested probe types không có JUnit tests. Chúng là **metadata-only classes**, và harness chủ động tạo manager. Nếu gắn SpringExtension trực tiếp vào một `@Test` class bị broken context, Spring sẽ thử load trước khi phương thức kiểm chạy, khiến bạn không thể dùng `assertThrows` trong thân test để điều tra.

**Vì sao set `spring.test.context.failure.threshold=1` trong Gradle?** Để project reproduction độc lập với hệ thống của người học vốn có thể cấu hình threshold khác. Trong production project, có thể bỏ explicit property để dùng default. Test `configuredDefaultThresholdIsOneInThisTestWorker` chỉ chứng minh **worker property là 1**, không chứng minh Spring Framework ở mọi phiên bản đều có default đó; Spring 6.1 docs là nguồn cho default semantics.

**Vì sao tạm đổi threshold ở test thứ sáu?** Để minh họa `2` là hai **actual failed load attempts ở hai lời gọi khác nhau**, chứ không phải `getApplicationContext()` tự retry hai lần. Test restore system property trong `finally` và toàn test suite chạy tuần tự. Đây là reproduction technique, không phải khuyến nghị bật đổi JVM globals tùy tiện trong ứng dụng.

## 17. Bài tập thực hành

**Bài 1 — Đọc exception đúng tầng.** Cho trace gồm `Failed to load ApplicationContext` → `UnsatisfiedDependencyException` → `BeanCreationException` → `IllegalArgumentException("payment.gateway.url missing")`. Chỉ ra root cause và bean bị ảnh hưởng.

**Bài 2 — Default threshold.** Với 5 classes cùng key K và threshold 1, nếu lần đầu load fail, có bao nhiêu actual failed attempts? Bao nhiêu lần bị skip? (Giả sử tất cả năm đều cần context, không dùng JVM forks.)

**Bài 3 — Threshold=2.** Với cùng key K, ba lời gọi load đều thất bại nếu thực hiện thật; cái nào actual? Cái nào skipped? Giải thích dựa trên counters.

**Bài 4 — Cache keys.** Hai classes có cùng config class nhưng một có `@TestPropertySource(properties="case.variant=alpha")`, lớp còn lại `beta`. Tại sao failure counts độc lập?

**Bài 5 — Healthy context reuse.** Dùng `assertSame` để kiểm hai load của cùng successful key trả đúng một context instance. Vì sao `getId()` không phải bằng chứng đủ?

**Bài 6 — CI report.** Lấy một Gradle `TEST-*.xml` của một project lỗi thật, nhóm các failures theo context key và root cause. Không log dữ liệu nhạy cảm.

**Bài 7 — Gradle worker.** Đổi property trong `application.properties` nhưng không đổi JVM test worker `spring.test.context.failure.threshold`. Vì sao threshold behavior có thể không thay?

**Bài 8 — Gradle CLI forwarding.** Thiết kế `build.gradle` cho phép `./gradlew test -Dspring.test.context.failure.threshold=2` được chuyển đúng vào Test task. Kiểm từ test worker.

**Bài 9 — Disabled threshold.** Thử giá trị lớn 1000000 trong sandbox với intentionally broken bean. Những gì xảy ra với số actual attempts/log/runtime? Tại sao không giữ giá trị này trong CI?

**Bài 10 — Multiple JVM forks.** Chạy hai Gradle forks với cùng failing application configuration. Vì sao có thể có **hai** root context attempts thay vì một trên toàn máy?

**Bài 11 — Testcontainers readiness.** Mô phỏng database container start chậm, context load trước khi DB ready. Thay threshold hay wait strategy mới là fix bền vững?

**Bài 12 — `@DirtiesContext`.** Một context không load nổi do thiếu property. Vì sao dirty không phải cách sửa phù hợp? Nếu context load xong nhưng singleton bị biến dạng thì sao?

**Bài 13 — Missing bean.** `NoSuchBeanDefinitionException` xuất hiện dưới `UnsatisfiedDependencyException`. Tìm root bean dependency path, `@Profile` và component scan.

**Bài 14 — Multiple keys.** WebMvcTest chạy được, DataJpaTest không start, SpringBootTest cũng fail do datasource. Vì sao không thể suy một global failure count cho cả ba?

**Bài 15 — Broken mock override.** Tạm bỏ `@MockBean` trong một test class và xem cache key thay đổi. Đừng kết luận test đã sửa chỉ vì class giờ khởi động được với graph khác.

**Bài 16 — Async contamination.** Một test sửa system property rồi restore muộn, làm context load của lớp khác fail. Viết isolation/serialization plan; kiểm JUnit parallel mode.

**Bài 17 — Cause chain helper.** Mở rộng `causeMessages` để lưu class+message của từng layer vào immutable list, che chuỗi chứa credentials, không chỉ lấy `Throwable.toString()`.

**Bài 18 — Classification.** Phân loại root errors từ báo cáo CI thành missing property, DB unavailable, bean graph, port conflict, migration và corrupted test fixture; đề xuất owner/fix.

**Bài 19 — Diagnostic noise.** Phân biệt 20 test failures, 1 context key, 1 actual failed load, 19 skips và 50 log lines trùng. Vì sao mỗi số đếm nói một điều khác?

**Bài 20 — Regression.** Sau khi sửa root cause, thêm một test guardrail đúng tầng, chạy representative test và full suite, xác nhận threshold messages biến mất mà không đổi threshold mặc định.

## 18. Checklist chẩn đoán trước khi thay config

1. Project có dùng Spring Framework 6.1+ không? Spring Boot 3.3.5 có.
2. Dòng lỗi chứa **`failure threshold`** hay **`Failed to load ApplicationContext`**?
3. Đã lấy full exception chain, không chỉ Gradle task failure summary?
4. Đã tìm root cause của **mỗi failing context key**?
5. Có nhiều keys do profiles, mocks, test slices, property sources hay context hierarchy?
6. JVM test worker có nhận đúng `spring.test.context.failure.threshold` không?
7. Có ai đã tăng threshold vô hạn để che lỗi và làm CI chậm?
8. Có tests chạy ở nhiều JVM forks/CI shards, mỗi nơi cache riêng?
9. `@DirtiesContext` có đang bị dùng sai để chữa startup failure?
10. Lỗi có thực sự nằm ở Spring context initialization hay ở thân test?
11. Nếu thiếu bean, kiểm scan/import/qualifier/profile thay vì chỉ thêm mock?
12. Nếu DB lỗi, kiểm connection/readiness/migration/URL/credentials **không in secret**?
13. Nếu chỉ fail full suite, đã kiểm shared state/parallel race/global properties?
14. Có external resources stop trước khi cached context được tái sử dụng?
15. Có đọc test HTML/XML thay vì tin task `--stacktrace` đã có mọi thông tin?
16. Logs có metadata cho test class/JVM/profile/context config không?
17. Sau khi sửa, đã chạy representative test và toàn suite?
18. Kết luận có phân biệt root context failures, skipped attempts và test failures?
19. Không claim “đã chạy Gradle và test xanh” nếu chỉ mới cung cấp source mẫu.
20. Có regression test/documentation cho lỗi chính, không kéo dài incident bằng log spam?

## 19. Nguồn tham khảo chính thức

- [Spring Framework 6.1 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/failure-threshold.html): chính sách từ Spring 6.1, mặc định 1 và JVM property.
- [Spring Framework 6.1 — Context Caching](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/caching.html): context cache key, static cache, LRU, DEBUG stats.
- [Spring Framework 6.1 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework.html): cơ chế loading/configuration/test lifecycle.
- [Spring Framework 6.1 API — TestContextManager](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContextManager.html): `getTestContext` và quản lý test contexts.
- [Spring Framework 6.1 API — TestContext](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContext.html): `getApplicationContext` nạp/lấy context cached.
- [Spring Framework 6.1 API — CacheAwareContextLoaderDelegate](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/CacheAwareContextLoaderDelegate.html): constants threshold và context loader contract.
- [Spring Framework 6.1 API — DefaultCacheAwareContextLoaderDelegate](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/cache/DefaultCacheAwareContextLoaderDelegate.html): default cache và failure threshold.
- [Spring Framework 6.1 API — ContextCacheUtils](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/cache/ContextCacheUtils.html): retrieve failure threshold/cache size.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): evict/close context, khác startup failure.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, testing slices và TestContext.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): properties/profiles trong Spring Boot.
- [JUnit Jupiter 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/): JUnit lifecycle, tests và assertions.
- [Gradle — Test Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): JVM test workers, test reports và `Test.systemProperty`.
- [Gradle — Command Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--info`, `--stacktrace`.

**Ghi nhớ:** `ApplicationContext failure threshold (1) exceeded` thường là **một tín hiệu phụ**: Spring TestContext đã thử nạp **cùng context cache key** và thất bại, nên nó **bỏ qua các lần thử lặp** cho key đó. Đừng sửa “skip message” bằng tăng threshold hoặc thêm `@DirtiesContext`; hãy lần về **actual failed load đầu tiên, đọc nested `Caused by` và khắc phục bean/property/resource gốc**. Spring Boot 3.3.5/Spring Framework 6.1 mặc định threshold=1, tính theo **cache key trong test JVM**. Kiểm thử và báo cáo tốt cần phân biệt **test cases failed**, **actual context load failures**, **preemptive skips** và **root causes**, rồi xác minh sửa chữa bằng representative test cùng toàn suite.
