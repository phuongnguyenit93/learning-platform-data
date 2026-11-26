# Tài liệu custom relation

Một API xử lý đơn hàng có thể cung cấp liên kết để phê duyệt đơn, yêu cầu hoàn tiền hoặc mở hồ sơ kiểm tra. Những quan hệ này mang ý nghĩa riêng của nghiệp vụ nên không phải lúc nào cũng có relation chuẩn trong IANA Link Relations Registry. Khi đó, API cần định nghĩa custom link relation và tài liệu hóa ý nghĩa của nó để client biết link context liên hệ với target như thế nào.

Một custom relation tốt có định danh ổn định, mô tả rõ hướng context–target, điều kiện xuất hiện và cách sử dụng target. Spring HATEOAS biểu diễn relation bằng `LinkRelation`; với HAL, ứng dụng có thể dùng CURIE để rút gọn extension relation URI trong `_links`. Tài liệu relation là hợp đồng ngữ nghĩa cho client và đội phát triển, không chỉ là ghi chú trong code.

## Custom relation là gì?

Link relation mô tả mối quan hệ giữa resource đang chứa link (*context*) và resource mà link trỏ đến (*target*). Ví dụ, representation của đơn hàng có thể chứa link `approve` đến endpoint phê duyệt đơn hàng.

```text
Order resource (context)
       |
       | rel = custom approve relation
       v
Approval endpoint (target)
```

Custom relation là relation do ứng dụng hoặc tổ chức định nghĩa để diễn đạt ngữ nghĩa chưa được một relation chuẩn đáp ứng. Ví dụ:

- `approve`: target cho phép bắt đầu quy trình phê duyệt đơn hàng.
- `request-refund`: target dùng để yêu cầu hoàn tiền.
- `risk-assessment`: target cung cấp kết quả đánh giá rủi ro cho hồ sơ hiện tại.
- `shipment-label`: target cung cấp nhãn vận chuyển gắn với lô hàng.

Relation không phải URI của target. Relation trả lời câu hỏi “target có ý nghĩa gì đối với context?”; `href` mới là URI để client điều hướng đến target.

## Khi nào cần custom relation?

Trước khi tạo relation riêng, hãy tìm trong IANA registry xem relation chuẩn có diễn đạt đúng ngữ nghĩa hay không. Nếu đã có relation phù hợp, nên tái sử dụng relation chuẩn để client có thể hiểu mà không cần một định nghĩa riêng của ứng dụng.

Custom relation phù hợp khi:

- Quan hệ mang ý nghĩa nghiệp vụ đặc thù của sản phẩm hoặc tổ chức.
- Không có IANA relation nào diễn đạt chính xác quan hệ context–target.
- Client cần phân biệt target này với các resource liên quan khác.
- API muốn công bố một capability hoặc quan hệ chuyên biệt qua hypermedia.

Không tạo custom relation chỉ để đổi tên một relation chuẩn. Ví dụ, nếu target thật sự là tài liệu trợ giúp của context, dùng `help`; nếu target là collection chứa resource hiện tại, cân nhắc `collection`. Relation riêng chỉ nên xuất hiện khi có ý nghĩa riêng cần được duy trì.

## Chọn định danh cho custom relation

RFC 8288 phân biệt registered relation type và extension relation type. Registered relation dùng token đã đăng ký trong IANA. Extension relation dùng URI xác định duy nhất ngữ nghĩa của relation.

Ví dụ extension relation URI:

```text
https://api.example.com/rels/approve
https://api.example.com/rels/request-refund
https://api.example.com/rels/risk-assessment
```

Nên dùng URI thuộc quyền kiểm soát của tổ chức định nghĩa relation. Dùng URI chữ thường và giữ nguyên định danh trong suốt vòng đời relation. URI có thể trỏ đến trang tài liệu giải thích semantics, nhưng client không nên tự động truy cập URI relation mỗi khi gặp link; URI này là định danh ngữ nghĩa, không phải endpoint nghiệp vụ.

Không dùng URL target thay cho relation URI. Ví dụ:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Relation URI | `https://api.example.com/rels/approve` | Định danh ý nghĩa “đây là thao tác phê duyệt của đơn hàng”. |
| Target URI | `/api/orders/ord-1042/approval` | Endpoint mà client có thể điều hướng đến. |

Hai URI có vòng đời khác nhau. Target URI có thể thay đổi theo từng đơn hàng hoặc phiên bản route; relation URI nên ổn định để client tiếp tục nhận diện cùng một ngữ nghĩa.

### Token ngắn và extension URI

Một số định dạng hoặc API nội bộ chấp nhận relation token ngắn như `approve`. Cách này dễ đọc nhưng có nguy cơ trùng tên và không tự cung cấp định danh toàn cục. Theo mô hình extension relation của RFC 8288, relation riêng nên được định danh bằng URI.

Với HAL, CURIE cho phép biểu diễn URI relation dài bằng một tên rút gọn như `acme:approve`. CURIE là dạng viết gọn có thể mở rộng về URI đầy đủ; nó không tạo ra một semantics mới và không thay thế tài liệu relation.

## Tài liệu hóa semantics của relation

Mỗi custom relation cần một định nghĩa có thể được đọc độc lập với implementation. Hãy mô tả quan hệ từ context đến target, không chỉ ghi “dùng để phê duyệt”.

Ví dụ định nghĩa relation `approve`:

| Mục | Định nghĩa |
| --- | --- |
| Relation URI | `https://api.example.com/rels/approve` |
| CURIE trong HAL | `acme:approve` |
| Context | Một resource đơn hàng. |
| Target | Endpoint bắt đầu quy trình phê duyệt đơn hàng đó. |
| Semantics | Target cho phép người dùng có quyền bắt đầu phê duyệt đơn hàng nếu trạng thái hiện tại hỗ trợ. |
| Điều kiện xuất hiện | Đơn hàng ở trạng thái `PENDING_APPROVAL` và người dùng có quyền phê duyệt. |
| HTTP method | `POST` theo hợp đồng endpoint ví dụ. |
| Request media type | `application/json` nếu target cần body; có thể không cần body nếu endpoint được thiết kế như action resource. |
| Kết quả | Trả representation của trạng thái phê duyệt hoặc resource tác vụ. |
| Lỗi quan trọng | `403` khi không đủ quyền, `409` khi trạng thái không còn cho phép phê duyệt. |

Đây là ví dụ hợp đồng của ứng dụng. Nếu API thực tế dùng method, body hoặc status code khác, tài liệu phải phản ánh đúng endpoint đang được công bố.

Một trang relation nên trả lời ít nhất các câu hỏi sau:

1. Relation định danh điều gì?
2. Context nào có thể chứa relation này?
3. Target đại diện cho resource hoặc capability nào?
4. Quan hệ có hướng như thế nào từ context đến target?
5. Một context có thể có một hay nhiều link cùng relation?
6. Điều kiện nào khiến link xuất hiện hoặc biến mất?
7. Target hỗ trợ method và media type nào?
8. Client cần quyền gì và có thể nhận những lỗi nào?
9. Semantics có ổn định qua các phiên bản API không?

Không suy ra thêm ý nghĩa chỉ từ việc relation xuất hiện hoặc có nhiều link cùng relation. Nếu một relation được phép xuất hiện nhiều lần, tài liệu cần nói rõ các target khác nhau như thế nào.

## Viết định nghĩa relation theo context và target

Định nghĩa nên dùng câu chủ động và xác định rõ hai đầu liên kết.

Ví dụ chưa đủ rõ:

> `approve`: link để phê duyệt.

Ví dụ rõ hơn:

> Từ một đơn hàng đang chờ phê duyệt, relation `approve` trỏ đến endpoint cho phép người dùng có quyền bắt đầu quy trình phê duyệt đơn hàng đó. Link chỉ được công bố khi trạng thái đơn hàng cho phép thao tác. Client gửi POST đến target; server kiểm tra lại quyền và trạng thái tại thời điểm xử lý.

Định nghĩa thứ hai giúp client hiểu context, target, điều kiện và giới hạn của thao tác. Nó cũng tránh hiểu nhầm link là một lệnh đã được thực thi.

## Tạo custom relation trong Spring HATEOAS

Spring HATEOAS cung cấp `LinkRelation` để biểu diễn relation chuẩn và custom. `LinkRelation.of(String)` tạo relation từ một chuỗi. Với custom relation tuân theo extension relation URI, dùng URI đầy đủ:

```java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation APPROVE = LinkRelation.of(
        "https://api.example.com/rels/approve");

    private OrderRelations() {
    }
}
```

Tách relation thành hằng giúp tránh lặp chuỗi và giảm nguy cơ sai chính tả. Tên hằng Java là chi tiết implementation; giá trị URI mới là định danh được công bố trong hợp đồng.

Thêm link vào representation:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

EntityModel<OrderView> model = EntityModel.of(orderView);

if (order.canBeApproved() && authorization.canApprove(order)) {
    model.add(Link.of(
        "/api/orders/" + order.getId() + "/approval",
        OrderRelations.APPROVE));
}
```

Ví dụ dùng URI tương đối để minh họa. Trong ứng dụng Spring MVC, nên tạo target từ controller mapping bằng `WebMvcLinkBuilder` để tránh hard-code path:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

model.add(linkTo(methodOn(OrderApprovalController.class)
        .approve(order.getId()))
    .withRel(OrderRelations.APPROVE));
```

`methodOn(...)` ghi nhận mapping controller và tham số để xây URI. Nó không gọi method controller và không thực hiện thao tác phê duyệt. Điều kiện `canBeApproved()` và `authorization.canApprove(...)` chỉ minh họa chính sách công bố link; endpoint vẫn phải kiểm tra lại quyền và trạng thái khi nhận request.

## Dùng CURIE để rút gọn relation URI trong HAL

Nếu mọi custom relation đều được serialize bằng URI dài, HAL representation có thể khó đọc. CURIE cho phép định nghĩa một prefix và URI template để biểu diễn extension relation ngắn gọn.

Ví dụ cấu hình một `CurieProvider`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "acme",
            new UriTemplate("https://api.example.com/rels/{rel}"));
    }
}
```

Prefix `acme` đại diện cho URI template `https://api.example.com/rels/{rel}`. Khi serializer HAL áp dụng CURIE provider, relation URI `https://api.example.com/rels/approve` có thể được biểu diễn bằng `acme:approve`.

Ví dụ HAL sau khi serialize:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    },
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "acme:approve": {
      "href": "https://api.example.com/api/orders/ord-1042/approval"
    }
  }
}
```

Client mở rộng `acme:approve` theo CURIE khai báo trong `curies` để nhận diện relation URI đầy đủ. CURIE chỉ là cách biểu diễn ngắn gọn trong HAL; trong code, relation vẫn nên được tạo bằng URI đầy đủ.

Spring HATEOAS `DefaultCurieProvider` hỗ trợ một URI template và prefix; ứng dụng có thể cung cấp một bean `CurieProvider`. Theo API hiện hành, chỉ nên cấu hình một CurieProvider trong application scope. Nếu dùng nhiều namespace, cấu hình map CURIE phù hợp và kiểm thử serializer.

CURIE là tính năng của HAL. Không giả định mọi media type khác như HAL-FORMS hoặc JSON tùy chỉnh sẽ serialize relation theo cùng dạng prefix.

## Phân biệt custom link relation với @Relation

Spring HATEOAS có nhiều abstraction mang tên relation nhưng phục vụ các mục đích khác nhau.

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| `LinkRelation` | Đại diện relation của một link bất kỳ, gồm IANA hoặc custom. | `https://api.example.com/rels/approve` |
| `IanaLinkRelations` | Hằng cho relation đã đăng ký trong IANA. | `IanaLinkRelations.SELF`, `IanaLinkRelations.NEXT`. |
| `CurieProvider` | Rút gọn extension relation URI khi serialize HAL. | `acme:approve`. |
| `@Relation` | Định nghĩa relation cho item và collection khi biểu diễn embedded resource. | `itemRelation = "order"`, `collectionRelation = "orders"`. |
| `LinkRelationProvider` | Xác định item/collection relation dựa trên kiểu resource. | Từ `OrderView` suy ra relation item/collection. |

Ví dụ `@Relation`:

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(UUID id, String status) {
}
```

Annotation này giúp serializer đặt item trong `_embedded.orders`. Nó không định nghĩa action relation `approve` và không thay thế `LinkRelation` khi thêm custom link vào `_links`.

Tương tự, custom `LinkRelationProvider` được dùng khi cần tùy biến cách framework xác định relation theo loại resource. Không cần triển khai provider chỉ để thêm một link custom vào một representation; dùng `LinkRelation` và `Link` là đủ.

## Tài liệu relation nên được tổ chức thế nào?

Có thể duy trì một danh mục relation trong tài liệu API. Mỗi relation có một trang hoặc một mục riêng, được tham chiếu từ tài liệu tổng quan hypermedia.

Một bảng danh mục có thể gồm:

| Trường | Nội dung |
| --- | --- |
| Relation URI | Định danh đầy đủ và ổn định. |
| CURIE | Tên rút gọn nếu API dùng HAL CURIE. |
| Tên dễ đọc | Tên nghiệp vụ để người phát triển trao đổi. |
| Context type | Loại representation có thể phát relation. |
| Target meaning | Resource hoặc capability mà target đại diện. |
| Availability | Trạng thái/quyền cần có để link xuất hiện. |
| Method/media type | Cách tương tác với target. |
| Response/error | Kết quả và lỗi client cần xử lý. |
| Version/deprecation | Trạng thái hỗ trợ và kế hoạch ngừng dùng. |

Ví dụ danh mục:

| Relation | Context | Target | Điều kiện |
| --- | --- | --- | --- |
| `acme:approve` | Đơn hàng | Endpoint bắt đầu phê duyệt | Đơn đang chờ phê duyệt và user có quyền. |
| `acme:request-refund` | Đơn hàng đã thanh toán | Endpoint tạo yêu cầu hoàn tiền | Đơn đủ điều kiện hoàn tiền. |
| `acme:risk-assessment` | Hồ sơ giao dịch | Resource kết quả đánh giá rủi ro | Đánh giá đã được tạo và user được phép xem. |

Không để định nghĩa relation chỉ tồn tại trong comment của assembler. Client và các nhóm tích hợp cần một nguồn tài liệu ổn định, có thể tra cứu độc lập.

## Versioning và tiến hóa semantics

Relation URI nên ổn định lâu dài. Việc thay đổi route target không nhất thiết cần đổi relation URI vì relation mô tả ngữ nghĩa, không mô tả vị trí endpoint.

Nếu chỉ thay đổi cách triển khai target nhưng semantics không đổi, giữ relation URI và cập nhật tài liệu tương tác nếu cần. Nếu semantics thay đổi không tương thích, ví dụ `approve` trước đây bắt đầu một bước phê duyệt nhưng nay lại tự động chấp thuận đơn, hãy tạo relation URI mới thay vì âm thầm đổi ý nghĩa cũ.

Khi deprecate relation:

1. Đánh dấu relation cũ deprecated trong danh mục.
2. Công bố relation mới và cách chuyển đổi.
3. Có thể công bố đồng thời link cũ và mới trong giai đoạn chuyển tiếp nếu semantics cho phép.
4. Theo dõi client usage và thông báo thời điểm ngừng cung cấp.
5. Chỉ gỡ relation cũ theo chính sách versioning đã công bố.

Không tái sử dụng một relation URI đã ngừng dùng cho ý nghĩa khác. Một URI relation phải tiếp tục nhận diện cùng một semantics.

## Tài liệu relation và tài liệu API endpoint

Trang relation mô tả ngữ nghĩa liên kết; tài liệu endpoint mô tả chi tiết HTTP operation. Hai phần liên quan nhưng không thay thế nhau.

| Tài liệu relation | Tài liệu endpoint |
| --- | --- |
| Context và target có quan hệ gì? | Route cụ thể là gì? |
| Khi nào relation xuất hiện? | Request cần path/query/header/body nào? |
| Target đại diện cho capability/resource nào? | Method, media type và schema cụ thể là gì? |
| Semantics của relation có ổn định không? | Status code, response schema và lỗi nào được trả? |

OpenAPI có thể mô tả endpoint và schema request/response. Tuy nhiên, nó không thay thế việc công bố link relation trong representation runtime. Ngược lại, link relation không nhất thiết chứa đầy đủ schema và mọi quy tắc validation của endpoint. Dùng cả hai để hỗ trợ client tĩnh lẫn client hypermedia.

## Bảo mật khi công bố custom relation

Custom relation có thể mô tả capability nhạy cảm như phê duyệt, hoàn tiền hoặc khóa tài khoản. Việc link xuất hiện có thể tiết lộ resource đang ở trạng thái nào hoặc người dùng có quyền gì.

Trước khi công bố link, hãy kiểm tra:

- User hiện tại có quyền nhìn thấy capability hay không.
- Trạng thái resource có cho phép target được sử dụng không.
- Target có nằm trong tenant và phạm vi dữ liệu đúng không.
- Link có tiết lộ thông tin nhạy cảm qua URI hoặc query string không.
- Cache có thể trả link của user/tenant này cho user/tenant khác không.

Việc không công bố link không thay thế authorization ở endpoint. Client có thể tự tạo request đến target URI hoặc dùng một response cũ. Endpoint luôn phải xác thực, phân quyền và kiểm tra trạng thái khi nhận request.

## Kiểm thử custom relation

Kiểm thử nên xác nhận cả relation trong model Java và cách relation được serialize trong media type mà API công bố.

### Unit test relation

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;

LinkRelation approve = LinkRelation.of(
    "https://api.example.com/rels/approve");

EntityModel<OrderView> model = assembler.toModel(order);

assertThat(model.hasLink(approve)).isTrue();
assertThat(model.getRequiredLink(approve).getHref())
    .endsWith("/api/orders/ord-1042/approval");
```

Test này xác nhận relation và target URI trong representation model. Cần có test riêng cho trường hợp đơn hàng không đủ điều kiện để bảo đảm link không xuất hiện.

### Kiểm tra HAL với CURIE

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies[0].name").value("acme"))
    .andExpect(jsonPath("$._links['acme:approve'].href")
        .exists());
```

Test này giả định `DefaultCurieProvider` đã được đăng ký và đơn hàng đủ điều kiện phê duyệt. Nếu ứng dụng không dùng CURIE, kiểm tra key relation theo cách serialize extension URI của cấu hình HAL thực tế.

### Kiểm tra semantics và quyền

Nên kiểm tra:

- Relation URI/CURIE đúng với danh mục đã công bố.
- Target URI trỏ đến đúng resource hoặc capability.
- Link chỉ xuất hiện khi điều kiện nghiệp vụ và quyền được đáp ứng.
- Endpoint target từ chối request trực tiếp khi user không đủ quyền.
- Nhiều link cùng relation được xử lý theo cardinality đã tài liệu hóa.
- Relation mới và cũ cùng tồn tại đúng trong giai đoạn deprecation nếu có.
- HAL response có CURIE declaration và relation key nhất quán.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng chuỗi token riêng không có namespace | Dễ trùng tên và khó dùng giữa nhiều API. | Dùng extension relation URI và CURIE khi cần rút gọn trong HAL. |
| Dùng target URI làm relation | Client nhầm định danh ngữ nghĩa với endpoint cụ thể. | Tách relation URI và `href` target. |
| Chỉ ghi tên relation mà không định nghĩa context/target | Client không biết quan hệ được hiểu theo hướng nào. | Mô tả semantics từ context đến target. |
| Tài liệu hóa relation như một lệnh đã thực thi | Client có thể hiểu link là kết quả thay vì capability. | Nêu rõ link chỉ công bố target; request mới thực hiện thao tác. |
| Đổi semantics nhưng giữ relation URI | Client cũ hiểu sai hành vi. | Tạo relation URI mới khi thay đổi không tương thích. |
| Nhầm `@Relation` với custom link relation | Embedded relation và action relation bị cấu hình sai. | Dùng `@Relation` cho item/collection embedding; `LinkRelation` cho link. |
| Coi CURIE là một relation mới | Client không mở rộng được relation về URI chuẩn. | Khai báo CURIE và giữ URI đầy đủ làm định danh. |
| Dùng relation để thay thế tài liệu endpoint | Client thiếu method, schema và lỗi cụ thể. | Liên kết tài liệu relation với OpenAPI/endpoint docs. |
| Chỉ ẩn link để bảo mật | Client vẫn có thể gọi target trực tiếp. | Authorization độc lập ở endpoint. |

## Ghi nhớ

- Custom relation diễn đạt ngữ nghĩa riêng giữa link context và target.
- Ưu tiên IANA relation nếu có relation chuẩn phù hợp; nếu không, dùng extension relation URI theo RFC 8288.
- Relation URI và target URI là hai thành phần khác nhau, có vòng đời khác nhau.
- Tài liệu relation cần nêu context, target, semantics, điều kiện xuất hiện, cardinality, method/media type, quyền và lỗi.
- Dùng `LinkRelation.of(...)` để tạo custom relation trong Spring HATEOAS.
- Dùng `CurieProvider`/`DefaultCurieProvider` để rút gọn extension relation URI khi serialize HAL.
- CURIE là dạng viết gọn của URI relation, không phải một semantics khác.
- `@Relation` và `LinkRelationProvider` phục vụ embedded item/collection naming; custom link relation dùng `LinkRelation`.
- Giữ relation URI ổn định; tạo URI mới nếu semantics thay đổi không tương thích.
- Kiểm thử relation trong model, HAL serialization, target URI, điều kiện công bố và authorization.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking, Section 2.1](https://www.rfc-editor.org/rfc/rfc8288.html#section-2.1)
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [Spring HATEOAS Reference Documentation – Link Relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links)
- [Spring HATEOAS Reference Documentation – CURIEs](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS API – DefaultCurieProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html)
- [Spring HATEOAS API – CurieProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/CurieProvider.html)
