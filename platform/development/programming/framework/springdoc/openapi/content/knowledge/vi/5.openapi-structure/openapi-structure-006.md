# Tags và cách tổ chức các operation theo chủ đề

Tags là cách phân nhóm operation theo chủ đề trong một OpenAPI document. Chúng giúp developer tìm endpoint theo tài nguyên hoặc mảng nghiệp vụ, hiểu ranh giới của API và điều hướng Swagger UI thuận tiện hơn. Một tag không tạo route mới, không lọc quyền truy cập và cũng không tách API thành document riêng.

Trong springdoc-openapi, có thể khai báo tag ở cấp controller bằng @Tag, gán tag cho từng operation bằng @Operation(tags = ...), hoặc mô tả danh sách tag chung bằng @OpenAPIDefinition. Khi thiết kế, cần giữ tên tag nhất quán, chọn mức độ chi tiết phù hợp và phân biệt tag với GroupedOpenApi.

Bài này hướng dẫn thiết kế taxonomy tag cho API Spring Boot, áp dụng annotation, xử lý operation có nhiều tag, sắp xếp trên Swagger UI, kiểm tra OpenAPI JSON và tránh các lỗi tổ chức thường gặp.

## 1. Tag giải quyết vấn đề gì?

Một API có thể chứa hàng chục hoặc hàng trăm operation. Nếu tất cả operation xuất hiện trong một danh sách dài, người dùng khó tìm được chức năng liên quan.

Tags tạo các nhóm chủ đề để người đọc điều hướng:

~~~text
OpenAPI document
|
+-- Orders
|   +-- GET    /api/orders
|   +-- POST   /api/orders
|   +-- GET    /api/orders/{id}
|   +-- PATCH  /api/orders/{id}
|
+-- Customers
|   +-- GET    /api/customers
|   +-- POST   /api/customers
|
+-- Payments
    +-- POST   /api/payments
    +-- GET    /api/payments/{id}
~~~

Trong ví dụ, Orders, Customers và Payments là các tag. Mỗi HTTP method/path vẫn là một operation riêng trong `paths`.

Tags giúp gom operation có cùng chủ đề, giảm thời gian tìm endpoint, làm rõ phạm vi nghiệp vụ, giữ cách điều hướng nhất quán giữa controller và hỗ trợ API portal trình bày tài liệu. Tag là metadata tổ chức tài liệu; nó không thay đổi cách Spring ánh xạ URL hoặc xử lý request.

## 2. Tag trong OpenAPI document gồm hai phần liên quan

OpenAPI biểu diễn tag ở hai vị trí:

1. Danh sách `tags` ở cấp root document dùng để khai báo thông tin chung của tag.
2. Thuộc tính `tags` trong từng Operation Object dùng để gán operation vào một hoặc nhiều nhóm.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
tags:
  - name: Orders
    description: Quản lý đơn hàng
  - name: Customers
    description: Quản lý khách hàng
paths:
  /api/orders:
    get:
      tags:
        - Orders
      summary: Liệt kê đơn hàng
      responses:
        "200":
          description: Thành công
~~~

`tags[0].name` ở cấp root là tên nhóm và `paths./api/orders.get.tags` tham chiếu nhóm đó. Danh sách root tags có thể cung cấp description, external documentation và metadata khác. Operation tags chỉ gán operation vào nhóm.

Chỉ khai báo root tag mà không gán tag vào operation chưa chắc tạo được cách nhóm operation như mong muốn. Ngược lại, operation có thể khai báo tên tag nhưng thiếu mô tả chung ở root.

## 3. Tag không phải path, controller hay API version

| Thành phần | Vai trò |
|---|---|
| Path | Địa chỉ tài nguyên HTTP, ví dụ `/api/orders/{id}` |
| HTTP method | Hành động trên path, ví dụ GET, POST, PATCH |
| Controller | Thành phần Spring xử lý một nhóm request |
| Tag | Nhóm operation theo chủ đề trong OpenAPI document |
| GroupedOpenApi | Tạo một OpenAPI document riêng theo tiêu chí lọc |
| API version | Phiên bản contract được công bố cho consumer |

Một controller có thể đóng góp operation cho nhiều tag. Một tag cũng có thể gom operation từ nhiều controller. Không cần tạo controller mới chỉ vì muốn tạo thêm tag.

Đổi tag từ Orders thành Order Management không làm đổi URL, request schema hay response schema. Đây là thay đổi tổ chức tài liệu, không phải thay đổi route.

## 4. Chọn taxonomy theo tài nguyên và nghiệp vụ

Một taxonomy dễ hiểu thường dùng danh từ đại diện cho tài nguyên hoặc capability nghiệp vụ:

- Orders
- Customers
- Payments
- Inventory
- Shipping
- Reports

Với REST API quản lý tài nguyên, dùng tên tài nguyên thường là điểm bắt đầu tốt.

Hạn chế tạo tag theo từng hành động:

~~~text
CreateOrder
GetOrder
UpdateOrder
DeleteOrder
~~~

Các tên này thường làm một tài nguyên bị chia thành nhiều nhóm nhỏ, khiến người dùng phải chuyển qua lại để tìm các operation cùng liên quan đến Orders. Hành động đã được thể hiện bởi HTTP method và summary của operation; tag nên giữ vai trò chủ đề bao quát.

## 5. Quy tắc đặt tên tag

Nên thống nhất quy ước tên trong toàn bộ document:

- Dùng danh từ hoặc tên capability dễ hiểu.
- Giữ cách viết hoa nhất quán, ví dụ Pascal Case hoặc Title Case.
- Dùng một ngôn ngữ thống nhất trong cùng API.
- Tránh tên quá chung như Common, Other, Misc hoặc Default.
- Tránh nhúng HTTP method vào tag.
- Tránh thêm version vào tên tag nếu version đã được thể hiện ở document hoặc path.
- Không tạo hai tag chỉ khác chữ hoa/chữ thường.
- Không dùng tên nội bộ khó hiểu với consumer.

| Chủ đề | Tag |
|---|---|
| Đơn hàng | Orders |
| Khách hàng | Customers |
| Thanh toán | Payments |
| Kho | Inventory |
| Vận chuyển | Shipping |

Tên tag phải khớp chính xác giữa root declaration và operation reference. Xem tag như một identifier trong tài liệu, không phải đoạn text tự do để mỗi controller đặt một kiểu.

## 6. Chọn mức độ chi tiết phù hợp

Tag quá rộng làm nhóm có quá nhiều operation. Tag quá nhỏ làm danh sách nhóm dài và phân mảnh.

Ví dụ một API thương mại điện tử có thể bắt đầu bằng:

~~~text
Orders
Customers
Payments
Products
Inventory
Shipping
~~~

Nếu Orders có nhiều operation thuộc những capability thực sự độc lập, có thể cân nhắc Orders, Order Fulfillment và Order Returns. Chỉ tách khi consumer có nhu cầu tìm kiếm hoặc nhóm chức năng khác biệt. Đừng tách tag chỉ vì một controller có nhiều method.

Một tiêu chí thực tế: người đọc có thể dự đoán operation cần tìm nằm trong tag nào mà không phải hiểu cấu trúc package Java của server.

## 7. Tránh tag theo tên lớp hoặc tên team

Tên lớp như `OrderController`, `OrderAdminController`, `OrderQueryController` phản ánh cách tổ chức code. Consumer API không nhất thiết cần biết những lớp này. Tên team như Team A hoặc Backend Squad cũng không mô tả capability API.

Thay vì chia theo tên controller, có thể dùng Orders, Order Administration hoặc Order Search. Tuy nhiên, nếu các operation đều thuộc cùng chủ đề Orders thì một tag Orders có thể đã đủ.

Tên controller không nên tự động trở thành taxonomy chính thức nếu nhóm muốn contract ổn định qua refactor code.

## 8. Dùng @Tag ở cấp controller

Cách phổ biến nhất trong Spring Boot là gắn @Tag lên controller:

~~~java
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Các thao tác tạo, tra cứu và cập nhật đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

springdoc dùng metadata này để tổ chức các operation của controller theo tag Orders. `name` là tên nhóm; `description` giải thích nhóm chứa chức năng gì.

Đặt @Tag ở cấp controller phù hợp khi phần lớn operation trong controller thuộc cùng một chủ đề. Nếu controller chỉ chứa operation thuộc một domain nhưng có một vài operation đặc biệt, có thể gán tag riêng ở cấp operation.

## 9. Gắn @Operation(tags = ...) ở cấp method

Khi một operation cần được nhóm theo tag khác controller hoặc cần nhiều tag, khai báo trên @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Tìm đơn hàng theo mã",
    tags = {"Orders", "Order Search"}
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

Thuộc tính `tags` nhận danh sách tên tag. Mỗi tên phải tuân theo taxonomy của document.

Một operation có thể được gắn nhiều tag nếu nó thực sự phục vụ nhiều chủ đề. Swagger UI và các consumer có thể hiển thị operation trong nhiều nhóm điều hướng, nhưng OpenAPI vẫn mô tả một operation duy nhất.

Không dùng nhiều tag chỉ để tạo cảm giác operation quan trọng. Mỗi tag thêm vào nên giúp một nhóm người đọc tìm operation theo một lý do cụ thể.

## 10. Ví dụ controller đầy đủ

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Quản lý vòng đời đơn hàng"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(summary = "Liệt kê đơn hàng")
    @GetMapping
    List<OrderResponse> list() {
        // ...
    }

    @Operation(summary = "Tạo đơn hàng")
    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }

    @Operation(
        summary = "Tra cứu đơn hàng",
        description = "Tìm một đơn hàng theo mã định danh"
    )
    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable String id) {
        // ...
    }
}
~~~

Ở đây @Tag định nghĩa chủ đề cho controller. Các operation có summary riêng để mô tả hành động.

Không cần lặp `tags = {"Orders"}` trên từng @Operation nếu tag ở cấp controller đã thể hiện đúng ý định và output thực tế của springdoc phù hợp.

## 11. Dùng @OpenAPIDefinition để khai báo tag chung

Khi muốn mô tả danh sách tag ở cấp document, dùng @OpenAPIDefinition:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Commerce API", version = "1.0.0"),
    tags = {
        @Tag(name = "Orders", description = "Quản lý đơn hàng"),
        @Tag(name = "Customers", description = "Quản lý khách hàng"),
        @Tag(name = "Payments", description = "Xử lý thanh toán")
    }
)
class OpenApiConfiguration {
}
~~~

Danh sách `tags` ở đây cung cấp metadata chung cho document. Controller hoặc method vẫn cần gán operation vào tag tương ứng.

Đặt cấu hình này trong class được Spring phát hiện, chẳng hạn @Configuration. Nếu class không được component scan hoặc không tham gia context, metadata có thể không được áp dụng.

## 12. Bổ sung external documentation cho tag

Tag Object có thể chứa liên kết tài liệu ngoài:

~~~java
@Tag(
    name = "Payments",
    description = "Tạo và tra cứu giao dịch thanh toán",
    externalDocs = @ExternalDocumentation(
        description = "Hướng dẫn tích hợp thanh toán",
        url = "https://docs.example.com/payments"
    )
)
~~~

Liên kết này hữu ích khi một nhóm operation cần tài liệu nghiệp vụ sâu hơn OpenAPI description, chẳng hạn quy tắc đối soát, trạng thái giao dịch hoặc quy trình xử lý hoàn tiền.

Chỉ đưa URL đã được công bố và có thể truy cập bởi đối tượng sử dụng tài liệu. Không dùng externalDocs để trỏ tới tài liệu nội bộ nhạy cảm trong một public OpenAPI document.

## 13. Tổ chức operation từ nhiều controller vào cùng tag

Một tag không bị giới hạn bởi một controller.

~~~java
@Tag(name = "Orders", description = "Quản lý đơn hàng")
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // CRUD operations
}
~~~

~~~java
@Tag(name = "Orders", description = "Quản lý đơn hàng")
@RestController
@RequestMapping("/api/order-items")
class OrderItemController {
    // Operations on order items
}
~~~

Cả hai controller có thể đóng góp operation vào nhóm Orders nếu đó là cách tổ chức phù hợp với consumer.

Nếu description được khai báo nhiều lần, cần giữ nội dung nhất quán. Tốt hơn là quản lý metadata tag chung tại một nơi và chỉ gán tên tag ở các controller/method khác.

Tránh khai báo cùng tên tag với description khác nhau ở nhiều class. Kết quả hợp nhất có thể khó dự đoán hoặc làm document có metadata trùng lặp tùy cách xử lý thư viện.

## 14. Operation thuộc nhiều tag

Một operation có thể liên quan tới nhiều chủ đề:

~~~java
@Operation(
    summary = "Tra cứu trạng thái thanh toán của đơn hàng",
    tags = {"Orders", "Payments"}
)
@GetMapping("/api/orders/{id}/payment")
PaymentStatusResponse paymentStatus(@PathVariable String id) {
    // ...
}
~~~

Điều này giúp người tìm từ Orders hoặc Payments đều có thể thấy operation.

Cần dùng có chọn lọc. Nếu phần lớn operation đều gắn vào ba hoặc bốn tag, taxonomy không còn giúp phân loại rõ ràng. Hãy đặt một tag chính theo chủ đề sở hữu operation. Tag phụ chỉ thêm khi có nhu cầu điều hướng thực tế.

## 15. Tag operation không tạo thêm endpoint

Ví dụ một operation có:

~~~yaml
paths:
  /api/orders/{id}/payment:
    get:
      tags:
        - Orders
        - Payments
      summary: Tra cứu trạng thái thanh toán
~~~

Đây vẫn là một GET operation tại `/api/orders/{id}/payment`. Việc gắn hai tag không tạo hai route, không nhân đôi controller method và không thay đổi request mapping.

Swagger UI có thể hiển thị operation dưới hai nhóm. Các tool khác có thể chọn cách trình bày riêng, nhưng contract vẫn chỉ có một path/method.

Không dùng multi-tag như một cách tạo alias endpoint. Nếu cần hai URL khác nhau, hãy khai báo hai route hoặc thiết kế API phù hợp.

## 16. Khai báo tag trong OpenAPI model bằng customizer

Nếu taxonomy được quản lý tập trung hoặc phụ thuộc cấu hình, có thể thêm Tag Object bằng OpenApiCustomizer:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.models.tags.Tag;

@Configuration
class OpenApiTagConfiguration {

    @Bean
    OpenApiCustomizer tagMetadata() {
        return openApi -> openApi.addTagsItem(
            new Tag()
                .name("Orders")
                .description("Quản lý đơn hàng")
        );
    }
}
~~~

Customizer tác động lên OpenAPI model trước khi document được serialize. Hãy bảo đảm không thêm tag trùng tên mỗi lần document được tạo.

Nếu dùng nhiều document GroupedOpenApi, xác định rõ customizer áp dụng cho document mặc định hay từng group. Dùng global customizer hoặc customizer gắn vào group theo phạm vi mong muốn, rồi kiểm tra từng endpoint document.

## 17. Duy trì danh sách tag nhất quán

Khi document lớn, nên quản lý tag như một taxonomy có quy ước:

| Tag | Phạm vi operation | Chủ đề loại trừ |
|---|---|---|
| Orders | Tạo, đọc, cập nhật và hủy đơn | Thanh toán độc lập |
| Customers | Hồ sơ và thông tin khách hàng | Authentication |
| Payments | Giao dịch, hoàn tiền, trạng thái thanh toán | Vận chuyển |
| Inventory | Tồn kho và điều chỉnh số lượng | Danh mục sản phẩm |
| Shipping | Địa chỉ giao, vận đơn và theo dõi | Order fulfillment nội bộ |

Khi thêm controller hoặc operation, nhóm phát triển chọn tag hiện có trước khi tạo tag mới. Một tag mới nên được thêm khi có chủ đề rõ ràng và đủ operation hoặc đủ giá trị điều hướng để tồn tại độc lập.

## 18. Tag và GroupedOpenApi khác nhau

Đây là điểm quan trọng khi tổ chức tài liệu lớn:

- Tag nhóm operation bên trong một OpenAPI document.
- GroupedOpenApi tạo document riêng, thường dựa trên path, package hoặc cấu hình lọc.

Một document có thể chứa tất cả API nhưng chia thành Orders, Customers, Payments. Đây là tổ chức bằng tag.

GroupedOpenApi có thể tạo các document `/v3/api-docs/public` và `/v3/api-docs/internal`, mỗi document có paths và operations khác nhau.

| Tiêu chí | Tags | GroupedOpenApi |
|---|---|---|
| Mục đích | Nhóm operation theo chủ đề | Tách tài liệu thành các nhóm document |
| Số document | Không làm tăng số document | Tạo document riêng cho từng group |
| Lọc path/package | Không | Có |
| Tạo URL document riêng | Không | Có |
| Ẩn operation khỏi document khác | Không | Có thể lọc khỏi group |
| Điều hướng Swagger UI | Có | Có thể chọn document/group |

Không dùng tag để thay thế security hoặc filtering. Nếu internal operation không được công bố trong public document, hãy tạo group/filter phù hợp và bảo vệ endpoint thật.

## 19. Ví dụ GroupedOpenApi kết hợp tags

Có thể khai báo document public riêng:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/admin/**")
            .build();
    }
}
~~~

Hai document có endpoint:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
~~~

Mỗi document vẫn có thể dùng tags Orders, Customers hoặc Administration để nhóm operation bên trong nó.

Một tag có thể xuất hiện trong nhiều group. Group xác định operation nào thuộc document; tag xác định cách tổ chức operation trong document đó.

## 20. Tag không phải cơ chế bảo mật

Không thể bảo vệ endpoint bằng cách đổi tag hoặc không hiển thị tag trong Swagger UI.

Ví dụ, operation có tag Internal:

~~~java
@Operation(tags = {"Internal"})
@GetMapping("/admin/rebuild-index")
void rebuildIndex() {
    // ...
}
~~~

Tên tag Internal không làm endpoint trở thành riêng tư. Bất kỳ client nào biết URL và có quyền truy cập mạng vẫn có thể gửi request.

Bảo vệ endpoint bằng Spring Security, authorization, network policy hoặc gateway. Nếu không muốn công bố operation trong public OpenAPI document, dùng filter/group phù hợp; đồng thời bảo đảm endpoint thực tế có access control.

## 21. Ẩn operation khác với gán tag

Có thể ẩn operation khỏi tài liệu bằng @Hidden hoặc `@Operation(hidden = true)`:

~~~java
@Operation(hidden = true)
@PostMapping("/internal/reindex")
void reindex() {
    // ...
}
~~~

Việc ẩn này chỉ ảnh hưởng document được sinh. Nó không vô hiệu route.

Nếu API có tài liệu public và internal, cân nhắc tạo hai GroupedOpenApi với filter rõ ràng thay vì chỉ dựa vào một tag tên Internal.

Không sử dụng tag như Hidden, Private hoặc Secret với kỳ vọng Swagger UI sẽ tự bảo vệ nội dung.

## 22. Sắp xếp tag trong Swagger UI

Swagger UI có thể sắp xếp tag theo alphabet:

~~~yaml
springdoc:
  swagger-ui:
    tags-sorter: alpha
~~~

Hoặc application.properties:

~~~properties
springdoc.swagger-ui.tagsSorter=alpha
~~~

Tùy chọn này tác động cách hiển thị nhóm trong Swagger UI. Nó không thay đổi tên tag, không thay đổi OpenAPI contract và không tự sắp xếp mọi tag trong JSON/YAML.

Nếu muốn giữ thứ tự nghiệp vụ, khai báo tag theo thứ tự mong muốn ở root document và kiểm tra hành vi UI khi không cấu hình sorter. Nếu dùng `tags-sorter: alpha`, thứ tự UI sẽ theo alphabet dù root list có thứ tự khác.

## 23. Sắp xếp operation bên trong tag

Swagger UI có thuộc tính operationsSorter:

~~~yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
~~~

Hoặc:

~~~properties
springdoc.swagger-ui.operationsSorter=alpha
~~~

Các lựa chọn phổ biến:

- `alpha`: sắp xếp operation theo path.
- `method`: sắp xếp theo HTTP method.
- Hàm JavaScript tùy chỉnh: khi UI được cấu hình để nhận sorter function phù hợp.

Sắp xếp operation khác sắp xếp tag. `tags-sorter` điều khiển thứ tự nhóm; `operations-sorter` điều khiển thứ tự operation trong nhóm.

Đây là tùy chọn giao diện. Không dùng nó làm bằng chứng rằng OpenAPI JSON đã được chuẩn hóa thứ tự hoặc semantic diff đã ổn định.

## 24. Giữ thứ tự tag có chủ đích

Nếu cần thứ tự tag riêng, có thể khai báo root tags theo thứ tự mong muốn trong @OpenAPIDefinition:

~~~java
@OpenAPIDefinition(
    tags = {
        @Tag(name = "Orders", description = "Quản lý đơn hàng"),
        @Tag(name = "Payments", description = "Xử lý thanh toán"),
        @Tag(name = "Customers", description = "Quản lý khách hàng")
    }
)
~~~

Hoặc sắp xếp model trong customizer:

~~~java
@Bean
OpenApiCustomizer stableTagOrder() {
    return openApi -> {
        if (openApi.getTags() != null) {
            openApi.getTags().sort(
                Comparator.comparing(
                    Tag::getName,
                    Comparator.nullsLast(String::compareTo)
                )
            );
        }
    };
}
~~~

Chỉ sắp xếp alphabet khi đó là quy ước của nhóm. Nếu muốn ưu tiên Orders, Payments, Customers theo hành trình nghiệp vụ, dùng thứ tự tường minh thay vì alphabet.

Nếu Swagger UI có sorter riêng, nó có thể ghi đè thứ tự mà document cung cấp trong giao diện. Hãy kiểm tra cả file JSON và UI theo đúng mục tiêu.

## 25. Tag và controller inheritance

Một số dự án dùng base controller hoặc interface để chia sẻ endpoint metadata. Khi có annotation ở interface, superclass và concrete controller, cần kiểm tra cách Spring và swagger-core đọc annotation trong cấu trúc đó.

Không giả định mọi annotation trên interface đều được kế thừa giống annotation Java thông thường. Kết quả còn phụ thuộc annotation target, retention và cách springdoc khám phá handler method.

Nếu tag bị thiếu hoặc lặp:

1. Kiểm tra class thực sự được đăng ký làm controller.
2. Kiểm tra vị trí @Tag.
3. Kiểm tra @Operation.tags trên method.
4. Xem OpenAPI JSON đầu ra.
5. Tránh khai báo cùng tag metadata trên nhiều lớp nếu không cần.

Với API contract quan trọng, một test kiểm tra tag cho từng operation giúp phát hiện thay đổi khi refactor controller.

## 26. Tổ chức tag cho API lớn

Với API có nhiều domain, bắt đầu từ các bounded context hoặc capability mà consumer nhận biết:

~~~text
Accounts
Customers
Orders
Payments
Inventory
Shipping
Notifications
Reports
~~~

Nếu một nhóm quá lớn, phân tích operation theo mục đích sử dụng. Có thể tách Order Fulfillment khỏi Orders nếu đó là capability riêng, có consumer và quy trình khác biệt.

Tránh tạo cây tag lồng nhiều tầng như:

~~~text
Commerce
  Orders
    Create
    Update
  Payments
    Refund
    Capture
~~~

OpenAPI Tag Object không định nghĩa taxonomy phân cấp chuẩn. Dấu cách, dấu / hoặc tiền tố chỉ tạo tên tag phẳng, không phải cấu trúc cây có semantics chung.

Nếu cần navigation phân cấp, dùng API portal hỗ trợ taxonomy riêng hoặc nhiều OpenAPI group.

## 27. Tag cho operation dùng chung

Các operation như health check, metadata hoặc authentication có thể không thuộc domain resource chính. Có thể chọn nhóm System, Authentication, Metadata hoặc Administration.

Tên phải mô tả đúng chức năng và phù hợp với consumer. Không gom tất cả operation khó phân loại vào Common.

Nếu endpoint chỉ phục vụ health probe và không dành cho API consumer, cân nhắc không đưa vào document public hoặc tạo document vận hành riêng.

## 28. Tag trong nhiều API version

Nếu document có nhiều version API, quyết định tag có giữ nguyên tên giữa các version hay không.

~~~text
v1:
  Orders
  Payments

v2:
  Orders
  Payments
  Fulfillment
~~~

Giữ tên tag ổn định giúp người dùng so sánh tài liệu qua version. Nếu capability đổi phạm vi đáng kể, có thể cần tên tag mới, nhưng hãy ghi rõ trong migration notes.

Không nhúng v1 hoặc v2 vào mọi tag nếu version đã được biểu diễn bằng path, server hoặc document metadata. Điều đó dễ tạo ra taxonomy trùng lặp.

## 29. Tag và code generation

Một số API portal và client generator sử dụng tags để nhóm operation hoặc sinh API class theo tag. Ví dụ, một generator có thể tạo `OrdersApi`, `PaymentsApi` từ tag tương ứng.

Vì vậy, đổi tag có thể ảnh hưởng tên class hoặc nhóm method trong generated SDK dù HTTP route không đổi.

Trước khi đổi tên tag trong API đã phát hành:

- Kiểm tra generator đang sử dụng.
- So sánh output SDK trước và sau.
- Xác định có thay đổi source compatibility cho consumer không.
- Ghi migration note nếu class/API grouping thay đổi.
- Giữ operationId ổn định nếu có thể.

Tag không chỉ là trang trí UI; một số toolchain dùng nó như metadata để tổ chức code được sinh.

## 30. Kiểm tra tag trong OpenAPI JSON

Sau khi chạy ứng dụng, tải document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

Xem danh sách tag root:

~~~bash
jq '.tags' target/openapi.json
~~~

Xem tag của một operation:

~~~bash
jq '.paths["/api/orders"].get.tags' target/openapi.json
~~~

Liệt kê các tag đang được operation sử dụng:

~~~bash
jq -r '.paths[] | to_entries[] | .value.tags[]? ' target/openapi.json |
  sort -u
~~~

Lệnh trên giúp kiểm tra tên tag thực tế trong document. So sánh với taxonomy đã thống nhất để phát hiện tag viết hoa khác nhau, tên cũ còn sót hoặc nhóm không mong muốn.

## 31. Kiểm tra tag root chưa được sử dụng

Có thể đối chiếu danh sách root tags với tag được gán vào operation:

~~~bash
jq -r '.tags[]?.name' target/openapi.json | sort -u
~~~

~~~bash
jq -r '.paths[] | to_entries[] | .value.tags[]?' target/openapi.json |
  sort -u
~~~

Nếu có root tag không được operation nào sử dụng, xem xét xóa hoặc xác nhận tag được giữ lại có chủ đích cho tài liệu.

Nếu operation sử dụng tag không có root declaration, cân nhắc bổ sung Tag Object để cung cấp description và externalDocs nhất quán. Một số tool vẫn hiển thị tag chưa có root metadata, nhưng document rõ ràng hơn khi khai báo đầy đủ.

## 32. Kiểm thử tag bằng WebTestClient

Ví dụ kiểm tra tag của operation:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiTagsTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void assignsOrdersTagToOrderOperations() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/orders'].get.tags[0]")
                .isEqualTo("Orders")
            .jsonPath("$.paths['/api/orders'].post.tags[0]")
                .isEqualTo("Orders");
    }
}
~~~

Test này giả định operation tags có Orders ở vị trí đầu tiên. Nếu operation có nhiều tag hoặc thứ tự không phải contract, hãy parse JSON và kiểm tra danh sách có chứa tag thay vì phụ thuộc index.

Cũng nên test root tag metadata:

~~~java
@Test
void publishesOrdersTagDescription() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.tags[?(@.name == 'Orders')].description")
        .isEqualTo("Quản lý vòng đời đơn hàng");
}
~~~

JSONPath filter có thể được hỗ trợ khác nhau giữa thư viện test. Nếu biểu thức không phù hợp, parse document thành JsonNode và tìm phần tử theo `name`.

## 33. Kiểm thử nhiều group

Nếu có GroupedOpenApi, kiểm tra tag trong từng document:

~~~text
/v3/api-docs/public
/v3/api-docs/internal
~~~

Các group có thể có tập operation khác nhau nhưng dùng chung taxonomy.

Test nên xác nhận operation public có tag dự kiến, operation internal không lọt vào public document, root tag metadata có mặt ở group cần thiết, customizer áp dụng đúng phạm vi và không có tag thừa hoặc tag trùng.

Đừng chỉ kiểm tra document mặc định nếu production đang phân phối nhiều group.

## 34. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI có nhiều tag gần giống | Tên khác chữ hoa, dấu cách hoặc số ít/số nhiều |
| Operation nằm trong tag không mong muốn | @Tag ở controller hoặc @Operation.tags chưa nhất quán |
| Root tag có description nhưng nhóm trống | Không có operation nào tham chiếu tag |
| Operation có tag nhưng thiếu mô tả | Chưa khai báo Tag Object ở root |
| Operation xuất hiện trong nhiều nhóm | Có nhiều tên tag trong @Operation.tags |
| Đổi tag làm SDK thay đổi | Generator dùng tag để nhóm class/API |
| Swagger UI sort khác JSON | tags-sorter hoặc operations-sorter thay đổi cách hiển thị |
| Gắn tag Internal nhưng endpoint vẫn gọi được | Tag không phải cơ chế bảo mật |
| Dùng tag để tách public/internal nhưng document vẫn chứa cả hai | Cần GroupedOpenApi hoặc filter |
| Tag trùng sau khi chia controller | Nhiều lớp khai báo metadata khác nhau |
| Tag mất sau refactor | Annotation trên interface/base class không được phát hiện như dự kiến |
| Quá nhiều tag | Taxonomy chia theo method hoặc tên controller |

## 35. Quy trình thiết kế và review taxonomy

Khi thiết kế tag cho API mới:

1. Liệt kê các tài nguyên và capability mà consumer nhận biết.
2. Chọn danh từ hoặc tên nghiệp vụ ngắn, nhất quán.
3. Xác định phạm vi operation của từng tag.
4. Gắn @Tag ở controller khi toàn bộ controller cùng chủ đề.
5. Dùng @Operation.tags cho operation đặc biệt hoặc nhiều chủ đề.
6. Khai báo description chung ở @OpenAPIDefinition khi cần.
7. Kiểm tra root tags và operation tags trong JSON.
8. Sắp xếp tag/operation theo chính sách UI.
9. Kiểm tra GroupedOpenApi riêng nếu có nhiều document.
10. Review ảnh hưởng đến API portal và generated SDK trước khi đổi tên tag.

Khi review pull request, yêu cầu người thay đổi giải thích tag mới phục vụ nhu cầu tìm kiếm nào. Nếu không có câu trả lời rõ ràng, tag mới có thể đang làm taxonomy phức tạp hơn cần thiết.

## 36. Checklist

- [ ] Tag mô tả chủ đề hoặc capability, không mô tả HTTP method.
- [ ] Tên tag nhất quán về chữ hoa, số ít/số nhiều và ngôn ngữ.
- [ ] Không tạo tag theo từng operation nếu không có nhu cầu rõ.
- [ ] Root Tag Object có description phù hợp.
- [ ] Operation tags tham chiếu đúng tên tag.
- [ ] @Tag được dùng ở controller có cùng chủ đề.
- [ ] @Operation(tags = ...) chỉ dùng khi cần gán riêng hoặc nhiều chủ đề.
- [ ] Tag không bị nhầm với path, controller hoặc API version.
- [ ] Tag không bị dùng như cơ chế bảo mật.
- [ ] GroupedOpenApi được dùng khi cần document riêng hoặc lọc path.
- [ ] Multi-tag không làm taxonomy bị lạm dụng.
- [ ] Thứ tự UI được cấu hình bằng tags-sorter/operations-sorter có chủ đích.
- [ ] Đã kiểm tra OpenAPI JSON sau khi sinh.
- [ ] Đã kiểm tra root tags và operation tags.
- [ ] Đã test từng GroupedOpenApi nếu có.
- [ ] Đã đánh giá ảnh hưởng tag rename tới API portal và SDK generator.

## 37. Nguồn tra cứu

- [OpenAPI Specification – Tags Object](https://spec.openapis.org/oas/latest.html#tag-object)
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger Core – OpenAPI 3 Annotations](https://github.com/swagger-api/swagger-core/wiki/Annotations)

Tags là taxonomy điều hướng operation bên trong một OpenAPI document. Dùng @Tag để mô tả nhóm ở controller hoặc document, @Operation(tags = ...) để gán operation vào một hay nhiều nhóm, và GroupedOpenApi khi cần tạo document riêng. Giữ tên tag ổn định vì API portal và SDK generator có thể dùng chúng để tổ chức nội dung; luôn kiểm tra cả root tags, operation tags và kết quả hiển thị sau khi sinh tài liệu.
