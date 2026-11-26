# Tích hợp CSRF vào form và yêu cầu phát sự kiện

Trong Spring Web Flow, một biểu mẫu thường gửi event để chuyển từ state này sang state khác: tiếp tục, xác nhận, lưu hoặc hủy. Những request thay đổi trạng thái cần được bảo vệ khỏi Cross-Site Request Forgery (CSRF). Nếu kẻ tấn công khiến trình duyệt của người dùng đã đăng nhập gửi một POST ngoài ý muốn, request đó có thể cố thực hiện event trên flow execution hiện tại.

Bài này thuộc chương **Bảo vệ flow** của module **SPRING_WEB_FLOW**. Bạn sẽ tích hợp token CSRF của Spring Security vào biểu mẫu Web Flow, hiểu thứ tự xử lý giữa security filter và FlowHandlerAdapter, xử lý token thiếu hoặc hết hạn và kiểm thử các event được bảo vệ. Mục tiêu là để mỗi yêu cầu thay đổi dữ liệu đều được xác thực nguồn gửi trước khi flow xử lý event.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích CSRF và vì sao flow event qua POST cần token bảo vệ.
- Bật CSRF protection trong Spring Security cho ứng dụng Spring MVC/Web Flow.
- Gửi token trong hidden field của form hoặc header của request AJAX.
- Giữ nguyên URL của flow execution khi gửi event.
- Phân biệt lỗi CSRF 403 với lỗi event hoặc transition của Spring Web Flow.
- Thiết kế form để token không bị binding thành dữ liệu nghiệp vụ.
- Kiểm thử request có token hợp lệ, thiếu token và token sai.

## 1. CSRF có thể tác động đến flow như thế nào?

Trình duyệt tự gửi cookie phiên đến website mà người dùng đã đăng nhập. Kẻ tấn công có thể lợi dụng cơ chế đó để khiến trình duyệt gửi request đến website, dù người dùng không chủ động thao tác trên website đó. Nếu ứng dụng chỉ dựa vào cookie phiên để nhận diện người dùng, một POST giả mạo có thể được xử lý như request của người dùng hợp lệ.

Trong Spring Web Flow, request POST thường mang theo hai thông tin khác nhau:

- **Execution key** xác định flow execution và snapshot mà request muốn tiếp tục.
- **Event ID** cho biết người dùng muốn flow thực hiện hành động nào, ví dụ `continue` hoặc `confirm`.

Hai thông tin này không chứng minh request được tạo từ form hợp lệ của ứng dụng. Token CSRF bổ sung bằng chứng rằng request có token do máy chủ cấp trong ngữ cảnh người dùng đang sử dụng.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant A as Website ứng dụng
    participant S as Spring Security
    participant F as Spring Web Flow

    U->>A: Mở form của flow
    A->>B: HTML + CSRF token + flowExecutionUrl
    U->>B: Gửi event continue
    B->>A: POST execution key + event + token
    A->>S: Đi qua security filter chain
    S->>S: Kiểm tra CSRF token
    alt Token hợp lệ
        S->>F: Chuyển request đến FlowHandlerAdapter
        F->>F: Xử lý event và transition
        F-->>B: Redirect đến URL execution tiếp theo
    else Token thiếu hoặc sai
        S-->>B: 403 Forbidden
    end
~~~

Khi token hợp lệ, request mới đi tiếp đến Spring Web Flow để xử lý event. Khi token thiếu hoặc không hợp lệ, Spring Security từ chối request trước khi FlowHandlerAdapter xử lý flow. Vì vậy, lỗi CSRF thường không phải lỗi transition và không nên cố sửa bằng cách thêm một transition có tên `csrf` vào flow XML.

## 2. Bật CSRF protection trong Spring Security

Với cấu hình Java hiện đại, CSRF protection được bật mặc định trong Spring Security cho các HTTP method có thể thay đổi trạng thái. Có thể thể hiện rõ cấu hình như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/assets/**").permitAll()
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Cấu hình này yêu cầu người dùng đã xác thực cho các URL còn lại và giữ CSRF protection theo mặc định. Trong ứng dụng thực tế, hãy ghép quy tắc phân quyền phù hợp với từng flow và từng chức năng. **Không tắt CSRF protection chỉ để làm cho form Web Flow hoạt động.**

Theo mặc định, Spring Security không yêu cầu token cho các method an toàn như GET, HEAD, OPTIONS và TRACE; token được kiểm tra cho các method có thể thay đổi trạng thái như POST, PUT, PATCH và DELETE. Vì vậy, các event làm thay đổi dữ liệu nên được gửi qua POST. Không dùng GET để xác nhận giao dịch, hủy hồ sơ hoặc thay đổi trạng thái nghiệp vụ.

Một flow thường có GET để khởi chạy hoặc hiển thị màn hình, rồi POST để gửi event. Ví dụ:

| Request | Mục đích | CSRF token |
|---|---|---|
| `GET /checkout` | Khởi chạy flow hoặc hiển thị màn hình | Không bắt buộc theo mặc định |
| `GET /checkout?execution=e1s2` | Render snapshot hiện tại | Không bắt buộc theo mặc định |
| `POST /checkout?execution=e1s2` | Gửi event `continue` hoặc `confirm` | Bắt buộc |
| `POST /checkout?execution=e1s2` | Gửi event hủy hoặc cập nhật dữ liệu | Bắt buộc |

CSRF bảo vệ nguồn gốc request trong ngữ cảnh trình duyệt; nó không thay thế xác thực người dùng, phân quyền trên hồ sơ hoặc kiểm tra nghiệp vụ. Mỗi action vẫn phải xác minh người dùng có quyền thao tác trên đối tượng mà flow đang xử lý.

## 3. Đưa token vào form Web Flow

Một form Web Flow cần gửi request về URL thực thi hiện tại, thường được cung cấp qua `flowExecutionUrl`. Khi dùng HTML form thuần, thêm hidden input mang token CSRF:

~~~jsp
<form method="post" action="${flowExecutionUrl}">
    <input type="hidden"
           name="${_csrf.parameterName}"
           value="${_csrf.token}"/>

    <label for="recipient">Người nhận</label>
    <input id="recipient" name="recipient" type="text"/>

    <button type="submit"
            name="_eventId_continue"
            value="continue">Tiếp tục</button>
</form>
~~~

Các giá trị có vai trò riêng:

- `flowExecutionUrl` gửi request đến flow execution hiện tại, giúp Spring Web Flow biết cần tiếp tục hành trình nào.
- `_csrf.parameterName` cung cấp tên tham số token theo cấu hình Spring Security.
- `_csrf.token` là token mà máy chủ cấp cho form hiện tại.
- `_eventId_continue` phát event `continue` để transition tương ứng trong flow xử lý.

Không hardcode tên tham số hoặc token nếu có thể lấy chúng từ request attribute `_csrf`. Cách này giúp form hoạt động theo tên parameter/header đã cấu hình cho ứng dụng.

Ví dụ flow XML:

~~~xml
<view-state id="edit" view="checkout/edit" model="checkout">
    <transition on="continue" to="review"/>
    <transition on="cancel" to="cancelled"/>
</view-state>

<view-state id="review" view="checkout/review">
    <transition on="confirm" to="completed"/>
    <transition on="back" to="edit"/>
</view-state>

<end-state id="completed" view="checkout/completed"/>
<end-state id="cancelled" view="checkout/cancelled"/>
~~~

Các transition vẫn nhận event theo tên đã khai báo. CSRF filter kiểm tra request trước khi event được chuyển đến flow. Nếu token sai, transition `continue`, `cancel` hoặc `confirm` không được chạy.

### Khi dùng Spring form tag

Với JSP dùng thư viện Spring form tag, tích hợp Spring MVC có thể tự thêm hidden CSRF field thông qua `RequestDataValueProcessor` do Spring Security cung cấp. Ví dụ:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form modelAttribute="checkout"
           action="${flowExecutionUrl}"
           method="post">

    <form:input path="recipient"/>

    <button type="submit"
            name="_eventId_continue"
            value="continue">Tiếp tục</button>
</form:form>
~~~

Trong cấu hình tích hợp này, không thêm một hidden token thứ hai nếu Spring form tag đã tự chèn token. Nếu dùng HTML form thuần, hãy tự thêm hidden input như ví dụ trước. Kiểm tra HTML được render trong trình duyệt để xác nhận chỉ có một token field hợp lệ.

Nếu ứng dụng dùng template engine khác, hãy dùng cách tích hợp CSRF token tương ứng của template engine hoặc render hidden field tường minh. Điều quan trọng là token thực sự nằm trong request gửi đến URL execution.

## 4. Gửi token bằng header cho AJAX

Nếu view phát event bằng JavaScript thay vì form submit truyền thống, token có thể được gửi qua header. Spring Security cung cấp các giá trị trong request attribute `_csrf`, gồm tên header và token.

Ví dụ JSP xuất token vào data attribute:

~~~jsp
<meta name="csrf-header" content="${_csrf.headerName}"/>
<meta name="csrf-token" content="${_csrf.token}"/>
~~~

JavaScript đọc các giá trị đó và gửi request:

~~~javascript
const csrfHeader = document.querySelector(
    'meta[name="csrf-header"]'
).content;

const csrfToken = document.querySelector(
    'meta[name="csrf-token"]'
).content;

const response = await fetch(flowExecutionUrl, {
    method: "POST",
    headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        [csrfHeader]: csrfToken
    },
    body: new URLSearchParams({
        "_eventId_continue": "continue"
    })
});
~~~

`flowExecutionUrl` trong ví dụ là URL do view của Web Flow cung cấp. Request phải gửi cookie phiên của cùng origin; với Fetch mặc định, credentials được gửi cho same-origin request. Nếu gọi khác origin, cần cấu hình CORS và credentials có chủ đích, đồng thời không được xem CORS là cơ chế thay thế CSRF.

Không đưa token vào query string hoặc URL. URL có thể bị ghi vào access log, lịch sử trình duyệt, analytics hoặc header Referer. Token nên đi trong request body hoặc header. Tránh ghi token vào log và không lưu token lâu dài trong local storage nếu ứng dụng có thể dùng cơ chế cấp token theo phiên.

## 5. Giữ token tách khỏi dữ liệu binding của flow

CSRF token là dữ liệu bảo vệ request, không phải một thuộc tính nghiệp vụ của đối tượng biểu mẫu. Không tạo thuộc tính `csrfToken` trong form model chỉ để nhận token, và không lưu token vào `flowScope`.

Nếu flow dùng binding allowlist, hãy chỉ cho phép các trường nghiệp vụ cần thiết như `recipient`, `address` hoặc `deliveryOption`. Các tham số điều khiển như `_eventId_continue` và token CSRF cần được xử lý theo cơ chế của Web Flow/Spring Security, không được coi là dữ liệu người dùng cần lưu vào đối tượng nghiệp vụ.

Ví dụ đối tượng form chỉ chứa dữ liệu nghiệp vụ:

~~~java
public class CheckoutForm {

    private String recipient;
    private String deliveryOption;

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getDeliveryOption() {
        return deliveryOption;
    }

    public void setDeliveryOption(String deliveryOption) {
        this.deliveryOption = deliveryOption;
    }
}
~~~

Cách tách này làm rõ trách nhiệm: Spring Security xác minh token, Spring Web Flow định tuyến event và binding dữ liệu form, còn service nghiệp vụ kiểm tra và lưu dữ liệu. Không dùng token CSRF làm mã định danh flow, quyền truy cập hay bằng chứng rằng người dùng được phép xác nhận một giao dịch.

## 6. Xử lý token thiếu, sai hoặc hết hạn

Nếu request POST không có token hoặc token không khớp với token mà server mong đợi, Spring Security từ chối request với **403 Forbidden**. Vì filter chạy trước FlowHandlerAdapter, flow action và transition chưa được thực thi.

Những nguyên nhân thường gặp:

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Form POST trả 403 | Hidden token không được render hoặc bị thiếu khi submit | Kiểm tra HTML thực tế, form action và token field. |
| AJAX trả 403 | Header name hoặc token không đúng | Đọc `_csrf.headerName` và `_csrf.token` từ trang hiện tại. |
| Form cũ đột nhiên không gửi được | Session hết hạn hoặc token đã được thay đổi sau đăng nhập/đăng xuất | Tải lại form để nhận token mới và khởi chạy/tiếp tục flow theo chính sách ứng dụng. |
| Spring form tag tạo hai token field | Vừa dùng tự động chèn token vừa thêm hidden input thủ công | Chỉ chọn một cách chèn token. |
| Flow không nhận event | Request bị chặn ở security filter hoặc URL execution không đúng | Phân biệt response 403 của security với lỗi mapping/event của Web Flow. |
| Upload multipart trả 403 | Token không được gửi theo cách mà filter có thể đọc trước khi multipart được phân tích | Dùng header token cho upload AJAX hoặc cấu hình thứ tự multipart/security phù hợp. |

Thông báo 403 cho người dùng nên ngắn gọn, chẳng hạn yêu cầu tải lại biểu mẫu vì phiên bảo vệ đã hết hạn. Không hiển thị token, stack trace hoặc chi tiết nội bộ. Với thao tác quan trọng, trước khi cho phép gửi lại, hãy kiểm tra trạng thái nghiệp vụ để tránh lặp một giao dịch đã được xử lý.

### Lưu ý riêng cho multipart

Với multipart request, thứ tự phân tích request có ý nghĩa. CSRF filter có thể chạy trước multipart resolver của Spring MVC; khi đó token nằm trong một multipart field có thể chưa đọc được tại thời điểm filter kiểm tra. Không nên giả định hidden field luôn hoạt động giống form URL-encoded.

Với upload bằng JavaScript, cách thường dùng là gửi token trong header CSRF. Nếu dùng form multipart truyền thống, cần cấu hình multipart parsing trước security filter theo hướng dẫn của phiên bản Spring Security/Servlet container, sau khi cân nhắc việc request chưa xác thực có thể ghi dữ liệu tạm lên đĩa. Không đưa token vào query string để né vấn đề thứ tự filter.

## 7. Bảo vệ toàn bộ event thay đổi trạng thái

Hãy rà soát các event của flow và bảo đảm mọi thao tác thay đổi dữ liệu đều phát sinh từ request được CSRF bảo vệ. Ví dụ:

| Event | Tác động | Cách gửi |
|---|---|---|
| `continue` | Lưu dữ liệu biểu mẫu và sang bước tiếp theo | POST có token |
| `back` | Chuyển state về bước trước; nếu chỉ điều hướng, vẫn nên dùng POST nhất quán với flow form | POST có token |
| `confirm` | Xác nhận hoặc ghi nhận giao dịch | POST có token |
| `cancel` | Hủy quy trình hoặc giải phóng tài nguyên | POST có token |
| `delete` | Xóa dữ liệu nghiệp vụ | POST/DELETE có token |

Đừng dựa vào tên event để suy ra request an toàn. Nếu một URL GET có thể phát event làm thay đổi dữ liệu, CSRF protection mặc định có thể không kiểm tra token cho request đó. Hãy thiết kế GET chỉ để đọc hoặc render; các thao tác có side effect phải dùng method không an toàn và được bảo vệ.

CSRF cũng không ngăn người dùng hợp lệ gửi event không được phép về mặt nghiệp vụ. Action cần xác minh quyền trên đối tượng, trạng thái hiện tại và điều kiện chuyển bước. Ví dụ, token hợp lệ không có nghĩa người dùng được phép xác nhận hồ sơ thuộc người khác.

## 8. Kiểm thử với MockMvc

Spring Security Test cung cấp request post processor `csrf()` để tạo request có token hợp lệ trong kiểm thử MockMvc. Có thể kiểm tra cả trường hợp token đúng và token sai.

Ví dụ kiểm thử request event:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.util.UriComponentsBuilder;

class CheckoutCsrfTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void acceptsFlowEventWithValidCsrfToken() throws Exception {
        MvcResult started = mockMvc.perform(get("/checkout"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                started.getRequest().getSession(false);
        String location = started.getResponse().getHeader("Location");
        String executionKey = UriComponentsBuilder
                .fromUriString(location)
                .build()
                .getQueryParams()
                .getFirst("execution");

        mockMvc.perform(post("/checkout")
                        .session(session)
                        .param("execution", executionKey)
                        .param("_eventId_continue", "continue")
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void rejectsFlowEventWithoutCsrfToken() throws Exception {
        mockMvc.perform(post("/checkout")
                        .param("execution", "key-is-not-validated-before-csrf")
                        .param("_eventId_continue", "continue"))
                .andExpect(status().isForbidden());
    }

    @Test
    void rejectsFlowEventWithInvalidCsrfToken() throws Exception {
        mockMvc.perform(post("/checkout")
                        .param("execution", "key-is-not-validated-before-csrf")
                        .param("_eventId_continue", "continue")
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }
}
~~~

Đây là khung minh họa; trong kiểm thử tích hợp thực tế, `execution` phải là key hợp lệ được lấy từ bước khởi chạy flow trong cùng session. Không hardcode một key giả rồi mong flow transition thành công. Có thể tách kiểm thử filter security với kiểm thử đầy đủ flow: kiểm thử filter xác nhận 403 khi token thiếu/sai, còn kiểm thử flow khởi chạy execution thật, lấy URL hoặc key trả về, rồi gửi POST có token hợp lệ và xác nhận transition được thực thi.

Để kiểm tra request bị từ chối trước khi flow chạy, dùng mock hoặc spy service/action và xác nhận nó không được gọi khi thiếu token. Với request hợp lệ, xác nhận action được gọi và response có redirect theo hành vi flow đã cấu hình.

Dependency kiểm thử cần có `spring-security-test` cùng phiên bản tương thích với Spring Security của ứng dụng. Khi test dùng MockMvc, cấu hình Spring Security filter chain phải được áp dụng vào MockMvc; nếu không, request post processor không kiểm tra được hành vi filter thật.

## 9. Nguyên tắc vận hành lâu dài

Giữ CSRF protection bật trong Spring Security và gửi token trong mọi form POST hoặc request AJAX tạo event thay đổi trạng thái. Form Web Flow cần vừa gửi execution URL đúng, vừa gửi event ID và CSRF token. Token không thay thế execution key, không phải dữ liệu nghiệp vụ và không chứng minh quyền truy cập vào hồ sơ.

Khi nhận 403, hãy kiểm tra token và session trước khi xem flow XML. Nếu request bị chặn ở security filter, action và transition chưa chạy. Với multipart, kiểm tra thứ tự phân tích request và ưu tiên header token cho upload AJAX. Cuối cùng, kiểm thử cả request hợp lệ lẫn request thiếu/sai token, đồng thời xác nhận không có side effect xảy ra khi security từ chối request.

Cách tích hợp này giúp Spring Security kiểm tra nguồn gốc request trước khi Spring Web Flow xử lý event, giữ cho các hành trình nhiều bước an toàn hơn mà vẫn duy trì được cơ chế state, transition và subflow của ứng dụng.
