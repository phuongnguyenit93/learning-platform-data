# Thông báo lỗi khi dữ liệu không thể chuyển đổi

Trong chương **Chuyển đổi và định dạng**, bài này hướng dẫn cách xử lý khi Spring Web Flow nhận dữ liệu từ form nhưng không thể chuyển dữ liệu đó sang kiểu của model. Ví dụ, người dùng nhập `31/02/2026` vào trường ngày, nhập `abc` vào trường số tiền hoặc dùng định dạng ngày khác với định dạng ứng dụng đang chờ. Mục tiêu là giữ người dùng ở đúng bước, chỉ rõ trường bị lỗi, hiển thị thông báo dễ hiểu và cho phép họ sửa dữ liệu.

Spring Web Flow quản lý state, event và transition của quy trình nhiều bước; Spring Binding và Spring ConversionService đảm nhiệm việc gắn dữ liệu request vào model và chuyển đổi kiểu. Khi binding thất bại, flow cần xử lý thông báo ở view state hiện tại thay vì tiếp tục với model chưa hợp lệ. Đây là một phần quan trọng khi tích hợp Spring MVC, form binding và validation trong module `SPRING_WEB_FLOW`.

## 1. Phân biệt lỗi chuyển đổi với lỗi validation

Hai nhóm lỗi thường xuất hiện gần nhau nhưng có nguyên nhân khác nhau:

| Loại lỗi | Ví dụ | Thời điểm phát hiện |
| --- | --- | --- |
| Lỗi chuyển đổi (conversion/binding) | Chuỗi `abc` không chuyển được thành `BigDecimal`; `31/02/2026` không phải ngày hợp lệ. | Khi dữ liệu request được bind vào thuộc tính model. |
| Lỗi validation | Ngày `15/12/2026` chuyển đổi thành `LocalDate` thành công nhưng nằm ngoài thời hạn đặt. | Sau khi dữ liệu đã được chuyển thành kiểu phù hợp và được kiểm tra quy tắc. |

Ví dụ, thuộc tính `amount` có kiểu `BigDecimal`. Nếu request gửi `"abc"`, ConversionService không thể tạo số và phát sinh lỗi binding. Nếu request gửi `"125000"` và chuyển đổi thành công, nhưng số tiền nhỏ hơn mức tối thiểu của nghiệp vụ, đó là lỗi validation.

Không nên gộp hai nhóm thành một thông báo chung. Lỗi chuyển đổi cần giải thích định dạng mong đợi; lỗi validation cần giải thích quy tắc nghiệp vụ. Khi phân loại đúng, người dùng biết phải sửa cách nhập hay thay đổi giá trị.

## 2. Khai báo model và binder trong view state

Giả sử flow đặt lịch có model `Booking` với hai thuộc tính `startDate` kiểu `LocalDate` và `amount` kiểu `BigDecimal`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public class Booking {
    private LocalDate startDate;
    private BigDecimal amount;

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Khai báo model và chỉ định các thuộc tính được phép bind trong flow:

```xml
<var name="booking" class="com.example.booking.Booking" />

<view-state id="editBooking" view="booking/edit" model="booking">
    <binder>
        <binding property="startDate" required="true" />
        <binding property="amount" required="true" />
    </binder>

    <transition on="submit" to="reviewBooking" />
</view-state>

<view-state id="reviewBooking" view="booking/review" />
```

Binder xác định những thuộc tính mà form được phép cập nhật và có thể đánh dấu trường bắt buộc. Khi người dùng gửi event `submit`, Web Flow bind các request parameter vào model. Nếu một giá trị không thể chuyển đổi, binding error được ghi nhận và view state có thể được render lại để người dùng sửa; flow không nên đi tiếp đến bước review với dữ liệu chưa bind hợp lệ.

Giới hạn danh sách thuộc tính trong binder còn giúp tránh mass assignment vào các trường nội bộ như `status`, `ownerId` hoặc `approved`. Chỉ mở binding cho dữ liệu thực sự do người dùng được phép cung cấp.

## 3. Hiển thị lỗi ngay tại trường nhập liệu

Trong JSP, Spring Form tag liên kết với model attribute và render lỗi theo đường dẫn thuộc tính:

```jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post" modelAttribute="booking">
    <div>
        <label for="startDate">Ngày bắt đầu (dd/MM/yyyy)</label>
        <form:input path="startDate" id="startDate" />
        <form:errors path="startDate" cssClass="field-error" />
    </div>

    <div>
        <label for="amount">Số tiền</label>
        <form:input path="amount" id="amount" />
        <form:errors path="amount" cssClass="field-error" />
    </div>

    <form:errors path="*" cssClass="form-error" />
    <input type="hidden" name="_flowExecutionKey" value="${flowExecutionKey}" />
    <button type="submit" name="_eventId_submit" value="true">Tiếp tục</button>
</form:form>
```

`form:errors` với `path="startDate"` hiển thị lỗi gắn với trường ngày; `path="amount"` hiển thị lỗi của trường số tiền. `path="*"` có thể dùng để hiển thị các lỗi tổng quát của form. Không chỉ tô viền đỏ mà không có nội dung giải thích; thông báo cần nói định dạng nào được chấp nhận.

Khi render lại view sau binding error, cần giữ lại dữ liệu người dùng đã nhập nếu có thể. Với trường ngày không chuyển đổi được, model không có một `LocalDate` hợp lệ để hiển thị lại qua `form:input`; tùy cơ chế binding/view, cần kiểm tra rằng giá trị request gốc và thông báo lỗi vẫn được giữ trong binding result để người dùng thấy nội dung đã nhập và sửa trực tiếp.

## 4. Cấu hình ConversionService cho flow

Spring ConversionService cung cấp các converter và formatter dùng để chuyển đổi giá trị giữa chuỗi request và kiểu Java. Có thể đăng ký một `FormattingConversionServiceFactoryBean` rồi liên kết nó với flow builder services:

```xml
<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="formatters">
        <set>
            <bean class="com.example.web.LocalDateFormatter" />
        </set>
    </property>
</bean>

<webflow:flow-builder-services id="flowBuilderServices"
                                conversion-service="conversionService" />

<webflow:flow-registry id="flowRegistry"
                       base-path="/WEB-INF/flows"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location-pattern value="/**/*-flow.xml" />
</webflow:flow-registry>
```

Registry dùng flow builder services để tạo flow. Khi cấu hình view factory hoặc validator riêng, có thể khai báo chúng cùng `flow-builder-services` theo phiên bản schema của dự án. Bảo đảm flow registry thực sự tham chiếu builder services có ConversionService mà ứng dụng vừa cấu hình; tạo bean nhưng không kết nối vào registry sẽ không thay đổi quá trình binding.

Trong dự án Spring MVC, có thể dùng chung quy ước chuyển đổi giữa form MVC và flow nếu hai bên được cấu hình với cùng ConversionService. Việc dùng chung giúp ngày, số tiền và enum được đọc theo cùng quy tắc ở các màn hình thông thường lẫn các bước trong flow.

## 5. Dùng annotation định dạng cho model

Với các kiểu phổ biến, annotation của Spring có thể mô tả định dạng trực tiếp trên thuộc tính:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class Booking {

    @DateTimeFormat(pattern = "dd/MM/yyyy")
    private LocalDate startDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    // getters and setters
}
```

`@DateTimeFormat` cho biết định dạng chuỗi ngày cần parse và định dạng khi in. `@NumberFormat` mô tả cách parse/in số. Những annotation này cần được hỗ trợ bởi FormattingConversionService đang được sử dụng trong flow.

Pattern `dd/MM/yyyy` là định dạng cố định. Nếu ứng dụng cần định dạng thay đổi theo locale, có thể dùng formatter dựa trên `Locale` thay vì khóa cứng pattern. Ngoài ra, trường HTML `input type="date"` thường gửi giá trị theo định dạng ISO `yyyy-MM-dd`; nếu dùng kiểu input này, converter phải chấp nhận định dạng ISO thay vì mong đợi `dd/MM/yyyy` từ trình duyệt.

## 6. Viết Formatter để kiểm soát parse và print

Khi định dạng mặc định không đáp ứng yêu cầu, viết một `Formatter<T>`. Formatter có hai nhiệm vụ: `parse` chuyển chuỗi người dùng nhập thành object; `print` chuyển object thành chuỗi để hiển thị.

```java
import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.FormatStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

public class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale) throws ParseException {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale);
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException ex) {
            ParseException parseException = new ParseException(
                    "Ngày không đúng định dạng theo ngôn ngữ đang chọn.",
                    Math.max(ex.getErrorIndex(), 0));
            parseException.initCause(ex);
            throw parseException;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale)
                .format(value);
    }
}
```

Formatter nhận `Locale` nên có thể parse/print theo ngôn ngữ hiện tại. Khi parse thất bại, nó ném `ParseException` với nguyên nhân gốc được giữ lại; ConversionService dùng lỗi này để tạo binding error. Không trả về một ngày mặc định khi parse sai, vì như vậy người dùng có thể vô tình xác nhận một ngày khác với nội dung đã nhập.

Nếu chỉ cần chuyển đổi một kiểu sang kiểu khác mà không cần định dạng theo locale, có thể đăng ký `Converter<S,T>`. Converter nên báo lỗi rõ ràng khi đầu vào không hợp lệ. Dùng Formatter cho dữ liệu hiển thị/nhập liệu có quy tắc locale; dùng Converter cho chuyển đổi kiểu tổng quát.

## 7. Viết thông báo lỗi dễ hiểu bằng MessageSource

Spring Binding tạo message code cho lỗi chuyển đổi. Các code thường được phân giải từ cụ thể đến tổng quát, dựa trên loại lỗi, tên object, tên field và kiểu đích. Ví dụ với model `booking`, field `startDate` có kiểu `LocalDate`, có thể khai báo các mức thông báo trong `messages.properties`:

```properties
typeMismatch.booking.startDate=Ngày bắt đầu phải theo định dạng dd/MM/yyyy.
typeMismatch.startDate=Vui lòng nhập ngày hợp lệ theo định dạng dd/MM/yyyy.
typeMismatch.java.time.LocalDate=Giá trị ngày không hợp lệ.
typeMismatch=Giá trị nhập không đúng định dạng.
```

Với trường `amount`:

```properties
typeMismatch.booking.amount=Số tiền phải là một giá trị số hợp lệ.
```

Các mã trên là ví dụ theo quy tắc message code phổ biến của Spring; object name, field name và target type thực tế phải khớp model và ConversionService của ứng dụng. Nếu thông báo không được hiển thị, hãy kiểm tra binding error code thực tế và cấu hình `MessageSource` mà MVC/Web Flow sử dụng. Đừng giả định mọi lỗi custom formatter đều có đúng một mã giống nhau ở mọi phiên bản.

Thông báo tốt nên trả lời ba điều: trường nào có lỗi, định dạng mong đợi là gì và một ví dụ hợp lệ. Tránh hiển thị nguyên văn stack trace hoặc tên exception Java cho người dùng.

## 8. Thêm lỗi nghiệp vụ sau khi chuyển đổi thành công

ConversionService chỉ xác nhận có thể chuyển chuỗi sang kiểu Java. Nó không biết ngày đặt còn nằm trong thời hạn hay số tiền có đạt mức tối thiểu hay không. Sau binding, validator nghiệp vụ cần kiểm tra các quy tắc đó.

Ví dụ một validator thêm lỗi vào `MessageContext`:

```java
import java.time.LocalDate;
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public class BookingValidator {

    public void validate(Booking booking, MessageContext messages) {
        if (booking.getStartDate() != null
                && booking.getStartDate().isBefore(LocalDate.now())) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("startDate")
                    .code("booking.startDate.past")
                    .defaultText("Ngày bắt đầu phải từ hôm nay trở đi.")
                    .build());
        }
    }
}
```

Thông báo này là lỗi nghiệp vụ trên một `LocalDate` đã được chuyển đổi thành công. Nó khác với lỗi `typeMismatch` khi chuỗi ngày không parse được. Flow có thể gọi validator ở bước submit theo cách cấu hình validator của dự án; chỉ cho phép transition sang bước tiếp theo khi không còn lỗi. Nếu dùng validation tích hợp của view state, hãy cấu hình validator theo flow builder services và tuân theo quy ước validation của phiên bản đang chạy.

Với quy tắc cần kiểm tra lại ngay trước thao tác xác nhận như còn chỗ, giá hiện tại hoặc quyền đặt, service nghiệp vụ vẫn phải kiểm tra lần nữa. Validation của form không thay thế kiểm tra ở ranh giới lưu dữ liệu.

## 9. Xử lý lỗi chuyển đổi trong hành trình nhiều bước

Một flow nhập thông tin đặt lịch có thể được mô hình hóa như sau:

```xml
<view-state id="editBooking" view="booking/edit" model="booking">
    <binder>
        <binding property="startDate" required="true" />
        <binding property="amount" required="true" />
    </binder>
    <transition on="submit" to="reviewBooking" />
</view-state>

<view-state id="reviewBooking" view="booking/review">
    <transition on="confirm" to="complete" />
</view-state>

<end-state id="complete" view="booking/complete" />
```

Luồng xử lý thông thường:

1. Người dùng mở `editBooking`; Web Flow cung cấp model `booking` cho view.
2. Người dùng gửi event `submit` cùng các request parameter.
3. Binder chuyển `startDate` thành `LocalDate` và `amount` thành `BigDecimal`.
4. Nếu conversion thành công, các bước validation được thực hiện theo cấu hình và flow có thể chuyển đến `reviewBooking`.
5. Nếu conversion thất bại, lỗi được gắn với field trong message context/binding result; view nhập liệu được hiển thị lại để người dùng sửa.
6. Sau khi người dùng sửa và gửi lại, flow tiếp tục khi dữ liệu có thể bind và vượt qua validation.

Nếu ứng dụng cần nhánh riêng cho lỗi nghiệp vụ, hãy dùng validator hoặc service trả kết quả có tên rõ ràng. Không nên dùng một transition `error` chung để xử lý mọi lỗi chuyển đổi nếu framework đã giữ người dùng ở view state và gắn lỗi cho đúng field.

## 10. Kiểm thử conversion và thông báo

Kiểm thử nên xác nhận cả quá trình parse, thông báo và hành vi của flow:

| Lớp kiểm thử | Trường hợp | Kết quả cần xác nhận |
| --- | --- | --- |
| Formatter unit test | Ngày hợp lệ theo locale | Parse ra đúng `LocalDate`; print cho ra chuỗi theo locale. |
| Formatter unit test | Ngày sai định dạng hoặc không tồn tại | Ném `ParseException`; không trả về ngày mặc định. |
| ConversionService test | Chuỗi số hợp lệ và không hợp lệ | Chuyển đổi đúng hoặc phát sinh conversion failure. |
| Flow execution test | Gửi ngày sai qua view state | Flow giữ người dùng ở view nhập liệu và có field error. |
| Flow execution test | Gửi ngày hợp lệ nhưng vi phạm nghiệp vụ | Conversion thành công, validator tạo lỗi nghiệp vụ riêng. |
| MVC integration test | Render lại form sau lỗi | Thông báo đúng field, đúng ngôn ngữ và dữ liệu người dùng có thể sửa. |

Một flow execution test có thể khởi chạy flow bằng `MockExternalContext`, đặt request parameter sai rồi resume execution. Xác nhận state vẫn là `editBooking`, message context có error và state `reviewBooking` chưa được kích hoạt. Tiếp đó gửi dữ liệu hợp lệ và xác nhận flow chuyển tiếp bình thường.

Với thông báo theo locale, chạy ít nhất hai test locale được ứng dụng hỗ trợ. Đừng chỉ kiểm tra rằng có một message; hãy xác nhận nội dung thông báo và định dạng chuỗi mà người dùng cần nhập. Trong MVC integration test, kiểm tra view thực tế vì message code có thể được tạo đúng nhưng `MessageSource` hoặc tag hiển thị lỗi chưa được cấu hình.

## 11. Lỗi thường gặp và cách khắc phục

- **Ngày nhập theo `dd/MM/yyyy` nhưng converter chờ ISO:** đồng bộ pattern giữa Formatter, annotation và hướng dẫn trên form; kiểm tra thêm nếu dùng `input type="date"`.
- **Số tiền dùng dấu phẩy nhưng parser hiểu dấu chấm:** cấu hình locale và NumberFormatter thống nhất; không tự thay dấu phân cách bằng phép thay chuỗi tùy tiện.
- **Đã tạo Formatter nhưng flow vẫn dùng converter mặc định:** kiểm tra `conversion-service` được gắn vào `flow-builder-services` của registry đang chạy.
- **Thông báo lỗi chỉ hiện ở đầu form:** dùng `form:errors` với đúng field path và có thể thêm vùng tổng hợp lỗi.
- **Thông báo chỉ hiện mã `typeMismatch`:** cấu hình MessageSource với code phù hợp và xác nhận object name/field name thực tế.
- **Flow vẫn đi tiếp khi dữ liệu không bind được:** kiểm tra cách view state nhận event, binder và validator; không bỏ qua binding errors trong custom action.
- **Lỗi conversion bị hiển thị như lỗi nghiệp vụ:** tách message code và quy tắc validation; giải thích định dạng mong đợi riêng.
- **Parse sai nhưng hệ thống tự điền giá trị mặc định:** loại bỏ fallback che lỗi; chỉ dùng mặc định khi nghiệp vụ xác định trường đó là tùy chọn.

## 12. Checklist trước khi hoàn tất form

- Model có kiểu dữ liệu phù hợp với giá trị nghiệp vụ, chẳng hạn `LocalDate` và `BigDecimal`.
- Binder chỉ cho phép các thuộc tính người dùng được cập nhật.
- ConversionService/Formatter được đăng ký và thực sự gắn với flow registry.
- Định dạng hiển thị, định dạng parse và locale trên giao diện thống nhất.
- Lỗi conversion được gắn với đúng field và có thông báo dễ hiểu.
- Lỗi validation được phân biệt với lỗi conversion.
- Flow không chuyển sang bước tiếp theo khi dữ liệu bind hoặc validation thất bại.
- Unit test, flow execution test và MVC integration test bao phủ cả dữ liệu hợp lệ lẫn sai.

Khi các điều kiện này được đáp ứng, người dùng có thể sửa dữ liệu ngay tại bước nhập liệu, còn flow chỉ chuyển tiếp khi model có kiểu dữ liệu hợp lệ và đáp ứng quy tắc nghiệp vụ. Việc định dạng và thông báo lỗi nhất quán cũng giúp các form trong Spring MVC và Spring Web Flow có cùng trải nghiệm.
