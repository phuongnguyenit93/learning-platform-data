# rel của link

Trong hypermedia, `rel` (link relation) mô tả mối quan hệ giữa tài nguyên hiện tại và tài nguyên ở đích của một liên kết. `href` cho biết client đi tới đâu; `rel` giải thích liên kết đó có ý nghĩa gì. Ví dụ, từ một đơn hàng, link có `rel="customer"` dẫn tới khách hàng sở hữu đơn hàng, còn `rel="self"` dẫn tới chính đơn hàng hiện tại.

Spring HATEOAS dùng `Link` và `LinkRelation` để biểu diễn các liên kết này. Khi trả representation theo HAL, giá trị relation trở thành khóa trong `_links`. Client dựa vào quan hệ để khám phá tài nguyên, thay vì phải suy luận ý nghĩa từ cấu trúc URL.

## rel và href có vai trò khác nhau

Một link có thể được hiểu qua hai thành phần:

- **`rel`:** tên quan hệ giữa tài nguyên nguồn và tài nguyên đích.
- **`href`:** URI tham chiếu tới tài nguyên đích.

Ví dụ, response đơn hàng có các liên kết:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/ORD-2048"
    },
    "customer": {
      "href": "/api/customers/C-100"
    },
    "items": {
      "href": "/api/orders/ORD-2048/items"
    },
    "cancel": {
      "href": "/api/orders/ORD-2048/cancel"
    }
  }
}
```

Ở đây:

- `self` chỉ tài nguyên đơn hàng hiện tại.
- `customer` chỉ tài nguyên khách hàng liên quan tới đơn hàng.
- `items` chỉ tập hợp dòng hàng của đơn hàng.
- `cancel` công bố hướng tương tác hủy đơn hàng.

Client có thể tìm `_links.customer.href` để mở khách hàng, bất kể URL của khách hàng được tổ chức theo cấu trúc nào. Server có thể đổi đường dẫn mà vẫn giữ nguyên quan hệ `customer`, miễn là ý nghĩa và hợp đồng của quan hệ không đổi.

`rel` không phải HTTP method. Quan hệ `cancel` không tự cho client biết phải dùng `POST`, `DELETE` hay gửi payload nào. HAL cơ bản biểu diễn quan hệ và đích liên kết; nếu client cần khám phá method, kiểu nội dung hoặc các trường đầu vào, API cần công bố thêm affordance qua media type phù hợp như HAL-FORMS.

## Quan hệ chuẩn được đăng ký với IANA

IANA duy trì danh mục các link relation types chuẩn để nhiều API và client có thể hiểu thống nhất. Khi một quan hệ chuẩn phù hợp với ý nghĩa cần biểu đạt, nên ưu tiên sử dụng quan hệ đó thay vì tự đặt tên mới.

Một số quan hệ thường gặp:

| rel | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `self` | Tài nguyên hiện tại | Link chính của representation |
| `next` | Phần tiếp theo | Trang kế tiếp trong collection phân trang |
| `prev` | Phần trước | Trang trước đó |
| `first` | Phần đầu tiên | Trang đầu của tập hợp |
| `last` | Phần cuối cùng | Trang cuối của tập hợp |
| `alternate` | Biểu diễn thay thế | Một định dạng hoặc cách trình bày khác của tài nguyên |
| `author` | Tác giả | Tài nguyên tác giả của nội dung hiện tại |
| `related` | Tài nguyên liên quan | Một tài nguyên có liên hệ với tài nguyên hiện tại |
| `describedby` | Tài liệu mô tả | Schema hoặc tài liệu giải thích tài nguyên |
| `collection` | Collection chứa tài nguyên | Tập hợp mà tài nguyên hiện tại thuộc về |
| `search` | Điểm tìm kiếm | Endpoint hỗ trợ tìm kiếm tài nguyên |
| `up` | Tài nguyên cấp trên | Tài nguyên cha hoặc cấp cao hơn trong cấu trúc điều hướng |

Danh mục đầy đủ được công bố trong IANA Link Relation Types Registry. Ý nghĩa của một relation đã đăng ký cần được giữ đúng; không tái sử dụng `author` để chỉ người phê duyệt hoặc dùng `next` cho một thao tác không liên quan đến phần tiếp theo.

## Quan hệ mở rộng do API định nghĩa

Khi không có relation chuẩn phù hợp, API có thể định nghĩa quan hệ mở rộng (extension relation type). Theo quy tắc của Web Linking, relation mở rộng nên dùng một URI tuyệt đối để tránh trùng tên và giúp client có thể nhận diện ngữ nghĩa trên nhiều hệ thống.

Ví dụ, API bán hàng định nghĩa quan hệ dẫn tới hóa đơn:

```text
https://api.example.com/rels/invoice
```

URI này đóng vai trò định danh quan hệ. Nhóm phát triển có thể cung cấp tài liệu tại URI đó để mô tả ý nghĩa, điều kiện xuất hiện và cách sử dụng relation. URI relation không nhất thiết phải là URL endpoint của hóa đơn; đích của liên kết vẫn nằm trong `href`.

Phân biệt hai URI sau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Relation URI | `https://api.example.com/rels/invoice` | Định danh ý nghĩa của mối quan hệ |
| Link target (`href`) | `/api/orders/ORD-2048/invoice` | Địa chỉ tài nguyên đích |

Với API nội bộ có một nhóm client được kiểm soát, các tên ngắn như `invoice` có thể được thống nhất trong hợp đồng riêng. Với API công khai hoặc tích hợp nhiều tổ chức, URI quan hệ mở rộng giúp tránh va chạm tên và làm rõ nơi công bố định nghĩa.

## Dùng rel trong Spring HATEOAS

Spring HATEOAS cung cấp `LinkRelation` để biểu diễn relation dưới dạng kiểu dữ liệu riêng. Có thể tạo link từ mapping controller bằng `WebMvcLinkBuilder`:

```java
import org.springframework.hateoas.LinkRelation;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link customerLink = linkTo(
        methodOn(OrderController.class).customer(orderId)
).withRel("customer");

Link invoiceLink = linkTo(
        methodOn(OrderController.class).invoice(orderId)
).withRel(LinkRelation.of(
        "https://api.example.com/rels/invoice"
));
```

`withRel("customer")` dùng tên quan hệ ngắn đã được API thống nhất. `LinkRelation.of(...)` tạo một relation từ chuỗi, phù hợp khi muốn dùng URI quan hệ mở rộng. Các phương thức `customer(...)` và `invoice(...)` là các endpoint minh họa cần được khai báo trong controller.

Quan hệ chuẩn có thể dùng các hằng trong `IanaLinkRelations`:

```java
import org.springframework.hateoas.IanaLinkRelations;

Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withRel(IanaLinkRelations.SELF);

Link next = linkTo(methodOn(OrderController.class).page(1))
        .withRel(IanaLinkRelations.NEXT);
```

Với link tự trỏ, `withSelfRel()` là cách viết ngắn và dễ đọc:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

Sử dụng hằng `IanaLinkRelations` giúp tránh lỗi đánh máy và làm rõ rằng relation thuộc danh mục chuẩn. Với relation riêng, hãy tập trung tên và định nghĩa ở một nơi, ví dụ hằng số hoặc lớp tiện ích:

```java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    public static final LinkRelation INVOICE = LinkRelation.of(
            "https://api.example.com/rels/invoice");

    public static final LinkRelation CUSTOMER = LinkRelation.of("customer");

    private ApiRelations() {}
}
```

Khi đó assembler dùng `ApiRelations.INVOICE` thay vì lặp lại chuỗi quan hệ ở nhiều nơi. Điều này giúp thay đổi định nghĩa có kiểm soát và giảm nguy cơ mỗi endpoint sử dụng một tên khác nhau cho cùng một ý nghĩa.

## Chọn rel có ngữ nghĩa rõ ràng

Một relation tốt phải giúp client hiểu quan hệ mà không cần phân tích URL. Khi thiết kế tên relation, cần cân nhắc:

1. **Diễn tả quan hệ từ tài nguyên hiện tại tới đích.** `customer` cho biết khách hàng liên quan; `items` cho biết tập hợp dòng hàng.
2. **Ưu tiên relation chuẩn khi đúng ý nghĩa.** Dùng `self`, `next`, `prev` hoặc `author` theo đúng định nghĩa của chúng.
3. **Định nghĩa URI cho quan hệ mở rộng khi cần liên thông.** Tránh dùng một token ngắn có thể trùng với cách đặt tên của API khác.
4. **Giữ ngữ nghĩa ổn định.** Nếu `invoice` hôm nay dẫn tới hóa đơn của đơn hàng, không đổi nó thành tài liệu vận chuyển ở phiên bản sau.
5. **Tài liệu hóa quan hệ riêng.** Mô tả ý nghĩa, khi nào xuất hiện, loại tài nguyên đích và cách client sử dụng.

Relation nên mô tả mối quan hệ, còn trạng thái và quyền quyết định link có được công bố trong response hay không. Ví dụ, hai đơn hàng có thể đều hiểu `cancel` là quan hệ hủy, nhưng server chỉ thêm link đó cho đơn hàng đang chờ xử lý và người dùng có quyền hủy.

## CURIE trong HAL để rút gọn URI relation

URI quan hệ mở rộng có thể dài. HAL hỗ trợ CURIE (Compact URI Expression) để biểu diễn chúng bằng một tiền tố ngắn trong tên relation. Ví dụ `ex:invoice` có thể đại diện cho URI `https://api.example.com/rels/invoice`.

Một HAL response có thể khai báo CURIE trong `_links`:

```json
{
  "_links": {
    "self": {
      "href": "/api/orders/ORD-2048"
    },
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:invoice": {
      "href": "/api/orders/ORD-2048/invoice"
    }
  }
}
```

Client có thể mở rộng `ex:invoice` bằng cách thay `{rel}` trong URI template, từ đó xác định URI quan hệ đầy đủ. CURIE giúp response ngắn hơn trong khi vẫn giữ định danh toàn cục của quan hệ.

Spring HATEOAS hỗ trợ `CurieProvider` cho HAL. Có thể khai báo một `DefaultCurieProvider` để ánh xạ tiền tố tới URI template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;
import org.springframework.web.util.UriTemplate;

@Configuration
public class HalConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "ex",
                new UriTemplate("https://api.example.com/rels/{rel}")
        );
    }
}
```

Khi có CURIE provider, relation URI có thể được hiển thị dưới dạng quan hệ rút gọn theo cấu hình HAL. Hãy thống nhất tiền tố và URI template với client; không thay đổi cách mở rộng một tiền tố khi client đang phụ thuộc vào nó.

## rel trong collection và embedded resources

Trong HAL collection, `collectionRelation` đặt tên quan hệ cho danh sách phần tử trong `_embedded`. `@Relation` của Spring HATEOAS có thể xác định tên này cùng với tên relation của từng phần tử:

```java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {
    // Các trường dữ liệu của đơn hàng.
}
```

Với cấu hình này, HAL collection sử dụng `_embedded.orders` để chứa các phần tử. Đây là quan hệ của collection/embedded resource, khác với link relation của các link trong `_links`. Nên đặt cả collection relation và các link relation sao cho nhất quán về ngữ nghĩa.

## Kiểm thử rel trong response

Kiểm thử hợp đồng nên xác nhận quan hệ xuất hiện đúng tên và đúng điều kiện. Với MockMvc, có thể kiểm tra link chuẩn và link mở rộng:

```java
mockMvc.perform(get("/api/orders/{id}", pendingOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Nếu API dùng URI relation mở rộng trong HAL, hãy kiểm tra đúng khóa relation hoặc CURIE đã công bố:

```java
mockMvc.perform(get("/api/orders/{id}", paidOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['https://api.example.com/rels/invoice'].href")
            .exists());
```

Nếu response sử dụng CURIE, kiểm tra cả khai báo `curies` và quan hệ rút gọn như `ex:invoice`. Với đơn hàng không thể hủy, kiểm tra `cancel` không xuất hiện. Các kiểm thử này phát hiện việc đổi tên relation ngoài ý muốn, thay đổi ngữ nghĩa hoặc công bố link không đúng trạng thái.

## Những lỗi thường gặp khi thiết kế rel

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Xem `rel` là một phần của URL | Client phụ thuộc cấu trúc đường dẫn | Phân biệt relation và `href` |
| Dùng relation chuẩn sai ý nghĩa | Client hiểu sai quan hệ | Tuân thủ định nghĩa trong IANA registry |
| Dùng tên ngắn trùng giữa các API | Khó tích hợp và có thể xung đột | Dùng URI relation mở rộng cho hợp đồng liên thông |
| Thay đổi ý nghĩa của relation đã công bố | Client cũ xử lý sai | Giữ ngữ nghĩa ổn định hoặc tạo relation mới |
| Cho rằng `cancel` mô tả HTTP method | Client không biết cách gửi request | Công bố affordance khi cần method và payload |
| Không tài liệu hóa relation riêng | Client không biết ý nghĩa và điều kiện sử dụng | Cung cấp định nghĩa quan hệ rõ ràng |
| Dùng CURIE nhưng không công bố tiền tố | Client không mở rộng được URI relation | Trả khai báo `curies` theo HAL |

## Quy trình chọn và sử dụng rel

Khi thêm một link vào representation, hãy thực hiện theo trình tự:

1. Xác định tài nguyên hiện tại và tài nguyên đích.
2. Mô tả mối quan hệ giữa hai tài nguyên bằng một tên có ý nghĩa.
3. Kiểm tra IANA registry để xem đã có relation chuẩn phù hợp chưa.
4. Nếu cần quan hệ mở rộng, chọn URI tuyệt đối và công bố tài liệu định nghĩa.
5. Dùng `IanaLinkRelations` hoặc `LinkRelation.of(...)` trong Spring HATEOAS.
6. Tạo `href` theo mapping controller bằng `linkTo(methodOn(...))`.
7. Kiểm thử tên relation, ngữ nghĩa, điều kiện xuất hiện và khả năng tương thích của client.

## Kết luận

`rel` là phần mô tả ý nghĩa của một liên kết hypermedia, còn `href` là đích truy cập. Chọn relation chuẩn từ IANA khi phù hợp; với quan hệ riêng, dùng định danh mở rộng có URI và giữ ngữ nghĩa ổn định. Spring HATEOAS cung cấp `IanaLinkRelations`, `LinkRelation` và các API tạo link để biểu diễn quan hệ nhất quán. Khi cần rút gọn URI relation trong HAL, CURIE giúp công bố tên ngắn mà vẫn giữ được định danh đầy đủ. Kiểm thử quan hệ trong `_links` bảo vệ hợp đồng điều hướng mà client sử dụng.
