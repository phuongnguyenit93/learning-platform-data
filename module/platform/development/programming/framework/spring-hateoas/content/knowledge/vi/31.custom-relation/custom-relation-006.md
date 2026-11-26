# Relation cho action

Trong một REST API dùng hypermedia, client thường cần biết một tài nguyên có thể thực hiện những hành động nghiệp vụ nào. Ví dụ, đơn hàng đang chờ duyệt có thể được duyệt, hủy hoặc yêu cầu bổ sung thông tin. Server có thể công bố các link cho những hành động này ngay trong representation của đơn hàng.

Khi một hành động không có link relation chuẩn phù hợp trong IANA registry, API có thể định nghĩa custom relation. Relation riêng nên dùng một URI tuyệt đối ổn định để định danh ngữ nghĩa hành động, chẳng hạn https://api.example.com/rels/approve. Spring HATEOAS biểu diễn relation bằng LinkRelation, gắn nó vào Link, và có thể dùng CURIE để hiển thị relation URI dài dưới dạng ngắn trong HAL.

Custom relation trả lời câu hỏi “link này biểu thị hành động nghiệp vụ nào?”. Nó không tự định nghĩa HTTP method, payload hoặc quyền truy cập. Nếu client cần biết cách thực hiện thao tác, hãy kết hợp link với affordance để mô tả method và metadata đầu vào/đầu ra. Bài học này trình bày cách thiết kế, công bố, quốc tế hóa và kiểm thử custom relation cho action trong Spring HATEOAS.

## 1. Action link trong hypermedia

Giả sử API trả về một đơn hàng:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Đơn hàng có trạng thái PENDING, vì vậy người dùng có thể duyệt đơn hàng. Representation có thể công bố:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "acme:approve": {
      "href": "https://api.example.com/api/orders/42/approval",
      "title": "Approve order"
    }
  }
}
~~~

Client đọc relation acme:approve để hiểu đây là khả năng duyệt đơn hàng và theo href để khám phá target. Client không phải tự đoán đường dẫn /approval từ cấu trúc URI của đơn hàng.

Một action link thường có ba thành phần:

- Relation: định danh ngữ nghĩa của hành động, ví dụ approve.
- Target URI: nơi client gửi request thực hiện hành động.
- Metadata tùy chọn: tiêu đề, media type hoặc affordance mô tả method và dữ liệu đầu vào.

Link action chỉ nên xuất hiện khi thao tác có ý nghĩa trong trạng thái hiện tại của tài nguyên và phù hợp với người dùng đang truy cập. Server vẫn phải xác thực và phân quyền khi nhận request.

## 2. Chọn relation chuẩn trước khi tạo custom relation

IANA registry có một số relation đã diễn đạt các khả năng chỉnh sửa hoặc lấy biểu mẫu:

| Relation chuẩn | Ý nghĩa |
| --- | --- |
| edit | Target có thể được dùng để chỉnh sửa tài nguyên hiện tại |
| edit-form | Target là nơi lấy biểu mẫu chỉnh sửa tài nguyên |
| create-form | Target là nơi lấy biểu mẫu tạo tài nguyên |
| search | Target có thể được dùng để tìm kiếm trong ngữ cảnh hiện tại |

Nếu ngữ nghĩa của link khớp với một relation đã đăng ký, hãy ưu tiên relation đó. Ví dụ, link đến biểu mẫu sửa đơn hàng có thể dùng edit-form. Nếu link thể hiện một hành động nghiệp vụ cụ thể như duyệt, từ chối, hoàn tiền hoặc phát hành, relation chuẩn có thể không đủ cụ thể.

Khi đó, custom relation giúp API công bố vocabulary riêng:

- approve: duyệt một đơn hàng.
- reject: từ chối một đơn hàng.
- refund: hoàn tiền cho một giao dịch.
- publish: xuất bản một bản nháp.

Không nên tạo custom relation chỉ để thay tên cho self, edit hoặc search. Trước khi thêm relation mới, hãy đọc mô tả IANA để tránh tạo một vocabulary trùng với chuẩn đã có.

## 3. Dùng URI tuyệt đối để định danh custom relation

Theo RFC 8288, relation type được chia thành registered relation type và extension relation type. Registered relation dùng tên đã đăng ký trong IANA. Extension relation dùng URI tuyệt đối để định danh quan hệ do ứng dụng định nghĩa.

Ví dụ custom relation:

~~~text
https://api.example.com/rels/approve
https://api.example.com/rels/reject
https://api.example.com/rels/refund
~~~

URI relation là định danh ngữ nghĩa, không nhất thiết là URI endpoint thực thi. Ví dụ:

| Thành phần | URI |
| --- | --- |
| Custom relation | https://api.example.com/rels/approve |
| Action target | https://api.example.com/api/orders/42/approval |

Hai URI có mục đích khác nhau. Relation định danh ý nghĩa “duyệt đơn hàng”; target là endpoint nhận request thực hiện việc duyệt.

Nên đặt URI relation dưới một domain do tổ chức kiểm soát, giữ nó ổn định và tài liệu hóa ngữ nghĩa. Nếu có thể, URI relation nên mở được tới tài liệu mô tả để developer hoặc công cụ có thể khám phá hợp đồng.

Không dùng một từ chưa đăng ký như approve làm extension relation độc lập trong HAL. Một tên ngắn như vậy có thể xung đột với vocabulary của API khác. Với HAL, hãy dùng CURIE để biểu diễn custom relation URI bằng prefix có namespace.

## 4. Khai báo custom LinkRelation trong Spring HATEOAS

Spring HATEOAS cung cấp LinkRelation để biểu diễn relation theo kiểu thống nhất với các relation IANA. Tạo relation cho hành động duyệt đơn hàng:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class OrderRelations {

    public static final LinkRelation APPROVE =
            LinkRelation.of("https://api.example.com/rels/approve");

    public static final LinkRelation REJECT =
            LinkRelation.of("https://api.example.com/rels/reject");

    private OrderRelations() {
    }
}
~~~

Tách các relation thành hằng số giúp:

- Tránh lặp URI relation ở nhiều controller.
- Giảm lỗi chính tả trong lúc tạo hoặc kiểm tra link.
- Giữ vocabulary nhất quán giữa các representation.
- Thay đổi có kiểm soát khi hợp đồng relation cần tiến hóa.

Không nhầm LinkRelation với IanaLinkRelations. IanaLinkRelations chứa các relation chuẩn đã đăng ký, còn LinkRelation.of(...) cho phép ứng dụng tạo relation riêng.

## 5. Tạo action link bằng Link.of

Khi đã có relation, có thể tạo link trực tiếp:

~~~java
import org.springframework.hateoas.Link;

Link approveLink = Link.of(
        "/api/orders/42/approval",
        OrderRelations.APPROVE
);
~~~

Link là value object bất biến. Phương thức withRel(...) tạo một link mới với relation được chỉ định:

~~~java
Link approveLink = Link.of("/api/orders/42/approval")
        .withRel(OrderRelations.APPROVE)
        .withTitle("Approve order");
~~~

Link.of(href) mặc định dùng relation self, vì vậy nếu link trỏ đến một hành động khác tài nguyên hiện tại, hãy chỉ định relation rõ ràng bằng Link.of(href, relation) hoặc withRel(relation).

## 6. Xây action link từ controller mapping

Trong Spring MVC, WebMvcLinkBuilder giúp tạo target URI từ mapping controller. Nhờ vậy, controller không phải lặp lại chuỗi đường dẫn:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping("/api/orders/{id}/approval")
    public void approve(@PathVariable Long id) {
        // Xử lý nghiệp vụ duyệt đơn hàng.
    }

    Link approveLink(Long id) {
        return linkTo(methodOn(OrderController.class)
                .approve(id))
                .withRel(OrderRelations.APPROVE);
    }
}
~~~

methodOn(...) tạo lời gọi giả lập để Spring HATEOAS đọc mapping của handler method. Nó không thực thi phương thức approve và không gọi nghiệp vụ duyệt đơn hàng.

Nếu mapping controller thay đổi từ /api/orders/{id}/approval sang một URI khác, link được tạo từ mapping cũng thay đổi theo. Điều này giảm nguy cơ controller và link bị lệch nhau.

## 7. Công bố action theo trạng thái tài nguyên

Không phải đơn hàng nào cũng có thể duyệt. Ví dụ, chỉ đơn hàng PENDING mới có hành động approve. Representation có thể công bố link theo trạng thái:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

public EntityModel<OrderDto> toModel(Order order) {
    OrderDto dto = OrderDto.from(order);

    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId()))
            .withSelfRel();

    EntityModel<OrderDto> model = EntityModel.of(dto, self);

    if (orderActionPolicy.canApprove(order)) {
        Link approve = linkTo(methodOn(OrderController.class)
                .approve(order.getId()))
                .withRel(OrderRelations.APPROVE)
                .withTitle("Approve order");

        model.add(approve);
    }

    if (orderActionPolicy.canReject(order)) {
        Link reject = linkTo(methodOn(OrderController.class)
                .reject(order.getId()))
                .withRel(OrderRelations.REJECT)
                .withTitle("Reject order");

        model.add(reject);
    }

    return model;
}
~~~

Trong ví dụ, OrderActionPolicy quyết định hành động có phù hợp với trạng thái nghiệp vụ và người dùng hiện tại hay không. OrderDto.from(...), các getter của Order, controller mapping one/reject và policy là các thành phần của ứng dụng.

Policy có thể khai báo một hợp đồng nhỏ như sau:

~~~java
public interface OrderActionPolicy {
    boolean canApprove(Order order);
    boolean canReject(Order order);
}
~~~

Phương thức toModel(...) ở trên thường nằm trong một OrderModelAssembler triển khai RepresentationModelAssembler<Order, EntityModel<OrderDto>>.

Khi đơn hàng đã được duyệt, link approve có thể không còn xuất hiện. Client có thể dùng sự hiện diện hoặc vắng mặt của link để cập nhật giao diện mà không phải tự suy luận trạng thái nghiệp vụ từ nhiều field.

Đây là cơ chế công bố khả năng, không phải cơ chế bảo mật. Client có thể gửi một URI cũ hoặc tự tạo request. Endpoint approve và reject vẫn phải kiểm tra quyền, trạng thái và các invariant ngay tại thời điểm xử lý.

## 8. Relation và affordance mô tả hai khía cạnh khác nhau

Custom relation cho client biết ý nghĩa nghiệp vụ của link. Affordance mô tả cách tương tác với target, ví dụ HTTP method, input model và output model.

| Thành phần | Câu hỏi |
| --- | --- |
| Custom relation approve | Link này đại diện cho khả năng nghiệp vụ nào? |
| Target URI | Client gửi request tới đâu? |
| HTTP method trong affordance | Client dùng POST, PUT hay PATCH? |
| Input metadata | Client cần gửi dữ liệu nào? |
| Authorization | Người dùng hiện tại có được phép thực hiện không? |

Ví dụ, custom relation approve không tự nói rằng server dùng POST. Mapping controller mới xác định HTTP method:

Đây là biến thể của handler approve ở phần trước, minh họa trường hợp controller muốn trả response entity để chỉ rõ status code:

~~~java
@PostMapping("/api/orders/{id}/approval")
public ResponseEntity<Void> approve(@PathVariable Long id) {
    orderService.approve(id);
    return ResponseEntity.noContent().build();
}
~~~

Nếu client chỉ cần theo link và đã biết hợp đồng HTTP qua tài liệu API, action link có thể là đủ. Nếu client cần khám phá method và input/output ngay trong representation, hãy gắn affordance vào link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

Link self = linkTo(methodOn(OrderController.class)
        .one(id))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
                .approve(id)));
~~~

Spring HATEOAS phân tích handler method được tham chiếu để thu thập mapping, request body và response type. Media type hỗ trợ affordance có thể chuyển metadata này thành cách biểu diễn riêng. Ví dụ HAL-FORMS có thể tạo template mô tả thao tác POST.

Có thể công bố custom action link và affordance cùng lúc nếu client cần cả tên nghiệp vụ ổn định lẫn metadata thao tác. Tránh công bố hai cách biểu diễn trùng lặp nếu chúng không đem lại lợi ích rõ ràng cho client.

## 9. Dùng CURIE để biểu diễn custom relation trong HAL

HAL cho phép dùng CURIE (Compact URI) để biểu diễn extension relation URI dưới dạng tên ngắn có prefix. Ví dụ:

~~~text
URI đầy đủ: https://api.example.com/rels/approve
CURIE:      acme:approve
~~~

Khai báo CurieProvider:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
@EnableHypermediaSupport(
        type = EnableHypermediaSupport.HypermediaType.HAL
)
public class HalConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
~~~

Khi CurieProvider được đăng ký, Spring HATEOAS có thể serialize custom relation thành acme:approve và tự thêm link curies vào representation:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approve": {
      "href": "https://api.example.com/api/orders/42/approval",
      "title": "Approve order"
    }
  }
}
~~~

Client dùng khai báo curies để mở rộng acme:approve thành URI relation đầy đủ. Prefix là namespace của vocabulary; phần approve là tên relation trong namespace đó.

Một application scope chỉ nên có một bean CurieProvider. Provider áp dụng cho các extension relation được serialize trong phạm vi HAL, vì vậy hãy chọn prefix ổn định và tránh xung đột với namespace khác.

## 10. Tên relation không phải tên Java method

Tên Java method mô tả cách server triển khai. Relation là một phần hợp đồng công khai cho client. Hai tên này có thể giống nhau, nhưng không bắt buộc phải giống:

| Java method | Custom relation |
| --- | --- |
| approveOrder | acme:approve |
| rejectOrder | acme:reject |
| refundPayment | acme:refund |
| publishDraft | acme:publish |

Giữ relation ngắn, rõ nghĩa và ổn định. Tránh đưa chi tiết triển khai như tên service, tên class hoặc cấu trúc package vào relation. Nếu refactor Java method mà ý nghĩa nghiệp vụ không đổi, client không nên phải thay đổi theo.

Với những hành động có ngữ cảnh khác nhau, tránh dùng một relation quá chung chung. Ví dụ approve có thể chưa đủ rõ nếu API có duyệt đơn hàng, duyệt hoàn tiền và duyệt tài khoản. Có thể định nghĩa approve-order, approve-refund hoặc một vocabulary được tổ chức rõ ràng hơn.

## 11. Quốc tế hóa tiêu đề action link

Relation là định danh máy đọc và nên ổn định qua các ngôn ngữ. Nội dung hiển thị cho người dùng nên được cung cấp qua title.

Spring HATEOAS hỗ trợ resource bundle tên rest-messages để resolve title của link. Với relation acme:approve, có thể khai báo:

~~~properties
# src/main/resources/rest-messages.properties
_links.acme\:approve.title=Approve order
_links.acme\:reject.title=Reject order
~~~

Bản tiếng Việt:

~~~properties
# src/main/resources/rest-messages_vi.properties
_links.acme\:approve.title=Duyệt đơn hàng
_links.acme\:reject.title=Từ chối đơn hàng
~~~

Client gửi Accept-Language: vi có thể nhận title đã được resolve theo locale nếu ứng dụng cấu hình message source tương ứng. Nếu dùng title tường minh bằng withTitle(...), hãy kiểm tra thứ tự ưu tiên và cấu hình resource bundle của ứng dụng để tránh nội dung bị ghi đè ngoài ý muốn.

Không dùng title làm relation. Title có thể thay đổi cách diễn đạt hoặc được dịch; relation phải giữ nguyên để client nhận diện hành động.

## 12. Phân biệt custom action relation với @Relation

Spring HATEOAS có annotation @Relation để cấu hình relation của item và collection khi tạo embedded resource. Ví dụ:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
        itemRelation = "order",
        collectionRelation = "orders"
)
public class OrderRepresentation
        extends RepresentationModel<OrderRepresentation> {
    // Các thuộc tính của representation.
}
~~~

@Relation giúp LinkRelationProvider xác định relation cho kiểu resource đơn lẻ hoặc collection. Nó không phải annotation để khai báo link action approve hay refund.

Phân biệt:

- LinkRelation.of(...): tạo relation cho một link cụ thể, bao gồm custom action relation.
- IanaLinkRelations: tham chiếu relation chuẩn của IANA.
- @Relation: tùy chỉnh relation cho resource type và collection khi framework tạo embedded representation.
- CurieProvider: ánh xạ extension relation URI thành prefix CURIE trong HAL.

Không nên tạo một LinkRelationProvider tùy chỉnh chỉ để đặt tên cho một action link. Dùng LinkRelation trực tiếp là đủ. Chỉ tùy biến provider khi quy tắc relation của nhiều loại resource cần được quản lý tập trung.

## 13. Kiểm thử custom relation ở mức unit

Có thể kiểm tra relation và target của action link trước khi serialize:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

class OrderActionRelationTest {

    @Test
    void createsApproveLinkWithStableExtensionRelation() {
        LinkRelation approve = LinkRelation.of(
                "https://api.example.com/rels/approve"
        );

        Link link = Link.of(
                "/api/orders/42/approval",
                approve
        );

        assertThat(link.getRel().value())
                .isEqualTo("https://api.example.com/rels/approve");
        assertThat(link.getHref())
                .isEqualTo("/api/orders/42/approval");
    }
}
~~~

Unit test này xác nhận custom relation không bị thay bằng target URI hoặc tên method. Nếu ứng dụng tập trung relation trong OrderRelations, hãy kiểm tra hằng số đó thay vì tạo lại chuỗi ở từng test.

## 14. Kiểm thử action link trong HAL bằng MockMvc

Kiểm thử HTTP cần xác nhận relation custom được serialize đúng và target trỏ đến endpoint action:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(HalConfiguration.class)
class OrderActionLinkMvcTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @MockBean
    OrderActionPolicy orderActionPolicy;

    @Test
    void exposesApproveActionWhenOrderCanBeApproved() throws Exception {
        Order order = Order.pending(42L);
        when(orderService.getRequired(42L)).thenReturn(order);
        when(orderActionPolicy.canApprove(order)).thenReturn(true);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['acme:approve'].href")
                        .value(org.hamcrest.Matchers.endsWith(
                                "/api/orders/42/approval"
                        )));
    }

    @Test
    void hidesApproveActionWhenOrderCannotBeApproved() throws Exception {
        Order order = Order.pending(42L);
        when(orderService.getRequired(42L)).thenReturn(order);
        when(orderActionPolicy.canApprove(order)).thenReturn(false);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['acme:approve']").doesNotExist());
    }
}
~~~

Đây là test slice minh họa. OrderController, OrderService, OrderActionPolicy, Order.pending(...) và DTO/assembler cần được định nghĩa trong ứng dụng. Nếu controller dùng các dependency khác, hãy mock hoặc import cấu hình tương ứng.

Khi không dùng CURIE, JSONPath cần kiểm tra key theo relation URI đầy đủ nếu media type và serializer đang sử dụng biểu diễn đó. Với HAL có CURIE, kiểm tra cả khai báo curies và key rút gọn để bảo đảm client có thể phân giải relation.

## 15. Kiểm thử affordance của action

Nếu API công bố affordance, hãy kiểm tra cả HTTP method và input metadata trong media type hỗ trợ affordance. Ví dụ với HAL-FORMS:

~~~java
mockMvc.perform(get("/api/orders/42")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates").exists());
~~~

Assertion cụ thể cho tên template và method phụ thuộc tên handler method, cách gắn affordance và cấu hình ứng dụng. Với controller có:

~~~java
@PostMapping("/api/orders/{id}/approval")
public ResponseEntity<Void> approve(@PathVariable Long id) {
    // ...
}
~~~

affordance suy ra từ method này mô tả thao tác POST không có request body. Nếu action nhận payload, hãy dùng input DTO rõ ràng và kiểm tra các property được công bố trong template.

Không suy luận HTTP method từ relation name. Hãy xác nhận method trong affordance khớp mapping controller thực tế.

## 16. Thiết kế vocabulary action ổn định

Custom relation là một phần hợp đồng công khai. Trước khi phát hành, hãy thống nhất:

- Prefix namespace, ví dụ acme.
- URI base, ví dụ https://api.example.com/rels/{rel}.
- Tên relation, ví dụ approve, reject, refund.
- Ý nghĩa nghiệp vụ và điều kiện công bố.
- Target URI và HTTP method được hỗ trợ.
- Input/output metadata nếu dùng affordance.
- Cách xử lý khi hành động không còn khả dụng.

Nếu target endpoint thay đổi nhưng ý nghĩa action không đổi, có thể giữ nguyên relation URI và cập nhật href. Nếu ngữ nghĩa action thay đổi không tương thích, hãy định nghĩa relation mới hoặc có chiến lược chuyển tiếp rõ ràng.

Client nên phụ thuộc vào relation và metadata đã công bố, không phụ thuộc vào tên method Java hoặc cấu trúc đường dẫn hiện tại.

## 17. Bảo mật và tính đúng đắn của action link

Action link không cấp quyền. Server cần kiểm tra lại:

- Người dùng đã xác thực hay chưa.
- Người dùng có quyền thực hiện hành động trên tài nguyên này không.
- Trạng thái hiện tại có cho phép hành động không.
- Các điều kiện nghiệp vụ và dữ liệu liên quan còn hợp lệ không.
- Request có bị gửi lặp hoặc xử lý đồng thời hay không.

Ví dụ, đơn hàng có thể đang PENDING khi GET response được tạo, nhưng một người dùng khác có thể duyệt nó trước khi client gửi POST. Endpoint cần kiểm tra trạng thái mới nhất và trả kết quả phù hợp, chẳng hạn 409 Conflict.

Không đưa thông tin nhạy cảm vào relation URI hoặc title. Relation nên mô tả khả năng nghiệp vụ, không chứa token, ID bí mật hoặc thông tin phân quyền.

## 18. Những lỗi thường gặp

**Dùng tên ngắn chưa đăng ký làm custom relation.** Dùng URI tuyệt đối làm extension relation và CURIE để biểu diễn gọn trong HAL.

**Nhầm relation URI với action target.** Relation URI định danh ngữ nghĩa; target URI là endpoint nhận request.

**Coi relation là HTTP method.** approve không nói client phải dùng POST hay PUT. Dùng mapping controller hoặc affordance để mô tả method.

**Dùng custom relation khi đã có relation chuẩn phù hợp.** Kiểm tra IANA registry trước khi mở rộng vocabulary.

**Dùng @Relation để đặt tên action link.** @Relation dành cho relation của item/collection resource type. Dùng LinkRelation cho action link.

**Để tên relation phụ thuộc Java method.** Refactor method không nên làm thay đổi hợp đồng công khai. Khai báo relation thành hằng số ổn định.

**Công bố action không phù hợp trạng thái.** Chỉ thêm link khi hành động khả dụng theo policy; endpoint vẫn phải kiểm tra lại khi nhận request.

**Coi sự vắng mặt của link là bảo mật.** Client có thể tự tạo request. Phân quyền luôn phải được thực thi ở server.

**Đổi relation mà không giữ tương thích.** Relation là vocabulary client sử dụng. Giữ URI ổn định hoặc công bố relation mới cùng kế hoạch chuyển đổi.

## 19. Ghi nhớ

Custom action relation cho phép API công bố các khả năng nghiệp vụ như approve, reject, refund hoặc publish khi IANA chưa có relation chuẩn phù hợp. Extension relation nên là URI tuyệt đối ổn định, ví dụ https://api.example.com/rels/approve. Spring HATEOAS biểu diễn nó bằng LinkRelation.of(...) và gắn vào link bằng Link.of(...) hoặc withRel(...).

Trong HAL, dùng CurieProvider để biểu diễn URI relation dài bằng prefix như acme:approve. Custom relation xác định ý nghĩa action; target URI xác định nơi gửi request; affordance mô tả HTTP method và metadata đầu vào/đầu ra. @Relation phục vụ relation của item và collection resource type, không phải action relation.

Chỉ công bố action khi phù hợp với trạng thái và policy hiện tại. Link không thay thế xác thực hoặc phân quyền. Kiểm thử relation, target, CURIE, affordance và việc ẩn/hiện action theo trạng thái để giữ hợp đồng hypermedia ổn định.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [Spring HATEOAS Reference – Link Relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference – CurieProvider](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie-provider)
- [Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
