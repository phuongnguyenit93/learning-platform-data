# @ConditionalOnMissingBean: chọn bean mặc định khi chưa có ứng viên

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vì sao Spring Boot cung cấp một bean mặc định nhưng vẫn ưu tiên bean do ứng dụng tự khai báo; xác định đúng trường hợp `@ConditionalOnMissingBean` khớp hoặc không khớp; xây dựng auto-configuration có khả năng nhường chỗ cho cấu hình của người dùng; và kiểm tra cả hai nhánh bằng `ApplicationContextRunner`.

## 1. Bài toán: cung cấp mặc định nhưng cho phép thay thế

Một thư viện hoặc starter có thể muốn cung cấp `GreetingService` sẵn để ứng dụng chạy ngay. Tuy nhiên, ứng dụng sử dụng thư viện có thể muốn tự định nghĩa `GreetingService` khác. Nếu thư viện luôn đăng ký bean mặc định, ngữ cảnh có thể xuất hiện hai bean cùng kiểu; một điểm tiêm phụ thuộc theo kiểu có thể gặp `NoUniqueBeanDefinitionException`.

`@ConditionalOnMissingBean` là điều kiện do **Spring Boot Auto-configuration** cung cấp. Khi điều kiện được đánh giá, Spring Boot chỉ đăng ký bean mang điều kiện nếu **chưa tìm thấy bean đáp ứng tiêu chí kiểm tra** trong `BeanFactory` thuộc phạm vi tìm kiếm.

Ví dụ về ý định thiết kế:

- Ứng dụng **không khai báo** `GreetingService`: auto-configuration đăng ký `defaultGreetingService`.
- Ứng dụng **đã khai báo** `GreetingService`: auto-configuration bỏ qua bean mặc định để ứng dụng dùng bản tùy chỉnh.
- Ứng dụng **đã có nhiều** `GreetingService`: điều kiện “thiếu bean” vẫn không khớp; annotation không tự giải quyết chuyện chọn một bean để tiêm.

Đây là cơ chế quyết định **có đăng ký định nghĩa bean hay không trong lúc xây dựng application context**. Nó không phải phép kiểm tra `null` của biến Java, không theo dõi việc bean bị xóa sau khi khởi động và không phải cơ chế đổi bean động ở thời điểm gọi phương thức.

## 2. Cách khai báo cơ bản

Mẫu thường gặp trong auto-configuration (đoạn sau minh họa cách khai báo, chưa phải một tệp Java độc lập):

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return name -> "Hello, " + name;
    }
}
~~~

Giả sử `GreetingService` là interface có phương thức `String greet(String name)`. Điều kiện hỏi: “Trong phạm vi được xét đã có bean thuộc kiểu `GreetingService` chưa?”. Nếu chưa, Spring đăng ký bean mặc định. Nếu đã có, phương thức `defaultGreetingService()` không được dùng để tạo bean đó.

Có thể bỏ đối số kiểu trong trường hợp annotation đặt **trực tiếp trên phương thức `@Bean`**:

~~~java
@Bean
@ConditionalOnMissingBean
GreetingService defaultGreetingService() {
    return name -> "Hello, " + name;
}
~~~

Ở đây, nếu không chỉ rõ `value`, `type` hoặc `name`, kiểu cần kiểm tra được suy ra từ **kiểu trả về khai báo** của phương thức (`GreetingService`). Nên khai báo kiểu trả về đủ rõ. Khai báo `Object` hoặc một kiểu quá tổng quát có thể khiến Spring Boot không nhận biết đúng loại bean cần kiểm tra tại thời điểm đánh giá điều kiện.

**Điểm phân biệt quan trọng:** tên phương thức `defaultGreetingService` thường trở thành tên bean, nhưng `@ConditionalOnMissingBean(GreetingService.class)` kiểm tra **kiểu**, không chỉ kiểm tra xem tên bean đó đã tồn tại hay chưa. Một bean tên `myGreetingService` nhưng cùng kiểu vẫn khiến fallback bị bỏ qua.

## 3. Spring Boot quyết định như thế nào?

Quy trình rút gọn khi một ứng dụng sử dụng auto-configuration:

1. Spring xử lý các định nghĩa bean từ cấu hình ứng dụng (`@Configuration`, `@Bean`, component scan, v.v.).
2. Khi xử lý định nghĩa bean trong auto-configuration, `OnBeanCondition` đánh giá `@ConditionalOnMissingBean` dựa trên **những định nghĩa bean đã được xử lý tới thời điểm đó**.
3. Spring Boot tìm bean theo những tiêu chí đã nêu: kiểu, tên hoặc annotation, có xét cấu trúc context cha–con theo `search`.
4. Nếu **không có bean nào thỏa bất kỳ tiêu chí hiện diện được chỉ định**, điều kiện khớp và định nghĩa bean mặc định được thêm vào context.
5. Nếu đã có bean tương ứng, nhánh mặc định không được đăng ký. Việc khởi tạo các singleton và tiêm phụ thuộc diễn ra theo vòng đời bean thông thường sau đó.

| Tình huống khi đánh giá điều kiện theo kiểu `GreetingService` | Đăng ký fallback? | Lý do |
| --- | --- | --- |
| Chưa có bean `GreetingService` | Có | Thiếu ứng viên đúng kiểu |
| Có một bean `customGreetingService` đúng kiểu | Không | Bean tùy chỉnh đã đáp ứng tiêu chí |
| Có hai bean cùng kiểu, một bean đánh dấu `@Primary` | Không | Số lượng lớn hơn 0; `@Primary` không biến các bean thành “không tồn tại” |
| Chỉ có bean tên `defaultGreetingService` nhưng **khác kiểu** | Có nếu kiểm tra theo kiểu | Tên trùng không đủ để thỏa điều kiện kiểm tra kiểu |
| Có bean cùng kiểu trong context cha, `search` mặc định | Không | Mặc định xét cả context cha |

Điều kiện có thể xem nhiều tiêu chí, và **không yêu cầu cùng một bean phải thỏa tất cả tiêu chí**: chỉ cần tìm thấy bean thỏa một yêu cầu hiện diện là điều kiện “missing” có thể bị loại. Vì vậy, nên dùng tiêu chí tối thiểu, rõ ràng và có chủ đích.

## 4. Ví dụ kiểm chứng thực tế bằng Java 17+ và Spring Boot 3.x

`ApplicationContextRunner` tạo các application context nhỏ, độc lập, cho phép kiểm tra auto-configuration mà không phải khởi động web server. Ví dụ sau là **một tệp test Java hoàn chỉnh**, dùng JUnit Jupiter và AssertJ từ `spring-boot-starter-test`.

Lưu tại `src/test/java/example/boot/condition/MissingBeanFallbackTest.java`:

~~~java
package example.boot.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MissingBeanFallbackTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("An"))
                    .isEqualTo("Hello, An");
            assertThat(context.containsBean("defaultGreetingService")).isTrue();
        });
    }

    @Test
    void backsOffWhenUserProvidesAService() {
        contextRunner
                .withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("An"))
                            .isEqualTo("Xin chào, An");
                    assertThat(context.containsBean("defaultGreetingService")).isFalse();
                });
    }

    @Test
    void doesNotAddDefaultWhenTwoUserServicesExist() {
        contextRunner
                .withUserConfiguration(TwoGreetingServicesConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(GreetingService.class))
                            .hasSize(2);
                    assertThat(context.containsBean("defaultGreetingService")).isFalse();
                });
    }

    interface GreetingService {
        String greet(String name);
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService defaultGreetingService() {
            return name -> "Hello, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Xin chào, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGreetingServicesConfiguration {

        @Bean
        GreetingService englishGreetingService() {
            return name -> "Hello, " + name;
        }

        @Bean
        GreetingService vietnameseGreetingService() {
            return name -> "Xin chào, " + name;
        }
    }
}
~~~

**Điều kiện chạy:** dự án Spring Boot đã có `spring-boot-autoconfigure` trên classpath và dependency test `org.springframework.boot:spring-boot-starter-test`. Với Gradle (Groovy DSL), phần dependency test có thể viết:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Khi dự án quản lý version bằng Spring Boot plugin hoặc BOM, không cần tự đặt version của starter trong đoạn trên. Chạy test tại project tương ứng:

~~~text
# Linux/macOS
./gradlew test --tests "example.boot.condition.MissingBeanFallbackTest"

# Windows
gradlew.bat test --tests "example.boot.condition.MissingBeanFallbackTest"
~~~

**Kết quả cần xác nhận:** cả ba test đều pass. Test thứ nhất chứng minh fallback được tạo và trả về `Hello, An`; test thứ hai chứng minh bean người dùng được chọn và trả về `Xin chào, An`; test thứ ba chứng minh có hai bean người dùng cũng khiến fallback không được tạo. Ví dụ sử dụng assertion, **không in các chuỗi trên ra stdout**, nên kết quả hiển thị chính xác của Gradle phụ thuộc cấu hình logging/test report.

Các lớp cấu hình trong test được khai báo lồng nhau để giữ ví dụ trong một tệp và được nạp tường minh bằng `ApplicationContextRunner`. Khi viết một starter thực tế, hãy tách auto-configuration ra lớp production phù hợp và khai báo để Spring Boot tự phát hiện.

## 5. Đưa auto-configuration vào thư viện/starter

Với Spring Boot 3.x, lớp `@AutoConfiguration` của thư viện được liệt kê, mỗi dòng một tên đầy đủ, trong tài nguyên:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung file sau khi đã tạo một lớp production `example.boot.autoconfigure.GreetingAutoConfiguration`:

~~~text
example.boot.autoconfigure.GreetingAutoConfiguration
~~~

`@AutoConfiguration` dự kiến được nạp qua file imports, không được vô tình nạp lại bằng component scan. Spring Boot xử lý auto-configuration sau các bean do ứng dụng người dùng định nghĩa, giúp fallback có cơ hội nhìn thấy cấu hình tùy chỉnh trước khi quyết định có đăng ký hay không.

Nếu một auto-configuration khác cũng cung cấp kiểu bean liên quan, cần xác định thứ tự đăng ký định nghĩa bean. Chẳng hạn, `@AutoConfiguration(after = OtherAutoConfiguration.class)` cho phép đặt fallback chạy sau cấu hình cung cấp bean kia. **Thứ tự auto-configuration là thứ tự xử lý định nghĩa bean, không đảm bảo thứ tự khởi tạo các đối tượng bean.**

## 6. Các tham số và phạm vi kiểm tra cần biết

| Cách viết/thuộc tính | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `@ConditionalOnMissingBean(MyService.class)` / `value` | Thiếu bean theo class/kiểu | Fallback phổ biến; thường là lựa chọn ưu tiên |
| `@ConditionalOnMissingBean(type = "com.example.MyService")` | Thiếu bean theo tên lớp dạng chuỗi | Khi cần tham chiếu kiểu bằng tên |
| `@ConditionalOnMissingBean(name = "myService")` | Thiếu bean có tên đã chỉ định | Khi ý định thật sự phụ thuộc vào bean name |
| `annotation = SomeMarker.class` | Thiếu bean mang annotation tương ứng | Cấu hình chuyên biệt theo marker |
| `search = SearchStrategy.CURRENT` | Chỉ xét context hiện tại | Trường hợp context cha–con cần fallback riêng cho con |
| `search = SearchStrategy.ALL` | Xét cả context hiện tại và context cha | Hành vi mặc định, tránh tạo trùng khi cha đã cung cấp bean |
| `ignored` / `ignoredType` | Bỏ qua một số kiểu bean trong quá trình dò | Trường hợp nâng cao, cần lý do rõ ràng |
| `parameterizedContainer` | Nhận diện kiểu được bao bởi generic container chỉ định | Ví dụ xem `NameRegistration<Name>` như ứng viên cho `Name` khi cấu hình yêu cầu |

Trong ứng dụng thông thường, kiểm tra theo **kiểu của dịch vụ mà consumer cần** là dễ hiểu nhất. Kiểm tra theo tên có thể khiến fallback vẫn xuất hiện dù người dùng đã đăng ký bean cùng kiểu với tên khác; khi đó các điểm injection theo kiểu có thể bị mơ hồ.

Nếu sử dụng cả `value`, `name` hoặc các tiêu chí khác, cần nhớ điều kiện chỉ khớp khi các yêu cầu “thiếu” đều thực sự được đáp ứng. Đừng tự diễn giải rằng một bean phải vừa đúng tên vừa đúng kiểu thì mới được tính là “đã tồn tại”.

### Phạm vi context cha–con

Mặc định `search = SearchStrategy.ALL`. Trong ứng dụng có parent context, một `GreetingService` ở cha có thể khiến fallback ở con **không được đăng ký**. Chỉ dùng `SearchStrategy.CURRENT` khi mỗi context thực sự cần một bản riêng và hành vi đó được thiết kế rõ. Đừng đổi search strategy để che một lỗi cấu trúc bean.

## 7. Phân biệt với các annotation và lựa chọn bean khác

- `@ConditionalOnBean(Foo.class)`: chỉ đăng ký phần cấu hình khi **đã có** bean `Foo` phù hợp.
- `@ConditionalOnMissingBean(Foo.class)`: chỉ đăng ký fallback khi **chưa có** bean `Foo` phù hợp.
- `@Primary`: ưu tiên **một bean trong số những bean đã tồn tại** khi injection theo kiểu gặp nhiều ứng viên; không quyết định có tạo fallback hay không.
- `@Qualifier`: chỉ định ứng viên tiêm phụ thuộc; không thay thế việc kiểm tra bean đã tồn tại.
- `@ConditionalOnProperty`: dựa trên thuộc tính cấu hình; có thể kết hợp với `@ConditionalOnMissingBean` nếu muốn cả điều kiện bật tính năng lẫn cơ chế cho phép người dùng thay thế.
- `spring.main.allow-bean-definition-overriding`: điều khiển việc ghi đè **định nghĩa trùng tên**; không phải cách thiết kế fallback và không nên dùng để chữa vấn đề có nhiều bean cùng kiểu.

Ví dụ cần đồng thời “tính năng được bật” và “chưa có dịch vụ tùy chỉnh” (đoạn minh họa trong auto-configuration):

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return name -> "Hello, " + name;
}
~~~

Nếu `app.greeting.enabled=false`, fallback sẽ bị tắt ngay cả khi không có `GreetingService`; nếu property cho phép nhưng người dùng đã cung cấp service thì fallback cũng bị bỏ qua.

## 8. Lỗi thường gặp và cách tìm nguyên nhân

1. **Đặt điều kiện trong cấu hình người dùng rồi mặc định rằng mọi bean khác đã xuất hiện.** Điều kiện chỉ thấy những định nghĩa bean được xử lý **cho tới lúc đánh giá**. Với fallback tái sử dụng, ưu tiên đặt trong auto-configuration. Nếu phụ thuộc auto-configuration khác, khai báo thứ tự phù hợp.
2. **Đặt điều kiện theo tên nhưng nghiệp vụ cần kiểm tra theo kiểu.** Tên khác vẫn có thể làm phát sinh bean thứ hai cùng interface. Sửa bằng `@ConditionalOnMissingBean(MyService.class)` khi mục tiêu là một implementation mặc định cho kiểu dịch vụ.
3. **Khai báo `@Bean` trả về `Object` hoặc interface quá chung.** Spring Boot kiểm tra thông tin kiểu được khai báo/biết tại thời điểm xử lý. Khai báo kiểu trả về có ý nghĩa và kiểm tra thử nhánh có bean tùy chỉnh.
4. **Cho rằng `@Primary` làm điều kiện “missing” khớp.** Có bất kỳ bean phù hợp nào vẫn là “đã có”; `@Primary` chỉ ảnh hưởng cách chọn giữa các ứng viên khi tiêm.
5. **Nhầm điều kiện bean với việc bean đã được khởi tạo.** Một bean definition phù hợp có thể chặn fallback trước khi đối tượng tương ứng được tạo.
6. **Không nhận ra bean ở parent context.** Kiểm tra `search` và cấu trúc context nếu không thấy fallback được đăng ký.
7. **Quên đăng ký auto-configuration của thư viện trong file imports.** Khi đó lớp có thể không được Boot tự nạp; đừng chẩn đoán nhầm là điều kiện “missing” không hoạt động.

Để điều tra, chạy ứng dụng với tùy chọn `--debug` và xem **Condition Evaluation Report**: phần matched/unmatched conditions thường cho biết có bean nào khiến `OnBeanCondition` không khớp. Trong test, có thể dùng `ConditionEvaluationReportLoggingListener` cùng `ApplicationContextRunner` để in báo cáo khi cần. Kiểm tra tên và kiểu bean được ghi nhận, rồi đối chiếu với thời điểm và phạm vi xử lý của auto-configuration.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Auto-configuration khai báo `@ConditionalOnMissingBean(PaymentGateway.class)`. Ứng dụng định nghĩa bean `stripeGateway` kiểu `PaymentGateway`. Bean mặc định có được tạo không?

**Đáp án:** Không. Điều kiện kiểm tra theo **kiểu**, nên tên `stripeGateway` không làm bean đó bị bỏ qua.

**Câu 2.** Có hai `PaymentGateway`, trong đó một bean là `@Primary`. Annotation missing-bean có đăng ký fallback để “có thêm lựa chọn” không?

**Đáp án:** Không. Hai bean đã tồn tại. `@Primary` chỉ giúp lựa chọn khi cần inject một bean theo kiểu.

**Câu 3.** Tại sao nên viết test cả khi không có bean người dùng lẫn khi có bean người dùng?

**Đáp án:** Nhánh đầu kiểm tra mặc định được cung cấp; nhánh sau xác minh thư viện thực sự **back off** để cấu hình người dùng thắng. Chỉ test một nhánh có thể bỏ sót lỗi thứ tự xử lý hoặc sai tiêu chí kiểm tra.

## 10. Ghi nhớ khi áp dụng

`@ConditionalOnMissingBean` giúp auto-configuration cung cấp giá trị mặc định **chỉ khi chưa có bean phù hợp**. Hãy xác định rõ kiểu dịch vụ cần kiểm tra, để bean của ứng dụng được xử lý trước fallback, khai báo thứ tự nếu phụ thuộc auto-configuration khác, và xác minh cả hai nhánh bằng `ApplicationContextRunner`. Khi có nhiều bean cùng kiểu, giải quyết bài toán chọn ứng viên bằng mô hình injection phù hợp; đừng kỳ vọng annotation “missing” tự chọn hộ.

### Tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
