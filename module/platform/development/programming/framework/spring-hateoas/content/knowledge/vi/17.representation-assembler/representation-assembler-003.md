# Phương thức toCollectionModel trong Spring HATEOAS

Khi một endpoint trả về nhiều tài nguyên, Spring HATEOAS cần chuyển từng phần tử thành representation model và gom chúng vào một representation ở cấp collection. `RepresentationModelAssembler` cung cấp phương thức `toCollectionModel(...)` để thực hiện phần chuyển đổi này. Phương thức sử dụng `toModel(...)` cho từng phần tử, sau đó tạo `CollectionModel` chứa các model đã chuyển đổi.

`toCollectionModel` giúp giữ cách biểu diễn item nhất quán giữa endpoint chi tiết và endpoint danh sách. Nếu `toModel` đã thêm self link và các relation nghiệp vụ cho từng item, collection được tạo ra sẽ mang các link đó theo từng phần tử. Tuy nhiên, link của chính collection như `self`, `next` hoặc `prev` vẫn cần được bổ sung theo hợp đồng API. Bài học này tập trung vào cách dùng phương thức, cách tổ chức assembler và những điều cần kiểm thử.

## 1. Vai trò của toCollectionModel

Một assembler thường chịu trách nhiệm chuyển domain object thành representation model. Với một tài nguyên đơn lẻ, phương thức `toModel(T entity)` tạo một model. Với nhiều tài nguyên, `toCollectionModel(Iterable<? extends T> entities)` chuyển toàn bộ phần tử thành các model rồi trả về một `CollectionModel<D>`.

| Phương thức | Đầu vào | Kết quả | Mục đích |
| --- | --- | --- | --- |
| `toModel(entity)` | Một domain object | Một representation model | Chuyển đổi một item và tạo link của item. |
| `toCollectionModel(entities)` | Một `Iterable` domain object | `CollectionModel` chứa nhiều representation model | Chuyển đổi một tập hợp item theo cùng quy tắc. |

Ví dụ với API đơn hàng:

- `toModel(order)` tạo `EntityModel<OrderView>` cho một đơn hàng.
- `toCollectionModel(orders)` gọi quy tắc chuyển đổi item cho các đơn hàng trong tập hợp và trả `CollectionModel<EntityModel<OrderView>>`.

Điểm quan trọng là collection model chứa các representation đã được tạo. Nó không thay thế logic chuyển đổi của từng item và cũng không tự quyết định các quy tắc nghiệp vụ như đơn nào có thể hủy.

## 2. Hiểu kiểu generic của RepresentationModelAssembler

Interface `RepresentationModelAssembler<T, D>` có hai tham số kiểu chính:

- `T` là kiểu dữ liệu đầu vào, thường là domain object hoặc entity được service trả về.
- `D` là kiểu representation model đầu ra, chẳng hạn `EntityModel<OrderView>` hoặc một class kế thừa `RepresentationModel`.

Ví dụ khai báo assembler:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        // Chuyển một Order thành EntityModel<OrderView>.
    }
}
```

Với khai báo này, `toCollectionModel(...)` nhận một tập hợp `Order` và tạo `CollectionModel<EntityModel<OrderView>>`. Kiểu generic cho biết rõ mỗi phần tử trong collection là representation nào.

Nếu ứng dụng dùng `OrderModel extends RepresentationModel<OrderModel>`, assembler có thể khai báo `RepresentationModelAssembler<Order, OrderModel>`. Khi đó kết quả collection là `CollectionModel<OrderModel>`. Hãy giữ kiểu đầu ra nhất quán với model thực tế mà `toModel` trả về.

## 3. Xây dựng toModel trước khi dùng toCollectionModel

`toCollectionModel` dựa trên phương thức chuyển đổi một phần tử. Vì vậy, hãy hoàn thiện `toModel` trước: xác định dữ liệu công khai, tạo model và thêm link cho item.

Giả sử API có DTO:

```java
public record OrderView(UUID id, String status, BigDecimal total) {}
```

Assembler có thể chuyển `Order` thành `EntityModel<OrderView>` như sau:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        UUID id = order.getId();
        OrderView view = new OrderView(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        return EntityModel.of(
                view,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Mỗi item được tạo có dữ liệu của đơn hàng và self link tới GET endpoint chi tiết. Có thể thêm các relation khác như `customer` hoặc `cancel` nếu hợp đồng API cần và điều kiện nghiệp vụ cho phép.

Khi `toModel` được gọi riêng cho endpoint chi tiết hoặc được dùng trong `toCollectionModel`, cùng một quy tắc biểu diễn sẽ được áp dụng. Điều này tránh việc endpoint chi tiết và endpoint danh sách tạo hai kiểu item khác nhau.

## 4. Gọi toCollectionModel trong controller

Khi service trả về một `List<Order>` hoặc một kiểu `Iterable<Order>`, controller có thể truyền trực tiếp kết quả cho assembler:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        CollectionModel<EntityModel<OrderView>> collection =
                assembler.toCollectionModel(orderService.findAll());

        collection.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
        return collection;
    }
}
```

Trong ví dụ:

1. `orderService.findAll()` tải tập hợp domain object.
2. `toCollectionModel(...)` chuyển từng `Order` bằng `toModel(...)`.
3. Mỗi item có self link riêng do assembler tạo.
4. Controller bổ sung self link ở cấp collection.
5. Controller trả `CollectionModel` để Spring HATEOAS tuần tự hóa theo media type đã cấu hình.

Link cấp collection cần được tạo riêng vì `toModel` chỉ biết một item. Assembler không thể tự suy ra URI của collection từ URI của từng item trong mọi API.

## 5. Điều gì xảy ra bên trong toCollectionModel?

Về mặt sử dụng, có thể hiểu `toCollectionModel` thực hiện ba bước:

1. Nhận một `Iterable` các đối tượng đầu vào.
2. Gọi `toModel` cho từng phần tử để tạo representation model.
3. Gom các model đó vào `CollectionModel` và trả kết quả.

Có thể hình dung luồng chuyển đổi:

```mermaid
flowchart TD
    A[Iterable<Order>] --> B[toCollectionModel]
    B --> C[toModel(order 1)]
    B --> D[toModel(order 2)]
    B --> E[toModel(order n)]
    C --> F[CollectionModel]
    D --> F
    E --> F
    F --> G[Thêm link cấp collection]
    G --> H[HAL representation]
```

Điều này có nghĩa là các quy tắc trong `toModel` được áp dụng cho từng phần tử. Nếu `toModel` thêm self link, mọi item trong collection sẽ nhận self link. Nếu `toModel` thêm link `customer`, mỗi item có thể trỏ tới khách hàng tương ứng.

Phương thức không tự thêm link `self` của collection, không tự tạo link phân trang và không tự thêm relation nghiệp vụ cấp danh sách. Những liên kết đó cần được bổ sung tại nơi có đủ thông tin về collection và request.

## 6. Thêm link ở cấp collection sau khi chuyển đổi

Sau khi gọi `toCollectionModel`, kết quả là một `CollectionModel` có thể nhận thêm các link cấp collection bằng `add(...)`:

```java
CollectionModel<EntityModel<OrderView>> collection =
        assembler.toCollectionModel(orders);

collection.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Link `self` trỏ tới collection. Nếu API có endpoint tìm kiếm, có thể bổ sung relation `search` bằng cách tham chiếu đúng method và mapping của endpoint đó. Nếu query parameter có giá trị cụ thể, hãy truyền giá trị đó để tạo URI cụ thể; nếu client cần tự chọn giá trị, cân nhắc URI template.

Không thêm self link của item lần nữa sau khi `toCollectionModel` đã gọi `toModel`. Nếu assembler đã tạo self link cho từng item, controller chỉ nên bổ sung link ở cấp collection. Quy tắc này giúp tránh duplicate self relation.

## 7. CollectionModel và relation của phần tử nhúng

Khi collection được tuần tự hóa thành HAL, các item thường được đặt trong `_embedded`; các link cấp collection nằm trong `_links` ở ngoài cùng.

Ví dụ response rút gọn:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "42",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      },
      {
        "id": "43",
        "status": "SHIPPED",
        "total": 98000,
        "_links": {
          "self": {
            "href": "/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
```

Relation `orders` trong `_embedded` là tên collection relation mà relation provider của Spring HATEOAS xác định. Nếu cần tên cụ thể, cấu hình relation cho model bằng `@Relation` hoặc cơ chế relation provider tương ứng và kiểm tra response thực tế.

Client cần phân biệt link cấp collection với link trong từng item. Không dùng URI `/orders` để thay cho self link của item `/orders/42`; cũng không giả định mỗi item có cùng một `href`.

## 8. Xử lý collection rỗng

Service có thể trả về một tập hợp rỗng. `toCollectionModel` vẫn tạo collection model với content không có phần tử. Controller vẫn có thể thêm self link của collection:

```java
CollectionModel<EntityModel<OrderView>> collection =
        assembler.toCollectionModel(List.<Order>of());

collection.add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
return collection;
```

Collection rỗng là kết quả hợp lệ, chẳng hạn người dùng chưa tạo đơn hàng nào hoặc bộ lọc không tìm thấy kết quả. Client nên xử lý trường hợp không có item và không phụ thuộc vào việc `_embedded` luôn xuất hiện.

Khi HAL không có phần tử để suy luận relation của embedded collection, cấu trúc `_embedded` hoặc tên relation có thể không xuất hiện như trường hợp collection có dữ liệu. Nếu hợp đồng yêu cầu một relation ổn định cả khi rỗng, hãy cấu hình fallback type hoặc relation phù hợp với phiên bản Spring HATEOAS đang dùng và viết kiểm thử cho response rỗng.

## 9. Giữ ranh giới giữa collection và phân trang

`toCollectionModel` chuyển đổi một tập hợp thành `CollectionModel`. Phương thức không tự tạo metadata phân trang như số trang hiện tại, kích thước trang, tổng số phần tử hay tổng số trang. Nó cũng không tự quyết định `prev` và `next`.

Nếu service trả về `Page<Order>`, có thể dùng `PagedResourcesAssembler` để tạo `PagedModel`:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

`PagedResourcesAssembler` dùng `Page` cùng `RepresentationModelAssembler` để tạo representation có metadata và link điều hướng trang. Không nên chỉ lấy `page.getContent()` rồi gọi `toCollectionModel` nếu client cần biết metadata phân trang; cách đó chỉ giữ các item của trang hiện tại và làm mất thông tin trang nếu không bổ sung riêng.

## 10. Khác biệt với reactive assembler

`RepresentationModelAssembler.toCollectionModel(...)` nhận một `Iterable` và trả về `CollectionModel` đồng bộ. Phương thức này phù hợp với luồng Spring MVC hoặc dữ liệu đã có sẵn dưới dạng collection đồng bộ.

Trong Spring WebFlux, dữ liệu thường là `Flux<T>`. Spring HATEOAS cung cấp `ReactiveRepresentationModelAssembler` với phương thức `toCollectionModel(Flux<? extends T>, ServerWebExchange)` trả về `Mono<CollectionModel<D>>`. Đây là API riêng cho luồng reactive.

Không truyền trực tiếp `Flux<T>` vào `RepresentationModelAssembler.toCollectionModel(...)` và cũng không gọi `.block()` để biến `Mono<CollectionModel<D>>` thành kết quả đồng bộ trong WebFlux. Hãy dùng reactive assembler và kết hợp publisher trong pipeline.

## 11. Kiểm thử toCollectionModel

Nên kiểm thử cả số lượng phần tử, dữ liệu sau chuyển đổi và link trên từng item. Ví dụ với JUnit và AssertJ:

```java
@Test
void convertsEveryOrderToAnEntityModel() {
    List<Order> orders = List.of(firstOrder, secondOrder);

    CollectionModel<EntityModel<OrderView>> result =
            assembler.toCollectionModel(orders);

    assertThat(result.getContent()).hasSize(2);
    assertThat(result.getContent())
            .extracting(item -> item.getContent().id())
            .containsExactly(firstOrder.getId(), secondOrder.getId());

    assertThat(result.getContent()).allSatisfy(item ->
            assertThat(item.hasLink(IanaLinkRelations.SELF)).isTrue()
    );
}
```

Ví dụ giả định `OrderView` là record có accessor `id()` và assembler tạo self link. Nếu DTO là class thông thường, dùng getter tương ứng. Khi kiểm tra URI, xác nhận mỗi item có `href` đúng ID của nó.

Kiểm thử collection rỗng:

```java
@Test
void createsAnEmptyCollectionModel() {
    CollectionModel<EntityModel<OrderView>> result =
            assembler.toCollectionModel(List.<Order>of());

    assertThat(result.getContent()).isEmpty();
}
```

Ngoài unit test, kiểm thử HTTP bằng MockMvc để xác nhận HAL serialization:

```java
mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Tên `orders` cần khớp relation được cấu hình trong ứng dụng. Hãy có test cho collection rỗng, một item và nhiều item. Nếu API có phân trang, kiểm thử `PagedResourcesAssembler` riêng cho trang đầu, trang giữa và trang cuối.

## 12. Các lỗi thường gặp

**Nghĩ rằng toCollectionModel tự tạo self link của collection.** Phương thức chuyển đổi item và gom chúng vào collection; link cấp collection cần được thêm riêng.

**Không định nghĩa toModel đầy đủ.** Nếu `toModel` thiếu self link hoặc trường dữ liệu, mọi item được chuyển qua `toCollectionModel` đều thiếu cùng phần đó.

**Thêm self link item hai lần.** Assembler đã tạo self link cho từng item; controller không nên lặp qua content để thêm lại relation này.

**Dùng toCollectionModel cho phân trang mà bỏ metadata.** `CollectionModel` không phải `PagedModel`. Dùng `PagedResourcesAssembler` khi cần metadata và link trang.

**Truyền Flux vào assembler đồng bộ.** `toCollectionModel` của `RepresentationModelAssembler` nhận `Iterable`; với WebFlux, dùng `ReactiveRepresentationModelAssembler`.

**Bỏ qua collection rỗng.** Test chỉ có dữ liệu có thể bỏ sót lỗi relation hoặc cấu trúc HAL khi không có item.

**Để assembler truy vấn database cho từng item.** Assembler nên chuyển đổi dữ liệu đã được service tải. Tránh tạo N+1 query do truy cập quan hệ lazy trong `toModel`.

## 13. Bài tập thực hành và tiêu chí hoàn thành

Hãy hoàn thiện endpoint `GET /orders` bằng `toCollectionModel`:

1. Tạo `OrderView` chứa các trường API cần công bố.
2. Viết `OrderModelAssembler implements RepresentationModelAssembler<Order, EntityModel<OrderView>>`.
3. Trong `toModel`, tạo DTO và self link cho từng đơn hàng.
4. Gọi `toCollectionModel(orderService.findAll())` trong controller.
5. Bổ sung self link cấp collection sau khi chuyển đổi.
6. Xác nhận mỗi item có một self link riêng và không bị trùng.
7. Kiểm tra response HAL có relation collection và các item trong `_embedded`.
8. Kiểm tra collection rỗng và xác định relation cần công bố khi không có item.
9. Nếu service trả `Page<Order>`, dùng `PagedResourcesAssembler` và kiểm tra metadata trang.
10. Nếu ứng dụng dùng WebFlux, thử chuyển đổi tương tự bằng `ReactiveRepresentationModelAssembler`.

Bạn đã nắm được `toCollectionModel` khi có thể giải thích cách phương thức dùng `toModel` cho từng phần tử, tạo collection model từ `Iterable`, phân biệt link của item và collection, xử lý collection rỗng và chọn đúng API cho phân trang hoặc reactive stream. Đây là cơ sở để các endpoint danh sách áp dụng cùng một hợp đồng hypermedia cho mọi item.
