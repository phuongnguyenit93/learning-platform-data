# Validation hints và nhóm kiểm tra theo từng bước trong Spring Web Flow

Trong một form đăng ký gồm nhiều màn hình, người dùng nhập email ở bước một, địa chỉ nhận hàng ở bước hai và xác nhận điều khoản ở bước cuối. Nếu ngay từ bước một đã kiểm tra **tất cả** trường của bản đăng ký, hệ thống sẽ báo lỗi cho địa chỉ chưa được hỏi đến. Ngược lại, nếu mỗi bước chỉ kiểm tra thông tin của chính nó mà bỏ qua bước tổng kiểm tra cuối cùng, dữ liệu cũ hoặc bị sửa bất thường có thể lọt vào thao tác ghi.

**Spring Web Flow (SWF)** hỗ trợ giải quyết tình huống này bằng **validation hints** kết hợp **Bean Validation groups**: khai báo tập quy tắc cần chạy ở từng `view-state` hoặc `transition`. Nhờ vậy, logic điều hướng bằng state/event/transition gắn với yêu cầu kiểm tra dữ liệu ở đúng thời điểm; bản nháp có thể giữ trong `flowScope`, binding từng phần theo màn hình, tích hợp Spring MVC để render lỗi và service kiểm tra lại ở bước ghi.

Bài học thuộc chương **Kiểm tra dữ liệu**, tập trung vào cú pháp `validation-hints`, cách định nghĩa groups, sự khác nhau giữa hint theo view và transition, mối quan hệ với `bind`/`validate`, lỗi thường gặp, kiểm thử và ví dụ wizard hoàn chỉnh.

## 1. Vì sao phải chia nhóm validation?

Xét một wizard đăng ký nhận hàng:

1. `enterContact`: nhập họ tên và email.
2. `enterAddress`: nhập địa chỉ giao hàng.
3. `review`: xem lại, tick đồng ý điều khoản rồi xác nhận.
4. `submit`: service kiểm tra quyền, tính hợp lệ và lưu đăng ký.

Một object `RegistrationDraft` chứa tất cả trường. Nhưng ở bước một chỉ có hai trường được người dùng điền; kiểm tra địa chỉ và điều khoản ngay lúc đó sẽ dẫn đến lỗi **quá sớm**.

| Bước | Những dữ liệu vừa nhập | Nhóm cần chạy | Kết quả mong muốn |
|---|---|---|---|
| `enterContact` → Next | `fullName`, `email` | `Contact` và quy tắc chung | Nếu tên/email sai, ở lại bước liên hệ |
| `enterAddress` → Next | `shippingAddress` | `Address`, cộng kiểm tra lại `Contact` nếu muốn | Nếu thiếu địa chỉ, ở lại bước địa chỉ |
| `review` → Confirm | `acceptedTerms` | `Contact`, `Address`, `Confirm` và quy tắc chung | Chặn xác nhận khi bất kỳ phần nào không đạt |
| `enterAddress` → Back | Không nhất thiết nhập xong địa chỉ | Bỏ validation | Cho phép quay lại sửa email |
| Bất kỳ view có nút Cancel | Không cần form hợp lệ | Bỏ binding/validation | Kết thúc flow không lưu |

Có hai ý quan trọng:

- **Phân nhóm** quyết định những constraint nào sẽ được kiểm tra vào một thời điểm.
- **Validation toàn bộ trước khi lưu** là tuyến phòng thủ bổ sung; nhóm theo bước không thay thế kiểm tra nghiệp vụ ở service.

## 2. Validation hints hoạt động ra sao?

Trong Spring Web Flow hỗ trợ partial Bean Validation (từ dòng **2.4**), thuộc tính `validation-hints` được phép khai báo trên `view-state` hoặc `transition`:

~~~xml
<view-state id="enterContact"
            model="registration"
            validation-hints="'default,Contact'">
    <transition on="next" to="enterAddress" />
</view-state>
~~~

Khi người dùng phát event `next`, SWF binding input vào model `registration`, sau đó thực hiện model validation đã cấu hình với những hints tương ứng. Nếu validator tạo lỗi, thông thường flow không rời khỏi view hiện tại mà render lại màn hình có thông báo.

`validation-hints` là **một biểu thức**, không phải tên một Java annotation. Trong ví dụ:

- Chuỗi XML bên ngoài được bao bằng `"..."`.
- Biểu thức bên trong `'default,Contact'` trả về một chuỗi hai hint phân cách bằng dấu phẩy.
- `BeanValidationHintResolver` mặc định diễn giải các hint này thành **các Java class đại diện cho group**.
- Hint `default` mang ý nghĩa đặc biệt là nhóm Bean Validation `Default`; `Contact` là group do ứng dụng tự tạo.

### 2.1. ValidationHintResolver làm nhiệm vụ gì?

Quá trình có thể hình dung như sau:

~~~mermaid
flowchart LR
    A["Form POST + event next"] --> B["SWF bind dữ liệu vào model"]
    B --> C["Đọc validation-hints tại transition hoặc view-state"]
    C --> D["ValidationHintResolver"]
    D --> E["Bean Validation với các group đã phân giải"]
    E --> F{"Có lỗi?"}
    F -->|"Có"| G["Render lại view + messages"]
    F -->|"Không"| H["Đi tiếp theo transition"]
~~~

`BeanValidationHintResolver` mặc định có thể tìm tên group tương ứng với **kiểu lồng trong model** (hoặc lớp cha), hoặc nhận tên class đầy đủ. Ví dụ model có nested interface `Contact`, `Address` thì có thể dùng các hint `'Contact'` và `'Address'`. Nếu tên group không phân giải được, có thể phát sinh lỗi thực thi flow; **đó không phải lỗi nhập liệu của người dùng**.

| Hint | Ý nghĩa | Ghi chú |
|---|---|---|
| `'Contact'` | Nhóm class `RegistrationDraft.Contact` | Tên ngắn được resolver tìm trong model |
| `'Address'` | Nhóm class `RegistrationDraft.Address` | Chạy constraint khai báo thuộc group này |
| `'Confirm'` | Nhóm class `RegistrationDraft.Confirm` | Áp dụng ở bước chấp thuận cuối |
| `'default'` | Bean Validation nhóm `Default` | Constraint không khai báo `groups` mặc định thuộc nhóm này |
| `'default,Contact,Address,Confirm'` | Kiểm tra tập hợp bốn nhóm | Thường dùng trước khi thực hiện action quan trọng |

Nếu group được khai báo trong một class khác, có thể sử dụng tên class đầy đủ thay vì dựa vào nested-type resolution. Trong ứng dụng nâng cấp từ `javax.validation` sang `jakarta.validation`, phải chọn phiên bản Spring Web Flow, Spring Framework, Bean Validation provider và Servlet API tương thích; không trộn hai hệ annotation/bộ thư viện mà chưa kiểm tra.

### 2.2. Đừng nhầm hint với một event

`next` là **event ID** để khớp `<transition on="next">`. `Contact` là **nhóm validation** mà SWF truyền cho validator. Hai giá trị phục vụ mục đích khác nhau.

Không có yêu cầu rằng event ID phải trùng tên group; một event `proceed` có thể kích hoạt các hint `'default,Contact,Address'`. Ngược lại, một view có thể có cả `next`, `back` và `cancel`, nhưng mỗi transition có chính sách binding/validation khác nhau.

## 3. Khai báo model với Bean Validation groups

Ví dụ dùng Bean Validation với các annotation chuẩn thuộc namespace `javax.validation.constraints` phù hợp với một cấu hình Spring Web Flow 2.x dựa trên Java EE. Các dự án tương thích Jakarta EE sử dụng `jakarta.validation.constraints` và thư viện SWF tương ứng.

~~~java
package com.example.registration;

import java.io.Serializable;
import javax.validation.constraints.AssertTrue;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Pattern;
import javax.validation.constraints.Size;

public class RegistrationDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    // Marker interfaces cho các nhóm validation riêng.
    public interface Contact {}
    public interface Address {}
    public interface Confirm {}

    @NotNull(groups = Contact.class)
    @Size(min = 3, max = 80, groups = Contact.class)
    private String fullName;

    @NotNull(groups = Contact.class)
    @Size(min = 5, max = 120, groups = Contact.class)
    @Pattern(regexp = ".+@.+\\..+")
    private String email;

    @NotNull(groups = Address.class)
    @Size(min = 10, max = 200, groups = Address.class)
    private String shippingAddress;

    @AssertTrue(groups = Confirm.class)
    private boolean acceptedTerms;

    public RegistrationDraft() {}

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getShippingAddress() { return shippingAddress; }
    public void setShippingAddress(String shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public boolean isAcceptedTerms() { return acceptedTerms; }
    public void setAcceptedTerms(boolean acceptedTerms) {
        this.acceptedTerms = acceptedTerms;
    }
}
~~~

Đây là DTO minh họa có getter/setter để Spring Form binding có thể truy cập các thuộc tính. Constraint `@Pattern` của email chỉ là kiểm tra định dạng **đơn giản cho bài học**; trong hệ thống thực, email cần quy tắc phù hợp sản phẩm và có thể phải xác minh quyền sở hữu bằng luồng riêng.

**Điểm dễ bỏ sót:** `@Pattern` ở trên không khai báo `groups`, nên nó thuộc **`Default`**. Nếu bước `enterContact` chỉ dùng `validation-hints="'Contact'"`, constraint `@Pattern` đó sẽ không được chọn. Vì vậy ví dụ dùng `'default,Contact'` để chạy cả constraint mặc định lẫn constraint thuộc Contact.

### 3.1. Group không tự kế thừa mọi constraint

Khi validate với group `Address`, thông thường các constraint chỉ thuộc `Contact` **không** tự chạy. Đây chính là mục đích của partial validation.

Ví dụ:

| Trường | Constraint | Group |
|---|---|---|
| `fullName` | `@NotNull`, `@Size` | `Contact` |
| `email` | `@NotNull`, `@Size` | `Contact` |
| `email` | `@Pattern` | `Default` |
| `shippingAddress` | `@NotNull`, `@Size` | `Address` |
| `acceptedTerms` | `@AssertTrue` | `Confirm` |

Nếu một constraint phải chạy ở nhiều nhóm, có thể khai báo `groups = {Contact.class, Address.class}` hoặc chọn nhiều group khi validation. Không cần gắn tất cả constraint vào tất cả group, vì như vậy sẽ tái tạo vấn đề kiểm tra quá sớm.

### 3.2. Group và validation của toàn model

Kiểm tra theo nhóm cho phép tái sử dụng **cùng một model** `RegistrationDraft` trong nhiều state, với những phần hợp lệ tương ứng tại thời điểm đó. Khi đến bước ghi, service vẫn nên validate toàn bộ những phần bắt buộc và thực hiện các quy tắc phụ thuộc cơ sở dữ liệu, quyền của người dùng, trạng thái phiên hay giao dịch.

Bean Validation groups không tự biến dữ liệu client thành đáng tin cậy; các field như `approved`, `price`, `ownerId` không nên được binding từ request chỉ vì chúng có annotation hợp lệ.

## 4. Cấu hình Bean Validation cho Spring Web Flow

Để SWF áp dụng Bean Validation lên model, ứng dụng cần một validator phù hợp, ví dụ `LocalValidatorFactoryBean` trong cấu hình XML kiểu SWF 2.4/2.5:

~~~xml
<!-- Phần trích trong Spring application context có namespace webflow. -->
<bean id="validator"
      class="org.springframework.validation.beanvalidation.LocalValidatorFactoryBean" />

<webflow:flow-builder-services id="flowBuilderServices"
                               validator="validator" />

<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location id="registration"
                           path="/WEB-INF/flows/registration/registration-flow.xml" />
</webflow:flow-registry>
~~~

Đây là **đoạn cấu hình rút gọn**, cần có namespace/XSD của `beans` và `webflow-config`, dependency Bean Validation provider, và cấu hình FlowExecutor/MVC thích hợp để chạy. Việc khai báo validator cho Spring MVC controller không tự bảo đảm mọi phiên bản SWF sẽ dùng cùng instance nếu flow-builder-services chưa được nối đúng.

Khi cần một quy ước phân giải hint khác, phiên bản hỗ trợ có thể cấu hình `validation-hint-resolver`:

~~~xml
<webflow:flow-builder-services
    id="flowBuilderServices"
    validator="validator"
    validation-hint-resolver="myValidationHintResolver" />
~~~

Đoạn trên là **cấu hình thay thế** bean `flowBuilderServices` trước đó, không khai báo trùng hai bean cùng ID. `myValidationHintResolver` phải là bean hiện thực hợp đồng `ValidationHintResolver`; ứng dụng thông thường không cần tùy biến nếu group được khai báo rõ và resolver mặc định nhận diện được.

## 5. Flow XML: validation theo từng màn hình và transition

Flow ví dụ có ba view và một action ghi đăng ký:

~~~mermaid
flowchart TD
    A["enterContact: email, họ tên"] -->|"next + Contact/Default OK"| B["enterAddress: địa chỉ"]
    A -->|"lỗi Contact"| A
    A -->|"cancel"| X(["cancelled"])
    B -->|"next + Contact/Address/Default OK"| C["review: điều khoản"]
    B -->|"lỗi Address"| B
    B -->|"back"| A
    B -->|"cancel"| X
    C -->|"confirm + tất cả groups OK"| D["submit: service lưu"]
    C -->|"lỗi Confirm"| C
    C -->|"back"| B
    C -->|"cancel"| X
    D -->|"success"| E(["completed"])
    D -->|"invalid"| A
    D -->|"failure"| F["submitError"]
~~~

XML minh họa đầy đủ phần flow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <var name="registration"
         class="com.example.registration.RegistrationDraft" />

    <!-- Bước 1: kiểm tra Default + Contact. -->
    <view-state id="enterContact"
                view="registration/contact"
                model="registration"
                validation-hints="'default,Contact'">
        <binder>
            <binding property="fullName" />
            <binding property="email" />
        </binder>
        <transition on="next" to="enterAddress"
                    bind="true" validate="true" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <!-- Bước 2: mặc định kiểm tra Default + Address. -->
    <view-state id="enterAddress"
                view="registration/address"
                model="registration"
                validation-hints="'default,Address'">
        <binder>
            <binding property="shippingAddress" />
        </binder>
        <!-- Override hint tại transition khi sang review:
             kiểm tra cả các bước đã đi qua. -->
        <transition on="next" to="review"
                    validation-hints="'default,Contact,Address'"
                    bind="true" validate="true" />
        <transition on="back" to="enterContact"
                    bind="false" validate="false" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <!-- Bước cuối: binding đúng checkbox điều khoản. -->
    <view-state id="review"
                view="registration/review"
                model="registration"
                validation-hints="'default,Confirm'">
        <binder>
            <binding property="acceptedTerms" />
        </binder>
        <transition on="confirm" to="submit"
                    validation-hints="'default,Contact,Address,Confirm'"
                    bind="true" validate="true" />
        <transition on="back" to="enterAddress"
                    bind="false" validate="false" />
        <transition on="cancel" to="cancelled"
                    bind="false" validate="false" />
    </view-state>

    <!-- Service chịu trách nhiệm kiểm tra nghiệp vụ và persist. -->
    <action-state id="submit">
        <evaluate expression="registrationService.submit(flowScope.registration)" />
        <transition on="success" to="completed" />
        <transition on="invalid" to="enterContact" />
        <transition on="failure" to="submitError" />
    </action-state>

    <view-state id="submitError" view="registration/submit-error">
        <transition on="back" to="review" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <end-state id="completed" view="registration/completed" />
    <end-state id="cancelled" />
</flow>
~~~

Các view, lớp DTO, Spring beans, validator và schema cần được cung cấp bởi ứng dụng thật. `registrationService.submit(...)` trong ví dụ giả định trả outcome được ánh xạ thành event `success`, `invalid` hoặc `failure`; exception do service ném **không tự** chuyển thành `failure`.

### 5.1. Hint ở view-state và hint ở transition: cái nào được ưu tiên?

Trong các phiên bản SWF hỗ trợ tính năng này, khi transition chỉ định `validation-hints` riêng, các hint đó được sử dụng cho transition đang xử lý; nếu không có hint tại transition, cơ chế validation sử dụng hint ở view-state tương ứng.

Đó là lý do ở `enterAddress`:

- View-state khai báo `'default,Address'`.
- Transition `next` khai báo `'default,Contact,Address'` nhằm **kiểm tra lại** những trường liên hệ trước khi đến review.
- Transition `back` dùng `validate="false"` nên không áp dụng validation để chặn đường quay lại.

Tương tự, ở `review`, hint mặc định chỉ là `'default,Confirm'` nhưng transition `confirm` chủ động dùng đủ `'default,Contact,Address,Confirm'`.

**Lưu ý:** override này không có nghĩa tự động **cộng dồn** group của transition vào group của view. Vì vậy phải ghi rõ tất cả group cần kiểm tra tại transition; thiếu `Contact` trong chuỗi ở bước cuối có thể làm bỏ sót constraint chỉ thuộc `Contact`.

### 5.2. Vì sao cần giới hạn binding theo view?

`<binder>` chỉ cho phép cập nhật những thuộc tính tương ứng với view hiện tại. Màn hình review chỉ có thể binding `acceptedTerms` từ request; nó không được phép thay `email` hay `shippingAddress` trực tiếp trong lần POST xác nhận.

Nếu không giới hạn binding, client có thể gửi các field đã “xem lại” với giá trị khác trong request `confirm` để lách bước xác nhận. Validation hints không thay thế **binding allowlist**, và cả hai cũng không thay thế kiểm tra quyền của service.

### 5.3. Validation errors xuất hiện ở đâu?

Nếu constraint của group được chọn phát hiện lỗi, SWF có thể thêm thông báo vào message/binding context và render lại view-state hiện tại. Trong JSP dùng Spring Form tags, có thể hiển thị lỗi:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="registration">
    <form:label path="email">Email</form:label>
    <form:input path="email" />
    <form:errors path="email" cssClass="error" />
    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form:form>
~~~

Đoạn form dành cho view `enterContact`; trang `enterAddress` và `review` phải render field tương ứng. `${flowExecutionUrl}` trong JSP thật là expression `flowExecutionUrl` do SWF cung cấp. Nên dùng execution URL thực tế và CSRF token hợp lệ theo cấu hình Spring Security của ứng dụng.

Trang `review` cũng cần hiển thị lỗi thuộc nhóm `Confirm`. Ví dụ JSP rút gọn:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<h2>Xem lại đăng ký</h2>
<p>Họ tên: <c:out value="${registration.fullName}" /></p>
<p>Email: <c:out value="${registration.email}" /></p>
<p>Địa chỉ: <c:out value="${registration.shippingAddress}" /></p>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="registration">
    <label for="acceptedTerms">Tôi đồng ý điều khoản</label>
    <form:checkbox path="acceptedTerms" id="acceptedTerms" />
    <form:errors path="acceptedTerms" cssClass="error" />

    <button type="submit" name="_eventId_confirm">Xác nhận</button>
    <button type="submit" name="_eventId_back" formnovalidate>Quay lại</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form:form>
~~~

Các biểu thức EL trong ví dụ đọc đối tượng `registration` đã có ở flowScope; `<c:out>` giúp escape dữ liệu khi hiển thị. Binder của `review` chỉ cho phép cập nhật `acceptedTerms`, nên những field khác dù bị client tự thêm vào POST cũng không được phép thay đổi theo cơ chế binding đã khai báo. Với POST thật, nhớ CSRF token khi Spring Security yêu cầu.

## 6. Tách biệt bind, validate và validation-hints

Ba cấu hình này có trách nhiệm khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `bind` | Có lấy dữ liệu request và cập nhật model không? | `bind="false"` cho Cancel |
| `validate` | Có thực hiện model validation cho event này không? | `validate="false"` cho Back |
| `validation-hints` | Nếu validation chạy, cần chọn nhóm/hint nào? | `validation-hints="'Address'"` |

### 6.1. Back và Cancel phải hoạt động dù form chưa hợp lệ

Mẫu phù hợp:

~~~xml
<transition on="back" to="enterContact"
            bind="false" validate="false" />
<transition on="cancel" to="cancelled"
            bind="false" validate="false" />
~~~

`bind="false"` bỏ qua việc cập nhật model từ request đang gửi. `validate="false"` bỏ qua model validation cho event tương ứng. Không nên đánh đồng hai thuộc tính: nếu chỉ đặt `validate="false"` thì binding **vẫn có thể diễn ra**; dữ liệu đang nhập dở có thể đi vào draft trước khi người dùng quay lại.

Trong một số giao diện, sản phẩm muốn **giữ dữ liệu tạm khi quay lại**; khi đó có thể để binding chạy nhưng tắt validation nếu điều đó phù hợp và được kiểm thử rõ ràng. Còn với Cancel, bỏ cả binding và validation là lựa chọn dễ hiểu.

### 6.2. Chỉ đặt hints không đồng nghĩa bật validation

Nếu đã viết:

~~~xml
<transition on="cancel" to="cancelled"
            validation-hints="'Contact,Address'"
            validate="false" />
~~~

thì việc ghi hints không làm SWF tự động bỏ qua `validate="false"`; transition hủy vẫn không nên chạy validation. Đừng cấu hình hints ở event không cần validation vì dễ làm người đọc nhầm ý đồ.

### 6.3. Lỗi binding khác lỗi constraint

Ngay cả khi không chạy Bean Validation group `Address`, request vẫn có thể lỗi **type conversion** trong binding (ví dụ gửi chuỗi vào field kiểu số). Vì vậy:

- Validation theo group xác định constraint nào được kiểm tra **sau binding**.
- Binding/conversion có cơ chế báo lỗi riêng.
- Để bỏ qua mọi field form chưa hợp lệ khi hủy, thường cần `bind="false"`, không chỉ `validate="false"`.

## 7. Kết hợp validation theo nhóm với validator lập trình

Bean Validation annotations phù hợp cho các ràng buộc cấu trúc: bắt buộc nhập, độ dài, pattern, checkbox đồng ý. Các quy tắc liên quan nhiều field, dịch vụ ngoài hoặc chính sách nghiệp vụ thường cần validator Java hoặc service.

Trong SWF, một cách tổ chức là định nghĩa validator bean theo quy ước tên model, ví dụ model tên `registration` thì bean có thể là `registrationValidator`. Validator có phương thức theo tên state:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.validation.ValidationContext;
import org.springframework.stereotype.Component;

@Component("registrationValidator")
public class RegistrationValidator {

    public void validateEnterAddress(
            RegistrationDraft registration,
            ValidationContext context) {

        String address = registration.getShippingAddress();
        if (address != null && address.trim().length() < 10) {
            context.getMessageContext().addMessage(
                new MessageBuilder()
                    .error()
                    .source("shippingAddress")
                    .defaultText("Địa chỉ cần ít nhất 10 ký tự có nghĩa.")
                    .build());
        }
    }
}
~~~

SWF có thể gọi phương thức `validateEnterAddress(...)` theo convention khi view-state `enterAddress` xử lý một event có validation. Đây là ví dụ bổ sung quy tắc **trim và độ dài có nghĩa**, khác với việc đếm ký tự đơn thuần bằng `@Size`. Bean cần được Spring component scan hoặc đăng ký tường minh.

`ValidationContext` cung cấp `getMessageContext()` để thêm thông báo, cùng dữ liệu như event người dùng kích hoạt (`getUserEvent()`) và principal. **Không dùng API giả định `ValidationContext.getValidationHints()`**: trong các API SWF phổ biến, việc lấy/giải quyết hints thuộc cơ chế validation helper/resolver, còn `ValidationContext` cung cấp ngữ cảnh thông điệp và user event.

### 7.1. Nhóm annotation và validator theo convention có thể cùng chạy

Nếu ứng dụng cấu hình cả Bean Validation và validator theo convention, chúng có thể được áp dụng đồng thời. Điều này hữu ích nhưng cần tránh kiểm tra trùng:

| Loại kiểm tra | Gợi ý đặt ở đâu |
|---|---|
| Email đúng định dạng đơn giản | Bean Validation constraint, nhóm Default |
| Tên và địa chỉ có độ dài hợp lệ | Bean Validation group Contact/Address |
| Địa chỉ có nội dung sau khi trim | Validator riêng cho bước địa chỉ |
| Mã ưu đãi còn hiệu lực | Service hoặc action có kiểm soát |
| Người dùng có quyền tạo đăng ký | Service có thông tin principal tin cậy |
| Trạng thái đơn chưa bị thay đổi | Service tại thời điểm ghi |

Nếu validator theo convention có phương thức mặc định `validate(...)`, SWF có thể gọi nó ngoài phương thức theo state. Vì vậy cần biết những phép kiểm tra nào thực sự chạy tại từng bước để tránh thêm thông báo lỗi lặp hoặc kiểm tra các field chưa được nhập.

### 7.2. Thông báo lỗi theo field và lỗi toàn model

Thông báo từ Bean Validation hoặc custom validator nên chỉ rõ field để view hiển thị cạnh ô nhập phù hợp. Với lỗi không gắn với một property, có thể tạo thông báo lỗi chung. Trong mọi trường hợp, không đưa lỗi hạ tầng hoặc stack trace trực tiếp tới người dùng; hãy ghi log nguyên nhân cần thiết và hiển thị thông báo phục hồi phù hợp.

## 8. Chiến lược cuối flow: revalidate trước khi ghi

Ngay cả khi các bước `enterContact` và `enterAddress` đều đã qua validation, đến `review` vẫn nên kiểm tra lại toàn bộ group cần thiết.

Lý do:

- Dữ liệu có thể đã thay đổi do action, subflow hoặc thao tác quay lại.
- Người dùng có thể gửi request khác thứ tự, dùng snapshot cũ hoặc cố ý sửa payload.
- Các quy tắc liên quan DB/quyền truy cập thay đổi giữa lúc nhập và lúc xác nhận.
- Constraint mới có thể được thêm vào một bước mà flow chưa bao phủ hết khi sửa cấu hình.

Trong ví dụ, `transition on="confirm"` áp dụng `'default,Contact,Address,Confirm'`. Dù vậy, service `registrationService.submit(...)` vẫn phải kiểm tra những điều kiện có ý nghĩa đối với giao dịch thật: chủ sở hữu, quyền truy cập, email có bị trùng, giới hạn số lượng, trạng thái hệ thống và tính lặp an toàn.

**Không** dùng một Bean Validation group như `Confirm` để cấp quyền hoặc xác nhận rằng giá, tồn kho, chính sách đã được đảm bảo. Đây là những kiểm tra nghiệp vụ có thể phải thực hiện lại trong transaction.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bước liên hệ báo lỗi địa chỉ chưa nhập | Dùng toàn bộ constraint ở bước đầu | Chọn group Contact/Default phù hợp |
| Email sai định dạng nhưng vẫn qua Contact | `@Pattern` ở Default, hint thiếu `default` | Thêm `'default,Contact'` hoặc phân nhóm lại |
| Bước địa chỉ không chạy group Address | Typo trong `validation-hints` hoặc resolver không tìm được class | Kiểm tra tên nested class, biểu thức và config |
| Khi Next chỉ kiểm tra Address nhưng quên Contact | Hint ở transition đã override hint view | Ghi đầy đủ group cần chạy ở transition |
| Cancel bị chặn do form thiếu trường | Chỉ đặt hint, chưa bỏ binding/validation | Dùng `bind="false" validate="false"` |
| Back ghi giá trị nhập dở vào draft | `validate="false"` nhưng binding vẫn chạy | Cân nhắc `bind="false"` |
| Có lỗi conversion dù đã tắt nhóm validation | Binding vẫn đang diễn ra | Phân biệt bind và validate |
| Nhóm Confirm không chạy khi bấm Confirm | Transition chọn sai hint hoặc không có model để validate | Kiểm tra view có model, binder và hint hợp lệ |
| Hints gây exception khi thực thi flow | Class group không phân giải được | Dùng tên đầy đủ, cấu hình resolver nếu cần |
| Lỗi hiển thị sai field | `MessageBuilder.source(...)` sai property | So khớp tên field trong model và view |
| Một lỗi xuất hiện hai lần | Annotation và custom validator cùng kiểm tra | Phân chia trách nhiệm rõ ràng |
| Gửi confirm với payload giả mạo | Không giới hạn binder/property | Chỉ bind field của view, service revalidate |

## 10. Kiểm thử bao phủ nhóm và từng transition

Không chỉ test một lần submit hợp lệ. Cần tạo dữ liệu để quan sát rõ **nhóm nào chạy ở state nào**.

| Ca kiểm thử | Dữ liệu / event | Kết quả mong đợi |
|---|---|---|
| Contact hợp lệ, Address chưa nhập | `next` tại `enterContact` | Sang `enterAddress`; chưa báo lỗi Address |
| Contact thiếu email | `next` tại `enterContact` | Ở lại Contact với lỗi thuộc Contact |
| Email sai pattern | `next` tại `enterContact` | Ở lại Contact nhờ hint Default |
| Address ngắn hơn 10 ký tự | `next` tại `enterAddress` | Ở lại Address |
| Contact bị sửa thành invalid trước Next ở Address | `next` tại `enterAddress` | Bị chặn do transition chạy lại Contact |
| Địa chỉ chưa hợp lệ, bấm Back | `back` tại `enterAddress` | Sang Contact, không cần Address hợp lệ |
| Dữ liệu form sai, bấm Cancel | `cancel` tại view nhập | Flow kết thúc, không gọi submit service |
| Review nhưng chưa tick điều khoản | `confirm` tại `review` | Ở lại Review, lỗi Confirm |
| Review hợp lệ toàn bộ | `confirm` tại `review` | Đến action submit |
| Submit service từ chối nghiệp vụ | Service trả `invalid` | Về view theo policy, không ghi |
| Hints sai tên group | Cấu hình `'NoSuchGroup'` | Phát hiện lỗi cấu hình trong integration test |
| Hai flow execution độc lập | Mở wizard ở hai tab với hai execution | Model/validation của hai flow không ghi đè nhau |

Các test nên kết hợp ba tầng:

**Unit test Bean Validation:** dùng `Validator.validate(draft, Group.class)` để chứng minh constraint thuộc `Contact` không tự khiến `Address` bị kiểm tra; chạy đồng thời `Default.class` khi cần.

**Flow test:** khởi động flow, gửi event `next`/`back`/`cancel`, quan sát state và `MessageContext`. Test riêng thuộc tính `validation-hints` ở transition, không chỉ thuộc tính ở view-state.

**MVC integration test:** dùng application context có đủ SWF + Spring MVC + validator; dùng execution URL thực và session giữa các POST, kiểm tra trang lỗi và hành vi trở lại bước cũ. `MockMvcBuilders.standaloneSetup(controller)` không tự tạo FlowExecutor.

### 10.1. Ví dụ unit test nhóm độc lập

Mã sau minh họa JUnit + `javax.validation.Validator`. Validator phải được khởi tạo bằng Bean Validation provider phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import javax.validation.Validation;
import javax.validation.Validator;
import org.junit.jupiter.api.Test;

class RegistrationDraftValidationTest {

    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void contactGroupDoesNotRequireAddressYet() {
        RegistrationDraft draft = new RegistrationDraft();
        draft.setFullName("Nguyen An");
        draft.setEmail("an@example.org");
        // shippingAddress còn null, acceptedTerms mặc định false.

        assertTrue(validator.validate(
            draft,
            javax.validation.groups.Default.class,
            RegistrationDraft.Contact.class
        ).isEmpty());

        assertTrue(validator.validate(
            draft, RegistrationDraft.Address.class
        ).stream().anyMatch(v ->
            v.getPropertyPath().toString().equals("shippingAddress")
        ));
    }
}
~~~

Khi triển khai thật, đóng `ValidatorFactory` phù hợp vòng đời tài nguyên của test và bổ sung assertions cụ thể theo từng constraint. Mục tiêu của ví dụ là minh họa **chọn group**, không khẳng định test độc lập này thay thế kiểm thử cú pháp XML hay flow runtime.

## 11. Bài tập thực hành

Thiết kế flow “đăng ký hội thảo” có ba màn hình: `participantDetails` (họ tên/email), `sessionSelection` (chọn phiên học), `reviewRegistration` (xem lại và đồng ý chính sách). Dữ liệu dùng chung trong `flowScope.registrationDraft`.

Yêu cầu:

1. Tạo marker interfaces `Participant`, `Session` và `Consent`; khai báo Bean Validation constraints cho từng group.
2. Cấu hình `LocalValidatorFactoryBean` trong `flowBuilderServices`.
3. Ở view nhập người tham dự, dùng `validation-hints="'default,Participant'"`.
4. Ở view chọn phiên, dùng group `Session`; transition Next kiểm tra lại `Participant` + `Session`.
5. Ở view review, cho phép binding duy nhất checkbox đồng ý; transition Confirm kiểm tra lại tất cả groups.
6. Back và Cancel bỏ validation; Cancel không cập nhật model đang nhập dở.
7. Bổ sung custom validator theo state để phát hiện một điều kiện nhiều field và đưa lỗi qua `MessageContext`.
8. Viết bảng test ít nhất 8 case, bao gồm nhóm kiểm tra chưa đến bước, tên hint sai, dữ liệu thiếu, Cancel, Confirm, và service từ chối ghi.

**Tiêu chí hoàn thành:** người học giải thích được một constraint thuộc **nhóm nào**, vì sao nó được hoặc chưa được chạy ở **state/transition** cụ thể, khác nhau giữa `bind`, `validate` và `validation-hints`, cách lỗi đến được view, và vì sao service vẫn phải tái kiểm tra dữ liệu trước khi persist. Khi các nhóm được thiết kế đúng, wizard sẽ kiểm tra vừa đủ ở từng bước nhưng không bỏ sót điều kiện quan trọng khi xác nhận.

## Tài liệu tham khảo

- Spring Web Flow 2.5, *Rendering views* — phần **JSR-303 Bean Validation**, **Partial Validation**, **ValidationContext** và **Suppressing validation**: https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/views.html
- Spring Web Flow API — `ValidationHintResolver` và `BeanValidationHintResolver`: https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/validation/ValidationHintResolver.html

*Ghi chú tương thích:* Cú pháp và package API phụ thuộc phiên bản Spring Web Flow và Bean Validation. Ví dụ sử dụng phong cách SWF 2.4/2.5 với `javax.validation`; với các phiên bản mới hỗ trợ `jakarta.validation`, phải đối chiếu API và dependencies thực tế, không chỉ thay chuỗi import.
