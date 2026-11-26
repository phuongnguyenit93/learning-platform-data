# Client không hard-code URI

Một client REST có hypermedia không cần tự biết cấu trúc đường dẫn của mọi tài nguyên. Client bắt đầu từ một **entry point** đã được cấu hình, đọc các link mà server công bố, tìm link theo relation có ý nghĩa và theo URI trong link đó. Khi server thay đổi route, thêm gateway prefix hoặc chuyển tài nguyên sang một host khác, client vẫn có thể hoạt động nếu hợp đồng relation được giữ ổn định.

Spring HATEOAS hỗ trợ cách thiết kế này ở phía server bằng các representation model và link builder. Ở phía client, thư viện **Traverson** của Spring HATEOAS giúp đi theo chuỗi relation trong hypermedia response. Client vẫn cần biết ngữ nghĩa mà nó muốn tìm, chẳng hạn relation `orders` hoặc `search`, nhưng không cần ghép `/orders/{id}`, tự nối query string hay đoán endpoint tiếp theo.

Bài học này giải thích ranh giới giữa entry point, relation và URI; cách khám phá API từ HAL; cách dùng Traverson; cách xử lý URI template, link tương đối, collection và pagination; cùng các nguyên tắc tương thích, kiểm thử và xử lý lỗi khi API tiến hóa.

## 1. Hard-code URI tạo ra coupling như thế nào?

Một client truyền thống thường ghép URL từ các quy ước nội bộ mà client và server cùng biết:

~~~java
String uri = baseUrl + "/orders/" + orderId;
OrderDto order = restClient.get()
    .uri(uri)
    .retrieve()
    .body(OrderDto.class);
~~~

Cách này có vẻ đơn giản, nhưng client đã phụ thuộc vào nhiều chi tiết:

- Collection có tên `orders`.
- Item có dạng `/orders/{id}`.
- ID nằm trực tiếp trong path.
- Server không đổi cấu trúc route hoặc prefix.
- Tài nguyên vẫn nằm trên cùng host.
- Cách tìm kiếm và phân trang vẫn dùng query parameter mà client đã biết.

Nếu server chuyển endpoint thành `/api/v2/purchases/{id}`, client phải được cập nhật dù ý nghĩa nghiệp vụ “đơn hàng” không thay đổi. Khi có nhiều client, việc thay đổi route trở thành một đợt phối hợp phát hành.

Một client hypermedia dùng URI do server cung cấp:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/v2/purchases/ORD-42"
    }
  }
}
~~~

Client không cần biết đường dẫn được tạo từ controller nào. Nó chỉ cần tìm relation `self` và theo `href`.

**Điều cần loại bỏ là việc tự xây URI theo cấu trúc route.** Client vẫn có thể lưu entry point và biết relation nghiệp vụ mà nó cần. Đây là những phần của hợp đồng client-server, không phải hard-code topology của server.

## 2. Phân biệt entry point, relation và URI

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Entry point | URI bắt đầu mà client được cấu hình hoặc nhận từ bên ngoài | `https://api.example.test/` |
| Relation | Ngữ nghĩa của link mà client muốn tìm | `orders`, `self`, `next`, `search` |
| Href | URI đích cụ thể do server công bố | `https://api.example.test/api/v2/purchases` |

Entry point thường là một cấu hình ban đầu vì client phải biết nơi bắt đầu. Sau request đầu tiên, server có thể công bố các link để client tiếp tục điều hướng.

Relation cho biết link có ý nghĩa gì. Ví dụ, relation `orders` có thể dẫn đến collection đơn hàng; relation `customer` dẫn đến khách hàng liên quan. Client cần hiểu relation để thực hiện use case, nhưng không cần biết href được hình thành từ những path segment nào.

Href là địa chỉ thực tế. Server có thể thay đổi href theo môi trường, phiên bản, gateway hoặc cách định tuyến. Client phải sử dụng URI được cung cấp và xử lý nó bằng HTTP client phù hợp.

Một quy trình hypermedia điển hình:

~~~text
Configured entry point
        |
        v
      GET /
        |
        v
 Read HAL document
        |
        +---- find relation "orders"
        |           |
        |           v
        |       follow href
        |           |
        |           v
        |      collection
        |           |
        |           +---- find "next"
        |           |
        |           +---- find "search"
        |
        +---- find relation "profile"
                    |
                    v
               API metadata
~~~

Client không cần biết collection nằm ở `/orders`, `/api/v2/purchases` hay một host khác. Nó chỉ cần tìm đúng relation và theo href.

## 3. Relation là hợp đồng mà client cần biết

Không hard-code URI không có nghĩa client không cần biết gì về API. Client vẫn cần biết ngữ nghĩa nghiệp vụ của thao tác mà nó muốn thực hiện.

Ví dụ, ứng dụng màn hình đơn hàng có thể cần relation:

- `orders`: collection đơn hàng.
- `self`: tài nguyên hoặc collection hiện tại.
- `customer`: khách hàng liên quan.
- `search`: khả năng tìm kiếm.
- `next` và `prev`: điều hướng giữa các trang.

Các relation chuẩn như `self`, `next`, `prev` có ngữ nghĩa được đăng ký trong IANA Link Relation Registry. Relation tùy chỉnh như `orders` hoặc `customer` cần được API tài liệu hóa và giữ ngữ nghĩa ổn định.

Với relation chuẩn, Spring HATEOAS cung cấp hằng số trong `IanaLinkRelations`:

~~~java
import org.springframework.hateoas.IanaLinkRelations;

IanaLinkRelations.SELF;
IanaLinkRelations.NEXT;
IanaLinkRelations.PREV;
IanaLinkRelations.SEARCH;
~~~

Với relation tùy chỉnh, client có thể dùng tên relation mà API đã công bố:

~~~java
Link orders = model.getRequiredLink("orders");
~~~

Nếu API sử dụng extension relation dạng URI hoặc CURIE, client cần dùng khả năng phân giải relation của HAL client/library phù hợp. Không nên tự bỏ prefix hoặc tự ghép URI relation theo phỏng đoán.

Relation cần ổn định về ngữ nghĩa. Nếu relation `orders` trước đây dẫn đến collection đơn hàng mà sau đó lại dẫn đến báo cáo doanh thu, client có thể vẫn tìm thấy link nhưng hành vi sẽ sai. Hãy tạo relation mới khi ý nghĩa thực sự khác.

## 4. Server công bố entry point và các link

Spring HATEOAS giúp server tạo representation có link. Ví dụ API có root resource công bố collection đơn hàng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class ApiRootProcessor implements
        RepresentationModelProcessor<EntityModel<ApiRoot>> {

    @Override
    public EntityModel<ApiRoot> process(EntityModel<ApiRoot> model) {
        Link orders = linkTo(
            methodOn(OrderController.class).all()
        ).withRel("orders");

        if (!model.hasLink("orders")) {
            model.add(orders);
        }

        return model;
    }
}
~~~

Ví dụ minh họa cách thêm relation vào root representation. Trong ứng dụng thực tế, root resource có thể được tạo bằng controller hoặc cấu hình riêng; điều quan trọng là response entry point công bố link tới các khả năng chính.

Client gọi entry point:

~~~http
GET / HTTP/1.1
Accept: application/hal+json
~~~

Response có thể là:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/"
    },
    "orders": {
      "href": "https://api.example.test/api/v2/purchases"
    },
    "profile": {
      "href": "https://api.example.test/profile"
    }
  }
}
~~~

Server có thể đổi đường dẫn collection mà không cần thay đổi relation `orders`. Client tìm relation đó trong response và theo href mới.

Một root resource không nhất thiết phải chứa mọi link trong toàn hệ thống. Nó có thể công bố các tài nguyên gốc hoặc khả năng cấp cao, sau đó mỗi tài nguyên tiếp tục công bố các link phù hợp với ngữ cảnh của nó.

## 5. Client HAL đọc link theo relation

Nếu client đã nhận một representation dưới dạng `EntityModel<T>`, nó có thể lấy link bằng relation:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

EntityModel<OrderRepresentation> order = /* decoded HAL response */;

Link self = order.getRequiredLink(IanaLinkRelations.SELF);
String selfHref = self.getHref();
~~~

`getRequiredLink(...)` phù hợp khi relation là bắt buộc theo hợp đồng mà client đang sử dụng. Nếu relation có thể không xuất hiện, dùng `getLink(...)` và xử lý trường hợp thiếu:

~~~java
order.getLink("customer").ifPresent(customerLink -> {
    // Theo customerLink.getHref() khi use case cần dữ liệu khách hàng
});
~~~

Không nên gọi `getRequiredLink(...)` cho mọi relation tùy chọn rồi để exception trở thành luồng điều khiển bình thường. Nếu một hành động hoặc association không có trong response, client cần quyết định có thể bỏ qua, ẩn thao tác hay báo lỗi theo use case.

Ví dụ, relation `cancel` có thể chỉ xuất hiện khi đơn hàng đang ở trạng thái cho phép hủy. Client có thể ẩn nút hủy khi link vắng mặt. Server vẫn phải kiểm tra trạng thái và quyền khi nhận request hủy.

## 6. Dùng Traverson để đi theo relation

**Traverson** là client của Spring HATEOAS dùng để đi theo chuỗi link relation trong tài liệu hypermedia. Client cung cấp URI entry point và media type; sau đó dùng tên relation để di chuyển qua API.

Ví dụ tạo Traverson:

~~~java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
    URI.create("https://api.example.test/"),
    MediaTypes.HAL_JSON
);
~~~

Lấy collection đơn hàng từ relation `orders`:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

public record OrderSummary(String id, String status) {}

ParameterizedTypeReference<
    CollectionModel<EntityModel<OrderSummary>>> orderCollectionType =
        new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<OrderSummary>> orders =
    traverson.follow("orders")
        .toObject(orderCollectionType);
~~~

Client không ghi `/api/v2/purchases` ở bất kỳ đâu. Nó chỉ nêu relation `orders`; Traverson tải entry point, tìm relation tương ứng, theo href rồi chuyển response thành kiểu Java được yêu cầu.

Có thể theo nhiều relation liên tiếp:

~~~java
OrderSummary order =
    traverson.follow("orders", "featured")
        .toObject(OrderSummary.class);
~~~

Ví dụ chuỗi trên giả định collection hoặc tài nguyên được tìm thấy qua `orders` công bố tiếp relation `featured`. Mỗi tên trong chuỗi là relation ở response hiện tại, không phải path segment.

## 7. Theo self link của tài nguyên được nhúng

Một collection HAL có thể nhúng nhiều item. Mỗi item có thể công bố self link riêng:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/api/v2/purchases"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "status": "PROCESSING",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/v2/purchases/ORD-42"
          }
        }
      }
    ]
  }
}
~~~

Client có thể đọc dữ liệu tóm tắt từ embedded item. Khi cần tải lại chi tiết, nó dùng self link của item đó:

~~~java
Link orderLink = orderModel.getRequiredLink(IanaLinkRelations.SELF);
~~~

Nếu dùng HTTP client thông thường, gửi request đến `orderLink.getHref()`. Nếu dùng một hypermedia client, có thể dùng cơ chế theo link đã phát hiện để tải representation đích.

Không suy ra URI item bằng cách nối ID vào href collection. Href của item có thể nằm ở host khác, có prefix khác hoặc có dạng opaque mà client không cần hiểu.

## 8. URI template: client cung cấp giá trị, server cung cấp cấu trúc

Một link tìm kiếm có thể là URI template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/v2/purchases{?status,from,to,page,size}",
      "templated": true
    }
  }
}
~~~

Thuộc tính `templated: true` cho biết href cần được mở rộng theo quy tắc URI Template. Client biết giá trị muốn tìm, ví dụ status=PROCESSING, nhưng không phải tự tạo path hoặc tự đoán tên query parameter.

Với Traverson, có thể theo relation search và truyền template parameters:

~~~java
import java.util.Map;

CollectionModel<EntityModel<OrderSummary>> processingOrders =
    traverson.follow("orders", "search")
        .withTemplateParameters(
            Map.of(
                "status", "PROCESSING",
                "page", 0,
                "size", 20
            )
        )
        .toObject(orderCollectionType);
~~~

Ví dụ giả định collection relation `orders` công bố relation `search` có template variables tương ứng. Tên biến phải được lấy từ link thực tế; nếu server đổi `from` thành `createdAfter`, client cần theo metadata mới thay vì tiếp tục tự ghép query string cũ.

Không thay thế URI template bằng nối chuỗi:

~~~java
// Không nên: client đang tự sở hữu cấu trúc query string.
String uri = "/api/v2/purchases?status=" + status + "&page=" + page;
~~~

Dữ liệu đầu vào vẫn thuộc client, còn cách biểu diễn URI và tên biến được server công bố trong template.

Khi một traversal có nhiều hop template và mỗi hop cần bộ tham số khác nhau, có thể mô tả từng hop bằng **Hop** thay vì dùng một map chung cho cả traversal:

~~~java
import static org.springframework.hateoas.client.Hop.rel;

var item = traverson
    .follow(rel("items").withParameter("projection", "summary"))
    .follow("self")
    .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

Ví dụ giả định response sau hop items có một link relation self phù hợp. API Hop cho phép gắn tham số vào đúng relation cần mở rộng, hữu ích khi các bước điều hướng có URI template khác nhau.

## 9. Link phân trang thay cho tự tăng page

Với collection phân trang, response có thể công bố các relation:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/v2/purchases?status=PROCESSING&page=0&size=20"
    },
    "next": {
      "href": "/api/v2/purchases?status=PROCESSING&page=1&size=20"
    },
    "last": {
      "href": "/api/v2/purchases?status=PROCESSING&page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 87,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Client có thể tìm relation `next` và theo href:

~~~java
Link next = page.getRequiredLink(IanaLinkRelations.NEXT);
~~~

Không tự tính `page + 1` rồi dựng query string. Server có thể chuyển từ offset pagination sang cursor pagination, thay đổi page size hoặc thay đổi cách encode token. Nếu relation `next` vẫn được công bố, client tiếp tục điều hướng mà không cần biết cấu trúc bên trong.

Một vòng lặp duyệt trang có thể được mô tả như sau:

~~~text
GET collection link
       |
       v
 process current page
       |
       v
 find relation "next"
       |
       +---- absent ----> finish
       |
       v
 follow next.href
       |
       +----> process next page
~~~

Khi theo link next, server phải giữ các filter và sort có ý nghĩa của truy vấn hiện tại. Client không phải tự bảo toàn các tham số đó bằng cách sao chép query string.

## 10. Link tương đối và URI resolution

Href không bắt buộc phải là URI tuyệt đối. HAL có thể chứa link tương đối:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/v2/purchases/ORD-42"
    }
  }
}
~~~

Client cần phân giải URI tương đối dựa trên URI cơ sở của tài liệu chứa link theo quy tắc URI reference resolution. Không nên tự nối chuỗi bằng dấu gạch chéo vì cách đó có thể sai khi href là path-relative, query-relative hoặc chứa fragment.

Ví dụ về hai dạng:

| Href | Cách hiểu |
|---|---|
| `https://api.example.test/api/v2/purchases/42` | URI tuyệt đối |
| `/api/v2/purchases/42` | Path tuyệt đối tương đối với origin hiện tại |
| `purchases/42` | Path tương đối với URI cơ sở hiện tại |
| `?page=2` | Thay query của URI cơ sở |
| `#details` | Tham chiếu fragment |

HTTP client hoặc hypermedia client cần xử lý URI resolution đúng chuẩn. Với client tự viết, dùng URI API của nền tảng thay vì ghép string. Traverson xử lý việc điều hướng từ entry point và các link được phát hiện.

Ở phía server, Spring HATEOAS có thể tạo link tuyệt đối hoặc tương đối tùy cấu hình và request context. Nếu ứng dụng chạy sau reverse proxy hoặc API gateway, forwarded headers phải được cấu hình đúng để href công bố host, scheme và prefix mà client thực sự truy cập được.

## 11. Đừng nhầm relation với tên thuộc tính JSON

HAL sử dụng `_links` để công bố relation, còn dữ liệu tài nguyên vẫn có các thuộc tính JSON riêng.

Ví dụ:

~~~json
{
  "id": "CUS-7",
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "/customers/CUS-7"
    },
    "orders": {
      "href": "/customers/CUS-7/orders"
    }
  }
}
~~~

`name` là thuộc tính dữ liệu. `orders` là relation. Client tìm relation trong `_links`, không tìm một field tên orders trong phần dữ liệu.

Một API có thể đổi tên field dữ liệu theo version hoặc projection nhưng vẫn giữ relation ổn định. Ngược lại, relation có thể được bổ sung mà không cần thay đổi schema dữ liệu chính.

Khi client dùng HAL, hãy parse response theo cấu trúc hypermedia thay vì dùng JSONPath cố định như `$.orders.href` nếu API thực tế công bố link ở `$._links.orders.href`.

## 12. Khi relation không xuất hiện

Không phải response nào cũng có mọi relation. Một link có thể vắng mặt vì:

- Tài nguyên không có quan hệ đó.
- Hành động không hợp lệ ở trạng thái hiện tại.
- Người dùng hiện tại không được phép thấy khả năng đó.
- Endpoint hoặc tính năng chưa được bật trong cấu hình.
- API version hiện tại không hỗ trợ khả năng đó.

Client cần xử lý sự vắng mặt theo ngữ nghĩa. Ví dụ, nếu không có relation `cancel`, client có thể ẩn nút hủy. Nếu không có relation `next`, client kết thúc việc duyệt trang.

Không nên tự dựng URI thay thế khi relation không xuất hiện. Việc đoán đường dẫn có thể vượt qua ý định công bố khả năng của server và khiến client gọi endpoint không được hỗ trợ.

Nếu một relation bắt buộc theo hợp đồng của use case bị thiếu, client nên trả lỗi giao thức có thông tin rõ ràng hoặc chuyển sang trạng thái không hỗ trợ. Không biến mọi relation thiếu thành lỗi nghiêm trọng nếu chúng vốn là tùy chọn.

## 13. URI thay đổi nhưng relation giữ ổn định

Giả sử phiên bản đầu của API công bố:

~~~json
{
  "_links": {
    "orders": {
      "href": "/orders"
    }
  }
}
~~~

Sau khi server thay đổi route:

~~~json
{
  "_links": {
    "orders": {
      "href": "/api/v2/purchases"
    }
  }
}
~~~

Client vẫn tìm relation `orders`. Nó không cần biết rằng đường dẫn đã đổi từ `/orders` sang `/api/v2/purchases`.

Đây là lợi ích chính của điều hướng theo relation: server có thể thay đổi cấu trúc URI mà không buộc client thay đổi theo, miễn là:

- Entry point vẫn được cung cấp hoặc cấu hình được cập nhật có chủ đích.
- Relation giữ ngữ nghĩa tương thích.
- Href mới có thể truy cập từ client.
- Media type và cấu trúc representation vẫn nằm trong phạm vi client hỗ trợ.
- Quyền truy cập và semantics HTTP không thay đổi ngoài hợp đồng.

Hypermedia không tự bảo đảm tương thích hoàn toàn. Nếu server đổi relation `orders` thành `purchases` mà không duy trì alias hoặc version compatibility, client cũ vẫn không tìm thấy relation. Nếu dữ liệu response đổi cấu trúc không tương thích, client vẫn cần nâng cấp. Hypermedia giảm coupling vào URI topology, không xóa bỏ nhu cầu quản lý version và hợp đồng.

## 14. HAL-FORMS và affordance cho thao tác

Một link HAL cơ bản cho client biết đích URI và relation. Nó không nhất thiết mô tả đầy đủ HTTP method hoặc request body của một thao tác.

Nếu API cần công bố biểu mẫu thao tác, có thể dùng HAL-FORMS hoặc affordance phù hợp. HAL-FORMS bổ sung `_templates` để mô tả method, target, content type và các property đầu vào.

Ví dụ rút gọn:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    }
  },
  "_templates": {
    "cancel": {
      "method": "put",
      "target": "/orders/ORD-42/cancellation",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "required": true,
          "type": "text"
        }
      ]
    }
  }
}
~~~

Client có thể chọn template `cancel`, đọc method và property, sau đó gửi request theo metadata được công bố. Không suy luận rằng có relation `self` là được phép PUT hoặc DELETE tài nguyên.

Traverson chủ yếu hỗ trợ điều hướng theo link relation. Nếu client cần dựng form từ HAL-FORMS, nó cần parser hoặc client hỗ trợ HAL-FORMS; không nên giả định Traverson tự dựng giao diện hay thực thi mọi template.

## 15. Bảo mật: link không phải quyền truy cập

Việc server công bố hoặc ẩn link có thể giúp client hiểu khả năng hiện tại, nhưng không thay thế authorization.

Ví dụ, response của người quản lý có thể chứa relation `approve`, trong khi response của nhân viên thường không có link này. Đây là cách công bố affordance theo ngữ cảnh. Tuy vậy, endpoint approve vẫn phải kiểm tra quyền khi nhận request.

Client cũng không nên tin rằng mọi href nhận được đều an toàn để gọi. Cần áp dụng chính sách mạng và bảo mật của ứng dụng:

- Chỉ gọi các scheme và host được phép theo chính sách client.
- Không gửi access token đến host khác một cách tự động nếu chưa có quy tắc xác thực phù hợp.
- Xử lý redirect theo chính sách bảo mật.
- Không đưa thông tin nhạy cảm vào URI template hoặc query string nếu không phù hợp.
- Kiểm tra TLS và xác thực server như với mọi HTTP request.

Nếu server công bố link tuyệt đối đến một host dịch vụ khác, client cần quyết định có tin cậy host đó và cách truyền credentials. Hypermedia cung cấp địa chỉ và ngữ nghĩa; nó không thay thế trust policy.

Traverson cho phép gửi header cho các request trong một traversal. Ví dụ, nếu API yêu cầu bearer token:

~~~java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

CollectionModel<EntityModel<OrderSummary>> securedOrders =
    traverson.follow("orders")
        .withHeaders(headers)
        .toObject(orderCollectionType);
~~~

Chỉ gửi credentials đến entry point và các host mà chính sách bảo mật của client cho phép. Nếu link dẫn sang host khác, hãy quyết định rõ có được chuyển tiếp header xác thực hay không.

## 16. Cache và link cũ

Client có thể cache representation hoặc link để giảm request. Tuy nhiên, link có thể hết hiệu lực khi tài nguyên bị xóa, quyền thay đổi hoặc API thay đổi.

Một số nguyên tắc:

- Tôn trọng cache header của response.
- Không cache vô thời hạn các link phụ thuộc quyền người dùng.
- Xử lý 404, 410, 401 và 403 khi theo link cũ.
- Khi nhận lỗi tài nguyên hoặc relation không còn phù hợp, quay lại entry point hoặc tải lại representation cha nếu use case cho phép.
- Không tự tạo URI thay thế từ ID khi link cũ thất bại.

Một link cũ không phải bằng chứng rằng tài nguyên vẫn tồn tại. Server vẫn là nguồn quyết định trạng thái hiện tại.

Với pagination, dữ liệu có thể thay đổi giữa hai lần gọi next. Nếu API dùng cursor hoặc snapshot token, client phải giữ nguyên token thông qua link do server cung cấp thay vì tự tái tạo.

## 17. Kiểm thử client không phụ thuộc URI topology

Một test tốt cần chứng minh client theo relation và href thực tế. Có thể dựng mock server trả entry point với một URI collection cố ý khác route mà client có thể đoán:

~~~json
{
  "_links": {
    "orders": {
      "href": "/internal-route-that-client-does-not-know"
    }
  }
}
~~~

Client test nên xác nhận request tiếp theo được gửi đến href đó. Nếu test chỉ kiểm tra rằng client gọi `/orders`, nó đang củng cố hard-code thay vì bảo vệ hành vi hypermedia.

Với Traverson, có thể dùng mock HTTP server hoặc mock server phù hợp với HTTP client bên dưới để trả chuỗi HAL response. Kiểm tra:

1. Request đầu tiên đi đến entry point.
2. Client đọc relation `orders`.
3. Request kế tiếp đi đến href server trả về.
4. Client không tự tạo path từ tên relation hoặc ID.
5. Khi relation tùy chọn vắng mặt, client xử lý theo use case.
6. Khi link next xuất hiện, client theo đúng href và giữ ngữ cảnh truy vấn do server công bố.

Traverson cho phép thay RestOperations mặc định bằng implementation khác qua **setRestOperations(...)**. Nhờ đó, test có thể gắn MockRestServiceServer vào RestTemplate được cấp cho Traverson và xác nhận request đi đúng href do mock server trả về. Cách kiểm thử này trực tiếp chứng minh client không phụ thuộc route mà nó tự đoán.

## 18. Kiểm thử hợp đồng server bằng MockMvc

Phía server cần kiểm thử rằng các relation được công bố đúng và href được tạo từ mapping hiện tại:

~~~java
import org.springframework.hateoas.MediaTypes;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Kiểm tra relation self và association:

~~~java
mockMvc.perform(get("/api/v2/purchases/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Trong test thực tế, không nên khóa cứng path nội bộ nếu mục tiêu là xác nhận client có thể khám phá URI. Có thể xác nhận link tồn tại, đúng relation và trỏ đến tài nguyên có thể truy cập. Nếu test cần kiểm tra mapping cụ thể, tách nó thành kiểm thử routing của server.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghép URL từ ID | Client phụ thuộc cấu trúc route | Theo self link hoặc relation phù hợp |
| Hard-code path collection | Server đổi route làm client hỏng | Khởi đầu từ entry point và tìm relation |
| Tự tăng page rồi ghép query | Có thể mất filter hoặc cursor | Theo relation next/prev |
| Tự dựng query string | Phụ thuộc tên và cách encode tham số | Mở rộng URI template do server công bố |
| Xem tên relation là URI path | Nhầm ngữ nghĩa với địa chỉ | Tìm relation trong `_links`, dùng href |
| Giả định relation luôn có mặt | Lỗi khi khả năng tùy chọn hoặc trạng thái thay đổi | Kiểm tra link optional |
| Xem self là quyền thực hiện thao tác | Client gọi sai method hoặc bị từ chối | Dùng affordance/template và vẫn xử lý response |
| Ghép chuỗi để xử lý URI tương đối | Có thể phân giải sai base URI | Dùng URI resolver hoặc hypermedia client |
| Tin mọi host trong link tuyệt đối | Rủi ro gửi credentials sai host | Áp dụng trust policy |
| Cache link vô thời hạn | Theo link cũ đến tài nguyên không còn hợp lệ | Tôn trọng cache policy và xử lý lỗi |
| Test chỉ xác nhận URL cố định | Không phát hiện client đang hard-code URI | Mock href khác route dự đoán và xác nhận client theo link |

## 20. Quy trình xây dựng client hypermedia

Khi viết client cho REST API dùng Spring HATEOAS, hãy thực hiện theo trình tự:

1. Cấu hình một entry point ổn định cho môi trường triển khai.
2. Yêu cầu media type mà API hỗ trợ, ví dụ `application/hal+json`.
3. Đọc response và tìm relation cần thiết.
4. Theo href server cung cấp bằng HTTP client hoặc Traverson.
5. Dùng `IanaLinkRelations` cho relation chuẩn và relation đã tài liệu hóa cho ngữ nghĩa tùy chỉnh.
6. Mở rộng URI template bằng thư viện URI Template thay vì nối chuỗi.
7. Theo `next`, `prev` và các link điều hướng do server công bố.
8. Xử lý relation tùy chọn vắng mặt theo use case.
9. Nếu cần mô tả request body hoặc thao tác, dùng affordance/HAL-FORMS và parser tương ứng.
10. Áp dụng xác thực, trust policy, timeout, retry và cache policy cho các request theo link.
11. Kiểm thử bằng href khác với route mà client có thể đoán.
12. Giữ relation ổn định và quản lý thay đổi representation như một hợp đồng API.

Client không hard-code URI giúp tách logic nghiệp vụ khỏi cấu trúc định tuyến của server. Client vẫn biết relation mà nó cần, nhưng để server công bố URI thực tế, query template và các link điều hướng. Spring HATEOAS hỗ trợ server tạo các liên kết đó; Traverson giúp client đi theo chúng. Khi relation có ngữ nghĩa ổn định, href được sử dụng trực tiếp và các trường hợp thiếu link được xử lý có chủ đích, API có thể thay đổi topology mà ít gây ảnh hưởng đến client.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Client-side support and Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Traverson API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [RFC 6570 – URI Template](https://www.rfc-editor.org/rfc/rfc6570)

