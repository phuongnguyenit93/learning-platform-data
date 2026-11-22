# `parameterizedContainer`: nhận diện kiểu bean qua lớp chứa generic trong Spring Boot

## 1. Vấn đề cần giải quyết

Trong Spring Boot Auto Configuration, điều kiện dựa trên bean thường kiểm tra xem `BeanFactory` đã có một bean thuộc kiểu được yêu cầu hay chưa. Tuy nhiên, một thành phần có thể được đăng ký gián tiếp bên trong một *bean có kiểu generic*. Ví dụ, ứng dụng không đăng ký bean `PaymentHandler` riêng lẻ mà đăng ký bean `HandlerRegistration<PaymentHandler>` để chứa và quản lý nó.

Nếu chỉ viết `@ConditionalOnBean(PaymentHandler.class)`, điều kiện thông thường sẽ tìm bean kiểu `PaymentHandler`, không coi mọi `HandlerRegistration<PaymentHandler>` là một `PaymentHandler` độc lập. Thuộc tính `parameterizedContainer` cho phép **mở rộng tập kiểu được kiểm tra**: ngoài bean trực tiếp thuộc kiểu đích, Spring Boot còn xét bean thuộc lớp chứa được chỉ định, với tham số generic tương ứng kiểu đích.

Đây là thuộc tính của `@ConditionalOnBean` và `@ConditionalOnMissingBean`, có từ Spring Boot 2.1.0. Tên thuộc tính viết chính xác là **`parameterizedContainer`** (số ít), kiểu khai báo API là `Class<?>[]` và giá trị mặc định là mảng rỗng `{}`.

## 2. Cú pháp và ý nghĩa chính xác

Giả sử tồn tại `Service` và lớp chứa một tham số kiểu `Registration<T>`. Khi khai báo:

- `@ConditionalOnBean(value = Service.class, parameterizedContainer = Registration.class)`: điều kiện thỏa nếu đã có bean `Service` trực tiếp **hoặc** bean `Registration<Service>` có thông tin kiểu generic phù hợp.
- `@ConditionalOnMissingBean(value = Service.class, parameterizedContainer = Registration.class)`: điều kiện thỏa nếu **không có** cả bean `Service` trực tiếp lẫn bean `Registration<Service>` được nhận diện.
- Nếu bỏ `parameterizedContainer`, các `Registration<Service>` không được bổ sung vào nhóm ứng viên bằng cơ chế này.
- Có thể truyền nhiều lớp chứa, ví dụ `parameterizedContainer = {Registration.class, Optional.class}`; `Optional<Service>` chỉ được tính nếu **chính Optional<Service> được đăng ký làm bean**, không phải vì Spring có hỗ trợ inject `Optional<Service>`.

Lưu ý: `Service.class` biểu thị **kiểu bean cần tìm**; `Registration.class` biểu thị **kiểu lớp chứa**. Không viết `Registration<Service>.class` vì Java không cho tạo class literal cho một kiểu đã gắn tham số generic.

### Bảng đối chiếu

Với điều kiện kiểm tra `Service.class` và (nếu có) lớp chứa `Registration.class`:

| Bean đã có trong context | `@ConditionalOnBean(Service.class)` | `@ConditionalOnBean(value=Service.class, parameterizedContainer=Registration.class)` | `@ConditionalOnMissingBean(value=Service.class, parameterizedContainer=Registration.class)` |
| --- | --- | --- | --- |
| Không có bean liên quan | Không khớp | Không khớp | Khớp |
| `Service` | Khớp | Khớp | Không khớp |
| `Registration<Service>` | Không khớp | Khớp | Không khớp |
| `Registration<String>` | Không khớp | Không khớp | Khớp |
| `Service` và `Registration<Service>` | Khớp | Khớp | Không khớp |

Bảng giả định bean đã được xử lý ở thời điểm kiểm tra, là ứng viên hợp lệ và kiểu generic khai báo đủ rõ. Kết quả dựa vào **định nghĩa kiểu bean**, không phải việc Spring mở hộp và tìm instance `Service` bên trong.

## 3. Cơ chế nhận diện trong `OnBeanCondition`

`@ConditionalOnBean` và `@ConditionalOnMissingBean` đều được xử lý bởi `OnBeanCondition` của Spring Boot:

1. Lấy kiểu đích từ `value`/`type` (hoặc suy ra từ kiểu trả về của phương thức `@Bean` trong trường hợp API cho phép).
2. Tìm các tên bean tương thích với kiểu đích trực tiếp.
3. Với từng lớp khai báo trong `parameterizedContainer`, tạo kiểu có thông tin generic, về mặt ý tưởng là `Registration<Service>`, qua `ResolvableType.forClassWithGenerics(...)`, rồi tìm bean phù hợp với kiểu đó.
4. Gộp ứng viên trực tiếp và ứng viên thông qua lớp chứa, sau đó áp dụng ngữ nghĩa "có bean" hoặc "không có bean" của annotation cùng các quy tắc lọc ứng viên.

`ResolvableType` cho phép Spring suy ra tham số generic từ metadata như chữ ký trả về `@Bean Registration<Service>`. Java có *type erasure* ở runtime nhưng thông tin kiểu đã khai báo trên phương thức/lớp vẫn có thể được Spring khai thác; Spring **không cần gọi `registration.wrapped()`** hay chạy logic ứng dụng để phát hiện kiểu phần tử.

`parameterizedContainer` không thay đổi bean đã đăng ký, không tạo bean `Service` mới, không tự unwrap khi dependency injection và không duyệt nội dung thực tế của `List`/`Map`. Kết quả điều kiện cũng không bảo đảm giá trị bên trong lớp chứa khác `null`: điều kiện kiểm tra metadata và bean definitions, không kiểm định dữ liệu bên trong.

## 4. Ví dụ chạy được với Java 17 và Spring Boot 3.5

Mục tiêu: tự động tạo `EnabledFeature` khi ứng dụng cung cấp `Service` trực tiếp **hoặc** `Registration<Service>`; nếu thiếu cả hai thì tạo `FallbackFeature`. Kiểm thử bốn trường hợp để thấy rõ khác biệt giữa kiểu generic đúng và sai.

Cấu trúc hai tệp:

- `pom.xml`
- `src/test/java/example/ParameterizedContainerTest.java`

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>parameterized-container-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**`src/test/java/example/ParameterizedContainerTest.java`**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ParameterizedContainerTest {

    interface Service {}

    static final class DefaultService implements Service {}

    // Lớp chứa: T thể hiện kiểu giá trị được bao bọc.
    record Registration<T>(T wrapped) {}

    record EnabledFeature() {}

    record FallbackFeature() {}

    @Configuration(proxyBeanMethods = false)
    static class WrapperUserConfiguration {
        @Bean
        Registration<Service> registration() {
            return new Registration<>(new DefaultService());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class WrongGenericUserConfiguration {
        @Bean
        Registration<String> registration() {
            return new Registration<>("khong phai Service");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class DirectServiceUserConfiguration {
        @Bean
        Service service() {
            return new DefaultService();
        }
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean(
            value = Service.class,
            parameterizedContainer = Registration.class
        )
        EnabledFeature enabledFeature() {
            return new EnabledFeature();
        }

        @Bean
        @ConditionalOnMissingBean(
            value = Service.class,
            parameterizedContainer = Registration.class
        )
        FallbackFeature fallbackFeature() {
            return new FallbackFeature();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(FeatureAutoConfiguration.class)
            );

    @Test
    void missingServiceCreatesFallback() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(EnabledFeature.class);
            assertThat(context).hasSingleBean(FallbackFeature.class);
        });
    }

    @Test
    void registrationOfServiceEnablesFeature() {
        runner.withUserConfiguration(WrapperUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(EnabledFeature.class);
                assertThat(context).doesNotHaveBean(FallbackFeature.class);
                // Service nằm trong Registration, không phải bean Service riêng.
                assertThat(context).doesNotHaveBean(Service.class);
            });
    }

    @Test
    void registrationOfStringDoesNotMatchService() {
        runner.withUserConfiguration(WrongGenericUserConfiguration.class)
            .run(context -> {
                assertThat(context).doesNotHaveBean(EnabledFeature.class);
                assertThat(context).hasSingleBean(FallbackFeature.class);
            });
    }

    @Test
    void directServiceAlsoEnablesFeature() {
        runner.withUserConfiguration(DirectServiceUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(EnabledFeature.class);
                assertThat(context).doesNotHaveBean(FallbackFeature.class);
            });
    }
}
```

Chạy tại thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** cả bốn test JUnit thành công, tiến trình Maven kết thúc với mã 0. Ví dụ không sử dụng `System.out.println`, nên không có chuỗi stdout cố định cần đối chiếu; các assertions chính là bằng chứng về sự hiện diện/vắng mặt của từng bean.

Giải thích điểm cốt lõi:

- `WrapperUserConfiguration` chỉ tạo bean `Registration<Service>`. Điều kiện có `parameterizedContainer` nhận diện tham số `Service` và kích hoạt `EnabledFeature`; nó không đăng ký thêm bean `Service`.
- `WrongGenericUserConfiguration` khai báo `Registration<String>`. Bean này không chứng minh có `Service`, nên nhánh fallback được chọn.
- `DirectServiceUserConfiguration` chứng minh điều kiện vẫn nhận diện bean `Service` trực tiếp: `parameterizedContainer` chỉ bổ sung cách tìm, không bắt buộc mọi bean phải nằm trong lớp chứa.
- Cả hai phương thức `enabledFeature()` và `fallbackFeature()` kiểm tra **cùng đối tượng mục tiêu** `Service.class`, nên không nên nhầm logic có/thiếu bean với kiểu marker mà chúng trả về.

## 5. Khi nào nên dùng

Dùng `parameterizedContainer` khi thư viện hoặc starter đăng ký thành phần bằng một **kiểu wrapper generic một tham số**, và auto configuration cần coi wrapper đó là dấu hiệu tồn tại của thành phần đích. Ví dụ phù hợp về mặt thiết kế là `Registration<Handler>`, `Holder<Plugin>` hoặc một wrapper do thư viện định nghĩa, miễn là chính wrapper đã được đăng ký làm bean với thông tin kiểu đầy đủ.

Không dùng thuộc tính này để thay cho truy vấn mọi kiểu generic. Chẳng hạn, `Map<String, Service>` có hai tham số kiểu; khai báo `parameterizedContainer = Map.class` không có nghĩa Spring sẽ tự tìm tham số `V` của Map. Trường hợp cần kiểm tra một vị trí generic cụ thể, điều kiện phức hợp hoặc giá trị thực, hãy cân nhắc viết `Condition` riêng và dùng `ResolvableType`/`BeanFactory` phù hợp.

## 6. Lưu ý và lỗi thường gặp

1. **Kiểu trả về quá rộng.** Với `@Bean Object registration()` hoặc kiểu raw `@Bean Registration registration()`, Spring không được cung cấp đầy đủ `Registration<Service>` trong chữ ký khai báo. Hãy ưu tiên kiểu trả về rõ ràng: `@Bean Registration<Service> registration()`.
2. **Nhầm wrapper với bean bên trong.** Điều kiện có thể khớp nhờ `Registration<Service>`, nhưng `@Autowired Service` không vì thế có một bean `Service` để inject. Muốn lấy giá trị được chứa, hãy inject `Registration<Service>` hoặc chủ động đăng ký `Service` như một bean khác.
3. **Quên nêu kiểu đích.** `parameterizedContainer = Registration.class` chỉ chỉ định wrapper. Khi cần tìm `Service`, hãy khai báo rõ `value = Service.class`; nếu để trống, quy tắc suy luận kiểu của phương thức `@Bean` có thể tạo điều kiện khác điều bạn tưởng.
4. **Nhầm nhiều kiểu đích với nhiều vị trí generic.** `value = {A.class, B.class}` không ánh xạ `A` vào tham số thứ nhất và `B` vào tham số thứ hai của một wrapper. Với `@ConditionalOnBean`, các yêu cầu phải cùng được đáp ứng; với `@ConditionalOnMissingBean`, không yêu cầu tương ứng nào được có mặt.
5. **Phụ thuộc thứ tự đăng ký bean.** Điều kiện chỉ thấy bean definitions đã được xử lý tới lúc đánh giá. Nên dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean` trong auto configuration, vì nó được xử lý sau cấu hình người dùng; nếu phụ thuộc auto configuration khác, hãy đặt thứ tự phù hợp bằng `@AutoConfiguration(after = ...)`.
6. **Bỏ qua khả năng được chọn làm ứng viên.** Spring Boot lọc các bean không phải ứng viên autowire/default theo quy tắc condition; có định nghĩa bean cùng tên hoặc wrapper cùng kiểu không đồng nghĩa chắc chắn điều kiện khớp.
7. **Hiểu sai phạm vi tìm kiếm.** `search` mặc định là `SearchStrategy.ALL` nên có thể xét context cha; `search = SearchStrategy.CURRENT` giới hạn ở context hiện tại. `parameterizedContainer` không thay đổi quy tắc phân cấp này.

## 7. Tự kiểm tra nhanh

- Có duy nhất bean `Registration<Service>` và annotation là `@ConditionalOnBean(Service.class)`: **không khớp theo nhánh wrapper**. Thêm `parameterizedContainer = Registration.class`: **khớp**.
- Có bean `Registration<String>`, annotation yêu cầu `Service.class` cùng wrapper `Registration.class`: **không khớp**, vì kiểu generic bên trong không tương ứng.
- Có bean `Service` trực tiếp: điều kiện `@ConditionalOnBean(value = Service.class, parameterizedContainer = Registration.class)` vẫn **khớp**, dù không tồn tại wrapper.
- Sau khi điều kiện khớp vì wrapper, có thể inject `Service` trực tiếp không? **Không thể suy ra như vậy**; cần có bean `Service` riêng hoặc dùng wrapper để truy cập giá trị.

## Tài liệu tham khảo chính thức

- Spring Boot API — `@ConditionalOnBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Creating Your Own Auto-configuration (bean conditions, thứ tự xử lý, `ApplicationContextRunner`): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Ghi nhớ:** `parameterizedContainer` giúp điều kiện kiểu bean nhận diện thêm `Registration<T>` như một nguồn thông tin về `T`. Nó không biến `T` thành một bean riêng và không kiểm tra đối tượng `T` ở bên trong wrapper.
