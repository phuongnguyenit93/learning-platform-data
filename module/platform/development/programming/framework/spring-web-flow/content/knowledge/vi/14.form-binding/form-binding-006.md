# Checkbox, trường không xuất hiện và giá trị rỗng

Một biểu mẫu HTML nhiều bước thường có checkbox, radio, select và các trường tùy chọn. Khi người dùng gửi form, **trình duyệt không gửi mọi control theo cùng một cách**: checkbox không được chọn thường không xuất hiện trong request; input text để trống lại có thể gửi tham số với giá trị rỗng; control bị disable thường không được gửi; một nhóm checkbox có thể gửi nhiều giá trị cho cùng một tên.

Nếu không hiểu các quy tắc này, ứng dụng Spring Web Flow (SWF) có thể giữ lại lựa chọn cũ dù người dùng đã bỏ chọn, xóa nhầm dữ liệu ở bước khác, hoặc báo lỗi required ngoài ý muốn. Bài này giải thích cách trình duyệt tạo request, cách binder của SWF xử lý **field marker**, cách phân biệt tham số thiếu với giá trị rỗng, và cách kiểm thử các trường hợp đó trong flow nhiều bước.

Bài thuộc chương **Liên kết biểu mẫu** của module **SPRING_WEB_FLOW**. SWF mô hình hóa hành trình web qua state, event, transition và subflow; binder nối dữ liệu HTTP với model trong từng view-state, validation kiểm tra giá trị sau binding, còn flow scope giữ bản nháp qua các bước. Khi thiết kế checkbox và trường tùy chọn, ta cần đồng bộ hợp đồng giữa HTML, binder, model và validation.

## 1. Trình duyệt gửi những control nào?

Một form HTML chỉ gửi các **successful controls**: control có tên, đang được gửi theo form và thỏa quy tắc của trình duyệt. Một số quy tắc quan trọng:

- Checkbox được chọn gửi tên và giá trị của nó.
- Checkbox không được chọn thường **không gửi tham số**.
- Radio chỉ gửi giá trị của lựa chọn đang được chọn; nếu không có lựa chọn, tham số có thể vắng mặt.
- Select một lựa chọn thường gửi option được chọn; option có value rỗng gửi một chuỗi rỗng.
- Select nhiều lựa chọn gửi các giá trị đã chọn; nếu không chọn mục nào, tham số có thể vắng mặt.
- Input text để trống thường gửi tham số với giá trị rỗng, ví dụ **nickname=**.
- Control có thuộc tính **disabled** thường không được gửi.
- Hidden input vẫn được gửi, nhưng giá trị của nó vẫn do client kiểm soát và không đáng tin cậy cho mục đích phân quyền.

Bảng sau minh họa dữ liệu mà server có thể nhận:

| Control | Trạng thái | Tham số ví dụ |
|---|---|---|
| Checkbox **newsletter** | Được chọn | **newsletter=true** |
| Checkbox **newsletter** | Không được chọn | Không có **newsletter** |
| Text **nickname** | Để trống | **nickname=** |
| Text **nickname** | Không nằm trong form/request | Không có **nickname** |
| Radio **deliveryMode** | Chọn **PICKUP** | **deliveryMode=PICKUP** |
| Radio **deliveryMode** | Chưa chọn | Không có **deliveryMode** |
| Select **city** | Chọn option rỗng | **city=** |
| Select nhiều **amenities** | Chọn hai mục | **amenities=POOL&amenities=GYM** |
| Input **comment** | Bị disable | Không có **comment** |

Điểm dễ nhầm nhất là **không có tham số** và **có tham số nhưng rỗng** là hai request khác nhau:

~~~http
# Trường nickname hoàn toàn vắng mặt
_eventId_save=&newsletter=true

# Trường nickname có mặt nhưng rỗng
_eventId_save=&nickname=&newsletter=true
~~~

Trong trường hợp đầu, server không nhận được khóa **nickname**. Trong trường hợp sau, server nhận được khóa nhưng giá trị là chuỗi rỗng. Binder có thể xử lý hai trường hợp khác nhau tùy cấu hình view-state và field marker.

## 2. Vì sao checkbox không được chọn gây vấn đề?

Giả sử model của một bản nháp có:

~~~java
public class PreferenceDraft {
    private boolean newsletter;
    private String nickname;

    public boolean isNewsletter() {
        return newsletter;
    }

    public void setNewsletter(boolean newsletter) {
        this.newsletter = newsletter;
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Người dùng mở form, checkbox newsletter đang được chọn. Model có **newsletter=true**. Sau đó họ bỏ chọn và nhấn Save.

Theo quy tắc HTML, checkbox không được chọn không gửi tham số **newsletter**. Nếu request không có dấu hiệu nào cho biết control này đã xuất hiện trên form, binder không thể phân biệt chắc chắn hai tình huống:

1. Người dùng đã bỏ chọn checkbox.
2. Request hiện tại không chứa field newsletter vì form chỉ gửi một phần dữ liệu.

Nếu binder không cập nhật property, giá trị cũ **true** có thể vẫn còn trong model. Điều này tạo lỗi nghiệp vụ: giao diện cho thấy người dùng đã bỏ chọn nhưng dữ liệu vẫn ghi nhận đã đăng ký.

**Field marker** giải quyết vấn đề này bằng cách gửi thêm một tham số đánh dấu rằng checkbox thuộc form hiện tại, kể cả khi checkbox không được chọn.

## 3. Field marker của Spring Web Flow

Với Spring Web MVC view trong Spring Web Flow 2.5.x, **AbstractMvcView** hỗ trợ một **field marker prefix**. Prefix mặc định là dấu gạch dưới **_**.

Nếu field có tên **newsletter**, marker tương ứng là:

~~~text
_newsletter
~~~

Binder kiểm tra sự tồn tại của marker; giá trị marker không cần mang ý nghĩa nghiệp vụ. Ví dụ **visible**, **1** hoặc chuỗi rỗng đều có thể dùng làm giá trị đánh dấu, miễn request có tham số marker theo quy ước.

HTML có thể viết:

~~~html
<form method="post">
    <input type="hidden"
           name="_newsletter"
           value="visible">

    <label>
        <input type="checkbox"
               name="newsletter"
               value="true">
        Nhận bản tin qua email
    </label>

    <button type="submit" name="_eventId_save" value="">
        Lưu lựa chọn
    </button>
</form>
~~~

Hai tình huống:

| Trạng thái checkbox | Request parameters |
|---|---|
| Được chọn | **_newsletter=visible**, **newsletter=true** |
| Không được chọn | **_newsletter=visible** |

Khi checkbox không được chọn, marker vẫn xuất hiện. Binder nhận ra field **newsletter** đã có mặt trong form nhưng không có giá trị được chọn, rồi **reset property về empty value phù hợp** theo cơ chế binding. Giá trị cụ thể cần được xác minh với kiểu property, conversion và phiên bản đang dùng; không nên giả định mọi kiểu đều nhận cùng một giá trị.

### 3.1. Marker được kiểm tra theo sự tồn tại

Marker không phải một cờ bảo mật. SWF kiểm tra tham số marker có tồn tại hay không; giá trị của nó có thể là bất kỳ chuỗi nào.

~~~text
_newsletter=visible
_newsletter=1
_newsletter=
~~~

Cả ba đều biểu diễn sự hiện diện của marker. Không dùng nội dung marker để quyết định người dùng có quyền hay đã đồng ý điều khoản.

### 3.2. Cấu hình prefix

Trong API Spring Web Flow 2.5.x, **AbstractMvcView#setFieldMarkerPrefix(...)** cho phép thay đổi prefix. **MvcViewFactoryCreator** cũng cung cấp cấu hình tương ứng cho MVC view factory.

Ví dụ, nếu ứng dụng chọn prefix **__**, field **newsletter** cần marker:

~~~text
__newsletter
~~~

HTML và cấu hình phải dùng cùng prefix. Nếu thay prefix ở server nhưng template vẫn phát **_newsletter**, binder sẽ không nhận diện marker theo quy ước mới.

Đặt prefix thành **null** sẽ tắt cơ chế kiểm tra field marker. Chỉ làm vậy khi ứng dụng đã có một cách khác để biểu diễn trạng thái bỏ chọn và đã kiểm thử tất cả form có checkbox/select tùy chọn.

## 4. Checkbox đơn và nhóm checkbox

### 4.1. Checkbox Boolean

Với một lựa chọn đúng/sai, dùng tên field ổn định và giá trị rõ ràng:

~~~html
<input type="hidden" name="_marketingOptIn" value="visible">

<label>
    <input type="checkbox"
           name="marketingOptIn"
           value="true">
    Tôi đồng ý nhận thông tin tiếp thị
</label>
~~~

Model có thể dùng **boolean** hoặc **Boolean**:

~~~java
public class ContactPreferences {
    private boolean marketingOptIn;

    public boolean isMarketingOptIn() {
        return marketingOptIn;
    }

    public void setMarketingOptIn(boolean marketingOptIn) {
        this.marketingOptIn = marketingOptIn;
    }
}
~~~

Với primitive **boolean**, trạng thái mặc định của Java là **false**. Với wrapper **Boolean**, model có thể biểu diễn cả **null**, **true** và **false**. Việc binder reset về empty value nào còn phụ thuộc loại property và conversion. Nếu nghiệp vụ cần phân biệt “chưa trả lời” với “đã chọn không”, wrapper hoặc enum có thể phù hợp hơn; hãy xác minh bằng test thay vì dựa vào giả định.

**Không dùng required="true" để bắt người dùng tick checkbox.** Required binding kiểm tra việc có giá trị được bind theo quy tắc của binder; giá trị Boolean **false** vẫn là một giá trị Boolean. Nếu điều kiện nghiệp vụ là người dùng phải đồng ý, hãy kiểm tra rõ **marketingOptIn == true** bằng validator hoặc service.

### 4.2. Nhiều checkbox cùng một property

Giả sử người dùng chọn các tiện ích muốn sử dụng. Model dùng tập hợp:

~~~java
public class PreferenceDraft {
    private Set<String> amenities = new LinkedHashSet<>();

    public Set<String> getAmenities() {
        return amenities;
    }

    public void setAmenities(Set<String> amenities) {
        this.amenities = amenities;
    }
}
~~~

Form:

~~~html
<input type="hidden" name="_amenities" value="visible">

<label>
    <input type="checkbox" name="amenities" value="POOL">
    Hồ bơi
</label>

<label>
    <input type="checkbox" name="amenities" value="GYM">
    Phòng tập
</label>

<label>
    <input type="checkbox" name="amenities" value="BREAKFAST">
    Bữa sáng
</label>
~~~

Nếu người dùng chọn hồ bơi và phòng tập, request có thể chứa:

~~~text
_amenities=visible
amenities=POOL
amenities=GYM
~~~

Nếu người dùng bỏ chọn tất cả, request vẫn có:

~~~text
_amenities=visible
~~~

Nhờ marker, binder biết nhóm checkbox có mặt trên form và có thể xóa tập lựa chọn cũ thay vì giữ lại các mục trước đó.

**Chỉ cần một marker cho cả nhóm checkbox có cùng tên property**, không cần một marker cho từng option. Nếu từng checkbox là một property riêng, mỗi property cần marker tương ứng.

### 4.3. Không dùng cùng tên cho các nhóm khác nhau

Nếu hai nhóm checkbox độc lập đều dùng tên **options**, binder không thể phân biệt nhóm nào tạo ra giá trị. Dùng property path riêng:

~~~text
contactChannels
bookingAmenities
notificationTypes
~~~

Mỗi nhóm có marker riêng và được ánh xạ tới đúng collection trong model.

## 5. Binder cấu hình tường minh và field không xuất hiện

Trong SWF, **view-state** có thể khai báo **<binder>** để giới hạn property được phép bind:

~~~xml
<view-state id="preferences"
            view="booking/preferences"
            model="draft">
    <binder>
        <binding property="newsletter"/>
        <binding property="amenities"/>
        <binding property="nickname"/>
    </binder>

    <transition on="save" to="review"/>
    <transition on="back"
                to="contact"
                bind="false"
                validate="false"/>
</view-state>
~~~

Binder tường minh có hai mục tiêu:

1. Chỉ cho phép các property đã khai báo được cập nhật từ view.
2. Xác định rõ các property mà view-state này quản lý.

Theo API **AbstractMvcView** của SWF 2.5.x, khi view có binder configuration, các binding đã khai báo được xét trong quá trình tạo mapping. Nếu request không có tham số tương ứng, SWF tạo mapping đặc biệt để đặt property về empty value (thường là **null**). Vì vậy, **field được khai báo trong binder nhưng vắng mặt khỏi request có thể bị reset**.

Điều này rất quan trọng với form gửi một phần dữ liệu:

- Nếu view-state quản lý toàn bộ các field đã khai báo, việc reset field vắng mặt có thể là hành vi mong muốn.
- Nếu request chỉ gửi một phần form qua AJAX, các field không gửi có thể bị xóa ngoài ý muốn.
- Nếu field bị ẩn hoặc disable theo điều kiện, binder vẫn có thể xem property đã khai báo là một phần của view và reset nó khi không có giá trị.

**Binder whitelist không phải cơ chế PATCH tự động.** Hãy thiết kế binder theo từng view-state và xác định rõ request đó đại diện cho toàn bộ form hay chỉ một phần dữ liệu.

### 5.1. Khi không khai báo binder

Nếu view không có binder configuration, SWF MVC view mặc định tạo mapping từ các request parameter đến property model trùng tên. Những parameter có prefix marker được loại khỏi mapping thông thường và xử lý như field marker.

Cách này linh hoạt nhưng có thể cho phép nhiều property public của model được bind hơn dự kiến. Với form nghiệp vụ, binder tường minh thường giúp giới hạn trường đầu vào và giảm nguy cơ over-posting.

### 5.2. So sánh hành vi

| Trường hợp | Binder tường minh | Không khai báo binder |
|---|---|---|
| Field được gửi với giá trị | Mapping theo binding đã khai báo | Mapping nếu tên khớp property |
| Field không có request parameter | Mapping empty value cho binding đã khai báo | Thường không tạo mapping thông thường cho property đó |
| Field marker có mặt | Dùng để biểu diễn field rỗng/bỏ chọn theo cấu hình | Được loại khỏi mapping thường và xử lý như marker |
| Field không nằm trong whitelist | Không được bind | Có thể được bind nếu request parameter khớp property public |
| Partial/AJAX submit | Cần chú ý field đã khai báo nhưng không gửi | Chỉ các parameter nhận được mới được map, trừ marker |

Chi tiết có thể thay đổi theo loại view, binder implementation và phiên bản SWF. Dùng HTTP integration test với chính renderer và view factory của ứng dụng để xác nhận.

## 6. Phân biệt missing, empty và blank

Ba trạng thái này cần được xử lý theo ngữ nghĩa của trường:

| Trạng thái | Ví dụ request | Ý nghĩa |
|---|---|---|
| Missing | Không có **nickname** | Request không gửi field |
| Empty | **nickname=** | Field được gửi với chuỗi rỗng |
| Blank | **nickname=+++** hoặc giá trị chỉ có khoảng trắng | Field có chuỗi nhưng không có nội dung hữu ích |
| Explicit false | **newsletter=false** | Có giá trị false được gửi rõ ràng |
| Marker only | **_newsletter=visible** | Field có trên form nhưng không có lựa chọn được gửi |
| Disabled | Control bị disable | Trình duyệt không gửi control đó |

### 6.1. Input text để trống

HTML:

~~~html
<label for="nickname">Tên hiển thị</label>
<input id="nickname"
       name="nickname"
       type="text"
       value="">
~~~

Khi submit, trình duyệt thường gửi **nickname=**. Với property kiểu **String**, binder có thể nhận chuỗi rỗng; với property số/ngày, kết quả conversion phụ thuộc converter/formatter và cấu hình. Không nên coi mọi giá trị rỗng đều tự động trở thành **null**.

### 6.2. Chuỗi chỉ có khoảng trắng

Request:

~~~text
nickname=%20%20%20
~~~

Đây là một giá trị chuỗi có ba dấu cách, không giống việc tham số hoàn toàn vắng mặt. Nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là rỗng, dùng trim/normalization phù hợp và validation như **@NotBlank**.

Không dùng **required="true"** như cách duy nhất để loại chuỗi whitespace nếu binder không trim giá trị theo cấu hình. Required binding tập trung vào giá trị null/empty theo cơ chế mapping; quy tắc “phải có ký tự có nghĩa” thuộc validation.

### 6.3. Giá trị false và giá trị không được gửi

Với checkbox:

~~~text
newsletter=false
~~~

là tham số được gửi rõ ràng. Còn:

~~~text
_newsletter=visible
~~~

là marker cho biết field có trên form nhưng không được chọn. Hai request có thể dẫn tới cùng trạng thái cuối trong model, nhưng ngữ nghĩa request khác nhau và có thể được xử lý khác tùy conversion.

## 7. Trường tùy chọn và trường bắt buộc

Không phải mọi field không xuất hiện đều là lỗi. Hãy phân loại theo nghiệp vụ:

- **Bắt buộc nhập:** ví dụ email liên hệ.
- **Tùy chọn:** ví dụ nickname.
- **Checkbox đồng ý bắt buộc phải chọn:** ví dụ đồng ý điều khoản.
- **Checkbox tùy chọn:** ví dụ nhận bản tin.
- **Trường phụ thuộc lựa chọn khác:** ví dụ địa chỉ chỉ bắt buộc khi chọn giao tận nơi.
- **Trường không thuộc form hiện tại:** không nên bị bind/reset trong request của view-state khác.

Ví dụ:

~~~xml
<view-state id="contact"
            view="booking/contact"
            model="draft">
    <binder>
        <binding property="email" required="true"/>
        <binding property="nickname"/>
        <binding property="termsAccepted"/>
        <binding property="newsletter"/>
    </binder>
    <transition on="next" to="review"/>
</view-state>
~~~

Ở đây **email** được đánh dấu required. Các field còn lại có thể nhận empty value. Tuy nhiên, nếu **termsAccepted** phải là true, cần kiểm tra điều kiện đó trong validation/service. **required="true" không có nghĩa checkbox phải được tick.**

Ví dụ validator:

~~~java
public void validateContact(
        BookingDraft draft,
        ValidationContext context) {

    if (!draft.isTermsAccepted()) {
        context.getMessageContext().addMessage(
            new MessageBuilder()
                .error()
                .source("termsAccepted")
                .defaultText("Bạn cần đồng ý điều khoản để tiếp tục.")
                .build()
        );
    }
}
~~~

Đây là ví dụ validator theo quy ước SWF; cần đăng ký validator hoặc phương thức validation theo đúng cấu hình model/view-state của ứng dụng. Với checkbox bắt buộc, kiểm tra **giá trị nghiệp vụ là true**, không chỉ sự tồn tại của parameter.

## 8. Trường bị disable, ẩn hoặc render có điều kiện

### 8.1. Disabled control

Một control có thuộc tính **disabled** thường không được gửi trong form. Ví dụ:

~~~html
<input type="checkbox"
       name="newsletter"
       value="true"
       disabled>
~~~

Nếu model đang có **newsletter=true**, request không có field này. Nếu binder tường minh quản lý **newsletter**, mapping empty value có thể reset property. Nếu mục tiêu là giữ giá trị cũ, đừng vô tình đưa field đó vào binding của request hiện tại; hãy thiết kế view-state/binder hoặc logic xử lý phù hợp.

Không dùng disabled để bảo vệ giá trị quan trọng. Người dùng có thể sửa request và gửi tham số khác; dữ liệu như giá, owner ID, approval status phải được server lấy hoặc xác minh từ nguồn tin cậy.

### 8.2. Trường ẩn bằng CSS

Một input bị ẩn bằng CSS nhưng vẫn enable và có name thường vẫn được gửi. Đây khác với input bị disable. Đừng dựa vào việc người dùng không nhìn thấy field để kết luận field không thể bị sửa.

### 8.3. Conditional rendering

Giả sử checkbox **hasCompany** điều khiển việc hiển thị trường **companyName**. Khi **hasCompany=false**, giao diện có thể bỏ render input companyName. Nếu binder view-state luôn khai báo **companyName**, field có thể được đặt empty value khi request không chứa nó.

Có hai lựa chọn thiết kế:

1. Nếu **companyName** không còn có ý nghĩa khi **hasCompany=false**, hãy xóa/reset nó một cách có chủ đích và kiểm tra ở service.
2. Nếu muốn giữ bản nháp để người dùng bật lại checkbox, đừng để request không chứa field tự động xóa dữ liệu; dùng binder/transition hoặc cơ chế cập nhật partial phù hợp.

Không để hành vi xóa dữ liệu phụ thuộc ngẫu nhiên vào việc template có render một input hay không.

## 9. Nhiều bước và nhiều loại submit

Trong flow nhiều bước, cùng một model có thể được dùng ở nhiều view-state nhưng mỗi view chỉ sửa một phần:

~~~xml
<view-state id="contact"
            view="booking/contact"
            model="draft">
    <binder>
        <binding property="email" required="true"/>
        <binding property="nickname"/>
    </binder>
    <transition on="next" to="preferences"/>
</view-state>

<view-state id="preferences"
            view="booking/preferences"
            model="draft">
    <binder>
        <binding property="newsletter"/>
        <binding property="amenities"/>
    </binder>
    <transition on="save" to="review"/>
    <transition on="back"
                to="contact"
                bind="false"
                validate="false"/>
</view-state>
~~~

Mỗi view-state có binder riêng nên chỉ quản lý field của màn hình tương ứng. Điều này giảm nguy cơ request của bước preferences tác động vào email đã nhập ở contact.

### 9.1. Phân biệt bind=false và validate=false

Hai thuộc tính này có tác dụng khác nhau:

- **bind="false"**: bỏ qua binding model cho transition đó; khi không binding thì validation gắn với model cũng không được chạy theo đường binding thông thường.
- **validate="false"**: bỏ qua validation nhưng **binding vẫn có thể xảy ra**.

Ví dụ:

~~~xml
<transition on="back"
            to="contact"
            bind="false"
            validate="false"/>
~~~

Dùng khi nút Back chỉ điều hướng và không muốn các giá trị dang dở của form hiện tại được bind. Nếu muốn giữ các thay đổi người dùng vừa nhập nhưng không chặn họ bằng validation, có thể cân nhắc chỉ đặt **validate="false"**; khi đó binding vẫn diễn ra.

Hãy chọn theo ý nghĩa nút bấm. Không mặc định mọi event Back phải bỏ binding, vì người dùng có thể mong muốn dữ liệu vừa nhập vẫn được giữ lại.

### 9.2. Submit Save Draft

Một nút Save Draft có thể cho phép field chưa hoàn chỉnh. Có thể định nghĩa transition riêng:

~~~xml
<transition on="saveDraft"
            to="draftSaved"
            validate="false">
    <evaluate expression="draftService.saveDraft(draft)"/>
</transition>
~~~

Ví dụ này vẫn cho phép binding vì không tắt **bind**; validation bị bỏ qua. Service phải biết đây là bản nháp chưa hoàn chỉnh, kiểm tra quyền và chỉ lưu những field hợp lệ theo hợp đồng draft. Không dùng **validate="false"** để bỏ qua kiểm tra bảo mật hoặc bất biến cần thiết khi lưu chính thức.

## 10. Marker với select và radio

Field marker không chỉ hữu ích với checkbox. API **AbstractMvcView** mô tả marker cho các field có thể rỗng, bao gồm checkbox và select options.

### 10.1. Select một lựa chọn

~~~html
<input type="hidden" name="_deliveryMode" value="visible">

<select name="deliveryMode">
    <option value="">-- Chọn hình thức nhận --</option>
    <option value="DELIVERY">Giao tận nơi</option>
    <option value="PICKUP">Nhận tại quầy</option>
</select>
~~~

Nếu người dùng chọn option rỗng, request có **deliveryMode=**. Nếu control không gửi tham số, marker có thể giúp binder nhận ra field thuộc form và cần reset. Cần phân biệt option rỗng với field hoàn toàn không được render.

### 10.2. Radio group

~~~html
<input type="hidden" name="_contactMethod" value="visible">

<label>
    <input type="radio" name="contactMethod" value="EMAIL">
    Email
</label>

<label>
    <input type="radio" name="contactMethod" value="PHONE">
    Điện thoại
</label>
~~~

Nếu không chọn radio nào, marker vẫn có thể được gửi để biểu diễn field đã xuất hiện nhưng không có lựa chọn. Nếu radio là bắt buộc, validation phải yêu cầu giá trị hợp lệ.

### 10.3. Multi-select

Một multi-select có thể không gửi giá trị nào khi người dùng bỏ hết lựa chọn. Marker giúp phân biệt “đã mở form và bỏ hết” với “field không thuộc request”. Test thực tế với renderer, browser và binder configuration trước khi dùng cho dữ liệu cần bảo toàn.

## 11. Những lưu ý bảo mật khi bind checkbox và hidden field

Checkbox có thể biểu diễn lựa chọn người dùng, nhưng **không phải cơ chế phân quyền**.

Không dùng các field sau làm bằng chứng đáng tin cậy:

- **isAdmin**
- **approved**
- **ownerId**
- **tenantId**
- **price**
- **isPaid**
- **termsAcceptedAt** nếu timestamp do client gửi

Người dùng có thể tự thêm parameter hoặc sửa hidden input. Binder whitelist chỉ giới hạn property được bind từ view; service vẫn cần xác minh danh tính, quyền và trạng thái dữ liệu.

Ví dụ không nên khai báo:

~~~xml
<binder>
    <binding property="customerName"/>
    <binding property="adminApproved"/>
    <binding property="price"/>
</binder>
~~~

nếu hai field cuối chỉ do server quyết định. Hãy tách form DTO khỏi entity nghiệp vụ và chỉ cho bind các trường mà người dùng được phép chỉnh sửa.

Với đồng ý điều khoản, nên lưu cả **phiên bản điều khoản** và thời điểm server ghi nhận sau khi xác nhận. Không tin một checkbox **termsAccepted=true** nếu request không qua bước xác thực và ghi nhận server-side phù hợp.

## 12. Kiểm thử các trạng thái của checkbox và field rỗng

Một test chỉ gửi checkbox checked chưa đủ. Cần kiểm thử việc bỏ chọn sau khi model đã có giá trị true, vì đây là tình huống dễ làm dữ liệu cũ bị giữ lại.

| ID | Giá trị ban đầu | Request | Kỳ vọng cần xác minh |
|---|---|---|---|
| C01 | **newsletter=false** | Marker + **newsletter=true** | Property thành true |
| C02 | **newsletter=true** | Chỉ marker **_newsletter** | Property được reset theo empty value của kiểu |
| C03 | **newsletter=true** | Không có marker, không có field | Hành vi theo binder config; không tự suy ra người dùng bỏ chọn |
| C04 | **nickname="Lan"** | **nickname=** | Property nhận empty value theo converter/binder |
| C05 | **nickname="Lan"** | Không có **nickname**, binder tường minh có binding | Kiểm tra mapping empty value của SWF |
| C06 | **nickname="Lan"** | Không có **nickname**, không binder config | Property thường không được map từ request thiếu |
| C07 | **newsletter=true** | Field disabled, không marker | Kiểm tra nguy cơ reset/giữ giá trị theo binder |
| C08 | **amenities={POOL,GYM}** | Marker **_amenities** nhưng không có **amenities** | Collection được reset theo cơ chế binder |
| C09 | **termsAccepted=false** | Marker nhưng checkbox không chọn | Validation phải từ chối nếu điều khoản bắt buộc |
| C10 | **newsletter=true** | AJAX chỉ gửi email | Không được vô tình xóa newsletter ngoài ý muốn |
| C11 | Có field ngoài whitelist | Gửi thêm **adminApproved=true** | Property không được bind |
| C12 | Có field chỉ whitespace | **nickname=%20%20** | Validation theo quy tắc blank của ứng dụng |

### 12.1. Flow test

Dùng flow execution test để xác minh binder xử lý event:

1. Bắt đầu flow và vào view-state preferences.
2. Đặt model ban đầu có **newsletter=true**.
3. Phát event save với request parameter chỉ chứa **_newsletter=visible**.
4. Kiểm tra property được reset theo empty-value policy của binder.
5. Lặp lại với **newsletter=true** và marker để xác nhận checked state.
6. Lặp lại với request thiếu cả marker và field để hiểu khác biệt của binder cấu hình tường minh và binder mặc định.
7. Kiểm tra validation message khi **termsAccepted** chưa được chọn.

Không chỉ gọi setter trực tiếp rồi kết luận checkbox binding đúng. Phải gửi **request parameters qua flow view binding**.

### 12.2. HTTP integration test

Dùng Spring MVC test hoặc servlet integration test với session và flow execution URL thực tế:

~~~java
// Pseudocode: helpers phải lấy action URL từ view do SWF render.
MvcResult page = mvc.perform(get("/booking/preferences"))
        .andReturn();

MockHttpSession session = sessionOf(page);
String actionUrl = flowExecutionUrlFrom(page);

// Người dùng bỏ chọn newsletter: marker có mặt,
// giá trị checkbox không xuất hiện.
MvcResult response = mvc.perform(
        post(actionUrl)
            .session(session)
            .param("_newsletter", "visible")
            .param("_eventId_save", ""))
        .andReturn();
~~~

Đây là pseudocode để thể hiện request cần gửi; **sessionOf** và **flowExecutionUrlFrom** là helper cần viết theo ứng dụng. Nếu form dùng CSRF, thêm token hợp lệ vào request. Với JSP, **MockMvc** có thể không render JSP thành HTML đầy đủ; khi cần kiểm tra hidden marker thực sự xuất hiện, dùng môi trường servlet có view rendering phù hợp hoặc browser test.

### 12.3. Kiểm tra HTML được render

Mở DevTools → Network và xem payload của request khi:

- Checkbox được chọn.
- Checkbox bị bỏ chọn.
- Người dùng bỏ chọn tất cả checkbox trong nhóm.
- Control bị disable.
- Một trường bị ẩn theo điều kiện.
- Form gửi qua AJAX chỉ gồm một phần field.

Đừng chỉ xem trạng thái control trên màn hình. **Payload HTTP thực tế** mới cho biết server nhận được tham số nào.

## 13. Lỗi thường gặp và cách xử lý

### 13.1. Bỏ chọn checkbox nhưng model vẫn true

**Nguyên nhân có thể:** HTML không gửi marker, field marker prefix không khớp, marker bị disable hoặc form không chứa hidden marker.

**Cách xử lý:** xác nhận request có **_field**, kiểm tra prefix của view factory và kiểm thử lại khi model ban đầu đã là true.

### 13.2. Checkbox bị reset dù người dùng không thay đổi

**Nguyên nhân có thể:** binder tường minh quản lý field nhưng request hiện tại không gửi field đó; form submit một phần hoặc control bị disable.

**Cách xử lý:** tách binder theo view-state, tránh đưa field không thuộc form vào binder hiện tại, hoặc thiết kế partial-update contract rõ ràng. Không xóa field khỏi binder chỉ để che lỗi mà chưa kiểm tra yêu cầu bảo mật/whitelist.

### 13.3. Marker bị bind vào model như một field bình thường

**Nguyên nhân có thể:** custom view factory tắt field marker, đổi prefix hoặc view không dùng SWF MVC view implementation dự kiến.

**Cách xử lý:** kiểm tra **fieldMarkerPrefix** và view factory; test để marker không trở thành property ngoài ý muốn.

### 13.4. Required checkbox vẫn cho qua khi không được chọn

**Nguyên nhân:** **required="true"** không tương đương điều kiện Boolean phải là true. Giá trị false vẫn không phải null.

**Cách xử lý:** dùng validator kiểm tra true, thêm thông báo gắn với field và test request marker-only.

### 13.5. Tất cả lựa chọn cũ vẫn còn sau khi bỏ chọn hết

**Nguyên nhân:** nhóm checkbox không có marker, binder không nhận ra nhóm đã được gửi nhưng không có lựa chọn, hoặc template chỉ gửi marker khi có option được chọn.

**Cách xử lý:** đặt marker một lần cho cả nhóm ở ngoài danh sách option, bảo đảm nó luôn được gửi cùng form.

### 13.6. AJAX xóa những field không có trong payload

**Nguyên nhân:** binder cấu hình tường minh tạo empty-value mapping cho field được khai báo nhưng request không chứa parameter.

**Cách xử lý:** chỉ bind các field của request partial, dùng transition phù hợp hoặc tách view-state/binder cho thao tác AJAX. Không dùng một binder của toàn form cho mọi request fragment nếu payload chỉ chứa một phần dữ liệu.

### 13.7. Field disabled bị coi là người dùng bỏ chọn

**Nguyên nhân:** control không gửi value, nhưng binder vẫn quản lý property hoặc marker còn được gửi.

**Cách xử lý:** xác định rõ disabled có nghĩa là giữ giá trị, xóa giá trị hay không cho phép thay đổi. Thực hiện quyết định đó ở server; đừng dựa vào việc trình duyệt bỏ gửi field.

## 14. Bài tập thực hành: form tùy chọn dịch vụ

Tạo flow đăng ký dịch vụ có hai bước:

~~~text
contact → preferences → review → submitted
~~~

Model:

~~~java
public class ServiceDraft implements Serializable {
    private String email;
    private boolean newsletter;
    private Set<String> channels = new LinkedHashSet<>();
    private String nickname;
    private boolean termsAccepted;

    // Getter/setter cho các property.
}
~~~

Yêu cầu:

1. Ở state **preferences**, hiển thị checkbox newsletter.
2. Dùng marker **_newsletter** để server nhận biết trường hợp người dùng bỏ chọn.
3. Tạo nhóm checkbox **channels** gồm EMAIL, SMS và APP; chỉ dùng một marker **_channels**.
4. Cho nickname là tùy chọn; thử cả **nickname=**, chuỗi whitespace và request không có tham số.
5. Bắt buộc **termsAccepted** phải true; dùng validator thay vì chỉ **required="true"**.
6. Cấu hình binder chỉ cho phép các property của màn hình preferences.
7. Gửi request partial chỉ chứa newsletter, quan sát field nào bị reset khi binder có nhiều binding.
8. Tạo một nút Back với **bind="false" validate="false"** và một nút Save Draft với binding bật nhưng validation tắt.
9. Viết test khi model ban đầu có newsletter=true, request marker-only phải reset trạng thái.
10. Thử tắt field marker prefix trong môi trường test và ghi nhận khác biệt.
11. Xác nhận server không dùng hidden input để quyết định quyền hoặc trạng thái phê duyệt.

### Câu hỏi ôn tập

**1. Vì sao checkbox không được chọn thường không có request parameter?** Vì theo quy tắc HTML, checkbox chỉ được gửi khi được chọn.

**2. Field marker giải quyết vấn đề nào?** Nó báo cho binder biết field thuộc form hiện tại dù không có giá trị checkbox được gửi, để property có thể được reset.

**3. Prefix marker mặc định của SWF MVC 2.5.x là gì?** Dấu gạch dưới **_**, ví dụ **_newsletter**.

**4. Giá trị của marker có cần là true không?** Không. Binder kiểm tra sự tồn tại của marker, không dùng giá trị đó làm lựa chọn nghiệp vụ.

**5. nickname= có giống không gửi nickname không?** Không. Một request có tham số với chuỗi rỗng; trường hợp kia không có khóa.

**6. Vì sao required="true" không đủ để bắt buộc checkbox được chọn?** Vì giá trị Boolean false vẫn không phải null; cần validation kiểm tra điều kiện true.

**7. Tại sao binder tường minh có thể xóa field trong AJAX partial submit?** Vì SWF MVC view có thể tạo empty-value mapping cho binding đã khai báo nhưng request không chứa parameter tương ứng.

**8. Hidden field có đáng tin hơn checkbox không?** Không. Người dùng có thể sửa mọi parameter từ client; server phải xác minh dữ liệu và quyền.

## 15. Checklist trước khi triển khai

- [ ] Đã xác định field nào là checkbox đơn, nhóm checkbox, radio, select và text tùy chọn.
- [ ] Đã phân biệt missing, empty, blank, false và marker-only.
- [ ] Checkbox cần nhận biết bỏ chọn có field marker phù hợp.
- [ ] Prefix marker trong HTML khớp với cấu hình SWF MVC view factory.
- [ ] Marker được gửi kể cả khi mọi checkbox trong nhóm đều không chọn.
- [ ] Chỉ dùng một marker cho một property collection có nhiều checkbox cùng tên.
- [ ] Binder whitelist chỉ chứa property được phép cập nhật từ view-state.
- [ ] Đã kiểm tra tác động của binding tường minh khi request thiếu field.
- [ ] Partial/AJAX submit không vô tình xóa field ngoài payload.
- [ ] Trường disabled/ẩn có chính sách giữ, xóa hoặc bỏ qua rõ ràng.
- [ ] required="true" không bị nhầm với validation Boolean phải là true.
- [ ] Model dùng kiểu dữ liệu phù hợp nếu cần phân biệt null, false và chưa trả lời.
- [ ] Validation xử lý chuỗi whitespace và điều kiện phụ thuộc.
- [ ] Back/Cancel/Save Draft có cấu hình bind/validate phù hợp.
- [ ] Test bao phủ checked, unchecked, marker-only, missing, empty, blank và partial request.
- [ ] Service không tin hidden field hoặc dữ liệu client làm bằng chứng quyền.

**Ghi nhớ:** Checkbox không được chọn thường **không gửi tham số**; field marker giúp SWF nhận ra control đã xuất hiện nhưng không có lựa chọn. Một field có tham số rỗng, một field hoàn toàn vắng mặt và một field chỉ có marker là ba request khác nhau. Kết hợp marker đúng prefix, binder theo từng view-state và validation theo nghiệp vụ sẽ giúp dữ liệu checkbox không bị giữ cũ hoặc xóa nhầm trong hành trình Spring Web Flow nhiều bước.

### Tài liệu tham khảo

- [Spring Web Flow 2.5.1 Reference — Binding to a model, specifying bindings and required checks](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/)
- [Spring Web Flow 2.5.x API — AbstractMvcView#setFieldMarkerPrefix](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/mvc/view/AbstractMvcView.html)
- [Spring Web Flow 2.5.1 API — MvcViewFactoryCreator](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/mvc/builder/MvcViewFactoryCreator.html)
- [Spring Framework API — WebDataBinder field markers](https://docs.spring.io/spring-framework/docs/6.0.21/javadoc-api/org/springframework/web/bind/WebDataBinder.html)

