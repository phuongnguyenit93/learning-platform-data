# Relation cho domain

Trong REST API dùng hypermedia, một link có `href` để chỉ ra đích điều hướng và `rel` để mô tả mối quan hệ giữa resource hiện tại với đích đó. Các relation chuẩn như `self`, `next`, `collection` hoặc `search` đã có ngữ nghĩa được cộng đồng thống nhất. Tuy nhiên, domain của một hệ thống thường có những quan hệ riêng: đơn hàng có thể liên kết đến khoản thanh toán, phiếu giao hàng, hóa đơn hoặc lịch sử phê duyệt. Khi không có relation chuẩn phù hợp, API có thể định nghĩa **custom relation** để diễn đạt chính xác các mối quan hệ nghiệp vụ này.

Spring HATEOAS biểu diễn relation bằng `LinkRelation`, gắn relation vào `Link` và hỗ trợ namespace custom relation trong HAL thông qua CURIE. Một vocabulary được thiết kế ổn định giúp client hiểu ý nghĩa link mà không phải phân tích URL, tên controller hay cấu trúc database của server.

## 1. Link relation diễn tả điều gì?

Relation mô tả mối quan hệ giữa resource chứa link và resource ở đích `href`. Ví dụ, một đơn hàng có link đến collection các khoản thanh toán:

```json
{
  "id": "ORD-2026-1042",
  "_links": {
    "self": {
      "href": "https://api.acme.example/orders/ORD-2026-1042"
    },
    "payments": {
      "href": "https://api.acme.example/orders/ORD-2026-1042/payments"
    }
  }
}
```

Relation `payments` cho client biết link dẫn đến tập payment gắn với đơn hàng hiện tại. Nó không nói rằng đích được triển khai bởi `PaymentController`, bảng `order_payment` hay một microservice cụ thể. Những chi tiết đó thuộc implementation của server.

Relation nên trả lời câu hỏi: “Đích này có ý nghĩa gì đối với resource hiện tại?”. Tên relation không nên chỉ mô tả cách server lưu trữ dữ liệu hoặc tên một hàm nội bộ.

## 2. Dùng relation chuẩn khi đã có ngữ nghĩa phù hợp

IANA duy trì registry các link relation chuẩn. Spring HATEOAS cung cấp `IanaLinkRelations` để tham chiếu một số relation thường dùng mà không phải gõ chuỗi thủ công:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("https://api.acme.example/orders/ORD-1042",
        IanaLinkRelations.SELF);

Link collection = Link.of("https://api.acme.example/orders",
        IanaLinkRelations.COLLECTION);
```

Chỉ dùng relation chuẩn khi ý nghĩa link khớp với định nghĩa của relation đó. Không dùng `next` cho một link đến khoản thanh toán hoặc dùng `item` chỉ vì đích là một object. Việc tái sử dụng relation chuẩn sai ngữ nghĩa khiến client hiểu nhầm và làm hợp đồng API khó tiến hóa.

Nếu một quan hệ domain không có trong registry, hãy định nghĩa extension relation riêng. Không cần tạo custom relation cho mọi link: ưu tiên relation chuẩn khi chúng đã diễn đạt đúng ý nghĩa.

## 3. Khi nào cần custom relation?

Custom relation hữu ích khi API cần mô tả một quan hệ đặc thù của domain mà relation chuẩn không bao phủ. Ví dụ:

| Resource hiện tại | Custom relation | Resource đích |
| --- | --- | --- |
| Order | `payments` | Các khoản thanh toán của đơn hàng |
| Order | `invoice` | Hóa đơn được phát hành cho đơn hàng |
| Order | `shipment` | Thông tin giao hàng |
| Payment | `refunds` | Các khoản hoàn tiền liên quan |
| Approval | `reviewer` | Người phụ trách phê duyệt |

Tên relation cần có ngữ nghĩa rõ ràng, ổn định và được dùng nhất quán trong mọi representation. Ví dụ, nếu `payments` luôn có nghĩa là collection khoản thanh toán của order, không nên lúc khác dùng nó cho một payment đơn lẻ.

Hãy chọn số ít hoặc số nhiều theo loại resource đích và convention của API. Quan trọng nhất là duy trì một ý nghĩa nhất quán, không phải chọn một quy tắc đặt tên duy nhất cho mọi hệ thống.

## 4. Extension relation và URI định danh

Theo quy tắc Web Linking, relation extension nên được định danh bằng URI tuyệt đối để tránh xung đột tên với relation của hệ thống khác. URI đó là định danh ngữ nghĩa, không nhất thiết phải là endpoint API thực thi thao tác.

Ví dụ vocabulary của Acme:

```text
https://api.acme.example/rels/payments
https://api.acme.example/rels/invoice
https://api.acme.example/rels/shipment
```

URI relation nên ổn định theo thời gian. Nếu có thể, hãy để URI mở được một trang tài liệu giải thích:

- Ý nghĩa của quan hệ giữa resource nguồn và resource đích.
- Kiểu resource mà link thường trỏ đến.
- Cardinality dự kiến: một resource hay một collection.
- Các điều kiện nghiệp vụ làm link xuất hiện hoặc biến mất.
- Cách client nên sử dụng link và media type liên quan.

Không dùng URL có chứa phiên bản implementation, hostname nội bộ hoặc tên database. Nếu đổi hạ tầng, định danh relation vẫn phải giữ nguyên vì client có thể đã phụ thuộc vào ngữ nghĩa đó.

## 5. Khai báo vocabulary trong Java

Tập trung các relation của domain trong một class giúp tránh typo và tạo một nơi tra cứu ý nghĩa:

```java
import org.springframework.hateoas.LinkRelation;

public final class OrderRelations {

    public static final LinkRelation PAYMENTS =
            LinkRelation.of("https://api.acme.example/rels/payments");

    public static final LinkRelation INVOICE =
            LinkRelation.of("https://api.acme.example/rels/invoice");

    public static final LinkRelation SHIPMENT =
            LinkRelation.of("https://api.acme.example/rels/shipment");

    private OrderRelations() {
    }
}
```

`LinkRelation.of(...)` tạo đối tượng relation từ tên hoặc URI relation. Dùng hằng số thay cho string literal ở nhiều assembler giúp thay đổi vocabulary có kiểm soát và dễ rà soát.

Có thể tách vocabulary theo bounded context nếu hệ thống lớn, ví dụ `OrderRelations`, `PaymentRelations` và `CustomerRelations`. Tránh tạo một class chứa hàng trăm relation không liên quan hoặc định nghĩa cùng một relation nhiều lần với các URI khác nhau.

## 6. Gắn custom relation vào Link

Spring HATEOAS cho phép gắn một `LinkRelation` vào link bằng `withRel(...)` hoặc tạo link trực tiếp bằng `Link.of(...)`:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link paymentsLink = linkTo(methodOn(PaymentController.class)
        .allForOrder(order.getId()))
        .withRel(OrderRelations.PAYMENTS);
```

`methodOn(...)` tham chiếu handler để Spring HATEOAS suy ra URI từ mapping controller. `withRel(OrderRelations.PAYMENTS)` gắn ngữ nghĩa domain vào link. Khi route thay đổi, link builder vẫn dựa vào mapping thay vì một chuỗi URL tự ghép.

Nếu chỉ có sẵn URI đích, có thể tạo link trực tiếp:

```java
Link invoiceLink = Link.of(
        invoiceUri,
        OrderRelations.INVOICE);
```

Trong cả hai trường hợp, relation vẫn là hợp đồng ngữ nghĩa. Client nên theo `href` do server trả về và sử dụng relation để nhận biết loại quan hệ.

## 7. Ví dụ domain: Order liên kết Payments và Invoice

Giả sử một đơn hàng có thể có nhiều khoản thanh toán và tối đa một hóa đơn. Controller khai báo các endpoint liên quan:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class PaymentController {

    private final PaymentService paymentService;

    PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @GetMapping("/{orderId}/payments")
    CollectionModel<EntityModel<PaymentRepresentation>> allForOrder(
            @PathVariable("orderId") UUID orderId) {
        // Trả về các khoản thanh toán của đơn hàng.
        return paymentService.findAllForOrder(orderId);
    }
}
```

Ví dụ này minh họa mapping endpoint; kiểu trả về thực tế có thể được xây bằng `RepresentationModelAssembler` tương ứng. Trong assembler của Order, thêm các link theo điều kiện nghiệp vụ:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    EntityModel<OrderRepresentation> model = EntityModel.of(
            OrderRepresentation.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId())).withSelfRel());

    if (order.hasPayments()) {
        model.add(linkTo(methodOn(PaymentController.class)
                .allForOrder(order.getId()))
                .withRel(OrderRelations.PAYMENTS));
    }

    if (order.hasInvoice()) {
        model.add(Link.of(order.getInvoiceHref(), OrderRelations.INVOICE));
    }

    return model;
}
```

Link `payments` xuất hiện khi đơn hàng có khoản thanh toán; link `invoice` xuất hiện khi hóa đơn đã được phát hành. Điều kiện công bố link là một phần của trạng thái nghiệp vụ mà API muốn client khám phá. Client không cần biết quy tắc nội bộ để quyết định có nên hiển thị khả năng xem khoản thanh toán hay hóa đơn.

`OrderController`, `Order`, `OrderRepresentation` và `PaymentService` trong ví dụ là các kiểu miền/ứng dụng giả định. Khi tích hợp, giữ assembler và controller của dự án theo cấu trúc thực tế.

`Order.getInvoiceHref()` trong ví dụ trả về URL hóa đơn dưới dạng `String`; nếu domain model đang giữ `URI`, hãy chuyển sang biểu diễn URI phù hợp với overload `Link.of(...)` mà ứng dụng sử dụng.

## 8. CURIE: rút gọn custom relation trong HAL

Một extension relation được định danh bằng URI tuyệt đối có thể khá dài. HAL hỗ trợ CURIE (Compact URI) để biểu diễn relation có namespace ngắn hơn. Ví dụ URI relation:

```text
https://api.acme.example/rels/payments
```

có thể được serialize dưới dạng:

```text
acme:payments
```

Response HAL có thể chứa khai báo CURIE và link đã được rút gọn:

```json
{
  "_links": {
    "curies": [
      {
        "name": "acme",
        "href": "https://api.acme.example/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "https://api.acme.example/orders/ORD-1042"
    },
    "acme:payments": {
      "href": "https://api.acme.example/orders/ORD-1042/payments"
    }
  }
}
```

CURIE không thay đổi ngữ nghĩa của relation. Nó chỉ cung cấp cách viết gọn trong representation HAL. Client có thể mở rộng `acme:payments` dựa vào CURIE declaration để tìm URI relation đầy đủ và tài liệu mô tả.

## 9. Cấu hình CurieProvider trong Spring HATEOAS

Spring HATEOAS cung cấp `CurieProvider` và `DefaultCurieProvider` để tạo CURIE cho custom relation khi dùng HAL. Có thể đăng ký provider như một bean:

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
                "acme",
                UriTemplate.of("https://api.acme.example/rels/{rel}"));
    }
}
```

Tên namespace `acme` được dùng trước dấu hai chấm. URI template `{rel}` xác định cách mở rộng tên relation thành URI đầy đủ. Khi HAL được cấu hình trong Spring HATEOAS, provider cho phép serializer tạo phần `curies` và rút gọn custom relation phù hợp.

Chỉ cấu hình CURIE khi media type HAL được dùng và hypermedia support HAL đã được bật. Với Spring Boot starter, phần hỗ trợ HAL thường được auto-configure; trong cấu hình thủ công, hãy bật hypermedia type HAL tương ứng. Các media type khác có thể biểu diễn relation URI đầy đủ hoặc áp dụng quy tắc riêng. Không giả định JSON thông thường tự hiểu CURIE.

## 10. Chọn tên relation và namespace

Một vocabulary tốt giúp client hiểu quan hệ mà không cần biết implementation. Khi thiết kế, nên thống nhất các nguyên tắc:

- Dùng danh từ hoặc cụm danh từ diễn tả resource đích/quan hệ, ví dụ `payments`, `invoice`, `shipment`.
- Dùng cùng một relation cho cùng ngữ nghĩa ở mọi endpoint.
- Không tái sử dụng một relation cho các đích khác loại chỉ vì chúng có cùng URI pattern.
- Ưu tiên relation chuẩn nếu định nghĩa chuẩn khớp hoàn toàn.
- Dùng URI tuyệt đối ổn định cho extension relation.
- Chọn một CURIE prefix ngắn, duy nhất trong representation, ví dụ `acme`.
- Viết tài liệu cho từng relation để consumer hiểu semantics và cardinality.

Không dùng relation như `getPayment`, `loadInvoice` hoặc `clickToShip` nếu mục đích là mô tả quan hệ đến resource. Tên như vậy trộn lẫn quan hệ dữ liệu với hành động hoặc chi tiết giao diện. Nếu cần mô tả hành động, dùng affordance cùng HTTP method và input metadata.

## 11. Relation khác affordance như thế nào?

Relation và affordance có liên quan nhưng không thay thế nhau:

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| Link relation | Ý nghĩa quan hệ giữa resource nguồn và resource đích | `acme:payments` |
| Affordance | Thao tác client có thể thực hiện, gồm method và dữ liệu đầu vào/đầu ra | `GET`, `POST` hoặc `DELETE` với metadata tương ứng |
| URI template | Các biến có thể mở rộng trong URI | `{?status,page,size}` |

Một link `acme:payments` có thể chỉ dẫn đến collection payment. Nếu collection đó có thao tác tạo payment, affordance có thể mô tả `POST` và request body. Relation vẫn nói link trỏ đến khoản thanh toán; affordance nói client có thể tương tác với endpoint bằng cách nào.

Không mã hóa HTTP method vào tên relation. Cùng một resource đích có thể hỗ trợ nhiều thao tác và các thao tác có thể thay đổi theo trạng thái hoặc quyền của caller.

## 12. Client nên tiêu thụ custom relation ra sao?

Client hypermedia nên xem relation là một định danh ngữ nghĩa. Ví dụ, client nhận `acme:payments` thì có thể:

1. Đọc CURIE declaration để mở rộng tên relation thành URI đầy đủ.
2. Tra tài liệu relation nếu cần hiểu sâu hơn về semantics.
3. Dùng `href` trong link để điều hướng đến collection payment.
4. Đọc link và affordance trong response mới để khám phá khả năng tiếp theo.

Client không nên phân tích `href` để đoán rằng `/orders/{id}/payments` là endpoint payment. Server có thể chuyển route sang một service khác hoặc thay đổi cấu trúc URI nhưng giữ relation và semantics ổn định.

Client tổng quát không nhất thiết phải hiểu mọi custom relation. Nó vẫn có thể lưu hoặc hiển thị link như một quan hệ chưa biết, trong khi client chuyên biệt có thể hiểu URI relation đã được tài liệu hóa và cung cấp trải nghiệm phù hợp.

## 13. Quản lý thay đổi vocabulary

Custom relation là một phần của hợp đồng công khai. Khi đã phát hành, client có thể phụ thuộc vào tên và ngữ nghĩa của nó. Vì vậy:

- Không đổi URI relation chỉ vì đổi tên class hoặc package.
- Không thay đổi semantics hiện có để phù hợp với một tính năng mới.
- Nếu cần ngữ nghĩa khác, tạo relation mới và duy trì relation cũ trong giai đoạn tương thích.
- Cập nhật tài liệu relation và ví dụ representation.
- Kiểm thử các consumer quan trọng khi thay đổi cách serialize relation.
- Dùng cùng một CURIE prefix và URI template trong toàn bộ API.

Nếu chỉ muốn thay đổi URL đích, có thể cập nhật `href` mà vẫn giữ relation. Đây là lợi ích quan trọng của việc tách semantics khỏi địa chỉ tài nguyên.

## 14. Kiểm thử custom relation

Unit test có thể kiểm tra relation được gắn đúng vào model:

```java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.assertj.core.api.Assertions.assertThat;

class OrderModelAssemblerTest {

    @Test
    void addsPaymentsRelationWhenOrderHasPayments() {
        Order order = OrderFixtures.withPayments();
        EntityModel<OrderRepresentation> model =
                new OrderModelAssembler().toModel(order);

        Link payments = model.getRequiredLink(OrderRelations.PAYMENTS);

        assertThat(payments.getRel()).isEqualTo(OrderRelations.PAYMENTS);
        assertThat(payments.getHref()).contains("/payments");
    }
}
```

`OrderFixtures` là fixture test giả định. Assertion `href` ở đây chỉ xác nhận route hiện tại của ví dụ; kiểm thử hợp đồng quan trọng nhất vẫn là relation đúng và link có đích hợp lệ.

Với HAL, kiểm tra response đã serialize để xác nhận CURIE và tên relation:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCustomRelationTest {

    private static final UUID ORDER_ID = UUID.fromString(
            "a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Autowired
    MockMvc mockMvc;

    @Test
    void serializesCustomRelationWithCurie() throws Exception {
        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.curies[0].name").value("acme"))
                .andExpect(jsonPath("$._links['acme:payments'].href").exists());
    }
}
```

`ORDER_ID` cần được chuẩn bị trong dữ liệu test với một đơn hàng có khoản thanh toán để assembler thêm link. Nếu ứng dụng có nhiều CURIE provider hoặc thứ tự CURIE không cố định, nên kiểm tra bằng JSONPath lọc theo `name` thay vì cố định chỉ số `[0]`.

Nên kiểm tra thêm:

- Relation chuẩn được dùng đúng semantics.
- Custom relation URI là tuyệt đối và ổn định.
- CURIE prefix không trùng với prefix khác trong representation.
- URI template của CURIE mở rộng thành đúng relation URI.
- Link xuất hiện và biến mất theo trạng thái domain như hợp đồng quy định.
- Client vẫn theo `href` nếu route đích thay đổi.
- Relation không bị nhầm với affordance hoặc HTTP method.

## 15. Lỗi thường gặp

**Dùng relation tùy ý như một label giao diện:** tên relation cần diễn tả semantics ổn định của liên kết, không phải câu chữ nút bấm.

**Dùng relation chuẩn sai ngữ nghĩa:** client có thể hiểu nhầm link. Chỉ dùng IANA relation khi ý nghĩa khớp định nghĩa.

**Đặt extension relation bằng tên ngắn không namespace:** tên có thể va chạm với relation của API khác. Dùng URI tuyệt đối và CURIE trong HAL khi cần viết gọn.

**Nhúng method vào relation:** relation không thay thế affordance. Dùng metadata affordance để mô tả thao tác.

**Đổi semantics của relation đã phát hành:** client cũ có thể xử lý sai. Tạo relation mới khi ngữ nghĩa thay đổi.

**Cho rằng CURIE là một URL endpoint:** CURIE mở rộng tên relation thành URI định danh ngữ nghĩa; nó không nhất thiết là URL của resource đích.

**Cấu hình CURIE nhưng trả JSON thường:** CURIE là quy ước serialize của HAL. Client chỉ hiểu nó khi response dùng media type và cấu trúc hỗ trợ.

**Kiểm thử chỉ dựa trên `href`:** route có thể đổi mà semantics vẫn giữ nguyên. Kiểm thử relation và cấu trúc hypermedia bên cạnh đích link.

## 16. Checklist thiết kế custom relation

- Kiểm tra IANA registry trước khi định nghĩa relation mới.
- Chọn tên relation mô tả ngữ nghĩa domain rõ ràng.
- Dùng URI tuyệt đối ổn định cho extension relation.
- Tập trung hằng số relation trong vocabulary class.
- Gắn relation bằng `LinkRelation` khi tạo link trong Spring HATEOAS.
- Dùng `WebMvcLinkBuilder` hoặc method mapping để tạo `href`.
- Cấu hình `DefaultCurieProvider` nếu cần namespace relation trong HAL.
- Giữ semantics relation độc lập với route và implementation.
- Dùng affordance để mô tả method và input thay vì nhồi chúng vào tên relation.
- Tài liệu hóa semantics, cardinality và điều kiện xuất hiện của link.
- Kiểm thử relation, CURIE serialization và điều kiện nghiệp vụ.
- Quản lý thay đổi vocabulary theo nguyên tắc tương thích ngược.

Custom relation giúp API mô tả những mối quan hệ đặc thù của domain bằng một vocabulary có thể mở rộng. Khi relation được định danh ổn định, gắn đúng vào `Link` và serialize bằng CURIE trong HAL khi cần, client có thể hiểu ý nghĩa của liên kết mà không phụ thuộc vào cấu trúc URL hay implementation nội bộ của Spring application.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – HAL support and CURIEs](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS API – DefaultCurieProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html)
- [IANA Link Relation Types Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
