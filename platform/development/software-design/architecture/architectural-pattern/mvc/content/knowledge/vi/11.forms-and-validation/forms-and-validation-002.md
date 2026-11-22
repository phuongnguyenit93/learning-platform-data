# Liên kết dữ liệu nhập (data binding) và lỗi chuyển đổi kiểu

Trong ứng dụng MVC web, dữ liệu người dùng gửi lên thường xuất hiện dưới dạng chuỗi trong query parameter hoặc form field. Trong khi đó, mã Java cần làm việc với các kiểu có ý nghĩa như số nguyên, ngày tháng, số tiền, mã định danh và các đối tượng nghiệp vụ. Data binding là quá trình ánh xạ dữ liệu ở ranh giới request vào các tham số hoặc đối tượng Java; conversion là bước chuyển một giá trị từ kiểu nguồn sang kiểu đích.

Nếu quá trình binding hoặc chuyển đổi thất bại, Controller cần nhận biết lỗi và trả phản hồi phù hợp. Người dùng có thể sửa biểu mẫu, API client có thể sửa JSON, còn hệ thống vẫn phải bảo vệ dữ liệu và quy tắc nghiệp vụ ở phía máy chủ.

Bài học này tập trung vào data binding và lỗi chuyển đổi kiểu trong Spring MVC, đồng thời làm rõ sự khác nhau giữa binding, conversion và validation.

Các đoạn Java dưới đây là ví dụ theo Spring MVC và Jakarta Bean Validation. Một số import, getter/setter, kiểu phụ trợ và cấu hình ứng dụng được lược bỏ để tập trung vào cơ chế đang giải thích.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích data binding và vị trí của nó trong vòng đời HTTP request.
- Phân biệt request parameter, path variable, form object và JSON body.
- Mô tả vai trò của ConversionService, Converter, Formatter và WebDataBinder.
- Nhận biết lỗi chuyển đổi kiểu và đọc lỗi từ BindingResult.
- Xử lý các giá trị thiếu, rỗng, null, khoảng trắng và định dạng sai.
- Cấu hình binding có kiểm soát để hạn chế mass assignment.
- Phân biệt lỗi binding của HTML form với lỗi giải mã JSON.
- Kiểm thử conversion và binding trong Controller.

## 2. Data binding là gì?

Data binding là quá trình đưa dữ liệu từ một nguồn bên ngoài vào một kiểu dữ liệu mà ứng dụng có thể làm việc. Trong một request web, nguồn dữ liệu có thể là:

- Query parameter trong URL, ví dụ /orders?page=2.
- Path variable, ví dụ /orders/42.
- Trường trong HTML form gửi bằng GET hoặc POST.
- Header hoặc cookie.
- Nội dung request body, thường là JSON hoặc XML.

Ví dụ, trình duyệt gửi biểu mẫu với các giá trị:

~~~text
productCode=BOOK-01
quantity=3
arrivalDate=2026-12-15
~~~

Ở phía Java, ứng dụng muốn nhận được một đối tượng có cấu trúc:

~~~java
public class CreateOrderForm {
    private String productCode;
    private Integer quantity;
    private LocalDate arrivalDate;

    // Getter và setter.
}
~~~

Framework cần ánh xạ tên trường productCode vào thuộc tính productCode, quantity vào Integer và arrivalDate vào LocalDate. Việc ánh xạ tên và gán giá trị là binding; việc chuyển chuỗi "3" thành Integer hoặc chuỗi ngày thành LocalDate là conversion.

Data binding giúp Controller không phải tự đọc từng tham số và tự chuyển kiểu. Tuy nhiên, binding không xác nhận rằng người dùng có quyền thực hiện hành động hoặc rằng dữ liệu thỏa mãn quy tắc nghiệp vụ.

## 3. Vị trí của binding trong luồng MVC

Một luồng xử lý form thường gồm các bước:

1. Router chọn Controller dựa trên URL và HTTP method.
2. Spring MVC đọc dữ liệu request.
3. WebDataBinder tạo hoặc chuẩn bị đối tượng đích và ánh xạ các trường.
4. ConversionService hoặc PropertyEditor chuyển dữ liệu sang kiểu Java.
5. Bean Validation kiểm tra các ràng buộc được khai báo nếu được yêu cầu.
6. Controller đọc kết quả binding và validation.
7. Controller gọi ca sử dụng khi dữ liệu đầu vào hợp lệ.
8. Controller chọn View, redirect hoặc response phù hợp.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Dispatcher as DispatcherServlet
    participant Binder as WebDataBinder
    participant Converter as ConversionService
    participant Validator as Bean Validation
    participant Controller as Controller

    User->>Browser: Gửi biểu mẫu
    Browser->>Dispatcher: POST /orders
    Dispatcher->>Controller: Chọn handler method
    Dispatcher->>Binder: Chuẩn bị tham số @ModelAttribute
    Binder->>Converter: Chuyển String sang kiểu đích
    Converter-->>Binder: Giá trị đã chuyển hoặc lỗi
    Binder->>Validator: Chạy validation nếu handler yêu cầu
    Validator-->>Binder: Bổ sung lỗi ràng buộc nếu có
    Binder-->>Controller: Gọi handler với form và BindingResult
    Controller-->>Browser: Render form lỗi hoặc redirect thành công
~~~

Thứ tự chi tiết có thể khác tùy loại tham số và cơ chế xử lý request. Với HTML form dùng @ModelAttribute, Spring sử dụng WebDataBinder để bind các request parameter vào đối tượng. Sau bước bind, validator được gọi nếu handler yêu cầu validation; lỗi conversion đã ghi nhận vẫn nằm trong BindingResult, và validator có thể bổ sung lỗi ràng buộc trên đối tượng đã bind một phần. Với JSON body dùng @RequestBody, HttpMessageConverter đọc và giải mã body trước khi Bean Validation được áp dụng.

## 4. Các cách nhận dữ liệu trong Spring MVC

Không phải mọi dữ liệu đầu vào đều được bind theo cùng một cách. Chọn annotation theo nguồn và ý nghĩa của dữ liệu.

| Annotation | Nguồn dữ liệu | Ví dụ |
|---|---|---|
| @RequestParam | Query parameter hoặc form parameter đơn lẻ | page=2, keyword=book |
| @PathVariable | Một phần của URL path | /orders/42 |
| @ModelAttribute | Request parameter được bind vào đối tượng form | Form tạo đơn |
| @RequestHeader | HTTP header | Accept-Language |
| @CookieValue | Cookie | Session cookie |
| @RequestBody | Nội dung request body qua HttpMessageConverter | JSON API |

### 4.1. @RequestParam

Dùng khi Controller cần một hoặc vài tham số riêng lẻ:

~~~java
@GetMapping("/orders")
public String list(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(required = false) String keyword,
        Model model) {

    model.addAttribute("orders", orderService.search(page, keyword));
    return "orders/list";
}
~~~

Nếu tham số bắt buộc không có, Spring thường trả lỗi thiếu request parameter trước khi gọi handler method. Nếu tham số có nhưng không chuyển được sang kiểu đích, Spring phát sinh lỗi kiểu tham số không phù hợp.

defaultValue có thể được dùng khi tham số không được gửi hoặc giá trị là chuỗi rỗng. Vì vậy, cần chọn default value theo đúng ý nghĩa nghiệp vụ; đừng dùng mặc định 0 hoặc chuỗi rỗng để che giấu dữ liệu bắt buộc bị thiếu.

### 4.2. @PathVariable

Dùng để lấy giá trị từ URL:

~~~java
@GetMapping("/orders/{id}")
public String detail(@PathVariable UUID id, Model model) {
    model.addAttribute("order", orderService.getDetails(id));
    return "orders/detail";
}
~~~

Nếu đường dẫn chứa một giá trị không thể chuyển thành UUID, handler không thể nhận được kiểu đích. Spring có thể báo MethodArgumentTypeMismatchException. Lỗi này xảy ra ở bước giải quyết tham số, không phải lỗi validation của một form object.

### 4.3. @ModelAttribute

Dùng để bind nhiều request parameter vào một đối tượng:

~~~java
@PostMapping("/orders")
public String create(
        @ModelAttribute("form") CreateOrderForm form,
        BindingResult bindingResult) {
    // Xử lý kết quả binding.
}
~~~

Spring tạo hoặc lấy đối tượng form, bind các thuộc tính tương ứng và ghi nhận lỗi chuyển đổi trong BindingResult. Đây là cơ chế thường gặp với form HTML server-rendered.

### 4.4. @RequestBody

Dùng khi dữ liệu nằm trong body, thường là JSON:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<?> createApi(
        @Valid @RequestBody CreateOrderRequest request) {
    // Gọi use case và trả response DTO.
    return ResponseEntity.accepted().build();
}
~~~

Với @RequestBody, Spring dùng HttpMessageConverter, thường là Jackson cho JSON, để giải mã body thành đối tượng Java. Nếu JSON sai cú pháp hoặc giá trị không thể giải mã sang kiểu đích, quá trình đọc body thất bại trước khi Controller nhận được đối tượng hoàn chỉnh.

Đây là điểm khác biệt quan trọng: lỗi binding của form object thường được ghi vào BindingResult; lỗi giải mã JSON thường được biểu diễn bằng HttpMessageNotReadableException và xử lý qua exception handler.

## 5. Conversion và các kiểu dữ liệu

Request parameter thường là chuỗi, nhưng đối tượng Java có thể chứa nhiều kiểu khác nhau. Spring MVC sử dụng cơ chế chuyển đổi để chuyển giá trị sang kiểu đích.

### 5.1. Các chuyển đổi phổ biến

| Giá trị request | Kiểu Java đích | Ví dụ |
|---|---|---|
| "25" | Integer | Số lượng |
| "true" | Boolean | Trạng thái bật/tắt |
| "2026-12-15" | LocalDate | Ngày đến |
| "10:30" | LocalTime | Giờ bắt đầu |
| "2026-12-15T10:30:00Z" | Instant | Thời điểm |
| "550e8400-e29b-41d4-a716-446655440000" | UUID | Định danh |
| "BOOK-01" | Kiểu ProductCode tùy chỉnh | Mã sản phẩm |

Các kiểu chuẩn thường có converter hoặc formatter được cung cấp sẵn. Với kiểu miền riêng, ứng dụng có thể đăng ký converter hoặc formatter để mô tả cách chuyển đổi.

### 5.2. Lỗi chuyển đổi kiểu

Giả sử form có trường quantity kiểu Integer, nhưng request gửi:

~~~text
quantity=three
~~~

Chuỗi "three" không thể chuyển thành Integer. Đây là lỗi binding/conversion, chưa phải lỗi nghiệp vụ như số lượng vượt tồn kho.

Các ví dụ khác:

- Chuỗi ngày không theo định dạng được hỗ trợ.
- UUID có ký tự sai.
- Chuỗi rỗng được gửi vào một thuộc tính kiểu số.
- Một giá trị không thuộc tập enum hợp lệ.
- Giá trị số vượt phạm vi của kiểu đích.

Controller cần phân biệt lỗi chuyển đổi với lỗi validation. Thông báo “Số lượng phải là số nguyên” phù hợp với lỗi chuyển đổi; thông báo “Số lượng phải từ 1 đến 100” phù hợp với lỗi ràng buộc sau khi đã chuyển được thành số.

### 5.3. Sử dụng kiểu wrapper thay cho primitive khi cần phân biệt thiếu dữ liệu

Với form, Integer thường hữu ích hơn int khi trường có thể không được gửi. Integer có thể là null để biểu diễn chưa có giá trị; int không thể biểu diễn null.

~~~java
public class QuantityForm {
    @NotNull(message = "Vui lòng nhập số lượng.")
    @Min(value = 1, message = "Số lượng phải lớn hơn 0.")
    private Integer quantity;

    // Getter và setter.
}
~~~

Nếu dùng int, giá trị mặc định của Java là 0. Khi đó, ứng dụng có thể khó phân biệt trường bị bỏ trống với người dùng thực sự gửi số 0. Kiểu wrapper giúp mô hình hóa trạng thái chưa nhập rõ ràng hơn.

Với JSON, hành vi khi thuộc tính primitive bị thiếu còn phụ thuộc cấu hình giải mã. Dùng kiểu wrapper và ràng buộc phù hợp thường giúp hợp đồng biểu đạt rõ hơn.

## 6. Phân biệt binding, conversion và validation

Ba khái niệm có liên quan nhưng giải quyết những câu hỏi khác nhau.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Binding | Giá trị request được ánh xạ vào thuộc tính hoặc tham số nào? | productCode vào form.productCode |
| Conversion | Giá trị có chuyển được sang kiểu Java đích không? | "3" thành Integer |
| Validation | Giá trị đã chuyển có thỏa mãn ràng buộc không? | quantity phải từ 1 đến 100 |
| Business rule | Thao tác có được phép trong trạng thái nghiệp vụ hiện tại không? | Còn đủ tồn kho để đặt hàng |

Ví dụ với quantity:

- Request không có trường quantity: thiếu dữ liệu.
- Request gửi quantity=abc: lỗi chuyển đổi.
- Request gửi quantity=0: chuyển đổi thành công nhưng vi phạm @Min(1).
- Request gửi quantity=5: hợp lệ về kiểu và ràng buộc cơ bản, nhưng có thể vẫn không đủ tồn kho.

Một ứng dụng tốt không coi mọi lỗi đều là “validation error”. Việc phân loại đúng giúp Controller hiển thị thông báo phù hợp và tránh đưa quy tắc nghiệp vụ vào converter.

## 7. BindingResult và cách đọc lỗi

Khi bind form object, Spring có thể lưu các lỗi vào BindingResult. Controller cần đặt BindingResult ngay sau tham số được bind để nhận các lỗi tương ứng.

~~~java
@PostMapping("/bookings")
public String create(
        @Valid @ModelAttribute("form") BookingForm form,
        BindingResult errors,
        Model model) {

    if (errors.hasErrors()) {
        populateOptions(model);
        return "bookings/new";
    }

    bookingService.create(toCommand(form));
    return "redirect:/bookings";
}
~~~

BindingResult chứa các loại lỗi khác nhau:

- FieldError: lỗi gắn với một thuộc tính cụ thể.
- ObjectError: lỗi áp dụng cho toàn bộ đối tượng.
- Binding failure: lỗi khi không thể chuyển đổi hoặc bind giá trị.
- Validation failure: lỗi do constraint hoặc validator phát hiện.

Có thể kiểm tra lỗi:

~~~java
if (errors.hasFieldErrors("quantity")) {
    FieldError error = errors.getFieldError("quantity");

    String code = error.getCode();
    boolean conversionFailed = error.isBindingFailure();
    Object rejectedValue = error.getRejectedValue();
}
~~~

Không nên hiển thị rejectedValue một cách tự động. Giá trị bị từ chối có thể chứa dữ liệu nhạy cảm hoặc chuỗi do người dùng kiểm soát. Chỉ sử dụng nó khi cần và phải escape khi render.

### 7.1. Phân biệt lỗi binding và lỗi validation

Một FieldError có thể mang mã typeMismatch khi conversion thất bại. Các mã validation thường phản ánh constraint như NotNull, Min, Size hoặc Email.

Không nên phụ thuộc cứng vào chuỗi thông báo cuối cùng để phân loại. Dùng message code và cấu trúc lỗi của Spring để ánh xạ nội dung phù hợp.

### 7.2. Hiển thị lỗi trong View

Trong template Thymeleaf, dùng th:field để liên kết input với thuộc tính của form object và th:errors để trình bày lỗi của trường. Phần tóm tắt lỗi có thể được xây dựng từ các lỗi trong BindingResult. Cần bảo đảm template escape thông báo và giữ lại các giá trị không nhạy cảm khi render lại biểu mẫu.

## 8. Cấu hình WebDataBinder

WebDataBinder là thành phần của Spring MVC hỗ trợ binding request vào đối tượng đích, đăng ký editor, kiểm soát thuộc tính và điều chỉnh hành vi binding.

Có thể cấu hình binder riêng cho một form object bằng @InitBinder:

~~~java
@InitBinder("form")
void configureFormBinder(WebDataBinder binder) {
    binder.setAllowedFields(
        "fullName",
        "email",
        "quantity",
        "arrivalDate",
        "note"
    );

    binder.registerCustomEditor(
        String.class,
        "note",
        new StringTrimmerEditor(true)
    );

    binder.setAutoGrowCollectionLimit(100);
}
~~~

Trong ví dụ:

- setAllowedFields tạo allowlist các thuộc tính được phép bind.
- StringTrimmerEditor loại bỏ khoảng trắng ở đầu và cuối; tham số true yêu cầu chuỗi rỗng sau khi trim trở thành null.
- setAutoGrowCollectionLimit giới hạn số phần tử mà binder tự mở rộng khi bind các thuộc tính collection có chỉ số.

Tên form trong @InitBinder("form") phải khớp với tên model attribute được bind. Cần chọn giới hạn collection phù hợp với biểu mẫu thực tế.

Nếu dùng nhiều Controller hoặc nhiều form, có thể đặt @InitBinder trong @ControllerAdvice để áp dụng cấu hình chung có chủ đích. Tránh đăng ký quy tắc quá rộng làm thay đổi hành vi của các form không liên quan.

## 9. Bảo vệ khỏi mass assignment

Mass assignment xảy ra khi ứng dụng bind request vào một đối tượng có nhiều thuộc tính hơn những gì người dùng được phép thay đổi. Kẻ tấn công có thể gửi thêm trường mà giao diện không hiển thị để cố sửa dữ liệu nhạy cảm.

Ví dụ, entity có thể chứa:

~~~java
public class UserAccount {
    private String displayName;
    private String email;
    private String role;
    private boolean active;
    private UUID ownerId;

    // Getter và setter.
}
~~~

Nếu Controller bind trực tiếp request vào UserAccount, người dùng có thể gửi thêm role=ADMIN hoặc active=true dù biểu mẫu chỉ hiển thị tên và email.

Các biện pháp nên áp dụng:

1. Dùng request DTO hoặc form object chuyên biệt chỉ chứa trường được phép thay đổi.
2. Dùng allowlist với WebDataBinder khi property binding được sử dụng.
3. Không nhận role, ownerId, approvalStatus hoặc giá trị quyền hạn từ client nếu chúng phải do server quyết định.
4. Lấy danh tính người dùng từ ngữ cảnh xác thực đã được kiểm tra.
5. Kiểm tra quyền và quy tắc nghiệp vụ ở phía máy chủ.
6. Không coi hidden field là dữ liệu đáng tin cậy.

DTO chuyên biệt thường là biện pháp chính; allowlist là lớp kiểm soát bổ sung. Không nên dựa vào danh sách trường bị ẩn trên giao diện để bảo vệ dữ liệu.

## 10. Giá trị thiếu, rỗng, null và khoảng trắng

Những trạng thái này có thể mang ý nghĩa khác nhau và cần được thiết kế rõ.

| Đầu vào | Ý nghĩa có thể gặp | Điều cần quyết định |
|---|---|---|
| Không có parameter | Người dùng không gửi trường | Có bắt buộc hay có giá trị mặc định? |
| Chuỗi rỗng | Trường có gửi nhưng không nhập nội dung | Xem là null, chuỗi rỗng hay lỗi? |
| Chỉ có khoảng trắng | Người dùng nhập khoảng trắng | Có trim trước khi kiểm tra không? |
| null trong JSON | Client chủ động gửi null | Có cho phép xóa giá trị hiện tại không? |
| Thuộc tính không có trong JSON | Client không đề cập đến trường | Giữ nguyên, dùng mặc định hay báo thiếu? |

Đặc biệt với API cập nhật, không có trường và trường có giá trị null có thể mang ý nghĩa khác nhau:

- Không có trường có thể có nghĩa là giữ nguyên giá trị hiện tại.
- Có trường với null có thể có nghĩa là xóa giá trị nếu hợp đồng cho phép.
- Chuỗi rỗng có thể được xem là một giá trị không hợp lệ hoặc được chuẩn hóa thành null.

Không nên để hành vi này phụ thuộc vào tình cờ của converter. Hãy định nghĩa rõ hợp đồng request và kiểm thử các trường hợp.

### 10.1. Trim chuỗi

Nếu nghiệp vụ không phân biệt khoảng trắng đầu/cuối, có thể chuẩn hóa chuỗi trước khi validation. Tuy nhiên, không phải mọi trường đều nên trim. Mật khẩu, mã token hoặc dữ liệu mà khoảng trắng có ý nghĩa cần được xử lý theo quy tắc riêng.

### 10.2. Phân biệt số 0 với chưa nhập

Với trường số bắt buộc, dùng Integer hoặc BigDecimal để có thể biểu diễn null. Sau đó dùng @NotNull và @Min/@DecimalMin để phân biệt:

- Chưa nhập: null.
- Nhập 0: giá trị có thật nhưng có thể vi phạm giới hạn.
- Nhập số âm: giá trị chuyển đổi được nhưng vi phạm quy tắc.
- Nhập chuỗi chữ: lỗi conversion.

## 11. Ngày tháng, số và locale

Dữ liệu ngày và số có thể được trình bày khác nhau theo locale. Ví dụ, ngày có thể là 15/12/2026 hoặc 12/15/2026; dấu thập phân có thể là dấu phẩy hoặc dấu chấm.

Với HTML form, cần chọn định dạng mà trình duyệt và server thống nhất. Ví dụ dùng ISO date:

~~~java
public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate arrivalDate;

    // Getter và setter.
}
~~~

Đầu vào có dạng 2026-12-15 và được chuyển thành LocalDate. LocalDate phù hợp với ngày lịch không có thời gian hoặc múi giờ. Nếu biểu diễn một thời điểm tuyệt đối, cân nhắc Instant hoặc OffsetDateTime và xác định rõ quy tắc múi giờ.

Với số, @NumberFormat có thể được dùng cho form theo locale:

~~~java
public class PriceForm {
    @NumberFormat(style = NumberFormat.Style.NUMBER)
    private BigDecimal amount;

    // Getter và setter.
}
~~~

Cần lưu ý:

- Giá trị hiển thị cho người dùng có thể theo locale.
- Giá trị API nên dùng một định dạng ổn định, thường là số JSON hoặc chuỗi ISO theo hợp đồng.
- Không dùng double hoặc float cho phép tính tiền cần độ chính xác thập phân; cân nhắc BigDecimal.
- Không tự đoán locale từ dấu phẩy hoặc dấu chấm nếu hợp đồng chưa quy định.
- Kiểm thử với locale thực tế mà ứng dụng hỗ trợ.

## 12. Tạo Converter hoặc Formatter tùy chỉnh

Khi kiểu dữ liệu miền không có chuyển đổi sẵn, có thể đăng ký converter hoặc formatter.

### 12.1. Converter cho kiểu ProductCode

Giả sử mã sản phẩm được biểu diễn bằng kiểu riêng:

~~~java
public record ProductCode(String value) {
    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product code is required");
        }
    }
}
~~~

Converter chuyển từ chuỗi request sang kiểu ProductCode:

~~~java
public class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }

        return new ProductCode(source.trim());
    }
}
~~~

Đăng ký converter với Spring MVC:

~~~java
@Configuration
public class WebConversionConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
    }
}
~~~

Converter nên thực hiện chuyển đổi đơn giản, có tính xác định. Không nên gọi cơ sở dữ liệu hoặc thực hiện nghiệp vụ phức tạp bên trong converter. Ví dụ, chuyển SKU thành Product bằng cách truy vấn repository nên thuộc application service hoặc ca sử dụng, vì việc tra cứu có thể thất bại do nghiệp vụ hoặc hạ tầng.

### 12.2. Converter và Formatter khác nhau thế nào?

| Thành phần | Mục đích | Đặc điểm |
|---|---|---|
| Converter | Chuyển kiểu nguồn sang kiểu đích | Không nhận locale |
| Formatter | Parse chuỗi và in giá trị theo locale | Phù hợp dữ liệu người dùng nhập và hiển thị |
| PropertyEditor | Cơ chế chuyển đổi cũ, thường gắn với một kiểu hoặc thuộc tính | Có trạng thái, nên không dùng tùy tiện làm converter dùng chung |

Dùng Converter khi cách chuyển đổi không phụ thuộc ngôn ngữ. Dùng Formatter khi việc parse và hiển thị chịu ảnh hưởng locale, chẳng hạn ngày, số hoặc tiền tệ.

## 13. Lỗi chuyển đổi trong JSON API

Đối với JSON, quá trình đọc body khác với binding form.

Ví dụ client gửi:

~~~json
{
  "productCode": "BOOK-01",
  "quantity": "three"
}
~~~

Nếu thuộc tính quantity là Integer, Jackson không thể giải mã chuỗi "three" thành số nguyên theo cấu hình mặc định thông thường. Spring thường ném HttpMessageNotReadableException trước khi Controller nhận được đối tượng hoàn chỉnh.

Nếu JSON hợp lệ về cú pháp và chuyển đổi được, nhưng vi phạm Bean Validation, lỗi có thể được xử lý bằng MethodArgumentNotValidException hoặc BindingResult tùy cách khai báo tham số.

Ví dụ một exception handler:

~~~java
@RestControllerAdvice
public class ApiBindingExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> unreadableBody(
            HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest().body(
            new ApiError(
                "request.body.invalid",
                "Nội dung request không đúng định dạng hoặc kiểu dữ liệu."
            )
        );
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException exception) {
        return ResponseEntity.badRequest().body(
            new ApiError(
                "request.parameter.invalid",
                "Một tham số request có kiểu dữ liệu không hợp lệ."
            )
        );
    }
}
~~~

ApiError là DTO do ứng dụng định nghĩa:

~~~java
public record ApiError(String code, String message) {}
~~~

Trong ứng dụng thực tế, có thể bổ sung handler cho lỗi Bean Validation, binding exception và lỗi nghiệp vụ. Không trả nội dung exception thô cho client vì nó có thể chứa chi tiết nội bộ hoặc dữ liệu request.

### 13.1. Validation JSON sau khi giải mã

Khi JSON được giải mã thành DTO, Bean Validation kiểm tra các constraint:

~~~java
public record CreateOrderRequest(
    @NotBlank String productCode,
    @NotNull @Min(1) @Max(100) Integer quantity
) {}
~~~

Một request có quantity là số nguyên 0 đã giải mã thành công nhưng vi phạm @Min(1). Đây là validation error, khác với lỗi giải mã chuỗi "three".

Nếu handler method nhận @Valid @RequestBody và không khai báo BindingResult ngay sau tham số, Spring thường ném MethodArgumentNotValidException. Nếu khai báo Errors hoặc BindingResult ngay sau tham số, ứng dụng có thể xử lý lỗi validation trong handler method. Lỗi giải mã body vẫn xảy ra trước đó và cần được xử lý riêng.

## 14. Chuyển lỗi binding thành thông báo dễ hiểu

Thông báo lỗi cần phản ánh đúng loại vấn đề:

| Mã hoặc loại lỗi | Thông báo hướng đến người dùng |
|---|---|
| typeMismatch | Nhập giá trị theo đúng kiểu dữ liệu |
| NotNull | Vui lòng nhập trường này |
| Min / Max | Nhập giá trị trong khoảng được phép |
| DateTimeFormat | Nhập ngày theo định dạng được hướng dẫn |
| Mã sản phẩm không tồn tại | Kiểm tra lại mã sản phẩm |
| Không đủ tồn kho | Chọn số lượng nhỏ hơn |

Có thể định nghĩa message trong messages.properties để hỗ trợ đa ngôn ngữ:

~~~properties
typeMismatch.form.quantity=Vui lòng nhập số lượng bằng số nguyên.
typeMismatch.form.arrivalDate=Vui lòng nhập ngày theo định dạng năm-tháng-ngày.
NotNull.form.quantity=Vui lòng nhập số lượng.
Min.form.quantity=Số lượng phải lớn hơn 0.
Max.form.quantity=Số lượng không được vượt quá 100.
~~~

Tên message code chính xác phụ thuộc object name, field name và cấu hình MessageCodesResolver. Có thể kiểm tra codes trong FieldError khi cần xác định key phù hợp.

Không nên hiển thị nguyên văn lỗi kỹ thuật như "Failed to convert property value" hoặc tên lớp Java. Hãy ánh xạ sang thông báo mà người dùng hiểu được.

## 15. Kiểm thử binding và conversion

Kiểm thử cần bao phủ cả chuyển đổi thành công, chuyển đổi thất bại và validation sau chuyển đổi.

### 15.1. Kiểm thử Converter

~~~java
class StringToProductCodeConverterTest {
    private final StringToProductCodeConverter converter =
        new StringToProductCodeConverter();

    @Test
    void trimsProductCode() {
        ProductCode code = converter.convert("  BOOK-01  ");

        assertEquals("BOOK-01", code.value());
    }

    @Test
    void returnsNullForBlankInput() {
        assertNull(converter.convert("   "));
    }
}
~~~

Nếu converter được thiết kế để từ chối chuỗi rỗng thay vì trả null, test cần phản ánh đúng chính sách đó. Điều quan trọng là hành vi phải rõ ràng và nhất quán.

### 15.2. Kiểm thử lỗi chuyển đổi trong Controller

Với MockMvc, gửi một giá trị không thể chuyển sang Integer:

~~~java
mockMvc.perform(post("/bookings")
        .param("quantity", "three"))
    .andExpect(status().isOk())
    .andExpect(view().name("bookings/new"))
    .andExpect(model().attributeHasFieldErrors(
        "form", "quantity"
    ));
~~~

Test này xác nhận Controller trả lại form và có lỗi gắn với trường quantity. Cần thiết lập các dependency và dữ liệu phụ trợ cần thiết cho template trong test thực tế.

### 15.3. Kiểm thử validation sau conversion

~~~java
mockMvc.perform(post("/bookings")
        .param("quantity", "0"))
    .andExpect(status().isOk())
    .andExpect(view().name("bookings/new"))
    .andExpect(model().attributeHasFieldErrors(
        "form", "quantity"
    ));
~~~

Cả hai test đều có field error nhưng nguyên nhân khác nhau: "three" không chuyển được thành Integer, còn "0" chuyển được nhưng vi phạm @Min(1). Nếu cần xác nhận chính xác loại lỗi, có thể kiểm tra FieldError code hoặc bindingFailure trong BindingResult.

### 15.4. Kiểm thử JSON

Kiểm tra ít nhất ba trường hợp:

- JSON sai cú pháp hoặc sai kiểu: nhận phản hồi lỗi body phù hợp.
- JSON hợp lệ nhưng vi phạm constraint: nhận lỗi validation theo hợp đồng.
- JSON hợp lệ và thỏa constraint: ca sử dụng được gọi và trả kết quả đúng.

Không chỉ kiểm tra status code. Cần kiểm tra mã lỗi, trường liên quan và cấu trúc response để bảo đảm API client có thể xử lý ổn định.

## 16. Những lỗi thiết kế thường gặp

### Coi conversion là validation

Chuyển "3" thành Integer thành công không có nghĩa số lượng 3 được phép trong nghiệp vụ. Conversion chỉ xác định kiểu; validation và domain rule quyết định tính hợp lệ.

### Dùng primitive cho mọi trường

Primitive không biểu diễn được trạng thái chưa nhập. Với trường có thể thiếu, wrapper type thường giúp phân biệt null với giá trị mặc định.

### Bind trực tiếp vào entity

Điều này mở rộng bề mặt dữ liệu client có thể thay đổi và có thể dẫn đến mass assignment. Dùng form DTO riêng và allowlist.

### Viết logic truy vấn trong Converter

Converter nên chuyển đổi biểu diễn, không nên truy cập repository hoặc gọi dịch vụ bên ngoài. Đưa việc tra cứu và kiểm tra nghiệp vụ vào application layer.

### Chỉ kiểm tra ở trình duyệt

Request có thể được gửi trực tiếp mà không qua giao diện. Binding và validation phía server luôn cần thiết.

### Hiển thị lỗi kỹ thuật nguyên văn

Thông báo conversion nội bộ không giúp người dùng sửa dữ liệu và có thể làm lộ chi tiết hệ thống. Dùng message code để ánh xạ thông báo an toàn.

### Không phân biệt form binding với JSON deserialization

BindingResult của @ModelAttribute và lỗi HttpMessageConverter khi đọc @RequestBody đi qua những cơ chế khác nhau. Cần xử lý đúng loại exception và hợp đồng phản hồi.

### Không giới hạn binding collection

Các thuộc tính lồng nhau hoặc collection index có thể tạo cấu trúc dữ liệu rất lớn. Đặt giới hạn hợp lý, kiểm tra số lượng phần tử và tránh cho phép client bind những cấu trúc không cần thiết.

## 17. Quy trình thiết kế binding an toàn

Khi tạo form hoặc endpoint mới, hãy thực hiện theo trình tự:

1. **Xác định nguồn dữ liệu.** Query, path, form parameter, header, cookie hay JSON body.
2. **Định nghĩa kiểu đích.** Dùng wrapper type khi cần biểu diễn giá trị chưa nhập.
3. **Xác định quy tắc conversion.** Chọn kiểu chuẩn, Converter hoặc Formatter.
4. **Định nghĩa hợp đồng đầu vào.** Dùng DTO hoặc form object chuyên biệt.
5. **Giới hạn trường được bind.** Dùng allowlist và tránh bind trực tiếp entity.
6. **Phân loại lỗi.** Tách binding/conversion, Bean Validation và business rule.
7. **Thiết kế phản hồi.** Hiển thị lỗi theo trường cho HTML; trả mã lỗi ổn định cho API.
8. **Kiểm tra bảo mật.** Không tin hidden field, owner ID hoặc trạng thái do client gửi.
9. **Kiểm thử trường hợp biên.** Bao gồm thiếu, rỗng, khoảng trắng, null, sai kiểu, ngoài phạm vi và collection lớn.
10. **Rà soát locale và định dạng.** Dùng định dạng phù hợp với người dùng và hợp đồng API.

Trước khi hoàn thành, hãy tự hỏi:

- Dữ liệu đến từ nguồn nào và được bind vào kiểu nào?
- Chuỗi sai định dạng sẽ được báo lỗi ở đâu?
- Trường thiếu có khác trường rỗng hoặc null không?
- Conversion có đang làm thay công việc của validation hoặc nghiệp vụ không?
- Client có thể bind vào trường nhạy cảm không?
- Form và JSON có cơ chế xử lý lỗi khác nhau không?
- Người dùng có nhận được thông báo dễ hiểu mà không lộ chi tiết nội bộ không?

## 18. Kết luận

Data binding giúp Spring MVC ánh xạ dữ liệu từ request vào tham số hoặc đối tượng Java; conversion chuyển biểu diễn bên ngoài sang kiểu dữ liệu đích. Binding và conversion tạo nền tảng để Controller làm việc với dữ liệu có cấu trúc, nhưng không thay thế validation hay quy tắc nghiệp vụ.

Khi thiết kế đúng, form object và DTO giới hạn dữ liệu được nhận, WebDataBinder kiểm soát quá trình binding, Converter và Formatter xử lý kiểu dữ liệu, còn BindingResult hoặc exception handler giúp chuyển lỗi thành phản hồi phù hợp. Phân biệt rõ lỗi form với lỗi giải mã JSON, bảo vệ khỏi mass assignment và kiểm thử các trường hợp biên giúp luồng MVC an toàn, dễ hiểu và ổn định hơn.

