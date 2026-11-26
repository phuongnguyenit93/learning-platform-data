# Thêm collection model

Sau khi xác định resource Order và URI của collection, bước tiếp theo là trả về một representation có thể mô tả cả danh sách lẫn các đường dẫn điều hướng. Một List<Order> chỉ chứa dữ liệu; client không biết URI của từng order, collection hiện tại hoặc cách chuyển sang trang tiếp theo nếu server không công bố những thông tin đó. Spring HATEOAS cung cấp CollectionModel để biểu diễn một nhóm resource cùng các hypermedia link của collection.

Trong bài thực hành này, bạn sẽ xây dựng endpoint GET /api/orders. Mỗi order trong collection có self link, collection có self link giữ lại filter, và response có embedded relation ổn định. Sau đó, bạn mở rộng endpoint sang phân trang bằng PagedModel và PagedResourcesAssembler để không phải tải toàn bộ dữ liệu khi collection lớn.

## Mục tiêu và đầu ra

Hoàn thành bài này khi API có thể:

- Trả về một collection resource dưới dạng HAL JSON.
- Đặt các item trong _embedded.orders.
- Cung cấp self link cho từng order.
- Cung cấp self link cho collection và giữ lại filter đang áp dụng.
- Trả response hợp lệ khi collection rỗng.
- Hỗ trợ phân trang bằng các link first, prev, self, next, last khi dữ liệu lớn.
- Kiểm thử relation, href, content type và pagination bằng MockMvc.

Phạm vi vẫn là API quản lý đơn hàng bằng Spring HATEOAS. Collection chỉ chứa các order mà người gọi được phép đọc; query service phải áp dụng tenant và authorization scope trước khi trả dữ liệu. Link trong response không thay thế việc kiểm tra quyền ở server.

## Vì sao cần CollectionModel?

Giả sử controller trả về List<OrderSummary>:

~~~java
@GetMapping("/api/orders")
List<OrderSummary> all() {
    return orderQueryService.findAll();
}
~~~

Response JSON có thể chứa một mảng dữ liệu, nhưng không có cấu trúc hypermedia chuẩn để client khám phá collection hoặc theo từng item. Client dễ phải tự tạo URI theo quy ước như /api/orders/{id}. Khi route thay đổi, client phải cập nhật code dù server có thể đã cung cấp đường dẫn đúng.

CollectionModel<T> là một RepresentationModel chứa nhiều phần tử cùng các link ở cấp collection. Mỗi phần tử có thể là EntityModel<T> hoặc một kiểu model riêng kế thừa RepresentationModel. Collection và item vì thế có thể mang link ở đúng cấp:

~~~text
CollectionModel<OrderModel>
  |
  +-- _links.self       -> collection hiện tại
  |
  +-- _embedded.orders
        |
        +-- OrderModel
        |     +-- _links.self -> order thứ nhất
        |
        +-- OrderModel
              +-- _links.self -> order thứ hai
~~~

Không cần thêm link giống nhau vào từng item nếu link đó chỉ có ý nghĩa ở cấp collection. Ngược lại, self link của từng item nên nằm trên chính representation của item.

## Chuẩn bị model cho một order

Giả sử query service trả về projection chỉ chứa dữ liệu cần hiển thị trong danh sách:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderSummary(
        UUID id,
        String status,
        BigDecimal total,
        Instant createdAt) {
}
~~~

Tạo model API riêng để kiểm soát dữ liệu được công bố:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;
    private final Instant createdAt;

    public OrderModel(
            UUID id,
            String status,
            BigDecimal total,
            Instant createdAt) {
        this.id = id;
        this.status = status;
        this.total = total;
        this.createdAt = createdAt;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

OrderModel kế thừa RepresentationModel<OrderModel> nên có thể mang link. Annotation @Relation chỉ định tên relation của item và collection khi Spring HATEOAS serialize embedded resource: mỗi item có relation order, còn collection dùng relation orders. Nhờ đó client không phụ thuộc vào tên class Java hoặc cách đặt tên mặc định của serializer.

Đây là tên relation theo hợp đồng API. Nếu dự án dùng custom relation URI/CURIE, cần cấu hình và tài liệu hóa chúng nhất quán. Ví dụ này dùng relation ngắn orders để tập trung vào collection.

## Tạo assembler cho từng item

Assembler chuyển projection thành OrderModel và gắn self link. Dùng WebMvcLinkBuilder cùng methodOn để tạo href từ mapping controller:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderSummary, OrderModel> {

    @Override
    public OrderModel toModel(OrderSummary order) {
        OrderModel model = new OrderModel(
                order.id(),
                order.status(),
                order.total(),
                order.createdAt());

        model.add(linkTo(methodOn(OrderController.class)
                .one(order.id())).withSelfRel());

        return model;
    }
}
~~~

Assembler chỉ chịu trách nhiệm tạo representation và link. Việc tải dữ liệu, lọc theo tenant, kiểm tra người gọi có được xem order hay không thuộc query/application service. Không đặt truy vấn repository trong toModel, vì collection có nhiều item có thể gây N+1 query.

## Tạo collection endpoint bằng CollectionModel

Query service có thể trả danh sách projection đã được giới hạn theo filter:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orderRepository;

    OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    List<OrderSummary> findAll(String status) {
        return orderRepository.findSummaries(status);
    }

    OrderSummary findById(UUID id) {
        return orderRepository.findSummaryById(id);
    }
}
~~~

OrderRepository.findSummaries và findSummaryById là các phương thức projection do ứng dụng triển khai. Chúng cần áp dụng tenant/security scope ở tầng truy vấn hoặc application service, đồng thời chỉ tải các field cần thiết cho danh sách và item.

Controller chuyển các projection thành item model, rồi gói chúng trong CollectionModel:

~~~java
import java.util.List;
import java.util.UUID;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderQueryService queryService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderQueryService queryService,
            OrderModelAssembler assembler) {
        this.queryService = queryService;
        this.assembler = assembler;
    }

    @GetMapping(
            path = "/api/orders",
            produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<OrderModel> all(
            @RequestParam(required = false) String status) {

        List<OrderModel> orders = queryService.findAll(status).stream()
                .map(assembler::toModel)
                .toList();

        Link self = linkTo(methodOn(OrderController.class)
                .all(status)).withSelfRel();

        if (orders.isEmpty()) {
            return CollectionModel.empty(OrderModel.class).add(self);
        }

        return CollectionModel.of(orders, self);
    }

    @GetMapping("/api/orders/{id}")
    OrderModel one(@PathVariable UUID id) {
        return assembler.toModel(queryService.findById(id));
    }
}
~~~

MediaTypes.HAL_JSON_VALUE yêu cầu endpoint công bố HAL JSON. Ứng dụng cần có HAL message converter do Spring HATEOAS auto-configuration đăng ký; client cũng cần gửi Accept: application/hal+json.

CollectionModel.empty(OrderModel.class) cung cấp fallback element type khi collection không có item. Điều này giúp relation của embedded collection vẫn có thể được xác định từ kiểu model đã khai báo. Collection rỗng vẫn có self link để client hiểu resource collection tồn tại và có thể điều hướng hoặc thay đổi filter.

## Hiểu response HAL của collection

Với hai order, response có thể có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "6c4b2b1a-5f0f-4bd2-9e12-8b1b5c61a001",
        "status": "PENDING",
        "total": 1250000.00,
        "createdAt": "2026-11-26T08:30:00Z",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/6c4b2b1a-5f0f-4bd2-9e12-8b1b5c61a001"
          }
        }
      },
      {
        "id": "d62e36c1-7e84-47c0-99d2-1c99d1f04002",
        "status": "APPROVED",
        "total": 890000.00,
        "createdAt": "2026-11-25T14:10:00Z",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/d62e36c1-7e84-47c0-99d2-1c99d1f04002"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
~~~

_embedded.orders là collection item relation được đặt bởi @Relation. Mỗi order có self link riêng. _links.self ở cấp ngoài đại diện cho chính collection. Client có thể lấy collection từ API root, đọc item, rồi theo self link của item để lấy representation chi tiết.

Nếu request dùng ?status=PENDING, self link collection phải giữ query parameter đó. Không tạo link collection chỉ đến /api/orders nếu nó làm mất ngữ cảnh filter mà client đang xem.

## Thêm relation điều hướng ở cấp collection

Collection có thể công bố link đến các collection hoặc tài nguyên liên quan:

~~~java
Link customers = linkTo(methodOn(CustomerController.class)
        .all()).withRel("customers");

Link products = linkTo(methodOn(ProductController.class)
        .all()).withRel("products");

CollectionModel<OrderModel> collection =
        CollectionModel.of(orders, self, customers, products);
~~~

Chỉ thêm relation thực sự hữu ích cho luồng client. Nếu collection có nhiều link giống nhau ở mọi item, đặt chúng ở cấp collection để giảm payload và tránh lặp semantics. Relation tùy chỉnh nên dùng URI ổn định hoặc CURIE theo quy ước API.

Đối với link action như create, có thể công bố trên collection khi người gọi có quyền tạo order. Nhưng link chỉ là thông tin điều hướng; endpoint POST vẫn phải kiểm tra quyền và validate request.

## Xử lý collection rỗng

Collection không có item vẫn là một resource hợp lệ. Response nên giữ status 200 và self link của collection; không trả 404 chỉ vì không có phần tử nào phù hợp filter.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders?status=UNKNOWN"
    }
  }
}
~~~

Không cần tạo item giả để serializer sinh _embedded.orders. Dùng fallback type khi tạo CollectionModel.empty(OrderModel.class). Test collection rỗng riêng để chắc chắn API không ném lỗi do không suy ra được relation.

## Khi collection lớn: chuyển sang PagedModel

CollectionModel phù hợp với danh sách nhỏ hoặc kết quả đã được giới hạn. Không tải hàng chục nghìn order vào bộ nhớ chỉ để gói chúng trong một collection. Khi cần pagination, query service trả Page<OrderSummary> và Spring Data cung cấp PagedResourcesAssembler để tạo PagedModel<OrderModel> cùng page metadata và navigation links.

Query service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
class PagedOrderQueryService {

    private final OrderRepository orderRepository;

    PagedOrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    Page<OrderSummary> findAll(String status, Pageable pageable) {
        return orderRepository.findSummaries(status, pageable);
    }
}
~~~

Controller dùng PagedResourcesAssembler:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.data.web.PageableDefault;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@RestController
class PagedOrderController {

    private final PagedOrderQueryService pagedOrderQueryService;
    private final OrderModelAssembler assembler;

    PagedOrderController(
            PagedOrderQueryService pagedOrderQueryService,
            OrderModelAssembler assembler) {
        this.pagedOrderQueryService = pagedOrderQueryService;
        this.assembler = assembler;
    }

    @GetMapping(
            path = "/api/orders",
            produces = MediaTypes.HAL_JSON_VALUE)
    PagedModel<OrderModel> all(
            @RequestParam(required = false) String status,
            @PageableDefault(
                    size = 20,
                    sort = "createdAt",
                    direction = Sort.Direction.DESC)
            Pageable pageable,
            PagedResourcesAssembler<OrderSummary> pagedAssembler) {

        Page<OrderSummary> page =
                pagedOrderQueryService.findAll(status, pageable);
        return pagedAssembler.toModel(page, assembler);
    }
}
~~~

PagedOrderController là biến thể thay cho handler collection không phân trang trước đó; chỉ đăng ký một controller xử lý GET /api/orders trong ứng dụng. Nếu chuyển sang phiên bản này, bỏ method all khỏi OrderController nhưng giữ method one để assembler tiếp tục tạo self link cho từng item. PagedResourcesAssembler dùng page metadata để tạo link điều hướng và chuyển từng phần tử qua OrderModelAssembler.

Spring Boot thường tự cấu hình Spring Data web support khi dependency Spring Data phù hợp có mặt. Trong cấu hình MVC tùy chỉnh, bật @EnableSpringDataWebSupport nếu cần đăng ký Pageable resolver và assembler. Repository cần thực hiện pagination ở database, không lấy toàn bộ danh sách rồi cắt trang trong Java.

Một response phân trang HAL thường có metadata và link:

~~~json
{
  "_embedded": {
    "orders": []
  },
  "page": {
    "size": 20,
    "totalElements": 63,
    "totalPages": 4,
    "number": 1
  },
  "_links": {
    "first": {
      "href": "/api/orders?page=0&size=20"
    },
    "prev": {
      "href": "/api/orders?page=0&size=20"
    },
    "self": {
      "href": "/api/orders?page=1&size=20"
    },
    "next": {
      "href": "/api/orders?page=2&size=20"
    },
    "last": {
      "href": "/api/orders?page=3&size=20"
    }
  }
}
~~~

Đây là response minh họa cho trang thứ hai. Link thực tế còn phải giữ filter, sort và các tham số liên quan. Client nên theo href next hoặc prev từ response, không tự tăng page number và dựng URL.

## Giữ filter và sort trong pagination links

Khi collection được lọc theo trạng thái:

~~~http
GET /api/orders?status=PENDING&page=0&size=20&sort=createdAt,desc
~~~

Link next phải giữ status=PENDING và sort tương ứng. PagedResourcesAssembler dựa trên request hiện tại để tạo navigation links; hãy kiểm thử behavior này thay vì giả định. Query service vẫn phải nhận cùng filter và áp dụng nó vào truy vấn.

Ví dụ controller phía trên đặt page mặc định là 20 item và sort theo createdAt giảm dần. Có thể đặt max page size bằng cấu hình Spring Data web hoặc validate pageable.getPageSize() ở boundary. Không cho client yêu cầu một page quá lớn làm tăng memory và query cost.

## Kiểm thử collection response bằng MockMvc

Kiểm thử cần xác nhận media type, embedded relation, item self link và collection self link. Ví dụ dùng WebMvcTest:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderCollectionTests {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderQueryService queryService;

    @Test
    void returnsEmbeddedOrdersWithLinks() throws Exception {
        UUID id = UUID.fromString(
                "6c4b2b1a-5f0f-4bd2-9e12-8b1b5c61a001");
        given(queryService.findAll("PENDING")).willReturn(List.of(
                new OrderSummary(
                        id,
                        "PENDING",
                        new BigDecimal("1250000.00"),
                        Instant.parse("2026-11-26T08:30:00Z"))));

        mockMvc.perform(get("/api/orders")
                        .param("status", "PENDING")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("status=PENDING")))
                .andExpect(jsonPath("$._embedded.orders[0].id")
                        .value(id.toString()))
                .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
                        .value(endsWith("/api/orders/" + id)));
    }
}
~~~

Test dùng Import(OrderModelAssembler.class) để nạp assembler thật vào MVC slice. Nếu ứng dụng bật Spring Security, cấu hình principal test phù hợp hoặc dùng WithMockUser; không vô hiệu hóa authorization trong test contract mà không có lý do.

Kiểm thử collection rỗng:

~~~java
@Test
void returnsAnEmptyCollectionWithSelfLink() throws Exception {
    given(queryService.findAll("UNKNOWN")).willReturn(List.of());

    mockMvc.perform(get("/api/orders")
                    .param("status", "UNKNOWN")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Không bắt buộc kiểm tra _embedded.orders có tồn tại khi collection rỗng; HAL serializer có thể bỏ embedded section không có phần tử. Điều cần giữ là response hợp lệ, status đúng và self link của collection còn đó.

## Kiểm thử pagination

Với endpoint dùng PagedResourcesAssembler, tạo test có nhiều trang và xác nhận page metadata cùng các relation:

~~~java
mockMvc.perform(get("/api/orders")
        .param("status", "PENDING")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(5))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists());
~~~

Test fixture phải trả Page<OrderSummary> có metadata tương ứng và cấu hình PagedResourcesAssembler trong application context. Thêm test trang cuối để xác nhận không có next, và test trang giữa để kiểm tra prev. Lấy href từ response rồi gọi tiếp bằng MockMvc hoặc HTTP client test; xác nhận filter và sort không bị mất.

Không hard-code toàn bộ href nếu host, context path hoặc cấu hình proxy có thể thay đổi. Kiểm tra relation tồn tại, parse URI và xác nhận path/query semantics cần thiết.

## Những lỗi thường gặp khi thêm collection model

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả List thay vì CollectionModel | Client thiếu link điều hướng ở cấp collection. | Bọc item trong CollectionModel và thêm collection links. |
| Không gắn self link cho từng item | Client phải tự ghép URI để xem chi tiết. | Gắn self link trong assembler của item. |
| Không định nghĩa embedded relation | Tên _embedded phụ thuộc convention hoặc khó ổn định. | Dùng @Relation hoặc relation provider đã cấu hình. |
| Collection rỗng không có fallback type | Serializer không xác định được relation embedded. | Dùng CollectionModel.empty(OrderModel.class). |
| Đưa mọi link vào từng item | Payload lặp và khó hiểu phạm vi link. | Đặt link collection ở cấp ngoài. |
| Tải toàn bộ dữ liệu rồi mới phân trang | Tốn memory và database/network. | Dùng Page và PagedResourcesAssembler. |
| Tự dựng href next bằng cách tăng page | Dễ mất filter/sort và phụ thuộc URI convention. | Theo link pagination server trả về. |
| Không giới hạn page size | Client có thể yêu cầu response quá lớn. | Đặt default/max page size ở server. |
| Dựa vào link để bảo vệ action | Client có thể gọi endpoint trực tiếp. | Kiểm tra authorization tại application service/controller. |
| Assembler truy vấn repository cho từng item | N+1 query khi tạo collection. | Query projection theo batch và giữ assembler thuần mapping. |

## Bài tập thực hành

Hãy hoàn thiện collection cho Orders API:

1. Tạo OrderModel kế thừa RepresentationModel và đặt relation order/orders.
2. Tạo OrderModelAssembler gắn self link cho mỗi item.
3. Tạo GET /api/orders trả CollectionModel<OrderModel>.
4. Thêm filter status và bảo đảm self link giữ filter.
5. Xử lý collection rỗng bằng fallback type.
6. Dùng MockMvc kiểm tra HAL content type, _embedded.orders và self links.
7. Mở rộng query thành Page<OrderSummary> và trả PagedModel<OrderModel>.
8. Kiểm tra link next/prev giữ filter và sort.

## Tiêu chí nghiệm thu

Collection model sẵn sàng khi:

- Endpoint trả đúng media type HAL theo Accept đã công bố.
- Collection có self link.
- Mỗi item có self link trỏ đến canonical item URI.
- Embedded relation ổn định và đúng tên orders.
- Collection rỗng vẫn trả response 200 cùng self link.
- Filter hiện tại được giữ trong collection link.
- Pagination dùng page metadata và link do server tạo.
- Query service áp dụng tenant/authorization scope trước khi tạo collection.
- Assembler không truy vấn database và không chứa business transition logic.
- Tests kiểm tra item links, collection links, empty collection và pagination behavior.

## Kết quả của bài

Sau bài này, GET /api/orders không còn chỉ trả về một danh sách dữ liệu. Nó trả một collection resource có embedded order representations và link để client tiếp tục điều hướng. CollectionModel phù hợp với collection hữu hạn; PagedModel cùng PagedResourcesAssembler phù hợp khi cần pagination ở quy mô dữ liệu lớn.

Hãy kiểm tra response như một client: bắt đầu từ collection link, đọc relation orders, theo self link của một item và dùng pagination link do server công bố. Khi client có thể khám phá collection mà không phải tự đoán URI, resource model của Orders API đã có nền tảng hypermedia rõ ràng.
