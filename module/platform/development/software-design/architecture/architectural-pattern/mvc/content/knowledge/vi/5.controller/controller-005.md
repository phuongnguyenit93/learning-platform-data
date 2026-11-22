# Chọn kết quả, dữ liệu trả về và View phù hợp

Trong module **MODEL_VIEW_CONTROLLER**, Controller tiếp nhận request, điều phối xử lý và quyết định phản hồi mà ứng dụng gửi lại. Sau khi gọi use case hoặc dịch vụ ứng dụng, Controller cần diễn giải kết quả: thao tác thành công hay thất bại, người dùng nên được đưa đến trang nào, dữ liệu nào cần cung cấp cho View và response cần có mã HTTP nào.

Việc chọn kết quả là một phần quan trọng của MVC. Cùng một kết quả nghiệp vụ có thể được trình bày theo nhiều cách: render trang HTML, chuyển hướng sang URL khác hoặc trả dữ liệu JSON cho client. Controller chịu trách nhiệm nối kết quả xử lý với hình thức phản hồi phù hợp, còn View tập trung trình bày dữ liệu đã được chuẩn bị.

## 1. Controller quyết định điều gì sau khi xử lý?

Một request thường bắt đầu từ thao tác của người dùng, nhưng kết thúc bằng một response cụ thể. Sau khi gọi use case, Controller cần quyết định:

- **Kết quả xử lý được ánh xạ ra sao?** Ví dụ tạo đơn hàng thành công, dữ liệu không hợp lệ, đơn hàng không tồn tại hoặc thao tác bị từ chối.
- **Phản hồi có hình thức nào?** Render một View, chuyển hướng đến URL khác, trả JSON/XML, trả tệp hoặc trả response không có nội dung.
- **Dữ liệu nào cần gửi về?** Chỉ những trường mà trang hoặc client cần để hiển thị kết quả.
- **Mã trạng thái HTTP nào phù hợp?** Chẳng hạn 200 khi lấy dữ liệu thành công, 201 khi tạo tài nguyên qua API, 302/303 khi chuyển hướng, 404 khi không tìm thấy hoặc 409 khi có xung đột.
- **Có cần header hoặc cookie nào không?** Ví dụ Location cho redirect hoặc thông tin cache phù hợp.

Controller thực hiện việc ánh xạ này dựa trên hợp đồng kết quả của tầng ứng dụng. Nó không nên tự suy luận trạng thái nghiệp vụ từ một chuỗi thông báo hoặc tự viết lại quy tắc nghiệp vụ.

## 2. Phân biệt kết quả nghiệp vụ và response HTTP

Kết quả nghiệp vụ mô tả điều đã xảy ra trong ứng dụng. Response HTTP mô tả cách server thông báo kết quả đó cho client. Hai thứ liên quan nhưng không đồng nhất.

Ví dụ, use case đặt hàng có thể trả về:

| Kết quả nghiệp vụ | Ý nghĩa |
| --- | --- |
| Đặt hàng thành công kèm mã đơn | Đơn hàng đã được tạo |
| Dữ liệu đầu vào không hợp lệ | Một hoặc nhiều điều kiện đầu vào không đạt |
| Sản phẩm không còn đủ tồn kho | Không thể hoàn thành thao tác theo trạng thái hiện tại |
| Khách hàng không tồn tại | Không tìm thấy đối tượng cần thiết |
| Người dùng không được phép đặt hàng | Thao tác bị từ chối theo quyền hoặc chính sách |

Controller ánh xạ các kết quả đó theo loại client:

| Kết quả | Phản hồi HTML thường gặp | API thường gặp |
| --- | --- | --- |
| Thành công | Redirect đến trang chi tiết hoặc render trang kết quả | 201 Created hoặc 200 OK tùy hợp đồng |
| Dữ liệu không hợp lệ | Render lại form cùng lỗi | 400 Bad Request hoặc 422 Unprocessable Content theo quy ước API |
| Không tìm thấy | Trang 404 | 404 Not Found |
| Xung đột trạng thái | Trang giải thích xung đột | 409 Conflict |
| Không có quyền | Trang từ chối truy cập | 403 Forbidden |
| Lỗi ngoài dự kiến | Trang lỗi chung | 500 Internal Server Error |

Mã HTTP phải phản ánh đúng ý nghĩa giao thức. Ví dụ, 401 thường dành cho trường hợp chưa xác thực hoặc cần thông tin xác thực; 403 diễn tả trường hợp đã được xác thực nhưng không được phép thực hiện thao tác. 400 và 422 có thể được dùng theo quy ước API nhất quán, nhưng không nên trả mã thành công cho một thao tác thất bại chỉ để client dễ xử lý.

## 3. Chọn View phù hợp với kết quả

Trong server-side MVC, Controller thường chọn một View dựa trên mục đích của request và kết quả xử lý. Một số lựa chọn phổ biến:

- **Render cùng trang:** phù hợp khi cần hiển thị kết quả hoặc form có lỗi ngay trong response hiện tại.
- **Redirect:** phù hợp khi thao tác đã thay đổi trạng thái và người dùng nên chuyển đến URL mới, chẳng hạn trang chi tiết sau khi tạo đơn.
- **Trang lỗi:** phù hợp khi tài nguyên không tồn tại, người dùng không có quyền hoặc xảy ra lỗi cần thông báo.
- **Response body:** phù hợp với API hoặc request bất đồng bộ cần dữ liệu JSON thay vì một trang HTML.

Tên View nên phản ánh trang cần hiển thị, không nên dùng tên kỹ thuật mơ hồ như **successPage2**. Với cấu trúc template theo tính năng, các tên như **orders/detail**, **orders/new** hoặc **errors/not-found** giúp Controller dễ đọc và giúp nhóm phát triển tìm đúng template.

Ví dụ Controller lấy dữ liệu đơn hàng và chọn trang chi tiết:

~~~java
@Controller
@RequestMapping("/orders")
public class OrderController {
    private final OrderQuery orderQuery;

    public OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable String id, Model model) {
        OrderDetailViewModel page = orderQuery.getDetail(id);
        model.addAttribute("page", page);
        return "orders/detail";
    }
}
~~~

Trong ví dụ Spring MVC, giá trị trả về **orders/detail** là tên View. Đối tượng **Model** được dùng để chuyển thuộc tính **page** sang View. Đây là Model trong cơ chế web MVC của Spring, không đồng nghĩa với toàn bộ lớp Model nghiệp vụ trong kiến trúc.

## 4. Chuẩn bị dữ liệu trả về cho View

View cần dữ liệu đủ để trình bày nhưng không cần toàn bộ đối tượng nội bộ của ứng dụng. Controller hoặc tầng ứng dụng nên cung cấp một DTO/view model có cấu trúc rõ ràng.

Ví dụ:

~~~java
public record OrderDetailViewModel(
        String orderNumber,
        String customerName,
        String statusLabel,
        List<OrderLineViewModel> lines,
        String totalLabel
) {}

public record OrderLineViewModel(
        String productName,
        String quantityLabel,
        String subtotalLabel
) {}
~~~

Khi đưa dữ liệu vào View, Controller có thể sử dụng thuộc tính có tên ổn định:

~~~java
OrderDetailViewModel page = orderQuery.getDetail(id);
model.addAttribute("page", page);
return "orders/detail";
~~~

Hợp đồng dữ liệu này giúp template biết chính xác các trường có thể sử dụng. Không nên đưa entity ORM trực tiếp vào View nếu entity chứa dữ liệu nhạy cảm, quan hệ lazy hoặc cấu trúc lưu trữ không dành cho giao diện. Khi cấu trúc Model thay đổi, DTO giúp giới hạn ảnh hưởng đến template.

Tên thuộc tính cũng cần nhất quán. Nếu Controller cung cấp **page** nhưng template lại đọc **order**, trang có thể lỗi khi render. Có thể giảm rủi ro bằng cách dùng kiểu view model rõ ràng và kiểm thử render cho từng View quan trọng.

## 5. Render lại form hay chuyển hướng?

Hai cách phản hồi phổ biến sau khi người dùng gửi form là render lại cùng View hoặc redirect. Chọn đúng cách giúp tránh gửi lại thao tác ngoài ý muốn và giữ trải nghiệm dễ hiểu.

### Render lại form khi dữ liệu không hợp lệ

Khi binding hoặc validation phát hiện lỗi, Controller thường trả lại template form cùng dữ liệu đã nhập và thông tin lỗi. Người dùng có thể sửa và gửi lại:

~~~java
@PostMapping
public String create(@Valid @ModelAttribute("form") OrderForm form,
                     BindingResult errors,
                     Model model) {
    if (errors.hasErrors()) {
        model.addAttribute("categories", categoryQuery.listForForm());
        return "orders/new";
    }

    OrderId id = placeOrder.execute(form.toCommand());
    return "redirect:/orders/" + id.value();
}
~~~

Trong Spring MVC, **BindingResult** phải đặt ngay sau tham số được binding để nhận lỗi tương ứng. Nếu form có các dữ liệu phụ như danh mục hoặc lựa chọn dropdown, Controller cần đưa lại những dữ liệu đó khi render form lỗi.

### Redirect sau khi thao tác thành công

Sau khi tạo đơn hàng thành công, redirect đưa trình duyệt đến URL chi tiết. Đây là một phần của mẫu **Post/Redirect/Get (PRG)**:

1. Trình duyệt gửi POST để tạo hoặc thay đổi dữ liệu.
2. Server xử lý và trả response redirect.
3. Trình duyệt gửi GET đến URL đích để hiển thị kết quả.

PRG giúp thao tác tải lại trang kết quả không tự gửi lại POST trước đó. Với dữ liệu thông báo chỉ cần tồn tại qua lần chuyển hướng, Spring có thể dùng **RedirectAttributes** để thêm flash attribute:

~~~java
OrderId id = placeOrder.execute(form.toCommand());
redirectAttributes.addFlashAttribute("notice", "Đơn hàng đã được tạo.");
return "redirect:/orders/" + id.value();
~~~

Flash attribute được lưu tạm để sử dụng ở request kế tiếp rồi loại bỏ theo cơ chế của framework. Không nên dùng redirect để truyền toàn bộ dữ liệu nhạy cảm hoặc một đối tượng lớn qua URL.

## 6. Trả dữ liệu cho API thay vì chọn template

Không phải mọi Controller đều trả tên View. Với REST API, Controller thường trả response body được tuần tự hóa thành JSON. Khi đó client tự dùng dữ liệu để cập nhật giao diện.

Ví dụ Spring REST Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderApiController {
    private final OrderQuery orderQuery;

    public OrderApiController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> detail(@PathVariable String id) {
        OrderResponse response = orderQuery.getResponse(id);
        return ResponseEntity.ok(response);
    }
}
~~~

Ở đây **@RestController** kết hợp hành vi của **@Controller** và **@ResponseBody**. Đối tượng trả về được chuyển thành response body theo cơ chế chuyển đổi của framework; Controller không chọn template HTML.

Với thao tác tạo tài nguyên qua API, có thể trả 201 Created cùng header Location và một response DTO:

~~~java
@PostMapping
public ResponseEntity<OrderCreatedResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderId id = placeOrder.execute(request.toCommand());
    URI location = URI.create("/api/orders/" + id.value());

    return ResponseEntity.created(location)
            .body(new OrderCreatedResponse(id.value()));
}
~~~

Hợp đồng API cần ổn định và không nên phụ thuộc trực tiếp vào entity lưu trữ. Response DTO xác định trường nào được công khai, tên trường và ý nghĩa của chúng.

## 7. Ánh xạ lỗi thành kết quả phù hợp

Lỗi có thể xuất hiện ở nhiều giai đoạn: binding dữ liệu, validation, kiểm tra nghiệp vụ, truy cập tài nguyên hoặc hạ tầng. Controller cần ánh xạ lỗi thành phản hồi nhất quán.

| Tình huống | Phản hồi thường phù hợp | Dữ liệu có thể cung cấp |
| --- | --- | --- |
| Form thiếu trường bắt buộc | Render lại form | Lỗi theo trường và dữ liệu người dùng đã nhập |
| Đơn hàng không tồn tại | 404 hoặc View not-found | Thông báo tài nguyên không tồn tại |
| Trạng thái không cho phép hủy | 409 hoặc trang xung đột | Trạng thái hiện tại và hướng xử lý phù hợp |
| Người dùng không có quyền | 403 hoặc trang forbidden | Thông báo chung không tiết lộ dữ liệu nhạy cảm |
| Lỗi hệ thống ngoài dự kiến | 500 hoặc trang lỗi chung | Mã tham chiếu để hỗ trợ tra cứu |

Không nên đưa stack trace, câu SQL, tên máy chủ, token hoặc nội dung exception thô vào response. Chi tiết kỹ thuật nên được ghi log ở phía server với cơ chế kiểm soát truy cập phù hợp; người dùng nhận thông báo đủ để hiểu và biết bước tiếp theo.

Với ứng dụng Spring, có thể tập trung ánh xạ exception bằng **@ControllerAdvice** và **@ExceptionHandler**. Cách này giúp nhiều Controller dùng chung quy ước phản hồi, tránh lặp cùng một khối xử lý lỗi ở từng endpoint:

~~~java
@ControllerAdvice
public class WebExceptionHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException exception) {
        ApiError error = new ApiError(
                "ORDER_NOT_FOUND",
                "Không tìm thấy đơn hàng."
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
    }
}
~~~

Ví dụ trên minh họa phản hồi API dạng JSON. Với giao diện HTML, handler có thể chọn trang lỗi phù hợp hoặc trả response status cùng View. Không phải mọi exception đều nên bị chuyển thành 404; cần ánh xạ theo đúng ý nghĩa của lỗi.

## 8. Chọn response theo loại request

Một ứng dụng có thể phục vụ cả trình duyệt và client API. Controller hoặc các endpoint riêng cần chọn response theo hợp đồng mà client mong đợi.

| Loại request | Kết quả mong đợi | Cách phản hồi |
| --- | --- | --- |
| Mở trang HTML | Nội dung giao diện | Tên View và dữ liệu Model |
| Gửi form HTML thành công | Trang đích sau thao tác | Redirect |
| Gửi form HTML không hợp lệ | Form cùng lỗi | Render lại form |
| Gọi API lấy dữ liệu | Dữ liệu có cấu trúc | JSON response body |
| Gọi API tạo tài nguyên | Kết quả tạo và địa chỉ tài nguyên | 201 Created, Location và DTO |
| Gửi request xóa thành công không cần nội dung | Xác nhận thao tác | 204 No Content nếu hợp đồng phù hợp |

Không nên trả HTML cho endpoint mà client đang chờ JSON, hoặc trả JSON tùy tiện cho form cần một trang có thể điều hướng. Nếu một endpoint hỗ trợ nhiều loại nội dung, cần xem xét header **Accept**, content negotiation và cấu hình của framework. Trong nhiều ứng dụng, tách endpoint HTML và API giúp hợp đồng dễ hiểu hơn.

## 9. Giữ Controller tập trung vào điều phối

Controller cần chọn kết quả và chuẩn bị response, nhưng không nên tự làm tất cả công việc của ứng dụng.

| Công việc | Trách nhiệm phù hợp |
| --- | --- |
| Đọc path, query, header và body | Controller / tầng web |
| Kiểm tra định dạng request và binding | Controller / tầng validation |
| Thực hiện quy tắc tạo, sửa hoặc hủy đơn hàng | Model và use case |
| Truy vấn dữ liệu cho trang | Dịch vụ truy vấn hoặc tầng ứng dụng |
| Chuyển dữ liệu nghiệp vụ thành view model | Mapper, presenter hoặc tầng ứng dụng |
| Chọn tên View, redirect, mã HTTP và response body | Controller |
| Dựng HTML và trình bày trạng thái giao diện | View |

Nếu Controller chứa nhiều phép tính nghiệp vụ, truy vấn trực tiếp nhiều bảng hoặc xây dựng HTML bằng nối chuỗi, việc chọn response sẽ trở nên khó đọc và khó kiểm thử. Hãy giữ Controller ở mức tiếp nhận, gọi use case, diễn giải kết quả và trả response.

## 10. Kiểm thử quyết định response của Controller

Kiểm thử Controller nên xác nhận rằng mỗi kết quả quan trọng được ánh xạ thành response đúng:

- Khi truy vấn thành công, Controller chọn đúng View và cung cấp đủ thuộc tính.
- Khi không tìm thấy dữ liệu, response có status hoặc View not-found phù hợp.
- Khi form không hợp lệ, Controller render lại form, giữ dữ liệu và lỗi cần thiết.
- Khi thao tác thành công, Controller redirect đến URL đúng hoặc trả DTO với status phù hợp.
- Với API, response có đúng cấu trúc JSON, header và mã HTTP.
- Khi có lỗi ngoài dự kiến, response không làm lộ chi tiết nội bộ.

Có thể dùng mock hoặc fake cho use case để tạo ra từng kết quả một cách có kiểm soát. Kiểm thử tích hợp bổ sung xác nhận template thật được render và thuộc tính trong Model có thể được View sử dụng.

Ví dụ các trường hợp cần kiểm tra cho thao tác tạo đơn hàng:

| Đầu vào / kết quả use case | Điều cần xác minh |
| --- | --- |
| Form sai định dạng | Trả template form và lỗi theo trường |
| Use case tạo thành công | Redirect đến trang chi tiết với mã đơn đúng |
| Use case báo xung đột | Trả phản hồi xung đột hoặc View tương ứng |
| API tạo thành công | Trả 201, Location và response DTO |
| Lỗi hệ thống | Trả lỗi chung, không chứa thông tin nội bộ |

## 11. Quy trình chọn kết quả và View

Khi viết một action của Controller, có thể thực hiện theo trình tự:

1. Xác định client đang mong đợi HTML, JSON, tệp hay một loại response khác.
2. Gọi use case hoặc dịch vụ phù hợp và nhận kết quả có cấu trúc.
3. Phân loại kết quả thành thành công, lỗi đầu vào, không tìm thấy, xung đột, từ chối quyền hoặc lỗi ngoài dự kiến.
4. Chọn mã HTTP và hình thức phản hồi phù hợp với hợp đồng.
5. Nếu render View, chuẩn bị view model chỉ chứa dữ liệu cần hiển thị và chọn template đúng.
6. Nếu redirect, chọn URL đích và chỉ truyền thông báo ngắn hoặc dữ liệu tạm cần thiết.
7. Nếu trả API response, dùng DTO công khai và status/header phù hợp.
8. Kiểm thử từng nhánh quan trọng để bảo đảm response nhất quán.

Ví dụ, khi người dùng hủy đơn hàng, Controller nhận request hủy và gọi use case. Nếu use case xác nhận hủy thành công, Controller redirect về trang chi tiết cùng thông báo. Nếu đơn hàng đã giao và không thể hủy, Controller có thể trả trang giải thích xung đột hoặc mã 409 cho API. Quy tắc “đơn hàng đã giao không thể hủy” thuộc về nghiệp vụ; Controller chỉ chuyển kết quả đó thành phản hồi phù hợp.

## Kết luận

Controller diễn giải kết quả từ tầng ứng dụng và chọn cách phản hồi phù hợp với client. Với HTML, Controller có thể chọn View, đưa view model vào Model hoặc redirect đến URL khác. Với API, Controller trả response DTO, mã HTTP và header theo hợp đồng. Khi kết quả nghiệp vụ, dữ liệu trình bày và response HTTP được phân biệt rõ, luồng MVC dễ đọc, dễ kiểm thử và nhất quán hơn.
