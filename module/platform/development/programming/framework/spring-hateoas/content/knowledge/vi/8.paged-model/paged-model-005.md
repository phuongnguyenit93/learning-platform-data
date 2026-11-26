# Link prev và next trong Spring HATEOAS

Khi API trả về một danh sách lớn, dữ liệu thường được chia thành nhiều trang. Client cần biết trang hiện tại, có thể quay lại trang trước hay đi tiếp đến trang sau, và URI nào dùng cho từng bước. Spring HATEOAS biểu diễn các bước đó bằng những liên kết hypermedia, phổ biến nhất là relation `prev` và `next`.

Với API phân trang dựa trên Spring Data, `PagedModel` kết hợp metadata của trang với các liên kết điều hướng. `PagedResourcesAssembler` có thể tạo representation và các link phân trang từ một `Page<T>`, giúp server tránh tự ghép URI trong từng controller. Bài học này giải thích ngữ nghĩa của hai relation, cách Spring tạo link, cách tùy chỉnh khi cần và cách kiểm thử những trường hợp đầu trang, giữa trang và cuối trang.

## 1. Ý nghĩa của prev và next

`prev` là liên kết đến trang ngay trước trang hiện tại; `next` là liên kết đến trang ngay sau trang hiện tại. Đây là các relation hypermedia chuẩn, vì vậy client có thể tìm chúng theo tên quan hệ thay vì tự đoán cấu trúc URL.

Ví dụ API quản lý đơn hàng có 53 đơn, mỗi trang hiển thị 20 đơn. Nếu client đang đọc trang thứ hai theo cách đánh số cho người dùng, server có thể trả các liên kết như sau:

```json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    }
  }
}
```

Spring Data mặc định đánh số trang từ `0`. Do đó `page=1` là trang thứ hai theo cách đếm thông thường. Liên kết `prev` đưa client về `page=0`, còn `next` đưa client đến `page=2`.

Hai relation này có quy tắc xuất hiện rõ ràng:

- Trang đầu tiên không có trang trước, vì vậy không cần công bố `prev`.
- Trang cuối cùng không có trang tiếp theo, vì vậy không cần công bố `next`.
- Trang nằm giữa tập kết quả có cả `prev` và `next`.
- Khi chỉ có một trang, thường chỉ có `self` cùng các relation cấp collection khác; không có `prev` hoặc `next`.

Client nên kiểm tra relation có tồn tại trước khi hiển thị nút điều hướng. Việc này giúp giao diện phản ánh đúng những bước server công bố.

## 2. PagedModel lưu metadata và liên kết trang

`PagedModel<T>` là kiểu representation của Spring HATEOAS dành cho collection có phân trang. Ngoài nội dung các item và liên kết hypermedia, model còn có metadata mô tả trang.

Metadata của `PagedModel` gồm các giá trị chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `size` | Kích thước trang được yêu cầu hoặc sử dụng. |
| `number` | Chỉ số trang hiện tại, mặc định bắt đầu từ `0`. |
| `totalElements` | Tổng số phần tử trong tập kết quả. |
| `totalPages` | Tổng số trang theo kích thước trang và tổng số phần tử. |

Ví dụ tạo một model thủ công:

```java
PagedModel<OrderModel> model = PagedModel.of(
        orderModels,
        new PagedModel.PageMetadata(
                20,  // size
                1,   // number: trang thứ hai
                53,  // totalElements
                3    // totalPages
        )
);
```

Ở ví dụ này, trang hiện tại là `1`, kích thước trang là `20` và tổng cộng có `53` phần tử. Do đó tổng số trang là `3`, với chỉ số `0`, `1`, `2`. `PagedModel` giữ metadata và content; các liên kết `prev` và `next` cần được thêm vào model hoặc được tạo tự động qua assembler.

## 3. Tạo prev và next tự động bằng PagedResourcesAssembler

Trong ứng dụng Spring MVC tích hợp Spring Data, cách thông dụng là dùng `PagedResourcesAssembler`. Thành phần này nhận một `Page<T>` và chuyển nó thành `PagedModel`, đồng thời tạo các liên kết điều hướng dựa trên request phân trang hiện tại.

Giả sử có assembler chuyển `Order` thành `EntityModel<OrderView>`:

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

Controller nhận `Pageable`, lấy một `Page<Order>` từ service rồi chuyển đổi bằng `PagedResourcesAssembler`:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler orderAssembler;

    OrderController(OrderService service, OrderModelAssembler orderAssembler) {
        this.service = service;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    PagedModel<EntityModel<OrderView>> all(
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = service.findAll(pageable);
        return pagedAssembler.toModel(page, orderAssembler);
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return orderAssembler.toModel(service.getRequired(id));
    }
}
```

`PagedResourcesAssembler` tạo `PagedModel` với metadata trang và các liên kết điều hướng phù hợp, thường gồm `first`, `prev`, `self`, `next` và `last` khi những trang tương ứng tồn tại. Client chỉ cần đọc relation `prev` hoặc `next` từ response để đi tiếp.

Trong ví dụ, `service.findAll(pageable)` trả về `Page<Order>`. `orderAssembler` tạo representation cho từng đơn hàng. Các kiểu `Order`, `OrderView`, `OrderService` và mapping là thành phần của ứng dụng minh họa. Dự án cần có tích hợp Spring Data Web để Spring MVC phân giải `Pageable` và cung cấp `PagedResourcesAssembler` phù hợp.

## 4. Ví dụ request và response

Client có thể yêu cầu một trang bằng query parameter:

```http
GET /orders?page=1&size=20 HTTP/1.1
Accept: application/hal+json
```

Với dữ liệu có 53 đơn hàng, response có thể chứa metadata và liên kết như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "21",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "/orders/21"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "/orders?page=0&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    },
    "last": {
      "href": "/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 53,
    "totalPages": 3,
    "number": 1
  }
}
```

Response là ví dụ rút gọn; số item thực tế trong `_embedded.orders` phụ thuộc dữ liệu của trang. Điều cần chú ý là link điều hướng nằm ở cấp collection, còn `self` của mỗi đơn hàng nằm bên trong item. Metadata `page.number` vẫn dùng chỉ số bắt đầu từ `0`.

## 5. Quy tắc xác định khi nào có prev và next

Nếu tự tạo link, điều kiện nên dựa trên metadata của `Page<T>`:

- `page.hasPrevious()` cho biết có trang trước hay không.
- `page.hasNext()` cho biết có trang sau hay không.
- `page.getNumber()` trả về chỉ số trang hiện tại.
- `page.getSize()` trả về số phần tử tối đa trên một trang.

Ví dụ logic điều hướng:

```java
if (page.hasPrevious()) {
    // Tạo link prev đến page.getNumber() - 1.
}

if (page.hasNext()) {
    // Tạo link next đến page.getNumber() + 1.
}
```

Không nên suy luận sự tồn tại của trang trước hoặc trang sau chỉ bằng cách kiểm tra số phần tử trong trang hiện tại. Một trang có thể chứa ít phần tử hơn kích thước tối đa mà vẫn có trang tiếp theo, hoặc là trang cuối có số phần tử không đầy đủ. Metadata của `Page<T>` đã cung cấp các phép kiểm tra đúng theo kết quả truy vấn.

Với `PagedResourcesAssembler`, logic này được xử lý trong quá trình tạo model. Khi dùng cách thủ công, hãy dùng `hasPrevious()` và `hasNext()` để tránh tạo liên kết ngoài phạm vi.

## 6. Tự tạo prev và next khi cần tùy chỉnh

Trong một số ứng dụng, cách tạo link mặc định chưa phù hợp với cấu trúc URL hoặc quy tắc query parameter riêng. Khi đó có thể tạo `PagedModel` thủ công và thêm liên kết bằng `Link`.

Ví dụ dưới đây dùng `ServletUriComponentsBuilder` để lấy URI request hiện tại, sau đó thay đổi giá trị `page`. Cách này giữ lại các query parameter khác như `size`, `sort`, `status` hoặc `customerId` nếu chúng có trong request:

```java
Page<Order> page = service.findAll(pageable);

PagedModel<EntityModel<OrderView>> model = PagedModel.of(
        page.map(orderAssembler::toModel).getContent(),
        new PagedModel.PageMetadata(
                page.getSize(),
                page.getNumber(),
                page.getTotalElements(),
                page.getTotalPages()
        )
);

UriComponentsBuilder current = ServletUriComponentsBuilder.fromCurrentRequest();
model.add(Link.of(current.cloneBuilder().build().encode().toUriString(), "self"));

if (page.hasPrevious()) {
    String previousUri = current.cloneBuilder()
            .replaceQueryParam("page", page.getNumber() - 1)
            .replaceQueryParam("size", page.getSize())
            .build()
            .encode()
            .toUriString();
    model.add(Link.of(previousUri, "prev"));
}

if (page.hasNext()) {
    String nextUri = current.cloneBuilder()
            .replaceQueryParam("page", page.getNumber() + 1)
            .replaceQueryParam("size", page.getSize())
            .build()
            .encode()
            .toUriString();
    model.add(Link.of(nextUri, "next"));
}
```

Đây là ví dụ cho Spring MVC chạy trên Servlet API. `cloneBuilder()` giúp mỗi URI được tạo từ cùng request gốc mà không làm thay đổi builder dùng cho link khác. `replaceQueryParam` cập nhật page và size trong khi giữ các tham số lọc/sắp xếp khác.

Khi áp dụng, hãy lưu ý:

- Tên query parameter `page` và `size` là mặc định phổ biến của Spring Data Web. Nếu ứng dụng cấu hình `PageableHandlerMethodArgumentResolver` với tên khác, link phải dùng đúng tên đã cấu hình.
- Nếu API dùng tham số riêng để chọn tenant, trạng thái hoặc bộ lọc, phải giữ chúng trong link điều hướng để client không mất ngữ cảnh truy vấn.
- Nếu request có nhiều giá trị `sort`, không xóa các giá trị đó khi cập nhật `page`.
- Với WebFlux, cách lấy request URI khác với Servlet MVC; dùng API request phù hợp thay vì `ServletUriComponentsBuilder`.
- Nếu có reverse proxy hoặc context path, cần kiểm tra URI sinh ra là URI client truy cập được.

Khi đã có thể dùng `PagedResourcesAssembler` và cấu hình mặc định đáp ứng hợp đồng, nên ưu tiên assembler để giảm mã tùy chỉnh. Chỉ tự tạo link khi cần kiểm soát cụ thể về URI, tham số hoặc cấu trúc điều hướng.

## 7. Giữ nguyên filter và sort khi chuyển trang

Một lỗi phổ biến là link `next` chỉ chứa `page` và `size`, làm mất các điều kiện lọc hoặc sắp xếp mà người dùng đã chọn.

Ví dụ request ban đầu:

```http
GET /orders?page=1&size=20&status=PENDING&sort=createdAt,desc
```

Link `next` đúng cần giữ `status=PENDING` và `sort=createdAt,desc`, đồng thời đổi `page` thành `2`. Nếu mất filter, client có thể nhận một tập dữ liệu khác khi chuyển trang; nếu mất sort, thứ tự các item có thể thay đổi giữa các request.

Khi sử dụng `PagedResourcesAssembler`, hãy kiểm tra link được tạo trong bối cảnh request thực tế và cấu hình pageable resolver. Khi tự tạo link, dùng builder dựa trên request hiện tại rồi thay đúng tham số phân trang như ví dụ trước. Không tạo URI từ một chuỗi cơ sở mới nếu điều đó làm mất query parameter.

Nếu API cho phép nhiều kiểu lọc, hãy coi toàn bộ query parameter có ảnh hưởng đến kết quả là một phần của ngữ cảnh phân trang. Test nên xác nhận các tham số này tồn tại trong cả link `prev` và `next`.

## 8. Phân trang cần thứ tự ổn định

Liên kết `prev` và `next` chỉ có ý nghĩa nếu các trang được xác định một cách nhất quán. Nếu API phân trang theo offset nhưng sắp xếp bằng một trường không duy nhất, nhiều bản ghi có thể có cùng giá trị sắp xếp. Khi đó, thứ tự giữa các request có thể thay đổi và một item có thể lặp lại hoặc bị bỏ qua giữa các trang.

Nên chỉ định thứ tự sắp xếp ổn định, thường bằng cách thêm một trường duy nhất làm tiêu chí phụ. Ví dụ, sắp xếp theo `createdAt` giảm dần và `id` tăng dần để phân biệt các bản ghi có cùng thời điểm tạo.

Ngoài ra, dữ liệu có thể được thêm hoặc xóa trong khi client đang duyệt nhiều trang. Với offset pagination, các thay đổi đó có thể làm dịch chuyển vị trí bản ghi. `prev` và `next` vẫn đưa client đến trang theo truy vấn mới, nhưng không bảo đảm snapshot dữ liệu bất biến. Với luồng dữ liệu thay đổi liên tục hoặc collection rất lớn, hãy đánh giá cursor/keyset pagination và mô hình điều hướng phù hợp.

## 9. Kiểm thử prev và next

Kiểm thử cần bao phủ ít nhất ba tình huống: trang đầu, trang giữa và trang cuối. Giả sử mỗi trang có 20 phần tử và tổng cộng có 53 phần tử:

| Trang hiện tại (0-based) | Trang theo cách đếm thông thường | prev | next |
| --- | --- | --- | --- |
| `0` | Trang 1 | Không | Có, đến `1` |
| `1` | Trang 2 | Có, đến `0` | Có, đến `2` |
| `2` | Trang 3 | Có, đến `1` | Không |

Với MockMvc, có thể kiểm tra relation và URI từ response HAL:

```java
mockMvc.perform(get("/orders")
        .param("page", "1")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev.href", containsString("page=0")))
    .andExpect(jsonPath("$._links.next.href", containsString("page=2")));
```

Trang đầu phải không có `prev`:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev").doesNotExist())
    .andExpect(jsonPath("$._links.next.href").exists());
```

Trang cuối phải không có `next`:

```java
mockMvc.perform(get("/orders")
        .param("page", "2")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.next").doesNotExist());
```

Các matcher `containsString` ở đây giúp minh họa việc kiểm tra chỉ số trang trong `href`. Trong bộ test thực tế, nên phân tích URI và kiểm tra từng query parameter để tránh phụ thuộc thứ tự tham số hoặc cách encode.

## 10. Những trường hợp biên cần kiểm tra

Ngoài ba vị trí trang cơ bản, hãy kiểm tra các trường hợp sau:

- **Chỉ có một trang:** không có `prev` và `next`.
- **Collection rỗng:** response vẫn theo hợp đồng; không tạo link `next` tới một trang không tồn tại.
- **Trang cuối chưa đầy:** vẫn không có `next`, dù số item ít hơn `size`.
- **Tham số size khác mặc định:** link điều hướng giữ đúng kích thước trang hiện tại hoặc theo chính sách API.
- **Có filter và sort:** link giữ ngữ cảnh truy vấn.
- **Trang được yêu cầu vượt quá tổng số trang:** xác định API trả trang rỗng, lỗi hay điều chỉnh trang; link phải phản ánh đúng chính sách đó.
- **Tham số page không hợp lệ hoặc âm:** xác định cách resolver xử lý và kiểm thử kết quả.
- **Thay đổi dữ liệu giữa hai request:** xác định cách API phản hồi khi tổng số trang thay đổi trong lúc client điều hướng.

Đừng suy ra link `next` chỉ bằng việc trang hiện tại có đủ `size` item. `Page.hasNext()` dựa trên metadata của truy vấn và là tín hiệu phù hợp khi dùng Spring Data `Page`.

## 11. Cách client sử dụng prev và next

Client không cần tự tăng hoặc giảm số trang để xây URI. Nó đọc relation từ response:

1. Tìm liên kết `self` để biết trang hiện tại.
2. Nếu có `prev`, dùng `href` của liên kết đó để quay lại.
3. Nếu có `next`, dùng `href` của liên kết đó để đi tiếp.
4. Nếu không có relation tương ứng, ẩn hoặc vô hiệu hóa điều khiển điều hướng.

Client không cần giả định endpoint dùng query parameter tên `page`, `size` hay cấu trúc URL cụ thể. Server có thể thay đổi cách định tuyến miễn là các relation và hợp đồng biểu diễn được giữ ổn định.

Với client tổng quát, nên dùng thư viện đọc hypermedia hoặc parser theo media type thay vì phụ thuộc trực tiếp vào đường dẫn JSON cố định. Điều đó giúp client tìm relation `next` trong response HAL theo đúng quy ước.

## 12. Bài tập thực hành và tiêu chí hoàn thành

Hãy hoàn thiện endpoint danh sách đơn hàng có phân trang:

1. Nhận `Pageable` từ request và gọi service để lấy `Page<Order>`.
2. Dùng `PagedResourcesAssembler` để chuyển page thành `PagedModel`.
3. Xác nhận response trang giữa có cả `prev` và `next`.
4. Xác nhận trang đầu không có `prev` và trang cuối không có `next`.
5. Gửi request kèm filter và sort, sau đó kiểm tra các tham số đó được giữ trong link điều hướng.
6. Kiểm tra collection rỗng, trang chỉ có một trang và trang được yêu cầu vượt quá phạm vi.
7. Tạo client mẫu đọc `href` từ relation `next` rồi gọi URI đó.
8. Đổi mapping hoặc cấu trúc query parameter trong môi trường thử nghiệm và xác nhận client vẫn điều hướng được khi relation được giữ ổn định.

Bạn đã nắm vững `prev` và `next` khi có thể giải thích quy tắc xuất hiện của chúng, hiểu cách `PagedResourcesAssembler` tạo link từ `Page<T>`, tự tùy chỉnh URI khi cần, giữ filter/sort qua các trang và kiểm thử đúng các ranh giới đầu trang/cuối trang. Những nguyên tắc này giúp client duyệt collection theo hypermedia mà không phụ thuộc vào cách server đánh số hay xây dựng URL nội bộ.
