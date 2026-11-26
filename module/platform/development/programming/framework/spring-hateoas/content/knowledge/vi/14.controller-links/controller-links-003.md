# Link cho GET trong Spring HATEOAS

Trong REST API, client thường cần một cách để khám phá endpoint đọc tài nguyên. Thay vì tự ghép đường dẫn từ mã định danh hoặc ghi cứng URL trong ứng dụng, server có thể công bố các liên kết trỏ tới những method `GET` của controller. Spring HATEOAS hỗ trợ tạo các liên kết này dựa trên mapping Spring MVC bằng `WebMvcLinkBuilder`, `linkTo(...)` và `methodOn(...)`.

Một GET link có thể trỏ tới chính tài nguyên hiện tại bằng relation `self`, tới collection bằng relation nghiệp vụ như `orders`, hoặc tới tài nguyên liên quan như `customer`. Khi được serialize thành HAL, client đọc relation và `href` để tiếp tục điều hướng. Bài học này tập trung vào cách tạo link cho GET endpoint, xử lý query parameter, tổ chức link trong controller/assembler và kiểm thử response.

## 1. GET link là gì?

GET link là một hypermedia link dẫn tới URI mà client dùng để truy xuất một representation bằng HTTP `GET`. Ví dụ, representation của đơn hàng có thể công bố:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    },
    "orders": {
      "href": "/orders"
    }
  }
}
```

Client có thể gửi GET tới `/orders/42` để đọc đơn hàng, theo link `customer` để đọc khách hàng liên quan hoặc theo link `orders` để quay lại collection.

Trong HAL cơ bản, một link thường công bố relation và URI đích. Nó không phải lúc nào cũng mang trường HTTP method. Việc link trỏ tới endpoint GET cần được xác định bởi thiết kế tài nguyên, mapping và hợp đồng API. Nếu cần mô tả thêm thao tác hoặc affordance, có thể xem xét các khả năng nâng cao của Spring HATEOAS và media type hỗ trợ chúng.

## 2. Vì sao tạo link từ mapping GET của controller?

Nếu client tự xây dựng URI như `"/orders/" + id`, nó phải biết cấu trúc đường dẫn của server. Khi server thay đổi mapping, client có thể tiếp tục gọi URL cũ. Link do server công bố giúp client lấy URI hiện hành từ response.

Trong ứng dụng Spring MVC, `WebMvcLinkBuilder` tạo link dựa trên annotation mapping của controller. Cách này đem lại một số lợi ích:

- Giảm việc lặp lại đường dẫn trong nhiều nơi của ứng dụng.
- Liên kết tự phản ánh mapping khi path hoặc path variable thay đổi.
- Có thể truyền giá trị path variable và query parameter để tạo URI cụ thể.
- Giúp controller hoặc assembler mô tả đường điều hướng bằng relation có ý nghĩa.
- Dễ kiểm thử link được công bố cùng representation.

Tạo link từ mapping không tự bảo đảm client tương thích. Client vẫn phải đọc relation và dùng `href`; nếu client bỏ qua link và tiếp tục ghép URI thủ công, nó vẫn phụ thuộc vào cấu trúc URL.

## 3. Khai báo GET endpoint trong controller

Giả sử API quản lý đơn hàng có endpoint đọc một đơn hàng theo ID:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderView getOrder(@PathVariable UUID id) {
        Order order = orderService.getRequired(id);
        return new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );
    }
}
```

`@RequestMapping("/orders")` khai báo path cơ sở của controller; `@GetMapping("/{id}")` khai báo endpoint đọc một item. URI kết hợp có dạng `/orders/{id}`.

Để tạo link tới method này, cần tham chiếu đúng controller và truyền tham số tương ứng với mapping. Spring HATEOAS sẽ sử dụng thông tin annotation để dựng URI.

## 4. Tạo self link cho GET endpoint bằng linkTo và methodOn

Hai phương thức thường dùng trong Spring MVC là:

- `methodOn(Controller.class).method(arguments...)` tạo tham chiếu tới method controller và các tham số cần thiết để phân tích mapping.
- `linkTo(...)` chuyển tham chiếu đó thành builder để tạo URI và gắn relation.

Ví dụ tạo self link tới GET endpoint của đơn hàng:

```java
Link self = linkTo(methodOn(OrderController.class).getOrder(orderId))
        .withSelfRel();
```

Sau đó thêm link vào model:

```java
OrderView view = orderService.getOrderView(orderId);

EntityModel<OrderView> model = EntityModel.of(
        view,
        linkTo(methodOn(OrderController.class).getOrder(orderId)).withSelfRel()
);
```

`methodOn` không thực thi method `getOrder` và không truy vấn database. Nó tạo một tham chiếu để Spring HATEOAS đọc metadata mapping. Vì vậy, không dùng `methodOn` như một cách gọi service hoặc thực hiện nghiệp vụ.

`withSelfRel()` gắn relation chuẩn `self`, nghĩa là URI được tạo trỏ tới chính tài nguyên đang được biểu diễn. Với link tới tài nguyên khác, hãy dùng relation phù hợp như `customer` hoặc relation riêng đã được định nghĩa trong hợp đồng API.

## 5. Tạo link GET cho collection

Controller thường có endpoint GET trả về collection:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> listOrders() {
    List<Order> orders = orderService.findAll();

    List<EntityModel<OrderView>> items = orders.stream()
            .map(order -> {
                OrderView view = new OrderView(
                        order.getId(),
                        order.getStatus().name(),
                        order.getTotal()
                );

                return EntityModel.of(
                        view,
                        linkTo(methodOn(OrderController.class)
                                .getOrder(order.getId())).withSelfRel()
                );
            })
            .toList();

    return CollectionModel.of(
            items,
            linkTo(methodOn(OrderController.class).listOrders()).withSelfRel()
    );
}
```

Trong ví dụ, mỗi item có self link trỏ tới GET endpoint chi tiết, còn `CollectionModel` có self link trỏ tới GET endpoint danh sách. Hai link thuộc hai representation khác nhau.

Với ứng dụng lớn, nên chuyển phần tạo `EntityModel<OrderView>` vào `RepresentationModelAssembler`. Khi đó assembler tạo self link cho từng item, còn controller hoặc thành phần chuyên trách bổ sung link cho collection. Không thêm self link của item lần thứ hai sau khi assembler đã tạo.

## 6. Tạo link GET tới tài nguyên liên quan

Một representation có thể công bố link tới GET endpoint của tài nguyên liên quan. Ví dụ đơn hàng có khách hàng sở hữu đơn:

```java
@GetMapping("/{id}")
EntityModel<OrderView> getOrder(@PathVariable UUID id) {
    Order order = orderService.getRequired(id);

    OrderView view = new OrderView(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
    );

    return EntityModel.of(
            view,
            linkTo(methodOn(OrderController.class).getOrder(id)).withSelfRel(),
            linkTo(methodOn(CustomerController.class)
                    .getCustomer(order.getCustomerId())).withRel("customer")
    );
}
```

`customer` là relation mô tả quan hệ giữa đơn hàng và khách hàng. Controller đích cần có GET mapping tương ứng, chẳng hạn `@GetMapping("/{id}")` trong `CustomerController`.

Relation cần có ngữ nghĩa ổn định và dễ hiểu. Dùng relation chuẩn khi có quan hệ phù hợp; nếu dùng relation riêng như `customer`, hãy định nghĩa nó trong hợp đồng API và giữ cách dùng nhất quán.

## 7. Link GET có query parameter

GET endpoint thường nhận query parameter để lọc, tìm kiếm hoặc phân trang. Spring HATEOAS có thể tạo link bằng cách truyền giá trị query parameter vào method controller.

Ví dụ controller tìm đơn hàng theo trạng thái:

```java
@GetMapping("/search")
CollectionModel<EntityModel<OrderView>> searchOrders(
        @RequestParam(required = false) OrderStatus status) {
    // Tìm các đơn hàng theo status.
}
```

Tạo link tới kết quả tìm kiếm:

```java
Link pendingOrders = linkTo(methodOn(OrderController.class)
        .searchOrders(OrderStatus.PENDING))
        .withRel("pending-orders");
```

Giá trị truyền vào `methodOn` được dùng để dựng URI theo mapping và tham số của method. Nếu tham số tùy chọn là `null`, cách biểu diễn query parameter phụ thuộc vào mapping và quy tắc URI builder; hãy kiểm tra URI thực tế trong response.

Nếu API cho phép client tự điền giá trị tìm kiếm, một URI template có thể phù hợp hơn, ví dụ `/orders/search{?status}`. Khi server đã biết giá trị cụ thể như `PENDING`, link cụ thể thường dễ dùng hơn.

Với nhiều tham số lọc, sắp xếp và phân trang, cần giữ đầy đủ ngữ cảnh truy vấn trong link điều hướng. Tránh tạo link chỉ giữ `page` mà bỏ mất `status` hoặc `sort`, vì client có thể chuyển sang một tập kết quả khác.

## 8. GET link và ý nghĩa HTTP GET

HTTP GET được thiết kế để truy xuất representation và có ngữ nghĩa an toàn (safe): request không yêu cầu server thực hiện thay đổi trạng thái nghiệp vụ. GET cũng là phương thức idempotent: gửi lại cùng một request không làm thay đổi kết quả nghiệp vụ do chính request đó yêu cầu.

Vì vậy, các link dùng để đọc tài nguyên, xem collection, tìm kiếm hoặc lấy trang tiếp theo thường dẫn tới GET endpoint. Những hành động thay đổi dữ liệu như tạo đơn, hủy đơn, duyệt đơn hoặc thanh toán cần endpoint và phương thức HTTP phù hợp với semantics của chúng.

Không nên khai báo một endpoint thay đổi dữ liệu bằng `@GetMapping` chỉ để việc điều hướng trông đơn giản. Client, proxy và cache có thể giả định GET là thao tác đọc và tự động gọi lại hoặc cache response. Hành động làm thay đổi trạng thái cần dùng phương thức phù hợp, chẳng hạn POST, PUT, PATCH hoặc DELETE tùy hợp đồng.

Một HAL link cơ bản không nhất thiết chứa HTTP method. Vì vậy, relation `cancel` trong HAL thuần không tự cho client biết phải gửi POST hay DELETE. Nếu cần mô tả affordance hoặc thao tác phong phú hơn, hãy đánh giá affordance trong Spring HATEOAS và media type như HAL-FORMS, đồng thời duy trì tài liệu hợp đồng về method và payload.

## 9. Tổ chức link GET trong assembler

Khi nhiều controller cần tạo representation cho cùng một loại tài nguyên, `RepresentationModelAssembler` giúp gom logic chuyển đổi và tạo link vào một nơi.

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        UUID id = order.getId();
        OrderView view = new OrderView(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).getOrder(id)).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .getCustomer(order.getCustomerId())).withRel("customer")
        );
    }
}
```

Controller sử dụng assembler:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> listOrders() {
        CollectionModel<EntityModel<OrderView>> collection =
                assembler.toCollectionModel(orderService.findAll());

        collection.add(linkTo(methodOn(OrderController.class).listOrders())
                .withSelfRel());
        return collection;
    }
}
```

Assembler tạo self link và customer link cho từng item. Controller tạo self link cho collection. Phân chia này giúp tránh lặp code và giảm nguy cơ một item nhận nhiều self link.

## 10. Kiểm tra URI công khai và môi trường triển khai

`WebMvcLinkBuilder` thường dựa vào request hiện tại để tạo URI. Nếu ứng dụng chạy sau reverse proxy, ingress hoặc load balancer, request nội bộ có thể dùng host và port khác với địa chỉ công khai mà client truy cập.

Hãy kiểm tra link được sinh ra có đúng scheme, host, port, context path và path công khai hay không. Cấu hình forwarded headers chỉ nên tin các proxy được kiểm soát; không tin header forwarded từ client không đáng tin cậy vì chúng có thể làm ứng dụng tạo URI giả mạo.

Với môi trường phát triển, link có thể là URI tương đối hoặc tuyệt đối tùy cấu hình và ngữ cảnh request. Kiểm thử không nên giả định host cố định nếu host không phải một phần của hợp đồng. Nếu hợp đồng yêu cầu URI tuyệt đối, hãy kiểm tra host công khai trong môi trường tích hợp phù hợp.

## 11. Kiểm thử link GET bằng MockMvc

Kiểm thử HTTP nên xác nhận response có status phù hợp, media type HAL và link trỏ tới đúng endpoint GET.

Ví dụ kiểm tra self link của item:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/orders/" + orderId)));
```

Kiểm tra link collection và link item:

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

`orders` cần khớp relation collection được cấu hình trong ứng dụng. Ngoài việc kiểm tra `href` tồn tại, hãy xác nhận URI item khác nhau cho các item khác nhau và từng URI thực sự gọi được bằng GET.

Một bài kiểm thử traversal có thể đọc `href` từ response HAL rồi gọi URI đó bằng MockMvc hoặc HTTP client. Cách này xác nhận client có thể điều hướng dựa trên link server cung cấp thay vì dựa vào đường dẫn được viết sẵn trong test client.

## 12. Các lỗi thường gặp khi tạo link GET

**Tự ghép URI bằng chuỗi.** Đường dẫn bị lặp ở nhiều nơi và dễ sai khi mapping thay đổi. Dùng `linkTo(methodOn(...))` khi tạo link từ Spring MVC controller.

**Dùng sai relation.** Link tới tài nguyên hiện tại nên dùng `self`; link tới collection hoặc tài nguyên liên quan cần relation có ngữ nghĩa phù hợp.

**Nhầm link item với link collection.** Self link của collection trỏ tới danh sách; self link của từng item trỏ tới endpoint chi tiết của item đó.

**Thêm self link nhiều lần.** Nếu assembler đã tạo self link cho từng item, controller chỉ nên bổ sung link cấp collection hoặc relation khác.

**Dùng GET để thay đổi trạng thái.** GET cần giữ semantics đọc an toàn và idempotent. Hành động thay đổi dữ liệu phải dùng HTTP method phù hợp.

**Cho rằng HAL link mô tả đầy đủ method và payload.** Link cơ bản chủ yếu cung cấp relation và URI; hợp đồng thao tác cần được mô tả bổ sung khi client cần.

**Không kiểm tra URI qua proxy.** Link có thể chứa host nội bộ hoặc scheme sai. Kiểm thử cấu hình forwarded headers và địa chỉ công khai.

## 13. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng API đơn hàng với các GET link sau:

1. Tạo endpoint GET chi tiết `/{id}` và công bố self link từ mapping controller.
2. Tạo endpoint GET collection và công bố self link cho collection.
3. Đảm bảo mỗi item trong collection có self link riêng.
4. Thêm relation `customer` tới GET endpoint của khách hàng liên quan.
5. Tạo link tìm kiếm GET với query parameter trạng thái.
6. Chuyển logic tạo representation và link item vào `RepresentationModelAssembler`.
7. Kiểm tra response HAL có đúng `_links` và `_embedded`.
8. Dùng một client thử nghiệm đọc relation và gọi URI nhận được.
9. Thay đổi mapping GET chi tiết, chạy lại kiểm thử và xác nhận link được cập nhật.
10. Xác nhận các endpoint GET chỉ đọc dữ liệu và không thực hiện thay đổi trạng thái nghiệp vụ.

Bạn đã nắm được cách tạo link cho GET khi có thể dùng `WebMvcLinkBuilder` để tạo URI từ mapping, chọn relation đúng cho item và collection, đưa query parameter vào link, tổ chức logic trong assembler và kiểm thử HAL qua HTTP. Khi client thực sự đi theo `href`, API có thể thay đổi cấu trúc URI mà ít làm client phụ thuộc vào đường dẫn nội bộ.
