# Không có converter phù hợp hoặc converter không được đăng ký trong Spring Framework

## 1. Mục tiêu chẩn đoán

Trong Spring Framework, nhiều dữ liệu ở ranh giới ứng dụng bắt đầu dưới dạng **chuỗi**: path variable, query parameter, form field hoặc một giá trị cấu hình. Để truyền chúng vào Java object, framework phải biết cách chuyển từ **kiểu nguồn** sang **kiểu đích**.

Ví dụ API nhận:

```text
GET /tickets/TKT-42
```

Trong controller:

```java
@GetMapping("/tickets/{key}")
public String detail(@PathVariable TicketKey key) {
    return "Ticket " + key.value();
}
```

Đây là đoạn mã minh họa. `TicketKey` là một value object của ứng dụng, không phải kiểu dữ liệu có sẵn trong Spring. Để ánh xạ từ chuỗi `"TKT-42"` vào `TicketKey(42)`, Spring cần một phép chuyển đổi có thể áp dụng trong **ConversionService mà luồng xử lý này thực sự sử dụng**.

Nếu phép chuyển đổi chưa tồn tại hoặc chưa được đăng ký đúng chỗ, việc binding có thể thất bại. Nếu đã có converter nhưng giá trị gửi tới sai định dạng, lỗi vẫn xảy ra — nhưng đó là **một nguyên nhân khác**.

Bài này phân biệt và chẩn đoán chính xác:

1. **Không tồn tại đường chuyển đổi** cho cặp kiểu nguồn/đích — có thể gặp `ConverterNotFoundException`.
2. **Có converter nhưng nội dung không hợp lệ** — có thể gặp `ConversionFailedException`.
3. **Lỗi conversion được DataBinder thu thập thành FieldError** — thường là `typeMismatch`.
4. **Converter đã được viết nhưng chưa đăng ký hoặc đăng ký sai ConversionService**.
5. **Converter được đăng ký nhưng sai generic source/target, sai scope, hoặc bị che bởi luồng Jackson/Formatter/PropertyEditor khác**.

Bạn sẽ có ví dụ **Java 17 + Spring Framework 6.2 + Maven + JUnit 5** chạy độc lập, sau đó là cách tích hợp converter đúng vào Spring MVC và một checklist chẩn đoán theo triệu chứng.

## 2. Các thành phần cốt lõi

Spring Core định nghĩa một hệ thống type conversion riêng với interface `ConversionService`. Đối với chuyển đổi một chiều đơn giản, lập trình viên thường hiện thực `Converter<S,T>`.

| API / class | Vai trò |
| --- | --- |
| `ConversionService` | Truy vấn `canConvert(...)` và thực thi `convert(...)` |
| `Converter<S,T>` | Hợp đồng chuyển một đối tượng kiểu S thành kiểu T |
| `ConverterRegistry` | Đăng ký converter hoặc converter factory |
| `GenericConversionService` | ConversionService mở rộng có khả năng quản lý registry |
| `DefaultConversionService` | Có sẵn converters thông dụng, như String ↔ số, enum, collection |
| `FormattingConversionService` | Bổ sung `Formatter`, parser/printer và hỗ trợ formatting |
| `Formatter<T>` | Chuyển text ↔ giá trị có thể phụ thuộc `Locale` |
| `ConverterFactory<S,R>` | Tạo converter cho một họ kiểu đích |
| `GenericConverter` | Xử lý các cặp kiểu rộng hơn với `TypeDescriptor` |
| `ConditionalGenericConverter` | Chỉ áp dụng khi metadata/điều kiện kiểu phù hợp |
| `DataBinder` / `WebDataBinder` | Bind giá trị đầu vào vào property hoặc target object |
| `BindingResult` / `FieldError` | Lưu lỗi binding/validation thay vì luôn ném exception ra ngoài |
| `WebMvcConfigurer#addFormatters` | Đăng ký converters/formatters cho hạ tầng Spring MVC |

**Điều kiện để một converter được gọi không chỉ là “class đã tồn tại trong source code”.** Nó phải có trong registry của đúng ConversionService, cặp kiểu phải phù hợp, và luồng xử lý phải thực sự đi qua registry đó.

## 3. Phân biệt ba loại lỗi dễ nhầm nhất

### 3.1. ConverterNotFoundException: không có đường chuyển đổi

Tình huống:

```java
DefaultConversionService cs = new DefaultConversionService();
TicketKey result = cs.convert("TKT-42", TicketKey.class);
```

Đây là fragment, `TicketKey` được định nghĩa ở chương trình mẫu bên dưới. Giả sử không có converter mặc định hoặc factory/constructor hợp lệ để tạo `TicketKey` từ String, lệnh `convert(...)` ném:

```text
org.springframework.core.convert.ConverterNotFoundException
```

Exception này mô tả cặp **sourceType** và **targetType** được yêu cầu, giúp truy ra converter nào đang thiếu.

Cần kiểm tra:

- `cs.canConvert(String.class, TicketKey.class)` có trả `false` không?
- Đã có `Converter<String,TicketKey>` chưa?
- Đã gọi `registry.addConverter(...)` hoặc cấu hình Spring tương đương chưa?
- Bạn có đang sử dụng **đúng instance** của service nơi converter được đăng ký không?
- Java type thực sự nhận được có đúng `String` không, và target type thực sự có đúng `TicketKey` không?

### 3.2. ConversionFailedException: đã chọn converter nhưng chuyển đổi lỗi

Khi converter đã đăng ký nhưng input sai định dạng:

```java
cs.addConverter(new StringToTicketKeyConverter());
cs.convert("BAD-42", TicketKey.class);
```

Một converter nên ném `IllegalArgumentException` cho đầu vào sai theo contract của mình. Hạ tầng conversion có thể bao exception đó bằng `ConversionFailedException` với nguyên nhân bên trong.

Lúc này `canConvert(String.class,TicketKey.class)` thường trả **true**, nhưng `convert(...)` vẫn thất bại. **canConvert chỉ khẳng định có phép chuyển đổi phù hợp cho kiểu, không khẳng định mọi giá trị cụ thể đều chuyển đổi thành công.**

### 3.3. FieldError/typeMismatch: binding thu thập lỗi

Nếu input từ form được gán vào object qua `DataBinder`, lỗi chuyển kiểu thường được thu thập vào `BindingResult`:

```java
FieldError error =
    binder.getBindingResult().getFieldError("ticketKey");

String code = error.getCode(); // Thường là "typeMismatch".
boolean bindingFailure = error.isBindingFailure();
```

Đây là fragment, `binder` cần được tạo/cấu hình trước. Trong controller có `@ModelAttribute`, bạn thường thấy `FieldError` hoặc lỗi bind từ MVC thay vì `ConverterNotFoundException` xuất hiện trực tiếp tới tầng REST response.

Vì vậy không nên dùng một chuỗi thông báo ngoại lệ làm cách nhận biết duy nhất. Hãy xem lỗi phát sinh **ở lớp nào**:

| Nơi gọi | Tình huống | Dấu hiệu |
| --- | --- | --- |
| `conversionService.convert(...)` trực tiếp | Chưa có converter | `ConverterNotFoundException` |
| `conversionService.convert(...)` trực tiếp | Có converter nhưng dữ liệu sai | `ConversionFailedException` |
| `DataBinder#bind(...)` | Conversion property thất bại | `BindingResult` có `typeMismatch` |
| MVC `@PathVariable`/`@RequestParam` scalar | Resolver không convert được | Có thể là `MethodArgumentTypeMismatchException`, thường thành HTTP 400 |
| MVC `@ModelAttribute` | Property không parse được | `BindingResult` / lỗi binding của argument |
| MVC `@RequestBody` JSON | Jackson không giải mã được JSON | Thường là `HttpMessageNotReadableException` |
| Spring Boot `@ConfigurationProperties` | Binding config thất bại | Các lỗi của Boot Binder/BindException tùy đường dẫn |

Tên exception ngoài cùng có thể thay theo lớp wrapper, handler, phiên bản hoặc cách cấu hình. Khi chẩn đoán hãy theo **cause chain** và xác định rõ source/target types.

## 4. Vì sao converter không được tự tìm thấy?

### 4.1. Spring có converters mặc định, nhưng không biết domain type tùy ý

`DefaultConversionService` hỗ trợ nhiều phép chuyển đổi thường gặp, chẳng hạn:

```java
DefaultConversionService cs = new DefaultConversionService();

Integer quantity = cs.convert("3", Integer.class);
Boolean enabled = cs.convert("true", Boolean.class);
```

Nhưng `TicketKey`, `CustomerCode`, `MoneyAmount`, `TenantKey` hoặc một value object chuyên biệt cần một chiến lược riêng, trừ khi một fallback converter có thể áp dụng.

Spring có các cơ chế fallback như chuyển qua factory method hoặc constructor phù hợp trong một số trường hợp. Vì vậy **không phải custom type nào cũng chắc chắn cần converter viết tay**. Tuy nhiên dựa ngầm vào heuristic cũng có thể tạo coupling khó bảo trì; một converter rõ ràng dễ test và kiểm soát format hơn.

### 4.2. Bean tồn tại chưa chắc được đăng ký

Giả sử bạn viết:

```java
public final class StringToTicketKeyConverter
        implements Converter<String, TicketKey> {
    // ...
}
```

Java compiler biết class đó, nhưng registry không tự có nó trong một chương trình tạo bằng `new DefaultConversionService()`. Phải gọi:

```java
cs.addConverter(new StringToTicketKeyConverter());
```

Trong Spring MVC, nên đăng ký ở `WebMvcConfigurer#addFormatters(FormatterRegistry)`. Một converter tự khai báo `@Component` có thể được tự động phát hiện trong một số context/auto-configuration, nhưng **không được giả định** nó sẽ tự xuất hiện trong mọi `ConversionService` của MVC, bean binding và Spring Boot configuration binding.

### 4.3. Đăng ký sai service instance

Ví dụ:

```java
DefaultConversionService first = new DefaultConversionService();
DefaultConversionService second = new DefaultConversionService();

first.addConverter(new StringToTicketKeyConverter());

System.out.println(
    first.canConvert(String.class, TicketKey.class)); // true
System.out.println(
    second.canConvert(String.class, TicketKey.class)); // false
```

Đây là fragment của ví dụ sau. Đăng ký trên `first` không thay đổi `second`. Một `DataBinder` hoặc MVC argument resolver dùng `second` vẫn không có converter, dù một unit test chạy trên `first` thành công.

### 4.4. Đăng ký ở tầng không dùng converter đó

Với Spring Boot, cần phân biệt:

- **MVC FormattingConversionService** dành cho path/query/form binding.
- **Application/property configuration binding** dành cho `application.properties`/`@ConfigurationProperties`, có chiến lược conversion và điểm đăng ký khác.
- **JavaBean property binding** nếu ứng dụng tự tạo `DataBinder` và truyền service riêng.
- **Jackson HTTP message converters** dành cho JSON body `@RequestBody`.

Một converter được đăng ký cho MVC chưa chắc được dùng cho Boot Binder; một custom Jackson deserializer không phải là `Converter<String,TicketKey>` mà `DataBinder` tự hiểu.

## 5. Quy trình chẩn đoán trong 8 bước

### Bước 1 — Xác định nơi lỗi được ném

Hãy ghi lại đường xử lý: convert trực tiếp, `@PathVariable`, `@RequestParam`, `@ModelAttribute`, `@RequestBody` hay `@ConfigurationProperties`. Đừng bắt đầu bằng cách thêm converter khắp nơi.

Ví dụ:

```text
GET /tickets/TKT-42
    -> @PathVariable TicketKey
    -> MVC ConversionService
    -> Converter<String, TicketKey>
```

Không giống:

```text
POST /tickets
Content-Type: application/json
{"key": {"value": 42}}
    -> Jackson deserialization
    -> TicketRequest JSON fields
```

### Bước 2 — Ghi chính xác cặp kiểu

Kiểm tra:

```java
conversionService.canConvert(
    String.class, TicketKey.class);
```

Trong một số tình huống kiểu đích là `List<TicketKey>`, `Optional<TicketKey>` hoặc field có annotation định dạng, Class đơn thuần chưa đủ. Dùng overload `canConvert(TypeDescriptor, TypeDescriptor)` để xét metadata kiểu generic hoặc annotations khi cần.

Nếu `sourceType` là `Integer` nhưng converter được viết cho `String`, đương nhiên có thể không khớp.

### Bước 3 — Kiểm tra registry thực tế

Xác định converter đã được thêm vào **registry của ConversionService được luồng đang dùng**:

```java
registry.addConverter(new StringToTicketKeyConverter());
```

Nếu code đăng ký nằm trong class `@Configuration`:

- Class có nằm trong component scan/import của application không?
- Bean `WebMvcConfigurer` có thật sự được tạo không?
- Phương thức `addFormatters` có chạy khi MVC khởi tạo không?
- Có cấu hình MVC thứ hai hoặc `@EnableWebMvc` làm thay đổi auto-configuration không?

### Bước 4 — Phân biệt không có converter với converter parse sai

Test hai câu hỏi:

```java
boolean supported = cs.canConvert(
    String.class, TicketKey.class);

TicketKey key = cs.convert(
    "TKT-42", TicketKey.class);
```

- `supported=false`: kiểm tra registration/source/target.
- `supported=true` nhưng convert thất bại: kiểm tra parser, pattern, null/blank, locale, overflow và exception cause.

### Bước 5 — Kiểm tra các conversion paths khác

- `String → Integer` chạy tốt không?
- `String → TicketKey` có bị fallback constructor/factory cũ chi phối không?
- Có converter được register sau một converter khác cho cùng cặp kiểu không?
- Có `Formatter<T>` hoặc `PropertyEditor` cục bộ trên binder ảnh hưởng kết quả không?
- Request có đi qua Jackson thay vì WebDataBinder không?

Khi converter mới thay thế một mapping cũ, nên có regression tests cả giá trị hợp lệ và không hợp lệ.

### Bước 6 — Tách lỗi binding khỏi lỗi validation

Nếu form có:

```java
@NotNull
private TicketKey ticketKey;
```

`@NotNull` chỉ kiểm tra **giá trị đã được tạo**, không tự dạy Spring cách chuyển `"TKT-42"` thành `TicketKey`. Nếu conversion thất bại, bạn có thể nhận `typeMismatch` trước khi constraint có giá trị thích hợp để đánh giá.

Trong generic `DataBinder`, `bind(...)` và `validate()` là hai bước khác nhau. Đừng mong `@Valid` tự xuất hiện khi chỉ tạo binder trong unit test.

### Bước 7 — Kiểm tra lỗi được trình bày ở HTTP boundary

Tại `@ControllerAdvice`, phân biệt:

- Sai path/query value → trả HTTP 400 với mã lỗi ổn định.
- Form field sai kiểu → ánh xạ `FieldError.getCode()` / `BindingResult`.
- JSON body sai cấu trúc → xử lý `HttpMessageNotReadableException`.
- Không ném nguyên stack trace, raw rejected values, token hoặc tên class internal cho client.

Một lỗi conversion của client thông thường không nên bị ánh xạ thành HTTP 500 chỉ vì bạn bắt `Exception.class` quá rộng mà không phân loại.

### Bước 8 — Viết test chống tái diễn

Tối thiểu cần:

1. `canConvert=false` trước khi đăng ký.
2. `ConverterNotFoundException` khi gọi `convert` trực tiếp ở case thiếu.
3. `canConvert=true` sau khi đăng ký.
4. Chuyển `"TKT-42"` thành `TicketKey(42)`.
5. Giá trị sai pattern tạo `ConversionFailedException`.
6. `DataBinder` báo `typeMismatch` khi không chuyển được.
7. `DataBinder` thành công với service đã đăng ký converter.
8. ConversionService khác không bị đăng ký theo.
9. Field bắt buộc bị thiếu cho ra lỗi `required` (nếu có `setRequiredFields`), **không phải** missing converter.
10. Integration test MVC bảo đảm `addFormatters` đã chạy trong context thật.

## 6. Thiết kế converter đúng: ngắn, rõ, thread-safe

Value object:

```java
public record TicketKey(long value) {}
```

Chúng ta cố tình **không** khai báo constructor nhận `String` hoặc static `valueOf(String)` / `of(String)` để mặc định Spring không có đường chuyển đổi thuận tiện từ text sang type này.

Converter:

```java
public final class StringToTicketKeyConverter
        implements Converter<String, TicketKey> {

    private static final Pattern FORMAT =
        Pattern.compile("TKT-[0-9]{1,5}");

    @Override
    public TicketKey convert(String source) {
        if (!FORMAT.matcher(source).matches()) {
            throw new IllegalArgumentException(
                "Ticket key must match TKT-<1..5 digits>");
        }
        return new TicketKey(
            Long.parseLong(source.substring(4)));
    }
}
```

Đây là fragment rút từ chương trình đầy đủ ở mục 9. `Converter#convert(S)` được gọi với source **không null** theo contract mặc định của Spring; không cần làm thay đổi input hay đọc state request. `Pattern` có thể tái sử dụng an toàn; `Matcher` được tạo mới mỗi lần.

Quy tắc parse trong ví dụ:

| Input | Kết quả |
| --- | --- |
| `TKT-42` | TicketKey có `value=42` |
| `TKT-00042` | TicketKey có `value=42` — số 0 đầu mất trong dạng số |
| `TKT-0` | TicketKey có `value=0` theo regex, trừ khi domain cấm |
| `TKT-12345` | Hợp lệ, value 12345 |
| `TKT-123456` | Sai vì quá năm chữ số |
| `TKT-abc` | Sai vì không phải chữ số |
| `tkt-42` | Sai vì quy tắc case-sensitive |
| `BAD-42` | Sai prefix |
| `" TKT-42 "` | Sai vì ví dụ không trim tự động |

Nếu ID có số 0 đầu mang ý nghĩa nghiệp vụ, **không** nên lưu nó bằng `long` như bài demo. Hãy dùng String value object và canonicalization được thiết kế rõ.

Không viết converter im lặng trả `null` cho mọi giá trị sai định dạng: điều đó có thể biến “input không hợp lệ” thành “thiếu trường” và che nguyên nhân. Nên ném `IllegalArgumentException` hoặc một unchecked exception thích hợp, để Spring tạo lỗi conversion có thể chẩn đoán.

## 7. Bổ sung converter vào đúng nơi

### 7.1. Trong một chương trình Java thuần

```java
DefaultConversionService cs = new DefaultConversionService();
cs.addConverter(new StringToTicketKeyConverter());
TicketKey key = cs.convert("TKT-42", TicketKey.class);
```

Chỉ cần một service được dùng nhất quán. Đừng thêm vào `DefaultConversionService.getSharedInstance()` vì accessor đó dành cho fallback read-only thông thường; tạo instance riêng cho ứng dụng/test.

### 7.2. Trong Spring MVC / Spring Boot

Một cấu hình MVC rõ ràng:

```java
package demo.web;

import demo.ConversionDebugLab.StringToTicketKeyConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToTicketKeyConverter());
    }
}
```

Đây là **file Spring MVC minh họa**, không nằm trong chương trình Java thuần ở mục 9. Khi sử dụng Spring Boot, để `WebMvcConfigurer` được quét bởi app (hoặc import vào context). Thông thường **không cần thêm `@EnableWebMvc`** trong Boot chỉ để đăng ký converter; `@EnableWebMvc` có thể thay đổi cấu hình MVC mặc định của Boot.

Controller minh họa:

```java
package demo.web;

import demo.ConversionDebugLab.TicketKey;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TicketController {

    @GetMapping("/tickets/{key}")
    public String get(@PathVariable("key") TicketKey key) {
        return "TICKET:" + key.value();
    }
}
```

Với cấu hình converter ở trên và request `GET /tickets/TKT-42`, method có thể nhận `TicketKey(42)` và trả `TICKET:42`. Với `GET /tickets/BAD-42`, argument conversion thất bại và MVC thường trả HTTP 400. **Đây là fragment tích hợp**: cần một ứng dụng Spring Boot Web đầy đủ, các dependencies/controller được quét, và tests HTTP.

### 7.3. @InitBinder cho phạm vi hẹp

Nếu quy tắc chỉ áp dụng ở một controller/form và bạn cần kiểm soát gần nơi dùng, bạn có thể cấu hình `WebDataBinder` trong `@InitBinder`:

```java
@InitBinder("ticketForm")
void customize(WebDataBinder binder) {
    // Ví dụ: binder.registerCustomEditor(
    //     TicketKey.class, new TicketKeyEditor());
}
```

Đây là snippet về **điểm mở rộng**, không phải khai báo đầy đủ editor. Một `PropertyEditor` thường là đối tượng stateful được tạo cho mỗi binder/request, không nên chia sẻ tùy tiện giữa threads. Với quy tắc có thể dùng nhiều endpoints, `Converter<String,TicketKey>` + `WebMvcConfigurer#addFormatters` thường rõ hơn.

**Quan trọng:** `DataBinder#setConversionService(...)` chỉ được set một lần trên binder khi conversion service chưa được thiết lập; trong MVC nên dùng hạ tầng cấu hình chính thức thay vì tìm cách ghi đè ConversionService của binder đang chạy.

### 7.4. Khi nào dùng Formatter thay vì Converter?

Dùng `Converter<String,TicketKey>` khi việc parse **không phụ thuộc locale**. Dùng `Formatter<T>` khi text form/print cần `Locale`, ví dụ ngày, số tiền hoặc số thập phân.

```java
public final class PriceFormatter implements Formatter<BigDecimal> {

    @Override
    public BigDecimal parse(String text, Locale locale)
            throws ParseException {
        // Parse theo chính sách locale cụ thể của ứng dụng.
        throw new UnsupportedOperationException(
            "Only an API-shape example");
    }

    @Override
    public String print(BigDecimal object, Locale locale) {
        return object.toPlainString();
    }
}
```

Đây là **đoạn minh họa chữ ký**, có deliberate exception và không là formatter hoàn chỉnh. Không thêm class này vào chương trình runnable ở mục 9; mục đích là cho thấy `parse`/`print` nhận Locale.

Với ngày giờ mặc định, trước khi tự viết formatter, hãy kiểm tra `@DateTimeFormat`, `@NumberFormat` và bộ formatters Spring MVC đã đăng ký. Nếu annotation format được gắn trên property, `TypeDescriptor` mang thông tin annotation ảnh hưởng khả năng chọn parser.

### 7.5. Khi nào dùng ConverterFactory / GenericConverter?

- `ConverterFactory<S,R>` phù hợp khi một phép chuyển đổi có thể tạo nhiều subtype đích, ví dụ một họ enum.
- `GenericConverter` phù hợp cho nhiều cặp source/target hoặc cần `TypeDescriptor`.
- `ConditionalGenericConverter` khi converter chỉ nên áp dụng nếu kiểu đích hoặc annotations thỏa điều kiện nhất định.

Đừng chuyển ngay sang GenericConverter chỉ vì không hiểu vì sao một Converter đơn giản chưa chạy. Trước hết hãy xác nhận đúng cặp generic types và registry.

## 8. Những điểm đặc thù của Spring Boot

### 8.1. Spring MVC khác @ConfigurationProperties

Tài liệu Spring Boot nhấn mạnh MVC conversion service **khác** conversion service dùng để bind `application.properties` và `application.yaml`. Do đó:

```java
@ConfigurationProperties(prefix = "tickets")
public record TicketSettings(TicketKey defaultKey) {}
```

Đây là fragment; muốn Boot Binder hiểu giá trị `tickets.default-key=TKT-42` cần đăng ký converter theo cơ chế configuration properties binding thích hợp, chẳng hạn `@ConfigurationPropertiesBinding` trong cấu hình phù hợp hoặc custom `ConversionService` mà Boot Binder dùng.

Một converter đăng ký qua `WebMvcConfigurer#addFormatters` chỉ bảo đảm cho MVC conversion path, **không tự đảm bảo** cho Boot configuration binding. Đừng nhầm một unit test của MVC với test của `@ConfigurationProperties`.

### 8.2. Bean conversionService và Boot auto-configuration

Một bean đặt tên `conversionService` có thể ảnh hưởng conversion trong application context, nhưng tạo mới và thay toàn bộ converters mặc định không cẩn thận có thể làm hỏng những nơi từng hoạt động (String ↔ số, thời gian, collection...).

Khi chỉ cần thêm một converter cho MVC, **dùng addFormatters**. Khi cần custom application ConversionService, bắt đầu từ một implementation có default converters rồi **bổ sung** quy tắc cần thiết; đừng thay bằng một `GenericConversionService` rỗng mà không biết hậu quả.

### 8.3. @Component không phải bằng chứng đã được MVC chọn

Trong một số cấu hình Boot, custom converter beans được phát hiện và đưa vào registry tự động. Trong các cấu hình khác, component scan/bean lifecycle hoặc conversion service khác có thể khiến bạn vẫn gặp `typeMismatch`.

Vì vậy muốn chẩn đoán phải **kiểm tra MVC context thật** bằng MockMvc/integration test. Đừng chỉ khẳng định “đã @Component rồi nên chắc chắn chạy”.

## 9. Dự án hoàn chỉnh: Java 17 + Maven + Spring 6.2 + JUnit 5

Bài lab này chạy **không cần Spring Boot** để phân biệt chính xác registry, conversion exception và binding error.

### 9.1. Cấu trúc file

```text
converter-debug-lab/
├── pom.xml
└── src/
    ├── main/java/demo/ConversionDebugLab.java
    └── test/java/demo/ConversionDebugLabTest.java
```

Không có database, REST endpoint hay file cấu hình bắt buộc. Converter sẽ được đăng ký **thủ công** trong từng test để so sánh hai trạng thái.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>demo</groupId>
  <artifactId>converter-debug-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`spring-context` kéo theo các thành phần Spring Core và Beans cần thiết cho conversion và DataBinder. JUnit Jupiter chỉ có ở test scope. Java 17 tương thích Spring Framework 6.

### 9.3. ConversionDebugLab.java

```java
package demo;

import java.util.regex.Pattern;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class ConversionDebugLab {

    // Không có String constructor/static valueOf/of/from(String).
    public record TicketKey(long value) {
    }

    public static final class StringToTicketKeyConverter
            implements Converter<String, TicketKey> {

        private static final Pattern FORMAT =
            Pattern.compile("TKT-[0-9]{1,5}");

        @Override
        public TicketKey convert(String source) {
            if (!FORMAT.matcher(source).matches()) {
                throw new IllegalArgumentException(
                    "Ticket key must match TKT-<digits>");
            }
            return new TicketKey(
                Long.parseLong(source.substring(4)));
        }
    }

    public static final class TicketForm {

        private TicketKey ticketKey;
        private Integer quantity;

        public TicketForm() {
        }

        public TicketKey getTicketKey() {
            return ticketKey;
        }

        public void setTicketKey(TicketKey ticketKey) {
            this.ticketKey = ticketKey;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    // Helper dùng trong main và JUnit: tái tạo một DataBinder
    // mới, gắn đúng ConversionService được truyền vào.
    public static BindingResult bind(
            DefaultConversionService conversionService,
            TicketForm target,
            String keyText,
            String quantityText) {

        DataBinder binder = new DataBinder(
            target, "ticketForm");

        binder.setConversionService(conversionService);
        binder.setAllowedFields("ticketKey", "quantity");

        MutablePropertyValues input =
            new MutablePropertyValues();

        if (keyText != null) {
            input.add("ticketKey", keyText);
        }

        if (quantityText != null) {
            input.add("quantity", quantityText);
        }

        binder.bind(input);
        return binder.getBindingResult();
    }

    private static String errorCode(
            BindingResult result, String field) {

        FieldError error = result.getFieldError(field);
        return error == null ? "none" : error.getCode();
    }

    public static void main(String[] args) {

        DefaultConversionService service =
            new DefaultConversionService();

        // 1. Converter chưa tồn tại trên instance service này.
        System.out.println(
            "BEFORE_CAN_CONVERT=" + service.canConvert(
                String.class, TicketKey.class));

        try {
            service.convert("TKT-42", TicketKey.class);
        } catch (ConverterNotFoundException ex) {
            System.out.println(
                "BEFORE_EXCEPTION="
                + ex.getClass().getSimpleName());
        }

        TicketForm before = new TicketForm();
        BindingResult beforeResult = bind(
            service, before, "TKT-42", "3");

        System.out.println(
            "BEFORE_BIND_ERROR="
            + errorCode(beforeResult, "ticketKey"));

        // 2. Bổ sung converter vào đúng instance.
        service.addConverter(
            new StringToTicketKeyConverter());

        System.out.println(
            "AFTER_CAN_CONVERT=" + service.canConvert(
                String.class, TicketKey.class));

        TicketKey key = service.convert(
            "TKT-42", TicketKey.class);

        System.out.println(
            "AFTER_CONVERT_VALUE=" + key.value());

        TicketForm form = new TicketForm();
        BindingResult afterResult = bind(
            service, form, "TKT-42", "3");

        System.out.println(
            "AFTER_BIND_VALUE=" + form.getTicketKey().value()
            + ",quantity=" + form.getQuantity()
            + ",errors=" + afterResult.getErrorCount());

        // 3. Converter có tồn tại nhưng input không parse được.
        try {
            service.convert("BAD-42", TicketKey.class);
        } catch (ConversionFailedException ex) {
            System.out.println(
                "INVALID_EXCEPTION="
                + ex.getClass().getSimpleName());
        }

        TicketForm invalid = new TicketForm();
        BindingResult invalidResult = bind(
            service, invalid, "BAD-42", "3");

        System.out.println(
            "INVALID_BIND_ERROR="
            + errorCode(invalidResult, "ticketKey"));

        // 4. Một ConversionService khác vẫn chưa được đăng ký.
        DefaultConversionService independent =
            new DefaultConversionService();

        System.out.println(
            "OTHER_INSTANCE_CAN_CONVERT="
            + independent.canConvert(
                String.class, TicketKey.class));
    }
}
```

### 9.4. Cách chương trình chứng minh lỗi

- `TicketKey` là record có constructor canonical nhận `long`, **không có constructor nhận String**; custom String-to-TicketKey conversion cần được đăng ký.
- Trước đăng ký, `service.canConvert(String.class,TicketKey.class)` là false.
- Gọi convert trực tiếp không có converter minh họa `ConverterNotFoundException`.
- Khi bind một form dùng service đó, lỗi chuyển kiểu được thu thập thành `FieldError` có code mặc định `typeMismatch`.
- `service.addConverter(...)` làm service có cặp kiểu mới; cả convert trực tiếp và DataBinder dùng **cùng service** bắt đầu hoạt động.
- Converter ném `IllegalArgumentException` cho `BAD-42`; gọi convert trực tiếp cho ra `ConversionFailedException`, còn bind form ghi `typeMismatch`.
- `DefaultConversionService independent` không thừa hưởng registration của instance khác.

### 9.5. Lệnh chạy

Tại thư mục `converter-debug-lab`, cần Java 17+, Maven 3.x:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java \
  -Dexec.mainClass=demo.ConversionDebugLab
```

Những dòng từ `System.out.println` của chương trình (không bao gồm Maven logging):

```text
BEFORE_CAN_CONVERT=false
BEFORE_EXCEPTION=ConverterNotFoundException
BEFORE_BIND_ERROR=typeMismatch
AFTER_CAN_CONVERT=true
AFTER_CONVERT_VALUE=42
AFTER_BIND_VALUE=42,quantity=3,errors=0
INVALID_EXCEPTION=ConversionFailedException
INVALID_BIND_ERROR=typeMismatch
OTHER_INSTANCE_CAN_CONVERT=false
```

Đây là kết quả dự kiến dựa trên code và contract API Spring 6.2; khi triển khai thực tế, chạy lệnh để xác minh môi trường, Maven versions và configuration. **Không** dùng `exception.getMessage()` làm một dòng stdout cố định vì wording có thể thay đổi theo version.

### 9.6. ConversionDebugLabTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.ConverterNotFoundException;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

class ConversionDebugLabTest {

    private static DefaultConversionService freshWithConverter() {
        DefaultConversionService service =
            new DefaultConversionService();

        service.addConverter(
            new ConversionDebugLab.StringToTicketKeyConverter());

        return service;
    }

    @Test
    void absentConverterReportsNotFound() {
        DefaultConversionService service =
            new DefaultConversionService();

        assertFalse(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertThrows(
            ConverterNotFoundException.class,
            () -> service.convert(
                "TKT-42",
                ConversionDebugLab.TicketKey.class));
    }

    @Test
    void defaultServiceStillConvertsBuiltInNumbers() {
        DefaultConversionService service =
            new DefaultConversionService();

        assertEquals(
            Integer.valueOf(3),
            service.convert("3", Integer.class));

        assertFalse(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));
    }

    @Test
    void missingConverterBecomesBindingTypeMismatch() {
        DefaultConversionService service =
            new DefaultConversionService();

        var target = new ConversionDebugLab.TicketForm();
        BindingResult result = ConversionDebugLab.bind(
            service, target, "TKT-42", "3");

        FieldError error = result.getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getTicketKey());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void registrationMakesCorrectTypeConvertible() {
        DefaultConversionService service = freshWithConverter();

        assertTrue(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        var converted = service.convert(
            "TKT-42",
            ConversionDebugLab.TicketKey.class);

        assertNotNull(converted);
        assertEquals(42L, converted.value());
    }

    @Test
    void registeredConverterStillRejectsBadInput() {
        DefaultConversionService service = freshWithConverter();

        ConversionFailedException error = assertThrows(
            ConversionFailedException.class,
            () -> service.convert(
                "BAD-42",
                ConversionDebugLab.TicketKey.class));

        assertNotNull(error.getCause());
        assertTrue(error.getCause()
            instanceof IllegalArgumentException);
    }

    @Test
    void binderUsesRegisteredConversionService() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();

        BindingResult result = ConversionDebugLab.bind(
            service, target, "TKT-42", "3");

        assertFalse(result.hasErrors());
        assertNotNull(target.getTicketKey());
        assertEquals(42L, target.getTicketKey().value());
        assertEquals(Integer.valueOf(3), target.getQuantity());
    }

    @Test
    void invalidInputWithConverterStillGetsTypeMismatch() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();

        BindingResult result = ConversionDebugLab.bind(
            service, target, "BAD-42", "2");

        FieldError error = result.getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());
        assertTrue(error.isBindingFailure());
        assertNull(target.getTicketKey());
    }

    @Test
    void registrationIsScopedToConversionServiceInstance() {
        DefaultConversionService first = freshWithConverter();
        DefaultConversionService second =
            new DefaultConversionService();

        assertTrue(first.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertFalse(second.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));
    }

    @Test
    void missingRequiredFieldIsDifferentFromMissingConverter() {
        DefaultConversionService service = freshWithConverter();
        var target = new ConversionDebugLab.TicketForm();
        DataBinder binder = new DataBinder(target, "ticketForm");

        binder.setConversionService(service);
        binder.setRequiredFields("ticketKey");

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("quantity", "2");  // Không gửi ticketKey.

        binder.bind(input);

        FieldError error =
            binder.getBindingResult().getFieldError("ticketKey");

        assertNotNull(error);
        assertEquals("required", error.getCode());
        assertNull(target.getTicketKey());
    }

    @Test
    void canConvertDoesNotValidateSourceText() {
        DefaultConversionService service = freshWithConverter();

        assertTrue(service.canConvert(
            String.class,
            ConversionDebugLab.TicketKey.class));

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert(
                "TKT-123456",
                ConversionDebugLab.TicketKey.class));
    }
}
```

Bộ test có **10 phương thức JUnit 5**. Mỗi test dùng ConversionService và target riêng để không phụ thuộc trạng thái được chỉnh bởi test khác.

### 9.7. Chạy JUnit

```bash
mvn -q test
```

Nếu tất cả assertions pass, Maven trả exit code 0; các báo cáo Surefire nằm ở `target/surefire-reports/`. Khi dùng `-q`, stdout của Maven không phải một chuỗi cố định để copy vào bài học.

Các tests kiểm tra cả API trực tiếp và DataBinder; nhưng chúng **không chứng minh** rằng Spring MVC thật đã load `MvcConversionConfig`. Với MVC, cần một integration test riêng dùng `MockMvc`.

## 10. Test tích hợp Spring MVC: chứng minh converter được gắn đúng

Để kiểm tra MVC registration, bạn có thể xây ứng dụng Spring Boot có:

- `spring-boot-starter-web`;
- `MvcConversionConfig implements WebMvcConfigurer` với `addFormatters`;
- `TicketController` có `@PathVariable TicketKey`;
- `spring-boot-starter-test` và `@SpringBootTest` / `@AutoConfigureMockMvc`.

Một fragment JUnit minh họa:

```java
@SpringBootTest
@AutoConfigureMockMvc
class TicketMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ticketPathVariableUsesRegisteredConverter()
            throws Exception {

        mvc.perform(get("/tickets/TKT-42"))
            .andExpect(status().isOk())
            .andExpect(content().string("TICKET:42"));
    }

    @Test
    void invalidTicketKeyReturnsClientError()
            throws Exception {

        mvc.perform(get("/tickets/BAD-42"))
            .andExpect(status().isBadRequest());
    }
}
```

Đây là **fragment**, cần static imports, Spring Boot context và dependency test; không nằm trong hai Java files của lab runnable. Nó xác nhận đúng request pipeline và context của Spring MVC.

Nếu test thứ nhất fail trong khi standalone converter unit test pass, nghi ngờ **config class không được scan**, `addFormatters` không chạy, hoặc MVC dùng một conversion service khác. Nếu test thứ nhất pass nhưng thứ hai không trả 400, hãy kiểm tra custom exception handlers / controller advice và status mapping.

### 10.1. Kiểm tra context thực sự dùng converter nào

Dùng breakpoint tại:

- `MvcConversionConfig#addFormatters`;
- `StringToTicketKeyConverter#convert`;
- controller method;
- exception resolver nếu response không đúng.

Nếu breakpoint converter không bao giờ hit, trace từ route/argument resolver tới service instance, không cố thay logic regex. Nếu breakpoint hit và ném `IllegalArgumentException`, converter đã đăng ký — vấn đề là parser/value, không phải missing registration.

## 11. Debug logging và quan sát lỗi an toàn

Khi cần xác định chuỗi lỗi trong development, có thể bật logging cho gói MVC/Beans/Conversion ở mức DEBUG hoặc TRACE theo đúng framework version:

```properties
logging.level.org.springframework.web=DEBUG
logging.level.org.springframework.validation=DEBUG
logging.level.org.springframework.core.convert=TRACE
```

Đây là **gợi ý cấu hình chẩn đoán**, không cam kết mọi class converter đều log đầy đủ ở TRACE. Trước tiên dùng breakpoint, targeted tests và structured logs do ứng dụng chủ động ghi; đừng bật logging quá chi tiết trên production.

Tối thiểu log an toàn:

```text
requestId=... field=ticketKey sourceType=String targetType=TicketKey
code=typeMismatch status=400
```

Không log nguyên rejected value nếu field có thể chứa token, password hoặc PII. Nếu cần log input của identifier công khai, dùng chính sách redact/rate-limit, tránh log injection.

### 11.1. Kiểm tra cause chain

Nếu catch một exception bên ngoài:

```java
Throwable cause = error;
while (cause != null) {
    System.out.println(cause.getClass().getName());
    cause = cause.getCause();
}
```

Đây là fragment debugging dùng biến `error` đã tồn tại. In cause class names ở môi trường local; trong production hãy dùng logger/correlation ID và phân loại lỗi trước khi ghi chi tiết.

Thông thường:

- `ConverterNotFoundException`: xem source/target và registry.
- `ConversionFailedException`: xem target, source và root cause.
- `TypeMismatchException` hoặc `FieldError(typeMismatch)`: xem binder/argument resolver.
- `HttpMessageNotReadableException`: xem JSON deserializer và payload shape.

### 11.2. Không dùng text ngoại lệ làm contract API

Một thông báo như “Failed to convert property value of type String to TicketKey” là mô tả kỹ thuật, có thể thay đổi. Client nên nhận một code ổn định như `INVALID_TICKET_KEY` hoặc `INVALID_PARAMETER`, status 400 và một câu đơn giản, có thể bản địa hóa.

## 12. Tình huống nâng cao dễ gây chẩn đoán sai

### 12.1. Source và target có cùng tên nhưng khác package

Hai class `demo.api.TicketKey` và `demo.domain.TicketKey` là hai kiểu Java khác nhau. `Converter<String,demo.api.TicketKey>` không tự xử lý `demo.domain.TicketKey`. Hãy kiểm tra fully qualified name trong exception/log/IDE.

### 12.2. Generic collection và TypeDescriptor

Khi đích là `List<TicketKey>`, test chỉ `canConvert(String.class, TicketKey.class)` có thể chưa đủ. Spring có converters cho collection/array elements và sử dụng `TypeDescriptor` để biết element type trong những trường hợp cần thiết.

Ví dụ conceptual:

```java
TypeDescriptor source =
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(String.class));

TypeDescriptor target =
    TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(TicketKey.class));

boolean supported = cs.canConvert(source, target);
```

Đây là fragment cần imports `TypeDescriptor`, `List`, biến `cs` và class `TicketKey`. Cần có cả converter element và collection conversion được cấu hình. Không suy luận rằng converter chỉ được gọi một lần cho toàn list; thông thường conversion phải xử lý từng element.

### 12.3. Locale và date/time formatting

Một `Formatter<LocalDate>` có thể parse theo locale, và `@DateTimeFormat` có thể chỉ định pattern. Nếu lỗi chỉ xuất hiện ở một locale:

- Kiểm tra locale thực tế của request.
- Kiểm tra annotation format trên field.
- Kiểm tra formatter đã đăng ký trong MVC service.
- Test từng chuỗi ngày theo đúng locale/pattern.

Đừng viết `Converter<String,LocalDate>` bằng regex ngẫu nhiên nếu `@DateTimeFormat` hoặc ISO format đã đủ đáp ứng.

### 12.4. Null không tự chứng minh thiếu converter

Một số overload `convert(null, TargetType.class)` có thể trả null cho reference type mà không cần tìm converter thực tế. Vì vậy **đừng dùng null làm probe** của missing conversion; dùng một giá trị thật như `"TKT-42"` và truy vấn `canConvert`.

### 12.5. @ModelAttribute và BindingResult

Với controller:

```java
@PostMapping("/tickets")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("ticketForm") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("INVALID");
    }
    return ResponseEntity.ok("OK");
}
```

Đây là fragment; cần class TicketForm, imports và annotation configuration. `BindingResult` đứng **ngay sau** model attribute để MVC đưa binding/validation errors vào đó thay vì luôn ném exception. Dù @Valid hoạt động, nó không tự cài converter cho TicketKey.

Không tự động expose `FieldError#getRejectedValue()`, stack trace hoặc converter exception text ra JSON response.

### 12.6. Unknown field và missing field không phải missing converter

Nếu request không gửi property `ticketKey`, `DataBinder` không cần chuyển đổi cho field không tồn tại. Nếu configured `setRequiredFields("ticketKey")`, binder có thể tạo `required`.

Nếu client gửi property không có trong DTO, binder có thể bỏ qua hoặc báo lỗi tùy `ignoreUnknownFields` và allowlist. Không thêm Converter chỉ để sửa lỗi `required` hoặc “unknown property”.

### 12.7. Converter bị thay thế và thứ tự registration

Khi nhiều converter cùng đăng ký cho cặp kiểu, framework có quy tắc chọn converter ở registry. Đăng ký thêm một converter khác có thể thay đổi behavior của phép chuyển đổi đang hoạt động. Hãy cấu hình một nguồn sự thật cho cặp type, tránh duplicate registrations và có tests cho edge cases.

### 12.8. Không bỏ converter mặc định khi xây service riêng

Nếu sử dụng `GenericConversionService` rỗng:

```java
GenericConversionService empty = new GenericConversionService();
```

các phép chuyển String sang Integer cũng có thể không chạy vì chưa có default converters. Nếu cần custom service cho application, thường nên bắt đầu bằng `DefaultConversionService` hoặc `DefaultFormattingConversionService` rồi bổ sung converter. Trong MVC, dùng `addFormatters` để giữ lại framework formatters.

### 12.9. @RequestBody JSON và Jackson

Đừng cho rằng `WebMvcConfigurer#addFormatters` luôn thay đổi cách Jackson giải mã một property JSON custom type. Jackson dựa trên constructors, records, deserializers, modules và annotations của nó. Khi request là JSON:

- Xác định target DTO có đúng cấu trúc JSON không.
- Dùng Jackson annotations/custom deserializer nếu cần.
- Test `HttpMessageNotReadableException`/binding behavior thực tế.
- Không dùng cùng tên lỗi `typeMismatch` để mô tả mọi JSON decode failures.

### 12.10. @ConfigurationProperties và conditional converter registration

Spring Boot Binder có một ConversionService/config conversion riêng; với Boot config properties, cách đăng ký như `@ConfigurationPropertiesBinding` có thể thích hợp. Nếu converter chỉ dùng ở MVC, không cần cố đăng ký nó cho mọi tầng. Nếu converter cần cả hai, thiết kế registration ở hai phạm vi một cách rõ ràng và test riêng.

## 13. Checklist code review

1. Loại request nào đang gây lỗi — path, query, form, JSON, config?
2. Source type và target type thực sự là gì?
3. `canConvert(source,target)` trên **đúng instance** trả giá trị nào?
4. Converter có implement `Converter<S,T>` với type arguments chính xác không?
5. Nếu thiếu converter, class configuration có được Spring quét và `addFormatters` đã chạy?
6. Nếu conversion fail, nguyên nhân có phải regex, overflow, blank, locale hoặc parser không?
7. Có PropertyEditor/Formatter/ConverterFactory khác đang tác động không?
8. Có dùng converter cho Java custom type chỉ có factory method hoặc constructor mặc định mà behavior không như ý không?
9. Có tạo ConversionService mới sau khi đã đăng ký converter ở instance cũ không?
10. Có vô tình thay default service bằng một service rỗng không?
11. Tình huống là generic collection hay property có annotations cần TypeDescriptor không?
12. Với @ModelAttribute, lỗi vào `BindingResult` hay bị ném ngoài controller?
13. Với @RequestBody, đã xem Jackson deserialization thay vì DataBinder chưa?
14. Có test chính xác giá trị valid và invalid trên cùng converter không?
15. Lỗi HTTP response đã được chuẩn hóa 4xx, tránh lộ chi tiết nội bộ chưa?

## 14. Bảng xử lý nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng giải quyết |
| --- | --- | --- |
| `canConvert=false` cho custom value object | Registry và cặp `S,T` | Đăng ký `Converter<String,Target>` đúng service |
| `ConverterNotFoundException` khi convert trực tiếp | `getSourceType/getTargetType` | Xác minh converter registration/source/target |
| `canConvert=true` nhưng sai input | Parser và nguyên nhân nested | Sửa giá trị hoặc converter; test boundary |
| `ConversionFailedException` | Root cause, format/locale | Trả lỗi input đúng semantics, không ghi stack trace client |
| `FieldError.code=typeMismatch` | Conversion path của DataBinder | Kiểm tra converter cùng binder conversionService |
| Unit test pass, MockMvc fail | Spring MVC configuration/scan | `WebMvcConfigurer#addFormatters` và integration test |
| MVC pass, @ConfigurationProperties fail | Boot config Binder dùng service khác | Đăng ký theo cơ chế Boot configuration binding |
| Form pass, JSON fail | Jackson không dùng cùng ConversionService | Sửa DTO/Jackson deserialization |
| String→Integer fail sau custom config | Default converters bị mất | Dùng DefaultConversionService/FormattingConversionService |
| Chỉ ngày dạng dd/MM/yyyy lỗi | Formatting/Locale/annotation | `@DateTimeFormat` và Formatter phù hợp |
| Missing field tạo `required` | Không phải converter thiếu | Sửa HTTP request/required field policy |
| Unknown property hoặc over-posting | Sai DTO/binder scope | Input DTO, allowlist, test suppressed fields |

## 15. Tổng kết

**“Không có converter phù hợp hoặc converter không được đăng ký” là lỗi về *khả năng chuyển đổi và nơi đăng ký*, khác với lỗi giá trị sai định dạng.** Với `ConversionService`, hãy kiểm tra `canConvert(...)` rồi gọi `convert(...)` trên đúng instance:

- `ConverterNotFoundException`: không tìm thấy đường chuyển đổi phù hợp.
- `ConversionFailedException`: có đường chuyển đổi nhưng conversion thực tế thất bại.
- `FieldError(typeMismatch)`: lỗi conversion đã được DataBinder thu thập cho property.
- `MethodArgumentTypeMismatchException`: một biểu hiện có thể có của lỗi path/query argument trong Spring MVC.

Giải pháp là viết converter/formatter có contract rõ, đăng ký vào **registry được pipeline thực sự sử dụng**, giữ default converters và có integration tests cho MVC hoặc Boot Binder tùy nơi dữ liệu đi vào. `@Valid` kiểm tra dữ liệu đã bind, **không** thay thế việc đăng ký converter. Khi dữ liệu là JSON, nhớ rằng Jackson có một cơ chế chuyển dữ liệu khác.

## Tài liệu tham khảo

- Spring Framework 6.2 — Type Conversion (Converter SPI, ConversionService API, registration): https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 — Spring MVC Type Conversion, addFormatters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- Spring Framework 6.2 Javadoc — `ConversionService`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework 6.2 Javadoc — `ConverterNotFoundException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConverterNotFoundException.html
- Spring Framework 6.2 Javadoc — `ConversionFailedException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/ConversionFailedException.html
- Spring Framework 6.2 Javadoc — `DefaultConversionService`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html
- Spring Framework 6.2 Javadoc — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — MVC `@InitBinder` and data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Boot Reference — MVC Conversion Service differs from application.properties conversion: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/