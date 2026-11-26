# Đối chiếu cơ chế conversion cũ với cấu hình Spring hiện hành

*Chương: Chuyển đổi và định dạng · Module: SPRING_WEB_FLOW*

Trong một flow nhiều bước, dữ liệu từ biểu mẫu thường đến dưới dạng chuỗi HTTP, trong khi mã Java làm việc với các kiểu như LocalDate, BigDecimal, enum hoặc ID miền nghiệp vụ. Spring cần chuyển đổi dữ liệu giữa hai dạng đó khi bind form, đưa dữ liệu vào model và hiển thị giá trị trở lại view. Cấu hình conversion vì vậy ảnh hưởng trực tiếp tới việc người dùng nhập ngày tháng, số tiền, lựa chọn trạng thái và nhận thông báo lỗi.

Các ứng dụng Spring cũ thường dựa vào JavaBeans PropertyEditor, CustomDateEditor và đăng ký editor trong WebDataBinder. Cấu hình Spring hiện hành ưu tiên ConversionService cùng Converter, GenericConverter và Formatter. Spring vẫn hỗ trợ PropertyEditor để tương thích, nhưng ConversionService cung cấp cách tổ chức quy tắc chuyển đổi rõ ràng, có kiểu và dễ dùng chung hơn. Với Spring Web Flow, cần bảo đảm dịch vụ conversion được cấu hình cho cả quá trình bind của flow view; cấu hình riêng cho Spring MVC không tự động chứng minh rằng flow builder cũng đang dùng đúng cùng bộ quy tắc.

Module SPRING_WEB_FLOW hướng tới việc mô hình hóa hành trình web qua state, event, transition và subflow, kết hợp form binding, validation, quản lý scope, Spring MVC, kiểm thử và phục hồi lỗi. Bài học này tập trung vào cách đối chiếu cơ chế conversion cũ với cấu hình hiện hành để dữ liệu đi qua các bước của flow nhất quán, dễ kiểm thử và phù hợp với locale của người dùng.

Sau bài học, bạn có thể:

- Phân biệt PropertyEditor với ConversionService, Converter và Formatter.
- Nhận biết nơi đăng ký conversion trong ứng dụng Spring MVC và Spring Web Flow.
- Chọn Converter cho chuyển đổi kiểu và Formatter cho định dạng văn bản phụ thuộc locale.
- Xử lý ngày, số thập phân, enum, giá trị rỗng và lỗi binding.
- Chuyển dần từ editor cũ sang conversion service mà không làm thay đổi hành vi ngoài ý muốn.
- Kiểm thử conversion trong unit test, MVC binding và flow execution.

## 1. Conversion xuất hiện ở đâu trong flow?

Trình duyệt gửi giá trị form qua HTTP dưới dạng văn bản hoặc các phần dữ liệu request. Khi Spring Web Flow bind form, giá trị đó cần được chuyển thành kiểu Java tương ứng. Ví dụ, chuỗi 15/04/2026 có thể được chuyển thành LocalDate; chuỗi 125000.50 có thể được chuyển thành BigDecimal; chuỗi PAID có thể được chuyển thành enum PaymentStatus.

Chiều ngược lại cũng quan trọng. View cần hiển thị ngày, số tiền và trạng thái theo định dạng dễ đọc. Một ngày có thể được hiển thị theo thứ tự ngày/tháng/năm ở một locale và tháng/ngày/năm ở locale khác. Giá trị nội bộ cần ổn định, còn cách trình bày cần phù hợp với ngôn ngữ và quy ước của người dùng.

Một luồng xử lý điển hình:

~~~mermaid
flowchart TD
    A[Form gửi chuỗi từ trình duyệt] --> B[Spring Web Flow bind dữ liệu]
    B --> C[ConversionService hoặc PropertyEditor]
    C --> D[Model object có kiểu Java]
    D --> E[Validation]
    E --> F{Dữ liệu hợp lệ?}
    F -->|Không| G[Giữ ở view và hiển thị lỗi]
    F -->|Có| H[Transition tới state tiếp theo]
    H --> I[View format giá trị để hiển thị]
~~~

Conversion và validation là hai công việc khác nhau. Conversion trả lời câu hỏi chuỗi đầu vào có thể biểu diễn thành kiểu Java hay không. Validation kiểm tra giá trị đã chuyển đổi có thỏa quy tắc nghiệp vụ hay không. Ví dụ, chuỗi 31/02/2026 có thể thất bại ngay ở bước parse ngày; một ngày hợp lệ như 10/05/2026 vẫn có thể không hợp lệ với quy tắc đặt lịch vì ngày đó đã ở quá khứ.

## 2. Cơ chế cũ: JavaBeans PropertyEditor

PropertyEditor là API của JavaBeans dùng để chuyển đổi giữa văn bản và một giá trị đối tượng. Editor thường được cấu hình cho một kiểu hoặc một thuộc tính cụ thể. Trong ứng dụng Spring MVC truyền thống, WebDataBinder có thể đăng ký editor để bind dữ liệu request.

Ví dụ với CustomDateEditor:

~~~java
@Controller
public class BookingController {

    @InitBinder
    public void initBinder(WebDataBinder binder) {
        SimpleDateFormat dateFormat =
                new SimpleDateFormat("dd/MM/yyyy");
        dateFormat.setLenient(false);

        binder.registerCustomEditor(
                Date.class,
                "bookingDate",
                new CustomDateEditor(dateFormat, true));
    }
}
~~~

Đoạn mã đăng ký một editor cho thuộc tính bookingDate. Tham số true cho phép giá trị rỗng được xử lý như null. setLenient(false) yêu cầu ngày phải phù hợp với lịch thay vì tự điều chỉnh ngày không hợp lệ.

PropertyEditor có một số đặc điểm cần nhớ:

- API chuyển đổi chủ yếu dựa trên thao tác setAsText và getAsText.
- Editor có thể giữ trạng thái của lần chuyển đổi gần nhất, vì vậy không nên chia sẻ một instance mutable giữa nhiều request hoặc thread.
- Editor thường được đăng ký theo kiểu dữ liệu hoặc theo đường dẫn thuộc tính trong một WebDataBinder.
- Quy tắc định dạng và parse thường nằm trong lớp editor hoặc cấu hình binder.
- Việc tái sử dụng editor ở nhiều controller, flow và thành phần có thể cần đăng ký lặp lại.

Trong ví dụ, SimpleDateFormat được tạo mới trong mỗi lần initBinder nên không bị dùng chung giữa các request. Không khai báo một SimpleDateFormat mutable thành static field hoặc singleton rồi dùng đồng thời trong nhiều request.

### Đăng ký editor theo phạm vi

Spring hỗ trợ đăng ký editor trong phương thức @InitBinder, thông qua PropertyEditorRegistrar hoặc một WebBindingInitializer. Cách đăng ký quyết định editor áp dụng cho binder nào và phạm vi nào. Một editor chỉ được đăng ký trong controller có thể không được áp dụng cho một flow view được cấu hình bằng cơ chế binding riêng.

Editor phù hợp khi duy trì một ứng dụng cũ cần tương thích với quy tắc đã tồn tại, hoặc khi có một editor đặc thù mà hệ thống hiện tại chưa thể chuyển đổi ngay. Tuy nhiên, không nên dùng editor như một nơi chứa logic nghiệp vụ, truy vấn database hoặc gọi service. Editor chỉ nên chịu trách nhiệm chuyển đổi và định dạng giá trị.

## 3. Cơ chế hiện hành: ConversionService

ConversionService là abstraction tập trung của Spring để chuyển một giá trị từ kiểu nguồn sang kiểu đích. Các converter được đăng ký theo cặp kiểu, nhờ đó quy tắc chuyển đổi có thể được tái sử dụng ở nhiều điểm binding.

Các abstraction thường gặp:

| Thành phần | Công việc chính | Khi nên dùng |
|---|---|---|
| Converter<S,T> | Chuyển một kiểu nguồn S thành kiểu đích T | Chuyển chuỗi sang enum, ID sang kiểu value object |
| ConverterFactory<S,R> | Tạo converter cho một họ kiểu đích có chung kiểu cơ sở | Họ enum hoặc kiểu có cùng quy tắc chuyển đổi |
| GenericConverter | Chuyển đổi giữa nhiều cặp kiểu, có thể xét metadata | Quy tắc cần biết kiểu nguồn/đích và thông tin descriptor |
| Formatter<T> | Parse văn bản thành T và in T thành văn bản, có Locale | Ngày tháng, số hoặc giá trị cần định dạng theo locale |
| ConversionService | Tra cứu và thực thi converter/formatter đã đăng ký | Dùng chung trong binding và các thành phần Spring |

Converter không nhận Locale. Nó phù hợp với chuyển đổi kiểu có quy tắc ổn định, ví dụ một chuỗi mã trạng thái thành enum. Formatter nhận Locale khi parse và print, phù hợp với dữ liệu nhập/xuất có quy ước văn bản khác nhau theo vùng.

Ví dụ converter chuyển chuỗi sang enum:

~~~java
public class StringToPaymentStatusConverter
        implements Converter<String, PaymentStatus> {

    @Override
    public PaymentStatus convert(String source) {
        if (source == null || source.trim().isEmpty()) {
            return null;
        }

        try {
            return PaymentStatus.valueOf(
                    source.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Trạng thái thanh toán không được hỗ trợ", ex);
        }
    }
}
~~~

Converter này chuẩn hóa mã enum bằng Locale.ROOT, tránh phụ thuộc locale mặc định của máy chủ. Nó không truy vấn database và không lưu trạng thái giữa các lần gọi. Với mã miền cần kiểm tra tồn tại trong database, hãy chuyển đổi chuỗi thành ID hoặc value object trước, sau đó để service xác minh bản ghi và quyền truy cập.

### Formatter cho ngày tháng

Formatter phù hợp khi cần cả parse lẫn hiển thị theo locale:

~~~java
public class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(locale);
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException ex) {
            ParseException parseException =
                    new ParseException("Ngày không hợp lệ", 0);
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
~~~

FormatStyle.SHORT sử dụng quy ước ngày ngắn của locale. Vì vậy, cùng một LocalDate có thể được hiển thị khác nhau theo locale. Khi sản phẩm yêu cầu một định dạng cố định, ví dụ một biểu mẫu nghiệp vụ luôn dùng dd/MM/uuuu, hãy dùng pattern được thống nhất và kiểm thử rõ ràng; đừng giả định định dạng ngắn theo locale luôn giống nhau ở mọi quốc gia.

Với ngày chỉ có ý nghĩa lịch, LocalDate thường phù hợp hơn Date hoặc Instant. Với thời điểm tuyệt đối, hãy dùng Instant hoặc kiểu thời gian có timezone phù hợp và xác định rõ múi giờ hiển thị. Định dạng ngày không được tự ý biến một ngày lịch thành một thời điểm theo timezone.

## 4. Đăng ký conversion cho Spring MVC

Trong ứng dụng Spring MVC cấu hình bằng Java, WebMvcConfigurer cho phép đăng ký converter và formatter trong registry của MVC:

~~~java
@Configuration
@EnableWebMvc
public class WebMvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new StringToPaymentStatusConverter());
        registry.addFormatter(
                new LocalDateFormatter());
    }
}
~~~

Trong cấu hình XML, mvc:annotation-driven có thể nhận conversion-service đã được khai báo:

~~~xml
<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="com.acme.web.StringToPaymentStatusConverter"/>
        </set>
    </property>
    <property name="formatters">
        <set>
            <bean class="com.acme.web.LocalDateFormatter"/>
        </set>
    </property>
</bean>

<mvc:annotation-driven conversion-service="conversionService"/>
~~~

Các ví dụ chỉ minh họa hai cách đăng ký. Hãy chọn cách phù hợp với kiểu cấu hình của ứng dụng. Không nên khai báo hai bộ conversion khác nhau cho cùng một quy tắc mà không có chủ đích, vì controller có thể bind một kiểu trong khi flow view lại bind theo kiểu khác.

Nếu dùng @InitBinder để đăng ký PropertyEditor cục bộ, editor đó có thể tiếp tục áp dụng cho binder tương ứng. Hãy kiểm tra các editor hiện có khi chuyển đổi vì chúng có thể ảnh hưởng tới thuộc tính được bind. Tránh để hai cơ chế cùng cố chuyển đổi một trường nhưng dùng pattern hoặc quy tắc khác nhau.

## 5. Đăng ký conversion cho Spring Web Flow

Spring Web Flow có flow builder services để cấu hình các dịch vụ dùng khi xây dựng và thực thi flow, trong đó có conversion service cho binding của flow view. Vì thế, đăng ký converter qua WebMvcConfigurer là chưa đủ để kết luận rằng các view state trong Spring Web Flow cũng sử dụng cùng bộ quy tắc.

Với namespace XML, có thể khai báo conversion service và gắn nó vào flow builder services của registry:

~~~xml
<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="com.acme.web.StringToPaymentStatusConverter"/>
        </set>
    </property>
    <property name="formatters">
        <set>
            <bean class="com.acme.web.LocalDateFormatter"/>
        </set>
    </property>
</bean>

<webflow:flow-builder-services
        id="flowBuilderServices"
        conversion-service="conversionService"/>

<webflow:flow-registry
        id="flowRegistry"
        base-path="/WEB-INF/flows"
        flow-builder-services="flowBuilderServices">
    <webflow:flow-location-pattern value="/**/*-flow.xml"/>
</webflow:flow-registry>
~~~

Tên namespace và cách khai báo bean phải khớp với phiên bản Spring Web Flow và cấu hình XML mà ứng dụng đang dùng. Ý chính cần giữ là registry sử dụng flow builder services đã được gắn conversion service. Nếu flow registry không dùng builder services đó, converter có thể hoạt động trong controller MVC nhưng không hoạt động trong form binding của flow.

Với Java configuration, tạo flow builder services với conversion service rồi gắn builder services đó vào flow definition registry. API builder cụ thể phụ thuộc phiên bản Spring Web Flow. Về mặt cấu hình, hai thành phần cần cùng tham chiếu tới một instance conversion service đã được đăng ký:

~~~java
FormattingConversionService conversionService =
        new DefaultFormattingConversionService();

conversionService.addConverter(
        new StringToPaymentStatusConverter());
conversionService.addFormatter(
        new LocalDateFormatter());

// Cấu hình MVC sử dụng conversionService này.
// Cấu hình FlowBuilderServices cũng nhận cùng instance
// thông qua setConversionService(conversionService).
// Gắn FlowBuilderServices vào FlowDefinitionRegistry.
~~~

Trong dự án thực tế, nên khai báo conversion service như một bean do Spring quản lý thay vì tự tạo nhiều instance rải rác. Nếu MVC và Web Flow cần cùng quy tắc, hãy bảo đảm cả hai được cấu hình để dùng đúng bean đó. Kiểm tra tên bean và wiring thực tế trong cấu hình của dự án.

## 6. Binding trong flow view

Flow view có thể khai báo các thuộc tính được phép bind trong binder của view state:

~~~xml
<view-state id="booking" view="booking/form">
    <binder>
        <binding property="bookingDate"/>
        <binding property="paymentStatus"/>
        <binding property="amount"/>
    </binder>
    <transition on="continue" to="review"/>
</view-state>
~~~

Binder xác định các thuộc tính được phép nhận dữ liệu từ view. Conversion service được cấu hình cho flow builder services chịu trách nhiệm chuyển chuỗi sang kiểu tương ứng khi binding. Ví dụ, bookingDate có thể được chuyển thành LocalDate, paymentStatus thành enum PaymentStatus và amount thành BigDecimal.

Hãy chỉ bind những trường mà người dùng được phép thay đổi. Không bind các thuộc tính như totalPrice, ownerId, paymentApproved hoặc trạng thái hệ thống chỉ vì chúng có mặt trên domain object. Các giá trị đó phải được tính toán hoặc xác định phía server. Giới hạn binding giúp giảm nguy cơ mass assignment và làm rõ hợp đồng dữ liệu giữa view với flow.

Khi sử dụng các annotation định dạng như DateTimeFormat hoặc NumberFormat, hãy kiểm tra thành phần binding đang xử lý thuộc tính có đọc metadata annotation đó hay không. Không nên giả định mọi binder trong MVC và Web Flow tự động có cấu hình annotation giống nhau nếu flow builder services hoặc view factory đã được tùy chỉnh.

## 7. Định dạng số, ngày và locale

Conversion thường gặp lỗi khi ứng dụng không xác định rõ quy ước văn bản. Số 1,234 có thể được hiểu là một nghìn hai trăm ba mươi tư hoặc một phẩy hai ba bốn tùy locale. Ngày 04/05/2026 có thể là ngày 4 tháng 5 hoặc ngày 5 tháng 4. Không nên dùng locale mặc định của JVM để diễn giải dữ liệu người dùng.

Với số tiền, dùng BigDecimal thay cho float hoặc double khi cần tính toán chính xác. Formatter nên xác định rõ quy tắc dấu thập phân, dấu phân nhóm và số chữ số thập phân. Không chuyển tiền thành chuỗi đã định dạng rồi dùng chuỗi đó làm giá trị tính toán nội bộ.

Với ngày tháng, xác định loại dữ liệu trước khi chọn formatter:

- LocalDate cho ngày lịch không có thời điểm.
- LocalDateTime cho ngày và giờ không gắn timezone cụ thể.
- Instant cho một thời điểm tuyệt đối trên timeline.
- ZonedDateTime hoặc OffsetDateTime khi cần thể hiện múi giờ hoặc độ lệch múi giờ.

Locale điều khiển cách đọc và hiển thị văn bản; timezone điều khiển cách diễn giải thời điểm. Hai khái niệm này không thay thế nhau.

Giá trị rỗng cũng cần có quy tắc nhất quán. Một trường ngày tùy chọn có thể chuyển chuỗi rỗng thành null; một trường bắt buộc cần được validation báo thiếu. Đừng để converter tự thay giá trị rỗng bằng ngày hiện tại hoặc số 0 vì điều đó che giấu việc người dùng chưa nhập dữ liệu.

## 8. Conversion error và validation error

Khi parse thất bại, binding có thể tạo lỗi chuyển đổi cho trường tương ứng. Ví dụ người dùng nhập abc vào trường amount; hệ thống không thể chuyển thành BigDecimal. Đây là lỗi binding/conversion. Nếu người dùng nhập 0.00 và quy tắc nghiệp vụ yêu cầu số tiền lớn hơn 0, conversion thành công nhưng validation thất bại.

| Tình huống | Lớp xử lý phù hợp | Kết quả mong muốn |
|---|---|---|
| Ngày có định dạng không đọc được | Converter/Formatter hoặc binding error | Giữ ở view và hiển thị lỗi nhập ngày |
| Trường tùy chọn để trống | Quy tắc xử lý empty/null của binder | Gán null nếu trường cho phép |
| Số tiền âm | Validator hoặc service nghiệp vụ | Báo số tiền không hợp lệ |
| Mã trạng thái không tồn tại trong enum | Converter | Báo lựa chọn không được hỗ trợ |
| ID có định dạng đúng nhưng bản ghi không tồn tại | Service/repository | Báo không tìm thấy dữ liệu |
| Người dùng không có quyền sửa bản ghi | Authorization/service | Từ chối thao tác theo chính sách bảo mật |

Không bắt mọi lỗi conversion rồi trả null. Làm vậy khiến dữ liệu sai trông giống dữ liệu bị bỏ trống và có thể làm flow chuyển tiếp với model không đúng. Hãy ném lỗi chuyển đổi phù hợp hoặc để binding framework ghi nhận lỗi, sau đó hiển thị message code có thể dịch.

Validation nên chạy sau khi binding đã chuyển đổi các trường thành kiểu Java. Khi có lỗi, flow cần ở lại view state hoặc đi tới nhánh sửa dữ liệu theo thiết kế. Chỉ transition tới bước tiếp theo khi dữ liệu đã chuyển đổi và thỏa các quy tắc cần thiết.

## 9. So sánh trực tiếp cơ chế cũ và hiện hành

| Tiêu chí | PropertyEditor và CustomDateEditor | ConversionService và Formatter |
|---|---|---|
| Mô hình | Editor chuyển văn bản và đối tượng | Dịch vụ tra cứu converter/formatter theo kiểu |
| API thường dùng | setAsText, getAsText | Converter, GenericConverter, Formatter |
| Trạng thái | Editor có thể mutable và giữ trạng thái | Converter/Formatter nên được thiết kế stateless |
| Locale | Thường phải tự cấu hình hoặc xử lý trong editor | Formatter nhận Locale trực tiếp |
| Đăng ký | @InitBinder, registrar, binder initializer | FormatterRegistry, ConversionService bean |
| Tái sử dụng | Có thể cần đăng ký editor tại nhiều binder | Có thể dùng chung ở nhiều thành phần được cấu hình |
| Kiểm thử | Kiểm thử từng editor và binder | Kiểm thử converter/formatter và integration binding |
| Tương thích cũ | Phù hợp mã nguồn dựa trên JavaBeans | Hỗ trợ cấu hình mới, vẫn có thể coexist với editor cũ |

Không nên xem PropertyEditor là API đã bị loại bỏ hoàn toàn. Spring vẫn hỗ trợ editor trong binding để tương thích với ứng dụng cũ. Điểm khác biệt là ConversionService tạo một nơi đăng ký quy tắc chuyển đổi có kiểu, dễ quản lý và dễ chia sẻ hơn. Khi di chuyển, cần kiểm tra cả quy tắc parse, format, locale, giá trị rỗng và thông báo lỗi để tránh thay đổi hành vi.

## 10. Lộ trình chuyển đổi từ editor cũ

Một cách chuyển đổi an toàn là thực hiện từng kiểu dữ liệu:

1. Tìm các phương thức @InitBinder, PropertyEditorRegistrar, WebBindingInitializer và nơi đăng ký CustomDateEditor.
2. Ghi lại kiểu nguồn, kiểu đích, thuộc tính áp dụng, pattern, locale, xử lý null và hành vi khi parse lỗi.
3. Phân loại quy tắc: chuyển kiểu thuần túy dùng Converter; định dạng văn bản có locale dùng Formatter; trường hợp đặc biệt chỉ áp dụng một binder có thể tiếp tục dùng editor cục bộ trong giai đoạn chuyển tiếp.
4. Viết converter hoặc formatter có thể tái sử dụng, không giữ trạng thái request và không gọi repository.
5. Đăng ký conversion service cho Spring MVC và cấu hình flow builder services của Spring Web Flow.
6. Chạy test với dữ liệu hợp lệ, rỗng, sai định dạng, locale khác nhau và giá trị biên.
7. Chỉ bỏ editor cũ sau khi đã xác nhận mọi binder cần thiết dùng quy tắc mới.

Không thay toàn bộ Date bằng LocalDate trong một lần nếu các phần khác của hệ thống vẫn phụ thuộc Date, timezone hoặc định dạng cũ. Có thể chuyển từng trường và giữ adapter tại ranh giới hệ thống để giảm rủi ro.

## 11. Kiểm thử conversion và form binding

Converter và Formatter nên được kiểm thử độc lập trước khi kiểm thử toàn bộ flow. Với Converter, kiểm tra đầu vào hợp lệ, khoảng trắng, chuỗi rỗng và giá trị không được hỗ trợ. Với Formatter, kiểm tra cả parse lẫn print theo nhiều locale.

Ví dụ kiểm thử Formatter:

~~~java
class LocalDateFormatterTests {

    private final LocalDateFormatter formatter =
            new LocalDateFormatter();

    @Test
    void parsesAndPrintsUsingLocale() throws Exception {
        Locale locale = Locale.UK;
        LocalDate date = formatter.parse("15/04/26", locale);

        assertEquals(
                "15/04/26",
                formatter.print(date, locale));
    }
}
~~~

Pattern ngày ngắn phụ thuộc dữ liệu locale và JDK, vì vậy test nên chạy với locale được chỉ định rõ. Nếu ứng dụng yêu cầu pattern cố định, test cần dùng đúng pattern đó thay vì dựa vào FormatStyle.SHORT.

Ở cấp Spring MVC, kiểm thử WebDataBinder hoặc MockMvc để xác minh request form thực sự dùng conversion service đã đăng ký. Ở cấp Spring Web Flow, khởi chạy flow execution, gửi event từ view state và xác minh:

- Giá trị chuỗi được bind thành đúng kiểu Java.
- Formatter nhận đúng locale đang hoạt động.
- Trường không bind không thể ghi đè thuộc tính nhạy cảm.
- Lỗi conversion giữ người dùng ở bước có thể sửa dữ liệu.
- Validation được thực hiện trên giá trị đã chuyển đổi.
- Flow chỉ chuyển tới state tiếp theo khi dữ liệu hợp lệ.
- Flow builder services đang tham chiếu conversion service dự kiến.

Một converter unit test thành công không chứng minh flow registry đã được cấu hình đúng. Cần ít nhất một integration test đi qua binder của flow để phát hiện trường hợp MVC dùng converter nhưng Web Flow chưa được wiring.

## 12. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| MVC bind được nhưng flow view không bind được | Flow builder services chưa dùng conversion service | Kiểm tra flow registry và flow-builder-services |
| Ngày bị hiểu sai thứ tự | Dùng pattern cố định hoặc locale mặc định không đúng | Kiểm tra Locale và formatter |
| Số tiền sai dấu thập phân | Quy tắc số của trình duyệt và server không thống nhất | Kiểm tra locale, decimal/grouping separator và BigDecimal |
| Editor chạy ở controller nhưng không chạy trong flow | Editor được đăng ký cục bộ qua @InitBinder | Đăng ký quy tắc phù hợp cho flow builder services |
| Chuỗi rỗng trở thành giá trị mặc định sai | Converter tự thay empty bằng 0 hoặc ngày hiện tại | Xác định rõ quy tắc null/empty |
| Giá trị sai bị bỏ qua | Converter bắt lỗi và trả null | Để binding ghi nhận conversion error |
| Hai màn hình chuyển đổi khác nhau | MVC và Web Flow dùng hai conversion service hoặc editor khác nhau | Kiểm tra wiring và integration test |
| Test qua nhưng production lỗi | Khác locale, timezone, JDK hoặc cấu hình bean | Chỉ định môi trường test và kiểm tra cấu hình runtime |

Khi debug, hãy xác định request đang được xử lý bởi Spring MVC binder hay binder của flow view. Sau đó kiểm tra conversion service thực tế mà binder sử dụng, editor cục bộ đã đăng ký, locale hiện hành và message code của lỗi. Điều này giúp tìm đúng lớp gây lỗi thay vì sửa formatter một cách phỏng đoán.

## Kết luận

PropertyEditor và CustomDateEditor là cơ chế quen thuộc trong ứng dụng Spring cũ, thường được đăng ký theo binder hoặc thuộc tính. ConversionService cùng Converter và Formatter là cách tổ chức hiện hành rõ ràng hơn cho quy tắc chuyển đổi có kiểu và định dạng theo locale. Spring vẫn hỗ trợ editor để tương thích, vì vậy quá trình nâng cấp cần dựa trên hành vi thực tế của từng trường.

Với Spring Web Flow, hãy cấu hình conversion service cho flow builder services và bảo đảm nó nhất quán với quy tắc mà Spring MVC sử dụng. Kiểm thử cả parse, print, locale, giá trị rỗng, lỗi binding và transition sau validation. Khi conversion được tổ chức đúng, dữ liệu đi qua các state có kiểu rõ ràng, view hiển thị nhất quán và người dùng nhận được lỗi có thể sửa ngay tại bước nhập liệu.
