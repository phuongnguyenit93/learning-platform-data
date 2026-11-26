# Nối các bước bằng transition

Trong **Spring Web Flow (SWF)**, một hành trình gồm nhiều màn hình được nối với nhau bằng **transition**. Khi người dùng bấm nút Tiếp tục, Quay lại, Xác nhận hoặc Hủy, trình duyệt gửi một **event**. Web Flow nhận event trong state hiện tại, tìm transition phù hợp và quyết định state tiếp theo. Nhờ vậy, đường đi của ứng dụng được mô tả rõ ràng thay vì rải điều hướng qua nhiều controller.

Bài thuộc chương **Flow đầu tiên** của module **SPRING_WEB_FLOW**. Ta sẽ nối các bước của một quy trình đăng ký đơn giản: nhập thông tin → xem lại → hoàn tất; đồng thời thêm nhánh quay lại và hủy. Bạn sẽ học cách đặt tên event, khai báo transition trong XML, dùng transition action để kiểm tra điều kiện, tạo global transition, xử lý event không đổi state và kiểm soát browser history.

Ví dụ lấy **Java 17 + Spring Framework 6.x + Spring Web Flow 3.x + Spring MVC** làm nền tảng. Các đoạn XML theo flow definition language của Web Flow; phần giao diện dùng HTML/Thymeleaf minh họa. Với SWF 2.5/Spring 5 hoặc SWF 4/Spring 7, hãy đối chiếu schema/API đúng phiên bản đang dùng.

> **Phạm vi:** Bài tập trung vào cách nối state bằng transition. Các action nghiệp vụ chỉ là ví dụ minh họa; nếu một transition tạo booking/thanh toán thật, service vẫn phải tự kiểm tra quyền, transaction, trạng thái dữ liệu và idempotency.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa **state**, **event**, **transition** và **target state**.
2. Gửi event từ HTML bằng named button, hidden field hoặc link.
3. Viết nhiều transition trên cùng một state và hiểu vì sao event phải được khai báo ở state hiện tại.
4. Phân biệt **bind="false"** với **validate="false"**.
5. Gọi action trong transition và giữ người dùng ở view hiện tại khi điều kiện không đạt.
6. Tạo transition không có thuộc tính **to** để xử lý event tại chỗ, hoặc cập nhật fragment bằng Ajax.
7. Khai báo **global-transitions** cho những event dùng chung.
8. Điều hướng sang **action-state**, **decision-state**, **subflow-state** hoặc **end-state**.
9. Chọn history policy phù hợp khi người dùng bấm Back.
10. Kiểm thử đường đi đúng, event sai, validation lỗi và nhánh nghiệp vụ thất bại.

Kết quả mong muốn là một flow có đường đi rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> enterDetails
    enterDetails --> review: next
    enterDetails --> cancelled: cancel
    review --> enterDetails: back
    review --> completed: finish
    completed --> [*]
    cancelled --> [*]
~~~

## 2. State, event và transition liên kết với nhau thế nào?

Một flow là máy trạng thái điều khiển hành trình. **State** cho biết người dùng đang ở bước nào; **event** mô tả điều người dùng hoặc action vừa yêu cầu; **transition** là quy tắc phản hồi event trong state đó.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| State | Flow đang ở bước nào? | **enterDetails**, **review** |
| Event | Điều gì vừa xảy ra? | **next**, **back**, **cancel**, **finish** |
| Transition | Khi nhận event này thì làm gì? | **on="next" to="review"** |
| Target state | Sau transition sẽ tới đâu? | **review**, **completed** |

Ví dụ:

~~~xml
<view-state id="enterDetails">
    <transition on="next" to="review"/>
</view-state>
~~~

Khi flow đang ở **enterDetails** và nhận event **next**, Web Flow tìm transition có **on="next"** rồi chuyển tới state **review**. Nếu flow đang ở state khác, transition này không tự áp dụng.

**Transition không phải một URL redirect được viết trong HTML.** HTML chỉ gửi event; flow definition ở server mới quyết định state đích. Đây là lý do người dùng không thể tự gửi một tham số **to=completed** để bỏ qua state mà XML chưa cho phép.

### 2.1. Một state có thể có nhiều transition

Một màn hình nhập liệu thường có nhiều hành động:

~~~xml
<view-state id="enterDetails">
    <transition on="next" to="review"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Event **next** đi tiếp; event **cancel** kết thúc nhánh hiện tại. Mỗi transition cần một event ID rõ ràng. Không nên đặt hai transition cùng event ID trong cùng một state rồi mong framework đoán ý định.

### 2.2. State đích phải tồn tại trong flow

Các giá trị **to** tham chiếu ID của state khác trong cùng flow definition:

~~~xml
<view-state id="review">
    <transition on="finish" to="completed"/>
</view-state>

<end-state id="completed"/>
~~~

Nếu gõ sai **to="complete"** trong khi không có state ID **complete**, flow definition có thể không khởi tạo được hoặc báo lỗi khi build/parse flow. Hãy xem ID là định danh của state machine, không phải tên template.

## 3. Gửi event từ view

Web Flow nhận event từ request thông qua các tham số đặc biệt. Với HTML form, hai cách thường dùng là **named submit button** và **hidden event parameter**.

### 3.1. Named submit button — phù hợp khi một form có nhiều nút

~~~html
<form method="post" th:action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_next" value="next">
        Tiếp tục
    </button>
    <button type="submit" name="_eventId_cancel" value="cancel"
            formnovalidate>
        Hủy
    </button>
</form>
~~~

Khi người dùng nhấn nút Tiếp tục, request có tham số tên **_eventId_next**; Web Flow lấy phần sau **_eventId_** làm event ID là **next**. Nếu nhấn Hủy, event ID là **cancel**.

Đây là cách dễ đọc khi nhiều nút cùng gửi một form vì chỉ nút được nhấn mới gửi giá trị tương ứng.

### 3.2. Hidden event parameter — phù hợp khi form chỉ có một event

~~~html
<form method="post" th:action="${flowExecutionUrl}">
    <input type="hidden" name="_eventId" value="next">
    <button type="submit">Tiếp tục</button>
</form>
~~~

Web Flow đọc giá trị **_eventId** là **next**. Chỉ nên dùng kiểu này khi form có một event duy nhất; nếu có nhiều nút khác nhau, named button rõ ràng hơn.

### 3.3. Event từ link

Với một hành động điều hướng không cần submit form, view có thể gửi event qua link theo cơ chế URL do Web Flow cung cấp. Cú pháp URL phụ thuộc view technology và tích hợp đang dùng. Với Thymeleaf/Spring MVC, không tự ghép execution key bằng JavaScript; dùng biến flow URL hoặc helper/tag phù hợp với cấu hình để tạo request đúng.

### 3.4. Không nhầm event ID với state ID

| Request event | XML transition | State đích |
| --- | --- | --- |
| **_eventId_next** | **on="next"** | **review** |
| **_eventId_back** | **on="back"** | **enterDetails** |
| **_eventId_finish** | **on="finish"** | **completed** |
| **_eventId_cancel** | **on="cancel"** | **cancelled** |

Tên event do view gửi phải khớp giá trị **on**. State đích do thuộc tính **to** xác định. Đổi tên event trong HTML mà quên đổi XML sẽ làm transition không khớp.

## 4. Flow hoàn chỉnh: nhập → xem lại → kết thúc

Ta dùng một flow đăng ký nhỏ có hai view-state và hai end-state. Mỗi màn hình phát event để điều hướng sang bước tiếp theo hoặc quay lại.

Tạo file **src/main/resources/flows/signup/signup-flow.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="signup" class="com.example.signup.SignupDraft"/>

    <view-state id="enterDetails"
                view="signup/details"
                model="signup">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="signup/review" model="signup">
        <transition on="back" to="enterDetails" validate="false"/>
        <transition on="finish" to="completed"/>
    </view-state>

    <end-state id="completed" view="signup/completed"/>
    <end-state id="cancelled" view="signup/cancelled"/>
</flow>
~~~

Flow trên có thể đọc như một bản đồ:

| State hiện tại | Event | Target | Ý nghĩa |
| --- | --- | --- | --- |
| **enterDetails** | **next** | **review** | Chấp nhận dữ liệu và xem lại |
| **enterDetails** | **cancel** | **cancelled** | Hủy, không cần bind form |
| **review** | **back** | **enterDetails** | Quay lại để sửa |
| **review** | **finish** | **completed** | Kết thúc flow |

**enterDetails** là state đầu tiên được khai báo trong flow. **signup** là object Java được tạo cho flow execution; **model="signup"** cho phép binder cập nhật các property đã khai báo. Template **signup/details** và **signup/review** được resolve qua view factory/ViewResolver.

### 4.1. Tạo model Java

~~~java
package com.example.signup;

import java.io.Serializable;

public class SignupDraft implements Serializable {
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

JavaBean giúp binder cập nhật dữ liệu qua postback. Biến flow giữ object theo execution; không đưa object này vào field mutable của singleton service/controller.

### 4.2. Template phát event

Trong file **details.html**:

~~~html
<form method="post" th:action="${flowExecutionUrl}" th:object="${signup}">
    <label for="fullName">Họ tên</label>
    <input id="fullName" type="text" th:field="*{fullName}">

    <label for="email">Email</label>
    <input id="email" type="email" th:field="*{email}">

    <button type="submit" name="_eventId_next">Tiếp tục</button>
    <button type="submit" name="_eventId_cancel" formnovalidate>Hủy</button>
</form>
~~~

Trong file **review.html**:

~~~html
<p>Họ tên: <span th:text="${signup.fullName}"></span></p>
<p>Email: <span th:text="${signup.email}"></span></p>

<form method="post" th:action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_back">Quay lại</button>
    <button type="submit" name="_eventId_finish">Hoàn tất</button>
</form>
~~~

**flowExecutionUrl** giúp gửi request tiếp tục đúng execution hiện tại. Khi Spring Security bật CSRF, form POST phải mang token hợp lệ; tích hợp Thymeleaf/Spring Security có thể chèn token qua request data value processor, hãy kiểm tra HTML được render thực tế.

### 4.3. Từng transition xảy ra ra sao?

1. GET flow start URL: Web Flow tạo execution và vào **enterDetails**.
2. Người dùng nhập form rồi gửi **next**.
3. Web Flow bind các property được cho phép, chạy validation nếu có, rồi xử lý transition **next**.
4. Flow vào **review**, render dữ liệu đã lưu trong object **signup**.
5. Nếu gửi **back**, flow quay về **enterDetails**; nếu gửi **finish**, flow kết thúc ở **completed**.

Đây là flow điều hướng. Nếu **finish** cần ghi database, hãy thêm action/service phù hợp và chỉ kết thúc sau khi service xác nhận thành công.

## 5. Binding và validation được điều khiển theo từng transition

Khi một view-state có thuộc tính **model**, Web Flow thực hiện binding dữ liệu form vào model khi nhận view event. Sau binding, framework chạy validation nếu model/flow có validator phù hợp. Nếu binding hoặc validation thất bại, view hiện tại được render lại để người dùng sửa.

Hai thuộc tính **bind** và **validate** cho phép thay đổi hành vi theo từng event:

| Cấu hình transition | Binding | Validation | Khi nào dùng |
| --- | --- | --- | --- |
| Mặc định | Có | Có | Tiếp tục với dữ liệu vừa nhập |
| `bind="false"` | Không | Không | Hủy form, bỏ qua dữ liệu đang nhập |
| `validate="false"` | Có | Không | Quay lại nhưng vẫn giữ dữ liệu người dùng vừa sửa |

### 5.1. Dùng bind=false cho Hủy

~~~xml
<view-state id="enterDetails" model="signup">
    <transition on="next" to="review"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Người dùng có thể hủy ngay cả khi form còn thiếu field bắt buộc. Transition không bind dữ liệu postback và không chạy validation cho event đó.

### 5.2. Dùng validate=false cho Quay lại

~~~xml
<view-state id="review" model="signup">
    <transition on="back" to="enterDetails" validate="false"/>
    <transition on="finish" to="completed"/>
</view-state>
~~~

Với event **back**, dữ liệu được bind vào model nhưng validation bị bỏ qua. Điều này hữu ích khi người dùng đang ở màn hình sau và muốn quay lại sửa một field chưa hoàn chỉnh. Nếu dùng **bind="false"**, thay đổi mới trong form sẽ không được cập nhật vào model.

### 5.3. Chọn đúng hành vi theo ý nghĩa nút

- **Tiếp tục:** thường cần bind và validate.
- **Quay lại:** thường vẫn muốn giữ thay đổi, nhưng không bắt buộc form phải hợp lệ; cân nhắc validate=false.
- **Hủy:** thường không cần nhận dữ liệu chưa hoàn chỉnh; cân nhắc bind=false.
- **Xem trước/tính thử:** có thể bind, validate theo nhóm field cần thiết, hoặc xử lý bằng validator riêng.

Không dùng bind/validate như cơ chế phân quyền. Chúng chỉ điều khiển lifecycle của model khi xử lý view event.

## 6. Transition action: kiểm tra điều kiện trước khi rời view

Một transition có thể chứa một hoặc nhiều action. Action được thực thi trước khi transition rời state hiện tại. Nếu action trả về kết quả lỗi, Web Flow có thể **giữ người dùng ở view-state hiện tại** để hiển thị thông báo.

Ví dụ, người dùng bấm Xác nhận; service kiểm tra tên đăng ký còn hợp lệ hay không:

~~~xml
<view-state id="review" view="signup/review" model="signup">
    <transition on="back" to="enterDetails" validate="false"/>
    <transition on="finish" to="completed">
        <evaluate expression="signupActions.checkBeforeFinish(signup, messageContext)"/>
    </transition>
</view-state>
~~~

Một POJO action có thể trả boolean:

~~~java
package com.example.signup;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Component;

@Component("signupActions")
public class SignupActions {
    public boolean checkBeforeFinish(
            SignupDraft signup, MessageContext messages) {
        if (signup.getEmail() == null ||
                !signup.getEmail().contains("@")) {
            messages.addMessage(new MessageBuilder()
                .error()
                .source("email")
                .defaultText("Email chưa hợp lệ, hãy quay lại để sửa.")
                .build());
            return false;
        }
        return true;
    }
}
~~~

Với một phương thức Java được gọi trực tiếp từ transition action:

- **true** cho phép transition tiếp tục tới state đích.
- **false** ngăn transition rời view-state; view được render lại và có thể hiển thị message.
- Nếu phương thức trả String, các giá trị **success**, **yes** hoặc **true** cho phép transition; giá trị khác ngăn transition.

Đây là một cách xử lý điều kiện nghiệp vụ nhỏ gắn với event. Khi logic trở nên phức tạp, nên tách vào service và để action làm adapter mỏng.

### 6.1. Phân biệt transition action với action-state

| Đặc điểm | Action trong transition | action-state |
| --- | --- | --- |
| Điểm chạy | Khi event xảy ra ở state hiện tại | Một state riêng trong flow |
| Có view riêng? | Không | Không nhất thiết có view; nó là state xử lý |
| Kết quả | Cho phép/ngăn transition hiện tại | Event kết quả chọn transition tiếp theo |
| Phù hợp | Kiểm tra trước khi rời màn hình | Tính toán hoặc gọi service để quyết định bước kế |

Nếu chỉ cần xác minh form trước khi sang màn hình review, transition action phù hợp. Nếu cần truy vấn trạng thái, quyết định nhánh hoặc chạy một quy trình xử lý độc lập, action-state thường dễ đọc hơn.

### 6.2. Không thực hiện side effect khó lặp mà thiếu idempotency

Một transition action có thể được gọi lại do retry, nhiều request hoặc lịch sử trình duyệt. Nếu action gửi tiền, tạo booking, trừ tồn kho hoặc gửi email, phải bảo vệ thao tác ở service/database bằng transaction và idempotency. Không dựa vào việc nút chỉ xuất hiện một lần trên màn hình.

## 7. Transition không có target: xử lý event tại chỗ

Không phải event nào cũng cần chuyển sang state khác. Một transition **không có thuộc tính to** được dùng như event handler: thực thi action rồi render lại view hiện tại hoặc một phần của view.

Ví dụ người dùng bấm nút Tải thêm để chuyển trang danh sách kết quả nhưng vẫn ở state search:

~~~xml
<view-state id="search" view="catalog/search">
    <on-render>
        <evaluate expression="catalogService.find(searchCriteria)"
                  result="viewScope.results"/>
    </on-render>

    <transition on="nextPage">
        <evaluate expression="searchCriteria.nextPage()"/>
        <render fragments="resultsPanel"/>
    </transition>

    <transition on="previousPage">
        <evaluate expression="searchCriteria.previousPage()"/>
        <render fragments="resultsPanel"/>
    </transition>

    <transition on="select" to="review"/>
</view-state>
~~~

Hai event **nextPage** và **previousPage** không có target. Chúng cập nhật criteria rồi yêu cầu render lại fragment có ID **resultsPanel**; flow vẫn ở state **search**. Event **select** có target nên chuyển sang **review**.

### 7.1. Phân biệt event handler với self-transition

| Cấu hình | Ý nghĩa |
| --- | --- |
| Transition chỉ có **on="refresh"** | Xử lý event trong state hiện tại, không chuyển state |
| **on="next" to="review"** | Chuyển sang state khác |
| **on="retry" to="search"** | Rời state rồi vào lại state search |

Event handler không có target thường phù hợp với Ajax, phân trang hoặc thao tác nhẹ trên cùng màn hình. Nếu cần chạy lại đầy đủ lifecycle khi vào một state, hãy cân nhắc transition có target và tác động của view scope/on-entry/on-render.

### 7.2. Render fragment bằng Ajax

Thẻ **render** tham chiếu ID phần tử trong view cần cập nhật:

~~~html
<section id="resultsPanel">
    <!-- danh sách kết quả -->
</section>
~~~

~~~xml
<transition on="nextPage">
    <evaluate expression="searchCriteria.nextPage()"/>
    <render fragments="resultsPanel"/>
</transition>
~~~

Để hoạt động, view factory và Ajax integration phải hỗ trợ fragment rendering; chỉ thêm thẻ render vào XML không tự biến mọi request thành Ajax. Khi dùng Thymeleaf hoặc một view technology khác, kiểm tra cách adapter nhận diện Ajax request và cách template render fragment.

## 8. Global transitions: event dùng chung trên nhiều view

Nếu nhiều view-state cùng cần xử lý một event, có thể khai báo **global-transitions** ở cấp flow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <global-transitions>
        <transition on="logout" to="logout"/>
        <transition on="help" to="help"/>
    </global-transitions>

    <view-state id="enterDetails" view="signup/details">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="signup/review">
        <transition on="back" to="enterDetails"/>
    </view-state>

    <end-state id="logout"/>
    <end-state id="help"/>
</flow>
~~~

Global transition hữu ích cho menu chung hoặc event điều hướng xuất hiện ở nhiều màn hình. Ví dụ, nút Đăng xuất trong layout có thể phát event **logout** mà không cần lặp một transition ở từng view-state.

### 8.1. Khi nào nên dùng transition cục bộ?

Nếu event có ý nghĩa khác nhau tùy state, hãy khai báo transition cục bộ:

- **cancel** ở màn hình nhập có thể kết thúc toàn flow.
- **cancel** ở màn hình chọn dịch vụ có thể quay về tìm kiếm.
- **cancel** ở màn hình xác nhận có thể quay về chỉnh sửa.

Không đưa một event vào global-transitions chỉ vì tên event giống nhau. Chỉ dùng global khi cùng một hành động có cùng ý nghĩa và target trong toàn flow.

### 8.2. Global transition không thay thế security

Một event **logout** trong flow không tự thay thế Spring Security logout. Nó chỉ là điều hướng trong state machine. Nếu ứng dụng cần xóa authentication, invalidate session, xóa cookie hoặc áp dụng chính sách đăng xuất, hãy cấu hình Spring Security tương ứng và bảo đảm luồng xử lý không giữ dữ liệu nhạy cảm.

## 9. Nối transition tới action-state và decision-state

Transition không chỉ nối một view-state sang view-state khác. Target có thể là một state xử lý hoặc một điểm kết thúc. Khi cần gọi service hay chọn nhánh dựa trên kết quả, hãy tách bước xử lý thành **action-state** hoặc **decision-state**.

### 9.1. Action-state: để kết quả action quyết định bước kế tiếp

Ví dụ sau khi người dùng nhập thông tin, hệ thống kiểm tra điều kiện tham gia:

~~~xml
<view-state id="enterDetails" view="signup/details" model="signup">
    <transition on="next" to="checkEligibility"/>
</view-state>

<action-state id="checkEligibility">
    <evaluate expression="signupPolicy.isEligible(signup)"/>
    <transition on="yes" to="review"/>
    <transition on="no" to="notEligible"/>
</action-state>

<view-state id="review" view="signup/review"/>
<view-state id="notEligible" view="signup/not-eligible"/>
~~~

Action trả boolean; Web Flow ánh xạ **true** thành event **yes** và **false** thành event **no**. Với phương thức trả String, giá trị String trở thành event ID; ví dụ **approved** hoặc **rejected**. Từ action-state, flow chọn transition có event khớp kết quả.

Một số mapping thường gặp:

| Kiểu trả về từ action | Event ID |
| --- | --- |
| String | Chính chuỗi được trả về |
| Boolean true/false | **yes** / **no** |
| Enum | Tên enum |
| Kiểu khác | **success** |

### 9.2. Decision-state: rẽ nhánh theo điều kiện

Nếu chỉ cần một phép if/else, decision-state thường ngắn gọn hơn:

~~~xml
<decision-state id="routeByType">
    <if test="signup.businessAccount"
        then="businessReview"
        else="personalReview"/>
</decision-state>
~~~

Flow có thể đi tới decision-state từ một transition:

~~~xml
<view-state id="enterDetails" view="signup/details" model="signup">
    <transition on="next" to="routeByType"/>
</view-state>
~~~

Decision-state không nhận event từ một nút; nó đánh giá điều kiện và chọn target. Dùng action-state khi cần gọi hành động có kết quả; dùng decision-state cho routing logic đơn giản.

### 9.3. Chọn đúng loại state đích

| Target | Dùng khi | Transition tiếp theo dựa trên |
| --- | --- | --- |
| view-state | Cần hiển thị màn hình | Event từ người dùng |
| action-state | Cần thực hiện một action | Event kết quả action |
| decision-state | Cần rẽ nhánh điều kiện | Biểu thức if/else |
| subflow-state | Gọi một flow con | Outcome của subflow |
| end-state | Kết thúc flow | Không còn bước tiếp trong flow đó |

Đặt tên state theo hành động/nhiệm vụ, chẳng hạn **checkEligibility**, **loadQuote**, **commitBooking**. Tên rõ ràng giúp đọc sơ đồ flow mà không phải mở từng Java method.

## 10. Nối sang subflow-state

Khi một phần quy trình có thể tái sử dụng, flow cha có thể gọi flow con bằng **subflow-state**. Transition của subflow-state thường được chọn theo outcome mà flow con trả về khi đi tới end-state.

Ví dụ flow cha gọi flow nhập địa chỉ:

~~~xml
<view-state id="enterDetails" view="signup/details">
    <transition on="next" to="collectAddress"/>
</view-state>

<subflow-state id="collectAddress" subflow="address">
    <input name="customerName" value="signup.fullName"/>
    <transition on="completed" to="review"/>
    <transition on="cancelled" to="enterDetails"/>
</subflow-state>

<view-state id="review" view="signup/review"/>
~~~

Flow con có thể kết thúc bằng các end-state mang ID **completed** hoặc **cancelled**. Outcome tương ứng trở thành event để flow cha chọn transition. Hợp đồng input/output cần được định nghĩa rõ; ví dụ trên truyền tên khách hàng vào flow con nhưng chưa minh họa output.

**Đừng nhầm state ID của flow cha với outcome của flow con.** Transition **on="completed"** trong subflow-state phản ứng với outcome mà flow con trả về; nó không phải event từ một nút HTML trong flow cha.

## 11. Browser history và history policy của transition

Theo mặc định, khi flow rời một view-state và đi tới view-state khác, người dùng có thể dùng nút Back của trình duyệt để quay lại view trước trong phạm vi history/snapshot còn được giữ. Có thể điều chỉnh chính sách theo từng transition bằng thuộc tính **history**.

| Giá trị | Tác động |
| --- | --- |
| Mặc định | Cho phép quay lại view trước theo history của flow |
| **history="discard"** | Không cho quay lại view vừa rời |
| **history="invalidate"** | Không cho quay lại view đó và các view đã hiển thị trước đó |

### 11.1. Discard history

~~~xml
<view-state id="review" view="signup/review">
    <transition on="cancel"
                to="cancelled"
                history="discard"/>
</view-state>
~~~

Ví dụ này loại view review khỏi khả năng backtracking theo policy của transition. Nó phù hợp với một số bước mà việc quay lại không còn ý nghĩa.

### 11.2. Invalidate history

~~~xml
<view-state id="review" view="signup/review">
    <transition on="confirm"
                to="completed"
                history="invalidate"/>
</view-state>
~~~

Invalidate ngăn quay lại view hiện tại cũng như các view đã hiển thị trước đó. Có thể cân nhắc sau một bước xác nhận cuối, nhưng **history policy không phải transaction rollback hay bảo mật dữ liệu**. Nếu booking đã commit, service vẫn phải ngăn việc xác nhận lại và xử lý request lặp.

### 11.3. Back button của trình duyệt khác event back

- Nút **Quay lại** trong form gửi event **back** và chạy transition XML đã khai báo.
- Nút **Back của trình duyệt** điều hướng theo browser history và flow snapshot.
- Hai hành vi có thể khác nhau; cần kiểm thử cả hai.

Không giả định mọi URL lịch sử còn tồn tại vô thời hạn. Session timeout, giới hạn snapshot hoặc execution đã kết thúc có thể khiến URL cũ không còn dùng được.

## 12. Thứ tự xử lý một view event

Khi view-state có model nhận một event, có thể hình dung luồng xử lý tổng quát như sau:

~~~mermaid
flowchart TD
    A["HTTP request chứa event ID"] --> B["Web Flow xác định state hiện tại"]
    B --> C["Tìm transition khớp event"]
    C --> D{"Transition có bind=false?"}
    D -->|"Không"| E["Bind request values vào model"]
    D -->|"Có"| H["Bỏ qua binding và validation"]
    E --> F{"Validation được bật?"}
    F -->|"Có"| G["Chạy validation"]
    F -->|"Không"| I["Bỏ qua validation"]
    G --> J{"Có lỗi binding/validation?"}
    J -->|"Có"| K["Render lại view hiện tại"]
    J -->|"Không"| L["Chạy transition actions"]
    I --> L
    H --> L
    L --> M{"Action cho phép transition?"}
    M -->|"Không"| K
    M -->|"Có"| N{"Có target state?"}
    N -->|"Có"| O["Rời state và vào target"]
    N -->|"Không"| P["Giữ state, render lại view/fragment"]
~~~

Đây là mô hình tổng quát để hiểu lifecycle, không thay thế chi tiết của từng view technology hoặc custom action. Các điểm cần nhớ:

1. Event phải được giải mã và khớp transition của state hiện tại.
2. Nếu transition cho phép binding, request values được bind vào model.
3. Validation được thực hiện nếu được bật và có validator tương ứng.
4. Transition actions có thể ngăn việc rời state nếu trả kết quả lỗi.
5. Có target thì chuyển state; không có target thì xử lý event tại view hiện tại.

### 12.1. Lỗi binding khác lỗi transition

Nếu người dùng nhập chữ vào một property số, binding/conversion có thể thất bại trước khi transition được thực thi. View hiện tại được render lại với lỗi. Ngược lại, nếu event không có transition tương ứng, đây là vấn đề event/state definition chứ không phải lỗi conversion.

### 12.2. Lỗi action khác lỗi validation

Validation kiểm tra model trước khi chuyển bước; transition action có thể gọi service hoặc kiểm tra một điều kiện bổ sung. Nếu service báo hết chỗ, action có thể thêm message và trả false để giữ người dùng ở view hiện tại. Không biến mọi exception kỹ thuật thành lỗi validation; phân loại lỗi để phục hồi phù hợp.

## 13. Những lỗi thường gặp khi nối các bước

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Bấm Tiếp tục nhưng không rời view | Tên event không khớp thuộc tính on | So sánh tên button với transition |
| Flow báo không có transition phù hợp | Event được gửi ở state không khai báo event đó | Xem state hiện tại và các transition con |
| Flow không khởi tạo | Thuộc tính to tham chiếu state ID sai hoặc XML không hợp lệ | Kiểm tra ID, schema và log khởi động |
| Bấm Hủy nhưng vẫn báo thiếu field | Transition chưa đặt bind=false hoặc button bị HTML validation chặn | Kiểm tra binder, bind và formnovalidate |
| Quay lại nhưng dữ liệu bị mất | Transition dùng bind=false hoặc view không bind lại cùng model | Kiểm tra model, flow variable và bind |
| Quay lại vẫn bị lỗi validation | Transition chưa đặt validate=false | Kiểm tra validate và validator |
| Action trả false nhưng flow vẫn đi tiếp | Method không trả kiểu/giá trị được Web Flow diễn giải như mong muốn | Kiểm tra chữ ký và kết quả thực tế |
| Action trả String nhưng không khớp transition | Event outcome không có transition tương ứng | Kiểm tra String/enum result mapping |
| Global event không hoạt động | Chưa khai báo global-transitions hoặc target sai | Kiểm tra flow-level definition |
| Ajax event reload cả trang | Request không được nhận diện là Ajax hoặc view factory không hỗ trợ fragment | Kiểm tra Ajax handler và fragment ID |
| Browser Back quay lại bước đã xác nhận | History policy vẫn cho phép backtracking | Xem history discard/invalidate |
| Event từ nút cũ được gửi ở state mới | Tab/history đang giữ URL hoặc snapshot cũ | Kiểm tra execution URL và repository |
| Event finish có thể gửi nhiều lần | Side effect không idempotent | Kiểm tra service/database |
| Validation lỗi nhưng không thấy message | View không render MessageContext/BindingResult | Kiểm tra message source và template |

### 13.1. Chẩn đoán theo thứ tự

Khi một transition không chạy, hãy kiểm tra:

1. **State hiện tại:** flow đang ở state nào? Đừng chỉ nhìn màn hình vì hai state có thể dùng chung một template.
2. **Event gửi lên:** request có tham số đúng như _eventId_next hoặc _eventId không?
3. **Transition matching:** state hiện tại có transition với đúng event ID không?
4. **Binding/validation:** model binding hoặc validator có lỗi khiến view được render lại không?
5. **Transition action:** action có trả false hoặc một outcome không cho phép rời state không?
6. **Target:** state ID đích có tồn tại và đúng chính tả không?
7. **Render:** target state đã vào nhưng view resolver không tìm được template hay chưa?

Nếu log cho thấy state đã đổi nhưng giao diện vẫn lỗi, tập trung vào view resolution. Nếu state không đổi, kiểm tra event, binding, validation và action trước.

### 13.2. Không dùng event name làm dữ liệu nghiệp vụ

Event ID nên là những tên ổn định như **next**, **back**, **confirm**, **cancel**. Không gửi một chuỗi tùy ý từ người dùng làm event ID hoặc tên state đích. Các giá trị này là một phần giao thức điều hướng giữa view và flow definition, không phải dữ liệu đầu vào tự do.

## 14. Kiểm thử transition với Spring Web Flow

Spring Web Flow cung cấp lớp hỗ trợ test cho flow XML, chẳng hạn **AbstractXmlFlowExecutionTests**. Bạn có thể kiểm tra state hiện tại sau khi bắt đầu flow và sau khi gửi event, đồng thời đăng ký stub/mock cho các bean mà flow gọi.

### 14.1. Kiểm tra flow khởi động

Một test class có thể chỉ định file flow cần kiểm tra:

~~~java
public class SignupFlowExecutionTests
        extends AbstractXmlFlowExecutionTests {

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createFileResource(
            "src/main/resources/flows/signup/signup-flow.xml");
    }

    public void testStartFlow() {
        MockExternalContext context = new MockExternalContext();
        startFlow(context);

        assertCurrentStateEquals("enterDetails");
    }
}
~~~

Đây là khung test theo API test của Web Flow. Bổ sung import, test runner và cấu hình build phù hợp phiên bản đang dùng. Nếu flow có bean action bên ngoài, override **configureFlowBuilderContext** để đăng ký stub/mock cho bean đó.

### 14.2. Kiểm tra event handling

Test event có thể thiết lập state cần kiểm tra, chuẩn bị model trong flow scope, gửi event qua MockExternalContext rồi xác nhận state đích:

~~~java
public void testBackFromReview() {
    setCurrentState("review");

    MockExternalContext context = new MockExternalContext();
    context.setEventId("back");
    resumeFlow(context);

    assertCurrentStateEquals("enterDetails");
}

public void testFinishFromReview() {
    setCurrentState("review");

    MockExternalContext context = new MockExternalContext();
    context.setEventId("finish");
    resumeFlow(context);

    assertFlowExecutionEnded();
    assertFlowExecutionOutcomeEquals("completed");
}
~~~

Các method test trên giả định test harness đã khởi tạo execution và flow variables cần thiết. Với transition có model binding/required fields, hãy thêm request parameters và model fixture tương ứng; nếu không, test có thể thất bại ở binding trước khi transition được thực thi.

### 14.3. Ma trận test đường đi

| ID | State ban đầu | Event | Kết quả cần xác minh |
| --- | --- | --- | --- |
| TR01 | Chưa chạy | Start flow | Vào state đầu tiên |
| TR02 | enterDetails | next | Sang review |
| TR03 | enterDetails | cancel | Kết thúc cancelled |
| TR04 | review | back | Trở về enterDetails |
| TR05 | review | finish | Kết thúc completed |
| TR06 | enterDetails | finish | Không bỏ qua review |
| TR07 | enterDetails | Event không khai báo | Không chuyển state ngoài ý muốn |
| TR08 | enterDetails | next với field thiếu | Binding/validation giữ view nếu field bắt buộc |
| TR09 | enterDetails | cancel khi form thiếu field | Hủy vẫn đi được nếu bind=false |
| TR10 | review | back với model chưa hợp lệ | Vẫn quay lại nếu validate=false |
| TR11 | review | finish, transition action trả true | Được phép tới completed |
| TR12 | review | finish, transition action trả false | Ở lại review và có thông báo |
| TR13 | search | nextPage | Giữ state search, cập nhật fragment |
| TR14 | Nhiều view-state | logout | Global transition chạy đúng |
| TR15 | checkEligibility | Outcome yes | Đi tới nhánh yes |
| TR16 | checkEligibility | Outcome no | Đi tới nhánh no |
| TR17 | collectAddress | Subflow completed | Flow cha đi tới review |
| TR18 | review | Browser Back sau invalidate | Không quay lại history đã bị vô hiệu |
| TR19 | review | Hai request confirm gần nhau | Service không tạo nghiệp vụ trùng |
| TR20 | State bất kỳ | Target ID sai trong XML | Flow definition test phát hiện lỗi |

### 14.4. Flow test chưa thay thế HTTP integration test

Flow test kiểm tra state machine và event handling. Để xác nhận HTML thực sự gửi đúng event, cần thêm MVC/HTTP integration test:

- GET start URL và xác nhận trang đầu được render.
- Kiểm tra form action là execution URL đúng.
- Kiểm tra named button tạo đúng tham số event.
- POST qua CSRF filter nếu ứng dụng bật Spring Security.
- Kiểm tra redirect/render và thông báo lỗi thực tế.
- Thử browser Back, refresh và execution key hết hạn.

## 15. Bài tập thực hành

### Bài A — thêm nhánh quay lại

Flow có hai state **enterDetails** và **review**. Thêm nút Quay lại trong template review, phát event **back**, khai báo transition về enterDetails. Kiểm tra dữ liệu vừa sửa được giữ lại và validation không chặn đường quay lại.

**Đạt khi:** event và target khớp, model giữ dữ liệu, test xác nhận state trở về.

### Bài B — thêm nhánh hủy

Thêm nút Hủy trên màn hình nhập. Khai báo transition tới end-state cancelled với bind=false. Thử hủy khi mọi field đều trống.

**Đạt khi:** request hủy không bị required binding/validation ngăn lại.

### Bài C — kiểm tra điều kiện trước khi hoàn tất

Thêm transition action cho event finish. Nếu email không hợp lệ, ghi lỗi vào MessageContext và trả false; nếu hợp lệ, trả true.

**Đạt khi:** action lỗi giữ người dùng ở review; action thành công mới chuyển sang completed.

### Bài D — dùng action-state để phân nhánh

Thêm state checkEligibility. Action trả true/false theo loại tài khoản, khai báo transition yes/no tới hai view khác nhau. Thử cả hai trường hợp.

**Đạt khi:** test chứng minh outcome của action quyết định target.

### Bài E — thêm global transition

Thêm menu Đăng xuất ở mọi view và một global transition logout. Tích hợp Spring Security logout thật nếu ứng dụng có xác thực; không chỉ kết thúc flow rồi coi người dùng đã đăng xuất.

**Đạt khi:** event được nhận từ nhiều view và security session được xử lý theo policy.

### Bài F — thêm event handler Ajax

Ở view tìm kiếm, thêm nút Tải thêm. Transition không có target gọi nextPage và render fragment kết quả. Thử bằng request Ajax và xác minh state không đổi.

**Đạt khi:** chỉ vùng kết quả được cập nhật và flow vẫn ở state search.

### Bài G — kiểm soát browser history

Thêm history=discard cho nhánh hủy và history=invalidate cho nhánh xác nhận cuối. Thử browser Back và ghi nhận khác biệt.

**Đạt khi:** hiểu history policy chỉ điều khiển khả năng quay lại của flow, không hoàn tác database.

## 16. Checklist trước khi hoàn thành flow

- [ ] Mỗi view-state có danh sách event được hỗ trợ rõ ràng.
- [ ] Tên event trong form khớp thuộc tính on của transition.
- [ ] Mỗi target state tồn tại và đúng ID.
- [ ] Nút Tiếp tục bind/validate dữ liệu cần thiết.
- [ ] Nút Quay lại giữ dữ liệu nhưng không bắt buộc validation nếu đó là chủ đích.
- [ ] Nút Hủy không bị binding/validation chặn khi form chưa hoàn chỉnh.
- [ ] Transition action xử lý kết quả lỗi rõ ràng và ghi message phù hợp.
- [ ] Action có side effect được bảo vệ bằng transaction/idempotency.
- [ ] Event handler không target chỉ được dùng khi muốn giữ nguyên state.
- [ ] Fragment ID khớp template và Ajax integration đã cấu hình.
- [ ] Global transition chỉ chứa hành vi thực sự dùng chung.
- [ ] Action-state/decision-state được chọn đúng mục đích.
- [ ] Subflow outcome khớp transition của flow cha.
- [ ] History policy phù hợp với bước có thể quay lại.
- [ ] Đã test từng event, nhánh lỗi và target state.
- [ ] Đã kiểm thử request thật, CSRF và browser history.

## 17. Câu hỏi tự kiểm tra

**1. Event và transition khác nhau thế nào?** Event là tín hiệu được gửi tới flow; transition là quy tắc trong state hiện tại phản hồi tín hiệu đó.

**2. Vì sao cùng event next có thể hoạt động ở state này nhưng không ở state khác?** Vì transition được khai báo theo từng state; event chỉ khớp transition mà state hiện tại có.

**3. bind=false khác validate=false thế nào?** bind=false bỏ cả binding và validation; validate=false vẫn bind dữ liệu nhưng bỏ validation.

**4. Khi transition action trả false thì sao?** Transition bị ngăn, view-state hiện tại được render lại để hiển thị message hoặc cho người dùng thử lại.

**5. Transition không có to dùng khi nào?** Khi muốn xử lý event và render lại view hiện tại hoặc fragment mà không chuyển state.

**6. Global transition phù hợp với event nào?** Event có cùng ý nghĩa và target ở nhiều view, chẳng hạn một menu dùng chung.

**7. Action-state khác decision-state ở đâu?** Action-state thực thi action và chọn transition theo outcome; decision-state đánh giá điều kiện if/else để chọn target.

**8. Subflow-state chọn transition theo điều gì?** Theo outcome mà flow con trả về khi kết thúc.

**9. history=invalidate có xóa dữ liệu database không?** Không. Nó chỉ vô hiệu khả năng quay lại các view trong history của flow.

**10. PRG có bảo đảm action không chạy hai lần không?** Không. Service/database vẫn cần idempotency và transaction cho request lặp hoặc đồng thời.

## 18. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 Reference Guide — Defining Flows](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — flow, view-state, transition và end-state.
2. [Spring Web Flow 3.0.2 Reference Guide — Binding and Validation](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — model binding, bind/validate, binder và validation lifecycle.
3. [Spring Web Flow 3.0.2 Reference Guide — Defining View Transitions](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — transition actions, global transitions, event handlers và fragment rendering.
4. [Spring Web Flow 3.0.2 Reference Guide — Executing Actions](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — action-state, decision-state và action outcome mapping.
5. [Spring Web Flow 3.0.2 Reference Guide — View Backtracking](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — history discard và invalidate.
6. [Spring Web Flow 3.0.2 Reference Guide — Testing Flows](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — AbstractXmlFlowExecutionTests và kiểm thử event handling.

**Điểm cần nhớ:** Transition nối các state bằng cách ánh xạ **event hiện tại → hành động/target state**. Chọn đúng cách gửi event, binding/validation và action result sẽ giúp flow đi đúng nhánh; event handler, global transition, action-state, decision-state và subflow mở rộng khả năng điều hướng. Khi flow có side effect, history policy và transition chỉ điều khiển hành trình; service/database vẫn phải bảo vệ tính đúng đắn của nghiệp vụ.
