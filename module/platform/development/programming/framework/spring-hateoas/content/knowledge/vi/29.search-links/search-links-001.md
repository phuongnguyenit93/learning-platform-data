# Search resource (tài nguyên tìm kiếm)

Một REST API thường cần cho client tìm kiếm tài nguyên theo từ khóa hoặc điều kiện lọc. Client có thể cần tìm đơn hàng theo trạng thái, khách hàng, khoảng thời gian hoặc nội dung mô tả. Nếu client phải tự biết endpoint tìm kiếm và tự ghép tên query parameter vào URL, nó sẽ phụ thuộc vào cấu trúc URI của server.

Spring HATEOAS cho phép công bố một liên kết tìm kiếm bằng relation search. Link này có thể chứa URI template với các biến query parameter để client tự mở rộng theo tiêu chí tìm kiếm. Khi cần mô tả chi tiết hơn về thao tác GET và các tham số đầu vào, có thể gắn affordance vào link. Nhờ vậy, client khám phá được nơi tìm kiếm và cách gửi tiêu chí mà không cần hard-code endpoint.

Bài học này trình bày cách thiết kế search resource trong Spring HATEOAS, cách dùng IANA relation search, tạo URI template, mô tả query parameter bằng affordance, xử lý kết quả tìm kiếm và kiểm thử liên kết.

## 1. Search resource là gì?

Search resource là điểm vào mà client sử dụng để khám phá hoặc thực hiện truy vấn trên một tập tài nguyên. Ví dụ, API đơn hàng có thể cung cấp:

- Collection resource: danh sách đơn hàng.
- Search resource: endpoint tìm đơn hàng theo tiêu chí.
- Item resource: một đơn hàng cụ thể.

Client không cần biết trước đường dẫn tìm kiếm nếu collection công bố link relation search.

~~~mermaid
flowchart TD
    A["API root"] --> B["orders collection"]
    B -->|"search"| C["search resource"]
    C -->|"query parameters"| D["filtered result collection"]
    D -->|"self"| E["order item"]
~~~

Search resource có thể là một endpoint riêng như /api/orders/search, hoặc cùng URI collection /api/orders nhưng hỗ trợ query parameter. Điều quan trọng là link relation và hợp đồng tham số cho client biết cách khám phá thao tác tìm kiếm.

## 2. Relation search theo IANA

Spring HATEOAS cung cấp IanaLinkRelations.SEARCH, tương ứng relation search trong danh mục IANA. Relation này biểu thị một tài nguyên có thể được sử dụng để tìm kiếm trong ngữ cảnh của link hiện tại và các tài nguyên liên quan.

Có thể tạo link đơn giản:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link search = Link.of(
        "/api/orders/search",
        IanaLinkRelations.SEARCH
);
~~~

Trong representation HAL, link được hiển thị như sau:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/api/orders/search"
    }
  }
}
~~~

Relation search cho client biết ý nghĩa của link. Nó không tự mô tả các query parameter, kiểu dữ liệu, giá trị hợp lệ hoặc cách mở rộng URI. Để mô tả các thông tin đó, dùng URI template hoặc affordance.

## 3. Vì sao nên dùng URI template?

Một search endpoint thường nhận các query parameter tùy chọn. Ví dụ:

~~~http
GET /api/orders/search?q=spring&status=PAID&customerId=7
~~~

Nếu client phải tự ghép URI, nó cần biết:

- Tên endpoint /api/orders/search.
- Tên tham số q, status, customerId.
- Cách nối nhiều tham số bằng ? và &.
- Cách encode giá trị chứa dấu cách, dấu & hoặc ký tự đặc biệt.

URI template công bố cấu trúc tham số trong link. Client chỉ cần cung cấp giá trị cho các biến:

~~~text
/api/orders/search{?q,status,customerId}
~~~

Ký hiệu {?q,status,customerId} cho biết các biến là query parameter. Client không phải tự đoán cấu trúc URI; nó chỉ mở rộng template bằng những giá trị muốn tìm kiếm.

## 4. Tạo URI template bằng Spring HATEOAS

Spring HATEOAS cung cấp UriTemplate, TemplateVariable và Link để tạo link có biến. Ví dụ:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of("/api/orders/search")
        .with(TemplateVariable.requestParameter("q"))
        .with(TemplateVariable.requestParameter("status"))
        .with(TemplateVariable.requestParameter("customerId"));

Link search = Link.of(template, IanaLinkRelations.SEARCH);
~~~

TemplateVariable.requestParameter(...) tạo một biến query parameter tùy chọn. Link.of(UriTemplate, LinkRelation) kết hợp template với relation search.

Có thể kiểm tra link:

~~~java
assertThat(search.getRel()).isEqualTo(IanaLinkRelations.SEARCH);
assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
        .containsExactly("q", "status", "customerId");
~~~

Khi serialize theo HAL, link được biểu diễn:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/api/orders/search{?q,status,customerId}",
      "templated": true
    }
  }
}
~~~

templated: true giúp client nhận biết rằng href chứa biến cần được mở rộng trước khi gửi request.

## 5. Mở rộng URI template ở phía client

Client có thể mở rộng link bằng cách truyền map giá trị:

~~~java
import java.util.Map;

Link concreteSearch = search.expand(Map.of(
        "q", "spring hateoas",
        "status", "PAID",
        "customerId", 7
));
~~~

Kết quả là một link URI cụ thể, tương đương:

~~~text
/api/orders/search?q=spring%20hateoas&status=PAID&customerId=7
~~~

Giá trị có ký tự đặc biệt được encode theo quy tắc URI template. Không nối chuỗi thủ công như "?q=" + query, vì cách đó dễ tạo URI sai khi giá trị có dấu cách, dấu &, dấu + hoặc ký tự Unicode.

Nếu bỏ một biến tùy chọn khi mở rộng, biến đó sẽ không xuất hiện trong URI kết quả:

~~~java
Link paidOrders = search.expand(Map.of(
        "status", "PAID"
));
~~~

URI sau khi mở rộng chỉ chứa status=PAID. Các tiêu chí khác không bắt buộc phải gửi.

## 6. Dùng IANA search relation trong collection resource

Giả sử OrderController quản lý collection đơn hàng. Collection có thể công bố link tìm kiếm cùng link self:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
import org.springframework.web.bind.annotation.GetMapping;
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

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderDto>> all() {
        CollectionModel<EntityModel<OrderDto>> model =
                orderAssembler.toCollectionModel(orderService.findRecent());

        String searchUri = linkTo(OrderController.class)
                .slash("search")
                .toUri()
                .toString();

        UriTemplate searchTemplate = UriTemplate.of(searchUri)
                .with(TemplateVariable.requestParameter("q"))
                .with(TemplateVariable.requestParameter("status"))
                .with(TemplateVariable.requestParameter("customerId"));

        Link search = Link.of(searchTemplate, IanaLinkRelations.SEARCH);

        return model.add(search);
    }
}
~~~

Ví dụ giả định OrderService, OrderDto và OrderModelAssembler đã được khai báo trong ứng dụng. linkTo(OrderController.class) lấy mapping gốc của controller; slash("search") thêm segment tìm kiếm. UriTemplate bổ sung các query parameter tùy chọn.

Các kiểu dữ liệu rút gọn mà những ví dụ sau sử dụng:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}

public record Order(
        Long id,
        OrderStatus status,
        Long customerId
) {
}

public record OrderDto(
        Long id,
        String status
) {
}
~~~

OrderService có thể khai báo các truy vấn được dùng trong ví dụ:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderService {
    List<Order> findRecent();

    List<Order> search(
            String query,
            OrderStatus status,
            Long customerId
    );

    Page<Order> search(
            String query,
            OrderStatus status,
            Pageable pageable
    );
}
~~~

OrderModelAssembler được giả định triển khai RepresentationModelAssembler<Order, EntityModel<OrderDto>> để chuyển từng Order thành EntityModel<OrderDto> và gắn link self.

Nếu controller có mapping /api/orders, link sẽ được tạo từ mapping đó thay vì phải lặp lại URL trong nhiều nơi. Khi thay đổi mapping controller, link được xây dựng từ controller cũng thay đổi theo.

## 7. Khai báo endpoint nhận tiêu chí tìm kiếm

Search endpoint cần nhận các tham số tương ứng với template:

~~~java
import java.util.List;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

// Đặt trong OrderController đã khai báo mapping /api/orders.
@GetMapping(
        value = "/search",
        produces = MediaTypes.HAL_JSON_VALUE
)
public CollectionModel<EntityModel<OrderDto>> search(
        @RequestParam(name = "q", required = false) String query,
        @RequestParam(name = "status", required = false) OrderStatus status,
        @RequestParam(name = "customerId", required = false) Long customerId
) {
    List<Order> results = orderService.search(query, status, customerId);

    return orderAssembler.toCollectionModel(results)
            .add(linkTo(methodOn(OrderController.class)
                    .search(query, status, customerId)).withSelfRel());
}
~~~

Spring MVC bind query parameter vào các tham số phương thức:

| Query parameter | Java parameter | Ý nghĩa |
| --- | --- | --- |
| q | String query | Từ khóa tìm kiếm |
| status | OrderStatus status | Trạng thái đơn hàng |
| customerId | Long customerId | Khách hàng liên quan |

required = false cho phép client chỉ gửi một phần tiêu chí. Service cần xử lý đúng trường hợp tham số vắng mặt, chuỗi rỗng hoặc giá trị không hợp lệ. Với enum, Spring MVC trả lỗi chuyển đổi nếu client gửi một giá trị không thể ánh xạ.

Link self trong kết quả nên phản ánh các tiêu chí thực tế đã dùng. Nhờ đó client có thể quay lại đúng truy vấn hiện tại.

## 8. Giữ query parameter nhất quán trong link

Khi tạo link search, tên biến trong URI template phải khớp với tên mà endpoint nhận. Nếu template công bố customerId nhưng controller nhận customer, client có thể mở rộng thành URI mà endpoint không hiểu.

Nên duy trì một bảng mapping rõ ràng:

| Tên công bố trong template | Tên trên @RequestParam |
| --- | --- |
| q | q |
| status | status |
| customerId | customerId |

Có thể đặt tên Java parameter khác tên query parameter nếu khai báo name hoặc value rõ ràng trong @RequestParam. Hợp đồng HTTP vẫn dựa trên tên query parameter được công bố.

Khi thêm bộ lọc mới, hãy bổ sung cả tham số endpoint và biến template. Nếu chỉ thêm tham số vào controller nhưng không công bố trong link, client HATEOAS không có cách khám phá tham số đó qua search link.

## 9. Search affordance mô tả thao tác GET

URI template cho client biết các biến query có thể được điền. Affordance cung cấp thêm metadata về thao tác, chẳng hạn HTTP method, output model và các tham số đầu vào.

Spring HATEOAS cho phép xây affordance thủ công bằng Affordances:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

Link searchWithAffordance = Affordances.of(search)
        .afford(HttpMethod.GET)
        .withOutput(OrderDto.class)
        .addParameters(
                QueryParameter.optional("q"),
                QueryParameter.optional("status"),
                QueryParameter.optional("customerId")
        )
        .withName("searchOrders")
        .toLink();
~~~

QueryParameter.optional(...) mô tả tham số tìm kiếm không bắt buộc. Nếu tiêu chí nào bắt buộc, có thể dùng QueryParameter.required(...). withOutput(...) mô tả kiểu dữ liệu kết quả; withName(...) đặt tên affordance để client phân biệt thao tác.

QueryParameter tập trung vào tên, giá trị mặc định nếu có và việc tham số có bắt buộc hay không. Nó không mang đầy đủ kiểu Java của tham số. Vì vậy, khi tự xây affordance thủ công, không nên giả định rằng client sẽ nhận được type number chỉ vì query parameter tương ứng với Long ở controller. Nếu giao diện cần metadata kiểu input chi tiết, hãy dùng affordance được suy ra từ handler method hoặc một cơ chế metadata riêng mà media type hỗ trợ. Server vẫn phải chuyển đổi và xác thực giá trị khi nhận request.

Ví dụ trên giả định biến search là link search đã tạo ở phần trước. Có thể gắn affordance này vào representation của collection để media type hỗ trợ affordance render metadata tương ứng.

Khi công bố affordance, hãy thêm searchWithAffordance vào collection thay cho link search đơn giản đã tạo ở phần 6. Không thêm cả hai link cùng relation search nếu client không có lý do để phân biệt chúng.

## 10. HAL và HAL-FORMS thể hiện search link

Với HAL cơ bản, client nhận được link relation search và URI template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/api/orders/search{?q,status,customerId}",
      "templated": true
    }
  }
}
~~~

HAL-FORMS có thể biểu diễn affordance GET thành một template với các property đầu vào. Ví dụ rút gọn:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/api/orders/search"
    }
  },
  "_templates": {
    "searchOrders": {
      "method": "get",
      "properties": [
        {
          "name": "q",
          "required": false
        },
        {
          "name": "status",
          "required": false
        },
        {
          "name": "customerId",
          "required": false
        }
      ]
    }
  }
}
~~~

Đây là hai cách biểu diễn bổ trợ nhau:

- URI template HAL công bố các biến có thể dùng để mở rộng href.
- HAL-FORMS template mô tả một thao tác GET và các trường đầu vào cho giao diện.

Nếu API cần giao diện tìm kiếm sinh tự động, hãy công bố affordance và hỗ trợ media type HAL-FORMS. Nếu chỉ cần client biết tên tham số và tự tạo request, URI template thường đã đủ.

## 11. Tìm kiếm với collection parameter

Một số bộ lọc nhận nhiều giá trị, ví dụ tìm đơn hàng thuộc một trong nhiều trạng thái:

~~~http
GET /api/orders/search?status=PAID&status=SHIPPED
~~~

Controller có thể nhận collection:

~~~java
@GetMapping("/search")
public CollectionModel<EntityModel<OrderDto>> search(
        @RequestParam(name = "status", required = false)
        List<OrderStatus> statuses
) {
    // Tìm các đơn hàng có một trong các trạng thái được gửi.
}
~~~

Theo URI template, collection-valued request parameter có thể được biểu diễn theo dạng composite, lặp lại tên tham số:

~~~text
status=PAID&status=SHIPPED
~~~

Spring MVC hỗ trợ cả dạng lặp tên và dạng phân tách bằng dấu phẩy. Spring HATEOAS mặc định tạo dạng composite. Nếu muốn dạng comma-separated, có thể dùng @NonComposite:

~~~java
import org.springframework.hateoas.NonComposite;

@GetMapping("/search")
public CollectionModel<EntityModel<OrderDto>> search(
        @NonComposite
        @RequestParam(name = "status", required = false)
        List<OrderStatus> statuses
) {
    // ...
}
~~~

Khi dùng collection parameter, hãy giữ cách biểu diễn nhất quán giữa controller, link template và client. Đừng giả định rằng mọi client đều tự hiểu dấu phẩy trong một query value là nhiều giá trị.

## 12. Phân trang và tìm kiếm kết hợp

Search endpoint thường trả về nhiều kết quả, vì vậy có thể kết hợp Pageable và PagedResourcesAssembler:

~~~java
@GetMapping("/search")
public PagedModel<EntityModel<OrderDto>> search(
        @RequestParam(name = "q", required = false) String query,
        @RequestParam(name = "status", required = false) OrderStatus status,
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler
) {
    Page<Order> results = orderService.search(query, status, pageable);
    return pagedAssembler.toModel(results, orderAssembler);
}
~~~

Khi tìm kiếm có phân trang, các link first, prev, self, next và last phải giữ nguyên tiêu chí lọc. Nếu link next chỉ thay page mà làm mất q hoặc status, client sẽ chuyển sang tập kết quả khác.

Spring Data web support và PagedResourcesAssembler có thể tạo link trang dựa trên request hiện tại. Hãy kiểm thử các query parameter tìm kiếm được giữ lại trong link phân trang, đặc biệt khi có sort hoặc filter tùy chỉnh.

## 13. Kiểm thử search link và URI template

Có thể kiểm tra relation, trạng thái templated và danh sách biến bằng unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

class SearchLinkTest {

    @Test
    void exposesSearchRelationWithOptionalQueryVariables() {
        UriTemplate template = UriTemplate.of("/api/orders/search")
                .with(TemplateVariable.requestParameter("q"))
                .with(TemplateVariable.requestParameter("status"));

        Link search = Link.of(template, IanaLinkRelations.SEARCH);

        assertThat(search.getRel()).isEqualTo(IanaLinkRelations.SEARCH);
        assertThat(search.isTemplated()).isTrue();
        assertThat(search.getVariableNames())
                .containsExactly("q", "status");

        Link expanded = search.expand(Map.of("status", "PAID"));
        assertThat(expanded.getHref()).contains("status=PAID");
        assertThat(expanded.getHref()).doesNotContain("{");
    }
}
~~~

Test xác nhận client có thể nhận biết search link và mở rộng một phần biến. Với các giá trị chứa dấu cách hoặc ký tự đặc biệt, nên kiểm thử URI đã được encode thay vì tự ghép chuỗi.

## 14. Kiểm thử search link trong response HAL bằng MockMvc

Một test MVC có thể xác nhận collection công bố relation search:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderSearchLinkMvcTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void exposesTemplatedSearchLink() throws Exception {
        when(orderService.findRecent()).thenReturn(List.of());

        mockMvc.perform(get("/api/orders")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.search.href")
                        .value(org.hamcrest.Matchers.containsString(
                                "/api/orders/search{?q,status,customerId}"
                        )))
                .andExpect(jsonPath("$._links.search.templated")
                        .value(true));
    }
}
~~~

Đây là test slice minh họa. Service được dùng để tải danh sách gần đây cần được mock hoặc cấu hình trong test context. Nếu ứng dụng tạo URI tuyệt đối, hãy kiểm tra phần path và template thay vì cố định hostname hoặc cổng.

## 15. Kiểm thử endpoint search

Kiểm thử endpoint để xác nhận query parameter được bind và chuyển đến service:

~~~java
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void acceptsSearchQueryParameters() throws Exception {
    mockMvc.perform(get("/api/orders/search")
                    .param("q", "spring hateoas")
                    .param("status", "PAID")
                    .param("customerId", "7")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());

    verify(orderService).search(
            "spring hateoas",
            OrderStatus.PAID,
            7L
    );
}
~~~

Test trên giả định OrderService.search có chữ ký nhận ba tiêu chí tương ứng. Có thể bổ sung test chỉ truyền status để bảo đảm các tham số tùy chọn hoạt động độc lập.

Các trường hợp nên kiểm tra:

- Không gửi query parameter nào: endpoint áp dụng mặc định hoặc trả toàn bộ kết quả phù hợp.
- Chỉ gửi một tiêu chí: các tiêu chí còn lại được xem là vắng mặt.
- Gửi enum hoặc ID không hợp lệ: trả lỗi chuyển đổi/validation phù hợp.
- Gửi giá trị có dấu cách hoặc Unicode: URI template mở rộng và encode đúng.
- Kết quả rỗng: response vẫn có cấu trúc collection hypermedia hợp lệ.
- Search link giữ relation search và có đầy đủ biến mà endpoint hỗ trợ.
- Link phân trang giữ nguyên tiêu chí tìm kiếm.

## 16. Thiết kế search query an toàn và ổn định

Query parameter là một phần của hợp đồng API. Hãy đặt tên có ý nghĩa, giữ ổn định và tránh để client phụ thuộc vào tên cột cơ sở dữ liệu.

Ví dụ, nên công bố createdAfter thay vì tên cột nội bộ created_at_utc. Service có thể ánh xạ query parameter sang specification hoặc tiêu chí repository phù hợp.

Một số lưu ý:

- Giới hạn độ dài của từ khóa tìm kiếm.
- Xác thực enum, ID và khoảng ngày.
- Giới hạn số phần tử collection parameter.
- Áp dụng giới hạn page size và timeout phù hợp.
- Không đưa thông tin nhạy cảm vào query string vì URL có thể xuất hiện trong log, lịch sử trình duyệt hoặc hệ thống quan sát.
- Không dùng search link như cơ chế phân quyền; endpoint vẫn phải kiểm tra quyền truy cập.

GET phù hợp với truy vấn an toàn, có thể cache và không thay đổi trạng thái. Nếu truy vấn rất phức tạp hoặc chứa dữ liệu nhạy cảm không nên nằm trong URL, cân nhắc thiết kế một thao tác tìm kiếm bằng POST với input model và affordance phù hợp.

## 17. Những lỗi thường gặp

**Dùng relation tùy ý thay cho search.** Nếu link thực sự dẫn đến tài nguyên tìm kiếm, relation IANA search giúp client hiểu ý nghĩa chuẩn hơn.

**Công bố search link nhưng không có biến.** Client biết endpoint nhưng vẫn phải đoán tên query parameter. Dùng URI template hoặc affordance để công bố tham số.

**Nhầm URI template với endpoint thực thi.** Template chỉ là khuôn URI. Server vẫn cần controller mapping nhận các query parameter tương ứng.

**Tên biến không khớp @RequestParam.** Template công bố customerId nhưng controller nhận customer sẽ làm client gửi sai hợp đồng. Đồng bộ tên tham số.

**Tự nối query string.** Cách này dễ lỗi encode và dấu phân cách. Dùng UriTemplate và Link.expand(...).

**Không phân biệt link và affordance.** Link search công bố đích; affordance mô tả method và query parameter. Dùng affordance khi client cần metadata thao tác chi tiết.

**Làm mất filter khi phân trang.** Link next phải giữ tiêu chí tìm kiếm, sort và các query parameter liên quan.

**Đưa dữ liệu nhạy cảm vào URL.** Query string có thể bị ghi log hoặc lưu trong lịch sử. Chọn phương thức và input model phù hợp với mức độ nhạy cảm của truy vấn.

## 18. Ghi nhớ

Search resource là điểm vào để client tìm kiếm trong một tập tài nguyên. Spring HATEOAS cung cấp IanaLinkRelations.SEARCH để công bố link có ngữ nghĩa tìm kiếm. Link có thể chứa URI template với các query parameter tùy chọn; client mở rộng template bằng giá trị thực tế và không phải tự ghép URL.

UriTemplate, TemplateVariable.requestParameter(...) và Link.of(...) tạo search link có template. Nếu cần mô tả rõ thao tác GET, output model và các tham số, dùng Affordances cùng QueryParameter.optional(...) hoặc required(...). HAL biểu diễn link templated; HAL-FORMS có thể biểu diễn affordance thành template có các property đầu vào.

Endpoint tìm kiếm phải nhận đúng các tham số đã công bố, kiểm tra dữ liệu và giữ tiêu chí lọc trong link phân trang. Kiểm thử cả relation, tên biến, URI expansion, query binding và kết quả hypermedia. Client nên khám phá search qua link server công bố thay vì phụ thuộc vào cấu trúc URI nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – URI Templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates)
- [Spring HATEOAS Reference – Link Relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [UriTemplate API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html)
- [QueryParameter API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html)
