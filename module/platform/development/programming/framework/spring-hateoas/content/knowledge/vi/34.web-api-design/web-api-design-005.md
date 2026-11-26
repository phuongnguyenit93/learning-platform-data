# Relation naming

## Mục tiêu

Sau bài này, bạn có thể đặt tên link relation theo ngữ nghĩa của API, chọn giữa relation chuẩn IANA và relation mở rộng, thống nhất tên cho tài nguyên đơn và collection, cấu hình tên bằng `@Relation` hoặc `LinkRelationProvider` trong Spring HATEOAS, đồng thời kiểm thử relation được serialize trong HAL.

## 1. Relation naming là quyết định về ngữ nghĩa

Một link biểu diễn mối quan hệ giữa tài nguyên đang chứa link (context) và tài nguyên đích (target). Relation name đặt tên cho mối quan hệ đó.

Ví dụ representation của một đơn hàng có thể công bố:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "collection": {
      "href": "/orders"
    },
    "acme:customer": {
      "href": "/customers/customer-7"
    },
    "acme:approval": {
      "href": "/orders/order-42/approval"
    }
  }
}
```

Các relation trong ví dụ có ý nghĩa riêng:

- `self` trỏ đến chính đơn hàng.
- `collection` trỏ đến collection chứa đơn hàng.
- `acme:customer` trỏ đến khách hàng liên quan.
- `acme:approval` trỏ đến tài nguyên hoặc quy trình phê duyệt đơn hàng.

Relation không phải URL, tên controller, tên thuộc tính Java hay HTTP method. Nó mô tả vai trò của target đối với context. Client có thể dùng relation để tìm đúng link mà không cần biết cấu trúc đường dẫn nội bộ của server.

Vì vậy, relation name là một phần của hợp đồng hypermedia. Khi client đã dựa vào relation để điều hướng, đổi tên hoặc đổi nghĩa relation có thể làm client cũ ngừng hoạt động dù URL và dữ liệu vẫn còn.

## 2. Bắt đầu bằng câu mô tả quan hệ

Trước khi chọn tên, hãy viết rõ câu:

> Tài nguyên hiện tại có quan hệ gì với tài nguyên đích?

Ví dụ:

| Context | Target | Câu mô tả quan hệ | Relation phù hợp |
|---|---|---|---|
| Một đơn hàng | Chính đơn hàng đó | Đây là URI của tài nguyên hiện tại | `self` |
| Một đơn hàng | Collection đơn hàng chứa nó | Đây là collection chứa tài nguyên hiện tại | `collection` |
| Một đơn hàng | Khách hàng liên quan | Đây là khách hàng của đơn hàng | Extension relation nếu `related` quá chung |
| Một đơn hàng | Quy trình phê duyệt | Đây là điểm truy cập quy trình phê duyệt đơn hàng | Extension relation `approval` |
| Một collection | Trang kế tiếp | Đây là phần tử kế tiếp trong chuỗi | `next` |
| Một collection | Trang liền trước | Đây là phần tử liền trước trong chuỗi | `prev` |

Câu mô tả giúp tránh các tên quá chung hoặc sai chiều. Ví dụ, nếu representation đơn hàng trỏ đến tài liệu mô tả đơn hàng, relation phù hợp là `describedby`; nếu tài liệu mô tả trỏ đến đơn hàng, relation là `describes`.

Đừng chọn tên chỉ vì nó giống tên endpoint. Endpoint `/orders/{id}/customer` có thể được công bố bằng relation `customer`, `related` hoặc một extension URI tùy ngữ nghĩa mà API muốn cam kết. URL có thể thay đổi độc lập với relation.

## 3. Ưu tiên relation chuẩn khi semantics đã khớp

IANA Link Relations Registry định nghĩa các relation có thể tái sử dụng giữa nhiều API. Spring HATEOAS cung cấp các hằng số trong `IanaLinkRelations`.

Ví dụ:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
Link collection = Link.of("/orders", IanaLinkRelations.COLLECTION);
Link next = Link.of("/orders?page=1", IanaLinkRelations.NEXT);
Link search = Link.of("/orders/search", IanaLinkRelations.SEARCH);
```

Một số nguyên tắc khi chọn relation chuẩn:

- Dùng `self` cho URI định danh context.
- Dùng `collection` khi target thực sự là collection chứa context.
- Dùng `next`, `prev`, `first` và `last` cho các vị trí tương ứng trong chuỗi.
- Dùng `search` cho tài nguyên tìm kiếm theo semantics của registry.
- Dùng `related` khi target chỉ là một tài nguyên liên quan và không có relation cụ thể hơn phù hợp.

Không nên dùng relation chuẩn theo nghĩa gần đúng. Ví dụ `item` biểu thị một item thuộc collection context; nó không phải tên thay thế chung cho mọi tài nguyên đơn. Nếu semantics không khớp, hãy chọn một relation khác hoặc định nghĩa extension relation.

Registered relation names được quy định là token chữ thường ASCII và được so sánh không phân biệt hoa thường theo RFC 8288. Trong response, nên serialize chúng bằng dạng chữ thường để giữ vocabulary nhất quán.

## 4. Khi nào cần extension relation?

Nếu IANA không có relation thể hiện đủ chính xác một quan hệ đặc thù, ứng dụng có thể định nghĩa extension relation. Theo RFC 8288, extension relation phải là một URI định danh duy nhất và nên thuộc quyền kiểm soát của tổ chức định nghĩa nó.

Ví dụ:

- `https://api.example.com/rels/customer`
- `https://api.example.com/rels/approval`
- `https://api.example.com/rels/line-items`

URI relation định danh loại quan hệ; thuộc tính `href` của link mới xác định tài nguyên đích cụ thể.

Trong Spring HATEOAS:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link customer = Link.of(
        "/customers/customer-7",
        LinkRelation.of("https://api.example.com/rels/customer")
);

Link approval = Link.of(
        "/orders/order-42/approval",
        LinkRelation.of("https://api.example.com/rels/approval")
);
```

Không nên tự tạo một token như `approval` rồi xem nó đã là relation chuẩn. `LinkRelation.of(...)` chỉ tạo giá trị relation trong Java; nó không đăng ký tên đó với IANA. Nếu relation là extension, cần dùng URI theo quy tắc của RFC 8288 hoặc dạng CURIE được định nghĩa bởi media type như HAL.

URI relation nên ổn định, dùng chữ thường và thuộc namespace do tổ chức kiểm soát. Tài liệu tại URI có thể mô tả context, target, semantics và các điều kiện công bố relation. Client không cần tự động truy cập URI đó mỗi khi nhận response; nó có thể dùng tài liệu API hoặc cache metadata đã biết.

## 5. Quy ước đặt tên cho item và collection

Với representation model, thường cần hai tên:

- **Item relation**: tên relation khi chỉ một tài nguyên thuộc kiểu đó được tham chiếu.
- **Collection relation**: tên relation khi collection của kiểu đó được tham chiếu.

Một quy ước dễ hiểu là dùng danh từ số ít cho item và dạng collection cho danh sách:

| Kiểu tài nguyên | Item relation | Collection relation |
|---|---|---|
| Đơn hàng | `order` | `orders` |
| Khách hàng | `customer` | `customers` |
| Dòng hàng | `line-item` | `line-items` |
| Hóa đơn | `invoice` | `invoices` |

Đây là quy ước thiết kế, không phải quy tắc bắt buộc của HTTP hay HAL. API có thể dùng từ vựng nghiệp vụ riêng, miễn là tên item và collection rõ ràng, ổn định và không mơ hồ.

Nên chọn một phong cách nhất quán cho toàn API:

- Tên relation ngắn và có nghĩa nghiệp vụ.
- Dùng chữ thường cho relation token; với extension URI, ưu tiên toàn bộ URI chữ thường.
- Không đưa tên package, tên class Java, tên bảng database hoặc mã nội bộ vào relation public.
- Tránh các từ viết tắt chỉ đội phát triển hiểu.
- Không dùng một relation cho hai ý nghĩa khác nhau chỉ vì cả hai cùng trỏ đến một loại URL.

Ví dụ, `line-items` mô tả collection các dòng hàng tốt hơn `details` nếu API cần phân biệt dòng hàng với thông tin chi tiết khác. Nếu một tên phải giải thích bằng nhiều ngoại lệ, hãy xem lại vocabulary.

## 6. Đặt tên relation cho embedded resource bằng @Relation

Spring HATEOAS cung cấp annotation `@Relation` trong package `org.springframework.hateoas.server.core`. Annotation này cấu hình relation được dùng khi nhúng object trong HAL representation của `EntityModel` và `CollectionModel`.

Ví dụ:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
        itemRelation = "order",
        collectionRelation = "orders"
)
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Có thể dùng thuộc tính `value` làm alias của `itemRelation`:

```java
@Relation(value = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {
    // Các thuộc tính representation.
}
```

Khi collection các `OrderModel` được serialize, relation collection có thể được dùng làm khóa trong `_embedded.orders`. Khi một object `OrderModel` được nhúng như item, relation item là `order`.

Ví dụ collection:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PENDING"
      }
    ]
  }
}
```

Điểm cần nhớ: `@Relation` điều khiển tên relation được suy ra từ kiểu khi nhúng object. Nó không tự đổi relation của một link mà code đã chỉ định rõ bằng `withRel(...)` hoặc `Link.of(..., relation)`.

Ví dụ link dưới đây có relation được gán tường minh:

```java
Link customer = Link.of(
        "/customers/customer-7",
        LinkRelation.of("https://api.example.com/rels/customer")
);
```

Tên của link này không lấy từ `@Relation` trên `CustomerModel`. Muốn thay đổi link relation, hãy thay đổi chính `LinkRelation` được truyền vào link.

## 7. LinkRelationProvider và quy tắc suy luận mặc định

Khi Spring HATEOAS cần suy ra relation từ một kiểu Java, `LinkRelationProvider` cung cấp hai giá trị:

- `getItemResourceRelFor(Class<?>)`: relation của tài nguyên đơn.
- `getCollectionResourceRelFor(Class<?>)`: relation của collection.

Trong Spring HATEOAS hiện hành, thuật toán được mô tả như sau:

1. Nếu kiểu có `@Relation`, sử dụng các giá trị được khai báo trong annotation.
2. Nếu không có annotation, dùng tên class đơn giản với chữ cái đầu viết thường cho item; collection mặc định thêm hậu tố `List`.
3. Nếu thư viện Evo Inflector có trong classpath, relation collection được tạo bằng thuật toán số nhiều của thư viện.
4. Controller có `@ExposesResourceFor` được tra relation theo kiểu tài nguyên mà controller công bố.

Ví dụ kiểu `OrderModel` không có `@Relation` có thể tạo item relation `orderModel` và collection relation `orderModelList`. Nếu có Evo Inflector, tên collection có thể được tạo thành dạng số nhiều theo thuật toán của thư viện.

Đây là lý do nên khai báo relation tường minh cho representation public. Đổi tên class hoặc thêm dependency pluralization có thể làm tên suy ra thay đổi. Nếu client đã dùng tên cũ, thay đổi đó có thể trở thành breaking change.

Có thể inject provider để xem relation đang được áp dụng:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
public class RelationInspector {

    private final LinkRelationProvider provider;

    public RelationInspector(LinkRelationProvider provider) {
        this.provider = provider;
    }

    public void inspect() {
        LinkRelation item =
                provider.getItemResourceRelFor(OrderModel.class);

        LinkRelation collection =
                provider.getCollectionResourceRelFor(OrderModel.class);

        // Với @Relation ở ví dụ trên:
        // item = "order"
        // collection = "orders"
    }
}
```

`LinkRelationProvider` được đăng ký trong cấu hình hypermedia của Spring HATEOAS. Có thể thay đổi thuật toán bằng cách cung cấp implementation riêng dưới dạng Spring bean.

## 8. Tạo naming policy riêng bằng LinkRelationProvider

Khi một nhóm representation cần quy tắc tên tập trung, có thể triển khai `LinkRelationProvider`. Interface hiện hành có các phương thức `getItemResourceRelFor`, `getCollectionResourceRelFor` và `supports(LookupContext)`.

Ví dụ provider riêng cho hóa đơn:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
public class InvoiceRelationProvider implements LinkRelationProvider {

    @Override
    public LinkRelation getItemResourceRelFor(Class<?> type) {
        return LinkRelation.of("invoice");
    }

    @Override
    public LinkRelation getCollectionResourceRelFor(Class<?> type) {
        return LinkRelation.of("invoices");
    }

    @Override
    public boolean supports(LookupContext context) {
        return context.handlesType(InvoiceModel.class);
    }
}
```

`supports(...)` cho biết provider này xử lý kiểu nào. `DelegatingLinkRelationProvider` dùng lookup context để chọn implementation phù hợp; code ứng dụng thông thường không cần tự gọi `supports(...)`.

Ví dụ chỉ minh họa một naming policy thay cho annotation trên `InvoiceModel`. Không nên để custom provider và `@Relation` cùng cạnh tranh quyền đặt tên cho một kiểu. Hãy xác định một nguồn chịu trách nhiệm cho mỗi nhóm model để kết quả không phụ thuộc thứ tự provider.

Trong ví dụ, `invoice` và `invoices` là tên ngắn của vocabulary ứng dụng. Khi serialize thành HAL, hãy cấu hình `CurieProvider` để namespace các relation không thuộc IANA (chẳng hạn thành `acme:invoice` và `acme:invoices`), hoặc để provider trả về extension relation URI phù hợp. Không nên coi các token tự đặt này là relation chuẩn IANA.

Custom provider phù hợp khi tổ chức có quy tắc dùng chung, ví dụ mọi model trong bounded context Billing đều dùng vocabulary riêng. Nếu chỉ một hoặc hai model cần tên khác, `@Relation` thường đơn giản và dễ bảo trì hơn.

## 9. Liên kết controller với domain type bằng @ExposesResourceFor

Controller thường được tổ chức theo domain type mà nó công bố. `@ExposesResourceFor` khai báo kiểu tài nguyên mà controller đại diện:

```java
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
public class OrderController {
    // Các endpoint collection và item của Order.
}
```

Khi `LinkRelationProvider` tra relation theo controller class, Spring HATEOAS có thể chuyển việc tra cứu sang domain type được khai báo. Điều này hữu ích với `EntityLinks` và các API tạo link dựa trên controller.

Tuy nhiên, controller class, domain entity và representation DTO có thể là ba kiểu khác nhau. Nếu HAL nhúng `OrderModel`, hãy đặt relation trên `OrderModel` hoặc cấu hình provider xử lý chính kiểu đó. Đừng dựa vào tên controller để quyết định relation của mọi representation.

## 10. Dùng CURIE để công bố extension relation trong HAL

HAL hỗ trợ CURIE (Compact URI) để rút gọn extension relation URI. Một CURIE gồm prefix và tên rút gọn; response phải công bố link `curies` để client có thể mở rộng tên đó thành URI đầy đủ.

Ví dụ, relation URI đầy đủ:

```text
https://api.example.com/rels/approval
```

có thể được serialize thành `acme:approval` nếu prefix `acme` được ánh xạ đến URI template `https://api.example.com/rels/{rel}`.

Spring HATEOAS cung cấp `DefaultCurieProvider`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
public class HalRelationConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
```

Khi CurieProvider được cấu hình, Spring HATEOAS có thể thêm link `curies` vào HAL response và dùng prefix cho các relation extension. Relation chuẩn IANA vẫn giữ dạng chuẩn, ví dụ `self`, `next` hoặc `collection`.

Quy tắc này cũng áp dụng cho relation item và collection do `@Relation` hoặc `LinkRelationProvider` cung cấp. Ví dụ, `order` và `orders` có thể được serialize thành `acme:order` và `acme:orders` nếu chúng không phải relation IANA và CurieProvider dùng prefix `acme`.

Ví dụ response:

```json
{
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approval": {
      "href": "/orders/order-42/approval"
    }
  }
}
```

Spring HATEOAS hiện hỗ trợ một CurieProvider cho mỗi application scope. Vì vậy, hãy chọn prefix và URI template có phạm vi đủ rộng cho vocabulary extension của API. Prefix là một phần của representation mà client đọc, nên cũng cần ổn định.

CURIE là cách rút gọn trong HAL; nó không thay đổi semantics của relation URI gốc và không phải một relation IANA mới.

## 11. Phân biệt relation của link với tên property và affordance

Ba loại tên thường bị nhầm:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| JSON property | Tên trường dữ liệu trong representation | `status`, `total` |
| Link relation | Ý nghĩa của liên kết giữa context và target | `self`, `acme:approval` |
| Affordance/template name | Tên hành động hoặc biểu mẫu client có thể thực hiện | `cancel`, `updateOrder` |

Ví dụ, một đơn hàng có thể chứa trường `status`, link relation `acme:approval` và affordance `cancel`. Ba tên này không thay thế nhau.

Relation `acme:approval` nói target liên quan đến quy trình phê duyệt. Affordance có thể mô tả HTTP method, input và output cho thao tác gửi đến target. Trong HAL-FORMS, tên template có thể được suy ra từ method controller hoặc đặt tường minh bằng API affordance.

Không nên dùng relation để nhét toàn bộ mô tả thao tác như `postCancelOrderWithReason`. Hãy giữ relation ngắn, biểu đạt quan hệ; dùng affordance và metadata phù hợp để mô tả cách tương tác.

## 12. Giữ relation ổn định khi API phát triển

Một khi relation đã được client sử dụng, hãy xem nó như một định danh công khai:

- Không đổi `orders` thành `orderList` chỉ vì refactor tên class.
- Không đổi relation từ “collection chứa item” sang “collection có item liên quan” mà không đánh giá ảnh hưởng client.
- Không tái sử dụng một URI relation cũ cho semantics mới.
- Giữ URI extension thuộc quyền kiểm soát của tổ chức và duy trì tài liệu mô tả.
- Nếu cần đổi vocabulary, cân nhắc giai đoạn chuyển tiếp để client có thời gian hỗ trợ relation mới.
- Không dịch relation theo `Accept-Language`; tên relation là định danh máy đọc, còn `title` có thể được quốc tế hóa.

Relation nên giữ ngữ nghĩa ổn định ngay cả khi URL, controller, service, database hoặc tên DTO thay đổi. Đây là lợi ích quan trọng của hypermedia: client dựa trên quan hệ được công bố, không phụ thuộc cấu trúc triển khai nội bộ.

## 13. Kiểm thử relation naming

Nên kiểm tra cả relation do provider trả về và JSON HAL cuối cùng.

Kiểm tra item và collection relation:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;

@SpringBootTest
class RelationNamingTest {

    @Autowired
    private LinkRelationProvider provider;

    @Test
    void exposesStableOrderRelations() {
        assertThat(provider.getItemResourceRelFor(OrderModel.class))
                .isEqualTo(LinkRelation.of("order"));

        assertThat(provider.getCollectionResourceRelFor(OrderModel.class))
                .isEqualTo(LinkRelation.of("orders"));
    }
}
```

Đây là ví dụ kiểm thử trong Spring test context có bean `LinkRelationProvider`. Nếu dùng JUnit thuần không có Spring context, hãy khởi tạo implementation cụ thể hoặc dùng test cấu hình phù hợp.

Kiểm tra response HAL:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu API dùng CURIE, kiểm tra cả mapping prefix và relation đã rút gọn:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies.name").value("acme"))
    .andExpect(jsonPath("$._links['acme:approval'].href").exists());
```

Nên có thêm các test sau:

1. Item relation và collection relation đúng với naming policy.
2. Đổi tên class Java không làm relation public thay đổi khi đã cấu hình tường minh.
3. Relation của link được gán bằng `withRel(...)` không bị nhầm với `@Relation`.
4. Collection rỗng vẫn có relation nếu model cung cấp fallback type.
5. Extension relation được serialize đúng dạng URI hoặc CURIE.
6. Prefix CURIE được công bố cùng URI template hợp lệ.
7. Relation chuẩn IANA giữ nguyên tên chuẩn.
8. Không có hai khái niệm nghiệp vụ khác nhau dùng chung một relation name.

## 14. Những lỗi thường gặp

**Dùng tên class làm relation public.** Đổi tên DTO có thể làm relation thay đổi. Khai báo `@Relation` hoặc naming provider rõ ràng.

**Chỉ định item relation nhưng quên collection relation.** Collection có thể nhận tên suy luận như `orderModelList`. Khai báo cả hai khi API công bố cả item và collection.

**Nhầm `@Relation` với `withRel(...)`.** Annotation cấu hình relation được suy ra cho embedded model; `withRel(...)` đặt relation của một link cụ thể.

**Dùng relation chuẩn cho semantics không khớp.** Client có thể hiểu target sai. Chọn IANA relation chính xác hoặc extension URI.

**Dùng bare token tùy ý cho extension relation trong HAL.** Token không tự trở thành relation chuẩn. Dùng URI extension và CURIE khi cần rút gọn.

**Để Evo Inflector quyết định hợp đồng mà không kiểm thử.** Thêm hoặc bỏ dependency có thể thay đổi pluralization. Khai báo collection relation tường minh nếu tên là public contract.

**Đăng ký custom provider quá rộng.** Provider có thể nhận các kiểu ngoài dự kiến. Giới hạn `supports(...)` cho đúng nhóm model.

**Dùng cùng một relation cho nhiều nghĩa.** Client không thể phân biệt các target theo semantics. Tạo vocabulary riêng cho từng quan hệ có ý nghĩa khác nhau.

**Đổi relation mà không xét client hiện tại.** Relation name là hợp đồng công khai. Lập kế hoạch tương thích trước khi đổi.

## 15. Nguyên tắc thiết kế

- Viết rõ quan hệ context → target trước khi chọn tên.
- Ưu tiên IANA relation khi semantics khớp chính xác.
- Dùng extension URI do tổ chức kiểm soát khi quan hệ mang ý nghĩa riêng.
- Giữ relation ngắn, rõ, nhất quán và độc lập với tên class hoặc endpoint.
- Chọn quy ước item/collection rõ ràng, ví dụ `order` và `orders`.
- Dùng `@Relation` để đặt tên item và collection cho representation model.
- Dùng `LinkRelationProvider` khi cần quy tắc tập trung cho nhiều kiểu.
- Dùng `@ExposesResourceFor` để liên kết controller với domain type mà nó công bố.
- Dùng CURIE để rút gọn extension relation URI trong HAL.
- Phân biệt relation với JSON property, URL, HTTP method và affordance name.
- Kiểm thử relation sau serialization như một phần hợp đồng API.

## Kết luận

Relation naming quyết định cách client hiểu quan hệ giữa tài nguyên hiện tại và target. Hãy chọn tên theo ngữ nghĩa, ưu tiên IANA relation khi phù hợp và dùng extension URI cho vocabulary riêng. Spring HATEOAS hỗ trợ đặt tên embedded relation bằng `@Relation`, áp dụng chính sách tập trung bằng `LinkRelationProvider` và rút gọn extension URI bằng `CurieProvider`. Giữ relation ổn định, tách biệt chúng khỏi tên class và endpoint, đồng thời kiểm thử JSON HAL thực tế để bảo vệ hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS Reference – LinkRelationProvider](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-relation-provider)
- [Spring HATEOAS Reference – CurieProvider](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie-provider)
- [Spring HATEOAS API – @Relation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring HATEOAS API – LinkRelationProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)

