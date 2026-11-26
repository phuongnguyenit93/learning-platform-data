# messageContext, resourceBundle và dữ liệu bản địa hóa

Một flow nhiều bước thường phải phản hồi cho người dùng bằng nhiều loại thông điệp: lỗi nhập liệu, cảnh báo, thông báo thao tác thành công hoặc nội dung hướng dẫn theo ngôn ngữ đang sử dụng. Nếu viết trực tiếp câu chữ vào action hay flow XML, nội dung sẽ khó thay đổi và khó hỗ trợ nhiều locale. Spring Web Flow cung cấp hai biến biểu thức hữu ích cho công việc này: `messageContext` để ghi nhận và truy xuất thông điệp trong một flow execution, và `resourceBundle` để tra cứu nội dung đã được bản địa hóa.

Hai biến này có mục đích khác nhau. `messageContext` quản lý các thông điệp phát sinh khi flow chạy, thường gắn với một trường form hoặc với toàn màn hình. `resourceBundle` cung cấp câu chữ theo locale hiện tại từ các message bundle. Kết hợp chúng với cơ chế validation và data binding giúp flow hiển thị thông báo nhất quán mà không trộn câu chữ trình bày vào quy tắc nghiệp vụ.

## 1. Vì sao cần message context và message bundle?

Giả sử người dùng đặt phòng khách sạn qua các bước chọn phòng, nhập thông tin và xác nhận. Ở bước nhập thông tin, ngày nhận phòng có thể không hợp lệ; khi xác nhận, phòng có thể vừa được người khác đặt; sau khi hoàn tất, ứng dụng cần hiển thị mã đặt chỗ. Đây là các kết quả khác nhau và cần được trình bày phù hợp với ngữ cảnh.

Nếu action tự tạo chuỗi như `"Ngày nhận phòng không hợp lệ"`, ứng dụng sẽ khó chuyển sang tiếng Anh hoặc ngôn ngữ khác. Nếu validator chỉ trả `false`, view cũng không biết lỗi thuộc trường nào và cần hiển thị thông báo gì. Một mã thông điệp ổn định giải quyết được cả hai vấn đề: code biểu thị ý nghĩa, còn message bundle quyết định câu chữ theo locale.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `MessageContext` | Ghi nhận, phân loại và cung cấp các message trong flow execution | Lỗi gắn với `checkinDate`, thông báo đặt chỗ thành công |
| `MessageBuilder` | Tạo `MessageResolver` với severity, source, code, tham số và nội dung dự phòng | Tạo lỗi `booking.checkinDate.notFuture` |
| `MessageSource` / message bundle | Tra cứu nội dung theo mã và locale | Trả câu tiếng Việt hoặc tiếng Anh cho cùng một code |
| `resourceBundle` | Biến EL để truy cập message resource từ flow hoặc view | Lấy `booking.confirmed` trong flow XML |

Spring Web Flow tích hợp `MessageContext` với quá trình hiển thị view. Thông điệp có thể được render bởi view và được giữ qua các redirect của flow execution. Các mức thông điệp thường dùng gồm `info`, `warning` và `error`.

## 2. `messageContext` là gì?

`messageContext` là biến ngầm định mà Spring Web Flow cung cấp trong biểu thức của flow. Nó đại diện cho nơi ghi nhận message trong lần thực thi hiện tại. Có thể thêm message trực tiếp trong Java qua `MessageContext`, hoặc truyền biến này cho validator từ flow expression.

Một message có thể gắn với:

- **Một trường dữ liệu:** source là tên thuộc tính, ví dụ `checkinDate`. View có thể hiển thị lỗi ngay cạnh trường đó.
- **Toàn màn hình:** không chỉ định source. Đây thường là thông báo thành công hoặc lỗi chung.
- **Một mức độ:** thông tin, cảnh báo hoặc lỗi để view chọn cách trình bày phù hợp.

`MessageContext` cung cấp các thao tác như `addMessage`, `getAllMessages`, `getMessagesBySource`, `getMessagesByCriteria`, `hasErrorMessages` và `clearMessages`. Ứng dụng thường dùng `addMessage` để ghi nhận lỗi trong validator; view hoặc thành phần điều phối có thể kiểm tra message theo source hay theo severity khi cần.

## 3. Tạo message bằng `MessageBuilder`

`MessageBuilder` giúp tạo message theo cách fluent. Một message có thể chứa severity, source, code tra cứu, tham số và nội dung dự phòng nếu không tìm thấy code trong bundle.

Ví dụ thêm lỗi gắn với trường ngày nhận phòng:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public class BookingRules {

    public void checkDates(Booking booking, MessageContext messages) {
        if (booking.getCheckinDate() == null) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkinDate")
                    .code("booking.checkinDate.required")
                    .defaultText("Vui lòng nhập ngày nhận phòng.")
                    .build());
        }
    }
}
```

Các thành phần trong ví dụ:

- `error()` đánh dấu message là lỗi.
- `source("checkinDate")` gắn message với thuộc tính của model.
- `code(...)` chỉ ra khóa cần tra cứu trong message bundle.
- `defaultText(...)` cung cấp nội dung dự phòng nếu không có bản dịch cho code.
- `build()` tạo `MessageResolver` để `MessageContext` thêm vào context.

Có thể thêm thông báo toàn cục mà không chỉ định source:

```java
public void addConfirmationMessage(Booking booking, MessageContext messages) {
    messages.addMessage(new MessageBuilder()
            .info()
            .code("booking.confirmed")
            .arg(booking.getConfirmationNumber())
            .defaultText("Đặt phòng thành công. Mã xác nhận: {0}")
            .build());
}
```

Trong message bundle, placeholder `{0}` nhận tham số thứ nhất. Có thể truyền nhiều tham số bằng `arg(...)` hoặc `args(...)`. Khi tham số cũng là một message resolvable cần được bản địa hóa, API cung cấp `resolvableArg(...)` và `resolvableArgs(...)`.

Không nên tạo message bằng cách nối các mảnh câu đã dịch trong Java. Hãy giữ nguyên một câu hoàn chỉnh trong bundle và truyền các giá trị thay đổi qua tham số. Cách này giúp ngữ pháp và thứ tự từ có thể khác nhau giữa các ngôn ngữ.

## 4. Dùng messageContext trong validation của view-state

Spring Web Flow có quy ước tự động gọi validator cho model được khai báo trên `view-state`. Với model expression là `booking`, framework tìm bean validator tương ứng, thường có tên `bookingValidator`. Validator có thể khai báo phương thức theo state, ví dụ `validateEnterBookingDetails`, và nhận model cùng `ValidationContext`.

Ví dụ:

```java
import java.time.LocalDate;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Component;
import org.springframework.webflow.execution.ValidationContext;

@Component
public class BookingValidator {

    public void validateEnterBookingDetails(
            Booking booking, ValidationContext context) {

        MessageContext messages = context.getMessageContext();
        LocalDate today = LocalDate.now();

        if (booking.getCheckinDate() == null
                || !booking.getCheckinDate().isAfter(today)) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkinDate")
                    .code("booking.checkinDate.notFuture")
                    .defaultText("Ngày nhận phòng phải sau ngày hiện tại.")
                    .build());
        }

        if (booking.getCheckoutDate() == null
                || booking.getCheckinDate() == null
                || !booking.getCheckoutDate().isAfter(booking.getCheckinDate())) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkoutDate")
                    .code("booking.checkoutDate.afterCheckin")
                    .defaultText("Ngày trả phòng phải sau ngày nhận phòng.")
                    .build());
        }
    }
}
```

Trong ví dụ, `ValidationContext` cung cấp `MessageContext` để validator ghi lỗi. Khi một transition của view-state được kích hoạt và model cần validation, Spring Web Flow tự gọi phương thức có tên theo quy ước `validate${stateId}`. Nếu message lỗi được thêm, flow giữ người dùng ở view để họ sửa dữ liệu. Validator phải được đăng ký thành Spring bean; dùng `@Component` là một cách phổ biến khi component scanning đã được cấu hình.

Khai báo view-state có model và các binding cần thiết:

```xml
<view-state id="enterBookingDetails" model="booking">
    <binder>
        <binding property="checkinDate" required="true" />
        <binding property="checkoutDate" required="true" />
    </binder>
    <transition on="proceed" to="reviewBooking" />
    <transition on="back" to="chooseRoom" validate="false" />
</view-state>
```

Ở đây, event `proceed` chạy validation theo quy ước. Event `back` vẫn có thể bind dữ liệu nhưng bỏ qua model validation nhờ `validate="false"`, phù hợp khi người dùng chỉ muốn quay lại bước trước. Cần cân nhắc riêng yêu cầu nghiệp vụ: bỏ qua validation của view không được đồng nghĩa bỏ qua kiểm tra quyền hoặc quy tắc nghiệp vụ khi thực hiện thao tác quan trọng.

Ngoài phương thức gắn với state, validator có thể định nghĩa `validate(...)` mặc định cho model. Nếu tồn tại cả phương thức mặc định và phương thức theo state, phương thức theo state được gọi trước rồi đến phương thức mặc định. Cách này hữu ích khi có một số kiểm tra chung và các kiểm tra riêng cho từng màn hình.

## 5. Tra cứu message bundle bằng `resourceBundle`

`resourceBundle` là biến EL ngầm định dùng để truy cập message resource. Có thể dùng trong biểu thức của flow để lấy nội dung theo code:

```xml
<action-state id="prepareConfirmation">
    <set name="flashScope.notice" value="resourceBundle['booking.confirmed']" />
    <transition to="bookingConfirmed" />
</action-state>
```

Trong view JSF, tài nguyên cũng có thể được truy cập bằng EL:

```xml
<h:outputText value="#{resourceBundle['booking.confirmed']}" />
```

Với view Spring MVC dùng Spring tag library, có thể dùng `spring:message` để lấy message qua `MessageSource` mà ứng dụng cấu hình:

```jsp
<spring:message code="booking.confirmed" />
```

`resourceBundle` thuận tiện khi cần lấy một message trong biểu thức flow hoặc view. `messageContext` phù hợp khi cần tạo message theo kết quả xử lý, gắn message với trường và xác định severity. Không nên nhầm hai biến này: một biến là context chứa message của execution, biến còn lại là cách tra cứu câu chữ từ resource.

## 6. Tổ chức message bundle theo flow và locale

Spring Web Flow hỗ trợ message bundle riêng cho từng flow. Theo quy ước, đặt `messages.properties` trong thư mục chứa flow definition. Tạo thêm một file cho mỗi locale cần hỗ trợ. Ví dụ:

```text
WEB-INF/
  flows/
    booking/
      booking-flow.xml
      messages.properties
      messages_vi.properties
      messages_en.properties
      messages_vi_VN.properties
```

`messages.properties` là bundle mặc định. Các file locale cung cấp nội dung tương ứng, chẳng hạn `messages_vi.properties` cho tiếng Việt và `messages_en.properties` cho tiếng Anh. Nếu cần phân biệt biến thể theo vùng, có thể dùng tên đầy đủ như `messages_vi_VN.properties`. Việc chọn bundle phụ thuộc locale hiện hành và quy tắc fallback của cơ chế resource bundle.

Ví dụ nội dung mặc định:

```properties
# messages.properties
booking.title=Hotel booking
booking.checkinDate.required=Enter a check-in date.
booking.checkinDate.notFuture=Check-in date must be in the future.
booking.checkoutDate.afterCheckin=Check-out date must be after check-in date.
booking.confirmed=Your booking is confirmed. Reference: {0}
booking.checkinDate.typeMismatch=Enter the check-in date in the required format.
typeMismatch=The {0} field has an invalid value.
```

Nội dung tiếng Việt:

```properties
# messages_vi.properties
booking.title=Đặt phòng khách sạn
booking.checkinDate.required=Vui lòng nhập ngày nhận phòng.
booking.checkinDate.notFuture=Ngày nhận phòng phải sau ngày hiện tại.
booking.checkoutDate.afterCheckin=Ngày trả phòng phải sau ngày nhận phòng.
booking.confirmed=Đặt phòng thành công. Mã xác nhận: {0}
booking.checkinDate.typeMismatch=Ngày nhận phòng không đúng định dạng yêu cầu.
typeMismatch=Trường {0} có giá trị không hợp lệ.
```

Các bundle dùng cùng bộ message code nhưng mỗi locale có câu chữ riêng. Nếu flow dùng chung nhiều message với các flow khác, có thể tổ chức thêm một `MessageSource` ở cấp ứng dụng. Với tài nguyên riêng của một hành trình, bundle đặt trong thư mục flow giúp nội dung gần với flow sử dụng nó và giảm nguy cơ trùng lẫn khóa.

## 7. Locale được chọn như thế nào?

Message resolver cần một `MessageSource` và locale hiện hành để giải quyết message. Trong ứng dụng Spring MVC, locale của request thường được quyết định bởi cấu hình locale resolver của ứng dụng, chẳng hạn dựa trên header `Accept-Language`, cookie hoặc session. Cấu hình cần bảo đảm locale được sử dụng nhất quán khi người dùng đi qua các request của flow.

Ví dụ, nếu locale hiện tại là `vi`, code `booking.confirmed` được tra trong bundle tiếng Việt trước theo quy tắc locale. Nếu không có bản dịch phù hợp, cơ chế resource bundle có thể tiếp tục tìm bundle mặc định. Vì vậy, nên luôn có `messages.properties` làm fallback và kiểm tra các locale thực tế mà ứng dụng hỗ trợ.

Nếu cho phép người dùng đổi ngôn ngữ giữa một flow đang chạy, cần bảo đảm locale mới được áp dụng cho request tiếp theo. Không lưu câu đã dịch vào flow scope quá sớm nếu nội dung cần phản ánh locale hiện tại ở mỗi lần render. Thông thường, lưu code cùng tham số rồi giải quyết message khi cần hiển thị sẽ linh hoạt hơn.

Với cấu hình `MessageSource` dùng chung trong Spring, có thể khai báo basename và encoding rõ ràng. Ví dụ cấu hình Java:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.support.ResourceBundleMessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MessageConfiguration {

    @Bean
    public MessageSource messageSource() {
        ResourceBundleMessageSource source = new ResourceBundleMessageSource();
        source.setBasename("i18n/messages");
        source.setDefaultEncoding("UTF-8");
        return source;
    }
}
```

Trong ví dụ, basename `i18n/messages` tương ứng các file bundle trong classpath như `i18n/messages.properties` và `i18n/messages_vi.properties`. Đây là cấu hình cho message dùng chung của ứng dụng; bundle riêng của flow vẫn được tổ chức theo thư mục flow theo quy ước của Spring Web Flow. Nếu ứng dụng đã có `MessageSource` do Spring Boot hoặc cấu hình XML cung cấp, hãy bổ sung basename và encoding vào cấu hình hiện tại thay vì tạo nhiều bean cùng tên.

## 8. Message tự sinh từ data binding và type conversion

Spring Web Flow có thể tạo message khi bind dữ liệu từ request vào model. Ví dụ, thuộc tính `checkinDate` có kiểu ngày nhưng người dùng nhập một chuỗi không thể chuyển đổi. Framework ghi nhận lỗi chuyển đổi và tra message trong bundle.

Với model `Booking` và thuộc tính `checkinDate`, Web Flow thử khóa có dạng:

```properties
booking.checkinDate.typeMismatch=Ngày nhận phòng không đúng định dạng yyyy-MM-dd.
```

Trong đó:

- `booking` là tên ngắn của lớp model `Booking`.
- `checkinDate` là thuộc tính nhận dữ liệu.
- `typeMismatch` là mã lỗi chuyển đổi kiểu.

Nếu không tìm thấy khóa chi tiết, Web Flow thử khóa tổng quát theo error code và truyền tên trường làm tham số:

```properties
typeMismatch=Trường {0} có kiểu dữ liệu không hợp lệ.
```

Cơ chế này cho phép cung cấp thông báo riêng cho từng thuộc tính mà không cần tự viết action cho mọi lỗi binding. Nên bổ sung các khóa chi tiết cho những trường quan trọng và giữ khóa tổng quát để tránh trường hợp người dùng thấy thông báo thô hoặc không thân thiện.

Lỗi binding và lỗi validation có liên quan nhưng khác nhau. Binding lỗi khi không thể chuyển dữ liệu request thành kiểu của model; validation lỗi khi dữ liệu đã bind được nhưng không thỏa điều kiện. Ví dụ, chuỗi `abc` không chuyển được thành ngày là lỗi `typeMismatch`; một ngày hợp lệ về định dạng nhưng nằm trong quá khứ là lỗi quy tắc `booking.checkinDate.notFuture`.

## 9. Hiển thị message trong view

View nên hiển thị lỗi tại đúng trường khi message có source, và hiển thị thông báo chung ở khu vực phù hợp khi source không được chỉ định. Cách render cụ thể phụ thuộc công nghệ view:

- Với JSF, có thể dùng các component message của JSF để hiển thị message gắn với component hoặc toàn trang.
- Với JSP và Spring MVC, Spring form/tag library có thể hiển thị lỗi binding và `spring:message` tra nội dung từ `MessageSource`.
- Với Thymeleaf hoặc template engine khác, cần tích hợp cơ chế hiển thị lỗi của model và tra message theo cấu hình của view layer.

Không nên giả định mọi template engine tự động hiển thị toàn bộ `MessageContext`. Hãy kiểm tra cách view tích hợp với Spring Web Flow trong ứng dụng, đặc biệt khi cần hiển thị message do action thêm vào chứ không chỉ lỗi binding của form.

Nên phân biệt rõ kiểu message trong giao diện: lỗi cần được gắn với trường hoặc vùng thông báo dễ nhận biết; cảnh báo cần giải thích điều kiện cần chú ý; thông tin thành công nên xuất hiện ở khu vực không gây nhầm lẫn với lỗi. Không chỉ dựa vào màu sắc để phân biệt; nội dung và nhãn hỗ trợ cũng cần rõ ràng.

## 10. Quy ước đặt message code và tham số

Một quy ước đặt tên tốt giúp tìm message dễ dàng và tránh va chạm giữa các flow. Có thể dùng cấu trúc theo domain, đối tượng, thuộc tính và tình huống:

```text
booking.checkinDate.required
booking.checkinDate.notFuture
booking.checkoutDate.afterCheckin
booking.confirmed
booking.cancelled
```

Nên tuân thủ một số nguyên tắc:

1. Dùng code ổn định theo ý nghĩa, không dựa trên câu chữ đã dịch.
2. Dùng cùng một code cho cùng một ý nghĩa trong các locale.
3. Đưa giá trị thay đổi vào tham số `{0}`, `{1}`, ... thay vì nối chuỗi.
4. Cung cấp `defaultText` hữu ích khi tạo message từ Java, nhất là trong giai đoạn phát triển hoặc khi thiếu bản dịch.
5. Giữ bundle mặc định đầy đủ để locale chưa được dịch vẫn có nội dung fallback.
6. Không dùng message code để quyết định quyền truy cập hoặc trạng thái nghiệp vụ; code chỉ phục vụ tra cứu nội dung.
7. Không đặt dữ liệu bí mật, token, thông tin thanh toán hoặc dữ liệu cá nhân nhạy cảm vào message hay log.

Khi cần thay đổi câu chữ, chỉ cần sửa bundle tương ứng. Khi thay đổi ý nghĩa nghiệp vụ, hãy cập nhật code và các kiểm thử liên quan để bảo đảm flow vẫn ánh xạ đúng kết quả.

## 11. Kiểm thử message và bản địa hóa

Kiểm thử nên bao phủ cả việc tạo message lẫn việc chọn đúng nội dung theo locale.

**Kiểm thử validator:** tạo model với dữ liệu hợp lệ và không hợp lệ, gọi validator, rồi xác minh message được thêm với source và severity đúng. Kiểm tra `hasErrorMessages()` khi có lỗi và bảo đảm không phát sinh lỗi cho dữ liệu hợp lệ.

**Kiểm thử tra cứu bundle:** tra cùng một code với locale tiếng Việt và tiếng Anh, xác minh câu chữ tương ứng và các tham số được thay thế đúng thứ tự. Kiểm tra cả khi code thiếu bản dịch ở locale cụ thể để bảo đảm fallback có nội dung.

**Kiểm thử binding:** gửi giá trị không thể chuyển đổi cho thuộc tính có kiểu ngày hoặc số, xác minh framework tạo lỗi phù hợp và message key chi tiết được chọn trước khóa tổng quát.

**Kiểm thử flow:** khởi chạy flow, gửi event làm validation thất bại, xác minh người dùng vẫn ở view hiện tại và message được hiển thị. Sau khi sửa dữ liệu và gửi lại, xác minh flow chuyển đến state tiếp theo và không còn message lỗi cũ ngoài dự kiến.

**Kiểm thử locale qua nhiều request:** chọn một locale, tiếp tục flow qua nhiều state và xác minh message vẫn theo locale đó. Nếu ứng dụng cho phép đổi locale trong flow, kiểm tra request kế tiếp sử dụng locale mới theo chính sách của ứng dụng.

Một danh sách tình huống kiểm thử thực tế:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Ngày nhận phòng nằm trong quá khứ | Có message code `booking.checkinDate.notFuture`, source là `checkinDate`, severity là error |
| Người dùng nhập chữ vào trường ngày | Có message type conversion phù hợp với `booking.checkinDate.typeMismatch` hoặc khóa tổng quát `typeMismatch` |
| Đặt phòng thành công | Có thông báo `booking.confirmed` với mã xác nhận được truyền đúng tham số |
| Locale là tiếng Việt | Nội dung lấy từ bundle tiếng Việt khi có bản dịch |
| Locale không có bản dịch riêng | Nội dung fallback được giải quyết từ bundle mặc định |
| Người dùng quay lại bước trước | Validation chỉ chạy theo cấu hình của transition, message không làm sai hành trình |

## 12. Lỗi thiết kế thường gặp

- **Viết câu đã dịch trực tiếp trong Java:** câu chữ bị gắn với code, khó hỗ trợ locale mới. Hãy dùng message code và bundle.
- **Dùng `resourceBundle` như nơi lưu trạng thái:** bundle chỉ phục vụ tra cứu nội dung; hãy dùng `messageContext` để ghi message phát sinh khi flow chạy.
- **Không gắn source cho lỗi trường:** view khó xác định lỗi cần hiển thị ở đâu. Hãy dùng source là tên thuộc tính của model.
- **Chỉ tạo bundle tiếng Việt:** locale khác hoặc code thiếu bản dịch có thể không có nội dung fallback. Hãy duy trì `messages.properties` mặc định.
- **Nối chuỗi với tham số đã dịch:** cấu trúc câu không linh hoạt giữa các ngôn ngữ. Hãy dùng placeholder trong một câu hoàn chỉnh.
- **Nhầm lỗi binding với lỗi nghiệp vụ:** lỗi chuyển kiểu và lỗi điều kiện dữ liệu cần message code riêng.
- **Lưu câu đã dịch quá sớm vào flow scope:** người dùng đổi locale có thể vẫn thấy câu theo ngôn ngữ cũ. Ưu tiên giữ code và tham số rồi tra cứu khi hiển thị.
- **Dùng message làm cơ chế bảo mật:** message chỉ giải thích kết quả; quyền truy cập và quyết định nghiệp vụ phải được kiểm tra độc lập.

## 13. Nguyên tắc áp dụng

1. Dùng `messageContext` để ghi nhận thông tin, cảnh báo và lỗi phát sinh trong flow execution.
2. Dùng `MessageBuilder` để xác định severity, source, code, tham số và nội dung dự phòng.
3. Để validator thêm lỗi vào `MessageContext`; tận dụng quy ước validator theo model và view-state của Spring Web Flow.
4. Dùng `resourceBundle` để tra nội dung theo code trong biểu thức flow hoặc view.
5. Tổ chức `messages.properties` mặc định và các bundle theo locale trong thư mục flow khi nội dung chỉ thuộc flow đó.
6. Bảo đảm locale được chọn nhất quán qua các request và bundle mặc định có nội dung fallback.
7. Kiểm thử lỗi binding, validation, message source, tham số và chuyển locale.

Trong Spring Web Flow, `messageContext` giúp flow quản lý thông điệp phát sinh theo từng execution, còn `resourceBundle` cung cấp câu chữ theo ngôn ngữ hiện hành. Khi dùng message code ổn định, gắn lỗi với đúng source và tổ chức bundle có fallback, ứng dụng có thể thay đổi nội dung hiển thị hoặc bổ sung locale mà không phải viết lại logic điều hướng và nghiệp vụ.
