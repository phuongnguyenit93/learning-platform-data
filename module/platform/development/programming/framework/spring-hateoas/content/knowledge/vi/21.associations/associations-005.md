# Nested resource

Trong REST API, **nested resource** là tài nguyên được truy cập trong ngữ cảnh của một tài nguyên cha. Ví dụ, các dòng hàng thuộc một đơn hàng có thể được truy cập qua `/orders/{orderId}/items`, còn một dòng hàng cụ thể nằm trong đơn hàng đó có thể được truy cập qua `/orders/{orderId}/items/{itemId}`. Cấu trúc URI thể hiện mối quan hệ giữa tài nguyên cha và tài nguyên con.

Spring HATEOAS giúp API công bố mối quan hệ này bằng hypermedia link. Controller có thể dùng mapping lồng nhau, assembler tạo link đến item và collection, còn client khám phá các liên kết `items`, `order`, `product` hoặc `self` từ response. Khi thiết kế nested resource, cần xác định rõ quyền sở hữu giữa cha và con, URI nào định danh tài nguyên, và liệu dữ liệu có được nhúng trong response hay chỉ được liên kết.

## 1. Nested resource là gì?

Giả sử một hệ thống thương mại điện tử có các tài nguyên `Order` và `OrderItem`. Một đơn hàng có nhiều dòng hàng; mỗi dòng hàng chỉ có ý nghĩa trong phạm vi đơn hàng đó. API có thể biểu diễn quan hệ như sau:

```text
/orders/{orderId}
/orders/{orderId}/items
/orders/{orderId}/items/{itemId}
```

Các URI có ý nghĩa:

| URI | Tài nguyên được truy cập |
| --- | --- |
| `/orders/ORD-101` | Một đơn hàng |
| `/orders/ORD-101/items` | Collection dòng hàng thuộc đơn hàng ORD-101 |
| `/orders/ORD-101/items/ITEM-7` | Dòng hàng ITEM-7 trong ngữ cảnh đơn hàng ORD-101 |

Nested resource thể hiện ngữ cảnh quan hệ qua đường dẫn. Khi client truy cập `/orders/ORD-101/items/ITEM-7`, server cần xác nhận `ITEM-7` thực sự thuộc `ORD-101`. Chỉ kiểm tra `itemId` tồn tại là chưa đủ nếu cùng một endpoint có thể nhận nhiều `orderId`.

## 2. Khi nào nên dùng URI lồng nhau?

URI lồng nhau phù hợp khi tài nguyên con được quản lý hoặc diễn giải trong phạm vi tài nguyên cha. Một số ví dụ:

- `/customers/{customerId}/addresses`: địa chỉ được quản lý trong hồ sơ khách hàng.
- `/projects/{projectId}/tasks`: các công việc thuộc một dự án.
- `/orders/{orderId}/items`: các dòng hàng cấu thành đơn hàng.
- `/accounts/{accountId}/transactions`: giao dịch trong phạm vi một tài khoản.

Nên cân nhắc mức độ phụ thuộc của tài nguyên con:

| Đặc điểm | Thiết kế thường phù hợp |
| --- | --- |
| Child không có ý nghĩa độc lập và luôn được truy cập qua parent | Dùng URI lồng nhau |
| Child có định danh ổn định và được nhiều parent tham chiếu | Có thể có URI riêng cho child, đồng thời cung cấp link quan hệ từ parent |
| Child có thể chuyển từ parent này sang parent khác | Cân nhắc URI canonical độc lập để việc chuyển quan hệ không làm thay đổi định danh chính |
| Quan hệ có nhiều tầng nhưng các tầng không tạo thêm ngữ nghĩa | Dùng URI ngắn hơn và biểu diễn quan hệ bằng link |

Nesting không phải mục tiêu tự thân. Không cần lồng URI qua nhiều cấp chỉ vì mô hình database có nhiều quan hệ. Đường dẫn nên thể hiện ngữ cảnh có ích cho client và giúp server xác định rõ phạm vi thao tác.

## 3. Nested URI không đồng nghĩa với embedded resource

Hai khái niệm này thường bị nhầm lẫn:

- **Nested URI** mô tả cách định địa chỉ tài nguyên, ví dụ `/orders/ORD-101/items/ITEM-7`.
- **Embedded representation** mô tả dữ liệu của một tài nguyên khác được đưa trực tiếp vào response, chẳng hạn HAL `_embedded`.

Một nested resource có thể được trả về riêng qua URI lồng nhau mà không nhúng dữ liệu vào response của parent. Ngược lại, response của một resource có thể nhúng dữ liệu liên quan dù tài nguyên được nhúng có URI độc lập.

Ví dụ, response đơn hàng có thể chỉ cung cấp link đến collection dòng hàng:

```json
{
  "id": "ORD-101",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-101"
    },
    "items": {
      "href": "https://api.example.test/orders/ORD-101/items"
    }
  }
}
```

Client theo link `items` để tải collection riêng. Một response khác có thể nhúng các dòng hàng trong `_embedded.items`. Việc chọn link hay embedded phụ thuộc kích thước dữ liệu, nhu cầu điều hướng, tần suất thay đổi và hợp đồng API.

## 4. Thiết kế quan hệ parent-child

Trước khi tạo controller và link, cần xác định các quy tắc quan hệ:

1. Parent nào sở hữu hoặc chứa child?
2. Child có thể tồn tại độc lập hay chỉ có ý nghĩa trong parent?
3. Child có được chuyển sang parent khác không?
4. Khi parent bị xóa, child được xóa theo, lưu trữ hay giữ lại?
5. Quyền truy cập child có phụ thuộc quyền truy cập parent không?
6. API có cần URI canonical riêng cho child không?

Ví dụ, `OrderItem` là dòng hàng trong một đơn hàng. Một thiết kế phổ biến là coi dòng hàng thuộc đơn hàng và mọi thao tác cập nhật/xóa đều đi qua URI có cả `orderId` và `itemId`. Service phải xác minh quan hệ đó trong cùng truy vấn hoặc cùng luồng nghiệp vụ.

Nếu `Product` được tham chiếu bởi nhiều dòng hàng, không nên tạo URI như `/orders/{orderId}/items/{itemId}/product` như thể sản phẩm là con sở hữu riêng của dòng hàng. Có thể cung cấp relation `product` trỏ đến URI canonical `/products/{productId}`.

## 5. Khai báo controller cho nested resource

Spring MVC cho phép đặt prefix chứa path variable ở cấp class bằng `@RequestMapping`. Ví dụ controller quản lý các dòng hàng trong một đơn hàng:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders/{orderId}/items")
class OrderItemController {

    private final OrderItemService itemService;
    private final OrderItemModelAssembler assembler;

    OrderItemController(
            OrderItemService itemService,
            OrderItemModelAssembler assembler) {
        this.itemService = itemService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderItemRepresentation>> allForOrder(
            @PathVariable("orderId") UUID orderId) {
        return assembler.toCollectionModel(
                orderId, itemService.findAllForOrder(orderId));
    }

    @GetMapping("/{itemId}")
    EntityModel<OrderItemRepresentation> one(
            @PathVariable("orderId") UUID orderId,
            @PathVariable("itemId") UUID itemId) {
        return assembler.toModel(
                itemService.getRequired(orderId, itemId));
    }
}
```

Mapping ở cấp lớp xác định ngữ cảnh parent. Handler `allForOrder(...)` xử lý collection; handler `one(...)` xử lý một child trong collection đó. Service nhận cả `orderId` và `itemId` khi lấy một dòng hàng để bảo đảm child thuộc đúng parent.

`OrderItemService`, `OrderItemModelAssembler` và các DTO trong ví dụ là thành phần ứng dụng cần triển khai. Controller chịu trách nhiệm nhận path variable và điều phối request; quy tắc kiểm tra quan hệ và quyền nên được thực hiện trong service hoặc tầng nghiệp vụ phù hợp.

## 6. Tạo link cho nested resource bằng WebMvcLinkBuilder

Khi tạo link trong Spring HATEOAS, `WebMvcLinkBuilder` có thể tham chiếu handler của controller và truyền đầy đủ path variable:

Kiểu DTO có thể khai báo relation cho collection embedded để HAL dùng tên `items`:

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "item", collectionRelation = "items")
public record OrderItemRepresentation(UUID id, String sku, int quantity) {

    static OrderItemRepresentation from(OrderItem item) {
        return new OrderItemRepresentation(
                item.getId(), item.getSku(), item.getQuantity());
    }
}
```

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderItemModelAssembler implements
        RepresentationModelAssembler<OrderItem, EntityModel<OrderItemRepresentation>> {

    @Override
    public EntityModel<OrderItemRepresentation> toModel(OrderItem item) {
        return EntityModel.of(
                OrderItemRepresentation.from(item),
                linkTo(methodOn(OrderItemController.class)
                        .one(item.getOrderId(), item.getId())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .one(item.getOrderId())).withRel("order"),
                linkTo(methodOn(ProductController.class)
                        .one(item.getProductId())).withRel("product"));
    }
}
```

Assembler tạo ba liên kết:

- `self` trỏ đến dòng hàng qua URI lồng nhau.
- `order` trỏ ngược đến resource cha.
- `product` trỏ đến sản phẩm được dòng hàng tham chiếu.

`methodOn(...)` tạo proxy mô tả lời gọi handler để Spring HATEOAS đọc mapping và dựng URI; nó không chạy logic nghiệp vụ của controller. Với controller có mapping `@RequestMapping("/orders/{orderId}/items")` và `@GetMapping("/{itemId}")`, lời gọi `one(orderId, itemId)` cung cấp giá trị cho cả hai path variable.

Các controller `OrderController` và `ProductController` cần có handler `one(...)` tương ứng. Nếu ứng dụng dùng WebFlux, cần chọn `WebFluxLinkBuilder` và ghép kết quả reactive theo mô hình của WebFlux.

## 7. Link ở cấp collection nested

Collection các dòng hàng cũng là một resource có thể có link `self` và link quay về parent. Vì collection có thể rỗng, hãy truyền `orderId` riêng vào phương thức dựng model thay vì suy ra từ phần tử đầu tiên:

```java
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

CollectionModel<EntityModel<OrderItemRepresentation>> toCollectionModel(
        UUID orderId, List<OrderItem> items) {

    List<EntityModel<OrderItemRepresentation>> content = items.stream()
            .map(this::toModel)
            .collect(Collectors.toList());

    return CollectionModel.of(content,
            linkTo(methodOn(OrderItemController.class)
                    .allForOrder(orderId)).withSelfRel(),
            linkTo(methodOn(OrderController.class)
                    .one(orderId)).withRel("order"));
}
```

Ở đây, `orderId` là ngữ cảnh bắt buộc của collection, kể cả khi collection chưa có phần tử. `toModel(...)` là phương thức assembler đã trình bày ở phần trước.

## 8. HAL representation cho nested resource

Một dòng hàng được trả về riêng có thể được serialize theo HAL như sau:

```json
{
  "id": "ITEM-7",
  "sku": "SKU-RED-01",
  "quantity": 2,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-101/items/ITEM-7"
    },
    "order": {
      "href": "https://api.example.test/orders/ORD-101"
    },
    "product": {
      "href": "https://api.example.test/products/PROD-9"
    }
  }
}
```

Collection nested có thể có cấu trúc:

```json
{
  "_embedded": {
    "items": [
      {
        "id": "ITEM-7",
        "sku": "SKU-RED-01",
        "quantity": 2,
        "_links": {
          "self": {
            "href": "https://api.example.test/orders/ORD-101/items/ITEM-7"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-101/items"
    },
    "order": {
      "href": "https://api.example.test/orders/ORD-101"
    }
  }
}
```

`_embedded.items` chứa representation của các phần tử; `_links.self` ở root trỏ đến collection nested. Link `self` của từng item trỏ đến resource con cụ thể. Tên relation `items` cần ổn định trong hợp đồng API; có thể tùy chỉnh collection relation bằng `@Relation` trên kiểu representation nếu cần.

## 9. URI nested và URI canonical của child

Một child có thể được truy cập qua URI lồng nhau và cũng có URI canonical riêng. Ví dụ:

```text
/orders/ORD-101/items/ITEM-7
/order-items/ITEM-7
```

URI đầu tiên thể hiện child trong ngữ cảnh đơn hàng. URI thứ hai định danh dòng hàng độc lập. Có thể công bố cả hai link nếu ứng dụng có nhu cầu truy cập theo hai ngữ cảnh:

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderItemRepresentation> model = EntityModel.of(
        OrderItemRepresentation.from(item),
        linkTo(methodOn(OrderItemController.class)
                .one(item.getOrderId(), item.getId())).withSelfRel(),
        linkTo(methodOn(OrderItemResourceController.class)
                .one(item.getId())).withRel("canonical"));
```

Ở ví dụ này, `self` đại diện cho địa chỉ nested đang được dùng; relation `canonical` trỏ đến URI độc lập của child. Tên relation `canonical` là relation tùy chỉnh của hợp đồng này; cần tài liệu hóa để client hiểu.

Nếu child có thể chuyển parent, cần quyết định URI nào là định danh ổn định. Nếu chỉ có nested URI, việc đổi parent có thể làm thay đổi URI của child. Nếu child có định danh độc lập, URI canonical có thể giữ ổn định trong khi quan hệ với parent thay đổi.

Không nhất thiết phải công bố cả hai dạng URI. Hãy cung cấp nhiều địa chỉ chỉ khi chúng đại diện cho những cách truy cập có ý nghĩa trong nghiệp vụ, tránh tạo alias không cần thiết.

## 10. Quy tắc quyền sở hữu và ngăn truy cập chéo parent

Với nested resource, một rủi ro quan trọng là client thay `orderId` trong URI nhưng giữ nguyên `itemId` để cố truy cập dòng hàng của đơn khác. Đây là lỗi kiểm tra quyền sở hữu hoặc kiểm soát truy cập theo đối tượng.

Không nên viết service chỉ truy vấn theo `itemId`:

```java
// Không đủ để xác nhận item thuộc order trong URI.
OrderItem item = repository.findById(itemId).orElseThrow();
```

Nên truy vấn theo cả parent và child:

```java
OrderItem getRequired(UUID orderId, UUID itemId) {
    return repository.findByOrderIdAndId(orderId, itemId)
            .orElseThrow(OrderItemNotFoundException::new);
}
```

Tên method repository là ví dụ theo Spring Data JPA; với reactive repository hoặc persistence khác, áp dụng cùng nguyên tắc phạm vi truy vấn. Nếu không tìm thấy quan hệ phù hợp, API trả phản hồi theo chính sách nhất quán, thường là `404 Not Found` hoặc phản hồi từ chối truy cập phù hợp với yêu cầu bảo mật.

Ngoài việc kiểm tra parent-child, server vẫn phải xác thực người gọi và kiểm tra quyền đối với parent cũng như child. Việc có link `self`, `items` hoặc `delete` trong response không cấp quyền truy cập và cũng không thay thế authorization ở endpoint.

## 11. Các thao tác HTTP trên nested resource

Một collection nested có thể hỗ trợ các thao tác quen thuộc:

| Request | Ý nghĩa thường gặp |
| --- | --- |
| `GET /orders/{orderId}/items` | Liệt kê các dòng hàng của đơn hàng |
| `POST /orders/{orderId}/items` | Thêm một dòng hàng vào đơn hàng |
| `GET /orders/{orderId}/items/{itemId}` | Lấy một dòng hàng trong đơn hàng |
| `PUT /orders/{orderId}/items/{itemId}` | Thay thế representation của dòng hàng nếu API cho phép |
| `PATCH /orders/{orderId}/items/{itemId}` | Cập nhật một phần dòng hàng |
| `DELETE /orders/{orderId}/items/{itemId}` | Xóa dòng hàng khỏi đơn hàng nếu quy tắc nghiệp vụ cho phép |

Khi tạo child bằng `POST` lên collection, response thường trả `201 Created` và `Location` trỏ đến URI của resource mới. Có thể dùng self link do assembler tạo để làm giá trị Location. Nếu API trả representation cùng link, client có thể tiếp tục điều hướng ngay sau khi tạo.

Các thao tác cập nhật và xóa phải kiểm tra child thuộc đúng parent trong URI. Nếu child không được di chuyển giữa các parent, `orderId` trong URI là một phần của ngữ cảnh bắt buộc. Nếu cho phép di chuyển, cần định nghĩa endpoint và semantics riêng để tránh biến thao tác cập nhật thông thường thành thay đổi quyền sở hữu ngoài ý muốn.

## 12. Phân trang collection nested

Collection nested có thể lớn, vì vậy cần hỗ trợ phân trang và lọc giống collection thông thường:

```http
GET /orders/ORD-101/items?page=0&size=20&sort=sku,asc
Accept: application/hal+json
```

Response paged nên giữ parent path cùng các điều kiện truy vấn trong các link `self`, `next` và `prev`. Ví dụ:

```text
/orders/ORD-101/items?page=1&size=20&sort=sku,asc
```

Với Spring Data, có thể dùng `PagedResourcesAssembler` để chuyển `Page<OrderItem>` thành `PagedModel<EntityModel<OrderItemRepresentation>>`. Assembler cho từng item vẫn tạo self link nested có cả `orderId` và `itemId`; page assembler tạo link điều hướng ở cấp collection. Cần kiểm thử để bảo đảm link trang sau không làm mất parent path, filter hoặc sort.

## 13. Kiểm thử nested resource và hypermedia link

Kiểm thử cần xác nhận cả mapping lồng nhau, quan hệ parent-child và link được serialize. Với Spring MVC, có thể dùng `MockMvc`:

```java
mockMvc.perform(get("/orders/{orderId}/items/{itemId}", orderId, itemId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId + "/items/" + itemId)))
    .andExpect(jsonPath("$._links.order.href")
            .value(org.hamcrest.Matchers.endsWith("/orders/" + orderId)));
```

Kiểm thử collection:

```java
mockMvc.perform(get("/orders/{orderId}/items", orderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.order.href").exists())
    .andExpect(jsonPath("$._embedded.items[0]._links.self.href").exists());
```

Các đoạn test giả định ứng dụng đã cấu hình HAL, có dữ liệu và assembler phù hợp. Ngoài các ca thành công, cần kiểm tra:

- `orderId` không tồn tại.
- `itemId` không tồn tại.
- `itemId` tồn tại nhưng thuộc một `orderId` khác.
- Người dùng không có quyền truy cập parent hoặc child.
- Collection rỗng vẫn tạo đúng self link dựa trên `orderId`.
- `POST` tạo child trả `201 Created` và Location đúng.
- Link phân trang giữ parent path, filter và sort.
- Relation `_embedded.items` và relation `order` nhất quán.

## 14. Lỗi thường gặp

**Lồng URI quá sâu:** đường dẫn dài và gắn chặt với cấu trúc quan hệ nội bộ. Chỉ lồng khi parent cung cấp ngữ cảnh có ý nghĩa; dùng link cho các quan hệ khác.

**Nhầm nested URI với embedded resource:** nested mô tả địa chỉ; embedded mô tả dữ liệu được nhúng trong response. Chọn riêng từng quyết định.

**Chỉ kiểm tra child ID:** child có thể thuộc parent khác. Truy vấn và kiểm tra theo cả parent ID lẫn child ID.

**Không có link quay về parent:** client có thể truy cập child nhưng khó khám phá resource cha. Cân nhắc relation `order` hoặc relation phù hợp.

**Lấy parent ID từ phần tử đầu tiên của collection:** collection rỗng không có phần tử để suy ra ngữ cảnh. Truyền parent ID riêng khi dựng collection.

**Coi nested URI luôn là URI canonical:** nếu child có định danh độc lập hoặc có thể chuyển parent, cần xác định địa chỉ ổn định và công bố link phù hợp.

**Để client tự ghép URI:** client nên theo link `items`, `self` và các relation server công bố thay vì hard-code cấu trúc nested path.

## 15. Checklist thiết kế nested resource

- Xác định rõ ý nghĩa và vòng đời của parent-child.
- Chỉ dùng nested URI khi ngữ cảnh parent có giá trị với client hoặc nghiệp vụ.
- Giữ độ sâu URI hợp lý và tránh phản chiếu máy móc cấu trúc database.
- Phân biệt nested URI với HAL `_embedded`.
- Dùng `@RequestMapping` cấp lớp và path variable rõ ràng cho controller nested.
- Tạo link bằng `WebMvcLinkBuilder`/`methodOn` với đầy đủ parent ID và child ID.
- Cung cấp link quay về parent và link đến resource liên quan khi hữu ích.
- Truyền parent ID riêng khi dựng collection để xử lý được collection rỗng.
- Kiểm tra child thuộc parent trong service và kiểm tra quyền truy cập ở endpoint.
- Giữ parent path, filter, sort và page trong link điều hướng.
- Xác định URI canonical nếu child có thể được truy cập hoặc di chuyển độc lập.
- Kiểm thử mapping, relation, URI, collection rỗng và truy cập chéo parent.

Nested resource giúp REST API thể hiện mối quan hệ cha-con bằng URI và hypermedia link có ngữ nghĩa. Khi đường dẫn phản ánh đúng phạm vi nghiệp vụ, assembler tạo liên kết ở đúng cấp và server kiểm tra quan hệ parent-child cho mọi request, client có thể khám phá tài nguyên liên quan mà không phải tự suy luận cấu trúc endpoint.
