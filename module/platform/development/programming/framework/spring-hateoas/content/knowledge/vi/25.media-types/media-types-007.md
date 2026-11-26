# Media type tùy biến

Media type cho biết định dạng và ngữ nghĩa của dữ liệu được gửi trong HTTP request hoặc response. Trong REST API, ngoài các media type phổ biến như `application/json`, `application/hal+json` và `application/prs.hal-forms+json`, một tổ chức có thể công bố media type riêng để mô tả hợp đồng dữ liệu của mình. Ví dụ `application/vnd.acme.order+json` là một vendor-specific media type cho representation đơn hàng của Acme.

Với Spring HATEOAS, việc dùng một media type tùy biến cần được thiết kế ở cả hai lớp: khai báo content negotiation trong Spring MVC/WebFlux và cung cấp cơ chế serialize/deserialize phù hợp. Chỉ đổi chuỗi `produces` thành một media type mới không tự biến JSON thông thường thành hypermedia. Nếu representation chứa `EntityModel`, `CollectionModel`, link và affordance, converter cùng `ObjectMapper` phải hiểu cấu trúc Spring HATEOAS cần serialize.

## 1. Media type là gì?

Media type (trước đây thường gọi là MIME type) xác định định dạng và loại nội dung của một HTTP message. Cấu trúc cơ bản là:

```text
type/subtype; parameter=value
```

Ví dụ:

| Media type | Ý nghĩa |
| --- | --- |
| `application/json` | Dữ liệu JSON thông thường |
| `application/hal+json` | Representation hypermedia theo HAL, dùng JSON làm cú pháp |
| `application/prs.hal-forms+json` | Representation HAL-FORMS, có thể mô tả template thao tác |
| `application/vnd.acme.order+json` | Vendor-specific JSON representation do Acme định nghĩa |
| `application/vnd.acme.order.v2+json` | Một biến thể/version riêng của representation đơn hàng |

`type` thường là `application` đối với API. `subtype` xác định định dạng cụ thể. Phần hậu tố `+json` là structured syntax suffix cho biết nội dung dùng cú pháp JSON; nó không tự định nghĩa cấu trúc dữ liệu hoặc quy tắc hypermedia.

Do đó, `application/vnd.acme.order+json` và `application/hal+json` đều có thể chứa JSON, nhưng không có cùng ngữ nghĩa. Client chỉ có thể hiểu `_links`, `_embedded` hoặc template nếu hợp đồng media type quy định cấu trúc đó và client hỗ trợ nó.

## 2. Khi nào cần media type tùy biến?

Media type riêng có ích khi API cần công bố một representation có ngữ nghĩa hoặc quy tắc xử lý riêng:

- Một vendor muốn định danh định dạng dữ liệu do mình quản lý.
- Một API cần phân biệt representation nghiệp vụ với JSON tổng quát.
- Một hợp đồng cần phiên bản hoặc profile có ngữ nghĩa rõ ràng.
- Một định dạng hypermedia nội bộ mở rộng từ cấu trúc đã biết và có serializer/client tương ứng.
- Một nhóm API muốn content negotiation theo khả năng biểu diễn thay vì chỉ theo đường dẫn URL.

Không nên tạo media type mới chỉ để đổi tên `application/json`. Nếu representation không có ngữ nghĩa bổ sung, dùng media type chuẩn thường giúp client và công cụ tích hợp dễ tương thích hơn. Media type tùy biến tạo thêm trách nhiệm duy trì tài liệu, converter, client và kiểm thử tương thích.

## 3. Cú pháp vendor-specific media type

Một media type vendor-specific thường dùng cây đăng ký `vnd.` trong subtype:

```text
application/vnd.<vendor>.<format>+json
```

Ví dụ:

```text
application/vnd.acme.order+json
application/vnd.acme.order.v2+json
application/vnd.acme.inventory+json
```

Tên vendor và format cần ổn định, dễ hiểu và không phụ thuộc tên class Java. Không nên đặt tên theo package nội bộ hoặc tên implementation có thể thay đổi.

Có thể khai báo media type trong Java bằng `MediaType`:

```java
import org.springframework.http.MediaType;

public final class ApiMediaTypes {

    public static final MediaType ORDER_JSON =
            MediaType.parseMediaType("application/vnd.acme.order+json");

    public static final MediaType ORDER_V2_JSON =
            MediaType.parseMediaType("application/vnd.acme.order.v2+json");

    private ApiMediaTypes() {
    }
}
```

Đặt các hằng số ở một vị trí dùng chung giúp tránh gõ sai subtype giữa controller, cấu hình converter và test. Media type là một phần hợp đồng công khai nên thay đổi tên hoặc ý nghĩa cần được quản lý như một thay đổi API.

## 4. Content negotiation: Accept và Content-Type

HTTP dùng hai header quan trọng để thương lượng định dạng:

- `Accept` cho biết client muốn nhận response ở media type nào.
- `Content-Type` cho biết định dạng của request body mà client đang gửi.

Ví dụ client yêu cầu vendor media type:

```http
GET /orders/ORD-101 HTTP/1.1
Host: api.example.test
Accept: application/vnd.acme.order+json
```

Khi gửi request body theo media type tùy biến:

```http
PUT /orders/ORD-101 HTTP/1.1
Host: api.example.test
Content-Type: application/vnd.acme.order+json
Accept: application/vnd.acme.order+json

{
  "note": "Giao hàng sau 17 giờ"
}
```

Server dùng `Accept` để chọn representation response và dùng `Content-Type` để chọn converter đọc request body. Hai header phục vụ hai chiều khác nhau; không nên dùng thay thế cho nhau.

Nếu server không thể tạo bất kỳ representation nào phù hợp với `Accept`, nó có thể trả `406 Not Acceptable`. Nếu không có converter đọc được request body theo `Content-Type`, server thường trả `415 Unsupported Media Type`.

## 5. Khai báo media type trong mapping controller

Spring MVC cho phép giới hạn media type được chấp nhận hoặc trả về bằng `consumes` và `produces`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

public record UpdateOrderRequest(String note) {
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = "application/vnd.acme.order+json")
    EntityModel<OrderRepresentation> one(@PathVariable("id") UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PutMapping(
            value = "/{id}",
            consumes = "application/vnd.acme.order+json")
    ResponseEntity<Void> update(
            @PathVariable("id") UUID id,
            @RequestBody UpdateOrderRequest request) {
        orderService.update(id, request);
        return ResponseEntity.noContent().build();
    }
}
```

`produces` và `consumes` tham gia chọn handler theo content negotiation. Chúng không tự đăng ký một `HttpMessageConverter` mới. Nếu converter hiện có không hỗ trợ media type được yêu cầu hoặc không biết cách serialize `EntityModel`, request vẫn có thể thất bại dù mapping đã khai báo `produces`.

Ví dụ controller trên giả định `OrderService` và `OrderModelAssembler` được inject qua constructor. `UpdateOrderRequest` là request DTO rút gọn để minh họa kiểu dữ liệu được đọc từ body.

Trong ví dụ, endpoint GET trả `EntityModel` theo vendor media type, nên ứng dụng phải có converter và mapper biết cách serialize representation HATEOAS dưới media type đó. Endpoint PUT đọc request body theo vendor media type, nên cần converter hỗ trợ đọc kiểu `UpdateOrderRequest` với `Content-Type` tương ứng. Nếu API không có lý do để dùng vendor media type cho request body, có thể giữ request `application/json` và chỉ dùng media type riêng cho response.

## 6. Media type tùy biến và Spring HATEOAS

Spring HATEOAS cung cấp `HypermediaMappingInformation` để đăng ký thông tin mapping cho một hypermedia media type. Đây là extension point để framework biết media type nào được hỗ trợ và `ObjectMapper` nào dùng để serialize representation hypermedia.

Hãy phân biệt hai trường hợp. Nếu media type tùy biến chỉ mang một DTO JSON thông thường, một Jackson converter hỗ trợ media type đó có thể là đủ. Nếu response chứa `EntityModel`, `CollectionModel` hoặc affordance và muốn công bố chúng theo một định dạng hypermedia, cần serializer/mapper hiểu các kiểu Spring HATEOAS và hợp đồng của media type. `HypermediaMappingInformation` phục vụ trường hợp thứ hai.

Một cấu hình cơ bản có thể khai báo media type riêng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaMappingInformation;
import org.springframework.http.MediaType;

@Configuration
class AcmeOrderHypermediaConfiguration implements HypermediaMappingInformation {

    private final ObjectMapper objectMapper;

    AcmeOrderHypermediaConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public MediaType getMediaType() {
        return MediaType.parseMediaType("application/vnd.acme.order+json");
    }

    @Override
    public ObjectMapper getMediaTypeObjectMapper() {
        return objectMapper;
    }
}
```

Đoạn code thể hiện extension point và cách công bố media type. `ObjectMapper` trả về phải được cấu hình phù hợp với định dạng hypermedia mà API cam kết. Việc inject một mapper JSON bất kỳ không tự thêm quy tắc serialize link, embedded resource hoặc affordance. Với một định dạng dựa trên HAL, cần cấu hình các module, mixin và serializer Spring HATEOAS cần thiết; với định dạng hoàn toàn riêng, cần triển khai serializer/deserializer theo schema của định dạng đó.

Đảm bảo cấu hình hypermedia được kích hoạt và implementation `HypermediaMappingInformation` được Spring phát hiện trong application context. Spring Boot với starter HATEOAS thường tự cấu hình phần nền; với cấu hình Spring thuần, cần bật hypermedia support và đăng ký mapping/converter theo stack MVC hoặc WebFlux.

Các phương thức và cách đăng ký của SPI có thể thay đổi theo phiên bản Spring HATEOAS. Hãy đối chiếu chữ ký API với phiên bản dependency mà ứng dụng đang dùng và xác nhận converter được đăng ký trong MVC/WebFlux message conversion. Không sao chép cấu hình mapper HAL của phiên bản khác mà chưa kiểm tra tính tương thích.

## 7. Media type tùy biến không tự tạo một định dạng hypermedia mới

Đặt tên subtype là `application/vnd.acme.order+json` chỉ định danh media type. Nó không tự tạo ra các quy tắc như:

- Link được đặt ở thuộc tính `_links`.
- Tài nguyên liên quan được đặt trong `_embedded`.
- Tên relation được xác định như thế nào.
- URI template hoặc affordance được biểu diễn ra sao.
- Client phải gửi request tiếp theo như thế nào.

Nếu định dạng tùy biến muốn giữ cấu trúc HAL, hãy mô tả rõ nó là biến thể tương thích HAL, chỉ rõ các quy tắc nào được giữ nguyên và cung cấp serializer/client tương ứng. Nếu muốn dùng HAL chuẩn, nên trả `application/hal+json` thay vì tạo alias riêng không có khác biệt ngữ nghĩa.

Tương tự, nếu cần biểu diễn form và affordance theo chuẩn HAL-FORMS, hãy dùng `application/prs.hal-forms+json` và cấu hình client hỗ trợ media type đó. Không nên đổi tên HAL-FORMS sang vendor type nếu chưa xác định rõ khả năng tương thích và quy tắc chuyển đổi.

## 8. Kết hợp EntityModel và custom media type

Representation HATEOAS có thể được tạo độc lập với media type:

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    return EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel(),
            linkTo(methodOn(CustomerController.class)
                    .one(order.getCustomerId())).withRel("customer"));
}
```

Assembler xây dựng nội dung và link. Converter/mapper quyết định cách representation đó được serialize cho media type được thương lượng. Tách hai trách nhiệm giúp cùng một model có thể được biểu diễn theo các media type khác nhau nếu ứng dụng đã cấu hình serializer tương ứng.

Đoạn code là phần thân của assembler và giả định `Order`, `OrderRepresentation`, `OrderController` cùng `CustomerController` đã được khai báo trong ứng dụng.

Ví dụ, một client có thể yêu cầu HAL chuẩn, client khác yêu cầu vendor-specific representation. Dù cùng lấy dữ liệu từ assembler, cấu trúc response chỉ tương thích khi converter của từng media type thực hiện đúng hợp đồng đã công bố.

## 9. Versioning bằng media type

Một API có thể dùng media type để phân biệt phiên bản representation:

```text
application/vnd.acme.order.v1+json
application/vnd.acme.order.v2+json
```

Hoặc dùng media type parameter nếu hợp đồng chọn cách đó:

```text
application/vnd.acme.order+json;version=2
```

Versioning qua media type cho phép cùng một URI trả về representation khác nhau theo `Accept`. Điều này có thể hữu ích khi URI định danh resource ổn định nhưng schema representation thay đổi.

Tuy nhiên, versioning bằng media type đòi hỏi server duy trì các converter, mapping hoặc logic chọn representation tương ứng. Client cũng phải gửi đúng `Accept`. Nếu thay đổi chỉ mang tính bổ sung tương thích ngược, không nhất thiết phải tạo version mới. Chỉ tăng version khi ngữ nghĩa hoặc cấu trúc thay đổi đến mức client cũ không thể xử lý an toàn.

Không nên đồng thời version bằng path, query và media type nếu không có quy tắc ưu tiên rõ ràng. Chọn một chiến lược chính, tài liệu hóa cách chọn phiên bản và giữ hành vi nhất quán.

## 10. Caching và Vary: Accept

Nếu cùng một URI trả response khác nhau tùy `Accept`, cache cần biết representation được chọn phụ thuộc header này. Response nên có `Vary: Accept` để cache phân biệt các biến thể:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.acme.order+json
Vary: Accept
```

Nếu thiếu `Vary: Accept`, một shared cache có thể trả representation HAL cho client yêu cầu vendor type hoặc ngược lại. Cách cấu hình header phụ thuộc hạ tầng cache và framework; hãy kiểm tra response thực tế khi triển khai content negotiation.

## 11. Kiểm thử content negotiation

Với Spring MVC, `MockMvc` có thể kiểm tra media type được chọn theo `Accept`:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    private final UUID orderId = UUID.fromString(
            "a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Test
    void returnsVendorMediaTypeWhenRequested() throws Exception {
        mockMvc.perform(get("/orders/{id}", orderId)
                        .accept("application/vnd.acme.order+json"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/vnd.acme.order+json"));
    }
}
```

Test cần chuẩn bị một order có ID tương ứng trước khi gọi endpoint. Test này chỉ pass khi mapping chấp nhận media type và converter phù hợp thực sự serialize response. Nếu mapping có `produces` nhưng converter không hỗ trợ media type, test có thể thất bại với lỗi content negotiation hoặc không tìm thấy converter.

Nên kiểm tra thêm:

- `Accept: application/hal+json` trả đúng HAL nếu endpoint hỗ trợ.
- `Accept` chứa media type không hỗ trợ dẫn đến `406 Not Acceptable` theo cấu hình.
- Request body có `Content-Type` được hỗ trợ được đọc đúng.
- Request body có `Content-Type` không được hỗ trợ dẫn đến `415 Unsupported Media Type`.
- Response `Content-Type` đúng với media type đã thương lượng.
- `EntityModel` được serialize đúng cấu trúc link theo định dạng công bố.
- `Vary: Accept` có mặt nếu cùng URI trả nhiều biến thể representation.

## 12. Lỗi thường gặp

**Chỉ khai báo `produces` rồi nghĩ converter tự xuất hiện:** mapping chỉ tham gia chọn handler. Cần converter và mapper hỗ trợ media type thực tế.

**Nhầm `+json` với HAL:** hậu tố `+json` chỉ nói về cú pháp JSON, không tự thêm `_links`, `_embedded` hoặc quy tắc relation.

**Dùng mapper JSON thông thường để serialize EntityModel:** mapper có thể không có module/mixin cần thiết của Spring HATEOAS. Hãy cấu hình mapper đúng với định dạng hypermedia.

**Dùng vendor media type không có tài liệu:** client không biết cấu trúc hoặc ngữ nghĩa của representation. Hãy công bố schema, ví dụ, link relation và quy tắc tương thích.

**Nhầm Accept với Content-Type:** `Accept` chọn response; `Content-Type` mô tả request body.

**Thêm version nhưng không duy trì tương thích:** client gửi media type v1 có thể nhận representation không đúng kỳ vọng nếu server thay đổi serializer. Cần kiểm thử từng phiên bản được hỗ trợ.

**Bỏ qua Vary khi response phụ thuộc Accept:** cache có thể trả nhầm biến thể representation. Kiểm tra header và cấu hình cache.

## 13. Checklist thiết kế media type tùy biến

- Chỉ tạo media type riêng khi có ngữ nghĩa hoặc nhu cầu tương thích rõ ràng.
- Chọn subtype ổn định, dễ hiểu và dùng hậu tố `+json` khi payload tuân theo cú pháp JSON.
- Khai báo media type bằng `MediaType` dùng chung.
- Dùng `Accept` để thương lượng response và `Content-Type` để mô tả request body.
- Khai báo `produces`/`consumes` đúng với hợp đồng endpoint.
- Đăng ký `HypermediaMappingInformation` hoặc converter phù hợp cho định dạng hypermedia tùy biến.
- Cấu hình `ObjectMapper` với module/mixin/serializer cần thiết cho representation.
- Không giả định `+json` tự tạo ngữ nghĩa HAL hoặc HAL-FORMS.
- Tài liệu hóa schema, relation, link, affordance và chiến lược versioning.
- Kiểm thử status code 406/415, Content-Type, cấu trúc representation và Vary.
- Giữ các phiên bản media type hoạt động nhất quán trong thời gian hỗ trợ.

Media type tùy biến cho phép API công bố một hợp đồng representation có tên và ngữ nghĩa riêng. Trong Spring HATEOAS, để client thực sự tiêu thụ được representation đó, media type phải được kết nối với content negotiation và converter/mapper hiểu cấu trúc hypermedia. Khi hợp đồng được tài liệu hóa và kiểm thử đầy đủ, API có thể phát triển representation mà vẫn giữ khả năng tương thích rõ ràng cho từng nhóm client.
