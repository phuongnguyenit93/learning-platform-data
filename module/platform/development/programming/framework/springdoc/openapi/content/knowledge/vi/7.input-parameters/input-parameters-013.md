# Tham số dùng lại thông qua components.parameters

Một API thường lặp lại cùng một tham số trên nhiều operation: mã tenant trong header, mã phiên bản trong query, bộ lọc phân trang hoặc một mã định danh được truyền qua path. Nếu mỗi operation tự khai báo lại toàn bộ tên, kiểu, mô tả và ràng buộc, tài liệu dễ bị lệch nhau khi quy tắc thay đổi.

OpenAPI cung cấp <code>components.parameters</code> để định nghĩa một Parameter Object dùng lại. Operation hoặc Path Item có thể tham chiếu định nghĩa đó bằng <code>$ref</code>. Với springdoc-openapi, có thể tạo các component bằng OpenAPI bean và gắn tham chiếu vào operation bằng <code>OpenApiCustomizer</code> hoặc <code>GlobalOpenApiCustomizer</code>.

## 1. Parameter Object và components.parameters

Parameter Object mô tả một tham số mà client gửi trong request. Một tham số được xác định bởi tên và vị trí truyền:

- <code>path</code>: một phần của đường dẫn URL.
- <code>query</code>: query string sau dấu <code>?</code>.
- <code>header</code>: HTTP request header.
- <code>cookie</code>: cookie gửi cùng request.

Ví dụ, tham số <code>X-Tenant-Id</code> được gửi trong header:

~~~yaml
name: X-Tenant-Id
in: header
required: true
description: Mã tenant đang thực hiện request
schema:
  type: string
~~~

Khi chỉ xuất hiện trong một operation, có thể khai báo Parameter Object trực tiếp ở operation. Khi nhiều operation dùng cùng một định nghĩa, đặt nó trong <code>components.parameters</code>:

~~~yaml
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      description: Mã tenant đang thực hiện request
      schema:
        type: string
~~~

<code>TenantId</code> là khóa do nhóm API chọn để định danh component. Khóa này phân biệt chữ hoa và chữ thường, không nhất thiết giống tên tham số HTTP. Tên HTTP thực tế vẫn được khai báo trong thuộc tính <code>name</code>.

Đặt định nghĩa trong <code>components.parameters</code> chỉ tạo một mục có thể tái sử dụng. Nó **không tự động thêm tham số vào tất cả endpoint**. Muốn một operation sử dụng định nghĩa đó, phải tham chiếu component bằng <code>$ref</code>.

## 2. Tham chiếu component bằng $ref

Một operation có thể dùng Parameter Object đã khai báo trong components:

~~~yaml
paths:
  /customers:
    get:
      operationId: listCustomers
      parameters:
        - $ref: "#/components/parameters/TenantId"
      responses:
        "200":
          description: Danh sách khách hàng
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      description: Mã tenant đang thực hiện request
      schema:
        type: string
~~~

Đường dẫn <code>#/components/parameters/TenantId</code> là JSON Pointer trỏ tới component có khóa <code>TenantId</code> trong tài liệu hiện tại. Tên khóa phải khớp chính xác.

Operation có thể có nhiều tham số dùng lại:

~~~yaml
paths:
  /orders:
    get:
      parameters:
        - $ref: "#/components/parameters/TenantId"
        - $ref: "#/components/parameters/PageSize"
      responses:
        "200":
          description: Danh sách đơn hàng
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
    PageSize:
      name: pageSize
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
~~~

Một component có thể được tham chiếu từ nhiều operation và cả mảng <code>parameters</code> của Path Item. Tham số ở Path Item được áp dụng cho mọi operation thuộc path đó; tham số ở operation chỉ áp dụng cho operation tương ứng.

Không khai báo lặp một tham số cùng tên và cùng vị trí trong cùng operation. OpenAPI xác định tính duy nhất của tham số theo tổ hợp <code>name</code> và <code>in</code>. Nếu đã tham chiếu component <code>TenantId</code>, không thêm một bản inline khác cũng có <code>name: X-Tenant-Id</code> và <code>in: header</code>.

## 3. Các thuộc tính quan trọng của Parameter Object

Parameter Object có một số thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>name</code> | Tên tham số HTTP |
| <code>in</code> | Vị trí: path, query, header hoặc cookie |
| <code>description</code> | Mô tả cách sử dụng tham số |
| <code>required</code> | Tham số có bắt buộc hay không; path parameter luôn bắt buộc |
| <code>deprecated</code> | Đánh dấu tham số đã lỗi thời |
| <code>schema</code> | Kiểu dữ liệu và các ràng buộc của giá trị |
| <code>example</code> / <code>examples</code> | Giá trị minh họa |
| <code>style</code> và <code>explode</code> | Cách tuần tự hóa giá trị thành chuỗi HTTP |

Ví dụ một query parameter dùng chung cho phân trang:

~~~yaml
components:
  parameters:
    PageSize:
      name: pageSize
      in: query
      required: false
      description: Số phần tử tối đa trong một trang
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
      example: 25
~~~

Trong ví dụ, <code>required: false</code> cho phép client bỏ query parameter. <code>default: 20</code> mô tả giá trị mặc định của hợp đồng; server vẫn cần triển khai hành vi mặc định tương ứng. <code>minimum</code> và <code>maximum</code> mô tả giới hạn hợp lệ, nhưng không tự thêm validation vào controller.

Với path parameter, <code>required</code> phải là <code>true</code>:

~~~yaml
components:
  parameters:
    CustomerId:
      name: customerId
      in: path
      required: true
      description: Mã khách hàng cần truy xuất
      schema:
        type: string
~~~

Không đưa header <code>Accept</code>, <code>Content-Type</code> hoặc <code>Authorization</code> vào Parameter Object. OpenAPI dành cơ chế mô tả riêng cho chúng: content negotiation được thể hiện qua <code>content</code> của request body/response; xác thực được mô tả bằng <code>components.securitySchemes</code> và security requirement.

## 4. Phân biệt components.parameters với các component khác

Trong OpenAPI, các mục dưới <code>components</code> có mục đích riêng. Không dùng thay thế lẫn nhau:

| Thành phần | Mô tả | Vị trí tham chiếu thường gặp |
|---|---|---|
| <code>components.parameters</code> | Tham số request như path, query, header, cookie | <code>parameters</code> của Path Item hoặc Operation |
| <code>components.headers</code> | Header trong response | <code>headers</code> của Response Object |
| <code>components.schemas</code> | Cấu trúc dữ liệu JSON/XML hoặc kiểu schema | <code>schema</code> trong request/response |
| <code>components.requestBodies</code> | Định nghĩa request body dùng lại | <code>requestBody</code> của Operation |
| <code>components.responses</code> | Định nghĩa response dùng lại | <code>responses</code> của Operation |
| <code>components.securitySchemes</code> | Cơ chế xác thực như API key, HTTP bearer, OAuth2 | Security requirement |

Ví dụ, <code>X-Request-Id</code> mà client gửi lên là request parameter ở vị trí header và có thể được định nghĩa trong <code>components.parameters</code>. Header <code>X-RateLimit-Remaining</code> mà server trả về là response header và thuộc <code>components.headers</code>.

## 5. Khai báo component dùng lại bằng OpenAPI bean

springdoc-openapi cho phép cung cấp một bean kiểu <code>OpenAPI</code> để bổ sung định nghĩa vào tài liệu. Ví dụ sau khai báo hai tham số dùng chung:

~~~java
import java.math.BigDecimal;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiComponentsConfiguration {

    @Bean
    OpenAPI reusableParametersOpenAPI() {
        return new OpenAPI()
            .components(new Components()
                .addParameters("TenantId",
                    new Parameter()
                        .name("X-Tenant-Id")
                        .in("header")
                        .required(true)
                        .description("Mã tenant đang thực hiện request")
                        .schema(new StringSchema()))
                .addParameters("PageSize",
                    new Parameter()
                        .name("pageSize")
                        .in("query")
                        .required(false)
                        .description("Số phần tử tối đa trong một trang")
                        .schema(new IntegerSchema()
                            .minimum(new BigDecimal("1"))
                            .maximum(new BigDecimal("100"))
                            ._default(20))))
            .info(new Info()
                .title("Customer API")
                .version("1.0.0"));
    }
}
~~~

Bean trên thêm các định nghĩa vào <code>components.parameters</code>. Định nghĩa <code>TenantId</code> và <code>PageSize</code> sẽ xuất hiện trong tài liệu OpenAPI. Các tham số chưa được thêm vào operation cho đến khi có tham chiếu <code>$ref</code>.

Nếu dự án đã có OpenAPI bean để khai báo <code>info</code>, <code>servers</code> hoặc security schemes, hãy thêm các <code>addParameters(...)</code> vào <code>Components</code> hiện có. Một ứng dụng chỉ nên có một cấu hình OpenAPI bean được phối hợp thống nhất; không tạo bean thứ hai chỉ để khai báo parameter.

OpenAPI bean phù hợp với component dùng chung trên toàn bộ tài liệu, kể cả khi ứng dụng có nhiều nhóm <code>GroupedOpenApi</code>. Nếu component chỉ cần xuất hiện trong một nhóm, có thể bổ sung bằng customizer gắn với nhóm đó.

## 6. Gắn $ref vào operation bằng OpenApiCustomizer

Controller vẫn cần annotation Spring để bind request khi runtime:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @GetMapping("/customers")
    Object listCustomers(
            @RequestHeader(name = "X-Tenant-Id") String tenantId,
            @RequestParam(name = "pageSize", required = false) Integer pageSize) {
        // Xử lý truy vấn khách hàng theo tenant và page size
        return List.of();
    }
}
~~~

springdoc sẽ tự sinh hai Parameter Object inline từ <code>@RequestHeader</code> và <code>@RequestParam</code>. Nếu muốn tài liệu cuối cùng dùng component reference, customizer cần thay hai tham số inline bằng <code>$ref</code>. Chỉ thêm reference mà vẫn giữ bản inline sẽ tạo hai tham số trùng tên và vị trí.

~~~java
import java.util.ArrayList;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.parameters.Parameter;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ReusableParameterCustomizerConfiguration {

    @Bean
    OpenApiCustomizer customerParameterReferences() {
        return openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }
            PathItem pathItem = openApi.getPaths().get("/customers");
            if (pathItem == null || pathItem.getGet() == null) {
                return;
            }

            Operation operation = pathItem.getGet();
            if (operation.getParameters() == null) {
                operation.setParameters(new ArrayList<>());
            }

            operation.getParameters().removeIf(parameter ->
                ("header".equals(parameter.getIn())
                    && "X-Tenant-Id".equals(parameter.getName()))
                || ("query".equals(parameter.getIn())
                    && "pageSize".equals(parameter.getName())));

            operation.addParametersItem(
                new Parameter().$ref("#/components/parameters/TenantId"));
            operation.addParametersItem(
                new Parameter().$ref("#/components/parameters/PageSize"));
        };
    }
}
~~~

Đây là ví dụ thay thế tham số inline do springdoc sinh ra cho operation <code>GET /customers</code> bằng component reference. Nếu path hoặc HTTP method thay đổi, cập nhật điều kiện tìm operation tương ứng. Nếu nhiều operation dùng chung tham số, có thể viết hàm hỗ trợ để thay tham số theo danh sách path/method đã chọn.

Customizer chỉ tác động đến đặc tả OpenAPI. Việc bind <code>X-Tenant-Id</code> và <code>pageSize</code> vẫn do các annotation Spring trong controller thực hiện. Component reference không tự tạo request parameter trong Spring và không thay đổi logic kiểm tra dữ liệu.

### 6.1. OpenApiCustomizer và GlobalOpenApiCustomizer

springdoc-openapi có hai phạm vi customizer cần phân biệt:

- <code>OpenApiCustomizer</code> được áp dụng cho tài liệu OpenAPI mặc định.
- <code>GlobalOpenApiCustomizer</code> được áp dụng cho tài liệu mặc định và cả các tài liệu nhóm <code>GroupedOpenApi</code>.

Nếu ứng dụng có nhiều nhóm và mọi nhóm đều cần tham chiếu các component dùng chung, có thể thay kiểu trả về của bean customizer thành <code>GlobalOpenApiCustomizer</code>:

~~~java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;

@Bean
GlobalOpenApiCustomizer customerParameterReferences() {
    return openApi -> {
        // Tìm operation thuộc tài liệu nhóm hiện tại,
        // loại bỏ tham số inline tương ứng và thêm các $ref.
    };
}
~~~

Nếu chỉ một nhóm cần các tham chiếu đó, gắn customizer trực tiếp khi tạo <code>GroupedOpenApi</code> bằng <code>addOpenApiCustomizer(...)</code>. Component định nghĩa bằng OpenAPI bean có thể dùng chung; customizer quyết định operation nào trong từng tài liệu nhận tham chiếu.

## 7. Dùng tham số dùng lại ở cấp Path Item

Nếu mọi operation trên cùng một path đều cần một tham số, có thể đặt tham chiếu tại cấp Path Item:

~~~yaml
paths:
  /reports:
    parameters:
      - $ref: "#/components/parameters/TenantId"
    get:
      operationId: listReports
      responses:
        "200":
          description: Danh sách báo cáo
    post:
      operationId: createReport
      responses:
        "201":
          description: Đã tạo báo cáo
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
~~~

Tham số ở cấp path được áp dụng cho tất cả operation trong path đó. Operation cụ thể có thể bổ sung thêm tham số riêng. Nếu operation khai báo một tham số trùng tổ hợp <code>name</code> và <code>in</code> với tham số cấp path, cần xử lý theo quy tắc ghi đè của OpenAPI và tránh tạo các bản khai báo không nhất quán.

Không đưa một header chỉ dành cho một operation lên cấp Path Item nếu các operation khác không cần nó. Đặt ở đúng cấp giúp tài liệu phản ánh chính xác hợp đồng và tránh yêu cầu client gửi dư tham số.

## 8. Tham số dùng chung toàn API và tham số dùng lại

Hai ý tưởng này khác nhau:

- **Tham số dùng lại**: định nghĩa một lần trong <code>components.parameters</code> rồi tham chiếu ở những operation cần nó.
- **Tham số toàn cục**: thêm một tham số vào mọi operation hoặc vào một tập operation theo chính sách của API.

Một component trong <code>components.parameters</code> không tự trở thành tham số toàn cục. Nếu mọi endpoint đều cần một header, có thể dùng customizer để thêm cùng một reference vào các operation phù hợp. Cần lọc rõ phạm vi áp dụng, vì một số operation như health check, endpoint công khai hoặc callback có thể không yêu cầu header đó.

Không biến tham số xác thực thành header parameter thông thường. Với API key, bearer token hoặc OAuth2, khai báo security scheme và security requirement để Swagger UI cùng công cụ client hiểu đúng cơ chế bảo mật.

## 9. Kiểm tra component và các tham chiếu

Sau khi cấu hình, tải tài liệu OpenAPI JSON:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra các vị trí:

- <code>components.parameters.TenantId</code> và <code>components.parameters.PageSize</code> tồn tại.
- Operation <code>GET /customers</code> có hai mục <code>$ref</code> trỏ đúng component.
- Không còn tham số inline trùng với cùng cặp tên và vị trí.
- Các giá trị <code>name</code>, <code>in</code>, <code>required</code>, schema và description trong component khớp với cách controller bind dữ liệu.
- Tài liệu nhóm cũng có component và reference nếu customizer cần áp dụng cho nhóm đó.

Một phần kết quả mong đợi:

~~~yaml
components:
  parameters:
    TenantId:
      name: X-Tenant-Id
      in: header
      required: true
      schema:
        type: string
    PageSize:
      name: pageSize
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
paths:
  /customers:
    get:
      parameters:
        - $ref: "#/components/parameters/TenantId"
        - $ref: "#/components/parameters/PageSize"
~~~

Có thể kiểm tra nhanh danh sách reference bằng <code>jq</code>:

~~~bash
curl -s http://localhost:8080/v3/api-docs |
  jq -r '.paths | to_entries[] |
    .key as $path |
    .value | to_entries[] |
    .key as $method |
    (.value.parameters // [])[] |
    select(.$ref != null) |
    [$method, $path, .$ref] | @tsv'
~~~

Sau khi kiểm tra tài liệu, thử request thật với và không có tham số, giá trị hợp lệ và không hợp lệ. Tài liệu mô tả quy tắc; controller, validation và service mới thực thi hành vi đó.

## 10. Lỗi thường gặp

**Đã định nghĩa component nhưng không thấy trong operation.** <code>components.parameters</code> chỉ là nơi lưu định nghĩa. Cần thêm <code>$ref</code> vào mảng <code>parameters</code> của Path Item hoặc Operation.

**Tham số xuất hiện hai lần.** Controller annotation đã khiến springdoc sinh tham số inline. Khi customizer thêm reference, hãy thay thế bản inline cùng tên và vị trí trước.

**$ref không tìm thấy component.** Kiểm tra khóa trong <code>components.parameters</code>, chính tả và chữ hoa/chữ thường trong JSON Pointer.

**Dùng nhầm components.headers.** <code>components.headers</code> dành cho header trong response; tham số request ở vị trí header phải dùng <code>components.parameters</code>.

**Định nghĩa tham số không khớp binding runtime.** Kiểm tra <code>name</code> và <code>in</code> của component cùng annotation <code>@RequestParam</code>, <code>@PathVariable</code>, <code>@RequestHeader</code> hoặc <code>@CookieValue</code>. <code>$ref</code> chỉ thay đổi tài liệu.

**Customizer không chạy cho tài liệu nhóm.** Nếu cần áp dụng customizer cho cả <code>GroupedOpenApi</code>, dùng <code>GlobalOpenApiCustomizer</code> hoặc đăng ký customizer riêng trong cấu hình nhóm.

**Thêm header xác thực như tham số thông thường.** Không mô tả <code>Authorization</code> bằng Parameter Object. Dùng <code>components.securitySchemes</code> và security requirement.

## 11. Danh sách rà soát trước khi công bố

- [ ] Tham số được dùng lặp lại đã có định nghĩa trong <code>components.parameters</code>.
- [ ] Khóa component có tên rõ ràng, ổn định và không bị trùng.
- [ ] Mọi operation cần dùng đều tham chiếu đúng bằng <code>$ref</code>.
- [ ] Không có tham số trùng tổ hợp <code>name</code> và <code>in</code> trong một operation.
- [ ] Tham số ở cấp Path Item chỉ áp dụng cho những operation thực sự cần nó.
- [ ] Binding runtime của Spring khớp với định nghĩa trong component.
- [ ] Đã xác định customizer áp dụng cho tài liệu mặc định hay cả các nhóm.
- [ ] Các header xác thực được mô tả bằng security scheme.
- [ ] Đã kiểm tra tài liệu sinh ra và thử request thực tế.

## Tài liệu tham khảo

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): định nghĩa các thành phần có thể tái sử dụng, gồm <code>parameters</code>.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): thuộc tính, vị trí và quy tắc của tham số.
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object): cú pháp và cách hoạt động của <code>$ref</code>.
- [springdoc-openapi FAQ](https://springdoc.org/faq.html): khai báo parameter dùng chung trong OpenAPI bean, tham chiếu bằng <code>$ref</code> và khác biệt phạm vi <code>OpenApiCustomizer</code>/<code>GlobalOpenApiCustomizer</code>.
- [Swagger – Describing Parameters](https://swagger.io/docs/specification/describing-parameters/): cách mô tả path, query, header và cookie parameter.
