# Phân biệt chuyển đổi kiểu, định dạng và kiểm tra hợp lệ

Trong ứng dụng web MVC, dữ liệu đi qua nhiều ranh giới: từ URL, biểu mẫu hoặc JSON vào Controller; từ Controller đến tầng ứng dụng và Model; rồi từ kết quả xử lý ra View hoặc HTTP response. Ở mỗi ranh giới, ứng dụng có thể cần chuyển đổi kiểu, định dạng dữ liệu hoặc kiểm tra tính hợp lệ. Ba việc này liên quan với nhau nhưng giải quyết ba câu hỏi khác nhau:

- **Chuyển đổi kiểu:** giá trị đầu vào được biến thành kiểu dữ liệu mà chương trình có thể xử lý như thế nào?
- **Định dạng:** một giá trị đã có kiểu được biểu diễn như thế nào cho người đọc hoặc một hợp đồng trao đổi?
- **Kiểm tra hợp lệ:** giá trị có đáp ứng các điều kiện của hợp đồng và quy tắc nghiệp vụ hay không?

Nếu trộn lẫn ba trách nhiệm, ứng dụng dễ mắc lỗi như lưu tiền dưới dạng chuỗi đã định dạng theo locale, chấp nhận ngày không hợp lệ vì chỉ kiểm tra được mẫu ký tự, hoặc từ chối dữ liệu hợp lệ vì giao diện và API dùng cách biểu diễn khác nhau. Tách rõ chúng giúp Controller xử lý đầu vào nhất quán, Model bảo vệ quy tắc nghiệp vụ và View trình bày dữ liệu phù hợp với người dùng.

## 1. Ba khái niệm và câu hỏi riêng

Giả sử người dùng nhập số tiền 1.250.000,50 vào một biểu mẫu tiếng Việt.

| Công việc | Câu hỏi | Ví dụ |
|---|---|---|
| Chuyển đổi kiểu (conversion/parsing) | Chuỗi biểu diễn giá trị nào? | Chuyển chuỗi theo quy ước đã chọn thành BigDecimal |
| Định dạng (formatting) | Giá trị có kiểu được hiển thị ra sao? | Hiển thị BigDecimal thành 1.250.000,50 ₫ |
| Kiểm tra hợp lệ (validation) | Giá trị có được phép trong ngữ cảnh này không? | Số tiền phải lớn hơn 0 và không vượt hạn mức |

Chuyển đổi thành công không có nghĩa là dữ liệu hợp lệ. Chuỗi -25 có thể chuyển thành số nguyên -25, nhưng số lượng sản phẩm âm thường không được chấp nhận. Tương tự, chuỗi 2026-02-31 có thể trông giống ngày ISO nhưng không phải ngày lịch hợp lệ.

Định dạng cũng không phải là chuyển đổi nghiệp vụ. Một giá trị tiền có thể được hiển thị với dấu phân cách hàng nghìn, ký hiệu tiền tệ hoặc số chữ số thập phân khác nhau tùy locale; giá trị lưu trong Model vẫn là số có kiểu và không chứa ký hiệu trình bày.

## 2. Chuyển đổi kiểu: từ biểu diễn bên ngoài sang kiểu dữ liệu

HTTP truyền dữ liệu dưới dạng byte, văn bản, header hoặc cấu trúc JSON/XML. Ứng dụng cần chuyển biểu diễn đó thành kiểu phù hợp trước khi xử lý.

Ví dụ:

- Path variable "42" thành long.
- Query parameter "true" thành boolean.
- Form field "2026-11-19" thành LocalDate.
- Giá trị JSON thành BigDecimal.
- Mã trạng thái "PAID" thành enum PaymentStatus.

Chuyển đổi cần một hợp đồng biểu diễn rõ ràng. Nếu API quy định ngày theo ISO yyyy-MM-dd, client phải gửi đúng dạng đó. Không nên đoán ngày theo nhiều quy ước như 03/04/2026, vì nó có thể được hiểu là ngày 3 tháng 4 hoặc ngày 4 tháng 3.

Khi chuyển đổi thất bại, ứng dụng cần báo lỗi đầu vào có thể hiểu được. Không nên tự động thay chuỗi sai bằng 0, ngày hiện tại hoặc một giá trị mặc định có thể làm thay đổi ý nghĩa thao tác.

### 2.1. Chọn kiểu dữ liệu phù hợp

| Ý nghĩa | Kiểu Java thường phù hợp | Lưu ý |
|---|---|---|
| Số lượng nguyên | int, long hoặc kiểu số nguyên phù hợp | Kiểm tra giới hạn và giá trị âm |
| Tiền tệ, số thập phân chính xác | BigDecimal | Tránh dùng float/double cho phép tính tiền |
| Ngày không có giờ | LocalDate | Không gắn múi giờ |
| Thời điểm tuyệt đối | Instant | Đại diện thời điểm trên trục thời gian |
| Ngày giờ địa phương có ngữ cảnh múi giờ | ZonedDateTime hoặc OffsetDateTime | Giữ thông tin vùng hoặc độ lệch múi giờ |
| Giá trị thuộc tập hữu hạn | enum | Chỉ nhận các giá trị được công bố |
| Mã định danh | UUID, long hoặc kiểu định danh chuyên biệt | Không đồng nhất ID với quyền truy cập |

Chọn kiểu theo ý nghĩa dữ liệu giúp tránh việc phải suy luận ngữ nghĩa từ chuỗi ở nhiều tầng. Ví dụ, ngày sinh thường là LocalDate, còn thời điểm một giao dịch được ghi nhận thường là Instant.

## 3. Chuyển đổi trong Spring MVC

Spring MVC dùng các cơ chế khác nhau tùy nguồn dữ liệu.

### 3.1. Path variable, query parameter và form

Với dữ liệu được bind từ URL hoặc form qua @PathVariable, @RequestParam và @ModelAttribute, Spring MVC dùng hệ thống chuyển đổi kiểu dựa trên ConversionService và WebDataBinder.

~~~java
@GetMapping("/orders/{id}")
public String detail(@PathVariable long id, Model model) {
    // Spring chuyển đoạn URL thành long trước khi gọi handler.
    model.addAttribute("order", orderService.findOrder(id));
    return "orders/detail";
}
~~~

Nếu URL chứa /orders/abc, Spring không thể chuyển abc thành long. Handler không được gọi theo cách thông thường; Spring phát sinh lỗi chuyển đổi/binding và có thể ánh xạ lỗi đó thành phản hồi 400 hoặc trang lỗi theo cấu hình.

### 3.2. JSON request body

Với @RequestBody, Spring MVC thường dùng HttpMessageConverter; JSON được giải mã bởi thư viện như Jackson thành DTO đích. Đây là đường chuyển đổi khác với binding form/query qua ConversionService.

~~~java
public record CreatePaymentRequest(
        BigDecimal amount,
        LocalDate paymentDate,
        PaymentMethod method
) {
}

@PostMapping("/payments")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreatePaymentRequest request
) {
    paymentService.create(request);
    return ResponseEntity.accepted().build();
}
~~~

Jackson cần được cấu hình phù hợp để giải mã LocalDate, enum và các kiểu dữ liệu khác. JSON sai cú pháp, chuỗi ngày không thể giải mã hoặc giá trị không tương thích với kiểu trường có thể gây lỗi đọc request trước khi phương thức Controller được gọi. Bean Validation chỉ kiểm tra đối tượng sau khi quá trình giải mã và binding tạo được đối tượng đó.

Không nên mặc định rằng @DateTimeFormat điều khiển cách Jackson đọc ngày trong JSON. @DateTimeFormat chủ yếu phục vụ hệ thống formatting/conversion của Spring MVC cho các giá trị như query parameter và form; JSON body thường do Jackson và cấu hình ObjectMapper xử lý. Với API, hãy công bố rõ định dạng JSON và cấu hình serializer/deserializer tương ứng.

## 4. Converter và Formatter trong Spring

Spring cung cấp hai abstraction thường dùng để chuyển đổi dữ liệu văn bản.

### 4.1. Converter

Converter<S, T> chuyển một kiểu nguồn thành kiểu đích. Nó phù hợp với chuyển đổi có quy tắc rõ ràng, không phụ thuộc locale.

~~~java
import org.springframework.core.convert.converter.Converter;
import java.util.Locale;

public final class StringToPaymentStatusConverter
        implements Converter<String, PaymentStatus> {

    @Override
    public PaymentStatus convert(String source) {
        return PaymentStatus.valueOf(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Converter này chuyển mã trạng thái văn bản thành enum. Trong ứng dụng thực tế, nếu giá trị không nằm trong tập enum, cần để lỗi chuyển đổi được ánh xạ thành lỗi đầu vào rõ ràng. Không nên tự chuyển giá trị không biết thành một trạng thái hợp lệ tùy tiện.

### 4.2. Formatter

Formatter<T> có hai chiều: parse(String, Locale) để đọc văn bản thành kiểu T và print(T, Locale) để biểu diễn T thành văn bản. Nó phù hợp với dữ liệu người dùng nhập hoặc xem có quy ước phụ thuộc locale.

~~~java
import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class LocalDateFormatter implements Formatter<LocalDate> {
    private final DateTimeFormatter formatter =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException ex) {
            ParseException error =
                    new ParseException("Ngày phải theo dạng yyyy-MM-dd", 0);
            error.initCause(ex);
            throw error;
        }
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return formatter.format(object);
    }
}
~~~

Formatter trên dùng ISO cố định nên locale không làm thay đổi cấu trúc ngày. Nếu giao diện cần hiển thị ngày theo locale, có thể dùng formatter theo locale ở tầng trình bày. Điều quan trọng là hợp đồng nhập liệu và cách hiển thị phải được xác định rõ, không thay đổi ngầm theo cấu hình máy chủ.

### 4.3. Formatter số phụ thuộc locale

Với một biểu mẫu dành cho người dùng, có thể cần đọc số theo locale. Ví dụ, dấu phẩy có thể là dấu thập phân trong quy ước Việt Nam, trong khi dấu chấm là dấu thập phân trong quy ước Hoa Kỳ. Formatter dưới đây tạo DecimalFormat riêng cho mỗi lần parse/print để không chia sẻ đối tượng định dạng vốn không an toàn khi dùng đồng thời.

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class LocalizedDecimalFormatter implements Formatter<BigDecimal> {
    private DecimalFormat createFormat(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.############################",
                DecimalFormatSymbols.getInstance(locale)
        );
        format.setParseBigDecimal(true);
        format.setMaximumFractionDigits(340);
        return format;
    }

    @Override
    public BigDecimal parse(String text, Locale locale)
            throws ParseException {
        DecimalFormat format = createFormat(locale);
        ParsePosition position = new ParsePosition(0);
        Object parsed = format.parse(text, position);

        if (!(parsed instanceof BigDecimal value)
                || position.getIndex() != text.length()) {
            int errorIndex = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();
            throw new ParseException("Số không đúng định dạng", errorIndex);
        }
        return value;
    }

    @Override
    public String print(BigDecimal object, Locale locale) {
        return createFormat(locale).format(object);
    }
}
~~~

Formatter này minh họa việc parse và print theo cùng locale. DecimalFormat có thể chấp nhận một số cách đặt dấu phân nhóm lỏng hơn quy tắc nhập liệu mà sản phẩm mong muốn; nếu hợp đồng yêu cầu grouping nghiêm ngặt, cần kiểm tra grammar đầu vào riêng. Trong ứng dụng thật, cũng cần quy định rõ có chấp nhận khoảng trắng, ký hiệu tiền tệ, dấu âm và số chữ số thập phân nào hay không. Với trường tiền, nên tách mã tiền tệ khỏi giá trị số; không tự suy ra currency từ locale.

### 4.4. Đăng ký Formatter trong Spring MVC

Có thể đăng ký formatter thông qua WebMvcConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebFormattingConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new LocalDateFormatter());
        registry.addFormatter(new LocalizedDecimalFormatter());
    }
}
~~~

Sau khi đăng ký, Spring MVC có thể dùng formatter này khi bind chuỗi ngày từ các nguồn được hỗ trợ bởi ConversionService, chẳng hạn form hoặc query parameter. Cấu hình này không tự thay đổi cách Jackson giải mã JSON request body.

## 5. Định dạng: biểu diễn giá trị cho người đọc

Định dạng quyết định cách một giá trị đã có kiểu được trình bày. Một giá trị BigDecimal có thể được hiển thị khác nhau tùy locale:

| Giá trị nội bộ | Locale/kiểu trình bày | Ví dụ hiển thị |
|---|---|---|
| 1234567.50 | Việt Nam, định dạng số | 1.234.567,50 |
| 1234567.50 | Hoa Kỳ, định dạng số | 1,234,567.50 |
| 2026-11-19 | ISO | 2026-11-19 |
| 2026-11-19 | Ngày theo locale Việt Nam | 19/11/2026 |

Giá trị nội bộ không thay đổi khi đổi cách hiển thị. Nếu ứng dụng lấy chuỗi 1.234.567,50 ₫ đã định dạng rồi lưu vào cột tiền, việc tính toán và truy vấn sẽ khó khăn, dễ lỗi theo locale.

### 5.1. Định dạng số và tiền

Java cung cấp NumberFormat để định dạng số theo locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal amount = new BigDecimal("1234567.50");

NumberFormat vietnamese =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
vietnamese.setMinimumFractionDigits(2);
vietnamese.setMaximumFractionDigits(2);

String display = vietnamese.format(amount);
// Ví dụ: 1.234.567,50
~~~

Nếu cần ký hiệu tiền tệ, có thể dùng NumberFormat.getCurrencyInstance(locale) và thiết lập Currency phù hợp. Không suy luận loại tiền chỉ từ locale: người dùng ở Việt Nam vẫn có thể giao dịch bằng USD hoặc EUR. Mã tiền tệ cần đến từ dữ liệu nghiệp vụ hoặc hợp đồng giao dịch.

### 5.2. Định dạng ngày và thời gian

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate dueDate = LocalDate.of(2026, 11, 19);

DateTimeFormatter displayFormatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"));

String displayDate = displayFormatter.format(dueDate);
~~~

Định dạng hiển thị có thể thay đổi theo ngôn ngữ và quy ước của người dùng. Với thời điểm như Instant, cần chọn múi giờ trước khi hiển thị; cùng một thời điểm có thể tương ứng với ngày và giờ khác nhau ở các vùng. Không nên âm thầm chuyển LocalDate thành thời điểm UTC vì ngày lịch không có thông tin múi giờ.

### 5.3. Không dùng chuỗi trình bày làm dữ liệu nghiệp vụ

Các ví dụ sau thường là dấu hiệu trộn lẫn định dạng và dữ liệu:

- Lưu số tiền "1.250.000 ₫" thay vì số tiền và mã tiền tệ.
- So sánh ngày bằng chuỗi "19/11/2026" thay vì LocalDate.
- Sắp xếp số lượng theo thứ tự từ điển của chuỗi thay vì theo giá trị số.
- Dùng văn bản hiển thị "Đã thanh toán" làm mã trạng thái lưu trữ.

Hãy giữ dữ liệu dưới dạng kiểu có ý nghĩa và chỉ định dạng khi tạo View, email, báo cáo hoặc response theo hợp đồng.

## 6. Kiểm tra hợp lệ: giá trị có được chấp nhận không?

Validation kiểm tra dữ liệu sau khi đã được đọc và chuyển thành kiểu phù hợp, hoặc kiểm tra chuỗi trước chuyển đổi khi hợp đồng yêu cầu. Có nhiều lớp điều kiện:

1. **Cấu trúc và sự hiện diện:** trường bắt buộc có mặt, chuỗi không rỗng, kiểu dữ liệu đúng.
2. **Giới hạn đơn trường:** độ dài, khoảng số, định dạng, tập giá trị cho phép.
3. **Quan hệ giữa các trường:** ngày kết thúc không trước ngày bắt đầu, mật khẩu xác nhận phải khớp.
4. **Quy tắc nghiệp vụ:** số lượng đặt không vượt tồn kho, tài khoản có quyền thực hiện giao dịch, trạng thái hiện tại cho phép thao tác.

Bean Validation phù hợp với các điều kiện trên DTO hoặc command. Những quy tắc phụ thuộc dữ liệu hiện tại, quyền, giao dịch hoặc trạng thái miền cần được kiểm tra ở application service và Model. Kiểm tra ở Controller không thay thế việc bảo vệ bất biến trong tầng nghiệp vụ.

### 6.1. Validation bằng Bean Validation

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;
import java.math.BigDecimal;
import java.time.LocalDate;

public record PaymentRequest(
        @NotNull
        @DecimalMin(value = "0.01")
        BigDecimal amount,

        @NotNull
        @PastOrPresent
        LocalDate paymentDate
) {
}
~~~

DTO này yêu cầu số tiền tối thiểu 0,01 và ngày thanh toán không ở tương lai. Những annotation này chỉ chạy khi ứng dụng kích hoạt Bean Validation, chẳng hạn bằng @Valid hoặc @Validated ở điểm phù hợp.

### 6.2. Kiểm tra quan hệ giữa nhiều trường

Giả sử một biểu mẫu tạo chương trình khuyến mãi có ngày bắt đầu và kết thúc. Mỗi ngày riêng lẻ có thể hợp lệ, nhưng cặp ngày không hợp lệ nếu kết thúc trước bắt đầu.

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record PromotionRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {
    @AssertTrue(message = "Ngày kết thúc phải từ ngày bắt đầu trở đi")
    public boolean isDateRangeValid() {
        return startDate == null
                || endDate == null
                || !endDate.isBefore(startDate);
    }
}
~~~

Đây là minh họa cho validation liên trường. Với mô hình lớn hơn, có thể tạo class-level constraint riêng để tách logic kiểm tra khỏi DTO. Phương thức kiểm tra nên xử lý trường hợp null một cách có chủ đích; các annotation @NotNull vẫn chịu trách nhiệm báo trường bắt buộc.

### 6.3. Validation nghiệp vụ ở tầng ứng dụng và Model

Giả sử request đặt mua có quantity = 3. Giá trị này có thể thỏa @Min(1), nhưng kho chỉ còn một sản phẩm. Tầng nghiệp vụ phải kiểm tra tồn kho ngay tại thời điểm xử lý và từ chối nếu không đủ. Không nên chỉ kiểm tra tồn kho lúc render form vì số lượng có thể thay đổi trước khi người dùng gửi request.

Một quy tắc cần luôn đúng phải được bảo vệ tại nơi có quyền thay đổi trạng thái. Với thao tác đồng thời, việc kiểm tra và cập nhật tồn kho cần được bảo vệ bằng transaction, khóa hoặc cơ chế cập nhật có điều kiện phù hợp.

## 7. Trình tự xử lý dữ liệu trong một request MVC

Một luồng điển hình cho form hoặc API có thể mô tả như sau:

~~~mermaid
flowchart TD
    A[HTTP input: text / JSON] --> B[Đọc và chuyển đổi kiểu]
    B --> C{Chuyển đổi thành công?}
    C -->|Không| D[Lỗi binding hoặc parse]
    C -->|Có| E[DTO có kiểu]
    E --> F[Validation cấu trúc và giới hạn]
    F --> G{Hợp lệ?}
    G -->|Không| H[Trả lỗi đầu vào]
    G -->|Có| I[Application Service / Use case]
    I --> J[Kiểm tra quy tắc nghiệp vụ]
    J --> K{Được phép?}
    K -->|Không| L[Lỗi nghiệp vụ]
    K -->|Có| M[Cập nhật Model / lưu trữ]
    M --> N[Projection hoặc response DTO]
    N --> O[Định dạng và render / serialize]
~~~

Định dạng hiển thị thường nằm ở bước tạo View hoặc response, sau khi dữ liệu nghiệp vụ đã được xử lý. Với API machine-to-machine, response serialization tuân theo hợp đồng JSON/XML, không nhất thiết dùng định dạng thân thiện với người đọc như giao diện.

## 8. Ví dụ đầy đủ: form tìm kiếm sản phẩm

Giả sử người dùng nhập từ khóa, ngày tạo tối thiểu và số trang. Ta tạo DTO dành cho form:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.format.annotation.DateTimeFormat;
import java.time.LocalDate;

public class ProductSearchForm {
    @NotBlank
    private String keyword;

    @Min(0)
    private int page = 0;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdAfter;

    // Getter và setter được lược bỏ.
}
~~~

Controller nhận form:

~~~java
@GetMapping("/products")
public String search(
        @Valid @ModelAttribute("search") ProductSearchForm form,
        BindingResult errors,
        Model model
) {
    if (errors.hasErrors()) {
        return "products/search";
    }

    ProductSearchCriteria criteria = new ProductSearchCriteria(
            form.getKeyword().trim(),
            form.getPage(),
            form.getCreatedAfter()
    );

    model.addAttribute("results", productService.search(criteria));
    return "products/list";
}
~~~

Trong luồng này:

- Spring chuyển query/form value thành kiểu int và LocalDate.
- @DateTimeFormat xác định cách parse ngày cho binding của Spring MVC.
- Bean Validation kiểm tra từ khóa không rỗng và trang không âm.
- Controller chuẩn hóa khoảng trắng ở biên và tạo criteria có kiểu.
- Service áp dụng quy tắc tìm kiếm, phân quyền và giới hạn kích thước trang.
- View định dạng ngày và số theo locale khi hiển thị.

Nếu createdAfter=2026-02-31, chuyển đổi ngày thất bại trước khi Bean Validation chạy. Nếu page=-1, chuyển đổi số thành công nhưng @Min(0) không đạt. Nếu page là 0 và từ khóa hợp lệ nhưng người dùng không có quyền xem một nhóm sản phẩm, service phải áp dụng chính sách quyền truy cập.

## 9. Lỗi chuyển đổi và lỗi validation nên được phản hồi khác nhau

Hai loại lỗi này có nguyên nhân khác nhau:

| Tình huống | Ví dụ | Cách phản hồi |
|---|---|---|
| Lỗi parse/binding | page=abc không chuyển thành số | Báo trường có định dạng hoặc kiểu không hợp lệ |
| Lỗi validation | page=-1 chuyển được thành số nhưng nhỏ hơn 0 | Báo điều kiện giá trị không được đáp ứng |
| Lỗi nghiệp vụ | Số lượng đặt vượt tồn kho | Báo thao tác không thể thực hiện trong trạng thái hiện tại |
| Lỗi quyền | Người dùng không có quyền xem tài nguyên | Trả phản hồi 403 hoặc 404 theo chính sách |

Với form HTML, có thể đưa lỗi binding và validation vào BindingResult để render lại trang. Với JSON API, lỗi đọc body có thể phát sinh HttpMessageNotReadableException; lỗi Bean Validation thường được Spring ánh xạ qua exception tương ứng như MethodArgumentNotValidException cho @RequestBody. Ứng dụng có thể dùng @ControllerAdvice để tạo cấu trúc lỗi nhất quán.

Phản hồi nên chỉ rõ trường nào sai, mã lỗi ổn định và thông điệp an toàn. Không đưa stack trace, dữ liệu nhạy cảm hoặc chi tiết nội bộ của parser vào response công khai.

## 10. Locale, múi giờ và hợp đồng dữ liệu

Locale ảnh hưởng đến cách người dùng đọc và nhập số, ngày, tiền tệ; múi giờ ảnh hưởng cách biểu diễn thời điểm. Đây là những yếu tố cần được công bố rõ trong hợp đồng.

### 10.1. Locale không nên làm thay đổi API một cách ngầm định

Một biểu mẫu dành cho người dùng có thể chấp nhận số thập phân theo locale đã chọn. Tuy nhiên, API công khai thường nên dùng biểu diễn ổn định, chẳng hạn JSON number theo quy tắc JSON hoặc chuỗi ISO cho ngày. Nếu cùng endpoint diễn giải "1,234" khác nhau tùy header Accept-Language, client khó dự đoán kết quả.

Nếu API cần nhận giá trị theo locale, hãy đưa locale vào hợp đồng một cách tường minh và xác định cách xử lý khi locale thiếu hoặc không được hỗ trợ.

### 10.2. Thời điểm và múi giờ

- LocalDate phù hợp với ngày lịch như ngày sinh hoặc ngày hiệu lực không gắn giờ.
- Instant phù hợp với thời điểm cần so sánh nhất quán trên toàn hệ thống.
- OffsetDateTime giữ độ lệch UTC đã gửi.
- ZonedDateTime có thể giữ vùng múi giờ như Asia/Ho_Chi_Minh.

Không nên dùng một chuỗi ngày giờ không có múi giờ cho sự kiện toàn cầu rồi mặc định hiểu nó theo múi giờ của máy chủ. Hãy xác định rõ múi giờ của đầu vào và chuyển đổi có chủ đích.

### 10.3. Tiền tệ và độ chính xác

Tiền cần có giá trị số chính xác và mã tiền tệ. BigDecimal phù hợp hơn double cho phép tính tiền, nhưng vẫn cần quy định scale, cách làm tròn và đơn vị tiền tệ. Không suy ra tiền tệ chỉ từ dấu ₫ trong chuỗi hiển thị.

Với JSON, cần quy định rõ trường tiền là number hay string. Nếu chọn string để tránh mất chính xác ở một số client, hãy mô tả định dạng thập phân được phép và parse thành BigDecimal ở máy chủ. Nếu chọn JSON number, các client vẫn cần xử lý độ chính xác phù hợp với hợp đồng.

## 11. Chuẩn hóa dữ liệu không thay thế validation

Chuẩn hóa là biến các biểu diễn tương đương thành một dạng nhất quán, chẳng hạn bỏ khoảng trắng đầu/cuối trong mã tìm kiếm hoặc chuẩn hóa chữ hoa/thường cho mã không phân biệt hoa thường. Nó không đồng nghĩa với việc tự sửa mọi dữ liệu sai.

Ví dụ:

- "  java  " có thể được trim thành "java" theo quy tắc tìm kiếm.
- Mã enum có thể được chấp nhận không phân biệt hoa thường nếu hợp đồng cho phép.
- Một email có thể được kiểm tra cú pháp và chuẩn hóa phần domain theo quy tắc phù hợp.
- Số tiền "1,2,3" không nên được sửa bằng cách tự xóa dấu phẩy để cố tạo ra một số.

Hãy xác định bước chuẩn hóa ở ranh giới phù hợp và kiểm thử nó. Không chuẩn hóa dữ liệu theo cách làm thay đổi ý nghĩa, ví dụ tự đổi ngày không hợp lệ sang ngày kế tiếp hoặc làm tròn tiền trước khi kiểm tra quy tắc.

## 12. Bảo mật khi chuyển đổi và xác thực dữ liệu

Chuyển đổi thành công không chứng minh dữ liệu an toàn. Validation cũng không thay thế mã hóa đầu ra hoặc kiểm soát quyền.

- **Allowlist trường đầu vào:** dùng request DTO thay vì bind trực tiếp vào entity có trường nội bộ như role, ownerId, approved hoặc price.
- **Giới hạn tài nguyên:** giới hạn kích thước request, độ dài chuỗi, số phần tử trong collection, số trang và độ sâu cấu trúc JSON.
- **Không tin giá trị có thẩm quyền từ client:** lấy giá, chủ sở hữu, vai trò và trạng thái thanh toán từ nguồn phía máy chủ.
- **Kiểm tra quyền và bất biến ở tầng nghiệp vụ:** không chỉ dựa vào annotation trên DTO hoặc việc ẩn nút trong View.
- **Mã hóa theo ngữ cảnh đầu ra:** dữ liệu văn bản hợp lệ vẫn có thể chứa nội dung gây XSS nếu được chèn vào HTML/JavaScript mà không escape đúng ngữ cảnh.
- **Không log dữ liệu nhạy cảm:** lỗi parse không phải lý do để ghi toàn bộ body có mật khẩu, token hoặc thông tin cá nhân vào log.

Đặc biệt, không dùng định dạng hiển thị làm bộ lọc bảo mật. Một chuỗi đã được format đẹp vẫn có thể chứa nội dung không an toàn khi render ở một ngữ cảnh khác.

## 13. Kiểm thử conversion, formatting và validation

Nên kiểm thử ba trách nhiệm riêng, sau đó kiểm thử tích hợp qua Controller.

### Kiểm thử chuyển đổi

- Chuỗi đúng định dạng được chuyển thành kiểu mong đợi.
- Chuỗi sai định dạng tạo lỗi binding/parse rõ ràng.
- Giá trị biên như số rất lớn, số âm hoặc ngày nhuận được xử lý đúng.
- Enum chỉ chấp nhận các mã được công bố.
- Locale và múi giờ được áp dụng đúng theo hợp đồng.

### Kiểm thử định dạng

- Giá trị số hiển thị đúng dấu phân cách và số chữ số thập phân theo locale.
- Ngày và thời gian hiển thị đúng định dạng, múi giờ.
- Format không làm thay đổi giá trị Model.
- Không dùng chuỗi đã format cho phép tính hoặc so sánh nghiệp vụ.

### Kiểm thử validation

- Trường bắt buộc, giới hạn số và độ dài chuỗi được kiểm tra.
- Quy tắc liên trường hoạt động với cả trường null và giá trị hợp lệ.
- Quy tắc nghiệp vụ được kiểm tra lại khi trạng thái dữ liệu thay đổi.
- Lỗi được ánh xạ thành response phù hợp và không làm lộ thông tin nội bộ.

### Kiểm thử tích hợp MVC

- Query parameter và form được bind qua ConversionService/Formatter đúng như mong đợi.
- JSON được giải mã qua HttpMessageConverter theo hợp đồng đã công bố.
- @Valid kích hoạt Bean Validation sau khi đối tượng được tạo thành công.
- Lỗi parse và lỗi validation có mã lỗi hoặc cấu trúc phản hồi nhất quán.
- Service không được gọi khi dữ liệu đầu vào không qua kiểm tra cấu trúc cần thiết.

Với Spring MVC, MockMvc có thể kiểm tra binding, validation, status và response. Converter/Formatter có thể được kiểm thử độc lập bằng unit test để cô lập lỗi quy tắc parse hoặc print.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu số tiền đã định dạng thành chuỗi | Khó tính toán, sắp xếp và truy vấn | Lưu kiểu số chính xác và mã tiền tệ |
| Dùng double cho tiền | Sai số nhị phân trong phép tính | Dùng BigDecimal và quy tắc scale/làm tròn |
| Coi parse thành công là dữ liệu hợp lệ | Giá trị âm hoặc ngoài giới hạn vẫn lọt qua | Thực hiện validation riêng |
| Dùng regex để thay thế parse ngày | Có thể nhận ngày không tồn tại | Parse bằng kiểu ngày thực như LocalDate |
| Dùng định dạng hiển thị làm định dạng API | Client phụ thuộc locale và cấu hình giao diện | Công bố biểu diễn API ổn định |
| Mong @DateTimeFormat xử lý JSON body | JSON vẫn có thể lỗi giải mã | Cấu hình Jackson cho request body |
| Đặt mọi quy tắc vào DTO | Bỏ qua được quy tắc khi gọi use case từ kênh khác | Bảo vệ bất biến trong service/Model |
| Tự sửa đầu vào sai thành giá trị mặc định | Thay đổi ý định người dùng mà không báo | Trả lỗi rõ ràng hoặc chuẩn hóa theo hợp đồng |
| Bind request trực tiếp vào entity | Mass assignment và thay đổi trường không được phép | Dùng DTO allowlist |

## 15. Checklist thiết kế hợp đồng dữ liệu

Trước khi hoàn thành một endpoint hoặc biểu mẫu, hãy xác nhận:

- Mỗi trường có kiểu dữ liệu phản ánh đúng ý nghĩa không?
- Biểu diễn đầu vào có được công bố rõ và ổn định không?
- Conversion có xử lý lỗi parse mà không tự thay bằng giá trị nguy hiểm không?
- JSON body và form/query đang dùng đúng cơ chế giải mã/binding không?
- Formatter có phụ thuộc locale đúng nơi cần thiết không?
- Dữ liệu nghiệp vụ có được giữ dưới dạng kiểu có ý nghĩa thay vì chuỗi trình bày không?
- Validation cấu trúc, giới hạn, liên trường và nghiệp vụ có được phân lớp rõ không?
- Quy tắc quan trọng có được bảo vệ trong tầng nghiệp vụ khi có nhiều kênh gọi không?
- Response lỗi có chỉ rõ trường sai mà không tiết lộ nội bộ không?
- Kiểm thử có tách conversion, formatting, validation và tích hợp MVC không?

Chuyển đổi kiểu, định dạng và kiểm tra hợp lệ là ba trách nhiệm bổ sung cho nhau trong hợp đồng dữ liệu MVC. Chuyển đổi đưa dữ liệu bên ngoài vào kiểu mà ứng dụng hiểu; validation quyết định dữ liệu có được chấp nhận; định dạng trình bày giá trị theo ngữ cảnh người đọc hoặc giao thức. Khi tách rõ ba bước, ứng dụng giữ được dữ liệu nghiệp vụ chính xác, phản hồi lỗi dễ hiểu và giao diện linh hoạt theo locale mà không làm thay đổi ý nghĩa dữ liệu.
