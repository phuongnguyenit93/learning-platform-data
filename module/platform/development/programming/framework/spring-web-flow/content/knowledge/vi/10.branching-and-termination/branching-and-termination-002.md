# Nhánh `then`, `else` và yêu cầu bao phủ các kết quả trong Spring Web Flow

Một flow đăng ký có thể đưa người dùng sang trang xác nhận nếu hồ sơ đạt điều kiện và sang trang chỉnh sửa nếu chưa đạt. Với **Spring Web Flow (SWF)**, quyết định này thường được khai báo trong `decision-state` bằng `<if test="..." then="..." else="..."/>`. Việc viết đủ hai nhánh có ý nghĩa lớn hơn một câu lệnh điều kiện: mỗi kết quả kiểm tra phải dẫn tới **state đích hợp lệ**, đồng thời các tình huống dữ liệu thiếu, lỗi hệ thống và kết quả nghiệp vụ nhiều hơn hai loại phải có cách xử lý rõ ràng.

Bài học thuộc chương **Rẽ nhánh và kết thúc**, tập trung vào ý nghĩa của `then` và `else`, yêu cầu bao phủ kết quả, cách nối các quyết định thành hành trình web nhiều bước, và phương pháp kiểm thử. Các ví dụ sử dụng SWF kết hợp Spring MVC, form binding, validation, flow scope và end-state; không yêu cầu viết logic điều hướng phân tán trong từng controller.

## 1. Hai nhánh của `<if>` hoạt động như thế nào?

Một `decision-state` là state điều khiển: khi flow đi vào state này, SWF đánh giá biểu thức trong thuộc tính `test` rồi chuyển ngay tới một state đích. Nó **không hiển thị giao diện** và không đợi người dùng phát thêm event.

~~~xml
<decision-state id="checkAge">
    <if test="flowScope.application.age ge 18"
        then="reviewApplication"
        else="ageRestriction" />
</decision-state>
~~~

Trong ví dụ:

| Thuộc tính | Vai trò | Giá trị mẫu |
|---|---|---|
| `id` của `decision-state` | Định danh bước kiểm tra | `checkAge` |
| `test` | Biểu thức điều kiện, kỳ vọng cho kết quả Boolean | `flowScope.application.age ge 18` |
| `then` | ID state đích khi `test` trả về `true` | `reviewApplication` |
| `else` | ID state đích khi `test` trả về `false` | `ageRestriction` |

Ở đây, `ge` tương đương “greater than or equal” (lớn hơn hoặc bằng) trong cách viết biểu thức SpEL. Dùng toán tử dạng từ cũng giúp tránh phải escape ký tự so sánh trong XML.

Đọc cấu hình thành câu: *Khi flow đến `checkAge`, nếu tuổi từ 18 trở lên thì sang `reviewApplication`, nếu thấp hơn thì sang `ageRestriction`.*

### 1.1. Bảng kết quả bắt buộc xem xét

| Kết quả thực tế khi đánh giá `test` | Cách xử lý dự kiến |
|---|---|
| `true` | Chuyển tới state được khai báo trong `then` |
| `false` | Chuyển tới state được khai báo trong `else` |
| Dữ liệu đầu vào bị thiếu hoặc không hợp lệ | Chặn ở bước binding/validation, hoặc xác định rõ điều kiện sẽ trả `false` |
| Biểu thức truy cập giá trị `null` không an toàn | Có thể phát sinh lỗi đánh giá biểu thức; cần sửa guard/model |
| Service trong `test` ném exception | Đi theo cơ chế xử lý exception; **không mặc nhiên sang `else`** |
| Kết quả nghiệp vụ có ba trạng thái trở lên | Không được âm thầm gộp các trạng thái khác nhau vào cùng một nhánh Boolean nếu hậu quả khác nhau |

**Bao phủ kết quả** ở đây có hai tầng. Ở tầng điều hướng, cả `true` lẫn `false` phải dẫn tới đường đi có chủ đích. Ở tầng nghiệp vụ, hệ thống phải quyết định rõ phải làm gì với dữ liệu thiếu, điều kiện bất thường và những kết quả không thể mô tả bằng một cặp đúng/sai.

### 1.2. `then` và `else` tham chiếu state, không trả về dữ liệu

Hai thuộc tính này chứa **state ID**, không phải URL, tên view tùy ý hay dữ liệu form:

~~~xml
<decision-state id="checkRegion">
    <if test="regionPolicyService.isSupported(flowScope.form.region)"
        then="choosePlan"
        else="unsupportedRegion" />
</decision-state>

<view-state id="choosePlan" view="signup/choose-plan" />
<view-state id="unsupportedRegion" view="signup/unsupported-region" />
~~~

Cả `choosePlan` và `unsupportedRegion` đều phải được định nghĩa trong flow thích hợp. Nếu đích không tồn tại, định nghĩa flow có thể bị từ chối khi xây dựng hoặc không thực thi như dự tính; đừng xem tên đích là một đường dẫn mà framework sẽ tự tạo.

Giá trị của `then`, `else` không đồng nghĩa “thành công” và “thất bại” nói chung. Chúng chỉ là kết quả Boolean của **điều kiện cụ thể**. Ví dụ, `test="application.needsReview"` đúng có thể phải đến màn hình chờ xét duyệt, dù chưa phải nghiệp vụ đã hoàn tất.

## 2. Bao phủ nhánh và bao phủ hành trình khác nhau ra sao?

Bản thân đoạn `<if>` rất ngắn, nhưng hai đường đi của flow có thể khác nhau đáng kể:

~~~mermaid
flowchart TD
    A["Nhập hồ sơ (view-state)"] -->|"next"| B{"checkEligibility (decision-state)"}
    B -->|"test = true / then"| C["reviewApplication (view-state)"]
    B -->|"test = false / else"| D["notEligible (view-state)"]
    C -->|"confirm"| E["submitApplication (action-state)"]
    E -->|"success"| F(["completed (end-state)"])
    E -->|"failure"| G["submissionError (view-state)"]
    D -->|"edit"| A
    G -->|"retry"| E
~~~

Một bài test chỉ đi qua `then` chưa chứng minh luồng đúng. Với nhánh `else`, người dùng có thể cần được giải thích lý do và có nút quay lại. Sau nhánh `then`, hành động lưu hồ sơ vẫn có thể thất bại và cần một hướng phục hồi riêng.

Có thể đặt ra ba yêu cầu kiểm tra:

1. **Bao phủ Boolean:** tạo được dữ liệu khiến `test` trả cả `true` và `false`.
2. **Bao phủ điều hướng:** mỗi kết quả chuyển tới **đúng state**, không mắc vòng lặp tự động hay đến view thiếu cấu hình.
3. **Bao phủ vòng đời:** các đường đi hợp lệ có cách tiếp tục, quay lại, hủy hoặc kết thúc phù hợp; các lỗi thực thi được xử lý theo chính sách riêng.

Trong thiết kế, nên lập bảng kết quả trước khi viết XML:

| State quyết định | Điều kiện | `then` | `else` | Hành động sau khi chọn nhánh |
|---|---|---|---|---|
| `checkAge` | Tuổi đủ 18? | `reviewApplication` | `ageRestriction` | Review hoặc giải thích điều kiện độ tuổi |
| `checkCountry` | Có hỗ trợ quốc gia? | `checkMinimum` | `unsupportedCountry` | Kiểm tra tiếp hoặc cho sửa địa chỉ |
| `checkMinimum` | Đơn đạt giá trị tối thiểu? | `reviewOrder` | `belowMinimum` | Xác nhận hoặc sửa giỏ hàng |
| `checkConsent` | Đã chấp thuận điều khoản? | `submitApplication` | `requestConsent` | Ghi hồ sơ hoặc yêu cầu xác nhận |

**Đừng chỉ nhìn tên nhánh:** một state `ageRestriction` là kết quả kiểm tra “không đủ tuổi”, chưa chắc phải là `end-state`. Tùy nghiệp vụ, ứng dụng có thể cho người dùng sửa ngày sinh hoặc phải dừng hành trình.

## 3. Cần khai báo rõ `else` khi thiết kế điều hướng

Trong ví dụ dạy học và cấu hình thực tế, nên khai báo **cả `then` và `else`** cho mỗi phép kiểm tra có hai khả năng. Như vậy người bảo trì nhìn định nghĩa flow sẽ biết hệ thống làm gì khi điều kiện sai.

~~~xml
<decision-state id="hasItems">
    <if test="flowScope.cart.itemCount gt 0"
        then="reviewCart"
        else="emptyCart" />
</decision-state>
~~~

Giả sử mới chỉ nghĩ đến giỏ hàng có sản phẩm mà bỏ qua trường hợp rỗng, flow sẽ thiếu đường xử lý nghiệp vụ quan trọng. Tùy ràng buộc schema/phiên bản, thiếu nhánh cần thiết có thể dẫn tới lỗi cấu hình hoặc không có transition thích hợp. Không dựa vào một “default” ngầm định khi thiết kế flow.

**Hai trạng thái đích phải có ý nghĩa rõ ràng.** Ví dụ, cùng trỏ `then` và `else` tới `reviewCart` thường là dấu hiệu điều kiện thừa. Nếu cả hai kết quả thực sự dẫn tới một bước, có thể bỏ decision-state và chuyển trực tiếp tới bước đó.

### 3.1. Không biến dữ liệu không hợp lệ thành `else` một cách tùy tiện

Kiểm tra sau đây dễ gây hiểu nhầm nếu model chưa khởi tạo đầy đủ:

~~~xml
<if test="flowScope.application.customer.age ge 18"
    then="adultReview"
    else="ageRestriction" />
~~~

Nếu `application`, `customer` hoặc `age` không có giá trị, hệ thống có thể lỗi đánh giá hoặc không thể so sánh chính xác. Đó là vấn đề **dữ liệu thiếu**, không đương nhiên là kết luận “không đủ tuổi”.

Có hai cách thiết kế thường dùng:

**Cách A — validation trước khi quyết định.** Ở `view-state`, binding model và áp dụng validator để yêu cầu trường tuổi hợp lệ. Khi transition `next` được thực thi, decision-state có thể tin rằng model đã thỏa các tiền điều kiện được xác minh.

~~~xml
<view-state id="enterDetails"
            view="application/enter-details"
            model="application">
    <transition on="next" to="checkAge"
                bind="true" validate="true" />
    <transition on="cancel" to="cancelled"
                bind="false" />
</view-state>
~~~

**Cách B — guard với điều kiện có chủ đích.** Nếu model có thể xuất hiện không đầy đủ qua nhiều nguồn, có thể kiểm tra null trước khi truy cập trường tiếp theo:

~~~xml
<decision-state id="hasAgeInformation">
    <if test="flowScope.application != null and
              flowScope.application.customer != null and
              flowScope.application.customer.age != null"
        then="checkAge"
        else="completePersonalInformation" />
</decision-state>
~~~

Với SpEL, toán tử `and` đánh giá ngắn mạch, nên mỗi biểu thức phía sau chỉ được xét khi những điều kiện trước đáp ứng. Nhánh `else` ở đây có nghĩa **thiếu dữ liệu tuổi**, không phải **dưới 18 tuổi**. Hai trường hợp được tách thành hai quyết định có thông điệp và đường xử lý khác nhau.

## 4. Ví dụ tự chứa: chọn luồng đăng ký theo loại tài khoản

Giả sử ứng dụng có màn hình nhập thông tin đăng ký với model `com.example.signup.RegistrationForm`. Form chứa `accountType` (giá trị `PERSONAL` hoặc `BUSINESS`) và `countryCode`. Với tài khoản doanh nghiệp, hệ thống chỉ nhận quốc gia nằm trong danh sách hỗ trợ.

Yêu cầu điều hướng:

- Người dùng chọn `PERSONAL` thì tới màn hình xem lại tài khoản cá nhân.
- Người dùng chọn `BUSINESS` thì kiểm tra quốc gia trước khi tới màn hình xem lại doanh nghiệp.
- Quốc gia không hỗ trợ phải đưa tới trang giải thích và cho sửa.
- Mọi loại tài khoản khác `PERSONAL` hoặc `BUSINESS` phải bị chặn bởi validation **hoặc** được xử lý như dữ liệu không hợp lệ, thay vì tự động coi là doanh nghiệp.
- Người dùng có quyền quay lại hoặc hủy; chỉ kết thúc flow sau thao tác hủy hay gửi đăng ký thành công.

### 4.1. Sơ đồ kết quả

~~~mermaid
flowchart TD
    A["enterRegistration"] -->|"next hợp lệ"| B{"checkAccountType"}
    B -->|"PERSONAL"| C["reviewPersonal"]
    B -->|"khác PERSONAL"| D{"checkBusinessType"}
    D -->|"BUSINESS"| E{"checkBusinessRegion"}
    D -->|"khác BUSINESS"| X["invalidAccountType"]
    E -->|"được hỗ trợ"| F["reviewBusiness"]
    E -->|"không hỗ trợ"| G["unsupportedCountry"]
    C -->|"confirm"| H["persistRegistration"]
    F -->|"confirm"| H
    H -->|"success"| I(["completed"])
    H -->|"duplicate"| J["duplicateRegistration"]
    H -->|"failure"| K["saveError"]
    G -->|"edit"| A
    X -->|"edit"| A
    J -->|"edit"| A
    K -->|"back"| A
    A -->|"cancel"| L(["cancelled"])
~~~

Ở đây, một kết quả sai từ `checkAccountType` không đủ để khẳng định người dùng chọn `BUSINESS`. Vì thế cần bước `checkBusinessType` nhằm tránh lẫn giá trị không hợp lệ với một loại hợp lệ khác.

### 4.2. Định nghĩa flow XML

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow-2.0.xsd">

    <!-- Model dùng xuyên suốt nhiều bước của flow. -->
    <var name="registration"
         class="com.example.signup.RegistrationForm" />

    <view-state id="enterRegistration"
                view="signup/enter-registration"
                model="registration">
        <transition on="next" to="checkAccountType"
                    bind="true" validate="true" />
        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>

    <decision-state id="checkAccountType">
        <if test="flowScope.registration.accountType == 'PERSONAL'"
            then="reviewPersonal"
            else="checkBusinessType" />
    </decision-state>

    <decision-state id="checkBusinessType">
        <if test="flowScope.registration.accountType == 'BUSINESS'"
            then="checkBusinessRegion"
            else="invalidAccountType" />
    </decision-state>

    <decision-state id="checkBusinessRegion">
        <if test="regionPolicyService.isSupported(
                      flowScope.registration.countryCode)"
            then="reviewBusiness"
            else="unsupportedCountry" />
    </decision-state>

    <view-state id="reviewPersonal"
                view="signup/review-personal">
        <transition on="back" to="enterRegistration" />
        <transition on="confirm" to="persistRegistration" />
    </view-state>

    <view-state id="reviewBusiness"
                view="signup/review-business">
        <transition on="back" to="enterRegistration" />
        <transition on="confirm" to="persistRegistration" />
    </view-state>

    <view-state id="invalidAccountType"
                view="signup/invalid-account-type">
        <transition on="edit" to="enterRegistration" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="unsupportedCountry"
                view="signup/unsupported-country">
        <transition on="edit" to="enterRegistration" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <action-state id="persistRegistration">
        <evaluate expression="registrationService.save(
                                  flowScope.registration)" />
        <transition on="success" to="completed" />
        <transition on="duplicate" to="duplicateRegistration" />
        <transition on="failure" to="saveError" />
    </action-state>

    <view-state id="duplicateRegistration"
                view="signup/duplicate">
        <transition on="edit" to="enterRegistration" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="saveError" view="signup/save-error">
        <transition on="back" to="enterRegistration" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <end-state id="completed" view="signup/completed" />
    <end-state id="cancelled" />
</flow>
~~~

**Điều kiện để ví dụ chạy:** dự án phải cung cấp các view template, Java model, validator, `regionPolicyService` và `registrationService`; phải đăng ký flow trong `FlowDefinitionRegistry` cùng `FlowExecutor`, `FlowHandlerMapping` và `FlowHandlerAdapter` khi tích hợp với Spring MVC. Đoạn XML mô tả logic điều hướng, không tự khai báo những bean bên ngoài.

Để các transition trong `persistRegistration` hoạt động như minh họa, `registrationService.save(...)` cần trả về một outcome mà SWF chuyển thành event ID `success`, `duplicate` hoặc `failure` (ví dụ các chuỗi tương ứng). Nếu service ném exception, **không** có bảo đảm nó trở thành event `failure`: phải xử lý lỗi theo cơ chế riêng hoặc thiết kế một action wrapper có hợp đồng trả kết quả rõ ràng.

### 4.3. Tại sao cần hai decision-state cho loại tài khoản?

Cách viết một bước ngắn hơn có thể tạo ra lỗ hổng ý nghĩa:

~~~xml
<!-- Phản ví dụ: mọi giá trị khác PERSONAL đều bị coi là BUSINESS. -->
<decision-state id="checkAccountType">
    <if test="flowScope.registration.accountType == 'PERSONAL'"
        then="reviewPersonal"
        else="reviewBusiness" />
</decision-state>
~~~

Nếu request chứa `accountType='UNKNOWN'` hay `accountType=null`, nhánh `else` sẽ dẫn tới `reviewBusiness` dù dữ liệu không phù hợp. Một validator chỉ chấp nhận hai giá trị vẫn là cần thiết, nhưng flow nên có hợp đồng rõ ràng nếu dữ liệu có thể đến từ một đường khác ngoài form đã validation.

Trong ví dụ đầy đủ, nhánh `else` đầu tiên mang ý nghĩa “chưa phải PERSONAL”; decision-state tiếp theo kiểm tra chính xác “có phải BUSINESS hay không”. Nếu cũng sai, người dùng tới `invalidAccountType` và có thể sửa thông tin.

## 5. Kết quả hai trạng thái và kết quả nhiều trạng thái

### 5.1. Khi nào một cặp `then/else` là đủ?

Một cặp Boolean phù hợp khi quy tắc thật sự là một câu hỏi đúng/sai:

- Giỏ hàng có ít nhất một sản phẩm hay không?
- Người dùng đã xác nhận điều khoản hay chưa?
- Mã quốc gia nằm trong danh sách đang hỗ trợ hay không?
- Hồ sơ hiện tại có đủ trường bắt buộc để chuyển bước hay không?

Với những câu hỏi này, `then` và `else` mô tả đủ hai kết quả hợp lệ. Tuy vậy, dữ liệu đầu vào vẫn phải được kiểm tra để phân biệt **false đúng nghĩa** và **lỗi/thiếu dữ liệu**.

### 5.2. Khi nào cần nhiều hơn hai nhánh?

Một quy trình duyệt hồ sơ có thể trả về `APPROVED`, `REJECTED`, `PENDING` và trạng thái không hợp lệ. Nếu chỉ kiểm tra `status == 'APPROVED'` rồi đưa tất cả kết quả khác sang `REJECTED`, flow sẽ làm mất ý nghĩa của `PENDING`.

Có thể nối các decision-state để phân biệt từng giá trị:

~~~xml
<decision-state id="isApproved">
    <if test="flowScope.application.status == 'APPROVED'"
        then="approvedView"
        else="isRejected" />
</decision-state>

<decision-state id="isRejected">
    <if test="flowScope.application.status == 'REJECTED'"
        then="rejectedView"
        else="isPending" />
</decision-state>

<decision-state id="isPending">
    <if test="flowScope.application.status == 'PENDING'"
        then="pendingView"
        else="unexpectedStatus" />
</decision-state>
~~~

Ba phép kiểm tra tạo ra bốn đường đi được mô tả rõ: duyệt, từ chối, đang chờ và không hợp lệ. Nếu có nhiều trạng thái phức tạp hoặc service phải tính toán, cân nhắc `action-state` tạo **outcome event** tương ứng rồi dùng các `<transition on="...">` rõ ràng.

Ví dụ xử lý outcome của action:

~~~xml
<action-state id="evaluateApplication">
    <evaluate expression="applicationEvaluator.evaluate(
                              flowScope.application)" />
    <transition on="approved" to="approvedView" />
    <transition on="rejected" to="rejectedView" />
    <transition on="pending" to="pendingView" />
    <transition on="error" to="evaluationError" />
</action-state>
~~~

Trong trường hợp này, `applicationEvaluator.evaluate(...)` phải **chủ động trả outcome** với event ID được quy ước; `error` không phải event được tự sinh cho mọi exception. Nếu service trả về một đối tượng kết quả thay cho chuỗi/outcome, phải chuyển kết quả đó thành event phù hợp hoặc dùng cách lưu dữ liệu rồi đi qua decision-state.

### 5.3. Một state phải có đường phục hồi hoặc kết thúc hợp lý

Bao phủ kết quả không dừng ở việc khai báo tất cả `then`/`else`. Sau khi rẽ nhánh, người dùng cần biết phải làm gì tiếp theo. Có thể thiết kế:

| Loại kết quả | State đích điển hình | Điều kiện kết thúc |
|---|---|---|
| Đủ điều kiện | View xem lại, rồi action ghi dữ liệu | Ghi thành công mới tới `end-state` |
| Thiếu thông tin | View yêu cầu bổ sung | Quay lại form và thử lại |
| Không thỏa điều kiện nghiệp vụ | View giải thích hoặc end-state | Tùy khả năng sửa và quy tắc sản phẩm |
| Người dùng hủy | `end-state` `cancelled` | Kết thúc flow chủ động |
| Kết quả chưa xác định | View chờ / thông báo tạm thời | Không tự đánh đồng với từ chối |
| Hệ thống gặp lỗi | View phục hồi hoặc error handling | Giữ trạng thái phù hợp, tránh mất dữ liệu đã nhập |

Chỉ dùng `end-state` khi thực sự muốn kết thúc execution. Với flow con (subflow), ID của `end-state` còn là outcome gửi lại cho flow cha, nên cũng cần đặt tên có ý nghĩa như `verified`, `cancelled` hoặc `rejected`.

## 6. Sai lầm thường gặp với `then` và `else`

### 6.1. Nhầm giữa kết quả Boolean và event ID

Trong một `decision-state`:

~~~xml
<if test="flowScope.cart.totalAmount ge 100000"
    then="reviewOrder"
    else="belowMinimum" />
~~~

`then`/`else` phụ thuộc **giá trị Boolean của test**. Không có event ID `true` hay `false` mà người dùng cần gửi để chọn nhánh. Ngược lại, trong `view-state` và `action-state`, `transition on="next"` hoặc `on="success"` phản ứng với **event ID** được phát.

Đọc đúng chuỗi: nút `next` rời màn hình nhập → SWF vào decision-state → kiểm tra Boolean → tự đi tới state đích.

### 6.2. Dùng `else` để che giấu lỗi service

Đoạn `test="riskService.isSafe(flowScope.order)"` sẽ theo nhánh `else` nếu service trả về `false`. Nếu service ném exception vì timeout hay lỗi kết nối, không nên coi đơn hàng là không đạt. Hãy xác định error handling phù hợp, ghi lại nguyên nhân và tránh ghi dữ liệu dựa trên kết quả không chắc chắn.

### 6.3. Điều kiện có tác dụng phụ

Tránh đặt lời gọi `orderService.placeOrder(...)` trong `test`. Decision-state dùng để ra quyết định; thao tác ghi đơn hàng nên đặt trong action/service với transaction và kiểm tra trùng. Khi người dùng refresh hoặc gửi lại request, tránh thiết kế khiến phép kiểm tra Boolean vô tình tạo đơn hàng lần thứ hai.

### 6.4. Tự động lặp vô hạn

~~~xml
<!-- Phản ví dụ: không có view hay sự kiện để thay đổi dữ liệu. -->
<decision-state id="waitForApproval">
    <if test="flowScope.application.approved"
        then="reviewApplication"
        else="waitForApproval" />
</decision-state>
~~~

Nếu điều kiện không đổi, SWF cứ quay lại state quyết định mà không đợi người dùng. Thay nhánh `else` bằng màn hình hiển thị trạng thái chờ, flow có thể kết thúc an toàn hoặc giao việc kiểm tra lại cho request/tác vụ thích hợp.

### 6.5. Tin vào dữ liệu phía client

Form có thể bị sửa để gửi giá trị `accountType`, `approved` hoặc `isAdmin` tùy ý. Validation quyết định dữ liệu có hợp lệ để dùng trong flow; các thao tác phân quyền, xác nhận thanh toán hay tạo tài khoản vẫn phải được service kiểm tra dựa trên dữ liệu tin cậy phía server.

### 6.6. Không tính đến dữ liệu thay đổi theo thời gian

Một nhánh `then` cho biết phép kiểm tra đúng **tại thời điểm đi vào decision-state**. Số dư, tồn kho, quyền truy cập hay trạng thái đơn hàng có thể đổi trước khi người dùng xác nhận. Tầng service thực hiện nghiệp vụ cần kiểm tra lại những tiền điều kiện quan trọng ở thời điểm ghi.

## 7. Kiểm thử bao phủ các kết quả

Một bộ kiểm thử tốt phải đi qua cả nhánh `then` và `else`, các trường hợp biên và nhánh lỗi. Với flow mẫu đăng ký ở phần 4:

| Test case | Input/điều kiện | State kỳ vọng |
|---|---|---|
| Tài khoản cá nhân | `accountType='PERSONAL'`, form hợp lệ | `reviewPersonal` |
| Doanh nghiệp được hỗ trợ | `BUSINESS` và `regionPolicyService.isSupported(...) == true` | `reviewBusiness` |
| Doanh nghiệp ngoài vùng | `BUSINESS` và service trả `false` | `unsupportedCountry` |
| Loại tài khoản không hợp lệ | `accountType='UNKNOWN'`, qua đường dữ liệu không bị chặn trước | `invalidAccountType` |
| Form thiếu trường bắt buộc | `accountType=null`, validator báo lỗi | Ở lại `enterRegistration`, chưa vào decision-state |
| Người dùng hủy | Event `cancel` ở form đang nhập | `cancelled` |
| Service lưu thành công | Event `success` từ `persistRegistration` | `completed` |
| Trùng đăng ký | Outcome `duplicate` | `duplicateRegistration` |
| Lỗi nghiệp vụ đã được chuẩn hóa | Outcome `failure` | `saveError` |
| Service ném exception | Exception không được chuyển thành outcome | Đi theo cơ chế xử lý exception đã cấu hình |

Các ví dụ test `UNKNOWN` và `null` có đường kiểm thử khác nhau vì một request từ form có thể đã bị validation chặn trước khi đến các decision-state. Không thể khẳng định test đã bao phủ `invalidAccountType` nếu luôn dùng dữ liệu bị validator chặn ở bước nhập. Có thể khởi chạy flow ở state thích hợp bằng công cụ kiểm thử SWF hoặc kiểm tra trực tiếp đơn vị rẽ nhánh với state đã được thiết lập.

### 7.1. Boundary test

Nếu quy tắc là `age ge 18`, hãy dùng ít nhất ba giá trị:

- `17`: điều kiện sai → `else`.
- `18`: điều kiện đúng ngay ranh giới → `then`.
- `19`: điều kiện đúng vượt ranh giới → `then`.

Với `totalAmount ge 100000`, kiểm tra `99999`, `100000`, `100001`. Các kiểm thử này giúp phát hiện nhầm `gt` (lớn hơn) với `ge` (lớn hơn hoặc bằng).

### 7.2. Đo từng nhánh trong toàn flow

Đối với mỗi `decision-state`, trả lời các câu hỏi:

1. Dữ liệu thử nào khiến `test` trả `true`?
2. Dữ liệu thử nào khiến `test` trả `false`?
3. Mỗi kết quả có tới đúng state ID không?
4. Từ state đích, người dùng có thể tiếp tục, sửa, hủy hay kết thúc theo yêu cầu không?
5. Trường hợp thiếu/null, loại dữ liệu sai hoặc exception được kiểm soát thế nào?
6. Có thể quay lại và nhập lại mà không làm mất các dữ liệu cần thiết trong `flowScope` không?
7. Nếu thao tác cuối được gửi hai lần, tầng nghiệp vụ có ngăn ghi trùng khi cần không?

Có thể dùng hỗ trợ kiểm thử flow XML của Spring Web Flow hoặc kiểm thử tích hợp Spring MVC để gửi event và quan sát state hiện tại. Test chỉ kiểm tra HTTP status 200 là chưa đủ: cần xác minh cả **state sau transition**, lỗi validation và dữ liệu trong scope.

### 7.3. Theo dõi nhánh trong lúc chẩn đoán

Khi một luồng đi sai:

1. Xác nhận event ở `view-state` trước đó đúng và binding/validation đã qua.
2. Xác nhận flow đã đi vào decision-state đang xét.
3. Ghi nhận dữ liệu thực tế mà biểu thức `test` sử dụng, tránh log thông tin nhạy cảm.
4. Phân biệt biểu thức trả `false` với exception khi đánh giá.
5. Kiểm tra state ID của `then` và `else` có tồn tại, đang được render/execute đúng hay không.
6. Kiểm tra thứ tự các decision-state nối tiếp, tránh gộp nhầm trạng thái không xác định vào `else`.

## 8. Bài tập thực hành

Hãy thiết kế flow đăng ký dịch vụ có ba loại hồ sơ: `PERSONAL`, `BUSINESS` và `NON_PROFIT`. Điều kiện là hồ sơ cá nhân có thể xem lại ngay, hồ sơ doanh nghiệp phải xác minh quốc gia, còn hồ sơ tổ chức phi lợi nhuận phải xác minh giấy tờ.

Yêu cầu:

1. Tạo `view-state` nhập hồ sơ với form binding và validation.
2. Dùng các `decision-state` nối tiếp với `<if test="..." then="..." else="..."/>` để phân biệt **đúng ba loại hợp lệ**, đồng thời đưa loại không hợp lệ tới view giải thích.
3. Với hồ sơ doanh nghiệp, kiểm tra một Boolean từ service; phân biệt quốc gia không hỗ trợ với lỗi service.
4. Với hồ sơ phi lợi nhuận, nếu thiếu giấy tờ thì đưa về bước bổ sung; nếu đủ thì tới review.
5. Tạo bước lưu hồ sơ bằng `action-state`, phân biệt outcome `success`, `duplicate` và `failure`, chỉ tới `end-state` `completed` khi thực sự lưu thành công.
6. Viết bảng kiểm thử bao phủ `then`, `else` của **từng decision-state**, một trường hợp null, một boundary case và một exception từ service.

Bài được coi là hoàn thành khi nhìn vào định nghĩa flow và bảng test có thể xác định **mỗi kết quả được xử lý ra sao**, trường hợp nào được tiếp tục, trường hợp nào cần quay lại, trường hợp nào phải phục hồi và thời điểm nào flow kết thúc. `then` và `else` là hai cổng điều hướng rõ ràng; chất lượng thực sự nằm ở việc bảo đảm tất cả kết quả nghiệp vụ có đường đi đúng và được kiểm thử.
