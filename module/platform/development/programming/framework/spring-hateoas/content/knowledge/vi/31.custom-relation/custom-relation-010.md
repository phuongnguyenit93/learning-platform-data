# Tránh relation mơ hồ

Link relation là một phần của hợp đồng hypermedia. Nó cho client biết tài nguyên đích có quan hệ gì với tài nguyên hiện tại và vì sao client nên theo liên kết đó. Nếu nhiều link mang các relation chung chung như `related`, `data` hoặc `action` mà không có định nghĩa cụ thể, client không thể phân biệt mục đích của chúng một cách đáng tin cậy. Khi đó, hypermedia mất đi phần ngữ nghĩa vốn giúp client giảm phụ thuộc vào cấu trúc URL.

Spring HATEOAS hỗ trợ cả relation chuẩn IANA và relation mở rộng do ứng dụng định nghĩa. Với relation chuẩn, nên dùng các hằng số trong `IanaLinkRelations`. Khi không có relation chuẩn phù hợp, ứng dụng có thể tạo extension relation type bằng một URI duy nhất, ổn định và nằm dưới quyền kiểm soát của tổ chức định nghĩa nó. Trong HAL, `CurieProvider` còn cho phép biểu diễn URI đó bằng một CURIE ngắn gọn.

Bài học này tập trung vào cách tránh relation mơ hồ: phân biệt relation chuẩn với relation mở rộng, viết định nghĩa có ngữ nghĩa rõ ràng, chọn URI bền vững, sử dụng `LinkRelation.of(...)` và `DefaultCurieProvider`, đồng thời kiểm thử relation sau khi serialize.

Sau bài học, bạn có thể:

- Giải thích vì sao relation mơ hồ làm client phụ thuộc vào phỏng đoán.
- Phân biệt registered relation type và extension relation type theo RFC 8288.
- Chọn relation IANA có sẵn khi ngữ nghĩa đã phù hợp.
- Định nghĩa custom relation bằng URI ổn định thuộc quyền kiểm soát của tổ chức.
- Tránh dùng tên chung chung, tên endpoint hoặc tên method làm relation.
- Tạo custom relation bằng `LinkRelation.of(...)` và `Link.of(...)`.
- Dùng CURIE để rút gọn extension relation trong HAL.
- Phân biệt custom relation với media type, URI template, affordance và tên tài nguyên.
- Kiểm thử relation và representation HAL để bảo vệ hợp đồng.

## 1. Relation có nhiệm vụ mô tả ngữ nghĩa

Một link nối tài nguyên hiện tại với tài nguyên đích. Relation mô tả quan hệ giữa hai tài nguyên đó.

Ví dụ, một đơn hàng có thể công bố:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "https://api.example.com/rels/order-approval-history": {
      "href": "/orders/42/approval-history"
    }
  }
}
~~~

Relation `https://api.example.com/rels/order-approval-history` nói rõ link đích là lịch sử phê duyệt của đơn hàng hiện tại. Client có thể dùng relation này để tìm đúng link mà không cần phân tích path `/orders/42/approval-history`.

Nếu cùng link đó mang relation `related`, client chỉ biết đích có liên quan theo một cách nào đó. Nó không biết đó là lịch sử phê duyệt, lịch sử thanh toán, tài liệu đính kèm hay thông tin khách hàng.

Một relation tốt giúp client trả lời được câu hỏi: *Tài nguyên đích có ý nghĩa gì đối với tài nguyên hiện tại?*

### 1.1. Relation không phải tên URL

Không nên đặt relation theo route hiện tại:

~~~text
/orders/{id}/approval-history
~~~

Đây là cấu trúc địa chỉ. Route có thể thay đổi khi server tổ chức lại controller hoặc gateway. Relation cần mô tả ngữ nghĩa ổn định để client tiếp tục nhận diện chức năng sau khi URL thay đổi.

Cũng không nên dùng tên method Java như `getApprovalHistory` làm relation. Tên method là chi tiết triển khai và có thể đổi theo quy ước code.

Hãy dùng relation thể hiện quan hệ, ví dụ `order-approval-history`, còn href trỏ đến URI thực tế do server công bố.

### 1.2. Relation không phải media type

Relation mô tả mối quan hệ giữa context và target. Media type mô tả định dạng representation mà client nhận khi dereference target.

Ví dụ:

- Relation: `https://api.example.com/rels/order-approval-history`.
- Href: `/orders/42/approval-history`.
- Media type của target: `application/hal+json`.

Không nên tạo relation như `hal-json` chỉ để mô tả định dạng JSON. Nếu cần cung cấp gợi ý định dạng, dùng thuộc tính `type` của link hoặc content negotiation theo hợp đồng HTTP.

## 2. Vì sao relation mơ hồ gây khó cho client?

Giả sử một representation chứa các link:

~~~json
{
  "_links": {
    "related": [
      { "href": "/orders/42/customer" },
      { "href": "/orders/42/payments" },
      { "href": "/orders/42/history" }
    ],
    "action": [
      { "href": "/orders/42/cancel" },
      { "href": "/orders/42/approve" }
    ]
  }
}
~~~

Client biết có các link, nhưng không thể phân biệt mục đích của từng phần tử trong cùng relation. Client phải đoán dựa trên URI hoặc vị trí của link. Khi server thay đổi path, client có thể hỏng dù ngữ nghĩa nghiệp vụ không thay đổi.

Có thể cải thiện bằng các relation riêng:

~~~json
{
  "_links": {
    "https://api.example.com/rels/order-customer": {
      "href": "/orders/42/customer"
    },
    "https://api.example.com/rels/order-payments": {
      "href": "/orders/42/payments"
    },
    "https://api.example.com/rels/order-history": {
      "href": "/orders/42/history"
    },
    "https://api.example.com/rels/cancel-order": {
      "href": "/orders/42/cancel"
    },
    "https://api.example.com/rels/approve-order": {
      "href": "/orders/42/approve"
    }
  }
}
~~~

Mỗi relation mô tả một ý nghĩa riêng. Client có thể tìm đúng liên kết theo ngữ nghĩa thay vì kiểm tra path.

### 2.1. Những tên relation cần xem xét kỹ

| Relation chung chung | Vấn đề | Cách diễn đạt cụ thể hơn |
|---|---|---|
| `related` | Không cho biết loại quan hệ | `acme:order-customer`, `acme:order-payments`, `acme:order-history` |
| `data` | Không nói dữ liệu gì | `acme:invoice-details`, `acme:approval-history` |
| `action` | Không nói hành động nào | `acme:cancel-order`, `acme:approve-order` |
| `info` | Không rõ nội dung đích | `acme:shipping-address`, `acme:payment-summary` |
| `details` | Có thể chỉ bất kỳ loại chi tiết nào | `acme:delivery-details`, `acme:tax-breakdown` |
| `link` | Chỉ lặp lại khái niệm liên kết | Dùng relation mô tả target |

Các ví dụ có prefix `acme:` giả định HAL đã công bố CURIE tương ứng. Nếu không dùng CURIE, relation cần được biểu diễn bằng URI extension đầy đủ.

Các relation IANA như `related` vẫn hợp lệ khi target thực sự chỉ là một tài nguyên có liên quan chung chung và client không cần phân biệt sâu hơn. Vấn đề xuất hiện khi ứng dụng dùng một relation rộng cho nhiều loại target có ý nghĩa khác nhau nhưng lại mong client nhận biết từng loại.

### 2.2. Không gom nhiều hành động vào một relation duy nhất

Ví dụ `action` có thể gom cancel, approve, refund và reopen. Client không thể xác định hành động nào đang được cung cấp nếu không đọc URL hoặc một metadata riêng.

Hãy chọn relation cho từng khả năng nếu client cần phân biệt:

- `acme:cancel-order`: tài nguyên hoặc endpoint hủy đơn hàng.
- `acme:approve-order`: tài nguyên hoặc endpoint phê duyệt đơn hàng.
- `acme:refund-payment`: tài nguyên hoặc endpoint hoàn tiền.

Nếu hành động có nhiều input hoặc HTTP method cần được mô tả, có thể kết hợp relation với affordance. Relation đặt tên ngữ nghĩa của link; affordance mô tả method và payload mà client cần gửi.

## 3. Ưu tiên relation chuẩn IANA khi có ngữ nghĩa phù hợp

IANA Link Relation Registry chứa các relation được định nghĩa để nhiều ứng dụng có thể dùng chung. Spring HATEOAS cung cấp `IanaLinkRelations` để tham chiếu chúng.

Ví dụ:

~~~java
Link self = Link.of("/orders/42", IanaLinkRelations.SELF);

Link collection = Link.of(
    "/orders",
    IanaLinkRelations.COLLECTION
);

Link edit = Link.of(
    "/orders/42/edit",
    IanaLinkRelations.EDIT
);
~~~

Import:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
~~~

Dùng relation chuẩn giúp client có thể tái sử dụng hiểu biết đã có. Tuy nhiên, chỉ chọn relation nếu định nghĩa của nó thực sự khớp với quan hệ mà API muốn công bố.

Không nên dùng relation chuẩn gần giống nghĩa chỉ để tránh tạo custom relation. Ví dụ, relation `edit` có ý nghĩa target có thể được dùng để chỉnh sửa context; nó không phải nhãn chung cho mọi trang chi tiết hoặc mọi thao tác ghi dữ liệu.

### 3.1. Kiểm tra IANA relation có sẵn

Có thể tra cứu registry trước khi định nghĩa relation mới:

- [IANA Link Relation Registry](https://www.iana.org/assignments/link-relations)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288)

Nếu một relation chuẩn đáp ứng đúng ngữ nghĩa, dùng hằng số tương ứng từ `IanaLinkRelations`. Nếu không có relation phù hợp, định nghĩa extension relation type.

### 3.2. Khi nào nên tạo custom relation?

Tạo custom relation khi:

- Quan hệ chỉ có ý nghĩa trong miền nghiệp vụ của ứng dụng.
- Client cần phân biệt một loại tài nguyên hoặc khả năng riêng.
- Không có registered relation nào mô tả chính xác quan hệ đó.
- Tổ chức có thể duy trì một định danh URI ổn định cho relation.

Ví dụ, `order-approval-history` là quan hệ đặc thù của miền đơn hàng. Nó có thể không phù hợp để đăng ký thành relation chung cho toàn Web, nhưng vẫn có thể được định danh duy nhất bằng extension relation URI.

## 4. Quy tắc của extension relation type theo RFC 8288

RFC 8288 phân biệt hai nhóm relation:

1. **Registered relation type**: tên token đã được đăng ký, thường được dùng lại giữa các ứng dụng.
2. **Extension relation type**: URI duy nhất xác định ngữ nghĩa relation do ứng dụng hoặc tổ chức định nghĩa.

Extension relation type phải là URI xác định duy nhất relation. URI nên nằm dưới quyền kiểm soát hoặc được ủy quyền cho tổ chức định nghĩa nó.

Ví dụ:

~~~text
https://api.example.com/rels/order-approval-history
https://api.example.com/rels/cancel-order
https://api.example.com/rels/refund-payment
~~~

Không nên dùng một chuỗi ngắn tự đặt như `approvalHistory` làm extension relation trong hợp đồng Web Linking. Spring HATEOAS cho phép tạo `LinkRelation` từ chuỗi, nhưng việc tạo được object không có nghĩa chuỗi tùy ý đó đáp ứng quy tắc extension relation của RFC 8288.

### 4.1. Chọn URI nằm trong quyền kiểm soát

Dùng một namespace mà tổ chức có thể duy trì lâu dài, chẳng hạn:

~~~text
https://api.example.com/rels/{relation-name}
~~~

Không nên dùng:

- Domain của bên thứ ba mà tổ chức không kiểm soát.
- URL của một endpoint nghiệp vụ đang có thể bị đổi.
- URL chứa ID môi trường như `dev`, `staging` hoặc hostname nội bộ.
- URI tạm thời chỉ tồn tại trong một phiên bản triển khai.

URI relation là định danh ngữ nghĩa. Nó không nhất thiết phải là endpoint xử lý request, cũng không nhất thiết phải trả dữ liệu nghiệp vụ khi client truy cập.

### 4.2. Dùng chữ thường và giữ URI nhất quán

RFC 8288 quy định extension relation được so sánh theo chuỗi và khuyến nghị URI chữ thường để tránh khác biệt không cần thiết.

Hãy chọn một cách viết chuẩn:

~~~text
https://api.example.com/rels/order-approval-history
~~~

Tránh phát ra nhiều biến thể như:

~~~text
https://api.example.com/rels/OrderApprovalHistory
https://api.example.com/rels/order-Approval-History
https://api.example.com/rels/order_approval_history
~~~

Dù các hệ thống có thể chuẩn hóa một số thành phần URI, client và server nên dùng đúng một chuỗi canonical để kiểm thử và trao đổi.

### 4.3. URI có thể dẫn đến tài liệu định nghĩa

Tổ chức có thể xuất bản tài liệu giải thích relation tại URI đó hoặc tại một trang tài liệu liên quan. Tài liệu nên mô tả:

- Tên và mục đích của relation.
- Quan hệ giữa link context và link target.
- Loại tài nguyên target.
- Các hành vi mà target hỗ trợ nếu có.
- Quy tắc tương thích và cách thay đổi ngữ nghĩa.

Tuy nhiên, RFC 8288 khuyến nghị client không tự động truy cập URI định nghĩa extension relation. Việc hiểu relation nên dựa trên hợp đồng hoặc tài liệu client đã biết, tránh tạo request tự động đến máy chủ chỉ để tra cứu mọi relation xuất hiện.

## 5. Tạo custom relation bằng Spring HATEOAS

Spring HATEOAS cung cấp `LinkRelation.of(String)` để tạo relation từ chuỗi và `Link.of(...)` để tạo link.

Ví dụ một relation mở rộng:

~~~java
LinkRelation approvalHistory =
    LinkRelation.of(
        "https://api.example.com/rels/order-approval-history"
    );

Link history = Link.of(
    "/orders/42/approval-history",
    approvalHistory
);
~~~

Import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
~~~

Có thể gắn link vào representation model:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {
    // Các thuộc tính của đơn hàng.
}
~~~

Import:

~~~java
import org.springframework.hateoas.RepresentationModel;
~~~

~~~java
OrderModel model = new OrderModel();
model.add(history);
~~~

Spring HATEOAS giữ relation trong object `LinkRelation`. Media type serializer sẽ quyết định cách biểu diễn relation trong response. Với HAL không cấu hình CURIE, extension relation có thể được xuất ra dưới dạng URI đầy đủ.

### 5.1. Tạo link bằng controller mapping

Trong ứng dụng Spring MVC, có thể lấy href từ controller mapping để tránh lặp URL:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}/approval-history")
    CollectionModel<ApprovalEventModel> approvalHistory(
            @PathVariable UUID id) {
        // Trả về lịch sử phê duyệt.
        // ...
    }
}
~~~

Tạo link:

~~~java
Link history = linkTo(
    methodOn(OrderController.class).approvalHistory(orderId)
).withRel(
    LinkRelation.of(
        "https://api.example.com/rels/order-approval-history"
    )
);
~~~

Import:

~~~java
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`methodOn(...)` giúp Spring HATEOAS phân tích mapping và giá trị `@PathVariable`. Relation được gắn tường minh để mô tả ý nghĩa nghiệp vụ của tài nguyên đích.

### 5.2. Tách hằng số relation dùng chung

Nếu một relation được dùng ở nhiều controller hoặc assembler, hãy định nghĩa một hằng số dùng chung:

~~~java
public final class OrderRelations {

    private OrderRelations() {}

    public static final LinkRelation APPROVAL_HISTORY =
        LinkRelation.of(
            "https://api.example.com/rels/order-approval-history"
        );
}
~~~

Import:

~~~java
import org.springframework.hateoas.LinkRelation;
~~~

Sau đó:

~~~java
Link history = Link.of(
    "/orders/42/approval-history",
    OrderRelations.APPROVAL_HISTORY
);
~~~

Việc tập trung relation giúp tránh sai khác URI giữa các module, giảm lỗi chính tả và làm rõ tập ngữ nghĩa mà API công bố.

Không cần tạo một class cho mọi relation nếu ứng dụng nhỏ. Điều quan trọng là các nơi sử dụng cùng một relation phải tham chiếu cùng định danh canonical.

## 6. Dùng CURIE để rút gọn custom relation trong HAL

Extension relation URI có thể dài. HAL hỗ trợ CURIE (Compact URI) để biểu diễn URI relation bằng prefix.

Ví dụ URI đầy đủ:

~~~text
https://api.example.com/rels/order-approval-history
~~~

Có thể rút gọn thành:

~~~text
acme:order-approval-history
~~~

Trong đó prefix `acme` được ánh xạ đến URI template:

~~~text
https://api.example.com/rels/{rel}
~~~

CURIE không tạo ra một relation mới và cũng không thay đổi ngữ nghĩa. Nó chỉ là cách viết ngắn của extension relation URI.

### 6.1. Cấu hình DefaultCurieProvider

Spring HATEOAS cung cấp `DefaultCurieProvider` để khai báo prefix và URI template:

~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "acme",
            UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;
~~~

Khi `CurieProvider` được cấu hình, Spring HATEOAS tự thêm link `curies` vào tài nguyên HAL và rút gọn các extension relation tương ứng. Relation IANA như `self` vẫn được giữ nguyên.

### 6.2. HAL representation có CURIE

Với link approval history đã tạo ở phần trước, HAL response có thể tương tự:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:order-approval-history": {
      "href": "/orders/42/approval-history"
    }
  }
}
~~~

Client đọc link `curies` để biết prefix `acme` tương ứng với URI template nào. Khi cần định danh đầy đủ, client mở rộng:

~~~text
acme:order-approval-history
        ↓
https://api.example.com/rels/order-approval-history
~~~

Nếu response không công bố CURIE tương ứng, client không nên tự đoán namespace của prefix.

### 6.3. Một CurieProvider trong application scope

Spring HATEOAS chỉ hỗ trợ một bean `CurieProvider` trong application scope. Nếu API cần nhiều namespace, có thể dùng constructor nhận map prefix và URI template của `DefaultCurieProvider` để khai báo nhiều CURIE trong cùng provider.

Ví dụ:

~~~java
@Bean
CurieProvider curieProvider() {
    return new DefaultCurieProvider(Map.of(
        "acme", UriTemplate.of("https://api.example.com/rels/{rel}"),
        "billing", UriTemplate.of("https://billing.example.com/rels/{rel}")
    ));
}
~~~

Import bổ sung:

~~~java
import java.util.Map;
~~~

Chỉ thêm namespace khi có ranh giới từ vựng hoặc chủ sở hữu ngữ nghĩa khác nhau. Quá nhiều prefix làm representation khó đọc và khiến client phải quản lý nhiều namespace không cần thiết.

## 7. Thiết kế relation để tránh mơ hồ

Một custom relation nên có định nghĩa ngắn gọn, cụ thể và ổn định. Hãy mô tả quan hệ giữa context và target, không chỉ ghi target là "một dữ liệu liên quan".

Ví dụ:

| Thành phần | Định nghĩa |
|---|---|
| URI relation | `https://api.example.com/rels/order-approval-history` |
| Context | Một đơn hàng |
| Target | Collection các sự kiện phê duyệt của đơn hàng đó |
| Ý nghĩa | Target cung cấp lịch sử phê duyệt thuộc đơn hàng hiện tại |
| Thay đổi URL target | Không làm đổi relation nếu ngữ nghĩa không đổi |
| Thay đổi ngữ nghĩa không tương thích | Cần định nghĩa relation mới |

### 7.1. Đặt tên theo ngữ nghĩa, không theo implementation

Tên relation nên phản ánh mục đích mà client cần hiểu.

Ví dụ phù hợp:

Với prefix CURIE `acme` đã được khai báo, các relation có thể được viết:

- `acme:order-approval-history`
- `acme:invoice-document`
- `acme:customer-preferences`
- `acme:shipment-tracking`
- `acme:cancel-order`

Ví dụ kém rõ nghĩa:

- `getOrderHistory`
- `orderController`
- `data2`
- `relatedResource`
- `endpointA`

Tên thứ nhất mô tả quan hệ hoặc khả năng; tên thứ hai bộc lộ chi tiết code, vị trí hoặc cách triển khai.

### 7.2. Relation phải đủ cụ thể nhưng không gắn với từng giá trị dữ liệu

Không tạo relation khác nhau cho từng ID hoặc từng giá trị trạng thái.

Không nên:

~~~text
https://api.example.com/rels/order-42-approval-history
https://api.example.com/rels/order-43-approval-history
~~~

Nên dùng cùng relation cho cùng một ý nghĩa:

~~~text
https://api.example.com/rels/order-approval-history
~~~

Href của mỗi link chứa ID đơn hàng tương ứng. Relation giữ ngữ nghĩa chung của loại quan hệ.

### 7.3. Phân biệt relation của tài nguyên và relation của thao tác

Một relation có thể chỉ đến tài nguyên liên quan, hoặc chỉ ra một khả năng mà target hỗ trợ. Hãy xác định rõ client cần nhận biết điều gì.

Ví dụ:

- `acme:order-approval-history`: target là tài nguyên lịch sử phê duyệt.
- `acme:cancel-order`: target là khả năng hoặc endpoint hủy đơn hàng.

Nếu thao tác có input payload, method hoặc affordance phức tạp, hãy công bố thêm metadata tương ứng. Đừng mong relation name tự mô tả mọi chi tiết của request.

### 7.4. Không thay đổi ý nghĩa của relation đã công bố

Khi client đã phụ thuộc vào relation, thay đổi ý nghĩa của nó có thể làm client diễn giải sai link.

Ví dụ, nếu relation `order-approval-history` trước đây trỏ đến lịch sử phê duyệt, không nên tái sử dụng nó cho một tài nguyên tổng hợp gồm phê duyệt, thanh toán và giao hàng.

Nếu ngữ nghĩa thay đổi không tương thích, tạo URI relation mới và có kế hoạch chuyển đổi. Nếu chỉ thay đổi URL hoặc cấu trúc nội bộ nhưng ngữ nghĩa giữ nguyên, có thể giữ nguyên relation.

## 8. Những điều relation không nên gánh thay

Relation chỉ mô tả quan hệ giữa context và target. Các phần khác của hợp đồng cần được biểu diễn bằng cơ chế phù hợp.

| Thông tin cần mô tả | Cơ chế phù hợp |
|---|---|
| Ý nghĩa link | Link relation |
| Địa chỉ tài nguyên đích | `href` |
| Định dạng representation | Media type và `type` |
| Query parameter có thể điền | URI template |
| HTTP method và input/output payload | Affordance hoặc tài liệu giao thức |
| Kiểu dữ liệu và schema | Schema/profile hoặc media type |
| Quyền thực hiện thao tác | Xác thực và phân quyền phía server |
| Trạng thái lỗi | HTTP status và Problem Details |

Ví dụ relation `acme:cancel-order` không tự đảm bảo người dùng được phép hủy đơn. Server vẫn phải kiểm tra quyền và trạng thái nghiệp vụ khi client gửi request.

Tương tự, relation `acme:invoice-document` không nói tài liệu đích là PDF hay JSON. Nếu cần gợi ý định dạng, dùng thuộc tính `type` hoặc content negotiation.

## 9. Kiểm thử custom relation

Custom relation là một phần hợp đồng API nên cần được kiểm thử. Có thể kiểm tra ở hai mức: object model và representation được serialize.

### 9.1. Unit test cho relation canonical

~~~java
@Test
void createsCanonicalApprovalHistoryRelation() {

    LinkRelation relation = LinkRelation.of(
        "https://api.example.com/rels/order-approval-history"
    );

    Link link = Link.of(
        "/orders/42/approval-history",
        relation
    );

    assertThat(link.getRel().value())
        .isEqualTo("https://api.example.com/rels/order-approval-history");

    assertThat(link.hasRel(relation)).isTrue();
}
~~~

Import:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Kiểm thử xác nhận relation dùng URI canonical và link giữ đúng relation đã định nghĩa.

### 9.2. Kiểm thử client tra cứu theo relation

~~~java
@Test
void findsApprovalHistoryBySemanticRelation() {

    LinkRelation relation = OrderRelations.APPROVAL_HISTORY;

    OrderModel model = new OrderModel();
    model.add(Link.of("/orders/42/approval-history", relation));

    Link history = model.getRequiredLink(relation);

    assertThat(history.getHref())
        .isEqualTo("/orders/42/approval-history");
}
~~~

Kiểm thử này thể hiện cách client hoặc code xử lý representation tìm link bằng relation. Nó không cần kiểm tra path để xác định ý nghĩa của link.

### 9.3. Kiểm thử CURIE trong HAL response

Nếu ứng dụng cấu hình `DefaultCurieProvider`, nên kiểm thử cả link CURIE lẫn mapping namespace:

~~~java
mvc.perform(get("/orders/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies.name").value("acme"))
    .andExpect(jsonPath("$._links.curies.templated").value(true))
    .andExpect(jsonPath(
        "$._links['acme:order-approval-history'].href"
    ).value("/orders/42/approval-history"));
~~~

Import kiểm thử:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Tùy cấu hình base URI, href có thể là absolute URI. Trong trường hợp đó, kiểm tra phần path hoặc dùng matcher phù hợp thay vì so sánh chuỗi đầy đủ.

### 9.4. Kiểm thử relation chuẩn không bị chuyển thành custom relation

Nếu ứng dụng bật CURIE, các relation IANA vẫn cần giữ nguyên:

~~~java
Link self = Link.of("/orders/42", IanaLinkRelations.SELF);

assertThat(self.getRel())
    .isEqualTo(IanaLinkRelations.SELF);
~~~

Import:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
~~~

Kiểm thử ở cấp representation cũng nên xác nhận `_links.self` vẫn là `self`, trong khi extension relation được serialize theo CURIE đã cấu hình.

## 10. Quy trình định nghĩa custom relation

Khi cần một relation mới, hãy thực hiện theo trình tự:

1. Xác định context và target của link.
2. Viết một câu mô tả quan hệ giữa hai tài nguyên.
3. Kiểm tra IANA registry để tìm relation chuẩn có ngữ nghĩa phù hợp.
4. Nếu không có, tạo extension relation URI thuộc quyền kiểm soát của tổ chức.
5. Dùng URI chữ thường, ổn định và không phụ thuộc môi trường.
6. Chọn tên cụ thể, không trùng với quan hệ khác hoặc chi tiết triển khai.
7. Định nghĩa relation trong một vị trí dùng chung nếu nhiều component cùng sử dụng.
8. Dùng `LinkRelation.of(...)` để tạo relation và gắn vào `Link`.
9. Nếu dùng HAL, cân nhắc `DefaultCurieProvider` để rút gọn URI.
10. Công bố tài liệu mô tả relation và chính sách tương thích.
11. Kiểm thử relation, href, CURIE và cách client khám phá link.
12. Giữ nguyên ngữ nghĩa relation đã công bố; tạo URI mới khi thay đổi không tương thích.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `related` cho mọi loại link | Client không phân biệt được mục đích | Đặt relation theo ngữ nghĩa cụ thể |
| Dùng tên method hoặc controller làm relation | Client phụ thuộc implementation | Đặt tên theo quan hệ nghiệp vụ |
| Dùng chuỗi ngắn tùy ý làm extension relation | Không đáp ứng định danh URI của RFC 8288 | Dùng URI duy nhất |
| Dùng domain không thuộc quyền kiểm soát | Không bảo đảm namespace lâu dài | Chọn URI do tổ chức quản lý |
| Đổi URL và đổi relation cùng lúc dù ngữ nghĩa không đổi | Client phải cập nhật không cần thiết | Giữ relation ổn định qua thay đổi route |
| Tái sử dụng relation cho ngữ nghĩa mới | Client diễn giải sai link | Định nghĩa URI relation mới |
| Tạo relation trùng với IANA relation | Client có thể hiểu theo nghĩa chuẩn khác | Tra cứu registry trước khi tạo |
| Coi CURIE là relation mới | Client không biết cách mở rộng prefix | Công bố `curies` link và URI template |
| Cho rằng client phải dereference URI relation | Tạo request thừa và phụ thuộc ngoài ý muốn | Cung cấp tài liệu nhưng không yêu cầu client tự truy cập |
| Dùng relation để mô tả media type hoặc schema | Trộn lẫn các phần hợp đồng | Dùng `type`, profile, affordance hoặc schema phù hợp |

## 12. Kết luận

Relation mơ hồ buộc client phải đoán ý nghĩa của link từ URL hoặc quy ước nội bộ. Hãy ưu tiên relation chuẩn IANA khi định nghĩa đã phù hợp. Khi cần một ngữ nghĩa riêng, hãy tạo extension relation type bằng URI duy nhất, ổn định và nằm dưới quyền kiểm soát của tổ chức. Trong Spring HATEOAS, `LinkRelation.of(...)` và `Link.of(...)` giúp tạo link đó; `DefaultCurieProvider` có thể rút gọn URI trong HAL bằng CURIE.

Một custom relation tốt mô tả rõ quan hệ giữa tài nguyên hiện tại và tài nguyên đích, không phụ thuộc tên controller hoặc đường dẫn triển khai, không bị tái sử dụng cho ý nghĩa khác và có thể được client kiểm thử bằng định danh ổn định. Khi relation, href, media type, URI template và affordance được dùng đúng vai trò, hợp đồng hypermedia trở nên dễ khám phá và ít mơ hồ hơn.

## Tài liệu tham khảo

- [RFC 8288 — Web Linking, Section 2.1](https://www.rfc-editor.org/rfc/rfc8288#section-2.1): registered và extension link relation types, yêu cầu đối với URI extension relation.
- [IANA Link Relation Registry](https://www.iana.org/assignments/link-relations): các relation chuẩn đã đăng ký.
- [Spring HATEOAS Reference — Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links.link-relations): `LinkRelation`, `IanaLinkRelations` và extension relation URI.
- [Spring HATEOAS Reference — Using the CurieProvider API](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.curie-provider): cấu hình CURIE và `DefaultCurieProvider`.
- [Spring HATEOAS API — LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html): tạo relation bằng `LinkRelation.of(String)`.
- [Spring HATEOAS API — DefaultCurieProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html): cấu hình namespace CURIE.

