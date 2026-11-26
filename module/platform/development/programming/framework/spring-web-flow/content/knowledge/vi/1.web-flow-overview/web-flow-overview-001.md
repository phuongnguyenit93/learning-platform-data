# Spring Web Flow là gì và bài toán điều hướng nhiều bước

> **Chương:** Bản đồ Web Flow  
> **Trọng tâm:** Hiểu vì sao Spring Web Flow tồn tại, cách một hành trình web được mô hình hóa bằng state, event, transition, và khi nào nên áp dụng nó trong ứng dụng Spring MVC.

## 1. Khi một màn hình web không còn là một yêu cầu độc lập

Một trang tra cứu sản phẩm thường có vòng đời đơn giản: trình duyệt gửi yêu cầu, controller lấy dữ liệu, trả về giao diện hoặc JSON. Tuy nhiên, có những tác vụ mà người dùng phải đi qua **một chuỗi bước có thứ tự**, dữ liệu nhập ở bước trước ảnh hưởng đến bước sau, và hệ thống phải xử lý cả quay lại, hủy, nhập sai hoặc hết phiên làm việc.

Ví dụ, chức năng đăng ký dịch vụ có thể gồm:

1. Nhập thông tin cá nhân.
2. Nhập thông tin liên hệ.
3. Kiểm tra lại các dữ liệu đã nhập.
4. Xác nhận đăng ký và nhận kết quả.

Yêu cầu thực tế không dừng ở nút **Tiếp tục**. Người dùng có thể nhấn **Quay lại** để sửa email, bấm **Hủy**, tải lại trang xác nhận, mở cùng một luồng ở hai tab, hoặc để phiên làm việc hết hạn giữa chừng. Hệ thống còn cần tránh lưu trùng đơn đăng ký nếu người dùng gửi lại yêu cầu.

Nếu chỉ ghép các controller theo từng URL, logic điều hướng thường phân tán:

~~~java
// Ví dụ giản lược về điều hướng được đặt trực tiếp trong controller.
@PostMapping("/register/contact")
public String submitContact(
        @ModelAttribute RegistrationDraft draft,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "register/contact";
    }
    if (draft.getEmail() == null) {
        return "redirect:/register/contact";
    }
    return "redirect:/register/review";
}
~~~

Đoạn mã trên chưa cho biết người dùng **được phép** đến trang contact từ trạng thái nào, dữ liệu draft đang lưu ở đâu, nút quay lại hoạt động ra sao, và URL review có thể được mở trực tiếp hay không. Những kiểm tra đó thường xuất hiện ở nhiều controller hoặc trong session, khiến quy trình khó nhìn toàn cảnh và khó kiểm thử.

**Spring Web Flow (SWF)** giải quyết nhóm bài toán này bằng cách đưa hành trình nhiều bước thành một **flow được khai báo tường minh**. Flow có các trạng thái, sự kiện và quy tắc chuyển trạng thái; framework quản lý một lần thực thi flow xuyên qua nhiều HTTP request.

## 2. Spring Web Flow là gì?

Spring Web Flow là một thành phần trong hệ sinh thái Spring dành cho **tương tác web có trạng thái và nhiều bước**. Nó thường được dùng cùng Spring MVC: MVC vẫn tiếp nhận HTTP và render view; Web Flow chịu trách nhiệm xác định người dùng đang ở bước nào, sự kiện nào được chấp nhận và bước tiếp theo là gì.

Một flow là bản mô tả quy trình. **Flow definition** có thể được viết bằng XML; **flow execution** là một phiên chạy cụ thể của định nghĩa đó cho một hành trình người dùng. Hai người cùng mở quy trình đăng ký có thể dùng chung một flow definition nhưng có hai flow execution độc lập.

Các khái niệm quan trọng:

| Khái niệm | Ý nghĩa trong hành trình web | Ví dụ |
| --- | --- | --- |
| **Flow** | Toàn bộ quy trình có điểm bắt đầu, các bước và điểm kết thúc | Đăng ký dịch vụ |
| **State** | Trạng thái hiện tại; chỉ định cần hiển thị gì hoặc thực hiện hành động gì | Nhập liên hệ, xem lại thông tin |
| **Event** | Sự kiện khiến flow xem xét chuyển bước | next, back, confirm, cancel |
| **Transition** | Quy tắc đi từ state hiện tại sang state khác khi có event phù hợp | Từ contact sang review khi next |
| **Flow execution** | Lần thực thi cụ thể, mang theo state và dữ liệu người dùng | Lần đăng ký đang mở ở một tab |
| **Scope** | Nơi lưu dữ liệu với vòng đời phù hợp | flowScope giữ bản nháp |
| **Subflow** | Flow con được flow cha gọi để thực hiện một tác vụ có thể tái sử dụng | Xác minh danh tính |

Web Flow có quan hệ gần với **máy trạng thái hữu hạn** (finite-state machine): ứng dụng có một tập trạng thái đã định nghĩa và chỉ chuyển qua những cạnh hợp lệ. Điểm khác với một máy trạng thái thuần túy là nó còn phối hợp việc render view, binding dữ liệu, validation, lưu trạng thái giữa HTTP request và gọi service nghiệp vụ.

## 3. Bản đồ của một flow nhiều bước

Xét quy trình đăng ký, trong đó người dùng có thể sửa thông tin trước khi xác nhận:

~~~mermaid
flowchart TD
    S((Bắt đầu)) --> P["profile: Thông tin cá nhân"]
    P -->|next| C["contact: Thông tin liên hệ"]
    C -->|back| P
    C -->|next| R["review: Kiểm tra lại"]
    R -->|edit| P
    R -->|confirm| A["save: Lưu đăng ký"]
    A -->|success| F((completed))
    A -->|error| R
    P -->|cancel| X((cancelled))
    C -->|cancel| X
    R -->|cancel| X
~~~

Trong sơ đồ, **profile**, **contact** và **review** là các bước người dùng tương tác. **save** là bước máy chủ thực hiện nghiệp vụ. **completed** và **cancelled** là hai kết thúc khác nhau.

Sơ đồ giúp trả lời những câu hỏi mà logic rải rác trong controller rất khó cho thấy cùng lúc: từ review có được quay lại contact không; cancel có phải thao tác ghi dữ liệu không; khi lưu thất bại phải quay về đâu; sau completed còn nhận sự kiện next hay không.

### 3.1. Bốn loại state thường gặp

| Loại state | Vai trò | Ví dụ |
| --- | --- | --- |
| **view-state** | Hiển thị giao diện, tạm dừng để chờ sự kiện từ người dùng | Form profile, trang review |
| **action-state** | Thực hiện logic phía máy chủ, chọn bước kế tiếp dựa trên kết quả | Gọi service để tạo đăng ký |
| **decision-state** | Rẽ nhánh theo một điều kiện rõ ràng | Đã xác minh tài khoản hay chưa |
| **end-state** | Kết thúc lần chạy flow | completed, cancelled |

Ngoài ra có **subflow-state** để gọi một flow con. Trong thực tế, nhiều hành trình chỉ cần view-state, action-state và end-state.

### 3.2. Event và transition không đồng nghĩa với URL

URL thường nhận diện **một flow** hoặc endpoint tiếp nhận yêu cầu. Còn **event** diễn đạt ý định trong flow, chẳng hạn next, back, confirm. Hai event gửi từ cùng một trang có thể dẫn đến hai state khác nhau; cùng một event next có thể hợp lệ ở state này nhưng không có transition tương ứng ở state khác.

Vì vậy, **không nên coi việc đổi URL là cơ chế bảo vệ thứ tự bước**. Flow cần kiểm tra transition hợp lệ trên phía máy chủ, quyền truy cập và điều kiện nghiệp vụ. Giao diện có ẩn nút confirm cũng không đủ để bảo vệ thao tác xác nhận.

## 4. Ví dụ flow definition bằng XML

Đây là một ví dụ rút gọn, đủ để thấy cách các phần nối với nhau. Giả sử ứng dụng có lớp RegistrationDraft giữ thông tin nhập dở và RegistrationService chịu trách nhiệm khởi tạo, lưu đăng ký. Mã view và service được lược bỏ để tập trung vào điều hướng.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <!-- Mỗi flow execution có một bản nháp riêng. -->
    <var name="registration"
         class="com.example.registration.RegistrationDraft"/>

    <on-start>
        <evaluate expression="registrationService.initialize(registration)"/>
    </on-start>

    <view-state id="profile"
                view="register/profile"
                model="registration">
        <binder>
            <binding property="fullName" required="true"/>
        </binder>
        <transition on="next" to="contact"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="contact"
                view="register/contact"
                model="registration">
        <binder>
            <binding property="email" required="true"/>
            <binding property="phone"/>
        </binder>
        <transition on="back" to="profile" bind="false"/>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="register/review">
        <transition on="edit" to="profile" bind="false"/>
        <transition on="confirm" to="save" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="save">
        <evaluate expression="registrationService.save(registration)"/>
        <transition on="success" to="completed"/>
        <transition on="error" to="review"/>
    </action-state>

    <end-state id="completed" view="register/completed"/>
    <end-state id="cancelled" view="register/cancelled"/>
</flow>
~~~

**Cách đọc flow từ trên xuống:**

1. Thẻ **var** tạo bản nháp registration cho một lần chạy flow; nó thuộc phạm vi flow.
2. Khối **on-start** khởi tạo dữ liệu khi flow bắt đầu.
3. Mỗi **view-state** khai báo view, model dùng cho binding và những event được phép.
4. **transition** mô tả event và state đích. Thuộc tính **bind="false"** có thể dùng cho back/cancel để tránh xử lý dữ liệu form không cần thiết.
5. **action-state** gọi service. Trong ví dụ, service/adaptor phải tạo ra kết quả sự kiện **success** hoặc **error** theo đúng hợp đồng; exception chưa xử lý sẽ không tự biến thành event error.
6. **end-state** hoàn tất flow và giải phóng dữ liệu sống theo flow execution theo cấu hình quản lý phiên.

Đoạn XML minh họa **cấu trúc điều hướng**. Muốn chạy thành ứng dụng thật cần có các lớp Java, view template, cấu hình Web Flow phù hợp phiên bản Spring đang sử dụng, chiến lược validation và xử lý lỗi. Không nên sao chép ví dụ rồi xem nó như một cấu hình ứng dụng hoàn chỉnh.

### 4.1. Vì sao cần một bước action-state riêng cho việc lưu?

Ở trang review, nút confirm thể hiện **ý định lưu**. Bước save là nơi service thực sự thực hiện lệnh. Cách tách này giúp test được điều hướng khi thành công hoặc thất bại và quan sát được thao tác ghi xảy ra ở state nào.

Dù vậy, **action-state không tự bảo đảm thao tác chỉ chạy một lần**. Người dùng có thể gửi lại HTTP request, flow execution có thể được phục hồi hoặc retry. Service vẫn cần bảo đảm an toàn khi gọi lặp, ví dụ dùng mã yêu cầu duy nhất (idempotency key), ràng buộc unique ở cơ sở dữ liệu và transaction đủ ngắn.

### 4.2. Decision-state cho rẽ nhánh tự động

Không phải bước nào cũng yêu cầu render trang. Khi cần kiểm tra trạng thái xác minh trước khi đi tiếp, có thể dùng decision-state:

~~~xml
<decision-state id="checkVerification">
    <if test="registrationService.isVerified(registration)"
        then="review"
        else="verifyAccount"/>
</decision-state>
~~~

Khác với event phát ra từ nút bấm, decision-state tự tính điều kiện ở phía máy chủ để quyết định hướng đi. Điều kiện nghiệp vụ nên nằm trong service hoặc policy dễ kiểm thử, tránh nhét nhiều biểu thức phức tạp vào XML.

## 5. Một HTTP request tương tác với flow như thế nào?

Trình duyệt có thể khởi động flow bằng một yêu cầu như **GET /register**. Sau khi Web Flow tìm thấy định nghĩa register và bắt đầu flow execution, nó chuyển đến view-state profile để render form.

Một lần submit tiếp theo có thể mang thông tin tương tự:

~~~http
POST /register?execution=e1s1
Content-Type: application/x-www-form-urlencoded

_eventId=next&fullName=Nguyen+An
~~~

Ở đây **execution=e1s1** chỉ là khóa minh họa của lần chạy flow; khóa thực tế do framework cấp và có thể thay đổi sau mỗi bước. **_eventId=next** báo sự kiện mà người dùng đã chọn. Một số mẫu form dùng tên nút **_eventId_next** thay cho tham số _eventId.

Chu trình điển hình:

1. Spring MVC chuyển request phù hợp đến Web Flow thông qua handler mapping và handler adapter.
2. Flow executor bắt đầu hoặc khôi phục flow execution dựa vào request.
3. Nếu state hiện tại là view-state, Web Flow thực hiện binding các trường hợp lệ và validation theo cấu hình khi xử lý sự kiện.
4. Flow xác định transition tương ứng. Nếu dữ liệu không hợp lệ, người dùng tiếp tục ở view hiện tại và nhìn thấy thông báo lỗi.
5. Nếu transition thành công, flow chuyển sang state đích; action/decision có thể tiếp tục chạy cho đến khi gặp view-state khác hoặc end-state.
6. Khi cần chờ tương tác, framework lưu trạng thái execution theo cấu hình rồi render hoặc redirect đến view.

Điểm quan trọng là mỗi lần bấm nút vẫn là **một HTTP request độc lập**. Web Flow cung cấp cơ chế nối các request đó thành một hành trình logic liên tục. Nó không giữ một Java thread, servlet request hay database transaction mở suốt thời gian người dùng điền form.

## 6. Kiến trúc: Web Flow nằm ở đâu trong Spring MVC?

Ứng dụng Spring MVC có thể đồng thời có controller bình thường và các flow dành riêng cho tác vụ nhiều bước.

~~~mermaid
flowchart LR
    B["Trình duyệt"] --> D["DispatcherServlet"]
    D --> M["FlowHandlerMapping"]
    M --> A["FlowHandlerAdapter"]
    A --> E["FlowExecutor"]
    E --> R["FlowDefinitionRegistry"]
    E --> V["View / ViewResolver"]
    E --> S["Service nghiệp vụ"]
    S --> DB[("Cơ sở dữ liệu")]
~~~

Những thành phần thường gặp:

| Thành phần | Trách nhiệm |
| --- | --- |
| **FlowDefinitionRegistry** | Đăng ký và tra cứu định nghĩa flow, ví dụ từ các file XML |
| **FlowExecutor** | Bắt đầu, tiếp tục và kết thúc các flow execution |
| **FlowHandlerMapping** | Định tuyến các yêu cầu flow trong Spring MVC |
| **FlowHandlerAdapter** | Kết nối Spring MVC với executor để xử lý yêu cầu |
| **ViewResolver / template engine** | Render giao diện cho view-state |
| **Service / repository** | Thực thi nghiệp vụ, quản lý transaction và truy cập dữ liệu |

**Spring MVC không biến mất khi dùng Web Flow.** Các endpoint REST, trang CRUD đơn giản, tải file hoặc callback từ hệ thống bên ngoài vẫn có thể dùng controller bình thường. Web Flow thích hợp cho những phần giao diện mà **trạng thái hành trình** là vấn đề chính.

Cấu hình registry, executor, MVC handler và view resolver phụ thuộc phiên bản thư viện cùng Spring Framework/Spring Boot. Trước khi tích hợp, phải kiểm tra khả năng tương thích giữa các phiên bản, đặc biệt với ứng dụng sử dụng namespace Jakarta Servlet.

## 7. Binding và validation trong form nhiều bước

**Form binding** chuyển giá trị người dùng gửi thành thuộc tính của model. **Validation** xác định dữ liệu đó đã đáp ứng các điều kiện để đi tiếp hay chưa. Hai bước có quan hệ nhưng không đồng nghĩa.

Trong ví dụ XML ở trên, view-state profile bind thuộc tính fullName; contact bind email và phone. Danh sách **binder/binding** có tác dụng giới hạn những field được phép nhập vào model ở mỗi bước, giảm nguy cơ người dùng cố tình gửi thêm thuộc tính không dự kiến.

Một form có thể gửi event như sau (cấu trúc HTML minh họa; cú pháp chèn khóa execution và CSRF token tùy template engine):

~~~html
<form method="post" action="/register">
  <!-- Giá trị phải do view hiện tại nhận từ Web Flow. -->
  <input type="hidden" name="execution" value="e1s1">
  <label>
    Họ tên
    <input name="fullName" required>
  </label>
  <button type="submit" name="_eventId_next">Tiếp tục</button>
  <button type="submit" name="_eventId_cancel">Hủy</button>
</form>
~~~

Ví dụ này cố ý dùng khóa cố định để người đọc dễ hình dung; ứng dụng thật phải **render khóa execution hiện thời**, dùng URL action phù hợp với flow và gửi CSRF token khi cơ chế bảo vệ CSRF được bật.

### 7.1. Validation theo bước

Không phải tất cả các field đều cần hợp lệ ngay từ bước đầu. Khi đang nhập profile, hệ thống không nên bắt buộc email đã có; khi đang review, mọi trường quan trọng cần được kiểm tra nhất quán.

Một cách thiết kế là:

- **Ràng buộc binding:** giới hạn những thuộc tính được ghi từ request vào model của view-state.
- **Ràng buộc tại bước:** kiểm tra các trường được yêu cầu ở state hiện tại, ví dụ fullName ở profile, email ở contact.
- **Ràng buộc nghiệp vụ tổng thể:** trước khi lưu, service kiểm tra tính hợp lệ của toàn bộ bản nháp, quyền thực hiện và dữ liệu hiện tại trong database.

Web Flow hỗ trợ tích hợp cơ chế validation của Spring; cách khai báo validator và quy tắc tự động gọi validator phụ thuộc cấu hình/model và phiên bản. Validation trong view không thay thế việc kiểm tra phía service khi ghi dữ liệu.

### 7.2. Khi có lỗi nhập liệu

Giả sử người dùng nhập một email sai định dạng rồi nhấn next. Hành vi mong muốn là **giữ state contact**, giữ dữ liệu đã nhập hợp lệ, hiển thị lỗi ngay tại field email và chưa chuyển sang review.

Nếu lỗi phát sinh ở service, ví dụ email vừa bị đăng ký ở một phiên khác, bước save có thể trả một kết quả nghiệp vụ phù hợp rồi điều hướng lại trang review hoặc contact với thông điệp cụ thể. Phải phân biệt **lỗi người dùng có thể sửa** với **lỗi hạ tầng** như database unavailable; không nên gom mọi exception vào nhánh error rồi coi là lỗi dữ liệu.

## 8. Scope: dữ liệu sống bao lâu trong hành trình?

Một trong những lợi ích của Web Flow là mô tả tương đối rõ dữ liệu nào cần tồn tại trong bao lâu. Các scope thường dùng:

| Scope | Vòng đời khái quát | Cách dùng phù hợp |
| --- | --- | --- |
| **requestScope** | Trong một lần xử lý request của flow | Kết quả tính toán ngắn hạn |
| **flashScope** | Tạm thời qua lần chuyển/render view gần nhất theo cơ chế flow | Thông báo sau một thao tác |
| **viewScope** | Trong khi một view-state đang hoạt động | Dữ liệu phục vụ riêng màn hình hiện tại |
| **flowScope** | Trong một flow execution | Bản nháp đăng ký, lựa chọn qua nhiều bước |
| **conversationScope** | Xuyên suốt một conversation, kể cả các flow/subflow liên quan | Ngữ cảnh chung của hành trình cha-con |

Với ví dụ đăng ký, registration nên thuộc **flowScope** vì người dùng cần giữ nó khi đi từ profile sang contact rồi review. Một danh sách gợi ý chỉ dùng tại màn hình profile có thể thuộc viewScope. Không nên sử dụng session HTTP toàn cục làm chỗ chứa mặc định cho tất cả bản nháp, vì nhiều tab hoặc nhiều hành trình có thể ghi đè dữ liệu của nhau.

### 8.1. Flow execution không phải dữ liệu vĩnh viễn

Dữ liệu scope của flow là **dữ liệu làm việc**, thường nằm trong bộ nhớ hoặc cơ chế lưu flow execution do ứng dụng cấu hình. Nó có thể mất khi phiên hết hạn, bị dọn dẹp hoặc ứng dụng thay đổi cách lưu trữ. Bản ghi quan trọng đã xác nhận cần được lưu có chủ đích vào nơi bền vững như cơ sở dữ liệu.

Không nên nhét đối tượng quá lớn, entity còn gắn với persistence context, tài nguyên không serializable hoặc dữ liệu nhạy cảm không cần thiết vào flowScope. Chỉ lưu những giá trị tối thiểu để tiếp tục hành trình.

### 8.2. Hai tab, nút Back của trình duyệt và khóa execution cũ

Người dùng có thể mở hai tab đăng ký, hoặc quay về một trang được trình duyệt cache. Nếu gửi request với **execution key đã cũ**, chương trình có thể cần phục hồi snapshot phù hợp hoặc báo không thể tiếp tục, tùy cấu hình repository/continuation và giới hạn snapshot của Web Flow.

Không được giả định mọi khóa cũ đều hợp lệ hoặc mọi trình duyệt Back tương đương với event back do flow định nghĩa. Nên thiết kế đường phục hồi rõ ràng, ví dụ cho người dùng bắt đầu lại, mở bản nháp đã được lưu bền vững, hoặc chuyển đến trang thông báo hết hạn.

## 9. Subflow: tái sử dụng một chặng của hành trình

Giả sử cả đăng ký tài khoản và xác nhận đơn hàng đều cần xác minh số điện thoại. Thay vì sao chép ba trang xác minh vào hai flow, có thể tạo **subflow** verifyPhone rồi gọi từ flow cha.

~~~xml
<subflow-state id="verifyPhone" subflow="verifyPhone">
    <input name="phone" value="registration.phone"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

Flow con có thể nhận input phone và kết thúc bằng end-state tương ứng, qua đó flow cha nhận event verified hoặc cancelled. Khi cần trao dữ liệu trở lại, định nghĩa output của subflow để mô tả hợp đồng rõ ràng.

**Subflow phù hợp cho một tác vụ có đầu vào, kết quả và vòng đời rõ ràng.** Nó không nên được dùng chỉ để chia một file XML lớn thành các mảnh tùy ý. Nếu xác minh số điện thoại là nghiệp vụ độc lập, service xác minh vẫn phải chịu trách nhiệm bảo vệ mã OTP, giới hạn lượt thử và các chính sách bảo mật.

## 10. Quản lý phiên, lỗi và phục hồi flow

Một flow chạy nhiều bước đồng nghĩa hệ thống phải xử lý các tình huống bất thường. Bảng dưới đây thể hiện hành vi nên thiết kế từ đầu:

| Tình huống | Điều nên xác định trước |
| --- | --- |
| Form sai dữ liệu | Giữ state, đưa lỗi về field, không đánh mất các giá trị hợp lệ |
| Người dùng bấm cancel | Xác định có cần dọn bản nháp, hoàn tác tài nguyên tạm, hoặc chỉ kết thúc flow |
| Session/flow execution hết hạn | Hiển thị thông báo dễ hiểu và đường bắt đầu lại hoặc phục hồi bản nháp |
| Người dùng tải lại trang kết quả | Tránh ghi lặp; cung cấp trạng thái kết quả có thể tra cứu |
| Service trả kết quả nghiệp vụ thất bại | Trả event/đường đi được thiết kế rõ ràng |
| Service ném exception kỹ thuật | Ghi log, đưa ra trang lỗi an toàn; cân nhắc retry có kiểm soát |
| Hai tab cùng thao tác một dữ liệu | Xác định ràng buộc cạnh tranh và idempotency ở tầng nghiệp vụ |

### 10.1. Không kéo dài transaction qua nhiều trang

Một luồng đăng ký có thể tồn tại vài phút. **Transaction database** không nên mở từ bước profile rồi chờ người dùng đến bước review. Thay vào đó, mỗi thao tác nghiệp vụ quan trọng trong service có transaction ngắn, độc lập. Khi confirm, service đọc và kiểm tra lại điều kiện hiện thời rồi commit.

Nếu hành trình gồm nhiều thao tác đã commit và cần bù trừ khi hủy, đó là vấn đề **nghiệp vụ/saga/compensation**, không được Web Flow tự động giải quyết chỉ bằng event cancel.

### 10.2. Bảo mật trong flow

State và transition là sơ đồ điều hướng, không phải cơ chế phân quyền toàn diện. Những thao tác như save phải xác thực người gọi, kiểm tra chủ sở hữu dữ liệu, CSRF, quyền thao tác và giới hạn số lần thử khi thích hợp. Không tin rằng tham số event từ trình duyệt luôn đến từ nút đã render. Mọi input đều cần được kiểm tra ở phía máy chủ.

## 11. Kiểm thử điều hướng dưới dạng chuyển trạng thái

Lợi thế quan trọng của cách mô hình hóa này là có thể kiểm thử từng đường đi mà không phải suy luận từ một chuỗi controller nằm rải rác.

Với flow đăng ký, một tập kịch bản tối thiểu gồm:

| Trạng thái ban đầu | Event/điều kiện | Trạng thái hoặc kết quả mong đợi |
| --- | --- | --- |
| profile | next, dữ liệu hợp lệ | contact |
| profile | next, thiếu fullName | profile cùng lỗi validation |
| contact | back | profile, dữ liệu đã nhập còn phù hợp |
| contact | next, email sai | contact cùng lỗi validation |
| contact | next, email đúng | review |
| review | edit | profile |
| review | confirm, lưu thành công | completed |
| review | confirm, lỗi nghiệp vụ | review hoặc state xử lý lỗi đã khai báo |
| profile/contact/review | cancel | cancelled |
| completed | gửi lại event cũ | Không tạo thêm bản ghi |

Web Flow có cơ sở hạ tầng test flow execution trong các thế hệ thư viện khác nhau. Về mặt ý tưởng, test bắt đầu flow, gửi một event và kiểm tra state đích:

~~~text
startFlow()
assertCurrentState("profile")

submitEvent("next", { fullName: "Nguyen An" })
assertCurrentState("contact")

submitEvent("back")
assertCurrentState("profile")
~~~

Đây là **pseudocode cho kịch bản**, không phải API test có thể chạy nguyên văn. Ngoài test transition, vẫn cần test binding/validation thực, Spring MVC integration, session expiration, phân quyền, xử lý concurrent request và tính idempotent của service lưu dữ liệu.

## 12. Khi nào nên chọn Spring Web Flow?

Web Flow phù hợp nhất khi **điều hướng có nhiều nhánh và dữ liệu cần duy trì qua các bước** là một phần quan trọng của yêu cầu:

- **Đăng ký và onboarding** nhiều trang với bước kiểm tra, quay lại, hủy.
- **Checkout/đặt chỗ** với chọn dịch vụ, nhập thông tin, xác nhận và kết thúc.
- **Quy trình duyệt hoặc wizard quản trị** có bước review, điều kiện rẽ nhánh, subflow xác minh.
- **Form nhiều trang** có quy tắc chuyển bước phức tạp hơn việc hiển thị từng phần của một trang.

Một controller Spring MVC thông thường thường đơn giản hơn cho CRUD ít bước, form chỉ một lần submit, hoặc API thuần stateless. Với ứng dụng web hiện đại có frontend SPA tự quản lý toàn bộ wizard, cần cân nhắc rõ **state điều hướng đặt ở frontend hay backend**; Web Flow không bắt buộc phải là lựa chọn mặc định.

Khi đánh giá áp dụng Web Flow, nên trả lời:

1. Quy trình có những state nào, event nào, bao nhiêu nhánh quay lại/hủy/lỗi?
2. Dữ liệu nào phải còn giữa các request, và dữ liệu nào cần lưu bền vững?
3. Quy tắc nào là điều hướng, quy tắc nào là nghiệp vụ phải ở service?
4. Cần những trường hợp phục hồi nào khi phiên hết hạn hoặc submit lặp?
5. Phiên bản SWF có tương thích với nền Spring MVC/Spring Boot/Jakarta đang vận hành không?

Nếu nhóm phát triển không thể vẽ ra một bản đồ state/event rõ ràng, nên làm rõ quy trình nghiệp vụ trước khi chọn framework.

## 13. Các lỗi thiết kế thường gặp

**Đặt toàn bộ nghiệp vụ trong XML.** Một flow definition nên mô tả state, transition và lời gọi service. Quy tắc giá, đăng ký, thanh toán, transaction và retry cần nằm trong các lớp nghiệp vụ có thể test độc lập.

**Dùng session HTTP làm kho dữ liệu chung.** Điều này có thể gây lẫn dữ liệu giữa các flow execution. Chọn scope nhỏ nhất đáp ứng vòng đời dữ liệu và lưu bản nháp bền vững khi yêu cầu phục hồi vượt qua session.

**Xem event confirm là xác nhận an toàn tuyệt đối.** Event có thể bị gửi lại hoặc bị giả mạo. Service phải thực hiện kiểm tra quyền, validate lần cuối và chống ghi trùng.

**Bỏ qua đường lỗi.** Bản đồ chỉ có next và success rất dễ trình bày nhưng không đủ cho sản phẩm thật. Cần thiết kế sớm đường back, cancel, validation failure, service failure và session expiration.

**Nhầm flow execution với transaction.** Flow có thể kéo dài qua nhiều HTTP request, trong khi transaction database chỉ nên tồn tại trong ranh giới ngắn của một thao tác nghiệp vụ.

**Viết test chỉ theo happy path.** Lỗi quan trọng thường xuất hiện khi người dùng quay lại, gửi event sai state, mở hai tab hoặc xác nhận lần thứ hai.

## 14. Bài thực hành: biến yêu cầu thành bản đồ Web Flow

Giả sử cần xây dựng một hành trình **đặt lịch tư vấn**:

- Người dùng chọn dịch vụ.
- Chọn ngày giờ còn trống.
- Nhập thông tin liên hệ.
- Xem lại lịch hẹn rồi xác nhận.
- Có thể quay lại, hủy hoặc đổi giờ khi thời điểm đã chọn không còn khả dụng.

Hãy tự thiết kế:

1. Ít nhất bốn view-state và một action-state để lưu lịch hẹn.
2. Các event next, back, confirm và cancel; thêm đường phản hồi khi khung giờ bị người khác giữ trước.
3. Bảng chọn scope cho thông tin dịch vụ, ngày giờ, người liên hệ và thông báo lỗi.
4. Quy tắc validation nào chạy từng bước, quy tắc nào phải kiểm tra lại ngay trước commit.
5. Ba test case ngoài happy path: giờ đã hết chỗ, form sai, gửi confirm lặp.

Một thiết kế tốt sẽ diễn đạt được hành trình bằng sơ đồ trước khi viết controller, và service lưu lịch hẹn vẫn an toàn ngay cả khi cùng một yêu cầu được gửi hai lần.

## 15. Tổng kết kiến thức

Spring Web Flow mô hình hóa một hành trình web dài thành **flow definition** gồm **state**, **event** và **transition**. Nó phối hợp với Spring MVC để duy trì **flow execution** qua nhiều request, render form, bind/validate dữ liệu, tổ chức scope và gọi các service nghiệp vụ. **Subflow** giúp tái sử dụng một chặng của hành trình có giao diện đầu vào/đầu ra rõ ràng.

Giá trị chính của Web Flow là khiến quy tắc điều hướng được nhìn thấy, kiểm tra và kiểm thử như một mô hình thống nhất. Để dùng an toàn trong sản phẩm thật, vẫn phải thiết kế kỹ validation, session expiration, concurrency, bảo mật, transaction và idempotency ở tầng nghiệp vụ.

**Câu hỏi tự kiểm tra**

1. Khác biệt giữa flow definition và flow execution là gì?
2. Khi người dùng nhấn back trên form, vì sao có thể cần bind="false"?
3. Tại sao nên giữ bản nháp đăng ký trong flowScope thay vì một biến static hoặc session dùng chung?
4. Vì sao event confirm chưa đủ để bảo đảm không lưu trùng?
5. Nếu một quy trình chỉ gồm một trang nhập liệu và một trang kết quả, bạn sẽ chọn MVC thông thường hay Web Flow? Vì sao?
