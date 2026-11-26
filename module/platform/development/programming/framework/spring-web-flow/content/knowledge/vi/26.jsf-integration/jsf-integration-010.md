# Chuyển kiểu, kiểm tra dữ liệu và thông báo trên form JSF

Trong chương **Tích hợp JSF**, một view-state của Spring Web Flow có thể hiển thị một trang JavaServer Faces (JSF) để người dùng nhập dữ liệu, kiểm tra và phát event chuyển sang bước tiếp theo. Trên trang đó, JSF chịu trách nhiệm chuyển đổi giá trị từ chuỗi request sang kiểu Java, chạy validator và hiển thị thông báo lỗi. Spring Web Flow tiếp nhận kết quả điều hướng khi JSF hoàn tất vòng đời xử lý request.

Bài học này trình bày cách phối hợp các cơ chế converter, validator và message của JSF với state, event và transition của **SPRING_WEB_FLOW**. Ta sẽ xây dựng một form đặt chỗ có ngày tháng và số khách, phân biệt lỗi chuyển đổi với lỗi validation, hiển thị lỗi đúng trường, xử lý nút Hủy và kiểm thử hành vi khi form không hợp lệ.

## 1. Vai trò của JSF trong một view-state

Spring Web Flow quản lý hành trình nhiều bước. JSF quản lý các thành phần giao diện và vòng đời xử lý form. Khi tích hợp Spring Faces, một view-state có thể sử dụng một trang JSF làm view:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="bookingForm">

    <var name="booking" class="com.example.BookingForm" />

    <view-state id="bookingForm" view="bookingForm.xhtml">
        <transition on="submit" to="reviewBooking" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <view-state id="reviewBooking" view="reviewBooking.xhtml">
        <transition on="confirm" to="bookingConfirmed" />
        <transition on="edit" to="bookingForm" />
    </view-state>

    <end-state id="bookingConfirmed" />
    <end-state id="bookingCancelled" />
</flow>
~~~

Trong ví dụ, biến flow có tên booking được đưa vào flow scope. Với cấu hình Spring Faces phù hợp, JSF Expression Language có thể truy cập biến đó bằng biểu thức #{booking}. Trang bookingForm.xhtml hiển thị form và phát event submit hoặc cancel. Flow definition quyết định event đó dẫn đến state nào.

Các thành phần có trách nhiệm riêng:

- **JSF component tree** giữ trạng thái thành phần giao diện, giá trị người dùng gửi và trạng thái hợp lệ của từng input.
- **Converter** chuyển chuỗi request thành kiểu Java và chuyển giá trị Java thành chuỗi hiển thị.
- **Validator** kiểm tra giá trị đã chuyển đổi theo quy tắc dữ liệu.
- **FacesMessage** ghi nhận thông báo gắn với một thành phần hoặc thông báo chung.
- **Spring Web Flow** tiếp tục hành trình khi JSF hoàn tất xử lý và phát ra event điều hướng phù hợp.

Tích hợp JSF cần được cấu hình theo phiên bản Spring Web Flow và JSF đang dùng. Các ví dụ bên dưới minh họa phần view và vòng đời JSF; namespace XML và package Jakarta/Javax cần khớp với runtime của ứng dụng.

## 2. Vòng đời JSF quyết định khi nào flow được chuyển state

Một request submit form JSF đi qua các pha chính của JSF lifecycle:

1. **Restore View**: khôi phục component tree của trang.
2. **Apply Request Values**: đọc các giá trị request và gán submitted value cho component.
3. **Process Validations**: chạy converter và validator.
4. **Update Model Values**: nếu dữ liệu hợp lệ, cập nhật giá trị vào model bean.
5. **Invoke Application**: gọi action của nút hoặc lệnh được người dùng kích hoạt.
6. **Render Response**: render trang phản hồi.

Converter và validator chạy trước khi model được cập nhật. Nếu một trường không chuyển đổi được hoặc validation thất bại, JSF đánh dấu component không hợp lệ, thêm FacesMessage và chuyển đến pha render response. Model không được cập nhật đầy đủ và action điều hướng thông thường không được gọi.

Điều này có ý nghĩa trực tiếp với Spring Web Flow: khi JSF validation thất bại, event submit thường chưa được phát đến flow executor. Vì vậy transition từ bookingForm sang reviewBooking không được thực hiện. Người dùng ở lại trang form và có thể sửa dữ liệu dựa trên thông báo lỗi.

~~~mermaid
flowchart TD
    A["Người dùng gửi form JSF"] --> B["Restore View / Apply Request Values"]
    B --> C["Converter: chuỗi sang kiểu Java"]
    C --> D{"Chuyển đổi thành công?"}
    D -->|"Không"| E["Ghi FacesMessage"]
    D -->|"Có"| F["Validator kiểm tra giá trị"]
    F --> G{"Validation hợp lệ?"}
    G -->|"Không"| E
    G -->|"Có"| H["Update Model Values"]
    H --> I["Invoke Application: gọi action"]
    I --> J["Spring Faces phát flow event"]
    J --> K["Spring Web Flow chọn transition"]
    E --> L["Render Response: hiển thị lỗi trên form"]
~~~

Không nên xem việc khai báo transition trong flow XML là đủ để form luôn chuyển state. Event chỉ được xử lý khi request vượt qua các pha JSF cần thiết. Khi validation không thành công, việc ở lại form là hành vi bình thường và thường là điều người dùng mong muốn.

## 3. Phân biệt conversion và validation

Hai loại lỗi thường xuất hiện cạnh nhau nhưng mang ý nghĩa khác nhau.

**Conversion** trả lời câu hỏi: giá trị người dùng gửi có thể chuyển thành kiểu Java mà thuộc tính yêu cầu hay không?

Ví dụ:

- Chuỗi 3 có thể chuyển thành Integer.
- Chuỗi abc không thể chuyển thành Integer.
- Chuỗi 25/11/2026 có thể chuyển thành Date nếu converter dùng đúng pattern.
- Chuỗi 2026-99-99 không phải ngày hợp lệ.

**Validation** trả lời câu hỏi: giá trị đã chuyển đổi có thỏa quy tắc của ứng dụng hay không?

Ví dụ:

- Số khách là 0 có thể chuyển thành Integer, nhưng không thỏa quy tắc phải có ít nhất một khách.
- Ngày kết thúc có thể chuyển thành Date, nhưng không được trước ngày bắt đầu.
- Tên khách có thể là chuỗi hợp lệ về kiểu, nhưng không được để trống.

| Giá trị người dùng nhập | Conversion | Validation | Kết quả |
|---|---|---|---|
| 3 khách | Thành công thành Integer | Hợp lệ nếu giới hạn cho phép | Có thể cập nhật model |
| 0 khách | Thành công thành Integer | Không hợp lệ nếu tối thiểu là 1 | Hiển thị lỗi validation |
| abc khách | Không chuyển thành Integer | Validator không nhận được giá trị số mới hợp lệ | Hiển thị lỗi conversion |
| 25/11/2026 | Thành công nếu pattern phù hợp | Kiểm tra quy tắc ngày | Có thể hợp lệ |
| 40/19/2026 | Chuyển đổi ngày thất bại | Không đến bước kiểm tra ngày nghiệp vụ | Hiển thị lỗi conversion |

Khi xử lý lỗi, hãy xác định lỗi nằm ở converter hay validator. Không nên cố sửa lỗi định dạng bằng cách nới lỏng quy tắc nghiệp vụ; cũng không nên dùng validator để xử lý một chuỗi vốn không thể chuyển thành kiểu dữ liệu đích.

## 4. Dùng converter có sẵn của JSF

JSF cung cấp các converter phổ biến cho số và ngày tháng. Có thể khai báo trực tiếp trong XHTML.

Ví dụ form đặt chỗ:

~~~xml
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:h="jakarta.faces.html"
      xmlns:f="jakarta.faces.core">
<h:head>
    <title>Thông tin đặt chỗ</title>
</h:head>
<h:body>
    <h:form id="bookingForm">

        <h:messages id="formMessages"
                    globalOnly="true"
                    layout="list" />

        <h:panelGrid columns="3">

            <h:outputLabel for="customerName"
                           value="Tên khách hàng" />
            <h:inputText id="customerName"
                         value="#{booking.customerName}"
                         required="true"
                         requiredMessage="Vui lòng nhập tên khách hàng."
                         maxlength="120" />
            <h:message for="customerName" />

            <h:outputLabel for="startDate"
                           value="Ngày bắt đầu" />
            <h:inputText id="startDate"
                         value="#{booking.startDate}"
                         required="true"
                         requiredMessage="Vui lòng nhập ngày bắt đầu."
                         converterMessage="Ngày bắt đầu phải theo định dạng ngày/tháng/năm.">
                <f:convertDateTime pattern="dd/MM/yyyy" />
            </h:inputText>
            <h:message for="startDate" />

            <h:outputLabel for="endDate"
                           value="Ngày kết thúc" />
            <h:inputText id="endDate"
                         value="#{booking.endDate}"
                         converterMessage="Ngày kết thúc không đúng định dạng.">
                <f:convertDateTime pattern="dd/MM/yyyy" />
            </h:inputText>
            <h:message for="endDate" />

            <h:outputLabel for="guests"
                           value="Số khách" />
            <h:inputText id="guests"
                         value="#{booking.guests}"
                         required="true"
                         requiredMessage="Vui lòng nhập số khách."
                         converterMessage="Số khách phải là số nguyên."
                         validatorMessage="Số khách phải từ 1 đến 8.">
                <f:convertNumber integerOnly="true"
                                 groupingUsed="false" />
                <f:validateLongRange minimum="1" maximum="8" />
            </h:inputText>
            <h:message for="guests" />

        </h:panelGrid>

        <h:commandButton id="submit"
                         value="Kiểm tra và tiếp tục"
                         action="submit" />

        <h:commandButton id="cancel"
                         value="Hủy"
                         action="cancel"
                         immediate="true" />

    </h:form>
</h:body>
</html>
~~~

Ví dụ dùng namespace Jakarta Faces hiện đại. Với ứng dụng JSF cũ, thay namespace bằng URI phù hợp với phiên bản, chẳng hạn http://xmlns.jcp.org/jsf/html và http://xmlns.jcp.org/jsf/core.

Các converter được dùng:

- f:convertDateTime chuyển chuỗi ngày theo pattern dd/MM/yyyy thành kiểu ngày của model.
- f:convertNumber chuyển chuỗi số thành kiểu số tương ứng với thuộc tính.
- f:validateLongRange kiểm tra số khách nằm trong khoảng từ 1 đến 8.

Các thuộc tính required, converterMessage và validatorMessage cho phép tùy chỉnh thông báo ngay tại component. h:message hiển thị lỗi của một trường; h:messages hiển thị danh sách thông báo chung hoặc tất cả thông báo tùy cấu hình.

Kiểu Java của các thuộc tính phải tương thích với converter. Ví dụ startDate và endDate có thể dùng java.util.Date; guests có thể dùng Integer. Nếu model dùng LocalDate hoặc kiểu miền riêng, cần converter tương thích với kiểu đó hoặc converter tùy chỉnh.

## 5. Giới hạn độ dài và khoảng giá trị bằng validator có sẵn

JSF cung cấp các validator tiêu chuẩn cho những quy tắc đơn giản:

~~~xml
<h:inputText id="customerName"
             value="#{booking.customerName}"
             required="true">
    <f:validateLength minimum="2" maximum="120" />
</h:inputText>

<h:inputText id="guests"
             value="#{booking.guests}">
    <f:convertNumber integerOnly="true" />
    <f:validateLongRange minimum="1" maximum="8" />
</h:inputText>
~~~

Một số validator thường dùng:

| Tag | Mục đích |
|---|---|
| f:validateLength | Giới hạn độ dài chuỗi |
| f:validateLongRange | Giới hạn giá trị số nguyên theo khoảng |
| f:validateDoubleRange | Giới hạn giá trị số thực theo khoảng |
| f:validateRegex | Kiểm tra chuỗi theo biểu thức chính quy ở các phiên bản JSF hỗ trợ |
| f:validateBean | Kích hoạt kiểm tra constraint Bean Validation theo cấu hình |

required kiểm tra component có giá trị bắt buộc hay không. validateLength kiểm tra độ dài. validateLongRange kiểm tra khoảng số. Hãy chọn validator đúng ý nghĩa dữ liệu thay vì dùng một regex phức tạp cho mọi quy tắc.

Nếu trường số cần chấp nhận giá trị thập phân, converter phải tạo kiểu số tương ứng và validator cũng phải dùng khoảng phù hợp. Không dùng Integer cho giá trị tiền hoặc tỷ lệ có phần thập phân.

## 6. Tạo custom Converter khi kiểu dữ liệu có quy tắc riêng

Converter tùy chỉnh phù hợp khi dữ liệu cần cách biểu diễn hoặc phân tích không có sẵn trong converter tiêu chuẩn. Ví dụ, mã phòng có dạng R-102 và cần chuyển thành đối tượng RoomCode.

Với JSF hỗ trợ Converter generic:

~~~java
import jakarta.faces.component.UIComponent;
import jakarta.faces.context.FacesContext;
import jakarta.faces.convert.Converter;
import jakarta.faces.convert.ConverterException;
import jakarta.faces.application.FacesMessage;
import jakarta.faces.convert.FacesConverter;

@FacesConverter(forClass = RoomCode.class)
public class RoomCodeConverter implements Converter<RoomCode> {

    @Override
    public RoomCode getAsObject(
            FacesContext context,
            UIComponent component,
            String value) {

        if (value == null || value.trim().isEmpty()) {
            return null;
        }

        try {
            return RoomCode.parse(value.trim());
        } catch (IllegalArgumentException ex) {
            FacesMessage message = new FacesMessage(
                FacesMessage.SEVERITY_ERROR,
                "Mã phòng không hợp lệ.",
                "Nhập mã theo dạng R-102."
            );
            throw new ConverterException(message);
        }
    }

    @Override
    public String getAsString(
            FacesContext context,
            UIComponent component,
            RoomCode value) {

        return value == null ? "" : value.toString();
    }
}
~~~

Hai phương thức có nhiệm vụ ngược nhau:

- getAsObject nhận chuỗi từ request và tạo đối tượng Java.
- getAsString chuyển đối tượng Java thành chuỗi để hiển thị trong component.

Converter không nên truy cập repository hoặc thực hiện nghiệp vụ phức tạp. Nếu việc chuyển đổi cần tra cứu dữ liệu, hãy cân nhắc dùng một mã định danh đơn giản rồi để service kiểm tra bản ghi sau khi form hợp lệ. Điều này giúp converter có thể tái sử dụng và tránh truy vấn bất ngờ trong JSF lifecycle.

Với phiên bản JSF cũ dùng Converter không generic, chữ ký phương thức có thể khác về kiểu tham số và kiểu trả về. Package cũng thay đổi giữa javax.faces và jakarta.faces. Hãy viết đúng API của phiên bản triển khai.

## 7. Tạo custom Validator cho quy tắc riêng của một trường

Khi quy tắc không thể biểu diễn bằng validator có sẵn, có thể tạo Validator tùy chỉnh. Ví dụ số khách phải thuộc khoảng 1 đến 8 và chỉ được phép áp dụng cho một loại đặt chỗ cụ thể.

~~~java
import jakarta.faces.application.FacesMessage;
import jakarta.faces.component.UIComponent;
import jakarta.faces.context.FacesContext;
import jakarta.faces.validator.FacesValidator;
import jakarta.faces.validator.Validator;
import jakarta.faces.validator.ValidatorException;

@FacesValidator("guestCountValidator")
public class GuestCountValidator implements Validator<Integer> {

    @Override
    public void validate(
            FacesContext context,
            UIComponent component,
            Integer value) throws ValidatorException {

        if (value == null) {
            return;
        }

        if (value < 1 || value > 8) {
            FacesMessage message = new FacesMessage(
                FacesMessage.SEVERITY_ERROR,
                "Số khách không hợp lệ.",
                "Một đặt chỗ phải có từ 1 đến 8 khách."
            );
            throw new ValidatorException(message);
        }
    }
}
~~~

Gắn validator vào component:

~~~xml
<h:inputText id="guests"
             value="#{booking.guests}">
    <f:convertNumber integerOnly="true" />
    <f:validator validatorId="guestCountValidator" />
</h:inputText>
<h:message for="guests" />
~~~

Khi validator phát hiện lỗi, nó ném ValidatorException chứa FacesMessage. JSF gắn thông báo vào component và không tiếp tục cập nhật model như một request hợp lệ.

Validator cấp component nên tập trung vào giá trị của trường đó. Không nên nhồi kiểm tra nhiều trường hoặc truy cập database vào một validator nhỏ. Quy tắc cần nhiều dữ liệu thường phù hợp hơn với Bean Validation cấp class hoặc service nghiệp vụ.

## 8. Kiểm tra quan hệ giữa nhiều trường

Một số quy tắc cần so sánh nhiều thuộc tính, ví dụ ngày kết thúc không được trước ngày bắt đầu. Validator gắn vào riêng trường endDate không phải lúc nào cũng có đầy đủ ngữ cảnh của toàn bộ model, đặc biệt khi thứ tự component hoặc quá trình cập nhật model thay đổi.

Có thể dùng Bean Validation với constraint cấp class. Ví dụ annotation tùy chỉnh:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = BookingDateRangeValidator.class)
public @interface ValidBookingDateRange {
    String message() default "Ngày kết thúc phải sau hoặc bằng ngày bắt đầu.";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator cấp class:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class BookingDateRangeValidator
        implements ConstraintValidator<ValidBookingDateRange, BookingForm> {

    @Override
    public boolean isValid(
            BookingForm booking,
            ConstraintValidatorContext context) {

        if (booking == null
                || booking.getStartDate() == null
                || booking.getEndDate() == null) {
            return true;
        }

        return !booking.getEndDate().before(booking.getStartDate());
    }
}
~~~

Gắn constraint lên model:

~~~java
import java.util.Date;

@ValidBookingDateRange
public class BookingForm {
    private Date startDate;
    private Date endDate;

    // Getter và setter
}
~~~

Khi JSF tích hợp Bean Validation và chạy validate bean, constraint cấp class có thể kiểm tra mối quan hệ giữa hai trường. Hãy kiểm tra cấu hình Bean Validation provider và cách JSF kích hoạt validation trong ứng dụng. Với lỗi cấp class, thông báo thường là global message; nếu muốn hiển thị ngay cạnh một trường, có thể tùy chỉnh ConstraintValidatorContext để gắn property path phù hợp.

Không nên dùng kiểm tra ở giao diện làm lớp bảo vệ duy nhất. Service vẫn cần kiểm tra lại ngày tháng và các quy tắc nghiệp vụ trước khi lưu hoặc xác nhận đặt chỗ.

## 9. Hiển thị FacesMessage đúng vị trí

JSF lưu thông báo trong FacesContext của request hiện tại. Có thể hiển thị thông báo theo hai cách chính:

- h:message với thuộc tính for trỏ đến client ID của một input, dùng cho lỗi cụ thể của trường.
- h:messages hiển thị nhiều thông báo trong form hoặc các thông báo chung.

Ví dụ:

~~~xml
<h:form id="bookingForm">
    <h:messages id="summary"
                globalOnly="true"
                layout="list"
                styleClass="error-summary" />

    <h:outputLabel for="email" value="Email" />
    <h:inputText id="email"
                 value="#{booking.email}"
                 required="true"
                 requiredMessage="Vui lòng nhập email."
                 validatorMessage="Email không đúng định dạng.">
        <f:validateRegex pattern="^[^@\s]+@[^@\s]+\.[^@\s]+$" />
    </h:inputText>
    <h:message for="email" styleClass="field-error" />
</h:form>
~~~

Thông báo gắn với email sẽ xuất hiện cạnh input tương ứng. Thông báo không gắn với component cụ thể có thể được hiển thị trong h:messages globalOnly=true.

Không nên chỉ hiển thị lỗi bằng màu sắc hoặc biểu tượng. Hãy dùng văn bản dễ hiểu, đặt gần trường liên quan và bảo đảm người dùng có thể nhận biết lỗi bằng công nghệ hỗ trợ. Nếu có nhiều lỗi, phần tổng hợp ở đầu form giúp người dùng thấy còn những vấn đề nào cần sửa.

### Tạo thông báo từ code

Khi một action hoặc listener cần thêm thông báo cho người dùng, có thể dùng FacesContext:

~~~java
FacesContext.getCurrentInstance().addMessage(
    null,
    new FacesMessage(
        FacesMessage.SEVERITY_INFO,
        "Đã lưu bản nháp.",
        null
    )
);
~~~

Tham số đầu tiên là client ID. Giá trị null tạo thông báo chung; nếu muốn gắn với một component, truyền client ID tương ứng. Các mức severity thường gồm INFO, WARN, ERROR và FATAL.

FacesMessage thuộc request JSF hiện tại. Nếu ứng dụng redirect sang request mới, không nên giả định message sẽ tự tồn tại. Với thông báo sau redirect, hãy dùng cơ chế flash phù hợp của JSF hoặc MVC tùy điểm đích; nếu chỉ chuyển state và render view tiếp theo trong cùng flow execution, hãy xác định rõ cách tích hợp giữ message của ứng dụng.

## 10. Kết hợp Bean Validation với form JSF

Bean Validation giúp đặt quy tắc gần model và tái sử dụng chúng ngoài JSF. Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class BookingForm {

    @NotBlank(message = "Vui lòng nhập tên khách hàng.")
    @Size(max = 120, message = "Tên không được dài quá 120 ký tự.")
    private String customerName;

    @NotNull(message = "Vui lòng nhập số khách.")
    @Min(value = 1, message = "Số khách tối thiểu là 1.")
    @Max(value = 8, message = "Số khách tối đa là 8.")
    private Integer guests;

    private Date startDate;
    private Date endDate;

    // Getter và setter
}
~~~

Nếu Bean Validation provider được cài đặt và tích hợp với JSF, các constraint có thể được chạy trong pha Process Validations. Có thể dùng f:validateBean để điều khiển validation bean ở phạm vi component hoặc form theo phiên bản JSF.

Ví dụ:

~~~xml
<h:form id="bookingForm">
    <f:validateBean>
        <h:inputText id="customerName"
                     value="#{booking.customerName}" />
        <h:inputText id="guests"
                     value="#{booking.guests}">
            <f:convertNumber integerOnly="true" />
        </h:inputText>
    </f:validateBean>
</h:form>
~~~

Hãy tránh khai báo cùng một quy tắc ở quá nhiều nơi nếu không có lý do. Nếu vừa dùng f:validateLongRange vừa dùng @Min/@Max với thông báo khác nhau, người dùng có thể thấy thông báo trùng. Chọn nơi chịu trách nhiệm cho mỗi quy tắc và kiểm thử thứ tự thực thi.

Bean Validation phù hợp với quy tắc dữ liệu của model. Những quy tắc cần tra cứu trạng thái hệ thống, kiểm tra quyền hoặc xác nhận giao dịch vẫn phải nằm ở service nghiệp vụ.

## 11. Vì sao lỗi validation ngăn transition của Spring Web Flow?

Giả sử view-state có transition:

~~~xml
<view-state id="bookingForm" view="bookingForm.xhtml">
    <transition on="submit" to="reviewBooking" />
</view-state>
~~~

Nút JSF phát action outcome submit:

~~~xml
<h:commandButton value="Tiếp tục" action="submit" />
~~~

Trong môi trường Spring Faces đã tích hợp điều hướng flow, action outcome được ánh xạ thành flow event. Nhưng JSF chỉ gọi action khi các bước xử lý cần thiết hoàn tất. Nếu converter hoặc validator thất bại, JSF chuyển đến Render Response và hiển thị lại form. Event submit không được phát, nên transition không chạy.

Điều này tránh việc flow chuyển sang reviewBooking khi model chưa nhận đủ dữ liệu hợp lệ. Người dùng vẫn ở bookingForm, các thông báo được hiển thị và có thể sửa lại.

Không nên gọi flow executor thủ công từ validator để ép chuyển state. Validator có trách nhiệm kiểm tra dữ liệu và báo lỗi; navigation nên diễn ra thông qua action/event của JSF và cơ chế tích hợp Spring Faces.

## 12. Xử lý nút Hủy khi form đang có lỗi

Một vấn đề thường gặp: người dùng nhập ngày không hợp lệ rồi bấm Hủy. Nếu nút Hủy cũng đi qua validation đầy đủ, lỗi ngày tháng có thể ngăn action cancel được gọi. Người dùng bị giữ lại ở form dù muốn rời khỏi nó.

Có thể dùng immediate=true trên command component Hủy để xử lý action sớm trong JSF lifecycle:

~~~xml
<h:commandButton value="Hủy"
                 action="cancel"
                 immediate="true" />
~~~

Trong flow definition, transition Hủy chỉ cần khai báo event và state đích:

~~~xml
<view-state id="bookingForm" view="bookingForm.xhtml">
    <transition on="submit" to="reviewBooking" />

    <transition on="cancel" to="bookingCancelled" />
</view-state>
~~~

Trong JSF view, cơ chế chính để nút Hủy không bị converter/validator thông thường chặn là immediate trên command component. Cần phân biệt hai lớp:

- immediate trên JSF command component đưa action event vào pha sớm của JSF lifecycle, trước khi các input chạy validation thông thường và cập nhật model.
- bind và validate trên transition của Spring Web Flow điều khiển binder/validator riêng của Web Flow trong những view technology sử dụng cơ chế đó. Chúng không tắt converter hoặc validator của component JSF.

Không nên xem immediate=true và validate=false là hai thuộc tính thay thế nhau. Với một view JSF, chỉ đặt validate=false trên transition của Web Flow không tắt JSF validation. Ngược lại, immediate=true có thể khiến model không được cập nhật từ các trường form vừa sửa. Đây thường là điều đúng với Hủy, nhưng không phù hợp nếu nút cần giữ các thay đổi mới nhất.

Hãy kiểm thử nút Hủy với một form có lỗi conversion và một form có lỗi validation để chắc chắn event cancel vẫn được phát và dữ liệu chưa xác nhận không bị lưu ngoài ý muốn.

## 13. Thông báo sau khi chuyển state hoặc redirect

Có ba tình huống khác nhau:

1. **Ở lại cùng view vì validation lỗi**: FacesMessage được render trong response JSF hiện tại.
2. **Chuyển sang view-state khác trong flow**: dữ liệu và message cần được xử lý theo cơ chế tích hợp JSF/Spring Faces và vòng đời view của flow. Không mặc định mọi FacesMessage sẽ tồn tại sau mọi lần điều hướng.
3. **Root flow kết thúc và redirect sang trang MVC hoặc JSF độc lập**: message trong FacesContext của request trước không tự động chuyển sang request mới.

Nếu đích là một trang JSF và muốn dùng cơ chế flash của JSF, có thể lưu thông báo trước redirect:

~~~java
FacesContext context = FacesContext.getCurrentInstance();

context.getExternalContext()
       .getFlash()
       .put("notice", "Đặt chỗ đã được xác nhận.");
~~~

Trang JSF đích có thể đọc flash scope theo cách mà phiên bản JSF hỗ trợ. Nếu đích là Spring MVC, hãy dùng MVC FlashMap. Còn nếu dữ liệu cần tồn tại xuyên nhiều state của flow, dùng scope phù hợp của Spring Web Flow hoặc lưu kết quả nghiệp vụ bền vững.

Đừng nhầm JSF Flash, Spring Web Flow flash scope và Spring MVC FlashMap. Chúng có API và vòng đời khác nhau, dù cùng phục vụ một số tình huống dữ liệu tạm thời.

## 14. Bản địa hóa thông báo và trải nghiệm sửa lỗi

Thông báo nên được viết theo ngôn ngữ của người dùng và giải thích cách sửa. Tránh chỉ hiển thị các câu chung chung như “Conversion Error” hoặc “Validation Error”.

Có thể dùng message bundle trong cấu hình JSF để quản lý thông báo theo locale:

~~~xml
<application>
    <message-bundle>com.example.i18n.messages</message-bundle>
</application>
~~~

Trong file resource bundle, đặt thông báo theo các key JSF hoặc key ứng dụng. Tên key mặc định cho converter và validator có thể khác giữa namespace javax và jakarta cũng như phiên bản JSF; hãy kiểm tra runtime đang dùng. Với lỗi riêng của ứng dụng, có thể đặt key cho annotation Bean Validation hoặc custom validator.

Một thông báo hữu ích nên nêu:

- Trường nào cần sửa.
- Giá trị nào được chấp nhận.
- Định dạng mong đợi, nếu có.
- Giới hạn cụ thể, nếu là khoảng số hoặc độ dài.

Ví dụ, “Ngày bắt đầu phải theo định dạng dd/MM/yyyy” dễ hành động hơn “Ngày không hợp lệ”. Với lỗi số khách, “Số khách phải từ 1 đến 8” tốt hơn “Giá trị ngoài phạm vi”.

## 15. Kiểm thử converter, validator và điều hướng flow

Nên kiểm thử từng lớp riêng và kiểm thử tích hợp toàn bộ vòng đời.

| Nhóm kiểm thử | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Converter số | Nhập số nguyên hợp lệ | Tạo đúng giá trị Integer |
| Converter số | Nhập chữ vào trường số | Có conversion message, model không nhận giá trị sai |
| Converter ngày | Nhập ngày đúng pattern | Chuyển thành Date đúng ngày |
| Converter ngày | Nhập ngày sai định dạng | Hiển thị lỗi conversion cạnh trường |
| Validator khoảng số | Nhập 0 hoặc 9 khách | Có validation message |
| Validator độ dài | Tên vượt giới hạn | Form không được chấp nhận |
| Validator nhiều trường | Ngày kết thúc trước ngày bắt đầu | Có thông báo phù hợp cho lỗi quan hệ ngày |
| JSF action | Form hợp lệ và bấm Submit | Action phát event và flow đến reviewBooking |
| JSF action | Form không hợp lệ và bấm Submit | Action không chạy; flow ở bookingForm |
| Nút Hủy | Form có lỗi và bấm Cancel | Event cancel được xử lý theo cấu hình |
| Message rendering | Lỗi theo trường và lỗi chung | h:message/h:messages hiển thị đúng nơi |
| Redirect | Flow kết thúc và chuyển sang request mới | Thông báo được truyền bằng flash phù hợp nếu cần |

Một bài kiểm thử end-to-end có thể thực hiện:

1. Khởi chạy flow booking và mở trang JSF bookingForm.
2. Gửi chuỗi không phải số vào trường guests.
3. Xác nhận JSF hiển thị lỗi conversion và flow không chuyển state.
4. Nhập số khách bằng 0 rồi submit.
5. Xác nhận converter thành công nhưng validator từ chối.
6. Nhập số khách hợp lệ và ngày đúng định dạng.
7. Gửi form và xác nhận action phát event submit.
8. Xác nhận flow chuyển đến reviewBooking.
9. Quay lại form, nhập một giá trị sai và bấm Hủy.
10. Xác nhận event cancel vẫn hoạt động theo thiết kế và dữ liệu chưa xác nhận không được áp dụng.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng validator để xử lý chuỗi sai kiểu | Conversion đã thất bại trước khi validator nhận giá trị đúng kiểu | Tạo hoặc cấu hình converter phù hợp |
| Chỉ dùng converter mà không validate | Giá trị chuyển đổi được nhưng có thể vi phạm quy tắc nghiệp vụ | Thêm validator phù hợp |
| Hiển thị tất cả lỗi ở một nơi | Người dùng khó biết trường nào cần sửa | Dùng h:message theo component và h:messages cho lỗi chung |
| Cho rằng flow transition luôn chạy khi bấm nút | JSF validation có thể chặn action trước navigation | Kiểm tra lifecycle và event mapping |
| Dùng immediate cho mọi nút | Bỏ qua các bước cần thiết và model không được cập nhật như mong muốn | Chỉ dùng cho hành động như Hủy khi cần |
| Dùng FacesMessage rồi redirect mà không lưu flash | Thông báo biến mất ở request mới | Dùng JSF Flash hoặc MVC FlashMap theo loại view đích |
| Dồn kiểm tra quyền vào validator | Quy tắc bảo mật bị gắn với giao diện và có thể bị bỏ qua ở đường gọi khác | Kiểm tra quyền trong service |
| Không kiểm tra lại ở tầng nghiệp vụ | Request khác có thể bỏ qua JSF | Service xác thực dữ liệu trước thao tác quan trọng |
| Trộn javax và jakarta API | Không biên dịch hoặc lỗi class loading | Đồng bộ package với phiên bản JSF/Spring |

## 17. Thực hành: hoàn thiện form JSF đặt chỗ

Hãy xây dựng form đặt chỗ có các trường tên khách, ngày bắt đầu, ngày kết thúc và số khách.

1. Khai báo biến booking trong flow scope và hiển thị form bằng view-state bookingForm.
2. Tạo input JSF cho từng thuộc tính của model.
3. Dùng f:convertDateTime cho ngày và f:convertNumber cho số khách.
4. Dùng required, f:validateLength và f:validateLongRange cho các quy tắc cơ bản.
5. Tạo custom validator nếu có quy tắc riêng cho một trường.
6. Tạo constraint cấp class hoặc service check cho quan hệ ngày bắt đầu/ngày kết thúc.
7. Hiển thị lỗi theo trường bằng h:message và lỗi chung bằng h:messages.
8. Cấu hình nút Submit phát event submit để đi đến reviewBooking.
9. Cấu hình nút Hủy với immediate khi cần bỏ qua validation của JSF; không dựa vào bind/validate của Web Flow để tắt lifecycle JSF.
10. Thử dữ liệu sai kiểu, dữ liệu đúng kiểu nhưng không hợp lệ và dữ liệu hợp lệ.
11. Xác nhận JSF chỉ cập nhật model và phát event điều hướng khi các bước cần thiết thành công.
12. Kiểm thử service xác nhận để bảo đảm dữ liệu vẫn được kiểm tra ở tầng nghiệp vụ.

Sau khi thực hành, hãy tự trả lời:

- Converter và validator chạy ở những pha nào của JSF lifecycle?
- Vì sao lỗi conversion hoặc validation ngăn action submit được gọi?
- Khi nào dùng f:convertDateTime và khi nào cần custom Converter?
- Vì sao lỗi quan hệ giữa hai trường thường phù hợp với class-level validation?
- h:message khác h:messages như thế nào?
- immediate=true trên command component ảnh hưởng gì đến nút Hủy?
- Vì sao service vẫn cần kiểm tra dữ liệu sau khi JSF đã validation thành công?
- FacesMessage có tự tồn tại sau redirect không?

## 18. Ghi nhớ

Trong form JSF, converter chuyển chuỗi request thành kiểu Java; validator kiểm tra giá trị đã chuyển đổi; FacesMessage cung cấp phản hồi cho người dùng. JSF thực hiện các bước này trước khi cập nhật model và gọi action. Nếu conversion hoặc validation thất bại, form được render lại cùng thông báo và event chuyển state của Spring Web Flow thường không được phát.

Hãy dùng converter và validator có sẵn cho quy tắc đơn giản, tạo custom component converter/validator khi cần và dùng Bean Validation cho quy tắc trên model. Gắn lỗi cạnh trường bằng h:message, tổng hợp lỗi bằng h:messages và xử lý riêng nút Hủy nếu cần bỏ qua validation. Cuối cùng, luôn giữ kiểm tra nghiệp vụ và phân quyền ở service. Cách phối hợp này giúp tích hợp JSF với **SPRING_WEB_FLOW** có vòng đời rõ ràng, thông báo dễ hiểu và điều hướng chỉ diễn ra khi dữ liệu đạt điều kiện.
