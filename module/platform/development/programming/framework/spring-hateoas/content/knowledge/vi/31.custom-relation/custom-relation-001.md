# Khi nào cần custom relation

Trong REST API dùng hypermedia, mỗi link cần một relation (`rel`) để client hiểu ý nghĩa của tài nguyên hoặc khả năng mà link đại diện. IANA đã đăng ký nhiều relation chuẩn như `self`, `collection`, `item`, `next`, `prev`, `related` và `edit`. Khi một relation chuẩn diễn đạt đúng ngữ nghĩa, hãy dùng nó. Khi API có một quan hệ hoặc hành động riêng của domain mà registry không mô tả phù hợp, có thể định nghĩa custom relation.

Custom relation giúp client nhận biết một khả năng theo ý nghĩa nghiệp vụ, ví dụ phê duyệt đơn hàng, yêu cầu hoàn tiền, đăng ký tham gia hoặc tải báo cáo. Trong hợp đồng công khai, extension relation nên được định danh bằng URI tuyệt đối theo quy tắc Web Linking. Với HAL, CURIE có thể rút gọn URI relation thành tên dễ đọc như `ex:approve`. Spring HATEOAS hỗ trợ biểu diễn relation qua `LinkRelation` và cấu hình CURIE cho HAL.

## Relation mô tả ý nghĩa của link

Một link gồm URI đích và relation. URI trả lời câu hỏi client có thể truy cập ở đâu; relation trả lời câu hỏi link đó có ý nghĩa gì trong ngữ cảnh representation hiện tại.

Ví dụ:

```json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "collection": {
      "href": "https://shop.example/api/orders"
    },
    "ex:approve": {
      "href": "https://shop.example/api/orders/o-42/approval"
    }
  }
}
```

Client có thể hiểu `self` và `collection` theo semantics chuẩn. Relation `ex:approve` là extension relation do API định nghĩa: nó cho biết link dẫn đến khả năng phê duyệt đơn hàng. Client không cần biết route được xây từ controller nào, cũng không cần tự nối `/approval` vào URI đơn hàng.

Relation không phải tên method Java, tên endpoint hay HTTP method. `approve` diễn đạt ngữ nghĩa hành động; target URI và affordance mô tả cách thực hiện hành động đó. Một thao tác có thể dùng `POST`, `PATCH` hoặc một cơ chế khác mà ý nghĩa relation vẫn giữ nguyên nếu hợp đồng không đổi.

## Khi nào dùng relation chuẩn của IANA?

Trước khi tạo relation riêng, hãy tìm relation chuẩn có semantics phù hợp trong IANA Link Relation Type Registry. Dùng relation chuẩn khi:

- Ý nghĩa link khớp với định nghĩa đã đăng ký.
- Client cần hiểu một khái niệm phổ biến, không phụ thuộc domain cụ thể.
- Relation mô tả điều hướng hoặc quan hệ tổng quát như self, collection, item, next, prev, alternate, describedby hoặc related.

Ví dụ, nếu một đơn hàng liên kết đến collection chứa các đơn hàng, dùng `collection`; nếu collection liên kết đến một member, dùng `item`. Không tạo `ordersCollection` chỉ để đổi tên relation `collection`.

Spring HATEOAS cung cấp `IanaLinkRelations` để sử dụng các relation chuẩn dưới dạng hằng:

```java
import org.springframework.hateoas.IanaLinkRelations;

IanaLinkRelations.SELF;
IanaLinkRelations.COLLECTION;
IanaLinkRelations.ITEM;
IanaLinkRelations.NEXT;
IanaLinkRelations.PREV;
IanaLinkRelations.RELATED;
```

Tên hằng cụ thể phụ thuộc phiên bản Spring HATEOAS. Hãy dùng các hằng có trong phiên bản dự án thay vì tự tạo một relation riêng trùng nghĩa với relation chuẩn.

## Khi nào cần custom relation?

Custom relation phù hợp khi API cần công bố ngữ nghĩa domain hoặc một khả năng mà relation chuẩn không diễn đạt đầy đủ. Ví dụ:

| Nhu cầu | Relation có thể định nghĩa | Vì sao cần custom relation |
| --- | --- | --- |
| Phê duyệt đơn hàng | `.../rels/approve` | `approve` là hành động nghiệp vụ cụ thể, không chỉ là link đến một resource liên quan. |
| Yêu cầu hoàn tiền | `.../rels/refund` | Phân biệt yêu cầu hoàn tiền với link đến hóa đơn hoặc giao dịch. |
| Đăng ký tham gia sự kiện | `.../rels/register` | Client cần nhận diện khả năng đăng ký theo ngữ nghĩa domain. |
| Tải báo cáo đối soát | `.../rels/reconciliation-report` | Link đại diện cho một loại báo cáo chuyên biệt. |
| Gửi đơn hàng vào quy trình đóng gói | `.../rels/submit-for-fulfillment` | Hành động có ý nghĩa rõ ràng trong quy trình fulfillment. |

Nên dùng custom relation khi client thực sự cần phân biệt khả năng đó để quyết định hành vi. Nếu tên relation chỉ phản ánh cách code được tổ chức, hoặc không có client nào cần hiểu ngữ nghĩa riêng, custom relation có thể làm hợp đồng phức tạp không cần thiết.

Một custom relation tốt có ngữ nghĩa ổn định, có tài liệu và không phụ thuộc route hiện tại. Ví dụ, `approve` vẫn có thể trỏ đến `/api/orders/{id}/approval`, `/workflow/approvals/{id}` hoặc một dịch vụ khác sau khi backend thay đổi. Client vẫn tìm relation phê duyệt theo cùng một định danh.

## Extension relation theo RFC 8288

RFC 8288, *Web Linking*, phân biệt relation type đã đăng ký với extension relation type. Relation đã đăng ký dùng token trong registry; extension relation type được biểu diễn bằng URI tuyệt đối. Vì vậy, với API công khai, không nên chỉ đặt một token tùy ý như `approve` rồi kỳ vọng mọi client hiểu đó là relation chuẩn.

Ví dụ URI relation:

```text
https://api.example.com/rels/approve
https://api.example.com/rels/refund
https://api.example.com/rels/reconciliation-report
```

URI relation là định danh ngữ nghĩa, không nhất thiết là URI endpoint thực thi hành động. Nó nên ổn định và có thể trỏ đến tài liệu giải thích relation, gồm:

- Ý nghĩa và ngữ cảnh sử dụng.
- Loại resource mà relation thường xuất hiện.
- Điều kiện để link được công bố.
- HTTP method, request representation và response behavior nếu relation biểu diễn hành động.
- Quy tắc authorization và các lỗi nghiệp vụ có thể xảy ra.
- Quy tắc tương thích và thay đổi semantics.

Client không cần dereference URI relation trong mỗi request để sử dụng link. Client có thể nhận diện URI đã biết và dùng tài liệu đã tích hợp trước. Khả năng URI relation mở được tài liệu giúp developer và công cụ khám phá semantics khi cần.

Không gắn version route vào URI relation nếu semantics không thay đổi. Ví dụ `/api/v2/orders/42/approval` có thể là target mới, nhưng relation `https://api.example.com/rels/approve` vẫn giữ nguyên. Nếu ý nghĩa hành động thay đổi không tương thích, hãy định nghĩa relation mới hoặc version hóa tài liệu/contract theo chính sách rõ ràng.

## Phân biệt custom relation với relation của embedded resource

Spring HATEOAS có một số khái niệm tên gần nhau nhưng giải quyết các việc khác nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `LinkRelation` | Biểu diễn relation của một link trong `_links`. | `https://api.example.com/rels/approve` |
| `IanaLinkRelations` | Các hằng cho relation chuẩn IANA. | `self`, `collection`, `next` |
| `@Relation` | Đặt tên item relation và collection relation khi serialize resource/collection, thường dùng cho `_embedded`. | `order` và `orders` |
| `LinkRelationProvider` | Xác định tên item/collection relation cho kiểu resource. | Tìm relation cho `OrderResource.class`. |
| `CurieProvider` | Rút gọn URI relation thành CURIE khi serialize HAL. | URI `.../rels/approve` thành `ex:approve`. |

`@Relation(itemRelation = "order", collectionRelation = "orders")` không đăng ký custom link relation `approve`. `LinkRelationProvider` cũng không thay thế `CurieProvider`: provider thứ nhất xác định tên relation của item/collection model; provider thứ hai hỗ trợ namespace và compact URI relation trong HAL.

## Dùng LinkRelation trong Spring HATEOAS

`LinkRelation` biểu diễn relation theo kiểu dữ liệu thay vì phải truyền chuỗi ở mọi nơi. Với extension relation, tạo relation từ URI tuyệt đối:

```java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    public static final LinkRelation APPROVE = LinkRelation.of(
            "https://api.example.com/rels/approve");

    public static final LinkRelation REFUND = LinkRelation.of(
            "https://api.example.com/rels/refund");

    private ApiRelations() {
    }
}
```

Assembler có thể gắn relation đó vào link được tạo từ controller mapping:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
class OrderAssembler {

    EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(order.getId(), order.getStatus().name());

        EntityModel<OrderDto> model = EntityModel.of(dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel());

        if (order.canBeApproved()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .approve(order.getId(), null))
                    .withRel(ApiRelations.APPROVE));
        }

        return model;
    }
}
```

`withRel(ApiRelations.APPROVE)` gắn extension relation vào link. Khi serialize, HAL converter sẽ ghi relation vào `_links`; nếu có CURIE provider tương ứng, relation URI có thể được rút gọn. `methodOn(...)` mô tả mapping để xây URI, không gọi endpoint approve.

Điều kiện `canBeApproved()` chỉ là ví dụ domain. Trong ứng dụng thực tế, khả năng được công bố có thể phụ thuộc trạng thái đơn hàng, vai trò người dùng, policy hoặc dữ liệu đã tải. Dù link không xuất hiện, endpoint vẫn phải kiểm tra quyền và trạng thái khi nhận request.

## Dùng CURIE để rút gọn custom relation trong HAL

HAL cho phép công bố CURIE (Compact URI) để rút gọn extension relation URI. Ví dụ, URI relation đầy đủ:

```text
https://api.example.com/rels/approve
```

có thể được biểu diễn trong `_links` bằng `ex:approve` nếu response khai báo CURIE `ex`:

```json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "ex:approve": {
      "href": "https://shop.example/api/orders/o-42/approval"
    }
  }
}
```

CURIE `ex` là prefix được định nghĩa trong response. Client có thể mở rộng `ex:approve` theo template để nhận URI relation đầy đủ. CURIE chỉ rút gọn tên relation; nó không thay đổi target `href` của link.

Trong Spring HATEOAS, có thể cấu hình `CurieProvider` để HAL serializer tạo CURIE:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "ex",
                UriTemplate.of("https://api.example.com/rels/{rel}"));
    }
}
```

Với cấu hình này, custom relation có URI khớp template có thể được serialize dưới dạng CURIE. Cần kiểm tra output của phiên bản Spring HATEOAS đang dùng, nhất là khi ứng dụng có nhiều namespace hoặc custom HAL configuration. Chọn prefix ngắn, ổn định và không trùng với prefix khác trong cùng representation.

Không dùng CURIE để che một relation không có semantics rõ ràng. Prefix chỉ là cách trình bày gọn; định danh đầy đủ và tài liệu của relation vẫn cần ổn định.

## Custom relation cho hành động và affordance

Relation cho biết link đại diện cho khả năng nào. Affordance bổ sung metadata về thao tác mà client có thể thực hiện, chẳng hạn HTTP method, input type và template. Hai cơ chế bổ trợ nhau.

Ví dụ link `approve` có thể được gắn affordance mô tả request body:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.Link;

Link approveLink = linkTo(methodOn(OrderController.class)
        .approve(order.getId(), null))
        .withRel(ApiRelations.APPROVE);

Link linkWithAffordance = Affordances.of(approveLink)
        .afford(afford(methodOn(OrderController.class)
                .approve(order.getId(), null))
                .withInput(ApprovalRequest.class))
        .toLink();
```

Đây là mẫu minh họa việc gắn affordance vào link có custom relation. Controller cần có method `approve(...)` tương ứng; `ApprovalRequest` là DTO đầu vào do ứng dụng định nghĩa. Khi serialize với định dạng hỗ trợ affordance như HAL-FORMS, client có thể nhận metadata thao tác. Khi chỉ serialize HAL JSON, link relation vẫn cho biết ngữ nghĩa điều hướng/hành động nhưng không tự mô tả toàn bộ form input.

Nếu một thao tác cần tên template riêng, dùng tên template trong affordance theo hợp đồng HAL-FORMS. Tên template và relation link là hai định danh khác nhau: relation trả lời link có nghĩa gì; template name giúp client chọn một mẫu request trong `_templates`.

## Custom relation không phải endpoint contract đầy đủ

Chỉ công bố `ex:approve` chưa đủ để client biết mọi chi tiết gửi request nếu response không kèm affordance hoặc tài liệu tương ứng. Relation nên giúp client nhận ra hành động; URI target cho biết nơi gửi request; affordance hoặc tài liệu mô tả method, content type và input.

| Thành phần | Câu hỏi được trả lời |
| --- | --- |
| Relation URI | Link này có ý nghĩa gì? |
| `href` | Client truy cập target ở đâu? |
| HTTP method | Client dùng thao tác HTTP nào? |
| Request media type | Body được gửi theo định dạng nào? |
| Input schema/affordance | Client cần gửi những trường nào? |
| Authorization và validation | Server có chấp nhận request trong trạng thái hiện tại không? |

Không suy ra HTTP method chỉ từ tên relation. Ví dụ, `approve` không mặc định có nghĩa `POST`; API phải công bố method qua affordance/HAL-FORMS hoặc tài liệu hợp đồng. Tương tự, sự hiện diện của link không đảm bảo request chắc chắn thành công vì trạng thái và quyền có thể thay đổi sau khi representation được tạo.

## Quản lý custom relation như hợp đồng công khai

Một khi client sử dụng relation, tên và semantics của nó trở thành một phần hợp đồng. Hãy quản lý relation như một API identifier:

- Dùng một namespace URI do tổ chức kiểm soát, không dùng domain cá nhân hoặc host theo môi trường.
- Giữ URI relation ổn định qua thay đổi route, controller, service và database.
- Duy trì trang tài liệu cho mỗi relation URI; mô tả semantics và điều kiện xuất hiện.
- Không tái sử dụng một relation URI cho hành động có ý nghĩa khác.
- Chỉ tạo relation mới khi semantics mới thực sự khác; không tạo alias tùy tiện cho cùng một hành động.
- Có chính sách tương thích khi ngừng công bố relation cũ; cân nhắc thời gian chuyển tiếp nếu client đã phụ thuộc.
- Dùng CURIE nhất quán để tránh nhiều cách viết cho cùng một relation URI.

Ví dụ, nếu quy trình phê duyệt được tách thành hai giai đoạn khác nhau, không nên âm thầm đổi nghĩa `.../rels/approve` từ “phê duyệt cuối cùng” thành “gửi yêu cầu phê duyệt”. Có thể định nghĩa relation riêng `.../rels/request-approval` để client phân biệt hai khả năng.

## Khi không nên tạo custom relation

Tránh custom relation trong các trường hợp sau:

- IANA đã có relation phù hợp với cùng semantics.
- Tên chỉ lặp lại cấu trúc URL, ví dụ `orderDetail` cho link self của order.
- Tên chỉ phản ánh HTTP method, ví dụ `postOrder` hoặc `deleteItem`.
- Tên gắn với class, bảng hoặc service nội bộ, ví dụ `orderJpaEntity`.
- Relation không có định nghĩa rõ hoặc không có client nào cần phân biệt.
- Một relation chuẩn đã mô tả đúng quan hệ nhưng nhóm phát triển muốn tên riêng theo sở thích.

Nếu chỉ cần phân biệt embedded item và collection, dùng `@Relation`/`LinkRelationProvider` theo mục đích đó. Nếu cần mô tả link điều hướng domain, dùng `LinkRelation` và relation URI. Nếu cần mô tả form/action input, bổ sung affordance và HAL-FORMS. Chọn đúng cơ chế giúp hợp đồng dễ hiểu và tránh trộn lẫn các tầng semantics.

## Kiểm thử custom relation

Kiểm thử nên xác nhận relation được serialize đúng, CURIE mở rộng đúng URI và link chỉ xuất hiện khi hành động khả dụng. Ví dụ với MockMvc:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
class CustomRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesApproveRelationForApprovableOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.curies[0].name").value("ex"))
                .andExpect(jsonPath("$._links['ex:approve'].href").exists());
    }

    @Test
    void omitsApproveRelationWhenOrderCannotBeApproved() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-43")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['ex:approve']").doesNotExist());
    }
}
```

Fixture cần có `o-42` ở trạng thái có thể phê duyệt và `o-43` ở trạng thái không thể phê duyệt. Test trên giả định HAL CURIE `ex` đã được cấu hình. Nếu serializer giữ URI relation đầy đủ thay vì CURIE, hãy kiểm tra key tương ứng với cấu hình thực tế.

Nên bổ sung kiểm thử:

- URI relation mở rộng đúng namespace đã công bố.
- `href` dẫn đến endpoint có thể truy cập và endpoint trả đúng representation.
- Affordance/template có method và input phù hợp với hành động.
- Người dùng không có quyền không nhận link nhạy cảm; endpoint vẫn từ chối request trái quyền.
- Relation giữ nguyên khi route thay đổi.
- Không có hai relation URI khác nhau nhưng cùng được dùng cho một semantics ngoài chủ ý.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng token tùy ý cho extension relation công khai | Client không có định danh toàn cục và semantics dễ xung đột. | Dùng URI relation tuyệt đối theo RFC 8288. |
| Tạo custom relation trùng nghĩa IANA | Client phải xử lý nhiều tên cho cùng một khái niệm. | Tra registry trước và dùng relation chuẩn khi phù hợp. |
| Dùng URI endpoint làm relation | Relation thay đổi theo route hoặc môi trường. | Dùng URI namespace riêng cho semantics; `href` mới là endpoint. |
| Nhầm `@Relation` với custom link relation | Tên `_embedded` bị dùng thay cho relation trong `_links`. | Dùng `LinkRelation` cho link; `@Relation` cho item/collection representation. |
| Nghĩ CURIE tạo semantics mới | Prefix chỉ rút gọn URI, không định nghĩa hành vi. | Duy trì URI relation và tài liệu gốc ổn định. |
| Cho rằng link đồng nghĩa request được phép | Client có thể thử thao tác trong trạng thái đã thay đổi. | Endpoint luôn kiểm tra authorization và business state. |
| Chỉ đặt tên relation mà không mô tả input | Client không biết cách gửi hành động. | Bổ sung affordance/HAL-FORMS hoặc tài liệu API. |

## Nguyên tắc thiết kế

- Ưu tiên relation IANA nếu semantics đã phù hợp.
- Chỉ tạo custom relation khi API có ý nghĩa domain hoặc khả năng riêng cần client nhận biết.
- Dùng URI tuyệt đối ổn định làm extension relation theo RFC 8288.
- Giữ relation độc lập với route, HTTP method và tên class nội bộ.
- Dùng `LinkRelation.of(...)` và `withRel(...)` để gắn relation trong Spring HATEOAS.
- Dùng CURIE/`CurieProvider` để rút gọn URI relation khi serialize HAL.
- Phân biệt custom link relation với `@Relation`, `LinkRelationProvider` và template name.
- Bổ sung affordance/HAL-FORMS khi client cần biết method và input.
- Tài liệu hóa semantics, điều kiện xuất hiện, quyền và chính sách tiến hóa.
- Kiểm thử relation, href, CURIE và hành vi endpoint.

Custom relation cần thiết khi một API muốn công bố một khái niệm hoặc hành động riêng mà relation chuẩn không diễn đạt đúng. Khi định danh bằng URI ổn định, dùng `LinkRelation` để gắn vào link và CURIE để trình bày gọn trong HAL, Spring HATEOAS cho phép client khám phá khả năng theo semantics nghiệp vụ mà không phụ thuộc vào đường dẫn hay cấu trúc triển khai nội bộ.
