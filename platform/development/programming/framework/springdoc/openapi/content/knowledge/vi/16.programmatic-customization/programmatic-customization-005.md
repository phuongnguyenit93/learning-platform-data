# `OperationCustomizer` và thông tin `HandlerMethod`

Springdoc tự tạo metadata OpenAPI từ controller Spring MVC, nhưng đôi khi nhóm phát triển cần áp dụng quy tắc chung dựa trên chính method đang xử lý request. Ví dụ, operation thuộc nhóm đối tác cần có extension `x-audience: partner`; endpoint cũ cần được đánh dấu deprecated theo annotation nội bộ; hoặc một header bắt buộc theo quy ước cần được bổ sung vào tài liệu.

`OperationCustomizer` cung cấp điểm mở rộng cho từng operation. Callback nhận đối tượng `Operation` mà Springdoc đang xây dựng cùng `HandlerMethod` tương ứng của Spring MVC. Nhờ `HandlerMethod`, customizer có thể đọc class controller, Java method, tham số, kiểu trả về và annotation để điều chỉnh metadata operation một cách có ngữ cảnh.

## 1. `OperationCustomizer` hoạt động như thế nào?

`OperationCustomizer` thuộc package `org.springdoc.core.customizers`. Đây là functional interface với phương thức:

```java
Operation customize(Operation operation, HandlerMethod handlerMethod);
```

Hai tham số có vai trò khác nhau:

- `operation` là model OpenAPI của operation đang được tạo. Nó chứa summary, description, operationId, tags, parameters, request body, responses, security và extensions.
- `handlerMethod` là thông tin handler của Spring MVC. Nó cho biết controller và method Java nào được Spring dùng để xử lý endpoint đó.

Customizer có thể sửa operation rồi trả lại chính đối tượng đã sửa. Springdoc sử dụng kết quả này trong tài liệu OpenAPI được sinh ra.

Ví dụ luồng xử lý:

```text
Spring MVC HandlerMethod
          |
          v
Springdoc đọc mapping và annotation
          |
          v
Tạo OpenAPI Operation
          |
          v
OperationCustomizer.customize(operation, handlerMethod)
          |
          v
Operation sau tùy biến
          |
          v
OpenAPI JSON/YAML và Swagger UI
```

Callback này chạy trong quá trình Springdoc xây dựng tài liệu, không chạy mỗi lần client gọi endpoint. Nó không gọi nghiệp vụ của controller và không thay đổi cách Spring định tuyến request.

## 2. `HandlerMethod` cung cấp thông tin gì?

`HandlerMethod` thuộc Spring Framework, package `org.springframework.web.method`. Nó là cầu nối giữa operation trong OpenAPI và method Java đã được Spring MVC phát hiện.

| API | Thông tin nhận được | Tình huống sử dụng |
| --- | --- | --- |
| `getBeanType()` | Class chứa handler method | Đọc annotation ở cấp controller, xác định miền API |
| `getMethod()` | Java reflection `Method` | Đọc tên method, return type và annotation trên method |
| `getMethodAnnotation(...)` | Annotation trực tiếp trên method | Đọc metadata tùy chỉnh gắn vào endpoint |
| `hasMethodAnnotation(...)` | Kiểm tra method có annotation hay không | Bật/tắt quy tắc tùy biến |
| `getMethodParameters()` | Danh sách `MethodParameter` | Phân tích tham số method và annotation của tham số |
| `getReturnType()` | `MethodParameter` mô tả kiểu trả về | Xác định metadata liên quan đến response |

Nếu cần xử lý annotation được tổng hợp từ meta-annotation hoặc annotation kế thừa, có thể dùng tiện ích `AnnotatedElementUtils` của Spring thay vì chỉ gọi reflection trực tiếp. Điều này hữu ích khi dự án tạo annotation tổng hợp để chuẩn hóa metadata cho nhiều controller.

Không nên dựa vào tên method để quyết định hợp đồng nếu có thể dùng annotation rõ ràng. Tên Java có thể thay đổi trong refactor và không nhất thiết là tên operation mà client nhìn thấy.

## 3. Tạo annotation nội bộ để đánh dấu audience

Giả sử API được dùng bởi nhiều nhóm client: ứng dụng công khai, đối tác và hệ thống nội bộ. Có thể tạo annotation `@ApiAudience` để đánh dấu nhóm người tiêu thụ API.

```java
package com.example.api.docs;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ApiAudience {
    String value();
}
```

`RetentionPolicy.RUNTIME` giúp customizer đọc annotation bằng reflection khi Springdoc tạo tài liệu. `TYPE` cho phép đặt mặc định trên class controller; `METHOD` cho phép ghi đè ở endpoint cụ thể.

Ví dụ controller:

```java
package com.example.orders;

import com.example.api.docs.ApiAudience;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@ApiAudience("partner")
public class OrderController {

    @GetMapping
    public String listOrders() {
        return "orders";
    }

    @GetMapping("/summary")
    @ApiAudience("internal")
    public String internalSummary() {
        return "summary";
    }
}
```

Method `listOrders` nhận audience `partner` từ class. Method `internalSummary` có annotation riêng nên được xem là `internal`. Đây là metadata tài liệu do nhóm tự quy ước; nó không tự phân quyền truy cập endpoint.

## 4. Đọc annotation từ `HandlerMethod` và thêm OpenAPI extension

OpenAPI hỗ trợ specification extension với tên bắt đầu bằng `x-`. Có thể dùng `x-audience` để công bố audience cho công cụ nội bộ hoặc cổng tài liệu.

```java
package com.example.api.docs;

import io.swagger.v3.oas.models.Operation;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;

public class AudienceOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        ApiAudience audience = AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(), ApiAudience.class
        );

        if (audience == null) {
            audience = AnnotatedElementUtils.findMergedAnnotation(
                handlerMethod.getBeanType(), ApiAudience.class
            );
        }

        if (audience != null) {
            Map<String, Object> extensions = operation.getExtensions();
            if (extensions == null) {
                extensions = new LinkedHashMap<>();
                operation.setExtensions(extensions);
            }
            extensions.put("x-audience", audience.value());
        }

        return operation;
    }
}
```

Customizer tìm annotation ở method trước, sau đó mới tìm ở class. Nhờ vậy metadata ở method có độ ưu tiên cao hơn metadata chung của controller. `getExtensions()` có thể trả về `null` nếu operation chưa có extension nào; vì thế ví dụ khởi tạo map trước khi thêm phần tử.

Kết quả OpenAPI có thể chứa:

```yaml
paths:
  /api/orders:
    get:
      x-audience: partner
  /api/orders/summary:
    get:
      x-audience: internal
```

Extension là metadata tùy chỉnh. Công cụ OpenAPI không nhất thiết hiểu ý nghĩa `x-audience`; cổng tài liệu hoặc pipeline riêng có thể đọc nó để phân loại, lọc hoặc kiểm tra hợp đồng.

## 5. Đăng ký customizer với `GroupedOpenApi`

Để kiểm soát rõ phạm vi, có thể gắn customizer vào một group bằng `addOperationCustomizer`. Ví dụ dưới đây dùng Spring Boot 3 và Springdoc 2.x:

```java
package com.example.api.docs;

import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/**")
            .addOperationCustomizer(new AudienceOperationCustomizer())
            .addOperationCustomizer(new LegacyOperationCustomizer())
            .build();
    }
}
```

Tài liệu group có thể được truy cập tại `/v3/api-docs/partner`. Customizer được gắn vào group này nên quy tắc áp dụng cho các operation thuộc tài liệu group đó.

Nếu có nhiều group cần cùng quy tắc, đăng ký customizer vào từng group tương ứng hoặc dùng cơ chế customizer toàn cục được hỗ trợ bởi đúng phiên bản Springdoc của dự án. Không nên giả định rằng một customizer chỉ được gắn vào một group sẽ tự động áp dụng cho mọi tài liệu.

Với Springdoc 1.x, package của `GroupedOpenApi` khác so với dòng 2.x. Kiểm tra dependency đang dùng trước khi sao chép import; không trộn API cấu hình giữa hai thế hệ.

## 6. Tùy biến summary, description, tag và trạng thái deprecated

Customizer có thể thay đổi các trường operation. Ví dụ, nếu controller dùng một annotation nội bộ để đánh dấu endpoint cũ, customizer có thể đánh dấu operation là deprecated:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface LegacyEndpoint {}
```

```java
public class LegacyOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        if (AnnotatedElementUtils.findMergedAnnotation(
                handlerMethod.getMethod(), LegacyEndpoint.class) != null) {
            operation.setDeprecated(true);
        }
        return operation;
    }
}
```

Endpoint có thể được đánh dấu:

```java
@GetMapping("/api/orders/legacy-report")
@LegacyEndpoint
public void legacyReport() {
    // Endpoint cũ vẫn hoạt động trong thời gian chuyển đổi.
}
```

`deprecated: true` trong OpenAPI thông báo cho người tiêu thụ rằng operation không nên được dùng cho tích hợp mới. Nó không tự tắt endpoint, không trả mã `410` và không xóa route. Việc ngừng hỗ trợ phải được thực hiện bằng kế hoạch migration và thay đổi runtime riêng.

Có thể dùng các phương thức `operation.setSummary(...)`, `setDescription(...)`, `setDeprecated(...)` hoặc `addTagsItem(...)` để điều chỉnh operation. Chỉ ghi đè summary/description khi có nguồn metadata có chủ đích; không nên xóa thông tin do `@Operation` hoặc Springdoc đã suy ra.

## 7. Bổ sung header parameter dựa trên annotation method

Một trường hợp khác là endpoint có điều kiện header mapping nhưng tham số header chưa xuất hiện rõ trong tài liệu. Có thể tạo annotation đánh dấu endpoint yêu cầu tenant header, sau đó bổ sung parameter vào OpenAPI operation.

Annotation:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresTenantHeader {}
```

Controller:

```java
@GetMapping(path = "/api/tenant/orders", headers = "X-Tenant-Id")
@RequiresTenantHeader
public void listTenantOrders() {
    // Lấy tenant từ ngữ cảnh request đã được kiểm tra.
}
```

Customizer:

```java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.method.HandlerMethod;

public class TenantHeaderOperationCustomizer implements OperationCustomizer {

    @Override
    public Operation customize(Operation operation, HandlerMethod handlerMethod) {
        boolean required = AnnotatedElementUtils.findMergedAnnotation(
            handlerMethod.getMethod(), RequiresTenantHeader.class
        ) != null;

        if (required && !hasTenantHeader(operation)) {
            operation.addParametersItem(
                new Parameter()
                    .name("X-Tenant-Id")
                    .in("header")
                    .required(true)
                    .description("Mã tenant được cấp cho client")
                    .schema(new StringSchema())
            );
        }

        return operation;
    }

    private boolean hasTenantHeader(Operation operation) {
        if (operation.getParameters() == null) {
            return false;
        }

        return operation.getParameters().stream().anyMatch(parameter ->
            "header".equalsIgnoreCase(parameter.getIn())
                && "X-Tenant-Id".equalsIgnoreCase(parameter.getName())
        );
    }
}
```

Đăng ký customizer này vào group có chứa endpoint tenant:

```java
@Bean
GroupedOpenApi tenantApi() {
    return GroupedOpenApi.builder()
        .group("tenant")
        .pathsToMatch("/api/tenant/**")
        .addOperationCustomizer(new TenantHeaderOperationCustomizer())
        .build();
}
```

Ví dụ kiểm tra parameter hiện có trước khi thêm để tránh tạo hai header cùng tên. Nếu controller đã khai báo `@RequestHeader("X-Tenant-Id")`, Springdoc thường tự tạo parameter; customizer có thể cập nhật parameter đó thay vì thêm bản sao.

Trong ứng dụng thật, phải bảo đảm runtime cũng thực sự kiểm tra tenant header và xác thực quyền truy cập tenant. Annotation `@RequiresTenantHeader` trong ví dụ chỉ là metadata tùy chỉnh; nó không tự tạo filter, không xác minh tenant và không bảo vệ dữ liệu.

## 8. `OperationCustomizer` khác `OpenApiCustomizer` như thế nào?

Hai extension point này hoạt động ở hai phạm vi khác nhau:

| Extension point | Đối tượng nhận được | Phạm vi phù hợp |
| --- | --- | --- |
| `OperationCustomizer` | Một `Operation` và `HandlerMethod` tương ứng | Quy tắc phụ thuộc controller/method cụ thể |
| `OpenApiCustomizer` | Toàn bộ model `OpenAPI` | Metadata cấp tài liệu như servers, tags, info hoặc components |

Ví dụ, thêm `x-audience` theo annotation của method là công việc phù hợp với `OperationCustomizer`. Thêm server URL theo môi trường hoặc metadata license cho toàn tài liệu phù hợp hơn với `OpenApiCustomizer`.

Không dùng `OperationCustomizer` để sửa cấu trúc toàn cục như `components.schemas` nếu có thể dùng customizer cấp OpenAPI. Ngược lại, dùng `OpenApiCustomizer` để tìm và sửa operation theo reflection sẽ phức tạp hơn vì nó không nhận trực tiếp `HandlerMethod` tương ứng.

## 9. Đọc annotation trên method, class và tham số

`HandlerMethod` cho phép đọc metadata ở nhiều mức. Cần xác định quy tắc ưu tiên rõ ràng:

1. Annotation ở method thường thể hiện ngoại lệ hoặc giá trị ghi đè cho endpoint cụ thể.
2. Annotation ở class thường cung cấp mặc định cho mọi operation trong controller.
3. Annotation trên tham số có thể mô tả header, query parameter hoặc quy tắc riêng của tham số.

Ví dụ đọc tham số:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface ParameterMetadata {
    String value();
}
```

Sau khi định nghĩa annotation cho tham số, customizer có thể đọc nó:

```java
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.AnnotatedElementUtils;

for (MethodParameter methodParameter : handlerMethod.getMethodParameters()) {
    ParameterMetadata metadata = AnnotatedElementUtils.findMergedAnnotation(
        methodParameter.getParameter(), ParameterMetadata.class
    );

    if (metadata != null) {
        // Dùng metadata để điều chỉnh operation parameter phù hợp.
    }
}
```

Đoạn code minh họa cách truy cập annotation của từng tham số. Khi sửa parameter trong `Operation`, hãy đối chiếu tên và vị trí (`query`, `path`, `header`, `cookie`) để cập nhật đúng parameter đã được Springdoc tạo. Tránh thêm parameter mới nếu một parameter tương ứng đã tồn tại.

Nếu annotation nằm trên interface hoặc được tổng hợp qua meta-annotation, kiểm tra cách Spring và `AnnotatedElementUtils` tìm annotation trong cấu trúc controller cụ thể của dự án. Không phải mọi kiểu kế thừa Java đều có cùng hành vi tìm annotation.

## 10. Quy tắc an toàn khi tùy biến operation

Customizer tác động trực tiếp đến hợp đồng được công bố, vì vậy cần giữ thay đổi có chủ đích và ổn định:

- **Không tạo operationId trùng nhau.** Nếu thay `operationId`, bảo đảm giá trị duy nhất trong tài liệu và ổn định giữa các lần build; client generator thường dùng trường này để tạo tên method.
- **Không xóa metadata đã suy ra nếu không cần thiết.** Summary, tags, parameters, request body và responses có thể đã được Springdoc xây dựng đúng.
- **Không thêm parameter trùng.** Kiểm tra `name` và `in` trước khi thêm; một header và query parameter cùng tên vẫn là hai parameter khác nhau.
- **Không thay đổi response schema tùy tiện.** Mọi thay đổi phải phản ánh payload runtime.
- **Không coi extension là bảo mật.** `x-audience`, `x-internal` hoặc `deprecated` chỉ là metadata; chúng không chặn request.
- **Tránh I/O hoặc truy vấn mạng.** Customizer có thể được gọi khi tài liệu được tạo hoặc làm mới; xử lý nặng làm tăng thời gian sinh tài liệu và gây khó dự đoán.
- **Giữ kết quả xác định.** Cùng một handler và cấu hình nên tạo cùng metadata để tài liệu ổn định trong CI.
- **Tránh phụ thuộc vào đối tượng bean runtime.** Dựa vào `getBeanType()`, `getMethod()` và annotation thay vì gọi method nghiệp vụ hoặc đọc trạng thái mutable của bean.

## 11. Kiểm tra kết quả customizer

Sau khi đăng ký customizer, mở tài liệu OpenAPI tương ứng, ví dụ `/v3/api-docs/partner`. Kiểm tra:

1. Operation đúng path và HTTP method đã được tùy biến.
2. Extension `x-audience` có giá trị lấy từ method hoặc class theo đúng thứ tự ưu tiên.
3. Endpoint có `@LegacyEndpoint` được đánh dấu `deprecated: true`.
4. Header parameter được thêm đúng vị trí, đúng tên và không bị trùng.
5. Summary, description, tags, request body và responses có sẵn vẫn còn nguyên.
6. Các group khác không bị thay đổi ngoài dự kiến.

Ví dụ kiểm tra JSON bằng cách tìm operation:

```json
{
  "get": {
    "x-audience": "partner",
    "summary": "Liệt kê đơn hàng"
  }
}
```

Đây là đoạn trích minh họa. Cấu trúc đầy đủ còn có thể chứa tags, parameters, responses, security và các metadata khác.

Nên có test cho logic customizer nếu quy tắc được dùng rộng rãi. Có thể tạo `HandlerMethod` từ một method test và tạo model `Operation` mới, gọi `customize`, sau đó xác minh extension hoặc flag đã được thiết lập. Ngoài unit test, cần kiểm tra tài liệu OpenAPI được Springdoc sinh ra để xác nhận customizer đã được đăng ký vào đúng group.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Customizer không chạy | Chưa đăng ký vào group đang kiểm tra hoặc bean không được Spring phát hiện | Kiểm tra `@Component`/`@Bean` và `addOperationCustomizer` |
| Annotation ở class không được đọc | Chỉ kiểm tra method hoặc tìm annotation chưa xử lý meta-annotation | Dùng `AnnotatedElementUtils` và quy định fallback rõ ràng |
| Giá trị method không ghi đè giá trị class | Thứ tự tìm annotation sai | Ưu tiên method trước, sau đó mới class |
| Header xuất hiện hai lần | Springdoc đã tự tạo parameter từ `@RequestHeader` | Tìm parameter theo cả `name` và `in` trước khi thêm |
| `x-audience` không xuất hiện | Extension map chưa được khởi tạo hoặc customizer chưa chạy | Khởi tạo map và xác minh đúng tài liệu group |
| Endpoint bị đánh dấu deprecated nhưng vẫn truy cập được | Nhầm metadata OpenAPI với thay đổi runtime | Thực hiện kế hoạch ngừng hỗ trợ ở controller/gateway riêng |
| Tài liệu khác nhau giữa các lần build | Customizer phụ thuộc dữ liệu mutable hoặc thời gian bên ngoài | Loại bỏ nguồn không xác định, dùng metadata ổn định |
| Group này đúng nhưng group khác không có tùy biến | Customizer chỉ được gắn vào một group | Đăng ký vào từng group cần áp dụng hoặc dùng cơ chế global phù hợp phiên bản |
| OperationId bị trùng sau tùy biến | Sinh ID từ tên method không đủ duy nhất | Giữ ID Springdoc tạo hoặc xây dựng quy tắc duy nhất có kiểm tra |

## 13. Checklist cho `OperationCustomizer`

- [ ] Customizer nhận `Operation` và `HandlerMethod` đúng mục đích.
- [ ] Đọc annotation method trước annotation class nếu method có quyền ghi đè.
- [ ] Dùng `AnnotatedElementUtils` khi cần hỗ trợ meta-annotation.
- [ ] Chỉ thay đổi metadata có căn cứ từ controller hoặc quy ước được khai báo.
- [ ] Khởi tạo extension map khi chưa có và dùng tên extension bắt đầu bằng `x-`.
- [ ] Kiểm tra parameter hiện có trước khi thêm để tránh trùng.
- [ ] Không nhầm metadata OpenAPI với xác thực, phân quyền hoặc routing runtime.
- [ ] Đăng ký customizer vào đúng `GroupedOpenApi` hoặc cơ chế toàn cục tương thích phiên bản.
- [ ] Dùng `OpenApiCustomizer` khi cần thay đổi toàn bộ tài liệu thay vì một operation.
- [ ] Kiểm tra JSON/YAML được sinh ra và giữ metadata Springdoc đã tạo.
- [ ] Giữ customizer nhanh, xác định và không gọi nghiệp vụ controller.

`OperationCustomizer` kết hợp với `HandlerMethod` giúp biến metadata trong controller thành quy tắc tài liệu có thể tái sử dụng. Khi đọc annotation theo thứ tự rõ ràng và chỉ sửa operation ở phạm vi cần thiết, nhóm có thể bổ sung audience, trạng thái deprecated, parameter hoặc extension mà vẫn giữ hợp đồng OpenAPI nhất quán với controller Spring Boot.
