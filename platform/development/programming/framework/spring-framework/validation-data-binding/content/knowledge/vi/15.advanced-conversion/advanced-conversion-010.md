# Kiểm soát chi phí, tác dụng phụ và lỗi trong converter tùy chỉnh của Spring

Một custom `Converter<S, T>` thường trông rất nhỏ: nhận một giá trị kiểu nguồn, chuẩn hóa hoặc phân tích nó, rồi trả về kiểu đích. Nhưng converter có thể được gọi trong luồng binding của nhiều request, nhiều field và nhiều thread. Một phép chuyển đổi tưởng như đơn giản có thể trở thành điểm nóng CPU, tạo nhiều object tạm, đọc file hoặc gọi database lặp lại, làm thay đổi trạng thái dùng chung, hoặc ném exception không đúng cách.

Khi thiết kế converter, cần kiểm soát bốn khía cạnh:

1. **Chi phí thực thi**: độ phức tạp CPU, cấp phát bộ nhớ, parse lặp, tra cứu và I/O.
2. **Tác dụng phụ**: ghi database, gửi message, sửa object dùng chung, đọc đồng hồ/hệ thống ngoài và tính không xác định.
3. **Lỗi chuyển đổi**: phân biệt input sai, không có converter, lỗi hạ tầng và lỗi lập trình; giữ đúng thông tin field khi binding.
4. **Khả năng vận hành**: thread-safety, logging, metrics, kiểm thử và benchmark có ý nghĩa.

Một nguyên tắc tốt là converter chỉ thực hiện phép ánh xạ **nhỏ, xác định, có thể kiểm thử và an toàn khi gọi lặp lại**. Các quy trình nghiệp vụ có lưu dữ liệu, gọi dịch vụ ngoài hoặc quyết định quyền truy cập thường nên nằm ở tầng service/domain thay vì giấu bên trong converter.

## 1. Converter nằm ở đâu trong luồng xử lý?

`Converter<S, T>` là SPI strongly typed của Spring Core:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

`ConversionService` tìm một converter phù hợp với kiểu nguồn và kiểu đích, sau đó gọi `convert(...)`. Với property binding, `DataBinder` hoặc `WebDataBinder` sử dụng conversion service để chuyển giá trị input trước khi gán vào JavaBean property.

```text
HTTP / PropertyValues / giá trị Java
                 |
                 v
            DataBinder
                 |
                 v
       ConversionService
                 |
          tra cứu converter
                 |
                 v
         Converter<S, T>
          |           |
       thành công   lỗi chuyển đổi
          |           |
          v           v
       setter     BindingResult / exception
          |
          v
      Java object
```

Một converter có thể được gọi trực tiếp qua `conversionService.convert(...)`, gián tiếp khi `DataBinder` bind request parameter, nhiều lần trong cùng request khi nhiều property/collection element cần chuyển đổi, hoặc đồng thời trên nhiều thread nếu conversion service dùng chung.

**Đừng suy ra converter chỉ chạy một lần vì một HTTP request.** Số lần gọi phụ thuộc số giá trị cần convert và cấu trúc input. Collection/array có thể kích hoạt chuyển đổi ở từng phần tử; controller hoặc service cũng có thể chủ động gọi `convert` nhiều lần.

## 2. Chi phí của converter: nhìn xa hơn một dòng code

Chi phí chuyển đổi không chỉ là thời gian trong method `convert`:

| Thành phần chi phí | Ví dụ | Dấu hiệu |
| --- | --- | --- |
| CPU | Regex phức tạp, parse ngày/nhiều định dạng, tìm kiếm | Thời gian tăng theo số lần gọi hoặc độ dài input |
| Bộ nhớ | Chuỗi trung gian, matcher, object tạm, collection mới | Allocation rate và GC tăng |
| Lookup | Tra cứu danh mục lớn hoặc parse metadata mỗi lần | Độ trễ tăng khi dữ liệu/phạm vi tìm kiếm lớn |
| I/O | Đọc file, gọi HTTP, truy vấn database | Latency cao, phụ thuộc mạng/dịch vụ khác |
| Lock/contention | Synchronized cache hoặc mutable singleton | Throughput giảm khi nhiều thread |
| Logging/telemetry | Log payload hoặc stack trace cho từng input sai | CPU, I/O log và rủi ro lộ dữ liệu |

Một converter `String → Integer` thường chỉ parse đơn giản. Nhưng nếu converter `String → Customer` tải bản ghi từ database, mỗi form có thể phát sinh query cho từng field hoặc phần tử. Khi binder xử lý danh sách 500 mã khách hàng, 500 truy vấn nối tiếp có thể trở thành nút thắt N+1.

**Nguyên tắc:** converter nên chuyển đổi representation và xác thực cú pháp cơ bản; nếu cần truy xuất trạng thái nghiệp vụ hiện thời, hãy cân nhắc thực hiện sau binding ở tầng service với batch lookup, transaction và chính sách cache rõ ràng.

## 3. Viết converter nhỏ, stateless và xác định

Ví dụ converter chuyển chuỗi mã sản phẩm thành value object:

```java
public record ProductCode(String value) {
}

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid product code");
        }

        return new ProductCode(normalized);
    }
}
```

Đây là ví dụ minh họa; cần import `java.util.Locale` và Spring `Converter`. Các thuộc tính tốt: không đọc/ghi database; không gọi HTTP, file system hoặc broker; không thay đổi input; không phụ thuộc thứ tự gọi; kết quả chỉ phụ thuộc input và quy tắc đã định nghĩa; không lưu trạng thái request trong instance converter.

Converter vẫn phải được đánh giá theo input thực tế: regex chạy trên chuỗi rất dài vẫn tiêu tốn CPU; `trim()` và `toUpperCase()` có thể tạo chuỗi mới. Nên đặt giới hạn độ dài input ở boundary đáng tin cậy nếu field có thể nhận payload lớn.

### 3.1. Tránh sửa source object

Không nên viết converter sửa trực tiếp source collection hoặc object rồi trả lại một phần đã thay đổi:

```java
// Không nên: sửa trạng thái object do nơi gọi sở hữu.
source.removeIf(String::isBlank);
return source;
```

Một converter tốt thường trả về object đích mới hoặc value object immutable đã chuẩn hóa. Nếu source mutable được nhiều nơi giữ reference, việc sửa nó khiến hành vi phụ thuộc thứ tự xử lý và có thể gây lỗi khi nhiều tầng cùng dùng reference.

### 3.2. Không lưu dữ liệu từng request trong field

Converter có thể được registry dùng chung. Tránh các field kiểu `currentTenant`, `currentUser`, `lastInput` hoặc một formatter mutable không thread-safe. Thay vào đó, truyền dữ liệu cần thiết qua source/target metadata nếu SPI hỗ trợ, hoặc đưa logic phụ thuộc tenant/user vào service nơi context request được quản lý rõ ràng.

## 4. Tác dụng phụ: điều gì nên và không nên nằm trong converter?

*Tác dụng phụ* là thay đổi trạng thái bên ngoài kết quả trả về, ví dụ ghi database, gửi email, cập nhật cache, phát event, ghi file hoặc sửa một object dùng chung.

| Việc converter làm | Đánh giá | Lý do |
| --- | --- | --- |
| Trim/parse/normalize input | Thường phù hợp | Là phép chuyển representation |
| Kiểm tra cú pháp mã | Thường phù hợp | Kết quả xác định từ input |
| Tạo value object immutable | Phù hợp | Không thay đổi hệ thống bên ngoài |
| Query database để tìm entity | Cần cân nhắc; thường nên đưa ra service | Có I/O, N+1, phụ thuộc trạng thái |
| Lưu entity hoặc tăng số dư | Không phù hợp | Conversion bị gọi lặp có thể thực hiện nghiệp vụ nhiều lần |
| Gửi email/message hoặc gọi API | Không phù hợp | Retry/rebinding có thể gây duplicate action |
| Sửa cache dùng chung | Rủi ro cao | Cần đồng bộ, eviction và ownership |
| Log payload đầy đủ | Tránh | Tăng I/O và có thể lộ dữ liệu |

Giả sử converter nhận `"C-100"` và truy vấn database để lấy customer. Controller có thể bind cùng field ở nhiều luồng xử lý; test cũng có thể gọi converter nhiều lần. Nếu converter còn đánh dấu khách hàng “đã truy cập”, gửi notification hoặc cập nhật trạng thái, một phép chuyển kiểu có thể vô tình thực hiện nghiệp vụ lặp lại.

Framework gọi converter không phải cam kết *exactly once*. Không nên dùng conversion call như cơ chế transaction hoặc event trigger.

### Tách conversion khỏi business lookup

```text
Request chứa customerCode
        |
        v
Converter: String -> CustomerId
        |
        v
DTO chứa CustomerId
        |
        v
Application Service
        |
        +-- batch load customer
        +-- kiểm tra quyền và trạng thái
        +-- thực hiện nghiệp vụ trong transaction
```

Converter chỉ phân tích mã và tạo `CustomerId`. Service mới truy vấn repository, kiểm tra customer tồn tại, quyền người dùng và trạng thái được phép cập nhật. Nhờ đó conversion có thể kiểm thử không cần database; service tối ưu truy vấn theo lô và quản lý transaction phù hợp.

Nếu yêu cầu sản phẩm thật sự cần chuyển ID thành entity trong binding, hãy cân nhắc custom argument resolver, application service hoặc abstraction có cache/batch semantics rõ ràng; đừng giấu chuỗi truy vấn trong converter chung toàn ứng dụng.

## 5. Thread-safety và vòng đời dùng chung

Spring mô tả `ConversionService` là đối tượng **stateless**, được thiết kế để khởi tạo lúc ứng dụng khởi động rồi chia sẻ giữa nhiều thread. Converter được đăng ký vào service vì thế cũng cần thread-safe.

### 5.1. Những mẫu code không an toàn

```java
public final class BadDateConverter
        implements Converter<String, Date> {

    private final SimpleDateFormat format =
            new SimpleDateFormat("yyyy-MM-dd");

    @Override
    public Date convert(String source) {
        try {
            return format.parse(source);
        } catch (ParseException ex) {
            throw new IllegalArgumentException(ex);
        }
    }
}
```

`SimpleDateFormat` mutable và không thread-safe. Nếu converter singleton được nhiều request dùng đồng thời, formatter có thể tạo kết quả sai hoặc lỗi khó tái hiện.

Thay vào đó, chọn API immutable/thread-safe:

```java
public final class StringToLocalDateConverter
        implements Converter<String, LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public LocalDate convert(String source) {
        return LocalDate.parse(source, FORMAT);
    }
}
```

Cần import `java.time.LocalDate` và `java.time.format.DateTimeFormatter`. Với format tùy chỉnh, tạo formatter immutable khi khởi tạo thay vì parse pattern ở mỗi lần gọi.

### 5.2. Nếu cần cache?

Cache kết quả conversion có thể giảm chi phí nếu phép chuyển đổi đắt và input lặp lại, nhưng cache thêm trạng thái và chi phí quản lý:

- Giới hạn kích thước và eviction để tránh bộ nhớ tăng vô hạn.
- Xác định key có bao gồm tenant, locale, version và context cần thiết không.
- Xử lý dữ liệu stale và invalidation.
- Bảo đảm thread-safe, tránh lock lớn làm giảm throughput.
- Không cache kết quả phụ thuộc quyền người dùng nếu key thiếu security context.
- Nếu negative cache lỗi, đặt TTL và chính sách rõ ràng.

Trước khi thêm cache, đo xem bottleneck có thực sự là converter hay lookup bên dưới. Cache trong converter có thể che một thiết kế N+1 thay vì giải quyết đúng tầng.

## 6. Tách chi phí lookup converter khỏi thực thi converter

`GenericConversionService` có thể cache việc tra cứu converter phù hợp theo kiểu nguồn/đích và metadata. Nhưng **cache lookup converter không đồng nghĩa cache kết quả chuyển đổi**.

```java
for (int i = 0; i < 1_000; i++) {
    service.convert("AB-123", ProductCode.class);
}
```

Dù registry không phải tìm lại converter từ đầu ở mọi lần gọi, method `convert` vẫn chạy để tạo/nhận giá trị đích cho từng lần gọi. Nếu converter bên trong parse file hoặc query database, chi phí đó vẫn lặp lại.

Ngoài ra:

- `canConvert(String.class, Target.class)` cho biết registry có đường chuyển đổi giữa hai kiểu.
- Với collection/map, khả năng chuyển đổi ngoài cùng vẫn có thể là `true` nhưng một phần tử cụ thể không chuyển được, khiến `convert` thất bại.
- Kết quả có thể phụ thuộc `TypeDescriptor`, generic element type, annotation hoặc `ConditionalConverter`.
- `canConvert` không bảo đảm mọi giá trị thực tế đều hợp lệ.

Khi đo hiệu năng, hãy tách thời gian khởi tạo service/registry, tra cứu hoặc chuẩn bị converter, thực thi converter với input hợp lệ, xử lý input sai, allocation/GC và I/O (tốt nhất loại I/O khỏi converter).

## 7. Chi phí CPU và bộ nhớ: các mẫu cần tránh

### 7.1. Tạo regex liên tục

Nếu pattern phức tạp và converter được gọi với số lượng lớn, tránh biên dịch lại pattern mỗi lượt:

```java
// Không tối ưu: compile pattern mỗi lần convert.
boolean valid = Pattern.compile("[A-Z]{2}-[0-9]{3}")
        .matcher(source)
        .matches();
```

Có thể tạo `Pattern` một lần:

```java
private static final Pattern CODE =
        Pattern.compile("[A-Z]{2}-[0-9]{3}");

public ProductCode convert(String source) {
    if (!CODE.matcher(source).matches()) {
        throw new IllegalArgumentException("Invalid code");
    }
    return new ProductCode(source);
}
```

`Pattern` immutable và có thể chia sẻ; `Matcher` được tạo cho mỗi phép kiểm tra. Đây là tối ưu nhỏ dựa trên chi phí thực tế, không phải lời mời biến mọi converter thành mã phức tạp.

### 7.2. Chuẩn hóa lặp ở nhiều tầng

Tránh trim/uppercase/parse cùng một mã ở converter, controller, service và repository. Quyết định tầng nào sở hữu normalization rồi giữ invariant đó. Nếu value object `ProductCode` bảo đảm canonical, các tầng sau không cần chuẩn hóa lại.

### 7.3. Tránh tạo graph object quá lớn

Converter biến một dòng input thành graph entity nhiều tầng có thể tạo nhiều allocation, kích hoạt lazy loading hoặc quan hệ hai chiều. Conversion nên trả về value object gọn; việc load entity và graph nghiệp vụ thuộc repository/service.

### 7.4. Giới hạn kích thước đầu vào

Regex có thể chạy rất chậm trên chuỗi adversarial nếu biểu thức có backtracking nghiêm trọng. Với input từ client:
- Giới hạn độ dài ở request boundary.
- Ưu tiên regex đơn giản, có cấu trúc ổn định.
- Kiểm thử input dài và trường hợp gần khớp nhưng thất bại.
- Không parse payload lớn không giới hạn trong converter.

## 8. Thiết kế lỗi chuyển đổi có thể chẩn đoán

Theo contract Spring, `Converter.convert(S)` nhận source khác null; khi không thể chuyển đổi, có thể ném unchecked exception. `IllegalArgumentException` là cách thông dụng để báo giá trị nguồn không hợp lệ. Spring bao bọc lỗi phù hợp trong cơ chế conversion, thường là `ConversionFailedException` chứa source/target type và nguyên nhân.

| Loại lỗi | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Không có converter | `String` sang kiểu đích chưa đăng ký | `ConverterNotFoundException` |
| Có converter nhưng input sai | `"abc"` sang ProductCode theo format nghiêm ngặt | `ConversionFailedException` với cause như `IllegalArgumentException` |
| Lỗi trong logic converter | Null assumption sai, bug hoặc dependency nội bộ lỗi | Xử lý theo root cause |
| Field binding thất bại | Không convert được property `code` | Có thể thành `FieldError` mã `typeMismatch` |
| Validation thất bại sau bind | `@NotBlank` hoặc business constraint không thỏa | Validation error, khác conversion error |

### 8.1. Invalid input và lỗi hệ thống không giống nhau

Nếu người dùng nhập `"A?"` cho mã sản phẩm, đây là invalid input dự đoán được. Converter có thể ném `IllegalArgumentException("Invalid product code")`.

Nếu converter gọi dịch vụ ngoài và dịch vụ timeout, đó là lỗi hạ tầng. Converter lý tưởng không nên làm I/O. Nếu kiến trúc bắt buộc phải gọi, đừng bọc mọi exception thành “mã không hợp lệ”: người dùng có thể sửa input vô ích trong khi dịch vụ đang lỗi.

### 8.2. Không dùng exception để điều khiển nhánh bình thường

Không nên parse một format, bắt exception rồi thử hàng chục format mỗi lần gọi nếu có cách xác định rõ hơn. Exception nên đại diện một lần chuyển đổi thất bại, không phải cơ chế điều khiển vòng lặp thường xuyên. Với nhiều định dạng ngày, cân nhắc `Formatter` có danh sách định dạng giới hạn và quy tắc chọn rõ ràng.

### 8.3. Không làm lộ dữ liệu trong exception

Thông báo lỗi không nên chứa token, password, địa chỉ riêng tư hay payload đầy đủ. Một lỗi có thể lưu field path, mã lỗi và giá trị đã mask. Stack trace nội bộ có thể ghi ở server khi cần điều tra, nhưng không trả nguyên stack trace cho client.

## 9. Binding và BindingResult: giữ lỗi ở đúng field

Khi custom converter được gọi trong `DataBinder`, lỗi chuyển đổi thường có thể được ghi vào `BindingResult` như một `FieldError`. Điều đó cho phép controller hoặc view hiển thị lỗi gắn với input tương ứng.

Ví dụ controller Spring MVC (đoạn tích hợp, cần class DTO, imports, bean converter và cấu hình MVC):

```java
@PostMapping("/products")
String submit(
        @Valid @ModelAttribute("form") ProductForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "products/form";
    }
    productService.create(form);
    return "products/success";
}
```

`BindingResult` cần đứng ngay sau tham số `@ModelAttribute` tương ứng. Nếu `code=bad-value` không được converter chuyển đổi, controller có thể nhận lỗi binding và không nên gọi business service như thể form đã hợp lệ.

Kiểm tra minh họa:

```java
FieldError error = result.getFieldError("productCode");
if (error != null) {
    String code = error.getCode();
}
```

Mã lỗi được tạo theo resolution strategy của Spring; với lỗi chuyển kiểu, `typeMismatch` là mã thường gặp. Không nên phụ thuộc message mặc định hoặc so sánh toàn bộ thông điệp exception trong business logic; hãy dùng field, error code và message resource phù hợp.

**Chú ý:** không phải mọi nguồn dữ liệu đều dùng cùng cơ chế. `@RequestBody` JSON đi qua `HttpMessageConverter` (thường Jackson), có thể báo `HttpMessageNotReadableException`. Form binding với `@ModelAttribute` đi qua `WebDataBinder`. Hãy xác định nguồn input trước khi chẩn đoán.

## 10. Retry và tính idempotent

Converter không nên tạo side effect vì việc gọi lại có thể xảy ra ở test, retry, bind lại hoặc do nhiều field cần chuyển đổi. Giả sử converter vừa parse mã vừa phát event `ProductCodeParsed`. Nếu cùng dữ liệu được xử lý lại, event có thể phát nhiều lần.

Nếu hệ thống cần phát event, hãy làm điều đó sau khi nghiệp vụ đã được chấp nhận và lưu thành công, bằng cơ chế transaction/outbox phù hợp. **Không đặt publish message vào converter.**

Tương tự, converter phụ thuộc thời gian hiện tại hoặc trạng thái DB có thể cho kết quả khác nhau với cùng một input ở các lần gọi. Điều đó khiến cache/test/retry khó xác định. Giữ converter thuần càng nhiều càng tốt; dependency không xác định nên nằm ở service với contract và test riêng.

## 11. Quan sát hiệu năng mà không gây thêm vấn đề

Có thể đo thời gian và số lần gọi bằng metrics, nhưng không log toàn bộ giá trị đầu vào. Một kế hoạch đo tốt:

- Counter số lần convert theo cặp kiểu hoặc converter name.
- Timer/histogram cho latency.
- Tỷ lệ lỗi theo mã lỗi, không gắn raw user input vào metric tag.
- Phân tích CPU/allocation bằng profiler khi có dấu hiệu bottleneck.
- Theo dõi external dependency ở service/repository thay vì gộp tất cả vào metric conversion.

**Tránh cardinality cao:** không đưa product code, user ID, tenant ID hoặc raw field value vào metric label. Mỗi giá trị khác nhau có thể tạo một time series mới, khiến hệ thống giám sát tiêu thụ tài nguyên quá mức.

Logging nên có cấu trúc, mức độ hợp lý và redaction. Với invalid input dự kiến, thường chỉ cần field path + error code; stack trace đầy đủ cho từng input sai có thể tạo lượng log lớn.

## 12. Benchmark đúng cách

Không đánh giá converter bằng một lần gọi và một con số `System.nanoTime` duy nhất. JVM có JIT compilation, warm-up, GC, CPU scheduling và nhiễu từ máy chạy. Nếu cần benchmark nghiêm túc, dùng **JMH**:

1. Tạo benchmark riêng cho parse thành công, parse thất bại và input biên.
2. Khởi tạo ConversionService/registry ngoài vùng đo nếu mục tiêu là latency convert, không phải startup.
3. Warm-up đủ vòng, nhiều measurement iteration và fork.
4. Dùng input đa dạng/realistic để tránh benchmark chỉ đo một nhánh thuận lợi.
5. Đo throughput, average/sample time và allocation rate khi phù hợp.
6. So sánh baseline với converter mới trên cùng môi trường, JDK và dữ liệu.
7. Nếu converter có I/O, đo riêng service/I/O; không gộp benchmark mạng vào tuyên bố hiệu năng parsing.

Benchmark micro không thể đại diện đầy đủ latency HTTP request. Integration test và production telemetry mới cho thấy ảnh hưởng toàn luồng.

### Checklist trước khi tối ưu

- Có số liệu cho thấy converter là bottleneck?
- Chi phí nằm ở parse, allocation, lock hay I/O?
- Có thao tác nào thực hiện lặp lại ở controller/service khác?
- Có thể chuyển I/O ra khỏi converter hoặc batch lookup ở service?
- Có thể tạo formatter/pattern immutable một lần?
- Input có giới hạn độ dài và cấu trúc không?
- Tối ưu có giữ nguyên kết quả và lỗi mong đợi không?

Đừng hy sinh tính đúng đắn hoặc bảo mật để giảm vài allocation không đáng kể.

## 13. Ví dụ Java 17+ chạy được: lỗi converter được ghi vào BindingResult

Ví dụ sau dùng Spring Framework 6.2.x, không cần Spring Boot hay HTTP server. Nó minh họa converter stateless, exception cho input sai và việc `DataBinder` ghi lỗi conversion vào `BindingResult`. Chương trình chứng minh conversion trực tiếp và binding là hai điểm gọi khác nhau.

### 13.1. Cấu trúc dự án

```text
converter-cost-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ConverterErrorDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'converter-cost-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.ConverterErrorDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dùng JDK 17+ và Gradle tương thích, có kết nối Maven Central để tải dependency lần đầu. `spring-context` kéo theo module Spring Core/Beans/Context cần cho ConversionService và DataBinder.

### 13.2. Mã nguồn đầy đủ

**`src/main/java/example/ConverterErrorDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import java.util.Locale;

public class ConverterErrorDemo {

    public record ProductCode(String value) {
    }

    public static final class StringToProductCodeConverter
            implements Converter<String, ProductCode> {

        @Override
        public ProductCode convert(String source) {
            String normalized =
                    source.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new IllegalArgumentException(
                        "Product code must match AA-123");
            }

            return new ProductCode(normalized);
        }
    }

    public static final class ProductForm {
        private ProductCode productCode;

        public ProductCode getProductCode() {
            return productCode;
        }

        public void setProductCode(ProductCode productCode) {
            this.productCode = productCode;
        }
    }

    public static void main(String[] args) {
        ConfigurableConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new StringToProductCodeConverter());

        ProductCode valid =
                service.convert(" ab-123 ", ProductCode.class);
        System.out.println("valid=" + valid);

        ProductForm form = new ProductForm();
        DataBinder binder = new DataBinder(form, "productForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("productCode", "bad-value");

        binder.bind(values);

        FieldError error =
                binder.getBindingResult().getFieldError("productCode");

        System.out.println("boundValue=" + form.getProductCode());
        System.out.println("hasError=" + (error != null));
        System.out.println("errorField="
                + (error != null ? error.getField() : "<none>"));
        System.out.println("errorCode="
                + (error != null ? error.getCode() : "<none>"));
    }
}
```

### 13.3. Chạy chương trình và stdout

Từ thư mục dự án:

```bash
gradle -q run
```

Nếu đã có Gradle wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

**Stdout mong đợi:**

```text
valid=ProductCode[value=AB-123]
boundValue=null
hasError=true
errorField=productCode
errorCode=typeMismatch
```

Giải thích:

- Converter trim và viết hoa chuỗi hợp lệ, tạo value object immutable.
- Input `bad-value` không khớp quy tắc, converter ném `IllegalArgumentException`.
- Khi đi qua `DataBinder`, lỗi được ghi vào `BindingResult` với field `productCode`.
- `boundValue=null` vì setter không nhận được `ProductCode` từ input lỗi.
- `typeMismatch` là mã lỗi binding thông dụng; message cụ thể phụ thuộc message code resolver và message bundle.

Converter không ghi database, không log raw input, không giữ trạng thái request và không phụ thuộc thread khác. Đó là thiết kế dễ chia sẻ và kiểm thử.

## 14. Kiểm thử converter: kết quả, lỗi và tính xác định

Một bộ test có giá trị nên kiểm tra:

| Nhóm | Input | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ cơ bản | `"ab-123"` | `ProductCode("AB-123")` |
| Có khoảng trắng | `"  ab-123  "` | Cùng giá trị chuẩn hóa |
| Sai format | `"abc"` | Invalid input exception |
| Sai prefix | `"1A-123"` | Invalid input exception |
| Thiếu phần số | `"AB-"` | Invalid input exception |
| Chuỗi rất dài | Input vượt giới hạn contract | Từ chối có kiểm soát ở boundary hoặc converter |
| Lặp lại | Cùng input nhiều lần | Kết quả giống nhau, không side effect |
| Đồng thời | Nhiều thread dùng chung service | Không có trạng thái chéo, không sai kết quả |
| Binding sai kiểu | Form gửi mã invalid | `BindingResult` có lỗi đúng field |

### Unit test thuần cho converter

```java
@Test
void normalizesProductCode() {
    var converter = new StringToProductCodeConverter();

    assertEquals(
            new ProductCode("AB-123"),
            converter.convert(" ab-123 "));
}

@Test
void rejectsInvalidCode() {
    var converter = new StringToProductCodeConverter();

    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("bad-value"));
}
```

Đây là đoạn **JUnit test minh họa**; cần cấu hình JUnit 5 và imports `org.junit.jupiter.api.Test` cùng assertions. Test thuần không cần tạo ApplicationContext hoặc kết nối database.

### Test tính thread-safe

Nếu converter stateless và chỉ dùng API immutable/thread-safe, có thể kiểm tra cùng instance được gọi đồng thời với nhiều input. Test concurrency không chứng minh tuyệt đối không có race condition; hãy xem xét code và dependencies, rồi dùng stress test/profiler phù hợp.

### Test side effects

Nếu converter có thể chạm một dependency (đây là dấu hiệu nên xem lại thiết kế), dùng mock/spy để xác nhận số lần tương tác, ví dụ một request không được vô tình lưu entity hoặc phát message. Tốt hơn, chuyển interaction sang application service, nơi idempotency, transaction và retry semantics được kiểm soát.

## 15. Checklist review một converter tùy chỉnh

Trước khi đưa converter vào registry dùng chung, hãy tự hỏi:

**Đầu vào và đầu ra**
- Kiểu nguồn/đích có đúng và rõ ràng?
- Có xử lý khoảng trắng, null, giá trị rỗng và ký tự Unicode theo contract?
- Có giới hạn input và tránh regex tốn kém?

**Chi phí**
- Có parse pattern/metadata lặp lại?
- Có tạo object/collection lớn không cần thiết?
- Có I/O hoặc N+1 lookup?
- Có benchmark/profile chứng minh cần tối ưu?

**Tác dụng phụ và đồng thời**
- Có ghi database, phát event, gọi API hoặc thay cache?
- Có field mutable theo request?
- Có dùng API thread-safe khi service được chia sẻ?
- Có phụ thuộc thời gian hoặc trạng thái ngoài khiến cùng input cho kết quả khác nhau?

**Lỗi và vận hành**
- Invalid input có exception thích hợp?
- Lỗi hạ tầng có bị ngụy trang thành lỗi dữ liệu?
- Binding error có giữ field path để hiển thị?
- Log/metrics có tránh raw PII và cardinality cao?
- Có unit test valid/invalid/boundary/concurrency và integration test binder?

Một converter đạt chất lượng là converter có hành vi rõ, dễ dự đoán, không che giấu business workflow và không làm tăng chi phí hệ thống ngoài mức cần thiết.

## 16. Ghi nhớ và tài liệu chính thức

- `ConversionService`/converter có thể được dùng chung; converter cần stateless và thread-safe.
- Chi phí cần nhìn cả CPU, allocation, GC, lookup, contention, I/O và logging.
- Không nên đặt database write, event publish hoặc remote API call trong converter; chuyển thành value object rồi xử lý ở service.
- `canConvert` phản ánh khả năng theo kiểu, không bảo đảm từng element hoặc từng giá trị thực tế đều convert thành công.
- Invalid input thường dùng unchecked exception như `IllegalArgumentException`; Spring có thể bao bọc thành `ConversionFailedException`.
- Trong property binding, lỗi chuyển đổi thường được ánh xạ thành `FieldError` mã `typeMismatch`; controller cần đọc `BindingResult` trước khi gọi nghiệp vụ.
- Benchmark bằng JMH và production telemetry; không dùng một lần `System.nanoTime` để kết luận.
- Tránh log raw input và metric tag có cardinality cao.

Tài liệu tham khảo:

- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): converter contract, stateless ConversionService và cách cấu hình.
- [Spring Framework — ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html): `canConvert`, `convert` và chuyển đổi collection/map.
- [Spring Framework — Converter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html): contract và yêu cầu với converter.
- [Spring Framework — GenericConversionService source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java): tra cứu, cache converter và chuyển lỗi.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): conversion trong property binding và BindingResult.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark JVM khi cần đo microbenchmark đáng tin cậy.
