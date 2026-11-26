# Phần tử trong collection

## Mục tiêu

Một collection trong REST API thường chứa nhiều tài nguyên cùng loại, chẳng hạn danh sách đơn hàng, khách hàng hoặc sản phẩm. Với Spring HATEOAS, CollectionModel<T> biểu diễn tập các phần tử đó và có thể mang thêm links ở cấp collection. Mỗi phần tử cũng có thể là một hypermedia model riêng để chứa dữ liệu cùng links điều hướng tới chính tài nguyên hoặc hành động khả dụng.

Sau bài học, bạn có thể:

- Hiểu vai trò của CollectionModel<T> và kiểu phần tử T.
- Chọn kiểu phần tử phù hợp: DTO, EntityModel hoặc custom RepresentationModel.
- Chuyển từng phần tử thành hypermedia model bằng RepresentationModelAssembler.
- Kiểm soát relation dùng cho collection nhúng trong HAL.
- Xử lý collection rỗng và kiểm thử links ở cấp item lẫn cấp collection.

## CollectionModel và phần tử bên trong

CollectionModel<T> là một representation chứa một tập phần tử kiểu T cùng các links ở cấp collection. Bản thân CollectionModel cũng kế thừa RepresentationModel, vì vậy có thể gắn link self, link tìm kiếm, link tạo tài nguyên hoặc các link điều hướng khác.

Kiểu T quyết định nội dung mỗi phần tử:

| Kiểu phần tử | Đặc điểm | Khi phù hợp |
|---|---|---|
| DTO thuần, ví dụ OrderSummary | Chỉ chứa dữ liệu; không tự mang links. | Collection chỉ cần dữ liệu và links ở cấp collection. |
| EntityModel<OrderSummary> | Bọc DTO và links riêng cho từng item. | DTO đã phù hợp, nhưng mỗi phần tử cần self hoặc action links. |
| Custom model, ví dụ OrderModel extends RepresentationModel<OrderModel> | Kiểu response riêng, có dữ liệu và links. | API cần representation chuyên biệt, dùng nhất quán ở nhiều endpoint. |

Ví dụ, CollectionModel<OrderSummary> có thể biểu diễn danh sách các DTO đơn giản. Nếu client cần mở từng đơn hàng bằng link self, dùng CollectionModel<EntityModel<OrderSummary>> hoặc CollectionModel<OrderModel>. Khi đó, mỗi phần tử có thể cung cấp điều hướng riêng, còn CollectionModel cung cấp điều hướng cho toàn bộ tập.

Không nên đưa entity JPA trực tiếp vào collection response. Hãy chuyển entity thành DTO hoặc representation model để kiểm soát dữ liệu công khai, tránh serialize quan hệ persistence không mong muốn và giữ hợp đồng HTTP độc lập với schema lưu trữ.

## Biểu diễn một phần tử có links

Một phần tử có thể được bọc bằng EntityModel mà không cần DTO kế thừa Spring HATEOAS:

~~~java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

OrderSummary summary = OrderSummary.from(order);

EntityModel<OrderSummary> item = EntityModel.of(summary)
        .add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());
~~~

Khi có hành động phụ thuộc trạng thái, có thể bổ sung link vào chính item:

~~~java
if (order.canBeCancelled()) {
    item.add(linkTo(methodOn(OrderController.class)
            .cancel(order.getId(), null)).withRel("cancel"));
}
~~~

Điều này giúp client tìm link self hoặc cancel ngay trong phần tử tương ứng. Client không phải ghép URL từ ID hoặc suy đoán hành động từ trường status. Endpoint vẫn phải kiểm tra quyền và trạng thái mới nhất khi request được thực hiện.

Nếu cần dùng kiểu representation riêng, tạo custom model kế thừa RepresentationModel:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Mỗi OrderModel có dữ liệu của một đơn hàng và tập links riêng. Annotation @Relation khai báo tên relation của item và collection để hypermedia relation resolver có thể sử dụng khi serialize. Cần giữ các tên này ổn định vì client có thể dựa vào relation để tìm phần tử trong HAL.

## Dùng assembler để tạo collection

RepresentationModelAssembler<T, D> định nghĩa cách chuyển một đối tượng nguồn thành representation. Khi dùng custom OrderModel, assembler có thể tạo links cho từng phần tử và cung cấp phương thức toCollectionModel để chuyển cả tập:

~~~java
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null)).withRel("cancel"));
        }

        return model;
    }
}
~~~

Phương thức toCollectionModel mặc định gọi toModel cho từng phần tử và đóng gói kết quả trong CollectionModel. Vì toModel gắn link self và cancel, các phần tử trong collection cũng có đúng những links đó theo trạng thái riêng của từng đơn hàng. Có thể giữ implementation mặc định và không override phương thức này nếu không cần thay đổi cách chuyển collection.

Controller bổ sung link cấp collection:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    OrderModel findById(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }

    @GetMapping
    CollectionModel<OrderModel> findAll() {
        return assembler.toCollectionModel(orderService.findAll())
                .add(linkTo(methodOn(OrderController.class)
                        .findAll()).withSelfRel());
    }
}
~~~

Ở đây có hai cấp điều hướng:

- Link ở cấp collection, chẳng hạn self, mô tả danh sách đang được trả về.
- Links trong từng OrderModel, chẳng hạn self và cancel, mô tả tài nguyên đơn hàng tương ứng.

Không nên đặt tất cả links của từng đơn hàng lên collection root. Nếu mỗi item có trạng thái hoặc quyền khác nhau, link phải nằm trên item tương ứng để client không nhầm hành động của tài nguyên này với hành động của tài nguyên khác.

## Collection trong HAL

Khi CollectionModel được serialize thành HAL JSON, các phần tử thường được đặt trong _embedded; links của collection nằm trong _links. Với @Relation(itemRelation = "order", collectionRelation = "orders"), collection relation là orders:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PENDING",
        "total": 125.50,
        "_links": {
          "self": {
            "href": "/api/orders/order-42"
          },
          "cancel": {
            "href": "/api/orders/order-42/cancellation"
          }
        }
      },
      {
        "id": "order-43",
        "status": "SHIPPED",
        "total": 80.00,
        "_links": {
          "self": {
            "href": "/api/orders/order-43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/api/orders"
    }
  }
}
~~~

Hai item có cấu trúc dữ liệu tương tự nhưng links khác nhau vì trạng thái khác nhau. Client đọc orders trong _embedded, sau đó đọc _links của từng item để điều hướng. Quan hệ orders là một phần hợp đồng API; đổi tên relation có thể làm client không còn tìm thấy collection dù URI endpoint vẫn giữ nguyên.

itemRelation mô tả quan hệ của từng phần tử; collectionRelation mô tả quan hệ của collection trong representation hypermedia. Hãy chọn tên số ít và số nhiều rõ ràng theo quy ước của API. Khi sử dụng DTO hoặc EntityModel thay cho custom model, cần kiểm tra relation resolver thực tế hoặc cấu hình relation provider phù hợp; không nên mặc định tên class sẽ luôn tạo ra tên embedded như mong muốn.

## Collection rỗng và fallback type

Collection rỗng vẫn là một response hợp lệ. Nó có thể mang link self và các link cấp collection khác dù không có item nào:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders"
    }
  }
}
~~~

Khi collection không có phần tử, serializer không thể suy luận kiểu phần tử từ một item thực tế. Nếu cần giữ relation ổn định cho collection rỗng, cung cấp fallback type cho CollectionModel:

~~~java
CollectionModel<OrderModel> model = CollectionModel
        .<OrderModel>empty()
        .withFallbackType(OrderModel.class)
        .add(linkTo(methodOn(OrderController.class)
                .findAll()).withSelfRel());
~~~

Fallback type cho serializer biết kiểu item dự kiến dù collection chưa có phần tử. Nhờ vậy, relation có thể được xác định nhất quán theo metadata của OrderModel. Hãy kiểm thử cả collection có dữ liệu và collection rỗng để xác nhận tên relation mà client nhận được. Với phiên bản Spring HATEOAS đang dùng, kiểm tra API CollectionModel tương ứng nếu overload hoặc cách khai báo generic có khác biệt.

## Phân trang và links cấp collection

CollectionModel biểu diễn một tập phần tử. Nếu API cần metadata trang như số trang hiện tại, kích thước trang và tổng số phần tử, dùng PagedModel hoặc tích hợp Spring Data phù hợp thay vì tự thêm các trường phân trang rời rạc vào DTO.

Một trang collection có thể công bố các quan hệ:

- first: trang đầu tiên.
- prev: trang trước nếu tồn tại.
- self: trang hiện tại.
- next: trang tiếp theo nếu tồn tại.
- last: trang cuối cùng.

Các links này thuộc cấp collection, còn links self hoặc cancel của từng OrderModel vẫn thuộc item. Khi query, filter hoặc sort thay đổi, link trang phải giữ các tham số cần thiết để client tiếp tục điều hướng trong cùng tập kết quả. Không tự tạo URL trang bằng nối chuỗi; dùng cơ chế link builder hoặc assembler phân trang của Spring HATEOAS/Spring Data.

## Kiểm thử item relation và collection relation

Kiểm thử response collection cần xác minh cả cấu trúc _embedded, links của collection và links của từng phần tử. Ví dụ với MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orders").isArray())
        .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orders[0]._links.cancel.href").exists());
~~~

Nên tạo fixture có ít nhất hai trạng thái khác nhau và kiểm tra item không thể hủy không có link cancel. Với collection rỗng, kiểm tra response vẫn có status phù hợp và link self; nếu hợp đồng yêu cầu relation _embedded ổn định ngay cả khi rỗng, kiểm tra thêm fallback type và relation thực tế theo cấu hình serializer.

Các kiểm thử này bảo vệ hợp đồng hypermedia ở cả hai cấp. Khi refactor assembler hoặc đổi tên @Relation, test sẽ phát hiện thay đổi ảnh hưởng client.

## Những lỗi thường gặp

- **Dùng DTO thuần nhưng mong có links trên từng item:** DTO không tự mang link. Bọc mỗi DTO bằng EntityModel hoặc dùng custom RepresentationModel.
- **Đặt link item ở collection root:** client không biết link thuộc tài nguyên nào. Gắn links vào chính item.
- **Nhầm link cấp collection với link cấp item:** self của collection trỏ tới danh sách; self của item trỏ tới một tài nguyên riêng.
- **Không ổn định collection relation:** đổi orders thành purchases có thể phá client đang đọc _embedded.orders.
- **Không xét collection rỗng:** serializer có thể thiếu thông tin kiểu phần tử để xác định relation. Dùng fallback type khi cần và kiểm thử response rỗng.
- **Dùng CollectionModel cho dữ liệu phân trang mà không công bố điều hướng:** nếu có page metadata, cân nhắc PagedModel và links first/prev/next/last.
- **Đưa entity JPA trực tiếp vào collection:** có thể làm lộ trường nội bộ hoặc kích hoạt lazy loading. Chuyển qua DTO/model công khai.
- **Cho rằng links thay thế authorization:** endpoint vẫn phải kiểm tra quyền và trạng thái khi client gửi request.

## Quy trình xây dựng collection representation

1. Chọn kiểu phần tử: DTO thuần, EntityModel hoặc custom RepresentationModel.
2. Nếu item cần links, tạo chúng trong assembler dựa trên trạng thái của từng phần tử.
3. Dùng toCollectionModel hoặc CollectionModel.of để tạo tập phần tử.
4. Gắn links cấp collection như self, search hoặc điều hướng trang.
5. Xác định item relation và collection relation ổn định cho HAL; xử lý fallback type nếu collection có thể rỗng.
6. Kiểm thử collection có dữ liệu, collection rỗng, links từng item và links cấp collection.

CollectionModel giúp API biểu diễn tập tài nguyên như một hypermedia resource hoàn chỉnh. Khi mỗi phần tử giữ links phù hợp với trạng thái của chính nó và collection có links điều hướng riêng, client có thể khám phá cả danh sách lẫn từng tài nguyên mà không phải tự xây URL hoặc suy đoán hành động.
