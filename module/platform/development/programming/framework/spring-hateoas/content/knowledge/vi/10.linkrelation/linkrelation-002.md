# Relation dạng chuỗi

Trong Spring HATEOAS, một liên kết (`Link`) gồm URI đích (`href`) và quan hệ liên kết (`rel`). Quan hệ cho biết tài nguyên hiện tại có mối liên hệ gì với tài nguyên đích. Spring biểu diễn giá trị quan hệ bằng kiểu `LinkRelation`, một abstraction dựa trên chuỗi. Nhờ đó, ứng dụng có thể dùng các quan hệ chuẩn như `self`, `next`, `collection` hoặc định nghĩa quan hệ riêng theo nghiệp vụ.

Bạn có thể truyền chuỗi trực tiếp vào API tạo link, ví dụ `withRel("orders")`, hoặc tạo một đối tượng `LinkRelation` bằng `LinkRelation.of("orders")`. Hai cách đều giúp gắn quan hệ vào link; dùng `LinkRelation` rõ ràng hơn khi cần truyền, so sánh hoặc tái sử dụng relation ở nhiều thành phần.

Bài học này thuộc chương **LinkRelation** của module **SPRING_HATEOAS**, tập trung vào cách dùng relation dạng chuỗi, phân biệt relation chuẩn IANA và relation mở rộng, quy tắc đặt tên, cách kiểm tra relation và cách công bố relation tùy chỉnh trong HAL.

Sau bài học, bạn có thể:

- Giải thích `LinkRelation` và vai trò của relation trong một `Link`.
- Tạo relation từ chuỗi bằng `LinkRelation.of(...)` và `LinkRelation.manyOf(...)`.
- Dùng overload nhận `String` hoặc `LinkRelation` của `Link`.
- Chọn relation chuẩn từ `IanaLinkRelations`.
- Thiết kế relation tùy chỉnh có ý nghĩa ổn định và tương thích chuẩn Web Linking.
- Dùng CURIE để biểu diễn relation URI tùy chỉnh gọn hơn trong HAL.
- Kiểm thử relation theo ngữ nghĩa thay vì dựa vào thứ tự hoặc URL cố định.

## 1. Relation mô tả mối quan hệ giữa hai tài nguyên

Một link không chỉ là địa chỉ URL. Nó mô tả một quan hệ từ tài nguyên đang được biểu diễn tới tài nguyên đích. Ví dụ, trong biểu diễn đơn hàng:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "customer": {
      "href": "https://api.example.com/customers/7"
    },
    "https://api.example.com/rels/cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  }
}
```

Các quan hệ có ý nghĩa khác nhau:

- `self`: link trỏ tới chính đơn hàng đang được biểu diễn.
- `orders`: link tới collection đơn hàng.
- `customer`: link tới khách hàng liên quan.
- `https://api.example.com/rels/cancel`: relation mở rộng định danh đích của thao tác hủy theo hợp đồng API.

`href` trả lời câu hỏi “đi tới đâu?”, còn `rel` trả lời câu hỏi “đích đó có quan hệ gì với tài nguyên hiện tại?”. Client nên tìm link theo relation, sau đó theo `href` do server cung cấp. Cách này giảm phụ thuộc vào cấu trúc URL và giúp server thay đổi đường dẫn mà không phải thay đổi cách client khám phá tài nguyên.

Relation không tự mô tả toàn bộ HTTP request. Ví dụ `cancel` cho client biết ý nghĩa liên kết, nhưng không tự nói request phải dùng `POST`, `DELETE` hay cần gửi payload nào. Nếu client cần metadata về phương thức và dữ liệu đầu vào, có thể dùng affordance hoặc media type phù hợp.

## 2. LinkRelation là kiểu biểu diễn relation dạng chuỗi

`LinkRelation` nằm trong gói `org.springframework.hateoas`. Đây là interface đại diện cho một loại quan hệ liên kết. Nó cung cấp factory method để tạo relation từ chuỗi và các phương thức để đọc hoặc so sánh giá trị.

```java
import org.springframework.hateoas.LinkRelation;

LinkRelation orders = LinkRelation.of("orders");

String relationValue = orders.value();
System.out.println(relationValue); // orders
```

`LinkRelation.of(...)` yêu cầu giá trị không null và không rỗng. Kiểu này giúp relation có tên và kiểu rõ ràng trong chữ ký phương thức, thay vì truyền một `String` không phân biệt với các chuỗi khác như URI, tên trạng thái hoặc thông báo.

`LinkRelation` là abstraction dùng trong mô hình Java; khi tuần tự hóa, serializer sẽ đưa giá trị relation vào định dạng hypermedia tương ứng. Trong HAL, tên relation thường trở thành khóa bên trong `_links`.

### Các phương thức thường dùng

| API | Vai trò |
|---|---|
| `LinkRelation.of(String)` | Tạo một relation từ chuỗi. |
| `LinkRelation.manyOf(String...)` | Tạo iterable chứa các relation từ nhiều chuỗi. |
| `value()` | Lấy chuỗi biểu diễn relation. |
| `isSameAs(LinkRelation)` | So sánh giá trị relation độc lập với implementation cụ thể. |
| `map(Function<String, String>)` | Tạo relation mới từ phép biến đổi chuỗi; relation IANA không bị biến đổi theo cách thông thường này. |

Ví dụ tạo nhiều relation:

```java
import org.springframework.hateoas.LinkRelation;

Iterable<LinkRelation> relations = LinkRelation.manyOf(
        "orders", "customer", "cancel");

for (LinkRelation relation : relations) {
    System.out.println(relation.value());
}
```

`manyOf` hữu ích khi cần truyền nhiều relation tới API nhận một tập hợp relation. Nếu chỉ tạo một link, dùng `LinkRelation.of(...)` là đủ.

## 3. Truyền chuỗi trực tiếp vào Link

Spring HATEOAS cung cấp các overload nhận `String` để tạo link nhanh:

```java
import org.springframework.hateoas.Link;

Link ordersLink = Link.of("/orders", "orders");

Link customerLink = Link.of("/customers/7")
        .withRel("customer");
```

Hai cách trên tạo link có cùng ý nghĩa: một URI đích và relation tương ứng. `Link.of(href)` không truyền relation sẽ mặc định dùng quan hệ `self`.

Nếu đã có `LinkRelation`, có thể truyền trực tiếp:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

LinkRelation relation = LinkRelation.of("customer");
Link customerLink = Link.of("/customers/7", relation);

Link sameMeaning = Link.of("/customers/7")
        .withRel(relation);
```

`Link` là kiểu immutable. Các phương thức như `withRel(...)`, `withHref(...)`, `withTitle(...)` tạo một `Link` mới với thuộc tính được cập nhật, không sửa đối tượng ban đầu. Có thể tận dụng API fluent để tạo link:

```java
Link helpLink = Link.of("/docs/orders")
        .withRel("help")
        .withTitle("Hướng dẫn đơn hàng")
        .withType("text/html");
```

## 4. Đọc và so sánh relation

Khi lấy relation từ một link, `getRel()` trả về `LinkRelation`, không phải `String`:

```java
Link link = Link.of("/orders", "orders");

LinkRelation relation = link.getRel();
String value = relation.value();
```

Nếu muốn so sánh hai relation, dùng `isSameAs(...)` để diễn đạt mục đích rõ ràng:

```java
LinkRelation actual = link.getRel();
LinkRelation expected = LinkRelation.of("orders");

if (actual.isSameAs(expected)) {
    // Đây là quan hệ orders.
}
```

`isSameAs` so sánh giá trị chuỗi của hai relation, không yêu cầu chúng phải được tạo từ cùng implementation. Khi cần tương thích với các relation chuẩn, nên dùng hằng số `IanaLinkRelations` thay vì tự tạo một chuỗi tương tự.

RFC 8288 quy định relation type được so sánh không phân biệt chữ hoa/thường. Tuy nhiên, không nên dựa vào việc một API Java tự chuẩn hóa mọi cách viết. Hãy dùng tên relation chuẩn ở dạng chữ thường và giữ URI relation tùy chỉnh ở dạng chữ thường thống nhất trong toàn ứng dụng.

Mô hình hypermedia cũng cho phép truy vấn link theo relation:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.Link;

EntityModel<OrderResponse> model = EntityModel.of(orderResponse);
model.add(Link.of("/orders/42", "self"));
model.add(Link.of("/orders/42/cancellation", "cancel"));

boolean canCancel = model.hasLink("cancel");

model.getLink(LinkRelation.of("cancel"))
        .ifPresent(cancelLink -> System.out.println(cancelLink.getHref()));
```

Trong ứng dụng, việc có link `cancel` có thể điều khiển việc hiển thị nút hủy. Tuy nhiên, server vẫn phải kiểm tra quyền và trạng thái khi nhận request. Relation chỉ mô tả khả năng được công bố trong biểu diễn.

## 5. Ưu tiên relation chuẩn từ IANA

IANA duy trì registry các link relation đã được chuẩn hóa. Spring HATEOAS cung cấp `IanaLinkRelations` để tham chiếu các giá trị này dưới dạng hằng số `LinkRelation`.

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
Link next = Link.of("/orders?page=1", IanaLinkRelations.NEXT);
Link collection = Link.of("/orders", IanaLinkRelations.COLLECTION);
```

Một số relation chuẩn thường gặp:

| Hằng số Spring | Giá trị relation | Ý nghĩa khái quát |
|---|---|---|
| `SELF` | `self` | Tài nguyên hiện tại. |
| `COLLECTION` | `collection` | Collection chứa tài nguyên hiện tại hoặc liên quan. |
| `ITEM` | `item` | Một phần tử trong collection. |
| `NEXT` | `next` | Trang hoặc phần tiếp theo. |
| `PREV` | `prev` | Trang hoặc phần trước. |
| `FIRST` | `first` | Trang đầu tiên. |
| `LAST` | `last` | Trang cuối cùng. |
| `EDIT` | `edit` | Đích có thể dùng để chỉnh sửa tài nguyên hiện tại. |
| `HELP` | `help` | Tài liệu trợ giúp cho tài nguyên hoặc thao tác. |

Có thể kiểm tra relation có thuộc tập IANA mà Spring biết hay không:

```java
boolean registered = IanaLinkRelations.isIanaRel(link.getRel());
```

Ưu tiên relation chuẩn khi ý nghĩa của liên kết khớp với một định nghĩa có sẵn. Điều này giúp client tổng quát có thể hiểu relation mà không cần tài liệu riêng của từng API. Không nên dùng `next` để biểu thị một thao tác nghiệp vụ không liên quan tới điều hướng tiếp theo.

## 6. Relation tùy chỉnh và quy tắc Web Linking

Khi nghiệp vụ cần một quan hệ không có trong registry, ứng dụng có thể định nghĩa relation mở rộng. Spring HATEOAS cho phép tạo relation từ chuỗi:

```java
Link cancel = Link.of(
        "/orders/42/cancellation",
        LinkRelation.of("cancel")
);
```

API Java chấp nhận chuỗi relation để ứng dụng làm việc thuận tiện. Tuy nhiên, cần phân biệt khả năng tạo chuỗi của thư viện với quy tắc của định dạng hypermedia trên wire. Theo RFC 8288, relation type có hai nhóm:

- **Registered relation type:** tên token đã đăng ký, ví dụ `self`, `next`, `collection`. Tên chuẩn được so sánh không phân biệt chữ hoa/thường; tên đăng ký phải ở dạng chữ thường ASCII.
- **Extension relation type:** URI tuyệt đối định danh duy nhất quan hệ do ứng dụng định nghĩa. URI này nên thuộc quyền kiểm soát của tổ chức định nghĩa relation và nên dùng chữ thường để so sánh nhất quán.

Vì vậy, đối với API cần khả năng tương tác rộng, relation tùy chỉnh nên dùng URI có ý nghĩa ổn định:

```java
Link cancel = Link.of(
        "/orders/42/cancellation",
        LinkRelation.of("https://api.example.com/rels/cancel")
);
```

Chuỗi `cancel` ngắn vẫn có thể dùng trong các hợp đồng nội bộ hoặc môi trường có quy ước rõ ràng, và Spring HATEOAS vẫn có thể biểu diễn nó. Nhưng nếu cần tuân thủ cách định danh relation mở rộng của Web Linking, hãy dùng URI tuyệt đối hoặc dạng CURIE mà media type hỗ trợ.

### Đặt tên relation tùy chỉnh

Một relation tốt nên:

1. Mô tả mối quan hệ giữa tài nguyên hiện tại và đích đến, không chỉ lặp lại đường dẫn.
2. Có ý nghĩa đơn nhất và ổn định trong toàn bộ API.
3. Không trùng hoặc làm sai lệch ý nghĩa relation IANA đã đăng ký.
4. Không đổi tên chỉ vì controller, class hoặc URL nội bộ được refactor.
5. Được ghi rõ trong tài liệu hợp đồng, nhất là khi client cần biết HTTP method hoặc payload của thao tác.

Ví dụ, `customer` phù hợp với liên kết từ đơn hàng tới khách hàng; `cancel` có thể mô tả đích của hành động hủy; `invoice` có thể trỏ tới hóa đơn của đơn hàng. Không nên đặt relation theo tên method Java như `getCustomerByOrderId` vì chi tiết triển khai không phải ngữ nghĩa của hợp đồng.

## 7. Dùng CURIE cho relation mở rộng trong HAL

Một URI relation tùy chỉnh có thể dài. HAL hỗ trợ CURIE (*Compact URI*) để biểu diễn relation URI bằng một tên rút gọn có prefix. Spring HATEOAS cung cấp `CurieProvider` và `DefaultCurieProvider` để tạo CURIE và tự động thêm link `curies` vào tài nguyên HAL.

Ví dụ cấu hình:

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
                "ex",
                new UriTemplate("https://api.example.com/rels/{rel}")
        );
    }
}
```

Với prefix `ex`, relation URI `https://api.example.com/rels/cancel` có thể được biểu diễn dưới dạng `ex:cancel`. Phản hồi HAL có dạng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  }
}
```

Client có thể dùng khai báo `curies` để hiểu `ex:cancel` tương ứng URI relation đầy đủ nào. CURIE là cách tuần tự hóa rút gọn dành cho HAL; không nên giả định mọi media type đều hỗ trợ prefix này. Nếu API trả nhiều định dạng hypermedia, hãy kiểm thử cách relation được biểu diễn trong từng định dạng.

## 8. Relation dạng chuỗi trong controller và assembler

Trong ứng dụng Spring MVC, relation thường được gắn khi tạo link trong controller hoặc assembler:

Ví dụ giả định `OrderResponse` là DTO có `id()` và `status()`, còn `OrderController` có các mapping `one`, `all` và `cancel` tương ứng.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    EntityModel<OrderResponse> toModel(OrderResponse order) {
        EntityModel<OrderResponse> model = EntityModel.of(order);

        model.add(linkTo(methodOn(OrderController.class).one(order.id()))
                .withRel(IanaLinkRelations.SELF));

        model.add(linkTo(methodOn(OrderController.class).all())
                .withRel("orders"));

        if ("PENDING".equals(order.status())) {
            model.add(linkTo(methodOn(OrderController.class).cancel(order.id()))
                    .withRel(LinkRelation.of("https://api.example.com/rels/cancel")));
        }

        return model;
    }
}
```

Ví dụ minh họa cách kết hợp relation chuẩn với relation tùy chỉnh. Nếu dùng CURIE trong HAL, cấu hình `CurieProvider` như phần trước để relation URI có thể được tuần tự hóa bằng prefix. Với controller thực tế, các method `one`, `all`, `cancel` phải có mapping phù hợp.

Để tránh lặp chuỗi relation trong nhiều lớp, có thể định nghĩa hằng số ở một nơi:

```java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    private ApiRelations() {}

    public static final LinkRelation ORDERS = LinkRelation.of("orders");
    public static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.com/rels/cancel");
    public static final LinkRelation CUSTOMER =
            LinkRelation.of("https://api.example.com/rels/customer");
}
```

Hằng số giúp giảm lỗi gõ sai, tập trung tài liệu và giúp thay đổi hợp đồng có kiểm soát. Chỉ tạo một hằng số khi relation được dùng nhiều nơi hoặc có ý nghĩa quan trọng; không cần tạo lớp registry riêng cho mọi link đơn giản.

## 9. Kiểm thử relation

Kiểm thử hypermedia cần xác nhận relation được công bố đúng và trỏ tới đích phù hợp. Không nên chỉ kiểm tra JSON có `_links`, vì tên relation có thể bị đổi hoặc thiếu.

Ví dụ với MockMvc và JSONPath:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pendingOrderPublishesCancelRelation() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists())
                .andExpect(jsonPath("$._links['https://api.example.com/rels/cancel'].href")
                        .exists());
    }
}
```

JSONPath và cách tuần tự hóa relation URI có thể phụ thuộc CURIE configuration. Nếu bật CURIE prefix `ex`, kiểm tra `_links['ex:cancel']` và link `curies` tương ứng. Hãy dùng đúng tên relation được công bố trong phản hồi thực tế.

Ngoài kiểm thử cấu trúc, nên xác nhận:

- Relation chuẩn được chọn đúng ngữ nghĩa, ví dụ `self`, `next`, `first`.
- Relation tùy chỉnh có tên ổn định và không xung đột với relation chuẩn.
- Relation hành động chỉ xuất hiện khi điều kiện nghiệp vụ cho phép.
- Client có thể tìm link theo relation mà không ghép URL.
- Việc đổi URI không làm đổi relation nếu ý nghĩa quan hệ không thay đổi.
- HAL CURIE được công bố và có thể giải nghĩa khi API dùng relation URI rút gọn.

## 10. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Xem `rel` chỉ là nhãn hiển thị | Client không hiểu ngữ nghĩa của link. | Đặt relation mô tả mối quan hệ giữa context và target. |
| Dùng relation chuẩn sai ý nghĩa | Client tổng quát có thể xử lý link sai. | Chọn relation IANA đúng nghĩa hoặc định nghĩa relation riêng. |
| Tự tạo relation tùy chỉnh trùng tên relation IANA | Hợp đồng mơ hồ hoặc xung đột với client. | Kiểm tra registry trước khi đặt tên. |
| Dùng tên method Java làm relation | Refactor code có thể vô tình thay đổi hợp đồng. | Dùng tên theo nghiệp vụ và giữ ổn định. |
| Rải chuỗi relation khắp code | Lỗi chính tả và thay đổi không đồng bộ. | Dùng hằng số `LinkRelation` cho relation dùng chung. |
| Cho rằng `LinkRelation.of` tự kiểm tra relation chuẩn | Chuỗi tùy ý có thể được dùng dù chưa có định nghĩa chung. | Phân biệt API tạo relation với quy tắc đăng ký/định danh relation. |
| Dùng chuỗi ngắn cho extension relation trong hợp đồng liên hệ rộng | Relation có thể không định danh duy nhất theo Web Linking. | Dùng URI tuyệt đối và CURIE khi phù hợp với HAL. |
| Client tự ghép URL từ relation | Client vẫn phụ thuộc cấu trúc endpoint. | Theo `href` do server trả về. |

## 11. Quy trình thiết kế relation dạng chuỗi

Khi cần thêm một quan hệ mới, thực hiện theo trình tự:

1. Xác định tài nguyên hiện tại và tài nguyên đích.
2. Viết một câu mô tả quan hệ giữa hai tài nguyên.
3. Kiểm tra IANA registry xem đã có relation phù hợp chưa.
4. Nếu có, dùng hằng số tương ứng từ `IanaLinkRelations`.
5. Nếu không, định nghĩa relation mở rộng có định danh ổn định; ưu tiên URI tuyệt đối cho khả năng tương tác.
6. Tạo `LinkRelation` bằng `LinkRelation.of(...)` hoặc dùng overload `withRel(String)` khi phù hợp.
7. Nếu dùng URI relation trong HAL, cân nhắc `CurieProvider` để rút gọn tên khi tuần tự hóa.
8. Ghi lại ý nghĩa, điều kiện xuất hiện và hành vi client mong đợi.
9. Kiểm thử relation, link đích và media type trong các trạng thái liên quan.

Relation dạng chuỗi là một API nhỏ nhưng có ý nghĩa lớn trong hợp đồng hypermedia. Khi relation được đặt tên đúng, dùng lại nhất quán và tuân theo quy tắc của định dạng, client có thể hiểu liên kết theo ngữ nghĩa thay vì phải biết cấu trúc URL hoặc tên method của server.

## Tài liệu tham khảo

- [Spring HATEOAS – Link relations](https://docs.spring.io/spring-hateoas/reference/fundamentals.html#fundamentals.link-relations)
- [Spring HATEOAS – LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS – IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS – CURIE support in HAL](https://docs.spring.io/spring-hateoas/reference/mediatypes.html#mediatypes.hal.curie-provider)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA – Link Relation Types registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
