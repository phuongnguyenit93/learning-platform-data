# Tương thích custom relation

Trong REST API có hypermedia, **link relation** (rel) mô tả mối quan hệ về ngữ nghĩa giữa resource hiện tại và resource đích. Những relation phổ biến như **self**, **next** hoặc **collection** có thể dùng tên đã được đăng ký với IANA. Khi API cần mô tả một quan hệ đặc thù của nghiệp vụ, chẳng hạn phê duyệt đơn hàng hoặc xem lịch sử thanh toán, ứng dụng có thể định nghĩa **custom relation**.

Custom relation là một phần của hợp đồng API. Client dựa vào relation để nhận biết khả năng hoặc loại resource mà link đại diện; server có thể thay đổi URI đích mà không buộc client thay đổi nếu relation vẫn giữ nguyên ý nghĩa. Ngược lại, đổi relation có thể làm client cũ không tìm thấy link dù href vẫn truy cập được.

Spring HATEOAS cung cấp **LinkRelation**, **LinkRelationProvider**, **@Relation** và **CurieProvider** để tạo, chuẩn hóa và serialize relation. Để giữ tương thích, cần chọn định danh ổn định, công bố rõ ý nghĩa, quản lý thay đổi theo lộ trình và kiểm thử cả representation server lẫn cách client khám phá link.

## Relation là một phần của hợp đồng hypermedia

Một link có thể được hiểu là mối quan hệ có kiểu giữa ngữ cảnh hiện tại và tài nguyên đích:

~~~json
{
  "_links": {
    "approve-order": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
~~~

Trong ví dụ, **approve-order** mô tả ý nghĩa của link; **href** chỉ URI mà client có thể truy cập. Hai thành phần không thay thế cho nhau:

- **Relation** nói client đang nhìn thấy khả năng hoặc quan hệ nào.
- **Href** nói client đi tới đâu để sử dụng khả năng đó.
- **HTTP method và affordance** mô tả cách tương tác nếu media type cung cấp đủ metadata.
- **Title** có thể cung cấp nhãn hiển thị cho người dùng, nhưng không phải định danh để client điều khiển luồng nghiệp vụ.

Nếu server chuyển endpoint từ /orders/42/approval sang /approvals/42, nó có thể giữ nguyên relation approve-order và chỉ cập nhật href. Client vẫn tìm đúng link theo ngữ nghĩa đã biết.

Không dùng relation như tên hiển thị hoặc tên method Java. Tên relation cần ổn định qua các lần refactor, đổi controller, đổi cấu trúc route và thay đổi nội bộ của ứng dụng.

## Registered relation và extension relation

RFC 8288 phân loại relation thành hai nhóm:

| Nhóm | Cách nhận diện | Khi sử dụng |
| --- | --- | --- |
| Registered relation | Token đã đăng ký trong IANA Link Relation Registry, ví dụ self, next, about | Khi ý nghĩa đã được định nghĩa chung và phù hợp với API |
| Extension relation | URI duy nhất do tổ chức hoặc ứng dụng kiểm soát | Khi cần diễn đạt quan hệ riêng của miền nghiệp vụ |

Ưu tiên relation IANA nếu đã có relation đúng ngữ nghĩa. Không tạo my-self, next-page hoặc một tên riêng khác chỉ để thay thế relation chuẩn self hoặc next.

Nếu không có relation đã đăng ký phù hợp, hãy dùng một URI tuyệt đối do tổ chức kiểm soát, ví dụ:

~~~text
https://api.example.com/rels/approve-order
https://api.example.com/rels/payment-history
https://api.example.com/rels/reopen-case
~~~

URI relation là định danh của ngữ nghĩa, không nhất thiết là URI endpoint thực thi thao tác. Nó có thể trỏ tới trang mô tả hợp đồng, nhưng theo RFC 8288, client không nên tự động truy cập URI định nghĩa relation chỉ vì nhìn thấy nó trong response. Hãy dùng link href riêng để thực hiện điều hướng.

Custom relation URI nên:

- Thuộc domain mà tổ chức kiểm soát hoặc được ủy quyền.
- Dùng chữ thường nhất quán để tránh các biến thể khó phân biệt.
- Có ngữ nghĩa ngắn gọn, cụ thể và được tài liệu hóa.
- Được giữ ổn định sau khi client đã tích hợp.
- Không gắn chặt với tên class, tên package hoặc cấu trúc controller nội bộ.

Không dùng một token tùy ý như approve-order làm extension relation trên wire nếu nó chưa được đăng ký. LinkRelation.of(...) có thể nhận chuỗi, nhưng việc tạo được đối tượng Java không tự chứng minh giá trị đó phù hợp với quy tắc relation của giao thức.

## Chọn relation chuẩn bằng IanaLinkRelations

Spring HATEOAS cung cấp **IanaLinkRelations** cho các relation đã đăng ký. Dùng các hằng này giúp code thể hiện rõ rằng relation thuộc bộ chuẩn:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
Link next = Link.of("/orders?page=2", IanaLinkRelations.NEXT);
~~~

Nếu relation đã có trong IANA, không nên tự tạo một extension URI có vẻ tương tự. Ví dụ, relation next đã có nghĩa chung là tài nguyên tiếp theo trong chuỗi điều hướng. Chỉ tạo custom relation khi API thực sự cần một ngữ nghĩa khác.

## Tạo custom relation bằng LinkRelation

**LinkRelation** là value type của Spring HATEOAS để biểu diễn relation. Có thể định nghĩa các hằng dùng chung trong một lớp riêng:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class OrderLinkRelations {

    public static final LinkRelation ORDER =
        LinkRelation.of("https://api.example.com/rels/order");

    public static final LinkRelation ORDERS =
        LinkRelation.of("https://api.example.com/rels/orders");

    public static final LinkRelation APPROVE_ORDER =
        LinkRelation.of("https://api.example.com/rels/approve-order");

    public static final LinkRelation PAYMENT_HISTORY =
        LinkRelation.of("https://api.example.com/rels/payment-history");

    private OrderLinkRelations() {
    }
}
~~~

Lớp hằng số tập trung tên relation giúp assembler, processor và test dùng cùng một định danh. Khi cần thay đổi, nhóm có thể tìm tất cả nơi sử dụng qua một biểu tượng duy nhất.

Gắn custom relation vào link:

~~~java
import org.springframework.hateoas.Link;

Link approve = Link.of(
    "/orders/42/approval",
    OrderLinkRelations.APPROVE_ORDER
);
~~~

Hoặc tạo href từ mapping controller:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link approve = linkTo(
        methodOn(OrderController.class).approve(order.getId()))
    .withRel(OrderLinkRelations.APPROVE_ORDER);
~~~

methodOn(...) giúp href bám theo mapping thực tế. Relation vẫn là hằng nghiệp vụ độc lập với tên phương thức approve. Nếu controller đổi tên hoặc route thay đổi, relation không cần đổi theo.

## Relation cho item và collection bằng @Relation

Khi Spring HATEOAS cần xác định relation theo kiểu representation, có thể dùng **@Relation** để khai báo tên item và collection:

~~~java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "https://api.example.com/rels/order",
    collectionRelation = "https://api.example.com/rels/orders"
)
public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

@Relation giúp Spring HATEOAS chọn relation khi representation được nhúng hoặc khi cần relation của item/collection. Nếu các giá trị này là extension relation, chúng cần được serialize thành định danh URI hợp lệ. Ví dụ trên dùng URI đầy đủ nên phù hợp khi không compact bằng CURIE. Nếu muốn dùng CURIE, với CurieProvider đã cấu hình, có thể khai báo tên cục bộ như itemRelation = "order" và collectionRelation = "orders"; serializer sẽ thêm prefix khi xuất HAL.

Đừng để relation mặc định tự thay đổi theo tên class khi đó là một phần hợp đồng công khai. DefaultLinkRelationProvider thường lấy tên class đã viết thường làm item relation và thêm hậu tố List cho collection relation; đổi tên class có thể làm thay đổi relation được phát ra. Khai báo @Relation tường minh giúp giữ tên ổn định qua refactor.

## LinkRelationProvider và quy tắc relation theo kiểu

**LinkRelationProvider** đóng gói cách Spring HATEOAS xác định relation cho một kiểu item hoặc collection. Theo cơ chế mặc định:

1. Nếu kiểu được gắn @Relation, provider sử dụng các giá trị trong annotation.
2. Nếu không có annotation, provider dùng tên class viết thường làm item relation và thêm hậu tố List cho collection relation.
3. Nếu thư viện Evo Inflector có trong classpath, collection relation có thể được tạo bằng quy tắc số nhiều tiếng Anh.
4. Controller có @ExposesResourceFor có thể được liên hệ với domain type mà nó expose.

Spring HATEOAS tự cung cấp LinkRelationProvider khi bật hỗ trợ hypermedia. Ứng dụng có thể thay thế hoặc bổ sung provider bằng cách triển khai interface và đăng ký bean khi cần quy tắc đặt tên riêng.

Ví dụ một provider tùy biến có thể áp dụng quy ước relation thống nhất cho các kiểu domain. Tuy nhiên, không nên thay đổi provider dùng chung chỉ để sửa một relation đơn lẻ. Nếu chỉ một model có tên đặc biệt, @Relation thường rõ ràng và ít ảnh hưởng hơn.

Khi triển khai provider riêng, cần kiểm tra:

- Relation item và collection có ổn định qua lần build hay không.
- Các kiểu không được provider hỗ trợ có được delegate đúng hay không.
- Tên relation không xung đột với relation IANA hoặc namespace của module khác.
- Client nhận đúng relation sau khi serialize HAL.

Ví dụ provider riêng chỉ xử lý một kiểu representation:

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
class OrderModelRelationProvider implements LinkRelationProvider {

    @Override
    public LinkRelation getItemResourceRelFor(Class<?> type) {
        return OrderLinkRelations.ORDER;
    }

    @Override
    public LinkRelation getCollectionResourceRelFor(Class<?> type) {
        return OrderLinkRelations.ORDERS;
    }

    @Override
    public boolean supports(LinkRelationProvider.LookupContext context) {
        return context.getType().equals(OrderModel.class);
    }
}
~~~

Ví dụ giả định lớp OrderLinkRelations khai báo hai URI extension ORDER và ORDERS. Provider chỉ nhận OrderModel; những kiểu khác cần được xử lý bởi provider mặc định hoặc provider khác. Đây là phương án thay cho @Relation trên OrderModel; nếu dùng provider này, bỏ annotation @Relation khỏi kiểu đó để tránh hai provider cùng xử lý một loại. Không để hai provider cùng nhận một kiểu nếu không có quy tắc ưu tiên rõ ràng, vì relation được chọn có thể phụ thuộc cơ chế delegate và thứ tự provider.

## CURIE: rút gọn custom relation trong HAL

Extension relation URI có thể dài. HAL hỗ trợ **CURIE** (Compact URI) để biểu diễn URI theo dạng rút gọn. Ví dụ:

~~~text
acme:approve-order
~~~

có thể đại diện cho:

~~~text
https://api.example.com/rels/approve-order
~~~

nếu response định nghĩa prefix acme bằng một URI template tương ứng. CURIE là cách serialize rút gọn của extension relation; nó không tạo ra một ngữ nghĩa relation mới.

Spring HATEOAS cung cấp **CurieProvider** và implementation **DefaultCurieProvider**. Khi có bean này, HAL serializer tự thêm link curies để client biết cách mở rộng prefix:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HalRelationConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "acme",
            UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
~~~

Ví dụ dùng @EnableHypermediaSupport cho ứng dụng Spring không có cấu hình hypermedia tương ứng. Với Spring Boot đã auto-configure HAL, hãy tích hợp bean CurieProvider vào cấu hình hiện có thay vì bật thêm một cấu hình MVC trùng lặp.

Khi dùng CurieProvider này, relation cục bộ chưa đăng ký IANA được khai báo bằng tên ngắn:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link approve = Link.of(
    "/orders/42/approval",
    LinkRelation.of("approve-order")
);
~~~

Trong cấu hình có CURIE acme ở trên, Spring HATEOAS serialize relation cục bộ approve-order thành acme:approve-order và cung cấp link curies để client mở rộng. Nếu không bật CURIE, hãy dùng URI đầy đủ như OrderLinkRelations.APPROVE_ORDER đã khai báo ở phần trước.

Response HAL có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approve-order": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
~~~

Client đọc curies, lấy prefix acme và template URI, rồi mở rộng acme:approve-order thành URI relation đầy đủ. Client không cần tự đoán base URI. Nếu CURIE được dùng, định nghĩa prefix phải xuất hiện trong phạm vi response để client có thể giải mã relation.

Một application scope chỉ nên có một bean CurieProvider mặc định. Nếu cần nhiều namespace, dùng cấu hình map CURIE của DefaultCurieProvider và xác định rõ prefix mặc định; tránh đổi prefix tùy tiện giữa các response.

## Phân biệt CURIE, relation và href

Ba giá trị sau có vai trò riêng:

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| CURIE | acme:approve-order | Tên relation rút gọn trong HAL |
| URI relation đầy đủ | https://api.example.com/rels/approve-order | Định danh ổn định của ngữ nghĩa |
| Href | https://api.example.com/orders/42/approval | URI endpoint thực hiện thao tác |

Không dùng href làm relation. Không dùng CURIE nếu response không công bố định nghĩa prefix. Không xem URI relation như endpoint mà client phải gọi để thực hiện thao tác.

## Tương thích khi relation thay đổi

Giả sử phiên bản đầu của API công bố relation:

~~~text
https://api.example.com/rels/approve
~~~

Sau này đội phát triển muốn dùng tên cụ thể hơn:

~~~text
https://api.example.com/rels/approve-order
~~~

Nếu thay thế relation cũ ngay lập tức, client đã tìm approve sẽ không còn thấy link. Dù href vẫn trỏ tới cùng endpoint, client không thể biết link mới có cùng ngữ nghĩa nếu nó không hiểu relation mới.

Một lộ trình chuyển đổi an toàn hơn:

1. Định nghĩa relation mới và tài liệu hóa ngữ nghĩa.
2. Phát hành server thêm relation mới, đồng thời duy trì relation cũ như alias tạm thời nếu cần hỗ trợ client cũ.
3. Cập nhật client ưu tiên relation mới và chỉ dùng relation cũ làm fallback trong giai đoạn chuyển tiếp.
4. Theo dõi client đã chuyển đổi qua telemetry hoặc phiên bản tích hợp.
5. Thông báo thời điểm ngừng relation cũ theo chính sách tương thích của API.
6. Chỉ gỡ alias cũ sau khi các client phụ thuộc đã được nâng cấp hoặc thời hạn hỗ trợ đã kết thúc.

Ví dụ server phát cả hai relation cùng trỏ tới một endpoint:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link approveTarget = Link.of("/orders/42/approval");

model.add(approveTarget.withRel(OrderLinkRelations.APPROVE_ORDER));
model.add(approveTarget.withRel(
    LinkRelation.of("https://api.example.com/rels/approve")));
~~~

Relation cũ chỉ được giữ như alias trong thời gian chuyển tiếp. Không nên duy trì alias vô thời hạn nếu nó gây nhầm lẫn về ngữ nghĩa hoặc làm client mới tiếp tục dùng hợp đồng cũ.

Client có thể ưu tiên relation mới rồi fallback về relation cũ:

~~~java
import java.util.Optional;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Optional<Link> approveLink =
    model.getLink(OrderLinkRelations.APPROVE_ORDER);

if (approveLink.isEmpty()) {
    approveLink = model.getLink(
        LinkRelation.of("https://api.example.com/rels/approve"));
}

approveLink.ifPresent(link -> follow(link.getHref()));
~~~

follow(...) là hàm HTTP client của ứng dụng. Client nên kiểm tra link có tồn tại trước khi bật hành động; nếu không có relation nào được hỗ trợ, hãy ẩn hoặc vô hiệu hóa thao tác thay vì tự đoán endpoint.

## Không đổi ngữ nghĩa của relation đang tồn tại

Relation là định danh ngữ nghĩa. Nếu relation approve-order trước đây có nghĩa là gửi yêu cầu phê duyệt, không được đổi nó thành xác nhận đơn hàng đã hoàn tất chỉ vì cả hai thao tác có vẻ gần nhau.

Khi ngữ nghĩa thay đổi đáng kể:

- Tạo relation mới.
- Giữ relation cũ cho hành vi cũ trong thời gian tương thích nếu server còn hỗ trợ.
- Cập nhật tài liệu mô tả relation.
- Cập nhật client để nhận biết relation mới.

Nếu chỉ đổi URI đích, không cần đổi relation. Nếu chỉ đổi nhãn hiển thị, hãy dùng thuộc tính title thay vì đổi relation. Nếu đổi controller hoặc route, giữ relation và cập nhật href.

## Client cần chịu được relation chưa biết

Một client hypermedia có thể nhận các relation mà phiên bản client chưa biết. Điều này là bình thường khi server bổ sung khả năng mới. Client nên:

- Bỏ qua relation không nhận diện được nếu nó không ảnh hưởng đến luồng bắt buộc.
- Tìm relation đã biết thay vì dựa vào thứ tự link trong JSON.
- Dùng curies để mở rộng relation rút gọn trước khi so sánh.
- Không suy luận rằng sự xuất hiện hoặc vắng mặt của một relation khác sẽ thay đổi ý nghĩa của relation đang xét.
- Không gọi href của relation chưa biết chỉ vì nó xuất hiện trong response.
- Giữ fallback có chủ đích cho các relation cũ trong giai đoạn migration.

Không viết client chỉ chấp nhận một danh sách cứng tất cả relation mà server có thể phát. Cách đó khiến việc bổ sung link mới trở thành thay đổi phá vỡ client dù API chỉ mở rộng khả năng.

## Cardinality và hình dạng HAL

Một relation có thể xuất hiện với một hoặc nhiều link. Trong HAL, một relation có một link thường được serialize thành object; khi có nhiều link cùng relation, serializer có thể biểu diễn thành mảng. Vì vậy, client không nên giả định một relation luôn là một JSON object nếu API cho phép nhiều đích.

Khi thiết kế custom relation, cần quy định rõ:

- Relation có thể có nhiều link hay chỉ một link.
- Nếu có nhiều link, client chọn theo tiêu chí nào, ví dụ title, type hoặc thuộc tính khác.
- Thứ tự link có ý nghĩa hay không; mặc định không nên dựa vào thứ tự.
- Link có thể xuất hiện lặp giữa các response hay thay đổi theo quyền/trạng thái.

Nếu đổi từ một link sang nhiều link, kiểm thử client cần xác nhận parser xử lý cả hai dạng. Không nên thay đổi cardinality bất ngờ khi client hiện tại chỉ đọc một object.

## Kiểm thử custom relation ở phía server

Test server nên xác nhận relation được serialize đúng và href vẫn tách biệt với định danh relation. Ví dụ với MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCustomRelationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesApproveOrderRelation() throws Exception {
        mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$._links['https://api.example.com/rels/approve-order'].href")
                .exists());
    }
}
~~~

EXISTING_ORDER_ID là ID fixture tồn tại và có trạng thái cho phép phê duyệt. Test này xác nhận custom relation xuất hiện trong HAL response. Nên có thêm test cho trạng thái không cho phép phê duyệt để xác nhận link bị ẩn khi hành động không khả dụng.

Nếu dùng CURIE, kiểm tra cả khai báo prefix và relation đã compact:

~~~java
mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies.name").value("acme"))
    .andExpect(jsonPath("$._links['acme:approve-order'].href").exists());
~~~

Test cần khớp cấu hình CURIE thực tế. Nếu có nhiều CURIE, không nên mặc định phần tử đầu tiên luôn là acme; hãy tìm phần tử theo name hoặc kiểm tra key relation đã compact.

## Kiểm thử tương thích phía client

Client nên có test cho các trường hợp:

- Response chỉ có relation mới.
- Response chỉ có relation cũ trong thời gian chuyển tiếp.
- Response có cả hai relation.
- Response không có relation nào mà client biết.
- Response có CURIE và client phải mở rộng đúng URI.
- Response có nhiều link cùng relation.
- Href thay đổi nhưng relation giữ nguyên.
- Relation mới xuất hiện mà client cũ vẫn bỏ qua an toàn.

Một test contract nên so sánh ngữ nghĩa và cấu trúc quan trọng thay vì snapshot toàn bộ JSON quá cứng. Hãy xác nhận relation, href, CURIE và cardinality theo hợp đồng; không phụ thuộc thứ tự thuộc tính JSON.

## Những lỗi thường gặp

- **Dùng token tùy ý làm custom rel:** relation không được đăng ký nhưng không phải URI duy nhất.
- **Dùng tên class làm hợp đồng:** refactor class làm thay đổi relation do provider mặc định sinh ra.
- **Đổi relation cùng lúc với route:** client mất khả năng tìm link dù chỉ có href cần thay đổi.
- **Đổi ngữ nghĩa relation cũ:** client cũ thực hiện hành động sai vì vẫn tin ý nghĩa trước đây.
- **Đổi CURIE prefix mà không kiểm thử:** client hardcode acme: có thể không còn resolve được relation.
- **Không công bố curies link:** client không thể mở rộng CURIE thành URI đầy đủ.
- **Dùng URI relation như endpoint:** client gọi URI mô tả ngữ nghĩa thay vì href của link.
- **Xóa relation cũ quá sớm:** client chưa nâng cấp bị mất khả năng điều hướng.
- **Giả định chỉ có một link:** response hợp lệ có thể chứa nhiều link cùng relation.
- **Dựa vào thứ tự link:** thứ tự serialize không phải hợp đồng điều hướng ổn định.

Custom relation tương thích cần một định danh duy nhất, ngữ nghĩa ổn định và lộ trình thay đổi có kiểm soát. Với Spring HATEOAS, dùng IanaLinkRelations cho relation chuẩn, LinkRelation cho extension URI, @Relation hoặc LinkRelationProvider cho relation theo kiểu và CurieProvider khi cần dạng rút gọn trong HAL. Khi server giữ alias trong thời gian chuyển tiếp, client bỏ qua relation chưa biết và cả hai phía kiểm thử hợp đồng thực tế, API có thể bổ sung hoặc đổi khả năng mà không làm hỏng các client đang hoạt động.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – LinkRelationProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS API – DefaultCurieProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA – Link Relation Types](https://www.iana.org/assignments/link-relations/)
