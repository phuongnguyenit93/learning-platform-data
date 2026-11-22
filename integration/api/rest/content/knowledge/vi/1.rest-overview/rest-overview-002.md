# Tài nguyên, biểu diễn, client và server liên hệ với nhau thế nào

Khi một ứng dụng gọi `GET /orders/ord_42` và nhận về JSON, điều gì đang diễn ra? Đơn hàng không được chuyển từ server sang máy người dùng. Server gửi một **biểu diễn của tài nguyên đơn hàng** để client có thể hiểu trạng thái hiện tại và quyết định bước tiếp theo.

Đây là nền tảng của module **INTEGRATION_API_REST**: thiết kế API dựa trên tài nguyên, URI, phương thức HTTP, mã trạng thái và hợp đồng dữ liệu rõ ràng. Hiểu đúng mối liên hệ này giúp việc học phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử API có một mô hình chung để dựa vào.

Sau bài này, bạn có thể:

- Phân biệt tài nguyên, URI, biểu diễn và thông điệp HTTP.
- Xác định vai trò client và server trong từng lần tương tác.
- Giải thích vì sao cùng một tài nguyên có thể có nhiều biểu diễn.
- Theo dõi một vòng tạo, đọc và thay đổi tài nguyên mà không đồng nhất API với bảng cơ sở dữ liệu.
- Áp dụng mô hình đó vào một API Java/Spring đơn giản.

## 1. Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ trong hệ thống đặt hàng |
| --- | --- | --- |
| Tài nguyên — resource | Khái niệm có thể được định danh và tương tác thông qua API | Một đơn hàng; tập đơn hàng; thông tin giao hàng của một đơn |
| Biểu diễn — representation | Dữ liệu mô tả tài nguyên trong một dạng mà hai bên hiểu được | JSON mô tả đơn hàng; bản HTML để hiển thị cùng đơn hàng |
| Client | Thành phần khởi tạo yêu cầu trong một tương tác | Ứng dụng web, ứng dụng di động, chương trình kiểm thử, dịch vụ khác |
| Server | Thành phần tiếp nhận, hiểu yêu cầu và cung cấp phản hồi | Dịch vụ quản lý đơn hàng cung cấp API HTTP |

Hai khái niệm đi kèm cần nhớ:

- **URI** xác định tài nguyên mà yêu cầu hướng đến, chẳng hạn `https://api.example.test/orders/ord_42`.
- **Thông điệp HTTP** mang phương thức, URI đích, header, mã trạng thái và body khi có. Biểu diễn có thể được truyền trong body, nhưng thông điệp còn chứa nhiều thông tin điều khiển khác.

Có thể hình dung như sau:

```text
Client -- yêu cầu HTTP hướng đến URI --> Server
Client <-- phản hồi HTTP, có thể kèm biểu diễn -- Server
                                           |
                                  quản lý tài nguyên
                                           |
                            dữ liệu và quy tắc nghiệp vụ
```

Tài nguyên là đối tượng mà hai bên đang nói đến. Biểu diễn là thông tin về đối tượng đó được truyền đi. Client và server là hai vai trò tham gia cuộc trao đổi.

## 2. Tài nguyên không đồng nghĩa với một dòng trong cơ sở dữ liệu

Xét đơn hàng `ord_42`. Trong nghiệp vụ, đơn hàng có danh tính, người mua, các dòng hàng, trạng thái và vòng đời. Đó là tài nguyên mà API có thể công khai tại:

```text
/orders/ord_42
```

Ở bên trong, server có thể ghép thông tin từ các bảng `orders`, `order_items`, từ dịch vụ giá và từ hệ thống vận chuyển. Client không cần biết những chi tiết đó để đọc đơn hàng.

Một tài nguyên cũng có thể là:

- Một tập hợp: `/orders`.
- Một tài nguyên liên quan: `/orders/ord_42/shipment`.
- Một kết quả được tính toán: `/products/prd_7/availability`.
- Một tiến trình xử lý có thể theo dõi: `/export-jobs/job_9`.

Không phải mỗi tài nguyên đều cần một bảng riêng. Ngược lại, không phải mỗi bảng nội bộ đều cần một endpoint công khai.

### Danh tính và trạng thái là hai chuyện khác nhau

Đơn hàng `ord_42` có thể đi từ `DRAFT` sang `CONFIRMED`, nhưng vẫn là cùng một đơn hàng. URI ổn định giúp client tiếp tục tìm đến tài nguyên qua nhiều lần thay đổi trạng thái.

```text
Danh tính: ord_42
URI:      /orders/ord_42

Trạng thái lúc t1: DRAFT
Trạng thái lúc t2: CONFIRMED
```

Tên khách hàng, tổng tiền hoặc trạng thái xuất hiện trong JSON không tự trở thành định danh. Khi chọn URI, cần dựa vào cách nhận diện tài nguyên trong hợp đồng API, không dựa vào dữ liệu dễ thay đổi.

URI và tài nguyên cũng không nhất thiết có quan hệ một-một tuyệt đối: một hệ thống có thể cung cấp nhiều URI dẫn tới cùng một tài nguyên. Trong thiết kế thực tế, xác định một URI chuẩn thường giúp liên kết và cache dễ quản lý hơn.

## 3. Biểu diễn là cách mô tả tài nguyên khi trao đổi

Một biểu diễn JSON của đơn hàng có thể là:

```json
{
  "id": "ord_42",
  "status": "DRAFT",
  "totalAmount": 289000,
  "currency": "VND",
  "items": [
    {
      "productId": "prd_7",
      "quantity": 1
    }
  ]
}
```

JSON này mô tả một số khía cạnh của đơn hàng tại thời điểm tạo phản hồi. Nó không phải toàn bộ trạng thái nội bộ của server. Server có thể còn lưu lịch sử thay đổi, thông tin chống gian lận hoặc ghi chú nội bộ mà hợp đồng API không công khai.

Vì thế, cần phân biệt ba lớp:

```text
Tài nguyên trong nghiệp vụ
          |
          | chọn thông tin được công khai
          v
Mô hình dữ liệu trao đổi, ví dụ OrderResponse
          |
          | mã hóa theo media type
          v
Các byte JSON/HTML/... trong thông điệp HTTP
```

### Cùng tài nguyên, nhiều biểu diễn

Một đơn hàng có thể được trình bày dưới dạng JSON cho ứng dụng di động và HTML cho trình duyệt. Đó là hai biểu diễn của cùng tài nguyên nếu API thiết kế chúng theo cách này.

Biểu diễn cũng có thể khác nhau theo:

- Ngôn ngữ được chọn.
- Bộ trường được yêu cầu, nếu API hỗ trợ lựa chọn trường.
- Quyền của người gọi.
- Thời điểm đọc, vì trạng thái tài nguyên có thể đã thay đổi.

Ví dụ, nhân viên hỗ trợ có thể được thấy thêm thông tin liên hệ; người chưa được cấp quyền có thể bị từ chối toàn bộ yêu cầu. Biến thể theo quyền không có nghĩa server được tùy tiện trả dữ liệu nhạy cảm: việc kiểm tra quyền diễn ra trước khi tạo biểu diễn phù hợp.

Client nhận dữ liệu rồi sửa một thuộc tính trong bộ nhớ của mình cũng chưa làm tài nguyên trên server thay đổi. Muốn thay đổi, client phải gửi một yêu cầu được server chấp nhận.

## 4. Client và server là vai trò trong một tương tác

Client không chỉ là giao diện người dùng. Một chương trình Java dùng HTTP client để gọi API cũng là client. Tương tự, server không đồng nghĩa với cơ sở dữ liệu hoặc một máy vật lý duy nhất.

Giả sử có luồng:

```text
Ứng dụng di động ---> Dịch vụ đơn hàng ---> Dịch vụ thanh toán
```

- Khi ứng dụng di động gọi dịch vụ đơn hàng, ứng dụng là client và dịch vụ đơn hàng là server.
- Khi dịch vụ đơn hàng gọi dịch vụ thanh toán, dịch vụ đơn hàng trở thành client của dịch vụ thanh toán.

Một thành phần có thể đồng thời đảm nhiệm hai vai trò trong các tương tác khác nhau.

### Trách nhiệm của mỗi bên

| Client | Server |
| --- | --- |
| Chọn tài nguyên cần tương tác | Nhận diện tài nguyên đích |
| Chọn phương thức phù hợp với ý định | Thực hiện đúng ngữ nghĩa của phương thức |
| Gửi header, dữ liệu đầu vào và thông tin xác thực cần thiết | Xác thực, phân quyền và kiểm tra dữ liệu |
| Hiểu mã trạng thái và hợp đồng phản hồi | Áp dụng quy tắc nghiệp vụ và tạo phản hồi |
| Quản lý luồng tương tác, ví dụ màn hình đang mở | Quản lý trạng thái tài nguyên và việc lưu trữ |

Client không quyết định kết quả cuối cùng chỉ bằng cách gửi `"status": "CONFIRMED"`. Server vẫn phải kiểm tra đơn hàng có đủ điều kiện xác nhận hay không. Tương tự, `"totalAmount"` do client gửi không buộc server phải tin vào giá trị đó nếu tổng tiền là dữ liệu server chịu trách nhiệm tính.

## 5. Đọc tài nguyên qua một vòng HTTP

Các ví dụ HTTP dưới đây lược bỏ một số header vận chuyển để tập trung vào nội dung trao đổi. `api.example.test` là tên miền minh họa.

Client yêu cầu một biểu diễn JSON:

```http
GET /orders/ord_42 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Server phản hồi:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=30
ETag: "order-42-v3-json"

{
  "id": "ord_42",
  "status": "DRAFT",
  "totalAmount": 289000,
  "currency": "VND"
}
```

Tách các thành phần của cuộc trao đổi:

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| `GET` | Yêu cầu đọc biểu diễn của tài nguyên đích |
| `/orders/ord_42` | Định danh đích của yêu cầu trên server này |
| `Accept: application/json` | Cho biết client chấp nhận biểu diễn JSON |
| `200 OK` | Cho biết yêu cầu đã được xử lý thành công theo ngữ nghĩa tương ứng |
| `Content-Type: application/json` | Mô tả kiểu dữ liệu thực tế của body phản hồi |
| Body JSON | Biểu diễn đơn hàng được gửi cho client |
| `Cache-Control` | Chính sách cache mà server công bố cho phản hồi này |
| `ETag` | Bộ xác thực cho biểu diễn được chọn, có thể dùng trong yêu cầu có điều kiện |

`Cache-Control` ở đây chỉ là chính sách minh họa, không phải giá trị mặc định phù hợp cho mọi API đơn hàng. Dữ liệu nhạy cảm hoặc yêu cầu độ mới khác nhau cần chính sách tương ứng.

### `Accept` và `Content-Type` trả lời hai câu hỏi khác nhau

- `Accept`: bên gửi yêu cầu có thể nhận những media type nào trong phản hồi?
- `Content-Type`: body đang được gửi có media type nào?

Nếu một request tạo đơn có body JSON, request thường cần `Content-Type: application/json`. Nếu client cũng muốn phản hồi JSON, nó gửi thêm `Accept: application/json`. Header của request và header của response mô tả các body theo từng chiều trao đổi.

Khi server thực sự lựa chọn JSON hoặc HTML theo `Accept`, phản hồi có thể cần:

```http
Vary: Accept
```

Header này giúp cache biết rằng lựa chọn biểu diễn phụ thuộc vào `Accept`. Nó không tự cấp quyền cache, cũng không thay cho chính sách `Cache-Control`.

Nếu server không hỗ trợ media type của request, `415 Unsupported Media Type` là phản hồi liên quan. Nếu không thể cung cấp biểu diễn mà client chấp nhận, server có thể trả `406 Not Acceptable` theo chính sách thương lượng nội dung của API.

## 6. Tạo tài nguyên: dữ liệu gửi vào và tài nguyên được tạo ra

Client có thể đề nghị tạo đơn hàng bằng cách gửi yêu cầu đến tập đơn hàng:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json

{
  "items": [
    {
      "productId": "prd_7",
      "quantity": 1
    }
  ]
}
```

Trong ví dụ này:

1. Tài nguyên đích của request là tập đơn hàng `/orders`.
2. Body chứa dữ liệu đầu vào cho việc tạo một đơn hàng mới.
3. Server xác thực người gọi, kiểm tra sản phẩm, số lượng và các điều kiện nghiệp vụ.
4. Server quyết định định danh, trạng thái ban đầu và tổng tiền theo hợp đồng.
5. Server tạo tài nguyên mới và trả kết quả.

```http
HTTP/1.1 201 Created
Location: /orders/ord_42
Content-Type: application/json

{
  "id": "ord_42",
  "status": "DRAFT",
  "totalAmount": 289000,
  "currency": "VND"
}
```

`Location` cho client biết URI của tài nguyên mới trong ví dụ này. Giá trị bắt đầu bằng `/` là một tham chiếu tương đối được giải theo URI của yêu cầu; nó không cần lặp lại toàn bộ hostname.

Body tạo đơn không nhất thiết giống body đọc đơn. Client chưa có `id`, còn tổng tiền có thể là dữ liệu do server tính. Bởi vậy, các mô hình như `CreateOrderRequest` và `OrderResponse` thường có trách nhiệm khác nhau.

### Không phải body nào cũng là toàn bộ biểu diễn của tài nguyên đích

Body của `POST /orders` là dữ liệu phục vụ việc xử lý của tập đơn hàng; nó không phải toàn bộ tập đơn hàng. Tương tự, body của một yêu cầu `PATCH` có thể là tài liệu mô tả các thay đổi, theo media type đã chọn.

Do đó, khi đọc API, hãy hỏi đồng thời:

- URI đang hướng tới tài nguyên nào?
- Phương thức có ý nghĩa gì?
- Hợp đồng quy định body mang dữ liệu gì?

Chỉ nhìn JSON sẽ không đủ để trả lời cả ba câu hỏi.

## 7. Phương thức và mã trạng thái làm rõ cách tương tác

URI trả lời “tương tác với tài nguyên nào”; phương thức giúp trả lời “tương tác theo cách nào”.

| Yêu cầu | Ý định thông thường | Phản hồi có thể gặp |
| --- | --- | --- |
| `GET /orders/ord_42` | Đọc biểu diễn đơn hàng | `200` kèm biểu diễn; `404` khi không tìm thấy tài nguyên theo cách API công bố |
| `POST /orders` | Nhờ tập đơn hàng xử lý việc tạo đơn | `201` và URI tài nguyên mới khi tạo thành công |
| `PUT /profiles/me/preferences` | Tạo hoặc thay thế trạng thái của tài nguyên tùy chọn theo biểu diễn được gửi | `201` nếu tạo mới; `200` hoặc `204` khi cập nhật thành công |
| `PATCH /orders/ord_42` | Áp dụng thay đổi được mô tả trong tài liệu patch | `200` kèm phản hồi hoặc `204` khi thành công và không gửi nội dung |
| `DELETE /orders/ord_42` | Yêu cầu loại bỏ liên kết giữa URI đích và chức năng hiện tại của tài nguyên, nếu API cho phép | `204` khi đã thực hiện thành công và không gửi nội dung; có thể có kết quả khác theo hợp đồng |

Đây là ví dụ, không phải danh sách đầy đủ mọi kết quả hợp lệ. Quy tắc nghiệp vụ có thể không cho phép xóa hoặc cập nhật một đơn đã xác nhận.

`PUT` mang ý nghĩa thay thế trạng thái theo hợp đồng của tài nguyên. Điều đó không có nghĩa client được ghi đè mọi cột dữ liệu nội bộ hoặc được thay đổi các trường do server quản lý.

`DELETE` cũng không cam kết dữ liệu vật lý đã bị xóa sạch khỏi mọi nơi lưu trữ. Hệ thống có thể cần giữ lịch sử theo nghiệp vụ; hợp đồng API phải làm rõ hành vi quan sát được của tài nguyên.

### Tài nguyên tồn tại không có nghĩa mọi phản hồi đều có JSON

Một phản hồi `204 No Content` không có body. Một yêu cầu `HEAD` cũng nhận phản hồi không có body dù tài nguyên có thể tồn tại và `GET` có thể trả biểu diễn của nó.

Nếu `GET` không thành công và server trả body mô tả lỗi, body đó mô tả vấn đề của yêu cầu, không phải một đơn hàng thành công có thêm trường `error`. Client cần xem mã trạng thái và kiểu nội dung trước khi giải mã dữ liệu theo `OrderResponse`.

## 8. Trạng thái tài nguyên và trạng thái tương tác của client

Hai loại trạng thái thường bị nhầm:

| Loại trạng thái | Ví dụ | Thành phần thường chịu trách nhiệm |
| --- | --- | --- |
| Trạng thái tài nguyên | Đơn hàng đang `DRAFT`, địa chỉ giao hàng đã lưu | Server quản lý theo quy tắc nghiệp vụ |
| Trạng thái tương tác của ứng dụng client | Người dùng đang mở tab nào, đang chọn bộ lọc nào, sẽ mở liên kết nào tiếp theo | Client quản lý luồng tương tác |

Với cách tương tác stateless của REST, mỗi request cần mang đủ thông tin để server hiểu và xử lý mà không phụ thuộc vào việc ghi nhớ các bước hội thoại trước đó của client.

Ví dụ, request đọc đơn cần có URI của đơn và thông tin xác thực nếu API yêu cầu. Client không nên chỉ gửi “đọc đơn vừa chọn ở bước trước” rồi trông chờ server nhớ màn hình trước của mình.

Stateless không có nghĩa server không được dùng cơ sở dữ liệu. Server vẫn lưu đơn hàng, quyền truy cập và các dữ liệu nghiệp vụ cần thiết. Điểm phân biệt là trạng thái của tài nguyên được quản lý lâu dài và ngữ cảnh hội thoại mà một request phải dựa vào để được hiểu.

Một giỏ hàng cũng có thể là tài nguyên lưu trên server nếu có định danh và hợp đồng rõ ràng. Việc lưu giỏ hàng không tự làm API mất tính stateless; cần xét các request có tự mang đủ ngữ cảnh tương tác hay không.

## 9. Liên kết giữa tài nguyên giúp client đi tiếp

Một biểu diễn có thể chứa liên kết đến các tài nguyên liên quan:

```json
{
  "id": "ord_42",
  "status": "CONFIRMED",
  "links": {
    "self": "/orders/ord_42",
    "shipment": "/orders/ord_42/shipment"
  }
}
```

Client có thể dùng liên kết `shipment` để lấy thông tin giao hàng. Cách này giúp diễn đạt quan hệ giữa tài nguyên thay vì buộc client suy ra mọi URI từ các mã định danh rời rạc.

Trong ví dụ, `links`, `self` và `shipment` là quy ước của hợp đồng minh họa. JSON thông thường không tự định nghĩa ý nghĩa của những tên này. API cần mô tả quan hệ liên kết, cách phân giải URI và các tương tác được hỗ trợ, hoặc dùng media type có quy ước phù hợp.

Trong REST, hypermedia còn có vai trò hướng dẫn các bước tương tác khả dụng qua biểu diễn. Chỉ thêm một trường `links` chưa đủ để kết luận một API đã đáp ứng toàn bộ các ràng buộc REST.

### Tập tài nguyên cũng có biểu diễn riêng

Một yêu cầu đọc tập đơn hàng có thể trả về:

```http
GET /orders?status=DRAFT&page=0&size=2 HTTP/1.1
Host: api.example.test
Accept: application/json
```

```json
{
  "items": [
    {
      "id": "ord_42",
      "status": "DRAFT"
    },
    {
      "id": "ord_43",
      "status": "DRAFT"
    }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "links": {
    "next": "/orders?status=DRAFT&page=1&size=2"
  }
}
```

Đây là biểu diễn của kết quả truy vấn trên tập đơn hàng, không phải biểu diễn đầy đủ của một đơn hàng riêng lẻ. Tham số truy vấn là một phần của URI; bộ lọc và phân trang giúp xác định kết quả được yêu cầu. API vẫn cần quy định rõ cách đánh số trang, thứ tự sắp xếp và cấu trúc phản hồi.

Biểu diễn tóm tắt trong danh sách có thể ít trường hơn biểu diễn chi tiết. Client không nên mặc định rằng mọi mục trong danh sách chứa đủ dữ liệu cho màn hình chi tiết.

## 10. Minh họa bằng Java/Spring

Ở phía server, có thể tách lớp xử lý HTTP khỏi dịch vụ nghiệp vụ và mô hình trả ra ngoài. Ví dụ dưới đây giả định một ứng dụng Spring MVC đã được cấu hình, dùng Java hỗ trợ `record` và có bộ chuyển đổi JSON. Các kiểu được trình bày gọn trong cùng đoạn mã để minh họa quan hệ; khi triển khai có thể tách chúng thành các tệp Java phù hợp.

```java
import java.net.URI;
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

record OrderResponse(
        String id,
        String status,
        long totalAmount,
        String currency,
        URI self
) {}

interface OrderQueryService {
    Optional<OrderResponse> findVisibleOrder(String orderId);
}

@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderQueryService orderQueryService;

    OrderController(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @GetMapping(
        value = "/{orderId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderResponse> getOrder(
            @PathVariable("orderId") String orderId) {
        OrderResponse response = orderQueryService
                .findVisibleOrder(orderId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order not found"
                ));

        return ResponseEntity.ok(response);
    }
}
```

Mối liên hệ giữa mã và mô hình:

| Thành phần trong mã | Ý nghĩa |
| --- | --- |
| `/orders/{orderId}` | Mẫu URI để định danh tài nguyên đơn hàng |
| `@GetMapping` | Ánh xạ tương tác đọc bằng `GET` |
| `OrderQueryService` | Ranh giới gọi nghiệp vụ và lấy dữ liệu phù hợp |
| `OrderResponse` | Mô hình biểu diễn công khai cho trường hợp đọc đơn |
| Bộ chuyển đổi JSON của Spring | Mã hóa đối tượng phản hồi thành body JSON |
| `ResponseEntity.ok(...)` | Tạo phản hồi thành công với mã `200` |

Đoạn mã chưa cung cấp phần triển khai `OrderQueryService`. Phần triển khai phải phối hợp với cơ chế xác thực, kiểm tra quyền và nguồn dữ liệu thực tế; tên `findVisibleOrder` không tự tạo ra các kiểm tra đó. Cách tạo body lỗi thống nhất cũng cần được thiết kế riêng.

Trường `totalAmount` dùng số nguyên trong ví dụ với hợp đồng biểu diễn tiền theo đơn vị đã quy định cho VND. Với hệ thống đa tiền tệ, phải mô tả rõ đơn vị và quy tắc tính, không suy ra chúng chỉ từ kiểu `long`.

Không trả trực tiếp entity lưu trữ ra ngoài giúp hạn chế việc vô tình công khai cột nội bộ hoặc để thay đổi cấu trúc cơ sở dữ liệu làm thay đổi hợp đồng API. DTO là một lựa chọn triển khai cho mục tiêu đó, không phải một điều kiện riêng của REST.

## 11. Những nhầm lẫn dễ làm thiết kế lệch hướng

### “Resource chính là JSON nhận được”

JSON là một biểu diễn. Tài nguyên có danh tính và trạng thái trong mô hình nghiệp vụ; có thể được mô tả bằng các dạng dữ liệu khác.

### “URI phải cho biết controller hoặc bảng nào đang xử lý”

URI là định danh công khai. Việc đổi tên controller, chia lại dịch vụ hoặc thay cơ sở dữ liệu không nên buộc client thay URI nếu hợp đồng công khai không đổi.

### “Client gửi trường nào thì server lưu trường đó”

Request là đề nghị tương tác theo hợp đồng. Server quyết định trường nào được ghi, trường nào tự tính và thao tác nào hợp lệ. Ví dụ, người mua không được tự xác nhận đã thanh toán bằng cách sửa JSON.

### “HTTP 200 nghĩa là dữ liệu vẫn mới ở mọi thời điểm sau đó”

Biểu diễn phản ánh dữ liệu tại thời điểm được tạo hoặc được lấy từ cache theo chính sách. Một client khác có thể cập nhật tài nguyên ngay sau đó. Cache validator và cơ chế kiểm soát cập nhật đồng thời giúp xử lý vấn đề này khi cần.

### “Client và server luôn là hai chương trình cố định”

Vai trò được xác định theo từng tương tác. Một dịch vụ nhận request từ bên ngoài vẫn có thể đóng vai client khi gọi hệ thống khác.

### “Có endpoint HTTP trả JSON thì đã đủ mọi đặc tính của REST”

HTTP và JSON là phương tiện triển khai phổ biến. Khi đánh giá REST còn cần xem cách tổ chức giao diện thống nhất, tính stateless, khả năng cache, phân lớp và cách biểu diễn hỗ trợ tương tác. Bài này tập trung vào các khái niệm đầu vào để hiểu những ràng buộc đó.

## 12. Bài tập tự thực hành

Giả sử cần thiết kế API thư viện với thao tác xem một cuốn sách và tạo lượt mượn.

1. Đề xuất URI cho cuốn sách, tập lượt mượn và một lượt mượn cụ thể.
2. Viết một biểu diễn JSON tóm tắt cho cuốn sách và một biểu diễn chi tiết có thêm thông tin.
3. Xác định client và server khi ứng dụng thư viện gọi dịch vụ mượn sách, rồi dịch vụ mượn sách gọi dịch vụ thông báo.
4. Viết request tạo lượt mượn và response thành công có `Location`.
5. Chỉ ra những trường client được gửi và những trường server phải tự quyết định.
6. Giải thích vì sao thay `status` trong JSON trên trình duyệt chưa làm lượt mượn trên server thay đổi.

Một hướng triển khai để đối chiếu:

- Cuốn sách: `/books/book_7`.
- Tập lượt mượn: `/loans`; lượt mượn mới: `/loans/loan_12`.
- `POST /loans` nhận mã sách và thông tin đầu vào được hợp đồng cho phép; server xác định người mượn từ ngữ cảnh xác thực khi thích hợp, kiểm tra điều kiện và cấp mã lượt mượn.
- Khi tạo thành công, phản hồi có thể là `201 Created`, `Location: /loans/loan_12` và biểu diễn lượt mượn.
- Client không được tự quyết định tình trạng sách còn khả dụng hay kết quả cấp quyền mượn chỉ bằng một thuộc tính trong request.

Khi đọc hoặc thiết kế một endpoint, hãy tự diễn đạt trọn vẹn: **client nào đang gửi phương thức gì đến tài nguyên nào, body mang ý nghĩa gì, server kiểm tra điều kiện nào và phản hồi mô tả kết quả ra sao**. Nếu diễn đạt rõ được câu đó, mối liên hệ giữa tài nguyên, biểu diễn, client và server đã trở nên cụ thể.