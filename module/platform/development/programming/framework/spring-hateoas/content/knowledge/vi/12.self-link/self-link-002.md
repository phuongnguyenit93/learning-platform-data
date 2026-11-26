# Xác định URI hiện tại

Trong Spring HATEOAS, self link là liên kết trỏ tới chính tài nguyên đang được biểu diễn. URI của self link cho client biết địa chỉ để truy cập lại tài nguyên đó. Để tạo link đúng, ứng dụng cần xác định URI từ ánh xạ controller hoặc từ request HTTP hiện tại, tùy theo loại tài nguyên và ngữ cảnh response.

Với tài nguyên có định danh rõ ràng như một đơn hàng, cách ổn định thường là tạo URI từ phương thức controller bằng `WebMvcLinkBuilder`. Với collection tìm kiếm hoặc phân trang, URI hiện tại có thể cần giữ các query parameter của request như `status`, `page` và `size`. Spring HATEOAS và Spring Web cung cấp các công cụ để xử lý cả hai trường hợp.

## Self link đại diện cho URI nào?

Self link dùng relation chuẩn `self` để trỏ về tài nguyên hiện tại. Ví dụ, representation của đơn hàng `ORD-2048` có thể chứa:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ORD-2048"
    }
  }
}
```

URI trong `href` cần xác định đúng tài nguyên đang được biểu diễn. Client có thể theo link này để tải lại tài nguyên hoặc dùng nó làm URI tham chiếu trong các thao tác tiếp theo.

Self link không nhất thiết phải giống URL của request đã tạo ra response. Ví dụ, một lệnh `POST /api/orders` tạo đơn hàng mới; response của lệnh đó biểu diễn đơn hàng vừa tạo, nên self link cần trỏ tới `GET /api/orders/{id}`. Tương tự, một response tìm kiếm có thể được tạo từ URL chứa bộ lọc và phân trang; self link của collection nên phản ánh truy vấn hiện tại nếu truy vấn đó là một phần của tài nguyên collection đang được biểu diễn.

## Cách 1: Tạo URI từ mapping controller

Với tài nguyên có ID, nên tạo link từ mapping của controller bằng `linkTo(...)` và `methodOn(...)`. Spring HATEOAS đọc mapping và tham số của phương thức để xây dựng URI.

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        Order order = service.findRequired(id);
        OrderResponse content = new OrderResponse(
                order.getId(), order.getStatus().name(), order.getTotal());

        return EntityModel.of(
                content,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

`methodOn(OrderController.class).one(id)` tham chiếu phương thức đọc tài nguyên. `linkTo(...)` dựa trên mapping `@RequestMapping("/api/orders")` và `@GetMapping("/{id}")` để tạo URI; `withSelfRel()` gắn quan hệ `self`.

Ưu điểm của cách này là URI đi theo mapping controller. Nếu đường dẫn được đổi từ `/api/orders/{id}` sang `/api/v2/orders/{id}`, link builder sẽ dùng mapping mới sau khi ứng dụng được cập nhật. Mã tạo link không phải tự nối chuỗi URL hoặc tự định dạng ID.

### Tạo self link trong assembler

Khi nhiều endpoint cùng biểu diễn một loại tài nguyên, hãy đặt logic tạo self link trong `RepresentationModelAssembler`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        UUID id = order.getId();
        OrderResponse content = new OrderResponse(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                content,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Controller chỉ cần lấy dữ liệu và gọi `assembler.toModel(order)`. Nhờ đó, mọi response đơn hàng dùng cùng quy tắc xác định URI hiện tại.

## Cách 2: Lấy URI từ HTTP request hiện tại

Trong một số trường hợp, cần dùng chính URI của request đang xử lý, bao gồm cả query parameter. Spring Web cung cấp `ServletUriComponentsBuilder` để đọc URI từ request hiện tại.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

String currentUri = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .build()
        .toUriString();

Link self = Link.of(currentUri).withSelfRel();
EntityModel<SearchResult> model = EntityModel.of(result, self);
```

`fromCurrentRequest()` lấy URI hiện tại cùng query string. Ví dụ, request:

```http
GET /api/orders?status=PENDING&page=0&size=20
```

có thể tạo self link giữ lại các tham số:

```text
/api/orders?status=PENDING&page=0&size=20
```

Cách này phù hợp khi URI đầy đủ của request xác định collection kết quả, chẳng hạn endpoint tìm kiếm, lọc hoặc phân trang. Nó cũng hữu ích khi muốn phản ánh đúng query string đang được xử lý.

### Chỉ lấy URI, không lấy query string

Nếu chỉ cần scheme, host, port và path của request, dùng `fromCurrentRequestUri()`:

```java
String currentPathUri = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .build()
        .toUriString();
```

Phương thức này bỏ query string. Phân biệt hai lựa chọn:

| API | Thành phần được giữ | Trường hợp phù hợp |
|---|---|---|
| `fromCurrentRequest()` | URI và query parameter | Search, filter, pagination |
| `fromCurrentRequestUri()` | URI path, không có query parameter | Tài nguyên được xác định bằng path |

Không nên dùng nguyên URI request cho mọi self link. Nếu request tới endpoint hành động hoặc một alias nhưng response biểu diễn tài nguyên khác, hãy tạo URI từ endpoint đọc tài nguyên bằng controller mapping.

## Giữ query parameter khi tạo self link cho collection

Một collection có thể được xác định bởi bộ lọc và thứ tự sắp xếp. Ví dụ:

```http
GET /api/orders?status=PENDING&sort=createdAt,desc&page=0&size=20
```

Self link của collection nên cho phép client quay lại cùng kết quả. Có hai cách phổ biến.

**Dùng URI của request hiện tại:**

```java
Link self = Link.of(
        ServletUriComponentsBuilder.fromCurrentRequest()
                .build()
                .toUriString()
).withSelfRel();
```

**Tạo link qua phương thức controller với các tham số tường minh:**

```java
Link self = linkTo(methodOn(OrderController.class)
        .search("PENDING", "createdAt,desc", 0, 20))
        .withSelfRel();
```

Phương thức controller tương ứng có thể khai báo các query parameter:

```java
@GetMapping
public CollectionModel<OrderModel> search(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) String sort,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
) {
    // Tìm dữ liệu theo tham số và tạo representation.
}
```

Cách tạo link từ phương thức controller giúp thể hiện rõ các tham số thuộc hợp đồng endpoint. Cách lấy request hiện tại giữ lại query string thực tế, kể cả những tham số mà controller không dùng để tìm dữ liệu. Hãy chọn theo ngữ nghĩa của collection và tránh vô tình đưa tham số theo dõi hoặc tham số không liên quan vào self link.

Với phân trang Spring Data, `PagedResourcesAssembler` có thể tạo metadata và các liên kết `self`, `next`, `prev`, `first`, `last` dựa trên `Pageable` và request hiện tại. Dùng cơ chế tích hợp này thường đơn giản hơn tự ghép URL trang.

## Self link khi tạo tài nguyên mới

Khi client gửi `POST` để tạo tài nguyên, URI request thường là URI collection. Response `201 Created` cần xác định URI của tài nguyên mới. Hãy tạo self link từ ID vừa được lưu:

```java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping
public ResponseEntity<EntityModel<OrderResponse>> create(
        @RequestBody CreateOrderRequest request
) {
    Order created = service.create(request);
    EntityModel<OrderResponse> model = assembler.toModel(created);

    URI selfUri = URI.create(
            model.getRequiredLink(IanaLinkRelations.SELF).getHref()
    );

    return ResponseEntity.created(selfUri).body(model);
}
```

Response vừa trả representation có link `self`, vừa đặt header `Location` trỏ tới URI của đơn hàng mới. Đây là cách thể hiện rõ tài nguyên vừa được tạo và cho client biết địa chỉ để truy cập tiếp.

## URI khi ứng dụng chạy sau reverse proxy

Ứng dụng Spring thường chạy sau load balancer hoặc reverse proxy. Khi đó, request nội bộ có thể dùng `http://service:8080`, trong khi địa chỉ công khai mà client truy cập là `https://api.example.com`. Nếu ứng dụng không xử lý forwarded headers đúng cách, URI tạo từ request hiện tại có thể lộ hostname nội bộ hoặc sai scheme/port.

Để tạo link công khai chính xác:

1. Cấu hình proxy gửi các header chuyển tiếp phù hợp, chẳng hạn `Forwarded` hoặc `X-Forwarded-*`.
2. Cấu hình Spring Boot/Spring MVC hoặc servlet container để xử lý forwarded headers theo phiên bản đang dùng.
3. Chỉ tin các forwarded header từ reverse proxy đáng tin cậy; không cho client bên ngoài tự quyết định host hoặc scheme trong link.
4. Kiểm thử self link qua đúng đường đi proxy ở môi trường triển khai.

`WebMvcLinkBuilder` và `ServletUriComponentsBuilder` dựa vào ngữ cảnh request và cấu hình xử lý forwarded headers của ứng dụng. Không nên tự nối hostname từ header `Host` hoặc `X-Forwarded-Host` mà chưa có cơ chế xác thực nguồn gửi.

## Khi không có HTTP request hiện tại

`ServletUriComponentsBuilder.fromCurrentRequest()` cần request context đang tồn tại. Nó không phù hợp khi tạo representation trong background job, message consumer hoặc tác vụ chạy ngoài luồng HTTP.

Trong các trường hợp đó, nên:

- Tạo link bằng mapping controller nếu có thể thiết lập ngữ cảnh xây dựng URI phù hợp.
- Dùng base URI công khai được cấu hình rõ ràng trong ứng dụng rồi kết hợp với route đã định nghĩa.
- Lưu URI chuẩn của tài nguyên nếu đó là một phần dữ liệu nghiệp vụ và có yêu cầu lâu dài.

Tránh giả định rằng luôn có request hiện tại trong assembler. Nếu assembler được gọi cả từ controller và background process, hãy thiết kế cách cung cấp URI/base URI rõ ràng thay vì phụ thuộc ngầm vào request context.

## Kiểm thử self link

Kiểm thử nên xác nhận relation `self` tồn tại và URI trỏ tới đúng tài nguyên. Với MockMvc:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/api/orders/" + orderId)));
```

Với collection có bộ lọc và phân trang, kiểm tra self link giữ query parameter quan trọng:

```java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").value(
            allOf(containsString("status=PENDING"),
                  containsString("page=0"),
                  containsString("size=20"))));
```

Các matcher `endsWith`, `allOf` và `containsString` là matcher của Hamcrest. Trong dự án, hãy thêm static import tương ứng. Nếu URL được tạo dưới dạng absolute URI, nên kiểm tra scheme/host theo cấu hình test hoặc chỉ kiểm tra path/query để tránh làm test phụ thuộc hostname của môi trường.

Với endpoint tạo tài nguyên, kiểm tra cả `Location` và link `self` trong body để bảo đảm hai giá trị trỏ tới cùng tài nguyên:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(jsonPath("$._links.self.href").exists());
```

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự nối URL bằng ID | Link dễ sai khi mapping đổi | Dùng `linkTo(methodOn(...))` |
| Dùng URL POST collection làm self của tài nguyên mới | Self link trỏ tới collection thay vì tài nguyên vừa tạo | Tạo link từ endpoint đọc tài nguyên và ID mới |
| Dùng `fromCurrentRequestUri()` khi cần query | Mất filter hoặc pagination | Dùng `fromCurrentRequest()` hoặc tham số controller tường minh |
| Dùng toàn bộ request URI cho endpoint hành động | Self link có thể trỏ tới action thay vì tài nguyên | Tạo link từ endpoint đọc tài nguyên |
| Không xử lý forwarded headers | Link chứa host, scheme hoặc port nội bộ | Cấu hình proxy và forwarded header support |
| Dùng request context trong background job | Không có request để suy ra URI | Cung cấp base URI rõ ràng hoặc dùng chiến lược tạo link khác |
| Tin trực tiếp forwarded host từ client | Có thể tạo link trỏ tới host không đáng tin cậy | Chỉ tin header từ proxy được kiểm soát |

## Quy trình xác định URI hiện tại

Khi tạo self link, hãy xác định loại URI cần biểu diễn trước:

1. Với tài nguyên có ID, dùng `linkTo(methodOn(...))` để tạo URI từ mapping đọc tài nguyên.
2. Với collection được xác định bởi query hiện tại, dùng `fromCurrentRequest()` hoặc truyền query parameter rõ ràng vào phương thức controller.
3. Dùng `fromCurrentRequestUri()` khi chỉ cần path và không cần query string.
4. Với response tạo tài nguyên, tạo self link từ ID mới và dùng URI đó cho header `Location`.
5. Nếu chạy sau proxy, cấu hình forwarded headers và chỉ tin proxy đáng tin cậy.
6. Không phụ thuộc request context trong background task; cung cấp base URI rõ ràng.
7. Kiểm thử relation, path, query parameter và `Location` của response.

## Kết luận

Xác định đúng URI hiện tại là điều kiện để self link trỏ tới đúng tài nguyên và giúp client điều hướng đáng tin cậy. Spring HATEOAS có thể tạo URI từ controller mapping bằng `WebMvcLinkBuilder`; Spring Web có thể lấy URI của request hiện tại bằng `ServletUriComponentsBuilder`. Chọn đúng cách theo tài nguyên, giữ query parameter khi cần, xử lý forwarded headers sau reverse proxy và kiểm thử self link cùng `Location` giúp hợp đồng hypermedia ổn định khi ứng dụng triển khai ở nhiều môi trường.
