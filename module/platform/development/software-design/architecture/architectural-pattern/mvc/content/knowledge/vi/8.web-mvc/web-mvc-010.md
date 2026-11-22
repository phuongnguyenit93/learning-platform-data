# Phân biệt chuyển tiếp nội bộ và chuyển hướng trình duyệt

Trong ứng dụng web MVC, sau khi nhận một request, Controller cần quyết định cách trả kết quả cho trình duyệt. Có thể render một View trực tiếp, chuyển tiếp request đến một tài nguyên nội bộ khác (forward), hoặc yêu cầu trình duyệt gửi một request mới đến URL khác (redirect). Forward và redirect đều có thể dẫn đến một trang khác, nhưng chúng khác nhau về nơi điều hướng diễn ra, vòng đời request, URL trên trình duyệt và cách dữ liệu được truyền.

Hiểu đúng hai cơ chế này giúp tránh gửi lại biểu mẫu ngoài ý muốn, tránh mất dữ liệu giữa các request và chọn được luồng phù hợp cho ứng dụng Spring MVC.

## 1. Ba cách Controller có thể trả kết quả

Sau khi xử lý request, Controller thường chọn một trong ba cách:

1. **Render View:** trả tên template để Spring MVC render HTML trong request hiện tại.
2. **Forward:** máy chủ chuyển tiếp request hiện tại đến một đường dẫn nội bộ khác.
3. **Redirect:** máy chủ trả phản hồi chuyển hướng; trình duyệt gửi request mới đến URL được chỉ định.

Ví dụ, khi người dùng xem đơn hàng:

- Controller có thể trả View orders/detail để render trực tiếp.
- Controller có thể forward đến một endpoint nội bộ chuyên chuẩn bị hoặc render báo cáo.
- Controller có thể redirect trình duyệt đến /orders/42 sau khi tạo đơn hàng thành công.

Không nên xem việc trả tên template thông thường là một forward. Trong Spring MVC, return "orders/detail" thường được ViewResolver dùng để tìm template; return "forward:/internal/orders/detail" mới yêu cầu điều phối nội bộ qua đường dẫn đó.

## 2. Forward là gì?

Forward là cơ chế chuyển tiếp ở phía máy chủ. Servlet container dùng RequestDispatcher.forward() để chuyển việc xử lý request hiện tại đến một tài nguyên nội bộ khác trong cùng ứng dụng web. Trình duyệt không nhận một chỉ thị điều hướng mới và không tự gửi request thứ hai.

~~~mermaid
sequenceDiagram
    actor Browser as Trình duyệt
    participant Server as Máy chủ / Servlet container
    participant A as Controller A
    participant B as Tài nguyên nội bộ B
    Browser->>Server: Request /reports/42/preview
    Server->>A: Xử lý request
    A->>A: Chuẩn bị dữ liệu
    A->>Server: forward đến /internal/report-preview
    Server->>B: Chuyển tiếp cùng request
    B-->>Server: Nội dung phản hồi
    Server-->>Browser: HTTP response cuối cùng
~~~

Các đặc điểm quan trọng:

- Forward diễn ra bên trong máy chủ, không tạo một chuyến đi HTTP mới từ trình duyệt.
- Request và response hiện tại tiếp tục được sử dụng.
- Phương thức HTTP của request hiện tại vẫn được giữ khi tài nguyên đích tiếp tục xử lý.
- Các request attribute đã đặt có thể được tài nguyên đích đọc.
- URL trên thanh địa chỉ trình duyệt vẫn là URL ban đầu.
- Đích forward phải là tài nguyên nội bộ mà ứng dụng có thể dispatch đến; không dùng forward để điều hướng đến một website bên ngoài.
- Forward phải được thực hiện trước khi response đã commit. Nếu response đã gửi nội dung hoặc header không thể thay đổi, việc forward có thể thất bại.

Forward thường hữu ích khi một request cần chuyển sang một endpoint hoặc tài nguyên nội bộ khác trong cùng lần xử lý. Nó không yêu cầu người dùng tải lại trang.

### 2.1. Forward bằng Servlet API

Ví dụ servlet chuẩn:

~~~java
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

@WebServlet("/reports/preview")
public class ReportPreviewServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws ServletException, IOException {
        request.setAttribute("reportTitle", "Báo cáo doanh thu");

        RequestDispatcher dispatcher =
                request.getRequestDispatcher("/WEB-INF/views/report-preview.jsp");
        dispatcher.forward(request, response);
    }
}
~~~

Servlet đặt reportTitle vào request attribute rồi forward đến JSP. JSP có thể đọc thuộc tính đó trong cùng request. Thư mục WEB-INF thường được dùng để chứa template không cho trình duyệt truy cập trực tiếp bằng URL.

### 2.2. Forward trong Spring MVC

Spring MVC hỗ trợ tiền tố forward: trong tên View:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.ui.Model;

@Controller
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/reports/{id}/preview")
    public String preview(
            @PathVariable long id,
            HttpServletRequest request
    ) {
        request.setAttribute("report", reportService.findReport(id));
        return "forward:/internal/report-preview";
    }

    @GetMapping("/internal/report-preview")
    public String renderPreview(
            @RequestAttribute("report") Report report,
            Model model
    ) {
        model.addAttribute("report", report);
        return "reports/preview";
    }
}
~~~

Ở đây, Spring tạo một forward nội bộ đến /internal/report-preview. Request attribute report vẫn nằm trên request và được handler đích đọc qua @RequestAttribute. Report và ReportService là kiểu dữ liệu/service của ứng dụng cần định nghĩa. Endpoint nội bộ nên được thiết kế rõ ràng, tránh forward quay lại chính endpoint ban đầu hoặc tạo chuỗi forward vòng lặp.

Trong ứng dụng Spring MVC thông thường, nếu mục tiêu chỉ là render một template bằng dữ liệu đã có, hãy trả trực tiếp tên View:

~~~java
@GetMapping("/reports/{id}")
public String detail(@PathVariable long id, Model model) {
    model.addAttribute("report", reportService.findReport(id));
    return "reports/detail";
}
~~~

Đoạn mã này render reports/detail qua ViewResolver; nó không yêu cầu servlet container forward sang một URL nội bộ khác. Chỉ dùng forward: khi cần chuyển tiếp request đến một đường dẫn nội bộ.

## 3. Redirect là gì?

Redirect là cơ chế chuyển hướng ở phía trình duyệt. Máy chủ trả về một HTTP response có mã trạng thái chuyển hướng và header Location. Trình duyệt đọc URL trong header đó rồi gửi một request mới.

~~~mermaid
sequenceDiagram
    actor Browser as Trình duyệt
    participant Server as Máy chủ
    participant A as Controller xử lý POST
    participant B as Endpoint đích
    Browser->>Server: POST /orders
    Server->>A: Xử lý tạo đơn hàng
    A->>Server: Redirect với Location: /orders/42
    Server-->>Browser: 303 See Other + Location
    Browser->>Server: GET /orders/42
    Server->>B: Xử lý request mới
    B-->>Server: Trang chi tiết đơn hàng
    Server-->>Browser: HTML
~~~

Các đặc điểm:

- Redirect yêu cầu trình duyệt thực hiện một request HTTP mới.
- URL trên thanh địa chỉ thay đổi thành URL đích sau khi trình duyệt theo chuyển hướng.
- Request mới có phương thức và dữ liệu phụ thuộc vào mã trạng thái redirect cùng hành vi của client.
- Request attribute của request cũ không tự động tồn tại trong request mới.
- Redirect có thể trỏ đến URL nội bộ hoặc URL bên ngoài, tùy chính sách và cách ứng dụng xây dựng URL.

Redirect phù hợp khi muốn kết thúc một thao tác rồi điều hướng trình duyệt sang một trang khác, đặc biệt sau khi gửi form tạo hoặc cập nhật dữ liệu.

## 4. Forward và redirect khác nhau ở đâu?

| Tiêu chí | Forward | Redirect |
|---|---|---|
| Nơi điều hướng | Phía máy chủ | Phía trình duyệt |
| Số request HTTP từ trình duyệt | Một request ban đầu | Ít nhất một request mới sau phản hồi redirect |
| Request object | Tiếp tục dùng request hiện tại | Tạo request mới |
| Request attributes | Có thể được tài nguyên đích đọc | Không tự chuyển sang request mới |
| URL trên trình duyệt | Giữ URL ban đầu | Đổi sang URL đích |
| Điều hướng ra website khác | Không | Có thể |
| Chi phí mạng | Không phát sinh request điều hướng mới | Có thêm round trip HTTP |
| Trường hợp thường dùng | Chuyển tiếp xử lý nội bộ | Điều hướng sau thao tác, PRG |

Ví dụ, người dùng gửi POST /orders:

- Nếu Controller forward sang một endpoint khác, trình duyệt vẫn ở URL /orders và request vẫn là request POST ban đầu. Khi người dùng refresh, trình duyệt có thể hỏi có gửi lại form hay không.
- Nếu Controller redirect đến /orders/42, trình duyệt thực hiện request mới, thường là GET khi dùng 303 See Other. Refresh trang chi tiết sẽ tải lại GET thay vì gửi lại POST tạo đơn.

## 5. Mã trạng thái HTTP khi redirect

Redirect không phải lúc nào cũng có cùng hành vi. Mã trạng thái quyết định cách client xử lý request tiếp theo.

| Mã | Ý nghĩa | Hành vi phương thức thường gặp |
|---:|---|---|
| 301 Moved Permanently | Tài nguyên đã chuyển vĩnh viễn | Client có thể chuyển POST thành GET; phù hợp cho điều hướng URL lâu dài theo chính sách |
| 302 Found | Chuyển hướng tạm thời | Hành vi lịch sử của trình duyệt thường đổi POST thành GET, nhưng ngữ nghĩa không mạnh bằng 303 |
| 303 See Other | Xem kết quả tại một URI khác | Request tiếp theo dùng GET (hoặc HEAD nếu request ban đầu là HEAD) |
| 307 Temporary Redirect | Chuyển hướng tạm thời, giữ phương thức | Client giữ method và body của request ban đầu |
| 308 Permanent Redirect | Chuyển hướng vĩnh viễn, giữ phương thức | Client giữ method và body của request ban đầu |

Với luồng Post/Redirect/Get sau khi tạo hoặc cập nhật dữ liệu, 303 See Other diễn tả rõ rằng trình duyệt nên thực hiện GET để xem kết quả. 307 và 308 giữ phương thức, nên có thể khiến một POST được gửi lại đến URL đích; chỉ dùng khi đó là hành vi mong muốn.

Các mã 301 và 308 mang ý nghĩa chuyển hướng vĩnh viễn và có thể được client hoặc cache ghi nhớ. Không dùng chúng cho điều hướng tạm thời sau khi gửi biểu mẫu.

## 6. Post/Redirect/Get (PRG)

PRG là mẫu xử lý biểu mẫu gồm ba bước:

1. **POST:** trình duyệt gửi dữ liệu biểu mẫu để tạo hoặc cập nhật.
2. **Redirect:** máy chủ xác nhận xử lý và trả chuyển hướng đến một URL kết quả.
3. **GET:** trình duyệt gửi request mới để đọc và hiển thị kết quả.

~~~mermaid
flowchart TD
    A[Người dùng gửi form] --> B[POST /orders]
    B --> C[Controller xác thực và gọi use case]
    C --> D{Thành công?}
    D -->|Có| E[303 See Other]
    E --> F[GET /orders/42]
    F --> G[Render trang chi tiết]
    D -->|Không| H[Render lại form cùng lỗi]
~~~

PRG giúp giảm việc gửi lại thao tác POST khi người dùng refresh trang kết quả. Nó cũng tạo một URL GET có thể tải lại, đánh dấu trang hoặc chia sẻ theo chính sách truy cập.

PRG không bảo đảm một thao tác nghiệp vụ chỉ được thực hiện một lần trong mọi tình huống. Người dùng vẫn có thể nhấn nút gửi nhiều lần, gửi request lặp do mạng hoặc gọi API trực tiếp. Với thao tác quan trọng như thanh toán hoặc tạo đơn hàng, ứng dụng có thể cần idempotency key, kiểm tra trạng thái và ràng buộc duy nhất ở tầng nghiệp vụ hoặc lưu trữ.

### 6.1. Ví dụ Spring MVC dùng PRG

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import org.springframework.http.HttpStatus;
import org.springframework.ui.Model;
import org.springframework.web.servlet.view.RedirectView;

@Controller
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders")
    public RedirectView create(RedirectAttributes redirectAttributes) {
        long orderId = orderService.createOrder();

        redirectAttributes.addFlashAttribute(
                "notice", "Đơn hàng đã được tạo thành công"
        );

        RedirectView redirect =
                new RedirectView("/orders/" + orderId, true);
        redirect.setStatusCode(HttpStatus.SEE_OTHER);
        return redirect;
    }

    @GetMapping("/orders/{id}")
    public String detail(@PathVariable long id, Model model) {
        model.addAttribute("order", orderService.findOrder(id));
        return "orders/detail";
    }
}
~~~

Ví dụ minh họa phần chuyển hướng; trong ứng dụng thật, phương thức create nhận DTO từ form hoặc request body, xác thực đầu vào và gọi use case tạo đơn hàng. RedirectView được đặt mã 303 See Other để trình duyệt thực hiện GET đến trang chi tiết. RedirectAttributes cho phép truyền thông báo flash sang request kế tiếp.

Nếu không cần chỉ định rõ status, Spring MVC cũng hỗ trợ cách viết ngắn:

~~~java
return "redirect:/orders/" + orderId;
~~~

Tiền tố redirect: yêu cầu Spring tạo redirect view. Mã trạng thái mặc định phụ thuộc cách cấu hình và loại redirect view; nếu hợp đồng cần chính xác là 303, hãy đặt status rõ ràng như ví dụ trên.

## 7. Truyền dữ liệu qua forward và redirect

Dữ liệu cần thiết cho View đích phải được truyền bằng cơ chế phù hợp với vòng đời của request.

### 7.1. Request attribute khi forward

Forward tiếp tục dùng request hiện tại, vì vậy tài nguyên đích có thể đọc request attribute:

~~~java
request.setAttribute("report", report);
request.getRequestDispatcher("/internal/report-preview")
       .forward(request, response);
~~~

Đây là cách truyền dữ liệu phù hợp với một lần xử lý nội bộ. Dữ liệu không tự tồn tại sau khi response kết thúc.

### 7.2. Query parameter hoặc path variable khi redirect

Redirect tạo request mới nên dữ liệu định tuyến cần được biểu diễn trong URL:

~~~java
return "redirect:/orders/" + orderId;
~~~

ID đơn hàng trở thành một phần của URL đích. Controller ở request GET tiếp theo đọc ID từ path và truy vấn dữ liệu có thẩm quyền. Không đưa mật khẩu, token, thông tin cá nhân nhạy cảm hoặc dữ liệu nội bộ vào query string vì URL có thể xuất hiện trong lịch sử trình duyệt, log, analytics hoặc header referrer.

Trong Spring MVC, RedirectAttributes.addAttribute() có thể thêm thuộc tính vào URL dưới dạng path/query parameter theo cách xây dựng redirect view:

~~~java
redirectAttributes.addAttribute("page", 2);
return "redirect:/orders";
~~~

Trình duyệt có thể được chuyển đến URL tương tự /orders?page=2. Chỉ dùng cách này cho dữ liệu không nhạy cảm và phù hợp để xuất hiện trong URL.

### 7.3. Flash attribute cho thông báo dùng một lần

Flash attribute lưu dữ liệu tạm thời để request kế tiếp sau redirect có thể đọc. Spring MVC thường dùng session làm nơi lưu flash map và loại bỏ dữ liệu sau khi nó được tiêu thụ.

~~~java
redirectAttributes.addFlashAttribute(
        "notice", "Cập nhật hồ sơ thành công"
);
return "redirect:/profile";
~~~

View ở request GET tiếp theo có thể hiển thị notice. Flash attribute phù hợp cho thông báo ngắn như “Đã lưu thành công” hoặc lỗi cần hiển thị ngay sau redirect. Không dùng flash attribute để thay thế kho dữ liệu nghiệp vụ hoặc lưu thông tin dài hạn.

### 7.4. Session cho trạng thái kéo dài hơn

Nếu dữ liệu cần tồn tại qua nhiều request, có thể dùng session hoặc kho lưu trữ phù hợp. Cần kiểm soát thời gian sống, kích thước, quyền truy cập và việc xóa dữ liệu. Không nên lưu toàn bộ entity lớn hoặc dữ liệu nhạy cảm trong session chỉ để tránh truy vấn lại.

## 8. Xử lý validation và lỗi biểu mẫu

Không phải mọi POST đều nên redirect. Khi dữ liệu biểu mẫu không hợp lệ, ứng dụng thường render lại form ngay trong response hiện tại để giữ lỗi validation và giá trị người dùng vừa nhập.

~~~java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@PostMapping("/profile")
public String updateProfile(
        @Valid @ModelAttribute("form") ProfileForm form,
        BindingResult errors,
        RedirectAttributes redirectAttributes
) {
    if (errors.hasErrors()) {
        return "profile/edit";
    }

    profileService.update(form);
    redirectAttributes.addFlashAttribute("notice", "Đã cập nhật hồ sơ");
    return "redirect:/profile";
}
~~~

Trong ví dụ, lỗi binding và validation được trả lại template profile/edit để hiển thị tại chỗ. Khi cập nhật thành công, Controller redirect đến trang hồ sơ. Quy tắc này giúp người dùng sửa dữ liệu sai mà không phải nhập lại toàn bộ biểu mẫu.

Đoạn mã là một handler nằm trong Controller có sẵn profileService; ProfileForm là DTO biểu mẫu của ứng dụng.

Nếu lỗi phát sinh ở tầng nghiệp vụ sau khi validation cấu trúc đã qua, ứng dụng cần ánh xạ lỗi đó thành lỗi trường hoặc thông báo phù hợp. Có thể render lại form với lỗi nếu request hiện tại còn dữ liệu cần giữ; hoặc redirect với flash error khi luồng trải nghiệm yêu cầu PRG. Không chuyển lỗi chi tiết nội bộ hoặc stack trace cho người dùng.

## 9. Chọn forward, redirect hay render trực tiếp?

| Nhu cầu | Cách thường phù hợp | Lý do |
|---|---|---|
| Hiển thị template với dữ liệu đã chuẩn bị | Render View trực tiếp | Không cần dispatch sang URL khác |
| Chuyển request đến tài nguyên nội bộ trong cùng lần xử lý | Forward | Giữ request và request attribute |
| Sau POST thành công, đưa người dùng đến trang kết quả | Redirect (thường 303) | Tạo GET mới, áp dụng PRG |
| Điều hướng đến URL bên ngoài | Redirect | Trình duyệt phải truy cập đích bên ngoài |
| Hiển thị lại form với lỗi validation | Render View trực tiếp | Giữ binding result và dữ liệu form |
| Chuyển hướng URL cũ sang URL chuẩn mới | Redirect phù hợp status | URL trình duyệt cần đổi |

Hãy bắt đầu từ câu hỏi: trình duyệt có cần biết URL mới hay không?

- Nếu không, và request cần tiếp tục được xử lý nội bộ, cân nhắc forward.
- Nếu có, redirect là cơ chế phù hợp.
- Nếu chỉ cần render template đã chọn, trả View bình thường là đủ.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng forward sau POST thành công rồi refresh | Trình duyệt có thể gửi lại POST | Dùng PRG và redirect đến GET |
| Nghĩ forward làm URL trình duyệt thay đổi | Người dùng vẫn thấy URL ban đầu | Dùng redirect nếu URL cần đổi |
| Mong request attribute tồn tại sau redirect | Dữ liệu không có trong request mới | Dùng URL parameter, flash attribute hoặc session phù hợp |
| Đưa dữ liệu nhạy cảm vào query string | Dữ liệu có thể lọt vào lịch sử hoặc log | Chỉ truyền ID hoặc dữ liệu không nhạy cảm; tải dữ liệu từ máy chủ |
| Redirect POST bằng 307/308 không chủ đích | Client có thể gửi lại POST và body đến URL đích | Dùng 303 cho luồng PRG |
| Forward vòng lặp giữa các endpoint | Request không kết thúc hoặc lỗi dispatch | Thiết kế đích rõ ràng, kiểm thử đường đi |
| Redirect đến URL do client tùy ý cung cấp | Có nguy cơ open redirect | Chỉ cho phép đích nội bộ hoặc allowlist URL đáng tin cậy |
| Redirect khi validation lỗi mà không giữ dữ liệu | Người dùng phải nhập lại form | Render form trực tiếp hoặc dùng flash data có chủ đích |
| Coi redirect là cơ chế chống gửi trùng tuyệt đối | Request lặp vẫn có thể xảy ra | Dùng idempotency và kiểm soát nghiệp vụ khi cần |

### 10.1. Tránh open redirect

Nếu ứng dụng nhận tham số như returnUrl rồi redirect trực tiếp đến giá trị đó, kẻ tấn công có thể gửi liên kết khiến người dùng bị chuyển đến website giả mạo. Hãy kiểm tra URL đích:

- Ưu tiên chỉ nhận đường dẫn tương đối nội bộ.
- Nếu cần domain bên ngoài, dùng allowlist domain rõ ràng.
- Chuẩn hóa URL trước khi kiểm tra, tránh chỉ kiểm tra bằng tiền tố chuỗi đơn giản.
- Không dùng giá trị Host hoặc URL do client cung cấp làm đích đáng tin nếu chưa xác thực.

## 11. Kiểm thử forward và redirect

Kiểm thử nên xác nhận cả hành vi HTTP lẫn dữ liệu đi qua đúng ranh giới.

1. **Render trực tiếp:** handler trả đúng tên View và model attribute cần thiết.
2. **Forward:** request được dispatch đến đích nội bộ, URL trình duyệt không được yêu cầu thay đổi và request attribute còn đọc được.
3. **Redirect:** response có mã 3xx mong muốn và header Location trỏ đến URL đúng.
4. **Phương thức sau redirect:** luồng PRG dùng GET sau POST; không vô tình giữ POST bằng 307/308.
5. **Flash attribute:** thông báo xuất hiện ở request đích và không tồn tại lâu hơn dự kiến.
6. **Validation:** lỗi trả lại form cùng dữ liệu cần thiết, không gọi use case thành công.
7. **Refresh:** tải lại trang kết quả không gửi lại thao tác POST đã hoàn thành.
8. **Open redirect:** URL ngoài danh sách cho phép bị từ chối hoặc chuẩn hóa về đích nội bộ.

Với Spring MVC, MockMvc có thể kiểm tra view name forward:/..., redirectedUrl(...), status, header và flash attribute. Kiểm thử tích hợp ở servlet container có thể xác nhận hành vi dispatch thực tế khi cần.

## 12. Checklist trước khi chọn cơ chế điều hướng

- Controller có cần render template hiện tại, dispatch nội bộ hay điều hướng trình duyệt?
- URL trên thanh địa chỉ có cần đổi không?
- Request hiện tại có cần được giữ lại không?
- Request attribute có đủ để truyền dữ liệu cho đích nội bộ không?
- Nếu redirect, dữ liệu nào cần nằm trong URL và dữ liệu nào nên dùng flash/session?
- Mã trạng thái redirect có giữ hay đổi HTTP method đúng với mục đích không?
- POST thành công có dùng PRG để tránh refresh gửi lại form không?
- Validation lỗi có giữ được dữ liệu người dùng đã nhập không?
- Đích redirect có được kiểm tra để ngăn open redirect không?
- Kiểm thử có xác nhận status, Location, request method và dữ liệu đích không?

Forward và redirect giải quyết hai nhu cầu điều hướng khác nhau. Forward chuyển tiếp việc xử lý bên trong máy chủ bằng request hiện tại; redirect yêu cầu trình duyệt tạo request mới đến URL đích. Khi chỉ cần render một template, Controller nên trả View trực tiếp. Chọn đúng cơ chế giúp luồng request dễ hiểu, dữ liệu được truyền đúng vòng đời và các thao tác POST được xử lý an toàn hơn.
