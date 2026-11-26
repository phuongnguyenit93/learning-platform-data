# Tạo link bất biến trong Spring HATEOAS

Trong Spring HATEOAS, `Link` là một value object bất biến đại diện cho một liên kết hypermedia. Sau khi tạo, không thể thay đổi trực tiếp URI, relation hay metadata của chính đối tượng đó. Các phương thức có tiền tố `with` như `withRel`, `withTitle` hoặc `withType` tạo và trả về một `Link` mới mang giá trị đã điều chỉnh.

Cách thiết kế này giúp mã tạo liên kết dễ dự đoán: một link đã được chia sẻ vẫn giữ nguyên giá trị, còn mỗi biến thể được lưu thành một đối tượng riêng. Cần phân biệt tính bất biến của đối tượng `Link` với độ bền vững của URI đích. Một `Link` bất biến không khiến tài nguyên ở URI đó trở thành bất biến hoặc bảo đảm URI sẽ tồn tại mãi mãi.

## 1. Link là một value object

Một liên kết hypermedia có URI đích và relation mô tả ý nghĩa của liên kết. Spring HATEOAS biểu diễn nó bằng lớp `org.springframework.hateoas.Link`.

Ví dụ tạo liên kết đến một đơn hàng:

```java
import org.springframework.hateoas.Link;

Link orderLink = Link.of("/orders/42", "self");
```

Hai thành phần chính:

- `href`: URI mà máy khách có thể truy cập.
- `rel`: quan hệ cho biết liên kết đại diện cho điều gì, ví dụ `self`, `collection`, `next` hoặc một relation nghiệp vụ do API định nghĩa.

Link có thể chứa metadata bổ sung như tiêu đề, media type, ngôn ngữ, tên hoặc thông tin deprecation. Những giá trị này giúp máy khách hiểu ngữ cảnh và cách sử dụng liên kết.

`Link` thuộc tầng biểu diễn HTTP. Nó không phải entity JPA, không giữ trạng thái nghiệp vụ và không thực hiện request thay cho máy khách.

## 2. Vì sao Link bất biến?

Đối tượng bất biến không cho phép thay đổi trạng thái sau khi được tạo. Thay vì cung cấp setter để sửa trực tiếp một instance, Spring HATEOAS cung cấp các phương thức `with...` trả về instance mới.

Ví dụ, tạo một link ban đầu rồi tạo phiên bản có relation khác:

```java
Link original = Link.of("/orders/42", "item");

Link selfLink = original.withRel("self");
```

Sau lời gọi `withRel`:

- `original` vẫn giữ relation `item`.
- `selfLink` có cùng URI nhưng relation là `self`.
- Hai biến tham chiếu đến hai giá trị Link riêng biệt.

Có thể tiếp tục tạo biến thể mới mà không ảnh hưởng đến các biến thể trước đó:

```java
Link original = Link.of("/orders/42", "self");

Link titledLink = original.withTitle("Order details");

Link typedLink = titledLink.withType("application/hal+json");
```

`titledLink` có tiêu đề; `typedLink` giữ tiêu đề đó và bổ sung media type. `original` vẫn là link ban đầu.

Đây là lý do nên gán kết quả trả về của phương thức `with...` vào biến hoặc truyền nó tiếp vào biểu thức. Nếu chỉ gọi phương thức mà bỏ qua kết quả, link ban đầu không được cập nhật:

```java
Link link = Link.of("/orders/42", "self");

// Kết quả mới bị bỏ đi; biến link vẫn giữ giá trị ban đầu.
link.withTitle("Order details");
```

Hãy viết:

```java
link = link.withTitle("Order details");
```

Lệnh gán chỉ thay đổi biến đang tham chiếu đến đối tượng nào. Nó không sửa đối tượng Link cũ.

## 3. Các phương thức with thường dùng

Các phương thức `with...` tạo ra một Link mới với một thuộc tính được thay đổi hoặc bổ sung.

| Phương thức | Tác dụng |
|---|---|
| `withRel(...)` | Gán relation khác |
| `withHref(...)` | Tạo link với URI đích khác |
| `withTitle(...)` | Bổ sung hoặc thay tiêu đề |
| `withType(...)` | Bổ sung hoặc thay media type |
| `withHreflang(...)` | Bổ sung ngôn ngữ của tài nguyên đích |
| `withName(...)` | Gán tên cho liên kết |
| `withDeprecation(...)` | Cung cấp URI mô tả tình trạng deprecation |
| `withProfile(...)` | Gắn URI profile mô tả semantics của biểu diễn |
| `withMedia(...)` | Gắn thông tin media |
| `withTemplated(...)` | Đặt trạng thái URI template |

Ví dụ kết hợp metadata:

```java
Link documentation = Link.of(
        "https://api.example.com/docs/orders",
        "describedby"
    )
    .withTitle("Order API documentation")
    .withType("text/html")
    .withHreflang("vi");
```

Mỗi bước trả về một Link mới. Có thể nối các lời gọi để tạo giá trị cuối cùng hoặc tách thành nhiều biến nếu cần tái sử dụng từng phiên bản.

Chỉ thêm metadata có ý nghĩa với hợp đồng API. Ví dụ `type` nên phản ánh media type thực tế của tài nguyên đích; `hreflang` nên phản ánh ngôn ngữ được cung cấp.

## 4. Dùng relation chuẩn và relation mở rộng

Relation cho biết ý nghĩa của liên kết. Với relation đã được đăng ký, nên dùng hằng số của `IanaLinkRelations` để tránh sai chính tả:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42")
    .withRel(IanaLinkRelations.SELF);

Link collection = Link.of("/orders")
    .withRel(IanaLinkRelations.COLLECTION);
```

Các relation thường gặp gồm:

- `self`: tài nguyên hiện tại.
- `collection`: tập hợp chứa hoặc liên quan đến tài nguyên.
- `next`, `prev`: trang tiếp theo và trang trước.
- `first`, `last`: trang đầu và trang cuối.
- `related`: tài nguyên có liên quan.

Với quan hệ nghiệp vụ riêng như hủy đơn hoặc thanh toán, API cần định nghĩa semantics rõ ràng và duy trì relation ổn định. Trong HAL, relation mở rộng nên được biểu diễn bằng URI relation hoặc CURIE theo quy ước của định dạng.

```java
private static final String CANCEL_REL =
    "https://api.example.com/rels/cancel";

Link cancel = Link.of("/orders/42/cancel")
    .withRel(CANCEL_REL)
    .withTitle("Cancel this order");
```

Máy khách có thể dựa vào relation đã được tài liệu hóa để nhận biết ý nghĩa liên kết. URI trong `href` cho biết đích đến cụ thể; relation cho biết máy khách đang nhìn vào loại điều hướng nào.

## 5. Phân biệt Link với LinkBuilder

`Link` là kết quả biểu diễn liên kết. `WebMvcLinkBuilder` là công cụ tạo URI dựa trên mapping của controller Spring MVC.

Ví dụ:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
```

Lời gọi `linkTo(...)` và `methodOn(...)` giúp Spring HATEOAS xác định URI theo mapping và tham số của controller. `withSelfRel()` hoàn tất quá trình xây dựng và trả về một `Link`.

Nếu cần bổ sung metadata, tiếp tục trên kết quả Link:

```java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
)
    .withSelfRel()
    .withTitle("Order details");
```

Nên xem builder là công cụ phục vụ quá trình tạo link, còn Link là giá trị đã được tạo để gắn vào representation, lưu trữ hoặc tuần tự hóa. Không nên nhầm việc tạo một builder với việc đã có một Link hoàn chỉnh.

## 6. Gắn Link bất biến vào RepresentationModel

Các representation model của Spring HATEOAS như `RepresentationModel`, `EntityModel` và `CollectionModel` có thể chứa các Link.

Ví dụ dùng DTO và EntityModel:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

OrderDto dto = new OrderDto(42L, "PENDING", total);

Link self = Link.of("/orders/42", "self");
Link collection = Link.of("/orders", "collection");

EntityModel<OrderDto> model = EntityModel.of(dto);
model.add(self);
model.add(collection);
```

Mỗi Link được tạo độc lập và có thể được tái sử dụng. `EntityModel` cung cấp API `add` để tập hợp các liên kết trong lúc xây dựng biểu diễn.

Điểm cần phân biệt: tính bất biến đang nói đến đối tượng `Link`. Việc thêm hoặc tổ chức các liên kết trên representation model là thao tác xây dựng model. Không nên suy ra rằng toàn bộ `EntityModel` hoặc controller response đều bất biến chỉ vì các Link bên trong là immutable value object.

## 7. Tái sử dụng Link an toàn

Vì Link không bị sửa tại chỗ, có thể tái sử dụng một giá trị chung trong nhiều representation khi URI và semantics của nó thực sự giống nhau.

Ví dụ một liên kết tài liệu API dùng chung:

```java
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
public class ApiDocumentationLinks {

    private static final Link ORDER_DOCUMENTATION =
        Link.of(
            "https://api.example.com/docs/orders",
            "describedby"
        ).withTitle("Order API documentation");

    public Link orderDocumentation() {
        return ORDER_DOCUMENTATION;
    }
}
```

Mỗi lần gọi trả về cùng một giá trị Link bất biến. Một representation có thể thêm nó mà không làm thay đổi giá trị mà representation khác sử dụng.

Nếu cần tạo URI phụ thuộc vào ID, tenant, người dùng hoặc request hiện tại, hãy tạo Link riêng cho ngữ cảnh đó. Không dùng một hằng số chung cho URL có dữ liệu động.

Việc chia sẻ một Link bất biến cũng không có nghĩa URI đích luôn truy cập được. Tài nguyên đích có thể bị xóa, chuyển hướng, thay đổi quyền hoặc thay đổi nội dung theo thời gian.

## 8. Link bất biến không đồng nghĩa URI bất biến

Cụm từ “link bất biến” có thể bị hiểu theo hai nghĩa khác nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| Immutable Link object | Đối tượng Link không thể bị sửa tại chỗ; các phương thức `with...` trả về Link mới |
| Stable/permanent URI | URI được duy trì ổn định trong hợp đồng để máy khách có thể tiếp tục sử dụng |

Spring HATEOAS bảo đảm mô hình giá trị bất biến của đối tượng Link. Việc duy trì URI lâu dài là trách nhiệm thiết kế và vận hành API.

Ví dụ, một Link có thể không thay đổi:

```java
Link payment = Link.of(
    "https://api.example.com/payments/91",
    "payment"
);
```

Nhưng sau đó máy chủ có thể ngừng cung cấp URI đó hoặc thay đổi quyền truy cập. Đối tượng Link ở phía ứng dụng vẫn giữ chuỗi URI đã tạo; điều đó không bảo đảm request tới URI sẽ thành công.

Để hỗ trợ tiến hóa API, nên duy trì relation có ý nghĩa ổn định và để máy khách theo URI được trả về. Nếu endpoint đích thay đổi, máy chủ có thể cập nhật `href` trong representation mới mà không yêu cầu máy khách tự ghép đường dẫn.

## 9. Kiểm thử hành vi immutable

Kiểm thử nên xác nhận các phương thức `with...` tạo giá trị mới và không làm thay đổi Link ban đầu.

Ví dụ với JUnit và AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;

class LinkImmutabilityTest {

    @Test
    void withTitleReturnsANewLinkAndKeepsOriginalValue() {
        Link original = Link.of("/orders/42", "self");

        Link titled = original.withTitle("Order details");

        assertThat(titled).isNotSameAs(original);
        assertThat(original.getHref()).isEqualTo("/orders/42");
        assertThat(titled.getHref()).isEqualTo("/orders/42");
        assertThat(original.getRel()).isEqualTo(titled.getRel());
    }
}
```

Kiểm thử trên xác nhận instance mới được tạo và các giá trị URI, relation hiện có vẫn được giữ. Có thể bổ sung kiểm tra metadata tiêu đề bằng API getter tương ứng của phiên bản Spring HATEOAS mà dự án đang dùng.

Ngoài kiểm thử value object, nên kiểm tra representation HTTP sau khi Link được gắn vào model:

```java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.self.title").value("Order details"));
```

Kết quả cần được đối chiếu với media type và cấu hình URI thực tế của ứng dụng. Nếu hệ thống sinh absolute URI, giá trị `href` trong kiểm thử phải phản ánh host và context path tương ứng.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Gọi `withTitle` nhưng bỏ qua giá trị trả về | Link ban đầu không thay đổi | Gán kết quả vào biến hoặc nối lời gọi |
| Mong đợi `withRel` sửa relation hiện tại | Phương thức tạo một Link mới | Dùng Link trả về |
| Nhầm Link với LinkBuilder | Builder dùng để tạo URI/link; Link là kết quả | Hoàn tất builder rồi lưu Link |
| Dùng relation tùy ý không có tài liệu | Máy khách không hiểu semantics | Dùng relation chuẩn hoặc URI relation ổn định |
| Dùng Link dùng chung cho URI phụ thuộc request | Link có thể trỏ sai tài nguyên hoặc ngữ cảnh | Tạo Link theo từng request |
| Cho rằng immutable đồng nghĩa permanent | Đích đến vẫn có thể ngừng hoạt động | Thiết kế và duy trì URI như một phần hợp đồng API |
| Cho rằng EntityModel cũng immutable | Model có API để thêm link khi xây dựng | Phân biệt bất biến của Link với cách lắp ghép representation |

## 11. Quy trình tạo và sử dụng Link

Khi tạo link trong Spring HATEOAS, có thể thực hiện theo trình tự:

1. Xác định tài nguyên đích và relation mô tả ý nghĩa của liên kết.
2. Tạo URI bằng `WebMvcLinkBuilder` hoặc `Link.of(...)` tùy ngữ cảnh.
3. Gắn relation chuẩn hoặc relation mở rộng đã được tài liệu hóa.
4. Dùng các phương thức `with...` để tạo phiên bản có metadata cần thiết.
5. Giữ lại Link trả về từ mỗi lời gọi thay vì mong đợi đối tượng cũ bị thay đổi.
6. Gắn Link vào representation model phù hợp.
7. Kiểm thử cả giá trị Link lẫn biểu diễn HTTP được tuần tự hóa.

`Link` bất biến giúp việc xây dựng và tái sử dụng liên kết dễ dự đoán. Mỗi biến thể là một giá trị riêng, không làm thay đổi link đã tạo trước đó. Khi kết hợp với relation rõ nghĩa, URI được duy trì theo hợp đồng và representation model của Spring HATEOAS, các liên kết trở thành phần ổn định, dễ kiểm thử của API hypermedia.
