# Đối chiếu kiểm thử bộ máy flow với kiểm thử qua HTTP

Trong **Spring Web Flow (SWF)**, một hành trình web có thể đi qua nhiều **state**, nhận các **event**, áp dụng **transition**, giữ dữ liệu trong **scope**, gọi **subflow**, thực hiện **form binding** và **validation** trước khi kết thúc. Khi viết kiểm thử cho hành trình như vậy, có hai câu hỏi khác nhau:

- **Bộ máy flow có chuyển đúng trạng thái và giữ đúng dữ liệu không?**
- **Một người dùng thực sự gửi request HTTP qua Spring MVC có thể đi hết hành trình đó không?**

Kiểm thử bộ máy flow (flow execution test) trả lời chủ yếu câu hỏi thứ nhất. Kiểm thử tích hợp qua HTTP (HTTP integration test) trả lời câu hỏi thứ hai, bao gồm những thứ flow engine không tự mô phỏng: ánh xạ URL, session/cookie, flow execution key, HTML form, event parameter, Spring Security, view resolver và phản hồi HTTP.

Bài học thuộc chương **Kiểm thử tích hợp** của module **SPRING_WEB_FLOW**. Chúng ta sẽ dùng cùng một quy trình đăng ký nhiều bước để đối chiếu hai tầng kiểm thử, thiết kế bộ ca kiểm tra không trùng lặp và nhận diện các lỗi chỉ xuất hiện khi đi qua HTTP.

## 1. Hai ranh giới kiểm thử khác nhau

Sơ đồ sau thể hiện đường đi của request trong ứng dụng web:

~~~mermaid
flowchart TB
    B["Trình duyệt / HTTP client"] --> H["Spring MVC / FlowHandlerMapping"]
    H --> A["FlowHandlerAdapter và FlowExecutor"]
    A --> F["Flow definition: state, event, transition"]
    F --> S["Flow scope, action, validation, subflow"]
    F --> V["View resolver / JSP / Thymeleaf"]
    V --> B

    T1["Flow execution test"] -. "Bắt đầu, phát event, đọc state/scope" .-> F
    T2["HTTP integration test / MockMvc"] -. "GET/POST, session, headers, form" .-> H
~~~

**Kiểm thử bộ máy flow** thường khởi động một flow definition trong test harness của SWF, giả lập event và kiểm tra trạng thái hiện tại. Nó hữu ích để xác nhận biểu đồ chuyển trạng thái, điều kiện transition, action, validation và biến scope.

**Kiểm thử qua HTTP** tạo request tới endpoint thực tế của ứng dụng, để Spring MVC tìm flow và SWF xử lý execution theo cấu hình đã đăng ký. Nó kiểm tra cả cách view được render, tên tham số event, URL chứa execution key, việc giữ session và phản hồi khi request tiếp theo đến.

| Chiều đối chiếu | Kiểm thử bộ máy flow | Kiểm thử tích hợp qua HTTP |
|---|---|---|
| Điểm vào | Flow definition và flow test harness | URL được ánh xạ bởi Spring MVC |
| Cách kích hoạt hành động | Gọi thao tác start/signal event của harness | GET/POST với parameter và session/cookie |
| Kiểm tra mạnh nhất | State, event, transition, flowScope, action, subflow | Handler mapping, binding từ request, render view, session, bảo mật, redirect |
| Thấy HTML thực tế? | Thường không, trừ khi tự kết hợp renderer | Có nếu test cấu hình renderer và view thật |
| Thấy mã trạng thái HTTP? | Không phải trọng tâm | Có: 200, 302, 400, 403… tùy contract |
| Phát hiện form gửi sai event name? | Không, nếu gọi event trực tiếp | Có |
| Phát hiện lỗi view resolver/template? | Thường không | Có |
| Tốc độ và chẩn đoán | Thường nhanh, lỗi gọn ở state/action | Thường nặng hơn, nhưng bao phủ tích hợp |
| Service phụ thuộc | Dễ dùng stub/mock | Có thể dùng mock hoặc service/DB kiểm thử |
| Kết luận khi PASS | Flow engine chạy đúng theo đầu vào mô phỏng | Đường đi HTTP được kiểm tra hoạt động trong cấu hình test |

**Không nên xem hai loại test là tương đương.** Một flow test có thể PASS dù form dùng `_eventId_save` trong khi XML chỉ có transition `confirm`. Ngược lại, một HTTP test có thể kiểm tra giao diện đúng nhưng thiếu xác nhận giá trị thực sự còn trong `flowScope` sau khi quay lại một bước.

## 2. Một kịch bản nghiệp vụ dùng chung

Ta xây dựng flow đăng ký gồm ba phần:

1. **contact**: nhập họ tên và email.
2. **review**: đọc lại thông tin, có thể quay về sửa.
3. **persist**: gọi service tạo đăng ký rồi kết thúc tại **completed**.

Flow có thêm **cancelled** để người dùng hủy mà không lưu. Model tạm được giữ trong `flowScope` để qua các request vẫn dùng cùng bản nháp.

~~~mermaid
stateDiagram-v2
    [*] --> contact
    contact --> review: next [hợp lệ]
    contact --> contact: next [validation fail]
    contact --> cancelled: cancel
    review --> contact: back
    review --> persist: confirm
    persist --> completed: success
    cancelled --> [*]
    completed --> [*]
~~~

Ví dụ flow XML đơn giản, minh họa vai trò của các tầng kiểm thử:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="draft"
         class="com.example.registration.RegistrationDraft"/>

    <view-state id="contact"
                view="registration/contact"
                model="draft">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>

        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false"/>
    </view-state>

    <view-state id="review"
                view="registration/review"
                model="draft">
        <transition on="back" to="contact"
                    bind="false" validate="false"/>
        <transition on="confirm" to="persist"
                    bind="false" validate="false"/>
    </view-state>

    <action-state id="persist">
        <evaluate expression="registrationService.save(draft)"
                  result="flowScope.registrationId"/>
        <transition on="success" to="completed"/>
    </action-state>

    <end-state id="completed"
               view="registration/completed"/>
    <end-state id="cancelled"
               view="registration/cancelled"/>
</flow>
~~~

Ở ví dụ này, `registrationService` là Spring bean của ứng dụng và có thể được thay bằng stub trong test. Phương thức `save` trả về một ID khi xử lý thành công. Nếu nó ném exception, SWF **không mặc nhiên biến exception thành event `failure`**. Ứng dụng muốn cho phép thử lại phải định nghĩa cơ chế xử lý lỗi riêng, chẳng hạn action trả về kết quả nghiệp vụ có kiểm soát hoặc exception handler phù hợp.

Một draft để binding:

~~~java
package com.example.registration;

import java.io.Serializable;

public class RegistrationDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    private String fullName;
    private String email;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Flow trên phục vụ minh họa. Khi áp dụng vào dự án cần cung cấp flow registry, executor, view resolver, bean `registrationService`, form tương ứng và validation cho dữ liệu. Đường dẫn view và URL HTTP cụ thể phụ thuộc cấu hình ứng dụng.

## 3. Kiểm thử bộ máy flow: làm việc trực tiếp với execution

SWF có các lớp kiểm thử chuyên dụng như `AbstractFlowExecutionTests` và `AbstractXmlFlowExecutionTests` trong họ package `org.springframework.webflow.test.execution` ở các phiên bản SWF 2.x. Tùy phiên bản và cách ứng dụng quản lý flow definition, có thể cần cấu hình thêm đường dẫn tài nguyên hoặc builder context.

Cách tiếp cận thường có các bước:

1. Nạp flow definition cần kiểm thử.
2. Cấu hình service giả (mock/stub), dữ liệu đầu vào và `ExternalContext` nếu cần.
3. Gọi thao tác bắt đầu flow.
4. Phát event như `next`, `back` hoặc `confirm`.
5. Xác nhận state, biến trong scope, kết quả action và thông báo validation.

Một ví dụ rút gọn theo API kiểm thử SWF 2.x:

~~~java
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;
import org.springframework.webflow.test.MockFlowBuilderContext;

public class RegistrationFlowTests
        extends AbstractXmlFlowExecutionTests {

    private final RegistrationServiceStub service =
            new RegistrationServiceStub();

    @Override
    protected void registerMockServices(MockFlowBuilderContext context) {
        context.registerBean("registrationService", service);
    }

    public void testStartsAtContact() {
        startFlow();

        assertCurrentStateEquals("contact");
        assertNotNull(getFlowScope().get("draft"));
    }

    public void testNextThenBackKeepsDraft() {
        startFlow();

        RegistrationDraft draft =
                (RegistrationDraft) getFlowScope().get("draft");
        draft.setFullName("Lan");
        draft.setEmail("lan@example.test");

        signalEvent("next");
        assertCurrentStateEquals("review");

        signalEvent("back");
        assertCurrentStateEquals("contact");

        RegistrationDraft afterBack =
                (RegistrationDraft) getFlowScope().get("draft");
        assertEquals("Lan", afterBack.getFullName());
        assertEquals("lan@example.test", afterBack.getEmail());
    }
}
~~~

Trong ví dụ, `RegistrationServiceStub` là test double do dự án cung cấp. Test harness có thể phải được cấu hình thêm để tìm đúng tài nguyên XML; các tên lớp/method cần đối chiếu với phiên bản SWF mà dự án sử dụng trước khi biên dịch.

**Giới hạn quan trọng của test này:** nó **gán trực tiếp** `draft.fullName` và `draft.email` rồi phát event. Như vậy, ta đã kiểm tra transition và vòng đời model, **chưa kiểm tra HTTP form binding**. Một form HTML gửi nhầm tên `mail` thay vì `email` vẫn có thể lọt qua phép thử này.

### Kiểm thử binding ở mức flow engine

Nếu cần kiểm tra cả binding trong flow test, hãy dựng một `MockExternalContext` có request parameter tương ứng, dùng API start/signal event có hỗ trợ context theo phiên bản, rồi assert model sau khi SWF xử lý request. Đối tượng này giả lập dữ liệu từ request, nhưng **không phải** một HTTP request thực chạy qua `DispatcherServlet`.

Có thể tách hai bài kiểm tra:

| Test | Dữ liệu được đưa vào bằng cách nào? | Điều đã chứng minh |
|---|---|---|
| `nextKeepsDraft` | Gán trực tiếp model trong flow scope | State và dữ liệu được giữ qua transition |
| `nextBindsEmail` | MockExternalContext với parameter `email` | Binder của view-state cập nhật trường hợp lệ |
| `invalidEmailShowsError` | Input sai + validator cấu hình cho state | Ở lại state và có message gắn field |
| `confirmCallsSaveOnce` | Flow đi tới action-state với stub ghi số lần gọi | Event confirm kích hoạt action đúng lần |

Kiểm thử bộ máy flow đặc biệt hữu ích khi flow có nhiều nhánh, guard hoặc subflow. Chẳng hạn, nếu transition `next` chỉ được thực hiện khi một điều kiện nghiệp vụ đúng, có thể dựng từng đầu vào khác nhau rồi assert state tương ứng mà không cần khởi động toàn bộ tầng HTTP.

## 4. Kiểm thử qua HTTP: đi từ URL tới view và trở lại

Một HTTP integration test phải đi qua các thành phần đủ gần với cấu hình chạy thực tế:

~~~mermaid
sequenceDiagram
    participant T as HTTP Test / MockMvc
    participant M as Spring MVC
    participant W as Spring Web Flow
    participant V as View Renderer

    T->>M: GET /registration
    M->>W: Tìm flow và bắt đầu execution
    W->>V: Render contact, model và execution URL
    V-->>T: HTTP response + form
    T->>M: POST action URL + _eventId_next + fields + session
    M->>W: Resume execution theo key
    W->>W: Bind, validate, transition
    W->>V: Render review hoặc contact có lỗi
    V-->>T: HTTP response / redirect
~~~

Những thứ cần được bảo toàn qua các request gồm **session**, flow execution key và các dữ liệu bảo mật cần thiết (ví dụ CSRF token khi security được bật).

### Các thành phần cấu hình phải tồn tại

Để thử đúng đường đi HTTP, môi trường test cần nạp:

- Spring MVC mapping tới flow (thường qua `FlowHandlerMapping` và `FlowHandlerAdapter`).
- `FlowExecutor`, flow registry và execution repository theo cấu hình ứng dụng.
- View resolver/template thực tế hoặc renderer kiểm thử đủ tương đương.
- Security filter chain nếu mục tiêu bao gồm authentication, authorization hoặc CSRF.
- Các bean được flow gọi và kho dữ liệu test tương ứng với phạm vi kiểm tra.

Nếu dùng Spring Boot với servlet/MVC, có thể sử dụng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`. Với ứng dụng Spring MVC truyền thống, cấu hình test thường dùng `@WebAppConfiguration`, `@ContextConfiguration` và `MockMvcBuilders.webAppContextSetup(...)`. **Không nên giả định `@WebMvcTest` mặc định nạp toàn bộ bean SWF**, vì một slice test có thể bỏ sót flow registry hoặc flow executor.

### Phác thảo một HTTP test bằng MockMvc

Ví dụ dưới đây trình bày cấu trúc cần kiểm tra. Hai hàm hỗ trợ `formAction` và `renderFollowingRedirect` được chủ ý đặt là helper của test suite, vì cách trích HTML, decode URL và chính sách redirect phụ thuộc view thực tế.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RegistrationHttpIT {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormOpensReview() throws Exception {
        MvcResult start = mvc.perform(get("/registration"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                start.getRequest().getSession(false);

        String html = start.getResponse().getContentAsString();
        String action = formAction(html, "contactForm");

        MvcResult next = mvc.perform(
                post(action)
                    .session(session)
                    .with(csrf())
                    .param("_eventId_next", "")
                    .param("fullName", "Lan")
                    .param("email", "lan@example.test"))
                .andReturn();

        String page = renderFollowingRedirect(next, session);
        assertThat(page).contains("Xác nhận");
        assertThat(page).contains("lan@example.test");
    }

    // formAction: parse <form id="contactForm" action="...">,
    // decode HTML entities and preserve the execution key.
    //
    // renderFollowingRedirect: if HTTP 3xx, request Location
    // with the same session; otherwise return response body.
    //
    // Imports, helpers, Security test support and application
    // configuration are intentionally project-specific.
}
~~~

Đây là **khung tích hợp có chú giải**, không phải một lớp Java đầy đủ có thể copy rồi chạy ngay mà không cung cấp helper, import, view và bean. Nếu test không bật Spring Security, có thể không cần `.with(csrf())`; nếu có bật, cần thêm dependency Spring Security Test và bảo đảm token hợp lệ. Khi áp dụng, dùng URL thực tế do form tạo, không tự bịa một execution key.

Trong nhiều ứng dụng SWF, form submit dùng tên button `_eventId_next` để phát event `next`; URL của form chứa thông tin nhận diện execution, thường gặp tham số `execution`. Chi tiết có thể khác theo view technology và cấu hình; **hãy lấy URL từ response HTML**. Việc hardcode giá trị như `execution=e1s1` sẽ làm test dễ vỡ khi sequence hay cách lưu execution thay đổi.

### MockMvc kiểm tra đến đâu?

`MockMvc` mô phỏng tầng Servlet/Spring MVC mà không cần mở socket mạng thật. Nó phù hợp để kiểm tra mapping, filter, session giả, HTML render và response của server. Nhưng nó **không tự chạy JavaScript của trình duyệt**, không đảm bảo hành vi CSS/UI, không chứng minh cookie hoạt động qua trình duyệt thực và không kiểm tra HTTP proxy/load balancer bên ngoài ứng dụng.

Nếu workflow phụ thuộc JavaScript, AJAX partial rendering, cookie chính sách SameSite, reverse proxy hoặc hành vi Back/Refresh của trình duyệt, nên bổ sung test với trình duyệt thật hoặc test end-to-end qua cổng HTTP chạy thực tế.

## 5. Bảng đối chiếu ca kiểm thử theo hành vi

Dùng **cùng một hợp đồng nghiệp vụ** nhưng quan sát ở hai biên khác nhau.

| Tình huống | Flow execution test cần assert | HTTP integration test cần assert |
|---|---|---|
| Mở hành trình | State đầu là `contact`; draft tồn tại | GET đúng URL thành công; form hiển thị; action URL hợp lệ |
| Nhấn Next hợp lệ | Sang `review`, draft giữ dữ liệu | POST đúng event/field/session; view Review hiển thị dữ liệu |
| Email thiếu/sai | Không chuyển state; có lỗi của `email` | Form hiển thị lỗi cạnh trường email; dữ liệu khác còn |
| Nhấn Back | Về `contact`; draft không bị reset | Form gửi `_eventId_back`, các giá trị cũ xuất hiện |
| Nhấn Cancel | Kết thúc nhánh `cancelled`; không gọi save | Request hủy đi đúng trang và không tạo dữ liệu |
| Confirm thành công | Action save được gọi đúng và flow kết thúc | Request confirm đi tới kết quả, dữ liệu ghi đúng |
| Action trả lỗi nghiệp vụ | Chuyển nhánh lỗi được thiết kế | Thông báo lỗi có ích, không rò rỉ stack trace |
| Execution key cũ/sai | Test harness có thể kiểm tra invalid execution nếu hỗ trợ | HTTP trả phản hồi/redirect theo chính sách hết hạn |
| Hai flow chạy song song | Hai execution có flowScope riêng | Hai session hoặc hai execution trong cùng session không ghi đè |
| CSRF/authorization | Không thuộc mục tiêu mặc định của test state | Filter từ chối request không hợp lệ theo chính sách |

Các ca hàng đầu nên có ở **cả hai tầng** dưới dạng gọn, nhưng không cần sao chép nguyên mọi tổ hợp input. Những nhánh điều hướng phức tạp có thể kiểm tra sâu ở flow test; tầng HTTP chọn vài đường đi quan trọng để chứng minh wiring, form, session và security hoạt động.

## 6. Kiểm tra validation và form binding mà không tự đánh lừa mình

Lỗi thường gặp nhất là một test đặt giá trị trực tiếp vào model rồi kết luận “form binding hoạt động”. Thực tế, luồng chưa hề nhận dữ liệu từ HTTP.

Để kiểm thử chính xác:

1. **Tại flow engine**, xác minh validator tạo lỗi tại đúng field/source và giữ state tương ứng. Nếu muốn kiểm tra binder ở tầng này, phải dùng `MockExternalContext` với request parameters.
2. **Tại HTTP**, gửi tên field đúng như HTML thật (`email`, `contact.email`, ...), event `_eventId_next`, session và token phù hợp.
3. Sau khi server trả về, kiểm tra lỗi đã được render ở vị trí đúng, không chỉ assert status 200.
4. Đảm bảo nhấn `back` hoặc `cancel` không bị validation của bước hiện tại chặn khi flow đã chủ động cấu hình `bind="false" validate="false"`.
5. Thử thêm tham số ngoài whitelist, ví dụ `approved=true`, rồi kiểm tra hệ thống không cập nhật các trường không được phép. Service vẫn phải kiểm tra quyền và bất biến nghiệp vụ trước khi lưu.

### Phân biệt lỗi chuyển kiểu và lỗi validation

Giả sử bước đặt lịch có trường `startDate` kiểu `LocalDate`. Giá trị `startDate=abc` có thể thất bại ngay ở **conversion/binding**. Giá trị `startDate=2027-01-01` chuyển kiểu hợp lệ nhưng có thể vi phạm quy tắc “không chọn quá xa trong tương lai”.

Hai lỗi cần test riêng vì logic chạy ở hai vị trí khác nhau. Nếu chỉ kiểm tra validator, ứng dụng vẫn có thể ném lỗi không mong muốn từ conversion hoặc hiển thị sai thông báo.

### Test invalid input phải giữ dữ liệu hợp lệ

Một lỗi email không nên xóa họ tên đã nhập. Khi test qua HTTP, assert cả vùng báo lỗi và input/value giữ lại sau render. Đây là nơi một flow test chỉ assert state không đủ để chứng minh UX.

## 7. Kiểm tra session và flow execution key

SWF thường dùng cơ chế lưu flow execution ở tầng phiên hoặc repository được cấu hình, và client gửi lại khóa execution để tiếp tục. Test cần hiểu rằng **execution key là giá trị opaque do framework phát hành**, không phải một ID để tự tăng hay tự đoán.

Một đường đi HTTP chuẩn:

1. GET endpoint bắt đầu flow.
2. Đọc action URL hoặc hidden field mang execution key từ HTML.
3. Gửi POST với action/key hiện tại và đúng session.
4. Đọc phản hồi mới; nếu bước tiếp theo tạo URL/key mới, lấy từ phản hồi mới.
5. Lặp lại đến khi flow hoàn tất.

Không nên dùng cùng một execution key cũ cho mọi POST nếu repository thực tế phát hành snapshot key mới sau các bước. Tùy cấu hình execution repository và history, một key cũ có thể được cho phép, dẫn đến trạng thái lịch sử hoặc bị từ chối. **Đừng viết assertion cứng về hành vi đó nếu chưa có contract ứng dụng.**

### Kiểm thử hai hành trình trong cùng session

Một người có thể mở hai tab đăng ký. Thiết kế đúng thường cần hai execution độc lập, mỗi execution giữ draft riêng.

~~~text
Session S
├── Execution A → flowScope.draft.email = a@example.test
└── Execution B → flowScope.draft.email = b@example.test
~~~

Test cần mở **hai flow execution mới** trong cùng session, lấy hai action URL khác nhau, POST riêng cho từng execution và kiểm tra kết quả không lẫn. Nếu ứng dụng tự giữ draft trong một thuộc tính cố định của `HttpSession`, hai tab có thể ghi đè dữ liệu dù từng flow test độc lập đều PASS.

### Session hết hạn và request lặp

Các trường hợp đáng thử ở tầng HTTP:

- Request dùng execution key không tồn tại hoặc session đã hết hạn.
- Submit lại cùng request sau khi thành công.
- Refresh trang Review.
- Người dùng bấm Back rồi gửi biểu mẫu từ snapshot cũ.
- Hai request gần đồng thời vào cùng execution.

Kết quả đúng tùy chính sách ứng dụng: thông báo phiên hết hạn, redirect đến entry point, HTTP lỗi có kiểm soát, từ chối submission cũ hoặc hiển thị hướng dẫn khởi động lại. Không được mặc định SWF sẽ khôi phục được bản nháp sau session timeout. Hãy xác định behavior và viết assertion tương ứng.

**Lưu ý về idempotency:** Kết thúc flow không tự giải quyết mọi tình huống bấm Confirm hai lần. Service cần cơ chế phù hợp như ràng buộc duy nhất hoặc idempotency key để ngăn tạo dữ liệu trùng.

## 8. Kiểm tra Spring MVC, view và Security

Đây là nhóm lỗi mà flow engine test hầu như không phát hiện được.

### Handler mapping và view resolver

Một flow có thể có XML hợp lệ nhưng URL `/registration` không được ánh xạ, dẫn đến 404. Hoặc flow chạy tới state `review` nhưng view resolver tìm sai template, dẫn đến 500. HTTP test phải bao phủ ít nhất một đường đi render qua từng loại view chính.

Không chỉ assert `status().isOk()`. Hãy tìm một phần tử có ý nghĩa như tiêu đề, form ID, nút sự kiện, thông báo validation hoặc dữ liệu đã nhập. Nếu view có redirect, theo `Location` bằng cùng session rồi mới kiểm tra HTML cuối.

### Spring Security và CSRF

Nếu ứng dụng bảo vệ luồng bằng Spring Security, HTTP test nên kiểm tra:

- Người chưa đăng nhập có được bắt đầu flow không?
- Người dùng hợp lệ có thể gửi POST kèm token CSRF không?
- Request thiếu hoặc sai CSRF token bị chặn theo cấu hình thực tế?
- Người dùng không có quyền có thể gọi URL/state/action trực tiếp hay không?
- Kết quả lưu có dùng danh tính đã xác thực phía server, thay vì một hidden field dễ sửa?

Khi dùng `MockMvc` với Spring Security Test, `.with(csrf())` giúp tạo request hợp lệ cho đường đi chính; một test độc lập nên cố ý **không** thêm token để xác minh hành vi bảo vệ, nếu CSRF được yêu cầu. Cần nạp filter chain tương ứng, vì MockMvc không có security filter thì test thiếu token vẫn có thể PASS một cách vô nghĩa.

### Locale và lỗi hiển thị

Nếu flow sử dụng message code và `MessageSource`, tầng HTTP phải kiểm tra ít nhất một trường hợp đổi locale:

- Gửi email sai trong locale `vi`, xác nhận thông báo tiếng Việt.
- Gửi cùng trường hợp trong locale `en`, xác nhận thông báo tiếng Anh.
- Bảo đảm state và dữ liệu không thay đổi chỉ vì đổi ngôn ngữ.

Flow execution test có thể xác nhận code hoặc source của message; HTTP test mới chứng minh resolver và template hiển thị văn bản phù hợp.

## 9. Đối chiếu lỗi action và phục hồi flow

Trong hành trình thực, lỗi có thể đến từ validation, service, database hoặc hệ thống ngoài. Nên test **nhánh lỗi có chủ đích**, không chỉ cố tình ném exception rồi hy vọng flow sẽ tự xử lý.

~~~mermaid
flowchart LR
    A["review + confirm"] --> B["persist action"]
    B --> C{"Kết quả nghiệp vụ"}
    C -->|Thành công| D["completed"]
    C -->|Không thể xử lý, có thể thử lại| E["review + thông báo chung"]
    C -->|Lỗi không phục hồi| F["error state / exception handler"]
~~~

Để nhánh “không thể lưu” có thể kiểm thử:

1. Định nghĩa một **hợp đồng service/action** trả kết quả nghiệp vụ rõ ràng, ví dụ thành công hoặc thất bại có mã.
2. Action của flow chuyển kết quả đó thành event/transition đúng theo cấu hình.
3. Với lỗi có thể thử lại, giữ draft và cung cấp message an toàn.
4. Với lỗi không thể phục hồi, chuyển sang màn hình hoặc exception handler phù hợp.
5. Bổ sung cơ chế bảo vệ giao dịch/idempotency trước request lặp.

**Ở flow test**, dùng stub cho service để tạo từng loại kết quả, assert state và số lần gọi. **Ở HTTP test**, gửi request confirm thật, assert trang lỗi, message, dữ liệu còn trên Review và việc thử lại. Nếu cần chứng minh transaction rollback hoặc ràng buộc database, phải có test tầng dữ liệu phù hợp, vì stub thuần không thể xác nhận hành vi của database.

## 10. Mức độ “tích hợp” phải được gọi đúng tên

Không phải cứ có `@SpringBootTest` là đã bao phủ mọi hệ thống. Cần biết test đang thay thế những thành phần nào.

| Cấu hình | Thành phần thật | Điều chưa được chứng minh |
|---|---|---|
| Flow test + stub service | Flow definition, state/transition, model/validator tương ứng | MVC mapping, HTML, filter, session HTTP, database |
| MockMvc + mock service | MVC/SWF/view/filter nếu đã nạp đầy đủ | Giao dịch và tích hợp database/service thật |
| MockMvc + test database | MVC/SWF/service/persistence thật trong môi trường test | Socket, reverse proxy, browser JavaScript, hạ tầng ngoài |
| HTTP client tới server test | Server HTTP, cookie, endpoint và cấu hình runtime test | Có thể chưa có proxy/SSO/cloud như production |
| Browser end-to-end | Render UI, JavaScript, điều hướng người dùng | Phân tích sâu từng branch/condition nếu không có test flow riêng |

Không cần chạy toàn bộ các tầng cho mọi commit. Một cách phân bổ hợp lý là:

- Nhiều **flow tests** cho nhánh transition, guard, validation và subflow.
- Một số **HTTP integration tests** cho đường đi chính, lỗi validation, Back/Cancel, flow key, session và security.
- Ít **browser tests** cho trường hợp cần JavaScript, AJAX, lịch sử trình duyệt hoặc hoạt động qua nhiều tab thực.

Mục tiêu là mỗi tầng chứng minh phần hành vi mà tầng khác dễ bỏ sót.

## 11. Tổ chức fixture, dữ liệu và isolation

Kiểm thử nhiều request có thể thất bại ngẫu nhiên nếu state của test trước còn lưu trong session, database hoặc mock.

**Với flow test:**

- Bắt đầu một flow execution mới cho mỗi ca.
- Stub service có trạng thái được reset trước mỗi test.
- Input, event và kỳ vọng phải rõ ràng, không chia sẻ draft mutable giữa các test.
- Nếu test subflow, cần mock đủ input/output contract và assert đường quay về flow cha.

**Với HTTP test:**

- Tạo hoặc giữ `MockHttpSession` theo từng test case. Chỉ chia session giữa các request của **cùng một hành trình**.
- Luôn lấy flow execution URL mới từ HTML/redirect khi cần.
- Dữ liệu test cần tách biệt bằng ID/email riêng hoặc cleanup có chủ đích.
- Không phụ thuộc thứ tự các test trong cùng class.
- Với database thật, kiểm tra chiến lược rollback/cleanup phù hợp. Đừng giả định `@Transactional` ở phía test luôn bao phủ các giao dịch chạy ở thread hoặc server khác.

**Với các test lỗi có thể thử lại:** nên dùng một fake service có thể đổi trạng thái từ thất bại sang thành công, nhưng cần xác nhận sau lần thất bại không có bản ghi sai, rồi thử lại và bảo đảm chỉ có **một** kết quả nghiệp vụ cuối.

## 12. Thiết kế test matrix không trùng lặp vô ích

Một ma trận rút gọn có thể làm điểm xuất phát cho bài tập:

| ID | Mục tiêu | Tầng ưu tiên | Assertion cốt lõi |
|---|---|---|---|
| F01 | State đầu và draft | Flow engine | `contact`, draft không null |
| F02 | Next/Back giữ dữ liệu | Flow engine | `review → contact`, dữ liệu không reset |
| F03 | Validation email | Flow engine | Ở lại `contact`, có lỗi của `email` |
| F04 | Confirm gọi service | Flow engine | Đúng action và số lần gọi |
| F05 | Subflow trả kết quả | Flow engine | Mapping output/transition về cha đúng |
| H01 | Mở flow qua endpoint | HTTP | Đúng status/view/form |
| H02 | POST form hợp lệ | HTTP | Đúng field, event, session, execution URL |
| H03 | Email sai hiển thị lỗi | HTTP | Có lỗi cạnh field, giữ giá trị khác |
| H04 | Back/Cancel | HTTP | Form event đúng, không bị validation cản |
| H05 | CSRF và quyền | HTTP | Thiếu token/không có quyền bị chặn |
| H06 | Session/key hết hạn | HTTP | Phản hồi có kiểm soát theo contract |
| H07 | Hai execution trong session | HTTP | Dữ liệu không lẫn giữa hai flow |
| H08 | Confirm và retry | HTTP + database | Không tạo dữ liệu trùng |
| B01 | AJAX/back/refresh thực tế | Browser (nếu cần) | UI/JS và lịch sử trang làm việc đúng |

Ma trận trên là **ví dụ thiết kế**, không phải yêu cầu phải có đúng số lượng test cho mọi ứng dụng. Bổ sung ca theo các transition, guard, side effect và rủi ro thực sự có trong flow của dự án.

### Quy tắc đặt tên dễ chẩn đoán

Tên test nên nêu **đầu vào – hành động – kỳ vọng**, chẳng hạn:

~~~text
givenValidContact_whenNext_thenReviewReceivesDraft
givenMissingEmail_whenNext_thenStayOnContactWithFieldError
givenReview_whenBack_thenContactKeepsPreviousValues
givenExpiredExecutionKey_whenPost_thenShowSessionExpiredPage
givenSubmittedRegistration_whenConfirmAgain_thenNoDuplicateRecord
~~~

Khi một test fail, tên và assertion cần chỉ rõ phần nào của contract bị phá vỡ.

## 13. Bắt bệnh khi một tầng PASS còn tầng kia FAIL

**Flow test PASS, HTTP test nhận 404:** kiểm tra `FlowHandlerMapping`, flow registry, URL và thứ tự handler mapping. Đây thường là lỗi cấu hình MVC.

**Flow test PASS, HTTP test vẫn ở state cũ:** kiểm tra form action URL, flow execution key, tên event parameter và dữ liệu binding. Có thể POST không thực sự phát event `next`, hoặc validation không cho chuyển state.

**Flow test PASS, HTTP test hiển thị 500:** kiểm tra view resolver, template path, model attributes và lỗi render; flow test thường không dựng HTML.

**Flow test PASS, HTTP test bị 403:** kiểm tra filter chain, authentication/authorization và CSRF; một lần signalEvent trực tiếp không đi qua security filter.

**HTTP test PASS nhưng flow test báo sai transition:** kiểm tra xem HTTP test chỉ assert status 200 hay thật sự assert state/ngữ cảnh hiển thị. Một page 200 không đủ chứng minh người dùng đã đi đúng bước.

**HTTP test không tái hiện được lỗi multi-tab:** có thể test đã vô tình dùng hai session khác nhau. Muốn kiểm tra hai execution trong cùng session, cần giữ một session nhưng bắt đầu hai flow riêng.

**Test lúc PASS lúc FAIL:** kiểm tra snapshot execution key bị dùng lại, mock chưa reset, dữ liệu trùng trong DB, thời gian hệ thống hoặc test chạy song song chia sẻ state. Không nên “sửa” bằng cách sleep cố định; hãy kiểm tra điều kiện đồng bộ và isolation.

## 14. Thực hành: đối chiếu ba đường đi

Hãy dùng quy trình đăng ký ở phần 2, bổ sung validation email và service lưu đơn. Viết hai nhóm test song song.

**Nhóm A – Flow engine:**

1. Bắt đầu flow, kiểm tra state `contact` và draft tồn tại.
2. Điền model hợp lệ, phát `next`; kiểm tra state `review`.
3. Phát `back`; kiểm tra `contact` và email đã nhập vẫn giữ.
4. Với input sai, kiểm tra validator tạo lỗi gắn field `email`.
5. Phát `confirm`; kiểm tra service stub được gọi đúng một lần khi điều kiện hợp lệ.

**Nhóm B – HTTP:**

1. GET URL của flow; kiểm tra form và lưu lại session.
2. Trích form action/execution URL từ HTML.
3. POST event `next` và dữ liệu hợp lệ, gửi kèm session và CSRF nếu cần; kiểm tra trang Review.
4. Nhập email không hợp lệ, kiểm tra nội dung lỗi cạnh trường và dữ liệu khác được giữ.
5. Thử `back` và `cancel` qua đúng tên button thực tế.
6. Mở hai flow execution bằng cùng session, điền hai email khác nhau; kiểm tra không bị ghi đè.
7. Gửi request với execution key hết hạn/không tồn tại; assert phản hồi theo chính sách ứng dụng.

Sau đó, hãy cố ý đổi tên button của form từ `_eventId_next` thành `_eventId_go` mà không sửa XML. Dự đoán: **flow test gọi `signalEvent("next")` vẫn có thể PASS; HTTP test sẽ lộ ra việc request không phát đúng event**. Đây là ví dụ điển hình cho giá trị của việc phối hợp hai tầng kiểm thử.

### Câu hỏi tự đánh giá

**1. Nếu test gọi `signalEvent("next")` và chuyển đúng state, điều đó có chứng minh JSP gửi đúng event parameter không?** Không. Ta chưa chạy form hay controller HTTP.

**2. Nếu MockMvc trả 200, điều đó có chứng minh flow chuyển đúng state không?** Không. Cần kiểm tra view/model thực tế hoặc dấu hiệu trạng thái phù hợp, và theo redirect nếu có.

**3. Tại sao không hardcode `execution=e1s1` trong test?** Execution key do framework/repository phát hành và có thể thay đổi theo request, snapshot hoặc cấu hình.

**4. MockMvc có kiểm tra JavaScript và nút Back của trình duyệt không?** Không. Với hành vi phụ thuộc trình duyệt, cần browser test.

**5. Nếu HTTP test dùng mock service, nó có chứng minh dữ liệu đã commit vào DB không?** Không. Cần test service/persistence thật hoặc integration test với database phù hợp.

**6. Tại sao phải test hai execution trong cùng session?** Vì chúng có thể chia sẻ session nhưng phải giữ dữ liệu theo từng execution; lỗi ghi đè có thể bị bỏ sót nếu mỗi test dùng một session riêng.

## 15. Checklist trước khi coi đường đi nhiều bước đã được kiểm tra đủ

- [ ] Flow test bao phủ state đầu, transition, guard, validation, Back/Cancel và nhánh kết thúc.
- [ ] Stub/mock service được kiểm tra về tham số, số lần gọi và side effect mong đợi.
- [ ] HTTP test đi qua đúng endpoint Spring MVC và view resolver.
- [ ] Test POST dùng form action hoặc execution key lấy từ response thực tế.
- [ ] Giữ session đúng giữa các request của cùng execution.
- [ ] Form binding được test qua request parameters, không chỉ gán trực tiếp draft.
- [ ] Test có assertion về HTML/form/error, không chỉ trạng thái HTTP.
- [ ] Security filter chain và CSRF được nạp khi nằm trong phạm vi kiểm thử.
- [ ] Có ca lỗi session/key, lưu thất bại, request lặp và hai execution song song khi nghiệp vụ cần.
- [ ] Có kiểm thử database riêng nếu cần chứng minh transaction và chống dữ liệu trùng.
- [ ] Các trường hợp phụ thuộc browser/JavaScript được đưa sang test end-to-end thích hợp.

**Ghi nhớ:** Kiểm thử **bộ máy flow** xác nhận logic hành trình được mô hình hóa đúng; kiểm thử **qua HTTP** xác nhận người dùng thực sự có thể đi theo hành trình ấy thông qua Spring MVC, form, session và bảo mật. Hai tầng bổ sung cho nhau. Đối chiếu cùng một hành vi ở đúng ranh giới giúp phát hiện cả lỗi trong flow definition lẫn lỗi tích hợp thường bị che khuất sau những test chuyển trạng thái thành công.

