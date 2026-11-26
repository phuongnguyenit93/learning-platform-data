# Đường đi của một yêu cầu từ DispatcherServlet đến flow và view

Trong chương **Kiến trúc thực thi**, bài này lần theo một yêu cầu HTTP khi ứng dụng dùng Spring Web Flow. Trong module **SPRING_WEB_FLOW**, ta mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; form binding, validation cùng các scope giữ dữ liệu đúng vòng đời, còn Spring MVC tiếp nhận yêu cầu và kết nối flow với giao diện.

Điểm cần nắm là Spring Web Flow chạy bên trong cơ chế dispatch của Spring MVC. **DispatcherServlet** vẫn là cửa vào của ứng dụng web. Hai thành phần **FlowHandlerMapping** và **FlowHandlerAdapter** giúp Spring MVC định tuyến một URL tới flow và chuyển yêu cầu đó cho bộ thực thi flow.

## Bức tranh tổng thể

~~~mermaid
flowchart TD
    A["Trình duyệt gửi HTTP request"] --> B["Servlet container"]
    B --> C["DispatcherServlet"]
    C --> D{"HandlerMapping"}
    D -->|"URL thuộc flow"| E["FlowHandlerMapping"]
    D -->|"URL thuộc controller"| M["RequestMappingHandlerMapping"]
    E --> F["FlowHandler"]
    F --> G["FlowHandlerAdapter"]
    G --> H["FlowExecutor"]
    H --> I["FlowDefinitionRegistry"]
    H --> J["FlowExecutionRepository"]
    I --> K["FlowDefinition"]
    J --> L["FlowExecution"]
    K --> L
    L --> N["State / Event / Transition / Action"]
    N --> O{"Kết quả xử lý"}
    O -->|"Đang ở view-state"| P["MVC ViewFactory / ViewResolver"]
    P --> Q["View render response"]
    O -->|"Flow kết thúc"| R["Flow outcome / redirect"]
    M --> S["Controller + HandlerAdapter"]
    S --> T["MVC View"]
    Q --> U["HTTP response"]
    R --> U
    T --> U
~~~

Sơ đồ cho thấy flow là một loại handler được tích hợp vào pipeline của Spring MVC. **DispatcherServlet** chọn handler dựa trên các **HandlerMapping**; nó không tự phân tích state hay transition. Khi handler là một flow, **FlowHandlerAdapter** gọi **FlowExecutor** để chạy đúng phiên thực thi.

## Các thành phần tham gia

| Thành phần | Trách nhiệm trong đường đi của request |
|---|---|
| Servlet container | Nhận kết nối HTTP và chuyển request tới servlet được ánh xạ, thường là **DispatcherServlet**. |
| **DispatcherServlet** | Điều phối request trong Spring MVC: tìm handler, chọn adapter và gửi response. |
| **FlowHandlerMapping** | Nhận diện URL thuộc một flow đã đăng ký và cung cấp **FlowHandler** tương ứng. |
| **FlowHandler** | Cầu nối ở mức web cho một flow; có thể tùy biến cách xác định flow ID, input và xử lý kết quả kết thúc. |
| **FlowHandlerAdapter** | Adapter để **DispatcherServlet** gọi flow handler; chuyển request/response thành ngữ cảnh thực thi và gọi **FlowExecutor**. |
| **FlowDefinitionRegistry** | Tra cứu định nghĩa flow theo flow ID, thường được nạp từ các file định nghĩa flow. |
| **FlowExecutor** | Cổng thực thi dùng để khởi chạy một flow mới hoặc tiếp tục một flow đang tồn tại. |
| **FlowExecutionRepository** | Lưu và tìm lại trạng thái thực thi giữa các request thông qua execution key. |
| **FlowExecution** | Một lần chạy cụ thể của flow: state hiện tại, dữ liệu trong các scope và lịch sử chuyển trạng thái cần thiết. |
| MVC view infrastructure | Tạo và render view khi flow dừng ở **view-state**, thông qua view factory và cơ chế phân giải view đã cấu hình. |

Cần phân biệt ba khái niệm dễ bị gộp làm một:

- **Flow definition** là bản thiết kế: các state, transition, action và subflow.
- **Flow execution** là một hành trình cụ thể của một người dùng đang đi theo bản thiết kế đó.
- **Flow ID** định danh bản thiết kế; **execution key** định danh lần thực thi cần tiếp tục.

Một flow có thể được nhiều người dùng khởi chạy. Mỗi lần khởi chạy tạo một flow execution riêng, vì vậy dữ liệu của các hành trình không được dùng chung chỉ vì chúng cùng flow ID.

## Đường đi của request theo từng chặng

### 1. Servlet container chuyển request vào DispatcherServlet

Trình duyệt gửi request tới URL của ứng dụng, ví dụ **/checkout**. Servlet container dựa trên servlet mapping để chuyển request đến **DispatcherServlet**. Việc servlet được ánh xạ với **/**, **\*.do** hay một pattern khác phụ thuộc cấu hình ứng dụng; điều quan trọng là URL phải đi vào đúng **DispatcherServlet** đang chứa cấu hình Spring MVC và Web Flow.

Tại thời điểm này request vẫn là request HTTP thông thường. Chưa có state nào của flow được chạy.

### 2. DispatcherServlet tìm handler phù hợp

**DispatcherServlet** hỏi các **HandlerMapping** theo thứ tự đã cấu hình. Với URL thuộc flow, **FlowHandlerMapping** đối chiếu đường dẫn với flow registry và trả về một **FlowHandler**. Với URL thuộc controller, một mapping như **RequestMappingHandlerMapping** có thể trả về controller method.

Do đó, thứ tự của các handler mapping và quy ước URL cần được cấu hình rõ. Nếu URL của controller và URL của flow chồng lấn, mapping được xét trước có thể nhận request và làm request đi sai nhánh.

### 3. FlowHandlerAdapter nhận handler và gọi FlowExecutor

Sau khi có handler, **DispatcherServlet** tìm **HandlerAdapter** hỗ trợ handler đó. **FlowHandlerAdapter** hỗ trợ **FlowHandler**. Adapter tạo ngữ cảnh ngoài flow từ request/response, lấy các thông tin định tuyến cần thiết rồi gọi **FlowExecutor**.

**FlowHandler** là điểm mở rộng ở ranh giới HTTP. Trong trường hợp thông thường, handler mặc định có thể lấy flow ID từ URL. Khi ứng dụng cần quy tắc riêng, có thể cài đặt handler để điều chỉnh input lúc bắt đầu flow hoặc xử lý outcome khi flow kết thúc.

### 4. FlowExecutor khởi chạy hoặc tiếp tục một flow

Đây là nhánh quan trọng nhất của vòng đời request:

| Loại request | Điều kiện thường gặp | Hành động |
|---|---|---|
| Khởi chạy | URL xác định flow ID nhưng chưa có execution key | **FlowExecutor** tra định nghĩa trong registry, tạo **FlowExecution** mới và đưa flow vào state bắt đầu. |
| Tiếp tục | Request mang execution key do flow phát ra trước đó | **FlowExecutor** yêu cầu repository khôi phục execution tương ứng rồi xử lý event/input mới. |

Execution key thường được đưa vào URL tiếp tục flow, chẳng hạn thông qua URL do Web Flow cung cấp cho view. Không nên tự ghép key bằng tay: dùng URL thực thi được framework cung cấp để giữ đúng thông tin định tuyến và vòng đời.

**FlowExecutionRepository** giúp Web Flow tìm lại hành trình giữa nhiều request. Tùy cấu hình, repository có thể lưu snapshot trong bộ nhớ hoặc dùng cơ chế lưu trữ phù hợp với môi trường triển khai. Vì vậy, execution key không nên được xem như toàn bộ dữ liệu flow; nó là khóa để tìm lại execution theo cơ chế repository.

### 5. FlowExecution xử lý state, event và transition

Khi flow bắt đầu hoặc được tiếp tục, engine xác định state hiện tại và xử lý request trong ngữ cảnh đó. Một event khớp với transition có thể khiến flow:

- chạy action hoặc expression;
- chuyển sang **view-state** khác;
- đi vào một subflow và chờ kết quả trả về;
- chuyển đến **end-state** để hoàn tất hành trình.

Ví dụ, người dùng ở state nhập thông tin có thể gửi event **continue**. Transition tương ứng chạy validation và chỉ chuyển sang state xem lại khi dữ liệu hợp lệ. Nếu validation tạo lỗi, flow có thể giữ người dùng ở view hiện tại để sửa dữ liệu.

### 6. View-state kết nối flow với giao diện

Khi flow đi đến **view-state**, Web Flow chuẩn bị model từ dữ liệu được đưa vào scope phù hợp và yêu cầu cơ chế view của Spring MVC tạo giao diện. Tên view trong flow được phân giải qua cấu hình view factory / **ViewResolver**; view sau đó render HTML hoặc nội dung phản hồi tương ứng.

View có thể là JSP, Thymeleaf hoặc công nghệ view khác nếu ứng dụng đã cấu hình adapter và resolver tương thích. View không quyết định transition của flow. Nó hiển thị dữ liệu và gửi event mà flow định nghĩa.

### 7. Response quay lại trình duyệt

Nếu flow đang ở một **view-state**, response chứa giao diện và URL thực thi để request tiếp theo có thể tiếp tục đúng execution. Khi người dùng gửi form, trình duyệt gửi lại dữ liệu cùng event. Chu kỳ từ bước 2 đến bước 7 lặp lại cho đến khi flow kết thúc.

Nếu flow đi đến **end-state**, **FlowHandler** có thể xử lý outcome và điều hướng tới URL đích. Sau khi flow kết thúc, execution đó không còn là một hành trình đang chờ event tiếp theo.

## Cấu hình kết nối Spring MVC và Spring Web Flow

Trong cấu hình XML, registry đăng ký các flow definition; executor sử dụng registry; mapping và adapter đưa flow vào pipeline của **DispatcherServlet**. Ví dụ cấu hình khung:

~~~xml
<webflow:flow-registry id="flowRegistry" base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern value="/**/*-flow.xml" />
</webflow:flow-registry>

<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry" />

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="order" value="0" />
    <property name="flowRegistry" ref="flowRegistry" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Đây là phần kết nối cốt lõi; ứng dụng thực tế còn cần cấu hình view factory, view resolver, message source, validator và các dịch vụ mà flow gọi. Giá trị **order** cần được chọn theo các mapping khác trong ứng dụng để URL flow được nhận đúng. Tên namespace và schema phải khớp phiên bản Spring Web Flow mà dự án sử dụng.

Một flow definition rút gọn minh họa cách state và event được xử lý:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="checkout" class="com.example.CheckoutForm" />

    <view-state id="details"
                view="checkout/details"
                model="checkout">
        <transition on="continue" to="review">
            <evaluate expression="checkoutValidator.validate(checkout, messageContext)" />
        </transition>
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="back" to="details" />
        <transition on="confirm" to="complete" />
    </view-state>

    <end-state id="complete" />
</flow>
~~~

Trong ví dụ này, **checkout** là model của view nhập thông tin. Khi người dùng phát event **continue**, transition gọi validator. Khi dữ liệu hợp lệ, flow đi tới **review**; event **back** quay lại màn hình nhập, còn **confirm** kết thúc flow. Chi tiết validator và cách hiển thị lỗi cần được cấu hình theo ứng dụng.

Một form JSP có thể gửi event về URL thực thi hiện tại như sau:

~~~jsp
<form:form modelAttribute="checkout"
           action="$FLOW_EXECUTION_URL"
           method="post">
    <form:label path="email">Email</form:label>
    <form:input path="email" />
    <button type="submit" name="_eventId_continue">Tiếp tục</button>
</form:form>
~~~

Trong ví dụ JSP, thay **$FLOW_EXECUTION_URL** bằng biểu thức JSP/EL của ứng dụng để lấy URL thực thi hiện tại, thường là **\${flowExecutionUrl}**. URL này giữ thông tin cần thiết để tiếp tục đúng flow execution. Tên nút **_eventId_continue** phát event **continue**, khớp với transition **on="continue"** trong flow definition. Form binding ánh xạ dữ liệu gửi lên vào model; validation quyết định flow có thể đi tiếp hay cần render lại view với thông báo lỗi.

## Dữ liệu sống ở đâu trong hành trình?

Việc chọn scope ảnh hưởng trực tiếp đến dữ liệu mà flow và view có thể đọc ở mỗi chặng:

| Scope | Vòng đời khái quát | Ví dụ sử dụng |
|---|---|---|
| **requestScope** | Một request hiện tại | Giá trị tạm chỉ cần trong lúc xử lý request. |
| **viewScope** | Một lần ở trong view-state | Dữ liệu phụ trợ riêng cho màn hình hiện tại. |
| **flowScope** | Từ lúc flow bắt đầu đến khi flow kết thúc | Form dữ liệu checkout cần dùng ở nhiều state. |
| **conversationScope** | Vòng đời conversation của flow gốc và các subflow | Dữ liệu cần chia sẻ giữa flow cha và subflow. |

Không nên đồng nhất **conversationScope** với toàn bộ HTTP session. Scope mô tả vòng đời dữ liệu trong mô hình Web Flow; cách execution được lưu giữa các request phụ thuộc repository và cấu hình triển khai. Chỉ đưa dữ liệu cần thiết vào scope dài hạn, đặc biệt tránh giữ các đối tượng lớn hoặc dữ liệu nhạy cảm mà flow không cần dùng tiếp.

## Theo dấu lỗi theo đúng chặng

Khi một hành trình không chạy như mong đợi, hãy xác định lỗi xuất hiện ở lớp nào trước khi sửa flow:

| Dấu hiệu | Chặng cần kiểm tra | Nguyên nhân thường gặp |
|---|---|---|
| URL trả về 404 hoặc vào nhầm controller | Servlet mapping và **HandlerMapping** | **DispatcherServlet** không nhận URL, mapping order sai hoặc pattern flow không khớp. |
| Không tìm thấy flow | **FlowHandlerMapping** và **FlowDefinitionRegistry** | Flow ID không khớp registry, file flow chưa được đăng ký hoặc base path sai. |
| Không thể tiếp tục execution | **FlowHandlerAdapter**, execution key và repository | URL thực thi bị mất/sửa, key hết hiệu lực hoặc repository không tìm thấy execution. |
| Event không chuyển state | Flow definition và request form | Tên event không khớp transition, transition không có ở state hiện tại hoặc form gửi sai URL. |
| View không render | View factory và **ViewResolver** | View name không phân giải được, template/JSP thiếu hoặc cấu hình resolver không phù hợp. |
| Dữ liệu mất giữa các màn hình | Model binding và scope | Đối tượng nằm trong scope quá ngắn, tên field không khớp hoặc dữ liệu chưa được lưu vào scope cần thiết. |

Lỗi validation thường là kết quả nghiệp vụ có thể xử lý ngay trong flow: giữ người dùng ở view-state, đưa message vào message context và render lại màn hình. Lỗi cấu hình mapping, lỗi registry hay execution key cần được xử lý ở lớp tích hợp web hoặc repository; thêm transition vào flow sẽ không giải quyết được các lỗi đó.

## Cách kiểm chứng đường đi

Có thể kiểm chứng một flow nhiều bước bằng một kịch bản nhỏ:

1. Gửi request tới URL khởi chạy flow và xác nhận **FlowHandlerMapping** chọn đúng flow ID.
2. Xác nhận **FlowExecutor** tạo execution và flow đi tới view-state đầu tiên.
3. Kiểm tra response có form, dữ liệu model và URL thực thi hợp lệ.
4. Gửi form với event hợp lệ; xác nhận request tiếp theo tiếp tục execution cũ và chuyển đúng state.
5. Gửi dữ liệu không hợp lệ; xác nhận validation giữ flow ở view phù hợp và trả message cho giao diện.
6. Hoàn tất hành trình; xác nhận end-state được xử lý và outcome dẫn tới trang đích mong muốn.

Trong kiểm thử tích hợp, nên kiểm tra cả hai nhánh: khởi chạy flow và tiếp tục flow bằng execution key. Chỉ kiểm tra việc tải được trang đầu tiên chưa chứng minh được repository, event, transition và kết quả kết thúc hoạt động đúng.

## Những điểm cần nhớ

- **DispatcherServlet** điều phối request; **FlowHandlerMapping** và **FlowHandlerAdapter** tích hợp flow vào cơ chế handler của Spring MVC.
- **FlowDefinitionRegistry** tra bản thiết kế; **FlowExecutor** khởi chạy hoặc tiếp tục; **FlowExecutionRepository** tìm lại execution giữa các request.
- Event từ form làm flow chuyển state theo transition đã khai báo. **view-state** kết nối model của flow với view được Spring MVC phân giải và render.
- Execution key phải được giữ qua URL thực thi để request kế tiếp tiếp tục đúng hành trình. Scope phải được chọn theo vòng đời dữ liệu.
- Khi điều tra sự cố, lần theo thứ tự từ servlet mapping, handler mapping, adapter, executor, state/transition đến view resolver.
