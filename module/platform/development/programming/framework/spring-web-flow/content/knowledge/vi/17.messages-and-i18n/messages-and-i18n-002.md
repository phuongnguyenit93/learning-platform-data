# MessageContext và các mức độ thông báo trong Spring Web Flow

> **Chương:** Thông báo và ngôn ngữ  
> **Mục tiêu:** Hiểu cách Spring Web Flow thu thập và chuyển thông báo từ bước xử lý đến giao diện; biết khi nào dùng thông tin, cảnh báo, lỗi, thông báo gắn field; tổ chức mã thông báo phục vụ đa ngôn ngữ (i18n) và kiểm thử trải nghiệm khi form hoặc nghiệp vụ không thành công.

## 1. Vì sao flow nhiều bước cần một cơ chế thông báo thống nhất?

Một quy trình đăng ký dịch vụ thường có các bước **nhập liên hệ → chọn gói → xem lại → xác nhận**. Trong cùng một flow, người dùng có thể gặp nhiều loại phản hồi:

- **Thông tin:** hệ thống đã lưu bản nháp, nhưng chưa hoàn tất đăng ký.
- **Cảnh báo:** gói được chọn sắp hết chỗ hoặc có điều kiện cần lưu ý.
- **Lỗi nhập liệu:** email bị bỏ trống hoặc không đúng định dạng.
- **Từ chối nghiệp vụ:** một gói đã hết chỗ trước thời điểm xác nhận.
- **Lỗi kỹ thuật:** dịch vụ đặt chỗ tạm thời không phản hồi, trạng thái giao dịch chưa chắc chắn.

Nếu mỗi controller tự đặt một chuỗi chữ vào session rồi view tự chọn cách hiển thị, thông báo có thể xuất hiện ở sai bước, bị mất khi redirect hoặc còn tồn tại sau khi người dùng đã sửa xong. Với ứng dụng nhiều ngôn ngữ, việc hardcode chuỗi còn gây khó khăn khi dịch.

**MessageContext** là một phần của cơ chế messaging trong **Spring Web Flow**: action, validator và các thành phần tham gia xử lý có thể bổ sung thông báo vào ngữ cảnh hiện hành để view hiển thị. Message có **mức độ (severity)**, có thể có **nguồn (source)** đại diện cho field, **mã (code)** để tra cứu bản dịch và **nội dung dự phòng** khi cần.

MessageContext giúp tách rõ ba trách nhiệm:

| Trách nhiệm | Thành phần điển hình | Ví dụ |
| --- | --- | --- |
| Xác định điều gì xảy ra | Validator hoặc service nghiệp vụ | Email rỗng, gói hết chỗ |
| Tạo thông báo phù hợp | MessageBuilder / MessageContext | ERROR cho email, WARNING cho gói |
| Hiển thị bằng ngôn ngữ và vị trí phù hợp | View + message source | Lỗi cạnh ô email, banner cảnh báo ở trang review |

**Message không phải event chuyển state.** Event và transition quyết định flow đi đến đâu; message giải thích cho người dùng vì sao flow đi theo nhánh đó và cần làm gì tiếp.

## 2. MessageContext là gì?

Trong Web Flow, **org.springframework.binding.message.MessageContext** là giao diện quản lý các thông báo được thu thập khi xử lý flow. Từ một **RequestContext**, code xử lý có thể truy cập:

~~~java
MessageContext messages = context.getMessageContext();
~~~

Trong đó **context** là **org.springframework.webflow.execution.RequestContext** của lần xử lý hiện hành. MessageContext có thể được dùng bởi validation, action hoặc code tích hợp với Web Flow.

Một thông báo có thể mang các thuộc tính:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Severity | Mức độ nghiêm trọng | INFO, WARNING, ERROR |
| Source | Thành phần/field mà message liên quan | email, packageCode |
| Code | Khóa tra cứu thông báo đã bản địa hóa | enrollment.email.required |
| Arguments | Giá trị tham số thay thế khi định dạng text | Số chỗ còn lại, ngày hết hạn |
| Default text | Nội dung dự phòng nếu không tra cứu được mã | Vui lòng nhập email |

**Source** thường là tên property của đối tượng form, chẳng hạn **email** hoặc **packageCode**. Một message không có source cụ thể thường thích hợp làm **thông báo toàn trang**.

### 2.1. MessageContext nằm ở đâu so với flowScope?

Đừng nhầm MessageContext với một biến trong **flowScope**:

- **flowScope** thường giữ dữ liệu nghiệp vụ đang nhập dở, như bản nháp đăng ký.
- **MessageContext** thu thập các message phục vụ phản hồi trong ngữ cảnh xử lý/hiển thị của Web Flow.
- **viewScope** có thể giữ dữ liệu riêng cho view-state đang hoạt động.
- **flashScope** có thể phù hợp với dữ liệu/thông báo ngắn hạn cần mang qua chuyển bước, tùy thiết kế.

Thời điểm message được hiển thị, giữ lại hay xóa khi chuyển state hoặc redirect phụ thuộc vòng đời view, cơ chế rendering và cấu hình phiên bản đang dùng. **Không nên giả định thông báo thêm vào MessageContext sẽ tồn tại vĩnh viễn qua mọi state, hoặc đương nhiên xuất hiện ở màn hình kết thúc.** Những thông điệp phải sống lâu hơn cần được thiết kế vòng đời riêng và kiểm thử thực tế.

### 2.2. MessageContext không lưu log vận hành

Một thông báo như “Vui lòng nhập địa chỉ email” là dữ liệu cho **trải nghiệm người dùng**. Log, metrics, trace và báo cáo sự cố là các cơ chế quan sát hệ thống khác. Không nên đưa stack trace, thông tin nhạy cảm hoặc chi tiết nội bộ của lỗi kỹ thuật vào message hiển thị ra trình duyệt.

## 3. Các mức độ thông báo: INFO, WARNING, ERROR và FATAL

Hệ thống message của Spring Web Flow phân loại severity để trình bày mức độ cần chú ý. Ba mức phổ biến nhất khi làm form là **INFO**, **WARNING** và **ERROR**; một số API của Spring Binding còn có **FATAL** dành cho lỗi đặc biệt nghiêm trọng.

| Mức | Khi nào dùng | Nội dung hướng tới người dùng | Phản ứng điển hình |
| --- | --- | --- | --- |
| **INFO** | Cung cấp tình trạng hoặc xác nhận thao tác chưa có vấn đề | Bản nháp đã được lưu | Hiển thị thông tin, cho tiếp tục |
| **WARNING** | Có điều cần lưu ý nhưng chưa chắc phải dừng quy trình | Gói bạn chọn chỉ còn ít chỗ | Hiển thị nổi bật, có thể cho tiếp tục |
| **ERROR** | Dữ liệu không hợp lệ hoặc thao tác chưa được chấp nhận | Email không hợp lệ | Yêu cầu sửa hoặc chuyển đến state xử lý lỗi |
| **FATAL** | Tình huống cần dừng xử lý theo chính sách ứng dụng/phiên bản hỗ trợ | Hiện không thể hoàn tất yêu cầu | Chuyển xử lý lỗi an toàn theo thiết kế |

Mức severity **không phải chính sách nghiệp vụ tự động**. Ví dụ:

- Cảnh báo “còn 2 chỗ” không nên chặn người dùng nếu hai chỗ vẫn hợp lệ.
- Lỗi “chọn 5 chỗ nhưng chỉ còn 2” phải được xử lý theo quy tắc đặt chỗ, dù UI chọn hiển thị banner nào.
- Lỗi kỹ thuật nghiêm trọng không nên được mô tả như một lỗi nhập liệu thông thường.

Đối với validation của Web Flow, các message mức lỗi có thể tham gia vào quyết định **giữ view để người dùng sửa** theo cơ chế binding/validation. Tuy nhiên, việc đi tiếp của các action-state phải được điều khiển bằng event/transition hoặc handling tương ứng. **Chỉ thêm một message ERROR trong một action không đồng nghĩa framework sẽ tự chọn nhánh error tùy ý.**

### 3.1. Không dùng ERROR cho mọi tình huống “chưa thành công”

Ba tình huống này cần được phân biệt:

1. Người dùng bỏ trống email: lỗi form, gắn source **email**.
2. Người dùng đã nhập đúng nhưng gói đã hết chỗ: kết quả nghiệp vụ không chấp nhận, có thể là message toàn trang và event **planUnavailable**.
3. Service timeout sau khi gọi tạo đăng ký: trạng thái kết quả có thể chưa rõ; hiển thị message trung tính, không khẳng định “đăng ký thất bại” nếu có khả năng đã commit.

Message severity diễn đạt cách giao tiếp với người dùng; **service vẫn phải cho biết kết quả nghiệp vụ hoặc tình trạng kỹ thuật một cách đáng tin cậy**.

## 4. Tạo message bằng MessageBuilder

Spring Binding cung cấp **MessageBuilder** để xây dựng một **MessageResolver** chứa các thuộc tính severity, source, code và text dự phòng. Sau đó bổ sung nó vào MessageContext.

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.webflow.execution.RequestContext;

public class EnrollmentFeedback {

    public void addFeedback(RequestContext context) {
        MessageContext messages = context.getMessageContext();

        messages.addMessage(new MessageBuilder()
                .info()
                .code("enrollment.draft.saved")
                .defaultText("Bản nháp đã được lưu.")
                .build());

        messages.addMessage(new MessageBuilder()
                .warning()
                .source("packageCode")
                .code("enrollment.package.lowCapacity")
                .defaultText("Gói này sắp hết chỗ.")
                .build());

        messages.addMessage(new MessageBuilder()
                .error()
                .source("email")
                .code("enrollment.email.invalid")
                .defaultText("Địa chỉ email không hợp lệ.")
                .build());
    }
}
~~~

Đây là ví dụ về **cách tạo message**, không phải một action dùng trong production: ba message được thêm đồng thời chỉ để người học so sánh cú pháp. Trong một xử lý thật, hãy chỉ thêm message đúng với kết quả đã xác định.

**Giải thích từng bước:**

1. Lấy MessageContext của request/flow đang xử lý.
2. Chọn severity bằng **info()**, **warning()** hoặc **error()**.
3. Chọn **source()** khi thông báo liên quan trực tiếp một field.
4. Đặt **code()** ổn định để ứng dụng tra cứu nội dung theo locale.
5. Đặt **defaultText()** để có nội dung dễ hiểu khi chưa có bản dịch tương ứng.
6. Gọi **build()** và chuyển resolver vào **addMessage()**.

**Không cần tạo MessageContext mới bằng tay** trong một action thông thường; dùng MessageContext thuộc RequestContext để tích hợp với vòng đời Web Flow.

### 4.1. Mã thông báo nên nói về ý nghĩa nghiệp vụ

Nên dùng:

- **enrollment.email.required**
- **enrollment.package.lowCapacity**
- **enrollment.submit.unavailable**
- **enrollment.draft.saved**

Tránh dùng mã phụ thuộc vị trí giao diện như **page2.text3**, vì khi thay đổi thiết kế màn hình, người đọc và người dịch không hiểu thông điệp phục vụ tình huống nào.

### 4.2. Source là định vị, không phải mã bản dịch

Trong message:

~~~java
new MessageBuilder()
    .error()
    .source("email")
    .code("enrollment.email.required")
    .defaultText("Vui lòng nhập email.")
    .build();
~~~

**email** là nơi hiển thị lỗi (source), còn **enrollment.email.required** là khóa tra cứu nội dung (code). Đổi source sang **packageCode** nhưng giữ nguyên code sẽ tạo một message có vị trí và ý nghĩa không khớp.

## 5. Message gắn field và message toàn trang

Với form nhiều bước, cần phân biệt message thuộc về **một trường nhập liệu** và message thuộc về **trạng thái chung của hành trình**.

| Trường hợp | Source | Vị trí hiển thị phù hợp |
| --- | --- | --- |
| Email không hợp lệ | email | Dưới ô email |
| Chưa chọn gói | packageCode | Gần vùng chọn gói |
| Giảm giá sắp hết hạn | Có thể không gắn source | Banner cảnh báo ở trang review |
| Lưu bản nháp thành công | Không cần source | Banner thông tin |
| Hệ thống chưa xác nhận được giao dịch | Không cần source | Khu vực trạng thái toàn trang |

Sự phân biệt này ảnh hưởng đến khả năng sử dụng: lỗi field cần đặt gần trường cần sửa, trong khi cảnh báo toàn trang có thể được trình bày ở đầu nội dung. **Một message được gắn source không có nghĩa mọi template engine tự động đặt nó đúng vị trí**; view phải sử dụng cơ chế hiển thị và binding tương thích.

### 5.1. Không tạo thông báo trùng nhau

Nếu cả validator của form và action nghiệp vụ đều báo **email.required**, người dùng có thể nhìn thấy hai lỗi giống hệt. Hãy xác định rõ quyền sở hữu:

- **Binding/validation**: sai định dạng, thiếu trường bắt buộc, dữ liệu của bước.
- **Service nghiệp vụ**: gói hết chỗ, không đủ điều kiện đăng ký, dữ liệu đã thay đổi.
- **Lớp xử lý lỗi kỹ thuật**: không thể xác minh kết quả, gián đoạn hạ tầng.

Mỗi loại phản hồi nên có một nơi chịu trách nhiệm phát message chính.

## 6. MessageContext trong vòng đời binding và validation

Xét view-state **contact**, người dùng phải nhập email hợp lệ trước khi đến **review**. Luồng xử lý logic:

~~~mermaid
flowchart TD
    A["Trình duyệt: gửi event next và form"] --> B["Web Flow: khôi phục contact"]
    B --> C["Binding dữ liệu vào model"]
    C --> D["Validation của contact"]
    D --> E{"Hợp lệ?"}
    E -->|"Không"| F["MessageContext: ERROR gắn field"]
    F --> G["Render lại contact kèm lỗi"]
    E -->|"Có"| H["Transition next tới review"]
~~~

Trong **ValidationContext**, validator có thể lấy MessageContext của lần validation:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.binding.validation.ValidationContext;

public class EnrollmentDraftValidator {

    // Method minh họa; phải đăng ký validator theo quy ước/cấu hình
    // phù hợp phiên bản Spring Web Flow được dùng.
    public void validateContact(
            EnrollmentDraft draft, ValidationContext context) {

        MessageContext messages = context.getMessageContext();
        String email = draft.getEmail();

        if (email == null || email.trim().isEmpty()) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("email")
                    .code("enrollment.email.required")
                    .defaultText("Vui lòng nhập email.")
                    .build());
        }
    }
}
~~~

**EnrollmentDraft** là lớp model tự định nghĩa; method **validateContact** chỉ minh họa quy tắc kiểm tra. Cách Web Flow tìm và gọi method validation theo state hoặc validator bean cần được cấu hình/đối chiếu đúng phiên bản. Ngoài kiểm tra rỗng, ứng dụng còn cần validator phù hợp cho định dạng email và quy tắc nghiệp vụ.

### 6.1. Thông báo lỗi có chặn transition không?

Trong quy trình form với validation được bật, lỗi validation thường khiến Web Flow giữ nguyên view-state để hiển thị lỗi. Tuy nhiên, cần xem riêng ba tình huống:

1. **Lỗi binding**: dữ liệu request không chuyển được sang kiểu model.
2. **Lỗi validation**: dữ liệu đã bind nhưng vi phạm ràng buộc.
3. **Kết quả nghiệp vụ thất bại ở action-state**: service trả outcome từ chối sau khi form đã hợp lệ.

Hai tình huống đầu thường được xử lý trong chu kỳ form. Tình huống thứ ba cần **đường event/transition** rõ ràng, ví dụ **planUnavailable** đưa về màn hình chọn gói. Không dùng một thông báo ERROR thay thế cho thiết kế điều hướng.

### 6.2. Back và Cancel có cần validation không?

Ở form **contact**, event **next** cần validate trước khi chuyển sang review. Nhưng nút **back** hoặc **cancel** có thể cần hoạt động ngay cả khi email chưa hợp lệ.

~~~xml
<view-state id="contact" view="enrollment/contact" model="draft">
    <binder>
        <binding property="email" required="true"/>
        <binding property="phone"/>
    </binder>

    <transition on="next" to="review"/>
    <transition on="back" to="profile" bind="false"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

**bind="false"** phù hợp với nút chuyển trang không cần nhận dữ liệu form. Nhưng khi bỏ binding, **những giá trị người dùng vừa nhập mà chưa được lưu vào model có thể không được giữ lại**. Chọn cách xử lý dựa trên trải nghiệm mong muốn thay vì gắn bind="false" cho mọi event.

## 7. i18n: thông báo được bản địa hóa như thế nào?

**Internationalization (i18n)** tách ý nghĩa message khỏi chuỗi hiển thị. Code Java chỉ phát **mã thông báo**; hệ thống giải mã đó thành text thích hợp theo locale của người dùng, dùng message source được cấu hình.

Một tổ chức file phổ biến trong Spring là:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

Ví dụ nội dung:

**messages_vi.properties**

~~~properties
enrollment.email.required=Vui lòng nhập địa chỉ email.
enrollment.email.invalid=Địa chỉ email không hợp lệ.
enrollment.draft.saved=Bản nháp của bạn đã được lưu.
enrollment.package.lowCapacity=Gói bạn chọn sắp hết chỗ.
enrollment.submit.unavailable=Gói này không còn chỗ. Vui lòng chọn lại.
~~~

**messages_en.properties**

~~~properties
enrollment.email.required=Please enter your email address.
enrollment.email.invalid=The email address is invalid.
enrollment.draft.saved=Your draft has been saved.
enrollment.package.lowCapacity=This package is almost full.
enrollment.submit.unavailable=This package is no longer available. Please select another.
~~~

Khi validator thêm message với code **enrollment.email.required**, view có thể hiển thị câu tiếng Việt hoặc tiếng Anh tùy locale và cách Spring Web Flow tích hợp với **MessageSource**.

### 7.1. Code, locale, fallback

Quá trình phân giải lý tưởng:

~~~mermaid
flowchart TD
    A["MessageResolver: code + arguments + defaultText"] --> B["Locale của request"]
    B --> C["MessageSource tra cứu resource bundle"]
    C --> D{"Tìm thấy mã?"}
    D -->|"Có"| E["Định dạng chuỗi theo locale"]
    D -->|"Không"| F["Dùng defaultText/fallback theo cấu hình"]
    E --> G["Message để view hiển thị"]
    F --> G
~~~

Không nên giả định ứng dụng tự phát hiện locale đúng chỉ vì tồn tại file **messages_vi.properties**. Cần kiểm tra **MessageSource**, cơ chế xác định locale trong Spring MVC, tích hợp với Web Flow và cách view render thông báo.

### 7.2. Đặt defaultText như thế nào?

**defaultText** giúp có phản hồi dễ hiểu khi message code chưa có bản dịch; nhưng nó không nên là lý do để bỏ quản lý file resource:

- Phát triển ban đầu có thể dùng defaultText để tránh màn hình trống.
- Khi sản phẩm có đa ngôn ngữ, bản dịch chính thức nên nằm trong message bundle.
- Test nên phát hiện **thiếu message code**, tránh để một locale âm thầm hiển thị nội dung tiếng Việt ở giao diện tiếng Anh.

Không bao giờ lấy một chuỗi lỗi kỹ thuật chưa được kiểm soát làm defaultText rồi hiển thị trực tiếp cho người dùng.

## 8. Thông báo có tham số: số lượng, thời gian và dữ liệu động

Nội dung như “Chỉ còn 2 chỗ trống” có dữ liệu thay đổi theo request. Không cần tạo nhiều message code cho mỗi giá trị; hãy dùng **message arguments** với cú pháp định dạng tương thích MessageSource.

Ví dụ resource bundle:

~~~properties
# messages_vi.properties
enrollment.package.remaining=Gói này chỉ còn {0} chỗ.

# messages_en.properties
enrollment.package.remaining=Only {0} seats remain in this package.
~~~

Một thông báo tham số có thể được xây dựng theo ý tưởng:

~~~java
int remainingSeats = 2;

context.getMessageContext().addMessage(new MessageBuilder()
        .warning()
        .code("enrollment.package.remaining")
        .args(remainingSeats)
        .defaultText("Gói này chỉ còn ít chỗ.")
        .build());
~~~

**Lưu ý:** hàm định dạng, cách xử lý dấu nháy, số nhiều và kiểu dữ liệu phải được kiểm tra theo MessageSource/MessageFormat và locale sử dụng. Với số lượng, tiền tệ, ngày giờ hoặc tên riêng, cần tránh ghép chuỗi trực tiếp trong Java rồi dịch từng mảnh.

### 8.1. Argument không được trở thành dữ liệu tin cậy

Nếu argument lấy từ người dùng, hệ thống vẫn phải xử lý đầu ra an toàn trong view để tránh XSS. Khi render HTML, **escape nội dung theo ngữ cảnh** và không coi text đã dịch hoặc argument là HTML đáng tin chỉ vì được đưa qua MessageContext.

## 9. Hiển thị message trong view

Spring Web Flow thường chạy cùng Spring MVC, nên việc hiển thị có thể dùng template engine và thư viện form binding của dự án, ví dụ JSP hoặc Thymeleaf. Tuy nhiên, **khả năng tự động đưa MessageContext vào các thuộc tính lỗi của template không giống nhau giữa các tích hợp**.

Mục tiêu của một màn hình contact nên là:

~~~text
Thông tin liên hệ

Email
[________________________]
  ! Vui lòng nhập địa chỉ email.    <-- ERROR, source=email

Số điện thoại
[________________________]

  [Quay lại] [Tiếp tục]
~~~

Trên trang review có thể là:

~~~text
Kiểm tra đăng ký

  ! Gói này chỉ còn 2 chỗ.         <-- WARNING toàn trang

Họ tên: ...
Email: ...
Gói: ...

  [Sửa thông tin] [Xác nhận]
~~~

Về mặt trình bày:

- **Field error** nên gần field và liên kết với input bằng cơ chế truy cập phù hợp (chẳng hạn aria-describedby).
- **Global error** nên có tiêu đề/nội dung rõ ràng, tránh yêu cầu người dùng tự tìm lỗi.
- **Warning** nên khác với error về cả chữ và biểu tượng; chỉ dùng màu sắc là chưa đủ cho khả năng truy cập.
- **Info** cần ngắn và chính xác; ví dụ “Đã lưu bản nháp” khác “Đăng ký hoàn tất”.

### 9.1. Ví dụ pseudocode của view

~~~text
messages = messagesFromFlowContext()

renderGlobalMessages(messages without source)
renderInput("email")
renderFieldMessages(messages with source == "email")
renderInput("packageCode")
renderFieldMessages(messages with source == "packageCode")
~~~

Đây là **pseudocode**, không phải API Web Flow template có sẵn. Cách lấy và nhóm message tùy giao diện, Spring MVC binding và thành phần view. Điểm cốt lõi là **đừng đánh mất source và severity** khi chuyển message sang giao diện.

## 10. Message trong action-state: thông báo và kết quả điều hướng

Giả sử người dùng chọn gói **STANDARD** và nhấn **confirm**. Service kiểm tra gói và trả kết quả **AVAILABLE** hoặc **SOLD_OUT**. Khi hết chỗ, cần vừa điều hướng về nơi chọn lại vừa giải thích lý do.

~~~mermaid
flowchart LR
    R["view-state review"] -->|"event confirm"| C["action-state checkAvailability"]
    C -->|"event available"| S["action-state save"]
    C -->|"event soldOut"| P["view-state choosePlan"]
    P --> M["Hiển thị message gói đã hết chỗ"]
~~~

Trong Java, code xử lý có thể thêm message **trước khi phát event**:

~~~java
public Event checkAvailability(RequestContext context) {
    if (availabilityService.isSoldOut(getSelectedPackage(context))) {
        context.getMessageContext().addMessage(new MessageBuilder()
                .error()
                .source("packageCode")
                .code("enrollment.submit.unavailable")
                .defaultText("Gói này không còn chỗ. Vui lòng chọn lại.")
                .build());

        return new Event(this, "soldOut");
    }
    return new Event(this, "available");
}
~~~

Đây là đoạn minh họa **cách phân biệt message và event**; các hàm **getSelectedPackage**, service, import và cấu hình action thực tế do ứng dụng cung cấp.

Một flow có thể mô tả các đường đi:

~~~xml
<action-state id="checkAvailability">
    <evaluate expression="enrollmentAction.checkAvailability(requestContext)"/>
    <transition on="available" to="save"/>
    <transition on="soldOut" to="choosePlan"/>
</action-state>
~~~

**Điểm cần kiểm thử:** MessageContext vừa nhận message trong action-state, nhưng nó có được đưa đến view-state **choosePlan** sau transition/redirect như mong muốn hay không còn phụ thuộc vòng đời message của Web Flow. Nếu phải giữ thông báo qua nhiều bước, cần thiết kế truyền trạng thái một cách tường minh. Không mặc định dùng MessageContext như hàng đợi thông báo bền vững.

## 11. Message, event và exception là ba khái niệm khác nhau

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Message** | Giải thích cho người dùng | “Gói không còn chỗ” |
| **Event** | Dẫn flow chọn transition | soldOut |
| **Exception** | Biểu diễn sự cố khi code/hạ tầng không xử lý như dự kiến | Database timeout |

Một service có thể **hoạt động đúng** nhưng trả outcome **SOLD_OUT**; action phát event **soldOut** và message giải thích. Ngược lại, nếu database bị timeout, hệ thống có thể chưa biết đơn có được ghi hay không. Không nên bắt mọi exception rồi phát message “hết chỗ”.

**Một exception không tự biến thành event error**, và **một message ERROR không tự trở thành exception**. Cơ chế xử lý exception và retry cần được thiết kế riêng, tránh tái thực hiện thao tác ghi khi chưa xác định được kết quả.

### 11.1. Thông báo lỗi kỹ thuật không lộ chi tiết

Người dùng nên thấy một câu như:

> Chúng tôi chưa xác nhận được kết quả. Vui lòng kiểm tra trạng thái yêu cầu hoặc thử lại theo hướng dẫn.

Nhóm vận hành mới cần log/trace chứa thông tin lỗi kỹ thuật phù hợp và mã tương quan. Không đưa tên bảng, URL nội bộ, stack trace, token hoặc thông tin nhận dạng nhạy cảm vào message xuất ra giao diện.

## 12. MessageContext và các luồng con (subflow)

Một flow cha có thể gọi subflow để xác thực số điện thoại. Flow con có thể:

- Hiển thị lỗi nhập mã xác thực tại field **verificationCode**.
- Báo WARNING khi sắp hết số lần thử.
- Trả outcome **verified**, **cancelled** hoặc **locked** cho flow cha.

Ví dụ sơ đồ:

~~~mermaid
flowchart TD
    P["Flow cha: review"] --> V["subflow-state verifyPhone"]
    V --> I["Flow con: enterCode"]
    I -->|"sai mã"| E["ERROR gắn verificationCode, giữ enterCode"]
    I -->|"đúng mã"| S["end-state verified"]
    S -->|"outcome verified"| C["Flow cha: confirm"]
    I -->|"quá số lần"| L["end-state locked"]
    L -->|"outcome locked"| R["Flow cha: hướng dẫn phục hồi"]
~~~

Flow con chịu trách nhiệm về message thuộc các màn hình của nó. Khi kết thúc, flow cha nên nhận **outcome và dữ liệu kết quả cần thiết** qua hợp đồng input/output rõ ràng. Nếu cần hiển thị lý do cụ thể ở flow cha, hãy truyền **mã kết quả hoặc dữ liệu có cấu trúc** và tạo message phù hợp ở view của flow cha; đừng giả định mọi message của một view con sẽ tự hiện ở view cha.

## 13. Mất message, lặp message và thông báo lỗi thời

Thông báo có giá trị khi đúng **thời điểm**, **vị trí** và **ngữ cảnh**.

| Vấn đề | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Message không xuất hiện | Template không render message source/severity hoặc chuyển state làm mất ngữ cảnh | Kiểm tra tích hợp view, vòng đời message và đường redirect |
| Lỗi vẫn hiện sau khi sửa | Message cũ chưa được cập nhật/xóa theo chu kỳ validation | Kiểm tra vòng đời MessageContext và tái validation |
| Hiện cùng lỗi hai lần | Nhiều thành phần cùng thêm message hoặc UI render cả field và global | Phân quyền phát message và lọc theo source |
| Chỉ thấy code thay vì bản dịch | Thiếu message source, thiếu mã hoặc locale không khớp | Bổ sung bundle, kiểm thử fallback |
| Thông báo xuất hiện ở state sai | Lưu trong session chung hoặc cố mang message qua nhiều state | Chọn phạm vi dữ liệu chính xác, không dùng session mặc định cho banner |
| Warning bị hiểu là error | UI dùng chung phong cách cho mọi severity | Phân biệt bằng nhãn, biểu tượng, ngữ nghĩa và thuộc tính truy cập |
| Có message “thành công” dù giao dịch thất bại | Thêm message trước khi service commit hoặc bỏ qua trạng thái bất định | Chỉ xác nhận thành công sau khi kết quả bền vững đã được biết |

### 13.1. Cảnh giác với nhiều tab và snapshot cũ

Vì một HTTP session có thể chứa nhiều flow execution, thông báo của tab A không nên vô tình lẫn vào form của tab B. Nếu có cơ chế lưu banner tùy chỉnh trong session, cần khóa theo đúng ngữ cảnh execution hoặc dùng phạm vi phù hợp.

Khi người dùng dùng Browser Back để mở trang cache, đó có thể là **giao diện cũ** mang message đã render từ trước. Điều này không có nghĩa MessageContext hiện tại vẫn chứa cùng thông báo. Phải kiểm thử Browser Back/Forward và submit bằng execution key cũ nếu sản phẩm cho phép tiếp tục từ snapshot.

## 14. Kiểm thử message theo ngữ cảnh và locale

Một bài test tốt cần xem **đúng severity, source, code và trạng thái flow**.

| Tình huống | Message mong đợi | Hành vi flow mong đợi |
| --- | --- | --- |
| Email trống tại contact | ERROR, source=email, code enrollment.email.required | Giữ contact |
| Email hợp lệ | Không còn lỗi email cũ | Có thể sang review |
| Gói sắp hết chỗ | WARNING, source=packageCode hoặc global tùy thiết kế | Cho tiếp tục nếu quy tắc nghiệp vụ cho phép |
| Gói đã hết chỗ khi confirm | ERROR nghiệp vụ, code enrollment.submit.unavailable | Đi đến state cho chọn lại |
| Bản nháp lưu thành công | INFO, code enrollment.draft.saved | Hiển thị ở view thích hợp |
| Locale tiếng Việt | Tra cứu bản dịch VI | Nội dung tiếng Việt |
| Locale tiếng Anh | Tra cứu bản dịch EN | Nội dung tiếng Anh |
| Thiếu mã dịch | Fallback có chủ đích, test phát hiện thiếu bundle | Không lỗi hiển thị khó hiểu |
| Service timeout sau ghi | Không khẳng định giao dịch đã thất bại | Phản hồi trạng thái chưa rõ / kiểm tra kết quả |

### 14.1. Kiểm thử riêng ở ba tầng

**Unit test cho validator:** gọi method validator với dữ liệu sai, kiểm tra message được tạo đúng source, code, severity và không bị tạo khi dữ liệu hợp lệ.

**Flow test:** khởi động flow ở view-state, phát event next với dữ liệu không hợp lệ, kiểm tra state không đổi; thử một business outcome để xác nhận transition và message phù hợp. Có thể dùng cơ sở hạ tầng test của Spring Web Flow tương ứng phiên bản thư viện.

**MVC/browser integration test:** thực sự submit form, kiểm tra message được render ở đúng vị trí, locale đúng, hoạt động qua redirect/Back/Forward, hiển thị được với công nghệ view đang dùng. Flow test thuần túy không thay thế test render.

### 14.2. Pseudocode kiểm thử

~~~text
flow = start("enrollment")
assertCurrentState(flow, "contact")

submit(flow, event="next", form={ email: "" })
assertCurrentState(flow, "contact")
assertMessage(severity="ERROR",
              source="email",
              code="enrollment.email.required")

submit(flow, event="next", form={ email: "an@example.com" })
assertCurrentState(flow, "review")

render(locale="vi")
assertLocalizedText("Vui lòng nhập địa chỉ email.")
~~~

Đây là **pseudocode**, không phải API Java có thể chạy nguyên văn. Khi triển khai, cần tách hai tình huống kiểm tra bản dịch: yêu cầu có lỗi và yêu cầu hợp lệ, tránh kỳ vọng lỗi email còn hiện sau khi đã sửa thành công.

## 15. Những lỗi thiết kế thường gặp

**Hardcode toàn bộ thông báo trong action.** Điều này khiến bản dịch, thống nhất thuật ngữ và kiểm tra thiếu locale khó quản lý. Ưu tiên code ổn định và message bundle.

**Dùng WARNING để che lỗi nghiệp vụ cần chặn.** Severity chỉ là một thuộc tính hiển thị; invariant của service phải được kiểm tra độc lập.

**Gắn mọi message vào source rỗng.** Người dùng khó biết cần sửa field nào. Hãy gắn source cho lỗi field và dùng message toàn trang cho kết quả chung.

**Xem MessageContext là kho thông báo vĩnh viễn.** MessageContext phục vụ chu kỳ xử lý/render của flow; nếu nghiệp vụ cần lịch sử phản hồi, hãy lưu dữ liệu riêng vào tầng phù hợp.

**Bắt exception kỹ thuật thành message validation.** Database timeout không phải lỗi email, và việc hiển thị “vui lòng sửa email” là sai. Hãy phân loại đúng sự cố.

**Tin rằng mọi template tự render message.** Tích hợp MessageContext với JSP/Thymeleaf/Spring MVC phải được cấu hình và kiểm thử; đặc biệt chú ý field/global message.

**Dùng message như nguồn sự thật nghiệp vụ.** Câu “đã đăng ký thành công” chỉ được phát khi service xác nhận thành công; message không tự bảo đảm transaction đã commit.

**Không kiểm tra các ngôn ngữ ngoài mặc định.** Một code thiếu bản dịch có thể rơi về defaultText khác ngôn ngữ hoặc hiện key không thân thiện.

## 16. Bài thực hành: phản hồi trong flow đặt lịch tư vấn

Giả sử flow **consultationBooking** gồm các bước **contact → chooseSlot → review → reserve → completed**. Yêu cầu nghiệp vụ:

1. Ở **contact**, email bắt buộc và phải đúng định dạng.
2. Ở **chooseSlot**, nếu còn dưới ba khung giờ thì hiển thị cảnh báo nhưng vẫn cho chọn.
3. Ở **review**, nếu khung giờ đã bị người khác đặt trước thì cho quay về chooseSlot, kèm lý do.
4. Sau khi lưu bản nháp thành công, hiển thị message thông tin.
5. Khi database timeout, không khẳng định lịch đã bị từ chối hay đặt thành công; cung cấp đường kiểm tra lại trạng thái.
6. Giao diện hỗ trợ tiếng Việt và tiếng Anh.

**Yêu cầu thực hiện:**

- Vẽ sơ đồ flow và chỉ rõ event nào chọn transition khi khung giờ hết chỗ.
- Thiết kế bảng message gồm **severity**, **source**, **code** và **nội dung VI/EN**.
- Viết method validator dùng **ValidationContext.getMessageContext()** cho email.
- Viết đoạn action phát outcome **slotUnavailable** khi service từ chối nghiệp vụ; message hiển thị ở bước chọn lại.
- Mô tả cách bảo toàn thông báo qua transition/redirect theo cấu hình thực tế.
- Viết ít nhất năm trường hợp test, bao gồm lỗi field, warning, hai locale, business outcome và timeout kỹ thuật.

Một bảng message đề xuất để bắt đầu:

| Code | Severity | Source | Nội dung tiếng Việt |
| --- | --- | --- | --- |
| booking.email.required | ERROR | email | Vui lòng nhập email. |
| booking.slot.limited | WARNING | slotId hoặc global | Hiện chỉ còn ít khung giờ. |
| booking.slot.unavailable | ERROR | slotId | Khung giờ đã được đặt. Vui lòng chọn lại. |
| booking.draft.saved | INFO | Global | Bản nháp đã được lưu. |
| booking.submit.unknown | ERROR hoặc thông báo trạng thái phù hợp | Global | Chưa xác nhận được kết quả. Vui lòng kiểm tra trạng thái yêu cầu. |

Đối với trường hợp cuối, lựa chọn severity, event và khả năng retry phải dựa trên chính sách phục hồi đã xác định; không dùng một lỗi chung làm căn cứ để gửi lại thao tác ghi mà không có idempotency.

## 17. Tổng kết và câu hỏi ôn tập

**MessageContext** tập hợp thông báo của quá trình xử lý Web Flow. **MessageBuilder** giúp khai báo severity, source, code, arguments và nội dung dự phòng. **INFO** cung cấp trạng thái, **WARNING** nhắc điều cần lưu ý, **ERROR** thể hiện vấn đề cần sửa hoặc thao tác không được chấp nhận; mức **FATAL** dành cho tình huống đặc biệt nghiêm trọng nếu ứng dụng sử dụng.

Trong một hành trình nhiều bước, hãy để **binding/validation** tạo lỗi form đúng field, **service** xác định kết quả nghiệp vụ, **event/transition** điều phối state và **MessageContext** cung cấp nội dung giải thích cho người dùng. **i18n** cho phép cùng một code được dịch theo locale qua message source. View phải hiển thị đúng source/severity và cần được kiểm thử qua các lần submit, redirect, thay đổi locale và phục hồi flow.

**Câu hỏi ôn tập:**

1. MessageContext khác flowScope ở điểm nào?
2. Severity WARNING có tự động chặn transition không? Tại sao?
3. Trong MessageBuilder, **source("email")** và **code("enrollment.email.required")** có vai trò gì khác nhau?
4. Nếu action thêm message ERROR nhưng vẫn trả event success, flow có tự chọn nhánh lỗi không?
5. Khi người dùng đổi locale từ VI sang EN, những thành phần nào phải phối hợp để message được dịch đúng?
6. Vì sao thông báo “đã lưu thành công” không nên được phát trước khi service biết kết quả của transaction?
7. Khi chuyển từ subflow sang flow cha, vì sao không nên giả định message của flow con sẽ luôn hiện ở màn hình cha?
