# Tên relation dễ hiểu

Trong REST HATEOAS, client điều hướng theo relation của link thay vì dựa vào tên endpoint hoặc tự ghép URL. Relation trả lời câu hỏi “liên kết này có ý nghĩa gì đối với tài nguyên hiện tại?”. Vì vậy, tên relation cần ổn định, dễ hiểu và mô tả đúng mối quan hệ mà server muốn công bố.

Spring HATEOAS biểu diễn relation bằng `LinkRelation`. Khi tạo link, ứng dụng có thể dùng relation chuẩn từ IANA hoặc định nghĩa extension relation riêng. Ngoài ra, Spring HATEOAS cung cấp `@Relation` và `LinkRelationProvider` để đặt tên nhất quán cho item resource và collection resource, đặc biệt khi serialize collection thành HAL.

Bài học này thuộc chương **Custom relation** trong module **SPRING_HATEOAS**, tập trung vào cách chọn tên relation dễ hiểu, phân biệt relation chuẩn và relation mở rộng, tùy chỉnh tên item/collection bằng `@Relation`, sử dụng `LinkRelationProvider`, và tránh nhầm relation với `title`, `name` hoặc URL.

Sau bài học, bạn có thể:

- Giải thích vai trò ngữ nghĩa của relation trong hypermedia.
- Chọn relation chuẩn IANA khi semantics phù hợp.
- Định nghĩa extension relation ổn định bằng URI.
- Tạo link với `LinkRelation` và `IanaLinkRelations`.
- Dùng `@Relation` để tùy chỉnh item relation và collection relation.
- Sử dụng `LinkRelationProvider` để lấy relation theo kiểu representation.
- Phân biệt relation key trong `_links`, key trong `_embedded`, `title` và `name`.
- Kiểm thử relation được serialize đúng trong HAL.

## 1. Relation mô tả ý nghĩa của liên kết

Một resource có thể cung cấp nhiều liên kết tới những đích khác nhau. Ví dụ đơn hàng có link tới chính nó, collection đơn hàng, khách hàng và thao tác hủy:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "https://api.example.com/orders/42" },
    "orders": { "href": "https://api.example.com/orders" },
    "customer": { "href": "https://api.example.com/customers/7" },
    "cancel": { "href": "https://api.example.com/orders/42/cancellation" }
  }
}
```

Các key `self`, `orders`, `customer` và `cancel` là relation. Chúng cho client biết link tương ứng có vai trò gì. Client có thể tìm relation `customer` mà không cần biết server đặt path là `/customers/7`, `/clients/7` hay một URI khác.

Một relation tốt cần có semantics rõ ràng:

- `customer` biểu thị quan hệ tới khách hàng của đơn hàng.
- `next` biểu thị trang tiếp theo trong một tập kết quả.
- `cancel` biểu thị khả năng hoặc điểm truy cập liên quan tới thao tác hủy.
- `self` biểu thị URI chuẩn của resource đang được biểu diễn.

Relation không phải tên method Java, tên controller hoặc bản sao của URL. Nếu route nội bộ thay đổi nhưng ý nghĩa quan hệ vẫn giữ nguyên, relation nên được giữ ổn định và chỉ `href` thay đổi.

## 2. Tiêu chí đặt tên relation dễ hiểu

Khi định nghĩa relation cho API, hãy ưu tiên các nguyên tắc sau:

1. **Mô tả ngữ nghĩa, không mô tả triển khai.** `customer` hữu ích hơn `getCustomerById` vì client không cần biết method hoặc cách truy vấn.
2. **Dùng cùng một tên cho cùng một ý nghĩa.** Nếu `payment` luôn chỉ tài nguyên thanh toán liên quan, đừng đổi thành `payInfo` ở một endpoint khác mà không có lý do hợp đồng.
3. **Ưu tiên relation chuẩn khi phù hợp.** Các relation như `self`, `next`, `prev`, `first`, `last`, `collection`, `item`, `related` đã có semantics được định nghĩa.
4. **Dùng extension relation có định danh ổn định cho semantics riêng.** Với relation nghiệp vụ không có trong registry, định danh bằng URI do tổ chức kiểm soát.
5. **Không dùng relation làm nhãn giao diện.** Dùng `title` để hiển thị câu chữ thân thiện; relation cần ổn định cho client và chương trình.
6. **Tránh viết tắt nội bộ hoặc tên khó hiểu.** Client bên ngoài không nên phải biết thuật ngữ nội bộ của đội phát triển.

Ví dụ lựa chọn:

| Tên relation | Đánh giá | Lý do |
|---|---|---|
| `customer` | Tốt | Nêu rõ tài nguyên liên quan. |
| `next` | Tốt khi đúng semantics | Relation chuẩn cho bước tiếp theo. |
| `cancel` | Có thể dùng làm extension relation | Mô tả hành động nghiệp vụ rõ ràng; nên định danh ổn định nếu là extension. |
| `getCustomer` | Không nên | Gắn với cách triển khai và tên method. |
| `cust_v2` | Không nên | Viết tắt nội bộ, lẫn semantics với phiên bản. |
| `link1` | Không nên | Không thể hiện ý nghĩa. |

Relation không cần là câu dài. Một từ hoặc cụm ngắn có semantics rõ thường dễ dùng hơn. Tài liệu định nghĩa relation có thể giải thích chi tiết hơn về hành vi và điều kiện sử dụng.

## 3. Relation chuẩn IANA và extension relation

Relation thường thuộc một trong hai nhóm:

- **Registered relation:** relation đã được đăng ký trong IANA Link Relation Types registry. Ví dụ `self`, `next`, `prev`, `first`, `last`, `collection`, `item`, `related`, `edit` và `help`.
- **Extension relation:** relation do API hoặc tổ chức định nghĩa để diễn đạt semantics riêng, thường được định danh bằng URI tuyệt đối.

Spring HATEOAS cung cấp `IanaLinkRelations` để dùng các relation chuẩn dưới dạng hằng số:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
Link next = Link.of("/orders?page=1", IanaLinkRelations.NEXT);
Link help = Link.of("https://docs.example.com/orders", IanaLinkRelations.HELP);
```

Không nên dùng relation chuẩn chỉ vì tên của nó nghe gần giống nhu cầu. Chỉ dùng khi semantics trong registry thực sự phù hợp. Ví dụ `edit` có nghĩa quan hệ tới tài nguyên có thể chỉnh sửa theo semantics đã định nghĩa; nếu API muốn công bố một hành động nghiệp vụ cụ thể như hoàn tiền, hãy cân nhắc extension relation `refund` thay vì dùng một relation chuẩn sai nghĩa.

## 4. Định nghĩa extension relation bằng URI

Khi không có relation chuẩn phù hợp, hãy định nghĩa relation riêng bằng URI mà tổ chức có thể duy trì lâu dài:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link cancel = Link.of("/orders/42/cancellation")
        .withRel(LinkRelation.of("https://api.example.com/rels/cancel"));
```

HAL representation có thể dùng URI đó làm key relation:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/orders/42/cancellation"
    }
  }
}
```

URI relation đóng vai trò định danh và tài liệu hóa semantics. Client không nhất thiết phải tải URI đó trong mỗi lần gọi API; điều quan trọng là URI ổn định và có thể trỏ tới tài liệu giải thích relation.

Đừng dùng URL endpoint làm relation chỉ vì endpoint đã tồn tại. Relation URI định danh **ý nghĩa quan hệ**, còn `href` xác định **đích cụ thể**. Hai URI này có thể khác domain, path và vòng đời.

## 5. Dùng CURIE để rút gọn extension relation trong HAL

URI relation đầy đủ có thể dài. HAL hỗ trợ CURIE (*Compact URI*) để khai báo prefix và rút gọn relation key. Ví dụ:

```json
{
  "_links": {
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "acme:cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  }
}
```

`acme:cancel` là dạng rút gọn của relation URI theo template đã công bố. Client có thể dùng khai báo `curies` để hiểu prefix `acme` được mở rộng thành URI nào.

Spring HATEOAS hỗ trợ CURIE thông qua `CurieProvider`. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HalRelationConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                new UriTemplate("https://api.example.com/rels/{rel}")
        );
    }
}
```

Khi `CurieProvider` được cấu hình, Spring HATEOAS có thể công bố prefix và rút gọn extension relation tương ứng khi serialize HAL. CURIE là quy ước của HAL; không giả định client của media type khác sẽ hiểu prefix này.

## 6. Tạo custom relation với LinkRelation

`LinkRelation` là kiểu giá trị chuyên biệt cho relation. Dùng `LinkRelation.of(...)` để tạo relation riêng và truyền vào `Link`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link refund = Link.of("/orders/42/refund")
        .withRel(LinkRelation.of("https://api.example.com/rels/refund"));

Link invoice = Link.of("/orders/42/invoice")
        .withRel(LinkRelation.of("https://api.example.com/rels/invoice"));
```

Có thể gom relation vào hằng số để tránh lặp chuỗi:

```java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    private ApiRelations() {}

    public static final LinkRelation REFUND =
            LinkRelation.of("https://api.example.com/rels/refund");

    public static final LinkRelation INVOICE =
            LinkRelation.of("https://api.example.com/rels/invoice");
}
```

Sau đó dùng:

```java
Link refund = Link.of("/orders/42/refund").withRel(ApiRelations.REFUND);
```

Việc tập trung relation giúp tránh lỗi chính tả và hỗ trợ tái sử dụng giữa assembler, controller và processor. Tên hằng số có thể theo quy ước Java, còn giá trị relation URI phải giữ đúng hợp đồng công khai.

## 7. Tùy chỉnh tên item và collection bằng @Relation

Spring HATEOAS có annotation `@Relation` để tùy chỉnh relation được dùng cho item resource và collection resource của một kiểu representation. Annotation này đặc biệt hữu ích khi tên class Java không phải tên phù hợp để công bố cho client.

Ví dụ class Java tên `PurchaseOrderRepresentation`, nhưng API muốn công bố item relation là `order` và collection relation là `orders`:

```java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class PurchaseOrderRepresentation
        extends RepresentationModel<PurchaseOrderRepresentation> {

    private Long id;
    private String status;

    // Constructors, getters and setters.
}
```

Khi dùng representation này trong collection, Spring HATEOAS dùng `orders` làm relation của collection:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "_links": {
          "self": { "href": "/orders/42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
```

Tên `orders` ở `_embedded` là collection relation. Từng phần tử trong mảng là representation của một item; HAL không bọc từng phần tử trong một object có key `order` riêng.

`itemRelation` và `collectionRelation` có vai trò riêng: `itemRelation` đặt tên khi một representation đơn lẻ của kiểu đó được nhúng hoặc được tham chiếu; `collectionRelation` đặt tên cho một tập hợp representation. Ví dụ, một đơn hàng được nhúng riêng có thể nằm dưới `_embedded.order`, còn danh sách đơn hàng nằm dưới `_embedded.orders`. `value` là alias của `itemRelation`, nên có thể viết `@Relation(value = "order", collectionRelation = "orders")` nếu muốn.

`@Relation` không tự tạo link tới endpoint. Nó cung cấp tên relation theo kiểu representation để Spring HATEOAS sử dụng khi tạo collection hoặc embedded resource. Để tạo link tới một URI cụ thể, vẫn dùng `Link` và `.withRel(...)`.

## 8. LinkRelationProvider quyết định tên relation theo kiểu

`LinkRelationProvider` là abstraction để lấy relation cho item resource và collection resource dựa trên Java type:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;

class RelationNameService {

    private final LinkRelationProvider relationProvider;

    RelationNameService(LinkRelationProvider relationProvider) {
        this.relationProvider = relationProvider;
    }

    LinkRelation itemRelation() {
        return relationProvider.getItemResourceRelFor(PurchaseOrderRepresentation.class);
    }

    LinkRelation collectionRelation() {
        return relationProvider.getCollectionResourceRelFor(PurchaseOrderRepresentation.class);
    }
}
```

Spring HATEOAS đăng ký implementation phù hợp trong application context. Thuật toán phân giải relation theo thứ tự:

1. Nếu kiểu có `@Relation`, dùng `itemRelation` và `collectionRelation` đã khai báo.
2. Nếu không có annotation, `DefaultLinkRelationProvider` dùng tên class đã viết thường chữ đầu làm item relation và nối thêm `List` cho collection relation. Ví dụ `OrderResponse` có thể thành `orderResponse` và `orderResponseList`.
3. Nếu thư viện Evo Inflector có trên classpath, `EvoInflectorLinkRelationProvider` có thể tạo dạng số nhiều tiếng Anh tự nhiên hơn, ví dụ `order` và `orders`.
4. Với controller có `@ExposesResourceFor`, `ControllerLinkRelationProvider` có thể phân giải relation theo domain type mà controller công bố.

`DelegatingLinkRelationProvider` chọn provider phù hợp theo `LookupContext`. `@EnableHypermediaSupport` tự công bố `LinkRelationProvider` như một Spring bean; ứng dụng cũng có thể bổ sung provider riêng bằng cách đăng ký bean triển khai interface.

Inject interface `LinkRelationProvider` thay vì tự tạo `DefaultLinkRelationProvider` trong từng lớp. Cách đó giúp ứng dụng tôn trọng cấu hình relation chung và annotation đã khai báo.

### Khi nào cần provider tùy chỉnh?

Nếu quy tắc đặt tên không thể biểu diễn bằng `@Relation`, có thể viết provider riêng. Provider dưới đây chỉ xử lý `OrderResponse`; các kiểu khác được provider khác trong cơ chế delegation đảm nhiệm:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
class OrderLinkRelationProvider implements LinkRelationProvider {

    @Override
    public boolean supports(LinkRelationProvider.LookupContext context) {
        return OrderResponse.class.equals(context.getType());
    }

    @Override
    public LinkRelation getItemResourceRelFor(Class<?> type) {
        return LinkRelation.of("order");
    }

    @Override
    public LinkRelation getCollectionResourceRelFor(Class<?> type) {
        return LinkRelation.of("orders");
    }
}
```

`supports` giúp `DelegatingLinkRelationProvider` chọn implementation theo kiểu cần phân giải. Hãy giữ phạm vi provider hẹp và có kiểm thử; một provider nhận mọi kiểu có thể vô tình ghi đè quy tắc relation mặc định của các representation khác. Nếu dùng provider tùy chỉnh cho một kiểu, tránh đồng thời khai báo `@Relation` cho cùng kiểu đó trừ khi đã chủ động kiểm soát thứ tự lựa chọn provider.

## 9. Khi nào dùng @Relation và khi nào dùng withRel?

Hai cơ chế giải quyết hai nhu cầu khác nhau:

| Cơ chế | Phạm vi | Dùng khi |
|---|---|---|
| `@Relation(itemRelation, collectionRelation)` | Tên relation gắn với một kiểu representation | Muốn tên item/collection nhất quán ở nhiều response. |
| `Link.withRel(...)` | Một liên kết cụ thể | Muốn đặt relation cho một link như `customer`, `cancel`, `refund`. |
| `IanaLinkRelations` | Relation chuẩn IANA | Muốn dùng relation chuẩn có sẵn như `self`, `next`, `help`. |
| `LinkRelationProvider` | Ánh xạ kiểu Java sang item/collection relation | Muốn lấy relation theo cấu hình chung thay vì tự suy ra từ tên class. |

Ví dụ một DTO có thể dùng `@Relation` để xác định collection relation `orders`, nhưng link từ đơn hàng tới khách hàng vẫn cần relation riêng `customer`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

EntityModel<PurchaseOrderRepresentation> model = EntityModel.of(order);
model.add(Link.of("/customers/7").withRel("customer"));
```

Đoạn code giả định `order` là một `PurchaseOrderRepresentation` đã được tạo từ service.

Không dùng `@Relation` để thay thế tất cả relation link trong resource. Annotation tập trung vào item/collection naming; link cụ thể vẫn được đặt relation tại nơi tạo link.

## 10. Relation, title và name là ba khái niệm khác nhau

HAL link object có thể chứa `title` và `name`, nhưng chúng không thay thế relation:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Relation | Ý nghĩa ngữ nghĩa mà client dùng để tìm liên kết | `customer`, `next`, `https://api.example.com/rels/refund` |
| `title` | Nhãn dễ đọc để hiển thị | `Thông tin khách hàng`, `Hoàn tiền` |
| `name` | Tên phụ để phân biệt các link cùng relation | `primary`, `download-pdf` |
| `href` | URI đích | `/customers/7` |

Ví dụ:

```java
Link refund = Link.of("/orders/42/refund")
        .withRel("https://api.example.com/rels/refund")
        .withTitle("Hoàn tiền cho đơn hàng")
        .withName("refund-order");
```

HAL output:

```json
{
  "_links": {
    "https://api.example.com/rels/refund": {
      "href": "/orders/42/refund",
      "title": "Hoàn tiền cho đơn hàng",
      "name": "refund-order"
    }
  }
}
```

Client dùng relation để hiểu loại liên kết, có thể dùng `title` làm nhãn giao diện và `name` để phân biệt nhiều link cùng relation. Đừng đặt relation thành câu tiếng Việt thay đổi theo locale; semantics của relation nên ổn định, còn title có thể được quốc tế hóa.

## 11. Relation trong _links và _embedded

HAL sử dụng relation ở hai vị trí khác nhau:

- `_links`: relation đặt tên cho link object, giúp client điều hướng tới resource hoặc hành động.
- `_embedded`: relation đặt tên cho resource được nhúng trực tiếp trong response.

Ví dụ:

```json
{
  "_links": {
    "self": { "href": "/orders/42" },
    "customer": { "href": "/customers/7" }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Lan"
    }
  }
}
```

Relation `customer` xuất hiện trong cả hai vùng nhưng ý nghĩa biểu diễn khác nhau: trong `_links` nó dẫn tới URI khách hàng; trong `_embedded` nó đặt tên cho representation khách hàng được nhúng. Một collection relation như `orders` thường được dùng làm key trong `_embedded` để nhóm các item.

Tên relation nên nhất quán giữa link và embedded resource khi chúng nói về cùng một quan hệ, nhưng client vẫn cần hiểu cấu trúc JSON khác nhau của hai vùng.

## 12. Kiểm thử custom relation

Nên kiểm thử cả relation key được tạo và relation key sau khi serialize HAL. Ví dụ MockMvc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderResponseUsesMeaningfulRelationNames() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.customer.href", endsWith("/customers/7")))
                .andExpect(jsonPath("$._links.cancel.title").value("Hủy đơn hàng"));
    }

    @Test
    void orderCollectionUsesConfiguredCollectionRelation() throws Exception {
        mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._embedded.orders").isArray());
    }
}
```

Ví dụ giả định endpoint `/orders/42` trả relation `customer` và `cancel`, còn collection endpoint dùng representation có `@Relation(collectionRelation = "orders")`. Test cần fixture và service phù hợp với ứng dụng thực tế.

Với extension relation dùng URI đầy đủ hoặc CURIE, kiểm tra đúng relation key đã được serializer công bố. Nếu bật `CurieProvider`, kiểm tra cả khai báo `curies` và relation rút gọn tương ứng.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng URL làm relation | Relation thay đổi theo route và khó tái sử dụng. | Dùng tên relation hoặc URI định danh semantics. |
| Dùng relation chuẩn sai nghĩa | Client tổng quát hiểu sai liên kết. | Đối chiếu semantics trong IANA registry. |
| Dùng tên method như `getCustomer` | Relation gắn với implementation. | Dùng `customer` hoặc extension relation có nghĩa rõ. |
| Dùng chuỗi tiếng Việt làm relation | Client khó xử lý đa ngôn ngữ và relation thiếu ổn định. | Dùng relation ổn định; đưa câu chữ vào `title`. |
| Nhầm `@Relation` với `Link.withRel` | Tên collection không đổi hoặc link cụ thể không đúng. | Dùng annotation cho item/collection, `withRel` cho từng link. |
| Cho rằng `@Relation` tự tạo endpoint | Không có link hoặc route như mong đợi. | Khai báo controller/repository và tạo link riêng. |
| Bỏ qua extension relation URI | Relation custom không có định danh toàn cục. | Dùng URI relation và tài liệu hóa semantics. |
| Nhầm `title` hoặc `name` với relation | Client tìm sai key trong `_links`. | Relation là key; title/name là metadata của link object. |
| Đặt relation collection không nhất quán | Key `_embedded` khó dự đoán cho client. | Dùng `@Relation(collectionRelation = ...)`. |

## 14. Quy trình đặt tên relation

Khi thiết kế relation cho một API, thực hiện theo trình tự:

1. Xác định chính xác mối quan hệ hoặc hành động mà link đại diện.
2. Kiểm tra IANA registry xem có relation chuẩn phù hợp không.
3. Nếu không có, tạo extension relation URI ổn định và tài liệu hóa semantics.
4. Dùng `LinkRelation`/`IanaLinkRelations` để tập trung giá trị relation trong code.
5. Dùng `@Relation` để tùy chỉnh item relation và collection relation của representation type.
6. Inject `LinkRelationProvider` khi cần lấy relation theo kiểu thay vì tự suy ra tên.
7. Dùng `title` cho nhãn hiển thị và `name` để phân biệt link, không dùng chúng thay relation.
8. Nếu dùng HAL và URI relation dài, cân nhắc CURIE để rút gọn key.
9. Kiểm thử `_links`, `_embedded`, CURIE và relation key trong response thực tế.

Relation dễ hiểu giúp client nhận diện ý nghĩa liên kết độc lập với URL và cách triển khai. Khi dùng relation chuẩn đúng semantics, extension relation có URI ổn định và `@Relation` cho tên item/collection nhất quán, API HATEOAS sẽ dễ khám phá, dễ tích hợp và ít bị ràng buộc vào cấu trúc nội bộ của server.

## Tài liệu tham khảo

- [Spring HATEOAS – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – Relation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring HATEOAS – LinkRelationProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [Spring HATEOAS – LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [IANA – Link Relation Types registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
