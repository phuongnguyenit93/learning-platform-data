# Output payload metadata

Trong Spring HATEOAS, affordance mô tả một thao tác mà client có thể thực hiện trên một tài nguyên: thao tác dùng HTTP method nào, gửi dữ liệu đầu vào gì, có tham số truy vấn nào và có thể nhận về kiểu dữ liệu nào. Output payload metadata là phần mô tả kiểu payload mà thao tác dự kiến trả về.

Ví dụ, một link đến đơn hàng có thể công bố thao tác cập nhật bằng PUT. Affordance của thao tác đó có thể mô tả request body là `UpdateOrderRequest` và response body là `OrderRepresentation`. Client hoặc một media type có hỗ trợ affordance có thể dùng metadata đầu ra để hiểu cấu trúc kết quả dự kiến.

Spring HATEOAS cho phép khai báo output metadata khi tạo affordance thủ công bằng `withOutput(...)`. Nếu affordance được suy ra từ một phương thức Spring MVC, thư viện có thể phân tích kiểu trả về của phương thức để thu thập metadata. Bài học này tập trung vào ý nghĩa, cách khai báo, cách đọc và kiểm thử output payload metadata, đồng thời phân biệt nó với dữ liệu response thực tế và metadata của request.

Sau bài học, bạn có thể:

- Giải thích output payload metadata trong mô hình affordance.
- Phân biệt metadata đầu ra với metadata đầu vào và query parameter.
- Khai báo kiểu response bằng `withOutput(Class<?>)`.
- Dùng `ResolvableType` khi payload đầu ra có generic type.
- Kết hợp `withInput(...)` và `withOutput(...)` khi request và response có kiểu khác nhau.
- Dùng `withInputAndOutput(...)` khi hai phía có cùng kiểu payload.
- Hiểu `AffordanceModel.PayloadMetadata` và `PropertyMetadata`.
- Đọc output metadata từ affordance model theo media type.
- Nhận biết giới hạn của việc biểu diễn output metadata trong HAL-FORMS.
- Kiểm thử sự nhất quán giữa metadata đã công bố và response thật.

## 1. Affordance mô tả cả thao tác và payload

Một link thông thường chủ yếu cho biết URI đích và quan hệ của tài nguyên đích với tài nguyên hiện tại. Ví dụ:

~~~java
Link self = Link.of("/orders/42").withSelfRel();
~~~

Client biết URI của đơn hàng. Nhưng chỉ từ link này, client chưa biết:

- Có thể gửi PUT đến URI này hay không.
- Request body cần có cấu trúc nào.
- Thao tác có nhận query parameter nào không.
- Response dự kiến chứa kiểu dữ liệu nào.

Affordance bổ sung mô tả về khả năng thao tác gắn với link. Spring HATEOAS lưu thông tin chung như HTTP method, link đích, input metadata, query parameters và output metadata. Các media type có hỗ trợ affordance sẽ chuyển thông tin chung này thành cách biểu diễn phù hợp.

Một affordance có thể được hiểu qua các thành phần:

| Thành phần | Mô tả |
|---|---|
| Target link | URI mà thao tác hướng đến |
| HTTP method | GET, POST, PUT, PATCH, DELETE... |
| Input metadata | Kiểu payload mà client gửi |
| Query parameters | Các tham số truy vấn của thao tác |
| Output metadata | Kiểu payload mà thao tác dự kiến trả về |
| Name | Tên thao tác, có thể được khai báo rõ ràng |

Output payload metadata là trọng tâm của bài học. Nó mô tả kết quả của thao tác để client và media type có thêm thông tin về response dự kiến.

## 2. Phân biệt input và output payload metadata

Input và output đều mô tả payload, nhưng nằm ở hai hướng khác nhau của HTTP exchange.

Giả sử API có thao tác cập nhật đơn hàng:

~~~java
@PutMapping("/orders/{id}")
public OrderRepresentation update(
        @RequestBody UpdateOrderRequest request,
        @PathVariable UUID id) {
    // ...
}
~~~

Client gửi một `UpdateOrderRequest` và server trả về `OrderRepresentation`.

| Metadata | Hướng dữ liệu | Ví dụ |
|---|---|---|
| Input payload metadata | Client gửi đến server | `UpdateOrderRequest` |
| Output payload metadata | Server trả về client | `OrderRepresentation` |

Không nên dùng cùng một kiểu cho input và output chỉ vì chúng có một số trường giống nhau. Request có thể chứa các trường cho phép chỉnh sửa; response có thể chứa ID, trạng thái, liên kết và những trường chỉ đọc.

Ví dụ:

~~~java
public record UpdateOrderRequest(
    String shippingAddress,
    String note
) {}

public record OrderRepresentation(
    UUID id,
    String status,
    String shippingAddress,
    BigDecimal total
) {}
~~~

Hai kiểu dữ liệu này có mục đích khác nhau. Request chỉ chứa những thông tin client được phép gửi để cập nhật. Response mô tả kết quả mà server trả về.

### 2.1. Output metadata không phải response body

Cần phân biệt ba khái niệm:

- **Output payload:** dữ liệu response thực tế được server serialize và gửi về.
- **Output payload metadata:** mô tả kiểu dữ liệu và các thuộc tính của payload đầu ra trong affordance.
- **HTTP response metadata:** status code, header, content type và các thông tin giao thức khác.

Ví dụ, response thực tế có thể là:

~~~json
{
  "id": "42",
  "status": "CONFIRMED",
  "shippingAddress": "12 Nguyễn Huệ",
  "total": 1250000
}
~~~

Output metadata có thể khai báo kiểu `OrderRepresentation.class`. Nó không chứa sẵn giá trị ID, trạng thái hoặc tổng tiền của đơn hàng cụ thể. Nó cũng không tự tạo response body, không thay thế logic controller và không xác thực dữ liệu trả về.

### 2.2. Output metadata không phải input form

Một biểu mẫu cập nhật cần mô tả những trường client có thể gửi. Đó là trách nhiệm của input metadata. Output metadata mô tả kiểu kết quả của thao tác.

Nếu request có `UpdateOrderRequest` và response có `OrderRepresentation`, cần khai báo riêng hai kiểu:

~~~java
.withInput(UpdateOrderRequest.class)
.withOutput(OrderRepresentation.class)
~~~

Chỉ dùng `withInputAndOutput(...)` khi cùng một kiểu payload thực sự được dùng cho cả hai phía.

### 2.3. Thao tác không có response body

Một số endpoint trả về `204 No Content`, chẳng hạn thao tác xóa hoặc cập nhật không trả representation. Khi đó không có output payload để mô tả. Có thể bỏ qua `withOutput(...)` thay vì khai báo một DTO giả chỉ để lấp metadata.

~~~java
Link delete = Affordances.of(Link.of("/orders/42"))
    .afford(HttpMethod.DELETE)
    .withName("deleteOrder")
    .toLink();
~~~

Status code và header của response vẫn thuộc hợp đồng HTTP. Việc không khai báo output model không có nghĩa endpoint không trả status hoặc header.

## 3. Khai báo output bằng withOutput(Class)

API chính để khai báo output model là:

~~~java
ConfigurableAffordance withOutput(Class<?> type)
~~~

Phương thức nhận kiểu Java của payload đầu ra và trả về một `ConfigurableAffordance` để tiếp tục cấu hình. Ví dụ:

~~~java
Link orderLink = Link.of("/orders/42").withSelfRel();

Link enriched = Affordances.of(orderLink)
    .afford(HttpMethod.GET)
    .withOutput(OrderRepresentation.class)
    .withName("getOrder")
    .toLink();
~~~

Giải thích:

1. `Affordances.of(orderLink)` bắt đầu xây dựng affordance dựa trên link có sẵn.
2. `afford(HttpMethod.GET)` khai báo thao tác GET.
3. `withOutput(OrderRepresentation.class)` khai báo kiểu payload dự kiến trả về.
4. `withName("getOrder")` đặt tên affordance rõ ràng.
5. `toLink()` tạo một link mang affordance đã cấu hình.

Link vẫn trỏ đến cùng URI. Affordance bổ sung thông tin về thao tác GET và output model.

Các import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.hateoas.mediatype.ConfigurableAffordance;
import org.springframework.http.HttpMethod;
~~~

### 3.1. Output type nên là kiểu representation công khai

Khi chọn output type, nên dùng kiểu mà API thực sự công bố. Ví dụ:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Khai báo:

~~~java
.withOutput(OrderRepresentation.class)
~~~

Không nên tự động dùng JPA entity hoặc aggregate nội bộ làm output model nếu API thực tế chỉ trả DTO. Output metadata là một phần mô tả hợp đồng công khai; khai báo kiểu nội bộ có thể khiến client hiểu sai cấu trúc response và vô tình để lộ chi tiết triển khai.

### 3.2. Đặt tên affordance

`withName(...)` đặt tên cho thao tác. Tên này giúp media type có thể nhận diện riêng các affordance cùng gắn với một link.

~~~java
Link updateLink = Affordances.of(Link.of("/orders/42"))
    .afford(HttpMethod.PUT)
    .withInput(UpdateOrderRequest.class)
    .withOutput(OrderRepresentation.class)
    .withName("updateOrder")
    .toLink();
~~~

Tên thao tác không thay thế relation của link. Relation mô tả mối quan hệ giữa tài nguyên hiện tại và tài nguyên đích; tên affordance nhận diện một thao tác cụ thể được hỗ trợ tại target.

## 4. Tạo affordance có input và output khác nhau

Trong nhiều API, request body và response body có cấu trúc khác nhau. Hãy khai báo chúng độc lập.

Ví dụ endpoint tạo đơn hàng:

~~~java
public record CreateOrderRequest(
    UUID customerId,
    List<CreateOrderLine> lines
) {}

public record CreateOrderLine(
    UUID productId,
    int quantity
) {}

public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Các import cho DTO:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
~~~

Affordance POST:

~~~java
Link orders = Link.of("/orders").withRel("orders");

Link createOrder = Affordances.of(orders)
    .afford(HttpMethod.POST)
    .withInput(CreateOrderRequest.class)
    .withOutput(OrderRepresentation.class)
    .withName("createOrder")
    .toLink();
~~~

Client có thể biết rằng thao tác tạo đơn hàng nhận payload theo `CreateOrderRequest` và dự kiến trả về `OrderRepresentation`.

Nếu chỉ khai báo `withInput(...)`, affordance có thông tin về request nhưng không có kiểu output được khai báo thủ công. Nếu thao tác có response body quan trọng đối với client, hãy khai báo output rõ ràng.

### 4.1. Cùng một target có nhiều affordance

Một collection endpoint có thể hỗ trợ POST để tạo đơn hàng và GET để tìm kiếm đơn hàng. Cả hai thao tác có thể gắn với cùng link collection:

~~~java
Link orders = Link.of("/orders").withRel("orders");

Link ordersWithOperations = Affordances.of(orders)
    .afford(HttpMethod.POST)
    .withInput(CreateOrderRequest.class)
    .withOutput(OrderRepresentation.class)
    .withName("createOrder")
    .andAfford(HttpMethod.GET)
    .withOutput(OrderSearchResult.class)
    .addParameters(
        QueryParameter.optional("status"),
        QueryParameter.optional("customerId")
    )
    .withName("searchOrders")
    .toLink();
~~~

Trong ví dụ:

- POST nhận `CreateOrderRequest` và trả `OrderRepresentation`.
- GET không có request body, trả `OrderSearchResult`.
- GET nhận các query parameter tùy chọn `status` và `customerId`.
- Mỗi affordance có tên riêng.

`andAfford(HttpMethod.GET)` kết thúc cấu hình affordance trước đó và bắt đầu cấu hình một thao tác mới. Các lời gọi `withOutput(...)` sau đó áp dụng cho affordance hiện tại.

Các import bổ sung:

~~~java
import org.springframework.hateoas.QueryParameter;
~~~

Không nên đưa query parameter vào output metadata. Query parameter là một phần của cách client gọi thao tác; output metadata mô tả kiểu dữ liệu server trả về.

## 5. withInputAndOutput khi hai phía dùng cùng kiểu

Nếu cùng một kiểu được dùng cho request và response, Spring HATEOAS cung cấp:

~~~java
withInputAndOutput(Class<?> type)
~~~

Ví dụ:

~~~java
Link update = Affordances.of(Link.of("/profiles/42"))
    .afford(HttpMethod.PUT)
    .withInputAndOutput(ProfileDocument.class)
    .withName("replaceProfile")
    .toLink();
~~~

Cách viết này tương đương việc khai báo cùng một kiểu cho hai phía:

~~~java
.withInput(ProfileDocument.class)
.withOutput(ProfileDocument.class)
~~~

Chỉ dùng cách rút gọn nếu hợp đồng thực sự giống nhau. Trong ứng dụng thực tế, request thường không chứa các trường do server quản lý như ID, thời điểm tạo, trạng thái phê duyệt hoặc liên kết hypermedia. Khi đó, nên dùng DTO riêng và khai báo input/output độc lập.

## 6. Output payload có generic type với ResolvableType

`Class<?>` đủ dùng cho một kiểu cụ thể, nhưng không thể giữ đầy đủ thông tin generic trong các trường hợp như:

- `List<OrderSummary>`.
- `Page<OrderRepresentation>`.
- `ApiResult<OrderRepresentation>`.
- `Map<String, OrderSummary>`.

Java type erasure khiến kiểu phần tử generic có thể không còn được thể hiện đầy đủ nếu chỉ truyền raw class. Spring HATEOAS hỗ trợ overload:

~~~java
withOutput(ResolvableType type)
~~~

Ví dụ output là danh sách đơn hàng:

~~~java
ResolvableType outputType = ResolvableType.forClassWithGenerics(
    List.class,
    OrderSummary.class
);

Link search = Affordances.of(Link.of("/orders"))
    .afford(HttpMethod.GET)
    .withOutput(outputType)
    .withName("searchOrders")
    .toLink();
~~~

Khi đó metadata giữ được thông tin rằng payload đầu ra là danh sách các `OrderSummary`.

Import:

~~~java
import java.util.List;

import org.springframework.core.ResolvableType;
~~~

### 6.1. Output kiểu wrapper

Giả sử API trả về:

~~~java
public record ApiResult<T>(
    boolean success,
    T data,
    String message
) {}
~~~

Nếu response là `ApiResult<OrderRepresentation>`, có thể mô tả:

~~~java
ResolvableType outputType = ResolvableType.forClassWithGenerics(
    ApiResult.class,
    OrderRepresentation.class
);

Link getOrder = Affordances.of(Link.of("/orders/42"))
    .afford(HttpMethod.GET)
    .withOutput(outputType)
    .toLink();
~~~

Metadata generic chính xác giúp media type hoặc thành phần tiêu thụ affordance có thêm thông tin về kiểu payload. Nếu chỉ truyền `ApiResult.class`, kiểu `T` có thể không được xác định.

### 6.2. Dùng kiểu generic đúng với response thực tế

Không khai báo `List<OrderSummary>` nếu controller thực tế trả về một object `OrderSearchResult` có thêm metadata phân trang, filter hoặc tổng số kết quả.

Output metadata phải phản ánh hợp đồng response mà client thực sự nhận được. Nếu controller trả về `PagedModel<EntityModel<OrderRepresentation>>`, cần xác định rõ kiểu representation công khai mà ứng dụng muốn mô tả và cách media type xử lý wrapper đó.

## 7. PayloadMetadata và PropertyMetadata

Ngoài overload nhận `Class<?>` và `ResolvableType`, `ConfigurableAffordance` còn có:

~~~java
withOutput(AffordanceModel.PayloadMetadata metadata)
~~~

`AffordanceModel.PayloadMetadata` là abstraction mô tả payload. API của nó cung cấp hai phần quan trọng:

- `getType()` trả về kiểu payload nếu xác định được.
- `stream()` trả về các `PropertyMetadata` của các thuộc tính có trong payload.

Overload nhận `PayloadMetadata` phù hợp với trường hợp ứng dụng hoặc một integration đã có metadata payload tùy chỉnh. Phần lớn code ứng dụng có thể dùng `Class<?>` hoặc `ResolvableType`; không cần tự triển khai SPI metadata nếu không có yêu cầu đặc biệt từ media type.

Ví dụ về thông tin có thể đọc từ payload metadata:

| API | Ý nghĩa |
|---|---|
| `getType()` | Kiểu payload |
| `stream()` | Luồng metadata của các thuộc tính |
| `PropertyMetadata.getName()` | Tên thuộc tính |
| `PropertyMetadata.getType()` | Kiểu của thuộc tính |
| `PropertyMetadata.isReadOnly()` | Thuộc tính chỉ đọc |
| `PropertyMetadata.isRequired()` | Thuộc tính được yêu cầu hoặc luôn hiện diện theo ngữ cảnh metadata |
| `PropertyMetadata.getPattern()` | Biểu thức chính quy nếu có |
| `PropertyMetadata.getMin()/getMax()` | Giới hạn số |
| `PropertyMetadata.getMinLength()/getMaxLength()` | Giới hạn độ dài |

`PropertyMetadata` là mô tả cấu trúc của thuộc tính, không phải giá trị của thuộc tính trong một response cụ thể.

### 7.1. Đọc output metadata từ AffordanceModel

Một `Link` có thể mang nhiều affordance. Mỗi affordance có các model tương ứng với media type được hỗ trợ.

Ví dụ, lấy output metadata từ model HAL-FORMS:

~~~java
Affordance affordance = link.getAffordances().get(0);

AffordanceModel model =
    affordance.getAffordanceModel(MediaTypes.HAL_FORMS_JSON);

if (model != null) {
    AffordanceModel.PayloadMetadata output = model.getOutput();

    Class<?> outputType = output.getType();

    output.stream().forEach(property -> {
        String name = property.getName();
        ResolvableType type = property.getType();
        boolean readOnly = property.isReadOnly();
    });
}
~~~

Ý nghĩa:

1. `link.getAffordances()` lấy danh sách affordance được gắn trên link.
2. `getAffordanceModel(MediaTypes.HAL_FORMS_JSON)` lấy model dành cho media type được chọn.
3. `getOutput()` trả về output payload metadata.
4. `getType()` lấy kiểu payload.
5. `stream()` cho phép duyệt metadata từng thuộc tính.

`getAffordanceModel(...)` có thể trả về `null` nếu affordance không có model cho media type đó. Không nên giả định mọi media type đều hỗ trợ mọi affordance.

Các import chính:

~~~java
import org.springframework.hateoas.Affordance;
import org.springframework.hateoas.AffordanceModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.core.ResolvableType;
~~~

### 7.2. Output metadata và thuộc tính chỉ đọc

Giả sử response có:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

`id` và `total` thường do server quản lý, trong khi client có thể chỉ được phép thay đổi một số trường. Metadata thuộc tính có thể mô tả tính chất chỉ đọc hoặc kiểu dữ liệu để media type diễn giải.

Tuy nhiên, ý nghĩa của một thuộc tính phụ thuộc vào vai trò input hay output:

- Trong input model, `required` có thể cho biết client cần gửi thuộc tính đó hay không.
- Trong output model, thuộc tính có thể là dữ liệu luôn hiện diện trong representation.
- `readOnly` cho biết thuộc tính không nên được thao tác trong request làm thay đổi trạng thái.

Không được dùng metadata này như cơ chế bảo vệ dữ liệu. Server vẫn phải kiểm tra request, quyền truy cập và quy tắc nghiệp vụ.

## 8. Tự động suy ra output metadata từ controller method

Khi affordance được tạo từ phương thức Spring MVC, Spring HATEOAS có thể phân tích phương thức để thu thập thông tin request body và response type.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        // ...
    }

    @PutMapping("/{id}")
    public EntityModel<OrderRepresentation> update(
            @RequestBody UpdateOrderRequest request,
            @PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Các import liên quan đến controller:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Tạo link self có affordance PUT:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel()
 .andAffordance(
    afford(methodOn(OrderController.class).update(null, orderId))
 );
~~~

Spring HATEOAS phân tích phương thức `update(...)` để thu thập:

- HTTP method PUT từ `@PutMapping`.
- Input type từ tham số `@RequestBody UpdateOrderRequest`.
- Output type từ kiểu trả về `EntityModel<OrderRepresentation>`.
- Mapping và path variable từ controller.

Lời gọi `methodOn(...).update(null, orderId)` chỉ mô tả phương thức và tham số để xây dựng affordance. Nó không thực thi nghiệp vụ cập nhật.

Các import tĩnh:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 8.1. Khi nào cần khai báo withOutput thủ công?

Tự động suy ra từ controller method phù hợp khi:

- Phương thức có mapping Spring MVC rõ ràng.
- Kiểu trả về được khai báo cụ thể.
- Input và output được thể hiện qua chữ ký phương thức.
- Affordance gắn trực tiếp với endpoint controller.

Khai báo thủ công bằng `withOutput(...)` phù hợp khi:

- Tạo affordance không dựa trên controller method.
- URI hoặc thao tác được tạo từ cấu hình.
- Kiểu response cần mô tả khác với kiểu có thể suy ra.
- Payload generic cần được chỉ rõ bằng `ResolvableType`.
- Ứng dụng đang tích hợp custom media type hoặc metadata provider.

Nếu phương thức controller trả về kiểu quá chung như `Object` hoặc `ResponseEntity<?>`, metadata suy ra có thể không đủ cụ thể. Hãy khai báo kiểu trả về rõ ràng hoặc cung cấp output metadata tường minh.

## 9. Output metadata được media type sử dụng như thế nào?

`Affordance` là mô hình chung, không phải một định dạng JSON cố định. Spring HATEOAS cung cấp affordance model theo từng media type. `AffordanceModelFactory` chuyển thông tin cấu hình chung thành model mà media type cụ thể có thể biểu diễn.

Điều đó có nghĩa:

- `withOutput(...)` lưu kiểu payload đầu ra vào affordance.
- `AffordanceModel.getOutput()` cung cấp metadata đầu ra trong model tương ứng.
- Media type quyết định có hiển thị thông tin đó hay không và hiển thị theo cấu trúc nào.

Không nên giả định mọi media type đều serialize output metadata thành cùng một trường JSON.

### 9.1. HAL và HAL-FORMS

HAL cơ bản tập trung vào link và embedded resource. Một link HAL thông thường không tự mô tả đầy đủ request body hoặc response schema của mọi thao tác.

HAL-FORMS bổ sung khả năng mô tả template thao tác. Template có thể chứa:

- HTTP method.
- Target URI.
- Content type đầu vào.
- Title.
- Danh sách properties mà client gửi.

Các properties của template chủ yếu được xây dựng từ input payload metadata. Vì vậy, output metadata không phải danh sách trường để client điền vào form.

Ví dụ template HAL-FORMS:

~~~json
{
  "_templates": {
    "updateOrder": {
      "method": "put",
      "properties": [
        {
          "name": "shippingAddress",
          "required": true
        },
        {
          "name": "note",
          "required": false
        }
      ]
    }
  }
}
~~~

Các thuộc tính trong template mô tả request mà client gửi. Việc khai báo `withOutput(OrderRepresentation.class)` không biến các trường response thành input properties của biểu mẫu.

Output metadata vẫn là một phần của affordance model chung. Một media type hoặc integration riêng có thể dùng nó để mô tả response. Nếu client cần một schema response công khai và có thể kiểm tra độc lập, hãy cung cấp tài liệu hợp đồng phù hợp như JSON Schema hoặc tài liệu API tương ứng.

### 9.2. Output metadata không thay thế produces và Accept

`withOutput(...)` khai báo kiểu mô hình payload đầu ra. Nó không khai báo media type HTTP mà server sẽ gửi.

Phân biệt:

| Cơ chế | Vai trò |
|---|---|
| `withOutput(OrderRepresentation.class)` | Mô tả kiểu payload đầu ra |
| `@RequestMapping(produces = ...)` | Khai báo media type endpoint có thể trả về |
| `Accept` | Client yêu cầu media type response |
| `withInputMediaType(...)` | Khai báo media type của payload đầu vào |
| `Content-Type` response | Media type thực tế của response |

Không có phương thức `withOutputMediaType(...)` trong `ConfigurableAffordance`. Nếu cần kiểm soát media type response, hãy cấu hình content negotiation và mapping HTTP tương ứng.

## 10. Không nhầm output metadata với validation

Output metadata mô tả payload cho affordance. Nó không tự động:

- Tạo response body.
- Chuyển đổi domain object thành DTO.
- Kiểm tra response thực tế có đúng schema hay không.
- Thay thế Bean Validation.
- Cấp quyền truy cập các trường dữ liệu.
- Đảm bảo endpoint luôn trả đúng status code.
- Công bố mọi HTTP header của response.

Ví dụ, nếu khai báo:

~~~java
.withOutput(OrderRepresentation.class)
~~~

nhưng controller thực tế trả về `PaymentRepresentation`, metadata đã công bố không còn khớp với hợp đồng thực tế.

Để tránh sai lệch:

1. Dùng DTO response làm nguồn khai báo output.
2. Tránh raw type hoặc wildcard nếu có thể khai báo kiểu cụ thể.
3. Cập nhật output metadata khi response contract thay đổi.
4. Kiểm thử cả metadata affordance và response body thực tế.
5. Kiểm tra quyền trước khi đưa trường dữ liệu vào representation.

## 11. Kiểm thử output payload metadata

Kiểm thử cần xác nhận output metadata được gắn đúng với affordance và phản ánh đúng kiểu response dự kiến.

Ví dụ tạo affordance thủ công:

~~~java
@Test
void registersOutputPayloadType() {
    Link link = Affordances.of(Link.of("/orders/42"))
        .afford(HttpMethod.GET)
        .withOutput(OrderRepresentation.class)
        .withName("getOrder")
        .toLink();

    assertThat(link.getAffordances()).hasSize(1);

    Affordance affordance = link.getAffordances().get(0);
    AffordanceModel model =
        affordance.getRequiredAffordanceModel(MediaTypes.HAL_FORMS_JSON);

    assertThat(model.getOutput().getType())
        .isEqualTo(OrderRepresentation.class);
}
~~~

Ví dụ này giả định ứng dụng đã đăng ký hỗ trợ HAL-FORMS để có affordance model tương ứng.

Cấu hình tối thiểu cho test context dùng Spring MVC:

~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class TestHypermediaConfiguration {
}
~~~

Với Spring Boot, có thể nạp cấu hình này vào test context bằng `@Import(TestHypermediaConfiguration.class)` hoặc dùng cấu hình hypermedia hiện có của ứng dụng.

Các import thường dùng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Affordance;
import org.springframework.hateoas.AffordanceModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.http.HttpMethod;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;
~~~

### 11.1. Kiểm thử generic output type

Nếu output là danh sách:

~~~java
@Test
void preservesGenericOutputType() {
    ResolvableType outputType = ResolvableType.forClassWithGenerics(
        List.class,
        OrderSummary.class
    );

    Link link = Affordances.of(Link.of("/orders"))
        .afford(HttpMethod.GET)
        .withOutput(outputType)
        .toLink();

    AffordanceModel model = link.getAffordances().get(0)
        .getRequiredAffordanceModel(MediaTypes.HAL_FORMS_JSON);

    assertThat(model.getOutput().getType()).isEqualTo(List.class);
}
~~~

Ví dụ này kiểm tra raw class của payload. Với ứng dụng cần xác nhận đầy đủ generic argument, nên kiểm tra thêm metadata hoặc contract test của media type đang sử dụng. Không nên chỉ kiểm tra `List.class` rồi kết luận rằng thông tin kiểu phần tử đã được giữ chính xác.

### 11.2. Kiểm thử output metadata và response body riêng biệt

Một contract test qua MockMvc có thể xác nhận response thật:

~~~java
mvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$.status").value("CONFIRMED"))
    .andExpect(jsonPath("$.total").value(1250000));
~~~

Kiểm thử affordance xác nhận mô tả thao tác. Kiểm thử HTTP xác nhận response thực tế. Hai kiểm thử bảo vệ hai phần khác nhau của hợp đồng API.

Nếu output type được suy ra từ controller method, nên có kiểm thử xác nhận phương thức controller vẫn trả về đúng kiểu representation sau khi refactor.

## 12. Lỗi thường gặp khi khai báo output metadata

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng input type làm output type dù hai bên khác nhau | Client hiểu sai response | Khai báo riêng `withInput` và `withOutput` |
| Không khai báo output cho thao tác có response body | Affordance thiếu thông tin về kết quả | Dùng `withOutput(...)` hoặc để controller method cung cấp kiểu rõ ràng |
| Dùng raw generic type | Mất thông tin kiểu phần tử | Dùng `ResolvableType` |
| Dùng JPA entity làm output model | Metadata không khớp DTO công khai | Dùng response representation |
| Coi output metadata là response body | Mong đợi metadata tự sinh dữ liệu | Controller vẫn phải trả payload thực tế |
| Coi output metadata là schema validation | Dữ liệu sai vẫn có thể được trả về | Dùng validation và contract test |
| Dùng `withInputAndOutput` khi hai kiểu khác nhau | Hợp đồng request/response sai | Khai báo hai phía độc lập |
| Nghĩ HAL-FORMS output metadata là form field | Client có thể gửi nhầm trường | Phân biệt input properties và output model |
| Coi `withOutput` khai báo Content-Type | Sai content negotiation | Dùng produces, Accept và cấu hình converter |
| Không cập nhật metadata khi đổi response DTO | Affordance mô tả sai hợp đồng | Đồng bộ code và kiểm thử |

## 13. Quy trình thiết kế output payload metadata

Khi xây dựng affordance có response body, hãy thực hiện theo trình tự:

1. Xác định thao tác và HTTP method.
2. Xác định response body thực tế của endpoint.
3. Chọn DTO hoặc representation công khai làm output type.
4. Nếu affordance được suy ra từ controller method, khai báo kiểu trả về cụ thể.
5. Nếu tạo thủ công, dùng `withOutput(Class<?>)`.
6. Nếu payload có generic type, dùng `withOutput(ResolvableType)`.
7. Nếu input và output khác nhau, khai báo riêng `withInput(...)` và `withOutput(...)`.
8. Chỉ dùng `withInputAndOutput(...)` khi cùng một kiểu thực sự được dùng cho cả hai phía.
9. Xác định media type cần hỗ trợ và cách nó biểu diễn affordance.
10. Kiểm thử output metadata và response body như hai phần riêng của hợp đồng.
11. Cập nhật metadata và contract test khi response representation thay đổi.

## 14. Kết luận

Output payload metadata mô tả kiểu dữ liệu mà một affordance dự kiến trả về. Spring HATEOAS cung cấp `withOutput(Class<?>)`, `withOutput(ResolvableType)` và `withOutput(PayloadMetadata)` để khai báo thông tin đó. Khi request và response có kiểu khác nhau, hãy khai báo input và output riêng; chỉ dùng `withInputAndOutput(...)` khi cùng một kiểu được sử dụng ở cả hai phía.

`AffordanceModel.PayloadMetadata` cung cấp kiểu payload và luồng metadata thuộc tính để media type có thể diễn giải. `AffordanceModel.getOutput()` cho phép truy cập thông tin đầu ra của model tương ứng. Output metadata không phải response body, không tự xác thực dữ liệu và không thay thế content negotiation. Khi metadata phản ánh đúng DTO công khai, được kiểm thử cùng response thật và được cập nhật theo thay đổi hợp đồng, affordance giúp client hiểu rõ hơn kết quả của thao tác mà API cung cấp.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances): tạo affordance từ controller method và tạo affordance thủ công.
- [Spring HATEOAS API — ConfigurableAffordance](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/ConfigurableAffordance.html): các overload `withOutput`, `withInput`, `withInputAndOutput` và cấu hình affordance.
- [Spring HATEOAS API — AffordanceModel.PayloadMetadata](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/AffordanceModel.PayloadMetadata.html): kiểu payload và luồng metadata thuộc tính.
- [Spring HATEOAS API — AffordanceModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/AffordanceModel.html): `getOutput()` và các thành phần của affordance model.
- [Spring HATEOAS Reference — HAL-FORMS metadata](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms.metadata): cách HAL-FORMS mô tả template và các input properties.

