# Kiểm thử link collection

Trong REST API có hypermedia, collection response không chỉ chứa danh sách phần tử. Nó còn công bố link nhận diện collection, các link điều hướng và đôi khi cả link tìm kiếm hoặc tạo tài nguyên. Client dựa vào những relation đó để tiếp tục khám phá API. Vì vậy, kiểm thử collection cần xác nhận cả dữ liệu được nhúng lẫn hợp đồng link mà server trả về.

Với Spring HATEOAS, collection thường được biểu diễn bằng **CollectionModel<T>** hoặc **PagedModel<T>**. Khi serialize thành HAL JSON, link cấp collection xuất hiện trong **_links**, còn các phần tử có thể xuất hiện trong **_embedded** theo collection relation. Mỗi item có thể có self link riêng. Nếu collection được phân trang, response còn có thể công bố **first**, **prev**, **next** và **last**.

Bài học này trình bày cách kiểm thử collection link bằng MockMvc và JsonPath, xác nhận relation và href, kiểm tra tên collection trong _embedded, kiểm thử collection rỗng, phân trang, search URI template, custom relation và các trường hợp lỗi. Mục tiêu là bảo vệ hợp đồng hypermedia để client có thể điều hướng bằng link server công bố.

## 1. Vì sao phải kiểm thử link collection?

Một response collection có thể trả dữ liệu đúng nhưng link sai. Ví dụ, danh sách đơn hàng có đủ phần tử nhưng self link lại trỏ đến collection khác; hoặc link next làm mất bộ lọc hiện tại. Nếu test chỉ kiểm tra status 200 và số lượng phần tử, lỗi hợp đồng đó vẫn có thể lọt qua.

Các lỗi thường gặp:

- Thiếu link self ở cấp collection.
- Relation collection trong _embedded đổi tên ngoài ý muốn.
- Item được nhúng nhưng không có self link.
- Href của item trỏ nhầm ID hoặc nhầm controller.
- Link next/prev không giữ filter và sort.
- Link search thiếu biến URI template.
- Media type trả về là JSON thường thay vì HAL JSON.
- Collection rỗng tạo cấu trúc khác với điều client mong đợi.
- Host hoặc context path của link sai khi ứng dụng chạy sau proxy.

Kiểm thử collection link cần xác nhận ba lớp:

1. **Representation**: dữ liệu và cấu trúc embedded đúng.
2. **Navigation**: relation và href đúng với ngữ cảnh collection.
3. **HTTP contract**: status, media type và semantics của endpoint phù hợp.

## 2. Cấu trúc HAL collection cần kiểm tra

Một collection HAL có thể có dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING",
        "_links": {
          "self": {
            "href": "https://api.example.test/orders/ORD-42"
          }
        }
      },
      {
        "id": "ORD-43",
        "status": "DELIVERED",
        "_links": {
          "self": {
            "href": "https://api.example.test/orders/ORD-43"
          }
        }
      }
    ]
  }
}
~~~

Có hai cấp link khác nhau:

| Vị trí | Relation | Ý nghĩa |
|---|---|---|
| $._links.self | self | URI của collection hiện tại |
| $._embedded.orders[0]._links.self | self | URI của item đầu tiên |
| $._embedded.orders[1]._links.self | self | URI của item thứ hai |

Không nhầm self của collection với self của từng item. Collection self dẫn đến danh sách; item self dẫn đến một tài nguyên cụ thể.

Tên orders trong _embedded là collection relation. Tên này có thể được suy ra từ kiểu tài nguyên hoặc khai báo tường minh bằng annotation Relation(collectionRelation = "orders"). Vì đây là một phần hợp đồng JSON, test nên xác nhận tên relation mà client đang sử dụng.

## 3. Chọn đúng công cụ kiểm thử

Spring MVC cung cấp nhiều cách kiểm thử endpoint hypermedia:

| Công cụ | Phạm vi | Khi nên dùng |
|---|---|---|
| MockMvc | Gửi request HTTP giả lập qua Spring MVC | Kiểm tra controller, serializer, media type và link |
| @WebMvcTest | Tạo web slice, chỉ nạp thành phần MVC được chọn | Test nhanh controller và cấu trúc response |
| @SpringBootTest + @AutoConfigureMockMvc | Nạp gần như toàn bộ application context | Kiểm tra cấu hình hypermedia, repository và security tích hợp |
| Unit test assembler | Gọi trực tiếp assembler | Kiểm tra mapping domain object sang model và link |
| Client traversal test | Theo link từ response | Xác nhận href công bố có thể được client sử dụng |

Đối với collection link, MockMvc thường là lớp kiểm thử chính vì nó kiểm tra response sau khi Spring HATEOAS và Jackson đã serialize model. Unit test assembler bổ sung độ chính xác cho logic tạo link. Integration test toàn ứng dụng phù hợp khi relation phụ thuộc cấu hình hoặc repository thực tế.

Không nên chỉ test object Java trước serialization. Một model có link đúng trong bộ nhớ vẫn có thể được serialize với relation hoặc media type không đúng như client nhận được.

## 4. Xây dựng model dùng trong ví dụ

Giả sử API quản lý đơn hàng. Domain object tối giản:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record Order(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Representation dành cho API:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "order",
    collectionRelation = "orders"
)
public record OrderSummary(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Annotation Relation đặt rõ relation của item và collection. Nhờ đó, khi tạo collection model, relation embedded được giữ ổn định ngay cả khi tên class Java thay đổi.

Service được controller sử dụng:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderQueryService {

    List<Order> findAll();

    Page<Order> findAll(Pageable pageable);

    Order findById(UUID id);
}
~~~

Trong bài học, service được mock ở controller test. Nhờ vậy, test tập trung vào HTTP response và hypermedia link thay vì phụ thuộc database.

## 5. Tạo self link cho từng item bằng assembler

Assembler chuyển domain object thành EntityModel và gắn self link:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(Order order) {
        OrderSummary body = new OrderSummary(
            order.id(),
            order.status(),
            order.total()
        );

        return EntityModel.of(
            body,
            linkTo(
                methodOn(OrderController.class).one(order.id())
            ).withSelfRel()
        );
    }
}
~~~

Self link được tạo từ mapping của OrderController.one(...). Nếu path controller thay đổi, assembler vẫn dựa trên mapping thay vì tự nối chuỗi URL từ ID.

Assembler chỉ tạo self cho item. Link self cấp collection được controller hoặc collection assembler bổ sung ở cấp collection. Hai cấp link cần được kiểm tra riêng.

## 6. Controller trả về CollectionModel

Controller có thể chuyển danh sách domain object thành các EntityModel rồi bọc trong CollectionModel:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderQueryService service;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderQueryService service,
            OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderSummary>> all() {
        List<EntityModel<OrderSummary>> items =
            service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        Link self = linkTo(
            methodOn(OrderController.class).all()
        ).withSelfRel();

        return CollectionModel.of(items, self);
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    public EntityModel<OrderSummary> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }
}
~~~

CollectionModel giữ các item và link cấp collection. Khi serialize thành HAL JSON, self link cấp collection xuất hiện ở _links.self; các item được nhóm dưới relation orders trong _embedded.

Nếu collection cần relation search hoặc link khác, hãy bổ sung ở cấp CollectionModel. Không thêm search link vào từng item nếu thao tác tìm kiếm thuộc collection.

Với endpoint phân trang, có thể dùng biến thể sau để tạo PagedModel thay cho CollectionModel:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;

@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<EntityModel<OrderSummary>> page(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> result = service.findAll(pageable);
    return pagedAssembler.toModel(result, assembler);
}
~~~

Đây là biến thể cho endpoint collection phân trang; service cần cung cấp Page<Order> và không dùng đồng thời hai handler GET không phân biệt được trên cùng mapping.

## 7. Thiết lập WebMvcTest

@WebMvcTest nạp controller và hạ tầng MVC liên quan. Service có thể được thay bằng mock; assembler thật được import để kiểm tra link được tạo từ mapping:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderQueryService service;

    // Các test ở những mục sau
}
~~~

Nếu ứng dụng có Spring Security, request có thể cần user hoặc CSRF token tùy endpoint. Dùng cấu hình security test phù hợp với chính sách ứng dụng; không tắt filter một cách mặc định nếu mục tiêu là kiểm tra cả quyền truy cập.

@WebMvcTest không tự nạp mọi bean của ứng dụng. Nếu controller cần mapper, validator hoặc component khác, hãy import bean cần thiết hoặc mock dependency tương ứng.

## 8. Kiểm tra media type và self link cấp collection

Test đầu tiên xác nhận endpoint trả HAL JSON và có self link:

~~~java
@Test
void exposesCollectionSelfLink() throws Exception {
    given(service.findAll()).willReturn(List.of());

    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath("$._links.self.href").value(
            org.hamcrest.Matchers.endsWith("/orders")
        ));
}
~~~

Test này xác nhận:

- Endpoint nhận request GET.
- Client yêu cầu HAL JSON.
- Server trả status 200.
- Content-Type tương thích với application/hal+json.
- Collection response có link self.

Không chỉ kiểm tra chuỗi header bằng cách so sánh cứng nếu server có thể thêm charset hoặc parameter hợp lệ. contentTypeCompatibleWith phù hợp để xác nhận media type chính.

Nếu endpoint không hỗ trợ HAL JSON, test nên thể hiện rõ media type thực tế và kỳ vọng hợp đồng. Đừng để test mặc định không gửi Accept rồi vô tình kiểm tra một representation khác với định dạng client đang sử dụng.

## 9. Kiểm tra embedded collection relation

Với collection có phần tử, test cần xác nhận dữ liệu nằm dưới đúng collection relation:

~~~java
@Test
void embedsOrdersUnderConfiguredCollectionRelation() throws Exception {
    UUID orderId = UUID.fromString(
        "c2d7b8a1-52b0-4a6a-8f10-5d7e8c9a1234"
    );

    Order order = new Order(
        orderId,
        "PROCESSING",
        new BigDecimal("125000")
    );

    given(service.findAll()).willReturn(List.of(order));

    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.orders").isArray())
        .andExpect(jsonPath("$._embedded.orders.length()").value(1))
        .andExpect(jsonPath("$._embedded.orders[0].id")
            .value(orderId.toString()))
        .andExpect(jsonPath("$._embedded.orders[0].status")
            .value("PROCESSING"));
}
~~~

Assertion $._embedded.orders kiểm tra collection relation. Assertion trên item đầu tiên xác nhận dữ liệu đúng với fixture.

Nếu relation được cấu hình thành acme:orders qua CURIE, JSONPath cần dùng cú pháp bracket:

~~~java
jsonPath("$._embedded['acme:orders']").isArray()
~~~

Không nên kiểm tra key mặc định orders khi ứng dụng đã chủ động thay relation. Test phải phản ánh hợp đồng thực tế mà client tiêu thụ.

## 10. Kiểm tra self link của từng item

Sau khi xác nhận collection embedded, kiểm tra mỗi item có self link riêng:

~~~java
@Test
void exposesSelfLinkForEveryEmbeddedOrder() throws Exception {
    UUID firstId = UUID.fromString(
        "c2d7b8a1-52b0-4a6a-8f10-5d7e8c9a1234"
    );
    UUID secondId = UUID.fromString(
        "d3e8c9b2-63c1-4b7b-9a21-6e8f9d0b2345"
    );

    given(service.findAll()).willReturn(List.of(
        new Order(firstId, "PROCESSING", new BigDecimal("125000")),
        new Order(secondId, "DELIVERED", new BigDecimal("89000"))
    ));

    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._embedded.orders[0]._links.self.href"
        ).value(org.hamcrest.Matchers.endsWith(
            "/orders/" + firstId
        )))
        .andExpect(jsonPath(
            "$._embedded.orders[1]._links.self.href"
        ).value(org.hamcrest.Matchers.endsWith(
            "/orders/" + secondId
        )));
}
~~~

Dùng matcher endsWith khi host, scheme hoặc context path có thể thay đổi giữa môi trường. Nếu hợp đồng yêu cầu URI tuyệt đối với host cụ thể, có thể kiểm tra cả host trong một test cấu hình riêng.

Điều quan trọng là href của item thứ nhất phải nhận diện item thứ nhất, và href của item thứ hai phải nhận diện item thứ hai. Không chỉ kiểm tra rằng một trường href tồn tại.

## 11. Kiểm tra quan hệ collection và item không bị đảo

Một lỗi serialization phổ biến là nhầm collection relation với item relation. Ví dụ, item relation là order còn collection relation là orders.

Có thể kiểm tra cấu trúc như sau:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.order").doesNotExist());
~~~

Trong test thực tế, chỉ kiểm tra key item không xuất hiện nếu hợp đồng xác định rõ collection relation phải là orders. Nếu API có một relation khác tên order ở vị trí khác, hãy giới hạn assertion vào đường dẫn JSON cụ thể thay vì cấm tên relation ở toàn response.

Annotation Relation giúp tên relation độc lập với tên class Java. Khi đổi class representation, test này bảo vệ collection key không đổi ngoài ý muốn.

## 12. Kiểm thử collection rỗng

Collection không có phần tử vẫn phải trả representation hợp lệ và self link cấp collection. Tuy nhiên, HAL serializer có thể lược bỏ thuộc tính _embedded khi collection rỗng.

Ví dụ response rỗng có thể là:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
~~~

Vì vậy, test collection rỗng nên xác nhận self link và status, thay vì luôn yêu cầu _embedded.orders phải là mảng rỗng:

~~~java
@Test
void exposesSelfLinkForEmptyCollection() throws Exception {
    given(service.findAll()).willReturn(List.of());

    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Nếu API của ứng dụng cam kết cụ thể rằng collection rỗng luôn có _embedded.orders: [], hãy thêm assertion đó và cấu hình serializer tương ứng. Nếu không có cam kết như vậy, client nên hiểu collection rỗng từ response hợp lệ và metadata liên quan, không dựa vào giả định về một key embedded luôn tồn tại.

## 13. Kiểm tra relation bổ sung ở cấp collection

Collection có thể công bố các relation khác ngoài self, ví dụ link tạo mới hoặc tìm kiếm:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    },
    "create": {
      "href": "/orders"
    },
    "search": {
      "href": "/orders{?status,page,size}",
      "templated": true
    }
  },
  "_embedded": {
    "orders": []
  }
}
~~~

Test relation tùy chỉnh:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.create.href").exists())
    .andExpect(jsonPath("$._links.search.href").exists());
~~~

Không nên kiểm tra mọi relation luôn tồn tại nếu chúng phụ thuộc quyền hoặc trạng thái. Ví dụ, link create có thể chỉ được công bố cho người dùng có quyền tạo đơn hàng. Test cần thiết lập security context đúng với trường hợp đang kiểm tra.

Nếu search link là URI template, kiểm tra cả thuộc tính templated và tên biến được công bố:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(org.hamcrest.Matchers.containsString("{?status,page,size}")));
~~~

Cấu trúc biến cụ thể có thể khác theo cách link builder tạo URI template. Nếu thứ tự biến không phải một phần hợp đồng, nên kiểm tra sự hiện diện của từng tên thay vì khóa cứng toàn bộ chuỗi href.

## 14. Kiểm tra link phân trang

Với PagedModel, collection response có thể công bố các relation điều hướng:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=2"
    },
    "first": {
      "href": "/orders?page=0&size=2"
    },
    "prev": {
      "href": "/orders?page=0&size=2"
    },
    "next": {
      "href": "/orders?page=2&size=2"
    },
    "last": {
      "href": "/orders?page=4&size=2"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 9,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Test nên kiểm tra relation phù hợp với trang hiện tại:

~~~java
mockMvc.perform(get("/orders")
        .param("page", "1")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists())
    .andExpect(jsonPath("$.page.number").value(1));
~~~

Các link điều hướng không xuất hiện giống nhau trên mọi trang. Trang đầu thường không có prev; trang cuối thường không có next. Test cần chọn fixture và số trang phù hợp với relation đang xác minh.

Ví dụ trang đầu:

~~~java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev.href").doesNotExist())
    .andExpect(jsonPath("$._links.next.href").exists());
~~~

Ví dụ trang cuối:

~~~java
mockMvc.perform(get("/orders")
        .param("page", "4")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href").doesNotExist());
~~~

Nếu response dùng một trang duy nhất, cả next và prev có thể vắng mặt. Đây là hành vi hợp lệ, không phải lỗi serialization.

## 15. Kiểm tra filter được giữ trong pagination links

Một lỗi quan trọng là link next làm mất filter hiện tại. Giả sử request:

~~~http
GET /orders?status=PROCESSING&customerId=CUS-7&page=0&size=2
~~~

Link next cần tiếp tục giữ status và customerId:

~~~json
{
  "_links": {
    "next": {
      "href": "/orders?status=PROCESSING&customerId=CUS-7&page=1&size=2"
    }
  }
}
~~~

Test:

~~~java
UUID customerId = UUID.fromString(
    "e4f9d0c3-74d2-4c8c-ab32-7f9a0e1c3456"
);

mockMvc.perform(get("/orders")
        .param("status", "PROCESSING")
        .param("customerId", customerId.toString())
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("status=PROCESSING")))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString(
            "customerId=" + customerId
        )))
    .andExpect(jsonPath("$._links.next.href")
        .value(org.hamcrest.Matchers.containsString("page=1")));
~~~

Test chỉ hợp lệ khi fixture có đủ bản ghi để tồn tại trang tiếp theo. Hãy tạo ít nhất ba kết quả phù hợp nếu page size bằng hai.

Không nên kiểm tra bằng cách tự ghép URL next trong test. Test cần đọc href server công bố và xác nhận các query parameter cần thiết được giữ lại. Nếu cần kiểm tra sâu hơn, lấy href từ JSON rồi gửi request tiếp theo đến URI đó và xác nhận dữ liệu vẫn thỏa filter.

## 16. Kiểm tra link bằng cách theo href thực tế

Một test hypermedia tốt có thể dùng link vừa nhận để gửi request tiếp theo. Điều này chứng minh href không chỉ đúng hình thức mà còn điều hướng đến endpoint có thể sử dụng.

Ví dụ với self link:

~~~java
MvcResult result = mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

String selfHref = JsonPath.read(
    result.getResponse().getContentAsString(),
    "$._links.self.href"
);

URI selfUri = URI.create(selfHref);
mockMvc.perform(get(selfUri.getRawPath())
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

Cần import:

~~~java
import java.net.URI;

import org.springframework.test.web.servlet.MvcResult;

import com.jayway.jsonpath.JsonPath;
~~~

Ví dụ giả định href được tạo trong cùng ứng dụng và path có thể gửi lại qua MockMvc. Nếu href là URI tuyệt đối trên host khác hoặc qua gateway, hãy tách phần path phù hợp hoặc dùng HTTP client integration test để gọi đúng URI đầy đủ.

Không loại bỏ query string nếu nó là một phần của self link collection view. Với URI có query, dùng raw query khi xây request MockMvc:

~~~java
URI selfUri = URI.create(selfHref);
String pathAndQuery = selfUri.getRawPath();
if (selfUri.getRawQuery() != null) {
    pathAndQuery += "?" + selfUri.getRawQuery();
}

mockMvc.perform(get(pathAndQuery)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

Trong code thực tế, chỉ thêm dấu hỏi khi raw query khác null. Mục tiêu là theo đúng URI server đã công bố, không tạo một đường dẫn tương đương bằng phỏng đoán.

## 17. Unit test assembler độc lập

MockMvc xác nhận response sau serialization. Unit test assembler giúp phát hiện lỗi sớm hơn nếu self link item bị tạo sai.

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.assertj.core.api.Assertions.assertThat;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler =
        new OrderModelAssembler();

    @Test
    void createsSelfLinkForEachOrder() {
        UUID id = UUID.fromString(
            "c2d7b8a1-52b0-4a6a-8f10-5d7e8c9a1234"
        );

        Order order = new Order(
            id,
            "PROCESSING",
            new BigDecimal("125000")
        );

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/orders");
        request.setScheme("https");
        request.setServerName("api.example.test");
        request.setServerPort(443);
        RequestContextHolder.setRequestAttributes(
            new ServletRequestAttributes(request)
        );

        EntityModel<OrderSummary> model;
        try {
            model = assembler.toModel(order);
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }

        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
        assertThat(
            model.getRequiredLink(IanaLinkRelations.SELF).getHref()
        ).endsWith("/orders/" + id);
    }
}
~~~

Đoạn test giả định request context cần thiết cho WebMvcLinkBuilder đã được thiết lập. Nếu assembler được gọi ngoài request, có thể dùng MockHttpServletRequest và RequestContextHolder hoặc kiểm tra qua MockMvc để Spring thiết lập context tự động.

Unit test không thay thế MockMvc test vì nó không xác nhận JSON HAL, collection relation hay Content-Type.

## 18. Kiểm tra custom relation và CURIE

Nếu ứng dụng dùng custom relation URI và CURIE, collection key có thể là acme:orders thay vì orders.

Ví dụ response:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    },
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.test/rels/{rel}",
        "templated": true
      }
    ]
  },
  "_embedded": {
    "acme:orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING"
      }
    ]
  }
}
~~~

Test:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies[0].name").value("acme"))
    .andExpect(jsonPath("$._embedded['acme:orders']").exists());
~~~

Tên CURIE và relation phải khớp cấu hình ứng dụng. Nếu dùng nhiều CURIE prefix, hãy kiểm tra từng prefix và relation cụ thể; không giả định luôn có một phần tử đầu tiên trong danh sách nếu serializer hoặc cấu hình biểu diễn theo dạng khác.

## 19. Kiểm tra content negotiation và lỗi media type

Collection endpoint có thể chỉ công bố HAL JSON hoặc hỗ trợ thêm media type khác. Test cần xác nhận rõ behavior đã chọn.

Request yêu cầu HAL JSON:

~~~java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON));
~~~

Request yêu cầu media type không được hỗ trợ có thể trả 406 Not Acceptable nếu endpoint không có representation phù hợp:

~~~java
mockMvc.perform(get("/orders")
        .accept("application/xml"))
    .andExpect(status().isNotAcceptable());
~~~

Kết quả cụ thể phụ thuộc các converter và media type endpoint đã cấu hình. Nếu ứng dụng có XML converter hoặc fallback khác, hãy kiểm thử theo hợp đồng thực tế thay vì mặc định luôn mong 406.

Không dùng test chỉ gửi Accept wildcard để xác nhận HAL. Hãy yêu cầu đúng media type mà client hypermedia sử dụng.

## 20. Kiểm tra link sau reverse proxy hoặc context path

Href có thể được tạo từ request hiện tại. Nếu ứng dụng chạy sau reverse proxy, link có thể sai host, scheme hoặc prefix khi forwarded headers chưa được cấu hình đúng.

Một test có thể gửi forwarded headers:

~~~java
mockMvc.perform(get("/orders")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.test")
        .header("X-Forwarded-Prefix", "/gateway")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.containsString(
            "https://api.example.test"
        )));
~~~

Test này chỉ có ý nghĩa nếu ứng dụng đã cấu hình forwarded header strategy phù hợp. Không phải mọi môi trường MockMvc đều tự xử lý forwarded headers như production proxy. Hãy cấu hình filter hoặc strategy tương ứng rồi xác nhận href thực tế.

Nếu ứng dụng cố ý công bố URI tương đối, hãy kiểm tra dạng tương đối đó thay vì bắt buộc host tuyệt đối.

## 21. Những lỗi thường gặp khi kiểm thử collection link

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra status 200 | Không phát hiện link sai hoặc thiếu | Kiểm tra _links và _embedded |
| Chỉ kiểm tra self cấp collection | Self link của item có thể sai | Kiểm tra self của từng embedded item |
| Hard-code thứ tự phần tử | Test dễ gãy khi thứ tự dữ liệu thay đổi | Sắp xếp fixture hoặc tìm item theo ID |
| Khóa cứng host và port | Test phụ thuộc môi trường | Dùng matcher theo path hoặc cấu hình host riêng |
| Giả định _embedded luôn tồn tại khi collection rỗng | Test thất bại dù response HAL hợp lệ | Kiểm tra self link; chỉ kiểm tra empty array nếu hợp đồng cam kết |
| Nhầm item relation với collection relation | Client không tìm được collection | Kiểm tra Relation và JSONPath đúng |
| Bỏ qua Content-Type | Server có thể trả JSON thường | Kiểm tra MediaTypes.HAL_JSON |
| Kiểm tra next trên trang cuối | Test mong relation không hợp lệ | Chọn fixture và page phù hợp |
| Không kiểm tra filter trong next href | Client chuyển sang tập kết quả khác | Assert các filter được giữ lại |
| Chỉ test assembler | Không xác nhận serialization HAL | Bổ sung MockMvc test |
| Chỉ test MockMvc | Khó xác định lỗi mapping ở assembler | Bổ sung unit test assembler |
| Tắt security cho mọi test | Không bảo vệ behavior quyền truy cập | Test cả user được phép và bị từ chối |

## 22. Quy trình kiểm thử link collection

Khi thêm hoặc thay đổi collection endpoint, hãy kiểm thử theo thứ tự:

1. Gửi GET với Accept là application/hal+json.
2. Xác nhận status và Content-Type.
3. Xác nhận collection self link tồn tại.
4. Xác nhận collection relation trong _embedded đúng tên.
5. Xác nhận dữ liệu embedded khớp fixture.
6. Xác nhận từng item có self link riêng và href nhận diện đúng ID.
7. Kiểm thử collection rỗng theo hợp đồng serialization của ứng dụng.
8. Nếu có search, xác nhận relation và URI template variables.
9. Nếu có pagination, xác nhận first/prev/next/last xuất hiện đúng theo vị trí trang.
10. Xác nhận filter và sort được giữ trong pagination href.
11. Theo href thực tế trong test để chứng minh link có thể sử dụng.
12. Kiểm thử media type không hỗ trợ, security và forwarded headers khi chúng thuộc hợp đồng endpoint.

Kiểm thử collection link giúp bảo vệ phần điều hướng của REST API cùng với dữ liệu nghiệp vụ. Với Spring HATEOAS, hãy xác nhận self ở cấp collection, self ở từng item, collection relation trong _embedded, các relation phân trang và search link sau khi serializer tạo HAL JSON. Khi test dựa trên relation và href thực tế thay vì tự dựng route, client có thể tiếp tục điều hướng ngay cả khi cấu trúc URI của server thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation models and links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring Framework MockMvc Testing](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Boot @WebMvcTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)

