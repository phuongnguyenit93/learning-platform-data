# Assembler có Pageable

## Mục tiêu

API trả về danh sách lớn thường cần chia kết quả thành nhiều trang. Trong Spring MVC, Pageable mô tả trang client yêu cầu; Spring Data dùng Pageable để truy vấn và trả về Page<T>; Spring HATEOAS biểu diễn kết quả dưới dạng PagedModel<D> với metadata và các liên kết điều hướng. PagedResourcesAssembler là cầu nối giữa Page và PagedModel, đồng thời dùng RepresentationModelAssembler để chuyển từng phần tử thành representation có links.

Sau bài học, bạn có thể:

- Phân biệt Pageable, Page<T>, RepresentationModelAssembler và PagedResourcesAssembler.
- Nhận Pageable từ query parameters của request.
- Chuyển Page<T> thành PagedModel<D> bằng PagedResourcesAssembler.
- Gắn links cho từng item bằng RepresentationModelAssembler.
- Hiểu metadata trang, links first/prev/self/next/last và ảnh hưởng của sort/filter.
- Kiểm thử response phân trang bằng MockMvc.

## Vai trò của từng thành phần

Phân trang hypermedia có nhiều thành phần phối hợp. Mỗi thành phần giải quyết một phần riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Pageable | Mô tả trang được yêu cầu: số trang, kích thước và thứ tự sắp xếp. |
| Page<T> | Kết quả truy vấn của Spring Data, gồm content và metadata tổng số phần tử/trang. |
| RepresentationModelAssembler<T, D> | Chuyển một đối tượng T thành representation D, thường gắn links cho từng item. |
| PagedResourcesAssembler<T> | Chuyển Page<T> thành PagedModel<D>, tạo page metadata và links điều hướng. |
| PagedModel<D> | Representation hypermedia chứa các item đã chuyển đổi, metadata phân trang và links cấp collection. |

Điểm cần nhớ: Pageable thường được nhận ở controller và chuyển xuống service/repository. RepresentationModelAssembler xử lý từng phần tử, không cần nhận Pageable để tạo link self của item. PagedResourcesAssembler nhận Page cùng item assembler và tạo lớp representation phân trang bên ngoài.

Luồng xử lý:

~~~mermaid
flowchart TD
    A[HTTP request: page, size, sort] --> B[Spring MVC Pageable resolver]
    B --> C[Controller nhận Pageable]
    C --> D[Service / Repository]
    D --> E[Page<Order>]
    E --> F[PagedResourcesAssembler]
    F --> G[RepresentationModelAssembler]
    G --> H[EntityModel<OrderResponse> cho từng item]
    H --> I[PagedModel với metadata và page links]
    I --> J[HAL JSON response]
~~~

## Pageable được tạo từ request như thế nào?

Spring Data Web hỗ trợ phân giải query parameters thành Pageable. Với cấu hình mặc định, client có thể gửi:

~~~http
GET /api/orders?page=0&size=20&sort=createdAt,desc
~~~

Các tham số thường dùng:

- page: số thứ tự trang, mặc định bắt đầu từ 0.
- size: số phần tử tối đa trên một trang.
- sort: thuộc tính sắp xếp và hướng sắp xếp; có thể lặp lại để khai báo nhiều tiêu chí.

Ví dụ request có nhiều tiêu chí sort:

~~~http
GET /api/orders?page=0&size=20&sort=status,asc&sort=createdAt,desc
~~~

Controller có thể đặt giá trị mặc định bằng @PageableDefault:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping
PagedModel<EntityModel<OrderResponse>> findAll(
        @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC)
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {
    // ...
}
~~~

@PageableDefault chỉ định mặc định khi client không gửi giá trị tương ứng. Client vẫn có thể gửi page, size hoặc sort theo chính sách endpoint. Hãy giới hạn kích thước trang tối đa và kiểm soát các thuộc tính được phép sort để tránh truy vấn quá lớn hoặc sắp xếp trên trường không phù hợp.

Pageable không phải request body. Spring MVC lấy các giá trị từ query string rồi tạo đối tượng Pageable cho controller. Khi ứng dụng không dùng Spring Boot, bật hỗ trợ Spring Data Web bằng @EnableSpringDataWebSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class SpringDataWebConfiguration {
}
~~~

Với Spring Boot, cấu hình Spring Data Web thường được auto-configure khi dependency phù hợp có mặt.

## Từ Page<T> tới PagedModel<D>

Repository hoặc service nhận Pageable và trả Page<T>. Page chứa:

- Content: các phần tử thuộc trang hiện tại.
- Number: số trang hiện tại, bắt đầu từ 0.
- Size: kích thước trang.
- Total elements: tổng số phần tử sau khi áp dụng bộ lọc.
- Total pages: tổng số trang theo kích thước trang.

PagedResourcesAssembler chuyển Page thành PagedModel. Trong API Spring Data hiện nay, tên class vẫn là PagedResourcesAssembler, trong khi kiểu hypermedia kết quả được gọi là PagedModel.

Page cung cấp tổng số phần tử và tổng số trang, nên truy vấn thường cần thêm phép đếm (count query). Với collection rất lớn hoặc truy vấn có count đắt đỏ, cân nhắc Slice hoặc cursor-based pagination nếu client không cần totalElements/totalPages. Các cách đó có hợp đồng metadata và điều hướng khác; ví dụ PagedResourcesAssembler trong bài này dành cho kết quả Page.

Ví dụ controller:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    PagedModel<EntityModel<OrderResponse>> findAll(
            @RequestParam(required = false) OrderStatus status,
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.findAll(status, pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
~~~

Spring MVC phân giải Pageable từ request. PagedResourcesAssembler được cung cấp bởi Spring Data Web support. Phương thức toModel nhận Page<Order> và RepresentationModelAssembler<Order, EntityModel<OrderResponse>>; nó chuyển từng Order thành EntityModel<OrderResponse>, rồi tạo PagedModel chứa các item, metadata và page links.

Controller không cần tự tính totalPages, tự tạo query parameter page hoặc tự ghép links next/prev. Những thông tin đó được suy ra từ Page và request hiện tại.

## RepresentationModelAssembler chuyển từng item

Item assembler chịu trách nhiệm chuyển domain object thành representation và tạo links của chính item đó:

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

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null)).withRel("cancel"));
        }

        return model;
    }
}
~~~

PagedResourcesAssembler gọi toModel cho từng phần tử trong Page. Vì vậy, mỗi item giữ link self và các action links phù hợp với trạng thái của nó. Ví dụ một trang có đơn hàng PENDING và SHIPPED sẽ có thể chứa link cancel ở item PENDING nhưng không có ở item SHIPPED.

Không đưa page number vào link self của item. Link self của item trỏ tới tài nguyên cụ thể; links phân trang thuộc PagedModel bên ngoài. Hai cấp link này có mục đích khác nhau:

- Item links: self, cancel, detail hoặc action của từng tài nguyên.
- Page links: first, prev, self, next, last của trang collection hiện tại.

## Metadata và page links

PagedModel thường serialize metadata phân trang dưới thuộc tính page. Metadata gồm size, totalElements, totalPages và number. Các links điều hướng được tạo theo trang hiện tại và tổng số trang:

| Link relation | Ý nghĩa |
|---|---|
| first | Trang đầu tiên. |
| prev | Trang ngay trước trang hiện tại, nếu tồn tại. |
| self | Trang hiện tại với các tham số đang áp dụng. |
| next | Trang kế tiếp, nếu tồn tại. |
| last | Trang cuối cùng. |

Ví dụ response HAL rút gọn:

~~~json
{
  "_embedded": {
    "orderResponseList": [
      {
        "id": "order-42",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/api/orders/order-42"
          },
          "cancel": {
            "href": "/api/orders/order-42/cancellation"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "/api/orders?page=0&size=20"
    },
    "self": {
      "href": "/api/orders?page=1&size=20"
    },
    "prev": {
      "href": "/api/orders?page=0&size=20"
    },
    "next": {
      "href": "/api/orders?page=2&size=20"
    },
    "last": {
      "href": "/api/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Tên relation trong _embedded phụ thuộc relation resolver hoặc @Relation của kiểu representation thực tế. Ví dụ trên dùng orderResponseList để minh họa; ứng dụng nên định nghĩa và kiểm thử tên relation ổn định mà client sử dụng.

Ở trang đầu, prev thường không xuất hiện; ở trang cuối, next thường không xuất hiện. Khi chỉ có một trang hoặc collection rỗng, tập links có thể khác với ví dụ. Client nên kiểm tra sự tồn tại của relation trước khi điều hướng, không tự suy ra rằng mọi response đều có đủ năm link.

## Giữ filter và sort khi điều hướng

Một request phân trang thường kết hợp nhiều tham số:

~~~http
GET /api/orders?status=PENDING&page=1&size=10&sort=createdAt,desc
~~~

Khi chuyển sang trang tiếp theo, client cần tiếp tục áp dụng filter và sort hiện tại. PagedResourcesAssembler xây page links dựa trên request hiện tại và Pageable resolver. Hãy xác minh các tham số lọc tùy chỉnh được giữ trong links theo cấu hình ứng dụng; nếu endpoint có filter, test nên kiểm tra href next/self chứa các filter cần thiết.

Nếu API sử dụng tên tham số Pageable tùy chỉnh hoặc cách đánh số trang khác mặc định, hãy cấu hình Spring Data Web resolver nhất quán. Ví dụ có thể thay đổi tên page/size hoặc bật cách đánh số một-based qua cấu hình phù hợp. Không nên để controller nhận một quy ước nhưng links lại phát ra một quy ước khác.

Sort cần dùng tên thuộc tính mà Spring Data hiểu trong mô hình persistence/query. Không nên cho phép client sort tùy ý trên mọi thuộc tính; hãy định nghĩa danh sách trường được hỗ trợ và kiểm thử trường hợp sort không hợp lệ.

## Khi nào cần thêm link collection riêng?

PagedResourcesAssembler tự tạo page links. Nếu API cần link tìm kiếm, link tạo mới hoặc link điều hướng nghiệp vụ ở cấp collection, có thể thêm sau khi nhận PagedModel:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

PagedModel<EntityModel<OrderResponse>> model =
        pagedAssembler.toModel(page, orderAssembler);

model.add(linkTo(methodOn(OrderController.class)
        .create(null)).withRel("create"));

return model;
~~~

Ví dụ minh họa link tới endpoint tạo đơn hàng; methodOn chỉ tham chiếu mapping và không thực hiện tạo đơn. Nếu endpoint tạo yêu cầu body, null được dùng ở vị trí body khi build link. Nếu client cần biết HTTP method hoặc schema đầu vào, hãy gắn affordance và chọn định dạng hypermedia hỗ trợ affordance.

Không thêm lại link self của page một cách thủ công nếu PagedResourcesAssembler đã tạo link đó. Hãy kiểm tra relation hiện có để tránh duplicate link hoặc ghi đè URI phân trang đúng.

## Collection rỗng và trang vượt phạm vi

PagedResourcesAssembler vẫn có thể tạo PagedModel khi Page không có content. Khi toàn bộ kết quả rỗng, totalElements và totalPages bằng 0; size vẫn phản ánh kích thước trang và number phản ánh trang đang được xử lý.

Trang vượt phạm vi cũng có content rỗng nhưng metadata có thể cho biết collection vẫn có dữ liệu. Ví dụ tổng cộng 45 phần tử, size 20, client yêu cầu page=5: totalElements vẫn là 45 và totalPages là 3. Không thay metadata thành 0 chỉ vì content của trang hiện tại rỗng.

Nếu dùng custom representation và cần relation HAL ổn định khi page rỗng, hãy kiểm thử cách relation được xác định cho kiểu phần tử rỗng. Với trường hợp tự tạo PagedModel rỗng, có thể cần cung cấp fallback type; còn khi chuyển từ Page bằng PagedResourcesAssembler, hãy kiểm tra serializer và relation resolver trong phiên bản Spring HATEOAS đang dùng.

## Kiểm thử assembler có Pageable

MockMvc có thể xác minh cả page metadata, links điều hướng và representation của từng item. Ví dụ fixture có ba đơn hàng phù hợp với filter và page size bằng hai:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .param("status", "PENDING")
                .param("page", "0")
                .param("size", "2")
                .param("sort", "createdAt,desc")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.page.size").value(2))
        .andExpect(jsonPath("$.page.number").value(0))
        .andExpect(jsonPath("$.page.totalElements").value(3))
        .andExpect(jsonPath("$.page.totalPages").value(2))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.next.href").exists())
        .andExpect(jsonPath("$._embedded").exists());
~~~

Tiếp tục kiểm tra page=1 để xác nhận link prev xuất hiện và link next không xuất hiện nếu đây là trang cuối. Với item assembler, kiểm tra một item PENDING có link cancel và item SHIPPED không có link đó. Nếu filter status phải được giữ khi điều hướng, kiểm tra href next có status=PENDING.

Các tình huống quan trọng:

- Request không truyền page/size dùng đúng default.
- Request có size lớn hơn giới hạn được áp dụng chính sách max page size.
- Page đầu, page giữa và page cuối có links phù hợp.
- Collection rỗng giữ metadata và response status đúng hợp đồng.
- Filter và sort được giữ trong page links.
- Item links vẫn đúng khi item nằm trong bất kỳ trang nào.

## Những lỗi thường gặp

- **Nhầm Pageable với PagedResourcesAssembler:** Pageable mô tả trang yêu cầu; PagedResourcesAssembler chuyển Page thành hypermedia representation.
- **Trả Page trực tiếp như hợp đồng HTTP:** Page là abstraction của Spring Data. Dùng PagedModel để công bố metadata và links hypermedia.
- **Tự tính totalPages trong controller:** lấy metadata từ Page để tránh sai lệch với truy vấn.
- **Dùng item assembler để tạo page links:** item assembler chỉ chuyển từng phần tử. PagedResourcesAssembler tạo links cấp trang.
- **Quên truyền item assembler:** nếu chỉ chuyển Page mà không dùng RepresentationModelAssembler, các item có thể thiếu links cần thiết.
- **Làm mất filter hoặc sort:** next/prev links phải tiếp tục truy vấn cùng tập kết quả theo hợp đồng.
- **Không giới hạn page size:** request có size quá lớn có thể làm tăng tải truy vấn và bộ nhớ.
- **Giả định trang rỗng đồng nghĩa collection rỗng:** trang ngoài phạm vi có thể rỗng trong khi tổng collection vẫn có dữ liệu.
- **Tạo duplicate self link:** kiểm tra page links do PagedResourcesAssembler tạo trước khi bổ sung link thủ công.

## Quy trình triển khai

1. Nhận Pageable ở controller và truyền xuống service/repository.
2. Lấy Page<T> với content và metadata tổng số phần tử.
3. Tạo RepresentationModelAssembler<T, D> để chuyển từng item và gắn links phù hợp.
4. Gọi PagedResourcesAssembler<T>.toModel(page, itemAssembler) để nhận PagedModel<D>.
5. Bổ sung links cấp collection nếu API cần action hoặc chức năng riêng.
6. Kiểm tra metadata, page links, filter, sort, page rỗng và giới hạn kích thước.
7. Dùng MockMvc xác minh response HAL và hành vi điều hướng giữa các trang.

Khi phối hợp Pageable, Page, RepresentationModelAssembler và PagedResourcesAssembler đúng vai trò, controller có thể trả một PagedModel vừa chứa dữ liệu từng item, vừa công bố metadata cùng các link điều hướng. Client nhờ đó duyệt collection theo các liên kết server cung cấp mà không phải tự xây dựng quy tắc phân trang.
