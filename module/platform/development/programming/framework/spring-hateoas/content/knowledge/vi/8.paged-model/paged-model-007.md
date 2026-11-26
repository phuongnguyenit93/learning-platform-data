# Pageable và PagedModel

API thường phải trả về những tập hợp có số lượng phần tử lớn như đơn hàng, khách hàng hoặc lịch sử giao dịch. Trả toàn bộ dữ liệu trong một phản hồi khiến payload tăng theo thời gian, làm chậm client và tiêu tốn bộ nhớ của server. Phân trang chia tập hợp thành các phần nhỏ, cho phép client yêu cầu đúng phần dữ liệu cần xem.

Trong Spring MVC, Pageable mô tả yêu cầu phân trang và sắp xếp từ client. Spring Data dùng thông tin đó để tạo Page<T>, chứa nội dung trang cùng metadata về tổng số phần tử. Spring HATEOAS cung cấp PagedModel<T> để biểu diễn collection có phân trang và liên kết điều hướng. PagedResourcesAssembler kết nối Page<T> với assembler của tài nguyên, tạo PagedModel<EntityModel<...>> cùng các link như first, prev, next và last.

Bài học này giải thích cách các kiểu dữ liệu phối hợp, cách tích hợp phân trang vào controller, cách đọc phản hồi HAL và cách kiểm thử metadata cũng như các liên kết điều hướng.

## 1. Vì sao API cần phân trang?

Giả sử hệ thống có hàng trăm nghìn đơn hàng. Nếu endpoint GET /api/orders trả về tất cả đơn hàng trong một lần gọi, server phải truy vấn và tuần tự hóa một tập hợp lớn. Client cũng phải tải và xử lý dữ liệu mà có thể người dùng không bao giờ xem đến.

Phân trang giới hạn số phần tử trong một phản hồi. Client có thể yêu cầu:

~~~http
GET /api/orders?page=0&size=20
Accept: application/hal+json
~~~

Yêu cầu trên đề nghị trang đầu tiên, mỗi trang có tối đa 20 phần tử. Client có thể theo liên kết next trong phản hồi để đến trang tiếp theo.

Phân trang giúp:

- Giới hạn kích thước phản hồi và lượng dữ liệu cần xử lý mỗi lần.
- Giảm thời gian chờ khi client chỉ cần xem một phần tập hợp.
- Cho phép server truy vấn dữ liệu theo từng phần thay vì tải toàn bộ.
- Công bố metadata để client biết còn bao nhiêu dữ liệu.
- Cung cấp liên kết điều hướng để client tiếp tục mà không phải tự ghép URL.

Phân trang không tự động làm truy vấn nhanh. Nếu truy vấn không có chỉ mục phù hợp, sắp xếp trên cột tốn kém hoặc dùng offset rất lớn, hiệu năng vẫn có thể giảm. Cần thiết kế truy vấn và chỉ mục phù hợp với cách API lọc, sắp xếp và phân trang.

## 2. Pageable, Page và PageMetadata

Spring Data cung cấp các kiểu dữ liệu có vai trò khác nhau:

| Kiểu | Vai trò |
| --- | --- |
| Pageable | Mô tả số trang, kích thước trang và thứ tự sắp xếp cần lấy |
| PageRequest | Cách tạo một đối tượng Pageable cụ thể |
| Page<T> | Chứa nội dung trang, thông tin phân trang và tổng số phần tử |
| Slice<T> | Chứa nội dung một lát dữ liệu và thông tin còn trang kế tiếp hay không |
| PagedModel<T> | Mô hình hypermedia có nội dung, metadata trang và liên kết điều hướng |
| PagedResourcesAssembler<T> | Chuyển Page<T> thành PagedModel và tạo các link phân trang |

### Pageable

Pageable mô tả yêu cầu phân trang. Các thông tin chính gồm:

- pageNumber: chỉ số trang, bắt đầu từ 0.
- pageSize: số phần tử tối đa mong muốn trong một trang.
- sort: tiêu chí sắp xếp, gồm thuộc tính và hướng tăng dần hoặc giảm dần.

Có thể tạo Pageable trong code:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

Đoạn mã yêu cầu trang đầu tiên, tối đa 20 phần tử và sắp xếp theo createdAt giảm dần. Trong controller Spring MVC, Spring Data Web có thể chuyển query parameter thành Pageable tự động.

### Page

Page<T> chứa dữ liệu của trang hiện tại và thông tin tổng thể của tập kết quả. Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| getContent() | Danh sách phần tử của trang |
| getNumber() | Chỉ số trang hiện tại, bắt đầu từ 0 |
| getSize() | Kích thước trang được yêu cầu |
| getNumberOfElements() | Số phần tử thực tế trong trang |
| getTotalElements() | Tổng số phần tử khớp truy vấn |
| getTotalPages() | Tổng số trang |
| hasNext() | Có trang kế tiếp hay không |
| hasPrevious() | Có trang trước hay không |

Ví dụ, một truy vấn có 53 đơn hàng, kích thước trang là 20 và client yêu cầu trang số 1. Kết quả có thể chứa 20 đơn hàng, tổng cộng 53 phần tử và 3 trang. Vì chỉ số trang bắt đầu từ 0, trang số 1 là trang thứ hai theo cách đếm thông thường.

### PageMetadata trong PagedModel

PagedModel công bố metadata trang qua PageMetadata. Các trường chính gồm:

| Trường | Ý nghĩa |
| --- | --- |
| size | Kích thước trang |
| totalElements | Tổng số phần tử |
| totalPages | Tổng số trang |
| number | Chỉ số trang hiện tại, bắt đầu từ 0 |

Metadata giúp client hiển thị số trang, số kết quả và trạng thái điều hướng. Client không cần tự tính tổng số trang từ dữ liệu đang có nếu server đã công bố thông tin đó.

## 3. PagedModel và CollectionModel khác nhau thế nào?

CollectionModel<T> biểu diễn một tập hợp tài nguyên và có thể mang các liên kết. Nó không bắt buộc phải có metadata phân trang.

PagedModel<T> chuyên dùng cho tập hợp có phân trang. Ngoài nội dung và liên kết, nó có metadata về kích thước trang, tổng số phần tử, tổng số trang và trang hiện tại.

| Đặc điểm | CollectionModel | PagedModel |
| --- | --- | --- |
| Biểu diễn collection | Có | Có |
| Link hypermedia | Có | Có |
| Metadata phân trang chuẩn | Không bắt buộc | Có |
| Phù hợp với tập hợp lớn | Có thể dùng nếu tự quản lý phân trang | Phù hợp khi cần metadata và điều hướng trang |

Khi endpoint trả danh sách không phân trang, CollectionModel<EntityModel<OrderDto>> là lựa chọn phù hợp. Khi endpoint nhận Pageable và cần công bố thông tin trang, hãy dùng PagedModel<EntityModel<OrderDto>>.

## 4. Tạo assembler cho phần tử của trang

PagedResourcesAssembler cần một RepresentationModelAssembler để chuyển từng đối tượng trong Page<T> thành mô hình hypermedia. Vì vậy, trước hết hãy xây assembler cho một tài nguyên.

DTO đơn hàng:

~~~java
import java.time.Instant;

import org.springframework.hateoas.server.core.Relation;

@Relation(collectionRelation = "orders")
public record OrderDto(
        Long id,
        String status,
        Instant createdAt
) {
}
~~~

Annotation Relation chỉ định tên quan hệ collection trong biểu diễn hypermedia. Tên này giúp phản hồi HAL dùng _embedded.orders thay vì phụ thuộc vào tên mặc định được suy ra từ kiểu dữ liệu.

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

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.status().name(),
                order.createdAt()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel()
        );
    }
}
~~~

Ví dụ giả định lớp Order có các phương thức id(), status() và createdAt(). OrderController.one(id) là endpoint chi tiết. Mỗi phần tử trong trang sẽ được assembler chuyển thành EntityModel<OrderDto> với link self.

Assembler chỉ tạo representation và liên kết. Việc truy vấn dữ liệu, kiểm tra quyền và thực thi quy tắc nghiệp vụ thuộc service.

## 5. Tích hợp Pageable và PagedResourcesAssembler vào controller

Giả sử service có phương thức trả về Page<Order>:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderService {
    Page<Order> findAll(Pageable pageable);
    Order getRequired(Long id);
}
~~~

Controller có thể nhận Pageable và PagedResourcesAssembler như tham số phương thức:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.data.web.PageableDefault;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler
    ) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        return orderAssembler.toModel(orderService.getRequired(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<OrderDto>> all(
            @PageableDefault(
                    size = 20,
                    sort = "createdAt",
                    direction = Sort.Direction.DESC
            ) Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler
    ) {
        Page<Order> page = orderService.findAll(pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }
}
~~~

Spring Data Web chuyển query parameter thành Pageable. PageableDefault đặt giá trị mặc định khi client không truyền tham số: kích thước 20, sắp xếp theo createdAt giảm dần. Nếu client truyền page, size hoặc sort, resolver sử dụng các giá trị hợp lệ đó theo cấu hình.

PagedResourcesAssembler<Order> nhận Page<Order> và OrderModelAssembler. Nó chuyển các phần tử thành EntityModel<OrderDto>, tạo PagedModel và thêm các link điều hướng trang dựa trên request hiện tại.

Client có thể gọi:

~~~http
GET /api/orders?page=1&size=20&sort=createdAt,desc
Accept: application/hal+json
~~~

page=1 là trang thứ hai vì chỉ số bắt đầu từ 0. size=20 yêu cầu tối đa 20 phần tử. sort=createdAt,desc yêu cầu sắp xếp theo thời điểm tạo giảm dần.

## 6. HAL biểu diễn PagedModel

Khi Spring HATEOAS tuần tự hóa PagedModel thành HAL, phản hồi thường có ba phần:

- _embedded: các tài nguyên của trang hiện tại.
- _links: liên kết đến trang hiện tại và các trang liên quan.
- page: metadata về phân trang.

Ví dụ phản hồi minh họa:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 101,
        "status": "PAID",
        "createdAt": "2026-11-20T08:30:00Z",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/101"
          }
        }
      },
      {
        "id": 102,
        "status": "PENDING",
        "createdAt": "2026-11-20T08:10:00Z",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/102"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders?page=1&size=20&sort=createdAt,desc"
    },
    "first": {
      "href": "https://api.example.com/api/orders?page=0&size=20&sort=createdAt,desc"
    },
    "prev": {
      "href": "https://api.example.com/api/orders?page=0&size=20&sort=createdAt,desc"
    },
    "next": {
      "href": "https://api.example.com/api/orders?page=2&size=20&sort=createdAt,desc"
    },
    "last": {
      "href": "https://api.example.com/api/orders?page=2&size=20&sort=createdAt,desc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 53,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Đây là ví dụ cấu trúc, không phải URL hoặc số liệu cố định. PagedResourcesAssembler tạo các link dựa trên trang thực tế. Trang đầu không có prev; trang cuối không có next. Link first, prev, next và last chỉ xuất hiện khi có ý nghĩa đối với vị trí hiện tại.

Metadata trong page cho biết trang hiện tại có chỉ số 1, kích thước 20, tổng cộng 53 đơn hàng và 3 trang. Client có thể dùng _links.next.href để tiếp tục mà không cần tự tính URL.

## 7. Client điều hướng bằng các link phân trang

Client hypermedia nên sử dụng link relation thay vì tự xây URL. Quy trình thông thường:

1. Gọi URI collection mà ứng dụng đã biết hoặc URI điểm vào được cung cấp.
2. Đọc _embedded.orders để hiển thị các đơn hàng của trang hiện tại.
3. Đọc page để hiển thị số trang và tổng số kết quả nếu giao diện cần.
4. Nếu có _links.next, cho phép người dùng chuyển sang trang tiếp theo.
5. Khi cần quay lại, dùng _links.prev hoặc _links.first.

Không phải trang nào cũng có đủ tất cả link. Client cần kiểm tra sự tồn tại của quan hệ trước khi hiển thị thao tác điều hướng. Nếu client chưa biết một relation mở rộng, có thể bỏ qua relation đó mà vẫn xử lý các quan hệ chuẩn mà nó hiểu.

Một điểm quan trọng là link có thể chứa query parameter, context path hoặc host khác với giá trị client tự giả định. Hãy dùng URI được server trả về theo chính sách bảo mật của ứng dụng. Không nên chỉ thay giá trị page trên chuỗi URL hiện tại vì cách đó có thể làm mất size, sort hoặc bộ lọc.

## 8. Kết hợp phân trang với bộ lọc và sắp xếp

Một collection thường cần lọc theo trạng thái, khách hàng hoặc khoảng thời gian. Ví dụ:

~~~http
GET /api/orders?status=PENDING&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
~~~

Controller có thể nhận bộ lọc và Pageable:

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<EntityModel<OrderDto>> all(
        @RequestParam(required = false) OrderStatus status,
        @PageableDefault(size = 20) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler
) {
    Page<Order> page = orderService.findAll(status, pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
~~~

Service áp dụng bộ lọc trước khi phân trang:

~~~java
Page<Order> findAll(OrderStatus status, Pageable pageable);
~~~

Thứ tự xử lý về mặt logic là lọc tập kết quả, sắp xếp tập kết quả rồi lấy phần tử của trang được yêu cầu. Tổng số phần tử trong Page phải phản ánh tập hợp sau khi áp dụng bộ lọc, không phải tổng số đơn hàng của toàn hệ thống.

Khi dùng bộ lọc, hãy kiểm tra các link do assembler tạo ra có giữ các tham số lọc cần thiết hay không trong cấu hình Spring Data Web của ứng dụng. Kiểm thử link next và prev với query filter thực tế. Nếu ứng dụng có cách tạo link tùy chỉnh hoặc tham số riêng, cần bảo đảm các link phân trang tiếp tục mang theo ngữ cảnh truy vấn đó.

## 9. Giới hạn page size và kiểm soát sort

Không nên để client yêu cầu kích thước trang tùy ý. Một request với size=1000000 có thể khiến server phải truy vấn, cấp phát bộ nhớ và tuần tự hóa một lượng dữ liệu quá lớn.

Hãy đặt giới hạn kích thước tối đa cho Pageable resolver hoặc kiểm tra giá trị đầu vào ở tầng API. Giá trị mặc định nên phù hợp với kích thước representation và khả năng truy vấn của hệ thống. Với endpoint công khai, hãy công bố giới hạn trong tài liệu API và trả lỗi đầu vào nhất quán khi client vượt giới hạn nếu đó là chính sách của ứng dụng.

Sắp xếp cũng cần được kiểm soát. sort thường tham chiếu đến thuộc tính của mô hình persistence hoặc domain. Không nên để client tùy ý yêu cầu sắp xếp theo mọi thuộc tính nội bộ. Hãy chỉ cho phép các trường được API hỗ trợ, ánh xạ tên sort công khai sang thuộc tính truy vấn phù hợp và từ chối hoặc bỏ qua tiêu chí không hợp lệ theo chính sách đã định.

Với các tập dữ liệu lớn, offset pagination có thể trở nên tốn kém ở những trang rất sâu. Khi đó, keyset pagination hoặc cursor pagination có thể phù hợp hơn. Những cách này dùng giá trị khóa sắp xếp làm điểm tiếp tục thay vì bỏ qua một số lượng lớn bản ghi. Tuy nhiên, hợp đồng cursor cần được thiết kế riêng; Pageable và PagedModel theo kiểu page-number không tự động trở thành cursor pagination.

## 10. Page và Slice: chọn kiểu truy vấn phù hợp

Page<T> thường cần tổng số phần tử để cung cấp totalElements và totalPages. Với cơ sở dữ liệu quan hệ, điều này thường kéo theo một truy vấn đếm bổ sung bên cạnh truy vấn lấy nội dung trang. Với tập dữ liệu lớn hoặc truy vấn phức tạp, chi phí đếm có thể đáng kể.

Slice<T> chỉ cần biết có phần tử tiếp theo hay không. Nó thường lấy thêm một phần tử để xác định hasNext, không cần tính tổng số phần tử và tổng số trang. Điều này có thể giảm chi phí khi giao diện chỉ cần nút “Tiếp theo” hoặc cuộn vô hạn.

| Nhu cầu | Kiểu phù hợp |
| --- | --- |
| Cần tổng số kết quả và tổng số trang | Page<T> |
| Chỉ cần biết có trang tiếp theo | Slice<T> |
| Cần biểu diễn hypermedia với metadata tổng trang | PagedModel<T> được tạo từ Page<T> |
| Dùng cursor để đi tiếp trên tập dữ liệu rất lớn | Thiết kế cursor model và link riêng |

PagedResourcesAssembler được thiết kế để chuyển Page<T> thành PagedModel. Nếu dùng Slice<T>, ứng dụng có thể tạo mô hình hypermedia riêng với các liên kết điều hướng phù hợp, nhưng không nên tự điền tổng số phần tử hoặc tổng số trang khi hệ thống không có thông tin đó.

## 11. Kiểm thử PagedModel bằng MockMvc

Kiểm thử endpoint phân trang cần xác nhận status code, media type, nội dung trang, metadata và các link điều hướng.

Ví dụ test slice:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsPagedOrdersWithMetadataAndNavigationLinks() throws Exception {
        Order order = new Order(
                101L,
                OrderStatus.PAID,
                Instant.parse("2026-11-20T08:30:00Z")
        );

        Pageable pageable = PageRequest.of(
                1,
                20,
                Sort.by(Sort.Direction.DESC, "createdAt")
        );
        Page<Order> page = new PageImpl<>(
                List.of(order),
                pageable,
                53
        );
        when(orderService.findAll(any(Pageable.class))).thenReturn(page);

        mockMvc.perform(get("/api/orders")
                        .param("page", "1")
                        .param("size", "20")
                        .param("sort", "createdAt,desc")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.page.number").value(1))
                .andExpect(jsonPath("$.page.size").value(20))
                .andExpect(jsonPath("$.page.totalElements").value(53))
                .andExpect(jsonPath("$.page.totalPages").value(3))
                .andExpect(jsonPath("$._embedded.orders[0].id").value(101))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.first.href").exists())
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next.href").exists())
                .andExpect(jsonPath("$._links.last.href").exists());
    }
}
~~~

Đây là ví dụ minh họa. Order, OrderStatus, OrderService, controller và assembler cần được định nghĩa trong package của ứng dụng. @Import đăng ký assembler trong test slice; service được mock để kiểm soát kết quả truy vấn.

Nên bổ sung kiểm thử cho các ranh giới:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Trang đầu | Không có link prev; có link next nếu còn dữ liệu |
| Trang giữa | Có cả prev và next |
| Trang cuối | Không có link next |
| Collection rỗng | Metadata phản ánh không có kết quả và cấu trúc HAL hợp lệ |
| size vượt giới hạn | Hành vi theo chính sách giới hạn page size |
| Bộ lọc kết hợp phân trang | Metadata và link giữ đúng điều kiện lọc |
| Sort không hợp lệ | Bị từ chối hoặc xử lý theo allowlist đã công bố |

Không nên khóa test vào hostname hoặc cổng cố định. Hãy xác nhận relation tồn tại và query parameter quan trọng trong link. Với link điều hướng, nên kiểm tra URI thực sự trỏ đến endpoint collection và giữ ngữ cảnh phân trang hoặc bộ lọc.

## 12. Những lỗi thường gặp

**Trả toàn bộ collection không giới hạn.** Dữ liệu lớn làm tăng chi phí truy vấn, bộ nhớ và thời gian truyền. Hãy giới hạn kết quả và cung cấp phân trang khi phù hợp.

**Nhầm chỉ số trang bắt đầu từ 1.** Spring Data dùng chỉ số trang bắt đầu từ 0. Trang 0 là trang đầu tiên, trang 1 là trang thứ hai.

**Dùng CollectionModel khi cần metadata phân trang.** CollectionModel không cung cấp metadata trang chuẩn. Dùng PagedModel khi cần tổng số phần tử, tổng số trang và các liên kết điều hướng.

**Tự ghép link next và prev.** Việc tự tạo URL dễ làm mất sort, filter hoặc context path. Dùng PagedResourcesAssembler để tạo link từ request và kết quả trang.

**Không giới hạn page size.** Client có thể yêu cầu quá nhiều dữ liệu. Hãy cấu hình kích thước mặc định và tối đa phù hợp.

**Cho phép sort mọi thuộc tính.** Tên thuộc tính persistence không nhất thiết là hợp đồng công khai. Hãy kiểm soát danh sách trường sort và ánh xạ sang truy vấn.

**Dùng Page dù không cần tổng số phần tử.** Truy vấn đếm có thể tốn kém. Nếu client chỉ cần biết có phần tiếp theo, cân nhắc Slice hoặc cursor pagination.

**Không kiểm tra link ở trang đầu và trang cuối.** Các quan hệ điều hướng tùy thuộc vị trí trang. Cần kiểm thử riêng từng trường hợp.

## 13. Ghi nhớ

Pageable mô tả trang, kích thước và sắp xếp mà client yêu cầu. Spring Data dùng nó để tạo Page<T>, chứa nội dung và tổng số phần tử. Spring HATEOAS dùng PagedModel<T> để biểu diễn collection có metadata trang và link điều hướng. PagedResourcesAssembler<T> chuyển Page<T> thành PagedModel bằng cách kết hợp kết quả với RepresentationModelAssembler của từng tài nguyên.

Trong controller, nhận Pageable và PagedResourcesAssembler, truy vấn service để lấy Page<T> rồi gọi toModel(page, assembler). HAL biểu diễn nội dung trong _embedded, link điều hướng trong _links và metadata trong page. Client nên theo first, prev, next hoặc last được server công bố thay vì tự xây URL.

Hãy giới hạn kích thước trang, kiểm soát các trường sort, giữ filter trong các link phân trang và chọn Page, Slice hoặc cursor theo nhu cầu metadata và chi phí truy vấn. Kiểm thử cả nội dung, metadata lẫn hành vi link ở trang đầu, trang giữa và trang cuối để hợp đồng phân trang hoạt động ổn định.
