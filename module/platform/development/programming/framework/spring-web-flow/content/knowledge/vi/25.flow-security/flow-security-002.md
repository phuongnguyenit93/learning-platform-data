# Cấu hình Spring Security cho URL khởi chạy và tiếp tục flow

Một flow đặt hàng có thể gồm các bước chọn địa chỉ, chọn phương thức thanh toán, xem lại và xác nhận. Người dùng truy cập `GET /checkout` để bắt đầu, sau đó gửi các yêu cầu đến URL do Spring Web Flow tạo ra để tiếp tục cùng một flow execution. Nếu ứng dụng chỉ bảo vệ trang đầu mà bỏ qua các request tiếp tục, người dùng không còn quyền truy cập vẫn có thể cố gửi event để chuyển bước hoặc thực hiện hành động nghiệp vụ.

Trong **Spring Web Flow (SWF)**, việc định nghĩa state, event và transition giải quyết bài toán điều hướng nhiều bước. **Spring Security** cần được cấu hình để kiểm soát các HTTP request đi qua Spring MVC/`DispatcherServlet`; những quyền nhạy cảm còn phải được kiểm tra trong service hoặc ở điểm thực thi nghiệp vụ. Bài học trong chương **Bảo vệ flow** này tập trung vào cách xác định và bảo vệ **URL khởi chạy flow** lẫn **URL tiếp tục flow**, kết hợp CSRF, session, kiểm tra quyền và kiểm thử.

## 1. Hai loại request cùng thuộc một flow

Giả sử ứng dụng dùng flow ID `checkout`, với servlet mapping mặc định `/` và đường dẫn bên ngoài `/checkout`.

| Giai đoạn | Request minh họa | Ý nghĩa |
|---|---|---|
| Khởi chạy | `GET /checkout` | Tìm định nghĩa flow và tạo flow execution mới |
| Tiếp tục | `POST /checkout?execution=e1s1` | Khôi phục execution từ khóa do SWF tạo, nhận event và dữ liệu form |
| Quay lại một bước | `POST /checkout?execution=e1s2` | Phát event `back` trong execution tương ứng |
| Xác nhận | `POST /checkout?execution=e1s3` | Phát event `confirm`; có thể dẫn tới action ghi đơn hàng |
| Hết hạn hoặc khóa không hợp lệ | Request với execution không còn khả dụng | Đi theo cơ chế xử lý lỗi/khôi phục đã cấu hình |

Những khóa như `e1s1` chỉ là ví dụ; định dạng và vòng đời thực tế do phiên bản/cấu hình SWF quyết định. `execution` **không phải session ID đăng nhập**, không chứng minh quyền sở hữu dữ liệu và không thay thế việc xác thực.

Trong cấu hình Web Flow thường gặp, cả request đầu tiên và những request tiếp theo **đều đi qua cùng đường dẫn flow**, chỉ khác query parameter, HTTP method và payload. State `payment` hoặc `review` là state ID bên trong flow, không mặc nhiên trở thành endpoint `/checkout/payment` hay `/checkout/review`.

Vì vậy, khi bảo vệ `/checkout`, phải tính đến **GET khởi chạy và POST tiếp tục**. Đồng thời, không nên dựa vào query parameter `execution` để quyết định một request có được xác thực hay không.

## 2. Request đi qua lớp bảo mật nào?

~~~mermaid
flowchart TD
    A["Trình duyệt: GET/POST /checkout"] --> B["Servlet container"]
    B --> C["Spring Security: FilterChainProxy"]
    C --> D{"Xác thực, phân quyền, CSRF"}
    D -->|"Không hợp lệ"| E["401/403 hoặc điều hướng đăng nhập theo cấu hình"]
    D -->|"Được phép"| F["DispatcherServlet"]
    F --> G["FlowHandlerMapping"]
    G --> H["FlowHandlerAdapter"]
    H --> I["FlowExecutor"]
    I --> J["State, event, transition"]
    J --> K{"Action nghiệp vụ cần quyền?"}
    K -->|"Có"| L["Kiểm tra chủ sở hữu/quyền tại service"]
    K -->|"Không"| M["View tiếp theo hoặc end-state"]
    L -->|"Hợp lệ"| M
    L -->|"Từ chối"| N["AccessDeniedException / xử lý lỗi"]
~~~

Trong ứng dụng Servlet sử dụng Spring Security, bộ lọc bảo mật thường chạy **trước** `DispatcherServlet`. Từ đó:

- `SecurityFilterChain` xác định yêu cầu HTTP nào cần đăng nhập, role/authority nào được phép và các chính sách như CSRF.
- `DispatcherServlet` dùng `FlowHandlerMapping` và `FlowHandlerAdapter` để chuyển request vào `FlowExecutor`.
- SWF khôi phục trạng thái, binding/validation biểu mẫu, xử lý event và transition.
- Service xác nhận các quyền liên quan **đến bản ghi cụ thể**, chẳng hạn chỉ chủ sở hữu đơn hàng được thanh toán đơn đó.

Một route được bảo vệ bằng `authenticated()` đảm bảo request có thông tin xác thực phù hợp theo chính sách filter chain, nhưng **không kết luận** người đăng nhập được phép sửa mọi đơn hàng hoặc mọi hồ sơ trong flow. Phải kiểm tra thêm tại tầng nghiệp vụ.

## 3. Xác định URL thực tế trước khi viết matcher

Đường dẫn bảo vệ phụ thuộc vào **flow ID**, cách đăng ký flow, context path của ứng dụng và servlet mapping:

| Cấu hình triển khai | URL trình duyệt ví dụ | Ghi chú |
|---|---|---|
| Web app tại root, flow ID `checkout` | `/checkout` | Trường hợp đơn giản |
| App có context path `/shop` | `/shop/checkout` | Khi viết matcher trong Spring Security thường **không** thêm context path `/shop` |
| Servlet được ánh xạ riêng, ví dụ `/ui/*` | `/ui/checkout` | Cần đối chiếu servlet path và cách Spring Security phiên bản đang dùng match path |
| Ứng dụng tự tạo mapping/`FlowHandler` | Có thể khác `/checkout` | Kiểm tra routing thực tế, đừng đoán từ tên file XML |

Trong các ví dụ sau, giả định URL mà Spring Security cần match là `/checkout` và `/registration`. Nếu ứng dụng có prefix riêng hoặc cấu hình nhiều `DispatcherServlet`, điều chỉnh matcher bằng cách kiểm tra **request thực tế** ở môi trường ứng dụng.

**Lưu ý về SecurityFilterChain:** Một ứng dụng có thể có nhiều chain với `securityMatcher(...)` khác nhau. `FilterChainProxy` chọn **chain phù hợp đầu tiên**; chain được chọn mới áp dụng các quy tắc `authorizeHttpRequests` bên trong. Nếu flow URL nằm ngoài mọi chain dự kiến hoặc bị một chain ưu tiên khác bắt trước, những quy tắc viết đúng trong chain sau vẫn có thể không được thực thi.

## 4. Ví dụ Spring Security 6: bảo vệ cả URL bắt đầu và tiếp tục

Ví dụ dưới đây sử dụng **Spring Security 6, cấu hình Java bằng `SecurityFilterChain`**, giả định ứng dụng có login bằng form, role `ROLE_CUSTOMER`, các flow `checkout` và `registration`. Đường dẫn demo có thể cần thay theo module thực tế.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class FlowSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/css/**", "/js/**", "/images/**"
                ).permitAll()
                // Chặn cả GET khởi chạy và POST tiếp tục của checkout.
                .requestMatchers("/checkout", "/checkout/**")
                    .hasRole("CUSTOMER")
                // Luồng đăng ký chỉ yêu cầu người dùng đã đăng nhập.
                .requestMatchers("/registration", "/registration/**")
                    .authenticated()
                .anyRequest().authenticated()
            )
            // Sử dụng trang login mặc định nếu chưa cấu hình riêng.
            .formLogin(Customizer.withDefaults())
            // Giữ bảo vệ CSRF cho các request thay đổi trạng thái.
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Trong `hasRole("CUSTOMER")`, Spring Security theo quy ước kiểm tra authority `ROLE_CUSTOMER`; nếu hệ thống lưu authority với cách đặt tên khác, điều chỉnh theo quy tắc cấp quyền thực tế. Cấu hình mẫu không bao gồm nơi cấp user/authority, repository account hay các bean tích hợp SWF/MVC; ứng dụng phải cung cấp chúng.

### 4.1. Vì sao matcher không phân biệt `GET` và `POST`?

Dòng:

~~~java
.requestMatchers("/checkout", "/checkout/**")
    .hasRole("CUSTOMER")
~~~

được đặt để áp dụng cho **mọi HTTP method** trên các path đó. Do đó yêu cầu `GET /checkout` và `POST /checkout?execution=...` đều chịu cùng chính sách xác thực/quyền. Query parameter `execution` không được dùng làm ngoại lệ.

Nếu chỉ viết matcher cho `HttpMethod.GET`, request POST tiếp tục có thể rơi vào quy tắc khác. Điều này đặc biệt nguy hiểm khi phía sau có `anyRequest().permitAll()`. Nếu có lý do nghiệp vụ buộc dùng chính sách khác theo method, hãy khai báo đủ tất cả method có thể thực thi flow và kiểm thử thực tế.

### 4.2. Luồng công khai có thể khởi chạy không cần đăng nhập?

Có, nếu sản phẩm cần một flow đăng ký trước khi tạo tài khoản. Khi đó có thể đổi policy URL `/registration` thành `permitAll()`, nhưng:

- `permitAll()` áp dụng cho request URL phù hợp, kể cả request tiếp tục flow trên cùng path.
- Một state nhạy cảm xuất hiện **ở giữa** flow không tự được bảo vệ bằng rule URL nếu không có endpoint riêng.
- Khi flow đi tới bước yêu cầu danh tính hoặc quyền, cần kiểm tra tại state/action/service phù hợp; trong một số thiết kế, phải yêu cầu đăng nhập rồi điều hướng tiếp hoặc chia thành các flow khác nhau theo mức độ bảo mật.

Ví dụ, **cho phép khách tạo giỏ hàng** không đồng nghĩa cho phép khách chưa đăng nhập thực hiện `confirmOrder`. Quy tắc trong service xác nhận đơn phải kiểm tra tài khoản, đơn sở hữu và trạng thái thanh toán trước khi ghi giao dịch.

### 4.3. Dùng nhiều chain thì phải bảo vệ đúng chain

Ví dụ ứng dụng có chain riêng cho `/api/**` và chain khác cho giao diện. Flow `/checkout` chỉ được bảo vệ khi chain giao diện thật sự match request. Cách sử dụng một `SecurityFilterChain` như ví dụ giúp dễ học; ở hệ thống lớn phải kiểm tra `@Order`, `securityMatcher` và thứ tự các chain.

Đừng nhầm `requestMatchers` trong `authorizeHttpRequests` với `securityMatcher` cấp chain: matcher đầu tiên xác định **quy tắc phân quyền bên trong chain**; matcher thứ hai xác định **chain nào nhận request**.

## 5. Cấu hình URL flow và Spring MVC tương ứng

Để `/checkout` thực sự được xử lý bởi Web Flow, ứng dụng phải có cấu hình tích hợp Spring MVC. Ví dụ XML rút gọn (minh họa phong cách namespace của Spring Web Flow 2):

~~~xml
<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location id="checkout"
                           path="/WEB-INF/flows/checkout/checkout-flow.xml" />
    <webflow:flow-location id="registration"
                           path="/WEB-INF/flows/registration/registration-flow.xml" />
</webflow:flow-registry>

<webflow:flow-executor id="flowExecutor" />

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Đoạn này thuộc cấu hình Spring MVC/Web Flow có namespace và `flowBuilderServices` được khai báo sẵn, không phải tệp XML độc lập. Ví dụ Java dùng Spring Security 6, còn XML minh họa cú pháp tích hợp Web Flow phổ biến ở dòng 2.x; **không mặc định hai phiên bản có thể lắp chung**. Trước khi triển khai, cần xác minh bộ phiên bản Spring Framework, Spring Web Flow, Spring Security và Servlet API (`javax.servlet` hoặc `jakarta.servlet`) tương thích. Cấu hình Spring Security còn phải được đăng ký qua cơ chế filter của ứng dụng Servlet (điển hình là `springSecurityFilterChain`), chứ không chỉ tạo một bean `SecurityFilterChain` trong context rồi mong servlet container tự gọi nó trong mọi kiểu triển khai.

**Tách trách nhiệm:** `FlowHandlerMapping` quyết định path nào khởi chạy hoặc tiếp tục flow; Spring Security quyết định request tới path đó có được đi tiếp vào `DispatcherServlet` hay không. Nếu URL thật khác `/checkout`, sửa matcher bảo mật để phù hợp trước khi đưa vào vận hành.

## 6. CSRF cho form phát event của Web Flow

Trong trình duyệt, những event như `next`, `save`, `cancel`, `confirm` được gửi bằng form. Chúng có thể thay đổi dữ liệu flow và thậm chí thực hiện tác động nghiệp vụ. CSRF protection nên được bật cho các yêu cầu thay đổi trạng thái và phải **truyền token hợp lệ** theo cơ chế Spring Security đang dùng.

Ví dụ form JSP dùng EL và hidden CSRF token:

~~~jsp
<form method="post" action="${flowExecutionUrl}">
    <input type="hidden"
           name="${_csrf.parameterName}"
           value="${_csrf.token}" />

    <label for="shippingAddress">Địa chỉ giao hàng</label>
    <input type="text" id="shippingAddress"
           name="shippingAddress" />

    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel">Hủy</button>
</form>
~~~

Các expression `${flowExecutionUrl}`, `${_csrf.parameterName}` và `${_csrf.token}` trong đoạn JSP sau khi render tương ứng với URL execution do SWF cung cấp và đối tượng CSRF của Spring Security. Ví dụ giả định CSRF token có sẵn trong request như `_csrf.parameterName` và `_csrf.token`. Với một số tag Spring Form và cấu hình `RequestDataValueProcessor`, token có thể được thêm tự động; cần **kiểm tra HTML thực tế được render** để tránh thiếu token hoặc triển khai hai cơ chế không cần thiết.

Một request form tiếp tục có thể chứa:

~~~http
POST /checkout?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId_confirm=&_csrf=<token-hop-le>
~~~

`_csrf` là ví dụ tên parameter mặc định; tên và cách truyền token tùy cấu hình. Cookie session, token và execution key là **ba khái niệm khác nhau**, mỗi loại có một mục đích.

### 6.1. Không coi `_eventId` là token bảo mật

Tên nút `_eventId_confirm` chỉ biểu thị event người dùng muốn gửi. Kẻ tấn công hoặc client tự viết có thể gửi tên/value này mà không cần dùng giao diện web. Vì thế:

- CSRF chống việc một trang khác lợi dụng phiên trình duyệt để gửi request không mong muốn.
- Authentication xác định ai đang gửi request.
- Authorization xác định họ được phép thao tác gì.
- Validation xác minh form hợp lệ.
- Kiểm tra nghiệp vụ đảm bảo hành động như thanh toán, duyệt đơn hay cập nhật hồ sơ chỉ được thực hiện khi còn đủ điều kiện.

Không yếu tố nào trong số đó có thể thay thế hoàn toàn các yếu tố còn lại.

### 6.2. Không dùng GET để thực hiện thao tác thay đổi dữ liệu

`GET /checkout` nên dùng để khởi chạy/hiển thị theo nghĩa an toàn của HTTP; **đặt hàng**, **xác nhận thanh toán** hoặc **hủy giao dịch** cần đi qua phương thức có bảo vệ thích hợp (thường là POST). Spring Security mặc định thường không yêu cầu CSRF token cho GET/HEAD/OPTIONS/TRACE, nên nếu thiết kế URL GET để thực hiện thao tác ghi, bảo vệ CSRF dựa trên phương thức sẽ không giúp được.

Khi dùng link thay vì form để phát event có tác dụng phụ, hãy đổi sang POST hoặc thiết kế lại bước điều hướng.

## 7. Xác thực và phân quyền sau khi flow đã bắt đầu

Một flow execution có thể tồn tại qua nhiều request, trong khi danh tính hoặc quyền truy cập có thể thay đổi: người dùng logout, session hết hạn, role bị thu hồi hoặc đơn hàng được người khác cập nhật. **Việc khởi chạy flow thành công không cấp phép vĩnh viễn cho mọi transition sau này**.

### 7.1. Bảo vệ ở tầng HTTP và tầng nghiệp vụ

Ví dụ `/checkout` yêu cầu `ROLE_CUSTOMER`, nhưng người dùng A và B đều có role này. Nếu user A đoán được ID đơn hàng của B từ một request hoặc thông qua model do client gửi, rule `hasRole("CUSTOMER")` vẫn không chứng minh A là chủ đơn hàng.

Có thể dùng method security ở service (Spring Security 6) để kiểm tra thêm quyền đối với đối tượng cụ thể:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class OrderService {

    private final OrderRepository orderRepository;

    OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    @PreAuthorize("hasRole('CUSTOMER') and " +
                  "@orderAccess.canConfirm(authentication, #orderId)")
    public Receipt confirmOrder(Long orderId) {
        // Đọc order từ DB, kiểm tra lại trạng thái và giá tiền,
        // thực hiện ghi giao dịch một cách nhất quán.
        return orderRepository.confirm(orderId);
    }
}
~~~

Đây là mã rút gọn cần các kiểu nghiệp vụ `OrderRepository`, `Receipt` và bean `orderAccess` do ứng dụng định nghĩa. `orderAccess.canConfirm(authentication, #orderId)` phải kiểm tra chủ sở hữu hoặc quyền được ủy quyền từ **nguồn tin cậy phía server**, đồng thời cần hỗ trợ xác định tên tham số `orderId` trong biểu thức (ví dụ bật metadata tham số hoặc dùng `@P("orderId")`). Phần `confirm` minh họa giả định repository/service đã được triển khai an toàn.

Method security cần được **kích hoạt** bằng `@EnableMethodSecurity` và lời gọi phải đi qua cơ chế proxy phù hợp; gọi nội bộ trực tiếp giữa các phương thức cùng bean có thể không kích hoạt interceptor như mong đợi. Khi thao tác ghi đòi hỏi quyền đặc biệt hoặc tính nguyên tử, nên kiểm tra điều kiện tại thời điểm ghi trong transaction, không chỉ kiểm tra lúc form được render.

### 7.2. Bảo vệ flow/state không đồng nghĩa URL authorization

Một số phiên bản/tích hợp SWF có hỗ trợ bảo vệ flow hoặc state bằng thành phần security chuyên biệt, ví dụ `SecurityFlowExecutionListener` và phần tử `<secured>` trong định nghĩa flow khi cấu hình phù hợp.

Ví dụ về ý tưởng bảo vệ ở cấp flow:

~~~xml
<!-- Minh họa với tích hợp SWF/Spring Security hỗ trợ <secured>. -->
<secured attributes="ROLE_CUSTOMER" />
~~~

Đoạn trên **không thể dùng độc lập**: cần đặt đúng trong định nghĩa flow/state và cấu hình security listener theo phiên bản tương thích. Nếu dự án không sử dụng tích hợp security flow/state, hãy đặt các kiểm tra ở action/service và sử dụng Spring Security HTTP filter cho URL tương ứng.

Hai lớp này giải quyết các vấn đề khác nhau: matcher URL bảo vệ **đường truy cập qua HTTP**, còn kiểm tra flow/state/service bảo vệ **trạng thái và hành động cụ thể**. Phân quyền trên các bản ghi nghiệp vụ vẫn phải xác minh trước khi thực hiện ghi dữ liệu.

### 7.3. Hết hạn phiên và đổi danh tính

Khi phiên HTTP hết hạn, flow execution lưu theo session có thể không còn phục hồi được. Người dùng có thể được đưa tới login nhưng sau login khóa execution cũ đã không còn hợp lệ. Ứng dụng cần có đường phục hồi có chủ đích:

1. Thông báo rằng phiên thao tác đã hết hạn hoặc không thể tiếp tục.
2. Cho phép khởi động flow mới và nhập lại dữ liệu cần thiết, hoặc khôi phục bản nháp từ nguồn tin cậy nếu sản phẩm hỗ trợ.
3. Không tự phát lại request `confirm` sau login nếu tác động nghiệp vụ có thể đã được thực hiện.
4. Khi logout/chuyển tài khoản, kiểm tra để execution cũ không được dùng để truy cập dữ liệu của chủ tài khoản trước.

Các cơ chế session fixation protection, cookie `HttpOnly`/`Secure`, session timeout và chính sách đăng nhập nên được cấu hình và kiểm thử thống nhất với phần còn lại của ứng dụng. Hạn chế lưu dữ liệu nhạy cảm hoặc đối tượng không thể serialize trong `flowScope`/`conversationScope` nếu repository có thể lưu snapshot lâu dài.

## 8. Những cấu hình dễ gây lỗ hổng

| Cấu hình hoặc thiết kế | Vấn đề có thể xảy ra | Cách xử lý |
|---|---|---|
| Chỉ bảo vệ `GET /checkout` | Request POST tiếp tục có thể trúng rule lỏng hơn | Match mọi method trên toàn bộ flow path |
| Bảo vệ `/checkout/start` nhưng URL thực là `/checkout` | Không match request vào flow | Xác minh URL thật do `FlowHandlerMapping` nhận |
| Dùng `/checkout/**` mà quên `/checkout` | Matcher có thể không match path gốc tùy loại matcher | Khai báo cả path gốc và path con cần bảo vệ |
| `anyRequest().permitAll()` đặt trước rule flow | Rule phía sau có thể không đạt tới | Sắp xếp rule cụ thể trước rule tổng quát |
| Flow URL bị một `SecurityFilterChain` khác nhận trước | Rule trong chain dự kiến không chạy | Kiểm tra `securityMatcher`, `@Order` và danh sách chain |
| Tắt CSRF toàn ứng dụng để POST flow hoạt động | Bỏ lớp bảo vệ cho form/giao dịch | Truyền token đúng; chỉ ngoại lệ khi có lý do đã đánh giá |
| Coi `execution` là chứng minh người dùng đã login | Execution key không đại diện authentication/authorization | Yêu cầu SecurityContext và kiểm tra quyền nghiệp vụ |
| Chỉ kiểm tra role khi khởi chạy | Quyền có thể thay đổi trước bước xác nhận | Kiểm tra lại tại request/action/service quan trọng |
| Tin vào ID/`ownerId` từ form | Rủi ro truy cập đối tượng của người khác (IDOR) | Truy vấn/đối chiếu quyền từ DB với user hiện hành |
| Dùng GET event để xác nhận ghi dữ liệu | GET không được CSRF bảo vệ mặc định | Dùng POST có CSRF và kiểm tra nghiệp vụ |
| Chỉ kiểm tra quyền trên view | Event có thể được gửi thủ công tới flow | Enforce ở tầng action/service |
| Flow timeout rồi tự động gửi lại POST | Nguy cơ xử lý trùng | Hiển thị phục hồi, idempotency hoặc kiểm tra trùng |

## 9. Kiểm thử Spring Security với cả request khởi chạy và tiếp tục

Cần kiểm thử **đường HTTP** và **điểm thực thi nghiệp vụ**. Test `GET /checkout` trả HTTP 200 chỉ chứng minh phần khởi chạy đã vượt qua bảo vệ; chưa chứng minh POST tiếp tục và action `confirm` được bảo vệ.

### 9.1. Ma trận truy cập

Giả định policy như cấu hình ở phần 4: `/checkout` chỉ cho `ROLE_CUSTOMER`, `/registration` cho user đã đăng nhập.

| Tình huống | Request | Kết quả cần xác minh |
|---|---|---|
| Chưa đăng nhập | `GET /checkout` | Bị yêu cầu xác thực (redirect hoặc 401 theo entry point) |
| Chưa đăng nhập | `POST /checkout?execution=...` | Không được xử lý event, không được lưu đơn |
| Đã đăng nhập nhưng thiếu role | `GET /checkout` | Bị từ chối truy cập, thường 403 |
| Đã đăng nhập nhưng thiếu role | POST tiếp tục flow | Bị từ chối trước khi action nghiệp vụ chạy |
| Có `ROLE_CUSTOMER` | `GET /checkout` | Được phép khởi chạy flow |
| Có `ROLE_CUSTOMER` và CSRF hợp lệ | POST tiếp tục bằng execution key thật | Flow nhận event và chuyển state phù hợp |
| Có `ROLE_CUSTOMER` nhưng CSRF thiếu/sai | POST event `next`/`confirm` | Bị chặn bởi CSRF |
| Có role nhưng cố thao tác đơn của người khác | POST `confirm` | Service từ chối dựa trên quyền đối tượng |
| Đang flow thì logout/timeout | POST bằng execution cũ | Không được thực hiện tác động nghiệp vụ |
| Session hợp lệ nhưng execution key không còn khả dụng | POST với khóa cũ | Có xử lý lỗi/khôi phục an toàn, không tự ghi đơn |

Kỳ vọng cụ thể của status/redirect phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler`, login configuration, ứng dụng dùng HTML hay API và chiến lược exception handling.

### 9.2. Ví dụ kiểm tra rule bằng Spring Security Test

Với Spring MVC, có thể sử dụng `MockMvc` và `spring-security-test`. Ví dụ dưới đây chỉ minh họa các **kiểm tra filter chain**; để kiểm tra điều hướng flow đầy đủ, phải dựng application context có SWF thực và duy trì session/cookie giữa các request.

~~~java
import org.junit.jupiter.api.Test;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void checkoutRequiresLogin() throws Exception {
    mockMvc.perform(get("/checkout"))
           .andExpect(status().is3xxRedirection());
}

@Test
void checkoutRejectsMissingRole() throws Exception {
    mockMvc.perform(get("/checkout")
           .with(user("viewer").roles("VIEWER")))
           .andExpect(status().isForbidden());
}

@Test
void checkoutPostRejectsMissingCsrfToken() throws Exception {
    mockMvc.perform(post("/checkout")
           .with(user("customer").roles("CUSTOMER"))
           .param("_eventId", "next"))
           .andExpect(status().isForbidden());
}

@Test
void registrationRejectsAnonymousWhenLoginIsRequired() throws Exception {
    mockMvc.perform(get("/registration"))
           .andExpect(status().is3xxRedirection());
}
~~~

Các test giả định security filter chain đã được áp dụng cho `MockMvc`, ứng dụng dùng form login với redirect khi chưa xác thực, và filter được chạy trước logic flow. Test POST không có CSRF có thể bị từ chối ngay cả khi execution key chưa được cung cấp; đó là kiểm tra **lớp CSRF**, không phải kiểm tra SWF chuyển state.

Muốn kiểm thử flow tiếp tục thực sự, test cần khởi chạy `GET /checkout`, lấy **URL execution thật** từ kết quả render, giữ session, gửi POST kèm `with(csrf())` và quyền hợp lệ, rồi xác nhận state/render kết quả. Không tự dựng `execution=e1s1` làm dữ liệu cố định vì khóa thực tế do engine quản lý.

### 9.3. Kiểm tra một sự kiện cố tình giả mạo

Ngoài happy path, cố tình gửi `_eventId_confirm` khi người dùng đang ở state chưa được phép xác nhận. Request có thể được tạo thủ công nên không thể dựa vào việc nút “Xác nhận” chưa xuất hiện trên giao diện.

Cần xác nhận rằng:

1. SWF không thực hiện transition không có trong state hiện tại.
2. Nếu event đi tới action hợp lệ, service vẫn kiểm tra quyền và tính nhất quán của đối tượng.
3. Quyền bị thu hồi giữa hai request khiến hành động không được thực hiện.
4. Đơn đã hoàn tất không bị xử lý lần hai dù trình duyệt gửi lại POST.

## 10. Bài tập thực hành

Hãy xây dựng flow `checkout` gồm `enterAddress` → `reviewOrder` → `confirmOrder` → `completed`, dùng Spring MVC để nhận request và Spring Web Flow để điều hướng.

Yêu cầu:

1. Đăng ký flow ID `checkout` và xác định chính xác URL khởi chạy cùng URL tiếp tục.
2. Cấu hình `SecurityFilterChain` để chỉ role `ROLE_CUSTOMER` truy cập flow; bảo vệ cả GET lẫn POST.
3. Tạo JSP/Thymeleaf form dùng URL execution do SWF cung cấp, có CSRF token hợp lệ và nút phát event `next` hoặc `confirm`.
4. Trong action xác nhận, gọi service kiểm tra người dùng hiện hành có quyền với đơn hàng, trạng thái đơn còn hợp lệ và không xử lý trùng.
5. Thiết kế cách phục hồi khi session hết hạn hoặc execution key không còn tồn tại, tránh tự gửi lại tác động ghi dữ liệu.
6. Viết test cho anonymous, sai role, thiếu CSRF, user có quyền, user cố xác nhận đơn của người khác và thử gửi lại `confirm`.

Khi hoàn thành, mỗi request của flow phải đi qua chính sách xác thực/phân quyền rõ ràng, còn thao tác nhạy cảm được xác minh tại tầng nghiệp vụ. **Bảo vệ URL khởi chạy và URL tiếp tục là lớp kiểm soát HTTP; bảo vệ state và hành động là bước quyết định flow có an toàn trước các request hợp lệ nhưng không được phép hay không.**
