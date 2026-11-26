# Chỉnh sửa dữ liệu với bước xem lại và nhánh hủy trong Spring Web Flow

Một chức năng **chỉnh sửa hồ sơ cá nhân** thường có ba nhu cầu tưởng chừng đơn giản: cho phép nhập thông tin mới, hiển thị bản xem lại trước khi lưu, và cho phép **hủy toàn bộ thay đổi chưa xác nhận**. Nếu cập nhật cơ sở dữ liệu ngay mỗi lần người dùng rời form, nút *Hủy* sẽ không còn đúng nghĩa. Nếu trải logic qua nhiều controller và session attribute tự quản, việc quay lại từ trang xem lại dễ làm mất dữ liệu hoặc vô tình ghi đè thay đổi của một phiên khác.

Trong **Spring Web Flow (SWF)**, có thể biểu diễn hành trình đó bằng các `view-state`, event và transition; giữ **bản nháp chỉnh sửa** trong `flowScope`; dùng `action-state` chỉ để ghi dữ liệu sau khi người dùng xác nhận; và dùng `end-state` riêng cho nhánh hoàn thành hoặc hủy. Đây là bài **Thực hành tổng hợp** kết hợp form binding, validation, quản lý scope/phiên, tích hợp Spring MVC, kiểm thử và phục hồi khi lỗi.

Mục tiêu của bài là tạo một flow có hợp đồng rõ ràng:

- **Chỉnh sửa** chỉ thay đổi bản nháp thuộc flow, chưa cập nhật dữ liệu đã lưu.
- **Xem lại** hiển thị chính những giá trị người dùng vừa nhập, không tự ghi dữ liệu.
- **Quay lại** cho phép sửa tiếp mà không mất bản nháp.
- **Hủy** từ màn hình nhập hoặc xem lại sẽ kết thúc flow mà không gọi hành động lưu.
- **Xác nhận** mới gọi service để kiểm tra lại quyền, phiên bản dữ liệu và ghi giao dịch.
- **Xung đột hoặc lỗi** được xử lý khác với kết quả hủy chủ động.

## 1. Phân tích yêu cầu và xác định ranh giới dữ liệu

Ta xây dựng chức năng sửa thông tin liên hệ của **người dùng đã đăng nhập**: họ tên (`fullName`) và số điện thoại (`phoneNumber`). Đây là ví dụ đào tạo; các trường và quy tắc kiểm tra cụ thể có thể điều chỉnh cho ứng dụng thật.

| Trạng thái | Việc người dùng nhìn thấy | Có ghi dữ liệu vào database? |
|---|---|---|
| `editProfile` | Form với giá trị ban đầu hoặc bản nháp đã sửa | Không |
| `reviewProfile` | Bản xem lại những giá trị sẽ được lưu | Không |
| `saveProfile` | Action xác minh và lưu dữ liệu | **Có, nếu điều kiện hợp lệ** |
| `conflictProfile` | Thông báo dữ liệu đã thay đổi ở nơi khác | Không ghi đè dữ liệu mới hơn |
| `completed` | Thông báo cập nhật thành công | Bước lưu đã hoàn thành trước đó |
| `cancelled` | Thông báo đã hủy | Không lưu bản nháp |

**Quy tắc quan trọng nhất:** một lần binding thành công không phải một lần persist. Bản nháp `ProfileDraft` ở `flowScope` phải độc lập với đối tượng entity đang được JPA quản lý. Nếu đưa thẳng managed entity vào flow rồi sửa field, một transaction có thể vô tình flush thay đổi vào DB trước khi người dùng bấm *Xác nhận*.

### 1.1. Sơ đồ hành trình

~~~mermaid
flowchart TD
    A["GET /profileEdit: khởi chạy flow"] --> B["on-start: tải ProfileDraft"]
    B --> C["editProfile (view-state)"]
    C -->|"review: binding/validation OK"| D["reviewProfile (view-state)"]
    C -->|"validation lỗi"| C
    C -->|"cancel; không binding"| X(["cancelled (end-state)"])
    D -->|"back"| C
    D -->|"cancel"| X
    D -->|"confirm"| E["saveProfile (action-state)"]
    E -->|"saved"| S(["completed (end-state)"])
    E -->|"invalid"| C
    E -->|"conflict"| F["conflictProfile (view-state)"]
    F -->|"cancel"| X
~~~

Flow có thể được mở rộng với nhánh lỗi hạ tầng riêng, nhưng không nên biến mọi exception thành một event nghiệp vụ `invalid` hoặc `conflict`. Nếu hệ thống không biết giao dịch đã commit hay chưa, không tự động gọi lại action lưu.

### 1.2. Bảng sự kiện

| State hiện tại | Event | State đích | Điều kiện |
|---|---|---|---|
| `editProfile` | `review` | `reviewProfile` | Binding và validation hợp lệ |
| `editProfile` | `cancel` | `cancelled` | Bỏ qua binding để có thể hủy form đang nhập dở |
| `reviewProfile` | `back` | `editProfile` | Không thực hiện save |
| `reviewProfile` | `cancel` | `cancelled` | Không thực hiện save |
| `reviewProfile` | `confirm` | `saveProfile` | Chỉ phát event; quyền và dữ liệu vẫn phải được service kiểm tra |
| `saveProfile` | `saved` | `completed` | Service đã commit thành công |
| `saveProfile` | `invalid` | `editProfile` | Dữ liệu không hợp lệ ở bước kiểm tra cuối |
| `saveProfile` | `conflict` | `conflictProfile` | Phiên bản dữ liệu trong database đã thay đổi |
| `conflictProfile` | `cancel` | `cancelled` | Dừng bản nháp cũ, cho phép khởi chạy flow mới từ trang khác |

Trong SWF, `review`, `back`, `cancel` và `confirm` là **event ID** do UI gửi. Trong khi đó `saved`, `invalid` và `conflict` là **outcome event** từ action. Hai nhóm đều có thể dùng thuộc tính `on` của transition, nhưng nguồn phát và ý nghĩa khác nhau.

## 2. Thiết kế model: bản nháp không phải entity đang được quản lý

Tạo DTO chỉ chứa những dữ liệu cần thiết để chỉnh sửa và một phiên bản kiểm soát xung đột. Đoạn Java sau minh họa ý tưởng; các getter/setter là cần thiết để Spring Form binding hoạt động.

~~~java
package com.example.profile;

import java.io.Serializable;

public class ProfileDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    private String fullName;
    private String phoneNumber;

    // Server điền khi tải bản nháp; không cho client sửa bằng binding.
    private Long originalVersion;

    public ProfileDraft() {
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }

    public void setPhoneNumber(String phoneNumber) {
        this.phoneNumber = phoneNumber;
    }

    public Long getOriginalVersion() {
        return originalVersion;
    }

    public void setOriginalVersion(Long originalVersion) {
        this.originalVersion = originalVersion;
    }
}
~~~

Ở đầu flow, service tạo `ProfileDraft` **bằng cách sao chép** những field cần thiết từ dữ liệu đã lưu của tài khoản đang đăng nhập. Giữ `originalVersion` như dữ liệu do server quản lý để kiểm tra optimistic locking. Không cần đưa `userId` vào form và không tin `ownerId` do client gửi.

Ví dụ giả định có Spring beans:

| Bean | Hợp đồng |
|---|---|
| `profileDraftService` | `loadForCurrentUser()` đọc hồ sơ hiện tại và tạo `ProfileDraft` độc lập |
| `profileSaveAction` | Java Action nhận `RequestContext`, gọi service lưu và trả một outcome rõ ràng |
| `profileService` | `saveForCurrentUser(ProfileDraft)` xác thực chủ sở hữu, validation, version, transaction |

Nếu dùng JPA, tầng service có thể nạp entity mới trong transaction tại thời điểm `confirm`, đối chiếu version và cập nhật các field được phép; không nên giữ entity đang attach trong `flowScope` giữa nhiều HTTP request.

## 3. Khai báo flow XML đầy đủ

Đặt định nghĩa flow ở đường dẫn mẫu `/WEB-INF/flows/profile-edit/profile-edit-flow.xml` và đăng ký flow ID `profileEdit`. Đây là ví dụ theo phong cách XML của Spring Web Flow 2; cần dùng phiên bản framework và thư viện web tương thích khi triển khai.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <!-- Khởi tạo bản nháp độc lập với entity đang được JPA quản lý. -->
    <on-start>
        <evaluate expression="profileDraftService.loadForCurrentUser()"
                  result="flowScope.profileDraft" />
    </on-start>

    <!-- Người dùng sửa và chỉ bind hai field được phép thay đổi. -->
    <view-state id="editProfile"
                view="profile/edit"
                model="profileDraft">
        <binder>
            <binding property="fullName" required="true" />
            <binding property="phoneNumber" />
        </binder>

        <transition on="review" to="reviewProfile"
                    bind="true" validate="true" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <!-- Chỉ hiển thị dữ liệu: không bind lại, không gọi service lưu. -->
    <view-state id="reviewProfile" view="profile/review">
        <transition on="back" to="editProfile"
                    bind="false" validate="false" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
        <transition on="confirm" to="saveProfile"
                    bind="false" validate="false" />
    </view-state>

    <!-- Chỉ state này được thực hiện thay đổi có hiệu lực lâu dài. -->
    <action-state id="saveProfile">
        <evaluate expression="profileSaveAction.execute(flowRequestContext)" />
        <transition on="saved" to="completed" />
        <transition on="invalid" to="editProfile" />
        <transition on="conflict" to="conflictProfile" />
    </action-state>

    <view-state id="conflictProfile" view="profile/conflict">
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <end-state id="completed" view="profile/completed" />
    <end-state id="cancelled" view="profile/cancelled" />
</flow>
~~~

Các view ở đây có thể là JSP được resolve thành `/WEB-INF/views/profile/edit.jsp`, `review.jsp`, `conflict.jsp`, `completed.jsp` và `cancelled.jsp` nếu ứng dụng cấu hình `InternalResourceViewResolver` với prefix/suffix phù hợp. Cần có các bean `profileDraftService` và `profileSaveAction` trong context mà flow có thể resolve.

### 3.1. Tại sao dùng `<on-start>` thay cho một entity lưu trong session?

`<on-start>` chạy khi khởi tạo flow execution và đưa DTO vào `flowScope`. Giá trị này tồn tại qua hai `view-state` trong cùng flow session. Nó **không** tự trở thành dữ liệu đã lưu trong DB; chỉ action `saveProfile` mới chịu trách nhiệm ghi.

Đây cũng là lý do không nên nạp lại bản nháp từ database **mỗi lần vào `editProfile`**. Nếu người dùng quay lại từ trang review, việc tải mới có thể làm mất các thay đổi chưa lưu. Khi muốn bắt đầu hẳn một lượt sửa mới sau xung đột, nên khởi chạy flow execution mới hoặc có hành động reload được thiết kế riêng.

### 3.2. Tại sao có `<binder>`?

`<binder>` trong `view-state` giới hạn những thuộc tính được nhận từ request. Ở ví dụ này, chỉ `fullName` và `phoneNumber` được phép binding từ form. Trường `originalVersion` không nằm trong danh sách, do server quản lý.

Giới hạn binding giúp giảm rủi ro **mass assignment**, nhưng vẫn phải có validation và kiểm tra nghiệp vụ trong service. Không nên xem việc không hiển thị field trong HTML là một biện pháp bảo mật: client có thể tự thêm field trong request.

### 3.3. Khi nào cần validator?

`validate="true"` yêu cầu thực hiện validation theo cơ chế của SWF, **không tự tạo ra mọi quy tắc kiểm tra**. Dự án cần cấu hình validator tương thích với model, ví dụ quy tắc:

- `fullName` không rỗng sau khi trim, tối đa 80 ký tự.
- `phoneNumber` không quá độ dài quy định, chỉ chứa tập ký tự được chấp nhận.
- Nếu dữ liệu thay đổi theo chính sách sản phẩm, service kiểm tra lại trước khi lưu.

Có thể dùng validator của Spring hoặc Bean Validation phù hợp phiên bản/configuration. Với triển khai dùng bean `profileDraftValidator` và convention/hook validation của SWF, cần đối chiếu chữ ký phương thức/cách đăng ký validator chính xác của phiên bản. Không giả định chỉ khai báo `validate="true"` là dữ liệu đã an toàn.

## 4. Trang nhập liệu: gửi event xem lại hoặc hủy

Ví dụ JSP dùng Spring Form tags:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<h2>Chỉnh sửa thông tin liên hệ</h2>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="profileDraft">

    <label for="fullName">Họ và tên</label>
    <form:input path="fullName" id="fullName" />
    <form:errors path="fullName" cssClass="error" />

    <label for="phoneNumber">Số điện thoại</label>
    <form:input path="phoneNumber" id="phoneNumber" />
    <form:errors path="phoneNumber" cssClass="error" />

    <button type="submit" name="_eventId_review">
        Xem lại
    </button>

    <button type="submit" name="_eventId_cancel" formnovalidate>
        Hủy
    </button>
</form:form>
~~~

`${flowExecutionUrl}` là URL thực thi do SWF cung cấp cho view; URL này giúp request quay lại **đúng flow execution**. Không tự thay bằng đường dẫn cố định `/profileEdit` khi đang tiếp tục flow.

Nút `_eventId_review` phát event `review`. SWF binding hai thuộc tính được cho phép vào `profileDraft` rồi chạy validation. Nếu dữ liệu không hợp lệ, giữ người dùng ở view nhập và hiển thị thông báo lỗi.

Nút `_eventId_cancel` phát event `cancel`; transition khai báo `bind="false"` và `validate="false"` để người dùng có thể hủy ngay cả khi vừa xóa hết họ tên hoặc nhập giá trị chưa hợp lệ. `formnovalidate` chỉ giúp bỏ qua **HTML5 browser validation** ở phía client, không thay thế cấu hình server-side ở transition.

Nếu ứng dụng dùng Spring Security CSRF protection, phải thêm CSRF token hợp lệ vào POST theo cơ chế đang cấu hình; biểu mẫu trên tập trung minh họa SWF form binding/event.

## 5. Trang xem lại: không cho phép cập nhật ngầm

Ở state `reviewProfile`, giao diện hiển thị giá trị đang nằm trong `flowScope.profileDraft`, tức bản nháp vừa được binding thành công. Ví dụ JSP dùng JSTL để escape dữ liệu khi render:

~~~jsp
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<h2>Xem lại trước khi lưu</h2>

<p>Họ và tên: <c:out value="${profileDraft.fullName}" /></p>
<p>Số điện thoại: <c:out value="${profileDraft.phoneNumber}" /></p>

<form method="post" action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_back">Sửa tiếp</button>
    <button type="submit" name="_eventId_confirm">Xác nhận lưu</button>
    <button type="submit" name="_eventId_cancel">Hủy thay đổi</button>
</form>
~~~

Trong JSP thực, `${profileDraft.fullName}` và `${profileDraft.phoneNumber}` là các EL expression đọc từ model `profileDraft`, còn `${flowExecutionUrl}` là URL execution do SWF render. `<c:out>` escape nội dung HTML nhằm giảm nguy cơ dữ liệu người dùng bị chèn thành mã khi hiển thị. Nếu dùng công nghệ view khác (Thymeleaf), phải dùng cách escaping tương ứng.

Để trang review không tự làm thay đổi model khi người dùng bấm nút, cả ba transition đã đặt `bind="false"`. Điều này còn ngăn một client tự gửi trường `fullName` mới trực tiếp ở request `confirm` nhằm lách bước xem lại. Tuy nhiên, **service vẫn phải kiểm tra lại** dữ liệu và quyền khi xử lý xác nhận.

### 5.1. Bấm Quay lại không làm mất giá trị

Khi `reviewProfile` phát event `back`, flow chuyển về `editProfile` với cùng `profileDraft` trong `flowScope`. Spring Form render những field từ model hiện tại; không cần copy dữ liệu giữa controller hoặc đọc lại từ database.

Nếu muốn một nút *Khôi phục giá trị ban đầu*, đó là **một event và quy tắc riêng**, ví dụ dịch vụ tải lại dữ liệu trong một action có kiểm soát. Không đánh đồng nút *Quay lại* với *Khôi phục* hoặc *Hủy*.

### 5.2. Bấm Hủy khác bấm Quay lại

- **Quay lại (`back`):** giữ execution đang hoạt động, giữ bản nháp, cho phép chỉnh tiếp.
- **Hủy (`cancel`):** đi tới `end-state cancelled`, kết thúc bản nháp của lượt chỉnh sửa này.
- **Xác nhận (`confirm`):** đi tới action lưu; chỉ thành công khi service trả outcome xác định.

Trang `cancelled` chỉ nên thông báo đã bỏ bản nháp chưa lưu. Nếu trước đó đã có thao tác nghiệp vụ ghi thành công trong một bước khác, kết thúc flow không có khả năng **rollback** thao tác đó. Chính vì vậy thiết kế này cố ý không có bất kỳ bước ghi dữ liệu nào trước `confirm`.

## 6. Action lưu: kiểm tra quyền và xung đột trước khi commit

Ở bước cuối, action Java đọc `ProfileDraft` từ flow scope rồi gọi service. Service phải làm việc với **người dùng hiện đang được xác thực**, không suy quyền từ hidden field của form.

~~~java
package com.example.profile;

import org.springframework.webflow.execution.Action;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class ProfileSaveAction implements Action {

    private final ProfileService profileService;

    public ProfileSaveAction(ProfileService profileService) {
        this.profileService = profileService;
    }

    @Override
    public Event execute(RequestContext context) {
        ProfileDraft draft =
            (ProfileDraft) context.getFlowScope().get("profileDraft");

        if (draft == null) {
            context.getFlashScope().put(
                "profileError", "Không tìm thấy bản nháp cần lưu.");
            return new Event(this, "invalid");
        }

        ProfileSaveOutcome outcome =
            profileService.saveForCurrentUser(draft);

        switch (outcome) {
            case SAVED:
                return new Event(this, "saved");
            case CONFLICT:
                return new Event(this, "conflict");
            case INVALID:
                context.getFlashScope().put(
                    "profileError", "Dữ liệu không còn hợp lệ.");
                return new Event(this, "invalid");
            default:
                throw new IllegalStateException(
                    "Kết quả lưu hồ sơ không được hỗ trợ.");
        }
    }
}
~~~

`ProfileService` và enum `ProfileSaveOutcome` (gồm `SAVED`, `CONFLICT` và `INVALID`) là thành phần do ứng dụng định nghĩa. Ví dụ minh họa cách **chuẩn hóa kết quả nghiệp vụ**, không mô tả toàn bộ lớp service/repository của hệ thống thực.

Tầng service phải thực hiện tối thiểu:

1. Lấy danh tính tài khoản hiện tại từ ngữ cảnh bảo mật đáng tin cậy.
2. Kiểm tra người đó có quyền cập nhật hồ sơ mục tiêu.
3. Validate lại `ProfileDraft` ở thời điểm lưu.
4. Đọc dữ liệu đã lưu trong transaction và so sánh `originalVersion` với phiên bản hiện tại (hoặc cơ chế optimistic locking tương đương).
5. Chỉ cập nhật `fullName`, `phoneNumber` và những field được phép; commit nhất quán.
6. Trả outcome `SAVED` khi **đã biết** thao tác thành công; trả `CONFLICT` hoặc `INVALID` khi kết quả tương ứng được xác định chắc chắn.

Một lỗi hệ thống, timeout hoặc exception trong service **không tự biến thành** outcome `invalid` hay `conflict`. Cần cơ chế exception handling riêng; nếu chưa biết việc ghi đã hoàn tất hay chưa, không tự động gửi lại action lưu mà không có giải pháp idempotency hoặc xác minh trạng thái từ nguồn tin cậy.

### 6.1. Optimistic locking giữ dữ liệu mới hơn không bị ghi đè

Giả sử phiên bản ban đầu là `7`. Người dùng A mở flow và giữ `originalVersion=7`, sau đó người dùng B/cửa sổ khác sửa hồ sơ làm bản ghi lên phiên bản `8`. Khi A xác nhận, service cần phát hiện bản nháp từ phiên bản `7` đã cũ và trả `CONFLICT` thay vì ghi đè mất thay đổi mới.

Màn hình `conflictProfile` giải thích rằng dữ liệu đã thay đổi và đề nghị người dùng kết thúc lượt sửa cũ, mở lại chức năng chỉnh sửa để tải dữ liệu mới. Không nên cho phép xác nhận lại vô hạn một bản nháp đã xung đột mà không có thao tác hòa giải hoặc reload rõ ràng.

### 6.2. Hủy không phải rollback một transaction đã commit

Vì chưa gọi `profileService.saveForCurrentUser(...)`, nhánh `cancelled` chỉ kết thúc flow execution; **không cần một lệnh database rollback** để bỏ bản nháp nằm trong flow scope.

Ngược lại, nếu thiết kế sai và ghi DB ngay ở `transition on="review"`, thì hành vi `cancel` sau đó sẽ không tự hoàn tác. Transaction thường chỉ bao quanh một thao tác server-side, không thể kéo dài an toàn xuyên qua nhiều lượt người dùng chờ ở trang review.

## 7. Đăng ký flow trong ứng dụng Spring MVC

Ứng dụng Spring MVC sử dụng `DispatcherServlet` tiếp nhận request. Khi tích hợp SWF, `FlowHandlerMapping` tìm flow phù hợp theo path, `FlowHandlerAdapter` chuyển yêu cầu đến `FlowExecutor` và engine quản lý state/transition/flow session.

Ví dụ cấu hình XML rút gọn (nằm trong context MVC/Web Flow đã có namespace tương ứng):

~~~xml
<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location id="profileEdit"
                           path="/WEB-INF/flows/profile-edit/profile-edit-flow.xml" />
</webflow:flow-registry>

<webflow:flow-executor id="flowExecutor" />

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Đoạn cấu hình là **phần trích**, giả định `flowBuilderServices`, view factory, `ViewResolver` và servlet mapping đã được khai báo. Đường dẫn trình duyệt minh họa `GET /profileEdit` chỉ đúng khi context path/servlet mapping/handler mapping tương ứng.

Ví dụ một form POST tiếp tục:

~~~http
POST /profileEdit?execution=e1s1 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId_review=&fullName=Nguyen+An&phoneNumber=0900000000
~~~

`e1s1` là khóa execution ví dụ; phải dùng URL thật do SWF render thay vì dựng khóa cố định. Nút `review` có nhiệm vụ rời form sau binding/validation. Không cần viết một `@Controller` riêng cho từng state `editProfile` hay `reviewProfile`.

### 7.1. Bảo vệ request, state và service

Nếu chỉnh sửa hồ sơ chỉ dành cho người đã đăng nhập, Spring Security phải bảo vệ **cả GET khởi chạy và POST tiếp tục** của flow URL. Bật CSRF protection với form POST. Một người dùng có thể tự gửi `_eventId_confirm` hoặc thử URL execution cũ, nên không coi việc một nút bị ẩn trên UI là rào chắn quyền truy cập.

Service luôn xác minh lại danh tính và quyền tại lúc ghi. Nếu người dùng đăng xuất hoặc thay tài khoản khi flow vẫn đang mở, thao tác xác nhận phải bị từ chối hoặc đi theo chính sách phục hồi an toàn.

## 8. Kiểm thử end-to-end theo từng nhánh

Có thể kết hợp công cụ kiểm thử flow của Spring Web Flow với `MockMvc`/tích hợp Servlet của Spring MVC. Cần giữ cookie/session và dùng **execution URL thực tế** giữa các request nếu kiểm thử HTTP.

| Trường hợp | Thao tác thử | State hoặc kết quả kỳ vọng |
|---|---|---|
| Khởi chạy | `GET /profileEdit` | `editProfile` có dữ liệu gốc từ server |
| Nhập hợp lệ | Sửa họ tên, bấm `review` | `reviewProfile` hiển thị giá trị mới |
| Nhập không hợp lệ | Họ tên rỗng, bấm `review` | Vẫn `editProfile`, hiển thị lỗi validation |
| Quay lại | Từ `reviewProfile` bấm `back` | `editProfile` còn bản nháp đã nhập |
| Sửa sau khi quay lại | Bấm `back`, đổi số điện thoại, `review` | Review hiển thị giá trị được sửa mới |
| Hủy khi form lỗi | Nhập form sai, bấm `cancel` | `cancelled`; không gọi save |
| Hủy từ review | Review rồi bấm `cancel` | `cancelled`; database giữ dữ liệu cũ |
| Xác nhận thành công | Review rồi bấm `confirm` | `completed`; dữ liệu mới được persist đúng một lần |
| Client giả mạo field | Gửi thêm `originalVersion` hoặc `isAdmin` | Không bind những field ngoài allowlist |
| Gửi trực tiếp confirm tại edit | POST `_eventId_confirm` khi còn ở `editProfile` | Không thực hiện save qua transition không được khai báo |
| Xung đột phiên bản | Bản ghi bị cập nhật trước `confirm` | `conflictProfile`; không ghi đè |
| Dữ liệu mất hiệu lực | Service trả `INVALID` | Quay lại `editProfile` và có thông báo phù hợp |
| Hai tab một execution | Sao chép URL execution rồi gửi event khác nhau | Xử lý snapshot/request cũ theo policy repository |
| Hai execution cùng người dùng | Mở hai flow rồi sửa cùng hồ sơ | Service chống lost update bằng version |
| Session hết hạn | POST bằng URL execution đã cũ | Có xử lý phục hồi; không tự gọi save |
| Submit lặp | Gửi `confirm` hai lần | Không tạo hai thao tác ghi ngoài chủ đích |

### 8.1. Test “Hủy không gọi save” là quan trọng nhất

Dùng fake/mock `ProfileService` trong kiểm thử flow:

1. Khởi chạy flow; tạo bản nháp từ dữ liệu ban đầu.
2. Gửi `review` với dữ liệu hợp lệ.
3. Gửi `cancel` tại `reviewProfile`.
4. Xác nhận state cuối là `cancelled`.
5. Xác nhận `saveForCurrentUser(...)` **không hề được gọi** và dữ liệu gốc trong repository không đổi.

Lặp lại với nút hủy trực tiếp ở `editProfile` sau khi form bị nhập sai: nhờ `bind="false"`, flow phải vẫn cho phép hủy mà không bị chặn bởi validator.

### 8.2. Test “Quay lại giữ dữ liệu” và “Xác nhận chỉ lưu một lần”

Ở đường thành công, so sánh giá trị của `ProfileDraft` sau `review` với dữ liệu được gửi lúc `confirm`; xác minh trang review không binding thêm field, action lưu được gọi tại đúng state và dữ liệu DB chỉ đổi sau khi xác nhận.

Không chỉ test HTTP 200. Nếu dùng `MockMvcBuilders.standaloneSetup(...)` với controller thuần, kiểm thử đó **không tự tạo** `FlowHandlerMapping`/`FlowExecutor` để thực thi Web Flow. Với integration test, cần application context cấu hình SWF thật.

## 9. Các lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bấm Hủy nhưng validator vẫn báo lỗi | Transition chưa bỏ binding/validation hoặc browser validation chặn | `bind="false"`, `validate="false"`, `formnovalidate` |
| Quay lại bị mất dữ liệu | Model được tạo lại mỗi lần vào view hoặc chỉ ở request scope | Khởi tạo một lần và giữ trong `flowScope` |
| Dữ liệu DB đổi trước khi xác nhận | Dùng managed entity trong flow hoặc gọi save lúc review | DTO tách biệt, chỉ commit ở `saveProfile` |
| Review hiển thị dữ liệu cũ | Form binding sai model/field, validation thất bại | Kiểm tra `model`, `binder`, view resolver |
| Gửi confirm làm sửa field mới | Review cho binding ngoài ý muốn | `bind="false"` trên transition review và service validate |
| Cập nhật mất thay đổi từ tab khác | Không dùng version/concurrency control | Optimistic locking hoặc cơ chế hòa giải |
| Flow lưu hai lần | Replay event, timeout không rõ trạng thái commit | Idempotency / version, không retry mù |
| Xác nhận không được phân quyền đúng | Tin ID từ form hoặc chỉ chặn đường dẫn đầu | Bảo vệ URL và kiểm tra lại service |
| 404 tại đường dẫn flow | Chưa đăng ký flow ID hoặc mapping servlet sai | Kiểm tra `FlowHandlerMapping`, registry và context path |
| POST tiếp tục bị lỗi | Execution key cũ, session timeout, CSRF thiếu | Dùng `flowExecutionUrl`, token CSRF và phục hồi hợp lý |
| Service ném exception nhưng không vào nhánh `invalid` | Exception không phải outcome event | Có error handling riêng, không giả định `else` |

## 10. Bài tập mở rộng và tiêu chí hoàn thành

Sau khi chạy được ví dụ chỉnh sửa hồ sơ, hãy bổ sung một trong các biến thể sau:

1. **Bước nhập nhiều màn hình:** tách `editProfile` thành `editPersonalInfo` và `editContactInfo`; cả hai dùng chung `flowScope.profileDraft`, từ review có thể quay về bước cần sửa.
2. **Nhánh hủy có xác nhận:** thay `cancel` đi thẳng tới `cancelled` bằng một `view-state confirmCancel`; nút “Không hủy” quay lại màn hình trước, nút “Hủy thật” mới kết thúc, nhưng vẫn tuyệt đối không persist trước confirm save.
3. **Cập nhật có kiểm toán:** sau commit thành công, service ghi audit log gồm người thực hiện, thời điểm và những trường được đổi (không log bí mật). Audit không được ghi ở event `review` hoặc `cancel`.
4. **Phục hồi sau lỗi:** triển khai trang khi execution key hết hạn, trang báo conflict và hành động khởi động lượt sửa mới sau khi xác thực lại. Không tự gửi lại POST có tác động ghi.
5. **Kiểm thử bảo mật:** gửi event `confirm` ở sai state, gửi thêm property không được phép, giả lập người dùng mất quyền giữa hai request, gửi lại xác nhận và kiểm tra service từ chối hoặc bảo vệ tính lặp an toàn.

Bài được coi là hoàn thành khi có thể chứng minh bằng cả sơ đồ và kiểm thử rằng **bản nháp sống trong flowScope, review không ghi dữ liệu, Back giữ bản nháp, Cancel kết thúc mà không lưu, Confirm gọi duy nhất điểm ghi có kiểm tra quyền/validation/version và các lỗi quan trọng có đường xử lý riêng**. Đây chính là lợi ích của Spring Web Flow: hành trình nhiều bước được mô tả nhất quán bằng state, event và transition thay vì rải quy tắc điều hướng trong controller.
