# Phân biệt kiểm thử JVM bằng ApplicationContextRunner với kiểm thử ứng dụng Spring Boot native

## 1. Hai mục tiêu kiểm thử khác nhau

Khi một thư viện Spring Boot cung cấp auto-configuration, ta thường cần xác minh hai nhóm hành vi:

1. **Quyết định cấu hình:** bean mặc định có được tạo không, custom bean có làm auto-configuration back off không, property/classpath condition có khớp không?
2. **Khả năng chạy native:** ứng dụng đã qua Spring AOT có khởi động được trong GraalVM Native Image không, các reflection/resource/proxy cần thiết có được giữ lại không và luồng ứng dụng có hoạt động trong executable native không?

`ApplicationContextRunner` là công cụ rất phù hợp cho nhóm thứ nhất. Nó tạo các Spring `ApplicationContext` nhỏ trên JVM để kiểm tra từng tổ hợp condition. Tuy nhiên, Spring Boot 3.3 ghi rõ `ApplicationContextRunner` **không hoạt động khi chạy test trong native image**.

Kiểm thử native dùng cơ chế khác: Spring TestContext Framework có hỗ trợ AOT cho các test JUnit 5, chẳng hạn `@SpringBootTest` và các test slice. Native Build Tools xử lý context ở build-time, tạo native test image, rồi chạy JUnit TestEngine trong image đó.

Vì vậy, hai nhóm test bổ sung cho nhau. Context runner giúp tìm lỗi logic auto-configuration nhanh; native test xác nhận ứng dụng và test context hoạt động trong môi trường native thực tế.

## 2. Bản đồ các lớp kiểm thử

| Kiểu kiểm thử | Môi trường thực thi | Mục tiêu chính | Dùng khi nào |
| --- | --- | --- | --- |
| Unit test Java thuần | JVM | Logic của class, không cần Spring | Service, mapper, validator, thuật toán |
| `ApplicationContextRunner` | JVM | Bean registration, condition, user override, property và classpath | Phát triển auto-configuration |
| `@SpringBootTest` thông thường | JVM | Khởi động context gần với ứng dụng thật | Kiểm thử tích hợp giữa nhiều bean |
| AOT mode trên JVM | JVM dùng code được Spring AOT sinh | Kiểm tra context AOT và code khởi tạo đã sinh | Trước khi tốn thời gian biên dịch native |
| Native test bằng `nativeTest` | GraalVM Native Image chứa test | Chạy Spring integration test trong native image | Xác minh các luồng có nguy cơ khác JVM |
| Smoke/integration test bên ngoài | Test process gọi native executable đang chạy | Kiểm tra artifact triển khai qua HTTP hoặc giao thức thật | Xác nhận binary/container native cuối cùng |

Không nên gọi mọi test có chữ “native” là cùng một loại. `nativeTest` tạo native image chứa bộ test và JUnit engine; `nativeCompile` tạo native executable của ứng dụng. Một test process riêng gọi endpoint của executable đang chạy là lớp kiểm thử black-box thứ ba.

## 3. ApplicationContextRunner giải quyết bài toán gì?

Một auto-configuration có thể thay đổi theo nhiều yếu tố:
- Ứng dụng có khai báo bean cùng contract hay chưa.
- Property trong `Environment` đang có giá trị gì.
- Dependency tùy chọn có trên classpath hay không.
- Có prerequisite bean nào được đăng ký trước không.
- Context là non-web, servlet hay reactive.

`ApplicationContextRunner` tạo context độc lập cho từng scenario. Các API thường dùng:

| API | Tác dụng |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp auto-configuration đang được kiểm thử |
| `withUserConfiguration(...)` | Mô phỏng cấu hình do ứng dụng cung cấp |
| `withPropertyValues(...)` | Đưa property vào Environment |
| `withBean(...)` | Đăng ký trực tiếp fixture/mock bean |
| `withClassLoader(new FilteredClassLoader(...))` | Mô phỏng class hoặc package không có trên classpath |
| `withInitializer(...)` | Gắn initializer hoặc Condition Evaluation Report listener |
| `run(context -> ...)` | Mở context, chạy assertion và đóng context |

Runner không cần khởi động toàn bộ `SpringApplication`, không yêu cầu web server hay database nếu scenario không cần các thành phần đó. Mỗi lần `run` tạo một context riêng, nên property và bean của test này không rò rỉ sang test khác.

## 4. Ví dụ JVM: kiểm tra default và custom bean bằng context runner

Giả sử thư viện có `GreetingService` và auto-configuration tạo implementation mặc định nếu ứng dụng chưa cung cấp bean riêng.

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationContextRunnerTests {

    interface GreetingService {
        String message();
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from library";
        }
    }

    static final class CustomGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from application";
        }
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        DefaultGreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        CustomGreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenApplicationHasNoCustomBean() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(DefaultGreetingService.class);
            assertThat(context.getBean(GreetingService.class).message())
                    .isEqualTo("hello from library");
        });
    }

    @Test
    void backsOffWhenApplicationProvidesCustomBean() {
        runner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                    assertThat(context.getBean(GreetingService.class).message())
                            .isEqualTo("hello from application");
                });
    }
}
~~~

Chạy test trên JVM:

~~~bash
./gradlew test --tests "*GreetingAutoConfigurationContextRunnerTests"
~~~

Hoặc Maven:

~~~bash
./mvnw -Dtest=GreetingAutoConfigurationContextRunnerTests test
~~~

Hai test chứng minh hai nhánh quan trọng của auto-configuration. Có thể mở rộng runner để kiểm tra property condition, missing dependency, nhiều candidate, `@Primary` hoặc `FilteredClassLoader`.

**Giới hạn quan trọng:** đây là test JVM. Spring Boot 3.3 ghi rõ `ApplicationContextRunner` không hoạt động khi chạy test trong native image. Không đưa test class dùng runner vào native test suite rồi kỳ vọng nó chạy giống JVM.

Nếu build chạy cả bộ test bằng Native Build Tools, hãy loại các context-runner test khỏi native run, ví dụ đánh dấu class/method bằng `@DisabledInNativeImage` của Native Build Tools hoặc cấu hình riêng danh sách test. Các test này vẫn chạy bình thường trong tác vụ JVM `test`.

## 5. @SpringBootTest trên JVM kiểm tra điều gì?

`@SpringBootTest` dùng `SpringApplication` để tạo context kiểm thử, nên có thể đưa vào nhiều phần cấu hình ứng dụng hơn context runner. Nó phù hợp khi cần kiểm tra tích hợp giữa controller, service, configuration, security, serialization hoặc các auto-configuration cùng hoạt động.

Ví dụ một test JVM thông thường:

~~~java
@SpringBootTest
class ApplicationContextIntegrationTests {

    @Autowired
    GreetingService greetingService;

    @Test
    void applicationProvidesGreetingService() {
        assertThat(greetingService.message()).isNotBlank();
    }
}
~~~

Test này xác minh context ứng dụng có thể khởi động và inject service. Tuy nhiên, nó vẫn chạy trên JVM thông thường. Nó chưa chứng minh:
- Spring AOT tạo được code khởi tạo hợp lệ.
- GraalVM giữ lại các class/resource/proxy cần thiết.
- Native executable khởi động được.
- Những API hoặc thư viện có hành vi khác trong native image vẫn hoạt động.

`@SpringBootTest` trên JVM và `@SpringBootTest` chạy trong native test image có thể dùng chung ý tưởng test, nhưng build pipeline và runtime khác nhau.

## 6. AOT mode chạy trên JVM: bước kiểm tra ở giữa

Spring AOT phân tích ứng dụng tại build-time và sinh code tối ưu cho việc khởi tạo `ApplicationContext`. Có thể chạy ứng dụng trên JVM nhưng yêu cầu Spring sử dụng code AOT đã sinh bằng system property:

~~~bash
java -Dspring.aot.enabled=true -jar target/my-application.jar
~~~

Điều kiện là artifact phải chứa output AOT. Với Maven, Spring Boot 3.3 có thể kích hoạt profile `native` để chạy `process-aot`; với Gradle, áp dụng GraalVM Native Image plugin để Spring Boot cấu hình các task AOT.

Ví dụ Maven với Spring Boot parent:

~~~bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/my-application.jar
~~~

Đây vẫn là một process JVM. Nó kiểm tra code khởi tạo AOT và phát hiện sớm một số vấn đề trước khi biên dịch native image. Nó **không** kiểm tra GraalVM reachability, native executable hay các giới hạn runtime của native image.

Nếu ứng dụng không bật đúng AOT build hoặc JAR không chứa generated assets, đặt `spring.aot.enabled=true` sẽ không biến một JAR thông thường thành artifact AOT. Hãy xác minh build output và task `processAot` đã chạy.

## 7. Native test hoạt động như thế nào?

Spring Framework hỗ trợ AOT cho JUnit 5 test sử dụng TestContext Framework. Native Build Tools và Spring Boot phối hợp theo luồng tổng quát:

1. Phân tích các test để tìm những `ApplicationContext` mà chúng cần.
2. Chạy AOT processing cho từng test context và sinh initializer/assets tương ứng.
3. Đưa generated assets vào quá trình biên dịch GraalVM Native Image.
4. Đóng gói JUnit `TestEngine` cùng danh sách test đã được phát hiện vào native test image.
5. Khởi chạy image; JUnit engine thực thi các test và báo cáo kết quả.

Vì vậy test dùng `@SpringBootTest` và Spring test slices có thể chạy trong native image thông qua cơ chế AOT của TestContext Framework.

Khác biệt với context runner:
- `ApplicationContextRunner` tự tạo context động trong thân test bằng callback `run`; Spring Boot không hỗ trợ cách này trong native image test.
- `@SpringBootTest` khai báo test context theo mô hình mà Spring TestContext Framework có thể phát hiện và xử lý AOT ở build-time.
- Native test image chứa test engine và context initializer đã sinh, thay vì dựa vào việc dựng context tùy ý tại runtime.

## 8. Ví dụ test ứng dụng chạy trong native image

Giả sử ứng dụng có endpoint:

~~~java
@RestController
class ProbeController {

    @GetMapping("/probe")
    String probe() {
        return "native-ready";
    }
}
~~~

Test tích hợp:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NativeApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void httpEndpointWorksInTheNativeTestImage() {
        ResponseEntity<String> response =
                http.getForEntity("/probe", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("native-ready");
    }
}
~~~

Test này dùng Spring TestContext Framework và khởi động web context với cổng ngẫu nhiên. Khi chạy qua native test task, context và test được xử lý AOT rồi thực thi trong native test image.

Điều kiện ví dụ:
- Ứng dụng có `spring-boot-starter-web` và `spring-boot-starter-test`.
- `ProbeController` được đăng ký trong component scan hoặc được import rõ ràng.
- Native Build Tools, GraalVM và toolchain biên dịch native đã được cài đặt đúng.
- Test context không phụ thuộc các cấu hình động mà AOT không thể xác định ở build-time.

Đây là ví dụ integration test. Nó kiểm tra endpoint và HTTP response trong native test image, không phải ví dụ của `ApplicationContextRunner`.

## 9. Cấu hình và lệnh chạy bằng Gradle

Với Gradle Groovy DSL, thêm Spring Boot plugin và GraalVM Native Image plugin. Ví dụ các phiên bản tương thích với Spring Boot 3.3.13:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.graalvm.buildtools.native' version '0.10.6'
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi GraalVM Native Image plugin được áp dụng, Spring Boot Gradle plugin cấu hình các task AOT cho application và test.

Các lệnh chính:

~~~bash
# Test nhanh trên JVM, bao gồm ApplicationContextRunner
./gradlew test

# Chạy các test được hỗ trợ bên trong native test image
./gradlew nativeTest

# Biên dịch native executable của ứng dụng
./gradlew nativeCompile
~~~

`nativeTest` và `nativeCompile` là hai task khác nhau. Task đầu tạo/chạy image chứa test; task sau tạo executable của ứng dụng để triển khai.

GraalVM Native Image yêu cầu toolchain phù hợp với hệ điều hành và kiến trúc đích. Build native thường chậm hơn JVM test đáng kể; vì vậy nên giữ `test` làm vòng phản hồi nhanh và chạy `nativeTest` trong CI hoặc trên một lịch phù hợp.

## 10. Cấu hình và lệnh chạy bằng Maven

Nếu dùng `spring-boot-starter-parent` 3.3.13, parent cung cấp profile `nativeTest` để cấu hình các execution AOT cho test. Module ứng dụng cần khai báo Spring Boot Maven plugin và Native Build Tools Maven plugin:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Lệnh:

~~~bash
# Test JVM thông thường
./mvnw test

# Xử lý AOT test và chạy test trong native image
./mvnw -PnativeTest test

# Biên dịch native executable của ứng dụng
./mvnw -Pnative native:compile
~~~

Nếu không dùng `spring-boot-starter-parent`, cần cấu hình tương đương cho `process-test-aot` của Spring Boot Maven plugin và goal `test` của Native Build Tools Maven plugin. Chỉ thêm native plugin mà không kích hoạt quy trình test AOT không đồng nghĩa Maven đã chạy test trong native image.

## 11. Native test image khác native executable triển khai

Hai quy trình sau thường bị nhầm:

**Native test image**
- Chứa các class test và JUnit TestEngine.
- Được tạo để chạy bộ test trong native mode.
- Dùng `nativeTest` của Gradle hoặc profile `nativeTest` của Maven.
- Mục tiêu là kiểm tra test context và hành vi trong native runtime.

**Native executable của ứng dụng**
- Chứa application code, generated AOT assets và các reachability hints cần thiết.
- Không phải bộ test JUnit của project.
- Được tạo bằng `nativeCompile` hoặc `native:compile`.
- Mục tiêu là artifact triển khai thực tế.

Có thể kiểm tra executable sau khi build bằng một smoke test bên ngoài:

~~~bash
# Khởi động executable native ở terminal thứ nhất
./build/native/nativeCompile/my-application
~~~

Terminal thứ hai gọi endpoint:

~~~bash
curl -i http://localhost:8080/probe
~~~

Kết quả mong đợi là HTTP 200 và body `native-ready`. Lệnh này kiểm tra native executable đang chạy; nó không phải lệnh `nativeTest`.

Đối với container image, có thể chạy container native rồi gửi HTTP request từ test process hoặc pipeline bên ngoài. Cách này xác minh thêm cấu hình container, port mapping, environment variables, filesystem và startup command.

## 12. Các khác biệt AOT/native cần kiểm tra

Native Image dùng phân tích tĩnh theo giả định closed-world. GraalVM không tự biết mọi hành vi động mà ứng dụng có thể thực hiện. Những khác biệt đáng chú ý:

### 12.1. Bean graph được quyết định ở build-time

Trong quá trình `processAot`, `BeanFactory` được chuẩn bị và các condition được đánh giá. Vì vậy cấu hình môi trường dùng ở build-time có thể quyết định bean nào tồn tại trong native image.

Ví dụ `@ConditionalOnProperty` hoặc `@Profile` dùng để tạo bean không thể được xem như công tắc tùy ý để thêm/xóa bean sau khi image đã build. Hãy cung cấp đúng property/profile cho AOT build và kiểm thử cấu hình tương ứng.

### 12.2. Reflection, resource và proxy

Native image có thể loại bỏ code không được chứng minh là reachable. Nếu ứng dụng dùng reflection, resource đọc theo tên động, serialization hoặc dynamic proxy, cần có hints phù hợp.

Spring AOT tự sinh nhiều hints cho các trường hợp được hỗ trợ. Với trường hợp đặc biệt, có thể cần đăng ký `RuntimeHints` hoặc metadata GraalVM bổ sung.

### 12.3. Classpath cố định

Native executable được build từ classpath tại thời điểm build. Không thể thêm thư viện mới vào runtime classpath như khi chạy JVM thông thường.

Một condition classpath đã được quyết định khi AOT xử lý; không thể kỳ vọng cài thêm JAR sau khi build để auto-configuration mới xuất hiện.

### 12.4. Thư viện và test framework

Một thư viện chạy tốt trên JVM chưa chắc đã hỗ trợ native. Các công cụ dựa vào bytecode instrumentation, dynamic class loading, reflection hoặc proxy cần được kiểm tra riêng. Không giả định mọi mock framework hay test extension đều tương thích chỉ vì test JVM đang pass.

## 13. Ma trận kiểm thử đề xuất cho thư viện auto-configuration

| Khu vực | JVM context runner | AOT trên JVM | Native test / native executable |
| --- | --- | --- | --- |
| Default bean được đăng ký | Rất phù hợp | Có thể kiểm tra thêm context AOT | Kiểm tra smoke/integration nếu ảnh hưởng runtime |
| User bean làm default back off | Rất phù hợp | Kiểm tra cấu hình build-time đã chọn | Test context bằng `@SpringBootTest` nếu cần |
| `@ConditionalOnProperty` | Thử nhiều giá trị nhanh | Xác minh giá trị được dùng khi AOT build | Xác minh image được build với đúng cấu hình |
| `@ConditionalOnClass` | Dùng `FilteredClassLoader` | Xác minh generated context cho dependency có mặt | Kiểm tra native image có dependency/hints phù hợp |
| Bean wiring và HTTP | Chỉ khi context nhỏ là đủ | Kiểm tra khởi tạo AOT | `@SpringBootTest` native hoặc black-box HTTP |
| Reflection/resource/proxy hints | Unit test `RuntimeHints` có thể hỗ trợ | Kiểm tra code AOT và hints sinh | Native test/executable là bằng chứng runtime mạnh hơn |
| Startup và cấu hình container | Không phải mục tiêu chính | Không thay thế deploy test | Chạy executable/container và smoke test |

Ma trận này giúp tránh hai thái cực: chỉ có context runner rồi kết luận native đã ổn, hoặc chạy native image cho mọi test dù phần lớn logic có thể kiểm tra nhanh trên JVM.

## 14. Quy trình CI cân bằng

Một pipeline thực tế có thể chia thành các tầng:

~~~mermaid
flowchart TD
    A["Mỗi thay đổi code"] --> B["Unit tests + ApplicationContextRunner trên JVM"]
    B --> C["Spring integration tests trên JVM"]
    C --> D["AOT processing và chạy ứng dụng trên JVM"]
    D --> E["Native test image: @SpringBootTest / test slices"]
    E --> F["Build native executable"]
    F --> G["Smoke test executable hoặc container"]
~~~

Cách phân bổ thường hợp lý:
- Chạy unit test và context runner ở mọi pull request vì nhanh.
- Chạy Spring integration test trên JVM trong mỗi build.
- Chạy AOT mode trên JVM để phát hiện lỗi generated initialization trước native compile.
- Chạy một tập native test có chọn lọc ở CI; có thể chạy nightly nếu thời gian biên dịch lớn.
- Chạy smoke test trên native executable/container trước phát hành.

Không nhất thiết mọi nhánh CI đều phải biên dịch native image. Hãy ưu tiên test những đường code có khác biệt thực sự giữa JVM và native, như reflection, resource access, serialization, proxy, classpath tùy chọn và cấu hình build-time.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ApplicationContextRunner` fail trong `nativeTest` | Runner không được hỗ trợ khi chạy test trong native image | Giữ test runner ở JVM; loại khỏi native suite hoặc dùng `@DisabledInNativeImage` |
| JVM test pass nhưng native test fail khi build AOT | Test context hoặc cấu hình có phần không thể phân tích ở build-time | Kiểm tra TestContext configuration, dynamic bean registration và build-time properties |
| Native app thiếu bean bật bằng property | Condition đã được đánh giá khi AOT build với Environment khác runtime | Đặt đúng property/profile trong môi trường build AOT và rebuild image |
| Native executable báo thiếu resource | Resource không được reachability analysis phát hiện | Đăng ký resource hint và kiểm tra lại native image |
| Reflection hoạt động trên JVM nhưng lỗi native | Thiếu reflection hint hoặc API không được hỗ trợ | Dùng Spring RuntimeHints/GraalVM metadata và viết native regression test |
| Bean dùng proxy chạy sai trong native | Proxy type/interface không được nhận diện hoặc có giới hạn AOT | Kiểm tra proxy strategy, generated hints và test case native |
| `nativeTest` không tìm thấy test | Test không thuộc JUnit 5/TestContext pipeline hoặc build plugin chưa cấu hình | Kiểm tra dependency, plugin, profile và báo cáo task |
| Native test chạy quá lâu | Biên dịch native test image tốn thời gian | Giữ phần lớn test trên JVM, chỉ đưa scenario native quan trọng vào suite |
| Native executable chạy được nhưng endpoint lỗi | Chỉ kiểm tra startup, chưa kiểm tra luồng HTTP/integration | Gửi request từ process bên ngoài và assert status/body |
| AOT JVM test dùng context khác production | Build-time property/profile khác với cấu hình phát hành | Đồng bộ Environment AOT build với profile triển khai mục tiêu |

### Checklist điều tra

1. Xác nhận lỗi xảy ra ở JVM test, AOT processing, native test image hay native executable.
2. Kiểm tra condition và profile nào được đánh giá tại build-time.
3. Xác minh generated AOT classes/resources có trong artifact.
4. Kiểm tra reflection/resource/proxy/serialization hints.
5. Đọc log của `processAot`, `processTestAot` và native-image compiler.
6. Reproduce bằng một test nhỏ trên JVM trước khi tăng độ phức tạp native.
7. Chạy native smoke test trên đúng OS/architecture và cấu hình gần production.

## 16. Nguyên tắc lựa chọn công cụ

- Dùng `ApplicationContextRunner` để kiểm tra nhanh logic auto-configuration trên JVM: default, back-off, property, classpath và dependency conditions.
- Dùng `@SpringBootTest` trên JVM để kiểm tra tích hợp ứng dụng với SpringApplication và các bean thực.
- Dùng AOT mode trên JVM để xác minh generated initialization code trước khi biên dịch native.
- Dùng `@SpringBootTest` hoặc test slices chạy qua `nativeTest` cho các scenario cần chứng minh TestContext hoạt động trong native image.
- Dùng test process bên ngoài để gọi native executable/container và kiểm tra giao thức triển khai.
- Đưa các test không tương thích native, như test dùng `ApplicationContextRunner`, ra khỏi native suite.
- Không coi native test image là native executable production; chạy smoke test riêng cho artifact triển khai.
- Ghi rõ profile/property được dùng khi AOT build vì điều kiện tạo bean được quyết định tại build-time.
- Chỉ mở rộng native suite khi có rủi ro native cụ thể; giữ vòng phản hồi JVM nhanh và dễ chạy trong IDE.

## 17. Tự kiểm tra kiến thức

1. `ApplicationContextRunner` phù hợp nhất với loại test nào? **Kiểm thử auto-configuration, bean conditions và Environment trên JVM.**
2. Có thể chạy `ApplicationContextRunner` trong native image test không? **Không; Spring Boot 3.3 ghi rõ runner không hoạt động trong native image tests.**
3. Test nào có thể được Spring TestContext AOT xử lý để chạy native? **Các JUnit 5 integration test dùng TestContext Framework, ví dụ `@SpringBootTest` và test slices.**
4. `nativeTest` tạo ra loại artifact nào? **Native image chứa test và JUnit TestEngine để chạy bộ test.**
5. `nativeCompile` tạo ra gì? **Native executable của ứng dụng.**
6. `spring.aot.enabled=true` có biến JVM thành native image không? **Không; nó yêu cầu JVM dùng code khởi tạo AOT đã sinh.**
7. Vì sao condition property cần được kiểm tra ở build-time? **Bean graph được chuẩn bị và condition được đánh giá trong AOT processing.**
8. Native image có thể tự giữ mọi class được gọi bằng reflection không? **Không; cần reachability hints phù hợp cho reflection/resources/proxies khi Spring không thể suy ra.**
9. Vì sao vẫn giữ nhiều test trên JVM? **Vòng phản hồi nhanh, IDE hỗ trợ tốt và chi phí native image build cao.**
10. Sau khi nativeCompile thành công, còn cần test gì? **Chạy executable/container và smoke/integration test các luồng quan trọng.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): cách dùng `ApplicationContextRunner`, các customizations của context và lưu ý runner không chạy trong native image tests.
- [Spring Boot 3.3 — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html): chiến lược giữ phần lớn test trên JVM, AOT mode trên JVM và native testing bằng Native Build Tools.
- [Spring Boot 3.3.13 — Maven Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html): `process-aot`, `process-test-aot`, build-time BeanFactory và nativeTest profile.
- [Spring Boot 3.3 — Gradle Plugin Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/gradle-plugin/aot.html): task `processAot`, `processTestAot`, `nativeTest` và `nativeCompile`.
- [Spring Boot 3.3 — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world, classpath cố định, AOT và các giới hạn native.
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java, GraalVM và Native Build Tools tương thích.
