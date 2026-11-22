# Controller diễn giải ý định từ đầu vào người dùng

Trong kiến trúc Model–View–Controller (MVC), Controller là điểm tiếp nhận tương tác từ bên ngoài ứng dụng. Nó nhận request hoặc hành động của người dùng, xác định use case tương ứng, chuyển dữ liệu đầu vào thành một yêu cầu có cấu trúc, gọi tầng ứng dụng và chọn phản hồi phù hợp. Có thể xem Controller như bộ chuyển đổi giữa ngôn ngữ của giao thức giao tiếp và ngôn ngữ của ứng dụng.

Người dùng gửi dữ liệu qua URL, query parameter, form, JSON, header hoặc phiên đăng nhập. Những dữ liệu này chỉ là biểu diễn bên ngoài của ý định. Controller cần hiểu người dùng đang muốn xem thông tin, tạo đơn hàng, cập nhật hồ sơ hay hủy một thao tác; đồng thời phải kiểm tra dữ liệu có thể chuyển đổi và hợp lệ ở ranh giới request hay không. Các quy tắc nghiệp vụ quyết định hành động có được phép thực hiện vẫn thuộc Model và tầng nghiệp vụ.

## 1. Từ dữ liệu đầu vào đến ý định của ứng dụng

Giả sử người dùng muốn đặt mua hai sản phẩm có mã 42 và giao đến một địa chỉ cụ thể. Trình duyệt có thể gửi:

~~~http
POST /orders
Content-Type: application/json

{
  "productId": 42,
  "quantity": 2,
  "deliveryAddress": "12 Nguyen Hue, Ho Chi Minh City"
}
~~~

Request chứa các giá trị do client cung cấp. Nó chưa phải là một lệnh nghiệp vụ hoàn chỉnh. Ứng dụng còn cần xác định đây là use case tạo đơn hàng, ai đang thực hiện, sản phẩm có tồn tại và được bán hay không, số lượng có đáp ứng quy tắc đặt hàng không, và địa chỉ giao hàng có được phép sử dụng hay không.

Controller đảm nhận phần chuyển đổi ở ranh giới:

1. Nhận biết endpoint và phương thức HTTP mà người dùng gọi.
2. Đọc và chuyển đổi dữ liệu từ request thành kiểu dữ liệu của ứng dụng.
3. Kiểm tra cấu trúc và những điều kiện đầu vào cơ bản.
4. Lấy danh tính hoặc ngữ cảnh người dùng đã được xác thực.
5. Tạo command hoặc tham số use case phù hợp.
6. Gọi tầng ứng dụng và chuyển kết quả thành phản hồi HTTP hoặc View.

Controller không nên tự quyết định quy tắc như giá cuối cùng, hạn mức mua, quyền sở hữu đơn hàng hoặc trạng thái chuyển tiếp hợp lệ. Những quy tắc này phải được thực thi ở tầng nghiệp vụ để mọi kênh gọi đều tuân theo cùng một chính sách.

## 2. Controller là bộ chuyển đổi ở ranh giới

Trong MVC, Controller kết nối tương tác bên ngoài với Model và View. Với ứng dụng web, ranh giới đó thường là HTTP:

~~~mermaid
flowchart LR
    U[Người dùng / Client] --> R[HTTP Request]
    R --> C[Controller]
    C --> I[Command hoặc Query]
    I --> A[Application Service]
    A --> M[Model và nghiệp vụ]
    M --> A
    A --> O[Kết quả use case]
    O --> C
    C --> V[View hoặc HTTP Response]
    V --> U
~~~

Controller biết chi tiết giao thức như route, HTTP method, path variable, query parameter, header, cookie, session và kiểu phản hồi. Tầng ứng dụng nên nhận một yêu cầu rõ nghĩa như CreateOrderCommand hoặc FindProductQuery, thay vì phải phụ thuộc vào HttpServletRequest, tên trường form hoặc cấu trúc JSON.

Sự phân tách này cho phép cùng một use case được gọi từ nhiều giao diện. Ví dụ, website có thể gọi CreateOrderCommand qua form HTML, ứng dụng di động gọi qua JSON API, còn một tác vụ nội bộ gọi trực tiếp application service. Quy tắc tạo đơn hàng vẫn được dùng chung.

## 3. Nhận biết ý định qua route và phương thức HTTP

Đối với API và ứng dụng web, ý định thường được biểu đạt trước hết bằng route và HTTP method. Dữ liệu trong request cung cấp các tham số để thực hiện ý định đó.

| Biểu diễn request | Ý định thường gặp | Ví dụ |
|---|---|---|
| GET /products/42 | Đọc một tài nguyên | Xem sản phẩm có mã 42 |
| GET /products?keyword=java | Tìm kiếm hoặc lọc | Tìm sản phẩm theo từ khóa |
| POST /orders | Tạo tài nguyên hoặc thực hiện một hành động | Tạo đơn hàng |
| PUT /profiles/7 | Thay thế biểu diễn của tài nguyên | Cập nhật toàn bộ hồ sơ |
| PATCH /profiles/7 | Thay đổi một phần tài nguyên | Cập nhật số điện thoại |
| DELETE /cart/items/42 | Xóa tài nguyên hoặc quan hệ | Bỏ sản phẩm khỏi giỏ hàng |

Đây là quy ước thiết kế phổ biến, không phải cách suy luận tuyệt đối từ tên URL. Hợp đồng API cần định nghĩa rõ hành vi của từng endpoint. Controller ánh xạ route và method vào một handler cụ thể; không nên cố đoán hành động từ một chuỗi dữ liệu tùy ý khi endpoint đã có thể biểu đạt hành động một cách tường minh.

Các phương thức HTTP cũng mang ngữ nghĩa quan trọng:

- GET dùng để đọc và không nên tạo thay đổi nghiệp vụ có chủ đích.
- POST thường dùng để tạo tài nguyên hoặc gửi một lệnh xử lý.
- PUT thường thay thế toàn bộ trạng thái có thể cập nhật của tài nguyên và được thiết kế idempotent.
- PATCH cập nhật một phần theo hợp đồng đã công bố.
- DELETE yêu cầu xóa tài nguyên hoặc mối quan hệ.

Thiết kế đúng method giúp trình duyệt, proxy, cache, client API và người bảo trì hiểu được ý định của request.

## 4. Đọc dữ liệu từ các vị trí khác nhau của request

Một request có thể chứa nhiều nhóm dữ liệu. Controller cần biết mỗi nhóm đại diện cho điều gì và dùng đúng cơ chế binding.

| Nguồn đầu vào | Cách dùng | Spring MVC thường dùng |
|---|---|---|
| Path variable | Định danh tài nguyên hoặc phần của route | @PathVariable |
| Query parameter | Tìm kiếm, lọc, sắp xếp, phân trang | @RequestParam |
| Form field | Dữ liệu người dùng nhập trong biểu mẫu | @ModelAttribute |
| Request body JSON/XML | Nội dung của lệnh hoặc tài nguyên | @RequestBody |
| Header | Metadata như loại nội dung hoặc thông tin điều kiện | @RequestHeader |
| Cookie/session | Ngữ cảnh phiên làm việc | Cơ chế session hoặc cookie phù hợp |

Ví dụ:

~~~java
@GetMapping("/products/{id}")
public String detail(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean showReviews,
        Model uiModel
) {
    // Dùng id để lấy sản phẩm; showReviews điều khiển dữ liệu phụ cần tải.
    return "products/detail";
}
~~~

Trong ví dụ, id xác định sản phẩm, còn showReviews là một tùy chọn của truy vấn. Controller có thể dùng chúng để tạo query hoặc gọi service. Việc một sản phẩm có được phép xem hay không vẫn phải được kiểm tra bởi tầng có trách nhiệm về quyền và nghiệp vụ.

Không phải mọi dữ liệu client gửi đều đáng tin. Giá sản phẩm, vai trò người dùng, trạng thái thanh toán hoặc chủ sở hữu tài nguyên không nên được lấy làm sự thật chỉ vì chúng xuất hiện trong form hay JSON. Những dữ liệu có thẩm quyền phải được xác định ở máy chủ.

## 5. Chuyển đổi và xác thực đầu vào

Controller thường tham gia hai lớp kiểm tra ở ranh giới:

- **Chuyển đổi và kiểm tra cấu trúc:** dữ liệu có thể được chuyển thành kiểu cần thiết không, trường bắt buộc có mặt không, định dạng có đúng không.
- **Kiểm tra nghiệp vụ:** hành động có hợp lệ trong trạng thái hiện tại và với người dùng hiện tại không.

Ví dụ, chuỗi abc không thể chuyển thành số lượng kiểu integer; đây là lỗi chuyển đổi đầu vào. Số lượng -3 có thể chuyển thành integer nhưng vi phạm điều kiện đầu vào. Một số lượng 3 vẫn có thể bị từ chối vì kho chỉ còn một sản phẩm; đây là quy tắc nghiệp vụ.

Không nên gom mọi loại kiểm tra vào Controller. Controller có thể dùng Bean Validation để phát hiện dữ liệu sai định dạng hoặc thiếu trường; application service và Model phải bảo vệ các bất biến nghiệp vụ, kể cả khi use case được gọi từ một nơi khác.

## 6. Ví dụ Spring MVC: diễn giải request tạo đơn hàng

Giả sử API nhận yêu cầu tạo đơn hàng. Ta định nghĩa DTO ở ranh giới để thể hiện đúng những trường client được phép gửi:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotNull Long productId,
        @NotNull @Min(1) Integer quantity,
        @NotBlank String deliveryAddress
) {
}
~~~

Đây là hợp đồng đầu vào của HTTP API. Nó không phải entity lưu trữ và cũng không phải toàn bộ đối tượng Order trong miền nghiệp vụ.

Application service có thể nhận command riêng:

~~~java
public record CreateOrderCommand(
        long productId,
        int quantity,
        String deliveryAddress,
        long customerId
) {
}
~~~

Controller lấy thông tin người dùng đã được xác thực từ security context, ánh xạ request thành command và gọi service:

~~~java
import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderApplicationService orderService;

    public OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal CurrentUser currentUser
    ) {
        CreateOrderCommand command = new CreateOrderCommand(
                request.productId(),
                request.quantity(),
                request.deliveryAddress(),
                currentUser.id()
        );

        OrderResult result = orderService.create(command);
        URI location = URI.create("/orders/" + result.orderId());

        return ResponseEntity
                .created(location)
                .body(new OrderResponse(result.orderId(), result.status()));
    }
}
~~~

Trong ví dụ, CurrentUser, OrderApplicationService, OrderResult và OrderResponse là kiểu dữ liệu của ứng dụng cần định nghĩa. Điểm quan trọng của luồng là:

1. @RequestBody chuyển JSON thành CreateOrderRequest.
2. @Valid kích hoạt kiểm tra các ràng buộc khai báo trên DTO.
3. Controller lấy customerId từ danh tính đã xác thực, không nhận nó từ JSON do client tự khai báo.
4. Controller tạo CreateOrderCommand thể hiện ý định nghiệp vụ.
5. Service kiểm tra quyền, sản phẩm, tồn kho, giá và các quy tắc đặt hàng trước khi tạo đơn.
6. Controller chuyển kết quả thành phản hồi HTTP, ở đây là 201 Created kèm URI của đơn hàng.

Nếu người dùng gửi quantity = 0, lỗi validation được phát hiện ở ranh giới. Nếu số lượng hợp lệ nhưng sản phẩm hết hàng, service có thể từ chối use case và Controller hoặc bộ xử lý ngoại lệ chuyển lỗi đó thành phản hồi phù hợp.

## 7. Controller với biểu mẫu HTML

Với ứng dụng render View phía máy chủ, Controller thường nhận form, trả lại trang khi có lỗi hoặc chuyển hướng sau khi xử lý thành công. BindingResult phải đứng ngay sau tham số được kiểm tra để Spring MVC cung cấp lỗi binding và validation cho handler.

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class RegistrationController {
    private final RegistrationService registrationService;

    public RegistrationController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @GetMapping("/register")
    public String showForm(Model uiModel) {
        uiModel.addAttribute("form", new RegistrationForm());
        return "registration/form";
    }

    @PostMapping("/register")
    public String register(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult bindingResult,
            RedirectAttributes redirectAttributes
    ) {
        if (bindingResult.hasErrors()) {
            return "registration/form";
        }

        registrationService.register(
                new RegisterUserCommand(form.getEmail(), form.getPassword())
        );
        redirectAttributes.addFlashAttribute(
                "message", "Đăng ký thành công"
        );
        return "redirect:/login";
    }
}
~~~

RegistrationForm là DTO dành cho biểu mẫu, còn RegisterUserCommand là yêu cầu của tầng ứng dụng. Sau khi binding và validation thành công, Controller chuyển các trường được cho phép sang command. Service vẫn phải mã hóa mật khẩu, kiểm tra email đã tồn tại và thực thi các quy tắc đăng ký.

Mẫu Post/Redirect/Get giúp trình duyệt chuyển sang một GET sau khi POST thành công, giảm nguy cơ gửi lại form khi người dùng refresh trang kết quả. Dữ liệu flash chỉ nên dùng cho thông báo ngắn trong lần chuyển hướng kế tiếp, không dùng để lưu trạng thái nghiệp vụ lâu dài.

## 8. Diễn giải ý định không đồng nghĩa với thực thi nghiệp vụ

Controller có thể nhận ra ý định từ route và dữ liệu đầu vào, nhưng không nên tự quyết định mọi điều kiện để thực hiện ý định đó.

Ví dụ với yêu cầu hủy đơn hàng:

- Controller xác định request POST /orders/42/cancel ánh xạ đến use case hủy đơn.
- Controller lấy mã đơn từ route và danh tính người dùng từ security context.
- Controller gọi CancelOrderCommand(orderId, actorId).
- Tầng nghiệp vụ kiểm tra đơn có tồn tại, người dùng có quyền hủy và trạng thái hiện tại có cho phép hủy không.
- Kết quả được chuyển thành phản hồi thành công hoặc lỗi phù hợp.

Một đơn hàng đã giao có thể không được hủy. Không nên chỉ ẩn nút “Hủy đơn” trên giao diện rồi cho rằng yêu cầu đã được bảo vệ. Client có thể gọi endpoint trực tiếp; use case phải kiểm tra lại mọi điều kiện quan trọng.

Nếu đầu vào có nhiều lựa chọn mơ hồ, hãy yêu cầu client gửi một giá trị rõ ràng theo hợp đồng. Ví dụ, bộ lọc trạng thái nên nhận enum hoặc mã trạng thái được công bố, thay vì suy luận trạng thái từ một đoạn mô tả tự do. Với đầu vào văn bản tự do có chủ đích, Controller vẫn cần chuyển nó thành một yêu cầu rõ ràng và kiểm tra giới hạn; việc hiểu ngữ nghĩa phức tạp có thể thuộc một dịch vụ chuyên biệt.

## 9. Thiết kế hợp đồng đầu vào an toàn

Controller là ranh giới tin cậy quan trọng. Một số nguyên tắc cần tuân thủ:

### Chỉ nhận những trường cần thiết

Không bind trực tiếp request vào entity có nhiều trường nội bộ. Nếu entity có role, ownerId, approved, price hoặc createdAt, client không nên được phép ghi các trường đó chỉ bằng cách thêm thuộc tính vào JSON.

Hãy dùng request DTO hoặc form DTO với allowlist trường rõ ràng. Sau đó tạo command chứa đúng dữ liệu use case cần.

### Xác định danh tính ở phía máy chủ

Thông tin người dùng hiện tại nên đến từ cơ chế xác thực đã được kiểm tra. Nếu client gửi customerId, accountId hoặc role, không mặc nhiên tin giá trị đó. Với một tài nguyên cụ thể, tầng nghiệp vụ cần kiểm tra người dùng có quyền thao tác trên tài nguyên đó không.

### Kiểm tra kiểu, giới hạn và định dạng

Giới hạn độ dài chuỗi, kích thước request, số lượng phần tử, kiểu dữ liệu và định dạng ngày giờ. Với phân trang, cần giới hạn kích thước trang tối đa. Với sort field, dùng danh sách thuộc tính được phép thay vì ghép trực tiếp chuỗi client vào truy vấn.

### Phân biệt dữ liệu thiếu và dữ liệu rỗng

Đối với cập nhật một phần, trường không xuất hiện có thể mang nghĩa “giữ nguyên”, trong khi trường xuất hiện với giá trị rỗng có thể mang nghĩa “xóa giá trị”. Hợp đồng PATCH cần định nghĩa rõ sự khác biệt này. Không nên để binding ngầm quyết định ngữ nghĩa cập nhật.

### Bảo vệ request thay đổi trạng thái

Với ứng dụng dùng cookie và session, cần cấu hình CSRF protection cho các thao tác thay đổi trạng thái. Kiểm tra quyền phải thực hiện ở máy chủ. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log request.

## 10. Chuyển lỗi thành phản hồi phù hợp

Controller và bộ xử lý ngoại lệ ở tầng web chuyển lỗi của ranh giới hoặc use case thành phản hồi mà client có thể hiểu. Nên phân biệt loại lỗi thay vì trả cùng một thông báo chung:

| Tình huống | Phản hồi HTTP thường dùng | Ý nghĩa |
|---|---:|---|
| JSON sai cú pháp hoặc không bind được kiểu | 400 Bad Request | Request không đọc được |
| Trường đầu vào không đạt validation | 400 hoặc 422 theo hợp đồng API | Dữ liệu không đáp ứng yêu cầu đầu vào |
| Chưa xác thực | 401 Unauthorized | Client cần xác thực |
| Đã xác thực nhưng không đủ quyền | 403 Forbidden | Không được phép thực hiện |
| Không tìm thấy tài nguyên | 404 Not Found | Tài nguyên không tồn tại hoặc không thể truy cập theo chính sách |
| Xung đột trạng thái nghiệp vụ | 409 Conflict | Hành động không phù hợp với trạng thái hiện tại |
| Lỗi ngoài dự kiến | 500 Internal Server Error | Lỗi máy chủ chưa được xử lý |

Mã trạng thái cụ thể phụ thuộc hợp đồng API và chính sách bảo mật. Phản hồi nên có cấu trúc ổn định, mã lỗi có thể xử lý và thông điệp an toàn. Không trả stack trace, câu SQL, tên class nội bộ hoặc thông tin nhạy cảm cho client.

Trong Spring MVC, có thể dùng @ControllerAdvice và @ExceptionHandler để tập trung ánh xạ exception thành response hoặc trang lỗi. Controller vẫn tập trung vào luồng use case chính.

## 11. Controller nên làm gì và không nên làm gì?

| Trách nhiệm phù hợp | Việc nên đặt ở tầng khác |
|---|---|
| Ánh xạ route và HTTP method vào handler | Quy tắc chuyển trạng thái nghiệp vụ |
| Đọc path, query, header, form và body | Truy vấn SQL trực tiếp hoặc thao tác repository tùy tiện |
| Chuyển đổi kiểu và kiểm tra cấu trúc đầu vào | Bảo vệ bất biến của miền nghiệp vụ |
| Lấy danh tính từ security context | Tự tin vào role hoặc owner ID do client gửi |
| Tạo command/query và gọi application service | Tính giá cuối cùng hoặc quyết định hạn mức |
| Chọn View hoặc cấu trúc HTTP response | Tạo HTML trong chuỗi hoặc trộn nghiệp vụ vào template |
| Chuyển lỗi thành phản hồi ở mức giao thức | Che giấu lỗi nghiệp vụ bằng cách trả thành công giả |

Controller quá lớn thường có dấu hiệu chứa nhiều nhánh nghiệp vụ, truy vấn dữ liệu trực tiếp, tính toán quy tắc, gửi email, ghi log nghiệp vụ và tự điều phối nhiều hệ thống. Khi đó, hãy chuyển phần điều phối use case sang application service và phần quy tắc sang Model hoặc domain service.

Không cần tạo một service cho mọi dòng code. Một Controller đơn giản có thể gọi trực tiếp một application service duy nhất. Mục tiêu là giữ ranh giới rõ ràng và tránh để handler trở thành nơi chứa toàn bộ hành vi của ứng dụng.

## 12. Kiểm thử việc diễn giải ý định

Kiểm thử Controller nên xác nhận request được ánh xạ đúng và dữ liệu được chuyển đến tầng ứng dụng đúng hợp đồng.

Các trường hợp nên kiểm tra:

1. **Đúng route và method:** endpoint chỉ phản hồi theo phương thức đã công bố.
2. **Binding:** path variable, query parameter, form hoặc JSON được chuyển đúng kiểu và đúng trường.
3. **Validation:** dữ liệu thiếu, sai định dạng hoặc vượt giới hạn bị từ chối trước khi gọi use case.
4. **Danh tính:** ID người dùng được lấy từ ngữ cảnh xác thực, không lấy từ trường client có thể giả mạo.
5. **Ủy quyền:** người không có quyền không thể thực hiện use case bằng cách gọi endpoint trực tiếp.
6. **Ánh xạ command:** application service nhận đúng command và giá trị đã chuẩn hóa.
7. **Phản hồi:** kết quả thành công, lỗi validation, không tìm thấy và xung đột trạng thái được ánh xạ đúng.
8. **Không rò rỉ nội bộ:** response không chứa trường hoặc thông tin lỗi không dành cho client.

Với Spring MVC, MockMvc hỗ trợ kiểm thử route, binding, validation, status và nội dung response mà không cần khởi chạy trình duyệt. Có thể mock application service để xác nhận Controller gửi đúng command; kiểm thử nghiệp vụ của service nên được thực hiện riêng ở tầng phù hợp.

## 13. Checklist trước khi hoàn thành một Controller

- Route và HTTP method có diễn tả rõ ý định của request không?
- Mỗi trường đầu vào có nguồn và ý nghĩa rõ ràng không?
- DTO có chỉ chứa những trường client được phép cung cấp không?
- Dữ liệu có được chuyển đổi và validation trước khi gọi use case không?
- Danh tính và quyền có được xác định ở phía máy chủ không?
- Controller có chuyển request thành command/query rõ nghĩa không?
- Quy tắc nghiệp vụ có được thực thi trong tầng nghiệp vụ không?
- Thành công và lỗi có được chuyển thành View hoặc HTTP response nhất quán không?
- Kiểm thử có bao phủ binding, validation, quyền và ánh xạ phản hồi không?

Controller diễn giải ý định bằng cách ánh xạ một tương tác cụ thể vào use case của ứng dụng. Khi ranh giới này được thiết kế rõ, ứng dụng có thể thay đổi giao diện, giao thức hoặc cách gửi dữ liệu mà vẫn giữ các quy tắc nghiệp vụ ổn định và có thể kiểm thử độc lập.
