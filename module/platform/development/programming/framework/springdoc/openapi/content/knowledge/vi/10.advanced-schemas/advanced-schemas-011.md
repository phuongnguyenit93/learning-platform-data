# Thay thế schema suy luận bằng implementation hoặc thành phần dùng lại

springdoc-openapi thường suy luận schema từ kiểu Java của tham số, DTO và giá trị trả về trong controller. Cách này thuận tiện khi chữ ký Java phản ánh đúng dữ liệu JSON mà API công bố. Nhưng trong một số trường hợp, kiểu Java không thể hiện đầy đủ hợp đồng: controller trả ResponseEntity<?>, trả wrapper tổng quát, một kiểu nội bộ được serialize thành cấu trúc khác, hoặc cùng một lớp Java cần có hai cách mô tả tùy vị trí sử dụng.

Khi đó, có thể dùng @Schema(implementation = ...) để chỉ định lớp đại diện cho schema, hoặc dùng một component có tên và tham chiếu lại bằng $ref. Với trường hợp phức tạp hơn, springdoc cho phép bổ sung hoặc thay đổi components.schemas bằng OpenAPI bean hay OpenApiCustomizer. Những kỹ thuật này giúp tài liệu mô tả hợp đồng mà client thực sự nhìn thấy, đồng thời tránh sao chép một schema ở nhiều endpoint.

## 1. Khi nào cần thay schema suy luận?

Giả sử một controller trả về ResponseEntity<OrderResponse>. springdoc có thể suy ra kiểu OrderResponse từ generic và tạo schema phù hợp. Nhưng nếu chữ ký trả về là ResponseEntity<?>, Object, một wrapper tổng quát hoặc kiểu Java nội bộ, thông tin kiểu có thể không đủ để tạo hợp đồng mong muốn.

Một số tình huống thường gặp:

| Tình huống | Schema suy luận có thể gặp vấn đề | Hướng xử lý |
| --- | --- | --- |
| Controller trả ResponseEntity<?> | Không xác định được kiểu JSON cụ thể | Chỉ định implementation trong response content |
| Endpoint trả wrapper hoặc kiểu tổng quát | Tham số kiểu có thể bị mất hoặc không được biểu diễn như mong muốn | Dùng DTO cụ thể hoặc lớp implementation chuyên biệt |
| Kiểu Java nội bộ khác cấu trúc JSON công khai | Schema phản ánh lớp nội bộ thay vì hợp đồng bên ngoài | Dùng DTO API hoặc override schema |
| Cùng một lớp được dùng ở nhiều ngữ cảnh | Mỗi nơi cần mô tả khác nhau, ví dụ địa chỉ nhà và địa chỉ nơi làm việc | Tạo các component schema riêng và tham chiếu theo ngữ cảnh |
| Endpoint không khai báo trong controller | Không có chữ ký Java để springdoc tự suy luận | Dùng OpenApiCustomizer và đăng ký schema vào components |

Trước khi override, hãy xác định JSON thực tế mà ứng dụng gửi hoặc nhận. implementation và $ref chỉ thay đổi tài liệu OpenAPI; chúng không thay đổi kiểu trả về Java, cách Jackson serialize hay logic xử lý request.

## 2. Dùng @Schema(implementation = ...) để chỉ định kiểu đại diện

implementation cho swagger-core biết lớp Java nào sẽ được dùng để xây dựng schema cho phần tử đang mô tả. Nó có thể thay thế kiểu được suy luận từ phần tử đó. Các thuộc tính mô tả khác của @Schema, như description, example hoặc requiredMode, vẫn có thể bổ sung cho schema được tạo.

Ví dụ, controller trả ResponseEntity<?> nhưng API thực tế luôn trả một OrderResponse:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    @Operation(summary = "Lấy đơn hàng theo mã")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy đơn hàng",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy đơn hàng",
            content = @Content
        )
    })
    public ResponseEntity<?> getById(@PathVariable long id) {
        Object body = orderService.findResponse(id);
        return ResponseEntity.ok(body);
    }
}
~~~

Trong ví dụ, ResponseEntity<?> là chi tiết của chữ ký Java, còn response content được mô tả bằng OrderResponse. Đặc tả OpenAPI sẽ dùng schema của OrderResponse cho response 200. Điều này chỉ chính xác khi orderService.findResponse(id) thực sự trả JSON có cấu trúc phù hợp với lớp đó.

Có thể dùng implementation cho request body khi kiểu tham số của handler không diễn tả trực tiếp payload công khai. Ví dụ, nếu controller nhận một kiểu tổng quát hoặc kiểu trung gian, dùng annotation io.swagger.v3.oas.annotations.parameters.RequestBody cùng @Content(schema = @Schema(implementation = CreateOrderRequest.class)) để chỉ rõ schema request. Khi đã có DTO rõ ràng trong chữ ký Spring, nên ưu tiên để springdoc suy luận từ DTO.

## 3. Override schema của collection bằng @ArraySchema

Khi dữ liệu là một mảng hoặc danh sách, dùng @ArraySchema để mô tả schema của phần tử. Annotation @ArraySchema dành riêng cho array; không đặt đồng thời @ArraySchema và @Schema trên cùng một phần tử.

Ví dụ response là danh sách đơn hàng nhưng kiểu trả về bị khai báo tổng quát:

~~~java
@GetMapping("/api/orders")
@Operation(summary = "Liệt kê đơn hàng")
@ApiResponse(
    responseCode = "200",
    description = "Danh sách đơn hàng",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
public ResponseEntity<?> listOrders() {
    return ResponseEntity.ok(orderService.findAll());
}
~~~

Schema được công bố là array có phần tử mang cấu trúc OrderResponse. Cần bảo đảm response thực tế là JSON array. Nếu ứng dụng trả object phân trang có các trường content, totalElements và page, thì không nên mô tả nó thành array đơn thuần; hãy dùng schema của kiểu page hoặc một DTO phân trang cụ thể.

## 4. Tạo tên component ổn định cho DTO

OpenAPI đặt các schema dùng lại trong components.schemas. Với object phức tạp, springdoc thường tạo component rồi tham chiếu từ operation hoặc từ thuộc tính khác bằng $ref. Có thể đặt tên component bằng @Schema(name = "...") trên lớp DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "OrderSummary",
    description = "Thông tin tóm tắt của một đơn hàng"
)
public class OrderSummary {

    private Long id;
    private String orderNumber;
    private String status;

    // Getter và setter được lược bỏ.
}
~~~

Khi DTO được dùng trong request hoặc response, springdoc có thể đưa schema vào components.schemas với tên OrderSummary và tham chiếu từ nơi sử dụng. Tên component ổn định giúp tài liệu dễ đọc, dễ so sánh giữa các phiên bản và thuận tiện khi nhiều endpoint cùng sử dụng một cấu trúc.

Nên chọn tên phản ánh hợp đồng công khai, ví dụ CreateOrderRequest, OrderResponse hoặc OrderSummary. Tránh dùng tên class nội bộ nếu tên đó không có ý nghĩa với client. Khi đổi tên component đã được client tham chiếu hoặc code generator sử dụng, cần xem xét đây là thay đổi có ảnh hưởng đến người tiêu thụ tài liệu.

## 5. Tham chiếu component bằng $ref

Một schema đã có trong components.schemas có thể được sử dụng lại ở nhiều nơi. Trong OpenAPI, $ref trỏ đến schema được định nghĩa một lần:

~~~yaml
components:
  schemas:
    Address:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string

    CustomerResponse:
      type: object
      properties:
        id:
          type: string
        address:
          $ref: '#/components/schemas/Address'

    SupplierResponse:
      type: object
      properties:
        id:
          type: string
        address:
          $ref: '#/components/schemas/Address'
~~~

Hai response cùng tham chiếu một định nghĩa Address. Nếu cấu trúc địa chỉ thay đổi theo hợp đồng, chỉ cần cập nhật component và kiểm tra các nơi đang dùng nó. Đây là lợi ích chính của schema dùng lại: giảm trùng lặp và giữ cấu trúc nhất quán.

Trong annotation, có thể chỉ định tham chiếu schema cho một thuộc tính bằng @Schema(ref = "..."). FAQ của springdoc minh họa việc tham chiếu component đã đăng ký bằng tên như WorkAddressSchema hoặc HomeAddressSchema. Hãy kiểm tra OpenAPI JSON được sinh để bảo đảm giá trị cuối cùng là $ref hợp lệ, thường có dạng #/components/schemas/WorkAddressSchema.

Không tạo tham chiếu đến component chưa tồn tại. Một $ref sai tên hoặc sai đường dẫn có thể khiến validator, Swagger UI hoặc công cụ sinh client không phân giải được schema.

## 6. Dùng hai schema khác nhau cho cùng một lớp Java

Có trường hợp một lớp Java được dùng ở nhiều vị trí nhưng ý nghĩa mô tả khác nhau. Ví dụ, Address có cùng các trường Java, nhưng khi là địa chỉ nơi làm việc cần phần mô tả riêng, còn khi là địa chỉ nhà cần một mô tả khác. Có thể đăng ký hai component schema riêng rồi tham chiếu từ từng thuộc tính:

~~~java
public class PersonResponse {

    private String fullName;

    @Schema(ref = "WorkAddressSchema")
    private Address workAddress;

    @Schema(ref = "HomeAddressSchema")
    private Address homeAddress;

    // Getter và setter được lược bỏ.
}
~~~

Một cách đơn giản là khai báo hai component trong OpenAPI bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;

@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI().components(new Components()
            .addSchemas(
                "WorkAddressSchema",
                addressSchema("Địa chỉ nơi làm việc")
            )
            .addSchemas(
                "HomeAddressSchema",
                addressSchema("Địa chỉ nhà")
            )
        );
    }

    private ObjectSchema addressSchema(String description) {
        return new ObjectSchema()
            .description(description)
            .addProperties(
                "addressName",
                new StringSchema().description("Tên hoặc mô tả địa chỉ")
            );
    }
}
~~~

Trong ví dụ, hai component có cùng cấu trúc thuộc tính nhưng có mô tả khác nhau. Nếu cần hai schema khác nhau về trường, kiểu dữ liệu, giới hạn hoặc required, hãy khai báo các thuộc tính tương ứng trong từng component. Không cần tạo hai class Java chỉ để có hai mô tả OpenAPI khác nhau.

Đây là metadata của tài liệu. Hai component không làm thay đổi object Address ở runtime và cũng không khiến Jackson tự phân biệt địa chỉ nhà với địa chỉ nơi làm việc. Nếu hai ngữ cảnh cần dữ liệu khác nhau về mặt nghiệp vụ, hãy cân nhắc tạo DTO riêng thay vì chỉ thay mô tả.

## 7. Đăng ký schema bằng OpenAPI bean và customizer

OpenAPI bean phù hợp khi muốn khai báo components hoặc metadata dùng chung cho tài liệu được sinh. Các định nghĩa được thêm vào bean có thể xuất hiện trong đặc tả mặc định và các nhóm theo cấu hình springdoc.

Nếu muốn thay đổi tài liệu theo từng nhóm, có thể gắn OpenApiCustomizer vào GroupedOpenApi. Nếu cần customizer áp dụng cho cả tài liệu mặc định và các nhóm, springdoc cung cấp GlobalOpenApiCustomizer. Hãy chọn phạm vi rõ ràng để component cần thiết không bị thiếu ở một nhóm.

Ví dụ, đăng ký một schema dùng lại trong tài liệu:

~~~java
@Bean
public OpenAPI customOpenAPI() {
    return new OpenAPI()
        .components(new Components()
            .addSchemas(
                "ApiError",
                new ObjectSchema()
                    .description("Thông tin lỗi chuẩn của API")
                    .addProperties("code", new StringSchema())
                    .addProperties("message", new StringSchema())
            )
        );
}
~~~

Sau đó, response lỗi có thể tham chiếu component này:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Request không hợp lệ",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(ref = "#/components/schemas/ApiError")
    )
)
~~~

Khi dùng OpenAPI bean, cần bảo đảm các cấu hình components khác của ứng dụng cũng được giữ lại. Nếu dự án đã có bean để khai báo thông tin API hoặc security scheme, hãy mở rộng bean hiện có hoặc hợp nhất các thành phần thay vì tạo nhiều nguồn cấu hình cạnh tranh.

## 8. Tạo schema từ lớp Java trong custom endpoint

Đôi khi endpoint được tạo bởi filter, gateway hoặc một cơ chế không có controller method để springdoc suy luận. Khi đó, có thể dùng OpenApiCustomizer để thêm operation và tạo schema từ lớp Java.

Với các phiên bản springdoc hiện hành, FAQ khuyến nghị dùng SpringDocAnnotationsUtils.extractSchema. Phương thức này nhận Components, kiểu Java và phiên bản OpenAPI; nó đăng ký các schema được tham chiếu, kể cả kiểu lồng nhau, rồi trả về schema hoặc $ref để gắn vào operation.

Ví dụ minh họa một endpoint đăng nhập được thêm vào tài liệu:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON_VALUE;

import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.utils.SpringDocAnnotationsUtils;
import org.springframework.context.annotation.Bean;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.media.Schema;

@Bean
public OpenApiCustomizer loginEndpointCustomizer() {
    return openApi -> {
        Schema<?> requestSchema = SpringDocAnnotationsUtils.extractSchema(
            openApi.getComponents(),
            LoginRequest.class,
            null,
            null,
            openApi.getSpecVersion()
        );

        Operation operation = new Operation()
            .operationId("login")
            .requestBody(new RequestBody()
                .required(true)
                .content(new Content().addMediaType(
                    APPLICATION_JSON_VALUE,
                    new MediaType().schema(requestSchema)
                ))
            )
            .responses(new ApiResponses().addApiResponse(
                "200",
                new ApiResponse().description("Đăng nhập thành công")
            ));

        openApi.path("/login", new PathItem().post(operation));
    };
}
~~~

Nếu LoginRequest chứa một kiểu lồng như Address, extractSchema sẽ đăng ký cả schema gốc và schema phụ vào components.schemas, sau đó trả về $ref phù hợp. Các converter do springdoc đăng ký cũng được sử dụng trong quá trình này. Đây là lựa chọn phù hợp hơn việc tự gọi ModelConverters rồi phải tự chép các schema tham chiếu vào Components.

Ví dụ trên thêm một operation không xuất phát từ controller. Nếu endpoint đã được springdoc quét từ controller, không cần thêm lại bằng customizer vì có thể tạo path hoặc operation trùng.

## 9. Reusable enum và schema hợp nhất

Enum được dùng ở nhiều DTO có thể được đưa thành component riêng bằng @Schema(enumAsRef = true):

~~~java
@Schema(enumAsRef = true, description = "Trạng thái đơn hàng")
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
~~~

Khi enum được tái sử dụng, component giúp tránh lặp danh sách giá trị ở nhiều schema. springdoc FAQ cũng mô tả tùy chọn toàn cục ModelResolver.enumsAsRef = true, nhưng thiết lập toàn cục sẽ ảnh hưởng đến tất cả enum. Chỉ bật khi quy ước tài liệu của dự án muốn mọi enum trở thành component dùng lại.

Nếu cần biểu diễn nhiều dạng dữ liệu hợp lệ, hãy cân nhắc các composition keyword như oneOf, anyOf hoặc allOf. Chúng có mục đích khác nhau:

- oneOf: giá trị phải khớp đúng một schema trong danh sách.
- anyOf: giá trị có thể khớp một hoặc nhiều schema trong danh sách.
- allOf: schema kết hợp các ràng buộc từ tất cả schema thành phần.

Có thể dùng @Schema(oneOf = {...}), @Schema(anyOf = {...}) hoặc @Schema(allOf = {...}) khi annotation và kiểu Java phù hợp. Nếu schema là array, dùng @ArraySchema cho phần tử và đặt composition trong schema của phần tử. Không dùng implementation để giả vờ rằng một kiểu dữ liệu có nhiều hình dạng nếu hợp đồng thực tế là union; hãy mô tả đúng bằng composition hoặc DTO phân biệt.

## 10. Kiểm tra schema và tham chiếu sau khi sinh

Sau khi ứng dụng khởi động, mở /v3/api-docs hoặc endpoint tài liệu của group tương ứng. Kiểm tra các điểm sau:

1. Operation có response hoặc request content đúng media type và đúng schema mong muốn.
2. implementation đã tạo schema từ lớp đại diện, không còn kiểu Object hoặc string ngoài dự kiến.
3. Schema phức tạp được đặt trong components.schemas với tên ổn định.
4. $ref trỏ đến component tồn tại và đúng đường dẫn.
5. Component lồng nhau, enum và các schema được dùng lại đều được đăng ký đầy đủ.
6. Hai schema dành cho cùng một lớp nhưng khác ngữ cảnh có đúng mô tả và thuộc tính riêng.
7. Không có tên component bị trùng hoặc tham chiếu bị đứt.
8. JSON thực tế của endpoint phù hợp với schema công bố.

Có thể tải tài liệu để kiểm tra nhanh:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Sau đó chạy validator OpenAPI phù hợp với phiên bản đặc tả mà dự án xuất. Mở Swagger UI để kiểm tra cách hiển thị component và thử request/response mẫu. Nếu một component không xuất hiện, kiểm tra xem nó đã được tham chiếu chưa và cấu hình có loại bỏ định nghĩa không được tham chiếu hay không.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response vẫn hiện Object hoặc string | Override được đặt sai vị trí hoặc thiếu @Content(schema = ...) | Đặt implementation tại schema của response content và kiểm tra JSON sinh ra |
| Schema array chỉ có kiểu phần tử không đúng | Dùng @Schema cho array thay vì @ArraySchema | Dùng @ArraySchema(schema = @Schema(implementation = ...)) |
| $ref không phân giải được | Component chưa được đăng ký hoặc sai tên | Đối chiếu tên component trong components.schemas và đường dẫn $ref |
| Hai ngữ cảnh dùng cùng một schema không thể có mô tả riêng | Cả hai thuộc tính đều tham chiếu cùng component | Tạo component riêng cho từng ngữ cảnh và trỏ đúng ref |
| Component bị trùng tên | Nhiều DTO hoặc cấu hình cùng đăng ký một tên | Đặt tên component có ý nghĩa và thống nhất một nơi quản lý |
| Generic wrapper sinh schema thiếu trường data cụ thể | Thông tin generic bị mất khi suy luận | Tạo DTO cụ thể hoặc dùng implementation đại diện cho payload thực tế |
| Custom endpoint có $ref nhưng thiếu schema lồng nhau | Chỉ thêm ref mà chưa thêm schema phụ vào components | Dùng SpringDocAnnotationsUtils.extractSchema để đăng ký đệ quy |
| Tài liệu đúng nhưng response thực tế khác cấu trúc | Annotation chỉ sửa OpenAPI, không thay đổi Jackson hoặc code runtime | Đồng bộ DTO/serializer với hợp đồng hoặc sửa schema cho đúng JSON thực tế |
| Component xuất hiện ở tài liệu mặc định nhưng thiếu trong group | Customizer chỉ áp dụng cho default OpenAPI | Đăng ký customizer ở group hoặc dùng GlobalOpenApiCustomizer theo phạm vi mong muốn |

## 12. Nguyên tắc lựa chọn

Ưu tiên để springdoc suy luận schema khi kiểu Java đã phản ánh chính xác hợp đồng. Dùng @Schema(implementation = ...) khi cần chỉ rõ kiểu đại diện cho một phần request hoặc response. Dùng @Schema(name = ...) để ổn định tên component; dùng $ref khi nhiều vị trí cần tham chiếu cùng một định nghĩa. Nếu một lớp có các biểu diễn khác nhau theo ngữ cảnh, hãy tạo component riêng cho từng biểu diễn và xác định rõ nơi sử dụng.

Với endpoint không xuất phát từ controller hoặc cần dựng schema bằng code, dùng OpenApiCustomizer và các tiện ích của springdoc để đăng ký đầy đủ schema tham chiếu. Sau cùng, kiểm tra cả đặc tả được sinh lẫn JSON runtime. Một schema override chỉ hữu ích khi nó mô tả đúng dữ liệu mà client thực sự gửi và nhận.

## 13. Tài liệu tham khảo chính thức

- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — override response schema, tạo component từ lớp Java, tạo nhiều schema cho cùng lớp, OpenApiCustomizer và reusable enum.
- [springdoc-openapi v2 FAQ](https://springdoc.org/v2/faq.html) — cấu hình OpenAPI bean, customizer theo group và SpringDocAnnotationsUtils.extractSchema.
- [Swagger Core — Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.41/apidocs/io/swagger/v3/oas/annotations/media/Schema.html) — implementation, ref, schema composition và cách annotation thay thế kiểu được suy luận.
- [OpenAPI Specification 3.1.2 — Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object) — vị trí và vai trò của các schema dùng lại.
- [OpenAPI Specification 3.1.2 — Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object) — quy tắc tham chiếu đến thành phần dùng lại.

Khi thay thế schema suy luận hoặc tạo component dùng lại, mục tiêu là giữ một hợp đồng OpenAPI nhất quán, có tên rõ ràng và phản ánh đúng dữ liệu trên dây. springdoc cung cấp annotation và API tùy chỉnh để thực hiện điều đó mà không buộc nhóm phải tự viết toàn bộ đặc tả bằng tay.
