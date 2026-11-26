# Phân biệt flow execution redirect, flow redirect và externalRedirect trong Spring Web Flow

Khi một hành trình đặt phòng kết thúc, ứng dụng có thể cần hiển thị lại bước hiện tại sau khi xử lý POST, chuyển người dùng sang flow thanh toán, hoặc đưa họ về trang danh sách đặt phòng trong Spring MVC. Cả ba tình huống đều có thể nhìn thấy như một lần trình duyệt điều hướng, nhưng **đích đến và vòng đời flow khác nhau**.

Spring Web Flow (SWF) có ba cơ chế cần phân biệt:

- **Flow execution redirect**: chuyển hướng tới URL của **execution đang chạy**, thường để thực hiện POST-REDIRECT-GET sau khi flow xử lý một event.
- **Flow redirect** (`flowRedirect:`): kết thúc flow hiện tại và khởi chạy **một flow definition khác** bằng execution mới, có thể truyền input.
- **External redirect** (`externalRedirect:`): chuyển trình duyệt tới URI của tài nguyên nằm ngoài flow, chẳng hạn Spring MVC controller, trang khác trong ứng dụng hoặc website bên ngoài.

Bài thuộc chương **URL và điều hướng** của module `SPRING_WEB_FLOW`. Ta sẽ xem từng cơ chế hoạt động ra sao, khi nào chọn loại nào, cách khai báo trong flow XML, cách truyền dữ liệu qua redirect, cách tích hợp Spring MVC và cách kiểm thử để tránh mất execution hoặc lộ dữ liệu.

## 1. So sánh nhanh ba cơ chế

| Cơ chế | Đích điều hướng | Flow hiện tại | Execution ở đích |
|---|---|---|---|
| **Flow execution redirect** | URL tiếp tục execution hiện tại, có flow execution key | Vẫn hoạt động | Tiếp tục cùng execution |
| **Flow redirect** (`flowRedirect:`) | URL khởi chạy flow ID khác | Kết thúc theo end-state phát redirect | Tạo execution mới cho flow đích |
| **External redirect** (`externalRedirect:`) | URI của tài nguyên bên ngoài flow | Nếu dùng ở end-state thì flow kết thúc | Không tự tạo execution Web Flow mới |

Có thể nhớ bằng ba câu hỏi:

1. **Còn đang ở cùng hành trình không?** Chọn flow execution redirect.
2. **Muốn chuyển sang một hành trình Web Flow khác?** Chọn `flowRedirect:`.
3. **Muốn rời Web Flow để tới controller, trang web hoặc hệ thống khác?** Chọn `externalRedirect:`.

~~~mermaid
flowchart TD
    A["Flow xử lý một request/event"] --> B{"Đích tiếp theo là gì?"}
    B -->|"Tiếp tục cùng execution"| C["Flow execution redirect"]
    C --> D["URL chứa execution key"]
    D --> E["Cùng flow execution được resume"]
    B -->|"Khởi chạy flow khác"| F["flowRedirect:targetFlow"]
    F --> G["Kết thúc flow hiện tại"]
    G --> H["Tạo execution mới cho targetFlow"]
    B -->|"Rời Web Flow"| I["externalRedirect:URI"]
    I --> J["Trình duyệt tới tài nguyên đích"]
~~~

Cả ba có thể tạo ra một phản hồi HTTP redirect ở tầng web, nhưng **không có cùng ngữ nghĩa flow**. Không nên chỉ nhìn thấy trình duyệt đổi URL rồi cho rằng mọi redirect đều giữ lại cùng trạng thái.

## 2. Flow execution redirect: tiếp tục đúng execution đang chạy

Flow execution redirect là cơ chế mặc định của SWF khi flow đi tới view-state và cần hiển thị view. Sau khi xử lý request/event, framework chuyển trình duyệt tới **URL riêng của execution hiện tại**, rồi mới render view ở request kế tiếp. Đây là mẫu **POST-REDIRECT-GET (PRG)**.

Ví dụ flow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="enterDetails" view="booking/details">
        <transition on="review" to="reviewBooking" />
    </view-state>

    <view-state id="reviewBooking" view="booking/review">
        <transition on="back" to="enterDetails" />
        <transition on="confirm" to="complete" />
    </view-state>

    <end-state id="complete" />
</flow>
~~~

Khi người dùng submit form ở `enterDetails`:

1. Trình duyệt gửi POST event `review`.
2. SWF xử lý event và chuyển state sang `reviewBooking`.
3. SWF yêu cầu client redirect tới URL execution hiện tại.
4. Trình duyệt gửi GET tới URL đó.
5. SWF khôi phục **cùng flow execution** và render `booking/review`.

Sơ đồ request:

~~~mermaid
sequenceDiagram
    participant Browser as Trình duyệt
    participant MVC as Spring MVC / FlowHandlerAdapter
    participant Executor as FlowExecutor
    participant Repo as FlowExecutionRepository
    Browser->>MVC: POST event=review + execution key
    MVC->>Executor: Resume execution
    Executor->>Repo: Khôi phục execution
    Repo-->>Executor: State và flow scope hiện tại
    Executor->>Executor: Transition sang reviewBooking
    Executor-->>MVC: Yêu cầu flow execution redirect
    MVC-->>Browser: Redirect tới execution URL
    Browser->>MVC: GET execution URL
    MVC->>Executor: Resume cùng execution
    Executor-->>MVC: Render review view
    MVC-->>Browser: HTML review
~~~

### 2.1. flowExecutionUrl trong view

SWF cung cấp biến EL `flowExecutionUrl` để view tạo URL tiếp tục execution hiện tại. Ví dụ JSP:

~~~jsp
<form method="post" action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_review">Xem lại</button>
</form>
~~~

Hoặc một liên kết phát event:

~~~jsp
<a href="${flowExecutionUrl}&_eventId=back">Quay lại</a>
~~~

Trong JSP, EL expression `flowExecutionUrl` được Web Flow cung cấp cho URL execution hiện tại. URL này chứa thông tin để SWF tìm đúng execution/snapshot. Hãy dùng URL do framework cung cấp, không tự ghép flow ID hoặc đoán execution key.

### 2.2. Vì sao flow execution redirect hữu ích?

- **Tránh gửi lại POST khi Refresh:** sau POST, trình duyệt đã được chuyển sang GET để render view.
- **Giảm cảnh báo gửi lại biểu mẫu:** Refresh thường tải lại view GET thay vì hỏi người dùng có gửi lại POST hay không.
- **Hỗ trợ Back/Forward:** execution URL cho biết continuation point của flow; repository có thể dùng snapshot để phục hồi trạng thái tương ứng.
- **Giữ nguyên flow scope:** dữ liệu của execution hiện tại được giữ qua request theo cơ chế repository.

PRG giảm khả năng người dùng vô tình gửi lại form khi refresh, nhưng **không thay thế idempotency**. Hai POST giống nhau vẫn có thể được gửi đồng thời hoặc gửi lại do mạng; thao tác thanh toán/đặt hàng vẫn cần kiểm soát trùng lặp ở service và database.

### 2.3. Redirect khi vẫn ở cùng view-state

SWF cũng có thể redirect sau một request mà flow vẫn ở cùng view-state, chẳng hạn validation thất bại hoặc paging. Với request HTTP thông thường, hành vi này giúp Refresh/Back không phát lại POST. Trong các request Ajax, hành vi redirect có thể khác để tránh tải lại toàn trang.

Nếu flow được nhúng trong một vùng trang và cập nhật bằng Ajax, có thể khởi chạy flow ở chế độ embedded bằng input `mode=embedded`:

~~~text
/booking?mode=embedded
~~~

Trong chế độ này, SWF không thực hiện flow execution redirect cho Ajax request theo cách mặc định của flow top-level. Client cần dùng Ajax và chỉ render phần giao diện cần cập nhật. Đây là lựa chọn dành cho flow embedded; không bật chỉ vì muốn bỏ qua PRG ở một form thông thường.

## 3. Flow redirect: kết thúc flow hiện tại và khởi chạy flow khác

`flowRedirect:` là view selector dùng để yêu cầu trình duyệt chuyển tới **một flow definition khác**. Đây là kiểu điều hướng dạng chuỗi: flow hiện tại hoàn thành một phần công việc, sau đó flow tiếp theo bắt đầu một execution độc lập.

Ví dụ: sau khi xác nhận thông tin đặt phòng, flow `booking` chuyển sang flow `payment` để thanh toán:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.BookingDraft" />

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="bookingComplete" />
    </view-state>

    <end-state id="bookingComplete"
               view="flowRedirect:payment?bookingId=#{flowScope.booking.id}" />
</flow>
~~~

Flow đích `payment` khai báo input tương ứng:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="bookingId" type="long" required="true" />

    <on-start>
        <evaluate expression="paymentService.createForBooking(bookingId)"
                  result="flowScope.payment" />
    </on-start>

    <view-state id="enterPayment" view="payment/enter" />
</flow>
~~~

Trong ví dụ:

- Flow `booking` kết thúc ở end-state `bookingComplete`.
- `flowRedirect:payment` chỉ định flow ID đích là `payment`.
- `bookingId=#{flowScope.booking.id}` truyền dữ liệu cần thiết để khởi chạy flow đích.
- Flow `payment` nhận giá trị đó qua input `bookingId` và tạo trạng thái riêng trong flow scope của execution mới.

Flow redirect không tiếp tục flow `booking` ở một state khác. Nó tạo **execution mới** cho flow `payment`; dữ liệu không tự động được chia sẻ như thể hai flow là một. Chỉ truyền các input cần thiết hoặc lưu dữ liệu nghiệp vụ bền vững ở service/database.

### 3.1. Truyền input sang flow đích

Các giá trị query trong URL khởi chạy flow có thể được xử lý như flow input theo cơ chế mặc định của Spring MVC FlowHandlerAdapter. Flow đích nên khai báo input rõ ràng:

~~~xml
<input name="bookingId" type="long" required="true" />
~~~

Nếu dùng custom `FlowHandler` hoặc custom `createExecutionInputMap(...)`, cách lấy input có thể được thay đổi. Vì vậy hãy kiểm tra hợp đồng input ở cả flow đích và FlowHandler đang dùng.

Không đưa toàn bộ object lớn vào query string. URL có thể xuất hiện trong browser history, access log, proxy log và referrer. Với dữ liệu nhạy cảm hoặc nhiều thuộc tính, chỉ truyền một ID không bí mật, sau đó flow đích tải dữ liệu từ service và kiểm tra quyền sở hữu.

### 3.2. Khi nào dùng flow redirect?

- Kết thúc wizard thông tin rồi chuyển sang wizard thanh toán.
- Hoàn tất đăng ký rồi khởi chạy flow xác minh bổ sung.
- Chuyển từ một flow top-level sang một hành trình độc lập khác.
- Bắt đầu một conversation mới với input được xác định rõ.

Nếu mục tiêu chỉ là gọi một subflow rồi quay về flow cha, hãy cân nhắc `subflow-state` và input/output mapping. Subflow chạy trong cùng flow execution stack và trả outcome về cha; `flowRedirect:` khởi chạy một flow độc lập thông qua redirect của trình duyệt.

## 4. External redirect: rời flow để tới một URI khác

`externalRedirect:` yêu cầu SWF chuyển trình duyệt tới một tài nguyên URI nằm ngoài flow hiện tại. “External” ở đây có nghĩa là **ngoài điều khiển của flow**, không nhất thiết là một website khác. Đích có thể là Spring MVC controller trong cùng ứng dụng, một servlet resource, một đường dẫn khác hoặc website bên ngoài.

Ví dụ flow kết thúc và chuyển người dùng tới trang tóm tắt đặt phòng của ứng dụng:

~~~xml
<end-state id="bookingComplete"
           view="externalRedirect:contextRelative:/booking/summary?bookingId=#{flowScope.booking.id}" />
~~~

Một số dạng URI được hỗ trợ:

| Prefix / URI | Ý nghĩa | Ví dụ |
|---|---|---|
| `servletRelative:` | Tương đối với servlet mapping hiện tại | `externalRedirect:servletRelative:/summary` |
| `contextRelative:` | Tương đối với web application context path | `externalRedirect:contextRelative:/booking/summary` |
| `serverRelative:` | Tương đối với server root | `externalRedirect:serverRelative:/help` |
| `http://` hoặc `https://` | URI đầy đủ | `externalRedirect:https://example.org/terms` |

Ví dụ chuyển tới website khác:

~~~xml
<end-state id="termsAccepted"
           view="externalRedirect:https://example.org/terms" />
~~~

Có thể dùng `externalRedirect:` trên `view-state` hoặc `end-state`. Nếu người dùng đã hoàn thành flow và không cần tiếp tục execution, nên đặt redirect ở `end-state` để kết thúc flow một cách rõ ràng.

### 4.1. External redirect tới Spring MVC controller

Một use case phổ biến là flow xử lý nghiệp vụ xong rồi chuyển sang controller hiển thị trang summary:

~~~xml
<end-state id="completed"
           view="externalRedirect:contextRelative:/orders/summary?orderId=#{flowScope.order.id}">
    <output name="orderId" value="flowScope.order.id" />
</end-state>
~~~

Nếu muốn controller đọc flow output từ Spring MVC flash scope, Spring Web Flow 2.4+ hỗ trợ `saveOutputToFlashScopeOnRedirect` trên `FlowHandlerAdapter`:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
    <property name="saveOutputToFlashScopeOnRedirect" value="true" />
</bean>
~~~

Khi bật cấu hình này, flow output có thể được đưa vào MVC flash scope trước internal redirect để controller đích đọc ở request tiếp theo. Chỉ bật khi controller thật sự cần output; tránh truyền dữ liệu nhạy cảm qua query string nếu flash scope là lựa chọn phù hợp hơn.

### 4.2. External redirect không phải cơ chế bảo mật

Nếu URL đích được tạo từ dữ liệu người dùng, không ghép trực tiếp `requestParameters.nextUrl` vào `externalRedirect:`. Một URL do client kiểm soát có thể đưa người dùng tới website giả mạo (open redirect).

Hãy dùng danh sách đích được phép hoặc một mã lựa chọn đã được server kiểm tra, rồi để service tạo URI hợp lệ. Không đưa password, session ID, access token hoặc thông tin cá nhân nhạy cảm vào query string.

## 5. Đặt ba loại redirect cạnh nhau trong cùng một hành trình

Ví dụ đặt phòng có ba nhu cầu:

1. Sau POST nhập chi tiết, hiển thị màn hình review của cùng flow.
2. Sau khi hoàn tất review, chuyển sang flow thanh toán độc lập.
3. Sau khi thanh toán hoàn tất, rời flow để tới trang MVC hiển thị hóa đơn.

~~~mermaid
flowchart TD
    A["booking: enterDetails"] -->|"POST review"| B["Flow execution redirect"]
    B --> C["booking: reviewBooking (cùng execution)"]
    C -->|"confirm"| D["booking: bookingComplete"]
    D -->|"flowRedirect:payment"| E["payment execution mới"]
    E --> F["payment: enterPayment"]
    F -->|"payment success"| G["payment: completed"]
    G -->|"externalRedirect:/orders/receipt"| H["MVC receipt controller"]
~~~

| Tình huống | Nên dùng | Lý do |
|---|---|---|
| Sau POST form, cần render view tiếp theo của flow hiện tại | Flow execution redirect | PRG và giữ execution |
| Validation lỗi nhưng vẫn ở cùng view-state | Flow execution redirect mặc định (với request thường) | Refresh không gửi lại POST |
| Booking kết thúc và bắt đầu thanh toán | `flowRedirect:` | Flow đích có execution riêng |
| Flow kết thúc và hiển thị trang MVC summary | `externalRedirect:` | Rời Web Flow tới controller |
| Flow kết thúc và chuyển sang website điều khoản | `externalRedirect:` với HTTPS | Đích là tài nguyên ngoài flow |
| Chỉ gọi một subflow rồi tiếp tục flow cha | `subflow-state` | Không cần redirect tạo execution mới |

## 6. Redirect và FlowHandler: một extension point khác

Ngoài các view selector trong flow definition, Spring MVC integration còn cho phép cài đặt `FlowHandler` để xử lý kết quả khi flow kết thúc.

Một `FlowHandler` có thể override `handleExecutionOutcome(...)` để chọn URL đích dựa trên outcome:

~~~java
public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleExecutionOutcome(
            FlowExecutionOutcome outcome,
            HttpServletRequest request,
            HttpServletResponse response) {

        if ("bookingConfirmed".equals(outcome.getId())) {
            return "contextRelative:/booking/summary";
        }
        return "contextRelative:/hotels";
    }
}
~~~

Đây là một cách điều hướng sau khi flow kết thúc, được quyết định ở lớp tích hợp MVC thay vì gắn URL cụ thể vào flow XML. Bean handler được đăng ký với tên trùng flow ID mà nó xử lý.

| Cách làm | URL đích được quyết định ở đâu? | Phù hợp khi |
|---|---|---|
| `externalRedirect:` | Flow definition, thường tại end-state | URL là một phần của hành vi flow |
| `FlowHandler.handleExecutionOutcome(...)` | Java FlowHandler trong Spring MVC | Muốn mapping outcome → controller route ở lớp MVC |
| `flowRedirect:` | Flow definition chỉ định flow ID đích | Muốn khởi chạy flow khác |
| Flow execution redirect | Cơ chế pause/render mặc định của SWF | Muốn tiếp tục cùng execution |

Không cần tạo custom FlowHandler chỉ để thay đổi một URL tĩnh nếu `externalRedirect:` đã diễn đạt rõ hành vi. Ngược lại, nếu nhiều outcome cần chuyển tới các controller khác nhau hoặc URL phụ thuộc logic MVC, FlowHandler là extension point phù hợp.

## 7. Điều khiển redirect trong một số trường hợp đặc biệt

### 7.1. Embedded mode và Ajax

Khi flow được nhúng vào một trang lớn, redirect toàn trang sau mỗi Ajax event có thể phá vỡ giao diện bao quanh. Có thể khởi chạy flow với input `mode=embedded` và sử dụng Ajax partial rendering. Chế độ này tác động tới flow execution redirect trong Ajax request; nó không biến `flowRedirect:` hoặc `externalRedirect:` thành một cập nhật fragment.

### 7.2. Redirect khi vẫn ở cùng view-state

Trong một số môi trường, đặc biệt một số tích hợp JSF, redirect khi flow vẫn ở cùng view-state có thể không mong muốn. Flow executor cho phép điều chỉnh `redirect-in-same-state`:

~~~xml
<webflow:flow-executor id="flowExecutor">
    <webflow:flow-execution-attributes>
        <webflow:redirect-in-same-state value="false" />
    </webflow:flow-execution-attributes>
</webflow:flow-executor>
~~~

Đây là cấu hình đặc biệt; mặc định redirect cùng state hữu ích cho PRG và hành vi Back/Refresh. Chỉ thay đổi sau khi xác định được vấn đề cụ thể trong view technology hoặc Ajax integration.

### 7.3. Redirect không đồng nghĩa với lưu dữ liệu

Redirect chỉ quyết định trình duyệt được điều hướng tới đâu. Nó không tự:

- Commit hoặc rollback transaction nghiệp vụ.
- Persist các biến trong flow scope thành dữ liệu lâu dài.
- Xác minh người dùng có quyền truy cập flow đích.
- Đảm bảo request chỉ được xử lý một lần.

Hãy thực hiện thao tác ghi ở service/action có transaction, kiểm tra quyền trước khi chuyển dữ liệu và dùng idempotency/concurrency control cho thao tác nhạy cảm.

## 8. Bảo mật và dữ liệu truyền qua redirect

URL thường xuất hiện trong browser history, access log, proxy log và có thể được gửi trong HTTP referrer tùy chính sách trình duyệt. Vì vậy:

- Chỉ truyền ID tham chiếu không bí mật qua `flowRedirect:` hoặc `externalRedirect:`.
- Không đưa session identifier, token xác thực, password hoặc dữ liệu thanh toán vào query string.
- Flow đích phải xác minh quyền truy cập đối với ID nhận được; biết `bookingId` không có nghĩa người dùng sở hữu booking.
- External redirect tới domain ngoài cần allowlist; không tin URL tùy ý từ request.
- Dùng HTTPS khi điều hướng qua mạng công cộng.
- Nếu dữ liệu lớn hoặc nhạy cảm, lưu ở server-side service/database và truyền một mã tham chiếu ngắn.

Đặc biệt, `flowRedirect:` tạo execution mới nên flow đích cần có input contract rõ ràng. Đừng dựa vào việc flow trước để lại object trong `flowScope`; scope đó thuộc execution khác.

## 9. Kiểm thử ba loại redirect

Flow test nên kiểm tra **loại redirect được yêu cầu**, flow execution có kết thúc hay vẫn hoạt động và flow ID/input đích. Đừng chỉ assert rằng không có exception.

`MockExternalContext` trong test support SWF cung cấp các thông tin để quan sát redirect, ví dụ:

- `getFlowExecutionRedirectRequested()`
- `getFlowDefinitionRedirectRequested()`
- `getFlowRedirectFlowId()`
- `getFlowRedirectFlowInput()`
- `getExternalRedirectRequested()`
- `getExternalRedirectUrl()`

Ví dụ kiểm thử flow redirect bằng test support SWF:

~~~java
public void testRedirectsToPaymentFlow() {
    MockExternalContext context = new MockExternalContext();

    startFlow(context);
    assertCurrentStateEquals("reviewBooking");

    context.setEventId("confirm");
    resumeFlow(context);

    assertTrue(context.getFlowDefinitionRedirectRequested());
    assertEquals("payment", context.getFlowRedirectFlowId());
    assertEquals(
        Long.valueOf(42L),
        context.getFlowRedirectFlowInput().get("bookingId"));
}
~~~

Ví dụ trên giả định fixture đã cung cấp booking có ID `42` và flow kết thúc ở end-state có `view="flowRedirect:payment?bookingId=..."`. Tên API và package cần đối chiếu với phiên bản SWF/test support đang dùng.

Một test external redirect có thể kiểm tra URL được yêu cầu:

~~~java
public void testRedirectsToReceiptController() {
    MockExternalContext context = new MockExternalContext();

    startFlow(context);
    context.setEventId("finish");
    resumeFlow(context);

    assertTrue(context.getExternalRedirectRequested());
    assertTrue(
        context.getExternalRedirectUrl().contains("/orders/receipt"));
}
~~~

Với flow execution redirect, có thể kiểm tra flag `getFlowExecutionRedirectRequested()` trên mock context sau khi flow pause tại view-state. Hãy xác minh URL thực tế qua Spring MVC integration test vì flow unit test không chạy servlet redirect, URL rewriting, context path hoặc filter chain như một container thật.

### 9.1. Ma trận test tối thiểu

| Ca test | Điều cần xác minh |
|---|---|
| Vào view-state sau khi start flow | Có flow execution redirect theo cấu hình mặc định |
| POST event sang view-state tiếp theo | Redirect tiếp tục cùng flow ID/execution |
| Validation lỗi nhưng vẫn ở view-state | Redirect same-state theo chính sách đang cấu hình |
| End-state dùng `flowRedirect:` | Có flow definition redirect và đúng flow ID |
| Flow redirect có query input | Flow đích nhận đúng input attribute |
| End-state dùng `externalRedirect:` | Có external redirect và URI đã resolve đúng |
| External redirect với `contextRelative:` | URI đích có context path phù hợp trong MVC integration |
| Event kết thúc flow | Execution cũ kết thúc đúng outcome |
| Gửi ID của người khác vào flow đích | Service từ chối truy cập trái quyền |
| Redirect URL không nằm allowlist | Request bị từ chối hoặc dùng route an toàn |
| Ajax trong embedded mode | Không điều hướng toàn trang ngoài chủ đích |

### 9.2. Unit test không thay thế HTTP integration test

Mock context có thể xác minh flow yêu cầu loại redirect nào, nhưng không đủ để chứng minh:

- `FlowHandlerAdapter` gửi response redirect đúng status/headers.
- `FlowUrlHandler` tạo URL đúng khi ứng dụng có context path hoặc servlet mapping khác.
- `FlowHandlerMapping` chọn đúng flow ID.
- Cookie/session và execution repository khôi phục đúng qua nhiều HTTP request.
- Spring Security filter chain, CSRF và allowlist external host hoạt động đúng.

Dùng MockMvc hoặc test tích hợp servlet cho các ranh giới đó. Với flow redirect và external redirect, kiểm tra cả URL cuối cùng sau khi expression được đánh giá, không chỉ chuỗi template trong XML.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Refresh khiến trình duyệt hỏi gửi lại form | PRG/flow execution redirect bị tắt hoặc request không đi qua SWF đúng cách | Kiểm tra `FlowHandlerAdapter`, execution URL và redirect policy |
| URL có execution key cũ không tiếp tục được | Execution đã kết thúc, hết hạn hoặc snapshot không còn | Khởi chạy flow mới hoặc phục hồi dữ liệu nghiệp vụ qua service |
| Flow đích báo thiếu input | Query parameter không khớp tên input hoặc custom FlowHandler thay cách tạo input map | Kiểm tra flowRedirect URL, `<input>` và `createExecutionInputMap` |
| Flow đích không được tìm thấy | Sai flow ID hoặc chưa đăng ký trong registry | Kiểm tra registry và flow ID đích |
| Redirect về sai đường dẫn trong ứng dụng | Nhầm servlet-relative với context-relative | Chọn prefix rõ ràng và kiểm tra servlet mapping |
| Redirect tới domain khác không hoạt động | URI không hợp lệ hoặc host bị giới hạn bởi cấu hình | Kiểm tra URL, `FlowHandlerAdapter` và allowed hosts |
| Dữ liệu trong flow cũ không có ở flow mới | Flow redirect tạo execution độc lập | Truyền input hoặc tải dữ liệu từ service |
| Ajax làm tải lại toàn trang | Flow không được khởi chạy ở embedded mode hoặc Ajax handler không phù hợp | Kiểm tra `mode=embedded`, AjaxHandler và fragment rendering |
| Redirect lặp liên tục | URL đích lại điều hướng về cùng flow hoặc handler tạo vòng lặp | Kiểm tra mapping/outcome và đường kết thúc |
| Người dùng truy cập được ID không thuộc sở hữu | Chỉ tin ID truyền qua query | Kiểm tra authorization trong service tại flow đích |

## 11. Bài tập thực hành

Xây dựng hành trình mua vé gồm ba flow độc lập:

- `ticketBooking`: chọn chuyến và xác nhận thông tin.
- `ticketPayment`: thanh toán bằng mã booking được truyền vào.
- `ticketReceipt`: flow hoặc controller hiển thị biên nhận cuối.

Yêu cầu:

1. Sau khi POST event `review` ở flow `ticketBooking`, xác minh flow execution redirect đưa trình duyệt về URL của cùng execution.
2. Khi người dùng xác nhận booking, kết thúc flow bằng `flowRedirect:ticketPayment?bookingId=...`.
3. Khai báo input `bookingId` bắt buộc trong `ticketPayment`, tải booking qua service và kiểm tra quyền sở hữu.
4. Khi thanh toán thành công, dùng `externalRedirect:` tới trang biên nhận hoặc controller trong ứng dụng.
5. So sánh việc dùng `externalRedirect:` với một `FlowHandler.handleExecutionOutcome(...)` tùy chỉnh.
6. Viết test xác minh redirect flag, flow ID, input map và URI đích.
7. Thử truyền một URL external không nằm trong allowlist và xác minh ứng dụng không mở redirect tùy ý.
8. Thử Refresh/Back sau POST và gửi lại event xác nhận; bảo đảm thao tác nghiệp vụ không bị ghi trùng.

**Tiêu chí hoàn thành:** bạn có thể giải thích redirect đang giữ execution hiện tại, tạo execution mới hay rời flow; xác định dữ liệu nào được truyền sang đích; và chứng minh bằng test rằng trình duyệt được chuyển tới đúng nơi. Khi hiểu đúng ba cơ chế, điều hướng sau POST, chuyển giữa các flow và rời ứng dụng có thể được thiết kế rõ ràng, dễ kiểm thử và an toàn hơn.

## Tài liệu tham khảo

- Spring Web Flow 2.5.1 Reference Guide — [Spring MVC Integration, Flow Handling Workflow](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): flow execution redirect mặc định, FlowHandler và redirect prefixes.
- Spring Web Flow 2.5.1 Reference Guide — [Embedding a Flow on a Page](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): PRG, Ajax và embedded mode.
- Spring Web Flow API — [ServletExternalContext](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/context/servlet/ServletExternalContext.html): các yêu cầu và trạng thái flow execution, flow definition và external redirect.
- Spring Web Flow API — [FlowHandlerAdapter](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/mvc/servlet/FlowHandlerAdapter.html): xử lý redirect ở lớp Spring MVC.

*Ghi chú tương thích:* Các ví dụ dựa trên Spring Web Flow 2.5.x. Cú pháp expression trong `view` phụ thuộc expression parser đã cấu hình; ví dụ dùng Spring EL với template expression `#{...}`. Kiểm tra namespace/schema, Servlet API (`javax.servlet` hoặc `jakarta.servlet`) và API test tương ứng với phiên bản thư viện của dự án.
