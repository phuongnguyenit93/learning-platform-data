# Giữ operationId, tên schema và đường dẫn tài liệu ổn định khi có thể

Khi nâng cấp Spring Boot, springdoc-openapi hoặc Swagger Core, OpenAPI document có thể thay đổi dù controller vẫn xử lý request như trước. Một thay đổi nhỏ trong tên method Java, tên class DTO, cách nhóm tài liệu hoặc cấu hình endpoint docs có thể làm thay đổi operationId, component schema hoặc URL mà client dùng để tải đặc tả. Những thay đổi này ảnh hưởng đến code được sinh tự động, tool registry, API catalog, pipeline kiểm thử hợp đồng và các hệ thống tích hợp.

Vì vậy, khi di chuyển hoặc nâng cấp, cần phân biệt thay đổi nội bộ của ứng dụng với thay đổi hợp đồng công khai. Giữ operationId, tên schema, path operation, group id và đường dẫn tài liệu ổn định khi có thể. Nếu buộc phải thay đổi, hãy công bố thay đổi có chủ đích, duy trì đường tương thích trong thời gian chuyển tiếp và kiểm tra document được sinh ra trước khi phát hành.

## 1. Những định danh nào tạo nên tính ổn định của hợp đồng?

Một API có nhiều lớp định danh. Không phải tất cả đều có cùng ý nghĩa hoặc cùng ảnh hưởng:

| Thành phần | Ví dụ | Ảnh hưởng khi đổi |
| --- | --- | --- |
| HTTP method và path | GET /api/v1/orders/{id} | Thay đổi cách client gọi API; thường là thay đổi wire contract. |
| operationId | getOrderById | Có thể đổi tên hàm trong SDK, tool binding hoặc code sinh tự động. |
| Tên component schema | OrderResponse | Có thể làm thay đổi tên kiểu dữ liệu trong SDK hoặc tham chiếu $ref. |
| Tên property JSON | order_id | Thay đổi payload thực tế nếu Jackson serialize/deserialze theo tên mới. |
| Group id | partner-v1 | Thay đổi URL document của group và cấu hình client tải tài liệu. |
| API docs path | /v3/api-docs | Thay đổi URL lấy OpenAPI JSON/YAML. |
| Swagger UI path | /docs | Thay đổi URL giao diện người dùng. |
| Server URL | https://api.example.com | Thay đổi base URL mà client ghép với path operation. |

Đổi tên method Java không nhất thiết phải đổi operationId. Đổi tên class DTO không nhất thiết phải đổi component schema name. Đổi URL lấy tài liệu cũng không nhất thiết phải đổi path của API nghiệp vụ. Tách các lớp này giúp việc refactor và nâng cấp dependency ít gây tác động ngoài ý muốn.

## 2. Khai báo operationId tường minh

OpenAPI dùng operationId làm định danh operation. Công cụ sinh SDK thường dựa vào giá trị này để đặt tên method; registry hoặc tool caller cũng có thể lưu operation theo định danh đó. Nếu để springdoc tự suy ra operationId từ method Java, việc đổi tên method hoặc thay đổi cách phân tích có thể làm tên operation trong document thay đổi.

Hãy khai báo operationId rõ ràng bằng @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/v1/orders/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã"
    )
    OrderResponse getById(@PathVariable String id) {
        return orderService.getById(id);
    }
}
~~~

OrderService và OrderResponse là các kiểu miền được ứng dụng cung cấp; phần ví dụ tập trung vào mapping và operationId.

Sau này có thể đổi tên method Java từ getById thành findOrder mà vẫn giữ operationId là getOrderById. Client sinh từ OpenAPI document tiếp tục nhìn thấy cùng tên operation, miễn là các phần hợp đồng liên quan khác không thay đổi.

OperationId phải duy nhất trong một OpenAPI document. Không sao chép cùng một operationId cho hai operation khác nhau trong cùng document chỉ vì chúng gọi chung một service. Nếu có hai path tương thích cùng tồn tại trong giai đoạn chuyển tiếp, hãy đặt operationId riêng cho từng operation.

Nên dùng quy ước đặt tên nhất quán, chẳng hạn động từ + tài nguyên + khóa định danh:

| Mục đích | operationId gợi ý |
| --- | --- |
| Liệt kê đơn hàng | listOrders |
| Tìm đơn hàng | searchOrders |
| Lấy đơn hàng theo mã | getOrderById |
| Tạo đơn hàng | createOrder |
| Hủy đơn hàng | cancelOrder |
| Cập nhật địa chỉ giao hàng | updateOrderShippingAddress |

Tránh tên chung như process, execute, handle hoặc getData. Tên operationId nên mô tả hành vi công khai, không phụ thuộc tên class service hoặc cách tổ chức package nội bộ.

## 3. Giữ tên component schema ổn định

Springdoc thường tạo component schema từ kiểu Java được dùng trong request hoặc response. Nếu đổi tên class DTO, đổi package gây trùng tên hoặc thay đổi cấu trúc generic, tên schema được sinh có thể thay đổi. SDK generator có thể coi đây là kiểu dữ liệu mới dù JSON payload vẫn tương thích.

Dùng @Schema(name = "...") để công bố tên component rõ ràng:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "OrderResponse",
    description = "Thông tin đơn hàng được trả về cho client"
)
public record OrderResponse(
    @JsonProperty("order_id")
    String orderId,

    @JsonProperty("status")
    OrderStatus status
) {
}

@Schema(name = "OrderStatus")
enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
~~~

Trong ví dụ, OrderResponse và OrderStatus là tên component được công bố. Có thể đổi tên class Java hoặc chuyển package trong quá trình refactor mà vẫn giữ tên schema đã chọn, miễn là mapping và annotation còn được giữ đúng.

Phân biệt tên component với tên property JSON:

- @Schema(name = "OrderResponse") đặt tên schema trong components.schemas.
- @JsonProperty("order_id") xác định tên property trong JSON do Jackson xử lý.
- @Schema(description = "...") mô tả schema hoặc property; nó không tự đổi tên field JSON.

Nếu client đang gửi order_id, đổi thành orderId là thay đổi payload ngay cả khi component vẫn tên OrderResponse. Ngược lại, đổi tên component từ OrderResponse thành PurchaseOrderResponse có thể không làm thay đổi JSON payload, nhưng có thể ảnh hưởng code generator, $ref hoặc consumer đọc trực tiếp component name.

Tên schema phải duy nhất trong cùng document. Không gán cùng một tên cho hai DTO có cấu trúc hoặc ý nghĩa khác nhau. Nếu nhiều module có class OrderResponse, hãy dùng tên công khai phân biệt như CustomerOrderResponse và AdminOrderResponse thay vì dựa vào hậu tố package do thư viện tự sinh.

## 4. Giữ cấu trúc schema và tham chiếu $ref

Tên component ổn định chỉ hữu ích khi nội dung schema cũng được kiểm soát. Các thay đổi sau có thể phá tương thích dù component name không đổi:

- Đổi kiểu property từ string sang integer hoặc object.
- Thêm property bắt buộc.
- Xóa property mà client đang sử dụng.
- Thu hẹp enum hoặc thay đổi format.
- Đổi tên property JSON.
- Chuyển property từ nullable sang non-nullable.
- Thay đổi cấu trúc array, map hoặc generic wrapper.

Ví dụ một response schema có tên ổn định:

Đây là một khai báo thay thế, độc lập với record OrderResponse ở mục trước.

~~~java
@Schema(name = "OrderResponse")
public record OrderResponse(
    @Schema(description = "Mã đơn hàng", example = "ORD-1001")
    String orderId,
    @Schema(description = "Trạng thái hiện tại")
    OrderStatus status
) {
}
~~~

Khi thêm trường tùy chọn, hãy cân nhắc giá trị mặc định và cách client cũ xử lý property chưa biết. Khi đổi cấu trúc bắt buộc hoặc ý nghĩa field, cân nhắc version API mới thay vì âm thầm sửa schema hiện tại.

Kiểm tra cả các tham chiếu trong document. Một response có thể dùng:

~~~yaml
responses:
  '200':
    description: Đơn hàng được tìm thấy
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

Consumer có thể dựa trực tiếp vào tên component trong $ref. Không đổi tên component nếu không cần thiết; nếu đổi, kiểm tra toàn bộ requestBody, response, array item và schema lồng nhau đang tham chiếu đến nó.

## 5. Giữ path operation ổn định khi refactor controller

Path công khai được xác định bởi mapping Spring MVC/WebFlux, không phải tên class hoặc method Java. Có thể chuyển controller sang package khác, tách service hoặc đổi tên method mà vẫn giữ nguyên path:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders")
class OrderQueryController {

    private final OrderService orderService;

    OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById")
    OrderResponse find(@PathVariable String id) {
        return orderService.getById(id);
    }
}
~~~

Nếu muốn chuyển từ /api/v1/orders/{id} sang /api/orders/{id}, hãy xem đây là thay đổi URL công khai. Client cũ vẫn có thể gọi path cũ trong một thời gian nếu server duy trì route tương thích. Không nên chỉ đổi @RequestMapping rồi kỳ vọng springdoc giữ lại path cũ.

## 6. Duy trì path cũ trong thời gian chuyển tiếp

Khi cần đổi path, có thể duy trì hai mapping cùng gọi một service. Mỗi mapping có operationId riêng trong OpenAPI document:

Ví dụ này là phương án thay thế cho controller ở mục trước trong giai đoạn chuyển tiếp; OrderService được inject như một dependency của ứng dụng.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderQueryController {

    private final OrderService orderService;

    OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/v1/orders/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã",
        deprecated = true,
        description = "Dùng /api/orders/{id} cho tích hợp mới."
    )
    OrderResponse getLegacy(@PathVariable String id) {
        return orderService.getById(id);
    }

    @GetMapping("/api/orders/{id}")
    @Operation(
        operationId = "getOrderByIdCurrent",
        summary = "Lấy đơn hàng theo mã"
    )
    OrderResponse getCurrent(@PathVariable String id) {
        return orderService.getById(id);
    }
}
~~~

Mapping cũ giữ operationId getOrderById để consumer cũ có thể tiếp tục nhận diện operation đã dùng. Mapping mới có operationId riêng vì hai operation cùng xuất hiện trong một document và operationId phải duy nhất. Trường deprecated đánh dấu operation cũ không nên dùng cho tích hợp mới.

Trong thực tế, có thể dùng tên operationId cho path mới theo quy ước phiên bản của tổ chức. Ví dụ getOrderByIdV2 cũng hợp lệ. Điều quan trọng là không thay operationId của path cũ trong cùng đợt chuyển tiếp nếu muốn giữ tên method trong SDK cũ.

Không gắn deprecated = true vào một method được map đồng thời cho cả path cũ và path mới nếu chỉ muốn đánh dấu path cũ; annotation sẽ áp dụng cho operation được tạo từ method đó. Hãy dùng handler riêng hoặc customizer theo group/path khi cần trạng thái deprecation khác nhau.

Giữ route cũ trong thời gian đã công bố, theo dõi traffic và thông báo ngày ngừng hỗ trợ. Chỉ gỡ mapping cũ khi consumer đã chuyển đổi và chính sách vòng đời API cho phép.

## 7. Phân biệt path API với đường dẫn tải OpenAPI

Ứng dụng có nhiều đường dẫn trông gần giống nhau nhưng điều khiển các chức năng khác nhau:

| Cấu hình | Mục đích | Ví dụ |
| --- | --- | --- |
| @RequestMapping hoặc @GetMapping | Path API nghiệp vụ | /api/v1/orders/{id} |
| springdoc.api-docs.path | Endpoint tải OpenAPI JSON | /v3/api-docs |
| springdoc.swagger-ui.path | URL vào Swagger UI | /swagger-ui.html hoặc /docs |
| GroupedOpenApi.group | Định danh document của group | partner-v1 |
| server.servlet.context-path | Prefix của ứng dụng Servlet | /store |
| OpenAPI servers[].url | Base URL client dùng khi gọi operation | https://api.example.com |

Đổi springdoc.api-docs.path không tự đổi @RequestMapping của controller. Tuy nhiên, nó làm thay đổi URL mà registry, pipeline hoặc client dùng để tải document. Đổi springdoc.swagger-ui.path làm thay đổi URL giao diện, không đổi path operation bên trong OpenAPI.

Ví dụ giữ endpoint tài liệu ổn định:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /docs
~~~

Nếu cần đổi endpoint tài liệu, cập nhật đồng bộ pipeline export, API catalog, gateway route, security matcher, monitoring và tài liệu vận hành. Không thay đổi URL docs chỉ vì muốn đổi tên ứng dụng hoặc package.

## 8. Giữ group id ổn định

Với GroupedOpenApi, group id xuất hiện trong URL tài liệu:

Đoạn dưới là method bean đặt bên trong một class cấu hình Spring có @Configuration.

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-v1")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Document có URL JSON /v3/api-docs/partner-v1 và YAML /v3/api-docs/partner-v1.yaml. Nếu đổi group id từ partner-v1 thành partner-api, consumer tải document theo URL cũ sẽ không còn tìm thấy group cũ.

Group id khác với info.title và info.version trong OpenAPI. Group id định danh endpoint document do springdoc cung cấp; info.version mô tả phiên bản API trong nội dung document. Có thể cập nhật info.version mà vẫn giữ group id nếu hợp đồng tương thích. Ngược lại, không cần đổi group id chỉ vì đổi title hiển thị.

Nếu cần đổi group id, có thể công bố tạm thời cả group cũ và group mới với cùng phạm vi filter trong giai đoạn chuyển đổi. Kiểm tra security cho cả hai URL và đặt lịch loại bỏ group cũ. Không để group cũ tồn tại vô thời hạn nếu nó gây nhầm lẫn về nguồn tài liệu chính thức.

## 9. Giữ server URL và prefix nhất quán

OpenAPI servers[].url là base URL mà client kết hợp với path operation. Ví dụ:

~~~yaml
servers:
  - url: https://api.example.com
paths:
  /api/v1/orders/{id}:
    get:
      operationId: getOrderById
~~~

Client gọi URL hoàn chỉnh bằng cách ghép server và path. Nếu chuyển /api/v1 vào servers.url nhưng vẫn giữ /api/v1 trong paths, client có thể tạo URL lặp prefix.

Khi nâng cấp hoặc đổi reverse proxy, kiểm tra:

- Scheme public có còn là HTTPS không?
- Host và port public có đúng không?
- Context path hoặc prefix gateway có bị thêm hai lần không?
- OpenAPI paths có còn là path tương đối với server base URL không?
- Swagger UI có tải document qua đúng URL public không?

Nếu host public cố định, có thể cấu hình servers tường minh. Nếu host phụ thuộc môi trường, quản lý theo profile hoặc cấu hình triển khai. Không để hostname nội bộ của container xuất hiện trong document được chia sẻ cho client bên ngoài.

## 10. Những thay đổi thường an toàn và những thay đổi cần xem là breaking

Không thể phân loại mọi thay đổi chỉ bằng việc JSON document có khác hay không. Hãy xét cả wire contract và các consumer của OpenAPI:

| Thay đổi | Đánh giá thường gặp | Lý do |
| --- | --- | --- |
| Đổi tên method Java nhưng giữ operationId và mapping | An toàn với client | Tên nội bộ thay đổi, hợp đồng công khai giữ nguyên. |
| Đổi tên DTO nhưng giữ schema name và JSON properties | Thường an toàn với client | Component và payload công khai không đổi. |
| Đổi operationId | Có thể phá SDK/tool binding | Client generator có thể đổi tên method. |
| Đổi component schema name | Có thể phá code generator hoặc consumer dùng $ref | Tên kiểu dữ liệu công khai thay đổi. |
| Đổi JSON property name | Breaking | Payload thực tế thay đổi. |
| Đổi path hoặc HTTP method | Breaking | Client phải gọi URL hoặc method khác. |
| Xóa operation | Breaking | Consumer không còn endpoint đang dùng. |
| Thêm response field tùy chọn | Thường tương thích, nhưng cần kiểm tra client strict | Một số client/validator có thể từ chối field chưa biết. |
| Thêm request field tùy chọn | Thường tương thích nếu server xử lý khi vắng mặt | Client cũ vẫn có thể gửi request cũ. |
| Thêm request field bắt buộc | Breaking | Client cũ không gửi field mới. |
| Xóa enum value hoặc thu hẹp miền giá trị | Breaking với consumer có thể nhận giá trị đó | Client không còn xử lý được giá trị hợp lệ trước đây. |
| Đổi group id hoặc api-docs.path | Breaking với hệ thống tải document | URL discovery thay đổi dù API path có thể không đổi. |
| Đổi Swagger UI path | Ảnh hưởng người dùng giao diện và bookmark | URL giao diện thay đổi, API operation có thể giữ nguyên. |
| Đổi description hoặc example | Thường không đổi wire contract | Nhưng có thể ảnh hưởng tool caller dựa vào metadata hoặc quy trình review. |

Đây là đánh giá phổ biến, không thay thế kiểm thử consumer. Một client có thể phụ thuộc vào chi tiết tưởng như không quan trọng, ví dụ thứ tự hiển thị, tên tag hoặc nội dung description. Ghi nhận những phụ thuộc đó trong contract test nếu chúng là một phần của tích hợp.

## 11. Di chuyển dependency mà không vô tình đổi hợp đồng

Khi nâng cấp Spring Boot hoặc springdoc, thay đổi dependency có thể kéo theo thay đổi phiên bản Swagger Core, Jackson hoặc cách introspection annotation. Nên tách việc nâng cấp thư viện khỏi việc thiết kế API mới.

Ví dụ, khi chuyển một ứng dụng từ Spring Boot 2 với springdoc 1.x sang Spring Boot 3 với springdoc 2.x, dependency starter được thay đổi theo dòng phiên bản. Ứng dụng MVC dùng starter WebMVC tương ứng; ứng dụng reactive dùng starter WebFlux tương ứng. Quá trình này còn liên quan đến yêu cầu Java/Spring Boot và namespace Jakarta của Spring Boot 3.

Không dùng việc đổi artifact Maven/Gradle làm lý do đổi operationId, component name, group id hoặc path API. Trước khi nâng cấp:

1. Lưu OpenAPI JSON/YAML hiện tại làm baseline.
2. Ghi nhận các operationId, component schema name, path, method, group id và URL docs đang được consumer sử dụng.
3. Bổ sung operationId tường minh cho operation quan trọng đang phụ thuộc tên tự sinh.
4. Bổ sung @Schema(name = "...") cho component có tên được consumer sử dụng.
5. Pin phiên bản Spring Boot, springdoc và dependency liên quan trong quá trình nâng cấp.
6. Nâng cấp dependency và xử lý thay đổi source cần thiết.
7. Sinh lại document từ cùng cấu hình/profile.
8. So sánh baseline với document mới và phân loại từng khác biệt.
9. Chỉ chấp nhận thay đổi hợp đồng khi có lý do, versioning và kế hoạch chuyển đổi.

Không chỉnh tay OpenAPI JSON được sinh ra để che khác biệt trong khi source annotation/controller vẫn tạo document khác. Hãy sửa nguồn cấu hình hoặc metadata để kết quả được tái tạo nhất quán trong mọi môi trường.

## 12. Dùng baseline và contract diff trong CI

Lưu OpenAPI document đã được review vào nơi quản lý version của hợp đồng. Trong CI, sinh document từ build hiện tại rồi so sánh với baseline:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o build/openapi-current.json

openapi-diff \
  contracts/openapi-baseline.json \
  build/openapi-current.json
~~~

Lệnh openapi-diff là ví dụ minh họa cho một công cụ diff OpenAPI được pin trong pipeline; cú pháp và exit code phụ thuộc công cụ/phiên bản được chọn. Cấu hình pipeline để breaking change làm job thất bại hoặc yêu cầu phê duyệt rõ ràng.

Ngoài diff tổng thể, có thể kiểm tra các định danh quan trọng bằng test:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiStableIdentifiersTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void keepsOperationAndSchemaNamesStable() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        JsonNode operation = document.path("paths")
            .path("/api/v1/orders/{id}")
            .path("get");

        assertThat(operation.path("operationId").asText())
            .isEqualTo("getOrderById");

        assertThat(document.path("components").path("schemas")
            .has("OrderResponse")).isTrue();
    }
}
~~~

Test này kiểm tra tên operation và component schema. Bổ sung assertion cho path, response schema reference, JSON property và server URL theo những phần hợp đồng mà consumer thực sự phụ thuộc.

## 13. Kiểm tra document của từng group và URL export

Nếu ứng dụng có nhiều group, đừng chỉ kiểm tra document mặc định. Mỗi group có URL, filter và có thể có customizer riêng:

Method sau là phần bổ sung cho test class có MockMvc; cần static import get, status và jsonPath từ MockMvc test support.

~~~java
@Test
void keepsPartnerGroupDocumentAddressStable() throws Exception {
    mockMvc.perform(get("/v3/api-docs/partner-v1"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/api/partner/orders/{id}'].get.operationId")
            .value("getPartnerOrderById"));
}
~~~

Kiểm tra thêm:

- JSON và YAML của group.
- swagger-config có còn tham chiếu URL group cũ không.
- Security matcher có bao phủ URL mới/cũ trong giai đoạn chuyển tiếp không.
- API docs path có bị đổi theo profile hoặc biến môi trường không.
- Reverse proxy và gateway có route đúng endpoint tài liệu không.

Đường dẫn tài liệu là một API dành cho registry, pipeline và Swagger UI. Hãy version và thông báo thay đổi của nó như một điểm tích hợp riêng, kể cả khi path nghiệp vụ không thay đổi.

## 14. Deprecation và kế hoạch loại bỏ

Khi một operation, path, group hoặc schema cần được thay thế:

1. Giữ định danh cũ trong giai đoạn tương thích nếu có thể.
2. Đánh dấu operation cũ deprecated trong OpenAPI.
3. Mô tả operation hoặc path thay thế.
4. Công bố thời điểm ngừng hỗ trợ và cách chuyển đổi.
5. Theo dõi traffic, log hoặc consumer registry để biết ai còn dùng.
6. Duy trì contract test cho cả operation cũ và mới trong giai đoạn chuyển tiếp.
7. Gỡ operation cũ sau khi hết thời hạn hỗ trợ và đã kiểm tra consumer.

Deprecated là tín hiệu cho consumer, không tự ngăn server nhận request. Nếu muốn chặn sau ngày hết hạn, cần thay đổi runtime routing/security và công bố chính sách rõ ràng.

Không nên giữ alias vô thời hạn nếu nó làm tăng bề mặt bảo trì hoặc gây mơ hồ. Mục tiêu là có lộ trình tương thích có thời hạn và có thể đo lường.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| SDK đổi tên method sau khi refactor | operationId được suy ra từ tên method Java | Khai báo operationId tường minh và giữ ổn định. |
| Component schema đổi tên sau khi đổi DTO | Tên schema được suy ra từ class hoặc xử lý trùng tên | Dùng @Schema(name = "...") với tên duy nhất. |
| $ref không còn trỏ đến component cũ | Schema bị đổi tên hoặc bị loại khỏi document | Kiểm tra components.schemas và tất cả request/response tham chiếu. |
| Client cũ nhận lỗi sau khi đổi path | Mapping cũ đã bị xóa | Duy trì alias hoặc phát hành API version mới. |
| Hai operation có cùng operationId | Sao chép annotation khi tạo alias path | Đặt operationId riêng cho từng operation trong cùng document. |
| Group document trả 404 sau nâng cấp | Group id hoặc api-docs path thay đổi | Kiểm tra GroupedOpenApi, springdoc.api-docs.path và gateway route. |
| Swagger UI không tải được document | swagger-config vẫn trỏ URL cũ hoặc security matcher chưa cập nhật | Kiểm tra swagger-config, UI Network tab và matcher. |
| JSON field đổi dù component name không đổi | Jackson naming strategy hoặc @JsonProperty thay đổi | So sánh payload schema và giữ tên JSON công khai. |
| Diff có nhiều thay đổi sau khi nâng cấp dependency | Swagger Core/Jackson hoặc introspection thay đổi | Phân loại diff, thêm metadata tường minh và kiểm tra source gây ra thay đổi. |
| API path bị lặp version prefix | Version nằm đồng thời trong servers.url và paths | Chọn một quy ước base URL/path nhất quán. |
| Document nội bộ bị lộ trong group public | Filter group rộng hoặc thiếu exclude | Dùng allowlist và test chính xác operation set. |

## 16. Checklist trước khi phát hành bản nâng cấp

Trước khi publish document mới, xác nhận:

1. operationId quan trọng vẫn giữ nguyên và không bị trùng trong document.
2. Tên components.schemas được giữ ổn định hoặc có migration rõ ràng.
3. Tên property JSON, kiểu dữ liệu, required, enum và format không đổi ngoài dự kiến.
4. Path và HTTP method cũ vẫn tồn tại hoặc có kế hoạch version/alias.
5. Group id và URL JSON/YAML vẫn đúng với consumer.
6. springdoc.api-docs.path và springdoc.swagger-ui.path được kiểm tra riêng.
7. servers URL, context path và reverse proxy prefix không bị sai hoặc lặp.
8. swagger-config tham chiếu đúng group document.
9. Contract diff đã được review và breaking change có phê duyệt.
10. Deprecated operation có thời hạn hỗ trợ và hướng dẫn chuyển đổi.
11. Security matcher bảo vệ cả URL JSON, YAML và group alias.
12. Consumer hoặc SDK quan trọng đã được kiểm tra với document mới.

## 17. Nguyên tắc áp dụng

- Khai báo operationId tường minh cho operation công khai và giữ nó ổn định khi có thể.
- Dùng @Schema(name = "...") cho component schema mà consumer phụ thuộc.
- Dùng @JsonProperty để giữ tên property JSON độc lập với tên field Java.
- Giữ HTTP method và path ổn định; nếu đổi, duy trì alias hoặc version API có lộ trình.
- Dùng operationId riêng cho từng operation cùng tồn tại trong document.
- Phân biệt API path, group id, API docs path, Swagger UI path và server URL.
- Không coi việc đổi dependency là lý do tự động đổi hợp đồng công khai.
- Lưu baseline OpenAPI và chạy contract diff trong CI.
- Đánh dấu deprecation, thông báo thời hạn và theo dõi consumer trước khi xóa API cũ.
- Kiểm tra từng group, JSON/YAML, swagger-config, security và URL public sau nâng cấp.

Tính ổn định của hợp đồng đến từ những định danh và hành vi mà consumer thực sự sử dụng. operationId giữ tên operation trong SDK và tool binding; tên schema giữ tham chiếu và kiểu dữ liệu công khai; path cùng group id và docs path giữ địa chỉ mà client hoặc registry truy cập. Khi nâng cấp Spring Boot và springdoc, hãy lưu baseline, khai báo định danh tường minh, so sánh document mới và xử lý khác biệt bằng alias, deprecation hoặc version API có kế hoạch. Cách này cho phép refactor nội bộ và nâng cấp dependency mà không vô tình phá các tích hợp đang hoạt động.

## Tài liệu tham khảo

- [Springdoc OpenAPI – FAQ và GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object)
- [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/reference/upgrading/index.html)
