# Nested embedded trong Spring HATEOAS

Nested embedded là cách biểu diễn một tài nguyên được nhúng bên trong tài nguyên khác, trong khi tài nguyên được nhúng vẫn có thể chứa các tài nguyên nhúng sâu hơn. Với HAL, cấu trúc này được thể hiện bằng các lớp _embedded lồng nhau. Nó giúp máy khách nhận một phần dữ liệu liên quan trong cùng response và tiếp tục khám phá các quan hệ ở từng cấp.

Trong Spring HATEOAS, **HalModelBuilder** được thiết kế để tạo các HAL representation phức tạp. Builder có thể nhúng object thông thường hoặc một HAL representation đã có link và embedded resources. Vì vậy, một đơn hàng có thể nhúng khách hàng, khách hàng nhúng địa chỉ, còn đơn hàng nhúng thêm danh sách mặt hàng. Mỗi cấp vẫn giữ relation và link của chính nó.

## 1. Nested embedded là gì?

Giả sử API trả về tài nguyên đơn hàng. Máy khách thường cần thông tin đơn hàng, người mua và danh sách mặt hàng. Nếu chỉ trả về link, máy khách phải gọi thêm endpoint để lấy thông tin khách hàng và mặt hàng. Nếu nhúng các phần dữ liệu thường xuyên được dùng cùng nhau, máy khách có thể nhận một response giàu thông tin hơn.

Một cấu trúc HAL có thể trông như sau:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "An Nguyen",
      "_links": {
        "self": {
          "href": "/customers/7"
        }
      },
      "_embedded": {
        "address": {
          "city": "Ho Chi Minh City",
          "_links": {
            "self": {
              "href": "/customers/7/address"
            }
          }
        }
      }
    },
    "items": [
      {
        "id": 3,
        "sku": "KB-01",
        "quantity": 2,
        "_links": {
          "self": {
            "href": "/orders/42/items/3"
          }
        }
      }
    ]
  }
}
~~~

Có ba cấp tài nguyên:

1. **order** là tài nguyên gốc.
2. **customer** và **items** là tài nguyên được nhúng trực tiếp trong order.
3. **address** được nhúng bên trong customer.

Mỗi embedded relation có tên riêng. Trong ví dụ, customer, items và address là relation keys nằm dưới _embedded. Các tài nguyên con cũng có thể có _links riêng để máy khách mở chúng độc lập.

Nested embedded là cấu trúc của hypermedia representation. Nó không bắt buộc object trong domain hoặc entity JPA phải có cùng cấu trúc lồng nhau.

## 2. Phân biệt embedded resource với object lồng nhau thông thường

Một object lồng nhau trong JSON chỉ là một phần dữ liệu:

~~~json
{
  "id": 42,
  "customer": {
    "id": 7,
    "name": "An Nguyen"
  }
}
~~~

Cấu trúc này không tự thể hiện customer là một tài nguyên hypermedia. Nó không có relation trong _embedded và cũng không nhất thiết có link để truy cập khách hàng độc lập.

Trong HAL, embedded resource được đặt dưới _embedded và được gắn với một link relation:

~~~json
{
  "id": 42,
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "An Nguyen",
      "_links": {
        "self": {
          "href": "/customers/7"
        }
      }
    }
  }
}
~~~

Điều đó giúp máy khách nhận biết customer là một tài nguyên liên quan được nhúng, có thể được truy cập qua link self. Nếu representation con lại có _embedded, cấu trúc trở thành nested embedded.

## 3. Khi nào nên nhúng nhiều cấp?

Không phải quan hệ nào trong domain cũng nên trở thành embedded resource. Quyết định nhúng cần dựa vào cách máy khách tiêu thụ dữ liệu.

| Trường hợp | Cách biểu diễn thường phù hợp |
|---|---|
| Dữ liệu nhỏ, gần như luôn được hiển thị cùng tài nguyên cha | Nhúng |
| Tóm tắt của tài nguyên liên quan | Nhúng preview |
| Tài nguyên có thể được truy cập độc lập | Cung cấp link; có thể nhúng nếu use case cần |
| Tập hợp lớn, cần phân trang hoặc lọc | Link tới collection endpoint |
| Dữ liệu nhạy cảm hoặc có quyền xem riêng | Chỉ nhúng sau khi kiểm tra quyền và giới hạn trường |
| Quan hệ có thể phát triển thành đồ thị sâu hoặc vòng lặp | Giới hạn độ sâu và dùng link cho phần còn lại |

Ví dụ, chi tiết khách hàng có thể được nhúng trong đơn hàng nếu màn hình đơn hàng luôn cần tên và thông tin liên hệ cơ bản. Danh sách lịch sử giao dịch của khách hàng có thể quá lớn để nhúng; nên công bố link tới collection giao dịch và để máy khách tải khi cần.

## 4. Dùng HalModelBuilder để tạo representation nhiều cấp

Spring HATEOAS cung cấp **HalModelBuilder** trong package org.springframework.hateoas.mediatype.hal. Đây là API chuyên biệt để tạo một HAL representation có payload chính, các embedded documents và các link.

Các phương thức thường dùng:

| Phương thức | Vai trò |
|---|---|
| halModelOf(entity) | Tạo builder với payload chính |
| emptyHalModel() | Tạo builder không có payload chính |
| embed(entity, relation) | Nhúng một object với relation được chỉ định |
| embed(collection, relation) | Nhúng một collection dưới relation được chỉ định |
| embed(collection, type) | Suy ra relation từ kiểu phần tử; hỗ trợ cả collection rỗng |
| link(link) | Thêm link vào representation cấp hiện tại |
| preview(entity).forLink(link) | Nhúng preview gắn với một link có cùng relation |
| build() | Tạo RepresentationModel cuối cùng |

Điểm quan trọng là embed(...) nhận được cả một HAL representation đã được tạo trước. Khi nhúng representation con, các link và embedded resources của nó vẫn nằm trong tài nguyên con đó. Đây là cơ chế để tạo cấu trúc nhiều cấp.

## 5. Tạo tài nguyên con trước, sau đó nhúng vào tài nguyên cha

Ví dụ đơn hàng có khách hàng và địa chỉ. Mỗi tài nguyên con được tạo bằng một HalModelBuilder riêng:

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

RepresentationModel<?> addressModel =
    HalModelBuilder.halModelOf(addressDto)
        .link(addressSelfLink)
        .build();

RepresentationModel<?> customerModel =
    HalModelBuilder.halModelOf(customerDto)
        .link(customerSelfLink)
        .embed(addressModel, LinkRelation.of("address"))
        .build();

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(customerModel, LinkRelation.of("customer"))
        .build();
~~~

Các biến addressDto, customerDto, orderDto là DTO đã được ánh xạ từ domain object. Các biến addressSelfLink, customerSelfLink và orderSelfLink là Link đã được tạo từ mapping controller hoặc URI phù hợp.

Luồng dựng model:

1. Tạo address representation và thêm link self.
2. Nhúng address representation vào customer dưới relation address.
3. Tạo customer representation và thêm link self.
4. Nhúng customer representation vào order dưới relation customer.
5. Tạo order representation gốc và thêm link self.

Khi serializer HAL xử lý representation gốc, nó có thể tạo _embedded.customer._embedded.address. Link self của từng cấp nằm trong representation tương ứng.

## 6. Nhúng một collection ở cấp con

Một đơn hàng thường có nhiều mặt hàng. Có thể tạo representation riêng cho từng mặt hàng rồi nhúng danh sách dưới relation items.

~~~java
import java.util.List;

List<?> itemModels = order.getItems().stream()
    .map(item -> HalModelBuilder.halModelOf(itemMapper.toDto(item))
        .link(itemLink(item))
        .build())
    .toList();

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(itemModels, LinkRelation.of("items"))
        .build();
~~~

Ở đây, mỗi item model có dữ liệu DTO và link self riêng. embed(itemModels, LinkRelation.of("items")) đặt toàn bộ danh sách dưới relation items.

HAL sẽ biểu diễn collection dưới dạng mảng:

~~~json
{
  "_embedded": {
    "items": [
      {
        "id": 3,
        "sku": "KB-01",
        "_links": {
          "self": {
            "href": "/orders/42/items/3"
          }
        }
      },
      {
        "id": 4,
        "sku": "MS-02",
        "_links": {
          "self": {
            "href": "/orders/42/items/4"
          }
        }
      }
    ]
  }
}
~~~

Nếu danh sách có thể lớn, không nên nhúng toàn bộ. Khi đó, hãy nhúng một vài item preview hoặc chỉ cung cấp link đến collection /orders/{id}/items để máy khách phân trang.

## 7. Kết hợp nested embedded trong một representation hoàn chỉnh

Có thể kết hợp khách hàng, địa chỉ và mặt hàng vào một order representation:

~~~java
List<?> itemModels = order.getItems().stream()
    .map(item -> HalModelBuilder.halModelOf(itemMapper.toDto(item))
        .link(itemLink(item))
        .build())
    .toList();

RepresentationModel<?> addressModel =
    HalModelBuilder.halModelOf(addressDto)
        .link(addressSelfLink)
        .build();

RepresentationModel<?> customerModel =
    HalModelBuilder.halModelOf(customerDto)
        .link(customerSelfLink)
        .embed(addressModel, LinkRelation.of("address"))
        .build();

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(customerModel, LinkRelation.of("customer"))
        .embed(itemModels, LinkRelation.of("items"))
        .build();
~~~

Kết quả có dạng khái quát:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "_links": {
        "self": {
          "href": "/customers/7"
        }
      },
      "_embedded": {
        "address": {
          "city": "Ho Chi Minh City",
          "_links": {
            "self": {
              "href": "/customers/7/address"
            }
          }
        }
      }
    },
    "items": [
      {
        "id": 3,
        "_links": {
          "self": {
            "href": "/orders/42/items/3"
          }
        }
      }
    ]
  }
}
~~~

Đây là ví dụ minh họa cấu trúc HAL. Các trường dữ liệu thực tế phụ thuộc DTO và serializer; các link cần được tạo theo mapping hoặc URI mà API công bố.

## 8. Dùng @Relation để đặt tên embedded relation nhất quán

Khi relation được suy ra từ kiểu representation, Spring HATEOAS có thể dùng **@Relation** để xác định tên item relation và collection relation.

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "orderItem",
    collectionRelation = "items"
)
public record OrderItemDto(
    Long id,
    String sku,
    Integer quantity
) {}
~~~

itemRelation mô tả tên relation cho một phần tử; collectionRelation mô tả tên relation cho collection. Điều này đặc biệt hữu ích khi serializer hoặc assembler cần suy ra tên relation từ kiểu dữ liệu.

Khi dùng HalModelBuilder.embed(collection, LinkRelation.of("items")), relation được truyền trực tiếp và không cần suy ra từ annotation. Chọn một quy ước ổn định cho toàn API, tránh để cùng một loại tài nguyên xuất hiện với các tên relation khác nhau ở các endpoint.

## 9. Preview cho tài nguyên có link riêng

Đôi khi máy khách cần một phần thông tin của tài nguyên liên quan nhưng vẫn cần link để mở bản đầy đủ. HAL hỗ trợ preview: representation nhúng một bản tóm tắt dưới cùng relation với link trỏ tới tài nguyên đầy đủ.

Với HalModelBuilder, có thể viết:

~~~java
import org.springframework.hateoas.Link;

Link customerLink = Link.of(
    "/customers/7",
    "customer"
);

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .preview(customerSummaryDto)
        .forLink(customerLink)
        .build();
~~~

Builder thêm link customer ở cấp order và đặt preview của khách hàng dưới _embedded.customer. Máy khách nhận được bản tóm tắt ngay trong response và có thể theo link để lấy tài nguyên đầy đủ.

Preview khác với việc nhúng toàn bộ representation khách hàng. Hãy chọn các trường tối thiểu đủ cho use case, chẳng hạn tên hiển thị và loại khách hàng, thay vì nhúng toàn bộ hồ sơ.

## 10. Collection rỗng và relation vẫn cần xuất hiện

Một collection rỗng vẫn có thể là một phần của hợp đồng API. Overload chỉ nhận collection không có type hoặc relation để suy ra tên khi collection rỗng, nên không thêm embedded entry. Khi muốn _embedded.items luôn xuất hiện dưới dạng mảng rỗng, hãy dùng overload nhận type hoặc LinkRelation tường minh.

Ví dụ:

~~~java
import java.util.List;

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(List.of(), OrderItemDto.class)
        .build();
~~~

Hoặc chỉ định relation trực tiếp:

~~~java
RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(List.of(), LinkRelation.of("items"))
        .build();
~~~

Kết quả có thể giữ cấu trúc:

~~~json
{
  "id": 42,
  "_embedded": {
    "items": []
  }
}
~~~

Điều này giúp máy khách phân biệt rõ collection rỗng với relation không được công bố. API cần chọn và duy trì một quy ước nhất quán.

## 11. Relation và link ở đúng cấp

Trong nested embedded, cần đặt link vào đúng representation. Link của order nằm ở cấp order; link của customer nằm bên trong customer; link của address nằm bên trong address.

Ví dụ:

~~~java
RepresentationModel<?> customerModel =
    HalModelBuilder.halModelOf(customerDto)
        .link(customerSelfLink)
        .build();

RepresentationModel<?> orderModel =
    HalModelBuilder.halModelOf(orderDto)
        .link(orderSelfLink)
        .embed(customerModel, LinkRelation.of("customer"))
        .build();
~~~

HalModelBuilder.link(...) thêm link vào representation đang được xây dựng. Nếu cần link thuộc tài nguyên con, hãy thêm link khi tạo builder của tài nguyên con trước khi nhúng nó vào cha.

Không nên thêm tất cả link vào builder gốc rồi mong serializer tự phân loại chúng theo object con. Link ở cấp nào thì phải được tạo trên representation của cấp đó.

## 12. Bảo đảm HAL serialization

HalModelBuilder tạo một RepresentationModel theo cấu trúc HAL, nhưng ứng dụng vẫn cần cấu hình hypermedia serialization để Spring chuyển model thành JSON có _links và _embedded. Trong Spring Boot MVC, cấu hình Spring HATEOAS thường được auto-configure khi dùng starter phù hợp. Với ứng dụng tự cấu hình, có thể bật HAL support bằng @EnableHypermediaSupport với HypermediaType.HAL.

Controller có thể trả về representation đã dựng:

~~~java
@GetMapping("/{id}")
public RepresentationModel<?> one(@PathVariable Long id) {
    Order order = orderService.findById(id);
    return orderHalAssembler.toModel(order);
}
~~~

Máy khách có thể yêu cầu HAL JSON bằng header:

~~~http
Accept: application/hal+json
~~~

Nếu ứng dụng có custom Jackson ObjectMapper hoặc message converter, cần xác nhận module HAL vẫn được đăng ký. Kiểm thử response HTTP giúp phát hiện trường hợp model Java có embedded data nhưng JSON đầu ra không có cấu trúc HAL như hợp đồng mong muốn.

HalModelBuilder là API đặc thù cho HAL. Nếu ứng dụng cần xuất nhiều media type hypermedia khác nhau, hãy cân nhắc tách logic tạo dữ liệu và link khỏi bước dựng HAL representation để không khóa toàn bộ tầng ứng dụng vào một định dạng.

## 13. Nested embedded và hiệu năng

Nhúng sâu làm response thuận tiện hơn cho máy khách nhưng cũng làm payload tăng nhanh. Nếu mỗi tài nguyên nhúng nhiều tài nguyên con, tổng số object có thể tăng theo cấp số nhân.

Ví dụ:

- Một order nhúng một customer và 10 items.
- Mỗi item lại nhúng product và category.
- Product lại nhúng inventory summary và supplier.

Một response tưởng như chỉ lấy một order có thể kéo theo hàng chục hoặc hàng trăm object. Việc này làm tăng thời gian truy vấn, dung lượng JSON, bộ nhớ và chi phí serialize.

Một số nguyên tắc:

- Giới hạn độ sâu embedded theo use case.
- Chỉ nhúng trường thực sự cần thiết.
- Không nhúng collection lớn nếu cần phân trang.
- Dùng preview cho dữ liệu liên quan chỉ cần tóm tắt.
- Dùng link cho tài nguyên độc lập hoặc ít được truy cập.
- Tránh vòng lặp quan hệ, chẳng hạn order nhúng customer rồi customer lại nhúng toàn bộ orders.

Nested embedded nên là một biểu diễn được chọn lọc, không phải bản sao toàn bộ đồ thị object của domain.

## 14. Quyền truy cập và dữ liệu nhạy cảm

Mỗi embedded resource là dữ liệu được công bố trong response của tài nguyên cha. Người dùng có quyền xem order không nhất thiết có quyền xem mọi thông tin customer, address hoặc payment.

Trước khi nhúng tài nguyên con, cần kiểm tra:

- Người gọi có quyền xem tài nguyên con không?
- Có trường nào nhạy cảm cần loại bỏ khỏi DTO không?
- Dữ liệu có thuộc tenant hoặc phạm vi truy cập của người gọi không?
- Việc nhúng có làm lộ quan hệ hoặc thông tin mà endpoint riêng đang bảo vệ không?

Không nên dựa vào việc link tới tài nguyên con bị ẩn để coi dữ liệu nhúng là an toàn. Nếu thông tin không được phép xem, không đưa nó vào embedded representation.

## 15. Cache và tính nhất quán dữ liệu

Một response chứa nested embedded kết hợp dữ liệu từ nhiều tài nguyên. Khi customer thay đổi tên hoặc address thay đổi, response order mới có thể khác dù bản thân order không đổi.

Điều này ảnh hưởng đến cache:

- Cache order representation có thể chứa snapshot customer cũ.
- ETag của response tổng có thể thay đổi khi tài nguyên con thay đổi.
- Chính sách cache của tài nguyên cha và tài nguyên con có thể khác nhau.
- Cache một response lớn làm mất lợi thế cache độc lập từng tài nguyên.

Nếu dữ liệu con thay đổi thường xuyên hoặc cần cache độc lập, link tới tài nguyên con có thể phù hợp hơn. Nếu dữ liệu cần đồng bộ theo một snapshot cho màn hình, nested embedded có thể là lựa chọn tốt.

## 16. Kiểm thử nested embedded bằng MockMvc

Kiểm thử cần xác nhận cấu trúc _embedded ở từng cấp, relation name và link của từng tài nguyên.

~~~java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.customer.id").value(7))
    .andExpect(jsonPath(
        "$._embedded.customer._links.self.href"
    ).exists())
    .andExpect(jsonPath(
        "$._embedded.customer._embedded.address._links.self.href"
    ).exists())
    .andExpect(jsonPath("$._embedded.items").isArray())
    .andExpect(jsonPath(
        "$._embedded.items[0]._links.self.href"
    ).exists());
~~~

Nên bổ sung kiểm thử cho:

- Relation customer, address và items đúng tên.
- Collection rỗng vẫn xuất hiện nếu hợp đồng yêu cầu mảng rỗng.
- Preview chỉ chứa các trường được phép công bố.
- Tài nguyên con không có quyền truy cập không xuất hiện trong response.
- Link self ở từng cấp trỏ đúng endpoint.
- Số lượng embedded được giới hạn theo yêu cầu.
- Response không chứa vòng lặp hoặc dữ liệu nhạy cảm.

Kiểm thử ở cấp HTTP quan trọng vì cấu trúc cuối cùng phụ thuộc HAL serializer và relation provider, không chỉ phụ thuộc object Java được tạo trong bộ nhớ.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm object lồng nhau với embedded resource | Máy khách không nhận được relation hypermedia | Dùng _embedded và relation rõ ràng |
| Nhúng DTO thô rồi kỳ vọng có link con | Tài nguyên con không có link riêng | Tạo HAL representation cho tài nguyên con rồi embed |
| Đưa link con vào builder cha | Link xuất hiện sai cấp | Thêm link khi xây representation con |
| Dùng relation suy ra không nhất quán | Máy khách khó tìm embedded resource | Dùng @Relation hoặc LinkRelation tường minh |
| Nhúng collection lớn | Response nặng và khó phân trang | Dùng link tới collection endpoint |
| Không khai báo type cho collection rỗng | Relation có thể không xuất hiện | Dùng overload embed(collection, type) hoặc relation |
| Nhúng toàn bộ entity JPA | Lộ trường nội bộ và kéo theo quan hệ không cần thiết | Ánh xạ sang DTO trước |
| Không kiểm tra quyền của tài nguyên con | Rò rỉ dữ liệu qua response cha | Áp dụng authorization trước khi embed |
| Tạo đồ thị embedded không giới hạn | Payload lớn hoặc vòng lặp | Giới hạn độ sâu và chuyển phần còn lại thành link |

## 18. Quy trình thiết kế nested embedded

Khi xây dựng nested embedded bằng Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định tài nguyên gốc và các quan hệ mà máy khách thường cần.
2. Quyết định quan hệ nào nên nhúng, quan hệ nào chỉ cần link.
3. Thiết kế DTO riêng cho từng cấp để giới hạn dữ liệu công khai.
4. Tạo representation con bằng HalModelBuilder và thêm link của chính tài nguyên con.
5. Nhúng representation con vào representation cha bằng relation rõ ràng.
6. Dùng @Relation hoặc LinkRelation để duy trì tên relation ổn định.
7. Xử lý collection rỗng với type hoặc relation tường minh nếu hợp đồng yêu cầu.
8. Giới hạn độ sâu, kích thước payload và dữ liệu nhạy cảm.
9. Kiểm thử cấu trúc _embedded, _links ở mọi cấp bằng response HTTP thực tế.

Nested embedded cho phép một HAL representation mô tả các tài nguyên liên quan theo nhiều cấp, đồng thời giữ relation và link của từng tài nguyên con. HalModelBuilder hỗ trợ dựng cấu trúc này bằng cách tạo representation con trước rồi nhúng vào representation cha. Khi chọn đúng dữ liệu, giới hạn độ sâu và kiểm soát quyền truy cập, nested embedded giúp máy khách nhận đủ thông tin cho use case mà vẫn giữ khả năng điều hướng hypermedia.
