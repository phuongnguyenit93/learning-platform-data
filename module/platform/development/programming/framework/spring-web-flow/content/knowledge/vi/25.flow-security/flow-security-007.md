
# Để lỗi AccessDenied được xử lý đúng tại ranh giới bảo mật

Trong một flow nhiều bước, người dùng có thể được phép mở quy trình nhưng không được phép vào một state hoặc thực hiện một transition cụ thể. Spring Web Flow phối hợp với Spring Security để kiểm tra những ranh giới này. Khi kiểm tra thất bại, Spring Web Flow ném **AccessDeniedException** để Spring Security xử lý ở tầng HTTP.

Điểm quan trọng của bài học là: **AccessDeniedException phải được truyền ngược ra khỏi flow execution để Spring Security nhận diện và tạo phản hồi bảo mật**. Nếu action, exception handler hoặc lớp xử lý lỗi chung bắt exception rồi đổi nó thành một event bình thường, người dùng có thể bị đưa tới sai màn hình, không nhận được phản hồi 401/403 phù hợp, hoặc tiếp tục flow trong khi quyền đã bị từ chối.

Bài thuộc chương **Bảo vệ flow** của module **SPRING_WEB_FLOW**. Module học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow, đồng thời thực hành form binding, validation, quản lý scope/phiên, tích hợp Spring MVC và phục hồi lỗi. Ta sẽ tập trung vào ranh giới giữa **ủy quyền bên trong flow** và **xử lý ngoại lệ của Spring Security**, phân biệt người chưa xác thực với người đã xác thực nhưng thiếu quyền, rồi kiểm thử để chắc chắn thao tác bị từ chối không tạo side effect.

## 1. Tình huống: người dùng bị từ chối ở giữa flow

Giả sử quy trình duyệt đặt lịch có các bước:

~~~text
booking
  details
    ↓ next
  review
    ↓ approve
  approved
~~~

Chính sách:

- Người có ROLE_USER được bắt đầu flow.
- Người có ROLE_MANAGER được vào state review.
- Người có ROLE_APPROVER được thực hiện transition approve.
- Service chỉ duyệt booking mà người đó có quyền xử lý và booking còn ở trạng thái PENDING.

Một người dùng có ROLE_USER và ROLE_MANAGER nhưng không có ROLE_APPROVER có thể xem màn hình review. Khi họ gửi event approve, Spring Web Flow phải từ chối transition. Người dùng đã đăng nhập, vì vậy phản hồi thường là **403 Forbidden** theo cấu hình Spring Security.

Một người chưa đăng nhập mà bị từ chối ở flow được bảo vệ thường cần được chuyển tới **AuthenticationEntryPoint**, chẳng hạn trang login hoặc phản hồi 401 của API. Hai trường hợp này đều có thể bắt đầu từ AccessDeniedException, nhưng Spring Security phân biệt danh tính hiện tại để chọn cách phản hồi.

~~~mermaid
flowchart TD
    A["Request tiếp tục booking flow"] --> B["SecurityFlowExecutionListener"]
    B --> C{"Có authority cần thiết?"}
    C -->|"Có"| D["Flow tiếp tục state / transition"]
    C -->|"Không"| E["AccessDeniedException"]
    E --> F["ExceptionTranslationFilter"]
    F --> G{"Người dùng anonymous?"}
    G -->|"Có"| H["AuthenticationEntryPoint"]
    G -->|"Không"| I["AccessDeniedHandler"]
    H --> J["Login / 401"]
    I --> K["403 / trang từ chối"]
~~~

Nếu exception bị bắt trong flow và chuyển thành event error, bước F có thể không nhận được exception. Khi đó Spring Security không còn cơ hội áp dụng chính sách authentication/access-denied đã cấu hình.

## 2. AuthenticationException và AccessDeniedException khác nhau thế nào?

Hai loại exception biểu diễn hai tình huống khác nhau:

| Loại | Ý nghĩa | Xử lý HTTP thường gặp |
|---|---|---|
| AuthenticationException | Không thể xác thực hoặc thông tin xác thực không hợp lệ | AuthenticationEntryPoint bắt đầu quy trình xác thực |
| AccessDeniedException | Quyền truy cập bị từ chối | Anonymous: AuthenticationEntryPoint; đã xác thực: AccessDeniedHandler |

Ví dụ:

- Người dùng chưa đăng nhập truy cập flow yêu cầu authentication.
- Người dùng đã đăng nhập bằng tài khoản USER nhưng cố vào state yêu cầu MANAGER.
- Người dùng có quyền xem review nhưng cố gửi event approve mà thiếu APPROVER.
- Người dùng có role APPROVER nhưng service từ chối booking thuộc tenant khác.

Trong ba trường hợp cuối, người dùng đã xác thực nhưng không có quyền tương ứng. Không nên hiển thị thông báo “phiên đăng nhập hết hạn” nếu thực tế họ chỉ thiếu authority.

### 2.1. AccessDeniedException không tự tạo ra response HTTP

AccessDeniedException là exception phía server. Nó chưa phải một response HTTP. Spring Security dùng **ExceptionTranslationFilter** để chuyển exception bảo mật thành phản hồi phù hợp:

- Nếu Authentication hiện tại là anonymous, filter gọi AuthenticationEntryPoint.
- Nếu người dùng đã xác thực, filter gọi AccessDeniedHandler.
- Cấu hình ứng dụng quyết định redirect login, status code, trang HTML hoặc response JSON.

Với ứng dụng web dùng form login, anonymous thường được redirect tới trang đăng nhập. Với API, AuthenticationEntryPoint có thể trả 401. Với người dùng đã đăng nhập nhưng thiếu quyền, AccessDeniedHandler thường trả 403 hoặc forward tới trang từ chối.

**ExceptionTranslationFilter không thực hiện quyết định phân quyền.** Nó là cầu nối chuyển exception bảo mật thành phản hồi HTTP. Quyết định từ chối được tạo bởi authorization component, chẳng hạn SecurityFlowExecutionListener, request authorization hoặc method security.

## 3. Ranh giới bảo mật trong một request Spring Web Flow

Trong ứng dụng Servlet/Spring MVC, request đi qua Spring Security filter chain trước khi tới DispatcherServlet. FlowHandlerAdapter và FlowExecutor xử lý flow bên trong DispatcherServlet. SecurityFlowExecutionListener có thể phát hiện người dùng không có quyền trong quá trình flow chạy.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as Spring Security Filter Chain
    participant M as DispatcherServlet
    participant A as FlowHandlerAdapter
    participant E as FlowExecutor
    participant L as SecurityFlowExecutionListener

    B->>F: POST flow execution URL + event
    F->>F: ExceptionTranslationFilter bọc downstream chain
    F->>M: Tiếp tục request
    M->>A: Chọn FlowHandlerAdapter
    A->>E: Resume flow execution
    E->>L: Kiểm tra state / transition
    L--xE: AccessDeniedException
    E--xA: Exception truyền ra
    A--xM: Không đổi thành event nghiệp vụ
    M--xF: Exception thoát khỏi downstream chain
    F->>F: ExceptionTranslationFilter phân loại Authentication
    F-->>B: Login/401 hoặc 403
~~~

Đây là luồng khái niệm. Cấu hình servlet, filter chain, adapter và exception resolver thực tế của ứng dụng quyết định chi tiết tích hợp. Điều cần giữ là **exception phải đi tới cơ chế xử lý bảo mật đang bao quanh request**.

### 3.1. Vì sao “để exception đi lên” quan trọng?

Spring Web Flow Reference Guide mô tả rõ rằng khi truy cập một phần flow bị từ chối, AccessDeniedException được ném ra và sau đó Spring Security xử lý. Tài liệu nhấn mạnh exception phải được phép đi lên execution stack mà không bị chặn; nếu không, người dùng có thể không được yêu cầu đăng nhập hoặc không nhận được phản hồi bảo mật đúng.

Một flow không nên tự quyết định rằng mọi lỗi quyền đều là một nhánh nghiệp vụ thông thường. Flow có thể cung cấp state và transition, nhưng quyết định cuối cùng về login/access denied thuộc về ranh giới bảo mật.

## 4. SecurityFlowExecutionListener phát hiện quyền ở đâu?

Flow definition có thể khai báo secured rule ở ba vị trí:

- Flow: kiểm tra quyền trước khi bắt đầu flow session.
- State: kiểm tra quyền trước khi vào state.
- Transition: kiểm tra quyền trước khi transition được thực hiện.

Các kiểm tra này được thực thi bởi **SecurityFlowExecutionListener** gắn với FlowExecutor.

Ví dụ flow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <secured attributes="ROLE_USER"/>

    <view-state id="details" view="booking/details">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <secured attributes="ROLE_MANAGER"/>

        <transition on="approve" to="approved">
            <secured attributes="ROLE_APPROVER"/>
            <evaluate expression="bookingService.approve(booking.id)"/>
        </transition>
    </view-state>

    <end-state id="approved"/>
</flow>
~~~

Trong ví dụ:

- Người dùng phải có ROLE_USER để bắt đầu flow.
- Người dùng phải có ROLE_MANAGER để vào review.
- Người dùng phải có ROLE_APPROVER để thực hiện approve.

Nếu thiếu quyền ở bất kỳ điểm nào, listener ném AccessDeniedException. Nó không tự chuyển người dùng tới một state business-error.

Trong transition approve, action gọi service được đặt sau secured rule. Listener kiểm tra quyền transition trước khi action được thực hiện; nếu thiếu ROLE_APPROVER, service approve không được gọi.

### 4.1. Đăng ký listener với FlowExecutor

Nếu flow có secured elements nhưng listener không được gắn vào executor, các rule đó không được xử lý như mong muốn.

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="securityFlowExecutionListener"/>
    </webflow:flow-execution-listeners>
</webflow:flow-executor>

<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener"/>
~~~

Phải bảo đảm FlowHandlerAdapter đang dùng đúng FlowExecutor có listener này. Nếu ứng dụng có nhiều executor hoặc nhiều DispatcherServlet, việc khai báo listener ở một executor không bảo vệ những flow đang chạy qua executor khác.

Về khác biệt phiên bản: các cấu hình Spring Web Flow 2.x thường dùng AccessDecisionManager; từ SWF 3.0.1, API AccessDecisionManager trên listener được đánh dấu deprecated để chuyển sang AuthorizationManager thông qua authorizationManagerInitializer. Hãy dùng API khớp phiên bản dependency thực tế. Khác biệt này thay đổi cách tạo quyết định quyền, không thay đổi yêu cầu để AccessDeniedException tiếp tục đi lên tới Spring Security.

### 4.2. Các callback của listener

API SecurityFlowExecutionListener cho biết listener thực hiện kiểm tra tại những thời điểm chính:

| Callback | Thời điểm | Ý nghĩa |
|---|---|---|
| sessionCreating | Trước khi tạo flow session mới | Kiểm tra quyền ở cấp flow |
| stateEntering | Sau khi transition được match, trước khi vào state | Kiểm tra quyền của state đích |
| transitionExecuting | Khi transition được match, trước khi thực hiện | Kiểm tra quyền của transition |

Nếu stateEntering hoặc transitionExecuting từ chối quyền, transition tương ứng không được thực hiện. Không nên bắt exception rồi tiếp tục chạy action hoặc ghi dữ liệu như thể quyền đã được cấp.

## 5. Spring Security là nơi chuyển AccessDenied thành HTTP response

Một cấu hình Spring Security hiện đại có thể khai báo URL flow được bảo vệ và trang từ chối:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/login",
                    "/access-denied",
                    "/assets/**"
                ).permitAll()
                .requestMatchers("/booking/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            )
            .exceptionHandling(exceptions -> exceptions
                .accessDeniedPage("/access-denied")
            );

        return http.build();
    }
}
~~~

Ví dụ dùng SecurityFilterChain và authorizeHttpRequests của Spring Security hiện đại. Cần có controller/view login và access-denied tương ứng. Nếu flow URL của ứng dụng không nằm dưới /booking/**, hãy điều chỉnh matcher theo URL mà filter chain thực sự nhận.

Trang /access-denied phải được phép truy cập công khai; nếu không, việc chuyển tới trang này có thể tạo vòng lặp từ chối. Không redirect trở lại chính flow/state đang bị bảo vệ.

### 5.1. AccessDeniedHandler và AuthenticationEntryPoint

Hai thành phần có trách nhiệm khác nhau:

- **AuthenticationEntryPoint** bắt đầu quá trình xác thực, chẳng hạn redirect tới login hoặc gửi WWW-Authenticate.
- **AccessDeniedHandler** xử lý trường hợp người dùng đã xác thực nhưng không đủ quyền.

Ví dụ custom AccessDeniedHandler trả 403 cho API:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .exceptionHandling(exceptions -> exceptions
            .accessDeniedHandler((request, response, denied) -> {
                response.sendError(
                    HttpServletResponse.SC_FORBIDDEN
                );
            })
        );

    return http.build();
}
~~~

Đây là ví dụ rút gọn; ứng dụng cần cấu hình authentication mechanism và CSRF phù hợp với loại client. Nếu API dùng bearer token, authentication entry point thường trả 401 theo hợp đồng API. Nếu người dùng đã xác thực nhưng bị từ chối, AccessDeniedHandler trả 403.

### 5.2. Không mặc định mọi AccessDenied đều là yêu cầu login

Tài liệu Spring Web Flow nói exception được Spring Security xử lý để người dùng có thể được yêu cầu xác thực. Trong Spring Security Servlet hiện đại, filter còn phân biệt anonymous với authenticated:

- Anonymous bị từ chối: gọi AuthenticationEntryPoint.
- Đã xác thực nhưng thiếu quyền: gọi AccessDeniedHandler.

Vì vậy, đừng redirect mọi người dùng bị từ chối tới login. Một tài khoản đã đăng nhập nhưng không có quyền APPROVER cần nhận phản hồi 403 hoặc trang access-denied phù hợp.

## 6. Những cách vô tình nuốt AccessDeniedException trong action

Một lỗi thường gặp là action bắt mọi exception để flow luôn có thể đi tới state lỗi:

~~~java
public String approve(BookingDraft draft) {
    try {
        bookingService.approve(draft.getId());
        return "success";
    } catch (Exception ex) {
        return "error";
    }
}
~~~

Đoạn code này bắt cả AccessDeniedException, vì exception này là runtime exception. Flow nhận event error và tiếp tục theo transition bình thường. Spring Security không còn nhận được exception gốc để áp dụng AuthenticationEntryPoint hoặc AccessDeniedHandler.

Cách tốt hơn là chỉ bắt những lỗi nghiệp vụ mà flow có thể xử lý:

~~~java
public String approve(BookingDraft draft) {
    try {
        bookingService.approve(draft.getId());
        return "success";
    } catch (BookingConflictException ex) {
        return "conflict";
    }
}
~~~

Nếu booking conflict là một kết quả nghiệp vụ dự kiến, flow có thể khai báo transition conflict tới state review-again. AccessDeniedException không bị bắt nên tiếp tục lan ra ngoài.

### 6.1. Nếu cần catch RuntimeException thì phải rethrow security exception

Tốt nhất là không dùng catch-all quanh lời gọi service. Nếu một adapter bắt buộc phải bắt rộng để ghi log hoặc bổ sung ngữ cảnh, phải bảo toàn exception bảo mật:

~~~java
try {
    bookingService.approve(draft.getId());
    return "success";
} catch (AccessDeniedException ex) {
    throw ex;
} catch (BookingConflictException ex) {
    return "conflict";
}
~~~

Không chuyển AccessDeniedException thành:

- Một event như denied hoặc error.
- Một message validation trong MessageContext.
- Một biến trong flashScope rồi render lại form.
- Một giá trị false hoặc null mà flow hiểu là action đã chạy xong.
- Một response 200 có nội dung “không có quyền” nếu chính sách ứng dụng yêu cầu Spring Security xử lý ở filter boundary.

## 7. Không map AccessDeniedException sang state phục hồi

Spring Web Flow có **FlowExecutionExceptionHandler** để xử lý một số exception runtime bên trong active flow execution. Đây là cơ chế điều khiển flow: handler có thể chuyển execution tới state khác.

AccessDeniedException có ý nghĩa bảo mật. Không dùng exception handler để biến nó thành một transition nghiệp vụ.

Ví dụ mapping phù hợp cho lỗi nghiệp vụ đã xác định:

~~~java
@Bean
FlowExecutionExceptionHandler bookingExceptionHandler() {
    return new TransitionExecutingFlowExecutionExceptionHandler()
        .add(BookingConflictException.class, "reviewAgain");
}
~~~

Không thêm mapping rộng như:

~~~java
// Không dùng mapping rộng để bắt mọi lỗi:
handler.add(RuntimeException.class, "technicalError");
handler.add(Exception.class, "technicalError");
~~~

AccessDeniedException là một runtime exception. Mapping tới RuntimeException có thể bắt luôn lỗi quyền và chuyển nó sang technicalError. Khi đó Spring Security không nhận được exception để xử lý.

### 7.1. TransitionExecutingFlowExecutionExceptionHandler có thể xét cause chain

Built-in TransitionExecutingFlowExecutionExceptionHandler ánh xạ exception class tới state đích và có thể tìm nguyên nhân trong cause chain. Vì vậy, mapping một lớp cha rộng có thể bắt exception bảo mật nằm bên trong exception được bọc.

Chỉ map các exception nghiệp vụ cụ thể có state phục hồi an toàn. Không map AccessDeniedException, RuntimeException, Exception hoặc Throwable vào state lỗi chung.

### 7.2. Custom FlowExecutionExceptionHandler cần loại trừ lỗi bảo mật

Nếu custom handler nhận FlowExecutionException và tự xét cause chain, cần bảo đảm nó không nhận exception có nguyên nhân là AccessDeniedException.

Ví dụ đoạn logic trong phương thức canHandle:

~~~java
private boolean hasCause(
        Throwable exception,
        Class<? extends Throwable> expectedType) {

    Throwable current = exception;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return false;
}

@Override
public boolean canHandle(FlowExecutionException exception) {
    if (hasCause(exception, AccessDeniedException.class)) {
        return false;
    }

    return hasCause(exception, BookingConflictException.class);
}
~~~

Đây là phần minh họa cho điều kiện chọn exception; implementation đầy đủ vẫn phải cung cấp handle theo hợp đồng FlowExecutionExceptionHandler và thực hiện transition hợp lệ cho exception mà nó nhận. Cần kiểm tra các handler khác trong cùng state để không có một handler catch-all phía sau nhận lại exception bảo mật.

## 8. Không chuyển AccessDenied thành lỗi validation hoặc business result

Lỗi validation và lỗi authorization có ý nghĩa khác nhau:

| Tình huống | Ví dụ | Cách xử lý |
|---|---|---|
| Validation | Email sai định dạng | Giữ view-state, gắn lỗi vào field |
| Business rule | Booking đã bị hủy nên không thể duyệt | Event nghiệp vụ hoặc state giải thích |
| Authorization | Người dùng thiếu ROLE_APPROVER | AccessDeniedException đi tới Spring Security |
| Authentication | Chưa đăng nhập | AuthenticationEntryPoint |
| Hạ tầng | Database timeout | Error/recovery policy riêng |

Ví dụ “booking đã hết hạn nên không thể xác nhận” có thể là một business outcome. Nhưng “người dùng không được phép xác nhận booking của tenant khác” là authorization denial. Không gộp hai tình huống chỉ vì giao diện đều có thể hiển thị một thông báo.

Nếu service dùng method security:

~~~java
@Service
public class BookingService {

    @PreAuthorize("hasAuthority('ROLE_APPROVER')")
    public void approve(UUID bookingId) {
        Booking booking = repository.findById(bookingId)
            .orElseThrow(BookingNotFoundException::new);

        authorization.checkCanApprove(
            SecurityContextHolder.getContext().getAuthentication(),
            booking
        );

        booking.approve();
    }
}
~~~

Khi thiếu authority, method security có thể ném AccessDeniedException trước khi thân phương thức chạy. Nếu action bắt RuntimeException rồi trả event error, nó sẽ vô tình nuốt quyết định từ method security.

Ví dụ dùng @PreAuthorize cần bật method security bằng @EnableMethodSecurity trong cấu hình ứng dụng. Quyền ở cấp phương thức bổ sung cho flow security, đặc biệt khi cùng service được gọi từ nhiều entry point khác nhau.

Service cũng cần kiểm tra quyền trên tài nguyên cụ thể, như owner, tenant và trạng thái bản ghi. Nhưng khi chính sách từ chối, exception vẫn phải được truyền ra ngoài theo ranh giới bảo mật.

## 9. Cẩn thận với @ControllerAdvice và HandlerExceptionResolver

Spring MVC có cơ chế xử lý exception riêng, chẳng hạn @ExceptionHandler, @ControllerAdvice và HandlerExceptionResolver. Những cơ chế này chạy bên trong DispatcherServlet.

Nếu một @ControllerAdvice bắt AccessDeniedException và trả về view lỗi bình thường, DispatcherServlet đã xử lý exception. ExceptionTranslationFilter bên ngoài có thể không còn nhận được exception để gọi AccessDeniedHandler.

Ví dụ cần tránh nếu ứng dụng muốn Spring Security xử lý tập trung:

~~~java
@ExceptionHandler(AccessDeniedException.class)
public ModelAndView handleDenied(AccessDeniedException exception) {
    return new ModelAndView("booking/error");
}
~~~

Đoạn này có thể tạo response từ Spring MVC và bỏ qua chính sách AccessDeniedHandler đã cấu hình.

Các nguyên tắc:

- Không bắt AccessDeniedException trong global MVC advice chỉ để trả HTTP 200.
- Không đưa người dùng tới state lỗi của flow.
- Không để handler tổng quát bắt exception bảo mật rồi ghi response thành công.
- Để Spring Security AccessDeniedHandler chịu trách nhiệm nếu muốn dùng chính sách từ chối tập trung.
- Nếu ứng dụng thật sự cần xử lý ở MVC, phải chủ động bảo đảm response vẫn có semantics bảo mật đúng và kiểm thử toàn bộ đường đi; không đồng thời để nhiều tầng cạnh tranh quyền sở hữu response.

Tương tự, custom servlet filter hoặc interceptor không nên bắt mọi exception từ downstream rồi đổi thành response chung. Một filter catch-all có thể chặn exception trước khi nó tới ExceptionTranslationFilter tùy vị trí filter trong chain.

## 10. Trang access-denied không nên khởi động lại flow bị từ chối

Một cách xử lý sai là redirect người dùng tới chính flow đang bị bảo vệ, hoặc tạo một flow execution mới với hy vọng state khác sẽ hiển thị thông báo.

Ví dụ:

~~~text
/booking/review
    ↓ AccessDeniedException
redirect /booking
    ↓ flow lại kiểm tra quyền
    ↓ AccessDeniedException
redirect /booking
    ↓ lặp vô hạn
~~~

Trang access-denied nên là một endpoint độc lập, không cần vào flow bị từ chối. Nó có thể:

- Trả HTTP 403.
- Hiển thị hướng dẫn liên hệ quản trị viên.
- Cung cấp correlation ID để hỗ trợ tra cứu.
- Cho phép người dùng quay về trang an toàn hoặc dashboard.

Trang login và access-denied phải được phép truy cập theo URL security rules. Không để trang lỗi yêu cầu chính role vừa bị từ chối.

### 10.1. Không tiết lộ thông tin nhạy cảm

Không đưa vào trang lỗi:

- Tên role nội bộ hoặc toàn bộ danh sách authority.
- Chi tiết policy hoặc tenant của người khác.
- Stack trace hoặc tên lớp exception.
- Dữ liệu booking mà người dùng không được phép xem.
- Execution key, session ID hoặc token.

Có thể hiển thị thông báo chung như “Bạn không có quyền thực hiện thao tác này” và correlation ID. Log nội bộ ghi đủ thông tin để điều tra theo chính sách, nhưng không ghi token/cookie hoặc dữ liệu không cần thiết.

## 11. Khi quyền bị từ chối, flow và nghiệp vụ phải dừng ở đâu?

Khi transition approve bị từ chối bởi secured rule, flow không được thực hiện transition đó. Nếu service authorization từ chối trong lúc action gọi service, action cũng không được biến exception thành success hoặc tiếp tục side effect.

Một thiết kế đúng cần xác nhận:

1. Security rule từ chối trước khi action đặc quyền được chạy, nếu rule nằm ở transition.
2. Nếu service có object-level authorization, service kiểm tra quyền trước khi ghi.
3. Không có event success hoặc business-error giả được phát ra sau khi bị từ chối.
4. Không có bản ghi, notification hoặc external side effect được tạo.
5. Spring Security nhận exception và tạo response theo authentication hiện tại.

**Không dựa vào việc flow execution đã tồn tại để kết luận người dùng có quyền tiếp tục.** Role có thể bị thu hồi giữa hai request; listener kiểm tra ở các điểm được bảo vệ, còn service phải xác minh quyền trên tài nguyên trước side effect.

## 12. Kiểm thử: chứng minh exception đi tới Spring Security

Một unit test cho service hoặc flow action chưa đủ. Cần integration test có cả:

- Spring Security filter chain.
- FlowDefinitionRegistry và FlowExecutor thật của ứng dụng.
- SecurityFlowExecutionListener gắn đúng executor.
- FlowHandlerMapping và FlowHandlerAdapter.
- Authentication/authorities trong SecurityContext.
- AccessDeniedHandler hoặc AuthenticationEntryPoint thực tế.

### 12.1. Test anonymous bị từ chối khi bắt đầu flow

Với form login, request anonymous tới URL được bảo vệ thường được redirect tới login:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BookingFlowSecurityIT {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousUserIsSentToLogin() throws Exception {
        mvc.perform(get("/booking"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
~~~

Ví dụ giả định ứng dụng dùng form login và entry point redirect tới /login. Nếu ứng dụng là REST API hoặc dùng HTTP Basic/Bearer, kết quả có thể là 401 thay vì redirect.

### 12.2. Test người đã đăng nhập nhưng thiếu quyền vào state

Giả sử flow yêu cầu ROLE_USER ở root và ROLE_MANAGER ở state review. Người có ROLE_USER nhưng không có ROLE_MANAGER có thể bắt đầu flow nhưng bị từ chối khi transition vào review.

Kịch bản test:

1. GET entry URL của flow bằng người dùng ROLE_USER.
2. Đọc flow execution URL từ response/view.
3. POST event next bằng cùng session và CSRF token hợp lệ.
4. Xác nhận response bị từ chối theo cấu hình, thường là 403.
5. Xác nhận flow không render review.
6. Xác nhận không có action review đặc quyền nào được gọi.

Không hardcode execution key; phải lấy URL do SWF tạo ra.

### 12.3. Test transition bị từ chối

Người dùng có ROLE_USER và ROLE_MANAGER nhưng thiếu ROLE_APPROVER. Họ được vào review nhưng không được approve.

~~~java
@Test
@WithMockUser(roles = {"USER", "MANAGER"})
void managerWithoutApproverCannotApprove() throws Exception {
    MvcResult start = mvc.perform(get("/booking"))
        .andReturn();

    MockHttpSession session =
        (MockHttpSession) start.getRequest().getSession(false);

    String nextUrl = flowExecutionUrlFrom(start);

    MvcResult review = mvc.perform(
            post(nextUrl)
                .session(session)
                .with(csrf())
                .param("_eventId_next", "")
        )
        .andReturn();

    String approveUrl = flowExecutionUrlFrom(review);

    mvc.perform(
            post(approveUrl)
                .session(session)
                .with(csrf())
                .param("_eventId_approve", "")
        )
        .andExpect(status().isForbidden());

    verify(bookingService, never()).approve(any());
}
~~~

Đây là khung integration test; helper flowExecutionUrlFrom phải đọc URL execution được render bởi view thật của ứng dụng. Tên event và đường dẫn cần khớp flow definition. Test phải nạp filter chain và security listener thật; không mock bỏ qua tầng đang cần kiểm tra.

### 12.4. Kiểm tra không có side effect

Ngoài status code, cần xác nhận:

- Service approve không được gọi nếu transition-level secured rule từ chối trước action.
- Nếu service-level authorization từ chối, transaction không ghi dữ liệu.
- Booking vẫn ở trạng thái cũ.
- Không có email, message broker event hoặc notification thành công.
- Flow không chuyển tới state approved hay technicalError.
- AccessDeniedHandler được gọi đúng một lần theo chính sách ứng dụng.

Một response 403 nhưng database vẫn có bản ghi đã duyệt là lỗi nghiêm trọng. Kiểm thử phải quan sát cả HTTP và dữ liệu nghiệp vụ.

### 12.5. Test catch-all không nuốt exception

Nếu ứng dụng có custom action hoặc FlowExecutionExceptionHandler, tạo test để xác nhận:

- AccessDeniedException không bị đổi thành event error.
- Handler nghiệp vụ không nhận exception có cause là AccessDeniedException.
- Exception không bị chuyển thành state technicalError.
- Spring Security vẫn tạo phản hồi 403 hoặc yêu cầu login.

## 13. Chẩn đoán khi AccessDenied không tới đúng nơi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Bị đưa tới state technicalError thay vì 403 | Action hoặc FlowExecutionExceptionHandler bắt quá rộng | Tìm catch Exception/RuntimeException và mapping catch-all |
| Anonymous thấy trang lỗi 500 | Exception bị bọc hoặc bị MVC resolver xử lý sai | Kiểm tra stack trace và exception chain |
| Người đã login bị redirect login liên tục | AccessDenied bị nhầm với authentication hoặc access-denied page không public | Kiểm tra AuthenticationTrustResolver, entry point và URL rules |
| Người thiếu role vẫn vào được state | SecurityFlowExecutionListener chưa gắn đúng executor | Kiểm tra FlowHandlerAdapter đang dùng executor nào |
| Có secured nhưng không có 403 | Một lớp đã bắt/đổi exception trước khi filter xử lý | Kiểm tra action, handler, ControllerAdvice và servlet filter |
| AccessDeniedHandler không chạy | ExceptionTranslationFilter không nhận exception hoặc request không nằm trong filter chain | Kiểm tra filter chain, servlet mapping và exception resolver |
| Response 403 nhưng action vẫn ghi dữ liệu | Side effect xảy ra trước authorization hoặc transaction không rollback | Kiểm tra thứ tự authorization/service/transaction |
| Trang access-denied lặp redirect | Endpoint access-denied cũng bị bảo vệ hoặc redirect về flow bị từ chối | Cho phép trang lỗi và dùng endpoint độc lập |
| Test pass nhưng runtime không xử lý đúng | Test bỏ qua filter chain hoặc dùng executor khác | Chạy full integration context giống deployment |

### 13.1. Kiểm tra thứ tự filter

Spring Security dùng SecurityFilterChain để bao quanh request. ExceptionTranslationFilter phải nằm trong chain đang xử lý flow URL và bao quanh downstream execution. Nếu một custom filter đứng sai vị trí hoặc bắt exception từ downstream, nó có thể ngăn exception tới filter dịch bảo mật.

Bật log DEBUG cho Spring Security trong môi trường phát triển để xem filter chain được đăng ký. Không bật log nhạy cảm ở production nếu log có thể chứa request data, cookie hoặc token.

### 13.2. Kiểm tra exception resolver

Nếu log cho thấy DispatcherServlet đã resolve AccessDeniedException thành view, ExceptionTranslationFilter có thể không còn nhận được exception. Rà soát @ControllerAdvice, @ExceptionHandler và HandlerExceptionResolver có phạm vi catch-all.

### 13.3. Kiểm tra đúng FlowExecutor

Một ứng dụng có thể có nhiều FlowExecutor hoặc nhiều web application context. Đảm bảo executor mà FlowHandlerAdapter sử dụng có SecurityFlowExecutionListener. Không chỉ kiểm tra bean tồn tại; phải xác minh bean đó được gắn vào đúng executor đang phục vụ URL.

## 14. Bài tập thực hành: bảo vệ thao tác approve

Tạo flow booking gồm details, review và approved.

**Chính sách:**

- ROLE_USER được bắt đầu flow.
- ROLE_MANAGER được vào review.
- ROLE_APPROVER được thực hiện approve.
- Service chỉ cho phép approver xử lý booking thuộc phạm vi được phân công.

**Yêu cầu triển khai:**

1. Cấu hình SecurityFilterChain bảo vệ URL booking.
2. Cấu hình login page và access-denied page được phép truy cập.
3. Đặt secured rule ở root flow, state review và transition approve.
4. Gắn SecurityFlowExecutionListener vào FlowExecutor được MVC adapter sử dụng.
5. Trong action, chỉ bắt BookingConflictException hoặc các business exception cụ thể.
6. Không bắt AccessDeniedException để trả event denied.
7. Không map RuntimeException hoặc Exception sang technicalError.
8. Nếu custom FlowExecutionExceptionHandler xét cause chain, loại trừ AccessDeniedException.
9. Không để @ControllerAdvice catch-all biến AccessDenied thành response 200.
10. Viết MockMvc test anonymous, USER thiếu MANAGER, MANAGER thiếu APPROVER và APPROVER hợp lệ.
11. Gửi trực tiếp event approve để chứng minh server-side transition rule hoạt động.
12. Xác nhận service không ghi dữ liệu khi quyền bị từ chối.
13. Xác nhận AccessDeniedHandler trả 403 cho người đã đăng nhập nhưng thiếu quyền.
14. Xác nhận AuthenticationEntryPoint xử lý anonymous theo chính sách login/API.

### Câu hỏi tự kiểm tra

**1. Vì sao AccessDeniedException phải đi ra khỏi flow?** Để Spring Security nhận diện và chuyển nó thành login/401 hoặc access-denied/403 theo Authentication hiện tại.

**2. Người dùng đã đăng nhập nhưng thiếu ROLE_APPROVER thường được xử lý thế nào?** AccessDeniedHandler xử lý, thường trả 403 hoặc trang từ chối.

**3. Người anonymous bị từ chối ở flow được bảo vệ thì sao?** Spring Security thường gọi AuthenticationEntryPoint để yêu cầu xác thực.

**4. ExceptionTranslationFilter có quyết định người dùng được vào state không?** Không. Nó chuyển exception bảo mật thành HTTP response; quyết định được thực hiện bởi authorization component như SecurityFlowExecutionListener.

**5. Vì sao catch Exception trong action nguy hiểm?** Vì AccessDeniedException là runtime exception và có thể bị đổi thành event nghiệp vụ, khiến Spring Security không nhận được.

**6. Có nên map RuntimeException sang technicalError không?** Không. Mapping này có thể bắt cả AccessDeniedException và làm mất ranh giới bảo mật.

**7. FlowExecutionExceptionHandler có thay AccessDeniedHandler không?** Không. Một bên điều khiển exception trong flow execution; một bên xử lý phản hồi bảo mật ở HTTP boundary.

**8. Vì sao test cần gửi event trực tiếp?** Vì ẩn nút trên giao diện không bảo vệ transition; người dùng có thể tự gửi request event.

**9. Nếu @ControllerAdvice bắt AccessDeniedException thì điều gì có thể xảy ra?** Spring MVC có thể resolve exception trước khi nó thoát ra filter chain, khiến AccessDeniedHandler không được gọi.

**10. Vì sao cần kiểm tra database sau response 403?** Để chắc chắn thao tác bị từ chối không tạo side effect trước khi authorization hoàn tất.

## 15. Checklist trước khi phát hành

- [ ] SecurityFilterChain bao phủ đúng URL flow và servlet mapping.
- [ ] FlowExecutor mà FlowHandlerAdapter sử dụng có SecurityFlowExecutionListener.
- [ ] Secured rule được đặt đúng ở flow, state và transition.
- [ ] AccessDeniedException không bị bắt rồi đổi thành event hoặc message thông thường.
- [ ] Action chỉ bắt business exception cụ thể.
- [ ] FlowExecutionExceptionHandler không map AccessDeniedException hoặc lớp cha quá rộng.
- [ ] Custom handler xét cause chain và loại trừ exception bảo mật.
- [ ] @ControllerAdvice không vô tình resolve AccessDeniedException trước Spring Security.
- [ ] Custom servlet filter không nuốt exception từ downstream.
- [ ] Anonymous được chuyển tới AuthenticationEntryPoint theo chính sách.
- [ ] Người đã xác thực nhưng thiếu quyền được xử lý bởi AccessDeniedHandler.
- [ ] Trang login và access-denied không bị bảo vệ gây redirect loop.
- [ ] Không đưa người dùng tới flow state bị từ chối để hiển thị lỗi.
- [ ] Không lộ stack trace, authority nội bộ, tenant data hoặc execution key.
- [ ] Service kiểm tra quyền trên tài nguyên trước side effect.
- [ ] Test bao phủ anonymous, state denial, transition denial và service-level denial.
- [ ] Test gửi trực tiếp event và xác nhận không có side effect.
- [ ] Test dùng filter chain, flow executor và listener giống runtime.
- [ ] Log và audit đủ thông tin điều tra nhưng không chứa token/cookie.

**Ghi nhớ:** Spring Web Flow dùng SecurityFlowExecutionListener để kiểm tra quyền tại flow, state và transition. Khi quyền bị từ chối, AccessDeniedException phải đi lên khỏi execution stack để Spring Security xử lý. Anonymous thường đi qua AuthenticationEntryPoint; người đã đăng nhập nhưng thiếu quyền đi qua AccessDeniedHandler. Đừng bắt exception này trong action, map nó sang state lỗi hoặc để MVC catch-all xử lý như lỗi thông thường. Hãy kiểm thử cả HTTP response lẫn việc không có side effect để bảo đảm ranh giới bảo mật được giữ nguyên.

### Tài liệu tham khảo

- [Spring Web Flow 3.0 Reference — Securing Flows](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/)
- [Spring Web Flow 2.5.1 Reference — Securing Flows](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/)
- [Spring Web Flow 3.0.1 API — SecurityFlowExecutionListener](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/security/SecurityFlowExecutionListener.html)
- [Spring Web Flow 3.0 API — FlowExecutionExceptionHandler](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/engine/FlowExecutionExceptionHandler.html)
- [Spring Security Reference — Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/7.1/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security Reference — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

