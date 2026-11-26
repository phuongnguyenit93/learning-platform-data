# REST và RPC

REST và RPC là hai cách tổ chức hợp đồng giữa các thành phần trong một hệ thống phân tán. REST mô hình hóa miền nghiệp vụ thành tài nguyên có định danh và biểu diễn được trao đổi qua một giao diện thống nhất. RPC mô hình hóa lời gọi từ xa như việc gọi một thao tác hoặc hàm trên một dịch vụ. Cả hai đều có thể truyền dữ liệu qua mạng và đều có thể dùng HTTP; điểm khác biệt nằm ở cách thiết kế hợp đồng, ngữ nghĩa tương tác và cách client khám phá khả năng của server.

Trong Spring HATEOAS, REST là trọng tâm vì hypermedia bổ sung các liên kết và hành động vào representation của tài nguyên. Hiểu RPC giúp nhận ra khi nào API đang công bố tài nguyên, khi nào nó đang công bố lệnh, và cách chọn mô hình phù hợp cho từng nhu cầu.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt tư duy hướng tài nguyên của REST với tư duy hướng thao tác của RPC.
- Nhận diện REST và RPC qua URI, HTTP method, payload và hợp đồng API.
- Thiết kế cùng một nghiệp vụ theo hai mô hình trong Spring MVC.
- Giải thích cách Spring HATEOAS hỗ trợ khám phá tài nguyên và hành động trong REST.
- Chọn mô hình phù hợp dựa trên khả năng cache, retry, khả năng khám phá và yêu cầu tích hợp.

## REST và RPC mô hình hóa điều gì?

### REST: trao đổi biểu diễn của tài nguyên

REST (Representational State Transfer) là một kiểu kiến trúc cho hệ thống phân tán. Tài nguyên là khái niệm trọng tâm. Mỗi tài nguyên có thể được định danh bằng URI; client và server trao đổi các representation của tài nguyên thông qua một giao diện thống nhất.

Ví dụ, trong hệ thống bán hàng:

- `/orders` định danh tập hợp đơn hàng.
- `/orders/42` định danh đơn hàng có ID 42.
- `GET /orders/42` lấy representation của đơn hàng.
- `PATCH /orders/42` cập nhật một phần trạng thái tài nguyên nếu hợp đồng cho phép.

Client làm việc với tài nguyên và ngữ nghĩa HTTP chung. Server có thể thay đổi cách lưu trữ hoặc cấu trúc nội bộ mà không cần để client gọi trực tiếp từng hàm nội bộ.

REST thường được mô tả bằng các ràng buộc kiến trúc: client-server, stateless, cacheable, uniform interface, layered system và code-on-demand tùy chọn. Hypermedia as the Engine of Application State (HATEOAS) là một phần của ràng buộc giao diện thống nhất. Trong thực tế, nhiều API được gọi là REST chỉ dùng URI tài nguyên và HTTP method nhưng chưa triển khai đầy đủ hypermedia.

### RPC: yêu cầu dịch vụ thực hiện thao tác

RPC (Remote Procedure Call) mô hình hóa tương tác như lời gọi một thủ tục hoặc phương thức trên một tiến trình từ xa. Client biết tên thao tác và cấu trúc tham số; server thực thi thao tác rồi trả kết quả.

Ví dụ, một API hướng RPC có thể công bố:

```http
POST /getOrder
Content-Type: application/json

{"orderId": 42}
```

Hoặc:

```http
POST /cancelOrder
Content-Type: application/json

{"orderId": 42, "reason": "Customer request"}
```

Tên thao tác `getOrder` và `cancelOrder` là phần trung tâm của hợp đồng. Payload chứa tham số cho thao tác. Server thực hiện lời gọi và trả kết quả, chẳng hạn một đối tượng đơn hàng hoặc kết quả hủy.

RPC không bắt buộc dùng HTTP. Một số hệ thống dùng giao thức nhị phân hoặc giao thức chuyên biệt. gRPC là một framework RPC phổ biến, thường dùng Protocol Buffers để định nghĩa service và message, hỗ trợ unary call và các kiểu streaming. JSON-RPC cũng là một giao thức RPC có thể chạy trên nhiều transport.

## So sánh hai mô hình

| Khía cạnh | REST | RPC |
|---|---|---|
| Đơn vị tư duy | Tài nguyên và representation | Thao tác hoặc lời gọi hàm |
| Định danh | URI định danh tài nguyên | Tên service và operation thường định danh hành động |
| Tương tác | Giao diện thống nhất, thường dùng ngữ nghĩa HTTP | Gọi operation với tham số và nhận kết quả |
| Payload | Biểu diễn trạng thái tài nguyên hoặc dữ liệu liên quan | Tham số đầu vào và kết quả thao tác |
| Khám phá | Có thể khám phá qua liên kết hypermedia | Thường dựa trên schema, IDL hoặc tài liệu service |
| Cache | Có thể tận dụng ngữ nghĩa và cache HTTP, đặc biệt với GET | Phụ thuộc operation và cơ chế cache được thiết kế riêng |
| Retry | Có thể dựa vào safe/idempotent semantics của HTTP | Cần xác định rõ operation có an toàn khi gọi lại hay không |
| Hợp đồng | Resource model, media type, quan hệ và ngữ nghĩa HTTP | Service, method, kiểu request/response và mã lỗi |
| Phù hợp | API tài nguyên, tích hợp rộng, truy cập qua web | Lệnh nghiệp vụ, giao tiếp service-to-service có schema rõ |

Không nên phân loại chỉ dựa trên việc request dùng `GET` hay `POST`, hoặc payload là JSON. Một endpoint RPC có thể chạy qua HTTP POST với JSON; một API REST cũng có thể dùng POST để tạo tài nguyên hoặc thực hiện một chuyển trạng thái được mô hình hóa phù hợp. Cần xem toàn bộ hợp đồng và cách client tương tác.

## Cùng một nghiệp vụ theo REST và RPC

Giả sử ứng dụng quản lý đơn hàng có hai nhu cầu: đọc thông tin đơn hàng và yêu cầu hủy đơn.

### Thiết kế theo REST

```http
GET /orders/42
Accept: application/hal+json
```

Server trả representation của đơn hàng cùng các liên kết:

```json
{
  "id": 42,
  "status": "NEW",
  "_links": {
    "self": { "href": "/orders/42" },
    "orders": { "href": "/orders" },
    "cancel": { "href": "/orders/42/cancellation" }
  }
}
```

Client đọc liên kết `cancel` rồi gửi request đến URI trong `href`. Nếu hủy đơn được mô hình hóa là tạo một tài nguyên cancellation, request có thể là:

```http
POST /orders/42/cancellation
Content-Type: application/json

{"reason": "Customer request"}
```

Ở đây, client làm việc với đơn hàng và tài nguyên cancellation. Quan hệ `cancel` cho biết khả năng chuyển tiếp hiện tại. Khi đơn hàng không còn hủy được, server có thể không công bố liên kết này.

Một thiết kế REST khác có thể biểu diễn hủy đơn như cập nhật trạng thái của đơn hàng bằng `PATCH /orders/42`. Lựa chọn phụ thuộc vào miền nghiệp vụ: nếu việc hủy tạo ra một thực thể có vòng đời, lịch sử hoặc dữ liệu riêng, tài nguyên cancellation thường diễn tả rõ hơn. Nếu chỉ cập nhật trường trạng thái, PATCH có thể phù hợp.

### Thiết kế theo RPC

```http
POST /getOrder
Content-Type: application/json

{"orderId": 42}
```

```http
POST /cancelOrder
Content-Type: application/json

{"orderId": 42, "reason": "Customer request"}
```

Client gọi trực tiếp operation đã biết. Hợp đồng cần mô tả tên thao tác, cấu trúc request, response, lỗi có thể xảy ra và điều kiện gọi. Server có thể trả về `OrderDto` sau khi đọc hoặc một kết quả thao tác sau khi hủy.

Hai thiết kế có thể phục vụ cùng một nghiệp vụ, nhưng client phụ thuộc vào những điều khác nhau. Client REST dựa vào resource model, quan hệ và ngữ nghĩa HTTP. Client RPC dựa vào tên operation và schema request/response.

## Triển khai hai phong cách với Spring MVC

### Controller hướng tài nguyên

Với Spring HATEOAS, controller có thể trả về model tài nguyên và các liên kết được tạo từ mapping:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderResourceController {

    private final OrderService orders;

    OrderResourceController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);
        var model = EntityModel.of(
            order,
            linkTo(methodOn(OrderResourceController.class).one(id)).withSelfRel()
        );

        if (order.cancellable()) {
            model.add(linkTo(methodOn(OrderResourceController.class)
                .cancel(id, new CancelOrderRequest("")))
                .withRel("cancel"));
        }

        return model;
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(
            @PathVariable long id,
            @RequestBody CancelOrderRequest request) {
        orders.cancel(id, request.reason());
        return ResponseEntity.noContent().build();
    }
}

record OrderView(long id, String status, boolean cancellable) {}
record CancelOrderRequest(String reason) {}
```

Ví dụ tập trung vào cách tổ chức hợp đồng; `OrderService` là tầng nghiệp vụ do ứng dụng cung cấp. `linkTo` và `methodOn` tạo URI dựa trên mapping của controller. Client có thể đọc liên kết `self` và `cancel` thay vì phải biết trước đường dẫn. Trong hệ thống thực tế, cần bảo đảm cách mô tả input của liên kết phù hợp với media type hypermedia mà client sử dụng; một HAL link thông thường chỉ cung cấp đích liên kết, chưa mô tả đầy đủ schema của request body.

### Controller hướng thao tác

Một controller hướng RPC có thể đặt tên endpoint theo operation:

```java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderCommandController {

    private final OrderService orders;

    OrderCommandController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/getOrder")
    OrderView getOrder(@RequestBody GetOrderRequest request) {
        return orders.findById(request.orderId());
    }

    @PostMapping("/cancelOrder")
    CancelOrderResult cancelOrder(@RequestBody CancelOrderRequest request) {
        orders.cancel(request.orderId(), request.reason());
        return new CancelOrderResult(request.orderId(), "CANCELLED");
    }
}

record GetOrderRequest(long orderId) {}
record CancelOrderRequest(long orderId, String reason) {}
record CancelOrderResult(long orderId, String status) {}
```

Trong ví dụ RPC, tên endpoint và kiểu DTO là hợp đồng chính. Việc dùng `POST` cho cả đọc và ghi không tự động biến API thành REST hay RPC; cách đặt tên operation và mô hình request/response mới thể hiện phong cách RPC. Nếu triển khai RPC qua HTTP, hãy cân nhắc cache, mã trạng thái, timeout, retry và idempotency cho từng operation.

Hai controller trên minh họa hai phong cách thiết kế. Không nên đặt cả hai bộ endpoint trùng chức năng vào một API chỉ để tăng số đường dẫn. Hãy chọn hợp đồng mà client mục tiêu có thể sử dụng rõ ràng, rồi tổ chức lớp nghiệp vụ dùng chung phía sau nếu cần.

## Vai trò của hypermedia trong REST

Hypermedia giúp client khám phá các bước tiếp theo từ representation hiện tại. Spring HATEOAS cung cấp `RepresentationModel`, `EntityModel`, `CollectionModel`, `Link`, `Affordance` và các builder liên kết để tạo hợp đồng đó.

Ví dụ, một đơn hàng ở trạng thái `NEW` có thể chứa liên kết `cancel`. Sau khi đơn hàng được giao, representation mới có thể bỏ liên kết này. Client không phải tự viết điều kiện `if (status == NEW)` dựa trên chi tiết nội bộ của server; client có thể kiểm tra hành động mà server công bố.

Để mô tả hành động chi tiết hơn, Spring HATEOAS hỗ trợ affordance. Affordance có thể cung cấp thông tin về HTTP method và đầu vào của hành động khi được tuần tự hóa bằng media type phù hợp, ví dụ HAL-FORMS. HAL JSON thông thường biểu diễn liên kết trong `_links`; chỉ có `href` không đồng nghĩa client đã biết cấu trúc body cần gửi.

RPC thường công bố danh sách thao tác trong schema hoặc IDL, ví dụ file `.proto` của gRPC. Client sinh mã hoặc dùng SDK dựa trên schema đó. Đây cũng là một cách khám phá hợp đồng, nhưng nó diễn ra ở cấp service và operation, thay vì qua liên kết được gửi trong từng representation tài nguyên.

## HTTP semantics, cache và retry

REST tận dụng ngữ nghĩa chuẩn của HTTP. Một số đặc tính quan trọng:

- `GET` là safe: client không yêu cầu thay đổi trạng thái nghiệp vụ khi gọi.
- `PUT` và `DELETE` có ngữ nghĩa idempotent theo HTTP: lặp lại cùng request có cùng hiệu ứng dự kiến trên trạng thái đích.
- `POST` thường không idempotent theo mặc định; tạo tài nguyên hoặc thực hiện lệnh có thể tạo hiệu ứng lặp nếu client gửi lại.
- `PATCH` không mặc nhiên idempotent; điều đó phụ thuộc vào định nghĩa patch và cách server xử lý.
- Cache HTTP dựa vào method, header và chỉ thị cache; GET có thể cache nếu response cho phép.

RPC không tự động thừa hưởng ngữ nghĩa này chỉ vì transport là HTTP. Ví dụ, `POST /chargeAccount` có thể trừ tiền mỗi lần gọi. Nếu client timeout và gửi lại, server có thể thực hiện giao dịch hai lần. Cần thiết kế idempotency key, mã giao dịch, timeout và chính sách retry phù hợp. Với gRPC, các chính sách retry cũng phải xem xét loại RPC, trạng thái lỗi và khả năng server đã thực hiện thao tác.

Ngay cả API REST cũng cần xử lý retry cẩn thận với POST hoặc các thao tác có tác động phụ. Dùng đúng HTTP method giúp client và intermediary hiểu hợp đồng tốt hơn, nhưng không thay thế logic bảo vệ giao dịch ở server.

## Khả năng tiến hóa hợp đồng

Trong REST có hypermedia, client phụ thuộc vào URI điểm vào, media type, ý nghĩa quan hệ và quy tắc thao tác. Nếu server đổi mapping từ `/orders/42` sang `/sales/orders/42`, các liên kết được tạo bằng `linkTo(methodOn(...))` có thể phản ánh mapping mới. Client theo `href` sẽ không cần tự ghép lại URI. Tuy vậy, ý nghĩa của relation như `self`, `orders` hoặc `cancel` phải ổn định và được mô tả cho client.

Trong RPC, client thường phụ thuộc vào tên operation, kiểu request/response và schema. Đổi tên `cancelOrder`, xóa trường bắt buộc hoặc thay đổi kiểu dữ liệu có thể phá vỡ client đã sinh mã từ schema cũ. Các hệ thống RPC cần quy tắc tương thích schema, chiến lược versioning và kiểm thử consumer/provider.

| Thay đổi | REST có hypermedia | RPC |
|---|---|---|
| Đổi đường dẫn nội bộ | Client theo `href` có thể tiếp tục hoạt động nếu entry point và relation ổn định | Client có thể bị ảnh hưởng nếu endpoint là một phần của stub hoặc cấu hình |
| Đổi tên relation | Có thể phá client đang tìm relation cũ | Không áp dụng trực tiếp; tương tự đổi tên operation |
| Thêm trường response tùy chọn | Thường có thể tương thích nếu client bỏ qua trường chưa biết | Thường tương thích nếu schema và quy tắc mã hóa cho phép |
| Xóa hoặc đổi kiểu trường | Có thể phá client đang đọc trường đó | Có thể phá client được sinh từ schema cũ |
| Thêm hành động | Có thể công bố thêm liên kết hoặc affordance | Thường cần thêm operation vào service contract |

Không mô hình nào tự động bảo đảm tương thích. Cần giữ ngữ nghĩa ổn định, quản lý schema, tài liệu hóa thay đổi và kiểm thử với client đại diện.

## Khi nào nên chọn REST hoặc RPC?

REST thường phù hợp khi:

- Dữ liệu nghiệp vụ có thể mô hình hóa tự nhiên thành tài nguyên và quan hệ.
- Nhiều loại client cần truy cập qua HTTP, trình duyệt hoặc công cụ thông dụng.
- Cần tận dụng cache, status code, content negotiation và các semantics HTTP.
- Client cần khám phá tài nguyên hoặc hành động từ hypermedia.

RPC thường phù hợp khi:

- Nghiệp vụ được diễn đạt tự nhiên thành lệnh hoặc thao tác có đầu vào/đầu ra rõ.
- Giao tiếp nội bộ cần schema chặt chẽ, code generation hoặc streaming.
- Client và server được phát triển theo service contract có quản lý phiên bản.
- Một thao tác nghiệp vụ phức tạp không biểu diễn rõ ràng thành thao tác trên một tài nguyên đơn lẻ.

Đây là hướng dẫn lựa chọn, không phải quy tắc tuyệt đối. Một hệ thống có thể dùng REST cho API công khai và RPC cho giao tiếp nội bộ giữa các service. Một lệnh nghiệp vụ cũng có thể được mô hình hóa thành tài nguyên trong REST, chẳng hạn tạo `payment`, `shipment` hoặc `cancellation` rồi theo dõi vòng đời tài nguyên đó.

## Lỗi thiết kế thường gặp

| Lỗi | Vì sao gây khó khăn | Cách cải thiện |
|---|---|---|
| Gọi mọi API dùng HTTP là REST | Transport không quyết định phong cách kiến trúc | Đánh giá resource model, uniform interface và hợp đồng thực tế |
| Tạo endpoint REST theo từng động từ như `/getOrder`, `/deleteOrder` | Hợp đồng nghiêng về operation và không tận dụng ngữ nghĩa HTTP | Mô hình hóa tài nguyên và dùng method HTTP phù hợp, hoặc xác định rõ đây là RPC |
| Dùng `POST` cho mọi thao tác mà không mô tả retry | Client khó suy luận safe/idempotent semantics | Chọn method phù hợp và thiết kế idempotency cho lệnh có tác động phụ |
| Cho rằng có liên kết `href` là client biết cách gọi | Liên kết HAL cơ bản chưa mô tả đầy đủ body hoặc schema | Dùng affordance và media type phù hợp khi client cần mô tả thao tác |
| Cho rằng REST không cần schema hay tài liệu | Relation, representation và quy tắc nghiệp vụ vẫn là hợp đồng | Tài liệu hóa media type, relation, trường và lỗi |
| Thay đổi operation hoặc relation mà không kiểm tra client | Client cũ có thể không hiểu hợp đồng mới | Kiểm thử tương thích và quản lý phiên bản |

## Ghi nhớ

REST tổ chức tương tác quanh tài nguyên, representation và giao diện thống nhất. RPC tổ chức tương tác quanh lời gọi operation với tham số và kết quả. Cả hai có thể dùng HTTP và JSON, vì vậy cần xem cách thiết kế hợp đồng thay vì chỉ nhìn transport. Spring HATEOAS giúp REST API công bố liên kết và affordance để client khám phá hành động từ trạng thái tài nguyên. RPC có lợi thế khi service contract, operation và schema là trung tâm. Hãy chọn mô hình theo miền nghiệp vụ, client, semantics cần có và cách hệ thống sẽ tiến hóa.
