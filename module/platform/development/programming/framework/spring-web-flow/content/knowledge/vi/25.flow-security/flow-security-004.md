# Gắn SecurityFlowExecutionListener vào FlowExecutor

> **Chương:** Bảo vệ flow  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Cấu hình `SecurityFlowExecutionListener` để Spring Web Flow thực thi ràng buộc bảo mật được khai báo trên flow/state; phân biệt xác thực HTTP với kiểm tra quyền khi chạy flow; phối hợp Spring Security, Spring MVC, form binding, session, transaction và kiểm thử các tình huống truy cập trái phép.

## 1. Bài toán: URL đã được bảo vệ, vì sao flow vẫn cần bảo vệ?

Một ứng dụng quản lý đặt lịch dùng Spring Web Flow để xây dựng hành trình:

~~~text
chooseSlot → contact → review → submitBooking → completed
                    ↘ cancel → cancelled
~~~

Ứng dụng yêu cầu:

- Chỉ người dùng đã đăng nhập và có quyền `ROLE_CUSTOMER` mới thực hiện flow đặt lịch.
- Một flow quản trị riêng chỉ dành cho `ROLE_SUPPORT`.
- Khi người dùng mất quyền giữa hai HTTP request, thao tác tiếp theo không được tự động vượt qua kiểm tra.
- Dù client tự gửi event `confirm` hoặc dùng execution key cũ, service không được tạo booking trái phép.

Spring Security có thể bảo vệ request HTTP theo URL. Tuy nhiên, Spring Web Flow còn mang một **máy trạng thái** riêng gồm flow execution, view-state, event, transition và subflow. Một endpoint flow có thể phục vụ nhiều state; chỉ so khớp URL thường **không mô tả hết quyền dành cho từng state**.

**`SecurityFlowExecutionListener`** là điểm tích hợp giữa hệ thống quyền của Spring Security và **vòng đời thực thi flow** của Spring Web Flow. Khi được đăng ký đúng, listener hỗ trợ thực thi metadata bảo mật khai báo bằng `<secured>` tại các vị trí được phiên bản Web Flow hỗ trợ, chẳng hạn flow và state.

Nhưng cần phân định trách nhiệm ngay từ đầu:

| Tầng | Bảo vệ điều gì? | Ví dụ |
| --- | --- | --- |
| Spring Security filter chain | HTTP request, authentication, session, CSRF | Yêu cầu đăng nhập trước khi truy cập `/booking` |
| `SecurityFlowExecutionListener` | Metadata quyền trên flow/state trong Web Flow | Không cho người thiếu `ROLE_CUSTOMER` vào flow đặt lịch |
| Flow definition | Đường đi hợp lệ giữa state và event | `confirm` chỉ có transition từ `review` |
| Domain service | Quyền trên đối tượng, điều kiện nghiệp vụ, transaction | Không đặt lịch thay người khác; kiểm tra slot còn trống |
| Database | Bất biến bền vững và chống ghi trùng | Unique constraint, optimistic locking/idempotency |

Không tầng nào tự thay thế hoàn toàn tầng khác. **Gắn listener là một lớp thực thi chính sách của Web Flow**, không phải thao tác bật tất cả tính năng bảo mật chỉ bằng một bean.

## 2. SecurityFlowExecutionListener là gì?

Trong các phiên bản Spring Web Flow hỗ trợ tích hợp Spring Security truyền thống, class thường được sử dụng là:

~~~java
org.springframework.webflow.security.SecurityFlowExecutionListener
~~~

Nó là một listener của **flow execution**. Thay vì tự tạo booking, ghi database hay quyết định view đích, nó tham gia kiểm tra các ràng buộc bảo mật khi framework thực thi flow/state theo hợp đồng của phiên bản đang dùng.

Những khái niệm liên quan:

- **`FlowExecutor`:** đầu mối khởi tạo và tiếp tục flow execution.
- **`FlowExecutionListener`:** cơ chế nhận callback về lifecycle của execution.
- **`SecurityFlowExecutionListener`:** listener chuyên trách việc tích hợp kiểm tra quyền từ metadata `<secured>`.
- **`<secured>`:** thành phần XML khai báo những authority/role cần có đối với flow hoặc state.
- **Spring Security `Authentication`:** thông tin principal và các granted authority của người dùng hiện hành.

### 2.1. Listener không phải một action-state

Một action trong flow có thể tạo event:

~~~xml
<action-state id="submitBooking">
    <evaluate expression="bookingAction.submit(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Listener bảo mật không trả event `booked`, `slotUnavailable` hay `accessDenied` để flow tự điều hướng theo cùng cách. Khi kiểm tra quyền không đạt, nó can thiệp theo cơ chế bảo mật/exception handling tương ứng, **không có nghĩa `<transition on="error">` tự bắt được lỗi phân quyền**.

**Action giải quyết nghiệp vụ; listener bảo mật thực thi metadata truy cập.** Hai cơ chế có thể cùng có mặt trong một request nhưng không nên tráo vai trò.

## 3. Điều kiện trước khi cấu hình listener

Để cấu hình có ý nghĩa, ứng dụng cần:

1. Tích hợp Spring Web Flow với Spring MVC hoặc môi trường web có cơ chế khởi tạo/tiếp tục flow.
2. Có `FlowRegistry` đăng ký các flow definition.
3. Có `FlowExecutor` tham chiếu đúng registry.
4. Có Spring Security hoạt động trên các request flow tương ứng.
5. Có người dùng/principal với granted authority thực tế, ví dụ `ROLE_CUSTOMER`.
6. Dùng tổ hợp phiên bản **Spring Web Flow và Spring Security tương thích**.

**Quan trọng về phiên bản:** các ví dụ XML bên dưới minh họa cơ chế thường gặp ở Spring Web Flow 2.x. Phiên bản Spring Framework/Spring Security mới có thể có khác biệt API, package, namespace hoặc mức tương thích. Trước khi đưa lên production, kiểm tra class `SecurityFlowExecutionListener`, schema XSD, dependency và cách đăng ký listener đúng với phiên bản thực tế của ứng dụng; không giả định mọi phiên bản Spring Boot tự cấu hình sẵn listener này.

### 3.1. FlowExecutor và FlowRegistry là các thành phần khác nhau

`FlowRegistry` trả lời câu hỏi: “Flow ID nào tương ứng với flow definition nào?”

`FlowExecutor` trả lời câu hỏi: “Khởi động/tiếp tục một execution, nhận event và chuyển trạng thái như thế nào?”

Listener phải được nối vào **executor đang thực sự xử lý HTTP request**, không chỉ đăng ký bean rồi để đó.

~~~mermaid
flowchart TD
    U["HTTP request /booking"] --> F["Spring Security filter chain"]
    F --> M["Spring MVC FlowHandlerAdapter"]
    M --> E["FlowExecutor"]
    E --> R["FlowRegistry"]
    E --> L["SecurityFlowExecutionListener"]
    L --> S["Authentication / authorities từ Spring Security"]
    R --> X["booking-flow.xml có secured metadata"]
    E --> A["Action và transition của flow"]
    A --> D["Domain service"]
~~~

Sơ đồ cho thấy cơ chế quyền ở mức Web Flow và service tồn tại **song song**, không phải một bước thay thế toàn bộ các bước còn lại.

## 4. Bước 1: tạo Spring bean cho SecurityFlowExecutionListener

Trong cấu hình Spring XML, có thể khai báo bean:

~~~xml
<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener"/>
~~~

Về bản chất:

- `id` là tên để cấu hình executor tham chiếu.
- `class` là implementation listener của Web Flow.
- Bean được tạo bởi Spring container và phải nằm trong context mà cấu hình executor có thể nhìn thấy.

**Chỉ khai báo bean chưa đủ:** Spring không thể suy rằng mọi bean implement listener đều phải được gắn vào FlowExecutor. Ta cần bước đăng ký rõ ràng.

### 4.1. Dependency phải tương thích

Không nên tự nghĩ rằng chỉ có dependency `spring-security-web` là đủ. Cần xác định module Spring Web Flow chứa lớp security listener và các dependency liên quan của **phiên bản đang sử dụng**.

Nếu IDE báo không tìm thấy `org.springframework.webflow.security.SecurityFlowExecutionListener`, hãy kiểm tra dependency/version đúng thay vì tạo một class trùng tên để che lỗi. Bài này tập trung vào cấu hình và kiến trúc; việc chọn version cụ thể phải theo build hiện tại của dự án.

## 5. Bước 2: gắn listener vào đúng FlowExecutor

Một cấu hình điển hình với namespace `webflow`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/webflow-config
           http://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <!-- Ví dụ giả định bean flowRegistry đã được cấu hình ở nơi khác. -->
    <bean id="securityFlowExecutionListener"
          class="org.springframework.webflow.security.SecurityFlowExecutionListener"/>

    <webflow:flow-executor id="flowExecutor"
                           flow-registry="flowRegistry">
        <webflow:flow-execution-listeners>
            <webflow:listener ref="securityFlowExecutionListener"/>
        </webflow:flow-execution-listeners>
    </webflow:flow-executor>
</beans>
~~~

Ba điểm phải kiểm tra:

1. `ref="securityFlowExecutionListener"` trùng tên bean đã tạo.
2. `flow-registry="flowRegistry"` trỏ đến registry thực tế.
3. `flowExecutor` là **chính executor mà Spring MVC FlowHandlerAdapter đang sử dụng**.

Nếu có nhiều executor trong ứng dụng, đăng ký listener vào một executor không tự bảo vệ những flow do executor khác xử lý.

### 5.1. Sai lầm: chỉ tạo bean nhưng quên đăng ký

~~~xml
<!-- Chưa đủ để kích hoạt callback của Web Flow. -->
<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener"/>
~~~

Bean trên có thể được Spring khởi tạo bình thường, ứng dụng không báo lỗi cấu hình, nhưng nếu listener chưa được kết nối với executor, metadata `<secured>` có thể **không được thực thi theo ý định**.

**Hãy kiểm thử bằng một tài khoản thiếu quyền** chứ không chỉ xác nhận Spring context startup thành công.

### 5.2. Nếu dự án dùng cấu hình Java

Không nên tự suy ra rằng annotation `@Component` là đủ. Với cấu hình programmatic, cần dùng API tạo FlowExecutor/listener loader được **phiên bản Web Flow** cung cấp. Dù cấu hình bằng XML hay Java, mục tiêu kiểm thử phải giống nhau: executor xử lý request có listener bảo mật được đăng ký và nhận các callback tương ứng.

## 6. Bước 3: khai báo metadata <secured> trong flow

Listener cần một **chính sách** để kiểm tra. Một ví dụ đặt lịch cho khách hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="chooseSlot">

    <!-- Yêu cầu authority đối với flow đặt lịch. -->
    <secured attributes="ROLE_CUSTOMER"/>

    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="chooseSlot" view="booking/choose-slot" model="booking">
        <binder>
            <binding property="slotId" required="true"/>
        </binder>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="submitBooking" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="submitBooking">
        <evaluate expression="bookingAction.submit(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Trong ví dụ:

- `<secured attributes="ROLE_CUSTOMER"/>` là **metadata quyền của flow**, không phải nút điều hướng.
- `<view-state>` nhận dữ liệu và điều phối event qua transition.
- `<action-state>` gọi service sau khi người dùng xác nhận.
- Listener đã đăng ký tại executor thực thi việc kiểm tra quyền theo lifecycle/hợp đồng của phiên bản Web Flow.

**Không dùng việc tồn tại một event `confirm` làm bằng chứng người dùng có quyền đặt lịch.** Client có thể tự tạo request event; service vẫn phải kiểm tra authentication, quyền trên tài nguyên và các bất biến nghiệp vụ.

### 6.1. Authority phải khớp dữ liệu Spring Security

Trong ví dụ, `ROLE_CUSTOMER` được hiểu là **granted authority** mà người dùng cần có theo chính sách cấu hình. Hãy xác minh authentication thực sự có authority đó.

Không nhầm:

~~~text
Tên hiển thị của vai trò: "Khách hàng"
Authority trong Spring Security: "ROLE_CUSTOMER"
Metadata Web Flow: attributes="ROLE_CUSTOMER"
~~~

Đừng trông đợi listener tự dịch tên tiếng Việt hoặc tự thêm prefix `ROLE_` trong mọi cấu hình. Một số cách viết `hasRole("CUSTOMER")` trong Spring Security có quy tắc prefix riêng; metadata `<secured attributes="...">` không nhất thiết dùng cùng cú pháp SpEL `hasRole`. Kiểm tra đúng cơ chế authorization của bộ phiên bản đang chạy.

## 7. Bảo vệ state riêng lẻ

Có những flow chỉ yêu cầu quyền ở một bước nhạy cảm, hoặc yêu cầu quyền bổ sung cho một số state. Ví dụ một flow nội bộ cho đội hỗ trợ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="searchBooking" view="support/search">
        <secured attributes="ROLE_SUPPORT"/>
        <transition on="next" to="inspectBooking"/>
    </view-state>

    <view-state id="inspectBooking" view="support/inspect">
        <secured attributes="ROLE_SUPPORT"/>
        <transition on="close" to="finished"/>
    </view-state>

    <end-state id="finished" view="support/done"/>
</flow>
~~~

Ví dụ minh họa metadata bảo mật ở **state**. Nếu toàn bộ flow thuộc quyền `ROLE_SUPPORT`, khai báo ở cấp **flow** thường dễ kiểm toán hơn. Không nên chỉ bảo vệ một state trong khi những state khác của cùng flow vẫn có thể hiển thị dữ liệu nhạy cảm.

### 7.1. Flow-level và state-level kết hợp ra sao?

Nếu vừa khai báo metadata ở flow, vừa khai báo ở một state, cần biết **chính sách quyền nào đang được kiểm tra tại mỗi mốc** và cách framework kết hợp chúng. Không nên tự giả định role ở state sẽ “ghi đè” toàn bộ role ở flow, hoặc ngược lại, khi chưa xác minh phiên bản.

Một hướng rõ ràng:

- Flow khách hàng: yêu cầu `ROLE_CUSTOMER` cho toàn bộ hành trình.
- Flow hỗ trợ: yêu cầu `ROLE_SUPPORT` cho toàn bộ hành trình.
- Các thao tác cần quyền chi tiết theo booking ID: **service** kiểm tra quyền đối tượng ở thời điểm đọc/ghi.

Nếu cần một state chỉ cho quản trị viên, hãy mô hình hóa policy đó và test cả **trường hợp người dùng có role flow nhưng thiếu role state**.

## 8. SecurityFlowExecutionListener kiểm tra ở thời điểm nào?

Listener hoạt động qua vòng đời flow execution, không phải sau mỗi dòng Java trong service. Những điểm kiểm tra liên quan metadata flow/state thường gắn với mốc bắt đầu flow session và việc vào state theo callback contract.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant SEC as Spring Security
    participant MVC as Spring MVC
    participant FE as FlowExecutor
    participant L as SecurityFlowExecutionListener
    participant S as BookingService

    U->>B: Mở /booking
    B->>SEC: GET /booking
    SEC->>SEC: Xác thực / kiểm tra HTTP
    SEC->>MVC: Chuyển request hợp lệ
    MVC->>FE: start booking flow
    FE->>L: Lifecycle callback theo API
    L->>SEC: Kiểm tra Authentication / authorities
    SEC-->>L: Có ROLE_CUSTOMER
    FE-->>B: Render chooseSlot

    U->>B: Nhấn Confirm ở review
    B->>SEC: POST event=confirm + execution key + CSRF
    SEC->>MVC: Request hợp lệ
    MVC->>FE: resume execution
    FE->>L: Lifecycle callback nếu phát sinh
    FE->>S: Gọi action/service nghiệp vụ
    S->>S: Kiểm tra lại quyền và điều kiện
    S-->>FE: Kết quả nghiệp vụ
    FE-->>B: View/redirect theo transition
~~~

Sơ đồ thể hiện **các lớp trách nhiệm**, không cam kết thứ tự từng callback trong một phiên bản cụ thể. Để biết chính xác listener kiểm tra flow/state ở thời điểm nào, cần đối chiếu API của thư viện và viết integration test với cấu hình thật.

### 8.1. Không suy ra listener kiểm tra lại mọi service invocation

Một flow có thể đứng ở `review` vài phút. Trong thời gian đó, quyền người dùng bị thu hồi hoặc session thay đổi. Nếu request sau tiếp tục execution tại state đã được vào trước đó, đừng suy rằng mọi callback vào state sẽ chắc chắn chạy lại **trước mọi action ghi**.

Vì vậy, ở `BookingService.reserveOnce(...)` phải có kiểm tra quyền hiện tại và quyền trên booking/slot, độc lập với việc listener đã cho vào flow trước đó.

**Listener là kiểm soát điều hướng ở tầng flow; service bảo vệ các thao tác có tác dụng bền vững.**

## 9. Kết nối với Spring Security filter chain và Spring MVC

Cấu hình listener **không tự bật authentication**. Spring Security cần được tích hợp vào HTTP layer để xử lý login, session, SecurityContext, CSRF và các rule request.

Một biểu đồ trách nhiệm:

~~~text
HTTP request
  -> Spring Security filter chain
       -> xác thực (Authentication)
       -> kiểm tra CSRF với request cần bảo vệ
       -> kiểm soát truy cập endpoint
  -> Spring MVC / FlowHandlerMapping, FlowHandlerAdapter
  -> FlowExecutor
       -> SecurityFlowExecutionListener kiểm tra metadata flow/state
       -> flow execution / state / event / transition
  -> Action
       -> Domain service kiểm tra quyền đối tượng và transaction
~~~

Ví dụ policy mong muốn, viết dưới dạng **pseudocode cấu hình** để tránh phụ thuộc DSL của một phiên bản Spring Security:

~~~text
permit GET /login và static resources
require authenticated for /booking/**
require ROLE_SUPPORT for /support/**
enable CSRF protection for form POST
configure login/session/exception handling
~~~

Đây chưa phải mã cấu hình security có thể dán vào dự án. Quy tắc path phải khớp **endpoint thực tế của FlowHandlerMapping**, không nhất thiết trùng với tên thư mục chứa XML flow.

### 9.1. Vì sao bảo vệ URL thôi chưa đủ?

Giả sử `/booking` là một URL duy nhất cho cả `chooseSlot`, `review` và `submitBooking`. Một URL rule có thể yêu cầu người dùng đăng nhập, nhưng không diễn đạt rằng một state quản trị nào đó cần authority bổ sung.

Metadata `<secured>` và listener giúp kiểm tra **đơn vị flow/state**. Nhưng việc truy cập một tài nguyên cụ thể, chẳng hạn “khách A có được xem booking số 42 hay không”, cần kiểm tra tại **service** hoặc policy domain với ID và principal thực tế.

## 10. Khi không có quyền, hệ thống phải phản hồi thế nào?

Các tình huống cần phân biệt:

| Tình huống | Cách hiểu | Phản hồi mục tiêu |
| --- | --- | --- |
| Chưa đăng nhập truy cập flow yêu cầu role | Authentication chưa có hoặc không hợp lệ | Chuyển sang login theo chính sách filter/entry point |
| Đã đăng nhập nhưng thiếu `ROLE_CUSTOMER` | Không đủ authority cho flow | Từ chối truy cập; thông báo quyền phù hợp |
| Có quyền flow nhưng không có quyền trên booking ID | Từ chối ở service/policy | Không để lộ dữ liệu hoặc thực hiện thay đổi |
| CSRF token thiếu/sai trên POST | Request không qua được CSRF filter | Từ chối request trước hoặc ở HTTP layer |
| Execution key hết hạn | Lỗi vòng đời execution, không nhất thiết lỗi role | Thông báo không thể tiếp tục, hướng dẫn bắt đầu lại |
| Session bị logout giữa chừng | Authentication thay đổi | Yêu cầu xác thực lại, không tiếp tục tác vụ ghi tùy tiện |

**Đừng cố định mọi trường hợp thành HTTP 401 hoặc 403** mà không kiểm tra integration. Hệ thống Spring Security và handler có thể redirect login, trả 401/403 hoặc đưa tới trang lỗi tùy kiểu request, exception handling và cấu hình.

### 10.1. Không biến access denied thành outcome nghiệp vụ

Đây là một anti-pattern:

~~~java
try {
    bookingService.reserveOnce(draft);
    return new Event(this, "booked");
} catch (Exception ex) {
    return new Event(this, "slotUnavailable");
}
~~~

Nếu `reserveOnce` ném exception vì thiếu quyền, service hỏng hoặc bug, action sẽ nói dối rằng slot hết chỗ. Đặc biệt, **không bắt exception bảo mật rồi phát event `success` hoặc `retry`**.

Thay vào đó, service nên trả outcome nghiệp vụ khi thực sự kiểm tra được điều kiện (như `SLOT_UNAVAILABLE`). Lỗi security và lỗi kỹ thuật đi theo cơ chế xử lý thích hợp, với log không lộ dữ liệu nhạy cảm.

## 11. Sự khác biệt giữa <secured> và event/transition

Spring Web Flow vẫn cần định nghĩa đường đi:

~~~xml
<view-state id="review" view="booking/review">
    <transition on="edit" to="chooseSlot" bind="false"/>
    <transition on="confirm" to="submitBooking" bind="false"/>
</view-state>
~~~

Metadata:

~~~xml
<secured attributes="ROLE_CUSTOMER"/>
~~~

không tự:

- Tạo nút Submit.
- Khai báo transition cho event `confirm`.
- Validate form hoặc bind giá trị `slotId`.
- Chống CSRF trên POST.
- Kiểm tra slot còn trống.
- Bảo đảm booking chỉ được tạo một lần.

**Security metadata quyết định ai được phép vào phần được bảo vệ; flow definition quyết định đường điều hướng; service quyết định một lệnh ghi có hợp lệ và an toàn hay không.**

### 11.1. Event từ client không đáng tin

Người dùng có thể sửa `_eventId=confirm` trong HTTP request. Nếu flow đang ở `chooseSlot` và không có transition `confirm`, request không nên tự đi thẳng tới action `submitBooking`.

Nhưng dù luồng điều hướng chặn được event sai, một request hợp lệ từ `review` vẫn cần được service kiểm tra quyền và điều kiện nghiệp vụ. Bảo vệ bằng flow không phải cơ chế chống giả mạo event theo nghĩa mã hóa.

## 12. Session, execution key và snapshot cũ

Một flow execution có thể tạm dừng giữa các HTTP request. Trình duyệt giữ execution key do Web Flow cấp để tiếp tục. Tùy repository, người dùng có thể Back/Forward về trang cũ hoặc gửi lại form chứa snapshot trước đó.

~~~mermaid
flowchart TD
    A["Đăng nhập, bắt đầu flow"] --> B["Snapshot: chooseSlot"]
    B --> C["Snapshot: review"]
    C --> D["Logout hoặc quyền bị thu hồi"]
    D --> E["Browser Back: trang cũ vẫn hiện"]
    E --> F["POST confirm với execution key cũ"]
    F --> G["Spring Security kiểm tra request/session"]
    G --> H["Web Flow khôi phục execution nếu còn hợp lệ"]
    H --> I["Listener kiểm tra metadata ở mốc phù hợp"]
    I --> J["Service kiểm tra lại quyền trước ghi"]
~~~

Một trang cũ hiển thị trên browser **không chứng minh quyền vẫn còn hiệu lực**. Browser cache có thể hiển thị HTML mà không gửi request đến server; khi submit mới phải thực hiện kiểm tra hiện hành.

### 12.1. Execution key không phải quyền truy cập

Không coi execution key là bearer token đủ để gọi service, cũng không dùng nó như bằng chứng ownership đối với booking. Một người có được execution key vẫn không tự động có quyền đọc hoặc sửa tài nguyên nghiệp vụ.

Nên bảo vệ:

- Authentication và session còn hiệu lực.
- CSRF cho request thay đổi trạng thái.
- Metadata flow/state nếu dùng.
- Quyền trên ID tài nguyên ở service.
- Idempotency của lệnh ghi.

### 12.2. Không mở transaction xuyên nhiều request

Người dùng có thể dừng ở màn hình review nhiều phút. Không mở một transaction database từ `chooseSlot` rồi giữ đến `completed`. Chỉ mở transaction ngắn ở service khi thực hiện nghiệp vụ, và kiểm tra quyền ở thời điểm đó.

## 13. Subflow và quyền truy cập

Flow đặt lịch có thể gọi subflow `verifyContact`:

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.booking.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="chooseSlot"/>
</subflow-state>
~~~

Flow con có vòng đời session riêng trong conversation và có thể có metadata `<secured>`. Cần kiểm tra:

1. Flow cha có yêu cầu role phù hợp không?
2. Flow con có metadata quyền độc lập hoặc bổ sung không?
3. Listener đã đăng ký với executor xử lý cả flow cha/con chưa?
4. Khi flow con kết thúc, flow cha có kiểm tra lại điều kiện nhạy cảm trước khi ghi không?

**Đừng cho rằng quyền của flow cha tự thay thế mọi quyền ở flow con hoặc ngược lại**. Nếu subflow được dùng lại trong nhiều quy trình, hãy xác định hợp đồng và quyền của nó một cách tường minh.

### 13.1. Kết quả verified không thay thế authorization

Flow con xác minh số điện thoại có thể trả outcome `verified`, nhưng điều đó không chứng minh người dùng có quyền tạo booking cho một khách hàng khác. Phân biệt:

- **Xác minh liên hệ:** mã OTP đúng.
- **Xác thực danh tính:** principal được Spring Security xác lập.
- **Phân quyền:** principal được phép tạo/sửa booking đang yêu cầu.

Một outcome của subflow chỉ giải quyết chính vấn đề nó được thiết kế để kiểm tra.

## 14. Quyền trên đối tượng nghiệp vụ: vì sao listener không đủ?

Giả sử cả An và Bình đều có `ROLE_CUSTOMER`. An đoán được ID lịch của Bình và gửi một request sửa lịch.

Listener có thể xác nhận An là customer, nhưng không thể suy ra An sở hữu booking của Bình chỉ từ metadata `ROLE_CUSTOMER`.

Service cần kiểm tra quyền dựa trên principal và tài nguyên:

~~~java
// Ví dụ phương thức nghiệp vụ; các kiểu là của ứng dụng.
@Transactional
public BookingResult changeSlot(
        String bookingId, String newSlotId, String currentUserId) {

    Booking booking = bookingRepository.findById(bookingId)
            .orElseThrow(() -> new ResourceNotFoundException());

    if (!booking.getOwnerId().equals(currentUserId)) {
        throw new AccessDeniedException("Not allowed");
    }

    // Kiểm tra slot, trạng thái booking, ràng buộc phiên bản/transaction.
    // Chỉ thay đổi tài nguyên sau khi quyền được xác minh.
    return bookingDomainService.changeSlot(booking, newSlotId);
}
~~~

Đoạn code **minh họa về ranh giới kiểm tra quyền**, không phải implementation đầy đủ. Các class `Booking`, repository, exception và service là của ứng dụng. Cần nhập đúng `AccessDeniedException` theo phiên bản Spring Security dùng; cũng phải quyết định cách xác định `currentUserId` an toàn từ security principal **phía server**, không tin một hidden field `ownerId` do browser gửi.

### 14.1. Dùng method security khi phù hợp

Một lựa chọn khác là bảo vệ service bằng cơ chế method security tương thích phiên bản Spring Security, ví dụ `@PreAuthorize` khi dự án đã bật method security và có policy phù hợp.

Nhưng annotation chỉ có tác dụng nếu được Spring cấu hình đúng, method được gọi qua proxy/interceptor phù hợp và kiểm tra resource-level thực sự có hiệu lực. Việc bật listener Web Flow **không tự bật method security**.

## 15. Đăng ký nhiều listener vào cùng executor

Ứng dụng có thể cần cả bảo mật lẫn quan sát:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="securityFlowExecutionListener"/>
        <webflow:listener ref="flowMetricsListener"/>
    </webflow:flow-execution-listeners>
</webflow:flow-executor>
~~~

`flowMetricsListener` là listener quan sát được ứng dụng tự tạo. Nó có thể đo số lần vào state, lỗi hoặc thời gian flow, nhưng không nên tự sửa authority, gọi service ghi hoặc quyết định outcome của action.

### 15.1. Không dựa vào thứ tự listener để bảo vệ transaction

Nếu một metrics listener ghi log rồi security listener từ chối, log vẫn có thể ghi nhận mốc callback. Điều đó không phải lỗi security. Ngược lại, không nên thiết kế một nghiệp vụ “chạy listener A trước listener B thì mới được ghi database”.

Thứ tự callback và thứ tự listener phụ thuộc contract/implementation của phiên bản Web Flow; bất biến nghiệp vụ phải nằm trong flow action/service/security boundary rõ ràng.

### 15.2. Listener bị lỗi phải được kiểm thử

Nếu listener metrics ném exception hoặc kết nối metrics backend bị gián đoạn, flow có thể bị ảnh hưởng. Nên thiết kế listener quan sát không quan trọng sao cho lỗi phụ trợ không gây mất khả năng phục vụ, theo chính sách vận hành. **Không được làm yếu security listener chỉ để “tránh lỗi”**.

## 16. Ma trận kiểm thử quyền của flow

Hãy dùng ít nhất bốn principal:

- `anonymous`: chưa đăng nhập.
- `customer`: có `ROLE_CUSTOMER`.
- `support`: có `ROLE_SUPPORT`.
- `other`: đăng nhập nhưng không có authority nào trong hai role trên.

Đối với flow khách hàng có `<secured attributes="ROLE_CUSTOMER"/>`:

| Người dùng | Bắt đầu booking flow | Mong đợi |
| --- | --- | --- |
| Anonymous | GET `/booking` | Bị yêu cầu đăng nhập hoặc từ chối theo HTTP security |
| Customer | GET `/booking` | Được vào `chooseSlot` |
| Support-only | GET `/booking` | Bị từ chối nếu không có `ROLE_CUSTOMER` |
| Other | GET `/booking` | Bị từ chối |

Đối với flow hỗ trợ có `ROLE_SUPPORT`, phải kiểm tra **support được phép** và **customer không được phép**.

### 16.1. Test listener đã thực sự được gắn

Không chỉ test:

~~~text
Spring context starts successfully
~~~

Mà phải test:

~~~text
Given a flow with secured ROLE_CUSTOMER
And a Spring Security principal without ROLE_CUSTOMER
When FlowExecutor starts that flow
Then access is denied by the configured integration
And the protected view/action is not executed
~~~

**Pseudocode trên mô tả kết quả**, không phải API Java chạy nguyên văn. Dùng test infrastructure của Web Flow, context bảo mật và servlet integration tương ứng phiên bản.

Nếu test thiếu quyền vẫn vào được flow, kiểm tra wiring listener, flow registry, metadata `<secured>` và Spring Security Authentication; đừng vội chỉ chỉnh URL matcher.

### 16.2. Test riêng việc vào state được bảo vệ

~~~text
Given a flow with a protected support state
And an authenticated principal missing ROLE_SUPPORT
When a legal transition attempts to enter the protected state
Then state access is denied
And no business action requiring support privilege occurs
~~~

Đồng thời test account có quyền thực sự vào state được. Nếu chỉ test từ chối, cấu hình quá chặt khiến mọi người đều bị từ chối cũng có thể lọt qua.

## 17. Kiểm thử session, CSRF và request cũ

Phải kiểm thử ngoài “đúng role khi bắt đầu”.

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Form POST thiếu/sai CSRF token | Bị từ chối theo chính sách Spring Security |
| Đã vào flow rồi logout | Request tiếp theo không thực thi thao tác ghi trái phép |
| Role bị thu hồi giữa hai bước | Service kiểm tra quyền mới nhất tại thời điểm ghi |
| Browser Back hiển thị trang cache | UI cũ có thể hiện; server vẫn kiểm tra hiện hành khi submit |
| Execution key hết hạn | Không tự sinh execution mới rồi bỏ qua bước bảo mật |
| Hai tab cùng execution key | Không cho bypass quyền hoặc tạo booking trùng |
| Người dùng sửa hidden field `ownerId` | Không đổi được chủ sở hữu trên service |
| `_eventId=confirm` gửi ở state sai | Không đi thẳng tới action ghi |
| Request submit lặp sau timeout | Service idempotent, tối đa một booking cho một ý định |
| Flow cha gọi subflow bảo vệ riêng | Metadata của flow con được thực thi đúng |

### 17.1. Phân biệt kiểm thử flow và kiểm thử service

**Flow/security integration test** xác minh listener chặn đúng các flow/state khi principal không đủ quyền.

**Service integration test** xác minh một khách hàng không thể sửa booking người khác dù cùng `ROLE_CUSTOMER`, và không thể ghi trùng khi request bị gửi lại.

Hai bộ test cần thiết vì listener không biết toàn bộ điều kiện nghiệp vụ trên từng booking ID.

### 17.2. Cẩn thận với test không đi qua servlet filter

Một unit/flow test gọi `FlowExecutor` trực tiếp có thể bỏ qua Spring Security filter chain. Khi đó CSRF, redirect login, session policy hoặc request matcher không được kiểm tra như trong browser thật.

Vì vậy cần thêm **MVC/browser integration test** để xác minh authentication, CSRF và phản hồi HTTP trong môi trường gần production.

## 18. Chẩn đoán lỗi cấu hình thường gặp

### 18.1. Bean listener tồn tại nhưng người thiếu quyền vẫn vào flow

Kiểm tra:

1. Listener đã nằm trong `<flow-execution-listeners>` của **executor đúng** chưa?
2. Spring MVC FlowHandlerAdapter có dùng executor đó không?
3. Flow XML đã khai báo `<secured>` ở đúng vị trí và đúng namespace/schema chưa?
4. `attributes` có khớp granted authority của người dùng không?
5. Ứng dụng có thực sự dùng Spring Security authentication trong request không?
6. Có flow definition khác cùng tên nhưng được registry nạp vào không?

### 18.2. Mọi người đều bị từ chối

Nguyên nhân thường là role không khớp (ví dụ có `CUSTOMER` nhưng metadata đòi `ROLE_CUSTOMER`), SecurityContext không được thiết lập, hoặc test không tạo authentication đúng.

Không sửa bằng cách bỏ listener hoặc đổi `<secured>` thành rỗng. Hãy đối chiếu authority và chính sách.

### 18.3. Không tìm thấy class listener hoặc XSD không hợp lệ

Có thể do dependency chưa chứa integration cần thiết, phiên bản Web Flow không tương thích với Spring Security đang dùng, hoặc cấu hình namespace không đúng. Cần kiểm tra dependency tree/version và tài liệu tương ứng, **không** dùng ví dụ XML 2.x làm bảo đảm mọi tổ hợp hiện đại hoạt động nguyên văn.

### 18.4. Login redirect lặp

Kiểm tra URL login có được permit không, session/cookie có giữ authentication không, có phân biệt login thành công nhưng thiếu authority hay không, và endpoint flow có đang bị matcher sai không.

### 18.5. Access denied bị render thành lỗi nghiệp vụ

Nếu action bắt mọi exception rồi trả `slotUnavailable`, người dùng sẽ nhận thông báo sai. Phân loại riêng exception bảo mật, lỗi kỹ thuật và kết quả nghiệp vụ.

## 19. Checklist triển khai an toàn

Trước khi bàn giao flow cho nhóm kiểm thử, cần xác nhận:

1. Spring Security bảo vệ request HTTP theo endpoint đúng và CSRF được cấu hình.
2. `FlowExecutor` đang được MVC sử dụng đã đăng ký `SecurityFlowExecutionListener`.
3. Các flow/state nhạy cảm có `<secured>` đúng role/authority.
4. Có test chứng minh principal thiếu quyền bị từ chối, và principal đủ quyền được phép.
5. Có test riêng cho state được bảo vệ, kể cả đường đi qua subflow.
6. Có quy tắc xử lý authentication/logout/session hết hạn rõ ràng.
7. Service kiểm tra ownership và quyền tại thời điểm đọc/ghi.
8. Không tin event, form field, execution key hoặc URL từ client.
9. Thao tác ghi có transaction/idempotency, không trùng khi retry.
10. Log không chứa token, session, execution key hay dữ liệu cá nhân nhạy cảm không cần thiết.
11. Phiên bản Spring Web Flow và Spring Security tương thích, cấu hình listener khớp API/schema.
12. Đã test cả flow-level, service-level và HTTP/browser-level.

## 20. Bài thực hành: bảo vệ flow đặt lịch và flow hỗ trợ

Thiết kế hai flow:

**`customerBooking`**

~~~text
chooseSlot → review → submitBooking → completed
       ^                      |
       +---- slotUnavailable --+
~~~

**`supportBookingReview`**

~~~text
searchBooking → inspectBooking → finished
~~~

**Yêu cầu:**

1. Cấu hình `SecurityFlowExecutionListener` thành Spring bean và đăng ký vào `FlowExecutor` qua `<webflow:flow-execution-listeners>`.
2. Đặt `<secured attributes="ROLE_CUSTOMER"/>` cho `customerBooking` và `<secured attributes="ROLE_SUPPORT"/>` cho `supportBookingReview`.
3. Đảm bảo Spring MVC request đi qua Spring Security filter chain và sử dụng đúng executor.
4. Viết policy HTTP giả định: login được permit; hai endpoint flow yêu cầu authentication; form POST bảo vệ CSRF.
5. Tạo bốn test principal `anonymous`, `customer`, `support` và `other`; kiểm tra cả cho phép lẫn từ chối.
6. Mô phỏng khách hàng tự thay `bookingId` trong form để sửa lịch người khác; thêm kiểm tra quyền ở domain service.
7. Mô phỏng logout sau khi vào `review` rồi POST confirm từ trang cũ; bảo đảm không tạo booking trái phép.
8. Mô phỏng gửi hai POST confirm cùng request ID; database chỉ có một booking.
9. Mô phỏng flow cha gọi một subflow cần quyền đặc biệt; kiểm tra listener/metadata thực sự có tác dụng.
10. Ghi lại luồng kiểm soát ở cả ba tầng: HTTP filter, Web Flow listener, domain service.

**Bảng mong đợi tối thiểu:**

| Tài khoản | customerBooking | supportBookingReview |
| --- | --- | --- |
| Anonymous | Từ chối / login | Từ chối / login |
| Customer | Cho phép | Từ chối |
| Support-only | Từ chối | Cho phép |
| Other | Từ chối | Từ chối |

Nếu `ROLE_SUPPORT` cũng được cấp `ROLE_CUSTOMER` trong chính sách thực tế, hãy điều chỉnh test theo danh sách authority được cấp, không giả định các role luôn loại trừ lẫn nhau.

**Tiêu chí đạt:** không chỉ bean listener tồn tại; quyền phải được kiểm tra thật qua executor, metadata state/flow được thực thi, và các thao tác ghi vẫn được service bảo vệ khi client gửi request cũ hoặc giả mạo dữ liệu.

## 21. Tổng kết và câu hỏi ôn tập

Để tích hợp bảo mật ở mức Spring Web Flow, cần **tạo bean `SecurityFlowExecutionListener`, đăng ký nó trong `FlowExecutor` đang chạy và khai báo metadata `<secured>` ở flow/state phù hợp**. Spring Security tiếp tục chịu trách nhiệm authentication và CSRF ở HTTP layer; action/transition điều phối nghiệp vụ; domain service kiểm tra ownership, quyền, transaction và idempotency trước thao tác ghi.

Một flow có `<secured>` nhưng chưa gắn listener đúng **không phải bằng chứng hệ thống đã được bảo vệ**. Một listener hoạt động cũng không cho phép bỏ kiểm tra quyền tại service. Cách xác nhận đáng tin là test cả **người được phép** và **người bị từ chối**, cùng các request cũ, session hết hạn và thao tác gửi lặp.

**Câu hỏi tự kiểm tra:**

1. Vì sao tạo bean `SecurityFlowExecutionListener` chưa đủ để bảo vệ flow?
2. Listener phải được đăng ký vào thành phần nào của Spring Web Flow?
3. `<secured attributes="ROLE_CUSTOMER"/>` khác gì với transition `on="confirm"`?
4. Tại sao một khách hàng có `ROLE_CUSTOMER` vẫn không đương nhiên được sửa booking của khách hàng khác?
5. Nếu role bị thu hồi khi người dùng đã đứng ở `review`, service cần làm gì khi họ nhấn Confirm?
6. Vì sao không dùng execution key làm bằng chứng authentication hoặc idempotency key?
7. Test gọi `FlowExecutor` trực tiếp đã đủ chứng minh CSRF và redirect login hoạt động đúng chưa?
8. Nếu listener đã đăng ký nhưng principal thiếu quyền vẫn vào flow được, bạn sẽ kiểm tra những thành phần nào trước?
