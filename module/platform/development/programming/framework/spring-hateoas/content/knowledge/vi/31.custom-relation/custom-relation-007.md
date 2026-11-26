# Đăng ký relation

Trong REST API có hypermedia, relation (quan hệ liên kết) cho client biết một link dẫn đến loại tài nguyên hoặc khả năng nào so với representation hiện tại. Ví dụ, một đơn hàng có thể công bố relation `customer` đến khách hàng, `payments` đến các khoản thanh toán hoặc `cancel` đến thao tác hủy. Tên relation là một phần hợp đồng công khai: client dựa vào nó để tìm link phù hợp mà không cần biết route nội bộ của server.

Spring HATEOAS hỗ trợ relation chuẩn qua `IanaLinkRelations`, đồng thời cho phép tạo relation riêng bằng `LinkRelation`. Khi relation gắn với kiểu tài nguyên, ứng dụng có thể khai báo tên bằng `@Relation` hoặc đăng ký quy tắc tập trung qua `LinkRelationProvider`. Với HAL, `CurieProvider` giúp biểu diễn URI relation dài bằng prefix ngắn, nhưng vẫn giữ được định danh đầy đủ cho client.

Bài học này giải thích cách chọn và định nghĩa custom relation, cách sử dụng `LinkRelation.of()`, `@Relation` và `LinkRelationProvider`, cách đăng ký provider như Spring bean, cách cấu hình CURIE trong HAL và cách kiểm thử relation trong response.

## 1. Relation mô tả ngữ nghĩa của link

Một link có hai thành phần cốt lõi:

- **Href**: URI hoặc URI template mà client có thể theo.
- **Relation**: ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và đích link.

Ví dụ một đơn hàng có link đến khách hàng:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "customer": {
      "href": "/customers/CUS-7"
    }
  }
}
~~~

Relation `customer` cho client biết link trỏ đến khách hàng của đơn hàng. Client không cần suy ra URL từ `customerId` hoặc tự ghép chuỗi `/customers/{id}`.

Relation không mô tả định dạng response. Nó mô tả mối quan hệ hoặc ý nghĩa điều hướng. Media type như `application/hal+json` mới quyết định cách biểu diễn link trong JSON.

Trong Spring HATEOAS, relation được biểu diễn bằng kiểu `LinkRelation`. Kiểu này giúp dùng relation như một giá trị có ngữ nghĩa rõ ràng thay vì truyền chuỗi tùy ý ở khắp nơi.

## 2. Relation chuẩn và custom relation

RFC 8288 phân biệt hai nhóm relation:

| Nhóm | Cách định danh | Khi sử dụng |
|---|---|---|
| Registered relation | Tên token đã đăng ký, ví dụ `self`, `next`, `edit` | Khi ngữ nghĩa đã có trong IANA Link Relation Registry |
| Extension relation | URI duy nhất do ứng dụng định nghĩa | Khi API cần một ngữ nghĩa riêng chưa có relation chuẩn phù hợp |

Trước khi tạo relation mới, hãy kiểm tra IANA registry. Nếu đã có relation chuẩn phù hợp, hãy dùng relation đó thay vì tạo một tên gần giống.

Với relation riêng, RFC 8288 quy định extension relation type là một URI duy nhất. URI nên thuộc quyền kiểm soát của tổ chức định nghĩa relation và nên dùng chữ thường nhất quán. URI có thể trỏ đến tài liệu mô tả ngữ nghĩa, nhưng client không nên tự động truy cập URI đó chỉ vì nhìn thấy relation.

Ví dụ, API có thể định nghĩa:

~~~text
https://api.example.com/rels/customer
https://api.example.com/rels/payments
https://api.example.com/rels/cancel
~~~

Những URI này phân biệt rõ các quan hệ trong hợp đồng API. Chúng không phải endpoint dữ liệu nhất thiết phải gọi; chúng là định danh cho ngữ nghĩa của relation.

Không cần gửi yêu cầu đăng ký IANA cho từng relation nội bộ của ứng dụng. Chỉ thực hiện quy trình đăng ký IANA nếu muốn đề xuất một relation dùng chung rộng rãi, có ngữ nghĩa ổn định và tài liệu đặc tả công khai.

## 3. Tạo custom relation trực tiếp bằng LinkRelation.of()

Khi một relation chỉ dùng cho một link cụ thể, có thể tạo trực tiếp bằng `LinkRelation.of(...)`.

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link payments = Link.of(
    "/orders/ORD-42/payments",
    LinkRelation.of("https://api.example.com/rels/payments")
);
~~~

`LinkRelation.of()` tạo một giá trị relation từ chuỗi không rỗng. Nó không đăng ký relation vào IANA, không lưu cấu hình toàn cục và không tự tạo URI đích. Nó chỉ cung cấp relation cho link đang xây dựng.

Nếu dùng một custom relation nhiều lần, nên khai báo hằng số để tránh sai khác chính tả:

~~~java
public final class ApiRelations {

    private ApiRelations() {
    }

    public static final LinkRelation PAYMENTS =
        LinkRelation.of("https://api.example.com/rels/payments");

    public static final LinkRelation CANCEL =
        LinkRelation.of("https://api.example.com/rels/cancel");
}
~~~

Sử dụng:

~~~java
Link paymentLink = Link.of(
    "/orders/ORD-42/payments",
    ApiRelations.PAYMENTS
);

Link cancelLink = Link.of(
    "/orders/ORD-42/cancellation",
    ApiRelations.CANCEL
);
~~~

Cách này phù hợp với relation của một hành động hoặc một liên kết đặc thù, không phụ thuộc vào tên lớp Java. Nếu relation được suy ra từ loại tài nguyên và dùng trong nhiều collection hoặc embedded representation, hãy cân nhắc `@Relation` hoặc `LinkRelationProvider`.

## 4. Dùng @Relation để đặt tên item và collection

Khi relation gắn với một kiểu representation, Spring HATEOAS cho phép khai báo tên item và collection bằng annotation `@Relation` trong package `org.springframework.hateoas.server.core`.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "https://api.example.com/rels/order",
    collectionRelation = "https://api.example.com/rels/orders"
)
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Hai thuộc tính có vai trò khác nhau:

- `itemRelation`: relation dùng khi tham chiếu một tài nguyên đơn.
- `collectionRelation`: relation dùng khi tham chiếu collection của kiểu tài nguyên đó.

Thuộc tính `value` là alias của `itemRelation`. Nếu chỉ cần khai báo tên item, có thể viết ngắn:

~~~java
@Relation(
    value = "https://api.example.com/rels/order",
    collectionRelation = "https://api.example.com/rels/orders"
)
public record OrderRepresentation(
    UUID id,
    String status
) {}
~~~

Khai báo tường minh cả hai tên giúp tránh phụ thuộc vào quy tắc suy luận số nhiều. Điều này đặc biệt hữu ích khi tên miền có quy tắc số nhiều bất quy tắc hoặc relation công khai không trùng với tên class.

### 4.1. Relation ảnh hưởng đến _embedded

Khi serialize collection theo HAL, Spring HATEOAS dùng collection relation để đặt tên khóa trong `_embedded`.

Ví dụ:

~~~java
List<OrderRepresentation> orders = service.findSummaries();

CollectionModel<OrderRepresentation> model =
    CollectionModel.of(orders);
~~~

Với cấu hình CURIE ở phần sau, response có thể có dạng:

~~~json
{
  "_embedded": {
    "acme:orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING"
      },
      {
        "id": "ORD-43",
        "status": "DELIVERED"
      }
    ]
  }
}
~~~

Nếu không có CURIE, relation URI đầy đủ được dùng theo quy tắc của media type. Relation item được dùng khi một tài nguyên đơn xuất hiện trong ngữ cảnh cần tên item, chẳng hạn trong preview hoặc embedded representation tương ứng.

`@Relation` điều khiển tên relation của kiểu tài nguyên. Nó không đổi tên thuộc tính JSON như `id`, `status` hoặc `total`; việc đặt tên field thuộc trách nhiệm của Jackson và cấu hình serialization.

## 5. Quy tắc mặc định của LinkRelationProvider

Spring HATEOAS đóng gói việc ánh xạ kiểu Java sang relation trong interface `LinkRelationProvider`. Interface cung cấp hai phép tra cứu:

~~~java
LinkRelation getItemResourceRelFor(Class<?> type);

LinkRelation getCollectionResourceRelFor(Class<?> type);
~~~

Cơ chế mặc định tìm relation theo thứ tự khái quát:

1. Nếu kiểu được gắn `@Relation`, dùng giá trị annotation.
2. Nếu không, tên item mặc định được suy ra từ tên class đã viết thường chữ đầu; collection mặc định có thể được tạo bằng cách nối `List`.
3. Nếu thư viện EVO Inflector có trên classpath, Spring HATEOAS có thể dùng thuật toán số nhiều tiếng Anh để tạo collection relation.
4. Với controller được gắn `@ExposesResourceFor`, relation có thể được tra theo kiểu tài nguyên mà controller công bố.

Ví dụ nếu không khai báo annotation, một kiểu `OrderRepresentation` có thể tạo relation item dựa trên tên kiểu và collection relation theo quy tắc mặc định. Kết quả đó tiện cho prototype, nhưng không phải lúc nào cũng phù hợp với hợp đồng công khai.

Nếu tên class đổi từ `OrderRepresentation` sang `OrderSummary`, relation mặc định có thể đổi theo. Vì relation là hợp đồng mà client tiêu thụ, hãy khai báo tường minh nếu tên cần ổn định qua các lần refactor.

## 6. Khi nào cần LinkRelationProvider tùy chỉnh?

`@Relation` phù hợp khi mỗi kiểu tài nguyên có một cặp tên cố định. `LinkRelationProvider` phù hợp hơn khi quy tắc ánh xạ cần được tập trung hoặc tính toán theo loại tài nguyên.

Các tình huống thường cần provider riêng:

- Nhiều kiểu Java dùng chung quy ước relation theo module hoặc bounded context.
- Tên relation đến từ metadata của hệ thống.
- Có quy tắc tương thích với một hợp đồng API cũ.
- Muốn ánh xạ riêng relation item và collection cho một nhóm kiểu.
- Muốn tách tên relation công khai khỏi tên class và annotation trên DTO.

Provider chỉ quyết định relation cho một kiểu tài nguyên. Nó không tạo href, không tìm dữ liệu và không quyết định HTTP method. Việc xây dựng URI vẫn thuộc link builder, controller hoặc assembler.

Spring HATEOAS cung cấp các provider mặc định như `AnnotationLinkRelationProvider`, `DefaultLinkRelationProvider`, `EvoInflectorLinkRelationProvider` và `ControllerLinkRelationProvider`. Các provider được chọn theo `LookupContext` để xác định loại tra cứu và kiểu tài nguyên.

## 7. Cài đặt LinkRelationProvider tùy chỉnh

Ví dụ, ứng dụng có kiểu `ShipmentRepresentation` và muốn dùng relation cố định cho shipment đơn và collection shipment.

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
public class ShipmentRelationProvider
        implements LinkRelationProvider {

    private static final LinkRelation SHIPMENT =
        LinkRelation.of("https://api.example.com/rels/shipment");

    private static final LinkRelation SHIPMENTS =
        LinkRelation.of("https://api.example.com/rels/shipments");

    @Override
    public boolean supports(LinkRelationProvider.LookupContext context) {
        return context.handlesType(ShipmentRepresentation.class);
    }

    @Override
    public LinkRelation getItemResourceRelFor(Class<?> type) {
        return SHIPMENT;
    }

    @Override
    public LinkRelation getCollectionResourceRelFor(Class<?> type) {
        return SHIPMENTS;
    }
}
~~~

`supports(...)` cho biết provider này xử lý kiểu nào. Ví dụ chỉ nhận `ShipmentRepresentation`; các kiểu khác được provider phù hợp khác xử lý.

`LookupContext` có thể biểu diễn tra cứu item, collection hoặc cả hai:

~~~java
LinkRelationProvider.LookupContext.forItemResourceRelLookup(
    ShipmentRepresentation.class
);

LinkRelationProvider.LookupContext.forCollectionResourceRelLookup(
    ShipmentRepresentation.class
);

LinkRelationProvider.LookupContext.forType(
    ShipmentRepresentation.class
);
~~~

Trong implementation, `context.handlesType(...)` giúp giới hạn phạm vi provider. Không nên trả `true` cho mọi kiểu nếu provider chỉ hiểu một nhóm tài nguyên, vì điều đó có thể che mất các provider mặc định hoặc provider chuyên biệt khác.

Nếu nhiều provider cùng trả về `true` cho một LookupContext, kết quả lựa chọn phụ thuộc thứ tự provider trong registry. Tránh để các provider tùy chỉnh chồng lấn phạm vi; nếu cần thứ tự ưu tiên, khai báo ordering phù hợp bằng `Ordered` hoặc `@Order` và kiểm thử kết quả trong ApplicationContext.

Các phương thức lấy item và collection relation được gọi sau khi provider được chọn. Vì vậy, mỗi phương thức phải trả relation đúng với kiểu mà provider nhận trách nhiệm xử lý.

Kiểu tài nguyên mà provider xử lý cần là một class thực tế trong ứng dụng, ví dụ:

~~~java
import java.util.UUID;

public record ShipmentRepresentation(
    UUID id,
    String status
) {}
~~~

## 8. Đăng ký provider như Spring bean

Khi bật hỗ trợ hypermedia, Spring HATEOAS tự đăng ký một `LinkRelationProvider` dạng ủy quyền. Cơ chế này tổng hợp các provider có trong ApplicationContext và chọn implementation phù hợp dựa trên `supports(LookupContext)`.

Trong ứng dụng Spring MVC cấu hình tường minh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;

@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL
)
public class HypermediaConfiguration {
}
~~~

Provider tùy chỉnh chỉ cần được đăng ký thành Spring bean, ví dụ dùng `@Component` như ở phần trước hoặc khai báo bằng `@Bean`:

~~~java
@Bean
ShipmentRelationProvider shipmentRelationProvider() {
    return new ShipmentRelationProvider();
}
~~~

Không khai báo thêm một provider tổng quát thay thế cơ chế ủy quyền do Spring HATEOAS tạo ra. Hãy để infrastructure mặc định tổng hợp các provider và chỉ đăng ký implementation tùy chỉnh cho những kiểu nó thực sự xử lý.

Với Spring Boot đã có auto-configuration cho Spring HATEOAS, hãy kiểm tra cấu hình hiện có trước khi thêm `@EnableHypermediaSupport` thủ công. Mục tiêu là có một bộ hạ tầng hypermedia nhất quán trong ApplicationContext, không đăng ký trùng converter hoặc cấu hình.

## 9. Dùng LinkRelationProvider trong code

Có thể inject `LinkRelationProvider` để lấy relation theo kiểu tài nguyên thay vì tự viết tên relation:

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
public class RelationLookup {

    private final LinkRelationProvider relations;

    public RelationLookup(LinkRelationProvider relations) {
        this.relations = relations;
    }

    public LinkRelation shipmentItemRelation() {
        return relations.getItemResourceRelFor(
            ShipmentRepresentation.class
        );
    }

    public LinkRelation shipmentCollectionRelation() {
        return relations.getCollectionResourceRelFor(
            ShipmentRepresentation.class
        );
    }
}
~~~

Có thể dùng kết quả để tạo link:

~~~java
Link shipmentLink = Link.of(
    "/shipments/SHP-42",
    relationLookup.shipmentItemRelation()
);
~~~

Trong thực tế, assembler hoặc component tạo representation thường là nơi tiêu thụ relation provider. Ví dụ này tách riêng thao tác tra cứu để làm rõ rằng provider trả về relation, còn link vẫn cần href do ứng dụng xác định.

## 10. Quan hệ từ controller với @ExposesResourceFor

Nếu muốn tra relation dựa trên controller class, Spring HATEOAS hỗ trợ `@ExposesResourceFor`. Annotation này khai báo kiểu tài nguyên mà controller quản lý.

~~~java
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@ExposesResourceFor(ShipmentRepresentation.class)
@RequestMapping("/shipments")
public class ShipmentController {
    // Các handler cho collection và item shipment
}
~~~

Khi controller được đánh dấu, `ControllerLinkRelationProvider` có thể ánh xạ controller sang relation của kiểu tài nguyên mà controller công bố. Ví dụ, khi tra relation của `ShipmentController.class`, infrastructure có thể dùng metadata `ShipmentRepresentation.class`.

Điều này hữu ích khi code tạo link làm việc với controller class, còn relation được quản lý theo kiểu representation. Hãy bảo đảm controller thật sự đại diện cho kiểu đã khai báo; không gắn một controller xử lý nhiều tài nguyên không liên quan vào cùng một loại nếu semantics của chúng khác nhau.

## 11. Dùng CURIE để rút gọn custom relation trong HAL

Extension relation là URI, nên nếu lặp lại URI đầy đủ trong mọi key relation, HAL JSON sẽ dài và khó đọc. HAL hỗ trợ CURIE (Compact URI Expression) để biểu diễn URI relation bằng prefix.

Ví dụ CURIE `acme` ánh xạ đến template:

~~~text
https://api.example.com/rels/{rel}
~~~

Relation đầy đủ:

~~~text
https://api.example.com/rels/orders
~~~

có thể được biểu diễn gọn thành:

~~~text
acme:orders
~~~

Trong Spring HATEOAS, có thể đăng ký `CurieProvider`:

~~~java
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
            UriTemplate.of(
                "https://api.example.com/rels/{rel}"
            )
        );
    }
}
~~~

Khi serialize HAL, Spring HATEOAS tự thêm link `curies` để client biết cách mở rộng prefix. Ví dụ:

~~~json
{
  "_links": {
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:payments": {
      "href": "/orders/ORD-42/payments"
    }
  }
}
~~~

Client có thể giải nghĩa `acme:payments` bằng CURIE đã công bố trong cùng response. CURIE không phải một relation mới và cũng không thay đổi ngữ nghĩa của URI relation gốc; nó chỉ là dạng viết gọn được media type hỗ trợ.

Spring HATEOAS chỉ cho phép một `CurieProvider` trong mỗi application scope. Nếu ứng dụng cần nhiều prefix, dùng constructor nhận map CURIE thay vì đăng ký nhiều bean `CurieProvider`.

## 12. Kết hợp @Relation với CURIE

Có thể dùng URI đầy đủ trong `@Relation`, sau đó để `CurieProvider` chuyển thành tên compact khi serialize HAL.

~~~java
@Relation(
    itemRelation = "https://api.example.com/rels/order",
    collectionRelation = "https://api.example.com/rels/orders"
)
public record OrderRepresentation(
    UUID id,
    String status
) {}
~~~

Khi collection được serialize, khóa embedded có thể là `acme:orders`. Khi một link dùng item relation, nó có thể xuất hiện dưới tên `acme:order`.

Ví dụ representation:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    },
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    }
  },
  "_embedded": {
    "acme:orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING"
      }
    ]
  }
}
~~~

Cách làm này giữ được URI relation đầy đủ trong metadata của ứng dụng, trong khi JSON gửi cho client ngắn gọn hơn. Client vẫn có thể phân giải relation thông qua CURIE.

Không nên dùng prefix CURIE mà không công bố mapping của nó trong response. Một client chỉ nhìn thấy `acme:orders` mà không có khai báo `curies` sẽ không có đủ thông tin để mở rộng relation.

## 13. Chọn đúng cơ chế cho từng nhu cầu

Ba cơ chế thường được dùng cho những phạm vi khác nhau:

| Nhu cầu | Cơ chế phù hợp | Phạm vi |
|---|---|---|
| Một link cụ thể có relation riêng | `LinkRelation.of(...)` | Từng link hoặc constant dùng lại |
| Một kiểu representation có item/collection rel cố định | `@Relation` | Một kiểu Java |
| Quy tắc ánh xạ relation tập trung hoặc theo loại tài nguyên | `LinkRelationProvider` | Một nhóm kiểu hoặc toàn ứng dụng |
| Rút gọn URI relation trong HAL | `CurieProvider` | Serialization HAL trong application scope |

Không cần tạo custom provider chỉ để đổi một relation trên một link. Ngược lại, không nên rải chuỗi URI relation vào nhiều assembler nếu cùng một quy tắc được áp dụng cho nhiều kiểu tài nguyên.

Một cách triển khai dễ bảo trì là bắt đầu bằng `@Relation` cho kiểu representation có tên cố định. Chỉ đưa vào `LinkRelationProvider` khi quy tắc cần tập trung hoặc phụ thuộc vào loại tài nguyên. Thêm `CurieProvider` khi API dùng HAL và muốn rút gọn các extension relation URI.

## 14. Kiểm thử relation provider

Có thể kiểm thử custom provider độc lập để xác nhận nó chỉ nhận đúng kiểu và trả đúng item/collection relation.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider.LookupContext;

import static org.assertj.core.api.Assertions.assertThat;

class ShipmentRelationProviderTest {

    private final ShipmentRelationProvider provider =
        new ShipmentRelationProvider();

    @Test
    void supportsShipmentRepresentationOnly() {
        assertThat(provider.supports(
            LookupContext.forItemResourceRelLookup(
                ShipmentRepresentation.class
            )
        )).isTrue();

        assertThat(provider.supports(
            LookupContext.forType(OrderRepresentation.class)
        )).isFalse();
    }

    @Test
    void returnsItemAndCollectionRelations() {
        assertThat(provider.getItemResourceRelFor(
            ShipmentRepresentation.class
        )).isEqualTo(
            LinkRelation.of("https://api.example.com/rels/shipment")
        );

        assertThat(provider.getCollectionResourceRelFor(
            ShipmentRepresentation.class
        )).isEqualTo(
            LinkRelation.of("https://api.example.com/rels/shipments")
        );
    }
}
~~~

Test này kiểm tra logic provider. Nó chưa chứng minh Spring đã phát hiện bean hoặc HAL serializer đã dùng relation đó. Vì vậy, cần có thêm integration test qua ApplicationContext hoặc MockMvc.

## 15. Kiểm thử relation trong HAL JSON

Integration test nên xác nhận cả CURIE và relation được dùng trong `_embedded` hoặc `_links`.

Ví dụ:

~~~java
import org.springframework.hateoas.MediaTypes;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.curies.name").value("acme"))
    .andExpect(jsonPath("$._embedded['acme:orders']").isArray());
~~~

Nếu endpoint công bố một custom link riêng, kiểm tra relation đó:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['acme:payments'].href"
    ).exists());
~~~

Các test trên giả định:

- Endpoint thực sự trả HAL JSON.
- CURIE provider đã được đăng ký.
- Relation URI nằm dưới base URI của CURIE `acme`.
- Fixture có collection hoặc link tương ứng.

Nếu response không có relation như mong đợi, hãy kiểm tra lần lượt kiểu Java được serialize, annotation `@Relation`, provider có được đăng ký làm bean, kết quả `supports(...)` và cấu hình CURIE.

## 16. Những lỗi thường gặp khi đăng ký relation

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng relation chuẩn cho ngữ nghĩa riêng | Client có thể hiểu sai khả năng hoặc loại tài nguyên | Dùng extension relation URI |
| Tạo relation tùy chỉnh bằng chuỗi ngắn không có namespace | Dễ trùng tên với API khác và khó nhận diện toàn cục | Dùng URI thuộc quyền kiểm soát của tổ chức |
| Chỉ khai báo itemRelation mà quên collectionRelation | Tên relation collection rơi về quy tắc mặc định | Khai báo cả hai nếu hợp đồng cần tên ổn định |
| Đổi tên class rồi dựa vào relation mặc định | Relation công khai có thể đổi theo tên class | Dùng `@Relation` hoặc provider |
| Provider nhận mọi LookupContext | Có thể che provider mặc định hoặc provider khác | Giới hạn bằng `supports(...)` |
| Dùng provider cho một link hành động đơn lẻ | Tạo abstraction không cần thiết | Dùng `LinkRelation.of(...)` |
| Nhầm @Relation với tên field JSON | Thay đổi relation nhưng không đổi field hoặc ngược lại | Dùng Jackson cho field, @Relation cho relation |
| Dùng CURIE nhưng không xuất link curies | Client không mở rộng được prefix | Đăng ký CurieProvider và kiểm thử response |
| Đăng ký nhiều CurieProvider | Cấu hình HAL mơ hồ hoặc không hợp lệ | Dùng một provider với map nhiều prefix nếu cần |
| Coi relation là quyền truy cập | Client có thể gọi link nhưng server vẫn phải từ chối | Kiểm tra authentication và authorization ở endpoint |

## 17. Quy trình thiết kế và đăng ký custom relation

Khi thêm một relation mới cho API, hãy thực hiện theo thứ tự:

1. Xác định ngữ nghĩa chính xác của mối quan hệ giữa tài nguyên hiện tại và đích link.
2. Kiểm tra IANA registry để xem đã có relation chuẩn phù hợp chưa.
3. Nếu cần extension relation, tạo URI ổn định thuộc quyền kiểm soát của tổ chức.
4. Chọn `LinkRelation.of()` cho link riêng, `@Relation` cho kiểu representation hoặc `LinkRelationProvider` cho quy tắc tập trung.
5. Nếu dùng provider, chỉ cho provider nhận những kiểu tài nguyên mà nó thực sự quản lý.
6. Đăng ký provider như Spring bean và bật hạ tầng hypermedia phù hợp.
7. Nếu dùng HAL, cấu hình một `CurieProvider` khi muốn rút gọn extension relation URI.
8. Kiểm thử item relation, collection relation, CURIE và cấu trúc `_links`/`_embedded`.
9. Tài liệu hóa relation như một phần hợp đồng API và giữ ngữ nghĩa ổn định qua các phiên bản.

Relation tùy chỉnh giúp API diễn đạt những mối quan hệ đặc thù của miền nghiệp vụ mà bộ IANA chưa có. Spring HATEOAS cung cấp nhiều mức khai báo: từ một `LinkRelation` cho link cụ thể, `@Relation` cho kiểu representation đến `LinkRelationProvider` cho quy tắc toàn ứng dụng. Khi relation được định danh bằng URI ổn định, có thể rút gọn bằng CURIE trong HAL và được kiểm thử như hợp đồng công khai, client có thể điều hướng dựa trên ngữ nghĩa thay vì phụ thuộc vào tên class hoặc route nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [LinkRelationProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [LinkRelationProvider.LookupContext API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.LookupContext.html)
- [Relation Annotation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [DelegatingLinkRelationProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/DelegatingLinkRelationProvider.html)
- [CurieProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/CurieProvider.html)
- [DefaultCurieProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/DefaultCurieProvider.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)

