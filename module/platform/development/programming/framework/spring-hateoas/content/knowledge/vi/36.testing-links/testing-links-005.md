# Kiểm thử embedded trong Spring HATEOAS

HAL biểu diễn các tài nguyên được nhúng trong thuộc tính _embedded, còn các liên kết điều hướng nằm trong _links. Khi một API trả về collection, client thường đọc các item từ _embedded và theo self link hoặc association link của từng item để đi tới tài nguyên tiếp theo. Vì vậy, kiểm thử hypermedia cần xác nhận cả dữ liệu embedded, tên relation, cấu trúc lồng nhau và các link đi kèm.

Một response có 200 OK và _links.self vẫn có thể sai nếu collection relation bị đặt tên không đúng, item bị thiếu, thứ tự không ổn định hoặc association đáng lẽ được nhúng lại chỉ xuất hiện dưới dạng link. Bài này tập trung vào cách kiểm tra HAL _embedded bằng Spring HATEOAS, MockMvc và JSONPath, đồng thời phân biệt embedded resource với association link và thuộc tính JSON lồng nhau thông thường.

## 1. Embedded resource trong HAL là gì?

Trong HAL, _links chứa các liên kết có thể theo, còn _embedded chứa representation của tài nguyên được nhúng ngay trong response hiện tại.

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-101",
        "status": "PENDING",
        "_links": {
          "self": { "href": "/orders/o-101" }
        }
      },
      {
        "id": "o-102",
        "status": "SHIPPED",
        "_links": {
          "self": { "href": "/orders/o-102" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
~~~

_embedded.orders chứa các representation của từng đơn hàng. Mỗi item có payload riêng và có thể có _links riêng. _links.self ở cấp ngoài trỏ tới collection; _links.self bên trong từng item trỏ tới đơn hàng tương ứng.

Embedded resource giúp client nhận collection cùng các item trong một response. Client không cần gọi thêm một request cho từng item chỉ để lấy dữ liệu cơ bản của collection.

## 2. Phân biệt _embedded, _links và thuộc tính JSON thông thường

Ba dạng dữ liệu này có ý nghĩa khác nhau:

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Link association | _links.customer.href | Công bố URI của tài nguyên khách hàng để client điều hướng. |
| Embedded association | _embedded.customer | Đưa representation khách hàng vào response hiện tại. |
| Nested JSON property | customer.name | Dữ liệu lồng nhau thông thường; không tự mang semantics HAL relation. |

Không nên chỉ kiểm tra chuỗi customer xuất hiện trong JSON rồi kết luận association đã được embedded. Hãy kiểm tra đúng đường dẫn $._embedded.customer nếu hợp đồng yêu cầu embedded relation, hoặc $._links.customer.href nếu hợp đồng chỉ yêu cầu link.

Một response có thể chứa cả link và embedded representation cho cùng một relation. Khi đó client có thể đọc dữ liệu ngay trong response và vẫn có URI để tải bản đầy đủ hoặc điều hướng tiếp.

## 3. Xác định relation của embedded resource

Tên relation trong _embedded là một phần của hợp đồng HAL. Với Spring HATEOAS, có thể chỉ định rõ tên relation cho item và collection bằng @Relation:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(UUID id, String status) {}
~~~

Khi OrderView được dùng làm content của EntityModel trong CollectionModel, relation collection được dùng để đặt tên mục embedded, ở đây là orders. Mỗi item thuộc collection có relation item order trong các ngữ cảnh mà relation item được dùng.

Nếu không cấu hình relation tường minh, Spring HATEOAS dùng LinkRelationProvider để suy ra tên relation từ kiểu content. Kết quả có thể không khớp tên client mong đợi nếu cách suy ra hoặc cấu hình pluralization thay đổi. Với API công khai, nên đặt relation rõ ràng và kiểm thử tên thực tế.

## 4. Tạo CollectionModel có embedded items

Một controller Spring MVC có thể trả CollectionModel<EntityModel<OrderView>>. Mỗi item được bọc trong EntityModel để giữ payload và link riêng:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> items = orderService.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
                items,
                linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }
}
~~~

Assembler của từng item:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel()
        );
    }
}
~~~

Ví dụ giả định controller có method one(UUID id) và domain Order có getId() cùng getStatus(). Khi serializer HAL ghi CollectionModel, các item được đặt dưới _embedded.orders; link collection nằm dưới _links.self, còn link của từng item nằm trong object tương ứng.

## 5. Kiểm thử embedded collection bằng MockMvc

Kiểm thử HTTP xác nhận cả controller, assembler và Jackson HAL serializer phối hợp đúng. Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderEmbeddedLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void embedsOrdersWithTheirSelfLinks() throws Exception {
        mockMvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$._embedded.orders.length()").value(2))
            .andExpect(jsonPath("$._embedded.orders[0].id").value("o-101"))
            .andExpect(jsonPath("$._embedded.orders[0].status").value("PENDING"))
            .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
                    .value(endsWith("/orders/o-101")))
            .andExpect(jsonPath("$._embedded.orders[1].id").value("o-102"))
            .andExpect(jsonPath("$._embedded.orders[1]._links.self.href")
                    .value(endsWith("/orders/o-102")))
            .andExpect(jsonPath("$._links.self.href").value(endsWith("/orders")));
    }
}
~~~

Test cần có fixture gồm đúng hai đơn hàng với thứ tự xác định. Nếu dùng database test, tạo dữ liệu trước request; nếu mock service, cấu hình findAll() trả danh sách theo đúng thứ tự. Không dựa vào thứ tự tự nhiên của database khi truy vấn không có ORDER BY.

Các assertion quan trọng là relation orders tồn tại, embedded item là array, số lượng item đúng, payload từng item đúng và self link của từng item trỏ tới tài nguyên tương ứng.

## 6. Kiểm tra embedded relation name chính xác

Nếu API công bố collection relation orders, test nên kiểm tra đúng $._embedded.orders. Nếu relation vô tình trở thành orderList, order, hoặc ordersView, test sẽ thất bại dù response vẫn có dữ liệu.

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").exists())
    .andExpect(jsonPath("$._embedded.orderList").doesNotExist());
~~~

Không nên kiểm tra tên relation bằng cách tìm substring trong toàn bộ response body. JSONPath kiểm tra đúng vị trí và giúp phân biệt _embedded.orders với một thuộc tính orders ở payload thông thường.

Nếu API dùng custom LinkRelationProvider, CURIE hoặc relation URI đầy đủ, hãy viết assertion theo đúng dạng JSON mà serializer tạo ra. Relation là hợp đồng cho client nên cần được kiểm thử như field công khai.

## 7. Kiểm thử nhiều embedded relation trong cùng response

Một resource có thể nhúng nhiều nhóm tài nguyên. Ví dụ dashboard có thể chứa các đơn hàng gần đây và các thông báo:

~~~json
{
  "_embedded": {
    "orders": [
      { "id": "o-101", "status": "PENDING" }
    ],
    "alerts": [
      { "id": "a-5", "message": "Payment required" }
    ]
  },
  "_links": {
    "self": { "href": "/dashboard" }
  }
}
~~~

Test cần kiểm tra từng relation riêng:

~~~java
mockMvc.perform(get("/dashboard").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.alerts").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(1))
    .andExpect(jsonPath("$._embedded.alerts.length()").value(1))
    .andExpect(jsonPath("$._embedded.orders[0].id").value("o-101"))
    .andExpect(jsonPath("$._embedded.alerts[0].id").value("a-5"));
~~~

Đừng chỉ assert _embedded tồn tại. Một relation có thể bị thiếu trong khi các relation khác vẫn được serialize đúng. Với mỗi relation, xác nhận tên, cardinality, item content và link liên quan.

## 8. Kiểm thử embedded association và association link

Giả sử mỗi đơn hàng liên kết với khách hàng. API có thể chỉ công bố link association:

~~~json
{
  "id": "o-101",
  "_links": {
    "self": { "href": "/orders/o-101" },
    "customer": { "href": "/orders/o-101/customer" }
  }
}
~~~

Trong trường hợp này, khách hàng không được nhúng trong _embedded. Test đúng là:

~~~java
mockMvc.perform(get("/orders/o-101").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._embedded.customer").doesNotExist());
~~~

Nếu hợp đồng yêu cầu khách hàng được nhúng, response cần có cấu trúc như:

~~~json
{
  "id": "o-101",
  "_embedded": {
    "customer": {
      "id": "c-7",
      "name": "An Nguyen",
      "_links": {
        "self": { "href": "/customers/c-7" }
      }
    }
  },
  "_links": {
    "self": { "href": "/orders/o-101" },
    "customer": { "href": "/orders/o-101/customer" }
  }
}
~~~

Test phải kiểm tra đường dẫn $._embedded.customer.name, không chỉ $.customer.name. Điều này xác nhận association được serialize như HAL embedded resource chứ không phải một nested property thông thường.

## 9. Kiểm thử embedded association qua projection trong Spring Data REST

Spring Data REST có thể dùng projection để chọn thuộc tính và association xuất hiện trong representation. Ví dụ projection của đơn hàng có thể công bố thông tin khách hàng:

~~~java
@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {
    String getOrderNumber();
    OrderStatus getStatus();
    CustomerSummary getCustomer();
}

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {
    String getName();
}
~~~

Repository có thể khai báo excerpt projection:

~~~java
@RepositoryRestResource(excerptProjection = OrderSummary.class)
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

Khi collection được trả về, projection có thể làm cho dữ liệu association xuất hiện trong embedded item theo cấu hình projection và association của ứng dụng. Hãy kiểm tra response thực tế để xác nhận tên relation và cấu trúc lồng nhau; đừng giả định một getter association luôn tạo ra _embedded trong mọi cấu hình.

Ví dụ assertion khi hợp đồng đã xác định khách hàng được nhúng:

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[0]._embedded.customer.name")
            .value("An Nguyen"));
~~~

Đường dẫn chính xác phụ thuộc relation name và cách exporter serialize projection. Nếu response chỉ có _links.customer, đó là association link, chưa phải nested embedded resource.

## 10. Kiểm thử self link bên trong từng embedded item

Mỗi item trong collection thường cần self link để client có thể mở tài nguyên chi tiết. Kiểm tra link của collection thôi là chưa đủ.

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[1]._links.self.href").exists());
~~~

Nếu mỗi item có relation nghiệp vụ như customer, invoice hoặc items, hãy kiểm tra chúng ở đúng item và đúng URI. Tránh kiểm tra link ở cấp ngoài rồi cho rằng link đó thuộc từng item.

Có thể kiểm tra URI cụ thể bằng endsWith(...) hoặc parse URI rồi xác nhận path. Khi ứng dụng chạy sau reverse proxy, host và prefix có thể khác môi trường test; so sánh path hoặc URI theo cấu hình test sẽ bền vững hơn việc hard-code hostname.

## 11. Kiểm thử thứ tự và cardinality của embedded items

HAL biểu diễn collection embedded dưới dạng array. Thứ tự array cần phản ánh hợp đồng API. Nếu endpoint công bố sort theo createdAt,desc, test nên xác nhận item mới hơn đứng trước item cũ hơn.

~~~java
mockMvc.perform(get("/orders")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders.length()").value(3))
    .andExpect(jsonPath("$._embedded.orders[0].id").value("o-new"))
    .andExpect(jsonPath("$._embedded.orders[1].id").value("o-mid"))
    .andExpect(jsonPath("$._embedded.orders[2].id").value("o-old"));
~~~

Nếu nhiều item có cùng giá trị sort, hãy dùng tiêu chí phụ ổn định trong query hoặc fixture để tránh test phụ thuộc vào thứ tự không được bảo đảm. Cardinality cũng cần được kiểm tra: thiếu item, item trùng hoặc relation có số lượng bất thường đều có thể làm client xử lý sai.

## 12. Kiểm thử collection rỗng

Collection rỗng là trường hợp quan trọng. API vẫn nên trả response đúng media type và self link để client biết resource collection tồn tại. Tuy nhiên, serializer HAL có thể bỏ qua relation embedded không có phần tử hoặc biểu diễn collection rỗng theo cấu hình cụ thể.

Với CollectionModel không phân trang, không nên mặc định mọi cấu hình serializer đều tạo _embedded.orders: []. Hãy xác định hợp đồng response của ứng dụng rồi viết test tương ứng. Nếu hợp đồng chỉ yêu cầu collection rỗng và self link, có thể kiểm tra:

~~~java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Nếu ứng dụng cam kết luôn xuất _embedded.orders với array rỗng, hãy thêm assertion isArray() và isEmpty() sau khi xác nhận serializer được cấu hình để tạo đúng cấu trúc đó. Với PagedModel, có thể kiểm tra thêm page.totalElements == 0 và metadata phân trang theo hợp đồng.

## 13. Kiểm thử embedded resources cùng pagination

Với PagedModel, response có thể chứa _embedded.orders, các link phân trang và object page. Test cần xác nhận page hiện tại chỉ chứa item của trang đó, relation embedded đúng tên và link next/prev xuất hiện phù hợp.

~~~java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(2))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$._links.next.href").exists());
~~~

Khi theo link next, hãy xác nhận item ở trang kế tiếp không bị lặp với trang đầu trong fixture có thứ tự ổn định. Nếu endpoint có filter hoặc sort, kiểm tra các query parameter đó được giữ trong link phân trang.

## 14. Kiểm thử embedded resource có điều kiện

Một số API chỉ nhúng tài nguyên liên quan khi thỏa điều kiện nghiệp vụ hoặc quyền truy cập. Ví dụ dashboard có thể nhúng payment khi đơn hàng đã thanh toán, hoặc chỉ nhúng customerDetails cho người dùng có quyền.

Hãy kiểm thử cả hai nhánh:

- Khi điều kiện đúng, relation embedded xuất hiện và payload chỉ chứa các trường được phép.
- Khi điều kiện sai, relation embedded không xuất hiện hoặc chỉ có link phù hợp theo hợp đồng.
- Người dùng không có quyền không nhận được dữ liệu nhạy cảm qua _embedded.
- Gọi trực tiếp URI của association vẫn được server kiểm tra authorization.

Không dùng việc ẩn embedded relation như biện pháp bảo mật duy nhất. Dữ liệu được nhúng là dữ liệu đã gửi qua mạng; nếu người dùng không được phép xem, server không được serialize nó.

## 15. Kiểm thử relation name khi refactor model

Tên class Java có thể thay đổi trong quá trình refactor, nhưng relation HAL là một phần hợp đồng công khai. Nếu OrderView được đổi tên thành OrderSummaryView, client vẫn cần nhận orders nếu relation đó được cam kết.

Đặt relation tường minh bằng @Relation và kiểm thử:

~~~java
@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderSummaryView(UUID id, String status) {}
~~~

Test cần xác nhận _embedded.orders tồn tại sau khi đổi tên class. Không để client phụ thuộc vào cách framework suy ra relation từ tên class hoặc tên collection Java.

Nếu thay đổi relation là bắt buộc, hãy xem đó là thay đổi hợp đồng: cập nhật tài liệu, hỗ trợ chuyển tiếp nếu cần và kiểm tra các client đang tiêu thụ relation cũ.

## 16. Kiểm thử model trong bộ nhớ và kiểm thử JSON khác nhau thế nào?

Có thể kiểm tra CollectionModel trước khi serialize:

~~~java
CollectionModel<EntityModel<OrderView>> model = assembler.toCollectionModel(orders);

assertThat(model.getContent()).hasSize(2);
assertThat(model.getContent())
        .allSatisfy(item ->
                assertThat(item.getLink(IanaLinkRelations.SELF)).isPresent());
~~~

Unit test này kiểm tra số item và self link ở cấp model. Nó không xác nhận Jackson đã serialize collection thành _embedded.orders, không kiểm tra relation naming trong JSON và cũng không xác nhận content negotiation.

Vì vậy, hãy kết hợp:

| Loại test | Xác nhận |
| --- | --- |
| Unit test assembler/model | Content và link tồn tại trong object model. |
| MockMvc/WebTestClient | _embedded, _links, relation name, JSON payload và media type. |
| Client traversal test | Client có thể đọc embedded item và theo link thực tế. |

Không thay thế integration test bằng assertion trên model trong bộ nhớ nếu mục tiêu là kiểm tra embedded serialization.

## 17. Kiểm thử client đọc embedded resource

Một kiểm thử consumer có thể parse response thành CollectionModel<EntityModel<OrderView>> rồi kiểm tra item và link:

~~~java
CollectionModel<EntityModel<OrderView>> orders =
        restTemplate.exchange(
                URI.create("https://api.example.test/orders"),
                HttpMethod.GET,
                new HttpEntity<>(headers),
                new ParameterizedTypeReference<>() {}
        ).getBody();

assertThat(orders).isNotNull();
assertThat(orders.getContent()).hasSize(2);

EntityModel<OrderView> first = orders.getContent().iterator().next();
assertThat(first.getContent().id()).isEqualTo(expectedId);
assertThat(first.getRequiredLink(IanaLinkRelations.SELF)).isNotNull();
~~~

Test này xác nhận converter HAL ở phía client có thể ánh xạ _embedded vào CollectionModel. Nếu client dùng raw CollectionModel.class, generic item type có thể không được giữ. Hãy dùng ParameterizedTypeReference khi cần kiểu content cụ thể.

Trong test này, RestTemplate cần được cấu hình message converter hỗ trợ HAL và header Accept cần chứa application/hal+json. Dùng URI tuyệt đối hoặc cấu hình root URI cho RestTemplate; không truyền relative path vào RestTemplate mặc định chưa có root URI.

## 18. Các lỗi thường gặp khi kiểm thử embedded

**Chỉ kiểm tra _links.** Link không chứng minh tài nguyên đã được nhúng. Kiểm tra đúng đường dẫn _embedded.

**Nhầm association link với embedded association.** _links.customer và _embedded.customer có semantics khác nhau.

**Kiểm tra nhầm thuộc tính JSON thông thường.** $.customer không tương đương $._embedded.customer; hãy dùng JSONPath chính xác.

**Không cố định collection relation.** Dùng @Relation hoặc relation provider được cấu hình rõ và kiểm thử tên relation.

**Chỉ kiểm tra collection relation, bỏ qua item self link.** Mỗi embedded item có thể cần self link riêng.

**Giả định thứ tự array luôn ổn định.** Nếu hợp đồng yêu cầu thứ tự, query phải có sort rõ ràng và test fixture phải xác định.

**Giả định collection rỗng luôn serialize thành array rỗng.** Xác nhận hành vi serializer và chỉ assert cấu trúc mà API cam kết.

**Chỉ unit test assembler.** Unit test không kiểm tra Jackson HAL serializer; cần MockMvc hoặc WebTestClient.

**Nhúng dữ liệu nhạy cảm.** Kiểm tra authorization và trường dữ liệu trong từng embedded representation.

**Không kiểm tra pagination links.** Embedded item và link next/prev phải cùng phản ánh page hiện tại và ngữ cảnh filter/sort.

## 19. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng bộ kiểm thử embedded cho API đơn hàng:

1. Tạo OrderView và đặt @Relation(itemRelation = "order", collectionRelation = "orders").
2. Dùng CollectionModel<EntityModel<OrderView>> để trả collection.
3. Thêm self link cho collection và từng item.
4. Viết MockMvc test kiểm tra application/hal+json và _embedded.orders.
5. Xác nhận số lượng item, payload và self link của từng item.
6. Thêm link association customer và kiểm tra nó nằm trong _links.
7. Nếu nghiệp vụ yêu cầu embedded customer, cấu hình representation/projection và kiểm tra _embedded.customer riêng biệt.
8. Kiểm tra nhiều embedded relation và relation name không bị đổi khi refactor DTO.
9. Kiểm tra collection rỗng, page đầu, page cuối và pagination metadata.
10. Viết unit test cho assembler, integration test cho HAL JSON và consumer test cho CollectionModel.
11. Kiểm tra embedded data có điều kiện và không làm lộ trường người dùng không được phép xem.

Bạn đã nắm được cách kiểm thử embedded khi có thể xác nhận chính xác dữ liệu nào nằm trong _embedded, phân biệt nó với _links và nested JSON property, kiểm tra relation name, số lượng và thứ tự item, self link bên trong item, association lồng nhau, collection rỗng và pagination. Những kiểm thử này bảo đảm client nhận đúng representation hypermedia mà API cam kết.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS Reference Documentation – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS API – Relation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
