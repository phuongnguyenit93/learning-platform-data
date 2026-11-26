# EntityModel lồng nhau

Trong REST API, một tài nguyên thường liên quan đến những tài nguyên khác. Đơn hàng có các dòng hàng, khách hàng có địa chỉ, bài viết có bình luận. Khi client đọc một tài nguyên cha, API có thể cung cấp liên kết để khám phá tài nguyên con hoặc trả về một tập hợp tài nguyên con trong cùng luồng điều hướng.

Spring HATEOAS dùng EntityModel để bọc biểu diễn của một tài nguyên cùng các liên kết của nó. Khi cần biểu diễn nhiều tài nguyên con, có thể dùng CollectionModel<EntityModel<T>>: CollectionModel mô tả tập hợp, còn mỗi EntityModel mô tả một phần tử có dữ liệu và liên kết riêng. Đây là cấu trúc quan trọng khi thiết kế các mối quan hệ lồng nhau trong API.

Bài học này sử dụng ví dụ đơn hàng và dòng hàng để giải thích cách tạo EntityModel cha, cách mô hình hóa các EntityModel con, cách công bố quan hệ trong HAL, khi nào nên nhúng dữ liệu và cách kiểm thử cấu trúc trả về.

## 1. EntityModel đại diện cho một resource

EntityModel<T> là wrapper của Spring HATEOAS dành cho một đối tượng nội dung. Nó kế thừa khả năng chứa liên kết từ RepresentationModel, vì vậy có thể biểu diễn dữ liệu và các đường dẫn liên quan trong cùng một mô hình.

Ví dụ, một đơn hàng có dữ liệu:

~~~java
public record OrderDto(
        Long id,
        String status,
        long total
) {
}
~~~

Assembler có thể bọc DTO thành EntityModel và gắn link:

~~~java
EntityModel<OrderDto> model = EntityModel.of(
        orderDto,
        linkTo(methodOn(OrderController.class)
                .one(orderDto.id())).withSelfRel(),
        linkTo(methodOn(OrderController.class)
                .all()).withRel("orders")
);
~~~

Khi controller trả EntityModel<OrderDto> và ứng dụng đã cấu hình HAL, phản hồi có thể có dạng:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
~~~

Trong ví dụ, EntityModel bao bọc một tài nguyên đơn hàng. Link self dẫn đến chính đơn hàng; link orders dẫn đến tập hợp đơn hàng. EntityModel không tự tạo URI và cũng không quyết định nghiệp vụ; controller hoặc assembler phải cung cấp các link phù hợp.

## 2. Hiểu cấu trúc cha và con

Giả sử một đơn hàng có nhiều dòng hàng. Mỗi dòng hàng có mã, tên sản phẩm, số lượng và giá tại thời điểm đặt hàng. Một client có thể cần:

- Đọc thông tin chung của đơn hàng.
- Khám phá tập hợp dòng hàng thuộc đơn hàng.
- Mở một dòng hàng cụ thể.
- Theo liên kết từ dòng hàng trở lại đơn hàng.

Có thể mô hình hóa quan hệ đó như sau:

~~~mermaid
flowchart TD
    O["Order resource<br/>EntityModel<OrderDto>"]
    I["Items collection<br/>CollectionModel<EntityModel<OrderItemDto>>"]
    I1["Order item 1<br/>EntityModel<OrderItemDto>"]
    I2["Order item 2<br/>EntityModel<OrderItemDto>"]
    I3["Order item n<br/>EntityModel<OrderItemDto>"]
    O -->|"rel: items"| I
    I --> I1
    I --> I2
    I --> I3
    I1 -->|"rel: order"| O
    I2 -->|"rel: order"| O
~~~

Trong cấu trúc này:

- EntityModel<OrderDto> biểu diễn đơn hàng cha.
- CollectionModel<EntityModel<OrderItemDto>> biểu diễn tập hợp dòng hàng.
- Mỗi EntityModel<OrderItemDto> là một tài nguyên con, có link self và link order.

CollectionModel là lớp bao cho tập hợp. Các phần tử của tập hợp là EntityModel riêng biệt, do đó từng phần tử có thể có link relation khác nhau. Đây là mẫu phổ biến để biểu diễn một collection gồm các resource con trong Spring HATEOAS.

Không cần tạo EntityModel<EntityModel<OrderDto>> để thể hiện quan hệ cha-con. Bọc một EntityModel bên trong một EntityModel khác thường làm cấu trúc dữ liệu khó hiểu và không diễn đạt rõ collection relation. Hãy chọn kiểu wrapper theo số lượng resource: EntityModel cho một resource, CollectionModel<EntityModel<T>> cho một tập hợp resource.

## 3. Thiết kế DTO cho tài nguyên cha và con

Domain model và representation không nhất thiết có cùng cấu trúc. DTO giúp kiểm soát dữ liệu được công bố cho client.

Ví dụ domain model rút gọn:

~~~java
import java.util.List;

public record OrderItem(
        Long id,
        Long orderId,
        String productName,
        int quantity,
        long unitPrice
) {
}

public record Order(
        Long id,
        String status,
        List<OrderItem> items
) {
}
~~~

DTO của đơn hàng:

~~~java
public record OrderDto(
        Long id,
        String status,
        long total
) {
}
~~~

DTO của dòng hàng:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(collectionRelation = "items")
public record OrderItemDto(
        Long id,
        String productName,
        int quantity,
        long unitPrice
) {
}
~~~

Annotation Relation cho phép chỉ định tên relation dùng khi Spring HATEOAS biểu diễn collection trong định dạng hypermedia. Ở đây collection các OrderItemDto được đặt tên items. Nếu không chỉ định, tên relation có thể được suy ra từ kiểu nội dung và quy tắc rel provider đang cấu hình; với API công khai, nên xác định tên quan hệ có chủ đích và kiểm thử kết quả.

Trong dự án Java thực tế, mỗi kiểu public ở ví dụ trên được đặt trong file nguồn riêng. Các lớp được đặt chung một khối để minh họa mối quan hệ giữa chúng.

## 4. Tạo EntityModel cho từng tài nguyên con

Assembler của dòng hàng chuyển OrderItem thành OrderItemDto và thêm các liên kết cần thiết:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderItemModelAssembler
        implements RepresentationModelAssembler<OrderItem, EntityModel<OrderItemDto>> {

    @Override
    public EntityModel<OrderItemDto> toModel(OrderItem item) {
        OrderItemDto dto = new OrderItemDto(
                item.id(),
                item.productName(),
                item.quantity(),
                item.unitPrice()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .item(item.orderId(), item.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(item.orderId())).withRel("order")
        );
    }
}
~~~

Mỗi dòng hàng có link self đến endpoint chi tiết của chính nó và link order dẫn ngược về đơn hàng cha. Nhờ đó, client có thể điều hướng từ collection đến một item rồi quay lại resource cha bằng quan hệ được công bố.

Assembler chỉ chịu trách nhiệm chuyển đổi và tạo link. Nó không nên truy vấn repository hoặc quyết định một dòng hàng có được phép sửa hay không. Các quy tắc đó thuộc application service và domain model.

## 5. Tạo EntityModel cho resource cha

Assembler của đơn hàng có thể công bố link đến tập hợp dòng hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.status(),
                order.items().stream()
                        .mapToLong(item -> item.quantity() * item.unitPrice())
                        .sum()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .items(order.id())).withRel("items")
        );
    }
}
~~~

Đơn hàng cha không cần nhúng tất cả dòng hàng vào DTO. Link items cho biết client có thể khám phá tập hợp con qua một endpoint riêng. Cách này phù hợp khi danh sách con có thể lớn, cần phân trang hoặc được truy cập độc lập.

Nếu dòng hàng ít và luôn được hiển thị cùng đơn hàng, API có thể chọn nhúng các trường tóm tắt như productName và quantity trong OrderDto. Khi đó, dữ liệu con là một phần của representation cha, không phải mỗi dòng hàng là một resource hypermedia độc lập. Nếu từng dòng hàng cần link riêng, hãy biểu diễn chúng thành các EntityModel trong collection.

## 6. Tạo CollectionModel chứa các EntityModel con

Spring HATEOAS cung cấp toCollectionModel trong RepresentationModelAssembler. Phương thức này chuyển một iterable thành CollectionModel có các phần tử do toModel tạo ra.

Ví dụ service:

~~~java
import java.util.List;

public interface OrderService {
    Order getRequired(Long orderId);
    List<OrderItem> findItems(Long orderId);
}
~~~

Controller có thể cung cấp resource cha, collection con và item con:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;
    private final OrderItemModelAssembler itemAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler,
            OrderItemModelAssembler itemAssembler
    ) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping(value = "/{orderId}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(@PathVariable Long orderId) {
        return orderAssembler.toModel(orderService.getRequired(orderId));
    }

    @GetMapping(
            value = "/{orderId}/items",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public CollectionModel<EntityModel<OrderItemDto>> items(
            @PathVariable Long orderId
    ) {
        orderService.getRequired(orderId);

        return itemAssembler.toCollectionModel(
                orderService.findItems(orderId)
        ).add(
                linkTo(methodOn(OrderController.class)
                        .items(orderId)).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(orderId)).withRel("order")
        );
    }

    @GetMapping(
            value = "/{orderId}/items/{itemId}",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public EntityModel<OrderItemDto> item(
            @PathVariable Long orderId,
            @PathVariable Long itemId
    ) {
        OrderItem item = orderService.findItems(orderId).stream()
                .filter(candidate -> candidate.id().equals(itemId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Item not found"));

        return itemAssembler.toModel(item);
    }
}
~~~

Ví dụ tập trung vào cách tạo mô hình. Trong ứng dụng thực tế, nên có phương thức service lấy một dòng hàng theo cả orderId và itemId để tránh tải toàn bộ collection chỉ để tìm một phần tử. Service cũng cần xác nhận item thực sự thuộc order được yêu cầu và ánh xạ lỗi thành HTTP status phù hợp.

Khi client gọi GET /api/orders/42, API trả EntityModel<OrderDto> cùng link items. Client theo href của items để lấy collection. Phản hồi collection có các phần tử EntityModel riêng, mỗi phần tử chứa link self và order. Client có thể theo self để mở một dòng hàng cụ thể.

## 7. HAL thể hiện resource lồng nhau

Với controller trả CollectionModel<EntityModel<OrderItemDto>> và HAL được cấu hình, collection được biểu diễn qua vùng _embedded. Ví dụ:

~~~http
GET /api/orders/42/items
Accept: application/hal+json
~~~

Phản hồi minh họa:

~~~json
{
  "_embedded": {
    "items": [
      {
        "id": 1,
        "productName": "Keyboard",
        "quantity": 1,
        "unitPrice": 850000,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/42/items/1"
          },
          "order": {
            "href": "https://api.example.com/api/orders/42"
          }
        }
      },
      {
        "id": 2,
        "productName": "Mouse",
        "quantity": 2,
        "unitPrice": 200000,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/42/items/2"
          },
          "order": {
            "href": "https://api.example.com/api/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42/items"
    },
    "order": {
      "href": "https://api.example.com/api/orders/42"
    }
  }
}
~~~

Trong HAL:

- _embedded chứa các resource con được nhúng trong representation của collection.
- Mỗi phần tử có các trường dữ liệu riêng và _links riêng.
- _links ở cấp collection mô tả collection và quan hệ với resource cha.
- Tên items đến từ quy tắc relation của kiểu nội dung, có thể tùy chỉnh bằng @Relation.

Đây là một cấu trúc lồng nhau theo quan hệ resource: collection chứa các EntityModel con và mỗi con mang link. Việc collection được nhúng trong response của endpoint items không có nghĩa nó tự động nằm bên trong JSON body của resource order. Resource order công bố liên kết items; client theo liên kết để lấy representation của collection.

## 8. Phân biệt link đến resource con và nhúng dữ liệu con

Hai cách biểu diễn này giải quyết nhu cầu khác nhau:

| Cách biểu diễn | Kết quả | Phù hợp khi |
| --- | --- | --- |
| Link đến collection con | Parent có rel items trỏ đến endpoint collection | Collection lớn, cần phân trang hoặc được truy cập độc lập |
| Nhúng dữ liệu con đơn giản | Parent chứa mảng DTO con trong nội dung | Client luôn cần dữ liệu tóm tắt cùng parent |
| CollectionModel<EntityModel<T>> | Collection có các phần tử con với link riêng | Mỗi phần tử cần định danh và điều hướng độc lập |

Một trường List<OrderItemDto> bên trong OrderDto là dữ liệu lồng nhau thông thường. Nó không tự động tương đương với một collection hypermedia có link self cho từng item. Nếu client cần điều hướng đến từng dòng hàng, hãy cung cấp EntityModel cho mỗi item và một CollectionModel bao quanh chúng.

Nếu muốn nhúng collection con trực tiếp vào representation cha, cần thiết kế kiểu representation và cơ chế HAL serialization có chủ đích. Không nên giả định mọi thuộc tính Java chứa EntityModel hoặc CollectionModel sẽ tự động được tuần tự hóa thành _embedded đúng quan hệ. Hãy kiểm tra JSON thực tế bằng kiểm thử tích hợp. Với nhiều API, link đến collection con là cách đơn giản và dễ kiểm soát hơn.

## 9. Đặt tên relation cho collection và item

Relation cho biết một link hoặc một collection embedded có ý nghĩa gì. Các quan hệ chuẩn như self, next, prev, first và last có ý nghĩa phổ biến. Quan hệ items hoặc order trong ví dụ là quan hệ do API định nghĩa.

Với kiểu nội dung dùng trong collection, @Relation(collectionRelation = "items") giúp đặt tên collection relation rõ ràng. Nếu không tùy chỉnh, Spring HATEOAS dùng relation provider để suy ra tên từ kiểu nội dung. Kết quả phụ thuộc cấu hình relation provider và quy ước đặt tên của ứng dụng.

Các nguyên tắc đặt tên:

1. Dùng tên ngắn, mô tả đúng quan hệ và nhất quán giữa các endpoint.
2. Không dùng tên relation để tiết lộ tên lớp Java hoặc tên bảng persistence.
3. Không đổi ý nghĩa của relation đã được client sử dụng.
4. Với API công khai hoặc cần tránh xung đột tên, cân nhắc URI relation cho quan hệ mở rộng.
5. Kiểm thử tên relation trong HAL output thay vì chỉ dựa vào suy đoán từ tên class.

## 10. Phân trang collection con

Collection con có thể tăng nhanh theo thời gian. Ví dụ một đơn hàng có lịch sử thay đổi hoặc các sự kiện xử lý lớn. Khi đó, endpoint items hoặc events nên hỗ trợ phân trang.

Với Spring Data, PagedResourcesAssembler có thể chuyển Page<OrderItem> thành PagedModel<EntityModel<OrderItemDto>>:

~~~java
@GetMapping(
        value = "/{orderId}/items",
        produces = MediaTypes.HAL_JSON_VALUE
)
public PagedModel<EntityModel<OrderItemDto>> items(
        @PathVariable Long orderId,
        Pageable pageable,
        PagedResourcesAssembler<OrderItem> pagedAssembler
) {
    orderService.getRequired(orderId);
    Page<OrderItem> page = orderService.findItems(orderId, pageable);

    return pagedAssembler.toModel(page, itemAssembler);
}
~~~

Đoạn mã giả định OrderService có phương thức findItems(Long, Pageable) trả về Page<OrderItem> và ứng dụng đã tích hợp Spring Data Web. PagedModel chứa metadata trang và các liên kết điều hướng phù hợp như first, prev, next, last. Mỗi item vẫn được tạo bởi itemAssembler, do đó các link self và order được giữ nhất quán.

Khi collection được phân trang, client nên theo link next hoặc prev mà server trả về. Client không nên tự cộng số trang hoặc tự tạo URI theo cấu trúc query parameter.

## 11. Kiểm thử EntityModel lồng nhau

Kiểm thử cần xác nhận cấu trúc collection, relation name và link của từng phần tử. Ví dụ kiểm tra endpoint items bằng MockMvc:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import({OrderModelAssembler.class, OrderItemModelAssembler.class})
class OrderItemsControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsEmbeddedItemsWithTheirOwnLinks() throws Exception {
        Order order = new Order(42L, "PENDING", List.of());
        List<OrderItem> items = List.of(
                new OrderItem(1L, 42L, "Keyboard", 1, 850000),
                new OrderItem(2L, 42L, "Mouse", 2, 200000)
        );

        when(orderService.getRequired(42L)).thenReturn(order);
        when(orderService.findItems(42L)).thenReturn(items);

        mockMvc.perform(get("/api/orders/42/items")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.items.length()").value(2))
                .andExpect(jsonPath("$._embedded.items[0].id").value(1))
                .andExpect(jsonPath(
                        "$._embedded.items[0]._links.self.href").exists())
                .andExpect(jsonPath(
                        "$._embedded.items[0]._links.order.href").exists())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.order.href").exists());
    }
}
~~~

Đây là ví dụ minh họa cho cấu trúc test slice. Các kiểu Order, OrderItem, OrderService và controller cần được đặt trong package mà test có thể truy cập. @Import đăng ký các assembler trong WebMvcTest; service được mock để kiểm soát dữ liệu.

Ngoài trường hợp collection có dữ liệu, nên kiểm thử:

- Collection rỗng vẫn trả về cấu trúc HAL và link collection đúng.
- Resource cha không tồn tại trả về status phù hợp, thường là 404.
- Item không thuộc order được yêu cầu không được trả về.
- Relation name trong _embedded giữ đúng là items.
- Mỗi item có self và order link trỏ đúng resource.
- Client yêu cầu media type không được hỗ trợ nhận phản hồi lỗi theo hợp đồng.
- Collection phân trang có metadata và link điều hướng chính xác.

Nên kiểm tra rel và hành vi mà client cần dựa vào. Hostname, cổng và context path có thể khác giữa môi trường, vì vậy không nên khóa test vào một URL tuyệt đối nếu điều đó không phải yêu cầu của hợp đồng.

## 12. Những lỗi thường gặp

**Bọc EntityModel nhiều tầng không cần thiết.** EntityModel<EntityModel<T>> không phải cấu trúc mặc định để diễn tả quan hệ cha-con. Dùng EntityModel cho một resource và CollectionModel<EntityModel<T>> cho collection con.

**Chỉ nhúng List DTO nhưng kỳ vọng mỗi phần tử có link.** DTO thuần không có link relation riêng. Khi mỗi item cần được điều hướng, hãy dùng EntityModel cho item.

**Gắn link collection nhưng không gắn link self cho từng item.** Client có thể biết collection ở đâu nhưng không thể khám phá ổn định URI của từng item. Hãy thêm self link trong item assembler.

**Không xác định relation name.** Tên collection có thể được suy ra theo quy tắc mặc định và khác với tên client mong đợi. Dùng @Relation khi cần tên rõ ràng và kiểm thử HAL output.

**Nhúng collection lớn vào parent.** Phản hồi có thể phình to và khó phân trang. Cung cấp link đến collection con khi danh sách lớn hoặc được truy cập độc lập.

**Cho rằng embedded resource thay thế kiểm tra quyền.** Client có thể lưu URI và gọi lại sau khi quyền hoặc trạng thái đã thay đổi. Endpoint vẫn phải xác thực và kiểm tra nghiệp vụ.

**Để assembler truy vấn dữ liệu.** Assembler nên nhận domain object hoặc DTO đã được service chuẩn bị, sau đó chuyển đổi và tạo link. Truy vấn và nghiệp vụ thuộc application service.

## 13. Ghi nhớ

EntityModel<T> bọc một resource cùng các liên kết. CollectionModel<EntityModel<T>> biểu diễn một tập hợp mà mỗi phần tử là một resource độc lập có thể mang link self và các quan hệ khác. Trong ví dụ đơn hàng, EntityModel<OrderDto> công bố link items; endpoint items trả CollectionModel<EntityModel<OrderItemDto>>, còn từng dòng hàng có link self và order.

HAL dùng _embedded để thể hiện các phần tử của collection và _links để thể hiện liên kết điều hướng. @Relation có thể tùy chỉnh tên collection relation. Nhúng dữ liệu DTO đơn giản phù hợp khi client chỉ cần snapshot; dùng EntityModel cho từng phần tử khi client cần điều hướng đến chúng như resource độc lập. Nếu cần nhúng collection trực tiếp vào representation cha, hãy thiết kế kiểu biểu diễn và xác minh kết quả tuần tự hóa thực tế.

Hãy giữ assembler tập trung vào chuyển đổi và tạo link, service chịu trách nhiệm truy vấn và nghiệp vụ, controller công bố các representation theo HTTP. Kiểm thử cả cấu trúc _embedded, tên relation, link của từng item và hành vi khi resource cha hoặc con không tồn tại.
