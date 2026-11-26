# Link và request mapping

## Mục tiêu

Spring MVC dùng request mapping để quyết định controller method nào xử lý một HTTP request. Spring HATEOAS có thể đọc mapping đó để tạo URI cho Link, nhờ vậy các liên kết trong representation bám sát endpoint mà ứng dụng thực sự công bố. Hiểu mối quan hệ giữa mapping và link giúp tránh ghép URL thủ công, xử lý đúng path variable và query parameter, đồng thời biết khi nào cần affordance để mô tả HTTP method.

Sau bài học, bạn có thể:

- Giải thích cách mapping cấp controller và cấp method tạo thành đường dẫn endpoint.
- Dùng WebMvcLinkBuilder và methodOn để tạo link từ handler method.
- Truyền path variable và query parameter đúng với chữ ký method.
- Phân biệt URI trong Link với HTTP method và các điều kiện request mapping.
- Kết hợp affordance để mô tả thao tác và kiểm thử link trong response HAL.

## Request mapping quyết định endpoint

Trong Spring MVC, @RequestMapping và các annotation rút gọn như @GetMapping, @PostMapping, @PutMapping, @PatchMapping và @DeleteMapping xác định cách request được ánh xạ tới handler method.

Mapping có thể được khai báo ở hai cấp:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse findById(@PathVariable("orderId") UUID orderId) {
        // ...
    }
}
~~~

Mapping cấp class cung cấp prefix /api/orders. Mapping cấp method thêm /{orderId} và giới hạn HTTP method là GET. Endpoint kết hợp là GET /api/orders/{orderId}.

Request mapping có thể chứa nhiều điều kiện:

| Thuộc tính mapping | Vai trò |
|---|---|
| path hoặc value | Đường dẫn mà request phải khớp. |
| method | HTTP method như GET, POST hoặc PATCH. |
| params | Điều kiện dựa trên query parameter, ví dụ params = "view=full". |
| headers | Điều kiện dựa trên request header. |
| consumes | Media type của request body mà handler chấp nhận. |
| produces | Media type mà handler có thể trả về. |

Các điều kiện này giúp Spring chọn handler phù hợp. Ví dụ, hai method có thể dùng cùng path nhưng khác HTTP method hoặc khác params. Khi tạo hypermedia link, cần nhớ rằng URI là một phần của mapping; các điều kiện như HTTP method và media type có ý nghĩa riêng trong việc chọn handler.

## Spring HATEOAS đọc mapping để tạo link

Với Spring MVC, WebMvcLinkBuilder cung cấp linkTo(...) và methodOn(...). methodOn tạo proxy để tham chiếu controller method và ghi nhận các đối số. linkTo sử dụng thông tin method cùng mapping Spring MVC để tạo URI.

~~~java
import java.util.UUID;

import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

UUID orderId = UUID.fromString("4c6b8e70-4c1e-4f2f-a5b1-3d4e5f607182");

Link self = linkTo(methodOn(OrderController.class)
        .findById(orderId))
        .withSelfRel();
~~~

methodOn không thực thi phần thân findById, không gọi service và không truy vấn cơ sở dữ liệu. Nó chỉ tạo lời gọi proxy để Spring HATEOAS biết method nào được tham chiếu và các giá trị tham số tương ứng. linkTo sau đó kết hợp mapping cấp class, mapping cấp method và giá trị path variable để tạo href.

Nếu mapping được đổi từ /api/orders thành /api/v2/orders, link được tạo từ method vẫn theo mapping mới sau khi ứng dụng cập nhật. Đây là lợi ích quan trọng so với việc tự ghép chuỗi URL trong assembler.

Khi chỉ cần link tới controller mapping cấp class, có thể dùng linkTo(OrderController.class). Khi cần URI của một handler cụ thể, đặc biệt là handler có path variable hoặc query parameter, hãy tham chiếu method bằng methodOn(...).

## Path variable và query parameter

Các tham số trong chữ ký method có thể tham gia vào URI theo annotation gắn trên chúng.

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse findById(
            @PathVariable("orderId") UUID orderId) {
        // ...
    }

    @GetMapping
    CollectionModel<OrderModel> findAll(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        // ...
    }
}
~~~

Với path variable, truyền giá trị thực khi tham chiếu method:

~~~java
Link self = linkTo(methodOn(OrderController.class)
        .findById(orderId))
        .withSelfRel();
~~~

Giá trị orderId được đưa vào vị trí {orderId}. Với query parameter, các giá trị truyền vào method có thể được đưa vào query string:

~~~java
Link pendingPage = linkTo(methodOn(OrderController.class)
        .findAll("PENDING", 0, 20))
        .withRel("orders");
~~~

Link này đại diện cho một truy vấn cụ thể, tương đương đường dẫn collection với các tham số status, page và size. Hãy kiểm tra cách tham số tùy chọn hoặc null được xử lý trong phiên bản Spring HATEOAS đang dùng và trong chữ ký endpoint của ứng dụng.

Nếu client cần tự chọn các giá trị thay vì nhận một truy vấn đã cố định, công bố URI template:

~~~java
Link search = Link.of(
        "/api/orders{?status,page,size}",
        "search");
~~~

Template cho biết các biến truy vấn mà client có thể cung cấp. Các biến phải tương ứng với tham số thực tế của endpoint; không công bố sort hoặc filter nếu handler không hỗ trợ chúng. Khi ứng dụng có context path hoặc chạy sau reverse proxy, hãy tạo template từ mapping và ngữ cảnh URI phù hợp thay vì cố định một path có thể sai ở môi trường khác.

## Những tham số không trở thành URI

Không phải mọi tham số của handler đều được đưa vào href:

~~~java
@PostMapping(
        path = "/{orderId}/cancellation",
        consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<Void> cancel(
        @PathVariable UUID orderId,
        @RequestBody CancelOrderRequest request,
        @RequestHeader("X-Request-Id") String requestId) {
    // ...
    return ResponseEntity.noContent().build();
}
~~~

- orderId được dùng để tạo path.
- CancelOrderRequest là request body, không được serialize vào URI.
- X-Request-Id là request header, không phải path hay query parameter.
- consumes quy định media type của body mà endpoint chấp nhận; nó không phải một phần của href.

Khi tham chiếu method có request body để tạo link, có thể truyền null ở vị trí body:

~~~java
Link cancel = linkTo(methodOn(OrderController.class)
        .cancel(orderId, null, null))
        .withRel("cancel");
~~~

Các giá trị null ở đây chỉ để tham chiếu method mapping. methodOn không gửi request body hoặc request header. Client sẽ cung cấp body và header cần thiết khi thực hiện request thực tế. Không truyền dữ liệu bí mật hoặc payload vào URI.

## Một URI có thể phục vụ nhiều HTTP method

Request mapping có thể định nghĩa nhiều handler cùng một đường dẫn nhưng khác HTTP method:

~~~java
@GetMapping("/{orderId}")
OrderResponse findById(@PathVariable UUID orderId) {
    // ...
}

@PatchMapping("/{orderId}")
OrderResponse update(
        @PathVariable UUID orderId,
        @RequestBody UpdateOrderRequest request) {
    // ...
}
~~~

Cả hai handler đều dùng path /api/orders/{orderId}. Một URI đơn lẻ không nói cho client biết nên gửi GET hay PATCH. Trong HAL, Link thông thường chủ yếu công bố href và relation; relation như self hoặc edit không tự mang ý nghĩa HTTP method bắt buộc.

Nếu client cần biết method và dữ liệu đầu vào, dùng affordance. Spring HATEOAS cho phép gắn affordance được suy ra từ method mapping:

~~~java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class)
        .findById(orderId))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
                .update(orderId, null)));
~~~

Affordance mô tả thao tác PATCH dựa trên mapping và chữ ký method update. Khi được serialize bằng định dạng hỗ trợ affordance như HAL-FORMS, response có thể cung cấp thông tin về method và các thuộc tính đầu vào. HAL JSON cơ bản không tự biểu diễn đầy đủ form hoặc request schema chỉ vì link được tạo từ một method.

Đối với thao tác POST như hủy đơn hàng, có thể tạo link riêng và gắn affordance tương tự. Hãy chọn relation có ý nghĩa, ví dụ cancel, và công bố link khi trạng thái nghiệp vụ hiện tại cho phép. Server vẫn phải xác thực, phân quyền và kiểm tra trạng thái mới nhất khi nhận request.

## Mapping conditions và giới hạn của Link

Một request mapping có thể giới hạn theo params, headers, consumes hoặc produces. Những điều kiện này giúp Spring MVC chọn đúng handler nhưng không phải tất cả đều được biểu diễn trong URI:

- Điều kiện path được thể hiện trực tiếp trong href.
- Path variable được thay bằng giá trị khi tạo link cụ thể.
- Query parameter có thể được đưa vào href hoặc công bố dưới dạng URI template.
- HTTP method được xác định bởi handler và có thể được mô tả thêm qua affordance.
- consumes và produces liên quan đến media type của request/response; chúng không trở thành path segment.
- Điều kiện header có thể yêu cầu client gửi header phù hợp; href đơn thuần không mô tả đầy đủ yêu cầu này.

Ví dụ, nếu handler chỉ nhận request có header X-API-Version: 2, một link thông thường không tự bảo đảm client biết header đó. Hãy công bố yêu cầu qua tài liệu hoặc cơ chế affordance/profile thích hợp, đồng thời kiểm thử endpoint với header bắt buộc.

Không nên coi việc tạo được href là bằng chứng request chắc chắn được chấp nhận. Handler có thể từ chối request do sai HTTP method, media type, header, quyền truy cập hoặc trạng thái nghiệp vụ.

## Tổ chức controller links trong assembler

Assembler chuyển domain object thành representation và dùng method mapping để tạo các links nhất quán:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    EntityModel<OrderResponse> toModel(Order order) {
        EntityModel<OrderResponse> model =
                EntityModel.of(OrderResponse.from(order));

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());

        model.add(linkTo(methodOn(OrderController.class)
                .findAll(null, 0, 20)).withRel("collection"));

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null, null))
                    .withRel("cancel")
                    .andAffordance(afford(methodOn(OrderController.class)
                            .cancel(order.getId(), null, null))));
        }

        return model;
    }
}
~~~

Assembler dùng cùng mapping với controller để tạo self và collection links. Link cancel chỉ được thêm khi trạng thái đơn hàng cho phép; affordance bổ sung thông tin về thao tác POST. Nếu chữ ký controller thay đổi, các lời gọi methodOn trong assembler cần được cập nhật tương ứng, và compiler/test có thể giúp phát hiện sai lệch.

Không đặt quy tắc nghiệp vụ trong link builder. Service/domain quyết định đơn hàng có thể hủy hay không; assembler phản ánh quyết định đó bằng việc công bố hoặc ẩn link; controller tiếp nhận request và gọi use case để kiểm tra lại.

## Kiểm thử mapping và link

MockMvc có thể kiểm tra href trong response HAL để xác nhận link được tạo theo mapping:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{orderId}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/api/orders/" + orderId)))
        .andExpect(jsonPath("$._links.cancel.href")
                .value(endsWith("/api/orders/" + orderId + "/cancellation")));
~~~

Nên bổ sung các trường hợp:

- Đổi path ở cấp class hoặc method và xác nhận href phản ánh mapping mới.
- Xác minh path variable và query parameter được đưa vào đúng vị trí.
- Xác minh link action không xuất hiện khi trạng thái không cho phép.
- Xác minh affordance hoặc HAL-FORMS mô tả đúng method và input nếu client dựa vào chúng.
- Xác minh request thực tế vẫn bị từ chối khi sai header, media type, quyền hoặc trạng thái.

Nếu test chạy dưới context path hoặc reverse proxy, tránh phụ thuộc vào host tuyệt đối cố định. Có thể kiểm tra phần path hoặc cấu hình request context và forwarded headers để assertion khớp với môi trường.

## Những lỗi thường gặp

- **Ghép URL từ chuỗi:** mapping đổi có thể khiến link trong assembler lỗi thời. Dùng linkTo(methodOn(...)).
- **Nghĩ rằng methodOn gọi controller:** methodOn tạo proxy để ghi nhận method và đối số; nó không thực thi nghiệp vụ.
- **Cho rằng href chứa HTTP method:** URI xác định đích; method là một phần khác của request. Dùng affordance khi cần mô tả thao tác.
- **Đưa request body vào href:** body không thuộc URI. Truyền null khi tham chiếu mapping có @RequestBody.
- **Bỏ qua query parameter:** link có thể trỏ tới collection nhưng làm mất bộ lọc hoặc trang hiện tại. Truyền tham số hoặc công bố template đúng hợp đồng.
- **Coi consumes/produces là path:** đây là điều kiện media type, không phải thành phần đường dẫn.
- **Công bố action mà không kiểm tra trạng thái:** assembler lọc link theo trạng thái, nhưng endpoint vẫn phải xác minh lại khi request đến.
- **Bỏ qua điều kiện header hoặc proxy:** href có thể đúng nhưng request vẫn thất bại nếu client thiếu header hoặc absolute URI được tạo từ host nội bộ.

## Quy trình xây controller links

1. Xác định handler method và các điều kiện mapping của endpoint.
2. Dùng methodOn để tham chiếu method với đúng kiểu, thứ tự và giá trị tham số.
3. Dùng linkTo để tạo URI từ mapping; chọn relation phù hợp cho tài nguyên hoặc hành động.
4. Công bố query parameter cụ thể hoặc URI template tùy khả năng client cần khám phá.
5. Dùng affordance khi client cần biết HTTP method hoặc dữ liệu đầu vào; chọn media type hypermedia hỗ trợ affordance.
6. Kiểm thử href, relation, affordance và hành vi request với các điều kiện mapping thực tế.

Request mapping là nguồn định nghĩa endpoint trong Spring MVC; controller links là cách đưa các endpoint đó vào representation hypermedia. Khi tạo links từ method mapping và bổ sung affordance đúng chỗ, Spring HATEOAS giúp client khám phá URI và thao tác khả dụng theo hợp đồng API mà server công bố.
