# Link sai relation

Trong REST API dùng Spring HATEOAS, một link không chỉ là URL để client gọi. Link còn mô tả quan hệ giữa resource hiện tại và resource đích thông qua **link relation** (`rel`). Client có thể dựa vào relation để tìm trang tiếp theo, mở collection, truy cập tài nguyên liên quan hoặc nhận biết một action có thể thực hiện.

Một anti-pattern phổ biến là gắn relation theo tên method controller, HTTP method, tên field hoặc một nhãn tùy ý mà không định nghĩa semantics. Một lỗi khác là dùng relation chuẩn như `next`, `self`, `edit` hoặc `item` cho một quan hệ khác nghĩa. Link vẫn có thể trả HTTP 200 khi được mở trực tiếp, nhưng client hiểu sai cấu trúc API và có thể điều hướng sai.

Bài học này giải thích semantics của relation, cách chọn relation IANA hoặc extension URI, cách tạo link đúng trong Spring HATEOAS, cách phân biệt relation với affordance và cách kiểm thử hợp đồng hypermedia.

## 1. Relation mô tả quan hệ giữa hai resource

Theo RFC 8288, một link là kết nối có kiểu giữa hai resource. Nó gồm:

- **Link context**: resource đang công bố link.
- **Link relation type**: loại quan hệ giữa context và target.
- **Link target**: resource mà link trỏ tới.
- **Target attributes**: metadata tùy chọn mô tả link hoặc target.

Có thể đọc một link như câu: “Resource hiện tại có một resource liên quan theo quan hệ X tại URI Y”.

Ví dụ:

~~~json
{
  "id": 42,
  "number": "SO-0042",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Trong representation này:

- Context là đơn hàng số 42.
- Relation `self` trỏ tới chính resource đơn hàng hiện tại.
- Relation `customer` mô tả resource khách hàng liên quan.
- `href` xác định nơi client có thể truy cập resource đích.

`rel` trả lời câu hỏi “đây là quan hệ gì?”, còn `href` trả lời “đi tới đâu?”. Nếu hai giá trị không khớp semantics, client có thể gọi sai luồng dù URL vẫn hợp lệ.

Relation không phải media type. Nó không mô tả JSON, XML hay HAL được trả về. Media type của representation đích được thương lượng qua HTTP và có thể được gợi ý bằng thuộc tính `type` của link.

## 2. Vì sao relation sai làm hỏng khả năng điều hướng?

Client HATEOAS thường không cần biết route nội bộ của server. Thay vào đó, client tìm link theo relation mà nó hiểu:

~~~java
Link nextPage = model.getRequiredLink(IanaLinkRelations.NEXT);
~~~

Client mong `next` dẫn tới phần tiếp theo của một chuỗi resource, chẳng hạn trang tiếp theo của collection. Nếu server gắn `next` vào URL hủy đơn hàng, client có thể xem action hủy như trang kế tiếp.

Relation sai tạo ra các vấn đề sau:

- Client không tìm thấy link cần thiết vì server dùng tên khác với vocabulary đã thống nhất.
- Client chọn nhầm link vì nhiều mục đích khác nhau dùng cùng một relation.
- Client gọi một URL với kỳ vọng sai về semantics hoặc kết quả.
- Khi đổi tên method controller, relation thay đổi theo dù ý nghĩa nghiệp vụ không đổi.
- Các client độc lập không thể tái sử dụng vocabulary vì relation chỉ có ý nghĩa trong một codebase.
- Test chỉ kiểm tra URL có phản hồi mà bỏ qua hợp đồng hypermedia.

Một link có thể đúng về cú pháp và sai về semantics. Vì vậy, kiểm tra `href` tồn tại chưa đủ; phải kiểm tra relation diễn đạt đúng quan hệ.

## 3. Anti-pattern: dùng tên method hoặc HTTP method làm relation

Ví dụ sau gắn relation theo tên method:

~~~java
model.add(
        linkTo(methodOn(OrderController.class).cancel(orderId))
                .withRel("cancel")
);

model.add(
        linkTo(methodOn(OrderController.class).delete(orderId))
                .withRel("delete")
);
~~~

Tên `cancel` hoặc `delete` có thể giúp người đọc đoán ý định, nhưng chưa xác định một vocabulary dùng chung. Đặc biệt, `delete` thường chỉ lặp lại HTTP method mà client phải dùng, trong khi relation cần diễn đạt ý nghĩa của target.

Không nên coi `rel` là trường `method`:

~~~json
{
  "_links": {
    "POST": {
      "href": "/api/orders/42/cancellation"
    },
    "DELETE": {
      "href": "/api/orders/42"
    }
  }
}
~~~

`POST` và `DELETE` là HTTP methods. Chúng không mô tả quan hệ của target với order. HAL link cơ bản cũng không tự khai báo HTTP method hay request body mà client phải gửi.

Với action nghiệp vụ như hủy đơn hàng, hãy định nghĩa một extension relation ổn định, ví dụ:

`https://api.example.com/rels/cancel-order`

Sau đó mô tả method và input bằng affordance hoặc media type hỗ trợ form khi client cần thông tin đó. Relation giữ semantics của action; affordance mô tả cách thực hiện action.

## 4. Anti-pattern: dùng tên field hoặc dữ liệu động làm relation

Một relation không nên thay đổi theo giá trị của resource:

~~~java
model.add(customerLink.withRel(order.getCustomer().getName()));
model.add(orderLink.withRel("order-" + order.getId()));
model.add(statusLink.withRel(order.getStatus().name().toLowerCase()));
~~~

Các relation như `Nguyen An`, `order-42` hoặc `pending` gây ra nhiều vấn đề:

- Client phải biết trước giá trị dữ liệu mới có thể tìm relation.
- Relation thay đổi khi tên khách hàng, ID hoặc trạng thái thay đổi.
- Số lượng relation tăng theo dữ liệu thay vì theo vocabulary API.
- Relation bị dùng như nơi chứa data, làm client khó phân biệt metadata và nội dung resource.

Nếu client cần tên khách hàng, hãy trả field `customerName` trong representation hoặc cung cấp link relation `customer`. Nếu cần trạng thái, trả field `status`. Nếu cần link tới order hiện tại, dùng `self`.

Ví dụ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.math.BigDecimal;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

public record OrderSummary(
        Long id,
        String number,
        OrderStatus status,
        BigDecimal total,
        String customerName
) {
}

Link customerLink = Link.of(
        linkTo(methodOn(CustomerController.class)
                .one(order.getCustomer().getId()))
                .toUri()
                .toString(),
        LinkRelation.of("https://api.example.com/rels/customer")
);

OrderSummary summary = new OrderSummary(
        order.getId(),
        order.getNumber(),
        order.getStatus(),
        order.getTotal(),
        order.getCustomer().getName()
);

EntityModel<OrderSummary> model = EntityModel.of(summary, customerLink);
~~~

Relation giữ nguyên qua các order; dữ liệu cụ thể nằm trong payload hoặc URI target.

## 5. Anti-pattern: dùng relation chuẩn sai semantics

Relation đã đăng ký có ý nghĩa được định nghĩa trước. Không nên tái sử dụng chúng chỉ vì tên có vẻ phù hợp.

| Relation | Ý nghĩa chuẩn | Cách dùng sai thường gặp |
| --- | --- | --- |
| `self` | Link tới chính resource hiện tại | Trỏ tới collection hoặc action khác |
| `collection` | Target là collection chứa hoặc đại diện cho context | Dùng cho link tới một item |
| `item` | Target là một thành viên của collection context | Dùng cho link tới trang tổng quan |
| `next` | Resource tiếp theo trong một chuỗi | Dùng cho action tiếp theo trong quy trình |
| `prev` | Resource trước đó trong một chuỗi | Dùng cho thao tác quay lại trạng thái |
| `edit` | Target có thể được dùng để chỉnh sửa context | Dùng cho endpoint xóa hoặc hủy |
| `edit-form` | Target cung cấp form để chỉnh sửa resource liên quan | Dùng cho JSON detail thông thường |
| `canonical` | Phiên bản được ưu tiên của resource | Dùng như alias cho `self` |
| `related` | Một resource có liên quan | Dùng cho mọi quan hệ dù đã có relation cụ thể hơn |

Ví dụ sai: đơn hàng công bố link hủy với relation `next`:

~~~java
Link cancelLink = linkTo(
        methodOn(OrderController.class).cancel(orderId)
).withRel(IanaLinkRelations.NEXT);
~~~

`next` không có nghĩa “action kế tiếp mà người dùng có thể làm”. Nó mô tả resource tiếp theo trong một chuỗi. Nếu đây là action hủy, hãy dùng extension relation dành cho action hủy.

Một ví dụ khác là gắn `self` cho link collection trong representation của một order. `self` phải trỏ tới order đang được biểu diễn. Link từ order về collection có thể dùng `collection`:

~~~java
Link self = linkTo(
        methodOn(OrderController.class).one(orderId)
).withSelfRel();

Link collection = linkTo(OrderController.class)
        .withRel(IanaLinkRelations.COLLECTION);
~~~

Khi collection trỏ tới từng phần tử, relation `item` diễn tả rằng target là một thành viên của collection. Hãy chọn theo hướng quan hệ giữa context và target.

## 6. Chọn relation IANA khi semantics đã tồn tại

IANA duy trì danh mục relation chuẩn để nhiều ứng dụng có thể dùng chung vocabulary. Trước khi tạo relation riêng, hãy kiểm tra danh mục này.

Spring HATEOAS cung cấp `IanaLinkRelations` với các hằng số có kiểu `LinkRelation`. Ví dụ:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of(orderUri.toString(), IanaLinkRelations.SELF);
Link collection = Link.of(collectionUri.toString(), IanaLinkRelations.COLLECTION);
Link next = Link.of(nextPageUri.toString(), IanaLinkRelations.NEXT);
Link edit = Link.of(editUri.toString(), IanaLinkRelations.EDIT);
~~~

Một số relation thường hữu ích trong API:

| Relation | Khi nên dùng |
| --- | --- |
| `self` | Định danh URI của representation hiện tại |
| `collection` | Từ resource thành viên trỏ về collection |
| `item` | Từ collection trỏ tới một thành viên |
| `next`, `prev`, `first`, `last` | Điều hướng trong chuỗi hoặc collection có phân trang |
| `edit` | Trỏ tới resource có thể dùng để chỉnh sửa context |
| `edit-form` | Trỏ tới form resource để chỉnh sửa context |
| `describedby` | Trỏ tới tài liệu mô tả context |
| `profile` | Nêu profile mà representation tuân theo |
| `related` | Resource liên quan khi không có relation cụ thể phù hợp hơn |

Tên relation đã đăng ký được so sánh không phân biệt chữ hoa chữ thường theo RFC 8288, nhưng nên viết chữ thường để nhất quán với registry. Trong Java, ưu tiên dùng hằng số `IanaLinkRelations` thay vì gõ chuỗi thủ công.

Không biến relation chuẩn thành URI bằng cách tự thêm base URL. Ví dụ `https://api.example.com/rels/next` không tự động tương đương với relation đã đăng ký `next`. Nếu semantics là IANA `next`, hãy dùng đúng relation `next`.

## 7. Tạo extension relation URI cho nghiệp vụ riêng

Nếu IANA chưa có relation phù hợp, ứng dụng có thể định nghĩa extension relation. Theo RFC 8288, extension relation là một URI duy nhất nhận diện semantics của quan hệ. URI nên thuộc quyền kiểm soát của tổ chức định nghĩa relation.

Ví dụ:

~~~text
https://api.example.com/rels/cancel-order
https://api.example.com/rels/approve-order
https://api.example.com/rels/request-refund
~~~

URI có thể dẫn tới tài liệu giải thích semantics, ví dụ:

~~~text
https://api.example.com/rels/cancel-order
~~~

Client không nên tự động truy cập URI relation chỉ để tìm hiểu ý nghĩa. Client cần được xây dựng theo hợp đồng và tài liệu API đã công bố. Nếu URI relation được dùng làm tài liệu, hãy giữ định nghĩa ổn định và không tái sử dụng URI cho semantics mới.

Spring HATEOAS tạo relation riêng bằng `LinkRelation.of(...)`:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link cancelOrder = Link.of(
        cancellationUri.toString(),
        LinkRelation.of("https://api.example.com/rels/cancel-order")
);
~~~

RFC khuyến nghị extension URI viết chữ thường. Dù quy tắc so sánh relation extension là không phân biệt hoa thường theo RFC 8288, dùng một cách viết thống nhất giúp giảm lỗi trong log, test và tài liệu.

Không dùng các chuỗi chung như `action`, `operation`, `do-it` hoặc `custom-link` cho nhiều ý nghĩa. Một relation cần đủ cụ thể để client hiểu target đại diện cho điều gì.

## 8. Tạo link đúng trong Spring HATEOAS

Ví dụ dưới đây tạo representation cho order, link self, link collection và action hủy. Relation của action là extension URI do API định nghĩa:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler {

    private static final LinkRelation CANCEL_ORDER =
            LinkRelation.of(
                    "https://api.example.com/rels/cancel-order"
            );

    public EntityModel<OrderSummary> toModel(Order order) {
        OrderSummary summary = new OrderSummary(
                order.getId(),
                order.getNumber(),
                order.getStatus(),
                order.getTotal(),
                order.getCustomer().getName()
        );

        Link self = linkTo(
                methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        Link collection = linkTo(OrderController.class)
                .withRel(IanaLinkRelations.COLLECTION);

        EntityModel<OrderSummary> model =
                EntityModel.of(summary, self, collection);

        if (order.getStatus() == OrderStatus.PENDING) {
            Link cancel = Link.of(
                    linkTo(methodOn(OrderController.class)
                            .cancel(order.getId()))
                            .toUri()
                            .toString(),
                    CANCEL_ORDER
            );

            model.add(cancel);
        }

        return model;
    }
}
~~~

Ví dụ giả định controller có các method `one(id)` và `cancel(id)`, còn `OrderSummary` chứa field công khai cần trả về. Link hủy chỉ xuất hiện khi order đang ở trạng thái `PENDING`. Relation vẫn giữ một ý nghĩa ổn định; sự hiện diện của link cho biết action hiện khả dụng theo chính sách của server.

Không dùng sự tồn tại của link làm cơ chế bảo mật duy nhất. Endpoint `cancel` vẫn phải xác thực người gọi, kiểm tra quyền và kiểm tra trạng thái tại thời điểm request được thực thi. Client có thể giữ representation cũ hoặc gọi URI trực tiếp.

## 9. Relation không thay thế affordance

Một HAL link cơ bản thường cho biết relation và target. Nó không nhất thiết mô tả đầy đủ:

- HTTP method cần dùng.
- Request body hoặc các field bắt buộc.
- Media type của request.
- Quy tắc validation.
- Các điều kiện nghiệp vụ để action thành công.

Không nên cố mã hóa các chi tiết đó bằng relation như `post-cancel-order`, `delete-order` hoặc `patch-order-status`. Các tên như vậy trộn lẫn ý nghĩa quan hệ với cách truyền tải.

Nếu client cần biết cách thực hiện action, hãy dùng affordance hoặc media type có form, chẳng hạn HAL-FORMS. Relation vẫn mô tả action hoặc resource đích; affordance cung cấp method và metadata payload.

Ví dụ vocabulary có thể được tổ chức như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `rel` `.../cancel-order` | Định danh action hủy đơn hàng |
| `href` | URI của endpoint thực hiện action |
| Affordance | Mô tả HTTP method, input và output |
| `type` | Gợi ý media type của representation đích hoặc payload theo ngữ cảnh |
| `title` | Nhãn thân thiện để hiển thị cho người dùng |

Không dùng `title` thay cho relation. `title` có thể được bản địa hóa hoặc đổi cách diễn đạt; relation phải ổn định để client nhận diện.

## 10. Phân biệt relation với title, type và tên property

Các thuộc tính của link có vai trò khác nhau:

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| `rel` | Target có quan hệ gì với context? |
| `href` | Target ở đâu? |
| `title` | Con người nên đọc nhãn nào cho link? |
| `type` | Representation đích có media type nào? |
| `hreflang` | Representation đích gắn với ngôn ngữ nào? |
| Affordance | Client có thể gửi request theo cách nào? |

Một anti-pattern khác là dùng media type làm relation:

~~~json
{
  "_links": {
    "application/json": {
      "href": "/api/orders/42"
    }
  }
}
~~~

`application/json` mô tả định dạng representation, không mô tả quan hệ của resource đích với context. Hãy dùng relation phù hợp và thương lượng media type qua `Accept`; nếu cần, dùng thuộc tính `type` của link làm hint.

Tương tự, `customerName` là dữ liệu, không phải relation. Nếu link trỏ tới khách hàng, relation phải mô tả quan hệ khách hàng.

## 11. Không nhầm relation của link với relation của embedded collection

Trong HAL, `_links` và `_embedded` có thể dùng tên relation để biểu diễn hai khía cạnh khác nhau:

- `_links.customer` là link tới resource khách hàng.
- `_embedded.customer` là representation khách hàng được nhúng.
- `_embedded.orders` có thể là collection các đơn hàng được nhúng.

Spring HATEOAS có annotation `@Relation` để tùy chỉnh relation dùng khi biểu diễn một item hoặc collection được nhúng:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private Long id;
    private String number;
}
~~~

`itemRelation` và `collectionRelation` điều khiển tên relation trong representation collection/embedded theo cơ chế của Spring HATEOAS. Chúng không tự động thay thế việc chọn relation cho mọi link được thêm bằng `Link` hoặc `RepresentationModel.add(...)`.

Đừng sửa `@Relation` với mục đích đổi semantics của một link action. Hãy xác định rõ đang đặt tên cho embedded item, embedded collection hay link target.

## 12. Relation phải ổn định khi implementation thay đổi

Relation là một phần hợp đồng công khai. Không để tên method Java hoặc cấu trúc package quyết định relation:

~~~java
// Dễ gây thay đổi hợp đồng khi refactor tên method.
model.add(linkTo(methodOn(OrderController.class).cancel(id))
        .withRel("cancelOrderV2"));
~~~

Nếu method được đổi từ `cancel` thành `requestCancellation`, relation không nên đổi theo. Client quan tâm ý nghĩa action, không quan tâm tên method nội bộ.

Đặt relation trong một nơi dùng chung:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    private ApiRelations() {
    }

    public static final LinkRelation CANCEL_ORDER =
            LinkRelation.of(
                    "https://api.example.com/rels/cancel-order"
            );

    public static final LinkRelation CUSTOMER =
            LinkRelation.of(
                    "https://api.example.com/rels/customer"
            );
}
~~~

Assembler, controller và test cùng dùng các constant này. Cách tổ chức đó giảm lỗi gõ sai và giúp review khi vocabulary thay đổi.

Không thay đổi semantics của một relation URI đã công bố. Nếu một action mới có ý nghĩa khác, tạo relation mới. Nếu chỉ đổi URL đích hoặc implementation mà ý nghĩa không đổi, giữ relation cũ và cập nhật link target.

## 13. Kiểm thử relation, không chỉ kiểm thử href

Một test chỉ kiểm tra endpoint trả HTTP 200 không phát hiện relation sai:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
~~~

Hãy kiểm tra relation quan trọng trong HAL response:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderRelationTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @BeforeEach
    void setUp() {
        when(orderService.getOrder(42L)).thenReturn(TestOrders.order42());
    }

    @Test
    void exposesRelationsWithTheirDocumentedMeaning() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.collection.href").exists())
                .andExpect(jsonPath(
                        "$._links['https://api.example.com/rels/cancel-order'].href"
                ).exists())
                .andExpect(jsonPath("$._links.next").doesNotExist());
    }
}
~~~

Ví dụ test giả định fixture order `42` ở trạng thái `PENDING`, controller và service đã được cấu hình cho slice test. Trong test đầy đủ, mock service hoặc cung cấp dữ liệu test xác định để không phụ thuộc database.

Ngoài sự tồn tại của relation, hãy kiểm tra target:

- `self` trỏ đúng URI của resource đang được biểu diễn.
- `collection` trỏ về collection resource.
- `next` trỏ tới trang hoặc resource tiếp theo trong chuỗi.
- Relation action trỏ tới endpoint tương ứng với semantics.
- Action link chỉ xuất hiện khi action khả dụng theo trạng thái và quyền.

Nên có test âm: một action không khả dụng thì relation tương ứng không xuất hiện. Điều này giúp phát hiện lỗi assembler thêm link vô điều kiện.

## 14. Dùng client test để xác nhận khả năng khám phá

Contract test phía server có thể xác nhận relation được phát ra. Một client test nhỏ có thể xác nhận client tìm thấy đúng relation và theo link đó:

~~~java
Link cancelLink = representation.getRequiredLink(
        LinkRelation.of(
                "https://api.example.com/rels/cancel-order"
        )
);

assertThat(cancelLink.getHref())
        .endsWith("/api/orders/42/cancellation");
~~~

Đừng để client phụ thuộc vào thứ tự link trong JSON hoặc vị trí phần tử của mảng link. Hãy tìm bằng relation và xử lý trường hợp link vắng mặt.

Nếu client sử dụng `LinkDiscoverer` hoặc `Traverson`, hãy kiểm tra bằng đúng media type đang được API công bố. Client có thể xử lý nhiều representation khác nhau; contract test cần xác nhận relation vẫn được nhận diện khi server thay đổi implementation.

## 15. Quy trình thiết kế relation

Trước khi thêm một link mới, hãy thực hiện các bước:

1. Xác định context: resource nào đang công bố link?
2. Xác định target: resource hoặc action nào nằm ở URI đích?
3. Viết một câu mô tả quan hệ từ context tới target.
4. Kiểm tra IANA registry xem đã có relation phù hợp chưa.
5. Nếu chưa có, tạo extension relation URI thuộc quyền kiểm soát của API.
6. Xác định `href` bằng `WebMvcLinkBuilder` hoặc URI builder phù hợp.
7. Nếu là action, bổ sung affordance/form metadata khi client cần method và input.
8. Kiểm tra authorization và điều kiện nghiệp vụ trước khi công bố action link.
9. Viết contract test cho relation và target.
10. Ghi relation vào catalog và giữ semantics ổn định qua các phiên bản.

Một catalog nhỏ giúp cả nhóm dùng cùng vocabulary:

| Relation | Loại | Ý nghĩa | Target |
| --- | --- | --- | --- |
| `self` | IANA | Chính resource hiện tại | Chi tiết order |
| `collection` | IANA | Collection chứa order | Danh sách orders |
| `next` | IANA | Trang tiếp theo | Trang kế tiếp |
| `.../customer` | Extension URI | Khách hàng của order | Chi tiết customer |
| `.../cancel-order` | Extension URI | Action hủy order | Endpoint cancellation |
| `.../approve-order` | Extension URI | Action duyệt order | Endpoint approval |

## 16. Các lỗi thường gặp và cách sửa

**Dùng `next` cho action tiếp theo trong workflow.** `next` chỉ quan hệ tới resource tiếp theo trong chuỗi. Dùng extension relation như `.../approve-order` hoặc `.../submit-order` cho action nghiệp vụ.

**Dùng `self` cho collection từ item.** `self` phải trỏ tới item đang được biểu diễn. Dùng `collection` khi target là collection của item.

**Dùng `item` cho link tới collection.** `item` có nghĩa target là thành viên của collection context. Chọn `collection` khi điều hướng từ item về collection.

**Dùng `delete` làm relation vì endpoint dùng HTTP DELETE.** HTTP method và relation có trách nhiệm khác nhau. Đặt relation theo semantics của resource hoặc action; dùng affordance để mô tả method nếu cần.

**Dùng tên field làm relation.** Field là dữ liệu trong payload. Relation phải mô tả quan hệ tới resource khác.

**Dùng relation động theo ID hoặc trạng thái.** Relation phải ổn định. Đưa ID vào `href`, trạng thái vào representation và chỉ công bố action link khi phù hợp.

**Dùng `related` cho mọi link.** `related` quá chung khi API đã biết rõ target là customer, invoice hoặc shipment. Tạo extension relation cụ thể hoặc chọn IANA relation chính xác hơn.

**Tạo extension relation trùng nghĩa với IANA.** Dùng đúng relation chuẩn để client có thể tái sử dụng vocabulary.

**Dùng URI relation của ứng dụng để thay thế relation IANA.** `https://api.example.com/rels/next` không tương đương với `next`. Hãy giữ đúng loại relation.

**Dùng title thay cho rel.** Title là nhãn hiển thị, có thể thay đổi hoặc dịch. Client cần relation ổn định để khám phá.

**Chỉ kiểm thử URL.** URL có thể hợp lệ trong khi relation sai. Test cả semantics của relation và target.

## 17. Ghi nhớ

Link relation là semantics công khai của kết nối giữa resource hiện tại và resource đích. Đừng dùng relation như tên method, HTTP method, tên field, dữ liệu động hoặc nhãn hiển thị. Relation chuẩn phải được dùng đúng ý nghĩa; relation nghiệp vụ riêng cần extension URI ổn định thuộc quyền kiểm soát của API.

Trong Spring HATEOAS, dùng `IanaLinkRelations` cho relation IANA và `LinkRelation.of(...)` cho extension relation. Dùng `WebMvcLinkBuilder` để tạo URI theo mapping controller. Với action cần mô tả method hoặc input, bổ sung affordance hay HAL-FORMS thay vì nhét những thông tin đó vào tên relation.

Cuối cùng, kiểm thử cả `rel` và `href`, kiểm tra sự hiện diện của action theo trạng thái, và duy trì một catalog relation dùng chung. Một vocabulary chính xác giúp client điều hướng API ổn định ngay cả khi server thay đổi route hoặc implementation.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA – Link Relation Types Registry](https://www.iana.org/assignments/link-relations/)
- [Spring HATEOAS Reference – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API – LinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkBuilder.html)
- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
