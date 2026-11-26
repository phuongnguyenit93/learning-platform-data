# Trùng self link trong Spring HATEOAS

Một representation của tài nguyên thường chỉ cần một liên kết `self` để chỉ tới URI chính thức của chính tài nguyên đó. Tuy nhiên, khi ứng dụng có nhiều lớp cùng tham gia tạo representation, cùng một item có thể nhận self link nhiều lần. Ví dụ assembler đã thêm `self`, sau đó controller hoặc một helper lại thêm một link `self` nữa. Kết quả là response có thể chứa nhiều link cùng relation, khiến client khó xác định URI nào là địa chỉ chính.

Bài học này giải thích cách trùng self link phát sinh, vì sao nó khác với self link ở cấp collection, cách tổ chức trách nhiệm tạo link và cách phát hiện trùng bằng kiểm thử. Mục tiêu là mỗi item công bố một self link nhất quán, trỏ đúng endpoint đọc tài nguyên.

## 1. Trùng self link là gì?

Trùng self link xảy ra khi một representation chứa từ hai liên kết trở lên cùng relation `self`. Các liên kết có thể có cùng `href` hoặc có URI khác nhau.

Ví dụ hai link cùng trỏ tới một URI:

```json
{
  "_links": {
    "self": [
      { "href": "/orders/42" },
      { "href": "/orders/42" }
    ]
  }
}
```

Hoặc hai link cùng relation nhưng trỏ tới hai URI khác nhau:

```json
{
  "_links": {
    "self": [
      { "href": "/orders/42" },
      { "href": "/api/orders/42" }
    ]
  }
}
```

HAL cho phép một relation có nhiều link và biểu diễn chúng dưới dạng mảng. Vì vậy, việc có nhiều link cùng relation không phải lúc nào cũng sai. Chẳng hạn, nhiều link `alternate` có thể trỏ tới các phiên bản ngôn ngữ khác nhau. Nhưng với self link của một representation, nhiều URI chính thường là dấu hiệu thiết kế không rõ ràng: client không biết đâu là URI chuẩn để đọc chính tài nguyên.

## 2. Phân biệt self link trùng với self link ở hai cấp

Một response collection có thể có một self link ở cấp collection và một self link riêng trên từng item. Đây là các link thuộc những representation khác nhau, nên không phải trường hợp trùng.

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "_links": {
          "self": { "href": "/orders/42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
```

Trong ví dụ, self link bên ngoài xác định collection `/orders`; self link bên trong xác định item `/orders/42`. Mỗi representation có đúng một self link của riêng nó. Vấn đề chỉ xuất hiện khi cùng một model item bị thêm relation `self` nhiều lần.

## 3. Nguyên nhân phổ biến: assembler và controller cùng thêm self

Một nguyên nhân thường gặp là assembler đã tạo self link cho từng item, nhưng controller lại tiếp tục thêm link cho các item sau khi chuyển collection.

Assembler đã có self link:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).one(order.getId())).withSelfRel()
        );
    }
}
```

Nếu controller gọi `toCollectionModel(...)` rồi lặp lại trên từng item để thêm `self`, cùng item sẽ nhận hai link cùng relation:

```java
CollectionModel<EntityModel<OrderView>> result =
        orderAssembler.toCollectionModel(orderService.findAll());

// Không thêm lại self cho từng item nếu assembler đã sở hữu việc này.
result.getContent().forEach(item ->
        item.add(linkTo(methodOn(OrderController.class)
                .one(item.getContent().id())).withSelfRel())
);
```

Controller chỉ cần thêm self link của collection:

```java
CollectionModel<EntityModel<OrderView>> result =
        orderAssembler.toCollectionModel(orderService.findAll());

result.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
return result;
```

Ở đây, assembler chịu trách nhiệm link của item; controller chịu trách nhiệm link của collection. Phân định này ngăn hai lớp cùng sửa cùng một relation trên cùng một model.

## 4. Các nguồn khác có thể tạo self link trùng

Ngoài trường hợp assembler và controller, trùng self link có thể xuất phát từ:

- **Lớp model cơ sở và model chuyên biệt:** lớp cha thêm `self`, sau đó subclass hoặc assembler chuyên biệt thêm lại.
- **Helper dùng chung và assembler:** một helper tự động bổ sung `self`, nhưng assembler cũng đã tạo link.
- **Decorator hoặc response enricher:** một bước hậu xử lý thêm các liên kết vào model đã hoàn chỉnh mà không kiểm tra relation hiện có.
- **Mapper và controller:** mapper chuyển DTO thành model có link, controller lại tự dựng link từ cùng mapping.
- **Ghép nhiều nguồn link:** model nhận link từ một service và từ một thành phần tích hợp khác; cả hai cùng dùng relation `self`.
- **Tạo link theo hai URI alias:** một lớp dùng đường dẫn cũ, lớp khác dùng đường dẫn mới nhưng đều đặt relation `self`.

Khi truy tìm lỗi, hãy lần theo toàn bộ luồng tạo model: mapper, assembler, lớp cơ sở, controller và các bước bổ sung liên kết trước serialization. Chỉ kiểm tra controller có thể bỏ sót nơi thêm link đầu tiên.

## 5. Vì sao không nên dựa vào add để tự loại trùng?

`RepresentationModel.add(...)` được dùng để thêm link vào model. Hãy xem đây là thao tác bổ sung link, không phải một chính sách đảm bảo chỉ tồn tại một link cho mỗi relation. Nếu nhiều lớp cùng gọi `add` với relation `self`, model có thể giữ nhiều link cùng relation.

Các phương thức `hasLink("self")` hoặc `getLink("self")` hữu ích để kiểm tra sự hiện diện, nhưng chỉ biết có ít nhất một link. Chúng không chứng minh rằng model chỉ có đúng một self link. Vì vậy, test chỉ kiểm tra `hasLink("self")` có thể vẫn xanh dù response chứa mảng `self` bị trùng.

Khi một relation được phép có nhiều link, chẳng hạn `alternate`, việc giữ nhiều link là có chủ đích. Khi relation `self` được thiết kế là URI chính duy nhất của item, cần kiểm tra số lượng và giá trị `href` thay vì chỉ kiểm tra relation tồn tại.

## 6. Quy tắc thiết kế: chỉ một nơi sở hữu self link của item

Cách xử lý bền vững là chọn một thành phần duy nhất chịu trách nhiệm tạo self link cho item. Với ứng dụng dùng `RepresentationModelAssembler`, thường nên để `toModel(...)` tạo self link. `toCollectionModel(...)` sẽ dùng kết quả `toModel(...)` cho từng phần tử; controller chỉ bổ sung liên kết ở cấp collection hoặc các relation khác thực sự thuộc collection.

Ví dụ phân chia trách nhiệm:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(view,
                linkTo(methodOn(OrderController.class).one(order.getId()))
                        .withSelfRel());
    }
}
```

Controller:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all() {
    CollectionModel<EntityModel<OrderView>> model =
            orderAssembler.toCollectionModel(orderService.findAll());

    model.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    return model;
}
```

Mỗi item nhận self link từ assembler. Collection nhận self link riêng từ controller. Không có bước nào lặp lại việc thêm `self` vào item.

Nếu dự án chọn controller hoặc một response enricher làm nơi sở hữu self link, hãy áp dụng quy tắc đó nhất quán và bỏ phần tạo link tương ứng ở assembler. Điều quan trọng là mỗi model item chỉ có một nguồn tạo self link.

## 7. Khi cần thay thế self link đã có

Đôi khi một model được tạo từ thành phần dùng chung với self link mặc định, nhưng một lớp chuyên biệt cần thay thế bằng URI chuẩn của API hiện tại. Trong trường hợp này, việc thêm link mới mà không xử lý link cũ sẽ tạo ra nhiều relation `self`.

`RepresentationModel` có phương thức loại bỏ link theo relation. Nếu thành phần hiện tại được giao quyền xác định self link chuẩn, có thể loại bỏ relation cũ rồi thêm link mới:

```java
Link canonicalSelf = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();

model.removeLinks(IanaLinkRelations.SELF);
model.add(canonicalSelf);
```

Đoạn mã trên đảm bảo model còn self link do thành phần này tạo ra. Chỉ dùng cách này khi lớp đang xử lý thực sự có trách nhiệm xác định URI chính thức. Không nên xóa self link tùy tiện nếu model có thể chứa một URI chuẩn được cung cấp từ nguồn đáng tin cậy khác.

Một cách kiểm tra đơn giản trước khi thêm là:

```java
if (!model.hasLink(IanaLinkRelations.SELF)) {
    model.add(canonicalSelf);
}
```

Điều kiện này ngăn thêm link khi đã có self, nhưng không sửa được trường hợp link hiện có sai URI hoặc có nhiều self link từ trước. Nếu cần bảo đảm canonical URI, hãy kiểm tra `href` hiện tại và thay thế theo một chính sách rõ ràng. Tránh dùng `removeLinks()` không tham số nếu chỉ muốn thay self link, vì thao tác đó xóa tất cả relation của model.

## 8. Self link khác nhau về URI: chọn URI chuẩn

Trường hợp khó hơn là hai self link cùng relation nhưng khác URI. Ví dụ một link trỏ tới `/orders/42`, link còn lại trỏ tới `/api/orders/42`. Cả hai có thể truy cập được do alias hoặc mapping cũ, nhưng client không biết URI nào là định danh chuẩn mà API muốn duy trì.

Hãy xác định một URI canonical theo hợp đồng API. Nếu endpoint cũ vẫn cần được hỗ trợ, có thể công bố nó bằng relation phù hợp như `alternate` hoặc duy trì redirect HTTP theo chính sách tương thích. Không nên gắn cả URI cũ và mới cùng relation `self` nếu API muốn chỉ ra một URI chính duy nhất.

Self link phải trỏ tới representation của chính tài nguyên. Một link tới endpoint thao tác như `/orders/42/cancel` không nên được đặt relation `self`; hãy dùng relation nghiệp vụ `cancel`. Tương tự, link đến collection `/orders` không phải self link của item `/orders/42`.

## 9. Kiểm tra số lượng self link trong unit test

Test chỉ dùng `hasLink("self")` không phát hiện được duplicate. Hãy đếm số link có relation `self` và xác nhận chỉ có một:

```java
@Test
void itemHasExactlyOneSelfLink() {
    EntityModel<OrderView> model = orderAssembler.toModel(order);

    long selfCount = model.getLinks().stream()
            .filter(link -> link.getRel().equals(IanaLinkRelations.SELF))
            .count();

    assertThat(selfCount).isEqualTo(1);
    assertThat(model.getRequiredLink(IanaLinkRelations.SELF).getHref())
            .endsWith("/orders/" + order.getId());
}
```

Nếu assembler dùng `WebMvcLinkBuilder`, test cần request context phù hợp để tạo URI. Có thể dùng test web để xác nhận `href` đầy đủ và dùng unit test để xác nhận assembler không tạo nhiều relation `self`.

Khi test collection, kiểm tra từng item riêng biệt:

```java
for (EntityModel<OrderView> item : collection.getContent()) {
    long selfCount = item.getLinks().stream()
            .filter(link -> link.getRel().equals(IanaLinkRelations.SELF))
            .count();

    assertThat(selfCount).isEqualTo(1);
}
```

Đồng thời kiểm tra self link cấp collection ở model ngoài cùng. Không cộng tất cả link `self` trong response thành một số duy nhất, vì collection và từng item là các representation khác nhau và mỗi representation có self link riêng.

## 10. Kiểm tra HAL serialization để phát hiện mảng self

Nếu có nhiều link cùng relation, HAL có thể serialize relation đó thành mảng. Do đó, kiểm thử HTTP cần xác nhận `_links.self` của item là một link object duy nhất, không phải mảng nhiều phần tử.

Ví dụ với MockMvc, có thể parse response thành `JsonNode`:

```java
MvcResult result = mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

JsonNode root = objectMapper.readTree(result.getResponse().getContentAsString());
JsonNode self = root.path("_links").path("self");

assertThat(self.isObject()).isTrue();
assertThat(self.path("href").asText()).endsWith("/orders/" + orderId);
```

Với item trong collection, lấy từng node trong `_embedded.orders` rồi xác nhận `_links.self` là object và có đúng `href`. Tên relation `orders` phải khớp cấu hình `@Relation` hoặc relation provider của ứng dụng.

Kiểm thử serialization giúp phát hiện vấn đề mà unit test có thể bỏ qua: model trong bộ nhớ có link, nhưng khi nhiều link cùng relation được tuần tự hóa, client nhìn thấy một mảng ngoài dự kiến.

## 11. Những nguyên tắc tránh trùng self link

- **Chỉ định một chủ sở hữu:** chọn assembler, mapper hoặc controller làm nơi tạo self link của item.
- **Phân biệt phạm vi:** controller có thể tạo self link cho collection mà không cần thêm lại self cho từng item.
- **Không dùng helper mù:** helper bổ sung link cần biết model đã có self hay chưa và ai chịu trách nhiệm về URI canonical.
- **Không dùng `hasLink` làm bằng chứng duy nhất:** kiểm tra số lượng link và `href`.
- **Không trộn URI canonical với alias:** chọn một self link chính; dùng relation khác hoặc redirect cho URI thay thế khi phù hợp.
- **Kiểm thử cả model và HAL:** xác nhận số lượng trong bộ nhớ và cấu trúc serialization.
- **Giữ relation hành động riêng:** `cancel`, `approve` hoặc `pay` không được dùng thay cho `self`.

## 12. Bài tập thực hành và tiêu chí hoàn thành

Hãy tạo một collection đơn hàng và chủ động mô phỏng lỗi duplicate self link:

1. Viết `OrderModelAssembler` thêm self link cho từng `EntityModel<OrderView>`.
2. Trong controller, thêm self link cấp collection.
3. Tạo một phiên bản lỗi trong test bằng cách thêm lại self link vào từng item.
4. Xác nhận `hasLink("self")` vẫn trả về true dù item có nhiều link cùng relation.
5. Đếm số link `self` và xác nhận test phát hiện trường hợp có hơn một link.
6. Xóa bước thêm self link lặp lại ở controller hoặc helper.
7. Nếu cần thay URI chuẩn, dùng chính sách loại bỏ relation cũ rồi thêm link canonical đúng nơi sở hữu.
8. Kiểm tra HAL JSON cho thấy mỗi item có một object `_links.self` với `href` đúng.
9. Kiểm tra self link collection vẫn trỏ tới danh sách và không bị xóa khi thay self link của item.

Bạn đã xử lý tốt trùng self link khi xác định được nơi tạo link đầu tiên, phân biệt self link của item với collection, giữ một URI canonical cho mỗi item, kiểm thử số lượng relation và xác nhận response HAL không chứa mảng `self` ngoài ý muốn. Điều này giúp client luôn tìm được địa chỉ chính của tài nguyên một cách nhất quán.
