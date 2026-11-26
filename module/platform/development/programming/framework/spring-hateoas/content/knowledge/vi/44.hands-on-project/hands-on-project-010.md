# Viết test hypermedia cho Spring HATEOAS

Một API có thể trả HTTP 200 và JSON hợp lệ nhưng vẫn phá vỡ hợp đồng hypermedia: thiếu link `self`, relation đổi tên ngoài ý muốn, action vẫn xuất hiện sau khi đơn hàng đã bị hủy, hoặc link `next` dẫn tới trang không tồn tại. Test chỉ kiểm tra status code và vài field dữ liệu sẽ không phát hiện được những lỗi này.

Dự án này yêu cầu xây dựng bộ kiểm thử cho một Orders API dùng Spring HATEOAS và HAL. Bạn sẽ kiểm tra relation, href, điều kiện xuất hiện action, collection và pagination links, content negotiation, lỗi Problem Details, đồng thời theo link do server trả về để đi tiếp trong workflow.

Mục tiêu là tạo một bộ test mô tả được cách client khám phá và sử dụng API. Khi route nội bộ thay đổi nhưng relation và hành vi điều hướng vẫn đúng, test vẫn phải tiếp tục thành công.

## 1. Mục tiêu dự án

Xây dựng test suite cho API quản lý đơn hàng với các khả năng sau:

- Client bắt đầu từ API root và khám phá collection đơn hàng.
- Client mở một đơn hàng thông qua link được cung cấp.
- Representation của đơn hàng có `self`, link về collection và các quan hệ phù hợp.
- Link action chỉ xuất hiện khi trạng thái và quyền cho phép.
- Client theo link action để thực hiện thao tác hủy đơn.
- Collection có pagination links đúng với trang hiện tại.
- API trả representation HAL khi client yêu cầu media type tương ứng.
- Lỗi nghiệp vụ trả Problem Details có type URI ổn định.
- Test lấy href từ response và theo link đó thay vì tự ghép route.

Sau khi hoàn thành, một thay đổi URL như `/orders/{id}` thành `/api/orders/{id}` không nên buộc bạn sửa mọi test chỉ vì chuỗi URL đã đổi. Test cần tập trung vào relation và hành vi của link.

## 2. Bối cảnh nghiệp vụ

API quản lý đơn hàng có các trạng thái:

| Trạng thái | Ý nghĩa | Action có thể xuất hiện |
|---|---|---|
| `NEW` | Đơn vừa được tạo | `cancel` |
| `AWAITING_PAYMENT` | Chờ thanh toán | `pay`, có thể `cancel` |
| `PAID` | Đã thanh toán | `ship` |
| `SHIPPED` | Đang giao | `track`, `confirm-delivery` |
| `DELIVERED` | Đã giao | `request-return`, `invoice` |
| `CANCELLED` | Đã hủy | Không còn action hủy |

Đây là workflow mẫu để làm bài. Quy tắc thực tế phải được xác định từ domain policy của ứng dụng.

Các endpoint được dùng trong dự án:

| Endpoint | Mục đích |
|---|---|
| `GET /api` | Entry point của API |
| `GET /api/orders` | Danh sách đơn hàng có phân trang |
| `GET /api/orders/{id}` | Representation của một đơn hàng |
| `POST /api/orders/{id}/cancel` | Hủy đơn nếu điều kiện cho phép |
| `GET /api/orders/{id}/invoice` | Xem hóa đơn khi khả dụng |

Test không được coi những route trên là kiến thức client phải tự biết. Chúng là mapping phía server để tạo link. Client bắt đầu từ `/api`, đọc relation, sau đó sử dụng href được trả về.

## 3. Hợp đồng hypermedia cần kiểm thử

### 3.1. API root

API root công bố link tới collection:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/api"
    },
    "https://api.example.test/rels/orders": {
      "href": "https://api.example.test/api/orders"
    }
  }
}
~~~

`https://api.example.test/rels/orders` là extension relation mà client sử dụng để khám phá collection. Ứng dụng cần công bố ý nghĩa của relation này trong tài liệu API hoặc tại URI relation.

API root phải dùng cùng relation constant với assembler để tránh hai entry point công bố hai tên khác nhau:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiRootController {

    @GetMapping("/api")
    RepresentationModel<?> root() {
        RepresentationModel<?> model = new RepresentationModel<>();
        model.add(linkTo(
            methodOn(ApiRootController.class).root()
        ).withSelfRel());
        model.add(linkTo(OrderController.class)
            .withRel(OrderModelAssembler.ORDERS_REL));
        return model;
    }
}
~~~

### 3.2. Order representation

Đơn hàng ở trạng thái `NEW` và actor có quyền hủy có thể trả:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "state": "NEW",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders/42"
    },
    "https://api.example.test/rels/orders": {
      "href": "https://api.example.test/api/orders"
    },
    "https://api.example.test/rels/order-cancellation": {
      "href": "https://api.example.test/api/orders/42/cancel"
    }
  }
}
~~~

Đơn hàng ở trạng thái `DELIVERED` không được công bố link hủy:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "state": "DELIVERED",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders/42"
    },
    "https://api.example.test/rels/orders": {
      "href": "https://api.example.test/api/orders"
    },
    "invoice": {
      "href": "https://api.example.test/api/orders/42/invoice"
    }
  }
}
~~~

Test cần xác nhận link `order-cancellation` vắng mặt ở trạng thái không cho phép. Chỉ kiểm tra link xuất hiện ở trạng thái `NEW` là chưa đủ; cần test cả trường hợp phủ định.

### 3.3. Collection representation

Collection có link điều hướng và embedded items:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "number": "ORD-0042",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.test/api/orders?page=1&size=20"
    },
    "last": {
      "href": "https://api.example.test/api/orders?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 87,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Test phải kiểm tra relation `next` xuất hiện khi còn trang tiếp theo, không xuất hiện ở trang cuối và href giữ lại các bộ lọc có ảnh hưởng tới kết quả.

### 3.4. Action thành công và lỗi nghiệp vụ

Khi hủy đơn thành công, response phản ánh trạng thái mới. Link hủy không còn xuất hiện:

~~~json
{
  "id": 42,
  "number": "ORD-0042",
  "state": "CANCELLED",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders/42"
    },
    "https://api.example.test/rels/orders": {
      "href": "https://api.example.test/api/orders"
    }
  }
}
~~~

Nếu client cố hủy đơn đã giao, API trả Problem Details:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be cancelled in its current state."
}
~~~

Test kiểm tra `type` vì đây là định danh problem type ổn định. Không kiểm tra toàn bộ câu `detail` nếu nội dung đó có thể được dịch hoặc cải thiện mà không thay đổi semantics.

## 4. Chuẩn bị test dependencies

Dự án cần Spring Boot test support, Spring MVC Test và Spring Security Test nếu action phụ thuộc quyền.

Với Gradle:

~~~groovy
dependencies {
    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.security:spring-security-test"
}
~~~

Nếu ứng dụng dùng Spring Boot 3.4 trở lên, có thể dùng `@MockitoBean` để thay bean bằng mock trong test context. Với phiên bản cũ hơn, dùng `@MockBean` tương ứng.

Không cần database thật cho các contract test ở web slice nếu query service đã được mock. Có thể bổ sung integration test với database test riêng khi cần xác nhận query, transaction hoặc mapping persistence.

## 5. Chuẩn bị representation và assembler

Test phải kiểm tra một contract có ý nghĩa. Trước hết, tạo model và assembler có relation ổn định.

Ví dụ view model:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(
    Long id,
    String number,
    OrderState state,
    boolean invoiceAvailable
) {}
~~~

Assembler tạo self link, collection link và action link theo policy:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderView>> {

    static final LinkRelation ORDERS_REL =
        LinkRelation.of("https://api.example.test/rels/orders");

    static final LinkRelation CANCEL_REL =
        LinkRelation.of(
            "https://api.example.test/rels/order-cancellation"
        );

    private final OrderActionPolicy actionPolicy;

    OrderModelAssembler(OrderActionPolicy actionPolicy) {
        this.actionPolicy = actionPolicy;
    }

    @Override
    public EntityModel<OrderView> toModel(OrderView order) {

        EntityModel<OrderView> model = EntityModel.of(order);

        model.add(linkTo(
            methodOn(OrderController.class).one(order.id())
        ).withSelfRel());

        model.add(linkTo(OrderController.class)
            .withRel(ORDERS_REL));

        if (actionPolicy.canCancel(order)) {
            model.add(linkTo(
                methodOn(OrderController.class).cancel(order.id())
            ).withRel(CANCEL_REL));
        }

        if (order.invoiceAvailable()) {
            model.add(linkTo(
                methodOn(OrderController.class).invoice(order.id())
            ).withRel("invoice"));
        }

        return model;
    }

    @Override
    public CollectionModel<EntityModel<OrderView>> toCollectionModel(
            Iterable<? extends OrderView> orders) {

        CollectionModel<EntityModel<OrderView>> collection =
            RepresentationModelAssembler.super.toCollectionModel(orders);

        collection.add(linkTo(OrderController.class).withSelfRel());
        return collection;
    }
}
~~~

`OrderActionPolicy` nên trả lời liệu actor hiện tại có thể thực hiện action trong trạng thái hiện tại hay không. Endpoint `POST /cancel` vẫn phải kiểm tra authorization và trạng thái khi nhận request. Việc không công bố link không thay thế kiểm soát truy cập.

Ví dụ policy nhỏ cho bài thực hành:

~~~java
@Component
class OrderActionPolicy {

    private final CurrentActor currentActor;

    OrderActionPolicy(CurrentActor currentActor) {
        this.currentActor = currentActor;
    }

    boolean canCancel(OrderView order) {
        return order.state() == OrderState.NEW
            && currentActor.hasAuthority("order:cancel");
    }
}
~~~

## 6. Tổ chức test slice bằng MockMvc

Dùng `@WebMvcTest` để kiểm thử controller, assembler, serialization và HTTP response mà không khởi động toàn bộ ứng dụng.

Ví dụ khung test:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.ArgumentMatchers.any;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Pageable;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;

@WebMvcTest(controllers = {
    ApiRootController.class,
    OrderController.class
})
@Import({
    OrderModelAssembler.class,
    OrderActionPolicy.class
})
@WithMockUser(authorities = "order:cancel")
class OrderHypermediaContractTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderQueryService queryService;

    @MockitoBean
    OrderCommandService commandService;

    @MockitoBean
    CurrentActor currentActor;

    @BeforeEach
    void setUpDefaults() {
        given(queryService.findView(42L)).willReturn(
            new OrderView(42L, "ORD-0042", OrderState.NEW, false)
        );
        given(queryService.findViews()).willReturn(List.of(
            new OrderView(42L, "ORD-0042", OrderState.NEW, false)
        ));
    }

    @Test
    void apiRootPublishesOrdersEntryPoint() throws Exception {
        mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON
            ))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath(
                "$._links['https://api.example.test/rels/orders'].href"
            ).exists());
    }
}
~~~

Tùy cấu hình ứng dụng, test slice có thể cần import security configuration, controller advice hoặc hypermedia configuration riêng. Chỉ import những thành phần cần thiết để kiểm thử contract; không biến test slice thành một bản sao của toàn bộ application context.

Nếu dự án đang dùng Spring Framework trước khi có `@MockitoBean`, thay bằng `@MockBean` và import annotation tương ứng.

## 7. Test entry point và điều hướng tới collection

Test đầu tiên xác nhận API root trả HAL và có relation `orders`.

~~~java
@Test
void rootExposesOrdersRelation() throws Exception {

    mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/orders'].href"
        ).exists());
}
~~~

Tiếp theo, không hard-code collection path trong bước điều hướng. Đọc href từ response root rồi gọi link đó:

~~~java
import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.springframework.test.web.servlet.MvcResult;

@Test
void followsOrdersLinkFromApiRoot() throws Exception {

    MvcResult rootResult = mockMvc.perform(
            get("/api").accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andReturn();

    String rootJson = rootResult.getResponse().getContentAsString();

    String ordersHref = JsonPath.read(
        rootJson,
        "$._links['https://api.example.test/rels/orders'].href"
    );

    mockMvc.perform(
            get(URI.create(ordersHref))
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ));
}
~~~

MockMvc hỗ trợ request builder nhận `URI`. Khi dùng href tuyệt đối do link builder tạo, test có thể theo chính URI đó. Nếu ứng dụng có context path hoặc reverse proxy, hãy cấu hình test request tương ứng.

Test này kiểm tra khả năng khám phá: client biết collection thông qua root relation. Nếu server đổi mapping và link builder tạo href mới, test vẫn theo link được công bố.

## 8. Test item representation và relation bắt buộc

Tạo fixture cho một đơn hàng `NEW`:

~~~java
@Test
void orderRepresentationContainsRequiredLinks() throws Exception {

    OrderView order = new OrderView(
        42L,
        "ORD-0042",
        OrderState.NEW,
        false
    );

    given(queryService.findView(42L)).willReturn(order);

    mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.number").value("ORD-0042"))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/orders'].href"
        ).exists());
}
~~~

Ngoài sự tồn tại, hãy kiểm tra href trỏ tới đúng resource. Dùng matcher kiểm tra suffix path hoặc parse URI để kiểm tra path:

~~~java
.andExpect(jsonPath("$._links.self.href")
    .value(org.hamcrest.Matchers.endsWith("/api/orders/42")));
~~~

Không nên kiểm tra cả host `localhost` hoặc port ngẫu nhiên nếu môi trường test không cố định các giá trị đó. Nếu host là một phần của contract sau reverse proxy, hãy viết test riêng cho forwarded headers và cấu hình proxy.

## 9. Test action link theo trạng thái

Đơn hàng mới có thể hủy:

~~~java
@Test
void exposesCancelRelationWhenOrderCanBeCancelled() throws Exception {

    given(currentActor.hasAuthority("order:cancel")).willReturn(true);

    given(queryService.findView(42L)).willReturn(
        new OrderView(
            42L,
            "ORD-0042",
            OrderState.NEW,
            false
        )
    );

    mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/order-cancellation'].href"
        ).exists());
}
~~~

Đơn hàng đã giao không thể hủy:

~~~java
@Test
void doesNotExposeCancelRelationForDeliveredOrder() throws Exception {

    given(currentActor.hasAuthority("order:cancel")).willReturn(true);

    given(queryService.findView(42L)).willReturn(
        new OrderView(
            42L,
            "ORD-0042",
            OrderState.DELIVERED,
            true
        )
    );

    mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/order-cancellation']"
        ).doesNotExist())
        .andExpect(jsonPath("$._links.invoice.href").exists());
}
~~~

Nếu relation được rút gọn bằng CURIE, JSON key thực tế có thể là tên CURIE thay vì URI đầy đủ. Test phải dùng đúng representation đã cấu hình và cần có test xác nhận CURIE declaration được công bố.

Không chỉ kiểm tra `cancel` xuất hiện. Test phủ định bảo vệ contract khỏi việc vô tình công bố action trong trạng thái không hợp lệ.

Thêm test actor không có quyền. Ví dụ method-level `@WithMockUser` ghi đè authority ở class-level:

~~~java
@Test
@WithMockUser(authorities = "order:read")
void doesNotExposeCancelRelationForReadOnlyActor() throws Exception {

    given(queryService.findView(42L)).willReturn(
        new OrderView(42L, "ORD-0042", OrderState.NEW, false)
    );

    given(currentActor.hasAuthority("order:cancel")).willReturn(false);

    mockMvc.perform(
            get("/api/orders/42").accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/order-cancellation']"
        ).doesNotExist());
}
~~~

## 10. Test theo action link để thực hiện workflow

Một test tốt không tự tạo URL action. Nó đọc link từ representation, rồi gọi URI đó.

~~~java
import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.springframework.test.web.servlet.MvcResult;

@Test
void followsCancelLinkAndReceivesUpdatedRepresentation() throws Exception {

    given(currentActor.hasAuthority("order:cancel")).willReturn(true);

    OrderView newOrder = new OrderView(
        42L,
        "ORD-0042",
        OrderState.NEW,
        false
    );

    OrderView cancelledOrder = new OrderView(
        42L,
        "ORD-0042",
        OrderState.CANCELLED,
        false
    );

    given(queryService.findView(42L)).willReturn(newOrder);
    given(commandService.cancel(42L)).willReturn(cancelledOrder);

    MvcResult detailResult = mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andReturn();

    String detailJson =
        detailResult.getResponse().getContentAsString();

    String cancelHref = JsonPath.read(
        detailJson,
        "$._links['https://api.example.test/rels/order-cancellation'].href"
    );

    mockMvc.perform(
            post(URI.create(cancelHref))
                .with(csrf())
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.state").value("CANCELLED"))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath(
            "$._links['https://api.example.test/rels/order-cancellation']"
        ).doesNotExist());
}
~~~

Trong test class, `@WithMockUser` tạo principal đã xác thực; `.with(csrf())` gắn CSRF token cho POST. Nếu ứng dụng dùng cơ chế xác thực khác, hãy thay annotation hoặc request post-processor cho phù hợp.

Thêm một test gọi thẳng action bằng actor thiếu quyền và xác nhận server từ chối request. Test này chứng minh endpoint được bảo vệ độc lập với việc assembler có công bố link hay không.

~~~java
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@Test
@WithMockUser(authorities = "order:read")
void cancelEndpointRejectsReadOnlyActor() throws Exception {

    mockMvc.perform(
            post("/api/orders/42/cancel")
                .with(csrf())
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isForbidden());

    verify(commandService, never()).cancel(42L);
}
~~~

HAL link thông thường không tự mô tả HTTP method hoặc request body. Test dùng POST vì contract của action endpoint quy định như vậy. Nếu client cần khám phá method và input schema từ representation, hãy kiểm thử affordance hoặc media type như HAL-FORMS; đừng suy luận method chỉ từ tên relation.

## 11. Test collection và embedded relation

Khi API trả collection, cần kiểm tra cả relation collection và self link của từng item.

~~~java
@Test
void collectionEmbedsOrdersAndEachOrderHasSelfLink() throws Exception {

    given(queryService.findViews()).willReturn(List.of(
        new OrderView(42L, "ORD-0042", OrderState.NEW, false),
        new OrderView(43L, "ORD-0043", OrderState.PAID, true)
    ));

    mockMvc.perform(
            get("/api/orders")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orders.length()").value(2))
        .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orders[1]._links.self.href").exists());
}
~~~

Relation `orders` trong `_embedded` phụ thuộc relation provider và cấu hình `@Relation` của type được serialize. Nếu test nhận `orderViews` hoặc một tên khác ngoài ý muốn, hãy sửa cấu hình relation thay vì sửa test để chấp nhận tên ngẫu nhiên.

Cần có test collection rỗng:

~~~java
@Test
void emptyCollectionStillExposesNavigationLinks() throws Exception {

    given(queryService.findViews()).willReturn(List.of());

    mockMvc.perform(
            get("/api/orders")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Collection rỗng vẫn cần link self và link điều hướng phù hợp. Client phải có thể tiếp tục khám phá API dù chưa có item nào.

## 12. Test pagination links

Với endpoint phân trang, nên kiểm tra ít nhất ba tình huống:

| Tình huống | Relation cần kiểm tra |
|---|---|
| Trang đầu và còn trang sau | `self`, `next`, `last`; thường có `first` |
| Trang giữa | `self`, `prev`, `next`, `first`, `last` |
| Trang cuối | `self`, `prev`, `first`, không có `next` |

Ví dụ trang đầu:

~~~java
@Test
void firstPageContainsNextLink() throws Exception {

    given(queryService.findPage(any(Pageable.class)))
        .willReturn(pageOfOrders(0, 2, 5));

    mockMvc.perform(
            get("/api/orders")
                .param("page", "0")
                .param("size", "2")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.next.href").exists())
        .andExpect(jsonPath("$._links.last.href").exists());
}
~~~

Trang cuối không có next:

~~~java
@Test
void lastPageDoesNotContainNextLink() throws Exception {

    given(queryService.findPage(any(Pageable.class)))
        .willReturn(pageOfOrders(2, 2, 5));

    mockMvc.perform(
            get("/api/orders")
                .param("page", "2")
                .param("size", "2")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.prev.href").exists())
        .andExpect(jsonPath("$._links.next").doesNotExist());
}
~~~

Trang giữa cần cả prev và next:

~~~java
@Test
void middlePageContainsPreviousAndNextLinks() throws Exception {

    given(queryService.findPage(any(Pageable.class)))
        .willReturn(pageOfOrders(1, 2, 5));

    mockMvc.perform(
            get("/api/orders")
                .param("page", "1")
                .param("size", "2")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.first.href").exists())
        .andExpect(jsonPath("$._links.prev.href").exists())
        .andExpect(jsonPath("$._links.next.href").exists())
        .andExpect(jsonPath("$._links.last.href").exists());
}
~~~

Trong ví dụ, `pageOfOrders(...)` là fixture helper tạo một `Page<OrderView>` có metadata tương ứng. Hãy dùng `PageImpl` hoặc factory của dự án để tạo page có `totalElements`, `totalPages` và `number` đúng.

Nếu endpoint hỗ trợ filter như `status=PAID`, test href của `next` phải giữ filter:

~~~java
.andExpect(jsonPath("$._links.next.href")
    .value(org.hamcrest.Matchers.containsString("status=PAID")));
~~~

Không kiểm tra toàn bộ query string theo thứ tự cố định nếu thứ tự parameter không thuộc contract. Có thể parse URI và kiểm tra từng query parameter.

## 13. Test content negotiation

API cần trả HAL khi client yêu cầu:

~~~java
@Test
void returnsHalWhenClientAcceptsHalJson() throws Exception {

    mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ));
}
~~~

Nếu API chỉ hỗ trợ HAL và không hỗ trợ XML, hãy kiểm tra request yêu cầu XML bị từ chối:

~~~java
@Test
void rejectsUnsupportedRepresentationType() throws Exception {

    mockMvc.perform(
            get("/api/orders/42")
                .accept(MediaType.APPLICATION_XML)
        )
        .andExpect(status().isNotAcceptable());
}
~~~

Kết quả phụ thuộc các message converter được cài đặt. Nếu ứng dụng chủ động hỗ trợ XML, không áp dụng kỳ vọng 406 này. Test phải phản ánh media type thực sự được công bố trong contract.

Ngoài ra, nên kiểm tra response có `Content-Type` phù hợp và các relation vẫn được serialize trong HAL. Một JSON bình thường với status 200 chưa chứng minh response là HAL.

## 14. Test Problem Details và error links

Khi action không hợp lệ theo trạng thái, test phải kiểm tra HTTP status và problem type:

~~~java
@Test
void cancellingDeliveredOrderReturnsProblemDetails() throws Exception {

    given(commandService.cancel(42L))
        .willThrow(new OrderStateConflictException());

    mockMvc.perform(
            post("/api/orders/42/cancel")
                .with(csrf())
                .accept(MediaType.valueOf("application/problem+json"))
        )
        .andExpect(status().isConflict())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.valueOf("application/problem+json")
        ))
        .andExpect(jsonPath("$.type").value(
            "https://api.example.test/problems/order-state-conflict"
        ))
        .andExpect(jsonPath("$.status").value(409));
}
~~~

Nếu API công bố link tài liệu qua HTTP `Link` header, kiểm tra relation `describedby`:

~~~java
.andExpect(header().string(
    HttpHeaders.LINK,
    org.hamcrest.Matchers.containsString("rel=\"describedby\"")
));
~~~

Test nên phân biệt lỗi validation, lỗi xác thực, lỗi authorization và xung đột trạng thái. Không gom mọi lỗi thành cùng một problem type nếu client cần hành vi xử lý khác nhau.

## 15. Test relation không bị phụ thuộc vào thứ tự JSON

Một response có thể serialize link theo thứ tự khác nhau sau khi đổi implementation. Thứ tự phần tử trong `_links` không nên là tiêu chí kiểm thử trừ khi contract của ứng dụng có quy định riêng.

Không nên viết assertion theo kiểu:

~~~java
.andExpect(jsonPath("$._links[0].rel").value("self"));
~~~

HAL biểu diễn `_links` dưới dạng object được đánh chỉ mục bằng relation. Hãy kiểm tra trực tiếp relation:

~~~java
.andExpect(jsonPath("$._links.self.href").exists())
.andExpect(jsonPath("$._links.next.href").exists());
~~~

Với extension relation URI có ký tự đặc biệt, dùng JSONPath bracket notation:

~~~java
.andExpect(jsonPath(
    "$._links['https://api.example.test/rels/order-cancellation'].href"
).exists());
~~~

Không so sánh toàn bộ JSON bằng một chuỗi literal lớn nếu chỉ một vài relation là contract quan trọng. So sánh field có chọn lọc giúp test chịu được thay đổi thứ tự property và các field không liên quan.

## 16. Tạo helper để test dễ đọc

Nếu nhiều test cùng cần lấy href, có thể tạo helper:

~~~java
private String linkHref(
        MvcResult result,
        String relationJsonPath) throws Exception {

    return JsonPath.read(
        result.getResponse().getContentAsString(),
        relationJsonPath
    );
}
~~~

Sử dụng:

~~~java
MvcResult result = mockMvc.perform(
        get("/api").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String ordersHref = linkHref(
    result,
    "$._links['https://api.example.test/rels/orders'].href"
);
~~~

Helper chỉ nên loại bỏ boilerplate. Không tạo một DSL kiểm thử quá tổng quát khiến người đọc khó thấy test đang kiểm tra relation nào.

Có thể thêm helper để parse URI:

~~~java
private URI linkUri(MvcResult result, String relationPath)
        throws Exception {

    return URI.create(linkHref(result, relationPath));
}
~~~

Từ URI đó, test có thể gọi endpoint bằng request builder tương ứng.

## 17. Test client traversal qua nhiều bước

Một client HATEOAS không nên biết trước mọi route. Test traversal mô phỏng cách client sử dụng API:

1. Gọi API root.
2. Đọc relation `orders`.
3. Gọi collection href.
4. Chọn một order trong `_embedded`.
5. Đọc relation `self` của item.
6. Gọi self href để lấy representation chi tiết.
7. Nếu có relation `order-cancellation`, theo href đó để hủy.
8. Đọc response sau hủy và xác nhận relation không còn.

Ví dụ phần traversal:

~~~java
given(currentActor.hasAuthority("order:cancel")).willReturn(true);
given(commandService.cancel(42L)).willReturn(
    new OrderView(42L, "ORD-0042", OrderState.CANCELLED, false)
);

MvcResult root = mockMvc.perform(
        get("/api").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String ordersHref = linkHref(
    root,
    "$._links['https://api.example.test/rels/orders'].href"
);

MvcResult collection = mockMvc.perform(
        get(URI.create(ordersHref)).accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String orderSelfHref = JsonPath.read(
    collection.getResponse().getContentAsString(),
    "$._embedded.orders[0]._links.self.href"
);

MvcResult detail = mockMvc.perform(
        get(URI.create(orderSelfHref)).accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

String cancelHref = linkHref(
    detail,
    "$._links['https://api.example.test/rels/order-cancellation'].href"
);

mockMvc.perform(
        post(URI.create(cancelHref))
            .with(csrf())
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.state").value("CANCELLED"))
    .andExpect(jsonPath(
        "$._links['https://api.example.test/rels/order-cancellation']"
    ).doesNotExist());
~~~

Sau bước này, test đọc action link từ `detail` và gọi đúng href. Test không tự ghép `/api/orders/42` từ ID.

Đây là test tích hợp ở tầng HTTP. Nó kiểm tra nhiều phần cùng lúc: controller, assembler, relation provider, serialization và khả năng điều hướng. Khi thất bại, hãy giữ thêm các test nhỏ cho từng contract để xác định nguyên nhân dễ hơn.

## 18. Phân biệt unit test, web slice và integration test

Không cần dùng một loại test cho mọi mục tiêu.

| Loại test | Nên kiểm tra | Không nên dùng để |
|---|---|---|
| Unit test policy | Trạng thái và quyền có cho phép action không | Kiểm tra URI hoặc serialization HAL |
| Unit test assembler | Relation và link được tạo theo dữ liệu đầu vào | Kiểm tra HTTP content negotiation |
| `@WebMvcTest` + MockMvc | Status, headers, HAL JSON, relation, href, error response | Xác nhận database query thật |
| `@SpringBootTest` | Luồng end-to-end và cấu hình tích hợp | Thay thế toàn bộ test nhỏ |
| Client traversal test | Client có thể khám phá và theo link | Kiểm tra mọi chi tiết implementation |

`WebMvcLinkBuilder` cần request context khi tạo một số URI. Nếu gọi assembler trực tiếp trong unit test mà không có servlet request attributes, test có thể thất bại dù assembler hoạt động đúng trong request thật. Có thể gắn `MockHttpServletRequest` vào `RequestContextHolder`, hoặc kiểm tra assembler thông qua MockMvc để có request context tự nhiên.

Đừng biến mọi assembler test thành Spring context test. Dùng unit test cho policy và mapping thuần, còn test HTTP để xác nhận link thực tế.

## 19. Ma trận test tối thiểu

Trước khi hoàn thành, bộ test cần bao phủ ít nhất các trường hợp sau:

| Nhóm | Trường hợp | Kỳ vọng |
|---|---|---|
| Entry point | `GET /api` | Có `self` và extension relation orders |
| Traversal | Theo orders href | Collection trả 200 |
| Item | Order tồn tại | Có `self` và collection relation |
| Conditional link | Order `NEW` | Có cancellation relation khi actor đủ quyền |
| Conditional link | Order `DELIVERED` | Không có cancellation relation |
| Action | Theo cancellation href | Order chuyển sang `CANCELLED` |
| Action | Hủy order đã giao | 409 Problem Details |
| Collection | Có items | Embedded relation đúng |
| Collection | Không có items | Vẫn có self link |
| Pagination | Trang đầu | Có next nếu còn trang |
| Pagination | Trang cuối | Không có next |
| Filter | Có query filter | Next link giữ filter |
| Media type | Accept HAL | Content-Type HAL |
| Media type | Accept XML không hỗ trợ | 406 |
| Error | Conflict | Type URI đúng và ổn định |
| Link integrity | Theo self href | Resource đích tồn tại |

Một bài thực hành đạt yêu cầu phải có cả test positive và negative. Test chỉ kiểm tra link xuất hiện sẽ bỏ qua lỗi phổ biến là action vẫn còn sau khi trạng thái thay đổi.

## 20. Bài tập mở rộng

Sau khi hoàn thành bộ test tối thiểu, thực hiện thêm các yêu cầu sau:

**A. Kiểm tra quyền theo actor**

- Actor có `order:cancel` nhìn thấy cancellation link khi trạng thái cho phép.
- Actor chỉ có quyền đọc không nhìn thấy action link.
- Gọi POST action bằng actor thiếu quyền vẫn bị từ chối.
- Dù client giữ link cũ, server vẫn kiểm tra quyền tại thời điểm thực thi.

**B. Kiểm tra link và pagination**

- Thay đổi page size.
- Dùng filter status.
- Theo `next` link và xác nhận số trang tăng.
- Ở trang cuối, xác nhận không có `next`.
- Theo `prev` link và xác nhận quay lại đúng trang.

**C. Kiểm tra URI sau khi đổi mapping**

Thay đổi base mapping của controller từ `/api/orders` thành `/api/v2/orders`. Các test traversal không được phải sửa URL collection hoặc item bằng tay. Test chỉ được thay đổi nếu relation hoặc hành vi contract thay đổi có chủ đích.

**D. Kiểm tra CURIE**

Nếu API dùng CURIE cho extension relation:

- Kiểm tra `_links.curies` được công bố.
- Kiểm tra relation rút gọn xuất hiện đúng tên.
- Kiểm tra href CURIE mở rộng thành URI relation đúng.
- Không để client phụ thuộc vào thứ tự CURIE trong JSON.

**E. Kiểm tra affordance**

Nếu API công bố HAL-FORMS:

- Kiểm tra action affordance có method đúng.
- Kiểm tra template hoặc input property được công bố.
- Kiểm tra action không khả dụng không xuất hiện.
- Gửi request theo form metadata và xác nhận server xử lý đúng.

## 21. Tiêu chí đánh giá sản phẩm

Chấm bài theo các tiêu chí sau:

| Tiêu chí | Điểm |
|---|---:|
| Entry point và relation traversal hoạt động | 15 |
| Test item/collection và embedded relation | 15 |
| Conditional action có test positive và negative | 20 |
| Pagination links và filter được kiểm tra | 15 |
| Content negotiation và Problem Details | 10 |
| Client traversal dùng href thực tế | 15 |
| Test dễ đọc, ít phụ thuộc implementation | 10 |
| **Tổng** | **100** |

Bộ test được xem là đạt khi:

- Tất cả test bắt buộc chạy thành công.
- Không có test phải tự ghép route để đi tiếp qua API.
- Action link phản ánh đúng trạng thái và quyền.
- Test xác nhận cả link hiện diện và link vắng mặt.
- Test collection rỗng và pagination không làm mất đường điều hướng.
- Test lỗi xác nhận problem type ổn định.
- Thay đổi mapping nội bộ không làm vỡ test traversal nếu contract không đổi.

## 22. Deliverables cần nộp

Hoàn thiện và lưu các thành phần sau trong project:

1. `OrderHypermediaContractTest` kiểm tra root, item, collection và action.
2. Test pagination links cho trang đầu, giữa và cuối.
3. Test content negotiation cho HAL và media type không hỗ trợ.
4. Test Problem Details cho lỗi xung đột trạng thái.
5. Một test traversal theo link từ root đến action.
6. Fixture hoặc factory tạo Order ở các trạng thái khác nhau.
7. Báo cáo ngắn ghi rõ relation được kiểm tra và các trường hợp positive/negative.
8. Kết quả chạy test suite.

Trong báo cáo, ghi lại một lỗi hypermedia mà test phát hiện được, nguyên nhân và cách sửa. Ví dụ: cancellation link vẫn xuất hiện sau khi order chuyển sang `CANCELLED`, collection relation serialize thành tên không mong muốn, hoặc pagination next link làm mất filter.

## 23. Quy trình thực hiện

Thực hiện dự án theo thứ tự để mỗi lớp contract được xác nhận trước khi thêm tình huống phức tạp:

1. Tạo fixture cho `NEW`, `AWAITING_PAYMENT`, `DELIVERED` và `CANCELLED`.
2. Tạo web test slice với MockMvc.
3. Kiểm tra API root và relation tới collection.
4. Kiểm tra item representation, self link và các relation cơ bản.
5. Kiểm tra action link theo state và actor.
6. Theo href action để thực hiện workflow.
7. Kiểm tra collection, embedded relation và collection rỗng.
8. Kiểm tra pagination links và giữ filter.
9. Kiểm tra HAL content negotiation.
10. Kiểm tra Problem Details và error type URI.
11. Viết traversal test từ root đến action.
12. Chạy toàn bộ test suite và ghi lại lỗi contract đã phát hiện.

Test hypermedia tốt mô tả cách client sử dụng API qua relation và href. Nó bảo vệ semantics của relation, điều kiện khả dụng của action, pagination, media type và error representation. Khi test theo link mà server thực sự công bố, đội phát triển có thể thay đổi route và tổ chức controller mà vẫn giữ contract điều hướng ổn định cho client.

## Tài liệu tham khảo

- [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API — MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [Spring HATEOAS API — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
