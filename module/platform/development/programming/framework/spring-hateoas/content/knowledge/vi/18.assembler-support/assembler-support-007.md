# Kết hợp RepresentationModelAssembler với PagedModel

Khi một API trả về danh sách có phân trang, mỗi phần tử thường cần một representation riêng với các liên kết hypermedia, còn toàn bộ trang cần metadata và liên kết điều hướng như trang đầu, trang trước, trang hiện tại, trang tiếp theo và trang cuối. Spring HATEOAS kết hợp hai trách nhiệm này bằng **RepresentationModelAssembler** và **PagedResourcesAssembler**, với kết quả là **PagedModel**.

RepresentationModelAssembler chuyển từng đối tượng domain thành representation có link. PagedResourcesAssembler nhận một trang Spring Data Page, gọi assembler cho từng phần tử, rồi tạo PagedModel chứa nội dung đã chuyển đổi, metadata phân trang và các link cấp trang. Nhờ vậy, controller không cần tự lặp qua danh sách, tự tính tổng số trang hoặc ghép URL cho từng trang.

## 1. Hai cấp độ biểu diễn trong một phản hồi phân trang

Một phản hồi phân trang có hai cấp độ hypermedia khác nhau:

1. **Cấp phần tử:** mỗi đơn hàng được biểu diễn bằng DTO hoặc representation model, có link self và các link liên quan hoặc hành động khả dụng.
2. **Cấp trang:** toàn bộ kết quả được bọc trong PagedModel, có metadata và link điều hướng phân trang.

Sơ đồ luồng dữ liệu:

~~~mermaid
flowchart TD
    A["Repository / Service"] --> B["Page<Order>"]
    B --> C["PagedResourcesAssembler"]
    C --> D["RepresentationModelAssembler.toModel()"]
    D --> E["EntityModel<OrderDto> cho từng Order"]
    E --> F["PagedModel<EntityModel<OrderDto>>"]
    F --> G["HAL JSON: _embedded, _links, page"]
~~~

RepresentationModelAssembler không tự tạo metadata phân trang. Nó chỉ chịu trách nhiệm chuyển đổi từng phần tử. PagedResourcesAssembler xử lý Page và kết hợp các phần tử đã chuyển đổi với metadata cùng các link điều hướng.

## 2. Phân biệt các kiểu dữ liệu

Các kiểu tham gia vào quy trình có vai trò riêng:

| Kiểu | Vai trò |
|---|---|
| Page&lt;T&gt; | Kết quả phân trang từ Spring Data, chứa nội dung trang và thông tin tổng kết quả |
| RepresentationModelAssembler&lt;T, D&gt; | Chuyển một đối tượng T thành representation D có thể mang link |
| EntityModel&lt;T&gt; | Bọc một nội dung đơn cùng các link |
| CollectionModel&lt;D&gt; | Biểu diễn một tập hợp representation và link cấp tập hợp |
| PagedResourcesAssembler&lt;T&gt; | Chuyển Page&lt;T&gt; thành PagedModel, có thể dùng RepresentationModelAssembler để chuyển từng phần tử |
| PagedModel&lt;D&gt; | Representation cho trang, gồm nội dung D, PageMetadata và link phân trang |

Tên PagedResourcesAssembler vẫn được giữ trong Spring Data Web, trong khi kiểu kết quả hiện đại của Spring HATEOAS là PagedModel. Vì vậy, tên lớp assembler có chữ Resources không có nghĩa controller cần trả về một kiểu Resources cũ.

## 3. Tạo RepresentationModelAssembler cho từng phần tử

Ví dụ hệ thống quản lý đơn hàng có domain object Order. API muốn công bố ID, trạng thái và tổng tiền, đồng thời thêm link self và link hủy khi đơn hàng còn ở trạng thái cho phép.

DTO:

~~~java
import java.math.BigDecimal;

public record OrderDto(
    Long id,
    String status,
    BigDecimal total
) {}
~~~

Assembler:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    private static final String CANCEL_REL =
        "https://api.example.com/rels/cancel";

    private final OrderMapper mapper;

    public OrderModelAssembler(OrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = mapper.toDto(order);
        EntityModel<OrderDto> model = EntityModel.of(dto);

        model.add(
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(order.getId()))
                    .withRel(CANCEL_REL)
            );
        }

        return model;
    }
}
~~~

Phương thức toModel nhận một Order và trả về EntityModel&lt;OrderDto&gt;. Nó thực hiện ba công việc:

- Chuyển domain object thành DTO để kiểm soát dữ liệu công khai.
- Thêm link self trỏ đến endpoint đọc chính đơn hàng.
- Thêm link hành động theo trạng thái nghiệp vụ.

Assembler của phần tử chỉ tạo link gắn với từng đơn hàng. Link điều hướng cấp trang được PagedResourcesAssembler tạo ở cấp ngoài cùng, dựa trên Page và request hiện tại. Giữ hai trách nhiệm riêng giúp tránh lặp link phân trang bên trong từng đơn hàng.

Assembler không thực hiện truy vấn phân trang và không tính totalElements. Những dữ liệu đó thuộc Page được service/repository trả về.

## 4. Dùng PagedResourcesAssembler trong controller

Trong ứng dụng Spring MVC có Spring Data Web, PagedResourcesAssembler có thể được nhận như một tham số của controller. Spring cung cấp instance được cấu hình để hiểu Pageable và request hiện tại.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
    }

    @GetMapping
    public PagedModel<EntityModel<OrderDto>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.findAll(pageable);

        return pagedAssembler.toModel(page, orderModelAssembler);
    }

    @GetMapping("/{id}")
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        return orderModelAssembler.toModel(orderService.findById(id));
    }
}
~~~

Lời gọi quan trọng là:

~~~java
pagedAssembler.toModel(page, orderModelAssembler)
~~~

Nó nhận Page&lt;Order&gt; và RepresentationModelAssembler&lt;Order, EntityModel&lt;OrderDto&gt;&gt;. Kết quả có kiểu PagedModel&lt;EntityModel&lt;OrderDto&gt;&gt;.

Quá trình chuyển đổi:

1. PagedResourcesAssembler đọc nội dung và metadata từ Page&lt;Order&gt;.
2. Nó gọi orderModelAssembler.toModel(order) cho từng phần tử trong trang.
3. Mỗi Order trở thành EntityModel&lt;OrderDto&gt; có link riêng.
4. Nó tạo PageMetadata từ thông tin trang.
5. Nó tạo link điều hướng trang theo Pageable và request hiện tại.
6. Nó trả về PagedModel chứa tất cả thành phần trên.

Controller vì thế chỉ cần lấy Page từ service rồi giao việc dựng representation phân trang cho assembler.

## 5. Link của phần tử và link của trang

Một điểm quan trọng là link do hai assembler tạo ra có phạm vi khác nhau.

| Link | Được tạo bởi | Ý nghĩa |
|---|---|---|
| self của đơn hàng | OrderModelAssembler | Mở tài nguyên đơn hàng cụ thể |
| cancel của đơn hàng | OrderModelAssembler | Công bố khả năng hủy đơn hàng đó |
| first của trang | PagedResourcesAssembler | Mở trang đầu của tập kết quả |
| prev của trang | PagedResourcesAssembler | Mở trang trước |
| self của trang | PagedResourcesAssembler | Mở lại trang hiện tại |
| next của trang | PagedResourcesAssembler | Mở trang tiếp theo |
| last của trang | PagedResourcesAssembler | Mở trang cuối |

Không nên nhầm link self của từng phần tử với link self của trang. Trong một phản hồi HAL, link self của đơn hàng nằm bên trong phần tử được nhúng; link self của trang nằm ở cấp ngoài cùng.

Ví dụ cấu trúc rút gọn:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "total": 1250000,
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/42"
          },
          "https://api.example.com/rels/cancel": {
            "href": "https://api.example.com/orders/42/cancel"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20"
    },
    "last": {
      "href": "https://api.example.com/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Ví dụ chỉ hiển thị một phần tử để minh họa. Tên relation trong _embedded phụ thuộc cấu hình relation của kiểu representation. API nên xác định tên collection ổn định để máy khách có thể đọc đúng danh sách phần tử.

## 6. Giữ filter, sort và page parameters trong link

Một trang có thể được tạo từ nhiều tham số truy vấn:

~~~http
GET /orders?status=PAID&page=0&size=20&sort=createdAt,desc
~~~

Các link phân trang cần giữ ngữ cảnh lọc và sắp xếp để khi máy khách đi đến trang tiếp theo, nó vẫn duyệt cùng tập kết quả.

Khi PagedResourcesAssembler được sử dụng trong request Spring MVC với Pageable được resolve từ Spring Data Web, nó tạo link dựa trên request hiện tại và pageable. Với filter tùy chỉnh, reverse proxy hoặc custom resolver, cần kiểm thử URI thực tế để bảo đảm các tham số vẫn được giữ đúng.

Ví dụ controller có bộ lọc:

~~~java
@GetMapping
public PagedModel<EntityModel<OrderDto>> search(
        @RequestParam(required = false) String status,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.search(status, pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
~~~

Nếu gọi:

~~~http
GET /orders?status=PAID&page=0&size=20
~~~

link next cần giữ status=PAID và size=20, chỉ thay đổi chỉ số page. Máy khách nên theo link do server cung cấp thay vì tự tạo URI bằng cách tăng page.

## 7. Cấu hình Pageable mặc định và giới hạn page size

Có thể dùng @PageableDefault để định nghĩa page size và sort mặc định:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping
public PagedModel<EntityModel<OrderDto>> all(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, orderModelAssembler);
}
~~~

Page size cần có giới hạn tối đa để tránh request tải quá nhiều dữ liệu. Có thể cấu hình PageableHandlerMethodArgumentResolver hoặc Spring Data Web configuration để giới hạn kích thước trang.

Các thuộc tính sort cũng cần được kiểm soát. Chỉ cho phép các trường mà API công bố và repository có thể xử lý an toàn. Không nên mặc định chấp nhận mọi tên thuộc tính do máy khách gửi lên.

## 8. Xử lý trang rỗng và kiểu representation

Nếu Page không có phần tử, PagedResourcesAssembler vẫn có thể tạo PagedModel với metadata phản ánh kết quả rỗng. Tuy nhiên, khi cần công bố rõ relation của collection trong trường hợp không có phần tử, kiểu representation và metadata relation cần được xác định để serializer biết tên collection.

Có thể khai báo relation trên DTO hoặc representation type:

~~~java
import org.springframework.hateoas.server.core.Relation;
import java.math.BigDecimal;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderDto(
    Long id,
    String status,
    BigDecimal total
) {}
~~~

Với những trường hợp cần tạo representation rỗng có type rõ ràng, PagedResourcesAssembler cung cấp API toEmptyModel. Kiểu được truyền vào cần phản ánh loại representation mà collection sẽ chứa; hãy kiểm tra chữ ký API của phiên bản Spring HATEOAS/Spring Data đang dùng khi cần tùy chỉnh empty response.

Không nên tạo một phần tử giả chỉ để HAL hiển thị tên collection. Trang rỗng cần giữ content rỗng và metadata đúng.

## 9. Tạo link cấp trang tùy chỉnh

Thông thường, PagedResourcesAssembler tự tạo link điều hướng từ request và Pageable. Trong trường hợp cần cung cấp link cơ sở tùy chỉnh, có thể dùng overload nhận Link.

Link được truyền vào đóng vai trò link cơ sở cho representation phân trang. Chỉ dùng overload này khi ứng dụng đã tạo được một link cơ sở chính xác cho endpoint và ngữ cảnh truy vấn. Link cơ sở cần giữ các bộ lọc có ý nghĩa; PagedResourcesAssembler dùng nó để xây dựng các link trang. Tránh tự ghép URI từ chuỗi vì có thể làm mất filter, sort, context path hoặc encoding.

Ví dụ lời gọi khi đã có base link phù hợp:

~~~java
return pagedAssembler.toModel(page, orderModelAssembler, baseLink);
~~~

Nếu API được triển khai sau reverse proxy, cần cấu hình forwarded headers đúng để link tuyệt đối phản ánh scheme và host mà máy khách nhìn thấy. Không nên sửa URI thủ công trong assembler để bù cho cấu hình proxy sai.

## 10. Khi không dùng Spring Data Page

PagedResourcesAssembler tích hợp thuận tiện nhất khi nguồn dữ liệu là Spring Data Page. Nếu dữ liệu đến từ một hệ thống ngoài, một truy vấn tùy chỉnh hoặc một nguồn chỉ cung cấp cursor, ứng dụng có thể tạo PagedModel thủ công.

Ví dụ khái quát:

~~~java
List<EntityModel<OrderDto>> content = orders.stream()
    .map(orderModelAssembler::toModel)
    .toList();

PagedModel.PageMetadata metadata =
    new PagedModel.PageMetadata(
        pageSize,
        pageNumber,
        totalElements,
        totalPages
    );

PagedModel<EntityModel<OrderDto>> model =
    PagedModel.of(content, metadata, selfLink, nextLink);
~~~

Ở đây, assembler vẫn chuyển từng phần tử thành representation. Phần tạo PageMetadata và link trang do ứng dụng chịu trách nhiệm. Cần bảo đảm số liệu tổng, chỉ số trang và link phản ánh cùng một snapshot dữ liệu.

Nếu nguồn chỉ có cursor hoặc không biết tổng số phần tử, không nên tự tạo totalElements hoặc totalPages giả. Có thể dùng CollectionModel với link next, hoặc định nghĩa representation riêng phù hợp với cơ chế cursor.

## 11. Kiểm thử sự kết hợp của hai assembler

Kiểm thử tích hợp cần xác nhận cả link ở cấp phần tử và cấp trang. Ví dụ với MockMvc:

~~~java
mockMvc.perform(
        get("/orders?page=0&size=2")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(5))
    .andExpect(jsonPath("$.page.totalPages").value(3))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0].id").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
~~~

Các trường hợp nên kiểm tra:

- Mỗi phần tử có link self đúng ID.
- Link hành động xuất hiện theo trạng thái của từng phần tử.
- PageMetadata phản ánh đúng Page từ service.
- Trang đầu không có prev; trang cuối không có next.
- Link next/prev giữ filter, sort và size.
- Trang rỗng trả về content rỗng và metadata đúng.
- Relation trong _embedded ổn định.
- Link phản ánh đúng host và context path khi chạy sau proxy.

Có thể kiểm thử riêng OrderModelAssembler bằng unit test để xác nhận ánh xạ và link của từng Order. Sau đó dùng MockMvc để kiểm tra cách PagedResourcesAssembler kết hợp các representation đó thành phản hồi HTTP hoàn chỉnh.

## 12. Những lỗi thường gặp khi kết hợp assembler với PagedModel

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng CollectionModel cho kết quả phân trang | Mất metadata tổng và số trang | Dùng PagedResourcesAssembler hoặc PagedModel |
| Tự map Page thành List rồi trả về | Mất thông tin Page và link điều hướng | Truyền Page trực tiếp vào paged assembler |
| Đưa logic link trang vào item assembler | Mỗi phần tử mang link phân trang không phù hợp | Để PagedResourcesAssembler quản lý page links |
| Bỏ qua item assembler | Phần tử thiếu DTO hoặc link riêng | Truyền RepresentationModelAssembler vào toModel |
| Nhầm link self của item với self của page | Máy khách điều hướng sai cấp tài nguyên | Kiểm tra vị trí link trong HAL |
| Tự tạo totalPages từ dữ liệu một trang | Metadata sai | Dùng Page metadata hoặc nguồn tổng đáng tin cậy |
| Không giữ filter và sort trong page links | Trang kế tiếp đổi tập kết quả | Kiểm thử query parameters được giữ lại |
| Tạo page response rỗng bằng phần tử giả | Hợp đồng dữ liệu sai | Dùng empty PagedModel với metadata và relation đúng |

## 13. Quy trình triển khai

Khi kết hợp assembler với PagedModel trong Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định service/repository trả về Page&lt;T&gt; và Pageable.
2. Tạo DTO hoặc representation type cho một phần tử.
3. Triển khai RepresentationModelAssembler&lt;T, D&gt; để ánh xạ từng phần tử và thêm link.
4. Nhận PagedResourcesAssembler&lt;T&gt; trong controller.
5. Gọi toModel(page, representationAssembler) để tạo PagedModel&lt;D&gt;.
6. Kiểm tra metadata và page links được tạo từ request hiện tại.
7. Xác định relation của collection, kể cả khi trang rỗng.
8. Kiểm thử item links, page links, filter, sort, trang đầu/cuối và kết quả rỗng.
9. Giới hạn page size và kiểm soát các trường sort được phép.

Kết hợp RepresentationModelAssembler với PagedResourcesAssembler giúp mỗi phần tử có biểu diễn hypermedia riêng, trong khi PagedModel cung cấp metadata và điều hướng cho toàn bộ trang. Tách rõ hai cấp độ này giúp controller ngắn gọn, link nhất quán và hợp đồng API dễ kiểm thử khi dữ liệu được phân trang.
