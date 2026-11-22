# Giữ tích hợp mới thành phần tùy chọn có kiểm thử riêng

Khi mở rộng Springdoc, một customizer, model converter, security scheme hoặc nhóm tài liệu mới có thể ảnh hưởng đến toàn bộ OpenAPI document của ứng dụng. Nếu tích hợp đó chỉ phục vụ một nhóm hệ thống hoặc một tính năng chưa phải mặc định, hãy thiết kế nó thành thành phần tùy chọn và kiểm thử riêng cả hai trạng thái bật/tắt.

Một tích hợp tùy chọn cần đáp ứng ba điều kiện:

1. **Không bật ngoài ý muốn**: khi chưa cấu hình, tích hợp không làm thay đổi document hiện tại.
2. **Không tạo phụ thuộc bắt buộc**: nếu thư viện mở rộng hoặc tính năng Springdoc tương ứng không có trên classpath, ứng dụng vẫn khởi động được khi tính năng không được yêu cầu.
3. **Có kiểm thử độc lập**: kiểm tra điều kiện kích hoạt, hành vi khi bật, hành vi khi tắt và ảnh hưởng thực tế lên OpenAPI document.

Trong bài này, ta xây dựng một tích hợp minh họa: thêm header `X-Request-Id` vào các operation được đánh dấu `@AuditedOperation`. Customizer chỉ hoạt động khi property `acme.openapi.audit.enabled=true`; khi tắt, OpenAPI document giữ nguyên.

## 1. Tách điều kiện bật tính năng khỏi logic tích hợp

Không nên tạo customizer vô điều kiện rồi kiểm tra property ở nhiều nơi trong lambda. Hãy đặt điều kiện tại cấu hình bean để Spring chỉ đăng ký bean khi tính năng được bật.

```yaml
acme:
  openapi:
    audit:
      enabled: false
```

Giá trị mặc định là `false`. Chỉ môi trường hoặc ứng dụng thực sự cần tích hợp mới bật:

```yaml
acme:
  openapi:
    audit:
      enabled: true
```

`acme.openapi.audit.enabled` là property do ứng dụng mở rộng tự định nghĩa, không phải property có sẵn của Springdoc. Việc dùng namespace riêng giúp tránh nhầm với cấu hình chuẩn `springdoc.*` và làm rõ chủ sở hữu của tính năng.

Với `@ConditionalOnProperty`, mặc định điều kiện chỉ khớp khi property có giá trị `true` đúng như khai báo `havingValue="true"`. Nếu property bị bỏ qua, bean không được tạo. Không đặt `matchIfMissing=true` cho một tính năng được yêu cầu là optional/off-by-default.

## 2. Tạo marker annotation để chọn operation

Tích hợp không nên sửa tất cả operation nếu yêu cầu chỉ áp dụng cho một nhóm endpoint. Marker annotation giúp controller chủ động chọn operation cần công bố header.

```java
package com.example.openapi.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
}
```

Annotation có `RUNTIME` retention vì `OperationCustomizer` kiểm tra metadata của handler method khi Springdoc xây dựng OpenAPI operation. Nếu dùng retention `SOURCE` hoặc `CLASS`, reflection ở runtime không thể đọc annotation theo cách này.

## 3. Viết `OperationCustomizer` theo hướng idempotent

`OperationCustomizer` cho phép điều chỉnh một OpenAPI `Operation` dựa trên `HandlerMethod`. Tích hợp chỉ thêm `X-Request-Id` khi method có `@AuditedOperation`.

```java
package com.example.openapi.audit;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;
import org.springdoc.core.customizers.OperationCustomizer;

import java.util.ArrayList;
import java.util.List;

public class AuditHeaderOperationCustomizer implements OperationCustomizer {

    private static final String HEADER_NAME = "X-Request-Id";

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        boolean audited = AnnotatedElementUtils.hasAnnotation(
            handlerMethod.getMethod(), AuditedOperation.class
        );

        if (!audited) {
            return operation;
        }

        List<Parameter> parameters = operation.getParameters();
        if (parameters == null) {
            parameters = new ArrayList<>();
            operation.setParameters(parameters);
        }

        boolean alreadyDeclared = parameters.stream().anyMatch(parameter ->
            HEADER_NAME.equalsIgnoreCase(parameter.getName())
                && "header".equalsIgnoreCase(parameter.getIn())
        );

        if (!alreadyDeclared) {
            parameters.add(new Parameter()
                .name(HEADER_NAME)
                .in("header")
                .required(false)
                .description("Mã tương quan tùy chọn do client gửi để truy vết request.")
                .schema(new StringSchema()));
        }

        return operation;
    }
}
```

Customizer có tính idempotent: nếu operation đã khai báo header cùng tên và vị trí, nó không thêm bản sao. Điều này hữu ích khi controller đã mô tả header bằng annotation hoặc một customizer khác đã thêm nó.

`OperationCustomizer` chạy trong quá trình tạo OpenAPI model. Không đặt I/O, gọi dịch vụ ngoài hoặc truy vấn database trong method `customize`; các thao tác đó làm document generation chậm và có thể khiến endpoint tài liệu phụ thuộc vào trạng thái hệ thống ngoài. Tất cả metadata cần thiết nên được lấy từ handler method, cấu hình hoặc bean có sẵn.

## 4. Đăng ký customizer bằng cấu hình có điều kiện

Nếu tích hợp nằm ngay trong ứng dụng, cấu hình đơn giản có thể như sau:

```java
package com.example.openapi.audit;

import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "acme.openapi.audit",
    name = "enabled",
    havingValue = "true"
)
public class AuditOpenApiConfiguration {

    @Bean
    OperationCustomizer auditHeaderOperationCustomizer() {
        return new AuditHeaderOperationCustomizer();
    }
}
```

Khi property không có hoặc là `false`, cấu hình không tạo customizer. Khi property là `true`, bean được đăng ký và Springdoc sử dụng nó khi xây dựng operation.

Nếu ứng dụng luôn có Springdoc trên classpath, chỉ cần điều kiện property là đủ. Nếu đang viết một thư viện mở rộng có thể được dùng trong ứng dụng không cài Springdoc, cần thêm điều kiện classpath như phần tiếp theo.

## 5. Giữ thư viện mở rộng optional khi Springdoc không có trên classpath

Một starter hoặc thư viện dùng lại có thể muốn cung cấp tính năng audit OpenAPI nhưng không bắt buộc mọi consumer phải dùng Springdoc. Khi đó, cần bảo đảm cả dependency graph lẫn auto-configuration đều optional.

Với Maven, khai báo dependency Springdoc là optional trong module tích hợp:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
    <optional>true</optional>
</dependency>
```

`optional=true` ngăn Maven truyền dependency này một cách tự động sang consumer của thư viện. Ứng dụng muốn dùng tính năng cần chủ động thêm starter Springdoc phù hợp với MVC hoặc WebFlux. Nó không tự động làm classpath condition; auto-configuration vẫn phải xử lý trường hợp class Springdoc không tồn tại.

Với Gradle, chọn cấu hình publication/feature variant phù hợp để consumer không bị kéo dependency Springdoc ngoài ý muốn. `compileOnly` có thể dùng để biên dịch thư viện khi Springdoc không được đóng gói như dependency runtime mặc định, nhưng cần kiểm tra metadata publication và cách consumer bật feature. Đừng giả định `compileOnly` tự tạo một optional feature có thể bật lại cho mọi loại repository.

## 6. Auto-configuration có điều kiện classpath

Với Spring Boot 3, có thể đăng ký auto-configuration của thư viện. Đặt điều kiện Springdoc trên nested configuration để class chứa kiểu `OperationCustomizer` chỉ được nạp khi class Springdoc tồn tại.

```java
package com.example.openapi.audit.autoconfigure;

import com.example.openapi.audit.AuditHeaderOperationCustomizer;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AuditOpenApiAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springdoc.core.customizers.OperationCustomizer")
    @ConditionalOnProperty(
        prefix = "acme.openapi.audit",
        name = "enabled",
        havingValue = "true"
    )
    static class SpringdocAuditConfiguration {

        @Bean
        @ConditionalOnMissingBean(name = "auditHeaderOperationCustomizer")
        OperationCustomizer auditHeaderOperationCustomizer() {
            return new AuditHeaderOperationCustomizer();
        }
    }
}
```

Điều kiện classpath được viết bằng tên class để outer auto-configuration không cần resolve kiểu Springdoc khi classpath không có dependency. Nested configuration giữ method signature tham chiếu `OperationCustomizer` bên trong phạm vi đã được bảo vệ.

Không đặt `@ConditionalOnClass(OperationCustomizer.class)` trực tiếp trên một method bean trong outer configuration rồi giả định mọi class-loading case đều an toàn. Khi một dependency thực sự optional, cấu trúc configuration phải tránh nạp các kiểu optional trước khi condition được đánh giá.

`@ConditionalOnMissingBean` ở ví dụ dùng tên bean cụ thể vì `OperationCustomizer` là extension point cho phép nhiều customizer cùng tồn tại. Dùng `@ConditionalOnMissingBean(OperationCustomizer.class)` sẽ có thể ngăn customizer của thư viện được đăng ký chỉ vì ứng dụng đã có một customizer khác, làm mất khả năng kết hợp. Chỉ dùng điều kiện theo type khi ý nghĩa thực sự là “chỉ có một bean thuộc loại này”.

Đăng ký auto-configuration trong file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file:

```text
com.example.openapi.audit.autoconfigure.AuditOpenApiAutoConfiguration
```

`@AutoConfiguration` và file `AutoConfiguration.imports` được hỗ trợ từ Spring Boot 2.7 trở lên và tiếp tục dùng trong Boot 3. Với Spring Boot 2.6 trở xuống, cách đăng ký auto-configuration thường dùng `spring.factories`; hãy xác định phiên bản tối thiểu mà starter hỗ trợ rồi cung cấp metadata tương ứng.

## 7. Sử dụng annotation trong controller

Controller đánh dấu rõ operation cần header audit:

```java
package com.example.orders.api;

import com.example.openapi.audit.AuditedOperation;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    @AuditedOperation
    @Operation(summary = "Lấy thông tin đơn hàng")
    OrderResponse getOrder(@PathVariable Long id) {
        return orderService.getOrder(id);
    }

    @GetMapping("/api/orders/health")
    @Operation(summary = "Kiểm tra trạng thái API đơn hàng")
    String health(@RequestParam(required = false) String detail) {
        return detail == null ? "ok" : detail;
    }
}
```

Khi tích hợp được bật, operation `GET /api/orders/{id}` có header tùy chọn `X-Request-Id`; operation health không có header này. Khi tích hợp tắt, cả hai operation vẫn được Springdoc mô tả theo metadata gốc.

Header được thêm vào OpenAPI document không tự động làm controller đọc hoặc validate header. Nếu runtime cần sử dụng `X-Request-Id`, controller/filter/interceptor phải triển khai hành vi tương ứng. OpenAPI metadata chỉ mô tả hợp đồng; nó không tự thay đổi xử lý HTTP.

Ví dụ dùng annotated controller với `HandlerMethod`. Nếu ứng dụng dùng WebFlux functional routes (`RouterFunction`), route không nhất thiết đi qua cùng metadata handler method; hãy mô tả operation bằng `@RouterOperation`/`@RouterOperations` hoặc functional DSL của Springdoc và kiểm thử riêng document của route đó.

## 8. Kiểm thử điều kiện bật/tắt bằng `ApplicationContextRunner`

`ApplicationContextRunner` giúp kiểm tra auto-configuration trong một context nhỏ mà không phải khởi động toàn bộ web server. Đây là nơi phù hợp để kiểm tra property, classpath condition và bean registration.

Các test dưới đây dùng JUnit 5, AssertJ và Spring Boot Test; có thể thêm dependency test:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

```java
package com.example.openapi.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class AuditOpenApiAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(AuditOpenApiAutoConfiguration.class));

    @Test
    void disabledByDefault() {
        contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
        });
    }

    @Test
    void registersCustomizerWhenEnabledAndSpringdocIsPresent() {
        contextRunner
            .withPropertyValues("acme.openapi.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasBean("auditHeaderOperationCustomizer");
            });
    }

    @Test
    void backsOffWhenSpringdocCustomizerTypeIsMissing() {
        contextRunner
            .withClassLoader(new FilteredClassLoader("org.springdoc.core.customizers"))
            .withPropertyValues("acme.openapi.audit.enabled=true")
            .run(context -> {
                assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
                assertThat(context).hasNotFailed();
            });
    }

    @Test
    void explicitFalseKeepsIntegrationDisabled() {
        contextRunner
            .withPropertyValues("acme.openapi.audit.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean("auditHeaderOperationCustomizer");
            });
    }
}
```

Các test này xác minh bốn trường hợp quan trọng: property vắng mặt, bật rõ ràng, thiếu class Springdoc và tắt rõ ràng. Test classpath missing đặc biệt có giá trị với starter optional: nó chứng minh ứng dụng không dùng Springdoc vẫn tạo được context khi feature chưa được bật.

Nếu test module luôn có Springdoc trên test classpath, `FilteredClassLoader` giúp mô phỏng trường hợp dependency không tồn tại ở runtime. Giữ auto-configuration test nhỏ và không cần khởi động web server để lỗi điều kiện được phát hiện nhanh.

## 9. Kiểm thử ảnh hưởng thực tế lên OpenAPI document

Chỉ kiểm tra bean tồn tại là chưa đủ. Một customizer có thể được đăng ký nhưng không được Springdoc gọi, hoặc thêm parameter sai operation. Cần integration test đọc document thực tế.

Test khi bật:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "acme.openapi.audit.enabled=true")
@AutoConfigureMockMvc
class AuditOpenApiEnabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsAuditHeaderOnlyToMarkedOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.parameters[*].name"
            ).value(hasItem("X-Request-Id")))
            .andExpect(jsonPath(
                "$.paths['/api/orders/health'].get.parameters[*].name"
            ).value(not(hasItem("X-Request-Id"))));
    }
}
```

Operation health trong ví dụ có query parameter `detail`, vì vậy test kiểm tra rằng operation có parameter nhưng không chứa `X-Request-Id`. Mục tiêu là xác nhận marker chỉ ảnh hưởng operation được chọn.

Test khi tắt:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "acme.openapi.audit.enabled=false")
@AutoConfigureMockMvc
class AuditOpenApiDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsBaseOpenApiWithoutAuditHeader() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.parameters[*].name"
            ).value(not(hasItem("X-Request-Id"))));
    }
}
```

Test trên kiểm tra danh sách parameter của operation `GET`. Trong OpenAPI, parameter cũng có thể được khai báo ở cấp Path Item; nếu extension của dự án hỗ trợ cả hai vị trí, hãy parse document thành object rồi hợp nhất danh sách theo quy tắc OpenAPI trước khi assertion. Ví dụ kiểm tra nhanh bằng `jq` sau khi lưu file:

```bash
jq '.paths["/api/orders/{id}"].get.parameters' openapi.json
```

Với test ổn định, nên xác minh danh sách parameter sau khi gộp path-level và operation-level theo quy tắc OpenAPI, tránh giả định tất cả parameter luôn nằm ở một vị trí.

## 10. Tách test unit cho customizer

Ngoài context test và integration test, có thể kiểm tra logic customizer bằng unit test thuần. Test này xác minh marker annotation, parameter được thêm và tính idempotent.

```java
package com.example.openapi.audit;

import io.swagger.v3.oas.models.Operation;
import org.junit.jupiter.api.Test;
import org.springframework.web.method.HandlerMethod;

import static org.assertj.core.api.Assertions.assertThat;

class AuditHeaderOperationCustomizerTests {

    private final AuditHeaderOperationCustomizer customizer =
        new AuditHeaderOperationCustomizer();

    @Test
    void addsHeaderForAuditedMethodOnly() throws Exception {
        HandlerMethod auditedMethod = new HandlerMethod(
            new SampleController(),
            SampleController.class.getMethod("audited")
        );
        Operation operation = new Operation();

        customizer.customize(operation, auditedMethod);

        assertThat(operation.getParameters())
            .extracting(parameter -> parameter.getName())
            .containsExactly("X-Request-Id");
    }

    @Test
    void doesNotAddDuplicateHeader() throws Exception {
        HandlerMethod auditedMethod = new HandlerMethod(
            new SampleController(),
            SampleController.class.getMethod("audited")
        );
        Operation operation = new Operation();

        customizer.customize(operation, auditedMethod);
        customizer.customize(operation, auditedMethod);

        assertThat(operation.getParameters())
            .extracting(parameter -> parameter.getName())
            .containsExactly("X-Request-Id");
    }

    static class SampleController {
        @AuditedOperation
        public void audited() {
        }
    }
}
```

Unit test không thay thế integration test vì nó không chứng minh Springdoc đã gọi customizer hoặc serialize parameter vào document. Nó chỉ kiểm tra logic biến đổi operation trong phạm vi nhỏ.

## 11. Kiểm thử tương thích với nhiều phiên bản Springdoc

Nếu thư viện mở rộng được dùng bởi nhiều ứng dụng, cần xác định rõ phiên bản Spring Boot và Springdoc được hỗ trợ. Không giả định mọi major version có cùng package, method signature hoặc model behavior.

Một ma trận kiểm thử có thể gồm:

| Biến thể | Mục tiêu |
|---|---|
| Spring Boot 3 + Springdoc v2 | Phiên bản nền tảng mà extension hỗ trợ |
| Phiên bản Springdoc thấp nhất được hỗ trợ | Phát hiện API customizer hoặc model khác biệt |
| Phiên bản Springdoc mới nhất trong major được hỗ trợ | Phát hiện thay đổi tương thích trong minor/patch |
| Springdoc không có trên classpath | Xác nhận optional auto-configuration không làm hỏng context |
| Property không khai báo | Xác nhận mặc định off |
| Property bật | Xác nhận customizer có tác dụng |
| Property tắt | Xác nhận document không bị biến đổi |

Khóa dependency trong từng test matrix job. Nếu build dùng Maven/Gradle dependency management của Spring Boot, không ép `swagger-core` hoặc `swagger-models` sang một version độc lập khi chưa kiểm tra compatibility với Springdoc.

## 12. Kiểm thử không gây ảnh hưởng khi tích hợp tắt

Một tính năng optional phải có test cho negative path. Khi `enabled=false` hoặc property không tồn tại:

- Không đăng ký customizer bean.
- Không thêm parameter/schema/security metadata ngoài ý muốn.
- Không gọi external service hoặc tạo scheduled task.
- Không thay đổi `OpenAPI` bean hoặc group mặc định.
- Không làm tăng startup failure do thiếu dependency optional.
- Không làm thay đổi response runtime của controller.

Đặc biệt, đừng chỉ assert bean vắng mặt. Hãy kiểm tra document đầu ra không có phần metadata của extension. Nếu extension có side effect ngoài OpenAPI, kiểm tra thêm side effect đó bằng fake/mock hoặc spy.

## 13. Tách optional dependency khỏi optional behavior

Hai khái niệm này cần được thiết kế độc lập:

| Khái niệm | Câu hỏi | Cơ chế |
|---|---|---|
| Optional dependency | Ứng dụng có thể chạy khi thư viện mở rộng không có trên classpath không? | Maven optional/Gradle feature metadata, `@ConditionalOnClass` |
| Optional behavior | Ứng dụng có thể giữ tích hợp tắt dù dependency đã có không? | `@ConditionalOnProperty`, default off |

Một ứng dụng có thể đã cài Springdoc nhưng không muốn thêm audit header; khi đó dependency có mặt nhưng property tắt. Ngược lại, một ứng dụng không dùng Springdoc có thể vẫn dùng các phần khác của thư viện; khi đó classpath condition phải ngăn cấu hình Springdoc được nạp.

Đừng dùng `@ConditionalOnProperty` để thay thế classpath condition trong thư viện optional. Nếu class không tồn tại mà configuration vẫn tham chiếu đến nó, ứng dụng có thể lỗi `NoClassDefFoundError` khi đọc cấu hình.

## 14. Tổ chức package và module để dễ bảo trì

Với một tích hợp nhỏ nằm trong ứng dụng:

```text
src/main/java/
  com/example/openapi/audit/
    AuditedOperation.java
    AuditHeaderOperationCustomizer.java
    AuditOpenApiConfiguration.java
```

Với thư viện/starter có thể tái sử dụng:

```text
openapi-audit-spring-boot-autoconfigure/
  src/main/java/.../AuditOpenApiAutoConfiguration.java
  src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

openapi-audit-spring-boot-starter/
  pom.xml
```

Module autoconfigure chứa logic và điều kiện; starter gom dependency cùng cấu hình publication. Tách module chỉ có lợi khi nhiều ứng dụng thực sự cần dùng lại hoặc cần quản lý dependency optional. Với một feature duy nhất trong một service, cấu hình có điều kiện trong chính ứng dụng có thể đơn giản và dễ kiểm soát hơn.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tích hợp luôn bật | `matchIfMissing=true` hoặc property mặc định true | Dùng `havingValue="true"` và mặc định false |
| Ứng dụng không có Springdoc vẫn lỗi startup | Auto-configuration nạp type Springdoc trước khi condition được kiểm tra | Đưa type optional vào nested configuration được bảo vệ bằng `@ConditionalOnClass(name=...)` |
| Consumer bị kéo Springdoc dù không dùng | Dependency được khai báo như dependency bắt buộc | Đánh dấu optional hoặc cấu hình feature publication đúng |
| Customizer không được gọi | Bean không được đăng ký hoặc package/config không được scan/import | Kiểm tra condition evaluation và bean registration |
| Header xuất hiện trên mọi operation | Customizer không kiểm tra marker annotation | Chỉ biến đổi handler method được đánh dấu |
| Header bị lặp | Customizer không kiểm tra parameter đã tồn tại | Làm logic idempotent trước khi thêm |
| Có bean nhưng document không thay đổi | Test chỉ kiểm tra context, chưa kiểm tra OpenAPI output | Thêm integration test gọi `/v3/api-docs` |
| Tắt property nhưng document vẫn thay đổi | Một customizer khác hoặc annotation trực tiếp cũng thêm metadata | Kiểm tra toàn bộ extension point và baseline document |
| `@ConditionalOnMissingBean(OperationCustomizer.class)` ngăn customizer khác | Extension point cho phép nhiều bean cùng loại | Dùng điều kiện theo tên/marker bean hoặc bỏ điều kiện nếu không cần |
| Tích hợp làm document generation chậm | Customizer gọi I/O hoặc quét dữ liệu runtime | Chỉ dùng metadata có sẵn; profile customizer bằng profiler |
| Nâng Springdoc làm lỗi compile | API/package model thay đổi giữa version | Dùng version matrix và kiểm tra dependency alignment |

## 16. Checklist thêm tích hợp Springdoc tùy chọn

- [ ] Có property riêng cho tính năng và mặc định là `false`.
- [ ] Tích hợp không được kích hoạt chỉ vì dependency đã có trên classpath.
- [ ] Thư viện mở rộng không kéo Springdoc thành dependency bắt buộc nếu consumer không cần.
- [ ] Auto-configuration có `@ConditionalOnClass` khi Springdoc là dependency optional.
- [ ] Các type Springdoc chỉ xuất hiện trong nested configuration được bảo vệ khi cần.
- [ ] Bean được đăng ký bằng điều kiện property rõ ràng.
- [ ] Customizer chỉ tác động đến operation được chọn.
- [ ] Customizer idempotent và không tạo duplicate parameter/schema.
- [ ] Không gọi network/database hoặc tạo side effect trong lúc tạo OpenAPI model.
- [ ] Có unit test cho logic customizer.
- [ ] Có `ApplicationContextRunner` test cho default off, explicit on, explicit off và missing classpath.
- [ ] Có integration test kiểm tra document thực tế khi bật và tắt.
- [ ] Có test xác nhận controller/API runtime không bị thay đổi ngoài ý muốn.
- [ ] Đã xác định ma trận Spring Boot/Springdoc được hỗ trợ.
- [ ] Đã kiểm tra dependency tree và metadata publication.

Giữ tích hợp mới thành thành phần tùy chọn bằng cách tách hai điều kiện: dependency có mặt trên classpath và tính năng được bật bằng property. Springdoc customizer nên được đăng ký có điều kiện, chỉ thay đổi operation được chọn và tránh side effect khi tạo document. Với thư viện dùng lại, classpath condition cùng dependency publication optional giúp consumer không dùng Springdoc vẫn khởi động được. Cuối cùng, kiểm thử riêng logic customizer, auto-configuration và OpenAPI document ở cả trạng thái bật/tắt để chứng minh tích hợp mới không làm thay đổi hợp đồng hiện tại ngoài phạm vi được yêu cầu.

## Tài liệu tham khảo

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot – `@ConditionalOnClass` and `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations)
- [Spring Boot – Testing Auto-configuration with `ApplicationContextRunner`](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Springdoc OpenAPI – Customization](https://springdoc.org/#how-can-i-customise-the-openapi-description)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
