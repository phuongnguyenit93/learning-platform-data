# Giới hạn của HATEOAS

HATEOAS (Hypermedia as the Engine of Application State) đưa các liên kết và thông tin điều hướng vào biểu diễn tài nguyên. Thay vì phải biết trước mọi URI, client có thể bắt đầu từ một điểm vào đã thỏa thuận, đọc biểu diễn máy chủ trả về rồi đi theo liên kết phù hợp với trạng thái hiện tại.

Spring HATEOAS hỗ trợ cách thiết kế này bằng các kiểu như `RepresentationModel`, `EntityModel`, `CollectionModel`, `Link` và các bộ dựng liên kết cho Spring MVC. Tuy nhiên, thư viện giúp tạo biểu diễn hypermedia; nó không tự giải quyết mọi vấn đề của thiết kế API. Hiểu rõ giới hạn giúp chọn đúng nơi áp dụng HATEOAS, tránh tạo thêm độ phức tạp mà client không sử dụng được.

## 1. HATEOAS giải quyết vấn đề gì?

Một API chỉ trả dữ liệu thường buộc client biết trước cấu trúc đường dẫn và quy trình gọi. Ví dụ, sau khi đọc đơn hàng, ứng dụng có thể tự ghép `/orders/{id}/cancel` để hủy đơn. Khi máy chủ thay đổi cấu trúc URI, client phải được cập nhật dù quy tắc nghiệp vụ không đổi.

Với HATEOAS, máy chủ trả về tài nguyên cùng những liên kết có ý nghĩa trong ngữ cảnh đó. Client đọc liên kết `self` để nhận diện tài nguyên, `next` để chuyển trang, hoặc một quan hệ nghiệp vụ như `cancel` để biết có đường dẫn liên quan đến thao tác hủy. Máy chủ có thể thay đổi URI đích mà không bắt client tự ghép lại đường dẫn, miễn là client thực sự dựa vào liên kết và ý nghĩa của quan hệ.

HATEOAS hữu ích nhất khi API có nhiều trạng thái, các bước xử lý phụ thuộc vào trạng thái hiện tại, hoặc máy chủ cần kiểm soát những khả năng mà client có thể khám phá tại mỗi thời điểm.

## 2. Những điều HATEOAS không tự bảo đảm

| Kỳ vọng dễ nhầm | Thực tế |
| --- | --- |
| Client không cần biết gì về API | Client vẫn cần biết điểm vào ban đầu, media type, cách đọc biểu diễn và ý nghĩa của các quan hệ mà nó quan tâm. |
| Có liên kết là client biết cách thực hiện thao tác | Một liên kết HAL thông thường chủ yếu cung cấp quan hệ và URI. Nó không nhất thiết mô tả HTTP method, cấu trúc request body, kiểu dữ liệu hay điều kiện tiền đề. |
| Server đổi URI thì mọi client đều tự thích nghi | Điều này chỉ đúng với client đi theo liên kết và không phụ thuộc vào URI cố định. Client bỏ qua liên kết vẫn bị ràng buộc với cấu trúc cũ. |
| Liên kết bảo đảm thao tác được phép | Liên kết không thay thế xác thực, phân quyền hoặc kiểm tra trạng thái ở phía server. |
| HATEOAS thay thế tài liệu API và kiểm thử | Client vẫn cần hợp đồng về media type, quan hệ, dữ liệu và lỗi; đội phát triển vẫn cần kiểm thử hành vi. |
| HATEOAS loại bỏ nhu cầu quản lý phiên bản | Thay đổi ý nghĩa quan hệ, cấu trúc biểu diễn hoặc quy tắc nghiệp vụ vẫn có thể phá vỡ client. |

Các giới hạn này không làm HATEOAS mất giá trị. Chúng xác định phần việc mà hypermedia đảm nhiệm và phần việc vẫn thuộc về hợp đồng API, bảo mật, vận hành và thiết kế client.

## 3. Liên kết không phải là một đặc tả thao tác đầy đủ

Trong HAL, liên kết thường có dạng một quan hệ (`rel`) gắn với một `href`, đôi khi có thêm các thuộc tính như `type`, `title` hoặc `hreflang`. Quan hệ cho biết liên kết có ý nghĩa gì trong biểu diễn. Nhưng một liên kết như `cancel` không tự nói rõ client phải gửi `POST`, gửi trường nào trong body, có cần `If-Match` hay không, hoặc nhận những mã lỗi nào.

Ví dụ, biểu diễn HAL có thể chứa:

```json
{
  "id": "8b3b1b2a-9a77-4d8a-a5d8-9fd57d3b0b4a",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/8b3b1b2a-9a77-4d8a-a5d8-9fd57d3b0b4a"
    },
    "cancel": {
      "href": "/orders/8b3b1b2a-9a77-4d8a-a5d8-9fd57d3b0b4a/cancel"
    }
  }
}
```

Client có thể nhận ra đơn hàng có một liên kết mang quan hệ `cancel`, nhưng HAL thuần không mô tả đầy đủ cách gửi yêu cầu hủy. Hai bên vẫn cần thống nhất hợp đồng cho quan hệ này hoặc dùng một định dạng có thể biểu diễn biểu mẫu và thao tác phong phú hơn. Trong hệ sinh thái Spring HATEOAS, có thể tìm hiểu affordance và HAL-FORMS khi cần mô tả thêm khả năng tương tác. OpenAPI vẫn có ích để công bố schema request/response, mã lỗi và chi tiết kỹ thuật cho công cụ, kiểm thử hoặc client được sinh mã.

Tên quan hệ cũng cần có ngữ nghĩa ổn định. Các quan hệ chuẩn của IANA phù hợp với ý nghĩa phổ biến như `self` hoặc `next`. Quan hệ riêng của miền nghiệp vụ như `cancel`, `approve` hay `shipment` cần được định nghĩa rõ và dùng nhất quán. Nếu client chỉ dựa vào một chuỗi quan hệ tùy ý mà không có quy ước chung, hypermedia không giúp hai bên hiểu nhau.

## 4. Chi phí triển khai và bảo trì tăng lên

Để HATEOAS có ích, server phải tạo các liên kết đúng với tài nguyên và trạng thái nghiệp vụ. Khi API có nhiều loại tài nguyên, mỗi loại có các chuyển trạng thái và quan hệ riêng, phần xây dựng representation có thể trở nên dài và khó đồng nhất.

Spring HATEOAS cung cấp các cơ chế như `RepresentationModel`, `EntityModel`, `CollectionModel`, `WebMvcLinkBuilder` và `RepresentationModelAssembler` để tổ chức công việc này. Chúng giảm thao tác ghép URI thủ công và hỗ trợ tái sử dụng, nhưng không tự quyết định quy tắc nghiệp vụ nào làm một liên kết xuất hiện. Nhóm phát triển vẫn phải xác định điều kiện, giữ tên quan hệ ổn định và kiểm thử liên kết được phát ra.

Một API có ít endpoint, luồng cố định và client nội bộ được triển khai cùng nhịp có thể không thu được đủ lợi ích để bù chi phí này. Nếu thêm liên kết nhưng client vẫn gọi URL đã mã hóa cứng, hệ thống phải chịu thêm công việc tạo và duy trì liên kết mà không đạt được mục tiêu giảm phụ thuộc URI.

## 5. Ví dụ: liên kết phụ thuộc trạng thái trong Spring HATEOAS

Giả sử API quản lý đơn hàng. Đơn ở trạng thái `PENDING` có thể được hủy; đơn đã giao hoặc đã hủy thì không. Controller có thể thêm liên kết `cancel` chỉ khi nghiệp vụ cho phép:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderMapper orderMapper;

    OrderController(OrderService orderService, OrderMapper orderMapper) {
        this.orderService = orderService;
        this.orderMapper = orderMapper;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> getOrder(@PathVariable UUID id) {
        Order order = orderService.getRequired(id);
        EntityModel<OrderView> model = EntityModel.of(orderMapper.toView(order));

        model.add(linkTo(methodOn(OrderController.class).getOrder(id)).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancelOrder(id))
                    .withRel("cancel"));
        }

        return model;
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancelOrder(@PathVariable UUID id) {
        orderService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Đoạn mã giả định `Order`, `OrderView`, `OrderService` và `OrderMapper` là các kiểu của ứng dụng. `linkTo(methodOn(...))` tạo URI dựa trên mapping của controller, còn `EntityModel` gói dữ liệu đơn hàng cùng các liên kết. Điều kiện `canBeCancelled()` là quy tắc nghiệp vụ quyết định liên kết có xuất hiện hay không.

Ví dụ này thể hiện một lợi ích và một giới hạn cùng lúc:

- Client có thể khám phá rằng thao tác hủy hiện được công bố cho đơn hàng đó, thay vì tự suy ra từ chuỗi trạng thái.
- Client vẫn cần biết hợp đồng của quan hệ `cancel` để gửi `POST` đúng cách. Liên kết HAL cơ bản không tự cung cấp schema thao tác.
- Server vẫn phải kiểm tra quyền và trạng thái khi nhận `POST`. Trạng thái đơn có thể thay đổi sau khi client đọc biểu diễn; sự hiện diện của liên kết không phải giấy phép thực hiện thao tác.

Việc ẩn liên kết giúp client điều hướng theo trạng thái hiện được công bố, nhưng không thay thế kiểm tra ở endpoint. Hai yêu cầu có thể xảy ra cách nhau đủ lâu để dữ liệu thay đổi; do đó thao tác hủy phải được xác thực lại trong `OrderService` hoặc lớp nghiệp vụ tương ứng.

## 6. Tác động đến client, hiệu năng và cache

Client phải có khả năng phân tích media type và duyệt liên kết. Với client web linh hoạt, điều này có thể phù hợp. Với ứng dụng di động dùng SDK sinh từ OpenAPI, hệ thống tích hợp cũ hoặc client có mô hình dữ liệu cố định, việc hỗ trợ nhiều quan hệ và media type có thể làm tăng độ phức tạp. Một số client sẽ tiếp tục dùng endpoint cố định vì cách đó đơn giản hơn với nhu cầu của họ.

Mỗi liên kết bổ sung làm biểu diễn lớn hơn và có thể khiến server phải thực hiện thêm công việc để xác định những khả năng được phép công bố. Khi một collection chứa nhiều tài nguyên, số lượng liên kết có thể tăng nhanh. Cần chọn các liên kết có ích cho bước tiếp theo của client, tránh biến representation thành danh sách mọi endpoint có thể tồn tại.

Liên kết cũng có thể thay đổi theo người dùng, vai trò, trạng thái tài nguyên hoặc cấu hình. Điều này ảnh hưởng đến cache: hai người dùng đọc cùng một URI có thể nhận representation với các liên kết khác nhau. Chính sách cache phải phản ánh các yếu tố làm thay đổi representation, chẳng hạn thông qua `Cache-Control`, `Vary` và chiến lược cache phù hợp với dữ liệu riêng tư. Không nên cache công khai một representation có chứa các liên kết được cá nhân hóa theo quyền truy cập.

## 7. HATEOAS không phải là cơ chế bảo mật

Không đưa liên kết `delete` vào representation không có nghĩa endpoint xóa đã được bảo vệ. Client có thể tự gửi request đến URI mà nó biết hoặc đoán được. Tương tự, một liên kết `approve` được phát ra trước đó không bảo đảm người dùng còn quyền phê duyệt khi request đến server.

Server phải xác thực danh tính, kiểm tra quyền trên đúng tài nguyên và xác minh điều kiện nghiệp vụ ở mỗi request. Việc tạo liên kết theo quyền chỉ cải thiện khả năng khám phá và trải nghiệm client; nó không thay thế authorization tại endpoint. Với thao tác nhạy cảm, cần xem xét thêm kiểm soát đồng thời, điều kiện tiền đề và ghi nhận kiểm toán theo yêu cầu nghiệp vụ.

## 8. HATEOAS không loại bỏ thay đổi hợp đồng và quản lý phiên bản

Liên kết giúp tách client khỏi URI cụ thể, nhưng client vẫn phụ thuộc vào:

- Media type và cấu trúc representation mà nó phân tích.
- Tên, ý nghĩa và quy tắc xuất hiện của các relation mà nó sử dụng.
- Kiểu dữ liệu và ý nghĩa của các trường trong tài nguyên.
- Quy tắc thao tác, lỗi và điều kiện chuyển trạng thái.

Đổi URI đích thường ít ảnh hưởng hơn khi client đi theo liên kết. Ngược lại, đổi `rel="cancel"` thành một tên khác, thay đổi ý nghĩa của `cancel`, xóa trường client đang dùng hoặc thay đổi định dạng biểu diễn vẫn có thể gây lỗi. Vì vậy, quan hệ hypermedia và media type cũng là một phần của hợp đồng cần quản lý tương thích.

Khi thiết kế thay đổi, hãy xác định client đang dựa vào quan hệ nào, trường nào và media type nào. Có thể duy trì quan hệ cũ trong giai đoạn chuyển tiếp, bổ sung quan hệ mới hoặc công bố profile và tài liệu cập nhật. HATEOAS hỗ trợ tiến hóa API khi các quy ước được duy trì; nó không tự làm cho mọi thay đổi trở nên tương thích ngược.

## 9. Cách giảm chi phí và dùng HATEOAS đúng chỗ

Một số thực hành giúp tận dụng hypermedia mà không làm API quá nặng:

1. **Bắt đầu từ nhu cầu điều hướng của client.** Xác định điểm vào, các trạng thái và bước tiếp theo client cần khám phá. Chỉ phát ra những liên kết phục vụ các bước đó.
2. **Định nghĩa relation rõ ràng.** Dùng relation chuẩn khi đúng ngữ nghĩa; với relation riêng, thống nhất tên và ý nghĩa giữa server, client và tài liệu API.
3. **Tách logic tạo representation.** Dùng `RepresentationModelAssembler` hoặc các hàm tạo model dùng chung khi nhiều controller cần tạo cùng một kiểu liên kết. Đặt quy tắc nghiệp vụ trong lớp nghiệp vụ, không để việc dựng link trở thành nơi quyết định trạng thái.
4. **Chọn đúng media type.** HAL phù hợp cho liên kết và tài nguyên nhúng. Nếu client cần biết cách gửi biểu mẫu hoặc mô tả thao tác, đánh giá affordance và HAL-FORMS. Dùng OpenAPI bổ sung schema, mã lỗi và thông tin cần cho công cụ.
5. **Kiểm thử cả nội dung lẫn khả năng điều hướng.** Kiểm tra relation, URI, điều kiện xuất hiện và việc liên kết biến mất khi trạng thái không còn phù hợp. Tránh chỉ kiểm tra response có mã `200`.
6. **Bảo vệ endpoint độc lập với liên kết.** Kiểm tra xác thực, quyền và trạng thái trong mọi thao tác thay đổi dữ liệu.
7. **Đánh giá cache và kích thước response.** Chú ý representation thay đổi theo người dùng hoặc trạng thái; không phát quá nhiều liên kết không có giá trị với client.

## 10. Khi nào nên áp dụng?

| Bối cảnh | Định hướng |
| --- | --- |
| API công khai có nhiều loại client và URI có thể thay đổi | HATEOAS có thể giảm việc client phụ thuộc vào đường dẫn cố định, nếu client thực sự duyệt liên kết. |
| Quy trình nghiệp vụ có nhiều trạng thái và chuyển tiếp | Liên kết theo trạng thái giúp client khám phá bước hiện có thể thực hiện. |
| API có phân trang, quan hệ tài nguyên hoặc luồng khám phá | Các relation như `next`, `prev`, `self` và liên kết tài nguyên thường đem lại lợi ích rõ ràng. |
| API nội bộ nhỏ, client cố định và endpoint ít thay đổi | Có thể dùng REST đơn giản cùng tài liệu hợp đồng; chỉ thêm hypermedia khi có nhu cầu cụ thể. |
| Client cần schema thao tác chặt chẽ hoặc SDK sinh mã | Kết hợp hypermedia với OpenAPI hoặc định dạng affordance phù hợp; không kỳ vọng một liên kết HAL thay thế toàn bộ schema. |

Không có quy tắc rằng mọi API REST đều phải triển khai HATEOAS ở cùng mức độ. Có thể áp dụng chọn lọc: dùng liên kết cho phân trang, điều hướng tài nguyên hoặc các bước nghiệp vụ có trạng thái; giữ hợp đồng tĩnh cho phần mà client cần schema rõ ràng và ổn định.

## 11. Danh sách kiểm tra khi thiết kế

Trước khi đưa HATEOAS vào một API Spring, hãy tự trả lời:

- Client bắt đầu khám phá API từ URI và media type nào?
- Client có thực sự đi theo liên kết được trả về hay vẫn ghép URI thủ công?
- Mỗi relation có tên và ý nghĩa được thống nhất không?
- Client có đủ thông tin để thực hiện thao tác, gồm method, body, kiểu dữ liệu và điều kiện cần thiết không?
- Liên kết có được tạo dựa trên trạng thái nghiệp vụ hiện tại không?
- Endpoint có tự kiểm tra quyền và trạng thái khi request đến không?
- Các liên kết có làm response quá lớn hoặc gây vấn đề cache theo người dùng không?
- Kiểm thử có xác nhận cả relation được công bố và relation không được công bố trong từng trạng thái không?
- Thay đổi relation, media type và trường dữ liệu có được xem là thay đổi hợp đồng API không?

HATEOAS phát huy tác dụng khi server và client cùng tuân theo một hợp đồng hypermedia rõ ràng. Spring HATEOAS giúp xây dựng hợp đồng đó trong ứng dụng Spring, còn chất lượng cuối cùng phụ thuộc vào cách nhóm định nghĩa relation, công bố khả năng, bảo vệ thao tác và kiểm thử các luồng điều hướng.
