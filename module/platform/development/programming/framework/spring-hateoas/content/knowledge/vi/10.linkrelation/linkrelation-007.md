# In relation ra JSON

Trong Spring HATEOAS, **LinkRelation** biểu diễn ý nghĩa của một liên kết hypermedia, chẳng hạn **self**, **next**, **orders** hoặc một quan hệ nghiệp vụ do API định nghĩa. Khi một **Link** được serialize theo HAL JSON, relation thường trở thành **tên thuộc tính bên trong object _links**. Giá trị của thuộc tính đó là object mô tả link, trong đó có **href** và có thể có thêm metadata.

Ví dụ, relation **self** không xuất hiện dưới dạng một trường **rel: self** trong object link HAL. Thay vào đó, nó được dùng làm key:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    }
  }
}
~~~

Client đọc tên relation để hiểu mục đích của liên kết và đọc **href** để biết URI đích. Vì vậy, relation là một phần quan trọng của hợp đồng hypermedia: đổi tên relation có thể ảnh hưởng đến client ngay cả khi URL đích vẫn giữ nguyên.

Sau bài học, bạn có thể:

- Giải thích LinkRelation và mối quan hệ giữa relation với Link.
- Đọc cách relation được biểu diễn thành key trong _links của HAL JSON.
- Tạo link bằng relation chuẩn IANA và relation mở rộng.
- Hiểu cách nhiều link cùng relation được serialize.
- Phân biệt relation của _links với relation dùng cho _embedded.
- Tạo và kiểm thử JSON hypermedia bằng Spring HATEOAS.

## LinkRelation và Link

Một link hypermedia có ít nhất hai thành phần khái niệm:

- **Target:** URI mà client có thể truy cập, thường được lưu trong thuộc tính href.
- **Relation:** ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và target, ví dụ chính tài nguyên (self), trang kế tiếp (next) hoặc collection (orders).

Trong Spring HATEOAS, Link mô tả liên kết; LinkRelation là value object đại diện cho quan hệ của liên kết đó. Link.getRel() trả về một LinkRelation, còn LinkRelation.value() trả về chuỗi relation.

Ví dụ:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link link = Link.of("/orders/42")
    .withRel(LinkRelation.of("self"));

String relationName = link.getRel().value(); // "self"
String target = link.getHref();              // "/orders/42"
~~~

Relation không phải HTTP method và cũng không phải URI đích. self không có nghĩa là GET; nó chỉ mô tả liên kết trỏ đến tài nguyên hiện tại. Method và dữ liệu gửi đi phải được xác định bằng ngữ nghĩa HTTP và hợp đồng tương tác tương ứng, chẳng hạn affordance hoặc form.

### Vì sao relation quan trọng?

Nếu client chỉ nhận một danh sách URL không có relation, client khó biết mỗi URL dùng để làm gì. Relation tạo ngữ nghĩa cho link để client có thể chọn đúng đích theo mục tiêu nghiệp vụ.

Ví dụ, client có thể tìm relation orders để mở collection, payment để đi đến thông tin thanh toán, hoặc next để lấy trang kế tiếp. Client không cần dựa vào thứ tự xuất hiện của các link hay tự suy đoán URL từ path hiện tại.

Relation nên có semantics ổn định. Nếu API đổi tên relation payment thành pay-order nhưng client vẫn tìm payment, client có thể không còn khám phá được liên kết dù href vẫn hoạt động. Khi cần thay đổi semantics, hãy định nghĩa relation mới, tài liệu hóa và có chiến lược chuyển đổi.

## Relation xuất hiện ở đâu trong HAL JSON?

HAL JSON dùng _links để biểu diễn các liên kết của tài nguyên. Mỗi relation là một key trong object _links; giá trị là object link hoặc mảng các object link nếu có nhiều liên kết cùng relation.

Ví dụ:

~~~json
{
  "id": 42,
  "status": "PENDING_PAYMENT",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "collection": {
      "href": "/orders"
    },
    "payment": {
      "href": "/orders/42/payment"
    }
  }
}
~~~

Trong response này:

- self là relation của link đến chính đơn hàng.
- collection là relation đến tập hợp chứa đơn hàng.
- payment là relation nghiệp vụ đến tài nguyên hoặc điểm tương tác thanh toán.
- href của mỗi link là URI đích.

HAL không cần lặp lại tên relation bên trong từng object link vì relation đã được thể hiện bằng key của _links. Vì vậy, cấu trúc sau không phải cách biểu diễn HAL thông thường:

~~~json
{
  "_links": {
    "link": {
      "rel": "self",
      "href": "/orders/42"
    }
  }
}
~~~

Với HAL, hãy đặt relation ở tên key:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Định dạng JSON cụ thể phụ thuộc media type. Cách biểu diễn key relation nói trên là quy ước của HAL JSON (application/hal+json), không phải quy tắc chung cho mọi JSON API hoặc mọi media type hypermedia.

## Tạo relation chuẩn với IanaLinkRelations

IANA duy trì registry các link relation chuẩn. Những relation đã đăng ký có semantics được công bố, giúp client và server dùng chung cách hiểu.

Spring HATEOAS cung cấp IanaLinkRelations với các hằng số cho các relation phổ biến, chẳng hạn:

| Hằng số Spring HATEOAS | Relation | Ý nghĩa |
| --- | --- | --- |
| SELF | self | Tài nguyên hiện tại |
| NEXT | next | Tài nguyên hoặc trang tiếp theo |
| PREV | prev | Tài nguyên hoặc trang trước |
| FIRST | first | Trang đầu tiên |
| LAST | last | Trang cuối cùng |
| COLLECTION | collection | Collection chứa item |
| ITEM | item | Một item trong collection |

Có thể dùng hằng số thay cho chuỗi literal để tránh gõ sai relation:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42").withRel(IanaLinkRelations.SELF);
Link next = Link.of("/orders?page=1").withRel(IanaLinkRelations.NEXT);
~~~

Với link được tạo từ controller, có thể dùng relation chuẩn hoặc relation dạng chuỗi:

~~~java
return EntityModel.of(order,
    linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
    linkTo(methodOn(OrderController.class).all())
        .withRel(IanaLinkRelations.COLLECTION));
~~~

withSelfRel() là cách viết tiện dụng cho relation self. Dùng hằng số relation giúp mã dễ đọc và giảm sự không nhất quán giữa các controller.

Không nên chọn một relation chuẩn chỉ vì tên có vẻ gần với nghiệp vụ. Hãy đọc semantics đã đăng ký và chỉ dùng khi ý nghĩa của link thực sự phù hợp.

## Relation mở rộng cho nghiệp vụ riêng

API có thể cần các quan hệ không nằm trong registry IANA, ví dụ payment, cancel, invoice hoặc approve. Spring HATEOAS cho phép tạo relation bằng LinkRelation.of(...) hoặc truyền chuỗi vào withRel(...).

Ví dụ:

~~~java
import org.springframework.hateoas.LinkRelation;

LinkRelation payRelation = LinkRelation.of("https://api.example.com/rels/pay");

Link payLink = Link.of("/orders/42/payment")
    .withRel(payRelation);
~~~

Với relation mở rộng, nên dùng URI tuyệt đối do tổ chức kiểm soát, ví dụ https://api.example.com/rels/pay. URI relation định danh semantics và có thể trỏ đến tài liệu giải thích ý nghĩa, điều kiện khả dụng và cách sử dụng relation. URI relation không nhất thiết là endpoint để thực hiện request.

Khi serialize HAL, relation URI trở thành key trong _links:

~~~json
{
  "_links": {
    "https://api.example.com/rels/pay": {
      "href": "/orders/42/payment"
    }
  }
}
~~~

Đừng dùng một relation tùy chỉnh cho nhiều ý nghĩa khác nhau. Nếu pay có semantics “bắt đầu thanh toán”, không nên đổi nó thành “xem lịch sử thanh toán” ở phiên bản sau. Hãy định nghĩa relation khác nếu mục đích thay đổi.

### Tên ngắn và URI relation

Tên ngắn như payment dễ đọc trong JSON, nhưng semantics có thể chỉ được hiểu bởi client biết trước quy ước của API. URI relation giúp định danh toàn cục và có thể dẫn đến tài liệu mô tả.

| Dạng relation | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Relation chuẩn | self, next, collection | Khi semantics trùng với relation đã đăng ký |
| Tên ngắn riêng | payment, cancel | API nội bộ có quy ước và tài liệu rõ ràng |
| URI relation | https://api.example.com/rels/pay | API công khai hoặc cần định danh semantics mở rộng ổn định |

Trong một API, hãy chọn quy ước nhất quán và công bố semantics để client không phải đoán.

## Nhiều link cùng relation được serialize như thế nào?

Một tài nguyên có thể có nhiều link cùng relation. Ví dụ, một tài nguyên có thể có nhiều link item đến các bản ghi liên quan hoặc nhiều link alternate cho các biến thể biểu diễn.

Trong HAL, nếu một relation chỉ có một link, giá trị thường là một object. Nếu relation có nhiều link, giá trị được biểu diễn thành mảng các object link.

Một link:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Nhiều link cùng relation:

~~~json
{
  "_links": {
    "alternate": [
      {
        "href": "/orders/42",
        "type": "application/hal+json",
        "title": "Biểu diễn HAL"
      },
      {
        "href": "/orders/42.xml",
        "type": "application/xml",
        "title": "Biểu diễn XML"
      }
    ]
  }
}
~~~

Client nên xử lý cả hai dạng: object khi chỉ có một link và array khi có nhiều link. Không nên giả định giá trị của mọi relation luôn là một object duy nhất. Thứ tự key của JSON object không có ý nghĩa hợp đồng; với array, thứ tự có thể được giữ trong response nhưng client vẫn nên chọn link theo metadata và mục đích thay vì dựa vào vị trí cố định.

Trong Java, có thể thêm nhiều Link cùng relation vào một representation:

~~~java
EntityModel<OrderResponse> model = EntityModel.of(order,
    Link.of("/orders/42").withSelfRel(),
    Link.of("/orders/42?view=compact").withRel("alternate"),
    Link.of("/orders/42?view=full").withRel("alternate"));
~~~

Khi serialize HAL, hai link alternate được gom dưới cùng relation. Hãy dùng nhiều link cùng relation khi chúng có cùng ý nghĩa nhưng khác URI hoặc metadata, chẳng hạn khác định dạng biểu diễn hoặc ngôn ngữ.

## Metadata bổ sung trong object link

Relation xác định loại quan hệ; object link cung cấp URI và có thể kèm metadata. HAL hỗ trợ một số thuộc tính link phổ biến:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| href | URI đích của link |
| templated | Cho biết href là URI template cần thay biến |
| type | Media type dự kiến của đích |
| deprecation | URI mô tả thông tin về việc link bị deprecated |
| name | Tên phân biệt một link khi có nhiều link cùng relation |
| profile | URI profile mô tả thêm semantics của đích |
| title | Nhãn dễ đọc cho người dùng |
| hreflang | Ngôn ngữ của tài nguyên đích |

Ví dụ:

~~~json
{
  "_links": {
    "alternate": {
      "href": "/orders/42.xml",
      "type": "application/xml",
      "title": "Đơn hàng dạng XML",
      "hreflang": "vi"
    }
  }
}
~~~

title không thay thế relation. title là nhãn hiển thị; relation là semantics mà client dùng để hiểu liên kết. Tương tự, type mô tả media type của đích chứ không phải HTTP method để gọi đích đó.

Spring HATEOAS cho phép bổ sung metadata cho Link thông qua các phương thức fluent như withTitle(...), withType(...), withHreflang(...), withName(...) hoặc các phương thức tương ứng trong phiên bản thư viện đang sử dụng.

## LinkRelation trong Spring HATEOAS và controller

Khi tạo model trong controller, relation được gắn vào link. Ví dụ:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping("/{id}")
EntityModel<OrderResponse> one(@PathVariable Long id) {
    OrderResponse order = orderService.findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

    return EntityModel.of(order,
        linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
        linkTo(methodOn(OrderController.class).all())
            .withRel(IanaLinkRelations.COLLECTION));
}
~~~

Trong response HAL, relation chuẩn self và collection trở thành key trong _links. Đường dẫn được tạo từ mapping controller; relation được chọn trong mã ứng dụng.

Với hành động nghiệp vụ, có thể tạo relation mở rộng:

~~~java
if (order.status() == OrderStatus.PENDING_PAYMENT) {
    model.add(linkTo(methodOn(PaymentController.class)
        .pay(order.id()))
        .withRel("https://api.example.com/rels/pay"));
}
~~~

Link chỉ nên xuất hiện khi hành động được công bố trong trạng thái hiện tại. Tuy nhiên, server vẫn phải kiểm tra quyền và trạng thái khi request thực sự đến; client có thể giữ link cũ hoặc tự gửi request.

## Relation của tài nguyên nhúng trong _embedded

HAL có hai khu vực thường gặp:

- _links: các liên kết điều hướng đến tài nguyên khác.
- _embedded: biểu diễn các tài nguyên được nhúng trong response hiện tại.

Relation cũng được dùng làm key trong _embedded, nhưng mục đích là đặt tên cho loại tài nguyên nhúng. Ví dụ:

~~~json
{
  "_embedded": {
    "orders": [
      { "id": 42, "status": "PAID" },
      { "id": 43, "status": "PENDING_PAYMENT" }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
~~~

Ở đây orders là relation dùng để đặt tên collection nhúng; self là relation của link đến collection. Không nên nhầm hai vai trò này dù cả hai đều dùng key có ý nghĩa relation.

Spring HATEOAS có LinkRelationProvider để xác định relation cho loại representation, đặc biệt khi tạo tên relation cho collection được nhúng. Có thể tùy chỉnh relation của model bằng annotation @Relation:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(value = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {
    private Long id;
    private String status;

    // Constructors, getters and setters
}
~~~

value xác định relation cho một item; collectionRelation xác định relation cho collection các item đó. Khi ứng dụng serialize collection model, relation provider có thể dùng cấu hình này để đặt tên key trong _embedded. Điều này giúp tránh tên relation tự động không phù hợp với hợp đồng công khai.

Với collection rỗng, serializer không có item thực tế để suy luận loại representation. Khi cần giữ relation nhúng ổn định, có thể cung cấp fallback type cho CollectionModel và kiểm thử response rỗng.

## Kiểm thử relation trong JSON

Kiểm thử hypermedia nên xác minh relation và URI cùng nhau. Chỉ kiểm tra href có tồn tại là chưa đủ vì link có thể bị gắn nhầm relation hoặc relation quan trọng bị đổi tên.

Ví dụ với Spring MVC Test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLinkRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void responseUsesExpectedRelations() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.collection.href").exists());
    }
}
~~~

Test giả định đơn hàng 42 tồn tại và controller công bố self cùng collection. Với relation mở rộng dạng URI, JSONPath cần trích key tương ứng, ví dụ:

~~~java
jsonPath("$._links['https://api.example.com/rels/pay'].href").exists()
~~~

Khi có nhiều link cùng relation, kiểm tra cấu trúc array và số link:

~~~java
jsonPath("$._links.alternate.length()").value(2)
~~~

Test trên giả định response có đúng hai link alternate. Với collection nhúng, kiểm tra relation trong _embedded, ví dụ jsonPath("$._embedded.orders").isArray().

Các trường hợp nên kiểm thử:

1. Relation chuẩn được serialize đúng key trong _links.
2. Relation mở rộng được serialize đúng, bao gồm URI relation nếu API dùng dạng đó.
3. href trỏ đến đúng URI tương ứng với relation.
4. Nhiều link cùng relation được biểu diễn thành array và client xử lý được.
5. Relation nghiệp vụ chỉ xuất hiện khi hành động khả dụng.
6. Relation collection trong _embedded giữ ổn định khi có và không có item.
7. Media type là HAL JSON khi client yêu cầu application/hal+json.

## Những sai lầm thường gặp

**Tìm rel như một trường trong object link HAL.** HAL dùng relation làm key bên trong _links; object link chứa href và metadata.

**Nhầm relation với href.** Relation trả lời “liên kết có ý nghĩa gì?”, còn href trả lời “đích ở đâu?”. Cả hai đều cần thiết.

**Nhầm relation với HTTP method.** self, payment hoặc next không tự xác định request phải dùng GET, POST hay DELETE. Method cần được mô tả bởi semantics HTTP và affordance/form nếu client cần thông tin thao tác.

**Dùng tên relation tùy ý mà không tài liệu hóa.** Client không thể hiểu semantics nếu server thay đổi hoặc không công bố ý nghĩa relation. Dùng IANA relation khi phù hợp; với relation mở rộng, định nghĩa và giữ ổn định semantics.

**Giả định một relation luôn có một link.** HAL cho phép một relation có nhiều link và biểu diễn giá trị đó thành array. Client nên xử lý cả object và array.

**Nhầm _links với _embedded.** _links công bố liên kết; _embedded chứa biểu diễn tài nguyên được nhúng. Relation là key ở cả hai nơi nhưng có vai trò khác nhau.

**Đổi relation mà không xem xét tương thích.** Client thường tìm relation theo semantics. Đổi tên relation có thể phá luồng điều hướng dù endpoint cũ vẫn hoạt động.

## Kết luận

LinkRelation là tên có ngữ nghĩa của mối quan hệ giữa tài nguyên hiện tại và một đích liên kết. Trong HAL JSON, relation được serialize thành key trong _links; giá trị là object link hoặc array nếu có nhiều link cùng relation. href chỉ ra URI đích, còn các metadata như type, title và hreflang bổ sung thông tin về link.

Trong Spring HATEOAS, hãy ưu tiên IanaLinkRelations cho relation chuẩn, dùng LinkRelation.of(...) hoặc relation URI được tài liệu hóa cho nghiệp vụ riêng, và cấu hình relation provider khi cần kiểm soát tên resource trong _embedded. Kiểm thử cả relation lẫn URI trong response để giữ hợp đồng hypermedia ổn định và giúp client điều hướng đúng.
