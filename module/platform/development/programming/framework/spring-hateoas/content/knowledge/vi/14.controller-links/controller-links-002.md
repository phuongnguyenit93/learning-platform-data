# Link đến handler method

Trong Spring HATEOAS, một link thường được tạo từ URI của một endpoint mà client có thể truy cập. Nếu viết URI bằng chuỗi cố định ở nhiều nơi, đường dẫn dễ bị lệch khi controller đổi mapping, thêm context path hoặc chuyển qua reverse proxy. Spring HATEOAS giải quyết vấn đề này bằng cách cho phép tạo link trực tiếp từ handler method của Spring MVC.

Cách dùng phổ biến là kết hợp `methodOn(...)` và `linkTo(...)`. `methodOn` ghi nhận lời gọi giả lập đến một phương thức controller; `linkTo` đọc metadata mapping và tạo URI tương ứng. Lời gọi giả lập không chạy logic nghiệp vụ của handler. Nhờ vậy, link có thể bám theo mapping thực tế mà không phải lặp lại chuỗi URL.

Bài học này trình bày cách tạo link đến handler method, cách xử lý path variable và request parameter, các giới hạn của proxy mà `methodOn` sử dụng, cách gắn link vào representation, liên kết affordance và kiểm thử link được sinh ra.

## 1. Từ handler method đến URI

Giả sử controller quản lý đơn hàng:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // Tìm và trả về một đơn hàng
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        // Trả về tập hợp đơn hàng
    }
}
~~~

Mapping ở cấp lớp tạo phần đường dẫn cơ sở `/orders`; mapping ở cấp phương thức bổ sung `/{id}` cho endpoint chi tiết. URI của một đơn hàng có dạng `/orders/{id}`.

Nếu tự tạo link bằng chuỗi:

~~~java
Link self = Link.of("/orders/" + order.getId(), "self");
~~~

mã nguồn phải biết trước cấu trúc route. Khi route thay đổi, mọi nơi nối chuỗi đều có thể cần cập nhật. Việc nối chuỗi còn dễ tạo lỗi encoding hoặc bỏ sót context path.

Thay vào đó, có thể yêu cầu Spring HATEOAS đọc mapping của handler method:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

Spring HATEOAS kết hợp mapping của `OrderController` với giá trị path variable để tạo link. Nếu mapping là `/orders/{id}` và id là `ORD-42`, href sẽ trỏ đến đường dẫn tương ứng.

## 2. Vai trò của methodOn() và linkTo()

Hai phương thức đảm nhiệm hai phần khác nhau:

| Phương thức | Vai trò |
|---|---|
| `methodOn(Controller.class)` | Tạo proxy ghi nhận lời gọi giả lập đến handler method |
| `linkTo(invocation)` | Đọc metadata mapping từ lời gọi đã ghi nhận và tạo link builder |
| `withSelfRel()` | Gắn relation chuẩn `self` cho link |
| `withRel("...")` | Gắn relation do API lựa chọn |

Có thể import static để cú pháp ngắn hơn:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.*;

Link link = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

### 2.1. methodOn() không gọi logic controller

Khi viết:

~~~java
methodOn(OrderController.class).one(orderId)
~~~

Java gọi phương thức trên một proxy do Spring HATEOAS tạo ra. Proxy ghi nhận phương thức và đối số để xác định handler method cần dùng. Phần thân thật của `one(...)` không được thực thi.

Do đó, không nên đặt truy vấn database, gửi email, cập nhật trạng thái hoặc tác dụng phụ khác trong một biểu thức được truyền vào `linkTo(methodOn(...))`. Những việc đó thuộc luồng xử lý request thông thường.

Ví dụ an toàn:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

Ví dụ trên chỉ cung cấp metadata và giá trị định danh để xây URI. Việc tìm đơn hàng đã được thực hiện trước đó bởi service hoặc repository.

### 2.2. Handler method phải có kiểu trả về có thể proxy

`methodOn` cần tạo proxy cho kiểu trả về để giữ được thông tin lời gọi. Vì vậy, kiểu trả về của handler phải có khả năng được proxy. Một kiểu final như `String` dùng làm tên view không phù hợp với kỹ thuật này.

Trong REST controller, các kiểu như `EntityModel<T>`, `CollectionModel<T>` hoặc `ResponseEntity<T>` thường phù hợp. Nếu handler trả kiểu không thể proxy, hãy cân nhắc dùng overload `linkTo(Method, ...)` hoặc `linkTo(Class, Method, ...)` thay vì lời gọi proxy.

Không nên biến kiểu trả về của handler chỉ để tạo link nếu có lựa chọn khác. Hãy chọn cách tạo link tương thích với chữ ký controller hiện có.

## 3. Link đến handler method có path variable

Path variable là phần quan trọng nhất khi tạo link đến tài nguyên cụ thể. Spring HATEOAS lấy giá trị từ tham số được đánh dấu `@PathVariable` và đặt vào vị trí tương ứng trong mapping.

Controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Tạo link:

~~~java
UUID orderId = order.getId();

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Nếu handler có nhiều path variable:

~~~java
@GetMapping("/{orderId}/items/{itemId}")
public EntityModel<OrderItemRepresentation> item(
        @PathVariable UUID orderId,
        @PathVariable UUID itemId) {
    // ...
}
~~~

cần truyền đủ đối số theo đúng thứ tự chữ ký phương thức:

~~~java
Link itemLink = linkTo(
    methodOn(OrderController.class).item(orderId, itemId)
).withRel("item");
~~~

Tên biến trong URI được lấy từ metadata mapping và annotation. Nên khai báo tên `@PathVariable` tường minh khi tên tham số Java không trùng placeholder hoặc khi muốn hợp đồng rõ ràng:

~~~java
@GetMapping("/{orderId}")
public EntityModel<OrderRepresentation> one(
        @PathVariable("orderId") UUID id) {
    // ...
}
~~~

### 3.1. Mapping ở cấp lớp và cấp phương thức

`linkTo(methodOn(...).method(...))` kết hợp mapping của lớp controller với mapping của handler method. Ví dụ:

~~~java
@RequestMapping("/api/v1/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        // ...
    }
}
~~~

Link được tạo từ handler method sẽ bao gồm cả prefix `/api/v1/orders` và path variable. Khi prefix thay đổi, link được sinh từ mapping sẽ phản ánh cấu hình mới.

Nếu chỉ cần link đến gốc controller, có thể dùng:

~~~java
Link orders = linkTo(OrderController.class)
    .withRel("orders");
~~~

Cách này sử dụng mapping ở cấp controller. Nó phù hợp cho link đến tài nguyên gốc của controller khi mapping lớp đã đủ xác định đích. Đối với một handler cụ thể, dùng `methodOn` để tránh tự ghép phần đường dẫn phương thức.

## 4. Link đến handler có request parameter

Handler method có thể nhận query parameter bằng `@RequestParam`. Khi tạo link từ handler, các giá trị request parameter được xử lý theo metadata tham số và URI contributor.

Ví dụ:

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> search(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) Integer page) {
    // ...
}
~~~

Tạo link đến kết quả tìm kiếm cụ thể:

~~~java
Link processingOrders = linkTo(
    methodOn(OrderController.class).search("PROCESSING", 2)
).withRel("orders");
~~~

Giá trị của `status` và `page` được biểu diễn thành query parameter theo mapping của handler. Với tham số không liên quan đến URI như request body, header hoặc đối tượng request, không nên kỳ vọng chúng xuất hiện trong href.

Khi muốn giữ link tìm kiếm tổng quát cho client, hãy thiết kế URI template với các biến query rõ ràng. Có thể tạo template tường minh bằng `Link.of(...)` hoặc `UriTemplate`, rồi gắn relation search. Không nên suy luận rằng truyền `null` vào mọi đối số `methodOn` luôn tạo ra template cho tất cả tham số.

### 4.1. Request parameter dạng collection

Một handler có thể nhận nhiều giá trị cho cùng một query parameter:

~~~java
import org.springframework.hateoas.NonComposite;

@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> searchByStatus(
        @RequestParam("status") Collection<String> statuses) {
    // ...
}
~~~

Mặc định, các giá trị collection được biểu diễn theo kiểu composite, lặp lại tên tham số:

~~~text
/orders?status=NEW&status=PROCESSING
~~~

Spring HATEOAS hỗ trợ cách biểu diễn non-composite bằng annotation `@NonComposite`, khi đó các giá trị có thể được phân tách bằng dấu phẩy:

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> searchByStatus(
        @NonComposite @RequestParam("status") Collection<String> statuses) {
    // ...
}
~~~

Tạo link với danh sách giá trị:

~~~java
var statuses = List.of("NEW", "PROCESSING");

Link search = linkTo(
    methodOn(OrderController.class).searchByStatus(statuses)
).withRel("search");
~~~

Với non-composite, href có dạng:

~~~text
/orders?status=NEW,PROCESSING
~~~

Cả hai dạng đều có thể được Spring MVC phân tích thành collection. Chọn cách biểu diễn nhất quán với hợp đồng API và kiểm thử href thực tế, đặc biệt nếu giá trị có dấu phẩy hoặc ký tự cần encoding.

## 5. Tham số không tham gia URI

Không phải mọi đối số của handler đều được đưa vào URI. Link builder quan tâm đến các tham số được ánh xạ vào đường dẫn hoặc query string.

Ví dụ handler cập nhật:

~~~java
@PutMapping("/{id}")
public ResponseEntity<Void> update(
        @RequestBody OrderUpdateRequest request,
        @PathVariable UUID id) {
    // ...
}
~~~

Khi tham chiếu handler để tạo affordance hoặc link, đối số request body có thể dùng placeholder `null`; path variable cần giá trị thực:

~~~java
methodOn(OrderController.class).update(null, orderId)
~~~

Các thông tin như `@RequestBody`, `@RequestHeader`, `HttpServletRequest` hoặc principal không tạo thành phần path của URI. Không đưa dữ liệu nhạy cảm vào URI chỉ để làm cho link builder nhận được giá trị.

Với `@RequestParam`, `@PathVariable` và các URI contributor tùy chỉnh, hành vi phụ thuộc annotation và cấu hình. Khi một tham số cần xuất hiện trong URI, hãy xác nhận nó được ánh xạ rõ ràng và kiểm tra link đầu ra.

## 6. Overload linkTo() nhận Method

Ngoài cách gọi proxy, WebMvcLinkBuilder còn hỗ trợ tạo link từ đối tượng `java.lang.reflect.Method`.

~~~java
Method method = OrderController.class.getMethod("one", UUID.class);

Link self = linkTo(
    OrderController.class,
    method,
    orderId
).withSelfRel();
~~~

Cách này không cần gọi `methodOn`, nhưng phải lấy đúng Method và truyền đối số tương ứng. Nó hữu ích khi method được chọn động hoặc khi kiểu trả về không thể proxy.

Có thể dùng overload:

- `linkTo(Method)`
- `linkTo(Method, Object...)`
- `linkTo(Class<?>, Method)`
- `linkTo(Class<?>, Method, Object...)`

Số đối số truyền vào phải khớp với chữ ký method khi dùng overload có tham số. Nếu method nằm trong controller có mapping cấp lớp, truyền controller class để builder kết hợp mapping lớp và method.

Đối với code thông thường, `methodOn` thường dễ đọc hơn vì không phải tra cứu method bằng reflection. Dùng reflection khi có lý do cụ thể như lựa chọn handler theo metadata hoặc xử lý kiểu trả về không proxy được.

## 7. Tạo link và gắn vào representation

Sau khi tạo link từ handler, gắn nó vào representation model để client có thể khám phá.

~~~java
@Component
public class OrderModelAssembler {

    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus(),
            order.getTotal()
        );

        Link self = linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        Link collection = linkTo(
            methodOn(OrderController.class).all()
        ).withRel("orders");

        var model = EntityModel.of(body, self, collection);

        if (order.canCancel()) {
            Link cancel = linkTo(
                methodOn(OrderController.class).cancel(order.getId())
            ).withRel("cancel");

            model.add(cancel);
        }

        return model;
    }
}
~~~

Assembler chịu trách nhiệm chuyển đổi entity sang DTO và tạo link từ handler mapping. Controller chỉ cần gọi assembler và trả về model. Cách này giúp các endpoint dùng chung một quy tắc tạo link và giữ controller gọn.

Link `cancel` chỉ xuất hiện khi trạng thái đơn hàng cho phép. Endpoint thực thi thao tác vẫn phải kiểm tra lại trạng thái và quyền truy cập khi nhận request; link phản ánh khả năng được công bố tại thời điểm tạo response.

## 8. Dùng handler method để mô tả affordance

Một Link cơ bản chỉ chứa relation và href. Nó không tự mô tả đầy đủ HTTP method, cấu trúc request body hoặc metadata đầu vào.

Spring HATEOAS cho phép gắn affordance vào link dựa trên một handler method khác. Ví dụ link self đến đơn hàng có thể công bố thao tác PUT cập nhật:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    Order order = service.findById(id);

    Link self = linkTo(
        methodOn(OrderController.class).one(id)
    ).withSelfRel()
     .andAffordance(afford(
        methodOn(OrderController.class).update(null, id)
    ));

    return EntityModel.of(toRepresentation(order), self);
}
~~~

Trong ví dụ, `one(...)` là handler GET tạo link self; `update(...)` là handler PUT được gắn như affordance. Spring HATEOAS phân tích mapping, HTTP method và kiểu request/response để media type hỗ trợ affordance có thể biểu diễn mô tả thao tác.

Cần import:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Affordance không phải một request được thực thi. Nó là metadata mô tả một thao tác liên quan đến link. HAL cơ bản chủ yếu biểu diễn href và relation; nếu client cần thông tin biểu mẫu hoặc đầu vào, hãy chọn media type có hỗ trợ affordance như HAL-FORMS và cấu hình hypermedia tương ứng.

## 9. Link builder dựa trên request hiện tại

WebMvcLinkBuilder sử dụng thông tin URI cơ sở từ request hiện tại để xây dựng link. Vì vậy, href có thể phản ánh scheme, host, port và context path mà request đang sử dụng.

Điều này hữu ích khi ứng dụng chạy dưới context path hoặc sau reverse proxy. Tuy nhiên, để tạo link công khai chính xác, forwarded header phải được xử lý theo cấu hình tin cậy. Trong Spring MVC, có thể đăng ký `ForwardedHeaderFilter`; Spring Boot có thể cấu hình filter này dưới dạng bean.

Chỉ tin forwarded header đến từ reverse proxy đáng tin cậy. Proxy cần loại bỏ hoặc ghi đè các header do client gửi vào trước khi chuyển request đến ứng dụng. Nếu không, client có thể tác động đến host hoặc scheme được đưa vào href.

Khi tạo link ngoài ngữ cảnh một request HTTP, không nên mặc định builder có thể biết base URI công khai. Với tác vụ nền hoặc tiến trình không có request context, hãy cung cấp URI cơ sở theo cấu hình hoặc dùng URI builder phù hợp với ngữ cảnh đó.

## 10. Kiểm thử link đến handler method

Nên kiểm thử ở hai mức:

- Unit test cho logic tạo link khi cần kiểm tra relation hoặc cách ghép giá trị.
- Integration test cho response HTTP để xác nhận mapping, request context, serializer và media type phối hợp đúng.

Ví dụ với MockMvc:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.endsWith("/orders/" + orderId)))
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Nếu controller mapping đổi, test sẽ phát hiện href không còn khớp. Với link hành động, kiểm tra cả điều kiện xuất hiện:

~~~java
mockMvc.perform(get("/orders/{id}", deliveredOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Với endpoint có request parameter, kiểm tra query string hoặc mở rộng URI template theo đúng hợp đồng. Với collection-valued request parameter, kiểm tra cả composite và non-composite nếu API hỗ trợ chúng.

Không nên khóa cứng scheme, host và port trong mọi test nếu chúng phụ thuộc môi trường. Kiểm tra path hoặc phần URI thuộc hợp đồng ổn định; tạo test riêng cho context path, forwarded header và địa chỉ công khai khi cần.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nối chuỗi URL thay vì tham chiếu handler | Link không theo mapping khi route thay đổi | Dùng `linkTo(methodOn(...))` |
| Nghĩ methodOn chạy logic controller | Có thể đặt nhầm tác dụng phụ trong biểu thức tạo link | Chỉ dùng lời gọi giả lập để ghi nhận mapping |
| Dùng handler trả kiểu không proxy được | Không tạo được proxy cho lời gọi method | Dùng kiểu trả về proxyable hoặc overload nhận Method |
| Truyền sai thứ tự path variable | URI được tạo sai hoặc không khớp mapping | Truyền đối số đúng thứ tự chữ ký |
| Mong request body xuất hiện trong href | URI bị thiết kế sai và có thể lộ dữ liệu | Chỉ dùng path/query parameter cho URI |
| Bỏ qua mapping cấp lớp | Link thủ công thiếu prefix hoặc context path | Dùng builder dựa trên controller mapping |
| Không kiểm tra request context | Link có thể sai base URI trong test hoặc tác vụ nền | Kiểm thử qua MockMvc và cấu hình base URI phù hợp |
| Nhầm affordance với request thực thi | Hiểu sai metadata như một hành động đã chạy | Xem affordance là mô tả thao tác |
| Công bố link là đã cấp quyền | Request cũ vẫn có thể được gửi | Kiểm tra quyền và trạng thái ở endpoint |

## 12. Quy trình áp dụng

Khi cần tạo link đến một handler method trong Spring MVC, hãy thực hiện theo trình tự:

1. Xác định controller class và handler method đích.
2. Kiểm tra mapping cấp lớp và cấp phương thức.
3. Dùng `methodOn(Controller.class).handler(...)` để ghi nhận lời gọi giả lập.
4. Truyền đúng giá trị cho path variable; cung cấp query parameter nếu chúng thuộc URI.
5. Dùng `linkTo(...)` để tạo builder và chọn relation bằng `withSelfRel()` hoặc `withRel(...)`.
6. Gắn link vào EntityModel, CollectionModel hoặc model riêng.
7. Dùng affordance khi cần mô tả thao tác gắn với link.
8. Kiểm thử href, relation, query string, context path và response HAL.

Tạo link từ handler method giúp URI được sinh từ cùng metadata mà Spring MVC dùng để ánh xạ request. Khi mapping thay đổi, link có thể đi theo cấu hình mới mà không cần sửa các chuỗi URL rải rác. Kết hợp cách làm này với relation ổn định, representation model và affordance sẽ giúp API công bố đường điều hướng cũng như các thao tác khả dụng theo một hợp đồng rõ ràng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [WebMvcLinkBuilderFactory API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilderFactory.html)
- [Spring MVC URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)

