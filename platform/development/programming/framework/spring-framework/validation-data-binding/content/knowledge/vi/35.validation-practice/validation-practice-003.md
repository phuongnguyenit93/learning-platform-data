# Xây dựng DTO bất biến bằng constructor binding trong Spring MVC

## 1. Bài toán thực hành và kết quả cần đạt

Một endpoint nhận thông tin đặt phòng qua `application/x-www-form-urlencoded`:

```http
POST /api/bookings
Content-Type: application/x-www-form-urlencoded

guest-name=Mai&
guest-count=2&
arrival=2026-11-20&
contact.email=mai@example.com
```

Ta muốn Spring MVC tạo một **request DTO bất biến** mà không cần:
- Constructor rỗng.
- Setter public cho mọi field.
- Gọi `new` DTO trong controller.
- Copy một loạt thuộc tính từ form sang domain entity.
- Cho client thay đổi `ownerId`, `approved` hoặc các thuộc tính chỉ server được quyết định.

Ví dụ DTO đích:

```java
public record BookingForm(
        String guestName,
        Integer guestCount,
        LocalDate arrival,
        Contact contact) {

    public record Contact(String email) {}
}
```

**Đầu ra mong đợi:** Spring dùng các tên input tương ứng với tham số constructor để tạo `BookingForm` và `Contact`; `guestCount` được convert từ String thành Integer, `arrival` thành LocalDate. Sau đó Jakarta Validation kiểm tra các constraints. Toàn bộ public state của record được đọc qua accessors, không sửa qua setter.

**Nhưng bất biến không đồng nghĩa an toàn tuyệt đối.** Một record có thể chứa `List`/`Map` mutable; constructor binding vẫn nhận mọi tham số được khai báo; `@BindParam` chỉ ánh xạ tên, không tự cấm field độc hại; không có `BindingResult` thì errors có thể đi qua global advice. Bài này xử lý đầy đủ các sắc thái đó.

**Mục tiêu:**

1. Hiểu sự khác nhau giữa **constructor binding** và **property/setter binding** trong Spring MVC.
2. Dùng Java 17 `record` hoặc class với một public constructor và các `final` fields.
3. Ánh xạ tên form bằng `@BindParam`, gồm tên chứa dấu gạch nối.
4. Dùng `@InitBinder` và `WebDataBinder#setDeclarativeBinding(true)` để tránh property binding ngoài chủ ý.
5. Bind DTO lồng nhau, parse ngày, validate `@NotBlank`/`@NotNull`/`@Min`/`@Max`/`@Email` bằng `@Valid`.
6. Tách **binding/conversion error** khỏi **Bean Validation violation** qua `BindingResult`.
7. Hiểu vì sao constructor binding không mặc nhiên **reject unknown HTTP parameters**.
8. Phân biệt form/query `@ModelAttribute` với JSON `@RequestBody` qua Jackson.
9. Viết dự án hoàn chỉnh Java 17 + Spring Boot 3.5.6 với MockMvc tests cho happy path, lỗi và bảo mật.
10. Biết khi nào cần DTO chuyên biệt, defensive copy, kiểm tra authorization và giới hạn collection.

**Bối cảnh:** module *Spring Framework - validation-data-binding*, nhóm *Thực hành*. Chủ đề trực tiếp là **xây dựng DTO bất biến bằng constructor binding**, không phải tutorial tổng quát về JPA hoặc Jackson. Các ví dụ chính chạy trên Spring MVC Servlet stack, Spring Framework 6.2.x, Jakarta Validation và Java 17.

## 2. Hai con đường để DataBinder tạo/điền object

### 2.1. Property binding truyền thống

DTO JavaBean mutable:

```java
public class BookingBean {
    private String guestName;
    private Integer guestCount;

    public BookingBean() {}

    public void setGuestName(String guestName) {
        this.guestName = guestName;
    }

    public void setGuestCount(Integer guestCount) {
        this.guestCount = guestCount;
    }

    public String getGuestName() { return guestName; }
    public Integer getGuestCount() { return guestCount; }
}
```

Spring có thể:
1. Khởi tạo đối tượng bằng constructor mặc định.
2. Tìm tên request fields phù hợp với bean properties.
3. Convert String values.
4. Gọi setters.
5. Chạy validator khi có `@Valid`/`@Validated`.

Nhược điểm khi dùng trực tiếp một domain entity: client có thể gửi các tên property mà UI không hiển thị, như `approved`, `role`, `ownerId`, nested objects hoặc indexed collections. Nếu có setter tương ứng và policy không chặn, đây là **mass assignment/over-posting**.

### 2.2. Constructor binding

Với DTO bất biến:

```java
public record BookingForm(String guestName, Integer guestCount) {}
```

Spring MVC có thể:
1. Xác định primary/data constructor.
2. Tìm request values theo **constructor parameter names**.
3. Convert từng value vào kiểu constructor argument.
4. Gọi constructor để tạo một instance hoàn chỉnh (nếu construction khả thi).
5. Validate object sau binding.

Không có bước bắt buộc gọi setter cho record.

**Lưu ý chính xác:** Spring MVC mặc định có thể thực hiện **cả constructor binding lẫn property binding**. Chỉ vì một model có constructor không có nghĩa Spring tự tắt setter binding cho các đối tượng khác. Spring Framework 6.1+ hỗ trợ `setDeclarativeBinding(true)` để giới hạn việc bind vào constructor arguments và những property fields đã explicit allowlist. <Cite ref="turn890037search0"/>

### 2.3. Bảng so sánh

| Tiêu chí | Constructor binding | Property binding |
| --- | --- | --- |
| Input ánh xạ theo | Tham số constructor | Bean properties/setters |
| Object cần no-arg constructor? | Không; cần data constructor phù hợp | Thường có |
| DTO có thể dùng Java `record`? | Có | Record không cung cấp setter thông thường |
| Khi nào state được thiết lập? | Khi tạo object | Sau khi object đã tồn tại |
| Hỗ trợ nested objects? | Có, recursive constructor binding | Có, nested paths/getters/setters |
| Hỗ trợ List/Map? | Có, qua constructor arguments/indexed keys | Có, qua bean property paths |
| `@BindParam` đổi tên input? | Có, dùng cho constructor argument/field | Không tự biến thành setter property mapping |
| `allowedFields` giới hạn gì? | Không là allowlist của constructor args | Giới hạn property binding |
| Ưu tiên bảo mật | DTO constructor chỉ chứa trường công khai | Phải đặt allowlist chặt cho fields được phép |
| Chẩn đoán lỗi | BindingResult + validation | BindingResult + validation |

**Điểm khó nhưng quan trọng:** Giới hạn setter binding không thể chặn một tham số nhạy cảm mà bạn đã khai báo trong constructor. Để tránh nhận `role` hoặc `approved` từ client, **đừng đặt chúng trong request constructor**.

## 3. Java 17 record — một DTO bất biến ở mức tham chiếu

```java
public record BookingForm(
        String guestName,
        Integer guestCount) {}
```

Compiler cung cấp:
- `private final` fields cho record components.
- Canonical constructor với đúng các components.
- Accessors `guestName()` và `guestCount()`.
- `equals`, `hashCode`, `toString` dựa trên components.

Sử dụng:

```java
BookingForm input = new BookingForm("Mai", 2);

System.out.println(input.guestName());
System.out.println(input.guestCount());
```

Stdout:

```text
Mai
2
```

Không có `setGuestName(...)`. Muốn “thay” giá trị cần tạo instance mới:

```java
BookingForm updated =
        new BookingForm(input.guestName(), 3);
```

Đây là ngữ nghĩa **bất biến** tại record fields. Nhưng:
- Record không tự validate giá trị; `new BookingForm("", -1)` vẫn có thể tạo object nếu constructor không kiểm tra.
- Nếu record chứa `List<String>` mutable, danh sách bên trong vẫn có thể bị thay đổi sau đó.
- Record có thể chứa mutable bean, byte array, Map, collection; phải thiết kế **deep immutability** khi cần.
- Record không tự xác thực quyền caller.
- Chỉ số lượng fields có setter ít hơn không tự ngăn mọi vấn đề deserialize của JSON.

### 3.1. Khi không thể dùng record

Một class bất biến thông thường:

```java
public final class GuestInput {

    private final String displayName;

    public GuestInput(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Với Spring constructor binding, class nên có một data constructor không mơ hồ và parameter names được giữ tại runtime, thường nhờ javac `-parameters`. Nếu có nhiều overload constructors hoặc no-arg constructor, framework có thể chọn đường khác theo quy tắc của version. Với Java records, canonical components rõ ràng hơn và thường là lựa chọn thuận tiện cho request DTO ngắn.

Đây là **fragment** minh họa; các file runnable ở phần 12.

## 4. Tên constructor argument và `@BindParam`

Một web form có tên legacy/kebab-case:

```text
guest-name=Mai
guest-count=2
```

Trong Java, record component là `guestName` và `guestCount`. Có thể dùng:

```java
import org.springframework.web.bind.annotation.BindParam;

public record BookingForm(
        @BindParam("guest-name") String guestName,
        @BindParam("guest-count") Integer guestCount) {}
```

Spring MVC 6.1+ hỗ trợ `@BindParam` trên constructor parameter hoặc field tương ứng để map tên input. Với Java record, annotation có `PARAMETER`/`FIELD` target và có thể được gắn lên component trong source, sau đó compiler chuyển nó đến những program elements hỗ trợ. <Cite ref="turn129063view0"/>

**Kết quả:**
- `guest-name` từ form ánh xạ vào constructor argument `guestName`.
- `guest-count` ánh xạ vào `guestCount`.
- Không có nghĩa `guestName` và `guest-name` được chấp nhận song song.
- Không có nghĩa Jackson sẽ xem `@BindParam` là `@JsonProperty`.

### 4.1. Compiler parameter metadata

Đối với ordinary immutable classes, thêm cấu hình:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Sự lựa chọn này giúp lưu runtime method/constructor parameter names (`-parameters`). Nếu mất metadata, framework có thể không xác định đúng input names khi constructor binding. Test build bằng Java 17 và đúng Maven compiler configuration.

### 4.2. `DataBinder.NameResolver` cho naming scheme riêng

Spring hỗ trợ đặt `DataBinder.NameResolver` để custom mapping phức tạp hơn `@BindParam`. Đây là cơ chế nâng cao, không cần cho dự án demo. Chỉ nên dùng nếu toàn module có quy ước tên field cần giải quyết nhất quán; có thể phải xem kỹ nested paths, aliases, canonicalization và security. Không tự tạo một resolver đọc toàn bộ request rồi âm thầm map mọi unknown field.

## 5. `setDeclarativeBinding(true)` — chỉ bind những gì được khai báo

Cấu hình controller:

```java
@InitBinder("bookingForm")
void bindConstructorOnly(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Spring Framework 6.1+:
- `false` (mặc định): có thể bind constructor và property fields.
- `true`: constructor binding vẫn chạy; setter/property binding **không chạy trừ khi** `allowedFields` được cấu hình.

Ví dụ legacy model có một public constructor `email` và một setter `setApproved(boolean)`. Nếu `setDeclarativeBinding(true)` và không thêm `allowedFields("approved")`, client gửi `approved=true` **không được dùng để gọi setter đó trong property binding**.

Điều này bổ sung cho record, nhưng không thay thiết kế input model: một request DTO nên **không** chứa privileged properties trong constructor. <Cite ref="turn890037search0"/>

### 5.1. Cạm bẫy: cấu hình `setAllowedFields` có thể bật lại property binding

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");
```

Trong chế độ declarative, setter binding có thể diễn ra **cho những properties được allowlist**. Đừng dùng `setAllowedFields("*")` vì nó loại bỏ phần lớn ý nghĩa bảo vệ setter surface.

Đối với một constructor-only DTO, cấu hình đơn giản nhất là:

```java
binder.setDeclarativeBinding(true);
```

và **không** khai báo `allowedFields` nếu không cần setter binding.

### 5.2. `allowedFields` không lọc constructor arguments

Giả sử bạn khai báo:

```java
public record UnsafeForm(
        String displayName,
        boolean approved,
        String ownerId) {}
```

Dù dùng:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");
```

điều đó **không tự bảo đảm** constructor arguments `approved` và `ownerId` bị bỏ qua. Chúng là một phần data constructor, còn `allowedFields` kiểm soát **property binding**. Đúng cách là loại chúng khỏi request constructor và để server xác định owner/approval.

### 5.3. `setIgnoreUnknownFields(false)` có phải lời giải cho unknown input?

Không. `DataBinder#setIgnoreUnknownFields(boolean)` chủ yếu áp dụng cho **property binding** qua `bind(PropertyValues)`; nó không biến `construct(ValueResolver)` thành bộ lọc mọi HTTP keys. Constructor binder lấy những giá trị nó cần để tạo constructor arguments; input ngoài danh sách có thể không được dùng và không tạo `FieldError` hay `suppressedFields`. <Cite ref="turn890037search8"/>

Nếu API yêu cầu **từ chối toàn bộ unknown parameters**, hãy thiết kế kiểm tra raw parameter names/schema trước khi tác động domain, hoặc một boundary parser có policy riêng. Bài demo có một endpoint strict minh họa điều đó.

## 6. Nested record: constructor binding đệ quy

DTO:

```java
public record BookingForm(
        String guestName,
        Contact contact) {

    public record Contact(String email) {}
}
```

Request:

```text
guestName=Mai
contact.email=mai@example.com
```

Với Spring MVC constructor binding, nếu constructor argument `contact` là một object và có thông tin nested path, framework có thể tạo `Contact` qua constructor tương ứng. Dữ liệu cuối cùng:

```java
booking.contact().email()
```

**Không cần setter** `setContact` hoặc `setEmail`. Tuy vậy nên dùng `@Valid`/`@NotNull` đúng vị trí nếu cần bảo đảm nested data thực sự hợp lệ.

### 6.1. Jakarta Validation trên record components

```java
public record BookingForm(
        @NotBlank String guestName,
        @NotNull @Valid Contact contact) {

    public record Contact(
            @NotBlank @Email String email) {}
}
```

- `@NotBlank` từ chối null/empty/blank trên `guestName`.
- `@NotNull` từ chối thiếu `contact`.
- `@Valid` kích hoạt cascade validation vào `Contact`.
- `@Email` kiểm tra định dạng email nhưng không bảo đảm non-null/nonblank; kết hợp `@NotBlank`.
- `@Valid` **không tự cấm null**: cần `@NotNull` khi bắt buộc có object con.

Không nhầm binding với validation. Khi `contact.email` không có hoặc sai kiểu, Spring có thể tạo Contact với `email=null` rồi validator mới phát hiện `@NotBlank`; khi conversion trước constructor thất bại, `BindingResult` có thể chứa type mismatch.

## 7. Type conversion khi gọi constructor

Request từ form đều là text:
- `guest-count=2`: `String` → `Integer`.
- `arrival=2026-11-20`: `String` → `LocalDate`.
- `contact.email=mai@example.com`: `String` → `String`.

Record đầy đủ trong demo có:

```java
@NotNull
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate arrival
```

Đây là **Spring formatting annotation**, không phải constraint Jakarta Validation. Nó yêu cầu parsing ngày ISO ở đường `@ModelAttribute`/Spring `ConversionService`. Request `arrival=20/11/2026` không theo ISO nên là **binding/conversion problem**, chưa phải lỗi của `@NotNull` hay `@Past`.

### 7.1. Vì sao dùng wrapper `Integer` thay `int`?

`Integer` có thể biểu diễn null khi input thiếu, nên `@NotNull` có thể phát hiện thiếu `guest-count`. Primitive `int` không biểu diễn null; nếu constructor nhận primitive nhưng converter không có value, framework cần quyết định xử lý argument thiếu và exception có thể khác.

Để phân biệt **missing field** với **numeric 0**, sử dụng `Integer` cùng `@NotNull` và `@Min(1)`.

### 7.2. Phân biệt input sai kiểu với vi phạm constraint

Với `guest-count`:
- `2`: parse thành Integer 2; constraints pass.
- `0`: parse thành Integer 0; `@Min(1)` fail.
- `abc`: conversion String→Integer fail; binder báo `typeMismatch`.
- Không gửi: giá trị có thể là null; `@NotNull` fail nếu object được dựng.

Một test chỉ assert HTTP 400 không cho biết loại lỗi đã xảy ra. Test cần phân biệt code `BINDING_ERROR`/`VALIDATION_ERROR` và các field issues.

## 8. `BindingResult` và cách bảo toàn lỗi từ constructor

Controller có thể xử lý lỗi tại chỗ:

```java
@PostMapping("/bookings")
public ResponseEntity<?> book(
        @Valid @ModelAttribute("bookingForm") BookingForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(ApiError.fromBindingResult(errors));
    }

    // Chỉ tiếp tục khi object hợp lệ.
}
```

**Vị trí `BindingResult` bắt buộc ngay sau** argument được bind/validate. Nếu không có nó, Spring MVC thường ném `MethodArgumentNotValidException` cho binding/validation errors, và global `@RestControllerAdvice` cần xử lý.

`BindingResult` có:
- `getFieldErrors()`: field-level problems.
- `FieldError.getField()`: path của field.
- `FieldError.isBindingFailure()`: true khi lỗi conversion/binding.
- `getGlobalErrors()`: object-level validation.
- `getSuppressedFields()`: những fields bị suppress bởi property binding policy, không phải bộ kiểm unknown keys toàn cục.

**Constructor binding caveat:** Nếu một constructor không thể tạo target vì lỗi construction nghiêm trọng (exception từ chính constructor, không có constructor được chọn, hoặc vấn đề metadata), request có thể thất bại trước handler với exception khác. `BindingResult` không cam kết biến **mọi runtime exception** thành field errors. Tránh đặt logic I/O hay ném business exceptions không cần thiết trong constructor DTO.

### 8.1. Không nhất thiết chỉ có một lỗi trên một field

Với `guest-count=abc`, binder có type mismatch. Tùy cơ chế xử lý, validator còn có thể nhìn thấy null hoặc error khác. Đừng viết test cứng rằng `issues.length==1` cho mọi kiểu conversion failure nếu hợp đồng không cam kết điều đó.

Thay vào đó:
- Assert `code=="BINDING_ERROR"` khi có `isBindingFailure()==true`.
- Assert danh sách có issue field liên quan và issue code `typeMismatch`.
- Khi cần hiển thị nhiều lỗi, giữ tất cả issues thay vì chỉ một String cuối cùng.

### 8.2. Hợp đồng lỗi ví dụ

```json
{
  "code": "BINDING_ERROR",
  "issues": [
    {
      "field": "guestCount",
      "code": "typeMismatch",
      "category": "binding"
    }
  ]
}
```

Đây là **schema ứng dụng** trong project demo, không phải body Spring MVC mặc định. Với alias `guest-count`, field path trong `BindingResult` có thể được đặt theo constructor argument hoặc binding name tùy đường xử lý; vì thế test tập trung vào mã `typeMismatch` và semantics, không tự đoán chính tả field path trong mọi version.

## 9. Constructor binding với List, Map và array

Spring hỗ trợ constructor arguments là List/Map/array thông qua giá trị đơn (ví dụ chuỗi phân tách) hoặc indexed paths như `rooms[0].code`, `labels[color]`. <Cite ref="turn615564search0"/>

Ví dụ record **minh họa**:

```java
public record BatchInput(
        @Size(min = 1, max = 3)
        List<@Valid RoomInput> rooms,
        Map<String, String> labels) {}

public record RoomInput(
        @NotBlank String code) {}
```

Request:

```text
rooms[0].code=A101
rooms[1].code=A102
labels[color]=blue
```

Spring có thể dựng nested collection objects qua constructor binding; nhưng các vấn đề cần thiết kế:
1. **Index quá lớn hoặc quá thưa**: không cho input tự khiến object graph phình ra.
2. **Map keys tùy ý**: `labels[role]` có thể tạo metadata trái policy nếu constructor chấp nhận Map.
3. **Mutable collection references**: record chứa List/Map không tự làm phần tử hoặc collection bất biến.
4. **`@Size(max=3)` sau binding**: không thay giới hạn request size, parser depth hoặc resource cap sớm.
5. **Duplicate field names**: cần chính sách cụ thể khi cùng tên input xuất hiện nhiều lần.
6. **Nested `@Valid`**: cascade từng phần tử nếu cần, thêm `@NotNull` cho element khi null bị cấm.
7. **Security ownership**: không dùng Map keys thay cho quyền caller.

**Không chạy trực tiếp snippet này trong project ở phần 12**; đây là hướng mở rộng để học viên thực hành. Mã cần imports `java.util.List`/`Map`, `jakarta.validation.Valid`/`constraints` và lựa chọn giới hạn theo nghiệp vụ.

### 9.1. Shallow immutability và defensive copy

Một record:

```java
public record Names(List<String> values) {}
```

không bảo vệ danh sách truyền vào:

```java
List<String> input = new ArrayList<>();
input.add("Mai");
Names names = new Names(input);
input.add("Lan");
System.out.println(names.values().size()); // 2
```

Muốn chặn sửa collection qua reference ngoài:

```java
public record Names(List<String> values) {
    public Names {
        if (values != null) {
            values = List.copyOf(values);
        }
    }
}
```

Khi `values` là nonnull và tất cả phần tử nonnull, `List.copyOf` tạo list unmodifiable snapshot. Nếu input có phần tử null, `List.copyOf` ném `NullPointerException` **trước validation**. Không áp dụng mù quáng với form binder có thể tạm tạo sparse list/null elements: thiết kế có chính sách null/size sớm và test. Nếu phải giữ null tạm để validator phát hiện, có thể chọn chiến lược copy cho phép null nhưng không expose mutable state.

**Sự khác nhau:** defensive copy bảo vệ **immutability sau khi object tồn tại**. Nó không thay input allowlist, bound/size limits hoặc service authorization.

## 10. Đối chiếu JSON `@RequestBody`: Jackson không dùng `@BindParam`

Hai endpoint có thể cùng nhận một record:

```java
@PostMapping(path="/bookings/form",
             consumes="application/x-www-form-urlencoded")
public void fromForm(@ModelAttribute BookingForm form) {}

@PostMapping(path="/bookings/json",
             consumes="application/json")
public void fromJson(@RequestBody BookingForm form) {}
```

Trong form binding:
- Spring MVC/WebDataBinder dùng constructor metadata.
- `@BindParam("guest-name")` xác định request form field name.

Trong JSON:
- Jackson/`HttpMessageConverter` deserialize JSON theo schema của Jackson.
- Tên property mặc định của record là `guestName`, không phải `guest-name`.
- `@BindParam` không thay thế `@JsonProperty("guest-name")`.
- `WebDataBinder#setDeclarativeBinding(true)` không tự điều khiển Jackson JSON deserialization, dù Spring có thể dùng binder để chạy validation sau decode.

JSON phù hợp:

```json
{
  "guestName": "Mai",
  "guestCount": 2,
  "arrival": "2026-11-20",
  "contact": {"email": "mai@example.com"}
}
```

Form tương đương:

```text
guest-name=Mai
guest-count=2
arrival=2026-11-20
contact.email=mai@example.com
```

**Khuyến nghị:** Nếu hợp đồng JSON và form khác nhau hoặc phát triển độc lập, tạo **request DTO riêng cho từng content type**. Đừng làm cả API phụ thuộc một record vừa mang Spring form annotations vừa mang Jackson annotations nếu nó khiến naming và backward compatibility khó hiểu.

## 11. Bảo mật thực hành: bỏ fields có quyền cao khỏi input constructor

Giả sử model/domain có:

```java
public class Booking {
    private UUID id;
    private UUID ownerId;
    private boolean approved;
    private String guestName;
    // ...
}
```

Đây là **fragment domain** không nằm trong project runnable. Tuyệt đối không bind request vào entity rồi save chỉ vì có constructor:

```java
// Anti-pattern:
repository.save(boundEntity);
```

Đúng hơn:

```java
BookingForm input = ...;          // chỉ các public input fields
UUID owner = currentPrincipalId(); // từ authenticated context

Booking entity = new Booking(
        generatedId(), owner, false,
        input.guestName(), input.guestCount());
```

Đoạn trên là **pseudo-flow**, không có đầy đủ definitions. Mấu chốt: server tự xác định `ownerId`, `approved` và business state, kiểm tra quyền caller, rồi map chính xác những field cho phép.

### 11.1. Tại sao không chỉ dựa vào `getSuppressedFields()`?

Với property binding có allowed/disallowed fields, `BindingResult.getSuppressedFields()` cho biết một số names bị chặn. Với constructor binding, binder chỉ lấy constructor arguments cần thiết; một unknown parameter như `approved=true` có thể bị **bỏ qua** chứ không tự ghi vào suppressed fields. `hasErrors()==false` không chứng minh request không chứa unknown names.

Nếu contract yêu cầu trả 400 cho unknown form field, hãy có **schema-aware raw parameter name check**, và test riêng. Cần xác định đúng tên alias `guest-name`, `guest-count`, nested `contact.email`, không trộn với JSON property names.

### 11.2. “Strict” chỉ là policy của endpoint

Dự án mẫu có hai lựa chọn:
- `POST /api/bookings`: constructor-only, **bỏ qua** unknown request field vì nó không phải constructor argument; không gán vào DTO/domain.
- `POST /api/bookings/strict`: tự kiểm tra `HttpServletRequest.getParameterMap().keySet()` theo allowlist của **form parameters** và trả `UNEXPECTED_FIELD` nếu có key khác.

**Giới hạn:** Kiểm tra raw form/query parameter keys không thay policy cho các nguồn khác mà `@ModelAttribute` có thể nhìn thấy (URI variables, header names được MVC chuẩn hóa). Với endpoint strict từ external clients, kiểm tra schema của **tất cả input sources** theo hợp đồng endpoint hoặc dùng một request decoding layer có policy rõ ràng. Không suy “chỉ kiểm param map là đủ để chống mọi đường đi”.

## 12. Dự án hoàn chỉnh Java 17 + Spring Boot 3.5.6

Ví dụ dưới tập trung thực hành với hai mô hình:
- `BookingForm`: **record**, có `@BindParam`, nested record, type conversion và validation.
- `AccessChangeForm`: **class mutable có public constructor + setter nguy hiểm giả định**. `setDeclarativeBinding(true)` chứng minh setter `approved` không bị bind.

Không dùng DB, credentials hay network ngoài localhost. `BookingController` chỉ tạo response view, không persist. API sản phẩm thực cần service/domain/authorization ngoài bước binding.

### 12.1. Cấu trúc thư mục

```text
immutable-constructor-demo/
├── pom.xml
├── src/main/java/demo/immutable/
│   ├── ImmutableDtoApplication.java
│   ├── BookingForm.java
│   ├── AccessChangeForm.java
│   ├── ApiError.java
│   ├── BookingController.java
│   └── ApiExceptionHandler.java
└── src/test/java/demo/immutable/
    ├── BookingFormMvcTest.java
    ├── BookingSecurityMvcTest.java
    ├── BookingJsonMvcTest.java
    └── ImmutableRecordTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>immutable-constructor-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>maven-compiler-plugin</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Các dependencies:**
- `spring-boot-starter-web`: MVC + Jackson.
- `spring-boot-starter-validation`: Jakarta Validation provider.
- `spring-boot-starter-test`: Spring Test MockMvc và JUnit Jupiter.
- Compiler `-parameters`: lưu parameter names cho các constructor thông thường; vẫn hữu ích khi demo có class thay vì chỉ record.

Chú ý cấu hình plugin Maven ở trên: `groupId` của `maven-compiler-plugin` phải là **`org.apache.maven.plugins`**, không phải `maven-compiler-plugin`. Tệp `pom.xml` đầy đủ cần dùng giá trị đúng như sau:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Đoạn cấu hình chuẩn này **thay thế** block compiler plugin trong listing POM ở trên khi tạo file thực tế. Không để hai plugin entries cho cùng artifact. Đây là điểm cần lưu ý khi chép code vào project: POM phải dùng groupId chuẩn để Maven resolution nhất quán.

### 12.3. `ImmutableDtoApplication.java`

```java
package demo.immutable;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImmutableDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImmutableDtoApplication.class, args);
    }
}
```

### 12.4. `BookingForm.java`

```java
package demo.immutable;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.BindParam;

import java.time.LocalDate;

public record BookingForm(

        @BindParam("guest-name")
        @NotBlank(message = "guestName.required")
        String guestName,

        @BindParam("guest-count")
        @NotNull(message = "guestCount.required")
        @Min(value = 1, message = "guestCount.min")
        @Max(value = 8, message = "guestCount.max")
        Integer guestCount,

        @NotNull(message = "arrival.required")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate arrival,

        @NotNull(message = "contact.required")
        @Valid
        Contact contact) {

    public record Contact(
            @NotBlank(message = "contact.email.required")
            @Email(message = "contact.email.invalid")
            String email) {
    }
}
```

Mã tập trung vào dữ liệu client được phép nhập. Không có `ownerId`, `admin` hay `approved`.

**Vì sao `@BindParam` xuất hiện trên record components?** Java compiler có thể phát annotation với target `PARAMETER`/`FIELD` lên các phần tương ứng của record; Spring tìm binding name ở constructor parameter/field. Đây là cách tránh phụ thuộc naming convention của browser/client cho các trường có dấu gạch nối.

### 12.5. `AccessChangeForm.java` — chứng minh declarative binding

```java
package demo.immutable;

public final class AccessChangeForm {

    private final String displayName;

    // Setter giả định có thể bị over-post nếu bật property binding.
    private boolean approved;

    public AccessChangeForm(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
```

**Đây là DTO cố tình có setter nhạy cảm để kiểm thử**, không phải thiết kế đề xuất cho hệ thống thật. DTO production không nên expose setter `approved` ở input model; việc bật declarative constructor-only binding giúp tạo thêm lớp phòng vệ khi legacy class vẫn còn setter này.

### 12.6. `ApiError.java`

```java
package demo.immutable;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record ApiError(
        String code,
        List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String category) {
    }

    public static ApiError simple(String code) {
        return new ApiError(code, List.of());
    }

    public static ApiError fromBindingResult(BindingResult errors) {
        List<Issue> issues = errors.getFieldErrors().stream()
                .map(e -> new Issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.toString(e.getCode(), "invalid"),
                        e.isBindingFailure()
                                ? "binding" : "constraint"))
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code)
                        .thenComparing(Issue::category))
                .toList();

        boolean hasBinding = errors.getFieldErrors().stream()
                .anyMatch(FieldError::isBindingFailure);

        return new ApiError(
                hasBinding ? "BINDING_ERROR" : "VALIDATION_ERROR",
                issues);
    }
}
```

Ứng dụng chọn mã lỗi ổn định:
- `BINDING_ERROR` khi có ít nhất một `FieldError.isBindingFailure()==true`.
- `VALIDATION_ERROR` khi chỉ có violations từ validator.
- `UNEXPECTED_FIELD` nếu strict endpoint phát hiện parameter name không được phép.
- `BODY_UNREADABLE` khi Jackson không đọc được JSON body.

Trong sản phẩm thực, bổ sung object-level errors từ `getGlobalErrors()` nếu có custom cross-field/class-level validator. Demo không định nghĩa object-level constraint, nên `getFieldErrors()` là đủ cho các test hiện có. Không trả raw rejected values hoặc exception internals cho client.

### 12.7. `BookingController.java`

```java
package demo.immutable;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Set;

@RestController
@RequestMapping("/api")
public class BookingController {

    // Chỉ khai báo public input names, gồm @BindParam aliases.
    private static final Set<String> FORM_FIELDS = Set.of(
            "guest-name", "guest-count",
            "arrival", "contact.email");

    @InitBinder({"bookingForm", "accessChangeForm"})
    void constructorOnly(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    public record BookingView(
            String guestName,
            Integer guestCount,
            String arrival,
            String email) {
    }

    public record AccessView(
            String displayName,
            boolean approved) {
    }

    private static BookingView view(BookingForm form) {
        return new BookingView(
                form.guestName(),
                form.guestCount(),
                form.arrival().toString(),
                form.contact().email());
    }

    @PostMapping(path = "/bookings",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> createForm(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/strict",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> createStrictForm(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form,
            BindingResult errors,
            HttpServletRequest request) {

        // Boundary rule cho endpoint form/query này, không phải
        // chức năng tự động của constructor binding.
        boolean unknownInput =
                request.getParameterMap().keySet().stream()
                        .anyMatch(key -> !FORM_FIELDS.contains(key));

        if (unknownInput) {
            return ResponseEntity.badRequest()
                    .body(ApiError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/advice",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<BookingView> createWithAdvice(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form) {

        // Không có BindingResult: global advice sẽ xử lý
        // lỗi binding/validation bằng MethodArgumentNotValidException.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookingView> createJson(
            @Valid @RequestBody BookingForm form) {

        // Jackson tạo record từ JSON; @BindParam thuộc MVC form
        // constructor binding chứ không phải tên JSON properties.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/access",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<AccessView> access(
            @ModelAttribute("accessChangeForm")
            AccessChangeForm form) {

        return ResponseEntity.ok(
                new AccessView(
                        form.getDisplayName(),
                        form.isApproved()));
    }
}
```

**Giải thích rõ từng route:**
- `/bookings`: dùng constructor binding + `BindingResult` local; unknown names có thể bị bỏ qua mà không sửa state.
- `/bookings/strict`: có thêm allowlist của request form/query names, explicit reject unknown.
- `/bookings/advice`: không có `BindingResult`; exception đi qua global handler.
- `/bookings/json`: Jackson record deserialization; JSON dùng camelCase properties.
- `/access`: chứng minh `setDeclarativeBinding(true)` chặn setter `setApproved` trong property binding của legacy class.

**Giới hạn bảo mật của `/bookings/strict`:** Ví dụ này kiểm tra `HttpServletRequest` parameter map của endpoint form, không biến thành một generic firewall cho mọi header/path/session attribute. Production phải bảo vệ mọi nguồn input và authorization tại service.

### 12.8. `ApiExceptionHandler.java`

```java
package demo.immutable;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                ApiError.fromBindingResult(ex.getBindingResult()),
                headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                ApiError.simple("BODY_UNREADABLE"),
                headers, status);
    }
}
```

Đây là phần **global error contract** dành cho đường không có BindingResult và lỗi Jackson trong demo. Không tự thêm một `@ExceptionHandler(MethodArgumentNotValidException.class)` cùng superclass đã handle loại này; override protected method để tránh ambiguous mappings.

Nếu application có direct `@Min` trên handler parameter hoặc constraint trên return value (Spring MVC 6.1+ built-in method validation), hãy bổ sung `handleHandlerMethodValidationException` tương ứng, giữ status 400/500 do framework quyết định. Bài demo tránh direct method constraints để tập trung constructor binding của DTO.

## 13. Kiểm thử MVC: record được tạo từ form như thế nào?

Tất cả các file dưới `src/test/java/demo/immutable`.

### 13.1. `BookingFormMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingFormMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder valid(String path) {
        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("guest-name", "Mai")
                .param("guest-count", "2")
                .param("arrival", "2026-11-20")
                .param("contact.email", "mai@example.com");
    }

    @Test
    void recordIsConstructedFromFormFields() throws Exception {
        mvc.perform(valid("/api/bookings"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.guestCount").value(2))
                .andExpect(jsonPath("$.arrival")
                        .value("2026-11-20"))
                .andExpect(jsonPath("$.email")
                        .value("mai@example.com"));
    }

    @Test
    void bindParamAliasesUseKebabCaseNames() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guestName", "IgnoredValue"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"));
    }

    @Test
    void missingGuestNameViolatesNotBlank() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-count", "2")
                        .param("arrival", "2026-11-20")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void blankGuestNameViolatesNotBlank() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guest-name", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void missingGuestCountIsNotNullViolation() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-name", "Mai")
                        .param("arrival", "2026-11-20")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }

    @Test
    void zeroGuestCountIsMinViolationNotTypeMismatch()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Min")));
    }

    @Test
    void nineGuestsExceedsMax() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "9"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Max")));
    }

    @Test
    void nonNumericGuestCountIsBindingError()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void wrongDatePatternIsBindingError() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("arrival", "20/11/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void missingNestedContactViolatesNotNull()
            throws Exception {

        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-name", "Mai")
                        .param("guest-count", "2")
                        .param("arrival", "2026-11-20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }

    @Test
    void invalidNestedEmailFailsCascadeValidation()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("contact.email", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("contact.email")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Email")));
    }

    @Test
    void blankNestedEmailViolatesNotBlank() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("contact.email", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void noBindingResultUsesGlobalAdvice() throws Exception {
        mvc.perform(valid("/api/bookings/advice")
                        .param("guest-count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void noBindingResultSuccessStillReturns201()
            throws Exception {

        mvc.perform(valid("/api/bookings/advice"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestCount").value(2));
    }
}
```

**Ý nghĩa 14 test:**
- Spring tạo record từ constructor arguments (không có setters).
- `@BindParam` xử lý kebab-case form names.
- Constructor nested `Contact` được tạo và cascade `@Valid` vào email.
- `Integer` và `LocalDate` được convert.
- Missing/blank/out-of-range values tạo Bean Validation field violations.
- Text không convert được tạo binding failures.
- Có/không có `BindingResult` dẫn tới hai đường xử lý lỗi khác nhau.

Các cases chứa nhiều lỗi không assert đúng một issue duy nhất. Dùng `hasItem` để bảo đảm issue cần quan sát có mặt. `@Valid` không bảo đảm input construction luôn hoàn tất trong mọi trường hợp lỗi runtime; các tests này giới hạn loại malformed data mà Spring binder có thể phản ánh qua `BindingResult`.

## 14. Kiểm thử input ngoài hợp đồng và setter binding

### 14.1. `BookingSecurityMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingSecurityMvcTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request
            .MockHttpServletRequestBuilder form(String path) {

        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("guest-name", "Mai")
                .param("guest-count", "2")
                .param("arrival", "2026-11-20")
                .param("contact.email", "mai@example.com");
    }

    @Test
    void constructorBindingDoesNotSetUnknownApprovedField()
            throws Exception {

        mvc.perform(form("/api/bookings")
                        .param("approved", "true"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.approved").doesNotExist());
    }

    @Test
    void unknownFieldIsRejectedByExplicitStrictPolicy()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void strictEndpointAcceptsOnlyDeclaredFormKeys()
            throws Exception {

        mvc.perform(form("/api/bookings/strict"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"));
    }

    @Test
    void strictEndpointRejectsUnmappedCamelCaseAlias()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("guestName", "Extra"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void strictEndpointRejectsUnexpectedNestedProperty()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("contact.admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void legacySetterIsNotInvokedInDeclarativeMode()
            throws Exception {

        mvc.perform(post("/api/access")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Mai")
                        .param("approved", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName")
                        .value("Mai"))
                .andExpect(jsonPath("$.approved").value(false));
    }

    @Test
    void constructorArgumentStillWorksInDeclarativeMode()
            throws Exception {

        mvc.perform(post("/api/access")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.approved").value(false));
    }
}
```

Bộ test này chứng minh **hai chính sách khác nhau**: constructor binding **không dùng unknown field** và strict endpoint **từ chối unknown field**. Hai khái niệm không đồng nhất. Bài cũng kiểm tra rằng setter nguy hiểm trong `AccessChangeForm` không bị gọi khi bật `setDeclarativeBinding(true)`.

Cần lưu ý: test `$.approved` doesNotExist() ở BookingView **chỉ chứng minh response không lộ field đó**, không chứng minh mọi side effect đã không xảy ra. Vì controller demo không persist và DTO không chứa approved, điều này đủ cho ví dụ; hệ thống thật phải test service/database authorization.

## 15. Kiểm thử JSON: record immutable nhưng không phải MVC `@BindParam`

### 15.1. `BookingJsonMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingJsonMvcTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID = """
            {
              "guestName":"Mai",
              "guestCount":2,
              "arrival":"2026-11-20",
              "contact":{"email":"mai@example.com"}
            }
            """;

    @Test
    void jacksonCreatesRecordUsingJsonPropertyNames()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.guestCount").value(2));
    }

    @Test
    void jsonValidationStillChecksRecordConstraints()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"",
                                  "guestCount":0,
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"bad-email"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Min")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Email")));
    }

    @Test
    void malformedJsonIsBodyUnreadable() throws Exception {
        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"guestName\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void wrongJavaTypeInJsonIsUnReadable() throws Exception {
        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"Mai",
                                  "guestCount":{"wrong":true},
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"mai@example.com"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void jsonMissingGuestCountIsConstraintViolation()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"Mai",
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"mai@example.com"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }
}
```

**Kết luận JSON:** Jackson tạo được record và Jakarta Validation vẫn chạy sau đó, nhưng đó **không chứng minh Spring WebDataBinder constructor binding**. Tests JSON và form cần được tách, nhất là khi input names/cấu hình parser khác nhau.

## 16. Unit tests: record thật sự immutable ở phần state công khai

### 16.1. `ImmutableRecordTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Modifier;
import java.time.LocalDate;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ImmutableRecordTest {

    @Test
    void bookingFormIsAJavaRecord() {
        assertTrue(BookingForm.class.isRecord());
        assertTrue(Modifier.isFinal(
                BookingForm.class.getModifiers()));
    }

    @Test
    void recordHasNoPublicSetter() {
        boolean publicSetter = Arrays.stream(
                BookingForm.class.getMethods())
                .anyMatch(method ->
                        method.getName().startsWith("set")
                                && method.getParameterCount() == 1);

        assertFalse(publicSetter);
    }

    @Test
    void sameComponentsHaveValueSemantics() {
        var one = new BookingForm(
                "Mai", 2,
                LocalDate.of(2026, 11, 20),
                new BookingForm.Contact("mai@example.com"));

        var two = new BookingForm(
                "Mai", 2,
                LocalDate.of(2026, 11, 20),
                new BookingForm.Contact("mai@example.com"));

        assertEquals(one, two);
        assertEquals(one.hashCode(), two.hashCode());
    }

    @Test
    void directNewDoesNotAutomaticallyRunBeanValidation() {
        var input = new BookingForm("", 0, null, null);

        // @NotBlank/@Min/@NotNull được kiểm khi Validator chạy.
        // Constructor record mặc định chưa tự gọi Validator.
        assertEquals("", input.guestName());
        assertEquals(0, input.guestCount());
    }
}
```

Đây là test **không cần Spring context**, kiểm tra Java record:
- `isRecord()` và `final`.
- Không có public `setX`.
- Hai records cùng components có value equality.
- Jakarta Validation **không tự chạy chỉ vì dùng `new`**. Với API khác tạo object trực tiếp, cần gọi validator hoặc có domain invariant riêng.

**Không suy rằng thiếu setter = deep immutable.** Test ở phần 9.1 chỉ ra record có thể vẫn chứa mutable List và cần defensive copying.

## 17. Chạy dự án và kiểm tra kết quả

Dự án minh họa có:
- `BookingFormMvcTest`: 14 tests.
- `BookingSecurityMvcTest`: 7 tests.
- `BookingJsonMvcTest`: 5 tests.
- `ImmutableRecordTest`: 4 tests.

**Tổng cộng 30 `@Test` methods** theo listing. Đây là **kỳ vọng tĩnh từ đoạn mã**, không phải báo cáo Maven đã thực thi.

Tại thư mục `immutable-constructor-demo`:

```bash
mvn test
```

Chạy từng lớp:

```bash
mvn -Dtest=BookingFormMvcTest test
mvn -Dtest=BookingSecurityMvcTest test
mvn -Dtest=BookingJsonMvcTest test
mvn -Dtest=ImmutableRecordTest test
```

Chạy server:

```bash
mvn spring-boot:run
```

Các unit tests không cần service/database. MockMvc tests dùng `@SpringBootTest + @AutoConfigureMockMvc` để kiểm tra thật Spring MVC argument resolution/constructors/formatter/validator/advice trong mock servlet environment; đây **không phải HTTP network test**. Maven/Surefire report thực tế có thể xem ở `target/surefire-reports` sau khi chạy.

## 18. Thử bằng curl

### 18.1. Form hợp lệ

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Kỳ vọng HTTP **201 Created**:

```json
{
  "guestName": "Mai",
  "guestCount": 2,
  "arrival": "2026-11-20",
  "email": "mai@example.com"
}
```

### 18.2. `@BindParam` alias viết sai

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guestName=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Field `guestName` trong raw form không thay thế `guest-name` theo alias constructor. DTO có thể nhận `guestName=null`, rồi `@NotBlank` báo lỗi. Với route strict, input `guestName` còn bị **unknown parameter check** từ chối.

### 18.3. Sai kiểu số

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=abc' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Kỳ vọng HTTP 400, response category `BINDING_ERROR` với issue `typeMismatch`.

### 18.4. Vi phạm constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=0' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Kỳ vọng HTTP 400, category `VALIDATION_ERROR` với issue `Min`.

### 18.5. Extra field bị bỏ qua hoặc bị từ chối tùy endpoint

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'approved=true'
```

Route `/bookings`: extra form parameter không nằm trong DTO constructor nên không thành privileged state; trong demo được bỏ qua, request vẫn có thể trả 201.

Đổi path thành:

```text
http://localhost:8080/api/bookings/strict
```

thì chính sách của ứng dụng phát hiện unknown name và trả HTTP 400:

```json
{"code":"UNEXPECTED_FIELD","issues":[]}
```

Đây là lựa chọn **API contract**, không phải tính năng tự động của `@BindParam`.

### 18.6. JSON record qua Jackson

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings/json' \
  -H 'Content-Type: application/json' \
  --data-binary '{
    "guestName":"Mai",
    "guestCount":2,
    "arrival":"2026-11-20",
    "contact":{"email":"mai@example.com"}
  }'
```

Kỳ vọng HTTP 201 và cùng BookingView như form. JSON dùng **camelCase** của record components; không dùng `guest-name` chỉ vì constructor form có `@BindParam`.

## 19. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `@ModelAttribute` record toàn null | Constructor parameter names/`@BindParam` aliases không khớp | Kiểm tra metadata `-parameters`, request keys |
| Spring không chọn constructor mong muốn | Nhiều constructors/no-arg constructor không phù hợp | Đơn giản hóa DTO, giữ một data constructor rõ |
| `guest-count=abc` gây 400 | Type conversion thất bại, chưa phải `@Min` | Kiểm tra `FieldError.isBindingFailure()` |
| `guest-count=0` gây 400 | Conversion pass, `@Min(1)` thất bại | Assert issue `Min` |
| Nested `contact.email` không validate | Thiếu `@Valid` trên component contact | Bổ sung `@NotNull @Valid` |
| `@Valid` không bắt contact null | `@Valid` bỏ qua null | Dùng thêm `@NotNull` |
| `arrival=20/11/2026` sai | Form dự kiến ISO.DATE | Định nghĩa `@DateTimeFormat`/format contract |
| `setDeclarativeBinding(true)` nhưng field nhạy cảm vẫn nhận | Có thể khai báo chính field đó trong constructor; hoặc cho phép property binding qua allowedFields | Loại khỏi input constructor, kiểm tra binder policy |
| Unknown field không tạo error | Constructor chỉ lấy args cần, unknown có thể bị ignore | Strict input name check nếu cần reject |
| `getSuppressedFields()` rỗng nhưng request có extra param | Suppression chủ yếu thuộc property binding policy | Không dùng suppressed fields làm universal unknown field detector |
| Record có List bị thay đổi bên ngoài | Shallow immutability | Defensive copy và test mutation |
| JSON `guest-name` không nhận đúng | `@BindParam` không là Jackson property annotation | Gửi `guestName` hoặc thiết kế Jackson schema bằng `@JsonProperty` |
| `@Valid` annotation có nhưng không sinh error | Thiếu provider, thiếu @Valid ở argument hoặc validator setup | Kiểm tra starter validation và MockMvc |
| `BindingResult` không được nhận | Đặt sai vị trí; method validation path khác | Đặt ngay sau model attribute, xem handler signature |
| Mọi validation error bị xem 400 client | Return-value constraint có thể là server error | Giữ HTTP status semantics |
| DTO record được bind nhưng domain bị over-post | Dùng `BeanUtils.copyProperties` hoặc map Map keys bừa bãi vào entity | Map từng field, authorization tại service |
| Test MockMvc pass nhưng qua HTTP thật fail | Container/encoding/security filters không giống mock | Test thêm real-server path cho yêu cầu cần thiết |
| Native image bind không hoạt động | Thiếu AOT hints khi implicit model attr | Explicit `@ModelAttribute`, xem native image hints |

## 20. Những giới hạn thiết kế cần nhớ

### 20.1. Constructor binding không tự là authorization

Có DTO immutable hợp lệ không chứng minh user có quyền tạo booking cho một `ownerId` hay tenant cụ thể. Dùng authenticated principal, service policy và domain rules. Đừng suy quyền từ chuỗi field tên `role` hay enum do client tự cung cấp.

### 20.2. Validation khác invariant

`@Min`/`@Max` kiểm tra dữ liệu tại boundary. Các domain invariants như “ngày đến phải trước ngày đi”, “phòng thuộc cùng khách sạn” hoặc “khách được phép đặt phòng này” cần logic business riêng. Nếu muốn invariant không thể bị phá khi object được tạo từ đường khác, cân nhắc kiểm tra trong domain constructor/factory; nhưng ném exception từ web DTO constructor có thể chuyển loại lỗi sang path không mong muốn. Tách web input parsing/validation khỏi domain model.

### 20.3. Bất biến dữ liệu không có nghĩa thread-safe với mọi thành phần

Một record chứa String/Integer/LocalDate và nested record immutable thì an toàn hơn với concurrent reads. Nhưng record có List mutable hoặc bean mutable không tự thread-safe. Nếu cần cache hoặc share object giữa threads, xem sâu tới mutable fields và copy semantics.

### 20.4. Cẩn trọng với `@ModelAttribute` dùng chung từ model/session

Spring MVC có thể tìm model attribute đã tồn tại từ model hoặc session trước khi tạo mới qua constructor. Nếu bean đã được đưa sẵn vào model bởi `@ModelAttribute` method hoặc `@SessionAttributes`, đường binding có thể khác việc luôn khởi tạo một instance mới. Test scenario khi dùng session/model lifecycle; không tuyên bố mọi request luôn gọi canonical constructor.

### 20.5. Kotlin data class và Java class thường

Kotlin data classes cũng hỗ trợ constructor binding, nhưng nullability, default parameters, value classes và validation placement có quy tắc riêng. Bài chọn Java 17 record để giữ runnable code nhất quán. Với ordinary Java final class, cần runtime parameter names và constructor selection rõ ràng.

### 20.6. Native image và reflection

Spring MVC có thể xử lý implicit `@ModelAttribute` ở JVM, nhưng Spring AOT/native image cần hints cho data binding/reflection. Dùng explicit `@ModelAttribute("bookingForm")` giúp framework suy luận input model tốt hơn. Không coi việc test trên JVM là chứng minh native image hoạt động; cần native test riêng nếu sản phẩm deploy GraalVM.

## 21. Checklist review trước khi merge

1. Request DTO có đúng **các trường public input** cần thiết, không chứa owner/role/approval từ client?
2. DTO dùng record hoặc một data constructor rõ ràng?
3. Có `-parameters`/constructor parameter name metadata cho ordinary class?
4. Request field names đã khớp constructor argument names hoặc `@BindParam`?
5. Có nested fields? Đã kiểm thử các paths như `contact.email`?
6. Có `@Valid` trên nested object và `@NotNull` nếu yêu cầu present?
7. Có `@NotNull` cho wrapper types cần phân biệt missing với 0?
8. Có `@DateTimeFormat`/formatter phù hợp với form date/number contract?
9. Controller dùng `@ModelAttribute` explicit để làm rõ đường bind?
10. `@InitBinder` nhắm đúng attribute name?
11. Nếu constructor-only, có `setDeclarativeBinding(true)`?
12. Có tránh `setAllowedFields("*")` vô tình bật lại property binding?
13. Có biết `allowedFields` không hạn chế constructor args?
14. Có test với extra field như `approved=true` để biết là ignored hay rejected?
15. Nếu API yêu cầu reject unknown names, có explicit schema validation?
16. Có `BindingResult` ngay sau model attribute nếu muốn local handling?
17. Có global advice cho controller không nhận `BindingResult`?
18. Có phân biệt `FieldError.isBindingFailure()` và constraint errors?
19. Có test success, missing, malformed type, constraint, nested invalid?
20. Có xem khác biệt JSON Jackson với form constructor binding?
21. Có giới hạn request size, nested depth, List indexes/Map keys?
22. Có defensive copying cho mutable components trong record nếu cần?
23. Có business authorization và mapping domain có chọn lọc?
24. Có tránh echo raw rejected values và stack traces vào API response?
25. Có test HTTP status và error code ổn định, không chỉ 400?
26. Có test compile Maven/JDK 17 và đúng package/file paths khi thực hành?
27. Có test service/database side effects nếu API thực ghi dữ liệu?
28. Có phân biệt output của demo với Spring default behavior?

## 22. Bài tập mở rộng

1. Thay `BookingForm` record bằng final class chỉ có one-arg constructor, rồi kiểm thử `-parameters`.
2. Bỏ `@BindParam("guest-name")`, gửi cả `guest-name` và `guestName` để hiểu mapping.
3. Đổi DTO `Integer guestCount` sang `int` và gửi request thiếu field; chẩn đoán kết quả.
4. Thêm `@Future` trên `arrival`; dùng fixed clock/Validation ClockProvider để tests không phụ thuộc ngày chạy.
5. Thêm nested record `Address(String city, String postalCode)`; bind `address.city`.
6. Bỏ `@Valid` trên `contact` và chứng minh email invalid không bị cascade.
7. Thêm `List<@Valid Room> rooms` và gửi `rooms[0].code`/`rooms[1].code`.
8. Bổ sung giới hạn index và request size cho List; test index lớn mà không tạo danh sách khổng lồ.
9. Thêm `Map<String,String> labels`, test `labels[color]` được nhận nhưng `labels[role]` không được quyền làm thay đổi entity.
10. Viết một record chứa List mutable, sau đó thêm defensive copy và test mutation.
11. Viết `@JsonProperty("guest-name")` cho JSON DTO riêng; không thay @BindParam của form bằng giả định.
12. Bật class-level `@Validated` trên controller thử nghiệm riêng, xem method validation AOP khác MVC handler validation như thế nào.
13. Tạo global `@ControllerAdvice @InitBinder` áp dụng `setDeclarativeBinding(true)`, xác minh không làm hỏng legacy property-binding forms.
14. Thêm custom `DataBinder.NameResolver` cho một naming convention riêng và tests negative cho aliases lạ.
15. Thêm một endpoint update có model attribute từ session để quan sát lifecycle khác constructor mới.
16. Dùng `@WebMvcTest` thay whole-context tests và import đúng binder/advice để so với `@SpringBootTest`.
17. Bổ sung error envelope theo `ProblemDetail` RFC 9457, vẫn giữ machine codes ổn định.
18. Test hai violations trên cùng một field, so issue set thay vì dựa vào thứ tự provider.
19. Thêm custom cross-field validator cho `arrival` và `departure`; giữ mapping object-level errors.
20. Refactor controller thành pure input mapping và service layer, dùng `@MockitoBean` để assert invalid request không gọi service.
21. Viết integration test trên real servlet container với form UTF-8 có tên người Việt.
22. Xây API multi-tenant: user từ authentication, ownerId không có trong DTO, test chống over-posting.
23. Kiểm thử JSON sai numeric type và form sai numeric type: cùng 400 nhưng nguyên nhân/exception khác nhau.
24. Làm một sample immutable class có constructor overload, kiểm chứng Spring chọn constructor nào trong version hiện dùng.
25. Tạo native image/AOT test nếu deploy GraalVM.

**Kết luận:** Spring MVC constructor binding cho phép xây DTO bất biến mà không cần setters. Với Java 17, `record` và `@BindParam` giúp xác định rõ input contract; `setDeclarativeBinding(true)` hạn chế setter binding ngoài ý định. Nhưng để API an toàn, cần **loại privileged fields khỏi constructor**, phân biệt **binding vs validation**, kiểm tra unknown input nếu hợp đồng yêu cầu, làm defensive copy cho mutable collections, và map DTO sang domain qua authorization. Bộ MockMvc/JUnit tests của bài giúp xác minh các hành vi đó thay vì chỉ tin vào annotation.

## 23. Tài liệu chính thức

- [Spring Framework 6.2 — @ModelAttribute constructor binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder, declarative binding, allowedFields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — Data Binding: constructor vs property](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindParam API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)
- [Spring Framework 6.2 — MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — DateTimeFormat API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Spring Framework 6.2 — MVC @RequestBody JSON](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Model design, security and allowed fields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Boot 3.5 — Testing MVC applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Oracle Java 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html)