# Giữ operationId và tên schema ổn định qua các lần phát hành

Một OpenAPI document không chỉ mô tả URL, HTTP method và JSON payload. Nó còn chứa các tên định danh mà công cụ sinh SDK, mock server, tài liệu và contract test có thể sử dụng. Hai nhóm tên cần quản lý ổn định là **operationId** của từng operation và **schema name** trong `components.schemas`.

Trong Spring Boot, springdoc-openapi thường suy ra operationId từ tên method xử lý request nếu method không khai báo ID rõ ràng. Tương tự, tên component schema có thể được suy ra từ kiểu Java. Khi refactor class hoặc method, các tên suy ra có thể đổi dù hợp đồng HTTP vẫn giữ nguyên. Client được sinh lại từ OpenAPI khi đó có thể đổi tên method hoặc model, khiến mã nguồn consumer không biên dịch.

Để giữ hợp đồng ổn định, hãy xem operationId và schema name là tên công khai của API. Đặt chúng tường minh bằng annotation của swagger-core, kiểm tra tài liệu được sinh ra và theo dõi thay đổi qua từng lần phát hành.

## 1. Phân biệt tương thích HTTP và tương thích SDK

Một thay đổi trong OpenAPI có thể không làm thay đổi request trên mạng nhưng vẫn ảnh hưởng đến ứng dụng sử dụng SDK sinh tự động.

| Thành phần thay đổi | Ảnh hưởng đến HTTP contract | Ảnh hưởng đến SDK/code generation |
| --- | --- | --- |
| URL hoặc HTTP method | Có thể làm client gọi API cũ thất bại | Method client được sinh có thể đổi |
| Tên JSON property | Thay đổi payload trên wire | Field/property trong model có thể đổi |
| Kiểu hoặc required của property | Thay đổi dữ liệu hợp lệ | Kiểu dữ liệu hoặc chữ ký method có thể đổi |
| operationId | Thường không đổi URL hoặc payload | Tên method client có thể đổi |
| Tên trong components.schemas | Không nhất thiết đổi JSON payload | Tên model/class được sinh có thể đổi |
| Summary hoặc description | Không đổi hành vi HTTP | Chủ yếu ảnh hưởng tài liệu và comment sinh ra |

Ví dụ, đổi operationId từ `getOrderById` thành `findOrder` không nhất thiết làm endpoint `/api/orders/{orderId}` thay đổi. Tuy nhiên, SDK có thể đổi tên method từ `getOrderById(...)` thành `findOrder(...)`. Consumer đang gọi method cũ sẽ cần sửa mã nguồn và build lại.

Tương tự, đổi component key từ `OrderResponse` thành `OrderDto` có thể không thay đổi JSON response, nhưng SDK có thể sinh class `OrderDto` thay cho `OrderResponse`. Các import và khai báo kiểu của ứng dụng consumer sẽ bị ảnh hưởng.

Vì vậy, đánh giá compatibility cần xét cả wire contract và source contract của SDK.

## 2. operationId là định danh công khai của operation

Trong OpenAPI, mỗi Operation Object có thể khai báo operationId. Đây là chuỗi định danh duy nhất của operation trong một API document. Giá trị phân biệt chữ hoa/chữ thường; công cụ và thư viện có thể dùng nó để nhận diện operation. OpenAPI khuyến nghị dùng quy ước đặt tên quen thuộc trong lập trình.

Ví dụ:

~~~yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Lấy đơn hàng theo mã
      responses:
        '200':
          description: Thành công
~~~

operationId không phải tên URL, tên controller hay tên Java method bắt buộc. Nó là tên ổn định để các công cụ tham chiếu đến operation.

Các quy tắc quan trọng:

- Nếu có khai báo, operationId phải duy nhất trong toàn bộ API document.
- So sánh operationId có phân biệt chữ hoa/chữ thường.
- Nên dùng tên ngắn, rõ nghĩa và theo một quy ước nhất quán.
- Không tái sử dụng một operationId cũ cho operation có ý nghĩa khác.
- Không xem operationId là phiên bản API hoặc URL của endpoint.

Nếu ứng dụng xuất nhiều OpenAPI document theo group, hãy kiểm tra uniqueness trong từng document được xuất. Để dễ quản lý SDK, nên giữ cùng operation có cùng operationId ở các group mà nó xuất hiện.

## 3. Vì sao tên method Java có thể làm operationId thay đổi

Khi không cung cấp @Operation(operationId = ...), springdoc có thể lấy tên method của Spring handler làm operationId. Vì vậy, thay đổi tên method trong refactor có thể làm thay đổi tài liệu.

Ví dụ ban đầu:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    public OrderResponse findOrder(@PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
~~~

Nếu không khai báo operationId, tài liệu có thể dùng `findOrder`. Sau đó nhóm phát triển đổi tên method để thống nhất cách đặt tên:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable UUID orderId) {
    return orderService.getById(orderId);
}
~~~

Tên operationId suy ra có thể đổi thành `getOrder`. URL và logic HTTP không thay đổi, nhưng tên method trong SDK có thể thay đổi theo.

Để tách tên API khỏi tên method Java, hãy khai báo operationId tường minh. Khi đó có thể đổi tên method nội bộ mà vẫn giữ định danh công khai.

## 4. Cố định operationId bằng @Operation

Annotation `io.swagger.v3.oas.annotations.Operation` có thuộc tính `operationId`. Đặt ID tại method controller:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã"
    )
    public OrderResponse getOrder(
            @PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
~~~

Kể cả khi đổi tên method thành `findOne`, operationId vẫn là `getOrderById`:

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã"
)
public OrderResponse findOne(@PathVariable UUID orderId) {
    return orderService.getById(orderId);
}
~~~

Tên Java method phục vụ tổ chức mã nguồn. operationId là định danh của API mà consumer nhìn thấy. Giữ hai tên độc lập giúp refactor nội bộ không làm thay đổi SDK. Các ví dụ controller tập trung vào annotation và giả định DTO, service cùng dependency Spring đã được khai báo trong ứng dụng.

## 5. Chọn quy ước đặt operationId

Một quy ước dễ đọc là dùng động từ mô tả hành động và danh từ chỉ tài nguyên. Ví dụ:

| Hành động | operationId gợi ý |
| --- | --- |
| Liệt kê đơn hàng | `listOrders` |
| Lấy một đơn hàng | `getOrderById` |
| Tạo đơn hàng | `createOrder` |
| Cập nhật đơn hàng | `updateOrder` |
| Hủy đơn hàng | `cancelOrder` |
| Liệt kê dòng hàng | `listOrderItems` |

Nên thống nhất:

- Dùng camelCase cho operationId nếu quy ước SDK của dự án theo kiểu này.
- Bắt đầu bằng động từ thể hiện hành động.
- Dùng tên nghiệp vụ mà consumer hiểu được, không dùng tên service hoặc repository nội bộ.
- Phân biệt các operation khác nhau về ý nghĩa, kể cả khi cùng HTTP method.
- Giữ cách viết số ít/số nhiều và cách viết tắt nhất quán.

Tránh các tên quá chung như `get`, `process`, `execute`, `handleRequest`, hoặc tên gắn với chi tiết triển khai như `orderControllerGet`. Những tên này không nói rõ hành động và dễ tạo collision.

Không thêm hậu tố tùy tiện như `V2`, `New`, `Final` chỉ vì method Java đã được refactor. Nếu API thực sự có operation khác về ngữ nghĩa, hãy đặt ID riêng thể hiện hành động mới. Nếu chỉ thay implementation, giữ ID cũ.

## 6. Tránh operationId trùng nhau

Hai operation khác nhau không được dùng cùng operationId trong một document. Ví dụ sau là lỗi thiết kế:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: getOrders
  /api/orders/{orderId}:
    get:
      operationId: getOrders
~~~

Hãy đặt tên theo hành vi:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
~~~

Không dựa vào việc một số generator tự thêm hậu tố để xử lý tên trùng. Cách xử lý collision khác nhau giữa công cụ và phiên bản; SDK có thể sinh tên không mong muốn hoặc quá trình generate có thể thất bại.

Khi dùng GroupedOpenApi, kiểm tra tất cả operation trong từng document. Nếu một operation được đưa vào nhiều group, dùng cùng operationId để consumer nhận ra đó là cùng thao tác API.

## 7. Giữ tên component schema ổn định bằng @Schema(name)

Các model được tham chiếu trong OpenAPI thường được đưa vào `components.schemas`. Ví dụ:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        orderId:
          type: string
          format: uuid
~~~

Các operation tham chiếu schema qua $ref:

~~~yaml
responses:
  '200':
    description: Thành công
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

Tên `OrderResponse` là component key của schema. Nhiều công cụ dùng key này làm tên model hoặc class khi sinh SDK.

Trong Java, dùng @Schema(name = "...") ở cấp class/record để đặt tên schema công khai:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(
    name = "OrderResponse",
    description = "Thông tin đơn hàng trả về cho client"
)
public record OrderResponse(
    UUID orderId,
    String status,
    BigDecimal totalAmount
) {}
~~~

Khi class Java được đổi tên, annotation vẫn giữ component key `OrderResponse` nếu model tiếp tục được springdoc nhận diện theo cùng cách.

Ví dụ nhóm phát triển muốn đổi tên lớp nội bộ:

~~~java
@Schema(name = "OrderResponse")
public record OrderView(
    UUID orderId,
    String status,
    BigDecimal totalAmount
) {}
~~~

Tên Java class là `OrderView`, còn tên schema công khai vẫn là `OrderResponse`. Cách này giúp refactor tên class mà không bắt consumer đổi tên model được sinh.

## 8. Phân biệt schema name và JSON property name

@Schema(name = "...") có thể đặt tên schema hoặc property tùy vị trí annotation. Khi dùng ở cấp class/record, mục tiêu thường là component schema name. Tên thuộc tính JSON là một phần khác của hợp đồng và thường được điều khiển bởi Jackson, ví dụ @JsonProperty.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

@Schema(name = "OrderResponse")
public record OrderResponse(
    @JsonProperty("order_id")
    UUID orderId,

    String status
) {}
~~~

OpenAPI có thể có:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        order_id:
          type: string
          format: uuid
        status:
          type: string
~~~

Ở đây:

- `OrderResponse` là tên schema trong `components.schemas`.
- `order_id` là tên property trong JSON payload.
- `orderId` là tên thành phần Java.

Đổi tên Java field nhưng giữ @JsonProperty("order_id") có thể giữ nguyên JSON property. Đổi @Schema(name = "OrderResponse") có thể làm đổi component key. Đổi @JsonProperty có thể làm thay đổi payload trên wire. Hãy kiểm tra đúng lớp tên cần giữ.

## 9. Đặt tên schema theo vai trò API

Một domain thường có nhiều model với dữ liệu gần giống nhau nhưng mục đích khác nhau. Không nên ép mọi trường hợp dùng chung một schema chỉ để giảm số component.

Ví dụ:

| Vai trò | Tên schema gợi ý |
| --- | --- |
| Dữ liệu tạo đơn hàng | `CreateOrderRequest` |
| Dữ liệu cập nhật đơn hàng | `UpdateOrderRequest` |
| Chi tiết đơn hàng trả về | `OrderResponse` |
| Dữ liệu tóm tắt đơn hàng | `OrderSummaryResponse` |
| Dòng hàng trong đơn | `OrderItemResponse` |
| Lỗi API | `ApiErrorResponse` |

Tên nên mô tả hợp đồng công khai, không mô tả persistence hoặc tầng triển khai. Ví dụ, `OrderEntity`, `OrderJpaModel`, `OrderRepositoryProjection` thường không phải tên phù hợp cho schema công khai vì chúng làm lộ cấu trúc nội bộ và dễ đổi khi refactor.

Nếu hai DTO cùng có tên Java đơn giản nhưng thuộc hai domain khác nhau, component key có thể gây khó hiểu hoặc collision. Đặt tên rõ phạm vi:

- `CustomerOrderResponse`
- `WarehouseOrderResponse`
- `AdminOrderResponse`

Tên schema phải duy nhất trong `components.schemas` của cùng document. Đừng dựa vào công cụ tự thêm package hoặc hậu tố để giải quyết trùng tên.

## 10. Giữ schema name ổn định khi đổi DTO hoặc package

Một refactor có thể đổi package hoặc tên Java class nhưng không thay đổi contract:

~~~text
Trước:
com.example.shop.order.dto.OrderResponse

Sau:
com.example.shop.api.orders.model.OrderView
~~~

Nếu không kiểm soát tên component, tài liệu có thể đổi từ `OrderResponse` sang `OrderView`. Consumer có thể phải sửa import và kiểu dữ liệu trong SDK.

Giữ tên công khai bằng annotation:

~~~java
@Schema(name = "OrderResponse")
public record OrderView(
    UUID orderId,
    String status
) {}
~~~

Khi chuyển DTO sang package khác, hãy giữ annotation và kiểm tra component key trong tài liệu được sinh. Không để tên package Java trở thành một phần quy ước public API trừ khi dự án chủ động muốn như vậy.

## 11. Quản lý schema dùng chung và schema khác biệt

Nếu hai operation trả cùng một cấu trúc dữ liệu với cùng ý nghĩa, dùng chung một component schema giúp tài liệu dễ hiểu và tránh sinh hai model gần giống nhau.

Nếu hai operation có ý nghĩa hoặc vòng đời khác nhau, hãy dùng schema riêng dù các field hiện tại giống nhau. Ví dụ:

- `CreateOrderRequest` chỉ chứa dữ liệu client được phép gửi khi tạo.
- `UpdateOrderRequest` có thể cho phép field tùy chọn để cập nhật một phần.
- `OrderResponse` có thể chứa createdAt, status và totalAmount.

Không gộp các model chỉ vì chúng đang có cùng ba field. Khi nghiệp vụ phát triển, request và response có thể thay đổi độc lập. Tên schema rõ nghĩa giúp consumer hiểu đúng mục đích và giúp thay đổi sau này có phạm vi cụ thể.

Ngược lại, tránh tạo nhiều schema khác tên nhưng cùng ý nghĩa chỉ vì Java class được đặt tên khác nhau ở từng module. Hãy thống nhất component name cho cùng một khái niệm public.

## 12. Lưu ý với generic, wrapper và enum

Các wrapper generic, page model và enum cũng có thể xuất hiện trong `components.schemas`. Nếu generator tạo tên tự động dựa trên kiểu tham số hoặc tên class, thay đổi kiểu generic có thể làm tên component thay đổi.

Ví dụ, các kiểu `PageResponse<OrderResponse>` và `PageResponse<CustomerResponse>` có thể cần schema riêng theo cách resolver tạo component. Nếu component name là một phần SDK công khai, hãy kiểm tra tên thực tế được sinh và cân nhắc tạo wrapper cụ thể:

~~~java
@Schema(name = "OrderPageResponse")
public record OrderPageResponse(
    List<OrderResponse> items,
    int page,
    int size,
    long totalElements
) {}
~~~

Đối với enum, giữ ổn định cả component name lẫn các giá trị enum. Đổi tên component có thể làm đổi tên enum type trong SDK; đổi giá trị enum có thể ảnh hưởng logic mapping của consumer.

Khi dùng `@Schema(enumAsRef = true)` để đưa enum thành component schema riêng, hãy kiểm tra key trong `components.schemas` sau khi sinh. Không mặc định rằng tên enum Java luôn là tên public mong muốn.

## 13. Discriminator và polymorphism cũng phụ thuộc schema name

Schema name còn có thể được tham chiếu từ `discriminator.mapping` hoặc các $ref khác. Khi đổi component key, phải cập nhật tất cả tham chiếu tương ứng.

Ví dụ:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'
      discriminator:
        propertyName: paymentType
        mapping:
          card: '#/components/schemas/CardPayment'
          bank_transfer: '#/components/schemas/BankTransferPayment'
~~~

Nếu đổi `CardPayment` thành `CardPaymentResponse`, tất cả $ref và mapping dùng tên cũ phải được xử lý. Nếu không, document có thể tham chiếu đến component không tồn tại hoặc code generator sinh model không đúng.

Giữ component key ổn định giúp giảm số điểm phải thay đổi khi refactor class hoặc tổ chức package.

## 14. Đặt operationId và schema name trong RouterFunction

Với Spring WebFlux hoặc MVC functional endpoints, springdoc dùng @RouterOperation để mô tả route. operationId cần được khai báo trong annotation @Operation lồng bên trong.

Đoạn annotation rút gọn dưới đây minh họa metadata OpenAPI cần gắn vào method bean khai báo RouterFunction thực tế:

~~~java
@RouterOperation(
    path = "/api/orders/{orderId}",
    produces = "application/json",
    method = RequestMethod.GET,
    operation = @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Thành công",
                content = @Content(
                    schema = @Schema(
                        name = "OrderResponse",
                        implementation = OrderResponse.class
                    )
                )
            )
        }
    )
)
~~~

Với functional endpoint, không có handler method kiểu controller để springdoc luôn tự suy ra tên operation. Khai báo operationId tường minh giúp định danh route ổn định và tránh phụ thuộc tên bean method.

## 15. Giữ tên ổn định khi dùng OpenApiCustomizer

Ứng dụng có thể bổ sung hoặc sửa OpenAPI model bằng OpenApiCustomizer hoặc OpenAPI bean. Khi tạo operation bằng code, hãy đặt operationId rõ ràng. Đoạn mã minh họa việc đặt ID; phần gắn PathItem vào OpenAPI được lược bỏ:

~~~java
@Bean
OpenApiCustomizer loginOperationCustomizer() {
    return openApi -> {
        Operation operation = new Operation()
            .operationId("login")
            .summary("Đăng nhập");

        // Gắn operation vào PathItem tương ứng.
    };
}
~~~

Không tạo operationId bằng giá trị biến động như timestamp, UUID ngẫu nhiên, tên class nội bộ hoặc tên method được reflection suy ra nếu mục tiêu là giữ hợp đồng ổn định.

Nếu customizer đổi tên component schema, cần cập nhật cả $ref trỏ đến component đó. Tránh viết customizer đổi tên schema theo package hoặc thứ tự duyệt class, vì kết quả có thể thay đổi khi refactor hoặc nâng phiên bản thư viện.

Với các cấu hình GroupedOpenApi, có thể dùng customizer riêng cho từng group. Đảm bảo cùng một schema public không vô tình mang tên khác nhau giữa các group nếu consumer dự kiến dùng chung model.

## 16. Kiểm thử operationId và schema name bằng MockMvc

Đừng chỉ kiểm tra controller trả đúng JSON. Hãy kiểm tra OpenAPI document do springdoc sinh ra vì đó mới là dữ liệu mà Swagger UI, SDK generator và contract tool đọc.

Ví dụ integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiNamingContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsPublicOperationAndSchemaNames() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{orderId}'].get.operationId"
            ).value("getOrderById"))
            .andExpect(jsonPath(
                "$.components.schemas.OrderResponse"
            ).exists())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{orderId}'].get.responses['200'].content['application/json'].schema['$ref']"
            ).value("#/components/schemas/OrderResponse"));
    }
}
~~~

Test trên phát hiện các trường hợp:

- Method Java bị đổi tên và operationId bị suy ra thành tên mới.
- DTO bị đổi tên làm component key đổi.
- Response không còn tham chiếu component schema dự kiến.
- Controller hoặc model không được springdoc đưa vào document như mong đợi.

Test này giả định API docs được phép truy cập trong test security context. Nếu Spring Security bảo vệ request /v3/api-docs, cấu hình test authentication hoặc quyền truy cập phù hợp.

## 17. Kiểm tra operationId không bị trùng

Ngoài kiểm tra từng ID cụ thể, nên có kiểm tra uniqueness cho tất cả operation trong document. Có thể đọc OpenAPI JSON bằng Jackson, duyệt các path item và thu thập operationId của từng HTTP operation.

Ví dụ ý tưởng kiểm thử:

~~~java
Set<String> operationIds = new HashSet<>();

for (PathItem pathItem : openAPI.getPaths().values()) {
    for (Operation operation : pathItem.readOperations()) {
        String operationId = operation.getOperationId();
        assertNotNull(operationId, "Operation phải có operationId");
        assertTrue(
            operationIds.add(operationId),
            "operationId bị trùng: " + operationId
        );
    }
}
~~~

Đoạn kiểm tra này giả định test đã tải và parse OpenAPI document thành model io.swagger.v3.oas.models.OpenAPI. Nếu dự án cho phép operation không có operationId, bỏ assertion assertNotNull nhưng vẫn kiểm tra uniqueness của các ID đã khai báo. Với dự án sinh SDK, nên yêu cầu tất cả operation công khai có ID rõ ràng.

Khi có nhiều group, chạy kiểm tra trên từng document. Một document có thể hợp lệ nhưng group khác vẫn chứa operationId trùng.

## 18. Snapshot và diff OpenAPI trong CI

Một snapshot OpenAPI đã được review có thể giúp phát hiện tên công khai bị đổi ngoài ý muốn.

Quy trình gợi ý:

1. Khởi động ứng dụng với profile dùng để export.
2. Tải OpenAPI JSON/YAML từ endpoint đã cấu hình.
3. Kiểm tra document parse được và operationId không trùng.
4. So sánh operationId và keys trong components.schemas với snapshot hoặc baseline của release trước.
5. Chạy công cụ kiểm tra breaking changes cho thay đổi contract.
6. Review mọi thay đổi tên method/model trước khi phát hành.

Có thể trích xuất danh sách tên từ JSON bằng jq:

~~~bash
# Liệt kê operationId
jq -r '.. | objects | .operationId? // empty' openapi.json | sort

# Tìm operationId trùng
jq -r '.. | objects | .operationId? // empty' openapi.json \
  | sort | uniq -d

# Liệt kê tên component schema
jq -r '.components.schemas | keys[]' openapi.json | sort
~~~

Snapshot không nên là cách duy nhất để đánh giá compatibility. Một diff toàn bộ document có thể chứa thay đổi thứ tự, mô tả hoặc metadata không ảnh hưởng runtime. Hãy kết hợp:

- Assertion cho operationId và schema keys quan trọng.
- OpenAPI diff hoặc compatibility checker để tìm thay đổi contract.
- Review thủ công các thay đổi có chủ đích.
- Test SDK generator nếu dự án phát hành client library.

## 19. Đổi tên khi thực sự cần thiết

Đôi khi tên public ban đầu sai nghĩa hoặc không thể tiếp tục dùng. Khi đó, đổi tên operationId hoặc schema key là thay đổi có thể ảnh hưởng source compatibility.

Trước khi đổi:

1. Xác định consumer nào dùng SDK sinh từ document.
2. Kiểm tra tên method/model được generator tạo ra ở các ngôn ngữ đang hỗ trợ.
3. Xác định đây chỉ là đổi tên hay còn thay đổi hành vi, payload và semantics.
4. Thông báo thay đổi và hướng dẫn migration.
5. Nếu cần duy trì client cũ, cân nhắc phát hành API/document version mới thay vì âm thầm thay tên trong cùng contract.

OpenAPI Generator có các tùy chọn mapping như operationIdNameMappings và modelNameMappings để điều chỉnh tên ở phía generator. Đây là biện pháp tùy biến SDK, không thay thế việc giữ định danh trong OpenAPI ổn định. Các mapping cũng phụ thuộc generator cụ thể và cần được kiểm thử.

Không tái sử dụng operationId cũ cho một hành động khác sau khi bỏ operation cũ. Điều đó khiến consumer hoặc tooling hiểu nhầm hai thao tác là cùng một định danh.

## 20. Những lỗi thường gặp

**Refactor tên controller method làm SDK đổi tên method.** Springdoc có thể dùng handler method name làm operationId mặc định. Đặt @Operation(operationId = "...") tường minh.

**Hai endpoint có cùng operationId.** Chọn ID riêng theo hành động và kiểm tra uniqueness trên toàn bộ document.

**Đổi tên DTO làm component schema đổi.** Đặt @Schema(name = "...") ở cấp model để giữ component key công khai.

**Đổi @Schema(name) nhưng JSON field không đổi.** Đây là hành vi có thể xảy ra vì component key và JSON property là hai tên khác nhau. Dùng @JsonProperty để quản lý tên field JSON.

**Đổi tên Java property làm JSON payload đổi ngoài ý muốn.** Kiểm tra Jackson naming strategy và @JsonProperty; giữ tên wire property khi chỉ refactor Java field.

**Hai package có class cùng tên gây component collision.** Đặt schema name riêng, rõ domain và duy nhất trong document.

**Schema đổi tên nhưng $ref hoặc discriminator mapping còn tên cũ.** Kiểm tra toàn bộ component references và mapping trong OpenAPI JSON.

**Một group có operationId khác group còn lại.** Dùng cùng ID cho cùng operation trong các document mà nó xuất hiện, sau đó kiểm tra từng group.

**Chỉ kiểm tra Swagger UI hiển thị được.** Swagger UI có thể render document dù operationId hoặc schema key đã đổi. Thêm integration test và snapshot/diff.

**Dùng generator mapping để che mọi thay đổi.** Mapping có thể giúp migration tạm thời nhưng không làm OpenAPI contract ổn định. Quản lý ID và schema name tại nguồn.

## 21. Checklist giữ định danh ổn định

- [ ] Khai báo operationId tường minh cho operation công khai.
- [ ] Dùng một quy ước tên operationId nhất quán và có ý nghĩa nghiệp vụ.
- [ ] Đảm bảo operationId duy nhất, phân biệt chữ hoa/chữ thường trong từng document.
- [ ] Không phụ thuộc tên method Java làm định danh SDK.
- [ ] Dùng @Schema(name = "...") cho component schema công khai cần giữ tên.
- [ ] Phân biệt component schema name với JSON property name.
- [ ] Dùng tên schema duy nhất, rõ domain và vai trò request/response.
- [ ] Không đưa tên entity/repository nội bộ vào contract công khai.
- [ ] Kiểm tra $ref, discriminator mapping và enum component.
- [ ] Giữ cùng tên cho operation/schema tương đương giữa các group.
- [ ] Kiểm tra OpenAPI JSON/YAML sau khi refactor.
- [ ] Có test uniqueness và regression test cho operationId/schema keys.
- [ ] Review diff OpenAPI và generated SDK trước mỗi lần phát hành.
- [ ] Có kế hoạch migration khi buộc phải đổi định danh công khai.

## 22. Kết luận

operationId và tên schema trong components.schemas là định danh mà công cụ OpenAPI và SDK generator có thể dùng để tạo method, model và tham chiếu. Springdoc có thể suy operationId từ tên handler method nếu không khai báo tường minh; tên model cũng có thể thay đổi khi refactor Java class. Dùng @Operation(operationId = "...") và @Schema(name = "...") để cố định tên công khai, đồng thời phân biệt component name với JSON property name. Cuối cùng, kiểm tra uniqueness, $ref, snapshot và generated SDK trong CI để phát hiện thay đổi ngoài ý muốn trước khi phát hành.

## 23. Nguồn tham khảo

- [OpenAPI Specification 3.1.2 — Operation Object](https://spec.openapis.org/oas/v3.1.2.html#operation-object): quy tắc operationId duy nhất, phân biệt chữ hoa/chữ thường và mục đích định danh.
- [springdoc-openapi FAQ v2](https://springdoc.org/v2/faq.html): ví dụ tạo operation bằng OpenApiCustomizer và cách springdoc xây schema component.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html): cấu hình @RouterOperation và yêu cầu khai báo operationId cho functional endpoint.
- [swagger-core — Operation annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html): thuộc tính operationId của @Operation.
- [swagger-core — Schema annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): tên schema/property và khả năng override schema bằng @Schema.
- [OpenAPI Generator — Customization](https://openapi-generator.tech/docs/customization/): mapping operationId và model name khi sinh SDK.
- [springdoc-openapi AbstractRequestService](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/service/AbstractRequestService.java): cách springdoc dùng operationId đã khai báo hoặc fallback sang tên handler method.
