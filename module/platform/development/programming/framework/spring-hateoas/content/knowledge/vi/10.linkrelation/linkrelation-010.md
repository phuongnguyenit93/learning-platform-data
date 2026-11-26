# Quản lý relation nhất quán

Trong một REST API dùng Spring HATEOAS, link relation (`rel`) là tên mô tả mối quan hệ giữa tài nguyên hiện tại và đích của liên kết. Khi nhiều controller và assembler cùng tạo link, các relation cần được quản lý thống nhất để client có thể nhận diện cùng một ý nghĩa ở mọi response.

Spring HATEOAS cung cấp `LinkRelation` như một kiểu dữ liệu dành riêng cho relation, cùng `IanaLinkRelations` cho các quan hệ chuẩn. Thay vì rải chuỗi như `"customer"`, `"invoice"` hoặc `"cancel"` trong nhiều lớp, ứng dụng có thể định nghĩa một vocabulary tập trung, dùng lại trong assembler và kiểm thử hợp đồng. Cách làm này giúp giảm lỗi đánh máy, ngăn các tên khác nhau cùng biểu thị một ý nghĩa và giữ ổn định giao kèo hypermedia khi API phát triển.

## Vì sao cần quản lý relation nhất quán?

Giả sử API bán hàng có các tài nguyên `Order`, `Invoice` và `Customer`. Nhiều endpoint có thể tạo liên kết tới cùng một loại tài nguyên. Nếu nhóm phát triển dùng `customer`, `client`, `buyer` và `customer-info` tùy nơi, client sẽ phải hiểu nhiều tên cho cùng một quan hệ.

Một vocabulary thống nhất giúp:

- **Client dễ khám phá:** cùng một ý nghĩa được công bố bằng cùng relation ở các response liên quan.
- **Giảm lỗi do chuỗi:** hằng số hoặc kiểu `LinkRelation` hạn chế lỗi chính tả và khác biệt cách viết.
- **Dễ thay đổi có kiểm soát:** nhóm phát triển có một nơi để xem relation nào đang được API công bố.
- **Kiểm thử hợp đồng rõ ràng:** test có thể xác nhận relation quan trọng xuất hiện đúng điều kiện.
- **Hỗ trợ nhiều nhóm phát triển:** controller, assembler và module con dùng chung quy ước.

Ví dụ, API có thể thống nhất vocabulary như sau:

| Relation | Ý nghĩa thống nhất | Ví dụ sử dụng |
|---|---|---|
| `self` | Tài nguyên hiện tại | Link của một đơn hàng |
| `customer` | Khách hàng liên quan tới tài nguyên | Từ đơn hàng tới khách hàng |
| `orders` | Tập hợp đơn hàng | Từ khách hàng tới danh sách đơn hàng |
| `invoice` | Hóa đơn của tài nguyên | Từ đơn hàng tới hóa đơn |
| `cancel` | Hướng tương tác hủy đơn | Từ đơn hàng đang chờ xử lý |
| `next` | Phần tiếp theo của collection | Trang kế tiếp |

Quan hệ phải được hiểu từ tài nguyên nguồn. `customer` có thể được dùng trên đơn hàng và hóa đơn nếu cả hai đều dẫn tới khách hàng có liên quan. Nếu hai liên kết có ngữ nghĩa khác nhau, hãy đặt relation khác nhau và mô tả rõ sự khác biệt.

## LinkRelation là gì?

`LinkRelation` là kiểu giá trị của Spring HATEOAS đại diện cho tên quan hệ. Có thể tạo relation từ một chuỗi bằng `LinkRelation.of(...)`:

```java
import org.springframework.hateoas.LinkRelation;

LinkRelation customer = LinkRelation.of("customer");
LinkRelation invoice = LinkRelation.of("invoice");
```

Sau khi có relation, dùng nó khi tạo link:

```java
Link customerLink = linkTo(
        methodOn(OrderController.class).customer(orderId)
).withRel(customer);
```

`LinkRelation` giúp biểu đạt relation bằng một kiểu chuyên biệt thay vì truyền chuỗi tùy ý qua các lớp. Nó không tự tạo URL và cũng không kiểm tra rằng endpoint có tồn tại. Đích liên kết vẫn được tạo riêng, thường bằng `linkTo(methodOn(...))`; relation chỉ định nghĩa ý nghĩa của liên kết.

## Dùng IanaLinkRelations cho quan hệ chuẩn

Các relation chuẩn đã được đăng ký trong IANA Link Relation Types Registry. Spring HATEOAS cung cấp `IanaLinkRelations` để dùng các tên chuẩn mà không cần tự gõ chuỗi.

Ví dụ:

```java
import org.springframework.hateoas.IanaLinkRelations;

Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withRel(IanaLinkRelations.SELF);

Link next = linkTo(methodOn(OrderController.class).page(1))
        .withRel(IanaLinkRelations.NEXT);
```

Với link tự trỏ, `withSelfRel()` là cách viết ngắn gọn:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

Chỉ dùng relation chuẩn khi ý nghĩa thực tế khớp định nghĩa của nó. Ví dụ, `next` dành cho phần tiếp theo trong một chuỗi điều hướng; không nên dùng `next` để biểu thị thao tác thanh toán. Nếu không có relation chuẩn phù hợp, định nghĩa một relation mở rộng.

## Tạo vocabulary relation dùng chung

Với relation riêng của ứng dụng, nên gom các định nghĩa vào một lớp hoặc package chuyên trách. Ví dụ:

```java
package com.example.api.hypermedia;

import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    public static final LinkRelation CUSTOMER =
            LinkRelation.of("customer");

    public static final LinkRelation ORDERS =
            LinkRelation.of("orders");

    public static final LinkRelation INVOICE =
            LinkRelation.of("https://api.example.com/rels/invoice");

    public static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.com/rels/cancel");

    private ApiRelations() {
    }
}
```

Lớp `ApiRelations` là vocabulary của API. Relation ngắn như `customer` hoặc `orders` phù hợp khi client và server cùng tuân theo một hợp đồng nội bộ đã thống nhất. Với API công khai hoặc có nhiều tổ chức tích hợp, relation mở rộng nên dùng URI tuyệt đối để tránh xung đột tên và cung cấp định danh toàn cục. URI định danh relation không nhất thiết là URL endpoint; `href` của link vẫn là địa chỉ tài nguyên đích.

Không nên tạo một lớp hằng số khổng lồ chứa mọi chuỗi của ứng dụng. Khi API lớn, có thể chia vocabulary theo miền như `OrderRelations`, `CustomerRelations` và `CatalogRelations`, nhưng cần có quy tắc đặt tên chung và tránh định nghĩa trùng lặp. Chỉ tách lớp khi các nhóm relation thực sự có phạm vi và người sở hữu khác nhau.

## Sử dụng vocabulary trong assembler

Assembler là nơi thích hợp để chuyển đối tượng miền thành representation và thêm các link theo quy tắc nghiệp vụ. Dùng relation đã định nghĩa giúp các assembler cùng công bố một hợp đồng thống nhất.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        var id = order.getId();

        EntityModel<OrderResponse> model = EntityModel.of(
                new OrderResponse(id, order.getStatus().name(), order.getTotal()),
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
                linkTo(methodOn(OrderController.class).customer(id))
                        .withRel(ApiRelations.CUSTOMER)
        );

        if (order.hasInvoice()) {
            model.add(linkTo(methodOn(OrderController.class).invoice(id))
                    .withRel(ApiRelations.INVOICE));
        }

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel(ApiRelations.CANCEL));
        }

        return model;
    }
}
```

Các phương thức `customer(...)`, `invoice(...)` và `cancel(...)` là endpoint minh họa của controller. Assembler dùng vocabulary chung cho mọi đơn hàng. Link `invoice` và `cancel` chỉ xuất hiện khi điều kiện nghiệp vụ tương ứng đúng. Việc dùng relation tập trung không thay thế kiểm tra quyền và trạng thái ở endpoint khi request được gửi tới.

Nếu một relation được sử dụng trong nhiều assembler, tất cả nơi sử dụng đều nên tham chiếu cùng một định nghĩa. Khi thay đổi relation, nhóm phát triển có thể tìm các điểm sử dụng qua tên hằng thay vì phải rà từng chuỗi literal.

## Dùng relation để kiểm tra link trên model

`RepresentationModel` cung cấp các phương thức kiểm tra và truy xuất link theo relation. Có thể dùng chính vocabulary đã định nghĩa để tránh kiểm tra bằng chuỗi rải rác:

```java
boolean hasCustomer = model.hasLink(ApiRelations.CUSTOMER);
boolean hasInvoice = model.hasLink(ApiRelations.INVOICE);

Optional<Link> invoiceLink = model.getLink(ApiRelations.INVOICE);
```

`hasLink(...)` hữu ích khi muốn xác nhận model có công bố một khả năng. `getLink(...)` trả về `Optional`, phù hợp với link chỉ xuất hiện theo trạng thái. Với relation luôn phải tồn tại theo hợp đồng, có thể dùng `getRequiredLink(...)` để nhận lỗi rõ ràng nếu model thiếu link.

Không nên dùng `getRequiredLink(...)` cho relation tùy chọn như `cancel` hoặc `invoice` nếu các link này chỉ xuất hiện khi điều kiện nghiệp vụ được thỏa mãn.

## Phân biệt LinkRelation với collection relation

Trong HAL, tên khóa trong `_links` là link relation. Tên khóa trong `_embedded` là collection relation dùng để xác định tập hợp representation được nhúng. Hai khái niệm liên quan nhưng có mục đích khác nhau.

Ví dụ:

```java
@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {
    // Nội dung representation của đơn hàng.
}
```

`collectionRelation = "orders"` đặt tên cho danh sách nhúng trong `_embedded`. Một link từ khách hàng tới danh sách đơn hàng vẫn có thể dùng `ApiRelations.ORDERS` trong `_links`. Nên thống nhất cách gọi giữa hai vị trí, nhưng không nhầm `@Relation` với `LinkRelation`: annotation điều khiển tên relation cho representation/collection, còn `LinkRelation` biểu diễn relation của một link.

## Quản lý thay đổi relation và tương thích client

Relation là một phần của hợp đồng API. Client thường tìm link bằng relation, vì vậy đổi tên hoặc thay đổi ngữ nghĩa của relation có thể làm client cũ không còn khám phá được khả năng.

Một số nguyên tắc khi thay đổi:

1. **Không tái sử dụng tên cũ cho ý nghĩa mới.** Nếu `invoice` từng là hóa đơn, không đổi nó thành phiếu giao hàng.
2. **Giữ relation cũ trong giai đoạn chuyển tiếp khi cần.** Có thể công bố cả relation cũ và mới trong thời gian client được nâng cấp, nếu hai relation trỏ tới cùng một khả năng và việc duy trì cả hai không gây mơ hồ.
3. **Định nghĩa relation mới khi ngữ nghĩa thay đổi.** Relation mới có tên hoặc URI riêng để client phân biệt rõ.
4. **Tài liệu hóa vòng đời relation.** Ghi rõ relation được thêm, thay thế hoặc ngừng công bố từ phiên bản nào.
5. **Kiểm thử các client contract quan trọng.** Bảo đảm relation thiết yếu vẫn xuất hiện và link vẫn trỏ tới đúng tài nguyên.

Đổi `href` không nhất thiết làm thay đổi hợp đồng nếu `rel` và ngữ nghĩa được giữ nguyên. Đây là một trong các lợi ích của hypermedia: client theo quan hệ và URL server cung cấp, thay vì tự ghép đường dẫn. Tuy nhiên, thay đổi nội dung tài nguyên, media type hoặc hành vi endpoint vẫn có thể ảnh hưởng client và cần được quản lý riêng.

## Kiểm thử vocabulary relation

Kiểm thử nên xác nhận cả relation và điều kiện xuất hiện của link. Ví dụ với MockMvc:

```java
mockMvc.perform(get("/api/orders/{id}", pendingOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._links['https://api.example.com/rels/cancel'].href")
            .exists());
```

Với đơn hàng đã giao, kiểm tra link `cancel` không xuất hiện:

```java
mockMvc.perform(get("/api/orders/{id}", deliveredOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links['https://api.example.com/rels/cancel']")
            .doesNotExist());
```

Nếu API dùng relation ngắn `customer`, test có thể kiểm tra `_links.customer.href`. Nếu dùng URI relation mở rộng, cần kiểm tra đúng tên relation hoặc CURIE mà HAL công bố. Các kiểm thử này giúp phát hiện thay đổi ngoài ý muốn trong vocabulary, nhưng cũng nên có kiểm thử riêng cho endpoint đích để xác nhận link dẫn tới tài nguyên thực sự truy cập được.

## Những lỗi thường gặp khi quản lý relation

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Rải chuỗi `rel` trong nhiều assembler | Dễ sai chính tả và không đồng nhất | Tập trung trong vocabulary dùng chung |
| Dùng nhiều tên cho cùng ý nghĩa | Client phải hỗ trợ nhiều trường hợp | Chọn một relation ổn định cho mỗi ngữ nghĩa |
| Dùng relation chuẩn sai định nghĩa | Client diễn giải sai liên kết | Dùng `IanaLinkRelations` đúng ngữ cảnh |
| Dùng tên ngắn trong tích hợp công khai mà không có quy ước | Có nguy cơ trùng tên | Dùng URI relation mở rộng |
| Đổi ý nghĩa relation đã phát hành | Phá vỡ hành vi client | Tạo relation mới và quản lý chuyển tiếp |
| Dùng `getRequiredLink` với link tùy chọn | Có thể phát sinh lỗi khi link vắng mặt hợp lệ | Dùng `getLink` hoặc `hasLink` |
| Nhầm collection relation với link relation | Đặt tên sai vị trí trong HAL | Phân biệt `@Relation` và `LinkRelation` |

## Quy trình quản lý relation trong dự án

Khi thêm relation mới, nhóm phát triển có thể theo quy trình sau:

1. Xác định rõ tài nguyên nguồn, tài nguyên đích và ý nghĩa quan hệ.
2. Kiểm tra IANA registry để xem có relation chuẩn phù hợp không.
3. Nếu là relation riêng, chọn tên thống nhất; dùng URI tuyệt đối khi cần liên thông giữa nhiều hệ thống.
4. Thêm relation vào vocabulary dùng chung như `ApiRelations`.
5. Dùng relation đó trong assembler hoặc nơi tạo link, tránh tạo chuỗi literal mới.
6. Cập nhật tài liệu hợp đồng và quy tắc khi link xuất hiện.
7. Thêm kiểm thử xác nhận relation, đích link và điều kiện nghiệp vụ.
8. Khi thay đổi relation đã phát hành, lập kế hoạch tương thích và chuyển tiếp cho client.

## Kết luận

Quản lý relation nhất quán giúp API hypermedia có vocabulary ổn định để client khám phá tài nguyên và hành động. Spring HATEOAS cung cấp `LinkRelation` cho relation riêng và `IanaLinkRelations` cho quan hệ chuẩn. Tập trung định nghĩa relation trong một vocabulary, tái sử dụng trong assembler, phân biệt link relation với collection relation và kiểm thử hợp đồng giúp hạn chế lỗi, đồng thời hỗ trợ API tiến hóa mà không làm client phụ thuộc vào tên URL nội bộ.
