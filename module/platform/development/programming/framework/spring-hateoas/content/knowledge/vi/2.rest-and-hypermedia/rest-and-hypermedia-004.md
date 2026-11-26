# Stateless interaction

Trong REST, **stateless interaction** (tương tác phi trạng thái) là ràng buộc yêu cầu mỗi request từ client phải mang đủ thông tin để server hiểu và xử lý request đó. Server không dựa vào một phiên hội thoại được lưu từ request trước của chính client để diễn giải request hiện tại.

Ràng buộc này ảnh hưởng trực tiếp đến cách thiết kế API. Client gửi thông tin xác thực, tham số và dữ liệu cần thiết trong từng request. Server xử lý request dựa trên thông tin đó cùng trạng thái tài nguyên mà server quản lý. Khi trả về representation, server có thể cung cấp các liên kết hypermedia để client khám phá bước tiếp theo. Client theo các liên kết này trong những request độc lập tiếp theo.

## 1. Hiểu đúng khái niệm stateless

Stateless không có nghĩa là server không lưu dữ liệu. Một API quản lý đơn hàng vẫn phải lưu đơn hàng, trạng thái thanh toán, lịch sử giao dịch và các dữ liệu nghiệp vụ khác. Những dữ liệu đó là **trạng thái tài nguyên** (*resource state*), thuộc về miền nghiệp vụ và được lưu trữ lâu dài hoặc trong khoảng thời gian cần thiết.

Điều REST hạn chế là trạng thái phiên của client (*client session state*): thông tin tạm thời về cuộc trao đổi giữa client và server mà server phải giữ để hiểu request tiếp theo. Ví dụ, nếu server ghi nhớ rằng một client đang ở bước thứ ba của quy trình tạo đơn hàng, rồi xử lý request tiếp theo dựa vào thông tin trong session thay vì dữ liệu request, tương tác đó phụ thuộc vào trạng thái phiên phía server.

Có thể phân biệt hai nhóm trạng thái như sau:

| Loại trạng thái | Nơi quản lý thường gặp | Ví dụ |
| --- | --- | --- |
| Trạng thái tài nguyên | Server | Đơn hàng `42` đang ở trạng thái `PENDING`; tài khoản có số dư hiện tại |
| Trạng thái ứng dụng của client (*application state*) | Client | Client đang xem đơn hàng `42`, vừa theo liên kết `cancel`, hoặc đang hiển thị bước xác nhận |
| Trạng thái phiên hội thoại | Không lưu ở server để làm ngữ cảnh bắt buộc cho request kế tiếp | Server nhớ client đã chọn địa chỉ giao hàng ở request trước dù request hiện tại không gửi lại thông tin đó |

Client có thể lưu trạng thái điều hướng hoặc dữ liệu giao diện ở phía mình. Server vẫn lưu và cập nhật tài nguyên nghiệp vụ. Vì vậy, một ứng dụng REST hoàn toàn có thể quản lý dữ liệu rất phức tạp mà vẫn tuân thủ ràng buộc stateless.

## 2. Mỗi request phải tự cung cấp ngữ cảnh cần thiết

Giả sử client muốn đọc đơn hàng `42`. Một request có thể chứa định danh tài nguyên, thông tin xác thực và kiểu representation mà client chấp nhận:

```http
GET /orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/hal+json
```

Server xác thực request, đọc trạng thái đơn hàng từ kho dữ liệu và trả về representation. Nếu client tiếp tục hủy đơn, request hủy cũng phải tự mang thông tin xác thực và mọi dữ liệu đầu vào cần thiết:

```http
POST /orders/42/cancellation HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/hal+json
```

Request thứ hai không được hiểu là “hãy hủy đơn mà tôi đã chọn trong phiên trước”. Nó chỉ rõ tài nguyên cần thao tác qua URI và mang thông tin cần thiết để server xác thực, kiểm tra điều kiện nghiệp vụ rồi thực hiện hành động.

Với một request thực tế, ngữ cảnh cần thiết có thể gồm:

- Phương thức HTTP và URI xác định thao tác, tài nguyên đích.
- Thông tin xác thực hoặc thông tin định danh cần cho việc kiểm soát truy cập.
- Header như `Accept`, `Content-Type`, mã tương quan hoặc điều kiện như `If-Match` khi API sử dụng chúng.
- Query parameter, path variable và body cần thiết cho thao tác.

Không phải request nào cũng cần tất cả các thành phần trên. Nguyên tắc là server không cần truy xuất một session hội thoại để bổ sung dữ liệu bắt buộc còn thiếu cho request.

## 3. Stateless kết hợp với hypermedia

Stateless và hypermedia giải quyết hai vấn đề liên quan nhưng khác nhau:

- Stateless quy định server xử lý mỗi request độc lập, dựa trên ngữ cảnh có trong request và trạng thái tài nguyên.
- Hypermedia giúp client khám phá các tài nguyên và hành động có thể thực hiện thông qua liên kết được gửi trong representation.

Ví dụ, server trả về đơn hàng đang chờ xử lý cùng liên kết `self` và `cancel`:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Client đọc quan hệ `cancel` để biết representation hiện tại cung cấp đường dẫn cho hành động hủy. Client gửi request đến URI đó và tự cung cấp thông tin xác thực. Server vẫn phải kiểm tra quyền của người gọi, trạng thái mới nhất của đơn hàng và quy tắc nghiệp vụ trước khi chấp nhận thao tác.

Sau khi hủy thành công, server có thể trả về representation mới với `status` là `CANCELLED` và không còn liên kết `cancel`. Tập liên kết thay đổi theo trạng thái tài nguyên. Client có thể dựa vào representation mới để biết các bước tiếp theo mà không cần server ghi nhớ client đã đi qua những màn hình nào.

Liên kết hypermedia không phải session token. Nó giúp client điều hướng đến tài nguyên hoặc hành động; bản thân liên kết không thay thế thông tin xác thực, không cấp quyền và không đảm bảo hành động sẽ thành công khi client gửi request. Trạng thái tài nguyên có thể đã thay đổi giữa lúc server phát liên kết và lúc client sử dụng liên kết.

Ngoài ra, một liên kết HAL cơ bản chủ yếu cung cấp URI và quan hệ liên kết. Nó không nhất thiết mô tả đầy đủ HTTP method hoặc cấu trúc dữ liệu đầu vào. Nếu client cần khám phá cả chi tiết thao tác, có thể dùng affordance của Spring HATEOAS và kiểu biểu diễn hỗ trợ metadata đó, hoặc cung cấp hợp đồng API tương ứng. Không nên giả định mọi liên kết HAL đều tự mô tả đầy đủ một biểu mẫu hay request body.

## 4. Biểu diễn tài nguyên stateless bằng Spring HATEOAS

Spring HATEOAS cung cấp các kiểu mô hình để gắn liên kết vào representation. `RepresentationModel` là lớp cơ sở cho mô hình representation tùy chỉnh; `EntityModel<T>` bọc một đối tượng; `CollectionModel<T>` biểu diễn một tập hợp. Các kiểu này giúp controller trả dữ liệu cùng liên kết trong một cấu trúc thống nhất.

Ví dụ sau biểu diễn một đơn hàng. Giả sử ứng dụng đã có `Order`, `OrderView`, `OrderService` và các quy tắc nghiệp vụ tương ứng:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
    EntityModel<OrderView> get(@PathVariable UUID id) {
        return toModel(orderService.getRequired(id));
    }

    @PostMapping("/{id}/cancellation")
    EntityModel<OrderView> cancel(@PathVariable UUID id) {
        return toModel(orderService.cancel(id));
    }

    private EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(OrderView.from(order));

        model.add(linkTo(methodOn(OrderController.class)
                .get(order.getId())).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        return model;
    }
}
```

Phương thức `toModel` tạo representation từ trạng thái đơn hàng hiện tại. `linkTo(methodOn(...))` tạo URI dựa trên mapping của controller, nhờ đó việc đổi cấu trúc đường dẫn có thể được phản ánh qua mapping thay vì phải ghép chuỗi URI thủ công. `withSelfRel()` gắn quan hệ `self`; `withRel("cancel")` gắn quan hệ nghiệp vụ cho hành động hủy.

Liên kết `cancel` chỉ được thêm khi quy tắc nghiệp vụ cho phép hủy tại thời điểm tạo representation. Khi request hủy đến server, `OrderService.cancel` vẫn phải kiểm tra lại điều kiện. Việc ẩn một liên kết giúp client hiểu các hành động đang khả dụng, còn kiểm tra quyền và tính hợp lệ ở server mới là lớp bảo vệ thực sự.

Khi ứng dụng cấu hình Spring HATEOAS để xuất HAL, representation có thể được tuần tự hóa thành JSON với dữ liệu tài nguyên và mục `_links`, như ví dụ ở phần trước. Client có thể yêu cầu kiểu nội dung HAL qua `Accept: application/hal+json`. Cấu hình cụ thể phụ thuộc vào cách ứng dụng tích hợp Spring HATEOAS và content negotiation.

Ví dụ này không dùng `HttpSession` để lưu đơn hàng đang được chọn hoặc bước hiện tại của client. Mỗi lần gọi `get` hay `cancel`, controller lấy tài nguyên theo định danh trong request. Các liên kết được tạo từ trạng thái đơn hàng vừa đọc.

## 5. Những nhầm lẫn thường gặp

**“Stateless nghĩa là server không lưu dữ liệu.”** Không đúng. Server vẫn lưu trạng thái tài nguyên và dữ liệu nghiệp vụ. Điều cần tránh là phụ thuộc vào trạng thái phiên hội thoại của client để xử lý request kế tiếp.

**“Dùng cookie hoặc JWT thì API chắc chắn stateless.”** Không thể kết luận chỉ từ loại token. Cookie chứa mã session trỏ đến dữ liệu phiên phía server vẫn tạo ra phụ thuộc session. JWT có thể hỗ trợ xác thực không cần session nếu server tự xác minh token, nhưng hệ thống vẫn có thể tra cứu trạng thái thu hồi, quyền hoặc dữ liệu khác ở server. Hãy xem request có tự mang đủ ngữ cảnh và server có phụ thuộc vào session hay không.

**“Client đã nhận liên kết thì có quyền thực hiện hành động.”** Không đúng. Liên kết thể hiện hành động mà representation hiện tại quảng bá. Server phải xác thực người gọi, kiểm tra phân quyền và kiểm tra lại điều kiện nghiệp vụ cho mỗi request.

**“Stateless đồng nghĩa với idempotent.”** Đây là hai khái niệm khác nhau. Stateless nói về nơi lưu ngữ cảnh tương tác; idempotent nói về kết quả khi thực hiện cùng một request nhiều lần. Ví dụ, `PUT` thường được thiết kế idempotent, còn `POST` tạo giao dịch có thể tạo nhiều kết quả nếu client gửi lại request. Với thao tác cần chống xử lý trùng, API có thể dùng idempotency key hoặc mã yêu cầu và lưu dấu vết xử lý trong dữ liệu nghiệp vụ.

**“Server có thể tin rằng trạng thái không đổi sau khi gửi liên kết.”** Không đúng. Một liên kết `cancel` có thể được phát ra khi đơn hàng còn `PENDING`, nhưng đơn hàng có thể đã được thanh toán hoặc giao đi trước khi client gọi liên kết. Server cần kiểm tra lại trạng thái mới nhất và trả lỗi phù hợp nếu chuyển trạng thái không còn hợp lệ.

## 6. Lợi ích và chi phí thiết kế

Stateless giúp mỗi request có thể được định tuyến đến bất kỳ instance phù hợp nào trong cụm server mà không cần khôi phục session hội thoại từ một instance cụ thể. Điều này hỗ trợ mở rộng ngang, cân bằng tải, xử lý lỗi và quan sát request độc lập. Cache cũng dễ áp dụng hơn với các response phù hợp vì server không phải ghép kết quả với trạng thái phiên ẩn của client.

Đổi lại, request có thể phải mang lại thông tin xác thực và ngữ cảnh cần thiết ở mỗi lần gọi. Server phải thiết kế cơ chế xác thực, phân quyền, quản lý token và xử lý chuyển trạng thái rõ ràng. Client cũng cần lưu trạng thái điều hướng của mình và làm việc với các representation mới nhận được. Stateless không tự động làm API nhanh hơn hoặc bảo đảm mọi thao tác có thể retry an toàn; những đặc tính đó cần được thiết kế riêng.

## 7. Checklist khi thiết kế API Spring HATEOAS

- Mỗi endpoint nhận đủ định danh, dữ liệu đầu vào và thông tin xác thực cần thiết qua request.
- Controller truy xuất tài nguyên theo định danh request thay vì dựa vào “tài nguyên hiện tại” được lưu trong session.
- Server lưu trạng thái nghiệp vụ dưới dạng tài nguyên và kiểm tra điều kiện chuyển trạng thái ở mỗi thao tác.
- Representation dùng `EntityModel`, `CollectionModel` hoặc mô hình kế thừa `RepresentationModel` phù hợp, đồng thời cung cấp `self` và các liên kết có ý nghĩa.
- Các liên kết hành động phản ánh trạng thái tài nguyên tại thời điểm tạo response; endpoint vẫn kiểm tra quyền và điều kiện khi được gọi.
- Client theo liên kết nhận được để điều hướng và gửi lại thông tin xác thực trong request tiếp theo.
- Các thao tác có thể được gửi lại được thiết kế với ngữ nghĩa HTTP phù hợp; thao tác tạo giao dịch cần cơ chế chống trùng nếu nghiệp vụ yêu cầu.

Khi kiểm thử, hãy gọi một endpoint bằng request độc lập có đầy đủ thông tin cần thiết, sau đó gọi một liên kết trong response bằng request mới. Thử thực hiện request thứ hai từ một kết nối hoặc instance server khác nếu môi trường cho phép. Kết quả đúng không phụ thuộc vào việc request đầu tiên đã tạo một session hội thoại ở server; nó phụ thuộc vào request hiện tại, quyền của người gọi và trạng thái tài nguyên thực tế.
