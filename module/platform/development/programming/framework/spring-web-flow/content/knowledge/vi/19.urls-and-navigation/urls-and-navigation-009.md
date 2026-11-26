# Đường dẫn tương đối, context path và reverse proxy

> **Chương:** URL và điều hướng  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Khi triển khai ứng dụng, một flow có thể chạy đúng ở máy phát triển nhưng lại sinh liên kết sai khi được đặt dưới context path, đổi servlet mapping hoặc đi qua reverse proxy. Bài học này giúp bạn hiểu cách trình duyệt giải quyết đường dẫn, cách Spring tạo URL theo ngữ cảnh request và cách cấu hình ứng dụng để URL công khai khớp với đường dẫn mà máy chủ nhìn thấy.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt URL tuyệt đối, đường dẫn tương đối, đường dẫn bắt đầu từ gốc website và đường dẫn theo context path.
- Giải thích context path, servlet mapping và flow mapping là những phần khác nhau của URL.
- Tạo liên kết và redirect có tính đến context path trong Spring MVC.
- Dùng URL do Spring Web Flow cung cấp để tiếp tục flow execution.
- Mô tả cách reverse proxy thay đổi scheme, host, port hoặc prefix của URL công khai.
- Cấu hình và kiểm tra forwarded headers theo mô hình triển khai đáng tin cậy.
- Chẩn đoán lỗi mất prefix, sai scheme, redirect vòng lặp và tài nguyên tĩnh không tải được.

## 1. Một URL có nhiều phần

URL mà người dùng nhìn thấy có thể được tạo bởi nhiều lớp: trình duyệt, reverse proxy, servlet container, Spring MVC và Spring Web Flow. Trước khi sửa một liên kết sai, hãy phân tách URL thành các phần.

Ví dụ URL công khai:

~~~text
https://booking.example.com/portal/booking/flow/start
~~~

Có thể đọc các thành phần:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | https | Giao thức trình duyệt sử dụng. |
| Host | booking.example.com | Tên miền công khai. |
| Port | mặc định của HTTPS | Cổng kết nối công khai; có thể được proxy chuyển tiếp sang cổng nội bộ khác. |
| Context path | /portal | Tiền tố ứng dụng trong servlet container nếu ứng dụng thực sự được triển khai dưới context này. |
| Servlet mapping | /booking/* hoặc / | Đường dẫn mà servlet nhận request, tùy cấu hình. |
| Flow mapping | /flow/* hoặc một mapping cụ thể | Phần đường dẫn được ứng dụng dùng để khởi chạy hoặc tiếp tục flow. |
| Flow execution | thông tin execution trong URL hoặc request | Định danh lần thực thi flow mà Spring Web Flow tiếp tục. |

Đây là cách phân tích minh họa. Cấu trúc chính xác phụ thuộc cách ứng dụng map DispatcherServlet, flow handler và cách reverse proxy chuyển tiếp request.

Ba khái niệm thường bị nhầm lẫn:

- **Context path** xác định ứng dụng web trong servlet container. Trong Servlet API, request cung cấp giá trị này qua getContextPath().
- **Servlet mapping** xác định URL pattern mà một servlet xử lý, ví dụ /app/* hoặc /.
- **Flow mapping** xác định URL mà Spring Web Flow dùng để nhận request khởi chạy hoặc tiếp tục flow. Mapping này phụ thuộc cấu hình handler của ứng dụng.

Context path có thể là chuỗi rỗng khi ứng dụng được triển khai ở root context. Không nên giả định ứng dụng luôn chạy tại / hoặc luôn có prefix cố định.

## 2. Đường dẫn tuyệt đối và đường dẫn tương đối trong trình duyệt

Trình duyệt giải quyết đường dẫn dựa trên URL hiện tại và thẻ base nếu trang có khai báo thẻ đó. Một dấu gạch chéo đầu đường dẫn làm thay đổi cách trình duyệt ghép URL.

Giả sử trang hiện tại có URL:

~~~text
https://booking.example.com/portal/booking/step
~~~

Các đường dẫn sau có kết quả khác nhau:

| Giá trị trong href/src | URL trình duyệt tạo ra | Nhận xét |
|---|---|---|
| next | https://booking.example.com/portal/booking/next | Tương đối với thư mục của URL hiện tại. |
| ../summary | https://booking.example.com/portal/summary | Đi lên một cấp đường dẫn. |
| /booking/next | https://booking.example.com/booking/next | Bắt đầu từ gốc host, bỏ qua /portal. |
| /portal/booking/next | https://booking.example.com/portal/booking/next | Đúng trong ví dụ này nhưng hard-code prefix. |
| ?tab=history | https://booking.example.com/portal/booking/step?tab=history | Giữ path, thay hoặc thêm query string. |
| https://docs.example.net/help | URL trên host khác | URL tuyệt đối gồm scheme và host. |

Điểm dễ gây lỗi là đường dẫn bắt đầu bằng /. Nó có nghĩa là gốc của website theo host, không có nghĩa là gốc của ứng dụng Spring. Khi ứng dụng nằm dưới /portal, liên kết /booking/next sẽ bỏ qua prefix đó.

Đường dẫn tương đối cũng phụ thuộc dấu / ở cuối URL hiện tại. Ví dụ:

- Trang tại /portal/booking/step có đường dẫn tương đối next được ghép thành /portal/booking/next.
- Trang tại /portal/booking/step/ có đường dẫn tương đối next được ghép thành /portal/booking/step/next.

Thẻ base href trong HTML còn có thể thay đổi gốc dùng để giải quyết các URL tương đối. Khi một liên kết hoạt động khác nhau giữa hai trang, hãy kiểm tra cả URL hiện tại và thẻ base trong HTML đã render.

### Tránh hard-code context path

Giả sử môi trường phát triển chạy tại root context nhưng môi trường staging chạy dưới /portal. Một liên kết cố định:

~~~html
<a href="/orders">Đơn hàng</a>
~~~

sẽ hoạt động ở root context nhưng có thể trỏ sai trong staging. Đường dẫn nên được tạo theo context của ứng dụng.

Với Thymeleaf, có thể dùng cú pháp URL expression:

~~~html
<a th:href="@{/orders}">Đơn hàng</a>
<img th:src="@{/assets/logo.svg}" alt="Logo"/>
<form th:action="@{/orders/search}" method="get">
    <input name="keyword"/>
    <button type="submit">Tìm</button>
</form>
~~~

Spring MVC integration của Thymeleaf xử lý context path khi tạo URL. Không cần ghép prefix bằng tay trong từng template.

Với JSP, dùng JSTL URL tag hoặc cơ chế URL của Spring để tạo đường dẫn theo context path. Tránh tự nối chuỗi context path vào URL ở nhiều nơi, vì cách đó dễ tạo đường dẫn lặp prefix hoặc thiếu prefix.

## 3. Context path trong Spring MVC

Servlet request cung cấp context path của ứng dụng. Trong controller, bạn có thể đọc giá trị này khi thật sự cần:

~~~java
@GetMapping("/debug/path")
@ResponseBody
public Map<String, String> inspectPath(HttpServletRequest request) {
    Map<String, String> result = new LinkedHashMap<>();
    result.put("contextPath", request.getContextPath());
    result.put("servletPath", request.getServletPath());
    result.put("requestURI", request.getRequestURI());
    return result;
}
~~~

Ví dụ khi ứng dụng được triển khai dưới context path /portal, request đến /portal/debug/path có thể cho kết quả:

~~~text
contextPath = /portal
servletPath = /debug/path
requestURI = /portal/debug/path
~~~

Kết quả cụ thể còn phụ thuộc servlet mapping và container. Dùng các giá trị này để quan sát request thực tế, không dùng một giá trị cố định lấy từ môi trường khác.

### Tạo URL trong controller

Khi cần xây dựng URL từ context path hiện tại, có thể dùng ServletUriComponentsBuilder:

~~~java
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

String ordersUrl = ServletUriComponentsBuilder
    .fromCurrentContextPath()
    .path("/orders")
    .build()
    .toUriString();
~~~

Cách này lấy base từ request hiện tại. Nếu request đã được xử lý đúng forwarded headers, base có thể phản ánh scheme, host và port công khai. Điều đó phụ thuộc cấu hình proxy và cơ chế forwarded-header của ứng dụng.

Đối với redirect nội bộ từ Spring MVC, thường nên dùng view name dạng:

~~~java
@PostMapping("/orders")
public String createOrder() {
    // Gọi service lưu đơn hàng ở đây.
    return "redirect:/orders";
}
~~~

Spring MVC xử lý redirect theo context của ứng dụng. Nếu reverse proxy có public prefix riêng, cần cấu hình forwarded request đúng để URL redirect được tạo ra phản ánh địa chỉ bên ngoài.

Không nối trực tiếp host hoặc scheme từ một header tùy ý vào URL redirect. Dữ liệu host không đáng tin có thể dẫn đến open redirect hoặc tạo liên kết trỏ sang tên miền do người gửi request kiểm soát.

## 4. URL của Spring Web Flow

Spring Web Flow quản lý một lần thực thi flow qua flow execution. Sau khi flow bắt đầu, các request tiếp theo phải tiếp tục đúng execution hiện tại. URL tiếp tục flow có thể chứa execution key hoặc thông tin điều phối tương ứng theo cấu hình.

Trong view Spring Web Flow, hãy dùng URL flow execution được framework đưa vào model, thường được expose dưới tên **flowExecutionUrl**, để đặt action của form. Không tự ghép context path, flow mapping và execution key bằng chuỗi.

Ví dụ cấu trúc form JSP:

~~~jsp
<form method="post" action="URL_FLOW_EXECUTION_DO_SPRING_WEB_FLOW_CUNG_CAP">
    <input name="bookingDate" type="date"/>
    <button type="submit" name="_eventId_next" value="next">
        Tiếp tục
    </button>
    <button type="submit" name="_eventId_cancel" value="cancel">
        Hủy
    </button>
</form>
~~~

Trong template thực tế, thay giá trị minh họa ở thuộc tính action bằng biến **flowExecutionUrl** do Spring Web Flow cung cấp cho view. Cú pháp xuất biến phụ thuộc JSP, Thymeleaf hoặc view technology của ứng dụng. Event id trong nút phải khớp với transition của view-state.

Các liên kết điều hướng bên trong flow nên được tạo theo cơ chế event và flow execution của Spring Web Flow. Không tự tạo URL đến một state nội bộ như thể state đó là một endpoint độc lập. Flow cần nhận đúng request cùng execution hiện tại để duy trì scope, lịch sử và quy tắc điều hướng.

### Phân biệt URL khởi chạy và URL tiếp tục flow

- **URL khởi chạy** được dùng để bắt đầu một flow mới. Ứng dụng có thể map nó qua Spring MVC hoặc FlowHandlerMapping.
- **URL tiếp tục** được dùng khi flow đã có execution. Framework tạo URL này để request tiếp theo được gắn với đúng execution.
- **URL kết thúc hoặc redirect ra ngoài** là điều hướng sau khi flow hoàn tất. Đích có thể là một controller hoặc một địa chỉ công khai khác.

Không tái sử dụng URL tiếp tục của một flow đã kết thúc hoặc hết hạn như URL khởi chạy mới. Nếu người dùng mở bookmark cũ, ứng dụng cần xử lý execution không còn hợp lệ theo chính sách phục hồi của flow.

## 5. Reverse proxy thay đổi URL công khai như thế nào?

Reverse proxy đứng trước ứng dụng và nhận request từ trình duyệt, sau đó chuyển tiếp đến máy chủ ứng dụng. Proxy có thể kết thúc TLS, đổi host, đổi port hoặc thêm/bỏ một prefix.

Ví dụ:

~~~text
Trình duyệt
  https://example.com/portal/booking/flow
           |
           v
Reverse proxy
  nhận /portal/booking/flow
  chuyển tiếp đến http://spring-app:8080/booking/flow
           |
           v
Spring application
  nhìn thấy request nội bộ /booking/flow
~~~

Trong mô hình này, người dùng truy cập bằng HTTPS và prefix /portal, nhưng ứng dụng phía sau có thể chỉ nhìn thấy HTTP và path /booking/flow. Nếu ứng dụng tự tạo redirect dựa trên request nội bộ mà không biết thông tin bên ngoài, nó có thể trả về:

~~~text
http://spring-app:8080/booking/flow
~~~

hoặc:

~~~text
https://example.com/booking/flow
~~~

Cả hai đều có thể sai với trình duyệt, vì URL công khai cần giữ HTTPS và prefix /portal.

Proxy thường gửi thông tin chuyển tiếp qua các header:

| Header | Thông tin thường biểu đạt |
|---|---|
| Forwarded | Thông tin chuẩn hóa theo RFC về host, proto và các thuộc tính chuyển tiếp. |
| X-Forwarded-Proto | Scheme mà client dùng để kết nối tới proxy, ví dụ https. |
| X-Forwarded-Host | Host công khai mà client truy cập. |
| X-Forwarded-Port | Port công khai. |
| X-Forwarded-Prefix | Prefix công khai mà proxy thêm vào hoặc giữ lại; đây là quy ước phổ biến, không phải header chuẩn hóa trong RFC Forwarded. |

Không phải mọi proxy đều gửi đủ các header trên. Một số cấu hình giữ nguyên prefix trong path gửi đến backend; cấu hình khác loại bỏ prefix trước khi chuyển tiếp. Ứng dụng và proxy phải thống nhất cách biểu diễn này.

### Hai mô hình xử lý prefix

**Mô hình A: proxy giữ prefix khi chuyển tiếp**

Trình duyệt gửi /portal/orders; proxy chuyển tiếp request vẫn có path /portal/orders. Ứng dụng có thể được triển khai dưới context path /portal hoặc có mapping tương ứng.

**Mô hình B: proxy bỏ prefix trước khi chuyển tiếp**

Trình duyệt gửi /portal/orders; proxy chuyển tiếp /orders đến ứng dụng chạy ở root context. Ứng dụng cần biết public prefix /portal để tạo redirect và URL công khai chính xác. Tùy phiên bản Spring và nền tảng, thông tin prefix có thể được xử lý qua forwarded-header support hoặc cơ chế cấu hình riêng. Không giả định mọi Servlet container và mọi phiên bản framework đều tự động áp dụng X-Forwarded-Prefix.

Nếu proxy thêm prefix nhưng không chuyển tiếp thông tin đó và ứng dụng cũng không được cấu hình để biết prefix, các URL do server tạo ra thường thiếu /portal. Nếu cả proxy và ứng dụng cùng thêm prefix, URL có thể thành /portal/portal/orders.

## 6. Cấu hình forwarded headers an toàn

Spring hỗ trợ forwarded headers để ứng dụng nhận biết địa chỉ mà client dùng khi đi qua proxy. Tùy phiên bản Spring Boot, có thể cấu hình chiến lược xử lý forwarded headers qua thuộc tính:

~~~properties
server.forward-headers-strategy=framework
~~~

Các giá trị và hành vi chi tiết phụ thuộc phiên bản Spring Boot và môi trường triển khai. Một số nền tảng có thể cần chiến lược native; một số ứng dụng Servlet truyền thống có thể cấu hình ForwardedHeaderFilter hoặc ForwardedHeaderTransformer theo phiên bản framework đang dùng.

Trước khi bật, hãy xác định:

1. Proxy nào là điểm vào đáng tin cậy.
2. Proxy có xóa các forwarded header do client tự gửi và ghi lại giá trị chính xác không.
3. Proxy có giữ prefix hay loại prefix trước khi gửi request đến backend.
4. Spring Boot/Spring Framework phiên bản nào đang được dùng.
5. Ứng dụng được triển khai dưới context path nào.
6. URL công khai kỳ vọng cho redirect, asset, link và flow execution là gì.

### Chỉ tin forwarded headers từ proxy đáng tin cậy

Các header như X-Forwarded-Host và X-Forwarded-Proto có thể bị client giả mạo nếu request đi thẳng đến ứng dụng hoặc proxy không lọc header. Nếu ứng dụng tin giá trị giả, nó có thể tạo redirect đến host không mong muốn, sinh URL sai hoặc làm sai logic bảo mật.

Cấu hình proxy nên:

- Xóa forwarded headers do client gửi từ bên ngoài.
- Ghi lại các header bằng giá trị proxy xác định từ kết nối thực tế.
- Chỉ cho phép backend nhận request qua proxy hoặc mạng nội bộ đáng tin cậy.
- Không cho phép client tự quyết định host, scheme hoặc prefix mà ứng dụng sẽ tin.

Không bật forwarded-header processing một cách mù quáng nếu backend vẫn có thể truy cập trực tiếp từ mạng không tin cậy.

## 7. Kết hợp context path và proxy trong môi trường triển khai

Giả sử có ba môi trường:

| Môi trường | URL người dùng truy cập | Cách ứng dụng có thể nhìn thấy |
|---|---|---|
| Local | http://localhost:8080/ | Root context, không có proxy. |
| Staging | https://staging.example.com/portal/ | Proxy có thể bỏ prefix trước khi chuyển tiếp. |
| Production | https://app.example.com/customer/ | Proxy có thể giữ prefix hoặc chuyển thành context path của ứng dụng. |

Không nên tạo ba bộ template chỉ để thay đổi prefix. Hãy dùng URL expression của view technology, URL builder của Spring và URL flow execution do Spring Web Flow cung cấp.

Với cấu hình ứng dụng, cần kiểm tra cả hai phía:

- **Phía proxy:** public path, rewrite rule, upstream path, forwarded headers, TLS termination và host.
- **Phía ứng dụng:** context path, servlet mapping, flow mapping, forwarded-header strategy, session cookie path và redirect.

Nếu ứng dụng đặt context path /portal nhưng proxy cũng prepend /portal trước một ứng dụng đã được cấu hình nhận prefix, request có thể bị lặp đường dẫn. Nếu ứng dụng ở root context và proxy loại bỏ prefix, URL được tạo từ getContextPath() có thể là chuỗi rỗng; muốn giữ prefix công khai phải xử lý forwarded prefix đúng cách.

### Cookie và session path

Reverse proxy và context path còn ảnh hưởng phạm vi cookie. Nếu cookie session có Path không khớp với public prefix, trình duyệt có thể không gửi cookie cho request tiếp theo hoặc có thể gửi cookie ở phạm vi không mong muốn.

Khi triển khai dưới prefix, hãy kiểm tra:

- Cookie session có Secure khi truy cập HTTPS không.
- Cookie có HttpOnly và SameSite phù hợp với luồng đăng nhập không.
- Path của cookie có phù hợp với ứng dụng công khai không.
- Proxy có sửa cookie path hoặc domain không.
- Flow execution có tiếp tục được sau redirect và qua các request kế tiếp không.

Không chỉnh cookie path để chữa lỗi URL nếu chưa xác định nguyên nhân. Cookie session và flow execution là hai cơ chế liên quan nhưng khác nhau; cả hai cần hoạt động đúng để flow nhiều bước được duy trì.

## 8. Tài nguyên tĩnh và URL trong JavaScript

Các URL của CSS, JavaScript, ảnh và request fetch cũng chịu ảnh hưởng của context path và reverse proxy.

Ví dụ dễ lỗi:

~~~html
<link rel="stylesheet" href="/css/app.css"/>
<script src="/js/booking.js"></script>
<img src="/images/logo.svg" alt="Logo"/>
~~~

Các URL bắt đầu bằng / được trình duyệt giải quyết từ gốc host. Khi ứng dụng nằm dưới /portal, chúng có thể trỏ ra ngoài context path.

Với Thymeleaf, tạo URL theo context:

~~~html
<link rel="stylesheet" th:href="@{/css/app.css}"/>
<script th:src="@{/js/booking.js}"></script>
<img th:src="@{/images/logo.svg}" alt="Logo"/>
~~~

Với JavaScript, có thể render một URL base từ template hoặc cung cấp một cấu hình công khai do server tạo. Ví dụ:

~~~html
<div id="booking-config"
     data-api-base="/portal/api"></div>
~~~

JavaScript đọc thuộc tính này để gọi API:

~~~javascript
const config = document.getElementById("booking-config");
const apiBase = config.dataset.apiBase;

fetch(apiBase + "/availability");
~~~

Đây là ví dụ minh họa cho việc server cung cấp base path. Trong ứng dụng thực tế, giá trị /portal/api cần được sinh theo context path hoặc public prefix đã cấu hình, không hard-code giống nhau cho mọi môi trường. Với request có URL tương đối, hãy kiểm tra URL trang và thẻ base để tránh ghép sai đường dẫn.

## 9. Chẩn đoán lỗi URL và điều hướng

Khi URL sai, hãy so sánh bốn giá trị: URL trình duyệt yêu cầu, path proxy nhận, path proxy chuyển tiếp và URL mà ứng dụng tạo trong response.

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Link hoạt động ở local nhưng mất prefix ở staging | Dùng đường dẫn bắt đầu bằng / hoặc hard-code root path | Kiểm tra HTML render và thay bằng URL expression theo context. |
| URL có prefix lặp hai lần | Proxy prepend prefix đồng thời ứng dụng cũng thêm prefix | Kiểm tra rewrite rule, context path và forwarded prefix. |
| Redirect trả về HTTP dù client dùng HTTPS | Ứng dụng không nhận Forwarded hoặc X-Forwarded-Proto | Kiểm tra TLS termination và forwarded-header strategy. |
| Redirect trỏ đến hostname nội bộ | Ứng dụng dùng host của upstream request | Kiểm tra Forwarded/X-Forwarded-Host và cấu hình proxy tin cậy. |
| Static asset trả 404 | URL asset bắt đầu từ gốc host hoặc prefix không đúng | Kiểm tra src/href đã render và đường dẫn proxy chuyển tiếp. |
| Flow mất execution sau khi điều hướng | Form action không dùng flowExecutionUrl hoặc session cookie không được gửi | Kiểm tra action của form, event id, cookie và flow execution key. |
| Refresh hoặc Back tạo URL cũ | Trình duyệt giữ URL execution trước đó hoặc flow đã hết hạn | Kiểm tra vòng đời execution và chính sách phục hồi. |
| Chỉ lỗi khi mở ứng dụng qua proxy | Proxy rewrite path hoặc forwarded headers không đồng nhất | So sánh request bên ngoài và request backend. |

### Quy trình điều tra từng bước

1. Sao chép URL công khai từ thanh địa chỉ trình duyệt.
2. Trong Network, chọn request lỗi và ghi lại Request URL, status, redirect Location và cookie có liên quan.
3. Kiểm tra HTML đã render để xem href, src và action có chứa context path hay public prefix không.
4. Ghi lại path mà reverse proxy chuyển tiếp đến backend.
5. Trong ứng dụng, tạm thời ghi nhận getContextPath(), getServletPath() và getRequestURI() ở môi trường thử nghiệm.
6. Kiểm tra forwarded headers sau khi proxy đã chuẩn hóa chúng.
7. Xác nhận URL redirect và URL flow execution có dùng đúng host, scheme, prefix và session.

Không ghi giá trị cookie session hoặc flow execution key đầy đủ vào log chia sẻ. Chỉ ghi thông tin cần thiết để chẩn đoán, che hoặc loại bỏ các giá trị định danh phiên.

## 10. Checklist trước khi triển khai

- [ ] Các liên kết nội bộ được tạo theo context path.
- [ ] Không hard-code prefix của môi trường trong template hoặc JavaScript.
- [ ] Đã phân biệt context path, servlet mapping và flow mapping.
- [ ] Form của Spring Web Flow dùng URL flow execution do framework cung cấp.
- [ ] Event id trên form khớp với transition trong flow definition.
- [ ] Redirect nội bộ được tạo qua cơ chế Spring MVC.
- [ ] Proxy và ứng dụng thống nhất việc giữ hoặc loại public prefix.
- [ ] Forwarded headers được ghi lại bởi proxy đáng tin cậy và được backend xử lý theo đúng phiên bản framework.
- [ ] Backend không tin forwarded headers do client tùy ý gửi.
- [ ] Scheme, host và port trong redirect phản ánh URL công khai.
- [ ] CSS, JavaScript, ảnh và fetch API hoạt động dưới context path.
- [ ] Cookie session có path và thuộc tính bảo mật phù hợp.
- [ ] Đã kiểm tra flow execution qua nhiều request, redirect, refresh và Back.
- [ ] Đã thử nghiệm ở cả root context và context có prefix nếu ứng dụng hỗ trợ nhiều cách triển khai.

## Kết luận

Đường dẫn tương đối được trình duyệt giải quyết dựa trên URL hiện tại; context path xác định vị trí ứng dụng trong servlet container; reverse proxy có thể thay đổi scheme, host, port hoặc prefix mà ứng dụng nhìn thấy. Hãy tạo URL qua cơ chế của Spring MVC và Spring Web Flow, thống nhất quy tắc rewrite với proxy, xử lý forwarded headers từ nguồn đáng tin cậy và kiểm tra URL ở cả phía trình duyệt lẫn backend. Khi các lớp này đồng bộ, flow execution, redirect và tài nguyên tĩnh sẽ hoạt động nhất quán giữa local, staging và production.
