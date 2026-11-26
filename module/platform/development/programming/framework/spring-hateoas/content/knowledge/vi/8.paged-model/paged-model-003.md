# Metadata phân trang với PagedModel trong Spring HATEOAS

Khi API trả về một tập hợp lớn, máy khách cần biết mình đang xem trang nào, mỗi trang có bao nhiêu phần tử, toàn bộ kết quả có bao nhiêu phần tử và còn bao nhiêu trang. Spring HATEOAS biểu diễn thông tin đó bằng `PagedModel` và đối tượng `PagedModel.PageMetadata`.

Metadata mô tả vị trí và quy mô của trang hiện tại. Các liên kết hypermedia như `first`, `prev`, `self`, `next` và `last` cho phép máy khách chuyển giữa các trang. Hai phần này bổ sung cho nhau: metadata cho biết trạng thái phân trang, còn link cung cấp đường đi để tiếp tục.

## 1. PagedModel và PageMetadata

`PagedModel<T>` là representation model dành cho một tập hợp có phân trang. Nó mở rộng khả năng của collection model bằng cách bổ sung metadata trang.

Metadata được biểu diễn bởi lớp lồng `PagedModel.PageMetadata`, gồm bốn giá trị:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---:|
| `size` | Số phần tử tối đa được yêu cầu trong một trang | 20 |
| `number` | Chỉ số trang hiện tại, bắt đầu từ 0 | 0 |
| `totalElements` | Tổng số phần tử phù hợp với truy vấn | 47 |
| `totalPages` | Tổng số trang theo kích thước trang | 3 |

Giả sử truy vấn có 47 đơn hàng và kích thước trang là 20:

- Trang 0 chứa tối đa 20 đơn hàng đầu tiên.
- Trang 1 chứa tối đa 20 đơn hàng tiếp theo.
- Trang 2 chứa 7 đơn hàng còn lại.
- Tổng số trang là 3.

Công thức tổng quát khi kích thước trang lớn hơn 0:

```
totalPages = ceil(totalElements / size)
```

`number` là chỉ số bắt đầu từ 0 theo quy ước của Spring Data. Vì vậy, trang đầu tiên có `number = 0`, trang thứ hai có `number = 1`. Giao diện người dùng có thể hiển thị số trang bắt đầu từ 1, nhưng không nên nhầm số hiển thị đó với giá trị API.

## 2. Metadata khác gì navigation links?

Metadata và link có vai trò riêng.

| Thành phần | Trả lời câu hỏi |
|---|---|
| `page.size` | Một trang có kích thước bao nhiêu? |
| `page.number` | Hiện tại đang ở trang nào? |
| `page.totalElements` | Có bao nhiêu phần tử trong toàn bộ kết quả? |
| `page.totalPages` | Có bao nhiêu trang? |
| `_links.first` | Đi tới trang đầu bằng URI nào? |
| `_links.prev` | Đi tới trang trước bằng URI nào? |
| `_links.self` | URI của trang hiện tại là gì? |
| `_links.next` | Đi tới trang tiếp theo bằng URI nào? |
| `_links.last` | Đi tới trang cuối bằng URI nào? |

Máy khách có thể dùng metadata để hiển thị “Trang 2 trên 3” hoặc “47 kết quả”. Khi cần chuyển trang, nó theo URI của link tương ứng.

Không nên yêu cầu máy khách tự tính URI từ `number`, `size` hoặc cấu trúc query string. Cách làm đó khiến máy khách phải biết quy ước phân trang của máy chủ và dễ bị ảnh hưởng khi tên tham số hoặc cấu trúc endpoint thay đổi.

## 3. Cấu trúc HAL của một trang

Khi `PagedModel` được tuần tự hóa thành HAL JSON, dữ liệu phần tử nằm trong `_embedded`, link nằm trong `_links`, còn metadata nằm trong thuộc tính `page`.

Ví dụ trang đầu của tập hợp 47 đơn hàng, mỗi trang 20 phần tử:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 101,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/101"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
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
```

Ví dụ chỉ hiển thị một phần tử trong `_embedded.orders` để dễ đọc; phản hồi thực tế có thể chứa tối đa 20 phần tử.

Ở trang đầu, link `prev` thường không được cung cấp vì chưa có trang trước. Ở trang cuối, link `next` thường không được cung cấp. Máy khách nên kiểm tra sự hiện diện của relation thay vì tự suy luận URL.

Tên relation nhúng như `orders` cần nhất quán với hợp đồng API. Với mô hình riêng, có thể khai báo `@Relation(collectionRelation = "orders")` trên representation type hoặc cấu hình relation phù hợp để HAL đặt đúng tên trong `_embedded`.

## 4. Tạo PageMetadata thủ công

Khi đã có danh sách nội dung, metadata và các link, có thể tạo `PagedModel` trực tiếp:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.PagedModel;

import java.util.List;

List<OrderRepresentation> content = loadCurrentPage();

PagedModel.PageMetadata metadata =
    new PagedModel.PageMetadata(
        20,  // size
        0,   // number
        47,  // totalElements
        3    // totalPages
    );

PagedModel<OrderRepresentation> model = PagedModel.of(
    content,
    metadata,
    Link.of("/orders?page=0&size=20", IanaLinkRelations.SELF),
    Link.of("/orders?page=1&size=20", IanaLinkRelations.NEXT),
    Link.of("/orders?page=2&size=20", IanaLinkRelations.LAST)
);
```

`PageMetadata` nhận các giá trị theo thứ tự `size`, `number`, `totalElements`, `totalPages`. `PagedModel.of(...)` kết hợp nội dung, metadata và các link để tạo representation.

Cách tạo thủ công hữu ích khi dữ liệu đến từ một nguồn không dùng Spring Data `Page`, hoặc khi ứng dụng có logic phân trang đặc thù. Tuy nhiên, ứng dụng phải tự bảo đảm metadata và link nhất quán với truy vấn thực tế. Không nên ghi cứng số trang, tổng phần tử hoặc URL như ví dụ minh họa vào API chạy thật.

## 5. Dùng Spring Data Page và PagedResourcesAssembler

Trong ứng dụng Spring Data, repository thường trả về `Page<T>`. `Page` chứa nội dung trang hiện tại, thông tin phân trang và tổng số phần tử. Spring HATEOAS tích hợp với Spring Data qua `PagedResourcesAssembler<T>`, giúp chuyển `Page<T>` thành `PagedModel<D>` và tạo các link điều hướng.

Giả sử có DTO:

```java
import java.math.BigDecimal;

public record OrderDto(
    Long id,
    String status,
    BigDecimal total
) {}
```

Assembler chuyển `Order` thành `EntityModel<OrderDto>`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    private final OrderDtoMapper mapper;

    public OrderAssembler(OrderDtoMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = mapper.toDto(order);

        return EntityModel.of(
            dto,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );
    }
}
```

Controller có thể nhận `Pageable` và dùng `PagedResourcesAssembler`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderAssembler orderAssembler;

    public OrderController(
            OrderService orderService,
            OrderAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    public PagedModel<EntityModel<OrderDto>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderService.findAll(pageable);

        return pagedAssembler.toModel(page, orderAssembler);
    }
}
```

Trong ví dụ, `OrderService.findAll(pageable)` trả về `Page<Order>`. `PagedResourcesAssembler` dùng metadata từ Page, chuyển từng phần tử qua `OrderAssembler`, rồi tạo `PagedModel` có các liên kết phân trang.

Spring Boot thường tự cấu hình hỗ trợ Spring Data web và Spring HATEOAS khi các dependency tương ứng có mặt. Với ứng dụng cấu hình thủ công, cần bảo đảm Spring Data web support và các resolver liên quan đã được đăng ký.

## 6. Pageable và tham số phân trang từ request

Spring Data Web có thể ánh xạ query parameter thành đối tượng `Pageable`. Ví dụ:

```http
GET /orders?page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

Các tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| `page` | Chỉ số trang, bắt đầu từ 0 |
| `size` | Số phần tử tối đa trên trang |
| `sort` | Thuộc tính sắp xếp và hướng sắp xếp |

Có thể đặt giá trị mặc định cho endpoint:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

@GetMapping
public PagedModel<EntityModel<OrderDto>> all(
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

`@PageableDefault` giúp xác định kích thước và thứ tự mặc định khi máy khách không truyền tham số. Có thể cấu hình giới hạn kích thước trang tối đa bằng `PageableHandlerMethodArgumentResolver` hoặc cấu hình Spring Data Web tương ứng. Đây là điều cần thiết để tránh máy khách yêu cầu một trang quá lớn.

Tên thuộc tính sắp xếp phải được kiểm soát. Không nên cho phép máy khách tùy ý sắp xếp theo các thuộc tính nội bộ hoặc trường không được hỗ trợ. Service/repository nên xác thực danh sách thuộc tính sort được phép trước khi tạo truy vấn.

## 7. Giữ bộ lọc và sắp xếp khi tạo link trang

Một trang kết quả thường được tạo từ nhiều tham số: từ khóa, trạng thái đơn hàng, khoảng thời gian, sort và kích thước trang. Link `next` hoặc `prev` phải giữ ngữ cảnh truy vấn để máy khách tiếp tục xem cùng tập kết quả.

Ví dụ:

```http
GET /orders?status=PAID&from=2026-01-01&page=0&size=20&sort=createdAt,desc
```

Link trang kế tiếp cần duy trì các bộ lọc và sort, đồng thời cập nhật giá trị `page`. Khi dùng `PagedResourcesAssembler` trong request Spring MVC thông thường, link được xây dựng dựa trên request hiện tại và pageable resolver. Với bộ lọc tùy chỉnh, proxy, custom argument resolver hoặc URL rewrite, cần kiểm thử các link sinh ra để xác nhận query parameter được giữ đúng.

Nếu tự tạo link thủ công, hãy dùng URI builder và giữ các tham số truy vấn có ý nghĩa. Không nên nối chuỗi query tùy tiện vì có thể làm mất bộ lọc, sai encoding hoặc tạo URL không hợp lệ.

## 8. Trang rỗng và các trường hợp biên

Kết quả phân trang có thể rỗng vì không có bản ghi phù hợp hoặc vì máy khách yêu cầu một trang ngoài phạm vi. API cần biểu diễn tình huống này rõ ràng.

Một trang rỗng vẫn có thể có metadata:

- `size`: kích thước trang được yêu cầu hoặc áp dụng.
- `number`: chỉ số trang được xử lý.
- `totalElements`: tổng số kết quả phù hợp.
- `totalPages`: tổng số trang theo kết quả và kích thước.

Nếu truy vấn không có kết quả, `totalElements` thường bằng 0 và `totalPages` bằng 0 với page size dương. `_embedded` có thể chứa danh sách rỗng. Không nên tự tạo một phần tử giả để tránh collection rỗng.

Cần xác định chính sách cho trang vượt quá phạm vi. Ứng dụng có thể trả về trang rỗng cùng metadata phản ánh truy vấn, hoặc từ chối request bằng lỗi phù hợp theo hợp đồng. Dù chọn cách nào, không được tạo link `next` hoặc `last` dẫn tới vòng điều hướng không có điểm dừng.

Khi dữ liệu thay đổi giữa hai lần gọi, tổng số phần tử và số trang có thể thay đổi. Metadata là ảnh chụp tại thời điểm truy vấn, không phải cam kết rằng tập kết quả sẽ bất biến trong suốt quá trình người dùng duyệt trang.

## 9. Page, Slice và chi phí đếm tổng số phần tử

Spring Data cung cấp cả `Page<T>` và `Slice<T>`, nhưng chúng không có cùng thông tin.

| Kiểu | Thông tin có sẵn | Khi nên dùng |
|---|---|---|
| `Page<T>` | Nội dung, thông tin trang, tổng số phần tử và tổng số trang | Khi giao diện cần tổng kết quả hoặc số trang |
| `Slice<T>` | Nội dung và thông tin có trang kế tiếp hay không | Khi chỉ cần nút tiếp tục tải thêm |

Để tính `totalElements` và `totalPages`, truy vấn `Page<T>` thường cần thực hiện thêm count query. Với tập dữ liệu lớn hoặc truy vấn phức tạp, chi phí đếm có thể đáng kể.

Nếu sản phẩm chỉ cần “Xem thêm” hoặc cuộn vô hạn, `Slice<T>` có thể phù hợp hơn vì chỉ cần biết còn phần tử tiếp theo hay không. Không nên giả lập `totalPages` hoặc `totalElements` khi nguồn dữ liệu không cung cấp các giá trị đáng tin cậy. Có thể thiết kế một representation riêng cho slice với link `next` thay vì dùng `PagedModel` như thể đã biết tổng số trang.

## 10. Kiểm thử metadata và link phân trang

Kiểm thử API cần xác nhận cả metadata lẫn link. Ví dụ với MockMvc, giả sử truy vấn có 45 đơn hàng và page size là 20:

```java
mockMvc.perform(
        get("/orders?page=0&size=20")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.totalElements").value(45))
    .andExpect(jsonPath("$.page.totalPages").value(3))
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$._links.prev").doesNotExist());
```

Với trang giữa hoặc trang cuối, kiểm thử các relation tương ứng. Chẳng hạn trang cuối không nên có `next`; trang không phải trang đầu có thể có `prev`.

Ngoài ra, nên có các trường hợp:

- Kết quả rỗng: nội dung nhúng rỗng và metadata tổng bằng 0.
- Trang cuối có ít phần tử hơn page size.
- Sort và filter được giữ trong URI của link điều hướng.
- Kích thước trang vượt giới hạn bị xử lý theo cấu hình.
- Trang vượt phạm vi tuân theo chính sách đã công bố.
- Máy khách không được truy cập dữ liệu ngoài phạm vi chỉ bằng cách thay query parameter hoặc ID.

Kiểm thử nên so sánh URI và giá trị metadata quan sát được trong phản hồi, tránh chỉ kiểm tra một phương thức tạo link nội bộ.

## 11. Những lỗi thường gặp khi thiết kế PagedModel

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `number` bắt đầu từ 1 | Điều hướng sai trang | Dùng chỉ số 0-based của Spring Data |
| Tự tính URI trong máy khách | Máy khách phụ thuộc quy ước URL | Theo link `next`, `prev`, `first`, `last` |
| Dùng tổng số phần tử giả | Giao diện hiển thị sai số trang | Dùng Page hoặc mô hình không công bố tổng |
| Bỏ qua filter khi tạo link | Trang kế tiếp chứa tập kết quả khác | Giữ query parameter của truy vấn |
| Cho phép page size không giới hạn | Truy vấn nặng và phản hồi lớn | Đặt page size mặc định và giới hạn tối đa |
| Không kiểm thử trang rỗng | Metadata hoặc link có thể sai | Kiểm thử trường hợp không có kết quả |
| Dùng Page khi không cần tổng | Phát sinh count query không cần thiết | Cân nhắc Slice hoặc cursor pagination |

## 12. Quy trình thiết kế metadata phân trang

Khi xây dựng endpoint phân trang với Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định máy khách cần tổng số kết quả hay chỉ cần biết còn trang tiếp theo.
2. Chọn `Page<T>` nếu cần metadata tổng; chọn `Slice<T>` nếu không cần tổng.
3. Xác định page size mặc định và giới hạn tối đa.
4. Xác thực các thuộc tính sort và bộ lọc được hỗ trợ.
5. Chuyển domain object thành DTO/representation model bằng assembler.
6. Dùng `PagedResourcesAssembler` để tạo `PagedModel` khi nguồn dữ liệu là Spring Data Page.
7. Xác nhận metadata và link phản ánh cùng một truy vấn.
8. Kiểm thử trang đầu, trang giữa, trang cuối, kết quả rỗng và filter/sort.

`PagedModel.PageMetadata` giúp công bố rõ quy mô và vị trí của trang hiện tại. Khi kết hợp với các relation điều hướng, máy khách có thể hiểu trạng thái phân trang và tiếp tục duyệt tập hợp theo URI mà máy chủ cung cấp. Spring Data `Page` cùng `PagedResourcesAssembler` giảm đáng kể công việc tạo metadata và link thủ công, trong khi việc chọn Page hay Slice giúp cân bằng giữa thông tin tổng kết quả và chi phí truy vấn.
