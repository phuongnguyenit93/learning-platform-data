# Hiểu @AutoConfigureObservability và hành vi tự cấu hình trong kiểm thử

> Phạm vi: Spring Boot 3.3.x, Java 21, JUnit Jupiter và Micrometer do Spring Boot quản lý phiên bản. Các cấu hình bên dưới là ví dụ học tập độc lập; không phải yêu cầu thay đổi cấu hình của mọi dự án.

## 1. Bài kiểm thử cần quan sát điều gì?

Giả sử thao tác xử lý đơn hàng đã được gắn mã quan sát. Khi chạy ứng dụng, bạn muốn biết thao tác xảy ra bao nhiêu lần, kéo dài bao lâu và nằm ở đâu trong chuỗi lời gọi. Khi kiểm thử, có thể bạn chỉ muốn xác nhận tên quan sát và nhãn; có thể bạn muốn kiểm tra cách Spring nối các bean; cũng có thể bạn cần chứng minh dữ liệu tới được hệ thống thu thập.

Ba mục tiêu đó cần ba mức kiểm thử khác nhau. Trước khi thêm annotation, hãy viết rõ điều cần chứng minh:

| Mục tiêu | Bằng chứng nên kiểm tra | Môi trường phù hợp |
| --- | --- | --- |
| Mã nghiệp vụ tạo đúng quan sát | Tên, nhãn, vòng đời bắt đầu/kết thúc | Kiểm thử đơn vị với TestObservationRegistry |
| Cấu hình Spring nối đúng các thành phần | Bean và kết quả ghi nhận trong registry | Kiểm thử có ApplicationContext |
| Dữ liệu được chuyển ra ngoài | Dữ liệu mà bộ thu thử nghiệm thực sự nhận | Kiểm thử tích hợp với bộ thu do bài kiểm thử kiểm soát |

Ví dụ, khẳng định một bean tồn tại chỉ trả lời câu hỏi về cấu hình. Nó chưa trả lời câu hỏi dữ liệu đã được gửi và tiếp nhận hay chưa.

## 2. Các thành phần cần nhận diện

Khả năng quan sát (observability) giúp tìm hiểu trạng thái bên trong hệ thống qua tín hiệu như nhật ký, số liệu đo và vết truy tìm. Trong bài này, trọng tâm là quan sát của Micrometer, số liệu đo (metrics) và truy vết (tracing). Spring Boot hỗ trợ kết nối chúng qua cấu hình tự động. [Tài liệu Observability của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

| Thành phần | Vai trò trong bài kiểm thử |
| --- | --- |
| Observation | Một lần thực hiện thao tác được quan sát |
| ObservationRegistry | Nơi cấu hình việc xử lý các quan sát |
| ObservationHandler | Nhận sự kiện trong vòng đời quan sát và thực hiện xử lý tương ứng |
| MeterRegistry | Chứa các bộ đo, chẳng hạn Counter và Timer |
| Tracer | API làm việc với các span trong truy vết |
| Exporter hoặc bộ phận gửi dữ liệu | Chuyển tín hiệu tới một hệ thống thu thập |

Quan sát tạo sự kiện; những bộ xử lý đã đăng ký quyết định sự kiện được chuyển thành số liệu hoặc vết như thế nào. Vì vậy, chỉ khởi tạo một ObservationRegistry chưa đủ để chứng minh có số liệu hay dữ liệu truy vết. [Cơ chế Observation của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Một SimpleMeterRegistry giữ số liệu trong bộ nhớ và không tự gửi chúng ra ngoài. Đây là công cụ hữu ích để kiểm tra kết quả đo mà không cần một hệ thống giám sát. [MeterRegistry và SimpleMeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

## 3. Annotation thay đổi điều gì?

Annotation có tên đầy đủ:

```java
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
```

Nó được đặt trên lớp kiểm thử và hỗ trợ tự cấu hình observability. Trong Spring Boot 3.3, hai thuộc tính sau đều mặc định là true:

```java
@AutoConfigureObservability(metrics = true, tracing = true)
```

metrics và tracing diễn đạt việc cho phép báo cáo số liệu hoặc vết ra hệ thống ngoài trong kiểm thử. Chúng không có nghĩa là thư viện xuất dữ liệu sẽ được tự tải xuống, bộ thu tự được khởi động hoặc mọi điều kiện cấu hình đều bị bỏ qua. [API AutoConfigureObservability 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/actuate/observability/AutoConfigureObservability.html).

Cần xét annotation cùng loại kiểm thử:

| Trường hợp | Hành vi cần nhớ trong Spring Boot 3.3 |
| --- | --- |
| @SpringBootTest thông thường | Tự cấu hình hạn chế các registry ngoài bộ nhớ và các thành phần truy vết báo cáo dữ liệu |
| @SpringBootTest kèm @AutoConfigureObservability | Có thể tự cấu hình lại các thành phần báo cáo nếu dependency, thuộc tính và điều kiện bean phù hợp |
| Kiểm thử lát cắt kèm @AutoConfigureObservability | Có MeterRegistry trong bộ nhớ, ObservationRegistry và Tracer dạng no-op khi các lớp cần thiết có mặt |

No-op nghĩa là thành phần đáp ứng giao diện mà không thực hiện ghi nhận truy vết thực. Đặc biệt, thêm annotation vào một kiểm thử lát cắt không biến nó thành bài kiểm thử xuất dữ liệu. [Quy tắc kiểm thử metrics và tracing của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.tracing).

## 4. Cách suy luận về cấu hình tự động

Khi kết quả khác dự đoán, lần lượt kiểm tra:

1. **Loại kiểm thử:** bạn đang nạp toàn bộ cấu hình ứng dụng hay một lát cắt?
2. **Dependency:** API quan sát, registry, cầu nối truy vết và bộ xuất cần dùng có thực sự nằm trong classpath?
3. **Lựa chọn của kiểm thử:** annotation có mặt không, metrics/tracing được đặt thế nào?
4. **Điều kiện cấu hình:** thuộc tính, cấu hình bị loại trừ hoặc bean tự khai báo có thay đổi kết quả không?
5. **Hành vi:** thao tác có chạy, quan sát có kết thúc, và bằng chứng bạn kiểm tra thuộc đúng mức không?

Đây là trình tự chẩn đoán. Nó giúp tránh việc sửa dependency khi nguyên nhân chỉ là dùng một kiểu kiểm thử không nạp phần cấu hình cần xét.

### Giới hạn của metrics = false và tracing = false

Cấu hình sau phù hợp để thể hiện ý định không bật cơ chế báo cáo ngoài của kiểm thử:

```java
@AutoConfigureObservability(metrics = false, tracing = false)
```

Đừng suy ra rằng mọi Counter, Timer hoặc ObservationRegistry đều biến mất. Đo trong bộ nhớ và gửi ra ngoài là hai việc khác nhau. Cũng cần kiểm tra các bean tự khai báo: annotation không phải cơ chế chặn mạng đối với mọi đoạn mã trong ứng dụng.

Một bean do ứng dụng khai báo có thể dùng @ConditionalOnEnabledTracing để tham gia điều kiện bật/tắt tracing. Annotation điều kiện này kiểm tra management.tracing.enabled và cũng khớp khi thuộc tính chưa được khai báo. [API ConditionalOnEnabledTracing 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/ConditionalOnEnabledTracing.html).

## 5. Thí nghiệm độc lập: so sánh cấu hình mặc định và cấu hình có annotation

Ví dụ dưới đây dùng hai lớp kiểm thử và một cấu hình dùng chung. Không cần máy chủ HTTP hay bộ thu bên ngoài. Bean tracingModeProbe chỉ là dấu hiệu để kiểm tra điều kiện tracing, không phải exporter hoặc tracer.

### 5.1. Cấu hình Gradle

Trong một dự án thực hành riêng, dùng build.gradle sau. Cần JDK 21 và Gradle tương thích; có thể dùng Gradle Wrapper 8.5 đã được chuẩn bị cho dự án đó.

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là dự án chỉ dùng để chạy test, nên không cần plugin đóng gói ứng dụng Boot hay phương thức main. Các dependency không ghi phiên bản riêng được quản lý qua BOM đã chọn.

### 5.2. Cấu hình dùng chung

Tệp src/test/java/example/ObservabilityTestApplication.java:

```java
package example;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.actuate.autoconfigure.tracing.ConditionalOnEnabledTracing;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
class ObservabilityTestApplication {

    @Bean
    @ConditionalOnEnabledTracing
    String tracingModeProbe() {
        return "tracing-condition-matched";
    }
}
```

### 5.3. Kiểm thử mặc định vẫn đo được trong bộ nhớ

Tệp src/test/java/example/DefaultObservabilityTest.java:

```java
package example;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ObservabilityTestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class DefaultObservabilityTest {

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @Autowired
    ApplicationContext context;

    @Test
    void recordsLocalMetricWithoutEnablingTracingReporting() {
        assertThat(context.containsBean("tracingModeProbe")).isFalse();

        String name = "lesson.default.work";
        Timer existing = meters.find(name).timer();
        long before = existing == null ? 0L : existing.count();

        Observation.createNotStarted(name, observations)
            .observe(() -> {
                int result = 6 * 7;
                assertThat(result).isEqualTo(42);
            });

        Timer recorded = meters.get(name).timer();
        assertThat(recorded.count()).isEqualTo(before + 1L);
    }
}
```

Phép đo được kiểm tra sau khi observe kết thúc. Dùng chênh lệch count thay vì mặc định tổng luôn bằng 1 giúp bài kiểm thử ít phụ thuộc hơn vào dữ liệu đã có trong registry. Timer cung cấp cả số lần ghi nhận và thời gian; bài kiểm thử này chủ động chọn count làm bằng chứng ổn định. [Ngữ nghĩa Timer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 5.4. Bật lại lựa chọn observability cho kiểm thử tích hợp

Tệp src/test/java/example/OptInObservabilityTest.java:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ObservabilityTestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@AutoConfigureObservability
class OptInObservabilityTest {

    @Autowired
    ApplicationContext context;

    @Test
    void permitsTheTracingConditionToMatch() {
        assertThat(context.containsBean("tracingModeProbe")).isTrue();
        assertThat(context.getBean("tracingModeProbe", String.class))
            .isEqualTo("tracing-condition-matched");
    }
}
```

Chạy từ thư mục dự án thực hành trên Windows:

```powershell
.\gradlew.bat test --tests 'example.DefaultObservabilityTest' --tests 'example.OptInObservabilityTest'
```

Kết quả mong đợi: cả hai phương thức kiểm thử thành công. Lớp đầu chứng minh việc đo cục bộ có thể hoạt động trong kiểm thử mặc định; lớp sau chứng minh điều kiện của bean thăm dò được cho phép khi có annotation. Chưa có dependency truy vết hay bộ thu nào trong ví dụ, nên không được kết luận một span đã được xuất.

Đây là mã kiểm thử chạy bằng Gradle/JUnit, không phải chương trình biên dịch độc lập bằng javac. Không dùng toàn bộ log khởi động làm stdout chuẩn, vì log còn phụ thuộc môi trường.

## 6. Khi chỉ cần kiểm tra một Observation

Giả sử mục tiêu là kiểm tra hợp đồng quan sát: đúng tên, đúng nhãn và kết thúc đầy đủ. Có thể bỏ qua việc nạp Spring bằng cách tạo TestObservationRegistry cho mỗi test.

Tệp src/test/java/example/ObservationContractTest.java, dùng cùng cấu hình Gradle ở trên:

```java
package example;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class ObservationContractTest {

    @Test
    void observesACompletedCalculation() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("lesson.calculation", registry)
            .lowCardinalityKeyValue("operation", "multiply")
            .observe(() -> {
                int answer = 6 * 7;
                if (answer != 42) {
                    throw new IllegalStateException("Unexpected result");
                }
            });

        TestObservationRegistryAssert.assertThat(registry)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasObservationWithNameEqualTo("lesson.calculation")
            .that()
            .hasLowCardinalityKeyValue("operation", "multiply")
            .hasBeenStarted()
            .hasBeenStopped();
    }
}
```

Chạy riêng:

```powershell
.\gradlew.bat test --tests 'example.ObservationContractTest'
```

Kết quả mong đợi: một test thành công. Registry được tạo mới trong phương thức nên dữ liệu của lần kiểm thử khác không được dùng làm bằng chứng. Test này kiểm tra hợp đồng Observation, không kiểm tra lựa chọn tự cấu hình của Spring hay việc gửi dữ liệu. Công cụ và chuỗi assertion tương ứng được cung cấp bởi micrometer-observation-test. [Kiểm thử Observation với Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

## 7. Chuyển sang kiểm thử bộ thu thật khi nào?

Chỉ nâng mức kiểm thử khi yêu cầu là xác minh đường truyền dữ liệu. Khi đó, chuẩn bị đầy đủ thư viện registry hoặc cầu nối truy vết, bộ xuất phù hợp, địa chỉ bộ thu thử nghiệm và các thuộc tính cần thiết. Đặt bộ thu dưới quyền kiểm soát của bài kiểm thử rồi kiểm tra dữ liệu nó nhận.

Nếu xuất dữ liệu theo lô hoặc bất đồng bộ, hãy chờ một điều kiện có thời hạn, chẳng hạn bộ thu đã nhận tín hiệu mang tên và nhãn riêng của test. Chờ một số mili giây cố định rồi kết luận thành công sẽ không chứng minh việc gửi dữ liệu hoàn tất.

Nên chọn dấu hiệu duy nhất cho dữ liệu kiểm thử để tránh nhầm với dữ liệu từ lần chạy trước. Với truy vết còn cần kiểm soát lấy mẫu; với số liệu cần hiểu chu kỳ gửi hoặc cơ chế thu thập. Việc test thành công không có ý nghĩa nếu nó chưa hề kiểm tra phía tiếp nhận.

## 8. Những nhầm lẫn thường gặp

| Hiện tượng hoặc suy luận | Cách kiểm tra lại |
| --- | --- |
| Có annotation nhưng không thấy dữ liệu ở bộ thu | Xác định loại test, thư viện, điều kiện cấu hình và dữ liệu bên nhận; không chỉ kiểm tra bean |
| Có Tracer nên chắc chắn có vết thực | Xem đó có phải no-op trong kiểm thử lát cắt không |
| metrics = false nên mọi Timer phải biến mất | Tách việc đo cục bộ khỏi việc báo cáo ra ngoài |
| TestObservationRegistry đã chứng minh cấu hình Boot đúng | Nó chỉ chứng minh phần mã dùng registry đó; cần test có context để kiểm tra cấu hình |
| Test thỉnh thoảng sai số đếm | Kiểm tra registry dùng chung, test chạy song song và tên bộ đo bị trùng |
| Thời gian đo không đúng một giá trị cố định | Chọn assertion phù hợp mục tiêu; không dùng độ trễ máy chạy làm hợp đồng nghiệp vụ |
| Kiểm thử bean thăm dò thành công nên exporter đã chạy | Kiểm tra trực tiếp dữ liệu bộ thu nhận trước khi đưa ra kết luận đó |

## 9. Tự thực hành

1. Chạy hai test cấu hình ở mục 5 và giải thích vì sao sự khác biệt của bean thăm dò không đồng nghĩa với có hay không có mọi số liệu.
2. Đổi lớp OptInObservabilityTest sang @AutoConfigureObservability(metrics = false, tracing = false). Sửa kỳ vọng của bean thăm dò thành không tồn tại, rồi kiểm tra lại.
3. Đổi nhãn operation trong mã của ObservationContractTest nhưng giữ nguyên assertion. Xác định assertion nào phát hiện sai hợp đồng.
4. Nếu yêu cầu mới là chứng minh một hệ thống thu thập đã nhận dữ liệu, viết ra bằng chứng phía bộ thu cần có và những thành phần còn thiếu trong ví dụ hiện tại.

Bạn đã nắm bài khi có thể chọn đúng mức kiểm thử, dự đoán vai trò của annotation theo loại test, và chỉ đưa ra kết luận mà assertion thực sự chứng minh được.
