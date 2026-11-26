# Resource identifier — định danh tài nguyên

Trong REST, tài nguyên được nhận diện bằng một định danh, thường là URI (Uniform Resource Identifier). Client dùng URI để tham chiếu đến tài nguyên mà nó muốn đọc hoặc tương tác. Ví dụ, `/orders/42` có thể là URI của một đơn hàng; `/orders` có thể là URI của tập hợp đơn hàng.

Định danh tài nguyên là nền tảng của kiến trúc REST và của hypermedia. Khi URI được thiết kế rõ ràng, server có thể cung cấp các biểu diễn khác nhau của cùng tài nguyên, còn client có thể theo liên kết do server trả về để khám phá tài nguyên liên quan. Spring HATEOAS hỗ trợ tạo những liên kết này dựa trên mapping của controller, giúp URI không bị lặp lại thành chuỗi rời rạc trong mã ứng dụng.

Sau bài học, bạn có thể:

- Phân biệt tài nguyên, định danh tài nguyên, biểu diễn và khóa dữ liệu nội bộ.
- Thiết kế URI dễ hiểu, ổn định và phản ánh đúng tài nguyên.
- Chọn định danh tự nhiên, định danh thay thế hoặc UUID theo yêu cầu nghiệp vụ.
- Tổ chức URI cho collection, item và tài nguyên con.
- Tạo liên kết đến tài nguyên bằng Spring HATEOAS.
- Nhận biết các rủi ro khi định danh bị thay đổi, bị lộ thông tin hoặc bị dùng sai như cơ chế phân quyền.

## Tài nguyên được nhận diện như thế nào?

Tài nguyên (resource) là một khái niệm mà hệ thống muốn cung cấp qua giao diện REST. Đó có thể là một đối tượng đơn lẻ như đơn hàng, một tập hợp như danh sách đơn hàng, hoặc một khái niệm nghiệp vụ như hóa đơn và khoản thanh toán.

URI xác định tài nguyên. Khi client gửi request đến URI đó, server xử lý request và có thể trả về một biểu diễn (representation) của tài nguyên. Biểu diễn thường là JSON, XML hoặc một định dạng hypermedia như HAL JSON. URI và biểu diễn có vai trò khác nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Tài nguyên | Hệ thống đang cung cấp khái niệm nào? | Đơn hàng số 42 |
| URI | Client tham chiếu đến tài nguyên ở đâu? | `/orders/42` |
| Biểu diễn | Tài nguyên được mô tả bằng dữ liệu nào? | JSON chứa mã, trạng thái và tổng tiền |
| Định dạng biểu diễn | Dữ liệu được mã hóa theo quy tắc nào? | `application/hal+json` |
| Khóa lưu trữ | Cơ sở dữ liệu dùng giá trị nào để tìm bản ghi? | `order_pk = 91827` |

Một tài nguyên có thể có nhiều biểu diễn. Cùng URI `/orders/42`, client có thể nhận HAL JSON hoặc một biểu diễn khác tùy theo `Accept` và khả năng server hỗ trợ. Việc đổi định dạng biểu diễn không nhất thiết tạo ra tài nguyên mới.

Định danh tài nguyên cũng không bắt buộc phải trùng khóa chính của bảng cơ sở dữ liệu. Ví dụ, đơn hàng có khóa nội bộ `91827`, nhưng API công bố mã đơn hàng `ORD-2026-0042` hoặc UUID. Server ánh xạ định danh công khai về đối tượng nội bộ trong quá trình xử lý request. Cách tách biệt này giúp cấu trúc lưu trữ có thể thay đổi mà hợp đồng URI vẫn ổn định.

## URI và URL

URI là định danh tài nguyên. URL (Uniform Resource Locator) là một dạng URI chỉ ra cách định vị tài nguyên. Trong API HTTP, các liên kết thường là URL tuyệt đối hoặc URI tham chiếu tương đối có thể phân giải thành URL.

Một URI HTTP có thể gồm các phần:

```text
https://api.example.com/v1/orders/42?expand=items#summary
|---- scheme ---| |---- authority ----| |-- path --| |query| |fragment|
```

- **Scheme:** cách truy cập tài nguyên, thường là `https`.
- **Authority:** host và có thể gồm port, ví dụ `api.example.com`.
- **Path:** đường dẫn định danh tài nguyên hoặc một phần cấu trúc tài nguyên, ví dụ `/v1/orders/42`.
- **Query:** các tham số bổ sung cho request, thường dùng để lọc, sắp xếp, phân trang hoặc yêu cầu tùy chọn biểu diễn.
- **Fragment:** phần định vị nội bộ trong một biểu diễn hoặc tài liệu; fragment không được gửi trong HTTP request đến server.

Trong thiết kế API, path thường thể hiện danh tính của collection hoặc item. Query thường thể hiện cách truy vấn collection hoặc yêu cầu một góc nhìn cụ thể. Ví dụ:

```text
GET /orders/42
GET /orders?status=PENDING_PAYMENT
GET /orders?page=0&size=20&sort=createdAt,desc
```

Request đầu tham chiếu một đơn hàng cụ thể. Hai request sau truy vấn tập hợp đơn hàng với điều kiện lọc hoặc phân trang khác nhau. Query không nên trở thành nơi chứa một tập hợp dài các thuộc tính định danh cốt lõi của item nếu một URI item rõ ràng phù hợp hơn.

## Nguyên tắc thiết kế URI tài nguyên

URI là một phần của hợp đồng API. Client có thể lưu, chia sẻ, ghi log hoặc theo các liên kết URI trong thời gian dài. Vì vậy, hãy thiết kế URI có ý nghĩa, nhất quán và có thể duy trì.

### Dùng danh từ để biểu diễn tài nguyên

Path thường nên đặt tên theo danh từ số nhiều cho collection và định danh item cho phần tử:

```text
/orders
/orders/42
/customers
/customers/7
/products
/products/sku-ABC-001
```

Các URI trên thể hiện tài nguyên. HTTP method mô tả thao tác trên tài nguyên:

| Request | Ý nghĩa thường gặp |
| --- | --- |
| `GET /orders` | Đọc collection đơn hàng |
| `POST /orders` | Tạo một đơn hàng mới trong collection |
| `GET /orders/42` | Đọc đơn hàng có định danh 42 |
| `PUT /orders/42` | Thay thế biểu diễn của đơn hàng theo hợp đồng API |
| `PATCH /orders/42` | Cập nhật một phần đơn hàng |
| `DELETE /orders/42` | Xóa hoặc yêu cầu xóa đơn hàng theo chính sách API |

Không cần tạo path riêng cho mọi động từ như `/getOrders`, `/createOrder` hoặc `/deleteOrder`. Dùng HTTP method đúng ngữ nghĩa giúp giao diện nhất quán và các thành phần HTTP trung gian hiểu request tốt hơn.

Một số hành động nghiệp vụ không phù hợp với thao tác CRUD đơn giản vẫn có thể được mô hình hóa thành tài nguyên. Ví dụ, thanh toán có thể là tài nguyên `/payments`, hoặc một thao tác thanh toán có thể được công bố qua affordance trỏ đến endpoint phù hợp. Chọn mô hình dựa trên ngữ nghĩa nghiệp vụ và hợp đồng cần cung cấp, không chỉ dựa trên tên method trong service.

### Dùng cấu trúc phân cấp khi quan hệ có ý nghĩa

URI lồng nhau có thể biểu diễn quan hệ giữa tài nguyên cha và tài nguyên con:

```text
/customers/7/orders
/customers/7/orders/42
/orders/42/items
/orders/42/items/3
```

Cấu trúc này có thể hữu ích khi item con chỉ có ý nghĩa trong phạm vi cha hoặc khi API muốn diễn đạt rõ ngữ cảnh truy cập. Tuy nhiên, không nên lồng sâu chỉ để phản chiếu cấu trúc bảng hoặc object graph nội bộ.

Hãy cân nhắc: đơn hàng số 42 có định danh độc lập hay chỉ có thể được xác định thông qua khách hàng? Nếu đơn hàng có URI độc lập `/orders/42`, client có thể tham chiếu nó từ nhiều ngữ cảnh. Link relation có thể nối `/customers/7` đến `/orders/42` mà không bắt client phải giữ toàn bộ đường dẫn lồng nhau.

### Duy trì tính ổn định của định danh

URI công khai nên ổn định trong suốt vòng đời tài nguyên. Nếu tên hiển thị, email, trạng thái hoặc chủ sở hữu thay đổi, URI không nên tự thay đổi theo trừ khi chính định danh nghiệp vụ đó được thiết kế để thay đổi.

Ví dụ, không nên dùng tên khách hàng làm định danh chính:

```text
/customers/Nguyen-Van-An
```

Tên có thể trùng, thay đổi dấu, thay đổi cách viết hoặc được cập nhật. Có thể dùng định danh ổn định hơn:

```text
/customers/8f2c6d80-6c6d-4a22-9c4d-7d4d20a0d101
```

Tên khách hàng vẫn có thể nằm trong biểu diễn để hiển thị. Nếu API bắt buộc hỗ trợ URI cũ sau khi đổi định danh, cần có quy tắc alias hoặc redirect rõ ràng và kiểm thử chúng.

### Giữ path dễ đọc và nhất quán

Một số quy ước hữu ích:

- Chọn một quy tắc số ít hoặc số nhiều cho collection và giữ nhất quán.
- Dùng chữ thường trong path để tránh nhầm lẫn vì path có thể được xử lý phân biệt chữ hoa/chữ thường bởi server hoặc proxy.
- Dùng dấu gạch ngang để tách từ trong slug khi cần, ví dụ `/purchase-orders`.
- Hạn chế đưa dấu cách, ký tự có ý nghĩa đặc biệt hoặc chuỗi khó encode vào path.
- Không đưa tên bảng, tên class Java, tên service hoặc cấu trúc package vào URI công khai.
- Giữ URI ngắn vừa đủ; độ sâu path nên phản ánh quan hệ tài nguyên thật sự.

URI path là chuỗi có quy tắc encoding. Các ký tự dành riêng như `/`, `?`, `#` và `%` có ý nghĩa cú pháp. Nếu một định danh chứa các ký tự này, phải encode đúng theo từng thành phần URI. Không nối chuỗi đầu vào tùy ý vào URL vì có thể tạo URI sai hoặc thay đổi cấu trúc path/query ngoài dự kiến.

## Chọn loại định danh

Định danh công khai có thể là khóa tự nhiên, khóa thay thế hoặc UUID. Không có một lựa chọn đúng cho mọi hệ thống; cần xem xét tính ổn định, khả năng đọc, tính duy nhất, bảo mật và yêu cầu tích hợp.

| Loại định danh | Ví dụ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Khóa tự nhiên | Mã SKU, mã đơn hàng công khai | Có ý nghĩa nghiệp vụ, dễ trao đổi | Có thể đổi quy tắc, cần bảo đảm duy nhất |
| Số tuần tự | `42`, `1008` | Ngắn, dễ đọc, hiệu quả lưu trữ | Có thể đoán được và để lộ quy mô hoặc thứ tự |
| UUID | `8f2c6d80-...` | Xác suất trùng rất thấp, dễ tạo phân tán | Dài, khó đọc và sao chép |
| Slug | `spring-hateoas-guide` | Dễ đọc, phù hợp tài nguyên công khai | Có thể đổi, trùng tên hoặc cần chuẩn hóa |

### Khóa tự nhiên

Khóa tự nhiên lấy từ miền nghiệp vụ, chẳng hạn mã ISBN của sách, mã SKU của sản phẩm hoặc mã hóa đơn. Chọn loại này khi mã đã có quy tắc ổn định, duy nhất và được dùng rộng rãi trong các tích hợp.

Trước khi đưa khóa tự nhiên vào URI, cần trả lời:

- Mã có thể thay đổi khi doanh nghiệp đổi quy tắc không?
- Mã có thể được tái sử dụng sau khi tài nguyên bị xóa không?
- Mã có phân biệt chữ hoa/chữ thường không?
- Có ký tự cần encode không?
- Mã có chứa thông tin cá nhân hoặc thông tin nội bộ không?

Nếu mã có thể thay đổi, có thể dùng nó như thuộc tính tra cứu thay vì định danh chính của tài nguyên. Một định danh thay thế ổn định thường phù hợp hơn cho URI công khai.

### Khóa thay thế và số tuần tự

Khóa thay thế là giá trị được tạo riêng để định danh bản ghi, không mang ý nghĩa nghiệp vụ. Số tuần tự dễ sử dụng và ngắn, nhưng có thể cho phép người dùng suy ra số lượng tài nguyên hoặc thử lần lượt các ID.

Việc một URI khó đoán không thay thế được xác thực và phân quyền. API phải kiểm tra người gọi có quyền truy cập tài nguyên cụ thể hay không, bất kể định danh là `42` hay một chuỗi ngẫu nhiên dài.

### UUID và định danh phân tán

UUID phù hợp khi nhiều service hoặc node cần tạo định danh mà không cần hỏi một bộ cấp số tuần tự trung tâm. UUID cũng giảm khả năng người dùng đoán ID kế tiếp, nhưng không phải bí mật và không phải access token.

Ví dụ UUID trong Java:

```java
import java.util.UUID;

UUID orderId = UUID.randomUUID();
String publicId = orderId.toString();
```

Nếu dùng UUID trong URI, cần nhất quán cách biểu diễn và cách parse. Không nên thay định dạng UUID giữa các phiên bản mà không có chiến lược tương thích.

### Định danh kết hợp tenant

Trong hệ thống đa tenant, tài nguyên có thể được truy cập qua URI có ngữ cảnh tenant:

```text
/tenants/acme/orders/42
```

Hoặc hệ thống có thể giữ URI `/orders/42` và lấy tenant từ thông tin xác thực hoặc context request. Lựa chọn phụ thuộc vào mô hình tài nguyên và hợp đồng công khai. Dù chọn cách nào, server phải kiểm tra tài nguyên thuộc tenant mà người gọi được phép truy cập. Không tin cậy tenant ID chỉ vì client gửi nó trong path.

## Collection, item và tài nguyên con

Một cấu trúc API phổ biến có collection và item:

```text
/orders             collection
/orders/42          item
/orders/42/items    collection con
/orders/42/items/3  item con
```

Collection có thể hỗ trợ lọc, tìm kiếm, sắp xếp và phân trang bằng query parameters. Ví dụ:

```text
GET /orders?status=PAID&sort=createdAt,desc&page=0&size=20
```

Các tham số này thay đổi tập kết quả hoặc cách trình bày collection. Chúng không nhất thiết tạo ra một tài nguyên nghiệp vụ mới có vòng đời độc lập.

Nếu một kết quả tìm kiếm cần được lưu, chia sẻ hoặc tham chiếu lâu dài, ứng dụng có thể mô hình hóa nó thành tài nguyên riêng, ví dụ `/saved-searches/abc123`. Khi đó, kết quả tìm kiếm có định danh và vòng đời rõ ràng thay vì phụ thuộc vào một query dài.

### URI lồng nhau và URI độc lập

Chọn URI lồng nhau khi ngữ cảnh cha là một phần thiết yếu của cách định danh tài nguyên con. Chọn URI độc lập khi tài nguyên con có thể được tham chiếu từ nhiều nơi hoặc có vòng đời riêng.

Một thiết kế có thể cung cấp cả hai URI nếu có nhu cầu rõ ràng:

```text
/orders/42/items/3
/order-items/3
```

Nếu hai URI đại diện cùng một tài nguyên, hãy xác định URI chuẩn (canonical URI), relation nào dẫn đến nó và cách xử lý URI thay thế. Tránh để hai endpoint trả về các biểu diễn mâu thuẫn hoặc áp dụng quy tắc cập nhật khác nhau cho cùng tài nguyên.

## URI ổn định và khả năng tiến hóa API

Định danh là một phần của hợp đồng bên ngoài. Khi đã phát hành URI, client có thể lưu nó trong cơ sở dữ liệu, bookmark, cache, log hoặc message queue. Vì vậy, đổi URI có thể ảnh hưởng đến các hệ thống ngoài phạm vi triển khai server.

Một số cách quản lý thay đổi:

- Dùng định danh ổn định độc lập với tên hiển thị hoặc vị trí lưu trữ.
- Tách version API khỏi định danh nội bộ của tài nguyên. Nếu dùng prefix `/v1`, xác định rõ version áp dụng cho hợp đồng hay endpoint.
- Khi cần chuyển URI, công bố link mới và duy trì alias hoặc redirect theo chính sách tương thích.
- Cập nhật client để theo link từ response thay vì tự dựng URL.
- Không tái sử dụng URI của tài nguyên đã xóa cho một tài nguyên khác nếu điều đó có thể làm client cũ hiểu sai tham chiếu.
- Dùng link relation và canonical link để công bố URI chính thức khi có nhiều đường truy cập.

URI có thể là ổn định trong khi biểu diễn thay đổi theo thời gian. Ví dụ `/orders/42` vẫn định danh cùng một đơn hàng, nhưng `status`, `total` hoặc các liên kết khả dụng thay đổi khi đơn hàng đi qua các trạng thái nghiệp vụ.

## Định danh tài nguyên trong Spring HATEOAS

Spring HATEOAS giúp controller và assembler tạo liên kết dựa trên mapping đã khai báo. Cách làm này giảm lỗi do viết tay path và giúp ứng dụng điều chỉnh cấu trúc URI tại một nơi.

### Dùng `linkTo` và `methodOn`

Giả sử controller cung cấp collection và item:

```java
import java.util.Optional;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("collection"));
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        var items = orderService.findAll().stream()
            .map(order -> EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel()))
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Đoạn mã giả định `OrderService.findById` trả về `Optional<Order>` và `findAll` trả về danh sách đơn hàng. `@PathVariable` nhận giá trị định danh từ path. `methodOn(OrderController.class).one(id)` tạo lời gọi mô phỏng để Spring HATEOAS đọc mapping và tham số của method; method controller không được thực thi như một request thật trong bước tạo link. `withSelfRel()` đánh dấu liên kết đến chính item, còn `withRel("collection")` mô tả liên kết đến collection.

Khi mapping thay đổi từ `/orders/{id}` sang một cấu trúc khác, link được tạo từ controller mapping sẽ theo cấu trúc mới. Client tiêu thụ relation `self` hoặc `collection` không cần biết đường dẫn cụ thể đã thay đổi như thế nào.

### Định danh UUID trong controller

Nếu ứng dụng dùng UUID làm định danh công khai, controller có thể khai báo kiểu tham số `UUID`:

```java
import java.util.UUID;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/{id}")
EntityModel<Order> one(@PathVariable UUID id) {
    Order order = orderService.findByPublicId(id);
    return assembler.toModel(order);
}
```

Spring MVC có thể chuyển đổi path variable sang UUID. Service sẽ ánh xạ public ID về đối tượng miền hoặc khóa lưu trữ nội bộ. Nên trả status code phù hợp nếu định dạng ID không hợp lệ hoặc không tìm thấy tài nguyên; không để lỗi chuyển đổi hoặc truy vấn bị biến thành lỗi server không rõ nguyên nhân.

### Tập trung quy tắc tạo link bằng assembler

Khi nhiều endpoint cần tạo cùng loại representation, `RepresentationModelAssembler` giúp tập trung cách ánh xạ tài nguyên sang `EntityModel`. Assembler có thể gắn link `self`, link collection và các liên kết đến tài nguyên liên quan. Điều này giúp mọi response dùng cùng relation và quy tắc định danh.

Không nên để assembler tự xây URL bằng cách nối chuỗi ID vào path. Dùng `linkTo(methodOn(...))` hoặc cơ chế xây URI phù hợp để framework xử lý mapping và encoding. Khi tạo link có query parameter, hãy dùng builder có hỗ trợ encode tham số thay vì ghép chuỗi trực tiếp.

### URI tham chiếu và host của ứng dụng

Link trong response có thể là URI tương đối hoặc tuyệt đối. URI tương đối như `/orders/42` thường được client phân giải dựa trên URI của response. URI tuyệt đối có scheme và host, hữu ích khi API cần công bố địa chỉ đầy đủ hoặc được truy cập qua gateway.

Trong môi trường có reverse proxy hoặc API gateway, ứng dụng phải được cấu hình đúng để tạo host, scheme và prefix bên ngoài. Nếu không, server có thể phát ra link nội bộ như `http://localhost:8080/orders/42` hoặc link dùng HTTP trong khi client truy cập HTTPS. Hãy kiểm tra cấu hình forwarded headers và proxy theo môi trường triển khai; không lấy host tùy ý từ header không đáng tin cậy.

## Bảo mật và quyền riêng tư của định danh

Định danh công khai cần được xem là dữ liệu có thể bị người khác biết. Một URI không phải bí mật và việc biết URI không đồng nghĩa người gọi có quyền truy cập tài nguyên.

Các lưu ý quan trọng:

- **Không dựa vào độ khó đoán của ID để phân quyền.** ID tuần tự hay UUID đều phải đi kèm kiểm tra quyền truy cập ở server.
- **Tránh ID chứa dữ liệu cá nhân.** Không đưa email, số điện thoại, số giấy tờ hoặc thông tin nhạy cảm vào path.
- **Tránh lộ dữ liệu nội bộ.** Không dùng trực tiếp số thứ tự bản ghi nếu nó làm lộ thông tin kinh doanh không cần công bố.
- **Chống truy cập ngang quyền (IDOR/BOLA).** Với mỗi request có ID, xác minh người gọi có quyền thao tác đúng tài nguyên đó và đúng tenant hay không.
- **Không dùng URI làm token xác thực.** Nếu một liên kết có khả năng cấp quyền truy cập tạm thời, cần thiết kế token riêng, giới hạn phạm vi và thời hạn, đồng thời bảo vệ khỏi rò rỉ qua log hoặc referrer.
- **Chuẩn hóa và encode đầu vào.** Không nối path segment trực tiếp từ dữ liệu chưa kiểm soát; kiểm tra định dạng ID và dùng URI builder.

Ví dụ, hai khách hàng có thể cùng gọi `GET /orders/42`. Server phải xác minh đơn hàng 42 thuộc phạm vi mà từng người được phép xem. Nếu không, việc đoán hoặc thay ID trong URL có thể làm lộ dữ liệu của người khác.

## Kiểm thử định danh và liên kết

Kiểm thử URI không chỉ xác minh endpoint trả về status `200`. Cần kiểm tra định danh được phân giải đúng, liên kết trỏ đến tài nguyên đúng và hợp đồng vẫn ổn định khi mapping thay đổi.

Ví dụ với Spring MVC Test:

```java
@Test
void orderHasStableSelfLink() throws Exception {
    mockMvc.perform(get("/orders/{id}", 42)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith("/orders/42")));
}
```

Trong ứng dụng thực tế, nên tránh cố định host nếu host thay đổi theo môi trường. Ví dụ trên kiểm tra phần path cuối của URI; có thể bổ sung việc phân tích URI để xác minh scheme, host hoặc prefix theo hợp đồng triển khai. Dữ liệu test phải được chuẩn bị để ID 42 ánh xạ đúng đơn hàng.

Các trường hợp nên kiểm thử:

1. ID hợp lệ trả đúng tài nguyên.
2. ID sai định dạng trả lỗi client phù hợp, ví dụ `400 Bad Request`.
3. ID đúng định dạng nhưng không tồn tại trả `404 Not Found`.
4. Người dùng không có quyền không thể truy cập tài nguyên bằng cách thay ID.
5. Link `self` trỏ về đúng item và link collection trỏ đến đúng collection.
6. URI được encode đúng khi ID hoặc query có ký tự đặc biệt.
7. Link được tạo đúng sau khi mapping controller hoặc cấu hình proxy thay đổi.
8. Alias hoặc redirect của URI cũ hoạt động theo chính sách tương thích đã công bố.

## Những sai lầm thường gặp

**Dùng khóa chính cơ sở dữ liệu làm định danh công khai mà không cân nhắc.** Khóa nội bộ có thể thay đổi khi chuyển hệ thống, để lộ thứ tự dữ liệu hoặc gắn API quá chặt với cấu trúc lưu trữ. Hãy chọn định danh công khai dựa trên yêu cầu vòng đời và tích hợp.

**Dùng tên hoặc thuộc tính có thể thay đổi làm URI chính.** Tên hiển thị và email có thể thay đổi hoặc trùng nhau. Hãy ưu tiên định danh ổn định; dùng tên làm dữ liệu biểu diễn hoặc tiêu chí tìm kiếm.

**Nhồi mọi điều kiện lọc vào path.** Path nên nhận diện tài nguyên và quan hệ tài nguyên. Query phù hợp hơn cho lọc, phân trang, sắp xếp và tùy chọn truy vấn collection.

**Lồng URI quá sâu theo cấu trúc cơ sở dữ liệu.** API mô hình hóa tài nguyên và quan hệ nghiệp vụ, không phơi bày nguyên trạng schema lưu trữ.

**Nghĩ UUID bảo đảm an toàn.** UUID khó đoán hơn số tuần tự nhưng vẫn có thể bị lộ qua log, lịch sử trình duyệt hoặc response. Xác thực và phân quyền vẫn là bắt buộc.

**Viết URL bằng cách nối chuỗi.** Việc nối chuỗi có thể tạo lỗi slash, encoding, query hoặc host. Hãy dùng link builder và URI builder của framework.

**Giả định một tài nguyên chỉ có một biểu diễn.** Cùng một URI có thể phục vụ nhiều media type. Phân biệt định danh tài nguyên với định dạng biểu diễn và dùng content negotiation phù hợp.

## Kết luận

Resource identifier là nền tảng để client tham chiếu tài nguyên trong REST. URI công khai cần phản ánh tài nguyên và quan hệ có ý nghĩa, giữ ổn định qua vòng đời, tách biệt hợp lý khỏi khóa lưu trữ và không mang thông tin nhạy cảm. Collection, item và tài nguyên con nên được tổ chức theo ngữ nghĩa nghiệp vụ; query parameters dùng cho truy vấn collection và tùy chọn biểu diễn.

Trong Spring HATEOAS, hãy tạo liên kết dựa trên mapping controller hoặc assembler thay vì nối chuỗi URI. Khi kiểm thử, xác minh cả việc phân giải ID, relation, URI đích, phân quyền và khả năng duy trì liên kết khi API thay đổi. Một hệ thống định danh được thiết kế tốt giúp client tham chiếu tài nguyên đáng tin cậy và cho phép server tiến hóa cách triển khai nội bộ.
