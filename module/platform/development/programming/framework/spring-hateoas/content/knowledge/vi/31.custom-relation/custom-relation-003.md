# Relation dạng URI

Trong Spring HATEOAS, link relation cho biết tài nguyên đích có ý nghĩa gì đối với tài nguyên hiện tại. IANA cung cấp một tập relation đã đăng ký như `self`, `next`, `collection` và `profile`. Khi API cần một quan hệ riêng của miền nghiệp vụ mà chưa có relation IANA phù hợp, có thể dùng extension relation type dưới dạng URI tuyệt đối.

Ví dụ, representation của đơn hàng có thể công bố một link tới quy trình phê duyệt. Relation `https://api.example.com/rels/approval` định danh ý nghĩa của quan hệ đó; `href` của link mới là URI endpoint để client gọi. Hai URI này có vai trò khác nhau: relation URI mô tả mối quan hệ, còn `href` xác định đích điều hướng.

Spring HATEOAS biểu diễn relation bằng `LinkRelation`. Có thể tạo relation URI bằng `LinkRelation.of(...)`, sau đó gắn nó vào `Link` hoặc `RepresentationModel`. Khi dùng HAL, relation URI có thể được serialize đầy đủ hoặc rút gọn bằng CURIE để response dễ đọc hơn.

## Registered relation và extension relation

RFC 8288 phân biệt hai loại link relation:

| Loại | Cách định danh | Khi nên dùng |
|---|---|---|
| Registered relation | Tên token đã đăng ký trong IANA Link Relation Registry, ví dụ `self`, `next`, `first` | Quan hệ phổ biến, có ngữ nghĩa dùng chung giữa nhiều ứng dụng |
| Extension relation | URI tuyệt đối định danh duy nhất quan hệ, ví dụ `https://api.example.com/rels/approval` | Quan hệ riêng của miền nghiệp vụ hoặc giao thức của một ứng dụng |

Nếu relation IANA hiện có đã diễn đạt đúng ý nghĩa, hãy dùng relation chuẩn đó. Không tạo một URI riêng chỉ để viết lại relation chuẩn, vì các ứng dụng khác sẽ không xem hai giá trị đó là cùng một relation. Ví dụ, `https://api.example.com/rels/next` không tương đương với relation chuẩn `next`.

Extension relation phù hợp khi ý nghĩa quá chuyên biệt để đăng ký thành một relation dùng chung. Ví dụ:

- `https://api.example.com/rels/approval`: link tới tài nguyên hoặc quy trình phê duyệt liên quan tới đơn hàng.
- `https://api.example.com/rels/approver`: link tới người hoặc nhóm chịu trách nhiệm phê duyệt.
- `https://api.example.com/rels/invoice`: link tới hóa đơn của giao dịch hiện tại.
- `https://api.example.com/rels/retry-payment`: link tới endpoint cho phép thử lại thanh toán.

Tên relation cần mô tả rõ quan hệ giữa tài nguyên nguồn và đích. Đừng chọn tên chỉ vì nó trùng với tên method hoặc URL của controller; một relation tốt mô tả ý nghĩa ổn định mà client cần hiểu.

## Vì sao extension relation phải là URI?

Tên relation ngắn như `approval` có thể có ý nghĩa khác nhau trong hai hệ thống. Một client dùng `approval` trong API quản lý đơn hàng có thể hiểu khác với client dùng cùng tên trong API quản lý tài liệu. URI tạo không gian tên toàn cục, giúp tránh va chạm giữa các ứng dụng.

RFC 8288 quy định extension relation type là URI. Với HTTP Link header, extension relation phải là URI tuyệt đối. Do đó, nên dùng URI tuyệt đối ngay từ đầu để giữ khả năng tương thích giữa các cách serialize link.

Ví dụ:

```text
https://api.example.com/rels/approval
https://api.example.com/rels/approver
https://api.example.com/rels/retry-payment
```

Các giá trị trên là URI nhận diện relation. Chúng không phải URL endpoint của hành động. Endpoint đích được cung cấp riêng trong `href`:

```json
{
  "_links": {
    "https://api.example.com/rels/approval": {
      "href": "/api/orders/ORD-2048/approval"
    }
  }
}
```

Ở đây:

- Key trong `_links` là relation URI, nghĩa là “quan hệ phê duyệt của đơn hàng”.
- `href` là đường dẫn endpoint mà client có thể theo để truy cập quy trình phê duyệt.

Không dùng URI relation làm `href` chỉ vì hai giá trị đều có dạng URI. Chúng trả lời hai câu hỏi khác nhau: “liên kết này có ý nghĩa gì?” và “tôi phải đi tới đâu?”.

## Chọn URI relation bền vững

URI relation là định danh công khai trong hợp đồng API. Khi client đã dựa vào nó, việc đổi URI có thể làm client không còn nhận ra quan hệ. Vì vậy, hãy thiết kế URI theo các nguyên tắc sau:

1. **Dùng domain do tổ chức kiểm soát.** Chọn hostname mà tổ chức có thể duy trì lâu dài hoặc được ủy quyền rõ ràng.
2. **Dùng HTTPS và chữ thường.** RFC 8288 khuyến nghị URI extension viết chữ thường để so sánh dễ nhất quán.
3. **Giữ URI ổn định.** Không đưa hostname môi trường dev, port cục bộ, tên pod, ID người dùng hoặc phiên bản triển khai tạm thời vào relation.
4. **Định nghĩa ngữ nghĩa một lần và giữ nhất quán.** Không tái sử dụng URI cũ cho một ý nghĩa khác.
5. **Tách relation khỏi endpoint.** Có thể đổi đường dẫn endpoint trong `href` mà không cần đổi relation URI nếu ý nghĩa quan hệ vẫn giữ nguyên.
6. **Cân nhắc cung cấp tài liệu tại URI.** URI có thể trỏ tới trang mô tả relation để con người tra cứu, nhưng client không nên tự động dereference mỗi relation URI trong lúc xử lý response.

Một quy ước dễ quản lý là đặt relation dưới một namespace riêng:

```text
https://api.example.com/rels/{relation-name}
```

Ví dụ, `https://api.example.com/rels/approval`. Khi thiết kế cần phân biệt giữa link tới một tài nguyên phê duyệt (`approval`) và link thực hiện thao tác phê duyệt (`approve`). Tên phải diễn đạt đúng target: tài nguyên quy trình, người phê duyệt hay endpoint hành động.

### URI relation có cần truy cập được không?

RFC 8288 cho phép extension relation URI trỏ tới tài nguyên chứa định nghĩa ngữ nghĩa. Tuy nhiên, client không nên tự động truy cập URI đó chỉ để xử lý link; hành vi này có thể tạo nhiều request không cần thiết và gây tải cho máy chủ tài liệu.

Việc cung cấp tài liệu tại URI vẫn hữu ích cho nhà phát triển, người vận hành và các công cụ kiểm tra hợp đồng. Trang tài liệu nên giải thích:

- Tài nguyên nguồn nào thường công bố relation.
- Tài nguyên đích đại diện cho điều gì.
- Khi nào relation xuất hiện hoặc bị lược bỏ.
- Client có thể mong đợi những thao tác hoặc trạng thái nào ở đích.
- Các thay đổi ngữ nghĩa và chính sách tương thích.

Nếu URI không được dereference, nó vẫn có thể là định danh hợp lệ miễn là URI tuyệt đối, duy nhất và được kiểm soát. Dù vậy, một URL tài liệu có thể truy cập lâu dài thường giúp con người khám phá hợp đồng dễ hơn.

## Tạo custom relation bằng LinkRelation

Spring HATEOAS cung cấp `LinkRelation` để biểu diễn relation dưới dạng kiểu giá trị thay vì truyền chuỗi rời rạc ở nhiều nơi.

```java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    private ApiRelations() {}

    public static final LinkRelation APPROVAL =
            LinkRelation.of("https://api.example.com/rels/approval");

    public static final LinkRelation APPROVER =
            LinkRelation.of("https://api.example.com/rels/approver");

    public static final LinkRelation RETRY_PAYMENT =
            LinkRelation.of("https://api.example.com/rels/retry-payment");
}
```

Đặt các relation dùng chung ở một nơi giúp tránh lỗi chính tả và giữ nguyên định danh khi nhiều assembler hoặc controller cùng tạo link. Các hằng này không thay thế tài liệu hợp đồng; chúng chỉ giúp code sử dụng cùng một giá trị.

Tạo link với relation URI:

```java
import org.springframework.hateoas.Link;

Link approvalLink = Link.of(
        "/api/orders/ORD-2048/approval",
        ApiRelations.APPROVAL
);
```

Hoặc thêm relation vào link đã tạo:

```java
Link approvalLink = Link.of("/api/orders/ORD-2048/approval")
        .withRel(ApiRelations.APPROVAL);
```

`Link.of(href)` mặc định dùng relation `self`, vì vậy khi link trỏ tới tài nguyên liên quan, hãy chỉ định relation tường minh. `withRel(...)` trả về một `Link` mới vì `Link` là kiểu immutable.

## Tạo link từ controller mapping

Khi `href` trỏ tới endpoint Spring MVC, nên dùng `WebMvcLinkBuilder` để lấy URI từ mapping controller. Relation URI vẫn được khai báo riêng:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler {

    public EntityModel<OrderResponse> toModel(Order order) {
        UUID id = order.getId();

        Link self = linkTo(methodOn(OrderController.class).one(id))
                .withSelfRel();

        Link approval = linkTo(methodOn(OrderController.class).approval(id))
                .withRel(ApiRelations.APPROVAL);

        return EntityModel.of(
                new OrderResponse(id, order.getStatus().name()),
                self,
                approval
        );
    }
}
```

Controller có thể khai báo endpoint đích như sau:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        // Đọc đơn hàng và tạo representation.
    }

    @GetMapping("/{id}/approval")
    public EntityModel<ApprovalResponse> approval(@PathVariable UUID id) {
        // Trả trạng thái và thông tin quy trình phê duyệt.
    }
}
```

`methodOn(...)` cung cấp mapping để tạo `href`; `ApiRelations.APPROVAL` cung cấp ngữ nghĩa relation. Khi đổi mapping từ `/api/orders/{id}/approval` sang đường dẫn khác, Spring HATEOAS cập nhật `href` theo controller trong khi relation URI vẫn giữ nguyên.

Nếu link chỉ xuất hiện khi đơn hàng có thể phê duyệt, hãy thêm link theo capability hoặc trạng thái nghiệp vụ:

```java
if (order.canBeApproved()) {
    model.add(linkTo(methodOn(OrderController.class)
            .approval(order.getId()))
            .withRel(ApiRelations.APPROVAL));
}
```

Sự vắng mặt của link chỉ mô tả khả năng server đang công bố trong representation. Endpoint đích vẫn phải xác thực, phân quyền và kiểm tra trạng thái khi nhận request.

## Custom relation trong HAL

HAL sử dụng relation làm tên khóa bên trong `_links`. Nếu không cấu hình CURIE, relation URI có thể được serialize đầy đủ:

```json
{
  "id": "ORD-2048",
  "_links": {
    "self": {
      "href": "/api/orders/ORD-2048"
    },
    "https://api.example.com/rels/approval": {
      "href": "/api/orders/ORD-2048/approval"
    }
  }
}
```

Client có thể tìm đúng khóa relation URI đã thỏa thuận và đọc `href`. Cách này thể hiện định danh đầy đủ, nhưng khóa JSON dài có thể làm response khó đọc và khó thao tác trong client.

HAL cho phép dùng CURIE (Compact URI) để rút gọn extension relation. CURIE không tạo một relation mới; nó là cách serialize ngắn của URI relation gốc. Ví dụ:

```text
acme:approval
```

có thể đại diện cho:

```text
https://api.example.com/rels/approval
```

Khi dùng CURIE, response phải công bố định nghĩa prefix trong scope thông qua relation `curies`. Client có thể mở rộng CURIE dựa trên URI template được cung cấp.

## Cấu hình CurieProvider

Spring HATEOAS cung cấp `CurieProvider` và `DefaultCurieProvider` để rút gọn extension relation trong HAL. Khai báo một bean như sau:

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
public class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
```

`DefaultCurieProvider` nhận prefix `acme` và URI template có đúng một biến `{rel}`. Với extension relation URI thuộc namespace đó, Spring HATEOAS có thể serialize relation dưới dạng `acme:approval` và tự thêm link `curies` vào HAL document.

Trong ứng dụng Spring Boot đã bật hypermedia auto-configuration, hãy kiểm tra cấu hình hiện có trước khi thêm `@EnableHypermediaSupport` lần nữa. Mục tiêu là đăng ký `CurieProvider` trong application context; không tạo nhiều bean CurieProvider cạnh tranh. Spring HATEOAS hỗ trợ một CurieProvider trong mỗi application scope.

Response HAL sau khi cấu hình có thể trông như sau:

```json
{
  "id": "ORD-2048",
  "_links": {
    "self": {
      "href": "/api/orders/ORD-2048"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approval": {
      "href": "/api/orders/ORD-2048/approval"
    }
  }
}
```

Prefix `acme` giúp response gọn hơn. Link `curies` giải thích cách mở rộng relation rút gọn. Nếu client không biết prefix, nó có thể đọc `name` và `href` của CURIE để xác định URI đầy đủ theo template.

## CURIE và URI relation đầy đủ

Khi xử lý relation trong HAL, client cần hiểu rằng `acme:approval` là dạng compact của URI, không phải một chuỗi nghiệp vụ hoàn toàn độc lập. Hãy dùng `curies` để mở rộng khi cần so sánh hoặc lưu trữ relation dưới dạng đầy đủ.

| Dạng | Ví dụ | Vai trò |
|---|---|---|
| URI relation đầy đủ | `https://api.example.com/rels/approval` | Định danh chuẩn của extension relation |
| CURIE | `acme:approval` | Dạng rút gọn khi serialize trong HAL |
| Link target | `/api/orders/ORD-2048/approval` | URI mà client gọi để truy cập tài nguyên đích |

Không nhầm CURIE với `href`. CURIE rút gọn relation; nó không rút gọn hoặc thay thế URI đích. Ngoài ra, CURIE là cơ chế của định dạng HAL; các media type khác có thể serialize extension relation theo cách khác.

## Khi nào nên dùng custom relation dạng URI?

Dùng extension relation khi quan hệ có ngữ nghĩa đặc thù của domain và chưa có relation chuẩn phù hợp. Ví dụ, một đơn hàng có thể liên kết tới “đề nghị hoàn tiền”, “kết quả đối soát” hoặc “quy trình phê duyệt”. Đây là những khái niệm riêng của API bán hàng và không nhất thiết phù hợp với một relation dùng chung toàn Internet.

Không nên tạo custom relation cho mọi link. Các quan hệ phổ biến như `self`, `next`, `prev`, `first`, `last`, `collection`, `item`, `profile` nên sử dụng relation IANA khi đúng ngữ nghĩa. Việc dùng relation chuẩn giúp client tổng quát có thể nhận diện các quan hệ thông dụng.

Một custom relation cũng không nhất thiết cần một endpoint mới. Nó định danh ý nghĩa của một link; target có thể là endpoint đã có hoặc một tài nguyên khác. Ngược lại, nhiều link có thể dùng cùng relation nếu chúng biểu diễn cùng một loại quan hệ tới nhiều target.

## Kiểm thử custom relation

Kiểm thử cần xác nhận relation đúng, `href` đúng và cách serialize HAL phù hợp với chính sách CURIE của ứng dụng.

### Unit test cho model

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;

class OrderRelationTest {

    @Test
    void addsApprovalRelation() {
        EntityModel<OrderResponse> model = new OrderModelAssembler()
                .toModel(OrderFixtures.pendingOrder());

        assertTrue(model.hasLink(ApiRelations.APPROVAL));
        assertEquals(
                "/api/orders/ORD-2048/approval",
                model.getRequiredLink(ApiRelations.APPROVAL).getHref()
        );
    }
}
```

Factory `OrderFixtures.pendingOrder()` đại diện cho dữ liệu test của ứng dụng. Nếu link phụ thuộc trạng thái, thêm test cho đơn hàng không thể phê duyệt để xác nhận relation không xuất hiện.

### Integration test với HAL và CURIE

Khi `CurieProvider` được cấu hình, test HTTP xác nhận prefix và target:

```java
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
class CustomRelationHalTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void serializesCustomRelationAsCurie() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-2048")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.curies.name").value("acme"))
            .andExpect(jsonPath("$._links.curies.templated").value(true))
            .andExpect(jsonPath("$._links['acme:approval'].href")
                    .value("/api/orders/ORD-2048/approval"));
    }
}
```

Nếu không cấu hình CURIE, test nên tìm key bằng URI relation đầy đủ thay vì `acme:approval`. Nếu API thay đổi prefix CURIE, đó là thay đổi serialization cần kiểm tra cùng client; URI relation gốc vẫn phải giữ nguyên.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng chuỗi ngắn `approval` làm extension relation | Có thể không tuân thủ yêu cầu URI và dễ va chạm | Dùng URI tuyệt đối do tổ chức kiểm soát |
| Tạo URI relation riêng cho một relation IANA đã có | Client không xem đó là relation chuẩn | Dùng `IanaLinkRelations` khi ngữ nghĩa đã phù hợp |
| Dùng relation URI làm `href` | Client đi tới URI định nghĩa thay vì endpoint đích | Tách relation và link target |
| Đưa hostname dev hoặc port vào relation | Relation thay đổi giữa các môi trường | Dùng namespace URI ổn định |
| Thay đổi ý nghĩa của URI cũ | Client cũ hiểu sai quan hệ | Giữ ngữ nghĩa hoặc tạo relation URI mới |
| Nghĩ client phải GET URI relation | Phát sinh request không cần thiết | Cung cấp tài liệu cho người phát triển; client không tự động dereference |
| Dùng CURIE mà không công bố `curies` | Client không thể mở rộng relation rút gọn | Cấu hình `CurieProvider` để HAL thêm link định nghĩa prefix |
| Truyền `acme:approval` như relation gốc trong code | Phụ thuộc cách serialize của HAL | Lưu URI relation đầy đủ trong `LinkRelation` |
| Tạo nhiều CurieProvider trong cùng scope | Cấu hình relation prefix không rõ ràng | Dùng một CurieProvider nhất quán cho application scope |

## Quy trình thiết kế và triển khai

1. Tìm relation IANA phù hợp trước khi tạo relation riêng.
2. Nếu không có relation phù hợp, định nghĩa extension relation bằng URI tuyệt đối.
3. Chọn namespace thuộc quyền kiểm soát của tổ chức và giữ URI ổn định, viết chữ thường.
4. Viết rõ ngữ nghĩa relation, tài nguyên nguồn, tài nguyên đích và điều kiện công bố.
5. Khai báo `LinkRelation` dùng chung trong code.
6. Tạo `Link` bằng relation URI đầy đủ và `href` trỏ tới endpoint/tài nguyên đích.
7. Nếu dùng HAL và muốn relation ngắn gọn, cấu hình `CurieProvider` và kiểm tra link `curies`.
8. Kiểm thử relation, `href`, điều kiện xuất hiện và dạng CURIE/URI trong response.
9. Giữ tài liệu relation cùng vòng đời và chính sách tương thích của API.

## Kết luận

Relation dạng URI cho phép Spring HATEOAS công bố các quan hệ hypermedia riêng của miền nghiệp vụ mà không xung đột với tên relation của ứng dụng khác. Theo RFC 8288, extension relation được định danh bằng URI; URI nên tuyệt đối, duy nhất, ổn định và thuộc quyền kiểm soát của bên định nghĩa. Trong code, `LinkRelation.of(...)` giữ relation URI đầy đủ, còn `Link` chứa `href` riêng để điều hướng tới target. Với HAL, `CurieProvider` và `DefaultCurieProvider` có thể rút gọn URI thành CURIE và tự công bố cách mở rộng prefix. Khi tách rõ relation khỏi target, ưu tiên relation IANA khi phù hợp và kiểm thử serialization, API có thể mở rộng vocabulary mà vẫn giữ hợp đồng dễ khám phá.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking, Section 2.1](https://www.rfc-editor.org/rfc/rfc8288.html#section-2.1): registered relation types và extension relation types.
- [IANA Link Relation Registry](https://www.iana.org/assignments/link-relations/): danh sách relation đã đăng ký.
- [Spring HATEOAS Reference – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations): `LinkRelation` và relation chuẩn IANA.
- [Spring HATEOAS Reference – CurieProvider](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie-provider): cấu hình CURIE trong HAL.
- [DefaultCurieProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html): cấu hình prefix và URI template.
