# ResponseEntity với model

Trong Spring MVC, controller có thể trả trực tiếp một đối tượng representation model như `EntityModel<OrderResponse>` hoặc `CollectionModel<OrderModel>`. Spring sẽ dùng các `HttpMessageConverter` đã đăng ký để ghi body thành định dạng mà request yêu cầu. Khi controller còn cần quyết định HTTP status, thêm header như `Location` hoặc `ETag`, hoặc trả về body tùy theo kết quả nghiệp vụ, `ResponseEntity<T>` là lựa chọn phù hợp.

Với Spring HATEOAS, kiểu trả về thường có dạng `ResponseEntity<EntityModel<T>>`, `ResponseEntity<CollectionModel<T>>` hoặc `ResponseEntity<PagedModel<T>>`. `ResponseEntity` quản lý phần HTTP response gồm status, headers và body; representation model ở bên trong body quản lý content nghiệp vụ cùng các hypermedia links. Hai lớp này bổ sung cho nhau: một lớp điều khiển HTTP, một lớp mô tả tài nguyên.

Trong module SPRING_HATEOAS, tích hợp `ResponseEntity` giúp controller trả representation có links theo đúng ngữ nghĩa HTTP. Bài học này tập trung vào cấu trúc kiểu trả về, cách trả một resource và collection, cách tạo tài nguyên mới với status `201 Created` và header `Location`, cách xử lý resource không tồn tại, lựa chọn status cho thao tác cập nhật/xóa, content negotiation và kiểm thử response.

Sau bài học, bạn có thể:

- Phân biệt `ResponseEntity<T>` với representation model `EntityModel<T>`.
- Chọn kiểu trả về phù hợp cho item, collection và paged collection.
- Kết hợp status, headers và HATEOAS body trong cùng response.
- Trả `201 Created` cùng `Location` và self link sau khi tạo resource.
- Dùng `ResponseEntity.of(Optional<T>)` để ánh xạ kết quả có/không có resource.
- Chọn `200`, `202`, `204` và `404` theo kết quả thao tác.
- Dùng `produces`, `Accept` và Content-Type khi trả HAL.
- Kiểm thử status, header và links bằng MockMvc.

## ResponseEntity và representation model có vai trò gì?

`ResponseEntity<T>` là kiểu HTTP response của Spring. Nó cho phép controller quyết định ba thành phần:

1. **Status code:** ví dụ 200, 201, 202, 204 hoặc 404.
2. **Response headers:** ví dụ Location, ETag, Cache-Control hoặc Vary.
3. **Body:** đối tượng được ghi thành HTTP representation.

`EntityModel<T>`, `CollectionModel<T>` và `PagedModel<T>` là các kiểu representation của Spring HATEOAS. Chúng giữ content và links, có thể được serialize thành HAL JSON hoặc media type hypermedia đã cấu hình.

Khi kết hợp hai loại:

~~~java
ResponseEntity<EntityModel<OrderResponse>>
ResponseEntity<CollectionModel<EntityModel<OrderResponse>>>
ResponseEntity<PagedModel<EntityModel<OrderResponse>>>
~~~

`ResponseEntity` không tự thêm links vào body. Controller hoặc assembler phải tạo representation model và gắn links trước khi đưa model vào `ResponseEntity`.

### Phân biệt với HttpEntity và @ResponseBody

`@ResponseBody` yêu cầu Spring ghi giá trị trả về vào response body; status mặc định thường là 200 và header có thể được cấu hình qua annotation hoặc cơ chế khác. `HttpEntity<T>` mang body cùng headers nhưng không mang status riêng. `ResponseEntity<T>` kế thừa `HttpEntity<T>` và bổ sung status code, vì vậy phù hợp khi kết quả nghiệp vụ quyết định status hoặc headers.

| Cách trả về | Body | Headers | Status |
| --- | --- | --- | --- |
| `@ResponseBody T` | Có | Không trực tiếp trong kiểu trả về | Theo mặc định hoặc annotation |
| `HttpEntity<T>` | Có | Có | Theo mặc định của framework |
| `ResponseEntity<T>` | Có thể có hoặc rỗng | Có | Có thể chỉ định |

### So sánh kiểu trả về

| Kiểu trả về | Vai trò | Khi dùng |
| --- | --- | --- |
| `EntityModel<T>` | Một content object cùng links | Trả một tài nguyên |
| `CollectionModel<T>` | Một collection cùng links cấp collection | Trả danh sách |
| `PagedModel<T>` | Collection có metadata trang và links điều hướng | Trả kết quả phân trang |
| `ResponseEntity<T>` | Status, headers và body | Cần điều khiển HTTP response |
| `ResponseEntity<EntityModel<T>>` | HTTP response chứa một item representation | Cần status/header và HATEOAS links cho một tài nguyên |

Nếu endpoint luôn trả `200 OK` và không cần header động, controller có thể trả trực tiếp `EntityModel<T>`. Nếu endpoint cần trả `201 Created`, `404 Not Found` hoặc header riêng theo kết quả, `ResponseEntity` làm rõ hợp đồng HTTP.

### ResponseEntity được Spring MVC xử lý như thế nào?

Spring MVC nhận `ResponseEntity` từ controller, áp dụng status và headers vào HTTP response, sau đó ghi body bằng `HttpMessageConverter` tương ứng. Khi body là representation model và client yêu cầu `application/hal+json`, cấu hình Spring HATEOAS sẽ serialize content cùng links thành HAL JSON.

Ví dụ:

~~~java
@GetMapping(value = "/orders/{id}", produces = MediaTypes.HAL_JSON_VALUE)
ResponseEntity<EntityModel<OrderResponse>> one(@PathVariable Long id) {
    EntityModel<OrderResponse> model = assembler.toModel(orderService.get(id));
    return ResponseEntity.ok(model);
}
~~~

`ResponseEntity.ok(model)` đặt status 200 và body là representation model. Spring MVC thực hiện serialize body; controller không cần tự chuyển model thành JSON string.

## Trả về một resource bằng ResponseEntity<EntityModel<T>>

Với endpoint đọc một tài nguyên, body thường là `EntityModel<T>`. Assembler chuyển domain object thành DTO và gắn self link cùng các relation phù hợp.

Assembler ví dụ:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(),
            order.orderNumber(),
            order.status().name());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}
~~~

Controller có thể trả response như sau:

~~~java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> one(@PathVariable Long id) {
    Order order = orderService.get(id);
    EntityModel<OrderResponse> model = assembler.toModel(order);

    return ResponseEntity.ok(model);
}
~~~

Ví dụ giả định service trả về order hợp lệ và assembler đã được inject. Nếu service không tìm thấy order, cần chuyển kết quả đó thành 404 thay vì để một lỗi không được xử lý trở thành 500.

### Xử lý resource không tồn tại

Nếu service trả `Optional<Order>`, có thể chuyển Optional thành Optional representation rồi dùng `ResponseEntity.of`:

~~~java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> one(@PathVariable Long id) {
    return ResponseEntity.of(
        orderService.findById(id).map(assembler::toModel));
}
~~~

`ResponseEntity.of(Optional<T>)` trả `200 OK` với body khi Optional có giá trị và `404 Not Found` với body rỗng khi Optional không có giá trị. API này có từ Spring Framework 5.1.

Nếu cần body lỗi theo một schema riêng, hãy xử lý bằng exception handler hoặc tạo response lỗi theo hợp đồng API. `ResponseEntity.of` chỉ giải quyết lựa chọn 200/404 đơn giản; nó không tự tạo thông tin lỗi chi tiết.

Có thể viết rõ nhánh xử lý nếu cần thêm headers hoặc logging:

~~~java
Optional<Order> result = orderService.findById(id);

if (result.isEmpty()) {
    return ResponseEntity.notFound().build();
}

EntityModel<OrderResponse> model = assembler.toModel(result.get());
return ResponseEntity.ok(model);
~~~

## Tạo resource mới: 201 Created, Location và self link

Khi client gửi POST để tạo tài nguyên, response thường dùng `201 Created`. Header `Location` chỉ URI của tài nguyên vừa được tạo. Body có thể chứa representation model của tài nguyên đó, gồm self link và các relation khác mà client có thể sử dụng.

Ví dụ request:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "productId": 900,
  "quantity": 2
}
~~~

Controller:

~~~java
import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<EntityModel<OrderResponse>> create(
        @Valid @RequestBody CreateOrderRequest request) {

    Order created = orderService.create(request);
    EntityModel<OrderResponse> model = assembler.toModel(created);

    URI location = URI.create(model.getRequiredLink("self").getHref());

    return ResponseEntity.created(location)
        .contentType(MediaTypes.HAL_JSON)
        .body(model);
}
~~~

Ví dụ giả định assembler luôn thêm relation `self` và service trả về tài nguyên đã lưu với ID được tạo. `ResponseEntity.created(location)` tạo status 201 và header `Location`. `body(model)` đặt representation model vào response body.

### Location và self link khác nhau thế nào?

Hai giá trị thường trỏ đến cùng một URI nhưng có vai trò ở hai lớp:

| Thành phần | Nằm ở đâu | Ý nghĩa |
| --- | --- | --- |
| `Location` | HTTP response header | Cho biết URI của resource vừa được tạo |
| `self` | Hypermedia links trong body | Cho client biết link định danh representation hiện tại |

Client HTTP có thể đọc Location ngay cả khi không phân tích body. Client HATEOAS có thể đọc self link trong representation và tiếp tục điều hướng. Giữ hai URI đồng nhất giúp hợp đồng dễ hiểu và tránh hai nguồn định danh mâu thuẫn.

Nếu không muốn phụ thuộc vào assembler để lấy self link, có thể tạo URI bằng controller mapping:

~~~java
URI location = linkTo(methodOn(OrderController.class)
    .one(created.id())).toUri();
~~~

`WebMvcLinkBuilder` xây URI từ mapping controller và request hiện tại, giúp tránh hard-code đường dẫn. Nếu dùng cách này, vẫn phải bảo đảm assembler tạo self link cùng target.

### Khi nào dùng 202 Accepted?

Nếu POST chỉ tiếp nhận công việc và xử lý bất đồng bộ, tài nguyên nghiệp vụ có thể chưa được tạo xong tại thời điểm trả response. Trong trường hợp đó, `202 Accepted` có thể phù hợp hơn `201 Created`. Body nên mô tả operation hoặc job đang chạy, có link để client kiểm tra trạng thái:

~~~java
return ResponseEntity.accepted()
    .body(operationAssembler.toModel(operation));
~~~

Không nên trả 201 nếu tài nguyên được chỉ định trong Location chưa thực sự được tạo theo semantics của endpoint.

## Trả về collection và paged collection

Với collection, body thường là `CollectionModel<T>` hoặc `CollectionModel<EntityModel<T>>`. `ResponseEntity` cho phép gắn status và headers ở cấp HTTP mà không làm thay đổi cấu trúc collection representation.

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<CollectionModel<EntityModel<OrderResponse>>> all() {
    CollectionModel<EntityModel<OrderResponse>> model =
        assembler.toCollectionModel(orderService.findAll());

    return ResponseEntity.ok(model);
}
~~~

Collection model có thể rỗng mà vẫn là response hợp lệ. Nếu collection không có phần tử, server thường trả `200 OK` cùng collection rỗng và self link, thay vì trả 404.

Với kết quả phân trang:

~~~java
@GetMapping(value = "/search", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<PagedModel<EntityModel<OrderResponse>>> search(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(pageable);
    PagedModel<EntityModel<OrderResponse>> model =
        pagedAssembler.toModel(page, assembler);

    return ResponseEntity.ok(model);
}
~~~

`PagedResourcesAssembler` tạo page metadata và các navigation links dựa trên request cùng kết quả `Page`. `ResponseEntity` ở đây chỉ bọc toàn bộ paged representation với status 200. Nó không thay thế chức năng phân trang hay tự sinh các page links.

### Chọn body model theo hình dạng response

| Dữ liệu từ service | Representation model | Kiểu ResponseEntity |
| --- | --- | --- |
| Một order | `EntityModel<OrderResponse>` | `ResponseEntity<EntityModel<OrderResponse>>` |
| Danh sách order có links từng item | `CollectionModel<EntityModel<OrderResponse>>` | `ResponseEntity<CollectionModel<EntityModel<OrderResponse>>>` |
| Trang order có links từng item | `PagedModel<EntityModel<OrderResponse>>` | `ResponseEntity<PagedModel<EntityModel<OrderResponse>>>` |

Giữ kiểu generic cụ thể giúp người đọc hiểu body và giúp compiler phát hiện một số lỗi gán nhầm model. Hạn chế dùng raw type hoặc `ResponseEntity<Object>` nếu endpoint có một kiểu body thành công ổn định.

## Chọn status code theo kết quả thao tác

`ResponseEntity` cung cấp các builder tĩnh giúp biểu đạt status rõ ràng:

| Builder | Status | Tình huống thường gặp |
| --- | --- | --- |
| `ResponseEntity.ok(body)` | 200 OK | Đọc hoặc cập nhật và trả representation |
| `ResponseEntity.created(uri)` | 201 Created | Tạo resource mới, có Location |
| `ResponseEntity.accepted()` | 202 Accepted | Chấp nhận xử lý bất đồng bộ |
| `ResponseEntity.noContent()` | 204 No Content | Thao tác thành công, không trả body |
| `ResponseEntity.notFound()` | 404 Not Found | Resource đích không tồn tại |
| `ResponseEntity.badRequest()` | 400 Bad Request | Request không hợp lệ khi xử lý thủ công |
| `ResponseEntity.status(status)` | Status tùy chọn | Hợp đồng cần status khác |

Ví dụ cập nhật và xóa:

~~~java
@PutMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateOrderRequest request) {

    return orderService.update(id, request)
        .map(assembler::toModel)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}

@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(@PathVariable Long id) {
    boolean deleted = orderService.delete(id);

    return deleted
        ? ResponseEntity.noContent().build()
        : ResponseEntity.notFound().build();
}
~~~

Ví dụ giả định service trả Optional khi update và boolean khi delete. Nếu PUT trả representation đã cập nhật, `200 OK` cùng model là phù hợp. Nếu DELETE thành công và không cần trả representation, `204 No Content` là lựa chọn thông dụng.

Không gửi body cùng status 204. Khi đã chọn `noContent().build()`, response không chứa representation model; client có thể tải lại collection hoặc resource qua link đã có nếu cần đồng bộ giao diện.

## Thêm response headers cùng HATEOAS body

Ngoài status và body, `ResponseEntity.BodyBuilder` hỗ trợ thêm headers:

- `header(name, values...)` thêm header tùy chỉnh.
- `contentType(mediaType)` đặt Content-Type.
- `eTag(value)` đặt ETag.
- `lastModified(value)` đặt Last-Modified.
- `cacheControl(value)` đặt Cache-Control.
- `varyBy(headers...)` khai báo các request header ảnh hưởng response.

Ví dụ response HAL có ETag và cache policy:

~~~java
import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;

@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> one(@PathVariable Long id) {
    Order order = orderService.get(id);
    EntityModel<OrderResponse> model = assembler.toModel(order);

    return ResponseEntity.ok()
        .eTag(order.versionTag())
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(1)).cachePrivate())
        .varyBy(HttpHeaders.ACCEPT)
        .body(model);
}
~~~

Ví dụ giả định `versionTag()` trả về giá trị version phù hợp với ETag và order có thể cache riêng cho user. `Vary: Accept` hữu ích khi cùng URI có thể trả nhiều media type tùy header Accept; cache sẽ biết representation phụ thuộc header đó.

Không đặt cache policy công khai cho representation chứa dữ liệu cá nhân hoặc dữ liệu phân quyền nếu cache dùng chung có thể làm lộ nội dung. Chọn Cache-Control theo tính nhạy cảm và khả năng thay đổi của dữ liệu.

### Không cần tự serialize body

Không làm như sau:

~~~java
String json = objectMapper.writeValueAsString(model);
return ResponseEntity.ok(json);
~~~

Cách này biến body thành String và có thể làm Spring xử lý nó như văn bản, khiến Content-Type và hypermedia converter không còn được chọn theo kiểu model. Hãy trả trực tiếp model:

~~~java
return ResponseEntity.ok(model);
~~~

Để Spring MVC cùng message converter xử lý serialization.

## Content negotiation cho ResponseEntity chứa model

`ResponseEntity` không quyết định media type hypermedia. Media type được xác định thông qua cấu hình converter, mapping của controller và header request.

Ví dụ endpoint chỉ công bố HAL JSON:

~~~java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public ResponseEntity<EntityModel<OrderResponse>> one(@PathVariable Long id) {
    // Build and return model.
}
~~~

Client yêu cầu:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Response có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Nếu controller khai báo `produces = application/hal+json`, client yêu cầu một media type không tương thích có thể nhận `406 Not Acceptable`. Nếu endpoint hỗ trợ nhiều representation, khai báo các media type tương ứng và để Spring chọn converter phù hợp.

Có thể đặt Content-Type tường minh trên builder:

~~~java
return ResponseEntity.ok()
    .contentType(MediaTypes.HAL_JSON)
    .body(model);
~~~

Chỉ đặt tường minh khi hợp đồng cần cố định media type. Tránh đặt Content-Type không khớp body hoặc không khớp media type mà endpoint công bố.

## Xử lý lỗi và representation lỗi

Response lỗi cũng cần có status và body nhất quán. Có thể dùng `@RestControllerAdvice` để ánh xạ exception thành HTTP response. Với Spring Framework hỗ trợ Problem Details, `ProblemDetail` có thể biểu diễn lỗi theo định dạng chuẩn.

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            exception.getMessage());

        problem.setTitle("Order not found");
        return ResponseEntity.of(problem).build();
    }
}
~~~

Ví dụ dùng overload `ResponseEntity.of(ProblemDetail)` có từ Spring Framework 6.0; status của response lấy từ ProblemDetail. Nếu ứng dụng chạy Spring Framework cũ hơn, dùng `ResponseEntity.status(problem.getStatus()).body(problem)` hoặc exception handling phù hợp với version đó.

Overload này tạo builder đã giữ sẵn ProblemDetail làm body, vì vậy gọi `build()` để tạo `ResponseEntity<ProblemDetail>`; không gọi `body(problem)` lần nữa.

Problem Details là representation lỗi ở cấp HTTP. Nó không tự trở thành `EntityModel` và không tự có HATEOAS links. Nếu API muốn lỗi cũng có hypermedia links, hãy thiết kế error representation riêng hoặc enrich model theo hợp đồng đã công bố.

Không nên trộn body thành công kiểu `EntityModel<OrderResponse>` và body lỗi kiểu `ProblemDetail` vào một kiểu trả về quá rộng mà không tài liệu hóa. Dùng exception handler riêng để success endpoint vẫn giữ generic type rõ ràng.

## Kiểm thử ResponseEntity và HATEOAS model bằng MockMvc

Kiểm thử cần xác minh ba phần: status code, HTTP headers và representation body. Một test chỉ kiểm tra `200 OK` chưa đủ để xác nhận response có đúng media type hoặc hypermedia links.

### Kiểm thử tạo resource

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderResponseEntityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsOrderAndReturnsLocationAndHalModel() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "productId": 900,
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Test giả định request hợp lệ, service lưu được order và assembler thêm self link. Nếu endpoint dùng status 201, hãy xác minh Location trỏ đến cùng resource với self link.

### Kiểm thử resource không tồn tại

~~~java
@Test
void returnsNotFoundWhenOrderDoesNotExist() throws Exception {
    mockMvc.perform(get("/orders/{id}", 999999L)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}
~~~

Test giả định ID không tồn tại và controller chuyển Optional rỗng thành 404. Có thể kiểm tra thêm response body rỗng hoặc Problem Details tùy hợp đồng lỗi.

### Kiểm thử collection và 204

~~~java
@Test
void returnsHalCollection() throws Exception {
    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}

@Test
void deleteReturnsNoContent() throws Exception {
    mockMvc.perform(delete("/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
}
~~~

Ví dụ giả định endpoint collection thêm self link và order 42 tồn tại để xóa. Với test DELETE, không gửi Accept HAL nếu response 204 không có representation body.

Các trường hợp nên kiểm thử:

1. GET item trả 200 cùng EntityModel và self link.
2. GET item không tồn tại trả 404.
3. POST tạo mới trả 201, Location và body model.
4. Location và self link trỏ đến cùng resource.
5. GET collection trả CollectionModel và links cấp collection.
6. GET search trả PagedModel cùng page metadata và navigation links.
7. PUT trả 200 với model hoặc 204 không body theo hợp đồng.
8. DELETE thành công trả 204 và body rỗng.
9. Response có Content-Type tương thích với Accept.
10. Accept không được hỗ trợ nhận 406 khi mapping giới hạn bằng produces.
11. ETag, Cache-Control và Vary có giá trị đúng nếu endpoint sử dụng.
12. Error handler trả status cùng error representation đã công bố.

## Những sai lầm thường gặp

**Nhầm ResponseEntity với EntityModel.** ResponseEntity quản lý status/header/body; EntityModel quản lý content và links. Khi cần cả hai, dùng ResponseEntity<EntityModel<T>>.

**Trả DTO thuần khi client cần hypermedia.** DTO không tự có links. Hãy chuyển DTO/domain object thành representation model bằng assembler.

**Trả 200 khi tạo resource mới.** Nếu thao tác đã tạo resource, 201 Created cùng Location thường mô tả chính xác hơn.

**Chỉ đặt Location mà quên self link.** HTTP client có Location, nhưng client HATEOAS cần self relation trong body để điều hướng theo representation.

**Location và self link trỏ đến hai URI khác nhau.** Hãy tạo chúng từ cùng controller mapping hoặc lấy Location từ self link của model.

**Dùng 204 nhưng vẫn trả body.** 204 No Content không có representation body. Nếu cần trả model sau thao tác, dùng status phù hợp như 200.

**Tự serialize model thành JSON String.** Trả model trực tiếp để Spring HATEOAS converter xử lý media type và links.

**Đặt Content-Type không khớp với body.** Dùng produces và Accept cho negotiation; chỉ đặt contentType tường minh khi cần.

**Dùng ResponseEntity<Object> cho mọi endpoint.** Giữ generic type cụ thể để hợp đồng rõ và giảm lỗi gán nhầm body.

**Coi ResponseEntity.of(Optional) là error handler đầy đủ.** Nó chỉ ánh xạ Optional có/không có thành 200/404. Lỗi cần chi tiết nên được xử lý theo error contract riêng.

**Cho rằng ResponseEntity tự tạo affordance hoặc links.** Links phải được assembler hoặc controller thêm vào representation model trước khi trả response.

## Kết luận

`ResponseEntity<T>` giúp Spring MVC kiểm soát HTTP status, headers và body trong cùng một kiểu trả về. Khi làm việc với Spring HATEOAS, đặt representation model bên trong body: `EntityModel<T>` cho một tài nguyên, `CollectionModel<T>` cho collection và `PagedModel<T>` cho collection phân trang. Spring MVC dùng message converter đã cấu hình để serialize body theo media type client yêu cầu.

Với thao tác tạo resource, trả `201 Created` cùng `Location` và body có self link. Với truy vấn có thể không tìm thấy tài nguyên, `ResponseEntity.of(Optional<T>)` giúp biểu đạt 200 hoặc 404. Với thao tác không trả body, dùng 204; với collection hoặc paged result, để assembler tạo links và metadata trước khi bọc bằng ResponseEntity. Kiểm thử status, headers, Content-Type và links để bảo đảm hợp đồng HTTP và hypermedia thống nhất.

Tài liệu tham khảo:

- [Spring HATEOAS Reference — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models).
- [Spring HATEOAS Reference — Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.mvc).
- [Spring Framework Reference — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html).
- [Spring Framework API — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html).
