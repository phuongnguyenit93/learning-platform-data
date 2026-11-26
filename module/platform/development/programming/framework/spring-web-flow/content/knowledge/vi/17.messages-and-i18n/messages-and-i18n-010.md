# Locale và bản dịch cho hành trình nhiều bước

## Bối cảnh và mục tiêu

Bài học thuộc chương **Thông báo và ngôn ngữ** của module `SPRING_WEB_FLOW`. Spring Web Flow mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow. Trong một hành trình như đăng ký, đặt hàng hoặc mở tài khoản, người dùng có thể đi qua nhiều màn hình, nhận thông báo validation ở nhiều bước và quay lại một màn hình trước đó. Giao diện, nhãn, thông báo lỗi và cách định dạng ngày giờ cần nhất quán theo ngôn ngữ mà người dùng đã chọn trong suốt hành trình.

Locale là thông tin về ngôn ngữ và quy ước vùng miền đang được dùng để trình bày nội dung. Bản dịch là nội dung văn bản tương ứng với locale đó. Hai việc này liên kết với nhau nhưng không đồng nhất: chọn locale quyết định bộ message và quy tắc định dạng được dùng; message bundle cung cấp nội dung dịch cho các mã thông điệp.

Sau bài học, bạn có thể:

- Phân biệt locale, ngôn ngữ và bản dịch.
- Cấu hình Spring MVC để xác định và duy trì locale qua nhiều request.
- Tổ chức message bundle cho các ngôn ngữ được hỗ trợ.
- Hiển thị nhãn, thông báo và lỗi validation theo locale trong Spring Web Flow.
- Giữ locale nhất quán giữa flow cha, subflow và các lần submit.
- Kiểm thử chuyển ngôn ngữ, fallback, định dạng ngày số và thông báo lỗi trong hành trình nhiều bước.

## 1. Locale có vai trò gì trong một flow?

Một locale thường được biểu diễn bằng mã ngôn ngữ và có thể kèm vùng. Ví dụ:

- `vi`: tiếng Việt.
- `en`: tiếng Anh.
- `en-US`: tiếng Anh theo quy ước Hoa Kỳ.
- `en-GB`: tiếng Anh theo quy ước Vương quốc Anh.
- `fr-FR`: tiếng Pháp theo quy ước Pháp.

Locale có thể ảnh hưởng đến:

- Ngôn ngữ của tiêu đề, nhãn, hướng dẫn và nút.
- Nội dung thông báo thành công, cảnh báo và lỗi validation.
- Cách viết ngày tháng, số thập phân, phần nghìn và tiền tệ.
- Cách sắp xếp hoặc trình bày dữ liệu theo quy ước vùng miền.
- Cách hiển thị số nhiều và các thông điệp có tham số.

Locale không quyết định quyền truy cập, danh tính hoặc ngôn ngữ mà người dùng bắt buộc phải dùng. Nó là lựa chọn trình bày. Một người dùng có thể chọn giao diện tiếng Việt nhưng vẫn nhập địa chỉ ở quốc gia khác hoặc dùng một múi giờ khác.

Trong Spring Web Flow, một flow execution có thể kéo dài qua nhiều HTTP request. Nếu request đầu tiên dùng tiếng Việt nhưng request tiếp theo được xử lý với locale mặc định tiếng Anh, cùng một hành trình có thể xuất hiện nhãn tiếng Việt ở bước đầu và thông báo tiếng Anh ở bước sau. Vì vậy, ứng dụng cần xác định locale nhất quán ở mỗi request và có cơ chế lưu lựa chọn của người dùng qua các bước.

## 2. Phân biệt locale resolver và message source

Hai thành phần thường được cấu hình cùng nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **LocaleResolver** | Xác định locale áp dụng cho request hiện tại và, tùy loại resolver, lưu lựa chọn qua các request | Chọn `vi` từ session hoặc đọc locale từ cookie |
| **MessageSource** | Tìm nội dung thông điệp theo mã message và locale | Mã `booking.confirm.title` được dịch thành tiêu đề tiếng Việt hoặc tiếng Anh |
| **Formatter / ConversionService** | Chuyển đổi và trình bày giá trị có kiểu theo locale | Hiển thị số tiền, ngày hoặc số thập phân theo quy ước |
| **View technology** | Render nhãn, message và dữ liệu lên trang | JSP, Thymeleaf hoặc template engine khác |

LocaleResolver không tự dịch chuỗi. MessageSource cũng không tự quyết định người dùng đang dùng locale nào; nó nhận locale do ngữ cảnh hiện tại cung cấp. Formatter có thể dùng locale để định dạng giá trị nhưng không thay thế message bundle.

Một cách hình dung đơn giản:

1. Request đến ứng dụng.
2. Spring MVC xác định locale cho request.
3. View và các thành phần xử lý thông điệp dùng locale đó để tra message.
4. Formatter dùng locale đó để trình bày ngày, số và tiền tệ.
5. Nếu người dùng đổi ngôn ngữ, request tiếp theo được xử lý với locale mới và nội dung được render lại.

## 3. Xác định và duy trì locale trong Spring MVC

Spring MVC có thể xác định locale bằng nhiều cách. Lựa chọn phụ thuộc vào việc ứng dụng muốn tự động theo trình duyệt hay cho người dùng chủ động đổi ngôn ngữ.

| Cách xác định | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Accept-Language | Đọc header ngôn ngữ do trình duyệt gửi | Chọn ngôn ngữ ban đầu theo cài đặt trình duyệt |
| SessionLocaleResolver | Lưu locale trong HttpSession | Người dùng chọn ngôn ngữ và muốn giữ lựa chọn qua nhiều request |
| CookieLocaleResolver | Lưu locale trong cookie | Muốn duy trì lựa chọn mà không phụ thuộc session phía server |
| FixedLocaleResolver | Dùng một locale cố định | Ứng dụng chỉ hỗ trợ một locale hoặc cần cấu hình cố định |

Với wizard nhiều bước, một lựa chọn thường gặp là dùng locale theo header cho lần truy cập đầu tiên, sau đó cho phép người dùng chọn ngôn ngữ và lưu lựa chọn bằng session hoặc cookie. Không nên giả định mọi LocaleResolver đều hỗ trợ thay đổi locale theo cùng cách. Ví dụ, resolver chỉ dựa vào header thường không cho ứng dụng ghi đè locale bằng một lời gọi setLocale.

### Ví dụ dùng SessionLocaleResolver

Trong cấu hình Spring MVC kiểu Java, có thể khai báo:

```java
@Configuration
@EnableWebMvc
public class WebMvcConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.forLanguageTag("vi"));
        return resolver;
    }

    @Bean
    public LocaleChangeInterceptor localeChangeInterceptor() {
        LocaleChangeInterceptor interceptor =
                new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        return interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(localeChangeInterceptor());
    }
}
```

Ví dụ này đặt tiếng Việt làm locale mặc định và cho phép request có tham số `lang` yêu cầu đổi locale, chẳng hạn `?lang=en`. SessionLocaleResolver giữ lựa chọn qua các request tiếp theo trong cùng HttpSession.

Cấu hình thực tế cần bổ sung import và các bean liên quan của ứng dụng. Với phiên bản Spring MVC đang sử dụng, hãy kiểm tra API và thứ tự interceptor. Chỉ chấp nhận các locale mà ứng dụng hỗ trợ; không lấy một giá trị tùy ý từ query string rồi dùng nó để tải tài nguyên không được kiểm soát.

Nếu ứng dụng không muốn lưu lựa chọn trong session, có thể cân nhắc CookieLocaleResolver. Nếu muốn ưu tiên ngôn ngữ trình duyệt, có thể dùng AcceptHeaderLocaleResolver và cung cấp một cơ chế lựa chọn phù hợp với khả năng của resolver đó.

### Thay đổi locale giữa hành trình

Giả sử người dùng bắt đầu flow đăng ký bằng tiếng Việt, sau đó chọn tiếng Anh ở màn hình xác nhận. Request đổi locale phải đi qua cấu hình Spring MVC có LocaleChangeInterceptor hoặc cơ chế tương ứng. Các request tiếp theo của cùng hành trình cần nhận locale mới.

Một số điểm cần kiểm tra:

- Tham số đổi locale có được interceptor xử lý trên đường dẫn flow hay không.
- Locale được lưu ở session/cookie có còn sau khi chuyển state hoặc gọi subflow hay không.
- Request tiếp theo có thật sự dùng locale mới, thay vì chỉ đổi nhãn ở một view.
- Các message đã được tạo trước khi đổi locale có cần được tạo lại để hiển thị theo ngôn ngữ mới hay không.
- Locale có bị ghi đè bởi header trình duyệt hoặc một resolver khác không.

Không nên lưu một bản sao locale cũ trong flowScope rồi dùng nó vô thời hạn để tra message. Locale là ngữ cảnh của request; khi người dùng đổi ngôn ngữ, flow nên dùng locale mới ở request kế tiếp. Chỉ lưu lựa chọn riêng trong flow nếu nghiệp vụ thật sự yêu cầu một hành trình phải cố định ngôn ngữ từ đầu, và cần giải thích rõ hành vi đó cho người dùng.

## 4. Tổ chức message bundle

Message bundle là tập hợp các mã thông điệp và nội dung tương ứng với từng locale. Tổ chức theo mã ổn định giúp view, validator và action dùng chung nội dung, đồng thời tránh viết trực tiếp câu chữ vào flow definition hoặc mã Java.

Ví dụ cấu trúc tài nguyên:

```text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
```

Có thể cấu hình MessageSource như sau:

```java
@Bean
public MessageSource messageSource() {
    ReloadableResourceBundleMessageSource source =
            new ReloadableResourceBundleMessageSource();

    source.setBasename("classpath:messages");
    source.setDefaultEncoding("UTF-8");
    source.setFallbackToSystemLocale(false);

    return source;
}
```

Tên basename phải khớp vị trí tài nguyên thực tế. Với basename `classpath:messages`, Spring tìm bundle cơ sở và các biến thể locale tương ứng như `messages_vi.properties` hoặc `messages_en.properties`. Cần kiểm tra cấu hình này phù hợp với cách đóng gói và phiên bản Spring của dự án.

Ví dụ `messages_vi.properties`:

```properties
booking.title=Thông tin đặt chỗ
booking.step.details=Bước 1: Thông tin
booking.step.confirm=Bước 2: Xác nhận
booking.button.next=Tiếp tục
booking.button.back=Quay lại
booking.button.cancel=Hủy
booking.confirm.title=Xác nhận đặt chỗ
booking.confirm.success=Đặt chỗ đã được ghi nhận.
booking.guests.minimum=Số khách phải lớn hơn hoặc bằng {0}.
booking.dateOrder=Ngày trả phòng phải sau ngày nhận phòng.
booking.email.invalid=Vui lòng nhập địa chỉ email hợp lệ.
```

Ví dụ `messages_en.properties`:

```properties
booking.title=Booking details
booking.step.details=Step 1: Details
booking.step.confirm=Step 2: Confirmation
booking.button.next=Continue
booking.button.back=Back
booking.button.cancel=Cancel
booking.confirm.title=Confirm booking
booking.confirm.success=Your booking has been saved.
booking.guests.minimum=The number of guests must be at least {0}.
booking.dateOrder=The check-out date must be after the check-in date.
booking.email.invalid=Enter a valid email address.
```

Nếu có bundle cơ sở `messages.properties`, hãy dùng nó làm tập thông điệp fallback có chủ đích. Một key bị thiếu trong bundle tiếng Việt hoặc tiếng Anh có thể được tra ở bundle mặc định theo cấu hình MessageSource. Nếu không có nội dung fallback, ứng dụng có thể hiển thị mã message hoặc nội dung mặc định tùy cách gọi. Đừng dựa vào hành vi fallback ngẫu nhiên của máy chủ hoặc locale hệ điều hành.

### Quy tắc đặt message key

Nên đặt key theo chức năng và ngữ cảnh, ví dụ:

- `booking.title`
- `booking.step.address`
- `booking.validation.postalCode.invalid`
- `account.password.required`
- `flow.error.expired`

Key cần ổn định khi câu chữ thay đổi. Tránh dùng nguyên câu tiếng Việt làm key, vì khi dịch sang ngôn ngữ khác sẽ khó quản lý và khó tìm các nơi đang sử dụng message.

Thông điệp có tham số nên dùng placeholder như `{0}`, `{1}` thay vì nối chuỗi. Ví dụ, `booking.guests.minimum=At least {0} guests are required.` cho phép code truyền số tối thiểu mà không cần tạo nhiều câu khác nhau. Cần kiểm tra thứ tự tham số trong từng ngôn ngữ vì cấu trúc câu có thể khác nhau.

## 5. Dùng message trong view và trong Spring Web Flow

View technology thường có cú pháp riêng để tra message. Với JSP có thể dùng Spring message tag; với Thymeleaf có thể dùng cú pháp message expression. Ví dụ JSP:

```jsp
<%@ taglib prefix="spring" uri="http://www.springframework.org/tags" %>

<h1><spring:message code="booking.title"/></h1>
<button type="submit">
    <spring:message code="booking.button.next"/>
</button>
```

Ví dụ Thymeleaf:

```html
<h1 th:text="#{booking.title}">Booking details</h1>
<button type="submit" th:text="#{booking.button.next}">
    Continue
</button>
```

Cú pháp trên phụ thuộc công nghệ view và thư viện tag được cài đặt. Điều quan trọng là view tra message bằng key, để cùng một template có thể render nội dung khác nhau theo locale hiện tại.

Spring Web Flow có MessageContext để quản lý thông báo của flow, bao gồm thông báo validation. Một action hoặc validator có thể thêm message bằng code, source và nội dung dự phòng:

```java
MessageContext messages = context.getMessageContext();

messages.addMessage(
    new MessageBuilder()
        .error()
        .source("email")
        .code("booking.email.invalid")
        .defaultText("Vui lòng nhập địa chỉ email hợp lệ.")
        .build()
);
```

Ở đây `context` là RequestContext được cung cấp cho logic xử lý của flow. `source("email")` gắn lỗi với field email để view có thể hiển thị lỗi cạnh input. `code("booking.email.invalid")` cho phép message resolver tra nội dung theo locale; `defaultText` là nội dung dự phòng nếu không tìm được bản dịch phù hợp.

Cần bảo đảm cơ chế phân giải message của flow dùng đúng MessageSource và locale của request. Cách cấu hình chi tiết có thể khác theo phiên bản Spring Web Flow và cách dựng flow builder; hãy đối chiếu tài liệu của phiên bản dự án trước khi cấu hình. Không nên cho rằng chỉ cần tạo file properties là mọi message trong flow tự động được dịch nếu message resolver chưa được nối đúng.

### Thông báo và lỗi validation qua nhiều bước

Một flow đặt hàng có thể có message ở nhiều state:

| Bước | Ví dụ message key | Mục đích |
| --- | --- | --- |
| Nhập thông tin | `booking.email.invalid` | Hướng dẫn sửa email |
| Chọn địa chỉ | `booking.postalCode.invalid` | Báo mã bưu chính không hợp lệ |
| Xác nhận | `booking.confirm.title` | Hiển thị tiêu đề xác nhận |
| Hoàn tất | `booking.confirm.success` | Thông báo lưu thành công |
| Execution hết hạn | `flow.error.expired` | Hướng dẫn bắt đầu lại hành trình |

Khi người dùng chuyển từ state nhập thông tin sang state xác nhận, các key vẫn giữ nguyên nhưng nội dung được chọn theo locale hiện tại. Subflow cũng cần dùng cùng nguồn message và ngữ cảnh locale để tránh trường hợp flow cha hiển thị tiếng Việt nhưng form địa chỉ trong subflow lại hiển thị tiếng Anh.

## 6. Locale trong form binding, validation và định dạng dữ liệu

Locale không chỉ ảnh hưởng đến câu chữ. Nó còn có thể ảnh hưởng cách người dùng nhập và đọc ngày, số, tiền tệ.

Ví dụ, số thập phân có thể được viết bằng dấu phẩy ở một locale và dấu chấm ở locale khác. Ngày có thể được trình bày theo thứ tự ngày-tháng-năm hoặc tháng-ngày-năm. Nếu ứng dụng nhận một chuỗi ngày theo định dạng địa phương, ConversionService/Formatter cần biết locale để chuyển đổi đúng.

Cần phân biệt:

- **Định dạng hiển thị:** cách trình bày một giá trị đã có kiểu, ví dụ số tiền hoặc ngày trên trang xác nhận.
- **Định dạng nhập liệu:** cách parse chuỗi người dùng gửi vào model.
- **Quy tắc nghiệp vụ:** giá trị có được chấp nhận hay không, ví dụ ngày trả phòng phải sau ngày nhận phòng.

Một ngày được parse thành công theo locale vẫn có thể không hợp lệ về nghiệp vụ. Ngược lại, chuỗi ngày không parse được là lỗi chuyển đổi/binding, không phải lỗi quy tắc ngày.

Với ứng dụng dùng HTML `input type="date"`, trình duyệt thường gửi giá trị theo định dạng chuẩn hóa như `yyyy-MM-dd`, dù cách hiển thị cho người dùng có thể phụ thuộc trình duyệt và hệ điều hành. Nếu dùng input văn bản với định dạng ngày địa phương, cần cấu hình formatter và thông báo mẫu nhập tương ứng. Không tự thay đổi định dạng đầu vào chỉ vì đã đổi ngôn ngữ.

### Ví dụ định dạng theo locale

```java
NumberFormat vietnameseNumber =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));

NumberFormat usNumber =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("en-US"));

String vi = vietnameseNumber.format(1234567.89);
String en = usNumber.format(1234567.89);
```

Kết quả định dạng cụ thể phụ thuộc JDK và locale data đang dùng. Trong ứng dụng Spring, ưu tiên cấu hình formatter/conversion service dùng locale của request thay vì tự tạo NumberFormat rải rác ở nhiều action.

Locale và múi giờ cũng là hai khái niệm khác nhau. Locale quyết định quy ước ngôn ngữ và định dạng; timezone quyết định cách chuyển thời điểm tuyệt đối thành giờ địa phương. Người dùng chọn tiếng Việt không có nghĩa họ luôn ở múi giờ Việt Nam. Với lịch đặt chỗ, cần lưu trữ thời điểm theo quy tắc nghiệp vụ rõ ràng và định dạng theo timezone đã chọn hoặc đã xác định cho địa điểm.

## 7. Duy trì locale giữa flow cha, subflow và request

Một flow execution có thể gồm nhiều flow session và nhiều request. Locale nên được xác định ở tầng web cho mỗi request; khi dùng SessionLocaleResolver hoặc CookieLocaleResolver, lựa chọn có thể được giữ xuyên suốt hành trình.

Ví dụ, flow `checkout` gọi subflow `address`:

1. Request đầu tiên đến với locale `vi`.
2. Flow checkout hiển thị nhãn và hướng dẫn tiếng Việt.
3. Checkout gọi subflow address; request tiếp theo vẫn được resolver xác định locale `vi`.
4. Subflow hiển thị form và validation message bằng tiếng Việt.
5. Người dùng đổi locale sang `en`; resolver lưu lựa chọn mới.
6. Các request tiếp theo, gồm cả request tiếp tục subflow và quay về checkout, được xử lý theo locale `en`.

Không cần sao chép toàn bộ message bundle vào từng flow. Cả flow cha và subflow có thể sử dụng chung MessageSource nếu cấu hình ứng dụng và flow builder được nối đúng. Nếu một subflow dùng message source riêng, cần bảo đảm các key dùng chung có bản dịch tương thích.

Locale không nên được truyền như một field nghiệp vụ trong input/output của subflow nếu nó chỉ là ngữ cảnh trình bày của request. Truyền locale như dữ liệu đầu vào chỉ hợp lý khi subflow có yêu cầu nghiệp vụ rõ ràng, chẳng hạn tạo một tài liệu theo ngôn ngữ mà người dùng đã xác nhận. Khi đó, hãy phân biệt ngôn ngữ của tài liệu được tạo với locale hiện tại của giao diện.

## 8. Fallback và xử lý bản dịch còn thiếu

Một ứng dụng thực tế có thể chưa dịch đủ tất cả key ở mọi ngôn ngữ. Cần xác định chính sách fallback để người dùng không nhìn thấy mã kỹ thuật hoặc nội dung trống.

Một chiến lược thường dùng:

1. Tra key trong bundle đúng locale, ví dụ `messages_vi.properties`.
2. Nếu thiếu, tra bundle cơ sở `messages.properties` hoặc locale mặc định theo cấu hình.
3. Nếu vẫn thiếu, dùng default text được cung cấp ở nơi tạo message hoặc một thông báo dự phòng phù hợp.
4. Ghi nhận key thiếu trong log phát triển/QA để nhóm bổ sung bản dịch.

Không nên dùng locale hệ điều hành của máy chủ làm fallback ngoài ý muốn. Kết quả có thể khác nhau giữa máy developer, staging và production. Cấu hình fallback rõ ràng giúp bản dịch có hành vi nhất quán.

Khi thêm một locale mới, cần kiểm tra không chỉ tiêu đề và nút mà cả validation, lỗi nghiệp vụ, thông báo hết phiên, nội dung email hoặc tài liệu được sinh ra từ flow nếu các thành phần đó thuộc phạm vi sản phẩm.

### Quy ước dịch thuật

- Dùng thuật ngữ nhất quán giữa các bước trong cùng hành trình.
- Giữ nguyên placeholder và thứ tự tham số theo hợp đồng của message key.
- Không ghép câu từ nhiều mảnh nếu ngữ pháp của ngôn ngữ đích có thể thay đổi trật tự.
- Không nhúng HTML tùy ý vào message nếu view chưa có cơ chế render an toàn.
- Kiểm tra độ dài bản dịch để nhãn hoặc nút không bị cắt.
- Tránh đưa dữ liệu cá nhân hoặc nội dung do người dùng nhập vào message key.
- Tách message cho lỗi kỹ thuật nội bộ khỏi thông báo thân thiện hiển thị cho người dùng.

## 9. Đổi locale an toàn trong một hành trình

Nếu ứng dụng cho phép đổi ngôn ngữ giữa chừng, nên cung cấp một danh sách locale được hỗ trợ, ví dụ `vi` và `en`. Không cho phép request chọn một mã locale tùy ý để truy cập các tài nguyên ngoài danh sách đã định.

Một thao tác đổi locale nên:

- Chỉ chấp nhận locale nằm trong allowlist.
- Lưu lựa chọn bằng resolver hỗ trợ thay đổi locale.
- Giữ nguyên flow execution và state hiện tại nếu request được thiết kế để đổi ngôn ngữ tại chỗ.
- Render lại view bằng locale mới.
- Giữ nguyên dữ liệu form và kết quả nghiệp vụ trong flow scope.
- Không thay đổi quyền, danh tính hoặc trạng thái xác thực của người dùng.

Đổi locale không nên làm mất dữ liệu form đang nhập. Nếu cơ chế đổi locale tạo một request mới hoặc redirect, cần kiểm tra flow execution key và dữ liệu view/flow còn được khôi phục đúng. Nếu một message cũ đã được giải quyết thành văn bản trước khi đổi locale, hãy cân nhắc tạo lại thông báo ở request mới thay vì giả định message đã tồn tại sẽ tự dịch lại.

## 10. Kiểm thử locale và message trong flow

Kiểm thử cần bao phủ cả lựa chọn locale, nội dung dịch, fallback và các bước của flow.

| Ca kiểm thử | Cách thực hiện | Điều cần xác minh |
| --- | --- | --- |
| Locale mặc định | Mở flow mà không gửi lựa chọn ngôn ngữ | Resolver trả locale mặc định đã cấu hình |
| Locale từ trình duyệt | Gửi Accept-Language với ngôn ngữ được hỗ trợ | Resolver chọn đúng locale nếu ứng dụng dùng header |
| Người dùng đổi locale | Gửi tham số đổi locale như `lang=en` | Session/cookie lưu lựa chọn theo resolver |
| Tiếp tục flow | Đổi locale rồi submit bước tiếp theo | View tiếp theo dùng locale mới và execution vẫn tiếp tục |
| Subflow | Gọi subflow sau khi chọn locale | Nhãn và validation message của subflow cùng locale |
| Binding error | Nhập ngày sai định dạng | Lỗi chuyển đổi hiển thị bằng ngôn ngữ hiện tại |
| Validation error | Nhập dữ liệu parse được nhưng vi phạm quy tắc | Thông báo validation đúng bản dịch |
| Message thiếu | Cố ý bỏ một key trong bundle locale | Fallback diễn ra theo chính sách, không lộ mã kỹ thuật |
| Placeholder | Dùng message có tham số | Giá trị được thay thế đúng và câu vẫn đúng ngữ pháp |
| Định dạng số/ngày | Render cùng dữ liệu với hai locale | Định dạng hiển thị phù hợp từng locale |
| Hai flow cùng session | Mở hai wizard và đổi locale ở một tab | Xác nhận hành vi locale dùng chung theo resolver/session là đúng với thiết kế sản phẩm |
| Session hết hạn | Tiếp tục flow sau khi session resolver mất dữ liệu | Ứng dụng dùng locale mặc định hoặc hướng dẫn khôi phục phù hợp |

Với SessionLocaleResolver, locale thường được chia sẻ ở cấp HttpSession. Vì thế, đổi locale trong một tab có thể ảnh hưởng tab khác thuộc cùng session. Nếu sản phẩm muốn mỗi flow execution hoặc mỗi tab có locale độc lập, cần thiết kế lựa chọn locale theo execution hoặc theo URL một cách tường minh; không thể kỳ vọng session resolver tự cô lập lựa chọn theo tab.

Nên có kiểm thử tích hợp qua Spring MVC để xác nhận interceptor, resolver, MessageSource và flow execution phối hợp đúng. Kiểm thử trực tiếp MessageSource chỉ chứng minh bundle có thể tra key; nó không chứng minh request của flow đang nhận đúng locale.

## 11. Quy trình xử lý khi một bước hiển thị sai ngôn ngữ

Khi một state hiển thị tiếng Anh trong khi các bước khác là tiếng Việt, hãy kiểm tra theo thứ tự:

1. Ghi lại request URL, header Accept-Language và tham số đổi locale.
2. Xác định LocaleResolver thực tế đang được dùng trong request.
3. Kiểm tra locale được lưu trong session/cookie và giá trị resolver trả về ở request tiếp theo.
4. Kiểm tra MessageSource có basename và bundle đúng locale không.
5. Kiểm tra message key có tồn tại ở bundle mong muốn và có bị sai chính tả không.
6. Kiểm tra flow message resolver có dùng cùng MessageSource và locale với Spring MVC không.
7. Nếu chỉ subflow sai ngôn ngữ, kiểm tra cấu hình view, message source và request mapping của subflow.
8. Nếu chỉ lỗi validation sai ngôn ngữ, kiểm tra message code, default text và thời điểm message được tạo.
9. Kiểm tra fallback có đang chọn bundle cơ sở hoặc locale mặc định ngoài ý muốn không.

Đừng bắt đầu bằng cách thay tất cả message key. Nguyên nhân có thể nằm ở LocaleResolver, request không đi qua interceptor, bundle không được đóng gói hoặc flow builder dùng message source khác.

## 12. Checklist triển khai

- [ ] Locale mặc định và danh sách locale được hỗ trợ đã được xác định.
- [ ] LocaleResolver phù hợp với cách người dùng chọn và duy trì ngôn ngữ.
- [ ] Nếu dùng SessionLocaleResolver hoặc CookieLocaleResolver, đã kiểm tra hành vi qua nhiều request.
- [ ] LocaleChangeInterceptor hoặc cơ chế đổi locale chỉ chấp nhận giá trị trong allowlist.
- [ ] MessageSource có basename đúng, encoding UTF-8 và chính sách fallback rõ ràng.
- [ ] Message bundle có key nhất quán cho nhãn, nút, validation và lỗi flow.
- [ ] View tra message bằng key thay vì hard-code câu chữ.
- [ ] MessageContext của Spring Web Flow được nối với message resolver phù hợp.
- [ ] Flow cha và subflow hiển thị cùng locale theo thiết kế.
- [ ] Formatter/conversion service xử lý ngày và số theo locale được xác định.
- [ ] Locale được phân biệt với timezone và quy tắc nghiệp vụ.
- [ ] Có test cho đổi locale, subflow, validation, fallback và nhiều flow trong cùng session.

## 13. Bài tập thực hành

Xây dựng flow đăng ký tài khoản có ba bước: nhập thông tin, xác nhận và hoàn tất. Flow có subflow `address` để nhập địa chỉ.

1. Tạo `messages_vi.properties` và `messages_en.properties` với các key cho tiêu đề, nhãn, nút, validation và thông báo hoàn tất.
2. Cấu hình MessageSource với UTF-8 và basename phù hợp.
3. Cấu hình SessionLocaleResolver mặc định là `vi` và một cơ chế đổi locale bằng tham số `lang`.
4. Hiển thị nhãn bằng message key trong view của flow đăng ký và subflow địa chỉ.
5. Tạo validation error cho email và mã bưu chính bằng MessageContext, dùng message code thay vì chỉ ghi câu cố định.
6. Bắt đầu flow bằng tiếng Việt, đổi sang tiếng Anh ở bước xác nhận rồi tiếp tục hoàn tất; xác minh subflow và flow cha đều dùng locale đã chọn.
7. Xóa có chủ đích một message key trong bundle tiếng Anh để kiểm tra fallback.
8. Render cùng một số tiền và ngày theo `vi-VN` và `en-US`, đồng thời giải thích vì sao timezone cần được xử lý riêng.

**Tiêu chí hoàn thành:** người học phân biệt được LocaleResolver với MessageSource; duy trì locale qua các request của một flow; dịch được nhãn và validation message ở cả flow cha lẫn subflow; giải thích được fallback và ảnh hưởng của locale tới định dạng; đồng thời kiểm thử được trường hợp đổi ngôn ngữ giữa hành trình.

## Kết luận

Một hành trình Spring Web Flow cần giữ ngôn ngữ nhất quán qua nhiều state, request và subflow. LocaleResolver xác định locale cho request; MessageSource cung cấp bản dịch theo key; MessageContext giúp flow tạo thông báo có thể bản địa hóa; formatter xử lý cách trình bày dữ liệu. Khi cấu hình rõ locale mặc định, cách lưu lựa chọn, message bundle, fallback và kiểm thử tích hợp, người dùng có thể đổi ngôn ngữ giữa hành trình mà vẫn giữ được tiến trình và dữ liệu đang nhập.

