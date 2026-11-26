# Building link từ method

## Mục tiêu

Trong REST API, link nên được tạo từ mapping của controller thay vì ghép chuỗi URL thủ công. Spring HATEOAS cung cấp WebMvcLinkBuilder để tham chiếu controller và handler method, đọc các annotation mapping cùng tham số đầu vào, rồi tạo URI cho link. Cách làm này giúp liên kết hypermedia bám theo cấu trúc endpoint khi đường dẫn hoặc tham số được thay đổi.

Sau bài học, bạn có thể:

- Tạo link từ class mapping và method mapping của Spring MVC.
- Dùng methodOn(...) để tham chiếu handler method mà không thực thi nghiệp vụ.
- Xử lý @PathVariable, query parameter và method có request body khi xây link.
- Gắn link self, collection và action vào representation bằng assembler.
- Kiểm thử URI được tạo từ method mapping và hiểu ảnh hưởng của proxy/context path.

## Vì sao nên build link từ method?

Giả sử controller khai báo:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        // ...
    }
}
~~~

Nếu assembler tự tạo URL bằng chuỗi "/api/orders/" + id, đường dẫn sẽ bị lặp lại ở nhiều nơi. Khi mapping đổi thành /api/v2/orders/{id}, các chuỗi thủ công có thể bị bỏ sót và response sẽ chứa link sai.

Khi build link từ method, Spring HATEOAS dựa trên mapping thực tế của controller. Assembler tham chiếu OrderController.findById(id) và thư viện ghép mapping cấp class, mapping cấp method cùng giá trị path variable để tạo URI. Khi mapping thay đổi, link builder đọc cấu hình mới thay vì dựa vào một chuỗi URL được sao chép ở nơi khác.

## WebMvcLinkBuilder và methodOn

Với ứng dụng Spring MVC, hai API thường dùng là:

- linkTo(...): bắt đầu xây dựng link từ controller, method hoặc URI builder.
- methodOn(...): tạo một proxy để tham chiếu handler method cùng các tham số của nó.

Ví dụ tạo link tới một đơn hàng:

~~~java
import java.util.UUID;

import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

UUID orderId = UUID.fromString("4c6b8e70-4c1e-4f2f-a5b1-3d4e5f607182");

Link selfLink = linkTo(methodOn(OrderController.class)
        .findById(orderId))
        .withSelfRel();
~~~

methodOn(OrderController.class) tạo proxy cho controller. Lời gọi findById(orderId) trên proxy cung cấp cho Spring HATEOAS thông tin về method và đối số. Nó không chạy phần thân method, không gọi service và không truy cập cơ sở dữ liệu. linkTo(...) dùng thông tin đó để tạo link; withSelfRel() gắn relation self.

Để tạo link tới collection, có thể tham chiếu handler method không có tham số:

~~~java
Link collectionLink = linkTo(methodOn(OrderController.class)
        .findAll())
        .withRel("collection");
~~~

Nếu chỉ cần URI gốc của controller, có thể dùng linkTo(OrderController.class). Cách này dựa vào mapping cấp class; khi cần đường dẫn tới một handler cụ thể và có tham số, hãy tham chiếu method bằng methodOn(...).

## Mapping được ghép như thế nào?

Spring MVC có thể khai báo mapping ở cấp class và cấp method:

~~~java
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        // ...
    }
}
~~~

Đường dẫn cuối cùng được ghép từ /api/orders và /{id}. Khi gọi:

~~~java
linkTo(methodOn(OrderController.class).findById(orderId))
~~~

Spring HATEOAS đọc các mapping đó và thay {id} bằng giá trị orderId. Vì vậy, link được tạo tương ứng với endpoint mà Spring MVC đã đăng ký.

| Thành phần | Vai trò khi build link |
|---|---|
| @RequestMapping trên controller | Cung cấp phần mapping chung của tài nguyên. |
| @GetMapping, @PostMapping, ... | Xác định mapping của handler method. |
| @PathVariable | Đưa giá trị tham số vào path segment tương ứng. |
| @RequestParam | Mô tả query parameter của endpoint. |
| @RequestBody | Mô tả body của request; dữ liệu body không trở thành một phần của URI. |

Tham số truyền vào methodOn cần tương ứng với chữ ký method. Với @PathVariable, truyền giá trị thực để tạo URI cụ thể. Với tham số query tùy chọn, có thể truyền giá trị thích hợp theo hợp đồng endpoint; nếu cần công bố biến tùy chọn thay vì một URI đã điền giá trị, hãy dùng URI template và templated Link.

## Xây link cho action method

Link action cũng được tạo từ method mapping. Ví dụ đơn hàng đang chờ có thể được hủy:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        // ...
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @RequestBody CancelOrderRequest request) {
        // ...
        return ResponseEntity.noContent().build();
    }
}
~~~

Assembler có thể tạo link cancel từ method:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    EntityModel<OrderResponse> toModel(Order order) {
        EntityModel<OrderResponse> model =
                EntityModel.of(OrderResponse.from(order));

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null))
                    .withRel("cancel"));
        }

        return model;
    }
}
~~~

Đối số null ở vị trí CancelOrderRequest chỉ phục vụ việc tham chiếu method để lấy mapping. methodOn không gọi controller thật và không gửi request body. Body được client cung cấp sau này khi thực hiện POST tới link. Server vẫn phải kiểm tra quyền và trạng thái đơn hàng khi nhận request; sự xuất hiện của link không cấp quyền thực thi hành động.

Nếu một method nhận nhiều tham số, hãy truyền đúng thứ tự và kiểu tham số theo chữ ký. Chỉ các tham số có ý nghĩa đối với URI mới ảnh hưởng đến đường dẫn hoặc query string; @RequestBody không được serialize vào href.

## Link từ method có query parameter

Một handler có thể nhận query parameter:

~~~java
@GetMapping
CollectionModel<OrderModel> findAll(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
~~~

Khi đã có giá trị cụ thể, có thể tham chiếu method để tạo link tới một truy vấn cụ thể:

~~~java
Link pendingOrders = linkTo(methodOn(OrderController.class)
        .findAll("PENDING", 0, 20))
        .withRel("orders");
~~~

Nếu muốn client tự chọn status, page và size, không nên đóng cứng các giá trị mặc định vào link. Hãy công bố URI template:

~~~java
Link search = Link.of(
        "/api/orders{?status,page,size}",
        "search");
~~~

Trong ứng dụng thực tế, href template nên được tạo dựa trên mapping và context path của ứng dụng hoặc một cơ chế URI builder phù hợp, tránh lặp lại path literal. Tên biến trong template phải khớp với tham số endpoint thực sự hỗ trợ.

## Kết hợp link builder với RepresentationModelAssembler

Assembler là nơi thích hợp để chuyển domain object thành representation và gắn các links được tạo từ controller method. Ví dụ:

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
        EntityModel<OrderResponse> model =
                EntityModel.of(OrderResponse.from(order));

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());

        model.add(linkTo(methodOn(OrderController.class)
                .findAll(null, 0, 20)).withRel("collection"));

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null)).withRel("cancel"));
        }

        return model;
    }
}
~~~

toModel tạo links theo trạng thái của từng đơn hàng. Link self luôn trỏ tới tài nguyên; link collection cho phép quay lại danh sách; link cancel chỉ xuất hiện khi nghiệp vụ hiện tại cho phép hủy. Quy tắc nghiệp vụ quyết định link nào được công bố, còn link builder chỉ tạo URI dựa trên mapping.

Với collection, toCollectionModel(...) gọi toModel(...) cho từng phần tử. Nhờ vậy, mỗi item có links phù hợp với trạng thái riêng, còn controller có thể bổ sung link ở cấp collection sau khi assembler chuyển danh sách.

## Context path, host và reverse proxy

Link builder hoạt động trong ngữ cảnh web request để tạo URI phù hợp với ứng dụng đang xử lý request. Trong môi trường có context path, host public khác host nội bộ hoặc reverse proxy, cấu hình forwarded headers cần chính xác để link không trỏ nhầm địa chỉ.

Ví dụ, ứng dụng chạy nội bộ tại http://service:8080 nhưng public qua https://api.example.com/orders. Nếu proxy chuyển tiếp request mà ứng dụng không nhận diện đúng forwarded host, scheme hoặc prefix, absolute link có thể phản ánh địa chỉ nội bộ. Hãy cấu hình proxy và forwarded header strategy theo môi trường triển khai; không sửa link bằng cách nối chuỗi host cố định trong assembler.

Với Spring WebFlux, Spring HATEOAS cung cấp WebFluxLinkBuilder cho ngữ cảnh reactive. Hãy dùng link builder phù hợp với web stack của ứng dụng; ví dụ trong bài sử dụng Spring MVC và WebMvcLinkBuilder.

## Kiểm thử link được build từ method

Kiểm thử endpoint bằng MockMvc giúp xác nhận link cuối cùng phản ánh mapping đã khai báo:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value("http://localhost/api/orders/" + orderId))
        .andExpect(jsonPath("$._links.cancel.href")
                .value("http://localhost/api/orders/" + orderId + "/cancellation"));
~~~

Địa chỉ tuyệt đối trong assertion phụ thuộc cấu hình MockMvc, servlet context và forwarded headers của test. Nếu môi trường test dùng base URL khác, hãy cấu hình request context hoặc kiểm tra phần path phù hợp thay vì hard-code host không ổn định.

Nên có thêm các kiểm thử:

- Đổi mapping cấp class hoặc cấp method và xác nhận link được tạo theo mapping mới.
- Kiểm tra giá trị @PathVariable được đưa vào đúng vị trí.
- Kiểm tra link action chỉ xuất hiện khi trạng thái cho phép.
- Kiểm tra query parameter hoặc template tương ứng với hợp đồng endpoint.
- Kiểm tra absolute URL khi ứng dụng chạy dưới context path hoặc sau reverse proxy.

## Những lỗi thường gặp

- **Ghép URL bằng chuỗi trong assembler:** mapping đổi có thể làm link cũ sai. Dùng linkTo(methodOn(...)).
- **Nghĩ rằng methodOn thực thi controller:** methodOn tạo proxy để ghi nhận method và tham số; nó không gọi service hay xử lý request.
- **Truyền sai tham số method:** số lượng, thứ tự hoặc kiểu tham số không khớp chữ ký có thể làm link không chính xác.
- **Đưa request body vào href:** body không thuộc URI. Truyền null khi chỉ cần tham chiếu mapping có @RequestBody; client gửi body khi thực hiện request.
- **Công bố action mà không kiểm tra trạng thái:** assembler nên lọc link theo trạng thái, nhưng endpoint vẫn phải kiểm tra lại quyền và nghiệp vụ.
- **Đóng cứng query mặc định khi client cần lựa chọn:** dùng templated Link để công bố biến truy vấn.
- **Bỏ qua forwarded headers:** link tuyệt đối có thể chứa host, scheme hoặc prefix nội bộ.
- **Dùng link builder sai web stack:** chọn WebMvcLinkBuilder cho Spring MVC và builder tương ứng cho WebFlux.

## Quy trình building link từ method

1. Xác định controller và handler method đích của link.
2. Dùng methodOn(Controller.class) để tham chiếu method với các tham số đúng chữ ký.
3. Dùng linkTo(...) để tạo link từ mapping và giá trị path/query tương ứng.
4. Gắn relation bằng withSelfRel() hoặc withRel(...), rồi thêm metadata nếu cần.
5. Đưa link vào representation trong assembler; chỉ công bố action phù hợp với trạng thái hiện tại.
6. Kiểm thử href, path variable, query parameter, action link và cấu hình host/proxy.

Building link từ method giúp URI trong hypermedia bám sát mapping thật của Spring MVC. Khi assembler dùng linkTo(methodOn(...)), controller giữ trách nhiệm định nghĩa endpoint, assembler giữ trách nhiệm mô tả tài nguyên và client nhận được liên kết có thể tiến hóa cùng cấu trúc API.
