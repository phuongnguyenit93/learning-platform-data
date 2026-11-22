# Cookie, session và dữ liệu chuyển tiếp sau chuyển hướng

HTTP được thiết kế theo mô hình request/response: mỗi request được xử lý độc lập và máy chủ không tự động nhớ những request trước đó đến từ cùng một người dùng. Tuy nhiên, ứng dụng web thường cần duy trì trạng thái đăng nhập, giỏ hàng, lựa chọn ngôn ngữ hoặc dữ liệu tạm của một quy trình nhiều bước. Cookie, session và dữ liệu chuyển tiếp sau redirect là những cơ chế thường được dùng để đáp ứng nhu cầu này.

Trong mô hình **Model–View–Controller (MVC)**, Controller tiếp nhận request và điều phối phản hồi, Model quản lý trạng thái và quy tắc nghiệp vụ, còn View trình bày dữ liệu. Việc chọn nơi lưu trạng thái ảnh hưởng trực tiếp đến ranh giới giữa client và máy chủ, vòng đời dữ liệu, bảo mật và cách Controller xử lý chuyển hướng.

Cookie được lưu ở trình duyệt và được gửi kèm những request phù hợp. Session thường lưu dữ liệu ở phía máy chủ và dùng một mã định danh để liên kết các request. Flash attributes là dữ liệu ngắn hạn được chuyển từ một request sang request kế tiếp, thường dùng cùng mẫu Post/Redirect/Get (PRG). Ba khái niệm này có liên quan nhưng không thể thay thế cho nhau.

## 1. Vì sao ứng dụng web cần duy trì trạng thái?

Hãy xem một người dùng đăng nhập rồi mở trang giỏ hàng. Khi chuyển sang trang thanh toán, ứng dụng cần biết người dùng nào đang thao tác và giỏ hàng nào cần được hiển thị. Nếu mỗi request hoàn toàn không có thông tin liên kết, ứng dụng không thể duy trì trải nghiệm liên tục.

Một số ví dụ về trạng thái:

- Danh tính người dùng đã xác thực.
- Mã giỏ hàng hoặc mã phiên làm việc.
- Ngôn ngữ và tùy chọn giao diện.
- Dữ liệu bản nháp trong quy trình nhiều bước.
- Thông báo “Đã lưu thành công” sau khi chuyển hướng.
- Bộ lọc hoặc trang hiện tại của một danh sách.

Không phải mọi dữ liệu đều cần lưu lâu dài. Có dữ liệu chỉ cần tồn tại trong một request, có dữ liệu cần dùng trong một phiên làm việc, và có dữ liệu cần được lưu bền vững trong cơ sở dữ liệu. Chọn sai phạm vi có thể làm dữ liệu biến mất quá sớm, tồn tại quá lâu hoặc bị lộ ra ngoài.

## 2. Cookie là gì?

Cookie là một mẩu dữ liệu nhỏ mà máy chủ yêu cầu trình duyệt lưu lại. Máy chủ gửi cookie trong header `Set-Cookie`; trình duyệt lưu cookie theo các thuộc tính được chỉ định và tự gửi lại trong header `Cookie` ở những request phù hợp.

Ví dụ, máy chủ gửi:

~~~http
Set-Cookie: theme=dark; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax
~~~

Ở các request tiếp theo thỏa mãn phạm vi cookie, trình duyệt có thể gửi:

~~~http
Cookie: theme=dark
~~~

Cookie được lưu ở phía client. Vì vậy, người dùng có thể xóa hoặc sửa cookie thông qua trình duyệt hay công cụ phát request. Ứng dụng phải xem giá trị cookie là dữ liệu không đáng tin cậy, trừ khi nó được bảo vệ bằng cơ chế xác minh phù hợp. Ngay cả cookie đã ký hoặc mã hóa cũng cần kiểm tra thời hạn, mục đích và quyền truy cập.

### 2.1. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `Name=Value` | Tên và giá trị cookie | Không nên chứa dữ liệu bí mật dạng rõ |
| `Expires` | Thời điểm cookie hết hạn | Dựa trên ngày giờ tuyệt đối |
| `Max-Age` | Thời gian tồn tại tính bằng giây | Thường được ưu tiên khi cùng xuất hiện với Expires |
| `Domain` | Phạm vi host được phép nhận cookie | Chỉ đặt khi thực sự cần chia sẻ giữa subdomain |
| `Path` | Phạm vi đường dẫn request | Giới hạn nơi trình duyệt gửi cookie, không phải ranh giới bảo mật mạnh |
| `Secure` | Chỉ gửi cookie qua kết nối HTTPS | Cần dùng cho cookie phiên trong môi trường HTTPS |
| `HttpOnly` | JavaScript phía trình duyệt không đọc được cookie qua API thông thường | Giảm khả năng lấy cookie bằng XSS nhưng không ngăn XSS thực hiện hành động thay người dùng |
| `SameSite` | Kiểm soát việc gửi cookie trong ngữ cảnh cross-site | Hỗ trợ giảm rủi ro CSRF, không thay thế toàn bộ cơ chế chống CSRF |

Nếu không có `Expires` hoặc `Max-Age`, cookie thường là cookie phiên của trình duyệt và có thể bị xóa khi phiên trình duyệt kết thúc. Hành vi khôi phục phiên của trình duyệt có thể khiến thời điểm xóa thực tế khác nhau; không nên dùng điều này làm cơ chế bảo đảm thời hạn bảo mật.

### 2.2. Cookie phù hợp để lưu gì?

Cookie thường phù hợp với dữ liệu nhỏ, ít nhạy cảm và cần được trình duyệt gửi tự động, ví dụ:

- Tùy chọn giao diện như theme.
- Locale hoặc ngôn ngữ hiển thị.
- Mã định danh ngẫu nhiên của session.
- Một số lựa chọn tiện ích có thể khôi phục.

Cookie không phù hợp để lưu trực tiếp mật khẩu, OTP, thông tin thẻ, quyền quản trị hoặc dữ liệu nghiệp vụ có thể bị người dùng sửa. Cookie cũng có giới hạn kích thước và được gửi kèm request phù hợp, nên lưu dữ liệu lớn sẽ làm tăng kích thước request.

## 3. Session là gì?

Session là cơ chế để ứng dụng duy trì trạng thái phía máy chủ giữa nhiều request. Khi người dùng bắt đầu một phiên, máy chủ tạo hoặc sử dụng một session và cấp cho trình duyệt một mã định danh. Trình duyệt thường giữ mã này trong cookie, ví dụ `JSESSIONID` trong ứng dụng Servlet.

Luồng cơ bản:

1. Trình duyệt gửi request chưa có session.
2. Máy chủ tạo session và lưu dữ liệu phía server.
3. Máy chủ gửi cookie chứa session ID.
4. Trình duyệt gửi lại cookie ở các request phù hợp.
5. Máy chủ dùng session ID để tìm dữ liệu session tương ứng.
6. Khi session hết hạn hoặc bị hủy, dữ liệu session được giải phóng theo cơ chế của ứng dụng/container.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant S as Máy chủ ứng dụng
    participant Store as Session Store

    B->>S: GET /login
    S->>Store: Tạo session
    Store-->>S: Session ID + dữ liệu
    S-->>B: Set-Cookie: JSESSIONID=...
    B->>S: POST /login + Cookie
    S->>Store: Tìm session theo ID
    Store-->>S: Session hiện tại
    S->>Store: Cập nhật trạng thái xác thực
    S-->>B: Response
~~~

Session ID là khóa tham chiếu đến trạng thái phía máy chủ, không phải bản thân toàn bộ dữ liệu session. Người dùng có thể nhìn thấy cookie chứa ID nhưng không nên có khả năng suy ra nội dung session từ ID đó.

### 3.1. Session trong Servlet

Servlet API cung cấp `HttpSession` để lưu dữ liệu gắn với một phiên:

~~~java
@WebServlet("/cart")
public class CartServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        HttpSession session = request.getSession();

        String cartId = (String) session.getAttribute("cartId");
        if (cartId == null) {
            cartId = UUID.randomUUID().toString();
            session.setAttribute("cartId", cartId);
        }

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("Cart: " + cartId);
    }
}
~~~

`request.getSession()` tạo session nếu chưa có. Nếu chỉ muốn lấy session hiện tại mà không tạo mới, dùng `request.getSession(false)`; kết quả có thể là `null`.

Không nên lưu đối tượng quá lớn, connection, request/response hoặc dữ liệu không thể serialize an toàn vào session. Session thường sống lâu hơn một request và có thể được chia sẻ giữa nhiều request hoặc node máy chủ.

### 3.2. Session không phải cơ sở dữ liệu nghiệp vụ

Session thích hợp cho trạng thái tạm gắn với phiên làm việc, không nên trở thành nơi lưu lâu dài mọi dữ liệu của ứng dụng. Ví dụ, giỏ hàng có thể được tham chiếu bằng cart ID trong session, nhưng dữ liệu giỏ hàng cần tồn tại qua nhiều thiết bị hoặc sau khi đăng xuất thường nên được lưu trong kho dữ liệu bền vững gắn với tài khoản.

Nếu session mất do hết hạn, restart hoặc xóa cache, ứng dụng không nên làm mất dữ liệu nghiệp vụ đã được xác nhận. Hãy xác định rõ dữ liệu nào là tạm thời và dữ liệu nào cần tồn tại độc lập với session.

## 4. Phân biệt Cookie và Session

| Tiêu chí | Cookie | Session |
|---|---|---|
| Nơi lưu chính | Trình duyệt | Phía máy chủ hoặc session store |
| Dữ liệu được gửi qua mạng | Giá trị cookie được gửi theo request phù hợp | Thường chỉ gửi session ID trong cookie |
| Người dùng có thể sửa trực tiếp | Có | Không thể sửa dữ liệu session phía server chỉ bằng cách sửa cookie ID |
| Dung lượng | Nhỏ, giới hạn bởi trình duyệt và server | Phụ thuộc cấu hình lưu trữ, nhưng vẫn cần giới hạn |
| Vòng đời | Theo Expires/Max-Age hoặc vòng đời trình duyệt | Theo timeout, invalidation và chính sách lưu trữ |
| Ví dụ sử dụng | Theme, locale, session ID | Danh tính phiên, draft ngắn hạn, trạng thái quy trình |
| Rủi ro chính | Giả mạo giá trị, bị đánh cắp, gửi tự động | Session hijacking, fixation, lưu quá nhiều dữ liệu, chia sẻ sai phạm vi |

Cookie và session thường phối hợp với nhau: cookie mang session ID, còn session store giữ trạng thái. Tuy nhiên, ứng dụng cũng có thể dùng session ID qua URL hoặc cơ chế khác; cách đó thường không được khuyến nghị vì ID có thể rò qua lịch sử, log hoặc referrer.

## 5. Dữ liệu chuyển tiếp sau redirect là gì?

Trong ứng dụng web, sau khi xử lý một POST thành công, Controller thường chuyển hướng trình duyệt đến một URL khác. Mẫu này được gọi là **Post/Redirect/Get (PRG)**:

1. Trình duyệt gửi POST.
2. Máy chủ xử lý thao tác.
3. Máy chủ trả phản hồi redirect.
4. Trình duyệt gửi GET đến URL đích.
5. Trang kết quả được hiển thị.

PRG giúp người dùng refresh trang kết quả mà không gửi lại POST vừa thực hiện. Tuy nhiên, request GET là một request mới. Các thuộc tính model của request POST không tự động tồn tại ở request GET.

Có lúc cần chuyển một lượng dữ liệu nhỏ từ POST sang GET, chẳng hạn thông báo “Đã lưu hồ sơ”. Dữ liệu ngắn hạn đó thường được gọi là **flash data** hoặc **flash attributes**.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant B as Trình duyệt
    participant C1 as Controller POST
    participant F as Flash Store
    participant C2 as Controller GET

    User->>B: Gửi biểu mẫu
    B->>C1: POST /profile
    C1->>C1: Cập nhật hồ sơ
    C1->>F: Lưu thông báo tạm
    C1-->>B: Redirect /profile
    B->>C2: GET /profile
    C2->>F: Lấy flash data
    F-->>C2: Thông báo tạm
    C2-->>B: HTML + thông báo
    B-->>User: Hiển thị kết quả
~~~

Flash data có vòng đời ngắn, thường chỉ dành cho request kế tiếp phù hợp rồi bị loại bỏ sau khi được tiêu thụ. Nó phù hợp với thông báo thành công, cảnh báo hoặc lỗi ngắn sau redirect, không phải kho lưu trữ cho toàn bộ biểu mẫu hay dữ liệu nghiệp vụ.

## 6. Flash attributes trong Spring MVC

Spring MVC cung cấp `RedirectAttributes` để truyền dữ liệu khi redirect. Có hai cách dùng cần phân biệt:

- `addAttribute(...)`: thêm thuộc tính vào URL redirect, thường thành path variable hoặc query parameter.
- `addFlashAttribute(...)`: lưu dữ liệu tạm để request đích có thể nhận, không đưa dữ liệu đó vào URL.

Ví dụ:

~~~java
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
    redirectAttributes.addFlashAttribute(
            "successMessage",
            "Hồ sơ đã được cập nhật."
    );
    return "redirect:/profile";
}

@GetMapping("/profile")
public String profile() {
    return "profile/detail";
}
~~~

View đích có thể đọc flash attribute:

~~~html
<div th:if="${successMessage}" th:text="${successMessage}"></div>
~~~

Flash attributes thường được Spring lưu tạm bằng cơ chế FlashMap, thường dựa trên session ở ứng dụng web thông thường. FlashMap có thể gắn với đường dẫn và tham số của redirect để giảm khả năng dữ liệu bị tiêu thụ bởi request không liên quan. Chi tiết lưu trữ và cấu hình có thể phụ thuộc môi trường triển khai.

Không nên dùng flash attribute để chuyển mật khẩu, OTP, token truy cập hoặc dữ liệu nhạy cảm. Cũng không nên dùng nó để chuyển một object lớn hoặc trạng thái cần tồn tại qua nhiều bước.

## 7. Chọn nơi lưu dữ liệu theo phạm vi và vòng đời

Một câu hỏi thiết kế quan trọng là: dữ liệu cần tồn tại trong bao lâu và cần được chia sẻ ở đâu?

| Phạm vi | Cơ chế phù hợp | Ví dụ |
|---|---|---|
| Trong một lần xử lý request | Request attribute hoặc model của request | Lỗi binding, dữ liệu render trang hiện tại |
| Sang request GET kế tiếp | Flash attribute | Thông báo sau khi lưu thành công |
| Trong một phiên làm việc | Session | Trạng thái đăng nhập, mã draft ngắn hạn |
| Qua nhiều phiên hoặc thiết bị | Cơ sở dữ liệu hoặc kho lưu trữ bền vững | Đơn hàng, giỏ hàng gắn tài khoản, hồ sơ |
| Cần client giữ tùy chọn nhỏ | Cookie | Theme, locale |
| Cần chia sẻ giữa các hệ thống | API, token hoặc kho dữ liệu phù hợp | Reference ID hoặc trạng thái được quản lý bởi dịch vụ |

Không nên chọn session chỉ vì nó tiện để lấy dữ liệu ở request sau. Hãy xem dữ liệu có cần tồn tại khi người dùng đóng trình duyệt, đăng nhập ở thiết bị khác hoặc khi máy chủ khởi động lại không.

## 8. Session trong Spring MVC

Spring MVC có thể làm việc với `HttpSession` trực tiếp hoặc dùng `@SessionAttributes` cho dữ liệu model cần giữ trong phạm vi một quy trình của Controller.

### 8.1. Dùng HttpSession trực tiếp

~~~java
@PostMapping("/cart/items")
public String addItem(
        @RequestParam String productId,
        HttpSession session
) {
    CartDraft draft = (CartDraft) session.getAttribute("cartDraft");
    if (draft == null) {
        draft = new CartDraft();
    }

    draft.add(productId);
    session.setAttribute("cartDraft", draft);
    return "redirect:/cart";
}
~~~

Ví dụ này minh họa cách giữ một draft ngắn hạn. Trong ứng dụng thật, cần xác định rõ dữ liệu giỏ hàng có nên nằm trong session hay kho lưu trữ bền vững; đồng thời kiểm tra sản phẩm, giá và tồn kho từ nguồn tin cậy mỗi khi thực hiện thao tác nghiệp vụ.

### 8.2. Dùng @SessionAttributes cho quy trình của Controller

~~~java
@Controller
@RequestMapping("/checkout")
@SessionAttributes("checkoutDraft")
public class CheckoutController {

    @ModelAttribute("checkoutDraft")
    public CheckoutDraft checkoutDraft() {
        return new CheckoutDraft();
    }

    @PostMapping("/address")
    public String saveAddress(
            @ModelAttribute("checkoutDraft") CheckoutDraft draft,
            @Valid @ModelAttribute("addressForm") AddressForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            return "checkout/address";
        }

        draft.setAddress(form.toValue());
        return "redirect:/checkout/shipping";
    }

    @PostMapping("/complete")
    public String complete(
            @ModelAttribute("checkoutDraft") CheckoutDraft draft,
            SessionStatus sessionStatus
    ) {
        checkoutService.complete(draft);
        sessionStatus.setComplete();
        return "redirect:/orders/confirmation";
    }
}
~~~

`@SessionAttributes` yêu cầu Spring giữ các thuộc tính model được chỉ định trong session trong phạm vi quy trình Controller. Khi quy trình hoàn tất, `SessionStatus.setComplete()` báo cho Spring kết thúc việc lưu các thuộc tính đó. Nó không đồng nghĩa với việc hủy toàn bộ session HTTP hoặc đăng xuất người dùng.

Ví dụ trên được rút gọn để thể hiện cơ chế. Trong ứng dụng thực tế, cần có bước kiểm tra dữ liệu draft, xác thực quyền, xử lý lỗi nghiệp vụ và bảo đảm không dùng dữ liệu giá hoặc tồn kho cũ khi xác nhận cuối.

## 9. Vòng đời session và quản lý đăng nhập

Session có thể kết thúc theo nhiều cách:

- Người dùng đăng xuất và ứng dụng chủ động invalidate session.
- Session không hoạt động trong thời gian vượt quá timeout.
- Quản trị viên hoặc hệ thống vận hành thu hồi session.
- Session store bị xóa hoặc máy chủ mất trạng thái do cấu hình triển khai.

Khi đăng xuất, nên hủy session hiện tại và xóa cookie session theo đúng cấu hình ứng dụng. Ví dụ Servlet:

~~~java
@PostMapping("/logout")
public String logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }
    return "redirect:/login";
}
~~~

Container hoặc security framework thường quản lý cookie session. Nếu ứng dụng tự quản lý cookie, khi xóa cần gửi lại cookie cùng tên và phạm vi Domain/Path tương ứng với cookie ban đầu, đồng thời đặt thời hạn về quá khứ hoặc Max-Age bằng 0.

### 9.1. Session timeout

Timeout giới hạn thời gian session không hoạt động. Trong Servlet, có thể cấu hình timeout theo phút:

~~~java
session.setMaxInactiveInterval(20 * 60);
~~~

Giá trị trên minh họa 20 phút không hoạt động. Timeout cần cân bằng giữa trải nghiệm và mức độ nhạy cảm của ứng dụng. Hết timeout không nhất thiết đồng nghĩa với việc dữ liệu nghiệp vụ đã lưu bị xóa; chỉ trạng thái session tạm thời bị kết thúc.

### 9.2. Session fixation

Session fixation xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết. Sau khi đăng nhập, nếu ứng dụng tiếp tục dùng cùng ID, kẻ tấn công có thể lợi dụng nó.

Sau khi xác thực hoặc nâng quyền, ứng dụng nên đổi session ID hoặc tạo session mới theo cơ chế bảo vệ của framework. Spring Security có chiến lược session fixation protection; nên dùng cấu hình được hỗ trợ thay vì tự xử lý bằng mã tùy tiện.

## 10. Bảo mật cookie và session

Session ID thường là một thông tin có giá trị cao: ai nắm được ID hợp lệ có thể có cơ hội sử dụng phiên của người dùng. Cần bảo vệ cả cookie lẫn trạng thái phía máy chủ.

### 10.1. Dùng HTTPS và Secure

Cookie phiên nên được gửi qua HTTPS và gắn thuộc tính `Secure`. Nếu cookie bị gửi qua HTTP không mã hóa, người có khả năng quan sát mạng có thể đánh cắp session ID.

### 10.2. Dùng HttpOnly

`HttpOnly` ngăn JavaScript đọc cookie qua `document.cookie` trong trình duyệt thông thường. Nó giúp giảm khả năng đánh cắp cookie bằng một số dạng XSS, nhưng không ngăn script độc hại thực hiện request thay người dùng trong trang đang bị khai thác. Vẫn cần phòng chống XSS.

### 10.3. Chọn SameSite phù hợp

- `Strict`: hạn chế gửi cookie trong hầu hết ngữ cảnh điều hướng cross-site; có thể ảnh hưởng luồng liên kết từ bên ngoài.
- `Lax`: thường cho phép cookie trong một số điều hướng top-level an toàn, đồng thời giảm nhiều request cross-site khác.
- `None`: cho phép gửi cookie trong ngữ cảnh cross-site và yêu cầu `Secure` trong các trình duyệt hiện đại.

Lựa chọn phụ thuộc vào luồng đăng nhập, tích hợp bên thứ ba và kiến trúc ứng dụng. SameSite là một lớp bảo vệ CSRF, không thay thế token CSRF hoặc kiểm tra Origin/Referer khi phù hợp.

### 10.4. Không lưu dữ liệu nhạy cảm trong cookie dạng rõ

Không lưu mật khẩu, OTP, số thẻ hoặc quyền quản trị trực tiếp trong cookie. Mã hóa hoặc ký cookie cũng cần thiết kế khóa, thời hạn, thu hồi và chống phát lại phù hợp. Với trạng thái xác thực, nên dùng cơ chế session hoặc token được thiết kế cho mục đích đó.

### 10.5. Bảo vệ session store

Session store cần được giới hạn quyền truy cập, bảo vệ mạng và có chính sách thời hạn. Không lưu dữ liệu nhạy cảm không cần thiết. Nếu dùng Redis hoặc một kho tập trung, cần xác thực, mã hóa đường truyền và kiểm soát truy cập phù hợp.

## 11. Cookie trong Jakarta Servlet và cấu hình thuộc tính

Với Servlet API, có thể tạo cookie như sau:

~~~java
Cookie themeCookie = new Cookie("theme", "dark");
themeCookie.setPath("/");
themeCookie.setMaxAge(30 * 24 * 60 * 60);
themeCookie.setHttpOnly(true);
themeCookie.setSecure(true);
response.addCookie(themeCookie);
~~~

Ví dụ này phù hợp với cookie tùy chọn giao diện trong ứng dụng chạy HTTPS. `HttpOnly` có thể không cần nếu client phải đọc cookie bằng JavaScript; tuy nhiên, nếu không có nhu cầu đó, nên bật. Với cookie session do container quản lý, hãy cấu hình thuộc tính trong Servlet container hoặc framework thay vì tạo cookie session thủ công.

Tùy phiên bản Servlet API, cách thiết lập `SameSite` có thể khác. Một số phiên bản mới hỗ trợ thuộc tính cookie mở rộng; với phiên bản cũ, có thể cần cấu hình tại container hoặc reverse proxy. Không nên nối chuỗi header tùy tiện nếu framework đã cung cấp cơ chế cấu hình an toàn.

Với Spring, có thể dùng `ResponseCookie` để tạo cookie ứng dụng:

~~~java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .maxAge(Duration.ofDays(30))
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax")
        .build();

response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
~~~

Không dùng ví dụ cookie theme này để tự triển khai session authentication. Cookie xác thực cần tuân theo cấu hình và vòng đời do security framework quản lý.

## 12. Flash data, query parameter và session draft khác nhau thế nào?

Khi chuyển hướng, có nhiều cách truyền dữ liệu sang request tiếp theo. Cần chọn theo độ nhạy cảm và thời gian cần giữ.

| Cơ chế | Dữ liệu nằm ở đâu | Vòng đời | Phù hợp với |
|---|---|---|---|
| Query parameter | URL | Có thể tồn tại trong bookmark, history và log | Bộ lọc tìm kiếm, trang, tab, giá trị không nhạy cảm |
| Flash attribute | Kho tạm phía server/framework | Thường dùng ở request kế tiếp phù hợp | Thông báo thành công, cảnh báo ngắn |
| Session attribute | Session phía server | Đến khi xóa, timeout hoặc invalidate | Draft nhiều bước, trạng thái phiên |
| Database draft | Kho dữ liệu bền vững | Theo chính sách nghiệp vụ | Quy trình dài, có thể tiếp tục trên thiết bị khác |
| Cookie | Trình duyệt | Theo thời hạn cookie | Tùy chọn nhỏ cần giữ ở client |

Ví dụ query parameter:

~~~java
redirectAttributes.addAttribute("page", 2);
redirectAttributes.addAttribute("sort", "createdAt");
return "redirect:/orders";
~~~

URL đích có thể chứa `?page=2&sort=createdAt`. Dữ liệu này có thể bookmark và chia sẻ, nhưng không nên chứa bí mật hoặc dữ liệu cá nhân nhạy cảm.

Ví dụ flash attribute:

~~~java
redirectAttributes.addFlashAttribute(
        "notice",
        "Đơn hàng đã được tạo."
);
return "redirect:/orders/" + orderId;
~~~

Ví dụ session draft:

~~~java
session.setAttribute("checkoutDraft", draft);
return "redirect:/checkout/shipping";
~~~

Draft có thể được dùng qua nhiều request trong quy trình, nên cần kiểm soát quyền sở hữu, timeout, kích thước và thời điểm xóa.

## 13. Chọn cơ chế theo tình huống

### Tình huống A: Ghi nhận ngôn ngữ người dùng

Locale là tùy chọn nhỏ có thể lưu trong cookie nếu ứng dụng muốn duy trì lựa chọn qua nhiều phiên. Máy chủ cần xác thực giá trị locale theo danh sách được hỗ trợ, không dùng chuỗi tùy ý làm đường dẫn hoặc tên resource.

### Tình huống B: Hiển thị thông báo sau khi lưu hồ sơ

Dùng flash attribute để hiển thị “Hồ sơ đã cập nhật” sau redirect. Không cần tạo session draft lâu dài cho một thông báo chỉ xuất hiện một lần.

### Tình huống C: Duy trì trạng thái đăng nhập

Dùng cơ chế session hoặc security framework được cấu hình đúng. Cookie chỉ mang session ID hoặc credential token được thiết kế phù hợp; không lưu mật khẩu dạng rõ.

### Tình huống D: Thanh toán nhiều bước

Dữ liệu chưa hoàn tất có thể được lưu trong draft phía server hoặc database, gắn với người dùng và có thời hạn. Không lưu CVV, OTP hoặc bí mật thanh toán trong session draft. Trước bước xác nhận cuối, phải tải lại và kiểm tra giá, tồn kho và quyền từ nguồn tin cậy.

### Tình huống E: Giữ bộ lọc danh sách đơn hàng

Nếu bộ lọc không nhạy cảm và cần bookmark/share, query parameter thường phù hợp hơn session. URL mô tả trạng thái tìm kiếm rõ ràng và có thể tải lại.

## 14. Những lỗi thiết kế thường gặp

### Lưu quá nhiều dữ liệu vào session

Session phình to khi chứa toàn bộ entity, danh sách lớn hoặc dữ liệu lặp. Điều này tăng bộ nhớ, chi phí replication và nguy cơ xung đột khi nhiều request đồng thời. Chỉ lưu dữ liệu tạm cần thiết hoặc mã tham chiếu.

### Dùng cookie làm nơi lưu trạng thái nghiệp vụ

Cookie có thể bị sửa và được gửi từ client. Không dùng cookie để quyết định giá, vai trò, quyền truy cập hoặc trạng thái đơn hàng nếu không có cơ chế xác minh và thiết kế phù hợp. Dữ liệu quan trọng cần được xác định ở phía máy chủ.

### Đưa session ID vào URL

Session ID trong URL có thể xuất hiện trong lịch sử trình duyệt, log, bookmark và referrer. Hãy dùng cookie với thuộc tính bảo mật phù hợp cho ứng dụng web thông thường.

### Dùng flash attribute cho dữ liệu dài hạn

Flash data thường chỉ tồn tại đến request đích phù hợp. Nếu người dùng cần tiếp tục quy trình sau nhiều trang hoặc nhiều ngày, hãy dùng session draft có quản lý vòng đời hoặc lưu draft bền vững.

### Dùng session để thay thế cơ sở dữ liệu

Session có thể hết hạn hoặc bị xóa. Đơn hàng đã xác nhận, thanh toán và hồ sơ phải được lưu ở nơi bền vững theo yêu cầu nghiệp vụ.

### Không xóa dữ liệu session sau khi hoàn tất

Draft checkout hoặc trạng thái tạm có thể còn tồn tại sau khi hoàn tất, khiến request sau dùng lại dữ liệu cũ. Hãy xóa thuộc tính hoặc kết thúc phạm vi session attribute đúng lúc.

### Tin rằng SameSite đủ để chống CSRF

SameSite giúp giảm một số request cross-site nhưng không phải cơ chế duy nhất. Cần dùng CSRF token và kiểm tra bảo mật phù hợp với cách xác thực và luồng ứng dụng.

### Không đổi session ID sau đăng nhập

Nếu session ID cũ được giữ sau khi quyền của người dùng thay đổi, ứng dụng có thể gặp rủi ro session fixation. Hãy dùng cơ chế bảo vệ session fixation của framework.

## 15. Kiểm thử cookie, session và flash data

### Kiểm thử cookie

- Cookie được gửi với đúng Path, Domain và thời hạn.
- Cookie xác thực có Secure, HttpOnly và SameSite theo chính sách.
- Cookie bị xóa bằng đúng tên và phạm vi đã tạo.
- Giá trị cookie không hợp lệ bị từ chối hoặc bỏ qua an toàn.

### Kiểm thử session

- Request tiếp theo với session ID hợp lệ truy cập được trạng thái cần thiết.
- Session không tồn tại được xử lý phù hợp.
- Logout invalidate session.
- Session timeout kết thúc trạng thái tạm.
- Session ID được thay đổi theo chính sách sau xác thực/nâng quyền.
- Dữ liệu draft không thể bị truy cập bởi người dùng khác.

### Kiểm thử flash attributes và PRG

- POST thành công redirect đến đúng URL.
- GET kế tiếp nhận được thông báo flash.
- Thông báo không xuất hiện lại sau khi đã tiêu thụ.
- Dữ liệu không bị đưa vào URL khi dùng flash attribute.
- Refresh trang đích không lặp lại thao tác POST.

### Kiểm thử tích hợp

Kiểm tra luồng request qua security filter, Controller và session store. Với môi trường nhiều node, kiểm tra session có được chia sẻ hoặc định tuyến đúng theo cấu hình triển khai.

## 16. Checklist review trạng thái và vòng đời

- [ ] Mỗi loại dữ liệu có phạm vi và vòng đời được xác định rõ.
- [ ] Cookie chỉ chứa dữ liệu nhỏ, không nhạy cảm hoặc token được thiết kế phù hợp.
- [ ] Cookie session được cấu hình Secure, HttpOnly và SameSite theo yêu cầu.
- [ ] Session ID không được đưa vào URL.
- [ ] Session không chứa connection, request/response hoặc object lớn không cần thiết.
- [ ] Trạng thái nghiệp vụ bền vững được lưu trong kho dữ liệu phù hợp.
- [ ] Flash attributes chỉ dùng cho dữ liệu chuyển tiếp ngắn sau redirect.
- [ ] Query parameter không chứa bí mật và có thể được bookmark khi cần.
- [ ] Draft nhiều bước có kiểm tra quyền, timeout và cơ chế dọn dẹp.
- [ ] Logout và session fixation protection được cấu hình.
- [ ] CSRF được bảo vệ theo cơ chế phù hợp; SameSite chỉ là một lớp bổ sung.
- [ ] Có kiểm thử vòng đời, phạm vi và quyền truy cập của dữ liệu.

## Kết luận

Cookie lưu dữ liệu nhỏ ở trình duyệt và được gửi tự động theo phạm vi; session duy trì trạng thái phía máy chủ qua một mã định danh; flash attributes chuyển dữ liệu ngắn hạn sang request kế tiếp, thường sau redirect theo PRG. Hãy chọn cơ chế dựa trên nơi lưu, độ nhạy cảm, thời gian tồn tại và nhu cầu chia sẻ. Cookie cần thuộc tính bảo mật phù hợp, session cần timeout và quản lý vòng đời, còn flash data chỉ nên chứa thông tin chuyển tiếp ngắn. Khi phân biệt rõ các phạm vi này, Controller có thể điều phối request và redirect mà không biến cookie hoặc session thành nơi lưu trữ tùy tiện cho toàn bộ trạng thái nghiệp vụ.
