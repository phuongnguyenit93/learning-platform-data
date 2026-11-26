# Embedded không kiểm soát

Spring HATEOAS cho phép một representation chứa cả link điều hướng và resource nhúng. Trong HAL, link nằm trong _links còn nội dung nhúng nằm trong _embedded. Embedded giúp client lấy được dữ liệu liên quan trong cùng response, giảm số request tiếp theo và tạo trải nghiệm liền mạch.

Vấn đề xuất hiện khi API nhúng mọi quan hệ mà domain model có, không giới hạn số lượng, độ sâu hoặc kích thước dữ liệu. Một response đơn hàng có thể kéo theo khách hàng, địa chỉ, từng dòng hàng, sản phẩm, nhà cung cấp, tồn kho, lịch sử và các đơn hàng liên quan. Kết quả là payload lớn, query tăng theo số item, dữ liệu bị lặp, quyền truy cập khó kiểm soát và client phụ thuộc chặt vào cấu trúc nội bộ.

Đây là anti-pattern **embedded không kiểm soát**: server biến một resource thành bản sao của cả object graph thay vì thiết kế representation phục vụ đúng nhu cầu điều hướng của client.

## Embedded và link giải quyết hai nhu cầu khác nhau

Link cho biết client có thể đi tới resource liên quan ở đâu và quan hệ của nó với resource hiện tại là gì. Embedded cung cấp một phần nội dung của resource liên quan ngay trong response hiện tại.

Ví dụ response HAL cho đơn hàng:

~~~json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "customer": {
      "href": "/customers/customer-7"
    },
    "items": {
      "href": "/orders/order-42/items"
    }
  },
  "_embedded": {
    "customer": {
      "name": "Nguyễn An",
      "tier": "GOLD"
    }
  }
}
~~~

Trong ví dụ, client nhận ngay tên khách hàng để hiển thị cạnh đơn hàng, nhưng vẫn có link tới resource khách hàng đầy đủ và collection các dòng hàng. Embedded customer là một preview; link customer là entry point tới resource độc lập.

Hai cách này không loại trừ nhau. Một relation có thể có link để điều hướng và có embedded preview để client sử dụng ngay. Tuy nhiên, preview phải có phạm vi rõ ràng, không khiến client hiểu nhầm rằng đó là toàn bộ resource đích.

## Vì sao nhúng mọi thứ gây hại?

Giả sử một trang có 30 đơn hàng. Mỗi đơn có 5 dòng hàng; mỗi dòng nhúng sản phẩm; mỗi sản phẩm lại nhúng nhà cung cấp và danh sách kho. Chỉ một request collection có thể tạo ra hàng trăm hoặc hàng nghìn object và link.

Các chi phí thường tăng cùng nhau:

| Chi phí | Hậu quả của embedded không giới hạn |
| --- | --- |
| Database | Lazy loading và N+1 query khi assembler duyệt từng quan hệ |
| CPU | Chuyển đổi nhiều object, tạo nhiều link và serialize JSON |
| Bộ nhớ | Giữ object graph lớn trong heap cho một response |
| Network | Payload tăng, thời gian truyền và parse ở client tăng |
| Cache | Một thay đổi nhỏ ở resource con làm response cha cần cập nhật hoặc revalidate |
| Bảo mật | Dễ đưa nhầm trường nhạy cảm hoặc dữ liệu ngoài phạm vi quyền của caller |
| Hợp đồng API | Client phụ thuộc vào nhiều cấu trúc lồng nhau và khó nâng cấp độc lập |

Độ lớn của response không chỉ phụ thuộc số item ở collection gốc. Nếu mỗi item nhúng một collection con, số object có thể tăng theo tích của các cardinality ở từng tầng. Ví dụ 30 đơn × 5 dòng hàng × 2 thông tin liên quan đã có thể tạo ra hàng trăm node trước khi tính các link và metadata.

## Các biểu hiện của anti-pattern

### Nhúng toàn bộ object graph

Assembler lấy JPA entity rồi trả trực tiếp các quan hệ. Jackson hoặc HAL serializer tiếp tục đi qua các getter và vô tình tải thêm dữ liệu.

~~~java
// Anti-pattern minh họa: trả entity với quan hệ rộng.
@GetMapping("/orders/{id}")
Order get(@PathVariable UUID id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Entity có thể có quan hệ hai chiều như Order → Customer → Orders → Customer. Nếu không có kiểm soát, response có thể lặp sâu, gây recursion, lỗi serialize hoặc buộc phải thêm annotation JSON chỉ để né vòng tham chiếu.

API nên định nghĩa representation riêng và chọn rõ trường nào được xuất hiện. Không dùng entity persistence làm hợp đồng HTTP.

### Nhúng collection không giới hạn

Một đơn hàng có thể có hàng nghìn dòng hàng hoặc một khách hàng có hàng chục nghìn giao dịch. Nhúng toàn bộ collection vào item response khiến request GET tưởng như nhỏ nhưng thực tế trở thành bulk download.

Nếu collection có thể tăng theo thời gian, hãy coi nó là một resource có URI và pagination riêng. Parent representation chỉ cần link tới collection đó, hoặc một preview có giới hạn nếu có lý do sản phẩm rõ ràng.

### Nhúng cùng một resource lặp lại trong collection

Một trang có 50 đơn hàng nhưng chỉ có 4 khách hàng. Nếu mỗi đơn hàng nhúng lại toàn bộ customer object, response lặp cùng dữ liệu nhiều lần. Khi thông tin customer thay đổi, nhiều bản sao trong response có thể không đồng nhất nếu được lấy ở các thời điểm khác nhau.

Có thể nhúng preview nhỏ, ổn định như tên hiển thị và tier. Với profile lớn hoặc dữ liệu thay đổi độc lập, dùng link customer để client tải resource khi cần.

### Nhúng dữ liệu ít liên quan tới tác vụ

Client đang hiển thị danh sách đơn hàng có thể chỉ cần mã đơn, trạng thái, tổng tiền và tên khách hàng. Nhúng audit history, địa chỉ đầy đủ, payment details và thông tin kho làm tăng payload mà màn hình không sử dụng.

Representation nên phản ánh nhu cầu của resource và tác vụ phổ biến. Nếu client cần chi tiết chuyên sâu, cung cấp resource con có link riêng.

### Nhúng dữ liệu nhạy cảm vì đã có quyền đọc parent

Quyền đọc đơn hàng không tự động có nghĩa là caller được đọc mọi trường của khách hàng, thông tin thanh toán hoặc ghi chú nội bộ. Nếu assembler nhúng toàn bộ đối tượng liên quan, API có thể vô tình vượt qua ranh giới authorization.

Mỗi embedded resource và từng trường nhạy cảm cần tuân theo policy truy cập tương ứng. Việc bỏ link hoặc không nhúng dữ liệu chỉ hỗ trợ discoverability; endpoint resource đích vẫn phải kiểm tra quyền khi được gọi trực tiếp.

## Quy tắc quyết định nên embed hay link

Chỉ nhúng một resource khi phần nội dung đó nhỏ, có giới hạn, liên quan trực tiếp tới tác vụ hiện tại và caller được phép xem. Nếu một trong các điều kiện không đúng, hãy ưu tiên link.

| Tiêu chí | Embed phù hợp khi | Link phù hợp khi |
| --- | --- | --- |
| Kích thước | Preview nhỏ, số trường ít | Resource lớn hoặc có nhiều quan hệ |
| Cardinality | Một resource hoặc collection nhỏ, có giới hạn cứng | Collection có thể tăng không giới hạn |
| Mức sử dụng | Hầu hết client cần ngay | Chỉ một số client hoặc một số màn hình cần |
| Vòng đời | Dữ liệu ít thay đổi và gắn chặt với tác vụ | Resource thay đổi độc lập hoặc có cache riêng |
| Quyền | Cùng phạm vi truy cập đã được xác nhận | Có policy riêng hoặc cần kiểm tra quyền độc lập |
| Pagination | Không cần phân trang riêng | Có sort, filter hoặc pagination riêng |
| Tiến hóa | Hợp đồng preview nhỏ và ổn định | Resource có thể phát triển độc lập |

Không có quy tắc rằng mọi quan hệ to-one đều phải embed hoặc mọi quan hệ to-many đều phải link. Cardinality là tín hiệu quan trọng, nhưng quyết định cuối cùng dựa trên nhu cầu client, kích thước, quyền và vòng đời dữ liệu.

## Thiết kế preview có giới hạn

Một preview nên:

- Chỉ chứa trường client thường dùng trong ngữ cảnh hiện tại.
- Có kích thước và số lượng tối đa xác định.
- Không chứa dữ liệu bí mật hoặc trường chỉ dành cho resource đích.
- Có relation rõ nghĩa.
- Có link tới resource đầy đủ khi client cần thêm thông tin.
- Không lồng tiếp các collection lớn hoặc object graph không giới hạn.

Ví dụ đơn hàng có thể embed customer preview gồm displayName và tier, đồng thời giữ link customer. Dòng hàng có thể chỉ embed sku, productName và quantity; thông tin tồn kho, mô tả dài và lịch sử giá nằm ở resource khác.

Nếu cần hiển thị ba dòng hàng gần nhất, đặt relation riêng như recentItems và công bố link items tới collection đầy đủ. Không dùng cùng một relation để biểu diễn một phần collection rồi khiến client hiểu đó là toàn bộ danh sách.

## Dùng HalModelBuilder để embed có chủ đích

Spring HATEOAS cung cấp HalModelBuilder để xây HAL representation có embedded document và preview gắn với link. Ví dụ sau chỉ nhúng customer summary, còn link customer dẫn tới resource đầy đủ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record CustomerPreview(String displayName, String tier) {}

record OrderSummary(UUID id, String status, BigDecimal total) {}

@RestController
class OrderController {

    private final OrderQueryService orderQueryService;
    private final TenantResolver tenantResolver;

    OrderController(
            OrderQueryService orderQueryService,
            TenantResolver tenantResolver) {
        this.orderQueryService = orderQueryService;
        this.tenantResolver = tenantResolver;
    }

    @GetMapping(
        value = "/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    RepresentationModel<?> one(
            @PathVariable UUID id,
            Authentication authentication) {
        UUID tenantId = tenantResolver.tenantId(authentication);
        OrderView view = orderQueryService.findView(tenantId, id);

        Link self = linkTo(
            methodOn(OrderController.class).one(id, null)
        ).withSelfRel();

        Link customer = linkTo(
            methodOn(CustomerController.class).one(view.customerId())
        ).withRel("customer");

        return HalModelBuilder.halModelOf(
                new OrderSummary(id, view.status(), view.total()))
            .preview(new CustomerPreview(
                view.customerName(),
                view.customerTier()))
            .forLink(customer)
            .link(self)
            .build();
    }
}
~~~

preview(...).forLink(customer) đưa preview vào _embedded theo relation của link và đồng thời giữ link customer trong _links. Client có thể hiển thị tên khách hàng ngay, sau đó theo link để lấy profile chi tiết.

OrderView là DTO được query service chuẩn bị trước; nó chỉ chứa dữ liệu cần cho response này. Ví dụ giả định OrderQueryService lấy order và customer preview bằng một query projection hoặc một fetch plan có giới hạn. Không gọi repository riêng cho từng trường từ assembler.

## Embed collection nhỏ và giữ link tới collection đầy đủ

Khi sản phẩm cần hiển thị vài item gần đây ngay trên trang đơn hàng, có thể nhúng một preview collection với giới hạn rõ ràng. Link items vẫn dẫn tới collection có pagination:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

record OrderItemPreview(String sku, String name, int quantity) {}

RepresentationModel<?> toOrderModel(
        OrderView order,
        List<OrderItemPreview> recentItems,
        Link self,
        Link itemsLink) {

    if (recentItems.size() > 3) {
        throw new IllegalArgumentException(
            "Preview chỉ được chứa tối đa 3 item");
    }

    return HalModelBuilder.halModelOf(order.summary())
        .embed(
            recentItems,
            LinkRelation.of(
                "https://api.example.com/rels/recent-order-items"))
        .link(self)
        .link(itemsLink)
        .build();
}
~~~

Giới hạn ba item là quy tắc ví dụ của hợp đồng API; chọn con số theo yêu cầu giao diện và dữ liệu đo được. Query lấy preview cũng phải áp dụng LIMIT tương ứng ở database, không tải toàn bộ collection rồi cắt bằng Java.

Relation recent-order-items nói rõ đây là preview. Link items dẫn tới resource collection đầy đủ, nơi client có thể dùng sort, filter và pagination. Nếu preview rỗng nhưng API muốn công bố collection rỗng, HalModelBuilder.embed(collection, LinkRelation) cho phép chỉ định relation tường minh.

## Không để quan hệ hai chiều tạo embedded cycle

Domain model có thể có quan hệ hai chiều:

~~~text
Customer
  └── orders[]
        └── customer
              └── orders[]
                    └── ...
~~~

Không chuyển cấu trúc này trực tiếp thành embedded representation. Chọn một chiều để nhúng preview và dùng link ở chiều ngược lại. Ví dụ:

- Order có thể embed customer preview.
- Customer chỉ có link orders tới collection đơn hàng.
- Order không embed lại customer đầy đủ trong mỗi item của collection đó.

Độ sâu embedded nên được giới hạn theo hợp đồng, thường chỉ một hoặc hai tầng có chủ đích. Nếu client cần đi sâu hơn, nó có thể theo link của resource con.

## Không để JPA lazy loading quyết định response

Truyền entity có quan hệ lazy vào assembler và để serializer tự truy cập getter là cách dễ tạo N+1:

~~~java
// Anti-pattern: mỗi lần đọc customer có thể phát sinh một query.
List<EntityModel<Order>> models = orders.stream()
    .map(order -> EntityModel.of(order)
        .add(customerLink(order)))
    .toList();
~~~

Nếu representation cần customer name, hãy tải trường đó bằng projection hoặc query phù hợp trước khi assembly. Nếu cần preview collection, query theo page ID và giới hạn số bản ghi. Tránh dùng EAGER toàn cục để sửa một response cụ thể; điều đó có thể làm các use case khác tải quá nhiều dữ liệu.

Ví dụ interface projection:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

interface OrderPreviewRow {
    UUID getId();
    String getStatus();
    BigDecimal getTotal();
    UUID getCustomerId();
    String getCustomerName();
    String getCustomerTier();
}
~~~

Repository có thể join customer để lấy đúng các trường preview:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface OrderRepository extends JpaRepository<Order, UUID> {

@Query("""
    select o.id as id,
           o.status as status,
           o.total as total,
           c.id as customerId,
           c.displayName as customerName,
           c.tier as customerTier
    from Order o
    join o.customer c
    where o.id = :orderId
      and o.tenantId = :tenantId
    """)
Optional<OrderPreviewRow> findPreview(
    @Param("tenantId") UUID tenantId,
    @Param("orderId") UUID orderId
);
}
~~~

Query áp dụng điều kiện tenant ngay tại database. Service có thể chuyển projection thành DTO bất biến rồi truyền cho assembler. Cách này giúp số query có thể dự đoán và tránh serializer truy cập persistence layer.

## Collection embedded phải có giới hạn

Trước khi embed collection, xác định:

1. Số item tối đa được nhúng.
2. Các trường nào được phép xuất hiện.
3. Có cần sort ổn định để preview có ý nghĩa không.
4. Query nào lấy preview mà không tải phần còn lại.
5. Relation nào mô tả preview và link nào trỏ tới collection đầy đủ.
6. Cách xử lý khi collection rỗng hoặc vượt giới hạn.

Nếu collection có thể lớn, có bộ lọc hoặc sort, hay cần metadata phân trang, hãy biểu diễn nó thành resource riêng. Parent chỉ cần link tới collection. Đừng giả định một mảng trong _embedded tự mang semantics phân trang của resource con.

## Cho phép client yêu cầu embed có kiểm soát

Một số API hỗ trợ client chọn preview qua query parameter, ví dụ:

~~~http
GET /orders/42?include=customer
Accept: application/hal+json
~~~

Đây có thể là một phần hợp đồng hợp lệ nếu được thiết kế rõ. Tuy nhiên, không cho client yêu cầu bất kỳ đường dẫn object graph nào như include=customer.orders.items.product.supplier. Cách đó biến cấu trúc domain nội bộ thành API công khai, tạo nguy cơ query amplification và khó kiểm soát quyền.

Nếu hỗ trợ include, hãy:

- Dùng allow-list relation như customer, recentItems.
- Đặt giới hạn số relation có thể yêu cầu trong một request.
- Đặt giới hạn depth và số item cho mỗi preview.
- Kiểm tra authorization riêng cho từng loại dữ liệu được nhúng.
- Giữ link tới resource đầy đủ.
- Đưa biến thể include vào cache key; URI query khác nhau là các request representation khác nhau.
- Từ chối hoặc bỏ qua relation không được hỗ trợ theo một quy ước nhất quán và có tài liệu.

Ví dụ parse allow-list:

~~~java
import java.util.Set;

private static final Set<String> ALLOWED_INCLUDES =
    Set.of("customer", "recentItems");

Set<String> validateIncludes(Set<String> requested) {
    if (!ALLOWED_INCLUDES.containsAll(requested)) {
        throw new InvalidIncludeException();
    }

    return requested;
}
~~~

Không dùng tên field Java hoặc tên association JPA làm giá trị include công khai. Relation trong API là một phần hợp đồng hypermedia và cần được đặt tên theo ngữ nghĩa mà client hiểu.

## Embedded và quyền truy cập

Nếu caller được phép đọc order nhưng không được phép đọc customer profile, không nhúng customer preview chứa thông tin riêng. Có thể:

- Chỉ nhúng trường công khai như tên hiển thị đã được phép chia sẻ.
- Bỏ preview và chỉ công bố link nếu caller có quyền truy cập resource đích.
- Không công bố link nếu caller không được phép khám phá resource đó, theo chính sách API.

Không dựa vào việc client không nhìn thấy link để bảo vệ endpoint. Khi client tự tạo URI hoặc giữ link cũ, controller/service của resource đích vẫn phải xác minh quyền.

Đối với collection, quyền truy cập phải được áp dụng trước khi query và pagination. Không tải tất cả dữ liệu rồi loại bỏ embedded item không được phép ở tầng serializer; cách đó có thể làm lộ số lượng, metadata hoặc dữ liệu qua log.

## Embedded ảnh hưởng cache và tính nhất quán

Khi order response nhúng customer preview, response order phụ thuộc cả dữ liệu order lẫn một phần dữ liệu customer. Nếu customer đổi tên, cache representation order cũng có thể trở nên stale dù order không đổi.

Điều này tạo ra các câu hỏi:

- Cache validator của order có thay đổi khi preview customer thay đổi không?
- Update customer có cần invalidate collection order chứa preview không?
- TTL của response có phù hợp với tần suất thay đổi của cả hai resource không?
- Dữ liệu embedded có được lấy trong cùng snapshot nhất quán hay ở các thời điểm khác nhau?

Nếu quan hệ thay đổi độc lập và yêu cầu freshness riêng, link tới resource con giúp cache và lifecycle tách biệt hơn. Nếu vẫn embed, ETag phải phản ánh toàn bộ representation, kể cả embedded data và link. Không dùng version của riêng entity cha làm validator nếu nó không đổi khi preview con thay đổi.

## Embedded và khả năng tiến hóa API

Khi client phụ thuộc vào trường lồng sâu, thay đổi schema của resource con có thể ảnh hưởng mọi endpoint đang nhúng nó. Ví dụ CustomerProfile được dùng trong order, invoice, shipment và support case. Một lần mở rộng profile có thể làm payload của cả bốn response tăng theo.

Tách preview thành DTO nhỏ giúp giữ hợp đồng của parent ổn định:

~~~java
record CustomerPreview(
    String displayName,
    String tier
) {}
~~~

DTO preview chỉ chứa trường được công bố cho ngữ cảnh đó. Resource /customers/{id} có thể tiếp tục phát triển độc lập mà không buộc mọi parent response phải thay đổi.

Nếu nhiều parent cần các trường khác nhau, đừng dùng một Customer khổng lồ cho tất cả. Tạo projection hoặc preview theo use case và relation có ngữ nghĩa rõ ràng.

## Kiểm thử embedded có giới hạn

MockMvc có thể xác nhận preview được nhúng và link tới resource đầy đủ vẫn tồn tại:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.customer.displayName").exists())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._links.items.href").exists());
~~~

Tên JSONPath cụ thể phụ thuộc relation đã cấu hình. Ví dụ giả định preview customer được serialize dưới _embedded.customer.

Kiểm tra collection preview không vượt giới hạn:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._embedded['https://api.example.com/rels/recent-order-items'].length()")
        .value(org.hamcrest.Matchers.lessThanOrEqualTo(3)));
~~~

Nếu relation URI được rút gọn bằng CURIE, JSONPath phải dùng tên relation đã serialize. Test cũng cần xác nhận link items trỏ tới collection đầy đủ, không phải URI preview.

## Kiểm thử query count và payload

Không chỉ kiểm tra JSON. Hãy đo số query khi trả collection có embedded preview. Tăng page size từ 10 lên 30 không nên tạo thêm một query cho mỗi item.

Với Hibernate Statistics, có thể reset bộ đếm sau khi chuẩn bị fixture rồi thực hiện request hoặc gọi read service. Xác nhận query count nằm trong ngưỡng dự kiến, đồng thời kiểm tra response không chứa quan hệ ngoài allow-list.

Theo dõi kích thước response:

~~~java
MvcResult result = mockMvc.perform(get("/orders")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

int responseBytes = result.getResponse().getContentAsByteArray().length;
assertThat(responseBytes).isLessThan(MAX_ORDER_PAGE_BYTES);
~~~

MAX_ORDER_PAGE_BYTES phải được chọn từ yêu cầu thực tế và baseline đo được. Không đặt một ngưỡng tùy ý rồi loại bỏ dữ liệu cần thiết chỉ để test qua.

Các test bổ sung nên xác nhận:

- Embedded preview không chứa trường nhạy cảm.
- Relation preview và link resource đầy đủ có tên rõ ràng.
- Collection preview tuân thủ giới hạn ngay ở query.
- Response không có embedded cycle hoặc object graph ngoài dự kiến.
- include chỉ chấp nhận allow-list.
- Quyền truy cập embedded resource được kiểm tra đúng.
- ETag thay đổi khi embedded data thay đổi nếu API dùng conditional caching.

## Khi nào nên giữ embedded?

Embedded là lựa chọn tốt khi client gần như luôn cần một phần dữ liệu nhỏ ngay cùng parent, số lượng có giới hạn và quyền truy cập tương thích. Ví dụ:

- Tên hiển thị của người tạo trong task card.
- Ảnh đại diện thumbnail trong danh sách người dùng.
- Một vài dòng hàng đầu tiên trong order preview.
- Tóm tắt địa chỉ giao hàng cần thiết để xác nhận đơn.

Ngay cả các trường hợp này, hãy giữ representation preview nhỏ và có link tới resource độc lập nếu client cần chi tiết hơn.

## Những lỗi thường gặp

- **Embed mọi quan hệ domain:** response phơi bày cấu trúc persistence thay vì hợp đồng API.
- **Embed collection không giới hạn:** payload tăng theo dữ liệu và thời gian.
- **Dùng JPA entity làm representation:** lazy loading và vòng tham chiếu khó kiểm soát.
- **Lặp lại resource lớn trong từng item:** tăng payload và tạo dữ liệu trùng lặp.
- **Embed cả dữ liệu ít dùng:** client phải tải và parse nội dung không cần thiết.
- **Không kiểm tra quyền embedded:** có thể làm lộ dữ liệu của resource liên quan.
- **Không có link tới resource đầy đủ:** client bị phụ thuộc vào preview thiếu trường.
- **Dùng cùng relation cho preview và collection hoàn chỉnh:** client không biết embedded có đầy đủ hay không.
- **Cho phép include tùy ý:** query graph và chi phí request không còn giới hạn.
- **Dùng eager fetch toàn cục:** sửa một endpoint nhưng làm các use case khác tải dư dữ liệu.
- **Bỏ qua cache dependency:** thay đổi resource con làm preview cũ tồn tại quá lâu.
- **Chỉ test status 200:** không phát hiện payload phình to, N+1 hoặc embedded data bị lộ.

## Checklist kiểm soát embedded

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Client có thực sự cần dữ liệu này ngay không? | Chỉ embed phần phục vụ tác vụ hiện tại |
| Kích thước và cardinality có giới hạn không? | Đặt max item, max depth và trường được phép |
| Resource con có vòng đời riêng không? | Giữ link tới resource độc lập |
| Có pagination/filter/sort riêng không? | Expose collection link thay vì nhúng toàn bộ |
| Dữ liệu có cùng phạm vi quyền không? | Kiểm tra authorization cho preview và endpoint đích |
| Query có phát sinh N+1 không? | Dùng projection, join hoặc batch query |
| Relation có mô tả đúng preview không? | Đặt relation rõ nghĩa và link đầy đủ |
| Cache có phản ánh thay đổi embedded data không? | Validator và invalidation bao phủ toàn representation |
| Có cho phép client chọn embed không? | Dùng allow-list, depth và size limits |
| Đã đo payload và query count chưa? | Có regression test và baseline thực tế |

Embedded không kiểm soát biến một REST API thành object graph lớn, khó cache, khó bảo mật và khó tiến hóa. Trong Spring HATEOAS, hãy dùng HalModelBuilder để nhúng preview có chủ đích, giữ link tới resource đầy đủ và giới hạn collection theo cardinality rõ ràng. Tải dữ liệu bằng DTO projection hoặc batch query trước khi assembly; áp dụng authorization cho từng phần dữ liệu; đo query count, payload và cache behavior. Hypermedia có giá trị khi client được cung cấp đủ thông tin để điều hướng, còn mỗi representation vẫn giữ kích thước và trách nhiệm có thể kiểm soát.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation, HAL representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS – HalModelBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html)
- [Spring HATEOAS – Relation annotation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring Data JPA – Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
