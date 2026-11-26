# Thiết kế search endpoint với Spring HATEOAS

Một search endpoint cho phép máy khách truy vấn một collection theo các điều kiện như trạng thái, tên khách hàng, khoảng ngày, thứ tự sắp xếp và phân trang. Trong REST API có hypermedia, server cần công bố cả endpoint tìm kiếm lẫn cách máy khách truyền các tiêu chí. Spring HATEOAS hỗ trợ việc này bằng **link relation `search`** và **URI template**, đồng thời có thể mô tả một biểu mẫu tìm kiếm bằng affordance khi dùng HAL-FORMS.

Bài này xây dựng endpoint tìm kiếm đơn hàng tại `/orders`, nhận các query parameter tùy chọn, trả về `PagedModel` và công bố link để client khám phá khả năng tìm kiếm mà không phải tự đoán URL.

## 1. Search endpoint trong REST API

Một collection endpoint thường hỗ trợ hai cách truy cập:

- Lấy collection với các điều kiện mặc định.
- Tìm một tập con của collection bằng filter do client gửi.

Ví dụ:

~~~http
GET /orders?status=PAID&customer=nguyen&page=0&size=20&sort=createdAt,desc
~~~

Request trên tìm các đơn hàng đã thanh toán, tên khách hàng khớp từ khóa `nguyen`, lấy trang đầu gồm tối đa 20 phần tử và sắp xếp theo thời điểm tạo giảm dần.

Search endpoint thường là một `GET` trên collection resource. Các điều kiện tìm kiếm nằm trong query string vì chúng mô tả tập kết quả mà client muốn đọc. Endpoint không tạo hay thay đổi đơn hàng.

Một contract đơn giản có thể như sau:

| Query parameter | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `status` | Enum | Lọc theo trạng thái |
| `customer` | String | Tìm theo tên hoặc mã khách hàng |
| `createdFrom` | ISO date | Ngày tạo từ |
| `createdTo` | ISO date | Ngày tạo đến |
| `page` | Integer | Trang cần lấy |
| `size` | Integer | Số phần tử mỗi trang |
| `sort` | String, lặp được | Thuộc tính và hướng sắp xếp |

Tên và kiểu query parameter là một phần của API contract. Hãy chọn tên ổn định, dễ hiểu và không phụ thuộc vào tên cột trong database.

## 2. Vì sao tìm kiếm thường dùng GET?

GET phù hợp khi thao tác chỉ đọc dữ liệu. Nó có semantics safe và idempotent theo HTTP: gửi lại cùng request không yêu cầu server thay đổi trạng thái nghiệp vụ.

Ví dụ:

~~~http
GET /orders?status=PAID&createdFrom=2026-01-01
~~~

Một số lợi ích của GET:

- URL có thể được bookmark hoặc chia sẻ.
- Proxy và cache có thể áp dụng chính sách cache cho request đọc.
- Client có thể theo dõi request và link tìm kiếm bằng công cụ HTTP thông thường.
- Query parameters được thể hiện rõ trong URI template.

Không nên gửi request body trong GET để chứa bộ lọc. Hành vi của GET body không có semantics thống nhất giữa các server, proxy và client.

Query string có thể xuất hiện trong access log, browser history và một số header referrer. Không đưa mật khẩu, token, dữ liệu cá nhân nhạy cảm hoặc nội dung bí mật vào search parameter. Với bộ lọc rất lớn hoặc dữ liệu cần giữ kín, cân nhắc một contract POST search riêng và đánh giá rõ hệ quả về cache, logging và semantics HTTP.

## 3. Thiết kế query parameters rõ ràng

Query parameters nên mô tả điều kiện tìm kiếm theo một quy ước nhất quán.

Ví dụ:

~~~http
GET /orders?status=PAID&status=SHIPPED&customer=an&createdFrom=2026-01-01&createdTo=2026-03-31
~~~

Một số quy tắc hữu ích:

- Dùng cùng một định dạng ngày, chẳng hạn ISO-8601 `yyyy-MM-dd`.
- Xác định rõ khoảng ngày có bao gồm hai đầu mút hay không.
- Xác định rõ cách so khớp chuỗi: chính xác, bắt đầu bằng hay chứa chuỗi.
- Xác định rõ query parameter có thể lặp lại hay chỉ nhận một giá trị.
- Quy định cách xử lý giá trị rỗng và khoảng trắng.
- Dùng `page`, `size` và `sort` nhất quán với Spring Data Web nếu không có lý do thay đổi.

Ví dụ filter theo khoảng thời gian thường được hiểu là:

~~~text
createdFrom <= createdAt <= createdTo
~~~

Nếu dữ liệu lưu timestamp có cả giờ và múi giờ, nên chuyển ngày bắt đầu/kết thúc thành khoảng thời gian có timezone rõ ràng tại service layer. Tránh so sánh chuỗi ngày hoặc cắt timestamp tùy tiện trong controller.

## 4. Khai báo controller nhận filter và Pageable

Spring MVC có thể bind query parameter vào các tham số `@RequestParam`. Spring Data Web tự bind `page`, `size` và `sort` thành `Pageable`.

~~~java
import java.time.LocalDate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
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
    PagedModel<EntityModel<OrderDto>> search(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) String customer,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate createdFrom,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate createdTo,
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            ) Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        OrderSearchCriteria criteria = new OrderSearchCriteria(
            status, customer, createdFrom, createdTo
        );

        validate(criteria);
        validateSort(pageable);

        Page<Order> page = orderService.search(criteria, pageable);

        PagedModel<EntityModel<OrderDto>> model =
            pagedAssembler.toModel(page, orderAssembler);

        model.add(searchLink());
        return model;
    }
}
~~~

`OrderSearchCriteria` gom các filter thành một đối tượng để service nhận một contract rõ ràng:

~~~java
public record OrderSearchCriteria(
    OrderStatus status,
    String customer,
    LocalDate createdFrom,
    LocalDate createdTo
) {}
~~~

Controller đảm nhận việc binding HTTP input và trả representation. Service xử lý quy tắc tìm kiếm, còn repository thực thi truy vấn. Cách phân chia này giúp controller không chứa logic truy vấn hoặc xử lý chuỗi phức tạp.

## 5. Xây dựng truy vấn tìm kiếm ở service/repository

Với Spring Data JPA, một repository có thể mở rộng `JpaSpecificationExecutor` để kết hợp các filter tùy chọn với `Pageable`.

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long>,
                JpaSpecificationExecutor<Order> {
}
~~~

Một Specification có thể thêm predicate tùy theo filter được gửi:

~~~java
import java.util.Locale;

public Page<Order> search(
        OrderSearchCriteria criteria,
        Pageable pageable) {

    Specification<Order> specification = (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (criteria.status() != null) {
            predicates.add(
                cb.equal(root.get("status"), criteria.status())
            );
        }

        if (criteria.customer() != null
                && !criteria.customer().isBlank()) {
            Join<Order, Customer> customer =
                root.join("customer", JoinType.INNER);

            predicates.add(
                cb.like(
                    cb.lower(customer.get("name")),
                    "%" + criteria.customer().trim().toLowerCase(Locale.ROOT) + "%"
                )
            );
        }

        if (criteria.createdFrom() != null) {
            predicates.add(
                cb.greaterThanOrEqualTo(
                    root.get("createdAt"),
                    criteria.createdFrom().atStartOfDay()
                )
            );
        }

        if (criteria.createdTo() != null) {
            predicates.add(
                cb.lessThan(
                    root.get("createdAt"),
                    criteria.createdTo().plusDays(1).atStartOfDay()
                )
            );
        }

        return cb.and(predicates.toArray(Predicate[]::new));
    };

    return orderRepository.findAll(specification, pageable);
}
~~~

Ví dụ trên giả định `createdAt` là `LocalDateTime` và filter `createdTo` bao gồm toàn bộ ngày được chọn. Nếu entity dùng `Instant`, `OffsetDateTime` hoặc kiểu khác, cần chuyển đổi khoảng ngày theo timezone nghiệp vụ trước khi tạo predicate.

Spring Data áp dụng `Pageable` trong truy vấn, vì vậy database xử lý filter, sort và giới hạn trang. Không nên tải toàn bộ đơn hàng về bộ nhớ Java rồi mới lọc, sắp xếp và cắt trang.

## 6. Validate filter và giới hạn truy vấn

Search endpoint là một contract công khai. Không nên chấp nhận mọi input mà không có giới hạn.

Các kiểm tra thường cần:

- `createdFrom` không được sau `createdTo`.
- Chuỗi tìm kiếm có độ dài tối đa hợp lý.
- Enum chỉ nhận các giá trị hợp lệ.
- `size` có giới hạn trên để tránh truy vấn quá lớn.
- `sort` chỉ nhận các thuộc tính được API công bố.
- Số lượng filter lặp lại được giới hạn nếu endpoint hỗ trợ collection.
- Chuẩn hóa khoảng trắng và chữ hoa/chữ thường theo quy tắc nghiệp vụ.

Ví dụ kiểm tra khoảng ngày và từ khóa:

~~~java
private void validate(OrderSearchCriteria criteria) {
    if (criteria.createdFrom() != null
            && criteria.createdTo() != null
            && criteria.createdFrom().isAfter(criteria.createdTo())) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "createdFrom must be before or equal to createdTo"
        );
    }

    if (criteria.customer() != null
            && criteria.customer().length() > 100) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "customer query is too long"
        );
    }
}
~~~

Với sort, dùng allow-list để client chỉ được chọn những thuộc tính đã được thiết kế:

~~~java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "id",
    "status",
    "createdAt",
    "totalAmount"
);

private void validateSort(Pageable pageable) {
    for (Sort.Order order : pageable.getSort()) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported sort property"
            );
        }
    }
}
~~~

Spring Data bind giá trị filter vào tham số truy vấn, nhưng sort key có thể ảnh hưởng trực tiếp đến cấu trúc `ORDER BY`. Không nối chuỗi sort do client gửi vào SQL và không chuyển input tùy ý thành `JpaSort.unsafe(...)`.

## 7. Công bố search link bằng IANA relation

Một client cần biết nơi bắt đầu tìm kiếm. Thay vì hard-code `/orders` trong ứng dụng client, server có thể công bố một link với relation `search`.

Spring HATEOAS có hằng số `IanaLinkRelations.SEARCH`. Relation này biểu thị tài nguyên đích có thể được dùng để tìm kiếm trong ngữ cảnh liên kết hiện tại và các tài nguyên liên quan.

Ví dụ:

~~~java
Link searchLink = Link.of(
    "/orders",
    IanaLinkRelations.SEARCH
);
~~~

Trong HAL, link có dạng:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders"
    }
  }
}
~~~

Link này chỉ công bố điểm truy cập. Client vẫn cần biết query parameters mà endpoint hỗ trợ. Để mô tả các tham số mà không buộc client đoán, hãy dùng URI template.

## 8. Mô tả tham số tìm kiếm bằng URI template

URI template theo RFC 6570 cho phép một link công bố các biến mà client có thể cung cấp khi mở rộng URI.

Ví dụ:

~~~text
/orders{?status,customer,createdFrom,createdTo,page,size,sort}
~~~

Phần `{? ... }` khai báo các query parameter tùy chọn. Client có thể cung cấp một số biến hoặc tất cả biến tùy theo nhu cầu.

Tạo link trong Spring HATEOAS:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

Link searchLink = Link.of(
    UriTemplate.of(
        "/orders{?status,customer,createdFrom,createdTo,page,size,sort}"
    ),
    IanaLinkRelations.SEARCH
);
~~~

Link có URI template được Spring HATEOAS nhận biết là templated. Khi tuần tự hóa HAL, response có thể chứa:

~~~json
{
  "_links": {
    "search": {
      "href": "/orders{?status,customer,createdFrom,createdTo,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Client đọc tên biến từ template và mở rộng link theo các điều kiện tìm kiếm. Nó không cần tự đoán endpoint hoặc cấu trúc query string.

## 9. Tạo URI template dựa trên mapping controller

Để tránh lặp lại đường dẫn `/orders`, có thể lấy URI collection từ mapping của controller bằng `WebMvcLinkBuilder`, rồi thêm các biến query.

~~~java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

private Link searchLink() {
    URI collectionUri = linkTo(OrderController.class).toUri();

    UriTemplate template = UriTemplate.of(
        collectionUri
            + "{?status,customer,createdFrom,createdTo,page,size,sort}"
    );

    return Link.of(template, IanaLinkRelations.SEARCH);
}
~~~

Ví dụ giả định `OrderController` có mapping lớp là `/orders`. `linkTo(OrderController.class)` lấy URI gốc từ mapping controller và request hiện tại. Khi thay đổi mapping, link được tạo dựa trên mapping mới thay vì giữ một chuỗi URL cũ trong nhiều nơi.

Nếu controller có mapping phức tạp hoặc nhiều search route, hãy tạo helper riêng cho từng route và kiểm thử kết quả template sau khi serialize.

## 10. Gắn search link vào PagedModel

Search link thường được công bố trên collection representation hoặc API root. Với kết quả tìm kiếm phân trang, có thể thêm link `search` vào `PagedModel` cùng các link điều hướng do `PagedResourcesAssembler` tạo.

~~~java
PagedModel<EntityModel<OrderDto>> model =
    pagedAssembler.toModel(page, orderAssembler);

model.add(searchLink());

return model;
~~~

Một response HAL có thể chứa cả link `self`, `search` và `next`:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders?status=PAID&page=0&size=20&sort=createdAt,desc"
    },
    "search": {
      "href": "/orders{?status,customer,createdFrom,createdTo,page,size,sort}",
      "templated": true
    },
    "next": {
      "href": "/orders?status=PAID&page=1&size=20&sort=createdAt,desc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Ba link có mục đích khác nhau:

| Relation | Ý nghĩa |
|---|---|
| `self` | Truy vấn cụ thể đã tạo ra trang hiện tại |
| `search` | Điểm bắt đầu cho một truy vấn mới với các tham số tùy chọn |
| `next` | Trang tiếp theo của cùng truy vấn hiện tại |

Client có thể theo `next` để tiếp tục truy vấn hiện tại hoặc mở rộng `search` để tạo một truy vấn mới.

## 11. Mở rộng URI template ở phía client

Spring HATEOAS `Link` cung cấp API để đọc biến và mở rộng URI template. Ví dụ:

~~~java
Link searchLink = Link.of(
    UriTemplate.of("/orders{?status,customer,page,size}"),
    IanaLinkRelations.SEARCH
);

Map<String, Object> parameters = Map.of(
    "status", "PAID",
    "customer", "an",
    "page", 0,
    "size", 20
);

Link expanded = searchLink.expand(parameters);
~~~

URI sau khi mở rộng có dạng:

~~~text
/orders?status=PAID&customer=an&page=0&size=20
~~~

Nếu bỏ một biến tùy chọn khỏi map, biến đó không xuất hiện trong URI kết quả. Spring HATEOAS cũng cho phép kiểm tra:

~~~java
searchLink.isTemplated();
searchLink.getVariableNames();
~~~

Các giá trị phải được encode đúng quy tắc URI. Không nối thủ công chuỗi query từ dữ liệu người dùng vì dấu cách, dấu `&`, dấu `+`, ký tự Unicode hoặc ký tự đặc biệt có thể làm hỏng URL hoặc thay đổi ý nghĩa tham số.

## 12. Query parameter collection và tham số lặp

Một số filter cho phép chọn nhiều giá trị. Ví dụ tìm đơn hàng ở nhiều trạng thái:

~~~http
GET /orders?status=PAID&status=SHIPPED
~~~

Controller có thể bind thành collection:

~~~java
@GetMapping
PagedModel<EntityModel<OrderDto>> search(
        @RequestParam(required = false) List<OrderStatus> status,
        Pageable pageable,
        PagedResourcesAssembler<Order> assembler) {
    // Chuyển danh sách trạng thái thành tiêu chí tìm kiếm.
}
~~~

Spring MVC hỗ trợ kiểu tham số lặp như `status=PAID&status=SHIPPED`. Spring HATEOAS mặc định tạo link collection-valued request parameter theo dạng composite, tức lặp lại tên parameter.

Nếu muốn dạng comma-separated:

~~~text
/orders?status=PAID,SHIPPED
~~~

có thể dùng `@NonComposite` với tham số `@RequestParam`:

~~~java
import org.springframework.hateoas.NonComposite;

@GetMapping
PagedModel<EntityModel<OrderDto>> search(
        @NonComposite
        @RequestParam(required = false) Collection<OrderStatus> status,
        Pageable pageable,
        PagedResourcesAssembler<Order> assembler) {
    // Xử lý truy vấn.
}
~~~

Hãy chọn một dạng và giữ nhất quán giữa controller, URI template, link được sinh và client. Đặc biệt, `sort` mặc định của Spring Data thường được gửi lặp lại cho nhiều tiêu chí.

## 13. Giữ filter và sort trong các link phân trang

Khi dùng `PagedResourcesAssembler`, Spring HATEOAS tạo link trang dựa trên request hiện tại và metadata của `Page`. Các filter và sort đang có trong request cần được giữ khi client theo `next` hoặc `prev`.

Ví dụ request:

~~~http
GET /orders?status=PAID&customer=an&page=0&size=20&sort=createdAt,desc&sort=id,asc
~~~

Link tiếp theo có thể giữ nguyên các điều kiện:

~~~text
/orders?status=PAID&customer=an&page=1&size=20&sort=createdAt,desc&sort=id,asc
~~~

Client nên theo link `next` server trả về thay vì tự ghép `page=1`. Server có thể thay đổi quy tắc route, tên tham số hoặc cách mã hóa query trong tương lai; hypermedia giúp client tiếp tục theo liên kết mà không phải biết các chi tiết đó.

Nếu tự tạo custom base link cho `PagedResourcesAssembler`, hãy bảo đảm link chứa đủ các filter và query context cần thiết. Một base link thiếu `status`, `customer` hoặc `sort` có thể khiến các trang tiếp theo thuộc một truy vấn khác.

## 14. Mô tả search form bằng HAL-FORMS affordance

URI template HAL cho biết tên các biến query. Nếu client cần thêm metadata để dựng form, chẳng hạn kiểu hành động và các thuộc tính đầu vào, có thể công bố affordance theo HAL-FORMS.

Spring HATEOAS cho phép xây dựng affordance GET thủ công:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

Link searchForm = Affordances.of(
        linkTo(OrderController.class).withSelfRel()
    )
    .andAfford(HttpMethod.GET)
    .withOutput(OrderDto.class)
    .addParameters(
        QueryParameter.optional("status"),
        QueryParameter.optional("customer"),
        QueryParameter.optional("createdFrom"),
        QueryParameter.optional("createdTo"),
        QueryParameter.optional("page"),
        QueryParameter.optional("size"),
        QueryParameter.optional("sort")
    )
    .withName("search")
    .toLink()
    .withRel(IanaLinkRelations.SEARCH);
~~~

Đây là ví dụ minh họa cách mô tả một GET affordance bằng các query parameter tùy chọn. Link cơ sở được lấy từ mapping lớp của controller. Nếu route tìm kiếm nằm ở mapping khác, hãy tạo link cơ sở trỏ đến đúng route đó.

HAL-FORMS có thể tuần tự hóa metadata affordance thành template trong `_templates`. Client có thể đọc template để dựng search form và gửi GET với các giá trị đã chọn.

Phân biệt hai cơ chế:

| Cơ chế | Thông tin công bố |
|---|---|
| HAL URI template | Tên các biến URI có thể mở rộng |
| HAL-FORMS affordance | HTTP method và metadata input/output để mô tả thao tác |

Không cần HAL-FORMS nếu client chỉ cần biết các query parameter và có thể dựng form theo contract riêng. Dùng affordance khi API muốn công bố thêm metadata về thao tác tìm kiếm.

## 15. Xử lý kết quả rỗng và lỗi đầu vào

Không tìm thấy kết quả không đồng nghĩa endpoint không tồn tại. Một search request hợp lệ nhưng không khớp dữ liệu thường trả `200 OK` với collection rỗng và page metadata phù hợp.

Ví dụ:

~~~http
GET /orders?status=REFUNDED
~~~

Nếu không có đơn hàng nào ở trạng thái đó, response vẫn có thể là một `PagedModel` rỗng:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?status=REFUNDED&page=0&size=20"
    },
    "search": {
      "href": "/orders{?status,customer,createdFrom,createdTo,page,size,sort}",
      "templated": true
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Các trường hợp lỗi nên được phân biệt:

| Tình huống | HTTP status thường dùng |
|---|---|
| Query hợp lệ, không có kết quả | `200 OK` với collection rỗng |
| Ngày bắt đầu sau ngày kết thúc | `400 Bad Request` |
| Enum hoặc định dạng ngày không parse được | `400 Bad Request` |
| Sort key không được hỗ trợ | `400 Bad Request` |
| Người gọi không có quyền tìm kiếm dữ liệu | `403 Forbidden` hoặc `404 Not Found` theo chính sách bảo mật |
| Lỗi hệ thống khi truy vấn | `5xx` phù hợp |

Không trả `404 Not Found` chỉ vì collection không có phần tử khớp filter. Endpoint `/orders` vẫn tồn tại và đã xử lý thành công truy vấn.

## 16. Kiểm thử search endpoint và search link

Kiểm thử nên xác nhận cả kết quả tìm kiếm lẫn khả năng khám phá search link.

Kiểm tra response có search URI template:

~~~java
mockMvc.perform(
        get("/orders")
            .param("status", "PAID")
            .param("customer", "an")
            .param("page", "0")
            .param("size", "20")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.search.href").exists())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Kiểm tra link search chứa các biến cần công bố:

~~~java
mockMvc.perform(
        get("/orders")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links.search.href",
        org.hamcrest.Matchers.containsString("{?status,customer")
    ));
~~~

Kiểm tra filter được bind và trả về đúng tập kết quả:

~~~java
mockMvc.perform(
        get("/orders")
            .param("status", "PAID")
            .param("createdFrom", "2026-01-01")
            .param("createdTo", "2026-01-31")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray());
~~~

Nên bổ sung kiểm thử cho:

- Từng filter riêng lẻ và tổ hợp filter.
- Tham số ngày hợp lệ, không hợp lệ và khoảng ngày đảo ngược.
- Nhiều giá trị của cùng một query parameter.
- Sort mặc định và sort nhiều tiêu chí.
- Sort key không nằm trong allow-list.
- Link `search` có đúng relation và URI template.
- Link `self`, `next` và `prev` giữ filter, sort và page size.
- Kết quả rỗng vẫn trả collection representation hợp lệ.
- HAL-FORMS template xuất hiện khi endpoint công bố search affordance.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Client phải tự đoán URL tìm kiếm | Client phụ thuộc cấu trúc route | Công bố link relation `search` |
| Chỉ có link `/orders`, không có tên biến | Client phải đoán query parameter | Dùng URI template |
| Nhầm `self` với `search` | Client không phân biệt truy vấn hiện tại và điểm bắt đầu tìm kiếm | Dùng relation riêng cho từng mục đích |
| Ghép query string thủ công | Sai encoding hoặc mất tham số | Dùng URI template và URI builder |
| Không validate khoảng ngày | Query sai hoặc tạo kết quả bất ngờ | Kiểm tra filter trước khi truy vấn |
| Cho phép sort key tùy ý | Truy vấn tốn kém hoặc không an toàn | Dùng allow-list |
| Tự tạo link next bằng cách tăng page | Có thể mất filter và sort | Dùng `PagedResourcesAssembler` |
| Trả 404 khi không có kết quả | Nhầm collection rỗng với endpoint không tồn tại | Trả `200 OK` cùng page rỗng |
| Công bố template không khớp controller | Client gửi request không được hỗ trợ | Kiểm thử URI template với endpoint thực |
| Dùng HAL-FORMS khi không cần metadata form | Contract phức tạp không cần thiết | Chỉ thêm affordance khi client cần mô tả form |

## 18. Quy trình thiết kế search endpoint

Khi xây dựng search endpoint với Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định collection resource và các filter mà client cần.
2. Chọn `GET` cho thao tác tìm kiếm chỉ đọc và định nghĩa query parameter rõ ràng.
3. Bind filter bằng `@RequestParam`, ngày bằng định dạng ISO và pagination bằng `Pageable`.
4. Gom điều kiện vào search criteria để service/repository xử lý.
5. Validate filter, giới hạn page size và allow-list sort key.
6. Dùng `PagedResourcesAssembler` để tạo `PagedModel`.
7. Công bố link relation `search` bằng `IanaLinkRelations.SEARCH`.
8. Dùng URI template để liệt kê các query parameter có thể mở rộng.
9. Dùng HAL-FORMS affordance nếu cần mô tả search form cho client.
10. Bảo đảm page links giữ nguyên filter, sort và page size.
11. Kiểm thử kết quả, link relation, template variables, trang rỗng và lỗi input.

Một search endpoint tốt công bố được cả nơi tìm kiếm và cách tìm kiếm. Spring Data giúp bind filter, sort và pagination; Spring HATEOAS giúp mô tả điểm tìm kiếm bằng relation `search`, URI template và tùy chọn HAL-FORMS affordance. Khi client khám phá các thông tin đó từ representation, nó có thể tạo truy vấn và theo dõi kết quả mà không phải phụ thuộc vào URL được hard-code.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates)
- [Spring HATEOAS Reference — Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.link-builder)
- [Spring HATEOAS Reference — Building affordances manually](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.affordances)
- [Spring HATEOAS API — IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API — QueryParameter](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html)
